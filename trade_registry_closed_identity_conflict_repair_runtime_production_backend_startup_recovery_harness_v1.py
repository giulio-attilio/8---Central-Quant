"""Memory-only harness for deterministic C3 startup recovery."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_contract_v1 as recovery_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_contract_v1 as receipt_port
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_harness_v1 as receipt_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as binding_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-STARTUP-RECOVERY-HARNESS-V1"
)
_NOW = 2_000_000_100


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_prepared_record_v1(
    protected_binding,
    *,
    index: int,
    prepared_at_epoch: int = _NOW - 100,
) -> dict[str, Any]:
    record = {
        "record_version": recovery_contract.SYNTHETIC_PREPARED_RECOVERY_RECORD_VERSION_V1,
        "binding_sha256": protected_binding.binding_sha256,
        "request_sha256": _sha256_text(f"synthetic-startup-request-{index}"),
        "transaction_sha256": _sha256_text(
            f"synthetic-startup-transaction-{index}"
        ),
        "original_invocation_command_sha256": _sha256_text(
            f"synthetic-startup-original-command-{index}"
        ),
        "backend_instance_sha256": protected_binding.binding[
            "backend_instance_sha256"
        ],
        "source_raw_document_sha256": _sha256_text(
            f"synthetic-startup-source-document-{index}"
        ),
        "candidate_raw_document_sha256": _sha256_text(
            f"synthetic-startup-candidate-document-{index}"
        ),
        "prepared_record_sha256": _sha256_text(
            f"synthetic-startup-prepared-record-{index}"
        ),
        "previous_maintenance_epoch": _sha256_text(
            f"synthetic-startup-previous-maintenance-{index}"
        ),
        "prepared_at_epoch": prepared_at_epoch,
        "terminal_state": "PREPARED",
        "terminal_receipt_sha256": None,
        "resolved_at_epoch": None,
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
    }
    record["record_sha256"] = recovery_contract.prepared_recovery_record_sha256_v1(
        record
    )
    return record


def build_synthetic_startup_recovery_context_v1(
    *,
    prepared_count: int = 2,
) -> dict[str, Any]:
    binding_values = (
        binding_harness.build_synthetic_provider_store_adapter_binding_context_v1()
    )
    binding_result = binding_values["binding_contract"].bind_offline(
        provider_projection=binding_values["provider_projection"],
        store_projection=binding_values["store_projection"],
        adapter_snapshot=binding_values["adapter_snapshot"],
    )
    protected_binding = binding_result["protected_binding"]
    ledger = recovery_contract.InMemorySyntheticPreparedRecoveryLedgerV1(
        binding_sha256=protected_binding.binding_sha256
    )
    for index in range(prepared_count):
        ledger.seed_prepared_offline(
            build_synthetic_prepared_record_v1(
                protected_binding,
                index=index,
            )
        )
    initial_snapshot = ledger.snapshot()
    startup_recovery = recovery_contract.DormantProductionBackendStartupRecoveryV1(
        config=recovery_contract.DormantProductionBackendStartupRecoveryConfigV1(
            enabled=True,
            scope_attestation=recovery_contract.OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1,
            expected_binding_sha256=protected_binding.binding_sha256,
            expected_initial_ledger_snapshot_sha256=initial_snapshot[
                "snapshot_sha256"
            ],
            max_prepared_records=64,
            max_recovery_seconds=120,
        ),
        ledger=ledger,
    )
    terminal_port = receipt_port.DormantProductionBackendTerminalReceiptPortV1(
        config=receipt_port.DormantProductionBackendTerminalReceiptPortConfigV1(
            enabled=True,
            scope_attestation=receipt_port.OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1,
            expected_binding_sha256=protected_binding.binding_sha256,
            max_completion_window_seconds=60,
        )
    )
    return {
        **binding_values,
        "binding_result": binding_result,
        "protected_binding": protected_binding,
        "ledger": ledger,
        "initial_ledger_snapshot": initial_snapshot,
        "startup_recovery": startup_recovery,
        "terminal_receipt_port": terminal_port,
    }


def build_synthetic_recovery_receipt_for_plan_item_v1(
    values: dict[str, Any],
    item: dict[str, Any],
    *,
    terminal_state: str = "COMMITTED",
    now_epoch: int = _NOW,
):
    evidence = receipt_harness.build_synthetic_terminal_evidence_v1(
        values["protected_binding"],
        operation="RECOVERY",
        terminal_state=terminal_state,
        now_epoch=now_epoch,
        deadline_epoch=now_epoch + 30,
    )
    transaction_sha = item["transaction_sha256"]
    evidence.update(
        command_sha256=_sha256_text(
            f"synthetic-startup-recovery-command-{transaction_sha}"
        ),
        original_invocation_command_sha256=item[
            "original_invocation_command_sha256"
        ],
        request_sha256=item["request_sha256"],
        transaction_sha256=transaction_sha,
        backend_instance_sha256=item["backend_instance_sha256"],
        authorization_consumption_receipt_sha256=_sha256_text(
            f"synthetic-startup-recovery-authorization-{transaction_sha}"
        ),
        previous_maintenance_epoch=item["previous_maintenance_epoch"],
        maintenance_epoch=_sha256_text(
            f"synthetic-startup-fresh-maintenance-{transaction_sha}"
        ),
        source_raw_document_sha256=item["source_raw_document_sha256"],
        candidate_raw_document_sha256=item["candidate_raw_document_sha256"],
        prepared_record_sha256=item["prepared_record_sha256"],
        terminal_record_sha256=_sha256_text(
            f"synthetic-startup-terminal-{terminal_state}-{transaction_sha}"
        ),
    )
    evidence["evidence_sha256"] = receipt_port.backend_terminal_evidence_sha256_v1(
        evidence
    )
    result = values["terminal_receipt_port"].normalize_recovery_offline(
        protected_binding=values["protected_binding"],
        terminal_evidence=evidence,
        now_epoch=now_epoch,
    )
    if result.get("ok") is not True:
        raise RuntimeError("synthetic recovery receipt construction failed")
    return result["protected_terminal_receipt"]


def run_synthetic_backend_startup_recovery_harness_v1() -> dict[str, Any]:
    values = build_synthetic_startup_recovery_context_v1(prepared_count=2)
    planned = values["startup_recovery"].plan_startup_recovery_offline(
        protected_binding=values["protected_binding"],
        now_epoch=_NOW,
    )
    plan = planned["protected_recovery_plan"]
    receipts = [
        build_synthetic_recovery_receipt_for_plan_item_v1(values, item)
        for item in reversed(plan.plan["items"])
    ]
    before_failed_batch = values["ledger"].snapshot()
    incomplete = values["startup_recovery"].reconcile_startup_recovery_offline(
        protected_binding=values["protected_binding"],
        protected_plan=plan,
        protected_receipts=receipts[:-1],
        now_epoch=_NOW + 1,
    )
    after_failed_batch = values["ledger"].snapshot()
    reconciled = values[
        "startup_recovery"
    ].reconcile_startup_recovery_offline(
        protected_binding=values["protected_binding"],
        protected_plan=plan,
        protected_receipts=receipts,
        now_epoch=_NOW + 1,
    )
    replay = values["startup_recovery"].reconcile_startup_recovery_offline(
        protected_binding=values["protected_binding"],
        protected_plan=plan,
        protected_receipts=receipts,
        now_epoch=_NOW + 2,
    )
    counters = values["store_double"].counters()
    final_snapshot = reconciled.get("final_ledger_snapshot", {})
    safe = bool(
        planned.get("ok") is True
        and plan.prepared_count == 2
        and recovery_contract.protected_startup_recovery_plan_valid_v1(plan)
        and incomplete.get("ok") is False
        and incomplete.get("reasons") == ["COMPLETE_RECOVERY_RECEIPT_SET_REQUIRED"]
        and before_failed_batch["snapshot_sha256"]
        == after_failed_batch["snapshot_sha256"]
        and reconciled.get("ok") is True
        and reconciled.get("atomic_batch_verified") is True
        and final_snapshot.get("prepared_count") == 0
        and final_snapshot.get("terminal_count") == 2
        and replay.get("ok") is False
        and replay.get("reasons")
        == ["STARTUP_RECOVERY_LEDGER_CHANGED_SINCE_PLAN"]
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
    )
    return {
        "ok": safe,
        "status": (
            "C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_HARNESS_V1_VERSION,
        "prepared_records_planned_synthetic": plan.prepared_count,
        "deterministic_plan_verified_synthetic": planned.get(
            "all_prepared_records_planned"
        )
        is True,
        "incomplete_batch_failed_closed_synthetic": incomplete.get("ok") is False,
        "failed_batch_left_ledger_unchanged_synthetic": before_failed_batch[
            "snapshot_sha256"
        ]
        == after_failed_batch["snapshot_sha256"],
        "atomic_recovery_batch_verified_synthetic": reconciled.get(
            "atomic_batch_verified"
        )
        is True,
        "startup_clean_synthetic": reconciled.get("startup_clean") is True,
        "stale_plan_replay_rejected_synthetic": replay.get("ok") is False,
        "durability_verified": False,
        "store_double_apply_call_count": counters["apply_call_count"],
        "store_double_recovery_call_count": counters["recovery_call_count"],
        "production_authority": False,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_HARNESS_V1_VERSION",
    "build_synthetic_prepared_record_v1",
    "build_synthetic_recovery_receipt_for_plan_item_v1",
    "build_synthetic_startup_recovery_context_v1",
    "run_synthetic_backend_startup_recovery_harness_v1",
]
