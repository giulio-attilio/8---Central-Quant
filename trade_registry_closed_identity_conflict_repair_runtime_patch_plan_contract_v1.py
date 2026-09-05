"""Non-applicable, hash-bound patch plan for CLOSED-repair integration.

The contract validates declarative operations only.  It contains no patch
payload, replacement text, file writer, runtime import or apply entrypoint.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_contract_v1 as installation_manifest
import trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_contract_v1 as projection
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PATCH-PLAN-CONTRACT-V1"
)

_PLAN_VERSION = "DORMANT_CLOSED_REPAIR_RUNTIME_HASH_BOUND_PATCH_PLAN_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_RUNTIME_PATCH_PLAN_REHEARSAL_V1"
_SOURCE_SET_VERSION = "READ_ONLY_CLOSED_REPAIR_RUNTIME_SOURCE_PRECONDITIONS_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MUTATED_FILES = ("trade_registry.py", "main.py")
_VERIFIED_ONLY_FILES = (
    "bots/meme.py",
    "bots/predator.py",
    "bots/turtle.py",
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py",
    "trade_registry_closed_identity_conflict_repair_production_provider_v1.py",
)
_SOURCE_FILES = _MUTATED_FILES + _VERIFIED_ONLY_FILES
_REHEARSAL_PHASES = (
    "ATTEST_SOURCE_HASHES",
    "VALIDATE_CURRENT_NINE_BLOCKERS",
    "VALIDATE_PATCH_OPERATION_COVERAGE",
    "VALIDATE_ALL_19_WRITER_SEAMS",
    "VALIDATE_PROVIDER_DEFAULT_OFF",
    "VALIDATE_ROLLBACK",
    "EMIT_NON_APPLICABLE_PLAN_RECEIPT",
)
_ROLLBACK = (
    "REJECT_ON_ANY_SOURCE_HASH_DRIFT",
    "REJECT_ON_ANY_MISSING_OPERATION",
    "REJECT_ON_UNKNOWN_OPERATION",
    "REJECT_ON_PATCH_PAYLOAD_PRESENCE",
    "REJECT_ON_APPLY_REQUEST",
    "PRESERVE_ALL_SOURCE_BYTES",
    "PRESERVE_RUNTIME_STATE",
    "PRESERVE_LIVE_DENIAL",
)
_PRODUCTION_BLOCKERS = (
    "PATCH_PLAN_IS_DECLARATIVE_ONLY",
    "PATCH_CONTENT_IS_ABSENT",
    "PATCH_APPLY_ENTRYPOINT_IS_ABSENT",
    "REAL_SOURCE_HASHES_MUST_BE_RECHECKED_BEFORE_FUTURE_EDIT",
    "REAL_RUNTIME_SOURCE_WAS_NOT_CHANGED",
    "RUNTIME_INSTALLATION_WAS_NOT_PERFORMED",
    "PRODUCTION_AND_LIVE_REMAIN_UNAUTHORIZED",
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


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def canonical_runtime_patch_source_files_v1() -> list[str]:
    return list(_SOURCE_FILES)


def canonical_runtime_patch_rehearsal_phases_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": index * 10, "phase": phase}
        for index, phase in enumerate(_REHEARSAL_PHASES, start=1)
    ]


def canonical_runtime_patch_rollback_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": index * 10, "step": step}
        for index, step in enumerate(_ROLLBACK, start=1)
    ]


def _operation(
    operation_id: str,
    kind: str,
    *,
    writer_id: str | None = None,
    function: str | None = None,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "kind": kind,
        "writer_id": writer_id,
        "function": function,
        "declarative_only": True,
        "patch_payload_present": False,
        "replacement_text_present": False,
        "apply_allowed": False,
    }


def canonical_runtime_patch_operations_v1() -> dict[str, list[dict[str, Any]]]:
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    registry_writers = [item for item in inventory if item["component"] == "trade_registry.py"]
    main_writers = [item for item in inventory if item["component"] == "main.py"]
    if len(registry_writers) != 8 or len(main_writers) != 11:
        raise AssertionError("runtime patch writer inventory diverged")
    registry_operations = [
        _operation("TR_IMPORT_COORDINATION_SEAM_API", "DECLARE_COORDINATION_SEAM_DEPENDENCY")
    ] + [
        _operation(
            f"TR_WRITER_SEAM_{index:02d}",
            "DECLARE_BODY_COORDINATION_SEAM",
            writer_id=writer["writer_id"],
            function=writer["function"],
        )
        for index, writer in enumerate(registry_writers, start=1)
    ]
    main_operations = [
        _operation("MAIN_IMPORT_C3_CAPABILITIES", "DECLARE_RUNTIME_CAPABILITY_IMPORTS"),
        _operation("MAIN_DEFINE_C3_INSTALLER", "DECLARE_DEFAULT_OFF_PROVIDER_INSTALLER"),
        _operation("MAIN_DEFINE_C3_RECOVERY", "DECLARE_FAIL_CLOSED_STARTUP_RECOVERY"),
        _operation("MAIN_REORDER_PERSISTENCE_BOOTSTRAP", "DECLARE_BOOTSTRAP_BEFORE_PROVIDER"),
        _operation("MAIN_GATE_BOT_IMPORTS_THREADS", "DECLARE_BOT_IMPORT_AND_THREAD_GATE"),
        _operation("MAIN_REQUIRE_C3_LIVE_PREFLIGHT", "DECLARE_BLOCKING_LIVE_PREFLIGHT_CHECK"),
        _operation("MAIN_MOVE_RUNTIME_START", "DECLARE_RUNTIME_START_AFTER_ALL_DEFINITIONS"),
    ] + [
        _operation(
            f"MAIN_WRITER_SEAM_{index:02d}",
            "DECLARE_BODY_COORDINATION_SEAM",
            writer_id=writer["writer_id"],
            function=writer["function"],
        )
        for index, writer in enumerate(main_writers, start=1)
    ]
    return {"trade_registry.py": registry_operations, "main.py": main_operations}


def canonical_runtime_patch_blocker_coverage_v1() -> list[dict[str, Any]]:
    mapping = (
        ("ALL_19_WRITER_BODY_SEAMS_COORDINATED", ("TR_IMPORT_COORDINATION_SEAM_API", "TR_WRITER_SEAM_01", "TR_WRITER_SEAM_02", "TR_WRITER_SEAM_03", "TR_WRITER_SEAM_04", "TR_WRITER_SEAM_05", "TR_WRITER_SEAM_06", "TR_WRITER_SEAM_07", "TR_WRITER_SEAM_08", "MAIN_WRITER_SEAM_01", "MAIN_WRITER_SEAM_02", "MAIN_WRITER_SEAM_03", "MAIN_WRITER_SEAM_04", "MAIN_WRITER_SEAM_05", "MAIN_WRITER_SEAM_06", "MAIN_WRITER_SEAM_07", "MAIN_WRITER_SEAM_08", "MAIN_WRITER_SEAM_09", "MAIN_WRITER_SEAM_10", "MAIN_WRITER_SEAM_11")),
        ("C3_RUNTIME_DEPENDENCIES_IMPORTED", ("MAIN_IMPORT_C3_CAPABILITIES",)),
        ("PRODUCTION_TRANSACTION_STORE_PRESENT", ("MAIN_IMPORT_C3_CAPABILITIES",)),
        ("PERSISTENCE_BOOTSTRAP_BEFORE_RUNTIME_START", ("MAIN_REORDER_PERSISTENCE_BOOTSTRAP", "MAIN_MOVE_RUNTIME_START")),
        ("C3_PROVIDER_INSTALLED_BEFORE_RUNTIME_START", ("MAIN_DEFINE_C3_INSTALLER", "MAIN_MOVE_RUNTIME_START")),
        ("C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES", ("MAIN_IMPORT_C3_CAPABILITIES", "MAIN_DEFINE_C3_INSTALLER")),
        ("C3_STARTUP_RECOVERY_BEFORE_RUNTIME_START", ("MAIN_DEFINE_C3_RECOVERY", "MAIN_MOVE_RUNTIME_START")),
        ("BY_NAME_BOT_WRITER_IMPORTS_GATED", ("MAIN_GATE_BOT_IMPORTS_THREADS", "TR_IMPORT_COORDINATION_SEAM_API")),
        ("LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION", ("MAIN_REQUIRE_C3_LIVE_PREFLIGHT",)),
    )
    return [
        {"blocker_code": blocker, "required_operation_ids": list(operation_ids)}
        for blocker, operation_ids in mapping
    ]


def runtime_patch_source_preconditions_sha256_v1(evidence: Mapping[str, Any]) -> str:
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    return _stable_sha256(
        {key: value for key, value in evidence.items() if key != "source_set_sha256"}
    )


def runtime_patch_plan_sha256_v1(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping):
        raise TypeError("plan must be a mapping")
    return _stable_sha256(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )


def runtime_patch_rehearsal_sha256_v1(rehearsal: Mapping[str, Any]) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256(
        {key: value for key, value in rehearsal.items() if key != "rehearsal_sha256"}
    )


def _receipt_sha(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "patch_plan_contract_verified": False,
        "source_preconditions_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "CLOSED_REPAIR_RUNTIME_PATCH_PLAN_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "declarative_only": True,
        "patch_content_present": False,
        "write_executed": False,
        "source_file_written": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "patch_plan_receipt": None,
    }


def _check_upstream(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    receipt = result.get("projection_receipt")
    supplied = _valid_sha256(receipt.get("projection_receipt_sha256")) if isinstance(receipt, Mapping) else ""
    expected = _receipt_sha(receipt, "projection_receipt_sha256") if isinstance(receipt, Mapping) else ""
    checks["upstream_projection_valid"] = bool(
        result.get("ok") is True
        and result.get("projection_contract_verified") is True
        and result.get("synthetic_static_readiness_proven") is True
        and result.get("production_ready") is False
        and result.get("runtime_install_allowed") is False
        and result.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and hmac.compare_digest(supplied, expected)
        and receipt.get("resolved_blocker_count") == 9
        and receipt.get("real_runtime_readiness_proven") is False
    )
    if not checks["upstream_projection_valid"]:
        reasons.append("RUNTIME_PATCH_PLAN_UPSTREAM_PROJECTION_INVALID")
    return supplied


def _check_sources(
    evidence: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    supplied = _valid_sha256(evidence.get("source_set_sha256"))
    files = evidence.get("files")
    checks["source_precondition_sha256_valid"] = bool(
        supplied
        and hmac.compare_digest(supplied, runtime_patch_source_preconditions_sha256_v1(evidence))
    )
    checks["source_preconditions_exact"] = bool(
        evidence.get("source_set_version") == _SOURCE_SET_VERSION
        and isinstance(files, list)
        and [item.get("relative_path") for item in files if isinstance(item, Mapping)] == list(_SOURCE_FILES)
        and all(
            isinstance(item, Mapping)
            and set(item) == {"relative_path", "sha256", "size_bytes", "role"}
            and _valid_sha256(item.get("sha256"))
            and int(item.get("size_bytes") or 0) > 0
            and item.get("role") in {"MUTATE_DECLARATIVELY", "VERIFY_UNCHANGED"}
            for item in files
        )
        and [item["relative_path"] for item in files if item.get("role") == "MUTATE_DECLARATIVELY"] == list(_MUTATED_FILES)
        and [item["relative_path"] for item in files if item.get("role") == "VERIFY_UNCHANGED"] == list(_VERIFIED_ONLY_FILES)
        and evidence.get("read_only_collection") is True
        and evidence.get("secret_files_excluded") is True
    )
    current = evidence.get("current_static_preflight")
    pre_install_attested = bool(
        isinstance(current, Mapping)
        and current.get("evaluation_complete") is True
        and current.get("static_readiness") is False
        and current.get("production_ready") is False
        and current.get("live_allowed") is False
        and current.get("runtime_executed") is False
        and current.get("blockers")
        == projection.canonical_resolved_runtime_preflight_blockers_v1()
        and current.get("writer_summary")
        == {
            "expected_count": 19,
            "discovered_count": 19,
            "signature_mismatch_count": 0,
            "anchor_mismatch_count": 0,
            "coordinated_count": 0,
        }
    )
    post_install_attested = bool(
        isinstance(current, Mapping)
        and current.get("evaluation_complete") is True
        and current.get("static_readiness") is True
        and current.get("production_ready") is False
        and current.get("live_allowed") is False
        and current.get("runtime_executed") is False
        and current.get("blockers") == []
        and current.get("writer_summary")
        == {
            "expected_count": 19,
            "discovered_count": 19,
            "signature_mismatch_count": 0,
            "anchor_mismatch_count": 0,
            "coordinated_count": 19,
        }
    )
    checks["current_nine_blockers_attested"] = bool(
        pre_install_attested or post_install_attested
    )
    if not checks["source_precondition_sha256_valid"]:
        reasons.append("RUNTIME_PATCH_SOURCE_PRECONDITION_SHA256_INVALID")
    if not checks["source_preconditions_exact"]:
        reasons.append("RUNTIME_PATCH_SOURCE_PRECONDITIONS_INVALID")
    if not checks["current_nine_blockers_attested"]:
        reasons.append("RUNTIME_PATCH_CURRENT_PREFLIGHT_INVALID")
    return supplied


def _check_plan(
    plan: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
    projection_sha: str,
    source_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied = _valid_sha256(plan.get("plan_sha256"))
    checks["plan_sha256_valid"] = bool(
        supplied and hmac.compare_digest(supplied, runtime_patch_plan_sha256_v1(plan))
    )
    expected_operations = canonical_runtime_patch_operations_v1()
    expected_coverage = canonical_runtime_patch_blocker_coverage_v1()
    expected_rollback = canonical_runtime_patch_rollback_v1()
    operations = plan.get("operations_by_file")
    operation_items = [item for values in operations.values() for item in values] if isinstance(operations, Mapping) else []
    operation_ids = [item.get("operation_id") for item in operation_items if isinstance(item, Mapping)]
    writer_ids = [item.get("writer_id") for item in operation_items if isinstance(item, Mapping) and item.get("writer_id")]
    checks["operations_exact"] = bool(
        operations == expected_operations
        and len(writer_ids) == 19
        and len(set(writer_ids)) == 19
        and len(operation_ids) == len(set(operation_ids))
        and all(
            isinstance(item, Mapping)
            and set(item) == {"operation_id", "kind", "writer_id", "function", "declarative_only", "patch_payload_present", "replacement_text_present", "apply_allowed"}
            and item.get("declarative_only") is True
            and item.get("patch_payload_present") is False
            and item.get("replacement_text_present") is False
            and item.get("apply_allowed") is False
            for item in operation_items
        )
    )
    checks["blocker_coverage_exact"] = bool(
        plan.get("blocker_coverage") == expected_coverage
        and [item["blocker_code"] for item in expected_coverage]
        == projection.canonical_resolved_runtime_preflight_blockers_v1()
        and all(set(item["required_operation_ids"]).issubset(set(operation_ids)) for item in expected_coverage)
    )
    checks["rollback_exact"] = bool(
        plan.get("rollback_protocol") == expected_rollback
        and plan.get("rollback_protocol_sha256") == _stable_sha256(expected_rollback)
    )
    checks["per_file_hash_preconditions_exact"] = bool(
        plan.get("file_preconditions") == source_evidence.get("files")
        and len(plan.get("file_preconditions") or ()) == len(_SOURCE_FILES)
    )
    safety = plan.get("safety_envelope")
    checks["plan_chain_and_safety_valid"] = bool(
        plan.get("plan_version") == _PLAN_VERSION
        and plan.get("upstream_projection_receipt_sha256") == projection_sha
        and plan.get("source_preconditions_sha256") == source_sha
        and plan.get("mutated_files") == list(_MUTATED_FILES)
        and plan.get("verified_only_files") == list(_VERIFIED_ONLY_FILES)
        and plan.get("installation_order")
        == installation_manifest.canonical_runtime_installation_phases_v1()
        and isinstance(safety, Mapping)
        and safety.get("declarative_only") is True
        and safety.get("patch_content_absent") is True
        and safety.get("replacement_text_absent") is True
        and safety.get("file_writer_absent") is True
        and safety.get("apply_entrypoint_present") is False
        and safety.get("runtime_imported") is False
        and safety.get("runtime_executed") is False
        and safety.get("source_file_written") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("live_allowed") is False
    )
    for check, reason in (
        ("plan_sha256_valid", "RUNTIME_PATCH_PLAN_SHA256_INVALID"),
        ("operations_exact", "RUNTIME_PATCH_OPERATIONS_INVALID"),
        ("blocker_coverage_exact", "RUNTIME_PATCH_BLOCKER_COVERAGE_INVALID"),
        ("rollback_exact", "RUNTIME_PATCH_ROLLBACK_INVALID"),
        ("per_file_hash_preconditions_exact", "RUNTIME_PATCH_PER_FILE_HASH_PRECONDITIONS_INVALID"),
        ("plan_chain_and_safety_valid", "RUNTIME_PATCH_PLAN_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied


def _check_rehearsal(
    rehearsal: Mapping[str, Any], plan_sha: str, source_sha: str, reasons: list[str], checks: dict[str, bool]
) -> str:
    supplied = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied and hmac.compare_digest(supplied, runtime_patch_rehearsal_sha256_v1(rehearsal))
    )
    expected_phases = [item["phase"] for item in canonical_runtime_patch_rehearsal_phases_v1()]
    controls = rehearsal.get("negative_controls")
    checks["rehearsal_protocol_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("patch_plan_sha256") == plan_sha
        and rehearsal.get("source_preconditions_sha256") == source_sha
        and rehearsal.get("phase_event_sequence") == expected_phases
        and rehearsal.get("writer_operation_count") == 19
        and rehearsal.get("mutated_file_count") == 2
        and rehearsal.get("verified_only_file_count") == 7
        and isinstance(controls, Mapping)
        and controls == {
            "source_hash_drift_denied": True,
            "missing_operation_denied": True,
            "unknown_operation_denied": True,
            "patch_payload_denied": True,
            "apply_request_denied": True,
        }
        and rehearsal.get("source_bytes_preserved") is True
        and rehearsal.get("source_file_written") is False
        and rehearsal.get("runtime_executed") is False
        and rehearsal.get("live_allowed") is False
    )
    if not checks["rehearsal_sha256_valid"]:
        reasons.append("RUNTIME_PATCH_REHEARSAL_SHA256_INVALID")
    if not checks["rehearsal_protocol_valid"]:
        reasons.append("RUNTIME_PATCH_REHEARSAL_PROTOCOL_INVALID")
    return supplied


def evaluate_closed_repair_runtime_patch_plan_offline_v1(
    projection_result: Mapping[str, Any],
    source_precondition_evidence: Mapping[str, Any],
    runtime_patch_plan: Mapping[str, Any],
    runtime_patch_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a non-applicable plan and always deny source mutation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    values = (projection_result, source_precondition_evidence, runtime_patch_plan, runtime_patch_rehearsal)
    if not all(isinstance(value, Mapping) for value in values):
        reasons.append("RUNTIME_PATCH_PLAN_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream, sources, plan, rehearsal = (_canonical_copy(value) for value in values)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RUNTIME_PATCH_PLAN_INPUT_NOT_CANONICALIZABLE")
        return base
    projection_sha = _check_upstream(upstream, reasons, checks)
    source_sha = _check_sources(sources, reasons, checks)
    plan_sha = _check_plan(
        plan, sources, projection_sha, source_sha, reasons, checks
    )
    rehearsal_sha = _check_rehearsal(rehearsal, plan_sha, source_sha, reasons, checks)
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_RUNTIME_PATCH_PLAN_CHECKS_FAILED")
        return base
    receipt = {
        "upstream_projection_receipt_sha256": projection_sha,
        "source_preconditions_sha256": source_sha,
        "runtime_patch_plan_sha256": plan_sha,
        "runtime_patch_rehearsal_sha256": rehearsal_sha,
        "source_file_count": len(_SOURCE_FILES),
        "mutated_file_count": 2,
        "verified_only_file_count": 7,
        "writer_operation_count": 19,
        "resolved_blocker_count": 9,
        "source_hashes_must_be_rechecked": True,
        "patch_content_present": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["patch_plan_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "patch_plan_contract_verified": True,
            "source_preconditions_verified": True,
            "synthetic_rehearsal_valid": True,
            "status": "CLOSED_REPAIR_RUNTIME_PATCH_PLAN_V1_VALID_OFFLINE_NON_APPLICABLE",
            "reasons": [],
            "checks": checks,
            "patch_plan_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_CONTRACT_V1_VERSION",
    "canonical_runtime_patch_blocker_coverage_v1",
    "canonical_runtime_patch_operations_v1",
    "canonical_runtime_patch_rehearsal_phases_v1",
    "canonical_runtime_patch_rollback_v1",
    "canonical_runtime_patch_source_files_v1",
    "evaluate_closed_repair_runtime_patch_plan_offline_v1",
    "runtime_patch_plan_sha256_v1",
    "runtime_patch_rehearsal_sha256_v1",
    "runtime_patch_source_preconditions_sha256_v1",
]
