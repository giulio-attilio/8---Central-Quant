from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HISTORY_MANAGER_PATH = ROOT / "history_manager.py"
TRADE_ID = "FALCON:FALCON15:XRPUSDT:LONG"


@pytest.fixture()
def history_module(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "history-data"))
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path / "central-data"))
    monkeypatch.setenv("HISTORY_AUTO_BACKFILL_CLOSED", "false")
    spec = importlib.util.spec_from_file_location(
        f"_isolated_history_closed_identity_{tmp_path.name}",
        HISTORY_MANAGER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _event(identity, *, uid=None):
    event = {
        "event": "TRADE_CLOSED",
        "trade_id": TRADE_ID,
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "opened_at": "2026-07-18T18:00:00-03:00",
        "closed_at": "2026-07-18T18:37:00-03:00",
        "ts": "2026-07-18T18:37:00-03:00",
        "entry": 1.0871,
        "qty": 9,
        "result_pct": 0.2851623585686696,
        "pnl_pct": 0.2851623585686696,
        "lifecycle_id": f"LC-{identity}",
        "client_order_id": f"CLIENT-{identity}",
        "broker_order_id": f"ORDER-{identity}",
    }
    if uid is not None:
        event["uid"] = uid
    return event


def _read_jsonl(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def test_existing_uid_remains_authoritative(history_module):
    first = _event("A", uid="EVENT-1")
    second = _event("B", uid="EVENT-1")
    assert history_module._closed_trade_key(first) == "uid:EVENT-1"
    assert history_module._closed_trade_key(second) == "uid:EVENT-1"


def test_nested_strong_identity_preserves_distinct_executions(history_module):
    common = {
        "trade_id": TRADE_ID,
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "entry_time": "2026-07-18T18:00:00-03:00",
        "exit_time": "2026-07-18T18:37:00-03:00",
        "entry_price": 1.0871,
        "qty": 9,
        "pnl_pct": 0.2851623585686696,
    }
    first = {
        **common,
        "source_event": {
            "lifecycle_id": "LC-A",
            "client_order_id": "CLIENT-A",
            "broker_order_id": "ORDER-A",
        },
    }
    second = {
        **common,
        "metadata": {
            "raw": {
                "lifecycle_id": "LC-B",
                "clientOrderID": "client-b",
                "orderId": "ORDER-B",
            }
        },
    }
    assert history_module._closed_trade_key(first) == (
        "lifecycle:LC-A|client_order_id=client-a|order_id=ORDER-A"
    )
    assert history_module._closed_trade_key(second) == (
        "lifecycle:LC-B|client_order_id=client-b|order_id=ORDER-B"
    )
    assert history_module._closed_trade_key(first) != (
        history_module._closed_trade_key(second)
    )


def test_client_order_and_specific_ids_are_used_without_lifecycle(
    history_module,
):
    client_order = {
        "source_event": {
            "clientOrderId": "Client-Case-Insensitive",
            "broker_order_id": "ORDER-1",
        }
    }
    specific_a = {"metadata": {"execution_attempt_id": "ATTEMPT-A"}}
    specific_b = {"raw": {"execution_attempt_id": "ATTEMPT-B"}}
    assert history_module._closed_trade_key(client_order) == (
        "client_order:client-case-insensitive|ORDER-1"
    )
    assert history_module._closed_trade_key(specific_a) == (
        "specific:execution_attempt_id=ATTEMPT-A"
    )
    assert history_module._closed_trade_key(specific_b) == (
        "specific:execution_attempt_id=ATTEMPT-B"
    )


def test_same_lifecycle_with_different_order_identity_is_not_fused(
    history_module,
):
    first = {
        "lifecycle_id": "LC-SHARED",
        "client_order_id": "CLIENT-A",
        "broker_order_id": "ORDER-A",
    }
    second = {
        "lifecycle_id": "LC-SHARED",
        "client_order_id": "CLIENT-B",
        "broker_order_id": "ORDER-B",
    }
    assert history_module._closed_trade_key(first) != (
        history_module._closed_trade_key(second)
    )


def test_alias_conflict_is_quarantined_by_exact_fingerprint(history_module):
    first = {
        "trade_id": TRADE_ID,
        "lifecycle_id": "LC-A",
        "metadata": {"trade_lifecycle_id": "LC-B", "marker": "first"},
    }
    exact_copy = copy.deepcopy(first)
    distinct = copy.deepcopy(first)
    distinct["metadata"]["marker"] = "second"
    first_key = history_module._closed_trade_key(first)
    assert first_key.startswith("conflict:")
    assert history_module._closed_trade_key(exact_copy) == first_key
    assert history_module._closed_trade_key(distinct) != first_key


def test_legacy_fallback_contains_modes_times_entry_and_qty(history_module):
    base = {
        "trade_id": TRADE_ID,
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "opened_at": "2026-07-18T18:00:00-03:00",
        "closed_at": "2026-07-18T18:37:00-03:00",
        "entry": "1.0871000",
        "qty": "9.0",
    }
    expected = (
        "legacy:"
        f"{TRADE_ID}|REAL|LIVE|"
        "2026-07-18T18:00:00-03:00|"
        "2026-07-18T18:37:00-03:00|1.0871|9"
    )
    assert history_module._closed_trade_key(base) == expected
    verify = {**base, "registry_mode": "VERIFY"}
    assert history_module._closed_trade_key(verify) != expected
    reordered = {key: base[key] for key in reversed(list(base))}
    assert history_module._closed_trade_key(reordered) == expected


def test_append_preserves_two_strong_executions_and_dedups_exact_retry(
    history_module,
):
    first = history_module.append_closed_trade(_event("A"))
    second = history_module.append_closed_trade(_event("B"))
    retry = history_module.append_closed_trade(copy.deepcopy(_event("A")))
    rows = _read_jsonl(history_module.CLOSED_TRADES_FILE)

    assert first["dedup"] is False
    assert second["dedup"] is False
    assert retry["dedup"] is True
    assert len(rows) == 2
    assert {
        row["source_event"]["lifecycle_id"] for row in rows
    } == {"LC-A", "LC-B"}


def test_rebuild_is_deterministic_and_idempotent_for_strong_executions(
    history_module, monkeypatch
):
    events = [_event("A"), _event("B"), copy.deepcopy(_event("A"))]
    monkeypatch.setattr(
        history_module,
        "load_events",
        lambda limit=None: copy.deepcopy(events),
    )

    first = history_module.rebuild_closed_trades_v4_from_events()
    first_bytes = history_module.CLOSED_TRADES_FILE.read_bytes()
    second = history_module.rebuild_closed_trades_v4_from_events()
    second_bytes = history_module.CLOSED_TRADES_FILE.read_bytes()

    assert first.get("created") == 2, first
    assert second["created"] == 2
    assert first["errors"] == second["errors"] == 0
    assert first_bytes == second_bytes
    assert len(_read_jsonl(history_module.CLOSED_TRADES_FILE)) == 2


def test_backfill_is_incremental_and_idempotent_for_strong_executions(
    history_module, monkeypatch
):
    events = [_event("A"), _event("B"), copy.deepcopy(_event("A"))]
    monkeypatch.setattr(
        history_module,
        "load_events",
        lambda limit=None: copy.deepcopy(events),
    )

    first = history_module.backfill_closed_trades_from_events()
    second = history_module.backfill_closed_trades_from_events()

    assert first.get("created") == 2, first
    assert first["skipped"] == 1
    assert first["errors"] == 0
    assert second.get("created") == 0, second
    assert second["skipped"] == 3
    assert second["errors"] == 0
    assert len(_read_jsonl(history_module.CLOSED_TRADES_FILE)) == 2


def test_history_identity_helper_has_no_registry_broker_or_network_import():
    source = HISTORY_MANAGER_PATH.read_text(encoding="utf-8")
    assert "import trade_registry" not in source
    assert "from trade_registry" not in source
    assert "import broker" not in source
    assert "from broker" not in source
    assert "import requests" not in source
    assert "import socket" not in source
