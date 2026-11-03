from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_function(relative_path: str, function_name: str, namespace: dict):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, relative_path, "exec"), namespace)
    return namespace[function_name]


def _connector_namespace(name: str, *, mode: str, enabled: bool, fail_closed: bool):
    prefix = name.upper()
    namespace = {
        "EXECUTION_MODE": mode,
        f"{prefix}_CENTRAL_RISK_ENABLED": enabled,
        f"{prefix}_CENTRAL_RISK_FAIL_CLOSED": fail_closed,
        f"{prefix}_CENTRAL_RISK_TIMEOUT": 1,
        "data_hora_sp_str": lambda: "synthetic-time",
        "nome_limpo": lambda value: str(value or "").replace("/USDT", "USDT"),
        "central_can_open_trade_url": lambda: "https://central.invalid/can_open_trade",
        "central_personal_http_auth": lambda _url: ("test-user", "test-password"),
    }
    if name == "cobra":
        function_name = "consultar_central_risk_manager"
    elif name == "donkey":
        function_name = "consultar_central_risk_manager"
    else:
        function_name = "consultar_central_risk_manager"
    return namespace, function_name


@pytest.mark.parametrize("bot", ["cobra", "donkey", "trendpro"])
def test_live_mode_disabling_central_risk_is_denied(bot):
    namespace, function_name = _connector_namespace(
        bot, mode="LIVE", enabled=False, fail_closed=False
    )
    function = _load_function(f"bots/{bot}.py", function_name, namespace)

    result = function({"symbol": "BTC/USDT", "side": "LONG"})

    assert result["allowed"] is False
    assert result["decision"] == "DENY"
    assert result["source"] == "local_disabled"


@pytest.mark.parametrize("bot", ["cobra", "donkey", "trendpro"])
def test_live_http_error_is_denied_even_if_fail_open_override_is_false(bot):
    namespace, function_name = _connector_namespace(
        bot, mode="LIVE", enabled=True, fail_closed=False
    )

    class Response:
        status_code = 503
        text = "synthetic unavailable"

        @staticmethod
        def json():
            raise ValueError("synthetic non-JSON response")

    namespace["requests"] = SimpleNamespace(post=lambda *args, **kwargs: Response())
    if bot == "cobra":
        namespace["COBRA_CENTRAL_RISK_TIMEOUT"] = 1
    elif bot == "donkey":
        namespace["DONKEY_CENTRAL_RISK_TIMEOUT"] = 1
    else:
        namespace["TRENDPRO_CENTRAL_RISK_TIMEOUT"] = 1

    function = _load_function(f"bots/{bot}.py", function_name, namespace)
    result = function({"symbol": "BTC/USDT", "side": "LONG"})

    assert result["allowed"] is False
    assert result["decision"] == "DENY"
    assert result["source"] == "http_error"


@pytest.mark.parametrize("bot", ["cobra", "donkey", "trendpro"])
def test_paper_mode_keeps_explicit_local_risk_override_compatible(bot):
    namespace, function_name = _connector_namespace(
        bot, mode="PAPER", enabled=False, fail_closed=False
    )
    function = _load_function(f"bots/{bot}.py", function_name, namespace)

    result = function({"symbol": "BTC/USDT", "side": "LONG"})

    assert result["allowed"] is True
    assert result["decision"] == "ALLOW"


def test_predator_live_mode_requires_central_risk_even_when_flag_is_disabled():
    namespace = {
        "PREDATOR_MODE": "LIVE",
        "PREDATOR_REQUIRE_CENTRAL_RISK": False,
        "PREDATOR_REAL_MARGIN_USDT": 0,
        "PREDATOR_REAL_LEVERAGE": 0,
        "PREDATOR_REAL_NOTIONAL_USDT": 0,
        "nome_limpo": lambda value: str(value or ""),
    }
    function = _load_function("bots/predator.py", "central_can_open_trade", namespace)

    result = function({"symbol": "BTC/USDT", "side": "LONG"})

    assert result["allowed"] is False
    assert result["decision"] == "DENY"
    assert "obrigatório" in result["reasons"][0]
