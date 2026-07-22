from __future__ import annotations

import ast
import copy
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from flask import Flask, request as flask_request


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = ROOT / "main.py"
BROKER_SOURCE = ROOT / "broker.py"

MAIN_FUNCTIONS = {
    "_fdsff_v1_response_headers",
    "_fdsff_v1_text_value",
    "_fdsff_v1_bool",
    "_fdsff_v1_extract_query",
    "_fdsff_v1_support_confirmation_scope",
    "_fdsff_v1_safe_scalar",
    "_fdsff_v1_walk_dicts",
    "_fdsff_v1_first",
    "_fdsff_v1_all_scalars",
    "_fdsff_v1_client_order_ids",
    "_fdsff_v1_event_name",
    "_fdsff_v1_safe_record",
    "_fdsff_v1_matches",
    "_fdsff_v1_event_time_evidence",
    "_fdsff_v1_incident_time_relation",
    "_fdsff_v1_operational_failsafe_record",
    "_fdsff_v1_group_failsafe_attempts",
    "_fdsff_v1_merge_record_categories",
    "_fdsff_v1_read_registry",
    "_fdsff_v1_read_falcon_health",
    "_fdsff_v1_read_snapshot_records",
    "_fdsff_v1_read_local_events",
    "_fdsff_v1_duplicate_client_order_id_audit",
    "_fdsff_v1_admin_auth",
    "_fdsff_v1_safe_live_lookup",
    "_fdsff_v1_epoch",
    "_fdsff_v1_float",
    "_fdsff_v1_classify",
    "_fdsff_v1_build_payload",
    "_fdsff_v1_text",
    "falcon_disaster_stop_failure_forensics_v1_text_route",
}
BROKER_FUNCTIONS = {
    "_dsff_v1_first",
    "_dsff_v1_safe_text",
    "_dsff_v1_safe_scalar",
    "_dsff_v1_epoch",
    "_dsff_v1_list_from_response",
    "_dsff_v1_call_raw",
    "_dsff_v1_normalize_order",
    "_dsff_v1_related_to_stop",
    "disaster_stop_failure_forensics_read_only",
}
_COMPILED_FUNCTIONS = {}


def _compile_functions(path: Path, names: set[str], namespace: dict) -> dict:
    cache_key = (str(path), tuple(sorted(names)))
    code = _COMPILED_FUNCTIONS.get(cache_key)
    if code is None:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        selected = []
        found = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                node = copy.deepcopy(node)
                node.decorator_list = []
                selected.append(node)
                found.add(node.name)
        assert found == names, f"missing functions: {sorted(names - found)}"
        selected.sort(key=lambda node: node.lineno)
        module = ast.Module(body=selected, type_ignores=[])
        ast.fix_missing_locations(module)
        code = compile(module, str(path), "exec")
        _COMPILED_FUNCTIONS[cache_key] = code
    exec(code, namespace)
    return namespace


def _norm_symbol(value):
    return str(value or "").upper().replace("/", "").replace(":USDT", "").replace("-", "").strip()


def _norm_side(value):
    value = str(value or "").upper().strip()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(value, value)


class FakeBroker:
    def __init__(self, live_result=None):
        self.live_result = copy.deepcopy(live_result or {})
        self.read_calls = []
        self.mutation_calls = []

    def disaster_stop_failure_forensics_read_only(self, **kwargs):
        self.read_calls.append(copy.deepcopy(kwargs))
        return copy.deepcopy(self.live_result)

    def __getattr__(self, name):
        if any(token in name.lower() for token in ("create", "cancel", "close", "replace", "edit", "reconcile")):
            def forbidden(*args, **kwargs):
                self.mutation_calls.append((name, args, kwargs))
                raise AssertionError(f"mutation attempted: {name}")

            return forbidden
        raise AttributeError(name)


class FakeRegistry:
    def __init__(self, open_trades=None, closed_trades=None):
        self.payload = {
            "open_trades": copy.deepcopy(open_trades or {}),
            "closed_trades": copy.deepcopy(closed_trades or []),
        }
        self.read_calls = 0
        self.write_calls = []

    def load_registry_read_only(self):
        self.read_calls += 1
        return copy.deepcopy(self.payload)

    def __getattr__(self, name):
        if any(token in name.lower() for token in ("save", "update", "register", "close", "write")):
            def forbidden(*args, **kwargs):
                self.write_calls.append((name, args, kwargs))
                raise AssertionError(f"registry write attempted: {name}")

            return forbidden
        raise AttributeError(name)


def _empty_live(**updates):
    payload = {
        "ok": True,
        "status": "READ_ONLY_LOOKUP_COMPLETE",
        "read_only": True,
        "sent": False,
        "cancel_called": False,
        "close_called": False,
        "position_modified": False,
        "reader_calls_attempted": [],
        "reader_calls_completed": [],
        "reader_calls_skipped_as_redundant": [],
        "reader_calls_attempted_count": 0,
        "reader_calls_completed_count": 0,
        "reader_calls_skipped_as_redundant_count": 0,
        "rate_limit_pacing_applied": False,
        "reader_calls": ["fetch_order_by_id:stop"],
        "reader_errors": [],
        "stop_orders": [],
        "derived_orders": [],
        "entry_orders": [],
        "manual_close_orders": [],
        "identity_conflicts": [],
        "identity_ambiguous": [],
        "identity_filters": [],
        "position": None,
        "raw_payload_exposed": False,
        "history_window_complete": True,
        "all_orders_saturated": False,
        "all_orders_pagination_incomplete": False,
        "local_negative_evidence_complete": True,
        "critical_alert_negative_evidence_complete": False,
        "critical_alert_negative_evidence_basis": "NO_COMPLETE_TELEGRAM_TRANSPORT_LEDGER_PROVEN",
    }
    payload.update(updates)
    return payload


def _main_namespace(*, local_records=None, live_result=None, registry=None):
    broker = FakeBroker(live_result=_empty_live() if live_result is None else live_result)
    registry = registry or FakeRegistry()
    namespace = {
        "Path": Path,
        "json": json,
        "re": re,
        "datetime": datetime,
        "timezone": timezone,
        "timedelta": timedelta,
        "request": flask_request,
        "central_broker": broker,
        "central_trade_registry": registry,
        "super_history_manager": None,
        "LOADED_BOTS": {},
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_LATEST_FILE": Path("unused-liveorder.json"),
        "_FDSFF_V1_QUERY_FIELDS": (
            "stop_order_id", "entry_order_id", "manual_close_order_id", "lifecycle_id", "client_order_id",
            "symbol", "side", "failure_timestamp", "manual_close_timestamp",
            "manual_close_price", "manual_close_quantity", "manual_close_value_usdt",
            "manual_close_gross_pnl_usdt", "manual_close_fee_usdt", "close_reason",
        ),
        "_FDSFF_V1_LOCAL_LIMIT": 300,
        "_FDSFF_V1_MAX_SNAPSHOT_BYTES": 2 * 1024 * 1024,
        "_FDSFF_V1_ORDER_FIELDS": (
            "source", "record_kind", "event", "order_id", "client_order_id", "client_order_ids", "parent_order_id",
            "requested_order_id", "plan_order_id", "trigger_order_id", "derived_order_id",
            "entry_order_id", "stop_order_id", "manual_close_order_id",
            "lifecycle_id", "trade_id", "symbol", "side", "position_side", "type",
            "plan_type", "order_type", "trigger_order_type", "trigger_type", "working_type",
            "status", "raw_status", "plan_status", "execute_status", "failure_status",
            "failure_code", "failure_reason", "trigger_price", "stop_price",
            "requested_quantity", "executed_quantity", "remaining_quantity",
            "quantity_unit", "quantity_source", "requested_quantity_unit",
            "requested_quantity_source", "executed_quantity_unit", "executed_quantity_source",
            "fill_id", "fill_time", "fill_quantity", "fill_quantity_unit",
            "fill_quantity_source", "fill_price", "fill_fee", "fill_realized_pnl",
            "average_fill_price", "close_position", "reduce_only", "created_at",
            "triggered_at", "failed_at", "canceled_at", "filled_at", "executed_at",
            "closed_at", "updated_at", "stop_identity_related", "stop_identity_conflict",
            "stop_identity_role", "bot", "external_position",
            "operational_correlation_role", "operational_correlation_basis",
            "operational_correlation_conflict", "failsafe_close_order_id",
            "failsafe_reason", "failsafe_sent", "failsafe_confirmed", "failsafe_status",
            "failsafe_timestamp", "failsafe_amount", "failsafe_expected_position_amount",
            "operational_correlation_quantity_basis", "incident_reported_quantity",
            "failsafe_order_sent", "failsafe_execution_confirmed",
            "failsafe_filled_amount", "failsafe_remaining_amount",
            "failsafe_timestamp_source_field", "failsafe_timestamp_basis",
            "failsafe_timestamp_precision", "failsafe_timestamp_epoch_start",
            "failsafe_timestamp_epoch_end", "failsafe_timestamp_timezone_basis",
            "failsafe_timestamp_evidence_conflict", "failsafe_attempt_inside_incident_window",
            "failsafe_timing_basis", "failsafe_timing_conflict", "failure_phase",
            "failsafe_incident_time_relation", "failsafe_interval_fully_inside",
            "failsafe_overlaps_start_boundary", "failsafe_overlaps_end_boundary",
            "failsafe_clock_skew_tolerance_only",
            "terminal_stop_emergency", "terminal_stop_emergency_incident_id",
            "terminal_stop_emergency_lifecycle_id", "terminal_stop_emergency_client_order_id",
            "terminal_stop_emergency_operation", "terminal_stop_emergency_attempt_state",
            "terminal_stop_emergency_send_attempted", "terminal_stop_emergency_sent",
            "terminal_stop_emergency_confirmed", "terminal_stop_emergency_send_outcome_unknown",
            "terminal_stop_emergency_order_id", "terminal_stop_emergency_filled_amount",
            "terminal_stop_emergency_remaining_amount", "terminal_stop_emergency_timestamp",
            "terminal_stop_emergency_status",
            "timestamp", "ts", "epoch", "epoch_ms",
        ),
        "FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1_VERSION": "TEST-V1",
        "FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1_ACK": "FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
        "FALCON_DISASTER_STOP_FAILURE_SUPPORT_CONFIRMED_CAUSE": "DUPLICATE_CLIENT_ORDER_ID",
        "FALCON_DISASTER_STOP_FAILURE_SUPPORT_CONFIRMED_BASIS": "BINGX_SUPPORT_CASE",
        "FALCON_DISASTER_STOP_FAILURE_DUPLICATED_CLIENT_ORDER_ID": "FALCON-LIVE-FALCON15-178-DS",
        "FALCON_DISASTER_STOP_FAILURE_SUPPORT_CONFIRMED_STOP_ORDER_ID": "2078846241538150400",
        "FALCON_DISASTER_STOP_FAILURE_SUPPORT_CONFIRMED_LIFECYCLE_IDS": (
            "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784470538",
        ),
        "FALCON_DISASTER_STOP_FAILURE_CLIENT_ORDER_ID_SCOPE": "ACCOUNT_WIDE",
        "FALCON_DISASTER_STOP_FAILURE_CLIENT_ORDER_ID_UNIQUENESS": "PERSISTENT_LIFETIME",
        "FALCON_DISASTER_STOP_FAILURE_CLIENT_ORDER_ID_CASE_SENSITIVE": False,
        "FALCON_DISASTER_STOP_FAILURE_AFFECTED_DATES": (
            "2026-07-14", "2026-07-15", "2026-07-19",
        ),
        "_flad_v1_norm_symbol": _norm_symbol,
        "_flad_v1_norm_side": _norm_side,
        "_fcor_v1_now": lambda: "2026-07-19T15:00:00Z",
        "_read_jsonl_tail": lambda *_args, **_kwargs: [],
    }
    _compile_functions(MAIN_SOURCE, MAIN_FUNCTIONS, namespace)
    namespace["_fdsff_v1_admin_auth_real"] = namespace["_fdsff_v1_admin_auth"]
    namespace["_fdsff_v1_admin_auth"] = lambda: {
        "available": True,
        "authenticated": True,
        "status": "ADMIN_AUTH_OK",
    }
    namespace["_fdsff_v1_read_registry_real"] = namespace["_fdsff_v1_read_registry"]
    namespace["_fdsff_v1_read_falcon_health_real"] = namespace["_fdsff_v1_read_falcon_health"]
    namespace["_fdsff_v1_read_snapshot_records_real"] = namespace["_fdsff_v1_read_snapshot_records"]
    namespace["_fdsff_v1_read_local_events_real"] = namespace["_fdsff_v1_read_local_events"]
    records = copy.deepcopy(local_records or [])
    namespace["_fdsff_v1_read_registry"] = lambda _query: ([], None)
    namespace["_fdsff_v1_read_falcon_health"] = lambda _query: ([], None)
    namespace["_fdsff_v1_read_snapshot_records"] = lambda *_args, **_kwargs: ([], None)
    complete_local_metadata = [
        {
            "source": source,
            "rows_read": 1,
            "configured_limit": 300,
            "saturated": False,
            "oldest_timestamp": "2026-07-19T13:30:00-03:00",
            "newest_timestamp": "2026-07-19T15:00:00-03:00",
            "incident_window_start": "2026-07-19T13:36:34-03:00",
            "incident_window_end": "2026-07-19T13:39:33-03:00",
            "incident_window_covered": True,
            "critical_alert_transport_audit_complete": False,
            "read_error": None,
        }
        for source in (
            "history.events", "broker.execution_audit", "broker.executions",
            "falcon.live_audit", "central.timeline",
        )
    ]
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        copy.deepcopy(records), [], 5, copy.deepcopy(complete_local_metadata)
    )
    return namespace, broker, registry


def _query(namespace, **updates):
    args = {
        "stop_order_id": "STOP-1",
        "entry_order_id": "ENTRY-1",
        "lifecycle_id": "LC-1",
        "client_order_id": "FALCON-LIVE-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
    }
    args.update(updates)
    return namespace["_fdsff_v1_extract_query"](args)


def _build(namespace, **updates):
    return namespace["_fdsff_v1_build_payload"](
        _query(namespace, **updates),
        admin_auth={"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
    )


def _classify(namespace, *, local=None, stop=None, derived=None, position=None, **query):
    live = _empty_live(
        stop_orders=copy.deepcopy(stop or []),
        derived_orders=copy.deepcopy(derived or []),
        position=copy.deepcopy(position),
    )
    query.setdefault("stop_order_id", "STOP-1")
    query.setdefault("symbol", "SOLUSDT")
    query.setdefault("side", "LONG")
    return namespace["_fdsff_v1_classify"](local or [], live, query)


def test_open_stop_is_created_but_terminal_status_remains_inconclusive():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "source": "bingx.fetch_order",
        "order_id": "STOP-1",
        "status": "OPEN",
        "requested_quantity": 0.13,
        "executed_quantity": 0.0,
    }])
    assert "STOP_CREATED" in result["classifications"]
    assert "STOP_TERMINAL_STATUS_INCONCLUSIVE" in result["classifications"]
    assert "STOP_FILLED" not in result["classifications"]


def test_full_filled_stop_is_classified_factually():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "FILLED",
        "requested_quantity": 0.13, "executed_quantity": 0.13,
        "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
    }])
    assert "STOP_FILLED" in result["classifications"]
    assert result["terminal_status_known"] is True
    assert result["executed_quantity"] == pytest.approx(0.13)


def test_triggered_stop_with_derived_market_fill_tracks_both_orders():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{"order_id": "STOP-1", "raw_status": "TRIGGERED", "requested_quantity": 0.13, "executed_quantity": 0.0, "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN"}],
        derived=[{"order_id": "MARKET-1", "parent_order_id": "STOP-1", "status": "FILLED", "executed_quantity": 0.13, "executed_quantity_unit": "COIN"}],
    )
    assert {"STOP_TRIGGERED", "STOP_DERIVED_ORDER_FOUND", "STOP_FILLED"}.issubset(result["classifications"])
    assert "STOP_TRIGGERED_ZERO_FILL" not in result["classifications"]


def test_parent_canceled_after_trigger_with_filled_child_is_success_not_failure_incident():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "order_id": "STOP-1", "status": "CANCELED", "plan_status": "TRIGGERED",
            "requested_quantity": 0.13, "executed_quantity": 0.0,
            "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
        }],
        derived=[{
            "order_id": "MARKET-1", "parent_order_id": "STOP-1",
            "raw_status": "FILLED", "executed_quantity": 0.13,
            "executed_quantity_unit": "COIN",
        }],
    )
    assert result["stop_filled"] is True
    assert result["failure_cause_status"] == "NOT_APPLICABLE_NO_FACTUAL_FAILURE"
    assert "FAILURE_REASON_UNAVAILABLE" not in result["classifications"]
    assert "STOP_CANCELED_AFTER_TRIGGER" in result["classifications"]


def test_parent_zero_does_not_hide_filled_child_when_child_quantity_is_missing():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "order_id": "STOP-1", "plan_status": "TRIGGERED",
            "requested_quantity": 0.13, "executed_quantity": 0.0,
            "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
        }],
        derived=[{
            "record_kind": "order", "order_id": "MARKET-1", "parent_order_id": "STOP-1", "raw_status": "FILLED",
        }],
    )
    assert result["stop_plan_executed_quantity"] == 0.0
    assert result["derived_executed_quantity"] is None
    assert result["executed_quantity"] is None
    assert result["stop_filled"] is True
    assert result["terminal_status"] == "FILLED"
    assert "STOP_TRIGGERED_ZERO_FILL" not in result["classifications"]


def test_failed_parent_with_filled_child_is_reported_as_terminal_evidence_conflict():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "order_id": "STOP-1", "raw_status": "FAILED", "plan_status": "TRIGGERED",
            "requested_quantity": 0.13, "executed_quantity": 0.0,
        }],
        derived=[{
            "order_id": "MARKET-1", "parent_order_id": "STOP-1",
            "raw_status": "FILLED", "executed_quantity": 0.13,
        }],
    )
    assert result["terminal_evidence_conflict"] is True
    assert "STOP_TERMINAL_EVIDENCE_CONFLICT" in result["classifications"]


def test_triggered_zero_fill_without_derived_order_is_not_assumed_filled():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "raw_status": "TRIGGERED",
        "requested_quantity": 0.13, "executed_quantity": 0.0,
        "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
    }])
    assert {"STOP_TRIGGERED", "STOP_DERIVED_ORDER_NOT_FOUND", "STOP_TRIGGERED_ZERO_FILL"}.issubset(result["classifications"])
    assert result["stop_filled"] is False


def test_triggered_with_missing_fill_quantity_remains_unknown_not_zero():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "raw_status": "TRIGGERED", "requested_quantity": 0.13,
    }])
    assert "STOP_TRIGGERED" in result["classifications"]
    assert "STOP_TRIGGERED_ZERO_FILL" not in result["classifications"]
    assert result["executed_quantity"] is None


def test_terminal_failed_zero_fill_projects_failure_reason_and_code():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "canceled", "raw_status": "FAILED",
        "requested_quantity": 0.13, "executed_quantity": 0.0,
        "failure_code": "109400", "failure_reason": "trigger market rejected",
    }])
    assert "STOP_FAILED" in result["classifications"]
    assert "FAILURE_REASON_AVAILABLE" in result["classifications"]
    assert result["terminal_status"] == "FAILED"
    assert result["stop_terminal_status"] == "FAILED"
    assert result["stop_failed"] is True
    assert result["stop_canceled"] is False
    assert "STOP_CANCELED_AFTER_TRIGGER" not in result["classifications"]
    assert "STOP_CANCELED_TRIGGER_PHASE_UNKNOWN" not in result["classifications"]
    assert result["order_statuses"] == ["CANCELED", "FAILED"]
    assert result["failure_code"] == "109400"


def test_canceled_zero_fill_without_trigger_evidence_keeps_trigger_phase_unknown():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "CANCELED", "executed_quantity": 0.0,
        "failed_at": "2026-07-19T13:36:34-03:00",
    }])
    assert "STOP_CANCELED_TRIGGER_PHASE_UNKNOWN" in result["classifications"]
    assert "STOP_CANCELED_BEFORE_TRIGGER" not in result["classifications"]
    assert "STOP_FILLED" not in result["classifications"]


def test_canceled_incident_preserves_reason_code_and_canceled_timestamp():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "source": "bingx.trade.order", "order_id": "STOP-1",
            "status": "CANCELED", "executed_quantity": 0.0,
            "failure_code": "CANCEL-9", "failure_reason": "conditional execution failed",
            "canceled_at": "2026-07-19T13:36:34-03:00",
        }],
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    assert result["failure_code"] == "CANCEL-9"
    assert result["failure_reason"] == "conditional execution failed"
    assert result["failure_cause_status"] == "FACTUAL_FAILURE_REASON_AVAILABLE"
    assert result["bingx_failure_timestamp"] == "2026-07-19T13:36:34-03:00"
    assert result["reported_manual_close_timestamp"] == "2026-07-19T13:39:33-03:00"
    assert result["failure_to_manual_close_seconds"] is None


def test_canceled_after_factual_trigger_is_classified_after_trigger():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "CANCELED", "plan_status": "TRIGGERED",
        "requested_quantity": 0.13, "executed_quantity": 0.0,
    }])
    assert "STOP_CANCELED_AFTER_TRIGGER" in result["classifications"]


def test_explicit_not_triggered_status_allows_before_trigger_classification():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "CANCELED", "plan_status": "NOT_TRIGGERED",
        "executed_quantity": 0.0,
    }])
    assert "STOP_CANCELED_BEFORE_TRIGGER" in result["classifications"]


def test_order_missing_from_open_but_failed_history_wins_over_disappearance():
    namespace, _, _ = _main_namespace()
    local = [
        {"event": "BROKER_DISASTER_STOP_CREATED", "stop_order_id": "STOP-1", "status": "DISASTER_STOP_CREATED"},
        {"event": "DISASTER_STOP_FAILED", "stop_order_id": "STOP-1", "status": "FAILED", "executed_quantity": 0.0},
    ]
    result = _classify(namespace, local=local)
    assert "STOP_FAILED" in result["classifications"]
    assert "STOP_FILLED" not in result["classifications"]


def test_disappearance_without_terminal_history_is_explicitly_inconclusive():
    namespace, _, _ = _main_namespace()
    local = [{"event": "BROKER_DISASTER_STOP_CREATED", "stop_order_id": "STOP-1", "status": "DISASTER_STOP_CREATED"}]
    result = _classify(namespace, local=local)
    assert "STOP_TERMINAL_STATUS_INCONCLUSIVE" in result["classifications"]
    assert result["terminal_status_known"] is False


def test_entry_fill_cannot_contaminate_stop_terminal_classification():
    namespace, _, _ = _main_namespace()
    local = [
        {"event": "BROKER_DISASTER_STOP_CREATED", "stop_order_id": "STOP-1", "status": "OPEN"},
        {"event": "BROKER_LIVE_SENT", "entry_order_id": "ENTRY-1", "order_id": "ENTRY-1", "status": "FILLED", "executed_quantity": 0.13},
    ]
    result = _classify(namespace, local=local)
    assert result["stop_filled"] is False
    assert "STOP_FILLED" not in result["classifications"]


def test_derived_market_failure_is_a_factual_stop_failure_with_its_reason():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{"order_id": "STOP-1", "plan_status": "TRIGGERED", "derived_order_id": "MARKET-1"}],
        derived=[{
            "order_id": "MARKET-1", "parent_order_id": "STOP-1", "raw_status": "FAILED",
            "failure_code": "CHILD-1", "failure_reason": "derived market rejected",
        }],
    )
    assert result["stop_failed"] is True
    assert result["terminal_status"] == "FAILED"
    assert result["failure_code"] == "CHILD-1"
    assert result["failure_reason"] == "derived market rejected"


def test_positive_execution_without_requested_quantity_is_not_called_full_fill():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "PARTIALLY_FILLED", "executed_quantity": 0.05,
    }])
    assert result["stop_filled"] is False
    assert "STOP_FILLED" not in result["classifications"]


def test_not_triggered_status_is_not_trigger_evidence():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "NOT_TRIGGERED", "executed_quantity": 0.0,
    }])
    assert result["stop_triggered"] is False
    assert "STOP_TRIGGERED" not in result["classifications"]


def test_local_broker_flat_anomaly_reason_is_not_promoted_to_bingx_failure_cause():
    namespace, _, _ = _main_namespace()
    local = [{
        "event": "FALCON_DISASTER_STOP_VERIFICATION_BLOCKED",
        "stop_order_id": "STOP-1",
        "status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
        "diagnostic_reason": "BROKER_FLAT_STOP_NOT_FILLED",
    }]
    result = _classify(namespace, local=local)
    assert result["stop_failed"] is False
    assert result["failure_reason"] is None
    assert result["failure_cause_status"] == "NOT_APPLICABLE_NO_FACTUAL_FAILURE"


def test_requested_quantity_013_is_preserved_and_partial_execution_is_mismatch():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1", "status": "PARTIALLY_FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.05, "executed_quantity_unit": "COIN",
    }])
    assert result["requested_quantity"] == pytest.approx(0.13)
    assert result["executed_quantity"] == pytest.approx(0.05)
    assert result["quantity_mismatch"] is True
    assert result["quantity_units_compatible"] is True


@pytest.mark.parametrize(
    ("requested_unit", "executed_unit"),
    [(None, None), ("COIN", "CONT"), ("COIN", "QUOTE")],
)
def test_quantity_mismatch_is_not_inferred_when_units_are_unknown_or_incompatible(
    requested_unit,
    executed_unit,
):
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "order_id": "STOP-1",
        "status": "PARTIALLY_FILLED",
        "requested_quantity": 0.13,
        "requested_quantity_unit": requested_unit,
        "executed_quantity": 0.05,
        "executed_quantity_unit": executed_unit,
    }])
    assert result["quantity_mismatch"] is None
    assert result["quantity_units_compatible"] is False


def test_missing_failure_reason_is_reported_explicitly():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{"order_id": "STOP-1", "raw_status": "FAILED", "executed_quantity": 0.0}])
    assert "FAILURE_REASON_UNAVAILABLE" in result["classifications"]
    assert result["failure_cause_status"] == "UNKNOWN_WITHOUT_FACTUAL_BINGX_REASON"


def test_position_still_open_after_failed_stop_is_factual_when_live_position_has_amount():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        local=[{
            "event": "DISASTER_STOP_FAILED",
            "stop_order_id": "STOP-1",
            "position_still_open_after_failure": True,
        }],
        stop=[{"order_id": "STOP-1", "raw_status": "FAILED", "executed_quantity": 0.0}],
        position={"ok": True, "amount": 0.13, "position_closed": False, "ownership_safe": True},
    )
    assert "POSITION_WAS_STILL_OPEN_AFTER_FAILURE" in result["classifications"]
    assert result["position_was_still_open_after_failure"] is True
    assert result["position_currently_open_at_lookup"] is True


def test_reported_manual_close_after_reported_failure_is_not_promoted_to_bingx_fact():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    assert "MANUAL_CLOSE_AFTER_REPORTED_FAILURE_TIMESTAMP" in result["classifications"]
    assert "MANUAL_CLOSE_AFTER_FACTUAL_FAILURE" not in result["classifications"]
    assert result["failure_to_manual_close_seconds"] == pytest.approx(179.0)
    assert result["reported_failure_timestamp"] == "2026-07-19T13:36:34-03:00"
    assert result["reported_manual_close_timestamp"] == "2026-07-19T13:39:33-03:00"
    assert result["bingx_failure_timestamp"] is None
    assert result["bingx_manual_close_timestamp"] is None


def test_factual_bingx_timestamps_prove_manual_close_after_failure():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        stop_orders=[{
            "order_id": "STOP-1",
            "raw_status": "FAILED",
            "failed_at": "2026-07-19T13:36:34-03:00",
        }],
        manual_close_orders=[{
            "order_id": "MANUAL-1",
            "raw_status": "FILLED",
            "updated_at": "2026-07-19T13:39:33-03:00",
        }],
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1",
        "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
    })
    assert "MANUAL_CLOSE_AFTER_FACTUAL_FAILURE" in result["classifications"]
    assert result["failure_to_manual_close_seconds"] == pytest.approx(179.0)
    assert result["bingx_failure_timestamp"] == "2026-07-19T13:36:34-03:00"
    assert result["bingx_manual_close_timestamp"] == "2026-07-19T13:39:33-03:00"


def test_reported_and_bingx_failure_timestamp_conflict_preserves_both_values():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "order_id": "STOP-1",
            "raw_status": "FAILED",
            "failed_at": "2026-07-19T13:35:00-03:00",
        }],
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert "FAILURE_TIMESTAMP_CONFLICT" in result["classifications"]
    assert result["bingx_failure_timestamp"] == "2026-07-19T13:35:00-03:00"
    assert result["reported_failure_timestamp"] == "2026-07-19T13:36:34-03:00"


def test_manual_close_fill_timestamp_is_preferred_and_conflict_is_rendered():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        stop_orders=[{
            "source": "bingx.swap_v2.trade.order.stop",
            "order_id": "STOP-1",
            "raw_status": "FAILED",
            "failed_at": "2026-07-19T13:36:34-03:00",
        }],
        manual_close_orders=[
            {
                "source": "bingx.swap_v2.trade.order.manual_close",
                "order_id": "MANUAL-1",
                "raw_status": "FILLED",
                "updated_at": "2026-07-19T13:45:00-03:00",
            },
            {
                "source": "bingx.swap_v2.trade.all_fill_orders",
                "order_id": "MANUAL-1",
                "raw_status": "FILLED",
                "executed_quantity": 0.13,
                "quantity_unit": "COIN",
                "updated_at": "2026-07-19T13:39:33-03:00",
            },
        ],
    )
    query = {
        "stop_order_id": "STOP-1",
        "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "failure_timestamp": "2026-07-19T13:36:34-03:00",
        "manual_close_timestamp": "2026-07-19T13:40:00-03:00",
    }
    findings = namespace["_fdsff_v1_classify"]([], live, query)
    assert findings["bingx_manual_close_timestamp"] == "2026-07-19T13:39:33-03:00"
    assert findings["reported_manual_close_timestamp"] == "2026-07-19T13:40:00-03:00"
    assert findings["manual_close_timestamp_conflict"] is True
    assert "FAILURE_TIMESTAMP_CONFLICT" in findings["classifications"]
    rendered = namespace["_fdsff_v1_text"]({
        "status": "FORENSICS_COMPLETE",
        "generated_at": "2026-07-19T15:00:00Z",
        "broker_called": False,
        "broker_call_state": "NOT_CALLED",
        "admin_auth": {"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
        "findings": findings,
        "live_lookup": live,
        "local_records": [],
        "reasons": [],
        "source_errors": [],
    })
    assert "bingx_manual_close_timestamp=2026-07-19T13:39:33-03:00" in rendered
    assert "reported_manual_close_timestamp=2026-07-19T13:40:00-03:00" in rendered
    assert "manual_close_timestamp_conflict=True" in rendered
    assert "FAILURE_TIMESTAMP_CONFLICT" in rendered


def test_absent_failsafe_and_critical_alert_are_reported_from_bounded_sources():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{"order_id": "STOP-1", "raw_status": "FAILED"}])
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" in result["classifications"]
    assert "CRITICAL_ALERT_NOT_FOUND" not in result["classifications"]
    assert "CRITICAL_ALERT_EVIDENCE_INCONCLUSIVE" in result["classifications"]


def test_failsafe_blocked_by_ownership_and_critical_condition_are_identified_without_assuming_alert():
    namespace, _, _ = _main_namespace()
    local = [
        {"event": "STOP_FAILSAFE", "status": "STOP_FAILSAFE_OWNERSHIP_EVIDENCE_INSUFFICIENT", "stop_order_id": "STOP-1"},
        {"event": "FALCON_DISASTER_STOP_VERIFICATION_BLOCKED", "status": "CRITICAL", "stop_order_id": "STOP-1"},
    ]
    result = _classify(namespace, local=local)
    assert "FAILSAFE_BLOCKED_BY_OWNERSHIP" in result["classifications"]
    assert "CRITICAL_CONDITION_FOUND" in result["classifications"]
    assert "CRITICAL_ALERT_NOT_FOUND" not in result["classifications"]
    assert result["failsafe_blocked_by_ownership"] is True


def test_failsafe_attempt_is_found_with_safe_details_but_not_marked_executed():
    namespace, _, _ = _main_namespace()
    local = [{
        "event": "BROKER_MANAGED_CLOSE_ERROR",
        "status": "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED",
        "lifecycle_id": "LC-1",
        "created_at": "2026-07-19T13:38:00-03:00",
        "failsafe_attempted": True,
        "failsafe_executed": False,
        "failsafe_decision": "ATTEMPT_CLOSE",
        "failsafe_block_reason": "BROKER_REJECTED",
        "error_type": "ExchangeError",
    }]
    result = _classify(
        namespace,
        local=local,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    assert "FAILSAFE_CLOSE_ATTEMPT_FOUND" in result["classifications"]
    assert result["failsafe_executed"] is False
    assert result["failsafe_attempt_before_manual_close_found"] is True
    assert result["failsafe_evidence"][0]["failsafe_decision"] == "ATTEMPT_CLOSE"


def test_critical_alert_suppression_is_separate_from_delivery_confirmation():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, local=[{
        "event": "FALCON_DISASTER_STOP_VERIFICATION_BLOCKED",
        "stop_order_id": "STOP-1",
        "alert_status": "SUPPRESSED_COOLDOWN",
        "alert_suppressed": True,
        "telegram_sent": False,
    }])
    assert "CRITICAL_ALERT_ATTEMPT_FOUND" not in result["classifications"]
    assert "CRITICAL_ALERT_SUPPRESSED" in result["classifications"]
    assert result["critical_alert_state_found"] is True
    assert result["critical_alert_attempt_found"] is None
    assert result["critical_alert_transport_called"] is None
    assert result["critical_alert_delivery_confirmed"] is None
    assert result["critical_alert_delivery_status"] == "UNKNOWN_INCOMPLETE_SOURCES"


def test_explicit_alert_attempt_and_transport_are_distinct_from_delivery():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, local=[{
        "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT",
        "stop_order_id": "STOP-1",
        "lifecycle_id": "LC-1",
        "created_at": "2026-07-19T13:37:00-03:00",
        "critical_alert_attempted": True,
        "critical_alert_transport_called": True,
        "telegram_sent": False,
    }])
    assert result["critical_alert_attempt_found"] is True
    assert result["critical_alert_transport_called"] is True
    assert result["critical_alert_delivery_confirmed"] is None
    assert result["critical_alert_evidence"][0]["stop_order_id"] == "STOP-1"
    assert result["critical_alert_evidence"][0]["lifecycle_id"] == "LC-1"
    assert result["critical_alert_evidence"][0]["created_at"] == "2026-07-19T13:37:00-03:00"


def test_telegram_sent_is_factual_alert_delivery_confirmation():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, local=[{
        "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT",
        "stop_order_id": "STOP-1",
        "telegram_sent": True,
    }])
    assert result["critical_alert_attempt_found"] is True
    assert result["critical_alert_transport_called"] is True
    assert result["critical_alert_delivery_confirmed"] is True


def test_generic_alert_sent_field_is_not_promoted_to_critical_alert_attempt():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_safe_record"]({
        "event": "DAILY_SUMMARY_SENT",
        "stop_order_id": "STOP-1",
        "alert_sent": True,
        "created_at": "2026-07-19T13:37:00-03:00",
    }, "test")
    result = _classify(namespace, local=[projected])
    assert result["critical_alert_attempt_found"] is None
    assert result["critical_alert_transport_called"] is None
    assert result["critical_alert_delivery_confirmed"] is None
    assert "CRITICAL_ALERT_ATTEMPT_FOUND" not in result["classifications"]


def test_blocked_alert_state_preserves_status_and_reason_without_inventing_attempt():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_safe_record"]({
        "event": "FALCON_DISASTER_STOP_VERIFICATION_BLOCKED",
        "stop_order_id": "STOP-1",
        "lifecycle_id": "LC-1",
        "alert_status": "BLOCKED",
        "alert_block_reason": "IDENTITY_EVIDENCE_INSUFFICIENT",
        "updated_at": "2026-07-19T13:37:00-03:00",
    }, "test")
    result = _classify(namespace, local=[projected])
    assert result["critical_alert_state_found"] is True
    assert result["critical_alert_blocked"] is True
    assert result["critical_alert_attempt_found"] is None
    evidence = result["critical_alert_state_evidence"][0]
    assert evidence["alert_status"] == "BLOCKED"
    assert evidence["alert_block_reason"] == "IDENTITY_EVIDENCE_INSUFFICIENT"
    assert evidence["stop_order_id"] == "STOP-1"
    assert evidence["lifecycle_id"] == "LC-1"


def test_stop_and_entry_roles_match_same_query_without_cross_rejection():
    namespace, _, _ = _main_namespace()
    query = {
        "stop_order_id": "STOP-1",
        "entry_order_id": "ENTRY-1",
        "client_order_id": "FALCON-LIVE-1",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
    }
    stop_record = {
        "event": "BROKER_DISASTER_STOP_CREATED",
        "order_id": "STOP-1",
        "clientOrderId": "FALCON-LIVE-1-DS",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "SELL",
        "positionSide": "LONG",
    }
    entry_record = {
        "event": "BROKER_LIVE_SENT",
        "order_id": "ENTRY-1",
        "clientOrderId": "FALCON-LIVE-1",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "BUY",
        "positionSide": "LONG",
    }
    safe_stop = namespace["_fdsff_v1_safe_record"](stop_record, "test")
    assert safe_stop["side"] == "SELL"
    assert safe_stop["position_side"] == "LONG"
    assert namespace["_fdsff_v1_matches"](stop_record, query) is True
    assert namespace["_fdsff_v1_matches"](entry_record, query) is True


def test_exact_stop_order_without_position_side_does_not_infer_trade_side_from_sell():
    namespace, _, _ = _main_namespace()
    assert namespace["_fdsff_v1_matches"]({
        "event": "BROKER_DISASTER_STOP_CREATED",
        "order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "SELL",
    }, {
        "stop_order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
    }) is True


def test_conflicting_stop_identity_is_rejected_even_when_lifecycle_matches():
    namespace, _, _ = _main_namespace()
    record = {
        "event": "DISASTER_STOP_FAILED", "stop_order_id": "OTHER-STOP",
        "lifecycle_id": "LC-1", "symbol": "SOLUSDT", "side": "LONG",
    }
    assert namespace["_fdsff_v1_matches"](record, {
        "stop_order_id": "STOP-1", "lifecycle_id": "LC-1", "symbol": "SOLUSDT", "side": "LONG",
    }) is False


@pytest.mark.parametrize("identity_field", ["requested_order_id", "plan_order_id"])
def test_main_matching_accepts_stop_plan_identity_without_overwriting_child_order(identity_field):
    namespace, _, _ = _main_namespace()
    record = {
        "event": "BROKER_DISASTER_STOP_STATUS",
        "order_id": "CHILD-1",
        identity_field: "STOP-1",
        "symbol": "SOLUSDT",
        "position_side": "LONG",
    }
    projected = namespace["_fdsff_v1_safe_record"](record, "test")
    assert projected["order_id"] == "CHILD-1"
    assert projected[identity_field] == "STOP-1"
    assert namespace["_fdsff_v1_matches"](record, {
        "stop_order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
    }) is True


def test_main_projection_preserves_conflicting_plan_and_child_id_for_diagnosis():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_safe_record"]({
        "event": "BROKER_DISASTER_STOP_STATUS",
        "order_id": "CHILD-1",
        "requested_order_id": "STOP-1",
        "plan_order_id": "OTHER-PLAN",
        "trigger_order_id": "TRIGGER-1",
    }, "test")
    assert projected["order_id"] == "CHILD-1"
    assert projected["requested_order_id"] == "STOP-1"
    assert projected["plan_order_id"] == "OTHER-PLAN"
    assert projected["trigger_order_id"] == "TRIGGER-1"


def test_manual_close_order_is_correlated_without_contaminating_stop_fill():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        stop_orders=[{
            "order_id": "STOP-1", "raw_status": "FAILED", "requested_quantity": 0.13,
            "executed_quantity": 0.0, "failed_at": "2026-07-19T13:36:34-03:00",
            "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
        }],
        manual_close_orders=[{
            "order_id": "MANUAL-1", "raw_status": "FILLED", "executed_quantity": 0.13,
            "average_fill_price": 75.924, "updated_at": "2026-07-19T13:39:33-03:00",
        }],
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1",
        "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "failure_timestamp": "2026-07-19T13:36:34-03:00",
        "manual_close_timestamp": "2026-07-19T13:39:33-03:00",
        "manual_close_quantity": "0.13",
        "manual_close_price": "75.924",
        "manual_close_value_usdt": "9.87",
        "manual_close_gross_pnl_usdt": "-0.03744",
        "manual_close_fee_usdt": "-0.0049",
        "close_reason": "DISASTER_STOP_FAILED_MANUAL_CLOSE",
    })
    assert result["stop_fill_evidence_status"] == "STOP_ZERO_FILL_CONFIRMED"
    assert result["executed_quantity"] == 0.0
    assert result["manual_close_executed_quantity"] == pytest.approx(0.13)
    assert result["manual_close_average_fill_price"] == pytest.approx(75.924)
    assert result["failure_to_manual_close_seconds"] == pytest.approx(179.0)
    assert result["manual_close_order_distinct_from_stop"] is True
    assert result["manual_close_order_linked_as_derived_conflict"] is False
    assert result["failsafe_attempt_before_manual_close_found"] is False


def _factual_full_manual_close_live(*, executed_quantity=0.13, executed_unit="COIN"):
    return _empty_live(
        stop_orders=[{
            "source": "bingx.swap_v2.trade.order.stop",
            "record_kind": "order",
            "order_id": "STOP-1",
            "status": "canceled",
            "raw_status": "FAILED",
            "plan_status": "TRIGGERED",
            "requested_quantity": 0.13,
            "requested_quantity_unit": "COIN",
            "executed_quantity": 0.0,
            "executed_quantity_unit": "COIN",
            "failed_at": "2026-07-19T13:36:34-03:00",
        }],
        manual_close_orders=[
            {
                "source": "bingx.swap_v2.trade.order.manual_close",
                "record_kind": "order",
                "order_id": "MANUAL-1",
                "raw_status": "FILLED",
                "requested_quantity": 0.13,
                "requested_quantity_unit": "COIN",
                "executed_quantity": executed_quantity,
                "executed_quantity_unit": executed_unit,
                "filled_at": "2026-07-19T13:39:33-03:00",
            },
            {
                "source": "bingx.swap_v2.trade.all_fill_orders",
                "record_kind": "trade",
                "order_id": "MANUAL-1",
                "raw_status": "FILLED",
                "fill_id": "MANUAL-FILL-1",
                "fill_time": "2026-07-19T13:39:33-03:00",
                "fill_quantity": executed_quantity,
                "fill_quantity_unit": executed_unit,
                "executed_quantity": executed_quantity,
                "executed_quantity_unit": executed_unit,
                "fill_price": 75.924,
            },
        ],
        position={
            "ok": True,
            "amount": 0.0,
            "position_closed": True,
            "ownership_safe": True,
            "ownership_basis": "EXACT_LIFECYCLE_AND_ORDER_IDS",
        },
    )


def test_factual_full_manual_close_after_failed_stop_infers_historical_open_position_while_currently_flat():
    namespace, _, _ = _main_namespace()
    result = namespace["_fdsff_v1_classify"](
        [],
        _factual_full_manual_close_live(),
        {
            "stop_order_id": "STOP-1",
            "manual_close_order_id": "MANUAL-1",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "failure_timestamp": "2026-07-19T13:36:34-03:00",
            "manual_close_timestamp": "2026-07-19T13:39:33-03:00",
            "manual_close_quantity": "0.13",
        },
    )

    assert result["terminal_status"] == "FAILED"
    assert result["stop_failed"] is True
    assert result["stop_canceled"] is False
    assert result["manual_close_occurred_after_failure"] is True
    assert result["factual_manual_close_full_quantity"] is True
    assert result["factual_manual_close_execution_basis"] == "SUM_UNIQUE_EXACT_FILLS"
    assert result["position_open_after_failure_inferred_from_manual_close"] is True
    assert result["position_was_still_open_after_failure"] is True
    assert result["position_currently_open_at_lookup"] is False
    assert result["position_evidence_basis"] == "FACTUAL_FULL_MANUAL_CLOSE_AFTER_FAILURE"
    assert "POSITION_WAS_STILL_OPEN_AFTER_FAILURE" in result["classifications"]

    text = namespace["_fdsff_v1_text"]({
        "status": "FORENSICS_COMPLETE",
        "findings": result,
        "live_lookup": {},
        "local_records": [],
        "reasons": [],
        "source_errors": [],
    })
    assert "terminal_status=FAILED" in text
    assert "position_currently_open_at_lookup=False" in text
    assert "position_open_after_failure_inferred_from_manual_close=True" in text
    assert "position_was_still_open_after_failure=True" in text
    assert "position_evidence_basis=FACTUAL_FULL_MANUAL_CLOSE_AFTER_FAILURE" in text


@pytest.mark.parametrize(
    ("executed_quantity", "executed_unit"),
    [
        (0.07, "COIN"),
        (0.13, "CONT"),
    ],
)
def test_partial_or_unit_incompatible_manual_close_does_not_infer_historical_open_position(
    executed_quantity,
    executed_unit,
):
    namespace, _, _ = _main_namespace()
    result = namespace["_fdsff_v1_classify"](
        [],
        _factual_full_manual_close_live(
            executed_quantity=executed_quantity,
            executed_unit=executed_unit,
        ),
        {
            "stop_order_id": "STOP-1",
            "manual_close_order_id": "MANUAL-1",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "failure_timestamp": "2026-07-19T13:36:34-03:00",
            "manual_close_timestamp": "2026-07-19T13:39:33-03:00",
            "manual_close_quantity": "0.13",
        },
    )

    assert result["factual_manual_close_full_quantity"] is False
    assert result["position_open_after_failure_inferred_from_manual_close"] is False
    assert result["position_was_still_open_after_failure"] is False
    assert result["position_evidence_basis"] is None


def test_reported_only_manual_close_never_infers_historical_open_position():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{
            "order_id": "STOP-1",
            "raw_status": "FAILED",
            "requested_quantity": 0.13,
            "requested_quantity_unit": "COIN",
            "executed_quantity": 0.0,
            "executed_quantity_unit": "COIN",
        }],
        manual_close_order_id="MANUAL-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
        manual_close_quantity="0.13",
    )

    assert result["manual_close_after_reported_failure_timestamp"] is True
    assert result["manual_close_occurred_after_failure"] is False
    assert result["factual_manual_close_full_quantity"] is False
    assert result["position_open_after_failure_inferred_from_manual_close"] is False
    assert result["position_was_still_open_after_failure"] is False


def test_creation_updated_at_never_overrides_supplied_failure_timestamp():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        local=[{
            "event": "BROKER_DISASTER_STOP_CREATED",
            "stop_order_id": "STOP-1",
            "status": "OPEN",
            "updated_at": "2026-07-19T11:15:42-03:00",
        }],
        stop=[{"order_id": "STOP-1", "raw_status": "FAILED", "executed_quantity": 0.0}],
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    assert result["failure_to_manual_close_seconds"] == pytest.approx(179.0)


def test_manual_close_id_linked_as_stop_derived_order_is_flagged_as_identity_conflict():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{"order_id": "STOP-1", "plan_status": "TRIGGERED", "derived_order_id": "MANUAL-1"}],
        derived=[{"order_id": "MANUAL-1", "parent_order_id": "STOP-1", "raw_status": "FILLED"}],
        manual_close_order_id="MANUAL-1",
    )
    assert result["manual_close_order_linked_as_derived_conflict"] is True
    assert "MANUAL_CLOSE_ORDER_LINKED_AS_DERIVED_CONFLICT" in result["classifications"]


def test_live_lookup_without_exact_ack_never_touches_broker():
    namespace, broker, _ = _main_namespace()
    payload = _build(namespace, live_lookup="true", ack="WRONG")
    assert payload["broker_called"] is False
    assert broker.read_calls == []
    assert "LIVE_LOOKUP_ACK_REQUIRED" in payload["reasons"]


def test_admin_auth_helper_accepts_only_valid_header_source():
    namespace, _, _ = _main_namespace()
    namespace["_ee_auth_resolver_v1_resolve"] = lambda **kwargs: {
        "ok": True,
        "configured": True,
        "status": "EXECUTION_AUTH_OK",
        "matched_source": "request.headers.X-Execution-Auth-Token",
        "token_value_exposed": False,
    }
    with Flask(__name__).test_request_context(
        "/falcon/disasterstop/failure/diagnostic/text",
        headers={"X-Execution-Auth-Token": "ADMIN-SECRET"},
    ):
        result = namespace["_fdsff_v1_admin_auth_real"]()
    assert result == {
        "available": True,
        "authenticated": True,
        "status": "ADMIN_AUTH_OK",
    }
    assert "ADMIN-SECRET" not in json.dumps(result)


@pytest.mark.parametrize(
    "matched_source",
    [
        "request.args.execution_auth_token",
        "request.form.execution_auth_token",
        "request.json.execution_auth_token",
        "env_fallback.EXECUTION_AUTH_TOKEN",
    ],
)
def test_admin_auth_helper_rejects_non_header_sources(matched_source):
    namespace, _, _ = _main_namespace()
    namespace["_ee_auth_resolver_v1_resolve"] = lambda **kwargs: {
        "ok": True,
        "configured": True,
        "status": "EXECUTION_AUTH_OK",
        "matched_source": matched_source,
        "token_value_exposed": False,
    }
    with Flask(__name__).test_request_context(
        "/falcon/disasterstop/failure/diagnostic/text",
    ):
        result = namespace["_fdsff_v1_admin_auth_real"]()
    assert result["available"] is True
    assert result["authenticated"] is False
    assert result["status"] == "ADMIN_AUTH_REQUIRED"


def test_admin_auth_query_alias_is_rejected_even_if_resolver_would_accept_a_header():
    namespace, _, _ = _main_namespace()
    namespace["_ee_auth_resolver_v1_resolve"] = lambda **kwargs: {
        "ok": True,
        "configured": True,
        "status": "EXECUTION_AUTH_OK",
        "matched_source": "request.headers.X-Execution-Auth-Token",
    }
    with Flask(__name__).test_request_context(
        "/falcon/disasterstop/failure/diagnostic/text?execution_auth_token=QUERY-SECRET",
    ):
        result = namespace["_fdsff_v1_admin_auth_real"]()
    assert result["authenticated"] is False
    assert result["status"] == "ADMIN_AUTH_REQUIRED"
    assert "QUERY-SECRET" not in json.dumps(result)


def test_admin_auth_helper_reports_guard_unavailable_when_no_token_is_configured():
    namespace, _, _ = _main_namespace()
    namespace["_ee_auth_resolver_v1_resolve"] = lambda **kwargs: {
        "ok": False,
        "configured": False,
        "status": "MISSING_CONFIGURED_EXECUTION_AUTH_TOKEN",
        "token_value_exposed": False,
    }
    with Flask(__name__).test_request_context(
        "/falcon/disasterstop/failure/diagnostic/text",
    ):
        result = namespace["_fdsff_v1_admin_auth_real"]()
    assert result == {
        "available": False,
        "authenticated": False,
        "status": "ADMIN_AUTH_GUARD_UNAVAILABLE",
    }


def test_admin_auth_guard_unavailable_blocks_all_sources_and_live_reader():
    namespace, broker, registry = _main_namespace()
    namespace["_fdsff_v1_admin_auth"] = lambda: {
        "available": False,
        "authenticated": False,
        "status": "ADMIN_AUTH_GUARD_UNAVAILABLE",
    }
    namespace["_fdsff_v1_read_registry"] = lambda _query: pytest.fail("registry reader called")
    namespace["_fdsff_v1_read_falcon_health"] = lambda _query: pytest.fail("health reader called")
    namespace["_fdsff_v1_read_local_events"] = lambda _query: pytest.fail("local reader called")
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get(
        "/falcon/disasterstop/failure/diagnostic/text"
        "?stop_order_id=STOP-1&symbol=SOLUSDT&live_lookup=true"
        "&ack=FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1"
    )
    rendered = response.get_data(as_text=True)
    assert response.status_code == 503
    assert "ADMIN_AUTH_GUARD_UNAVAILABLE" in rendered
    assert broker.read_calls == []
    assert registry.read_calls == 0


def test_ack_without_admin_auth_is_blocked_before_any_sensitive_reader():
    namespace, broker, registry = _main_namespace()
    namespace["_fdsff_v1_admin_auth"] = lambda: {
        "available": True,
        "authenticated": False,
        "status": "ADMIN_AUTH_REQUIRED",
    }
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get(
        "/falcon/disasterstop/failure/diagnostic/text"
        "?stop_order_id=STOP-1&symbol=SOLUSDT&live_lookup=true"
        "&ack=FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1"
    )
    assert response.status_code == 403
    assert "ADMIN_AUTH_REQUIRED" in response.get_data(as_text=True)
    assert broker.read_calls == []
    assert registry.read_calls == 0


def test_admin_auth_without_ack_keeps_live_reader_blocked():
    namespace, broker, _ = _main_namespace()
    payload = namespace["_fdsff_v1_build_payload"](
        _query(namespace, live_lookup="true", ack="WRONG"),
        admin_auth={"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
    )
    assert payload["admin_auth"] == {
        "available": True,
        "authenticated": True,
        "status": "ADMIN_AUTH_OK",
    }
    assert payload["broker_call_state"] == "NOT_CALLED"
    assert payload["broker_called"] is False
    assert broker.read_calls == []


def test_admin_auth_plus_ack_uses_only_read_only_reader_and_never_exposes_header_token():
    namespace, broker, registry = _main_namespace()
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get(
        "/falcon/disasterstop/failure/diagnostic/text"
        "?stop_order_id=STOP-1&symbol=SOLUSDT&live_lookup=true"
        "&ack=FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
        headers={"X-Execution-Auth-Token": "NEVER-RETURN-THIS-TOKEN"},
    )
    rendered = response.get_data(as_text=True)
    assert response.status_code == 200
    assert len(broker.read_calls) == 1
    assert broker.mutation_calls == []
    assert registry.write_calls == []
    assert "READ_ONLY_CALL_COMPLETED" in rendered
    assert "NEVER-RETURN-THIS-TOKEN" not in rendered


def test_live_lookup_with_ack_calls_only_the_read_only_helper():
    live = _empty_live(stop_orders=[{
        "source": "bingx.trade.all_orders", "order_id": "STOP-1",
        "status": "canceled", "raw_status": "FAILED", "requested_quantity": 0.13,
        "executed_quantity": 0.0, "failure_reason": "safe reason",
    }])
    namespace, broker, registry = _main_namespace(live_result=live)
    payload = _build(
        namespace,
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    assert payload["broker_called"] is True
    assert payload["broker_call_state"] == "READ_ONLY_CALL_COMPLETED"
    assert len(broker.read_calls) == 1
    assert broker.mutation_calls == []
    assert registry.write_calls == []
    assert payload["findings"]["terminal_status"] == "FAILED"


def test_reader_exception_after_call_start_is_not_reported_as_not_called():
    namespace, broker, _ = _main_namespace()

    def fail_reader(**kwargs):
        broker.read_calls.append(copy.deepcopy(kwargs))
        raise RuntimeError("read failed after request started")

    broker.disaster_stop_failure_forensics_read_only = fail_reader
    payload = _build(
        namespace,
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    assert len(broker.read_calls) == 1
    assert payload["broker_called"] is True
    assert payload["broker_call_state"] == "READ_ONLY_CALL_STARTED"
    assert payload["broker_call_state"] != "NOT_CALLED"
    assert "live_lookup:READ_ERROR:RuntimeError" in payload["source_errors"]


def test_manual_close_identity_flows_query_builder_reader_classifier_and_text_without_stop_fill_contamination():
    live = _empty_live(
        stop_orders=[{
            "order_id": "STOP-1", "raw_status": "FAILED", "requested_quantity": 0.13,
            "executed_quantity": 0.0, "failed_at": "2026-07-19T13:36:34-03:00",
            "requested_quantity_unit": "COIN", "executed_quantity_unit": "COIN",
        }],
        manual_close_orders=[{
            "order_id": "MANUAL-1", "raw_status": "FILLED", "executed_quantity": 0.13,
            "average_fill_price": 75.924, "updated_at": "2026-07-19T13:39:33-03:00",
        }],
    )
    namespace, broker, _ = _main_namespace(live_result=live)
    payload = _build(
        namespace,
        manual_close_order_id="MANUAL-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
        manual_close_price="75.924",
        manual_close_quantity="0.13",
        manual_close_value_usdt="9.87",
        manual_close_gross_pnl_usdt="-0.03744",
        manual_close_fee_usdt="-0.0049",
        close_reason="DISASTER_STOP_FAILED_MANUAL_CLOSE",
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    assert broker.read_calls[0]["manual_close_order_id"] == "MANUAL-1"
    assert payload["findings"]["executed_quantity"] == 0.0
    assert payload["findings"]["manual_close_executed_quantity"] == pytest.approx(0.13)
    assert payload["findings"]["failure_to_manual_close_seconds"] == pytest.approx(179.0)
    rendered = namespace["_fdsff_v1_text"](payload)
    assert "manual_close_order_id=MANUAL-1" in rendered
    assert "stop_fill_evidence_status=STOP_ZERO_FILL_CONFIRMED" in rendered


def test_live_lookup_requires_exact_stop_id_and_symbol_even_with_ack():
    namespace, broker, _ = _main_namespace()
    query = namespace["_fdsff_v1_extract_query"]({
        "lifecycle_id": "LC-1",
        "live_lookup": "true",
        "ack": "FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    })
    payload = namespace["_fdsff_v1_build_payload"](
        query,
        admin_auth={"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
    )
    assert payload["broker_called"] is False
    assert broker.read_calls == []
    assert "LIVE_LOOKUP_REQUIRES_STOP_ORDER_ID_AND_SYMBOL" in payload["reasons"]


def test_endpoint_returns_all_safety_guards_and_performs_no_action():
    namespace, broker, registry = _main_namespace()
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1&symbol=SOLUSDT&side=LONG"
    )
    text = response.get_data(as_text=True)
    assert response.status_code == 200
    for expected in (
        "no_order_sent_by_this_route=True",
        "would_send_order=False",
        "cancel_called=False",
        "close_called=False",
        "position_modified=False",
        "registry_write=False",
        "management_executed=False",
        "reconciliation_executed=False",
        "broker_called=False",
    ):
        assert expected in text
    assert broker.mutation_calls == []
    assert registry.write_calls == []


def test_endpoint_without_params_is_safe_and_does_not_scan_or_call_broker():
    namespace, broker, _ = _main_namespace()
    payload = namespace["_fdsff_v1_build_payload"](
        namespace["_fdsff_v1_extract_query"]({}),
        admin_auth={"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
    )
    assert payload["status"] == "FORENSICS_INCONCLUSIVE"
    assert "FORENSIC_IDENTITY_REQUIRED" in payload["reasons"]
    assert payload["local_records"] == []
    assert broker.read_calls == []


def test_negative_findings_never_claim_global_source_completeness():
    namespace, _, _ = _main_namespace()
    payload = _build(namespace)
    assert payload["findings"]["source_completeness"] == "BOUNDED_LOCAL_ONLY_LIVE_NOT_CONSULTED"
    assert "LOCAL_ONLY" in payload["findings"]["negative_evidence_scope"]
    assert "NO_ABSENCE_CLAIM" in payload["findings"]["negative_evidence_scope"]


def test_failed_local_reader_disables_absence_claims_and_marks_partial_scope():
    namespace, _, _ = _main_namespace()
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        [], ["history_events:READ_ERROR:OSError"], 1,
    )
    payload = _build(namespace)
    classifications = set(payload["findings"].get("classifications") or [])
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" not in classifications
    assert "CRITICAL_ALERT_NOT_FOUND" not in classifications
    assert payload["findings"].get("failsafe_close_attempt_found") is not False
    assert payload["findings"].get("critical_alert_attempt_found") is not False
    assert "NO_ABSENCE_CLAIM" in payload["findings"]["negative_evidence_scope"]
    assert payload["findings"]["source_completeness"] == "PARTIAL_WITH_REPORTED_ERRORS"


def test_live_not_requested_reports_local_only_negative_evidence_scope():
    namespace, _, _ = _main_namespace()
    payload = _build(namespace, live_lookup="false")
    assert payload["live_lookup_requested"] is False
    assert payload["broker_call_state"] == "NOT_CALLED"
    assert "LOCAL_ONLY" in payload["findings"]["negative_evidence_scope"]
    assert "NO_ABSENCE_CLAIM" in payload["findings"]["negative_evidence_scope"]
    assert "AUTHORIZED_LIVE" not in payload["findings"]["negative_evidence_scope"]


def test_two_bots_and_lifecycles_on_same_symbol_side_never_mix_registry_evidence():
    registry = FakeRegistry(open_trades={
        "falcon": {
            "bot": "FALCON", "trade_id": "FALCON-1", "lifecycle_id": "LC-FALCON",
            "stop_order_id": "STOP-FALCON", "symbol": "SOLUSDT", "side": "LONG",
        },
        "falcon_other": {
            "bot": "FALCON", "trade_id": "FALCON-2", "lifecycle_id": "LC-FALCON-OTHER",
            "stop_order_id": "STOP-FALCON-OTHER", "symbol": "SOLUSDT", "side": "LONG",
        },
        "donkey": {
            "bot": "DONKEY", "trade_id": "DONKEY-1", "lifecycle_id": "LC-DONKEY",
            "stop_order_id": "STOP-DONKEY", "symbol": "SOLUSDT", "side": "LONG",
        },
    })
    namespace, _, _ = _main_namespace(registry=registry)
    rows, error = namespace["_fdsff_v1_read_registry_real"]({
        "stop_order_id": "STOP-FALCON",
        "lifecycle_id": "LC-FALCON",
        "symbol": "SOLUSDT",
        "side": "LONG",
    })
    assert error is None
    assert len(rows) == 1
    assert rows[0]["trade_id"] == "FALCON-1"
    assert rows[0]["lifecycle_id"] == "LC-FALCON"
    assert rows[0]["stop_order_id"] == "STOP-FALCON"


def test_symbol_only_never_authorizes_sensitive_forensics_correlation_or_readers():
    namespace, broker, registry = _main_namespace()
    namespace["_fdsff_v1_read_registry"] = lambda _query: pytest.fail("registry reader called")
    namespace["_fdsff_v1_read_falcon_health"] = lambda _query: pytest.fail("health reader called")
    namespace["_fdsff_v1_read_snapshot_records"] = lambda *_args: pytest.fail("snapshot reader called")
    namespace["_fdsff_v1_read_local_events"] = lambda _query: pytest.fail("event reader called")
    query_info = namespace["_fdsff_v1_extract_query"]({"symbol": "SOLUSDT"})
    payload = namespace["_fdsff_v1_build_payload"](
        query_info,
        admin_auth={"available": True, "authenticated": True, "status": "ADMIN_AUTH_OK"},
    )
    assert payload["local_records"] == []
    assert all(value == 0 for value in payload["local_source_counts"].values())
    assert "FORENSIC_IDENTITY_REQUIRED" in payload["reasons"]
    assert payload["broker_call_state"] == "NOT_CALLED"
    assert broker.read_calls == []
    assert registry.read_calls == 0


def test_text_response_is_hard_capped_with_explicit_truncation_marker():
    namespace, _, _ = _main_namespace()
    huge_row = {
        key: "X" * 500
        for key in namespace["_FDSFF_V1_ORDER_FIELDS"]
    }
    payload = {
        "status": "FORENSICS_COMPLETE",
        "generated_at": "2026-07-19T15:00:00Z",
        "findings": {"classifications": []},
        "live_lookup": {
            "status": "READ_ONLY_LOOKUP_COMPLETE",
            "stop_orders": [copy.deepcopy(huge_row) for _ in range(100)],
            "derived_orders": [copy.deepcopy(huge_row) for _ in range(100)],
            "entry_orders": [copy.deepcopy(huge_row) for _ in range(100)],
            "manual_close_orders": [copy.deepcopy(huge_row) for _ in range(100)],
        },
        "local_records": [copy.deepcopy(huge_row) for _ in range(100)],
    }
    rendered = namespace["_fdsff_v1_text"](payload)
    assert len(rendered.encode("utf-8")) <= 256 * 1024
    assert rendered.endswith("OUTPUT_TRUNCATED_AT_256_KIB=True")


def test_slim_critical_event_uses_original_event_for_matching_and_classification():
    namespace, _, _ = _main_namespace()
    raw = {
        "event": "HISTORY_ROTATION_PRESERVED_CRITICAL_EVENT",
        "original_event": "DISASTER_STOP_FAILED",
        "order_id": "STOP-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "status": "FAILED",
    }
    safe = namespace["_fdsff_v1_safe_record"](raw, "history.events")
    assert safe["event"] == "DISASTER_STOP_FAILED"
    assert namespace["_fdsff_v1_matches"](raw, {"stop_order_id": "STOP-1"}) is True


def test_registry_reader_is_read_only_and_lists_matching_open_trade():
    registry = FakeRegistry(open_trades={"A": {
        "trade_id": "TR-1", "lifecycle_id": "LC-1", "bot": "FALCON",
        "symbol": "SOLUSDT", "side": "LONG", "broker_stop_order_id": "STOP-1",
        "status": "OPEN",
    }})
    namespace, _, registry = _main_namespace(registry=registry)
    rows, error = namespace["_fdsff_v1_read_registry_real"]({"stop_order_id": "STOP-1"})
    assert error is None
    assert len(rows) == 1
    assert rows[0]["registry_collection"] == "open_trades"
    assert registry.read_calls == 1
    assert registry.write_calls == []


def test_falcon_health_reader_projects_stop_and_spam_guard_without_side_effects():
    namespace, _, _ = _main_namespace()
    module = type("FalconProbe", (), {"HEALTH": {
        "falcon_disaster_stop_order_id": "STOP-1",
        "falcon_disaster_stop_order_status": "CANCELED",
        "falcon_stop_anomaly_symbol": "SOLUSDT",
        "falcon_stop_anomaly_side": "LONG",
        "falcon_management_spam_guard_status": "SUPPRESSED_COOLDOWN",
        "falcon_management_spam_guard_last_reason": "DISASTER_STOP_INACTIVE_WITH_POSITION_OPEN",
        "falcon_management_spam_guard_suppressed_count": 3,
    }})()
    namespace["LOADED_BOTS"] = {"FALCON": module}
    rows, error = namespace["_fdsff_v1_read_falcon_health_real"]({
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert error is None
    assert len(rows) == 1
    assert rows[0]["alert_status"] == "SUPPRESSED_COOLDOWN"
    assert rows[0]["alert_suppressed_count"] == 3


def test_bounded_local_event_reader_uses_only_fixed_sources_and_exact_identity(tmp_path):
    namespace, broker, _ = _main_namespace()
    history_path = tmp_path / "history.jsonl"
    broker.EXECUTION_AUDIT_LOG_FILE = tmp_path / "audit.jsonl"
    broker.EXECUTIONS_LOG_FILE = tmp_path / "executions.jsonl"
    namespace["super_history_manager"] = type("HistoryProbe", (), {"HISTORY_EVENTS_FILE": history_path})()
    namespace["FALCON_LIVE_AUDIT_EVENTS_FILE"] = tmp_path / "falcon.jsonl"
    namespace["CENTRAL_TIMELINE_LOG_FILE"] = tmp_path / "timeline.jsonl"
    row = {
        "event": "DISASTER_STOP_FAILED", "stop_order_id": "STOP-1",
        "symbol": "SOLUSDT", "side": "LONG", "status": "FAILED",
        "created_at": "2026-07-19T13:36:34-03:00",
    }
    for path in (
        history_path, broker.EXECUTION_AUDIT_LOG_FILE, broker.EXECUTIONS_LOG_FILE,
        namespace["FALCON_LIVE_AUDIT_EVENTS_FILE"], namespace["CENTRAL_TIMELINE_LOG_FILE"],
    ):
        Path(path).write_text(json.dumps(row) + "\n", encoding="utf-8")
    rows, errors, checked, metadata = namespace["_fdsff_v1_read_local_events_real"]({
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert errors == []
    assert checked == 5
    assert len(rows) == 5
    assert len(metadata) == 5
    assert all(item["rows_read"] == 1 for item in metadata)
    assert all(row["stop_order_id"] == "STOP-1" for row in rows)


def test_snapshot_reader_rejects_oversized_file_without_reading_content(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b"x" * 32)
    namespace, _, _ = _main_namespace()
    namespace["_FDSFF_V1_MAX_SNAPSHOT_BYTES"] = 16
    rows, error = namespace["_fdsff_v1_read_snapshot_records_real"](path, "snapshot", {"stop_order_id": "STOP-1"})
    assert rows == []
    assert error == "SNAPSHOT_TOO_LARGE"


def test_snapshot_reader_never_builds_a_cross_order_frankenstein_record(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({
        "orders": [
            {"order_id": "STOP-1", "status": "OPEN", "symbol": "SOLUSDT"},
            {"order_id": "OTHER-1", "status": "FILLED", "executed_quantity": 0.13},
        ]
    }), encoding="utf-8")
    namespace, _, _ = _main_namespace()
    rows, error = namespace["_fdsff_v1_read_snapshot_records_real"](
        path, "snapshot", {"stop_order_id": "STOP-1"},
    )
    assert error is None
    assert len(rows) == 1
    assert rows[0]["order_id"] == "STOP-1"
    assert rows[0]["status"] == "OPEN"
    assert rows[0].get("executed_quantity") is None


def test_public_payload_drops_raw_info_paths_headers_and_secret_values():
    live = _empty_live(stop_orders=[{
        "source": "bingx", "order_id": "STOP-1", "raw_status": "FAILED",
        "failure_reason": "api_key=TOPSECRET signature=BAD",
        "raw": {"secret": "TOPSECRET"},
        "info": {"apiKey": "TOPSECRET"},
        "path": "C:/private/data.jsonl",
        "headers": {"Authorization": "Bearer TOPSECRET"},
    }])
    namespace, _, _ = _main_namespace(live_result=live)
    payload = _build(
        namespace,
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    serialized = json.dumps(payload)
    assert "TOPSECRET" not in serialized
    assert '"raw"' not in serialized
    assert '"info"' not in serialized
    assert '"path"' not in serialized
    assert '"headers"' not in serialized
    assert payload["raw_payload_exposed"] is False


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "C:/private/history.jsonl",
        "c:/private/history.jsonl",
        "/home/render/private.json",
        "/opt/service/private.json",
        "/var/data/private.json",
        "apiSecret=DO_NOT_EXPOSE",
        "secret: DO_NOT_EXPOSE",
        "token: DO_NOT_EXPOSE",
        "authorization=Bearer DO_NOT_EXPOSE",
    ],
)
def test_main_scalar_redaction_blocks_paths_and_secret_assignments(sensitive_value):
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_safe_scalar"](sensitive_value)
    assert projected == "REDACTED_SENSITIVE_VALUE"
    assert "DO_NOT_EXPOSE" not in str(projected)


def test_route_internal_exception_is_sanitized_and_preserves_all_safety_flags():
    namespace, _, _ = _main_namespace()
    namespace["_fdsff_v1_build_payload"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("TOPSECRET /home/private"))
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get("/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1")
    text = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "TOPSECRET" not in text
    assert "/home/private" not in text
    assert "INTERNAL_ROUTE_ERROR:RuntimeError" in text
    assert "no_order_sent_by_this_route=True" in text
    assert "registry_write=False" in text


def test_route_error_after_reader_start_does_not_claim_broker_was_not_called():
    namespace, _, _ = _main_namespace()

    def fail_after_reader_started(_query, admin_auth=None, route_state=None):
        route_state["broker_call_state"] = "READ_ONLY_CALL_STARTED"
        raise RuntimeError("after reader started")

    namespace["_fdsff_v1_build_payload"] = fail_after_reader_started
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    response = app.test_client().get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1&symbol=SOLUSDT"
    )
    rendered = response.get_data(as_text=True)
    assert response.status_code == 500
    assert "broker_call_state=UNKNOWN_AFTER_ROUTE_ERROR" in rendered
    assert "broker_called=None" in rendered
    assert "broker_called=False" not in rendered
    assert "cancel_called=False" in rendered
    assert "close_called=False" in rendered
    assert "position_modified=False" in rendered


def _broker_namespace(
    *,
    exact_order=None,
    raw_exact_orders=None,
    recent_orders=None,
    raw_orders=None,
    raw_fills=None,
    raw_all_orders_response=None,
    raw_fill_orders_response=None,
    trades=None,
    position_result=None,
    raw_fail_methods=None,
):
    calls = []
    raw_exact_orders = copy.deepcopy(raw_exact_orders or {})
    raw_fail_methods = set(raw_fail_methods or ())

    def fetch_order_by_id(symbol, order_id=None, client_order_id=None):
        calls.append(("fetch_order_by_id", symbol, order_id, client_order_id))
        return {"ok": bool(exact_order), "order": copy.deepcopy(exact_order)}

    def fetch_recent_orders(symbol=None, since=None, limit=100):
        calls.append(("fetch_recent_orders", symbol, since, limit))
        return {"ok": True, "orders": copy.deepcopy(recent_orders or []), "errors": []}

    class ReadOnlyExchange:
        enableRateLimit = True

        def _record(self, method_name, params):
            calls.append(("raw_get", method_name, copy.deepcopy(params)))
            if method_name in raw_fail_methods:
                raise RuntimeError(f"simulated read failure: {method_name}")

        def swapV2PrivateGetTradeOrder(self, params):
            self._record("swapV2PrivateGetTradeOrder", params)
            order = raw_exact_orders.get(str(params.get("orderId")))
            return {"data": {"order": copy.deepcopy(order)}} if order else {"data": {}}

        def swap_v2_private_get_trade_order(self, params):
            self._record("swap_v2_private_get_trade_order", params)
            order = raw_exact_orders.get(str(params.get("orderId")))
            return {"data": {"order": copy.deepcopy(order)}} if order else {"data": {}}

        def swapV2PrivateGetTradeAllOrders(self, params):
            self._record("swapV2PrivateGetTradeAllOrders", params)
            if raw_all_orders_response is not None:
                return copy.deepcopy(raw_all_orders_response)
            return {"data": {"orders": copy.deepcopy(raw_orders or [])}}

        def swap_v2_private_get_trade_all_orders(self, params):
            self._record("swap_v2_private_get_trade_all_orders", params)
            if raw_all_orders_response is not None:
                return copy.deepcopy(raw_all_orders_response)
            return {"data": {"orders": copy.deepcopy(raw_orders or [])}}

        def swapV2PrivateGetTradeAllFillOrders(self, params):
            self._record("swapV2PrivateGetTradeAllFillOrders", params)
            if raw_fill_orders_response is not None:
                return copy.deepcopy(raw_fill_orders_response)
            rows = copy.deepcopy(raw_fills or [])
            requested = str(params.get("orderId") or "")
            if requested:
                rows = [
                    row for row in rows
                    if str(row.get("orderId") or row.get("order_id") or row.get("order") or "") == requested
                ]
            return {"data": {"fill_orders": rows}}

        def swap_v2_private_get_trade_all_fill_orders(self, params):
            self._record("swap_v2_private_get_trade_all_fill_orders", params)
            if raw_fill_orders_response is not None:
                return copy.deepcopy(raw_fill_orders_response)
            rows = copy.deepcopy(raw_fills or [])
            requested = str(params.get("orderId") or "")
            if requested:
                rows = [
                    row for row in rows
                    if str(row.get("orderId") or row.get("order_id") or row.get("order") or "") == requested
                ]
            return {"data": {"fill_orders": rows}}

        def fetch_order(self, order_id, symbol=None):
            calls.append(("fetch_order", order_id, symbol))
            if isinstance(exact_order, dict):
                return copy.deepcopy(exact_order)
            raise LookupError("order not found")

        def fetch_orders(self, symbol=None, since=None, limit=None):
            calls.append(("fetch_orders", symbol, since, limit))
            return copy.deepcopy(recent_orders or [])

        def fetch_closed_orders(self, symbol=None, since=None, limit=None):
            calls.append(("fetch_closed_orders", symbol, since, limit))
            return copy.deepcopy(recent_orders or [])

        def fetch_open_orders(self, symbol=None, since=None, limit=None):
            calls.append(("fetch_open_orders", symbol, since, limit))
            return copy.deepcopy(recent_orders or [])

        def fetch_my_trades(self, symbol=None, since=None, limit=None):
            calls.append(("fetch_my_trades", symbol, since, limit))
            return copy.deepcopy(trades or [])

        def fetch_positions(self, symbols=None):
            calls.append(("fetch_positions", copy.deepcopy(symbols)))
            if isinstance(position_result, dict) and position_result.get("ok") is False:
                raise RuntimeError("simulated position reader error")
            snapshot = copy.deepcopy(position_result or {
                "symbol": "SOLUSDT", "side": "LONG", "amount": 0.13,
            })
            if isinstance(snapshot, list):
                return snapshot
            if not isinstance(snapshot, dict):
                return []
            return [{
                "symbol": snapshot.get("symbol") or "SOLUSDT",
                "side": snapshot.get("side") or "LONG",
                "contracts": snapshot.get("amount", 0.13),
                "info": {
                    "positionSide": snapshot.get("side") or "LONG",
                    "positionAmt": snapshot.get("amount", 0.13),
                },
            }]

    read_only_exchange = ReadOnlyExchange()

    def fetch_recent_my_trades(symbol=None, since=None, limit=100):
        calls.append(("fetch_recent_my_trades", symbol, since, limit))
        return {"ok": True, "trades": copy.deepcopy(trades or [])}

    def managed_position_snapshot(symbol, side):
        calls.append(("managed_position_snapshot", symbol, side))
        return copy.deepcopy(position_result or {
            "ok": True, "status": "POSITION_MATCHED", "symbol": symbol, "side": side,
            "amount": 0.13, "position_closed": False, "ownership_safe": True,
            "matched_count": 1, "read_only": True, "sent": False,
        })

    namespace = {
        "datetime": datetime,
        "timezone": timezone,
        "FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1_VERSION": "TEST-BROKER-V1",
        "normalize_symbol": lambda value: str(value or "").upper(),
        "bingx_api_symbol": lambda value: (
            f"{str(value or '')[:-4]}-USDT"
            if str(value or "").upper().endswith("USDT") and "-" not in str(value or "")
            else str(value or "").replace("/", "-").replace(":USDT", "")
        ),
        "exchange": lambda: read_only_exchange,
        "_cq_patch_safe_float": lambda value, default=None: default if value in (None, "") else float(value),
        "fetch_order_by_id": fetch_order_by_id,
        "fetch_recent_orders": fetch_recent_orders,
        "fetch_recent_my_trades": fetch_recent_my_trades,
        "managed_position_snapshot": managed_position_snapshot,
    }
    _compile_functions(BROKER_SOURCE, BROKER_FUNCTIONS, namespace)
    namespace["_reader_calls"] = calls
    return namespace


def test_broker_normalizer_preserves_raw_failed_and_safe_terminal_fields():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "id": "STOP-1",
        "status": "canceled",
        "amount": 0.13,
        "filled": 0,
        "info": {
            "status": "FAILED",
            "planStatus": "TRIGGERED",
            "executeStatus": "FAILED",
            "errorCode": "109400",
            "failReason": "market execution rejected",
            "triggerPrice": "75.9305",
            "failTime": 1784478994000,
            "apiKey": "MUST_NOT_ESCAPE",
        },
    }, "test")
    assert normalized["status"] == "canceled"
    assert normalized["raw_status"] == "FAILED"
    assert normalized["plan_status"] == "TRIGGERED"
    assert normalized["execute_status"] == "FAILED"
    assert normalized["failure_code"] == "109400"
    assert normalized["failure_reason"] == "market execution rejected"
    assert normalized["requested_quantity"] == pytest.approx(0.13)
    assert normalized["executed_quantity"] == 0
    assert "MUST_NOT_ESCAPE" not in json.dumps(normalized)


@pytest.mark.parametrize(
    "sensitive_value",
    [
        "C:/private/history.jsonl",
        "/home/render/private.json",
        "/opt/service/private.json",
        "/var/data/private.json",
        "apiSecret=DO_NOT_EXPOSE",
        "secret: DO_NOT_EXPOSE",
        "token: DO_NOT_EXPOSE",
        "authorization=Bearer DO_NOT_EXPOSE",
    ],
)
def test_broker_safe_text_redacts_paths_and_secret_assignments(sensitive_value):
    namespace = _broker_namespace()
    projected = namespace["_dsff_v1_safe_text"](sensitive_value)
    assert projected == "REDACTED_SENSITIVE_VALUE"
    assert "DO_NOT_EXPOSE" not in str(projected)


def test_broker_normalizer_keeps_missing_fill_unknown_and_top_level_failed_raw():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "id": "STOP-1",
        "status": "FAILED",
        "amount": 0.13,
        "info": {"planStatus": "TRIGGERED"},
    }, "test")
    assert normalized["raw_status"] == "FAILED"
    assert normalized["executed_quantity"] is None
    assert normalized["remaining_quantity"] is None


def test_broker_normalizer_prioritizes_raw_executed_qty_over_conflicting_ccxt_filled():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "id": "STOP-1",
        "status": "canceled",
        "filled": 0,
        "info": {"status": "FAILED", "executedQty": "0.13", "avgPrice": "75.924"},
    }, "test")
    assert normalized["executed_quantity"] == pytest.approx(0.13)
    assert normalized["average_fill_price"] == pytest.approx(75.924)


def test_broker_trade_normalization_uses_order_id_and_amount_as_executed_fill():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "id": "TRADE-1",
        "order": "MARKET-1",
        "amount": 0.13,
        "price": 75.924,
        "info": {"status": "FILLED", "parentOrderId": "STOP-1"},
    }, "test.trade", record_kind="trade")
    assert normalized["order_id"] == "MARKET-1"
    assert normalized["requested_quantity"] is None
    assert normalized["executed_quantity"] == pytest.approx(0.13)


def test_broker_raw_fill_uses_volume_as_base_quantity_not_usdt_amount():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "orderId": "MANUAL-1",
        "volume": "0.13",
        "amount": "9.87",
        "price": "75.924",
        "filledTime": "2026-07-19T13:39:33-03:00",
    }, "test.raw_fill", record_kind="trade")
    assert normalized["executed_quantity"] == pytest.approx(0.13)
    assert normalized["average_fill_price"] == pytest.approx(75.924)
    assert normalized["updated_at"] == "2026-07-19T13:39:33-03:00"


def test_broker_normalizer_preserves_requested_plan_and_actual_order_id_separately():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "orderId": "CHILD-1",
        "planOrderId": "STOP-1",
        "volume": "0.13",
        "status": "FILLED",
    }, "test.raw_exact", requested_order_id="STOP-1")
    assert normalized["order_id"] == "CHILD-1"
    assert normalized["requested_order_id"] == "STOP-1"
    assert normalized["plan_order_id"] == "STOP-1"
    assert normalized["order_id"] != normalized["requested_order_id"]


def test_broker_normalizer_labels_base_quantity_source_and_unit_for_raw_fill():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "orderId": "STOP-1",
        "volume": "0.13",
        "amount": "9.87",
    }, "test.raw_fill", record_kind="trade")
    assert normalized["executed_quantity"] == pytest.approx(0.13)
    assert normalized["quantity_unit"] == "COIN"
    assert normalized["quantity_source"].endswith(".volume")


@pytest.mark.parametrize(
    ("identity_field", "expected_role"),
    [
        ("order_id", "STOP_ORDER"),
        ("requested_order_id", "REQUESTED_STOP_RESPONSE_ID_DIFFERENT"),
        ("plan_order_id", "DERIVED_ORDER"),
    ],
)
def test_broker_stop_relationship_accepts_each_explicit_plan_identity(identity_field, expected_role):
    namespace = _broker_namespace()
    record = {
        "order_id": "CHILD-1",
        "requested_order_id": None,
        "plan_order_id": None,
        "trigger_order_id": None,
    }
    record[identity_field] = "STOP-1"
    relation = namespace["_dsff_v1_related_to_stop"](record, "STOP-1")
    assert relation["related"] is True
    assert relation["conflict"] is False
    assert relation["matched_fields"] == [identity_field]
    assert relation["role"] == expected_role


def test_broker_stop_relationship_does_not_silently_choose_conflicting_identity():
    namespace = _broker_namespace()
    record = {
        "order_id": "UNRELATED-1",
        "requested_order_id": "OTHER-PLAN",
        "plan_order_id": "OTHER-PLAN",
        "trigger_order_id": "STOP-1",
    }
    relation = namespace["_dsff_v1_related_to_stop"](record, "STOP-1")
    assert isinstance(relation, dict)
    assert relation["related"] is True
    assert relation["conflict"] is True
    assert relation["matched_fields"] == ["trigger_order_id"]


def test_broker_requested_stop_response_with_different_order_id_has_explicit_role():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "orderId": "CHILD-1",
        "status": "FILLED",
    }, "test.raw_exact", requested_order_id="STOP-1")
    relation = namespace["_dsff_v1_related_to_stop"](normalized, "STOP-1")
    assert relation["related"] is True
    assert relation["conflict"] is False
    assert relation["role"] == "REQUESTED_STOP_RESPONSE_ID_DIFFERENT"
    assert normalized["order_id"] == "CHILD-1"
    assert normalized["requested_order_id"] == "STOP-1"
    assert normalized["plan_order_id"] is None


def test_broker_read_only_helper_finds_derived_order_and_never_calls_mutators():
    exact = {
        "id": "STOP-1", "status": "canceled", "amount": 0.13, "filled": 0,
        "info": {"status": "FAILED", "derivedOrderId": "MARKET-1"},
    }
    derived = {
        "id": "MARKET-1", "status": "closed", "amount": 0.13, "filled": 0.13,
        "info": {"status": "FILLED", "parentOrderId": "STOP-1"},
    }
    namespace = _broker_namespace(exact_order=exact, raw_orders=[derived])
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1", failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert result["read_only"] is True
    assert result["sent"] is False
    assert result["cancel_called"] is False
    assert result["close_called"] is False
    assert result["position_modified"] is False
    assert {row["order_id"] for row in result["stop_orders"]} == {"STOP-1"}
    assert {row["order_id"] for row in result["derived_orders"]} == {"MARKET-1"}
    assert not ({row["order_id"] for row in result["stop_orders"]} & {row["order_id"] for row in result["derived_orders"]})
    called_names = [call[0] for call in namespace["_reader_calls"]]
    assert "raw_get" in called_names
    assert set(called_names) <= {
        "fetch_order_by_id", "fetch_recent_orders", "raw_get", "fetch_recent_my_trades",
        "fetch_order", "fetch_orders", "fetch_closed_orders", "fetch_open_orders",
        "fetch_my_trades", "fetch_positions", "managed_position_snapshot",
    }


def test_broker_exact_raw_order_reader_uses_only_symbol_and_order_id_and_preserves_raw_status():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1",
            "symbol": "SOL-USDT",
            "status": "FAILED",
            "planStatus": "TRIGGERED",
            "executeStatus": "FAILED",
            "failureCode": "109400",
            "failureReason": "market execution rejected",
            "origQty": "0.13",
            "executedQty": "0",
        },
    })
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    exact_calls = [
        call for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeOrder")
    ]
    assert [call[2] for call in exact_calls] == [{"symbol": "SOL-USDT", "orderId": "STOP-1"}]
    stop = result["stop_orders"][0]
    assert stop["raw_status"] == "FAILED"
    assert stop["plan_status"] == "TRIGGERED"
    assert stop["execute_status"] == "FAILED"
    assert stop["failure_code"] == "109400"
    assert stop["failure_reason"] == "market execution rejected"
    assert stop["requested_quantity"] == pytest.approx(0.13)
    assert stop["executed_quantity"] == 0


def test_broker_exact_raw_order_reader_queries_each_known_identity_separately():
    raw_exact = {
        "STOP-1": {"orderId": "STOP-1", "status": "FAILED"},
        "ENTRY-1": {"orderId": "ENTRY-1", "status": "FILLED"},
        "MANUAL-1": {"orderId": "MANUAL-1", "status": "FILLED"},
    }
    namespace = _broker_namespace(raw_exact_orders=raw_exact)
    namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        entry_order_id="ENTRY-1",
        manual_close_order_id="MANUAL-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    exact_params = [
        call[2] for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeOrder")
    ]
    assert exact_params == [
        {"symbol": "SOL-USDT", "orderId": "STOP-1"},
        {"symbol": "SOL-USDT", "orderId": "ENTRY-1"},
        {"symbol": "SOL-USDT", "orderId": "MANUAL-1"},
    ]


def test_all_fill_orders_contract_is_exact_per_relevant_order_id_and_filters_unrelated_fills():
    namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {
                "orderId": "STOP-1", "status": "TRIGGERED", "derivedOrderId": "CHILD-1",
            },
        },
        raw_orders=[{
            "orderId": "CHILD-1", "parentOrderId": "STOP-1", "status": "FILLED",
        }],
        raw_fills=[
            {"orderId": "STOP-1", "volume": "0", "status": "FAILED"},
            {"orderId": "CHILD-1", "volume": "0.13", "status": "FILLED"},
            {"orderId": "UNRELATED-1", "volume": "999", "status": "FILLED"},
        ],
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    fill_params = [
        call[2] for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeAllFillOrders")
    ]
    assert fill_params
    for params in fill_params:
        assert set(params) == {"tradingUnit", "startTs", "endTs", "orderId"}
        assert params["tradingUnit"] == "COIN"
        assert params["startTs"] < params["endTs"]
        assert params["orderId"] in {"STOP-1", "CHILD-1"}
        assert "symbol" not in params
        assert "limit" not in params
    assert {params["orderId"] for params in fill_params} == {"STOP-1", "CHILD-1"}
    projected_ids = {
        row.get("order_id")
        for collection in ("stop_orders", "derived_orders", "entry_orders", "manual_close_orders")
        for row in result[collection]
    }
    assert "UNRELATED-1" not in projected_ids


def test_all_fill_orders_never_omits_required_window_when_operator_timestamp_is_absent():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1", "status": "FAILED",
            "updateTime": "2026-07-19T13:36:34-03:00",
        },
    })
    namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
    )
    fill_params = [
        call[2] for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeAllFillOrders")
    ]
    assert fill_params
    assert all(params.get("startTs") is not None for params in fill_params)
    assert all(params.get("endTs") is not None for params in fill_params)
    assert all(params.get("tradingUnit") == "COIN" for params in fill_params)
    assert all(params.get("orderId") == "STOP-1" for params in fill_params)


def test_all_orders_contract_is_bounded_and_called_only_once():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {"orderId": "STOP-1", "status": "FAILED"},
    })
    namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
        limit=200,
    )
    all_orders_params = [
        call[2] for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeAllOrders")
    ]
    assert len(all_orders_params) == 1
    assert set(all_orders_params[0]) == {"symbol", "limit", "startTime", "endTime"}
    assert all_orders_params[0]["symbol"] == "SOL-USDT"
    assert all_orders_params[0]["limit"] == 200
    assert all_orders_params[0]["endTime"] - all_orders_params[0]["startTime"] == 172_800_000


def test_broker_reader_exposes_call_metrics_and_ccxt_rate_limit_pacing_state():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {"orderId": "STOP-1", "status": "FAILED"},
    })
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert isinstance(result["reader_calls_attempted"], list)
    assert isinstance(result["reader_calls_completed"], list)
    assert isinstance(result["reader_calls_skipped_as_redundant"], list)
    assert result["reader_calls_attempted_count"] == len(result["reader_calls_attempted"])
    assert result["reader_calls_completed_count"] == len(result["reader_calls_completed"])
    assert result["reader_calls_skipped_as_redundant_count"] == len(result["reader_calls_skipped_as_redundant"])
    assert result["reader_calls_attempted_count"] >= result["reader_calls_completed_count"] >= 1
    assert result["rate_limit_pacing_applied"] is True


def test_identity_conflict_never_drives_derived_order_or_fill_queries_end_to_end():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "CONFLICT-CHILD",
            "planOrderId": "OTHER-PLAN",
            "derivedOrderId": "UNTRUSTED-DERIVED",
            "status": "TRIGGERED",
        },
    })
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert result["identity_conflicts"]
    assert result["derived_orders"] == []
    queried_exact_ids = {
        call[2].get("orderId")
        for call in namespace["_reader_calls"]
        if call[0] == "raw_get" and call[1] in {
            "swapV2PrivateGetTradeOrder", "swap_v2_private_get_trade_order",
        }
    }
    queried_fill_ids = {
        call[2].get("orderId")
        for call in namespace["_reader_calls"]
        if call[0] == "raw_get" and "AllFillOrders" in call[1]
    }
    assert "UNTRUSTED-DERIVED" not in queried_exact_ids
    assert "CONFLICT-CHILD" not in queried_fill_ids
    assert "UNTRUSTED-DERIVED" not in queried_fill_ids


def test_plan_only_child_remains_derived_and_disjoint_from_stop_plan_rows():
    namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {"orderId": "STOP-1", "status": "TRIGGERED"},
            "CHILD-1": {"orderId": "CHILD-1", "planOrderId": "STOP-1", "status": "FILLED"},
        },
        raw_orders=[{
            "orderId": "CHILD-1",
            "planOrderId": "STOP-1",
            "status": "FILLED",
        }],
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    stop_ids = {row["order_id"] for row in result["stop_orders"]}
    plan_ids = {row["order_id"] for row in result["plan_orders"]}
    derived_ids = {row["order_id"] for row in result["derived_orders"]}
    assert stop_ids == plan_ids == {"STOP-1"}
    assert derived_ids == {"CHILD-1"}
    assert stop_ids.isdisjoint(derived_ids)


@pytest.mark.parametrize(
    ("aliases", "failing_method"),
    [
        (["swapV2PrivateGetTradeOrder", "swap_v2_private_get_trade_order"], "swapV2PrivateGetTradeOrder"),
        (["swapV2PrivateGetTradeAllOrders", "swap_v2_private_get_trade_all_orders"], "swapV2PrivateGetTradeAllOrders"),
        (["swapV2PrivateGetTradeAllFillOrders", "swap_v2_private_get_trade_all_fill_orders"], "swapV2PrivateGetTradeAllFillOrders"),
    ],
)
def test_first_callable_raw_alias_failure_never_attempts_a_second_alias(aliases, failing_method):
    namespace = _broker_namespace(raw_fail_methods={failing_method})
    rows, attempts = namespace["_dsff_v1_call_raw"](aliases, {"orderId": "STOP-1"})
    physical = [call[1] for call in namespace["_reader_calls"] if call[0] == "raw_get"]
    assert rows == []
    assert physical == [failing_method]
    assert len(attempts) == 1
    assert attempts[0]["method"] == failing_method
    assert attempts[0]["ok"] is False


def test_sufficient_raw_all_orders_skips_recent_orders_fallback():
    namespace = _broker_namespace(
        raw_exact_orders={"STOP-1": {"orderId": "STOP-1", "status": "FAILED"}},
        raw_orders=[{"orderId": "STOP-1", "status": "FAILED"}],
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert "fetch_recent_orders:raw_all_orders_sufficient" in result["reader_calls_skipped_as_redundant"]
    assert not any(call[0] in {"fetch_orders", "fetch_closed_orders", "fetch_open_orders"} for call in namespace["_reader_calls"])
    assert not any(call[0] == "fetch_order" for call in namespace["_reader_calls"])


def test_reader_telemetry_matches_the_number_of_physical_reader_invocations():
    namespace = _broker_namespace(
        raw_exact_orders={"STOP-1": {"orderId": "STOP-1", "status": "FAILED"}},
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    physical_calls = [
        call for call in namespace["_reader_calls"]
        if call[0] in {
            "raw_get", "fetch_order_by_id", "fetch_recent_orders",
            "fetch_recent_my_trades", "managed_position_snapshot", "fetch_order",
            "fetch_orders", "fetch_closed_orders", "fetch_open_orders", "fetch_my_trades",
            "fetch_positions",
        }
    ]
    assert result["reader_calls_attempted_count"] == len(physical_calls)
    assert len(result["reader_calls_attempted"]) == len(physical_calls)
    assert result["reader_calls_completed_count"] == len(physical_calls)
    assert len(result["reader_calls_completed"]) == len(physical_calls)


def test_broker_helper_correlates_trigger_order_id_child_and_reports_position_reader_error():
    exact = {
        "id": "STOP-1", "status": "canceled", "amount": 0.13,
        "info": {"status": "FAILED", "triggerOrderId": "MARKET-2"},
    }
    child = {"id": "MARKET-2", "status": "closed", "filled": 0.13, "info": {"status": "FILLED"}}
    namespace = _broker_namespace(
        exact_order=exact,
        raw_orders=[child],
        position_result={"ok": False, "status": "POSITION_SNAPSHOT_ERROR", "read_only": True, "sent": False},
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert {row["order_id"] for row in result["derived_orders"]} == {"MARKET-2"}
    assert result["status"] == "READ_ONLY_LOOKUP_PARTIAL"
    assert {error["source"] for error in result["reader_errors"]} == {
        "ccxt_fetch_positions:fetch_positions",
    }


def test_broker_helper_keeps_manual_close_fill_separate_and_bounds_incident_window():
    namespace = _broker_namespace(
        exact_order={"id": "STOP-1", "status": "canceled", "amount": 0.13, "filled": 0, "info": {"status": "FAILED"}},
        raw_fills=[{
            "orderId": "MANUAL-1", "volume": "0.13", "amount": "9.87",
            "price": "75.924", "filledTime": "2026-07-19T13:39:33-03:00",
        }],
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT",
        side="LONG",
        stop_order_id="STOP-1",
        manual_close_order_id="MANUAL-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert result["manual_close_orders"][0]["order_id"] == "MANUAL-1"
    assert result["manual_close_orders"][0]["executed_quantity"] == pytest.approx(0.13)
    assert all(row["order_id"] != "MANUAL-1" for row in result["stop_orders"])
    raw_calls = [call for call in namespace["_reader_calls"] if call[0] == "raw_get"]
    order_params = next(call[2] for call in raw_calls if call[1] == "swapV2PrivateGetTradeAllOrders")
    fill_params = next(
        call[2]
        for call in raw_calls
        if call[1] == "swapV2PrivateGetTradeAllFillOrders" and call[2].get("orderId") == "MANUAL-1"
    )
    assert order_params["endTime"] - order_params["startTime"] == 172_800_000
    assert fill_params["endTs"] - fill_params["startTs"] == 172_800_000
    assert result["position"]["ownership_safe"] is False
    assert result["position"]["ownership_basis"] == "SYMBOL_SIDE_EXPOSURE_ONLY"


def test_broker_forensics_source_contains_no_mutating_call_sites():
    source = BROKER_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "disaster_stop_failure_forensics_read_only")
    called = set()
    for node in ast.walk(helper):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    assert called.isdisjoint({
        "create_order", "cancel_order", "edit_order", "close_position", "close_position_market",
        "managed_close_position_market", "cancel_managed_stop_order", "replace_position_stop_order",
    })


def test_broker_raw_private_aliases_are_explicit_get_readers_only():
    source = BROKER_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "disaster_stop_failure_forensics_read_only"
    )
    aliases = {
        node.value
        for node in ast.walk(helper)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "Private" in node.value
        and "Trade" in node.value
    }
    assert aliases
    assert all("Get" in alias for alias in aliases)
    assert all("Post" not in alias and "Delete" not in alias for alias in aliases)


def test_broker_forensics_reader_contains_no_explicit_sleep_loop():
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    helper = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "disaster_stop_failure_forensics_read_only"
    )
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "time"
        and node.func.attr == "sleep"
        for node in ast.walk(helper)
    )


def test_route_and_builder_contain_no_write_management_or_reconciliation_calls():
    source = MAIN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("_fdsff_v1_")]
    selected.append(next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "falcon_disaster_stop_failure_forensics_v1_text_route"))
    called = set()
    for function in selected:
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    called.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
    assert called.isdisjoint({
        "create_order", "cancel_order", "close_position", "managed_close_position_market",
        "save_registry", "update_trade", "close_trade", "record_event", "append_timeline_event",
        "falcon_verify_live_disaster_stop", "falcon_handle_live_stop_cross", "reconcile_trade",
    })


def test_route_is_registered_as_get_only_at_the_expected_path():
    tree = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))
    route = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "falcon_disaster_stop_failure_forensics_v1_text_route"
    )
    decorators = [ast.unparse(item) for item in route.decorator_list]
    assert decorators == [
        "app.route('/falcon/disasterstop/failure/diagnostic/text', methods=['GET'])"
    ]


# ---------------------------------------------------------------------------
# REVIEW 3: identity parity, ambiguous evidence and exact-fill aggregation.
# ---------------------------------------------------------------------------

def _review3_stop_plan():
    return {
        "source": "bingx.swap_v2.trade.order.stop",
        "record_kind": "order",
        "order_id": "STOP-1",
        "requested_order_id": "STOP-1",
        "plan_status": "TRIGGERED",
        "derived_order_id": "CHILD-1",
        "requested_quantity": 0.13,
        "requested_quantity_unit": "COIN",
        "executed_quantity": 0.0,
        "executed_quantity_unit": "COIN",
        "stop_identity_role": "STOP_ORDER",
    }


def _review3_fill(fill_id, quantity, *, source="bingx.swap_v2.trade.all_fill_orders", unit="COIN", timestamp=None):
    return {
        "source": source,
        "record_kind": "trade",
        "order_id": "CHILD-1",
        "requested_order_id": "CHILD-1",
        "plan_order_id": "STOP-1",
        "raw_status": "FILLED",
        "fill_id": fill_id,
        "fill_time": timestamp or f"2026-07-19T13:36:{34 + len(str(fill_id)):02d}-03:00",
        "fill_quantity": quantity,
        "fill_quantity_unit": unit,
        "fill_price": 75.90,
        "fill_fee": 0.001,
        "executed_quantity": quantity,
        "executed_quantity_unit": unit,
        "stop_identity_role": "DERIVED_ORDER",
    }


def test_review3_legitimate_child_requested_by_own_id_is_not_identity_conflict():
    namespace, _, _ = _main_namespace()
    child = {
        "source": "bingx.swap_v2.trade.order.derived",
        "record_kind": "order",
        "order_id": "CHILD-1",
        "requested_order_id": "CHILD-1",
        "plan_order_id": "STOP-1",
        "raw_status": "FILLED",
        "executed_quantity": 0.13,
        "executed_quantity_unit": "COIN",
        "stop_identity_role": "DERIVED_ORDER",
    }
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[child])
    assert result["stop_identity_conflict"] is False
    assert result["derived_order_found"] is True
    assert result["stop_filled"] is True
    assert result["executed_quantity"] == pytest.approx(0.13)
    assert {"STOP_DERIVED_ORDER_FOUND", "STOP_FILLED"}.issubset(result["classifications"])
    assert {
        "STOP_DERIVED_ORDER_NOT_FOUND", "STOP_TRIGGERED_ZERO_FILL",
        "STOP_IDENTITY_CONFLICT", "STOP_PLAN_ORDER_IDENTITY_CONFLICT",
    }.isdisjoint(result["classifications"])


def test_review3_legitimate_child_passes_broker_projection_classifier_and_text():
    broker_namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {
                "orderId": "STOP-1", "planStatus": "TRIGGERED", "triggerOrderId": "CHILD-1",
                "origQty": "0.13", "executedQty": "0",
            },
            "CHILD-1": {
                "orderId": "CHILD-1", "planOrderId": "STOP-1", "status": "FILLED",
                "origQty": "0.13", "executedQty": "0.13",
            },
        },
        raw_fills=[{
            "orderId": "CHILD-1", "tradeId": "T1", "volume": "0.13",
            "price": "75.90", "commission": "0.001", "tradeTime": 1784464593000,
            "status": "FILLED", "symbol": "SOL-USDT",
        }],
        raw_orders=[],
        position_result={"symbol": "SOLUSDT", "side": "LONG", "amount": 0.0},
    )
    raw = broker_namespace["disaster_stop_failure_forensics_read_only"](
        "SOLUSDT", side="LONG", stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    namespace, _, _ = _main_namespace()
    safe = namespace["_fdsff_v1_safe_live_lookup"](raw)
    findings = namespace["_fdsff_v1_classify"](
        [], safe, {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"},
    )
    rendered = namespace["_fdsff_v1_text"]({"findings": findings, "live_lookup": safe})
    assert findings["stop_identity_conflict"] is False
    assert findings["derived_order_found"] is True
    assert findings["stop_filled"] is True
    assert findings["executed_quantity"] == pytest.approx(0.13)
    assert findings["executed_quantity_aggregation_source"] == "SUM_UNIQUE_EXACT_FILLS"
    assert "STOP_FILLED" in rendered
    assert "stop_identity_conflict=False" in rendered


def test_review3_ambiguous_exact_response_survives_public_projection_without_terminal_claim():
    broker_namespace = _broker_namespace(
        raw_exact_orders={"STOP-1": {"orderId": "CHILD-1", "status": "FILLED", "executedQty": "0.13"}},
        raw_orders=[], raw_fills=[], position_result={"symbol": "SOLUSDT", "side": "LONG", "amount": 0.0},
    )
    raw = broker_namespace["disaster_stop_failure_forensics_read_only"](
        "SOLUSDT", stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert raw["stop_orders"] == []
    assert raw["derived_orders"] == []
    assert len(raw["identity_ambiguous"]) == 1
    namespace, _, _ = _main_namespace()
    safe = namespace["_fdsff_v1_safe_live_lookup"](raw)
    assert len(safe["identity_ambiguous"]) == 1
    findings = namespace["_fdsff_v1_classify"](
        [], safe, {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"},
    )
    assert findings["stop_identity_ambiguous"] is True
    assert findings["identity_ambiguous_count"] == 1
    assert "STOP_IDENTITY_AMBIGUOUS" in findings["classifications"]
    assert findings["stop_created"] is False
    assert findings["stop_triggered"] is False
    assert findings["stop_filled"] is False
    assert findings["derived_order_found"] is False
    assert findings["terminal_status_known"] is False
    assert findings["executed_quantity"] is None


def test_review3_broker_normalizer_preserves_distinct_order_and_fill_identity():
    namespace = _broker_namespace()
    normalized = namespace["_dsff_v1_normalize_order"]({
        "orderId": "CHILD-1", "tradeId": "T1", "id": "CCXT-T1",
        "volume": "0.07", "price": "75.90", "commission": "0.001",
        "tradeTime": 1784464593000,
    }, "bingx.swap_v2.trade.all_fill_orders", record_kind="trade")
    assert normalized["order_id"] == "CHILD-1"
    assert normalized["fill_id"] == "T1"
    assert normalized["fill_quantity"] == pytest.approx(0.07)
    assert normalized["fill_quantity_unit"] == "COIN"
    assert normalized["fill_price"] == pytest.approx(75.90)
    assert normalized["fill_fee"] == pytest.approx(0.001)
    assert normalized["fill_time"] == 1784464593000


def test_review3_two_unique_fills_are_summed_to_requested_quantity():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[_review3_stop_plan()],
        derived=[_review3_fill("T1", 0.07), _review3_fill("T2", 0.06)],
    )
    assert result["fill_count"] == 2
    assert result["fill_ids"] == ["T1", "T2"]
    assert result["executed_quantity"] == pytest.approx(0.13)
    assert result["executed_quantity_unit"] == "COIN"
    assert result["executed_quantity_aggregation_source"] == "SUM_UNIQUE_EXACT_FILLS"
    assert result["quantity_mismatch"] is False
    assert result["stop_filled"] is True


def test_review3_duplicate_fill_id_across_sources_is_counted_once():
    namespace, _, _ = _main_namespace()
    raw = _review3_fill("T1", 0.07)
    duplicate = _review3_fill("T1", 0.07, source="bingx.fetch_my_trades")
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[raw, duplicate])
    assert result["fill_count"] == 1
    assert result["fill_ids"] == ["T1"]
    assert result["executed_quantity"] == pytest.approx(0.07)
    assert result["stop_filled"] is False


def test_review3_fill_without_id_uses_conservative_composite_key_for_deduplication():
    namespace, _, _ = _main_namespace()
    first = _review3_fill("", 0.07, source="bingx.swap_v2.trade.all_fill_orders")
    duplicate = _review3_fill("", 0.07, source="bingx.fetch_my_trades")
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[first, duplicate])
    assert result["fill_count"] == 1
    assert result["fill_ids"] == []
    assert result["executed_quantity"] == pytest.approx(0.07)


def test_review3_fill_without_stable_identity_is_not_summed_silently():
    namespace, _, _ = _main_namespace()
    keyless = _review3_fill("", 0.13)
    keyless.pop("fill_time")
    keyless.pop("fill_price")
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[keyless])
    assert result["fill_count"] == 0
    assert result["fill_keyless_count"] == 1
    assert result["fill_aggregation_inconclusive"] is True
    assert result["executed_quantity"] is None
    assert result["stop_filled"] is False


def test_review3_cumulative_snapshot_is_not_added_to_exact_fills():
    namespace, _, _ = _main_namespace()
    child_snapshot = {
        "record_kind": "order", "order_id": "CHILD-1", "requested_order_id": "CHILD-1",
        "plan_order_id": "STOP-1", "executed_quantity": 0.13,
        "executed_quantity_unit": "COIN", "status": "FILLED",
    }
    result = _classify(
        namespace,
        stop=[_review3_stop_plan()],
        derived=[child_snapshot, _review3_fill("T1", 0.07), _review3_fill("T2", 0.06)],
    )
    assert result["executed_quantity"] == pytest.approx(0.13)
    assert result["executed_quantity_aggregation_source"] == "SUM_UNIQUE_EXACT_FILLS"
    assert result["fill_count"] == 2


def test_review3_single_trade_filled_status_does_not_prove_whole_order_fill():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace, stop=[_review3_stop_plan()], derived=[_review3_fill("T1", 0.07)],
    )
    assert result["executed_quantity"] == pytest.approx(0.07)
    assert result["quantity_mismatch"] is True
    assert result["stop_filled"] is False
    assert "STOP_FILLED" not in result["classifications"]


def test_review3_incompatible_fill_units_are_not_summed_or_promoted_to_full_fill():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[_review3_stop_plan()],
        derived=[_review3_fill("T1", 0.07, unit="COIN"), _review3_fill("T2", 0.06, unit="CONT")],
    )
    assert result["executed_quantity"] is None
    assert result["quantity_unit_conflict"] is True
    assert result["fill_aggregation_inconclusive"] is True
    assert result["stop_filled"] is False


def test_review3_manual_close_fills_are_summed_and_completion_uses_last_required_fill():
    namespace, _, _ = _main_namespace()
    manual_fills = [
        {
            **_review3_fill("M1", 0.07, timestamp="2026-07-19T13:38:00-03:00"),
            "order_id": "MANUAL-1", "requested_order_id": "MANUAL-1", "plan_order_id": None,
        },
        {
            **_review3_fill("M2", 0.06, timestamp="2026-07-19T13:39:33-03:00"),
            "order_id": "MANUAL-1", "requested_order_id": "MANUAL-1", "plan_order_id": None,
        },
    ]
    live = _empty_live(
        stop_orders=[{**_review3_stop_plan(), "raw_status": "FAILED"}],
        manual_close_orders=manual_fills,
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "manual_close_order_id": "MANUAL-1",
        "manual_close_quantity": "0.13", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["manual_close_executed_quantity"] == pytest.approx(0.13)
    assert result["manual_close_executed_quantity_source"] == "SUM_UNIQUE_EXACT_FILLS"
    assert result["manual_close_fill_count"] == 2
    assert result["manual_close_fill_ids"] == ["M1", "M2"]
    assert result["manual_close_first_fill_timestamp"] == "2026-07-19T13:38:00-03:00"
    assert result["manual_close_last_fill_timestamp"] == "2026-07-19T13:39:33-03:00"
    assert result["manual_close_completion_fill_timestamp"] is None
    assert result["bingx_manual_close_timestamp"] is None


def test_review3_partial_manual_fill_does_not_invent_completed_close_timestamp():
    namespace, _, _ = _main_namespace()
    partial = {
        **_review3_fill("M1", 0.07, timestamp="2026-07-19T13:38:00-03:00"),
        "order_id": "MANUAL-1", "requested_order_id": "MANUAL-1", "plan_order_id": None,
    }
    result = namespace["_fdsff_v1_classify"]([], _empty_live(
        stop_orders=[{**_review3_stop_plan(), "raw_status": "FAILED"}],
        manual_close_orders=[partial],
    ), {
        "stop_order_id": "STOP-1", "manual_close_order_id": "MANUAL-1",
        "manual_close_quantity": "0.13", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["manual_close_executed_quantity"] == pytest.approx(0.07)
    assert result["manual_close_completion_fill_timestamp"] is None
    assert result["bingx_manual_close_timestamp"] is None


def test_review3_reader_counters_contracts_filters_and_ambiguous_survive_projection_and_text():
    namespace, _, _ = _main_namespace()
    safe = namespace["_fdsff_v1_safe_live_lookup"](_empty_live(
        reader_calls_attempted=["exact", "fills"],
        reader_calls_completed=["exact"],
        reader_calls_skipped_as_redundant=["fallback"],
        reader_calls_attempted_count=2,
        reader_calls_completed_count=1,
        reader_calls_skipped_as_redundant_count=1,
        all_orders_params_contract=["symbol", "limit", "startTime", "endTime"],
        all_fill_orders_params_contract=["tradingUnit", "startTs", "endTs", "orderId"],
        all_fill_orders_trading_unit="COIN",
        identity_filters=[{"source": "raw", "reason": "ORDER_ID_MISMATCH_FILTERED", "secret": "never"}],
        identity_ambiguous=[{
            "source": "raw", "order_id": "CHILD-1", "requested_order_id": "STOP-1",
            "stop_identity_role": "REQUESTED_STOP_RESPONSE_ID_DIFFERENT",
        }],
    ))
    rendered = namespace["_fdsff_v1_text"]({"live_lookup": safe, "findings": {}})
    assert safe["reader_calls_attempted_count"] == 2
    assert safe["reader_calls_completed_count"] == 1
    assert safe["reader_calls_skipped_as_redundant_count"] == 1
    assert safe["identity_filters"] == [{"source": "raw", "reason": "ORDER_ID_MISMATCH_FILTERED"}]
    assert len(safe["identity_ambiguous"]) == 1
    assert safe["all_fill_orders_trading_unit"] == "COIN"
    assert "live_reader_calls_attempted_count=2" in rendered
    assert "live_reader_calls_completed_count=1" in rendered
    assert "live_reader_calls_skipped_as_redundant_count=1" in rendered
    assert "secret" not in rendered


# ---------------------------------------------------------------------------
# REVIEW 4: semantic status channels, conservative absence and private cache.
# ---------------------------------------------------------------------------

def test_review4_plan_filled_with_zero_quantity_does_not_prove_execution():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "plan_status": "FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.0, "executed_quantity_unit": "COIN",
    }])
    assert result["stop_filled"] is False
    assert result["order_statuses"] == []
    assert result["plan_statuses"] == ["FILLED"]
    assert "STOP_FILLED" not in result["classifications"]
    assert "STOP_FILLED_QUANTITY_CONFLICT" not in result["classifications"]


def test_review4_order_filled_with_zero_quantity_is_explicit_conflict():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "status": "FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.0, "executed_quantity_unit": "COIN",
    }])
    assert result["stop_filled"] is False
    assert result["terminal_evidence_conflict"] is True
    assert result["stop_fill_evidence_status"] == "STOP_FILLED_STATUS_ZERO_QUANTITY_CONFLICT"
    assert "STOP_FILLED_QUANTITY_CONFLICT" in result["classifications"]
    assert "STOP_FILLED" not in result["classifications"]


def test_review4_order_filled_with_partial_quantity_is_explicit_conflict():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "raw_status": "FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.07, "executed_quantity_unit": "COIN",
    }])
    assert result["stop_filled"] is False
    assert result["quantity_mismatch"] is True
    assert result["terminal_evidence_conflict"] is True
    assert result["stop_fill_evidence_status"] == "STOP_FILLED_STATUS_PARTIAL_QUANTITY_CONFLICT"
    assert "STOP_FILLED_QUANTITY_CONFLICT" in result["classifications"]


def test_review4_execute_filled_on_plan_without_child_is_not_executor_evidence():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "execute_status": "FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.0, "executed_quantity_unit": "COIN",
    }])
    assert result["execute_statuses"] == []
    assert result["stop_filled"] is False
    assert "STOP_FILLED" not in result["classifications"]


def test_review4_order_filled_without_quantity_preserves_status_without_inventing_quantity():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "status": "FILLED",
    }])
    assert result["terminal_status"] == "FILLED"
    assert result["executed_quantity"] is None
    assert result["quantity_confirmation_available"] is False
    assert result["stop_filled"] is True
    assert result["stop_fill_evidence_status"] == "STOP_FILLED_BY_ORDER_STATUS_QUANTITY_UNAVAILABLE"
    assert "STOP_FILLED_BY_ORDER_STATUS_QUANTITY_UNAVAILABLE" in result["classifications"]


def test_review4_exact_complete_fills_override_zero_plan_snapshot():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace,
        stop=[{**_review3_stop_plan(), "status": "FILLED"}],
        derived=[_review3_fill("T1", 0.07), _review3_fill("T2", 0.06)],
    )
    assert result["executed_quantity"] == pytest.approx(0.13)
    assert result["executed_quantity_aggregation_source"] == "SUM_UNIQUE_EXACT_FILLS"
    assert result["stop_filled"] is True
    assert result["terminal_evidence_conflict"] is False
    assert "STOP_FILLED_QUANTITY_CONFLICT" not in result["classifications"]


def test_review4_individual_filled_trade_does_not_prove_full_order():
    namespace, _, _ = _main_namespace()
    result = _classify(
        namespace, stop=[_review3_stop_plan()], derived=[_review3_fill("T1", 0.07)],
    )
    assert result["order_statuses"] == []
    assert result["stop_filled"] is False
    assert result["executed_quantity"] == pytest.approx(0.07)


def test_review4_failed_and_filled_statuses_remain_terminal_conflict():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "status": "FILLED",
        "failure_status": "FAILED",
    }])
    assert result["failure_statuses"] == ["FAILED"]
    assert result["terminal_evidence_conflict"] is True
    assert "STOP_TERMINAL_EVIDENCE_CONFLICT" in result["classifications"]
    assert "STOP_FILLED" not in result["classifications"]


def test_review4_triggered_missing_child_is_inconclusive_when_live_reader_is_partial():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        status="READ_ONLY_LOOKUP_PARTIAL",
        reader_errors=[{"source": "allOrders", "error_type": "RuntimeError"}],
        local_negative_evidence_complete=False,
        stop_orders=[{"record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED"}],
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["derived_order_found"] is None
    assert "STOP_DERIVED_ORDER_EVIDENCE_INCONCLUSIVE" in result["classifications"]
    assert "STOP_DERIVED_ORDER_NOT_FOUND" not in result["classifications"]


def test_review4_triggered_missing_child_can_be_negative_when_live_readers_are_complete():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED",
    }])
    assert result["derived_order_found"] is False
    assert "STOP_DERIVED_ORDER_NOT_FOUND" in result["classifications"]


def test_review4_positive_child_survives_an_unrelated_reader_failure():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        status="READ_ONLY_LOOKUP_PARTIAL",
        reader_errors=[{"source": "allFillOrders", "error_type": "RuntimeError"}],
        stop_orders=[{"record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED"}],
        derived_orders=[{
            "record_kind": "order", "order_id": "CHILD-1", "plan_order_id": "STOP-1",
            "status": "OPEN",
        }],
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["derived_order_found"] is True
    assert "STOP_DERIVED_ORDER_FOUND" in result["classifications"]


def test_review4_negative_fields_are_none_when_required_sources_are_incomplete():
    namespace, _, _ = _main_namespace()
    result = namespace["_fdsff_v1_classify"]([], _empty_live(
        status="READ_ONLY_LOOKUP_PARTIAL",
        reader_errors=[{"source": "allOrders", "error_type": "RuntimeError"}],
        local_negative_evidence_complete=False,
    ), {
        "stop_order_id": "STOP-1", "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["manual_close_order_found"] is None
    assert result["failsafe_blocked_by_ownership"] is None
    assert result["critical_condition_found"] is None
    assert result["critical_alert_state_found"] is None


def test_review4_final_source_completeness_downgrades_earlier_negative_claims():
    namespace, _, _ = _main_namespace(live_result=_empty_live(stop_orders=[{
        "record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED",
    }]))
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        [], ["history.events:READ_ERROR:OSError"], 4,
    )
    payload = _build(
        namespace,
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    findings = payload["findings"]
    assert payload["status"] == "FORENSICS_PARTIAL_SOURCE_ERRORS"
    assert findings["absence_claims_supported"] is False
    assert findings["derived_order_found"] is False
    assert findings["manual_close_order_found"] is False
    assert findings["failsafe_blocked_by_ownership"] is None
    assert findings["critical_condition_found"] is None
    assert findings["critical_alert_state_found"] is None
    assert "STOP_DERIVED_ORDER_NOT_FOUND" in findings["classifications"]


def test_review4_manual_close_derived_conflict_survives_broker_projection_classifier_and_text():
    broker_namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {
                "orderId": "STOP-1", "planStatus": "TRIGGERED",
                "origQty": "0.13", "executedQty": "0",
            },
            "MANUAL-1": {
                "orderId": "MANUAL-1", "planOrderId": "STOP-1", "status": "FILLED",
                "origQty": "0.13", "executedQty": "0.13",
            },
        },
        raw_orders=[], raw_fills=[],
        position_result={"symbol": "SOLUSDT", "side": "LONG", "amount": 0.0},
    )
    raw = broker_namespace["disaster_stop_failure_forensics_read_only"](
        "SOLUSDT", side="LONG", stop_order_id="STOP-1",
        manual_close_order_id="MANUAL-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert raw["identity_conflicts"]
    assert "manual_close_order_id" in raw["identity_conflicts"][0]["stop_identity_conflicting_fields"]

    namespace, _, _ = _main_namespace()
    safe = namespace["_fdsff_v1_safe_live_lookup"](raw)
    findings = namespace["_fdsff_v1_classify"]([], safe, {
        "stop_order_id": "STOP-1", "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT", "side": "LONG",
    })
    rendered = namespace["_fdsff_v1_text"]({"findings": findings, "live_lookup": safe})
    assert findings["manual_close_order_linked_as_derived_conflict"] is True
    assert "MANUAL_CLOSE_DERIVED_IDENTITY_CONFLICT" in findings["classifications"]
    assert "STOP_IDENTITY_CONFLICT" in findings["classifications"]
    assert "STOP_PLAN_ORDER_IDENTITY_CONFLICT" not in findings["classifications"]
    assert findings["executed_quantity"] == pytest.approx(0.0)
    assert findings["stop_filled"] is False
    assert "stop_identity_conflicting_fields=['manual_close_order_id']" in rendered


@pytest.mark.parametrize(
    "conflicting_fields,expected,unexpected",
    [
        (["plan_order_id"], "STOP_PLAN_ORDER_IDENTITY_CONFLICT", "STOP_REQUESTED_ORDER_IDENTITY_CONFLICT"),
        (["requested_order_id"], "STOP_REQUESTED_ORDER_IDENTITY_CONFLICT", "STOP_PLAN_ORDER_IDENTITY_CONFLICT"),
    ],
)
def test_review4_identity_conflict_classifications_are_field_specific(
    conflicting_fields, expected, unexpected,
):
    namespace, _, _ = _main_namespace()
    live = _empty_live(identity_conflicts=[{
        "record_kind": "order", "order_id": "STOP-1",
        "stop_identity_conflict": True, "stop_identity_role": "IDENTITY_CONFLICT",
        "stop_identity_conflicting_fields": conflicting_fields,
    }])
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert "STOP_IDENTITY_CONFLICT" in result["classifications"]
    assert expected in result["classifications"]
    assert unexpected not in result["classifications"]
    assert result["identity_conflicts"][0]["stop_identity_conflicting_fields"] == conflicting_fields


def test_review4_multiple_identity_conflict_types_are_all_preserved():
    namespace, _, _ = _main_namespace()
    live = _empty_live(identity_conflicts=[{
        "record_kind": "order", "order_id": "MANUAL-1", "plan_order_id": "STOP-1",
        "stop_identity_conflict": True, "stop_identity_role": "IDENTITY_CONFLICT",
        "stop_identity_conflicting_fields": [
            "plan_order_id", "requested_order_id", "manual_close_order_id",
        ],
    }])
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "manual_close_order_id": "MANUAL-1",
        "symbol": "SOLUSDT", "side": "LONG",
    })
    assert {
        "STOP_IDENTITY_CONFLICT", "STOP_PLAN_ORDER_IDENTITY_CONFLICT",
        "STOP_REQUESTED_ORDER_IDENTITY_CONFLICT", "MANUAL_CLOSE_DERIVED_IDENTITY_CONFLICT",
    }.issubset(result["classifications"])


def _assert_review4_no_store_headers(response):
    assert response.headers["Content-Type"].startswith("text/plain")
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    serialized = json.dumps(dict(response.headers), ensure_ascii=False).lower()
    assert "secret" not in serialized
    assert "token" not in serialized
    assert "credential" not in serialized


def _review4_route(namespace):
    app = Flask(__name__)
    app.add_url_rule(
        "/falcon/disasterstop/failure/diagnostic/text",
        view_func=namespace["falcon_disaster_stop_failure_forensics_v1_text_route"],
        methods=["GET"],
    )
    return app.test_client()


def test_review4_no_store_headers_are_present_on_200():
    namespace, _, _ = _main_namespace()
    response = _review4_route(namespace).get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1"
    )
    assert response.status_code == 200
    _assert_review4_no_store_headers(response)


def test_review4_no_store_headers_are_present_on_403():
    namespace, _, _ = _main_namespace()
    namespace["_fdsff_v1_admin_auth"] = lambda: {
        "available": True, "authenticated": False, "status": "ADMIN_AUTH_REQUIRED",
    }
    response = _review4_route(namespace).get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1"
    )
    assert response.status_code == 403
    _assert_review4_no_store_headers(response)


def test_review4_no_store_headers_are_present_on_503():
    namespace, _, _ = _main_namespace()
    namespace["_fdsff_v1_admin_auth"] = lambda: {
        "available": False, "authenticated": False, "status": "ADMIN_AUTH_GUARD_UNAVAILABLE",
    }
    response = _review4_route(namespace).get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1"
    )
    assert response.status_code == 503
    _assert_review4_no_store_headers(response)


def test_review4_no_store_headers_are_present_on_500():
    namespace, _, _ = _main_namespace()
    namespace["_fdsff_v1_build_payload"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("internal")
    )
    response = _review4_route(namespace).get(
        "/falcon/disasterstop/failure/diagnostic/text?stop_order_id=STOP-1"
    )
    assert response.status_code == 500
    _assert_review4_no_store_headers(response)


# ---------------------------------------------------------------------------
# Review 5 - strict units, global fill identity, bounded-source completeness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requested_unit", "executed_unit"),
    [(None, None), (None, "COIN"), ("COIN", None)],
)
def test_review5_numeric_quantity_requires_known_equal_units(requested_unit, executed_unit):
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "raw_status": "FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": requested_unit,
        "executed_quantity": 0.13, "executed_quantity_unit": executed_unit,
    }])
    assert result["quantity_confirmation_available"] is False
    assert result["quantity_mismatch"] is None
    assert result["quantity_units_compatible"] is False
    assert result["quantity_unit_inconclusive"] is True
    assert result["stop_fill_evidence_status"] == "STOP_FILL_QUANTITY_UNIT_INCONCLUSIVE"
    assert result["stop_filled"] is False
    assert "STOP_FILLED" not in result["classifications"]
    assert "STOP_FILLED_QUANTITY_CONFLICT" not in result["classifications"]


def test_review5_incompatible_known_units_are_inconclusive_not_partial_fill():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "status": "PARTIALLY_FILLED",
        "requested_quantity": 0.13, "requested_quantity_unit": "COIN",
        "executed_quantity": 0.05, "executed_quantity_unit": "CONT",
    }])
    assert result["quantity_unit_conflict"] is True
    assert result["quantity_mismatch"] is None
    assert result["stop_fill_evidence_status"] == "STOP_FILL_QUANTITY_UNIT_INCONCLUSIVE"
    assert "STOP_FILLED_QUANTITY_CONFLICT" not in result["classifications"]


def test_review5_filled_status_with_numeric_unknown_unit_preserves_status_only():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "raw_status": "FILLED",
        "requested_quantity": 0.13, "executed_quantity": 0.13,
    }])
    assert "FILLED" in result["order_statuses"]
    assert result["stop_filled"] is False
    assert result["stop_fill_evidence_status"] == "STOP_FILL_QUANTITY_UNIT_INCONCLUSIVE"


def test_review5_factual_filled_order_without_any_quantity_keeps_status_fallback():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "raw_status": "FILLED",
    }])
    assert result["stop_filled"] is True
    assert result["quantity_confirmation_available"] is False
    assert result["stop_fill_evidence_status"] == "STOP_FILLED_BY_ORDER_STATUS_QUANTITY_UNAVAILABLE"


def test_review5_numeric_zero_without_units_does_not_confirm_zero_fill():
    namespace, _, _ = _main_namespace()
    result = _classify(namespace, stop=[{
        "record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED",
        "requested_quantity": 0.13, "executed_quantity": 0.0,
    }])
    assert result["stop_fill_evidence_status"] == "STOP_FILL_QUANTITY_UNIT_INCONCLUSIVE"
    assert "STOP_TRIGGERED_ZERO_FILL" not in result["classifications"]


def test_review5_same_fill_id_across_order_ids_is_counted_once_and_conflicted():
    namespace, _, _ = _main_namespace()
    first = _review3_fill("T1", 0.13)
    second = {
        **first,
        "order_id": "OTHER-CHILD",
        "requested_order_id": "OTHER-CHILD",
        "parent_order_id": "STOP-1",
    }
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[first, second])
    assert result["fill_count"] == 1
    assert result["fill_observed_quantity_once"] == pytest.approx(0.13)
    assert result["fill_order_identity_conflict"] is True
    assert result["stop_filled"] is False
    assert "FILL_ORDER_IDENTITY_CONFLICT" in result["classifications"]
    assert result["fill_order_observations"][0]["observed_order_ids"] == ["CHILD-1", "OTHER-CHILD"]


def test_review5_duplicate_fill_payload_conflict_is_inconclusive():
    namespace, _, _ = _main_namespace()
    first = _review3_fill("T1", 0.07, source="source.a")
    second = _review3_fill("T1", 0.06, source="source.b")
    result = _classify(namespace, stop=[_review3_stop_plan()], derived=[first, second])
    assert result["fill_count"] == 1
    assert result["fill_duplicate_payload_conflict"] is True
    assert result["fill_aggregation_inconclusive"] is True
    assert result["stop_filled"] is False
    assert "FILL_DUPLICATE_PAYLOAD_CONFLICT" in result["classifications"]


@pytest.mark.parametrize(
    ("returned", "limit", "saturated"),
    [(199, 200, False), (200, 200, True), (1000, 1000, True)],
)
def test_review5_all_orders_saturation_contract(returned, limit, saturated):
    rows = [
        {"orderId": f"UNRELATED-{index}", "status": "FILLED"}
        for index in range(returned)
    ]
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1", "status": "FAILED",
            "updateTime": "2026-07-19T13:36:34-03:00",
        },
    }, raw_orders=rows)
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1", limit=limit,
    )
    assert result["all_orders_requested_limit"] == limit
    assert result["all_orders_returned_count"] == returned
    assert result["all_orders_saturated"] is saturated
    if saturated:
        assert result["status"] == "READ_ONLY_LOOKUP_PARTIAL"
        assert "ALL_ORDERS_RESULT_SATURATED" in {
            item["error_type"] for item in result["reader_errors"]
        }


def test_review5_positive_child_survives_saturated_all_orders():
    rows = [{"orderId": "CHILD-1", "parentOrderId": "STOP-1", "status": "FILLED"}]
    rows.extend(
        {"orderId": f"UNRELATED-{index}", "status": "FILLED"}
        for index in range(999)
    )
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1", "status": "TRIGGERED", "derivedOrderId": "CHILD-1",
            "updateTime": "2026-07-19T13:36:34-03:00",
        },
    }, raw_orders=rows)
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
    )
    assert result["all_orders_saturated"] is True
    assert {item["order_id"] for item in result["derived_orders"]} == {"CHILD-1"}


def test_review5_absent_child_in_saturated_results_is_inconclusive():
    namespace, _, _ = _main_namespace()
    live = _empty_live(
        status="READ_ONLY_LOOKUP_PARTIAL",
        history_window_complete=True,
        all_orders_requested_limit=1000,
        all_orders_returned_count=1000,
        all_orders_saturated=True,
        stop_orders=[{"record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED"}],
    )
    result = namespace["_fdsff_v1_classify"]([], live, {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["derived_order_found"] is None
    assert "STOP_DERIVED_ORDER_NOT_FOUND" not in result["classifications"]


def test_review5_nonzero_raw_response_code_is_a_safe_reader_error():
    namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {
                "orderId": "STOP-1", "status": "FAILED",
                "updateTime": "2026-07-19T13:36:34-03:00",
            },
        },
        raw_all_orders_response={"code": 100421, "msg": "private payload must not leak", "data": {}},
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
    )
    errors = [item for item in result["reader_errors"] if item["error_type"] == "RAW_RESPONSE_CODE_NON_ZERO"]
    assert errors and errors[0]["response_code"] == "100421"
    assert result["status"] == "READ_ONLY_LOOKUP_PARTIAL"
    assert "private payload must not leak" not in json.dumps(result)


def test_review5_raw_pagination_marker_makes_all_orders_incomplete():
    namespace = _broker_namespace(
        raw_exact_orders={
            "STOP-1": {
                "orderId": "STOP-1", "status": "TRIGGERED",
                "updateTime": "2026-07-19T13:36:34-03:00",
            },
        },
        raw_all_orders_response={
            "code": 0,
            "data": {
                "orders": [{"orderId": "CHILD-1", "parentOrderId": "STOP-1", "status": "FILLED"}],
                "hasMore": True,
                "nextPageCursor": "opaque-not-exposed",
            },
        },
    )
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
    )
    assert result["all_orders_pagination_incomplete"] is True
    assert result["status"] == "READ_ONLY_LOOKUP_PARTIAL"
    assert "opaque-not-exposed" not in json.dumps(result)
    assert {item["order_id"] for item in result["derived_orders"]} == {"CHILD-1"}


def _review5_local_sources(namespace, broker, tmp_path, rows_by_source):
    paths = {
        "history.events": tmp_path / "history.jsonl",
        "broker.execution_audit": tmp_path / "audit.jsonl",
        "broker.executions": tmp_path / "executions.jsonl",
        "falcon.live_audit": tmp_path / "falcon.jsonl",
        "central.timeline": tmp_path / "timeline.jsonl",
    }
    namespace["super_history_manager"] = type(
        "HistoryProbe", (), {"HISTORY_EVENTS_FILE": paths["history.events"]}
    )()
    broker.EXECUTION_AUDIT_LOG_FILE = paths["broker.execution_audit"]
    broker.EXECUTIONS_LOG_FILE = paths["broker.executions"]
    namespace["FALCON_LIVE_AUDIT_EVENTS_FILE"] = paths["falcon.live_audit"]
    namespace["CENTRAL_TIMELINE_LOG_FILE"] = paths["central.timeline"]
    for source, path in paths.items():
        rows = rows_by_source.get(source, [])
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows),
            encoding="utf-8",
        )
    return paths


def _review5_coverage_rows(event="DIAGNOSTIC_HEARTBEAT"):
    return [
        {"event": event, "stop_order_id": "STOP-1", "created_at": "2026-07-19T13:35:00-03:00"},
        {"event": event, "stop_order_id": "STOP-1", "created_at": "2026-07-19T13:41:00-03:00"},
    ]


def _review5_read_local(namespace, query=None):
    return namespace["_fdsff_v1_read_local_events_real"](query or {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
        "failure_timestamp": "2026-07-19T13:36:34-03:00",
        "manual_close_timestamp": "2026-07-19T13:39:33-03:00",
    })


def test_review5_exactly_300_local_rows_marks_source_saturated(tmp_path):
    namespace, broker, _ = _main_namespace()
    rows_by_source = {source: _review5_coverage_rows() for source in (
        "history.events", "broker.execution_audit", "broker.executions",
        "falcon.live_audit", "central.timeline",
    )}
    rows_by_source["history.events"] = [
        {"event": "DIAGNOSTIC_HEARTBEAT", "stop_order_id": "STOP-1", "created_at": f"2026-07-19T13:{index % 60:02d}:00-03:00"}
        for index in range(300)
    ]
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    _rows, _errors, _checked, metadata = _review5_read_local(namespace)
    history = next(item for item in metadata if item["source"] == "history.events")
    assert history["rows_read"] == 300
    assert history["saturated"] is True


def test_review5_event_outside_saturated_tail_cannot_produce_not_found_claim(tmp_path):
    namespace, broker, _ = _main_namespace()
    # The omitted older row represents the event outside the bounded tail.  A
    # saturated result must remain inconclusive rather than assert NOT_FOUND.
    saturated = [
        {"event": "DIAGNOSTIC_HEARTBEAT", "stop_order_id": "STOP-1", "created_at": "2026-07-19T13:37:00-03:00"}
        for _ in range(300)
    ]
    rows_by_source = {source: _review5_coverage_rows() for source in (
        "history.events", "broker.execution_audit", "broker.executions",
        "falcon.live_audit", "central.timeline",
    )}
    rows_by_source["history.events"] = saturated
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    matches, _errors, _checked, metadata = _review5_read_local(namespace)
    complete = all(
        not item["saturated"] and not item["read_error"] and item["incident_window_covered"]
        for item in metadata
    )
    result = namespace["_fdsff_v1_classify"](matches, _empty_live(
        local_negative_evidence_complete=complete,
    ), {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"})
    assert complete is False
    assert result["failsafe_close_attempt_found"] is None
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" not in result["classifications"]


@pytest.mark.parametrize(
    "timestamps",
    [
        ("2026-07-19T13:37:00-03:00", "2026-07-19T13:41:00-03:00"),
        ("2026-07-19T13:35:00-03:00", "2026-07-19T13:38:00-03:00"),
    ],
)
def test_review5_local_tail_must_cover_both_ends_of_incident_window(tmp_path, timestamps):
    namespace, broker, _ = _main_namespace()
    rows = [
        {"event": "DIAGNOSTIC_HEARTBEAT", "stop_order_id": "STOP-1", "created_at": value}
        for value in timestamps
    ]
    _review5_local_sources(namespace, broker, tmp_path, {
        source: copy.deepcopy(rows) for source in (
            "history.events", "broker.execution_audit", "broker.executions",
            "falcon.live_audit", "central.timeline",
        )
    })
    _matches, _errors, _checked, metadata = _review5_read_local(namespace)
    assert all(item["incident_window_covered"] is False for item in metadata)


def test_review5_round_robin_prevents_later_alert_source_starvation(tmp_path):
    namespace, broker, _ = _main_namespace()
    noisy = [
        {"event": "DIAGNOSTIC_HEARTBEAT", "stop_order_id": "STOP-1", "created_at": "2026-07-19T13:37:00-03:00"}
        for _ in range(300)
    ]
    alert = {
        "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT", "stop_order_id": "STOP-1",
        "critical_alert_attempted": True, "critical_alert_transport_called": True,
        "created_at": "2026-07-19T13:37:30-03:00",
    }
    rows_by_source = {source: _review5_coverage_rows() for source in (
        "history.events", "broker.execution_audit", "broker.executions",
        "falcon.live_audit", "central.timeline",
    )}
    rows_by_source["history.events"] = noisy
    rows_by_source["central.timeline"] = [*_review5_coverage_rows(), alert]
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    matches, _errors, _checked, _metadata = _review5_read_local(namespace)
    result = namespace["_fdsff_v1_classify"](matches, _empty_live(
        local_negative_evidence_complete=False,
    ), {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"})
    assert result["critical_alert_attempt_found"] is True
    assert result["critical_alert_transport_called"] is True


def test_review5_complete_local_window_alone_allows_local_negative_claims(tmp_path):
    namespace, broker, _ = _main_namespace()
    rows_by_source = {source: _review5_coverage_rows() for source in (
        "history.events", "broker.execution_audit", "broker.executions",
        "falcon.live_audit", "central.timeline",
    )}
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    matches, errors, _checked, metadata = _review5_read_local(namespace)
    complete = bool(not errors and all(
        not item["saturated"] and not item["read_error"] and item["incident_window_covered"]
        for item in metadata
    ))
    result = namespace["_fdsff_v1_classify"](matches, _empty_live(
        local_negative_evidence_complete=complete,
    ), {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"})
    assert complete is True
    assert result["failsafe_close_attempt_found"] is False
    assert result["critical_alert_attempt_found"] is None
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" in result["classifications"]


def test_review5_positive_failsafe_survives_saturated_local_source(tmp_path):
    namespace, broker, _ = _main_namespace()
    positive = {
        "event": "STOP_FAILSAFE", "stop_order_id": "STOP-1", "failsafe_attempted": True,
        "created_at": "2026-07-19T13:37:00-03:00",
    }
    saturated = [positive] + [
        {"event": "DIAGNOSTIC_HEARTBEAT", "stop_order_id": "STOP-1", "created_at": "2026-07-19T13:37:00-03:00"}
        for _ in range(299)
    ]
    rows_by_source = {source: _review5_coverage_rows() for source in (
        "history.events", "broker.execution_audit", "broker.executions",
        "falcon.live_audit", "central.timeline",
    )}
    rows_by_source["history.events"] = saturated
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    matches, _errors, _checked, metadata = _review5_read_local(namespace)
    result = namespace["_fdsff_v1_classify"](matches, _empty_live(
        local_negative_evidence_complete=False,
    ), {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"})
    assert any(item["saturated"] for item in metadata)
    assert result["failsafe_close_attempt_found"] is True
    assert "FAILSAFE_CLOSE_ATTEMPT_FOUND" in result["classifications"]


def test_review5_factual_stop_anchor_precedes_operator_timestamp_and_reports_conflict():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1", "status": "FAILED",
            "failedTime": "2026-07-18T10:00:00-03:00",
        },
    })
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    assert result["history_window_basis"] == "FACTUAL_STOP_ORDER_TIMESTAMP"
    assert result["factual_anchor_timestamp"] == "2026-07-18T10:00:00-03:00"
    assert result["reported_anchor_timestamp"] == "2026-07-19T13:36:34-03:00"
    assert result["history_window_anchor_conflict"] is True
    all_orders_call = next(
        call for call in namespace["_reader_calls"]
        if call[:2] == ("raw_get", "swapV2PrivateGetTradeAllOrders")
    )
    assert all_orders_call[2]["startTime"] < all_orders_call[2]["endTime"]


def test_review5_exact_old_stop_without_operator_timestamp_builds_factual_window():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {
            "orderId": "STOP-1", "status": "FAILED", "updateTime": 1700000000000,
        },
    })
    result = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
    )
    assert result["history_window_complete"] is True
    assert result["history_window_basis"] == "FACTUAL_STOP_ORDER_TIMESTAMP"
    assert result["factual_anchor_timestamp"] == 1700000000000


def test_review5_missing_anchor_skips_all_window_readers_and_absence_is_inconclusive():
    namespace = _broker_namespace(raw_exact_orders={
        "STOP-1": {"orderId": "STOP-1", "status": "TRIGGERED"},
    })
    raw = namespace["disaster_stop_failure_forensics_read_only"](
        symbol="SOLUSDT", side="LONG", stop_order_id="STOP-1",
    )
    assert raw["history_window_complete"] is False
    assert not any(call[:2] == ("raw_get", "swapV2PrivateGetTradeAllOrders") for call in namespace["_reader_calls"])
    assert not any(call[:2] == ("raw_get", "swapV2PrivateGetTradeAllFillOrders") for call in namespace["_reader_calls"])
    main_namespace, _, _ = _main_namespace()
    safe = main_namespace["_fdsff_v1_safe_live_lookup"](raw)
    result = main_namespace["_fdsff_v1_classify"]([], safe, {
        "stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG",
    })
    assert result["derived_order_found"] is None
    assert "STOP_DERIVED_ORDER_NOT_FOUND" not in result["classifications"]


def test_review5_payload_exposes_local_completeness_and_saturation_classification():
    live = _empty_live(
        status="READ_ONLY_LOOKUP_PARTIAL",
        history_window_complete=True,
        all_orders_requested_limit=1000,
        all_orders_returned_count=1000,
        all_orders_saturated=True,
        reader_errors=[{
            "source": "bounded_raw_all_orders",
            "error_type": "ALL_ORDERS_RESULT_SATURATED",
        }],
        stop_orders=[{"record_kind": "order", "order_id": "STOP-1", "plan_status": "TRIGGERED"}],
    )
    namespace, _, _ = _main_namespace(live_result=live)
    payload = _build(
        namespace,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
        live_lookup="true",
        ack="FALCON_DISASTER_STOP_FAILURE_FORENSICS_V1",
    )
    findings = payload["findings"]
    assert len(payload["local_source_metadata"]) == 5
    assert findings["local_source_completeness"] == "COMPLETE_INCIDENT_WINDOW"
    assert findings["local_negative_evidence_complete"] is True
    assert "ALL_ORDERS_RESULT_SATURATED" in findings["classifications"]
    assert findings["derived_order_found"] is None


# ============================================================================
# REVISION 6 — operational fail-safe correlation and evidence completeness
# ============================================================================


def _review6_incident_query():
    return {
        "stop_order_id": "2078846241538150400",
        "entry_order_id": "ENTRY-SOL",
        "manual_close_order_id": "2078882445537792000",
        "lifecycle_id": "LC-SOL",
        "client_order_id": "FALCON-LIVE-SOL",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "failure_timestamp": "2026-07-19T13:36:34-03:00",
        "manual_close_timestamp": "2026-07-19T13:39:33-03:00",
        "manual_close_quantity": 0.13,
    }


def _review6_real_failsafe(**updates):
    row = {
        "event": "BROKER_MANAGED_CLOSE_ERROR",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "amount": 0.13,
        "expected_position_amount": 0.13,
        "reason": "STOP_BROKER_NOT_CONFIRMED",
        "sent": False,
        "confirmed": False,
        "status": "MANAGED_CLOSE_ERROR",
        "ts": "19/07/2026 13:38",
        "error": "simulated",
    }
    row.update(updates)
    return row


def test_review6_real_broker_failsafe_without_strong_ids_is_correlated_end_to_end(tmp_path):
    namespace, broker, _ = _main_namespace()
    rows_by_source = {
        source: _review5_coverage_rows()
        for source in (
            "history.events", "broker.execution_audit", "broker.executions",
            "falcon.live_audit", "central.timeline",
        )
    }
    rows_by_source["broker.execution_audit"] = [
        _review5_coverage_rows()[0],
        _review6_real_failsafe(),
        _review5_coverage_rows()[1],
    ]
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    matches, errors, _checked, metadata = _review5_read_local(
        namespace, _review6_incident_query()
    )
    complete = bool(not errors and all(
        not item["saturated"] and not item["read_error"] and item["incident_window_covered"]
        for item in metadata
    ))
    operational = next(
        row for row in matches
        if row.get("operational_correlation_role") == "FAILSAFE_CLOSE_AUDIT"
    )
    result = namespace["_fdsff_v1_classify"](
        matches,
        _empty_live(local_negative_evidence_complete=complete),
        _review6_incident_query(),
    )
    assert operational["failsafe_reason"] == "STOP_BROKER_NOT_CONFIRMED"
    assert operational["failsafe_amount"] == pytest.approx(0.13)
    assert "stop_order_id" not in operational
    assert result["failsafe_close_attempt_found"] is True
    assert result["failsafe_executed"] is None
    assert result["failsafe_attempt_before_manual_close_found"] is True
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" not in result["classifications"]


@pytest.mark.parametrize(
    ("confirmed", "expected"),
    [(True, True), (False, None), (None, None)],
)
def test_review6_failsafe_sent_execution_is_tristate(confirmed, expected):
    namespace, _, _ = _main_namespace()
    raw = _review6_real_failsafe(
        event="BROKER_MANAGED_CLOSE_SENT",
        status=(
            "MANAGED_CLOSE_CONFIRMED"
            if confirmed is True
            else "MANAGED_CLOSE_SENT_UNCONFIRMED"
        ),
        sent=True,
        confirmed=confirmed,
        order_id="FAILSAFE-MARKET-1",
    )
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        raw, "broker.executions", _review6_incident_query()
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(local_negative_evidence_complete=False),
        _review6_incident_query(),
    )
    assert result["failsafe_close_attempt_found"] is True
    assert result["failsafe_executed"] is expected
    assert result["failsafe_order_sent"] is True
    assert result["failsafe_execution_confirmed"] is (True if confirmed is True else False)
    assert projected["failsafe_close_order_id"] == "FAILSAFE-MARKET-1"
    assert "stop_order_id" not in projected


@pytest.mark.parametrize(
    "updates",
    [
        {"reason": "TP50_REAL_PARTIAL"},
        {"reason": "MANAGED_CLOSE"},
        {"event": "BROKER_UNRELATED_EVENT"},
        {"ts": "19/07/2026 13:50"},
        {"symbol": "XRPUSDT"},
        {"side": "SHORT"},
    ],
)
def test_review6_unrelated_managed_close_evidence_is_excluded(updates):
    namespace, _, _ = _main_namespace()
    assert namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(**updates),
        "broker.execution_audit",
        _review6_incident_query(),
    ) is None


@pytest.mark.parametrize(
    ("updates", "conflict"),
    [
        ({"ts": None}, "INCIDENT_WINDOW_OR_FACTUAL_TIMESTAMP_MISSING"),
        ({"expected_position_amount": 0.25}, "INCIDENT_QUANTITY_MISMATCH"),
    ],
)
def test_review6_incomplete_operational_correlation_remains_candidate(updates, conflict):
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(**updates),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert projected["operational_correlation_conflict"] == conflict
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(local_negative_evidence_complete=False),
        _review6_incident_query(),
    )
    assert result["failsafe_close_attempt_found"] is None
    assert result["failsafe_candidate_evidence"]


def test_review6_failsafe_market_order_does_not_contaminate_stop_orders_or_fills():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(
            event="BROKER_MANAGED_CLOSE_SENT", confirmed=True,
            sent=True, order_id="FAILSAFE-MARKET-1", status="MANAGED_CLOSE_SENT",
        ),
        "broker.executions",
        _review6_incident_query(),
    )
    live = _empty_live(stop_orders=[{
        "order_id": "2078846241538150400", "status": "FAILED",
        "requested_quantity": 0.13, "executed_quantity": 0.0,
    }])
    result = namespace["_fdsff_v1_classify"](
        [projected], live, _review6_incident_query()
    )
    assert result["requested_quantity"] == pytest.approx(0.13)
    assert result["executed_quantity"] == pytest.approx(0.0)
    assert result["fill_count"] == 0
    assert result["derived_order_found"] is False
    assert result["manual_close_order_found"] is False
    assert result["failsafe_evidence"][0]["failsafe_close_order_id"] == "FAILSAFE-MARKET-1"


def _review6_noisy_local_records():
    return [
        {
            "source": "history.events", "event": "DIAGNOSTIC_HEARTBEAT",
            "stop_order_id": "STOP-1", "created_at": f"2026-07-19T13:37:{index % 60:02d}-03:00",
            "diagnostic_reason": f"row-{index}",
        }
        for index in range(300)
    ]


def test_review6_external_round_robin_keeps_health_alert_visible_to_classifier():
    namespace, _, _ = _main_namespace(local_records=_review6_noisy_local_records())
    namespace["_fdsff_v1_read_falcon_health"] = lambda _query: ([{
        "source": "falcon.health", "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT",
        "stop_order_id": "STOP-1", "critical_alert_attempted": True,
        "critical_alert_transport_called": True,
    }], None)
    payload = _build(namespace)
    assert payload["findings"]["critical_alert_attempt_found"] is True
    assert payload["local_records_category_counts"]["after"]["falcon_health"] == 1
    assert len(payload["local_records"]) == 300


def test_review6_external_round_robin_keeps_snapshot_stop_visible_to_classifier():
    namespace, _, _ = _main_namespace(local_records=_review6_noisy_local_records())
    namespace["_fdsff_v1_read_snapshot_records"] = lambda *_args: ([{
        "source": "falcon.liveorder.snapshot", "event": "DISASTER_STOP_FAILED",
        "order_id": "STOP-1", "stop_order_id": "STOP-1", "status": "FAILED",
    }], None)
    payload = _build(namespace)
    assert payload["findings"]["terminal_status_known"] is True
    assert payload["local_records_category_counts"]["after"]["liveorder_snapshot"] == 1


def test_review6_external_round_robin_keeps_registry_identity_visible_to_classifier():
    namespace, _, _ = _main_namespace(local_records=_review6_noisy_local_records())
    namespace["_fdsff_v1_read_registry"] = lambda _query: ([{
        "source": "trade_registry.closed_trades", "event": "STOP_FAILSAFE",
        "stop_order_id": "STOP-1", "lifecycle_id": "LC-1", "failsafe_attempted": True,
    }], None)
    payload = _build(namespace)
    assert payload["findings"]["failsafe_close_attempt_found"] is True
    assert payload["local_records_category_counts"]["after"]["registry"] == 1


def test_review6_public_projection_is_bounded_safe_and_order_independent():
    noisy = _review6_noisy_local_records()
    first, _, _ = _main_namespace(local_records=noisy)
    second, _, _ = _main_namespace(local_records=list(reversed(noisy)))
    alert = [{
        "source": "falcon.health", "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT",
        "stop_order_id": "STOP-1", "critical_alert_attempted": True,
        "critical_alert_transport_called": True,
    }]
    first["_fdsff_v1_read_falcon_health"] = lambda _query: (copy.deepcopy(alert), None)
    second["_fdsff_v1_read_falcon_health"] = lambda _query: (copy.deepcopy(alert), None)
    payload_a = _build(first)
    payload_b = _build(second)
    text = first["_fdsff_v1_text"](payload_a)
    assert len(payload_a["local_records"]) == 300
    assert payload_a["local_records_truncated"] is True
    assert payload_a["findings"]["critical_alert_attempt_found"] is True
    assert payload_b["findings"]["critical_alert_attempt_found"] is True
    assert "C:\\" not in text and "api_key" not in text.lower() and "secret=" not in text.lower()


def test_review6_generic_complete_logs_do_not_prove_critical_alert_transport_absence():
    namespace, _, _ = _main_namespace()
    payload = _build(
        namespace,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    findings = payload["findings"]
    assert findings["local_negative_evidence_complete"] is True
    assert findings["critical_alert_negative_evidence_complete"] is False
    assert findings["critical_alert_attempt_found"] is None
    assert findings["critical_alert_transport_called"] is None
    assert findings["critical_alert_delivery_confirmed"] is None
    assert "CRITICAL_ALERT_NOT_FOUND" not in findings["classifications"]
    assert "CRITICAL_ALERT_EVIDENCE_INCONCLUSIVE" in findings["classifications"]


def test_review6_proven_complete_transport_source_allows_negative_conclusion():
    namespace, _, _ = _main_namespace()
    metadata = [{
        "source": "test.telegram_transport_ledger",
        "rows_read": 0,
        "configured_limit": 300,
        "saturated": False,
        "incident_window_covered": True,
        "critical_alert_transport_audit_complete": True,
        "read_error": None,
    }]
    namespace["_fdsff_v1_read_local_events"] = lambda _query: ([], [], 1, copy.deepcopy(metadata))
    payload = _build(
        namespace,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    findings = payload["findings"]
    assert findings["critical_alert_negative_evidence_complete"] is True
    assert findings["critical_alert_attempt_found"] is False
    assert findings["critical_alert_transport_called"] is False
    assert findings["critical_alert_delivery_confirmed"] is False
    assert "CRITICAL_ALERT_NOT_FOUND" in findings["classifications"]


def test_review6_incomplete_transport_source_does_not_hide_positive_delivery():
    namespace, _, _ = _main_namespace()
    result = namespace["_fdsff_v1_classify"]([{
        "event": "FALCON_CRITICAL_ALERT_TRANSPORT_ATTEMPT",
        "stop_order_id": "STOP-1",
        "telegram_sent": True,
    }], _empty_live(
        critical_alert_negative_evidence_complete=False,
    ), {"stop_order_id": "STOP-1", "symbol": "SOLUSDT", "side": "LONG"})
    assert result["critical_alert_attempt_found"] is True
    assert result["critical_alert_transport_called"] is True
    assert result["critical_alert_delivery_confirmed"] is True


def test_review6_text_separates_general_and_alert_transport_completeness():
    namespace, _, _ = _main_namespace()
    payload = _build(
        namespace,
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp="2026-07-19T13:39:33-03:00",
    )
    text = namespace["_fdsff_v1_text"](payload)
    assert "local_negative_evidence_complete=True" in text
    assert "critical_alert_negative_evidence_complete=False" in text
    assert "critical_alert_negative_evidence_basis=NO_COMPLETE_TELEGRAM_TRANSPORT_LEDGER_PROVEN" in text


# ============================================================================
# REVISION 7 — final fail-safe evidence semantics
# ============================================================================


def test_review7_candidate_prevents_not_found_even_with_complete_local_evidence():
    namespace, _, _ = _main_namespace()
    candidate = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(amount=0.25, expected_position_amount=0.25),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    result = namespace["_fdsff_v1_classify"](
        [candidate],
        _empty_live(local_negative_evidence_complete=True),
        _review6_incident_query(),
    )
    assert candidate["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert candidate["operational_correlation_conflict"] == "INCIDENT_QUANTITY_MISMATCH"
    assert result["failsafe_candidate_evidence"]
    assert result["failsafe_close_attempt_found"] is None
    assert result["failsafe_executed"] is None
    assert result["failsafe_attempt_before_manual_close_found"] is None
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" not in result["classifications"]
    assert "FAILSAFE_EVIDENCE_CONFLICT_OR_CANDIDATE" in result["classifications"]


@pytest.mark.parametrize(
    "reason",
    ["MANAGED_CLOSE", "TP50_REAL_PARTIAL", "TP50_STOP_RESIZE_FAILED", None],
)
def test_review7_generic_managed_close_name_with_exact_lifecycle_is_not_failsafe(reason):
    namespace, _, _ = _main_namespace()
    row = {
        "event": "BROKER_MANAGED_CLOSE_SENT",
        "status": "MANAGED_CLOSE_CONFIRMED",
        "lifecycle_id": "LC-1",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "sent": True,
        "confirmed": True,
    }
    if reason is not None:
        row["reason"] = reason
    result = _classify(namespace, local=[row], lifecycle_id="LC-1")
    assert result["failsafe_close_attempt_found"] is False
    assert "FAILSAFE_CLOSE_ATTEMPT_FOUND" not in result["classifications"]


def test_review7_specialized_role_remains_positive_but_candidate_never_is():
    namespace, _, _ = _main_namespace()
    positive = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    candidate = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(ts=None),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    positive_result = namespace["_fdsff_v1_classify"](
        [positive], _empty_live(), _review6_incident_query()
    )
    candidate_result = namespace["_fdsff_v1_classify"](
        [candidate], _empty_live(), _review6_incident_query()
    )
    assert positive["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert positive_result["failsafe_close_attempt_found"] is True
    assert candidate_result["failsafe_close_attempt_found"] is None


def test_review7_managed_close_error_is_inconclusive_without_pre_transport_phase():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(status="MANAGED_CLOSE_ERROR"),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_close_attempt_found"] is True
    assert result["failsafe_order_sent"] is None
    assert result["failsafe_execution_confirmed"] is None
    assert result["failsafe_executed"] is None
    assert "FAILSAFE_ERROR_SEND_AND_EXECUTION_INCONCLUSIVE" in result["classifications"]


def test_review7_sent_unconfirmed_preserves_fill_evidence_without_proving_execution():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(
            event="BROKER_MANAGED_CLOSE_SENT",
            status="MANAGED_CLOSE_SENT_UNCONFIRMED",
            sent=True,
            confirmed=False,
            order_id="FAILSAFE-MARKET-1",
            filled_amount=0.13,
            remaining_amount=0.13,
        ),
        "broker.executions",
        _review6_incident_query(),
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_order_sent"] is True
    assert result["failsafe_execution_confirmed"] is False
    assert result["failsafe_executed"] is None
    assert result["failsafe_filled_amount"] == pytest.approx(0.13)
    assert result["failsafe_remaining_amount"] == pytest.approx(0.13)
    assert result["fill_count"] == 0
    evidence = result["failsafe_evidence"][0]
    assert evidence["failsafe_filled_amount"] == pytest.approx(0.13)
    assert evidence["failsafe_remaining_amount"] == pytest.approx(0.13)


def test_review7_reported_incident_quantity_matches_positive_correlation():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(amount=0.13, expected_position_amount=0.13),
        "broker.execution_audit",
        _review6_incident_query(),
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["operational_correlation_quantity_basis"] == "USER_REPORTED_MANUAL_CLOSE_QUANTITY"
    assert projected["incident_reported_quantity"] == pytest.approx(0.13)


def test_review7_absent_incident_quantity_uses_internal_event_basis_only():
    namespace, _, _ = _main_namespace()
    query = _review6_incident_query()
    query.pop("manual_close_quantity")
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(amount=0.13, expected_position_amount=0.13),
        "broker.execution_audit",
        query,
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["operational_correlation_quantity_basis"] == "EVENT_INTERNAL_AMOUNT_EXPECTED_MATCH_ONLY"
    assert "incident_reported_quantity" not in projected


def test_review7_internally_divergent_event_quantities_remain_candidate():
    namespace, _, _ = _main_namespace()
    query = _review6_incident_query()
    query.pop("manual_close_quantity")
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(amount=0.13, expected_position_amount=0.25),
        "broker.execution_audit",
        query,
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert projected["operational_correlation_conflict"] == "FAILSAFE_QUANTITY_MISMATCH"


def test_review7_text_exposes_sent_confirmation_execution_and_amount_channels():
    namespace, _, _ = _main_namespace()
    projected = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(
            event="BROKER_MANAGED_CLOSE_SENT",
            status="MANAGED_CLOSE_SENT_UNCONFIRMED",
            sent=True,
            confirmed=False,
            filled_amount=0.05,
            remaining_amount=0.08,
        ),
        "broker.executions",
        _review6_incident_query(),
    )
    findings = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    text = namespace["_fdsff_v1_text"]({
        "status": "FORENSICS_COMPLETE",
        "findings": findings,
        "live_lookup": {},
        "local_records": [],
        "reasons": [],
        "source_errors": [],
    })
    assert "failsafe_order_sent=True" in text
    assert "failsafe_execution_confirmed=False" in text
    assert "failsafe_executed=None" in text
    assert "failsafe_filled_amount=0.05" in text
    assert "failsafe_remaining_amount=0.08" in text


# ============================================================================
# REVISION 8 — real ledger time and conservative multi-attempt aggregation
# ============================================================================


def _review8_epoch(hour, minute, second=0):
    return datetime(2026, 7, 19, hour, minute, second, tzinfo=timezone(timedelta(hours=-3))).timestamp()


def _review8_operational(namespace, source="broker.execution_audit", **updates):
    raw = _review6_real_failsafe(**updates)
    return namespace["_fdsff_v1_operational_failsafe_record"](
        raw, source, _review6_incident_query()
    )


def test_review8_real_execution_ledger_minute_timestamp_correlates_by_interval():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace, source="broker.executions", ts="19/07/2026 13:38",
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["failsafe_timestamp_source_field"] == "ts"
    assert projected["failsafe_timestamp_basis"] == "SAO_PAULO_LOGGER_MINUTE"
    assert projected["failsafe_timestamp_precision"] == "MINUTE_INTERVAL"
    assert projected["failsafe_attempt_inside_incident_window"] is True
    assert projected["failsafe_timestamp_epoch_end"] - projected["failsafe_timestamp_epoch_start"] == pytest.approx(60.0, abs=1e-3)


def test_review8_audit_epoch_precedes_real_minute_ts():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        ts="19/07/2026 13:38",
        epoch=_review8_epoch(13, 38, 17),
    )
    assert projected["failsafe_timestamp_source_field"] == "epoch"
    assert projected["failsafe_timestamp_basis"] == "NUMERIC_EPOCH_SECONDS"
    assert projected["failsafe_timestamp_precision"] == "EXACT_SECOND_OR_BETTER"
    assert projected["failsafe_timestamp_epoch_start"] == pytest.approx(_review8_epoch(13, 38, 17))
    assert projected["failsafe_timestamp_evidence_conflict"] is False


def test_review8_conflicting_ts_and_epoch_preserves_both_and_prefers_epoch():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        ts="19/07/2026 12:00",
        epoch=_review8_epoch(13, 38, 17),
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["failsafe_timestamp_source_field"] == "epoch"
    assert projected["failsafe_timestamp_evidence_conflict"] is True
    assert {item["source_field"] for item in projected["failsafe_timestamp_observations"]} == {"epoch", "ts"}
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert "TIMESTAMP_EVIDENCE_CONFLICT" in result["classifications"]
    assert result["failsafe_attempt_before_manual_close_found"] is True


@pytest.mark.parametrize(
    ("ts", "relation", "conflict", "boundary_field"),
    [
        (
            "19/07/2026 13:36",
            "OVERLAPS_INCIDENT_START_BOUNDARY",
            "INCIDENT_WINDOW_START_BOUNDARY_AMBIGUOUS",
            "failsafe_overlaps_start_boundary",
        ),
        (
            "19/07/2026 13:39",
            "OVERLAPS_INCIDENT_END_BOUNDARY",
            "INCIDENT_WINDOW_END_BOUNDARY_AMBIGUOUS",
            "failsafe_overlaps_end_boundary",
        ),
    ],
)
def test_review8_minute_precision_at_incident_boundaries_is_candidate(
    ts, relation, conflict, boundary_field,
):
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(namespace, source="broker.executions", ts=ts)
    assert projected is not None
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert projected["operational_correlation_conflict"] == conflict
    assert projected["failsafe_incident_time_relation"] == relation
    assert projected[boundary_field] is True
    assert projected["failsafe_interval_fully_inside"] is False
    assert projected["failsafe_attempt_inside_incident_window"] is False


def test_review8_unparseable_real_ledger_timestamp_remains_candidate():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(namespace, ts="timestamp-unparseable")
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert projected["operational_correlation_conflict"] == "INCIDENT_WINDOW_OR_FACTUAL_TIMESTAMP_MISSING"
    assert projected["failsafe_timestamp_basis"] == "UNPARSEABLE_OR_MISSING"


def test_review8_local_source_coverage_uses_real_ts_and_epoch_contract(tmp_path):
    namespace, broker, _ = _main_namespace()
    real_minute_rows = [
        {"event": "HEARTBEAT", "ts": "19/07/2026 13:35"},
        {"event": "HEARTBEAT", "ts": "19/07/2026 13:40"},
    ]
    audit_rows = [
        {"event": "HEARTBEAT", "ts": "19/07/2026 13:35", "epoch": _review8_epoch(13, 35, 30)},
        {"event": "HEARTBEAT", "ts": "19/07/2026 13:40", "epoch": _review8_epoch(13, 40, 30)},
    ]
    rows_by_source = {
        "history.events": real_minute_rows,
        "broker.execution_audit": audit_rows,
        "broker.executions": real_minute_rows,
        "falcon.live_audit": real_minute_rows,
        "central.timeline": real_minute_rows,
    }
    _review5_local_sources(namespace, broker, tmp_path, rows_by_source)
    _matches, errors, _checked, metadata = _review5_read_local(
        namespace, _review6_incident_query()
    )
    assert errors == []
    assert all(item["incident_window_covered"] is True for item in metadata)
    audit_meta = next(item for item in metadata if item["source"] == "broker.execution_audit")
    assert audit_meta["oldest_timestamp"] == pytest.approx(_review8_epoch(13, 35, 30))
    assert audit_meta["newest_timestamp"] == pytest.approx(_review8_epoch(13, 40, 30))


def test_review8_managed_close_error_without_order_is_send_and_execution_inconclusive():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(namespace)
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_close_attempt_found"] is True
    assert result["failsafe_order_sent"] is None
    assert result["failsafe_execution_confirmed"] is None
    assert result["failsafe_executed"] is None
    assert "FAILSAFE_ERROR_SEND_AND_EXECUTION_INCONCLUSIVE" in result["classifications"]


def test_review8_managed_close_error_with_order_proves_send_only():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(namespace, order_id="FAILSAFE-ERROR-ORDER")
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_order_sent"] is True
    assert result["failsafe_execution_confirmed"] is None
    assert result["failsafe_executed"] is None


def test_review8_explicit_pre_transport_failure_is_the_only_error_false_path():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(namespace, failure_phase="BEFORE_CREATE_ORDER")
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_order_sent"] is False
    assert result["failsafe_execution_confirmed"] is False
    assert result["failsafe_executed"] is False


def test_review8_sent_unconfirmed_is_sent_but_not_factually_executed():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_SENT_UNCONFIRMED",
        sent=True,
        confirmed=False,
        order_id="FAILSAFE-UNCONFIRMED",
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_order_sent"] is True
    assert result["failsafe_execution_confirmed"] is False
    assert result["failsafe_executed"] is None
    assert "FAILSAFE_UNRESOLVED_SENT_ATTEMPT" in result["classifications"]


@pytest.mark.parametrize(
    ("status", "expected_confirmed", "expected_executed"),
    [
        ("MANAGED_CLOSE_SENT_UNCONFIRMED", False, None),
        ("MANAGED_CLOSE_CONFIRMED", True, True),
    ],
)
def test_review8_real_status_is_semantic_even_without_redundant_confirmed_field(
    status, expected_confirmed, expected_executed,
):
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status=status,
        sent=True,
        confirmed=None,
        order_id=f"FAILSAFE-{status}",
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_execution_confirmed"] is expected_confirmed
    assert result["failsafe_executed"] is expected_executed


def test_review8_same_operation_in_both_ledgers_is_one_attempt():
    namespace, _, _ = _main_namespace()
    execution_observation = _review8_operational(
        namespace, source="broker.executions", ts="19/07/2026 13:38",
    )
    audit_observation = _review8_operational(
        namespace,
        source="broker.execution_audit",
        ts="19/07/2026 13:38",
        epoch=_review8_epoch(13, 38, 17),
    )
    result = namespace["_fdsff_v1_classify"](
        [execution_observation, audit_observation], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_observation_count"] == 2
    assert result["failsafe_attempt_count"] == 1
    assert result["failsafe_multiple_attempts"] is False
    assert result["failsafe_dedup_inconclusive"] is False
    assert result["failsafe_attempts"][0]["observation_count"] == 2


def test_review8_ambiguous_cross_ledger_dedup_preserves_observations():
    namespace, _, _ = _main_namespace()
    observations = [
        _review8_operational(namespace, source="broker.executions"),
        _review8_operational(namespace, source="broker.execution_audit", epoch=_review8_epoch(13, 38, 10)),
        _review8_operational(namespace, source="broker.execution_audit", epoch=_review8_epoch(13, 38, 20)),
    ]
    result = namespace["_fdsff_v1_classify"](
        observations, _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_observation_count"] == 3
    assert result["failsafe_attempt_count"] is None
    assert result["failsafe_dedup_inconclusive"] is True
    assert len(result["failsafe_attempts"]) == 3
    assert "FAILSAFE_DEDUP_INCONCLUSIVE" in result["classifications"]


def test_review8_error_then_sent_unconfirmed_aggregates_conservatively():
    namespace, _, _ = _main_namespace()
    error = _review8_operational(namespace)
    sent = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_SENT_UNCONFIRMED",
        sent=True,
        confirmed=False,
        order_id="FAILSAFE-SENT-2",
    )
    result = namespace["_fdsff_v1_classify"](
        [error, sent], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_order_sent"] is True
    assert result["failsafe_execution_confirmed"] is None
    assert result["failsafe_executed"] is None
    assert result["failsafe_multiple_attempts"] is True
    assert {"FAILSAFE_MULTIPLE_ATTEMPTS", "FAILSAFE_UNRESOLVED_SENT_ATTEMPT"}.issubset(result["classifications"])


def test_review8_confirmed_then_error_preserves_success_and_both_attempts():
    namespace, _, _ = _main_namespace()
    confirmed = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_CONFIRMED",
        sent=True,
        confirmed=True,
        order_id="FAILSAFE-CONFIRMED",
        filled_amount=0.13,
        remaining_amount=0.0,
    )
    error = _review8_operational(namespace)
    result = namespace["_fdsff_v1_classify"](
        [confirmed, error], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_any_execution_confirmed"] is True
    assert result["failsafe_execution_confirmed"] is True
    assert result["failsafe_executed"] is True
    assert result["failsafe_all_attempts_resolved"] is False
    assert result["failsafe_attempt_count"] == 2


@pytest.mark.parametrize(
    ("field", "aggregate_field"),
    [
        ("filled_amount", "failsafe_filled_amount"),
        ("remaining_amount", "failsafe_remaining_amount"),
    ],
)
def test_review8_incompatible_amounts_across_attempts_do_not_select_first(field, aggregate_field):
    namespace, _, _ = _main_namespace()
    first = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_CONFIRMED",
        sent=True,
        confirmed=True,
        order_id="FAILSAFE-AMOUNT-1",
        **{field: 0.05},
    )
    second = _review8_operational(
        namespace,
        source="broker.execution_audit",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_CONFIRMED",
        sent=True,
        confirmed=True,
        order_id="FAILSAFE-AMOUNT-2",
        **{field: 0.13},
    )
    result = namespace["_fdsff_v1_classify"](
        [first, second], _empty_live(), _review6_incident_query()
    )
    assert result[aggregate_field] is None
    assert result["failsafe_amount_evidence_conflict"] is True
    assert "FAILSAFE_AMOUNT_EVIDENCE_CONFLICT" in result["classifications"]
    values = [attempt[aggregate_field] for attempt in result["failsafe_attempts"]]
    assert values == pytest.approx([0.05, 0.13])


def test_review8_event_before_failure_does_not_prove_incident_timing():
    namespace, _, _ = _main_namespace()
    local = [{
        "event": "STOP_FAILSAFE_MARKET_CONFIRMED",
        "status": "STOP_FAILSAFE_MARKET_CONFIRMED",
        "lifecycle_id": "LC-SOL",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "created_at": "2026-07-19T12:00:00-03:00",
        "failsafe_attempted": True,
        "failsafe_executed": True,
    }]
    result = namespace["_fdsff_v1_classify"](
        local, _empty_live(local_negative_evidence_complete=True), _review6_incident_query()
    )
    assert result["failsafe_close_attempt_found"] is None
    assert result["failsafe_attempt_before_manual_close_found"] is None
    assert result["failsafe_attempt_inside_incident_window"] is None
    assert result["failsafe_candidate_evidence"][0]["operational_correlation_conflict"] == "FAILSAFE_ATTEMPT_OUTSIDE_INCIDENT_WINDOW"
    assert "FAILSAFE_EVIDENCE_CONFLICT_OR_CANDIDATE" in result["classifications"]


def test_review8_operational_failsafe_never_contaminates_disaster_stop_fills():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        source="broker.executions",
        event="BROKER_MANAGED_CLOSE_SENT",
        status="MANAGED_CLOSE_CONFIRMED",
        sent=True,
        confirmed=True,
        order_id="FAILSAFE-FILL-SEPARATE",
        filled_amount=0.13,
    )
    result = namespace["_fdsff_v1_classify"](
        [projected],
        _empty_live(stop_orders=[{
            "order_id": "2078846241538150400",
            "status": "FAILED",
            "requested_quantity": 0.13,
            "executed_quantity": 0.0,
        }]),
        _review6_incident_query(),
    )
    assert result["failsafe_filled_amount"] == pytest.approx(0.13)
    assert result["fill_count"] == 0
    assert result["executed_quantity"] == pytest.approx(0.0)


# ============================================================================
# REVISION 9 — strict temporal attribution to the factual incident
# ============================================================================


@pytest.mark.parametrize("minute", [37, 38])
def test_review9_full_minute_inside_incident_is_positive(minute):
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        source="broker.executions",
        ts=f"19/07/2026 13:{minute:02d}",
    )
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["failsafe_incident_time_relation"] == "FULLY_INSIDE_INCIDENT_WINDOW"
    assert projected["failsafe_interval_fully_inside"] is True
    assert projected["failsafe_overlaps_start_boundary"] is False
    assert projected["failsafe_overlaps_end_boundary"] is False
    assert projected["failsafe_attempt_inside_incident_window"] is True


@pytest.mark.parametrize(
    (
        "hour", "minute", "second", "ts", "expected_role", "expected_relation",
        "expected_conflict", "expected_inside",
    ),
    [
        (
            13, 36, 33, "19/07/2026 13:36", "FAILSAFE_CLOSE_AUDIT_CANDIDATE",
            "CLOCK_SKEW_TOLERANCE_ONLY_BEFORE",
            "INCIDENT_CLOCK_SKEW_BEFORE_START_CANDIDATE", False,
        ),
        (
            13, 36, 34, "19/07/2026 13:36", "FAILSAFE_CLOSE_AUDIT",
            "FULLY_INSIDE_INCIDENT_WINDOW", None, True,
        ),
        (
            13, 39, 32, "19/07/2026 13:39", "FAILSAFE_CLOSE_AUDIT",
            "FULLY_INSIDE_INCIDENT_WINDOW", None, True,
        ),
        (
            13, 39, 33, "19/07/2026 13:39", "FAILSAFE_CLOSE_AUDIT_CANDIDATE",
            "CLOCK_SKEW_TOLERANCE_ONLY_AFTER",
            "INCIDENT_CLOCK_SKEW_AFTER_END_CANDIDATE", False,
        ),
        (
            13, 39, 34, "19/07/2026 13:39", "FAILSAFE_CLOSE_AUDIT_CANDIDATE",
            "CLOCK_SKEW_TOLERANCE_ONLY_AFTER",
            "INCIDENT_CLOCK_SKEW_AFTER_END_CANDIDATE", False,
        ),
        (
            13, 39, 37, "19/07/2026 13:39", "FAILSAFE_CLOSE_AUDIT_CANDIDATE",
            "CLOCK_SKEW_TOLERANCE_ONLY_AFTER",
            "INCIDENT_CLOCK_SKEW_AFTER_END_CANDIDATE", False,
        ),
    ],
)
def test_review9_exact_epoch_respects_inclusive_start_and_exclusive_end(
    hour, minute, second, ts, expected_role, expected_relation,
    expected_conflict, expected_inside,
):
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        ts=ts,
        epoch=_review8_epoch(hour, minute, second),
    )
    assert projected["failsafe_timestamp_source_field"] == "epoch"
    assert projected["operational_correlation_role"] == expected_role
    assert projected["failsafe_incident_time_relation"] == expected_relation
    assert projected["failsafe_interval_fully_inside"] is expected_inside
    assert projected["failsafe_attempt_inside_incident_window"] is expected_inside
    assert projected.get("operational_correlation_conflict") == expected_conflict
    if "CLOCK_SKEW" in expected_relation:
        assert projected["failsafe_clock_skew_tolerance_only"] is True


@pytest.mark.parametrize(
    ("ts", "second", "secondary_relation", "expected_role"),
    [
        (
            "19/07/2026 13:36", 40,
            "OVERLAPS_INCIDENT_START_BOUNDARY", "FAILSAFE_CLOSE_AUDIT",
        ),
        (
            "19/07/2026 13:39", 20,
            "OVERLAPS_INCIDENT_END_BOUNDARY", "FAILSAFE_CLOSE_AUDIT",
        ),
        (
            "19/07/2026 13:39", 34,
            "OVERLAPS_INCIDENT_END_BOUNDARY", "FAILSAFE_CLOSE_AUDIT_CANDIDATE",
        ),
    ],
)
def test_review9_exact_epoch_resolves_ambiguous_text_minute(
    ts, second, secondary_relation, expected_role,
):
    namespace, _, _ = _main_namespace()
    minute = 36 if ":36" in ts else 39
    projected = _review8_operational(
        namespace,
        ts=ts,
        epoch=_review8_epoch(13, minute, second),
    )
    assert projected["failsafe_timestamp_source_field"] == "epoch"
    assert projected["operational_correlation_role"] == expected_role
    observations = projected["failsafe_timestamp_observation_relations"]
    text_observation = next(item for item in observations if item["source_field"] == "ts")
    assert text_observation["relation"] == secondary_relation
    if expected_role == "FAILSAFE_CLOSE_AUDIT":
        assert projected["failsafe_incident_time_relation"] == "FULLY_INSIDE_INCIDENT_WINDOW"
        assert projected["failsafe_attempt_inside_incident_window"] is True
    else:
        assert projected["failsafe_incident_time_relation"] == "CLOCK_SKEW_TOLERANCE_ONLY_AFTER"
        assert projected["failsafe_attempt_inside_incident_window"] is False


def test_review9_divergent_text_timestamp_never_replaces_primary_epoch():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace,
        ts="19/07/2026 12:00",
        epoch=_review8_epoch(13, 38, 17),
    )
    assert projected["failsafe_timestamp_source_field"] == "epoch"
    assert projected["failsafe_incident_time_relation"] == "FULLY_INSIDE_INCIDENT_WINDOW"
    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["failsafe_timestamp_evidence_conflict"] is True


@pytest.mark.parametrize("ts", ["19/07/2026 13:36", "19/07/2026 13:39"])
def test_review9_boundary_candidate_blocks_absence_without_becoming_attempt(ts):
    namespace, _, _ = _main_namespace()
    candidate = _review8_operational(
        namespace, source="broker.executions", ts=ts,
    )
    result = namespace["_fdsff_v1_classify"](
        [candidate],
        _empty_live(local_negative_evidence_complete=True),
        _review6_incident_query(),
    )
    assert result["failsafe_close_attempt_found"] is None
    assert result["failsafe_attempt_before_manual_close_found"] is None
    assert result["failsafe_attempt_inside_incident_window"] is None
    assert result["failsafe_executed"] is None
    assert "FAILSAFE_CLOSE_ATTEMPT_NOT_FOUND" not in result["classifications"]
    assert "FAILSAFE_EVIDENCE_CONFLICT_OR_CANDIDATE" in result["classifications"]


def test_review9_fully_contained_attempt_proves_before_manual_close():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace, source="broker.executions", ts="19/07/2026 13:38",
    )
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    assert result["failsafe_close_attempt_found"] is True
    assert result["failsafe_attempt_inside_incident_window"] is True
    assert result["failsafe_attempt_before_manual_close_found"] is True
    assert result["failsafe_attempts"][0]["failsafe_incident_time_relation"] == "FULLY_INSIDE_INCIDENT_WINDOW"
    assert result["failsafe_attempts"][0]["failsafe_interval_fully_inside"] is True


def test_review9_text_exposes_strict_incident_relation_fields():
    namespace, _, _ = _main_namespace()
    projected = _review8_operational(
        namespace, source="broker.executions", ts="19/07/2026 13:38",
    )
    findings = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )
    text = namespace["_fdsff_v1_text"]({
        "status": "FORENSICS_COMPLETE",
        "findings": findings,
        "live_lookup": {},
        "local_records": [],
        "reasons": [],
        "source_errors": [],
    })
    assert "failsafe_incident_time_relation=FULLY_INSIDE_INCIDENT_WINDOW" in text
    assert "failsafe_interval_fully_inside=True" in text


# ============================================================================
# REVIEW 2 ITEM 6 - terminal disaster-stop emergency projection
# ============================================================================


def _review2_item6_terminal_emergency(**updates):
    row = {
        "event": "BROKER_MANAGED_CLOSE_SENT",
        "reason": "STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "amount": 0.13,
        "expected_position_amount": 0.13,
        "incident_id": "FALCON-TERMINAL-STOP-INCIDENT-1",
        "lifecycle_id": "LC-SOL",
        "client_tag": "FALCON-TDS-0123456789abcdef",
        "emergency_operation": "TERMINAL_STOP_EMERGENCY_CLOSE",
        "attempt_state": "SENT_UNCONFIRMED",
        "send_attempted": True,
        "sent": True,
        "confirmed": False,
        "send_outcome_unknown": False,
        "order_id": "TERMINAL-CLOSE-1",
        "filled_amount": 0.05,
        "remaining_amount": 0.08,
        "status": "MANAGED_CLOSE_SENT_UNCONFIRMED",
        "ts": "19/07/2026 13:38",
        "epoch": _review8_epoch(13, 38, 17),
    }
    row.update(updates)
    return row


def _review2_item6_project(namespace, **updates):
    return namespace["_fdsff_v1_operational_failsafe_record"](
        _review2_item6_terminal_emergency(**updates),
        "broker.execution_audit",
        _review6_incident_query(),
    )


def test_review2_item6_terminal_emergency_reason_has_its_own_safe_projection():
    namespace, _, _ = _main_namespace()

    projected = _review2_item6_project(namespace)

    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert projected["failsafe_reason"] == "STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN"
    assert projected["terminal_stop_emergency"] is True
    assert projected["terminal_stop_emergency_incident_id"] == "FALCON-TERMINAL-STOP-INCIDENT-1"
    assert projected["terminal_stop_emergency_lifecycle_id"] == "LC-SOL"
    assert projected["terminal_stop_emergency_client_order_id"] == "FALCON-TDS-0123456789abcdef"
    assert projected["terminal_stop_emergency_operation"] == "TERMINAL_STOP_EMERGENCY_CLOSE"
    assert projected["terminal_stop_emergency_attempt_state"] == "SENT_UNCONFIRMED"
    assert projected["terminal_stop_emergency_send_attempted"] is True
    assert projected["terminal_stop_emergency_sent"] is True
    assert projected["terminal_stop_emergency_confirmed"] is False
    assert projected["terminal_stop_emergency_send_outcome_unknown"] is False
    assert projected["terminal_stop_emergency_order_id"] == "TERMINAL-CLOSE-1"
    assert projected["terminal_stop_emergency_filled_amount"] == pytest.approx(0.05)
    assert projected["terminal_stop_emergency_remaining_amount"] == pytest.approx(0.08)
    assert projected["terminal_stop_emergency_timestamp"] == pytest.approx(
        _review8_epoch(13, 38, 17)
    )
    assert projected["terminal_stop_emergency_status"] == "MANAGED_CLOSE_SENT_UNCONFIRMED"
    assert "stop_order_id" not in projected


def test_review2_item6_terminal_emergency_has_own_classifications_and_never_becomes_stop_fill():
    namespace, _, _ = _main_namespace()
    projected = _review2_item6_project(namespace)
    live = _empty_live(stop_orders=[{
        "order_id": "2078846241538150400",
        "raw_status": "FAILED",
        "status": "CANCELED",
        "requested_quantity": 0.13,
        "executed_quantity": 0.0,
        "requested_quantity_unit": "COIN",
        "executed_quantity_unit": "COIN",
    }])

    result = namespace["_fdsff_v1_classify"](
        [projected], live, _review6_incident_query()
    )

    assert result["terminal_stop_emergency_attempt_found"] is True
    assert result["terminal_stop_emergency_incident_id"] == "FALCON-TERMINAL-STOP-INCIDENT-1"
    assert result["terminal_stop_emergency_lifecycle_id"] == "LC-SOL"
    assert result["terminal_stop_emergency_client_order_id"] == "FALCON-TDS-0123456789abcdef"
    assert result["terminal_stop_emergency_send_attempted"] is True
    assert result["terminal_stop_emergency_sent"] is True
    assert result["terminal_stop_emergency_confirmed"] is False
    assert result["terminal_stop_emergency_order_id"] == "TERMINAL-CLOSE-1"
    assert result["terminal_stop_emergency_filled_amount"] == pytest.approx(0.05)
    assert result["terminal_stop_emergency_remaining_amount"] == pytest.approx(0.08)
    assert {
        "TERMINAL_STOP_EMERGENCY_ATTEMPT_FOUND",
        "TERMINAL_STOP_EMERGENCY_SEND_ATTEMPTED",
        "TERMINAL_STOP_EMERGENCY_SENT_UNCONFIRMED",
    }.issubset(result["classifications"])
    assert result["executed_quantity"] == pytest.approx(0.0)
    assert result["fill_count"] == 0
    assert result["derived_order_found"] is False
    assert result["terminal_stop_emergency_evidence"][0][
        "terminal_stop_emergency_order_id"
    ] == "TERMINAL-CLOSE-1"


def test_review2_item6_confirmed_terminal_emergency_has_confirmed_classification():
    namespace, _, _ = _main_namespace()
    projected = _review2_item6_project(
        namespace,
        attempt_state="CONFIRMED",
        confirmed=True,
        filled_amount=0.13,
        remaining_amount=0.0,
        status="MANAGED_CLOSE_CONFIRMED",
    )

    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )

    assert result["terminal_stop_emergency_confirmed"] is True
    assert "TERMINAL_STOP_EMERGENCY_CLOSE_CONFIRMED" in result["classifications"]
    assert "TERMINAL_STOP_EMERGENCY_SENT_UNCONFIRMED" not in result["classifications"]


@pytest.mark.parametrize(
    ("updates", "expected_conflict"),
    [
        (
            {"client_tag": "FALCON-LIVE-SOL"},
            "TERMINAL_EMERGENCY_CLIENT_ID_MISSING_OR_INVALID",
        ),
        (
            {"lifecycle_id": "OTHER-LIFECYCLE"},
            "TERMINAL_EMERGENCY_LIFECYCLE_MISMATCH",
        ),
        (
            {"emergency_operation": "TP50_REAL_PARTIAL"},
            "TERMINAL_EMERGENCY_OPERATION_MISMATCH",
        ),
    ],
)
def test_review2_item6_terminal_emergency_weak_or_mismatched_identity_is_candidate(
    updates, expected_conflict,
):
    namespace, _, _ = _main_namespace()

    projected = _review2_item6_project(namespace, **updates)
    result = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )

    assert projected["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT_CANDIDATE"
    assert projected["operational_correlation_conflict"] == expected_conflict
    assert result["terminal_stop_emergency_attempt_found"] is None
    assert not result["terminal_stop_emergency_evidence"]
    assert result["terminal_stop_emergency_candidate_evidence"]
    assert "TERMINAL_STOP_EMERGENCY_EVIDENCE_CANDIDATE" in result["classifications"]


def test_review2_item6_legacy_reason_remains_separate_from_terminal_emergency():
    namespace, _, _ = _main_namespace()
    legacy = namespace["_fdsff_v1_operational_failsafe_record"](
        _review6_real_failsafe(),
        "broker.execution_audit",
        _review6_incident_query(),
    )

    result = namespace["_fdsff_v1_classify"](
        [legacy], _empty_live(), _review6_incident_query()
    )

    assert legacy["failsafe_reason"] == "STOP_BROKER_NOT_CONFIRMED"
    assert "terminal_stop_emergency" not in legacy
    assert result["failsafe_close_attempt_found"] is True
    assert result["terminal_stop_emergency_attempt_found"] is False
    assert not any(
        classification.startswith("TERMINAL_STOP_EMERGENCY_")
        for classification in result["classifications"]
    )


def test_review2_item6_terminal_emergency_text_exposes_safe_channels():
    namespace, _, _ = _main_namespace()
    projected = _review2_item6_project(namespace)
    findings = namespace["_fdsff_v1_classify"](
        [projected], _empty_live(), _review6_incident_query()
    )

    text = namespace["_fdsff_v1_text"]({
        "status": "FORENSICS_COMPLETE",
        "findings": findings,
        "live_lookup": {},
        "local_records": [],
        "reasons": [],
        "source_errors": [],
    })

    assert "terminal_stop_emergency_attempt_found=True" in text
    assert "terminal_stop_emergency_incident_id=FALCON-TERMINAL-STOP-INCIDENT-1" in text
    assert "terminal_stop_emergency_lifecycle_id=LC-SOL" in text
    assert "terminal_stop_emergency_client_order_id=FALCON-TDS-0123456789abcdef" in text
    assert "terminal_stop_emergency_send_attempted=True" in text
    assert "terminal_stop_emergency_sent=True" in text
    assert "terminal_stop_emergency_confirmed=False" in text
    assert "terminal_stop_emergency_order_id=TERMINAL-CLOSE-1" in text
    assert "terminal_stop_emergency_filled_amount=0.05" in text
    assert "terminal_stop_emergency_remaining_amount=0.08" in text
    assert "terminal_stop_emergency_status=MANAGED_CLOSE_SENT_UNCONFIRMED" in text


# ---------------------------------------------------------------------------
# P0: BingX support-confirmed duplicate clientOrderID evidence.
# ---------------------------------------------------------------------------

P0_DUPLICATED_CLIENT_ORDER_ID = "FALCON-LIVE-FALCON15-178-DS"
P0_SUPPORT_CONFIRMED_STOP_ORDER_ID = "2078846241538150400"
P0_SUPPORT_CONFIRMED_LIFECYCLE_ID = (
    "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784470538"
)


def test_p0_support_cause_is_separate_from_api_failure_and_lists_exact_local_occurrence():
    local = [
        {
            "source": "broker.execution_audit",
            "event": "DISASTER_STOP_FAILED",
            "stop_order_id": P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
            "order_id": P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
            "client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID,
            "symbol": "SOLUSDT",
            "side": "SELL",
            "position_side": "LONG",
            "status": "FAILED",
            "executed_quantity": 0.0,
            "updated_at": "2026-07-19T13:36:34-03:00",
        },
        {
            "source": "trade_registry.closed_trades",
            "event": "FALCON_LIVE_AUDIT_ACK",
            "stop_order_id": P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
            "entry_order_id": "ENTRY-1",
            "client_order_id": "FALCON-LIVE-1",
            "lifecycle_id": P0_SUPPORT_CONFIRMED_LIFECYCLE_ID,
            "trade_id": "FALCON:FALCON15:SOLUSDT:LONG",
            "bot": "FALCON",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "status": "CLOSED",
        },
        {
            "source": "broker.execution_audit",
            "event": "BROKER_DISASTER_STOP_CREATED",
            "stop_order_id": "OTHER-STOP",
            "order_id": "OTHER-STOP",
            "client_order_id": "UNRELATED-CLIENT-ID",
            "symbol": "SOLUSDT",
            "position_side": "LONG",
        },
    ]
    namespace, broker, registry = _main_namespace(local_records=local)

    payload = _build(
        namespace,
        stop_order_id=P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
        lifecycle_id=P0_SUPPORT_CONFIRMED_LIFECYCLE_ID,
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    findings = payload["findings"]

    # The API-derived channel remains inconclusive; support evidence has its own
    # explicit source and does not rewrite failure_reason/failure_cause_status.
    assert findings["failure_cause_status"] == "UNKNOWN_WITHOUT_FACTUAL_BINGX_REASON"
    assert findings["api_failure_cause_status"] == "UNKNOWN_WITHOUT_FACTUAL_BINGX_REASON"
    assert findings["failure_cause_resolution_status"] == "SUPPORT_CONFIRMED"
    assert findings["support_confirmed_failure_cause"] == "DUPLICATE_CLIENT_ORDER_ID"
    assert findings["support_confirmed_failure_basis"] == "BINGX_SUPPORT_CASE"
    assert findings["duplicated_client_order_id"] == P0_DUPLICATED_CLIENT_ORDER_ID
    assert findings["client_order_id_scope"] == "ACCOUNT_WIDE"
    assert findings["client_order_id_uniqueness"] == "PERSISTENT_LIFETIME"
    assert findings["client_order_id_case_sensitive"] is False
    assert findings["affected_dates"] == [
        "2026-07-14", "2026-07-15", "2026-07-19",
    ]
    assert findings["duplicated_client_order_id_local_occurrence_count"] == 1
    assert findings["duplicated_client_order_id_local_audit_complete"] is True
    occurrence = findings["duplicated_client_order_id_local_occurrences"][0]
    assert occurrence["client_order_id"] == P0_DUPLICATED_CLIENT_ORDER_ID
    assert occurrence["order_id"] == P0_SUPPORT_CONFIRMED_STOP_ORDER_ID
    assert occurrence["associated_lifecycle_ids"] == [
        P0_SUPPORT_CONFIRMED_LIFECYCLE_ID
    ]
    assert occurrence["associated_trade_ids"] == [
        "FALCON:FALCON15:SOLUSDT:LONG"
    ]
    assert occurrence["associated_entry_order_ids"] == ["ENTRY-1"]
    assert all(
        row["client_order_id"].upper() == P0_DUPLICATED_CLIENT_ORDER_ID
        for row in findings["duplicated_client_order_id_local_occurrences"]
    )
    assert payload["duplicated_client_order_id_local_audit"]["raw_payload_exposed"] is False
    assert broker.mutation_calls == []
    assert registry.write_calls == []

    rendered = namespace["_fdsff_v1_text"](payload)
    assert "support_confirmed_failure_cause=DUPLICATE_CLIENT_ORDER_ID" in rendered
    assert "failure_cause_resolution_status=SUPPORT_CONFIRMED" in rendered
    assert "support_confirmed_failure_basis=BINGX_SUPPORT_CASE" in rendered
    assert f"duplicated_client_order_id={P0_DUPLICATED_CLIENT_ORDER_ID}" in rendered
    assert "client_order_id_scope=ACCOUNT_WIDE" in rendered
    assert "client_order_id_uniqueness=PERSISTENT_LIFETIME" in rendered
    assert "client_order_id_case_sensitive=False" in rendered
    assert "affected_dates=['2026-07-14', '2026-07-15', '2026-07-19']" in rendered
    assert "duplicated_client_order_id_local_occurrence_count=1" in rendered
    assert (
        f"associated_lifecycle_ids=['{P0_SUPPORT_CONFIRMED_LIFECYCLE_ID}']"
        in rendered
    )


def test_p0_unrelated_stop_never_inherits_support_confirmed_duplicate_cause():
    local = [{
        "source": "broker.execution_audit",
        "event": "DISASTER_STOP_FAILED",
        "stop_order_id": "UNRELATED-STOP",
        "order_id": "UNRELATED-STOP",
        "client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID,
        "symbol": "SOLUSDT",
        "position_side": "LONG",
        "status": "FAILED",
        "updated_at": "2026-07-19T13:36:34-03:00",
    }]
    namespace, broker, registry = _main_namespace(local_records=local)

    payload = _build(
        namespace,
        stop_order_id="UNRELATED-STOP",
        lifecycle_id="UNRELATED-LIFECYCLE",
        client_order_id="UNRELATED-ENTRY-CLIENT-ID",
        failure_timestamp="2026-07-19T13:36:34-03:00",
    )
    findings = payload["findings"]

    assert findings["failure_cause_resolution_status"] == (
        "NOT_SUPPORT_CONFIRMED_FOR_INCIDENT"
    )
    assert findings["support_confirmation_scope_matched"] is False
    assert findings["support_confirmed_failure_cause"] is None
    assert findings["support_confirmed_failure_basis"] is None
    assert findings["duplicated_client_order_id"] is None
    assert findings["duplicated_client_order_id_local_occurrence_count"] is None
    assert findings["duplicated_client_order_id_local_audit_basis"] == (
        "NOT_RUN_SUPPORT_CONFIRMATION_SCOPE_MISMATCH"
    )
    assert broker.mutation_calls == []
    assert registry.write_calls == []


@pytest.mark.parametrize(
    "identity",
    [
        {"client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID.lower()},
        {"lifecycle_id": P0_SUPPORT_CONFIRMED_LIFECYCLE_ID},
    ],
)
def test_p0_exact_legacy_client_or_known_lifecycle_matches_support_scope(identity):
    namespace, _, _ = _main_namespace()
    payload = _build(
        namespace,
        stop_order_id=None,
        lifecycle_id=identity.get("lifecycle_id", "UNRELATED-LIFECYCLE"),
        client_order_id=identity.get(
            "client_order_id", "UNRELATED-ENTRY-CLIENT-ID"
        ),
        failure_timestamp=None,
    )

    assert payload["findings"]["failure_cause_resolution_status"] == (
        "SUPPORT_CONFIRMED"
    )
    assert payload["findings"]["support_confirmation_scope_matched"] is True


def test_p0_known_date_without_strong_incident_identity_is_not_support_confirmed():
    namespace, _, _ = _main_namespace()
    payload = _build(
        namespace,
        stop_order_id=None,
        lifecycle_id="UNRELATED-LIFECYCLE",
        client_order_id="UNRELATED-ENTRY-CLIENT-ID",
        failure_timestamp="2026-07-19T13:36:34-03:00",
        manual_close_timestamp=None,
    )

    assert payload["findings"]["failure_cause_resolution_status"] == (
        "NOT_SUPPORT_CONFIRMED_FOR_INCIDENT"
    )
    assert payload["findings"]["support_confirmation_scope_basis"] == (
        "KNOWN_AFFECTED_DATE_WITHOUT_STRONG_INCIDENT_IDENTITY"
    )


def test_p0_account_wide_case_insensitive_readers_preserve_observed_client_id_case(tmp_path):
    lowercase_id = P0_DUPLICATED_CLIENT_ORDER_ID.lower()
    record = {
        "event": "DISASTER_STOP_FAILED",
        "order_id": "ACCOUNT-WIDE-STOP",
        "clientOrderID": lowercase_id,
        "bot": "TRENDPRO",
        "external_position": True,
        "updated_at": "2026-07-14T12:00:00Z",
    }
    registry = FakeRegistry(closed_trades=[record])
    namespace, _, _ = _main_namespace(registry=registry)
    query = {
        "client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID,
        "_account_wide_client_order_id_audit": True,
    }

    # Account-wide means neither another bot nor an external-position marker may
    # hide a collision.  Comparison is normalized, but evidence keeps its factual
    # observed spelling for auditability.
    assert namespace["_fdsff_v1_matches"](record, query) is True
    registry_matches, registry_error = namespace["_fdsff_v1_read_registry_real"](query)
    assert registry_error is None
    assert registry_matches[0]["client_order_id"] == lowercase_id

    snapshot_path = tmp_path / "liveorder-snapshot.json"
    snapshot_path.write_text(json.dumps(record), encoding="utf-8")
    snapshot_matches, snapshot_error = namespace[
        "_fdsff_v1_read_snapshot_records_real"
    ](snapshot_path, "test.snapshot", query)
    assert snapshot_error is None
    assert snapshot_matches[0]["client_order_id"] == lowercase_id

    history_path = tmp_path / "history-events.jsonl"
    history_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    missing = tmp_path / "missing.jsonl"
    namespace["super_history_manager"] = type(
        "HistorySource", (), {"HISTORY_EVENTS_FILE": history_path}
    )()
    namespace["central_broker"] = type(
        "BrokerSources",
        (),
        {
            "EXECUTION_AUDIT_LOG_FILE": missing,
            "EXECUTIONS_LOG_FILE": missing,
        },
    )()
    namespace["FALCON_LIVE_AUDIT_EVENTS_FILE"] = missing
    namespace["CENTRAL_TIMELINE_LOG_FILE"] = missing
    local_matches, _, sources_checked, metadata = namespace[
        "_fdsff_v1_read_local_events_real"
    ](query)
    assert 1 <= sources_checked <= 5
    assert len(metadata) == sources_checked
    assert local_matches[0]["client_order_id"] == lowercase_id

    namespace["_fdsff_v1_read_registry"] = lambda _query: (registry_matches, None)
    namespace["_fdsff_v1_read_snapshot_records"] = lambda *_args: (
        snapshot_matches, None,
    )
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        local_matches, [], 5, [
            {
                "source": f"source-{index}",
                "saturated": False,
                "read_error": None,
            }
            for index in range(5)
        ],
    )
    audit = namespace["_fdsff_v1_duplicate_client_order_id_audit"](
        P0_DUPLICATED_CLIENT_ORDER_ID
    )
    assert audit["occurrence_count"] >= 1
    assert any(
        item["client_order_id"] == lowercase_id
        for item in audit["occurrences"]
    )
    assert all(
        item["client_order_id_match_basis"]
        == "CASE_NORMALIZED_EXACT_CLIENT_ORDER_ID"
        for item in audit["occurrences"]
    )


def test_p0_nested_legacy_id_is_not_hidden_by_a_different_top_level_alias():
    namespace, _, _ = _main_namespace()
    record = {
        "event": "DISASTER_STOP_FAILED",
        "order_id": "STOP-NESTED",
        "client_order_id": "FDS1-UNRELATED-ACCOUNT-ID",
        "info": {
            "clientOrderID": P0_DUPLICATED_CLIENT_ORDER_ID.lower(),
        },
        "bot": "OTHER_BOT",
        "external_position": True,
    }
    query = {
        "client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID,
        "_account_wide_client_order_id_audit": True,
    }

    assert namespace["_fdsff_v1_matches"](record, query) is True
    safe = namespace["_fdsff_v1_safe_record"](record, "test")
    assert safe["client_order_ids"] == [
        "FDS1-UNRELATED-ACCOUNT-ID",
        P0_DUPLICATED_CLIENT_ORDER_ID.lower(),
    ]

    namespace["_fdsff_v1_read_registry"] = lambda _query: ([record], None)
    namespace["_fdsff_v1_read_snapshot_records"] = lambda *_args: ([], None)
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        [],
        [],
        5,
        [
            {"source": f"source-{index}", "saturated": False, "read_error": None}
            for index in range(5)
        ],
    )

    audit = namespace["_fdsff_v1_duplicate_client_order_id_audit"](
        P0_DUPLICATED_CLIENT_ORDER_ID
    )

    assert audit["occurrence_count"] == 1
    assert audit["evidence_record_count"] == 1
    assert audit["unique_occurrence_count"] == 1
    assert audit["occurrences"][0]["client_order_id"] == (
        P0_DUPLICATED_CLIENT_ORDER_ID.lower()
    )


def test_p0_duplicate_client_order_id_local_audit_is_explicitly_partial_when_source_saturated():
    namespace, broker, registry = _main_namespace()
    occurrence = {
        "source": "broker.execution_audit",
        "event": "BROKER_DISASTER_STOP_CREATED",
        "stop_order_id": P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
        "order_id": P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
        "client_order_id": P0_DUPLICATED_CLIENT_ORDER_ID,
        "symbol": "SOLUSDT",
        "position_side": "LONG",
    }
    metadata = [
        {
            "source": f"source-{index}",
            "saturated": index == 0,
            "read_error": None,
            "incident_window_covered": False,
            "critical_alert_transport_audit_complete": False,
        }
        for index in range(5)
    ]
    namespace["_fdsff_v1_read_local_events"] = lambda _query: (
        [copy.deepcopy(occurrence)], [], 5, copy.deepcopy(metadata)
    )

    payload = _build(
        namespace,
        stop_order_id=P0_SUPPORT_CONFIRMED_STOP_ORDER_ID,
    )
    findings = payload["findings"]

    assert findings["duplicated_client_order_id_local_occurrence_count"] == 1
    assert findings["duplicated_client_order_id_local_audit_complete"] is False
    assert findings["duplicated_client_order_id_local_audit_basis"] == (
        "PARTIAL_BOUNDED_LOCAL_SOURCES_NO_ABSENCE_CLAIM"
    )
    assert findings["duplicated_client_order_id_local_sources_saturated"] == [
        "source-0"
    ]
    assert broker.mutation_calls == []
    assert registry.write_calls == []


def test_p0_canonical_fec1_terminal_emergency_id_is_correlated_with_legacy_compatibility_preserved():
    namespace, _, _ = _main_namespace()
    canonical = _review2_item6_project(
        namespace,
        client_tag="FEC1-" + ("A" * 24),
    )
    legacy = _review2_item6_project(namespace)

    canonical_result = namespace["_fdsff_v1_classify"](
        [canonical], _empty_live(), _review6_incident_query()
    )
    legacy_result = namespace["_fdsff_v1_classify"](
        [legacy], _empty_live(), _review6_incident_query()
    )

    assert canonical["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert canonical_result["terminal_stop_emergency_attempt_found"] is True
    assert canonical_result["terminal_stop_emergency_client_order_id"] == (
        "FEC1-" + ("A" * 24)
    )
    assert legacy["operational_correlation_role"] == "FAILSAFE_CLOSE_AUDIT"
    assert legacy_result["terminal_stop_emergency_attempt_found"] is True
