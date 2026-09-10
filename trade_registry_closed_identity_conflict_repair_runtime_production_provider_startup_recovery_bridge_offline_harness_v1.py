"""Temporary synthetic harness for the offline production-provider bridge."""

from __future__ import annotations

import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract
import trade_registry_closed_identity_conflict_repair_production_provider_v1 as production_provider
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_v1 as bridge_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as provider_store_binding_harness
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as provider_binding_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-PROVIDER-STARTUP-RECOVERY-BRIDGE-OFFLINE-HARNESS-V1"
)
SYNTHETIC_NOW_V1 = 1_788_900_000


def build_synthetic_production_provider_startup_recovery_bridge_context_v1(
    storage_root: str,
    *,
    prepared_count: int = 2,
) -> dict[str, Any]:
    backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
        storage_root,
        enabled=True,
        scope_attestation=(
            physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
        ),
        clock=lambda: SYNTHETIC_NOW_V1,
    )
    backend.initialize_synthetic_registry_offline(
        {"closed_trades": [], "fixture": "provider-bridge-source"}
    )
    for index in range(prepared_count):
        request = backend.build_transaction_request_offline(
            {
                "closed_trades": [],
                "fixture": f"provider-bridge-candidate-{index}",
            },
            label=f"provider-bridge-prepared-{index}",
            deadline_epoch=SYNTHETIC_NOW_V1 + 120,
        )
        backend.prepare_interrupted_transaction_offline(request)
    snapshot = backend.snapshot_offline()
    capability_sha256 = backend_contract.stable_sha256_v2(
        {
            "kind": "SYNTHETIC_TEMPORARY_PROVIDER_BRIDGE_CAPABILITY_V1",
            "backend_module_source_sha256": snapshot[
                "backend_module_source_sha256"
            ],
        }
    )
    provider_values = provider_store_binding_harness.build_synthetic_provider_store_adapter_binding_context_v1(
        backend_instance_sha256=snapshot["backend_instance_sha256"],
        registry_path_binding_sha256=snapshot[
            "registry_path_binding_sha256"
        ],
        capability_sha256=capability_sha256,
    )
    provider_store_result = provider_values["binding_contract"].bind_offline(
        provider_projection=provider_values["provider_projection"],
        store_projection=provider_values["store_projection"],
        adapter_snapshot=provider_values["adapter_snapshot"],
    )
    protected_provider_store = provider_store_result.get("protected_binding")
    identity_binder = provider_binding_contract.DormantStartupRecoveryProductionProviderBindingContractV1(
        config=provider_binding_contract.DormantStartupRecoveryProductionProviderBindingConfigV1(
            enabled=True,
            scope_attestation=(
                provider_binding_contract.OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
            ),
            expected_provider_store_binding_sha256=(
                protected_provider_store.binding_sha256
                if protected_provider_store is not None
                else None
            ),
            expected_adapter_contract_sha256=(
                provider_binding_contract.startup_recovery_adapter_contract_sha256_v1()
            ),
        )
    )
    identity_result = identity_binder.bind_offline(
        protected_provider_store_binding=protected_provider_store,
        provider_type=production_provider.ProductionClosedRepairProviderV1,
        adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
    )
    protected_identity = identity_result.get("protected_binding")
    provider_port = bridge_contract.SyntheticProductionStartupRecoveryProviderPortDoubleV1(
        temporary_backend=backend
    )
    bridge = bridge_contract.OfflineProductionProviderStartupRecoveryBridgeV1(
        protected_binding=protected_identity,
        provider_port=provider_port,
        config=bridge_contract.OfflineProductionProviderStartupRecoveryBridgeConfigV1(
            enabled=True,
            scope_attestation=(
                bridge_contract.OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1
            ),
            expected_binding_sha256=(
                protected_identity.binding_sha256
                if protected_identity is not None
                else None
            ),
        ),
    )
    recovery = startup_contract.ResumableStartupRecoveryV2(
        startup_contract.StartupRecoveryConfigV2(
            enabled=True,
            scope_attestation=(
                startup_contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2
            ),
            max_prepared_records=8,
            max_recovery_seconds=120,
        ),
        clock=lambda: SYNTHETIC_NOW_V1 + 1,
    )
    terminal_port = terminal_contract.PhysicalTerminalEvidencePortV2(
        terminal_contract.PhysicalTerminalEvidencePortConfigV2(
            enabled=True,
            scope_attestation=(
                terminal_contract.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2
            ),
            max_completion_window_seconds=120,
        ),
        clock=lambda: SYNTHETIC_NOW_V1 + 2,
    )
    adapter = startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1(
        backend=bridge,
        startup_recovery=recovery,
        terminal_evidence_port=terminal_port,
        config=startup_adapter.OfflineRuntimeStartupRecoveryAdapterConfigV1(
            enabled=True,
            scope_attestation=(
                startup_adapter.OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1
            ),
        ),
    )
    return {
        **provider_values,
        "backend": backend,
        "backend_snapshot": snapshot,
        "provider_store_result": provider_store_result,
        "identity_result": identity_result,
        "protected_identity_binding": protected_identity,
        "provider_port": provider_port,
        "bridge": bridge,
        "adapter": adapter,
    }


def run_synthetic_production_provider_startup_recovery_bridge_harness_v1() -> dict[
    str, Any
]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        values = build_synthetic_production_provider_startup_recovery_bridge_context_v1(
            root
        )
        initial_catalog = values["backend"].list_prepared_transactions_offline()
        result = values["adapter"](
            {
                "state": "QUIESCED",
                "maintenance_epoch": backend_contract.stable_sha256_v2(
                    "synthetic-provider-bridge-maintenance-epoch-v1"
                ),
                "lock_namespace_sha256": values["backend_snapshot"][
                    "lock_namespace_sha256"
                ],
                "registered_writer_count": 19,
                "inflight_mutations": 0,
                "shared_lock_acquired": True,
            }
        )
        final_catalog = values["backend"].list_prepared_transactions_offline()
        final_audit = values["backend"].inspect_transaction_log_offline()
        bridge_counters = values["bridge"].counters()
        port_counters = values["provider_port"].counters()
        store_counters = values["store_double"].counters()
        all_capabilities_exercised = bool(
            all(count > 0 for count in bridge_counters.values())
            and all(count > 0 for count in port_counters.values())
        )
        safe = bool(
            values["provider_store_result"].get("ok") is True
            and values["identity_result"].get("ok") is True
            and initial_catalog.get("prepared_count") == 2
            and result.get("ok") is True
            and result.get("prepared_transactions_before") == 2
            and result.get("prepared_transactions_after") == 0
            and result.get("unresolved_transactions_after") == 0
            and final_catalog.get("prepared_count") == 0
            and final_audit.get("unresolved_prepared_count") == 0
            and final_audit.get("unresolved_resolved_count") == 0
            and all_capabilities_exercised
            and bridge_counters
            == {
                "snapshot_offline": 2,
                "list_prepared_transactions_offline": 2,
                "inspect_transaction_log_offline": 2,
                "reconcile_attested_transaction_offline": 2,
            }
            and store_counters
            == {"apply_call_count": 0, "recovery_call_count": 0}
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("no_order_sent") is True
            and result.get("runtime_integrated") is False
            and result.get("activation_allowed") is False
            and result.get("live_allowed") is False
        )
        return {
            "ok": safe,
            "status": (
                "C3_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_HARNESS_PASSED_OFFLINE"
                if safe
                else "C3_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_HARNESS_FAILED_CLOSED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_OFFLINE_HARNESS_V1_VERSION,
            "initial_prepared_count": initial_catalog.get("prepared_count"),
            "final_prepared_count": final_catalog.get("prepared_count"),
            "final_resolved_count": final_audit.get(
                "unresolved_resolved_count"
            ),
            "all_four_bridge_capabilities_exercised": all_capabilities_exercised,
            "bridge_counters": bridge_counters,
            "provider_port_double_counters": port_counters,
            "production_store_apply_call_count": store_counters[
                "apply_call_count"
            ],
            "production_store_recovery_call_count": store_counters[
                "recovery_call_count"
            ],
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_provider_instantiated": False,
            "production_provider_called": False,
            "production_store_called": False,
            "production_backend_called": False,
            "runtime_integrated": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


__all__ = [
    "SYNTHETIC_NOW_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_production_provider_startup_recovery_bridge_context_v1",
    "run_synthetic_production_provider_startup_recovery_bridge_harness_v1",
]
