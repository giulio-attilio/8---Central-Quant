"""Synthetic harness for the default-off evidence read-port reference adapter."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_harness_v1 as plan_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_v1 as adapter_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_harness_v1 as reference_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-READ-PORT-REFERENCE-ADAPTER-"
    "OFFLINE-HARNESS-V1"
)


def make_synthetic_evidence_read_port_reference_adapter_v1(
    *, protected_adapter_plan: Any, source_read_port: Any
) -> adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1:
    return adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1(
        protected_adapter_plan=protected_adapter_plan,
        source_read_port=source_read_port,
        config=adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1(
            enabled=True,
            scope_attestation=(
                adapter_v1.OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1
            ),
            expected_adapter_plan_sha256=protected_adapter_plan.plan_sha256,
            expected_source_object_identity_sha256=(
                ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    source_read_port
                )
            ),
        ),
    )


def build_synthetic_evidence_read_port_reference_adapter_context_v1() -> dict[
    str, Any
]:
    values = reference_harness_v1.build_synthetic_evidence_reference_builder_context_v1()
    protected_scope = values["protected_scope_binding"]
    protected_startup_provider = values["protected_identity_binding"]
    protected_provider_store = values["provider_store_result"][
        "protected_binding"
    ]
    plan_contract = plan_harness_v1.make_synthetic_evidence_read_port_adapter_contract_v1(
        scope_binding_sha256=protected_scope.binding_sha256,
        startup_provider_binding_sha256=protected_startup_provider.binding_sha256,
        provider_store_binding_sha256=protected_provider_store.binding_sha256,
    )
    plan_result = plan_contract.project_offline(
        protected_scope_binding=protected_scope,
        protected_startup_provider_binding=protected_startup_provider,
        protected_provider_store_binding=protected_provider_store,
    )
    protected_plan = plan_result.get("protected_adapter_plan")
    if plan_result.get("ok") is not True or protected_plan is None:
        raise ValueError("synthetic protected adapter plan unavailable")
    adapter = make_synthetic_evidence_read_port_reference_adapter_v1(
        protected_adapter_plan=protected_plan,
        source_read_port=values["evidence_read_port"],
    )
    return {
        **values,
        "plan_contract": plan_contract,
        "plan_result": plan_result,
        "protected_adapter_plan": protected_plan,
        "reference_adapter": adapter,
    }


def collect_synthetic_read_port_artifacts_v1(
    adapter: adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1,
) -> dict[str, Any]:
    initial_snapshot = adapter.read_backend_snapshot_offline(phase="INITIAL")
    capability_probe = adapter.read_backend_capability_probe_offline(
        snapshot=initial_snapshot
    )
    initial_audit = adapter.read_transaction_log_audit_offline(
        snapshot=initial_snapshot, phase="INITIAL"
    )
    initial_prepared = adapter.read_prepared_catalog_offline(
        snapshot=initial_snapshot, phase="INITIAL"
    )
    initial_resolved = adapter.read_resolved_catalog_offline(
        snapshot=initial_snapshot, phase="INITIAL"
    )
    final_snapshot = adapter.read_backend_snapshot_offline(phase="FINAL")
    final_audit = adapter.read_transaction_log_audit_offline(
        snapshot=final_snapshot, phase="FINAL"
    )
    final_prepared = adapter.read_prepared_catalog_offline(
        snapshot=final_snapshot, phase="FINAL"
    )
    final_resolved = adapter.read_resolved_catalog_offline(
        snapshot=final_snapshot, phase="FINAL"
    )
    return {
        "initial_backend_snapshot": initial_snapshot,
        "backend_capability_probe": capability_probe,
        "initial_transaction_log_audit": initial_audit,
        "initial_prepared_catalog": initial_prepared,
        "initial_resolved_catalog": initial_resolved,
        "final_backend_snapshot": final_snapshot,
        "final_transaction_log_audit": final_audit,
        "final_prepared_catalog": final_prepared,
        "final_resolved_catalog": final_resolved,
    }


def run_synthetic_evidence_read_port_reference_adapter_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_evidence_read_port_reference_adapter_context_v1()
    adapter = values["reference_adapter"]
    artifacts = collect_synthetic_read_port_artifacts_v1(adapter)
    source = values["source_bundle"]
    expected_artifacts = {
        key: source[key]
        for key in artifacts
        if key != "backend_capability_probe"
    }
    observed_artifacts = {
        key: value
        for key, value in artifacts.items()
        if key != "backend_capability_probe"
    }
    expected_counts = {
        "snapshot": 2,
        "audit": 2,
        "prepared": 2,
        "resolved": 2,
        "probe": 1,
    }
    state = adapter.state_snapshot()
    safe = bool(
        observed_artifacts == expected_artifacts
        and artifacts["backend_capability_probe"] == values["capability_probe"]
        and adapter.counters() == expected_counts
        and values["evidence_read_port"].counters() == expected_counts
        and adapter.completed
        and state["completed"] is True
        and state["read_count"] == 9
        and state["next_step"] is None
        and state["filesystem_accessed"] is False
        and state["real_registry_accessed"] is False
        and state["network_accessed"] is False
        and state["broker_called"] is False
        and state["write_executed"] is False
        and state["registry_write"] is False
        and state["runtime_integrated"] is False
        and state["live_allowed"] is False
        and state["no_order_sent"] is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_HARNESS_V1_VERSION,
        "read_count": state["read_count"],
        "strict_sequence_completed": state["completed"],
        "artifacts_match_independent_oracle": observed_artifacts
        == expected_artifacts,
        "capability_probe_matches_independent_oracle": artifacts[
            "backend_capability_probe"
        ]
        == values["capability_probe"],
        "default_off": True,
        "offline_only": True,
        "memory_only": True,
        "synthetic_only": True,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_evidence_read_port_reference_adapter_context_v1",
    "collect_synthetic_read_port_artifacts_v1",
    "make_synthetic_evidence_read_port_reference_adapter_v1",
    "run_synthetic_evidence_read_port_reference_adapter_harness_v1",
]
