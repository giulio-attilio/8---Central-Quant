"""Offline adapter contract for parsing an exchange-generated stop readback."""

import ccxt
import socket
import urllib.request


def test_pinned_bingx_adapter_preserves_stop_readback_evidence():
    assert ccxt.__version__ == "4.5.88"
    exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
    market = {
        "id": "BTC-USDT",
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "quote": "USDT",
        "settle": "USDT",
        "baseId": "BTC",
        "quoteId": "USDT",
        "settleId": "USDT",
        "type": "swap",
        "spot": False,
        "margin": False,
        "swap": True,
        "future": False,
        "option": False,
        "contract": True,
        "linear": True,
        "inverse": False,
        "active": True,
        "contractSize": 1.0,
    }
    raw_readback = {
        "orderId": "SYNTHETIC-ORDER-7",
        "symbol": "BTC-USDT",
        "type": "STOP_MARKET",
        "side": "SELL",
        "positionSide": "LONG",
        "origQty": "0.1",
        "executedQty": "0",
        "status": "NEW",
        "stopPrice": "68000",
        "updateTime": 1761955200000,
    }

    order = exchange.parse_order(raw_readback, market)

    # CCXT intentionally normalizes STOP_MARKET to type=market; our safety
    # verification must inspect the preserved raw `info` fields as well.
    assert order["id"] == "SYNTHETIC-ORDER-7"
    assert order["symbol"] == "BTC/USDT"
    assert order["type"] == "market"
    assert order["side"] == "sell"
    assert order["amount"] == 0.1
    assert order["status"] == "open"
    assert order["stopLossPrice"] == 68000.0
    assert order["info"]["type"] == "STOP_MARKET"
    assert order["info"]["positionSide"] == "LONG"
    assert order["info"]["stopPrice"] == "68000"


def test_pinned_bingx_fetch_order_queries_system_id_and_parses_stop_readback(monkeypatch):
    assert ccxt.__version__ == "4.5.88"

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is blocked in this contract test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)

    exchange = ccxt.bingx({"options": {"defaultType": "swap"}})
    market = {
        "id": "BTC-USDT",
        "symbol": "BTC/USDT:USDT",
        "base": "BTC",
        "quote": "USDT",
        "settle": "USDT",
        "baseId": "BTC",
        "quoteId": "USDT",
        "settleId": "USDT",
        "type": "swap",
        "spot": False,
        "margin": False,
        "swap": True,
        "future": False,
        "option": False,
        "contract": True,
        "linear": True,
        "inverse": False,
        "active": True,
        "contractSize": 1.0,
    }
    exchange.markets = {market["symbol"]: market}
    exchange.markets_by_id = {market["id"]: [market]}
    raw_readback = {
        "orderId": "SYNTHETIC-STOP-42",
        "symbol": "BTC-USDT",
        "type": "STOP_MARKET",
        "side": "SELL",
        "positionSide": "LONG",
        "origQty": "0.1",
        "executedQty": "0",
        "status": "NEW",
        "stopPrice": "68000",
        "updateTime": 1761955200000,
    }
    requests = []

    def query_order(params):
        requests.append(params)
        return {"code": 0, "msg": "", "data": {"order": raw_readback}}

    monkeypatch.setattr(exchange, "swapV2PrivateGetTradeOrder", query_order)

    order = exchange.fetch_order("SYNTHETIC-STOP-42", market["symbol"])

    assert requests == [{"symbol": "BTC-USDT", "orderId": "SYNTHETIC-STOP-42"}]
    assert order["id"] == "SYNTHETIC-STOP-42"
    # fetch_order uses market['symbol'], which retains CCXT's linear-swap
    # settlement suffix; the broker's contract identity normalizer strips it.
    assert order["symbol"] == "BTC/USDT:USDT"
    assert order["status"] == "open"
    assert order["info"]["type"] == "STOP_MARKET"
    assert order["info"]["positionSide"] == "LONG"
    assert order["info"]["stopPrice"] == "68000"
