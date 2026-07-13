from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import predator_audit_observability as observability


ROOT = Path(__file__).resolve().parents[1]


def _events(output):
    records = []
    for line in output.splitlines():
        if not line.startswith("PREDATOR_AUDIT_"):
            continue
        records.append(json.loads(line.split(" ", 1)[1]))
    return records


def test_current_process_rss_is_available_on_supported_host():
    rss = observability.current_rss_mb()
    assert rss is None or rss > 0


def test_probe_and_stage_emit_structured_memory_contract(monkeypatch, capsys):
    values = iter([100.0, 101.0, 104.0, 103.0])
    monkeypatch.setattr(observability, "current_rss_mb", lambda: next(values))

    with observability.predator_audit_probe("audit", limit=10):
        with observability.predator_audit_stage("audit", "load_registry", records_in=2) as stage:
            stage.finish([{"id": 1}, {"id": 2}], records_processed=2, objects_produced=2)

    events = _events(capsys.readouterr().out)
    assert [item["event"] for item in events] == [
        "PREDATOR_AUDIT_BEGIN",
        "PREDATOR_AUDIT_STAGE_BEGIN",
        "PREDATOR_AUDIT_STAGE_END",
        "PREDATOR_AUDIT_END",
    ]
    stage_end = events[2]
    assert events[1]["run_id"] == events[0]["run_id"] == stage_end["run_id"]
    assert stage_end["stage"] == "load_registry"
    assert stage_end["rss_before_mb"] == 101.0
    assert stage_end["rss_after_mb"] == 104.0
    assert stage_end["delta_mb"] == 3.0
    assert stage_end["records_processed"] == 2
    assert stage_end["objects_produced"] == 2
    assert stage_end["object"]["type"] == "list"
    assert events[-1]["delta_mb"] == 3.0


def test_probe_reports_reentry_and_duplicate_call(capsys):
    with observability.predator_audit_probe("same"):
        with observability.predator_audit_probe("same"):
            pass

    begins = [item for item in _events(capsys.readouterr().out) if item["event"] == "PREDATOR_AUDIT_BEGIN"]
    assert len(begins) == 2
    assert begins[0]["reentrant"] is False
    assert begins[1]["reentrant"] is True
    assert begins[1]["duplicate_within_window"] is True
    assert begins[1]["active_before"] == 1
    assert begins[1]["thread"]
    assert begins[1]["caller"]
    assert all("/" not in frame and "\\" not in frame for frame in begins[1]["stack"])


def test_observability_is_fail_open_when_logging_fails(monkeypatch):
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("log unavailable")))

    @observability.observe_predator_audit("fail_open")
    def operation():
        with observability.predator_audit_stage("fail_open", "work") as stage:
            stage.finish({"ok": True})
        return {"official": "unchanged"}

    assert operation() == {"official": "unchanged"}


def test_exception_is_observed_but_not_swallowed(capsys):
    @observability.observe_predator_audit("raises")
    def operation():
        raise RuntimeError("expected")

    with pytest.raises(RuntimeError, match="expected"):
        operation()
    names = [item["event"] for item in _events(capsys.readouterr().out)]
    assert "PREDATOR_AUDIT_ERROR" in names
    assert names[-1] == "PREDATOR_AUDIT_END"


def test_object_estimation_is_bounded_and_contains_no_object_copy():
    payload = [{"value": "x" * 100} for _ in range(5000)]
    result = observability.estimate_object(payload, max_nodes=20, max_items=5)
    assert result["type"] == "list"
    assert result["count"] == 5000
    assert result["nodes_examined"] <= 20
    assert result["partial"] is True
    assert "value" not in json.dumps(result)


def test_helper_creates_no_thread_and_has_no_central_dependencies():
    tree = ast.parse((ROOT / "predator_audit_observability.py").read_text(encoding="utf-8"))
    imports = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
    assert imports.isdisjoint(
        {
            "requests",
            "flask",
            "redis",
            "broker",
            "trade_registry",
            "trade_lifecycle_manager",
            "pandas",
            "numpy",
            "ccxt",
        }
    )
    assert calls.isdisjoint({"Thread", "start", "Popen", "create_order", "send_telegram"})


def test_main_has_complete_predator_audit_stage_inventory_without_importing_main():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    required = {
        "load_registry",
        "load_decision_log",
        "load_history",
        "load_trade_lifecycle",
        "load_registry_full_for_lifecycle_audit",
        "load_broker_logs",
        "aggregate_group_and_filter",
        "group_by_canonical_trade",
        "sort_and_deduplicate_groups",
        "filter_pnl_records",
        "build_payload",
        "build_lifecycle_payload",
        "build_sample_payloads",
        "serialize_latest_payload",
        "serialize_lifecycle_latest",
        "export_event_journal",
        "build_text_report",
        "retain_lifecycle_cache_payload",
    }
    assert required <= {value for value in required if f'"{value}"' in source}
    assert '@observe_predator_audit("predator_source_collection")' in source
    assert '@observe_predator_audit("predator_pnl_paper_audit")' in source
    assert '@observe_predator_audit("predator_paper_lifecycle_audit")' in source
    assert '@observe_predator_audit("predator_registry_sync_audit_pipeline")' in source


def test_static_call_graph_exposes_repeated_cold_source_collection():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "def _ppla_v1_get_closed_paper_events" in source
    assert source.count("_pppa_v1_collect_source_events(limit=limit)") >= 2
    assert "pnl_audit = predator_pnl_paper_audit_v1_status(include_samples=False, limit=limit)" in source
    assert "audit = predator_pnl_paper_audit_v1_status(include_samples=False, limit=600)" in source
    assert "audit = predator_paper_lifecycle_audit_v1_status(include_samples=False, limit=800, use_cache=True)" in source
    assert "before_snapshot = predator_paper_lifecycle_audit_v1_status(include_samples=True, use_cache=False)" in source
    assert "closed_events, closed_source_counts = _ppla_v1_get_closed_paper_events(limit=2000)" in source
    assert "sync = predator_paper_registry_sync_fix_v1_status(commit=False, include_samples=False, use_cache=True)" in source
