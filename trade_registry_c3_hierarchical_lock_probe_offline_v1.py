"""Synthetic-only proof of outer writer/maintenance and inner store locks.

This module is not installed in the runtime.  It accepts only a temporary WAL
backend, acquires only temporary OS file locks, and never grants production or
LIVE authority.  It reuses the existing two-store observation lease/collector.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as wal_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as ledger_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as collection_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


def _lock_is_available(
    backend: storage_v1.CrossPlatformInterprocessFileLockBackendV1,
    namespace: str,
) -> bool:
    handle = backend.acquire(namespace, 0.01)
    if handle is None:
        return False
    try:
        return True
    finally:
        handle.release()


def probe_c3_hierarchical_locks_offline_v1(
    *,
    enabled: bool = False,
    coordinator: Any = None,
    wal_backend: Any = None,
    resolved_ledger: Any = None,
    observation_lease: Any = None,
    aggregate_collector: Any = None,
) -> dict[str, Any]:
    """Exercise one temporary outer lock, then WAL -> RESOLVED inner locks.

    A positive result proves bounded local file-lock behavior for these exact
    objects, not cross-process runtime wiring, crash safety, or readiness.
    """
    result: dict[str, Any] = {
        "ok": False,
        "status": "C3_HIERARCHICAL_LOCK_PROBE_BLOCKED",
        "reason": "C3_HIERARCHICAL_LOCK_PROBE_DEFAULT_OFF",
        "writer_lock_probes_verified": 0,
        "maintenance_lock_verified": False,
        "inner_lock_order_verified": False,
        "inner_contention_verified": False,
        "aggregate_collection_verified": False,
        "all_locks_released": False,
        "cross_process_verified": False,
        "runtime_writers_verified": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }
    if type(enabled) is not bool:
        result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_ENABLE_INVALID"
        return result
    if not enabled:
        return result
    if not (
        type(coordinator) is coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1
        and type(wal_backend) is wal_v2.TemporaryPhysicalDurableRawTransactionBackendV2
        and type(resolved_ledger) is ledger_v2.DormantDurableReconciliationAuthorityLedgerV2
        and type(observation_lease) is observation_v2.PhysicalMultiStoreObservationLeaseV2
        and type(aggregate_collector) is collection_v2.PhysicalLockedAggregateCollectionV2
    ):
        result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_EXACT_TYPES_REQUIRED"
        return result
    try:
        outer = coordinator._lock_backend
        wal_lock = wal_backend._lock_backend
        ledger_lock = resolved_ledger._lock_backend
        lease_store = coordinator._lease_store
        if not (
            type(outer) is storage_v1.CrossPlatformInterprocessFileLockBackendV1
            and type(wal_lock) is storage_v1.CrossPlatformInterprocessFileLockBackendV1
            and type(ledger_lock) is storage_v1.CrossPlatformInterprocessFileLockBackendV1
            and type(lease_store) is storage_v1.DurableJsonMaintenanceLeaseStoreV1
            and outer.enabled is True
            and wal_lock.enabled is True
            and ledger_lock.enabled is True
            and lease_store.enabled is True
            and coordinator.enabled is True
            and coordinator.maintenance_only is False
            and coordinator.all_writers_registered is True
            and coordinator.registered_writer_count == 19
            and coordinator.lock_namespace == coordinator_v1.canonical_runtime_lock_namespace_v1()
            and wal_backend._enabled is True
            and resolved_ledger._config.enabled is True
        ):
            result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_TEMPORARY_WRITERS_REQUIRED"
            return result
        wal_root = Path(wal_backend._root).resolve(strict=False)
        temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
        lock_roots = tuple(item.storage_root.resolve(strict=False) for item in (outer, wal_lock, ledger_lock))
        if not (
            wal_root.is_relative_to(temp_root)
            and wal_root.name.startswith("c3_durable_backend_v2_")
            and all(root.parent == wal_root for root in lock_roots)
            and len(set(lock_roots)) == 3
        ):
            result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_LOCK_DOMAINS_NOT_DISTINCT"
            return result
        if not (
            lease_store.storage_root == outer.storage_root
            and observation_lease._backend is wal_backend
            and observation_lease._ledger is resolved_ledger
            and aggregate_collector._lease is observation_lease
            and aggregate_collector._backend is wal_backend
            and aggregate_collector._ledger is resolved_ledger
            and observation_lease._config_reason() is None
            and observation_lease._dependencies_reason() is None
            and aggregate_collector._reason() is None
        ):
            result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_BINDING_INVALID"
            return result
        specs = observation_lease._specs()
        if not (
            len(specs) == 2
            and specs[0][0] is wal_lock
            and specs[0][1] == wal_backend._lock_namespace()
            and specs[1][0] is ledger_lock
            and specs[1][1] == observation_lease._config.expected_resolved_ledger_storage_binding_sha256
        ):
            result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_INNER_ORDER_INVALID"
            return result
    except Exception:
        result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_VALIDATION_FAILED"
        return result

    try:
        outer_competitor = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            outer.storage_root, enabled=True,
        )
        wal_competitor = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            wal_lock.storage_root, enabled=True,
        )
        ledger_competitor = storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            ledger_lock.storage_root, enabled=True,
        )
        for writer in coordinator_v1.canonical_runtime_writer_inventory_v1():
            with coordinator.mutation(writer["writer_id"]) as permit:
                if not (
                    permit.coordinated is True
                    and permit.shared_lock_acquired is True
                    and not _lock_is_available(outer_competitor, coordinator.lock_namespace)
                ):
                    result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_WRITER_LOCK_NOT_HELD"
                    return result
                result["writer_lock_probes_verified"] += 1
        with coordinator.maintenance_lease() as permit:
            if not (
                coordinator.maintenance_permit_is_current_v1(
                    asdict(permit), lock_backend=outer,
                )
                and not _lock_is_available(outer_competitor, coordinator.lock_namespace)
            ):
                result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_MAINTENANCE_LOCK_NOT_HELD"
                return result
            result["maintenance_lock_verified"] = True
            if not wal_backend.mark_lock_probe_offline():
                result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_WAL_INNER_LOCK_UNAVAILABLE"
                return result
            with observation_lease.hold_offline(
                expires_at_epoch=observation_lease._clock() + 60,
            ) as token:
                if not observation_lease.validate_live(
                    token, backend=wal_backend,
                    durable_authority_ledger=resolved_ledger,
                    now_epoch=observation_lease._clock(),
                ):
                    result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_INNER_LEASE_NOT_LIVE"
                    return result
                if (
                    _lock_is_available(wal_competitor, specs[0][1])
                    or _lock_is_available(ledger_competitor, specs[1][1])
                ):
                    result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_INNER_LOCK_NOT_HELD"
                    return result
                result["inner_contention_verified"] = True
            if not (
                _lock_is_available(wal_competitor, specs[0][1])
                and _lock_is_available(ledger_competitor, specs[1][1])
            ):
                result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_INNER_LOCK_NOT_RELEASED"
                return result
            collected = aggregate_collector.collect_offline()
            if not (
                collected.get("ok") is True
                and collection_v2.physical_locked_aggregate_collection_receipt_valid_v2(
                    collected.get("collection_receipt")
                )
                and collected.get("lease_revalidation_count") == 8
                and collected.get("lease_released_after_collection") is True
                and observation_lease.snapshot()["held_lock_count"] == 0
                and coordinator.maintenance_permit_is_current_v1(
                    asdict(permit), lock_backend=outer,
                )
                and not _lock_is_available(outer_competitor, coordinator.lock_namespace)
            ):
                result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_AGGREGATE_FAILED"
                return result
            result["aggregate_collection_verified"] = True
        result["all_locks_released"] = bool(
            _lock_is_available(outer_competitor, coordinator.lock_namespace)
            and _lock_is_available(wal_competitor, specs[0][1])
            and _lock_is_available(ledger_competitor, specs[1][1])
            and observation_lease.snapshot()["held_lock_count"] == 0
        )
        if not result["all_locks_released"]:
            result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_LOCK_NOT_RELEASED"
            return result
    except Exception:
        result["reason"] = "C3_HIERARCHICAL_LOCK_PROBE_PHYSICAL_CHECK_FAILED"
        return result
    result.update(
        ok=True,
        status="C3_HIERARCHICAL_LOCK_PROBE_VERIFIED_OFFLINE",
        reason=None,
        inner_lock_order_verified=True,
    )
    return result


__all__ = ["probe_c3_hierarchical_locks_offline_v1"]
