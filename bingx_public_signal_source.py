"""Explicit, credential-free public market reads. No trading/Telegram/runtime.

Only two fixed GET endpoints. No env, API keys, signing, redirects, retries or
arbitrary endpoint/host parameters. Collected data is NEVER marked synthetic.
Receive time is not exchange event time or proof of clock qualification.
"""
import http.client
import json
import math
import re
import time
from urllib.parse import urlencode

PERIODS = {"15m": 900000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
PATHS = {"candles": "/openApi/swap/v3/quote/klines", "quote": "/openApi/swap/v2/quote/price"}


class PublicDataError(ValueError):
    pass


PUBLIC_ERROR_CODES = frozenset({
    "INVALID_NUMBER", "INVALID_TIMESTAMP", "PUBLIC_READ_AUTHORIZATION_REQUIRED",
    "ENDPOINT_NOT_ALLOWED", "SYMBOL", "INTERVAL", "LIMIT", "QUOTE_INTERVAL",
    "PUBLIC_HTTP_FAILED_NO_RETRY", "RESPONSE_TOO_LARGE", "PUBLIC_API_REJECTED_NO_RETRY",
    "PUBLIC_TRANSPORT_OR_JSON_FAILED_NO_RETRY", "CANDLES_REQUIRED",
    "UNREVIEWED_CANDLE_SCHEMA", "CANDLE_FIELDS", "CANDLE_ALIGNMENT_REVIEW_REQUIRED",
    "CANDLE_OHLC", "CANDLE_GAP_OR_DUPLICATE", "QUOTE_SYMBOL_OR_SCHEMA", "QUOTE_FIELDS",
    "EXPLICIT_AGE_POLICY_REQUIRED", "SNAPSHOT_REQUIRED", "PUBLIC_SOURCE_REQUIRED",
    "FEED_DISCONNECTED", "UNQUALIFIED_INPUT_REQUIRED", "SNAPSHOT_STALE_OR_FUTURE",
    "FRAMES_REQUIRED", "FRAME_RECEIPTS_REQUIRED", "FRAME_STALE_OR_FUTURE",
    "CANDLE_ORDER", "FRAME_NOT_CURRENT", "QUOTE_STALE_OR_FUTURE",
    "INTERVALS", "DUPLICATE_INTERVAL",
})


def safe_error_code(error):
    """Fixed diagnostic only; never stringify exceptions or return raw responses."""
    if type(error) is PublicDataError and len(error.args) == 1:
        code = error.args[0]
        if type(code) is str and code in PUBLIC_ERROR_CODES:
            return code
    return "PUBLIC_DATA_FAILURE_REDACTED"


def require(condition, code):
    if not condition:
        raise PublicDataError(code)


def number(value, *, zero=False):
    require(type(value) in (str, int, float), "INVALID_NUMBER")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise PublicDataError("INVALID_NUMBER") from None
    require(math.isfinite(result) and (result >= 0 if zero else result > 0), "INVALID_NUMBER")
    return result


def stamp(value):
    require(type(value) is int and 0 < value <= 4102444800000, "INVALID_TIMESTAMP")
    return value


def _public_path(kind, symbol, *, interval=None, limit=200, authorized=False):
    require(authorized is True, "PUBLIC_READ_AUTHORIZATION_REQUIRED")
    require(type(kind) is str and kind in PATHS, "ENDPOINT_NOT_ALLOWED")
    require(type(symbol) is str and re.fullmatch(r"[A-Z0-9]{2,25}-USDT", symbol) is not None, "SYMBOL")
    params = dict(symbol=symbol)
    if kind == "candles":
        require(type(interval) is str and interval in PERIODS, "INTERVAL")
        require(type(limit) is int and 2 <= limit <= 200, "LIMIT")
        params.update(interval=interval, limit=limit)
    else:
        require(interval is None, "QUOTE_INTERVAL")
    return PATHS[kind] + "?" + urlencode(params)


def _read_public(connection, path):
    try:
        connection.request("GET", path, headers={"Accept": "application/json"})
        response = connection.getresponse()
        raw = response.read(1048577)
        require(response.status == 200, "PUBLIC_HTTP_FAILED_NO_RETRY")
        require(len(raw) <= 1048576, "RESPONSE_TOO_LARGE")
        result = json.loads(raw)
        require(type(result) is dict and type(result.get("code")) is int and result["code"] == 0, "PUBLIC_API_REJECTED_NO_RETRY")
        return result.get("data")
    except PublicDataError:
        raise
    except Exception:
        raise PublicDataError("PUBLIC_TRANSPORT_OR_JSON_FAILED_NO_RETRY") from None


def request_public(kind, symbol, *, interval=None, limit=200, authorized=False):
    path = _public_path(kind, symbol, interval=interval, limit=limit, authorized=authorized)
    connection = http.client.HTTPSConnection("open-api.bingx.com", timeout=15)
    try:
        return _read_public(connection, path)
    finally:
        connection.close()


def normalize_candles(data, interval):
    require(type(interval) is str and interval in PERIODS, "INTERVAL")
    require(type(data) is list and 2 <= len(data) <= 200, "CANDLES_REQUIRED")
    rows = []
    for item in data:
        require(type(item) is dict, "UNREVIEWED_CANDLE_SCHEMA")
        require({"time", "open", "high", "low", "close", "volume"} <= set(item), "CANDLE_FIELDS")
        ts = stamp(item["time"])
        require(ts % PERIODS[interval] == 0, "CANDLE_ALIGNMENT_REVIEW_REQUIRED")
        op, high, low, close = (number(item[k]) for k in ("open", "high", "low", "close"))
        require(low <= min(op, close) <= max(op, close) <= high, "CANDLE_OHLC")
        rows.append([ts, op, high, low, close, number(item["volume"], zero=True)])
    rows.sort(key=lambda row: row[0])
    require(all(b[0]-a[0] == PERIODS[interval] for a, b in zip(rows, rows[1:])), "CANDLE_GAP_OR_DUPLICATE")
    return rows


def normalize_quote(data, symbol):
    require(type(data) is dict and data.get("symbol") == symbol, "QUOTE_SYMBOL_OR_SCHEMA")
    require({"price", "time"} <= set(data), "QUOTE_FIELDS")
    return dict(price=number(data["price"]), at_ms=stamp(data["time"]))


def validate_snapshot(snapshot, *, now_ms, frame_max_age_ms, quote_max_age_ms):
    """Pure intake validation with explicit caller policy; never authorizes delivery.

    Receipt age and candle coverage are checked separately for every frame.
    Crossing a candle boundary requires recollection, not relabeling the last row.
    This checks consistency, not authenticity, clock accuracy or strategy fitness.
    Returns an independent allowlisted copy; no input flags are promoted.
    """
    stamp(now_ms)
    require(all(type(x) is int and x > 0 for x in
                (frame_max_age_ms, quote_max_age_ms)), "EXPLICIT_AGE_POLICY_REQUIRED")
    require(type(snapshot) is dict, "SNAPSHOT_REQUIRED")
    require(snapshot.get("synthetic") is False and
            snapshot.get("source") == "BINGX_PUBLIC_SWAP", "PUBLIC_SOURCE_REQUIRED")
    require(snapshot.get("connected") is True, "FEED_DISCONNECTED")
    for flag in ("source_qualified", "delivery_allowed", "live_allowed", "manual_trade_authorized"):
        require(snapshot.get(flag) is False, "UNQUALIFIED_INPUT_REQUIRED")
    symbol = snapshot.get("symbol")
    require(type(symbol) is str and re.fullmatch(r"[A-Z0-9]{2,25}-USDT", symbol) is not None, "SYMBOL")
    observed = stamp(snapshot.get("observed_at_ms"))
    require(0 <= now_ms - observed <= frame_max_age_ms, "SNAPSHOT_STALE_OR_FUTURE")
    supplied, receipts = snapshot.get("frames"), snapshot.get("frame_received_at_ms")
    require(type(supplied) is dict and 1 <= len(supplied) <= 4 and
            set(supplied) <= set(PERIODS), "FRAMES_REQUIRED")
    require(type(receipts) is dict and set(receipts) == set(supplied), "FRAME_RECEIPTS_REQUIRED")
    frames, received = {}, {}
    for interval, rows in supplied.items():
        receipt = stamp(receipts[interval])
        require(receipt <= observed and 0 <= now_ms - receipt <= frame_max_age_ms,
                "FRAME_STALE_OR_FUTURE")
        require(type(rows) is list and 2 <= len(rows) <= 200, "CANDLES_REQUIRED")
        require(all(type(row) in (list, tuple) and len(row) == 6 for row in rows), "CANDLE_FIELDS")
        normalized = normalize_candles([
            dict(zip(("time", "open", "high", "low", "close", "volume"), row))
            for row in rows], interval)
        require([row[0] for row in rows] == [row[0] for row in normalized], "CANDLE_ORDER")
        latest, duration = normalized[-1][0], PERIODS[interval]
        require(latest <= receipt <= now_ms < latest + duration, "FRAME_NOT_CURRENT")
        frames[interval], received[interval] = normalized, receipt
    quote = snapshot.get("quote")
    require(type(quote) is dict, "QUOTE_FIELDS")
    quote_time = stamp(quote.get("at_ms"))
    require(quote_time <= observed and 0 <= now_ms - quote_time <= quote_max_age_ms,
            "QUOTE_STALE_OR_FUTURE")
    return dict(synthetic=False, connected=True, source="BINGX_PUBLIC_SWAP", symbol=symbol,
                observed_at_ms=observed, frames=frames, frame_received_at_ms=received,
                quote=dict(price=number(quote.get("price")), at_ms=quote_time),
                input_validated=True, source_qualified=False, delivery_allowed=False,
                live_allowed=False, manual_trade_authorized=False)


def collect_snapshot(symbol, intervals, *, authorized=False, limit=200):
    """Finite read of one symbol, no loop/watchlist discovery. Stops on first error.

One-second spacing is a request pacing measure, not a signal TTL or freshness
guarantee. A production scheduler sharing IP limits remains separate work.
"""
    require(authorized is True, "PUBLIC_READ_AUTHORIZATION_REQUIRED")
    require(type(intervals) in (tuple, list) and 1 <= len(intervals) <= 4, "INTERVALS")
    require(all(type(x) is str and x in PERIODS for x in intervals), "INTERVAL")
    require(len(set(intervals)) == len(intervals), "DUPLICATE_INTERVAL")
    # Validate all requests before constructing a connection. Reuse only within
    # this finite symbol read; a failed request is never retried.
    paths = [_public_path("candles", symbol, interval=interval, limit=limit,
                          authorized=authorized) for interval in intervals]
    quote_path = _public_path("quote", symbol, authorized=authorized)
    frames, received = {}, {}
    connection = http.client.HTTPSConnection("open-api.bingx.com", timeout=15)
    try:
        for interval, path in zip(intervals, paths):
            frames[interval] = normalize_candles(_read_public(connection, path), interval)
            received[interval] = time.time_ns() // 1000000
            time.sleep(1)
        quote = normalize_quote(_read_public(connection, quote_path), symbol)
    finally:
        connection.close()
    observed = time.time_ns() // 1000000
    # Receipt metadata does not prove that each frame was current at receipt.
    return dict(synthetic=False, connected=True, source="BINGX_PUBLIC_SWAP",
                symbol=symbol, observed_at_ms=observed, frames=frames, quote=quote,
                frame_received_at_ms=received, source_qualified=False,
                delivery_allowed=False, live_allowed=False, manual_trade_authorized=False)
