"""Offline physical-binding adapter for the pre-bootstrap C3 coordinator.

The adapter binds one coordinator to the exact lock backend and lease store
instances used to construct it.  It exposes the three-method port consumed by
the maintenance-only entrypoint, while remaining default-off and synthetic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-PHYSICAL-COORDINATOR-PORT-ADAPTER-CONTRACT-V1"
)
PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_DRIVE_ROOT_RE = re.compile(r"^[a-zA-Z]:[\\/]*$")


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


def _safe_storage_root_identity(root: Any) -> str:
    value = str(root or "").strip()
    if not value or value in {"/", "\\"} or _DRIVE_ROOT_RE.fullmatch(value):
        raise ValueError("storage root identity must be explicit and non-root")
    return value


def prebootstrap_physical_storage_root_binding_sha256_v1(
    storage_root: Any,
    *,
    lock_namespace_sha256: str,
) -> str:
    root = _safe_storage_root_identity(storage_root)
    namespace = _valid_sha256(lock_namespace_sha256)
    if not namespace:
        raise ValueError("lock namespace must be a lowercase SHA-256")
    return _stable_sha256(
        {
            "binding_version": "C3_PREBOOTSTRAP_PHYSICAL_COORDINATOR_STORAGE_ROOT_BINDING_V1",
            "storage_root_identity": root,
            "lock_namespace_sha256": namespace,
        }
    )


class PrebootstrapPhysicalCoordinatorPortAdapterBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "PREBOOTSTRAP_PHYSICAL_COORDINATOR_ADAPTER_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class PrebootstrapPhysicalCoordinatorPortAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_storage_root_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_lock_namespace_sha256: str | None = field(default=None, repr=False)


class PrebootstrapPhysicalCoordinatorPortAdapterContractV1:
    """Expose a hash-bound coordinator/storage port without runtime wiring."""

    def __init__(
        self,
        *,
        coordinator: Any,
        lock_backend: Any,
        maintenance_lease_store: Any,
        config: PrebootstrapPhysicalCoordinatorPortAdapterConfigV1 | None = None,
    ) -> None:
        if coordinator is None or not all(
            callable(getattr(coordinator, name, None))
            for name in ("snapshot", "maintenance_lease")
        ):
            raise TypeError("coordinator snapshot and maintenance_lease are required")
        if lock_backend is None or maintenance_lease_store is None:
            raise TypeError("lock backend and maintenance lease store are required")
        self._coordinator = coordinator
        self._lock_backend = lock_backend
        self._maintenance_lease_store = maintenance_lease_store
        self._config = config or PrebootstrapPhysicalCoordinatorPortAdapterConfigV1()

    def __repr__(self) -> str:
        return "<PrebootstrapPhysicalCoordinatorPortAdapterContractV1 protected>"

    def _enabled(self) -> bool:
        return bool(
            self._config.enabled is True
            and self._config.scope_attestation
            == PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_SCOPE_ATTESTATION_V1
        )

    def _require_enabled(self) -> None:
        if self._config.enabled is not True:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_ADAPTER_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_ADAPTER_SCOPE_REQUIRED"
            )

    def _binding(self) -> tuple[dict[str, Any], str, str]:
        self._require_enabled()
        if (
            getattr(self._coordinator, "_lock_backend", None)
            is not self._lock_backend
            or getattr(self._coordinator, "_lease_store", None)
            is not self._maintenance_lease_store
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_DEPENDENCY_IDENTITY_MISMATCH"
            )
        if (
            getattr(self._coordinator, "enabled", None) is not True
            or getattr(self._lock_backend, "enabled", None) is not True
            or getattr(self._maintenance_lease_store, "enabled", None) is not True
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_DEPENDENCY_DEFAULT_OFF"
            )
        lock_root = getattr(self._lock_backend, "storage_root", None)
        lease_root = getattr(self._maintenance_lease_store, "storage_root", None)
        if lock_root is None or lease_root is None or lock_root != lease_root:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_STORAGE_ROOT_MISMATCH"
            )
        namespace = _valid_sha256(
            getattr(self._coordinator, "lock_namespace", None)
        )
        expected_namespace = _valid_sha256(
            self._config.expected_lock_namespace_sha256
        )
        if not namespace or not expected_namespace or not hmac.compare_digest(
            namespace, expected_namespace
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_NAMESPACE_MISMATCH"
            )
        try:
            actual_root_binding = (
                prebootstrap_physical_storage_root_binding_sha256_v1(
                    lock_root,
                    lock_namespace_sha256=namespace,
                )
            )
        except (TypeError, ValueError) as exc:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_STORAGE_ROOT_INVALID"
            ) from exc
        supplied_root_binding = _valid_sha256(
            self._config.expected_storage_root_binding_sha256
        )
        if not supplied_root_binding or not hmac.compare_digest(
            supplied_root_binding, actual_root_binding
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_STORAGE_ROOT_BINDING_MISMATCH"
            )
        try:
            snapshot = self._coordinator.snapshot()
        except Exception as exc:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_SNAPSHOT_FAILED"
            ) from exc
        if not bool(
            isinstance(snapshot, Mapping)
            and snapshot.get("enabled") is True
            and snapshot.get("registered_writer_count") == 19
            and snapshot.get("all_writers_registered") is True
            and snapshot.get("inflight_mutations") == 0
            and snapshot.get("lock_namespace_sha256") == namespace
            and snapshot.get("runtime_integrated") is False
            and snapshot.get("real_registry_accessed") is False
            and snapshot.get("broker_called") is False
            and snapshot.get("no_order_sent") is True
        ):
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_SNAPSHOT_UNSAFE"
            )
        return dict(snapshot), namespace, actual_root_binding

    def snapshot(self) -> dict[str, Any]:
        if not self._enabled():
            return {
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_CONTRACT_V1_VERSION,
                "enabled": False,
                "default_off": True,
                "registered_writer_count": 0,
                "all_writers_registered": False,
                "inflight_mutations": 0,
                "maintenance_lease_state": None,
                "lock_namespace_sha256": None,
                "runtime_integrated": False,
                "real_registry_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
            }
        snapshot, _namespace, _binding = self._binding()
        return snapshot

    def storage_readiness(self) -> dict[str, Any]:
        _snapshot, namespace, root_binding = self._binding()
        return {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_PHYSICAL_COORDINATOR_STORAGE_READY",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_CONTRACT_V1_VERSION,
            "shared_lock_backend_ready": True,
            "maintenance_lease_store_ready": True,
            "same_storage_root_verified": True,
            "coordinator_dependency_identity_verified": True,
            "lock_namespace_sha256": namespace,
            "storage_root_binding_sha256": root_binding,
            "synthetic_only": True,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def maintenance_lease(self) -> AbstractContextManager[Any]:
        self._binding()
        try:
            context = self._coordinator.maintenance_lease()
        except Exception as exc:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_LEASE_FAILED"
            ) from exc
        if context is None:
            raise PrebootstrapPhysicalCoordinatorPortAdapterBlocked(
                "PREBOOTSTRAP_PHYSICAL_COORDINATOR_LEASE_UNAVAILABLE"
            )
        return context


__all__ = [
    "PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_SCOPE_ATTESTATION_V1",
    "PrebootstrapPhysicalCoordinatorPortAdapterBlocked",
    "PrebootstrapPhysicalCoordinatorPortAdapterConfigV1",
    "PrebootstrapPhysicalCoordinatorPortAdapterContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_CONTRACT_V1_VERSION",
    "prebootstrap_physical_storage_root_binding_sha256_v1",
]
