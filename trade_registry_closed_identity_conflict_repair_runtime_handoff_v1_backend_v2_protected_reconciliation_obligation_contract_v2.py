"""Default-off offline contract for a protected reconciliation obligation.

An obligation may be issued only from a valid AMBIGUOUS terminal result or a
sanitized post-call uncertainty. It blocks apply/retry until reconciliation is
resolved under fresh authority. This module never calls a backend or runtime.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2 as adapter_contract_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2 as adapter_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_OBLIGATION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-OBLIGATION-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_OBLIGATION_OFFLINE_ONLY"
)
PROTECTED_RECONCILIATION_SOURCE_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_SOURCE_EVIDENCE_V2"
)
PROTECTED_RECONCILIATION_OBLIGATION_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_OBLIGATION_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POST_CALL_REASONS = {
    "SYNTHETIC_HELD_LEASE_PORT_CALL_FAILED_CLOSED": "PORT_CALL_EXCEPTION",
    "SYNTHETIC_PORT_POST_CALL_COUNTERS_MISSING": "POST_CALL_COUNTERS_UNKNOWN",
    "NON_REENTRANT_PORT_COUNTER_INVARIANT_VIOLATED": "LOCK_INVARIANT_VIOLATION",
    "SYNTHETIC_TERMINAL_RESULT_INVALID": "TERMINAL_RESULT_INVALID",
    "PROTECTED_SYNTHETIC_RESULT_INTERNAL_INVALID": "PROTECTED_RESULT_INVALID",
}
_SOURCE_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "adapter_plan_sha256",
        "materialized_request_envelope_sha256",
        "request_binding_sha256",
        "request_sha256",
        "transaction_sha256",
        "cas_witness_sha256",
        "cause_kind",
        "reason_code",
        "terminal_state",
        "terminal_result_sha256",
        "backend_call_count",
        "backend_called",
        "lease_revalidation_count",
        "recovery_required",
        "retry_allowed",
        "raw_result_retained",
        "synthetic_only",
        "production_authority",
        "evidence_sha256",
    }
)
_OBLIGATION_KEYS = frozenset(
    {
        "obligation_version",
        "scope_attestation",
        "obligation_id_sha256",
        "source_evidence_sha256",
        "adapter_plan_sha256",
        "materialized_request_envelope_sha256",
        "request_binding_sha256",
        "request_sha256",
        "transaction_sha256",
        "idempotency_key_sha256",
        "authorization_receipt_sha256",
        "cas_witness_sha256",
        "cause_kind",
        "terminal_state",
        "created_at_epoch",
        "resolution_state",
        "reconciliation_required",
        "new_apply_allowed",
        "retry_allowed",
        "original_authorization_reusable",
        "same_transaction_identity_required",
        "fresh_single_use_authorization_required",
        "fresh_maintenance_permit_required",
        "fresh_lease_required",
        "reconcile_before_retry_required",
        "required_reconciliation_method",
        "resolution_receipt_required",
        "terminal_result_required_for_resolution",
        "backend_bound",
        "backend_call_allowed",
        "synthetic_only",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "obligation_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def protected_reconciliation_source_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _hash_without(value, "evidence_sha256")


def protected_reconciliation_obligation_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _hash_without(value, "obligation_sha256")


def _source_evidence_valid_v2(
    value: Any,
    adapter_plan: adapter_contract_v2.ProtectedHeldLeasePortAdapterPlanV2,
    protected_terminal_result: Any,
) -> bool:
    if type(value) is not dict or set(value) != _SOURCE_EVIDENCE_KEYS:
        return False
    protected_request = adapter_plan.protected_request
    request = protected_request.request
    terminal_sha = backend_v2.stable_sha256_v2(
        {"no_terminal_result": adapter_plan.plan_sha256}
    )
    if protected_terminal_result is not None:
        if not adapter_v2.protected_held_lease_port_invocation_result_valid_v2(
            protected_terminal_result
        ):
            return False
        if protected_terminal_result.adapter_plan is not adapter_plan:
            return False
        terminal_sha = protected_terminal_result.terminal_result["result_sha256"]
    try:
        return bool(
            value["evidence_version"]
            == PROTECTED_RECONCILIATION_SOURCE_EVIDENCE_VERSION_V2
            and value["adapter_plan_sha256"] == adapter_plan.plan_sha256
            and value["materialized_request_envelope_sha256"]
            == protected_request.envelope_sha256
            and value["request_binding_sha256"]
            == request["request_binding_sha256"]
            and value["request_sha256"] == request["request_sha256"]
            and value["transaction_sha256"] == request["transaction_sha256"]
            and value["cas_witness_sha256"]
            == adapter_plan.cas_witness.witness_sha256
            and value["cause_kind"]
            in {"TERMINAL_RESULT_AMBIGUOUS", *_POST_CALL_REASONS.values()}
            and value["reason_code"]
            in {
                "SYNTHETIC_TRANSACTION_AMBIGUOUS_RECONCILIATION_REQUIRED",
                *_POST_CALL_REASONS.keys(),
            }
            and value["terminal_state"] in {"AMBIGUOUS", "UNKNOWN"}
            and value["terminal_result_sha256"] == terminal_sha
            and value["backend_call_count"] == 1
            and value["backend_called"] is True
            and value["lease_revalidation_count"] == 1
            and value["recovery_required"] is True
            and value["retry_allowed"] is False
            and value["raw_result_retained"] is False
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and _valid_sha(value["evidence_sha256"])
            and hmac.compare_digest(
                value["evidence_sha256"],
                protected_reconciliation_source_evidence_sha256_v2(value),
            )
            and (
                protected_terminal_result is not None
                and value["cause_kind"] == "TERMINAL_RESULT_AMBIGUOUS"
                and value["reason_code"]
                == "SYNTHETIC_TRANSACTION_AMBIGUOUS_RECONCILIATION_REQUIRED"
                and value["terminal_state"] == "AMBIGUOUS"
                and protected_terminal_result.terminal_result["terminal_state"]
                == "AMBIGUOUS"
                and protected_terminal_result.terminal_result[
                    "recovery_required"
                ]
                is True
                or protected_terminal_result is None
                and value["cause_kind"]
                == _POST_CALL_REASONS[value["reason_code"]]
                and value["terminal_state"] == "UNKNOWN"
            )
        )
    except Exception:
        return False


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationObligationV2:
    adapter_plan: adapter_contract_v2.ProtectedHeldLeasePortAdapterPlanV2 = field(
        repr=False
    )
    protected_terminal_result: Any = field(repr=False)
    source_evidence: Mapping[str, Any] = field(repr=False)
    obligation: Mapping[str, Any] = field(repr=False)
    obligation_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationObligationV2(<protected>)"


@dataclass(frozen=True)
class DormantProtectedReconciliationObligationConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_plan_sha256: str | None = field(default=None, repr=False)


def protected_reconciliation_obligation_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedReconciliationObligationV2:
        return False
    adapter_plan = value.adapter_plan
    if not adapter_contract_v2.protected_held_lease_port_adapter_plan_valid_v2(
        adapter_plan
    ):
        return False
    if not _source_evidence_valid_v2(
        value.source_evidence,
        adapter_plan,
        value.protected_terminal_result,
    ):
        return False
    obligation = value.obligation
    if type(obligation) is not dict or set(obligation) != _OBLIGATION_KEYS:
        return False
    protected_request = adapter_plan.protected_request
    request = protected_request.request
    evidence = value.source_evidence
    expected_id = backend_v2.stable_sha256_v2(
        {
            "adapter_plan_sha256": adapter_plan.plan_sha256,
            "transaction_sha256": request["transaction_sha256"],
            "source_evidence_sha256": evidence["evidence_sha256"],
            "cause_kind": evidence["cause_kind"],
        }
    )
    try:
        return bool(
            obligation["obligation_version"]
            == PROTECTED_RECONCILIATION_OBLIGATION_VERSION_V2
            and obligation["scope_attestation"]
            == OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2
            and obligation["obligation_id_sha256"] == expected_id
            and obligation["source_evidence_sha256"]
            == evidence["evidence_sha256"]
            and obligation["adapter_plan_sha256"] == adapter_plan.plan_sha256
            and obligation["materialized_request_envelope_sha256"]
            == protected_request.envelope_sha256
            and obligation["request_binding_sha256"]
            == request["request_binding_sha256"]
            and obligation["request_sha256"] == request["request_sha256"]
            and obligation["transaction_sha256"] == request["transaction_sha256"]
            and obligation["idempotency_key_sha256"]
            == backend_v2.stable_sha256_v2(request["idempotency_key"])
            and obligation["authorization_receipt_sha256"]
            == request["authorization_receipt_sha256"]
            and obligation["cas_witness_sha256"]
            == adapter_plan.cas_witness.witness_sha256
            and obligation["cause_kind"] == evidence["cause_kind"]
            and obligation["terminal_state"] == evidence["terminal_state"]
            and type(obligation["created_at_epoch"]) is int
            and obligation["created_at_epoch"]
            >= adapter_plan.plan["planned_at_epoch"]
            and obligation["resolution_state"] == "UNRESOLVED"
            and obligation["reconciliation_required"] is True
            and obligation["new_apply_allowed"] is False
            and obligation["retry_allowed"] is False
            and obligation["original_authorization_reusable"] is False
            and obligation["same_transaction_identity_required"] is True
            and obligation["fresh_single_use_authorization_required"] is True
            and obligation["fresh_maintenance_permit_required"] is True
            and obligation["fresh_lease_required"] is True
            and obligation["reconcile_before_retry_required"] is True
            and obligation["required_reconciliation_method"]
            == "reconcile_under_fresh_maintenance_lease"
            and obligation["resolution_receipt_required"] is True
            and obligation["terminal_result_required_for_resolution"] is True
            and obligation["backend_bound"] is False
            and obligation["backend_call_allowed"] is False
            and obligation["synthetic_only"] is True
            and obligation["production_authority"] is False
            and obligation["runtime_integrated"] is False
            and obligation["activation_allowed"] is False
            and obligation["live_allowed"] is False
            and value.obligation_sha256 == obligation["obligation_sha256"]
            and _valid_sha(obligation["obligation_sha256"])
            and hmac.compare_digest(
                obligation["obligation_sha256"],
                protected_reconciliation_obligation_sha256_v2(obligation),
            )
        )
    except Exception:
        return False


class DormantProtectedReconciliationObligationContractV2:
    def __init__(
        self,
        config: DormantProtectedReconciliationObligationConfigV2 | None = None,
    ) -> None:
        self._config = (
            config or DormantProtectedReconciliationObligationConfigV2()
        )

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_RECONCILIATION_OBLIGATION_V2_BLOCKED",
            "reason": reason,
            "protected_obligation": None,
            "reconciliation_required": False,
            "retry_allowed": False,
            "new_apply_allowed": False,
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

    def issue_offline(
        self,
        adapter_plan: adapter_contract_v2.ProtectedHeldLeasePortAdapterPlanV2,
        invocation_outcome: Mapping[str, Any],
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_V2_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2
        ):
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_REQUIRED")
        if not adapter_contract_v2.protected_held_lease_port_adapter_plan_valid_v2(
            adapter_plan
        ):
            return self._failed("PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_INVALID")
        if not (
            _valid_sha(self._config.expected_adapter_plan_sha256)
            and hmac.compare_digest(
                str(self._config.expected_adapter_plan_sha256),
                adapter_plan.plan_sha256,
            )
        ):
            return self._failed("PROTECTED_ADAPTER_PLAN_PIN_MISMATCH")
        if type(invocation_outcome) is not dict or type(now_epoch) is not int:
            return self._failed("RECONCILIATION_SOURCE_OUTCOME_INVALID")
        if not (
            invocation_outcome.get("ok") is False
            and invocation_outcome.get("backend_called") is True
            and invocation_outcome.get("backend_call_count") == 1
            and invocation_outcome.get("lease_revalidation_count") == 1
            and invocation_outcome.get("recovery_required") is True
            and invocation_outcome.get("retry_allowed") is False
            and invocation_outcome.get("raw_result_exposed") is False
            and now_epoch >= adapter_plan.plan["planned_at_epoch"]
        ):
            return self._failed("POST_CALL_UNCERTAINTY_EVIDENCE_REQUIRED")
        protected_terminal_result = invocation_outcome.get("protected_result")
        reason = invocation_outcome.get("reason")
        if protected_terminal_result is not None:
            if not (
                adapter_v2.protected_held_lease_port_invocation_result_valid_v2(
                    protected_terminal_result
                )
                and protected_terminal_result.adapter_plan is adapter_plan
                and protected_terminal_result.terminal_result["terminal_state"]
                == "AMBIGUOUS"
                and protected_terminal_result.terminal_result[
                    "recovery_required"
                ]
                is True
                and invocation_outcome.get("terminal_state") == "AMBIGUOUS"
                and reason
                == "SYNTHETIC_TRANSACTION_AMBIGUOUS_RECONCILIATION_REQUIRED"
            ):
                return self._failed("AMBIGUOUS_TERMINAL_RESULT_INVALID")
            cause_kind = "TERMINAL_RESULT_AMBIGUOUS"
            terminal_state = "AMBIGUOUS"
            terminal_result_sha256 = protected_terminal_result.terminal_result[
                "result_sha256"
            ]
        else:
            if reason not in _POST_CALL_REASONS or invocation_outcome.get(
                "terminal_state"
            ) is not None:
                return self._failed("SANITIZED_POST_CALL_FAILURE_INVALID")
            cause_kind = _POST_CALL_REASONS[reason]
            terminal_state = "UNKNOWN"
            terminal_result_sha256 = backend_v2.stable_sha256_v2(
                {"no_terminal_result": adapter_plan.plan_sha256}
            )
        protected_request = adapter_plan.protected_request
        request = protected_request.request
        source_evidence = {
            "evidence_version": PROTECTED_RECONCILIATION_SOURCE_EVIDENCE_VERSION_V2,
            "adapter_plan_sha256": adapter_plan.plan_sha256,
            "materialized_request_envelope_sha256": protected_request.envelope_sha256,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "cas_witness_sha256": adapter_plan.cas_witness.witness_sha256,
            "cause_kind": cause_kind,
            "reason_code": reason,
            "terminal_state": terminal_state,
            "terminal_result_sha256": terminal_result_sha256,
            "backend_call_count": 1,
            "backend_called": True,
            "lease_revalidation_count": 1,
            "recovery_required": True,
            "retry_allowed": False,
            "raw_result_retained": False,
            "synthetic_only": True,
            "production_authority": False,
        }
        source_evidence["evidence_sha256"] = (
            protected_reconciliation_source_evidence_sha256_v2(source_evidence)
        )
        obligation_id = backend_v2.stable_sha256_v2(
            {
                "adapter_plan_sha256": adapter_plan.plan_sha256,
                "transaction_sha256": request["transaction_sha256"],
                "source_evidence_sha256": source_evidence["evidence_sha256"],
                "cause_kind": cause_kind,
            }
        )
        obligation = {
            "obligation_version": PROTECTED_RECONCILIATION_OBLIGATION_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2,
            "obligation_id_sha256": obligation_id,
            "source_evidence_sha256": source_evidence["evidence_sha256"],
            "adapter_plan_sha256": adapter_plan.plan_sha256,
            "materialized_request_envelope_sha256": protected_request.envelope_sha256,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "idempotency_key_sha256": backend_v2.stable_sha256_v2(
                request["idempotency_key"]
            ),
            "authorization_receipt_sha256": request[
                "authorization_receipt_sha256"
            ],
            "cas_witness_sha256": adapter_plan.cas_witness.witness_sha256,
            "cause_kind": cause_kind,
            "terminal_state": terminal_state,
            "created_at_epoch": now_epoch,
            "resolution_state": "UNRESOLVED",
            "reconciliation_required": True,
            "new_apply_allowed": False,
            "retry_allowed": False,
            "original_authorization_reusable": False,
            "same_transaction_identity_required": True,
            "fresh_single_use_authorization_required": True,
            "fresh_maintenance_permit_required": True,
            "fresh_lease_required": True,
            "reconcile_before_retry_required": True,
            "required_reconciliation_method": "reconcile_under_fresh_maintenance_lease",
            "resolution_receipt_required": True,
            "terminal_result_required_for_resolution": True,
            "backend_bound": False,
            "backend_call_allowed": False,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        obligation["obligation_sha256"] = (
            protected_reconciliation_obligation_sha256_v2(obligation)
        )
        protected_obligation = ProtectedReconciliationObligationV2(
            adapter_plan=adapter_plan,
            protected_terminal_result=protected_terminal_result,
            source_evidence=copy.deepcopy(source_evidence),
            obligation=copy.deepcopy(obligation),
            obligation_sha256=obligation["obligation_sha256"],
        )
        if not protected_reconciliation_obligation_valid_v2(
            protected_obligation
        ):
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_RECONCILIATION_OBLIGATION_ISSUED_OFFLINE",
                "reason": None,
                "protected_obligation": protected_obligation,
                "obligation_sha256": protected_obligation.obligation_sha256,
                "obligation_id_sha256": obligation_id,
                "cause_kind": cause_kind,
                "reconciliation_required": True,
            }
        )
        return result


__all__ = [
    "DormantProtectedReconciliationObligationConfigV2",
    "DormantProtectedReconciliationObligationContractV2",
    "OFFLINE_PROTECTED_RECONCILIATION_OBLIGATION_SCOPE_ATTESTATION_V2",
    "PROTECTED_RECONCILIATION_OBLIGATION_VERSION_V2",
    "ProtectedReconciliationObligationV2",
    "protected_reconciliation_obligation_sha256_v2",
    "protected_reconciliation_obligation_valid_v2",
    "protected_reconciliation_source_evidence_sha256_v2",
]
