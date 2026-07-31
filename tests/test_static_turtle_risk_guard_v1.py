from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_TREE = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))


def _compile_turtle_guard(namespace):
    node = next(
        item
        for item in MAIN_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == "_trg_v1_evaluate"
    )
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<static-turtle-risk-guard>", "exec"), namespace)
    return namespace["_trg_v1_evaluate"]


def _namespace(static_enabled, history_calls):
    return {
        "normalize_registry_bot": lambda value: str(value or "").upper(),
        "_trg_v1_normalize_setup": lambda value: str(value or "").upper(),
        "_trg_v1_normalize_side": lambda value: str(value or "").upper(),
        "static_operational_runtime_enabled": lambda: static_enabled,
        "TURTLE_RISK_GUARD_ENABLED": True,
        "TURTLE_RISK_GUARD_VERSION": "test-v1",
        "TURTLE_RISK_GUARD_BLOCK_TURTLE55_SHORT": True,
        "TURTLE_RISK_GUARD_BLOCK_NEG_EXPECTANCY": True,
        "TURTLE_RISK_GUARD_MIN_TRADES_FOR_EXPECTANCY": 8,
        "TURTLE_RISK_GUARD_MAX_CONSECUTIVE_STOPS_DAY": 5,
        "TURTLE_RISK_GUARD_PF_R_OBSERVATION_THRESHOLD": 1.0,
        "TURTLE_RISK_GUARD_BLOCK_OBSERVATION_ONLY": True,
        "TURTLE_RISK_GUARD_HISTORY_LIMIT": 6000,
        "_trg_v1_load_history_events": lambda: history_calls.append("load") or [],
        "_trg_v1_stats_for": lambda **_kwargs: {
            "r_sample": 0,
            "consecutive_stops_today": 0,
            "expectancy_r": None,
            "profit_factor_r": 0.0,
        },
        "_trg_v1_float": lambda value, default=0.0: float(value if value is not None else default),
    }


def test_static_turtle_guard_skips_history_and_returns_neutral_factual_state():
    history_calls = []
    namespace = _namespace(True, history_calls)
    namespace["_read_jsonl_tail"] = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("JSONL read must not occur")
    )
    evaluate = _compile_turtle_guard(namespace)

    result = evaluate({"bot": "TURTLE", "setup": "TURTLE20", "side": "LONG"})

    assert history_calls == []
    assert result["enabled"] is True
    assert result["applies"] is False
    assert result["historical_data_used"] is False
    assert result["status"] == "STATIC_OPERATIONAL_SKIPPED"
    assert result["reason"] == "STATIC_OPERATIONAL_RUNTIME"
    assert "allowed" not in result
    assert result["reasons"] == []


def test_static_turtle55_short_preserves_static_hard_block_without_history():
    history_calls = []
    evaluate = _compile_turtle_guard(_namespace(True, history_calls))

    result = evaluate({"bot": "TURTLE", "setup": "TURTLE55", "side": "SHORT"})

    assert history_calls == []
    assert result["historical_data_used"] is False
    assert result["status"] == "STATIC_OPERATIONAL_SKIPPED"
    assert result["applies"] is True
    assert result["allowed"] is False
    assert result["decision"] == "DENY_STATIC_RULE"
    assert result["actions"] == ["BLOCK_TURTLE55_SHORT"]
    assert result["reasons"]


def test_static_non_turtle_remains_non_applicable_without_history():
    history_calls = []
    evaluate = _compile_turtle_guard(_namespace(True, history_calls))

    result = evaluate({"bot": "PREDATOR", "setup": "SMART_PREDATOR", "side": "LONG"})

    assert history_calls == []
    assert result["applies"] is False
    assert result["historical_data_used"] is False
    assert result["status"] == "STATIC_OPERATIONAL_SKIPPED"


def test_normal_turtle_guard_keeps_historical_path_and_existing_behavior():
    history_calls = []
    evaluate = _compile_turtle_guard(_namespace(False, history_calls))

    result = evaluate({"bot": "TURTLE", "setup": "TURTLE20", "side": "LONG"})

    assert history_calls == ["load"]
    assert result["applies"] is True
    assert result["allowed"] is True
    assert result["decision"] == "ALLOW"
    assert "STATIC_OPERATIONAL_SKIPPED" not in result.values()


def test_can_open_trade_keeps_guard_reasons_as_part_of_existing_hard_block_path():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    start = source.index("# Turtle Risk Guard V1")
    block = source[start : start + 1800]

    assert "turtle_risk_guard_payload = _trg_v1_evaluate(" in block
    assert "for _reason in turtle_risk_guard_payload.get(\"reasons\") or []:" in block
    assert "reasons.append(str(_reason))" in block
