from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "execution_engine.py"
TREE = ast.parse(ENGINE.read_text(encoding="utf-8"), filename=str(ENGINE))


def _load_validator(*, broker, required=True, original=None):
    definitions = [
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "validate_real_pilot_guard"
    ]
    assert len(definitions) >= 2, "partial-capable validator override missing"
    final_validator = definitions[-1]
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "central_broker": broker,
        "EXECUTION_ENGINE_REQUIRE_PARTIAL_CAPABLE_FOR_FALCON": required,
        "EXECUTION_ENGINE_PARTIAL_CAPABLE_GUARD_VERSION": "test-version",
        "REAL_PILOT_MAX_NOTIONAL_USDT": 20.0,
        "_safe_float": lambda value, default=None: default if value is None else float(value),
        "_ORIGINAL_VALIDATE_REAL_PILOT_GUARD_20260711": original or _allowed_falcon_result,
    }
    module = ast.Module(body=[final_validator], type_ignores=[])
    exec(compile(module, str(ENGINE), "exec"), namespace)
    return namespace["validate_real_pilot_guard"]


def _allowed_falcon_result(_payload, _plan, dry_run=True):
    return {
        "ok": True,
        "allowed": True,
        "status": "REAL_PILOT_ALLOWED",
        "reasons": [],
        "warnings": [],
        "trade": {
            "bot": "FALCON",
            "symbol": "BTCUSDT",
            "notional_usdt": 20.0,
        },
    }


class _CapableBroker:
    @staticmethod
    def partial_capability_from_notional(symbol, notional, **kwargs):
        assert symbol == "BTCUSDT"
        assert notional == 20.0
        assert kwargs == {"max_notional_usdt": 20.0, "min_parts": 2}
        return {"ok": True, "partial_capable": True, "status": "PARTIAL_CAPABLE"}


class _NotCapableBroker:
    @staticmethod
    def partial_capability_from_notional(_symbol, _notional, **_kwargs):
        return {"ok": True, "partial_capable": False, "status": "PARTIAL_NOT_CAPABLE"}


class _RaisingBroker:
    @staticmethod
    def partial_capability_from_notional(_symbol, _notional, **_kwargs):
        raise RuntimeError("synthetic precision failure")


class _InvalidBroker:
    @staticmethod
    def partial_capability_from_notional(_symbol, _notional, **_kwargs):
        return None


def test_falcon_partial_capability_true_preserves_allowed_result():
    result = _load_validator(broker=_CapableBroker())({}, {}, dry_run=False)

    assert result["ok"] is True
    assert result["allowed"] is True
    assert result["partial_capable_guard"]["partial_capable"] is True


def test_falcon_partial_not_capable_blocks_live_entry():
    result = _load_validator(broker=_NotCapableBroker())({}, {}, dry_run=False)

    assert result["ok"] is False
    assert result["allowed"] is False
    assert result["status"] == "REAL_PILOT_BLOCKED_PARTIAL_NOT_CAPABLE"
    assert any("2x minQty" in reason for reason in result["reasons"])


@pytest.mark.parametrize("broker", [None, object(), _RaisingBroker(), _InvalidBroker()])
def test_falcon_partial_capability_unconfirmed_fails_closed(broker):
    result = _load_validator(broker=broker)({}, {}, dry_run=False)

    assert result["ok"] is False
    assert result["allowed"] is False
    assert result["status"] == "REAL_PILOT_BLOCKED_PARTIAL_CAPABILITY_UNCONFIRMED"
    assert result["partial_capable_guard"]["partial_capable"] is False
    assert any("não pôde ser confirmada" in reason for reason in result["reasons"])


def test_partial_capability_exception_exposes_only_error_type():
    result = _load_validator(broker=_RaisingBroker())({}, {}, dry_run=False)

    guard = result["partial_capable_guard"]
    assert guard["status"] == "PARTIAL_CAPABILITY_CHECK_ERROR"
    assert guard["error_type"] == "RuntimeError"
    assert "synthetic precision failure" not in repr(result)


def test_non_falcon_trade_is_unchanged_by_falcon_partial_guard():
    def original(_payload, _plan, dry_run=True):
        result = _allowed_falcon_result({}, {}, dry_run=dry_run)
        result["trade"]["bot"] = "PREDATOR"
        return result

    result = _load_validator(broker=None, original=original)({}, {}, dry_run=False)

    assert result["ok"] is True
    assert result["allowed"] is True
    assert "partial_capable_guard" not in result


def test_explicitly_disabled_requirement_preserves_existing_guard_result():
    result = _load_validator(broker=None, required=False)({}, {}, dry_run=False)

    assert result["ok"] is True
    assert result["allowed"] is True
    assert "partial_capable_guard" not in result


def test_invalid_original_guard_result_is_blocked():
    result = _load_validator(
        broker=_CapableBroker(),
        original=lambda _payload, _plan, dry_run=True: None,
    )({}, {}, dry_run=False)

    assert result["ok"] is False
    assert result["allowed"] is False
    assert result["status"] == "REAL_PILOT_GUARD_INVALID_RESULT"
