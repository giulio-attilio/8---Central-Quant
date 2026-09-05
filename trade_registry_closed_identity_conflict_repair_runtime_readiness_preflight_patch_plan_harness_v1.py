"""Read-only harness for the non-applicable C3 preflight P1 patch plan."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as binding_contract
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_harness_v1 as binding_harness
import trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1 as patch_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_HARNESS_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-READINESS-PREFLIGHT-PATCH-PLAN-HARNESS-V1"
)


def _verify_source_pins_read_only_v1(repository_root: str | Path) -> list[dict[str, Any]]:
    root = Path(repository_root).resolve()
    verified: list[dict[str, Any]] = []
    for pin in patch_contract.canonical_c3_preflight_patch_source_pins_v1():
        source_path = (root / pin["path"]).resolve()
        if root not in source_path.parents:
            raise AssertionError("source precondition escaped repository root")
        source_text = source_path.read_text(encoding="utf-8")
        sha256, size_bytes = binding_contract.source_text_sha256_v1(source_text)
        observed = {
            "role": pin["role"],
            "path": pin["path"],
            "sha256": sha256,
            "normalized_size_bytes": size_bytes,
        }
        if observed != pin:
            raise AssertionError(f"source precondition drifted: {pin['role']}")
        verified.append(observed)
    return verified


def build_synthetic_c3_readiness_preflight_patch_plan_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    binding_inputs = binding_harness.build_synthetic_c3_runtime_readiness_binding_inputs_v1(
        repository_root
    )
    binding_result = binding_contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(
        **binding_inputs
    )
    if binding_result.get("ok") is not True:
        raise AssertionError("upstream readiness-binding contract failed closed")

    source_pins = _verify_source_pins_read_only_v1(repository_root)
    operations = patch_contract.canonical_c3_preflight_p1_patch_operations_v1()
    matrix = patch_contract.canonical_c3_preflight_patch_acceptance_matrix_v1()
    plan = {
        "plan_version": "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_OFFLINE_V1",
        "upstream_binding_receipt_sha256": binding_result["binding_receipt"][
            "binding_receipt_sha256"
        ],
        "source_preconditions": source_pins,
        "source_preconditions_sha256": patch_contract._stable_sha256(source_pins),
        "operations": operations,
        "operations_sha256": patch_contract._stable_sha256(operations),
        "acceptance_matrix": matrix,
        "acceptance_matrix_sha256": patch_contract._stable_sha256(matrix),
        "safety_envelope": {
            "scope_attestation": "C3_READINESS_PREFLIGHT_P1_PATCH_PLANNING_OFFLINE_ONLY_V1",
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
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        },
    }
    plan["plan_sha256"] = patch_contract.c3_preflight_patch_plan_sha256_v1(plan)

    required_fields = list(binding_contract.canonical_c3_runtime_readiness_vector_v1())
    rehearsal = {
        "rehearsal_version": "C3_READINESS_PREFLIGHT_P1_PATCH_REHEARSAL_SYNTHETIC_V1",
        "patch_plan_sha256": plan["plan_sha256"],
        "source_preconditions_sha256": plan["source_preconditions_sha256"],
        "event_sequence": [
            "ATTEST_FIVE_SOURCE_HASHES",
            "VERIFY_UPSTREAM_READINESS_BINDING_RECEIPT",
            "CLASSIFY_TWO_CURRENT_P1_GAPS",
            "PROJECT_EXACT_RUNTIME_VECTOR_GATE",
            "PROJECT_STATIC_AST_SEMANTIC_PROOF",
            "VERIFY_NEGATIVE_ACCEPTANCE_MATRIX",
            "VERIFY_ROLLBACK_AND_SOURCE_PRESERVATION",
            "EMIT_NON_APPLICABLE_PATCH_PLAN_RECEIPT",
        ],
        "current_findings": [
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
        ],
        "projected_outcome": {
            "required_guard_fields": required_fields,
            "required_guard_count": 13,
            "all_fields_conjunctive": True,
            "decision_time_status_sample_required": True,
            "activation_receipt_sha256_required": True,
            "static_ast_semantic_proof_required": True,
            "negative_case_count": 18,
            "projected_blockers": [],
            "source_changed": False,
            "patch_applied": False,
            "runtime_executed": False,
            "activation_allowed": False,
            "live_allowed": False,
        },
        "source_bytes_preserved": True,
        "write_executed": False,
        "runtime_imported": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }
    rehearsal["rehearsal_sha256"] = (
        patch_contract.c3_preflight_patch_rehearsal_sha256_v1(rehearsal)
    )
    return {
        "readiness_binding_result": binding_result,
        "patch_plan": plan,
        "synthetic_rehearsal": rehearsal,
    }


def run_synthetic_c3_readiness_preflight_patch_plan_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_readiness_preflight_patch_plan_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    before_sha = patch_contract._stable_sha256(before)
    first = patch_contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(
        **inputs
    )
    second = patch_contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = patch_contract._stable_sha256(inputs)
    receipt = first.get("patch_plan_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("patch_plan_contract_verified") is True
        and first.get("upstream_readiness_binding_verified") is True
        and first.get("source_preconditions_verified") is True
        and first.get("two_p1_findings_covered") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_patch_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("activation_allowed") is False
        and first.get("live_allowed") is False
        and first.get("patch_payload_present") is False
        and first.get("replacement_text_present") is False
        and first.get("apply_entrypoint_present") is False
        and first.get("source_file_written") is False
        and first.get("write_executed") is False
        and first.get("runtime_imported") is False
        and first.get("runtime_integrated") is False
        and first.get("real_registry_accessed") is False
        and first.get("network_accessed") is False
        and first.get("broker_called") is False
        and first.get("no_order_sent") is True
        and isinstance(receipt, dict)
        and receipt.get("p1_finding_count") == 2
        and receipt.get("patch_operation_count") == 2
        and receipt.get("required_guard_count") == 13
        and receipt.get("acceptance_case_count") == 19
        and receipt.get("apply_allowed") is False
        and receipt.get("activation_allowed") is False
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_V1_HARNESS_PASSED_OFFLINE_NON_APPLICABLE"
            if ok
            else "C3_READINESS_PREFLIGHT_P1_PATCH_PLAN_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_HARNESS_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "declarative_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
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
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "patch_plan_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_PREFLIGHT_PATCH_PLAN_HARNESS_V1_VERSION",
    "build_synthetic_c3_readiness_preflight_patch_plan_inputs_v1",
    "run_synthetic_c3_readiness_preflight_patch_plan_harness_v1",
]
