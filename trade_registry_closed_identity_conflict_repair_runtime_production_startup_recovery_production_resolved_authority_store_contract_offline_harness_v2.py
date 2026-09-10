"""In-memory harness for the dormant production RESOLVED store contract."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1 as authority_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_harness_v2 as multistore_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2 as store_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-RESOLVED-AUTHORITY-STORE-"
    "CONTRACT-OFFLINE-HARNESS-V2"
)


def build_production_resolved_authority_store_context_v2() -> dict[str, Any]:
    authority_values = (
        authority_harness_v1.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
    )
    authority_result = authority_values["binding_contract"].bind_offline(
        protected_evidence_schema=authority_values["protected_schema"],
        recovery_identity=authority_values["recovery_identity"],
        root_authority_attestation=authority_values[
            "root_authority_attestation"
        ],
        root_authority_verifier=authority_values["root_authority_verifier"],
        durable_authority_receipt=authority_values["durable_authority_receipt"],
        now_epoch=authority_values["now_epoch"],
    )
    if authority_result.get("ok") is not True:
        raise RuntimeError("SYNTHETIC_AUTHENTICATED_AUTHORITY_BINDING_FAILED")
    authenticated_binding = authority_result["protected_binding"]
    authenticated = dict(authenticated_binding.binding)
    transaction_projection = (
        multistore_v2.build_production_store_lock_port_projection_offline_v2(
            port_role=multistore_v2.TRANSACTION_STORE_ROLE_V2,
            source_contract_version=(
                multistore_v2.EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2
            ),
            store_identity_sha256=multistore_harness_v2._sha(
                "resolved-store-context-transaction-identity"
            ),
            storage_binding_sha256=multistore_harness_v2._sha(
                "resolved-store-context-transaction-storage"
            ),
            lock_namespace_sha256=multistore_harness_v2._sha(
                "resolved-store-context-transaction-lock"
            ),
        )
    )
    resolved_projection = (
        multistore_v2.build_production_store_lock_port_projection_offline_v2(
            port_role=multistore_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2,
            source_contract_version=(
                multistore_v2.EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
            ),
            store_identity_sha256=multistore_harness_v2._sha(
                "resolved-store-context-resolved-identity"
            ),
            storage_binding_sha256=authenticated[
                "durable_authority_storage_binding_sha256"
            ],
            lock_namespace_sha256=multistore_harness_v2._sha(
                "resolved-store-context-resolved-lock"
            ),
        )
    )
    multistore_contract = (
        multistore_v2.DormantProductionMultistoreObservationLeaseContractV2(
            multistore_v2.DormantProductionMultistoreObservationLeaseConfigV2(
                enabled=True,
                scope_attestation=(
                    multistore_v2.OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
                ),
                expected_transaction_store_projection_sha256=(
                    transaction_projection.projection_sha256
                ),
                expected_resolved_authority_store_projection_sha256=(
                    resolved_projection.projection_sha256
                ),
                expected_writer_coordination_binding_sha256=(
                    multistore_harness_v2._sha(
                        "resolved-store-context-writer-coordination"
                    )
                ),
                expected_maintenance_lease_contract_sha256=authenticated[
                    "maintenance_lease_receipt_sha256"
                ],
                expected_authenticated_authority_contract_sha256=(
                    authenticated_binding.binding_sha256
                ),
                required_writer_count=19,
            )
        )
    )
    multistore_result = multistore_contract.bind_offline(
        transaction_store_lock_port=transaction_projection,
        resolved_authority_store_lock_port=resolved_projection,
    )
    if multistore_result.get("ok") is not True:
        raise RuntimeError("SYNTHETIC_MULTISTORE_BINDING_FAILED")
    multistore_binding = multistore_result["protected_binding"]
    store_contract = store_v2.DormantProductionResolvedAuthorityStoreContractV2(
        store_v2.DormantProductionResolvedAuthorityStoreConfigV2(
            enabled=True,
            scope_attestation=(
                store_v2.OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2
            ),
            expected_authenticated_binding_sha256=(
                authenticated_binding.binding_sha256
            ),
            expected_multistore_binding_sha256=multistore_binding.binding_sha256,
            expected_resolved_projection_sha256=(
                resolved_projection.projection_sha256
            ),
            expected_authenticated_binding_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    authenticated_binding
                )
            ),
            expected_multistore_binding_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    multistore_binding
                )
            ),
            expected_resolved_projection_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_projection
                )
            ),
        )
    )
    return {
        **authority_values,
        "authority_result": authority_result,
        "authenticated_binding": authenticated_binding,
        "transaction_projection": transaction_projection,
        "resolved_projection": resolved_projection,
        "multistore_contract": multistore_contract,
        "multistore_result": multistore_result,
        "multistore_binding": multistore_binding,
        "store_contract": store_contract,
    }


def run_production_resolved_authority_store_contract_offline_harness_v2(
) -> dict[str, Any]:
    values = build_production_resolved_authority_store_context_v2()
    result = values["store_contract"].bind_offline(
        authenticated_authority_binding=values["authenticated_binding"],
        multistore_lease_binding=values["multistore_binding"],
        resolved_lock_port_projection=values["resolved_projection"],
    )
    protected = result.get("protected_binding")
    binding = dict(protected.binding) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and result.get("status")
        == "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_V2_VERIFIED_OFFLINE"
        and result.get("authenticated_root_evidence_verified") is True
        and result.get("rotation_recovery_requirements_verified") is True
        and result.get("multistore_cross_binding_verified") is True
        and store_v2.protected_production_resolved_authority_store_binding_valid_v2(
            protected
        )
        and binding.get("root_signature_evidence_verified") is True
        and binding.get("monotonic_key_epoch_required") is True
        and binding.get("root_revocation_registry_required") is True
        and binding.get("write_ahead_log_required") is True
        and binding.get("crash_recovery_required") is True
        and binding.get("unresolved_transactions_block_readiness") is True
        and binding.get("physical_store_implementation_bound") is False
        and result.get("store_open_allowed") is False
        and result.get("store_read_allowed") is False
        and result.get("store_write_allowed") is False
        and result.get("root_rotation_allowed") is False
        and result.get("recovery_allowed") is False
        and result.get("filesystem_accessed") is False
        and result.get("network_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("no_order_sent") is True
        and result.get("production_signature_verified") is False
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
            "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_HARNESS_V2_PASSED"
            if ok
            else "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_HARNESS_V2_VERSION,
        "store_result": result,
        "authenticated_root_evidence_verified": result.get(
            "authenticated_root_evidence_verified"
        )
        is True,
        "rotation_recovery_requirements_verified": result.get(
            "rotation_recovery_requirements_verified"
        )
        is True,
        "multistore_cross_binding_verified": result.get(
            "multistore_cross_binding_verified"
        )
        is True,
        "physical_store_implementation_bound": False,
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
    "build_production_resolved_authority_store_context_v2",
    "run_production_resolved_authority_store_contract_offline_harness_v2",
]
