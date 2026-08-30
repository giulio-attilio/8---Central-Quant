from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
TREE = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))


def _load_functions(names: set[str], namespace: dict | None = None):
    selected = [
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    found = {node.name for node in selected}
    assert found == names, f"missing functions in main.py: {sorted(names - found)}"
    values = dict(namespace or {})
    exec(
        compile(ast.Module(body=sorted(selected, key=lambda node: node.lineno), type_ignores=[]), str(MAIN), "exec"),
        values,
    )
    return values


def test_guard_enable_flag_never_arms_real_pilot(monkeypatch):
    pilot_keys = [
        "CENTRAL_REAL_PILOT_ENABLED",
        "REAL_PILOT_ENABLED",
        "EXECUTION_REAL_PILOT_ENABLED",
        "BINGX_REAL_PILOT_ENABLED",
    ]
    for key in pilot_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CENTRAL_REAL_PILOT_GUARD_ENABLED", "true")
    namespace = _load_functions(
        {"_rpg_v1_bool", "_rpg_v1_bool_env", "_rpg_v1_real_pilot_enabled"},
        {"os": os},
    )

    enabled, source = namespace["_rpg_v1_real_pilot_enabled"]()

    assert enabled is False
    assert source is None


def test_explicit_real_pilot_flag_is_still_recognized(monkeypatch):
    monkeypatch.setenv("CENTRAL_REAL_PILOT_ENABLED", "true")
    namespace = _load_functions(
        {"_rpg_v1_bool", "_rpg_v1_bool_env", "_rpg_v1_real_pilot_enabled"},
        {"os": os},
    )

    enabled, source = namespace["_rpg_v1_real_pilot_enabled"]()

    assert enabled is True
    assert source == "CENTRAL_REAL_PILOT_ENABLED"


def test_broker_trading_switch_never_arms_central_real_execution(monkeypatch):
    central_keys = [
        "CENTRAL_REAL_EXECUTION_ENABLED",
        "REAL_EXECUTION_ENABLED",
        "EXECUTION_REAL_ENABLED",
        "ENABLE_REAL_EXECUTION",
        "BINGX_REAL_EXECUTION_ENABLED",
    ]
    for key in central_keys:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENABLE_REAL_TRADING", "true")
    namespace = _load_functions(
        {"_rpg_v1_bool", "_rpg_v1_bool_env", "_rpg_v1_real_execution_enabled"},
        {"os": os},
    )

    enabled, source = namespace["_rpg_v1_real_execution_enabled"]()

    assert enabled is False
    assert source is None


def test_broker_without_ready_check_is_not_reported_ready():
    namespace = _load_functions(
        {"_rpg_v1_broker_snapshot"},
        {
            "central_broker": SimpleNamespace(),
            "BROKER_IMPORT_ERROR": None,
        },
    )

    snapshot = namespace["_rpg_v1_broker_snapshot"]()

    assert snapshot["available"] is True
    assert snapshot["ready"]["ok"] is False
    assert snapshot["ready"]["status"] == "BROKER_READY_CHECK_MISSING"


def _load_trade_size(config):
    return _load_functions(
        {
            "_rpg_v1_float",
            "_rpg_v1_int",
            "_rpg_v1_payload_float",
            "_rpg_v1_payload_int",
            "_rpg_v1_trade_size",
        },
        {"real_execution_config_for_bot": lambda _bot: config},
    )["_rpg_v1_trade_size"]


def test_missing_real_trade_size_remains_unproven_instead_of_defaulting_to_twenty():
    trade = _load_trade_size({})({}, "FALCON")

    assert trade["margin_usdt"] is None
    assert trade["notional_usdt"] is None
    assert trade["margin_source"] is None
    assert trade["notional_source"] is None
    assert trade["leverage"] == 1


def test_explicit_notional_and_leverage_still_derive_margin():
    trade = _load_trade_size({})(
        {"notional_usdt": 10, "leverage": 2},
        "FALCON",
    )

    assert trade["notional_usdt"] == 10
    assert trade["leverage"] == 2
    assert trade["margin_usdt"] == 5
    assert trade["margin_source"] == "notional_div_leverage"
