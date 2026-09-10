"""Synthetic harness for terminal-receipt normalizer reference V1."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_harness_v1 as read_adapter_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_v1 as normalizer_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-TERMINAL-RECEIPT-NORMALIZER-REFERENCE-"
    "OFFLINE-HARNESS-V1"
)


def make_synthetic_terminal_receipt_normalizer_reference_v1(
    *, protected_adapter_plan: Any, source_normalizer_port: Any
) -> normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1:
    return normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1(
        protected_adapter_plan=protected_adapter_plan,
        source_normalizer_port=source_normalizer_port,
        config=normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1(
            enabled=True,
            scope_attestation=(
                normalizer_v1.OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1
            ),
            expected_adapter_plan_sha256=protected_adapter_plan.plan_sha256,
            expected_source_object_identity_sha256=(
                ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                    source_normalizer_port
                )
            ),
        ),
    )


def build_synthetic_terminal_receipt_normalizer_reference_context_v1() -> dict[
    str, Any
]:
    values = read_adapter_harness_v1.build_synthetic_evidence_read_port_reference_adapter_context_v1()
    normalizer = make_synthetic_terminal_receipt_normalizer_reference_v1(
        protected_adapter_plan=values["protected_adapter_plan"],
        source_normalizer_port=values["terminal_normalizer_port"],
    )
    return {**values, "normalizer_reference": normalizer}


def normalize_synthetic_terminal_receipt_batch_v1(
    normalizer: normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1,
    *,
    raw_terminal_receipts: Any,
    protected_scope_binding: Any,
) -> list[Any]:
    raw_by_transaction = {
        item["transaction_sha256"]: item for item in raw_terminal_receipts
    }
    return [
        normalizer.normalize_terminal_receipt_offline(
            raw_receipt=raw_by_transaction[transaction_sha256],
            protected_scope_binding=protected_scope_binding,
        )
        for transaction_sha256 in sorted(raw_by_transaction)
    ]


def run_synthetic_terminal_receipt_normalizer_reference_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_terminal_receipt_normalizer_reference_context_v1()
    normalizer = values["normalizer_reference"]
    normalized = normalize_synthetic_terminal_receipt_batch_v1(
        normalizer,
        raw_terminal_receipts=values["raw_terminal_receipts"],
        protected_scope_binding=values["protected_scope_binding"],
    )
    receipt_set = normalizer.terminal_receipt_set_snapshot()
    expected = sorted(
        values["source_bundle"]["terminal_receipts"],
        key=lambda item: item["receipt_sha256"],
    )
    state = normalizer.state_snapshot()
    safe = bool(
        sorted(normalized, key=lambda item: item["receipt_sha256"]) == expected
        and receipt_set == expected
        and normalizer.completed
        and normalizer.call_count == len(expected)
        and values["terminal_normalizer_port"].call_count == len(expected)
        and state["completed"] is True
        and state["expected_receipt_count"] == len(expected)
        and state["normalized_receipt_count"] == len(expected)
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
            "C3_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_HARNESS_V1_VERSION,
        "normalized_receipt_count": state["normalized_receipt_count"],
        "batch_sequence_completed": state["completed"],
        "receipt_set_matches_independent_oracle": receipt_set == expected,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_terminal_receipt_normalizer_reference_context_v1",
    "make_synthetic_terminal_receipt_normalizer_reference_v1",
    "normalize_synthetic_terminal_receipt_batch_v1",
    "run_synthetic_terminal_receipt_normalizer_reference_harness_v1",
]
