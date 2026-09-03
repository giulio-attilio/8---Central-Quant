from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from falcon_execution_intent_identity import (
    derive_falcon_execution_intent_idempotency_key,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON = ROOT / "bots" / "falcon.py"
MAIN = ROOT / "main.py"


def _load_latest(path: Path, names: set[str], namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    latest = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in names:
            latest[node.name] = copy.deepcopy(node)
    assert set(latest) == names
    module = ast.Module(
        body=sorted(latest.values(), key=lambda node: node.lineno), type_ignores=[]
    )
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in names})


def _load_function_at_line(path: Path, name: str, lineno: int, namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == name
        and item.lineno == lineno
    )
    node = copy.deepcopy(node)
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def _load_first_function(path: Path, name: str, namespace: dict):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    node = copy.deepcopy(node)
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace[name]


def _load_auto_bridge_can_open_wrapper(namespace: dict):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "can_open_trade_decision"
        and any(
            isinstance(child, ast.Name)
            and child.id == "auto_real_execution_bridge_v1_process"
            for child in ast.walk(item)
        )
    )
    node = copy.deepcopy(node)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(MAIN), "exec"), namespace)
    return namespace["can_open_trade_decision"]


def _signal(**changes):
    value = {
        "id": "FALCON-SIGNAL-1",
        "signal_id": "FALCON-SIGNAL-1",
        "lifecycle_id": "FALCON-LIFECYCLE-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "setup": "FALCON15",
        "entry": 76.11,
        "stop": 75.80,
        "tp50": 76.42,
        "risk_pct": 0.5,
    }
    value.update(changes)
    return value


def _helpers(**changes):
    namespace = {
        "FALCON_MODE": "LIVE",
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-V1",
        "FALCON_SINGLE_LIVE_EXECUTION_CONTRACT_IMPORT_ERROR": None,
        "EXECUTION_ENGINE_IMPORT_ERROR": None,
        "derive_falcon_execution_intent_idempotency_key": (
            derive_falcon_execution_intent_idempotency_key
        ),
        "central_run_execution_engine": None,
        "central_trade_registry": SimpleNamespace(
            falcon_live_entry_storage_readiness=lambda: {
                "ok": True,
                "status": "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READY",
                "read_only": True,
                "write_executed": False,
            }
        ),
        "find_falcon_pending_broker_states": lambda limit=32: {
            "ok": True,
            "status": "FALCON_ENGINE_BROKER_LEDGER_CLEAR",
            "pending": [],
        },
        "_falcon_terminal_sanitize_projection": lambda value: value,
        "hashlib": hashlib,
        "json": json,
        "HEALTH": {},
        "falcon_initial_stop_failure_live_entry_lock_status": lambda: {
            "ok": True,
            "locked": False,
        },
    }
    namespace.update(changes)
    return _load_latest(
        FALCON,
        {
            "falcon_live_execution_path_guard",
            "_falcon_engine_pending_ledger_preflight",
            "_falcon_engine_unknown_active_lock_materially_persisted",
            "falcon_handle_engine_send_outcome_unknown",
            "_falcon_engine_result_live_order",
            "falcon_engine_send_outcome_unknown_result",
            "falcon_execute_live_via_canonical_engine",
        },
        namespace,
    ), namespace


def _reconcile_helpers(**changes):
    namespace = {
        "HEALTH": {},
        "data_hora_sp_str": lambda: "04/08/2026 12:00",
        "safe_float": lambda value, default=None: (
            float(value) if value not in (None, "") else default
        ),
        "FALCON_MANAGEMENT_AMOUNT_TOLERANCE": 1e-9,
        "FALCON_ENGINE_UNKNOWN_TERMINAL_FACT_PHASE": "ENGINE_UNKNOWN_TERMINAL_FACT_PERSISTED",
        "FALCON_ENGINE_UNKNOWN_TERMINAL_LEDGER_PHASE": "ENGINE_UNKNOWN_LEDGER_TERMINAL_PERSISTED",
        "FALCON_ENGINE_UNKNOWN_LOCK_RELEASE_PHASE": "ENGINE_UNKNOWN_LOCK_RELEASED",
        "FALCON_ENGINE_UNKNOWN_TERMINAL_ACK_PHASE": "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGED",
        "_falcon_terminal_sanitize_projection": lambda value: value,
        "record_execution_broker_state": lambda _key, state, identity: {
            "ok": True,
            "persistent": True,
            "status": state,
            "identity": dict(identity),
        },
        "verify_account_client_order_id_reservation": lambda reservation, **_kwargs: {
            "ok": True,
            "persistent": True,
            "status": "RESERVED_UNIQUE",
            "send_allowed": True,
            "send_claimed": False,
            "client_order_id": reservation.get("client_order_id"),
            "outcomes_found": [],
        },
    }
    namespace.update(changes)
    return _load_latest(
        FALCON,
        {
            "_falcon_engine_unknown_read_only_evidence",
            "_falcon_engine_unknown_account_authority",
            "_falcon_engine_unknown_normalize_order_lookup",
            "_falcon_engine_unknown_ledger_identity_validation",
            "_falcon_engine_unknown_reconciliation_position",
            "_falcon_engine_unknown_complete_terminal_acknowledgement",
            "_falcon_engine_unknown_finalize_terminal",
            "_falcon_engine_unknown_restore_protected_lifecycle",
            "_falcon_engine_unknown_containment_payload",
            "falcon_reconcile_engine_send_outcome_unknown",
        },
        namespace,
    ), namespace


def _engine_sent_result(**changes):
    order = {
        "ok": True,
        "sent": True,
        "status": "LIVE_SENT",
        "order_id": "ENTRY-1",
        "client_order_id": "ENT1-FALCON-1",
        "entry_acknowledged": True,
        "returned_client_order_id_matches": True,
        "disaster_stop": {
            "stop_operationally_armed": True,
            "client_order_id": "FDS1-FALCON-1",
        },
    }
    order.update(changes)
    return {
        "ok": bool(order.get("ok")),
        "payload": {
            "status": order.get("status"),
            "live_broker_called": bool(order.get("sent")),
            "plan": {"idempotency_key": "IDEM-FALCON-1"},
            "orchestration": {"payload": {"idempotency_key": "IDEM-FALCON-1"}},
            "live_result": order,
        },
    }


@pytest.mark.parametrize(
    ("state", "entry", "snapshot", "expected"),
    [
        (
            {
                "signal_id": "SIGNAL-1",
                "lifecycle_id": "LIFECYCLE-1",
                "trade_id": "TRADE-1",
                "symbol": "SOLUSDT",
                "side": "LONG",
                "client_order_id": "ENTRY-CID-1",
                "entry_price": 76.11,
            },
            {
                "id": "ENTRY-1",
                "filled": 0.5,
                "disaster_stop": {
                    "order_id": "STOP-1",
                    "client_order_id": "STOP-CID-1",
                },
            },
            {"amount": 0.5},
            {"live_order_id": "ENTRY-1", "broker_stop_order_id": "STOP-1"},
        ),
        ({"symbol": "SOLUSDT", "side": "LONG"}, {"id": "ENTRY-2"}, {}, {"live_order_id": "ENTRY-2", "broker_stop_order_id": None}),
        ({}, {}, {}, {"live_order_id": None, "broker_stop_order_id": None}),
        (None, None, None, {"live_order_id": None, "broker_stop_order_id": None}),
    ],
)
def test_engine_unknown_reconciliation_position_always_returns_factual_dict(
    state, entry, snapshot, expected
):
    helpers, _namespace = _reconcile_helpers()

    result = helpers._falcon_engine_unknown_reconciliation_position(
        state, entry, snapshot
    )

    assert isinstance(result, dict)
    assert result["bot"] == "FALCON"
    assert result["execution_mode"] == "LIVE"
    assert result["registry_mode"] == "REAL"
    assert result["live_order"] == {
        "sent": True,
        "order_id": expected["live_order_id"],
        "client_order_id": result["live_client_order_id"],
        "amount": result["live_order"]["amount"],
        "filled_amount": result["live_order"]["filled_amount"],
        "disaster_stop": result["live_order"]["disaster_stop"],
    }
    assert result["live_order_id"] == expected["live_order_id"]
    assert result["broker_stop_order_id"] == expected["broker_stop_order_id"]
    assert "disaster_stop_client_order_id" in result


def test_live_adapter_calls_engine_once_and_propagates_identity_without_direct_broker():
    calls = []

    def runner(*, payload, mode, dry_run):
        calls.append({"payload": dict(payload), "mode": mode, "dry_run": dry_run})
        return _engine_sent_result()

    helpers, _namespace = _helpers(central_run_execution_engine=runner)
    signal = _signal()
    risk = {"allowed": True, "decision": "ALLOW", "decision_id": "DECISION-1"}
    ownership = {"evidence": {"allowed": True, "requested_symbol": "SOLUSDT"}}

    result = helpers.falcon_execute_live_via_canonical_engine(
        signal, risk, 10.0, ownership
    )

    assert len(calls) == 1
    assert calls[0]["mode"] == "LIVE"
    assert calls[0]["dry_run"] is False
    assert calls[0]["payload"]["signal_id"] == "FALCON-SIGNAL-1"
    assert calls[0]["payload"]["lifecycle_id"] == "FALCON-LIFECYCLE-1"
    assert calls[0]["payload"]["decision_id"] == "DECISION-1"
    assert calls[0]["payload"]["falcon_position_ownership_limit"] == ownership["evidence"]
    assert result["falcon_live_execution_path"] == "ORCHESTRATOR_ENGINE"
    assert result["central_risk_verified"] is True
    assert result["orchestrator_called"] is True
    assert result["engine_called"] is True
    assert result["direct_broker_path_blocked"] is False
    assert result["auto_bridge_suppressed"] is True
    assert result["logical_send_count"] == result["broker_send_count"] == 1
    assert result["containment_triggered"] is False
    assert signal["entry_client_order_id"] == "ENT1-FALCON-1"


@pytest.mark.parametrize(
    ("registry", "expected_status"),
    [
        (
            SimpleNamespace(),
            "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_AUTHORITY_UNAVAILABLE",
        ),
        (
            SimpleNamespace(
                falcon_live_entry_storage_readiness=lambda: {
                    "ok": False,
                    "status": "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_NOT_READY",
                    "checks": {"last_write_ok": False},
                }
            ),
            "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_NOT_READY",
        ),
        (
            SimpleNamespace(
                falcon_live_entry_storage_readiness=lambda: (_ for _ in ()).throw(
                    RuntimeError("startup")
                )
            ),
            "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READINESS_ERROR",
        ),
    ],
)
def test_live_adapter_blocks_before_engine_until_registry_storage_is_ready(
    registry, expected_status
):
    calls = []
    helpers, _namespace = _helpers(
        central_trade_registry=registry,
        central_run_execution_engine=lambda **_kwargs: calls.append(True),
    )

    result = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert result["ok"] is False
    assert result["sent"] is False
    assert result["send_attempted"] is False
    assert result["engine_called"] is False
    assert result["broker_send_count"] == 0
    assert result["status"] == expected_status
    assert calls == []


def test_live_adapter_runner_missing_is_pre_send_false_and_runner_exception_is_unknown():
    helpers, _namespace = _helpers()
    missing = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert missing["status"] == "FALCON_EXECUTION_ENGINE_UNAVAILABLE"
    assert missing["sent"] is False
    assert missing["broker_send_count"] == 0

    def broken_runner(**_kwargs):
        raise RuntimeError("engine unavailable")

    helpers, _namespace = _helpers(central_run_execution_engine=broken_runner)
    failed = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert failed["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert failed["sent"] is None
    assert failed["send_outcome_unknown"] is True
    assert failed["reconciliation_required"] is True
    assert failed["falcon_live_entries_locked"] is True
    assert failed["broker_send_count"] is None


def test_same_signal_second_engine_result_is_exposed_as_duplicate_without_broker_send():
    calls = []

    def runner(**_kwargs):
        calls.append(True)
        if len(calls) == 1:
            return _engine_sent_result()
        return _engine_sent_result(
            ok=False,
            sent=False,
            status="DUPLICATE_BLOCKED",
            client_order_id="ENT1-FALCON-1",
        )

    helpers, _namespace = _helpers(central_run_execution_engine=runner)
    first = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )
    second = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert first["broker_send_count"] == 1
    assert second["duplicate_execution_blocked"] is True
    assert second["broker_send_count"] == 0


def test_live_path_guard_blocks_a_direct_path_name():
    helpers, _namespace = _helpers()

    result = helpers.falcon_live_execution_path_guard("DIRECT_BROKER")

    assert result["ok"] is False
    assert result["status"] == "FALCON_DIRECT_LIVE_BROKER_PATH_BLOCKED"
    assert result["direct_broker_path_blocked"] is True


def test_engine_result_normalizer_preserves_true_false_and_unknown_facts():
    helpers, _namespace = _helpers()

    sent = helpers._falcon_engine_result_live_order(_engine_sent_result())
    assert sent["sent"] is True
    assert sent["broker_send_count"] == 1
    assert sent["send_outcome_unknown"] is False

    pre_send_block = helpers._falcon_engine_result_live_order(
        {
            "ok": False,
            "payload": {
                "status": "LIVE_BLOCKED_BY_PILOT_GUARD",
                "live_broker_called": False,
                "plan": {"idempotency_key": "IDEM-BLOCKED"},
                "live_result": {"ok": False, "status": "LIVE_BLOCKED_BY_PILOT_GUARD"},
            },
        }
    )
    assert pre_send_block["sent"] is False
    assert pre_send_block["broker_send_count"] == 0
    assert pre_send_block["send_outcome_unknown"] is False

    missing_result_after_broker = helpers._falcon_engine_result_live_order(
        {
            "ok": False,
            "payload": {
                "status": "LIVE_RESULT_MISSING",
                "live_broker_called": True,
                "plan": {"idempotency_key": "IDEM-UNKNOWN"},
            },
        }
    )
    assert missing_result_after_broker["sent"] is None
    assert missing_result_after_broker["broker_send_count"] is None
    assert missing_result_after_broker["send_outcome_unknown"] is True
    assert missing_result_after_broker["reconciliation_required"] is True

    explicit_unknown = helpers._falcon_engine_result_live_order(
        _engine_sent_result(sent=None, ok=False, status="CREATE_ORDER_OUTCOME_UNKNOWN")
    )
    assert explicit_unknown["sent"] is None
    assert explicit_unknown["send_outcome_unknown"] is True

    invalid_after_runner = helpers._falcon_engine_result_live_order(None)
    assert invalid_after_runner["sent"] is None
    assert invalid_after_runner["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert invalid_after_runner["broker_send_count"] is None


def test_engine_exception_locks_and_persists_unknown_intention_without_second_send():
    calls = {
        "runner": 0,
        "simulated_broker": 0,
        "persisted": [],
        "alerts": 0,
        "locked": False,
    }

    def runner(**_kwargs):
        calls["runner"] += 1
        calls["simulated_broker"] += 1
        raise RuntimeError("result lost after Engine invocation")

    def lock_status():
        return {"ok": True, "locked": calls["locked"]}

    def lock_writer(_incident_id, *, active, reason=None):
        assert active is True
        assert reason == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
        calls["locked"] = True
        return {"ok": True, "locked": True, "status": "LOCKED"}

    def persist(incident_id, state):
        calls["persisted"].append((incident_id, dict(state)))
        return {"ok": True, "status": "PERSISTED"}

    def alert(_position, _state, blocked=False):
        assert blocked is True
        calls["alerts"] += 1
        return {"ok": True, "sent": True}

    helpers, _namespace = _helpers(
        central_run_execution_engine=runner,
        falcon_initial_stop_failure_live_entry_lock_status=lock_status,
        falcon_initial_stop_failure_save_live_entry_lock=lock_writer,
        falcon_terminal_stop_recovery_save=persist,
        falcon_terminal_stop_critical_alert=alert,
        _falcon_terminal_safe_text=lambda value, limit=240: str(value)[:limit],
        _falcon_terminal_sanitize_projection=lambda value: value,
    )
    signal = _signal(decision_id="DECISION-1")
    risk = {"allowed": True, "decision": "ALLOW", "decision_id": "DECISION-1"}

    first = helpers.falcon_execute_live_via_canonical_engine(signal, risk, 10.0)
    second = helpers.falcon_execute_live_via_canonical_engine(signal, risk, 10.0)

    assert first["sent"] is None
    assert first["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert first["send_outcome_unknown"] is True
    assert first["reconciliation_required"] is True
    assert first["falcon_live_entries_locked"] is True
    assert first["broker_send_count"] is None
    assert second["sent"] is False
    assert second["status"] == "FALCON_LIVE_ENTRIES_LOCKED_LOCAL_P0"
    assert calls["runner"] == 1
    assert calls["simulated_broker"] == 1
    assert calls["alerts"] == 1
    assert calls["persisted"]
    persisted = calls["persisted"][0][1]
    assert persisted["signal_id"] == "FALCON-SIGNAL-1"
    assert persisted["lifecycle_id"] == "FALCON-LIFECYCLE-1"
    assert persisted["decision_id"] == "DECISION-1"
    assert persisted["client_order_attempt_id"] == "FALCON-SIGNAL-1"
    assert persisted["execution_idempotency_key"].startswith("FALCON-ENGINE-INTENT:")


def test_literal_live_identity_rejects_legacy_id_and_empty_values_before_engine():
    calls = []

    def runner(**_kwargs):
        calls.append(True)
        return _engine_sent_result()

    helpers, _namespace = _helpers(central_run_execution_engine=runner)
    risk = {"allowed": True, "decision": "ALLOW"}
    rejected = [
        _signal(signal_id=None, id="LEGACY-ID-ONLY"),
        _signal(lifecycle_id=None),
        _signal(signal_id=""),
        _signal(lifecycle_id=""),
    ]
    for signal in rejected:
        result = helpers.falcon_execute_live_via_canonical_engine(signal, risk, 10.0)
        assert result["sent"] is False
        assert result["status"] == "FALCON_ENTRY_SIGNAL_OR_LIFECYCLE_IDENTITY_REQUIRED"
    assert calls == []


def test_live_adapter_fails_closed_for_invalid_contract_and_p0_lock_authority_states():
    calls = []

    def runner(**_kwargs):
        calls.append(True)
        return _engine_sent_result()

    invalid_contract, _ = _helpers(
        central_run_execution_engine=runner,
        FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION=None,
    )
    assert invalid_contract.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True}, 10.0
    )["status"] == "FALCON_SINGLE_LIVE_EXECUTION_CONTRACT_UNAVAILABLE"

    cases = [
        ({"HEALTH": {"falcon_live_entries_locked": True}}, "FALCON_LIVE_ENTRIES_LOCKED_LOCAL_P0"),
        ({"falcon_initial_stop_failure_live_entry_lock_status": None}, "FALCON_LIVE_ENTRY_LOCK_AUTHORITY_UNAVAILABLE"),
        ({"falcon_initial_stop_failure_live_entry_lock_status": lambda: (_ for _ in ()).throw(RuntimeError("down"))}, "FALCON_LIVE_ENTRY_LOCK_AUTHORITY_UNAVAILABLE"),
        ({"falcon_initial_stop_failure_live_entry_lock_status": lambda: {"ok": False, "locked": False}}, "FALCON_LIVE_ENTRY_LOCK_AUTHORITY_UNAVAILABLE"),
        ({"falcon_initial_stop_failure_live_entry_lock_status": lambda: {"ok": True, "locked": True}}, "FALCON_LIVE_ENTRIES_LOCKED_BY_RECONCILIATION"),
    ]
    for overrides, status in cases:
        helpers, _ = _helpers(central_run_execution_engine=runner, **overrides)
        result = helpers.falcon_execute_live_via_canonical_engine(
            _signal(), {"allowed": True}, 10.0
        )
        assert result["status"] == status
        assert result["sent"] is False
    assert calls == []


def test_post_engine_normalization_or_telemetry_exception_is_unknown_and_locked():
    def runner(**_kwargs):
        return _engine_sent_result()

    helpers, namespace = _helpers(central_run_execution_engine=runner)
    namespace["_falcon_engine_result_live_order"] = lambda _value: (_ for _ in ()).throw(
        RuntimeError("normalization failed")
    )
    result = helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert result["sent"] is None
    assert result["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert result["engine_invocation_started"] is True
    assert result["reconciliation_required"] is True
    assert result["falcon_live_entries_locked"] is True


def test_verify_and_paper_do_not_call_hostile_mutable_broker_even_with_live_flags():
    class HostileBroker:
        def ready_check(self):
            return {"ok": True, "status": "READY"}

        def place_market_order(self, **_kwargs):
            pytest.fail("VERIFY/PAPER must not call a mutable broker entry method")

    def run_mode(mode):
        namespace = {
            "FALCON_MODE": mode,
            "ENABLE_REAL_TRADING": True,
            "FALCON_REAL_NOTIONAL_USDT": 10.0,
            "FALCON_REAL_MAX_POSITIONS": 1,
            "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
            "HEALTH": {},
            "central_broker": HostileBroker(),
            "BROKER_IMPORT_ERROR": None,
            "safe_float": lambda value, default=None: float(value)
            if value is not None
            else default,
            "falcon_resolve_partial_capable_notional": lambda _sig: {
                "allowed": True,
                "notional_usdt": 10.0,
            },
            "falcon_live_positions_count": lambda _positions: 0,
            "central_can_open_trade": lambda _sig, positions=None: {
                "allowed": True,
                "decision": "ALLOW",
            },
        }
        execute = _load_first_function(FALCON, "execute_signal_if_allowed", namespace)
        signal = _signal()
        allowed, decision = execute(signal, positions={})
        return allowed, decision, signal

    paper_allowed, paper_decision, paper_signal = run_mode("PAPER")
    assert paper_allowed is True
    assert paper_decision["decision"] == "PAPER"
    assert "verify_order" not in paper_signal

    verify_allowed, verify_decision, verify_signal = run_mode("VERIFY")
    assert verify_allowed is True
    assert verify_decision["decision"] == "ALLOW"
    assert verify_signal["verify_order"]["sent"] is False
    assert verify_signal["verify_order"]["status"] == "FALCON_VERIFY_PLAN_ONLY"
    assert verify_signal["verify_order"]["client_order_id"] is None


def test_live_consumer_treats_unknown_engine_outcome_as_reconciliation_only():
    calls = {"unknown": 0}

    def unknown_handler(_signal, _payload, *, error=None):
        calls["unknown"] += 1
        assert error == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
        return {
            "incident_id": "UNKNOWN-1",
            "containment_status": "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN",
            "falcon_live_entries_locked": True,
            "reconciliation_required": True,
            "emergency_close_attempted": False,
        }

    namespace = {
        "FALCON_MODE": "LIVE",
        "ENABLE_REAL_TRADING": True,
        "FALCON_REAL_NOTIONAL_USDT": 10.0,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "HEALTH": {},
        "central_broker": object(),
        "BROKER_IMPORT_ERROR": None,
        "safe_float": lambda value, default=None: float(value)
        if value is not None
        else default,
        "falcon_resolve_partial_capable_notional": lambda _sig: {
            "allowed": True,
            "notional_usdt": 10.0,
        },
        "falcon_live_positions_count": lambda _positions: 0,
        "central_can_open_trade": lambda _sig, positions=None: {
            "allowed": True,
            "decision": "ALLOW",
            "decision_id": "DECISION-1",
        },
        "falcon_validate_position_ownership_limit_evidence": lambda _decision, sig=None: {
            "ok": True,
            "evidence": {},
        },
        "falcon_execute_live_via_canonical_engine": lambda *_args, **_kwargs: {
            "ok": False,
            "sent": None,
            "status": "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN",
            "send_outcome_unknown": True,
            "reconciliation_required": True,
            "falcon_live_entries_locked": True,
        },
        "falcon_handle_engine_send_outcome_unknown": unknown_handler,
        "falcon_handle_initial_stop_failure_containment": lambda *_args, **_kwargs: pytest.fail(
            "unknown outcome must not enter sent/unarmed-stop containment"
        ),
        "falcon_handle_unsafe_live_entry_identity": lambda *_args, **_kwargs: pytest.fail(
            "unknown outcome must not trigger a blind close path"
        ),
    }
    execute = _load_first_function(FALCON, "execute_signal_if_allowed", namespace)
    signal = _signal(decision_id="DECISION-1")
    allowed, decision = execute(signal, positions={})

    assert allowed is False
    assert decision["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert decision["reconciliation_required"] is True
    assert signal["live_order"]["sent"] is None
    assert signal["live_order"]["broker_send_count"] is None
    assert calls["unknown"] == 1


def test_live_consumer_post_engine_exception_becomes_unknown_without_retry_or_close():
    calls = {"adapter": 0, "unknown": 0}

    class PostEngineFailureSignal(dict):
        def __setitem__(self, key, value):
            if key == "live_order_id":
                raise RuntimeError("post-engine consumer failure")
            return super().__setitem__(key, value)

    def adapter(signal, *_args, **_kwargs):
        calls["adapter"] += 1
        signal["falcon_engine_invocation_started"] = True
        return _engine_sent_result()["payload"]["live_result"]

    def unknown_result(_signal, payload, *, error=None, engine_invocation_started=False, **_kwargs):
        calls["unknown"] += 1
        assert engine_invocation_started is True
        assert payload["signal_id"] == "FALCON-SIGNAL-1"
        return {
            "ok": False,
            "sent": None,
            "status": "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN",
            "reconciliation_required": True,
            "falcon_live_entries_locked": True,
            "engine_send_outcome_unknown_incident": {"incident_id": "P0-1"},
        }

    namespace = {
        "FALCON_MODE": "LIVE",
        "ENABLE_REAL_TRADING": True,
        "FALCON_REAL_NOTIONAL_USDT": 10.0,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "HEALTH": {},
        "central_broker": object(),
        "BROKER_IMPORT_ERROR": None,
        "safe_float": lambda value, default=None: float(value) if value is not None else default,
        "falcon_resolve_partial_capable_notional": lambda _sig: {"allowed": True, "notional_usdt": 10.0},
        "falcon_live_positions_count": lambda _positions: 0,
        "central_can_open_trade": lambda _sig, positions=None: {"allowed": True, "decision": "ALLOW", "decision_id": "DECISION-1"},
        "falcon_validate_position_ownership_limit_evidence": lambda *_args, **_kwargs: {"ok": True, "evidence": {}},
        "falcon_execute_live_via_canonical_engine": adapter,
        "falcon_engine_send_outcome_unknown_result": unknown_result,
    }
    execute = _load_first_function(FALCON, "execute_signal_if_allowed", namespace)
    allowed, decision = execute(PostEngineFailureSignal(_signal()), positions={})

    assert allowed is False
    assert decision["status"] == "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN"
    assert calls == {"adapter": 1, "unknown": 1}


def _unknown_incident_state(**updates):
    value = {
        "incident_type": "FALCON_ENGINE_SEND_OUTCOME_UNKNOWN",
        "signal_id": "FALCON-SIGNAL-1",
        "lifecycle_id": "FALCON-LIFECYCLE-1",
        "decision_id": "DECISION-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "client_order_id": "ENT1-EXACT",
        "canonical_operation_id": "OP1-EXACT",
        "client_order_attempt_id": "ATTEMPT-0",
        "client_order_attempt_sequence": 0,
        "orchestrator_idempotency_key": "ORCH-EXACT",
        "execution_idempotency_key": "FALCON-ENGINE-INTENT:EXACT",
        "execution_intent_idempotency_key": "FALCON-ENGINE-INTENT:EXACT",
        "reconciled_terminal": False,
    }
    value.update(updates)
    return value


def _unknown_reconcile_runtime(
    evidence,
    *,
    ledger_changes=None,
    fail_acknowledgement=False,
    fail_acknowledgement_permanently=False,
):
    state = _unknown_incident_state()
    lock = {"locked": True, "release_calls": 0, "events": []}
    saved = []
    ack_failure = {"used": False}

    def load(_incident_id):
        return {"ok": True, "incident": dict(state)}

    def save(_incident_id, value):
        acknowledgement_phase = value.get("terminal_phase") == (
            "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGED"
        )
        if acknowledgement_phase and (
            fail_acknowledgement_permanently
            or (fail_acknowledgement and not ack_failure["used"])
        ):
            ack_failure["used"] = True
            return {"ok": False, "status": "ACK_WRITE_FAILED"}
        state.clear()
        state.update(value)
        saved.append(dict(value))
        lock["events"].append(("persist", dict(value)))
        return {"ok": True, "status": "PERSISTED"}

    def writer(_incident_id, *, active, **_kwargs):
        lock["locked"] = bool(active)
        if not active:
            lock["release_calls"] += 1
            lock["events"].append(("unlock", None))
        return {"ok": True, "locked": bool(active), "status": "LOCK"}

    def reader():
        return {"ok": True, "locked": lock["locked"], "status": "LOCK"}

    ledger_identity = {
        "bot": "FALCON",
        "orchestrator_idempotency_key": state["orchestrator_idempotency_key"],
        "execution_intent_idempotency_key": state[
            "execution_intent_idempotency_key"
        ],
        "client_order_id": state["client_order_id"],
        "canonical_operation_id": state["canonical_operation_id"],
        "attempt_id": state["client_order_attempt_id"],
        "client_order_attempt_id": state["client_order_attempt_id"],
        "signal_id": state["signal_id"],
        "lifecycle_id": state["lifecycle_id"],
        "symbol": state["symbol"],
        "side": state["side"],
    }
    ledger_identity.update(ledger_changes or {})
    default_evidence = {
        "ok": True,
        "manual_or_ambiguous": False,
        "entry_position_closed": False,
        "reconciliation_position": {
            "live_order": {"order_id": "ENTRY-EXACT"},
            "live_order_id": "ENTRY-EXACT",
        },
        "stop_verification": {
            "stop_order_id": "STOP-EXACT",
            "disaster_stop_client_order_id": "FDS1-EXACT",
        },
    }
    if isinstance(evidence, dict):
        default_evidence.update(evidence)

    helpers, namespace = _reconcile_helpers(
        falcon_terminal_stop_recovery_load=load,
        falcon_terminal_stop_recovery_save=save,
        falcon_initial_stop_failure_save_live_entry_lock=writer,
        falcon_initial_stop_failure_live_entry_lock_status=reader,
        load_execution_broker_state=lambda _key: {
            "ok": True,
            "state": {
                "state": "ENGINE_BROKER_SEND_OUTCOME_UNKNOWN",
                "identity": dict(ledger_identity),
            },
        },
        falcon_engine_unknown_read_only_evidence_provider=(
            evidence
            if callable(evidence)
            else lambda _state: dict(default_evidence)
        ),
        get_positions=lambda: {},
        falcon_persist_accepted_signal=lambda _signal, _positions: {"ok": True},
    )
    return helpers, namespace, state, lock, saved


def test_unknown_reconciliation_terminal_paths_persist_then_unlock_and_are_idempotent():
    helpers, namespace, state, lock, saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": False,
            "account_authority_not_sent_confirmed": True,
            "manual_or_ambiguous": False,
        }
    )
    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-1")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-1")

    assert first["status"] == "ENGINE_ENTRY_NOT_SENT_CONFIRMED"
    assert first["falcon_live_entries_locked"] is False
    assert lock["release_calls"] == 1
    assert saved[0]["reconciled_terminal"] is True
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is False
    assert second["idempotent"] is True


def test_unknown_reconciliation_protected_entry_unlocks_only_after_terminal_persistence():
    helpers, namespace, state, lock, saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": True,
            "stop_operationally_armed": True,
            "manual_or_ambiguous": False,
        }
    )
    result = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-2")

    assert result["status"] == "ENGINE_ENTRY_PROTECTED_RECONCILED"
    assert result["falcon_live_entries_locked"] is False
    tracking_index = next(
        index
        for index, value in enumerate(saved)
        if value.get("protected_lifecycle_tracking_call_pending") is True
    )
    terminal_index = next(
        index
        for index, value in enumerate(saved)
        if value.get("attempt_state") == "ENGINE_ENTRY_PROTECTED_RECONCILED"
        and value.get("terminal_fact_persisted") is True
    )
    unlock_index = next(
        index
        for index, event in enumerate(lock["events"])
        if event[0] == "unlock"
    )
    terminal_event_index = next(
        index
        for index, event in enumerate(lock["events"])
        if event[0] == "persist"
        and event[1].get("attempt_state") == "ENGINE_ENTRY_PROTECTED_RECONCILED"
        and event[1].get("terminal_fact_persisted") is True
    )
    assert tracking_index < terminal_index
    assert terminal_event_index < unlock_index
    assert lock["release_calls"] == 1
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is False


def test_unknown_protected_entry_is_registered_for_normal_tracking_exactly_once():
    calls = {"tracking": []}
    helpers, namespace, _state, lock, _saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": True,
            "stop_operationally_armed": True,
            "manual_or_ambiguous": False,
            "reconciliation_position": {
                "live_order": {"order_id": "ENTRY-EXACT"},
                "live_order_id": "ENTRY-EXACT",
                "symbol": "SOLUSDT",
                "side": "LONG",
            },
            "stop_verification": {
                "status": "DISASTER_STOP_ACTIVE_VERIFIED",
                "stop_order_id": "STOP-EXACT",
                "disaster_stop_client_order_id": "FDS1-EXACT",
                "protected_qty": 0.5,
                "trigger_price": 75.8,
                "trigger_type": "MARK_PRICE",
                "stop_position_side": "LONG",
            },
            "entry_order_id": "ENTRY-EXACT",
            "entry_amount": 0.5,
        }
    )

    def track(signal, positions):
        calls["tracking"].append((dict(signal), positions))
        return {"ok": True, "status": "FALCON_ACCEPTED_SIGNAL_SYNCHRONIZED"}

    namespace["get_positions"] = lambda: {}
    namespace["falcon_persist_accepted_signal"] = track
    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-TRACK")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-TRACK")

    assert first["status"] == "ENGINE_ENTRY_PROTECTED_RECONCILED"
    assert second["idempotent"] is True
    assert len(calls["tracking"]) == 1
    tracked = calls["tracking"][0][0]
    assert tracked["execution_mode"] == "LIVE"
    assert tracked["registry_mode"] == "REAL"
    assert tracked["live_order"]["disaster_stop"]["stop_operationally_armed"] is True
    assert lock["release_calls"] == 1


def test_unknown_reconciliation_unprotected_entry_calls_existing_containment_once():
    calls = {"containment": 0}
    helpers, namespace, state, lock, _saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": True,
            "stop_operationally_armed": False,
            "stop_absent_confirmed": True,
            "manual_or_ambiguous": False,
        }
    )
    namespace["falcon_handle_initial_stop_failure_containment"] = lambda *_args: calls.update(
        containment=calls["containment"] + 1
    ) or {"ok": False, "containment_status": "CONTAINMENT"}

    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-3")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-3")
    assert first["status"] == "ENGINE_UNKNOWN_INITIAL_STOP_CONTAINMENT_TRIGGERED"
    assert second["status"] == "ENGINE_UNKNOWN_INITIAL_STOP_CONTAINMENT_PENDING"
    assert calls["containment"] == 1
    assert lock["release_calls"] == 0
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is True


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ({"ok": True, "entry_found": True, "stop_operationally_armed": None, "manual_or_ambiguous": True}, "ENGINE_UNKNOWN_MANUAL_OR_AMBIGUOUS"),
        ({"ok": False}, "ENGINE_UNKNOWN_RECONCILIATION_INCONCLUSIVE"),
    ],
)
def test_unknown_reconciliation_never_unlocks_or_closes_ambiguous_or_unavailable(
    evidence, expected
):
    helpers, namespace, _state, lock, _saved = _unknown_reconcile_runtime(evidence)
    namespace["falcon_handle_initial_stop_failure_containment"] = lambda *_args: pytest.fail(
        "manual or inconclusive evidence must not close"
    )
    result = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-4")
    assert result["status"] == expected
    assert result["falcon_live_entries_locked"] is True
    assert lock["release_calls"] == 0


def test_unknown_default_reader_uses_exact_stop_verifier_not_entry_stop_flag():
    calls = {"lookup": 0, "position": 0, "stop": []}

    class Broker:
        def reconcile_order_from_bingx(
            self, symbol, order_id=None, client_order_id=None
        ):
            calls["lookup"] += 1
            assert symbol == "SOLUSDT"
            assert order_id == "ENTRY-EXACT"
            assert client_order_id == "ENT1-EXACT"
            return {
                "ok": True,
                # Exercise the real reader's alternate contract spelling.
                "orders": [
                    {
                        "id": "ENTRY-EXACT",
                        "clientOrderId": "ENT1-EXACT",
                        "symbol": "SOLUSDT",
                        "side": "BUY",
                        "filled": 0.5,
                        # This stale entry flag must never become proof.
                        "stop_operationally_armed": True,
                    }
                ],
            }

        def managed_position_snapshot(self, symbol, side, expected_amount=None):
            calls["position"] += 1
            assert (symbol, side, expected_amount) == ("SOLUSDT", "LONG", 0.5)
            return {
                "ok": True,
                "read_only": True,
                "amount": 0.5,
                "position_closed": False,
                "ownership_safe": True,
                "matched_count": 1,
            }

    def physical_stop_verifier(position, *, force, persist_registry):
        calls["stop"].append(dict(position))
        assert force is True and persist_registry is False
        assert position["broker_stop_order_id"] == "STOP-EXACT"
        assert position["disaster_stop_client_order_id"] == "FDS1-EXACT"
        assert position["lifecycle_id"] == "FALCON-LIFECYCLE-1"
        return {
            "ok": True,
            "read_only": True,
            "status": "DISASTER_STOP_ACTIVE_VERIFIED",
            "stop_operationally_armed": True,
            "stop_order_id": "STOP-EXACT",
            "disaster_stop_client_order_id": "FDS1-EXACT",
            "stop_order_active": True,
            "protected_qty": 0.5,
            "trigger_price": 75.8,
            "trigger_type": "MARK_PRICE",
            "stop_position_side": "LONG",
        }

    helpers, _namespace = _reconcile_helpers(
        central_broker=Broker(),
        falcon_verify_live_disaster_stop=physical_stop_verifier,
    )
    evidence = helpers._falcon_engine_unknown_read_only_evidence(
        _unknown_incident_state(
            entry_order_id="ENTRY-EXACT",
            entry_filled_amount=0.5,
            disaster_stop={
                "order_id": "STOP-EXACT",
                "client_order_id": "FDS1-EXACT",
                "client_order_id_reserved": True,
                "client_order_id_unique": True,
                "amount": 0.5,
            },
        )
    )

    assert evidence["ok"] is True
    assert evidence["entry_found"] is True
    assert evidence["stop_operationally_armed"] is True
    assert calls["lookup"] == calls["position"] == 1
    assert len(calls["stop"]) == 1


def _real_unknown_reader_runtime(*, lookup, position, authority):
    class Broker:
        def reconcile_order_from_bingx(
            self, symbol, order_id=None, client_order_id=None
        ):
            assert symbol == "SOLUSDT"
            assert order_id is None
            assert client_order_id == "ENT1-EXACT"
            return lookup

        def managed_position_snapshot(self, symbol, side, expected_amount=None):
            assert (symbol, side) == ("SOLUSDT", "LONG")
            return position

    helpers, namespace = _reconcile_helpers(central_broker=Broker())
    namespace["verify_account_client_order_id_reservation"] = (
        lambda _reservation, **_kwargs: dict(authority)
    )
    state = _unknown_incident_state(
        entry_order_id=None,
        order_id=None,
        client_order_id="ENT1-EXACT",
        client_order_id_reservation={
            "ok": True,
            "status": "RESERVED_UNIQUE",
            "reservation_status": "RESERVED_UNIQUE",
            "reservation_state": "RESERVED_PRE_SEND",
            "persistent": True,
            "client_order_id": "ENT1-EXACT",
        },
    )
    return helpers._falcon_engine_unknown_read_only_evidence(state)


def test_real_reader_confirms_not_sent_only_from_unclaimed_authority_and_empty_facts():
    evidence = _real_unknown_reader_runtime(
        lookup={"ok": True, "orders": []},
        position={
            "ok": True,
            "read_only": True,
            "amount": 0.0,
            "position_closed": True,
            "matched_count": 0,
        },
        authority={
            "ok": True,
            "persistent": True,
            "status": "RESERVED_UNIQUE",
            "send_allowed": True,
            "send_claimed": False,
            "client_order_id": "ENT1-EXACT",
            "outcomes_found": [],
        },
    )
    assert evidence["ok"] is True
    assert evidence["entry_found"] is False
    assert evidence["account_authority_not_sent_confirmed"] is True


@pytest.mark.parametrize(
    "authority",
    [
        {
            "ok": True,
            "persistent": True,
            "status": "CLIENT_ORDER_ATTEMPT_SEND_ALREADY_CLAIMED",
            "send_allowed": False,
            "send_claimed": True,
            "client_order_id": "ENT1-EXACT",
            "outcomes_found": [],
        },
        {
            "ok": True,
            "persistent": True,
            "status": "CREATE_ORDER_OUTCOME_UNKNOWN",
            "send_allowed": False,
            "send_claimed": True,
            "client_order_id": "ENT1-EXACT",
            "outcomes_found": ["CREATE_ORDER_OUTCOME_UNKNOWN"],
        },
    ],
)
def test_real_reader_keeps_claimed_or_unknown_authority_inconclusive(authority):
    evidence = _real_unknown_reader_runtime(
        lookup={"ok": True, "orders": []},
        position={
            "ok": True,
            "read_only": True,
            "amount": 0.0,
            "position_closed": True,
            "matched_count": 0,
        },
        authority=authority,
    )
    assert evidence["ok"] is False
    assert evidence["account_authority_not_sent_confirmed"] is False
    assert evidence["account_authority_inconclusive"] is True


def test_real_reader_keeps_lookup_unavailable_inconclusive():
    evidence = _real_unknown_reader_runtime(
        lookup={"ok": False, "status": "LOOKUP_UNAVAILABLE"},
        position={
            "ok": True,
            "read_only": True,
            "amount": 0.0,
            "position_closed": True,
            "matched_count": 0,
        },
        authority={"ok": True, "status": "RESERVED_UNIQUE"},
    )
    assert evidence["ok"] is False
    assert evidence["account_authority_not_sent_confirmed"] is False


def test_real_reader_rejects_divergent_client_order_id_as_identity_conflict():
    evidence = _real_unknown_reader_runtime(
        lookup={
            "ok": True,
            "orders": [
                {
                    "id": "ENTRY-OTHER",
                    "clientOrderId": "ENT1-OTHER",
                    "symbol": "SOLUSDT",
                    "side": "BUY",
                }
            ],
        },
        position={
            "ok": True,
            "read_only": True,
            "amount": 0.0,
            "position_closed": True,
            "matched_count": 0,
        },
        authority={
            "ok": True,
            "persistent": True,
            "status": "RESERVED_UNIQUE",
            "send_allowed": True,
            "send_claimed": False,
            "client_order_id": "ENT1-EXACT",
            "outcomes_found": [],
        },
    )
    assert evidence["ok"] is False
    assert evidence["entry_identity_conflict"] is True
    assert evidence["account_authority_not_sent_confirmed"] is False


def test_real_reader_does_not_confirm_not_sent_when_position_is_open():
    evidence = _real_unknown_reader_runtime(
        lookup={"ok": True, "orders": []},
        position={
            "ok": True,
            "read_only": True,
            "amount": 0.5,
            "position_closed": False,
            "matched_count": 1,
            "ownership_safe": True,
        },
        authority={
            "ok": True,
            "persistent": True,
            "status": "RESERVED_UNIQUE",
            "send_allowed": True,
            "send_claimed": False,
            "client_order_id": "ENT1-EXACT",
            "outcomes_found": [],
        },
    )
    assert evidence["ok"] is False
    assert evidence["position_empty_factual"] is False
    assert evidence["account_authority_not_sent_confirmed"] is False


def test_unknown_partial_stop_identity_stays_inconclusive_without_containment():
    helpers, namespace, _state, lock, _saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": True,
            "stop_operationally_armed": None,
            "stop_absent_confirmed": False,
            "manual_or_ambiguous": False,
        }
    )
    namespace["falcon_handle_initial_stop_failure_containment"] = lambda *_args: pytest.fail(
        "partial physical stop evidence must not close"
    )
    result = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-PARTIAL")

    assert result["status"] == "ENGINE_UNKNOWN_RECONCILIATION_INCONCLUSIVE"
    assert result["falcon_live_entries_locked"] is True
    assert lock["release_calls"] == 0


def test_unknown_ledger_identity_conflict_keeps_lock_and_never_calls_containment():
    helpers, namespace, _state, lock, _saved = _unknown_reconcile_runtime(
        {"ok": True}, ledger_changes={"signal_id": "OTHER-SIGNAL"}
    )
    namespace["falcon_handle_initial_stop_failure_containment"] = lambda *_args: pytest.fail(
        "ledger identity conflict must not close"
    )
    alerts = []
    namespace["falcon_terminal_stop_critical_alert"] = lambda *_args, **_kwargs: alerts.append(
        True
    ) or {"ok": True}

    result = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-CONFLICT")

    assert result["status"] == "ENGINE_UNKNOWN_LEDGER_IDENTITY_CONFLICT"
    assert result["falcon_live_entries_locked"] is True
    assert lock["release_calls"] == 0
    assert alerts == [True]


def test_unknown_confirmed_containment_can_reach_terminal_on_later_read_only_pass():
    calls = {"containment": 0}

    def evidence(_state):
        if _state.get("initial_stop_containment_confirmed") is True:
            return {
                "ok": True,
                "entry_found": True,
                "entry_position_closed": True,
                "manual_or_ambiguous": False,
            }
        return {
            "ok": True,
            "entry_found": True,
            "stop_absent_confirmed": True,
            "manual_or_ambiguous": False,
            "reconciliation_position": {"live_order_id": "ENTRY-EXACT"},
            "order": {"id": "ENTRY-EXACT"},
            "position_snapshot": {"position_closed": False},
            "stop_verification": {"status": "DISASTER_STOP_NOT_FOUND"},
        }

    helpers, namespace, state, lock, _saved = _unknown_reconcile_runtime(evidence)
    namespace["falcon_handle_initial_stop_failure_containment"] = lambda *_args: calls.update(
        containment=calls["containment"] + 1
    ) or {
        "incident_id": "INITIAL-STOP-1",
        "containment_status": "INITIAL_STOP_FAILED_EMERGENCY_CLOSE_CONFIRMED",
        "emergency_close_confirmed": True,
        "residual_position_qty": 0.0,
    }

    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-CLOSE")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-CLOSE")

    assert first["status"] == "ENGINE_UNKNOWN_INITIAL_STOP_CONTAINMENT_TRIGGERED"
    assert state["initial_stop_containment_incident_id"] == "INITIAL-STOP-1"
    assert state["initial_stop_containment_confirmed"] is True
    assert second["status"] == "ENGINE_ENTRY_EMERGENCY_CLOSED_RECONCILED"
    assert calls["containment"] == 1
    assert lock["release_calls"] == 1


def test_terminal_unlock_crash_window_completes_ack_without_resending_or_reunlocking():
    helpers, namespace, _state, lock, saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": False,
            "account_authority_not_sent_confirmed": True,
            "manual_or_ambiguous": False,
        },
        fail_acknowledgement=True,
    )
    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-ACK")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-ACK")

    assert first["status"] == "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGEMENT_REQUIRED"
    assert second["status"] == "ENGINE_ENTRY_NOT_SENT_CONFIRMED"
    assert second["falcon_live_entries_locked"] is False
    assert lock["release_calls"] == 1
    assert saved[-1]["terminal_acknowledged"] is True
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is False


def test_permanent_terminal_ack_failure_keeps_gate_closed_and_blocks_new_engine_call():
    helpers, namespace, state, lock, _saved = _unknown_reconcile_runtime(
        {
            "ok": True,
            "entry_found": False,
            "account_authority_not_sent_confirmed": True,
            "manual_or_ambiguous": False,
        },
        fail_acknowledgement_permanently=True,
    )

    first = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-ACK-PERSISTENT")
    second = helpers.falcon_reconcile_engine_send_outcome_unknown("INCIDENT-ACK-PERSISTENT")

    assert first["status"] == "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGEMENT_REQUIRED"
    assert second["status"] == "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGEMENT_REQUIRED"
    assert state["terminal_acknowledged"] is False
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is True
    assert lock["release_calls"] == 1

    calls = {"engine": 0}
    gate_helpers, _gate_namespace = _helpers(
        central_run_execution_engine=lambda **_kwargs: calls.update(
            engine=calls["engine"] + 1
        )
        or _engine_sent_result(),
        falcon_terminal_stop_ack_gate_status=lambda: {
            "ok": True,
            "active": True,
            "status": "TERMINAL_ACKNOWLEDGEMENT_REQUIRED",
        },
    )
    blocked = gate_helpers.falcon_execute_live_via_canonical_engine(
        _signal(), {"allowed": True, "decision": "ALLOW"}, 10.0
    )

    assert blocked["status"] == "FALCON_TERMINAL_ACKNOWLEDGEMENT_REQUIRED"
    assert blocked["engine_called"] is False
    assert calls["engine"] == 0


def _terminal_phase_runtime(failure):
    durable = _unknown_incident_state()
    saved = []
    lock = {"locked": True, "release_calls": 0}
    calls = {"ledger": 0}
    failure = {"kind": failure, "used": False}

    def load(_incident_id):
        return {"ok": True, "incident": dict(durable)}

    def save(_incident_id, value):
        phase = value.get("terminal_phase")
        if (
            not failure["used"]
            and failure["kind"] in {"ledger_phase", "lock_phase", "ack_phase"}
            and phase
            == {
                "ledger_phase": "ENGINE_UNKNOWN_LEDGER_TERMINAL_PERSISTED",
                "lock_phase": "ENGINE_UNKNOWN_LOCK_RELEASED",
                "ack_phase": "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGED",
            }[failure["kind"]]
        ):
            failure["used"] = True
            return {"ok": False, "status": "FAULT_INJECTED"}
        durable.clear()
        durable.update(value)
        saved.append(dict(value))
        return {"ok": True, "status": "PERSISTED"}

    def lock_writer(_incident_id, *, active, **_kwargs):
        lock["locked"] = bool(active)
        if not active:
            lock["release_calls"] += 1
        return {"ok": True, "locked": bool(active), "status": "LOCK"}

    def lock_reader():
        return {"ok": True, "locked": lock["locked"], "status": "LOCK"}

    def ledger_writer(_key, _state, identity):
        calls["ledger"] += 1
        if failure["kind"] == "ledger_writer" and not failure["used"]:
            failure["used"] = True
            return {"ok": False, "persistent": False, "status": "FAULT_INJECTED"}
        return {"ok": True, "persistent": True, "status": "LEDGER", "identity": identity}

    helpers, namespace = _reconcile_helpers(
        falcon_terminal_stop_recovery_load=load,
        falcon_terminal_stop_recovery_save=save,
        falcon_initial_stop_failure_save_live_entry_lock=lock_writer,
        falcon_initial_stop_failure_live_entry_lock_status=lock_reader,
        record_execution_broker_state=ledger_writer,
    )
    return helpers, namespace, durable, saved, lock, calls


def test_terminal_finalization_replaces_pending_status_and_preserves_it_for_audit():
    helpers, _namespace, durable, _saved, _lock, _calls = _terminal_phase_runtime(
        "none"
    )
    result = helpers._falcon_engine_unknown_finalize_terminal(
        "INCIDENT-TERMINAL-STATUS",
        _unknown_incident_state(
            containment_status="ENGINE_UNKNOWN_INITIAL_STOP_CONTAINMENT_CALL_PENDING",
            containment_reason="INITIAL_STOP_CONTAINMENT_PENDING",
        ),
        "ENGINE_ENTRY_EMERGENCY_CLOSED_RECONCILED",
        "INITIAL_STOP_CONTAINMENT_CONFIRMED_AND_POSITION_FACTUALLY_FLAT",
    )

    assert result["status"] == "ENGINE_ENTRY_EMERGENCY_CLOSED_RECONCILED"
    assert durable["attempt_state"] == "ENGINE_ENTRY_EMERGENCY_CLOSED_RECONCILED"
    assert durable["containment_status"] == "ENGINE_ENTRY_EMERGENCY_CLOSED_RECONCILED"
    assert durable["containment_reason"] == (
        "INITIAL_STOP_CONTAINMENT_CONFIRMED_AND_POSITION_FACTUALLY_FLAT"
    )
    assert durable["previous_containment_status"] == (
        "ENGINE_UNKNOWN_INITIAL_STOP_CONTAINMENT_CALL_PENDING"
    )


@pytest.mark.parametrize("failure", ["ledger_writer", "ledger_phase", "lock_phase", "ack_phase"])
def test_terminal_state_machine_restarts_from_last_confirmed_phase(failure):
    helpers, namespace, durable, saved, lock, calls = _terminal_phase_runtime(failure)
    first = helpers._falcon_engine_unknown_finalize_terminal(
        "INCIDENT-PHASE",
        dict(durable),
        "ENGINE_ENTRY_NOT_SENT_CONFIRMED",
        "FACTUAL_NOT_SENT",
    )
    assert first["falcon_live_entries_locked"] is True
    if failure == "ack_phase":
        assert first["status"] == "ENGINE_UNKNOWN_TERMINAL_ACKNOWLEDGEMENT_REQUIRED"

    second = helpers._falcon_engine_unknown_finalize_terminal(
        "INCIDENT-PHASE",
        dict(durable),
        "ENGINE_ENTRY_NOT_SENT_CONFIRMED",
        "FACTUAL_NOT_SENT",
    )
    assert second["status"] == "ENGINE_ENTRY_NOT_SENT_CONFIRMED"
    assert second["falcon_live_entries_locked"] is False
    assert lock["release_calls"] <= 1
    assert calls["ledger"] <= 2
    assert saved[-1]["terminal_acknowledged"] is True
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is False


def test_pending_ledger_blocks_a_different_falcon_signal_before_engine_or_broker():
    calls = {"engine": 0}
    pending = {
        "orchestrator_idempotency_key": "ORCH-PENDING",
        "state": "ENGINE_BROKER_CALL_PENDING",
        "identity": {
            "bot": "FALCON",
            "signal_id": "OLD-SIGNAL",
            "lifecycle_id": "OLD-LIFECYCLE",
            "decision_id": "OLD-DECISION",
            "client_order_id": "ENT1-OLD",
            "canonical_operation_id": "OP-OLD",
            "attempt_id": "ATTEMPT-OLD",
            "client_order_attempt_id": "ATTEMPT-OLD",
            "client_order_attempt_sequence": 0,
            "execution_intent_idempotency_key": "FALCON-ENGINE-INTENT:OLD",
            "symbol": "SOLUSDT",
            "side": "LONG",
        },
    }
    helpers, namespace = _helpers(
        central_run_execution_engine=lambda **_kwargs: calls.update(
            engine=calls["engine"] + 1
        ) or _engine_sent_result(),
        find_falcon_pending_broker_states=lambda limit=32: {
            "ok": True,
            "pending": [pending],
        },
        falcon_initial_stop_failure_save_live_entry_lock=lambda incident_id, **_kwargs: {
            "ok": True,
            "locked": True,
            "incident_id": incident_id,
            "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED",
        },
        falcon_initial_stop_failure_live_entry_lock_status=lambda: {
            "ok": True,
            "locked": True,
            "incident_id": "FALCON-ENGINE-SEND-OUTCOME-UNKNOWN:TEST",
            "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED",
        },
        falcon_terminal_stop_recovery_save=lambda *_args: {"ok": True},
        _falcon_terminal_safe_text=lambda value, limit=240: str(value)[:limit],
    )

    result = helpers.falcon_execute_live_via_canonical_engine(
        _signal(signal_id="NEW-SIGNAL", lifecycle_id="NEW-LIFECYCLE"),
        {"allowed": True, "decision": "ALLOW"},
        10.0,
    )

    assert result["status"] == "FALCON_ENGINE_BROKER_RECONCILIATION_PENDING"
    assert result["sent"] is False
    assert result["engine_called"] is False
    assert calls["engine"] == 0
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is True


def test_live_risk_bypass_is_fail_closed_and_verify_bypass_remains_compatible():
    live, _namespace = _load_latest(
        FALCON,
        {"central_can_open_trade"},
        {
            "FALCON_USE_CENTRAL_RISK": False,
            "FALCON_MODE": "LIVE",
            "FALCON_REAL_NOTIONAL_USDT": 10.0,
            "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
        },
    ), None
    live_result = live.central_can_open_trade(_signal())

    verify, _namespace = _load_latest(
        FALCON,
        {"central_can_open_trade"},
        {
            "FALCON_USE_CENTRAL_RISK": False,
            "FALCON_MODE": "VERIFY",
            "FALCON_REAL_NOTIONAL_USDT": 10.0,
        },
    ), None
    verify_result = verify.central_can_open_trade(_signal())

    assert live_result["allowed"] is False
    assert live_result["status"] == "FALCON_LIVE_CENTRAL_RISK_REQUIRED"
    assert verify_result["allowed"] is True
    assert "FALCON_USE_CENTRAL_RISK=false" in verify_result["warnings"]


def test_live_risk_payload_uses_exact_single_path_version_and_literal_signal_id():
    captured = []

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"allowed": True, "decision": "ALLOW"}

    class Requests:
        @staticmethod
        def post(_url, json=None, timeout=None):
            captured.append({"payload": dict(json or {}), "timeout": timeout})
            return Response()

    helpers, _namespace = _load_latest(
        FALCON,
        {"central_can_open_trade"},
        {
            "FALCON_USE_CENTRAL_RISK": True,
            "FALCON_MODE": "LIVE",
            "FALCON_REAL_NOTIONAL_USDT": 10.0,
            "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
            "CENTRAL_CAN_OPEN_TRADE_URL": "http://test.invalid/can_open_trade",
            "requests": Requests(),
            "normalize_symbol_for_central": lambda value: value,
            "safe_float": lambda value, default=None: float(value)
            if value is not None
            else default,
        },
    ), None
    result = helpers.central_can_open_trade(
        _signal(signal_id=None, id="LEGACY-ID-MUST-NOT-BECOME-SIGNAL")
    )

    assert result["allowed"] is True
    assert captured[0]["payload"]["signal_id"] is None
    assert captured[0]["payload"]["lifecycle_id"] == "FALCON-LIFECYCLE-1"
    assert captured[0]["payload"]["falcon_single_live_execution_path_v1"] == (
        "TEST-FALCON-V1"
    )


def test_auto_real_bridge_suppresses_only_explicit_falcon_single_path_before_engine():
    events = []
    namespace = {
        "_AUTO_REAL_EXECUTION_BRIDGE_V1_CONTEXT": None,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_VERSION": "TEST-V1",
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
        "_arb_v1_norm_bot": lambda value: str(value or "").upper(),
        "_arb_v1_signal_id": lambda payload, _risk: payload.get("signal_id"),
        "_arb_v1_now": lambda: "2026-08-03T12:00:00Z",
        "_arb_v1_append_event": lambda event: events.append(dict(event)) or True,
    }
    process = _load_latest(
        MAIN, {"auto_real_execution_bridge_v1_process"}, namespace
    ).auto_real_execution_bridge_v1_process

    result = process(
        payload={
            "bot": "FALCON",
            "signal_id": "FALCON-SIGNAL-1",
            "lifecycle_id": "FALCON-LIFECYCLE-1",
            "falcon_single_live_execution_path_v1": "TEST-FALCON-V1",
            "suppress_auto_real_bridge": True,
        },
        risk_result={"allowed": True, "decision": "ALLOW"},
        source="can_open_trade",
        execute=True,
        dry_run=False,
    )

    assert result["status"] == "AUTO_REAL_BRIDGE_SUPPRESSED_FOR_FALCON_SINGLE_LIVE_PATH"
    assert result["executed"] is result["sent"] is False
    assert result["auto_bridge_suppressed"] is True
    assert len(events) == 1


def test_auto_real_bridge_fails_closed_for_invalid_falcon_contract_but_not_other_bots():
    events = []
    namespace = {
        "_AUTO_REAL_EXECUTION_BRIDGE_V1_CONTEXT": None,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_VERSION": "TEST-V1",
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
        "_arb_v1_norm_bot": lambda value: str(value or "").upper(),
        "_arb_v1_now": lambda: "2026-08-03T12:00:00Z",
        "_arb_v1_append_event": lambda event: events.append(dict(event)) or True,
        "_arb_v1_basic_eligibility": lambda *args, **kwargs: {
            "eligible": False,
            "payload": {},
            "config": {"require_signal_id": True},
            "reasons": ["not eligible"],
            "warnings": [],
        },
        "_arb_v1_config": lambda: {"require_signal_id": True},
        "_arb_v1_signal_key": lambda *args, **kwargs: None,
    }
    process = _load_latest(
        MAIN, {"auto_real_execution_bridge_v1_process"}, namespace
    ).auto_real_execution_bridge_v1_process
    invalid = process(
        payload={
            "bot": "FALCON",
            "signal_id": "S1",
            "lifecycle_id": "L1",
            "falcon_single_live_execution_path_v1": "WRONG",
            "suppress_auto_real_bridge": True,
        },
        source="can_open_trade",
        execute=True,
        dry_run=False,
    )
    assert invalid["status"] == "AUTO_REAL_BRIDGE_FALCON_SINGLE_PATH_CONTRACT_INVALID"
    assert invalid["executed"] is invalid["sent"] is False

    other = process(
        payload={
            "bot": "PREDATOR",
            "falcon_single_live_execution_path_v1": "WRONG",
        },
        source="can_open_trade",
    )
    assert other["status"] != "AUTO_REAL_BRIDGE_FALCON_SINGLE_PATH_CONTRACT_INVALID"


def test_can_open_trade_wrapper_attaches_only_validated_falcon_bridge_suppression():
    events = []
    original_decision = lambda _payload: {
        "ok": True,
        "allowed": True,
        "decision": "ALLOW",
    }
    namespace = {
        "_AUTO_REAL_EXECUTION_BRIDGE_V1_CONTEXT": None,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_VERSION": "TEST-BRIDGE",
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
        "_ORIGINAL_CAN_OPEN_TRADE_DECISION_FOR_AUTO_REAL_BRIDGE_V1": original_decision,
        "_arb_v1_norm_bot": lambda value: str(value or "").upper(),
        "_arb_v1_signal_id": lambda payload, _risk: payload.get("signal_id"),
        "_arb_v1_now": lambda: "2026-08-03T12:00:00Z",
        "_arb_v1_append_event": lambda event: events.append(dict(event)) or True,
        "_arb_v1_sanitize_public": lambda result: dict(result),
        "_arb_v1_basic_eligibility": lambda payload, _risk, source=None: {
            "eligible": False,
            "payload": dict(payload or {}),
            "config": {"require_signal_id": True},
            "reasons": ["not eligible in local test"],
            "warnings": [],
            "signal_id": (payload or {}).get("signal_id"),
        },
        "_arb_v1_config": lambda: {"require_signal_id": True},
        "_arb_v1_signal_key": lambda payload, _risk, require_signal_id=False: (
            payload.get("signal_id") if require_signal_id else None
        ),
        "_arb_v1_payload_summary": lambda payload: dict(payload or {}),
        "hashlib": hashlib,
    }
    bridge = _load_latest(
        MAIN, {"auto_real_execution_bridge_v1_process"}, namespace
    ).auto_real_execution_bridge_v1_process
    namespace["auto_real_execution_bridge_v1_process"] = bridge
    can_open = _load_auto_bridge_can_open_wrapper(namespace)

    valid = can_open(
        {
            "bot": "FALCON",
            "signal_id": "FALCON-SIGNAL-1",
            "lifecycle_id": "FALCON-LIFECYCLE-1",
            "falcon_single_live_execution_path_v1": "TEST-FALCON-V1",
            "suppress_auto_real_bridge": True,
        }
    )
    assert valid["auto_real_execution_bridge_v1"]["status"] == (
        "AUTO_REAL_BRIDGE_SUPPRESSED_FOR_FALCON_SINGLE_LIVE_PATH"
    )

    missing_identity = can_open(
        {
            "bot": "FALCON",
            "signal_id": "FALCON-SIGNAL-1",
            "falcon_single_live_execution_path_v1": "TEST-FALCON-V1",
            "suppress_auto_real_bridge": True,
        }
    )
    assert missing_identity["auto_real_execution_bridge_v1"]["status"] == (
        "AUTO_REAL_BRIDGE_FALCON_SINGLE_PATH_CONTRACT_INVALID"
    )

    missing_contract = can_open(
        {
            "bot": "FALCON",
            "signal_id": "FALCON-SIGNAL-1",
            "lifecycle_id": "FALCON-LIFECYCLE-1",
        }
    )
    assert missing_contract["auto_real_execution_bridge_v1"]["status"] == (
        "AUTO_REAL_BRIDGE_FALCON_SINGLE_PATH_CONTRACT_INVALID"
    )

    other_bot = bridge(
        payload={
            "bot": "PREDATOR",
            "signal_id": "PREDATOR-SIGNAL-1",
            "lifecycle_id": "PREDATOR-LIFECYCLE-1",
            "falcon_single_live_execution_path_v1": "TEST-FALCON-V1",
            "suppress_auto_real_bridge": True,
        },
        risk_result={"allowed": True, "decision": "ALLOW"},
        source="can_open_trade",
        execute=True,
        dry_run=False,
    )
    assert other_bot["status"] == "NOT_ELIGIBLE_FOR_AUTO_REAL_EXECUTION"
    assert any(
        event["status"] == "AUTO_REAL_BRIDGE_SUPPRESSED_FOR_FALCON_SINGLE_LIVE_PATH"
        for event in events
    )


def test_auto_bridge_blocks_every_invalid_falcon_can_open_contract():
    namespace = {
        "_AUTO_REAL_EXECUTION_BRIDGE_V1_CONTEXT": None,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_VERSION": "TEST-V1",
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "TEST-FALCON-V1",
        "_arb_v1_norm_bot": lambda value: str(value or "").upper(),
        "_arb_v1_now": lambda: "2026-08-04T12:00:00Z",
        "_arb_v1_append_event": lambda *_args, **_kwargs: None,
        "_arb_v1_basic_eligibility": lambda *_args, **_kwargs: pytest.fail(
            "invalid Falcon contract reached generic eligibility"
        ),
        "run_execution_engine": lambda **_kwargs: pytest.fail(
            "invalid Falcon contract reached Engine"
        ),
    }
    process = _load_latest(
        MAIN, {"auto_real_execution_bridge_v1_process"}, namespace
    ).auto_real_execution_bridge_v1_process
    cases = [
        {"bot": "FALCON", "signal_id": "S1", "lifecycle_id": "L1"},
        {"bot": "FALCON", "signal_id": "S1", "lifecycle_id": "L1", "falcon_single_live_execution_path_v1": None, "suppress_auto_real_bridge": True},
        {"bot": "FALCON", "signal_id": "S1", "lifecycle_id": "L1", "falcon_single_live_execution_path_v1": "WRONG", "suppress_auto_real_bridge": True},
        {"bot": "FALCON", "lifecycle_id": "L1", "falcon_single_live_execution_path_v1": "TEST-FALCON-V1", "suppress_auto_real_bridge": True},
        {"bot": "FALCON", "signal_id": "S1", "falcon_single_live_execution_path_v1": "TEST-FALCON-V1", "suppress_auto_real_bridge": True},
        {"bot": "FALCON", "signal_id": "S1", "lifecycle_id": "L1", "falcon_single_live_execution_path_v1": "TEST-FALCON-V1", "suppress_auto_real_bridge": False},
    ]
    for payload in cases:
        result = process(
            payload=payload,
            risk_result={"allowed": True, "decision": "ALLOW"},
            source="can_open_trade",
            execute=True,
            dry_run=False,
        )
        assert result["status"] == "AUTO_REAL_BRIDGE_FALCON_SINGLE_PATH_CONTRACT_INVALID"
        assert result["executed"] is result["sent"] is False


def test_unknown_handler_requires_active_owner_matched_lock_and_readback():
    cases = [
        ({"ok": True, "locked": False, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED"}, {"ok": True, "locked": True, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED"}, True),
        ({"ok": True, "locked": True, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED", "incident_id": "OTHER"}, {"ok": True, "locked": True, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED", "incident_id": "OTHER"}, True),
        ({"ok": True, "locked": True}, {"ok": True, "locked": True}, True),
        ({"ok": True, "locked": True, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED"}, {"ok": True, "locked": True, "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED"}, False),
    ]
    for written_template, read_template, degraded in cases:
        written = {"incident_id": None}
        def writer(incident_id, **_kwargs):
            written["incident_id"] = incident_id
            result = dict(written_template)
            result.setdefault("incident_id", incident_id)
            return result
        def reader():
            result = dict(read_template)
            result.setdefault("incident_id", written["incident_id"])
            return result
        helpers, namespace = _helpers(
            falcon_initial_stop_failure_save_live_entry_lock=writer,
            falcon_initial_stop_failure_live_entry_lock_status=reader,
            falcon_terminal_stop_recovery_save=lambda *_args: {"ok": True},
            _falcon_terminal_safe_text=lambda value, limit=240: str(value)[:limit],
            _falcon_terminal_sanitize_projection=lambda value: value,
        )
        result = helpers.falcon_handle_engine_send_outcome_unknown(
            _signal(),
            {"signal_id": "S1", "lifecycle_id": "L1", "client_order_id": "ENT1-X", "canonical_operation_id": "OP1-X", "client_order_attempt_id": "A1"},
        )
        assert result["durability_degraded"] is degraded
        assert namespace["HEALTH"]["falcon_live_entries_locked"] is True

    helpers, namespace = _helpers(
        falcon_initial_stop_failure_save_live_entry_lock=lambda incident_id, **_kwargs: {
            "ok": True,
            "locked": True,
            "status": "INITIAL_STOP_FAILURE_LIVE_ENTRY_LOCKED",
            "incident_id": incident_id,
        },
        falcon_initial_stop_failure_live_entry_lock_status=lambda: (_ for _ in ()).throw(
            RuntimeError("readback unavailable")
        ),
        falcon_terminal_stop_recovery_save=lambda *_args: {"ok": True},
        _falcon_terminal_safe_text=lambda value, limit=240: str(value)[:limit],
        _falcon_terminal_sanitize_projection=lambda value: value,
    )
    failed_readback = helpers.falcon_handle_engine_send_outcome_unknown(
        _signal(), {"signal_id": "S1", "lifecycle_id": "L1"}
    )
    assert failed_readback["durability_degraded"] is True
    assert namespace["HEALTH"]["falcon_live_entries_locked"] is True


def test_structural_falcon_source_has_no_direct_place_market_order_calls():
    tree = ast.parse(FALCON.read_text(encoding="utf-8"), filename=str(FALCON))
    direct_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "central_broker"
        and node.func.attr == "place_market_order"
    ]
    assert direct_calls == []


def test_contract_constant_has_a_single_neutral_definition_and_both_consumers_import_it():
    import falcon_live_execution_contract as contract

    assert isinstance(contract.FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION, str)
    for source in (FALCON, MAIN):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "falcon_live_execution_contract"
            and any(alias.name == "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION" for alias in node.names)
            for node in ast.walk(tree)
        )
