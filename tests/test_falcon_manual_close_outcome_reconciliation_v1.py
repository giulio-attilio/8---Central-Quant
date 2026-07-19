from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = ROOT / "main.py"
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
REGISTRY_SOURCE = ROOT / "trade_registry.py"
_MAIN_FUNCTION_CODE = None


def _safe_float(value, default=0.0):
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _norm_symbol(value):
    return str(value or "").upper().replace("/", "").replace(":USDT", "").replace("-", "").strip()


def _norm_side(value):
    value = str(value or "").upper().strip()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(value, value)


def _meta(record):
    return record.get("metadata") if isinstance(record, dict) and isinstance(record.get("metadata"), dict) else {}


def _value(record, *keys):
    for key in keys:
        if record.get(key) not in (None, ""):
            return record.get(key)
        if _meta(record).get(key) not in (None, ""):
            return _meta(record).get(key)
    return None


def _identity(position):
    return {
        "trade_id": position.get("trade_registry_id") or position.get("trade_id"),
        "lifecycle_id": position.get("lifecycle_id"),
        "order_id": position.get("live_order_id") or position.get("order_id"),
        "symbol": _norm_symbol(position.get("symbol")),
        "side": _norm_side(position.get("side")),
    }


def _load_main_functions(namespace):
    global _MAIN_FUNCTION_CODE
    wanted = {
        "_fmcor_v1_present",
        "_fmcor_v1_text_value",
        "_fmcor_v1_identifier",
        "_fmcor_v1_trade_values",
        "_fmcor_v1_has_stronger_outcome",
        "_fmcor_v1_classification",
        "_fmcor_v1_module_positions",
        "_fmcor_v1_build_candidate",
        "_fmcor_v1_build_payload",
        "_fmcor_v1_text",
        "falcon_manual_close_outcome_v1_text_route",
    }
    if _MAIN_FUNCTION_CODE is None:
        tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in wanted:
                node.decorator_list = []
                nodes.append(node)
        assert {node.name for node in nodes} == wanted
        _MAIN_FUNCTION_CODE = compile(
            ast.Module(body=nodes, type_ignores=[]), str(MAIN_SOURCE), "exec"
        )
    exec(_MAIN_FUNCTION_CODE, namespace)
    return namespace


def _base_trade(**updates):
    trade = {
        "trade_id": "TR-XRP",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-XRP",
        "broker_order_id": "ORDER-XRP",
        "client_order_id": "CLIENT-XRP",
        "entry": 1.0871,
        "qty": 9.0,
        "sl": 1.08,
        "central_only_broker_flat_reconciled": True,
        "outcome_status": "RECONCILED_WITHOUT_PNL",
        "financial_reconciliation_pending": True,
        "learning_eligible": False,
        "metadata": {
            "owner": "FALCON",
            "central_only_broker_flat_reconciled": True,
            "outcome_status": "RECONCILED_WITHOUT_PNL",
            "financial_reconciliation_pending": True,
        },
    }
    trade.update(updates)
    return trade


def _params(**updates):
    params = {
        "trade_id": "TR-XRP",
        "lifecycle_id": "LC-XRP",
        "close_event_id": "CLOSE-XRP-MANUAL-1",
        "exit_price": "1.0902",
        "close_timestamp": "2026-07-15T15:30:00Z",
        "closed_quantity": "9",
        "close_reason": "TP50_MANUAL_FULL_CLOSE",
    }
    params.update(updates)
    return params


class FakeFalcon:
    def __init__(self, positions=None, fail_projection=False):
        self.positions = copy.deepcopy(positions or {})
        self.fail_projection = fail_projection
        self.projections = []
        self.HEALTH = {}

    def get_positions(self):
        return copy.deepcopy(self.positions)

    def falcon_project_manual_close_outcome(self, outcome):
        key = (outcome.get("outcome_id"), outcome.get("lifecycle_id"), outcome.get("close_event_id"))
        if self.fail_projection:
            self.HEALTH["falcon_manual_close_outcome_projection_pending"] = True
            return {"ok": False, "status": "PROJECTION_WRITE_FAILED", "projection_pending": True, "no_order_sent": True}
        if key in self.projections:
            return {"ok": True, "status": "ALREADY_PROJECTED", "projection_pending": False, "no_order_sent": True}
        self.projections.append(key)
        return {"ok": True, "status": "PROJECTED", "projection_pending": False, "no_order_sent": True}


class FakeRegistry:
    def __init__(self, closed=None, open_trades=None):
        self.closed = copy.deepcopy(closed or [])
        self.open = copy.deepcopy(open_trades or {})
        self.write_calls = []

    def load_registry(self):
        return {"open_trades": copy.deepcopy(self.open), "closed_trades": copy.deepcopy(self.closed)}

    def record_manual_close_outcome(self, trade_id, close_event_id, outcome, expected_identity=None):
        self.write_calls.append(copy.deepcopy({
            "trade_id": trade_id,
            "close_event_id": close_event_id,
            "outcome": outcome,
            "expected_identity": expected_identity,
        }))
        lifecycle_id = (expected_identity or {}).get("lifecycle_id") or outcome.get("lifecycle_id")
        candidates = [
            item for item in self.closed
            if item.get("lifecycle_id") == lifecycle_id
            and item.get("status") == "CLOSED"
            and item.get("bot") == "FALCON"
        ]
        if len(candidates) != 1:
            return {"ok": False, "error": "CLOSED_FALCON_LIFECYCLE_CANDIDATE_COUNT_INVALID"}
        trade = candidates[0]
        if trade.get("trade_id") != trade_id:
            return {"ok": False, "error": "TRADE_ID_MISMATCH"}
        keys = trade.setdefault("manual_close_outcome_keys", [])
        if close_event_id in keys:
            return {"ok": True, "action": "ALREADY_APPLIED", "trade": copy.deepcopy(trade), "outcome_id": trade.get("outcome_id")}
        keys.extend([close_event_id, f"{outcome.get('lifecycle_id')}:{close_event_id}"])
        trade.update(copy.deepcopy(outcome))
        trade.setdefault("metadata", {}).update(copy.deepcopy(outcome))
        trade["metadata"]["manual_close_outcome_keys"] = list(keys)
        return {"ok": True, "action": "OUTCOME_RECORDED", "trade": copy.deepcopy(trade), "outcome_id": trade.get("outcome_id")}


def _harness(trade=None, *, closed=None, positions=None, open_trades=None, fail_projection=False):
    registry = FakeRegistry(
        copy.deepcopy(closed) if closed is not None else [trade or _base_trade()],
        open_trades=open_trades,
    )
    falcon = FakeFalcon(positions=positions, fail_projection=fail_projection)
    namespace = {
        "json": json,
        "hashlib": hashlib,
        "threading": threading,
        "_safe_float": _safe_float,
        "_flad_v1_norm_symbol": _norm_symbol,
        "_flad_v1_norm_side": _norm_side,
        "_flad_v1_public": copy.deepcopy,
        "_fcor_v1_meta": _meta,
        "_fcor_v1_value": _value,
        "_fcor_v1_identity": lambda position, position_id=None: _identity(position),
        "_fcor_v1_falcon_module": lambda: falcon,
        "_fcor_v1_now": lambda: "19/07/2026 12:00:00",
        "central_trade_registry": registry,
        "FALCON_MANUAL_CLOSE_OUTCOME_V1_VERSION": "TEST-V1",
        "FALCON_MANUAL_CLOSE_OUTCOME_V1_ACK": "FALCON_MANUAL_CLOSE_OUTCOME_V1",
        "_FMCOR_V1_LOCK": threading.RLock(),
    }
    return _load_main_functions(namespace), registry, falcon


def test_xrp_like_tp50_manual_full_close_calculates_factual_outcome():
    ns, registry, _ = _harness()
    payload = ns["_fmcor_v1_build_payload"](_params())

    outcome = payload["outcome"]
    assert payload["status"] == "PREVIEW_READY"
    assert outcome["close_classification"] == "TP50_MANUAL_FULL_CLOSE"
    assert outcome["tp50_hit"] is True
    assert outcome["pnl_pct"] == pytest.approx((1.0902 - 1.0871) / 1.0871 * 100)
    assert outcome["gross_pnl_usdt"] == pytest.approx((1.0902 - 1.0871) * 9)
    assert outcome["result_r"] == pytest.approx((1.0902 - 1.0871) / (1.0871 - 1.08))
    assert registry.write_calls == []


def _xrp_trade_id_collision_fixture():
    trade_id = "FALCON:FALCON15:XRPUSDT:LONG"
    old_verify = _base_trade(
        trade_id=trade_id,
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:FALCON-VERIFY-OLD-XRP",
        broker_order_id="VERIFY-ORDER-XRP",
        client_order_id="FALCON-VERIFY-OLD-XRP",
        entry=1.1123,
        registry_mode="VERIFY",
        execution_mode="VERIFY",
    )
    live_real = _base_trade(
        trade_id=trade_id,
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114",
        broker_order_id="2078483751332171776",
        client_order_id="FALCON-LIVE-FALCON15-1784384114",
        entry=1.0871,
        initial_qty=9.0,
        qty=9.0,
        sl=1.084175,
        tp50=1.090025,
        registry_mode="REAL",
        execution_mode="LIVE",
        central_only_broker_flat_reconciled=True,
        financial_reconciliation_pending=True,
        outcome_status="RECONCILED_WITHOUT_PNL",
        learning_eligible=False,
    )
    params = _params(
        trade_id=trade_id,
        lifecycle_id=live_real["lifecycle_id"],
        close_event_id="XRP_MANUAL_TP50_20260718_1837",
        exit_price="1.0902",
        close_timestamp="2026-07-18T18:37:00-03:00",
        closed_quantity="9",
        close_reason="TP50_MANUAL_FULL_CLOSE",
    )
    return old_verify, live_real, params


def test_lifecycle_first_resolves_live_trade_despite_reused_trade_id():
    old_verify, live_real, params = _xrp_trade_id_collision_fixture()
    ns, registry, _ = _harness(closed=[old_verify, live_real])

    payload = ns["_fmcor_v1_build_payload"](params)

    assert payload["status"] == "PREVIEW_READY"
    assert payload["candidate_count"] == 1
    assert payload["trade_id_candidate_count"] == 2
    assert payload["resolution_diagnostics"] == [
        "CANDIDATE_RESOLVED_BY_LIFECYCLE_ID",
        "TRADE_ID_COLLISION_IGNORED_AFTER_LIFECYCLE_MATCH",
    ]
    outcome = payload["outcome"]
    assert outcome["entry"] == pytest.approx(1.0871)
    assert outcome["order_id"] == "2078483751332171776"
    assert outcome["client_order_id"] == "FALCON-LIVE-FALCON15-1784384114"
    assert outcome["pnl_pct"] == pytest.approx(0.2851623585686696)
    assert outcome["gross_pnl_usdt"] == pytest.approx(0.0279)
    assert outcome["result_r"] == pytest.approx(1.0614, abs=0.002)
    assert outcome["tp50_hit"] is True
    assert not {
        "TRADE_NOT_LIVE",
        "POSITION_STILL_OPEN",
        "LIFECYCLE_ID_MISMATCH",
        "ORDER_IDENTITY_DIVERGENCE",
        "FACTUAL_ENTRY_REQUIRED",
    }.intersection(payload["reasons"])
    assert registry.write_calls == []


def test_trade_id_collision_without_lifecycle_is_fail_closed():
    old_verify, live_real, params = _xrp_trade_id_collision_fixture()
    ns, registry, _ = _harness(closed=[old_verify, live_real])
    params["lifecycle_id"] = ""

    payload = ns["_fmcor_v1_build_payload"](params)

    assert payload["status"] == "BLOCKED"
    assert "LIFECYCLE_ID_REQUIRED" in payload["reasons"]
    assert "LIFECYCLE_ID_REQUIRED_WHEN_TRADE_ID_NOT_UNIQUE" in payload["reasons"]
    assert registry.write_calls == []


def test_commit_with_collision_writes_only_lifecycle_selected_trade_and_retries_idempotently():
    old_verify, live_real, params = _xrp_trade_id_collision_fixture()
    ns, registry, falcon = _harness(closed=[old_verify, live_real])

    first = ns["_fmcor_v1_build_payload"](
        params, commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1"
    )
    second = ns["_fmcor_v1_build_payload"](
        params, commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1"
    )

    assert first["status"] == "OUTCOME_RECORDED"
    assert second["status"] == "ALREADY_APPLIED"
    assert registry.closed[0].get("outcome_id") is None
    assert registry.closed[0]["entry"] == pytest.approx(1.1123)
    assert registry.closed[1]["outcome_status"] == "OUTCOME_RECORDED"
    assert registry.closed[1]["entry"] == pytest.approx(1.0871)
    assert len(falcon.projections) == 1


def test_sol_like_manual_close_outcome_is_supported():
    trade = _base_trade(
        trade_id="TR-SOL", lifecycle_id="LC-SOL", broker_order_id="ORDER-SOL",
        symbol="SOLUSDT", entry=160.0, qty=2.0, sl=156.0,
    )
    ns, _, _ = _harness(trade)
    payload = ns["_fmcor_v1_build_payload"](_params(
        trade_id="TR-SOL", lifecycle_id="LC-SOL", close_event_id="CLOSE-SOL-1",
        exit_price="162", closed_quantity="2", close_reason="MANUAL_CLOSE",
    ))

    assert payload["status"] == "PREVIEW_READY"
    assert payload["outcome"]["symbol"] == "SOLUSDT"
    assert payload["outcome"]["pnl_pct"] == pytest.approx(1.25)
    assert payload["outcome"]["gross_pnl_usdt"] == pytest.approx(4.0)
    assert payload["outcome"]["result_r"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"exit_price": ""}, "EXIT_PRICE_REQUIRED"),
        ({"lifecycle_id": "OTHER"}, "LIFECYCLE_ID_MISMATCH"),
        ({"closed_quantity": "4"}, "PARTIAL_CLOSE_NOT_FINAL_OUTCOME"),
        ({"closed_quantity": "10"}, "CLOSED_QUANTITY_EXCEEDS_LIFECYCLE"),
    ],
)
def test_invalid_or_partial_outcome_is_blocked(updates, reason):
    ns, registry, _ = _harness()
    payload = ns["_fmcor_v1_build_payload"](_params(**updates), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")

    assert payload["status"] == "BLOCKED"
    assert reason in payload["reasons"]
    assert registry.write_calls == []


def test_position_still_open_and_central_only_pending_are_blocked():
    open_position = {
        "trade_registry_id": "TR-XRP", "lifecycle_id": "LC-XRP", "live_order_id": "ORDER-XRP",
        "symbol": "XRPUSDT", "side": "LONG", "central_only_reconcile_required": True,
    }
    ns, registry, _ = _harness(positions={"P": open_position})
    payload = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")

    assert payload["status"] == "BLOCKED"
    assert "CENTRAL_ONLY_RECONCILIATION_PENDING" in payload["reasons"]
    assert registry.write_calls == []


def test_registry_open_trade_blocks_even_with_closed_candidate():
    ns, registry, _ = _harness(open_trades={"TR-XRP": _base_trade(status="OPEN")})
    payload = ns["_fmcor_v1_build_payload"](_params())
    assert payload["status"] == "BLOCKED"
    assert "POSITION_STILL_OPEN" in payload["reasons"]
    assert registry.write_calls == []


def test_manual_external_position_is_never_attributed_to_falcon():
    ns, registry, _ = _harness(_base_trade(external_position=True))
    payload = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")
    assert payload["status"] == "BLOCKED"
    assert "EXTERNAL_POSITION_OWNERSHIP_RISK" in payload["reasons"]
    assert registry.write_calls == []


def test_missing_factual_entry_and_stronger_existing_outcome_are_blocked():
    no_entry = _base_trade(entry=None)
    ns, registry, _ = _harness(no_entry)
    missing = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")
    assert "FACTUAL_ENTRY_REQUIRED" in missing["reasons"]
    assert registry.write_calls == []

    stronger_trade = _base_trade(
        outcome_status="OUTCOME_EVALUATED",
        outcome_id="BROKER-OUTCOME-1",
        outcome_source="BROKER_CONFIRMED_FILL",
        exit_price=1.091,
        pnl_pct=0.35,
        financial_reconciliation_pending=False,
    )
    ns, registry, _ = _harness(stronger_trade)
    stronger = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")
    assert "STRONGER_FACTUAL_OUTCOME_ALREADY_EXISTS" in stronger["reasons"]
    assert registry.write_calls == []


def test_missing_initial_stop_keeps_result_r_unknown_without_zero_fallback():
    trade = _base_trade(sl=None)
    ns, _, _ = _harness(trade)
    payload = ns["_fmcor_v1_build_payload"](_params())
    assert payload["status"] == "PREVIEW_READY"
    assert payload["outcome"]["result_r"] is None


def test_preview_and_wrong_ack_never_write():
    ns, registry, falcon = _harness()
    preview = ns["_fmcor_v1_build_payload"](_params())
    wrong_ack = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="WRONG")

    assert preview["status"] == "PREVIEW_READY"
    assert wrong_ack["status"] == "ACK_REQUIRED"
    assert registry.write_calls == []
    assert falcon.projections == []


def test_commit_and_retry_are_idempotent_and_project_once():
    ns, registry, falcon = _harness()
    first = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")
    second = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")

    assert first["status"] == "OUTCOME_RECORDED"
    assert second["status"] == "ALREADY_APPLIED"
    assert second["idempotent"] is True
    assert len(falcon.projections) == 1
    assert registry.closed[0]["outcome_status"] == "OUTCOME_RECORDED"
    assert registry.closed[0]["financial_reconciliation_pending"] is False
    assert registry.closed[0]["outcome_source"] == "MANUAL_CLOSE_RECONCILIATION"
    assert len(registry.closed[0]["manual_close_outcome_keys"]) == 2


def test_projection_failure_leaves_registry_authoritative_and_pending_visible():
    ns, registry, falcon = _harness(fail_projection=True)
    payload = ns["_fmcor_v1_build_payload"](_params(), commit_requested=True, ack="FALCON_MANUAL_CLOSE_OUTCOME_V1")

    assert payload["status"] == "OUTCOME_RECORDED_PROJECTION_PENDING"
    assert payload["ok"] is True and payload["committed"] is True
    assert payload["projection_pending"] is True
    assert registry.closed[0]["outcome_status"] == "OUTCOME_RECORDED"
    assert falcon.HEALTH["falcon_manual_close_outcome_projection_pending"] is True


def test_text_route_is_manual_get_and_never_exposes_operational_actions():
    ns, registry, _ = _harness()
    ns["request"] = SimpleNamespace(args=_params())
    text, status, headers = ns["falcon_manual_close_outcome_v1_text_route"]()

    assert status == 200
    assert headers["Content-Type"].startswith("text/plain")
    assert "Status: PREVIEW_READY" in text
    assert "no_order_sent_by_this_route: True" in text
    assert "broker_called: False" in text
    assert registry.write_calls == []


def _load_falcon_projection(storage, health):
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "falcon_project_manual_close_outcome")
    def store(_key, value):
        storage.clear()
        storage.extend(copy.deepcopy(value))
        return True

    namespace = {
        "manual_close_outcome_projection_lock": threading.RLock(),
        "redis_get_json": lambda key, default: copy.deepcopy(storage),
        "redis_set_json": store,
        "TRADES_KEY": "falcon:trades",
        "HEALTH": health,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(FALCON_SOURCE), "exec"), namespace)
    return namespace["falcon_project_manual_close_outcome"]


def test_falcon_projection_appends_once_without_close_position_or_broker():
    storage = []
    health = {}
    project = _load_falcon_projection(storage, health)
    outcome = {
        **_params(), "bot": "FALCON", "setup": "FALCON15", "symbol": "XRPUSDT", "side": "LONG",
        "order_id": "ORDER-XRP", "entry": 1.0871, "initial_stop": 1.08,
        "outcome_id": "OUT-1", "outcome_hash": "HASH-1", "pnl_pct": 0.28,
        "gross_pnl_usdt": 0.0279, "result_r": 0.43, "tp50_hit": True,
    }
    first = project(outcome)
    second = project(outcome)

    assert first["status"] == "PROJECTED"
    assert second["status"] == "ALREADY_PROJECTED"
    assert len(storage) == 1
    assert storage[0]["result_pct"] == pytest.approx(0.28)
    source = ast.get_source_segment(FALCON_SOURCE.read_text(encoding="utf-8"), next(node for node in ast.parse(FALCON_SOURCE.read_text(encoding="utf-8")).body if isinstance(node, ast.FunctionDef) and node.name == "falcon_project_manual_close_outcome"))
    assert "close_position(" not in source
    assert "central_broker" not in source


def test_registry_writer_is_atomic_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    spec = importlib.util.spec_from_file_location("trade_registry_manual_outcome_test", REGISTRY_SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_observe_shadow_registry_snapshot", lambda *args, **kwargs: None)
    old_collision = _base_trade(
        lifecycle_id="LC-XRP-OLD-VERIFY",
        broker_order_id="ORDER-XRP-OLD",
        client_order_id="CLIENT-XRP-OLD",
        entry=1.1123,
        registry_mode="VERIFY",
        execution_mode="VERIFY",
    )
    module.save_registry({"open_trades": {}, "closed_trades": [old_collision, _base_trade()]})
    outcome = {
        "trade_id": "TR-XRP", "lifecycle_id": "LC-XRP", "close_event_id": "CLOSE-XRP-MANUAL-1",
        "outcome_id": "OUT-XRP-1", "outcome_hash": "HASH-XRP-1", "outcome_status": "OUTCOME_RECORDED",
        "outcome_source": "MANUAL_CLOSE_RECONCILIATION", "financial_reconciliation_pending": False,
        "learning_eligible": True, "data_quality": "MANUAL_CONFIRMED", "exit_price": 1.0902,
        "closed_quantity": 9.0, "close_timestamp": "2026-07-15T15:30:00Z",
        "close_reason": "TP50_MANUAL_FULL_CLOSE", "close_classification": "TP50_MANUAL_FULL_CLOSE",
        "pnl_pct": 0.28, "result_pct": 0.28, "gross_pnl_usdt": 0.0279, "result_r": 0.43,
        "pnl_r": 0.43, "tp50_hit": True,
    }

    first = module.record_manual_close_outcome("TR-XRP", "CLOSE-XRP-MANUAL-1", outcome, expected_identity={"lifecycle_id": "LC-XRP", "order_id": "ORDER-XRP"})
    second = module.record_manual_close_outcome("TR-XRP", "CLOSE-XRP-MANUAL-1", outcome, expected_identity={"lifecycle_id": "LC-XRP", "order_id": "ORDER-XRP"})
    saved = module.load_registry()["closed_trades"]

    assert first.get("action") == "OUTCOME_RECORDED", first
    assert second.get("action") == "ALREADY_APPLIED", second
    assert len(saved) == 2
    assert saved[0].get("outcome_id") is None
    assert saved[0]["entry"] == pytest.approx(1.1123)
    assert saved[1]["outcome_id"] == "OUT-XRP-1"
    assert saved[1]["financial_reconciliation_pending"] is False
    assert saved[1]["manual_close_outcome_keys"] == ["CLOSE-XRP-MANUAL-1", "LC-XRP:CLOSE-XRP-MANUAL-1"]
