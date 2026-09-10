"""Offline contract for a startup-only C3 maintenance seam installation.

The contract models an atomic, temporary coordinator swap before any runtime,
worker or request-serving activity begins.  It never imports or mutates the real
seam.  All state and compare-and-swap operations are injected synthetic ports.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-STARTUP-ONLY-SEAM-INSTALLATION-CONTRACT-V1"
)
PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1 = (
    "C3_CLOSED_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_V1"
)
PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_KEYS = frozenset({"ack", "scope_attestation", "evidence", "request_sha256"})
_SAFE_CONTROL_VECTOR = {
    "enable_real_trading": False,
    "broker_dry_run": True,
    "falcon_mode": "VERIFY",
    "central_real_execution_enabled": False,
    "central_real_pilot_enabled": False,
    "live_trading_enabled": False,
    "order_submission_authorized": False,
}


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


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def startup_only_seam_installation_request_sha256_v1(
    request: Mapping[str, Any],
) -> str:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    return _stable_sha256(
        {key: value for key, value in request.items() if key != "request_sha256"}
    )


class PrebootstrapStartupOnlySeamInstallationBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_STARTUP_ONLY_SEAM_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapStartupOnlySeamInstallationConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class PrebootstrapStartupOnlySeamInstallationPermitV1:
    mode: str
    startup_phase: str
    generation_before: int
    generation_installed: int
    writer_mutations_allowed: bool
    runtime_activation_allowed: bool
    runtime_started: bool
    process_boot_epoch_sha256: str = field(repr=False)
    replacement_coordinator_binding_sha256: str = field(repr=False)
    installation_receipt_sha256: str = field(repr=False)


class PrebootstrapStartupOnlySeamInstallationContractV1:
    """Temporarily install one exact maintenance coordinator before runtime."""

    def __init__(
        self,
        *,
        seam_port: Any,
        dormant_coordinator: Any,
        maintenance_coordinator: Any,
        maintenance_coordinator_port: Any,
        trading_controls: Callable[[], Mapping[str, Any]],
        config: PrebootstrapStartupOnlySeamInstallationConfigV1 | None = None,
    ) -> None:
        required_seam_methods = (
            "snapshot_installation_state",
            "current_coordinator",
            "compare_and_swap_coordinator",
        )
        if seam_port is None or not all(
            callable(getattr(seam_port, name, None))
            for name in required_seam_methods
        ):
            raise TypeError("one seam port with snapshot, identity and CAS is required")
        if dormant_coordinator is None or maintenance_coordinator is None:
            raise TypeError("dormant and maintenance coordinators are required")
        if (
            maintenance_coordinator_port is None
            or getattr(maintenance_coordinator_port, "_coordinator", None)
            is not maintenance_coordinator
            or not callable(getattr(maintenance_coordinator_port, "snapshot", None))
            or not callable(
                getattr(maintenance_coordinator_port, "storage_readiness", None)
            )
        ):
            raise TypeError(
                "maintenance coordinator must match its physical coordinator port"
            )
        if not callable(trading_controls):
            raise TypeError("trading_controls is required")
        self._seam = seam_port
        self._dormant = dormant_coordinator
        self._maintenance = maintenance_coordinator
        self._maintenance_port = maintenance_coordinator_port
        self._trading_controls = trading_controls
        self._config = config or PrebootstrapStartupOnlySeamInstallationConfigV1()
        self._active_permit: PrebootstrapStartupOnlySeamInstallationPermitV1 | None = None
        self._consumed: set[str] = set()

    def __repr__(self) -> str:
        return "<PrebootstrapStartupOnlySeamInstallationContractV1 protected>"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_CONTRACT_V1_VERSION,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "writer_mutations_allowed": False,
            "runtime_activation_allowed": False,
            "seam_installation_simulated": False,
            "rollback_attempted": False,
            "rollback_verified": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def snapshot(self) -> dict[str, Any]:
        value = self._base()
        enabled = bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1
        )
        value.update(
            enabled=enabled,
            default_off=not enabled,
            installation_active=self._active_permit is not None,
            consumed_request_count=len(self._consumed),
        )
        return value

    def _require_enabled(self) -> None:
        if self._config.enabled is not True:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_REQUIRED"
            )

    def _validate_request(
        self, request: Any
    ) -> tuple[str, Mapping[str, Any]]:
        if not isinstance(request, Mapping) or set(request) != _REQUEST_KEYS:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_INVALID"
            )
        if request.get("ack") != PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_ACK_REQUIRED"
            )
        if (
            request.get("scope_attestation")
            != PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_SCOPE_INVALID"
            )
        supplied = _valid_sha256(request.get("request_sha256"))
        try:
            expected = startup_only_seam_installation_request_sha256_v1(request)
        except (TypeError, ValueError, OverflowError) as exc:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_INVALID"
            ) from exc
        if not supplied or not hmac.compare_digest(supplied, expected):
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_HASH_MISMATCH"
            )
        evidence = request.get("evidence")
        if not isinstance(evidence, Mapping):
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_EVIDENCE_INVALID"
            )
        return supplied, evidence

    @staticmethod
    def _startup_snapshot_safe(snapshot: Any) -> bool:
        return bool(
            isinstance(snapshot, Mapping)
            and snapshot.get("mode") == "DORMANT"
            and snapshot.get("startup_phase") == "PRE_RUNTIME"
            and snapshot.get("runtime_started") is False
            and snapshot.get("workers_started") is False
            and snapshot.get("server_accepting_requests") is False
            and snapshot.get("writer_invocations_seen") == 0
            and type(snapshot.get("generation")) is int
            and snapshot.get("generation") >= 0
            and _valid_sha256(snapshot.get("process_boot_epoch_sha256"))
            and _valid_sha256(snapshot.get("current_coordinator_identity_sha256"))
            and snapshot.get("writer_mutations_allowed") is True
            and snapshot.get("runtime_activation_allowed") is False
            and snapshot.get("synthetic_only") is True
            and snapshot.get("runtime_integrated") is False
        )

    @staticmethod
    def _maintenance_coordinator_safe(snapshot: Any, storage: Any) -> bool:
        return bool(
            isinstance(snapshot, Mapping)
            and snapshot.get("enabled") is True
            and snapshot.get("registered_writer_count") == 19
            and snapshot.get("all_writers_registered") is True
            and snapshot.get("inflight_mutations") == 0
            and snapshot.get("maintenance_lease_state") in (None, "RELEASED")
            and snapshot.get("runtime_integrated") is False
            and isinstance(storage, Mapping)
            and storage.get("shared_lock_backend_ready") is True
            and storage.get("maintenance_lease_store_ready") is True
            and storage.get("same_storage_root_verified") is True
            and storage.get("coordinator_dependency_identity_verified") is True
            and _valid_sha256(storage.get("storage_root_binding_sha256"))
            and storage.get("synthetic_only") is True
            and storage.get("runtime_integrated") is False
        )

    @staticmethod
    def _receipt_safe(receipt: Any, *, expected_generation: int) -> bool:
        if not isinstance(receipt, Mapping):
            return False
        payload = dict(receipt)
        supplied = _valid_sha256(payload.pop("receipt_sha256", None))
        return bool(
            receipt.get("ok") is True
            and receipt.get("status") == "SYNTHETIC_SEAM_COORDINATOR_CAS_COMMITTED"
            and receipt.get("generation_before") == expected_generation
            and receipt.get("generation_after") == expected_generation + 1
            and receipt.get("mode_after") == "MAINTENANCE_ONLY"
            and receipt.get("runtime_started") is False
            and receipt.get("writer_mutations_allowed") is False
            and receipt.get("runtime_activation_allowed") is False
            and receipt.get("synthetic_only") is True
            and receipt.get("write_executed") is False
            and receipt.get("registry_write") is False
            and supplied
            and hmac.compare_digest(supplied, _stable_sha256(payload))
        )

    def _rollback(self, generation: int) -> bool:
        try:
            receipt = self._seam.compare_and_swap_coordinator(
                expected_generation=generation,
                expected_coordinator=self._maintenance,
                replacement_coordinator=self._dormant,
                replacement_mode="DORMANT",
            )
            current = self._seam.current_coordinator()
            state = self._seam.snapshot_installation_state()
        except Exception:
            return False
        return bool(
            isinstance(receipt, Mapping)
            and receipt.get("ok") is True
            and receipt.get("generation_before") == generation
            and receipt.get("generation_after") == generation + 1
            and receipt.get("mode_after") == "DORMANT"
            and current is self._dormant
            and isinstance(state, Mapping)
            and state.get("mode") == "DORMANT"
            and state.get("generation") == generation + 1
            and state.get("runtime_started") is False
            and state.get("writer_mutations_allowed") is True
            and state.get("runtime_activation_allowed") is False
        )

    @contextmanager
    def maintenance_only_installation(
        self, request: Any
    ) -> Iterator[PrebootstrapStartupOnlySeamInstallationPermitV1]:
        self._require_enabled()
        if self._active_permit is not None:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_NESTED_INSTALLATION_FORBIDDEN"
            )
        request_sha, evidence = self._validate_request(request)
        if request_sha in self._consumed:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_REPLAY_BLOCKED"
            )
        try:
            controls = self._trading_controls()
            before = self._seam.snapshot_installation_state()
            current = self._seam.current_coordinator()
            maintenance_snapshot = self._maintenance_port.snapshot()
            storage = self._maintenance_port.storage_readiness()
        except Exception as exc:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_PREFLIGHT_FAILED"
            ) from exc
        evidence_matches = bool(
            isinstance(controls, Mapping)
            and dict(controls) == _SAFE_CONTROL_VECTOR
            and self._startup_snapshot_safe(before)
            and current is self._dormant
            and self._maintenance_coordinator_safe(maintenance_snapshot, storage)
            and evidence.get("trading_controls") == _SAFE_CONTROL_VECTOR
            and evidence.get("startup_state") == before
            and evidence.get("replacement_coordinator_binding_sha256")
            == storage.get("storage_root_binding_sha256")
            and evidence.get("synthetic_only") is True
            and evidence.get("runtime_binding_satisfied") is False
            and evidence.get("production_authorization_valid") is False
        )
        if not evidence_matches:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_PREFLIGHT_UNSAFE"
            )
        generation = before["generation"]
        self._consumed.add(request_sha)
        try:
            receipt = self._seam.compare_and_swap_coordinator(
                expected_generation=generation,
                expected_coordinator=self._dormant,
                replacement_coordinator=self._maintenance,
                replacement_mode="MAINTENANCE_ONLY",
            )
        except Exception as exc:
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_CAS_FAILED"
            ) from exc
        installed_generation = generation + 1
        installed = False
        try:
            after = self._seam.snapshot_installation_state()
            installed = bool(
                self._receipt_safe(receipt, expected_generation=generation)
                and self._seam.current_coordinator() is self._maintenance
                and isinstance(after, Mapping)
                and after.get("mode") == "MAINTENANCE_ONLY"
                and after.get("generation") == installed_generation
                and after.get("startup_phase") == "PRE_RUNTIME"
                and after.get("runtime_started") is False
                and after.get("workers_started") is False
                and after.get("server_accepting_requests") is False
                and after.get("writer_invocations_seen") == 0
                and after.get("writer_mutations_allowed") is False
                and after.get("runtime_activation_allowed") is False
            )
        except Exception:
            installed = False
        if not installed:
            if not self._rollback(installed_generation):
                raise PrebootstrapStartupOnlySeamInstallationBlocked(
                    "PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALL_AND_ROLLBACK_FAILED"
                )
            raise PrebootstrapStartupOnlySeamInstallationBlocked(
                "PREBOOTSTRAP_STARTUP_ONLY_SEAM_POSTCONDITION_FAILED"
            )
        permit = PrebootstrapStartupOnlySeamInstallationPermitV1(
            mode="MAINTENANCE_ONLY",
            startup_phase="PRE_RUNTIME",
            generation_before=generation,
            generation_installed=installed_generation,
            writer_mutations_allowed=False,
            runtime_activation_allowed=False,
            runtime_started=False,
            process_boot_epoch_sha256=before["process_boot_epoch_sha256"],
            replacement_coordinator_binding_sha256=storage[
                "storage_root_binding_sha256"
            ],
            installation_receipt_sha256=receipt["receipt_sha256"],
        )
        self._active_permit = permit
        body_error: BaseException | None = None
        try:
            yield permit
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            self._active_permit = None
            rollback_ok = self._rollback(installed_generation)
            if not rollback_ok:
                raise PrebootstrapStartupOnlySeamInstallationBlocked(
                    "PREBOOTSTRAP_STARTUP_ONLY_SEAM_ROLLBACK_FAILED"
                ) from body_error


__all__ = [
    "PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1",
    "PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1",
    "PrebootstrapStartupOnlySeamInstallationBlocked",
    "PrebootstrapStartupOnlySeamInstallationConfigV1",
    "PrebootstrapStartupOnlySeamInstallationContractV1",
    "PrebootstrapStartupOnlySeamInstallationPermitV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_CONTRACT_V1_VERSION",
    "startup_only_seam_installation_request_sha256_v1",
]
