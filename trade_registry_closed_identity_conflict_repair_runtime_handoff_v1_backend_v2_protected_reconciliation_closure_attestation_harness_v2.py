"""Offline harness for immutable reconciliation closure attestations."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any

import registry_v2_wal as wal_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_contract_v2 as closure_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2 as envelope_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_harness_v2 as envelope_harness_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-CLOSURE-ATTESTATION-HARNESS-V2"
)
_CHECK_NAMES = (
    "LEGACY_OUTCOME_CLOSURE_ATTESTED",
    "DURABLE_OUTCOME_CLOSURE_ATTESTED",
    "ORIGINAL_OBLIGATIONS_REMAIN_UNRESOLVED_AND_VALID",
    "FULL_IDENTITY_VECTOR_MATCHED",
    "DETERMINISTIC_REISSUE_IDENTICAL",
    "RECONSTRUCTED_OBLIGATION_INSTANCE_REJECTED",
    "RECONSTRUCTED_ENVELOPE_INSTANCE_REJECTED",
    "CROSS_OUTCOME_IDENTITY_MISMATCH_REJECTED",
    "RESEALED_RETRY_AUTHORITY_REJECTED",
    "SOURCE_SEMANTICS_PRESERVED",
    "DEFAULT_OFF_BEFORE_INPUT_INSPECTION",
    "NO_STATE_RUNTIME_REGISTRY_NETWORK_BROKER_OR_ORDER",
    "DURABLE_CLOSURE_PROJECTION_COMMITTED",
    "DURABLE_CLOSURE_PROJECTION_IDEMPOTENT",
    "RESTART_READS_AUTHORITATIVE_RESOLVED_PROJECTION",
    "PROJECTION_PRESERVES_ORIGINAL_OBLIGATION_IMMUTABLE",
    "PREPARED_PROJECTION_RECOVERED_AFTER_RESTART",
    "RECONSTRUCTED_CLOSURE_ATTESTATION_REJECTED",
)


def _contract(obligation, envelope):
    return closure_v2.DormantReconciliationClosureAttestationContractV2(
        closure_v2.DormantReconciliationClosureAttestationConfigV2(
            enabled=True,
            scope_attestation=closure_v2.OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2,
            expected_obligation_sha256=obligation.obligation_sha256,
            expected_outcome_envelope_sha256=envelope.envelope_sha256,
            expected_source_receipt_sha256=envelope.envelope["source_receipt_sha256"],
            expected_transaction_sha256=obligation.obligation["transaction_sha256"],
        ),
        original_obligation=obligation,
        outcome_envelope=envelope,
    )


def _projection_storage(root: Path) -> wal_v2.RegistryV2WalStorage:
    return wal_v2.RegistryV2WalStorage(
        snapshot_path=root / "closure.snapshot.json",
        journal_path=root / "closure.journal.jsonl",
        lock_path=root / "closure.wal.lock",
        backup_dir=root / "closure.backups",
    )


def _projection_ledger(
    root: Path,
    storage: wal_v2.RegistryV2WalStorage,
    attestation=None,
):
    binding = closure_v2.durable_closure_projection_storage_binding_sha256_v2(
        storage
    )
    return closure_v2.DormantDurableClosureProjectionLedgerV2(
        closure_v2.DormantDurableClosureProjectionConfigV2(
            enabled=True,
            scope_attestation=closure_v2.DURABLE_CLOSURE_PROJECTION_SCOPE_V2,
            expected_storage_binding_sha256=binding,
            expected_closure_attestation_sha256=(
                attestation.attestation_sha256 if attestation is not None else None
            ),
        ),
        protected_attestation=attestation,
        storage=storage,
        lock_backend=storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            root, enabled=True
        ),
    )


def run_reconciliation_closure_attestation_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_VERSION,
        "legacy_attestation": None,
        "durable_attestation": None,
        "checks": [],
        "check_count": 0,
        "passed_count": 0,
        "state_update_executed": False,
        "write_executed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        default_off = closure_v2.DormantReconciliationClosureAttestationContractV2().issue_offline(None, None)
        upstream = envelope_harness_v2.run_resolution_outcome_envelope_harness_v2()
        if upstream.get("ok") is not True:
            base["reason"] = "OUTCOME_ENVELOPE_HARNESS_FAILED"
            return base
        legacy_obligation = upstream["legacy_obligation"]
        durable_obligation = upstream["durable_obligation"]
        legacy_envelope = upstream["legacy_envelope"]
        durable_envelope = upstream["durable_envelope"]
        legacy_contract = _contract(legacy_obligation, legacy_envelope)
        durable_contract = _contract(durable_obligation, durable_envelope)
        legacy_result = legacy_contract.issue_offline(legacy_obligation, legacy_envelope)
        durable_result = durable_contract.issue_offline(durable_obligation, durable_envelope)
        legacy_attestation = legacy_result.get("protected_attestation")
        durable_attestation = durable_result.get("protected_attestation")
        if legacy_attestation is None or durable_attestation is None:
            base["reason"] = "CLOSURE_ATTESTATION_NOT_ISSUED"
            return base
        repeated = durable_contract.issue_offline(durable_obligation, durable_envelope)
        reconstructed_obligation = obligation_v2.ProtectedReconciliationObligationV2(
            adapter_plan=durable_obligation.adapter_plan,
            protected_terminal_result=durable_obligation.protected_terminal_result,
            source_evidence=durable_obligation.source_evidence,
            obligation=durable_obligation.obligation,
            obligation_sha256=durable_obligation.obligation_sha256,
        )
        reconstructed_obligation_result = durable_contract.issue_offline(
            reconstructed_obligation, durable_envelope
        )
        reconstructed_envelope = envelope_v2.ProtectedResolutionOutcomeEnvelopeV2(
            native_source_receipt=durable_envelope.native_source_receipt,
            envelope=durable_envelope.envelope,
            envelope_sha256=durable_envelope.envelope_sha256,
        )
        reconstructed_envelope_result = durable_contract.issue_offline(
            durable_obligation, reconstructed_envelope
        )
        crossed = _contract(legacy_obligation, durable_envelope).issue_offline(
            legacy_obligation, durable_envelope
        )
        tampered_record = copy.deepcopy(dict(durable_attestation.attestation))
        tampered_record["retry_allowed"] = True
        tampered_record["attestation_sha256"] = closure_v2.reconciliation_closure_attestation_sha256_v2(tampered_record)
        tampered = closure_v2.ProtectedReconciliationClosureAttestationV2(
            original_obligation=durable_obligation,
            outcome_envelope=durable_envelope,
            attestation=tampered_record,
            attestation_sha256=tampered_record["attestation_sha256"],
        )
        reconstructed_attestation = (
            closure_v2.ProtectedReconciliationClosureAttestationV2(
                original_obligation=durable_obligation,
                outcome_envelope=durable_envelope,
                attestation=durable_attestation.attestation,
                attestation_sha256=durable_attestation.attestation_sha256,
            )
        )
        with tempfile.TemporaryDirectory(
            prefix="c3-closure-projection-v2-"
        ) as directory:
            projection_root = Path(directory)
            projection_storage = _projection_storage(projection_root)
            projection = _projection_ledger(
                projection_root, projection_storage, durable_attestation
            )
            projection_open = projection.open_offline()
            projection_commit = projection.commit_once_offline(
                durable_attestation
            )
            projection_receipt = projection_commit.get("protected_receipt")
            projection_replay = projection.commit_once_offline(
                durable_attestation
            )
            reconstructed_projection = projection.commit_once_offline(
                reconstructed_attestation
            )
            projection_restart = _projection_ledger(
                projection_root, projection_storage
            )
            projection_reopen = projection_restart.open_offline()
            projection_read = projection_restart.read_closure_offline(
                durable_obligation.obligation_sha256
            )

            def interrupt_after_prepare(stage: str) -> None:
                if stage == wal_v2.AFTER_PREPARED:
                    raise RuntimeError("synthetic-closure-projection-crash")

            legacy_projection = _projection_ledger(
                projection_root, projection_storage, legacy_attestation
            )
            projection_interrupted = legacy_projection.commit_once_offline(
                legacy_attestation,
                fault_hook=interrupt_after_prepare,
            )
            recovery = _projection_ledger(
                projection_root, projection_storage
            ).recover_offline()
            recovered_projection = _projection_ledger(
                projection_root, projection_storage
            ).read_closure_offline(legacy_obligation.obligation_sha256)
        identity_fields = (
            "obligation_sha256", "obligation_id_sha256",
            "source_evidence_sha256", "adapter_plan_sha256",
            "request_binding_sha256", "request_sha256", "transaction_sha256",
        )
        legacy_record = legacy_attestation.attestation
        durable_record = durable_attestation.attestation
        checks_by_name = {
            "LEGACY_OUTCOME_CLOSURE_ATTESTED": legacy_result["ok"] is True and closure_v2.protected_reconciliation_closure_attestation_valid_v2(legacy_attestation),
            "DURABLE_OUTCOME_CLOSURE_ATTESTED": durable_result["ok"] is True and closure_v2.protected_reconciliation_closure_attestation_valid_v2(durable_attestation),
            "ORIGINAL_OBLIGATIONS_REMAIN_UNRESOLVED_AND_VALID": obligation_v2.protected_reconciliation_obligation_valid_v2(legacy_obligation) and obligation_v2.protected_reconciliation_obligation_valid_v2(durable_obligation) and legacy_obligation.obligation["resolution_state"] == "UNRESOLVED" and durable_obligation.obligation["resolution_state"] == "UNRESOLVED",
            "FULL_IDENTITY_VECTOR_MATCHED": all(legacy_record[key] == legacy_obligation.obligation[key] for key in identity_fields) and all(durable_record[key] == durable_obligation.obligation[key] for key in identity_fields),
            "DETERMINISTIC_REISSUE_IDENTICAL": repeated["ok"] is True and repeated["protected_attestation"].attestation_sha256 == durable_attestation.attestation_sha256,
            "RECONSTRUCTED_OBLIGATION_INSTANCE_REJECTED": reconstructed_obligation_result["ok"] is False and reconstructed_obligation_result["reason"] == "ORIGINAL_OBLIGATION_INSTANCE_NOT_PINNED",
            "RECONSTRUCTED_ENVELOPE_INSTANCE_REJECTED": reconstructed_envelope_result["ok"] is False and reconstructed_envelope_result["reason"] == "OUTCOME_ENVELOPE_INSTANCE_NOT_PINNED",
            "CROSS_OUTCOME_IDENTITY_MISMATCH_REJECTED": crossed["ok"] is False and crossed["reason"] == "OBLIGATION_OUTCOME_IDENTITY_MISMATCH",
            "RESEALED_RETRY_AUTHORITY_REJECTED": closure_v2.protected_reconciliation_closure_attestation_valid_v2(tampered) is False,
            "SOURCE_SEMANTICS_PRESERVED": legacy_record["source_kind"] == envelope_v2.ORIGINAL_SESSION_RECEIPT_SOURCE_V2 and durable_record["source_kind"] == envelope_v2.DURABLE_RESTART_RECEIPT_SOURCE_V2,
            "DEFAULT_OFF_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "RECONCILIATION_CLOSURE_ATTESTATION_V2_DEFAULT_OFF",
            "NO_STATE_RUNTIME_REGISTRY_NETWORK_BROKER_OR_ORDER": all(legacy_result[key] is False and durable_result[key] is False for key in ("state_update_allowed", "runtime_mutation_allowed", "write_executed", "real_registry_accessed", "network_accessed", "broker_called", "runtime_integrated", "activation_allowed", "live_allowed")) and legacy_result["no_order_sent"] is True and durable_result["no_order_sent"] is True,
            "DURABLE_CLOSURE_PROJECTION_COMMITTED": projection_open["ok"] is True and projection_commit["ok"] is True and closure_v2.protected_durable_closure_projection_receipt_valid_v2(projection_receipt) and projection_commit["effective_resolution_state"] == "RESOLVED" and projection_commit["effective_reconciliation_required"] is False,
            "DURABLE_CLOSURE_PROJECTION_IDEMPOTENT": projection_replay["ok"] is True and projection_replay["status"] == "DURABLE_CLOSURE_PROJECTION_ALREADY_COMMITTED" and projection_replay["protected_receipt"].receipt_sha256 == projection_receipt.receipt_sha256,
            "RESTART_READS_AUTHORITATIVE_RESOLVED_PROJECTION": projection_reopen["ok"] is True and projection_read["ok"] is True and projection_read["protected_receipt"].receipt_sha256 == projection_receipt.receipt_sha256 and projection_read["effective_resolution_state"] == "RESOLVED",
            "PROJECTION_PRESERVES_ORIGINAL_OBLIGATION_IMMUTABLE": durable_obligation.obligation["resolution_state"] == "UNRESOLVED" and obligation_v2.protected_reconciliation_obligation_valid_v2(durable_obligation),
            "PREPARED_PROJECTION_RECOVERED_AFTER_RESTART": projection_interrupted["ok"] is False and projection_interrupted["reason"] == "DURABLE_CLOSURE_PROJECTION_INTERRUPTED" and recovery["ok"] is True and recovered_projection["ok"] is True and recovered_projection["effective_reconciliation_required"] is False,
            "RECONSTRUCTED_CLOSURE_ATTESTATION_REJECTED": reconstructed_projection["ok"] is False and reconstructed_projection["reason"] == "CLOSURE_ATTESTATION_INSTANCE_NOT_PINNED",
        }
        checks = [
            {"name": name, "passed": checks_by_name.get(name) is True}
            for name in _CHECK_NAMES
        ]
        passed_count = sum(item["passed"] for item in checks)
        ok = passed_count == len(_CHECK_NAMES)
        base.update(
            {
                "ok": ok,
                "status": "RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_PASSED" if ok else "RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_FAILED_CLOSED",
                "reason": None if ok else "ONE_OR_MORE_CHECKS_FAILED",
                "legacy_attestation": legacy_attestation,
                "durable_attestation": durable_attestation,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": passed_count,
            }
        )
        return base
    except Exception as exc:
        detail = str(exc) if isinstance(exc, KeyError) else type(exc).__name__
        base["reason"] = f"HARNESS_EXCEPTION:{type(exc).__name__}:{detail}"
        return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_CLOSURE_ATTESTATION_HARNESS_V2_VERSION",
    "run_reconciliation_closure_attestation_harness_v2",
]
