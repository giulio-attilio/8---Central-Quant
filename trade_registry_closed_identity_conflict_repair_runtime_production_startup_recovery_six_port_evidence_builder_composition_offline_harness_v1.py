"""Synthetic harness for the protected six-port builder composition."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_v1 as composition_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_harness_v1 as normalizer_harness_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-SIX-PORT-EVIDENCE-BUILDER-COMPOSITION-"
    "OFFLINE-HARNESS-V1"
)


def make_synthetic_six_port_evidence_builder_composition_v1(
    *, protected_adapter_plan: Any, read_adapter: Any, terminal_normalizer: Any
) -> composition_v1.OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1:
    return composition_v1.OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1(
        config=composition_v1.OfflineStartupRecoverySixPortEvidenceBuilderCompositionConfigV1(
            enabled=True,
            scope_attestation=(
                composition_v1.OFFLINE_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_SCOPE_ATTESTATION_V1
            ),
            expected_adapter_plan_sha256=protected_adapter_plan.plan_sha256,
            expected_read_adapter_object_identity_sha256=(
                ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    read_adapter
                )
            ),
            expected_normalizer_object_identity_sha256=(
                ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    terminal_normalizer
                )
            ),
        )
    )


def build_synthetic_six_port_evidence_builder_composition_context_v1() -> dict[
    str, Any
]:
    values = normalizer_harness_v1.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
    composition = make_synthetic_six_port_evidence_builder_composition_v1(
        protected_adapter_plan=values["protected_adapter_plan"],
        read_adapter=values["reference_adapter"],
        terminal_normalizer=values["normalizer_reference"],
    )
    return {**values, "six_port_composition": composition}


def run_synthetic_six_port_evidence_builder_composition_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_six_port_evidence_builder_composition_context_v1()
    result = values["six_port_composition"].compose_offline(
        protected_adapter_plan=values["protected_adapter_plan"],
        read_adapter=values["reference_adapter"],
        terminal_normalizer=values["normalizer_reference"],
        raw_terminal_receipts=values["raw_terminal_receipts"],
    )
    bundle = result.get("fixture_bundle") or {}
    source_bundle = values["source_bundle"]
    safe = bool(
        result.get("ok") is True
        and result.get("dependencies_verified") is True
        and result.get("raw_receipts_verified") is True
        and result.get("protected_reads_completed") is True
        and result.get("protected_normalization_completed") is True
        and result.get("canonical_replay_bound") is True
        and result.get("evidence_builder_called") is True
        and result.get("bundle_created") is True
        and result.get("bundle_matches_protected_collection") is True
        and result.get("scope_aware_conformance_verified") is True
        and result.get("protected_read_count") == 9
        and result.get("protected_normalizer_call_count")
        == len(values["raw_terminal_receipts"])
        and result.get("replay_read_count") == 9
        and result.get("replay_normalizer_call_count")
        == len(values["raw_terminal_receipts"])
        and bundle.get("bundle_sha256") == source_bundle["bundle_sha256"]
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
            "C3_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_HARNESS_V1_VERSION,
        "protected_read_count": result.get("protected_read_count", 0),
        "protected_normalizer_call_count": result.get(
            "protected_normalizer_call_count", 0
        ),
        "replay_read_count": result.get("replay_read_count", 0),
        "replay_normalizer_call_count": result.get(
            "replay_normalizer_call_count", 0
        ),
        "bundle_matches_independent_oracle": bundle.get("bundle_sha256")
        == source_bundle["bundle_sha256"],
        "scope_aware_conformance_verified": result.get(
            "scope_aware_conformance_verified"
        )
        is True,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_six_port_evidence_builder_composition_context_v1",
    "make_synthetic_six_port_evidence_builder_composition_v1",
    "run_synthetic_six_port_evidence_builder_composition_harness_v1",
]
