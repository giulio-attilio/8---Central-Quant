"""Inspect a temporary C3 lock graph without running recovery or installing it.

This is a local structural check, not a physical lock acquisition or a
production recovery port.  It never reads Registry/WAL contents and cannot
authorize startup, trading, or LIVE.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as wal_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as ledger_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as collection_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


def inspect_c3_physical_lock_graph_offline_v1(
    *,
    enabled: bool = False,
    coordinator: Any = None,
    wal_backend: Any = None,
    resolved_ledger: Any = None,
    observation_lease: Any = None,
    aggregate_collector: Any = None,
    multistore_recovery: Any = None,
    startup_bridge: Any = None,
    authority_boundary: Any = None,
) -> dict[str, Any]:
    """Fail closed unless exact temporary objects form one pinned lock graph.

    The live maintenance lease, the 19 writer call sites, and the recovery
    ports are deliberately *not* exercised here.  A positive structural
    result must never be treated as a production readiness receipt.
    """

    result = {
        "ok": False,
        "status": "C3_PHYSICAL_LOCK_GRAPH_OFFLINE_BLOCKED",
        "reason": "C3_PHYSICAL_LOCK_GRAPH_DEFAULT_OFF",
        "structural_binding_verified": False,
        "synthetic_registry_lock_lease_colocated": False,
        "physical_lock_acquired": False,
        "writer_runtime_lock_verified": False,
        "store_recovery_ports_verified": False,
        "registry_or_wal_contents_read": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "synthetic_only": True,
        "temporary_storage_only": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }
    if type(enabled) is not bool:
        result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_ENABLE_INVALID"
        return result
    if not enabled:
        return result
    if not (
        type(coordinator) is coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1
        and type(wal_backend) is wal_v2.TemporaryPhysicalDurableRawTransactionBackendV2
        and type(resolved_ledger) is ledger_v2.DormantDurableReconciliationAuthorityLedgerV2
        and type(observation_lease) is observation_v2.PhysicalMultiStoreObservationLeaseV2
        and type(aggregate_collector) is collection_v2.PhysicalLockedAggregateCollectionV2
        and type(multistore_recovery) is multistore_v2.CoordinatedMultistoreStartupRecoveryV2
        and type(startup_bridge) is bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2
        and type(authority_boundary) is boundary_v2.AuthenticatedPersistentAuthorityBoundaryV2
    ):
        result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_EXACT_TYPES_REQUIRED"
        return result
    try:
        lock_backend = coordinator._lock_backend
        lease_store = coordinator._lease_store
        if not (
            coordinator.enabled is True
            and coordinator.maintenance_only is True
            and coordinator.all_writers_registered is True
            and coordinator.registered_writer_count == 19
            and wal_backend._enabled is True
            and type(lock_backend) is storage_v1.CrossPlatformInterprocessFileLockBackendV1
            and type(lease_store) is storage_v1.DurableJsonMaintenanceLeaseStoreV1
            and lock_backend.enabled is True
            and lease_store.enabled is True
        ):
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_TEMPORARY_MAINTENANCE_REQUIRED"
            return result
        if not (
            wal_backend._lock_backend is lock_backend
            and multistore_recovery._lock_backend is lock_backend
            and multistore_recovery._maintenance_coordinator is coordinator
            and startup_bridge._lock_backend is lock_backend
            and startup_bridge._maintenance_coordinator is coordinator
            and lock_backend.storage_root == lease_store.storage_root
            and coordinator.lock_namespace == wal_backend._lock_namespace()
            and getattr(multistore_recovery._transaction_recovery, "recovery_lock_backend", None) is lock_backend
            and getattr(multistore_recovery._resolved_recovery, "recovery_lock_backend", None) is lock_backend
            and getattr(multistore_recovery._transaction_recovery, "recovery_lock_namespace_sha256", None)
            == multistore_recovery._config.transaction_lock_namespace_sha256
            and getattr(multistore_recovery._resolved_recovery, "recovery_lock_namespace_sha256", None)
            == multistore_recovery._config.resolved_lock_namespace_sha256
        ):
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_WRITER_WAL_DOMAIN_MISMATCH"
            return result
        if not (
            observation_lease._backend is wal_backend
            and observation_lease._ledger is resolved_ledger
            and aggregate_collector._lease is observation_lease
            and aggregate_collector._backend is wal_backend
            and aggregate_collector._ledger is resolved_ledger
            and getattr(startup_bridge._physical_store, "_ledger", None) is resolved_ledger
            and authority_boundary._multistore_recovery is multistore_recovery
            and authority_boundary._startup_bridge is startup_bridge
            and authority_boundary._locked_physical_aggregate_collector is aggregate_collector
        ):
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_STORE_INSTANCE_MISMATCH"
            return result
        registry_store = wal_backend._store
        wal_root = Path(wal_backend._root).resolve(strict=True)
        lock_root = lock_backend.storage_root.resolve(strict=True)
        lease_root = lease_store.storage_root.resolve(strict=True)
        registry_path = registry_store.target_path
        if not (
            registry_store.enabled is True
            and registry_store.storage_root == wal_root
            and registry_path.is_file()
            and not registry_path.is_symlink()
            and registry_path.resolve(strict=True).parent == wal_root
            and lock_root == lease_root
            and lock_root.parent == wal_root
            and len({
                wal_root.stat().st_dev,
                lock_root.stat().st_dev,
                registry_path.stat().st_dev,
            }) == 1
        ):
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_SYNTHETIC_REGISTRY_DOMAIN_MISMATCH"
            return result
        result["synthetic_registry_lock_lease_colocated"] = True
        if not (
            multistore_recovery.coordinated_bridge_bound_v2(startup_bridge) is True
            and authority_boundary._config.require_locked_physical_aggregate is True
            and authority_boundary._config.expected_locked_physical_aggregate_collector_object_identity_sha256
            == boundary_v2._object_identity(aggregate_collector)
        ):
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_BOUNDARY_REQUIREMENT_MISSING"
            return result
        # Reuse the existing offline validators: they check exact identity pins
        # and that RESOLVED storage paths remain beneath the temporary WAL root.
        if observation_lease._config_reason() is not None or observation_lease._dependencies_reason() is not None:
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_OBSERVATION_LEASE_INVALID"
            return result
        if aggregate_collector._reason() is not None:
            result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_COLLECTOR_INVALID"
            return result
    except Exception:
        result["reason"] = "C3_PHYSICAL_LOCK_GRAPH_INSPECTION_FAILED"
        return result
    result.update(
        ok=True,
        status="C3_PHYSICAL_LOCK_GRAPH_OFFLINE_STRUCTURALLY_BOUND",
        reason=None,
        structural_binding_verified=True,
    )
    return result


__all__ = ["inspect_c3_physical_lock_graph_offline_v1"]
