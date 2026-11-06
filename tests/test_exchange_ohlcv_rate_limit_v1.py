from __future__ import annotations

import ast
import socket
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path

import pytest

from exchange_ohlcv_rate_limit_v1 import (
    MIN_OHLCV_REQUEST_INTERVAL_SECONDS,
    reset_exchange_ohlcv_rate_limit_for_tests,
    wait_for_exchange_ohlcv_slot,
    wait_for_exchange_ticker_slot,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_clock_and_block_network(monkeypatch):
    clock = {"now": 1000.0, "sleeps": []}

    def sleep(seconds):
        clock["sleeps"].append(seconds)
        clock["now"] += seconds

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in this test")

    monkeypatch.setattr(
        "exchange_ohlcv_rate_limit_v1.time",
        SimpleNamespace(monotonic=lambda: clock["now"], sleep=sleep),
    )
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    reset_exchange_ohlcv_rate_limit_for_tests()
    yield clock
    reset_exchange_ohlcv_rate_limit_for_tests()


def test_first_exchange_ohlcv_request_does_not_wait():
    assert wait_for_exchange_ohlcv_slot() == 0.0


def test_consecutive_exchange_ohlcv_requests_are_spaced_at_documented_cap(isolate_clock_and_block_network):
    clock = isolate_clock_and_block_network
    assert wait_for_exchange_ohlcv_slot() == 0.0
    clock["now"] += 0.2

    waited = wait_for_exchange_ohlcv_slot()

    assert waited == pytest.approx(MIN_OHLCV_REQUEST_INTERVAL_SECONDS - 0.2)
    assert clock["sleeps"] == [pytest.approx(MIN_OHLCV_REQUEST_INTERVAL_SECONDS - 0.2)]


def test_no_wait_after_request_duration_already_satisfies_spacing(isolate_clock_and_block_network):
    clock = isolate_clock_and_block_network
    assert wait_for_exchange_ohlcv_slot() == 0.0
    clock["now"] += MIN_OHLCV_REQUEST_INTERVAL_SECONDS + 0.25

    assert wait_for_exchange_ohlcv_slot() == 0.0
    assert clock["sleeps"] == []


def test_concurrent_callers_are_paced_under_one_shared_lock():
    with ThreadPoolExecutor(max_workers=4) as pool:
        waits = list(pool.map(lambda _index: wait_for_exchange_ohlcv_slot(), range(4)))

    assert sorted(waits) == pytest.approx(
        [0.0] + [MIN_OHLCV_REQUEST_INTERVAL_SECONDS] * 3
    )


def test_ticker_requests_have_an_independent_documented_endpoint_budget(
    isolate_clock_and_block_network,
):
    clock = isolate_clock_and_block_network
    assert wait_for_exchange_ticker_slot() == 0.0
    clock["now"] += 0.2

    waited = wait_for_exchange_ticker_slot()

    assert waited == pytest.approx(MIN_OHLCV_REQUEST_INTERVAL_SECONDS - 0.2)
    assert clock["sleeps"] == [pytest.approx(MIN_OHLCV_REQUEST_INTERVAL_SECONDS - 0.2)]


def test_ticker_slot_is_independent_from_ohlcv_slot(isolate_clock_and_block_network):
    assert wait_for_exchange_ohlcv_slot() == 0.0
    assert wait_for_exchange_ticker_slot() == 0.0


def test_shared_exchange_guard_paces_before_each_network_call():
    tree = ast.parse((ROOT / "exchange_manager.py").read_text(encoding="utf-8"))
    installer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_install_shared_ohlcv_throttle_guard"
    )
    guard = next(
        node
        for node in ast.walk(installer)
        if isinstance(node, ast.FunctionDef) and node.name == "guarded_fetch_ohlcv"
    )
    calls = [
        node.func.id
        for node in ast.walk(guard)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert "wait_for_exchange_ohlcv_slot" in calls
    assert calls.index("wait_for_exchange_ohlcv_slot") < calls.index("original_fetch_ohlcv")


def test_shared_ticker_guard_paces_before_each_network_call():
    tree = ast.parse((ROOT / "exchange_manager.py").read_text(encoding="utf-8"))
    installer = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_install_shared_ticker_throttle_guard"
    )
    guard = next(
        node
        for node in ast.walk(installer)
        if isinstance(node, ast.FunctionDef) and node.name == "guarded_fetch_ticker"
    )
    calls = [
        node.func.id
        for node in ast.walk(guard)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]

    assert "wait_for_exchange_ticker_slot" in calls
    assert calls.index("wait_for_exchange_ticker_slot") < calls.index("original_fetch_ticker")


@pytest.mark.parametrize(
    "bot_name",
    ["cobra", "donkey", "falcon", "meme", "predator", "trendpro", "turtle"],
)
def test_every_personal_bot_uses_the_shared_guarded_exchange(bot_name):
    tree = ast.parse((ROOT / "bots" / f"{bot_name}.py").read_text(encoding="utf-8"))
    imports_shared_client = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "exchange_manager"
        and any(
            alias.name == "get_exchange" and alias.asname in (None, "get_exchange")
            for alias in node.names
        )
        for node in tree.body
    )
    initializes_shared_client = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and (
            any(
                isinstance(target, ast.Name) and target.id == "exchange"
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            )
        )
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "get_exchange"
        for node in tree.body
    )

    assert imports_shared_client, f"{bot_name} must import the shared exchange manager"
    assert initializes_shared_client, f"{bot_name} must use the guarded shared client"
