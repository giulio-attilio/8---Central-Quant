"""Fail-closed offline source-anchor contract for the 19 Registry writers.

Only sanitized AST and line-marker evidence is accepted.  Source modules are
never imported or executed, and this module exposes no patch/apply surface.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1 as placement


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-WRITER-SOURCE-ANCHOR-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_SPEC_V1"
_EVIDENCE_VERSION = "READ_ONLY_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_EVIDENCE_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_FILES = ("trade_registry.py", "main.py")
_FUNCTION_SPANS = {
    "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE": (263, 287),
    "TRADE_REGISTRY_REGISTER_OPEN_TRADE": (366, 440),
    "TRADE_REGISTRY_UPDATE_OPEN_TRADE": (443, 466),
    "TRADE_REGISTRY_UPDATE_CLOSED_TRADE": (603, 745),
    "TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL": (2714, 2814),
    "TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME": (2853, 3017),
    "TRADE_REGISTRY_CLOSE_TRADE": (3098, 3252),
    "TRADE_REGISTRY_RESET": (3302, 3309),
    "MAIN_SYNC_MANUAL_REGISTER_OPEN": (4488, 4535),
    "MAIN_LIFECYCLE_UPDATE_OPEN_SNAPSHOT": (7249, 7294),
    "MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT": (9859, 10007),
    "MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE": (10186, 10367),
    "MAIN_TRADE_CLOSE_OUTCOME_COMMIT": (11052, 11167),
    "MAIN_REGISTRY_MODE_SEGREGATION_COMMIT": (11606, 11705),
    "MAIN_MARK_REGISTRY_MISSING_TRADES": (14681, 14729),
    "MAIN_PREDATOR_PAPER_REGISTRY_SYNC": (49325, 49584),
    "MAIN_PREDATOR_ORPHAN_OPEN_FIX": (49761, 49960),
    "MAIN_PREDATOR_AUTO_CLOSED_SYNC": (67476, 67683),
    "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP": (50531, 50896),
}
_FRESH_MARKERS = {
    "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE": "REGISTRY_STORAGE_STATE_GUARD",
    "TRADE_REGISTRY_REGISTER_OPEN_TRADE": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_UPDATE_OPEN_TRADE": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_UPDATE_CLOSED_TRADE": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_CLOSE_TRADE": "REGISTRY_READ_CALL",
    "TRADE_REGISTRY_RESET": None,
    "MAIN_SYNC_MANUAL_REGISTER_OPEN": "REGISTRY_READ_CALL",
    "MAIN_LIFECYCLE_UPDATE_OPEN_SNAPSHOT": "REGISTRY_READ_CALL",
    "MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT": "REGISTRY_SNAPSHOT_READ_CALL",
    "MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE": "TRY_INSERTION_SEAM",
    "MAIN_TRADE_CLOSE_OUTCOME_COMMIT": "REGISTRY_READ_CALL",
    "MAIN_REGISTRY_MODE_SEGREGATION_COMMIT": "LOOP_INSERTION_SEAM",
    "MAIN_MARK_REGISTRY_MISSING_TRADES": "REGISTRY_READ_CALL",
    "MAIN_PREDATOR_PAPER_REGISTRY_SYNC": "TRY_INSERTION_SEAM",
    "MAIN_PREDATOR_ORPHAN_OPEN_FIX": "TRY_INSERTION_SEAM",
    "MAIN_PREDATOR_AUTO_CLOSED_SYNC": "REGISTRY_READ_CALL",
    "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP": "RAW_REGISTRY_READ_CALL",
}
_WRITE_MARKERS = {
    **{writer_id: ["REGISTRY_SAVE_CALL"] for writer_id in _FUNCTION_SPANS if writer_id != "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"},
    "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE": [
        "REGISTRY_SAVE_CALL",
        "REGISTRY_SAVE_CALL",
    ],
    "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP": [
        "ATOMIC_JSON_WRITE_CALL",
        "ATOMIC_JSON_WRITE_CALL",
        "ATOMIC_JSON_WRITE_CALL",
        "EVENT_APPEND_WRITE_CALL",
    ],
}
_LOCAL_LOCK_MARKERS = {
    "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_REGISTER_OPEN_TRADE": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_UPDATE_OPEN_TRADE": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_UPDATE_CLOSED_TRADE": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME": "WITH_MODULE_RLOCK",
    "TRADE_REGISTRY_CLOSE_TRADE": "WITH_MODULE_RLOCK",
    "MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT": "WITH_LOCAL_LOCK",
    "MAIN_PREDATOR_AUTO_CLOSED_SYNC": "LOCAL_LOCK_ACQUIRE",
    "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP": "WITH_LOCAL_LOCK",
}
_NEGATIVE_CONTROLS = {
    "function_line_shift_denied": True,
    "writer_missing_denied": True,
    "write_marker_drift_denied": True,
    "lock_marker_drift_denied": True,
    "fresh_read_anchor_drift_denied": True,
    "source_hash_mismatch_denied": True,
    "runtime_import_request_denied": True,
}
_PRODUCTION_BLOCKERS = (
    "SOURCE_ANCHOR_VALIDATION_IS_OFFLINE_ONLY",
    "RUNTIME_SOURCE_WAS_NOT_CHANGED",
    "PATCH_CONTENT_IS_ABSENT",
    "PATCH_APPLY_ENTRYPOINT_IS_ABSENT",
    "SHARED_COORDINATOR_WAS_NOT_INSTALLED",
    "PRODUCTION_AND_LIVE_REMAIN_UNAUTHORIZED",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def canonical_runtime_writer_source_anchor_expectations_v1() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in placement.canonical_runtime_writer_transaction_placements_v1():
        start, end = _FUNCTION_SPANS[item["writer_id"]]
        result.append(
            {
                "writer_id": item["writer_id"],
                "component": item["component"],
                "function": item["function"],
                "function_start_line": start,
                "function_end_line": end,
                "acquire_before_line": item["acquire_before_line"],
                "release_after_line": item["release_after_line"],
                "fresh_read_after_acquire_line": item["fresh_read_after_acquire_line"],
                "authoritative_write_lines": list(item["authoritative_write_lines"]),
                "process_local_lock_line": item["process_local_lock_line"],
                "commit_guard_line": item["commit_guard_line"],
                "expected_fresh_marker": _FRESH_MARKERS[item["writer_id"]],
                "expected_write_markers": list(_WRITE_MARKERS[item["writer_id"]]),
                "expected_local_lock_marker": _LOCAL_LOCK_MARKERS.get(item["writer_id"]),
                "expected_commit_guard_marker": "IF_GUARD" if item["commit_guard_line"] is not None else None,
            }
        )
    return result


def runtime_writer_source_anchor_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def runtime_writer_source_anchor_evidence_sha256_v1(evidence: Mapping[str, Any]) -> str:
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    return _stable_sha256({key: value for key, value in evidence.items() if key != "evidence_sha256"})


def runtime_writer_source_anchor_rehearsal_sha256_v1(rehearsal: Mapping[str, Any]) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256({key: value for key, value in rehearsal.items() if key != "rehearsal_sha256"})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "source_anchor_contract_verified": False,
        "source_anchors_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "read_only": True,
        "source_content_exposed": False,
        "source_file_written": False,
        "runtime_imported": False,
        "runtime_executed": False,
        "registry_read": False,
        "registry_write": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "source_anchor_receipt": None,
    }


def _check_upstream(result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]) -> tuple[str, str]:
    receipt = result.get("transaction_placement_receipt")
    supplied = _valid_sha256(receipt.get("transaction_placement_receipt_sha256")) if isinstance(receipt, Mapping) else ""
    expected = _stable_sha256({key: value for key, value in receipt.items() if key != "transaction_placement_receipt_sha256"}) if isinstance(receipt, Mapping) else ""
    source_sha = _valid_sha256(receipt.get("source_preconditions_sha256")) if isinstance(receipt, Mapping) else ""
    checks["upstream_placement_valid"] = bool(
        result.get("ok") is True
        and result.get("transaction_placement_contract_verified") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and source_sha
        and hmac.compare_digest(supplied, expected)
        and receipt.get("writer_count") == 19
        and receipt.get("registry_write") is False
    )
    if not checks["upstream_placement_valid"]:
        reasons.append("SOURCE_ANCHOR_UPSTREAM_PLACEMENT_INVALID")
    return supplied, source_sha


def _check_spec(spec: Mapping[str, Any], upstream_sha: str, reasons: list[str], checks: dict[str, bool]) -> str:
    supplied = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(supplied and hmac.compare_digest(supplied, runtime_writer_source_anchor_spec_sha256_v1(spec)))
    checks["expectations_exact"] = spec.get("anchor_expectations") == canonical_runtime_writer_source_anchor_expectations_v1()
    checks["spec_chain_and_safety_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_transaction_placement_receipt_sha256") == upstream_sha
        and spec.get("source_files") == list(_SOURCE_FILES)
        and spec.get("writer_count") == 19
        and spec.get("parse_only") is True
        and spec.get("runtime_import_allowed") is False
        and spec.get("patch_content_present") is False
        and spec.get("apply_entrypoint_present") is False
        and spec.get("source_file_write_allowed") is False
        and spec.get("live_allowed") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "SOURCE_ANCHOR_SPEC_SHA256_INVALID"),
        ("expectations_exact", "SOURCE_ANCHOR_EXPECTATIONS_INVALID"),
        ("spec_chain_and_safety_valid", "SOURCE_ANCHOR_SPEC_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied


def _check_evidence(evidence: Mapping[str, Any], source_sha: str, reasons: list[str], checks: dict[str, bool]) -> str:
    supplied = _valid_sha256(evidence.get("evidence_sha256"))
    checks["evidence_sha256_valid"] = bool(supplied and hmac.compare_digest(supplied, runtime_writer_source_anchor_evidence_sha256_v1(evidence)))
    source_preconditions = evidence.get("source_precondition_evidence")
    nested_sha = _valid_sha256(source_preconditions.get("source_set_sha256")) if isinstance(source_preconditions, Mapping) else ""
    checks["source_hash_chain_valid"] = bool(
        isinstance(source_preconditions, Mapping)
        and nested_sha
        and nested_sha == source_sha
        and hmac.compare_digest(nested_sha, patch_plan.runtime_patch_source_preconditions_sha256_v1(source_preconditions))
        and [item.get("relative_path") for item in source_preconditions.get("files", ())] == patch_plan.canonical_runtime_patch_source_files_v1()
        and source_preconditions.get("read_only_collection") is True
        and source_preconditions.get("secret_files_excluded") is True
    )
    anchors = evidence.get("observed_anchors")
    expected = canonical_runtime_writer_source_anchor_expectations_v1()
    checks["all_source_anchors_valid"] = bool(
        isinstance(anchors, list)
        and len(anchors) == 19
        and [item.get("writer_id") for item in anchors if isinstance(item, Mapping)] == [item["writer_id"] for item in expected]
        and all(
            isinstance(observed, Mapping)
            and observed.get("writer_id") == wanted["writer_id"]
            and observed.get("component") == wanted["component"]
            and observed.get("function") == wanted["function"]
            and observed.get("function_start_line") == wanted["function_start_line"]
            and observed.get("function_end_line") == wanted["function_end_line"]
            and observed.get("all_placement_lines_within_function") is True
            and observed.get("fresh_marker") == wanted["expected_fresh_marker"]
            and observed.get("write_markers") == wanted["expected_write_markers"]
            and observed.get("local_lock_marker") == wanted["expected_local_lock_marker"]
            and observed.get("commit_guard_marker") == wanted["expected_commit_guard_marker"]
            and observed.get("source_content_exposed") is False
            for observed, wanted in zip(anchors, expected)
        )
    )
    checks["evidence_safety_valid"] = bool(
        evidence.get("evidence_version") == _EVIDENCE_VERSION
        and evidence.get("ast_parse_only") is True
        and evidence.get("runtime_imported") is False
        and evidence.get("runtime_executed") is False
        and evidence.get("source_content_exposed") is False
        and evidence.get("source_file_written") is False
        and evidence.get("registry_read") is False
        and evidence.get("registry_write") is False
    )
    for check, reason in (
        ("evidence_sha256_valid", "SOURCE_ANCHOR_EVIDENCE_SHA256_INVALID"),
        ("source_hash_chain_valid", "SOURCE_ANCHOR_SOURCE_HASH_CHAIN_INVALID"),
        ("all_source_anchors_valid", "SOURCE_ANCHOR_OBSERVATIONS_INVALID"),
        ("evidence_safety_valid", "SOURCE_ANCHOR_EVIDENCE_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied


def _check_rehearsal(rehearsal: Mapping[str, Any], spec_sha: str, evidence_sha: str, reasons: list[str], checks: dict[str, bool]) -> str:
    supplied = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(supplied and hmac.compare_digest(supplied, runtime_writer_source_anchor_rehearsal_sha256_v1(rehearsal)))
    checks["rehearsal_protocol_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("spec_sha256") == spec_sha
        and rehearsal.get("evidence_sha256") == evidence_sha
        and rehearsal.get("writer_count") == 19
        and rehearsal.get("validated_source_files") == list(_SOURCE_FILES)
        and rehearsal.get("negative_controls") == _NEGATIVE_CONTROLS
        and rehearsal.get("source_bytes_preserved") is True
        and rehearsal.get("runtime_executed") is False
        and rehearsal.get("live_allowed") is False
    )
    if not checks["rehearsal_sha256_valid"]:
        reasons.append("SOURCE_ANCHOR_REHEARSAL_SHA256_INVALID")
    if not checks["rehearsal_protocol_valid"]:
        reasons.append("SOURCE_ANCHOR_REHEARSAL_PROTOCOL_INVALID")
    return supplied


def evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(
    transaction_placement_result: Mapping[str, Any],
    source_anchor_spec: Mapping[str, Any],
    source_anchor_evidence: Mapping[str, Any],
    source_anchor_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    values = (transaction_placement_result, source_anchor_spec, source_anchor_evidence, source_anchor_rehearsal)
    if not all(isinstance(value, Mapping) for value in values):
        reasons.append("SOURCE_ANCHOR_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream, spec, evidence, rehearsal = (_canonical_copy(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        reasons.append("SOURCE_ANCHOR_INPUT_NOT_CANONICALIZABLE")
        return base
    upstream_sha, source_sha = _check_upstream(upstream, reasons, checks)
    spec_sha = _check_spec(spec, upstream_sha, reasons, checks)
    evidence_sha = _check_evidence(evidence, source_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(rehearsal, spec_sha, evidence_sha, reasons, checks)
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_SOURCE_ANCHOR_CHECKS_FAILED")
        return base
    receipt = {
        "upstream_transaction_placement_receipt_sha256": upstream_sha,
        "source_preconditions_sha256": source_sha,
        "source_anchor_spec_sha256": spec_sha,
        "source_anchor_evidence_sha256": evidence_sha,
        "source_anchor_rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "source_file_count": 2,
        "source_content_exposed": False,
        "source_file_written": False,
        "runtime_imported": False,
        "runtime_executed": False,
        "registry_read": False,
        "registry_write": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["source_anchor_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "source_anchor_contract_verified": True,
            "source_anchors_verified": True,
            "synthetic_rehearsal_valid": True,
            "status": "CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_V1_VALID_OFFLINE_DORMANT",
            "reasons": [],
            "checks": checks,
            "source_anchor_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_CONTRACT_V1_VERSION",
    "canonical_runtime_writer_source_anchor_expectations_v1",
    "evaluate_closed_repair_runtime_writer_source_anchors_offline_v1",
    "runtime_writer_source_anchor_evidence_sha256_v1",
    "runtime_writer_source_anchor_rehearsal_sha256_v1",
    "runtime_writer_source_anchor_spec_sha256_v1",
]
