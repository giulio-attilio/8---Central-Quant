"""Synthetic harness for the dormant raw transaction rehearsal V2."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_composition_contract_v2 as composition
import trade_registry_closed_identity_conflict_repair_raw_composition_harness_v2 as composition_harness
import trade_registry_closed_identity_conflict_repair_raw_transaction_rehearsal_offline_v2 as rehearsal


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_HARNESS_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-TRANSACTION-REHEARSAL-HARNESS-V2"
)


def build_synthetic_raw_transaction_rehearsal_inputs_v2() -> dict[str, Any]:
    composition_inputs = composition_harness.build_synthetic_raw_composition_inputs_v2()
    composition_result = composition.compose_closed_identity_conflict_raw_preview_offline_v2(
        **composition_inputs
    )
    if composition_result.get("ok") is not True:
        raise AssertionError("synthetic raw composition unexpectedly failed")
    return {
        **copy.deepcopy(composition_inputs),
        "composition_preview_receipt": copy.deepcopy(
            composition_result["preview_receipt"]
        ),
        "candidate_snapshot": copy.deepcopy(composition_result["candidate_snapshot"]),
    }


def run_synthetic_raw_transaction_rehearsal_harness_v2() -> dict[str, Any]:
    inputs = build_synthetic_raw_transaction_rehearsal_inputs_v2()
    before = copy.deepcopy(inputs)
    before_sha = rehearsal._stable_sha256(before)
    first = rehearsal.rehearse_closed_identity_conflict_raw_transaction_offline_v2(
        **inputs
    )
    second = rehearsal.rehearse_closed_identity_conflict_raw_transaction_offline_v2(
        **copy.deepcopy(inputs)
    )
    after_sha = rehearsal._stable_sha256(inputs)
    transaction = first.get("transaction")
    source_document = inputs["raw_registry_snapshot"]["raw_registry_document"]
    candidate_document = inputs["candidate_snapshot"]["raw_registry_document"]
    original_state = (
        rehearsal.classify_raw_registry_document_against_rehearsal_offline_v2(
            source_document, transaction
        )
        if isinstance(transaction, dict)
        else {}
    )
    candidate_state = (
        rehearsal.classify_raw_registry_document_against_rehearsal_offline_v2(
            candidate_document, transaction
        )
        if isinstance(transaction, dict)
        else {}
    )
    ok = bool(
        first.get("ok") is True
        and first.get("transaction_verified") is True
        and first.get("translation_allowed") is False
        and first.get("apply_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and first.get("runtime_integrated") is False
        and first.get("broker_called") is False
        and isinstance(transaction, dict)
        and transaction.get("state") == "REHEARSED_NOT_APPLIED"
        and transaction.get("rollback_envelope", {}).get("rollback_verified") is True
        and transaction.get("translation_allowed") is False
        and transaction.get("apply_allowed") is False
        and original_state.get("state") == "ORIGINAL"
        and candidate_state.get("state") == "CANDIDATE_ALREADY_PRESENT"
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "RAW_TRANSACTION_REHEARSAL_V2_HARNESS_PASSED_NOT_APPLIED"
            if ok
            else "RAW_TRANSACTION_REHEARSAL_V2_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_HARNESS_V2_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "translation_allowed": False,
        "apply_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "original_state": original_state,
        "candidate_state": candidate_state,
        "rehearsal_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_HARNESS_V2_VERSION",
    "build_synthetic_raw_transaction_rehearsal_inputs_v2",
    "run_synthetic_raw_transaction_rehearsal_harness_v2",
]
