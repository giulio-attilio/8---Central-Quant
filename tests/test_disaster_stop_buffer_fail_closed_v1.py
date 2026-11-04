from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest
import broker


ROOT = Path(__file__).resolve().parents[1]
BROKER_SOURCE = ROOT / "broker.py"


def _load_broker_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert definitions, name
        selected.append(definitions[-1])
    module = ast.Module(
        body=sorted(selected, key=lambda node: node.lineno),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = {"math": math, **globals_dict}
    exec(compile(module, str(BROKER_SOURCE), "exec"), namespace)
    return namespace


_PREPARATION_FUNCTIONS = (
    "_safe_float_broker",
    "validate_disaster_stop_price",
    "_apply_disaster_stop_buffer",
    "_prepare_buffered_disaster_stop",
    "_live_disaster_stop_preflight",
)


def _load_preparation(buffer_pct: float):
    return _load_broker_functions(
        _PREPARATION_FUNCTIONS,
        {"DISASTER_STOP_PRICE_BUFFER_PCT": buffer_pct},
    )


def _load_live_preflight(*, enabled: bool, required: bool, buffer_pct: float):
    return _load_broker_functions(
        (*_PREPARATION_FUNCTIONS,),
        {
            "DISASTER_STOP_ENABLED": enabled,
            "DISASTER_STOP_REQUIRE_FOR_LIVE": required,
            "DISASTER_STOP_PRICE_BUFFER_PCT": buffer_pct,
        },
    )


@pytest.mark.parametrize("buffer_pct", [float("nan"), float("inf"), float("-inf"), -0.01])
def test_buffered_stop_rejects_nonfinite_or_negative_configuration(buffer_pct):
    ns = _load_preparation(buffer_pct)

    result = ns["_prepare_buffered_disaster_stop"]("LONG", 100.0, 90.0)

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_BUFFER_INVALID"
    assert result["stop_price"] is None


@pytest.mark.parametrize("side,entry,stop,pct,expected", [
    ("LONG", 100.0, 90.0, 0.0, 90.0),
    ("LONG", 100.0, 90.0, 1.0, 89.1),
    ("SHORT", 100.0, 110.0, 1.0, 111.1),
])
def test_buffered_stop_returns_only_finite_side_valid_trigger(side, entry, stop, pct, expected):
    ns = _load_preparation(pct)

    result = ns["_prepare_buffered_disaster_stop"](side, entry, stop)

    assert result["ok"] is True
    assert result["stop_price"] == pytest.approx(expected)
    assert math.isfinite(result["stop_price"])
    assert result["buffered_validation"]["ok"] is True


def test_live_preflight_blocks_required_stop_when_feature_is_disabled():
    ns = _load_live_preflight(enabled=False, required=True, buffer_pct=0.0)

    result = ns["_live_disaster_stop_preflight"]("LONG", 100.0, 90.0)

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_REQUIRED_BUT_DISABLED"


def test_live_preflight_allows_disabled_optional_stop():
    ns = _load_live_preflight(enabled=False, required=False, buffer_pct=0.0)

    result = ns["_live_disaster_stop_preflight"]("LONG", 100.0, 90.0)

    assert result["ok"] is True
    assert result["status"] == "DISASTER_STOP_NOT_REQUIRED_AND_DISABLED"


def test_live_preflight_checks_invalid_buffer_even_when_stop_is_optional():
    ns = _load_live_preflight(enabled=True, required=False, buffer_pct=float("nan"))

    result = ns["_live_disaster_stop_preflight"]("LONG", 100.0, 90.0)

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_BUFFER_INVALID"


def _load_create_stop(buffer_pct: float):
    diagnostic_calls = []
    globals_dict = {
        "DISASTER_STOP_ENABLED": True,
        "DISASTER_STOP_PRICE_BUFFER_PCT": buffer_pct,
        "_broker_factual_writes_enabled": lambda: True,
        "normalize_symbol": lambda value: str(value),
        "normalize_side": lambda value: "buy" if str(value).upper() == "LONG" else "sell",
        "bingx_position_side": lambda value: str(value).upper(),
        "_managed_exception_details": lambda exc: {
            "error": str(exc),
            "error_type": type(exc).__name__,
        },
        "_set_last_disaster_stop_diagnostic": lambda **kwargs: diagnostic_calls.append(kwargs),
        "validate_broker_client_order_id": lambda value, required=True: value,
        "_build_disaster_stop_hedge_mode_fix_payload": lambda *_args, **_kwargs: {
            "reduce_only_sent": False,
            "hedge_mode_detected": True,
            "reduce_only_removed_for_hedge_mode": True,
        },
    }
    names = (*_PREPARATION_FUNCTIONS, "create_disaster_stop_order")
    ns = _load_broker_functions(names, globals_dict)
    return ns["create_disaster_stop_order"], diagnostic_calls


def test_create_stop_rejects_nonfinite_amount_before_any_exchange_call():
    create_stop, diagnostics = _load_create_stop(0.0)

    result = create_stop(
        symbol="BTCUSDT",
        side="LONG",
        amount=float("nan"),
        stop_loss_price=90.0,
        entry_price=100.0,
        client_order_id="CQ-STOP-TEST-1",
    )

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_INVALID_INPUT"
    assert result["send_attempted"] is False
    assert diagnostics


def test_create_stop_rejects_nan_buffer_before_any_exchange_call():
    create_stop, diagnostics = _load_create_stop(float("nan"))

    result = create_stop(
        symbol="BTCUSDT",
        side="LONG",
        amount=0.1,
        stop_loss_price=90.0,
        entry_price=100.0,
        client_order_id="CQ-STOP-TEST-2",
    )

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_BUFFER_INVALID"
    assert result["send_attempted"] is False
    assert diagnostics


def test_live_entry_preflight_validates_buffer_before_entry_send():
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    definitions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "place_market_order"
    ]
    assert definitions
    function = definitions[-1]
    calls = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else None
        )
        if name in {"_live_disaster_stop_preflight", "_create_order_with_reserved_attempt"}:
            calls.append((name, node.lineno))

    prepare_lines = [line for name, line in calls if name == "_live_disaster_stop_preflight"]
    entry_send_lines = [line for name, line in calls if name == "_create_order_with_reserved_attempt"]
    assert prepare_lines
    assert entry_send_lines
    assert min(prepare_lines) < min(entry_send_lines)


def test_live_entry_blocks_invalid_stop_buffer_before_exchange_initialization(monkeypatch):
    monkeypatch.setattr(broker, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(broker, "ENABLE_REAL_TRADING", True)
    monkeypatch.setattr(broker, "BROKER_DRY_RUN", False)
    monkeypatch.setattr(broker, "DISASTER_STOP_ENABLED", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_REQUIRE_FOR_LIVE", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_PRICE_BUFFER_PCT", float("nan"))
    monkeypatch.setattr(broker, "is_real_live_send_enabled", lambda: True)
    monkeypatch.setattr(
        broker,
        "execution_config_for_bot",
        lambda **_kwargs: {
            "margin_usdt": 10.0,
            "leverage": 1.0,
            "effective_notional_usdt": 10.0,
        },
    )
    monkeypatch.setattr(broker, "_infer_bot_for_audit", lambda **_kwargs: "FALCON")
    monkeypatch.setattr(
        broker, "_automatic_broker_preview_firewall", lambda **_kwargs: {"blocked": False}
    )
    monkeypatch.setattr(
        broker,
        "build_order_preview",
        lambda *_args, **_kwargs: {
            "ok": True,
            "constraints_ok": True,
            "client_order_id": "TEST-ENTRY-1",
            "amount": 0.1,
            "price_ref": 100.0,
            "notional_usdt": 10.0,
            "planned_exposure_usdt": 10.0,
            "actual_exposure_usdt": 10.0,
        },
    )
    monkeypatch.setattr(
        broker, "validate_broker_client_order_id", lambda value, **_kwargs: value
    )
    monkeypatch.setattr(
        broker,
        "_broker_account_reservation_verification",
        lambda *_args, **_kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        broker, "broker_real_pilot_guard_v1_validate", lambda **_kwargs: {"allowed": True}
    )
    monkeypatch.setattr(
        broker, "validate_execution_auth_token", lambda *_args, **_kwargs: {"ok": True}
    )
    monkeypatch.setattr(broker, "log_execution_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(broker, "log_execution_audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        broker,
        "ready_check",
        lambda **_kwargs: pytest.fail("stop validation must run before ready/exchange setup"),
    )
    monkeypatch.setattr(
        broker,
        "exchange",
        lambda: pytest.fail("invalid stop configuration must block before exchange initialization"),
    )

    result = broker.place_market_order(
        symbol="BTCUSDT",
        side="LONG",
        margin_usdt=10.0,
        leverage=1.0,
        client_tag="TEST-ENTRY-1",
        bot="FALCON",
        execution_auth_token="TEST-ONLY",
        stop_loss_price=90.0,
        falcon_position_ownership_limit={"known": True},
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert result["status"] == "DISASTER_STOP_REQUIRED_BLOCKED"
    assert result["stop_validation"]["status"] == "DISASTER_STOP_BUFFER_INVALID"


def test_paper_entry_stays_preview_only_without_live_preflight_or_exchange(monkeypatch):
    monkeypatch.setattr(broker, "EXECUTION_MODE", "PAPER")
    monkeypatch.setattr(broker, "ENABLE_REAL_TRADING", False)
    monkeypatch.setattr(broker, "BROKER_DRY_RUN", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_ENABLED", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_REQUIRE_FOR_LIVE", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_PRICE_BUFFER_PCT", float("nan"))
    monkeypatch.setattr(broker, "is_real_live_send_enabled", lambda: False)
    monkeypatch.setattr(
        broker,
        "execution_config_for_bot",
        lambda **_kwargs: {
            "margin_usdt": 10.0,
            "leverage": 1.0,
            "effective_notional_usdt": 10.0,
        },
    )
    monkeypatch.setattr(broker, "_infer_bot_for_audit", lambda **_kwargs: "FALCON")
    monkeypatch.setattr(
        broker, "_automatic_broker_preview_firewall", lambda **_kwargs: {"blocked": False}
    )
    monkeypatch.setattr(
        broker,
        "build_order_preview",
        lambda *_args, **_kwargs: {
            "ok": True,
            "constraints_ok": True,
            "client_order_id": "TEST-PAPER-ENTRY-1",
            "amount": 0.1,
            "price_ref": 100.0,
            "notional_usdt": 10.0,
            "planned_exposure_usdt": 10.0,
            "actual_exposure_usdt": 10.0,
        },
    )
    monkeypatch.setattr(broker, "log_execution_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(broker, "log_execution_audit_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        broker,
        "_live_disaster_stop_preflight",
        lambda *_args, **_kwargs: pytest.fail("PAPER must return before LIVE stop preflight"),
    )
    monkeypatch.setattr(
        broker,
        "validate_execution_auth_token",
        lambda *_args, **_kwargs: pytest.fail("PAPER must not consume a live execution token"),
    )
    monkeypatch.setattr(
        broker,
        "exchange",
        lambda: pytest.fail("PAPER must not initialize an exchange client"),
    )

    result = broker.place_market_order(
        symbol="BTCUSDT",
        side="LONG",
        margin_usdt=10.0,
        leverage=1.0,
        client_tag="TEST-PAPER-ENTRY-1",
        bot="FALCON",
        stop_loss_price=90.0,
    )

    assert result["sent"] is False
    assert result["status"] == "DRY_RUN"
    assert result["live_send_enabled"] is False
