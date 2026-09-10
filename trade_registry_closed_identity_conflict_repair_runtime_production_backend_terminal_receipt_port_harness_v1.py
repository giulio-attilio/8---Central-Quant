"""Synthetic harness for the dormant backend terminal receipt port."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_contract_v1 as port_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as binding_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-TERMINAL-RECEIPT-PORT-HARNESS-V1"
)
_NOW = 2_000_000_000


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_terminal_evidence_v1(
    protected_binding,
    *,
    operation: str,
    terminal_state: str,
    now_epoch: int = _NOW,
    deadline_epoch: int | None = None,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    normalized_operation = str(operation or "").upper().strip()
    normalized_state = str(terminal_state or "").upper().strip()
    binding = protected_binding.binding
    original_command_sha256 = _sha256_text(
        "synthetic-original-invocation-command-v1"
    )
    if normalized_operation == "APPLY":
        command_sha256 = original_command_sha256
        previous_maintenance_epoch = None
        maintenance_epoch = _sha256_text("synthetic-apply-maintenance-epoch-v1")
        authorization_sha256 = _sha256_text(
            "synthetic-apply-authorization-consumption-receipt-v1"
        )
    else:
        command_sha256 = _sha256_text("synthetic-recovery-command-v1")
        previous_maintenance_epoch = _sha256_text(
            "synthetic-apply-maintenance-epoch-v1"
        )
        maintenance_epoch = _sha256_text(
            "synthetic-fresh-recovery-maintenance-epoch-v1"
        )
        authorization_sha256 = _sha256_text(
            "synthetic-recovery-authorization-consumption-receipt-v1"
        )
    ambiguous = normalized_state == "AMBIGUOUS"
    evidence = {
        "evidence_version": port_contract.SYNTHETIC_BACKEND_TERMINAL_EVIDENCE_VERSION_V1,
        "operation": normalized_operation,
        "binding_sha256": protected_binding.binding_sha256,
        "store_projection_sha256": binding["store_projection_sha256"],
        "source_store_snapshot_sha256": binding[
            "source_store_snapshot_sha256"
        ],
        "adapter_snapshot_sha256": binding["adapter_snapshot_sha256"],
        "command_sha256": command_sha256,
        "original_invocation_command_sha256": original_command_sha256,
        "request_sha256": _sha256_text("synthetic-production-request-v1"),
        "transaction_sha256": _sha256_text("synthetic-production-transaction-v1"),
        "backend_instance_sha256": binding["backend_instance_sha256"],
        "authorization_consumption_receipt_sha256": authorization_sha256,
        "previous_maintenance_epoch": previous_maintenance_epoch,
        "maintenance_epoch": maintenance_epoch,
        "source_raw_document_sha256": _sha256_text(
            "synthetic-source-raw-document-v1"
        ),
        "candidate_raw_document_sha256": _sha256_text(
            "synthetic-candidate-raw-document-v1"
        ),
        "terminal_state": normalized_state,
        "prepared_record_sha256": _sha256_text(
            "synthetic-durable-prepared-record-v1"
        ),
        "terminal_record_sha256": _sha256_text(
            f"synthetic-durable-{normalized_operation}-{normalized_state}-record-v1"
        ),
        "postconditions_verified": not ambiguous,
        "recovery_required": ambiguous,
        "ambiguous": ambiguous,
        "idempotent_replay": idempotent_replay,
        "deadline_epoch": deadline_epoch or now_epoch + 30,
        "completed_at_epoch": now_epoch,
        "deadline_observed": True,
        "durability_required": True,
        "durability_verified": False,
        "synthetic_only": True,
        "production_evidence": False,
        "write_executed": False,
        "registry_write": False,
    }
    evidence["evidence_sha256"] = (
        port_contract.backend_terminal_evidence_sha256_v1(evidence)
    )
    return evidence


def build_synthetic_terminal_receipt_port_context_v1() -> dict[str, Any]:
    binding_values = (
        binding_harness.build_synthetic_provider_store_adapter_binding_context_v1()
    )
    binding_result = binding_values["binding_contract"].bind_offline(
        provider_projection=binding_values["provider_projection"],
        store_projection=binding_values["store_projection"],
        adapter_snapshot=binding_values["adapter_snapshot"],
    )
    protected_binding = binding_result["protected_binding"]
    port = port_contract.DormantProductionBackendTerminalReceiptPortV1(
        config=port_contract.DormantProductionBackendTerminalReceiptPortConfigV1(
            enabled=True,
            scope_attestation=port_contract.OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1,
            expected_binding_sha256=protected_binding.binding_sha256,
            max_completion_window_seconds=60,
        )
    )
    return {
        **binding_values,
        "binding_result": binding_result,
        "protected_binding": protected_binding,
        "terminal_receipt_port": port,
    }


def run_synthetic_backend_terminal_receipt_port_harness_v1() -> dict[str, Any]:
    values = build_synthetic_terminal_receipt_port_context_v1()
    protected_binding = values["protected_binding"]
    port = values["terminal_receipt_port"]
    committed_evidence = build_synthetic_terminal_evidence_v1(
        protected_binding,
        operation="APPLY",
        terminal_state="COMMITTED",
    )
    committed = port.normalize_apply_offline(
        protected_binding=protected_binding,
        terminal_evidence=committed_evidence,
        now_epoch=_NOW,
    )
    ambiguous_evidence = build_synthetic_terminal_evidence_v1(
        protected_binding,
        operation="APPLY",
        terminal_state="AMBIGUOUS",
    )
    ambiguous = port.normalize_apply_offline(
        protected_binding=protected_binding,
        terminal_evidence=ambiguous_evidence,
        now_epoch=_NOW,
    )
    recovery_evidence = build_synthetic_terminal_evidence_v1(
        protected_binding,
        operation="RECOVERY",
        terminal_state="COMMITTED",
        idempotent_replay=True,
    )
    recovered = port.normalize_recovery_offline(
        protected_binding=protected_binding,
        terminal_evidence=recovery_evidence,
        now_epoch=_NOW,
    )
    counters = values["store_double"].counters()
    committed_receipt = committed.get("protected_terminal_receipt")
    ambiguous_receipt = ambiguous.get("protected_terminal_receipt")
    recovered_receipt = recovered.get("protected_terminal_receipt")
    safe = bool(
        values["binding_result"].get("ok") is True
        and committed.get("ok") is True
        and committed_receipt.terminal_state == "COMMITTED"
        and ambiguous.get("ok") is True
        and ambiguous_receipt.terminal_state == "AMBIGUOUS"
        and ambiguous_receipt.receipt["adapter_store_result"][
            "recovery_required"
        ]
        is True
        and recovered.get("ok") is True
        and recovered_receipt.operation == "RECOVERY"
        and recovered_receipt.terminal_state == "COMMITTED"
        and recovered_receipt.receipt["adapter_store_result"][
            "idempotent_replay"
        ]
        is True
        and port_contract.protected_backend_terminal_port_receipt_valid_v1(
            committed_receipt
        )
        and port_contract.protected_backend_terminal_port_receipt_valid_v1(
            ambiguous_receipt
        )
        and port_contract.protected_backend_terminal_port_receipt_valid_v1(
            recovered_receipt
        )
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
    )
    return {
        "ok": safe,
        "status": (
            "C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_HARNESS_V1_VERSION,
        "binding_verified_synthetic": committed.get("binding_verified") is True,
        "apply_terminal_normalized_synthetic": committed.get(
            "terminal_contract_normalized"
        )
        is True,
        "ambiguous_apply_requires_recovery_synthetic": ambiguous_receipt.receipt[
            "adapter_store_result"
        ]["recovery_required"]
        is True,
        "recovery_terminal_normalized_synthetic": recovered.get(
            "terminal_contract_normalized"
        )
        is True,
        "fresh_recovery_epoch_verified_synthetic": recovery_evidence[
            "previous_maintenance_epoch"
        ]
        != recovery_evidence["maintenance_epoch"],
        "durability_required": True,
        "durability_verified": False,
        "store_double_apply_call_count": counters["apply_call_count"],
        "store_double_recovery_call_count": counters["recovery_call_count"],
        "production_authority": False,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_HARNESS_V1_VERSION",
    "build_synthetic_terminal_evidence_v1",
    "build_synthetic_terminal_receipt_port_context_v1",
    "run_synthetic_backend_terminal_receipt_port_harness_v1",
]
