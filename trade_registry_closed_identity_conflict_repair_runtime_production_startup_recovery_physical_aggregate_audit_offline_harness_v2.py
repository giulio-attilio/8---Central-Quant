"""Synthetic harness for the temporary physical aggregate audit V2."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_v2 as contract_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_AGGREGATE_AUDIT_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-AGGREGATE-AUDIT-"
    "OFFLINE-HARNESS-V2"
)


def make_physical_aggregate_audit_v2(
) -> contract_v2.DormantPhysicalAggregateRecoveryAuditV2:
    return contract_v2.DormantPhysicalAggregateRecoveryAuditV2(
        contract_v2.PhysicalAggregateRecoveryAuditConfigV2(
            enabled=True,
            scope_attestation=(
                contract_v2.OFFLINE_PHYSICAL_AGGREGATE_AUDIT_SCOPE_ATTESTATION_V2
            ),
        )
    )


def collect_physical_aggregate_evidence_v2(values: dict[str, Any]) -> dict[str, Any]:
    backend = values["backend"]
    resolved_port = values["resolved_catalog_port"]
    initial_snapshot = dict(backend.snapshot_offline())
    transaction_log_audit = dict(backend.inspect_transaction_log_offline())
    prepared_catalog = dict(backend.list_prepared_transactions_offline())
    initial_resolved = dict(
        resolved_port.read_resolved_catalog_offline(
            backend=backend, backend_snapshot=initial_snapshot
        )
    )
    final_snapshot = dict(backend.snapshot_offline())
    final_transaction_log_audit = dict(
        backend.inspect_transaction_log_offline()
    )
    final_prepared_catalog = dict(backend.list_prepared_transactions_offline())
    final_resolved = dict(
        resolved_port.read_resolved_catalog_offline(
            backend=backend, backend_snapshot=final_snapshot
        )
    )
    return {
        "initial_backend_snapshot": initial_snapshot,
        "transaction_log_audit": transaction_log_audit,
        "prepared_catalog": prepared_catalog,
        "initial_resolved_catalog": initial_resolved,
        "final_backend_snapshot": final_snapshot,
        "final_transaction_log_audit": final_transaction_log_audit,
        "final_prepared_catalog": final_prepared_catalog,
        "final_resolved_catalog": final_resolved,
    }


def run_physical_aggregate_audit_offline_harness_v2() -> dict[str, Any]:
    with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
        evidence = collect_physical_aggregate_evidence_v2(values)
        result = make_physical_aggregate_audit_v2().build_offline(**evidence)
    aggregate = result.get("aggregate_audit") or {}
    ok = bool(
        result.get("ok") is True
        and contract_v2.physical_aggregate_recovery_audit_valid_v2(aggregate)
        and result.get("stable_observation_window_verified") is True
        and result.get("catalog_crosscheck_verified") is True
        and result.get("optimistic_atomic_observation_verified") is True
        and result.get("shared_lock_atomicity_verified") is False
        and aggregate.get("unresolved_prepared_count") == 0
        and aggregate.get("unresolved_resolved_count") == 0
        and aggregate.get("total_pending_count") == 0
        and aggregate.get("separate_resolved_ledger_verified") is True
        and aggregate.get("raw_wal_resolved_state_supported") is False
        and aggregate.get("write_executed") is False
        and aggregate.get("real_registry_accessed") is False
        and aggregate.get("network_accessed") is False
        and aggregate.get("broker_called") is False
        and aggregate.get("no_order_sent") is True
        and aggregate.get("production_ready") is False
        and aggregate.get("runtime_integrated") is False
        and aggregate.get("activation_allowed") is False
        and aggregate.get("live_allowed") is False
    )
    return {
        "ok": ok,
        "status": (
            "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_V2_HARNESS_PASSED"
            if ok
            else "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_V2_HARNESS_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_AGGREGATE_AUDIT_OFFLINE_HARNESS_V2_VERSION,
        "aggregate_audit": aggregate,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "source_filesystem_accessed": True,
        "write_executed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "collect_physical_aggregate_evidence_v2",
    "make_physical_aggregate_audit_v2",
    "run_physical_aggregate_audit_offline_harness_v2",
]
