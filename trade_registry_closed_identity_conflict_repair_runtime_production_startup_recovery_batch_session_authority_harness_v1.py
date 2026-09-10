"""Temporary-synthetic harness for the dormant batch-session authority."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_authority_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2 as restart_admission_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as authenticated_binding_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1 as authenticated_binding_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as schema_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-BATCH-SESSION-AUTHORITY-HARNESS-V1"
)


class OfflineSyntheticDurableRootVerifierV1(
    durable_authority_harness_v2._SyntheticRootAuthorityVerifierV2
):
    offline_only = True
    filesystem_access_allowed = False
    network_access_allowed = False

    def __repr__(self) -> str:
        return "OfflineSyntheticDurableRootVerifierV1(<protected>)"


def make_synthetic_batch_session_contract_v1(
    *,
    authenticated_authority_binding_sha256: str,
    pending_catalog_binding_sha256: str,
    pending_item_count: int,
) -> contract.DormantStartupRecoveryBatchSessionAuthorityContractV1:
    return contract.DormantStartupRecoveryBatchSessionAuthorityContractV1(
        config=contract.DormantStartupRecoveryBatchSessionAuthorityConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1
            ),
            expected_authenticated_authority_binding_sha256=(
                authenticated_authority_binding_sha256
            ),
            expected_pending_catalog_binding_sha256=(
                pending_catalog_binding_sha256
            ),
            expected_pending_item_count=pending_item_count,
        )
    )


def build_synthetic_startup_recovery_batch_session_authority_context_v1() -> dict[
    str, Any
]:
    restart_result = restart_admission_harness_v2.run_durable_restart_admission_harness_v2()
    protected_admission = restart_result.get("protected_admission")
    if restart_result.get("ok") is not True or protected_admission is None:
        raise ValueError("synthetic restart admission unavailable")
    request = protected_admission.obligation.adapter_plan.protected_request.request
    schema_values = (
        schema_harness_v1.build_synthetic_production_startup_recovery_evidence_schema_context_v1(
            backend_instance_sha256=request["backend_instance_sha256"],
            registry_path_binding_sha256=request[
                "registry_path_binding_sha256"
            ],
        )
    )
    schema_result = schema_values["schema_contract"].define_offline(
        protected_provider_binding=schema_values["protected_identity_binding"]
    )
    protected_schema = schema_result.get("protected_schema")
    if schema_result.get("ok") is not True or protected_schema is None:
        raise ValueError("synthetic recovery schema unavailable")
    durable_receipt = protected_admission.durable_authority_receipt
    root_attestation = durable_authority_harness_v2._root_attestation(
        durable_receipt.receipt["root_identity_sha256"],
        durable_receipt.receipt["storage_binding_sha256"],
    )
    if (
        root_attestation["attestation_sha256"]
        != durable_receipt.receipt["root_authority_attestation_sha256"]
    ):
        raise ValueError("synthetic root attestation reconstruction mismatch")
    recovery_identity = (
        authenticated_binding_harness_v1.make_synthetic_startup_recovery_authority_identity_v1(
            backend_instance_sha256=request["backend_instance_sha256"],
            registry_path_binding_sha256=request[
                "registry_path_binding_sha256"
            ],
            lock_namespace_sha256=request["lock_namespace_sha256"],
            authority_storage_binding_sha256=durable_receipt.receipt[
                "storage_binding_sha256"
            ],
        )
    )
    recovery_identity["maintenance_epoch"] = protected_admission.admission[
        "fresh_maintenance_epoch"
    ]
    recovery_identity["maintenance_lease_receipt_sha256"] = (
        contract.startup_recovery_batch_maintenance_lease_receipt_sha256_v1(
            protected_admission
        )
    )
    recovery_identity["identity_sha256"] = (
        authenticated_binding_v1.startup_recovery_authority_identity_sha256_v1(
            recovery_identity
        )
    )
    verifier = OfflineSyntheticDurableRootVerifierV1()
    authenticated_contract = (
        authenticated_binding_harness_v1.make_synthetic_authenticated_authority_binding_contract_v1(
            schema_sha256=protected_schema.schema_sha256,
            root_authority_attestation_sha256=root_attestation[
                "attestation_sha256"
            ],
            durable_authority_receipt_sha256=durable_receipt.receipt_sha256,
            recovery_identity_sha256=recovery_identity["identity_sha256"],
        )
    )
    authenticated_result = authenticated_contract.bind_offline(
        protected_evidence_schema=protected_schema,
        recovery_identity=recovery_identity,
        root_authority_attestation=root_attestation,
        root_authority_verifier=verifier,
        durable_authority_receipt=durable_receipt,
        now_epoch=protected_admission.admission["admitted_at_epoch"],
    )
    protected_authenticated_binding = authenticated_result.get(
        "protected_binding"
    )
    if (
        authenticated_result.get("ok") is not True
        or protected_authenticated_binding is None
    ):
        raise ValueError("synthetic authenticated authority binding unavailable")
    protected_admissions = (protected_admission,)
    pending_states = {
        protected_admission.admission["transaction_sha256"]: "PREPARED"
    }
    pending_items = contract._pending_items(protected_admissions, pending_states)
    catalog_binding_sha256 = (
        contract.startup_recovery_batch_pending_catalog_binding_sha256_v1(
            pending_items
        )
    )
    batch_contract = make_synthetic_batch_session_contract_v1(
        authenticated_authority_binding_sha256=(
            protected_authenticated_binding.binding_sha256
        ),
        pending_catalog_binding_sha256=catalog_binding_sha256,
        pending_item_count=len(protected_admissions),
    )
    return {
        **schema_values,
        "restart_result": restart_result,
        "schema_result": schema_result,
        "protected_schema": protected_schema,
        "root_attestation": root_attestation,
        "root_verifier": verifier,
        "recovery_identity": recovery_identity,
        "authenticated_result": authenticated_result,
        "protected_authenticated_binding": protected_authenticated_binding,
        "protected_restart_admissions": protected_admissions,
        "pending_states_by_transaction": pending_states,
        "pending_items": pending_items,
        "pending_catalog_binding_sha256": catalog_binding_sha256,
        "batch_contract": batch_contract,
        "now_epoch": protected_admission.admission["admitted_at_epoch"],
    }


def run_synthetic_startup_recovery_batch_session_authority_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_startup_recovery_batch_session_authority_context_v1()
    result = values["batch_contract"].bind_offline(
        protected_authenticated_authority_binding=values[
            "protected_authenticated_binding"
        ],
        protected_restart_admissions=values["protected_restart_admissions"],
        pending_states_by_transaction=values["pending_states_by_transaction"],
        now_epoch=values["now_epoch"],
    )
    protected = result.get("protected_batch_session")
    receipt = protected.receipt if protected is not None else {}
    counters = values["store_double"].counters()
    restart_result = values["restart_result"]
    safe = bool(
        restart_result.get("ok") is True
        and restart_result.get("temporary_filesystem_accessed") is True
        and restart_result.get("temporary_storage_removed") is True
        and values["schema_result"].get("ok") is True
        and values["authenticated_result"].get("ok") is True
        and result.get("ok") is True
        and result.get("authenticated_binding_verified") is True
        and result.get("restart_admissions_verified") is True
        and result.get("batch_identity_verified") is True
        and result.get("batch_session_bound") is True
        and contract.protected_startup_recovery_batch_session_authority_valid_v1(
            protected
        )
        and receipt.get("pending_item_count") == 1
        and receipt.get("same_permit_instance_verified") is True
        and receipt.get("same_backend_instance_verified") is True
        and receipt.get("same_registry_path_binding_verified") is True
        and receipt.get("same_lock_namespace_verified") is True
        and receipt.get("same_maintenance_epoch_verified") is True
        and receipt.get("live_lease_revalidation_required") is True
        and receipt.get("durable_current_state_revalidation_required") is True
        and receipt.get("recovery_authority_granted") is False
        and receipt.get("evidence_population_allowed") is False
        and receipt.get("production_authority") is False
        and receipt.get("runtime_integrated") is False
        and receipt.get("live_allowed") is False
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("provider_called") is False
        and result.get("store_called") is False
        and result.get("backend_called") is False
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
            "C3_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_HARNESS_V1_VERSION,
        "pending_item_count": receipt.get("pending_item_count", 0),
        "same_session_identity_verified": all(
            receipt.get(field_name) is True
            for field_name in (
                "same_permit_instance_verified",
                "same_lease_token_instance_verified",
                "same_lease_witness_instance_verified",
                "same_session_anchor_instance_verified",
                "same_authorization_issuer_instance_verified",
                "same_single_use_ledger_instance_verified",
            )
        ),
        "same_backend_path_lock_epoch_verified": all(
            receipt.get(field_name) is True
            for field_name in (
                "same_backend_instance_verified",
                "same_registry_path_binding_verified",
                "same_lock_namespace_verified",
                "same_maintenance_epoch_verified",
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
        "batch_contract_filesystem_accessed": False,
        "live_lease_revalidation_required": True,
        "durable_current_state_revalidation_required": True,
        "recovery_authority_granted": False,
        "evidence_created": False,
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
    "OfflineSyntheticDurableRootVerifierV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_HARNESS_V1_VERSION",
    "build_synthetic_startup_recovery_batch_session_authority_context_v1",
    "make_synthetic_batch_session_contract_v1",
    "run_synthetic_startup_recovery_batch_session_authority_harness_v1",
]
