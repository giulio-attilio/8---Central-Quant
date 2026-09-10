"""Dormant offline contract for a C3 pre-bootstrap maintenance-only entrypoint.

The entrypoint exposes only status and one exclusive maintenance lease.  Normal
writer admission and runtime activation are unconditionally denied.  All
capabilities are injected; this module has no filesystem, network, broker or
application-runtime binding.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-MAINTENANCE-ONLY-COORDINATOR-ENTRYPOINT-CONTRACT-V1"
)
PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_CONTROL_VECTOR = {
    "enable_real_trading": False,
    "broker_dry_run": True,
    "falcon_mode": "VERIFY",
    "central_real_execution_enabled": False,
    "central_real_pilot_enabled": False,
    "live_trading_enabled": False,
    "order_submission_authorized": False,
}
_NO_SIDE_EFFECT_FLAGS = {
    "synthetic_only": True,
    "real_registry_accessed": False,
    "write_executed": False,
    "registry_write": False,
    "network_accessed": False,
    "broker_called": False,
    "no_order_sent": True,
}


def _value(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


class PrebootstrapMaintenanceOnlyCoordinatorBlocked(RuntimeError):
    """Sanitized fail-closed error for the maintenance-only boundary."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_MAINTENANCE_ONLY_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapMaintenanceOnlyCoordinatorConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


class PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1:
    """Permit maintenance while keeping all writer/runtime paths denied."""

    def __init__(
        self,
        *,
        coordinator: Any,
        trading_controls: Callable[[], Mapping[str, Any]],
        config: PrebootstrapMaintenanceOnlyCoordinatorConfigV1 | None = None,
    ) -> None:
        required = ("snapshot", "storage_readiness", "maintenance_lease")
        if coordinator is None or not all(
            callable(getattr(coordinator, name, None)) for name in required
        ):
            raise TypeError(
                "one coordinator instance with snapshot, storage_readiness and maintenance_lease is required"
            )
        if not callable(trading_controls):
            raise TypeError("trading_controls is required")
        self._coordinator = coordinator
        self._trading_controls = trading_controls
        self._config = config or PrebootstrapMaintenanceOnlyCoordinatorConfigV1()
        self._active_raw_permit: Any = None
        self._last_release_verified = False

    def __repr__(self) -> str:
        return "<PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1 protected>"

    def _enabled(self) -> bool:
        return bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1
        )

    def snapshot(self) -> dict[str, Any]:
        enabled = self._enabled()
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_CONTRACT_V1_VERSION,
            "enabled": enabled,
            "default_off": not enabled,
            "maintenance_only": True,
            "writer_mutations_allowed": False,
            "runtime_activation_allowed": False,
            "coordination_ready": False,
            "startup_recovery_verified": False,
            "active_maintenance_lease": self._active_raw_permit is not None,
            "last_release_verified": self._last_release_verified,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            **_NO_SIDE_EFFECT_FLAGS,
        }

    def _require_enabled(self) -> None:
        if self._config.enabled is not True:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_SCOPE_REQUIRED"
            )

    @staticmethod
    def _coordinator_snapshot_safe(snapshot: Any) -> bool:
        return bool(
            isinstance(snapshot, Mapping)
            and snapshot.get("enabled") is True
            and snapshot.get("registered_writer_count") == 19
            and snapshot.get("all_writers_registered") is True
            and snapshot.get("inflight_mutations") == 0
            and snapshot.get("maintenance_lease_state") in (None, "RELEASED")
            and _valid_sha256(snapshot.get("lock_namespace_sha256"))
            and snapshot.get("runtime_integrated") is False
            and snapshot.get("real_registry_accessed") is False
            and snapshot.get("broker_called") is False
            and snapshot.get("no_order_sent") is True
        )

    @staticmethod
    def _storage_ready(storage: Any, namespace: str) -> bool:
        return bool(
            isinstance(storage, Mapping)
            and storage.get("shared_lock_backend_ready") is True
            and storage.get("maintenance_lease_store_ready") is True
            and storage.get("lock_namespace_sha256") == namespace
            and storage.get("synthetic_only") is True
            and storage.get("runtime_integrated") is False
            and storage.get("real_registry_accessed") is False
            and storage.get("network_accessed") is False
            and storage.get("broker_called") is False
            and storage.get("no_order_sent") is True
        )

    def coordination_status(self) -> dict[str, Any]:
        self._require_enabled()
        try:
            controls = self._trading_controls()
            snapshot = self._coordinator.snapshot()
            storage = self._coordinator.storage_readiness()
        except Exception as exc:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_EVIDENCE_COLLECTION_FAILED"
            ) from exc
        if not isinstance(controls, Mapping) or dict(controls) != _SAFE_CONTROL_VECTOR:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_TRADING_CONTROLS_UNSAFE"
            )
        if not self._coordinator_snapshot_safe(snapshot):
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_UNSAFE"
            )
        namespace = _valid_sha256(snapshot.get("lock_namespace_sha256"))
        if not self._storage_ready(storage, namespace):
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_STORAGE_UNSAFE"
            )
        return {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_MAINTENANCE_ONLY_READY",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_CONTRACT_V1_VERSION,
            "enabled": True,
            "maintenance_entrypoint_enabled": True,
            "maintenance_only": True,
            "coordination_ready": False,
            "registered_writer_count": 19,
            "all_writers_registered": True,
            "inflight_mutations": 0,
            "shared_lock_backend_ready": True,
            "maintenance_lease_store_ready": True,
            "writer_mutations_allowed": False,
            "runtime_activation_allowed": False,
            "startup_recovery_verified": False,
            "trading_controls_safe": True,
            "lock_namespace_sha256": namespace,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            **_NO_SIDE_EFFECT_FLAGS,
        }

    @staticmethod
    def _permit_safe(permit: Any, namespace: str) -> bool:
        return bool(
            _value(permit, "state") == "QUIESCED"
            and _value(permit, "registered_writer_count") == 19
            and _value(permit, "inflight_mutations") == 0
            and _value(permit, "shared_lock_acquired") is True
            and _valid_sha256(_value(permit, "maintenance_epoch"))
            and _value(permit, "lock_namespace_sha256") == namespace
        )

    @contextmanager
    def maintenance_lease(self) -> Iterator[Any]:
        self._require_enabled()
        if self._active_raw_permit is not None:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_NESTED_LEASE_FORBIDDEN"
            )
        status = self.coordination_status()
        namespace = status["lock_namespace_sha256"]
        self._last_release_verified = False
        try:
            context: AbstractContextManager[Any] = (
                self._coordinator.maintenance_lease()
            )
            if context is None:
                raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                    "PREBOOTSTRAP_MAINTENANCE_ONLY_LEASE_UNAVAILABLE"
                )
            with context as permit:
                if not self._permit_safe(permit, namespace):
                    raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                        "PREBOOTSTRAP_MAINTENANCE_ONLY_PERMIT_INVALID"
                    )
                self._active_raw_permit = permit
                try:
                    yield permit
                finally:
                    self._active_raw_permit = None
        except PrebootstrapMaintenanceOnlyCoordinatorBlocked:
            raise
        except Exception as exc:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_LEASE_FAILED_CLOSED"
            ) from exc
        try:
            released = self._coordinator.snapshot()
        except Exception as exc:
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_RELEASE_UNVERIFIED"
            ) from exc
        if not bool(
            isinstance(released, Mapping)
            and released.get("maintenance_lease_state") == "RELEASED"
            and released.get("inflight_mutations") == 0
            and released.get("lock_namespace_sha256") == namespace
        ):
            raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
                "PREBOOTSTRAP_MAINTENANCE_ONLY_RELEASE_UNVERIFIED"
            )
        self._last_release_verified = True

    @contextmanager
    def writer_mutation(self, _writer_id: str) -> Iterator[Any]:
        raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
            "PREBOOTSTRAP_MAINTENANCE_ONLY_WRITER_MUTATIONS_FORBIDDEN"
        )
        yield None

    def request_runtime_activation(self) -> None:
        raise PrebootstrapMaintenanceOnlyCoordinatorBlocked(
            "PREBOOTSTRAP_MAINTENANCE_ONLY_RUNTIME_ACTIVATION_FORBIDDEN"
        )


__all__ = [
    "PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1",
    "PrebootstrapMaintenanceOnlyCoordinatorBlocked",
    "PrebootstrapMaintenanceOnlyCoordinatorConfigV1",
    "PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_CONTRACT_V1_VERSION",
]
