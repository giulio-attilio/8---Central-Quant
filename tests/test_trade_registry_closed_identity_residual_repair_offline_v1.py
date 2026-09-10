from __future__ import annotations

import ast
import copy
from pathlib import Path

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as contract
import trade_registry_closed_identity_residual_repair_offline_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


def _plan(snapshot=None):
    snapshot = snapshot or harness.build_synthetic_residual_matrix_v1()
    return contract.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256=contract.stable_sha256_v1(snapshot),
    )


def test_synthetic_matrix_matches_the_read_only_residual_audit():
    result = harness.run_residual_repair_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())
    assert result["plan"]["status"] == "OFFLINE_RESIDUAL_REPAIR_PLAN_PARTIAL_QUARANTINE"


def test_plan_is_deterministic_and_does_not_mutate_the_injected_snapshot():
    snapshot = harness.build_synthetic_residual_matrix_v1()
    original = copy.deepcopy(snapshot)

    first = _plan(snapshot)
    second = _plan(snapshot)

    assert snapshot == original
    assert first == second
    assert first["plan_sha256"] == second["plan_sha256"]
    assert first["source_snapshot_sha256"] == contract.stable_sha256_v1(original)


def test_safe_aliases_are_archived_exactly_while_canonical_values_are_preserved():
    snapshot = harness.build_synthetic_residual_matrix_v1()
    result = _plan(snapshot)
    candidate = result["candidate_registry"]

    assert result["summary"] == {
        "residual_record_count": 43,
        "timestamp_aliases_archived": 11,
        "status_aliases_archived": 31,
        "quarantined_conflict_count": 32,
        "quarantined_record_count": 32,
        "modified_record_count": 41,
    }
    for action in result["actions"]:
        index = action["registry_index"]
        before = snapshot["closed_trades"][index]
        after = candidate["closed_trades"][index]
        assert after["opened_at"] == before["opened_at"]
        assert after["status"] == "CLOSED"
        field = "created_at" if action["field"] == "opened_at" else "status"
        archived = after["metadata"]["c3_residual_identity_evidence_v1"]["fields"][field]
        assert archived["source_value"] == before["metadata"][field]
        assert archived["source_value_sha256"] == contract.stable_sha256_v1(
            before["metadata"][field]
        )


def test_historical_timestamp_divergence_stays_unchanged_and_quarantined():
    snapshot = harness.build_synthetic_residual_matrix_v1()
    result = _plan(snapshot)
    candidate = result["candidate_registry"]
    quarantined = {
        item["registry_index"]: item for item in result["quarantine"]
    }

    assert len(quarantined) == 32
    for index in quarantined:
        assert candidate["closed_trades"][index]["opened_at"] == snapshot["closed_trades"][index]["opened_at"]
        assert candidate["closed_trades"][index]["metadata"]["created_at"] == snapshot["closed_trades"][index]["metadata"]["created_at"]


def test_financial_and_unrelated_values_are_preserved_byte_for_byte_semantically():
    snapshot = harness.build_synthetic_residual_matrix_v1()
    snapshot["closed_trades"][0].update(
        {
            "close_reason": "STOP",
            "pnl_r": -1.26907189,
            "gross_r_multiple": -1.08850668,
        }
    )
    snapshot["closed_trades"][0]["metadata"]["outcome"] = {
        "close_reason": "STOP",
        "r_multiple": -1.26907189,
        "gross_r_multiple": -1.08850668,
    }

    result = _plan(snapshot)
    before = snapshot["closed_trades"][0]
    after = result["candidate_registry"]["closed_trades"][0]

    for field in ("close_reason", "pnl_r", "gross_r_multiple"):
        assert after[field] == before[field]
    assert after["metadata"]["outcome"] == before["metadata"]["outcome"]
    assert result["candidate_registry"]["open_trades"] == snapshot["open_trades"]


def test_digest_mismatch_malformed_shape_and_archive_collision_fail_closed():
    snapshot = harness.build_synthetic_residual_matrix_v1()
    mismatch = contract.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256="0" * 64,
    )
    assert mismatch["ok"] is False
    assert mismatch["reasons"] == ["SOURCE_SNAPSHOT_SHA256_MISMATCH"]
    assert mismatch["candidate_registry"] is None

    malformed = copy.deepcopy(snapshot)
    malformed["closed_trades"][0] = "invalid"
    malformed_result = _plan(malformed)
    assert malformed_result["ok"] is False
    assert malformed_result["reasons"] == ["CLOSED_TRADES_INVALID_RECORD"]

    collision = copy.deepcopy(snapshot)
    collision["closed_trades"][0]["metadata"]["c3_residual_identity_evidence_v1"] = {}
    collision_result = _plan(collision)
    assert collision_result["ok"] is False
    assert collision_result["reasons"] == ["PREEXISTING_RESIDUAL_EVIDENCE_ARCHIVE"]

    invalid_metadata = copy.deepcopy(snapshot)
    invalid_metadata["closed_trades"][0]["metadata"] = "invalid"
    invalid_metadata_result = _plan(invalid_metadata)
    assert invalid_metadata_result["ok"] is False
    assert invalid_metadata_result["reasons"] == ["CLOSED_TRADE_METADATA_INVALID"]

    invalid_caps = contract.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256=contract.stable_sha256_v1(snapshot),
        caps=contract.ResidualClosedIdentityRepairCapsV1(
            max_residual_records=0
        ),
    )
    assert invalid_caps["ok"] is False
    assert invalid_caps["reasons"] == ["INVALID_REPAIR_CAPS"]

    for blocked in (
        mismatch,
        malformed_result,
        collision_result,
        invalid_metadata_result,
        invalid_caps,
    ):
        assert blocked["apply_allowed"] is False
        assert blocked["runtime_activation_allowed"] is False
        assert blocked["write_executed"] is False
        assert blocked["broker_called"] is False


def test_default_cap_accepts_43_and_hard_cap_rejects_65_residual_records():
    snapshot = harness.build_synthetic_residual_matrix_v1()

    accepted = _plan(snapshot)
    assert len(snapshot["closed_trades"]) == 43
    assert accepted["ok"] is True
    assert accepted["summary"]["residual_record_count"] == 43

    overflow = copy.deepcopy(snapshot)
    template = snapshot["closed_trades"][-1]
    for number in range(44, 66):
        record = copy.deepcopy(template)
        record["trade_id"] = f"SYNTHETIC:FALCON:{number:02d}"
        record["symbol"] = f"SYN{number:02d}USDT"
        overflow["closed_trades"].append(record)

    blocked = _plan(overflow)
    assert len(overflow["closed_trades"]) == 65
    assert blocked["ok"] is False
    assert blocked["reasons"] == ["RESIDUAL_RECORD_CAP_EXCEEDED"]
    assert blocked["candidate_registry"] is None
    assert blocked["apply_allowed"] is False
    assert blocked["runtime_activation_allowed"] is False
    assert blocked["write_executed"] is False
    assert blocked["broker_called"] is False

    invalid_override = contract.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256=contract.stable_sha256_v1(snapshot),
        caps=contract.ResidualClosedIdentityRepairCapsV1(
            max_residual_records=65
        ),
    )
    assert invalid_override["ok"] is False
    assert invalid_override["reasons"] == ["INVALID_REPAIR_CAPS"]


def test_contract_has_no_runtime_network_or_filesystem_integration():
    path = ROOT / "trade_registry_closed_identity_residual_repair_offline_contract_v1.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported.isdisjoint(
        {"os", "pathlib", "requests", "httpx", "urllib", "socket", "trade_registry", "main"}
    )
    assert calls.isdisjoint(
        {"open", "write_text", "write_bytes", "remove", "unlink", "urlopen", "request"}
    )
