"""Memory-only harness for the dormant recovery/provider identity binding."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_production_provider_v1 as production_provider
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as provider_binding_harness
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-RECOVERY-PRODUCTION-PROVIDER-BINDING-HARNESS-V1"
)


def build_synthetic_startup_recovery_production_provider_binding_context_v1() -> dict[
    str, Any
]:
    values = (
        provider_binding_harness.build_synthetic_provider_store_adapter_binding_context_v1()
    )
    provider_binding_result = values["binding_contract"].bind_offline(
        provider_projection=values["provider_projection"],
        store_projection=values["store_projection"],
        adapter_snapshot=values["adapter_snapshot"],
    )
    protected_provider_binding = provider_binding_result.get("protected_binding")
    binder = contract.DormantStartupRecoveryProductionProviderBindingContractV1(
        config=contract.DormantStartupRecoveryProductionProviderBindingConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
            ),
            expected_provider_store_binding_sha256=(
                protected_provider_binding.binding_sha256
                if protected_provider_binding is not None
                else None
            ),
            expected_adapter_contract_sha256=(
                contract.startup_recovery_adapter_contract_sha256_v1()
            ),
        )
    )
    return {
        **values,
        "provider_binding_result": provider_binding_result,
        "protected_provider_binding": protected_provider_binding,
        "startup_recovery_provider_binder": binder,
    }


def run_synthetic_startup_recovery_production_provider_binding_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_startup_recovery_production_provider_binding_context_v1()
    result = values["startup_recovery_provider_binder"].bind_offline(
        protected_provider_store_binding=values["protected_provider_binding"],
        provider_type=production_provider.ProductionClosedRepairProviderV1,
        adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
    )
    protected = result.get("protected_binding")
    counters = values["store_double"].counters()
    safe = bool(
        values["provider_binding_result"].get("ok") is True
        and result.get("ok") is True
        and result.get("provider_store_binding_verified") is True
        and result.get("provider_class_verified") is True
        and result.get("adapter_class_verified") is True
        and result.get("contract_identity_verified") is True
        and result.get("identity_binding_created") is True
        and result.get("direct_port_compatibility_verified") is False
        and result.get("bridge_required") is True
        and contract.protected_startup_recovery_production_provider_binding_valid_v1(
            protected
        )
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("provider_instance_bound") is False
        and result.get("adapter_instance_bound") is False
        and result.get("provider_called") is False
        and result.get("adapter_called") is False
        and result.get("recovery_executed") is False
        and result.get("runtime_integrated") is False
        and result.get("production_ready") is False
        and result.get("activation_allowed") is False
        and result.get("live_allowed") is False
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
            "C3_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_HARNESS_V1_VERSION,
        "provider_store_binding_verified": result.get(
            "provider_store_binding_verified"
        )
        is True,
        "exact_provider_class_verified": result.get("provider_class_verified")
        is True,
        "exact_adapter_class_verified": result.get("adapter_class_verified")
        is True,
        "identity_binding_created": result.get("identity_binding_created")
        is True,
        "direct_port_compatibility_verified": False,
        "bridge_required": True,
        "store_double_apply_call_count": counters["apply_call_count"],
        "store_double_recovery_call_count": counters["recovery_call_count"],
        "provider_called": False,
        "adapter_called": False,
        "recovery_executed": False,
        "runtime_integrated": False,
        "production_ready": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_startup_recovery_production_provider_binding_context_v1",
    "run_synthetic_startup_recovery_production_provider_binding_harness_v1",
]
