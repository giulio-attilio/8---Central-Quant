from __future__ import annotations

import ast
import hashlib
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import account_client_order_id as authority


ROOT = Path(__file__).resolve().parents[1]


def _compile_functions(path: Path, names: set[str], namespace: dict[str, Any]):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    assert {node.name for node in nodes} == names
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in names})


def _engine_helpers(**overrides):
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "Optional": Optional,
        "ACCOUNT_CLIENT_ORDER_ID_IMPORT_ERROR": None,
        "ROLE_ENTRY": authority.ROLE_ENTRY,
        "ROLE_INITIAL_DISASTER_STOP": authority.ROLE_INITIAL_DISASTER_STOP,
        "build_canonical_operation_id": authority.build_canonical_operation_id,
        "generate_account_client_order_id": authority.generate_account_client_order_id,
        "normalize_account_client_order_id": authority.normalize_account_client_order_id,
        "reserve_account_client_order_attempt": lambda *args, **kwargs: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": kwargs["client_order_id"],
            "identity": dict(args[0]),
        },
    }
    namespace.update(overrides)
    return _compile_functions(
        ROOT / "execution_engine.py",
        {
            "_execution_entry_client_order_identity",
            "_execution_disaster_stop_reservation_factory",
            "_normalize_symbol",
            "_normalize_side",
            "_safe_mode",
            "run_execution_engine",
        },
        namespace,
    ), namespace


def _predator_helpers(**overrides):
    namespace = {
        "json": json,
        "hashlib": hashlib,
        "ROLE_ENTRY": authority.ROLE_ENTRY,
        "ROLE_INITIAL_DISASTER_STOP": authority.ROLE_INITIAL_DISASTER_STOP,
        "build_canonical_operation_id": authority.build_canonical_operation_id,
        "generate_account_client_order_id": authority.generate_account_client_order_id,
        "reserve_account_client_order_attempt": lambda *args, **kwargs: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": kwargs["client_order_id"],
            "identity": dict(args[0]),
        },
        "redis": object(),
        "bandwidth_redis_set_if_absent": object(),
        "bandwidth_redis_get_authoritative": object(),
        "PREDATOR_MODE": "LIVE",
        "bingx_broker": SimpleNamespace(is_real_live_send_enabled=lambda: True),
    }
    namespace.update(overrides)
    return _compile_functions(
        ROOT / "bots" / "predator.py",
        {
            "nome_limpo",
            "_predator_entry_account_identity",
            "_predator_reserve_entry_attempt",
            "_predator_disaster_stop_reservation_factory",
            "_predator_broker_live_send_state",
            "execute_predator_signal_safe",
        },
        namespace,
    ), namespace


def _entry_payload(**updates):
    payload = {
        "bot": "FALCON",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "lifecycle_id": "LC-FALCON-SOL-1",
        "client_order_attempt_id": "ENTRY-ATTEMPT-0",
        "client_order_attempt_sequence": 0,
        "signal_id": "SIGNAL-1",
        "entry": 76.11,
        "sl": 75.80,
    }
    payload.update(updates)
    return payload


def _predator_signal(**updates):
    signal = {
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "SMART_PREDATOR",
        "lifecycle_id": "LC-PREDATOR-SOL-1",
        "client_order_attempt_id": "PREDATOR-ENTRY-ATTEMPT-0",
        "client_order_attempt_sequence": 0,
        "signal_id": "PREDATOR-SIGNAL-1",
        "timestamp": "2026-07-20T12:00:00Z",
        "entry": 76.11,
        "sl": 75.80,
        "tp50": 76.42,
        "risk_pct": 0.5,
    }
    signal.update(updates)
    return signal


def test_execution_live_requires_explicit_lifecycle_and_separates_operation_attempt_id():
    helpers, _ = _engine_helpers()
    missing = helpers._execution_entry_client_order_identity(
        _entry_payload(lifecycle_id=None),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    assert missing["status"] == "CLIENT_ORDER_LIFECYCLE_ID_REQUIRED"

    first = helpers._execution_entry_client_order_identity(
        _entry_payload(),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    second = helpers._execution_entry_client_order_identity(
        _entry_payload(
            client_order_attempt_id="ENTRY-ATTEMPT-1",
            client_order_attempt_sequence=1,
        ),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )

    assert first["ok"] is second["ok"] is True
    assert first["canonical_operation_id"] == second["canonical_operation_id"]
    assert first["attempt_id"] != second["attempt_id"]
    assert first["client_order_id"] != second["client_order_id"]
    assert first["client_order_id"].startswith("ENT1-")
    assert first["client_order_id"] == first["client_order_id"].upper()
    assert len(first["client_order_id"]) <= 32

    lowercase_supplied = helpers._execution_entry_client_order_identity(
        _entry_payload(client_order_id=first["client_order_id"].lower()),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    assert lowercase_supplied["ok"] is True
    assert lowercase_supplied["client_order_id"] == first["client_order_id"]


def test_execution_initial_stop_is_a_separate_fds1_attempt_bound_to_entry():
    reservations = []

    def reserve(identity, *, client_order_id, **kwargs):
        reservations.append((dict(identity), client_order_id))
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
        }

    helpers, _ = _engine_helpers(reserve_account_client_order_attempt=reserve)
    entry = helpers._execution_entry_client_order_identity(
        _entry_payload(),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    stop_factory = helpers._execution_disaster_stop_reservation_factory(entry)
    stop = stop_factory(
        entry_order_id="BROKER-ENTRY-1",
        entry_client_order_id=entry["client_order_id"],
        symbol="SOLUSDT",
        side="LONG",
        revision=0,
        attempt=0,
    )

    stop_identity, stop_id = reservations[-1]
    assert stop["status"] == "RESERVED_UNIQUE"
    assert stop_id.startswith("FDS1-")
    assert stop_id != entry["client_order_id"]
    assert stop_identity["role"] == authority.ROLE_INITIAL_DISASTER_STOP
    assert stop_identity["entry_order_id"] == "BROKER-ENTRY-1"
    assert stop_identity["entry_client_order_id"] == entry["client_order_id"]
    assert stop_identity["canonical_operation_id"] != entry["canonical_operation_id"]


def _configure_engine_runtime(namespace, broker, reserve, outcome):
    namespace.update(
        {
            "VERSION": "TEST",
            "BROKER_IMPORT_ERROR": None,
            "ORCHESTRATOR_IMPORT_ERROR": None,
            "EXECUTION_AUTH_TOKEN_ENABLED": False,
            "EXECUTION_AUTH_TOKEN_TTL_SECONDS": 60,
            "EXECUTION_ENGINE_LOG_FILE": ROOT / "unused.jsonl",
            "PAPER_EXECUTION_ENABLED": False,
            "PAPER_EXECUTOR_IMPORT_ERROR": None,
            "REAL_EXECUTION_ENABLED": True,
            "REAL_PILOT_ENABLED": True,
            "central_broker": broker,
            "execute_paper_from_engine": None,
            "time": time,
            "_now_br": lambda: "2026-07-20T12:00:00Z",
            "_append_jsonl": lambda *args, **kwargs: None,
            "_append_audit": lambda *args, **kwargs: None,
            "orchestrate_execution": lambda **kwargs: {
                "ok": True,
                "payload": {
                    "status": "READY_FOR_EXECUTION",
                    "idempotency_key": kwargs["payload"].get("signal_id"),
                    "identity": {
                        "lifecycle_id": kwargs["payload"].get("lifecycle_id")
                    },
                },
            },
            "validate_real_pilot_guard": lambda **kwargs: {
                "allowed": True,
                "status": "REAL_PILOT_ALLOWED",
                "reasons": [],
                "trade": {
                    "bot": kwargs["payload"].get("bot"),
                    "symbol": kwargs["payload"].get("symbol"),
                    "side": kwargs["payload"].get("side"),
                    "margin_usdt": 10.0,
                    "leverage": 1,
                    "risk_pct": 0.5,
                    "stop": kwargs["payload"].get("sl"),
                    "notional_usdt": 10.0,
                },
            },
            "execution_confirmation_guard": lambda **kwargs: {
                "allowed": True,
                "status": "CONFIRMATION_ALLOWED",
            },
            "reserve_account_client_order_attempt": reserve,
            "record_account_client_order_attempt_outcome": outcome,
        }
    )


def test_execution_dry_run_does_not_reserve_or_record_attempt_outcome():
    calls = {"broker": [], "reserve": 0, "outcome": 0}

    class PreviewBroker:
        def place_market_order(self, **kwargs):
            calls["broker"].append(kwargs)
            return {"ok": True, "sent": False, "status": "VERIFY"}

    helpers, namespace = _engine_helpers()

    def forbidden_reserve(*args, **kwargs):
        calls["reserve"] += 1
        raise AssertionError("dry-run reserved a factual attempt")

    def forbidden_outcome(*args, **kwargs):
        calls["outcome"] += 1
        raise AssertionError("dry-run recorded a factual outcome")

    _configure_engine_runtime(
        namespace, PreviewBroker(), forbidden_reserve, forbidden_outcome
    )
    result = helpers.run_execution_engine(
        _entry_payload(lifecycle_id=None), mode="LIVE", dry_run=True
    )

    assert result["payload"]["status"] == "LIVE_PREVIEW_OK"
    assert calls["reserve"] == calls["outcome"] == 0
    assert len(calls["broker"]) == 1
    assert calls["broker"][0]["client_order_id_reservation"] is None
    assert calls["broker"][0]["disaster_stop_client_order_id_factory"] is None


def test_execution_timeout_is_unknown_and_same_attempt_is_not_sent_twice():
    calls = {"broker": 0, "reserve": 0, "outcomes": []}
    receipts = {}

    class TimeoutBroker:
        def place_market_order(self, **kwargs):
            calls["broker"] += 1
            raise TimeoutError("simulated local timeout")

    def reserve(identity, *, client_order_id, **kwargs):
        calls["reserve"] += 1
        key = (identity["canonical_operation_id"], identity["attempt_id"])
        if key in receipts:
            return {
                **receipts[key],
                "ok": True,
                "send_allowed": False,
                "status": "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED",
            }
        receipt = {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
        }
        receipts[key] = receipt
        return receipt

    def outcome(receipt, *, outcome_state, **kwargs):
        calls["outcomes"].append(outcome_state)
        return {"ok": True, "status": outcome_state}

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(namespace, TimeoutBroker(), reserve, outcome)
    first = helpers.run_execution_engine(_entry_payload(), mode="LIVE", dry_run=False)
    second = helpers.run_execution_engine(_entry_payload(), mode="LIVE", dry_run=False)

    assert first["payload"]["live_result"]["sent"] is None
    assert first["payload"]["live_result"]["send_outcome_unknown"] is True
    assert first["payload"]["live_result"]["reconciliation_required"] is True
    assert calls["outcomes"] == ["CREATE_ORDER_OUTCOME_UNKNOWN"]
    assert second["payload"]["live_result"]["status"] == (
        "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
    )
    assert calls["broker"] == 1


def test_execution_overlength_client_order_id_blocks_before_reservation_or_broker():
    calls = {"broker": 0, "reserve": 0, "outcome": 0}

    class ForbiddenBroker:
        def place_market_order(self, **kwargs):
            calls["broker"] += 1
            raise AssertionError("broker called with overlength clientOrderID")

    def forbidden_reserve(*args, **kwargs):
        calls["reserve"] += 1
        raise AssertionError("overlength clientOrderID reached reservation")

    def forbidden_outcome(*args, **kwargs):
        calls["outcome"] += 1
        raise AssertionError("overlength clientOrderID recorded outcome")

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace, ForbiddenBroker(), forbidden_reserve, forbidden_outcome
    )
    result = helpers.run_execution_engine(
        _entry_payload(client_order_id="X" * 33), mode="LIVE", dry_run=False
    )

    live = result["payload"]["live_result"]
    assert live["status"] == "CLIENT_ORDER_ID_INVALID_LENGTH"
    assert live["sent"] is False
    assert calls == {"broker": 0, "reserve": 0, "outcome": 0}


def test_predator_identity_uses_ent1_and_initial_stop_uses_fds1():
    reservations = []

    def reserve(identity, *, client_order_id, **kwargs):
        reservations.append((dict(identity), client_order_id))
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
        }

    helpers, _ = _predator_helpers(reserve_account_client_order_attempt=reserve)
    entry = helpers._predator_entry_account_identity(_predator_signal())
    stop = helpers._predator_disaster_stop_reservation_factory(entry)(
        entry_order_id="PREDATOR-BROKER-ENTRY-1",
        entry_client_order_id=entry["client_order_id"],
        symbol="SOLUSDT",
        side="LONG",
        revision=0,
        attempt=0,
    )

    assert entry["client_order_id"].startswith("ENT1-")
    assert entry["canonical_operation_id"] != entry["attempt_id"]
    assert stop["client_order_id"].startswith("FDS1-")
    stop_identity, stop_id = reservations[-1]
    assert stop_id == stop["client_order_id"]
    assert stop_identity["lifecycle_id"] == entry["lifecycle_id"]
    assert stop_identity["entry_client_order_id"] == entry["client_order_id"]


def _configure_predator_runtime(namespace, *, mode, broker, reserve, outcome):
    namespace.update(
        {
            "BOT_VERSION": "TEST",
            "BROKER_IMPORT_ERROR": None,
            "HEALTH": {},
            "PREDATOR_ALLOW_AUTOMATIC_BROKER_PREVIEW": True,
            "PREDATOR_AUTO_BROKER_PREVIEW_FIREWALL_ENABLED": True,
            "PREDATOR_AUTO_BROKER_READY_CHECK_ENABLED": False,
            "PREDATOR_EXECUTION_NOTIFY": False,
            "PREDATOR_MODE": mode,
            "PREDATOR_NOTIFY_AUTO_BROKER_PREVIEW_BLOCKED": False,
            "PREDATOR_REAL_LEVERAGE": 1,
            "PREDATOR_REAL_MARGIN_USDT": 10.0,
            "PREDATOR_REAL_NOTIONAL_USDT": 10.0,
            "bingx_broker": broker,
            "execution_mode_active": lambda: True,
            "_predator_origin_type": lambda value: "MANUAL_CONSOLE",
            "data_hora_sp_str": lambda: "20/07/2026 12:00",
            "predator_local_live_gate": lambda sig: {"allowed": True},
            "central_can_open_trade": lambda sig: {
                "allowed": True,
                "decision": "ALLOW",
            },
            "predator_should_block_automatic_broker_preview": lambda origin: (
                False,
                None,
            ),
            "broker_ready_payload": lambda: {"ok": True, "status": "READY"},
            "registrar_predator_execution_firewall_event": lambda *args, **kwargs: None,
            "_predator_reserve_entry_attempt": reserve,
            "record_account_client_order_attempt_outcome": outcome,
            "update_position_execution_fields": lambda *args, **kwargs: None,
            "build_predator_execution_message": lambda *args, **kwargs: "TEST",
            "send_automatic_telegram": lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("Telegram called")
            ),
            "_safe_send_telegram_transport": None,
            "redis": object(),
            "bandwidth_redis_set_if_absent": object(),
        }
    )


def test_predator_verify_preview_does_not_reserve_or_record_outcome():
    calls = {"broker": [], "reserve": 0, "outcome": 0}

    class PreviewBroker:
        def is_real_live_send_enabled(self):
            raise AssertionError("VERIFY queried factual LIVE state")

        def place_market_order(self, *args, **kwargs):
            calls["broker"].append((args, kwargs))
            return {"ok": True, "sent": False, "status": "VERIFY"}

    helpers, namespace = _predator_helpers()

    def forbidden_reserve(*args, **kwargs):
        calls["reserve"] += 1
        raise AssertionError("VERIFY reserved a factual attempt")

    def forbidden_outcome(*args, **kwargs):
        calls["outcome"] += 1
        raise AssertionError("VERIFY recorded a factual outcome")

    _configure_predator_runtime(
        namespace,
        mode="VERIFY",
        broker=PreviewBroker(),
        reserve=forbidden_reserve,
        outcome=forbidden_outcome,
    )
    result = helpers.execute_predator_signal_safe(
        _predator_signal(),
        risk_prechecked={"allowed": True, "decision": "ALLOW"},
        local_gate_prechecked={"allowed": True},
        origin_type="MANUAL_CONSOLE",
    )

    assert result["broker_result"]["status"] == "VERIFY"
    assert result["broker_result"]["client_order_id_reservation"] is None
    assert calls["reserve"] == calls["outcome"] == 0
    assert len(calls["broker"]) == 1
    assert calls["broker"][0][1]["disaster_stop_client_order_id_factory"] is None


def test_predator_timeout_is_unknown_and_same_attempt_is_not_sent_twice():
    calls = {"broker": 0, "reserve": 0, "outcomes": []}
    reservations = {}

    class TimeoutBroker:
        def is_real_live_send_enabled(self):
            return True

        def place_market_order(self, *args, **kwargs):
            calls["broker"] += 1
            raise TimeoutError("simulated timeout")

    def reserve(account_identity):
        calls["reserve"] += 1
        key = (
            account_identity["canonical_operation_id"],
            account_identity["attempt_id"],
        )
        if key in reservations:
            return {
                **reservations[key],
                "send_allowed": False,
                "status": "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED",
            }
        receipt = {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": account_identity["client_order_id"],
            "canonical_operation_id": account_identity["canonical_operation_id"],
            "attempt_id": account_identity["attempt_id"],
        }
        reservations[key] = receipt
        return receipt

    def outcome(receipt, *, outcome_state, **kwargs):
        calls["outcomes"].append(outcome_state)
        return {"ok": True, "status": outcome_state}

    helpers, namespace = _predator_helpers()
    broker = TimeoutBroker()
    _configure_predator_runtime(
        namespace, mode="LIVE", broker=broker, reserve=reserve, outcome=outcome
    )
    first = helpers.execute_predator_signal_safe(
        _predator_signal(),
        risk_prechecked={"allowed": True, "decision": "ALLOW"},
        local_gate_prechecked={"allowed": True},
        origin_type="MANUAL_CONSOLE",
    )
    second = helpers.execute_predator_signal_safe(
        _predator_signal(),
        risk_prechecked={"allowed": True, "decision": "ALLOW"},
        local_gate_prechecked={"allowed": True},
        origin_type="MANUAL_CONSOLE",
    )

    first_result = first["broker_result"]
    assert first_result["sent"] is None
    assert first_result["send_outcome_unknown"] is True
    assert first_result["reconciliation_required"] is True
    assert calls["outcomes"] == ["CREATE_ORDER_OUTCOME_UNKNOWN"]
    assert second["broker_result"]["status"] == (
        "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
    )
    assert calls["broker"] == 1


def test_predator_pre_send_failure_consumes_attempt_without_automatic_retry():
    calls = {"broker": 0, "outcomes": []}
    reserved = False

    class PreSendFailureBroker:
        def is_real_live_send_enabled(self):
            return True

        def place_market_order(self, *args, **kwargs):
            calls["broker"] += 1
            return {
                "ok": False,
                "status": "BROKER_PRE_SEND_BLOCKED",
                "sent": False,
                "send_attempted": False,
            }

    def reserve(account_identity):
        nonlocal reserved
        if reserved:
            return {
                "ok": True,
                "send_allowed": False,
                "status": "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED",
                "client_order_id": account_identity["client_order_id"],
            }
        reserved = True
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": account_identity["client_order_id"],
            "canonical_operation_id": account_identity["canonical_operation_id"],
            "attempt_id": account_identity["attempt_id"],
        }

    def outcome(receipt, *, outcome_state, **kwargs):
        calls["outcomes"].append(outcome_state)
        return {"ok": True, "status": outcome_state}

    helpers, namespace = _predator_helpers()
    _configure_predator_runtime(
        namespace,
        mode="LIVE",
        broker=PreSendFailureBroker(),
        reserve=reserve,
        outcome=outcome,
    )
    first = helpers.execute_predator_signal_safe(
        _predator_signal(),
        risk_prechecked={"allowed": True, "decision": "ALLOW"},
        local_gate_prechecked={"allowed": True},
        origin_type="MANUAL_CONSOLE",
    )
    second = helpers.execute_predator_signal_safe(
        _predator_signal(),
        risk_prechecked={"allowed": True, "decision": "ALLOW"},
        local_gate_prechecked={"allowed": True},
        origin_type="MANUAL_CONSOLE",
    )

    assert first["broker_result"]["sent"] is False
    assert calls["outcomes"] == ["PRE_SEND_FAILED_ATTEMPT_CONSUMED"]
    assert second["broker_result"]["status"] == (
        "CLIENT_ORDER_ID_ALREADY_RESERVED_RECONCILIATION_REQUIRED"
    )
    assert calls["broker"] == 1


def test_pre_send_failure_consumes_attempt_and_authorized_retry_gets_new_id():
    class Ledger:
        def __init__(self):
            self.data = {}

        def set_if_absent(self, redis_client, key, value, **kwargs):
            assert redis_client is self
            if key in self.data:
                return False
            self.data[key] = value
            return True

        def get(self, redis_client, key, **kwargs):
            assert redis_client is self
            return self.data.get(key)

    ledger = Ledger()
    helpers, _ = _engine_helpers()
    first = helpers._execution_entry_client_order_identity(
        _entry_payload(),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    first_receipt = authority.reserve_account_client_order_attempt(
        first["identity"],
        client_order_id=first["client_order_id"],
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get,
        now=lambda: "2026-07-20T12:00:00Z",
    )
    authority.record_account_client_order_attempt_outcome(
        first_receipt,
        outcome_state="PRE_SEND_FAILED_ATTEMPT_CONSUMED",
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get,
        now=lambda: "2026-07-20T12:00:01Z",
    )
    repeated = authority.reserve_account_client_order_attempt(
        first["identity"],
        client_order_id=first["client_order_id"],
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get,
    )
    assert repeated["send_allowed"] is False

    second = helpers._execution_entry_client_order_identity(
        _entry_payload(
            client_order_attempt_id="ENTRY-ATTEMPT-1",
            client_order_attempt_sequence=1,
        ),
        {},
        bot="FALCON",
        symbol="SOLUSDT",
        side="LONG",
        require_explicit_lifecycle=True,
    )
    assert second["canonical_operation_id"] == first["canonical_operation_id"]
    assert second["client_order_id"] != first["client_order_id"]
    authorization = authority.authorize_account_client_order_next_attempt(
        canonical_operation_id=first["canonical_operation_id"],
        prior_attempt_id=first["attempt_id"],
        next_attempt_id=second["attempt_id"],
        next_attempt_sequence=1,
        reconciliation_status="NOT_CREATED",
        evidence_source="TEST_FACTUAL_RECONCILIATION",
        reconciled_at="2026-07-20T12:01:00Z",
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get,
    )
    assert authorization["ok"] is True
    second_receipt = authority.reserve_account_client_order_attempt(
        second["identity"],
        client_order_id=second["client_order_id"],
        redis_client=ledger,
        set_if_absent=ledger.set_if_absent,
        get_authoritative=ledger.get,
    )
    assert second_receipt["status"] == "RESERVED_UNIQUE"
    assert second_receipt["send_allowed"] is True


def test_engine_and_predator_have_no_client_order_id_slice_construction():
    for relative in ("execution_engine.py", "bots/predator.py"):
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript) or not isinstance(
                node.slice, ast.Slice
            ):
                continue
            expression = ast.unparse(node.value).lower()
            if any(token in expression for token in ("client_order", "client_tag")):
                violations.append((node.lineno, ast.unparse(node)))
        assert violations == [], f"destructive clientOrderID slices in {relative}: {violations}"
