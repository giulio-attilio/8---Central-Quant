"""Temporary-storage harness for dormant durable restart admission V2."""

from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as resolution_harness_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESTART-ADMISSION-HARNESS-V2"
)
_CHECK_NAMES = (
    "CURRENT_DURABLE_ISSUED_RECORD_VERIFIED",
    "EXACT_OBLIGATION_AND_TRANSACTION_BOUND",
    "FRESH_QUIESCED_19_WRITER_ZERO_INFLIGHT_LEASE_BOUND",
    "NEW_SESSION_AUTHORITY_BOUND",
    "RESEALED_NONCURRENT_DURABLE_RECEIPT_REJECTED",
    "FRESH_AUTHORITY_SUBSTITUTION_REJECTED",
    "EXPIRED_DURABLE_AUTHORITY_REJECTED",
    "CONSUMED_DURABLE_AUTHORITY_REJECTED",
    "DEFAULT_OFF_REJECTS_BEFORE_INPUT_INSPECTION",
    "PROTECTED_REPR_HIDES_ADMISSION",
    "NO_BARRIER_OR_RESOLVER_CALL_ALLOWED",
    "NO_REAL_REGISTRY_RUNTIME_NETWORK_BROKER_OR_ORDER",
)


def _sha(value: Any) -> str:
    return hash_v2.stable_sha256_v2(value)


def _contract(obligation, receipt, authority, ledger):
    return admission_v2.DormantDurableRestartAdmissionContractV2(
        admission_v2.DormantDurableRestartAdmissionConfigV2(
            enabled=True,
            scope_attestation=admission_v2.OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2,
            expected_obligation_sha256=obligation.obligation_sha256,
            expected_durable_root_identity_sha256=receipt.receipt["root_identity_sha256"],
            expected_durable_storage_binding_sha256=receipt.receipt["storage_binding_sha256"],
            expected_durable_record_sha256=receipt.receipt["record_sha256"],
            expected_fresh_authority_sha256=authority.authority_sha256,
        ),
        durable_authority_ledger=ledger,
    )


def _session_components(obligation, label: str, now_epoch: int):
    resolution_ledger = resolution_v2.InMemorySyntheticReconciliationResolutionLedgerV2()
    anchor = resolution_v2.ProtectedSyntheticReconciliationProcessSessionAnchorV2(
        _sha({"durable-admission-session": label, "obligation": obligation.obligation_sha256})
    )
    issuer = resolution_v2.InMemorySyntheticReconciliationAuthorizationIssuerV2(
        process_session_anchor=anchor,
        resolution_ledger=resolution_ledger,
    )
    permit = coordinator_v1.WriterMaintenancePermitV1(
        maintenance_epoch=_sha({"durable-admission-epoch": label}),
        state="QUIESCED",
        lock_namespace_sha256=coordinator_v1.canonical_runtime_lock_namespace_v1(),
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )
    witness = consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1(
        clock=lambda: now_epoch,
        nonce_source=lambda: "durable-restart-admission-" + label,
    )
    authorization_receipt = resolution_harness_v2._authorization_receipt(
        obligation, issuer, now_epoch
    )
    return (
        resolution_ledger, anchor, issuer, permit, witness,
        authorization_receipt,
    )


def _resealed_receipt(receipt):
    record = copy.deepcopy(dict(receipt.record))
    record["grant_sha256"] = _sha({"reconstructed-grant": record["grant_sha256"]})
    record["record_sha256"] = durable_v2.durable_authority_record_sha256_v2(record)
    envelope = copy.deepcopy(dict(receipt.receipt))
    envelope["grant_sha256"] = record["grant_sha256"]
    envelope["record_sha256"] = record["record_sha256"]
    envelope["receipt_sha256"] = durable_v2.durable_authority_receipt_sha256_v2(envelope)
    return durable_v2.ProtectedDurableReconciliationAuthorityReceiptV2(
        record=record,
        receipt=envelope,
        receipt_sha256=envelope["receipt_sha256"],
    )


def run_durable_restart_admission_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "DURABLE_RESTART_ADMISSION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_HARNESS_V2_VERSION,
        "protected_admission": None,
        "checks": [],
        "check_count": 0,
        "passed_count": 0,
        "temporary_filesystem_accessed": False,
        "temporary_write_executed": False,
        "temporary_storage_removed": False,
        "interprocess_lock_acquired": False,
        "barrier_called": False,
        "resolver_called": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        default_off = admission_v2.DormantDurableRestartAdmissionContractV2().issue_offline(
            None, None, None, now_epoch=0
        )
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        root_identity = _sha({"durable-restart-admission-root": obligation.obligation_sha256})
        grant = _sha({"durable-restart-admission-grant": obligation.obligation_sha256})
        issue_args = {
            "obligation_sha256": obligation.obligation_sha256,
            "obligation_id_sha256": obligation.obligation["obligation_id_sha256"],
            "transaction_sha256": obligation.obligation["transaction_sha256"],
            "subject_binding_sha256": obligation.obligation_sha256,
            "grant_sha256": grant,
            "issued_at_epoch": now_epoch,
            "expires_at_epoch": now_epoch + 240,
        }
        temp_path: Path | None = None
        with tempfile.TemporaryDirectory(prefix="c3-durable-restart-admission-v2-") as directory:
            temp_path = Path(directory)
            storage = durable_harness_v2._storage(temp_path)
            ledger = durable_harness_v2._ledger(temp_path, storage, root_identity)
            opened = ledger.open_offline()
            issued = ledger.issue_once_offline(**issue_args)
            durable_receipt = issued.get("protected_receipt")
            if opened.get("ok") is not True or durable_receipt is None:
                base["reason"] = "DURABLE_AUTHORITY_NOT_ISSUED"
                return base

            components1 = _session_components(
                obligation, "durable-admission-current-session", now_epoch
            )
            ledger1, anchor1, issuer1, permit1, witness1, auth_receipt1 = components1
            components2 = _session_components(
                obligation, "durable-admission-substitute-session", now_epoch
            )
            ledger2, anchor2, issuer2, permit2, witness2, auth_receipt2 = components2
            with witness1.hold_offline(permit1, expires_at_epoch=now_epoch + 120) as token1:
                authority1 = resolution_harness_v2._protected_authority(
                    obligation, permit1, token1, witness1, ledger1, issuer1,
                    anchor1, now_epoch, auth_receipt1,
                )
                contract = _contract(obligation, durable_receipt, authority1, ledger)
                admitted = contract.issue_offline(
                    obligation, durable_receipt, authority1, now_epoch=now_epoch
                )
                protected_admission = admitted.get("protected_admission")
                if admitted.get("ok") is not True or protected_admission is None:
                    base["reason"] = admitted.get("reason") or "DURABLE_RESTART_ADMISSION_NOT_ISSUED"
                    return base

                forged_receipt = _resealed_receipt(durable_receipt)
                forged_contract = _contract(obligation, forged_receipt, authority1, ledger)
                forged = forged_contract.issue_offline(
                    obligation, forged_receipt, authority1, now_epoch=now_epoch
                )
                expired = contract.issue_offline(
                    obligation, durable_receipt, authority1, now_epoch=now_epoch + 241
                )
                with witness2.hold_offline(permit2, expires_at_epoch=now_epoch + 120) as token2:
                    authority2 = resolution_harness_v2._protected_authority(
                        obligation, permit2, token2, witness2, ledger2, issuer2,
                        anchor2, now_epoch, auth_receipt2,
                    )
                    substituted = contract.issue_offline(
                        obligation, durable_receipt, authority2, now_epoch=now_epoch
                    )
                consumed = ledger.consume_once_offline(
                    durable_receipt,
                    terminal_evidence_sha256=_sha({"terminal": obligation.obligation_sha256}),
                    consumed_at_epoch=now_epoch + 1,
                )
                after_consumption = contract.issue_offline(
                    obligation, durable_receipt, authority1, now_epoch=now_epoch + 1
                )

            admission = protected_admission.admission
            checks_by_name = {
                "CURRENT_DURABLE_ISSUED_RECORD_VERIFIED": admitted["durable_authority_currently_issued_verified"] is True and admission["durable_record_sha256"] == durable_receipt.receipt["record_sha256"],
                "EXACT_OBLIGATION_AND_TRANSACTION_BOUND": admission["obligation_sha256"] == obligation.obligation_sha256 and admission["transaction_sha256"] == obligation.obligation["transaction_sha256"],
                "FRESH_QUIESCED_19_WRITER_ZERO_INFLIGHT_LEASE_BOUND": admission["fresh_quiesced_lease_verified"] is True and permit1.state == "QUIESCED" and permit1.registered_writer_count == 19 and permit1.inflight_mutations == 0,
                "NEW_SESSION_AUTHORITY_BOUND": admission["fresh_session_anchor_identity_sha256"] == authority1.authority["process_session_anchor_object_identity_sha256"] and authority1.process_session_anchor is anchor1,
                "RESEALED_NONCURRENT_DURABLE_RECEIPT_REJECTED": forged["ok"] is False and forged["reason"] == "DURABLE_AUTHORITY_NOT_CURRENTLY_ISSUED",
                "FRESH_AUTHORITY_SUBSTITUTION_REJECTED": substituted["ok"] is False and substituted["reason"] == "FRESH_QUIESCED_RECONCILIATION_AUTHORITY_NOT_PINNED",
                "EXPIRED_DURABLE_AUTHORITY_REJECTED": expired["ok"] is False and expired["reason"] == "DURABLE_AUTHORITY_NOT_CURRENTLY_VALID",
                "CONSUMED_DURABLE_AUTHORITY_REJECTED": consumed["ok"] is True and after_consumption["ok"] is False and after_consumption["reason"] == "DURABLE_AUTHORITY_NOT_CURRENTLY_ISSUED",
                "DEFAULT_OFF_REJECTS_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "DURABLE_RESTART_ADMISSION_V2_DEFAULT_OFF" and default_off["temporary_filesystem_accessed"] is False,
                "PROTECTED_REPR_HIDES_ADMISSION": repr(protected_admission) == "ProtectedDurableRestartAdmissionV2(<protected>)" and admission_v2.protected_durable_restart_admission_valid_v2(protected_admission),
                "NO_BARRIER_OR_RESOLVER_CALL_ALLOWED": admission["barrier_call_allowed"] is False and admission["resolver_call_allowed"] is False and admitted["barrier_called"] is False and admitted["resolver_called"] is False,
                "NO_REAL_REGISTRY_RUNTIME_NETWORK_BROKER_OR_ORDER": all(admitted[key] is False for key in ("real_registry_accessed", "network_accessed", "broker_called", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")) and admitted["no_order_sent"] is True,
            }
            base["temporary_filesystem_accessed"] = True
            base["temporary_write_executed"] = True
            base["interprocess_lock_acquired"] = True
        removed = temp_path is not None and not temp_path.exists()
        checks = [
            {"name": name, "passed": checks_by_name.get(name) is True}
            for name in _CHECK_NAMES
        ]
        passed = sum(item["passed"] for item in checks)
        base.update(
            {
                "ok": passed == len(_CHECK_NAMES) and removed,
                "status": "DURABLE_RESTART_ADMISSION_HARNESS_V2_PASSED" if passed == len(_CHECK_NAMES) and removed else "DURABLE_RESTART_ADMISSION_HARNESS_V2_FAILED_CLOSED",
                "reason": None if passed == len(_CHECK_NAMES) and removed else "ONE_OR_MORE_CHECKS_FAILED",
                "protected_admission": protected_admission,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": passed,
                "temporary_storage_removed": removed,
            }
        )
        return base
    except Exception as exc:
        base["reason"] = f"HARNESS_EXCEPTION:{type(exc).__name__}"
        return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_HARNESS_V2_VERSION",
    "run_durable_restart_admission_harness_v2",
]
