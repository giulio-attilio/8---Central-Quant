"""Dormant raw transaction rehearsal V2 for synthetic CLOSED repairs.

The rehearsal revalidates the complete raw composition preview, then builds an
in-memory transaction, immutable backup, inverse rollback and deterministic
idempotency identity.  No returned state can authorize translation, apply,
persistence, runtime integration or trading.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_composition_contract_v2 as composition
import trade_registry_closed_identity_conflict_repair_raw_path_binding_contract_v1 as raw_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_OFFLINE_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-TRANSACTION-REHEARSAL-OFFLINE-V2"
)

_OPERATION = "SYNTHETIC_RAW_CLOSED_IDENTITY_CONFLICT_REPAIR_REHEARSAL_V2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _ordered_json_copy(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def raw_repair_rehearsal_transaction_sha256_v2(
    transaction: Mapping[str, Any],
) -> str:
    if not isinstance(transaction, Mapping):
        raise TypeError("transaction must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in transaction.items()
            if key != "transaction_sha256"
        }
    )


def _write_path(record: dict[str, Any], path: str, value: Any) -> bool:
    parts = path.split(".")
    if len(parts) < 2 or parts[0] != "trade" or any(not part for part in parts):
        return False
    current: Any = record
    for part in parts[1:-1]:
        if not isinstance(current, dict) or not isinstance(current.get(part), dict):
            return False
        current = current[part]
    field = parts[-1]
    if not isinstance(current, dict) or field not in current:
        return False
    current[field] = copy.deepcopy(value)
    return True


def _mutable_record_at_locator(
    document: dict[str, Any], binding: Mapping[str, Any]
) -> dict[str, Any] | None:
    closed = document.get("closed_trades")
    index = binding.get("registry_index")
    key = binding.get("registry_collection_key")
    if binding.get("collection_shape") == "list" and isinstance(closed, list):
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(closed):
            return None
        record = closed[index]
    elif binding.get("collection_shape") == "dict" and isinstance(closed, dict):
        keys = list(closed)
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not isinstance(key, str)
            or not 0 <= index < len(keys)
            or keys[index] != key
        ):
            return None
        record = closed.get(key)
    else:
        return None
    return record if isinstance(record, dict) else None


def _rollback_candidate_document(
    candidate_document: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
    reasons: list[str],
) -> dict[str, Any]:
    rollback = _ordered_json_copy(candidate_document)
    for entry in reversed(entries):
        record = _mutable_record_at_locator(rollback, entry)
        before_values = entry.get("before_values")
        changed_paths = entry.get("changed_paths")
        if (
            record is None
            or not isinstance(before_values, Mapping)
            or not isinstance(changed_paths, list)
        ):
            reasons.append("RAW_REHEARSAL_ROLLBACK_ENTRY_INVALID")
            continue
        for path_value in changed_paths:
            path = str(path_value)
            if path not in before_values or not _write_path(
                record, path, before_values[path]
            ):
                reasons.append("RAW_REHEARSAL_ROLLBACK_PATH_RESTORE_FAILED")
    return rollback


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "rehearsal_allowed": False,
        "transaction_verified": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "status": "RAW_CLOSED_IDENTITY_CONFLICT_TRANSACTION_REHEARSAL_V2_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_OFFLINE_V2_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "in_memory_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "persistence_allowed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "transaction": None,
    }


def rehearse_closed_identity_conflict_raw_transaction_offline_v2(
    planner_plan: Mapping[str, Any],
    raw_registry_snapshot: Mapping[str, Any],
    raw_path_inventory: Mapping[str, Any],
    composition_preview_receipt: Mapping[str, Any],
    candidate_snapshot: Mapping[str, Any],
    *,
    expected_legacy_count: int = 151,
    expected_financial_count: int = 1,
    max_proposals: int = 152,
) -> dict[str, Any]:
    """Rehearse a fully bound raw transaction without applying anything."""

    base = _base()
    reasons: list[str] = base["reasons"]
    values = (
        planner_plan,
        raw_registry_snapshot,
        raw_path_inventory,
        composition_preview_receipt,
        candidate_snapshot,
    )
    if not all(isinstance(value, Mapping) for value in values):
        reasons.append("RAW_REHEARSAL_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        plan_copy, snapshot_copy, inventory_copy, receipt_copy, candidate_copy = (
            _ordered_json_copy(value) for value in values
        )
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_REHEARSAL_INPUT_NOT_CANONICALIZABLE")
        return base

    receipt_sha = _valid_sha256(receipt_copy.get("receipt_sha256"))
    if not receipt_sha or not hmac.compare_digest(
        receipt_sha,
        composition.raw_composition_preview_receipt_sha256_v2(receipt_copy),
    ):
        reasons.append("RAW_COMPOSITION_PREVIEW_RECEIPT_SHA256_MISMATCH")
    candidate_sha = _valid_sha256(candidate_copy.get("candidate_snapshot_sha256"))
    if not candidate_sha or not hmac.compare_digest(
        candidate_sha,
        composition.raw_composition_candidate_snapshot_sha256_v2(candidate_copy),
    ):
        reasons.append("RAW_COMPOSITION_CANDIDATE_SNAPSHOT_SHA256_MISMATCH")
    if (
        receipt_copy.get("translation_allowed") is not False
        or receipt_copy.get("apply_allowed") is not False
        or candidate_copy.get("translation_allowed") is not False
        or candidate_copy.get("apply_allowed") is not False
        or receipt_copy.get("round_trip_verified") is not True
    ):
        reasons.append("RAW_COMPOSITION_INPUT_SAFETY_ENVELOPE_INVALID")

    recomputed = composition.compose_closed_identity_conflict_raw_preview_offline_v2(
        plan_copy,
        snapshot_copy,
        inventory_copy,
        expected_legacy_count=expected_legacy_count,
        expected_financial_count=expected_financial_count,
        max_proposals=max_proposals,
    )
    if recomputed.get("ok") is not True:
        reasons.append("RAW_COMPOSITION_PREVIEW_RECOMPUTATION_FAILED")
        reasons.extend(recomputed.get("reasons") or [])
    elif (
        recomputed.get("preview_receipt") != receipt_copy
        or recomputed.get("candidate_snapshot") != candidate_copy
    ):
        reasons.append("RAW_COMPOSITION_PREVIEW_RECOMPUTATION_MISMATCH")
    if reasons:
        reasons[:] = sorted(set(str(item) for item in reasons))
        return base

    source_document = snapshot_copy.get("raw_registry_document")
    candidate_document = candidate_copy.get("raw_registry_document")
    entries = receipt_copy.get("entries")
    if (
        not isinstance(source_document, Mapping)
        or not isinstance(candidate_document, Mapping)
        or not isinstance(entries, list)
        or any(not isinstance(entry, Mapping) for entry in entries)
    ):
        reasons.append("RAW_REHEARSAL_COMPOSITION_PAYLOAD_INVALID")
        return base
    source_document_sha = raw_binding.raw_registry_document_sha256_v1(source_document)
    candidate_document_sha = raw_binding.raw_registry_document_sha256_v1(
        candidate_document
    )
    if (
        source_document_sha
        != receipt_copy.get("source_raw_registry_document_sha256")
        or candidate_document_sha
        != receipt_copy.get("candidate_raw_registry_document_sha256")
    ):
        reasons.append("RAW_REHEARSAL_DOCUMENT_SHA256_BINDING_MISMATCH")

    rollback_document = _rollback_candidate_document(
        candidate_document, entries, reasons
    )
    rollback_sha = raw_binding.raw_registry_document_sha256_v1(rollback_document)
    rollback_verified = bool(
        rollback_document == source_document and rollback_sha == source_document_sha
    )
    if not rollback_verified:
        reasons.append("RAW_REHEARSAL_ROLLBACK_NOT_IDENTICAL_TO_PREIMAGE")
    reasons[:] = sorted(set(str(item) for item in reasons))
    if reasons:
        return base

    request_binding = {
        "operation": _OPERATION,
        "upstream_plan_sha256": receipt_copy["upstream_plan_sha256"],
        "binding_plan_sha256": receipt_copy["binding_plan_sha256"],
        "raw_path_receipt_sha256": receipt_copy["raw_path_receipt_sha256"],
        "composition_preview_receipt_sha256": receipt_sha,
        "source_raw_registry_document_sha256": source_document_sha,
        "candidate_raw_registry_document_sha256": candidate_document_sha,
        "candidate_snapshot_sha256": candidate_sha,
    }
    request_digest = _stable_sha256(request_binding)
    idempotency_key = _stable_sha256(
        {"operation": _OPERATION, "request_digest": request_digest}
    )
    record_bindings = [
        {
            "proposal_ordinal": entry["proposal_ordinal"],
            "proposal_type": entry["proposal_type"],
            "registry_index": entry["registry_index"],
            "registry_collection_key": entry["registry_collection_key"],
            "collection_shape": entry["collection_shape"],
            "record_fingerprint_before": entry["record_fingerprint_before"],
            "raw_record_sha256_before": entry["raw_record_sha256_before"],
            "raw_record_sha256_after": entry[
                "raw_record_sha256_after_proposed"
            ],
            "changed_paths": list(entry["changed_paths"]),
        }
        for entry in entries
    ]
    transaction = {
        "operation": _OPERATION,
        "state": "REHEARSED_NOT_APPLIED",
        "request_digest": request_digest,
        "idempotency_key": idempotency_key,
        "upstream_plan_sha256": receipt_copy["upstream_plan_sha256"],
        "binding_plan_sha256": receipt_copy["binding_plan_sha256"],
        "raw_path_receipt_sha256": receipt_copy["raw_path_receipt_sha256"],
        "composition_preview_receipt_sha256": receipt_sha,
        "source_snapshot_envelope_sha256": snapshot_copy[
            "snapshot_envelope_sha256"
        ],
        "source_raw_registry_document_sha256": source_document_sha,
        "candidate_raw_registry_document_sha256": candidate_document_sha,
        "candidate_snapshot_sha256": candidate_sha,
        "proposal_count": receipt_copy["proposal_count"],
        "changed_path_count": receipt_copy["changed_path_count"],
        "record_bindings": record_bindings,
        "candidate_snapshot": candidate_copy,
        "backup_envelope": {
            "snapshot_envelope_sha256": snapshot_copy[
                "snapshot_envelope_sha256"
            ],
            "raw_registry_document_sha256": source_document_sha,
            "snapshot": snapshot_copy,
            "immutable_preimage": True,
        },
        "rollback_envelope": {
            "from_raw_registry_document_sha256": candidate_document_sha,
            "to_raw_registry_document_sha256": source_document_sha,
            "rollback_raw_registry_document_sha256": rollback_sha,
            "rollback_document": rollback_document,
            "rollback_verified": rollback_verified,
            "inverse_entry_count": len(entries),
            "inverse_path_count": sum(len(entry["changed_paths"]) for entry in entries),
        },
        "compare_and_swap": {
            "required": True,
            "source_snapshot_envelope_sha256": snapshot_copy[
                "snapshot_envelope_sha256"
            ],
            "source_raw_registry_document_sha256": source_document_sha,
            "fail_closed_on_mismatch": True,
        },
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "translation_allowed": False,
        "apply_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "persistence_allowed": False,
        "broker_called": False,
        "no_order_sent": True,
    }
    transaction["transaction_sha256"] = raw_repair_rehearsal_transaction_sha256_v2(
        transaction
    )
    base.update(
        {
            "ok": True,
            "rehearsal_allowed": True,
            "transaction_verified": True,
            "translation_allowed": False,
            "apply_allowed": False,
            "status": "RAW_CLOSED_IDENTITY_CONFLICT_TRANSACTION_REHEARSED_V2_NOT_APPLIED",
            "reasons": [],
            "transaction": transaction,
        }
    )
    return base


def classify_raw_registry_document_against_rehearsal_offline_v2(
    raw_registry_document: Mapping[str, Any],
    transaction: Mapping[str, Any],
) -> dict[str, Any]:
    """Classify an injected document as original, candidate or divergent."""

    result = {
        "ok": False,
        "state": "BLOCKED",
        "apply_allowed": False,
        "translation_allowed": False,
        "offline_only": True,
        "synthetic_only": True,
        "write_executed": False,
        "reasons": [],
        "state_counts": {"before": 0, "after": 0, "unknown": 0},
    }
    reasons: list[str] = result["reasons"]
    if not isinstance(raw_registry_document, Mapping) or not isinstance(
        transaction, Mapping
    ):
        reasons.append("RAW_REHEARSAL_CLASSIFIER_MAPPING_INPUTS_REQUIRED")
        return result
    try:
        document = _ordered_json_copy(raw_registry_document)
        transaction_copy = _ordered_json_copy(transaction)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_REHEARSAL_CLASSIFIER_INPUT_NOT_CANONICALIZABLE")
        return result
    supplied_transaction_sha = _valid_sha256(
        transaction_copy.get("transaction_sha256")
    )
    if not supplied_transaction_sha or not hmac.compare_digest(
        supplied_transaction_sha,
        raw_repair_rehearsal_transaction_sha256_v2(transaction_copy),
    ):
        reasons.append("RAW_REHEARSAL_TRANSACTION_SHA256_MISMATCH")
        return result
    if (
        transaction_copy.get("state") != "REHEARSED_NOT_APPLIED"
        or transaction_copy.get("translation_allowed") is not False
        or transaction_copy.get("apply_allowed") is not False
        or transaction_copy.get("write_executed") is not False
    ):
        reasons.append("RAW_REHEARSAL_TRANSACTION_SAFETY_ENVELOPE_INVALID")
        return result
    document_sha = raw_binding.raw_registry_document_sha256_v1(document)
    source_sha = str(
        transaction_copy.get("source_raw_registry_document_sha256") or ""
    )
    candidate_sha = str(
        transaction_copy.get("candidate_raw_registry_document_sha256") or ""
    )
    if document_sha == source_sha:
        result.update({"ok": True, "state": "ORIGINAL", "reasons": []})
        return result
    if document_sha == candidate_sha:
        result.update(
            {"ok": True, "state": "CANDIDATE_ALREADY_PRESENT", "reasons": []}
        )
        return result

    counts = result["state_counts"]
    bindings = transaction_copy.get("record_bindings")
    if not isinstance(bindings, list) or not bindings:
        reasons.append("RAW_REHEARSAL_RECORD_BINDINGS_REQUIRED")
        return result
    for binding in bindings:
        if not isinstance(binding, Mapping):
            counts["unknown"] += 1
            continue
        record = _mutable_record_at_locator(document, binding)
        if record is None:
            counts["unknown"] += 1
            continue
        digest = _stable_sha256(record)
        if digest == binding.get("raw_record_sha256_before"):
            counts["before"] += 1
        elif digest == binding.get("raw_record_sha256_after"):
            counts["after"] += 1
        else:
            counts["unknown"] += 1
    reasons.append("PARTIAL_OR_DIVERGENT_RAW_REHEARSAL_STATE_DETECTED")
    result["state"] = "PARTIAL_OR_DIVERGENT"
    return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_REHEARSAL_OFFLINE_V2_VERSION",
    "classify_raw_registry_document_against_rehearsal_offline_v2",
    "raw_repair_rehearsal_transaction_sha256_v2",
    "rehearse_closed_identity_conflict_raw_transaction_offline_v2",
]
