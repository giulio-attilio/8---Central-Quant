"""Memory-only harness for the synthetic evidence reference builder."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1 as scope_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1 as ports_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as builder
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_harness_v1 as conformance_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-REFERENCE-BUILDER-OFFLINE-HARNESS-V1"
)


def _raw_terminal_receipt(transaction_sha256: str, source_state: str) -> dict[str, Any]:
    value = {
        "raw_version": builder.SYNTHETIC_RAW_TERMINAL_RECEIPT_VERSION_V1,
        "transaction_sha256": transaction_sha256,
        "source_state": source_state,
        "synthetic_only": True,
    }
    value["raw_receipt_sha256"] = builder.synthetic_raw_terminal_receipt_sha256_v1(
        value
    )
    return value


def build_synthetic_evidence_reference_builder_context_v1() -> dict[str, Any]:
    values = (
        scope_harness_v1.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
    )
    scope_result = values["scope_contract"].bind_offline(
        protected_batch_session=values["protected_batch_session"],
        protected_evidence_schema=values["protected_schema"],
    )
    protected_scope = scope_result.get("protected_scope_binding")
    if scope_result.get("ok") is not True or protected_scope is None:
        raise ValueError("synthetic protected scope unavailable")
    source_bundle = conformance_harness_v1.build_scope_compatible_synthetic_evidence_bundle_v1(
        protected_scope
    )
    artifacts = {
        key: source_bundle[key]
        for key in (
            "initial_backend_snapshot",
            "initial_transaction_log_audit",
            "initial_prepared_catalog",
            "initial_resolved_catalog",
            "final_backend_snapshot",
            "final_transaction_log_audit",
            "final_prepared_catalog",
            "final_resolved_catalog",
        )
    }
    scope = protected_scope.binding
    capability_probe = {
        "probe_version": builder.SYNTHETIC_CAPABILITY_PROBE_VERSION_V1,
        "schema_sha256": scope["schema_sha256"],
        "backend_instance_sha256": scope["backend_instance_sha256"],
        "backend_snapshot_sha256": artifacts["initial_backend_snapshot"][
            "snapshot_sha256"
        ],
        "maintenance_epoch": scope["maintenance_epoch"],
        "maintenance_lease_receipt_sha256": scope[
            "candidate_maintenance_lease_receipt_sha256"
        ],
        "authenticated_authority_receipt_sha256": scope[
            "candidate_authenticated_authority_receipt_sha256"
        ],
        "writers_blocked_entire_window": True,
        "fsync_capability_verified": False,
        "durable": False,
        "production_evidence": False,
        "synthetic_only": True,
    }
    capability_probe["probe_receipt_sha256"] = (
        builder.synthetic_capability_probe_receipt_sha256_v1(capability_probe)
    )
    read_port = builder.InMemorySyntheticEvidenceReadPortV1(
        artifacts=artifacts, capability_probe=capability_probe
    )
    normalizer = builder.InMemorySyntheticTerminalReceiptNormalizerV1(
        terminal_receipts=source_bundle["terminal_receipts"]
    )
    ports_contract = ports_harness_v1.make_synthetic_evidence_builder_ports_contract_v1(
        scope_binding_sha256=protected_scope.binding_sha256,
        evidence_read_port=read_port,
        terminal_normalizer_port=normalizer,
    )
    ports_result = ports_contract.bind_offline(
        protected_scope_binding=protected_scope,
        evidence_read_port=read_port,
        terminal_normalizer_port=normalizer,
    )
    protected_ports = ports_result.get("protected_port_binding")
    if ports_result.get("ok") is not True or protected_ports is None:
        raise ValueError("synthetic protected builder ports unavailable")
    raw_receipts = [
        _raw_terminal_receipt(
            item["transaction_sha256"], item["source_state"]
        )
        for item in scope["pending_items"]
    ]
    reference_builder = builder.OfflineStartupRecoveryEvidenceReferenceBuilderV1(
        config=builder.OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1(
            enabled=True,
            scope_attestation=(
                builder.OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1
            ),
            expected_port_binding_sha256=protected_ports.binding_sha256,
            max_pending_items=len(raw_receipts),
        )
    )
    return {
        **values,
        "scope_result": scope_result,
        "protected_scope_binding": protected_scope,
        "source_bundle": source_bundle,
        "capability_probe": capability_probe,
        "evidence_read_port": read_port,
        "terminal_normalizer_port": normalizer,
        "ports_contract": ports_contract,
        "ports_result": ports_result,
        "protected_port_binding": protected_ports,
        "raw_terminal_receipts": raw_receipts,
        "reference_builder": reference_builder,
    }


def run_synthetic_evidence_reference_builder_harness_v1() -> dict[str, Any]:
    values = build_synthetic_evidence_reference_builder_context_v1()
    result = values["reference_builder"].build_offline(
        protected_port_binding=values["protected_port_binding"],
        raw_terminal_receipts=values["raw_terminal_receipts"],
    )
    bundle = result.get("fixture_bundle") or {}
    read_counts = values["evidence_read_port"].counters()
    normalizer_count = values["terminal_normalizer_port"].call_count
    safe = bool(
        result.get("ok") is True
        and result.get("port_binding_verified") is True
        and result.get("raw_receipts_verified") is True
        and result.get("initial_evidence_collected") is True
        and result.get("terminal_receipts_normalized") is True
        and result.get("final_evidence_collected") is True
        and result.get("synthetic_bundle_created") is True
        and result.get("scope_aware_conformance_verified") is True
        and bundle.get("bundle_sha256") == values["source_bundle"]["bundle_sha256"]
        and read_counts
        == {"snapshot": 2, "audit": 2, "prepared": 2, "resolved": 2, "probe": 1}
        and normalizer_count == len(values["raw_terminal_receipts"])
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("production_evidence") is False
        and result.get("production_authority") is False
        and result.get("runtime_integrated") is False
        and result.get("live_allowed") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_HARNESS_V1_VERSION,
        "read_port_calls": sum(read_counts.values()),
        "normalizer_port_calls": normalizer_count,
        "bundle_matches_independent_oracle": bundle.get("bundle_sha256")
        == values["source_bundle"]["bundle_sha256"],
        "scope_aware_conformance_verified": result.get(
            "scope_aware_conformance_verified"
        )
        is True,
        "synthetic_bundle_created": result.get("synthetic_bundle_created") is True,
        "production_evidence": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_evidence_reference_builder_context_v1",
    "run_synthetic_evidence_reference_builder_harness_v1",
]
