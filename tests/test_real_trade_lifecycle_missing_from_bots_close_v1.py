from __future__ import annotations

import ast
import copy
import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, request as flask_request


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))

TRADE_ID = "FALCON:FALCON15:XRPUSDT:LONG"
LIFECYCLE_ID = "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114"
CLIENT_ORDER_ID = "FALCON-LIVE-FALCON15-1784384114"
BROKER_ORDER_ID = "2078483751332171776"

_FUNCTION_CODE = None


def _norm_symbol(value):
    return (
        str(value or "")
        .upper()
        .replace("/", "")
        .replace(":USDT", "")
        .replace("-", "")
        .strip()
    )


def _norm_side(value):
    value = str(value or "").upper().strip()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(value, value)


def _norm_bot(value):
    return str(value or "FALCON").upper().strip()


def _value(record, *keys):
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _base_trade(**updates):
    trade = {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "broker_order_id": BROKER_ORDER_ID,
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "status": "MISSING_FROM_BOTS",
        "entry": 1.0871,
        "qty": 9.0,
        "metadata": {"source": "test_real_trade_lifecycle_missing_from_bots_close_v1"},
    }
    trade.update(updates)
    return trade


def _known_flat_lifecycle(**updates):
    lifecycle = {
        "ok": False,
        "status": "NO_OPEN_POSITION_AND_NO_OPEN_REGISTRY_MATCH",
        "position_found": False,
        "requires_manual_attention": False,
        "actions": [],
        "safety_check": {
            "positions_fetch_ok": True,
            "positions_response_received": True,
            "positions_response_shape_valid": True,
            "position_rows_valid": True,
            "position_absence_confirmed": True,
            "position_count": 0,
        },
    }
    lifecycle.update(updates)
    return lifecycle


def _flat_reader_payload(**updates):
    payload = {
        "ok": True,
        "response_received": True,
        "response_shape_valid": True,
        "position_rows_valid": True,
        "position_absence_confirmed": True,
        "count": 0,
        "positions": [],
        "error": None,
    }
    payload.update(updates)
    return payload


class FakeRegistry:
    def __init__(self, open_trades=None):
        self.state = {
            "open_trades": copy.deepcopy(open_trades if open_trades is not None else {TRADE_ID: _base_trade()}),
            "closed_trades": [],
        }
        self.read_calls = 0
        self.close_calls = []
        self.legacy_load_calls = 0
        self.save_calls = 0

    def load_registry_read_only(self):
        self.read_calls += 1
        return copy.deepcopy(self.state)

    def load_registry(self):
        self.legacy_load_calls += 1
        raise AssertionError("mutating/bootstrap Registry loader called")

    def save_registry(self, _registry):
        self.save_calls += 1
        raise AssertionError("direct Registry writer called")

    def close_trade(self, trade_id, **kwargs):
        self.close_calls.append((trade_id, copy.deepcopy(kwargs)))
        open_trades = self.state["open_trades"]
        if not isinstance(open_trades, dict):
            raise AssertionError("commit tests require dict-backed open_trades")
        trade = open_trades.get(trade_id)
        if not isinstance(trade, dict):
            return {"ok": False, "action": "TRADE_NOT_FOUND", "trade_id": trade_id}

        expected = kwargs.get("expected_identity") or {}
        actual = {
            "trade_id": str(_value(trade, "trade_id") or trade_id),
            "lifecycle_id": str(_value(trade, "lifecycle_id") or ""),
            "client_order_id": str(
                _value(trade, "client_order_id", "clientOrderId", "client_tag") or ""
            ),
            "order_id": str(
                _value(
                    trade,
                    "broker_order_id",
                    "order_id",
                    "live_order_id",
                    "entry_order_id",
                )
                or ""
            ),
            "symbol": _norm_symbol(_value(trade, "symbol", "symbol_clean")),
            "side": _norm_side(_value(trade, "side", "direction")),
            "bot": _norm_bot(_value(trade, "bot")),
            "setup": str(_value(trade, "setup", "signal_type", "setup_label") or "")
            .upper()
            .strip(),
            "registry_mode": str(_value(trade, "registry_mode") or "").upper().strip(),
            "execution_mode": str(_value(trade, "execution_mode") or "").upper().strip(),
            "status": str(_value(trade, "status") or "").upper().strip(),
        }
        if actual != expected:
            return {
                "ok": False,
                "action": "EXPECTED_IDENTITY_MISMATCH",
                "expected": expected,
                "actual": actual,
            }

        closed = copy.deepcopy(trade)
        closed.update(
            {
                "status": "CLOSED",
                "close_reason": kwargs.get("reason"),
                "central_only_broker_flat_reconciled": kwargs.get(
                    "central_only_broker_flat_reconciled"
                ),
                "financial_reconciliation_pending": kwargs.get(
                    "financial_reconciliation_pending"
                ),
                "learning_eligible": kwargs.get("learning_eligible"),
                "outcome_status": kwargs.get("outcome_status"),
                "missing_from_bots_strong_identity_validated": kwargs.get(
                    "missing_from_bots_strong_identity_validated"
                ),
            }
        )
        closed.setdefault("metadata", {}).update(kwargs.get("metadata") or {})
        open_trades.pop(trade_id)
        self.state["closed_trades"].append(closed)
        return {"ok": True, "action": "TRADE_CLOSED", "trade_id": trade_id}


class FakeBroker:
    WRITER_NAMES = {
        "place_market_order",
        "create_order",
        "create_disaster_stop_order",
        "managed_close_position_market",
        "close_position_market",
        "cancel_order",
        "cancel_all_orders",
    }

    def __init__(self, position_payload=None):
        self.position_payload = copy.deepcopy(
            _flat_reader_payload() if position_payload is None else position_payload
        )
        self.position_reads = []
        self.writer_calls = []
        self.auth_calls = []

    def read_positions(self, symbol, side, strict_raw_exchange=False):
        assert strict_raw_exchange is True
        self.position_reads.append((symbol, side))
        return copy.deepcopy(self.position_payload)

    def __getattr__(self, name):
        if name not in self.WRITER_NAMES:
            raise AttributeError(name)

        def forbidden_writer(*args, **kwargs):
            self.writer_calls.append((name, args, kwargs))
            raise AssertionError(f"Broker writer called: {name}")

        return forbidden_writer


class RequestProbe:
    def __init__(self, args=None, path="/realtradelifecycle", headers=None, json_body=None):
        self.args = dict(args or {})
        self.path = path
        self.headers = dict(headers or {})
        self.form = {}
        self.values = dict(self.args)
        self._json_body = copy.deepcopy(json_body)

    def get_json(self, silent=True):
        return copy.deepcopy(self._json_body)


def _function_code():
    global _FUNCTION_CODE
    if _FUNCTION_CODE is not None:
        return _FUNCTION_CODE
    wanted = {
        "_rtlm_v1_bool",
        "_rtlm_v1_registry_open_items",
        "_rtlm_v14_clean_identity",
        "_rtlm_v14_trade_value",
        "_rtlm_v14_trade_values",
        "_rtlm_v14_normalize_identity_field",
        "_rtlm_v14_record_identity",
        "_rtlm_v14_record_matches_identity",
        "_rtlm_v14_missing_close_identity",
        "_rtlm_v14_build_position_evidence",
        "_rtlm_v14_resolve_missing_from_bots_close",
        "_rtlm_v14_confirm_registry_close",
        "_rtlm_v14_close_missing_from_bots",
        "_rtlm_v14_apply_missing_from_bots_close",
        "_rtlm_private_no_store_headers",
        "memory_stabilizer_after_request",
        "_rtlm_v15_is_auth_material_key",
        "_rtlm_v15_contains_auth_material",
        "_rtlm_v15_admin_auth",
        "_rtlm_v15_public_payload",
        "_rtlm_v15_response",
        "_rtlm_v15_get_mutation_parameters",
        "_rtlm_v15_identity_from_mapping",
        "_rtlm_v16_identity_divergence_diagnostic",
        "real_trade_lifecycle_monitor_v1_route",
        "real_trade_lifecycle_missing_from_bots_close_v15_route",
    }
    nodes = []
    found = set()
    for item in MAIN_TREE.body:
        if isinstance(item, ast.FunctionDef) and item.name in wanted:
            node = copy.deepcopy(item)
            node.decorator_list = []
            nodes.append(node)
            found.add(node.name)
    assert found == wanted
    tree = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(tree)
    _FUNCTION_CODE = compile(tree, "<isolated-real-trade-lifecycle-v14>", "exec")
    return _FUNCTION_CODE


def _exec_main_function(namespace, name, occurrence=-1):
    matches = [
        item
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    ]
    assert matches, name
    node = copy.deepcopy(matches[occurrence])
    node.decorator_list = []
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, f"<isolated-{name}>", "exec"), namespace)


def _install_real_read_only_builder(namespace, broker):
    forbidden_calls = []

    def forbidden(name):
        def fail(*_args, **_kwargs):
            forbidden_calls.append(name)
            raise AssertionError(f"strict GET reached forbidden path: {name}")

        return fail

    def position_reader(symbol, side, strict_raw_exchange=False):
        return broker.read_positions(symbol, side, strict_raw_exchange=True)

    namespace.update(
        {
            "TRADE_REGISTRY_IMPORT_ERROR": None,
            "POST_EXECUTION_SAFETY_CHECK_V1_VERSION": "TEST-SAFETY-V1",
            "TP50_RESOLVER_V1_VERSION": "TEST-TP50-V1",
            "REGISTRY_PERSISTENCE_V1_VERSION": "TEST-PERSISTENCE-V1",
            "_pesc_v1_norm_symbol": _norm_symbol,
            "_pesc_v1_norm_side": _norm_side,
            "_pesc_v1_fetch_positions": position_reader,
            "_pesc_v11_fetch_open_orders": lambda *_args, **_kwargs: {
                "ok": True,
                "orders": [],
                "count": 0,
                "attempts": [],
            },
            "_pesc_v1_is_protective_order": lambda *_args, **_kwargs: False,
            "_pesc_v11_registry_repair_from_position": forbidden(
                "registry_repair"
            ),
            "get_open_positions_central": forbidden("get_open_positions_central"),
            "central_trade_registry_snapshot": forbidden(
                "central_trade_registry_snapshot"
            ),
            "autosync_trade_registry": forbidden("autosync_trade_registry"),
            "registry_persistence_v1_snapshot": forbidden(
                "registry_persistence_v1_snapshot"
            ),
            "registry_persistence_v1_restore_from_latest_snapshot": forbidden(
                "registry_persistence_v1_restore_from_latest_snapshot"
            ),
            "_rp_v1_read_latest_snapshot": forbidden("read_latest_snapshot"),
            "_rp_v1_atomic_write_json": forbidden("atomic_snapshot_write"),
            "_rp_v1_append_event": forbidden("persistent_event_write"),
            "trade_registry_sync_v1_register_candidate": forbidden(
                "trade_registry_sync"
            ),
            "data_hora_sp_str": lambda: "22/07/2026 00:00",
            "_rtlm_v1_tp50_status": lambda *_args, **_kwargs: {
                "needs_tp50_review": False,
                "resolved": False,
            },
            "_rtlm_v1_update_open_trade_snapshot": lambda **kwargs: (
                {
                    "attempted": False,
                    "committed": False,
                    "status": "STRICT_READ_ONLY_NOT_REQUESTED",
                }
                if kwargs.get("commit") is False
                else forbidden("registry_snapshot_update")()
            ),
            "_rp_v1_bool": lambda value, default=False: str(value or "")
            .strip()
            .lower()
            in {"1", "true", "yes", "sim", "on"},
        }
    )

    for name in (
        "_pesc_v11_trade_registry_matches",
        "build_post_execution_safety_check_v1",
        "_rtlm_v1_registry_available",
        "_rtlm_v1_load_registry",
        "_rtlm_v1_match_trade",
        "_rtlm_v1_find_open_trades",
        "_rtlm_v1_first_position",
        "_rtlm_v1_first_registry_trade",
        "_rtlm_v1_protective_summary",
    ):
        _exec_main_function(namespace, name)

    _exec_main_function(namespace, "build_real_trade_lifecycle_monitor_v1", 0)
    namespace["_rtlm_v13_original_build_real_trade_lifecycle_monitor_v1"] = (
        namespace["build_real_trade_lifecycle_monitor_v1"]
    )
    _exec_main_function(namespace, "_rp_v1_registry_snapshot_full")
    _exec_main_function(namespace, "build_real_trade_lifecycle_monitor_v1", -1)
    return forbidden_calls


def _harness(
    open_trades=None,
    *,
    position_payload=None,
    request_args=None,
    request_path="/realtradelifecycle",
    request_headers=None,
    request_json=None,
    auth_result=None,
    lifecycle=None,
):
    registry = FakeRegistry(open_trades=open_trades)
    broker = FakeBroker(position_payload=position_payload)
    build_calls = []
    lifecycle_template = copy.deepcopy(lifecycle or _known_flat_lifecycle())

    def build_monitor(**kwargs):
        build_calls.append(copy.deepcopy(kwargs))
        return copy.deepcopy(lifecycle_template)

    default_headers = (
        {"X-Execution-Auth-Token": "TEST-EXECUTION-AUTH"}
        if request_headers is None
        else dict(request_headers)
    )
    request_probe = RequestProbe(
        args=request_args,
        path=request_path,
        headers=default_headers,
        json_body=request_json,
    )
    namespace = {}

    def auth_resolver(*args, **kwargs):
        broker.auth_calls.append({"args": args, "kwargs": copy.deepcopy(kwargs)})
        if auth_result is not None:
            return copy.deepcopy(auth_result)
        current_request = namespace.get("request", request_probe)
        token = current_request.headers.get("X-Execution-Auth-Token")
        if token == "TEST-EXECUTION-AUTH":
            return {
                "ok": True,
                "status": "EXECUTION_AUTH_OK",
                "matched_source": "request.headers.X-Execution-Auth-Token",
            }
        return {"ok": False, "status": "INVALID_EXECUTION_AUTH_TOKEN"}

    namespace.update({
        "central_trade_registry": registry,
        "central_broker": broker,
        "REAL_TRADE_LIFECYCLE_MONITOR_V1_VERSION": "TEST-V1.5",
        "request": request_probe,
        "app": SimpleNamespace(
            logger=SimpleNamespace(exception=lambda *_args, **_kwargs: None)
        ),
        "MEMORY_STABILIZER_ENABLED": False,
        "MEMORY_STABILIZER_FORCE_GC_AFTER_REQUEST": False,
        "_rtlm_v1_norm_symbol": _norm_symbol,
        "_rtlm_v1_norm_side": _norm_side,
        "_rtlm_v1_norm_bot": _norm_bot,
        "_rtlm_v1_now": lambda: "2026-07-22T00:00:00-03:00",
        "_ee_auth_resolver_v1_get_from_mapping": lambda mapping, key: (
            mapping.get(key) if hasattr(mapping, "get") else None
        ),
        "_ee_auth_resolver_v1_resolve": auth_resolver,
        "_pesc_v1_fetch_positions": broker.read_positions,
        "build_real_trade_lifecycle_monitor_v1": build_monitor,
    })
    exec(_function_code(), namespace)
    # The isolated route resolves this global at call time; retain the probe
    # instead of importing either definition of the production monitor.
    namespace["build_real_trade_lifecycle_monitor_v1"] = build_monitor
    return namespace, registry, broker, build_calls


def _route_payload(result):
    return result[0] if isinstance(result, tuple) else result


def _flask_client_for_harness(namespace):
    app = Flask(f"isolated-rtlm-{id(namespace)}")
    app.config.update(TESTING=True)
    namespace["app"] = app
    namespace["request"] = flask_request
    app.add_url_rule(
        "/realtradelifecycle",
        "real_trade_lifecycle_preview",
        namespace["real_trade_lifecycle_monitor_v1_route"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/realtradelifecycle/<symbol>/<side>",
        "real_trade_lifecycle_preview_path",
        namespace["real_trade_lifecycle_monitor_v1_route"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/lifecyclemonitor",
        "real_trade_lifecycle_alias",
        namespace["real_trade_lifecycle_monitor_v1_route"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/lifecyclemonitor/<symbol>/<side>",
        "real_trade_lifecycle_alias_path",
        namespace["real_trade_lifecycle_monitor_v1_route"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/trade/lifecycle",
        "real_trade_lifecycle_trade_alias",
        namespace["real_trade_lifecycle_monitor_v1_route"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/realtradelifecycle/close",
        "real_trade_lifecycle_close",
        namespace["real_trade_lifecycle_missing_from_bots_close_v15_route"],
        methods=["POST"],
    )
    app.after_request(namespace["memory_stabilizer_after_request"])
    return app.test_client()


def _identity(namespace, **updates):
    values = {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "broker_order_id": BROKER_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
    }
    values.update(updates)
    return namespace["_rtlm_v14_missing_close_identity"](**values)


def _route_params(**updates):
    params = {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "broker_order_id": BROKER_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
    }
    params.update(updates)
    return params


def _post_payload(**updates):
    payload = _route_params()
    payload["ack"] = "POSITION_CLOSED_CONFIRMED"
    payload.update(updates)
    return payload


def _auth_headers(**updates):
    headers = {"X-Execution-Auth-Token": "TEST-EXECUTION-AUTH"}
    headers.update(updates)
    return headers


def _assert_no_store(response):
    assert response.headers["Cache-Control"] == (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Vary"] == "X-Execution-Auth-Token"


def _isolated_trade_registry(tmp_path, filename):
    """Load a private Registry module immune to session-level main threads."""

    module_name = (
        f"_test_trade_registry_{id(tmp_path)}_"
        + str(filename).replace(".", "_").replace("-", "_")
    )
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "trade_registry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TRADE_REGISTRY_FILE = str(tmp_path / filename)
    module.TRADE_REGISTRY_LEGACY_FILE = str(tmp_path / "missing-legacy.json")
    module._observe_shadow_registry_snapshot = lambda *_args, **_kwargs: None
    return module


def test_xrp_preview_resolves_exact_missing_trade_without_any_write():
    ns, registry, broker, _ = _harness()
    before = copy.deepcopy(registry.state)

    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(), _identity(ns), close_registry=False, ack=None
    )

    close = result["missing_from_bots_close"]
    assert result["status"] == "MISSING_FROM_BOTS_EXACT_CLOSE_READY"
    assert close["status"] == "MISSING_FROM_BOTS_EXACT_OPEN_MATCH_READY"
    assert close["safe_to_close"] is True
    assert close["exact_open_match_count"] == 1
    assert close["committed"] is False
    assert close["registry_write"] is False
    assert close["write_executed"] is False
    assert close["registry_write_may_have_occurred"] is False
    assert close["persistence_confirmed"] is False
    assert close["broker_called"] is False
    assert close["broker_writer_called"] is False
    assert registry.state == before
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_commit_requires_exact_ack_and_fresh_flat_then_closes_only_xrp():
    decoy = _base_trade(
        trade_id="FALCON:FALCON15:XRPUSDT:LONG:OTHER",
        lifecycle_id="LC-OTHER",
        client_order_id="CLIENT-OTHER",
        broker_order_id="ORDER-OTHER",
    )
    open_trades = {TRADE_ID: _base_trade(), decoy["trade_id"]: decoy}
    ns, registry, broker, _ = _harness(open_trades=open_trades)

    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        _identity(ns),
        close_registry=True,
        ack="POSITION_CLOSED_CONFIRMED",
    )

    close = result["registry_close"]
    assert result["status"] == "MISSING_FROM_BOTS_REGISTRY_CLOSED"
    assert close["status"] == "MISSING_FROM_BOTS_REGISTRY_CLOSED"
    assert close["committed"] is True
    assert close["registry_write"] is True
    assert close["write_executed"] is True
    assert close["persistence_confirmation"]["confirmed"] is True
    assert close["fresh_position_revalidation"] == {
        "ok": True,
        "response_received": True,
        "response_shape_valid": True,
        "position_rows_valid": True,
        "position_absence_confirmed": True,
        "count": 0,
        "error": None,
    }
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []
    assert list(registry.state["open_trades"]) == [decoy["trade_id"]]
    assert registry.state["open_trades"][decoy["trade_id"]] == decoy
    assert len(registry.state["closed_trades"]) == 1
    assert registry.state["closed_trades"][0]["trade_id"] == TRADE_ID
    assert len(registry.close_calls) == 1
    called_trade_id, kwargs = registry.close_calls[0]
    assert called_trade_id == TRADE_ID
    assert kwargs["reason"] == "BROKER_POSITION_NOT_FOUND_CONFIRMED"
    assert kwargs["registry_mode"] == "REAL"
    assert kwargs["expected_open_trade_id_count"] == 1
    assert kwargs["expected_identity"] == {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "order_id": BROKER_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "status": "MISSING_FROM_BOTS",
    }


@pytest.mark.parametrize(
    "field",
    [
        "trade_id",
        "lifecycle_id",
        "client_order_id",
        "broker_order_id",
        "symbol",
        "side",
        "bot",
        "setup",
        "registry_mode",
        "execution_mode",
    ],
)
def test_each_required_identity_field_is_fail_closed_when_absent(field):
    ns, registry, broker, _ = _harness()
    identity = _identity(ns)
    identity[field] = ""

    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        identity,
        close_registry=True,
        ack="POSITION_CLOSED_CONFIRMED",
    )["registry_close"]

    assert result["status"] == "MISSING_FROM_BOTS_STRONG_IDENTITY_REQUIRED"
    assert field in result["missing_identity_fields"]
    assert result["committed"] is False
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("trade_id", "FALCON:FALCON15:XRPUSDT:LONG:WRONG"),
        ("lifecycle_id", "LC-WRONG"),
        ("client_order_id", "CLIENT-WRONG"),
        ("broker_order_id", "ORDER-WRONG"),
        ("symbol", "SOLUSDT"),
        ("side", "SHORT"),
        ("bot", "TURTLE"),
        ("setup", "FALCON60"),
        ("registry_mode", "VERIFY"),
        ("execution_mode", "PAPER"),
        ("status", "OPEN"),
    ],
)
def test_any_record_identity_mode_or_status_divergence_yields_zero_exact_matches(
    field, bad_value
):
    trade = _base_trade(**{field: bad_value})
    ns, registry, broker, _ = _harness(open_trades={TRADE_ID: trade})

    resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
        _identity(ns), lifecycle=_known_flat_lifecycle()
    )

    assert resolution["status"] in {
        "MISSING_FROM_BOTS_OPEN_TRADE_ID_COUNT_INVALID",
        "MISSING_FROM_BOTS_EXACT_OPEN_COUNT_INVALID",
    }
    assert resolution["exact_open_match_count"] == 0
    assert resolution["safe_to_close"] is False
    assert registry.close_calls == []
    assert broker.writer_calls == []


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("trade_id", "TRADE-METADATA-CONFLICT"),
        ("lifecycle_id", "LC-METADATA-CONFLICT"),
        ("client_order_id", "CLIENT-METADATA-CONFLICT"),
        ("broker_order_id", "ORDER-METADATA-CONFLICT"),
        ("symbol", "SOLUSDT"),
        ("side", "SHORT"),
        ("bot", "TURTLE"),
        ("setup", "FALCON60"),
        ("registry_mode", "VERIFY"),
        ("execution_mode", "PAPER"),
        ("status", "OPEN"),
    ],
)
def test_conflicting_metadata_cannot_be_hidden_by_correct_top_level_value(
    field, bad_value
):
    trade = _base_trade(
        metadata={
            "source": "test_real_trade_lifecycle_missing_from_bots_close_v1",
            field: bad_value,
        }
    )
    ns, registry, broker, _ = _harness(open_trades={TRADE_ID: trade})

    resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
        _identity(ns), lifecycle=_known_flat_lifecycle()
    )

    assert resolution["status"] in {
        "MISSING_FROM_BOTS_OPEN_TRADE_ID_COUNT_INVALID",
        "MISSING_FROM_BOTS_EXACT_OPEN_COUNT_INVALID",
    }
    assert resolution["exact_open_match_count"] == 0
    assert resolution["safe_to_close"] is False
    assert registry.close_calls == []
    assert broker.writer_calls == []


def test_zero_and_two_exact_open_records_are_both_fail_closed():
    for open_trades, expected_total, expected_exact in (
        ({}, 0, 0),
        ([_base_trade(), copy.deepcopy(_base_trade())], 2, 2),
    ):
        ns, registry, broker, _ = _harness(open_trades=open_trades)
        resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
            _identity(ns), lifecycle=_known_flat_lifecycle()
        )
        assert resolution["status"] == "MISSING_FROM_BOTS_OPEN_TRADE_ID_COUNT_INVALID"
        assert resolution["registry_open_total"] == expected_total
        assert resolution["exact_open_match_count"] == expected_exact
        assert resolution["safe_to_close"] is False
        assert registry.close_calls == []
        assert broker.writer_calls == []


@pytest.mark.parametrize(
    "lifecycle",
    [
        _known_flat_lifecycle(
            position_found=True,
            safety_check={
                "positions_fetch_ok": True,
                "positions_response_received": True,
                "positions_response_shape_valid": True,
                "position_rows_valid": True,
                "position_absence_confirmed": False,
                "position_count": 1,
            },
        ),
        _known_flat_lifecycle(
            position_found=None,
            safety_check={
                "positions_fetch_ok": False,
                "positions_response_received": False,
                "positions_response_shape_valid": False,
                "position_rows_valid": False,
                "position_absence_confirmed": False,
                "position_count": None,
            },
        ),
    ],
)
def test_preview_blocks_when_position_is_present_or_reader_is_unknown(lifecycle):
    ns, registry, broker, _ = _harness()
    resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
        _identity(ns), lifecycle=lifecycle
    )
    assert resolution["status"] == "BROKER_POSITION_LOOKUP_NOT_CONFIRMED"
    assert resolution["safe_to_close"] is False
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert broker.writer_calls == []


@pytest.mark.parametrize(
    "fresh_payload",
    [
        _flat_reader_payload(
            ok=False,
            response_received=False,
            position_absence_confirmed=False,
            count=None,
            error="position reader unavailable",
        ),
        _flat_reader_payload(
            position_absence_confirmed=False,
            count=1,
            positions=[{"symbol": "XRPUSDT", "side": "LONG", "contracts": 9}],
        ),
    ],
)
def test_commit_revalidation_blocks_unknown_or_still_present_position(fresh_payload):
    ns, registry, broker, _ = _harness(position_payload=fresh_payload)
    before = copy.deepcopy(registry.state)

    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        _identity(ns),
        close_registry=True,
        ack="POSITION_CLOSED_CONFIRMED",
    )["registry_close"]

    assert result["status"] == "BROKER_POSITION_LOOKUP_NOT_CONFIRMED"
    assert result["safe_to_close"] is False
    assert result["committed"] is False
    assert registry.state == before
    assert registry.close_calls == []
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []


@pytest.mark.parametrize(
    "ack",
    [None, "", "CLOSE_CONFIRMED", "CLOSED_CONFIRMED", "position_closed_confirmed"],
)
def test_commit_rejects_missing_legacy_or_nonexact_ack(ack):
    ns, registry, broker, _ = _harness()
    before = copy.deepcopy(registry.state)

    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        _identity(ns),
        close_registry=True,
        ack=ack,
    )["registry_close"]

    assert result["status"] == "ACK_REQUIRED"
    assert result["required_ack"] == "POSITION_CLOSED_CONFIRMED"
    assert result["committed"] is False
    assert registry.state == before
    assert registry.close_calls == []
    # Invalid ACK is rejected before the commit revalidation read.
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_same_symbol_side_decoy_never_counts_as_strong_identity_match():
    decoy = _base_trade(
        trade_id="FALCON:FALCON15:XRPUSDT:LONG:OLD",
        lifecycle_id="LC-OLD",
        client_order_id="CLIENT-OLD",
        broker_order_id="ORDER-OLD",
    )
    ns, registry, broker, _ = _harness(
        open_trades={TRADE_ID: _base_trade(), decoy["trade_id"]: decoy}
    )

    resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
        _identity(ns), lifecycle=_known_flat_lifecycle()
    )

    assert resolution["registry_open_total"] == 2
    assert resolution["exact_open_match_count"] == 1
    assert resolution["candidate"]["trade_id"] == TRADE_ID
    assert resolution["candidate"]["lifecycle_id"] == LIFECYCLE_ID
    assert registry.close_calls == []
    assert broker.writer_calls == []


def test_duplicate_trade_id_under_alternate_registry_key_is_fail_closed():
    duplicate = copy.deepcopy(_base_trade())
    ns, registry, broker, _ = _harness(
        open_trades={TRADE_ID: _base_trade(), "CORRUPT-ALTERNATE-KEY": duplicate}
    )

    resolution = ns["_rtlm_v14_resolve_missing_from_bots_close"](
        _identity(ns), lifecycle=_known_flat_lifecycle()
    )

    assert resolution["status"] == "MISSING_FROM_BOTS_OPEN_TRADE_ID_COUNT_INVALID"
    assert resolution["open_trade_id_match_count"] == 2
    assert resolution["safe_to_close"] is False
    assert registry.close_calls == []
    assert broker.writer_calls == []


def test_route_trims_strong_identity_and_propagates_monitor_dimensions():
    params = _route_params(
        trade_id=f"  {TRADE_ID}  ",
        lifecycle_id=f"  {LIFECYCLE_ID}  ",
        client_order_id=f"  {CLIENT_ORDER_ID}  ",
        broker_order_id=f"  {BROKER_ORDER_ID}  ",
        symbol=" xrp/usdt ",
        side=" long ",
        bot=" falcon ",
        setup=" falcon15 ",
    )
    ns, registry, broker, build_calls = _harness(request_args=params)

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    close = result["missing_from_bots_close"]
    assert close["safe_to_close"] is True
    assert close["identity"] == {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "broker_order_id": BROKER_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
    }
    assert build_calls == []
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []


@pytest.mark.parametrize("missing_mode", ["registry_mode", "execution_mode"])
def test_route_requires_explicit_real_live_modes_without_read_or_write(missing_mode):
    params = _route_params()
    params.pop(missing_mode)
    ns, registry, broker, build_calls = _harness(request_args=params)

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["ok"] is False
    assert result["status"] == "MISSING_FROM_BOTS_STRONG_IDENTITY_REQUIRED"
    assert missing_mode in result["registry_close"]["missing_identity_fields"]
    assert build_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert registry.close_calls == []


def test_legacy_snapshot_commit_query_is_blocked_before_builder_or_write():
    ns, registry, broker, build_calls = _harness(
        request_args={
            "symbol": "XRPUSDT",
            "side": "LONG",
            "bot": "FALCON",
            "setup": "FALCON15",
            "commit": "true",
        }
    )

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["ok"] is False
    assert result["status"] == "GET_PREVIEW_ONLY"
    assert result["blocked_mutation_parameters"] == ["commit"]
    assert build_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_route_blocks_conflicting_mutation_parameter_before_build_or_write():
    params = _route_params(close_registry="true", ack="POSITION_CLOSED_CONFIRMED")
    params.update({"commit": "true", "repair_registry": "true"})
    ns, registry, broker, build_calls = _harness(request_args=params)
    before = copy.deepcopy(registry.state)

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["status"] == "GET_PREVIEW_ONLY"
    assert result["blocked_mutation_parameters"] == [
        "close_registry",
        "commit",
        "repair_registry",
    ]
    assert result["required_close_route"] == "/realtradelifecycle/close"
    assert result["registry_write"] is False
    assert result["write_executed"] is False
    assert result["broker_called"] is False
    assert result["broker_writer_called"] is False
    assert build_calls == []
    assert registry.state == before
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_get_close_registry_is_blocked_before_identity_or_any_read():
    ns, registry, broker, build_calls = _harness(
        request_args={
            "close_registry": "true",
            "ack": "POSITION_CLOSED_CONFIRMED",
        }
    )

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["ok"] is False
    assert result["status"] == "GET_PREVIEW_ONLY"
    assert result["blocked_mutation_parameters"] == ["close_registry"]
    assert build_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_path_and_query_identity_conflict_is_blocked_before_any_read():
    ns, registry, broker, build_calls = _harness(
        request_args=_route_params(symbol="SOLUSDT")
    )

    result = _route_payload(
        ns["real_trade_lifecycle_monitor_v1_route"](
            symbol="XRPUSDT", side="LONG"
        )
    )

    assert result["status"] == "PATH_QUERY_IDENTITY_CONFLICT"
    assert result["conflicting_fields"] == ["symbol"]
    assert build_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


@pytest.mark.parametrize("alias", ["1", "yes", "on", "commit"])
def test_get_close_registry_rejects_every_truthy_alias(alias):
    ns, registry, broker, build_calls = _harness(
        request_args=_route_params(
            close_registry=alias, ack="POSITION_CLOSED_CONFIRMED"
        )
    )

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["ok"] is False
    assert result["status"] == "GET_PREVIEW_ONLY"
    assert result["blocked_mutation_parameters"] == ["close_registry"]
    assert result["write_executed"] is False
    assert build_calls == []
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_mutating_close_is_rejected_on_every_get_alias_route():
    ns, registry, broker, build_calls = _harness(
        request_args=_route_params(
            close_registry="true", ack="POSITION_CLOSED_CONFIRMED"
        ),
        request_path="/lifecyclemonitor",
    )

    result = _route_payload(ns["real_trade_lifecycle_monitor_v1_route"]())

    assert result["status"] == "GET_PREVIEW_ONLY"
    assert result["required_close_route"] == "/realtradelifecycle/close"
    assert build_calls == []
    assert registry.close_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []


def test_post_commit_route_uses_only_position_reader_and_never_network_or_broker_writer(
    monkeypatch,
):
    payload = _post_payload()
    ns, registry, broker, build_calls = _harness(request_json=payload)
    monkeypatch.setattr(
        socket,
        "socket",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )

    result = _route_payload(
        ns["real_trade_lifecycle_missing_from_bots_close_v15_route"]()
    )

    assert result["status"] == "MISSING_FROM_BOTS_REGISTRY_CLOSED"
    assert result["registry_close"]["broker_called"] is True
    assert result["registry_close"]["broker_reader_call_count"] == 2
    assert result["registry_close"]["broker_writer_called"] is False
    assert build_calls == []
    assert broker.position_reads == [("XRPUSDT", "LONG"), ("XRPUSDT", "LONG")]
    assert broker.writer_calls == []
    assert len(registry.close_calls) == 1


def test_false_writer_success_is_blocked_by_registry_readback():
    ns, registry, broker, _ = _harness()
    before = copy.deepcopy(registry.state)

    def false_success(trade_id, **kwargs):
        registry.close_calls.append((trade_id, copy.deepcopy(kwargs)))
        return {"ok": True, "action": "TRADE_CLOSED", "trade_id": trade_id}

    registry.close_trade = false_success
    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        _identity(ns),
        close_registry=True,
        ack="POSITION_CLOSED_CONFIRMED",
    )

    close = result["registry_close"]
    assert result["ok"] is False
    assert result["status"] == "REGISTRY_CLOSE_PERSISTENCE_UNCONFIRMED"
    assert close["committed"] is False
    assert close["registry_write_attempted"] is True
    assert close["registry_write"] is None
    assert close["write_executed"] is None
    assert close["registry_write_may_have_occurred"] is True
    assert close["persistence_confirmed"] is False
    assert close["persistence_confirmation"]["confirmed"] is False
    assert close["persistence_confirmation"]["open_trade_id_match_count"] == 1
    assert registry.state == before
    assert broker.writer_calls == []


def test_successful_write_with_readback_error_reports_unknown_not_false():
    ns, registry, broker, _ = _harness()
    original_reader = registry.load_registry_read_only

    def fail_third_read():
        if registry.read_calls >= 2:
            raise OSError("readback unavailable")
        return original_reader()

    registry.load_registry_read_only = fail_third_read
    result = ns["_rtlm_v14_apply_missing_from_bots_close"](
        _known_flat_lifecycle(),
        _identity(ns),
        close_registry=True,
        ack="POSITION_CLOSED_CONFIRMED",
    )

    close = result["registry_close"]
    assert result["ok"] is False
    assert result["status"] == "REGISTRY_CLOSE_PERSISTENCE_UNCONFIRMED"
    assert close["committed"] is False
    assert close["registry_write_attempted"] is True
    assert close["registry_write"] is None
    assert close["write_executed"] is None
    assert close["registry_write_may_have_occurred"] is True
    assert close["persistence_confirmation"]["status"] == "TRADE_REGISTRY_READBACK_ERROR"
    assert TRADE_ID not in registry.state["open_trades"]
    assert len(registry.state["closed_trades"]) == 1
    assert broker.writer_calls == []


def test_invalid_position_response_shape_can_never_confirm_flat():
    node = next(
        copy.deepcopy(item)
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_pesc_v1_fetch_positions"
    )
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    for raw, expected_shape_valid in (
        ({"ok": False, "error": "upstream failure"}, False),
        ([None], True),
        ([{"ok": False}], True),
        ([{"symbol": "XRPUSDT", "positionAmt": 9}], True),
    ):
        namespace = {
            "central_broker": object(),
            "_pesc_v1_norm_symbol": _norm_symbol,
            "_pesc_v1_norm_side": _norm_side,
            "_pesc_v1_broker_call": lambda *_args, _raw=raw, **_kwargs: (
                copy.deepcopy(_raw),
                None,
            ),
            "_pesc_v1_slim_position": lambda item: {
                "symbol": _norm_symbol(item.get("symbol")),
                "side": _norm_side(item.get("side")),
                "contracts": abs(float(item.get("positionAmt") or 0)),
                "notional": abs(float(item.get("notional") or 0)),
            },
            "_pesc_v1_market_symbol": lambda value: value,
        }
        exec(compile(tree, "<isolated-position-shape-check>", "exec"), namespace)

        result = namespace["_pesc_v1_fetch_positions"]("XRPUSDT", "LONG")

        assert result["ok"] is False
        assert result["response_received"] is True
        assert result["response_shape_valid"] is expected_shape_valid
        assert result["position_absence_confirmed"] is False
        assert result["count"] == 0


def test_valid_empty_position_list_is_the_only_flat_evidence_shape():
    node = next(
        copy.deepcopy(item)
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_pesc_v1_fetch_positions"
    )
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    namespace = {
        "central_broker": object(),
        "_pesc_v1_norm_symbol": _norm_symbol,
        "_pesc_v1_norm_side": _norm_side,
        "_pesc_v1_broker_call": lambda *_args, **_kwargs: ([], None),
        "_pesc_v1_slim_position": lambda item: item,
        "_pesc_v1_market_symbol": lambda value: value,
    }
    exec(compile(tree, "<isolated-position-empty-check>", "exec"), namespace)

    result = namespace["_pesc_v1_fetch_positions"]("XRPUSDT", "LONG")

    assert result["ok"] is True
    assert result["response_shape_valid"] is True
    assert result["position_rows_valid"] is True
    assert result["position_absence_confirmed"] is True


@pytest.mark.parametrize(
    "raw,expected_shape_valid",
    [
        (None, False),
        ({}, False),
        (False, False),
        ((), False),
        ([], True),
    ],
)
def test_strong_close_reads_raw_exchange_and_never_trusts_lossy_broker_wrapper(
    raw, expected_shape_valid
):
    node = next(
        copy.deepcopy(item)
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_pesc_v1_fetch_positions"
    )
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)
    calls = {"wrapper": 0, "raw": 0}

    class ExchangeProbe:
        def fetch_positions(self, markets=None):
            calls["raw"] += 1
            assert markets == ["XRPUSDT"]
            return copy.deepcopy(raw)

    class BrokerProbe:
        @staticmethod
        def get_positions():
            calls["wrapper"] += 1
            return []

        @staticmethod
        def exchange():
            return ExchangeProbe()

    namespace = {
        "central_broker": BrokerProbe(),
        "BROKER_IMPORT_ERROR": None,
        "_pesc_v1_norm_symbol": _norm_symbol,
        "_pesc_v1_norm_side": _norm_side,
        "_pesc_v1_float": lambda value, default=None: (
            float(value) if value not in (None, "") else default
        ),
        "_pesc_v1_broker_call": lambda *_args, **_kwargs: pytest.fail(
            "lossy Broker wrapper must not be called"
        ),
        "_pesc_v1_slim_position": lambda item: item,
        "_pesc_v1_market_symbol": lambda value: value,
    }
    exec(compile(tree, "<isolated-position-raw-check>", "exec"), namespace)

    result = namespace["_pesc_v1_fetch_positions"](
        "XRPUSDT", "LONG", strict_raw_exchange=True
    )

    assert calls == {"wrapper": 0, "raw": 1}
    assert result["response_shape_valid"] is expected_shape_valid
    assert result["position_absence_confirmed"] is (raw == [])
    assert result["ok"] is (raw == [])


@pytest.mark.parametrize(
    "raw,expected_ok,expected_count,expected_invalid_quantity",
    [
        ([{"symbol": "XRPUSDT", "side": "LONG"}], False, 0, 1),
        ([{"symbol": "XRPUSDT", "side": "LONG", "contracts": False}], False, 0, 1),
        ([{"symbol": "XRPUSDT", "side": "LONG", "contracts": "nan"}], False, 0, 1),
        ([{"symbol": "XRPUSDT", "side": "LONG", "contracts": "inf"}], False, 0, 1),
        (
            [
                {
                    "symbol": "XRPUSDT",
                    "side": "LONG",
                    "contracts": "N/A",
                    "info": {"positionAmt": "9"},
                }
            ],
            False,
            0,
            1,
        ),
        (
            [
                {
                    "symbol": "XRPUSDT",
                    "side": "LONG",
                    "contracts": 0,
                    "info": {"positionAmt": 9},
                }
            ],
            True,
            1,
            0,
        ),
        ([{"symbol": "XRPUSDT", "side": "LONG", "contracts": 0}], True, 0, 0),
        ([{"symbol": "XRPUSDT", "side": "LONG", "contracts": 9}], True, 1, 0),
    ],
)
def test_strong_close_requires_factual_parseable_position_quantity(
    raw, expected_ok, expected_count, expected_invalid_quantity
):
    node = next(
        copy.deepcopy(item)
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_pesc_v1_fetch_positions"
    )
    tree = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(tree)

    class ExchangeProbe:
        def fetch_positions(self, markets=None):
            assert markets == ["XRPUSDT"]
            return copy.deepcopy(raw)

    class BrokerProbe:
        @staticmethod
        def exchange():
            return ExchangeProbe()

    def strict_float(value, default=None):
        try:
            if value is None or str(value).strip() == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def slim(item):
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        contracts = strict_float(item.get("contracts"), 0.0)
        notional = strict_float(item.get("notional"), 0.0)
        return {
            "symbol": _norm_symbol(item.get("symbol") or info.get("symbol")),
            "side": _norm_side(item.get("side") or info.get("positionSide")),
            "contracts": abs(float(contracts or 0.0)),
            "notional": abs(float(notional or 0.0)),
        }

    namespace = {
        "central_broker": BrokerProbe(),
        "BROKER_IMPORT_ERROR": None,
        "_pesc_v1_norm_symbol": _norm_symbol,
        "_pesc_v1_norm_side": _norm_side,
        "_pesc_v1_float": strict_float,
        "_pesc_v1_broker_call": lambda *_args, **_kwargs: pytest.fail(
            "lossy Broker wrapper must not be called"
        ),
        "_pesc_v1_slim_position": slim,
        "_pesc_v1_market_symbol": lambda value: value,
    }
    exec(compile(tree, "<isolated-position-quantity-check>", "exec"), namespace)

    result = namespace["_pesc_v1_fetch_positions"](
        "XRPUSDT", "LONG", strict_raw_exchange=True
    )

    assert result["ok"] is expected_ok
    assert result["count"] == expected_count
    assert (
        result["invalid_position_quantity_count"]
        == expected_invalid_quantity
    )
    assert result["position_absence_confirmed"] is (
        expected_ok and expected_count == 0
    )


def test_post_ack_failure_is_top_level_blocked_and_never_writes():
    ns, registry, broker, build_calls = _harness(
        request_json=_post_payload(ack="CLOSE_CONFIRMED")
    )

    result = _route_payload(
        ns["real_trade_lifecycle_missing_from_bots_close_v15_route"]()
    )

    assert result["ok"] is False
    assert result["status"] == "ACK_REQUIRED"
    assert result["registry_write"] is False
    assert result["write_executed"] is False
    assert build_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.close_calls == []


def test_route_remains_get_only_and_exposes_no_order_writer_call():
    node = next(
        item
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "real_trade_lifecycle_monitor_v1_route"
    )
    decorators = [ast.unparse(item) for item in node.decorator_list]
    assert decorators == [
        "app.route('/realtradelifecycle', methods=['GET'])",
        "app.route('/realtradelifecycle/<symbol>/<side>', methods=['GET'])",
        "app.route('/lifecyclemonitor', methods=['GET'])",
        "app.route('/lifecyclemonitor/<symbol>/<side>', methods=['GET'])",
        "app.route('/trade/lifecycle', methods=['GET'])",
    ]
    source = ast.unparse(node)
    for forbidden in (
        "place_market_order",
        "create_order",
        "create_disaster_stop_order",
        "managed_close_position_market",
        "close_position_market",
        "cancel_order",
    ):
        assert forbidden not in source


def test_close_route_is_post_only_and_exposes_no_broker_writer_call():
    node = next(
        item
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "real_trade_lifecycle_missing_from_bots_close_v15_route"
    )
    assert [ast.unparse(item) for item in node.decorator_list] == [
        "app.route('/realtradelifecycle/close', methods=['POST'])"
    ]
    source = ast.unparse(node)
    for forbidden in (
        "place_market_order",
        "create_order",
        "create_disaster_stop_order",
        "managed_close_position_market",
        "close_position_market",
        "cancel_order",
    ):
        assert forbidden not in source


def test_http_get_strong_preview_requires_exact_header_and_never_writes():
    ns, registry, broker, build_calls = _harness()
    before = copy.deepcopy(registry.state)
    client = _flask_client_for_harness(ns)

    response = client.get(
        "/realtradelifecycle",
        query_string=_route_params(),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    _assert_no_store(response)
    payload = response.get_json()
    assert payload["status"] == "MISSING_FROM_BOTS_EXACT_CLOSE_READY"
    assert payload["read_only"] is True
    assert payload["registry_write"] is False
    assert payload["write_executed"] is False
    assert "candidate_registry_key" not in payload
    assert "identity_comparison" not in payload
    assert registry.state == before
    assert registry.close_calls == []
    assert registry.save_calls == 0
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []
    assert build_calls == []
    assert broker.auth_calls == [
        {"args": (), "kwargs": {"allow_env_fallback": False}}
    ]


def test_http_get_reports_only_safe_identity_divergence_for_single_candidate():
    sentinel = "DO_NOT_EXPOSE_REGISTRY_METADATA"
    candidate = _base_trade()
    candidate.pop("client_order_id")
    candidate["metadata"] = {
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:STALE",
        "secret": sentinel,
        "token": "PRIVATE-TOKEN",
        "path": r"C:\\private\\trade_registry.json",
    }
    ns, registry, broker, _ = _harness(
        open_trades={TRADE_ID: candidate}
    )
    client = _flask_client_for_harness(ns)

    response = client.get(
        "/realtradelifecycle",
        query_string=_route_params(),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    _assert_no_store(response)
    payload = response.get_json()
    assert payload["status"] == "MISSING_FROM_BOTS_EXACT_OPEN_COUNT_INVALID"
    assert payload["registry_close"]["open_trade_id_match_count"] == 1
    assert payload["registry_close"]["exact_open_match_count"] == 0
    assert payload["candidate_registry_key"] == TRADE_ID
    comparison = payload["identity_comparison"]
    assert set(comparison) == {
        "trade_id",
        "lifecycle_id",
        "client_order_id",
        "broker_order_id",
        "symbol",
        "side",
        "bot",
        "setup",
        "registry_mode",
        "execution_mode",
        "status",
    }
    assert comparison["trade_id"] == {
        "expected": TRADE_ID,
        "primary_value": TRADE_ID,
        "all_current_values": [TRADE_ID],
        "result": "MATCH",
    }
    assert comparison["lifecycle_id"] == {
        "expected": LIFECYCLE_ID,
        "primary_value": LIFECYCLE_ID,
        "all_current_values": sorted(
            [LIFECYCLE_ID, "CENTRAL-FALCON-LIFECYCLE:STALE"]
        ),
        "result": "CONFLICT",
    }
    assert comparison["client_order_id"] == {
        "expected": CLIENT_ORDER_ID,
        "primary_value": None,
        "all_current_values": [],
        "result": "MISSING",
    }
    for field in (
        "broker_order_id",
        "symbol",
        "side",
        "bot",
        "setup",
        "registry_mode",
        "execution_mode",
        "status",
    ):
        assert comparison[field]["result"] == "MATCH"
    serialized = response.get_data(as_text=True)
    assert "metadata" not in serialized
    assert sentinel not in serialized
    assert "PRIVATE-TOKEN" not in serialized
    assert "trade_registry.json" not in serialized
    assert '"_trade_id_match_record"' not in serialized
    assert '"_trade_id_match_values"' not in serialized
    assert registry.read_calls == 1
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert registry.close_calls == []
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []


def test_http_post_does_not_expose_get_identity_divergence_diagnostic():
    candidate = _base_trade(lifecycle_id="WRONG-LIFECYCLE")
    ns, registry, broker, _ = _harness(
        open_trades={TRADE_ID: candidate}
    )
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["status"] == "MISSING_FROM_BOTS_EXACT_OPEN_COUNT_INVALID"
    assert "candidate_registry_key" not in payload
    assert "identity_comparison" not in payload
    assert registry.close_calls == []
    assert registry.save_calls == 0
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []


def test_http_get_strong_preview_without_token_is_403_before_private_reads():
    ns, registry, broker, build_calls = _harness(request_headers={})
    client = _flask_client_for_harness(ns)

    response = client.get(
        "/realtradelifecycle", query_string=_route_params()
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert build_calls == []


def test_http_get_rejects_json_auth_material_before_legacy_preview_builder():
    ns, registry, broker, build_calls = _harness(request_headers={})
    client = _flask_client_for_harness(ns)

    response = client.get(
        "/realtradelifecycle",
        json={"auth": {"token": "TEST-EXECUTION-AUTH"}},
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_HEADER_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert build_calls == []


@pytest.mark.parametrize(
    "parameter",
    [
        "close_registry",
        "mark_closed",
        "commit",
        "update_registry",
        "repair_registry",
        "repair",
        "persist_registry",
        "persist",
        "registry_persistence_rebuild",
        "rebuild_registry",
        "restore_registry",
        "restore_from_snapshot",
    ],
)
def test_http_get_blocks_every_legacy_mutation_alias_before_any_read(parameter):
    ns, registry, broker, build_calls = _harness(request_headers={})
    client = _flask_client_for_harness(ns)

    response = client.get(
        "/realtradelifecycle", query_string={parameter: "true"}
    )

    assert response.status_code == 405
    _assert_no_store(response)
    payload = response.get_json()
    assert payload["status"] == "GET_PREVIEW_ONLY"
    assert payload["blocked_mutation_parameters"] == [parameter]
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert registry.save_calls == 0
    assert build_calls == []


def test_http_post_without_token_is_403_before_any_read_or_write():
    ns, registry, broker, build_calls = _harness(request_headers={})
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close", json=_post_payload()
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []
    assert build_calls == []


def test_http_post_wrong_token_is_403_before_any_read_or_write():
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers={"X-Execution-Auth-Token": "WRONG"},
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_INVALID"
    assert broker.auth_calls == [
        {"args": (), "kwargs": {"allow_env_fallback": False}}
    ]
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


@pytest.mark.parametrize(
    "query",
    [
        {"token": "TEST-EXECUTION-AUTH"},
        {"execution_auth_token": "TEST-EXECUTION-AUTH"},
    ],
)
def test_http_post_rejects_token_in_query_even_with_valid_header(query):
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        query_string=query,
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_HEADER_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


@pytest.mark.parametrize(
    "auth_material",
    [
        {"execution_auth_token": "TEST-EXECUTION-AUTH"},
        {"auth": {"token": "TEST-EXECUTION-AUTH"}},
        {"execution_auth": {"authorization": "TEST-EXECUTION-AUTH"}},
    ],
)
def test_http_post_rejects_token_in_json_even_with_valid_header(auth_material):
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)
    body = _post_payload()
    body.update(auth_material)

    response = client.post(
        "/realtradelifecycle/close", json=body, headers=_auth_headers()
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_HEADER_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer TEST-EXECUTION-AUTH"},
        {"X-Execution-Auth": "TEST-EXECUTION-AUTH"},
        {
            "X-Execution-Auth-Token": "TEST-EXECUTION-AUTH",
            "Authorization": "Bearer TEST-EXECUTION-AUTH",
        },
    ],
)
def test_http_post_rejects_alternative_auth_headers(headers):
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close", json=_post_payload(), headers=headers
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_HEADER_REQUIRED"
    assert broker.auth_calls == []
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_http_post_rejects_non_header_source_reported_by_resolver():
    ns, registry, broker, _ = _harness(
        auth_result={
            "ok": True,
            "status": "EXECUTION_AUTH_OK",
            "matched_source": "request.json.execution_auth_token",
        }
    )
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 403
    _assert_no_store(response)
    assert response.get_json()["status"] == "EXECUTION_AUTH_INVALID"
    assert broker.auth_calls == [
        {"args": (), "kwargs": {"allow_env_fallback": False}}
    ]
    assert broker.position_reads == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_http_post_identity_must_come_from_json_not_query():
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        query_string=_route_params(),
        json={"ack": "POSITION_CLOSED_CONFIRMED"},
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    _assert_no_store(response)
    assert response.get_json()["status"] == "POST_QUERY_PARAMETERS_NOT_SUPPORTED"
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_http_post_authenticated_exact_identity_closes_only_xrp_once():
    decoy_id = "FALCON:FALCON15:SOLUSDT:LONG"
    open_trades = {
        TRADE_ID: _base_trade(),
        decoy_id: _base_trade(
            trade_id=decoy_id,
            lifecycle_id="CENTRAL-FALCON-LIFECYCLE:SOL-DECOY",
            client_order_id="FALCON-LIVE-SOL-DECOY",
            broker_order_id="SOL-DECOY-ORDER",
            symbol="SOLUSDT",
        ),
    }
    ns, registry, broker, build_calls = _harness(open_trades=open_trades)
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    _assert_no_store(response)
    payload = response.get_json()
    assert payload["status"] == "MISSING_FROM_BOTS_REGISTRY_CLOSED"
    assert payload["registry_close"]["committed"] is True
    assert list(registry.state["open_trades"]) == [decoy_id]
    assert registry.state["open_trades"][decoy_id]["symbol"] == "SOLUSDT"
    assert len(registry.state["closed_trades"]) == 1
    assert registry.state["closed_trades"][0]["trade_id"] == TRADE_ID
    assert len(registry.close_calls) == 1
    assert broker.position_reads == [("XRPUSDT", "LONG"), ("XRPUSDT", "LONG")]
    assert broker.writer_calls == []
    assert build_calls == []
    assert broker.auth_calls == [
        {"args": (), "kwargs": {"allow_env_fallback": False}}
    ]


def test_http_post_live_position_present_remains_fail_closed_without_write():
    position = {
        "symbol": "XRPUSDT",
        "side": "LONG",
        "contracts": 9.0,
    }
    ns, registry, broker, _ = _harness(
        position_payload=_flat_reader_payload(
            position_absence_confirmed=False,
            count=1,
            positions=[position],
        )
    )
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    _assert_no_store(response)
    assert response.get_json()["status"] == "BROKER_POSITION_LOOKUP_NOT_CONFIRMED"
    assert broker.position_reads == [("XRPUSDT", "LONG")]
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_http_post_wrong_ack_returns_400_without_factual_or_registry_reads():
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(ack="WRONG"),
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    _assert_no_store(response)
    assert response.get_json()["status"] == "ACK_REQUIRED"
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_http_responses_sanitize_internal_errors_paths_and_registry_payloads():
    sentinel = "ULTRA_PRIVATE_SENTINEL"
    private_path = r"C:\\private\\central\\registry.json"
    ns, registry, broker, _ = _harness()

    def unsafe_registry_result(trade_id, **kwargs):
        registry.close_calls.append((trade_id, copy.deepcopy(kwargs)))
        return {
            "ok": False,
            "action": "BLOCKED",
            "error": f"{sentinel} {private_path}",
            "trade": {
                "trade_id": trade_id,
                "metadata": {"secret": sentinel, "path": private_path},
            },
        }

    registry.close_trade = unsafe_registry_result
    client = _flask_client_for_harness(ns)
    response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    _assert_no_store(response)
    serialized = response.get_data(as_text=True) + str(dict(response.headers))
    assert sentinel not in serialized
    assert private_path not in serialized
    assert "metadata" not in response.get_data(as_text=True)
    assert "registry_result" not in response.get_data(as_text=True)
    assert broker.writer_calls == []


def test_http_internal_error_is_sanitized_500_with_no_store():
    sentinel = "INTERNAL_SECRET_SENTINEL"
    private_path = r"C:\\private\\central\\secret.json"
    ns, registry, broker, _ = _harness()

    def fail_identity(_mapping):
        raise RuntimeError(f"{sentinel} {private_path}")

    ns["_rtlm_v15_identity_from_mapping"] = fail_identity
    client = _flask_client_for_harness(ns)
    response = client.get(
        "/realtradelifecycle",
        query_string=_route_params(),
        headers=_auth_headers(),
    )

    assert response.status_code == 500
    _assert_no_store(response)
    assert response.get_json()["status"] == "REAL_TRADE_LIFECYCLE_INTERNAL_ERROR"
    serialized = response.get_data(as_text=True) + str(dict(response.headers))
    assert sentinel not in serialized
    assert private_path not in serialized
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_public_projection_redacts_posix_unc_traversal_and_credential_strings():
    ns, _registry, _broker, _ = _harness()

    projected = ns["_rtlm_v15_public_payload"](
        {
            "generic_posix": "/opt/render/project/data/private.json",
            "generic_unc": r"\\server\share\private.json",
            "generic_traversal": "../private/registry.json",
            "generic_credential": "token=TOP-SECRET",
            "safe_status": "MISSING_FROM_BOTS_REGISTRY_CLOSED",
        }
    )

    assert projected == {
        "generic_posix": "REDACTED",
        "generic_unc": "REDACTED",
        "generic_traversal": "REDACTED",
        "generic_credential": "REDACTED",
        "safe_status": "MISSING_FROM_BOTS_REGISTRY_CLOSED",
    }


def test_http_framework_405_also_has_no_store_headers():
    ns, registry, broker, _ = _harness()
    client = _flask_client_for_harness(ns)

    response = client.get("/realtradelifecycle/close")

    assert response.status_code == 405
    _assert_no_store(response)
    assert broker.position_reads == []
    assert broker.writer_calls == []
    assert registry.read_calls == 0
    assert registry.close_calls == []


def test_real_builder_get_aliases_are_strict_read_only_and_post_is_unchanged():
    ns, registry, broker, build_calls = _harness()
    forbidden_calls = _install_real_read_only_builder(ns, broker)
    client = _flask_client_for_harness(ns)
    before = copy.deepcopy(registry.state)

    generic_urls = (
        "/realtradelifecycle",
        "/realtradelifecycle/XRPUSDT/LONG",
        "/lifecyclemonitor",
        "/lifecyclemonitor/XRPUSDT/LONG",
        "/trade/lifecycle",
    )
    for url in generic_urls:
        response = client.get(
            url,
            query_string={"bot": "FALCON", "setup": "FALCON15"},
        )
        assert response.status_code == 200
        _assert_no_store(response)
        payload = response.get_json()
        assert payload["read_only"] is True
        assert payload["registry_write"] is False
        assert payload["write_executed"] is False
        assert payload["registry_persistence_v1"] == {
            "version": "TEST-PERSISTENCE-V1",
            "status": "STRICT_READ_ONLY_PREVIEW",
            "strict_read_only": True,
            "registry_read_only_available": True,
            "registry_read_status": "TRADE_REGISTRY_READ_ONLY_LOADED",
            "summary": {"open_count": 1},
            "snapshot_save": {
                "attempted": False,
                "committed": False,
                "status": "STRICT_READ_ONLY_NOT_REQUESTED",
            },
            "rebuild": {
                "attempted": False,
                "committed": False,
                "status": "STRICT_READ_ONLY_NOT_REQUESTED",
            },
            "restore": {
                "attempted": False,
                "committed": False,
                "status": "STRICT_READ_ONLY_NOT_REQUESTED",
            },
            "persistent_snapshot_accessed": False,
            "persistent_event_written": False,
            "registry_write": False,
            "write_executed": False,
        }

    assert registry.state == before
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert registry.close_calls == []
    assert forbidden_calls == []
    assert build_calls == []

    position_reads_before = len(broker.position_reads)
    strong_preview = client.get(
        "/realtradelifecycle",
        query_string=_route_params(),
        headers=_auth_headers(),
    )
    assert strong_preview.status_code == 200
    assert strong_preview.get_json()["status"] == (
        "MISSING_FROM_BOTS_EXACT_CLOSE_READY"
    )
    assert len(broker.position_reads) - position_reads_before == 1
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert registry.close_calls == []
    assert forbidden_calls == []

    position_reads_before = len(broker.position_reads)
    close_response = client.post(
        "/realtradelifecycle/close",
        json=_post_payload(),
        headers=_auth_headers(),
    )
    assert close_response.status_code == 200
    assert close_response.get_json()["status"] == (
        "MISSING_FROM_BOTS_REGISTRY_CLOSED"
    )
    assert len(broker.position_reads) - position_reads_before == 2
    assert len(registry.close_calls) == 1
    assert registry.legacy_load_calls == 0
    assert registry.save_calls == 0
    assert broker.writer_calls == []
    assert forbidden_calls == []


def test_strict_registry_readers_do_not_fallback_when_read_only_loader_missing():
    calls = []

    class RegistryWithoutReadOnlyLoader:
        def load_registry(self):
            calls.append("load_registry")
            raise AssertionError("load_registry must not be called")

        def save_registry(self, _registry):
            calls.append("save_registry")
            raise AssertionError("save_registry must not be called")

    ns, _registry, broker, _ = _harness()
    forbidden_calls = _install_real_read_only_builder(ns, broker)
    ns["central_trade_registry"] = RegistryWithoutReadOnlyLoader()
    client = _flask_client_for_harness(ns)

    response = client.get("/realtradelifecycle")

    assert response.status_code == 200
    _assert_no_store(response)
    payload = response.get_json()
    assert payload["registry_persistence_v1"]["registry_read_only_available"] is False
    assert payload["registry_persistence_v1"]["registry_read_status"] == (
        "TRADE_REGISTRY_READ_ONLY_LOADER_UNAVAILABLE"
    )
    assert ns["_rtlm_v1_load_registry"]() is None
    assert ns["_rp_v1_registry_snapshot_full"](strict_read_only=True)["status"] == (
        "TRADE_REGISTRY_READ_ONLY_LOADER_UNAVAILABLE"
    )
    assert calls == []
    assert forbidden_calls == []
    assert broker.writer_calls == []


def test_trade_registry_strong_compare_and_close_is_atomic(tmp_path, monkeypatch):
    trade_registry = _isolated_trade_registry(tmp_path, "trade_registry.json")
    trade_registry.save_registry(
        {"open_trades": {TRADE_ID: _base_trade()}, "closed_trades": []}
    )
    expected = {
        "trade_id": TRADE_ID,
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "order_id": BROKER_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "status": "MISSING_FROM_BOTS",
    }

    blocked = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity={**expected, "lifecycle_id": "LC-WRONG"},
    )
    assert blocked["ok"] is False
    assert blocked["error"] == "TRADE_IDENTITY_MISMATCH"
    assert TRADE_ID in trade_registry.load_registry_read_only()["open_trades"]

    closed = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity=expected,
        clear_financial_results=True,
    )
    assert closed["ok"] is True
    assert closed["action"] == "TRADE_CLOSED"
    state = trade_registry.load_registry_read_only()
    assert TRADE_ID not in state["open_trades"]
    assert len(state["closed_trades"]) == 1


def test_trade_registry_strong_compare_rejects_conflicting_alias(tmp_path, monkeypatch):
    trade_registry = _isolated_trade_registry(
        tmp_path, "trade_registry-conflict.json"
    )
    trade = _base_trade()
    trade["metadata"]["client_order_id"] = "CLIENT-CONFLICT"
    trade_registry.save_registry(
        {"open_trades": {TRADE_ID: trade}, "closed_trades": []}
    )

    result = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity={"client_order_id": CLIENT_ORDER_ID},
    )

    assert result["ok"] is False
    assert result["error"] == "TRADE_IDENTITY_MISMATCH"
    assert result["identity_comparison"]["client_order_id"]["all_current_values"] == [
        CLIENT_ORDER_ID,
        "CLIENT-CONFLICT",
    ]
    assert TRADE_ID in trade_registry.load_registry_read_only()["open_trades"]


def test_trade_registry_close_respects_explicit_save_failure(tmp_path, monkeypatch):
    trade_registry = _isolated_trade_registry(
        tmp_path, "trade_registry-save-failure.json"
    )
    trade_registry.save_registry(
        {"open_trades": {TRADE_ID: _base_trade()}, "closed_trades": []}
    )
    monkeypatch.setattr(trade_registry, "save_registry", lambda _registry: False)

    result = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity={"lifecycle_id": LIFECYCLE_ID},
    )

    assert result == {
        "ok": False,
        "error": "TRADE_REGISTRY_SAVE_FAILED",
        "trade_id": TRADE_ID,
    }
    assert TRADE_ID in trade_registry.load_registry_read_only()["open_trades"]


def test_trade_registry_atomic_identity_uses_canonical_symbol_and_side(
    tmp_path, monkeypatch
):
    trade_registry = _isolated_trade_registry(
        tmp_path, "trade_registry-canonical.json"
    )
    trade = _base_trade(metadata={"symbol": "XRP/USDT:USDT", "side": "BUY"})
    trade_registry.save_registry(
        {"open_trades": {TRADE_ID: trade}, "closed_trades": []}
    )

    result = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity={"symbol": "XRPUSDT", "side": "LONG"},
    )

    assert result["ok"] is True
    assert result["action"] == "TRADE_CLOSED"


def test_trade_registry_revalidates_open_trade_id_uniqueness_inside_lock(
    tmp_path, monkeypatch
):
    trade_registry = _isolated_trade_registry(
        tmp_path, "trade_registry-duplicate-id.json"
    )
    trade_registry.save_registry(
        {
            "open_trades": {
                TRADE_ID: _base_trade(),
                "CORRUPT-ALTERNATE-KEY": copy.deepcopy(_base_trade()),
            },
            "closed_trades": [],
        }
    )

    result = trade_registry.close_trade(
        TRADE_ID,
        reason="BROKER_POSITION_NOT_FOUND_CONFIRMED",
        expected_identity={"lifecycle_id": LIFECYCLE_ID},
        expected_open_trade_id_count=1,
    )

    assert result["ok"] is False
    assert result["error"] == "TRADE_OPEN_IDENTITY_COUNT_MISMATCH"
    assert result["actual_open_trade_id_count"] == 2
    assert len(trade_registry.load_registry_read_only()["open_trades"]) == 2
