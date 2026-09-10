"""Synthetic in-memory harness for the dormant reconciliation restart barrier."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as resolution_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESTART-BARRIER-HARNESS-V2"
)
PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EVIDENCE_V2"
)
_CHECK_NAMES = (
    "BARRIER_VALID_AND_PROTECTED",
    "ORIGINAL_SESSION_CONTINUITY_CONFIRMED",
    "SESSION_LOSS_FAILS_CLOSED",
    "FULL_REMINT_NEW_SESSION_REJECTED",
    "SAME_GRANT_NEW_RECEIPT_NOT_ACCEPTED",
    "SESSION_ISSUER_LEDGER_IDENTITIES_PINNED",
    "DURABLE_EVIDENCE_UNSUPPORTED_FAILS_CLOSED",
    "RESEALED_SESSION_IDENTITY_REJECTED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "NO_RESOLUTION_AUTHORITY_OR_EXECUTION_EMITTED",
    "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "barrier_sha256", "obligation_sha256",
        "reference_authority_sha256", "reminted_authority_sha256",
        "same_grant_sha256", "distinct_authorization_receipts",
        "checks", "check_count", "passed_count", "backend_called",
        "provider_called", "store_called", "writer_called", "lock_acquired",
        "registry_write", "write_executed", "filesystem_accessed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "production_authority", "runtime_integrated", "activation_allowed",
        "live_allowed", "resolution_executed", "synthetic_only",
        "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def _permit(obligation_sha256: str, label: str):
    return coordinator_v1.WriterMaintenancePermitV1(
        maintenance_epoch=_sha({label: obligation_sha256}),
        state="QUIESCED",
        lock_namespace_sha256=coordinator_v1.canonical_runtime_lock_namespace_v1(),
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )


def _session_components(obligation, label: str, now_epoch: int):
    ledger = resolution_v2.InMemorySyntheticReconciliationResolutionLedgerV2()
    anchor = resolution_v2.ProtectedSyntheticReconciliationProcessSessionAnchorV2(
        _sha({"restart-barrier-session": label, "obligation": obligation.obligation_sha256})
    )
    issuer = resolution_v2.InMemorySyntheticReconciliationAuthorizationIssuerV2(
        process_session_anchor=anchor,
        resolution_ledger=ledger,
    )
    permit = _permit(obligation.obligation_sha256, label)
    witness = consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1(
        clock=lambda: now_epoch,
        nonce_source=lambda: "restart-barrier-" + label,
    )
    receipt = resolution_harness_v2._authorization_receipt(
        obligation, issuer, now_epoch
    )
    return ledger, anchor, issuer, permit, witness, receipt


def protected_reconciliation_restart_barrier_harness_evidence_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return _sha({key: item for key, item in value.items() if key != "evidence_sha256"})


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationRestartBarrierHarnessEvidenceV2:
    protected_barrier: barrier_v2.ProtectedReconciliationRestartBarrierV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationRestartBarrierHarnessEvidenceV2(<protected>)"


def protected_reconciliation_restart_barrier_harness_evidence_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedReconciliationRestartBarrierHarnessEvidenceV2:
        return False
    evidence = value.evidence
    checks = evidence.get("checks") if type(evidence) is dict else None
    try:
        return bool(
            type(evidence) is dict
            and set(evidence) == _EVIDENCE_KEYS
            and barrier_v2.protected_reconciliation_restart_barrier_valid_v2(
                value.protected_barrier
            )
            and evidence["evidence_version"]
            == PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EVIDENCE_VERSION_V2
            and evidence["barrier_sha256"] == value.protected_barrier.barrier_sha256
            and evidence["obligation_sha256"]
            == value.protected_barrier.obligation.obligation_sha256
            and evidence["reference_authority_sha256"]
            == value.protected_barrier.reference_authority.authority_sha256
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(
                type(item) is dict
                and set(item) == _CHECK_KEYS
                and item["passed"] is True
                for item in checks
            )
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and evidence["same_grant_sha256"] is True
            and evidence["distinct_authorization_receipts"] is True
            and all(
                evidence[key] is False
                for key in (
                    "backend_called", "provider_called", "store_called",
                    "writer_called", "lock_acquired", "registry_write",
                    "write_executed", "filesystem_accessed",
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed", "resolution_executed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_reconciliation_restart_barrier_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def run_protected_reconciliation_restart_barrier_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_V2_VERSION,
        "protected_barrier": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "registry_write": False,
        "write_executed": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "resolution_executed": False,
        "no_order_sent": True,
    }
    try:
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        ledger1, anchor1, issuer1, permit1, witness1, receipt1 = _session_components(
            obligation, "original", now_epoch
        )
        ledger2, anchor2, issuer2, permit2, witness2, receipt2 = _session_components(
            obligation, "reminted", now_epoch
        )
        default_off = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2().issue_offline(
            None, None, now_epoch=0
        )
        with witness1.hold_offline(permit1, expires_at_epoch=now_epoch + 120) as token1:
            authority1 = resolution_harness_v2._protected_authority(
                obligation, permit1, token1, witness1, ledger1, issuer1, anchor1,
                now_epoch, receipt1,
            )
            contract = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2(
                barrier_v2.DormantProtectedReconciliationRestartBarrierConfigV2(
                    enabled=True,
                    scope_attestation=barrier_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
                    expected_obligation_sha256=obligation.obligation_sha256,
                    expected_reference_authority_sha256=authority1.authority_sha256,
                )
            )
            issued = contract.issue_offline(
                obligation, authority1, now_epoch=now_epoch
            )
            protected_barrier = issued.get("protected_barrier")
            if issued.get("ok") is not True or protected_barrier is None:
                base["reason"] = "PROTECTED_RESTART_BARRIER_NOT_ISSUED"
                return base
            original_continuity = contract.evaluate_offline(
                protected_barrier, authority1,
                session_loss_declared=False, now_epoch=now_epoch,
            )
            declared_loss = contract.evaluate_offline(
                protected_barrier, authority1,
                session_loss_declared=True, now_epoch=now_epoch,
            )
            durable_unsupported = contract.evaluate_offline(
                protected_barrier, authority1,
                session_loss_declared=True, now_epoch=now_epoch,
                durable_authority_evidence={"synthetic": "unsupported"},
            )
            with witness2.hold_offline(permit2, expires_at_epoch=now_epoch + 120) as token2:
                authority2 = resolution_harness_v2._protected_authority(
                    obligation, permit2, token2, witness2, ledger2, issuer2, anchor2,
                    now_epoch, receipt2,
                )
                reminted_rejected = contract.evaluate_offline(
                    protected_barrier, authority2,
                    session_loss_declared=False, now_epoch=now_epoch,
                )
            tampered_record = copy.deepcopy(dict(protected_barrier.barrier))
            tampered_record["reference_session_anchor_object_identity_sha256"] = _sha(
                "substituted-session"
            )
            tampered_record["barrier_sha256"] = (
                barrier_v2.protected_reconciliation_restart_barrier_sha256_v2(
                    tampered_record
                )
            )
            tampered_barrier = barrier_v2.ProtectedReconciliationRestartBarrierV2(
                obligation=obligation,
                reference_authority=authority1,
                barrier=tampered_record,
                barrier_sha256=tampered_record["barrier_sha256"],
            )
            tampered_rejected = contract.evaluate_offline(
                tampered_barrier, authority1,
                session_loss_declared=False, now_epoch=now_epoch,
            )
        same_grant = receipt1["grant_sha256"] == receipt2["grant_sha256"]
        distinct_receipts = receipt1["receipt_sha256"] != receipt2["receipt_sha256"]
        barrier_record = protected_barrier.barrier
        checks_by_name = {
            "BARRIER_VALID_AND_PROTECTED": barrier_v2.protected_reconciliation_restart_barrier_valid_v2(protected_barrier) and repr(protected_barrier) == "ProtectedReconciliationRestartBarrierV2(<protected>)",
            "ORIGINAL_SESSION_CONTINUITY_CONFIRMED": original_continuity["ok"] is True and original_continuity["barrier_passed_offline"] is True and original_continuity["original_session_continuity_confirmed"] is True,
            "SESSION_LOSS_FAILS_CLOSED": declared_loss["ok"] is False and declared_loss["reason"] == "RESTART_RESOLUTION_FORBIDDEN_DURABLE_AUTHORITY_REQUIRED" and declared_loss["durable_authority_required"] is True,
            "FULL_REMINT_NEW_SESSION_REJECTED": reminted_rejected["ok"] is False and reminted_rejected["reason"] == "ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN",
            "SAME_GRANT_NEW_RECEIPT_NOT_ACCEPTED": same_grant and distinct_receipts and reminted_rejected["ok"] is False,
            "SESSION_ISSUER_LEDGER_IDENTITIES_PINNED": barrier_record["reference_authority_sha256"] == authority1.authority_sha256 and barrier_record["reference_authorization_receipt_sha256"] == receipt1["receipt_sha256"] and authority1.process_session_anchor is anchor1 and authority1.authorization_issuer is issuer1 and authority1.single_use_ledger is ledger1,
            "DURABLE_EVIDENCE_UNSUPPORTED_FAILS_CLOSED": durable_unsupported["ok"] is False and durable_unsupported["reason"] == "DURABLE_AUTHORITY_VALIDATION_NOT_IMPLEMENTED" and durable_unsupported["durable_authority_required"] is True,
            "RESEALED_SESSION_IDENTITY_REJECTED": tampered_rejected["ok"] is False and tampered_rejected["reason"] == "PROTECTED_RECONCILIATION_RESTART_BARRIER_INVALID",
            "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "PROTECTED_RECONCILIATION_RESTART_BARRIER_V2_DEFAULT_OFF",
            "NO_RESOLUTION_AUTHORITY_OR_EXECUTION_EMITTED": all(result["resolution_authority_granted"] is False and result["resolution_executed"] is False for result in (issued, original_continuity, declared_loss, durable_unsupported, reminted_rejected, tampered_rejected)),
            "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT": all(all(result[key] is False for key in ("backend_called", "provider_called", "store_called", "writer_called", "lock_acquired", "registry_write", "write_executed", "filesystem_accessed", "real_registry_accessed", "network_accessed", "broker_called", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")) for result in (issued, original_continuity, declared_loss, durable_unsupported, reminted_rejected, tampered_rejected)),
        }
        checks = [
            {"name": name, "passed": checks_by_name[name] is True}
            for name in _CHECK_NAMES
        ]
        if not all(item["passed"] for item in checks):
            base["reason"] = "PROTECTED_RESTART_BARRIER_ORACLE_FAILED"
            base["failed_checks"] = [item["name"] for item in checks if not item["passed"]]
            return base
        evidence = {
            "evidence_version": PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EVIDENCE_VERSION_V2,
            "barrier_sha256": protected_barrier.barrier_sha256,
            "obligation_sha256": obligation.obligation_sha256,
            "reference_authority_sha256": authority1.authority_sha256,
            "reminted_authority_sha256": authority2.authority_sha256,
            "same_grant_sha256": same_grant,
            "distinct_authorization_receipts": distinct_receipts,
            "checks": checks,
            "check_count": len(checks),
            "passed_count": sum(item["passed"] for item in checks),
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "registry_write": False,
            "write_executed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "resolution_executed": False,
            "synthetic_only": True,
        }
        evidence["evidence_sha256"] = protected_reconciliation_restart_barrier_harness_evidence_sha256_v2(evidence)
        protected_evidence = ProtectedReconciliationRestartBarrierHarnessEvidenceV2(
            protected_barrier=protected_barrier,
            evidence=copy.deepcopy(evidence),
            evidence_sha256=evidence["evidence_sha256"],
        )
        if not protected_reconciliation_restart_barrier_harness_evidence_valid_v2(
            protected_evidence
        ):
            base["reason"] = "PROTECTED_RESTART_BARRIER_EVIDENCE_INTERNAL_INVALID"
            return base
    except Exception as exc:
        base["reason"] = "PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EXCEPTION"
        base["diagnostic"] = type(exc).__name__
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_PASSED_OFFLINE",
            "protected_barrier": protected_barrier,
            "protected_evidence": protected_evidence,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
        }
    )
    return base


__all__ = [
    "PROTECTED_RECONCILIATION_RESTART_BARRIER_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedReconciliationRestartBarrierHarnessEvidenceV2",
    "protected_reconciliation_restart_barrier_harness_evidence_sha256_v2",
    "protected_reconciliation_restart_barrier_harness_evidence_valid_v2",
    "run_protected_reconciliation_restart_barrier_harness_v2",
]
