from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from falcon_client_order_id import (
    FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION,
    ROLE_INITIAL_DISASTER_STOP,
    canonical_falcon_order_identity,
    canonical_falcon_order_identity_hash,
    generate_falcon_client_order_id,
    is_valid_falcon_client_order_id,
)
from account_client_order_id import (
    ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX,
    account_client_order_id_ledger_key,
    reserve_account_client_order_attempt,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
MAIN_SOURCE = ROOT / "main.py"
BROKER_SOURCE = ROOT / "broker.py"


def _load_final_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    """Compile selected Falcon helpers without importing its runtime module."""
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert definitions, name
        selected.append(copy.deepcopy(definitions[-1]))
    module = ast.Module(
        body=sorted(selected, key=lambda node: node.lineno),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = dict(globals_dict)
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    return namespace


def _load_final_main_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert definitions, name
        selected.append(copy.deepcopy(definitions[-1]))
    module = ast.Module(
        body=sorted(selected, key=lambda node: node.lineno),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = dict(globals_dict)
    exec(compile(module, str(MAIN_SOURCE), "exec"), namespace)
    return namespace


def _load_broker_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    selected = []
    for name in names:
        definitions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == name
        ]
        assert definitions, name
        selected.append(copy.deepcopy(definitions[-1]))
    module = ast.Module(
        body=sorted(selected, key=lambda node: node.lineno),
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    namespace = dict(globals_dict)
    exec(compile(module, str(BROKER_SOURCE), "exec"), namespace)
    return namespace


class _PersistentRedisFake:
    """Minimal process-persistent Redis model used only by the isolated guard."""

    def __init__(self):
        self.values: dict[str, str] = {}
        self.lock = threading.Lock()


def _guard_namespace():
    redis = _PersistentRedisFake()
    health: dict = {}

    def set_if_absent(client, key, value, *, caller=None):
        del caller
        assert client is redis
        with client.lock:
            if key in client.values:
                return False
            client.values[key] = value
            return True

    def get_authoritative(client, key, *, caller=None):
        del caller
        assert client is redis
        with client.lock:
            return client.values.get(key)

    namespace = _load_final_functions(
        (
            "_falcon_client_order_id_health_update",
            "falcon_client_order_id_reservation_key",
            "falcon_reserve_client_order_id",
        ),
        {
            "__name__": "isolated_falcon_client_order_id_guard",
            "hashlib": hashlib,
            "json": json,
            "redis_lock": threading.Lock(),
            "redis": redis,
            "HEALTH": health,
            "FALCON_CLIENT_ORDER_ID_RESERVATION_PREFIX": (
                ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX
            ),
            "FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION": (
                FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION
            ),
            "ROLE_INITIAL_DISASTER_STOP": ROLE_INITIAL_DISASTER_STOP,
            "canonical_falcon_order_identity": canonical_falcon_order_identity,
            "canonical_falcon_order_identity_hash": (
                canonical_falcon_order_identity_hash
            ),
            "is_valid_falcon_client_order_id": is_valid_falcon_client_order_id,
            "bandwidth_redis_set_if_absent": set_if_absent,
            "bandwidth_redis_get_authoritative": get_authoritative,
            "account_client_order_id_ledger_key": account_client_order_id_ledger_key,
            "reserve_account_client_order_attempt": reserve_account_client_order_attempt,
            "datetime": datetime,
            "timezone": timezone,
            "data_hora_sp_str": lambda: "20/07/2026 12:00",
        },
    )
    return namespace, redis, health


def _identity(**updates):
    value = {
        "bot": "FALCON",
        "lifecycle_id": (
            "CENTRAL-FALCON-LIFECYCLE:"
            "FALCON-LIVE-FALCON15-1784470538"
        ),
        "entry_client_order_id": "FALCON-LIVE-FALCON15-1784470538",
        "entry_order_id": "2078846240427298816",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "operation": ROLE_INITIAL_DISASTER_STOP,
        "revision": 0,
        "attempt": 0,
    }
    value.update(updates)
    return value


def test_atomic_reservation_allows_exactly_one_send_for_first_identity():
    namespace, redis, _ = _guard_namespace()
    reserve = namespace["falcon_reserve_client_order_id"]
    identity = _identity()
    client_order_id = generate_falcon_client_order_id(**identity)
    sends: list[str] = []

    def guarded_send(_):
        reservation = reserve(client_order_id, identity)
        if reservation["send_allowed"]:
            sends.append(client_order_id)
        return reservation

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(guarded_send, range(24)))

    assert sends == [client_order_id]
    assert sum(row["status"] == "RESERVED_UNIQUE" for row in results) == 1
    assert sum(
        row["status"]
        == "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
        for row in results
    ) == 23
    assert len(redis.values) == 4
    sequence_records = [
        json.loads(serialized)
        for key, serialized in redis.values.items()
        if "client_order_sequence" in key
    ]
    assert len(sequence_records) == 1
    assert sequence_records[0]["attempt_sequence"] == 0
    assert sequence_records[0]["client_order_id"] == client_order_id


def test_same_id_and_same_identity_is_idempotent_but_never_authorizes_resend():
    namespace, _, _ = _guard_namespace()
    reserve = namespace["falcon_reserve_client_order_id"]
    identity = _identity()
    client_order_id = generate_falcon_client_order_id(**identity)

    first = reserve(client_order_id, identity)
    retry = reserve(client_order_id, identity)

    assert first["send_allowed"] is True
    assert first["client_order_id_unique"] is True
    assert retry["ok"] is True
    assert retry["send_allowed"] is False
    assert retry["status"] == (
        "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
    )
    assert retry["client_order_id_unique"] is True
    assert retry["collision_detected"] is False
    assert retry["same_identity"] is True
    assert retry["reconciliation_required"] is True


def test_same_id_and_different_identity_is_a_fail_closed_collision():
    namespace, _, health = _guard_namespace()
    reserve = namespace["falcon_reserve_client_order_id"]
    first_identity = _identity()
    different_identity = _identity(
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:OTHER",
        entry_client_order_id="FALCON-LIVE-FALCON15-1784124020",
        entry_order_id="2078846240427298999",
    )
    client_order_id = generate_falcon_client_order_id(**first_identity)

    assert reserve(client_order_id, first_identity)["send_allowed"] is True
    collision = reserve(client_order_id, different_identity)

    assert collision["ok"] is False
    assert collision["send_allowed"] is False
    assert collision["status"] == "CLIENT_ORDER_ID_COLLISION_DETECTED"
    assert collision["client_order_id_unique"] is False
    assert collision["same_identity"] is False
    assert collision["collision_detected"] is True
    assert collision["reconciliation_required"] is True
    assert health["falcon_client_order_id_collision_detected"] is True
    assert health["falcon_client_order_id_collision_role"] == (
        ROLE_INITIAL_DISASTER_STOP
    )


def test_persisted_reservation_is_minimal_and_contains_no_authorization_token():
    namespace, redis, _ = _guard_namespace()
    identity = _identity()
    client_order_id = generate_falcon_client_order_id(**identity)
    result = namespace["falcon_reserve_client_order_id"](
        client_order_id, identity
    )

    assert result["send_allowed"] is True
    records = [json.loads(serialized) for serialized in redis.values.values()]
    ledger_record = next(
        record
        for record in records
        if record.get("client_order_id") == client_order_id
        and record.get("state") == "RESERVED_PRE_SEND"
    )
    assert ledger_record["client_order_id"] == client_order_id
    assert ledger_record["state"] == "RESERVED_PRE_SEND"
    assert ledger_record["lifetime"] is True
    assert ledger_record["case_sensitive"] is False
    serialized_all = json.dumps(records, sort_keys=True)
    assert not {
        "authorization_token",
        "management_authorization_token",
        "token",
        "secret",
    }.intersection(ledger_record)
    assert "authorization_token" not in serialized_all.lower()
    assert "secret" not in serialized_all.lower()


def test_disaster_stop_health_cannot_be_armed_without_uniqueness_proof():
    health: dict = {}
    namespace = _load_final_functions(
        ("_falcon_update_stop_health",),
        {"HEALTH": health},
    )
    update_health = namespace["_falcon_update_stop_health"]
    otherwise_valid = {
        "stop_order_active": True,
        "stop_order_identity_match": True,
        "protection_matches_position": True,
        "stop_order_protective_verified": True,
        "entry_ownership_verified": True,
        "client_order_id_reserved": True,
        "stop_client_order_id_match": True,
        "stop_operationally_armed": True,
        "disaster_stop_client_order_id": "FDS1-0123456789ABCDEF01234567",
        "stop_semantic_predicates": {},
        "stop_semantic_failure_reasons": [],
        "type_source_summary": [],
    }

    update_health({**otherwise_valid, "client_order_id_unique": None})
    assert health["falcon_disaster_stop_active_verified"] is False
    assert health["falcon_disaster_stop_client_order_id_unique"] is False

    update_health({**otherwise_valid, "client_order_id_unique": False})
    assert health["falcon_disaster_stop_active_verified"] is False

    update_health({**otherwise_valid, "client_order_id_unique": True})
    assert health["falcon_disaster_stop_active_verified"] is True
    assert health["falcon_disaster_stop_client_order_id_unique"] is True


def test_main_disaster_stop_fallback_never_reaches_broker_without_persistent_reservation():
    class BrokerAccessBomb:
        def __getattr__(self, name):
            raise AssertionError(f"broker accessed: {name}")

    namespace = _load_final_main_functions(
        (
            "_dsf_v1_client_order_id_reservation_allows",
            "_dsf_v1_attempt_broker_stop_order",
        ),
        {
            "central_broker": BrokerAccessBomb(),
            "DISASTER_STOP_HEDGE_MODE_FIX_V1_VERSION": "test",
        },
    )
    attempt = namespace["_dsf_v1_attempt_broker_stop_order"]
    client_order_id = "FDS1-0123456789ABCDEF01234567"
    invalid_proofs = (
        None,
        {},
        {
            "client_order_id": "FDS1-FFFFFFFFFFFFFFFFFFFFFFFF",
            "client_order_id_unique": True,
            "send_allowed": True,
            "persistent": True,
            "reservation_state": "RESERVED_PRE_SEND",
        },
        {
            "client_order_id": client_order_id,
            "client_order_id_unique": False,
            "send_allowed": True,
            "persistent": True,
            "reservation_state": "RESERVED_PRE_SEND",
        },
    )

    for proof in invalid_proofs:
        result = attempt(
            "SOLUSDT",
            "LONG",
            0.13,
            75.924,
            client_order_id,
            client_order_id_reservation=proof,
        )
        assert result["status"] == "CLIENT_ORDER_ID_RESERVATION_REQUIRED"
        assert result["broker_called"] is False
        assert result["exchange_called"] is False
        assert result["sent"] is False
        assert result["attempts"] == []


def test_broker_sends_and_audits_the_exact_reserved_disaster_stop_id_once():
    client_order_id = "FDS1-0123456789ABCDEF01234567"
    reservation = {
        "status": "RESERVED_UNIQUE",
        "reservation_status": "RESERVED_UNIQUE",
        "reservation_state": "RESERVED_PRE_SEND",
        "persistent": True,
        "client_order_id": client_order_id,
        "client_order_id_reserved": True,
        "client_order_id_unique": True,
        "canonical_operation_id": "OP-STOP-1",
        "attempt_id": "ATTEMPT-STOP-1",
        "attempt_sequence": 0,
        "attempt_identity_hash": "HASH-STOP-1",
        "bot": "FALCON",
        "role": ROLE_INITIAL_DISASTER_STOP,
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:TEST-SOL-LONG",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "entry_client_order_id": "ENTRY-TEST-SOL-LONG",
        "entry_order_id": "ORDER-TEST-SOL-LONG",
        "stop_revision": 0,
        "order_type": "STOP_MARKET",
    }

    def verify(receipt, *, expected_client_order_id):
        valid = bool(receipt and expected_client_order_id == client_order_id)
        return {
            "ok": valid,
            "send_allowed": valid,
            "status": "RESERVED_UNIQUE"
            if valid
            else "CLIENT_ORDER_ID_RESERVATION_RECEIPT_INVALID",
            "persistent": valid,
            "client_order_id": expected_client_order_id,
            "client_order_id_reserved": valid,
            "client_order_id_unique": valid,
            "canonical_operation_id": receipt.get("canonical_operation_id")
            if receipt
            else None,
            "attempt_id": receipt.get("attempt_id") if receipt else None,
            "attempt_sequence": (
                receipt.get("attempt_sequence") if receipt else None
            ),
            "attempt_identity_hash": receipt.get("attempt_identity_hash")
            if receipt
            else None,
            "bot": receipt.get("bot") if receipt else None,
            "role": receipt.get("role") if receipt else None,
            "lifecycle_id": receipt.get("lifecycle_id") if receipt else None,
            "symbol": receipt.get("symbol") if receipt else None,
            "side": receipt.get("side") if receipt else None,
            "entry_client_order_id": (
                receipt.get("entry_client_order_id") if receipt else None
            ),
            "entry_order_id": (
                receipt.get("entry_order_id") if receipt else None
            ),
            "stop_revision": receipt.get("stop_revision") if receipt else None,
            "order_type": receipt.get("order_type") if receipt else None,
        }

    def claim(receipt, *, expected_client_order_id):
        verified = verify(receipt, expected_client_order_id=expected_client_order_id)
        return {
            **verified,
            "ok": verified["ok"],
            "send_allowed": verified["ok"],
            "send_claimed": verified["ok"],
            "status": "SEND_CLAIMED" if verified["ok"] else verified["status"],
            "attempt_disposition": (
                "SEND_CLAIMED" if verified["ok"] else None
            ),
        }

    class ExchangeProbe:
        def __init__(self):
            self.calls = []

        def create_order(self, *args):
            self.calls.append(args)
            return {
                "id": "STOP-ORDER-1",
                "status": "open",
                "clientOrderId": client_order_id,
                "symbol": "SOLUSDT",
                "side": "sell",
                "positionSide": "LONG",
                "type": "stop_market",
                "amount": 0.13,
                "stopPrice": 75.924,
            }

    exchange_probe = ExchangeProbe()
    audit_events = []
    namespace = _load_broker_functions(
        (
            "_managed_sanitize_exception_text",
            "_managed_exception_details",
            "validate_broker_client_order_id",
            "_broker_account_reservation_verification",
            "_broker_account_order_context",
            "_broker_returned_client_order_id",
            "_broker_material_disaster_stop_confirmation",
            "_create_order_with_reserved_attempt",
            "create_disaster_stop_order",
        ),
        {
            "BROKER_CLIENT_ORDER_ID_MAX_LENGTH": 32,
            "_BROKER_CLIENT_ORDER_ID_PATTERN": re.compile(r"^[A-Z0-9_-]+$"),
            "normalize_account_client_order_id": lambda value: str(value).strip().upper(),
            "verify_account_client_order_id_reservation": verify,
            "claim_account_client_order_send_authorization": claim,
            "record_account_client_order_attempt_outcome": (
                lambda receipt, *, outcome_state, **_details: {
                    "ok": True,
                    "status": outcome_state,
                    "client_order_id": (receipt or {}).get("client_order_id"),
                    "persistent": True,
                    "id_released": False,
                }
            ),
            "ROLE_ENTRY": "ENTRY",
            "ROLE_INITIAL_DISASTER_STOP": ROLE_INITIAL_DISASTER_STOP,
            "DISASTER_STOP_ENABLED": True,
            "_broker_factual_writes_enabled": lambda: True,
            "DISASTER_STOP_WORKING_TYPE": "MARK_PRICE",
            "normalize_symbol": lambda value: value,
            "normalize_side": lambda value: "buy" if str(value).upper() == "LONG" else "sell",
            "bingx_position_side": lambda value: str(value).upper(),
            "validate_disaster_stop_price": lambda *_args: {"ok": True},
            "_apply_disaster_stop_buffer": lambda _side, value: value,
            "_build_disaster_stop_hedge_mode_fix_payload": lambda *_args, **_kwargs: {
                "reduce_only_sent": False,
                "hedge_mode_detected": True,
                "reduce_only_removed_for_hedge_mode": True,
            },
            "bingx_api_symbol": lambda value: value,
            "exchange": lambda: exchange_probe,
            "agora_sp_str": lambda: "20/07/2026 12:00",
            "_set_last_disaster_stop_diagnostic": lambda **_kwargs: None,
            "log_execution_audit_event": lambda event: audit_events.append(event),
        },
    )
    create_stop = namespace["create_disaster_stop_order"]

    blocked = create_stop(
        symbol="SOLUSDT",
        side="LONG",
        amount=0.13,
        stop_loss_price=75.924,
        entry_price=76.212,
        client_order_id=client_order_id,
        client_order_id_unique=False,
        client_order_id_reservation_status="NOT_RESERVED",
    )
    assert blocked["status"] == "CLIENT_ORDER_ID_RESERVATION_RECEIPT_INVALID"
    assert blocked["send_attempted"] is False
    assert exchange_probe.calls == []

    result = create_stop(
        symbol="SOLUSDT",
        side="LONG",
        amount=0.13,
        stop_loss_price=75.924,
        entry_price=76.212,
        client_order_id=client_order_id,
        client_order_id_unique=True,
        client_order_id_reservation_status="CLIENT_ORDER_ID_RESERVED",
        client_order_id_reservation=reservation,
    )

    assert result["ok"] is True
    assert result["client_order_id"] == client_order_id
    assert result["client_order_id_unique"] is True
    assert result["stop_operationally_armed"] is True
    assert result["attempt_outcome_persistence_ok"] is True
    assert result["attempt_outcome_persistence"]["persistent"] is True
    assert result["reconciliation_required"] is False
    assert len(exchange_probe.calls) == 1
    assert exchange_probe.calls[0][-1]["clientOrderId"] == client_order_id
    assert audit_events[-1]["client_order_id"] == client_order_id


def test_disaster_stop_operational_armed_requires_all_returned_material_evidence():
    namespace = _load_broker_functions(
        ("_broker_material_disaster_stop_confirmation",),
        {},
    )
    confirm = namespace["_broker_material_disaster_stop_confirmation"]
    expected = {
        "expected_symbol": "SOL/USDT:USDT",
        "expected_close_side": "sell",
        "expected_position_side": "LONG",
        "expected_amount": 0.13,
        "expected_stop_price": 75.924,
        "entry_price": 76.212,
    }
    valid_order = {
        "id": "STOP-1",
        "symbol": "SOL-USDT",
        "side": "SELL",
        "positionSide": "LONG",
        "type": "MARKET",
        "amount": 0.13,
        "stopPrice": 75.924,
        "info": {
            "planType": "STOP_LOSS",
            "stopLossPrice": 75.924,
        },
    }

    valid = confirm(valid_order, **expected)
    assert valid["materially_valid"] is True
    assert valid["stop_loss_evidence_present"] is True
    assert valid["take_profit_evidence_present"] is False
    assert valid["failed_checks"] == []

    invalid_orders = {
        "missing_symbol": {**valid_order, "symbol": None},
        "wrong_close_side": {**valid_order, "side": "BUY"},
        "wrong_position_side": {**valid_order, "positionSide": "SHORT"},
        "quantity_mismatch": {**valid_order, "amount": 0.12},
        "wrong_trigger": {
            **valid_order,
            "stopPrice": 77.0,
            "info": {"planType": "STOP_LOSS", "stopLossPrice": 77.0},
        },
        "take_profit_conflict": {
            **valid_order,
            "info": {
                "planType": "TAKE_PROFIT",
                "stopLossPrice": 75.924,
                "takeProfitPrice": 80.0,
            },
        },
        "market_without_stop_evidence": {
            **valid_order,
            "stopPrice": None,
            "info": {},
        },
        "normalized_type_hides_take_profit_raw_type": {
            **valid_order,
            "type": "STOP_MARKET",
            "info": {
                "type": "TAKE_PROFIT",
                "planType": "STOP_LOSS",
                "stopLossPrice": 75.924,
            },
        },
        "symbol_conflicts_between_sources": {
            **valid_order,
            "info": {
                **valid_order["info"],
                "symbol": "BTCUSDT",
            },
        },
        "side_conflicts_between_sources": {
            **valid_order,
            "info": {
                **valid_order["info"],
                "side": "BUY",
            },
        },
        "quantity_conflicts_between_sources": {
            **valid_order,
            "info": {
                **valid_order["info"],
                "origQty": 0.12,
            },
        },
        "trigger_conflicts_between_sources": {
            **valid_order,
            "info": {
                "planType": "STOP_LOSS",
                "stopLossPrice": 75.924,
                "triggerPrice": 70.0,
            },
        },
    }
    for name, order in invalid_orders.items():
        result = confirm(order, **expected)
        assert result["materially_valid"] is False, name
        assert result["failed_checks"], name


def test_conflicting_returned_client_order_ids_never_match_reserved_identity():
    namespace = _load_broker_functions(
        ("_broker_returned_client_order_id",),
        {"normalize_account_client_order_id": lambda value: str(value).strip().upper()},
    )
    returned = namespace["_broker_returned_client_order_id"]

    assert returned(
        {
            "clientOrderId": "FDS1-0123456789ABCDEF01234567",
            "info": {"clientOrderID": "FDS1-89ABCDEF0123456789ABCDEF"},
        }
    ) is None


def test_unsafe_sent_entry_persists_before_one_managed_failsafe_and_is_idempotent():
    timeline = []
    incident_store = {}
    close_calls = []
    projection_expected = []
    health = {}
    close_client_order_id = "FEC1-0123456789ABCDEF01234567"

    class BrokerProbe:
        def __init__(self):
            self.position_side = "LONG"

        def managed_order_snapshot(self, symbol, order_id):
            timeline.append(("entry_snapshot", order_id))
            assert symbol == "SOLUSDT"
            return {
                "ok": True,
                "read_only": True,
                "sent": False,
                "order_id": "ENTRY-UNSAFE-1",
                "symbol": "SOLUSDT",
                "side": "BUY",
                "position_side": self.position_side,
                "status": "CLOSED",
                "raw_status": "FILLED",
                "amount": 0.13,
                "filled": 0.13,
                "remaining": 0.0,
            }

        def managed_close_position_market(self, **kwargs):
            timeline.append(("managed_close", kwargs["client_tag"]))
            close_calls.append(kwargs)
            return {
                "ok": True,
                "status": "MANAGED_CLOSE_CONFIRMED",
                "sent": True,
                "confirmed": True,
                "send_attempted": True,
                "send_outcome_unknown": False,
                "phase": "POST_CREATE_CONFIRMATION",
                "order_id": "FAILSAFE-CLOSE-1",
                "client_order_id": kwargs["client_tag"],
                "symbol": kwargs["symbol"],
                "side": kwargs["side"],
                "filled_amount": kwargs["amount"],
                "remaining_amount": 0.0,
            }

    broker_probe = BrokerProbe()

    def load_incident(incident_id):
        return {
            "ok": True,
            "incident": copy.deepcopy(incident_store.get(incident_id, {})),
        }

    def save_incident(incident_id, state):
        timeline.append(("persist", state.get("attempt_state")))
        incident_store[incident_id] = copy.deepcopy(state)
        return {"ok": True, "status": "INCIDENT_PERSISTED"}

    def project_close(result, **expected):
        projection_expected.append(expected)
        return dict(result)

    def issue_valid_management_token(pos, operation, extra=None):
        return {
            "ok": True,
            "token": "TEST-ONLY",
            "context": {
                "operation": operation,
                "symbol": pos.get("symbol"),
                "side": pos.get("side"),
                **dict(extra or {}),
            },
        }

    namespace = _load_final_functions(
        ("falcon_handle_unsafe_live_entry_identity",),
        {
            "hashlib": hashlib,
            "secrets": SimpleNamespace(token_hex=lambda _length: "OWNER-NONCE"),
            "HEALTH": health,
            "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE": "EMERGENCY_TERMINAL_STOP_CLOSE",
            "central_broker": broker_probe,
            "data_hora_sp_str": lambda: "21/07/2026 12:00",
            "normalize_symbol_for_central": lambda value: str(value or "")
            .upper()
            .replace("/", "")
            .replace(":USDT", ""),
            "_falcon_management_norm_side": lambda value: (
                "LONG"
                if str(value or "").upper() in {"LONG", "BUY"}
                else "SHORT"
                if str(value or "").upper() in {"SHORT", "SELL"}
                else str(value or "").upper()
            ),
            "_falcon_management_bool": lambda value: (
                value
                if isinstance(value, bool)
                else None
                if value in (None, "")
                else str(value).strip().lower() in {"1", "true", "yes", "on"}
            ),
            "safe_float": lambda value, default=None: (
                float(value) if value not in (None, "") else default
            ),
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
            "falcon_terminal_stop_recovery_load": load_incident,
            "falcon_terminal_stop_recovery_save": save_incident,
            "falcon_terminal_stop_lifecycle_lock_id": lambda _pos: "LIFECYCLE-LOCK-1",
            "falcon_terminal_stop_acquire_lifecycle_lock": (
                lambda lock_id, owner: {
                    "ok": True,
                    "acquired": True,
                    "status": "LIFECYCLE_LOCK_ACQUIRED",
                    "lock_id": lock_id,
                    "owner": owner,
                }
            ),
            "falcon_prepare_position_client_order_id": (
                lambda _pos, role, revision, attempt=0: {
                    "ok": True,
                    "send_allowed": True,
                    "persistent": True,
                    "status": "RESERVED_UNIQUE",
                    "client_order_id": close_client_order_id,
                    "role": role,
                    "revision": revision,
                    "attempt": attempt,
                }
            ),
            "falcon_issue_management_token": issue_valid_management_token,
            "_falcon_client_order_authority_projection": lambda value: dict(value),
            "_falcon_terminal_auth_projection": (
                lambda auth, context_matches: {
                    "ok": auth.get("ok"),
                    "context_matches": context_matches,
                }
            ),
            "_falcon_terminal_stop_result_projection": project_close,
            "_falcon_terminal_sanitize_projection": lambda value: copy.deepcopy(value),
            "_falcon_terminal_safe_text": lambda value, limit=240: (
                str(value)[:limit] if value not in (None, "") else None
            ),
            "record_event": lambda event, _sig, _extra: timeline.append(
                ("event", event)
            ),
        },
    )
    handle = namespace["falcon_handle_unsafe_live_entry_identity"]
    sig = {
        "id": "FALCON:FALCON15:SOLUSDT:LONG",
        "lifecycle_id": "LC-UNSAFE-1",
        "entry_client_order_id": "ENT1-EXPECTED",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
    }
    order = {
        "ok": False,
        "status": "CLIENT_ORDER_ID_RETURNED_MISMATCH",
        "sent": True,
        "entry_acknowledged": False,
        "order_id": "ENTRY-UNSAFE-1",
        "client_order_id": "ENT1-EXPECTED",
        "returned_client_order_id": None,
        "returned_client_order_id_matches": False,
        "reconciliation_required": True,
    }

    first = handle(sig, order)
    second = handle(sig, order)

    assert first["status"] == "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_CONFIRMED"
    assert first["failsafe_attempted"] is True
    assert first["entry_retry_blocked"] is True
    assert first["disaster_stop_binding_allowed"] is False
    assert first["reconciliation_required"] is True
    assert second["status"] == "LIVE_ENTRY_IDENTITY_UNSAFE_ALREADY_RECORDED"
    assert second["idempotent"] is True
    assert second["failsafe_attempted"] is False
    assert len(close_calls) == 1
    assert close_calls[0]["amount"] == 0.13
    assert close_calls[0]["expected_position_amount"] == 0.13
    assert close_calls[0]["client_tag"] == close_client_order_id
    assert timeline.index(("persist", "DETECTED")) < timeline.index(
        ("event", "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE")
    )
    assert timeline.index(("persist", "BROKER_CALL_PENDING")) < timeline.index(
        ("managed_close", close_client_order_id)
    )
    assert projection_expected == [
        {
            "expected_client_order_id": close_client_order_id,
            "expected_symbol": "SOLUSDT",
            "expected_side": "LONG",
            "expected_amount": 0.13,
        }
    ]
    assert sig["live_entry_identity_unsafe"] is True
    assert sig["entry_retry_blocked"] is True
    assert sig["reconciliation_required"] is True
    final_state = next(iter(incident_store.values()))
    assert final_state["attempt_state"] == "FAILSAFE_CONFIRMED"
    assert final_state["entry_sent"] is True
    assert final_state["send_attempted"] is True
    assert final_state["sent"] is True
    assert final_state["confirmed"] is True
    assert final_state["intended_client_order_id"] == "ENT1-EXPECTED"
    assert final_state["returned_client_order_id"] is None
    assert final_state["entry_order_snapshot"]["order_id"] == "ENTRY-UNSAFE-1"
    assert all(final_state["entry_order_snapshot_predicates"].values())
    assert "disaster_stop_order_id" not in final_state
    assert "disaster_stop_client_order_id" not in final_state

    mismatched_sig = {**sig, "lifecycle_id": "LC-UNSAFE-ACKED-MISMATCH"}
    mismatched_order = {
        **order,
        "entry_acknowledged": True,
        "returned_client_order_id": "ENT1-DIFFERENT",
        "returned_client_order_id_matches": False,
        "disaster_stop": {
            "stop_operationally_armed": True,
            "order_id": "UNSAFE-STOP-MUST-NOT-BIND",
        },
    }

    broker_probe.position_side = "BOTH"
    mismatched = handle(mismatched_sig, mismatched_order)

    assert mismatched["status"] == "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_CONFIRMED"
    assert len(close_calls) == 2
    mismatch_state = next(
        value
        for value in incident_store.values()
        if value.get("lifecycle_id") == "LC-UNSAFE-ACKED-MISMATCH"
    )
    assert mismatch_state["entry_acknowledged"] is True
    assert mismatch_state["returned_client_order_id_matches"] is False
    assert "disaster_stop_order_id" not in mismatch_state
    assert "disaster_stop_client_order_id" not in mismatch_state

    # A token with the wrong management context must never authorize the
    # fail-safe, even though the token string itself is present.
    namespace["falcon_issue_management_token"] = (
        lambda _pos, _operation, extra=None: {
            "ok": True,
            "token": "TEST-ONLY-WRONG-CONTEXT",
            "context": {
                "operation": "ENTRY_IDENTITY_UNSAFE_FAILSAFE_CLOSE",
                "symbol": "BTCUSDT",
                "side": "SHORT",
                **dict(extra or {}),
            },
        }
    )
    close_count_before_bad_auth = len(close_calls)
    bad_auth = handle(
        {**sig, "lifecycle_id": "LC-UNSAFE-BAD-AUTH"},
        mismatched_order,
    )

    assert bad_auth["status"] == "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_PRE_SEND_BLOCKED"
    assert bad_auth["failsafe_attempted"] is False
    assert len(close_calls) == close_count_before_bad_auth
    bad_auth_state = next(
        value
        for value in incident_store.values()
        if value.get("lifecycle_id") == "LC-UNSAFE-BAD-AUTH"
    )
    assert bad_auth_state["auth"]["context_matches"] is False

    namespace["falcon_issue_management_token"] = issue_valid_management_token
    close_count_before_missing_identity = len(close_calls)
    missing_identity_sig = {
        **sig,
        "lifecycle_id": "",
        "entry_client_order_id": "",
    }
    missing_identity_order = {
        **mismatched_order,
        "client_order_id": "",
        "client_tag": "",
    }
    missing_identity = handle(missing_identity_sig, missing_identity_order)

    assert missing_identity["status"] == "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_PRE_SEND_BLOCKED"
    assert missing_identity["failsafe_attempted"] is False
    assert len(close_calls) == close_count_before_missing_identity
    missing_identity_state = next(
        value
        for value in incident_store.values()
        if value.get("lifecycle_id") is None
        and value.get("intended_client_order_id") is None
    )
    assert missing_identity_state["auth"]["context_matches"] is False

    namespace["falcon_terminal_stop_recovery_load"] = lambda _incident_id: {
        "ok": False,
        "incident": {},
        "source": "READ_ERROR",
    }
    close_count_before_read_error = len(close_calls)
    read_blocked = handle(
        {**sig, "lifecycle_id": "LC-UNSAFE-READ-ERROR"},
        mismatched_order,
    )

    assert read_blocked["status"] == "LIVE_ENTRY_IDENTITY_INCIDENT_READ_BLOCKED"
    assert read_blocked["entry_retry_blocked"] is True
    assert read_blocked["failsafe_attempted"] is False
    assert len(close_calls) == close_count_before_read_error


def test_original_falcon_consumer_routes_sent_missing_client_id_to_unsafe_handler():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    definitions = [
        copy.deepcopy(node)
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "execute_signal_if_allowed"
    ]
    assert len(definitions) >= 2
    original = definitions[0]
    module = ast.Module(body=[original], type_ignores=[])
    ast.fix_missing_locations(module)
    handler_calls = []
    broker_calls = []

    class BrokerProbe:
        def __init__(self):
            self.acknowledged_mismatch = False

        def issue_execution_auth_token(self, **_kwargs):
            return {"ok": True, "token": "TEST-ONLY"}

        def place_market_order(self, **kwargs):
            broker_calls.append(kwargs)
            result = {
                "ok": False,
                "status": "CLIENT_ORDER_ID_RETURNED_MISSING",
                "sent": True,
                "entry_acknowledged": self.acknowledged_mismatch,
                "order_id": "ENTRY-UNSAFE-1",
                "client_order_id": kwargs["client_tag"],
                "returned_client_order_id": (
                    "ENT1-DIFFERENT" if self.acknowledged_mismatch else None
                ),
                "returned_client_order_id_matches": False,
                "reconciliation_required": True,
            }
            if self.acknowledged_mismatch:
                result["status"] = "CLIENT_ORDER_ID_RETURNED_MISMATCH"
                result["disaster_stop"] = {
                    "stop_operationally_armed": True,
                    "order_id": "UNSAFE-STOP-MUST-NOT-BIND",
                }
            return result

    broker_probe = BrokerProbe()

    namespace = {
        "FALCON_MODE": "LIVE",
        "FALCON_REAL_NOTIONAL_USDT": 10.0,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "ENABLE_REAL_TRADING": True,
        "BROKER_IMPORT_ERROR": None,
        "ROLE_ENTRY": "ENTRY",
        "HEALTH": {},
        "central_broker": broker_probe,
        "get_positions": lambda: {},
        "falcon_resolve_partial_capable_notional": lambda _sig: {
            "allowed": True,
            "notional_usdt": 10.0,
        },
        "safe_float": lambda value, default=0.0: (
            float(value) if value not in (None, "") else default
        ),
        "falcon_live_positions_count": lambda _positions: 0,
        "central_can_open_trade": lambda _sig, positions=None: {
            "allowed": True,
            "decision": "ALLOW",
            "reasons": [],
            "warnings": [],
        },
        "falcon_validate_position_ownership_limit_evidence": (
            lambda _decision, sig=None: {"ok": True, "evidence": {"known": True}}
        ),
        "falcon_prepare_canonical_client_order_id": lambda _identity: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": "ENT1-EXPECTED",
        },
        "falcon_prepare_initial_disaster_stop_client_order_id": (
            lambda **_identity: {"send_allowed": True}
        ),
        "falcon_handle_unsafe_live_entry_identity": (
            lambda sig, order: handler_calls.append((sig, order))
            or {
                "ok": True,
                "status": "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_CONFIRMED",
                "reconciliation_required": True,
            }
        ),
        "hashlib": hashlib,
        "json": json,
    }
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    sig = {
        "id": "SIGNAL-1",
        "lifecycle_id": "LC-UNSAFE-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "stop": 75.924,
    }

    allowed, decision = namespace["execute_signal_if_allowed"](sig, positions={})

    assert allowed is False
    assert decision["status"] == "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE"
    assert decision["reconciliation_required"] is True
    assert len(broker_calls) == 1
    assert len(handler_calls) == 1
    assert sig["live_order"]["sent"] is True
    assert sig["live_order_id"] == "ENTRY-UNSAFE-1"
    assert "disaster_stop" not in sig["live_order"]

    # An internally inconsistent payload must still take the unsafe path when
    # the explicit returned-ID predicate is false, even if ACK/stop flags say
    # true.  The consumer preserves the raw facts but binds no stop ownership.
    broker_probe.acknowledged_mismatch = True
    mismatched_sig = {
        **sig,
        "id": "SIGNAL-2",
        "lifecycle_id": "LC-UNSAFE-2",
    }
    mismatched_sig.pop("live_order", None)
    mismatched_sig.pop("live_order_id", None)
    mismatched_sig.pop("bingx_order_id", None)

    allowed, decision = namespace["execute_signal_if_allowed"](
        mismatched_sig, positions={}
    )

    assert allowed is False
    assert decision["status"] == "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE"
    assert len(broker_calls) == 2
    assert len(handler_calls) == 2
    assert handler_calls[-1][1]["entry_acknowledged"] is True
    assert handler_calls[-1][1]["returned_client_order_id_matches"] is False
    assert "disaster_stop_order_id" not in mismatched_sig
    assert "disaster_stop_client_order_id" not in mismatched_sig

    wrapper_node = definitions[-1]
    wrapper_module = ast.Module(body=[wrapper_node], type_ignores=[])
    ast.fix_missing_locations(wrapper_module)
    sync_calls = []
    wrapper_namespace = {
        "_ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1": namespace[
            "execute_signal_if_allowed"
        ],
        "falcon_sync_live_order_state": (
            lambda wrapped_sig, wrapped_order: sync_calls.append(
                (wrapped_sig, wrapped_order)
            )
        ),
        "HEALTH": namespace["HEALTH"],
    }
    exec(compile(wrapper_module, str(FALCON_SOURCE), "exec"), wrapper_namespace)
    wrapped_sig = {
        **mismatched_sig,
        "id": "SIGNAL-3",
        "lifecycle_id": "LC-UNSAFE-3",
    }
    wrapped_sig.pop("live_order", None)
    wrapped_sig.pop("live_order_id", None)
    wrapped_sig.pop("bingx_order_id", None)

    allowed, decision = wrapper_namespace["execute_signal_if_allowed"](
        wrapped_sig, positions={}
    )

    assert allowed is False
    assert decision["status"] == "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE"
    assert sync_calls == []
    assert "disaster_stop_order_id" not in wrapped_sig
    assert "disaster_stop_client_order_id" not in wrapped_sig
