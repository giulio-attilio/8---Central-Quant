"""Synthetic harness for aggregate collection under one two-store lease."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as collection_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-LOCKED-AGGREGATE-COLLECTION-"
    "OFFLINE-HARNESS-V2"
)


def make_physical_locked_aggregate_collection_v2(
    *, observation_lease: Any, backend: Any, ledger: Any, clock=None
) -> collection_v2.PhysicalLockedAggregateCollectionV2:
    return collection_v2.PhysicalLockedAggregateCollectionV2(
        collection_v2.PhysicalLockedAggregateCollectionConfigV2(
            enabled=True,
            scope_attestation=(
                collection_v2.OFFLINE_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_ATTESTATION_V2
            ),
            expected_lease_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    observation_lease
                )
            ),
            expected_backend_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                )
            ),
            expected_ledger_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    ledger
                )
            ),
            lease_ttl_seconds=60,
        ),
        observation_lease=observation_lease,
        backend=backend,
        durable_authority_ledger=ledger,
        clock=clock or (lambda: physical_harness_v2.SYNTHETIC_NOW_V2),
    )


def run_physical_locked_aggregate_collection_offline_harness_v2() -> dict[str, Any]:
    with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
        result = values["locked_collection"].collect_offline()
        receipt = result.get("collection_receipt")
        aggregate = result.get("aggregate_audit")
        ok = bool(
            result.get("ok") is True
            and result.get("status")
            == "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_V2_VERIFIED_OFFLINE"
            and collection_v2.physical_locked_aggregate_collection_receipt_valid_v2(
                receipt
            )
            and receipt["aggregate_audit_sha256"]
            == aggregate["aggregate_audit_sha256"]
            and receipt["held_lock_count"] == 2
            and receipt["lease_revalidation_count"] == 8
            and receipt["shared_lock_atomicity_verified"] is True
            and receipt["lease_released_after_collection"] is True
            and result.get("lease_revalidation_count") == 8
            and result.get("shared_lock_atomicity_verified") is True
            and result.get("stable_observation_window_verified") is True
            and result.get("catalog_crosscheck_verified") is True
            and result.get("lease_released_after_collection") is True
            and values["observation_lease"].snapshot()["held_lock_count"] == 0
            and aggregate["optimistic_atomic_observation_verified"] is True
            and aggregate["shared_lock_atomicity_verified"] is False
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("write_executed") is False
            and result.get("registry_write") is False
            and result.get("no_order_sent") is True
            and result.get("production_ready") is False
            and result.get("runtime_integrated") is False
            and result.get("activation_allowed") is False
            and result.get("live_allowed") is False
        )
    return {
        "ok": ok,
        "status": (
            "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_V2_HARNESS_PASSED"
            if ok
            else "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_V2_HARNESS_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_OFFLINE_HARNESS_V2_VERSION,
        "collection_result": result,
        "same_lease_eight_reads_verified": bool(
            result.get("lease_revalidation_count") == 8
        ),
        "shared_lock_atomicity_verified": bool(
            result.get("shared_lock_atomicity_verified") is True
        ),
        "lease_released_after_collection": bool(
            result.get("lease_released_after_collection") is True
        ),
        "temporary_storage_only": True,
        "synthetic_only": True,
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
    "make_physical_locked_aggregate_collection_v2",
    "run_physical_locked_aggregate_collection_offline_harness_v2",
]
