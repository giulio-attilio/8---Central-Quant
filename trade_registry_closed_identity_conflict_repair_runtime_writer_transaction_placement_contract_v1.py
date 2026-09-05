"""Dormant placement contract for the 19 Trade Registry writer transactions.

The module describes where a future shared coordinator must begin and end.  It
does not import runtime modules, acquire locks, write files, or expose an apply
entrypoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections import Counter
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-WRITER-TRANSACTION-PLACEMENT-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLASS_COUNTS = {
    "TRADE_REGISTRY_FULL_RMW_REENTRANT": 7,
    "TRADE_REGISTRY_EXCLUSIVE_WRITE_REENTRANT": 1,
    "MAIN_FULL_RMW_FRESH_READ": 3,
    "MAIN_COMMIT_BRANCH_FRESH_RELOAD": 5,
    "MAIN_EXISTING_LOCK_COORDINATOR_UPGRADE": 3,
}
_NEGATIVE_CONTROLS = {
    "wrong_lock_order_denied": True,
    "missing_fresh_read_denied": True,
    "return_path_lease_leak_denied": True,
    "exception_path_lease_leak_denied": True,
    "partial_commit_downgrade_denied": True,
    "external_collection_under_lease_denied": True,
}
_PRODUCTION_BLOCKERS = (
    "TRANSACTION_PLACEMENT_IS_CONTRACT_ONLY",
    "RUNTIME_SOURCE_WAS_NOT_CHANGED",
    "SHARED_COORDINATOR_WAS_NOT_INSTALLED",
    "REAL_LOCK_WAS_NOT_ACQUIRED",
    "REAL_REGISTRY_WAS_NOT_READ_OR_WRITTEN",
    "PATCH_APPLY_ENTRYPOINT_IS_ABSENT",
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


def _placement(
    writer_id: str,
    component: str,
    function: str,
    classification: str,
    acquire_before_line: int,
    release_after_line: int,
    *,
    fresh_read_line: int | None,
    authoritative_write_lines: tuple[int, ...],
    local_lock_line: int | None = None,
    commit_guard_line: int | None = None,
    nested_reentry: bool = False,
    revalidation: bool = False,
    external_collection_outside: bool = False,
    sidecar_outside: bool = False,
    partial_commit_truth: bool = False,
) -> dict[str, Any]:
    return {
        "writer_id": writer_id,
        "component": component,
        "function": function,
        "classification": classification,
        "acquire_before_line": acquire_before_line,
        "release_after_line": release_after_line,
        "fresh_read_after_acquire_line": fresh_read_line,
        "authoritative_write_lines": list(authoritative_write_lines),
        "process_local_lock_line": local_lock_line,
        "commit_guard_line": commit_guard_line,
        "coordinator_before_process_local_lock": local_lock_line is not None,
        "same_owner_token_for_nested_reentry": nested_reentry,
        "fresh_state_revalidation_required": revalidation,
        "external_collection_outside_coordinator": external_collection_outside,
        "sidecar_io_outside_coordinator": sidecar_outside,
        "separate_registry_commit_truth_required": partial_commit_truth,
        "release_on_all_returns": True,
        "release_on_all_exceptions": True,
        "fail_closed_on_acquire_timeout": True,
        "declarative_only": True,
    }


def canonical_runtime_writer_transaction_placements_v1() -> list[dict[str, Any]]:
    """Exact audited section boundaries; line numbers bind the current sources."""

    return [
        _placement("TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE", "trade_registry.py", "load_registry", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 266, 287, fresh_read_line=267, authoritative_write_lines=(274, 280), local_lock_line=266, nested_reentry=True),
        _placement("TRADE_REGISTRY_REGISTER_OPEN_TRADE", "trade_registry.py", "register_open_trade", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 430, 438, fresh_read_line=431, authoritative_write_lines=(433,), local_lock_line=430, nested_reentry=True),
        _placement("TRADE_REGISTRY_UPDATE_OPEN_TRADE", "trade_registry.py", "update_trade", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 444, 464, fresh_read_line=445, authoritative_write_lines=(459,), local_lock_line=444, nested_reentry=True),
        _placement("TRADE_REGISTRY_UPDATE_CLOSED_TRADE", "trade_registry.py", "update_closed_trade", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 614, 737, fresh_read_line=615, authoritative_write_lines=(731,), local_lock_line=614, nested_reentry=True),
        _placement("TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL", "trade_registry.py", "backfill_historical_strong_identity", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 2731, 2814, fresh_read_line=2732, authoritative_write_lines=(2800,), local_lock_line=2731, nested_reentry=True),
        _placement("TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME", "trade_registry.py", "record_manual_close_outcome", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 2874, 3007, fresh_read_line=2875, authoritative_write_lines=(3001,), local_lock_line=2874, nested_reentry=True, sidecar_outside=True),
        _placement("TRADE_REGISTRY_CLOSE_TRADE", "trade_registry.py", "close_trade", "TRADE_REGISTRY_FULL_RMW_REENTRANT", 3115, 3250, fresh_read_line=3116, authoritative_write_lines=(3244,), local_lock_line=3115, nested_reentry=True, sidecar_outside=True),
        _placement("TRADE_REGISTRY_RESET", "trade_registry.py", "reset_trade_registry", "TRADE_REGISTRY_EXCLUSIVE_WRITE_REENTRANT", 3305, 3308, fresh_read_line=None, authoritative_write_lines=(3306,), commit_guard_line=3303, nested_reentry=True),
        _placement("MAIN_SYNC_MANUAL_REGISTER_OPEN", "main.py", "_trs_v1_manual_register_open_trade", "MAIN_FULL_RMW_FRESH_READ", 4489, 4535, fresh_read_line=4489, authoritative_write_lines=(4527,)),
        _placement("MAIN_LIFECYCLE_UPDATE_OPEN_SNAPSHOT", "main.py", "_rtlm_v1_update_open_trade_snapshot", "MAIN_COMMIT_BRANCH_FRESH_RELOAD", 7253, 7294, fresh_read_line=7253, authoritative_write_lines=(7289,), commit_guard_line=7251),
        _placement("MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT", "main.py", "registry_persistence_v1_restore_from_latest_snapshot", "MAIN_EXISTING_LOCK_COORDINATOR_UPGRADE", 9862, 10007, fresh_read_line=9914, authoritative_write_lines=(9990,), local_lock_line=9879, commit_guard_line=9862, nested_reentry=True, revalidation=True, sidecar_outside=True),
        _placement("MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE", "main.py", "registry_persistence_v12_recover_closed_trade_from_params", "MAIN_COMMIT_BRANCH_FRESH_RELOAD", 10316, 10330, fresh_read_line=10319, authoritative_write_lines=(10327,), commit_guard_line=10305, revalidation=True, external_collection_outside=True, sidecar_outside=True, partial_commit_truth=True),
        _placement("MAIN_TRADE_CLOSE_OUTCOME_COMMIT", "main.py", "trade_close_outcome_v1_commit", "MAIN_FULL_RMW_FRESH_READ", 11060, 11155, fresh_read_line=11060, authoritative_write_lines=(11153,), revalidation=True, sidecar_outside=True, partial_commit_truth=True),
        _placement("MAIN_REGISTRY_MODE_SEGREGATION_COMMIT", "main.py", "registry_mode_segregation_v1_analyze", "MAIN_COMMIT_BRANCH_FRESH_RELOAD", 11638, 11652, fresh_read_line=11639, authoritative_write_lines=(11651,), commit_guard_line=11638, revalidation=True, external_collection_outside=True, sidecar_outside=True),
        _placement("MAIN_MARK_REGISTRY_MISSING_TRADES", "main.py", "mark_registry_missing_trades", "MAIN_FULL_RMW_FRESH_READ", 14689, 14718, fresh_read_line=14689, authoritative_write_lines=(14718,)),
        _placement("MAIN_PREDATOR_PAPER_REGISTRY_SYNC", "main.py", "predator_paper_registry_sync_fix_v1_status", "MAIN_COMMIT_BRANCH_FRESH_RELOAD", 49451, 49464, fresh_read_line=49452, authoritative_write_lines=(49463,), commit_guard_line=49451, revalidation=True, external_collection_outside=True, sidecar_outside=True),
        _placement("MAIN_PREDATOR_ORPHAN_OPEN_FIX", "main.py", "predator_registry_orphan_open_fix_v1_status", "MAIN_COMMIT_BRANCH_FRESH_RELOAD", 49789, 49887, fresh_read_line=49790, authoritative_write_lines=(49886,), commit_guard_line=49789, revalidation=True, external_collection_outside=True, sidecar_outside=True),
        _placement("MAIN_PREDATOR_AUTO_CLOSED_SYNC", "main.py", "predator_auto_closed_sync_v1_status", "MAIN_EXISTING_LOCK_COORDINATOR_UPGRADE", 67518, 67573, fresh_read_line=67525, authoritative_write_lines=(67562,), local_lock_line=67523, commit_guard_line=67518, nested_reentry=True, revalidation=True, external_collection_outside=True, sidecar_outside=True),
        _placement("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP", "main.py", "_trpsf_v1_bootstrap_registry", "MAIN_EXISTING_LOCK_COORDINATOR_UPGRADE", 50534, 50896, fresh_read_line=50573, authoritative_write_lines=(50817, 50825, 50874, 50883), local_lock_line=50564, commit_guard_line=50534, nested_reentry=True, revalidation=True, sidecar_outside=False),
    ]


def canonical_runtime_writer_lock_protocol_v1() -> dict[str, Any]:
    return {
        "acquisition_order": ["C3_SHARED_INTERPROCESS_COORDINATOR", "PROCESS_LOCAL_RLOCK"],
        "release_order": ["PROCESS_LOCAL_RLOCK", "C3_SHARED_INTERPROCESS_COORDINATOR"],
        "same_owner_token_across_nested_calls": True,
        "fresh_read_after_coordinator_acquire": True,
        "bounded_acquire_deadline": True,
        "fail_closed_on_timeout": True,
        "release_on_all_returns": True,
        "release_on_all_exceptions": True,
        "external_collection_while_held": False,
        "broker_call_while_held": False,
    }


def canonical_runtime_writer_partial_commit_truth_v1() -> list[dict[str, Any]]:
    return [
        {
            "writer_id": writer_id,
            "registry_commit_becomes_true_only_after_confirmed_save": True,
            "sidecar_failure_cannot_downgrade_registry_commit": True,
            "registry_committed_and_sidecar_persisted_are_separate": True,
            "retry_reconciles_registry_before_reapply": True,
        }
        for writer_id in (
            "MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE",
            "MAIN_TRADE_CLOSE_OUTCOME_COMMIT",
        )
    ]


def runtime_writer_transaction_placement_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def runtime_writer_transaction_placement_rehearsal_sha256_v1(rehearsal: Mapping[str, Any]) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256({key: value for key, value in rehearsal.items() if key != "rehearsal_sha256"})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "transaction_placement_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "declarative_only": True,
        "write_executed": False,
        "source_file_written": False,
        "registry_read": False,
        "registry_write": False,
        "lock_acquired": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "transaction_placement_receipt": None,
    }


def _check_upstream(result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]) -> str:
    receipt = result.get("patch_plan_receipt")
    supplied = _valid_sha256(receipt.get("patch_plan_receipt_sha256")) if isinstance(receipt, Mapping) else ""
    expected = _stable_sha256({key: value for key, value in receipt.items() if key != "patch_plan_receipt_sha256"}) if isinstance(receipt, Mapping) else ""
    checks["upstream_patch_plan_valid"] = bool(
        result.get("ok") is True
        and result.get("patch_plan_contract_verified") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and hmac.compare_digest(supplied, expected)
        and receipt.get("writer_operation_count") == 19
        and receipt.get("apply_allowed") is False
    )
    if not checks["upstream_patch_plan_valid"]:
        reasons.append("TRANSACTION_PLACEMENT_UPSTREAM_PATCH_PLAN_INVALID")
    return supplied


def _check_spec(spec: Mapping[str, Any], upstream_sha: str, reasons: list[str], checks: dict[str, bool]) -> str:
    supplied = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(supplied and hmac.compare_digest(supplied, runtime_writer_transaction_placement_spec_sha256_v1(spec)))
    expected = canonical_runtime_writer_transaction_placements_v1()
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    placements = spec.get("placements")
    writer_ids = [item["writer_id"] for item in expected]
    checks["placements_exact"] = bool(
        placements == expected
        and len(expected) == 19
        and len(set(writer_ids)) == 19
        and writer_ids == [item["writer_id"] for item in inventory]
        and Counter(item["classification"] for item in expected) == Counter(_CLASS_COUNTS)
        and all(item["release_on_all_returns"] and item["release_on_all_exceptions"] for item in expected)
        and all(item["acquire_before_line"] <= min(item["authoritative_write_lines"]) <= item["release_after_line"] for item in expected)
        and all(item["fresh_read_after_acquire_line"] is not None for item in expected if item["writer_id"] != "TRADE_REGISTRY_RESET")
    )
    checks["protocol_exact"] = spec.get("lock_protocol") == canonical_runtime_writer_lock_protocol_v1()
    checks["partial_commit_truth_exact"] = spec.get("partial_commit_truth") == canonical_runtime_writer_partial_commit_truth_v1()
    checks["chain_and_safety_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_patch_plan_receipt_sha256") == upstream_sha
        and spec.get("classification_counts") == _CLASS_COUNTS
        and spec.get("declarative_only") is True
        and spec.get("patch_content_present") is False
        and spec.get("apply_entrypoint_present") is False
        and spec.get("runtime_imported") is False
        and spec.get("source_file_written") is False
        and spec.get("live_allowed") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "TRANSACTION_PLACEMENT_SPEC_SHA256_INVALID"),
        ("placements_exact", "TRANSACTION_PLACEMENTS_INVALID"),
        ("protocol_exact", "TRANSACTION_PLACEMENT_LOCK_PROTOCOL_INVALID"),
        ("partial_commit_truth_exact", "TRANSACTION_PLACEMENT_PARTIAL_COMMIT_TRUTH_INVALID"),
        ("chain_and_safety_valid", "TRANSACTION_PLACEMENT_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied


def _check_rehearsal(rehearsal: Mapping[str, Any], spec_sha: str, reasons: list[str], checks: dict[str, bool]) -> str:
    supplied = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(supplied and hmac.compare_digest(supplied, runtime_writer_transaction_placement_rehearsal_sha256_v1(rehearsal)))
    receipts = rehearsal.get("writer_receipts")
    expected = canonical_runtime_writer_transaction_placements_v1()
    checks["rehearsal_protocol_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("spec_sha256") == spec_sha
        and isinstance(receipts, list)
        and [item.get("writer_id") for item in receipts if isinstance(item, Mapping)] == [item["writer_id"] for item in expected]
        and len(receipts) == 19
        and all(
            isinstance(item, Mapping)
            and item.get("synthetic_acquire") is True
            and item.get("fresh_read_rehearsed") is (placement["fresh_read_after_acquire_line"] is not None)
            and item.get("authoritative_write_simulated") is True
            and item.get("return_release_rehearsed") is True
            and item.get("exception_release_rehearsed") is True
            and item.get("real_lock_acquired") is False
            and item.get("registry_read") is False
            and item.get("registry_write") is False
            for item, placement in zip(receipts, expected)
        )
        and rehearsal.get("classification_counts") == _CLASS_COUNTS
        and rehearsal.get("negative_controls") == _NEGATIVE_CONTROLS
        and rehearsal.get("partial_commit_truth_case_count") == 2
        and rehearsal.get("source_bytes_preserved") is True
        and rehearsal.get("runtime_executed") is False
        and rehearsal.get("live_allowed") is False
    )
    if not checks["rehearsal_sha256_valid"]:
        reasons.append("TRANSACTION_PLACEMENT_REHEARSAL_SHA256_INVALID")
    if not checks["rehearsal_protocol_valid"]:
        reasons.append("TRANSACTION_PLACEMENT_REHEARSAL_PROTOCOL_INVALID")
    return supplied


def evaluate_closed_repair_runtime_writer_transaction_placement_offline_v1(
    runtime_patch_plan_result: Mapping[str, Any],
    transaction_placement_spec: Mapping[str, Any],
    transaction_placement_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate exact placements while keeping every runtime action denied."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    values = (runtime_patch_plan_result, transaction_placement_spec, transaction_placement_rehearsal)
    if not all(isinstance(value, Mapping) for value in values):
        reasons.append("TRANSACTION_PLACEMENT_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream, spec, rehearsal = (_canonical_copy(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        reasons.append("TRANSACTION_PLACEMENT_INPUT_NOT_CANONICALIZABLE")
        return base
    upstream_sha = _check_upstream(upstream, reasons, checks)
    spec_sha = _check_spec(spec, upstream_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(rehearsal, spec_sha, reasons, checks)
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_TRANSACTION_PLACEMENT_CHECKS_FAILED")
        return base
    receipt = {
        "upstream_patch_plan_receipt_sha256": upstream_sha,
        "source_preconditions_sha256": upstream["patch_plan_receipt"]["source_preconditions_sha256"],
        "transaction_placement_spec_sha256": spec_sha,
        "transaction_placement_rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "classification_counts": dict(_CLASS_COUNTS),
        "partial_commit_truth_case_count": 2,
        "real_lock_acquired": False,
        "registry_read": False,
        "registry_write": False,
        "source_file_written": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["transaction_placement_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "transaction_placement_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "status": "CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_V1_VALID_OFFLINE_DORMANT",
            "reasons": [],
            "checks": checks,
            "transaction_placement_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_CONTRACT_V1_VERSION",
    "canonical_runtime_writer_lock_protocol_v1",
    "canonical_runtime_writer_partial_commit_truth_v1",
    "canonical_runtime_writer_transaction_placements_v1",
    "evaluate_closed_repair_runtime_writer_transaction_placement_offline_v1",
    "runtime_writer_transaction_placement_rehearsal_sha256_v1",
    "runtime_writer_transaction_placement_spec_sha256_v1",
]
