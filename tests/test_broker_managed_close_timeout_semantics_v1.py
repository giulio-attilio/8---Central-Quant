from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_EMERGENCY_CLOSE_ID = "FEC1-0123456789abcdef01234567"
CANONICAL_MANAGED_CLOSE_ID = "FMC1-89abcdef0123456789abcdef"


def _reservation(
    client_order_id,
    *,
    attempt_id=None,
    role="MANAGED_CLOSE",
    order_type="MARKET",
    symbol="SOLUSDT",
    side="LONG",
    lifecycle_id="CENTRAL-FALCON-LIFECYCLE:TEST-SOL-LONG",
):
    normalized = str(client_order_id).strip().upper()
    attempt = attempt_id or f"ATTEMPT:{normalized}"
    return {
        "ok": True,
        "send_allowed": True,
        "status": "RESERVED_UNIQUE",
        "reservation_status": "RESERVED_UNIQUE",
        "reservation_state": "RESERVED_PRE_SEND",
        "persistent": True,
        "client_order_id": normalized,
        "client_order_id_reserved": True,
        "client_order_id_unique": True,
        "canonical_operation_id": f"OPERATION:{normalized}",
        "attempt_id": attempt,
        "attempt_sequence": 0,
        "attempt_identity_hash": f"HASH:{attempt}",
        "bot": "FALCON",
        "role": role,
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "side": side,
        "entry_client_order_id": "ENTRY-TEST-SOL-LONG",
        "entry_order_id": "ORDER-TEST-SOL-LONG",
        "stop_revision": 1,
        "order_type": order_type,
    }


def _fake_account_authority():
    claimed = set()

    def verify(reservation, *, expected_client_order_id):
        receipt = dict(reservation or {})
        normalized = str(expected_client_order_id).strip().upper()
        identity = (
            receipt.get("canonical_operation_id"),
            receipt.get("attempt_id"),
        )
        valid = bool(
            receipt.get("status") == "RESERVED_UNIQUE"
            and receipt.get("persistent") is True
            and receipt.get("client_order_id_reserved") is True
            and receipt.get("client_order_id_unique") is True
            and str(receipt.get("client_order_id") or "").upper() == normalized
            and all(identity)
            and receipt.get("attempt_identity_hash")
            and identity not in claimed
        )
        return {
            "ok": valid,
            "send_allowed": valid,
            "status": "RESERVED_UNIQUE"
            if valid
            else "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
            if identity in claimed
            else "CLIENT_ORDER_ID_RESERVATION_RECEIPT_INVALID",
            "persistent": bool(receipt),
            "client_order_id": normalized,
            "client_order_id_reserved": valid,
            "client_order_id_unique": valid,
            "canonical_operation_id": receipt.get("canonical_operation_id"),
            "attempt_id": receipt.get("attempt_id"),
            "attempt_sequence": receipt.get("attempt_sequence"),
            "attempt_identity_hash": receipt.get("attempt_identity_hash"),
            "bot": receipt.get("bot"),
            "role": receipt.get("role"),
            "lifecycle_id": receipt.get("lifecycle_id"),
            "symbol": receipt.get("symbol"),
            "side": receipt.get("side"),
            "entry_client_order_id": receipt.get("entry_client_order_id"),
            "entry_order_id": receipt.get("entry_order_id"),
            "stop_revision": receipt.get("stop_revision"),
            "order_type": receipt.get("order_type"),
        }

    def claim(reservation, *, expected_client_order_id):
        verified = verify(
            reservation, expected_client_order_id=expected_client_order_id
        )
        if not verified.get("ok"):
            return {
                **verified,
                "send_claimed": bool(
                    verified.get("status")
                    == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
                ),
                "reconciliation_required": True,
            }
        identity = (
            verified["canonical_operation_id"], verified["attempt_id"]
        )
        claimed.add(identity)
        return {
            **verified,
            "ok": True,
            "send_allowed": True,
            "send_claimed": True,
            "status": "SEND_CLAIMED",
            "attempt_disposition": "SEND_CLAIMED",
            "persistent": True,
        }

    return verify, claim


class FakeExchange:
    def __init__(self, *, response=None, error=None):
        self.response = response
        self.error = error
        self.create_calls = []

    def create_order(self, *args):
        self.create_calls.append(args)
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.response)


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_managed_close(
    *,
    snapshots,
    fake_exchange,
    live=True,
    auth_ok=True,
    precision_error=None,
    exchange_error=None,
    position_side_error=None,
    hedge_error=None,
    outcome_persistence_ok=True,
):
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    names = {
        "_managed_sanitize_exception_text",
        "_managed_exception_details",
        "validate_broker_client_order_id",
        "_broker_account_reservation_verification",
        "_broker_account_order_context",
        "_broker_returned_client_order_id",
        "_create_order_with_reserved_attempt",
        "managed_close_position_market",
    }
    nodes = [
        copy.deepcopy(item)
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    assert {item.name for item in nodes} == names
    node = next(
        item
        for item in nodes
        if item.name == "managed_close_position_market"
    )
    isolated = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(isolated)

    snapshot_results = [copy.deepcopy(item) for item in snapshots]
    snapshot_calls = []
    execution_events = []
    audit_events = []

    def managed_position_snapshot(symbol, side, expected_amount=None):
        snapshot_calls.append((symbol, side, expected_amount))
        if not snapshot_results:
            raise AssertionError("unexpected managed_position_snapshot call")
        result = snapshot_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def amount_to_precision(_exchange, _symbol, amount):
        if precision_error is not None:
            raise precision_error
        return float(amount)

    def get_exchange():
        if exchange_error is not None:
            raise exchange_error
        return fake_exchange

    def get_position_side(side):
        if position_side_error is not None:
            raise position_side_error
        return str(side).upper()

    def hedge_mode_detected():
        if hedge_error is not None:
            raise hedge_error
        return True

    verify_reservation, claim_send = _fake_account_authority()

    def record_attempt_outcome(reservation, *, outcome_state, **_details):
        return {
            "ok": outcome_persistence_ok,
            "status": (
                outcome_state
                if outcome_persistence_ok
                else "ATTEMPT_OUTCOME_PERSISTENCE_ERROR"
            ),
            "client_order_id": (reservation or {}).get("client_order_id"),
            "persistent": outcome_persistence_ok,
            "id_released": False,
        }

    namespace = {
        "normalize_symbol": lambda value: str(value),
        "_rpm_norm_side": lambda value: str(value).upper(),
        "_cq_patch_safe_float": _safe_float,
        "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST-V1",
        "BROKER_CLIENT_ORDER_ID_MAX_LENGTH": 32,
        "_BROKER_CLIENT_ORDER_ID_PATTERN": re.compile(r"^[A-Za-z0-9_-]{1,32}$"),
        "normalize_account_client_order_id": lambda value: str(value).strip().upper(),
        "verify_account_client_order_id_reservation": verify_reservation,
        "claim_account_client_order_send_authorization": claim_send,
        "record_account_client_order_attempt_outcome": record_attempt_outcome,
        "ROLE_ENTRY": "ENTRY",
        "ROLE_TP50_CLOSE": "TP50_CLOSE",
        "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE": (
            "EMERGENCY_TERMINAL_STOP_CLOSE"
        ),
        "ROLE_MANAGED_CLOSE": "MANAGED_CLOSE",
        "managed_position_snapshot": managed_position_snapshot,
        "BROKER_MANAGEMENT_AMOUNT_TOLERANCE": 1e-10,
        "_rpm_live_write_enabled": lambda: live,
        "_rpm_validate_auth": lambda token, context: {
            "ok": auth_ok,
            "token": token,
            "context": context,
        },
        "exchange": get_exchange,
        "bingx_position_side": get_position_side,
        "_disaster_stop_hedge_mode_detected": hedge_mode_detected,
        "re": re,
        "time": SimpleNamespace(perf_counter=lambda: 1.0, sleep=lambda _seconds: None),
        "_rpm_amount_to_precision": amount_to_precision,
        "BROKER_MANAGEMENT_CONFIRM_RETRIES": 1,
        "BROKER_MANAGEMENT_CONFIRM_DELAY_SECONDS": 0,
        "log_execution_event": lambda event: execution_events.append(copy.deepcopy(event)) or True,
        "log_execution_audit_event": lambda event: audit_events.append(copy.deepcopy(event)) or True,
    }
    exec(compile(isolated, "<isolated-managed-close>", "exec"), namespace)
    return (
        namespace["managed_close_position_market"],
        snapshot_calls,
        execution_events,
        audit_events,
    )


def _load_stop_replacement(*, fake_exchange, snapshots):
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    names = {
        "_managed_sanitize_exception_text",
        "_managed_exception_details",
        "validate_broker_client_order_id",
        "_broker_account_reservation_verification",
        "_broker_account_order_context",
        "_broker_returned_client_order_id",
        "_broker_material_disaster_stop_confirmation",
        "_create_order_with_reserved_attempt",
        "_rpm_create_stop_live",
        "_rpm_stop_create_confirmation",
        "replace_position_stop_order",
    }
    nodes = [
        copy.deepcopy(item)
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    assert {item.name for item in nodes} == names
    snapshot_results = [copy.deepcopy(item) for item in snapshots]
    audit_events = []

    def managed_position_snapshot(*_args, **_kwargs):
        assert snapshot_results
        return snapshot_results.pop(0)

    verify_reservation, claim_send = _fake_account_authority()
    namespace = {
        "normalize_symbol": lambda value: str(value),
        "_rpm_norm_side": lambda value: str(value).upper(),
        "_cq_patch_safe_float": _safe_float,
        "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST-V1",
        "BROKER_CLIENT_ORDER_ID_MAX_LENGTH": 32,
        "_BROKER_CLIENT_ORDER_ID_PATTERN": re.compile(r"^[A-Za-z0-9_-]{1,32}$"),
        "normalize_account_client_order_id": lambda value: str(value).strip().upper(),
        "verify_account_client_order_id_reservation": verify_reservation,
        "claim_account_client_order_send_authorization": claim_send,
        "record_account_client_order_attempt_outcome": (
            lambda reservation, *, outcome_state, **_details: {
                "ok": True,
                "status": outcome_state,
                "client_order_id": (reservation or {}).get("client_order_id"),
                "persistent": True,
                "id_released": False,
            }
        ),
        "ROLE_ENTRY": "ENTRY",
        "ROLE_REPLACEMENT_STOP": "REPLACEMENT_STOP",
        "ROLE_ROLLBACK_STOP": "ROLLBACK_STOP",
        "ROLE_BREAK_EVEN_STOP": "BREAK_EVEN_STOP",
        "ROLE_TRAILING_STOP": "TRAILING_STOP",
        "BROKER_MANAGEMENT_AMOUNT_TOLERANCE": 1e-10,
        "managed_position_snapshot": managed_position_snapshot,
        "fetch_last_price": lambda _symbol: 80.0,
        "_rpm_live_write_enabled": lambda: True,
        "_rpm_validate_auth": lambda *_args, **_kwargs: {"ok": True},
        "exchange": lambda: fake_exchange,
        "bingx_position_side": lambda side: str(side).upper(),
        "_disaster_stop_hedge_mode_detected": lambda: True,
        "DISASTER_STOP_WORKING_TYPE": "MARK_PRICE",
        "_rpm_amount_to_precision": lambda _exchange, _symbol, amount: float(amount),
        "re": re,
        "time": SimpleNamespace(perf_counter=lambda: 1.0),
        "log_execution_event": lambda event: True,
        "log_execution_audit_event": lambda event: audit_events.append(copy.deepcopy(event)) or True,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<isolated-stop-replacement>", "exec"), namespace)
    return namespace["replace_position_stop_order"], audit_events


def _load_order_normalizer():
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_normalize_managed_order_payload"
    )
    namespace = {"_cq_patch_safe_float": _safe_float}
    exec(
        compile(ast.Module(body=[copy.deepcopy(node)], type_ignores=[]), "<managed-order-normalizer>", "exec"),
        namespace,
    )
    return namespace["_normalize_managed_order_payload"]


def _load_historical_order_snapshot(fetch_result=None, *, fetch_error=None):
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    names = {
        "_managed_sanitize_exception_text",
        "_managed_exception_details",
        "_normalize_managed_order_payload",
        "managed_historical_order_snapshot",
    }
    nodes = [
        copy.deepcopy(item)
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    def fetch_order_by_id(_symbol, order_id=None):
        if fetch_error is not None:
            raise fetch_error
        return copy.deepcopy(fetch_result)

    namespace = {
        "_cq_patch_safe_float": _safe_float,
        "normalize_symbol": lambda value: str(value),
        "fetch_order_by_id": fetch_order_by_id,
        "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST-V1",
        "re": re,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<historical-order-snapshot>", "exec"), namespace)
    return namespace["managed_historical_order_snapshot"]


def _load_open_orders_snapshot(*, orders=None, fetch_error=None):
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    names = {
        "_managed_sanitize_exception_text",
        "_managed_exception_details",
        "_managed_sanitize_snapshot_value",
        "_managed_symbol_identity",
        "_normalize_managed_order_payload",
        "managed_open_orders_snapshot",
    }
    nodes = [
        copy.deepcopy(item)
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    assert {item.name for item in nodes} == names
    calls = []

    class ReadOnlyExchange:
        def fetch_open_orders(self, symbol):
            calls.append(symbol)
            if fetch_error is not None:
                raise fetch_error
            return copy.deepcopy(orders)

        def __getattr__(self, name):
            if name in {"create_order", "cancel_order", "edit_order"}:
                raise AssertionError(f"mutating broker method accessed: {name}")
            raise AttributeError(name)

    def normalize_symbol(value):
        text = str(value or "").upper().strip()
        if text and "/" not in text and text.endswith("USDT"):
            return f"{text[:-4]}/USDT:USDT"
        return text

    namespace = {
        "_cq_patch_safe_float": _safe_float,
        "normalize_symbol": normalize_symbol,
        "exchange": lambda: ReadOnlyExchange(),
        "REAL_POSITION_MANAGEMENT_HARDENING_VERSION": "TEST-V1",
        "re": re,
    }
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<managed-open-orders-snapshot>", "exec"), namespace)
    return namespace["managed_open_orders_snapshot"], calls


def _safe_open_snapshot(amount=0.13):
    return {
        "ok": True,
        "position_closed": False,
        "ownership_safe": True,
        "amount": amount,
        "status": "POSITION_MATCHED",
    }


def test_replacement_create_timeout_never_blindly_creates_rollback_stop():
    exchange_probe = FakeExchange(error=TimeoutError("create timeout"))
    exchange_probe.has = {"editOrder": False}
    exchange_probe.cancel_order = lambda *_args: {
        "ok": True,
        "id": "STOP-OLD",
        "status": "CANCELED",
    }
    replace, audit_events = _load_stop_replacement(
        fake_exchange=exchange_probe,
        snapshots=[_safe_open_snapshot(), _safe_open_snapshot()],
    )

    result = replace(
        symbol="SOLUSDT",
        side="LONG",
        old_order_id="STOP-OLD",
        old_stop_price=75.0,
        new_stop_price=76.0,
        amount=0.13,
        expected_position_amount=0.13,
        client_tag="FRS1-0123456789ABCDEF01234567",
        rollback_client_tag="FRS1-89ABCDEF0123456789ABCDEF",
        client_order_id_unique=True,
        rollback_client_order_id_unique=True,
        client_order_id_reservation=_reservation(
            "FRS1-0123456789ABCDEF01234567",
            role="REPLACEMENT_STOP",
            order_type="STOP_MARKET",
        ),
        rollback_client_order_id_reservation=_reservation(
            "FRS1-89ABCDEF0123456789ABCDEF",
            role="ROLLBACK_STOP",
            order_type="STOP_MARKET",
        ),
        execution_auth_token="test-only",
    )

    assert result["status"] == "STOP_REPLACE_CREATE_OUTCOME_UNKNOWN"
    assert result["sent"] is None
    assert result["send_outcome_unknown"] is True
    assert result["rollback_attempted"] is False
    assert result["rollback"] is None
    assert len(exchange_probe.create_calls) == 1
    assert audit_events[-1]["event"] == "BROKER_STOP_REPLACE_OUTCOME_UNKNOWN"


def _replace_call(replace, **updates):
    parameters = {
        "symbol": "SOLUSDT",
        "side": "LONG",
        "old_order_id": "STOP-OLD",
        "old_stop_price": 75.0,
        "new_stop_price": 76.0,
        "amount": 0.13,
        "expected_position_amount": 0.13,
        "client_tag": "FRS1-0123456789ABCDEF01234567",
        "rollback_client_tag": "FRS1-89ABCDEF0123456789ABCDEF",
        "client_order_id_unique": True,
        "rollback_client_order_id_unique": True,
        "client_order_id_reservation": _reservation(
            "FRS1-0123456789ABCDEF01234567",
            role="REPLACEMENT_STOP",
            order_type="STOP_MARKET",
        ),
        "rollback_client_order_id_reservation": _reservation(
            "FRS1-89ABCDEF0123456789ABCDEF",
            role="ROLLBACK_STOP",
            order_type="STOP_MARKET",
        ),
        "execution_auth_token": "test-only",
    }
    parameters.update(updates)
    return replace(**parameters)


def _replacement_response(**updates):
    payload = {
        "id": "STOP-NEW",
        "status": "OPEN",
        "clientOrderId": "FRS1-0123456789ABCDEF01234567",
        "symbol": "SOLUSDT",
        "side": "sell",
        "positionSide": "LONG",
        "type": "stop_market",
        "amount": 0.13,
        "stopPrice": 76.0,
    }
    payload.update(updates)
    return payload


def test_replacement_blocks_before_create_when_cancel_is_not_factually_terminal():
    exchange_probe = FakeExchange(response=_replacement_response())
    exchange_probe.cancel_order = lambda *_args: {"id": "STOP-OLD", "status": "OPEN"}
    replace, audit_events = _load_stop_replacement(
        fake_exchange=exchange_probe,
        snapshots=[_safe_open_snapshot()],
    )

    result = _replace_call(replace)

    assert result["status"] == "STOP_REPLACE_CANCEL_UNCONFIRMED"
    assert result["send_attempted"] is False
    assert exchange_probe.create_calls == []
    assert audit_events[-1]["event"] == "BROKER_STOP_REPLACE_CANCEL_UNCONFIRMED"


def test_replacement_requires_materially_armed_returned_stop():
    exchange_probe = FakeExchange(
        response=_replacement_response(info={"status": "FAILED"})
    )
    exchange_probe.cancel_order = lambda *_args: {
        "id": "STOP-OLD",
        "status": "CANCELED",
    }
    replace, audit_events = _load_stop_replacement(
        fake_exchange=exchange_probe,
        snapshots=[_safe_open_snapshot(), _safe_open_snapshot()],
    )

    result = _replace_call(replace)

    assert result["status"] == "STOP_REPLACE_CREATED_NOT_ARMED"
    assert result["sent"] is True
    assert result["confirmed"] is False
    assert result["reconciliation_required"] is True
    assert result["rollback_attempted"] is False
    assert len(exchange_probe.create_calls) == 1
    assert audit_events[-1]["event"] == "BROKER_STOP_REPLACE_NOT_ARMED"


def test_replacement_post_return_error_never_creates_rollback_order():
    exchange_probe = FakeExchange(response=_replacement_response())
    exchange_probe.cancel_order = lambda *_args: {
        "id": "STOP-OLD",
        "status": "CANCELED",
    }
    replace, _ = _load_stop_replacement(
        fake_exchange=exchange_probe,
        snapshots=[_safe_open_snapshot(), _safe_open_snapshot()],
    )
    replace.__globals__["_rpm_stop_create_confirmation"] = (
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("post return diagnostic error")
        )
    )

    result = _replace_call(replace)

    assert result["status"] == "STOP_REPLACE_CREATED_CONFIRMATION_ERROR"
    assert result["sent"] is True
    assert result["confirmed"] is None
    assert result["rollback_attempted"] is False
    assert len(exchange_probe.create_calls) == 1


def test_replacement_and_rollback_ids_must_be_distinct_before_any_mutation():
    exchange_probe = FakeExchange(response=_replacement_response())
    exchange_probe.cancel_order = lambda *_args: pytest.fail("cancel must not run")
    replace, _ = _load_stop_replacement(
        fake_exchange=exchange_probe,
        snapshots=[],
    )
    same_id = "FRS1-0123456789ABCDEF01234567"

    result = _replace_call(
        replace,
        rollback_client_tag=same_id,
        rollback_client_order_id_reservation=_reservation(
            same_id,
            role="ROLLBACK_STOP",
            order_type="STOP_MARKET",
        ),
    )

    assert result["status"] == "STOP_REPLACE_CLIENT_ORDER_ID_COLLISION"
    assert result["send_attempted"] is False
    assert exchange_probe.create_calls == []


def test_create_timeout_is_inconclusive_and_preserves_client_identity():
    exchange = FakeExchange(error=TimeoutError("response lost"))
    close, snapshot_calls, execution_events, audit_events = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=exchange,
    )
    client_tag = CANONICAL_EMERGENCY_CLOSE_ID

    result = close(
        "SOL/USDT:USDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        reason="STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN",
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    assert result["status"] == "MANAGED_CLOSE_ERROR"
    assert result["sent"] is None
    assert result["confirmed"] is None
    assert result["send_attempted"] is True
    assert result["send_outcome_unknown"] is True
    assert (
        result["phase"]
        == result["failure_phase"]
        == "CREATE_ORDER_OUTCOME_UNKNOWN"
    )
    assert result["error_type"] == "TimeoutError"
    assert result["remaining_amount"] is None
    assert result["client_tag"] == client_tag
    assert result["client_order_id"] == client_tag.upper()
    assert result["attempt_outcome_persistence_ok"] is True
    assert result["attempt_outcome_persistence"]["persistent"] is True
    assert result["reconciliation_required"] is True
    assert snapshot_calls == [("SOL/USDT:USDT", "LONG", 0.13)]
    assert len(exchange.create_calls) == 1
    assert exchange.create_calls[0][-1]["clientOrderId"] == client_tag.upper()
    assert execution_events[-1]["sent"] is None
    assert audit_events[-1]["send_outcome_unknown"] is True

    retry = close(
        "SOL/USDT:USDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        reason="STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN",
        execution_auth_token="TOKEN",
        client_order_id_unique=False,
        client_order_id_reservation=_reservation(client_tag),
    )

    assert retry["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert retry["sent"] is False
    assert retry["send_attempted"] is False
    assert len(exchange.create_calls) == 1


def test_missing_client_order_id_uniqueness_blocks_before_snapshot_or_send():
    exchange = FakeExchange(response={"id": "MUST-NOT-BE-CREATED"})
    close, snapshot_calls, execution_events, audit_events = _load_managed_close(
        snapshots=[],
        fake_exchange=exchange,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_EMERGENCY_CLOSE_ID,
        execution_auth_token="TOKEN",
    )

    assert result["status"] == "CLIENT_ORDER_ID_RESERVATION_RECEIPT_INVALID"
    assert result["sent"] is False
    assert result["confirmed"] is False
    assert result["send_attempted"] is False
    assert result["send_outcome_unknown"] is False
    assert snapshot_calls == []
    assert exchange.create_calls == []
    assert execution_events == []
    assert audit_events == []


def test_pre_send_gates_remain_definitively_not_sent():
    client_tag = CANONICAL_MANAGED_CLOSE_ID

    invalid_exchange = FakeExchange(response={"id": "UNEXPECTED"})
    invalid, _, _, _ = _load_managed_close(
        snapshots=[],
        fake_exchange=invalid_exchange,
    )
    invalid_result = invalid(
        "SOLUSDT",
        "LONG",
        0,
        client_tag=client_tag,
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    unsafe_exchange = FakeExchange(response={"id": "UNEXPECTED"})
    unsafe, _, _, _ = _load_managed_close(
        snapshots=[
            {
                "ok": True,
                "position_closed": False,
                "ownership_safe": False,
                "amount": 0.25,
            }
        ],
        fake_exchange=unsafe_exchange,
    )
    unsafe_result = unsafe(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    dry_exchange = FakeExchange(response={"id": "UNEXPECTED"})
    dry, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=dry_exchange,
        live=False,
    )
    dry_result = dry(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    denied_exchange = FakeExchange(response={"id": "UNEXPECTED"})
    denied, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=denied_exchange,
        auth_ok=False,
    )
    denied_result = denied(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        execution_auth_token="DENIED",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    precision_exchange = FakeExchange(response={"id": "UNEXPECTED"})
    precision, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=precision_exchange,
        precision_error=ValueError("precision unavailable"),
    )
    precision_result = precision(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=client_tag,
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(client_tag),
    )

    assert [
        result["status"]
        for result in (
            invalid_result,
            unsafe_result,
            dry_result,
            denied_result,
            precision_result,
        )
    ] == [
        "MANAGED_CLOSE_INVALID_AMOUNT",
        "MANAGED_CLOSE_POSITION_NOT_SAFE",
        "MANAGED_CLOSE_DRY_RUN",
        "MANAGED_CLOSE_AUTH_DENIED",
        "MANAGED_CLOSE_ERROR",
    ]
    for result in (
        invalid_result,
        unsafe_result,
        dry_result,
        denied_result,
        precision_result,
    ):
        assert result["sent"] is False
        assert result["confirmed"] is False
        assert result["send_attempted"] is False
        assert result["send_outcome_unknown"] is False
        assert result["client_tag"] == client_tag
        assert result["client_order_id"] == client_tag.upper()
    assert dry_result["remaining_amount"] == 0.13
    assert not invalid_exchange.create_calls
    assert not unsafe_exchange.create_calls
    assert not dry_exchange.create_calls
    assert not denied_exchange.create_calls
    assert not precision_exchange.create_calls
    assert precision_result["phase"] == "PRE_SEND_SETUP"
    assert precision_result["failure_phase"] == "PRE_SEND_SETUP"


@pytest.mark.parametrize(
    "failure_kwargs",
    [
        {"exchange_error": RuntimeError("exchange setup unavailable")},
        {"position_side_error": RuntimeError("position side unavailable")},
        {"hedge_error": RuntimeError("hedge mode unavailable")},
        {"precision_error": RuntimeError("amount precision unavailable")},
    ],
)
def test_pre_send_setup_exceptions_are_structured_and_definitively_not_sent(failure_kwargs):
    fake_exchange = FakeExchange(response={"id": "MUST-NOT-BE-CREATED"})
    close, snapshot_calls, execution_events, audit_events = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=fake_exchange,
        **failure_kwargs,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TEST-AUTH",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )

    assert result["ok"] is False
    assert result["status"] == "MANAGED_CLOSE_ERROR"
    assert result["phase"] == result["failure_phase"] == "PRE_SEND_SETUP"
    assert result["send_attempted"] is False
    assert result["sent"] is False
    assert result["confirmed"] is False
    assert result["send_outcome_unknown"] is False
    assert result["error_type"] == "RuntimeError"
    assert snapshot_calls == [("SOLUSDT", "LONG", 0.13)]
    assert fake_exchange.create_calls == []
    assert execution_events[-1]["sent"] is False
    assert audit_events[-1]["send_attempted"] is False


def test_create_ack_without_factual_post_snapshot_is_sent_unconfirmed():
    exchange = FakeExchange(response={"id": "CLOSE-1", "filled": None})
    close, _, _, _ = _load_managed_close(
        snapshots=[
            _safe_open_snapshot(),
            {"ok": False, "status": "POSITION_SNAPSHOT_ERROR", "amount": None},
        ],
        fake_exchange=exchange,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )

    assert result["status"] == "MANAGED_CLOSE_SENT_UNCONFIRMED"
    assert result["sent"] is True
    assert result["confirmed"] is False
    assert result["send_attempted"] is True
    assert result["send_outcome_unknown"] is False
    assert result["order_id"] == "CLOSE-1"
    assert result["remaining_amount"] is None
    assert result["attempt_outcome_persistence_ok"] is True
    assert result["reconciliation_required"] is True


def test_create_ack_and_factual_flat_snapshot_is_confirmed():
    exchange = FakeExchange(response={"id": "CLOSE-2", "filled": 0.13})
    close, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot(), _safe_open_snapshot(amount=0.0)],
        fake_exchange=exchange,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )

    assert result["status"] == "MANAGED_CLOSE_CONFIRMED"
    assert result["sent"] is True
    assert result["confirmed"] is True
    assert result["send_attempted"] is True
    assert result["send_outcome_unknown"] is False
    assert result["order_id"] == "CLOSE-2"
    assert result["remaining_amount"] == 0.0


def test_managed_close_ack_with_unpersisted_outcome_is_sent_and_reconciled():
    exchange = FakeExchange(response={"id": "CLOSE-OUTCOME-PERSIST-FAIL"})
    close, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot(), _safe_open_snapshot(amount=0.0)],
        fake_exchange=exchange,
        outcome_persistence_ok=False,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )

    assert result["ok"] is False
    assert result["status"] == (
        "CREATE_ORDER_RETURNED_OUTCOME_PERSISTENCE_ERROR"
    )
    assert result["sent"] is True
    assert result["send_attempted"] is True
    assert result["send_outcome_unknown"] is False
    assert result["confirmed"] is None
    assert result["attempt_outcome_persistence_ok"] is False
    assert result["attempt_outcome_persistence"]["persistent"] is False
    assert result["reconciliation_required"] is True
    assert len(exchange.create_calls) == 1


def test_post_create_confirmation_exception_preserves_sent_and_order_identity():
    exchange = FakeExchange(
        response={
            "id": "CLOSE-POST-ACK",
            "filled": 0.02,
            "average": 75.90,
            "datetime": "2026-07-20T12:00:00Z",
        }
    )
    close, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=exchange,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TOKEN",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )

    assert result["status"] == "MANAGED_CLOSE_ERROR"
    assert result["send_attempted"] is True
    assert result["sent"] is True
    assert result["confirmed"] is None
    assert result["send_outcome_unknown"] is False
    assert result["order_id"] == "CLOSE-POST-ACK"
    assert result["filled_amount"] == 0.02
    assert result["average"] == 75.90
    assert result["timestamp"] == "2026-07-20T12:00:00Z"
    assert result["attempt_outcome_persistence_ok"] is True
    assert result["attempt_outcome_persistence"]["persistent"] is True
    assert result["reconciliation_required"] is True
    assert result["phase"] == result["failure_phase"] == "POST_CREATE_CONFIRMATION"


def test_historical_reader_requires_exact_order_identity_and_returns_sanitized_terminal_fact():
    reader = _load_historical_order_snapshot({
        "order": {
            "id": "STOP-HIST-1",
            "symbol": "SOLUSDT",
            "status": "canceled",
            "info": {
                "status": "FAILED",
                "executedQty": "0",
                "remainingQty": "0.13",
            },
        },
        "matched_count": 1,
    })

    result = reader("SOLUSDT", "STOP-HIST-1")

    assert result["ok"] is True
    assert result["historical"] is True
    assert result["read_only"] is True
    assert result["sent"] is False
    assert result["order_id"] == result["requested_order_id"] == "STOP-HIST-1"
    assert result["raw_status"] == "FAILED"
    assert result["executed_quantity"] == 0.0
    assert result["remaining_quantity"] == 0.13


def test_order_normalizer_preserves_raw_terminal_failure_and_sanitized_evidence():
    result = _load_order_normalizer()({
        "id": "STOP-1",
        "status": "canceled",
        "filled": 0,
        "remaining": 0.13,
        "info": {
            "status": "FAILED",
            "failureCode": "STOP_REJECTED",
            "failureReason": "trigger rejected",
            "executedQty": "0",
            "remainingQty": "0.13",
            "triggeredOrderId": "DERIVED-1",
            "fills": [{"tradeId": "FILL-1", "orderId": "STOP-1", "qty": "0", "price": "75.9"}],
        },
    }, requested_symbol="SOLUSDT", requested_order_id="STOP-1")

    assert result["status"] == "CANCELED"
    assert result["raw_status"] == "FAILED"
    assert result["failure_code"] == "STOP_REJECTED"
    assert result["failure_reason"] == "trigger rejected"
    assert result["executed_quantity"] == 0.0
    assert result["remaining_quantity"] == 0.13
    assert result["derived_order_id"] == "DERIVED-1"
    assert result["fills"] == [{
        "id": "FILL-1",
        "order_id": "STOP-1",
        "amount": 0.0,
        "price": 75.9,
    }]
    assert result["raw_info_exposed"] is False


@pytest.mark.parametrize(
    ("unsafe_message", "forbidden_fragments"),
    [
        ("request failed signature=SECRET", ["signature", "secret"]),
        ("request failed token=SECRET", ["token", "secret"]),
        ("request failed api_key=SECRET", ["api_key", "secret"]),
        (r"read failed at C:\secret\file", [r"c:\secret\file", "secret"]),
        ("read failed at /home/user/secret", ["/home/user/secret", "secret"]),
        (
            "GET https://api.example.test/order?signature=SECRET&token=SECRET failed",
            ["https://", "signature", "token", "secret"],
        ),
        (
            "authorization=Bearer-SECRET cookie=SECRET",
            ["authorization", "cookie", "secret"],
        ),
    ],
)
def test_historical_reader_sanitizes_and_bounds_exception_details(
    unsafe_message,
    forbidden_fragments,
):
    reader = _load_historical_order_snapshot(
        fetch_error=RuntimeError(unsafe_message),
    )

    result = reader("SOLUSDT", "STOP-HIST-SENSITIVE")
    serialized = json.dumps(result, ensure_ascii=False).lower()

    assert result["ok"] is False
    assert result["status"] == "HISTORICAL_ORDER_SNAPSHOT_ERROR"
    assert result["error_type"] == "RuntimeError"
    assert 0 < len(result["error"]) <= 240
    assert "\n" not in result["error"]
    for fragment in forbidden_fragments:
        assert fragment.lower() not in serialized


def test_managed_close_exception_uses_same_sanitized_projection():
    exchange = FakeExchange(error=RuntimeError("token=SECRET https://signed.test/x?signature=SECRET"))
    close, _, _, _ = _load_managed_close(
        snapshots=[_safe_open_snapshot()],
        fake_exchange=exchange,
    )

    result = close(
        "SOLUSDT",
        "LONG",
        0.13,
        expected_position_amount=0.13,
        client_tag=CANONICAL_MANAGED_CLOSE_ID,
        execution_auth_token="TEST-AUTH",
        client_order_id_unique=True,
        client_order_id_reservation=_reservation(CANONICAL_MANAGED_CLOSE_ID),
    )
    serialized = json.dumps(result, ensure_ascii=False).lower()

    assert result["phase"] == "CREATE_ORDER_OUTCOME_UNKNOWN"
    assert result["sent"] is None
    assert result["confirmed"] is None
    assert result["error_type"] == "RuntimeError"
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "signature" not in serialized
    assert "https://" not in serialized


def test_open_orders_snapshot_exposes_active_replacement_stop_without_raw_payload():
    reader, calls = _load_open_orders_snapshot(
        orders=[
            {
                "id": "STOP-2",
                "clientOrderId": "FALCON-STOP-2",
                "symbol": "SOL/USDT:USDT",
                "status": "open",
                "type": "market",
                "side": "sell",
                "amount": 0.13,
                "remaining": 0.13,
                "info": {
                    "status": "PENDING",
                    "planType": "STOP_LOSS",
                    "triggerOrderType": "STOP_MARKET",
                    "positionSide": "LONG",
                    "stopLossPrice": "75.90",
                },
            }
        ]
    )

    result = reader("SOLUSDT")

    assert result["ok"] is True
    assert result["status"] == "OPEN_ORDERS_SNAPSHOT_OK"
    assert result["read_only"] is True
    assert result["sent"] is False
    assert result["count"] == result["source_count"] == 1
    assert calls == ["SOL/USDT:USDT"]
    order = result["orders"][0]
    assert order["order_id"] == "STOP-2"
    assert order["client_order_id"] == "FALCON-STOP-2"
    assert order["status"] == "OPEN"
    assert order["plan_type"] == "STOP_LOSS"
    assert order["trigger_order_type"] == "STOP_MARKET"
    assert order["position_side"] == "LONG"
    assert order["stop_loss_price"] == 75.90
    assert order["symbol_matches_request"] is True
    assert order["raw_info_exposed"] is False
    assert "info" not in order


def test_open_orders_snapshot_sanitizes_bounded_order_projection():
    reader, _ = _load_open_orders_snapshot(
        orders=[
            {
                "id": "STOP-SAFE",
                "clientOrderId": "token=SECRET",
                "symbol": "SOL/USDT:USDT",
                "status": "open",
                "info": {
                    "planType": "STOP_LOSS",
                    "failureReason": (
                        r"signature=SECRET C:\secret\file "
                        "https://signed.test/order?api_key=SECRET"
                    ),
                },
            }
        ]
    )

    result = reader("SOLUSDT")
    serialized = json.dumps(result, ensure_ascii=False).lower()

    assert result["ok"] is True
    assert len(serialized) < 20_000
    for fragment in (
        "secret",
        "token",
        "signature",
        "api_key",
        "c:\\secret\\file",
        "https://",
    ):
        assert fragment not in serialized


def test_open_orders_snapshot_failure_is_structured_sanitized_and_read_only():
    reader, calls = _load_open_orders_snapshot(
        fetch_error=RuntimeError(
            "authorization=SECRET /home/user/secret "
            "https://signed.test/open?signature=SECRET"
        )
    )

    result = reader("SOLUSDT")
    serialized = json.dumps(result, ensure_ascii=False).lower()

    assert result["ok"] is False
    assert result["status"] == "OPEN_ORDERS_SNAPSHOT_ERROR"
    assert result["read_only"] is True
    assert result["sent"] is False
    assert result["orders"] == []
    assert result["count"] == 0
    assert result["error_type"] == "RuntimeError"
    assert 0 < len(result["error"]) <= 240
    assert calls == ["SOL/USDT:USDT"]
    for fragment in ("authorization", "secret", "/home/user/secret", "https://", "signature"):
        assert fragment not in serialized
