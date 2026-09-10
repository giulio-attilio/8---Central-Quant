"""Dormant offline adapter from a runtime-seam surface to the C3 CAS port.

The real runtime seam is not imported or changed here.  This contract defines
the exact production-shaped surface that it must expose later: one shared lock,
identity-bound coordinator replacement and one dynamic guard covering all 19
writers.  Tests use only an in-memory facade.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_contract_v1 as port_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-REAL-SEAM-CAS-ADAPTER-CONTRACT-V1"
)
PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_V1"
)
EXPECTED_RUNTIME_SEAM_MODULE_NAME_V1 = (
    "trade_registry_closed_identity_conflict_repair_runtime_seam_v1"
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


class PrebootstrapRealSeamCasAdapterBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapRealSeamCasAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    process_boot_epoch_sha256: str | None = field(default=None, repr=False)


class PrebootstrapRealSeamCasAdapterBindingV1:
    __slots__ = ("_port", "_writer_guard", "_surface")

    def __init__(self, *, port: Any, writer_guard: Callable[[str], Any], surface: Any):
        self._port = port
        self._writer_guard = writer_guard
        self._surface = surface

    def __repr__(self) -> str:
        return "<PrebootstrapRealSeamCasAdapterBindingV1 protected>"

    @property
    def port(self) -> Any:
        return self._port

    @property
    def writer_guard(self) -> Callable[[str], Any]:
        return self._writer_guard

    def binding_snapshot(self) -> dict[str, Any]:
        return {
            "ok": self._surface.current_writer_guard() is self._writer_guard,
            "status": "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BOUND_OFFLINE",
            "writer_guard_bound": self._surface.current_writer_guard()
            is self._writer_guard,
            "same_atomic_lock": True,
            "registered_writer_count": 19,
            "all_writers_routed": True,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "runtime_activation_allowed": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


class PrebootstrapRealSeamCasAdapterContractV1:
    """Bind an attested seam facade to one exact offline CAS-port instance."""

    _REQUIRED_METHODS = (
        "current_coordinator",
        "compare_and_swap_coordinator",
        "coordinator_identity_sha256",
        "current_writer_guard",
        "compare_and_swap_writer_guard",
    )

    def __init__(
        self,
        *,
        seam_surface: Any,
        dormant_coordinator: Any,
        maintenance_coordinator: Any,
        runtime_state: Callable[[], Mapping[str, Any]],
        config: PrebootstrapRealSeamCasAdapterConfigV1 | None = None,
    ) -> None:
        if seam_surface is None or dormant_coordinator is None or maintenance_coordinator is None:
            raise TypeError("seam surface and both coordinators are required")
        if not callable(runtime_state):
            raise TypeError("runtime_state is required")
        self._surface = seam_surface
        self._dormant = dormant_coordinator
        self._maintenance = maintenance_coordinator
        self._runtime_state = runtime_state
        self._config = config or PrebootstrapRealSeamCasAdapterConfigV1()
        self._binding: PrebootstrapRealSeamCasAdapterBindingV1 | None = None

    def __repr__(self) -> str:
        return "<PrebootstrapRealSeamCasAdapterContractV1 protected>"

    def snapshot(self) -> dict[str, Any]:
        enabled = bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1
            and _valid_sha256(self._config.process_boot_epoch_sha256)
        )
        return {
            "ok": enabled,
            "status": (
                "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_OFFLINE_READY"
                if enabled
                else "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_DORMANT_DEFAULT_OFF"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_CONTRACT_V1_VERSION,
            "enabled": enabled,
            "default_off": not enabled,
            "binding_created": self._binding is not None,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "runtime_activation_allowed": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def _require_enabled(self) -> str:
        if self._config.enabled is not True:
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_REQUIRED"
            )
        boot_sha = _valid_sha256(self._config.process_boot_epoch_sha256)
        if not boot_sha:
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BOOT_IDENTITY_REQUIRED"
            )
        return boot_sha

    def _validate_surface(self) -> Any:
        if getattr(self._surface, "module_name", None) != EXPECTED_RUNTIME_SEAM_MODULE_NAME_V1:
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_MODULE_IDENTITY_MISMATCH"
            )
        if not all(
            callable(getattr(self._surface, name, None))
            for name in self._REQUIRED_METHODS
        ):
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SURFACE_INCOMPLETE"
            )
        lock = getattr(self._surface, "atomic_lock", None)
        if lock is None or not all(
            callable(getattr(lock, name, None)) for name in ("__enter__", "__exit__")
        ):
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_ATOMIC_LOCK_REQUIRED"
            )
        return lock

    def _runtime_safe(self) -> bool:
        try:
            state = self._runtime_state()
        except Exception:
            return False
        return bool(
            isinstance(state, Mapping)
            and set(state) == _RUNTIME_STATE_KEYS
            and all(state[key] is False for key in _RUNTIME_STATE_KEYS)
        )

    @staticmethod
    def _coordinator_safe(coordinator: Any, *, enabled: bool) -> bool:
        try:
            snapshot = coordinator.snapshot()
        except Exception:
            return False
        if not isinstance(snapshot, Mapping) or snapshot.get("enabled") is not enabled:
            return False
        if enabled:
            return bool(
                snapshot.get("registered_writer_count") == 19
                and snapshot.get("all_writers_registered") is True
                and snapshot.get("inflight_mutations") == 0
                and snapshot.get("maintenance_lease_state") in (None, "RELEASED")
            )
        return True

    @staticmethod
    def _receipt_safe(receipt: Any, *, status: str) -> bool:
        if not isinstance(receipt, Mapping):
            return False
        payload = dict(receipt)
        supplied = _valid_sha256(payload.pop("receipt_sha256", None))
        return bool(
            receipt.get("ok") is True
            and receipt.get("status") == status
            and receipt.get("synthetic_only") is True
            and receipt.get("runtime_integrated") is False
            and receipt.get("write_executed") is False
            and receipt.get("registry_write") is False
            and supplied
            and hmac.compare_digest(supplied, _stable_sha256(payload))
        )

    def bind_offline(self) -> PrebootstrapRealSeamCasAdapterBindingV1:
        boot_sha = self._require_enabled()
        if self._binding is not None:
            raise PrebootstrapRealSeamCasAdapterBlocked(
                "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_ALREADY_BOUND"
            )
        lock = self._validate_surface()
        with lock:
            if not self._runtime_safe():
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_RUNTIME_ALREADY_STARTED"
                )
            if self._surface.current_coordinator() is not self._dormant:
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_DORMANT_IDENTITY_MISMATCH"
                )
            if self._surface.current_writer_guard() is not None:
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_WRITER_GUARD_ALREADY_BOUND"
                )
            if not self._coordinator_safe(self._dormant, enabled=False):
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_DORMANT_UNSAFE"
                )
            if not self._coordinator_safe(self._maintenance, enabled=True):
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_MAINTENANCE_UNSAFE"
                )

        def set_coordinator(replacement: Any) -> None:
            current = self._surface.current_coordinator()
            receipt = self._surface.compare_and_swap_coordinator(
                expected_coordinator=current,
                replacement_coordinator=replacement,
            )
            if not self._receipt_safe(
                receipt, status="C3_PREBOOTSTRAP_REAL_SEAM_COORDINATOR_CAS_COMMITTED"
            ):
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_COORDINATOR_CAS_UNVERIFIED"
                )

        port = port_contract.PrebootstrapSeamCasPortContractV1(
            dormant_coordinator=self._dormant,
            coordinator_getter=self._surface.current_coordinator,
            coordinator_setter=set_coordinator,
            coordinator_identity_sha256=self._surface.coordinator_identity_sha256,
            runtime_state=self._runtime_state,
            atomic_lock=lock,
            config=port_contract.PrebootstrapSeamCasPortConfigV1(
                enabled=True,
                scope_attestation=port_contract.PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1,
                process_boot_epoch_sha256=boot_sha,
            ),
        )
        writer_guard = port.before_writer_invocation
        with lock:
            if not self._runtime_safe():
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_RUNTIME_ALREADY_STARTED"
                )
            try:
                receipt = self._surface.compare_and_swap_writer_guard(
                    expected_guard=None,
                    replacement_guard=writer_guard,
                    atomic_lock=lock,
                )
            except Exception as exc:
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_WRITER_GUARD_CAS_FAILED"
                ) from exc
            valid = bool(
                self._receipt_safe(
                    receipt, status="C3_PREBOOTSTRAP_REAL_SEAM_WRITER_GUARD_CAS_COMMITTED"
                )
                and receipt.get("registered_writer_count") == 19
                and receipt.get("all_writers_routed") is True
                and receipt.get("dynamic_at_invocation") is True
                and receipt.get("same_atomic_lock") is True
                and self._surface.current_writer_guard() is writer_guard
            )
            if not valid:
                rollback_ok = False
                try:
                    rollback = self._surface.compare_and_swap_writer_guard(
                        expected_guard=writer_guard,
                        replacement_guard=None,
                        atomic_lock=lock,
                    )
                    rollback_ok = bool(
                        self._receipt_safe(
                            rollback,
                            status="C3_PREBOOTSTRAP_REAL_SEAM_WRITER_GUARD_CAS_COMMITTED",
                        )
                        and self._surface.current_writer_guard() is None
                    )
                except Exception:
                    rollback_ok = False
                raise PrebootstrapRealSeamCasAdapterBlocked(
                    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_WRITER_GUARD_BINDING_UNSAFE"
                    if rollback_ok
                    else "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_WRITER_GUARD_ROLLBACK_FAILED"
                )
        self._binding = PrebootstrapRealSeamCasAdapterBindingV1(
            port=port,
            writer_guard=writer_guard,
            surface=self._surface,
        )
        return self._binding


__all__ = [
    "EXPECTED_RUNTIME_SEAM_MODULE_NAME_V1",
    "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1",
    "PrebootstrapRealSeamCasAdapterBindingV1",
    "PrebootstrapRealSeamCasAdapterBlocked",
    "PrebootstrapRealSeamCasAdapterConfigV1",
    "PrebootstrapRealSeamCasAdapterContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_CONTRACT_V1_VERSION",
]
