"""Temporary-filesystem harness for resumable startup recovery V2."""

from __future__ import annotations

import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as conformance_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_STARTUP_RECOVERY_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-STARTUP-RECOVERY-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_810_000


def run_resumable_startup_recovery_harness_v2() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
            root,
            enabled=True,
            scope_attestation=physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "startup-recovery-source"}
        )
        for index in range(2):
            request = backend.build_transaction_request_offline(
                {
                    "closed_trades": [],
                    "fixture": f"startup-recovery-candidate-{index}",
                },
                label=f"startup-recovery-prepared-{index}",
                deadline_epoch=SYNTHETIC_NOW_V2 + 120,
            )
            backend.prepare_interrupted_transaction_offline(request)

        initial_snapshot = backend.snapshot_offline()
        initial_catalog = backend.list_prepared_transactions_offline()
        startup = startup_contract.ResumableStartupRecoveryV2(
            startup_contract.StartupRecoveryConfigV2(
                enabled=True,
                scope_attestation=startup_contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2,
                max_prepared_records=8,
                max_recovery_seconds=120,
            ),
            clock=lambda: SYNTHETIC_NOW_V2 + 1,
        )
        terminal_port = terminal_contract.PhysicalTerminalEvidencePortV2(
            terminal_contract.PhysicalTerminalEvidencePortConfigV2(
                enabled=True,
                scope_attestation=terminal_contract.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2,
                max_completion_window_seconds=120,
            ),
            clock=lambda: SYNTHETIC_NOW_V2 + 2,
        )
        planned = startup.plan_offline(initial_snapshot, initial_catalog)
        state = planned["protected_state"]
        checkpoint_state_sha256s = [state.state_sha256]
        terminal_receipt_sha256s = []

        while not state.complete:
            batch = state.state["recovery_batch"]
            record_hash = batch["item_record_sha256s"][batch["next_index"]]
            record = next(
                item for item in state.state["prepared_catalog"]["records"]
                if item["record_sha256"] == record_hash
            )
            recovery_request = conformance_harness.build_synthetic_recovery_request_v2(
                record, batch, checkpoint_index=batch["next_index"]
            )
            recovery_result = backend.reconcile_attested_transaction_offline(
                recovery_request
            )
            terminal = terminal_port.normalize_recovery_offline(
                snapshot=state.state["backend_snapshot"],
                catalog_record=record,
                batch=batch,
                request=recovery_request,
                result=recovery_result,
            )
            recorded = startup.record_terminal_receipt_offline(
                state, terminal["protected_receipt"]
            )
            state = recorded["protected_state"]
            checkpoint_state_sha256s.append(state.state_sha256)
            terminal_receipt_sha256s.append(terminal["receipt_sha256"])

        final_snapshot = backend.snapshot_offline()
        final_catalog = backend.list_prepared_transactions_offline()
        finalized = startup.finalize_offline(state, final_snapshot, final_catalog)
        completion = finalized.get("protected_completion")
        protected_repr = bool(
            repr(state) == "ProtectedStartupRecoveryStateV2(<protected>)"
            and repr(completion)
            == "ProtectedStartupRecoveryCompletionV2(<protected>)"
        )
        ok = bool(
            planned.get("ok") is True
            and initial_catalog["prepared_count"] == 2
            and len(terminal_receipt_sha256s) == 2
            and len(set(terminal_receipt_sha256s)) == 2
            and len(set(checkpoint_state_sha256s)) == 3
            and state.complete
            and final_catalog["prepared_count"] == 0
            and finalized.get("ok") is True
            and finalized.get("prepared_catalog_drained") is True
            and startup_contract.protected_startup_recovery_completion_valid_v2(
                completion
            )
            and protected_repr
        )
        return {
            "ok": ok,
            "status": (
                "STARTUP_RECOVERY_V2_HARNESS_PASSED_OFFLINE"
                if ok else "STARTUP_RECOVERY_V2_HARNESS_FAILED_CLOSED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_STARTUP_RECOVERY_HARNESS_V2_VERSION,
            "initial_prepared_count": initial_catalog["prepared_count"],
            "terminal_receipt_count": len(terminal_receipt_sha256s),
            "checkpoint_count": len(checkpoint_state_sha256s),
            "all_checkpoints_distinct": len(set(checkpoint_state_sha256s)) == 3,
            "prepared_catalog_drained": final_catalog["prepared_count"] == 0,
            "completion_sha256": finalized.get("completion_sha256"),
            "protected_repr_verified": protected_repr,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "durable": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


__all__ = ["run_resumable_startup_recovery_harness_v2"]
