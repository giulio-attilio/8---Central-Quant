# ==========================================================
# SUPER CENTRAL QUANT - EVENT BUS
# Versao: 2026-06-28-EVENT-BUS-V1
#
# Objetivo:
# - Criar uma porta unica para todos os robos enviarem eventos.
# - Padronizar payloads antes de gravar no Super History.
# - Evitar duplicidades simples por dedupe_key/event_id.
# - Nao executa trades. Nao altera estrategia.
# ==========================================================

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import history_manager
except Exception as exc:
    history_manager = None
    HISTORY_MANAGER_ERROR = str(exc)
else:
    HISTORY_MANAGER_ERROR = None

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
EVENT_BUS_SEEN_FILE = DATA_DIR / "event_bus_seen.json"
EVENT_BUS_LOG_FILE = DATA_DIR / "event_bus.jsonl"
MAX_SEEN_KEYS = int(os.environ.get("EVENT_BUS_MAX_SEEN_KEYS", "20000"))


def agora_sp():
    return datetime.now(TIMEZONE_BR)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def _safe_upper(value):
    return str(value or "").strip().upper()


def _normalize_symbol(value):
    txt = _safe_upper(value)
    return txt.replace("/", "").replace(":USDT", "").replace("-", "")


def _json_default(obj):
    try:
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
    except Exception:
        pass
    return str(obj)


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace("R", "").replace("+", "").replace(",", ".").strip()
            if value == "":
                return default
        return float(value)
    except Exception:
        return default


def _read_json(path, default):
    try:
        p = Path(path)
        if not p.exists():
            return default
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path, payload):
    try:
        Path(path).parent.mkdir(exist_ok=True)
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        return True
    except Exception:
        return False


def _append_jsonl(path, payload):
    try:
        Path(path).parent.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception:
        return False


def _fingerprint(payload):
    raw = payload if isinstance(payload, dict) else {"value": payload}
    explicit = raw.get("event_id") or raw.get("dedupe_key") or raw.get("idempotency_key")
    if explicit:
        return str(explicit)
    basis = {
        "event_type": raw.get("event_type") or raw.get("event") or raw.get("type"),
        "bot": raw.get("bot"),
        "symbol": raw.get("symbol"),
        "setup": raw.get("setup"),
        "side": raw.get("side"),
        "trade_id": raw.get("trade_id") or raw.get("id"),
        "created_at": raw.get("created_at") or raw.get("event_created_at") or raw.get("ts"),
        "result_pct": raw.get("result_pct") or raw.get("pnl_pct"),
        "result_r": raw.get("result_r") or raw.get("pnl_r"),
    }
    txt = json.dumps(basis, ensure_ascii=False, sort_keys=True, default=_json_default)
    return hashlib.sha256(txt.encode("utf-8")).hexdigest()[:32]


def _seen_contains_or_add(key):
    data = _read_json(EVENT_BUS_SEEN_FILE, {"keys": []})
    keys = data.get("keys") if isinstance(data, dict) else []
    if not isinstance(keys, list):
        keys = []
    if key in set(keys):
        return True
    keys.append(key)
    if len(keys) > MAX_SEEN_KEYS:
        keys = keys[-MAX_SEEN_KEYS:]
    _write_json(EVENT_BUS_SEEN_FILE, {"updated_at": data_hora_sp_str(), "keys": keys})
    return False


def normalize_event(event_type=None, payload=None, source="event_bus"):
    data = dict(payload or {}) if isinstance(payload, dict) else {"value": payload}
    et = event_type or data.get("event_type") or data.get("event") or data.get("type") or "EVENT"
    bot = data.get("bot") or data.get("robot") or data.get("strategy")
    symbol = data.get("symbol") or data.get("ativo") or data.get("pair")
    side = data.get("side") or data.get("direction") or data.get("lado")
    setup = data.get("setup") or data.get("setup_label")
    trade_id = data.get("trade_id") or data.get("id") or data.get("position_id")
    normalized = {
        "event_type": _safe_upper(et),
        "bot": _safe_upper(bot),
        "symbol": _normalize_symbol(symbol),
        "side": _safe_upper(side),
        "setup": str(setup or ""),
        "trade_id": str(trade_id or ""),
        "source": str(source or data.get("source") or "event_bus"),
        "result": _safe_upper(data.get("result") or data.get("status") or data.get("decision")),
        "pnl_pct": _safe_float(data.get("pnl_pct") or data.get("result_pct") or data.get("pnl"), None),
        "pnl_r": _safe_float(data.get("pnl_r") or data.get("result_r"), None),
        "risk_pct": _safe_float(data.get("risk_pct") or data.get("risk"), None),
        "score": _safe_float(data.get("score") or data.get("score_falcon"), None),
        "raw": data,
    }
    return normalized


def emit(event_type=None, payload=None, source="event_bus", dedupe=True):
    """Emite um evento padronizado para o Super History."""
    if history_manager is None:
        return {"ok": False, "error": HISTORY_MANAGER_ERROR or "history_manager unavailable"}

    normalized = normalize_event(event_type=event_type, payload=payload, source=source)
    raw = normalized.get("raw") or {}
    key = _fingerprint({**raw, **normalized})

    if dedupe and _seen_contains_or_add(key):
        return {"ok": True, "duplicate": True, "dedupe_key": key, "event_type": normalized.get("event_type")}

    raw["event_bus"] = {
        "dedupe_key": key,
        "received_at": data_hora_sp_str(),
        "source": source,
        "version": "2026-06-28-EVENT-BUS-V1",
    }
    normalized["raw"] = raw

    try:
        item = history_manager.log_event(
            normalized.get("event_type"),
            {
                **raw,
                "bot": normalized.get("bot"),
                "symbol": normalized.get("symbol"),
                "side": normalized.get("side"),
                "setup": normalized.get("setup"),
                "trade_id": normalized.get("trade_id"),
                "result": normalized.get("result"),
                "pnl_pct": normalized.get("pnl_pct"),
                "pnl_r": normalized.get("pnl_r"),
                "risk_pct": normalized.get("risk_pct"),
                "score": normalized.get("score"),
                "dedupe_key": key,
            },
            source=normalized.get("source"),
            trade_id=normalized.get("trade_id"),
        )
        _append_jsonl(EVENT_BUS_LOG_FILE, {"ts": data_hora_sp_str(), "dedupe_key": key, "normalized": normalized})
        return {"ok": True, "duplicate": False, "dedupe_key": key, "event": item}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "dedupe_key": key}


def emit_from_http(payload):
    data = dict(payload or {}) if isinstance(payload, dict) else {"value": payload}
    event_type = data.get("event_type") or data.get("event") or data.get("type")
    source = data.get("source") or "http_event_bus"
    dedupe = str(data.get("dedupe", "true")).lower() not in {"0", "false", "no", "nao", "não"}
    return emit(event_type=event_type, payload=data, source=source, dedupe=dedupe)
