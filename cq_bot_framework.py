# ==============================================================================
# CENTRAL QUANT - CQ BOT FRAMEWORK
# Versão: 2026-07-02-CQ-BOT-FRAMEWORK-V1
#
# Objetivo:
# - Padronizar payloads emitidos pelos robôs da Central Quant.
# - Melhorar cobertura de Journal, Lifecycle, Context, Learning e futuros módulos.
# - Não executa ordens, não altera estratégia e não decide nada.
# ============================================================================

from datetime import datetime, timezone, timedelta

TIMEZONE_BR = timezone(timedelta(hours=-3))
FRAMEWORK_VERSION = "2026-07-02-CQ-BOT-FRAMEWORK-V1"


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def first(*values, default=None):
    for value in values:
        if value is not None and value != "" and value != [] and value != {}:
            return value
    return default


def normalize_symbol(symbol):
    s = str(symbol or "").upper().strip()
    if not s:
        return ""
    return s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "").replace("-", "")


def normalize_side(side):
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return s


def normalize_event(event_type):
    et = str(event_type or "EVENT").upper().strip()
    aliases = {
        "SIGNAL": "SIGNAL_CREATED",
        "SINAL": "SIGNAL_CREATED",
        "ENTRY": "TRADE_OPENED",
        "OPEN": "TRADE_OPENED",
        "TRADE_OPENED": "TRADE_OPENED",
        "TP50": "TP50_HIT",
        "TP50_HIT": "TP50_HIT",
        "BE": "BREAKEVEN",
        "BREAKEVEN": "BREAKEVEN",
        "TRAIL": "TRAILING_UPDATED",
        "TRAILING": "TRAILING_UPDATED",
        "TRAILING_UPDATED": "TRAILING_UPDATED",
        "STOP": "TRADE_CLOSED",
        "CLOSE": "TRADE_CLOSED",
        "CLOSED": "TRADE_CLOSED",
        "TRADE_CLOSED": "TRADE_CLOSED",
        "BLOCKED": "TRADE_BLOCKED",
        "TRADE_BLOCKED": "TRADE_BLOCKED",
    }
    return aliases.get(et, et)


def score_bucket(score):
    score = safe_float(score, None)
    if score is None:
        return "UNKNOWN"
    if score < 55:
        return "0_54"
    if score < 65:
        return "55_64"
    if score < 75:
        return "65_74"
    if score < 85:
        return "75_84"
    return "85_100"


def risk_bucket(risk_pct):
    risk = safe_float(risk_pct, None)
    if risk is None:
        return "UNKNOWN"
    if risk < 1:
        return "0_1"
    if risk < 2:
        return "1_2"
    if risk < 3:
        return "2_3"
    return "3_PLUS"


def session_br_from_hour(hour):
    try:
        h = int(hour)
    except Exception:
        return "UNKNOWN"
    if 0 <= h < 6:
        return "MADRUGADA"
    if 6 <= h < 12:
        return "MANHA"
    if 12 <= h < 18:
        return "TARDE"
    return "NOITE"


def volume_status_from_rel(volume_rel):
    rel = safe_float(volume_rel, None)
    if rel is None:
        return None
    if rel < 0.8:
        return "LOW"
    if rel >= 1.5:
        return "HIGH"
    return "NORMAL"


def market_regime_from_adx(adx):
    value = safe_float(adx, None)
    if value is None:
        return None
    if value < 18:
        return "RANGE"
    if value < 25:
        return "TRANSITION"
    return "TREND"


def volatility_from_atr_pct(atr_pct):
    value = safe_float(atr_pct, None)
    if value is None:
        return None
    if value < 0.5:
        return "LOW"
    if value > 2.5:
        return "HIGH"
    return "NORMAL"


def _execution_context(execution_decision):
    d = execution_decision if isinstance(execution_decision, dict) else {}
    exposure = d.get("exposure") if isinstance(d.get("exposure"), dict) else {}
    memory = d.get("memory") if isinstance(d.get("memory"), dict) else {}
    execution = d.get("execution") if isinstance(d.get("execution"), dict) else {}
    return {
        "risk_decision": d.get("decision") or ("ALLOW" if d.get("allowed") is True else ("DENY" if d.get("allowed") is False else None)),
        "risk_allowed": d.get("allowed"),
        "risk_reasons": d.get("reasons") or [],
        "risk_warnings": d.get("warnings") or [],
        "paper_positions": first(exposure.get("paper_total"), exposure.get("total"), default=None),
        "paper_long": exposure.get("paper_long"),
        "paper_short": exposure.get("paper_short"),
        "live_positions": first(exposure.get("live_total"), exposure.get("live"), default=None),
        "memory_usage_pct": memory.get("usage_pct"),
        "memory_rss_mb": memory.get("rss_mb"),
        "requested_margin_usdt": d.get("requested_margin_usdt"),
        "requested_leverage": d.get("requested_leverage"),
        "requested_effective_notional_usdt": d.get("requested_effective_notional_usdt"),
        "execution_mode_from_decision": d.get("mode") or execution.get("execution_mode"),
    }


def build_standard_payload(bot, bot_name=None, mode=None, position=None, event=None, extra=None, event_type=None, now_str=None):
    """Cria um payload padrão para History/Journal/Learning/Decision.

    A função é tolerante a payloads incompletos. Ela nunca deve impedir o robô de operar.
    """
    pos = position if isinstance(position, dict) else {}
    ev = event if isinstance(event, dict) else {}
    ex = extra if isinstance(extra, dict) else {}

    execution_decision = first(pos.get("execution_decision"), ex.get("execution_decision"), ev.get("execution_decision"), default={})
    if not isinstance(execution_decision, dict):
        execution_decision = {}
    exec_ctx = _execution_context(execution_decision)

    score = first(pos.get("score"), pos.get("score_falcon"), pos.get("signal_score"), ev.get("score"), ex.get("score"), default=None)
    risk = first(pos.get("risk_pct"), ev.get("risk_pct"), ex.get("risk_pct"), default=None)
    adx = first(pos.get("adx"), ev.get("adx"), ex.get("adx"), default=None)
    atr = first(pos.get("atr"), ev.get("atr"), ex.get("atr"), default=None)
    atr_pct = first(pos.get("atr_pct"), ev.get("atr_pct"), ex.get("atr_pct"), default=None)
    volume_rel = first(pos.get("volume_rel"), ev.get("volume_rel"), ex.get("volume_rel"), default=None)

    ts = now_str or ev.get("created_at") or pos.get("created_at") or data_hora_sp_str()
    dt = agora_sp()
    hour = dt.hour
    minute = dt.minute

    payload = {
        "standard_payload_version": FRAMEWORK_VERSION,
        "bot": str(bot or pos.get("bot") or "").upper(),
        "bot_name": bot_name or pos.get("bot_name") or pos.get("bot"),
        "event": normalize_event(event_type or ev.get("event_type") or ev.get("event") or ex.get("event")),
        "event_raw": str(event_type or ev.get("event_type") or ev.get("event") or ex.get("event") or "EVENT").upper(),
        "trade_id": first(pos.get("id"), pos.get("trade_id"), ev.get("trade_id"), ex.get("trade_id"), default=None),
        "setup": str(first(pos.get("setup"), ev.get("setup"), ex.get("setup"), default="") or "").upper(),
        "setup_label": first(pos.get("setup_label"), ev.get("setup_label"), ex.get("setup_label"), default=None),
        "symbol": normalize_symbol(first(pos.get("symbol"), ev.get("symbol"), ex.get("symbol"), default="")),
        "side": normalize_side(first(pos.get("side"), pos.get("direction"), ev.get("side"), ex.get("side"), default="")),
        "direction": first(pos.get("direction"), ev.get("direction"), ex.get("direction"), default=None),
        "entry": safe_float(first(pos.get("entry"), ev.get("entry"), ex.get("entry"), default=None), None),
        "stop": safe_float(first(pos.get("stop"), ev.get("stop"), ex.get("stop"), default=None), None),
        "initial_stop": safe_float(first(pos.get("initial_stop"), ev.get("initial_stop"), ex.get("initial_stop"), default=None), None),
        "tp50": safe_float(first(pos.get("tp50"), ev.get("tp50"), ex.get("tp50"), default=None), None),
        "exit_price": safe_float(first(ex.get("exit_price"), ev.get("exit_price"), pos.get("exit_price"), default=None), None),
        "result_pct": safe_float(first(ex.get("result_pct"), pos.get("result_pct"), ev.get("result_pct"), default=None), None),
        "result_r": safe_float(first(ex.get("result_r"), pos.get("result_r"), ev.get("result_r"), default=None), None),
        "mfe_pct": safe_float(first(pos.get("mfe_pct"), ev.get("mfe_pct"), ex.get("mfe_pct"), default=None), None),
        "mae_pct": safe_float(first(pos.get("mae_pct"), ev.get("mae_pct"), ex.get("mae_pct"), default=None), None),
        "mfe_r": safe_float(first(pos.get("mfe_r"), ev.get("mfe_r"), ex.get("mfe_r"), default=None), None),
        "mae_r": safe_float(first(pos.get("mae_r"), ev.get("mae_r"), ex.get("mae_r"), default=None), None),
        "giveback_pct": safe_float(first(pos.get("giveback_pct"), ev.get("giveback_pct"), ex.get("giveback_pct"), default=None), None),
        "giveback_r": safe_float(first(pos.get("giveback_r"), ev.get("giveback_r"), ex.get("giveback_r"), default=None), None),
        "score": safe_float(score, None),
        "score_bucket": score_bucket(score),
        "quality": first(pos.get("quality"), ev.get("quality"), ex.get("quality"), default=None),
        "risk_pct": safe_float(risk, None),
        "risk_bucket": risk_bucket(risk),
        "adx": safe_float(adx, None),
        "atr": safe_float(atr, None),
        "atr_pct": safe_float(atr_pct, None),
        "rsi": safe_float(first(pos.get("rsi"), ev.get("rsi"), ex.get("rsi"), default=None), None),
        "volume_rel": safe_float(volume_rel, None),
        "volume_status": first(pos.get("volume_status"), ev.get("volume_status"), ex.get("volume_status"), volume_status_from_rel(volume_rel), default=None),
        "market_regime": first(pos.get("market_regime"), ev.get("market_regime"), ex.get("market_regime"), market_regime_from_adx(adx), default=None),
        "volatility": first(pos.get("volatility"), ev.get("volatility"), ex.get("volatility"), volatility_from_atr_pct(atr_pct), default=None),
        "btc_alignment": first(pos.get("btc_alignment"), ev.get("btc_alignment"), ex.get("btc_alignment"), default=None),
        "timeframe": first(pos.get("timeframe"), ev.get("timeframe"), ex.get("timeframe"), default=None),
        "execution_mode": first(pos.get("execution_mode"), ex.get("execution_mode"), ev.get("execution_mode"), mode, exec_ctx.get("execution_mode_from_decision"), default=None),
        "mode": first(pos.get("mode"), ex.get("mode"), ev.get("mode"), mode, default=None),
        "created_at": ts,
        "event_created_at": ts,
        "hour": hour,
        "minute": minute,
        "weekday": dt.strftime("%A"),
        "session_br": session_br_from_hour(hour),
        "context": {
            "hour": hour,
            "minute": minute,
            "weekday": dt.strftime("%A"),
            "session_br": session_br_from_hour(hour),
            "score_bucket": score_bucket(score),
            "risk_bucket": risk_bucket(risk),
            "market_regime": first(pos.get("market_regime"), ev.get("market_regime"), ex.get("market_regime"), market_regime_from_adx(adx), default=None),
            "btc_alignment": first(pos.get("btc_alignment"), ev.get("btc_alignment"), ex.get("btc_alignment"), default=None),
            "volatility": first(pos.get("volatility"), ev.get("volatility"), ex.get("volatility"), volatility_from_atr_pct(atr_pct), default=None),
            "volume_status": first(pos.get("volume_status"), ev.get("volume_status"), ex.get("volume_status"), volume_status_from_rel(volume_rel), default=None),
            "adx": safe_float(adx, None),
            "atr": safe_float(atr, None),
            "atr_pct": safe_float(atr_pct, None),
            "rsi": safe_float(first(pos.get("rsi"), ev.get("rsi"), ex.get("rsi"), default=None), None),
            "paper_positions": exec_ctx.get("paper_positions"),
            "paper_long": exec_ctx.get("paper_long"),
            "paper_short": exec_ctx.get("paper_short"),
            "live_positions": exec_ctx.get("live_positions"),
            "memory_usage_pct": exec_ctx.get("memory_usage_pct"),
            "memory_rss_mb": exec_ctx.get("memory_rss_mb"),
            "execution_mode": first(pos.get("execution_mode"), ex.get("execution_mode"), ev.get("execution_mode"), mode, exec_ctx.get("execution_mode_from_decision"), default=None),
        },
        "execution_decision": execution_decision,
        "risk_decision": exec_ctx.get("risk_decision"),
        "risk_allowed": exec_ctx.get("risk_allowed"),
        "reasons": first(ex.get("reasons"), exec_ctx.get("risk_reasons"), default=[]),
        "warnings": first(ex.get("warnings"), exec_ctx.get("risk_warnings"), default=[]),
        "paper_positions": exec_ctx.get("paper_positions"),
        "memory_usage_pct": exec_ctx.get("memory_usage_pct"),
        "raw_event": ev,
    }
    return payload
