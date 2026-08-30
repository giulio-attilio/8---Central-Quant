from __future__ import annotations

import ast
import copy
import math
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BROKER = ROOT / "broker.py"
SOURCE = BROKER.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE, filename=str(BROKER))


def _function_node(name):
    return next(
        node
        for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


class _SyntheticExchange:
    def __init__(self, market, *, precise_amount=None, precision_error=None):
        self.market_payload = dict(market)
        self.precise_amount = precise_amount
        self.precision_error = precision_error
        self.precision_inputs = []

    def market(self, _symbol):
        return dict(self.market_payload)

    def amount_to_precision(self, symbol, amount):
        self.precision_inputs.append((symbol, amount))
        if self.precision_error is not None:
            raise self.precision_error
        return self.precise_amount if self.precise_amount is not None else amount


def _run_amount_details(exchange_probe, *, notional=20.0, price=100_000.0):
    namespace = {
        "math": math,
        "normalize_symbol": lambda value: str(value).upper(),
        "fetch_last_price": lambda _symbol: price,
        "exchange": lambda: exchange_probe,
        "safe_float": _safe_float,
        "market_info": lambda _symbol: {
            "symbol": exchange_probe.market_payload.get("symbol", "BTC/USDT:USDT"),
            "contract": exchange_probe.market_payload.get("contract"),
            "contract_size": exchange_probe.market_payload.get("contractSize"),
            "min_amount": ((exchange_probe.market_payload.get("limits") or {}).get("amount") or {}).get("min"),
            "min_cost": ((exchange_probe.market_payload.get("limits") or {}).get("cost") or {}).get("min"),
        },
        "bingx_api_symbol": lambda _symbol: "BTC-USDT",
        "money": lambda value, _digits=8: value,
    }
    node = copy.deepcopy(_function_node("amount_details"))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BROKER), "exec"), namespace)
    return namespace["amount_details"]("BTCUSDT", notional)


def _constraints(details, *, reduce_only=False):
    namespace = {"safe_float": _safe_float}
    node = copy.deepcopy(_function_node("_order_constraint_evidence"))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(BROKER), "exec"), namespace)
    return namespace["_order_constraint_evidence"](details, reduce_only=reduce_only)


def _market(**updates):
    payload = {
        "symbol": "BTC/USDT:USDT",
        "contract": True,
        "contractSize": 0.001,
        "limits": {
            "amount": {"min": 0.1},
            "cost": {"min": 5.0},
        },
    }
    payload.update(updates)
    return payload


def test_contract_size_is_applied_to_amount_and_actual_notional():
    exchange_probe = _SyntheticExchange(_market(), precise_amount="0.2")

    details = _run_amount_details(exchange_probe, notional=20.0, price=100_000.0)

    assert details["ok"] is True
    assert details["contract_size"] == 0.001
    assert details["amount_raw"] == pytest.approx(0.2)
    assert details["amount"] == pytest.approx(0.2)
    assert details["actual_exposure_usdt"] == pytest.approx(20.0)
    assert exchange_probe.precision_inputs == [("BTC/USDT:USDT", pytest.approx(0.2))]


def test_precision_failure_never_falls_back_to_rounded_raw_amount():
    exchange_probe = _SyntheticExchange(
        _market(),
        precision_error=RuntimeError("synthetic precision failure"),
    )

    details = _run_amount_details(exchange_probe)

    assert details["ok"] is False
    assert details["amount"] is None
    assert details["amount_final"] is None
    assert details["actual_exposure_usdt"] is None
    assert details["precision_error"] == "RuntimeError"
    assert "synthetic precision failure" not in repr(details)


def test_missing_contract_size_fails_amount_evidence_closed():
    exchange_probe = _SyntheticExchange(_market(contractSize=None))

    details = _run_amount_details(exchange_probe)

    assert details["ok"] is False
    assert details["amount"] is None
    assert details["precision_error"] == "ValueError"


def _valid_details(**updates):
    details = {
        "ok": True,
        "amount": 0.2,
        "effective_notional_usdt": 20.0,
        "contract_size": 0.001,
        "precision_error": None,
        "market": {
            "contract": True,
            "contract_size": 0.001,
            "min_amount": 0.1,
            "min_cost": 5.0,
        },
    }
    details.update(updates)
    return details


def test_complete_min_qty_and_min_notional_evidence_passes():
    result = _constraints(_valid_details())

    assert result["ok"] is True
    assert result["constraints_ok"] is True
    assert result["constraint_reasons"] == []


@pytest.mark.parametrize(
    "market_update, reason",
    [
        ({"min_amount": None}, "MIN_QTY_UNAVAILABLE"),
        ({"min_cost": None}, "MIN_NOTIONAL_UNAVAILABLE"),
        ({"contract_size": None}, "CONTRACT_SIZE_UNAVAILABLE"),
    ],
)
def test_missing_exchange_constraint_evidence_blocks(market_update, reason):
    details = _valid_details()
    details["market"] = {**details["market"], **market_update}
    if "contract_size" in market_update:
        details["contract_size"] = market_update["contract_size"]

    result = _constraints(details)

    assert result["constraints_ok"] is False
    assert reason in result["constraint_reasons"]


@pytest.mark.parametrize(
    "updates, reason",
    [
        ({"amount": 0.09}, "AMOUNT_BELOW_MIN_QTY"),
        ({"effective_notional_usdt": 4.99}, "NOTIONAL_BELOW_MINIMUM"),
    ],
)
def test_below_exchange_minimum_blocks(updates, reason):
    result = _constraints(_valid_details(**updates))

    assert result["constraints_ok"] is False
    assert reason in result["constraint_reasons"]


def test_reduce_only_does_not_require_min_notional_but_still_requires_min_qty():
    details = _valid_details()
    details["market"] = {**details["market"], "min_cost": None}

    reduce_result = _constraints(details, reduce_only=True)
    entry_result = _constraints(details, reduce_only=False)

    assert reduce_result["constraints_ok"] is True
    assert entry_result["constraints_ok"] is False
    assert "MIN_NOTIONAL_UNAVAILABLE" in entry_result["constraint_reasons"]


def test_order_preview_projects_constraints_consumed_by_send_gate():
    preview_source = ast.get_source_segment(SOURCE, _function_node("build_order_preview"))
    send_source = ast.get_source_segment(SOURCE, _function_node("place_market_order"))

    assert "_order_constraint_evidence(details, reduce_only=reduce_only)" in preview_source
    assert '"constraints_ok": constraints.get("constraints_ok")' in preview_source
    assert 'preview.get("constraints_ok") is False' in send_source
    assert '"status": "CONSTRAINTS_BLOCKED"' in send_source
