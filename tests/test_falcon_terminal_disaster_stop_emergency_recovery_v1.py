from __future__ import annotations

import ast
import copy
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from account_client_order_id import (
    authorize_account_client_order_next_attempt,
    record_account_client_order_attempt_outcome,
    reserve_account_client_order_attempt,
)
from falcon_client_order_id import (
    ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
    canonical_falcon_order_identity,
    generate_falcon_client_order_id,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"


def _load_final_functions(names: tuple[str, ...], globals_dict: dict) -> dict:
    """Compile selected final definitions without importing Falcon's runtime."""
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


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _position(**updates):
    pos = {
        "id": "FALCON15:SOLUSDT:LONG",
        "trade_registry_id": "TRADE-1",
        "lifecycle_id": "LIFECYCLE-1",
        "live_order_id": "ENTRY-1",
        "live_client_order_id": "CLIENT-1",
        "broker_stop_order_id": "STOP-1",
        "disaster_stop_order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "entry": 76.212,
        "stop": 75.924,
        "initial_stop": 75.924,
        "tp50": 76.50,
        "qty": 0.13,
        "initial_qty": 0.13,
        "remaining_qty": 0.13,
        "broker_stop_amount": 0.13,
        "broker_stop_price": 75.924,
        "broker_stop_symbol": "SOLUSDT",
        "broker_stop_side": "SELL",
        "broker_stop_type": "STOP_MARKET",
        "broker_stop_position_side": "LONG",
        "broker_stop_reduce_only": False,
        "broker_stop_hedge_mode_detected": True,
        "broker_stop_trigger_type": "MARK_PRICE",
        "live_order": {
            "sent": True,
            "order_id": "ENTRY-1",
            "client_order_id": "CLIENT-1",
            "disaster_stop": {
                "order_id": "STOP-1",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "type": "STOP_MARKET",
                "position_side": "LONG",
                "amount": 0.13,
                "stop_price": 75.924,
            },
        },
    }
    pos.update(updates)
    return pos


def _registry_row(**updates):
    row = {
        "bot": "FALCON",
        "trade_id": "TRADE-1",
        "lifecycle_id": "LIFECYCLE-1",
        "client_order_id": "CLIENT-1",
        "broker_order_id": "ENTRY-1",
        "broker_stop_order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "status": "OPEN",
    }
    row.update(updates)
    return row


def _registry_snapshot(*extra_rows):
    rows = {"primary": _registry_row()}
    for index, row in enumerate(extra_rows):
        rows[f"extra-{index}"] = row
    return {"open_trades": rows, "closed_trades": []}


def _verification(**updates):
    verification = {
        "ok": False,
        "cached": False,
        "management_allowed": False,
        "status": "DISASTER_STOP_TERMINAL_WITH_POSITION_OPEN",
        "stop_order_id": "STOP-1",
        "stop_order_status": "CANCELED",
        "order_snapshot": {
            "ok": True,
            "read_only": True,
            "order_id": "STOP-1",
            "raw_status": "FAILED",
            "status": "CANCELED",
            "executed_quantity": 0.0,
            "remaining_quantity": 0.13,
            "failure_code": "TRIGGER_FAILED",
            "failure_reason": "terminal stop failed",
            "fills": [],
        },
        "entry_order_snapshot": {
            "ok": True,
            "read_only": True,
            "order_id": "ENTRY-1",
            "client_order_id": "CLIENT-1",
            "symbol": "SOLUSDT",
            "side": "BUY",
            "raw_status": "FILLED",
            "status": "CLOSED",
            "executed_quantity": 0.13,
            "remaining_quantity": 0.0,
        },
        "position_snapshot": {
            "ok": True,
            "read_only": True,
            "position_closed": False,
            "amount": 0.13,
            "symbol": "SOLUSDT",
            "side": "LONG",
            "ownership_safe": True,
            "matched_count": 1,
            "positions": [
                {"symbol": "SOLUSDT", "side": "LONG", "amount": 0.13}
            ],
        },
    }
    verification.update(updates)
    return verification


def _canceled_verification(**updates):
    verification = _verification()
    verification["stop_order_status"] = "CANCELED"
    verification["order_snapshot"]["raw_status"] = "CANCELED"
    verification["order_snapshot"]["status"] = "CANCELED"
    verification.update(updates)
    return verification


class _BrokerProbe:
    def __init__(self, result=None, open_orders_result=None):
        self.result = result or {
            "ok": True,
            "status": "MANAGED_CLOSE_CONFIRMED",
            "send_attempted": True,
            "sent": True,
            "confirmed": True,
            "send_outcome_unknown": False,
            "phase": "POST_CREATE_CONFIRMATION",
            "order_id": "EMERGENCY-CLOSE-1",
            "filled_amount": 0.13,
            "remaining_amount": 0.0,
            "average": 75.924,
        }
        self.calls = []
        self.open_orders_calls = []
        self.open_orders_result = open_orders_result or {
            "ok": True,
            "status": "OPEN_ORDERS_SNAPSHOT_OK",
            "read_only": True,
            "sent": False,
            "orders": [],
            "count": 0,
        }

    def managed_close_position_market(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if isinstance(self.result, BaseException):
            raise self.result
        result = copy.deepcopy(self.result)
        result.setdefault("client_order_id", kwargs.get("client_tag"))
        result.setdefault("symbol", kwargs.get("symbol"))
        result.setdefault("side", kwargs.get("side"))
        if result.get("sent") is True:
            result.setdefault("send_outcome_unknown", False)
            result.setdefault("phase", "POST_CREATE_CONFIRMATION")
        elif result.get("sent") is False:
            result.setdefault("send_outcome_unknown", False)
            result.setdefault("phase", "PRE_SEND_SETUP")
        elif result.get("sent") is None:
            result.setdefault("send_outcome_unknown", True)
        return result

    def managed_open_orders_snapshot(self, symbol):
        self.open_orders_calls.append(symbol)
        return copy.deepcopy(self.open_orders_result)


class _RedisNxProbe:
    def __init__(self, barrier=None):
        self.values = {}
        self.barrier = barrier
        self.lock = threading.Lock()
        self.authoritative_get_calls = []

    def set(self, key, value, nx=False):
        if nx and self.barrier is not None:
            self.barrier.wait(timeout=5)
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    def get(self, key):
        with self.lock:
            self.authoritative_get_calls.append(key)
            return self.values.get(key)

    def eval(self, script, keys=None, args=None):
        with self.lock:
            key = list(keys or [])[0]
            owner = list(args or [])[0]
            if self.values.get(key) != owner:
                return 0
            self.values.pop(key, None)
            return 1


class _LegacyRaceBroker(_BrokerProbe):
    def __init__(self):
        super().__init__({
            "ok": True,
            "status": "MANAGED_CLOSE_SENT_UNCONFIRMED",
            "phase": "POST_CREATE_CONFIRMATION",
            "send_attempted": True,
            "sent": True,
            "confirmed": False,
            "send_outcome_unknown": False,
            "order_id": "ONLY-MARKET-CLOSE",
            "filled_amount": 0.0,
            "remaining_amount": 0.13,
        })
        self.cancel_calls = []
        self.position_calls = []

    def cancel_managed_stop_order(self, symbol, order_id, **kwargs):
        self.cancel_calls.append((symbol, order_id, copy.deepcopy(kwargs)))
        return {"ok": True, "status": "CANCEL_CONFIRMED", "order_id": order_id}

    def managed_position_snapshot(self, symbol, side, expected_amount=None):
        self.position_calls.append((symbol, side, expected_amount))
        return {
            "ok": True,
            "read_only": True,
            "position_closed": False,
            "ownership_safe": True,
            "amount": 0.13,
            "symbol": symbol,
            "side": side,
            "matched_count": 1,
        }

    def managed_order_snapshot(self, symbol, order_id):
        return {
            "ok": True,
            "read_only": True,
            "status": "CANCELED",
            "order_id": order_id,
            "filled": 0.0,
        }


def _load_real_lifecycle_lock_functions(redis_probe):
    namespace = _load_final_functions(
        (
            "_falcon_terminal_safe_text",
            "falcon_terminal_stop_acquire_lifecycle_lock",
            "falcon_terminal_stop_release_lifecycle_lock",
        ),
        {
            "json": json,
            "redis": redis_probe,
            "redis_lock": threading.RLock(),
            "bandwidth_redis_set_if_absent": (
                lambda client, key, value, caller=None: client.set(
                    key,
                    value,
                    nx=True,
                )
            ),
            "bandwidth_redis_get_authoritative": (
                lambda client, key, caller=None: client.get(key)
            ),
            "bandwidth_redis_compare_and_delete": (
                lambda client, key, owner, caller=None: bool(
                    client.eval("atomic", keys=[key], args=[owner])
                )
            ),
            "data_hora_sp_str": lambda: "20/07/2026 12:00",
            "FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX": "test:terminal-stop-lifecycle-lock",
        },
    )
    return (
        namespace["falcon_terminal_stop_acquire_lifecycle_lock"],
        namespace["falcon_terminal_stop_release_lifecycle_lock"],
    )


_FUNCTIONS = (
    "falcon_is_live_real_position",
    "falcon_real_remaining_qty",
    "_falcon_management_norm_symbol",
    "_falcon_management_norm_side",
    "falcon_position_identity",
    "falcon_position_client_order_identity",
    "falcon_generate_position_client_order_id",
    "falcon_authorize_position_client_order_retry",
    "falcon_record_client_order_attempt_outcome",
    "_falcon_client_order_authority_projection",
    "_falcon_prune_timestamped_map",
    "_falcon_management_bool",
    "_falcon_stop_creation_evidence",
    "_falcon_terminal_safe_text",
    "_falcon_terminal_sanitize_projection",
    "_falcon_terminal_registry_field",
    "_falcon_terminal_bool",
    "falcon_terminal_stop_incident_id",
    "falcon_terminal_stop_client_tag",
    "falcon_terminal_stop_recovery_key",
    "falcon_terminal_stop_recovery_load",
    "falcon_terminal_stop_recovery_save",
    "falcon_terminal_stop_lifecycle_lock_id",
    "_falcon_terminal_registry_evidence",
    "_falcon_terminal_stop_facts",
    "_falcon_terminal_replacement_evidence",
    "_falcon_terminal_active_replacement_orders",
    "falcon_terminal_stop_emergency_decision",
    "_falcon_terminal_stop_creation_projection",
    "_falcon_terminal_stop_result_projection",
    "_falcon_terminal_pre_send_not_sent_proven",
    "falcon_terminal_stop_critical_alert",
    "_falcon_terminal_auth_projection",
    "falcon_handle_terminal_stop_emergency",
)


class _Harness:
    RECOVERY_KEY = "falcon:terminal_stop_emergency_recovery:v1"

    def __init__(
        self,
        *,
        backend=None,
        broker_result=None,
        open_orders_result=None,
        auth_allowed=True,
        auth_token="TEST-AUTH",
        auth_context_updates=None,
        persistence_ack=True,
        persistence_fail_states=None,
        lifecycle_lock_acquired=True,
        lifecycle_locks=None,
        account_authority=None,
        final_verification=None,
        final_mutator=None,
    ):
        self.backend = {} if backend is None else backend
        self.broker = _BrokerProbe(broker_result, open_orders_result=open_orders_result)
        self.auth_allowed = auth_allowed
        self.auth_token = auth_token
        self.auth_context_updates = dict(auth_context_updates or {})
        self.persistence_ack = persistence_ack
        self.persistence_fail_states = {
            str(state or "").upper().strip()
            for state in (persistence_fail_states or set())
        }
        self.lifecycle_lock_acquired = lifecycle_lock_acquired
        self.lifecycle_locks = lifecycle_locks or _RedisNxProbe()
        self.account_authority = account_authority or _RedisNxProbe()
        self.final_verification = copy.deepcopy(final_verification)
        self.final_mutator = final_mutator
        self._next_final_verification = None
        self.alert_calls = []
        self.event_calls = []
        self.registry_write_calls = []
        self.auth_calls = []
        self.lifecycle_lock_calls = []
        self.lifecycle_lock_release_calls = []
        self.final_verification_calls = []
        self.operation_log = []
        self.health = {}

        def redis_get(_redis, key, caller=None, no_cache=False):
            if str(key).startswith(self.RECOVERY_KEY):
                return self.backend.get(key)
            return self.account_authority.get(key)

        def redis_set_if_absent(_redis, key, value, caller=None):
            return self.account_authority.set(key, value, nx=True)

        def redis_set(_redis, key, value, caller=None):
            attempt_state = None
            try:
                payload = json.loads(value) if isinstance(value, str) else value
                incident = (
                    payload.get("incident")
                    if isinstance(payload, dict)
                    and isinstance(payload.get("incident"), dict)
                    else {}
                )
                attempt_state = str(incident.get("attempt_state") or "").upper().strip() or None
            except Exception:
                attempt_state = None
            acknowledged = bool(
                self.persistence_ack
                and (attempt_state or "") not in self.persistence_fail_states
            )
            self.operation_log.append({
                "operation": "PERSIST",
                "attempt_state": attempt_state,
                "acknowledged": acknowledged,
            })
            if not acknowledged:
                return False
            self.backend[key] = value
            return True

        def issue_token(pos, operation, extra=None):
            self.auth_calls.append((copy.deepcopy(pos), operation, copy.deepcopy(extra)))
            if self.auth_allowed:
                context = {
                    "bot": "FALCON",
                    "setup": pos.get("setup"),
                    "symbol": pos.get("symbol"),
                    "side": pos.get("side"),
                    "operation": operation,
                    "trade_id": pos.get("trade_registry_id") or pos.get("id"),
                }
                context.update(copy.deepcopy(extra or {}))
                context.update(copy.deepcopy(self.auth_context_updates))
                return {
                    "ok": True,
                    "status": "AUTH_ISSUED",
                    "token": self.auth_token,
                    "context": context,
                }
            return {"ok": False, "status": "AUTH_BLOCKED", "token": None}

        def acquire_lifecycle_lock(lifecycle_lock_id, owner_nonce):
            self.lifecycle_lock_calls.append((lifecycle_lock_id, owner_nonce))
            key = f"test:lifecycle-lock:{lifecycle_lock_id}"
            acquired = bool(
                self.lifecycle_lock_acquired
                and self.lifecycle_locks.set(key, owner_nonce, nx=True)
            )
            return {
                "ok": acquired,
                "acquired": acquired,
                "status": (
                    "LIFECYCLE_LOCK_ACQUIRED"
                    if acquired
                    else "LIFECYCLE_LOCK_ALREADY_EXISTS"
                ),
                "authoritative_lock_present": not acquired,
            }

        def release_lifecycle_lock(lifecycle_lock_id, owner_nonce):
            persisted_attempt_states = []
            for key, raw in self.backend.items():
                if ":incident:" not in str(key):
                    continue
                try:
                    payload = json.loads(raw) if isinstance(raw, str) else raw
                    incident = payload.get("incident") if isinstance(payload, dict) else {}
                    persisted_attempt_states.append(
                        str((incident or {}).get("attempt_state") or "").upper().strip()
                        or None
                    )
                except Exception:
                    persisted_attempt_states.append(None)
            self.operation_log.append({
                "operation": "RELEASE",
                "persisted_attempt_state": (
                    persisted_attempt_states[-1] if persisted_attempt_states else None
                ),
            })
            self.lifecycle_lock_release_calls.append((lifecycle_lock_id, owner_nonce))
            key = f"test:lifecycle-lock:{lifecycle_lock_id}"
            released = bool(self.lifecycle_locks.eval("atomic", keys=[key], args=[owner_nonce]))
            return {
                "ok": released,
                "released": released,
                "status": "LIFECYCLE_LOCK_RELEASED" if released else "LIFECYCLE_LOCK_OWNERSHIP_MISMATCH",
            }

        def refresh_verification(pos, force=False, persist_registry=True):
            self.final_verification_calls.append({
                "force": force,
                "persist_registry": persist_registry,
            })
            if callable(self.final_mutator):
                self.final_mutator(pos)
            selected = (
                self.final_verification
                if isinstance(self.final_verification, dict)
                else self._next_final_verification
            )
            return copy.deepcopy(selected or _verification())

        def send_telegram(message, **kwargs):
            self.alert_calls.append((message, copy.deepcopy(kwargs)))
            return True

        def record_event(event_type, pos, extra=None):
            self.event_calls.append((event_type, copy.deepcopy(pos), copy.deepcopy(extra)))
            return {"event_type": event_type}

        def registry_write(pos, **updates):
            self.registry_write_calls.append((copy.deepcopy(pos), copy.deepcopy(updates)))
            return {"ok": True, "status": "MOCKED_REGISTRY_UPDATE"}

        def prepare_position_client_order_id(pos, role, revision, attempt=0):
            identity = self.ns["falcon_position_client_order_identity"](
                pos, role, revision, attempt=attempt
            )
            canonical = canonical_falcon_order_identity(**identity)
            account_identity = {
                key: canonical.get(key)
                for key in (
                    "account_namespace", "bot", "role", "lifecycle_id",
                    "symbol", "side", "attempt_id", "attempt_sequence",
                    "canonical_operation_id", "entry_client_order_id",
                    "entry_order_id", "stop_revision", "order_type",
                )
            }
            client_order_id = generate_falcon_client_order_id(**identity)
            result = reserve_account_client_order_attempt(
                account_identity,
                client_order_id=client_order_id,
                redis_client=self.account_authority,
                set_if_absent=(
                    lambda client, key, value, caller=None: client.set(
                        key, value, nx=True
                    )
                ),
                get_authoritative=(
                    lambda client, key, caller=None: client.get(key)
                ),
                now=lambda: "2026-07-20T12:00:00+00:00",
            )
            return {
                **dict(result or {}),
                "role": canonical.get("role"),
                "identity_hash": (result or {}).get("attempt_identity_hash"),
                "revision": canonical.get("revision"),
                "attempt": canonical.get("attempt"),
                "same_identity": (result or {}).get("same_attempt") is True,
            }

        globals_dict = {
            "hashlib": hashlib,
            "json": json,
            "threading": threading,
            "time": time,
            "safe_float": _safe_float,
            "central_broker": self.broker,
            "central_trade_registry": None,
            "redis": SimpleNamespace(),
            "redis_lock": threading.RLock(),
            "terminal_stop_recovery_lock": threading.RLock(),
            "position_mutation_lock": threading.RLock(),
            "bandwidth_redis_get": redis_get,
            "bandwidth_redis_get_authoritative": redis_get,
            "bandwidth_redis_set": redis_set,
            "bandwidth_redis_set_if_absent": redis_set_if_absent,
            "data_hora_sp_str": lambda: "20/07/2026 12:00",
            "safe_send_telegram": send_telegram,
            "record_event": record_event,
            "falcon_update_registry_management": registry_write,
            "falcon_issue_management_token": issue_token,
            "falcon_terminal_stop_acquire_lifecycle_lock": acquire_lifecycle_lock,
            "falcon_terminal_stop_release_lifecycle_lock": release_lifecycle_lock,
            "falcon_verify_live_disaster_stop": refresh_verification,
            "falcon_prepare_position_client_order_id": prepare_position_client_order_id,
            "authorize_account_client_order_next_attempt": authorize_account_client_order_next_attempt,
            "record_account_client_order_attempt_outcome": record_account_client_order_attempt_outcome,
            "canonical_falcon_order_identity": canonical_falcon_order_identity,
            "generate_falcon_client_order_id": generate_falcon_client_order_id,
            "ROLE_EMERGENCY_TERMINAL_STOP_CLOSE": ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
            "HEALTH": self.health,
            "secrets": SimpleNamespace(token_hex=lambda _size: uuid.uuid4().hex),
            "datetime": __import__("datetime").datetime,
            "timezone": __import__("datetime").timezone,
            "FALCON_MANAGEMENT_FAILSAFE_ENABLED": True,
            "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-10,
            "FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION": (
                "2026-07-20-FALCON-TERMINAL-STOP-EMERGENCY-RECOVERY-V1"
            ),
            "FALCON_TERMINAL_STOP_STATUSES": {
                "FAILED",
                "REJECTED",
                "EXPIRED",
                "CANCELED",
                "CANCELLED",
            },
            "FALCON_TERMINAL_STOP_UNRESOLVED_STATES": {
                "RESERVED",
                "SEND_ATTEMPTED",
                "BROKER_CALL_PENDING",
                "LIFECYCLE_LOCK_BLOCKED",
                "SEND_OUTCOME_UNKNOWN",
                "SENT_UNCONFIRMED",
                "CONFIRMED",
            },
            "FALCON_TERMINAL_STOP_RECOVERY_KEY": self.RECOVERY_KEY,
            "FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX": "test:lifecycle-lock",
            "__name__": "falcon_terminal_recovery_test_harness",
        }
        self.ns = _load_final_functions(_FUNCTIONS, globals_dict)

    def decision(self, pos=None, verification=None, registry=None, existing=None):
        return self.ns["falcon_terminal_stop_emergency_decision"](
            _position() if pos is None else pos,
            _verification() if verification is None else verification,
            registry_snapshot=_registry_snapshot() if registry is None else registry,
            existing_recovery={} if existing is None else existing,
        )

    def handle(self, pos=None, verification=None, registry=None):
        pos = _position() if pos is None else pos
        selected_verification = _verification() if verification is None else verification
        self._next_final_verification = copy.deepcopy(selected_verification)
        return self.ns["falcon_handle_terminal_stop_emergency"](
            pos.get("id", "PID-1"),
            pos,
            selected_verification,
            registry_snapshot=_registry_snapshot() if registry is None else registry,
        )

    def incident_id(self, pos=None, verification=None):
        return self.ns["falcon_terminal_stop_incident_id"](
            _position() if pos is None else pos,
            _verification() if verification is None else verification,
        )

    def seed_incident(self, state, pos=None, verification=None):
        incident_id = self.incident_id(pos, verification)
        key = self.ns["falcon_terminal_stop_recovery_key"](incident_id)
        payload = {
            "version": "test",
            "updated_at": "20/07/2026 12:00",
            "incident_id": incident_id,
            "incident": {
                "incident_id": incident_id,
                "updated_epoch": time.time(),
                **state,
            },
        }
        self.backend[key] = json.dumps(payload)
        return incident_id

    def persisted_incident(self, incident_id):
        key = self.ns["falcon_terminal_stop_recovery_key"](incident_id)
        payload = json.loads(self.backend[key])
        return payload["incident"]


def _assert_terminal_state_persisted_before_release(harness, expected_state):
    expected_state = str(expected_state).upper()
    persisted_indexes = [
        index
        for index, operation in enumerate(harness.operation_log)
        if operation.get("operation") == "PERSIST"
        and operation.get("attempt_state") == expected_state
        and operation.get("acknowledged") is True
    ]
    release_indexes = [
        index
        for index, operation in enumerate(harness.operation_log)
        if operation.get("operation") == "RELEASE"
    ]
    assert persisted_indexes, harness.operation_log
    assert release_indexes, harness.operation_log
    assert persisted_indexes[-1] < release_indexes[0], harness.operation_log
    assert (
        harness.operation_log[release_indexes[0]]["persisted_attempt_state"]
        == expected_state
    )


def _decoded_account_authority_records(harness):
    records = []
    for raw in harness.account_authority.values.values():
        try:
            decoded = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if isinstance(decoded, dict):
            records.append(decoded)
    return records


def _load_legacy_stop_cross(harness, broker, closed_calls):
    namespace = dict(harness.ns)
    namespace.update({
        "central_broker": broker,
        "FALCON_MANAGEMENT_STOP_GRACE_SECONDS": 0,
        "_falcon_stop_status_flags": lambda *_args, **_kwargs: {
            "cancelled": False,
            "rejected": False,
            "filled": False,
        },
        "_falcon_stop_not_found_evidence": lambda *_args, **_kwargs: False,
        "_falcon_protective_stop_evidence": lambda *_args, **_kwargs: {
            "protective": True,
        },
        "record_event": lambda *_args, **_kwargs: {},
        "close_position": lambda *args, **kwargs: closed_calls.append((args, kwargs)),
        "safe_send_telegram": lambda *_args, **_kwargs: False,
    })
    return _load_final_functions(
        ("falcon_handle_live_stop_cross",),
        namespace,
    )["falcon_handle_live_stop_cross"]


def test_failed_zero_fill_open_position_is_eligible_and_raw_status_is_authoritative():
    harness = _Harness()

    result = harness.decision()

    assert result["incident_detected"] is True
    assert result["eligible"] is True
    assert result["status"] == "TERMINAL_STOP_EMERGENCY_ALLOWED"
    assert result["stop"]["terminal_status"] == "FAILED"
    assert result["stop"]["executed_quantity"] == 0.0
    assert result["broker_qty"] == pytest.approx(0.13)
    assert result["reasons"] == []


def test_generic_management_or_ownership_block_status_does_not_hide_exact_evidence():
    verification = _verification(
        management_allowed=False,
        status="DISASTER_STOP_OWNERSHIP_BLOCKED",
        ownership_verified=False,
    )

    result = _Harness().decision(verification=verification)

    assert result["incident_detected"] is True
    assert result["eligible"] is True
    assert result["normal_management_allowed"] is False


def test_symbol_and_side_only_identity_is_fail_closed():
    pos = _position(
        trade_registry_id=None,
        lifecycle_id=None,
        live_order_id=None,
        live_client_order_id=None,
        broker_stop_order_id=None,
        disaster_stop_order_id=None,
        live_order={"sent": False},
    )

    verification = _verification(stop_order_id=None)
    result = _Harness().decision(
        pos=pos,
        verification=verification,
        registry={"open_trades": {}},
    )

    assert result["eligible"] is False
    assert {
        "FALCON_LIVE_REAL_POSITION_REQUIRED",
        "LIFECYCLE_ID_REQUIRED",
        "CLIENT_ORDER_ID_REQUIRED",
        "ENTRY_ORDER_ID_REQUIRED",
        "DISASTER_STOP_ORDER_ID_REQUIRED",
    }.issubset(set(result["reasons"]))


def test_lifecycle_mismatch_is_fail_closed():
    registry = _registry_snapshot(_registry_row(lifecycle_id="OTHER-LIFECYCLE"))
    registry["open_trades"].pop("primary")

    result = _Harness().decision(registry=registry)

    assert result["incident_detected"] is True
    assert result["eligible"] is False
    assert "OPEN_FALCON_LIFECYCLE_MATCH_NOT_UNIQUE" in result["reasons"]


def test_entry_order_mismatch_is_fail_closed():
    verification = _verification()
    verification["entry_order_snapshot"]["order_id"] = "ENTRY-OTHER"

    result = _Harness().decision(verification=verification)

    assert result["incident_detected"] is True
    assert result["eligible"] is False
    assert "ENTRY_BROKER_ORDER_ID_NOT_EXACT" in result["reasons"]


def test_stop_identity_mismatch_is_fail_closed():
    registry = _registry_snapshot()
    registry["open_trades"]["primary"]["broker_stop_order_id"] = "STOP-OTHER"

    result = _Harness().decision(registry=registry)

    assert result["incident_detected"] is True
    assert result["eligible"] is False
    assert "REGISTRY_STOP_ORDER_ID_MISMATCH" in result["reasons"]


def test_broker_quantity_greater_than_falcon_quantity_blocks_manual_aggregation_risk():
    verification = _verification()
    verification["position_snapshot"]["amount"] = 0.20
    verification["position_snapshot"]["positions"][0]["amount"] = 0.20
    verification["entry_order_snapshot"]["executed_quantity"] = 0.20

    result = _Harness().decision(verification=verification)

    assert result["incident_detected"] is True
    assert result["eligible"] is False
    assert "BROKER_QTY_EXCEEDS_FALCON_QTY_POSSIBLE_MANUAL_AGGREGATION" in result["reasons"]


def test_manual_or_external_position_on_same_leg_blocks():
    verification = _verification()
    verification["position_snapshot"]["positions"].append(
        {
            "symbol": "SOLUSDT",
            "side": "LONG",
            "amount": 0.01,
            "ownership": "MANUAL",
            "manual_position": True,
        }
    )

    result = _Harness().decision(verification=verification)

    assert result["incident_detected"] is True
    assert result["eligible"] is False
    assert "MANUAL_OR_EXTERNAL_POSITION_AGGREGATION_RISK" in result["reasons"]


def test_manual_position_on_another_symbol_does_not_block_exact_leg():
    external_other_symbol = _registry_row(
        bot="EXTERNAL",
        trade_id="MANUAL-BTC",
        lifecycle_id="MANUAL-BTC-LC",
        client_order_id=None,
        broker_order_id=None,
        broker_stop_order_id=None,
        symbol="BTCUSDT",
        side="LONG",
        execution_mode="EXTERNAL",
        registry_mode="EXTERNAL",
        external_position=True,
    )

    result = _Harness().decision(
        registry=_registry_snapshot(external_other_symbol)
    )

    assert result["incident_detected"] is True
    assert result["eligible"] is True
    assert "MANUAL_OR_EXTERNAL_POSITION_AGGREGATION_RISK" not in result["reasons"]


@pytest.mark.parametrize(
    "extra_row",
    [
        _registry_row(
            bot="TURTLE", lifecycle_id="TURTLE-PAPER-1",
            execution_mode="PAPER", registry_mode="PAPER",
        ),
        _registry_row(
            bot="FALCON", lifecycle_id="FALCON-PAPER-1",
            execution_mode="PAPER", registry_mode="PAPER",
        ),
        _registry_row(
            bot="FALCON", lifecycle_id="FALCON-VERIFY-1",
            execution_mode="VERIFY", registry_mode="VERIFY",
        ),
    ],
)
def test_virtual_or_advisory_same_leg_registry_rows_do_not_block(extra_row):
    result = _Harness().decision(registry=_registry_snapshot(extra_row))

    assert result["eligible"] is True
    assert result["registry"]["same_leg_other_record_count"] == 0
    assert result["registry"]["ignored_same_leg_record_count"] == 1
    assert "MANUAL_OR_EXTERNAL_POSITION_AGGREGATION_RISK" not in result["reasons"]


def test_other_live_real_lifecycle_on_same_leg_is_factual_conflict():
    other = _registry_row(
        bot="TURTLE", trade_id="TURTLE-LIVE-1", lifecycle_id="TURTLE-LIVE-1",
        client_order_id="TURTLE-CLIENT", broker_order_id="TURTLE-ENTRY",
        broker_stop_order_id="TURTLE-STOP", execution_mode="LIVE", registry_mode="REAL",
    )

    result = _Harness().decision(registry=_registry_snapshot(other))

    assert result["eligible"] is False
    assert "MANUAL_OR_EXTERNAL_POSITION_AGGREGATION_RISK" in result["reasons"]
    conflict = result["registry"]["same_leg_conflicts"][0]
    assert conflict["execution_mode"] == "LIVE"
    assert conflict["registry_mode"] == "REAL"
    assert conflict["conflict_reason"] == "OTHER_LIVE_REAL_LIFECYCLE_SAME_LEG"


@pytest.mark.parametrize("bot", ["MANUAL", "EXTERNAL"])
def test_manual_or_external_same_leg_is_factual_conflict_without_missing_field_inference(bot):
    other = _registry_row(
        bot=bot, lifecycle_id=f"{bot}-1", execution_mode=None, registry_mode=None,
    )
    result = _Harness().decision(registry=_registry_snapshot(other))

    assert result["eligible"] is False
    conflict = result["registry"]["same_leg_conflicts"][0]
    assert conflict["conflict_reason"] == "MANUAL_OR_EXTERNAL_SAME_LEG"


@pytest.mark.parametrize(
    "updates",
    [
        {"bot": "MANUAL", "symbol": "BTCUSDT", "lifecycle_id": "MANUAL-BTC"},
        {"bot": "EXTERNAL", "side": "SHORT", "lifecycle_id": "EXTERNAL-SHORT"},
    ],
)
def test_manual_or_external_other_leg_does_not_block(updates):
    result = _Harness().decision(registry=_registry_snapshot(_registry_row(**updates)))
    assert result["eligible"] is True
    assert result["registry"]["same_leg_other_record_count"] == 0


def test_paper_duplicate_with_same_lifecycle_does_not_invalidate_unique_live_real_row():
    paper_duplicate = _registry_row(
        execution_mode="PAPER", registry_mode="PAPER", trade_id="PAPER-DUPLICATE",
    )
    result = _Harness().decision(registry=_registry_snapshot(paper_duplicate))

    assert result["eligible"] is True
    assert result["registry"]["lifecycle_match_count"] == 1
    assert result["registry"]["all_lifecycle_record_count"] == 2


def test_sufficient_filled_disaster_stop_never_sends_emergency_close():
    harness = _Harness()
    verification = _verification()
    verification["order_snapshot"].update(
        raw_status="FILLED",
        status="CLOSED",
        executed_quantity=0.13,
        remaining_quantity=0.0,
    )

    result = harness.handle(verification=verification)

    assert result["status"] == "NO_TERMINAL_STOP_EMERGENCY"
    assert result["incident_detected"] is False
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_flat_broker_position_never_sends_emergency_close():
    harness = _Harness()
    verification = _verification()
    verification["position_snapshot"].update(
        position_closed=True,
        amount=0.0,
        matched_count=0,
        positions=[],
    )

    result = harness.handle(verification=verification)

    assert result["status"] == "NO_TERMINAL_STOP_EMERGENCY"
    assert result["incident_detected"] is False
    assert harness.broker.calls == []


@pytest.mark.parametrize(
    "state",
    [
        "RESERVED", "SEND_ATTEMPTED", "BROKER_CALL_PENDING",
        "LIFECYCLE_LOCK_BLOCKED", "SEND_OUTCOME_UNKNOWN",
        "SENT_UNCONFIRMED", "CONFIRMED",
    ],
)
def test_reserved_sent_inconclusive_or_confirmed_incident_is_never_sent_twice(state):
    harness = _Harness()
    harness.seed_incident(
        {
            "attempt_state": state,
            "send_attempted": state not in {"RESERVED", "BROKER_CALL_PENDING", "LIFECYCLE_LOCK_BLOCKED"},
            "sent": state in {"SENT_UNCONFIRMED", "CONFIRMED"},
            "confirmed": state == "CONFIRMED",
        }
    )

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_BLOCKED"
    assert "FAILSAFE_ALREADY_RESERVED_SENT_OR_UNRESOLVED" in result["guard"]["reasons"]
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_confirmed_emergency_close_is_persisted_and_projected_once_via_mocked_registry():
    harness = _Harness()
    pos = _position()

    result = harness.handle(pos=pos)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert result["sent"] is True
    assert result["confirmed"] is True
    assert len(harness.broker.calls) == 1
    assert harness.broker.calls[0]["amount"] == pytest.approx(0.13)
    assert harness.broker.calls[0]["expected_position_amount"] == pytest.approx(0.13)
    assert harness.broker.calls[0]["execution_auth_token"] == "TEST-AUTH"
    assert harness.auth_calls[0][1] == "managed_close_position_market"
    assert len(harness.lifecycle_lock_calls) == 1
    assert len(harness.registry_write_calls) == 1
    assert len([call for call in harness.event_calls if call[0] == "FALCON_TERMINAL_STOP_EMERGENCY_RESULT"]) == 1
    incident = harness.persisted_incident(result["incident_id"])
    assert incident["attempt_state"] == "CONFIRMED"
    assert incident["sent"] is True
    assert incident["confirmed"] is True
    assert pos["terminal_stop_emergency_reconcile_required"] is True


def test_sequential_retry_after_confirmed_preserves_authoritative_bytes_alerts_and_events():
    harness = _Harness()
    first_position = _position()

    first = harness.handle(pos=first_position)

    assert first["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    incident_id = first["incident_id"]
    incident_key = harness.ns["falcon_terminal_stop_recovery_key"](incident_id)
    authoritative_bytes = harness.backend[incident_key]
    alerts_before_retry = copy.deepcopy(harness.alert_calls)
    events_before_retry = copy.deepcopy(harness.event_calls)
    registry_writes_before_retry = copy.deepcopy(harness.registry_write_calls)
    broker_calls_before_retry = copy.deepcopy(harness.broker.calls)
    retry_position = _position()

    retry = harness.handle(pos=retry_position)

    assert retry["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert retry["authoritative_attempt_state"] == "CONFIRMED"
    assert harness.backend[incident_key] == authoritative_bytes
    assert harness.alert_calls == alerts_before_retry
    assert harness.event_calls == events_before_retry
    assert harness.registry_write_calls == registry_writes_before_retry
    assert harness.broker.calls == broker_calls_before_retry
    assert "terminal_stop_emergency_recovery" not in retry_position


def test_contradictory_confirmation_is_downgraded_to_inconclusive():
    harness = _Harness()

    projected = harness.ns["_falcon_terminal_stop_result_projection"]({
        "ok": True,
        "status": "MANAGED_CLOSE_CONFIRMED",
        "send_attempted": True,
        "sent": False,
        "confirmed": True,
        "remaining_amount": None,
    })

    assert projected["ok"] is False
    assert projected["confirmed"] is None
    assert set(projected["evidence_conflicts"]).issuperset({
        "CONFIRMED_WITHOUT_SENT",
        "CONFIRMED_WITHOUT_FACTUAL_REMAINING_AMOUNT",
        "NOT_SENT_WITHOUT_PRE_SEND_PROOF",
        "NOT_SENT_WITH_UNKNOWN_OUTCOME",
    })


@pytest.mark.parametrize("confirmed", [None, False])
def test_sent_but_unconfirmed_result_is_not_retried(confirmed):
    harness = _Harness(
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_TIMEOUT_UNCONFIRMED",
            "send_attempted": True,
            "sent": True,
            "confirmed": confirmed,
            "send_outcome_unknown": False,
            "phase": "POST_CREATE_CONFIRMATION",
            "order_id": "MAYBE-CLOSE-1",
            "remaining_amount": 0.13,
        }
    )

    first = harness.handle()
    second = harness.handle()

    assert first["status"] == "TERMINAL_STOP_EMERGENCY_SENT_UNCONFIRMED"
    assert first["sent"] is True
    assert first["confirmed"] is confirmed
    assert second["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert second["authoritative_attempt_state"] == "SENT_UNCONFIRMED"
    assert "FAILSAFE_ALREADY_RESERVED_SENT_OR_UNRESOLVED" in second["guard"]["reasons"]
    assert len(harness.broker.calls) == 1
    assert len(harness.registry_write_calls) == 1


def test_critical_alert_bypasses_common_cooldown_but_is_incident_scoped():
    harness = _Harness()
    common_cooldown_calls = []
    harness.ns["falcon_management_alert_decision"] = (
        lambda *args, **kwargs: common_cooldown_calls.append((args, kwargs))
    )
    state = {"incident_id": "INCIDENT-1"}

    first = harness.ns["falcon_terminal_stop_critical_alert"](
        _position(), state, blocked=True
    )
    state["critical_alert"] = first
    second = harness.ns["falcon_terminal_stop_critical_alert"](
        _position(), state, blocked=True
    )

    assert len(harness.alert_calls) == 1
    assert common_cooldown_calls == []
    assert harness.alert_calls[0][1] == {
        "event_type": "FALCON_TERMINAL_DISASTER_STOP_EMERGENCY",
        "mode": "LIVE",
        "operational_critical": True,
    }
    assert first["blocked"] is True
    assert second["suppressed"] is True
    assert second["suppression_reason"] == "INCIDENT_CRITICAL_ALERT_ALREADY_ATTEMPTED"


def test_safety_block_still_alerts_but_never_calls_broker():
    harness = _Harness()
    registry = _registry_snapshot()
    registry["open_trades"]["primary"]["broker_stop_order_id"] = "STOP-OTHER"

    result = harness.handle(registry=registry)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_BLOCKED"
    assert result["critical_alert"]["attempted"] is True
    assert result["critical_alert"]["blocked"] is True
    assert len(harness.alert_calls) == 1
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_auth_block_still_alerts_but_never_calls_broker():
    harness = _Harness(auth_allowed=False)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_AUTH_BLOCKED"
    assert result["critical_alert"]["attempted"] is True
    assert result["critical_alert"]["blocked"] is True
    assert len(harness.auth_calls) == 1
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_auth_context_mismatch_blocks_before_broker():
    harness = _Harness(auth_context_updates={"lifecycle_id": "OTHER", "amount": 9.0})

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_AUTH_BLOCKED"
    assert result["critical_alert"]["attempted"] is True
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_auth_token_never_appears_in_results_position_persistence_registry_events_or_health():
    forbidden = "NEVER-PERSIST-THIS-TOKEN"
    harness = _Harness(
        auth_token=forbidden,
        auth_context_updates={"lifecycle_id": "OTHER-LIFECYCLE"},
    )
    pos = _position()

    result = harness.handle(pos=pos)
    pos["terminal_stop_emergency_last_decision"] = copy.deepcopy(result)
    aggregate = {
        "result": result,
        "pos": pos,
        "redis": harness.backend,
        "registry_updates": harness.registry_write_calls,
        "events": harness.event_calls,
        "health": harness.health,
    }
    encoded = json.dumps(aggregate, ensure_ascii=False, default=str)

    assert result["auth"] == {
        "ok": True,
        "status": "AUTH_ISSUED",
        "token_present": True,
        "context_matches": False,
        "expires_at": None,
    }
    assert forbidden not in encoded
    assert "context" not in result["auth"]
    assert harness.broker.calls == []


def test_atomic_lifecycle_lock_blocks_second_worker_before_token_or_broker():
    harness = _Harness(lifecycle_lock_acquired=False)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert result["lifecycle_lock"]["acquired"] is False
    assert result["critical_alert"] is None
    assert result["persistence"] == {
        "ok": True,
        "status": "NOT_WRITTEN_BY_LIFECYCLE_LOCK_LOSER",
        "authoritative_state_preserved": True,
    }
    assert len(harness.lifecycle_lock_calls) == 1
    assert harness.backend == {}
    assert harness.alert_calls == []
    assert harness.auth_calls == []
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_not_sent_terminal_state_is_persisted_before_lifecycle_lock_release():
    harness = _Harness(
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_EXCHANGE_INIT_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        }
    )

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    _assert_terminal_state_persisted_before_release(harness, "NOT_SENT")


def test_final_revalidation_block_is_persisted_before_lifecycle_lock_release():
    final = _verification()
    final["position_snapshot"].update({"position_closed": True, "amount": 0.0})
    harness = _Harness(final_verification=final)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    _assert_terminal_state_persisted_before_release(
        harness, "FINAL_REVALIDATION_BLOCKED"
    )


def test_auth_block_is_persisted_before_lifecycle_lock_release():
    harness = _Harness(auth_allowed=False)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_AUTH_BLOCKED"
    _assert_terminal_state_persisted_before_release(harness, "BLOCKED_AUTH")


def test_lifecycle_lock_loser_never_overwrites_existing_authoritative_incident():
    harness = _Harness(lifecycle_lock_acquired=False)
    incident_id = harness.seed_incident({
        "attempt_state": "FINAL_REVALIDATION_BLOCKED",
        "winner_marker": "PRESERVE-EXACTLY",
        "send_attempted": False,
        "sent": False,
        "confirmed": False,
    })
    before = copy.deepcopy(harness.backend)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert result["authoritative_attempt_state"] == "FINAL_REVALIDATION_BLOCKED"
    assert result["persistence"]["authoritative_state_preserved"] is True
    assert harness.backend == before
    assert harness.persisted_incident(incident_id)["winner_marker"] == "PRESERVE-EXACTLY"
    assert harness.alert_calls == []
    assert harness.auth_calls == []
    assert harness.broker.calls == []


def test_real_atomic_lock_is_lifecycle_owned_and_releasable_only_by_owner_nonce():
    redis_probe = _RedisNxProbe()
    acquire, release = _load_real_lifecycle_lock_functions(redis_probe)

    first = acquire("LIFECYCLE-LOCK-1", "OWNER-1")
    duplicate = acquire("LIFECYCLE-LOCK-1", "OWNER-2")
    wrong_owner = release("LIFECYCLE-LOCK-1", "OWNER-OTHER")
    right_owner = release("LIFECYCLE-LOCK-1", "OWNER-1")
    retry_after_release = acquire("LIFECYCLE-LOCK-1", "OWNER-2")

    assert first["acquired"] is True
    assert duplicate["acquired"] is False
    assert wrong_owner["released"] is False
    assert wrong_owner["status"] == "LIFECYCLE_LOCK_OWNERSHIP_MISMATCH"
    assert right_owner["released"] is True
    assert retry_after_release["acquired"] is True
    assert redis_probe.authoritative_get_calls


def test_two_concurrent_stop_ids_for_same_lifecycle_emit_exactly_one_managed_close():
    barrier = threading.Barrier(2)
    lifecycle_locks = _RedisNxProbe(barrier=barrier)
    backend = {}
    first = _Harness(backend=backend, lifecycle_locks=lifecycle_locks)
    second = _Harness(backend=backend, lifecycle_locks=lifecycle_locks)
    second.ns["central_broker"] = first.broker

    pos_1 = _position()
    verification_1 = _verification()
    registry_1 = _registry_snapshot()
    pos_2 = _position(broker_stop_order_id="STOP-2", disaster_stop_order_id="STOP-2")
    pos_2["live_order"]["disaster_stop"]["order_id"] = "STOP-2"
    verification_2 = _verification(stop_order_id="STOP-2")
    verification_2["order_snapshot"]["order_id"] = "STOP-2"
    registry_2 = _registry_snapshot()
    registry_2["open_trades"]["primary"]["broker_stop_order_id"] = "STOP-2"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(first.handle, pos_1, verification_1, registry_1),
            pool.submit(second.handle, pos_2, verification_2, registry_2),
        ]
        results = [future.result(timeout=10) for future in futures]

    assert sum(result["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED" for result in results) == 1
    assert sum(result["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED" for result in results) == 1
    assert len(first.broker.calls) == 1
    assert len(first.auth_calls) + len(second.auth_calls) == 1
    assert len(lifecycle_locks.values) == 1
    incident_keys = [key for key in backend if ":incident:" in key]
    assert len(incident_keys) == 1
    assert json.loads(backend[incident_keys[0]])["incident"]["attempt_state"] == "CONFIRMED"


def test_terminal_and_legacy_stop_failsafes_share_one_lifecycle_lock():
    lifecycle_locks = _RedisNxProbe(barrier=threading.Barrier(2))
    harness = _Harness(lifecycle_locks=lifecycle_locks)
    broker = _LegacyRaceBroker()
    harness.broker = broker
    harness.ns["central_broker"] = broker
    closed_calls = []
    legacy = _load_legacy_stop_cross(harness, broker, closed_calls)
    terminal_pos = _position()
    legacy_pos = _position(entry_ownership_verified=True)
    legacy_position = {
        "ok": True,
        "read_only": True,
        "position_closed": False,
        "ownership_safe": True,
        "amount": 0.13,
        "symbol": "SOLUSDT",
        "side": "LONG",
        "matched_count": 1,
    }
    legacy_order = {
        "ok": True,
        "read_only": True,
        "status": "OPEN",
        "order_id": "STOP-1",
        "filled": 0.0,
    }

    with ThreadPoolExecutor(max_workers=2) as pool:
        terminal_future = pool.submit(harness.handle, terminal_pos, _verification())
        legacy_future = pool.submit(
            legacy,
            legacy_pos["id"],
            legacy_pos,
            75.80,
            True,
            legacy_position,
            legacy_order,
        )
        results = [
            terminal_future.result(timeout=10),
            legacy_future.result(timeout=10),
        ]

    assert len(broker.calls) == 1
    assert len(broker.cancel_calls) <= 1
    assert sum(
        result.get("status") in {
            "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED",
            "STOP_FAILSAFE_LIFECYCLE_LOCK_BLOCKED",
        }
        for result in results
    ) == 1
    assert closed_calls == []


def test_orphan_lifecycle_lock_blocks_legacy_before_cancel_auth_or_market_close():
    lifecycle_locks = _RedisNxProbe()
    harness = _Harness(lifecycle_locks=lifecycle_locks)
    broker = _LegacyRaceBroker()
    harness.ns["central_broker"] = broker
    closed_calls = []
    legacy = _load_legacy_stop_cross(harness, broker, closed_calls)
    pos = _position(entry_ownership_verified=True)
    lock_id = harness.ns["falcon_terminal_stop_lifecycle_lock_id"](pos)
    lifecycle_locks.set(f"test:lifecycle-lock:{lock_id}", "ORPHAN-OWNER", nx=True)

    result = legacy(
        pos["id"],
        pos,
        75.80,
        True,
        {
            "ok": True,
            "read_only": True,
            "position_closed": False,
            "ownership_safe": True,
            "amount": 0.13,
            "symbol": "SOLUSDT",
            "side": "LONG",
            "matched_count": 1,
        },
        {"ok": True, "read_only": True, "status": "OPEN", "order_id": "STOP-1"},
    )

    assert result["status"] == "STOP_FAILSAFE_LIFECYCLE_LOCK_BLOCKED"
    assert result["lifecycle_lock"]["reconciliation_required"] is True
    assert broker.cancel_calls == []
    assert broker.calls == []
    assert harness.auth_calls == []
    assert closed_calls == []


def test_stop_replacement_uses_lifecycle_lock_before_auth_and_broker_mutation():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_falcon_resize_runner_stop"
    )
    call_lines = {}
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            call_lines.setdefault(node.func.id, []).append(node.lineno)
        elif isinstance(node.func, ast.Attribute):
            call_lines.setdefault(node.func.attr, []).append(node.lineno)

    acquire_line = min(call_lines["falcon_terminal_stop_acquire_lifecycle_lock"])
    auth_line = min(call_lines["falcon_issue_management_token"])
    broker_line = min(call_lines["replace_position_stop_order"])
    release_line = min(call_lines["falcon_terminal_stop_release_lifecycle_lock"])

    assert acquire_line < auth_line < broker_line < release_line
    source = ast.get_source_segment(FALCON_SOURCE.read_text(encoding="utf-8"), function)
    assert 'pos["broker_stop_order_id"] = new_order_id' in source
    assert 'pos["disaster_stop_order_id"] = new_order_id' in source


def test_terminal_projection_sanitizer_removes_raw_context_nonce_and_extended_secrets():
    sanitize = _Harness().ns["_falcon_terminal_sanitize_projection"]
    forbidden = "NEVER-PERSIST-EXTENDED-SECRET"

    result = sanitize({
        "context": {"token": forbidden, "authorization": forbidden},
        "owner_nonce": forbidden,
        "auth": {"token": forbidden, "token_present": True},
        "error": f"token:{forbidden} password={forbidden} /opt/private/{forbidden}",
    })
    serialized = json.dumps(result, ensure_ascii=False)

    assert forbidden not in serialized
    assert "context" not in result
    assert "owner_nonce" not in result
    assert result["auth"] == {"token_present": True}
    assert result["error"] == "REDACTED_SENSITIVE_VALUE"


def test_two_different_lifecycles_proceed_independently_and_preserve_both_incident_keys():
    lifecycle_locks = _RedisNxProbe(barrier=threading.Barrier(2))
    backend = {}
    first = _Harness(backend=backend, lifecycle_locks=lifecycle_locks)
    second = _Harness(backend=backend, lifecycle_locks=lifecycle_locks)
    pos_2 = _position(lifecycle_id="LIFECYCLE-2")
    registry_2 = _registry_snapshot()
    registry_2["open_trades"]["primary"]["lifecycle_id"] = "LIFECYCLE-2"

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_1 = pool.submit(first.handle)
        future_2 = pool.submit(second.handle, pos_2, None, registry_2)
        result_1 = future_1.result(timeout=10)
        result_2 = future_2.result(timeout=10)

    assert result_1["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert result_2["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert len(first.broker.calls) == len(second.broker.calls) == 1
    incident_keys = [key for key in backend if ":incident:" in key]
    assert len(incident_keys) == 2
    assert all(json.loads(backend[key])["incident"] for key in incident_keys)


def test_restart_with_lifecycle_lock_but_empty_incident_ledger_never_reissues():
    lifecycle_locks = _RedisNxProbe()
    first = _Harness(lifecycle_locks=lifecycle_locks)
    lock_id = first.ns["falcon_terminal_stop_lifecycle_lock_id"](_position())
    lifecycle_locks.values[f"test:lifecycle-lock:{lock_id}"] = "ORPHANED-OWNER"
    restarted = _Harness(backend={}, lifecycle_locks=lifecycle_locks)

    result = restarted.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert result["reasons"] == ["LIFECYCLE_LOCK_ACTIVE_OR_ORPHANED_RECONCILIATION_REQUIRED"]
    assert restarted.auth_calls == []
    assert restarted.broker.calls == []


@pytest.mark.parametrize(
    "status",
    [
        "MANAGED_CLOSE_EXCHANGE_INIT_ERROR",
        "MANAGED_CLOSE_POSITION_SIDE_ERROR",
        "MANAGED_CLOSE_HEDGE_MODE_ERROR",
        "MANAGED_CLOSE_PRECISION_ERROR",
    ],
)
def test_definitive_pre_send_broker_block_releases_lock_for_safe_retry(status):
    harness = _Harness(
        broker_result={
            "ok": False,
            "status": status,
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        }
    )

    first = harness.handle()
    second = harness.handle()

    assert first["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    assert second["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    assert len(harness.broker.calls) == 2
    assert len(harness.lifecycle_lock_release_calls) == 2


def test_fec1_is_reserved_only_after_final_revalidation_and_complete_auth():
    harness = _Harness()
    original_prepare = harness.ns["falcon_prepare_position_client_order_id"]
    reservation_observations = []

    def traced_prepare(*args, **kwargs):
        reservation_observations.append({
            "final_revalidations": len(harness.final_verification_calls),
            "auth_calls": len(harness.auth_calls),
        })
        return original_prepare(*args, **kwargs)

    harness.ns["falcon_prepare_position_client_order_id"] = traced_prepare

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert reservation_observations == [
        {"final_revalidations": 1, "auth_calls": 1}
    ]
    assert harness.broker.calls[0]["client_tag"].startswith("FEC1-")


def test_final_revalidation_or_auth_block_consumes_no_fec1_reservation():
    final = _verification()
    final["position_snapshot"].update({"position_closed": True, "amount": 0.0})
    final_blocked = _Harness(final_verification=final)

    final_result = final_blocked.handle()

    assert final_result["status"] == (
        "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    )
    assert final_blocked.account_authority.values == {}
    assert final_blocked.broker.calls == []

    auth_blocked = _Harness(
        auth_context_updates={"lifecycle_id": "WRONG-LIFECYCLE"}
    )

    auth_result = auth_blocked.handle()

    assert auth_result["status"] == "TERMINAL_STOP_EMERGENCY_AUTH_BLOCKED"
    assert auth_blocked.account_authority.values == {}
    assert auth_blocked.broker.calls == []


def test_factual_pre_send_consumes_attempt_before_unlock_and_retries_contiguously():
    harness = _Harness(
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_PRECISION_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        }
    )
    original_record = harness.ns[
        "falcon_record_client_order_attempt_outcome"
    ]

    def traced_record(reservation, outcome_state, **kwargs):
        result = original_record(reservation, outcome_state, **kwargs)
        harness.operation_log.append({
            "operation": "ACCOUNT_OUTCOME_PERSISTED",
            "status": result.get("status"),
            "persistent": result.get("persistent"),
            "attempt_id": reservation.get("attempt_id"),
        })
        return result

    harness.ns["falcon_record_client_order_attempt_outcome"] = traced_record

    results = [harness.handle() for _ in range(3)]

    assert [result["status"] for result in results] == [
        "TERMINAL_STOP_EMERGENCY_NOT_SENT",
        "TERMINAL_STOP_EMERGENCY_NOT_SENT",
        "TERMINAL_STOP_EMERGENCY_NOT_SENT",
    ]
    reservations = [
        call["client_order_id_reservation"] for call in harness.broker.calls
    ]
    assert [item["attempt_sequence"] for item in reservations] == [0, 1, 2]
    assert len({item["attempt_id"] for item in reservations}) == 3
    assert len({item["client_order_id"] for item in reservations}) == 3
    assert [call["client_tag"] for call in harness.broker.calls] == [
        item["client_order_id"] for item in reservations
    ]
    assert all(
        result["account_attempt_outcome"]["status"]
        == "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
        and result["account_attempt_outcome"]["persistent"] is True
        and result["account_attempt_outcome"]["id_released"] is False
        for result in results
    )
    records = _decoded_account_authority_records(harness)
    assert sum(
        record.get("status") == "RECONCILED_NEW_ATTEMPT_AUTHORIZED"
        for record in records
    ) == 2
    persisted = harness.persisted_incident(results[-1]["incident_id"])
    assert persisted["current_attempt_id"] == reservations[-1]["attempt_id"]
    assert persisted["current_attempt_sequence"] == 2
    assert persisted["prior_attempt_id"] == reservations[-2]["attempt_id"]
    assert persisted["client_order_id"] == reservations[-1]["client_order_id"]
    assert persisted["disposition"] == "PRE_SEND_CONSUMED"
    assert persisted["retry_authorization_status"] in {
        "RECONCILED_NEW_ATTEMPT_AUTHORIZED",
        "ATTEMPT_AUTHORIZATION_ALREADY_EXISTS",
    }
    assert persisted["reconciliation_basis"] == (
        "AUTHORITATIVE_PRE_SEND_NO_SEND_CLAIM"
    )
    outcome_indexes = [
        index
        for index, operation in enumerate(harness.operation_log)
        if operation.get("operation") == "ACCOUNT_OUTCOME_PERSISTED"
        and operation.get("persistent") is True
    ]
    release_indexes = [
        index
        for index, operation in enumerate(harness.operation_log)
        if operation.get("operation") == "RELEASE"
    ]
    assert len(outcome_indexes) == len(release_indexes) == 3
    assert all(
        outcome_index < release_index
        for outcome_index, release_index in zip(outcome_indexes, release_indexes)
    )


def test_pre_send_outcome_authority_failure_retains_lock_and_blocks_retry():
    class OutcomeWriteFailure(_RedisNxProbe):
        def set(self, key, value, nx=False):
            try:
                record = json.loads(value) if isinstance(value, str) else value
            except (TypeError, ValueError):
                record = {}
            if (
                nx
                and isinstance(record, dict)
                and record.get("status") == "PRE_SEND_CONSUMED"
            ):
                return False
            return super().set(key, value, nx=nx)

    authority = OutcomeWriteFailure()
    harness = _Harness(
        account_authority=authority,
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_PRECISION_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        },
    )

    first = harness.handle()
    authority_keys_after_first = set(authority.values)
    second = harness.handle()

    assert first["status"] == (
        "TERMINAL_STOP_EMERGENCY_PRE_SEND_OUTCOME_PERSISTENCE_BLOCKED"
    )
    assert first["account_attempt_outcome"]["ok"] is False
    assert first["lifecycle_lock_retained"] is True
    assert first["lifecycle_lock_release"] is None
    assert second["status"] == (
        "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    )
    assert set(authority.values) == authority_keys_after_first
    assert len(harness.broker.calls) == 1


def test_broker_persisted_pre_send_outcome_is_reused_without_conflicting_rewrite():
    harness = _Harness()
    record_outcome = harness.ns[
        "falcon_record_client_order_attempt_outcome"
    ]

    def broker_with_persisted_outcome(**kwargs):
        harness.broker.calls.append(copy.deepcopy(kwargs))
        outcome = record_outcome(
            kwargs["client_order_id_reservation"],
            "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
            reason="BROKER_PRE_SEND_CONTEXT_BLOCKED",
            failure_phase="PRE_SEND_CONTEXT_VALIDATION",
        )
        return {
            "ok": False,
            "status": "MANAGED_CLOSE_POSITION_SIDE_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
            "client_order_id": kwargs["client_tag"],
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "attempt_outcome_persistence": outcome,
        }

    harness.broker.managed_close_position_market = broker_with_persisted_outcome
    harness.ns["falcon_record_client_order_attempt_outcome"] = (
        lambda *_args, **_kwargs: pytest.fail(
            "Falcon rewrote a broker-persisted PRE_SEND outcome"
        )
    )

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    assert result["account_attempt_outcome"]["status"] == (
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
    )
    consumed = next(
        record
        for record in _decoded_account_authority_records(harness)
        if record.get("status") == "PRE_SEND_CONSUMED"
    )
    assert consumed["reason"] == "BROKER_PRE_SEND_CONTEXT_BLOCKED"
    assert consumed["failure_phase"] == "PRE_SEND_CONTEXT_VALIDATION"
    assert result["lifecycle_lock_release"]["released"] is True


def test_failed_lifecycle_unlock_is_reported_retained_and_never_retries():
    class ReleaseFailure(_RedisNxProbe):
        def eval(self, script, keys=None, args=None):
            return 0

    lifecycle_locks = ReleaseFailure()
    harness = _Harness(
        lifecycle_locks=lifecycle_locks,
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_PRECISION_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        },
    )

    first = harness.handle()
    second = harness.handle()

    assert first["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    assert first["lifecycle_lock_release"]["released"] is False
    assert first["lifecycle_lock_retained"] is True
    assert second["status"] == (
        "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    )
    assert len(harness.broker.calls) == 1


def test_two_workers_allow_one_attempt_then_next_cycle_uses_new_identity():
    backend = {}
    lifecycle_locks = _RedisNxProbe()
    account_authority = _RedisNxProbe()
    first = _Harness(
        backend=backend,
        lifecycle_locks=lifecycle_locks,
        account_authority=account_authority,
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_PRECISION_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": False,
            "remaining_amount": 0.13,
        },
    )
    second = _Harness(
        backend=backend,
        lifecycle_locks=lifecycle_locks,
        account_authority=account_authority,
    )
    broker_entered = threading.Event()
    allow_broker_return = threading.Event()
    first_broker_call = first.broker.managed_close_position_market

    def blocked_broker_call(**kwargs):
        broker_entered.set()
        assert allow_broker_return.wait(timeout=10)
        return first_broker_call(**kwargs)

    first.broker.managed_close_position_market = blocked_broker_call

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(first.handle)
        assert broker_entered.wait(timeout=10)
        second_future = pool.submit(second.handle)
        overlapping_result = second_future.result(timeout=10)
        allow_broker_return.set()
        first_result = first_future.result(timeout=10)

    assert first_result["status"] == "TERMINAL_STOP_EMERGENCY_NOT_SENT"
    assert overlapping_result["status"] == (
        "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    )
    assert len(first.broker.calls) + len(second.broker.calls) == 1
    first_reservation = first.broker.calls[0]["client_order_id_reservation"]
    assert first_reservation["attempt_sequence"] == 0

    next_cycle = second.handle()

    assert next_cycle["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert len(second.broker.calls) == 1
    next_reservation = second.broker.calls[0]["client_order_id_reservation"]
    assert next_reservation["attempt_sequence"] == 1
    assert next_reservation["attempt_id"] != first_reservation["attempt_id"]
    assert (
        next_reservation["client_order_id"]
        != first_reservation["client_order_id"]
    )
    persisted = second.persisted_incident(second.incident_id())
    assert persisted["client_order_id"] == next_reservation["client_order_id"]
    assert persisted["client_tag"] == next_reservation["client_order_id"]


def test_contradictory_not_sent_unknown_result_retains_lock_and_blocks_retry():
    harness = _Harness(
        broker_result={
            "ok": False,
            "status": "MANAGED_CLOSE_ERROR",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "send_outcome_unknown": True,
            "remaining_amount": 0.13,
        },
    )

    first = harness.handle()
    authority_keys_after_first = set(harness.account_authority.values)
    second = harness.handle()

    assert first["status"] == "TERMINAL_STOP_EMERGENCY_SEND_OUTCOME_UNKNOWN"
    assert first["failsafe"]["sent"] is None
    assert "NOT_SENT_WITH_UNKNOWN_OUTCOME" in first["failsafe"]["evidence_conflicts"]
    assert harness.lifecycle_lock_release_calls == []
    assert second["status"] in {
        "TERMINAL_STOP_EMERGENCY_BLOCKED",
        "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED",
    }
    assert len(harness.broker.calls) == 1
    assert set(harness.account_authority.values) == authority_keys_after_first


def test_confirmed_without_sent_never_marks_flat_or_releases_lock():
    pos = _position(remaining_qty=0.13)
    harness = _Harness(
        broker_result={
            "ok": True,
            "status": "MANAGED_CLOSE_CONFIRMED",
            "phase": "PRE_SEND_SETUP",
            "send_attempted": False,
            "sent": False,
            "confirmed": True,
            "send_outcome_unknown": False,
            "order_id": "CONTRADICTORY",
            "filled_amount": 0.13,
            "remaining_amount": 0.0,
        },
    )

    result = harness.handle(pos=pos)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_SEND_OUTCOME_UNKNOWN"
    assert result["confirmed"] is None
    assert pos["remaining_qty"] == pytest.approx(0.13)
    assert harness.lifecycle_lock_release_calls == []


@pytest.mark.parametrize(
    "broker_updates,expected_conflict",
    [
        ({"client_order_id": "WRONG-CLIENT"}, "CONFIRMED_CLIENT_ORDER_ID_MISMATCH"),
        ({"order_id": None}, "CONFIRMED_WITHOUT_FACTUAL_ORDER_ID"),
        ({"filled_amount": 0.01}, "CONFIRMED_FILLED_AMOUNT_INSUFFICIENT"),
    ],
)
def test_confirmed_close_requires_exact_deterministic_identity(broker_updates, expected_conflict):
    broker_result = {
        "ok": True,
        "status": "MANAGED_CLOSE_CONFIRMED",
        "phase": "POST_CREATE_CONFIRMATION",
        "send_attempted": True,
        "sent": True,
        "confirmed": True,
        "send_outcome_unknown": False,
        "order_id": "EMERGENCY-CLOSE-1",
        "filled_amount": 0.13,
        "remaining_amount": 0.0,
        "symbol": "SOLUSDT",
        "side": "LONG",
    }
    broker_result.update(broker_updates)
    pos = _position(remaining_qty=0.13)
    harness = _Harness(broker_result=broker_result)

    result = harness.handle(pos=pos)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_SEND_OUTCOME_UNKNOWN"
    assert expected_conflict in result["failsafe"]["evidence_conflicts"]
    assert pos["remaining_qty"] == pytest.approx(0.13)
    assert harness.lifecycle_lock_release_calls == []


def test_unresolved_recovery_on_other_stop_blocks_same_lifecycle():
    harness = _Harness()
    lifecycle_lock_id = harness.ns["falcon_terminal_stop_lifecycle_lock_id"](_position())
    harness.lifecycle_locks.values[f"test:lifecycle-lock:{lifecycle_lock_id}"] = "OWNER-A"
    pos = _position(
        broker_stop_order_id="STOP-2",
        disaster_stop_order_id="STOP-2",
    )
    pos["live_order"]["disaster_stop"]["order_id"] = "STOP-2"
    verification = _verification(stop_order_id="STOP-2")
    verification["order_snapshot"]["order_id"] = "STOP-2"
    registry = _registry_snapshot()
    registry["open_trades"]["primary"]["broker_stop_order_id"] = "STOP-2"

    result = harness.handle(
        pos=pos,
        verification=verification,
        registry=registry,
    )

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED"
    assert result["reasons"] == ["LIFECYCLE_LOCK_ACTIVE_OR_ORPHANED_RECONCILIATION_REQUIRED"]
    assert harness.auth_calls == []
    assert harness.broker.calls == []


@pytest.mark.parametrize(
    "broker_result,expected_state",
    [
        (
            {
                "ok": True,
                "status": "MANAGED_CLOSE_CONFIRMED",
                "send_attempted": True,
                "sent": True,
                "confirmed": True,
                "order_id": "CLOSE-1",
                "filled_amount": 0.13,
                "remaining_amount": 0.0,
            },
            "CONFIRMED",
        ),
        (
            {
                "ok": False,
                "status": "MANAGED_CLOSE_TIMEOUT_UNCONFIRMED",
                "send_attempted": True,
                "sent": True,
                "confirmed": None,
                "send_outcome_unknown": False,
                "phase": "POST_CREATE_CONFIRMATION",
                "order_id": "MAYBE-CLOSE-1",
                "remaining_amount": 0.13,
            },
            "SENT_UNCONFIRMED",
        ),
    ],
)
def test_persisted_idempotency_survives_harness_restart(broker_result, expected_state):
    backend = {}
    first_process = _Harness(backend=backend, broker_result=broker_result)
    first = first_process.handle()
    second_process = _Harness(backend=backend)

    second = second_process.handle()

    assert first["status"] == f"TERMINAL_STOP_EMERGENCY_{expected_state}"
    assert len(first_process.broker.calls) == 1
    assert second["status"] == "TERMINAL_STOP_EMERGENCY_BLOCKED"
    assert "FAILSAFE_ALREADY_RESERVED_SENT_OR_UNRESOLVED" in second["guard"]["reasons"]
    assert second_process.broker.calls == []
    assert second_process.registry_write_calls == []


def test_exact_historical_terminal_evidence_can_resolve_order_not_found():
    harness = _Harness()
    verification = _verification()
    verification["order_snapshot"] = {
        "ok": False,
        "read_only": True,
        "order_id": "STOP-1",
        "status": "ORDER_NOT_FOUND",
        "executed_quantity": None,
    }
    verification["historical_stop_order_snapshot"] = {
        "ok": True,
        "read_only": True,
        "historical": True,
        "requested_order_id": "STOP-1",
        "order_id": "STOP-1",
        "raw_status": "REJECTED",
        "status": "CANCELED",
        "executed_quantity": 0.0,
        "remaining_quantity": 0.13,
    }

    result = harness.decision(verification=verification)

    assert result["incident_detected"] is True
    assert result["eligible"] is True
    assert result["stop"]["historical_terminal_found"] is True
    assert result["stop"]["source"] == "EXACT_HISTORICAL_TERMINAL_ORDER"


def test_historical_terminal_without_factual_executed_quantity_is_not_zero_fill():
    harness = _Harness()
    verification = _verification()
    verification["order_snapshot"] = {
        "ok": False,
        "read_only": True,
        "order_id": "STOP-1",
        "status": "ORDER_NOT_FOUND",
        "executed_quantity": None,
    }
    verification["historical_stop_order_snapshot"] = {
        "ok": True,
        "historical": True,
        "read_only": True,
        "requested_order_id": "STOP-1",
        "order_id": "STOP-1",
        "raw_status": "FAILED",
        "status": "CANCELED",
        "executed_quantity": None,
        # Compatibility projections used to expose this default as factual.
        "filled": 0.0,
        "remaining_quantity": 0.13,
    }

    result = harness.handle(verification=verification)

    assert result["status"] == "NO_TERMINAL_STOP_EMERGENCY"
    assert result["terminal_stop"]["executed_quantity"] is None
    assert harness.broker.calls == []


@pytest.mark.parametrize(
    ("reduce_only", "eligible", "expected_reason"),
    [
        (True, True, None),
        (False, False, "STOP_ONE_WAY_CLOSE_SEMANTICS_NOT_PROVEN"),
    ],
)
def test_one_way_terminal_stop_requires_reduce_only_or_close_semantics(
    reduce_only,
    eligible,
    expected_reason,
):
    pos = _position(
        broker_stop_position_side=None,
        broker_stop_hedge_mode_detected=False,
        broker_stop_reduce_only=reduce_only,
    )
    pos["live_order"]["disaster_stop"].update({
        "position_side": None,
        "hedge_mode_detected": False,
        "reduce_only": reduce_only,
    })

    result = _Harness().decision(pos=pos)

    assert result["eligible"] is eligible
    if expected_reason:
        assert expected_reason in result["reasons"]
    else:
        assert "STOP_POSITION_SIDE_MISMATCH" not in result["reasons"]


def test_order_not_found_without_exact_historical_terminal_evidence_does_not_send():
    harness = _Harness()
    verification = _verification()
    verification["order_snapshot"] = {
        "ok": False,
        "read_only": True,
        "order_id": "STOP-1",
        "status": "ORDER_NOT_FOUND",
        "executed_quantity": None,
    }

    result = harness.handle(verification=verification)

    assert result["status"] == "NO_TERMINAL_STOP_EMERGENCY"
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []


def test_canceled_stop_with_active_replacement_discovered_after_lock_never_market_closes():
    initial = _canceled_verification()
    harness = _Harness(
        final_verification=_canceled_verification(),
        open_orders_result={
            "ok": True,
            "status": "OPEN_ORDERS_SNAPSHOT_OK",
            "read_only": True,
            "sent": False,
            "count": 1,
            "orders": [{
                "order_id": "STOP-2",
                "raw_status": "OPEN",
                "status": "OPEN",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "position_side": "LONG",
                "type": "STOP_MARKET",
                "remaining_quantity": 0.13,
                "stop_price": 75.924,
            }],
        },
    )

    result = harness.handle(verification=initial)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "CANCELED_STOP_ACTIVE_REPLACEMENT_PRESENT" in result["guard"]["reasons"]
    assert harness.broker.open_orders_calls == ["SOLUSDT"]
    assert harness.broker.calls == []


def test_canceled_stop_with_one_way_reduce_only_replacement_never_market_closes():
    harness = _Harness(
        final_verification=_canceled_verification(),
        open_orders_result={
            "ok": True,
            "status": "OPEN_ORDERS_SNAPSHOT_OK",
            "read_only": True,
            "sent": False,
            "count": 1,
            "orders": [{
                "order_id": "STOP-2-ONE-WAY",
                "raw_status": "OPEN",
                "status": "OPEN",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "position_side": None,
                "reduce_only": True,
                "type": "STOP_MARKET",
                "remaining_quantity": 0.13,
                "stop_price": 75.924,
            }],
        },
    )

    result = harness.handle(verification=_canceled_verification())

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "CANCELED_STOP_ACTIVE_REPLACEMENT_PRESENT" in result["guard"]["reasons"]
    assert harness.broker.open_orders_calls == ["SOLUSDT"]
    assert harness.auth_calls == []
    assert harness.broker.calls == []


@pytest.mark.parametrize(
    "order_updates,expected_reason",
    [
        (
            {"derived_order_id": "DERIVED-MARKET-2"},
            "CANCELED_STOP_DERIVED_ORDER_RECONCILIATION_REQUIRED",
        ),
        (
            {
                "fills": [{"id": "FILL-2", "order_id": "DERIVED-MARKET-2", "amount": 0.01}],
                "fills_count": 1,
                "executed_quantity": 0.0,
            },
            "CANCELED_STOP_DERIVED_FILL_RECONCILIATION_REQUIRED",
        ),
    ],
)
def test_canceled_stop_with_derived_child_or_fill_blocks_new_close(order_updates, expected_reason):
    verification = _canceled_verification()
    verification["order_snapshot"].update(order_updates)
    harness = _Harness(final_verification=verification)

    result = harness.handle(verification=verification)

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_BLOCKED"
    assert expected_reason in result["guard"]["reasons"]
    assert harness.auth_calls == []
    assert harness.broker.calls == []


def test_canceled_stop_with_ambiguous_same_leg_stop_order_fails_closed():
    harness = _Harness(
        final_verification=_canceled_verification(),
        open_orders_result={
            "ok": True,
            "status": "OPEN_ORDERS_SNAPSHOT_OK",
            "read_only": True,
            "sent": False,
            "count": 1,
            "orders": [{
                "order_id": "STOP-2-AMBIGUOUS",
                "raw_status": "OPEN",
                "symbol": "SOLUSDT",
                "side": "SELL",
                "position_side": "BOTH",
                "reduce_only": False,
                "close_position": False,
                "type": "STOP_MARKET",
                "remaining_quantity": 0.50,
                "stop_price": 75.924,
            }],
        },
    )

    result = harness.handle(verification=_canceled_verification())

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "CANCELED_STOP_ACTIVE_REPLACEMENT_PRESENT" in result["guard"]["reasons"]
    replacement = result["guard"]["replacement"]["active_replacements"][0]
    assert replacement["active"] is True
    assert harness.auth_calls == []
    assert harness.broker.calls == []


def test_canceled_stop_during_replace_position_stop_order_never_market_closes():
    harness = _Harness(
        final_verification=_canceled_verification(),
        final_mutator=lambda pos: pos.__setitem__("stop_replacement_in_progress", True),
    )

    result = harness.handle(verification=_canceled_verification())

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "CANCELED_STOP_REPLACEMENT_IN_PROGRESS" in result["guard"]["reasons"]
    assert harness.broker.calls == []


def test_canceled_stop_requires_successful_post_lock_open_order_scan():
    harness = _Harness(
        final_verification=_canceled_verification(),
        open_orders_result={
            "ok": False,
            "status": "OPEN_ORDERS_SNAPSHOT_ERROR",
            "read_only": True,
            "orders": [],
            "count": 0,
        },
    )

    result = harness.handle(verification=_canceled_verification())

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "CANCELED_STOP_OPEN_ORDERS_REVALIDATION_REQUIRED" in result["guard"]["reasons"]
    assert harness.broker.calls == []


def test_canceled_stop_without_replacement_and_with_fresh_empty_scan_remains_eligible():
    harness = _Harness(final_verification=_canceled_verification())
    result = harness.handle(verification=_canceled_verification())

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert harness.broker.open_orders_calls == ["SOLUSDT"]
    assert len(harness.broker.calls) == 1


def test_stop_id_change_between_decision_and_send_blocks_before_token_and_broker():
    def mutate(pos):
        pos["broker_stop_order_id"] = "STOP-2"
        pos["disaster_stop_order_id"] = "STOP-2"

    harness = _Harness(final_mutator=mutate)
    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "STOP_ID_CHANGED_DURING_FINAL_REVALIDATION" in result["guard"]["reasons"]
    assert harness.auth_calls == []
    assert harness.broker.calls == []


def test_position_closes_between_decision_and_send_blocks_before_market_close():
    final = _verification()
    final["position_snapshot"].update({"position_closed": True, "amount": 0.0})
    harness = _Harness(final_verification=final)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "BROKER_POSITION_NOT_OPEN" in result["guard"]["reasons"]
    assert harness.broker.calls == []


def test_position_quantity_changes_between_decision_and_send_blocks_before_market_close():
    final = _verification()
    final["position_snapshot"]["amount"] = 0.12
    final["position_snapshot"]["positions"][0]["amount"] = 0.12
    harness = _Harness(final_verification=final)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED"
    assert "BROKER_QTY_DIFFERS_FROM_FALCON_REMAINING_QTY" in result["guard"]["reasons"]
    assert harness.broker.calls == []


def test_failed_zero_fill_without_replacement_remains_eligible_after_final_revalidation():
    harness = _Harness(final_verification=_verification())
    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_EMERGENCY_CONFIRMED"
    assert len(harness.broker.calls) == 1


def test_unacknowledged_persistence_blocks_before_auth_or_broker():
    harness = _Harness(persistence_ack=False)

    result = harness.handle()

    assert result["status"] == "TERMINAL_STOP_RECOVERY_PERSISTENCE_WRITE_REQUIRED"
    assert result["incident_detected"] is True
    assert harness.auth_calls == []
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []
    assert harness.lifecycle_lock_release_calls == []
    assert len(harness.lifecycle_locks.values) == 1


def test_broker_call_pending_persistence_failure_retains_lock_and_never_sends():
    harness = _Harness(persistence_fail_states={"BROKER_CALL_PENDING"})
    pos = _position()

    result = harness.handle(pos=pos)

    assert result["status"] == "TERMINAL_STOP_RECOVERY_PRE_SEND_PERSISTENCE_REQUIRED"
    assert harness.broker.calls == []
    assert harness.registry_write_calls == []
    assert harness.lifecycle_lock_release_calls == []
    assert len(harness.lifecycle_locks.values) == 1
    assert result["account_attempt_outcome"]["status"] == (
        "PRE_SEND_FAILED_ATTEMPT_CONSUMED"
    )
    assert result["account_attempt_outcome"]["persistent"] is True
    blocked_state = pos["terminal_stop_emergency_recovery"]
    assert blocked_state["current_attempt_sequence"] == 0
    assert blocked_state["current_attempt_id"]
    assert blocked_state["client_order_id"].startswith("FEC1-")
    assert blocked_state["disposition"] == "PRE_SEND_CONSUMED"
    assert blocked_state["retry_authorization_status"] == (
        "NOT_REQUIRED_INITIAL_ATTEMPT"
    )
    assert blocked_state["reconciliation_basis"] == "INITIAL_ATTEMPT"
    account_records = _decoded_account_authority_records(harness)
    consumed = next(
        record
        for record in account_records
        if record.get("status") == "PRE_SEND_CONSUMED"
    )
    assert consumed["reason"] == "INCIDENT_STATE_PERSISTENCE_FAILED"
    assert consumed["failure_phase"] == "PRE_SEND_STATE_PERSISTENCE"
    assert harness.persisted_incident(result["incident_id"])["attempt_state"] == "READY_TO_SEND"
    failed_pending_writes = [
        operation
        for operation in harness.operation_log
        if operation.get("operation") == "PERSIST"
        and operation.get("attempt_state") == "BROKER_CALL_PENDING"
    ]
    assert failed_pending_writes == [
        {
            "operation": "PERSIST",
            "attempt_state": "BROKER_CALL_PENDING",
            "acknowledged": False,
        }
    ]


def test_management_loop_calls_terminal_guard_before_continue_and_skips_all_normal_management():
    class StopLoop(Exception):
        pass

    calls = []
    saved = []
    health = {}
    pos = _position(
        reconciliation_required=True,
        live_management_reconciliation_pending=True,
    )

    def forbidden(name, result=None):
        def probe(*args, **kwargs):
            calls.append(name)
            return copy.deepcopy(result)

        return probe

    globals_dict = {
        "get_positions": lambda: {pos["id"]: pos},
        "safe_float": _safe_float,
        "falcon_is_live_real_position": lambda _pos: True,
        "falcon_verify_live_disaster_stop": forbidden(
            "verify",
            {
                "management_allowed": False,
                "status": "DISASTER_STOP_TERMINAL_WITH_POSITION_OPEN",
            },
        ),
        "falcon_handle_terminal_stop_emergency": forbidden(
            "terminal_guard",
            {
                "incident_detected": True,
                "status": "TERMINAL_STOP_EMERGENCY_SENT_UNCONFIRMED",
            },
        ),
        "falcon_management_alert_decision": forbidden("common_alert", {"send": False}),
        "record_event": forbidden("record_event", {}),
        "safe_send_telegram": forbidden("telegram", False),
        "safe_fetch_price": forbidden("price", 76.50),
        "update_mfe_mae": forbidden("mfe_mae", pos),
        "falcon_handle_live_stop_cross": forbidden("ordinary_stop", {"closed": False}),
        "close_position": forbidden("close_position", {}),
        "falcon_try_execute_tp50_real_partial": forbidden("tp50", {}),
        "r_for_side": forbidden("r_calculation", 2.0),
        "falcon_apply_live_stop_update": forbidden("be_or_trailing", {}),
        "calc_chandelier_stop": forbidden("trailing", None),
        "falcon_refresh_management_safety_health": lambda _positions: calls.append("health_projection"),
        "save_positions": lambda positions: saved.append(copy.deepcopy(positions)),
        "refresh_health_stats": lambda: calls.append("refresh_health"),
        "data_hora_sp_str": lambda: "20/07/2026 12:00",
        "HEALTH": health,
        "time": SimpleNamespace(sleep=lambda _seconds: (_ for _ in ()).throw(StopLoop())),
        "traceback": SimpleNamespace(print_exc=lambda: calls.append("traceback")),
        "MANAGEMENT_SLEEP_SECONDS": 20,
        "FALCON_TP50_RETRY_SECONDS": 20,
        "BE_TRIGGER_R": 1.0,
        "BE_OFFSET_PCT": 0.0,
        "TRAIL_TRIGGER_R": 1.5,
        "fmt_price": str,
        "fmt_r": str,
        "fmt_pct": str,
        "pnl_pct_for_side": lambda *_args: 0.0,
    }
    namespace = _load_final_functions(("management_loop",), globals_dict)

    with pytest.raises(StopLoop):
        namespace["management_loop"]()

    assert calls[:2] == ["verify", "terminal_guard"]
    assert not {
        "common_alert",
        "record_event",
        "telegram",
        "price",
        "mfe_mae",
        "ordinary_stop",
        "close_position",
        "tp50",
        "r_calculation",
        "be_or_trailing",
        "trailing",
        "traceback",
    }.intersection(calls)
    assert calls[-2:] == ["health_projection", "refresh_health"]
    assert len(saved) == 1
    saved_pos = saved[0][pos["id"]]
    assert saved_pos["terminal_stop_emergency_last_decision"]["incident_detected"] is True
    assert saved_pos.get("tp50_hit") is not True
    assert saved_pos.get("be_moved") is not True
    assert saved_pos.get("trailing_active") is not True


def test_management_loop_reconciliation_pending_verifies_stop_and_blocks_normal_management():
    class StopLoop(Exception):
        pass

    calls = []
    saved = []
    health = {}
    pos = _position(
        reconciliation_required=True,
        live_management_reconciliation_pending=True,
    )

    def probe(name, result=None):
        def call(*args, **kwargs):
            calls.append(name)
            return copy.deepcopy(result)

        return call

    globals_dict = {
        "get_positions": lambda: {pos["id"]: pos},
        "safe_float": _safe_float,
        "falcon_is_live_real_position": lambda _pos: True,
        "falcon_verify_live_disaster_stop": probe(
            "verify",
            {
                "management_allowed": True,
                "status": "DISASTER_STOP_VERIFIED",
            },
        ),
        "falcon_handle_terminal_stop_emergency": probe(
            "terminal_guard",
            {"incident_detected": False},
        ),
        "falcon_management_alert_decision": probe("common_alert", {"send": False}),
        "record_event": probe("record_event", {}),
        "safe_send_telegram": probe("telegram", False),
        "safe_fetch_price": probe("price", 76.50),
        "update_mfe_mae": probe("mfe_mae", pos),
        "falcon_handle_live_stop_cross": probe("ordinary_stop", {"closed": False}),
        "close_position": probe("close_position", {}),
        "falcon_try_execute_tp50_real_partial": probe("tp50", {}),
        "r_for_side": probe("r_calculation", 2.0),
        "falcon_apply_live_stop_update": probe("be_or_trailing", {}),
        "calc_chandelier_stop": probe("trailing", None),
        "falcon_refresh_management_safety_health": lambda _positions: calls.append("health_projection"),
        "save_positions": lambda positions: saved.append(copy.deepcopy(positions)),
        "refresh_health_stats": lambda: calls.append("refresh_health"),
        "data_hora_sp_str": lambda: "20/07/2026 12:00",
        "HEALTH": health,
        "time": SimpleNamespace(sleep=lambda _seconds: (_ for _ in ()).throw(StopLoop())),
        "traceback": SimpleNamespace(print_exc=lambda: calls.append("traceback")),
        "MANAGEMENT_SLEEP_SECONDS": 20,
        "FALCON_TP50_RETRY_SECONDS": 20,
        "BE_TRIGGER_R": 1.0,
        "BE_OFFSET_PCT": 0.0,
        "TRAIL_TRIGGER_R": 1.5,
        "fmt_price": str,
        "fmt_r": str,
        "fmt_pct": str,
        "pnl_pct_for_side": lambda *_args: 0.0,
    }
    namespace = _load_final_functions(("management_loop",), globals_dict)

    with pytest.raises(StopLoop):
        namespace["management_loop"]()

    assert calls == ["verify", "health_projection", "refresh_health"]
    assert len(saved) == 1
    saved_pos = saved[0][pos["id"]]
    assert saved_pos["live_management_reconciliation_pending"] is True
    assert saved_pos["live_management_block_reason"] == (
        "ENTRY_ACK_PERSISTENCE_RECONCILIATION_REQUIRED"
    )
    assert saved_pos.get("tp50_hit") is not True
    assert saved_pos.get("be_moved") is not True
    assert saved_pos.get("trailing_active") is not True


def test_test_harness_has_no_runtime_falcon_import_or_real_execution_dependency():
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "bots.falcon" not in imported
    assert "broker" not in imported
    assert "requests" not in imported
    assert "redis" not in imported
    assert "socket" not in imported
