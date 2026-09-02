from __future__ import annotations

import ast
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import account_client_order_id as authority
import broker as real_broker
import execution_orchestrator as canonical_orchestrator
from falcon_execution_intent_identity import (
    derive_falcon_execution_intent_idempotency_key,
)
import pytest


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
        "derive_falcon_execution_intent_idempotency_key": (
            derive_falcon_execution_intent_idempotency_key
        ),
        "record_execution_broker_state": lambda _key, state, identity: {
            "ok": True,
            "persistent": True,
            "status": state,
            "identity": dict(identity),
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
            "_safe_float",
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
        "notional_usdt": 10.0,
    }
    payload.update(updates)
    payload.setdefault(
        "execution_intent_idempotency_key",
        derive_falcon_execution_intent_idempotency_key(
            signal_id=payload.get("signal_id"),
            lifecycle_id=payload.get("lifecycle_id"),
            decision_id=payload.get("decision_id") or payload.get("id"),
            client_order_attempt_id=(
                payload.get("client_order_attempt_id") or payload.get("signal_id")
            ),
            client_order_attempt_sequence=payload.get(
                "client_order_attempt_sequence", 0
            ),
        ),
    )
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
    unknown = first["payload"]["live_result"]
    assert unknown["client_order_id"]
    assert unknown["canonical_operation_id"]
    assert unknown["client_order_attempt_id"] == "ENTRY-ATTEMPT-0"
    assert unknown["client_order_id_reservation"]["canonical_operation_id"] == unknown[
        "canonical_operation_id"
    ]
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


def test_engine_passes_falcon_notional_and_ownership_once_to_the_only_broker_send():
    calls = []

    class SentBroker:
        def place_market_order(self, **kwargs):
            calls.append(kwargs)
            return {
                "ok": True,
                "sent": True,
                "status": "LIVE_SENT",
                "client_order_id": kwargs["client_tag"],
                "returned_client_order_id": kwargs["client_tag"],
                "returned_client_order_id_matches": True,
                "entry_acknowledged": True,
                "order_id": "ENTRY-1",
                "disaster_stop": {
                    "confirmed": True,
                    "order_id": "STOP-1",
                    "returned_client_order_id": "FDS1-RETURNED",
                    "returned_client_order_id_matches": True,
                    "stop_materially_valid": True,
                    "stop_operationally_armed": True,
                    "stop_status_active": True,
                },
            }

    def reserve(identity, *, client_order_id, **kwargs):
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
        }

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        SentBroker(),
        reserve,
        lambda *_args, **_kwargs: {"ok": True},
    )
    ownership = {"allowed": True, "requested_symbol": "SOLUSDT"}
    result = helpers.run_execution_engine(
        _entry_payload(
            notional_usdt=10.0,
            falcon_position_ownership_limit=ownership,
        ),
        mode="LIVE",
        dry_run=False,
    )

    assert result["payload"]["live_result"]["sent"] is True
    broker_state_identity = result["payload"]["live_result"][
        "engine_broker_state"
    ]["identity"]
    assert broker_state_identity["returned_client_order_id"] == calls[0]["client_tag"]
    assert broker_state_identity["returned_client_order_id_matches"] is True
    assert broker_state_identity["disaster_stop"]["stop_operationally_armed"] is True
    assert len(calls) == 1
    assert calls[0]["notional_usdt"] == 10.0
    assert "margin_usdt" not in calls[0]
    assert calls[0]["falcon_position_ownership_limit"] == ownership
    basis = result["payload"]["live_result"]["falcon_sizing_basis"]
    assert basis["authority"] == "REAL_PILOT_GUARD_APPROVED_NOTIONAL_USDT"
    assert basis["approved_notional_usdt"] == basis["payload_notional_usdt"] == 10.0
    assert basis["monetary_tolerance_usdt"] >= 0.01


def test_orchestrator_projection_preserves_only_bounded_strict_broker_proofs():
    projected = canonical_orchestrator._broker_execution_identity_projection(
        {
            "client_order_id": "ENT1-EXPECTED",
            "returned_client_order_id": "ENT1-EXPECTED",
            "returned_client_order_id_matches": True,
            "disaster_stop": {
                "confirmed": True,
                "order_id": "STOP-1",
                "returned_client_order_id": "FDS1-EXPECTED",
                "returned_client_order_id_matches": True,
                "stop_status_active": True,
                "stop_status_values": ["OPEN"],
                "stop_materially_valid": True,
                "stop_operationally_armed": True,
                "attempt_outcome_persistence_ok": False,
                "reconciliation_required": True,
                "raw": {"apiKey": "must-not-survive"},
                "stop_material_confirmation": {"unbounded": "must-not-survive"},
            },
        }
    )

    assert projected["returned_client_order_id"] == "ENT1-EXPECTED"
    assert projected["returned_client_order_id_matches"] is True
    stop = projected["disaster_stop"]
    assert stop["confirmed"] is True
    assert stop["returned_client_order_id"] == "FDS1-EXPECTED"
    assert stop["returned_client_order_id_matches"] is True
    assert stop["stop_status_active"] is True
    assert stop["stop_status_values"] == ["OPEN"]
    assert stop["stop_materially_valid"] is True
    assert stop["stop_operationally_armed"] is True
    assert stop["attempt_outcome_persistence_ok"] is False
    assert stop["reconciliation_required"] is True
    assert "raw" not in stop
    assert "stop_material_confirmation" not in stop


def test_engine_preserves_preexisting_broker_kwargs_for_non_falcon_bots():
    calls = []

    class SentBroker:
        def place_market_order(self, **kwargs):
            calls.append(dict(kwargs))
            return {
                "ok": True,
                "sent": True,
                "status": "LIVE_SENT",
                "client_order_id": kwargs["client_tag"],
            }

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        SentBroker(),
        lambda *_args, **kwargs: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": kwargs["client_order_id"],
        },
        lambda *_args, **_kwargs: {"ok": True},
    )
    result = helpers.run_execution_engine(
        _entry_payload(bot="SMART_PREDATOR", notional_usdt=99.0),
        mode="LIVE",
        dry_run=False,
    )

    assert result["payload"]["live_result"]["sent"] is True
    assert len(calls) == 1
    assert "notional_usdt" not in calls[0]
    assert "falcon_position_ownership_limit" not in calls[0]
    assert calls[0]["margin_usdt"] == 10.0
    assert set(calls[0]) == {
        "symbol",
        "side",
        "margin_usdt",
        "reduce_only",
        "client_tag",
        "leverage",
        "bot",
        "risk_pct",
        "execution_auth_token",
        "stop_loss_price",
        "client_order_id_reservation",
        "disaster_stop_client_order_id_factory",
    }


def test_engine_blocks_falcon_margin_notional_divergence_before_broker():
    calls = []

    class Broker:
        def place_market_order(self, **kwargs):
            calls.append(kwargs)
            pytest.fail("Falcon sizing mismatch must be blocked before broker")

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        Broker(),
        lambda *_args, **_kwargs: pytest.fail("sizing mismatch must not reserve"),
        lambda *_args, **_kwargs: pytest.fail("sizing mismatch must not record outcome"),
    )
    result = helpers.run_execution_engine(
        _entry_payload(notional_usdt=12.5), mode="LIVE", dry_run=False
    )

    live = result["payload"]["live_result"]
    assert result["payload"]["status"] == "FALCON_SIZING_MISMATCH_BLOCKED"
    assert live["sent"] is False
    assert live["falcon_sizing_basis"]["approved_notional_usdt"] == 10.0
    assert live["falcon_sizing_basis"]["payload_notional_usdt"] == 12.5
    assert calls == []


def test_real_engine_calls_orchestrator_then_pilot_guard_then_broker_once():
    calls = []

    class Broker:
        def place_market_order(self, **kwargs):
            calls.append(("broker", dict(kwargs)))
            return {
                "ok": True,
                "sent": True,
                "status": "LIVE_SENT",
                "client_order_id": kwargs["client_tag"],
            }

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        Broker(),
        lambda identity, *, client_order_id, **_kwargs: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
        },
        lambda *_args, **_kwargs: {"ok": True},
    )

    def orchestrator(**kwargs):
        calls.append(("orchestrator", dict(kwargs["payload"])))
        return {
            "ok": True,
            "payload": {
                "status": "READY_FOR_EXECUTION",
                "idempotency_key": "IDEM-ENGINE-1",
                "identity": {"lifecycle_id": kwargs["payload"]["lifecycle_id"]},
            },
        }

    def pilot_guard(**kwargs):
        calls.append(("pilot_guard", dict(kwargs["payload"])))
        return {
            "allowed": True,
            "status": "REAL_PILOT_ALLOWED",
            "reasons": [],
            "trade": {
                "bot": "FALCON",
                "symbol": "SOLUSDT",
                "side": "LONG",
                "margin_usdt": 10.0,
                "leverage": 1,
                "notional_usdt": 10.0,
                "risk_pct": 0.5,
                "stop": 75.8,
            },
        }

    namespace["orchestrate_execution"] = orchestrator
    namespace["validate_real_pilot_guard"] = pilot_guard
    payload = _entry_payload(notional_usdt=10.0)
    result = helpers.run_execution_engine(payload, mode="LIVE", dry_run=False)

    assert result["payload"]["live_result"]["sent"] is True
    assert [name for name, _value in calls] == [
        "orchestrator",
        "pilot_guard",
        "broker",
    ]
    assert calls[0][1]["signal_id"] == calls[1][1]["signal_id"] == "SIGNAL-1"
    assert calls[0][1]["lifecycle_id"] == calls[1][1]["lifecycle_id"] == "LC-FALCON-SOL-1"
    assert calls[2][1]["client_tag"].startswith("ENT1-")


def test_real_engine_consumes_falcon_intent_in_canonical_orchestrator_idempotency(
    tmp_path, monkeypatch
):
    """The real Engine reaches the existing persisted Orchestrator gate once."""
    seen_file = tmp_path / "execution_seen.json"
    monkeypatch.setattr(canonical_orchestrator, "EXECUTION_SEEN_FILE", seen_file)
    monkeypatch.setattr(canonical_orchestrator, "EXECUTION_LOG_FILE", tmp_path / "execution.jsonl")
    monkeypatch.setattr(canonical_orchestrator, "REAL_EXECUTION_ENABLED", True)

    calls = []

    class Broker:
        def place_market_order(self, **kwargs):
            calls.append(dict(kwargs))
            return {
                "ok": True,
                "sent": True,
                "status": "LIVE_SENT",
                "client_order_id": kwargs["client_tag"],
            }

    def reserve(identity, *, client_order_id, **_kwargs):
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
        }

    def build_engine():
        helpers, namespace = _engine_helpers()
        _configure_engine_runtime(
            namespace, Broker(), reserve, lambda *_args, **_kwargs: {"ok": True}
        )
        namespace["orchestrate_execution"] = canonical_orchestrator.orchestrate_execution
        namespace["record_execution_broker_state"] = (
            canonical_orchestrator.record_execution_broker_state
        )
        return helpers

    payload = _entry_payload(
        decision="ALLOW",
        setup="FALCON15",
    )
    engine = build_engine()
    first = engine.run_execution_engine(dict(payload), mode="LIVE", dry_run=False)
    second = engine.run_execution_engine(dict(payload), mode="LIVE", dry_run=False)

    assert first["payload"]["live_result"]["sent"] is True
    assert first["payload"]["plan"]["execution_intent_idempotency_key"] == payload[
        "execution_intent_idempotency_key"
    ]
    assert first["payload"]["live_result"]["client_order_id_reservation"][
        "execution_intent_idempotency_key"
    ] == payload["execution_intent_idempotency_key"]
    assert second["payload"]["status"] == "LIVE_BLOCKED_BY_ORCHESTRATOR"
    assert second["payload"]["plan"]["status"] == "DUPLICATE_BLOCKED"
    assert len(calls) == 1

    # A fresh Engine process sees the persisted canonical Orchestrator record.
    restarted = build_engine().run_execution_engine(
        dict(payload), mode="LIVE", dry_run=False
    )
    assert restarted["payload"]["plan"]["status"] == "DUPLICATE_BLOCKED"
    assert len(calls) == 1

    conflicting_lifecycle = dict(
        payload, lifecycle_id="LC-FALCON-SOL-2", signal_id="SIGNAL-2"
    )
    conflict = engine.run_execution_engine(
        conflicting_lifecycle, mode="LIVE", dry_run=False
    )
    assert conflict["payload"]["status"] == "EXECUTION_INTENT_IDENTITY_CONFLICT"
    assert conflict["payload"]["sent"] is False
    assert len(calls) == 1

    distinct_lifecycle = _entry_payload(
        decision="ALLOW",
        setup="FALCON15",
        lifecycle_id="LC-FALCON-SOL-2",
        signal_id="SIGNAL-2",
    )
    different = engine.run_execution_engine(distinct_lifecycle, mode="LIVE", dry_run=False)
    assert different["payload"]["live_result"]["sent"] is True
    assert len(calls) == 2

    concurrent_payload = _entry_payload(
        decision="ALLOW",
        setup="FALCON15",
        lifecycle_id="LC-FALCON-CONCURRENT",
        signal_id="SIGNAL-CONCURRENT",
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _unused: engine.run_execution_engine(
                    dict(concurrent_payload), mode="LIVE", dry_run=False
                ),
                range(2),
            )
        )
    assert sum(
        (item["payload"].get("live_result") or {}).get("sent") is True
        for item in results
    ) == 1
    assert len(calls) == 3

    new_attempt = _entry_payload(
        decision="ALLOW",
        setup="FALCON15",
        client_order_attempt_id="ENTRY-ATTEMPT-1",
        client_order_attempt_sequence=1,
    )
    allowed_new_attempt = engine.run_execution_engine(
        new_attempt, mode="LIVE", dry_run=False
    )
    assert allowed_new_attempt["payload"]["live_result"]["sent"] is True
    assert len(calls) == 4


def test_real_engine_persists_exact_pending_identity_before_broker_unknown(
    tmp_path, monkeypatch
):
    seen_file = tmp_path / "execution_seen.json"
    monkeypatch.setattr(canonical_orchestrator, "EXECUTION_SEEN_FILE", seen_file)
    monkeypatch.setattr(canonical_orchestrator, "EXECUTION_LOG_FILE", tmp_path / "execution.jsonl")
    monkeypatch.setattr(canonical_orchestrator, "REAL_EXECUTION_ENABLED", True)
    calls = []

    class AcceptedThenUnknownBroker:
        def place_market_order(self, **kwargs):
            calls.append(dict(kwargs))
            raise TimeoutError("accepted locally; result lost")

    def reserve(identity, *, client_order_id, **_kwargs):
        return {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
            "attempt_sequence": identity["attempt_sequence"],
            "attempt_identity_hash": "HASH-EXACT-1",
            "lifecycle_id": identity["lifecycle_id"],
            "persistent": True,
        }

    def build_engine():
        helpers, namespace = _engine_helpers()
        _configure_engine_runtime(
            namespace,
            AcceptedThenUnknownBroker(),
            reserve,
            lambda *_args, **_kwargs: {"ok": True},
        )
        namespace["orchestrate_execution"] = canonical_orchestrator.orchestrate_execution
        namespace["record_execution_broker_state"] = (
            canonical_orchestrator.record_execution_broker_state
        )
        return helpers

    payload = _entry_payload(decision="ALLOW", setup="FALCON15")
    engine = build_engine()
    first = engine.run_execution_engine(dict(payload), mode="LIVE", dry_run=False)
    unknown = first["payload"]["live_result"]

    assert len(calls) == 1
    assert calls[0]["client_tag"] == unknown["client_order_id"]
    assert unknown["sent"] is None
    assert unknown["engine_broker_state"]["status"] == (
        "ENGINE_BROKER_SEND_OUTCOME_UNKNOWN"
    )
    persisted = canonical_orchestrator.load_execution_broker_state(
        first["payload"]["plan"]["idempotency_key"]
    )
    identity = persisted["state"]["identity"]
    for field in (
        "client_order_id",
        "client_order_id_reservation",
        "canonical_operation_id",
        "attempt_id",
        "signal_id",
        "lifecycle_id",
        "execution_intent_idempotency_key",
    ):
        assert identity[field]

    second = engine.run_execution_engine(dict(payload), mode="LIVE", dry_run=False)
    restarted = build_engine().run_execution_engine(
        dict(payload), mode="LIVE", dry_run=False
    )
    assert second["payload"]["plan"]["status"] == "DUPLICATE_BLOCKED"
    assert restarted["payload"]["plan"]["status"] == "DUPLICATE_BLOCKED"
    assert len(calls) == 1


def test_orchestrator_pending_falcon_scan_is_bounded_and_terminal_state_releases_gate(
    tmp_path, monkeypatch
):
    seen_file = tmp_path / "execution_seen.json"
    monkeypatch.setattr(canonical_orchestrator, "EXECUTION_SEEN_FILE", seen_file)
    identity = {
        "bot": "FALCON",
        "client_order_id": "ENT1-PENDING",
        "canonical_operation_id": "OP-PENDING",
        "attempt_id": "ATTEMPT-PENDING",
        "client_order_attempt_id": "ATTEMPT-PENDING",
        "client_order_attempt_sequence": 0,
        "signal_id": "SIGNAL-PENDING",
        "lifecycle_id": "LIFECYCLE-PENDING",
        "decision_id": "DECISION-PENDING",
        "execution_intent_idempotency_key": "FALCON-ENGINE-INTENT:PENDING",
        "orchestrator_idempotency_key": "ORCH-PENDING",
        "symbol": "SOLUSDT",
        "side": "LONG",
    }
    canonical_orchestrator._save_seen(
        {
            "ORCH-PENDING": {
                "bot": "FALCON",
                "broker_execution_state": {
                    "state": "ENGINE_BROKER_CALL_PENDING",
                    "identity": dict(identity),
                },
            },
            "OTHER": {
                "bot": "PREDATOR",
                "broker_execution_state": {
                    "state": "ENGINE_BROKER_SEND_OUTCOME_UNKNOWN",
                    "identity": {"bot": "PREDATOR"},
                },
            },
        }
    )

    pending = canonical_orchestrator.find_falcon_pending_broker_states()
    assert pending["ok"] is True
    assert pending["status"] == "FALCON_ENGINE_BROKER_RECONCILIATION_PENDING"
    assert pending["pending_count"] == 1
    assert pending["pending"][0]["identity"]["client_order_id"] == "ENT1-PENDING"

    terminal = canonical_orchestrator.record_execution_broker_state(
        "ORCH-PENDING", "ENGINE_BROKER_RECONCILED_TERMINAL", identity
    )
    assert terminal["ok"] is True
    assert terminal["persistent"] is True
    assert canonical_orchestrator.find_falcon_pending_broker_states()["pending"] == []


def test_engine_to_real_broker_uses_falcon_approved_notional_without_margin(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        real_broker,
        "execution_config_for_bot",
        lambda **_kwargs: {
            "margin_usdt": 20.0,
            "leverage": 3.0,
            "effective_notional_usdt": 60.0,
        },
    )
    monkeypatch.setattr(real_broker, "is_real_live_send_enabled", lambda: False)
    monkeypatch.setattr(
        real_broker, "_automatic_broker_preview_firewall", lambda **_kwargs: {"blocked": False}
    )
    monkeypatch.setattr(real_broker, "_infer_bot_for_audit", lambda **kwargs: kwargs["bot"])
    monkeypatch.setattr(real_broker, "_classify_preview_audit", lambda **_kwargs: "TEST")
    monkeypatch.setattr(real_broker, "log_execution_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(real_broker, "log_execution_audit_event", lambda *_args, **_kwargs: None)

    def preview(*_args, **kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "constraints_ok": True,
            "symbol": "SOLUSDT",
            "side": "LONG",
            "margin_usdt": 20.0,
            "leverage": 3.0,
            "notional_usdt": kwargs["notional_usdt"],
            "planned_exposure_usdt": kwargs["notional_usdt"],
            "actual_exposure_usdt": kwargs["notional_usdt"],
            "client_order_id": kwargs["client_tag"],
        }

    monkeypatch.setattr(real_broker, "build_order_preview", preview)
    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        real_broker,
        lambda identity, *, client_order_id, **_kwargs: {
            "ok": True,
            "send_allowed": True,
            "status": "RESERVED_UNIQUE",
            "client_order_id": client_order_id,
            "canonical_operation_id": identity["canonical_operation_id"],
            "attempt_id": identity["attempt_id"],
            "attempt_sequence": identity["attempt_sequence"],
            "attempt_identity_hash": "SIZING-HASH",
            "lifecycle_id": identity["lifecycle_id"],
            "persistent": True,
        },
        lambda *_args, **_kwargs: {"ok": True},
    )
    namespace["validate_real_pilot_guard"] = lambda **kwargs: {
        "allowed": True,
        "status": "REAL_PILOT_ALLOWED",
        "reasons": [],
        "trade": {
            "bot": "FALCON",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "margin_usdt": 20.0,
            "leverage": 3.0,
            "notional_usdt": 60.0,
            "risk_pct": 0.5,
            "stop": kwargs["payload"]["sl"],
        },
    }
    result = helpers.run_execution_engine(
        _entry_payload(decision="ALLOW", setup="FALCON15", notional_usdt=60.0),
        mode="LIVE",
        dry_run=False,
    )

    assert result["payload"]["live_result"]["sent"] is False
    assert captured["notional_usdt"] == 60.0
    assert captured["notional_usdt"] != 180.0


@pytest.mark.parametrize(
    "changes",
    [
        {"lifecycle_id": "LC-FALCON-OTHER"},
        {"signal_id": "SIGNAL-OTHER"},
        {
            "client_order_attempt_id": "ENTRY-ATTEMPT-OTHER",
            "client_order_attempt_sequence": 1,
        },
    ],
)
def test_engine_blocks_reused_falcon_intent_key_for_conflicting_identity(changes):
    calls = {"broker": 0, "reserve": 0}

    class ForbiddenBroker:
        def place_market_order(self, **_kwargs):
            calls["broker"] += 1
            pytest.fail("intent conflict must not reach broker")

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        ForbiddenBroker(),
        lambda *_args, **_kwargs: calls.update(reserve=calls["reserve"] + 1),
        lambda *_args, **_kwargs: pytest.fail("intent conflict must not persist an outcome"),
    )
    original = _entry_payload(decision="ALLOW", setup="FALCON15")
    conflicting = dict(original, **changes)
    result = helpers.run_execution_engine(conflicting, mode="LIVE", dry_run=False)

    assert result["payload"]["status"] == "EXECUTION_INTENT_IDENTITY_CONFLICT"
    assert result["payload"]["sent"] is False
    assert calls == {"broker": 0, "reserve": 0}


def test_real_engine_pilot_deny_or_orchestrator_error_never_reaches_broker():
    calls = {"broker": 0, "orchestrator": 0, "pilot": 0}

    class Broker:
        def place_market_order(self, **_kwargs):
            calls["broker"] += 1
            pytest.fail("blocked Engine path cannot reach broker")

    helpers, namespace = _engine_helpers()
    _configure_engine_runtime(
        namespace,
        Broker(),
        lambda *_args, **_kwargs: pytest.fail("deny must not reserve"),
        lambda *_args, **_kwargs: pytest.fail("deny must not record"),
    )

    def ready_orchestrator(**_kwargs):
        calls["orchestrator"] += 1
        return {"ok": True, "payload": {"status": "READY_FOR_EXECUTION"}}

    def deny_guard(**_kwargs):
        calls["pilot"] += 1
        return {"allowed": False, "status": "REAL_PILOT_BLOCKED", "reasons": ["deny"]}

    namespace["orchestrate_execution"] = ready_orchestrator
    namespace["validate_real_pilot_guard"] = deny_guard
    denied = helpers.run_execution_engine(_entry_payload(notional_usdt=10.0), mode="LIVE", dry_run=False)
    assert denied["payload"]["status"] == "LIVE_BLOCKED_BY_PILOT_GUARD"
    assert calls == {"broker": 0, "orchestrator": 1, "pilot": 1}

    def broken_orchestrator(**_kwargs):
        calls["orchestrator"] += 1
        raise RuntimeError("orchestrator failure")

    namespace["orchestrate_execution"] = broken_orchestrator
    with pytest.raises(RuntimeError, match="orchestrator failure"):
        helpers.run_execution_engine(_entry_payload(notional_usdt=10.0), mode="LIVE", dry_run=False)
    assert calls["broker"] == 0


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
