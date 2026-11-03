from __future__ import annotations

import ast
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import exchange_manager
from exchange_throttle_policy_v1 import (
    exchange_throttle_cooldown_remaining,
    reset_exchange_throttle_cooldown_for_tests,
    start_exchange_throttle_cooldown,
)


BOT_MODULES = (
    "cobra.py",
    "donkey.py",
    "falcon.py",
    "meme.py",
    "predator.py",
    "trendpro.py",
    "turtle.py",
)
BOT_DIR = Path(__file__).resolve().parents[1] / "bots"


@pytest.fixture(autouse=True)
def isolate_state_and_block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(exchange_manager, "_exchange", None)
    reset_exchange_throttle_cooldown_for_tests()
    yield
    reset_exchange_throttle_cooldown_for_tests()
    monkeypatch.setattr(exchange_manager, "_exchange", None)


@pytest.mark.parametrize("module_name", BOT_MODULES)
def test_all_bot_ohlcv_reads_use_the_shared_exchange_client(module_name):
    tree = ast.parse((BOT_DIR / module_name).read_text(encoding="utf-8"))
    imports_shared_factory = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "exchange_manager"
        and any(alias.name == "get_exchange" for alias in node.names)
        for node in tree.body
    )
    initializes_shared_client = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "exchange"
            for target in node.targets
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "get_exchange"
        for node in tree.body
    )
    ohlcv_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fetch_ohlcv"
    ]

    assert imports_shared_factory
    assert initializes_shared_client
    assert ohlcv_calls, f"{module_name} no longer has an auditable OHLCV call path"
    assert all(
        isinstance(call.func.value, ast.Name) and call.func.value.id == "exchange"
        for call in ohlcv_calls
    ), f"{module_name} bypasses the shared exchange client's OHLCV wrapper"


def test_shared_client_starts_cooldown_and_rejects_next_scanner_read(monkeypatch):
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, symbol, **kwargs):
            calls.append((symbol, kwargs))
            raise exchange_manager.ccxt.ExchangeError(
                'bingx {"code":100410,"msg":"system busy"}'
            )

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)

    shared = exchange_manager.get_exchange()
    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        shared.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        shared.fetch_ohlcv("ETH/USDT", timeframe="1h", limit=100)

    assert len(calls) == 1


def test_concurrent_scanners_serialize_request_and_share_throttle_cooldown(monkeypatch):
    request_started = threading.Event()
    release_request = threading.Event()
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, symbol, **_kwargs):
            calls.append(symbol)
            request_started.set()
            if not release_request.wait(timeout=5):
                raise AssertionError("test did not release synthetic request")
            raise exchange_manager.ccxt.ExchangeError(
                'bingx {"code":100410,"msg":"system busy"}'
            )

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()

    def fetch(symbol):
        return shared.fetch_ohlcv(symbol, timeframe="1h", limit=100)

    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(fetch, "BTC/USDT")
        assert request_started.wait(timeout=2)
        others = [pool.submit(fetch, f"COIN{index}/USDT") for index in range(3)]
        try:
            time.sleep(0.05)
            assert calls == ["BTC/USDT"]
        finally:
            release_request.set()

        with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
            first.result(timeout=2)
        for future in others:
            with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
                future.result(timeout=2)

    assert calls == ["BTC/USDT"]


def test_shared_cooldown_expires_and_restores_exchange_reads(monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr(
        "exchange_throttle_policy_v1.time.monotonic", lambda: clock["now"]
    )
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, symbol, **kwargs):
            calls.append((symbol, kwargs))
            if len(calls) in {1, 3}:
                raise exchange_manager.ccxt.ExchangeError(
                    'bingx {"code":100410,"msg":"system busy"}'
                )
            return [[1, 2, 3, 4, 5, 6]]

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()
    with pytest.raises(exchange_manager.ccxt.ExchangeError):
        shared.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
    clock["now"] += 61.0

    assert shared.fetch_ohlcv("ETH/USDT", timeframe="1h", limit=100) == [
        [1, 2, 3, 4, 5, 6]
    ]
    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        shared.fetch_ohlcv("XRP/USDT", timeframe="1h", limit=100)
    assert exchange_throttle_cooldown_remaining() == 60.0
    assert len(calls) == 3


def test_guard_installs_on_real_ccxt_client_without_network():
    client = exchange_manager.ccxt.bingx({"enableRateLimit": True})
    start_exchange_throttle_cooldown(60)

    assert exchange_manager._install_shared_ohlcv_throttle_guard(client) is True
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        client.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)
