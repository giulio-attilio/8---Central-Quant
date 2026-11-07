from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

from runtime_drain_v1 import (
    RuntimeDrainState,
    guard_management_cycle,
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


def test_management_decorator_tracks_active_work_and_denies_after_drain():
    state = RuntimeDrainState()

    @guard_management_cycle(state)
    def manage(value):
        assert state.active_management_cycles() == 1
        return value

    assert manage("done") == "done"
    assert state.active_management_cycles() == 0
    state.begin_draining()
    assert manage("must-not-run") is None
    assert state.active_management_cycles() == 0


def test_admitted_management_can_finish_nested_work_after_drain_begins():
    state = RuntimeDrainState()

    @guard_management_cycle(state)
    def nested_management():
        assert state.is_draining()
        assert state.active_management_cycles() == 1
        return "nested-finished"

    @guard_management_cycle(state)
    def outer_management():
        state.begin_draining()
        return nested_management()

    assert outer_management() == "nested-finished"
    assert state.active_management_cycles() == 0
    assert nested_management() is None


def test_turtle_management_loop_tracks_cycle_and_exits_after_drain():
    source_path = Path(__file__).resolve().parents[1] / "bots" / "turtle.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "management_loop"
    ]
    function = functions[-1]
    loop = next(node for node in function.body if isinstance(node, ast.While))

    def calls(node, method):
        return [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == method
        ]

    admission_if = loop.body[0]
    assert isinstance(admission_if, ast.If)
    assert calls(admission_if, "try_enter_management_cycle")

    guarded_try = next(node for node in loop.body if isinstance(node, ast.Try))
    assert calls(guarded_try, "leave_management_cycle")
    assert calls(guarded_try.finalbody[0], "leave_management_cycle")

    drain_if = next(
        node
        for node in loop.body[loop.body.index(guarded_try) + 1 :]
        if isinstance(node, ast.If)
    )
    assert calls(drain_if, "is_draining")
    assert any(isinstance(node, ast.Return) for node in drain_if.body)


def test_falcon_management_loop_tracks_cycle_and_exits_after_drain():
    source_path = Path(__file__).resolve().parents[1] / "bots" / "falcon.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "management_loop"
    ]
    function = functions[-1]
    loop = next(node for node in function.body if isinstance(node, ast.While))

    def calls(node, method):
        return [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == method
        ]

    admission_if = loop.body[0]
    assert isinstance(admission_if, ast.If)
    assert calls(admission_if, "try_enter_management_cycle")

    guarded_try = next(node for node in loop.body if isinstance(node, ast.Try))
    assert calls(guarded_try.finalbody[0], "leave_management_cycle")

    drain_if = next(
        node
        for node in loop.body[loop.body.index(guarded_try) + 1 :]
        if isinstance(node, ast.If)
    )
    assert calls(drain_if, "is_draining")
    assert any(isinstance(node, ast.Return) for node in drain_if.body)


def test_position_managers_use_the_shared_shutdown_drain():
    expected = {
        "cobra.py": {"gerenciar_posicoes"},
        "donkey.py": {"gerenciar_donkey_position", "gerenciar_posicoes"},
        "meme.py": {"atualizar_monitor_be", "gerenciar_posicoes"},
        "predator.py": {"gerenciar_posicoes"},
        "trendpro.py": {"atualizar_monitor_be", "gerenciar_posicoes"},
    }
    bots_dir = Path(__file__).resolve().parents[1] / "bots"
    for filename, function_names in expected.items():
        module = ast.parse((bots_dir / filename).read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
        }
        for name in function_names:
            function = functions[name]
            assert any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "guard_management_cycle"
                for decorator in function.decorator_list
            ), f"{filename}:{name} is not tracked by runtime drain"


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


def test_signal_drain_waits_for_management_then_closes_server_without_network_access():
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
    server = _FakeServer(signals)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    original_handlers = dict(signals.handlers)
    restore = install_shutdown_signal_handlers(server, state, signal_module=signals)
    drain_results = []
    closer = None
    try:
        management.start()
        serving.start()
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
        assert server.closed
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
