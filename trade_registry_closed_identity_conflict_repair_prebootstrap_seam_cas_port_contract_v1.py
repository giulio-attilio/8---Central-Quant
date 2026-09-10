"""Offline contract for an atomic startup-only C3 runtime seam port.

The port is production-shaped but deliberately detached from the real seam.  It
owns no filesystem or network dependency and accepts only injected, in-memory
state primitives.  A later integration must explicitly bind the real seam and
its writer decorators to this contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-SEAM-CAS-PORT-CONTRACT-V1"
)
PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_SEAM_CAS_PORT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUNTIME_STATE_KEYS = frozenset(
    {"runtime_started", "workers_started", "server_accepting_requests"}
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower().strip()
    return candidate if _SHA256_RE.fullmatch(candidate) else None


class PrebootstrapSeamCasPortBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_SEAM_CAS_PORT_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapSeamCasPortConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    process_boot_epoch_sha256: str | None = field(default=None, repr=False)


class PrebootstrapSeamCasPortContractV1:
    """Expose identity-bound startup state and atomic coordinator CAS offline."""

    def __init__(
        self,
        *,
        dormant_coordinator: Any,
        coordinator_getter: Callable[[], Any],
        coordinator_setter: Callable[[Any], None],
        coordinator_identity_sha256: Callable[[Any], str],
        runtime_state: Callable[[], Mapping[str, Any]],
        atomic_lock: Any,
        config: PrebootstrapSeamCasPortConfigV1 | None = None,
    ) -> None:
        dependencies = {
            "coordinator_getter": coordinator_getter,
            "coordinator_setter": coordinator_setter,
            "coordinator_identity_sha256": coordinator_identity_sha256,
            "runtime_state": runtime_state,
        }
        if dormant_coordinator is None:
            raise TypeError("dormant_coordinator is required")
        if not all(callable(value) for value in dependencies.values()):
            raise TypeError("all seam state dependencies must be callable")
        if atomic_lock is None or not all(
            callable(getattr(atomic_lock, name, None))
            for name in ("__enter__", "__exit__")
        ):
            raise TypeError("one context-manager atomic_lock is required")
        self._dormant = dormant_coordinator
        self._get = coordinator_getter
        self._set = coordinator_setter
        self._identity = coordinator_identity_sha256
        self._runtime_state = runtime_state
        self._lock = atomic_lock
        self._config = config or PrebootstrapSeamCasPortConfigV1()
        self._mode = "DORMANT"
        self._generation = 0
        self._writer_invocations_seen = 0
        self._installed_coordinator: Any | None = None
        self._poisoned = False

    def __repr__(self) -> str:
        return "<PrebootstrapSeamCasPortContractV1 protected>"

    def contract_snapshot(self) -> dict[str, Any]:
        enabled = bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1
            and _valid_sha256(self._config.process_boot_epoch_sha256)
        )
        return {
            "ok": enabled and not self._poisoned,
            "status": (
                "C3_PREBOOTSTRAP_SEAM_CAS_PORT_OFFLINE_READY"
                if enabled and not self._poisoned
                else (
                    "C3_PREBOOTSTRAP_SEAM_CAS_PORT_POISONED"
                    if self._poisoned
                    else "C3_PREBOOTSTRAP_SEAM_CAS_PORT_DORMANT_DEFAULT_OFF"
                )
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_CONTRACT_V1_VERSION,
            "enabled": enabled,
            "default_off": not enabled,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "runtime_activation_allowed": False,
            "poisoned": self._poisoned,
            "generation": self._generation,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def _require_enabled(self) -> str:
        if self._config.enabled is not True:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_REQUIRED"
            )
        boot_sha = _valid_sha256(self._config.process_boot_epoch_sha256)
        if not boot_sha:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_BOOT_IDENTITY_REQUIRED"
            )
        if self._poisoned:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_POISONED"
            )
        return boot_sha

    def _read_runtime_state(self) -> dict[str, bool]:
        try:
            value = self._runtime_state()
        except Exception as exc:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_RUNTIME_STATE_FAILED"
            ) from exc
        if (
            not isinstance(value, Mapping)
            or set(value) != _RUNTIME_STATE_KEYS
            or not all(type(value[key]) is bool for key in _RUNTIME_STATE_KEYS)
        ):
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_RUNTIME_STATE_INVALID"
            )
        return {key: value[key] for key in _RUNTIME_STATE_KEYS}

    def _identity_sha(self, coordinator: Any) -> str:
        try:
            value = _valid_sha256(self._identity(coordinator))
        except Exception as exc:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_COORDINATOR_IDENTITY_FAILED"
            ) from exc
        if not value:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_COORDINATOR_IDENTITY_INVALID"
            )
        return value

    def _current_locked(self) -> Any:
        try:
            current = self._get()
        except Exception as exc:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_COORDINATOR_READ_FAILED"
            ) from exc
        expected = (
            self._dormant if self._mode == "DORMANT" else self._installed_coordinator
        )
        if expected is None or current is not expected:
            self._poisoned = True
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_COORDINATOR_DRIFT"
            )
        return current

    def _snapshot_locked(self, boot_sha: str) -> dict[str, Any]:
        runtime = self._read_runtime_state()
        current = self._current_locked()
        runtime_started = any(runtime.values())
        return {
            "mode": self._mode,
            "startup_phase": "RUNTIME_STARTED" if runtime_started else "PRE_RUNTIME",
            **runtime,
            "writer_invocations_seen": self._writer_invocations_seen,
            "generation": self._generation,
            "process_boot_epoch_sha256": boot_sha,
            "current_coordinator_identity_sha256": self._identity_sha(current),
            "writer_mutations_allowed": self._mode == "DORMANT",
            "runtime_activation_allowed": False,
            "synthetic_only": True,
            "runtime_integrated": False,
        }

    def snapshot_installation_state(self) -> dict[str, Any]:
        boot_sha = self._require_enabled()
        with self._lock:
            return self._snapshot_locked(boot_sha)

    def current_coordinator(self) -> Any:
        self._require_enabled()
        with self._lock:
            return self._current_locked()

    def before_writer_invocation(self, writer_id: str) -> dict[str, Any]:
        self._require_enabled()
        candidate = str(writer_id or "").strip()
        if not candidate:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_ID_REQUIRED"
            )
        with self._lock:
            self._current_locked()
            self._writer_invocations_seen += 1
            if self._mode != "DORMANT":
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_BLOCKED_MAINTENANCE_ONLY"
                )
            return {
                "ok": True,
                "status": "C3_PREBOOTSTRAP_SEAM_WRITER_ALLOWED_DORMANT",
                "writer_id": candidate,
                "writer_invocations_seen": self._writer_invocations_seen,
                "mode": self._mode,
                "runtime_activation_allowed": False,
            }

    def _restore_expected_locked(self, expected: Any) -> bool:
        try:
            self._set(expected)
            return self._get() is expected
        except Exception:
            return False

    def compare_and_swap_coordinator(
        self,
        *,
        expected_generation: int,
        expected_coordinator: Any,
        replacement_coordinator: Any,
        replacement_mode: str,
    ) -> dict[str, Any]:
        self._require_enabled()
        if type(expected_generation) is not int or expected_generation < 0:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_GENERATION_INVALID"
            )
        if replacement_coordinator is None:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_REPLACEMENT_REQUIRED"
            )
        if replacement_mode not in {"DORMANT", "MAINTENANCE_ONLY"}:
            raise PrebootstrapSeamCasPortBlocked(
                "PREBOOTSTRAP_SEAM_CAS_PORT_MODE_INVALID"
            )
        with self._lock:
            runtime = self._read_runtime_state()
            if any(runtime.values()):
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_RUNTIME_ALREADY_STARTED"
                )
            current = self._current_locked()
            if self._generation != expected_generation:
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_GENERATION_MISMATCH"
                )
            if current is not expected_coordinator:
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_EXPECTED_COORDINATOR_MISMATCH"
                )
            installing = self._mode == "DORMANT" and replacement_mode == "MAINTENANCE_ONLY"
            restoring = self._mode == "MAINTENANCE_ONLY" and replacement_mode == "DORMANT"
            if not (installing or restoring):
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_TRANSITION_INVALID"
                )
            if installing:
                if replacement_coordinator is self._dormant:
                    raise PrebootstrapSeamCasPortBlocked(
                        "PREBOOTSTRAP_SEAM_CAS_PORT_MAINTENANCE_IDENTITY_INVALID"
                    )
                if self._writer_invocations_seen != 0:
                    raise PrebootstrapSeamCasPortBlocked(
                        "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_ALREADY_INVOKED"
                    )
            elif (
                replacement_coordinator is not self._dormant
                or expected_coordinator is not self._installed_coordinator
            ):
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_DORMANT_RESTORE_IDENTITY_INVALID"
                )
            replacement_identity_sha = self._identity_sha(replacement_coordinator)
            generation_before = self._generation
            try:
                self._set(replacement_coordinator)
                committed = self._get() is replacement_coordinator
            except Exception as exc:
                restored = self._restore_expected_locked(current)
                if not restored:
                    self._poisoned = True
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_BACKEND_WRITE_FAILED"
                ) from exc
            if not committed:
                restored = self._restore_expected_locked(current)
                if not restored:
                    self._poisoned = True
                raise PrebootstrapSeamCasPortBlocked(
                    "PREBOOTSTRAP_SEAM_CAS_PORT_BACKEND_COMMIT_UNVERIFIED"
                )
            self._generation += 1
            self._mode = replacement_mode
            self._installed_coordinator = (
                replacement_coordinator if installing else None
            )
            receipt = {
                "ok": True,
                "status": "SYNTHETIC_SEAM_COORDINATOR_CAS_COMMITTED",
                "generation_before": generation_before,
                "generation_after": self._generation,
                "mode_after": replacement_mode,
                **runtime,
                "writer_mutations_allowed": replacement_mode == "DORMANT",
                "runtime_activation_allowed": False,
                "coordinator_identity_sha256": replacement_identity_sha,
                "process_boot_epoch_sha256": _valid_sha256(
                    self._config.process_boot_epoch_sha256
                ),
                "synthetic_only": True,
                "write_executed": False,
                "registry_write": False,
            }
            receipt["receipt_sha256"] = _stable_sha256(receipt)
            return receipt


__all__ = [
    "PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1",
    "PrebootstrapSeamCasPortBlocked",
    "PrebootstrapSeamCasPortConfigV1",
    "PrebootstrapSeamCasPortContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_CONTRACT_V1_VERSION",
]
