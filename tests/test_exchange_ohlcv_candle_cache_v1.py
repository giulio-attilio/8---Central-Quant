from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

import exchange_ohlcv_candle_cache_v1 as cache


@pytest.fixture(autouse=True)
def isolate_clock_and_block_network(monkeypatch):
    now = {"seconds": 3601.0}

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(cache, "time", SimpleNamespace(time=lambda: now["seconds"]))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    cache.clear_ohlcv_candle_cache_for_tests()
    yield now
    cache.clear_ohlcv_candle_cache_for_tests()


def _rows(window_start_ms, count=5):
    earlier = [
        [window_start_ms - (count - index) * 3_600_000, index, 2, 0, 1, 10]
        for index in range(count - 1)
    ]
    return earlier + [[window_start_ms, count, 3, 1, 2, 11]]


def test_same_candle_snapshot_serves_smaller_limit_as_a_defensive_copy():
    window_start = cache.current_ohlcv_window_start_ms("1h")
    assert window_start == 3_600_000
    rows = _rows(window_start)

    assert cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT",
        "1h",
        rows,
        requested_window_start_ms=window_start,
    )
    returned = cache.get_cached_ohlcv_snapshot("btc/usdt:usdt", "1h", 2)

    assert returned == rows[-2:]
    returned[-1][4] = 999
    assert cache.get_cached_ohlcv_snapshot("BTC/USDT:USDT", "1h", 1)[0][4] == 2


def test_snapshot_is_not_reused_for_another_symbol_or_timeframe():
    start = cache.current_ohlcv_window_start_ms("1h")
    assert cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT", "1h", _rows(start), requested_window_start_ms=start
    )

    assert cache.get_cached_ohlcv_snapshot("ETH/USDT:USDT", "1h", 1) is None
    assert cache.get_cached_ohlcv_snapshot("BTC/USDT:USDT", "4h", 1) is None


def test_snapshot_expires_at_candle_boundary():
    now = {"seconds": 3601.0}
    monkeypatch_time = cache.time
    start = cache.current_ohlcv_window_start_ms("1h")
    assert cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT", "1h", _rows(start), requested_window_start_ms=start
    )

    now["seconds"] = 7200.0
    monkeypatch_time.time = lambda: now["seconds"]
    assert cache.get_cached_ohlcv_snapshot("BTC/USDT:USDT", "1h", 1) is None
    assert monkeypatch_time is cache.time


@pytest.mark.parametrize("timeframe", ["1M", "1w", "not-a-timeframe"])
def test_unsupported_timeframes_bypass_cache(timeframe):
    assert cache.current_ohlcv_window_start_ms(timeframe) is None
    assert not cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT",
        timeframe,
        [[0, 1, 2, 0, 1, 1]],
        requested_window_start_ms=0,
    )


def test_snapshot_requires_current_window_candle_and_does_not_cache_bad_rows():
    start = cache.current_ohlcv_window_start_ms("1h")
    assert not cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT",
        "1h",
        _rows(start - 3_600_000),
        requested_window_start_ms=start,
    )
    assert cache.get_cached_ohlcv_snapshot("BTC/USDT:USDT", "1h", 1) is None


def test_snapshot_does_not_cross_candle_boundary_during_fetch():
    now = {"seconds": 7199.9}
    cache.time.time = lambda: now["seconds"]
    old_window_start = cache.current_ohlcv_window_start_ms("1h")
    now["seconds"] = 7200.0

    assert not cache.store_ohlcv_snapshot(
        "BTC/USDT:USDT",
        "1h",
        _rows(old_window_start),
        requested_window_start_ms=old_window_start,
    )
    assert cache.get_cached_ohlcv_snapshot("BTC/USDT:USDT", "1h", 1) is None
