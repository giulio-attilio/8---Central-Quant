from __future__ import annotations

import ast
from pathlib import Path

import broker


def _fill(**updates):
    result = {
        "id": "ENTRY-1",
        "clientOrderId": "ENTRY-CID-1",
        "symbol": "SOL/USDT:USDT",
        "side": "buy",
        "status": "closed",
        "amount": 1.0,
        "filled": 1.0,
        "average": 100.25,
        "info": {"status": "FILLED", "executedQty": "1", "avgPrice": "100.25"},
    }
    result.update(updates)
    return result


def _validate(order):
    return broker.validate_entry_fill_for_disaster_stop(
        order,
        expected_order_id="ENTRY-1",
        expected_client_order_id="ENTRY-CID-1",
        expected_symbol="SOLUSDT",
        expected_side="buy",
        expected_amount=1.0,
    )


def test_full_fill_exact_identity_and_average_are_accepted():
    result = _validate(_fill())

    assert result["ok"] is True
    assert result["filled"] == 1.0
    assert result["average"] == 100.25


def test_partial_fill_is_rejected_for_stop_sizing():
    order = _fill(status="open", filled=0.4, info={"status": "PARTIALLY_FILLED", "executedQty": "0.4", "avgPrice": "100.25"})

    result = _validate(order)

    assert result["ok"] is False
    assert "terminal_status" in result["failed_checks"]
    assert "full_fill_confirmed" in result["failed_checks"]


def test_missing_fill_facts_are_rejected():
    order = _fill()
    for key in ("status", "amount", "filled", "average"):
        order.pop(key)
    order["info"] = {}

    result = _validate(order)

    assert result["ok"] is False
    assert {"terminal_status", "requested_amount_consistent", "full_fill_confirmed", "average_price_confirmed"} <= set(result["failed_checks"])


def test_mismatched_order_client_symbol_or_side_is_rejected():
    for field, value in (
        ("id", "OTHER-ORDER"),
        ("clientOrderId", "OTHER-CID"),
        ("symbol", "BTC/USDT:USDT"),
        ("side", "sell"),
    ):
        result = _validate(_fill(**{field: value}))
        assert result["ok"] is False, field
        assert any(name.startswith("exact_") for name in result["failed_checks"]), field


def test_conflicting_raw_status_or_fill_values_are_rejected():
    conflict_status = _fill(info={"status": "PARTIALLY_FILLED", "executedQty": "1", "avgPrice": "100.25"})
    conflict_fill = _fill(info={"status": "FILLED", "executedQty": "0.9", "avgPrice": "100.25"})

    assert "terminal_status" in _validate(conflict_status)["failed_checks"]
    assert "full_fill_confirmed" in _validate(conflict_fill)["failed_checks"]


def test_normalized_read_only_snapshot_requires_terminal_status_and_exact_fill():
    snapshot = {
        "order_id": "ENTRY-1",
        "client_order_id": "ENTRY-CID-1",
        "symbol": "SOL/USDT:USDT",
        "side": "BUY",
        "status": "CLOSED",
        "raw_status": "FILLED",
        "amount": 1.0,
        "filled": 1.0,
        "executed_quantity": 1.0,
        "average": 100.25,
    }
    assert _validate(snapshot)["ok"] is True

    snapshot["raw_status"] = "PARTIALLY_FILLED"
    assert "terminal_status" in _validate(snapshot)["failed_checks"]


def test_average_price_must_be_present_positive_and_consistent():
    missing = _fill(average=None, info={"status": "FILLED", "executedQty": "1"})
    zero = _fill(average=0)
    conflict = _fill(info={"status": "FILLED", "executedQty": "1", "avgPrice": "101"})

    assert "average_price_confirmed" in _validate(missing)["failed_checks"]
    assert "average_price_confirmed" in _validate(zero)["failed_checks"]
    assert "average_price_confirmed" in _validate(conflict)["failed_checks"]


def test_malformed_numeric_alias_is_rejected_even_when_another_alias_matches():
    cases = (
        (
            _fill(info={
                "status": "FILLED",
                "origQty": "not-a-number",
                "executedQty": "1",
                "avgPrice": "100.25",
            }),
            "requested_amount_consistent",
        ),
        (
            _fill(info={
                "status": "FILLED",
                "executedQty": "NaN",
                "avgPrice": "100.25",
            }),
            "full_fill_confirmed",
        ),
        (
            _fill(info={
                "status": "FILLED",
                "executedQty": "1",
                "avgPrice": "Infinity",
            }),
            "average_price_confirmed",
        ),
    )

    for order, failed_check in cases:
        result = _validate(order)
        assert result["ok"] is False
        assert failed_check in result["failed_checks"]


def test_accepted_tolerant_aliases_return_usable_fill_and_average():
    result = _validate(_fill(info={
        "status": "FILLED",
        "executedQty": "1.00000000001",
        "avgPrice": "100.2500000001",
    }))

    assert result["ok"] is True
    assert result["filled"] == 1.0
    assert result["average"] == 100.25


def test_readback_projection_preserves_malformed_alias_failure_without_raw_info():
    raw_order = _fill(info={
        "status": "FILLED",
        "executedQty": "1",
        "cumExecQty": "not-a-number",
        "avgPrice": "100.25",
    })
    projected = broker._normalize_managed_order_payload(
        raw_order,
        requested_symbol="SOL/USDT:USDT",
        requested_order_id="ENTRY-1",
    )

    assert "info" not in projected
    assert projected["numeric_aliases_well_formed"]["filled"] is False
    result = _validate(projected)
    assert result["ok"] is False
    assert "full_fill_confirmed" in result["failed_checks"]


def test_live_stop_call_is_wired_to_verified_fill_quantity_and_average():
    source_path = Path(broker.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "place_market_order"
    )
    validation_line = min(
        node.lineno for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_entry_fill_for_disaster_stop"
    )
    stop_call = next(
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "create_disaster_stop_order"
    )
    assert validation_line < stop_call.lineno
    keywords = {item.arg: item.value for item in stop_call.keywords}
    assert isinstance(keywords["amount"], ast.Subscript)
    assert isinstance(keywords["entry_price"], ast.Subscript)
    assert isinstance(keywords["amount"].value, ast.Name)
    assert keywords["amount"].value.id == "entry_fill_evidence"
    assert isinstance(keywords["entry_price"].value, ast.Name)
    assert keywords["entry_price"].value.id == "entry_fill_evidence"
