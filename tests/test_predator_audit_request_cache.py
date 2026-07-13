from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from flask import Flask

from predator_audit_request_cache import request_cached_predator_audit


ROOT = Path(__file__).resolve().parents[1]


def _cache_events(output):
    records = []
    for line in output.splitlines():
        if not line.startswith("REQUEST_CACHE_"):
            continue
        event, payload = line.split(" ", 1)
        row = json.loads(payload)
        row["event"] = event
        records.append(row)
    return records


@pytest.fixture()
def app():
    return Flask(__name__)


def test_each_predator_audit_executes_once_per_request(app, capsys):
    calls = {
        "predator_source_collection": 0,
        "predator_pnl_paper_audit": 0,
        "predator_paper_lifecycle_audit": 0,
        "predator_registry_sync_audit_pipeline": 0,
    }
    functions = {}
    for audit in calls:
        def operation(value=None, _audit=audit):
            calls[_audit] += 1
            return {"audit": _audit, "first_value": value}

        functions[audit] = request_cached_predator_audit(audit)(operation)

    with app.test_request_context("/health"):
        for audit, function in functions.items():
            first = function("first")
            second = function("second")
            assert second is first
            assert second["first_value"] == "first"

    assert calls == {audit: 1 for audit in calls}
    events = _cache_events(capsys.readouterr().out)
    for audit in calls:
        audit_events = [row for row in events if row["audit"] == audit]
        assert [row["event"] for row in audit_events] == [
            "REQUEST_CACHE_MISS",
            "REQUEST_CACHE_STORE",
            "REQUEST_CACHE_HIT",
        ]
        assert len({row["request_id"] for row in audit_events}) == 1
        assert all(set(row) == {"event", "request_id", "audit", "caller"} for row in audit_events)


def test_nested_health_lifecycle_and_sync_graph_computes_each_audit_once(app):
    calls = {"source": 0, "pnl": 0, "lifecycle": 0, "sync": 0}

    @request_cached_predator_audit("predator_source_collection")
    def source_collection():
        calls["source"] += 1
        return ["events"]

    @request_cached_predator_audit("predator_pnl_paper_audit")
    def pnl_audit():
        calls["pnl"] += 1
        return {"events": source_collection()}

    @request_cached_predator_audit("predator_paper_lifecycle_audit")
    def lifecycle_audit():
        calls["lifecycle"] += 1
        return {"events": source_collection(), "pnl": pnl_audit()}

    @request_cached_predator_audit("predator_registry_sync_audit_pipeline")
    def registry_sync_audit():
        calls["sync"] += 1
        return {"lifecycle": lifecycle_audit(), "events": source_collection()}

    with app.test_request_context("/health"):
        pnl_audit()
        lifecycle_audit()
        registry_sync_audit()
        lifecycle_audit()

    assert calls == {"source": 1, "pnl": 1, "lifecycle": 1, "sync": 1}


def test_cache_does_not_survive_between_requests(app):
    calls = {"count": 0}

    @request_cached_predator_audit("predator_pnl_paper_audit")
    def operation():
        calls["count"] += 1
        return {"execution": calls["count"]}

    with app.test_request_context("/one"):
        first = operation()
        assert operation() is first
    with app.test_request_context("/two"):
        second = operation()
        assert operation() is second

    assert calls["count"] == 2
    assert first is not second


def test_outside_http_request_no_cache_is_applied():
    calls = {"count": 0}

    @request_cached_predator_audit("predator_source_collection")
    def operation():
        calls["count"] += 1
        return calls["count"]

    assert operation() == 1
    assert operation() == 2


def test_ephemeral_watchdog_app_context_caches_only_one_cycle(app):
    calls = {"count": 0}

    @request_cached_predator_audit("predator_pnl_paper_audit")
    def operation():
        calls["count"] += 1
        return calls["count"]

    with app.app_context():
        assert operation() == operation() == 1
    with app.app_context():
        assert operation() == operation() == 2
    assert calls["count"] == 2


def test_failure_is_not_cached_and_original_exception_is_preserved(app):
    calls = {"count": 0}

    @request_cached_predator_audit("predator_paper_lifecycle_audit")
    def operation():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("audit failed")
        return {"ok": True}

    with app.test_request_context("/health"):
        with pytest.raises(RuntimeError, match="audit failed"):
            operation()
        assert operation() == {"ok": True}
        assert operation() == {"ok": True}
    assert calls["count"] == 2


def test_helper_has_no_global_result_cache_or_persistence_calls():
    source = (ROOT / "predator_audit_request_cache.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned_module_names = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert assigned_module_names <= {"__all__"}
    assert calls.isdisjoint({"open", "write", "write_text", "set", "save", "rpush", "lpush"})
    assert "Redis" not in source
    assert "ContextVar" not in source


def test_main_applies_request_cache_to_exactly_four_predator_audits():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    audits = [
        "predator_source_collection",
        "predator_pnl_paper_audit",
        "predator_paper_lifecycle_audit",
        "predator_registry_sync_audit_pipeline",
    ]
    for audit in audits:
        assert source.count(f'@request_cached_predator_audit("{audit}")') == 1
    assert "_PREDATOR_PAPER_LIFECYCLE_AUDIT_V1_CACHE" not in source
    assert "_PREDATOR_PAPER_REGISTRY_SYNC_FIX_V1_CACHE" not in source
    assert "with app.app_context():\n                status = central_watchdog_status()" in source


def test_static_composite_graph_uses_one_shared_request_limit():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    required_edges = [
        "pnl_audit = predator_pnl_paper_audit_v1_status(include_samples=False, limit=limit)",
        "sync = predator_paper_registry_sync_fix_v1_status(commit=False, include_samples=False, use_cache=True)",
        "before_snapshot = predator_paper_lifecycle_audit_v1_status(",
        "closed_events, closed_source_counts = _ppla_v1_get_closed_paper_events(limit=2000)",
    ]
    assert all(edge in source for edge in required_edges)
    assert 'PREDATOR_AUDIT_REQUEST_SHARED_LIMIT = 2000' in source
    assert source.count("limit=PREDATOR_AUDIT_REQUEST_SHARED_LIMIT") >= 3


def test_execution_count_contract_before_and_after_request_cache():
    before = {
        "predator_source_collection": 6,
        "predator_pnl_paper_audit": 3,
        "predator_paper_lifecycle_audit": 2,
        "predator_registry_sync_audit_pipeline": 1,
    }
    after = {audit: 1 for audit in before}
    assert before == {
        "predator_source_collection": 6,
        "predator_pnl_paper_audit": 3,
        "predator_paper_lifecycle_audit": 2,
        "predator_registry_sync_audit_pipeline": 1,
    }
    assert after == {audit: 1 for audit in before}
