"""Hash-bound, non-applicable patch plan for two C3 preflight P1 gaps.

This contract describes the required semantic changes without carrying patch
content or an apply surface.  A valid result is an offline planning receipt;
runtime modification, activation, production and Live always remain denied.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_CONTRACT_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-READINESS-PREFLIGHT-PATCH-PLAN-CONTRACT-V1"
)

_PLAN_VERSION = "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_OFFLINE_V1"
_REHEARSAL_VERSION = "C3_READINESS_PREFLIGHT_P1_PATCH_REHEARSAL_SYNTHETIC_V1"
_SCOPE_ATTESTATION = "C3_READINESS_PREFLIGHT_P1_PATCH_PLANNING_OFFLINE_ONLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_CONTRACT_PIN = {
    "role": "readiness_binding_contract",
    "path": "trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py",
    "sha256": "ec3ddc46fff55b3d22bcbfd36b061dae1966d39ad9cfadd20e103f6ff4070b47",
    "normalized_size_bytes": 16719,
}
_REHEARSAL_PHASES = (
    "ATTEST_FIVE_SOURCE_HASHES",
    "VERIFY_UPSTREAM_READINESS_BINDING_RECEIPT",
    "CLASSIFY_TWO_CURRENT_P1_GAPS",
    "PROJECT_EXACT_RUNTIME_VECTOR_GATE",
    "PROJECT_STATIC_AST_SEMANTIC_PROOF",
    "VERIFY_NEGATIVE_ACCEPTANCE_MATRIX",
    "VERIFY_ROLLBACK_AND_SOURCE_PRESERVATION",
    "EMIT_NON_APPLICABLE_PATCH_PLAN_RECEIPT",
)
_PRODUCTION_BLOCKERS = (
    "PATCH_PLAN_IS_DECLARATIVE_ONLY",
    "PATCH_CONTENT_IS_ABSENT",
    "REPLACEMENT_TEXT_IS_ABSENT",
    "PATCH_APPLY_ENTRYPOINT_IS_ABSENT",
    "PATCH_IMPLEMENTATION_EXISTS_ONLY_IN_ISOLATED_WORKTREE",
    "IMPLEMENTED_SOURCE_IS_NOT_COMMITTED_OR_DEPLOYED",
    "RUNTIME_SEAM_REMAINS_DEFAULT_OFF",
    "SOURCE_HASHES_MUST_BE_RECHECKED_BEFORE_FUTURE_EDIT",
    "SEPARATE_PATCH_IMPLEMENTATION_REQUIRED",
    "SEPARATE_PRODUCTION_AUTHORIZATION_REQUIRED",
    "LIVE_TRADING_REMAINS_FORBIDDEN",
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


def _receipt_sha256(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def canonical_c3_preflight_patch_source_pins_v1() -> list[dict[str, Any]]:
    return binding.canonical_c3_readiness_source_attestation_pins_v1() + [
        _canonical_copy(_BINDING_CONTRACT_PIN)
    ]


def canonical_c3_preflight_p1_patch_operations_v1() -> list[dict[str, Any]]:
    required_fields = list(binding.canonical_c3_runtime_readiness_vector_v1())
    return [
        {
            "operation_id": "MAIN_LIVE_PREFLIGHT_REQUIRE_EXACT_C3_VECTOR",
            "finding_priority": "P1",
            "target_role": "live_preflight_owner",
            "target_path": "main.py",
            "target_function": "_frpp_v1_build_checklist",
            "pre_patch_semantics": "COORDINATION_READY_SINGLE_FIELD_ONLY",
            "pre_patch_guard_fields": ["coordination_ready"],
            "current_semantics": "ALL_EXACT_C3_READINESS_FIELDS_CONJUNCTION",
            "current_guard_fields": required_fields,
            "required_semantics": "ALL_EXACT_C3_READINESS_FIELDS_CONJUNCTION",
            "required_guard_fields": required_fields,
            "post_patch_semantics_verified_offline": True,
            "require_decision_time_sample": True,
            "require_upstream_activation_receipt_sha256": True,
            "generic_ok_forbidden": True,
            "declarative_only": True,
            "patch_payload_present": False,
            "replacement_text_present": False,
            "apply_allowed": False,
        },
        {
            "operation_id": "STATIC_PREFLIGHT_PROVE_C3_VECTOR_AST_SEMANTICS",
            "finding_priority": "P1",
            "target_role": "static_preflight",
            "target_path": "trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py",
            "target_function": "evaluate_closed_repair_runtime_static_preflight_v1",
            "pre_patch_semantics": "CHECK_CODE_STRING_LITERAL_MEMBERSHIP_ONLY",
            "pre_patch_guard_fields": [],
            "current_semantics": "EXACT_ADD_PREDICATE_AST_CONJUNCTION",
            "current_guard_fields": required_fields,
            "required_semantics": "EXACT_ADD_PREDICATE_AST_CONJUNCTION",
            "required_guard_fields": required_fields,
            "post_patch_semantics_verified_offline": True,
            "require_decision_time_sample": True,
            "require_upstream_activation_receipt_sha256": True,
            "generic_ok_forbidden": True,
            "declarative_only": True,
            "patch_payload_present": False,
            "replacement_text_present": False,
            "apply_allowed": False,
        },
    ]


def canonical_c3_preflight_patch_acceptance_matrix_v1() -> list[dict[str, Any]]:
    fields = list(binding.canonical_c3_runtime_readiness_vector_v1())
    cases = [
        {
            "case_id": f"LIVE_GATE_REJECTS_WEAKENED_{field.upper()}",
            "layer": "live_preflight",
            "mutation": {"field": field, "kind": "WEAKEN_EXPECTED_VALUE"},
            "expected": "BLOCKED",
        }
        for field in fields
    ]
    cases.extend(
        [
            {
                "case_id": "LIVE_GATE_REJECTS_MISSING_FIELD",
                "layer": "live_preflight",
                "mutation": {"kind": "REMOVE_REQUIRED_FIELD"},
                "expected": "BLOCKED",
            },
            {
                "case_id": "LIVE_GATE_REJECTS_GENERIC_OK_ONLY",
                "layer": "live_preflight",
                "mutation": {"kind": "REPLACE_VECTOR_WITH_GENERIC_OK"},
                "expected": "BLOCKED",
            },
            {
                "case_id": "STATIC_PREFLIGHT_REJECTS_LITERAL_ONLY",
                "layer": "static_preflight",
                "mutation": {"kind": "CHECK_CODE_LITERAL_WITHOUT_VECTOR"},
                "expected": "BLOCKED",
            },
            {
                "case_id": "STATIC_PREFLIGHT_REJECTS_OR_COMPOSITION",
                "layer": "static_preflight",
                "mutation": {"kind": "REPLACE_REQUIRED_AND_WITH_OR"},
                "expected": "BLOCKED",
            },
            {
                "case_id": "STATIC_PREFLIGHT_REJECTS_CACHED_STATUS",
                "layer": "static_preflight",
                "mutation": {"kind": "REMOVE_DECISION_TIME_STATUS_CALL"},
                "expected": "BLOCKED",
            },
            {
                "case_id": "EXACT_VECTOR_AND_HASH_BINDING_ACCEPTED_OFFLINE",
                "layer": "composition",
                "mutation": {"kind": "NONE_SYNTHETIC_EXACT_POLICY"},
                "expected": "OFFLINE_POLICY_VALID_PRODUCTION_DENIED",
            },
        ]
    )
    return cases


def c3_preflight_patch_plan_sha256_v1(plan: Mapping[str, Any]) -> str:
    if not isinstance(plan, Mapping):
        raise TypeError("plan must be a mapping")
    return _stable_sha256({key: value for key, value in plan.items() if key != "plan_sha256"})


def c3_preflight_patch_rehearsal_sha256_v1(rehearsal: Mapping[str, Any]) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256(
        {key: value for key, value in rehearsal.items() if key != "rehearsal_sha256"}
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "patch_plan_contract_verified": False,
        "upstream_readiness_binding_verified": False,
        "source_preconditions_verified": False,
        "two_p1_findings_covered": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "status": "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "declarative_only": True,
        "patch_payload_present": False,
        "replacement_text_present": False,
        "apply_entrypoint_present": False,
        "source_file_written": False,
        "write_executed": False,
        "runtime_imported": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "patch_plan_receipt": None,
    }


def _check_upstream(
    upstream: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    receipt = upstream.get("binding_receipt")
    supplied = (
        _valid_sha256(receipt.get("binding_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected = (
        _receipt_sha256(receipt, "binding_receipt_sha256")
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_binding_receipt_valid"] = bool(
        upstream.get("ok") is True
        and upstream.get("binding_contract_verified") is True
        and upstream.get("source_hashes_verified") is True
        and upstream.get("runtime_readiness_policy_verified") is True
        and upstream.get("live_preflight_policy_verified") is True
        and upstream.get("runtime_binding_satisfied") is False
        and upstream.get("production_ready") is False
        and upstream.get("apply_allowed") is False
        and upstream.get("runtime_patch_allowed") is False
        and upstream.get("activation_allowed") is False
        and upstream.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and hmac.compare_digest(supplied, expected)
        and receipt.get("source_attestation_count") == 4
        and receipt.get("required_predicate_count") == 13
        and receipt.get("writer_count") == 19
        and receipt.get("runtime_binding_satisfied") is False
        and receipt.get("production_ready") is False
        and receipt.get("apply_allowed") is False
        and receipt.get("activation_allowed") is False
        and receipt.get("live_allowed") is False
        and bool(receipt.get("production_blockers"))
    )
    if not checks["upstream_binding_receipt_valid"]:
        reasons.append("PREFLIGHT_PATCH_PLAN_UPSTREAM_BINDING_INVALID")
    return supplied


def _check_plan(
    plan: Mapping[str, Any], upstream_sha: str, reasons: list[str], checks: dict[str, bool]
) -> tuple[str, str]:
    source_pins = canonical_c3_preflight_patch_source_pins_v1()
    source_sha = _stable_sha256(source_pins)
    checks["source_preconditions_exact"] = bool(
        plan.get("source_preconditions") == source_pins
        and len(source_pins) == 5
        and len({item["role"] for item in source_pins}) == 5
        and plan.get("source_preconditions_sha256") == source_sha
    )

    operations = canonical_c3_preflight_p1_patch_operations_v1()
    matrix = canonical_c3_preflight_patch_acceptance_matrix_v1()
    checks["two_p1_operations_exact"] = bool(
        plan.get("operations") == operations
        and plan.get("operations_sha256") == _stable_sha256(operations)
        and len(operations) == 2
        and {item["finding_priority"] for item in operations} == {"P1"}
        and {item["target_path"] for item in operations}
        == {
            "main.py",
            "trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py",
        }
        and all(
            item.get("declarative_only") is True
            and item.get("patch_payload_present") is False
            and item.get("replacement_text_present") is False
            and item.get("apply_allowed") is False
            for item in operations
        )
    )
    checks["acceptance_matrix_exact"] = bool(
        plan.get("acceptance_matrix") == matrix
        and plan.get("acceptance_matrix_sha256") == _stable_sha256(matrix)
        and len(matrix) == 19
        and len({item["case_id"] for item in matrix}) == 19
    )
    safety = plan.get("safety_envelope")
    checks["plan_safety_envelope_exact"] = bool(
        plan.get("plan_version") == _PLAN_VERSION
        and plan.get("upstream_binding_receipt_sha256") == upstream_sha
        and isinstance(safety, Mapping)
        and safety.get("scope_attestation") == _SCOPE_ATTESTATION
        and safety.get("declarative_only") is True
        and safety.get("patch_payload_present") is False
        and safety.get("replacement_text_present") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("source_file_written") is False
        and safety.get("write_executed") is False
        and safety.get("runtime_imported") is False
        and safety.get("runtime_integrated") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("broker_called") is False
        and safety.get("activation_allowed") is False
        and safety.get("live_allowed") is False
        and safety.get("no_order_sent") is True
    )
    supplied_plan_sha = _valid_sha256(plan.get("plan_sha256"))
    checks["plan_sha256_valid"] = bool(
        supplied_plan_sha
        and hmac.compare_digest(supplied_plan_sha, c3_preflight_patch_plan_sha256_v1(plan))
    )
    for check, reason in (
        ("source_preconditions_exact", "PREFLIGHT_PATCH_PLAN_SOURCE_PRECONDITIONS_INVALID"),
        ("two_p1_operations_exact", "PREFLIGHT_PATCH_PLAN_OPERATIONS_INVALID"),
        ("acceptance_matrix_exact", "PREFLIGHT_PATCH_PLAN_ACCEPTANCE_MATRIX_INVALID"),
        ("plan_safety_envelope_exact", "PREFLIGHT_PATCH_PLAN_SAFETY_INVALID"),
        ("plan_sha256_valid", "PREFLIGHT_PATCH_PLAN_SHA256_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_plan_sha, source_sha


def _check_rehearsal(
    rehearsal: Mapping[str, Any], plan_sha: str, source_sha: str, reasons: list[str], checks: dict[str, bool]
) -> str:
    required_fields = list(binding.canonical_c3_runtime_readiness_vector_v1())
    checks["rehearsal_current_findings_exact"] = rehearsal.get("current_findings") == [
        {
            "finding_id": "P1_MAIN_LIVE_GATE_SINGLE_FIELD",
            "observed_fields": required_fields,
            "missing_required_fields": [],
            "blocked": False,
            "resolution_verified_offline": True,
        },
        {
            "finding_id": "P1_STATIC_PREFLIGHT_LITERAL_ONLY",
            "observed_semantics": "EXACT_ADD_PREDICATE_AST_CONJUNCTION",
            "semantic_vector_proven": True,
            "blocked": False,
            "resolution_verified_offline": True,
        },
    ]
    projected = rehearsal.get("projected_outcome")
    checks["rehearsal_projected_semantics_exact"] = bool(
        isinstance(projected, Mapping)
        and projected.get("required_guard_fields") == required_fields
        and projected.get("required_guard_count") == 13
        and projected.get("all_fields_conjunctive") is True
        and projected.get("decision_time_status_sample_required") is True
        and projected.get("activation_receipt_sha256_required") is True
        and projected.get("static_ast_semantic_proof_required") is True
        and projected.get("negative_case_count") == 18
        and projected.get("projected_blockers") == []
        and projected.get("source_changed") is False
        and projected.get("patch_applied") is False
        and projected.get("runtime_executed") is False
        and projected.get("activation_allowed") is False
        and projected.get("live_allowed") is False
    )
    checks["rehearsal_sequence_and_safety_exact"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("patch_plan_sha256") == plan_sha
        and rehearsal.get("source_preconditions_sha256") == source_sha
        and rehearsal.get("event_sequence") == list(_REHEARSAL_PHASES)
        and rehearsal.get("source_bytes_preserved") is True
        and rehearsal.get("write_executed") is False
        and rehearsal.get("runtime_imported") is False
        and rehearsal.get("runtime_integrated") is False
        and rehearsal.get("real_registry_accessed") is False
        and rehearsal.get("network_accessed") is False
        and rehearsal.get("broker_called") is False
        and rehearsal.get("no_order_sent") is True
    )
    supplied = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied
        and hmac.compare_digest(
            supplied,
            c3_preflight_patch_rehearsal_sha256_v1(rehearsal),
        )
    )
    for check, reason in (
        ("rehearsal_current_findings_exact", "PREFLIGHT_PATCH_REHEARSAL_CURRENT_FINDINGS_INVALID"),
        ("rehearsal_projected_semantics_exact", "PREFLIGHT_PATCH_REHEARSAL_PROJECTED_OUTCOME_INVALID"),
        ("rehearsal_sequence_and_safety_exact", "PREFLIGHT_PATCH_REHEARSAL_SAFETY_INVALID"),
        ("rehearsal_sha256_valid", "PREFLIGHT_PATCH_REHEARSAL_SHA256_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied


def evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(
    readiness_binding_result: Mapping[str, Any],
    patch_plan: Mapping[str, Any],
    synthetic_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a non-applicable plan and always deny patching/activation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (readiness_binding_result, patch_plan, synthetic_rehearsal)
    ):
        reasons.append("PREFLIGHT_PATCH_PLAN_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(readiness_binding_result)
        plan = _canonical_copy(patch_plan)
        rehearsal = _canonical_copy(synthetic_rehearsal)
    except (TypeError, ValueError, OverflowError):
        reasons.append("PREFLIGHT_PATCH_PLAN_INPUT_NOT_CANONICALIZABLE")
        return base

    upstream_sha = _check_upstream(upstream, reasons, checks)
    plan_sha, source_sha = _check_plan(plan, upstream_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(rehearsal, plan_sha, source_sha, reasons, checks)
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_PREFLIGHT_PATCH_PLAN_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_binding_receipt_sha256": upstream_sha,
        "patch_plan_sha256": plan_sha,
        "synthetic_rehearsal_sha256": rehearsal_sha,
        "source_preconditions_sha256": source_sha,
        "source_file_count": 5,
        "p1_finding_count": 2,
        "patch_operation_count": 2,
        "required_guard_count": 13,
        "acceptance_case_count": 19,
        "patch_content_present": False,
        "replacement_text_present": False,
        "source_hashes_must_be_rechecked": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["patch_plan_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "patch_plan_contract_verified": True,
            "upstream_readiness_binding_verified": True,
            "source_preconditions_verified": True,
            "two_p1_findings_covered": True,
            "synthetic_rehearsal_valid": True,
            "status": "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_V1_VALID_OFFLINE_NON_APPLICABLE",
            "reasons": [],
            "checks": checks,
            "patch_plan_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_CONTRACT_V1_VERSION",
    "c3_preflight_patch_plan_sha256_v1",
    "c3_preflight_patch_rehearsal_sha256_v1",
    "canonical_c3_preflight_p1_patch_operations_v1",
    "canonical_c3_preflight_patch_acceptance_matrix_v1",
    "canonical_c3_preflight_patch_source_pins_v1",
    "evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1",
]
