"""In-memory harness for the dormant recovery-evidence builder ports."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1 as scope_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-BUILDER-PORTS-HARNESS-V1"
)


class SyntheticEvidenceReadPortDoubleV1:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(self) -> None:
        self._counts = {
            "snapshot": 0,
            "audit": 0,
            "prepared": 0,
            "resolved": 0,
            "probe": 0,
        }

    def read_backend_snapshot_offline(self, *_args, **_kwargs):
        self._counts["snapshot"] += 1
        raise AssertionError("dormant port binding must not read snapshot")

    def read_transaction_log_audit_offline(self, *_args, **_kwargs):
        self._counts["audit"] += 1
        raise AssertionError("dormant port binding must not read audit")

    def read_prepared_catalog_offline(self, *_args, **_kwargs):
        self._counts["prepared"] += 1
        raise AssertionError("dormant port binding must not read prepared catalog")

    def read_resolved_catalog_offline(self, *_args, **_kwargs):
        self._counts["resolved"] += 1
        raise AssertionError("dormant port binding must not read resolved catalog")

    def read_backend_capability_probe_offline(self, *_args, **_kwargs):
        self._counts["probe"] += 1
        raise AssertionError("dormant port binding must not read capability probe")

    def counters(self) -> dict[str, int]:
        return dict(self._counts)

    def __repr__(self) -> str:
        return "SyntheticEvidenceReadPortDoubleV1(<protected>)"


class SyntheticTerminalReceiptNormalizerPortDoubleV1:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(self) -> None:
        self._call_count = 0

    def normalize_terminal_receipt_offline(self, *_args, **_kwargs):
        self._call_count += 1
        raise AssertionError("dormant port binding must not normalize receipts")

    @property
    def call_count(self) -> int:
        return self._call_count

    def __repr__(self) -> str:
        return "SyntheticTerminalReceiptNormalizerPortDoubleV1(<protected>)"


def make_synthetic_evidence_builder_ports_contract_v1(
    *,
    scope_binding_sha256: str,
    evidence_read_port: Any,
    terminal_normalizer_port: Any,
) -> contract.DormantStartupRecoveryEvidenceBuilderPortsContractV1:
    return contract.DormantStartupRecoveryEvidenceBuilderPortsContractV1(
        config=contract.DormantStartupRecoveryEvidenceBuilderPortsConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1
            ),
            expected_scope_binding_sha256=scope_binding_sha256,
            expected_read_port_object_identity_sha256=(
                contract.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    evidence_read_port
                )
            ),
            expected_normalizer_port_object_identity_sha256=(
                contract.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    terminal_normalizer_port
                )
            ),
        )
    )


def build_synthetic_evidence_builder_ports_context_v1() -> dict[str, Any]:
    values = (
        scope_harness_v1.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
    )
    scope_result = values["scope_contract"].bind_offline(
        protected_batch_session=values["protected_batch_session"],
        protected_evidence_schema=values["protected_schema"],
    )
    protected_scope = scope_result.get("protected_scope_binding")
    if scope_result.get("ok") is not True or protected_scope is None:
        raise ValueError("synthetic protected evidence scope unavailable")
    read_port = SyntheticEvidenceReadPortDoubleV1()
    normalizer_port = SyntheticTerminalReceiptNormalizerPortDoubleV1()
    ports_contract = make_synthetic_evidence_builder_ports_contract_v1(
        scope_binding_sha256=protected_scope.binding_sha256,
        evidence_read_port=read_port,
        terminal_normalizer_port=normalizer_port,
    )
    return {
        **values,
        "scope_result": scope_result,
        "protected_scope_binding": protected_scope,
        "evidence_read_port": read_port,
        "terminal_normalizer_port": normalizer_port,
        "ports_contract": ports_contract,
    }


def run_synthetic_evidence_builder_ports_harness_v1() -> dict[str, Any]:
    values = build_synthetic_evidence_builder_ports_context_v1()
    result = values["ports_contract"].bind_offline(
        protected_scope_binding=values["protected_scope_binding"],
        evidence_read_port=values["evidence_read_port"],
        terminal_normalizer_port=values["terminal_normalizer_port"],
    )
    protected = result.get("protected_port_binding")
    binding = protected.binding if protected is not None else {}
    read_counts = values["evidence_read_port"].counters()
    normalize_count = values["terminal_normalizer_port"].call_count
    safe = bool(
        result.get("ok") is True
        and result.get("scope_binding_verified") is True
        and result.get("read_port_verified") is True
        and result.get("normalizer_port_verified") is True
        and result.get("port_instances_bound") is True
        and contract.protected_startup_recovery_evidence_builder_port_binding_valid_v1(
            protected
        )
        and binding.get("complete_prepared_catalog_required") is True
        and binding.get("complete_resolved_catalog_required") is True
        and binding.get("backend_capability_probe_required") is True
        and binding.get("terminal_receipt_normalization_required") is True
        and binding.get("exact_scope_cross_binding_required") is True
        and binding.get("ports_called") is False
        and binding.get("evidence_created") is False
        and binding.get("evidence_builder_available") is False
        and binding.get("runtime_integrated") is False
        and binding.get("live_allowed") is False
        and read_counts
        == {"snapshot": 0, "audit": 0, "prepared": 0, "resolved": 0, "probe": 0}
        and normalize_count == 0
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
            "C3_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_HARNESS_V1_VERSION,
        "all_port_surfaces_bound": all(
            binding.get(field_name) is True
            for field_name in (
                "complete_prepared_catalog_required",
                "complete_resolved_catalog_required",
                "backend_capability_probe_required",
                "terminal_receipt_normalization_required",
            )
        ),
        "read_port_calls": sum(read_counts.values()),
        "normalizer_port_calls": normalize_count,
        "evidence_created": False,
        "evidence_builder_available": False,
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
    "SyntheticEvidenceReadPortDoubleV1",
    "SyntheticTerminalReceiptNormalizerPortDoubleV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_HARNESS_V1_VERSION",
    "build_synthetic_evidence_builder_ports_context_v1",
    "make_synthetic_evidence_builder_ports_contract_v1",
    "run_synthetic_evidence_builder_ports_harness_v1",
]
