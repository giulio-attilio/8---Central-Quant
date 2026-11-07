from __future__ import annotations

import ast
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType

import pytest

try:
    import ccxt  # noqa: F401
except ModuleNotFoundError:
    # Keep the guard tests runnable in an approved offline environment without
    # ccxt; all exchange behavior below is already supplied by FakeExchange.
    ccxt_stub = ModuleType("ccxt")
    ccxt_stub.ExchangeError = type("ExchangeError", (Exception,), {})
    ccxt_stub.RateLimitExceeded = type("RateLimitExceeded", (Exception,), {})

    class _StubBingx:
        def __init__(self, _config):
            self.options = {}
            self.fetch_ohlcv = lambda *_args, **_kwargs: []

    ccxt_stub.bingx = _StubBingx
    sys.modules["ccxt"] = ccxt_stub

import exchange_manager
from exchange_ohlcv_candle_cache_v1 import clear_ohlcv_candle_cache_for_tests
from exchange_throttle_policy_v1 import (
    exchange_throttle_cooldown_remaining,
    is_exchange_throttle_error,
    reset_exchange_throttle_cooldown_for_tests,
    start_exchange_throttle_cooldown,
)
from exchange_ohlcv_rate_limit_v1 import reset_exchange_ohlcv_rate_limit_for_tests


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
    reset_exchange_ohlcv_rate_limit_for_tests()
    clear_ohlcv_candle_cache_for_tests()
    yield
    reset_exchange_throttle_cooldown_for_tests()
    reset_exchange_ohlcv_rate_limit_for_tests()
    clear_ohlcv_candle_cache_for_tests()
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


@pytest.mark.parametrize(
    ("module_name", "error_type_name", "message"),
    [
        ("cobra.py", "RateLimitExceeded", "cooldown"),
        ("cobra.py", "OperationFailed", 'bingx {"code":100410,"msg":"try again later"}'),
        ("meme.py", "RateLimitExceeded", "cooldown"),
        ("meme.py", "OperationFailed", 'bingx {"code":100410,"msg":"try again later"}'),
        ("meme.py", "Exception", 'bingx {"code":100410,"msg":"try again later"}'),
        ("donkey.py", "RateLimitExceeded", "cooldown"),
        ("donkey.py", "OperationFailed", 'bingx {"code":100410,"msg":"try again later"}'),
        ("donkey.py", "Exception", 'bingx {"code":100410,"msg":"try again later"}'),
        ("trendpro.py", "RateLimitExceeded", "cooldown"),
        ("trendpro.py", "OperationFailed", 'bingx {"code":100410,"msg":"try again later"}'),
        ("trendpro.py", "Exception", 'bingx {"code":100410,"msg":"try again later"}'),
    ],
)
def test_bot_ticker_throttle_fails_fast_without_retry_or_sleep(
    module_name, error_type_name, message
):
    exception_type = {
        "RateLimitExceeded": exchange_manager.ccxt.RateLimitExceeded,
        "OperationFailed": exchange_manager.ccxt.OperationFailed,
        "Exception": Exception,
    }[error_type_name]

    class FakeExchange:
        calls = 0

        def fetch_ticker(self, _symbol):
            self.calls += 1
            raise exception_type(message)

    tree = ast.parse((BOT_DIR / module_name).read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "safe_fetch_ticker"
    )
    def fail_on_sleep(*_args):
        pytest.fail("throttle retry slept")

    namespace = {
        "exchange": FakeExchange(),
        "HEALTH": {},
        "NetworkError": exchange_manager.ccxt.NetworkError,
        "RateLimitExceeded": exchange_manager.ccxt.RateLimitExceeded,
        "ExchangeError": exchange_manager.ccxt.ExchangeError,
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "time": type("NoSleep", (), {"sleep": staticmethod(fail_on_sleep)}),
    }
    isolated = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated),
            f"{module_name}:safe_fetch_ticker",
            "exec",
        ),
        namespace,
    )

    result = namespace["safe_fetch_ticker"]("BTC/USDT:USDT", max_retries=3)

    assert result is None
    assert namespace["exchange"].calls == 1
    assert namespace["HEALTH"]["last_warning"] == (
        "Rate limit ticker BTC/USDT:USDT; novas tentativas suspensas"
    )


@pytest.mark.parametrize("module_name", ["cobra.py", "donkey.py", "meme.py", "trendpro.py"])
def test_bot_load_markets_operation_failed_100410_fails_fast(module_name):
    calls = []

    def load_markets_once():
        calls.append("load")
        raise exchange_manager.ccxt.OperationFailed(
            'bingx {"code":100410,"msg":"try again later"}'
        )

    tree = ast.parse((BOT_DIR / module_name).read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "safe_load_markets"
    )

    def fail_on_sleep(*_args):
        pytest.fail("throttled load_markets retried")

    namespace = {
        "load_markets_once": load_markets_once,
        "HEALTH": {},
        "NetworkError": exchange_manager.ccxt.NetworkError,
        "RateLimitExceeded": exchange_manager.ccxt.RateLimitExceeded,
        "ExchangeError": exchange_manager.ccxt.ExchangeError,
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "time": type("NoSleep", (), {"sleep": staticmethod(fail_on_sleep)}),
    }
    isolated = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated),
            f"{module_name}:safe_load_markets",
            "exec",
        ),
        namespace,
    )

    result = namespace["safe_load_markets"](max_retries=3)

    assert result is None
    assert calls == ["load"]
    assert namespace["HEALTH"]["last_warning"] == (
        "Rate limit BingX load_markets; novas tentativas suspensas"
    )


def test_cobra_ohlcv_operation_failed_100410_fails_fast():
    class FakeExchange:
        calls = 0

        def fetch_ohlcv(self, _symbol, *, timeframe, limit):
            self.calls += 1
            raise exchange_manager.ccxt.OperationFailed(
                'bingx {"code":100410,"msg":"try again later"}'
            )

    tree = ast.parse((BOT_DIR / "cobra.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "safe_fetch_ohlcv"
    )

    def fail_on_sleep(*_args):
        pytest.fail("throttled OHLCV retried")

    namespace = {
        "exchange": FakeExchange(),
        "HEALTH": {},
        "NetworkError": exchange_manager.ccxt.NetworkError,
        "RateLimitExceeded": exchange_manager.ccxt.RateLimitExceeded,
        "ExchangeError": exchange_manager.ccxt.ExchangeError,
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "time": type("NoSleep", (), {"sleep": staticmethod(fail_on_sleep)}),
    }
    isolated = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated),
            "cobra.py:safe_fetch_ohlcv",
            "exec",
        ),
        namespace,
    )

    result = namespace["safe_fetch_ohlcv"](
        "BTC/USDT:USDT", timeframe="1m", limit=100, max_retries=3
    )

    assert result == []
    assert namespace["exchange"].calls == 1
    assert "Rate limit OHLCV BTC/USDT:USDT 1m" in namespace["HEALTH"]["last_warning"]


@pytest.mark.parametrize(
    "throttle_error",
    [
        exchange_manager.ccxt.RateLimitExceeded(
            "Central shared OHLCV throttle cooldown active (10s)"
        ),
        RuntimeError('bingx {"code":100410,"msg":"try again later"}'),
    ],
)
def test_predator_fetch_df_converts_shared_throttle_to_skipped_symbol(throttle_error):
    class FakeExchange:
        calls = 0

        def fetch_ohlcv(self, _symbol, *, timeframe, limit):
            self.calls += 1
            raise throttle_error

    tree = ast.parse((BOT_DIR / "predator.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_df"
    )
    namespace = {
        "exchange": FakeExchange(),
        "HEALTH": {},
        "is_exchange_throttle_error": is_exchange_throttle_error,
        "nome_limpo": lambda symbol: symbol,
    }
    isolated = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated),
            "predator.py:fetch_df",
            "exec",
        ),
        namespace,
    )

    result = namespace["fetch_df"]("APT/USDT:USDT", "1h", limit=100)

    assert result is None
    assert namespace["exchange"].calls == 1
    assert namespace["HEALTH"]["last_warning"] == (
        "Rate limit BingX OHLCV APT/USDT:USDT 1h; "
        "Predator ignorou o símbolo neste ciclo"
    )


def test_predator_scanner_stops_after_throttled_h1_without_more_reads():
    tree = ast.parse((BOT_DIR / "predator.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "scan_smart_predator_symbol"
    )
    calls = []

    def throttled_fetch(symbol, timeframe, *, limit):
        calls.append((symbol, timeframe, limit))
        return None

    namespace = {
        "inc_funnel_stat": lambda *_args: None,
        "SMART_PREDATOR_ENABLED": True,
        "existe_posicao_ativa": lambda _symbol: False,
        "limite_posicoes_atingido": lambda: False,
        "fetch_df": throttled_fetch,
        "TIMEFRAME_H1": "1h",
        "TIMEFRAME_H4": "4h",
    }
    isolated = ast.Module(body=[function], type_ignores=[])
    exec(
        compile(
            ast.fix_missing_locations(isolated),
            "predator.py:scan_smart_predator_symbol",
            "exec",
        ),
        namespace,
    )

    result = namespace["scan_smart_predator_symbol"]("APT/USDT:USDT")

    assert result is None
    assert calls == [("APT/USDT:USDT", "1h", 100)]


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


def test_ticker_throttle_opens_shared_cooldown_for_tickers_and_scanners(monkeypatch):
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ticker(self, symbol):
            calls.append(("ticker", symbol))
            raise exchange_manager.ccxt.ExchangeError(
                'bingx {"code":100410,"msg":"system busy"}'
            )

        def fetch_ohlcv(self, symbol, **kwargs):
            calls.append(("ohlcv", symbol, kwargs))
            return []

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()

    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        shared.fetch_ticker("ALGO/USDT:USDT")
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        shared.fetch_ticker("BTC/USDT:USDT")
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        shared.fetch_ohlcv("ETH/USDT:USDT", timeframe="1m", limit=10)

    assert calls == [("ticker", "ALGO/USDT:USDT")]


def test_concurrent_ticker_callers_cannot_bypass_new_throttle_cooldown(monkeypatch):
    calls = []
    first_request_started = threading.Event()
    release_first_request = threading.Event()

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ticker(self, symbol):
            calls.append(symbol)
            first_request_started.set()
            assert release_first_request.wait(timeout=2)
            raise exchange_manager.ccxt.ExchangeError(
                'bingx {"code":100410,"msg":"system busy"}'
            )

        def fetch_ohlcv(self, *_args, **_kwargs):
            return []

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(shared.fetch_ticker, "ALGO/USDT:USDT")
        assert first_request_started.wait(timeout=2)
        second = pool.submit(shared.fetch_ticker, "BTC/USDT:USDT")
        release_first_request.set()
        with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
            first.result(timeout=2)
        with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
            second.result(timeout=2)

    assert calls == ["ALGO/USDT:USDT"]


def test_ticker_guard_is_installed_and_keeps_successful_results(monkeypatch):
    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ticker(self, symbol, params=None):
            return {"symbol": symbol, "last": 1.25, "params": params}

        def fetch_ohlcv(self, *_args, **_kwargs):
            return []

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()

    assert getattr(shared.fetch_ticker, "_central_throttle_guard_v1", False)
    assert shared.fetch_ticker("BTC/USDT:USDT", {"price": "mark"}) == {
        "symbol": "BTC/USDT:USDT",
        "last": 1.25,
        "params": {"price": "mark"},
    }


@pytest.mark.parametrize("module_name", BOT_MODULES)
def test_all_bot_ticker_reads_use_the_shared_exchange_client(module_name):
    tree = ast.parse((BOT_DIR / module_name).read_text(encoding="utf-8"))
    ticker_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "fetch_ticker"
    ]

    assert ticker_calls, f"{module_name} no longer has an auditable ticker call path"
    assert all(
        isinstance(call.func.value, ast.Name) and call.func.value.id == "exchange"
        for call in ticker_calls
    ), f"{module_name} bypasses the shared exchange client's ticker guard"


def test_shared_client_reuses_matching_candle_snapshot_across_bots(monkeypatch):
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, symbol, **kwargs):
            calls.append((symbol, kwargs))
            window = exchange_manager.current_ohlcv_window_start_ms(kwargs["timeframe"])
            return [
                [window - 3_600_000, 1, 2, 0, 1, 10],
                [window, 2, 3, 1, 2, 11],
            ]

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()

    first = shared.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=2)
    second = shared.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=1)

    assert first[-1][4] == 2
    assert second == [first[-1]]
    assert len(calls) == 1
    second[-1][4] = 999
    assert shared.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=1)[-1][4] == 2


def test_shared_throttle_cooldown_serves_valid_cache_but_rejects_cache_miss(monkeypatch):
    calls = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, _symbol, **kwargs):
            calls.append(kwargs)
            window = exchange_manager.current_ohlcv_window_start_ms(kwargs["timeframe"])
            return [[window - 3_600_000, 1, 2, 0, 1, 10], [window, 2, 3, 1, 2, 11]]

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    shared = exchange_manager.get_exchange()
    shared.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=2)
    start_exchange_throttle_cooldown(60)

    cached = shared.fetch_ohlcv("BTC/USDT:USDT", timeframe="1h", limit=2)
    assert len(cached) == 2
    assert len(calls) == 1

    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        shared.fetch_ohlcv("ETH/USDT:USDT", timeframe="1h", limit=2)

    assert len(calls) == 1


@pytest.mark.parametrize(
    ("args", "kwargs"),
    [
        (("BTC/USDT", None), {"timeframe": "1h", "limit": 2}),
        (("BTC/USDT",), {"timeframe": "1h", "limit": 2, "since": 123}),
        (("BTC/USDT",), {"timeframe": "1h", "limit": 2, "params": {"price": "mark"}}),
    ],
)
def test_non_scanner_fetch_shapes_bypass_candle_cache(args, kwargs):
    assert exchange_manager._cache_request_parts(args, kwargs) is None


def test_six_scanner_consumers_share_43_symbols_across_h1_h4_snapshots(monkeypatch):
    calls = []
    paced_slots = []
    elapsed = {"seconds": 0.0}

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, symbol, **kwargs):
            calls.append((symbol, kwargs["timeframe"], kwargs["limit"]))
            timeframe = kwargs["timeframe"]
            window = exchange_manager.current_ohlcv_window_start_ms(timeframe)
            interval_ms = 3_600_000 if timeframe == "1h" else 14_400_000
            return [
                [window - (299 - index) * interval_ms, index, index + 1, index - 1, index, 10]
                for index in range(299)
            ] + [[window, 299, 300, 298, 299, 11]]

    def fake_rate_slot():
        if paced_slots:
            elapsed["seconds"] += 1.05
        paced_slots.append(elapsed["seconds"])
        return 1.05 if len(paced_slots) > 1 else 0.0

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    monkeypatch.setattr(exchange_manager, "wait_for_exchange_ohlcv_slot", fake_rate_slot)
    shared = exchange_manager.get_exchange()

    symbols = [f"COIN{index}/USDT:USDT" for index in range(43)]
    limits_by_scanner = (300, 200, 120, 80, 80, 120)
    for symbol in symbols:
        for timeframe in ("1h", "4h"):
            for limit in limits_by_scanner:
                rows = shared.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
                assert len(rows) == limit

    assert len(calls) == 43 * 2
    assert len(paced_slots) == 43 * 2
    assert elapsed["seconds"] == pytest.approx((43 * 2 - 1) * 1.05)


def test_shared_client_waits_for_rate_slot_before_exchange_call(monkeypatch):
    events = []

    class FakeExchange:
        def __init__(self):
            self.options = {}

        def fetch_ohlcv(self, _symbol, **_kwargs):
            events.append("request")
            return [[1, 2, 3, 4, 5, 6]]

    client = FakeExchange()
    monkeypatch.setattr(exchange_manager.ccxt, "bingx", lambda _config: client)
    monkeypatch.setattr(
        exchange_manager,
        "wait_for_exchange_ohlcv_slot",
        lambda: events.append("paced"),
    )

    exchange_manager.get_exchange().fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)

    assert events == ["paced", "request"]


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


def test_guard_installs_on_ccxt_compatible_client_without_network():
    client = exchange_manager.ccxt.bingx({"enableRateLimit": True})
    start_exchange_throttle_cooldown(60)

    assert exchange_manager._install_shared_ohlcv_throttle_guard(client) is True
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        client.fetch_ohlcv("BTC/USDT", timeframe="1h", limit=100)


def test_independent_clients_share_market_data_throttle_cooldown(monkeypatch):
    calls = []
    ticker_pacing_calls = []
    monkeypatch.setattr(
        exchange_manager,
        "wait_for_exchange_ticker_slot",
        lambda: ticker_pacing_calls.append("waited") or 0.0,
    )

    class FakeExchange:
        def __init__(self, *, fail_ticker=False):
            self.options = {}
            self.fail_ticker = fail_ticker

        def fetch_ohlcv(self, symbol, **_kwargs):
            calls.append(("ohlcv", symbol))
            return [[1, 2, 3, 4, 5, 6]]

        def fetch_ticker(self, symbol):
            calls.append(("ticker", symbol))
            if self.fail_ticker:
                raise exchange_manager.ccxt.ExchangeError(
                    'bingx {"code":100410,"msg":"try again later"}'
                )
            return {"symbol": symbol}

    public_client = FakeExchange()
    authenticated_broker_client = FakeExchange(fail_ticker=True)
    assert exchange_manager.install_shared_market_data_throttle_guards(
        public_client
    ) == {"markets": False, "ohlcv": True, "ticker": True, "time": False}
    assert exchange_manager.install_shared_market_data_throttle_guards(
        authenticated_broker_client
    ) == {"markets": False, "ohlcv": True, "ticker": True, "time": False}

    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        authenticated_broker_client.fetch_ticker("BTC/USDT:USDT")
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        public_client.fetch_ohlcv("ETH/USDT:USDT", timeframe="1h", limit=1)

    assert calls == [("ticker", "BTC/USDT:USDT")]
    assert ticker_pacing_calls == ["waited"]


def test_broker_market_metadata_throttle_blocks_public_client_load_markets():
    calls = []

    class FakeExchange:
        def __init__(self, *, fail=False):
            self.options = {}
            self.fail = fail

        def load_markets(self, **kwargs):
            calls.append((self.fail, kwargs))
            if self.fail:
                raise exchange_manager.ccxt.ExchangeError(
                    'bingx {"code":100410,"msg":"try again later"}'
                )
            return {"BTC/USDT": {"symbol": "BTC/USDT"}}

    public_client = FakeExchange()
    broker_client = FakeExchange(fail=True)
    assert exchange_manager.install_shared_market_data_throttle_guards(
        public_client
    ) == {"markets": True, "ohlcv": False, "ticker": False, "time": False}
    assert exchange_manager.install_shared_market_data_throttle_guards(
        broker_client
    ) == {"markets": True, "ohlcv": False, "ticker": False, "time": False}

    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        broker_client.load_markets()
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        public_client.load_markets(reload=True)
    assert calls == [(True, {})]


def test_broker_public_time_throttle_blocks_market_reads_only():
    calls = []

    class FakeExchange:
        def __init__(self, *, fail=False):
            self.fail = fail

        def fetch_time(self):
            calls.append(("time", self.fail))
            if self.fail:
                raise exchange_manager.ccxt.ExchangeError(
                    'bingx {"code":100410,"msg":"try again later"}'
                )
            return 123456789

        def fetch_ticker(self, _symbol):
            calls.append(("ticker", self.fail))
            return {"last": 1.0}

        def fetch_balance(self):
            calls.append(("balance", self.fail))
            return {"USDT": {"free": 100.0}}

    public_client = FakeExchange()
    broker_client = FakeExchange(fail=True)
    assert exchange_manager.install_shared_market_data_throttle_guards(
        public_client
    ) == {"markets": False, "ohlcv": False, "ticker": True, "time": True}
    assert exchange_manager.install_shared_market_data_throttle_guards(
        broker_client
    ) == {"markets": False, "ohlcv": False, "ticker": True, "time": True}

    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        broker_client.fetch_time()
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        public_client.fetch_ticker("BTC/USDT:USDT")
    assert broker_client.fetch_balance() == {"USDT": {"free": 100.0}}
    assert calls == [("time", True), ("balance", True)]


def test_load_markets_throttle_opens_shared_cooldown_and_suppresses_repeat(monkeypatch):
    calls = []

    class FakeExchange:
        markets = None

        def load_markets(self, *, reload):
            calls.append(reload)
            raise exchange_manager.ccxt.ExchangeError(
                'bingx {"code":100410,"msg":"try again later"}'
            )

    monkeypatch.setattr(exchange_manager, "_exchange", FakeExchange())
    monkeypatch.setattr(exchange_manager, "_markets_loaded", False)
    exchange_manager.install_shared_market_data_throttle_guards(
        exchange_manager._exchange
    )

    with pytest.raises(exchange_manager.ccxt.ExchangeError, match="100410"):
        exchange_manager.load_markets_once()

    assert exchange_throttle_cooldown_remaining() >= 59.0
    with pytest.raises(exchange_manager.ccxt.RateLimitExceeded, match="cooldown"):
        exchange_manager.load_markets_once(force=True)
    assert calls == [True]


def test_broker_authenticated_client_installs_shared_guards():
    tree = ast.parse((BOT_DIR.parent / "broker.py").read_text(encoding="utf-8"))
    exchange_function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "exchange"
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "exchange_manager"
        and any(
            alias.name == "install_shared_market_data_throttle_guards"
            for alias in node.names
        )
        for node in ast.walk(exchange_function)
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "install_shared_market_data_throttle_guards"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "ex"
        for node in ast.walk(exchange_function)
    )
