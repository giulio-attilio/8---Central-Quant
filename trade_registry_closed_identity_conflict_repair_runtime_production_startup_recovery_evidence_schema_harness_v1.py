"""In-memory harness for the dormant production recovery evidence schema."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_production_provider_v1 as production_provider
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as provider_store_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as provider_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SCHEMA-HARNESS-V1"
)


def build_synthetic_production_startup_recovery_evidence_schema_context_v1(
    *,
    backend_instance_sha256: str | None = None,
    registry_path_binding_sha256: str | None = None,
    capability_sha256: str | None = None,
) -> dict[str, Any]:
    values = provider_store_harness.build_synthetic_provider_store_adapter_binding_context_v1(
        backend_instance_sha256=backend_instance_sha256,
        registry_path_binding_sha256=registry_path_binding_sha256,
        capability_sha256=capability_sha256,
    )
    provider_store_result = values["binding_contract"].bind_offline(
        provider_projection=values["provider_projection"],
        store_projection=values["store_projection"],
        adapter_snapshot=values["adapter_snapshot"],
    )
    protected_provider_store = provider_store_result.get("protected_binding")
    identity_binder = provider_binding.DormantStartupRecoveryProductionProviderBindingContractV1(
        config=provider_binding.DormantStartupRecoveryProductionProviderBindingConfigV1(
            enabled=True,
            scope_attestation=(
                provider_binding.OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
            ),
            expected_provider_store_binding_sha256=(
                protected_provider_store.binding_sha256
                if protected_provider_store is not None
                else None
            ),
            expected_adapter_contract_sha256=(
                provider_binding.startup_recovery_adapter_contract_sha256_v1()
            ),
        )
    )
    identity_result = identity_binder.bind_offline(
        protected_provider_store_binding=protected_provider_store,
        provider_type=production_provider.ProductionClosedRepairProviderV1,
        adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
    )
    protected_identity = identity_result.get("protected_binding")
    schema_contract = contract.DormantProductionStartupRecoveryEvidenceSchemaContractV1(
        config=contract.DormantProductionStartupRecoveryEvidenceSchemaConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1
            ),
            expected_provider_binding_sha256=(
                protected_identity.binding_sha256
                if protected_identity is not None
                else None
            ),
        )
    )
    return {
        **values,
        "provider_store_result": provider_store_result,
        "identity_result": identity_result,
        "protected_identity_binding": protected_identity,
        "schema_contract": schema_contract,
    }


def run_synthetic_production_startup_recovery_evidence_schema_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_production_startup_recovery_evidence_schema_context_v1()
    result = values["schema_contract"].define_offline(
        protected_provider_binding=values["protected_identity_binding"]
    )
    protected = result.get("protected_schema")
    schema = protected.schema if protected is not None else {}
    counters = values["store_double"].counters()
    safe = bool(
        values["provider_store_result"].get("ok") is True
        and values["identity_result"].get("ok") is True
        and result.get("ok") is True
        and result.get("provider_binding_verified") is True
        and result.get("prepared_schema_defined") is True
        and result.get("resolved_schema_defined") is True
        and result.get("schema_created") is True
        and result.get("evidence_created") is False
        and contract.protected_production_startup_recovery_evidence_schema_valid_v1(
            protected
        )
        and schema.get("pending_states") == ["PREPARED", "RESOLVED"]
        and schema.get("authenticated_verifier_required") is True
        and schema.get("empirical_capability_probe_required") is True
        and schema.get("evidence_builder_available") is False
        and schema.get("production_authority") is False
        and schema.get("production_ready") is False
        and schema.get("runtime_integrated") is False
        and schema.get("recovery_execution_allowed") is False
        and schema.get("live_allowed") is False
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
            "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_HARNESS_V1_VERSION,
        "prepared_and_resolved_schemas_defined": bool(
            result.get("prepared_schema_defined")
            and result.get("resolved_schema_defined")
        ),
        "pending_states": list(schema.get("pending_states") or ()),
        "authenticated_proofs_required": result.get(
            "authenticated_proofs_required"
        )
        is True,
        "empirical_capability_probe_required": result.get(
            "empirical_capability_probe_required"
        )
        is True,
        "evidence_created": False,
        "production_provider_instantiated": False,
        "production_provider_called": False,
        "production_store_called": False,
        "production_backend_called": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_HARNESS_V1_VERSION",
    "build_synthetic_production_startup_recovery_evidence_schema_context_v1",
    "run_synthetic_production_startup_recovery_evidence_schema_harness_v1",
]
