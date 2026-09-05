from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def patch_inputs() -> dict:
    return harness.build_synthetic_c3_readiness_preflight_patch_plan_inputs_v1(ROOT)


def _reseal_plan(inputs: dict) -> None:
    plan = inputs["patch_plan"]
    plan["plan_sha256"] = contract.c3_preflight_patch_plan_sha256_v1(plan)


def _reseal_rehearsal(inputs: dict) -> None:
    rehearsal = inputs["synthetic_rehearsal"]
    rehearsal["rehearsal_sha256"] = (
        contract.c3_preflight_patch_rehearsal_sha256_v1(rehearsal)
    )


def test_valid_plan_is_complete_but_non_applicable(patch_inputs: dict) -> None:
    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(
        **copy.deepcopy(patch_inputs)
    )

    assert result["ok"] is True
    assert result["patch_plan_contract_verified"] is True
    assert result["upstream_readiness_binding_verified"] is True
    assert result["source_preconditions_verified"] is True
    assert result["two_p1_findings_covered"] is True
    assert result["synthetic_rehearsal_valid"] is True
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["patch_payload_present"] is False
    assert result["replacement_text_present"] is False
    assert result["apply_entrypoint_present"] is False
    assert result["source_file_written"] is False
    assert result["no_order_sent"] is True


def test_exact_two_p1_operations_cover_runtime_and_static_preflight() -> None:
    operations = contract.canonical_c3_preflight_p1_patch_operations_v1()

    assert len(operations) == 2
    assert {item["finding_priority"] for item in operations} == {"P1"}
    assert {item["target_path"] for item in operations} == {
        "main.py",
        "trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py",
    }
    assert all(len(item["required_guard_fields"]) == 13 for item in operations)
    assert all(item["declarative_only"] is True for item in operations)
    assert all(item["patch_payload_present"] is False for item in operations)
    assert all(item["replacement_text_present"] is False for item in operations)
    assert all(item["apply_allowed"] is False for item in operations)


def test_acceptance_matrix_covers_each_guard_and_semantic_bypasses() -> None:
    matrix = contract.canonical_c3_preflight_patch_acceptance_matrix_v1()
    case_ids = {item["case_id"] for item in matrix}

    assert len(matrix) == 19
    assert len(case_ids) == 19
    assert "LIVE_GATE_REJECTS_WEAKENED_ENABLED" in case_ids
    assert "LIVE_GATE_REJECTS_WEAKENED_RUNTIME_ACTIVATION_ALLOWED" in case_ids
    assert "LIVE_GATE_REJECTS_WEAKENED_REGISTERED_WRITER_COUNT" in case_ids
    assert "LIVE_GATE_REJECTS_GENERIC_OK_ONLY" in case_ids
    assert "STATIC_PREFLIGHT_REJECTS_LITERAL_ONLY" in case_ids
    assert "STATIC_PREFLIGHT_REJECTS_OR_COMPOSITION" in case_ids
    assert "STATIC_PREFLIGHT_REJECTS_CACHED_STATUS" in case_ids


def test_receipt_keeps_both_p1_gaps_and_production_blockers_explicit(
    patch_inputs: dict,
) -> None:
    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(
        **copy.deepcopy(patch_inputs)
    )
    receipt = result["patch_plan_receipt"]

    assert receipt["source_file_count"] == 5
    assert receipt["p1_finding_count"] == 2
    assert receipt["patch_operation_count"] == 2
    assert receipt["required_guard_count"] == 13
    assert receipt["acceptance_case_count"] == 19
    assert len(receipt["patch_plan_receipt_sha256"]) == 64
    assert receipt["patch_content_present"] is False
    assert receipt["replacement_text_present"] is False
    assert receipt["source_hashes_must_be_rechecked"] is True
    assert receipt["production_ready"] is False
    assert receipt["apply_allowed"] is False
    assert receipt["activation_allowed"] is False
    assert receipt["production_blockers"]


def test_harness_is_deterministic_read_only_and_non_applying() -> None:
    result = harness.run_synthetic_c3_readiness_preflight_patch_plan_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["deterministic"] is True
    assert result["offline_only"] is True
    assert result["apply_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["patch_payload_present"] is False
    assert result["replacement_text_present"] is False
    assert result["source_file_written"] is False
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


@pytest.mark.parametrize(
    "operation_index",
    [0, 1],
)
def test_removing_any_required_guard_from_an_operation_fails_closed(
    patch_inputs: dict, operation_index: int
) -> None:
    inputs = copy.deepcopy(patch_inputs)
    operations = inputs["patch_plan"]["operations"]
    operations[operation_index]["required_guard_fields"].pop()
    inputs["patch_plan"]["operations_sha256"] = contract._stable_sha256(operations)
    _reseal_plan(inputs)

    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert result["ok"] is False
    assert "PREFLIGHT_PATCH_PLAN_OPERATIONS_INVALID" in result["reasons"]
    assert result["apply_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("patch_payload_present", True),
        ("replacement_text_present", True),
        ("apply_allowed", True),
    ],
)
def test_any_applicable_operation_claim_fails_closed(
    patch_inputs: dict, field: str, value: object
) -> None:
    inputs = copy.deepcopy(patch_inputs)
    operations = inputs["patch_plan"]["operations"]
    operations[0][field] = value
    inputs["patch_plan"]["operations_sha256"] = contract._stable_sha256(operations)
    _reseal_plan(inputs)

    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert result["ok"] is False
    assert "PREFLIGHT_PATCH_PLAN_OPERATIONS_INVALID" in result["reasons"]
    assert result["runtime_patch_allowed"] is False


def test_source_hash_drift_fails_closed_even_when_resealed(patch_inputs: dict) -> None:
    inputs = copy.deepcopy(patch_inputs)
    pins = inputs["patch_plan"]["source_preconditions"]
    pins[0]["sha256"] = "f" * 64
    inputs["patch_plan"]["source_preconditions_sha256"] = contract._stable_sha256(pins)
    _reseal_plan(inputs)

    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert result["ok"] is False
    assert "PREFLIGHT_PATCH_PLAN_SOURCE_PRECONDITIONS_INVALID" in result["reasons"]
    assert result["source_preconditions_verified"] is False


def test_tampered_upstream_binding_receipt_fails_closed(patch_inputs: dict) -> None:
    inputs = copy.deepcopy(patch_inputs)
    inputs["readiness_binding_result"]["binding_receipt"]["required_guard_count"] = 12

    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert result["ok"] is False
    assert "PREFLIGHT_PATCH_PLAN_UPSTREAM_BINDING_INVALID" in result["reasons"]
    assert result["patch_plan_receipt"] is None


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("projected_outcome", "required_guard_count"), 12, "PREFLIGHT_PATCH_REHEARSAL_PROJECTED_OUTCOME_INVALID"),
        (("projected_outcome", "all_fields_conjunctive"), False, "PREFLIGHT_PATCH_REHEARSAL_PROJECTED_OUTCOME_INVALID"),
        (("projected_outcome", "static_ast_semantic_proof_required"), False, "PREFLIGHT_PATCH_REHEARSAL_PROJECTED_OUTCOME_INVALID"),
        (("source_bytes_preserved",), False, "PREFLIGHT_PATCH_REHEARSAL_SAFETY_INVALID"),
        (("write_executed",), True, "PREFLIGHT_PATCH_REHEARSAL_SAFETY_INVALID"),
    ],
)
def test_weakened_rehearsal_fails_closed(
    patch_inputs: dict, path: tuple[str, ...], value: object, reason: str
) -> None:
    inputs = copy.deepcopy(patch_inputs)
    target = inputs["synthetic_rehearsal"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _reseal_rehearsal(inputs)

    result = contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert result["ok"] is False
    assert reason in result["reasons"]
    assert result["activation_allowed"] is False


def test_validation_preserves_inputs(patch_inputs: dict) -> None:
    inputs = copy.deepcopy(patch_inputs)
    before = copy.deepcopy(inputs)

    contract.evaluate_c3_readiness_preflight_p1_patch_plan_offline_v1(**inputs)

    assert inputs == before


def test_modules_expose_no_patch_apply_runtime_or_external_surface() -> None:
    modules = (contract, harness)
    imported_modules = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported_modules
    assert "trade_registry" not in imported_modules
    assert "broker" not in imported_modules
    source = "\n".join(inspect.getsource(module) for module in modules)
    for token in (
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "importlib",
        "os.environ",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(contract, "apply")
    assert not hasattr(contract, "activate")
    assert not hasattr(harness, "apply")
    assert not hasattr(harness, "activate")
