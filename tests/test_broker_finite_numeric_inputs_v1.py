from __future__ import annotations

import math

import pytest

import broker


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_broker_numeric_parsers_reject_nonfinite_values(value):
    assert broker.safe_float(value, None) is None
    assert broker._safe_float_broker(value, None) is None
    assert broker._cq_patch_safe_float(value, None) is None


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
@pytest.mark.parametrize("invalid_stop", [float("nan"), float("inf"), float("-inf")])
def test_disaster_stop_validator_rejects_nonfinite_stop_price(side, invalid_stop):
    result = broker.validate_disaster_stop_price(
        side, entry_price=100.0, stop_price=invalid_stop
    )

    assert result["ok"] is False
    assert result["stop"] is None


@pytest.mark.parametrize("invalid_amount", [float("nan"), float("inf"), float("-inf")])
def test_managed_position_snapshot_fails_closed_on_nonfinite_amount(
    monkeypatch, invalid_amount
):
    monkeypatch.setattr(
        broker,
        "get_positions",
        lambda _symbols: [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "contracts": invalid_amount,
            }
        ],
    )

    result = broker.managed_position_snapshot("BTCUSDT", "LONG", expected_amount=1.0)

    assert result["ok"] is False
    assert result["status"] == "POSITION_SNAPSHOT_ERROR"
    assert result["ownership_safe"] is False
    assert result["error"] == "POSITION_AMOUNT_INVALID"


@pytest.mark.parametrize(
    "position_row",
    [
        {"contracts": 0.0, "info": {"positionAmt": "9"}},
        {"contracts": 9.0, "info": {"positionAmt": "0"}},
    ],
)
def test_managed_position_snapshot_rejects_conflicting_zero_and_open_amounts(
    monkeypatch, position_row
):
    monkeypatch.setattr(
        broker,
        "get_positions",
        lambda _symbols: [{"symbol": "BTC/USDT:USDT", "side": "long", **position_row}],
    )

    result = broker.managed_position_snapshot("BTCUSDT", "LONG", expected_amount=0.0)

    assert result["ok"] is False
    assert result["status"] == "POSITION_SNAPSHOT_ERROR"
    assert result["amount"] is None
    assert result["ownership_safe"] is False
    assert result["error"] == "POSITION_AMOUNT_INVALID"


def test_managed_position_snapshot_ignores_available_to_close_quantity(monkeypatch):
    monkeypatch.setattr(
        broker,
        "get_positions",
        lambda _symbols: [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "contracts": 9.0,
                "info": {"positionAmt": "9", "availableAmt": "0"},
            }
        ],
    )

    result = broker.managed_position_snapshot("BTCUSDT", "LONG", expected_amount=9.0)

    assert result["ok"] is True
    assert result["amount"] == pytest.approx(9.0)
    assert result["ownership_safe"] is True
    assert result["position_closed"] is False


def test_managed_position_snapshot_keeps_explicit_zero_position_closed(monkeypatch):
    monkeypatch.setattr(
        broker,
        "get_positions",
        lambda _symbols: [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "contracts": 0.0,
            }
        ],
    )

    result = broker.managed_position_snapshot("BTCUSDT", "LONG", expected_amount=0.0)

    assert result["ok"] is True
    assert result["position_closed"] is True
    assert math.isfinite(result["amount"])
