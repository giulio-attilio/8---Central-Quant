from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))


def _main_function(name):
    return next(
        node
        for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _compile_main_function(name, namespace):
    module = ast.Module(body=[_main_function(name)], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, f"<decision-log-single-writer-{name}>", "exec"), namespace)
    return namespace[name]


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@pytest.fixture()
def history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "history"))
    original_history_manager = sys.modules.get("history_manager")
    try:
        sys.modules.pop("history_manager", None)
        module = importlib.import_module("history_manager")
        module.HISTORY_EVENTS_FILE = tmp_path / "history_events.jsonl"
        module.DECISION_LOG_FILE = tmp_path / "decision_log.jsonl"
        module.TIMELINE_LOG_FILE = tmp_path / "timeline.jsonl"
        module.HISTORY_SEEN_FILE = tmp_path / "history_seen.json"
        module._PROCESS_SEEN_UIDS.clear()
        monkeypatch.setitem(
            sys.modules,
            "context_manager",
            SimpleNamespace(enrich_event=lambda item: item, CONTEXT_VERSION="test"),
        )
        monkeypatch.setitem(
            sys.modules,
            "journal_manager",
            SimpleNamespace(
                append_lifecycle_event=lambda item: {"ok": True},
                append_journal_trade=lambda item: {"ok": True},
            ),
        )
        yield module
    finally:
        sys.modules.pop("history_manager", None)
        if original_history_manager is not None:
            sys.modules["history_manager"] = original_history_manager


@pytest.fixture()
def original_history_manager_after_history_fixture(request):
    original_history_manager = sys.modules.get("history_manager")

    def assert_original_module_restored():
        assert sys.modules.get("history_manager") is original_history_manager

    request.addfinalizer(assert_original_module_restored)
    return original_history_manager


def _append_decision_log(history):
    namespace = {
        "json": json,
        "Path": Path,
        "time": SimpleNamespace(time=lambda: 123.5),
        "_json_default": str,
        "data_hora_sp_str": lambda: "2026-07-30T12:00:00Z",
        "agora_sp": None,
        "normalize_symbol_for_risk": lambda value: str(value or "").upper(),
        "generate_trade_id": lambda bot, symbol, side: f"{bot}-{symbol}-{side}-GENERATED",
        "_event_trade_id": lambda bot, symbol, side, existing: existing or f"{bot}-{symbol}-{side}",
        "EXECUTION_MODE": "PAPER",
        "CENTRAL_DECISION_LOG_FILE": history.DECISION_LOG_FILE,
        "enrich_decision_result_with_policy_links": lambda result, payload: result,
        "extract_policy_decision_link": lambda result, payload: {
            "policy_codes": [],
            "active_policy_codes": [],
            "dominant_policy_code": None,
        },
        "upsert_shadow_position": lambda item: None,
    }
    namespace["_append_jsonl"] = _compile_main_function("_append_jsonl", namespace)
    namespace["_history_payload_from_event"] = _compile_main_function(
        "_history_payload_from_event", namespace
    )
    namespace["_emit_history_event"] = _compile_main_function("_emit_history_event", namespace)
    namespace["append_timeline_event"] = _compile_main_function(
        "append_timeline_event", namespace
    )
    return _compile_main_function("append_decision_log", namespace)


def _decision(allowed, decision_id):
    return {
        "allowed": allowed,
        "decision": "ALLOW" if allowed else "DENY",
        "bot": "PREDATOR",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "PAPER",
        "reasons": [] if allowed else ["GLOBAL_RISK_LIMIT"],
        "warnings": ["audit-warning"],
        "decision_id": decision_id,
    }


def test_history_fixture_restores_original_module_cache(
    original_history_manager_after_history_fixture, history
):
    assert sys.modules.get("history_manager") is history


@pytest.mark.parametrize(("allowed", "event_type"), [(True, "RISK_ALLOW"), (False, "RISK_DENY")])
def test_untagged_risk_mirror_reaches_the_same_physical_decision_file(history, allowed, event_type):
    """Guarda o diagnostico: sem o marcador, os dois writers usam o mesmo arquivo."""
    main_writer = _append_decision_log(history).__globals__["_append_jsonl"]
    canonical = {
        "decision_id": f"DEC-BASELINE-{event_type}",
        "trade_id": f"TR-BASELINE-{event_type}",
        "bot": "PREDATOR",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "decision": "ALLOW" if allowed else "DENY",
    }
    assert main_writer(history.DECISION_LOG_FILE, canonical) is True
    mirror = history.log_event(event_type, canonical, source="predator", trade_id=canonical["trade_id"])

    assert mirror["decision_log_written"] is True
    assert len(_rows(history.DECISION_LOG_FILE)) == 2


@pytest.mark.parametrize("allowed", [True, False])
def test_can_open_trade_decision_has_one_canonical_physical_write(history, allowed):
    append = _append_decision_log(history)
    decision_id = f"DEC-{'ALLOW' if allowed else 'DENY'}"
    result = _decision(allowed, decision_id)
    payload = {
        "trade_id": f"TR-{decision_id}",
        "decision_id": decision_id,
        "bot": "PREDATOR",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "setup": "SMART_PREDATOR",
    }

    item = append(payload, result)
    decision_rows = _rows(history.DECISION_LOG_FILE)
    history_rows = _rows(history.HISTORY_EVENTS_FILE)

    assert len(decision_rows) == 1
    assert decision_rows[0]["decision_id"] == decision_id
    assert decision_rows[0]["decision"] == ("ALLOW" if allowed else "DENY")
    assert decision_rows[0]["decision_log_single_writer"] is True
    assert decision_rows[0]["canonical_writer"] == "main._append_jsonl"
    assert decision_rows[0]["redundant_mirror_suppressed"] is True
    assert item["decision_id"] == decision_id
    assert result["decision_log_single_writer"] is True
    assert result["canonical_writer"] == "main._append_jsonl"
    assert result["redundant_mirror_suppressed"] is True
    assert len(history_rows) == 1
    assert history_rows[0]["event"] == ("RISK_ALLOW" if allowed else "TRADE_BLOCKED")
    if not allowed:
        assert history_rows[0]["raw"]["event_type"] == "RISK_DENY"
    assert not any(row.get("event") in {"RISK_ALLOW", "RISK_DENY"} for row in decision_rows)


def test_different_decisions_write_and_later_legitimate_shared_identity_events_are_not_deduped(history):
    append = _append_decision_log(history)
    append({"trade_id": "TR-ONE", "decision_id": "DEC-ONE"}, _decision(True, "DEC-ONE"))
    append({"trade_id": "TR-TWO", "decision_id": "DEC-TWO"}, _decision(False, "DEC-TWO"))
    assert [
        row["decision_id"]
        for row in _rows(history.DECISION_LOG_FILE)
        if row.get("decision_id") in {"DEC-ONE", "DEC-TWO"}
    ] == ["DEC-ONE", "DEC-TWO"]

    shared = {
        "decision_id": "DEC-SHARED",
        "trade_id": "TR-SHARED",
        "bot": "PREDATOR",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    first = history.log_event("RISK_ALLOW", {**shared, "event_id": "LATER-ALLOW"}, source="predator")
    second = history.log_event("TRADE_BLOCKED", {**shared, "event_id": "LATER-BLOCK"}, source="predator")

    assert first["dedup"] is False
    assert second["dedup"] is False
    assert first["redundant_mirror_suppressed"] is False
    assert second["redundant_mirror_suppressed"] is False
    assert len(_rows(history.DECISION_LOG_FILE)) == 4


@pytest.mark.parametrize(
    "analytics",
    [
        {"historical_analytics_used": False, "analytics_ranking_status": "STATIC_OPERATIONAL_SKIPPED"},
        {"historical_analytics_used": True, "analytics_ranking_status": "HISTORICAL_ANALYTICS_FALLBACK_CALLED"},
    ],
)
def test_logging_keeps_static_and_normal_risk_authority_unchanged(history, analytics):
    append = _append_decision_log(history)
    original = _decision(False, f"DEC-{analytics['analytics_ranking_status']}")
    original.update(analytics)
    payload = {"trade_id": f"TR-{original['decision_id']}", "decision_id": original["decision_id"]}

    append(payload, original)

    assert original["allowed"] is False
    assert original["decision"] == "DENY"
    assert original["reasons"] == ["GLOBAL_RISK_LIMIT"]
    assert original["historical_analytics_used"] is analytics["historical_analytics_used"]
    assert original["analytics_ranking_status"] == analytics["analytics_ranking_status"]
