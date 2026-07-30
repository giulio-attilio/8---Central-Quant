from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _function_nodes(*names: str):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in selected} == set(names)
    return selected


def _load_functions(names: set[str], namespace: dict):
    nodes = _function_nodes(*names)
    for node in nodes:
        node.decorator_list = []
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "main.py", "exec"), namespace)
    return namespace


class _PolicyManager:
    def __init__(self, active_count=0):
        self.active_count = active_count
        self.health_calls = 0

    def build_policy_health(self):
        self.health_calls += 1
        return {
            "active_policy_count": self.active_count,
            "active_codes": ["BLOCK_ALL"] if self.active_count else [],
        }


def test_static_risk_gate_skips_executive_history_snapshot_and_returns_neutral_state():
    snapshot_calls = []
    namespace = {
        "static_operational_runtime_enabled": lambda: True,
        "EXECUTIVE_POLICY_MANAGER_LOADED": True,
        "EXECUTIVE_POLICY_MANAGER_ERROR": None,
        "executive_policy_manager": _PolicyManager(active_count=0),
        "_executive_decision_snapshot_for_reports": lambda **kwargs: snapshot_calls.append(
            kwargs
        ),
    }
    _load_functions(
        {
            "_static_risk_analytics_gate_payload",
            "_ensure_executive_policy_manager_synced_for_risk",
        },
        namespace,
    )

    result = namespace["_ensure_executive_policy_manager_synced_for_risk"]()

    assert snapshot_calls == []
    assert result["historical_analytics_used"] is False
    assert result["analytics_ranking_status"] == "STATIC_OPERATIONAL_SKIPPED"
    assert result["analytics_ranking"] == {
        "state": "NEUTRAL",
        "reason": "STATIC_OPERATIONAL_RUNTIME",
    }
    assert result["reason"] == "STATIC_OPERATIONAL_HISTORICAL_ANALYTICS_SKIPPED"
    assert result["attempted"] is False
    assert result["ok"] is True


def test_static_risk_gate_keeps_existing_active_policies_without_history_snapshot():
    snapshot_calls = []
    namespace = {
        "static_operational_runtime_enabled": lambda: True,
        "EXECUTIVE_POLICY_MANAGER_LOADED": True,
        "EXECUTIVE_POLICY_MANAGER_ERROR": None,
        "executive_policy_manager": _PolicyManager(active_count=1),
        "_executive_decision_snapshot_for_reports": lambda **kwargs: snapshot_calls.append(kwargs),
    }
    _load_functions({"_static_risk_analytics_gate_payload", "_ensure_executive_policy_manager_synced_for_risk"}, namespace)

    result = namespace["_ensure_executive_policy_manager_synced_for_risk"]()

    assert snapshot_calls == []
    assert result["ok"] is True
    assert result["active_codes"] == ["BLOCK_ALL"]
    assert result["analytics_ranking_status"] == "STATIC_OPERATIONAL_SKIPPED"


def test_normal_risk_gate_calls_history_fallback_when_no_policies_are_active():
    snapshot_calls = []
    manager = _PolicyManager(active_count=0)

    def snapshot(**kwargs):
        snapshot_calls.append(kwargs)
        manager.active_count = 1
        return {"executive_policy_manager": {"ingested": 1}}

    namespace = {
        "static_operational_runtime_enabled": lambda: False,
        "EXECUTIVE_POLICY_MANAGER_LOADED": True,
        "EXECUTIVE_POLICY_MANAGER_ERROR": None,
        "executive_policy_manager": manager,
        "_executive_decision_snapshot_for_reports": snapshot,
    }
    _load_functions(
        {
            "_static_risk_analytics_gate_payload",
            "_ensure_executive_policy_manager_synced_for_risk",
        },
        namespace,
    )

    result = namespace["_ensure_executive_policy_manager_synced_for_risk"]()

    assert snapshot_calls == [{"compact_source": True}]
    assert result["ok"] is True
    assert result["reason"] == "synced_from_executive_decision"
    assert result["analytics_ranking_status"] == "HISTORICAL_ANALYTICS_FALLBACK_CALLED"
    assert result["historical_analytics_used"] is True


def test_normal_risk_gate_records_failed_historical_fallback_without_raising():
    def failed_snapshot(**_kwargs):
        raise RuntimeError("synthetic historical snapshot failure")

    namespace = {
        "static_operational_runtime_enabled": lambda: False,
        "EXECUTIVE_POLICY_MANAGER_LOADED": True,
        "EXECUTIVE_POLICY_MANAGER_ERROR": None,
        "executive_policy_manager": _PolicyManager(active_count=0),
        "_executive_decision_snapshot_for_reports": failed_snapshot,
    }
    _load_functions(
        {
            "_static_risk_analytics_gate_payload",
            "_ensure_executive_policy_manager_synced_for_risk",
        },
        namespace,
    )

    result = namespace["_ensure_executive_policy_manager_synced_for_risk"]()

    assert result["attempted"] is True
    assert result["historical_analytics_used"] is True
    assert result["analytics_ranking_status"] == "HISTORICAL_ANALYTICS_FALLBACK_FAILED"
    assert result["reason"] == "synthetic historical snapshot failure"


def test_normal_risk_gate_skips_history_when_policies_are_already_active():
    snapshot_calls = []
    namespace = {
        "static_operational_runtime_enabled": lambda: False,
        "EXECUTIVE_POLICY_MANAGER_LOADED": True,
        "EXECUTIVE_POLICY_MANAGER_ERROR": None,
        "executive_policy_manager": _PolicyManager(active_count=1),
        "_executive_decision_snapshot_for_reports": lambda **kwargs: snapshot_calls.append(kwargs),
    }
    _load_functions({"_static_risk_analytics_gate_payload", "_ensure_executive_policy_manager_synced_for_risk"}, namespace)
    result = namespace["_ensure_executive_policy_manager_synced_for_risk"]()

    assert snapshot_calls == []
    assert result["historical_analytics_used"] is False
    assert result["analytics_ranking_status"] == "HISTORICAL_ANALYTICS_NOT_NEEDED"


def test_can_open_trade_exposes_static_risk_gate_without_direct_historical_ranking():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    original_start = source.index("def can_open_trade_decision(payload: dict):")
    original_end = source.index("def build_execution_report():", original_start)
    original = source[original_start:original_end]

    assert "analytics_gate = _static_risk_analytics_gate_payload()" in original
    assert "**analytics_gate" in original
    assert "analytics_engine.bot_ranking" not in original
    assert "build_trade_record_analytics" not in original
    assert "load_closed_trades" not in original
    assert "closed_trades.jsonl" not in original
    assert 'reasons.append("STATIC_OPERATIONAL_HISTORICAL_ANALYTICS_SKIPPED")' not in original
    assert "allowed = len(reasons) == 0" in original


def test_policy_sync_is_context_only_and_cannot_allow_or_block_by_itself():
    policy_apply = ast.unparse(_function_nodes("_apply_executive_policy_to_risk_reasons")[0])
    assert "sync_result = _ensure_executive_policy_manager_synced_for_risk(force=False)" in policy_apply
    assert "if not sync_result.get('ok')" not in policy_apply
    assert "if not sync_result.get(\"ok\")" not in policy_apply
