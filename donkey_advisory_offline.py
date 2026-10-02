"""Pinned local Donkey analysis: no operational import, position or storage.

Uses the reviewed local ATR fallback because strategy.py is absent here. This
does not establish parity with a deployment providing a different strategy.py.
All three entry variants require explicit selection; POI/management is excluded.
"""
import ast
import hashlib
import json

from falcon_advisory_offline import _require, _number, _timestamp, _identifier, _policy, pd
from falcon_advisory_preview import preview_signal, preview_public_signal
from bingx_public_signal_source import validate_snapshot, PublicDataError, safe_error_code

FUNCTIONS = frozenset({"calcular_atr", "calcular_supertrend_df", "calcular_adx",
    "marcar_spikes", "preparar_df", "nome_limpo", "detectar_donkey_h4",
    "detectar_donkey_h4_original", "detectar_early_donkey_h4"})
SOURCE_DIGEST = "ae5e1e1caea30ef9f4e289f04e28ebcaf95fa53e86c625dde471cb794deac6a6"
SETUPS = {"DONKEY": "detectar_donkey_h4", "DONKEY_ORIGINAL": "detectar_donkey_h4_original",
          "EARLY_DONKEY": "detectar_early_donkey_h4"}
PERIODS = {"4h": 14400000, "1d": 86400000}
INTS = {"EMA_FAST", "EMA20", "EMA_MID", "EMA50", "EMA200", "ATR_LEN", "ADX_LEN",
        "SUPERTREND_PERIOD", "DONKEY_MACD_FAST", "DONKEY_MACD_SLOW", "DONKEY_MACD_SIGNAL"}
NUMBERS = {"SUPERTREND_FACTOR", "ADX_MIN", "SPIKE_RANGE_ATR_MULT", "SPIKE_BODY_ATR_MULT",
           "DONKEY_BUFFER_PCT", "TP50_R", "DONKEY_MAX_RISK_PCT"}
BOOLS = {"ENABLE_SPIKE_FILTER", "USE_MAX_RISK_FILTER"}


def reviewed_analysis(source):
    _require(type(source) is str and len(source) < 2000000, "SOURCE_SIZE")
    nodes = [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    _require(len(nodes) == len(FUNCTIONS) and {n.name for n in nodes} == FUNCTIONS, "SOURCE_FUNCTIONS")
    selected = ast.Module(body=nodes, type_ignores=[])
    _require(hashlib.sha256(ast.dump(selected, include_attributes=False).encode()).hexdigest() == SOURCE_DIGEST,
             "SOURCE_CHANGED_REVIEW_REQUIRED")
    return compile(selected, "<reviewed-donkey-only>", "exec")


def validate_config(config):
    """Validate explicit entry-analysis settings without running a strategy."""
    _require(type(config) is dict and set(config) == INTS | NUMBERS | BOOLS, "CONFIG_FIELDS")
    _require(all(type(config[k]) is int and 2 <= config[k] <= 200 for k in INTS), "CONFIG_PERIOD")
    _require(all(_number(config[k]) and 0 < config[k] <= 100 for k in NUMBERS), "CONFIG_NUMBER")
    _require(all(type(config[k]) is bool for k in BOOLS), "CONFIG_BOOL")
    _require(config["EMA20"] < config["EMA50"] and config["DONKEY_MACD_FAST"] < config["DONKEY_MACD_SLOW"], "CONFIG_ORDER")
    return dict(config)


def analyze(source, snapshot, config, policy, *, setup, now_ms, public_data_authorized=False):
    """Return one synthetic or explicitly authorized public-data local candidate.

Legacy position/exit cooldown checks are excluded from entry-only analysis;
entry cooldown writes stay in local memory. No trade registry is touched.
Public previews never authorize delivery or establish parity with position management.
"""
    base = dict(status="REJECTED", reason=None, message=None, live_allowed=False,
                delivery_allowed=False, source_qualified=False, manual_trade_authorized=False)
    try:
        _require(type(setup) is str and setup in SETUPS, "SETUP")
        config = validate_config(config)
        policy = _policy(policy)
        _require(_timestamp(now_ms), "NOW_TIME")
        public = type(snapshot) is dict and snapshot.get("synthetic") is False
        if public and public_data_authorized is True:
            snapshot = validate_snapshot(snapshot, now_ms=now_ms,
                frame_max_age_ms=policy["snapshot_max_age_ms"], quote_max_age_ms=policy["quote_max_age_ms"])
        else:
            _require(type(snapshot) is dict and snapshot.get("synthetic") is True, "SYNTHETIC_ONLY")
        _require(snapshot.get("connected") is True, "FEED_DISCONNECTED")
        _require(_identifier(snapshot.get("symbol")) and len(snapshot["symbol"]) <= 32, "SYMBOL")
        observed = snapshot.get("observed_at_ms")
        _require(_timestamp(observed) and 0 <= now_ms - observed <= policy["snapshot_max_age_ms"], "SNAPSHOT_STALE_OR_FUTURE")
        supplied = snapshot.get("frames")
        needed = {"4h", "1d"} if setup == "DONKEY_ORIGINAL" else {"4h"}
        _require(type(supplied) is dict and needed <= set(supplied) <= set(PERIODS), "FRAMES_REQUIRED")
        frames = {}
        for tf in needed:
            rows, duration = supplied[tf], PERIODS[tf]
            # Match the source's requested history lengths including forming row.
            limit = 200 if tf == "4h" else 120
            _require(type(rows) is list and limit <= len(rows) <= 5000, "FRAME_LENGTH")
            prev = None
            for row in rows:
                _require(type(row) in (list, tuple) and len(row) == 6, "CANDLE_FIELDS")
                ts, opening, high, low, close, volume = row
                _require(_timestamp(ts) and ts % duration == 0, "CANDLE_TIME")
                _require(prev is None or ts == prev + duration, "CANDLE_GAP_OR_DUPLICATE")
                _require(all(_number(x) and x > 0 for x in row[1:5]) and
                         _number(volume) and (volume >= 0 if public else volume > 0), "CANDLE_NUMERIC")
                _require(low <= min(opening, close) <= max(opening, close) <= high, "CANDLE_OHLC")
                prev = ts
            _require(rows[-1][0] <= observed < rows[-1][0] + duration, "FRAME_NOT_CURRENT")
            frames[tf] = [list(row) for row in rows[-limit:]]
        quote = snapshot.get("quote")
        _require(type(quote) is dict and _number(quote.get("price")) and quote["price"] > 0, "QUOTE_PRICE")
        _require(_timestamp(quote.get("at_ms")) and quote["at_ms"] <= observed and now_ms - quote["at_ms"] <= policy["quote_max_age_ms"], "QUOTE_STALE_OR_FUTURE")
        marks = []
        ns = dict(config, pd=pd, DONKEY_TIMEFRAME="4h", DONKEY_RISK_USDT=0,
                  ENABLE_DONKEY_H4=True, ENABLE_DONKEY_H4_ORIGINAL=True, ENABLE_EARLY_DONKEY_H4=True,
                  existe_posicao_ativa=lambda symbol: False,
                  donkey_em_cooldown_pos_saida=lambda symbol: False,
                  donkey_em_cooldown=lambda *args: False,
                  marcar_donkey_cooldown=lambda *args: marks.append(args),
                  safe_fetch_ohlcv=lambda symbol, timeframe, limit: [row[:] for row in frames[timeframe][-limit:]],
                  print=lambda *args: None)
        exec(reviewed_analysis(source), ns)
        for tf, rows in frames.items():
            enriched = ns["preparar_df"](pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]))
            _require(all(_number(float(enriched.iloc[-2][k])) for k in ("ema20", "ema50", "macd", "atr14")), "INDICATORS_UNDEFINED")
        raw = ns[SETUPS[setup]](snapshot["symbol"])
        if raw is None:
            return dict(base, status="NO_SIGNAL")
        price = quote["price"]
        _require(min(raw["sl"], raw["tp50"]) < price < max(raw["sl"], raw["tp50"]), "LEVEL_ALREADY_CROSSED")
        _require(abs(price - raw["entry"]) / raw["entry"] <= policy["max_entry_deviation_fraction"], "ENTRY_DEVIATION")
        closed = raw["timestamp"] + PERIODS["4h"]
        expiry = closed + policy["signal_ttl_ms"]
        _require(now_ms < expiry, "EXPIRED")
        signal = dict(synthetic=not public, symbol=raw["symbol"], setup=setup, timeframe="4h",
                      side=raw["side"], entry=raw["entry"], stop=raw["sl"], tp50=raw["tp50"],
                      candle_closed_at_ms=closed, generated_at_ms=now_ms, invalidated=False)
        if public:
            signal["source"] = "BINGX_PUBLIC_SWAP"
        facts = {k: v for k, v in signal.items() if k != "generated_at_ms"}
        signal["signal_id"] = "DONKEY-SIGNAL:" + hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()
        presenter = preview_public_signal if public else preview_signal
        result = presenter(signal, now_ms=now_ms, expires_at_ms=expiry, validity_basis=policy["basis"])
        if result["status"] in ("OFFLINE_PREVIEW", "PUBLIC_DATA_PREVIEW"):
            result.update(signal=signal, expires_at_ms=expiry, analysis_sha256=SOURCE_DIGEST)
        return result
    except PublicDataError as exc:
        return dict(base, reason='FRAME_EXPIRED' if safe_error_code(exc) == 'FRAME_EXPIRED' else 'ANALYSIS_FAILED')
    except Exception as exc:
        # Known validation codes only, never raw exception text/data from analysis.
        from falcon_advisory_offline import OfflineInputError
        return dict(base, reason=str(exc) if isinstance(exc, OfflineInputError) else "ANALYSIS_FAILED")


def closed_h4_indicators(source, snapshot, config, *, now_ms, frame_max_age_ms,
                         quote_max_age_ms, evaluated_through_ms=None):
    """Reuse reviewed entry indicators and iloc[-2]; no operational bot import."""
    config = validate_config(config)
    snapshot = validate_snapshot(snapshot, now_ms=now_ms,
        frame_max_age_ms=frame_max_age_ms, quote_max_age_ms=quote_max_age_ms)
    rows = snapshot["frames"].get("4h")
    _require(type(rows) is list and len(rows) >= 120, "MANUAL_TRACKING_H4_REQUIRED")
    closed = rows[-2][0] + PERIODS["4h"]
    if evaluated_through_ms is not None and closed <= evaluated_through_ms:
        return None
    ns = dict(config, pd=pd)
    exec(reviewed_analysis(source), ns)
    frame = ns["preparar_df"](pd.DataFrame(rows,
        columns=["time", "open", "high", "low", "close", "volume"]))
    candle = frame.iloc[-2]
    values = {key: float(candle[key]) for key in ("close", "ema20", "macd")}
    _require(all(_number(value) for value in values.values()), "INDICATORS_UNDEFINED")
    return dict(values, closed_at_ms=int(candle["time"]) + PERIODS["4h"])
