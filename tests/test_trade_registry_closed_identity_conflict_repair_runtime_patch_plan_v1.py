from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_contract_v1 as projection
import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan_inputs() -> dict:
    return harness.build_closed_repair_runtime_patch_plan_inputs_read_only_v1(ROOT)


def _reseal_source_evidence(inputs: dict) -> None:
    evidence = inputs["source_precondition_evidence"]
    evidence["source_set_sha256"] = (
        patch_plan.runtime_patch_source_preconditions_sha256_v1(evidence)
    )


def _reseal_plan(inputs: dict) -> None:
    plan = inputs["runtime_patch_plan"]
    plan["plan_sha256"] = patch_plan.runtime_patch_plan_sha256_v1(plan)
    rehearsal = inputs["runtime_patch_rehearsal"]
    rehearsal["patch_plan_sha256"] = plan["plan_sha256"]
    rehearsal["rehearsal_sha256"] = patch_plan.runtime_patch_rehearsal_sha256_v1(
        rehearsal
    )


def test_hash_bound_plan_is_valid_but_non_applicable(plan_inputs: dict) -> None:
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **copy.deepcopy(plan_inputs)
    )
    assert result["ok"] is True
    assert result["patch_plan_contract_verified"] is True
    assert result["source_preconditions_verified"] is True
    assert result["synthetic_rehearsal_valid"] is True
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["live_allowed"] is False
    assert result["patch_content_present"] is False
    assert result["source_file_written"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_source_preconditions_bind_exact_nine_files_without_content(
    plan_inputs: dict,
) -> None:
    evidence = plan_inputs["source_precondition_evidence"]
    files = evidence["files"]
    assert [item["relative_path"] for item in files] == (
        patch_plan.canonical_runtime_patch_source_files_v1()
    )
    assert len(files) == 9
    assert [item["relative_path"] for item in files if item["role"] == "MUTATE_DECLARATIVELY"] == [
        "trade_registry.py",
        "main.py",
    ]
    assert len([item for item in files if item["role"] == "VERIFY_UNCHANGED"]) == 7
    assert all(set(item) == {"relative_path", "sha256", "size_bytes", "role"} for item in files)
    assert all(len(item["sha256"]) == 64 and item["size_bytes"] > 0 for item in files)
    assert evidence["read_only_collection"] is True
    assert evidence["secret_files_excluded"] is True


def test_current_real_sources_are_bound_to_the_installed_dormant_seams(
    plan_inputs: dict,
) -> None:
    current = plan_inputs["source_precondition_evidence"]["current_static_preflight"]
    assert current["blockers"] == []
    assert current["evaluation_complete"] is True
    assert current["static_readiness"] is True
    assert current["production_ready"] is False
    assert current["live_allowed"] is False
    assert current["runtime_executed"] is False
    assert current["writer_summary"]["discovered_count"] == 19
    assert current["writer_summary"]["coordinated_count"] == 19


def test_only_main_and_trade_registry_have_declarative_operations(
    plan_inputs: dict,
) -> None:
    plan = plan_inputs["runtime_patch_plan"]
    assert set(plan["operations_by_file"]) == {"trade_registry.py", "main.py"}
    assert plan["mutated_files"] == ["trade_registry.py", "main.py"]
    assert len(plan["verified_only_files"]) == 7
    operations = [
        item
        for values in plan["operations_by_file"].values()
        for item in values
    ]
    writer_operations = [item for item in operations if item["writer_id"]]
    assert len(writer_operations) == 19
    assert len({item["writer_id"] for item in writer_operations}) == 19
    assert all(item["declarative_only"] is True for item in operations)
    assert all(item["patch_payload_present"] is False for item in operations)
    assert all(item["replacement_text_present"] is False for item in operations)
    assert all(item["apply_allowed"] is False for item in operations)


def test_each_blocker_is_covered_by_existing_operation_ids(
    plan_inputs: dict,
) -> None:
    plan = plan_inputs["runtime_patch_plan"]
    coverage = plan["blocker_coverage"]
    operation_ids = {
        item["operation_id"]
        for values in plan["operations_by_file"].values()
        for item in values
    }
    assert [item["blocker_code"] for item in coverage] == (
        projection.canonical_resolved_runtime_preflight_blockers_v1()
    )
    assert all(
        set(item["required_operation_ids"]).issubset(operation_ids)
        for item in coverage
    )


def test_per_file_plan_preconditions_equal_read_only_attestations(
    plan_inputs: dict,
) -> None:
    assert plan_inputs["runtime_patch_plan"]["file_preconditions"] == (
        plan_inputs["source_precondition_evidence"]["files"]
    )


def test_rollback_denies_drift_payload_apply_and_preserves_sources(
    plan_inputs: dict,
) -> None:
    steps = [
        item["step"]
        for item in plan_inputs["runtime_patch_plan"]["rollback_protocol"]
    ]
    assert steps == [
        "REJECT_ON_ANY_SOURCE_HASH_DRIFT",
        "REJECT_ON_ANY_MISSING_OPERATION",
        "REJECT_ON_UNKNOWN_OPERATION",
        "REJECT_ON_PATCH_PAYLOAD_PRESENCE",
        "REJECT_ON_APPLY_REQUEST",
        "PRESERVE_ALL_SOURCE_BYTES",
        "PRESERVE_RUNTIME_STATE",
        "PRESERVE_LIVE_DENIAL",
    ]
    rehearsal = plan_inputs["runtime_patch_rehearsal"]
    assert rehearsal["source_bytes_preserved"] is True
    assert rehearsal["source_file_written"] is False
    assert rehearsal["runtime_executed"] is False
    assert rehearsal["live_allowed"] is False


def test_harness_is_deterministic_read_only_and_preserves_inputs() -> None:
    result = harness.run_closed_repair_runtime_patch_plan_harness_read_only_v1(ROOT)
    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["deterministic"] is True
    assert result["read_only"] is True
    assert result["declarative_only"] is True
    assert result["patch_content_present"] is False
    assert result["source_file_written"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["live_allowed"] is False


def test_resealed_source_hash_drift_breaks_per_file_binding(
    plan_inputs: dict,
) -> None:
    inputs = copy.deepcopy(plan_inputs)
    inputs["source_precondition_evidence"]["files"][0]["sha256"] = "f" * 64
    _reseal_source_evidence(inputs)
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    assert result["ok"] is False
    assert result["apply_allowed"] is False
    assert "RUNTIME_PATCH_PER_FILE_HASH_PRECONDITIONS_INVALID" in result["reasons"]


def test_resealed_missing_writer_operation_fails_closed(
    plan_inputs: dict,
) -> None:
    inputs = copy.deepcopy(plan_inputs)
    inputs["runtime_patch_plan"]["operations_by_file"]["trade_registry.py"].pop()
    _reseal_plan(inputs)
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    assert result["ok"] is False
    assert result["runtime_install_allowed"] is False
    assert "RUNTIME_PATCH_OPERATIONS_INVALID" in result["reasons"]


def test_resealed_patch_payload_claim_fails_closed(
    plan_inputs: dict,
) -> None:
    inputs = copy.deepcopy(plan_inputs)
    operation = inputs["runtime_patch_plan"]["operations_by_file"]["main.py"][0]
    operation["patch_payload_present"] = True
    _reseal_plan(inputs)
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    assert result["ok"] is False
    assert result["patch_content_present"] is False
    assert result["apply_allowed"] is False
    assert "RUNTIME_PATCH_OPERATIONS_INVALID" in result["reasons"]


def test_resealed_current_preflight_change_invalidates_plan(
    plan_inputs: dict,
) -> None:
    inputs = copy.deepcopy(plan_inputs)
    inputs["source_precondition_evidence"]["current_static_preflight"][
        "blockers"
    ].append("UNATTESTED_BLOCKER")
    _reseal_source_evidence(inputs)
    inputs["runtime_patch_plan"]["source_preconditions_sha256"] = inputs[
        "source_precondition_evidence"
    ]["source_set_sha256"]
    _reseal_plan(inputs)
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    assert result["ok"] is False
    assert "RUNTIME_PATCH_CURRENT_PREFLIGHT_INVALID" in result["reasons"]


def test_tampered_projection_receipt_breaks_chain(plan_inputs: dict) -> None:
    inputs = copy.deepcopy(plan_inputs)
    inputs["projection_result"]["projection_receipt"]["resolved_blocker_count"] = 8
    result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    assert result["ok"] is False
    assert result["patch_plan_receipt"] is None
    assert "RUNTIME_PATCH_PLAN_UPSTREAM_PROJECTION_INVALID" in result["reasons"]


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"source_hashes_match": False}, "SOURCE_HASH_DRIFT_DENIED"),
        ({"patch_payload_provided": True}, "PATCH_PAYLOAD_DENIED"),
        ({"replacement_text_provided": True}, "REPLACEMENT_TEXT_DENIED"),
        ({"apply_requested": True}, "APPLY_REQUEST_DENIED"),
        ({"executable_object_provided": True}, "EXECUTABLE_OBJECT_DENIED"),
    ],
)
def test_planner_negative_controls_fail_before_any_event(
    plan_inputs: dict, override: dict, reason: str
) -> None:
    planner = harness.InMemoryDormantRuntimePatchPlanner(
        plan_inputs["source_precondition_evidence"]["files"]
    )
    with pytest.raises(harness.RuntimePatchPlanHarnessBlocked) as raised:
        planner.rehearse(
            operations_by_file=patch_plan.canonical_runtime_patch_operations_v1(),
            **override,
        )
    assert raised.value.reason == reason
    assert planner.events == ()


def test_modules_have_no_patch_writer_runtime_or_external_surface() -> None:
    modules = (patch_plan, harness)
    imported_modules = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported_modules
    assert "trade_registry" not in imported_modules
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
    ):
        assert token not in source
    assert not hasattr(patch_plan, "apply")
    assert not hasattr(harness.InMemoryDormantRuntimePatchPlanner, "apply")


def test_validation_does_not_mutate_inputs(plan_inputs: dict) -> None:
    inputs = copy.deepcopy(plan_inputs)
    before = copy.deepcopy(inputs)
    patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(**inputs)
    assert inputs == before
