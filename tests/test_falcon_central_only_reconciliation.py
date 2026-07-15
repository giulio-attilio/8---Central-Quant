from __future__ import annotations

import ast
import copy
import json
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


MAIN = Path("main.py")
FIXED_EPOCH = 1_784_128_000.0
FIXED_NOW = "2026-07-15 09:00:00"
ACK = "FALCON_CENTRAL_ONLY_RECONCILE"


RECONCILIATION_FUNCTIONS = {
    "_fcor_v1_now",
    "_fcor_v1_falcon_module",
    "_fcor_v1_raw_positions",
    "_fcor_v1_meta",
    "_fcor_v1_value",
    "_fcor_v1_identity",
    "_fcor_v1_registry_identity",
    "_fcor_v1_reconciled_closed_index",
    "_fcor_v1_factual_closed_index",
    "_fcor_v1_evidence_reasons",
    "_fcor_v1_candidate",
    "_fcor_v1_build_plan",
    "_fcor_v1_counts",
    "_fcor_v1_atomic_write",
    "_fcor_v1_append",
    "_fcor_v1_sample",
    "_fcor_v1_reconciliation_metadata",
    "_fcor_v1_build_payload",
    "_fcor_v1_health_overlay",
    "_fcor_v1_text",
    "_fcor_v1_request_commit_ack",
}
_COMPILED_FUNCTION_SETS: dict[tuple[str, ...], object] = {}


def _extract_functions(names: set[str], namespace: dict) -> dict:
    """Compile selected top-level functions without importing the application."""
    cache_key = tuple(sorted(names))
    compiled = _COMPILED_FUNCTION_SETS.get(cache_key)
    if compiled is None:
        tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
        selected = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        ]
        found = {node.name for node in selected}
        assert found == names, f"missing functions in main.py: {sorted(names - found)}"
        module = ast.Module(body=selected, type_ignores=[])
        ast.fix_missing_locations(module)
        compiled = compile(module, str(MAIN), "exec")
        _COMPILED_FUNCTION_SETS[cache_key] = compiled
    exec(compiled, namespace)
    return namespace


def _norm_symbol(value) -> str:
    return str(value or "").upper().replace("/", "").replace(":USDT", "").replace("-", "")


def _norm_side(value) -> str:
    side = str(value or "").upper().strip()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)


def _safe_float(value, default=0.0):
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def _public(value):
    return copy.deepcopy(value)


def _base_position(**updates) -> dict:
    position = {
        "id": "POS-XRP",
        "trade_registry_id": "TR-XRP",
        "lifecycle_id": "LC-XRP",
        "live_order_id": "2077392837327147008",
        "live_client_order_id": "FALCON-LIVE-FALCON15-1784124020",
        "symbol": "XRPUSDT",
        "side": "SHORT",
        "setup": "FALCON15",
        "entry": 1.1219,
        "remaining_qty": 8.0,
        "initial_stop": 1.1294,
        "opened_at": "2026-07-15 08:20:00",
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "central_only_reconcile_required": True,
        "central_only_evidence": {
            "status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
            "broker_flat": True,
            "position_closed": True,
            "read_only": True,
            "sent": False,
            "position_qty": 0.0,
            "matched_count": 0,
            "checked_epoch": FIXED_EPOCH,
            "checked_at": FIXED_NOW,
            "stop_order_active": False,
            "stop_order_status": "CANCELED",
            "stop_order_filled": False,
            "stop_order_full_fill_confirmed": False,
            "trade_id": "TR-XRP",
            "lifecycle_id": "LC-XRP",
            "order_id": "2077392837327147008",
            "client_order_id": "FALCON-LIVE-FALCON15-1784124020",
            "symbol": "XRPUSDT",
            "side": "SHORT",
            "manual_user_close_suspected": True,
            "stop_anomaly_suspected": True,
        },
    }
    position.update(updates)
    return position


def _base_trade(**updates) -> dict:
    trade = {
        "trade_id": "TR-XRP",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "SHORT",
        "status": "OPEN",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-XRP",
        "broker_order_id": "2077392837327147008",
        "client_order_id": "FALCON-LIVE-FALCON15-1784124020",
        "entry": 1.1219,
        "qty": 8.0,
        "sl": 1.1294,
        "opened_at": "2026-07-15 08:20:00",
        "metadata": {
            "owner": "FALCON",
            "original_marker": "preserve-me",
        },
    }
    trade.update(updates)
    return trade


class FakeRegistry:
    def __init__(self, trade: dict, *, fail_close: bool = False, operation_log: list[str] | None = None):
        self.payload = {
            "open_trades": {str(trade["trade_id"]): copy.deepcopy(trade)},
            "closed_trades": [],
        }
        self.fail_close = fail_close
        self.close_calls: list[dict] = []
        self.operation_log = operation_log if operation_log is not None else []

    def load_registry(self):
        return copy.deepcopy(self.payload)

    def close_trade(self, trade_id, **kwargs):
        self.operation_log.append("registry_close")
        self.close_calls.append({"trade_id": trade_id, **copy.deepcopy(kwargs)})
        if self.fail_close:
            return {"ok": False, "error": "SIMULATED_REGISTRY_FAILURE", "trade_id": trade_id}
        current = self.payload["open_trades"].get(str(trade_id))
        expected_identity = kwargs.get("expected_identity") or {}
        aliases = {
            "lifecycle_id": ("lifecycle_id",),
            "order_id": ("broker_order_id", "order_id"),
            "client_order_id": ("client_order_id",),
        }
        for field, expected in expected_identity.items():
            if expected in (None, ""):
                continue
            actual = next((current.get(key) for key in aliases[field] if current and current.get(key) not in (None, "")), None)
            if str(actual or "") != str(expected):
                return {"ok": False, "error": "TRADE_IDENTITY_MISMATCH", "trade_id": trade_id}
        trade = self.payload["open_trades"].pop(str(trade_id), None)
        if trade is None:
            return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}
        closed = copy.deepcopy(trade)
        closed.update(
            {
                "status": "CLOSED",
                "exit_price": kwargs.get("exit_price"),
                "pnl_pct": kwargs.get("pnl_pct"),
                "pnl_r": kwargs.get("pnl_r"),
                "close_reason": kwargs.get("reason"),
                "closed_at": FIXED_NOW,
            }
        )
        if kwargs.get("broker_close_order_id") is not None:
            closed["broker_close_order_id"] = kwargs["broker_close_order_id"]
        closed["registry_mode"] = kwargs.get("registry_mode") or closed.get("registry_mode")
        if kwargs.get("clear_financial_results"):
            for field in (
                "result_pct", "result_r", "realized_pnl", "realized_pnl_usdt",
                "net_pnl", "net_pnl_usdt", "pnl_usdt", "profit_usdt",
                "profit_loss", "r_multiple", "outcome", "outcome_id", "fee", "funding",
                "broker_close_order_id", "close_order_id", "close_qty", "closed_qty",
            ):
                closed[field] = None
        closed.setdefault("metadata", {}).update(copy.deepcopy(kwargs.get("metadata") or {}))
        for key, value in kwargs.items():
            if key not in {"exit_price", "pnl_pct", "pnl_r", "reason", "metadata", "registry_mode", "broker_close_order_id", "expected_identity", "clear_financial_results"} and value is not None:
                closed[key] = copy.deepcopy(value)
        self.payload["closed_trades"].append(closed)
        return {"ok": True, "action": "TRADE_CLOSED", "trade_id": trade_id, "trade": copy.deepcopy(closed)}


class FakeFalconModule:
    FALCON_CENTRAL_ONLY_EVIDENCE_MAX_AGE_SECONDS = 300

    def __init__(
        self,
        position: dict,
        registry: FakeRegistry,
        *,
        fail_remove: bool = False,
        operation_log: list[str] | None = None,
    ):
        self.positions = {str(position.get("id") or "POS-XRP"): copy.deepcopy(position)}
        self.registry = registry
        self.fail_remove = fail_remove
        self.remove_calls: list[dict] = []
        self.operation_log = operation_log if operation_log is not None else []
        self.HEALTH = {}

    def get_positions(self):
        return copy.deepcopy(self.positions)

    def falcon_reconcile_remove_position(self, **identity):
        self.operation_log.append("module_remove")
        self.remove_calls.append(copy.deepcopy(identity))
        trade_id = str(identity.get("trade_id") or "")
        # The module position may only disappear after the Registry has reached
        # a factual terminal state.
        assert trade_id not in self.registry.payload["open_trades"]
        assert any(item.get("trade_id") == trade_id for item in self.registry.payload["closed_trades"])
        if self.fail_remove:
            return {"ok": False, "removed": False, "status": "SIMULATED_REMOVE_FAILURE"}
        position_id = str(identity.get("position_id") or "")
        position = self.positions.get(position_id)
        if position is None:
            return {"ok": True, "removed": False, "already_removed": True, "status": "ALREADY_REMOVED"}
        expected = {
            "trade_id": position.get("trade_registry_id") or position.get("trade_id"),
            "lifecycle_id": position.get("lifecycle_id"),
            "order_id": position.get("live_order_id"),
            "client_order_id": position.get("live_client_order_id"),
        }
        if any(str(identity.get(key) or "") != str(value or "") for key, value in expected.items()):
            return {"ok": False, "removed": False, "status": "IDENTITY_MISMATCH"}
        self.positions.pop(position_id)
        return {"ok": True, "removed": True, "already_removed": False, "status": "CENTRAL_ONLY_POSITION_REMOVED"}


class ForbiddenBroker:
    def __getattr__(self, name):
        raise AssertionError(f"broker/order surface must not be used by reconciliation route: {name}")


def _harness(
    tmp_path: Path,
    *,
    position: dict | None = None,
    trade: dict | None = None,
    fail_registry_close: bool = False,
    fail_module_remove: bool = False,
):
    operation_log: list[str] = []
    registry = FakeRegistry(
        trade or _base_trade(),
        fail_close=fail_registry_close,
        operation_log=operation_log,
    )
    module = FakeFalconModule(
        position or _base_position(),
        registry,
        fail_remove=fail_module_remove,
        operation_log=operation_log,
    )
    state = {
        "status": "NOT_RUN",
        "last_run": None,
        "last_error": None,
        "last_reconciled_count": 0,
    }
    namespace = {
        "Path": Path,
        "json": json,
        "os": os,
        "threading": threading,
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "time": SimpleNamespace(time=lambda: FIXED_EPOCH),
        "data_hora_sp_str": lambda: FIXED_NOW,
        "_safe_float": _safe_float,
        "_flad_v1_norm_symbol": _norm_symbol,
        "_flad_v1_norm_side": _norm_side,
        "_flad_v1_public": _public,
        "central_trade_registry": registry,
        "central_broker": ForbiddenBroker(),
        "LOADED_BOTS": {"FALCON": module},
        "EXECUTION_MODE": "BINGX_AUTO",
        "ENABLE_REAL_TRADING": True,
        "FALCON_CENTRAL_ONLY_RECONCILIATION_V1_VERSION": "TEST-V1",
        "FALCON_CENTRAL_ONLY_RECONCILIATION_V1_ACK": ACK,
        "FALCON_CENTRAL_ONLY_RECONCILIATION_V1_LATEST_FILE": tmp_path / "latest.json",
        "FALCON_CENTRAL_ONLY_RECONCILIATION_V1_EVENTS_FILE": tmp_path / "events.jsonl",
        "_FCOR_V1_LOCK": threading.RLock(),
        "_FCOR_V1_STATE": state,
    }
    _extract_functions(RECONCILIATION_FUNCTIONS, namespace)
    return SimpleNamespace(ns=namespace, registry=registry, module=module, state=state, operation_log=operation_log)


def _build(harness, *, commit=False, ack=None):
    return harness.ns["_fcor_v1_build_payload"](commit_requested=commit, ack=ack)


def test_request_parser_accepts_preview_by_default_and_exact_query_or_post_ack(tmp_path):
    harness = _harness(tmp_path)
    parser = harness.ns["_fcor_v1_request_commit_ack"]

    harness.ns["request"] = SimpleNamespace(method="GET", args={}, get_json=lambda silent=True: None)
    assert parser() == (False, None)

    harness.ns["request"] = SimpleNamespace(
        method="GET",
        args={"commit": "true", "ack": ACK},
        get_json=lambda silent=True: None,
    )
    assert parser() == (True, ACK)

    harness.ns["request"] = SimpleNamespace(
        method="POST",
        args={},
        get_json=lambda silent=True: {"commit": True, "ack": ACK},
    )
    assert parser() == (True, ACK)


def _closed_trade(harness) -> dict:
    assert len(harness.registry.payload["closed_trades"]) == 1
    return harness.registry.payload["closed_trades"][0]


def test_preview_is_pure_and_reports_the_factual_central_only_candidate(tmp_path):
    harness = _harness(tmp_path)
    registry_before = copy.deepcopy(harness.registry.payload)
    positions_before = copy.deepcopy(harness.module.positions)

    result = _build(harness)

    assert result["status"] == "PREVIEW_READY"
    assert result["commit_requested"] is False
    assert result["committed"] is False
    assert result["planned_count"] == 1
    assert result["central_live_before"] == result["central_live_after"] == 1
    assert result["only_central_before"] == result["only_central_after"] == 1
    assert result["bingx_positions_before"] == result["bingx_positions_after"] == 0
    assert result["broker_called_by_this_route"] is False
    assert result["no_order_sent_by_this_route"] is True
    assert result["would_send_order"] is False
    assert harness.registry.payload == registry_before
    assert harness.module.positions == positions_before
    assert not harness.registry.close_calls
    assert not harness.module.remove_calls
    assert not (tmp_path / "latest.json").exists()
    assert not (tmp_path / "events.jsonl").exists()


@pytest.mark.parametrize("ack", [None, "", "WRONG", "falcon_central_only_reconcile"])
def test_commit_requires_the_exact_ack_and_never_mutates_on_rejection(tmp_path, ack):
    harness = _harness(tmp_path)
    before = copy.deepcopy((harness.registry.payload, harness.module.positions))

    result = _build(harness, commit=True, ack=ack)

    assert result["status"] == "ACK_REQUIRED"
    assert result["ack_ok"] is False
    assert result["committed"] is False
    assert (harness.registry.payload, harness.module.positions) == before
    assert not harness.registry.close_calls
    assert not harness.module.remove_calls


def test_valid_commit_closes_registry_then_removes_the_exact_module_position(tmp_path):
    harness = _harness(tmp_path)

    result = _build(harness, commit=True, ack=ACK)

    assert result["status"] == "RECONCILED"
    assert result["ack_ok"] is True and result["committed"] is True
    assert result["registry_closed_count"] == 1
    assert result["reconciled_count"] == 1
    assert result["central_live_before"] == 1 and result["central_live_after"] == 0
    assert result["only_central_before"] == 1 and result["only_central_after"] == 0
    assert result["bingx_positions_before"] == result["bingx_positions_after"] == 0
    assert harness.operation_log == ["registry_close", "module_remove"]
    assert harness.registry.payload["open_trades"] == {}
    assert harness.module.positions == {}
    assert (tmp_path / "latest.json").exists()
    assert (tmp_path / "events.jsonl").exists()


def test_commit_preserves_canonical_identity_original_trade_fields_and_audit_metadata(tmp_path):
    harness = _harness(tmp_path)
    original = copy.deepcopy(harness.registry.payload["open_trades"]["TR-XRP"])

    result = _build(harness, commit=True, ack=ACK)
    closed = _closed_trade(harness)

    assert result["reconciled_count"] == 1
    for field in ("trade_id", "bot", "setup", "symbol", "side", "lifecycle_id", "broker_order_id", "client_order_id", "entry", "opened_at"):
        assert closed[field] == original[field]
    assert closed["close_reason"] == "CENTRAL_ONLY_BROKER_FLAT_RECONCILED"
    metadata = closed["metadata"]
    assert metadata["owner"] == "FALCON"
    assert metadata["original_marker"] == "preserve-me"
    assert metadata["reconciled_by"] == "falcon_central_only_reconcile_v1"
    assert metadata["reconciled_at"] == FIXED_NOW
    assert metadata["reason"] == "CENTRAL_LIVE_WITH_BROKER_FLAT"
    assert metadata["evidence_bingx_positions"] == 0
    assert metadata["evidence_central_live_positions"] == 1
    assert metadata["manual_user_close_suspected"] is True
    assert metadata["stop_anomaly_suspected"] is True
    assert metadata["original_sl"] == pytest.approx(1.1294)
    assert metadata["outcome_status"] == "RECONCILED_WITHOUT_PNL"
    assert metadata["financial_reconciliation_pending"] is True
    assert metadata["learning_eligible"] is False


def test_broker_flat_only_commit_does_not_invent_exit_price_pnl_or_outcome(tmp_path):
    harness = _harness(tmp_path)

    _build(harness, commit=True, ack=ACK)
    closed = _closed_trade(harness)
    call = harness.registry.close_calls[0]

    assert closed["exit_price"] is None
    assert closed["pnl_pct"] is None
    assert closed["pnl_r"] is None
    assert call["exit_price"] is None
    assert call["pnl_pct"] is None
    assert call["pnl_r"] is None
    assert call["broker_close_order_id"] is None
    assert call["outcome_status"] == "RECONCILED_WITHOUT_PNL"
    assert call["learning_eligible"] is False
    assert "realized_pnl" not in call
    assert "fee" not in call


def test_reliable_terminal_stop_fill_is_the_only_source_of_close_price_and_quantity(tmp_path):
    position = _base_position()
    position["central_only_evidence"].update(
        {
            "stop_order_status": "FILLED",
            "stop_order_filled": True,
            "stop_order_full_fill_confirmed": True,
            "stop_order_average": 1.1295,
            "stop_order_filled_qty": 8.0,
            "stop_order_id": "STOP-XRP",
            "stop_order_timestamp": "2026-07-15T08:27:00Z",
        }
    )
    harness = _harness(tmp_path, position=position)

    result = _build(harness, commit=True, ack=ACK)
    call = harness.registry.close_calls[0]

    assert result["status"] == "RECONCILED"
    assert call["exit_price"] == pytest.approx(1.1295)
    assert call["broker_close_order_id"] == "STOP-XRP"
    assert call["close_qty"] == pytest.approx(8.0)
    assert call["closed_at"] == "2026-07-15T08:27:00Z"
    assert call["metadata"]["close_qty"] == pytest.approx(8.0)
    assert call["metadata"]["close_evidence_source"] == "BROKER_STOP_FILL"
    assert call["pnl_pct"] is None and call["pnl_r"] is None


def test_partial_terminal_stop_fill_does_not_supply_exit_price_or_close_quantity(tmp_path):
    position = _base_position()
    position["central_only_evidence"].update(
        {
            "stop_order_status": "FILLED",
            "stop_order_filled": True,
            # Defense in depth: even a malformed persisted full-fill flag must
            # not override the independently reconciled lifecycle quantity.
            "stop_order_full_fill_confirmed": True,
            "stop_order_average": 1.1295,
            "stop_order_filled_qty": 2.0,
            "stop_order_id": "STOP-XRP",
        }
    )
    harness = _harness(tmp_path, position=position)

    result = _build(harness, commit=True, ack=ACK)
    call = harness.registry.close_calls[0]

    assert result["status"] == "RECONCILED"
    assert call["exit_price"] is None
    assert call["broker_close_order_id"] is None
    assert call["close_qty"] is None
    assert call["metadata"]["close_evidence_source"] == "BROKER_FLAT_ONLY"


def test_cancelled_stop_with_stale_fill_flags_never_supplies_financial_close_evidence(tmp_path):
    position = _base_position()
    position["central_only_evidence"].update(
        {
            "stop_order_status": "CANCELED",
            "stop_order_filled": True,
            "stop_order_full_fill_confirmed": True,
            "stop_order_average": 1.1295,
            "stop_order_filled_qty": 8.0,
            "stop_order_id": "STOP-XRP",
        }
    )
    harness = _harness(tmp_path, position=position)

    result = _build(harness, commit=True, ack=ACK)
    call = harness.registry.close_calls[0]

    assert result["status"] == "RECONCILED"
    assert call["exit_price"] is None
    assert call["broker_close_order_id"] is None
    assert call["close_qty"] is None
    assert call["metadata"]["close_evidence_source"] == "BROKER_FLAT_ONLY"


def test_unknown_financial_outcome_clears_provisional_result_fields(tmp_path):
    trade = _base_trade(
        result_pct=99.0,
        result_r=12.0,
        realized_pnl=50.0,
        realized_pnl_usdt=50.0,
        net_pnl=49.0,
        net_pnl_usdt=49.0,
        pnl_usdt=50.0,
        r_multiple=12.0,
        outcome={"status": "PROVISIONAL", "pnl": 50.0},
        outcome_id="OUT-PROVISIONAL",
        broker_close_order_id="PARTIAL-CLOSE",
        close_order_id="PARTIAL-CLOSE",
        close_qty=2.0,
        fee=1.0,
        funding=0.5,
    )
    harness = _harness(tmp_path, trade=trade)

    _build(harness, commit=True, ack=ACK)
    closed = _closed_trade(harness)

    assert closed["pnl_pct"] is None and closed["pnl_r"] is None
    assert closed["result_pct"] is None and closed["result_r"] is None
    assert closed["realized_pnl"] is None
    assert closed["realized_pnl_usdt"] is None
    assert closed["net_pnl"] is None and closed["net_pnl_usdt"] is None
    assert closed["pnl_usdt"] is None and closed["r_multiple"] is None
    assert closed["outcome"] is None and closed["outcome_id"] is None
    assert closed["broker_close_order_id"] is None
    assert closed["close_order_id"] is None and closed["close_qty"] is None
    assert closed["fee"] is None and closed["funding"] is None
    assert closed["financial_reconciliation_pending"] is True
    assert closed["learning_eligible"] is False


@pytest.mark.parametrize(
    ("evidence_updates", "expected_reason"),
    [
        ({"broker_flat": False, "position_closed": False, "position_qty": 8.0, "matched_count": 1}, "BROKER_FLAT_NOT_CONFIRMED"),
        ({"checked_epoch": FIXED_EPOCH - 301}, "BROKER_FLAT_EVIDENCE_STALE"),
        ({"stop_order_active": True, "stop_order_status": "ACTIVE"}, "STOP_TERMINAL_STATE_NOT_CONFIRMED"),
    ],
)
def test_open_broker_stale_evidence_or_active_stop_is_fail_closed(tmp_path, evidence_updates, expected_reason):
    position = _base_position()
    position["central_only_evidence"].update(evidence_updates)
    harness = _harness(tmp_path, position=position)

    result = _build(harness, commit=True, ack=ACK)

    assert result["reconciled_count"] == 0
    assert result["registry_closed_count"] == 0
    assert result["skipped_count"] == 1
    assert expected_reason in result["skipped_samples"][0]["skip_reasons"]
    assert "TR-XRP" in harness.registry.payload["open_trades"]
    assert "POS-XRP" in harness.module.positions
    assert not harness.registry.close_calls
    assert not harness.module.remove_calls


def test_registry_trade_owned_by_another_bot_is_never_reconciled(tmp_path):
    harness = _harness(tmp_path, trade=_base_trade(bot="PREDATOR"))

    result = _build(harness, commit=True, ack=ACK)

    assert result["reconciled_count"] == 0
    assert "REGISTRY_BOT_NOT_FALCON" in result["skipped_samples"][0]["skip_reasons"]
    assert harness.registry.payload["closed_trades"] == []
    assert not harness.module.remove_calls


def test_symbol_and_side_without_a_matching_strong_id_never_prove_ownership(tmp_path):
    trade = _base_trade(lifecycle_id="LC-OTHER", broker_order_id="ORDER-OTHER", client_order_id="CLIENT-OTHER")
    harness = _harness(tmp_path, trade=trade)

    result = _build(harness, commit=True, ack=ACK)

    reasons = result["skipped_samples"][0]["skip_reasons"]
    assert result["reconciled_count"] == 0
    assert "REGISTRY_LIFECYCLE_ID_MISMATCH" in reasons
    assert "REGISTRY_ORDER_ID_MISMATCH" in reasons
    assert "REGISTRY_CLIENT_ORDER_ID_MISMATCH" in reasons
    assert "REGISTRY_STRONG_IDENTITY_MATCH_REQUIRED" in reasons
    assert not harness.registry.close_calls


def test_broker_flat_evidence_without_a_strong_bound_identity_is_never_eligible(tmp_path):
    position = _base_position()
    for field in ("lifecycle_id", "order_id", "client_order_id"):
        position["central_only_evidence"].pop(field, None)
    harness = _harness(tmp_path, position=position)

    result = _build(harness, commit=True, ack=ACK)

    assert result["reconciled_count"] == 0
    assert "BROKER_EVIDENCE_STRONG_IDENTITY_REQUIRED" in result["skipped_samples"][0]["skip_reasons"]
    assert not harness.registry.close_calls
    assert "POS-XRP" in harness.module.positions


def test_malformed_broker_count_is_reported_fail_closed_without_crashing_preview(tmp_path):
    position = _base_position()
    position["central_only_evidence"]["matched_count"] = "invalid"
    harness = _harness(tmp_path, position=position)

    result = _build(harness)

    assert result["status"] == "PREVIEW_BLOCKED"
    assert result["bingx_positions_before"] == 0
    assert result["planned_count"] == 0
    assert result["skipped_count"] == 1
    assert "BROKER_MATCHED_POSITION_PRESENT" in result["skipped_samples"][0]["skip_reasons"]


def test_commit_is_idempotent_and_does_not_duplicate_close_pnl_or_outcome(tmp_path):
    harness = _harness(tmp_path)

    first = _build(harness, commit=True, ack=ACK)
    second = _build(harness, commit=True, ack=ACK)

    assert first["status"] == "RECONCILED"
    assert second["status"] == "ALREADY_RECONCILED"
    assert second["idempotent"] is True
    assert second["reconciled_count"] == 0
    assert len(harness.registry.close_calls) == 1
    assert len(harness.module.remove_calls) == 1
    assert len(harness.registry.payload["closed_trades"]) == 1
    closed = _closed_trade(harness)
    assert closed["pnl_pct"] is None and closed["pnl_r"] is None
    assert closed.get("outcome_status") == "RECONCILED_WITHOUT_PNL"


def test_exact_registry_closed_trade_allows_stale_module_cleanup_without_second_close(tmp_path):
    harness = _harness(tmp_path)
    already_closed = harness.registry.payload["open_trades"].pop("TR-XRP")
    already_closed.update({"status": "CLOSED", "close_reason": "STOP_BROKER_CONFIRMED", "closed_at": FIXED_NOW})
    harness.registry.payload["closed_trades"].append(already_closed)

    result = _build(harness, commit=True, ack=ACK)

    assert result["status"] == "RECONCILED"
    assert result["registry_closed_count"] == 0
    assert result["reconciled_count"] == 1
    assert harness.registry.close_calls == []
    assert harness.module.positions == {}
    assert len(harness.registry.payload["closed_trades"]) == 1


def test_stale_cleanup_selects_exact_lifecycle_when_trade_id_has_multiple_closed_records(tmp_path):
    harness = _harness(tmp_path)
    exact = harness.registry.payload["open_trades"].pop("TR-XRP")
    exact.update({"status": "CLOSED", "close_reason": "FACTUAL_CLOSE", "closed_at": FIXED_NOW})
    replacement = copy.deepcopy(exact)
    replacement.update(
        {
            "lifecycle_id": "LC-NEW",
            "broker_order_id": "ORDER-NEW",
            "client_order_id": "CLIENT-NEW",
        }
    )
    harness.registry.payload["closed_trades"].extend([exact, replacement])

    result = _build(harness, commit=True, ack=ACK)

    assert result["status"] == "RECONCILED"
    assert result["registry_closed_count"] == 0
    assert harness.registry.close_calls == []
    assert harness.module.positions == {}
    assert len(harness.registry.payload["closed_trades"]) == 2


def test_registry_close_failure_keeps_module_position_and_returns_blocked(tmp_path):
    harness = _harness(tmp_path, fail_registry_close=True)

    result = _build(harness, commit=True, ack=ACK)

    assert result["status"] == "PARTIAL_OR_BLOCKED"
    assert result["committed"] is False
    assert result["registry_closed_count"] == 0
    assert result["reconciled_count"] == 0
    assert any(error.startswith("REGISTRY_CLOSE_FAILED:TR-XRP") for error in result["errors"])
    assert "TR-XRP" in harness.registry.payload["open_trades"]
    assert "POS-XRP" in harness.module.positions
    assert harness.operation_log == ["registry_close"]
    assert not harness.module.remove_calls


def test_module_remove_failure_never_rolls_registry_back_or_sends_an_order(tmp_path):
    harness = _harness(tmp_path, fail_module_remove=True)

    result = _build(harness, commit=True, ack=ACK)

    assert result["status"] == "PARTIAL_OR_BLOCKED"
    assert result["registry_closed_count"] == 1
    assert result["reconciled_count"] == 0
    assert harness.operation_log == ["registry_close", "module_remove"]
    assert harness.registry.payload["open_trades"] == {}
    assert len(harness.registry.payload["closed_trades"]) == 1
    assert "POS-XRP" in harness.module.positions
    assert result["no_order_sent_by_this_route"] is True
    assert result["broker_called_by_this_route"] is False


def test_factual_pending_health_clears_only_after_successful_reconciliation(tmp_path):
    harness = _harness(tmp_path)

    before = harness.ns["_fcor_v1_health_overlay"]()
    result = _build(harness, commit=True, ack=ACK)
    after = harness.ns["_fcor_v1_health_overlay"]()

    assert before["falcon_central_only_reconcile_status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert before["falcon_central_only_pending_count"] == 1
    assert result["only_central_after"] == 0
    assert after["falcon_central_only_reconcile_status"] == "RECONCILED"
    assert after["falcon_central_only_pending_count"] == 0
    assert after["falcon_central_only_last_reconciled_count"] == 1


def test_wrong_ack_cannot_clear_the_factual_pending_health_state(tmp_path):
    harness = _harness(tmp_path)

    _build(harness, commit=True, ack="WRONG")
    health = harness.ns["_fcor_v1_health_overlay"]()

    assert health["falcon_central_only_reconcile_status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert health["falcon_central_only_pending_count"] == 1
    assert "POS-XRP" in harness.module.positions


def test_text_report_exposes_required_safety_counts_identity_and_storage(tmp_path):
    harness = _harness(tmp_path)
    payload = _build(harness)

    text = harness.ns["_fcor_v1_text"](payload)

    for expected in (
        "Status: PREVIEW_READY",
        "Commit solicitado: False",
        "ACK correto: False",
        "Committed: False",
        "execution_mode: BINGX_AUTO",
        "ENABLE_REAL_TRADING: True",
        "BROKER_DRY_RUN:",
        "no_order_sent_by_this_route: True",
        "would_send_order: False",
        "Central LIVE: 1 -> 1",
        "BingX positions (evidencia factual pre-commit; sem nova chamada pelo endpoint): 0 -> 0",
        "BingX rechecked after commit: False",
        "So na Central: 1 -> 1",
        "XRPUSDT SHORT",
        "order=2077392837327147008",
        "client=FALCON-LIVE-FALCON15-1784124020",
        "lifecycle=LC-XRP",
        "CENTRAL_LIVE_WITH_BROKER_FLAT",
        str(tmp_path / "latest.json"),
        str(tmp_path / "events.jsonl"),
    ):
        assert expected in text


def test_reconciliation_block_has_no_broker_exchange_order_cancel_or_runtime_calls():
    source = MAIN.read_text(encoding="utf-8")
    start = source.index("# FALCON CENTRAL-ONLY MANUAL CLOSE RECONCILIATION V1")
    end = source.index('if __name__ == "__main__":', start)
    block = source[start:end]
    tree = ast.parse(block)
    call_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            call_names.add(node.func.attr)
    forbidden = {
        "create_order",
        "cancel_order",
        "place_market_order",
        "managed_close_position_market",
        "managed_position_snapshot",
        "managed_order_snapshot",
        "fetch_positions",
        "fetch_open_orders",
        "reconcile_closed_trade",
        "send_order",
        "start",
        "run",
    }
    assert call_names.isdisjoint(forbidden), sorted(call_names & forbidden)
    for forbidden_import in ("broker", "ccxt", "requests", "socket", "execution_engine", "execution_orchestrator"):
        assert not any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and (
                (isinstance(node, ast.ImportFrom) and str(node.module or "").split(".")[0] == forbidden_import)
                or (isinstance(node, ast.Import) and any(alias.name.split(".")[0] == forbidden_import for alias in node.names))
            )
            for node in ast.walk(tree)
        )


def test_route_does_not_modify_real_trading_configuration_or_ack_the_live_audit():
    source = MAIN.read_text(encoding="utf-8")
    start = source.index("# FALCON CENTRAL-ONLY MANUAL CLOSE RECONCILIATION V1")
    end = source.index('if __name__ == "__main__":', start)
    block = source[start:end]

    assert "ENABLE_REAL_TRADING =" not in block
    assert "BROKER_DRY_RUN =" not in block
    assert "CENTRAL_REAL_EXECUTION_ENABLED =" not in block
    assert "falcon_live_execution_audit_guard_v1_ack" not in block
    assert "clear_block" not in block


def test_trade_registry_compare_and_close_blocks_replaced_lifecycle_and_clears_unknown_financials(tmp_path, monkeypatch):
    import trade_registry

    registry_file = tmp_path / "registry.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(registry_file))
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_LEGACY_FILE", str(tmp_path / "missing-legacy.json"))
    monkeypatch.setattr(trade_registry, "_observe_shadow_registry_snapshot", lambda *_args, **_kwargs: None)
    open_trade = _base_trade(
        result_pct=42.0,
        result_r=7.0,
        realized_pnl=12.0,
        realized_pnl_usdt=12.0,
        net_pnl=11.5,
        pnl_usdt=12.0,
        r_multiple=7.0,
        outcome={"status": "PROVISIONAL"},
        outcome_id="OUT-PROVISIONAL",
        broker_close_order_id="PARTIAL-CLOSE",
        close_order_id="PARTIAL-CLOSE",
        close_qty=2.0,
    )
    trade_registry.save_registry({"open_trades": {"TR-XRP": open_trade}, "closed_trades": []})

    blocked = trade_registry.close_trade(
        "TR-XRP",
        reason="CENTRAL_ONLY_BROKER_FLAT_RECONCILED",
        expected_identity={"lifecycle_id": "LC-REPLACED", "order_id": "OTHER-ORDER"},
        clear_financial_results=True,
    )

    assert blocked["ok"] is False
    assert blocked["error"] == "TRADE_IDENTITY_MISMATCH"
    assert "TR-XRP" in trade_registry.load_registry()["open_trades"]

    closed = trade_registry.close_trade(
        "TR-XRP",
        reason="CENTRAL_ONLY_BROKER_FLAT_RECONCILED",
        expected_identity={"lifecycle_id": "LC-XRP", "order_id": "2077392837327147008"},
        clear_financial_results=True,
        financial_reconciliation_pending=True,
        learning_eligible=False,
    )

    assert closed["ok"] is True
    trade = closed["trade"]
    assert trade["result_pct"] is None and trade["result_r"] is None
    assert trade["realized_pnl"] is None
    assert trade["realized_pnl_usdt"] is None
    assert trade["net_pnl"] is None and trade["pnl_usdt"] is None
    assert trade["r_multiple"] is None
    assert trade["outcome"] is None and trade["outcome_id"] is None
    assert trade["broker_close_order_id"] is None
    assert trade["close_order_id"] is None and trade["close_qty"] is None
    assert trade["financial_reconciliation_pending"] is True
    assert trade["learning_eligible"] is False


def test_trade_registry_default_close_behavior_remains_compatible_for_other_bots(tmp_path, monkeypatch):
    import trade_registry

    registry_file = tmp_path / "registry-default.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(registry_file))
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_LEGACY_FILE", str(tmp_path / "missing-legacy.json"))
    monkeypatch.setattr(trade_registry, "_observe_shadow_registry_snapshot", lambda *_args, **_kwargs: None)
    paper_trade = _base_trade(
        trade_id="TR-PREDATOR",
        bot="PREDATOR",
        registry_mode="PAPER",
        execution_mode="PAPER",
        result_pct=9.0,
    )
    trade_registry.save_registry({"open_trades": {"TR-PREDATOR": paper_trade}, "closed_trades": []})

    result = trade_registry.close_trade(
        "TR-PREDATOR",
        exit_price=1.2,
        pnl_pct=1.5,
        pnl_r=0.75,
        reason="TEST_CLOSE",
    )

    assert result["ok"] is True
    trade = result["trade"]
    assert trade["bot"] == "PREDATOR"
    assert trade["result_pct"] == pytest.approx(1.5)
    assert trade["result_r"] == pytest.approx(0.75)


def test_trade_registry_compare_and_close_never_overwrites_a_concurrent_factual_close(tmp_path, monkeypatch):
    import trade_registry

    registry_file = tmp_path / "registry-concurrent-close.json"
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_FILE", str(registry_file))
    monkeypatch.setattr(trade_registry, "TRADE_REGISTRY_LEGACY_FILE", str(tmp_path / "missing-legacy.json"))
    monkeypatch.setattr(trade_registry, "_observe_shadow_registry_snapshot", lambda *_args, **_kwargs: None)
    trade_registry.save_registry({"open_trades": {"TR-XRP": _base_trade()}, "closed_trades": []})

    factual = trade_registry.close_trade(
        "TR-XRP",
        exit_price=1.11,
        pnl_pct=1.25,
        pnl_r=0.5,
        reason="FACTUAL_BROKER_CLOSE",
        metadata={"factual_close": True},
    )
    reconciler = trade_registry.close_trade(
        "TR-XRP",
        reason="CENTRAL_ONLY_BROKER_FLAT_RECONCILED",
        expected_identity={"lifecycle_id": "LC-XRP", "order_id": "2077392837327147008"},
        clear_financial_results=True,
        metadata={"reconciled_by": "must-not-overwrite"},
    )

    assert factual["ok"] is True
    assert reconciler["ok"] is True
    assert reconciler["action"] == "TRADE_ALREADY_CLOSED"
    closed = trade_registry.get_closed_trade(trade_id="TR-XRP")["trade"]
    assert closed["close_reason"] == "FACTUAL_BROKER_CLOSE"
    assert closed["exit_price"] == pytest.approx(1.11)
    assert closed["result_pct"] == pytest.approx(1.25)
    assert closed["metadata"]["factual_close"] is True
    assert "reconciled_by" not in closed["metadata"]
