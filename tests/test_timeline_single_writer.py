from __future__ import annotations

import ast
import copy
import importlib
import json
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _main_function(name):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compile_function(node, namespace):
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<timeline-single-writer>", "exec"), namespace)
    return namespace[node.name]


@pytest.fixture()
def history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "history"))
    sys.modules.pop("history_manager", None)
    module = importlib.import_module("history_manager")
    module.HISTORY_EVENTS_FILE = tmp_path / "history_events.jsonl"
    module.DECISION_LOG_FILE = tmp_path / "decision_log.jsonl"
    module.TIMELINE_LOG_FILE = tmp_path / "timeline.jsonl"
    module.HISTORY_SEEN_FILE = tmp_path / "history_seen.json"
    module.CLOSED_TRADES_FILE = tmp_path / "closed_trades.jsonl"
    module._PROCESS_SEEN_UIDS.clear()
    monkeypatch.setitem(
        sys.modules,
        "context_manager",
        SimpleNamespace(enrich_event=lambda item: item, CONTEXT_VERSION="test"),
    )
    monkeypatch.setitem(
        sys.modules,
        "journal_manager",
        SimpleNamespace(
            append_lifecycle_event=lambda item: {"ok": True},
            append_journal_trade=lambda item: {"ok": True},
        ),
    )
    return module


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.mark.parametrize(
    "event",
    [
        "RISK_ALLOW",
        "RISK_DENY",
        "SHADOW_POSITION",
        "TRADE_OPENED",
        "TP50_HIT",
        "TRAILING_UPDATED",
        "TRADE_CLOSED",
    ],
)
def test_each_logical_event_writes_one_timeline_row(history, event):
    result = history.log_event(
        event,
        {
            "trade_id": f"TR-{event}",
            "bot": "FALCON",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "timestamp": "2026-07-13T12:00:00Z",
        },
        source="falcon",
        trade_id=f"TR-{event}",
    )
    assert result["ok"] is True
    assert result["timeline_written"] is True
    assert len(_rows(history.TIMELINE_LOG_FILE)) == 1


def test_verify_allow_and_shadow_are_two_distinct_logical_rows_not_seven(history):
    common = {
        "trade_id": "TR-VERIFY",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "timestamp": "2026-07-13T12:00:00Z",
    }
    history.log_event("RISK_ALLOW", common, source="falcon", trade_id="TR-VERIFY")
    history.log_event(
        "SHADOW_POSITION",
        {**common, "state": "VERIFY"},
        source="falcon",
        trade_id="TR-VERIFY",
    )
    rows = _rows(history.TIMELINE_LOG_FILE)
    assert [row["event"] for row in rows] == ["RISK_ALLOW", "SHADOW_POSITION"]


def test_same_uid_is_persisted_once_with_bounded_process_dedup(history):
    payload = {
        "event_id": "EVENT-EXPLICIT",
        "trade_id": "TR-1",
        "symbol": "BTCUSDT",
    }
    first = history.log_event("TP50_HIT", payload, source="falcon", trade_id="TR-1")
    second = history.log_event("TP50_HIT", payload, source="falcon", trade_id="TR-1")
    assert first["event"]["uid"] == "EVENT-EXPLICIT"
    assert second["dedup"] is True
    assert len(_rows(history.TIMELINE_LOG_FILE)) == 1


def test_configure_timeline_writer_reuses_official_history_instance(history, tmp_path):
    canonical = tmp_path / "central" / "timeline.jsonl"
    returned = history.configure_timeline_writer(canonical)
    assert returned == canonical
    assert history.TIMELINE_LOG_FILE == canonical


def test_derived_uid_is_deterministic_and_event_specific(history):
    payload = {
        "trade_id": "TR-STABLE",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "timestamp": "2026-07-13T12:00:00Z",
        "new_stop": 101.5,
    }
    first = history.normalize_payload("TRAILING_UPDATED", payload, source="falcon")
    second = history.normalize_payload("TRAILING_UPDATED", copy.deepcopy(payload), source="falcon")
    other = history.normalize_payload("TP50_HIT", payload, source="falcon")
    assert first["uid"] == second["uid"]
    assert first["uid"].startswith("TIMELINE-")
    assert first["uid"] != other["uid"]


def test_derived_uid_is_stable_after_module_reload(tmp_path, monkeypatch):
    payload = {
        "trade_id": "TR-RESTART",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "timestamp": "2026-07-13T12:00:00Z",
    }
    values = []
    for number in range(2):
        monkeypatch.setenv("DATA_DIR", str(tmp_path / f"instance-{number}"))
        sys.modules.pop("history_manager", None)
        module = importlib.import_module("history_manager")
        values.append(module.normalize_payload("TRADE_OPENED", payload, source="falcon")["uid"])
    assert values[0] == values[1]


def test_bot_and_trade_ownership_are_part_of_uid(history):
    base = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "timestamp": "2026-07-13T12:00:00Z",
    }
    falcon = history.normalize_payload(
        "TRADE_OPENED", {**base, "bot": "FALCON", "trade_id": "TR-F"}, source="falcon"
    )
    predator = history.normalize_payload(
        "TRADE_OPENED", {**base, "bot": "PREDATOR", "trade_id": "TR-P"}, source="predator"
    )
    falcon_other = history.normalize_payload(
        "TRADE_OPENED", {**base, "bot": "FALCON", "trade_id": "TR-F2"}, source="falcon"
    )
    assert len({falcon["uid"], predator["uid"], falcon_other["uid"]}) == 3


def test_normalization_preserves_payload_and_both_schemas(history):
    payload = {
        "ts": "13/07/2026 12:00",
        "epoch": 123.5,
        "trade_id": "TR-SCHEMA",
        "event": "TP50_HIT",
        "state": "OPEN",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "details": {"note": [1]},
        "setup": "ORB",
        "score": 90,
        "entry": 100,
        "stop": 99,
        "tp50": 101,
        "risk_pct": 1,
        "result_pct": 1.2,
        "reason": "target",
    }
    original = copy.deepcopy(payload)
    item = history.normalize_payload("TP50_HIT", payload, source="falcon")
    assert payload == original
    for key in (
        "uid", "ts", "epoch", "event", "event_raw", "source", "trade_id",
        "bot", "symbol", "side", "setup", "score", "quality", "entry", "stop",
        "tp50", "exit_price", "risk_pct", "result_pct", "result_r", "result",
        "reason", "raw",
    ):
        assert key in item
    assert item["state"] == "OPEN"
    assert item["details"] == {"note": [1]}
    assert "details" not in item["raw"]


def test_append_failure_is_fail_open_and_does_not_retry(history, monkeypatch):
    calls = []

    def failing_append(path, item):
        calls.append(path)
        return False

    monkeypatch.setattr(history, "_append_jsonl", failing_append)
    result = history.log_event(
        "RISK_ALLOW",
        {"trade_id": "TR-FAIL", "timestamp": "2026-07-13T12:00:00Z"},
        source="central",
        trade_id="TR-FAIL",
    )
    assert result["ok"] is False
    assert calls == [history.HISTORY_EVENTS_FILE]


def test_timeline_failure_does_not_escape_or_trigger_fallback(history, monkeypatch):
    calls = []

    def selective_append(path, item):
        calls.append(path)
        return path != history.TIMELINE_LOG_FILE

    monkeypatch.setattr(history, "_append_jsonl", selective_append)
    result = history.log_event(
        "TP50_HIT",
        {"trade_id": "TR-TL-FAIL", "timestamp": "2026-07-13T12:00:00Z"},
        source="falcon",
        trade_id="TR-TL-FAIL",
    )
    assert result["ok"] is True
    assert result["timeline_written"] is False
    assert calls.count(history.TIMELINE_LOG_FILE) == 1


def test_central_wrappers_mark_existing_bridges_without_reemitting(history):
    calls = []

    def append_decision(payload, result):
        calls.append("decision")
        return {"ok": True}

    def append_timeline(event_type, **kwargs):
        calls.append(event_type)
        return {"event": event_type}

    namespace = {
        "append_decision_log": append_decision,
        "append_timeline_event": append_timeline,
        "LOADED_BOTS": {},
    }
    assert history.wrap_central_functions(namespace) is True
    assert namespace["append_decision_log"] is append_decision
    assert namespace["append_timeline_event"] is append_timeline
    namespace["append_decision_log"]({}, {})
    namespace["append_timeline_event"]("RISK_ALLOW")
    assert calls == ["decision", "RISK_ALLOW"]
    assert append_timeline._history_single_writer is True


def test_bot_wrapper_skips_function_that_already_emits_history(history):
    calls = []

    def record_event(event_type, pos, extra=None):
        calls.append("original")
        return {"event_type": event_type}

    module = SimpleNamespace(
        record_event=record_event,
        falcon_log_super_history=lambda *args, **kwargs: None,
        BOT_NAME="FALCON",
    )
    assert history.wrap_bot_module(module, "falcon") is True
    module.record_event("TP50", {"trade_id": "TR-1"})
    assert calls == ["original"]
    assert module.record_event is record_event


def test_generic_bot_wrapper_emits_once(history):
    def record_event(event_type, pos, extra=None):
        return {"event_type": event_type}

    module = SimpleNamespace(record_event=record_event, BOT_NAME="TURTLE")
    history.wrap_bot_module(module, "turtle")
    module.record_event(
        "TP50",
        {"trade_id": "TR-T", "symbol": "BTCUSDT", "side": "LONG"},
        extra={"timestamp": "2026-07-13T12:00:00Z"},
    )
    assert len(_rows(history.TIMELINE_LOG_FILE)) == 1


def test_event_bus_emits_one_timeline_row(history, tmp_path, monkeypatch):
    sys.modules.pop("event_bus", None)
    event_bus = importlib.import_module("event_bus")
    event_bus.history_manager = history
    event_bus.EVENT_BUS_LOG_FILE = tmp_path / "event_bus.jsonl"
    event_bus.EVENT_BUS_SEEN_FILE = tmp_path / "event_bus_seen.json"
    result = event_bus.emit_from_http(
        {
            "event_id": "BUS-1",
            "event": "TRADE_OPENED",
            "trade_id": "TR-BUS",
            "bot": "TURTLE",
            "symbol": "BTCUSDT",
        }
    )
    assert result["history_logged"] is True
    assert len(_rows(history.TIMELINE_LOG_FILE)) == 1


def test_paper_lifecycle_emits_one_timeline_row(history, tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path / "paper"))
    sys.modules.pop("paper_lifecycle", None)
    paper = importlib.import_module("paper_lifecycle")
    result = paper._emit_history_event(
        {
            "event_id": "PAPER-1",
            "event": "TRADE_OPENED",
            "trade_id": "TR-PAPER",
            "bot": "PAPER",
            "symbol": "BTCUSDT",
        }
    )
    assert result["ok"] is True
    assert len(_rows(history.TIMELINE_LOG_FILE)) == 1


def test_main_append_timeline_is_bridge_only():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "append_timeline_event"
    )
    rendered = ast.unparse(function)
    assert "_append_jsonl" not in rendered
    assert rendered.count("_emit_history_event") == 1


def test_main_bridge_preserves_public_schema_and_emits_once():
    emitted = []
    namespace = {
        "time": SimpleNamespace(time=lambda: 123.5),
        "data_hora_sp_str": lambda: "13/07/2026 12:00",
        "_event_trade_id": lambda bot, symbol, side, existing: existing or "TR-DERIVED",
        "normalize_symbol_for_risk": lambda symbol: str(symbol or "").upper(),
        "_emit_history_event": lambda *args, **kwargs: emitted.append((args, kwargs)),
    }
    bridge = _compile_function(_main_function("append_timeline_event"), namespace)
    details = {"setup": "ORB"}
    result = bridge(
        "RISK_ALLOW",
        bot="falcon",
        symbol="btcusdt",
        side="long",
        trade_id="TR-1",
        state="ALLOW",
        details=details,
    )
    assert len(emitted) == 1
    assert result == {
        "ts": "13/07/2026 12:00",
        "epoch": 123.5,
        "trade_id": "TR-1",
        "event": "RISK_ALLOW",
        "state": "ALLOW",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "details": details,
    }


def test_main_bridge_verify_flow_emits_two_distinct_events_not_seven():
    emitted = []
    namespace = {
        "time": SimpleNamespace(time=lambda: 123.5),
        "data_hora_sp_str": lambda: "13/07/2026 12:00",
        "_event_trade_id": lambda bot, symbol, side, existing: existing or "TR-VERIFY",
        "normalize_symbol_for_risk": lambda symbol: str(symbol or "").upper(),
        "_emit_history_event": lambda event_type, **kwargs: emitted.append(event_type),
    }
    bridge = _compile_function(_main_function("append_timeline_event"), namespace)
    bridge("RISK_ALLOW", trade_id="TR-VERIFY", state="VERIFY")
    bridge("SHADOW_POSITION", trade_id="TR-VERIFY", state="VERIFY")
    assert emitted == ["RISK_ALLOW", "SHADOW_POSITION"]


def test_history_exception_is_contained_by_main_history_bridge(monkeypatch):
    failing_history = SimpleNamespace(
        log_event=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full"))
    )
    monkeypatch.setitem(sys.modules, "history_manager", failing_history)
    namespace = {
        "_history_payload_from_event": lambda *args, **kwargs: {"trade_id": "TR-FAIL"},
    }
    emit = _compile_function(_main_function("_emit_history_event"), namespace)
    assert emit("RISK_ALLOW", trade_id="TR-FAIL") is None


def test_no_new_thread_network_broker_registry_or_lifecycle_dependency(monkeypatch):
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: pytest.fail("network access attempted"),
    )
    source = (ROOT / "history_manager.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert "Thread" not in calls
    assert "start" not in calls
    assert "register_open_trade" not in calls
    assert "update_trade" not in calls
    assert "close_trade" not in calls


def test_history_module_does_not_import_operational_components():
    tree = ast.parse((ROOT / "history_manager.py").read_text(encoding="utf-8"))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(
        {
            "broker",
            "trade_registry",
            "trade_lifecycle_manager",
            "trade_lifecycle_shadow_runtime_adapter",
            "requests",
            "redis",
        }
    )
