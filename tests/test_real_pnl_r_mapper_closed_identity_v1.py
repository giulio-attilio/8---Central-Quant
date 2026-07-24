from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAPPER_PATH = ROOT / "real_pnl_r_mapper.py"
TRADE_ID = "FALCON:FALCON15:XRPUSDT:LONG"


@pytest.fixture()
def mapper(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    spec = importlib.util.spec_from_file_location(
        f"_isolated_real_pnl_r_mapper_{tmp_path.name}", MAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _raw_trade(**updates):
    trade = {
        "trade_id": TRADE_ID,
        "status": "CLOSED",
        "event": "TRADE_CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-XRP-REAL",
        "client_order_id": "CLIENT-XRP-REAL",
        "broker_order_id": "ORDER-XRP-REAL",
        "order_id": "ORDER-XRP-REAL",
        "entry": 1.0871,
        "stop": 1.084175,
        "exit_price": 1.0902,
        "qty": 9,
        "closed_at": "2026-07-18T18:37:00-03:00",
        "pnl_pct": 0.2851623585686696,
        "result_r": 1.0614,
        "outcome_status": "OUTCOME_RECORDED",
        "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
        "outcome_id": "XRP_MANUAL_TP50_20260718_1837",
    }
    trade.update(updates)
    return trade


def _normalized(mapper, raw, source="trade_registry_json"):
    item = mapper._normalize_trade_v26(raw, source)
    assert item is not None
    return item


def _stable(rows):
    return json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def test_verify_and_real_with_same_trade_id_remain_distinct(mapper):
    verify = _raw_trade(
        registry_mode="VERIFY",
        execution_mode="VERIFY",
        lifecycle_id=None,
        client_order_id=None,
        broker_order_id=None,
        order_id=None,
        entry=1.1123,
        stop=1.108,
        exit_price=1.113,
        qty=7,
        closed_at="2026-07-01T10:00:00-03:00",
        outcome_status="CLOSED",
        outcome_source="FALCON",
        outcome_id=None,
    )
    result = mapper._merge_trades_with_diagnostics(
        [_normalized(mapper, verify), _normalized(mapper, _raw_trade())]
    )

    assert len(result["records"]) == 2
    by_mode = {row["registry_mode"]: row for row in result["records"]}
    assert by_mode["VERIFY"]["entry"] == pytest.approx(1.1123)
    assert by_mode["REAL"]["entry"] == pytest.approx(1.0871)
    assert by_mode["REAL"]["lifecycle_id"] == "LC-XRP-REAL"
    assert by_mode["REAL"]["client_order_id"] == "CLIENT-XRP-REAL"
    assert by_mode["REAL"]["broker_order_id"] == "ORDER-XRP-REAL"
    assert by_mode["REAL"]["outcome_status"] == "OUTCOME_RECORDED"
    assert result["diagnostics"]["real_verify_collision_group_count"] == 1
    assert result["diagnostics"]["trade_id_only_merge"] is False


def test_two_real_executions_with_same_trade_id_remain_distinct(mapper):
    second = _raw_trade(
        lifecycle_id="LC-XRP-REAL-2",
        client_order_id="CLIENT-XRP-REAL-2",
        broker_order_id="ORDER-XRP-REAL-2",
        order_id="ORDER-XRP-REAL-2",
        entry=1.2,
        stop=1.18,
        exit_price=1.23,
        qty=10,
        closed_at="2026-07-20T12:00:00-03:00",
        outcome_id="XRP-SECOND-CLOSE",
    )
    result = mapper._merge_trades_with_diagnostics(
        [_normalized(mapper, _raw_trade()), _normalized(mapper, second)]
    )

    assert len(result["records"]) == 2
    assert {row["lifecycle_id"] for row in result["records"]} == {
        "LC-XRP-REAL",
        "LC-XRP-REAL-2",
    }


def test_registry_reader_does_not_drop_distinct_strong_identities(
    mapper, tmp_path
):
    second = _raw_trade(
        lifecycle_id="LC-XRP-REAL-2",
        client_order_id="CLIENT-XRP-REAL-2",
        broker_order_id="ORDER-XRP-REAL-2",
        order_id="ORDER-XRP-REAL-2",
    )
    registry_path = tmp_path / "trade_registry.json"
    registry_path.write_text(
        json.dumps(
            {"closed_trades": [_raw_trade(), second]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    mapper.TRADE_REGISTRY_JSON_FILE = str(registry_path)

    rows = mapper._read_trade_registry_json_rows()
    assert len(rows) == 2
    assert {row["lifecycle_id"] for row in rows} == {
        "LC-XRP-REAL",
        "LC-XRP-REAL-2",
    }


def test_same_execution_is_deduplicated_conservatively(mapper):
    complete = _raw_trade()
    incomplete = _raw_trade(
        exit_price=None,
        pnl_pct=None,
        result_r=None,
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
    )
    result = mapper._merge_trades_with_diagnostics(
        [
            _normalized(mapper, incomplete, source="history_events"),
            _normalized(mapper, complete, source="trade_registry_json"),
        ]
    )

    assert len(result["records"]) == 1
    merged = result["records"][0]
    assert merged["lifecycle_id"] == "LC-XRP-REAL"
    assert merged["exit"] == pytest.approx(1.0902)
    assert merged["outcome_status"] == "OUTCOME_RECORDED"
    assert merged["outcome_source"] == "MANUAL_CLOSE_RECONCILIATION"
    assert merged["outcome_id"] == "XRP_MANUAL_TP50_20260718_1837"
    assert set(merged["sources"]) == {"history_events", "trade_registry_json"}
    assert result["diagnostics"]["duplicate_execution_copy_count"] == 1
    assert result["diagnostics"]["safe_to_commit"] is True


def test_open_observation_enriches_incomplete_closed_only_with_canonical_identity(
    mapper,
):
    closed = _raw_trade(
        entry=None,
        stop=None,
        qty=None,
        pnl_pct=None,
        result_r=None,
    )
    opened = _raw_trade(
        status="OPEN",
        event="POSITION_OPEN",
        exit_price=None,
        closed_at=None,
        pnl_pct=None,
        result_r=None,
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
        opened_at="2026-07-18T17:00:00-03:00",
    )

    result = mapper._merge_trades_with_diagnostics(
        [
            _normalized(mapper, closed, source="trade_registry_json"),
            _normalized(mapper, opened, source="history_events"),
        ]
    )
    reversed_result = mapper._merge_trades_with_diagnostics(
        [
            _normalized(mapper, opened, source="history_events"),
            _normalized(mapper, closed, source="trade_registry_json"),
        ]
    )

    assert len(result["records"]) == 1
    assert _stable(result["records"]) == _stable(reversed_result["records"])
    merged = result["records"][0]
    assert merged["status"] == "CLOSED"
    assert merged["closed"] is True
    assert merged["entry"] == pytest.approx(1.0871)
    assert merged["stop"] == pytest.approx(1.084175)
    assert merged["qty"] == pytest.approx(9)
    assert merged["exit"] == pytest.approx(1.0902)
    assert set(merged["sources"]) == {"history_events", "trade_registry_json"}
    assert result["diagnostics"]["open_enrichment_candidate_count"] == 1
    assert result["diagnostics"]["open_enrichment_consumed_count"] == 1
    assert result["diagnostics"]["open_enrichment_preserved_count"] == 0
    assert result["diagnostics"]["safe_to_commit"] is True


def test_open_observation_with_different_lifecycle_does_not_enrich_closed(
    mapper,
):
    closed = _raw_trade(
        entry=None,
        stop=None,
        qty=None,
        pnl_pct=None,
        result_r=None,
    )
    other_open = _raw_trade(
        status="OPEN",
        event="POSITION_OPEN",
        lifecycle_id="LC-XRP-OTHER",
        client_order_id="CLIENT-XRP-OTHER",
        broker_order_id="ORDER-XRP-OTHER",
        order_id="ORDER-XRP-OTHER",
        exit_price=None,
        closed_at=None,
        pnl_pct=None,
        result_r=None,
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
        opened_at="2026-07-18T17:00:00-03:00",
    )

    result = mapper._merge_trades_with_diagnostics(
        [
            _normalized(mapper, closed, source="trade_registry_json"),
            _normalized(mapper, other_open, source="history_events"),
        ]
    )

    assert len(result["records"]) == 2
    merged_closed = next(row for row in result["records"] if row["closed"])
    preserved_open = next(row for row in result["records"] if not row["closed"])
    assert merged_closed["lifecycle_id"] == "LC-XRP-REAL"
    assert merged_closed["entry"] is None
    assert merged_closed["qty"] is None
    assert preserved_open["lifecycle_id"] == "LC-XRP-OTHER"
    assert preserved_open["entry"] == pytest.approx(1.0871)
    assert result["diagnostics"]["open_enrichment_candidate_count"] == 0
    assert result["diagnostics"]["open_enrichment_consumed_count"] == 0
    assert result["diagnostics"]["safe_to_commit"] is True


def test_open_observation_with_conflicting_strong_identity_is_preserved_fail_closed(
    mapper,
):
    opened = _raw_trade(
        status="OPEN",
        event="POSITION_OPEN",
        client_order_id="CLIENT-XRP-CONFLICT",
        broker_order_id="ORDER-XRP-CONFLICT",
        order_id="ORDER-XRP-CONFLICT",
        exit_price=None,
        closed_at=None,
        pnl_pct=None,
        result_r=None,
        outcome_status=None,
        outcome_source=None,
        outcome_id=None,
    )
    result = mapper._merge_trades_with_diagnostics(
        [
            _normalized(mapper, _raw_trade(), source="trade_registry_json"),
            _normalized(mapper, opened, source="history_events"),
        ]
    )

    assert len(result["records"]) == 2
    assert sum(1 for row in result["records"] if row["closed"]) == 1
    assert sum(1 for row in result["records"] if not row["closed"]) == 1
    assert result["diagnostics"]["open_enrichment_candidate_count"] == 1
    assert result["diagnostics"]["open_enrichment_consumed_count"] == 0
    assert result["diagnostics"]["open_enrichment_preserved_count"] == 1
    assert result["diagnostics"]["ambiguous_identity_bridge_count"] == 1
    assert result["diagnostics"]["safe_to_commit"] is False


def test_merge_is_deterministic_when_source_order_is_reversed(mapper):
    complete = _normalized(mapper, _raw_trade(), source="trade_registry_json")
    incomplete = _normalized(
        mapper,
        _raw_trade(
            exit_price=None,
            pnl_pct=None,
            result_r=None,
            outcome_status=None,
            outcome_source=None,
            outcome_id=None,
        ),
        source="history_events",
    )
    second = _normalized(
        mapper,
        _raw_trade(
            lifecycle_id="LC-XRP-REAL-2",
            client_order_id="CLIENT-XRP-REAL-2",
            broker_order_id="ORDER-XRP-REAL-2",
            order_id="ORDER-XRP-REAL-2",
            entry=1.2,
            stop=1.18,
            exit_price=1.23,
            qty=10,
            closed_at="2026-07-20T12:00:00-03:00",
            outcome_id="XRP-SECOND-CLOSE",
        ),
        source="trade_registry_json",
    )

    forward = mapper._merge_trades_with_diagnostics(
        [incomplete, second, complete]
    )
    reverse = mapper._merge_trades_with_diagnostics(
        [complete, second, incomplete]
    )
    assert _stable(forward["records"]) == _stable(reverse["records"])


def test_conflicting_strong_aliases_are_preserved_and_block_commit(mapper):
    corrupted = _raw_trade(
        metadata={"trade_lifecycle_id": "LC-XRP-CONFLICT"}
    )
    clean = _raw_trade(
        lifecycle_id="LC-XRP-CLEAN",
        client_order_id="CLIENT-XRP-CLEAN",
        broker_order_id="ORDER-XRP-CLEAN",
        order_id="ORDER-XRP-CLEAN",
        closed_at="2026-07-19T18:37:00-03:00",
        outcome_id="XRP-CLEAN-CLOSE",
    )
    result = mapper._merge_trades_with_diagnostics(
        [_normalized(mapper, corrupted), _normalized(mapper, clean)]
    )

    assert len(result["records"]) == 2
    assert result["diagnostics"]["strong_alias_conflict_count"] == 1
    assert result["diagnostics"]["safe_to_commit"] is False
    assert any(
        row.get("metadata", {}).get("trade_lifecycle_id")
        == "LC-XRP-CONFLICT"
        for row in result["records"]
    )


def test_build_blocks_mapper_persistence_when_identity_merge_is_unsafe(
    mapper, monkeypatch
):
    corrupted = _raw_trade(
        metadata={"trade_lifecycle_id": "LC-XRP-CONFLICT"}
    )
    monkeypatch.setattr(
        mapper,
        "_read_trade_registry_json_rows",
        lambda limit=None: [corrupted],
    )
    monkeypatch.setattr(mapper, "_read_jsonl", lambda *args, **kwargs: [])
    monkeypatch.setattr(mapper, "_load_history_export_rows", lambda: [])
    monkeypatch.setattr(
        mapper,
        "_write_json",
        lambda *args, **kwargs: pytest.fail("mapper snapshot write"),
    )
    monkeypatch.setattr(
        mapper,
        "_append_jsonl",
        lambda *args, **kwargs: pytest.fail("mapper event write"),
    )

    payload = mapper.build_real_pnl_r_map(commit=True)
    assert payload["status"] == "CLOSED_IDENTITY_REVIEW_REQUIRED"
    assert payload["commit_blocked"] is True
    assert payload["committed"] is False
    assert payload["closed_identity_merge"]["safe_to_commit"] is False
