from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))


def _load_functions(names: set[str], namespace: dict | None = None) -> dict:
    selected = [
        node
        for node in MAIN_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    found = {node.name for node in selected}
    assert found == names, f"missing functions in main.py: {sorted(names - found)}"
    module = ast.Module(body=sorted(selected, key=lambda node: node.lineno), type_ignores=[])
    values = dict(namespace or {})
    exec(compile(module, str(MAIN), "exec"), values)
    return values


def _valid_divergence(**overrides):
    payload = {
        "ok": True,
        "broker_bingx_open_count": 0,
        "central_live_count": 0,
        "only_bingx_count": 0,
        "only_central_count": 0,
        "live_without_stop_count": 0,
    }
    payload.update(overrides)
    return payload


def _preflight_namespace(divergence):
    return {
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_VERSION": "test-version",
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_LATEST_FILE": "unused-latest.json",
        "FALCON_REAL_PILOT_PREFLIGHT_CHECKLIST_V1_EVENTS_FILE": "unused-events.jsonl",
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-ownership-policy",
        "_frpp_v1_env_snapshot": lambda: {
            "enable_real_trading_bool": False,
            "broker_dry_run_bool": True,
            "central_real_execution_enabled_bool": False,
            "central_real_pilot_enabled_bool": False,
            "falcon_mode": "VERIFY",
        },
        "_frpp_v1_get_bots_snapshot": lambda: {
            "FALCON": {
                "token_configured": True,
                "chat_configured": True,
                "health": {"mode": "VERIFY"},
            },
            "PREDATOR": {
                "health": {
                    "execution_mode": "PAPER",
                    "predator_real_sent_or_live_event_count": 0,
                    "predator_lifecycle_audit_ok": True,
                }
            },
            "TURTLE": {"health": {"mode": "PAPER"}},
        },
        "_frpp_v1_get_falcon_audit": lambda: {
            "ok": True,
            "live_audit_status": "OK",
            "bad_execution_events_total_count": 0,
            "bad_execution_events_acked_count": 0,
            "bad_execution_events_unacked_count": 0,
        },
        "_frpp_v1_get_broker_ready": lambda: {"ready": {"ok": True}, "broker": {}},
        "_frpp_v1_get_divergence": lambda: divergence,
        "_frpp_v1_get_runtime": lambda: {
            "ok": True,
            "status": "OK",
            "current_memory_pct": 10,
            "peak_memory_pct_observed": 20,
            "restart_like_count_24h": 0,
        },
        "_frpp_v1_get_trade_registry_storage": lambda: {
            "status": "OK",
            "registry_file_active": "/data/trade_registry.json",
            "persistent_storage_enabled": True,
            "last_load_ok": True,
            "last_write_ok": True,
            "current_counts": {"open_count": 0, "closed_count": 0},
        },
        "_frpp_v1_get_disaster_preview_status": lambda: {
            "ok": True,
            "long_ok": True,
            "short_ok": True,
        },
        "_frpp_v1_safe_sanitize": lambda value: value,
        "_frpp_v1_now": lambda: "2026-08-29T00:00:00Z",
        "_frpp_v1_write_json_atomic": lambda _path, _payload: (True, None),
        "_frpp_v1_append_event": lambda _payload: (True, None),
    }


def _build_preflight(divergence):
    namespace = _load_functions(
        {
            "_frpp_v1_float",
            "_frpp_v1_int",
            "_frpp_v1_nonnegative_count",
            "_frpp_v1_upper",
            "_frpp_v1_build_checklist",
        },
        _preflight_namespace(divergence),
    )
    return namespace["_frpp_v1_build_checklist"]()


def _check(payload, code):
    return next(item for item in payload["checks"] if item["code"] == code)


@pytest.mark.parametrize(
    "value, expected",
    [
        (0, 0),
        (7, 7),
        ("0", 0),
        (" 12 ", 12),
        (None, None),
        (True, None),
        (False, None),
        (-1, None),
        (0.0, None),
        (0.5, None),
        ("0.0", None),
        ("-1", None),
        ("", None),
        ("zero", None),
    ],
)
def test_preflight_count_evidence_accepts_only_explicit_nonnegative_integers(value, expected):
    namespace = _load_functions({"_frpp_v1_nonnegative_count"})
    assert namespace["_frpp_v1_nonnegative_count"](value) == expected


@pytest.mark.parametrize("missing_key", ["only_central_count", "live_without_stop_count"])
def test_preflight_blocks_when_ownership_evidence_is_missing(missing_key):
    divergence = _valid_divergence()
    divergence.pop(missing_key)

    payload = _build_preflight(divergence)
    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")

    assert payload["ok"] is False
    assert payload["manual_rearm_next_step_allowed"] is False
    assert ownership["ok"] is False
    assert ownership["blocking"] is True
    assert ownership["details"]["evidence_complete"] is False


def test_preflight_blocks_zero_counts_when_divergence_source_failed():
    payload = _build_preflight(_valid_divergence(ok=False, broker_error="unavailable"))

    assert _check(payload, "SYNC_CENTRAL_LIVE_ZERO")["ok"] is False
    assert _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")["ok"] is False
    assert payload["manual_rearm_next_step_allowed"] is False


@pytest.mark.parametrize("bad_value", [True, -1, 0.0, 0.5, "0.0", "-1", "bad"])
def test_preflight_blocks_malformed_ownership_counts(bad_value):
    payload = _build_preflight(_valid_divergence(only_central_count=bad_value))

    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")
    assert ownership["ok"] is False
    assert ownership["details"]["only_central_count"] is None
    assert payload["ok"] is False


def test_preflight_keeps_manual_external_positions_informational():
    payload = _build_preflight(
        _valid_divergence(broker_bingx_open_count=1, only_bingx_count=1)
    )

    manual = _check(payload, "BINGX_MANUAL_POSITIONS_INFORMATIONAL")
    ownership = _check(payload, "SYNC_NO_CENTRAL_OWNERSHIP_DIVERGENCE")
    assert manual["ok"] is True
    assert manual["blocking"] is False
    assert manual["details"]["manual_external_blocks_falcon"] is False
    assert ownership["ok"] is True
    assert payload["ok"] is True


def _divergence_namespace(broker_result, central_result):
    def broker():
        if isinstance(broker_result, BaseException):
            raise broker_result
        return broker_result

    def central():
        if isinstance(central_result, BaseException):
            raise central_result
        return central_result

    return {
        "_broker_open_positions": broker,
        "_central_live_positions_payload": central,
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-policy",
    }


def _run_divergence(broker_result=([], None), central_result=None):
    namespace = _load_functions(
        {
            "_fleag_v1_norm_symbol",
            "_fleag_v1_norm_side",
            "_fleag_v1_divergence_payload",
        },
        _divergence_namespace(broker_result, [] if central_result is None else central_result),
    )
    return namespace["_fleag_v1_divergence_payload"]()


def test_divergence_payload_fails_closed_when_central_source_raises():
    payload = _run_divergence(central_result=RuntimeError("central unavailable"))

    assert payload["ok"] is False
    assert payload["central_error"] == "central unavailable"


def test_divergence_payload_fails_closed_on_invalid_source_shapes():
    broker_invalid = _run_divergence(broker_result=({"not": "a list"}, None))
    central_invalid = _run_divergence(central_result={"not": "a list"})

    assert broker_invalid["ok"] is False
    assert broker_invalid["broker_error"] == "invalid broker open positions payload"
    assert central_invalid["ok"] is False
    assert central_invalid["central_error"] == "invalid central live positions payload"


def test_divergence_payload_preserves_manual_position_isolation_with_valid_sources():
    broker_position = {"symbol": "BTC/USDT:USDT", "side": "LONG", "contracts": 1}
    payload = _run_divergence(broker_result=([broker_position], None), central_result=[])

    assert payload["ok"] is True
    assert payload["only_bingx_count"] == 1
    assert payload["only_central_count"] == 0
    assert payload["manual_external_blocks_falcon"] is False


class _MissingAuditFile:
    @staticmethod
    def exists():
        return False


def test_live_audit_guard_blocks_when_divergence_evidence_is_unavailable():
    namespace = _load_functions(
        {"falcon_live_execution_audit_guard_v1_status"},
        {
            "json": json,
            "FALCON_LIVE_AUDIT_LATEST_FILE": _MissingAuditFile(),
            "FALCON_LIVE_EXECUTION_AUDIT_GUARD_V1_VERSION": "test-version",
            "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "test-policy",
            "_fleag_v1_config": lambda: {"enabled": True, "block_on_previous_failure": True, "block_on_divergence": True},
            "_fleag_v1_load_state": lambda: {},
            "_fleag_v1_read_bad_execution_events": lambda limit=200: [],
            "_fleag_v1_dedup_bad_events_v1_3": lambda _events, _state: {
                "unique_bad_events_unacked": [],
                "unique_bad_events_acked": [],
                "unique_bad_events": [],
                "raw_bad_events_total_count": 0,
                "unique_bad_events_total_count": 0,
                "duplicate_bad_events_removed_count": 0,
                "duplicate_bad_event_groups_count": 0,
                "duplicate_bad_event_samples": [],
            },
            "_fleag_v1_divergence_payload": lambda: {
                "ok": False,
                "broker_error": "unavailable",
                "broker_bingx_open_count": 0,
                "central_live_count": 0,
                "only_bingx_count": 0,
                "only_central_count": 0,
                "live_without_stop_count": 0,
            },
            "_fleag_v1_public": lambda value: value,
            "_fleag_v1_now": lambda: "2026-08-29T00:00:00Z",
            "_fleag_v1_read_events": lambda limit=10: [],
        },
    )

    payload = namespace["falcon_live_execution_audit_guard_v1_status"]()

    assert payload["ok"] is False
    assert payload["live_audit_status"] == "BLOCKED"
    assert any("evidência autoritativa" in reason for reason in payload["reasons"])
