"""AST-only checks for the main.py C3 writer boundaries, independent of synthetic rollout."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def anchors() -> list[dict]:
    # Read source as data; never import the runtime modules or start a worker.
    contents = {name: (ROOT / name).read_text(encoding="utf-8") for name in ("trade_registry.py", "main.py")}
    return harness._observe_source_anchors(contents)


def test_all_11_main_writers_have_exact_scoped_c3_then_local_lock(anchors: list[dict]) -> None:
    main = [item for item in anchors if item["component"] == "main.py"]
    assert len(main) == 11
    assert all(item["coordinator_scope_verified"] is True for item in main)
    assert all(item["local_lock_marker"] == "WITH_C3_BEFORE_LOCAL_LOCK" for item in main)
    assert all(item["all_placement_lines_within_function"] is True for item in main)


def test_all_19_source_markers_match_current_placements(anchors: list[dict]) -> None:
    result = harness.InMemoryDormantSourceAnchorRehearsal().rehearse(anchors)
    assert result["writer_count"] == 19
    assert result["runtime_executed"] is False
    for observed, wanted in zip(anchors, contract.canonical_runtime_writer_source_anchor_expectations_v1()):
        assert (observed["function_start_line"], observed["function_end_line"]) == (
            wanted["function_start_line"], wanted["function_end_line"]
        )


def test_coordinator_scope_drift_fails_closed(anchors: list[dict]) -> None:
    drifted = copy.deepcopy(anchors)
    next(item for item in drifted if item["component"] == "main.py")["coordinator_scope_verified"] = False
    with pytest.raises(harness.RuntimeWriterSourceAnchorHarnessBlocked, match="COORDINATOR_SCOPE_DRIFT_DENIED"):
        harness.InMemoryDormantSourceAnchorRehearsal().rehearse(drifted)
