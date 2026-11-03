from __future__ import annotations

import threading
import time

from runtime_drain_v1 import (
    RuntimeDrainState,
    close_after_drain,
    guard_live_flow,
    guard_new_live_entries,
    install_shutdown_signal_handlers,
)


def test_drain_atomically_rejects_new_entries_and_waits_for_existing():
    state = RuntimeDrainState()
    assert state.try_enter_live_entry()
    assert state.active_live_entries() == 1
    assert state.begin_draining() is True
    assert state.begin_draining() is False
    assert state.is_draining()
    assert not state.try_enter_live_entry()
    assert not state.wait_for_live_entries(0)
    state.leave_live_entry()
    assert state.wait_for_live_entries(0)
    assert state.active_live_entries() == 0


def test_management_cycle_is_admitted_before_drain_and_shutdown_waits_for_it():
    state = RuntimeDrainState()
    assert state.try_enter_management_cycle()
    assert state.active_management_cycles() == 1
    state.begin_draining()
    assert not state.try_enter_management_cycle()
    assert not state.wait_for_shutdown_work(0)
    state.leave_management_cycle()
    assert state.wait_for_shutdown_work(0)
    assert state.active_management_cycles() == 0


def test_shutdown_waits_for_entry_and_management_work_together():
    state = RuntimeDrainState()
    assert state.try_enter_live_entry()
    assert state.try_enter_management_cycle()
    state.begin_draining()
    state.leave_live_entry()
    assert not state.wait_for_shutdown_work(0)
    state.leave_management_cycle()
    assert state.wait_for_shutdown_work(0)


def test_close_after_drain_waits_for_admitted_management_cycle():
    state = RuntimeDrainState()
    assert state.try_enter_management_cycle()
    server = _FakeServer(_SignalHarness())
    release_cycle = threading.Event()
    result = []

    def finish_cycle():
        assert release_cycle.wait(1)
        state.leave_management_cycle()

    worker = threading.Thread(target=finish_cycle)
    worker.start()
    drain_result = threading.Thread(
        target=lambda: result.append(close_after_drain(server, state, grace_seconds=1))
    )
    drain_result.start()
    assert not server.closed
    release_cycle.set()
    worker.join(1)
    drain_result.join(1)

    assert not worker.is_alive()
    assert not drain_result.is_alive()
    assert result == [True]
    assert server.closed


def test_broker_boundary_only_tracks_real_non_reduce_only_entries():
    state = RuntimeDrainState()
    calls = []

    @guard_new_live_entries(state, live_send_enabled=lambda: True)
    def place_market_order(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ok": True, "sent": True}

    assert place_market_order("BTC-USDT", "buy")["sent"]
    assert calls == [(('BTC-USDT', 'buy'), {})]
    assert state.active_live_entries() == 0

    state.begin_draining()
    blocked = place_market_order("ETH-USDT", "buy")
    assert blocked == {
        "ok": False,
        "status": "ENTRY_BLOCKED_RUNTIME_DRAIN",
        "sent": False,
        "reason": "RUNTIME_DRAINING",
        "live_send_enabled": True,
        "preview_isolation": True,
    }
    assert place_market_order("ETH-USDT", "sell", None, True)["sent"]
    assert calls[-1][0] == ("ETH-USDT", "sell", None, True)
    assert state.active_live_entries() == 0


def test_paper_path_is_unchanged_even_after_drain():
    state = RuntimeDrainState()
    state.begin_draining()
    calls = []

    @guard_new_live_entries(state, live_send_enabled=lambda: False)
    def place_market_order(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "DRY_RUN", "sent": False}

    assert place_market_order("BTC-USDT", "buy") == {
        "status": "DRY_RUN",
        "sent": False,
    }
    assert len(calls) == 1
    assert state.active_live_entries() == 0


def test_mode_inspection_failure_during_drain_fails_closed():
    state = RuntimeDrainState()
    state.begin_draining()

    def unavailable_mode():
        raise RuntimeError("mode inspection unavailable")

    @guard_new_live_entries(state, live_send_enabled=unavailable_mode)
    def place_market_order(*_args, **_kwargs):
        raise AssertionError("broker entry must not run when mode is unknown during drain")

    result = place_market_order("BTC-USDT", "buy")
    assert result["status"] == "ENTRY_BLOCKED_RUNTIME_DRAIN"
    assert result["sent"] is False


def test_live_flow_lease_covers_post_broker_persistence_until_return():
    state = RuntimeDrainState()
    broker_sent = threading.Event()
    allow_persistence_to_finish = threading.Event()
    results = []

    @guard_live_flow(
        state,
        live_flow_enabled=lambda *_args, **_kwargs: True,
        blocked_result=lambda _args, _kwargs: {"status": "ENTRY_BLOCKED_RUNTIME_DRAIN"},
    )
    def complete_entry_flow():
        # Models a successful broker response followed by Registry persistence.
        broker_sent.set()
        assert allow_persistence_to_finish.wait(1)
        return {"status": "BROKER_ACK_AND_REGISTRY_PERSISTED"}

    worker = threading.Thread(target=lambda: results.append(complete_entry_flow()))
    worker.start()
    assert broker_sent.wait(1)
    assert state.active_live_entries() == 1

    state.begin_draining()
    assert not state.wait_for_live_entries(0)
    assert complete_entry_flow() == {"status": "ENTRY_BLOCKED_RUNTIME_DRAIN"}

    allow_persistence_to_finish.set()
    worker.join(1)
    assert not worker.is_alive()
    assert results == [{"status": "BROKER_ACK_AND_REGISTRY_PERSISTED"}]
    assert state.wait_for_live_entries(0)


def test_live_flow_guard_leaves_paper_and_reduce_only_flows_unchanged():
    state = RuntimeDrainState()
    state.begin_draining()
    calls = []

    @guard_live_flow(
        state,
        live_flow_enabled=lambda mode, reduce_only=False: mode == "LIVE" and not reduce_only,
        blocked_result=lambda _args, _kwargs: {"status": "ENTRY_BLOCKED_RUNTIME_DRAIN"},
    )
    def run_flow(mode, reduce_only=False):
        calls.append((mode, reduce_only))
        return {"status": "FLOW_RAN"}

    assert run_flow("PAPER") == {"status": "FLOW_RAN"}
    assert run_flow("LIVE", reduce_only=True) == {"status": "FLOW_RAN"}
    assert calls == [("PAPER", False), ("LIVE", True)]
    assert state.active_live_entries() == 0


class _SignalHarness:
    SIGTERM = 15
    SIGINT = 2

    def __init__(self):
        self.handlers = {self.SIGTERM: "old-term", self.SIGINT: "old-int"}

    def getsignal(self, sig):
        return self.handlers[sig]

    def signal(self, sig, handler):
        old = self.handlers[sig]
        self.handlers[sig] = handler
        return old

    def send(self, sig):
        self.handlers[sig](sig, None)


class _FakeServer:
    def __init__(self, signal_harness):
        self.signal_harness = signal_harness
        self.stopped = threading.Event()
        self.closed = False

    def shutdown(self):
        self.stopped.set()

    def serve_forever(self):
        self.signal_harness.send(self.signal_harness.SIGTERM)
        assert self.stopped.wait(1)

    def server_close(self):
        self.closed = True


def test_sigterm_starts_drain_stops_server_and_closes_after_bounded_wait():
    state = RuntimeDrainState()
    assert state.try_enter_live_entry()
    assert state.try_enter_management_cycle()
    signals = _SignalHarness()
    server = _FakeServer(signals)
    original_handlers = dict(signals.handlers)
    restore = install_shutdown_signal_handlers(server, state, signal_module=signals)

    server.serve_forever()
    assert state.is_draining()
    assert not state.try_enter_live_entry()
    drained = close_after_drain(server, state, grace_seconds=0)

    assert drained is False
    assert server.closed
    state.leave_live_entry()
    assert not state.wait_for_shutdown_work(0)
    state.leave_management_cycle()
    assert state.wait_for_shutdown_work(0)
    restore()
    assert signals.handlers == original_handlers


def test_werkzeug_server_shutdown_signal_contract_without_client_network_access():
    from flask import Flask
    from werkzeug.serving import make_server
    from unittest.mock import patch

    wait_started = threading.Event()

    class ObservedDrainState(RuntimeDrainState):
        def wait_for_shutdown_work(self, timeout_seconds):
            wait_started.set()
            return super().wait_for_shutdown_work(timeout_seconds)

    state = ObservedDrainState()
    assert state.try_enter_management_cycle()
    signals = _SignalHarness()
    release_management = threading.Event()
    management = threading.Thread(
        target=lambda: (release_management.wait(), state.leave_management_cycle()),
        daemon=True,
    )
    app = Flask("runtime-drain-test")
    app.add_url_rule("/", view_func=lambda: "ok")
    with patch("werkzeug.serving.get_sockaddr", return_value=("127.0.0.1", 0)):
        server = make_server("127.0.0.1", 0, app, threaded=True)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    original_handlers = dict(signals.handlers)
    restore = install_shutdown_signal_handlers(server, state, signal_module=signals)
    drain_results = []
    closer = None
    try:
        management.start()
        serving.start()
        shutdown_event = server._BaseServer__is_shut_down
        deadline = time.monotonic() + 2
        while shutdown_event.is_set() and time.monotonic() < deadline:
            time.sleep(0.005)
        assert not shutdown_event.is_set(), "Werkzeug serve_forever did not start"

        signals.send(signals.SIGTERM)
        serving.join(2)
        assert not serving.is_alive()
        assert state.is_draining()
        closer = threading.Thread(
            target=lambda: drain_results.append(
                close_after_drain(server, state, grace_seconds=5)
            ),
            daemon=True,
        )
        closer.start()
        assert wait_started.wait(1)
        assert drain_results == []
        release_management.set()
        management.join(1)
        closer.join(2)
        assert not management.is_alive()
        assert not closer.is_alive()
        assert drain_results == [True]
        assert server.socket.fileno() == -1
    finally:
        release_management.set()
        if management.is_alive():
            management.join(1)
        if closer is not None and closer.is_alive():
            closer.join(2)
        if serving.is_alive():
            server.shutdown()
            serving.join(2)
        server.server_close()
        restore()
    assert signals.handlers == original_handlers
