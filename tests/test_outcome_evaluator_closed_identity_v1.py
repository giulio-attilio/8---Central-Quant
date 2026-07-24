from __future__ import annotations

import importlib
import json
import sys

import pytest


@pytest.fixture()
def evaluator(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "registry-unused.json"))
    monkeypatch.setenv("CENTRAL_OUTCOME_EVALUATOR_ENABLED", "true")
    sys.modules.pop("outcome_evaluator", None)
    module = importlib.import_module("outcome_evaluator")
    yield module
    sys.modules.pop("outcome_evaluator", None)


def _closed(
    *,
    trade_id="PREDATOR:SMART:XRPUSDT:LONG",
    lifecycle_id=None,
    client_order_id=None,
    order_id=None,
    closed_at="23/07/2026 10:00:00",
    pnl_pct=1.0,
):
    trade = {
        "trade_id": trade_id,
        "status": "CLOSED",
        "bot": "PREDATOR",
        "setup": "SMART_PREDATOR",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "entry": 1.0,
        "exit_price": 1.0 + pnl_pct / 100,
        "pnl_pct": pnl_pct,
        "r_result": pnl_pct,
        "closed_at": closed_at,
        "qty": 10,
    }
    if lifecycle_id is not None:
        trade["lifecycle_id"] = lifecycle_id
    if client_order_id is not None:
        trade["client_order_id"] = client_order_id
    if order_id is not None:
        trade["broker_order_id"] = order_id
    return trade


def _empty_stats(module, evaluated_trade_ids=None):
    return {
        "version": module.VERSION,
        "updated_at": None,
        "global": module._empty_bucket(),
        "by_bot": {},
        "by_setup": {},
        "by_symbol": {},
        "by_side": {},
        "evaluated_trade_ids": list(evaluated_trade_ids or []),
        "evaluated_closed_execution_keys": [],
        "evaluated_closed_executions": [],
    }


def _write_positions(module, positions):
    module.PAPER_POSITIONS_FILE.write_text(
        json.dumps(positions), encoding="utf-8"
    )


def test_same_trade_id_distinct_lifecycles_are_evaluated_independently(
    evaluator,
):
    _write_positions(
        evaluator,
        [
            _closed(
                lifecycle_id="LC-ONE",
                client_order_id="CLIENT-ONE",
                order_id="ORDER-ONE",
                closed_at="23/07/2026 10:00:00",
                pnl_pct=1.0,
            ),
            _closed(
                lifecycle_id="LC-TWO",
                client_order_id="CLIENT-TWO",
                order_id="ORDER-TWO",
                closed_at="23/07/2026 11:00:00",
                pnl_pct=2.0,
            ),
        ],
    )

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 2
    assert result["stats"]["global"]["trades"] == 2
    assert result["stats"]["global"]["pnl_total_pct"] == 3.0
    assert len(result["stats"]["evaluated_trade_ids"]) == 1
    assert len(result["stats"]["evaluated_closed_execution_keys"]) == 2
    assert len(result["stats"]["evaluated_closed_executions"]) == 2


def test_same_execution_retry_by_client_and_order_is_idempotent(evaluator):
    first = _closed(
        lifecycle_id="LC-SAME",
        client_order_id="CLIENT-SAME",
        order_id="ORDER-SAME",
        pnl_pct=1.25,
    )
    _write_positions(evaluator, [first])
    first_result = evaluator.evaluate_closed_paper_trades()
    assert first_result["evaluated_count"] == 1

    # Simulate a rebuilt PAPER row that lost lifecycle but retained the factual
    # client+exchange order identity. It must match the prior execution marker.
    retry = _closed(
        client_order_id="client-same",
        order_id="ORDER-SAME",
        pnl_pct=1.25,
    )
    _write_positions(evaluator, [retry])

    retry_result = evaluator.evaluate_closed_paper_trades()

    assert retry_result["evaluated_count"] == 0
    assert retry_result["skipped_count"] == 1
    assert retry_result["skipped"][0]["identity_reason"] == (
        "CLOSED_EXECUTION_ALREADY_EVALUATED"
    )
    assert retry_result["stats"]["global"]["trades"] == 1
    assert len(retry_result["stats"]["evaluated_closed_executions"]) == 1


def test_legacy_marker_remains_readable_without_hiding_strong_execution(
    evaluator,
):
    shared_trade_id = "PREDATOR:SMART:XRPUSDT:LONG"
    legacy_stats = _empty_stats(
        evaluator, evaluated_trade_ids=[shared_trade_id]
    )
    legacy_stats["global"]["trades"] = 1
    evaluator.OUTCOME_STATS_FILE.write_text(
        json.dumps(legacy_stats), encoding="utf-8"
    )
    legacy = _closed(trade_id=shared_trade_id)
    strong = _closed(
        trade_id=shared_trade_id,
        lifecycle_id="LC-NEW",
        client_order_id="CLIENT-NEW",
        order_id="ORDER-NEW",
        closed_at="23/07/2026 12:00:00",
        pnl_pct=2.0,
    )
    _write_positions(evaluator, [legacy, strong])

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 1
    assert result["evaluated"][0]["closed_execution_key"].startswith(
        "lifecycle|LC-NEW"
    )
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["identity_reason"] == (
        "LEGACY_TRADE_ID_MARKER_MATCH"
    )
    assert result["stats"]["global"]["trades"] == 2
    assert len(result["stats"]["evaluated_closed_executions"]) == 1


def test_new_legacy_executions_with_same_trade_id_do_not_collapse(evaluator):
    _write_positions(
        evaluator,
        [
            _closed(
                closed_at="23/07/2026 10:00:00",
                pnl_pct=1.0,
            ),
            _closed(
                closed_at="23/07/2026 11:00:00",
                pnl_pct=2.0,
            ),
        ],
    )

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 2
    assert result["stats"]["global"]["trades"] == 2
    assert len(result["stats"]["evaluated_trade_ids"]) == 1
    assert len(result["stats"]["evaluated_closed_execution_keys"]) == 2
    assert len(result["stats"]["evaluated_closed_executions"]) == 2


def test_ambiguous_bare_legacy_marker_blocks_instead_of_choosing_by_order(
    evaluator,
):
    shared_trade_id = "PREDATOR:SMART:XRPUSDT:LONG"
    evaluator.OUTCOME_STATS_FILE.write_text(
        json.dumps(
            _empty_stats(
                evaluator, evaluated_trade_ids=[shared_trade_id]
            )
        ),
        encoding="utf-8",
    )
    _write_positions(
        evaluator,
        [
            _closed(
                trade_id=shared_trade_id,
                closed_at="23/07/2026 10:00:00",
            ),
            _closed(
                trade_id=shared_trade_id,
                closed_at="23/07/2026 11:00:00",
            ),
        ],
    )

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 0
    assert result["skipped_count"] == 2
    assert {
        item["reason"] for item in result["skipped"]
    } == {"LEGACY_TRADE_ID_MARKER_AMBIGUOUS"}
    assert result["stats"]["global"]["trades"] == 0
    assert result["stats"]["evaluated_closed_executions"] == []
    assert not evaluator.OUTCOME_LOG_FILE.exists()


def test_marker_conflict_on_shared_lifecycle_is_fail_closed(evaluator):
    original = _closed(
        lifecycle_id="LC-CONFLICT",
        client_order_id="CLIENT-A",
        order_id="ORDER-A",
    )
    _write_positions(evaluator, [original])
    assert evaluator.evaluate_closed_paper_trades()["evaluated_count"] == 1

    conflicting = _closed(
        lifecycle_id="LC-CONFLICT",
        client_order_id="CLIENT-B",
        order_id="ORDER-B",
        closed_at="23/07/2026 12:00:00",
        pnl_pct=-1.0,
    )
    _write_positions(evaluator, [conflicting])

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 0
    assert result["skipped"][0]["reason"] == (
        "CLOSED_EXECUTION_MARKER_CONFLICT"
    )
    assert result["stats"]["global"]["trades"] == 1
    assert len(result["stats"]["evaluated_closed_executions"]) == 1
    stored = json.loads(evaluator.PAPER_POSITIONS_FILE.read_text("utf-8"))
    assert stored[0].get("outcome_evaluated") is not True
    assert len(evaluator.OUTCOME_LOG_FILE.read_text("utf-8").splitlines()) == 1


def test_internal_alias_conflict_is_not_evaluated(evaluator):
    conflicting = _closed(
        lifecycle_id="LC-TOP",
        client_order_id="CLIENT-A",
        order_id="ORDER-A",
    )
    conflicting["metadata"] = {"trade_lifecycle_id": "LC-METADATA"}
    _write_positions(evaluator, [conflicting])

    result = evaluator.evaluate_closed_paper_trades()

    assert result["evaluated_count"] == 0
    assert result["skipped"][0]["reason"] == (
        "CLOSED_EXECUTION_IDENTITY_ALIAS_CONFLICT"
    )
    assert result["stats"]["global"]["trades"] == 0
    assert result["stats"]["evaluated_closed_executions"] == []
    assert not evaluator.OUTCOME_LOG_FILE.exists()


def test_evaluator_mutation_does_not_change_legacy_incomplete_identity(
    evaluator,
):
    legacy_incomplete = _closed()
    before = evaluator._closed_execution_identity(legacy_incomplete)
    assert before["identity_kind"] == "LEGACY_INCOMPLETE_EXACT_ONLY"
    _write_positions(evaluator, [legacy_incomplete])

    first = evaluator.evaluate_closed_paper_trades()
    stored = json.loads(evaluator.PAPER_POSITIONS_FILE.read_text("utf-8"))[0]
    after = evaluator._closed_execution_identity(stored)
    retry = evaluator.evaluate_closed_paper_trades()

    assert after["canonical_key"] == before["canonical_key"]
    assert first["evaluated_count"] == 1
    assert retry["evaluated_count"] == 0
    assert retry["stats"]["global"]["trades"] == 1
