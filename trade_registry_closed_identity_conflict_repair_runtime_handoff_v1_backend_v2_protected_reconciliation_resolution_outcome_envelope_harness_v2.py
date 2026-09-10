"""Offline compatibility harness for native C3 resolution receipt envelopes."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_harness_v2 as durable_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2 as envelope_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as legacy_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as legacy_harness_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESOLUTION-OUTCOME-ENVELOPE-HARNESS-V2"
)
_CHECK_NAMES = (
    "LEGACY_NATIVE_VALIDATOR_REQUIRED",
    "DURABLE_NATIVE_VALIDATOR_REQUIRED",
    "COMMON_IDENTITY_VECTOR_PRESERVED",
    "DURABLE_IDENTITY_VECTOR_TAMPERING_REJECTED",
    "SOURCE_SEMANTICS_REMAIN_DISTINCT",
    "NO_RECEIPT_TYPE_CONVERSION",
    "WRONG_SOURCE_DISCRIMINATOR_REJECTED",
    "RECONSTRUCTED_SOURCE_INSTANCE_REJECTED",
    "RESEALED_DISCRIMINATOR_SUBSTITUTION_REJECTED",
    "DEFAULT_OFF_BEFORE_INPUT_INSPECTION",
    "NO_RUNTIME_NETWORK_BROKER_WRITE_OR_ORDER",
)


def _contract(source_kind: str, source: Any):
    return envelope_v2.DormantResolutionOutcomeEnvelopeContractV2(
        envelope_v2.DormantResolutionOutcomeEnvelopeConfigV2(
            enabled=True,
            scope_attestation=envelope_v2.OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2,
            expected_source_kind=source_kind,
            expected_source_receipt_sha256=source.receipt_sha256,
            expected_obligation_sha256=source.receipt["obligation_sha256"],
            expected_transaction_sha256=source.receipt["transaction_sha256"],
        ),
        protected_source_receipt=source,
    )


def run_resolution_outcome_envelope_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_VERSION,
        "legacy_envelope": None,
        "durable_envelope": None,
        "legacy_obligation": None,
        "durable_obligation": None,
        "checks": [],
        "check_count": 0,
        "passed_count": 0,
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
        default_off = envelope_v2.DormantResolutionOutcomeEnvelopeContractV2().issue_offline(None)
        legacy_result = legacy_harness_v2.run_protected_reconciliation_resolution_receipt_harness_v2()
        durable_result = durable_harness_v2.run_durable_resolution_commit_harness_v2()
        legacy = legacy_result.get("protected_receipt")
        durable = durable_result.get("protected_receipt")
        if legacy_result.get("ok") is not True or durable_result.get("ok") is not True or legacy is None or durable is None:
            base["reason"] = "NATIVE_SOURCE_RECEIPT_HARNESS_FAILED"
            return base
        legacy_contract = _contract(envelope_v2.ORIGINAL_SESSION_RECEIPT_SOURCE_V2, legacy)
        durable_contract = _contract(envelope_v2.DURABLE_RESTART_RECEIPT_SOURCE_V2, durable)
        legacy_issued = legacy_contract.issue_offline(legacy)
        durable_issued = durable_contract.issue_offline(durable)
        legacy_envelope = legacy_issued.get("protected_envelope")
        durable_envelope = durable_issued.get("protected_envelope")
        if legacy_envelope is None or durable_envelope is None:
            base["reason"] = "NATIVE_SOURCE_ENVELOPE_NOT_ISSUED"
            return base
        wrong_kind = _contract(envelope_v2.DURABLE_RESTART_RECEIPT_SOURCE_V2, legacy).issue_offline(legacy)
        reconstructed_legacy = legacy_v2.ProtectedReconciliationResolutionReceiptV2(
            obligation=legacy.obligation,
            fresh_authority=legacy.fresh_authority,
            protected_restart_barrier=legacy.protected_restart_barrier,
            terminal_resolution_evidence=legacy.terminal_resolution_evidence,
            single_use_consumption_receipt=legacy.single_use_consumption_receipt,
            receipt=legacy.receipt,
            receipt_sha256=legacy.receipt_sha256,
        )
        reconstructed = legacy_contract.issue_offline(reconstructed_legacy)
        tampered_record = copy.deepcopy(dict(legacy_envelope.envelope))
        tampered_record["source_kind"] = envelope_v2.DURABLE_RESTART_RECEIPT_SOURCE_V2
        tampered_record["envelope_sha256"] = envelope_v2.resolution_outcome_envelope_sha256_v2(tampered_record)
        tampered = envelope_v2.ProtectedResolutionOutcomeEnvelopeV2(
            native_source_receipt=legacy,
            envelope=tampered_record,
            envelope_sha256=tampered_record["envelope_sha256"],
        )
        legacy_record = legacy_envelope.envelope
        durable_record = durable_envelope.envelope
        common_keys = (
            "obligation_sha256", "obligation_id_sha256",
            "source_evidence_sha256", "adapter_plan_sha256",
            "request_binding_sha256", "request_sha256", "transaction_sha256",
            "terminal_resolution_evidence_sha256", "terminal_state",
            "resolved_at_epoch",
        )
        durable_identity_record_keys = (
            "resolution_source_evidence_sha256",
            "resolution_adapter_plan_sha256",
            "resolution_request_binding_sha256",
            "resolution_request_sha256",
        )
        identity_tampering_rejected = True
        for key in durable_identity_record_keys:
            tampered_durable_record = copy.deepcopy(
                dict(durable.resolved_durable_authority_receipt.record)
            )
            tampered_durable_record[key] = "0" * 64
            identity_tampering_rejected = bool(
                identity_tampering_rejected
                and not durable_authority_v2.durable_authority_record_valid_v2(
                    tampered_durable_record
                )
            )
        checks_by_name = {
            "LEGACY_NATIVE_VALIDATOR_REQUIRED": legacy_issued["ok"] is True and legacy_record["source_native_validator_passed"] is True and legacy_envelope.native_source_receipt is legacy,
            "DURABLE_NATIVE_VALIDATOR_REQUIRED": durable_issued["ok"] is True and durable_record["source_native_validator_passed"] is True and durable_envelope.native_source_receipt is durable,
            "COMMON_IDENTITY_VECTOR_PRESERVED": all(legacy_record[key] is not None and durable_record[key] is not None for key in common_keys) and all(durable_record[key] == durable.receipt[key] for key in common_keys if key != "terminal_resolution_evidence_sha256"),
            "DURABLE_IDENTITY_VECTOR_TAMPERING_REJECTED": identity_tampering_rejected,
            "SOURCE_SEMANTICS_REMAIN_DISTINCT": legacy_record["original_session_continuity_verified"] is True and legacy_record["durable_atomic_commit_verified"] is False and durable_record["original_session_continuity_verified"] is False and durable_record["durable_atomic_commit_verified"] is True and durable_record["restart_reconstructible"] is True,
            "NO_RECEIPT_TYPE_CONVERSION": legacy_record["conversion_performed"] is False and durable_record["conversion_performed"] is False and legacy_record["fabricated_session_evidence"] is False and durable_record["fabricated_session_evidence"] is False,
            "WRONG_SOURCE_DISCRIMINATOR_REJECTED": wrong_kind["ok"] is False and wrong_kind["reason"] == "NATIVE_SOURCE_RECEIPT_INVALID_FOR_KIND",
            "RECONSTRUCTED_SOURCE_INSTANCE_REJECTED": reconstructed["ok"] is False and reconstructed["reason"] == "NATIVE_SOURCE_RECEIPT_INSTANCE_NOT_PINNED",
            "RESEALED_DISCRIMINATOR_SUBSTITUTION_REJECTED": envelope_v2.protected_resolution_outcome_envelope_valid_v2(tampered) is False,
            "DEFAULT_OFF_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "RESOLUTION_OUTCOME_ENVELOPE_V2_DEFAULT_OFF",
            "NO_RUNTIME_NETWORK_BROKER_WRITE_OR_ORDER": all(legacy_issued[key] is False and durable_issued[key] is False for key in ("write_executed", "real_registry_accessed", "network_accessed", "broker_called", "runtime_integrated", "activation_allowed", "live_allowed")) and legacy_issued["no_order_sent"] is True and durable_issued["no_order_sent"] is True,
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
                "status": "RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_PASSED" if ok else "RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_FAILED_CLOSED",
                "reason": None if ok else "ONE_OR_MORE_CHECKS_FAILED",
                "legacy_envelope": legacy_envelope,
                "durable_envelope": durable_envelope,
                "legacy_obligation": legacy.obligation,
                "durable_obligation": durable_result["source_obligation"],
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_OUTCOME_ENVELOPE_HARNESS_V2_VERSION",
    "run_resolution_outcome_envelope_harness_v2",
]
