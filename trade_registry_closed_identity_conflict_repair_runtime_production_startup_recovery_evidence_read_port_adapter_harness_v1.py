"""Synthetic harness for the dormant evidence read-port adapter plan."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1 as scope_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-READ-PORT-ADAPTER-HARNESS-V1"
)


def make_synthetic_evidence_read_port_adapter_contract_v1(
    *,
    scope_binding_sha256: str,
    startup_provider_binding_sha256: str,
    provider_store_binding_sha256: str,
) -> contract.DormantStartupRecoveryEvidenceReadPortAdapterContractV1:
    return contract.DormantStartupRecoveryEvidenceReadPortAdapterContractV1(
        config=contract.DormantStartupRecoveryEvidenceReadPortAdapterConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1
            ),
            expected_scope_binding_sha256=scope_binding_sha256,
            expected_startup_provider_binding_sha256=(
                startup_provider_binding_sha256
            ),
            expected_provider_store_binding_sha256=provider_store_binding_sha256,
        )
    )


def build_synthetic_evidence_read_port_adapter_context_v1() -> dict[str, Any]:
    values = (
        scope_harness_v1.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
    )
    scope_result = values["scope_contract"].bind_offline(
        protected_batch_session=values["protected_batch_session"],
        protected_evidence_schema=values["protected_schema"],
    )
    protected_scope = scope_result.get("protected_scope_binding")
    protected_startup_provider = values["protected_identity_binding"]
    protected_provider = values["provider_store_result"]["protected_binding"]
    if scope_result.get("ok") is not True or protected_scope is None:
        raise ValueError("synthetic protected evidence scope unavailable")
    adapter_contract = make_synthetic_evidence_read_port_adapter_contract_v1(
        scope_binding_sha256=protected_scope.binding_sha256,
        startup_provider_binding_sha256=protected_startup_provider.binding_sha256,
        provider_store_binding_sha256=protected_provider.binding_sha256,
    )
    return {
        **values,
        "scope_result": scope_result,
        "protected_scope_binding": protected_scope,
        "protected_startup_provider_binding": protected_startup_provider,
        "protected_provider_store_binding": protected_provider,
        "adapter_contract": adapter_contract,
    }


def run_synthetic_evidence_read_port_adapter_harness_v1() -> dict[str, Any]:
    values = build_synthetic_evidence_read_port_adapter_context_v1()
    result = values["adapter_contract"].project_offline(
        protected_scope_binding=values["protected_scope_binding"],
        protected_startup_provider_binding=values[
            "protected_startup_provider_binding"
        ],
        protected_provider_store_binding=values[
            "protected_provider_store_binding"
        ],
    )
    protected = result.get("protected_adapter_plan")
    plan = protected.plan if protected is not None else {}
    store_counts = values["store_double"].counters()
    safe = bool(
        result.get("ok") is True
        and result.get("scope_binding_verified") is True
        and result.get("startup_provider_binding_verified") is True
        and result.get("provider_store_binding_verified") is True
        and result.get("identity_vector_verified") is True
        and result.get("adapter_plan_created") is True
        and contract.protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
            protected
        )
        and plan.get("required_port_count") == 6
        and plan.get("implemented_port_count") == 0
        and plan.get("missing_port_count") == 6
        and plan.get("complete_prepared_catalog_required") is True
        and plan.get("complete_resolved_catalog_required") is True
        and plan.get("empirical_capability_probe_required") is True
        and plan.get("terminal_receipt_normalizer_required") is True
        and plan.get("adapter_callable_created") is False
        and plan.get("provider_instance_bound") is False
        and plan.get("backend_instance_bound") is False
        and store_counts == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("provider_called") is False
        and result.get("store_called") is False
        and result.get("backend_called") is False
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("runtime_integrated") is False
        and result.get("live_allowed") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_HARNESS_V1_VERSION,
        "required_port_count": plan.get("required_port_count", 0),
        "implemented_port_count": plan.get("implemented_port_count", 0),
        "missing_port_count": plan.get("missing_port_count", 0),
        "identity_vector_verified": result.get("identity_vector_verified") is True,
        "adapter_callable_created": False,
        "provider_instance_bound": False,
        "backend_instance_bound": False,
        "production_authority": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_HARNESS_V1_VERSION",
    "build_synthetic_evidence_read_port_adapter_context_v1",
    "make_synthetic_evidence_read_port_adapter_contract_v1",
    "run_synthetic_evidence_read_port_adapter_harness_v1",
]
