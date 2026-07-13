from __future__ import annotations

import ast
import json
import logging
import re
from pathlib import Path

import pytest


FUNCTIONS = {
    "_predator_registry_trade_id",
    "_predator_registry_safe_text",
    "_predator_registry_close_log",
    "registrar_trade_registry_close_predator",
    "encerrar_posicao",
}


def _load_functions(namespace):
    source = Path("bots/predator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "bots/predator.py", "exec"), namespace)
    return namespace


@pytest.fixture()
def harness(caplog):
    calls = {"close": [], "register": 0, "shadow": 0}

    def close_trade(trade_id, **kwargs):
        calls["close"].append((trade_id, kwargs))
        return {"ok": True, "action": "TRADE_CLOSED"}

    namespace = {
        "json": json,
        "re": re,
        "LOGGER": logging.getLogger("test.predator.registry.close"),
        "TRADE_REGISTRY_LOADED": True,
        "close_trade": close_trade,
        "make_trade_id": lambda bot, symbol, side, setup: f"{bot}:{setup}:{symbol}:{side}",
        "nome_limpo": lambda value: str(value or "").replace("/", ""),
    }
    caplog.set_level(logging.INFO, logger="test.predator.registry.close")
    _load_functions(namespace)
    return namespace, calls, caplog


def _position(**updates):
    position = {
        "symbol": "BCH/USDT",
        "symbol_clean": "BCHUSDT",
        "side": "LONG",
        "signal_type": "SMART_PREDATOR",
        "trade_registry_id": "PREDATOR:SMART_PREDATOR:BCHUSDT:LONG",
        "entry": 240.04,
        "risk_pct": 1.0,
        "mfe_max_pct": 1.61,
        "mae_min_pct": -0.1,
        "tp50_hit": True,
        "management_cycles": 10,
    }
    position.update(updates)
    return position


def _messages(caplog):
    return "\n".join(record.getMessage() for record in caplog.records)


def test_valid_registry_id_and_trade_closed_result(harness):
    namespace, calls, caplog = harness
    result = namespace["registrar_trade_registry_close_predator"](_position(), 243.26067426, 1.34, 1.34, "TRAIL")
    assert result == {
        "ok": True,
        "status": "TRADE_CLOSED",
        "attempted": True,
        "trade_id": "PREDATOR:SMART_PREDATOR:BCHUSDT:LONG",
        "registry_result": {"ok": True, "status": "TRADE_CLOSED", "action": "TRADE_CLOSED", "reason": None, "error": None},
    }
    assert len(calls["close"]) == 1
    assert calls["close"][0][0] == result["trade_id"]
    logs = _messages(caplog)
    assert "PREDATOR_REGISTRY_CLOSE_ATTEMPT" in logs
    assert "PREDATOR_REGISTRY_CLOSE_RESULT" in logs
    assert '"bot": "PREDATOR"' in logs and '"setup": "SMART_PREDATOR"' in logs


@pytest.mark.parametrize("raw", [None, object(), {"unexpected": "value"}])
def test_none_or_malformed_result_is_unknown_and_fail_open(harness, raw):
    namespace, calls, caplog = harness
    namespace["close_trade"] = lambda *args, **kwargs: calls["close"].append((args[0], kwargs)) or raw
    result = namespace["registrar_trade_registry_close_predator"](_position(), 243.26067426, 1.34, 1.34, "TRAIL")
    assert result["ok"] is False and result["status"] == "UNKNOWN_RESULT" and result["attempted"] is True
    assert len(calls["close"]) == 1
    assert "PREDATOR_REGISTRY_CLOSE_RESULT" in _messages(caplog)


def test_trade_not_found_incident_is_structured_without_retry_or_repair(harness):
    namespace, calls, caplog = harness
    namespace["close_trade"] = lambda *args, **kwargs: calls["close"].append((args[0], kwargs)) or {"ok": False, "status": "TRADE_NOT_FOUND"}
    namespace["register_open_trade"] = lambda *args, **kwargs: calls.__setitem__("register", calls["register"] + 1)
    namespace["safe_observe_shadow_event"] = lambda *args, **kwargs: calls.__setitem__("shadow", calls["shadow"] + 1)
    result = namespace["registrar_trade_registry_close_predator"](_position(trade_registry_id=None), 243.26067426, 1.34, 1.34, "TRAIL")
    assert result["status"] == "TRADE_NOT_FOUND" and result["attempted"] is True
    assert result["trade_id"] == "PREDATOR:SMART_PREDATOR:BCHUSDT:LONG"
    assert len(calls["close"]) == 1 and calls["register"] == 0 and calls["shadow"] == 0
    logs = _messages(caplog)
    assert "PREDATOR_REGISTRY_CLOSE_ATTEMPT" in logs
    assert "PREDATOR_REGISTRY_CLOSE_RESULT" in logs
    assert "TRADE_NOT_FOUND" in logs


def test_exception_is_sanitized_truncated_and_fail_open(harness):
    namespace, calls, caplog = harness
    secret = "TOKEN-SHOULD-NOT-BE-LOGGED"

    def fail(*args, **kwargs):
        calls["close"].append((args[0], kwargs))
        raise RuntimeError("line one\ntoken=" + secret + " " + ("x" * 400))

    namespace["close_trade"] = fail
    result = namespace["registrar_trade_registry_close_predator"](_position(secret_payload=secret), 243.26067426, 1.34, 1.34, "TRAIL")
    logs = _messages(caplog)
    assert result["status"] == "ERROR" and result["attempted"] is True
    assert len(calls["close"]) == 1
    assert "PREDATOR_REGISTRY_CLOSE_EXCEPTION" in logs
    assert all("\n" not in record.getMessage() for record in caplog.records)
    assert secret not in logs
    assert "headers" not in logs.lower() and "payload" not in logs.lower() and "token" not in logs.lower()


@pytest.mark.parametrize(
    "loaded,closer,expected",
    [
        (False, lambda *args, **kwargs: None, "REGISTRY_NOT_LOADED"),
        (True, None, "CLOSE_TRADE_NOT_CALLABLE"),
    ],
)
def test_registry_unavailable_is_skipped(harness, loaded, closer, expected):
    namespace, calls, caplog = harness
    namespace["TRADE_REGISTRY_LOADED"] = loaded
    namespace["close_trade"] = closer
    result = namespace["registrar_trade_registry_close_predator"](_position(), 243.26067426, 1.34, 1.34, "TRAIL")
    assert result["status"] == expected and result["attempted"] is False
    assert calls["close"] == []
    assert "PREDATOR_REGISTRY_CLOSE_SKIPPED" in _messages(caplog)


def test_missing_trade_id_is_skipped(harness):
    namespace, calls, caplog = harness
    namespace["_predator_registry_trade_id"] = lambda *args, **kwargs: ""
    result = namespace["registrar_trade_registry_close_predator"](_position(trade_registry_id=None), 243.26067426, 1.34, 1.34, "TRAIL")
    assert result["status"] == "MISSING_TRADE_ID" and result["attempted"] is False
    assert calls["close"] == []
    assert "PREDATOR_REGISTRY_CLOSE_SKIPPED" in _messages(caplog)


def test_local_trail_close_continues_when_registry_returns_not_found(harness):
    namespace, calls, caplog = harness
    saved_positions = []
    saved_events = []
    telegram = []
    namespace.update(
        {
            "close_trade": lambda *args, **kwargs: calls["close"].append((args[0], kwargs)) or {"ok": False, "status": "TRADE_NOT_FOUND"},
            "carregar_posicoes": lambda: {},
            "salvar_posicoes": lambda positions: saved_positions.append(positions),
            "registrar_evento_trade": lambda event: saved_events.append(event),
            "safe_send_telegram": lambda message: telegram.append(message),
            "mensagem_saida": lambda *args: "TRAIL MESSAGE",
            "pnl_pct": lambda side, entry, exit_price: 1.34,
            "pct_to_r": lambda value, risk: value / risk if risk else 0.0,
            "data_hora_sp_str": lambda: "2026-07-12 12:00:00",
            "data_hoje_sp_str": lambda: "2026-07-12",
            "time": type("Clock", (), {"time": staticmethod(lambda: 1.0)}),
        }
    )
    position = _position(trade_registry_id=None, trailing_active=True)
    namespace["encerrar_posicao"]("BCH/USDT", position, 243.26067426, "TRAIL")
    assert position["status"] == "ENCERRADO" and position["close_reason"] == "TRAIL"
    assert saved_positions and saved_events and telegram == ["TRAIL MESSAGE"]
    assert len(calls["close"]) == 1
    assert "TRADE_NOT_FOUND" in _messages(caplog)
