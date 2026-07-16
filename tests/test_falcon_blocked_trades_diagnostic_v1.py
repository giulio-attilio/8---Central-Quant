from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SOURCE = MAIN.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(MAIN))

UNKNOWN = "UNKNOWN_IN_EVENT"
HELPERS = {
    "_fbd_v1_limit",
    "_fbd_v1_containers",
    "_fbd_v1_first",
    "_fbd_v1_text",
    "_fbd_v1_event_name",
    "_fbd_v1_is_falcon_blocked",
    "_fbd_v1_bool",
    "_fbd_v1_epoch",
    "_fbd_v1_guard_category",
    "_fbd_v1_build_item",
    "build_falcon_blocked_diagnostic_v1",
    "build_falcon_blocked_diagnostic_v1_text",
}


def _functions(names: set[str], namespace: dict) -> dict:
    selected = {}
    for node in TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected[node.name] = copy.deepcopy(node)
    assert set(selected) == names, f"missing functions: {sorted(names - set(selected))}"
    module = ast.Module(body=sorted(selected.values(), key=lambda item: item.lineno), type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(MAIN), "exec"), namespace)
    return namespace


def _blocked(epoch=1.0, **updates):
    raw = {
        "execution_mode": "LIVE",
        "sent": False,
        "block_guard": "RISK_GUARD",
        "reasons": ["RISK_LIMIT_REACHED"],
        "score": 82.5,
        "risk_pct": 0.25,
        "falcon_audit_status": "OK_ACKED_HISTORY_CLEAR",
        "bingx_position_count": 0,
        "central_live_count": 0,
        "central_only_count": 0,
        "manual_external_same_symbol_side": False,
    }
    raw.update(updates.pop("raw", {}))
    event = {
        "event": "TRADE_BLOCKED",
        "bot": "FALCON",
        "source": "falcon",
        "epoch": epoch,
        "ts": f"16/07/2026 12:{int(epoch):02d}",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "setup": "FALCON30",
        "result": "DENY",
        "raw": raw,
    }
    event.update(updates)
    return event


def _diagnostic(events=None, error=None):
    namespace = {
        "FALCON_BLOCKED_DIAGNOSTIC_V1_VERSION": "1.0.0",
        "FALCON_BLOCKED_DIAGNOSTIC_V1_DEFAULT_LIMIT": 20,
        "FALCON_BLOCKED_DIAGNOSTIC_V1_MAX_LIMIT": 100,
        "FALCON_BLOCKED_DIAGNOSTIC_V1_MAX_SCAN": 1000,
        "FALCON_BLOCKED_DIAGNOSTIC_V1_UNKNOWN": UNKNOWN,
    }

    def loader(_scan_limit):
        if error:
            raise error
        return copy.deepcopy(events or []), "history_events.jsonl", None

    namespace["_fbd_v1_load_events"] = loader
    return _functions(HELPERS, namespace)


def test_endpoint_payload_lists_only_falcon_trade_blocked_in_descending_order():
    events = [
        _blocked(1, symbol="BTCUSDT", setup="FALCON15"),
        {"event": "TRADE_BLOCKED", "bot": "TURTLE", "epoch": 9},
        {"event": "TRADE_OPENED", "bot": "FALCON", "epoch": 10},
        _blocked(2, symbol="SOLUSDT", side="SHORT"),
    ]
    payload = _diagnostic(events)["build_falcon_blocked_diagnostic_v1"](limit=20)

    assert payload["status"] == "OK"
    assert payload["events_analyzed"] == 4
    assert payload["blocked_count"] == 2
    assert [item["symbol"] for item in payload["items"]] == ["SOLUSDT", "BTCUSDT"]
    assert payload["items"][0]["candidate"] == "FALCON30"
    assert payload["summary"]["risk"] == 2


def test_unknown_reason_is_explicit_and_never_invented():
    event = _blocked()
    event["raw"] = {"execution_mode": "PAPER", "sent": False}
    payload = _diagnostic([event])["build_falcon_blocked_diagnostic_v1"]()
    item = payload["items"][0]

    assert item["reason"] == UNKNOWN
    assert item["guard"] == UNKNOWN
    assert item["category"] == "unknown"
    assert item["recommendation"] == "instrumentar bloqueio na origem"
    assert "RISK" not in item["reason"]


def test_recorded_context_is_reported_without_live_broker_lookup():
    item = _diagnostic([_blocked(1)])["build_falcon_blocked_diagnostic_v1"]()["items"][0]

    assert item["sent"] is False
    assert item["execution_mode"] == "LIVE"
    assert item["bingx_position"] == 0
    assert item["central_live_position"] == 0
    assert item["central_only"] == 0
    assert item["manual_external_same_symbol_side"] is False
    assert item["falcon_audit_ok"] is True
    assert item["risk_guard_blocked"] is True
    assert item["score"] == 82.5
    assert item["risk_pct"] == 0.25


def test_blocked_audit_status_is_not_reported_as_audit_ok():
    event = _blocked(raw={"falcon_audit_status": "BLOCKED_BY_LIVE_AUDIT"})
    item = _diagnostic([event])["build_falcon_blocked_diagnostic_v1"]()["items"][0]

    assert item["falcon_audit_ok"] is False


def test_limit_defaults_to_20_and_is_capped_at_100():
    events = [_blocked(float(index), symbol=f"S{index}USDT") for index in range(140)]
    build = _diagnostic(events)["build_falcon_blocked_diagnostic_v1"]

    assert build(limit="invalid")["blocked_count"] == 20
    capped = build(limit=500)
    assert capped["limit"] == 100
    assert capped["blocked_count"] == 100


def test_empty_and_malformed_events_are_safe():
    empty = _diagnostic([])["build_falcon_blocked_diagnostic_v1"]()
    invalid_epoch = _blocked(1)
    invalid_epoch["epoch"] = "not-a-number"
    malformed = _diagnostic([None, "broken", {}, invalid_epoch])["build_falcon_blocked_diagnostic_v1"]()

    assert empty["ok"] is True and empty["items"] == []
    assert malformed["blocked_count"] == 1
    assert any("malformed" in warning for warning in malformed["warnings"])


def test_source_failure_returns_legible_read_only_error():
    payload = _diagnostic(error=OSError("local history unavailable"))["build_falcon_blocked_diagnostic_v1"]()

    assert payload["ok"] is False
    assert payload["status"] == "SOURCE_READ_ERROR"
    assert payload["read_only"] is True
    assert payload["items"] == []
    assert payload["error"] == "OSError"


def test_text_endpoint_contract_and_unknown_recommendation():
    event = _blocked()
    event["raw"] = {"sent": False}
    text = _diagnostic([event])["build_falcon_blocked_diagnostic_v1_text"](20)

    assert "FALCON BLOCKED TRADES — V1" in text
    assert "Status: OK" in text
    assert "reason: UNKNOWN_IN_EVENT" in text
    assert "recommendation: instrumentar bloqueio na origem" in text
    assert "bloqueios por unknown: 1" in text


class _FakeApp:
    def route(self, *_args, **_kwargs):
        return lambda function: function


def test_http_routes_use_only_read_only_builders_and_query_limit():
    namespace = {
        "app": _FakeApp(),
        "request": SimpleNamespace(args={"limit": "7"}),
        "FALCON_BLOCKED_DIAGNOSTIC_V1_DEFAULT_LIMIT": 20,
        "build_falcon_blocked_diagnostic_v1": lambda limit: {"status": "OK", "limit": int(limit)},
        "build_falcon_blocked_diagnostic_v1_text": lambda limit: f"limit={limit}",
    }
    routes = _functions(
        {"falcon_blocked_diagnostic_v1_route", "falcon_blocked_diagnostic_v1_text_route"},
        namespace,
    )

    assert routes["falcon_blocked_diagnostic_v1_route"]() == ({"status": "OK", "limit": 7}, 200)
    text, status, headers = routes["falcon_blocked_diagnostic_v1_text_route"]()
    assert text == "limit=7" and status == 200
    assert headers["Content-Type"].startswith("text/plain")


def test_diagnostic_code_has_no_mutating_or_external_calls():
    selected = [
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and (node.name in HELPERS or node.name == "_fbd_v1_load_events")
    ]
    called_names = {
        child.func.id
        for node in selected
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    called_attrs = {
        child.func.attr
        for node in selected
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
    }
    forbidden = {
        "create_order",
        "cancel_order",
        "close_position",
        "fetch_positions",
        "fetch_balance",
        "broker",
        "redis_set_json",
        "_append_jsonl",
        "_write_json_file",
    }

    assert not (called_names | called_attrs) & forbidden
    loader = next(node for node in selected if node.name == "_fbd_v1_load_events")
    assert any(isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "load_events" for child in ast.walk(loader))


def test_existing_falcon_and_bots_routes_remain_defined():
    route_functions = {
        node.name
        for node in TREE.body
        if isinstance(node, ast.FunctionDef)
        and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == "route" for decorator in node.decorator_list)
    }

    assert "falcon_route" in route_functions
    assert "bots" in route_functions
    assert "falcon_blocked_diagnostic_v1_route" in route_functions
    assert "falcon_blocked_diagnostic_v1_text_route" in route_functions
