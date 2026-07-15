from __future__ import annotations

import ast
import threading
import time as real_time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
BROKER_SOURCE = ROOT / "broker.py"


def _load_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    """Load selected final Falcon functions without importing its runtime module."""
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert definitions, name
        selected.append(definitions[-1])
    module = ast.Module(body=sorted(selected, key=lambda node: node.lineno), type_ignores=[])
    namespace = dict(globals_dict)
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    return namespace


def _load_broker_function(name: str, globals_dict: dict):
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    assert definitions, name
    namespace = dict(globals_dict)
    exec(compile(ast.Module(body=[definitions[-1]], type_ignores=[]), str(BROKER_SOURCE), "exec"), namespace)
    return namespace[name]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _position(**updates):
    value = {
        "symbol": "XRPUSDT",
        "side": "LONG",
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "qty": 2.0,
        "initial_qty": 2.0,
        "remaining_qty": 2.0,
        "entry": 2.0,
        "stop": 1.8,
        "tp50": 2.2,
        "broker_stop_order_id": "STOP-1",
        "broker_stop_amount": 2.0,
        "broker_stop_price": 1.8,
        "live_order_id": "ORDER-1",
        "live_client_order_id": "CLIENT-1",
        "lifecycle_id": "LIFECYCLE-1",
        "trade_registry_id": "TRADE-1",
    }
    value.update(updates)
    return value


class _ReadOnlyBroker:
    """Broker probe that permits snapshots and rejects every mutating operation."""

    MUTATING_METHODS = {
        "create_order",
        "cancel_order",
        "close_position",
        "managed_close_position_market",
        "replace_position_stop_order",
        "cancel_managed_stop_order",
        "create_position_stop_order",
    }

    def __init__(self, position_snapshot: dict, order_snapshot: dict, entry_snapshot: dict | None = None):
        self.position_snapshot = position_snapshot
        self.order_snapshot = order_snapshot
        self.entry_snapshot = entry_snapshot or {
            "ok": True,
            "status": "CLOSED",
            "order_id": "ORDER-1",
            "client_order_id": "CLIENT-1",
            "side": "BUY",
            "amount": 2.0,
            "filled": 2.0,
            "remaining": 0.0,
            "read_only": True,
            "sent": False,
        }
        self.read_calls: list[tuple] = []
        self.mutation_calls: list[tuple] = []

    def managed_position_snapshot(self, symbol, side, **kwargs):
        self.read_calls.append(("position", symbol, side, kwargs))
        return dict(self.position_snapshot)

    def managed_order_snapshot(self, symbol, order_id):
        self.read_calls.append(("order", symbol, order_id))
        return dict(self.entry_snapshot if str(order_id) == "ORDER-1" else self.order_snapshot)

    def __getattr__(self, name):
        if name in self.MUTATING_METHODS:
            def forbidden(*args, **kwargs):
                self.mutation_calls.append((name, args, kwargs))
                raise AssertionError(f"mutating Broker call attempted: {name}")

            return forbidden
        raise AttributeError(name)


def _position_snapshot(*, amount=2.0, closed=False, matched_count=1, ownership_safe=True):
    return {
        "ok": True,
        "status": "POSITION_SNAPSHOT",
        "amount": amount,
        "position_closed": closed,
        "matched_count": matched_count,
        "ownership_safe": ownership_safe,
        "read_only": True,
        "sent": False,
    }


def _order_snapshot(status="OPEN", *, ok=True, amount=2.0, filled=0.0):
    return {
        "ok": ok,
        "status": status,
        "id": "STOP-1",
        "order_id": "STOP-1",
        "amount": amount,
        "filled": filled,
        "stop_price": 1.8,
        "side": "SELL",
        "type": "STOP_MARKET",
        "working_type": "MARK_PRICE",
        "position_side": "LONG",
        "reduce_only": False,
        "read_only": True,
        "sent": False,
    }


def _verifier(broker: _ReadOnlyBroker, health: dict | None = None):
    health = {} if health is None else health
    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "_falcon_stop_status_flags",
            "_falcon_management_bool",
            "_falcon_protective_stop_evidence",
            "_falcon_stop_not_found_evidence",
            "_falcon_update_stop_health",
            "falcon_verify_live_disaster_stop",
        ),
        {
            "safe_float": _safe_float,
            "time": real_time,
            "data_hora_sp_str": lambda: "15/07/2026 10:00:00",
            "central_broker": broker,
            "HEALTH": health,
            "falcon_real_remaining_qty": lambda pos: _safe_float(pos.get("remaining_qty")),
            "falcon_update_registry_management": lambda *_args, **_kwargs: {
                "ok": True,
                "read_only_test": True,
            },
            "FALCON_STOP_VERIFY_INTERVAL_SECONDS": 15,
            "FALCON_STOP_VERIFY_PERSIST_SECONDS": 60,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
        },
    )
    return namespace["falcon_verify_live_disaster_stop"]


def test_stop_active_is_factually_verified_without_mutating_broker():
    broker = _ReadOnlyBroker(_position_snapshot(), _order_snapshot("OPEN"))
    position = _position()

    result = _verifier(broker)(position, now_epoch=1000.0, force=True, persist_registry=False)

    assert result["ok"] is True
    assert result["status"] == "DISASTER_STOP_ACTIVE_VERIFIED"
    assert result["management_allowed"] is True
    assert result["stop_order_active"] is True
    assert result["stop_order_filled"] is False
    assert result["protection_matches_position"] is True
    assert result["trigger_type"] == "MARK_PRICE"
    assert result["stop_order_type"] == "STOP_MARKET"
    assert result["entry_ownership_verified"] is True
    assert position["disaster_stop_active_verified"] is True
    assert [call[0] for call in broker.read_calls] == ["position", "order", "order"]
    assert broker.mutation_calls == []


@pytest.mark.parametrize(
    "updates",
    [
        {"type": "LIMIT"},
        {"side": "BUY"},
        {"position_side": "SHORT", "reduce_only": False},
    ],
)
def test_active_order_without_protective_type_side_or_close_semantics_is_rejected(updates):
    stop = _order_snapshot("OPEN")
    stop.update(updates)
    broker = _ReadOnlyBroker(_position_snapshot(), stop)

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["management_allowed"] is False
    assert result["status"] == "DISASTER_STOP_EVIDENCE_INSUFFICIENT"
    assert result["stop_anomaly_reason"] == "STOP_TYPE_SIDE_OR_CLOSE_SEMANTICS_NOT_CONFIRMED"
    assert broker.mutation_calls == []


def test_active_stop_does_not_authorize_management_without_entry_fill_identity():
    entry = {
        "ok": True,
        "status": "CLOSED",
        "order_id": "ORDER-1",
        "client_order_id": "OTHER-CLIENT",
        "side": "BUY",
        "filled": 2.0,
        "read_only": True,
        "sent": False,
    }
    broker = _ReadOnlyBroker(_position_snapshot(), _order_snapshot("OPEN"), entry_snapshot=entry)

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["entry_ownership_verified"] is False
    assert result["management_allowed"] is False
    assert result["status"] == "ENTRY_LIFECYCLE_OWNERSHIP_NOT_CONFIRMED"
    assert broker.mutation_calls == []


def test_active_stop_with_different_factual_order_id_is_never_authorized():
    stop = _order_snapshot("OPEN")
    stop["order_id"] = "OTHER-STOP"
    stop["id"] = "OTHER-STOP"
    broker = _ReadOnlyBroker(_position_snapshot(), stop)

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["stop_order_identity_match"] is False
    assert result["management_allowed"] is False
    assert result["status"] == "DISASTER_STOP_IDENTITY_MISMATCH"
    assert result["stop_anomaly_reason"] == "STOP_ORDER_IDENTITY_MISMATCH"
    assert broker.mutation_calls == []


def test_missing_stop_with_open_position_is_critical_and_never_mutates_broker():
    broker = _ReadOnlyBroker(
        _position_snapshot(),
        {"ok": False, "status": "ORDER_NOT_FOUND", "read_only": True, "sent": False},
    )

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["ok"] is False
    assert result["status"] == "DISASTER_STOP_NOT_FOUND"
    assert result["management_allowed"] is False
    assert result["stop_anomaly_detected"] is True
    assert result["stop_anomaly_reason"] == "DISASTER_STOP_NOT_FOUND"
    assert result["manual_intervention_required"] is True
    assert result["failsafe_eligible"] is False
    assert broker.mutation_calls == []


def test_generic_stop_snapshot_error_is_not_reclassified_as_not_found_or_filled():
    broker = _ReadOnlyBroker(
        _position_snapshot(),
        {"ok": False, "status": "ORDER_SNAPSHOT_ERROR", "read_only": True, "sent": False},
    )

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["status"] == "STOP_ORDER_VERIFICATION_ERROR"
    assert result["stop_anomaly_reason"] == "STOP_ORDER_VERIFICATION_ERROR"
    assert result["central_only_reconcile_required"] is False
    assert result["stop_order_filled"] is False
    assert result["failsafe_eligible"] is False
    assert broker.mutation_calls == []


@pytest.mark.parametrize(
    ("terminal_status", "filled", "manual_suspected", "broker_stop_suspected"),
    [
        ("FILLED", 2.0, False, True),
        ("CANCELED", 0.0, True, False),
        ("ORDER_NOT_FOUND", 0.0, True, False),
    ],
)
def test_broker_flat_with_terminal_stop_becomes_central_only_reconciliation(
    terminal_status, filled, manual_suspected, broker_stop_suspected
):
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot(terminal_status, ok=terminal_status != "ORDER_NOT_FOUND", filled=filled),
    )
    if terminal_status == "ORDER_NOT_FOUND":
        broker.order_snapshot = {
            "ok": False,
            "status": terminal_status,
            "read_only": True,
            "sent": False,
        }
    position = _position()

    result = _verifier(broker)(position, now_epoch=1000.0, force=True, persist_registry=False)

    assert result["ok"] is True
    assert result["status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert result["central_only_reconcile_required"] is True
    assert result["management_allowed"] is False
    assert result["manual_user_close_suspected"] is manual_suspected
    assert result["broker_stop_execution_suspected"] is broker_stop_suspected
    assert position["central_only_evidence"]["matched_count"] == 0
    assert position["central_only_evidence"]["read_only"] is True
    assert position["central_only_evidence"]["sent"] is False
    assert broker.mutation_calls == []


def test_broker_flat_with_stop_still_active_is_blocked_not_terminal():
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot("OPEN"),
    )

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["ok"] is False
    assert result["status"] == "BROKER_FLAT_STOP_TERMINAL_STATE_UNCONFIRMED"
    assert result["central_only_reconcile_required"] is False
    assert result["management_allowed"] is False
    assert result["manual_intervention_required"] is True
    assert broker.mutation_calls == []


def test_triggered_is_not_treated_as_filled_or_as_flat_terminal_evidence():
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot("TRIGGERED", filled=0.0),
    )

    result = _verifier(broker)(_position(), now_epoch=1000.0, force=True, persist_registry=False)

    assert result["stop_order_triggered"] is True
    assert result["stop_order_filled"] is False
    assert result["status"] == "BROKER_FLAT_STOP_TERMINAL_STATE_UNCONFIRMED"
    assert result["central_only_reconcile_required"] is False
    assert broker.mutation_calls == []


def test_partial_terminal_stop_fill_never_becomes_reliable_full_fill_evidence():
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot("FILLED", amount=2.0, filled=0.5),
    )
    position = _position()

    result = _verifier(broker)(position, now_epoch=1000.0, force=True, persist_registry=False)

    assert result["central_only_reconcile_required"] is True
    assert result["stop_order_filled"] is True
    assert result["stop_order_full_fill_confirmed"] is False
    assert result["manual_user_close_suspected"] is True
    assert position["central_only_evidence"]["stop_order_full_fill_confirmed"] is False
    assert broker.mutation_calls == []


@pytest.mark.parametrize(
    "updates",
    [
        {"order_id": "OTHER-STOP"},
        {"type": "LIMIT"},
        {"side": "BUY"},
        {"filled": 0.5},
    ],
)
def test_stop_fill_requires_exact_protective_identity_and_complete_quantity(updates):
    order = _order_snapshot("FILLED", filled=2.0)
    order.update({"average": 1.79, **updates})
    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "_falcon_stop_status_flags",
            "_falcon_management_bool",
            "_falcon_protective_stop_evidence",
            "_falcon_confirmed_stop_fill_evidence",
        ),
        {
            "safe_float": _safe_float,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
        },
    )
    position = _position(entry_ownership_verified=True)

    evidence = namespace["_falcon_confirmed_stop_fill_evidence"](
        position,
        "PID-1",
        order,
        2.0,
    )

    assert evidence["confirmed"] is False


def test_stop_fill_can_close_lifecycle_only_with_exact_factual_evidence():
    order = _order_snapshot("FILLED", filled=2.0)
    order["average"] = 1.79
    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "_falcon_stop_status_flags",
            "_falcon_management_bool",
            "_falcon_protective_stop_evidence",
            "_falcon_confirmed_stop_fill_evidence",
        ),
        {
            "safe_float": _safe_float,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
        },
    )

    evidence = namespace["_falcon_confirmed_stop_fill_evidence"](
        _position(entry_ownership_verified=True),
        "PID-1",
        order,
        2.0,
    )

    assert evidence["confirmed"] is True
    assert evidence["actual_stop_order_id"] == "STOP-1"
    assert evidence["average"] == pytest.approx(1.79)


def _alert_namespace(redis_store: dict, health: dict):
    def redis_get_json(key, default=None):
        value = redis_store.get(key, default)
        return dict(value) if isinstance(value, dict) else value

    def redis_set_json(key, value):
        redis_store[key] = dict(value)
        return True

    return _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "falcon_position_identity_fingerprint",
            "_falcon_prune_timestamped_map",
            "_falcon_management_alert_fingerprint",
            "falcon_management_alert_decision",
            "falcon_clear_management_alert",
        ),
        {
            "safe_float": _safe_float,
            "time": real_time,
            "data_hora_sp_str": lambda: "15/07/2026 10:00:00",
            "redis_get_json": redis_get_json,
            "redis_set_json": redis_set_json,
            "FALCON_MANAGEMENT_ALERT_GUARD_KEY": "test:alerts",
            "FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS": 3600,
            "management_alert_guard_lock": threading.RLock(),
            "_management_alert_guard_memory": {},
            "HEALTH": health,
        },
    )


def test_management_spam_guard_persists_before_suppressing_and_clear_rearms():
    redis_store: dict = {}
    health: dict = {}
    namespace = _alert_namespace(redis_store, health)
    decide = namespace["falcon_management_alert_decision"]
    clear = namespace["falcon_clear_management_alert"]
    position = _position()

    first = decide(position, "CENTRAL_ONLY_RECONCILE_REQUIRED", now_epoch=1000.0, position_id="PID-1")
    repeated = decide(position, "CENTRAL_ONLY_RECONCILE_REQUIRED", now_epoch=1001.0, position_id="PID-1")

    assert first["send"] is True and first["persisted"] is True
    assert repeated["send"] is False and repeated["suppressed"] is True
    assert repeated["entry"]["attempt_count"] == 1
    assert repeated["entry"]["suppressed_count"] == 1
    assert health["falcon_management_spam_guard_status"] == "SUPPRESSED_COOLDOWN"
    assert clear(position, position_id="PID-1")["removed"] == 1

    rearmed = decide(position, "CENTRAL_ONLY_RECONCILE_REQUIRED", now_epoch=1002.0, position_id="PID-1")
    assert rearmed["send"] is True
    assert rearmed["entry"]["attempt_count"] == 1

    unsafe_first = decide(position, "TP50:MANAGED_CLOSE_POSITION_NOT_SAFE", now_epoch=1003.0, position_id="PID-1")
    unsafe_repeat = decide(position, "TP50:MANAGED_CLOSE_POSITION_NOT_SAFE", now_epoch=1004.0, position_id="PID-1")
    assert unsafe_first["send"] is True
    assert unsafe_repeat["send"] is False
    assert unsafe_repeat["entry"]["suppressed_count"] == 1


def _reconcile_namespace(positions: dict, redis_store: dict, saved: list, now_epoch: float):
    class _Clock:
        @staticmethod
        def time():
            return now_epoch

    def redis_get_json(key, default=None):
        value = redis_store.get(key, default)
        return dict(value) if isinstance(value, dict) else value

    def redis_set_json(key, value):
        redis_store[key] = dict(value)
        return True

    def save_positions(value):
        positions.clear()
        positions.update(value)
        saved.append(dict(value))
        return True

    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "falcon_position_identity_fingerprint",
            "falcon_position_tombstone_keys",
            "_falcon_prune_timestamped_map",
            "falcon_reconcile_remove_position",
        ),
        {
            "safe_float": _safe_float,
            "time": _Clock,
            "data_hora_sp_str": lambda: "15/07/2026 10:00:00",
            "redis_get_json": redis_get_json,
            "redis_set_json": redis_set_json,
            "get_positions": lambda: positions,
            "save_positions": save_positions,
            "falcon_clear_management_alert": lambda *_args, **_kwargs: {
                "ok": True,
                "removed": 1,
                "no_order_sent": True,
            },
            "falcon_refresh_management_safety_health": lambda value: {"count": len(value)},
            "FALCON_CENTRAL_ONLY_TOMBSTONES_KEY": "test:tombstones",
            "FALCON_CENTRAL_ONLY_EVIDENCE_MAX_AGE_SECONDS": 300,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "position_mutation_lock": threading.RLock(),
            "_central_only_tombstones_memory": {},
        },
    )
    return namespace["falcon_reconcile_remove_position"]


def _reconcilable_position(*, checked_epoch: float):
    return _position(
        central_only_reconcile_required=True,
        central_only_evidence={
            "broker_flat": True,
            "position_closed": True,
            "position_qty": 0.0,
            "matched_count": 0,
            "read_only": True,
            "sent": False,
            "checked_epoch": checked_epoch,
            "symbol": "XRPUSDT",
            "side": "LONG",
            "trade_id": "TRADE-1",
            "lifecycle_id": "LIFECYCLE-1",
            "order_id": "ORDER-1",
            "client_order_id": "CLIENT-1",
            "stop_order_status": "ORDER_NOT_FOUND",
            "stop_order_active": False,
        },
    )


def test_reconcile_remove_requires_exact_fresh_identity_and_persists_tombstone_first():
    positions = {"PID-1": _reconcilable_position(checked_epoch=990.0)}
    redis_store: dict = {}
    saved: list = []
    remove = _reconcile_namespace(positions, redis_store, saved, now_epoch=1000.0)

    mismatch = remove(order_id="OTHER", lifecycle_id="LIFECYCLE-1", trade_id="TRADE-1")
    assert mismatch["status"] == "POSITION_IDENTITY_CONFLICT"
    assert mismatch["ok"] is False
    assert "PID-1" in positions

    result = remove(
        position_id="PID-1",
        order_id="ORDER-1",
        client_order_id="CLIENT-1",
        lifecycle_id="LIFECYCLE-1",
        trade_id="TRADE-1",
    )

    assert result["ok"] is True
    assert result["status"] == "CENTRAL_ONLY_POSITION_REMOVED"
    assert result["removed"] is True
    assert positions == {}
    assert saved == [{}]
    tombstones = redis_store["test:tombstones"]
    assert "ORDER|ORDER-1" in tombstones
    assert "CLIENT|CLIENT-1" in tombstones
    assert "LIFECYCLE|LIFECYCLE-1" in tombstones
    assert all(item["reason"] == "CENTRAL_ONLY_BROKER_FLAT_RECONCILED" for item in tombstones.values())
    assert result["no_order_sent"] is True


def test_reconcile_remove_rejects_stale_flat_evidence_without_removing_position():
    positions = {"PID-1": _reconcilable_position(checked_epoch=600.0)}
    redis_store: dict = {}
    saved: list = []
    remove = _reconcile_namespace(positions, redis_store, saved, now_epoch=1000.0)

    result = remove(order_id="ORDER-1", lifecycle_id="LIFECYCLE-1", trade_id="TRADE-1")

    assert result["ok"] is False
    assert result["status"] == "POSITION_NOT_RECONCILABLE"
    assert result["removed"] is False
    assert "PID-1" in positions
    assert saved == []
    assert "test:tombstones" not in redis_store


def test_reconcile_remove_rejects_reused_position_id_with_different_requested_key():
    positions = {"PID-NEW": _reconcilable_position(checked_epoch=990.0)}
    redis_store: dict = {}
    saved: list = []
    remove = _reconcile_namespace(positions, redis_store, saved, now_epoch=1000.0)

    result = remove(
        position_id="PID-OLD",
        order_id="ORDER-1",
        client_order_id="CLIENT-1",
        lifecycle_id="LIFECYCLE-1",
        trade_id="TRADE-1",
    )

    assert result["ok"] is False
    assert result["status"] == "POSITION_IDENTITY_CONFLICT"
    assert result["conflicts"] == [{"position_id": "PID-NEW", "fields": ["position_id"]}]
    assert "PID-NEW" in positions
    assert saved == []


def test_reconciliation_tombstone_blocks_stale_save_but_allows_same_day_reentry_with_new_ids():
    old_position = _position(
        lifecycle_id="LIFECYCLE-OLD",
        live_order_id="ORDER-OLD",
        live_client_order_id="CLIENT-OLD",
    )
    new_position = _position(
        lifecycle_id="LIFECYCLE-NEW",
        live_order_id="ORDER-NEW",
        live_client_order_id="CLIENT-NEW",
    )
    tombstones = {
        "LIFECYCLE|LIFECYCLE-OLD": {"updated_epoch": 1000.0},
        "ORDER|ORDER-OLD": {"updated_epoch": 1000.0},
        "CLIENT|CLIENT-OLD": {"updated_epoch": 1000.0},
    }
    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "falcon_position_tombstone_keys",
            "_falcon_prune_timestamped_map",
            "falcon_filter_reconciled_positions",
        ),
        {
            "safe_float": _safe_float,
            "time": SimpleNamespace(time=lambda: 1001.0),
            "redis_get_json": lambda _key, _default=None: dict(tombstones),
            "FALCON_CENTRAL_ONLY_TOMBSTONES_KEY": "test:tombstones",
            "_central_only_tombstones_memory": {},
        },
    )
    filter_positions = namespace["falcon_filter_reconciled_positions"]

    assert filter_positions({"FALCON15:XRPUSDT:LONG:2026-07-15": old_position}) == {}
    assert filter_positions({"FALCON15:XRPUSDT:LONG:2026-07-15": new_position}) == {
        "FALCON15:XRPUSDT:LONG:2026-07-15": new_position
    }


def test_broker_order_snapshot_exposes_protective_evidence_read_only():
    calls: list[tuple] = []

    class Exchange:
        def fetch_order(self, order_id, symbol):
            calls.append(("fetch_order", order_id, symbol))
            return {
                "id": order_id,
                "status": "open",
                "type": "stop_market",
                "side": "sell",
                "amount": 2.0,
                "filled": 0.0,
                "remaining": 2.0,
                "datetime": "2026-07-15T10:00:00Z",
                "stopPrice": 1.8,
                "info": {
                    "clientOrderId": "STOP-CLIENT-1",
                    "workingType": "MARK_PRICE",
                    "positionSide": "LONG",
                    "reduceOnly": False,
                    "closePosition": False,
                },
            }

    snapshot = _load_broker_function(
        "managed_order_snapshot",
        {
            "exchange": lambda: Exchange(),
            "normalize_symbol": lambda value: str(value),
            "_cq_patch_safe_float": _safe_float,
            "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "ccxt": SimpleNamespace(OrderNotFound=type("OrderNotFound", (Exception,), {})),
        },
    )("XRPUSDT", "STOP-1")

    assert calls == [("fetch_order", "STOP-1", "XRPUSDT")]
    assert snapshot["ok"] is True and snapshot["read_only"] is True and snapshot["sent"] is False
    assert snapshot["order_id"] == "STOP-1"
    assert snapshot["requested_order_id"] == "STOP-1"
    assert snapshot["type"] == "STOP_MARKET"
    assert snapshot["working_type"] == "MARK_PRICE"
    assert snapshot["side"] == "SELL"
    assert snapshot["position_side"] == "LONG"
    assert snapshot["reduce_only"] is False
    assert snapshot["close_position"] is False
    assert snapshot["amount"] == pytest.approx(2.0)
    assert snapshot["timestamp"] == "2026-07-15T10:00:00Z"


def test_broker_order_snapshot_normalizes_structured_order_not_found():
    class OrderNotFound(Exception):
        pass

    class Exchange:
        def fetch_order(self, _order_id, _symbol):
            raise OrderNotFound("missing")

    snapshot = _load_broker_function(
        "managed_order_snapshot",
        {
            "exchange": lambda: Exchange(),
            "normalize_symbol": lambda value: str(value),
            "_cq_patch_safe_float": _safe_float,
            "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST",
            "ccxt": SimpleNamespace(OrderNotFound=OrderNotFound),
        },
    )("XRPUSDT", "STOP-404")

    assert snapshot["ok"] is False
    assert snapshot["status"] == "ORDER_NOT_FOUND"
    assert snapshot["error_type"] == "OrderNotFound"
    assert snapshot["read_only"] is True and snapshot["sent"] is False


class _StopLoop(BaseException):
    pass


class _SingleCycleClock:
    @staticmethod
    def time():
        return 1000.0

    @staticmethod
    def sleep(_seconds):
        raise _StopLoop


class _TwoCycleClock:
    sleep_calls = 0

    @classmethod
    def time(cls):
        return 1000.0 + cls.sleep_calls

    @classmethod
    def sleep(cls, _seconds):
        cls.sleep_calls += 1
        if cls.sleep_calls >= 2:
            raise _StopLoop


def test_management_loop_central_only_preflight_skips_all_normal_management_and_mutations():
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot("CANCELED", filled=0.0),
    )
    positions = {"PID-1": _position()}
    saved: list[dict] = []
    forbidden_calls: list[str] = []

    def forbidden(name):
        def fail(*_args, **_kwargs):
            forbidden_calls.append(name)
            raise AssertionError(f"normal management reached: {name}")

        return fail

    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "_falcon_stop_status_flags",
            "_falcon_management_bool",
            "_falcon_protective_stop_evidence",
            "_falcon_stop_not_found_evidence",
            "_falcon_update_stop_health",
            "falcon_verify_live_disaster_stop",
            "management_loop",
        ),
        {
            "safe_float": _safe_float,
            "time": _SingleCycleClock,
            "data_hora_sp_str": lambda: "15/07/2026 10:00:00",
            "central_broker": broker,
            "HEALTH": {},
            "get_positions": lambda: positions,
            "save_positions": lambda value: saved.append(dict(value)) or True,
            "falcon_is_live_real_position": lambda _pos: True,
            "falcon_real_remaining_qty": lambda pos: _safe_float(pos.get("remaining_qty")),
            "falcon_update_registry_management": lambda *_args, **_kwargs: {"ok": True},
            "falcon_management_alert_decision": lambda *_args, **_kwargs: {
                "send": False,
                "suppressed": True,
            },
            "record_event": forbidden("record_event"),
            "safe_send_telegram": forbidden("telegram"),
            "safe_fetch_price": forbidden("price"),
            "update_mfe_mae": forbidden("mfe_mae"),
            "falcon_handle_live_stop_cross": forbidden("stop_close"),
            "close_position": forbidden("close"),
            "falcon_try_execute_tp50_real_partial": forbidden("tp50"),
            "falcon_apply_live_stop_update": forbidden("break_even_or_trailing"),
            "calc_chandelier_stop": forbidden("trailing"),
            "falcon_refresh_management_safety_health": lambda value: {"count": len(value)},
            "refresh_health_stats": lambda: None,
            "FALCON_STOP_VERIFY_INTERVAL_SECONDS": 15,
            "FALCON_STOP_VERIFY_PERSIST_SECONDS": 60,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "MANAGEMENT_SLEEP_SECONDS": 1,
        },
    )

    with pytest.raises(_StopLoop):
        namespace["management_loop"]()

    assert forbidden_calls == []
    assert len(saved) == 1
    assert positions["PID-1"]["central_only_reconcile_required"] is True
    assert positions["PID-1"]["live_management_block_reason"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert [call[0] for call in broker.read_calls] == ["position", "order", "order"]
    assert broker.mutation_calls == []


def test_two_management_cycles_emit_one_central_only_alert_and_never_tp50_spam():
    _TwoCycleClock.sleep_calls = 0
    broker = _ReadOnlyBroker(
        _position_snapshot(amount=0.0, closed=True, matched_count=0),
        _order_snapshot("CANCELED", filled=0.0),
    )
    positions = {"PID-1": _position()}
    redis_store: dict = {}
    telegram: list[tuple[str, dict]] = []
    events: list[str] = []
    forbidden_calls: list[str] = []

    def redis_get_json(key, default=None):
        value = redis_store.get(key, default)
        return dict(value) if isinstance(value, dict) else value

    def redis_set_json(key, value):
        redis_store[key] = dict(value)
        return True

    def forbidden(name):
        def fail(*_args, **_kwargs):
            forbidden_calls.append(name)
            raise AssertionError(f"normal management reached: {name}")

        return fail

    namespace = _load_functions(
        (
            "_falcon_management_norm_symbol",
            "_falcon_management_norm_side",
            "falcon_position_identity",
            "falcon_position_identity_fingerprint",
            "_falcon_prune_timestamped_map",
            "_falcon_management_alert_fingerprint",
            "falcon_management_alert_decision",
            "_falcon_stop_status_flags",
            "_falcon_management_bool",
            "_falcon_protective_stop_evidence",
            "_falcon_stop_not_found_evidence",
            "_falcon_update_stop_health",
            "falcon_verify_live_disaster_stop",
            "management_loop",
        ),
        {
            "safe_float": _safe_float,
            "time": _TwoCycleClock,
            "data_hora_sp_str": lambda: "15/07/2026 10:00:00",
            "central_broker": broker,
            "HEALTH": {},
            "get_positions": lambda: positions,
            "save_positions": lambda _value: True,
            "redis_get_json": redis_get_json,
            "redis_set_json": redis_set_json,
            "management_alert_guard_lock": threading.RLock(),
            "_management_alert_guard_memory": {},
            "FALCON_MANAGEMENT_ALERT_GUARD_KEY": "test:alerts",
            "FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS": 3600,
            "falcon_is_live_real_position": lambda _pos: True,
            "falcon_real_remaining_qty": lambda pos: _safe_float(pos.get("remaining_qty")),
            "falcon_update_registry_management": lambda *_args, **_kwargs: {"ok": True},
            "record_event": lambda event_type, *_args, **_kwargs: events.append(event_type),
            "safe_send_telegram": lambda message, **kwargs: telegram.append((message, kwargs)),
            "safe_fetch_price": forbidden("price"),
            "update_mfe_mae": forbidden("mfe_mae"),
            "falcon_handle_live_stop_cross": forbidden("stop_close"),
            "close_position": forbidden("close"),
            "falcon_try_execute_tp50_real_partial": forbidden("tp50"),
            "falcon_apply_live_stop_update": forbidden("break_even_or_trailing"),
            "calc_chandelier_stop": forbidden("trailing"),
            "falcon_refresh_management_safety_health": lambda value: {"count": len(value)},
            "refresh_health_stats": lambda: None,
            "FALCON_STOP_VERIFY_INTERVAL_SECONDS": 15,
            "FALCON_STOP_VERIFY_PERSIST_SECONDS": 60,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "MANAGEMENT_SLEEP_SECONDS": 1,
        },
    )

    with pytest.raises(_StopLoop):
        namespace["management_loop"]()

    assert forbidden_calls == []
    assert events == ["FALCON_CENTRAL_ONLY_RECONCILE_REQUIRED"]
    assert len(telegram) == 1
    assert "FALCON CENTRAL-ONLY RECONCILE REQUIRED" in telegram[0][0]
    assert "TP50 REAL" not in telegram[0][0]
    assert "MANAGED_CLOSE_POSITION_NOT_SAFE" not in telegram[0][0]
    guard = redis_store["test:alerts"]
    assert len(guard) == 1
    assert next(iter(guard.values()))["suppressed_count"] == 1
    assert broker.mutation_calls == []
