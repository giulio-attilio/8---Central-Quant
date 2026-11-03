from __future__ import annotations

import ast
import socket
from pathlib import Path

import pytest

from exchange_throttle_policy_v1 import (
    is_exchange_throttle_error,
    record_exchange_throttle_cooldown,
    reset_exchange_throttle_backoff,
    reset_exchange_throttle_cooldown_for_tests,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


class FakeExchangeError(Exception):
    pass


class FakeNetworkError(Exception):
    pass


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError('bingx {"code":100410,"msg":"try again later"}'),
        RuntimeError("HTTP 429 Too Many Requests"),
    ],
)
def test_exchange_throttle_classifier_recognizes_explicit_rejection(error):
    assert is_exchange_throttle_error(error) is True


def test_exchange_throttle_classifier_does_not_classify_other_failures():
    assert is_exchange_throttle_error(RuntimeError("temporary socket reset")) is False
    assert is_exchange_throttle_error(ValueError("invalid symbol")) is False


def test_repeated_throttles_use_bounded_exponential_backoff_and_success_reset(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(
        "exchange_throttle_policy_v1.time.monotonic", lambda: clock["now"]
    )
    reset_exchange_throttle_cooldown_for_tests()

    for expected in (60.0, 120.0, 240.0, 300.0, 300.0):
        assert record_exchange_throttle_cooldown() == expected
        clock["now"] += expected

    reset_exchange_throttle_backoff()
    assert record_exchange_throttle_cooldown() == 60.0


def _load_safe_fetch(relative_path, outcomes):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "safe_fetch_ohlcv"
    )
    node.decorator_list = []
    calls = {"fetch": 0, "sleep": []}

    class FakeExchange:
        def fetch_ohlcv(self, *_args, **_kwargs):
            calls["fetch"] += 1
            outcome = outcomes[min(calls["fetch"] - 1, len(outcomes) - 1)]
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    namespace = {
        "RateLimitExceeded": type("RateLimitExceeded", (Exception,), {}),
        "NetworkError": type("NetworkError", (Exception,), {}),
        "ExchangeError": FakeExchangeError,
        "NetworkError": FakeNetworkError,
        "exchange": FakeExchange(),
        "HEALTH": {},
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "time": type("Clock", (), {"sleep": staticmethod(calls["sleep"].append)}),
    }
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, relative_path, "exec"), namespace)
    return namespace["safe_fetch_ohlcv"], calls, namespace


def _load_single_attempt_safe_fetch(relative_path, error_message):
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "safe_fetch_ohlcv"
    )
    calls = {"fetch": 0}
    rate_limit_error = type("RateLimitExceeded", (Exception,), {})

    class FakeExchange:
        def fetch_ohlcv(self, *_args, **_kwargs):
            calls["fetch"] += 1
            raise rate_limit_error(error_message)

    namespace = {
        "RateLimitExceeded": rate_limit_error,
        "NetworkError": type("NetworkError", (Exception,), {}),
        "ExchangeError": type("ExchangeError", (Exception,), {}),
        "exchange": FakeExchange(),
        "to_ccxt_symbol": lambda symbol: symbol,
        "TIMEFRAME": "1h",
        "OHLCV_LIMIT": 100,
        "HEALTH": {"last_error": None, "last_warning": None},
    }
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, relative_path, "exec"), namespace)
    return namespace["safe_fetch_ohlcv"], calls, namespace


@pytest.mark.parametrize("relative_path", ["bots/cobra.py", "bots/donkey.py", "bots/meme.py", "bots/trendpro.py"])
def test_all_scanner_ohlcv_wrappers_stop_retrying_explicit_throttle(relative_path):
    error = FakeExchangeError('bingx {"code":100410,"msg":"try again later"}')
    safe_fetch, calls, namespace = _load_safe_fetch(relative_path, [error])

    assert safe_fetch("BTC/USDT", "1h", 100, max_retries=3) == []
    assert calls["fetch"] == 1
    assert calls["sleep"] == []
    assert "Rate limit OHLCV" in namespace["HEALTH"]["last_warning"]


@pytest.mark.parametrize("relative_path", ["bots/falcon.py", "bots/turtle.py"])
def test_single_attempt_scanners_keep_throttle_as_warning(relative_path):
    safe_fetch, calls, namespace = _load_single_attempt_safe_fetch(
        relative_path,
        'bingx {"code":100410,"msg":"try again later"}',
    )

    assert safe_fetch("BTC/USDT", "1h", 100) is None
    assert calls["fetch"] == 1
    assert namespace["HEALTH"]["last_error"] is None
    assert "100410" in namespace["HEALTH"]["last_warning"]


@pytest.mark.parametrize("relative_path", ["bots/cobra.py", "bots/donkey.py", "bots/meme.py", "bots/trendpro.py"])
def test_all_scanner_ohlcv_wrappers_keep_network_retry(relative_path):
    result = [[1, 2, 3, 4, 5, 6]]
    safe_fetch, calls, _namespace = _load_safe_fetch(
        relative_path,
        [FakeNetworkError("temporary network outage"), result],
    )

    assert safe_fetch("BTC/USDT", "1h", 100, max_retries=3) == result
    assert calls["fetch"] == 2
    assert calls["sleep"] == [1]


def _load_predator_scanner_error_handler():
    tree = ast.parse((ROOT / "bots/predator.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_record_predator_scanner_symbol_error"
    )
    namespace = {
        "HEALTH": {"last_error": None, "last_warning": None},
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "nome_limpo": lambda symbol: symbol,
    }
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "bots/predator.py", "exec"), namespace)
    return namespace["_record_predator_scanner_symbol_error"], namespace["HEALTH"]


def _load_predator_watchdog_status(health):
    tree = ast.parse((ROOT / "bots/predator.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "montar_watchdog_status"
    )
    namespace = {
        "HEALTH": health,
        "minutos_desde_health": lambda _field: 0,
        "WATCHDOG_THRESHOLD_MINUTES": 5,
        "BOT_NAME": "PREDATOR",
        "SERVICE_MODE": "PAPER",
        "WATCHDOG_CHECK_SECONDS": 30,
        "WATCHDOG_ALERT_COOLDOWN_SECONDS": 300,
    }
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "bots/predator.py", "exec"), namespace)
    return namespace["montar_watchdog_status"]


def _load_predator_scanner_cycle_error_handler(health):
    tree = ast.parse((ROOT / "bots/predator.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_record_predator_scanner_cycle_error"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"HEALTH": health}
    exec(compile(module, "bots/predator.py", "exec"), namespace)
    return namespace["_record_predator_scanner_cycle_error"]


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError('bingx {"code":100410,"msg":"try again later"}'),
        RuntimeError("HTTP 429 Too Many Requests"),
        type("RateLimitExceeded", (Exception,), {})("cooldown active"),
    ],
)
def test_predator_rate_limits_become_warnings_not_watchdog_errors(error):
    record_error, health = _load_predator_scanner_error_handler()
    watchdog_status = _load_predator_watchdog_status(health)

    record_error("ALGOUSDT", error)

    assert health["last_error"] is None
    assert "Rate limit BingX OHLCV ALGOUSDT" in health["last_warning"]
    assert watchdog_status()["ok"] is True


def test_predator_throttle_warning_does_not_clear_another_symbols_fatal_error():
    record_error, health = _load_predator_scanner_error_handler()
    watchdog_status = _load_predator_watchdog_status(health)

    record_error("BTCUSDT", RuntimeError("unexpected scanner failure"))
    fatal_error = health["last_error"]
    record_error("ALGOUSDT", RuntimeError('bingx {"code":100410,"msg":"try again later"}'))

    assert health["last_error"] == fatal_error
    assert "Rate limit BingX OHLCV ALGOUSDT" in health["last_warning"]
    status = watchdog_status()
    assert status["ok"] is False
    assert status["status"] == "ALERTA"


def test_predator_non_throttle_scanner_failures_remain_fatal():
    record_error, health = _load_predator_scanner_error_handler()
    watchdog_status = _load_predator_watchdog_status(health)

    record_error("ALGOUSDT", RuntimeError("unexpected scanner failure"))

    assert health["last_error"] == "Erro scanner ALGOUSDT: unexpected scanner failure"
    status = watchdog_status()
    assert status["ok"] is False
    assert status["status"] == "ALERTA"


def test_predator_existing_quote_outage_stays_a_warning():
    record_error, health = _load_predator_scanner_error_handler()

    record_error("ALGOUSDT", RuntimeError('bingx {"code":109500} quote service unavailable'))

    assert health["last_error"] is None
    assert "Erro temporário BingX ALGOUSDT" in health["last_warning"]


def test_predator_cycle_quote_outage_does_not_clear_existing_fatal_error():
    record_symbol_error, health = _load_predator_scanner_error_handler()
    record_cycle_error = _load_predator_scanner_cycle_error_handler(health)
    watchdog_status = _load_predator_watchdog_status(health)

    record_symbol_error("BTCUSDT", RuntimeError("unexpected scanner failure"))
    fatal_error = health["last_error"]
    record_cycle_error(RuntimeError('bingx {"code":109500} quote service unavailable'))

    assert health["last_error"] == fatal_error
    assert "Erro temporário BingX no scanner" in health["last_warning"]
    status = watchdog_status()
    assert status["ok"] is False
    assert status["status"] == "ALERTA"


def test_predator_cycle_quote_outage_alone_remains_warning_only():
    _record, health = _load_predator_scanner_error_handler()
    record_cycle_error = _load_predator_scanner_cycle_error_handler(health)

    record_cycle_error(RuntimeError('bingx {"code":109500} quote service unavailable'))

    assert health["last_error"] is None
    assert "Erro temporário BingX no scanner" in health["last_warning"]
