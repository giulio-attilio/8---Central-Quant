from __future__ import annotations

import ast
from pathlib import Path

import pytest

import broker


ROOT = Path(__file__).resolve().parents[1]
CLIENT_ORDER_ID = "FDS1-0123456789ABCDEF01234567"
ENTRY_CLIENT_ORDER_ID = "ENT1-0123456789ABCDEF01234567"


@pytest.fixture(autouse=True)
def _recorded_account_attempt_outcomes(monkeypatch):
    recorded = []

    def record(reservation, *, outcome_state, **details):
        recorded.append((dict(reservation or {}), outcome_state, details))
        return {
            "ok": True,
            "status": outcome_state,
            "client_order_id": (reservation or {}).get("client_order_id"),
            "persistent": True,
            "id_released": False,
        }

    monkeypatch.setattr(
        broker, "record_account_client_order_attempt_outcome", record
    )
    return recorded


def _reservation():
    return {
        "ok": True,
        "send_allowed": True,
        "status": "RESERVED_UNIQUE",
        "reservation_status": "RESERVED_UNIQUE",
        "reservation_state": "RESERVED_PRE_SEND",
        "persistent": True,
        "client_order_id": CLIENT_ORDER_ID,
        "client_order_id_reserved": True,
        "client_order_id_unique": True,
        "canonical_operation_id": "OP-1",
        "attempt_id": "ATTEMPT-1",
        "attempt_sequence": 0,
        "attempt_identity_hash": "HASH-1",
        "bot": "FALCON",
        "role": "INITIAL_DISASTER_STOP",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "entry_client_order_id": "ENTRY-1",
        "entry_order_id": "ORDER-1",
        "stop_revision": 0,
        "order_type": "STOP_MARKET",
    }


def _verified(_reservation_payload, expected_client_order_id=None):
    assert expected_client_order_id == CLIENT_ORDER_ID
    return {
        "ok": True,
        "send_allowed": True,
        "status": "RESERVED_UNIQUE",
        "persistent": True,
        "client_order_id": CLIENT_ORDER_ID,
        "client_order_id_reserved": True,
        "client_order_id_unique": True,
        "canonical_operation_id": "OP-1",
        "attempt_id": "ATTEMPT-1",
        "attempt_sequence": 0,
        "attempt_identity_hash": "HASH-1",
        "bot": "FALCON",
        "role": "INITIAL_DISASTER_STOP",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "entry_client_order_id": "ENTRY-1",
        "entry_order_id": "ORDER-1",
        "stop_revision": 0,
        "order_type": "STOP_MARKET",
    }


class _FakeExchange:
    def __init__(self, *, failure=None):
        self.failure = failure
        self.calls = []

    def create_order(self, *args):
        self.calls.append(args)
        if self.failure is not None:
            raise self.failure
        params = args[-1]
        return {
            "id": "EXCHANGE-ORDER-1",
            "status": "open",
            "clientOrderId": params["clientOrderId"],
        }


def _install_one_time_claim(monkeypatch):
    state = {"claimed": False, "calls": 0}

    def claim(reservation, *, expected_client_order_id):
        state["calls"] += 1
        assert reservation["attempt_id"] == "ATTEMPT-1"
        assert expected_client_order_id == CLIENT_ORDER_ID
        if state["claimed"]:
            return {
                "ok": False,
                "send_allowed": False,
                "send_claimed": True,
                "status": "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED",
                "client_order_id": CLIENT_ORDER_ID,
                "persistent": True,
                "reconciliation_required": True,
            }
        state["claimed"] = True
        return {
            "ok": True,
            "send_allowed": True,
            "send_claimed": True,
            "status": "SEND_CLAIMED",
            "client_order_id": CLIENT_ORDER_ID,
            "canonical_operation_id": "OP-1",
            "attempt_id": "ATTEMPT-1",
            "attempt_sequence": 0,
            "attempt_identity_hash": "HASH-1",
            "attempt_disposition": "SEND_CLAIMED",
            "persistent": True,
        }

    monkeypatch.setattr(
        broker, "claim_account_client_order_send_authorization", claim
    )
    return state


def _send(exchange, *, send_state=None):
    return broker._create_order_with_reserved_attempt(
        exchange,
        "SOL/USDT:USDT",
        "stop_market",
        "sell",
        0.13,
        None,
        {"clientOrderId": CLIENT_ORDER_ID, "stopPrice": 75.9},
        client_order_id_reservation=_reservation(),
        expected_reservation_roles={"INITIAL_DISASTER_STOP"},
        client_order_id_reservation_verifier=_verified,
        send_state=send_state,
    )


def test_raw_create_boundary_claims_once_and_blocks_receipt_reuse(
    monkeypatch, _recorded_account_attempt_outcomes
):
    claim_state = _install_one_time_claim(monkeypatch)
    exchange = _FakeExchange()

    first = _send(exchange)
    second = _send(exchange)

    assert first["ok"] is True
    assert first["returned_client_order_id_matches"] is True
    assert second["ok"] is False
    assert second["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert second["sent"] is False
    assert len(exchange.calls) == 1
    assert claim_state["calls"] == 2
    assert [
        state for _, state, _ in _recorded_account_attempt_outcomes
    ] == ["ACKNOWLEDGED"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "TP50_CLOSE"),
        ("symbol", "XRPUSDT"),
        ("side", "SHORT"),
        ("order_type", "MARKET"),
        ("lifecycle_id", ""),
    ],
)
def test_raw_create_boundary_rejects_reservation_context_mismatch(
    monkeypatch, field, value, _recorded_account_attempt_outcomes
):
    exchange = _FakeExchange()
    reservation = _reservation()
    verification = _verified(reservation, expected_client_order_id=CLIENT_ORDER_ID)
    verification[field] = value

    result = broker._create_order_with_reserved_attempt(
        exchange,
        "SOL/USDT:USDT",
        "stop_market",
        "sell",
        0.13,
        None,
        {"clientOrderId": CLIENT_ORDER_ID, "stopPrice": 75.9},
        client_order_id_reservation=reservation,
        expected_reservation_roles={"INITIAL_DISASTER_STOP"},
        client_order_id_reservation_verifier=lambda *_args, **_kwargs: verification,
    )

    assert result["status"] == "CLIENT_ORDER_ID_RESERVATION_CONTEXT_MISMATCH"
    failed_check = {
        "role": "role_matches_writer",
        "symbol": "symbol_matches_writer",
        "side": "side_matches_writer",
        "order_type": "order_type_matches_writer",
        "lifecycle_id": "lifecycle_identity_present",
    }[field]
    assert failed_check in result["reservation_context"]["failed_checks"]
    assert result["reservation_context"][failed_check] is False
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert exchange.calls == []
    assert [
        state for _, state, _ in _recorded_account_attempt_outcomes
    ] == ["PRE_SEND_FAILED_ATTEMPT_CONSUMED"]
    assert _recorded_account_attempt_outcomes[0][2] == {
        "reason": "CLIENT_ORDER_ID_RESERVATION_CONTEXT_MISMATCH",
        "failure_phase": "PRE_SEND_CONTEXT_VALIDATION",
    }


def test_timeout_after_claim_is_outcome_unknown_and_retry_does_not_send(
    monkeypatch, _recorded_account_attempt_outcomes
):
    _install_one_time_claim(monkeypatch)
    exchange = _FakeExchange(failure=TimeoutError("response lost"))
    send_state = {}

    with pytest.raises(TimeoutError, match="response lost"):
        _send(exchange, send_state=send_state)

    retry = _send(exchange)
    assert send_state["send_attempted"] is True
    assert send_state["create_returned"] is False
    assert send_state["send_outcome_unknown"] is True
    assert retry["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert len(exchange.calls) == 1
    assert [
        state for _, state, _ in _recorded_account_attempt_outcomes
    ] == ["CREATE_ORDER_OUTCOME_UNKNOWN"]


def test_overlength_id_blocks_before_claim_or_exchange(monkeypatch):
    claim_calls = []
    monkeypatch.setattr(
        broker,
        "claim_account_client_order_send_authorization",
        lambda *args, **kwargs: claim_calls.append((args, kwargs)),
    )
    exchange = _FakeExchange()
    result = broker._create_order_with_reserved_attempt(
        exchange,
        "SOL/USDT:USDT",
        "market",
        "sell",
        0.13,
        None,
        {"clientOrderId": "X" * 33},
        client_order_id_reservation=_reservation(),
        expected_reservation_roles={"INITIAL_DISASTER_STOP"},
        client_order_id_reservation_verifier=_verified,
    )
    assert result["status"] == "CLIENT_ORDER_ID_INVALID_LENGTH"
    assert result["sent"] is False
    assert exchange.calls == []
    assert claim_calls == []


def test_authority_exception_is_fail_closed_before_exchange(monkeypatch):
    monkeypatch.setattr(
        broker,
        "claim_account_client_order_send_authorization",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("authority unavailable")
        ),
    )
    exchange = _FakeExchange()
    result = _send(exchange)
    assert result["status"] == "CLIENT_ORDER_SEND_CLAIM_AUTHORITY_ERROR"
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert result["reconciliation_required"] is True
    assert exchange.calls == []


@pytest.mark.parametrize(
    "authority_status",
    [
        "CLIENT_ORDER_ATTEMPT_DISPOSITION_BLOCKED",
        "CLIENT_ORDER_ATTEMPT_SEQUENCE_SLOT_MISMATCH",
    ],
)
def test_authoritative_disposition_or_sequence_failure_never_reaches_exchange(
    monkeypatch, authority_status
):
    claim_calls = []
    monkeypatch.setattr(
        broker,
        "claim_account_client_order_send_authorization",
        lambda *args, **kwargs: claim_calls.append((args, kwargs)),
    )
    exchange = _FakeExchange()

    def blocked_verifier(*_args, **_kwargs):
        return {
            **_verified(_reservation(), expected_client_order_id=CLIENT_ORDER_ID),
            "ok": False,
            "send_allowed": False,
            "status": authority_status,
            "reconciliation_required": True,
        }

    result = broker._create_order_with_reserved_attempt(
        exchange,
        "SOL/USDT:USDT",
        "stop_market",
        "sell",
        0.13,
        None,
        {"clientOrderId": CLIENT_ORDER_ID, "stopPrice": 75.9},
        client_order_id_reservation=_reservation(),
        expected_reservation_roles={"INITIAL_DISASTER_STOP"},
        client_order_id_reservation_verifier=blocked_verifier,
    )

    assert result["status"] == authority_status
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert exchange.calls == []
    assert claim_calls == []


def test_send_claim_sequence_mismatch_blocks_before_exchange(monkeypatch):
    monkeypatch.setattr(
        broker,
        "claim_account_client_order_send_authorization",
        lambda *_args, **_kwargs: {
            "ok": True,
            "send_allowed": True,
            "send_claimed": True,
            "status": "SEND_CLAIMED",
            "persistent": True,
            "client_order_id": CLIENT_ORDER_ID,
            "canonical_operation_id": "OP-1",
            "attempt_id": "ATTEMPT-1",
            "attempt_sequence": 1,
            "attempt_identity_hash": "HASH-1",
        },
    )
    exchange = _FakeExchange()

    result = _send(exchange)

    assert result["status"] == "CLIENT_ORDER_SEND_CLAIM_CONTEXT_MISMATCH"
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert exchange.calls == []


def test_disposition_lost_during_claim_blocks_before_exchange(monkeypatch):
    monkeypatch.setattr(
        broker,
        "claim_account_client_order_send_authorization",
        lambda *_args, **_kwargs: {
            "ok": False,
            "send_allowed": False,
            "send_claimed": False,
            "status": "CLIENT_ORDER_ATTEMPT_PRE_SEND_CONSUMED",
            "persistent": True,
            "attempt_disposition": "PRE_SEND_CONSUMED",
            "reconciliation_required": True,
        },
    )
    exchange = _FakeExchange()

    result = _send(exchange)

    assert result["status"] == "CLIENT_ORDER_ATTEMPT_PRE_SEND_CONSUMED"
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert result["reconciliation_required"] is True
    assert exchange.calls == []


def test_acknowledged_send_with_unpersisted_outcome_requires_reconciliation(
    monkeypatch
):
    _install_one_time_claim(monkeypatch)
    monkeypatch.setattr(
        broker,
        "record_account_client_order_attempt_outcome",
        lambda *_args, **_kwargs: {
            "ok": False,
            "status": "ATTEMPT_OUTCOME_PERSISTENCE_ERROR",
            "persistent": False,
        },
    )
    exchange = _FakeExchange()

    result = _send(exchange)

    assert result["ok"] is False
    assert result["status"] == (
        "CREATE_ORDER_RETURNED_OUTCOME_PERSISTENCE_ERROR"
    )
    assert result["sent"] is True
    assert result["send_attempted"] is True
    assert result["attempt_outcome_persistent"] is False
    assert result["attempt_outcome_persistence"]["persistent"] is False
    assert result["reconciliation_required"] is True
    assert len(exchange.calls) == 1


def test_acknowledged_send_survives_outcome_recorder_exception(monkeypatch):
    _install_one_time_claim(monkeypatch)
    monkeypatch.setattr(
        broker,
        "record_account_client_order_attempt_outcome",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("outcome authority unavailable")
        ),
    )
    exchange = _FakeExchange()

    result = _send(exchange)

    assert result["ok"] is False
    assert result["status"] == (
        "CREATE_ORDER_RETURNED_OUTCOME_PERSISTENCE_ERROR"
    )
    assert result["sent"] is True
    assert result["send_attempted"] is True
    assert result["attempt_outcome_persistence_ok"] is False
    assert result["attempt_outcome_persistence"]["error_type"] == "RuntimeError"
    assert result["reconciliation_required"] is True
    assert len(exchange.calls) == 1


def test_unknown_send_with_unpersisted_outcome_keeps_material_unknown_state(
    monkeypatch
):
    _install_one_time_claim(monkeypatch)
    monkeypatch.setattr(
        broker,
        "record_account_client_order_attempt_outcome",
        lambda *_args, **_kwargs: {
            "ok": False,
            "status": "ATTEMPT_OUTCOME_PERSISTENCE_ERROR",
            "persistent": False,
        },
    )
    exchange = _FakeExchange(failure=TimeoutError("response lost"))
    send_state = {}

    with pytest.raises(TimeoutError, match="response lost"):
        _send(exchange, send_state=send_state)

    assert send_state["send_attempted"] is True
    assert send_state["create_returned"] is False
    assert send_state["send_outcome_unknown"] is True
    assert send_state["attempt_outcome_persistent"] is False
    assert send_state["attempt_outcome_persistence"]["persistent"] is False
    assert send_state["reconciliation_required"] is True
    assert len(exchange.calls) == 1


def test_entry_ack_persistence_failure_still_arms_stop_and_never_resends_entry(
    monkeypatch,
):
    stop_client_order_id = CLIENT_ORDER_ID

    def reservation(client_order_id, role, order_type, attempt_id):
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "reservation_status": "RESERVED_UNIQUE",
            "reservation_state": "RESERVED_PRE_SEND",
            "persistent": True,
            "client_order_id": client_order_id,
            "client_order_id_reserved": True,
            "client_order_id_unique": True,
            "canonical_operation_id": f"OP-{role}",
            "attempt_id": attempt_id,
            "attempt_sequence": 0,
            "attempt_identity_hash": f"HASH-{role}",
            "bot": "FALCON",
            "role": role,
            "lifecycle_id": "LC-ENTRY-ACK-PERSISTENCE",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "entry_client_order_id": ENTRY_CLIENT_ORDER_ID,
            "entry_order_id": "ENTRY-ORDER-1",
            "stop_revision": 0,
            "order_type": order_type,
        }

    entry_reservation = reservation(
        ENTRY_CLIENT_ORDER_ID, "ENTRY", "MARKET", "ENTRY-ATTEMPT-0"
    )
    stop_reservation = reservation(
        stop_client_order_id,
        "INITIAL_DISASTER_STOP",
        "STOP_MARKET",
        "STOP-ATTEMPT-0",
    )
    claimed = set()
    outcomes = []

    def verify(receipt, *, expected_client_order_id):
        assert receipt["client_order_id"] == expected_client_order_id
        return dict(receipt)

    def claim(receipt, *, expected_client_order_id):
        assert receipt["client_order_id"] == expected_client_order_id
        attempt_id = receipt["attempt_id"]
        if attempt_id in claimed:
            return {
                "ok": False,
                "send_allowed": False,
                "send_claimed": True,
                "status": "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED",
                "client_order_id": expected_client_order_id,
                "persistent": True,
                "reconciliation_required": True,
            }
        claimed.add(attempt_id)
        return {
            **dict(receipt),
            "ok": True,
            "send_allowed": True,
            "send_claimed": True,
            "status": "SEND_CLAIMED",
            "attempt_disposition": "SEND_CLAIMED",
            "persistent": True,
        }

    def record(receipt, *, outcome_state, **_details):
        outcomes.append((receipt["role"], outcome_state))
        if receipt["role"] == "ENTRY":
            return {
                "ok": False,
                "status": "ATTEMPT_OUTCOME_PERSISTENCE_ERROR",
                "persistent": False,
            }
        return {
            "ok": True,
            "status": outcome_state,
            "persistent": True,
            "id_released": False,
        }

    class ExchangeProbe:
        def __init__(self):
            self.create_calls = []
            self.entry_returned_client_order_id_override = None

        def set_margin_mode(self, *_args, **_kwargs):
            return {"ok": True}

        def set_leverage(self, *_args, **_kwargs):
            return {"ok": True}

        def create_order(self, symbol, order_type, side, amount, price, params):
            del price
            self.create_calls.append(
                {
                    "symbol": symbol,
                    "type": order_type,
                    "side": side,
                    "amount": amount,
                    "client_order_id": params["clientOrderId"],
                }
            )
            if order_type == "market":
                return {
                    "id": "ENTRY-ORDER-1",
                    "status": "closed",
                    "clientOrderId": (
                        self.entry_returned_client_order_id_override
                        or params["clientOrderId"]
                    ),
                }
            return {
                "id": "STOP-ORDER-1",
                "status": "open",
                "clientOrderId": params["clientOrderId"],
                "symbol": symbol,
                "side": side,
                "positionSide": params["positionSide"],
                "type": order_type,
                "amount": amount,
                "stopPrice": params["stopPrice"],
            }

    exchange = ExchangeProbe()
    audit_events = []
    monkeypatch.setattr(broker, "EXECUTION_MODE", "LIVE")
    monkeypatch.setattr(broker, "ENABLE_REAL_TRADING", True)
    monkeypatch.setattr(broker, "BROKER_DRY_RUN", False)
    monkeypatch.setattr(broker, "DISASTER_STOP_ENABLED", True)
    monkeypatch.setattr(broker, "DISASTER_STOP_REQUIRE_FOR_LIVE", True)
    monkeypatch.setattr(
        broker, "_automatic_broker_preview_firewall", lambda **_kwargs: {"blocked": False}
    )
    monkeypatch.setattr(
        broker,
        "build_order_preview",
        lambda *_args, **_kwargs: {
            "ok": True,
            "status": "PREVIEW",
            "constraints_ok": True,
            "client_order_id": _kwargs["client_tag"],
            "amount": 0.13,
            "price_ref": 76.212,
            "notional_usdt": 9.90,
            "planned_exposure_usdt": 9.90,
            "actual_exposure_usdt": 9.90,
        },
    )
    monkeypatch.setattr(
        broker,
        "broker_real_pilot_guard_v1_validate",
        lambda **_kwargs: {"allowed": True, "reasons": []},
    )
    monkeypatch.setattr(
        broker,
        "validate_execution_auth_token",
        lambda *_args, **_kwargs: {"ok": True},
    )
    monkeypatch.setattr(
        broker, "validate_disaster_stop_price", lambda *_args, **_kwargs: {"ok": True}
    )
    monkeypatch.setattr(broker, "ready_check", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(broker, "exchange", lambda: exchange)
    monkeypatch.setattr(
        broker, "verify_account_client_order_id_reservation", verify
    )
    monkeypatch.setattr(
        broker, "claim_account_client_order_send_authorization", claim
    )
    monkeypatch.setattr(
        broker, "record_account_client_order_attempt_outcome", record
    )
    monkeypatch.setattr(broker, "log_execution_event", lambda event: audit_events.append(event))
    monkeypatch.setattr(
        broker, "log_execution_audit_event", lambda event: audit_events.append(event)
    )
    monkeypatch.setattr(
        broker, "_set_last_disaster_stop_diagnostic", lambda **_kwargs: None
    )

    def stop_factory(**identity):
        assert identity["entry_order_id"] == "ENTRY-ORDER-1"
        assert identity["entry_client_order_id"] == ENTRY_CLIENT_ORDER_ID
        return dict(stop_reservation)

    first = broker.place_market_order(
        symbol="SOLUSDT",
        side="LONG",
        margin_usdt=9.90,
        leverage=1,
        client_tag=ENTRY_CLIENT_ORDER_ID,
        bot="FALCON",
        execution_auth_token="TEST-ONLY",
        stop_loss_price=75.924,
        falcon_position_ownership_limit={"known": True},
        disaster_stop_client_order_id_factory=stop_factory,
        client_order_id_reservation=entry_reservation,
        client_order_id_reservation_verifier=verify,
    )

    assert first["ok"] is False
    assert first["status"] == (
        "LIVE_SENT_PROTECTED_ENTRY_ACK_PERSISTENCE_ERROR"
    )
    assert first["sent"] is True
    assert first["entry_acknowledged"] is True
    assert first["entry_ack_persistence_degraded"] is True
    assert first["attempt_outcome_persistence_ok"] is False
    assert first["reconciliation_required"] is True
    assert first["disaster_stop"]["stop_operationally_armed"] is True
    assert first["disaster_stop"]["order_id"] == "STOP-ORDER-1"
    assert [call["type"] for call in exchange.create_calls] == [
        "market",
        "stop_market",
    ]
    assert [call["client_order_id"] for call in exchange.create_calls] == [
        ENTRY_CLIENT_ORDER_ID,
        stop_client_order_id,
    ]
    assert outcomes == [
        ("ENTRY", "ACKNOWLEDGED"),
        ("INITIAL_DISASTER_STOP", "ACKNOWLEDGED"),
    ]

    retry = broker.place_market_order(
        symbol="SOLUSDT",
        side="LONG",
        margin_usdt=9.90,
        leverage=1,
        client_tag=ENTRY_CLIENT_ORDER_ID,
        bot="FALCON",
        execution_auth_token="TEST-ONLY",
        stop_loss_price=75.924,
        falcon_position_ownership_limit={"known": True},
        disaster_stop_client_order_id_factory=stop_factory,
        client_order_id_reservation=entry_reservation,
        client_order_id_reservation_verifier=verify,
    )

    assert retry["status"] == "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED"
    assert retry["sent"] is False
    assert len(exchange.create_calls) == 2

    untrusted_client_order_id = "ENT1-FEDCBA9876543210FEDCBA98"
    untrusted_reservation = reservation(
        untrusted_client_order_id,
        "ENTRY",
        "MARKET",
        "ENTRY-ATTEMPT-UNTRUSTED",
    )
    exchange.entry_returned_client_order_id_override = ENTRY_CLIENT_ORDER_ID
    untrusted = broker.place_market_order(
        symbol="SOLUSDT",
        side="LONG",
        margin_usdt=9.90,
        leverage=1,
        client_tag=untrusted_client_order_id,
        bot="FALCON",
        execution_auth_token="TEST-ONLY",
        stop_loss_price=75.924,
        falcon_position_ownership_limit={"known": True},
        disaster_stop_client_order_id_factory=lambda **_identity: pytest.fail(
            "disaster stop attempted without trusted returned clientOrderID"
        ),
        client_order_id_reservation=untrusted_reservation,
        client_order_id_reservation_verifier=verify,
    )

    assert untrusted["ok"] is False
    assert untrusted["sent"] is True
    assert untrusted["entry_acknowledged"] is False
    assert untrusted["returned_client_order_id_matches"] is False
    assert untrusted["reconciliation_required"] is True
    assert len(exchange.create_calls) == 3
    assert exchange.create_calls[-1]["type"] == "market"


def test_broker_has_exactly_one_raw_create_order_sink():
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    calls = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_order"
        ):
            continue
        owner = parents.get(node)
        while owner is not None and not isinstance(
            owner, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            owner = parents.get(owner)
        calls.append((node.lineno, owner.name if owner is not None else None))

    assert len(calls) == 1
    assert calls[0][1] == "_create_order_with_reserved_attempt"


def test_replace_and_managed_close_require_rich_reservation_parameters():
    replace_parameters = broker.replace_position_stop_order.__code__.co_varnames[
        : broker.replace_position_stop_order.__code__.co_argcount
    ]
    close_parameters = broker.managed_close_position_market.__code__.co_varnames[
        : broker.managed_close_position_market.__code__.co_argcount
    ]
    assert "client_order_id_reservation" in replace_parameters
    assert "rollback_client_order_id_reservation" in replace_parameters
    assert "client_order_id_reservation_verifier" in replace_parameters
    assert "client_order_id_reservation" in close_parameters
    assert "client_order_id_reservation_verifier" in close_parameters


def test_active_legacy_close_initializes_send_state_before_common_boundary():
    tree = ast.parse((ROOT / "broker.py").read_text(encoding="utf-8"))
    definitions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "close_position_market"
    ]
    assert definitions
    active = definitions[-1]
    assignments = [
        node
        for node in ast.walk(active)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "send_state"
            for target in node.targets
        )
    ]
    boundary_calls = [
        node
        for node in ast.walk(active)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_create_order_with_reserved_attempt"
    ]

    assert len(assignments) == len(boundary_calls) == 1
    assert assignments[0].lineno < boundary_calls[0].lineno
    keywords = {item.arg: item.value for item in boundary_calls[0].keywords if item.arg}
    assert isinstance(keywords.get("send_state"), ast.Name)
    assert keywords["send_state"].id == "send_state"
