"""Offline harness for the protected V2 reconciliation obligation contract."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_execution_harness_v2 as execution_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2 as adapter_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-OBLIGATION-HARNESS-V2"
)
PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EVIDENCE_V2"
)

_CHECK_NAMES = (
    "TERMINAL_AMBIGUITY_OBLIGATION_VALID",
    "POST_CALL_EXCEPTION_OBLIGATION_VALID",
    "SAME_TRANSACTION_IDENTITY_BOUND",
    "NEW_APPLY_AND_RETRY_FORBIDDEN",
    "ORIGINAL_AUTHORIZATION_REUSE_FORBIDDEN",
    "FRESH_AUTHORITY_REQUIRED_FOR_RECONCILIATION",
    "RESOLUTION_RECEIPT_REQUIRED",
    "COMMITTED_OUTCOME_REJECTED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "RESEALED_RETRY_ESCALATION_REJECTED",
    "RESEALED_RESOLUTION_CLAIM_REJECTED",
    "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "terminal_ambiguity_obligation_sha256",
        "post_call_exception_obligation_sha256",
        "transaction_sha256",
        "checks",
        "check_count",
        "passed_count",
        "backend_called",
        "provider_called",
        "store_called",
        "writer_called",
        "lock_acquired",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "evidence_sha256",
    }
)


def protected_reconciliation_obligation_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return backend_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


def _ambiguous_protected_result(committed):
    terminal = copy.deepcopy(dict(committed.terminal_result))
    terminal["terminal_state"] = "AMBIGUOUS"
    terminal["postconditions_verified"] = False
    terminal["recovery_required"] = True
    terminal["result_sha256"] = backend_v2.stable_sha256_v2(
        {
            key: item
            for key, item in terminal.items()
            if key != "result_sha256"
        }
    )
    envelope = copy.deepcopy(dict(committed.envelope))
    envelope["terminal_result_sha256"] = terminal["result_sha256"]
    envelope["envelope_sha256"] = (
        adapter_v2.protected_held_lease_port_invocation_result_envelope_sha256_v2(
            envelope
        )
    )
    protected = adapter_v2.ProtectedHeldLeasePortInvocationResultV2(
        adapter_plan=committed.adapter_plan,
        port_attestation=committed.port_attestation,
        terminal_result=terminal,
        envelope=envelope,
        envelope_sha256=envelope["envelope_sha256"],
    )
    if not adapter_v2.protected_held_lease_port_invocation_result_valid_v2(
        protected
    ):
        raise ValueError("SYNTHETIC_AMBIGUOUS_PROTECTED_RESULT_INVALID")
    return protected


def _ambiguous_outcome(protected_result):
    outcome = adapter_v2.SyntheticProtectedHeldLeasePortAdapterV2._failed(
        "",
        backend_called=True,
        lease_revalidated=True,
        recovery_required=True,
    )
    outcome.update(
        {
            "status": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_AMBIGUOUS_RECONCILIATION_REQUIRED",
            "reason": "SYNTHETIC_TRANSACTION_AMBIGUOUS_RECONCILIATION_REQUIRED",
            "protected_result": protected_result,
            "result_envelope_sha256": protected_result.envelope_sha256,
            "terminal_state": "AMBIGUOUS",
            "recovery_required": True,
            "retry_allowed": False,
            "synthetic_memory_write_executed": bool(
                protected_result.terminal_result["write_executed"]
            ),
        }
    )
    return outcome


def _exception_outcome():
    return adapter_v2.SyntheticProtectedHeldLeasePortAdapterV2._failed(
        "SYNTHETIC_HELD_LEASE_PORT_CALL_FAILED_CLOSED",
        backend_called=True,
        lease_revalidated=True,
        recovery_required=True,
    )


def _committed_outcome(protected_result):
    outcome = adapter_v2.SyntheticProtectedHeldLeasePortAdapterV2._failed(
        "",
        backend_called=True,
        lease_revalidated=True,
    )
    outcome.update(
        {
            "ok": True,
            "status": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_COMMITTED_OFFLINE",
            "reason": None,
            "protected_result": protected_result,
            "terminal_state": "COMMITTED",
            "recovery_required": False,
            "retry_allowed": False,
        }
    )
    return outcome


def _issuer(adapter_plan):
    return obligation_v2.DormantProtectedReconciliationObligationContractV2(
        obligation_v2.DormantProtectedReconciliationObligationConfigV2(
            enabled=True,
            scope_attestation=(
                obligation_v2.OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2
            ),
            expected_adapter_plan_sha256=adapter_plan.plan_sha256,
        )
    )


def _tampered_obligation(protected, **changes):
    obligation = copy.deepcopy(dict(protected.obligation))
    obligation.update(changes)
    obligation["obligation_sha256"] = (
        obligation_v2.protected_reconciliation_obligation_sha256_v2(obligation)
    )
    return obligation_v2.ProtectedReconciliationObligationV2(
        adapter_plan=protected.adapter_plan,
        protected_terminal_result=protected.protected_terminal_result,
        source_evidence=protected.source_evidence,
        obligation=obligation,
        obligation_sha256=obligation["obligation_sha256"],
    )


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationObligationHarnessEvidenceV2:
    terminal_ambiguity_obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(
        repr=False
    )
    post_call_exception_obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationObligationHarnessEvidenceV2(<protected>)"


def protected_reconciliation_obligation_harness_evidence_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedReconciliationObligationHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    try:
        return bool(
            obligation_v2.protected_reconciliation_obligation_valid_v2(
                value.terminal_ambiguity_obligation
            )
            and obligation_v2.protected_reconciliation_obligation_valid_v2(
                value.post_call_exception_obligation
            )
            and evidence["evidence_version"]
            == PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EVIDENCE_VERSION_V2
            and evidence["terminal_ambiguity_obligation_sha256"]
            == value.terminal_ambiguity_obligation.obligation_sha256
            and evidence["post_call_exception_obligation_sha256"]
            == value.post_call_exception_obligation.obligation_sha256
            and evidence["transaction_sha256"]
            == value.terminal_ambiguity_obligation.obligation[
                "transaction_sha256"
            ]
            == value.post_call_exception_obligation.obligation[
                "transaction_sha256"
            ]
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
            and all(
                evidence[key] is False
                for key in (
                    "backend_called",
                    "provider_called",
                    "store_called",
                    "writer_called",
                    "lock_acquired",
                    "filesystem_accessed",
                    "real_registry_accessed",
                    "network_accessed",
                    "broker_called",
                    "write_executed",
                    "production_authority",
                    "runtime_integrated",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_reconciliation_obligation_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def run_protected_reconciliation_obligation_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_V2_VERSION,
        "terminal_ambiguity_obligation": None,
        "post_call_exception_obligation": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        execution = execution_harness.run_protected_held_lease_port_adapter_execution_harness_v2()
        committed_result = execution.get("protected_result")
        if execution.get("ok") is not True or committed_result is None:
            base["reason"] = "UPSTREAM_SYNTHETIC_EXECUTION_INVALID"
            return base
        adapter_plan = committed_result.adapter_plan
        now_epoch = adapter_plan.plan["planned_at_epoch"]
        ambiguous_result = _ambiguous_protected_result(committed_result)
        issuer = _issuer(adapter_plan)
        terminal_ambiguity = issuer.issue_offline(
            adapter_plan,
            _ambiguous_outcome(ambiguous_result),
            now_epoch=now_epoch,
        )
        exception = issuer.issue_offline(
            adapter_plan,
            _exception_outcome(),
            now_epoch=now_epoch,
        )
        terminal_obligation = terminal_ambiguity.get("protected_obligation")
        exception_obligation = exception.get("protected_obligation")
        if (
            terminal_ambiguity.get("ok") is not True
            or exception.get("ok") is not True
            or terminal_obligation is None
            or exception_obligation is None
        ):
            base["reason"] = "PROTECTED_OBLIGATION_ISSUE_FAILED"
            return base
        committed_rejected = issuer.issue_offline(
            adapter_plan,
            _committed_outcome(committed_result),
            now_epoch=now_epoch,
        )
        default_off = obligation_v2.DormantProtectedReconciliationObligationContractV2().issue_offline(
            None,
            None,
            now_epoch=0,
        )
        retry_escalation = _tampered_obligation(
            terminal_obligation,
            retry_allowed=True,
            new_apply_allowed=True,
        )
        resolved_claim = _tampered_obligation(
            terminal_obligation,
            resolution_state="RESOLVED",
            reconciliation_required=False,
        )
        obligation = terminal_obligation.obligation
        checks_by_name = {
            "TERMINAL_AMBIGUITY_OBLIGATION_VALID": obligation_v2.protected_reconciliation_obligation_valid_v2(terminal_obligation) and terminal_obligation.protected_terminal_result is ambiguous_result,
            "POST_CALL_EXCEPTION_OBLIGATION_VALID": obligation_v2.protected_reconciliation_obligation_valid_v2(exception_obligation) and exception_obligation.protected_terminal_result is None,
            "SAME_TRANSACTION_IDENTITY_BOUND": terminal_obligation.obligation["transaction_sha256"] == exception_obligation.obligation["transaction_sha256"] == adapter_plan.protected_request.request["transaction_sha256"],
            "NEW_APPLY_AND_RETRY_FORBIDDEN": obligation["new_apply_allowed"] is False and obligation["retry_allowed"] is False and obligation["reconcile_before_retry_required"] is True,
            "ORIGINAL_AUTHORIZATION_REUSE_FORBIDDEN": obligation["original_authorization_reusable"] is False,
            "FRESH_AUTHORITY_REQUIRED_FOR_RECONCILIATION": obligation["fresh_single_use_authorization_required"] is True and obligation["fresh_maintenance_permit_required"] is True and obligation["fresh_lease_required"] is True,
            "RESOLUTION_RECEIPT_REQUIRED": obligation["resolution_receipt_required"] is True and obligation["terminal_result_required_for_resolution"] is True and obligation["resolution_state"] == "UNRESOLVED",
            "COMMITTED_OUTCOME_REJECTED": committed_rejected["ok"] is False and committed_rejected["reason"] == "POST_CALL_UNCERTAINTY_EVIDENCE_REQUIRED",
            "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "PROTECTED_RECONCILIATION_OBLIGATION_V2_DEFAULT_OFF",
            "RESEALED_RETRY_ESCALATION_REJECTED": not obligation_v2.protected_reconciliation_obligation_valid_v2(retry_escalation),
            "RESEALED_RESOLUTION_CLAIM_REJECTED": not obligation_v2.protected_reconciliation_obligation_valid_v2(resolved_claim),
            "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT": all(terminal_ambiguity[key] is False for key in ("backend_called", "provider_called", "store_called", "writer_called", "lock_acquired", "filesystem_accessed", "real_registry_accessed", "network_accessed", "broker_called", "write_executed", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")),
        }
        checks = [
            {"name": name, "passed": checks_by_name[name] is True}
            for name in _CHECK_NAMES
        ]
        if not all(item["passed"] for item in checks):
            base["reason"] = "PROTECTED_RECONCILIATION_OBLIGATION_ORACLE_FAILED"
            return base
        evidence = {
            "evidence_version": PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EVIDENCE_VERSION_V2,
            "terminal_ambiguity_obligation_sha256": terminal_obligation.obligation_sha256,
            "post_call_exception_obligation_sha256": exception_obligation.obligation_sha256,
            "transaction_sha256": obligation["transaction_sha256"],
            "checks": checks,
            "check_count": len(checks),
            "passed_count": sum(item["passed"] for item in checks),
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        evidence["evidence_sha256"] = (
            protected_reconciliation_obligation_harness_evidence_sha256_v2(
                evidence
            )
        )
        protected_evidence = ProtectedReconciliationObligationHarnessEvidenceV2(
            terminal_ambiguity_obligation=terminal_obligation,
            post_call_exception_obligation=exception_obligation,
            evidence=copy.deepcopy(evidence),
            evidence_sha256=evidence["evidence_sha256"],
        )
        if not protected_reconciliation_obligation_harness_evidence_valid_v2(
            protected_evidence
        ):
            base["reason"] = "PROTECTED_OBLIGATION_EVIDENCE_INTERNAL_INVALID"
            return base
    except Exception:
        base["reason"] = "PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_PASSED_OFFLINE",
            "terminal_ambiguity_obligation": terminal_obligation,
            "post_call_exception_obligation": exception_obligation,
            "protected_evidence": protected_evidence,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
        }
    )
    return base


__all__ = [
    "PROTECTED_RECONCILIATION_OBLIGATION_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedReconciliationObligationHarnessEvidenceV2",
    "protected_reconciliation_obligation_harness_evidence_sha256_v2",
    "protected_reconciliation_obligation_harness_evidence_valid_v2",
    "run_protected_reconciliation_obligation_harness_v2",
]
