import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from registry_execution_identity import is_v2_execution_id


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)

_IDENTITY_ONE = "exec_00000000-0000-4000-8000-000000000001"
_IDENTITY_TWO = "exec_00000000-0000-4000-8000-000000000002"
_SOURCE_KEY = (
    'turtle-paper-register-occurrence:v1:{"setup":"TURTLE20","side":"LONG",'
    '"signal_ts":1700000000,"symbol":"BTCUSDT"}'
)

_SYNC_FUNCTIONS = {
    "_trade_registry_sync_symbol",
    "normalize_registry_symbol",
    "normalize_registry_bot",
    "_trade_registry_sync_side",
    "_trade_registry_sync_setup",
    "_trade_registry_sync_entry",
    "_trade_registry_sync_sl",
    "_trade_registry_sync_qty",
    "_trade_registry_sync_v2_register_source_key_valid",
    "_trade_registry_sync_v2_ownership",
    "_trade_registry_sync_protected_signature",
    "_trade_registry_existing_trade_ids",
    "_trade_registry_sync_candidate",
    "_trade_registry_signature_from_items",
    "_trade_registry_signature_map",
    "mark_registry_missing_trades",
    "sync_trade_registry_from_open_positions",
}


class _BotModule:
    def __init__(self, positions):
        self.positions = copy.deepcopy(positions)


class _FakeTradeRegistry:
    def __init__(self, open_trades=None):
        self.registry = {"open_trades": copy.deepcopy(open_trades or {})}
        self.register_calls = []
        self.save_calls = []

    def load_registry(self):
        return self.registry

    def get_trade_registry_snapshot(self):
        return {"open_trades": list(self.registry["open_trades"].values())}

    @staticmethod
    def make_trade_id(bot, symbol, side, setup):
        return f"{bot}:{setup}:{symbol}:{side}"

    def register_open_trade(self, **kwargs):
        self.register_calls.append(copy.deepcopy(kwargs))
        trade_id = self.make_trade_id(
            kwargs["bot"],
            kwargs["symbol"],
            kwargs["side"],
            kwargs["setup"],
        )
        self.registry["open_trades"][trade_id] = {
            "trade_id": trade_id,
            "bot": kwargs["bot"],
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "setup": kwargs["setup"],
            "status": "OPEN",
            "source": kwargs["source"],
        }
        return {"ok": True, "trade_id": trade_id}

    def save_registry(self, registry):
        self.save_calls.append(copy.deepcopy(registry))
        self.registry = registry
        return True


def _compile_sync_functions(namespace):
    nodes = [
        node
        for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in _SYNC_FUNCTIONS
    ]
    assert {node.name for node in nodes} == _SYNC_FUNCTIONS
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace.setdefault(
        "c3_runtime_seam_v1",
        SimpleNamespace(
            _c3_closed_repair_writer_mutation_v1=(
                lambda _writer_id: lambda function: function
            )
        ),
    )
    exec(compile(module, "<main-traderegistry-v2-ownership>", "exec"), namespace)
    return namespace


def _position(**overrides):
    position = {
        "id": "TURTLE20:BTCUSDT:LONG",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "setup": "TURTLE20",
        "entry": 100.0,
        "stop": 95.0,
        "tp50": 105.0,
        "status": "OPEN",
    }
    position.update(overrides)
    return position


def _v2_owned_position(**overrides):
    position = _position()
    position.update(
        {
            "execution_id": _IDENTITY_ONE,
            "lifecycle_id": _IDENTITY_ONE,
            "registry_v2_routed": True,
            "registry_v2_register_idempotency_key": _SOURCE_KEY,
        }
    )
    position.update(overrides)
    return position


def _v1_trade(position, *, bot="TURTLE"):
    trade_id = f"{bot}:{position['setup']}:{position['symbol']}:{position['side']}"
    return {
        trade_id: {
            "trade_id": trade_id,
            "bot": bot,
            "symbol": position["symbol"],
            "side": position["side"],
            "setup": position["setup"],
            "status": "OPEN",
        }
    }


def _sync(registry, bot_positions, *, commit=True, write_gate=False):
    namespace = {
        "central_trade_registry": registry,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "LOADED_BOTS": {
            bot: _BotModule(positions) for bot, positions in bot_positions.items()
        },
        "REGISTRY_V2_PAPER_WRITE_ENABLED": write_gate,
        "_TRADE_REGISTRY_V2_TURTLE_REGISTER_OCCURRENCE_PREFIX": (
            "turtle-paper-register-occurrence:v1:"
        ),
        "is_v2_execution_id": is_v2_execution_id,
        "json": __import__("json"),
        "data_hora_sp_str": lambda: "2026-08-11T12:00:00-03:00",
        "_position_runner_r": lambda _position: None,
        "_position_runner_pct": lambda _position: None,
        "get_open_positions_from_module": (
            lambda module, key=None: copy.deepcopy(module.positions)
        ),
        "central_trade_registry_snapshot": lambda include_trades=False: {},
    }
    _compile_sync_functions(namespace)
    return namespace["sync_trade_registry_from_open_positions"](commit=commit)


def _mark_missing(registry, removed, *, timestamp="2026-09-06T01:00:00-03:00"):
    namespace = {
        "central_trade_registry": registry,
        "data_hora_sp_str": lambda: timestamp,
    }
    _compile_sync_functions(namespace)
    return namespace["mark_registry_missing_trades"](copy.deepcopy(removed))


@pytest.mark.parametrize("bot", ("TURTLE", "PREDATOR"))
def test_plain_legacy_candidates_still_sync_to_v1(bot):
    registry = _FakeTradeRegistry()
    position = _position(setup="TURTLE20" if bot == "TURTLE" else "PREDATOR")

    result = _sync(registry, {bot: [position]})

    assert result["ok"] is True
    assert len(registry.register_calls) == 1
    assert registry.register_calls[0]["source"] == "main_traderegistry_sync"


@pytest.mark.parametrize("write_gate", (True, False))
def test_exact_v2_owned_candidate_never_registers_v1(write_gate):
    registry = _FakeTradeRegistry()

    result = _sync(
        registry,
        {"TURTLE": [_v2_owned_position()]},
        write_gate=write_gate,
    )

    assert result["ok"] is True
    assert registry.register_calls == []
    assert registry.save_calls == []
    assert result["skipped"] == [
        {
            "bot": "TURTLE",
            "reason": "EXACT_V2_OWNED",
            "execution_id": _IDENTITY_ONE,
            "lifecycle_id": _IDENTITY_ONE,
        }
    ]


def test_exact_v2_owned_candidate_protects_existing_v1_row_from_missing_mutation():
    position = _v2_owned_position()
    registry = _FakeTradeRegistry(_v1_trade(position))

    result = _sync(registry, {"TURTLE": [position]})

    trade = next(iter(registry.registry["open_trades"].values()))
    assert registry.register_calls == []
    assert registry.save_calls == []
    assert trade["status"] == "OPEN"
    assert "missing_from_bots" not in trade
    assert result["removed_count"] == 0


@pytest.mark.parametrize(
    "overrides",
    (
        {"execution_id": None},
        {"lifecycle_id": None},
        {"lifecycle_id": _IDENTITY_TWO},
        {"execution_id": "exec_not_canonical"},
        {"registry_v2_register_idempotency_key": "not-a-v2-source-key"},
        {
            "registry_v2_register_idempotency_key": (
                "turtle-paper-register-occurrence:v1:not-json"
            )
        },
    ),
)
def test_malformed_explicit_v2_claim_fails_closed_for_new_v1_materialization(overrides):
    registry = _FakeTradeRegistry()

    result = _sync(registry, {"TURTLE": [_v2_owned_position(**overrides)]})

    assert result["ok"] is False
    assert registry.register_calls == []
    assert registry.save_calls == []
    assert result["skipped"][0]["reason"] == "MALFORMED_V2_CLAIM"
    assert any(
        item["error"] == "REGISTRY_V2_OWNERSHIP_IDENTITY_INVALID"
        for item in result["errors"]
    )


def test_malformed_v2_claim_with_known_legacy_signature_cannot_mark_v1_missing():
    position = _v2_owned_position(lifecycle_id=_IDENTITY_TWO)
    registry = _FakeTradeRegistry(_v1_trade(position))

    result = _sync(registry, {"TURTLE": [position]})

    trade = next(iter(registry.registry["open_trades"].values()))
    assert registry.register_calls == []
    assert registry.save_calls == []
    assert trade["status"] == "OPEN"
    assert result["v2_ownership_missing_mutation_blocked"] is True
    assert result["missing_mark_result"]["error"] == (
        "REGISTRY_V2_OWNERSHIP_MISSING_MUTATION_BLOCKED"
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {"logical_trade_id": "TURTLE:TURTLE20:BTCUSDT:LONG"},
        {"execution_id": _IDENTITY_ONE, "lifecycle_id": _IDENTITY_ONE},
        {"execution_mode": "PAPER", "registry_mode": "PAPER"},
    ),
)
def test_non_v2_legacy_fields_do_not_suppress_v1_materialization(overrides):
    registry = _FakeTradeRegistry()

    result = _sync(registry, {"TURTLE": [_position(**overrides)]})

    assert result["ok"] is True
    assert len(registry.register_calls) == 1


def test_ordinary_legacy_absence_still_marks_existing_v1_record_missing():
    position = _position()
    registry = _FakeTradeRegistry(_v1_trade(position))

    result = _sync(registry, {})

    trade = next(iter(registry.registry["open_trades"].values()))
    assert result["ok"] is True
    assert registry.save_calls
    assert trade["status"] == "MISSING_FROM_BOTS"
    assert trade["missing_from_bots"] is True


def test_missing_mark_is_persisted_once_then_becomes_idempotent():
    position = _position()
    open_trades = _v1_trade(position)
    trade_id = next(iter(open_trades))
    registry = _FakeTradeRegistry(open_trades)
    removed = [{"trade_id": trade_id}]

    first = _mark_missing(registry, removed)
    after_first = copy.deepcopy(registry.registry)
    second = _mark_missing(
        registry,
        removed,
        timestamp="2026-09-06T02:00:00-03:00",
    )

    assert first["ok"] is True
    assert first["marked_count"] == 1
    assert first["registry_write"] is True
    assert second == {
        "ok": True,
        "marked_count": 0,
        "marked": [],
        "already_marked": [trade_id],
        "registry_write": False,
    }
    assert len(registry.save_calls) == 1
    assert registry.registry == after_first


def test_existing_equivalent_missing_mark_preserves_timestamps_without_save():
    position = _position()
    open_trades = _v1_trade(position)
    trade_id = next(iter(open_trades))
    open_trades[trade_id].update(
        {
            "status": "MISSING_FROM_BOTS",
            "missing_from_bots": True,
            "missing_detected_at": "2026-09-05T20:00:00-03:00",
            "last_update": "2026-09-05T20:00:01-03:00",
        }
    )
    registry = _FakeTradeRegistry(open_trades)
    before = copy.deepcopy(registry.registry)

    result = _mark_missing(registry, [{"trade_id": trade_id}])

    assert result["marked_count"] == 0
    assert result["registry_write"] is False
    assert registry.save_calls == []
    assert registry.registry == before


def test_mixed_missing_batch_saves_only_the_effective_change():
    first = _position()
    second = _position(symbol="ETHUSDT", id="TURTLE20:ETHUSDT:LONG")
    open_trades = _v1_trade(first)
    open_trades.update(_v1_trade(second))
    first_id, second_id = tuple(open_trades)
    open_trades[first_id].update(
        {
            "status": "MISSING_FROM_BOTS",
            "missing_from_bots": True,
            "missing_detected_at": "2026-09-05T20:00:00-03:00",
            "last_update": "2026-09-05T20:00:01-03:00",
        }
    )
    registry = _FakeTradeRegistry(open_trades)

    result = _mark_missing(
        registry,
        [{"trade_id": first_id}, {"trade_id": second_id}],
    )

    assert result["marked_count"] == 1
    assert result["already_marked"] == [first_id]
    assert len(registry.save_calls) == 1
    assert registry.registry["open_trades"][first_id]["last_update"] == (
        "2026-09-05T20:00:01-03:00"
    )
    assert registry.registry["open_trades"][second_id]["last_update"] == (
        "2026-09-06T01:00:00-03:00"
    )


def test_missing_mark_fails_closed_when_persistence_is_not_confirmed():
    class _RejectingRegistry(_FakeTradeRegistry):
        def save_registry(self, registry):
            self.save_calls.append(copy.deepcopy(registry))
            return False

    position = _position()
    open_trades = _v1_trade(position)
    trade_id = next(iter(open_trades))
    registry = _RejectingRegistry(open_trades)
    before = copy.deepcopy(registry.registry)

    result = _mark_missing(registry, [{"trade_id": trade_id}])

    assert result == {
        "ok": False,
        "error": "REGISTRY_SAVE_NOT_CONFIRMED",
        "registry_write": False,
    }
    assert len(registry.save_calls) == 1
    assert registry.registry == before


def test_exact_v2_claim_without_a_legacy_signature_blocks_missing_mutation():
    position = _v2_owned_position(symbol=None, side=None, setup=None)
    registry = _FakeTradeRegistry(_v1_trade(_position()))

    result = _sync(registry, {"TURTLE": [position]})

    trade = next(iter(registry.registry["open_trades"].values()))
    assert registry.register_calls == []
    assert registry.save_calls == []
    assert trade["status"] == "OPEN"
    assert result["v2_ownership_missing_mutation_blocked"] is True
    assert result["missing_mark_result"]["error"] == (
        "REGISTRY_V2_OWNERSHIP_MISSING_MUTATION_BLOCKED"
    )
