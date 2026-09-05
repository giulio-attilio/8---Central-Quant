from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def anchor_inputs() -> dict:
    return harness.build_closed_repair_runtime_writer_source_anchor_inputs_read_only_v1(ROOT)


def _reseal_evidence(inputs: dict) -> None:
    evidence = inputs["source_anchor_evidence"]
    evidence["evidence_sha256"] = contract.runtime_writer_source_anchor_evidence_sha256_v1(evidence)
    rehearsal = inputs["source_anchor_rehearsal"]
    rehearsal["evidence_sha256"] = evidence["evidence_sha256"]
    rehearsal["rehearsal_sha256"] = contract.runtime_writer_source_anchor_rehearsal_sha256_v1(rehearsal)


def test_real_source_anchors_validate_offline_but_cannot_install(anchor_inputs: dict) -> None:
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**copy.deepcopy(anchor_inputs))
    assert result["ok"] is True
    assert result["source_anchor_contract_verified"] is True
    assert result["source_anchors_verified"] is True
    assert result["synthetic_rehearsal_valid"] is True
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["live_allowed"] is False
    assert result["source_file_written"] is False
    assert result["no_order_sent"] is True


def test_exact_19_function_spans_are_bound_in_inventory_order(anchor_inputs: dict) -> None:
    expected = contract.canonical_runtime_writer_source_anchor_expectations_v1()
    observed = anchor_inputs["source_anchor_evidence"]["observed_anchors"]
    assert len(expected) == len(observed) == 19
    assert [item["writer_id"] for item in observed] == [item["writer_id"] for item in expected]
    assert [
        (item["function_start_line"], item["function_end_line"])
        for item in observed
    ] == [
        (item["function_start_line"], item["function_end_line"])
        for item in expected
    ]
    assert all(item["all_placement_lines_within_function"] is True for item in observed)


def test_source_hashes_chain_to_the_upstream_patch_plan(anchor_inputs: dict) -> None:
    receipt = anchor_inputs["transaction_placement_result"]["transaction_placement_receipt"]
    evidence = anchor_inputs["source_anchor_evidence"]["source_precondition_evidence"]
    assert evidence["source_set_sha256"] == receipt["source_preconditions_sha256"]
    assert [item["relative_path"] for item in evidence["files"]][:2] == ["trade_registry.py", "main.py"]
    assert len(evidence["files"]) == 9
    assert evidence["read_only_collection"] is True
    assert evidence["secret_files_excluded"] is True


def test_fresh_read_and_insertion_seam_markers_are_exact(anchor_inputs: dict) -> None:
    observed = anchor_inputs["source_anchor_evidence"]["observed_anchors"]
    by_id = {item["writer_id"]: item for item in observed}
    assert by_id["TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE"]["fresh_marker"] == "REGISTRY_STORAGE_STATE_GUARD"
    assert by_id["MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT"]["fresh_marker"] == "REGISTRY_SNAPSHOT_READ_CALL"
    assert by_id["MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"]["fresh_marker"] == "RAW_REGISTRY_READ_CALL"
    assert by_id["TRADE_REGISTRY_RESET"]["fresh_marker"] is None
    assert by_id["MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE"]["fresh_marker"] == "TRY_INSERTION_SEAM"
    assert by_id["MAIN_REGISTRY_MODE_SEGREGATION_COMMIT"]["fresh_marker"] == "LOOP_INSERTION_SEAM"
    assert by_id["MAIN_PREDATOR_PAPER_REGISTRY_SYNC"]["fresh_marker"] == "TRY_INSERTION_SEAM"
    assert by_id["MAIN_PREDATOR_ORPHAN_OPEN_FIX"]["fresh_marker"] == "TRY_INSERTION_SEAM"


def test_all_authoritative_writes_still_have_expected_markers(anchor_inputs: dict) -> None:
    observed = anchor_inputs["source_anchor_evidence"]["observed_anchors"]
    bootstrap = next(item for item in observed if item["writer_id"] == "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP")
    assert bootstrap["write_markers"] == [
        "ATOMIC_JSON_WRITE_CALL",
        "ATOMIC_JSON_WRITE_CALL",
        "ATOMIC_JSON_WRITE_CALL",
        "EVENT_APPEND_WRITE_CALL",
    ]
    load = next(item for item in observed if item["writer_id"] == "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE")
    assert load["write_markers"] == ["REGISTRY_SAVE_CALL", "REGISTRY_SAVE_CALL"]
    assert all(
        item["write_markers"] == ["REGISTRY_SAVE_CALL"]
        for item in observed
        if item["writer_id"] not in {
            "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP",
            "TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE",
        }
    )


def test_existing_process_local_lock_markers_are_exact(anchor_inputs: dict) -> None:
    observed = anchor_inputs["source_anchor_evidence"]["observed_anchors"]
    locks = {item["writer_id"]: item["local_lock_marker"] for item in observed if item["local_lock_marker"] is not None}
    assert len(locks) == 10
    assert list(locks.values()).count("WITH_MODULE_RLOCK") == 7
    assert locks["MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT"] == "WITH_LOCAL_LOCK"
    assert locks["MAIN_PREDATOR_AUTO_CLOSED_SYNC"] == "LOCAL_LOCK_ACQUIRE"
    assert locks["MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"] == "WITH_LOCAL_LOCK"
    assert "TRADE_REGISTRY_RESET" not in locks


def test_commit_guards_are_observed_without_source_content(anchor_inputs: dict) -> None:
    observed = anchor_inputs["source_anchor_evidence"]["observed_anchors"]
    expected = contract.canonical_runtime_writer_source_anchor_expectations_v1()
    assert all(
        item["commit_guard_marker"] == wanted["expected_commit_guard_marker"]
        for item, wanted in zip(observed, expected)
    )
    assert all(item["source_content_exposed"] is False for item in observed)
    assert "source" not in observed[0]
    assert "line_text" not in observed[0]


def test_harness_is_read_only_and_preserves_inputs() -> None:
    result = harness.run_closed_repair_runtime_writer_source_anchor_harness_read_only_v1(ROOT)
    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["read_only"] is True
    assert result["source_content_exposed"] is False
    assert result["source_file_written"] is False
    assert result["runtime_imported"] is False
    assert result["runtime_executed"] is False
    assert result["registry_read"] is False
    assert result["registry_write"] is False
    assert result["runtime_install_allowed"] is False
    assert result["live_allowed"] is False


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"function_line_shift": True}, "FUNCTION_LINE_SHIFT_DENIED"),
        ({"writer_missing": True}, "WRITER_MISSING_DENIED"),
        ({"write_marker_drift": True}, "WRITE_MARKER_DRIFT_DENIED"),
        ({"lock_marker_drift": True}, "LOCK_MARKER_DRIFT_DENIED"),
        ({"fresh_read_anchor_drift": True}, "FRESH_READ_ANCHOR_DRIFT_DENIED"),
        ({"source_hash_mismatch": True}, "SOURCE_HASH_MISMATCH_DENIED"),
        ({"runtime_import_requested": True}, "RUNTIME_IMPORT_REQUEST_DENIED"),
    ],
)
def test_rehearsal_negative_controls_fail_closed(anchor_inputs: dict, kwargs: dict, reason: str) -> None:
    runner = harness.InMemoryDormantSourceAnchorRehearsal()
    with pytest.raises(harness.RuntimeWriterSourceAnchorHarnessBlocked, match=reason):
        runner.rehearse(anchor_inputs["source_anchor_evidence"]["observed_anchors"], **kwargs)


def test_resealed_function_line_shift_fails_closed(anchor_inputs: dict) -> None:
    inputs = copy.deepcopy(anchor_inputs)
    inputs["source_anchor_evidence"]["observed_anchors"][0]["function_start_line"] += 1
    _reseal_evidence(inputs)
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**inputs)
    assert result["ok"] is False
    assert "SOURCE_ANCHOR_OBSERVATIONS_INVALID" in result["reasons"]


def test_resealed_write_marker_drift_fails_closed(anchor_inputs: dict) -> None:
    inputs = copy.deepcopy(anchor_inputs)
    inputs["source_anchor_evidence"]["observed_anchors"][0]["write_markers"] = ["OTHER"]
    _reseal_evidence(inputs)
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**inputs)
    assert result["ok"] is False
    assert result["apply_allowed"] is False
    assert "SOURCE_ANCHOR_OBSERVATIONS_INVALID" in result["reasons"]


def test_resealed_source_hash_mismatch_fails_closed(anchor_inputs: dict) -> None:
    inputs = copy.deepcopy(anchor_inputs)
    nested = inputs["source_anchor_evidence"]["source_precondition_evidence"]
    nested["files"][0]["sha256"] = "f" * 64
    import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan

    nested["source_set_sha256"] = patch_plan.runtime_patch_source_preconditions_sha256_v1(nested)
    _reseal_evidence(inputs)
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**inputs)
    assert result["ok"] is False
    assert "SOURCE_ANCHOR_SOURCE_HASH_CHAIN_INVALID" in result["reasons"]


def test_tampered_upstream_placement_receipt_fails_closed(anchor_inputs: dict) -> None:
    inputs = copy.deepcopy(anchor_inputs)
    inputs["transaction_placement_result"]["transaction_placement_receipt"]["writer_count"] = 18
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**inputs)
    assert result["ok"] is False
    assert "SOURCE_ANCHOR_UPSTREAM_PLACEMENT_INVALID" in result["reasons"]


def test_contract_and_harness_never_import_runtime_or_expose_apply() -> None:
    for module in (contract, harness):
        tree = ast.parse(inspect.getsource(module))
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(name=node.module or "")])
        }
        functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert "main" not in imports
        assert "trade_registry" not in imports
        assert not any("apply" in name.lower() for name in functions)
