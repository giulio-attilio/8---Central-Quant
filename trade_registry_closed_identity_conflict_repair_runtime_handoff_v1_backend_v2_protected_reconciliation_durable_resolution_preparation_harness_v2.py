"""Offline harness for non-executable durable resolution preparation V2."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2 as admission_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as resolution_harness_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESOLUTION-PREPARATION-HARNESS-V2"
)
_CHECK_NAMES = (
    "SAME_ADMISSION_INSTANCE_REQUIRED",
    "CURRENT_DURABLE_ISSUED_RECORD_REVALIDATED",
    "FRESH_QUIESCED_LEASE_REVALIDATED_LIVE",
    "TERMINAL_EVIDENCE_EXACTLY_BOUND",
    "RECONSTRUCTED_ADMISSION_INSTANCE_REJECTED",
    "RESEALED_TERMINAL_EVIDENCE_REJECTED",
    "ENDED_LEASE_REJECTED",
    "CONSUMED_DURABLE_AUTHORITY_REJECTED",
    "DEFAULT_OFF_BEFORE_INPUT_INSPECTION",
    "PREPARATION_PROTECTED_AND_NON_EXECUTABLE",
    "NO_REAL_REGISTRY_RUNTIME_NETWORK_BROKER_OR_ORDER",
)


def _sha(value: Any) -> str:
    return hash_v2.stable_sha256_v2(value)


def run_durable_resolution_preparation_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_VERSION,
        "protected_preparation": None,
        "checks": [],
        "check_count": 0,
        "passed_count": 0,
        "temporary_filesystem_accessed": False,
        "temporary_write_executed": False,
        "temporary_storage_removed": False,
        "interprocess_lock_acquired": False,
        "resolver_called": False,
        "barrier_called": False,
        "resolution_executed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        default_off = preparation_v2.DormantDurableResolutionPreparationContractV2().prepare_offline(
            None, None, now_epoch=0
        )
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        root_identity = _sha({"durable-resolution-preparation-root": obligation.obligation_sha256})
        temp_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="c3-durable-resolution-preparation-v2-") as directory:
            temp_path = Path(directory)
            storage = durable_harness_v2._storage(temp_path)
            durable_ledger = durable_harness_v2._ledger(temp_path, storage, root_identity)
            opened = durable_ledger.open_offline()
            issued = durable_ledger.issue_once_offline(
                obligation_sha256=obligation.obligation_sha256,
                obligation_id_sha256=obligation.obligation["obligation_id_sha256"],
                transaction_sha256=obligation.obligation["transaction_sha256"],
                subject_binding_sha256=obligation.obligation_sha256,
                grant_sha256=_sha({"durable-resolution-preparation-grant": obligation.obligation_sha256}),
                issued_at_epoch=now_epoch,
                expires_at_epoch=now_epoch + 240,
            )
            durable_receipt = issued.get("protected_receipt")
            if opened.get("ok") is not True or durable_receipt is None:
                base["reason"] = "DURABLE_AUTHORITY_NOT_ISSUED"
                return base
            components = admission_harness_v2._session_components(
                obligation, "durable-resolution-preparation", now_epoch
            )
            memory_ledger, anchor, issuer, permit, witness, auth_receipt = components
            with witness.hold_offline(permit, expires_at_epoch=now_epoch + 120) as token:
                fresh_authority = resolution_harness_v2._protected_authority(
                    obligation, permit, token, witness, memory_ledger, issuer,
                    anchor, now_epoch, auth_receipt,
                )
                admission_contract = admission_harness_v2._contract(
                    obligation, durable_receipt, fresh_authority, durable_ledger
                )
                admitted = admission_contract.issue_offline(
                    obligation, durable_receipt, fresh_authority, now_epoch=now_epoch
                )
                protected_admission = admitted.get("protected_admission")
                if admitted.get("ok") is not True or protected_admission is None:
                    base["reason"] = admitted.get("reason") or "DURABLE_RESTART_ADMISSION_NOT_ISSUED"
                    return base
                terminal = resolution_harness_v2._terminal_evidence(
                    obligation, fresh_authority, now_epoch, "COMMITTED"
                )
                contract = preparation_v2.DormantDurableResolutionPreparationContractV2(
                    preparation_v2.DormantDurableResolutionPreparationConfigV2(
                        enabled=True,
                        scope_attestation=preparation_v2.OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2,
                        expected_admission_sha256=protected_admission.admission_sha256,
                        expected_obligation_sha256=obligation.obligation_sha256,
                        expected_durable_record_sha256=durable_receipt.receipt["record_sha256"],
                        expected_terminal_evidence_sha256=terminal["evidence_sha256"],
                    ),
                    protected_admission=protected_admission,
                    durable_authority_ledger=durable_ledger,
                )
                prepared = contract.prepare_offline(
                    protected_admission, terminal, now_epoch=now_epoch
                )
                protected_preparation = prepared.get("protected_preparation")
                if prepared.get("ok") is not True or protected_preparation is None:
                    base["reason"] = prepared.get("reason") or "DURABLE_RESOLUTION_PREPARATION_NOT_ISSUED"
                    return base
                reconstructed = admission_v2.ProtectedDurableRestartAdmissionV2(
                    obligation=protected_admission.obligation,
                    durable_authority_receipt=protected_admission.durable_authority_receipt,
                    fresh_authority=protected_admission.fresh_authority,
                    admission=protected_admission.admission,
                    admission_sha256=protected_admission.admission_sha256,
                )
                reconstructed_result = contract.prepare_offline(
                    reconstructed, terminal, now_epoch=now_epoch
                )
                altered_terminal = resolution_harness_v2._reseal_terminal(
                    terminal, terminal_state="ABORTED"
                )
                altered_terminal_result = contract.prepare_offline(
                    protected_admission, altered_terminal, now_epoch=now_epoch
                )
            ended_lease = contract.prepare_offline(
                protected_admission, terminal, now_epoch=now_epoch
            )
            consumed = durable_ledger.consume_once_offline(
                durable_receipt,
                terminal_evidence_sha256=terminal["evidence_sha256"],
                consumed_at_epoch=now_epoch + 1,
            )
            consumed_result = contract.prepare_offline(
                protected_admission, terminal, now_epoch=now_epoch + 1
            )
            record = protected_preparation.preparation
            checks_by_name = {
                "SAME_ADMISSION_INSTANCE_REQUIRED": prepared["exact_admission_instance_verified"] is True and protected_preparation.protected_admission is protected_admission,
                "CURRENT_DURABLE_ISSUED_RECORD_REVALIDATED": prepared["durable_authority_currently_issued_verified"] is True and record["durable_record_sha256"] == durable_receipt.receipt["record_sha256"],
                "FRESH_QUIESCED_LEASE_REVALIDATED_LIVE": prepared["fresh_quiesced_lease_currently_live_verified"] is True and permit.state == "QUIESCED" and permit.registered_writer_count == 19 and permit.inflight_mutations == 0,
                "TERMINAL_EVIDENCE_EXACTLY_BOUND": prepared["terminal_evidence_verified"] is True and record["terminal_evidence_sha256"] == terminal["evidence_sha256"],
                "RECONSTRUCTED_ADMISSION_INSTANCE_REJECTED": reconstructed_result["ok"] is False and reconstructed_result["reason"] == "DURABLE_RESTART_ADMISSION_INSTANCE_NOT_PINNED",
                "RESEALED_TERMINAL_EVIDENCE_REJECTED": altered_terminal_result["ok"] is False and altered_terminal_result["reason"] == "TERMINAL_RESOLUTION_EVIDENCE_NOT_PINNED",
                "ENDED_LEASE_REJECTED": ended_lease["ok"] is False and ended_lease["reason"] == "FRESH_QUIESCED_RECONCILIATION_LEASE_NOT_LIVE",
                "CONSUMED_DURABLE_AUTHORITY_REJECTED": consumed["ok"] is True and consumed_result["ok"] is False and consumed_result["reason"] == "DURABLE_AUTHORITY_NOT_CURRENTLY_ISSUED",
                "DEFAULT_OFF_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "DURABLE_RESOLUTION_PREPARATION_V2_DEFAULT_OFF" and default_off["temporary_filesystem_accessed"] is False,
                "PREPARATION_PROTECTED_AND_NON_EXECUTABLE": preparation_v2.protected_durable_resolution_preparation_valid_v2(protected_preparation) and repr(protected_preparation) == "ProtectedDurableResolutionPreparationV2(<protected>)" and record["resolver_call_allowed"] is False and record["resolution_executed"] is False and record["durable_authority_consumed"] is False,
                "NO_REAL_REGISTRY_RUNTIME_NETWORK_BROKER_OR_ORDER": all(prepared[key] is False for key in ("real_registry_accessed", "network_accessed", "broker_called", "runtime_integrated", "activation_allowed", "live_allowed", "resolver_called", "barrier_called", "resolution_executed")) and prepared["no_order_sent"] is True,
            }
            base.update(
                {
                    "temporary_filesystem_accessed": True,
                    "temporary_write_executed": True,
                    "interprocess_lock_acquired": True,
                }
            )
        removed = temp_path is not None and not temp_path.exists()
        checks = [
            {"name": name, "passed": checks_by_name.get(name) is True}
            for name in _CHECK_NAMES
        ]
        passed_count = sum(item["passed"] for item in checks)
        ok = passed_count == len(_CHECK_NAMES) and removed
        base.update(
            {
                "ok": ok,
                "status": "DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_PASSED" if ok else "DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_FAILED_CLOSED",
                "reason": None if ok else "ONE_OR_MORE_CHECKS_FAILED",
                "protected_preparation": protected_preparation,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": passed_count,
                "temporary_storage_removed": removed,
            }
        )
        return base
    except Exception as exc:
        base["reason"] = f"HARNESS_EXCEPTION:{type(exc).__name__}"
        return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_PREPARATION_HARNESS_V2_VERSION",
    "run_durable_resolution_preparation_harness_v2",
]
