from __future__ import annotations

import copy

import pytest

import trade_registry


@pytest.fixture(autouse=True)
def _isolate_registry_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(
        trade_registry,
        "TRADE_REGISTRY_FILE",
        str(tmp_path / "trade_registry.json"),
    )
    monkeypatch.setattr(
        trade_registry,
        "TRADE_REGISTRY_LEGACY_FILE",
        str(tmp_path / "legacy_trade_registry.json"),
    )


def _closed_trade(**updates):
    trade = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "opened_at": "2026-07-18T18:00:00-03:00",
        "closed_at": "2026-07-18T18:37:00-03:00",
        "entry": 1.0871,
        "qty": 9,
        "metadata": {},
    }
    trade.update(updates)
    return trade


def test_numeric_closed_collection_key_is_context_not_specific_identity():
    rows = trade_registry._closed_trade_records_from_collection(
        {"69": _closed_trade()}
    )

    assert len(rows) == 1
    assert rows[0]["registry_collection_key"] == "69"
    assert "registry_record_id" not in rows[0]
    assert (
        "registry_collection_key"
        not in trade_registry.CLOSED_TRADE_SPECIFIC_ID_FIELDS
    )
    state = trade_registry.closed_trade_identity_state(rows[0])
    assert state["identity_kind"] == "LEGACY_FALLBACK"
    assert not any(
        token.startswith("specific|registry_record_id|")
        for token in state["merge_tokens"]
    )


def test_same_contextual_key_in_distinct_sources_does_not_join_executions():
    first = _closed_trade(
        lifecycle_id="LC-XRP-ONE",
        client_order_id="CLIENT-XRP-ONE",
        broker_order_id="ORDER-XRP-ONE",
    )
    second = _closed_trade(
        lifecycle_id="LC-XRP-TWO",
        client_order_id="CLIENT-XRP-TWO",
        broker_order_id="ORDER-XRP-TWO",
        opened_at="2026-07-19T18:00:00-03:00",
        closed_at="2026-07-19T18:37:00-03:00",
        entry=1.09,
    )
    first_row = trade_registry._closed_trade_records_from_collection(
        {"69": first}
    )[0]
    second_row = trade_registry._closed_trade_records_from_collection(
        {"69": second}
    )[0]

    forward = trade_registry.merge_closed_trade_records(
        [first_row, second_row], sources=["snapshot", "active"]
    )
    reverse = trade_registry.merge_closed_trade_records(
        [second_row, first_row], sources=["active", "snapshot"]
    )

    assert len(forward["records"]) == 2
    assert forward["records"] == reverse["records"]
    assert forward["diagnostics"]["merge_group_count"] == 0
    assert forward["diagnostics"]["safe_to_commit"] is True
    assert {
        row["registry_collection_key"] for row in forward["records"]
    } == {"69"}
    assert {
        trade_registry.closed_trade_identity_state(row)["canonical_key"]
        for row in forward["records"]
    } == {"lifecycle|LC-XRP-ONE", "lifecycle|LC-XRP-TWO"}


def test_explicit_registry_record_id_remains_specific_and_is_not_overwritten():
    record = _closed_trade(
        registry_record_id="FACTUAL-CLOSED-RECORD-1",
        opened_at=None,
        closed_at=None,
    )
    row = trade_registry._closed_trade_records_from_collection(
        {"69": record}
    )[0]

    assert row["registry_record_id"] == "FACTUAL-CLOSED-RECORD-1"
    assert row["registry_collection_key"] == "69"
    state = trade_registry.closed_trade_identity_state(row)
    assert state["identity_kind"] == "SPECIFIC_EXECUTION_ID"
    assert state["canonical_key"] == (
        "specific|registry_record_id|FACTUAL-CLOSED-RECORD-1"
    )


def test_explicit_registry_record_id_duplicate_merge_is_order_independent():
    complete = _closed_trade(
        registry_record_id="FACTUAL-CLOSED-RECORD-1",
        lifecycle_id=None,
        client_order_id=None,
        broker_order_id=None,
    )
    sparse = copy.deepcopy(complete)
    sparse.pop("entry")
    first = trade_registry._closed_trade_records_from_collection(
        {"69": complete}
    )[0]
    second = trade_registry._closed_trade_records_from_collection(
        {"104": sparse}
    )[0]

    forward = trade_registry.merge_closed_trade_records([first, second])
    reverse = trade_registry.merge_closed_trade_records([second, first])

    assert len(forward["records"]) == 1
    assert forward["records"] == reverse["records"]
    assert forward["records"][0]["entry"] == 1.0871
    assert forward["records"][0]["registry_record_id"] == (
        "FACTUAL-CLOSED-RECORD-1"
    )
    assert forward["diagnostics"]["safe_to_commit"] is True
