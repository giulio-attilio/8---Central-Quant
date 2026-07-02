# ==============================================================================
# CENTRAL QUANT - CONTEXT MANAGER
# Versão: 2026-07-02-CONTEXT-MANAGER-V1
#
# Objetivo:
# - Enriquecer eventos antes de entrarem no History/Journal.
# - Centralizar contexto operacional, temporal e de mercado em um único módulo.
# - Não alterar estratégias nem decisões dos bots.
# - Preparar a base para Learning Engine e Decision Intelligence.
# ============================================================================

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONTEXT_EXPORT_FILE = DATA_DIR / "context_export.json"
CONTEXT_SEEN_FILE = DATA_DIR / "context_seen.json"
CONTEXT_VERSION = "2026-07-02-CONTEXT-MANAGER-V1-1-COVERAGE"


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def _json_default(value):
    try:
        return str(value)
    except Exception:
        return None


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=None):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _safe_dict(value):
    return value if isinstance(value, dict) else {}


def _first(payload, keys, default=None):
    if not isinstance(payload, dict):
        return default
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return default


def _deep_get(payload, keys, default=None, max_depth=5):
    """
    Busca recursiva em payloads heterogêneos dos bots.

    V1.1 aumenta a cobertura para eventos que chegam como:
    event.raw.raw.execution_decision, event.raw.falcon_event, context aninhado, etc.
    Mantém limite de profundidade para não pesar no Render.
    """
    if not isinstance(payload, dict) or max_depth <= 0:
        return default

    direct = _first(payload, keys, None)
    if direct is not None and direct != "":
        return direct

    preferred = (
        "context",
        "raw",
        "falcon_event",
        "execution_decision",
        "risk_decision",
        "market_context",
        "details",
        "payload",
        "state",
        "event",
    )

    for container_key in preferred:
        child = payload.get(container_key)
        if isinstance(child, dict):
            value = _deep_get(child, keys, None, max_depth=max_depth - 1)
            if value is not None and value != "":
                return value

    for child in payload.values():
        if isinstance(child, dict):
            value = _deep_get(child, keys, None, max_depth=max_depth - 1)
            if value is not None and value != "":
                return value
        elif isinstance(child, list) and max_depth > 1:
            for entry in child[:5]:
                if isinstance(entry, dict):
                    value = _deep_get(entry, keys, None, max_depth=max_depth - 1)
                    if value is not None and value != "":
                        return value
    return default


def _normalize_quality(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Mantém emojis no raw, mas cria versão normalizada simples.
    upper = text.upper()
    for token in ["🟢", "🟡", "🔴", "✅", "⚠️"]:
        upper = upper.replace(token, "")
    return upper.strip()


def _normalize_regime(value):
    if value is None:
        return None
    text = str(value).upper().strip()
    if not text:
        return None
    aliases = {
        "TRENDING": "TREND",
        "TENDENCIA": "TREND",
        "TENDÊNCIA": "TREND",
        "RANGEBOUND": "RANGE",
        "LATERAL": "RANGE",
        "VOLATILE": "HIGH_VOLATILITY",
        "ALTA_VOL": "HIGH_VOLATILITY",
    }
    return aliases.get(text, text)


def _weekday_name(dt):
    names = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
    try:
        return names[int(dt.weekday())]
    except Exception:
        return None


def _time_context(payload):
    # Usa o epoch do evento quando existir; senão usa agora.
    epoch = _safe_float(_first(payload, ["epoch", "timestamp", "ts_epoch"], None), None)
    try:
        dt = datetime.fromtimestamp(epoch, TIMEZONE_BR) if epoch else agora_sp()
    except Exception:
        dt = agora_sp()
    return {
        "context_ts": dt.strftime("%d/%m/%Y %H:%M"),
        "context_epoch": float(dt.timestamp()),
        "hour": int(dt.hour),
        "minute": int(dt.minute),
        "weekday": _weekday_name(dt),
        "weekday_num": int(dt.weekday()),
        "date": dt.strftime("%Y-%m-%d"),
        "session_br": _session_br(dt.hour),
    }


def _session_br(hour):
    try:
        h = int(hour)
    except Exception:
        return None
    if 0 <= h < 6:
        return "MADRUGADA"
    if 6 <= h < 12:
        return "MANHA"
    if 12 <= h < 18:
        return "TARDE"
    return "NOITE"


def _risk_context(raw):
    decision = _deep_get(raw, ["execution_decision", "risk_decision"], None)
    decision = decision if isinstance(decision, dict) else {}
    exposure = decision.get("exposure") if isinstance(decision.get("exposure"), dict) else {}
    memory = decision.get("memory") if isinstance(decision.get("memory"), dict) else {}
    execution = decision.get("execution") if isinstance(decision.get("execution"), dict) else {}
    broker = execution.get("broker") if isinstance(execution.get("broker"), dict) else {}

    return {
        "risk_decision": decision.get("decision") or _deep_get(raw, ["decision"], None),
        "risk_allowed": decision.get("allowed"),
        "risk_warnings": decision.get("warnings") if isinstance(decision.get("warnings"), list) else [],
        "paper_positions": _safe_int(exposure.get("paper_total"), None),
        "paper_long": _safe_int(exposure.get("paper_long"), None),
        "paper_short": _safe_int(exposure.get("paper_short"), None),
        "live_positions": _safe_int(exposure.get("live_total"), None),
        "memory_rss_mb": _safe_float(memory.get("rss_mb"), None),
        "memory_usage_pct": _safe_float(memory.get("usage_pct"), None),
        "memory_blocked": memory.get("blocked"),
        "execution_mode": decision.get("mode") or execution.get("execution_mode") or broker.get("execution_mode") or _deep_get(raw, ["mode", "execution_mode"], None),
        "enable_real_trading": execution.get("enable_real_trading") if "enable_real_trading" in execution else broker.get("enable_real_trading"),
        "broker_dry_run": broker.get("broker_dry_run"),
        "requested_margin_usdt": _safe_float(decision.get("requested_margin_usdt"), None),
        "requested_leverage": _safe_int(decision.get("requested_leverage"), None),
        "requested_effective_notional_usdt": _safe_float(decision.get("requested_effective_notional_usdt"), None),
    }


def _market_context(raw):
    return {
        "market_regime": _normalize_regime(_deep_get(raw, ["market_regime", "regime", "regime_mercado"], None)),
        "btc_alignment": _deep_get(raw, ["btc_alignment", "btc_trend", "btc_context", "btc_alinhamento"], None),
        "volatility": _deep_get(raw, ["volatility", "volatility_status", "volatilidade"], None),
        "volume_status": _deep_get(raw, ["volume_status", "volume", "volume_class"], None),
        "adx": _safe_float(_deep_get(raw, ["adx", "adx_h4", "adx_h1", "adx_value"], None), None),
        "atr": _safe_float(_deep_get(raw, ["atr", "atr_pct", "atr_value"], None), None),
        "rsi": _safe_float(_deep_get(raw, ["rsi", "rsi_h1", "rsi_h4"], None), None),
        "spread": _safe_float(_deep_get(raw, ["spread", "spread_pct"], None), None),
        "timeframe": _deep_get(raw, ["timeframe", "tf"], None),
    }


def enrich_event(event):
    """
    Recebe um evento normalizado pelo history_manager e devolve uma cópia enriquecida.
    Não altera decisão, score ou lógica dos robôs.
    """
    if not isinstance(event, dict):
        return event

    item = dict(event)
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else item

    time_ctx = _time_context(item)
    risk_ctx = _risk_context(raw)
    market_ctx = _market_context(raw)

    context = {}
    context.update(time_ctx)
    context.update(risk_ctx)
    context.update(market_ctx)
    # Completa métricas importantes que nem todos os bots mandam no topo do evento.
    # Isso melhora a cobertura do Learning sem alterar decisão operacional.
    score_value = _safe_float(item.get("score"), None)
    if score_value is None:
        score_value = _safe_float(_deep_get(raw, ["score", "signal_score", "meme_score", "qualidade_pontos"], None), None)

    risk_value = _safe_float(item.get("risk_pct"), None)
    if risk_value is None:
        risk_value = _safe_float(_deep_get(raw, ["risk_pct", "risco_pct", "risk"], None), None)

    mfe_value = _safe_float(item.get("mfe_pct"), None)
    if mfe_value is None:
        mfe_value = _safe_float(_deep_get(raw, ["mfe_pct", "mfe", "max_favorable_excursion_pct"], None), None)

    mae_value = _safe_float(item.get("mae_pct"), None)
    if mae_value is None:
        mae_value = _safe_float(_deep_get(raw, ["mae_pct", "mae", "max_adverse_excursion_pct"], None), None)

    quality_value = item.get("quality") or _deep_get(raw, ["quality", "qualidade", "classification"], None)

    context.update({
        "quality_normalized": _normalize_quality(quality_value),
        "score_bucket": score_bucket(score_value),
        "risk_bucket": risk_bucket(risk_value),
        "mfe_bucket": pct_bucket(mfe_value),
        "mae_bucket": pct_bucket(mae_value),
    })

    # Campos úteis também ficam no topo para facilitar filtros simples e Learning.
    if item.get("score") is None and score_value is not None:
        item["score"] = score_value
    if item.get("risk_pct") is None and risk_value is not None:
        item["risk_pct"] = risk_value
    if item.get("mfe_pct") is None and mfe_value is not None:
        item["mfe_pct"] = mfe_value
    if item.get("mae_pct") is None and mae_value is not None:
        item["mae_pct"] = mae_value
    if item.get("quality") is None and quality_value is not None:
        item["quality"] = quality_value

    for key, value in context.items():
        if item.get(key) is None and value is not None:
            item[key] = value

    item["context"] = context
    item["context_version"] = CONTEXT_VERSION
    item["context_enriched_at"] = data_hora_sp_str()
    return item


def score_bucket(score):
    value = _safe_float(score, None)
    if value is None:
        return None
    if value >= 85:
        return "85_100"
    if value >= 75:
        return "75_84"
    if value >= 65:
        return "65_74"
    if value >= 55:
        return "55_64"
    return "0_54"


def risk_bucket(risk_pct):
    value = _safe_float(risk_pct, None)
    if value is None:
        return None
    if value <= 1.0:
        return "0_1"
    if value <= 2.0:
        return "1_2"
    if value <= 3.0:
        return "2_3"
    return "3_PLUS"


def pct_bucket(value):
    value = _safe_float(value, None)
    if value is None:
        return None
    if value < -3:
        return "LT_-3"
    if value < -1:
        return "-3_-1"
    if value < 0:
        return "-1_0"
    if value < 1:
        return "0_1"
    if value < 3:
        return "1_3"
    if value < 5:
        return "3_5"
    return "5_PLUS"


def get_status():
    return {
        "ok": True,
        "module": "context_manager",
        "version": CONTEXT_VERSION,
        "data_dir": str(DATA_DIR),
        "export_file": str(CONTEXT_EXPORT_FILE),
        "seen_file": str(CONTEXT_SEEN_FILE),
        "fields": [
            "hour", "weekday", "session_br", "market_regime", "btc_alignment",
            "volatility", "volume_status", "adx", "atr", "rsi", "paper_positions",
            "memory_usage_pct", "execution_mode", "score_bucket", "risk_bucket",
        ],
    }


def build_context_report(sample_event=None):
    status = get_status()
    lines = [
        "🧩 CONTEXT MANAGER — CENTRAL QUANT",
        f"Data/hora: {data_hora_sp_str()}",
        f"Status: {'OK' if status.get('ok') else 'ERRO'}",
        f"Versão: {status.get('version')}",
        "",
        "Contextos adicionados:",
        "- Tempo: hora, minuto, dia da semana, sessão BR",
        "- Mercado: regime, BTC, volatilidade, volume, ADX, ATR, RSI",
        "- Risco: decisão, exposição paper/live, memória, modo de execução",
        "- Buckets: score, risco, MFE, MAE",
        "",
        "Uso:",
        "Os eventos são enriquecidos antes de entrarem no History, Journal e Lifecycle.",
    ]
    if isinstance(sample_event, dict):
        enriched = enrich_event(sample_event)
        lines += ["", "Amostra:", json.dumps(enriched.get("context", {}), ensure_ascii=False, default=_json_default)[:1200]]
    return "\n".join(lines)


# Alias para compatibilidade futura.
def enrich(payload):
    return enrich_event(payload)
