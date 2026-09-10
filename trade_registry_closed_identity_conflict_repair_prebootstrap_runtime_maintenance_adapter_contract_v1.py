"""Offline contract for adapting one runtime-shaped pre-bootstrap lease.

This module deliberately has no production bindings.  It accepts only injected
ports, keeps the adapter default-off and exposes the callback shape required by
the offline pre-bootstrap bridge.  It never imports the application runtime,
opens files, uses the network or calls a broker.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-RUNTIME-MAINTENANCE-ADAPTER-CONTRACT-V1"
)
PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_RESULT_FLAGS = {
    "synthetic_only": True,
    "real_registry_accessed": False,
    "write_executed": False,
    "registry_write": False,
    "network_accessed": False,
    "broker_called": False,
    "no_order_sent": True,
}
_REQUIRED_COORDINATOR_TRUE = (
    "enabled",
    "maintenance_only",
    "all_writers_registered",
    "shared_lock_backend_ready",
    "maintenance_lease_store_ready",
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


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _permit_value(permit: Any, name: str) -> Any:
    if isinstance(permit, Mapping):
        return permit.get(name)
    return getattr(permit, name, None)


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _safe_port_result(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and all(value.get(key) is expected for key, expected in _SAFE_RESULT_FLAGS.items())
    )


class PrebootstrapRuntimeMaintenanceAdapterBlocked(RuntimeError):
    """Fail-closed adapter error carrying only a sanitized reason code."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_RUNTIME_ADAPTER_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapRuntimeMaintenanceAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class PrebootstrapMaintenancePermitAdapterV1:
    """Sanitized bridge permit bound to one hidden runtime-shaped permit."""

    state: str
    registered_writer_count: int
    inflight_mutations: int
    shared_lock_acquired: bool
    maintenance_only: bool
    writer_mutations_allowed: bool
    runtime_activation_allowed: bool
    maintenance_epoch: str = field(repr=False)
    lock_namespace_sha256: str = field(repr=False)
    permit_binding_sha256: str = field(repr=False)


class PrebootstrapRuntimeMaintenanceAdapterContractV1:
    """Adapt injected runtime-shaped ports to one offline bridge invocation.

    The adapter owns exactly one outer maintenance context.  Every phase gets
    the same raw permit instance; recovery is therefore permit-aware and never
    opens a nested lease.  Bootstrap is supplied through a dedicated
    maintenance port instead of the ordinary writer-decorated runtime path.
    """

    def __init__(
        self,
        *,
        coordinator_status: Callable[[], Mapping[str, Any]],
        runtime_maintenance_lease: Callable[[], AbstractContextManager[Any]],
        repair_under_maintenance: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        bootstrap_under_maintenance: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        recovery_under_existing_maintenance: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        postflight_under_maintenance: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        rollback_under_maintenance: Callable[[Mapping[str, Any], Any], Mapping[str, Any]],
        config: PrebootstrapRuntimeMaintenanceAdapterConfigV1 | None = None,
    ) -> None:
        ports = {
            "coordinator_status": coordinator_status,
            "runtime_maintenance_lease": runtime_maintenance_lease,
            "repair_under_maintenance": repair_under_maintenance,
            "bootstrap_under_maintenance": bootstrap_under_maintenance,
            "recovery_under_existing_maintenance": recovery_under_existing_maintenance,
            "postflight_under_maintenance": postflight_under_maintenance,
            "rollback_under_maintenance": rollback_under_maintenance,
        }
        if not all(callable(port) for port in ports.values()):
            raise TypeError("all pre-bootstrap runtime maintenance ports are required")
        status_owner = getattr(coordinator_status, "__self__", None)
        lease_owner = getattr(runtime_maintenance_lease, "__self__", None)
        if status_owner is None or status_owner is not lease_owner:
            raise TypeError(
                "coordinator status and maintenance lease must be bound to the same instance"
            )
        self._coordinator_port = status_owner
        self._coordinator_status = coordinator_status
        self._runtime_maintenance_lease = runtime_maintenance_lease
        self._repair_port = repair_under_maintenance
        self._bootstrap_port = bootstrap_under_maintenance
        self._recovery_port = recovery_under_existing_maintenance
        self._postflight_port = postflight_under_maintenance
        self._rollback_port = rollback_under_maintenance
        self._config = config or PrebootstrapRuntimeMaintenanceAdapterConfigV1()
        self._active_bridge_permit: PrebootstrapMaintenancePermitAdapterV1 | None = None
        self._active_raw_permit: Any = None
        self._phase = "IDLE"

    def __repr__(self) -> str:
        return "<PrebootstrapRuntimeMaintenanceAdapterContractV1 protected>"

    def snapshot(self) -> dict[str, Any]:
        enabled = bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1
        )
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_CONTRACT_V1_VERSION,
            "enabled": enabled,
            "default_off": not enabled,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "active_lease": self._active_bridge_permit is not None,
            "phase": self._phase,
            **_SAFE_RESULT_FLAGS,
        }

    def _require_enabled(self) -> None:
        if self._config.enabled is not True:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_ADAPTER_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_ADAPTER_SCOPE_REQUIRED"
            )

    def _coordinator_safe(self, status: Any) -> bool:
        return bool(
            isinstance(status, Mapping)
            and all(status.get(key) is True for key in _REQUIRED_COORDINATOR_TRUE)
            and status.get("registered_writer_count") == 19
            and status.get("inflight_mutations") == 0
            and status.get("writer_mutations_allowed") is False
            and status.get("runtime_activation_allowed") is False
            and status.get("startup_recovery_verified") is False
            and status.get("coordination_ready") is False
        )

    @staticmethod
    def _runtime_permit_safe(permit: Any) -> bool:
        return bool(
            _permit_value(permit, "state") == "QUIESCED"
            and _permit_value(permit, "registered_writer_count") == 19
            and _permit_value(permit, "inflight_mutations") == 0
            and _permit_value(permit, "shared_lock_acquired") is True
            and _valid_sha256(_permit_value(permit, "maintenance_epoch"))
            and _valid_sha256(_permit_value(permit, "lock_namespace_sha256"))
        )

    def _require_active(
        self,
        permit: Any,
        *,
        allowed_phases: tuple[str, ...],
    ) -> Any:
        if (
            permit is not self._active_bridge_permit
            or self._active_raw_permit is None
        ):
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_PERMIT_IDENTITY_MISMATCH"
            )
        if self._phase not in allowed_phases:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_PHASE_ORDER_INVALID"
            )
        return self._active_raw_permit

    @staticmethod
    def _with_bridge_attestation(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_PORT_RESULT_INVALID"
            )
        result = _canonical_copy(dict(value))
        result["same_maintenance_permit"] = True
        return result

    @contextmanager
    def maintenance_lease(self) -> Iterator[PrebootstrapMaintenancePermitAdapterV1]:
        self._require_enabled()
        if self._active_bridge_permit is not None:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_NESTED_LEASE_FORBIDDEN"
            )
        try:
            coordinator = self._coordinator_status()
        except Exception as exc:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_COORDINATOR_STATUS_FAILED"
            ) from exc
        if not self._coordinator_safe(coordinator):
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_MAINTENANCE_COORDINATOR_UNSAFE"
            )
        try:
            context = self._runtime_maintenance_lease()
        except Exception as exc:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_MAINTENANCE_LEASE_FAILED"
            ) from exc
        if context is None:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_MAINTENANCE_LEASE_UNAVAILABLE"
            )
        with context as raw_permit:
            if not self._runtime_permit_safe(raw_permit):
                raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                    "PREBOOTSTRAP_RUNTIME_MAINTENANCE_PERMIT_INVALID"
                )
            epoch = _valid_sha256(_permit_value(raw_permit, "maintenance_epoch"))
            namespace = _valid_sha256(
                _permit_value(raw_permit, "lock_namespace_sha256")
            )
            binding = _stable_sha256(
                {
                    "maintenance_epoch": epoch,
                    "lock_namespace_sha256": namespace,
                    "registered_writer_count": 19,
                    "maintenance_only": True,
                    "runtime_activation_allowed": False,
                }
            )
            bridge_permit = PrebootstrapMaintenancePermitAdapterV1(
                state="QUIESCED",
                registered_writer_count=19,
                inflight_mutations=0,
                shared_lock_acquired=True,
                maintenance_only=True,
                writer_mutations_allowed=False,
                runtime_activation_allowed=False,
                maintenance_epoch=epoch,
                lock_namespace_sha256=namespace,
                permit_binding_sha256=binding,
            )
            self._active_raw_permit = raw_permit
            self._active_bridge_permit = bridge_permit
            self._phase = "LEASED"
            try:
                yield bridge_permit
            finally:
                self._active_bridge_permit = None
                self._active_raw_permit = None
                self._phase = "IDLE"

    def repair(
        self, preview: Mapping[str, Any], permit: Any
    ) -> dict[str, Any]:
        raw = self._require_active(permit, allowed_phases=("LEASED",))
        if not isinstance(preview, Mapping) or preview.get("apply_allowed") is not False:
            raise PrebootstrapRuntimeMaintenanceAdapterBlocked(
                "PREBOOTSTRAP_RUNTIME_PREVIEW_MUST_REMAIN_NON_APPLICABLE"
            )
        value = self._with_bridge_attestation(self._repair_port(preview, raw))
        if value.get("simulated_registry_write") is True:
            self._phase = "REPAIR_DIRTY"
        if bool(
            _safe_port_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_CLOSED_REPAIR_APPLIED"
            and value.get("simulated_registry_write") is True
        ):
            self._phase = "REPAIRED"
        return value

    def bootstrap(
        self, repair_result: Mapping[str, Any], permit: Any
    ) -> dict[str, Any]:
        raw = self._require_active(permit, allowed_phases=("REPAIRED",))
        value = self._with_bridge_attestation(
            self._bootstrap_port(repair_result, raw)
        )
        if bool(
            _safe_port_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_BOOTSTRAP_COMPLETED"
        ):
            self._phase = "BOOTSTRAPPED"
        return value

    def startup_recovery(
        self, bootstrap_result: Mapping[str, Any], permit: Any
    ) -> dict[str, Any]:
        raw = self._require_active(permit, allowed_phases=("BOOTSTRAPPED",))
        value = self._with_bridge_attestation(
            self._recovery_port(bootstrap_result, raw)
        )
        if bool(
            _safe_port_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_STARTUP_RECOVERY_COMPLETED"
            and value.get("maintenance_epoch")
            == _permit_value(raw, "maintenance_epoch")
            and value.get("lock_namespace_sha256")
            == _permit_value(raw, "lock_namespace_sha256")
        ):
            self._phase = "RECOVERED"
        return value

    def postflight(
        self, recovery_result: Mapping[str, Any], permit: Any
    ) -> dict[str, Any]:
        raw = self._require_active(permit, allowed_phases=("RECOVERED",))
        value = self._with_bridge_attestation(
            self._postflight_port(recovery_result, raw)
        )
        if bool(
            _safe_port_result(value)
            and value.get("ok") is True
            and value.get("status") == "SYNTHETIC_READINESS_PROJECTED"
            and value.get("runtime_integrated") is False
            and value.get("production_ready") is False
            and value.get("live_allowed") is False
        ):
            self._phase = "COMPLETE"
        return value

    def rollback(
        self, repair_result: Mapping[str, Any], permit: Any
    ) -> dict[str, Any]:
        raw = self._require_active(
            permit,
            allowed_phases=(
                "REPAIR_DIRTY",
                "REPAIRED",
                "BOOTSTRAPPED",
                "RECOVERED",
            ),
        )
        value = self._with_bridge_attestation(
            self._rollback_port(repair_result, raw)
        )
        if bool(
            _safe_port_result(value)
            and value.get("ok") is True
            and value.get("status")
            == "SYNTHETIC_PREBOOTSTRAP_ROLLBACK_VERIFIED"
            and value.get("source_restored") is True
        ):
            self._phase = "ROLLED_BACK"
        return value


__all__ = [
    "PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1",
    "PrebootstrapMaintenancePermitAdapterV1",
    "PrebootstrapRuntimeMaintenanceAdapterBlocked",
    "PrebootstrapRuntimeMaintenanceAdapterConfigV1",
    "PrebootstrapRuntimeMaintenanceAdapterContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_CONTRACT_V1_VERSION",
]
