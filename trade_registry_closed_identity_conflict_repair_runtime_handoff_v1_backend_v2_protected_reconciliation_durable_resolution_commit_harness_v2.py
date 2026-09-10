"""Crash/replay harness for the synthetic atomic durable resolution commit."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import registry_v2_wal as wal_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2 as admission_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2 as commit_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as resolution_harness_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_COMMIT_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESOLUTION-COMMIT-HARNESS-V2"
)
_CHECK_NAMES = (
    "ISSUED_TO_RESOLVED_SINGLE_WAL_MUTATION",
    "CONSUMPTION_AND_RECEIPT_MATERIAL_SHARE_RECORD",
    "CLEAN_REPLAY_RETURNS_IDENTICAL_RECEIPT",
    "DIVERGENT_REPLAY_FAILS_CLOSED",
    "CRASH_AFTER_PREPARED_RECOVERS",
    "AFTER_PREPARED_REPLAY_RETURNS_IDENTICAL_RECEIPT",
    "CRASH_AFTER_REPLACE_RECOVERS",
    "AFTER_REPLACE_REPLAY_RETURNS_IDENTICAL_RECEIPT",
    "RECONSTRUCTED_PREPARATION_INSTANCE_REJECTED",
    "DEFAULT_OFF_BEFORE_INPUT_INSPECTION",
    "NO_LEGACY_RESOLVER_BARRIER_BACKEND_OR_OPERATIONAL_ACCESS",
    "TEMPORARY_STORAGE_REMOVED",
)


def _sha(value: Any) -> str:
    return hash_v2.stable_sha256_v2(value)


def _scenario(root: Path, obligation, label: str, fault_point: str | None):
    now_epoch = obligation.obligation["created_at_epoch"] + 1
    root_identity = _sha({"durable-resolution-commit-root": label})
    storage = durable_harness_v2._storage(root)
    ledger = durable_harness_v2._ledger(root, storage, root_identity)
    opened = ledger.open_offline()
    issued = ledger.issue_once_offline(
        obligation_sha256=obligation.obligation_sha256,
        obligation_id_sha256=obligation.obligation["obligation_id_sha256"],
        transaction_sha256=obligation.obligation["transaction_sha256"],
        subject_binding_sha256=obligation.obligation_sha256,
        grant_sha256=_sha({"durable-resolution-commit-grant": label}),
        issued_at_epoch=now_epoch,
        expires_at_epoch=now_epoch + 240,
    )
    durable_receipt = issued.get("protected_receipt")
    if opened.get("ok") is not True or durable_receipt is None:
        raise RuntimeError("DURABLE_AUTHORITY_NOT_ISSUED")
    components = admission_harness_v2._session_components(obligation, label, now_epoch)
    memory_ledger, anchor, issuer, permit, witness, auth_receipt = components
    with witness.hold_offline(permit, expires_at_epoch=now_epoch + 120) as token:
        fresh_authority = resolution_harness_v2._protected_authority(
            obligation, permit, token, witness, memory_ledger, issuer, anchor,
            now_epoch, auth_receipt,
        )
        admission_contract = admission_harness_v2._contract(
            obligation, durable_receipt, fresh_authority, ledger
        )
        admitted = admission_contract.issue_offline(
            obligation, durable_receipt, fresh_authority, now_epoch=now_epoch
        )
        protected_admission = admitted.get("protected_admission")
        if admitted.get("ok") is not True or protected_admission is None:
            raise RuntimeError("DURABLE_RESTART_ADMISSION_NOT_ISSUED")
        terminal = resolution_harness_v2._terminal_evidence(
            obligation, fresh_authority, now_epoch, "COMMITTED"
        )
        preparation_contract = preparation_v2.DormantDurableResolutionPreparationContractV2(
            preparation_v2.DormantDurableResolutionPreparationConfigV2(
                enabled=True,
                scope_attestation=preparation_v2.OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2,
                expected_admission_sha256=protected_admission.admission_sha256,
                expected_obligation_sha256=obligation.obligation_sha256,
                expected_durable_record_sha256=durable_receipt.receipt["record_sha256"],
                expected_terminal_evidence_sha256=terminal["evidence_sha256"],
            ),
            protected_admission=protected_admission,
            durable_authority_ledger=ledger,
        )
        prepared_result = preparation_contract.prepare_offline(
            protected_admission, terminal, now_epoch=now_epoch
        )
        protected_preparation = prepared_result.get("protected_preparation")
        if prepared_result.get("ok") is not True or protected_preparation is None:
            raise RuntimeError("DURABLE_RESOLUTION_PREPARATION_NOT_ISSUED")
        commit_config = commit_v2.DormantDurableResolutionCommitConfigV2(
            enabled=True,
            scope_attestation=commit_v2.OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2,
            expected_preparation_sha256=protected_preparation.preparation_sha256,
            expected_admission_sha256=protected_admission.admission_sha256,
            expected_obligation_sha256=obligation.obligation_sha256,
            expected_pre_resolution_record_sha256=durable_receipt.receipt["record_sha256"],
            expected_terminal_evidence_sha256=terminal["evidence_sha256"],
        )
        commit_contract = commit_v2.DormantDurableResolutionCommitContractV2(
            commit_config,
            protected_preparation=protected_preparation,
            durable_authority_ledger=ledger,
        )
        triggered = {"value": False}

        def fault_hook(stage: str) -> None:
            if stage == fault_point and triggered["value"] is False:
                triggered["value"] = True
                raise RuntimeError("SYNTHETIC_INTERRUPT")

        first = commit_contract.commit_offline(
            protected_preparation,
            now_epoch=now_epoch,
            fault_hook=fault_hook if fault_point is not None else None,
        )
        active_ledger = ledger
        recovery = None
        recovered_receipt = None
        if fault_point is not None:
            active_ledger = durable_harness_v2._ledger(
                root, storage, root_identity
            )
            recovery = active_ledger.recover_offline()
            recovery_contract = commit_v2.DormantDurableResolutionCommitContractV2(
                commit_config,
                durable_authority_ledger=active_ledger,
            )
            recovered_receipt = recovery_contract.recover_receipt_offline()
        replay_contract = commit_v2.DormantDurableResolutionCommitContractV2(
            commit_config,
            protected_preparation=protected_preparation,
            durable_authority_ledger=active_ledger,
        )
        replay = replay_contract.commit_offline(
            protected_preparation, now_epoch=now_epoch
        )
        repeat = replay_contract.commit_offline(
            protected_preparation, now_epoch=now_epoch
        )
        divergent_preparation = preparation_v2.ProtectedDurableResolutionPreparationV2(
            protected_admission=protected_preparation.protected_admission,
            terminal_resolution_evidence=protected_preparation.terminal_resolution_evidence,
            preparation=protected_preparation.preparation,
            preparation_sha256=protected_preparation.preparation_sha256,
        )
        divergent = active_ledger.resolve_once_offline(
            divergent_preparation,
        )
    return {
        "first": first,
        "recovery": recovery,
        "recovered_receipt": recovered_receipt,
        "replay": replay,
        "repeat": repeat,
        "divergent": divergent,
        "commit_contract": commit_contract,
        "active_ledger": active_ledger,
        "protected_preparation": protected_preparation,
        "wal_events": wal_v2.read_journal(storage),
    }


def run_durable_resolution_commit_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "DURABLE_RESOLUTION_COMMIT_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_COMMIT_HARNESS_V2_VERSION,
        "protected_receipt": None,
        "source_obligation": None,
        "checks": [],
        "check_count": 0,
        "passed_count": 0,
        "temporary_filesystem_accessed": False,
        "temporary_write_executed": False,
        "temporary_storage_removed": False,
        "interprocess_lock_acquired": False,
        "resolver_called": False,
        "barrier_called": False,
        "backend_called": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        default_off = commit_v2.DormantDurableResolutionCommitContractV2().commit_offline(
            None, now_epoch=0
        )
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        temp_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="c3-durable-resolution-commit-v2-") as directory:
            temp_path = Path(directory)
            clean = _scenario(temp_path / "clean", obligation, "clean", None)
            after_prepared = _scenario(
                temp_path / "after-prepared", obligation, "after-prepared",
                wal_v2.AFTER_PREPARED,
            )
            after_replace = _scenario(
                temp_path / "after-replace", obligation, "after-replace",
                wal_v2.AFTER_REPLACE,
            )
            clean_receipt = clean["first"]["protected_receipt"]
            reconstructed = preparation_v2.ProtectedDurableResolutionPreparationV2(
                protected_admission=clean["protected_preparation"].protected_admission,
                terminal_resolution_evidence=clean["protected_preparation"].terminal_resolution_evidence,
                preparation=clean["protected_preparation"].preparation,
                preparation_sha256=clean["protected_preparation"].preparation_sha256,
            )
            reconstructed_result = clean["commit_contract"].commit_offline(
                reconstructed,
                now_epoch=clean["protected_preparation"].preparation["prepared_at_epoch"],
            )
            clean_resolve_commits = [
                event for event in clean["wal_events"]
                if event.operation == "DURABLE_AUTHORITY_RESOLVE"
                and event.state == wal_v2.EVENT_COMMITTED
            ]
            checks_by_name = {
                "ISSUED_TO_RESOLVED_SINGLE_WAL_MUTATION": clean["first"]["ok"] is True and clean_receipt.resolved_durable_authority_receipt.receipt["state"] == "RESOLVED" and len(clean_resolve_commits) == 1,
                "CONSUMPTION_AND_RECEIPT_MATERIAL_SHARE_RECORD": clean_receipt.resolved_durable_authority_receipt.record["consumption_count"] == 1 and clean_receipt.resolved_durable_authority_receipt.record["preparation_sha256"] == clean_receipt.receipt["preparation_sha256"] and clean_receipt.resolved_durable_authority_receipt.record["terminal_evidence_sha256"] == clean_receipt.receipt["terminal_evidence_sha256"],
                "CLEAN_REPLAY_RETURNS_IDENTICAL_RECEIPT": clean["replay"]["ok"] is True and clean["replay"]["idempotent_replay"] is True and clean["replay"]["protected_receipt"].receipt_sha256 == clean_receipt.receipt_sha256,
                "DIVERGENT_REPLAY_FAILS_CLOSED": clean["divergent"]["ok"] is False and clean["divergent"]["reason"] == "DURABLE_RESOLUTION_PREPARATION_INSTANCE_NOT_BOUND",
                "CRASH_AFTER_PREPARED_RECOVERS": after_prepared["first"]["ok"] is False and after_prepared["first"]["reason"] == "DURABLE_RESOLUTION_INTERRUPTED" and after_prepared["recovery"]["ok"] is True,
                "AFTER_PREPARED_REPLAY_RETURNS_IDENTICAL_RECEIPT": after_prepared["recovered_receipt"]["ok"] is True and after_prepared["replay"]["ok"] is True and after_prepared["repeat"]["ok"] is True and after_prepared["recovered_receipt"]["protected_receipt"].receipt_sha256 == after_prepared["replay"]["protected_receipt"].receipt_sha256 == after_prepared["repeat"]["protected_receipt"].receipt_sha256,
                "CRASH_AFTER_REPLACE_RECOVERS": after_replace["first"]["ok"] is False and after_replace["first"]["reason"] == "DURABLE_RESOLUTION_INTERRUPTED" and after_replace["recovery"]["ok"] is True,
                "AFTER_REPLACE_REPLAY_RETURNS_IDENTICAL_RECEIPT": after_replace["recovered_receipt"]["ok"] is True and after_replace["replay"]["ok"] is True and after_replace["repeat"]["ok"] is True and after_replace["recovered_receipt"]["protected_receipt"].receipt_sha256 == after_replace["replay"]["protected_receipt"].receipt_sha256 == after_replace["repeat"]["protected_receipt"].receipt_sha256,
                "RECONSTRUCTED_PREPARATION_INSTANCE_REJECTED": reconstructed_result["ok"] is False and reconstructed_result["reason"] == "DURABLE_RESOLUTION_PREPARATION_INSTANCE_NOT_PINNED",
                "DEFAULT_OFF_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "DURABLE_RESOLUTION_COMMIT_V2_DEFAULT_OFF" and default_off["filesystem_accessed"] is False,
                "NO_LEGACY_RESOLVER_BARRIER_BACKEND_OR_OPERATIONAL_ACCESS": all(clean["first"][key] is False for key in ("resolver_called", "barrier_called", "backend_called", "real_registry_accessed", "network_accessed", "broker_called", "runtime_integrated", "activation_allowed", "live_allowed")) and clean["first"]["no_order_sent"] is True,
                "TEMPORARY_STORAGE_REMOVED": True,
            }
            base.update({"temporary_filesystem_accessed": True, "temporary_write_executed": True, "interprocess_lock_acquired": True})
        removed = temp_path is not None and not temp_path.exists()
        checks_by_name["TEMPORARY_STORAGE_REMOVED"] = removed
        checks = [
            {"name": name, "passed": checks_by_name.get(name) is True}
            for name in _CHECK_NAMES
        ]
        passed_count = sum(item["passed"] for item in checks)
        ok = passed_count == len(_CHECK_NAMES)
        base.update(
            {
                "ok": ok,
                "status": "DURABLE_RESOLUTION_COMMIT_HARNESS_V2_PASSED" if ok else "DURABLE_RESOLUTION_COMMIT_HARNESS_V2_FAILED_CLOSED",
                "reason": None if ok else "ONE_OR_MORE_CHECKS_FAILED",
                "protected_receipt": clean_receipt,
                "source_obligation": clean["protected_preparation"].protected_admission.obligation,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_COMMIT_HARNESS_V2_VERSION",
    "run_durable_resolution_commit_harness_v2",
]
