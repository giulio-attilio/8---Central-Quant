"""Isolated replay/local public-data preview of reviewed Falcon analysis.

No filesystem, network, clock, environment or transport access. The caller supplies
reviewed source text, snapshots and explicit policy. Public-schema input requires
separate explicit authorization and intake validation; it never enables delivery.
An AST fingerprint
pins exactly fourteen functions; all other source statements are discarded, never
executed. This is an offline reuse/parity seam, not a production import mechanism.
"""
import ast
import hashlib
import json
import math
import re
from datetime import datetime, timezone, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from falcon_signal_identity import attach_falcon_signal_identity, FalconSignalIdentityConstructionError
from falcon_advisory_preview import preview_signal, preview_public_signal
from bingx_public_signal_source import validate_snapshot


FUNCTIONS = frozenset({
    "safe_float", "add_indicators", "closed_candles", "position_id", "risk_pct",
    "ny_dt_from_row", "ny_time_bounds", "get_orb_range", "is_trade_window",
    "trend_state_for_timeframe", "passes_alignment", "quality_from_score",
    "calc_falcon_score", "analyze_symbol_setup",
})
SOURCE_DIGEST = "8ff4aaa7340a9577f19defe851dbcec6b4b932d5ae57d34ef32e742095f195bb"
PERIODS = {"15m": 900000, "1h": 3600000, "4h": 14400000}
INTEGER_CONFIG = {
    "ORB_START_HOUR", "ORB_START_MINUTE", "ORB_TRADE_END_HOUR", "ORB_TRADE_END_MINUTE",
    "ATR_LEN", "ADX_LEN", "EMA_FAST", "EMA_SLOW", "SCORE_MIN_QUALITY_TO_SIGNAL",
}
NUMBER_CONFIG = {
    "TP50_R", "STOP_ATR_BUFFER", "MIN_ATR_PCT", "MAX_RISK_PCT", "MIN_RANGE_ATR",
    "MAX_RANGE_ATR", "MIN_VOLUME_REL_TO_SIGNAL", "MIN_ADX_TO_SIGNAL",
}
POLICY_KEYS = {"signal_ttl_ms", "snapshot_max_age_ms", "quote_max_age_ms", "max_entry_deviation_fraction", "basis"}


class OfflineInputError(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise OfflineInputError(reason)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _timestamp(value):
    return type(value) is int and 0 <= value <= 4102444800000


def _identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_:/.-]{1,100}", value) is not None


def _config(config):
    _require(type(config) is dict and set(config) == INTEGER_CONFIG | NUMBER_CONFIG | {"ALIGNMENT_MODE"}, "CONFIG_FIELDS")
    _require(all(type(config[k]) is int and 0 <= config[k] <= 1000 for k in INTEGER_CONFIG), "CONFIG_INTEGER")
    _require(all(_number(config[k]) and 0 <= config[k] <= 1000 for k in NUMBER_CONFIG), "CONFIG_NUMBER")
    _require(config["ALIGNMENT_MODE"] in ("off", "h1", "h1_h4"), "CONFIG_ALIGNMENT")
    _require(all(config[k] >= 2 for k in ("ATR_LEN", "ADX_LEN", "EMA_FAST", "EMA_SLOW")), "CONFIG_PERIOD")
    _require(config["EMA_FAST"] < config["EMA_SLOW"], "CONFIG_EMA_ORDER")
    _require(config["TP50_R"] > 0 and config["MAX_RISK_PCT"] > 0, "CONFIG_POSITIVE")
    _require(config["MIN_RANGE_ATR"] <= config["MAX_RANGE_ATR"], "CONFIG_RANGE_ORDER")
    _require(config["SCORE_MIN_QUALITY_TO_SIGNAL"] <= 100, "CONFIG_SCORE")
    for k in ("ORB_START_HOUR", "ORB_TRADE_END_HOUR"):
        _require(config[k] < 24, "CONFIG_HOUR")
    for k in ("ORB_START_MINUTE", "ORB_TRADE_END_MINUTE"):
        _require(config[k] < 60, "CONFIG_MINUTE")
    start = config["ORB_START_HOUR"] * 60 + config["ORB_START_MINUTE"]
    end = config["ORB_TRADE_END_HOUR"] * 60 + config["ORB_TRADE_END_MINUTE"]
    _require(start + 30 < end < 1440 and start % 15 == 0, "CONFIG_WINDOW")
    return dict(config)


def _policy(policy):
    _require(type(policy) is dict and set(policy) == POLICY_KEYS, "POLICY_FIELDS")
    _require(type(policy["basis"]) is str and 0 < len(policy["basis"].strip()) <= 200, "POLICY_BASIS")
    for k in ("signal_ttl_ms", "snapshot_max_age_ms", "quote_max_age_ms"):
        _require(type(policy[k]) is int and policy[k] > 0, "POLICY_TIME")
    _require(_number(policy["max_entry_deviation_fraction"]) and 0 <= policy["max_entry_deviation_fraction"] < 1, "POLICY_DEVIATION")
    return dict(policy)


def reviewed_analysis(source_text):
    """Return only the pinned function ASTs; never execute module-level code."""
    _require(type(source_text) is str and len(source_text) < 2000000, "SOURCE_SIZE")
    tree = ast.parse(source_text)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    _require(len(nodes) == len(FUNCTIONS) and {n.name for n in nodes} == FUNCTIONS, "SOURCE_FUNCTIONS")
    selected = ast.Module(body=nodes, type_ignores=[])
    digest = hashlib.sha256(ast.dump(selected, include_attributes=False).encode()).hexdigest()
    _require(digest == SOURCE_DIGEST, "SOURCE_CHANGED_REVIEW_REQUIRED")
    return compile(selected, "<reviewed-falcon-analysis-only>", "exec")


def _frames(snapshot, config, now_ms, policy, *, public_data_authorized=False):
    public = type(snapshot) is dict and snapshot.get("synthetic") is False
    if public and public_data_authorized is True:
        snapshot = validate_snapshot(snapshot, now_ms=now_ms,
            frame_max_age_ms=policy["snapshot_max_age_ms"], quote_max_age_ms=policy["quote_max_age_ms"])
    else:
        _require(type(snapshot) is dict and snapshot.get("synthetic") is True, "SYNTHETIC_ONLY")
    _require(snapshot.get("connected") is True, "FEED_DISCONNECTED")
    _require(_identifier(snapshot.get("symbol")) and len(snapshot["symbol"]) <= 32, "SYMBOL")
    observed = snapshot.get("observed_at_ms")
    _require(_timestamp(observed) and observed <= now_ms, "SNAPSHOT_TIME")
    _require(now_ms - observed <= policy["snapshot_max_age_ms"], "SNAPSHOT_STALE")
    supplied = snapshot.get("frames")
    needed = {"15m"}
    if config["ALIGNMENT_MODE"] in ("h1", "h1_h4"):
        needed.add("1h")
    if config["ALIGNMENT_MODE"] == "h1_h4":
        needed.add("4h")
    _require(type(supplied) is dict and needed <= set(supplied) <= set(PERIODS), "FRAMES_REQUIRED")
    frames = {}
    warmup = max(80, config["EMA_SLOW"] + 5, config["ATR_LEN"], 2 * config["ADX_LEN"], 20)
    for tf in needed:
        rows, duration = supplied[tf], PERIODS[tf]
        _require(type(rows) is list and warmup + 1 <= len(rows) <= 5000, "FRAME_LENGTH")
        previous = None
        for row in rows:
            _require(type(row) in (tuple, list) and len(row) == 6, "CANDLE_FIELDS")
            ts, opening, high, low, close, volume = row
            _require(_timestamp(ts) and ts % duration == 0, "CANDLE_TIME")
            _require(previous is None or ts == previous + duration, "CANDLE_GAP_OR_DUPLICATE")
            _require(all(_number(x) and x > 0 for x in (opening, high, low, close)) and
                     _number(volume) and (volume >= 0 if public else volume > 0), "CANDLE_NUMERIC")
            _require(low <= min(opening, close) <= max(opening, close) <= high, "CANDLE_OHLC")
            previous = ts
        # Exactly one trailing forming candle. All previous candles are closed.
        _require(rows[-1][0] <= observed < rows[-1][0] + duration, "FRAME_NOT_CURRENT")
        frame = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        frame["dt"] = pd.to_datetime(frame["ts"], unit="ms", utc=True)
        frames[tf] = frame
    quote = snapshot.get("quote")
    _require(type(quote) is dict and _number(quote.get("price")) and quote["price"] > 0, "QUOTE_PRICE")
    _require(_timestamp(quote.get("at_ms")) and quote["at_ms"] <= observed, "QUOTE_TIME")
    _require(now_ms - quote["at_ms"] <= policy["quote_max_age_ms"], "QUOTE_STALE")
    return frames


class OfflineSignalSession:
    """Memory-only replay state. Restarts require explicit prior state, never live IO.

    This models deduplication, not durable delivery. Use a new session only for a
    new synthetic experiment; it is not a way to replay actual notifications.
    """

    def __init__(self, source_text, config, policy, *, session_id, prior_state):
        _require(_identifier(session_id), "SESSION_ID")
        self.code = reviewed_analysis(source_text)
        self.config, self.policy = _config(config), _policy(policy)
        self.context = hashlib.sha256(json.dumps([SOURCE_DIGEST, self.config, self.policy], sort_keys=True).encode()).hexdigest()
        _require(type(prior_state) is dict and set(prior_state) == {"session_id", "seen", "revoked", "last_now_ms", "context"}, "EXPLICIT_STATE_REQUIRED")
        _require(prior_state["session_id"] == session_id, "SESSION_MISMATCH")
        _require(type(prior_state["seen"]) is list and all(_identifier(x) for x in prior_state["seen"]), "STATE_SEEN")
        _require(type(prior_state["revoked"]) is list and all(_identifier(x) for x in prior_state["revoked"]), "STATE_REVOKED")
        _require(prior_state["last_now_ms"] is None or _timestamp(prior_state["last_now_ms"]), "STATE_TIME")
        empty_initial = not prior_state["seen"] and not prior_state["revoked"] and prior_state["last_now_ms"] is None
        _require(prior_state["context"] == self.context or (empty_initial and prior_state["context"] is None), "STATE_CONTEXT_CHANGED")
        self.session_id = session_id
        self.seen, self.revoked = set(prior_state["seen"]), set(prior_state["revoked"])
        self.last_now_ms = prior_state["last_now_ms"]

    def state(self):
        return dict(session_id=self.session_id, seen=sorted(self.seen), revoked=sorted(self.revoked), last_now_ms=self.last_now_ms, context=self.context)

    def revoke(self, signal_id):
        _require(_identifier(signal_id), "SIGNAL_ID")
        self.revoked.add(signal_id)

    def evaluate(self, snapshot, *, setup, now_ms, public_data_authorized=False):
        out = dict(status="REJECTED", reason=None, message=None, live_allowed=False,
                   delivery_allowed=False, manual_trade_authorized=False, source_qualified=False)
        try:
            _require(_timestamp(now_ms), "NOW_TIME")
            _require(self.last_now_ms is None or now_ms >= self.last_now_ms, "CLOCK_REGRESSION")
            self.last_now_ms = now_ms
            _require(setup in ("FALCON15", "FALCON30"), "SETUP")
            frames = _frames(snapshot, self.config, now_ms, self.policy,
                             public_data_authorized=public_data_authorized)
            public = snapshot["synthetic"] is False
            counters = {}

            def count(key, amount=1):
                counters[key] = counters.get(key, 0) + amount

            def fetch(symbol, timeframe="15m", limit=None):
                _require(symbol == snapshot["symbol"] and timeframe in frames, "UNAVAILABLE_FRAME")
                frame = frames[timeframe]
                return (frame.tail(limit) if limit is not None else frame).copy(deep=True)

            ns = dict(self.config, pd=pd, np=np, dtime=dtime,
                      TIMEZONE_NY=ZoneInfo("America/New_York"), TIMEFRAME="15m", BOT_NAME="FALCON",
                      funnel_inc=count, safe_fetch_ohlcv=fetch,
                      data_hora_sp_str=lambda: datetime.fromtimestamp(now_ms / 1000, timezone.utc).isoformat(),
                      attach_falcon_signal_identity=attach_falcon_signal_identity,
                      FalconSignalIdentityConstructionError=FalconSignalIdentityConstructionError)
            exec(self.code, ns)  # Pinned definitions only, no imports/top-level startup.
            closed = ns["closed_candles"](frames["15m"])
            enriched = ns["add_indicators"](closed)
            _require(all(math.isfinite(float(enriched.iloc[-1][k])) for k in ("atr", "adx", "volume_rel", "ema20", "ema50")), "INDICATORS_UNDEFINED")
            minutes = 15 if setup == "FALCON15" else 30
            # Legacy accepts a partial ORB; this boundary explicitly refuses it.
            orb = ns["get_orb_range"](closed, minutes)
            _require(orb is not None and orb["candles"] == minutes // 15, "ORB_INCOMPLETE")
            signal = ns["analyze_symbol_setup"](snapshot["symbol"], setup,
                                               dict(range_minutes=minutes, label=setup), closed)
            if signal is None:
                return dict(out, status="NO_SIGNAL", counters=counters)
            _require("signal_id" in signal, "IDENTITY_UNAVAILABLE")
            signal_id = signal["signal_id"]
            _require(signal_id not in self.revoked, "REVOKED")
            _require(signal_id not in self.seen, "DUPLICATE")
            candle_key = f"CANDLE:{setup}:{snapshot['symbol']}:{signal['signal_ts']}"
            _require(candle_key not in self.seen, "CANDLE_ALREADY_PRESENTED")
            price = snapshot["quote"]["price"]
            if signal["side"] == "LONG":
                _require(signal["stop"] < price < signal["tp50"], "LEVEL_ALREADY_CROSSED")
            else:
                _require(signal["tp50"] < price < signal["stop"], "LEVEL_ALREADY_CROSSED")
            _require(abs(price - signal["entry"]) / signal["entry"] <= self.policy["max_entry_deviation_fraction"], "ENTRY_DEVIATION")
            closed_at = signal["signal_ts"] + PERIODS["15m"]
            _require(now_ms < closed_at + self.policy["signal_ttl_ms"], "EXPIRED")
            preview = dict(synthetic=not public, signal_id=signal_id, symbol=signal["symbol"],
                           setup=setup, timeframe="15m", side=signal["side"],
                           entry=signal["entry"], stop=signal["stop"], tp50=signal["tp50"],
                           candle_closed_at_ms=closed_at, generated_at_ms=now_ms, invalidated=False)
            if public:
                preview["source"] = "BINGX_PUBLIC_SWAP"
            presenter = preview_public_signal if public else preview_signal
            result = presenter(preview, now_ms=now_ms,
                                    expires_at_ms=closed_at + self.policy["signal_ttl_ms"],
                                    validity_basis=self.policy["basis"], seen_ids=self.seen)
            if result["status"] in ("OFFLINE_PREVIEW", "PUBLIC_DATA_PREVIEW"):
                self.seen.add(signal_id)
                self.seen.add(candle_key)
                result.update(signal=preview, counters=counters, analysis_sha256=SOURCE_DIGEST)
            return result
        except OfflineInputError as exc:
            return dict(out, reason=str(exc))
        except Exception:
            # No partial recommendation and no input/exception payload disclosure.
            return dict(out, reason="ANALYSIS_FAILED")
