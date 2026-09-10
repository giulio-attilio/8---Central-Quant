"""In-memory harness for the protected RESOLVED-store lease composition."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_harness_v2 as executor_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2 as executor_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_harness_v2 as store_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_v2 as composition_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-RESOLVED-STORE-"
    "MULTISTORE-LEASE-COMPOSITION-OFFLINE-HARNESS-V2"
)


def build_resolved_store_multistore_lease_composition_context_v2(
    *, fail_transaction_acquire: bool = False, fail_resolved_acquire: bool = False
) -> dict[str, Any]:
    values = store_harness_v2.build_production_resolved_authority_store_context_v2()
    store_result = values["store_contract"].bind_offline(
        authenticated_authority_binding=values["authenticated_binding"],
        multistore_lease_binding=values["multistore_binding"],
        resolved_lock_port_projection=values["resolved_projection"],
    )
    if store_result.get("ok") is not True:
        raise RuntimeError("SYNTHETIC_RESOLVED_STORE_BINDING_FAILED")
    store_binding = store_result["protected_binding"]
    now = executor_harness_v2.SYNTHETIC_NOW_V2
    authority = (
        executor_v2.build_synthetic_production_observation_authority_offline_v2(
            values["multistore_binding"],
            maintenance_epoch=store_harness_v2.multistore_harness_v2._sha(
                "resolved-store-lease-composition-maintenance-epoch"
            ),
            issued_at_epoch=now - 1,
            expires_at_epoch=now + 60,
        )
    )
    events: list[tuple[str, str]] = []
    transaction_port = executor_v2.InMemoryProductionStoreLockPortDoubleV2(
        values["transaction_projection"],
        fail_acquire=fail_transaction_acquire,
        event_sink=events,
    )
    resolved_port = executor_v2.InMemoryProductionStoreLockPortDoubleV2(
        values["resolved_projection"],
        fail_acquire=fail_resolved_acquire,
        event_sink=events,
    )
    executor = executor_v2.ReferenceProductionMultistoreObservationLeaseExecutorV2(
        executor_v2.ReferenceProductionMultistoreObservationLeaseExecutorConfigV2(
            enabled=True,
            scope_attestation=(
                executor_v2.OFFLINE_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_ATTESTATION_V2
            ),
            expected_binding_sha256=values[
                "multistore_binding"
            ].binding_sha256,
            expected_authority_sha256=authority.authority_sha256,
            expected_authority_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    authority
                )
            ),
            expected_transaction_lock_port_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    transaction_port
                )
            ),
            expected_resolved_lock_port_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_port
                )
            ),
            max_ttl_seconds=300,
            lock_timeout_seconds=1.0,
        ),
        clock=lambda: now,
        nonce_source=lambda: "resolved-store-multistore-composition",
    )
    dependencies = (
        store_binding,
        values["multistore_binding"],
        authority,
        values["transaction_projection"],
        values["resolved_projection"],
        transaction_port,
        resolved_port,
        executor,
        events,
    )
    identities = tuple(
        identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
            item
        )
        for item in dependencies
    )
    composition = composition_v2.ProductionResolvedStoreMultistoreLeaseCompositionV2(
        composition_v2.ProductionResolvedStoreMultistoreLeaseCompositionConfigV2(
            enabled=True,
            scope_attestation=(
                composition_v2.OFFLINE_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_SCOPE_ATTESTATION_V2
            ),
            expected_store_binding_sha256=store_binding.binding_sha256,
            expected_multistore_binding_sha256=values[
                "multistore_binding"
            ].binding_sha256,
            expected_authority_sha256=authority.authority_sha256,
            expected_transaction_projection_sha256=values[
                "transaction_projection"
            ].projection_sha256,
            expected_resolved_projection_sha256=values[
                "resolved_projection"
            ].projection_sha256,
            expected_store_binding_object_identity_sha256=identities[0],
            expected_multistore_binding_object_identity_sha256=identities[1],
            expected_authority_object_identity_sha256=identities[2],
            expected_transaction_projection_object_identity_sha256=identities[3],
            expected_resolved_projection_object_identity_sha256=identities[4],
            expected_transaction_port_object_identity_sha256=identities[5],
            expected_resolved_port_object_identity_sha256=identities[6],
            expected_executor_object_identity_sha256=identities[7],
            expected_event_observer_object_identity_sha256=identities[8],
            lease_ttl_seconds=30,
        ),
        resolved_store_binding=store_binding,
        multistore_lease_binding=values["multistore_binding"],
        synthetic_authority=authority,
        transaction_projection=values["transaction_projection"],
        resolved_projection=values["resolved_projection"],
        transaction_lock_port=transaction_port,
        resolved_lock_port=resolved_port,
        lease_executor=executor,
        event_observer=events,
        clock=lambda: now,
    )
    return {
        **values,
        "store_result": store_result,
        "store_binding": store_binding,
        "authority": authority,
        "events": events,
        "transaction_port": transaction_port,
        "resolved_port": resolved_port,
        "executor": executor,
        "composition": composition,
    }


def run_resolved_store_multistore_lease_composition_offline_harness_v2(
) -> dict[str, Any]:
    values = build_resolved_store_multistore_lease_composition_context_v2()
    result = values["composition"].execute_offline()
    receipt = result.get("execution_receipt")
    ok = bool(
        result.get("ok") is True
        and result.get("status")
        == "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_V2_VERIFIED_OFFLINE"
        and result.get("chain_verified") is True
        and result.get("lease_live_verified") is True
        and result.get("lease_released_after_execution") is True
        and composition_v2.production_resolved_store_multistore_lease_execution_receipt_valid_v2(
            receipt
        )
        and receipt["store_to_projection_binding_verified"] is True
        and receipt["projection_to_multistore_binding_verified"] is True
        and receipt["multistore_to_executor_binding_verified"] is True
        and receipt["same_instances_verified"] is True
        and receipt["acquire_order_verified"] is True
        and receipt["reverse_release_order_verified"] is True
        and values["executor"].snapshot()["held_lock_count"] == 0
        and values["store_result"]["store_open_allowed"] is False
        and result.get("physical_store_called") is False
        and result.get("filesystem_accessed") is False
        and result.get("network_accessed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("real_registry_accessed") is False
        and result.get("broker_called") is False
        and result.get("no_order_sent") is True
        and result.get("production_authority") is False
        and result.get("production_durable") is False
        and result.get("production_ready") is False
        and result.get("runtime_integrated") is False
        and result.get("activation_allowed") is False
        and result.get("live_allowed") is False
    )
    return {
        "ok": ok,
        "status": (
            "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_HARNESS_V2_PASSED"
            if ok
            else "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_HARNESS_V2_VERSION,
        "composition_result": result,
        "chain_verified": result.get("chain_verified") is True,
        "lease_released_after_execution": result.get(
            "lease_released_after_execution"
        )
        is True,
        "in_memory_only": True,
        "physical_store_called": False,
        "filesystem_accessed": False,
        "network_accessed": False,
        "real_registry_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_authority": False,
        "production_durable": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "build_resolved_store_multistore_lease_composition_context_v2",
    "run_resolved_store_multistore_lease_composition_offline_harness_v2",
]
