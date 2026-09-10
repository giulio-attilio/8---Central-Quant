"""Synthetic harness for the dormant batch-to-evidence scope binding."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_harness_v1 as batch_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-BATCH-EVIDENCE-SCOPE-BINDING-HARNESS-V1"
)


def make_synthetic_batch_evidence_scope_binding_contract_v1(
    *,
    batch_session_receipt_sha256: str,
    schema_sha256: str,
    pending_catalog_binding_sha256: str,
) -> contract.DormantStartupRecoveryBatchEvidenceScopeBindingContractV1:
    return contract.DormantStartupRecoveryBatchEvidenceScopeBindingContractV1(
        config=contract.DormantStartupRecoveryBatchEvidenceScopeBindingConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1
            ),
            expected_batch_session_receipt_sha256=batch_session_receipt_sha256,
            expected_schema_sha256=schema_sha256,
            expected_pending_catalog_binding_sha256=(
                pending_catalog_binding_sha256
            ),
        )
    )


def build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1() -> dict[
    str, Any
]:
    values = (
        batch_harness_v1.build_synthetic_startup_recovery_batch_session_authority_context_v1()
    )
    batch_result = values["batch_contract"].bind_offline(
        protected_authenticated_authority_binding=values[
            "protected_authenticated_binding"
        ],
        protected_restart_admissions=values["protected_restart_admissions"],
        pending_states_by_transaction=values[
            "pending_states_by_transaction"
        ],
        now_epoch=values["now_epoch"],
    )
    protected_batch_session = batch_result.get("protected_batch_session")
    if batch_result.get("ok") is not True or protected_batch_session is None:
        raise ValueError("synthetic protected batch session unavailable")
    protected_schema = values["protected_schema"]
    scope_contract = make_synthetic_batch_evidence_scope_binding_contract_v1(
        batch_session_receipt_sha256=protected_batch_session.receipt_sha256,
        schema_sha256=protected_schema.schema_sha256,
        pending_catalog_binding_sha256=protected_batch_session.receipt[
            "pending_catalog_binding_sha256"
        ],
    )
    return {
        **values,
        "batch_result": batch_result,
        "protected_batch_session": protected_batch_session,
        "scope_contract": scope_contract,
    }


def run_synthetic_startup_recovery_batch_evidence_scope_binding_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
    result = values["scope_contract"].bind_offline(
        protected_batch_session=values["protected_batch_session"],
        protected_evidence_schema=values["protected_schema"],
    )
    protected = result.get("protected_scope_binding")
    binding = protected.binding if protected is not None else {}
    restart_result = values["restart_result"]
    counters = values["store_double"].counters()
    safe = bool(
        result.get("ok") is True
        and result.get("batch_session_verified") is True
        and result.get("evidence_schema_verified") is True
        and result.get("identity_vector_verified") is True
        and result.get("batch_scope_bound") is True
        and contract.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
            protected
        )
        and binding.get("pending_item_count") == 1
        and binding.get("exact_maintenance_epoch_required") is True
        and binding.get("exact_maintenance_lease_receipt_required") is True
        and binding.get("exact_authenticated_authority_receipt_required") is True
        and binding.get("exact_pending_catalog_crosscheck_required") is True
        and binding.get("terminal_receipt_per_pending_item_required") is True
        and binding.get("live_lease_revalidation_required") is True
        and binding.get("durable_current_state_revalidation_required") is True
        and binding.get("evidence_created") is False
        and binding.get("evidence_builder_called") is False
        and binding.get("evidence_population_allowed") is False
        and binding.get("recovery_authority_granted") is False
        and binding.get("production_authority") is False
        and binding.get("runtime_integrated") is False
        and binding.get("live_allowed") is False
        and restart_result.get("temporary_filesystem_accessed") is True
        and restart_result.get("temporary_storage_removed") is True
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_HARNESS_V1_VERSION,
        "pending_item_count": binding.get("pending_item_count", 0),
        "batch_scope_bound": result.get("batch_scope_bound") is True,
        "exact_maintenance_identity_required": all(
            binding.get(field_name) is True
            for field_name in (
                "exact_maintenance_epoch_required",
                "exact_maintenance_lease_receipt_required",
            )
        ),
        "exact_catalog_and_authority_crosscheck_required": all(
            binding.get(field_name) is True
            for field_name in (
                "exact_authenticated_authority_receipt_required",
                "exact_pending_catalog_crosscheck_required",
                "terminal_receipt_per_pending_item_required",
            )
        ),
        "upstream_temporary_storage_accessed": restart_result.get(
            "temporary_filesystem_accessed"
        )
        is True,
        "upstream_temporary_storage_removed": restart_result.get(
            "temporary_storage_removed"
        )
        is True,
        "scope_contract_filesystem_accessed": False,
        "evidence_created": False,
        "evidence_builder_called": False,
        "evidence_population_allowed": False,
        "recovery_authority_granted": False,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1",
    "make_synthetic_batch_evidence_scope_binding_contract_v1",
    "run_synthetic_startup_recovery_batch_evidence_scope_binding_harness_v1",
]
