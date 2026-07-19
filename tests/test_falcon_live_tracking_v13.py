from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_SOURCE.read_text(encoding="utf-8"))


def _functions(names: set[str], namespace: dict) -> dict:
    """Load the last definition of selected functions without importing main."""
    selected = {}
    for node in MAIN_TREE.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            selected[node.name] = copy.deepcopy(node)
    missing = names.difference(selected)
    assert not missing, f"missing functions in main.py: {sorted(missing)}"
    nodes = sorted(selected.values(), key=lambda node: node.lineno)
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(MAIN_SOURCE), "exec"), namespace)
    return namespace


def _public(value, **_kwargs):
    return copy.deepcopy(value)


def _event_detail(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "client_order_id": f"CLIENT-{order_id}",
        "review_status": "LIVE_ORDER_REQUIRES_TRACKING",
        "action_required": True,
        "tracking_active": True,
        "reconciliation_required": False,
        "historical_acked": False,
        "bad_stop_event": False,
        "symbol": "SOLUSDT" if order_id.startswith("SOL") else "XRPUSDT",
        "side": "SHORT",
    }


def _build_live_order_detail_payload(audit, detail=None, *, central_only=False, reconciled=False):
    detail = copy.deepcopy(detail or _event_detail("XRP-ENTRY-1"))
    order_id = detail.get("order_id")
    namespace = {
        "falcon_live_execution_audit_guard_v1_status": lambda **_kwargs: copy.deepcopy(audit),
        "_flad_v1_read_falcon_live_order_events": lambda limit=100: [{"order_id": order_id}],
        "_flad_v1_build_event_detail": lambda _event, **_kwargs: copy.deepcopy(detail),
        "_live_v12_reconciled_closed_order_index": lambda: {
            "order_ids": {order_id} if reconciled else set(),
            "client_order_ids": set(),
        },
        "_flad_v1_central_only_identity_index": lambda: {
            "order_ids": {order_id} if central_only else set(),
            "client_order_ids": set(),
            "rows": [],
        },
        "_flad_v1_detail_is_central_only": lambda row, index: row.get("order_id") in index.get("order_ids", set()),
        "_live_v12_detail_is_reconciled_completed": lambda row, index: row.get("order_id") in index.get("order_ids", set()),
        "_flad_v1_now": lambda: "2026-07-19T00:00:00Z",
        "_flad_v1_public": _public,
        "_flad_v1_write_snapshot": lambda *_args, **_kwargs: None,
        "_flad_v1_append_event": lambda *_args, **_kwargs: None,
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_VERSION": "V1.1-TEST",
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_LATEST_FILE": Path("unused-latest.json"),
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_EVENTS_FILE": Path("unused-events.jsonl"),
    }
    _functions({"_flad_v1_build_payload"}, namespace)
    return namespace["_flad_v1_build_payload"]()


def test_managed_close_confirmed_is_management_history_not_active_tracking():
    namespace = {
        "_flad_v1_event_status": lambda event: str(event.get("status") or "").upper(),
        "_flad_v1_is_bad_stop_event": lambda _event: False,
        "_flad_v1_bad_event_acked": lambda *_args, **_kwargs: False,
        "_flad_v1_disaster_stop_detail": lambda _event: {},
        "_flad_v1_event_order_id": lambda event: event.get("order_id"),
        "_flad_v1_event_client_id": lambda event: event.get("client_order_id"),
        "_flad_v1_norm_symbol": lambda value: str(value or "").replace("/", "").replace(":USDT", ""),
        "_flad_v1_deep_find": lambda event, keys: next((event.get(key) for key in keys if event.get(key) is not None), None),
        "_flad_v1_norm_side": lambda value: str(value or "").upper(),
        "_flad_v1_event_key": lambda event: f"ORDER|{event.get('order_id')}",
        "_flad_v1_infer_bot": lambda _event: "FALCON",
        "_flad_v1_public": _public,
        "_flad_v1_upper": lambda value: str(value or "").upper(),
    }
    _functions(
        {"_flad_v1_is_managed_close_confirmed", "_flad_v1_build_event_detail"},
        namespace,
    )
    event = {
        "event": "MANAGED_CLOSE_CONFIRMED",
        "status": "MANAGED_CLOSE_CONFIRMED",
        "sent": True,
        "order_id": "CLOSE-1",
        "client_order_id": "CLIENT-CLOSE-1",
        "symbol": "XRP/USDT:USDT",
        "side": "sell",
    }

    detail = namespace["_flad_v1_build_event_detail"](event, audit_payload={"ok": True})

    assert detail["management_event"] is True
    assert detail["review_status"] == "HISTORICAL_MANAGEMENT_CONFIRMED"
    assert detail["tracking_active"] is False
    assert detail["action_required"] is False
    assert detail["reconciliation_required"] is False


def test_event_dedup_key_preserves_terminal_event_for_the_same_order():
    namespace = {
        "_flad_v1_upper": lambda value: str(value or "").upper(),
        "_flad_v1_event_status": lambda event: event.get("status"),
        "_flad_v1_event_order_id": lambda event: event.get("order_id"),
        "_flad_v1_event_client_id": lambda event: event.get("client_order_id"),
        "_flad_v1_public": _public,
        "json": __import__("json"),
    }
    _functions({"_flad_v1_event_key"}, namespace)

    sent = namespace["_flad_v1_event_key"]({"order_id": "ORDER-1", "status": "SENT"})
    closed = namespace["_flad_v1_event_key"]({"order_id": "ORDER-1", "status": "MANAGED_CLOSE_CONFIRMED"})

    assert sent == "ORDER|ORDER-1|SENT"
    assert closed == "ORDER|ORDER-1|MANAGED_CLOSE_CONFIRMED"
    assert sent != closed


class _Registry:
    def __init__(self, closed_trades):
        self.closed_trades = closed_trades

    def load_registry(self):
        return {"open_trades": {}, "closed_trades": copy.deepcopy(self.closed_trades)}


def test_sol_closed_real_with_strong_identity_is_historical_completed():
    registry = _Registry(
        [
            {
                "trade_id": "TR-SOL",
                "bot": "FALCON",
                "symbol": "SOLUSDT",
                "side": "SHORT",
                "status": "CLOSED",
                "registry_mode": "REAL",
                "entry_order_id": "SOL-ENTRY-1",
                "client_order_id": "SOL-CLIENT-1",
                "closed_at": "2026-07-14T12:00:00Z",
                "close_reason": "MANAGED_CLOSE_CONFIRMED",
                "real_close_reconciled": True,
            },
            {
                "trade_id": "TR-WITHOUT-IDENTITY",
                "status": "CLOSED",
                "registry_mode": "REAL",
                "closed_at": "2026-07-14T12:01:00Z",
                "close_reason": "CLOSED",
            },
            {
                "trade_id": "TR-PAPER",
                "status": "CLOSED",
                "registry_mode": "PAPER",
                "order_id": "PAPER-1",
                "closed_at": "2026-07-14T12:02:00Z",
                "close_reason": "CLOSED",
            },
        ]
    )
    namespace = {
        "central_trade_registry": registry,
        "_flad_v1_norm_symbol": lambda value: str(value or "").replace("/", "").replace(":USDT", "").upper(),
        "_flad_v1_norm_side": lambda value: str(value or "").upper(),
    }
    _functions(
        {"_live_v12_reconciled_closed_order_index", "_live_v12_detail_is_reconciled_completed"},
        namespace,
    )

    index = namespace["_live_v12_reconciled_closed_order_index"]()

    assert index["order_ids"] == {"SOL-ENTRY-1"}
    assert index["client_order_ids"] == {"sol-client-1"}
    assert index["trade_ids"] == {"TR-SOL"}
    assert namespace["_live_v12_detail_is_reconciled_completed"](
        {"order_id": "SOL-ENTRY-1", "client_order_id": None, "bad_stop_event": False, "symbol": "SOLUSDT", "side": "SHORT"},
        index,
    ) is True
    assert namespace["_live_v12_detail_is_reconciled_completed"](
        {"order_id": None, "client_order_id": "SOL-CLIENT-1", "bad_stop_event": False, "symbol": "SOLUSDT", "side": "SHORT"},
        index,
    ) is True
    assert namespace["_live_v12_detail_is_reconciled_completed"](
        {"order_id": "SOL-ENTRY-1", "client_order_id": None, "bad_stop_event": False, "symbol": "XRPUSDT", "side": "SHORT"},
        index,
    ) is False


def test_order_detail_separates_xrp_central_only_from_tracking_and_clears_after_reconcile():
    audit = {
        "ok": True,
        "live_audit_status": "OK",
        "state": {},
        "divergence": {
            "broker_bingx_open_count": 0,
            "central_live_count": 1,
            "only_bingx_count": 0,
            "only_central_count": 1,
            "live_without_stop_count": 0,
        },
    }
    events = [
        {"order_id": "SOL-ENTRY-1", "client_order_id": "SOL-CLIENT-1"},
        {"order_id": "XRP-ENTRY-1", "client_order_id": "XRP-CLIENT-1"},
    ]
    namespace = {
        "falcon_live_execution_audit_guard_v1_status": lambda **_kwargs: copy.deepcopy(audit),
        "_flad_v1_read_falcon_live_order_events": lambda limit=100: copy.deepcopy(events),
        "_flad_v1_build_event_detail": lambda event, **_kwargs: _event_detail(event["order_id"]),
        "_live_v12_reconciled_closed_order_index": lambda: {
            "order_ids": {"SOL-ENTRY-1"},
            "client_order_ids": {"sol-client-1"},
        },
        "_flad_v1_central_only_identity_index": lambda: {
            "order_ids": {"XRP-ENTRY-1"},
            "client_order_ids": {"xrp-client-1"},
        },
        "_flad_v1_detail_is_central_only": lambda detail, index: detail.get("order_id") in index.get("order_ids", set()),
        "_live_v12_detail_is_reconciled_completed": lambda detail, index: detail.get("order_id") in index.get("order_ids", set()),
        "_flad_v1_now": lambda: "2026-07-15T00:00:00Z",
        "_flad_v1_public": _public,
        "_flad_v1_write_snapshot": lambda *_args, **_kwargs: None,
        "_flad_v1_append_event": lambda *_args, **_kwargs: None,
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_VERSION": "V1.3-TEST",
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_LATEST_FILE": Path("unused-latest.json"),
        "FALCON_LIVE_ORDER_AUDIT_DETAIL_V1_EVENTS_FILE": Path("unused-events.jsonl"),
    }
    _functions({"_flad_v1_build_payload"}, namespace)

    before = namespace["_flad_v1_build_payload"]()

    assert before["status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert before["summary"]["active_or_tracking_orders"] == 0
    assert before["summary"]["central_only_pending_reconcile_orders"] == 1
    by_order = {row["order_id"]: row for row in before["orders"]}
    assert by_order["SOL-ENTRY-1"]["review_status"] == "HISTORICAL_COMPLETED_OR_CLOSED"
    assert by_order["SOL-ENTRY-1"]["tracking_active"] is False
    assert by_order["XRP-ENTRY-1"]["review_status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert by_order["XRP-ENTRY-1"]["reconciliation_required"] is True
    assert by_order["XRP-ENTRY-1"]["tracking_active"] is False

    namespace["_flad_v1_central_only_identity_index"] = lambda: {
        "order_ids": set(),
        "client_order_ids": set(),
    }
    namespace["_live_v12_reconciled_closed_order_index"] = lambda: {
        "order_ids": {"SOL-ENTRY-1", "XRP-ENTRY-1"},
        "client_order_ids": {"sol-client-1", "xrp-client-1"},
    }
    after = namespace["_flad_v1_build_payload"]()

    assert after["summary"]["active_or_tracking_orders"] == 0
    assert after["summary"]["central_only_pending_reconcile_orders"] == 0
    assert all(row["review_status"] == "HISTORICAL_COMPLETED_OR_CLOSED" for row in after["orders"])


def test_xrp_like_live_sent_is_historical_when_central_audit_is_flat():
    audit = {
        "ok": True,
        "live_audit_status": "OK_ACKED_HISTORY_CLEAR",
        "state": {},
        "divergence": {
            "broker_bingx_open_count": 2,
            "central_live_count": 0,
            "only_bingx_count": 2,
            "only_central_count": 0,
            "live_without_stop_count": 0,
        },
    }
    detail = {
        **_event_detail("2078483751332171776"),
        "client_order_id": "FALCON-XRP-LONG-1",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "LIVE_SENT",
        "disaster_stop": {"status": "CLOSED", "created": True, "failed": False},
    }

    payload = _build_live_order_detail_payload(audit, detail)

    assert payload["status"] == "OK_HISTORICAL_COMPLETED_OR_CLOSED"
    assert payload["summary"]["active_or_tracking_orders"] == 0
    assert payload["summary"]["historical_completed_or_closed_orders"] == 1
    row = payload["orders"][0]
    assert row["review_status"] == "HISTORICAL_COMPLETED_OR_CLOSED"
    assert row["tracking_active"] is False
    assert row["action_required"] is False
    assert row["completed_by_flat_central_audit"] is True
    assert row["order_id"] == "2078483751332171776"
    assert row["client_order_id"] == "FALCON-XRP-LONG-1"
    assert row["symbol"] == "XRPUSDT" and row["side"] == "LONG"
    assert row["disaster_stop"] == {"status": "CLOSED", "created": True, "failed": False}
    assert payload["no_order_sent_by_this_route"] is True
    assert payload["sent"] is False
    assert payload["would_send_order"] is False
    assert payload["broker_called"] is False


def test_live_order_remains_tracking_when_central_position_is_open():
    audit = {
        "ok": True,
        "live_audit_status": "OK",
        "state": {},
        "divergence": {
            "central_live_count": 1,
            "only_central_count": 0,
            "live_without_stop_count": 0,
        },
    }

    payload = _build_live_order_detail_payload(audit)

    assert payload["status"] == "LIVE_ORDER_TRACKING_REQUIRED"
    assert payload["orders"][0]["review_status"] == "LIVE_ORDER_REQUIRES_TRACKING"
    assert payload["orders"][0]["tracking_active"] is True


def test_unknown_or_non_integer_counts_do_not_prove_flat_state():
    audit = {
        "ok": True,
        "live_audit_status": "OK",
        "state": {},
        "divergence": {
            "central_live_count": None,
            "only_central_count": "0",
            "live_without_stop_count": False,
        },
    }

    payload = _build_live_order_detail_payload(audit)

    assert payload["status"] == "LIVE_ORDER_TRACKING_REQUIRED"
    assert "completed_by_flat_central_audit" not in payload["orders"][0]


def test_live_without_stop_never_receives_flat_historical_reclassification():
    audit = {
        "ok": True,
        "live_audit_status": "OK",
        "state": {},
        "divergence": {
            "central_live_count": 0,
            "only_central_count": 0,
            "live_without_stop_count": 1,
        },
    }

    payload = _build_live_order_detail_payload(audit)

    assert payload["status"] == "LIVE_ORDER_TRACKING_REQUIRED"
    assert payload["orders"][0]["tracking_active"] is True


def test_unacked_failure_and_non_ok_audit_keep_blocking_precedence():
    flat = {
        "central_live_count": 0,
        "only_central_count": 0,
        "live_without_stop_count": 0,
    }
    failure = {
        **_event_detail("FAILED-1"),
        "review_status": "LIVE_FAILURE_REQUIRES_REVIEW",
        "tracking_active": False,
        "bad_stop_event": True,
        "historical_acked": False,
    }
    unacked = _build_live_order_detail_payload(
        {"ok": True, "live_audit_status": "OK", "state": {}, "divergence": flat},
        failure,
    )
    divergent = _build_live_order_detail_payload(
        {"ok": False, "live_audit_status": "BLOCKED", "state": {}, "divergence": flat},
    )

    assert unacked["status"] == "BLOCKED_UNACKED_LIVE_FAILURE"
    assert unacked["orders"][0]["review_status"] == "LIVE_FAILURE_REQUIRES_REVIEW"
    assert divergent["status"] == "BLOCKED_BY_FALCON_AUDIT"
    assert divergent["orders"][0]["review_status"] == "LIVE_ORDER_REQUIRES_TRACKING"


def test_historical_acked_failure_keeps_existing_classification():
    acked = {
        **_event_detail("ACKED-1"),
        "review_status": "HISTORICAL_ACKED_FAILURE",
        "tracking_active": False,
        "action_required": False,
        "bad_stop_event": True,
        "historical_acked": True,
    }
    payload = _build_live_order_detail_payload(
        {
            "ok": True,
            "live_audit_status": "OK_ACKED_HISTORY_CLEAR",
            "state": {},
            "divergence": {
                "central_live_count": 0,
                "only_central_count": 0,
                "live_without_stop_count": 0,
            },
        },
        acked,
    )

    assert payload["status"] == "OK_HISTORICAL_ACKED_ONLY"
    assert payload["orders"][0]["review_status"] == "HISTORICAL_ACKED_FAILURE"


def test_falcon_audit_clears_only_after_factual_central_only_divergence_disappears(tmp_path):
    central_positions = [{"bot": "FALCON", "symbol": "XRPUSDT", "side": "SHORT", "stop": 1.1294}]
    acknowledged_bad = {"order_id": "HISTORICAL-FAILED", "status": "DISASTER_STOP_FAILED"}
    dedup = {
        "unique_bad_events_unacked": [],
        "unique_bad_events_acked": [acknowledged_bad],
        "unique_bad_events": [acknowledged_bad],
        "raw_bad_events_total_count": 1,
        "unique_bad_events_total_count": 1,
        "duplicate_bad_events_removed_count": 0,
        "duplicate_bad_event_groups_count": 0,
        "duplicate_bad_event_samples": [],
    }
    namespace = {
        "_broker_open_positions": lambda: ([], None),
        "_central_live_positions_payload": lambda: copy.deepcopy(central_positions),
        "_fleag_v1_norm_symbol": lambda value: str(value or "").replace("/", "").replace(":USDT", "").upper(),
        "_fleag_v1_norm_side": lambda value: str(value or "").upper(),
        "_fleag_v1_config": lambda: {"enabled": True, "block_on_previous_failure": True, "block_on_divergence": True},
        "_fleag_v1_load_state": lambda: {"acked_bad_event_keys": ["HISTORICAL-FAILED"]},
        "_fleag_v1_read_bad_execution_events": lambda limit=200: [acknowledged_bad],
        "_fleag_v1_dedup_bad_events_v1_3": lambda *_args, **_kwargs: copy.deepcopy(dedup),
        "_fleag_v1_public": _public,
        "_fleag_v1_now": lambda: "2026-07-15T00:00:00Z",
        "_fleag_v1_read_events": lambda limit=10: [],
        "FALCON_LIVE_AUDIT_LATEST_FILE": tmp_path / "does-not-exist.json",
        "FALCON_LIVE_EXECUTION_AUDIT_GUARD_V1_VERSION": "TEST-AUDIT",
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "TEST-OWNERSHIP",
        "json": json,
    }
    _functions({"_fleag_v1_divergence_payload", "falcon_live_execution_audit_guard_v1_status"}, namespace)

    before = namespace["falcon_live_execution_audit_guard_v1_status"](include_recent=False)
    central_positions.clear()
    after = namespace["falcon_live_execution_audit_guard_v1_status"](include_recent=False)

    assert before["live_audit_status"] == "BLOCKED"
    assert before["ok"] is False
    assert before["divergence"]["only_central_count"] == 1
    assert after["live_audit_status"] == "OK_ACKED_HISTORY_CLEAR"
    assert after["ack_recheck_status"] == "CLEAR"
    assert after["ok"] is True
    assert after["divergence"]["only_central_count"] == 0


def test_live_classes_keep_management_completed_and_central_only_in_separate_counters():
    details = {
        "SOL-ENTRY-1": {
            "order_id": "SOL-ENTRY-1",
            "review_status": "HISTORICAL_COMPLETED_OR_CLOSED",
            "action_required": False,
        },
        "XRP-ENTRY-1": {
            "order_id": "XRP-ENTRY-1",
            "review_status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
            "action_required": True,
            "reconciliation_required": True,
        },
    }
    namespace = {
        "_live_v11_classify_event": lambda _event: {},
        "_flad_v1_is_live_sent": lambda event: event.get("sent") is True,
        "_flad_v1_is_bad_stop_event": lambda _event: False,
        "_flad_v1_is_managed_close_confirmed": lambda event: event.get("status") == "MANAGED_CLOSE_CONFIRMED",
        "_flad_v1_bad_event_acked": lambda *_args, **_kwargs: False,
        "_live_v12_order_detail_match": lambda event, **_kwargs: details.get(event.get("order_id")),
        "_flad_v1_infer_bot": lambda _event: "FALCON",
    }
    _functions({"_live_v12_classify_event", "_live_v12_summarize_classes"}, namespace)
    events = [
        {"sent": True, "status": "SENT", "order_id": "SOL-ENTRY-1"},
        {"sent": True, "status": "SENT", "order_id": "XRP-ENTRY-1"},
        {"sent": True, "status": "MANAGED_CLOSE_CONFIRMED", "order_id": "XRP-CLOSE-1"},
    ]

    classes = [namespace["_live_v12_classify_event"](event, order_detail={"orders": []}) for event in events]
    summary = namespace["_live_v12_summarize_classes"](events, order_detail={"orders": []})

    assert [item["class_code"] for item in classes] == [
        "LIVE_SENT_COMPLETED_HISTORY",
        "LIVE_SENT_CENTRAL_ONLY_RECONCILE",
        "LIVE_MANAGEMENT_CONFIRMED_HISTORY",
    ]
    assert classes[0]["tracking_active"] is False and classes[0]["safe"] is True
    assert classes[1]["tracking_active"] is False and classes[1]["reconciliation_required"] is True
    assert classes[2]["tracking_active"] is False and classes[2]["management_event"] is True
    assert summary == {
        "LIVE_SENT_COMPLETED_HISTORY": 1,
        "LIVE_SENT_CENTRAL_ONLY_RECONCILE": 1,
        "LIVE_MANAGEMENT_CONFIRMED_HISTORY": 1,
    }


def test_central_live_payload_preserves_exact_ids_quantity_and_broker_flat_evidence():
    evidence = {
        "status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
        "broker_flat": True,
        "read_only": True,
        "sent": False,
        "matched_count": 0,
        "checked_at": "2026-07-15T01:00:00Z",
        "order_id": "XRP-ENTRY-1",
        "client_order_id": "XRP-CLIENT-1",
        "trade_id": "TR-XRP",
    }
    position = {
        "id": "POS-XRP",
        "trade_registry_id": "TR-XRP",
        "lifecycle_id": "LC-XRP",
        "symbol": "XRP/USDT:USDT",
        "side": "LONG",
        "setup": "FALCON15",
        "entry": 2.5,
        "stop": 2.4,
        "tp50": 2.7,
        "live_order_id": "XRP-ENTRY-1",
        "live_client_order_id": "XRP-CLIENT-1",
        "remaining_qty": 8.0,
        "execution_mode": "LIVE",
        "registry_mode": "REAL",
        "central_only_reconcile_required": True,
        "central_only_evidence": evidence,
    }
    namespace = {
        "LOADED_BOTS": {"FALCON": SimpleNamespace()},
        "get_open_positions_from_module": lambda _module: [copy.deepcopy(position)],
        "normalize_symbol_for_risk": lambda value: str(value).replace("/", "").replace(":USDT", ""),
        "_flad_v1_public": _public,
    }
    _functions({"_central_live_positions_payload"}, namespace)

    rows = namespace["_central_live_positions_payload"]()

    assert len(rows) == 1
    row = rows[0]
    assert row["position_id"] == "POS-XRP"
    assert row["trade_id"] == "TR-XRP"
    assert row["lifecycle_id"] == "LC-XRP"
    assert row["order_id"] == "XRP-ENTRY-1"
    assert row["client_order_id"] == "XRP-CLIENT-1"
    assert row["quantity"] == 8.0
    assert row["central_only_reconcile_required"] is True
    assert row["central_only_evidence"] == evidence
    assert row["central_only_evidence"] is not evidence


def test_falcon_health_overlay_exposes_all_20_reconciliation_stop_spam_and_projection_fields():
    stop_and_spam = {
        "falcon_disaster_stop_active_verified": True,
        "falcon_disaster_stop_trigger_type": "MARK_PRICE",
        "falcon_disaster_stop_order_status": "OPEN",
        "falcon_disaster_stop_order_id": "STOP-1",
        "falcon_disaster_stop_last_checked_at": "2026-07-15T01:00:00Z",
        "falcon_disaster_stop_protection_matches_position": True,
        "falcon_stop_anomaly_detected": False,
        "falcon_stop_anomaly_last_reason": None,
        "falcon_management_spam_guard_status": "CLEAR",
        "falcon_management_spam_guard_last_reason": None,
        "falcon_management_spam_guard_suppressed_count": 2,
        "falcon_management_spam_guard_last_suppressed_at": "2026-07-15T00:59:00Z",
        "falcon_manual_close_outcome_projection_pending": False,
        "falcon_manual_close_outcome_projection_status": "PROJECTED",
        "falcon_manual_close_outcome_last_outcome_id": "OUTCOME-1",
    }
    namespace = {
        "_fcor_v1_raw_positions": lambda: ([
            ("POS-XRP", {"central_only_reconcile_required": True})
        ], None),
        "_fcor_v1_falcon_module": lambda: SimpleNamespace(HEALTH=copy.deepcopy(stop_and_spam)),
        "_FCOR_V1_STATE": {
            "status": "NOT_RUN",
            "last_run": None,
            "last_error": None,
            "last_reconciled_count": 0,
        },
    }
    _functions({"_fcor_v1_health_overlay"}, namespace)

    overlay = namespace["_fcor_v1_health_overlay"]()
    expected = {
        "falcon_central_only_reconcile_status",
        "falcon_central_only_pending_count",
        "falcon_central_only_last_run",
        "falcon_central_only_last_error",
        "falcon_central_only_last_reconciled_count",
        *stop_and_spam.keys(),
    }

    assert len(expected) == 20
    assert set(overlay) == expected
    assert overlay["falcon_central_only_reconcile_status"] == "CENTRAL_ONLY_RECONCILE_REQUIRED"
    assert overlay["falcon_central_only_pending_count"] == 1
    assert overlay["falcon_disaster_stop_order_id"] == "STOP-1"
    assert overlay["falcon_management_spam_guard_suppressed_count"] == 2


def test_bots_falcon_health_promotes_same_overlay_at_top_level_and_nested_health():
    overlay = {f"falcon_field_{index}": index for index in range(17)}
    namespace = {
        "_TRPSF_V1_ORIGINAL_BOT_HEALTH": lambda key, cfg: {
            "name": cfg.get("name"),
            "health": {"existing": True},
        },
        "trade_registry_persistent_storage_fix_v1_status": lambda force=False: {
            "status": "OK",
            "ok": True,
            "registry_file_active": "registry.json",
            "persistent_storage_enabled": True,
            "last_write_ok": True,
        },
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "TEST",
        "_fcor_v1_health_overlay": lambda: copy.deepcopy(overlay),
    }
    _functions({"bot_health"}, namespace)

    payload = namespace["bot_health"]("FALCON", {"name": "Falcon"})

    assert payload["health"]["existing"] is True
    for key, value in overlay.items():
        assert payload[key] == value
        assert payload["health"][key] == value
