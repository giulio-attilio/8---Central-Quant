"""Memory-only harness for the provider/store/adapter binding contract."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as binding_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-PROVIDER-STORE-ADAPTER-BINDING-HARNESS-V1"
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_provider_store_adapter_binding_context_v1(
    *,
    backend_instance_sha256: str | None = None,
    registry_path_binding_sha256: str | None = None,
    capability_sha256: str | None = None,
) -> dict[str, Any]:
    backend_instance_sha256 = backend_instance_sha256 or _sha256_text(
        "synthetic-production-backend-instance-v1"
    )
    registry_path_binding_sha256 = (
        registry_path_binding_sha256
        or _sha256_text("synthetic-production-registry-path-binding-v1")
    )
    capability_sha256 = capability_sha256 or _sha256_text(
        "synthetic-production-backend-capability-attestation-v1"
    )
    composition_sha256 = _sha256_text(
        "synthetic-production-provider-composition-attestation-v1"
    )
    store_double = adapter_contract.InMemoryProductionBackendStoreDoubleV1(
        backend_instance_sha256=backend_instance_sha256,
        registry_path_binding_sha256=registry_path_binding_sha256,
        production_backend_capability_attestation_sha256=capability_sha256,
    )
    adapter_snapshot = store_double.snapshot()
    store_projection = {
        "projection_version": binding_contract.SYNTHETIC_STORE_PORT_PROJECTION_VERSION_V1,
        "source_store_version": binding_contract.EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1,
        "source_store_snapshot_sha256": _sha256_text(
            "synthetic-source-production-store-snapshot-v1"
        ),
        "storage_scope": "EXPLICIT_PRODUCTION",
        "store_instance_sha256": adapter_snapshot["store_instance_sha256"],
        "backend_instance_sha256": adapter_snapshot["backend_instance_sha256"],
        "registry_path_binding_sha256": adapter_snapshot[
            "registry_path_binding_sha256"
        ],
        "backend_capability_attestation_sha256": adapter_snapshot[
            "production_backend_capability_attestation_sha256"
        ],
        "lock_namespace_sha256": adapter_snapshot["lock_namespace_sha256"],
        "request_schema_version": adapter_snapshot["request_schema_version"],
        "result_schema_version": adapter_snapshot["result_schema_version"],
        "recovery_request_schema_version": adapter_snapshot[
            "recovery_request_schema_version"
        ],
        "apply_supported": True,
        "recovery_supported": True,
        "path_binding_required": True,
        "production_interface_bound_required": True,
        "durability_required": True,
        "durability_verified": False,
        "production_ready": False,
        "runtime_integrated": False,
        "synthetic_projection": True,
        "real_component_referenced": False,
        "production_evidence": False,
    }
    store_projection["projection_sha256"] = (
        binding_contract.store_port_projection_sha256_v1(store_projection)
    )
    provider_projection = {
        "projection_version": binding_contract.SYNTHETIC_PROVIDER_BINDING_PROJECTION_VERSION_V1,
        "source_provider_version": binding_contract.EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1,
        "source_provider_snapshot_sha256": _sha256_text(
            "synthetic-source-production-provider-snapshot-v1"
        ),
        "composition_attestation_sha256": composition_sha256,
        "binding_scope": "EXPLICIT_RUNTIME",
        "components_bound": True,
        "transaction_store_version": store_projection["source_store_version"],
        "transaction_store_storage_scope": store_projection["storage_scope"],
        "transaction_store_projection_sha256": store_projection[
            "projection_sha256"
        ],
        "registry_path_binding_sha256": store_projection[
            "registry_path_binding_sha256"
        ],
        "backend_capability_attestation_sha256": store_projection[
            "backend_capability_attestation_sha256"
        ],
        "lock_namespace_sha256": store_projection["lock_namespace_sha256"],
        "production_ready": False,
        "runtime_integrated": False,
        "synthetic_projection": True,
        "real_component_referenced": False,
        "production_evidence": False,
    }
    provider_projection["projection_sha256"] = (
        binding_contract.provider_binding_projection_sha256_v1(
            provider_projection
        )
    )
    binder = binding_contract.DormantProductionProviderStoreAdapterBindingContractV1(
        config=binding_contract.DormantProductionProviderStoreAdapterBindingConfigV1(
            enabled=True,
            scope_attestation=binding_contract.OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1,
            expected_provider_projection_sha256=provider_projection[
                "projection_sha256"
            ],
            expected_store_projection_sha256=store_projection[
                "projection_sha256"
            ],
            expected_adapter_snapshot_sha256=adapter_snapshot["snapshot_sha256"],
            expected_composition_attestation_sha256=composition_sha256,
        )
    )
    return {
        "store_double": store_double,
        "adapter_snapshot": adapter_snapshot,
        "store_projection": store_projection,
        "provider_projection": provider_projection,
        "composition_attestation_sha256": composition_sha256,
        "binding_contract": binder,
    }


def run_synthetic_provider_store_adapter_binding_harness_v1() -> dict[str, Any]:
    values = build_synthetic_provider_store_adapter_binding_context_v1()
    result = values["binding_contract"].bind_offline(
        provider_projection=values["provider_projection"],
        store_projection=values["store_projection"],
        adapter_snapshot=values["adapter_snapshot"],
    )
    protected = result.get("protected_binding")
    counters = values["store_double"].counters()
    safe = bool(
        result.get("ok") is True
        and result.get("provider_projection_verified") is True
        and result.get("store_projection_verified") is True
        and result.get("adapter_snapshot_verified") is True
        and result.get("cross_binding_verified") is True
        and result.get("binding_created") is True
        and binding_contract.protected_provider_store_adapter_binding_valid_v1(
            protected
        )
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("provider_called") is False
        and result.get("store_called") is False
        and result.get("production_backend_called") is False
        and result.get("runtime_integrated") is False
        and result.get("production_ready") is False
        and result.get("production_authority") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
    )
    return {
        "ok": safe,
        "status": (
            "C3_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_HARNESS_V1_VERSION,
        "provider_projection_bound_synthetic": result.get(
            "provider_projection_verified"
        )
        is True,
        "store_projection_bound_synthetic": result.get(
            "store_projection_verified"
        )
        is True,
        "adapter_snapshot_bound_synthetic": result.get(
            "adapter_snapshot_verified"
        )
        is True,
        "cross_binding_verified_synthetic": result.get(
            "cross_binding_verified"
        )
        is True,
        "terminal_receipt_contract_required": True,
        "recovery_receipt_contract_required": True,
        "durability_required": True,
        "durability_verified": False,
        "store_double_apply_call_count": counters["apply_call_count"],
        "store_double_recovery_call_count": counters["recovery_call_count"],
        "production_authority": False,
        "provider_called": False,
        "production_store_called": False,
        "production_backend_called": False,
        "runtime_integrated": False,
        "production_ready": False,
        "apply_allowed": False,
        "recovery_allowed": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_provider_store_adapter_binding_context_v1",
    "run_synthetic_provider_store_adapter_binding_harness_v1",
]
