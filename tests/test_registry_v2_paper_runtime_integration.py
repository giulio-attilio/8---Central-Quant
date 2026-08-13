from __future__ import annotations

import ast
import copy
from dataclasses import replace
from pathlib import Path

import pytest

import registry_execution_schema as schema
import registry_v2_paper_runtime_adapter as paper
import registry_v2_wal as wal


ROOT = Path(__file__).resolve().parents[1]
TURTLE_SOURCE = (ROOT / "bots" / "turtle.py").read_text(encoding="utf-8")
TURTLE_TREE = ast.parse(TURTLE_SOURCE)


class _AdapterResult:
    def __init__(self, status="WAL_OK", *, execution_id="exec_test", committed=True, found=False):
        self.status = status
        self.execution_id = execution_id
        self.committed = committed
        self.found = found

    def to_dict(self):
        return {
            "ok": self.committed,
            "status": self.status,
            "execution_id": self.execution_id,
            "write_committed": self.committed,
            "found": self.found,
        }


class _FakePaperAdapter:
    def __init__(self, *, enabled=True):
        self.enabled = enabled
        self.has_explicit_paper_storage = True
        self.calls = []

    def register_turtle_paper(self, position, **kwargs):
        self.calls.append(("register", position, kwargs))
        if self.enabled:
            position.setdefault("execution_id", "exec_test")
            position.setdefault("lifecycle_id", "exec_test")
            return _AdapterResult()
        return _AdapterResult("REGISTRY_V2_PAPER_WRITE_DISABLED", committed=False)

    def update_turtle_paper(self, position, **kwargs):
        self.calls.append(("update", position, kwargs))
        return _AdapterResult("WAL_OK" if self.enabled else "REGISTRY_V2_PAPER_WRITE_DISABLED", committed=self.enabled)

    def close_turtle_paper(self, position, **kwargs):
        self.calls.append(("close", position, kwargs))
        return _AdapterResult("WAL_OK" if self.enabled else "REGISTRY_V2_PAPER_WRITE_DISABLED", committed=self.enabled)

    def read_turtle_paper_committed_register(self, position, **kwargs):
        self.calls.append(("read_register", position, kwargs))
        return _AdapterResult(
            "WAL_NOT_FOUND" if self.enabled else "REGISTRY_V2_PAPER_WRITE_DISABLED",
            committed=self.enabled,
            found=False,
        )


def _compile_registry_functions(namespace):
    names = {
        "turtle_registry_id",
        "turtle_registry_open_occurrence_key",
        "turtle_registry_write_committed",
        "turtle_registry_is_v2_routed",
        "turtle_registry_result_payload",
        "turtle_registry_read_committed_open",
        "turtle_registry_open",
        "turtle_registry_update",
        "turtle_registry_close",
    }
    nodes = [
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == names
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<turtle-v2-paper-runtime>", "exec"), namespace)
    return namespace


def _namespace(*, gate, fake_adapter, v1_calls):
    def make_trade_id(bot, symbol, side, setup):
        v1_calls.append(("make_trade_id", bot, symbol, side, setup))
        return f"{bot}:{setup}:{symbol}:{side}"

    def register_open_trade(**kwargs):
        v1_calls.append(("register_open_trade", kwargs))
        return {"ok": True, "trade_id": "v1-trade"}

    def update_trade(trade_id, **kwargs):
        v1_calls.append(("update_trade", trade_id, kwargs))
        return {"ok": True, "trade_id": trade_id}

    def close_trade(trade_id, **kwargs):
        v1_calls.append(("close_trade", trade_id, kwargs))
        return {"ok": True, "trade_id": trade_id}

    return {
        "json": __import__("json"),
        "REGISTRY_V2_PAPER_WRITE_ENABLED": gate,
        "get_registry_v2_paper_runtime_adapter": lambda: fake_adapter,
        "TRADE_REGISTRY_LOADED": True,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "make_trade_id": make_trade_id,
        "register_open_trade": register_open_trade,
        "update_trade": update_trade,
        "close_trade": close_trade,
        "safe_float": lambda value: float(value if value is not None else 0.0),
        "data_hora_sp_str": lambda: "2026-08-10T12:00:00-03:00",
        "BOT_NAME": "Turtle Breakout PRO 2.0",
    }


def _position(**overrides):
    position = {
        "setup": "TURTLE20",
        "setup_label": "Turtle 20",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry": 100.0,
        "initial_stop": 95.0,
        "stop": 95.0,
        "tp50": 105.0,
        "status": "OPEN",
        "tp50_hit": False,
        "be_moved": False,
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "management_cycles": 0,
        "signal_ts": 1_700_000_000,
        "opened_candle_ts": 1_700_000_000,
    }
    position.update(overrides)
    return position


def _compile_turtle_functions(namespace, names):
    nodes = [
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == set(names)
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<turtle-v2-paper-runtime-review3>", "exec"), namespace)
    return namespace


class _StopLoop(RuntimeError):
    pass


class _OneLoopTime:
    def time(self):
        return 10_000.0

    def sleep(self, _seconds):
        raise _StopLoop()


class _ClosedCandle:
    class _ILoc:
        def __getitem__(self, _item):
            return {"ts": 1_700_000_000}

    iloc = _ILoc()

    def __len__(self):
        return 1


class _LifecycleAdapter:
    """Delegate V2 reads/writes while permitting one intentional local failure."""

    def __init__(self, adapter, *, register_status=None, update_status=None, close_status=None):
        self._adapter = adapter
        self._register_status = register_status
        self._update_status = update_status
        self._close_status = close_status
        self.register_calls = 0

    @property
    def has_explicit_paper_storage(self):
        return self._adapter.has_explicit_paper_storage

    @staticmethod
    def _failure(status):
        return _AdapterResult(status, committed=False)

    def register_turtle_paper(self, position, **kwargs):
        self.register_calls += 1
        status = (
            self._register_status(position, kwargs)
            if callable(self._register_status)
            else self._register_status
        )
        if status is not None:
            return self._failure(status)
        return self._adapter.register_turtle_paper(position, **kwargs)

    def update_turtle_paper(self, position, **kwargs):
        status = (
            self._update_status(position, kwargs)
            if callable(self._update_status)
            else self._update_status
        )
        if status is not None:
            return self._failure(status)
        return self._adapter.update_turtle_paper(position, **kwargs)

    def close_turtle_paper(self, position, **kwargs):
        if self._close_status is not None:
            return self._failure(self._close_status)
        return self._adapter.close_turtle_paper(position, **kwargs)

    def read_turtle_paper_committed_update(self, position, **kwargs):
        return self._adapter.read_turtle_paper_committed_update(position, **kwargs)

    def read_turtle_paper_committed_register(self, position, **kwargs):
        return self._adapter.read_turtle_paper_committed_register(position, **kwargs)

    def read_turtle_paper_committed_close(self, position, **kwargs):
        return self._adapter.read_turtle_paper_committed_close(position, **kwargs)


def _runtime_registry_namespace(adapter, *, gate=True):
    calls = []
    namespace = _namespace(gate=gate, fake_adapter=adapter, v1_calls=calls)
    _compile_registry_functions(namespace)
    return namespace, calls


def _management_namespace(adapter, state, *, price):
    events = []
    telegram = []
    trades = []
    saves = []

    def get_positions():
        return copy.deepcopy(state["positions"])

    def save_positions(positions):
        saves.append(copy.deepcopy(positions))
        if state.get("save_ok", True):
            state["positions"] = copy.deepcopy(positions)
            return True
        return False

    def pnl_pct_for_side(side, entry, exit_price):
        change = (exit_price - entry) / entry * 100.0
        return change if side == "LONG" else -change

    def r_for_side(side, entry, stop, exit_price):
        risk = abs(entry - stop)
        change = exit_price - entry if side == "LONG" else entry - exit_price
        return change / risk if risk else 0.0

    namespace, v1_calls = _runtime_registry_namespace(adapter)
    namespace.update(
        {
            "get_positions": get_positions,
            "save_positions": save_positions,
            "safe_fetch_price": lambda _symbol: price,
            "turtle_exit_signal": lambda _pos: (False, None),
            "pnl_pct_for_side": pnl_pct_for_side,
            "r_for_side": r_for_side,
            "safe_float": lambda value, default=0.0: float(value if value is not None else default),
            "record_event": lambda event, pos, extra=None: events.append((event, copy.deepcopy(pos), extra)),
            "redis_list_append": lambda key, value: trades.append((key, copy.deepcopy(value))) or True,
            "send_automatic_telegram": lambda *args, **kwargs: telegram.append((args, kwargs)),
            "safe_send_telegram": object(),
            "fmt_price": str,
            "fmt_pct": str,
            "fmt_r": str,
            "TRADES_KEY": "trades",
            "HEALTH": {},
            "data_hora_sp_str": lambda: "2026-08-10T12:00:00-03:00",
            "traceback": type("Traceback", (), {"print_exc": staticmethod(lambda: None)})(),
            "time": _OneLoopTime(),
            "MANAGEMENT_SLEEP_SECONDS": 0,
        }
    )
    _compile_turtle_functions(
        namespace,
        {
            "turtle_registry_recover_management",
            "turtle_registry_apply_management_patch",
            "turtle_registry_committed_close_facts",
            "update_mfe_mae",
            "emit_closed_trade",
            "close_position",
            "record_tp50_transition",
            "notify_tp50_transition",
            "management_loop",
        },
    )
    return namespace, {"events": events, "telegram": telegram, "trades": trades, "saves": saves}


def _run_management_once(namespace):
    with pytest.raises(_StopLoop):
        namespace["management_loop"]()


def _storage_events(tmp_path):
    storage = wal.RegistryV2WalStorage(
        snapshot_path=tmp_path / paper.REGISTRY_V2_PAPER_SNAPSHOT_FILENAME,
        journal_path=tmp_path / paper.REGISTRY_V2_PAPER_JOURNAL_FILENAME,
        lock_path=tmp_path / paper.REGISTRY_V2_PAPER_LOCK_FILENAME,
        backup_dir=tmp_path / paper.REGISTRY_V2_PAPER_BACKUP_DIRNAME,
    )
    return wal.read_journal(storage)


def _source_occurrence_key(adapter, signal):
    runtime, _v1_calls = _runtime_registry_namespace(adapter)
    key = runtime["turtle_registry_open_occurrence_key"](signal)
    assert key is not None
    return key


def _commit_source_register(adapter, signal):
    source = copy.deepcopy(signal)
    result = adapter.register_turtle_paper(
        source,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        idempotency_key=_source_occurrence_key(adapter, signal),
    )
    assert result.ok is True
    assert result.write_committed is True
    return source


def _scanner_namespace(
    adapter,
    signal,
    *,
    save_ok=True,
    state=None,
    risk_guard=None,
    watchlist=None,
    setups=None,
    signals_by_occurrence=None,
    max_open_positions=5,
    should_skip=None,
    startup_guard_seconds=0,
    save_behavior=None,
    gate=True,
):
    state = {} if state is None else state
    state.setdefault("positions", {})
    state.setdefault("last_candles", {})
    state.setdefault("save_ok", save_ok)
    state.setdefault("risk_calls", 0)
    state.setdefault("should_skip_calls", 0)
    state.setdefault("analysis_calls", [])
    signals = []
    events = []
    telegram = []
    saves = []
    cooldowns = []
    last_candle_saves = []
    namespace, v1_calls = _runtime_registry_namespace(adapter, gate=gate)

    def save_positions(positions):
        saves.append(copy.deepcopy(positions))
        saved = (
            bool(save_behavior(positions, len(saves)))
            if save_behavior is not None
            else state["save_ok"]
        )
        if saved:
            state["positions"] = copy.deepcopy(positions)
            return True
        return False

    def save_last_candles(last_candles):
        last_candle_saves.append(copy.deepcopy(last_candles))
        state["last_candles"] = copy.deepcopy(last_candles)
        return True

    def run_risk_guard(sig):
        state["risk_calls"] += 1
        if risk_guard is not None:
            return risk_guard(sig)
        return True, {}

    def analyze(symbol, setup_key, *_args):
        state["analysis_calls"].append((symbol, setup_key))
        candidate = (
            signal
            if signals_by_occurrence is None
            else signals_by_occurrence.get((symbol, setup_key))
        )
        return copy.deepcopy(candidate) if candidate is not None else None

    def run_should_skip(positions, symbol, setup_key, side):
        state["should_skip_calls"] += 1
        if callable(should_skip):
            return should_skip(positions, symbol, setup_key, side)
        return should_skip is True

    namespace.update(
        {
            "get_positions": lambda: copy.deepcopy(state["positions"]),
            "load_watchlist": lambda: list(watchlist or ["BTCUSDT"]),
            "get_last_candles_by_symbol": lambda: copy.deepcopy(state["last_candles"]),
            "save_last_candles_by_symbol": save_last_candles,
            "safe_fetch_ohlcv": lambda _symbol: object(),
            "closed_candles": lambda _df: _ClosedCandle(),
            "MAX_OPEN_POSITIONS": max_open_positions,
            "SETUPS": setups or {"TURTLE20": {"label": "Turtle 20"}},
            "analyze_symbol_setup": analyze,
            "should_skip_due_to_open_position": run_should_skip,
            "STARTUP_GUARD_SECONDS": startup_guard_seconds,
            "turtle_risk_guard_allows": run_risk_guard,
            "funnel_inc": lambda _name: None,
            "save_positions": save_positions,
            "redis_list_append": lambda key, value: signals.append((key, copy.deepcopy(value))) or True,
            "record_event": lambda event, pos, extra=None: events.append((event, copy.deepcopy(pos), extra)),
            "set_cooldown": lambda *args: cooldowns.append(args),
            "send_automatic_telegram": lambda *args, **kwargs: telegram.append((args, kwargs)),
            "safe_send_telegram": object(),
            "signal_message": lambda _sig: "signal",
            "SIGNALS_KEY": "signals",
            "HEALTH": {},
            "data_hora_sp_str": lambda: "2026-08-10T12:00:00-03:00",
            "traceback": type("Traceback", (), {"print_exc": staticmethod(lambda: None)})(),
            "time": _OneLoopTime(),
            "SCAN_SLEEP_SECONDS": 0,
        }
    )
    _compile_turtle_functions(namespace, {"scanner_loop"})
    return namespace, {
        "state": state,
        "signals": signals,
        "events": events,
        "telegram": telegram,
        "saves": saves,
        "cooldowns": cooldowns,
        "last_candle_saves": last_candle_saves,
        "v1_calls": v1_calls,
    }


def _run_scanner_once(namespace):
    with pytest.raises(_StopLoop):
        namespace["scanner_loop"]()


def _open_v2_position(adapter, **overrides):
    namespace, v1_calls = _runtime_registry_namespace(adapter)
    position = _position(id="TURTLE20:BTCUSDT:LONG", **overrides)
    result = namespace["turtle_registry_open"](position)
    assert result["ok"] is True
    assert result["write_committed"] is True
    assert v1_calls == []
    return position


def test_gate_off_preserves_turtle_v1_open_behavior_without_v2_identity():
    calls = []
    fake = _FakePaperAdapter()
    namespace = _compile_registry_functions(_namespace(gate=False, fake_adapter=fake, v1_calls=calls))
    signal = _position()

    result = namespace["turtle_registry_open"](signal)

    assert result == {"ok": True, "trade_id": "v1-trade"}
    assert [call[0] for call in calls] == ["register_open_trade"]
    assert fake.calls == []
    assert "execution_id" not in signal
    assert "lifecycle_id" not in signal
    assert "registry_v2_routed" not in signal


def test_enabled_turtle_open_routes_exclusively_to_v2_paper_adapter():
    calls = []
    fake = _FakePaperAdapter()
    namespace = _compile_registry_functions(_namespace(gate=True, fake_adapter=fake, v1_calls=calls))
    signal = _position()

    result = namespace["turtle_registry_open"](signal)

    assert result["ok"] is True
    assert calls == []
    assert len(fake.calls) == 1
    operation, received_position, kwargs = fake.calls[0]
    assert operation == "register"
    assert received_position is signal
    assert kwargs["execution_mode"] == "PAPER"
    assert kwargs["registry_mode"] == "PAPER"
    assert kwargs["idempotency_key"] == (
        'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
        '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
    )
    assert signal["registry_v2_routed"] is True
    assert signal["registry_v2_result"]["write_committed"] is True


def test_v2_open_failure_has_no_v1_registry_fallback():
    calls = []
    fake = _FakePaperAdapter(enabled=False)
    namespace = _compile_registry_functions(_namespace(gate=True, fake_adapter=fake, v1_calls=calls))
    signal = _position()

    result = namespace["turtle_registry_open"](signal)

    assert result["ok"] is False
    assert result["status"] == "REGISTRY_V2_PAPER_WRITE_DISABLED"
    assert [call[0] for call in fake.calls] == ["register"]
    assert calls == []
    assert "registry_v2_routed" not in signal


def test_v2_routed_management_and_close_never_call_v1_mutators():
    calls = []
    fake = _FakePaperAdapter()
    namespace = _compile_registry_functions(_namespace(gate=True, fake_adapter=fake, v1_calls=calls))
    position = _position(
        registry_v2_routed=True,
        execution_id="exec_test",
        lifecycle_id="exec_test",
    )

    updated = namespace["turtle_registry_update"](position, "TP50", price=105.0)
    closed = namespace["turtle_registry_close"](position, 106.0, "TURTLE_EXIT", 6.0, 1.2)

    assert updated["write_committed"] is True
    assert closed["write_committed"] is True
    assert [call[0] for call in fake.calls] == ["update", "close"]
    assert calls == []
    assert fake.calls[0][2]["execution_mode"] == "PAPER"
    assert fake.calls[0][2]["registry_mode"] == "PAPER"
    assert fake.calls[1][2]["execution_mode"] == "PAPER"
    assert fake.calls[1][2]["registry_mode"] == "PAPER"


def test_disabling_gate_on_existing_v2_routed_position_does_not_rewrite_v1():
    calls = []
    fake = _FakePaperAdapter(enabled=False)
    namespace = _compile_registry_functions(_namespace(gate=False, fake_adapter=fake, v1_calls=calls))
    position = _position(
        registry_v2_routed=True,
        execution_id="exec_test",
        lifecycle_id="exec_test",
    )

    result = namespace["turtle_registry_update"](position, "BE", new_sl=100.0)

    assert result["status"] == "REGISTRY_V2_PAPER_WRITE_DISABLED"
    assert [call[0] for call in fake.calls] == ["update"]
    assert calls == []


def test_preexisting_v1_position_remains_v1_for_management_even_when_new_gate_is_enabled():
    calls = []
    fake = _FakePaperAdapter()
    namespace = _compile_registry_functions(_namespace(gate=True, fake_adapter=fake, v1_calls=calls))
    position = _position(trade_registry_id="v1-trade")

    result = namespace["turtle_registry_update"](position, "BE", new_sl=100.0)

    assert result == {"ok": True, "trade_id": "v1-trade"}
    assert [call[0] for call in calls] == ["update_trade"]
    assert fake.calls == []


@pytest.mark.parametrize(
    "status",
    (
        paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT,
        wal.WAL_CONFLICT,
    ),
)
def test_productive_scanner_noncommitted_register_failure_retries_same_candle(tmp_path, status):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path), register_status=status)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    namespace, observed = _scanner_namespace(adapter, signal)

    _run_scanner_once(namespace)

    assert observed["state"]["risk_calls"] == 1
    assert adapter.register_calls == 1
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["saves"] == []
    assert observed["state"]["last_candles"] == {}
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == []

    adapter._register_status = None
    _run_scanner_once(namespace)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert observed["state"]["risk_calls"] == 2
    assert adapter.register_calls == 2
    assert len(committed) == 1
    assert observed["state"]["positions"][signal["id"]]["execution_id"] == committed[0].execution_id
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert observed["v1_calls"] == []


def test_productive_scanner_new_v2_signal_runs_risk_registers_saves_and_advances_candle(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    namespace, observed = _scanner_namespace(adapter, signal)

    _run_scanner_once(namespace)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    assert adapter.register_calls == 1
    assert observed["state"]["risk_calls"] == 1
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    position = observed["state"]["positions"][signal["id"]]
    assert position["execution_id"] == position["lifecycle_id"] == committed[0].execution_id
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert observed["v1_calls"] == []


def test_productive_scanner_new_risk_deny_prevents_register(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    namespace, observed = _scanner_namespace(
        adapter,
        signal,
        risk_guard=lambda _sig: (False, {"reasons": ["test_deny"], "warnings": []}),
    )

    _run_scanner_once(namespace)

    assert observed["state"]["risk_calls"] == 1
    assert adapter.register_calls == 0
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["telegram"] == []
    assert [event[0] for event in observed["events"]] == ["TRADE_BLOCKED"]
    assert len(observed["cooldowns"]) == 1
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == []
    assert observed["v1_calls"] == []


def test_productive_scanner_local_save_failure_retries_same_committed_register_in_process(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    namespace, observed = _scanner_namespace(adapter, signal, save_ok=False)

    _run_scanner_once(namespace)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    execution_id = committed[0].execution_id
    assert adapter.register_calls == 1
    assert observed["state"]["risk_calls"] == 1
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["last_candle_saves"] == [{}]

    observed["state"]["save_ok"] = True
    _run_scanner_once(namespace)

    assert adapter.register_calls == 1
    assert observed["state"]["risk_calls"] == 1
    recovered = observed["state"]["positions"][signal["id"]]
    assert recovered["execution_id"] == recovered["lifecycle_id"] == execution_id
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed
    assert observed["v1_calls"] == []


def test_productive_scanner_restart_recovers_committed_register_without_current_risk(tmp_path):
    first_adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    first, first_observed = _scanner_namespace(first_adapter, signal, save_ok=False)

    _run_scanner_once(first)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    execution_id = committed[0].execution_id
    assert first_observed["state"]["positions"] == {}

    restarted_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    )
    restarted_state = {"positions": {}, "last_candles": {}, "save_ok": True}
    restarted, observed = _scanner_namespace(
        restarted_adapter,
        signal,
        state=restarted_state,
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )

    _run_scanner_once(restarted)

    assert restarted_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    recovered = observed["state"]["positions"][signal["id"]]
    assert recovered["execution_id"] == recovered["lifecycle_id"] == execution_id
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed
    assert observed["v1_calls"] == []


def test_productive_scanner_gate_false_restart_recovers_committed_register_without_v1(
    tmp_path,
):
    first_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    )
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    first, first_observed = _scanner_namespace(first_adapter, signal, save_ok=False)

    _run_scanner_once(first)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    execution_id = committed[0].execution_id
    assert first_observed["state"]["positions"] == {}

    restarted_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=False, storage_dir=tmp_path)
    )
    restarted, observed = _scanner_namespace(
        restarted_adapter,
        signal,
        gate=False,
        state={"positions": {}, "last_candles": {}, "save_ok": True},
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )

    _run_scanner_once(restarted)

    assert restarted_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    recovered = observed["state"]["positions"][signal["id"]]
    assert recovered["execution_id"] == recovered["lifecycle_id"] == execution_id
    assert recovered["registry_v2_routed"] is True
    assert recovered["registry_v2_register_idempotency_key"].startswith(
        "turtle-paper-register-occurrence:v1:"
    )
    assert observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed


def test_productive_scanner_gate_false_recovery_save_failure_retries_without_republish(
    tmp_path,
):
    signal = _position(id="TURTLE20:BTCUSDT:LONG")

    # A: an enabled V2 REGISTER commits, but the local card does not persist.
    first_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    )
    first, first_observed = _scanner_namespace(first_adapter, signal, save_ok=False)

    _run_scanner_once(first)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    execution_id = committed[0].execution_id
    assert len(first_observed["saves"]) == 1
    first_attempt = first_observed["saves"][0][signal["id"]]
    occurrence_key = first_attempt["registry_v2_register_idempotency_key"]
    assert first_adapter.register_calls == 1
    assert first_observed["state"]["risk_calls"] == 1
    assert first_attempt["execution_id"] == first_attempt["lifecycle_id"] == execution_id
    assert first_attempt["registry_v2_routed"] is True
    assert first_observed["state"]["positions"] == {}
    assert first_observed["signals"] == first_observed["events"] == first_observed["telegram"] == []
    assert first_observed["cooldowns"] == []
    assert first_observed["state"]["last_candles"] == {}
    assert first_observed["last_candle_saves"] == [{}]
    assert first_observed["v1_calls"] == []

    # B: after restart with the gate off, exact V2 recovery must still fail
    # closed when the recovered local card cannot be saved.
    second_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=False, storage_dir=tmp_path)
    )
    second, second_observed = _scanner_namespace(
        second_adapter,
        signal,
        gate=False,
        save_ok=False,
        state={"positions": {}, "last_candles": {}},
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )

    _run_scanner_once(second)

    assert len(second_observed["saves"]) == 1
    second_attempt = second_observed["saves"][0][signal["id"]]
    assert second_adapter.register_calls == 0
    assert second_observed["state"]["risk_calls"] == 0
    assert second_attempt["execution_id"] == second_attempt["lifecycle_id"] == execution_id
    assert second_attempt["registry_v2_routed"] is True
    assert second_attempt["registry_v2_register_idempotency_key"] == occurrence_key
    assert second_observed["state"]["positions"] == {}
    assert second_observed["signals"] == second_observed["events"] == second_observed["telegram"] == []
    assert second_observed["cooldowns"] == []
    assert second_observed["state"]["last_candles"] == {}
    assert second_observed["last_candle_saves"] == [{}]
    assert second_observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed

    # C: a later gate-off retry persists the same recovered V2 card and only
    # then publishes the normal local success effects.
    third_adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=False, storage_dir=tmp_path)
    )
    third, third_observed = _scanner_namespace(
        third_adapter,
        signal,
        gate=False,
        state={"positions": {}, "last_candles": {}},
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )

    _run_scanner_once(third)

    assert len(third_observed["saves"]) == 1
    assert third_adapter.register_calls == 0
    assert third_observed["state"]["risk_calls"] == 0
    recovered = third_observed["state"]["positions"][signal["id"]]
    assert recovered["execution_id"] == recovered["lifecycle_id"] == execution_id
    assert recovered["registry_v2_routed"] is True
    assert recovered["registry_v2_register_idempotency_key"] == occurrence_key
    assert third_observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert len(third_observed["signals"]) == len(third_observed["events"]) == len(third_observed["telegram"]) == 1
    assert len(third_observed["cooldowns"]) == 1
    assert third_observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed


def test_productive_scanner_gate_false_without_committed_register_preserves_v1_open(
    tmp_path,
):
    adapter = _LifecycleAdapter(
        paper.RegistryV2PaperRuntimeAdapter(enabled=False, storage_dir=tmp_path)
    )
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    scanner, observed = _scanner_namespace(adapter, signal, gate=False)

    _run_scanner_once(scanner)

    assert adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 1
    assert [call[0] for call in observed["v1_calls"]] == ["register_open_trade"]
    opened = observed["state"]["positions"][signal["id"]]
    assert opened.get("registry_v2_routed") is not True


def test_productive_scanner_committed_recovery_bypasses_all_current_new_entry_gates(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    committed_card = _commit_source_register(adapter, signal)
    scanner_adapter = _LifecycleAdapter(adapter)
    existing = _position(id="already-open")
    state = {"positions": {"already-open": existing}, "last_candles": {}, "save_ok": True}
    scanner, observed = _scanner_namespace(
        scanner_adapter,
        signal,
        state=state,
        max_open_positions=1,
        should_skip=lambda *_args: True,
        startup_guard_seconds=60,
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )

    _run_scanner_once(scanner)

    recovered = observed["state"]["positions"][signal["id"]]
    assert scanner_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["should_skip_calls"] == 0
    assert recovered["execution_id"] == recovered["lifecycle_id"] == committed_card["execution_id"]
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert observed["v1_calls"] == []


def test_productive_scanner_new_occurrence_respects_max_position_gate(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    state = {"positions": {"already-open": _position(id="already-open")}, "last_candles": {}}
    scanner, observed = _scanner_namespace(
        adapter,
        signal,
        state=state,
        max_open_positions=1,
    )

    _run_scanner_once(scanner)

    assert observed["state"]["analysis_calls"] == [("BTCUSDT", "TURTLE20")]
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["should_skip_calls"] == 0
    assert adapter.register_calls == 0
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["v1_calls"] == []


def test_productive_scanner_new_occurrence_respects_open_position_gate(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    scanner, observed = _scanner_namespace(
        adapter,
        signal,
        should_skip=lambda *_args: True,
    )

    _run_scanner_once(scanner)

    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["should_skip_calls"] == 1
    assert adapter.register_calls == 0
    assert observed["signals"] == observed["telegram"] == []
    assert observed["events"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert observed["v1_calls"] == []


def test_productive_scanner_exact_local_pid_recovery_is_idempotent(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    committed_card = _commit_source_register(adapter, signal)
    existing = copy.deepcopy(committed_card)
    state = {"positions": {signal["id"]: existing}, "last_candles": {}, "save_ok": True}
    scanner_adapter = _LifecycleAdapter(adapter)
    scanner, observed = _scanner_namespace(scanner_adapter, signal, state=state)

    _run_scanner_once(scanner)

    assert scanner_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["should_skip_calls"] == 0
    assert observed["state"]["positions"] == {signal["id"]: existing}
    assert observed["saves"] == []
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {"BTCUSDT": 1_700_000_000}
    assert observed["v1_calls"] == []


def test_productive_scanner_conflicting_local_pid_recovery_fails_closed(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    _commit_source_register(adapter, signal)
    conflicting = _position(
        id=signal["id"],
        execution_id="exec_00000000-0000-4000-8000-000000000002",
        lifecycle_id="exec_00000000-0000-4000-8000-000000000002",
    )
    before = copy.deepcopy(conflicting)
    state = {"positions": {signal["id"]: conflicting}, "last_candles": {}, "save_ok": True}
    scanner_adapter = _LifecycleAdapter(adapter)
    scanner, observed = _scanner_namespace(scanner_adapter, signal, state=state)

    _run_scanner_once(scanner)

    assert scanner_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["positions"] == {signal["id"]: before}
    assert observed["saves"] == []
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["v1_calls"] == []


def test_productive_scanner_unresolved_setup_stops_same_symbol_new_setup(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    setup_a = _position(id="TURTLE20:BTCUSDT:LONG", setup="TURTLE20")
    setup_b = _position(id="TURTLE55:BTCUSDT:LONG", setup="TURTLE55", setup_label="Turtle 55")
    scanner, observed = _scanner_namespace(
        adapter,
        setup_a,
        setups={"TURTLE20": {}, "TURTLE55": {}},
        signals_by_occurrence={
            ("BTCUSDT", "TURTLE20"): setup_a,
            ("BTCUSDT", "TURTLE55"): setup_b,
        },
        save_behavior=lambda _positions, call_number: call_number != 1,
    )

    _run_scanner_once(scanner)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert observed["state"]["analysis_calls"] == [("BTCUSDT", "TURTLE20")]
    assert adapter.register_calls == 1
    assert len(committed) == 1
    assert committed[0].mutation_payload["trade"]["setup"] == "TURTLE20"
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}


def test_productive_scanner_unrelated_symbol_continues_after_unresolved_v2_setup(tmp_path):
    adapter = _LifecycleAdapter(paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path))
    btc_signal = _position(id="TURTLE20:BTCUSDT:LONG", symbol="BTCUSDT")
    eth_signal = _position(id="TURTLE20:ETHUSDT:LONG", symbol="ETHUSDT")
    scanner, observed = _scanner_namespace(
        adapter,
        btc_signal,
        watchlist=["BTCUSDT", "ETHUSDT"],
        signals_by_occurrence={
            ("BTCUSDT", "TURTLE20"): btc_signal,
            ("ETHUSDT", "TURTLE20"): eth_signal,
        },
        save_behavior=lambda _positions, call_number: call_number != 1,
    )

    _run_scanner_once(scanner)

    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert observed["state"]["analysis_calls"] == [
        ("BTCUSDT", "TURTLE20"),
        ("ETHUSDT", "TURTLE20"),
    ]
    assert adapter.register_calls == 2
    assert len(committed) == 2
    assert set(observed["state"]["positions"]) == {eth_signal["id"]}
    assert observed["state"]["positions"][eth_signal["id"]]["symbol"] == "ETHUSDT"
    assert observed["state"]["last_candles"] == {"ETHUSDT": 1_700_000_000}
    assert len(observed["signals"]) == len(observed["events"]) == len(observed["telegram"]) == 1
    assert len(observed["cooldowns"]) == 1
    assert observed["v1_calls"] == []


def test_productive_scanner_signal_ts_mismatch_in_source_evidence_fails_closed(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    current_signal = _position(
        id="TURTLE20:BTCUSDT:LONG",
        signal_ts=1_700_000_001,
        opened_candle_ts=1_700_000_001,
    )
    runtime, _v1_calls = _runtime_registry_namespace(adapter)
    source_key = runtime["turtle_registry_open_occurrence_key"](current_signal)
    assert source_key is not None
    corrupt_row = _position(id=current_signal["id"])
    assert adapter.register_turtle_paper(
        corrupt_row,
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        idempotency_key=source_key,
    ).ok is True
    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1

    scanner_adapter = _LifecycleAdapter(adapter)
    scanner, observed = _scanner_namespace(
        scanner_adapter,
        current_signal,
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )
    _run_scanner_once(scanner)

    assert scanner_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed


def test_productive_scanner_duplicate_source_evidence_fails_closed(monkeypatch, tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    runtime, _v1_calls = _runtime_registry_namespace(adapter)
    source_key = runtime["turtle_registry_open_occurrence_key"](signal)
    assert source_key is not None
    assert adapter.register_turtle_paper(
        copy.deepcopy(signal),
        execution_mode=schema.PAPER,
        registry_mode=schema.PAPER,
        idempotency_key=source_key,
    ).ok is True
    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1
    original_inspection = paper.wal.inspect_wal_recovery_state

    def duplicate_source_evidence(storage):
        inspection = original_inspection(storage)
        event = next(
            item
            for item in inspection.committed_events
            if item.operation == "REGISTER" and item.idempotency_key == source_key
        )
        return replace(
            inspection,
            committed_events=(event, replace(event, event_id="duplicate-source-evidence")),
        )

    monkeypatch.setattr(paper.wal, "inspect_wal_recovery_state", duplicate_source_evidence)
    scanner_adapter = _LifecycleAdapter(adapter)
    scanner, observed = _scanner_namespace(
        scanner_adapter,
        signal,
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )
    _run_scanner_once(scanner)

    assert scanner_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed


def test_productive_scanner_recovery_blocked_prevents_recovery_or_new_register(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    signal = _position(id="TURTLE20:BTCUSDT:LONG")
    first, _first_observed = _scanner_namespace(adapter, signal, save_ok=False)
    _run_scanner_once(first)
    committed = [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(committed) == 1

    pending_position = _position(
        id=signal["id"],
        execution_id=committed[0].execution_id,
        lifecycle_id=committed[0].execution_id,
    )

    def crash_after_prepared(stage):
        if stage == wal.AFTER_PREPARED:
            raise RuntimeError("after_prepared")

    with pytest.raises(RuntimeError, match="after_prepared"):
        adapter.update_turtle_paper(
            pending_position,
            event="TP50",
            updates={"pending": True},
            execution_mode=schema.PAPER,
            registry_mode=schema.PAPER,
            fault_hook=crash_after_prepared,
        )

    blocked_adapter = _LifecycleAdapter(adapter)
    blocked, observed = _scanner_namespace(
        blocked_adapter,
        signal,
        risk_guard=lambda _sig: (False, {"reasons": ["current_deny"], "warnings": []}),
    )
    _run_scanner_once(blocked)

    assert blocked_adapter.register_calls == 0
    assert observed["state"]["risk_calls"] == 0
    assert observed["state"]["positions"] == {}
    assert observed["signals"] == observed["events"] == observed["telegram"] == []
    assert observed["cooldowns"] == []
    assert observed["state"]["last_candles"] == {}
    assert observed["v1_calls"] == []
    assert [
        event
        for event in _storage_events(tmp_path)
        if event.operation == "REGISTER" and event.state == wal.EVENT_COMMITTED
    ] == committed


def test_productive_tp50_failure_blocks_local_transition_and_notifications(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    position = _open_v2_position(adapter)
    before = copy.deepcopy(position)
    failing = _LifecycleAdapter(adapter, update_status=paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT)
    state = {"positions": {position["id"]: before}}
    namespace, observed = _management_namespace(failing, state, price=106.0)

    _run_management_once(namespace)

    assert state["positions"] == {position["id"]: before}
    assert observed["saves"] == []
    assert observed["events"] == observed["telegram"] == observed["trades"] == []
    assert [event for event in _storage_events(tmp_path) if event.operation == "UPDATE"] == []


def test_productive_be_failure_retries_only_the_missing_committed_step_after_restart(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    position = _open_v2_position(adapter)
    before = copy.deepcopy(position)
    failing = _LifecycleAdapter(
        adapter,
        update_status=lambda _position, kwargs: (
            paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT if kwargs.get("event") == "BE" else None
        ),
    )
    state = {"positions": {position["id"]: before}}
    namespace, observed = _management_namespace(failing, state, price=106.0)

    _run_management_once(namespace)

    updates_after_failure = [
        event for event in _storage_events(tmp_path)
        if event.operation == "UPDATE" and event.state == wal.EVENT_COMMITTED
    ]
    assert [event.mutation_payload["patch"]["last_event"] for event in updates_after_failure] == ["TP50"]
    assert state["positions"] == {position["id"]: before}
    assert observed["events"] == observed["telegram"] == observed["trades"] == []

    restarted_state = {"positions": copy.deepcopy(state["positions"])}
    restarted, restarted_observed = _management_namespace(adapter, restarted_state, price=112.0)
    _run_management_once(restarted)

    updates = [
        event for event in _storage_events(tmp_path)
        if event.operation == "UPDATE" and event.state == wal.EVENT_COMMITTED
    ]
    assert [event.mutation_payload["patch"]["last_event"] for event in updates] == ["TP50", "BE"]
    restored = restarted_state["positions"][position["id"]]
    assert restored["tp50_hit"] is True
    assert restored["be_moved"] is True
    assert restored["stop"] == 100.0
    assert restarted_observed["events"]
    assert restarted_observed["telegram"]


def test_productive_committed_tp50_be_recovery_uses_original_facts_without_second_update(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    position = _open_v2_position(adapter)
    before = copy.deepcopy(position)
    crashed_state = {"positions": {position["id"]: before}, "save_ok": False}
    crashed, crashed_observed = _management_namespace(adapter, crashed_state, price=106.0)

    _run_management_once(crashed)

    committed_before_restart = [
        event for event in _storage_events(tmp_path)
        if event.operation == "UPDATE" and event.state == wal.EVENT_COMMITTED
    ]
    assert [event.mutation_payload["patch"]["last_event"] for event in committed_before_restart] == ["TP50", "BE"]
    assert crashed_state["positions"] == {position["id"]: before}
    assert crashed_observed["events"] == crashed_observed["telegram"] == crashed_observed["trades"] == []

    restarted_state = {"positions": copy.deepcopy(crashed_state["positions"])}
    restarted, _observed = _management_namespace(adapter, restarted_state, price=130.0)
    _run_management_once(restarted)

    committed_after_restart = [
        event for event in _storage_events(tmp_path)
        if event.operation == "UPDATE" and event.state == wal.EVENT_COMMITTED
    ]
    assert committed_after_restart == committed_before_restart
    restored = restarted_state["positions"][position["id"]]
    assert restored["tp50_hit"] is True
    assert restored["be_moved"] is True
    assert restored["stop"] == 100.0
    assert restored["candles_to_tp50"] == 0


def test_productive_close_failure_retains_local_position_without_close_observability(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    position = _open_v2_position(adapter)
    before = copy.deepcopy(position)
    failing = _LifecycleAdapter(adapter, close_status=paper.REGISTRY_PERSISTENCE_LOCK_TIMEOUT)
    state = {"positions": {position["id"]: before}}
    namespace, observed = _management_namespace(failing, state, price=94.0)

    _run_management_once(namespace)

    assert state["positions"] == {position["id"]: before}
    assert observed["saves"] == []
    assert observed["events"] == observed["telegram"] == observed["trades"] == []
    assert [
        event for event in _storage_events(tmp_path)
        if event.operation == "FULL_CLOSE" and event.state == wal.EVENT_COMMITTED
    ] == []


def test_productive_committed_close_recovers_original_economics_without_second_full_close(tmp_path):
    adapter = paper.RegistryV2PaperRuntimeAdapter(enabled=True, storage_dir=tmp_path)
    position = _open_v2_position(adapter)
    before = copy.deepcopy(position)
    crashed_state = {"positions": {position["id"]: before}, "save_ok": False}
    crashed, crashed_observed = _management_namespace(adapter, crashed_state, price=94.0)

    _run_management_once(crashed)

    closes_before_restart = [
        event for event in _storage_events(tmp_path)
        if event.operation == "FULL_CLOSE" and event.state == wal.EVENT_COMMITTED
    ]
    assert len(closes_before_restart) == 1
    assert crashed_state["positions"] == {position["id"]: before}
    assert crashed_observed["events"] == crashed_observed["telegram"] == crashed_observed["trades"] == []

    restarted_state = {"positions": copy.deepcopy(crashed_state["positions"])}
    restarted, observed = _management_namespace(adapter, restarted_state, price=120.0)
    _run_management_once(restarted)

    assert restarted_state["positions"] == {}
    closes_after_restart = [
        event for event in _storage_events(tmp_path)
        if event.operation == "FULL_CLOSE" and event.state == wal.EVENT_COMMITTED
    ]
    assert closes_after_restart == closes_before_restart
    assert len(observed["trades"]) == 1
    trade = observed["trades"][0][1]
    assert trade["exit_price"] == 94.0
    assert trade["exit_reason"] == "STOP"
    assert trade["result_pct"] == -6.0


def test_turtle_v2_updates_are_exactly_the_tp50_be_one_shot_transition():
    management = next(
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "management_loop"
    )
    one_shot_branches = [
        node
        for node in ast.walk(management)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and isinstance(node.test.operand.func, ast.Attribute)
        and isinstance(node.test.operand.func.value, ast.Name)
        and node.test.operand.func.value.id == "pos"
        and node.test.operand.func.attr == "get"
        and len(node.test.operand.args) == 1
        and isinstance(node.test.operand.args[0], ast.Constant)
        and node.test.operand.args[0].value == "tp50_hit"
    ]
    assert len(one_shot_branches) == 1
    one_shot = one_shot_branches[0]
    calls = [
        node
        for node in ast.walk(one_shot)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "turtle_registry_update"
    ]
    event_names = [
        call.args[1].value
        for call in calls
        if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant)
    ]
    # The V1 compatibility branch and the V2-authoritative branch each retain
    # the accepted TP50 -> BE one-shot pair; recovery is outside this branch.
    assert event_names == ["TP50", "BE", "TP50", "BE"]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "save_positions"
        and node.lineno > max(call.lineno for call in calls)
        for node in ast.walk(management)
    )


def test_source_guards_keep_the_turtle_change_at_the_registry_boundary_only():
    tree = TURTLE_TREE
    imported_adapter_names = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "registry_v2_paper_runtime_adapter"
        for alias in node.names
    }
    registry_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "turtle_registry_read_committed_open",
            "turtle_registry_open",
            "turtle_registry_update",
            "turtle_registry_close",
        }
    }

    assert imported_adapter_names == {
        "REGISTRY_V2_PAPER_WRITE_ENABLED",
        "get_registry_v2_paper_runtime_adapter",
    }
    assert set(registry_functions) == {
        "turtle_registry_read_committed_open",
        "turtle_registry_open",
        "turtle_registry_update",
        "turtle_registry_close",
    }
    assert "registry_v2" not in ast.get_source_segment(TURTLE_SOURCE, next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "analyze_symbol_setup"
    ))
    assert "registry_v2" not in ast.get_source_segment(TURTLE_SOURCE, next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "management_loop"
    ))
    assert "LIVE" not in "\n".join(
        ast.get_source_segment(TURTLE_SOURCE, node) or "" for node in registry_functions.values()
    )

    for function in registry_functions.values():
        adapter_calls = [
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {
                "read_turtle_paper_committed_register",
                "register_turtle_paper",
                "update_turtle_paper",
                "close_turtle_paper",
            }
        ]
        for call in adapter_calls:
            keyword_values = {
                keyword.arg: keyword.value.value
                for keyword in call.keywords
                if keyword.arg in {"execution_mode", "registry_mode"}
                and isinstance(keyword.value, ast.Constant)
            }
            assert keyword_values == {
                "execution_mode": "PAPER",
                "registry_mode": "PAPER",
            }


def test_scanner_source_guard_keeps_exact_read_recovery_before_new_risk_and_register():
    scanner = next(
        node
        for node in TURTLE_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "scanner_loop"
    )

    def calls_named(name):
        return [
            node
            for node in ast.walk(scanner)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]

    recovery_calls = calls_named("turtle_registry_read_committed_open")
    open_position_calls = calls_named("should_skip_due_to_open_position")
    risk_calls = calls_named("turtle_risk_guard_allows")
    register_calls = calls_named("turtle_registry_open")
    redis_calls = calls_named("redis_list_append")
    startup_guards = [
        node
        for node in ast.walk(scanner)
        if isinstance(node, ast.If)
        and "STARTUP_GUARD_SECONDS" in (ast.get_source_segment(TURTLE_SOURCE, node.test) or "")
    ]
    max_position_gates_after_recovery = [
        node
        for node in ast.walk(scanner)
        if isinstance(node, ast.If)
        and node.lineno > recovery_calls[0].lineno
        and "MAX_OPEN_POSITIONS" in (ast.get_source_segment(TURTLE_SOURCE, node.test) or "")
    ]

    assert len(recovery_calls) == len(open_position_calls) == len(risk_calls) == len(register_calls) == 1
    assert len(startup_guards) == 1
    assert recovery_calls[0].lineno < open_position_calls[0].lineno < startup_guards[0].lineno
    assert startup_guards[0].lineno < risk_calls[0].lineno < register_calls[0].lineno
    assert max_position_gates_after_recovery
    assert len(redis_calls) == 1
    scanner_source = ast.get_source_segment(TURTLE_SOURCE, scanner) or ""
    assert "logical_trade_id" not in scanner_source
