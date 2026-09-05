"""Dormant V2 composition of planner, raw-path proof and raw preview.

Only injected synthetic mappings are accepted.  The source planner plan is
never changed: a separately hashed binding envelope is derived in memory for
the V1 raw-path verifier.  The resulting candidate is a preview only, includes
an exact round-trip proof, and can never authorize translation, persistence,
runtime integration, apply or trading.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_path_binding_contract_v1 as raw_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_CONTRACT_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-COMPOSITION-CONTRACT-V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLAN_PRECONDITIONS = frozenset(
    {
        "PLAN_IS_NOT_AN_APPLY_COMMAND",
        "PRESERVE_COMPLETE_PRE_REPAIR_BACKUP",
        "RELOAD_REGISTRY_BEFORE_ANY_FUTURE_WRITE",
        "REQUIRE_IDENTICAL_INPUT_MANIFEST_SHA256",
        "REQUIRE_EVERY_RECORD_FINGERPRINT_UNCHANGED",
        "REQUIRE_SEPARATE_PRODUCTION_REVIEW_AND_AUTHORIZATION",
    }
)
_TEXT_LEGACY_FIELDS = frozenset(
    {
        "trade_id",
        "registry_mode",
        "execution_mode",
        "opened_at",
        "closed_at",
        "bot",
        "setup",
        "symbol",
        "side",
        "status",
    }
)
_NUMERIC_LEGACY_FIELDS = frozenset({"entry", "qty"})
_PREVIEW_BLOCKERS = (
    "RAW_PREVIEW_IS_NOT_A_TRANSLATION_COMMAND",
    "RAW_PREVIEW_IS_NOT_AN_APPLY_COMMAND",
    "NO_RUNTIME_OR_STORAGE_ADAPTER_EXISTS",
    "SEPARATE_TRANSACTION_V2_REHEARSAL_REQUIRED",
    "SEPARATE_READINESS_V2_GATE_REQUIRED",
    "SEPARATE_PRODUCTION_REVIEW_AND_AUTHORIZATION_REQUIRED",
)


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


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


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


def planner_plan_sha256_v2(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping):
        raise TypeError("plan must be a mapping")
    return _stable_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )


def derive_raw_binding_plan_envelope_v2(
    planner_plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Create a separate raw-binding envelope without mutating the plan."""

    if not isinstance(planner_plan, Mapping):
        raise TypeError("planner_plan must be a mapping")
    source = _ordered_json_copy(planner_plan)
    source_sha = _valid_sha256(source.get("plan_sha256"))
    if not source_sha or not hmac.compare_digest(
        source_sha, planner_plan_sha256_v2(source)
    ):
        raise ValueError("planner plan digest mismatch")
    derived = _ordered_json_copy(source)
    derived["upstream_plan_sha256"] = source_sha
    derived["offline_only"] = True
    derived["synthetic_only"] = True
    derived["plan_sha256"] = raw_binding.repair_plan_sha256_v1(derived)
    return derived


def raw_composition_preview_receipt_sha256_v2(
    receipt: Mapping[str, Any],
) -> str:
    if not isinstance(receipt, Mapping):
        raise TypeError("receipt must be a mapping")
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    )


def raw_composition_candidate_snapshot_sha256_v2(
    snapshot: Mapping[str, Any],
) -> str:
    if not isinstance(snapshot, Mapping):
        raise TypeError("snapshot must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in snapshot.items()
            if key != "candidate_snapshot_sha256"
        }
    )


def _validate_source_plan(
    plan: Mapping[str, Any],
    reasons: list[str],
    *,
    expected_legacy_count: int,
    expected_financial_count: int,
    max_proposals: int,
) -> list[Mapping[str, Any]]:
    supplied_sha = _valid_sha256(plan.get("plan_sha256"))
    if not supplied_sha or not hmac.compare_digest(
        supplied_sha, planner_plan_sha256_v2(plan)
    ):
        reasons.append("UPSTREAM_PLAN_SHA256_MISMATCH")
    proposals_value = plan.get("proposals")
    if not isinstance(proposals_value, list) or any(
        not isinstance(item, Mapping) for item in proposals_value
    ):
        reasons.append("UPSTREAM_PLAN_PROPOSALS_INVALID")
        return []
    proposals = list(proposals_value)
    expected_total = expected_legacy_count + expected_financial_count
    if (
        len(proposals) != expected_total
        or len(proposals) > max_proposals
        or plan.get("proposal_count") != expected_total
        or plan.get("legacy_proposal_count") != expected_legacy_count
        or plan.get("financial_proposal_count") != expected_financial_count
    ):
        reasons.append("UPSTREAM_PLAN_COUNTS_OR_BUDGET_INVALID")
    preconditions = plan.get("preconditions")
    if not isinstance(preconditions, list) or not _PLAN_PRECONDITIONS.issubset(
        {str(item) for item in preconditions}
    ):
        reasons.append("UPSTREAM_PLAN_PRECONDITIONS_INCOMPLETE")
    preservation = plan.get("preservation")
    if not isinstance(preservation, Mapping):
        reasons.append("UPSTREAM_PLAN_PRESERVATION_REQUIRED")
        preservation = {}
    fingerprints = sorted(
        str(item.get("record_fingerprint") or "") for item in proposals
    )
    legacy_conflicts = sorted(
        str(item.get("conflict_sha256") or "")
        for item in proposals
        if item.get("proposal_type") == "LEGACY_ALIAS_CANONICALIZATION"
    )
    financial_conflicts = sorted(
        str(item.get("conflict_sha256") or "")
        for item in proposals
        if item.get("proposal_type") == "FINANCIAL_OUTCOME_CANONICALIZATION"
    )
    manifest = {
        "legacy_conflict_sha256": legacy_conflicts,
        "financial_conflict_sha256": financial_conflicts,
        "record_fingerprints": fingerprints,
    }
    if (
        preservation.get("input_record_count") != expected_total
        or preservation.get("preserved_record_count") != expected_total
        or preservation.get("removed_record_count") != 0
        or preservation.get("mutated_record_count") != 0
        or sorted(preservation.get("record_fingerprints") or []) != fingerprints
        or preservation.get("input_manifest_sha256") != _stable_sha256(manifest)
    ):
        reasons.append("UPSTREAM_PLAN_PRESERVATION_INVALID")
    if len(fingerprints) != len(set(fingerprints)) or any(
        not _valid_sha256(value) for value in fingerprints
    ):
        reasons.append("UPSTREAM_PLAN_FINGERPRINTS_INVALID_OR_DUPLICATE")
    return proposals


def _translation_request_sha256(request: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {
            key: value
            for key, value in request.items()
            if key != "translation_request_sha256"
        }
    )


def _record_at_locator(
    document: Mapping[str, Any], binding: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    closed = document.get("closed_trades")
    index = binding.get("registry_index")
    key = binding.get("registry_collection_key")
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return None
    if binding.get("collection_shape") == "list" and isinstance(closed, list):
        if key is not None or index >= len(closed):
            return None
        record = closed[index]
    elif binding.get("collection_shape") == "dict" and isinstance(closed, Mapping):
        keys = list(closed)
        if (
            not isinstance(key, str)
            or index >= len(keys)
            or keys[index] != key
        ):
            return None
        record = closed.get(key)
    else:
        return None
    return record if isinstance(record, Mapping) else None


def _mutable_record_at_locator(
    document: dict[str, Any], binding: Mapping[str, Any]
) -> dict[str, Any] | None:
    closed = document.get("closed_trades")
    index = binding.get("registry_index")
    key = binding.get("registry_collection_key")
    if binding.get("collection_shape") == "list" and isinstance(closed, list):
        record = closed[index] if isinstance(index, int) and index < len(closed) else None
    elif binding.get("collection_shape") == "dict" and isinstance(closed, dict):
        record = closed.get(key)
    else:
        record = None
    return record if isinstance(record, dict) else None


def _read_path(record: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    parts = path.split(".")
    if len(parts) < 2 or parts[0] != "trade" or any(not part for part in parts):
        return False, None
    current: Any = record
    for part in parts[1:]:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _write_path(record: dict[str, Any], path: str, value: Any) -> bool:
    parts = path.split(".")
    if len(parts) < 2 or parts[0] != "trade":
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


def _typed_target(
    canonical_field: str,
    raw_type: str,
    normalized_target: str,
    reasons: list[str],
) -> Any:
    if canonical_field in _TEXT_LEGACY_FIELDS or canonical_field == "close_reason":
        if raw_type != "string":
            reasons.append("TEXT_TARGET_REQUIRES_STRING_SOURCE")
            return None
        return normalized_target
    if canonical_field in _NUMERIC_LEGACY_FIELDS or canonical_field == "pnl_r":
        try:
            number = Decimal(normalized_target)
        except (InvalidOperation, ValueError):
            reasons.append("NUMERIC_TARGET_INVALID")
            return None
        if not number.is_finite():
            reasons.append("NUMERIC_TARGET_INVALID")
            return None
        if raw_type == "string":
            return normalized_target
        if raw_type == "integer":
            if number != number.to_integral_value():
                reasons.append("LOSSY_INTEGER_TARGET_BLOCKED")
                return None
            return int(number)
        if raw_type == "number":
            return float(number)
        reasons.append("NUMERIC_TARGET_SOURCE_TYPE_UNSUPPORTED")
        return None
    reasons.append("TARGET_FIELD_UNSUPPORTED")
    return None


def _proposal_target(proposal: Mapping[str, Any], field: str) -> str:
    if proposal.get("proposal_type") == "LEGACY_ALIAS_CANONICALIZATION":
        return str(proposal.get("selected_normalized_value") or "")
    updates = proposal.get("canonical_updates")
    if not isinstance(updates, Mapping):
        return ""
    if field == "close_reason":
        return str(updates.get(field) or "").strip().upper()
    if field == "pnl_r":
        try:
            number = Decimal(str(updates.get(field)))
            if not number.is_finite():
                return ""
            if number == 0:
                return "0"
            return format(number.normalize(), "f")
        except (InvalidOperation, ValueError, TypeError):
            return ""
    return ""


def _leaf_diff_paths(before: Any, after: Any, prefix: str = "trade") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        if set(before) != set(after):
            return {prefix}
        paths: set[str] = set()
        for key in before:
            paths.update(_leaf_diff_paths(before[key], after[key], f"{prefix}.{key}"))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        return set() if _canonical_json(before) == _canonical_json(after) else {prefix}
    return set() if _canonical_json(before) == _canonical_json(after) else {prefix}


def _replace_record(
    document: dict[str, Any], binding: Mapping[str, Any], record: dict[str, Any]
) -> bool:
    closed = document.get("closed_trades")
    index = binding.get("registry_index")
    key = binding.get("registry_collection_key")
    if binding.get("collection_shape") == "list" and isinstance(closed, list):
        if not isinstance(index, int) or index >= len(closed):
            return False
        closed[index] = record
        return True
    if binding.get("collection_shape") == "dict" and isinstance(closed, dict):
        if key not in closed:
            return False
        closed[key] = record
        return True
    return False


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "composition_verification_allowed": False,
        "raw_preview_allowed": False,
        "preview_materialized": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "status": "CLOSED_IDENTITY_CONFLICT_RAW_COMPOSITION_V2_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_CONTRACT_V2_VERSION,
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
        "binding_result": None,
        "candidate_snapshot": None,
        "preview_receipt": None,
    }


def compose_closed_identity_conflict_raw_preview_offline_v2(
    planner_plan: Mapping[str, Any],
    raw_registry_snapshot: Mapping[str, Any],
    raw_path_inventory: Mapping[str, Any],
    *,
    expected_legacy_count: int = 151,
    expected_financial_count: int = 1,
    max_proposals: int = 152,
) -> dict[str, Any]:
    """Compose a path-complete raw preview while denying translation/apply."""

    base = _base()
    reasons: list[str] = base["reasons"]
    if not all(
        isinstance(value, Mapping)
        for value in (planner_plan, raw_registry_snapshot, raw_path_inventory)
    ):
        reasons.append("RAW_COMPOSITION_MAPPING_INPUTS_REQUIRED")
        return base
    limits = (expected_legacy_count, expected_financial_count, max_proposals)
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in limits
    ) or max_proposals == 0:
        reasons.append("RAW_COMPOSITION_LIMITS_INVALID")
        return base
    try:
        source_plan = _ordered_json_copy(planner_plan)
        source_snapshot = _ordered_json_copy(raw_registry_snapshot)
        source_inventory = _ordered_json_copy(raw_path_inventory)
        proposals = _validate_source_plan(
            source_plan,
            reasons,
            expected_legacy_count=expected_legacy_count,
            expected_financial_count=expected_financial_count,
            max_proposals=max_proposals,
        )
        binding_plan = derive_raw_binding_plan_envelope_v2(source_plan)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_COMPOSITION_INPUT_OR_PLAN_INVALID")
        return base
    if reasons:
        reasons[:] = sorted(set(reasons))
        return base

    binding_result = raw_binding.bind_closed_identity_conflict_raw_paths_offline_v1(
        binding_plan,
        source_snapshot,
        source_inventory,
        max_bindings=max_proposals,
    )
    base["binding_result"] = binding_result
    if binding_result.get("ok") is not True:
        reasons.append("RAW_PATH_BINDING_VERIFICATION_FAILED")
        reasons.extend(binding_result.get("reasons") or [])
        reasons[:] = sorted(set(str(item) for item in reasons))
        return base
    request = binding_result.get("translation_request")
    if not isinstance(request, Mapping):
        reasons.append("RAW_PATH_TRANSLATION_REQUEST_REQUIRED")
        return base
    supplied_request_sha = _valid_sha256(request.get("translation_request_sha256"))
    if not supplied_request_sha or not hmac.compare_digest(
        supplied_request_sha, _translation_request_sha256(request)
    ):
        reasons.append("RAW_PATH_TRANSLATION_REQUEST_SHA256_MISMATCH")
    if (
        request.get("plan_sha256") != binding_plan.get("plan_sha256")
        or request.get("translation_allowed") is not False
        or request.get("apply_allowed") is not False
        or request.get("binding_count") != len(proposals)
    ):
        reasons.append("RAW_PATH_TRANSLATION_REQUEST_ENVELOPE_INVALID")
    bindings = request.get("bindings")
    if not isinstance(bindings, list) or len(bindings) != len(proposals):
        reasons.append("RAW_PATH_TRANSLATION_REQUEST_BINDINGS_INVALID")
        bindings = []
    document = source_snapshot.get("raw_registry_document")
    if not isinstance(document, Mapping):
        reasons.append("RAW_REGISTRY_DOCUMENT_REQUIRED")
        document = {}
    if reasons:
        reasons[:] = sorted(set(reasons))
        return base

    candidate_document = _ordered_json_copy(document)
    receipt_entries: list[dict[str, Any]] = []
    total_changed_paths = 0
    for ordinal, (proposal, item) in enumerate(zip(proposals, bindings, strict=True)):
        entry_reasons: list[str] = []
        before_record = _record_at_locator(document, item)
        candidate_record = _mutable_record_at_locator(candidate_document, item)
        if before_record is None or candidate_record is None:
            entry_reasons.append("RAW_COMPOSITION_RECORD_LOCATOR_INVALID")
        if item.get("proposal_ordinal") != ordinal:
            entry_reasons.append("RAW_COMPOSITION_PROPOSAL_ORDINAL_MISMATCH")
        if item.get("proposal_sha256") != _stable_sha256(proposal):
            entry_reasons.append("RAW_COMPOSITION_PROPOSAL_SHA256_MISMATCH")
        descriptors = item.get("path_bindings")
        if not isinstance(descriptors, list) or not descriptors:
            entry_reasons.append("RAW_COMPOSITION_PATH_BINDINGS_REQUIRED")
            descriptors = []
        before_values: dict[str, Any] = {}
        proposed_values: dict[str, Any] = {}
        changed_paths: list[str] = []
        if before_record is not None and candidate_record is not None:
            for descriptor in descriptors:
                if not isinstance(descriptor, Mapping):
                    entry_reasons.append("RAW_COMPOSITION_PATH_DESCRIPTOR_INVALID")
                    continue
                field = str(descriptor.get("canonical_field") or "")
                path = str(descriptor.get("path") or "")
                exists, observed = _read_path(before_record, path)
                if not exists or _stable_sha256(observed) != descriptor.get(
                    "raw_value_sha256"
                ):
                    entry_reasons.append("RAW_COMPOSITION_PATH_PREIMAGE_MISMATCH")
                    continue
                target_text = _proposal_target(proposal, field)
                if not target_text:
                    entry_reasons.append("RAW_COMPOSITION_TARGET_MISSING")
                    continue
                target = _typed_target(
                    field,
                    str(descriptor.get("raw_type") or ""),
                    target_text,
                    entry_reasons,
                )
                if entry_reasons:
                    continue
                before_values[path] = copy.deepcopy(observed)
                proposed_values[path] = copy.deepcopy(target)
                if _canonical_json(observed) != _canonical_json(target):
                    if not _write_path(candidate_record, path, target):
                        entry_reasons.append("RAW_COMPOSITION_PATH_WRITE_PREVIEW_FAILED")
                        continue
                    changed_paths.append(path)
            if not changed_paths:
                entry_reasons.append("RAW_COMPOSITION_PROPOSAL_HAS_NO_CHANGE")
            actual_diff = _leaf_diff_paths(before_record, candidate_record)
            if actual_diff != set(changed_paths):
                entry_reasons.append("RAW_COMPOSITION_DIFF_ESCAPED_BOUND_PATHS")
        if entry_reasons:
            reasons.extend(entry_reasons)
            continue
        before_record_sha = _stable_sha256(before_record)
        after_record_sha = _stable_sha256(candidate_record)
        receipt_entries.append(
            {
                "proposal_ordinal": ordinal,
                "proposal_type": proposal.get("proposal_type"),
                "registry_index": item.get("registry_index"),
                "registry_collection_key": item.get("registry_collection_key"),
                "collection_shape": item.get("collection_shape"),
                "record_fingerprint_before": item.get("record_fingerprint"),
                "raw_record_sha256_before": before_record_sha,
                "raw_record_sha256_after_proposed": after_record_sha,
                "conflict_sha256": item.get("conflict_sha256"),
                "evidence_sha256": item.get("evidence_sha256"),
                "changed_paths": sorted(changed_paths),
                "before_values": before_values,
                "proposed_values": proposed_values,
                "apply_allowed": False,
            }
        )
        total_changed_paths += len(changed_paths)

    if reasons or len(receipt_entries) != len(proposals):
        if len(receipt_entries) != len(proposals):
            reasons.append("RAW_COMPOSITION_ATOMIC_PREVIEW_INCOMPLETE")
        reasons[:] = sorted(set(str(item) for item in reasons))
        return base

    source_document_sha = raw_binding.raw_registry_document_sha256_v1(document)
    candidate_document_sha = raw_binding.raw_registry_document_sha256_v1(
        candidate_document
    )
    if source_document_sha == candidate_document_sha:
        reasons.append("RAW_COMPOSITION_CANDIDATE_UNCHANGED")
    source_top = {key: value for key, value in document.items() if key != "closed_trades"}
    candidate_top = {
        key: value for key, value in candidate_document.items() if key != "closed_trades"
    }
    if _canonical_json(source_top) != _canonical_json(candidate_top):
        reasons.append("RAW_COMPOSITION_TOP_LEVEL_OR_OPEN_TRADES_CHANGED")
    if raw_binding.raw_closed_collection_locator_sha256_v1(
        document
    ) != raw_binding.raw_closed_collection_locator_sha256_v1(candidate_document):
        reasons.append("RAW_COMPOSITION_COLLECTION_LOCATOR_CHANGED")
    target_locators = {
        (
            item.get("collection_shape"),
            item.get("registry_index"),
            item.get("registry_collection_key"),
        )
        for item in bindings
    }
    source_closed = document.get("closed_trades")
    candidate_closed = candidate_document.get("closed_trades")
    non_target_records_verified = True
    if isinstance(source_closed, list) and isinstance(candidate_closed, list):
        for index, (before, after) in enumerate(
            zip(source_closed, candidate_closed, strict=True)
        ):
            if ("list", index, None) not in target_locators and before != after:
                non_target_records_verified = False
    elif isinstance(source_closed, Mapping) and isinstance(candidate_closed, Mapping):
        for index, key in enumerate(source_closed):
            if (
                ("dict", index, key) not in target_locators
                and source_closed[key] != candidate_closed.get(key)
            ):
                non_target_records_verified = False
    else:
        non_target_records_verified = False
    if not non_target_records_verified:
        reasons.append("RAW_COMPOSITION_NON_TARGET_RECORD_CHANGED")

    round_trip_document = _ordered_json_copy(candidate_document)
    for entry, item in reversed(list(zip(receipt_entries, bindings, strict=True))):
        record = _mutable_record_at_locator(round_trip_document, item)
        if record is None:
            reasons.append("RAW_COMPOSITION_ROUND_TRIP_LOCATOR_INVALID")
            continue
        for path in entry["changed_paths"]:
            if path not in entry["before_values"] or not _write_path(
                record, path, entry["before_values"][path]
            ):
                reasons.append("RAW_COMPOSITION_ROUND_TRIP_RESTORE_FAILED")
    round_trip_sha = raw_binding.raw_registry_document_sha256_v1(round_trip_document)
    round_trip_verified = bool(
        round_trip_document == document and round_trip_sha == source_document_sha
    )
    if not round_trip_verified:
        reasons.append("RAW_COMPOSITION_ROUND_TRIP_MISMATCH")
    reasons[:] = sorted(set(reasons))
    if reasons:
        return base

    candidate_snapshot = {
        "snapshot_version": "SYNTHETIC_RAW_TRADE_REGISTRY_CANDIDATE_PREVIEW_V2",
        "synthetic_only": True,
        "offline_only": True,
        "source_raw_registry_document_sha256": source_document_sha,
        "candidate_raw_registry_document_sha256": candidate_document_sha,
        "closed_collection_locator_sha256": raw_binding.raw_closed_collection_locator_sha256_v1(
            candidate_document
        ),
        "raw_registry_document": candidate_document,
        "translation_allowed": False,
        "apply_allowed": False,
    }
    candidate_snapshot["candidate_snapshot_sha256"] = (
        raw_composition_candidate_snapshot_sha256_v2(candidate_snapshot)
    )
    receipt = {
        "receipt_version": "SYNTHETIC_RAW_COMPOSITION_PREVIEW_RECEIPT_V2",
        "upstream_plan_sha256": source_plan["plan_sha256"],
        "binding_plan_sha256": binding_plan["plan_sha256"],
        "raw_path_receipt_sha256": request["raw_path_receipt_sha256"],
        "raw_path_translation_request_sha256": supplied_request_sha,
        "source_raw_registry_document_sha256": source_document_sha,
        "candidate_raw_registry_document_sha256": candidate_document_sha,
        "round_trip_raw_registry_document_sha256": round_trip_sha,
        "round_trip_verified": round_trip_verified,
        "preservation_proof": {
            "top_level_and_open_trades_exact": True,
            "non_target_closed_records_exact": non_target_records_verified,
            "collection_shape_order_and_keys_exact": True,
            "target_diffs_confined_to_bound_paths": True,
        },
        "proposal_count": len(receipt_entries),
        "changed_path_count": total_changed_paths,
        "entries": receipt_entries,
        "all_or_nothing": True,
        "translation_allowed": False,
        "apply_allowed": False,
        "preview_blockers": list(_PREVIEW_BLOCKERS),
    }
    receipt["receipt_sha256"] = raw_composition_preview_receipt_sha256_v2(receipt)
    base.update(
        {
            "ok": True,
            "composition_verification_allowed": True,
            "raw_preview_allowed": True,
            "preview_materialized": True,
            "translation_allowed": False,
            "apply_allowed": False,
            "status": "CLOSED_IDENTITY_CONFLICT_RAW_COMPOSITION_V2_PREVIEW_READY_OFFLINE_TRANSLATION_BLOCKED",
            "reasons": [],
            "candidate_snapshot": candidate_snapshot,
            "preview_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_CONTRACT_V2_VERSION",
    "compose_closed_identity_conflict_raw_preview_offline_v2",
    "derive_raw_binding_plan_envelope_v2",
    "planner_plan_sha256_v2",
    "raw_composition_candidate_snapshot_sha256_v2",
    "raw_composition_preview_receipt_sha256_v2",
]
