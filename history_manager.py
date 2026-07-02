# ==============================================================================
# CENTRAL QUANT - SUPER HISTORY MANAGER
# Versão: 2026-06-29-SUPER-HISTORY-V1
#
# Objetivo:
# - Criar um histórico persistente único da Central Quant.
# - Registrar decisões do Risk Manager, eventos de timeline e eventos dos robôs.
# - Expor /history, /riskstats, /exporthistory e /history/raw sem depender de banco externo.
# - Funcionar em Render Free usando JSONL local/ephemeral.
# - Ser tolerante a payloads diferentes de cada robô.
#
# Observação importante:
# - Este módulo registra eventos daqui para frente.
# - Históricos antigos que estão apenas no Redis de cada robô não são migrados automaticamente
#   nesta versão V1. A migração pode ser feita em uma V2, lendo TRADES_KEY de cada robô.
# ============================================================================

import ast
import json
import os
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict


TIMEZONE_BR = timezone(timedelta(hours=-3))

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(
    os.getenv("DATA_DIR", str(BASE_DIR / "data"))
).resolve()

DATA_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_EVENTS_FILE = DATA_DIR / "history_events.jsonl"
DECISION_LOG_FILE = DATA_DIR / "decision_log.jsonl"
TIMELINE_LOG_FILE = DATA_DIR / "timeline.jsonl"
HISTORY_EXPORT_FILE = DATA_DIR / "history_export.json"
HISTORY_SEEN_FILE = DATA_DIR / "history_seen.json"


def ensure_history_files():
    """Garante que os arquivos básicos do Super History existam."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for file_path in [
        HISTORY_EVENTS_FILE,
        DECISION_LOG_FILE,
        TIMELINE_LOG_FILE,
    ]:
        if not file_path.exists():
            file_path.touch()

    if not HISTORY_EXPORT_FILE.exists():
        HISTORY_EXPORT_FILE.write_text("{}", encoding="utf-8")

    if not HISTORY_SEEN_FILE.exists():
        HISTORY_SEEN_FILE.write_text("{}", encoding="utf-8")


ensure_history_files()


HISTORY_MAX_READ = int(os.environ.get("HISTORY_MAX_READ", "2000"))
HISTORY_REPORT_DAYS = int(os.environ.get("HISTORY_REPORT_DAYS", "7"))
HISTORY_DEDUP_ENABLED = str(os.environ.get("HISTORY_DEDUP_ENABLED", "true")).lower() in {"1", "true", "yes", "sim", "on"}
HISTORY_DEDUP_MAX_KEYS = int(os.environ.get("HISTORY_DEDUP_MAX_KEYS", "5000"))


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


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _append_jsonl(path: Path, item: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception as exc:
        print(f"ERRO HISTORY append_jsonl {path}: {exc}")
        return False


def _read_jsonl_tail(path: Path, limit=None):
    try:
        limit = int(limit or HISTORY_MAX_READ)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"raw": line})
        return rows
    except Exception as exc:
        print(f"ERRO HISTORY read_jsonl {path}: {exc}")
        return []


def _read_json(path: Path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: Path, payload):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        return True
    except Exception as exc:
        print(f"ERRO HISTORY write_json {path}: {exc}")
        return False


def normalize_symbol(symbol):
    s = str(symbol or "").upper().strip()
    if not s:
        return ""
    return s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace("-", "")


def normalize_side(side):
    s = str(side or "").upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return s


def get_status():
    """Retorna um resumo simples do estado local do history manager."""
    return {
        "ok": True,
        "data_dir": str(DATA_DIR),
        "events_file": str(HISTORY_EVENTS_FILE),
        "decision_log_file": str(DECISION_LOG_FILE),
        "timeline_file": str(TIMELINE_LOG_FILE),
        "export_file": str(HISTORY_EXPORT_FILE),
        "seen_file": str(HISTORY_SEEN_FILE),
        "max_read": HISTORY_MAX_READ,
        "report_days": HISTORY_REPORT_DAYS,
        "dedup_enabled": HISTORY_DEDUP_ENABLED,
        "dedup_max_keys": HISTORY_DEDUP_MAX_KEYS,
    }


def _first(payload, keys, default=None):
    if not isinstance(payload, dict):
        return default
    for key in keys:
        if payload.get(key) is not None:
            return payload.get(key)
    return default


def safe_parse_dict_string(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text:
        return {}
    try:
        parsed = ast.literal_eval(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        return safe_parse_dict_string(value)
    return {}


def is_bad_string_value(value):
    if value is None:
        return False
    if isinstance(value, (dict, list)):
        return True
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    if text.lower() in {"none", "null", "nan", "n/a", "na"}:
        return False
    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        return True
    if "{" in text and "}" in text:
        return True
    if "[" in text and "]" in text:
        return True
    try:
        json.loads(text)
        return True
    except Exception:
        pass
    return len(text) > 160


def sanitize_bot(value, payload=None):
    candidate = value
    if isinstance(candidate, str):
        candidate = candidate.strip()
    else:
        candidate = ""

    if not candidate or is_bad_string_value(candidate):
        if isinstance(payload, dict):
            candidate = _extract_field(payload, ["bot", "bot_name", "strategy", "source"], default="")
            if isinstance(candidate, str):
                candidate = candidate.strip()
            else:
                candidate = ""

    if not candidate or is_bad_string_value(candidate):
        return ""
    lowered = candidate.lower()
    if lowered in {"none", "null", "nan", "n/a", "na"}:
        return ""
    normalized = lowered.replace("_", " ").replace("-", " ").replace(".", " ")
    if "smart predator" in normalized or "smartpredator" in normalized or "predator" in normalized and "smart" in normalized:
        return "PREDATOR"
    if "turtle breakout pro" in normalized or "turtle" in normalized and "breakout" in normalized:
        return "TURTLE"
    if "falcon strike" in normalized or "falcon" in normalized and "strike" in normalized:
        return "FALCON"
    if normalized.startswith("predator"):
        return "PREDATOR"
    if normalized.startswith("turtle"):
        return "TURTLE"
    if normalized.startswith("falcon"):
        return "FALCON"
    return candidate.upper()


def _extract_field(payload, field_names, default=None):
    if not isinstance(payload, dict):
        return default

    def _lookup_from_mapping(mapping):
        if not isinstance(mapping, dict):
            return default
        for name in field_names:
            key = str(name)
            if key in mapping:
                return mapping[key]
            if key.upper() in {str(k).upper() for k in mapping.keys()}:
                for candidate_key, candidate_value in mapping.items():
                    if isinstance(candidate_key, str) and candidate_key.upper() == key.upper():
                        return candidate_value
        return default

    def _search(node):
        if not isinstance(node, dict):
            return default
        for name in field_names:
            value = node.get(name)
            if value is not None and value != "":
                parsed = safe_parse_dict_string(value)
                if parsed:
                    mapped = _lookup_from_mapping(parsed)
                    if mapped is not default:
                        return mapped
                if isinstance(value, str):
                    if is_bad_string_value(value):
                        continue
                    return value
                return value

        for candidate_key in ("event", "state", "details", "payload", "context", "raw_event"):
            candidate = node.get(candidate_key)
            if candidate is None or candidate == "":
                continue
            parsed = safe_parse_dict_string(candidate)
            if parsed:
                mapped = _lookup_from_mapping(parsed)
                if mapped is not default:
                    return mapped
            if isinstance(candidate, dict):
                nested = _search(candidate)
                if nested is not default and nested != "":
                    return nested

        for child_name in ("raw", "falcon_event", "execution_decision"):
            child = node.get(child_name)
            if isinstance(child, dict):
                nested = _search(child)
                if nested is not None and nested != "":
                    return nested
        for child in node.values():
            if isinstance(child, dict):
                nested = _search(child)
                if nested is not None and nested != "":
                    return nested
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, dict):
                        nested = _search(item)
                        if nested is not None and nested != "":
                            return nested
        return default

    return _search(payload)


def _extract_bot(payload):
    value = _extract_field(payload, ["bot", "bot_name", "strategy", "source"], default="")
    return sanitize_bot(value, payload)


def _extract_symbol(payload):
    value = _extract_field(payload, ["symbol", "ativo", "pair", "ticker"], default="")
    if isinstance(value, str):
        value = value.strip()
        if not value or is_bad_string_value(value):
            return ""
        return normalize_symbol(value)
    return ""


def _extract_setup(payload):
    value = _extract_field(payload, ["setup", "signal_type", "setup_label", "strategy"], default="")
    if isinstance(value, str):
        value = value.strip()
        if not value or is_bad_string_value(value):
            return ""
        return value.upper()
    return ""


def _extract_side(payload):
    value = _extract_field(payload, ["side", "direction", "signal"], default="")
    if isinstance(value, str):
        value = value.strip()
        if not value or is_bad_string_value(value):
            return ""
    return normalize_side(value)


def _event_uid(event_type, payload, source=None, trade_id=None):
    payload = payload if isinstance(payload, dict) else {}
    raw = _first(payload, ["event_id", "uid", "id"])
    if raw:
        return str(raw)
    tid = trade_id or _first(payload, ["trade_id", "position_id", "client_trade_id"])
    event_ts = _first(payload, ["event_ts", "timestamp", "created_at", "closed_at", "ts"])
    symbol = normalize_symbol(_first(payload, ["symbol", "ativo", "pair"]))
    side = normalize_side(_first(payload, ["side", "direction", "signal"]))
    setup = str(_first(payload, ["setup", "signal_type", "strategy"], "")).upper()
    return f"{source or ''}|{event_type}|{tid or ''}|{symbol}|{side}|{setup}|{event_ts or ''}"


def _dedup_seen(uid):
    if not HISTORY_DEDUP_ENABLED:
        return False
    try:
        seen = _read_json(HISTORY_SEEN_FILE, {})
        if not isinstance(seen, dict):
            seen = {}
        if uid in seen:
            return True
        seen[uid] = time.time()
        if len(seen) > HISTORY_DEDUP_MAX_KEYS:
            items = sorted(seen.items(), key=lambda x: x[1])[-HISTORY_DEDUP_MAX_KEYS:]
            seen = dict(items)
        _write_json(HISTORY_SEEN_FILE, seen)
        return False
    except Exception:
        return False


def normalize_event_type(event_type, payload=None):
    et = str(event_type or "EVENT").upper().strip()
    p = payload if isinstance(payload, dict) else {}
    status = str(_first(p, ["status", "state", "result", "decision", "resultado"], "")).upper()
    event_name = str(_extract_field(p, ["event", "event_type", "type"], "") or "").upper().strip()
    if not et and event_name:
        et = event_name

    aliases = {
        "SIGNAL": "SIGNAL_CREATED",
        "SINAL": "SIGNAL_CREATED",
        "SIGNAL_CREATED": "SIGNAL_CREATED",
        "ENTRY": "TRADE_OPENED",
        "ENTRADA": "TRADE_OPENED",
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
        "SL": "TRADE_CLOSED",
        "SL100": "TRADE_CLOSED",
        "CLOSE": "TRADE_CLOSED",
        "CLOSED": "TRADE_CLOSED",
        "CLOSES": "TRADE_CLOSED",
        "EXIT": "TRADE_CLOSED",
        "ENCERRADO": "TRADE_CLOSED",
        "FECHADO": "TRADE_CLOSED",
        "TRADE_CLOSED": "TRADE_CLOSED",
        "DENY": "TRADE_BLOCKED",
        "DENIED": "TRADE_BLOCKED",
        "BLOCKED": "TRADE_BLOCKED",
        "TRADING_BLOCKED": "TRADE_BLOCKED",
        "RISK_DENY": "TRADE_BLOCKED",
        "ALLOW": "RISK_ALLOW",
        "RISK_ALLOW": "RISK_ALLOW",
        "RISK_DECISION": "RISK_DECISION",
        "WIN": "TRADE_CLOSED",
        "LOSS": "TRADE_CLOSED",
    }

    if et in aliases:
        return aliases[et]
    if event_name in aliases:
        return aliases[event_name]
    if status in {"DENY", "DENIED", "BLOCKED", "ENCERRADO", "CLOSED", "FECHADO"}:
        return "TRADE_BLOCKED" if status in {"DENY", "DENIED", "BLOCKED"} else "TRADE_CLOSED"
    return et


def classify_event(event_type, payload=None):
    return normalize_event_type(event_type, payload)


def normalize_payload(event_type, payload=None, source=None, trade_id=None):
    raw = payload if isinstance(payload, dict) else {"value": payload}
    event = classify_event(event_type, raw)

    bot_value = _extract_bot(raw)
    fallback_bot = sanitize_bot(_first(raw, ["bot", "bot_name", "strategy", "source"], source or "CENTRAL"), raw)
    bot = str(bot_value or fallback_bot or source or "CENTRAL").upper()

    symbol = _extract_symbol(raw)
    side = _extract_side(raw)
    setup = _extract_setup(raw)

    raw_setup = _first(raw, ["setup", "signal_type", "setup_label", "strategy"], "")
    if raw_setup is not None and str(raw_setup).strip():
        setup = str(raw_setup).strip().upper()

    if bot == "TURTLE":
        if setup in {"20", "T20", "TURTLE_20", "TURTLE 20"}:
            setup = "TURTLE20"
        elif setup in {"55", "T55", "TURTLE_55", "TURTLE 55"}:
            setup = "TURTLE55"

    if not setup:
        signal_type = str(_first(raw, ["signal_type"], "") or "").upper().strip()
        raw_event = str(_first(raw, ["event", "event_type", "type"], "") or "").upper().strip()
        source_name = str(source or raw.get("source") or "").lower().strip()

        if signal_type:
            setup = signal_type
        elif event == "POI" or raw_event == "POI":
            setup = "POI"
        elif source_name == "trendpro":
            setup = "TRENDPRO"
        elif source_name == "meme":
            setup = "MEME"
        elif source_name == "donkey":
            setup = "DONKEY"
        elif source_name == "cobra":
            setup = "COBRA"
        elif source_name == "predator":
            setup = "SMART_PREDATOR"
        elif source_name == "falcon":
            setup = "FALCON"
        elif source_name == "turtle":
            setup = "TURTLE"

    tid = trade_id or _first(raw, ["trade_id", "position_id", "client_trade_id"])
    if not tid:
        stamp = agora_sp().strftime("%Y%m%d-%H%M%S")
        tid = f"{bot[:12]}-{stamp}-{symbol or 'NA'}-{uuid.uuid4().hex[:6].upper()}"

    result_pct = _safe_float(_first(raw, ["result_pct", "pnl_pct", "current_pct", "open_pct", "pnl"]), None)
    result_r = _safe_float(_first(raw, ["result_r", "pnl_r", "current_r", "open_r"]), None)
    risk_pct = _safe_float(_first(raw, ["risk_pct", "risco_pct", "risk"]), None)
    score = _safe_float(_first(raw, ["score", "signal_score", "meme_score", "qualidade_pontos"]), None)

    result_value = _first(raw, ["result", "decision", "status", "result_type"])

    item = {
        "uid": _event_uid(event, raw, source=source, trade_id=tid),
        "ts": data_hora_sp_str(),
        "epoch": time.time(),
        "event": event,
        "event_raw": str(event_type or "EVENT").upper(),
        "source": str(source or raw.get("source") or bot or "central").lower(),
        "trade_id": str(tid),
        "bot": bot,
        "symbol": symbol,
        "side": side,
        "setup": setup,
        "score": score,
        "quality": _first(raw, ["quality", "qualidade", "classification"]),
        "entry": _safe_float(_first(raw, ["entry", "entrada", "entry_price"]), None),
        "stop": _safe_float(_first(raw, ["stop", "sl", "initial_sl", "stop_atual"]), None),
        "tp50": _safe_float(_first(raw, ["tp50", "tp_50"]), None),
        "exit_price": _safe_float(_first(raw, ["exit_price", "close_price", "price", "exit"]), None),
        "risk_pct": risk_pct,
        "result_pct": result_pct,
        "result_r": result_r,
        "result": result_value,
        "reason": _first(raw, ["reason", "motivo", "exit_reason"]),
        "raw": raw,
    }
    return item


def log_event(event_type, payload=None, source=None, trade_id=None):
    try:
        item = normalize_payload(event_type, payload, source=source, trade_id=trade_id)
        uid = item.get("uid")
        if uid and _dedup_seen(uid):
            return {"ok": True, "dedup": True, "uid": uid}
        ok = _append_jsonl(HISTORY_EVENTS_FILE, item)
        if ok and item.get("event") in {"RISK_DECISION", "RISK_ALLOW", "RISK_DENY", "TRADE_BLOCKED"}:
            _append_jsonl(DECISION_LOG_FILE, item)
        if ok and item.get("event") not in {"CENTRAL_COMMAND", "BOT_COMMAND"}:
            _append_jsonl(TIMELINE_LOG_FILE, item)
        return {"ok": ok, "dedup": False, "event": item}
    except Exception as exc:
        return {"ok": False, "dedup": False, "error": str(exc), "event": {"event_type": event_type, "payload": payload}}


def _log_from_trade_event(evento, source=None):
    if not isinstance(evento, dict):
        return None
    event_type = _first(evento, ["event_type", "event", "type"], "EVENT")
    return log_event(event_type, evento, source=source, trade_id=_first(evento, ["trade_id", "position_id"]))


def wrap_bot_module(module, bot_key=None):
    """Instala hooks leves nos robôs carregados pela Central."""
    if module is None:
        return False
    source = str(bot_key or getattr(module, "BOT_NAME", getattr(module, "__name__", "bot"))).lower()
    wrapped = False

    fn = getattr(module, "registrar_evento_trade", None)
    if callable(fn) and not getattr(fn, "_history_wrapped", False):
        original = fn
        def registrar_evento_trade_wrapper(evento, *args, **kwargs):
            result = original(evento, *args, **kwargs)
            try:
                _log_from_trade_event(evento, source=source)
            except Exception as exc:
                print(f"ERRO HISTORY registrar_evento_trade {source}: {exc}")
            return result
        registrar_evento_trade_wrapper._history_wrapped = True
        setattr(module, "registrar_evento_trade", registrar_evento_trade_wrapper)
        wrapped = True

    fn = getattr(module, "record_event", None)
    if callable(fn) and not getattr(fn, "_history_wrapped", False):
        original = fn
        def record_event_wrapper(event_type, pos, extra=None, *args, **kwargs):
            result = original(event_type, pos, extra=extra, *args, **kwargs)
            try:
                payload = dict(pos or {})
                if isinstance(extra, dict):
                    payload.update(extra)
                payload["event_type"] = event_type
                log_event(event_type, payload, source=source, trade_id=payload.get("trade_id"))
            except Exception as exc:
                print(f"ERRO HISTORY record_event {source}: {exc}")
            return result
        record_event_wrapper._history_wrapped = True
        setattr(module, "record_event", record_event_wrapper)
        wrapped = True

    return wrapped


def wrap_central_functions(globals_dict):
    """Envolve funções centrais sem quebrar o comportamento original."""
    if not isinstance(globals_dict, dict):
        return False

    append_decision = globals_dict.get("append_decision_log")
    if callable(append_decision) and not getattr(append_decision, "_history_wrapped", False):
        original = append_decision
        def append_decision_log_wrapper(payload, decision_result, *args, **kwargs):
            result = original(payload, decision_result, *args, **kwargs)
            try:
                merged = {}
                if isinstance(payload, dict):
                    merged.update(payload)
                if isinstance(decision_result, dict):
                    merged.update(decision_result)
                if isinstance(result, dict):
                    merged.update(result)
                log_event("RISK_DECISION", merged, source="central", trade_id=merged.get("trade_id"))
            except Exception as exc:
                print("ERRO HISTORY append_decision_log:", exc)
            return result
        append_decision_log_wrapper._history_wrapped = True
        globals_dict["append_decision_log"] = append_decision_log_wrapper

    append_timeline = globals_dict.get("append_timeline_event")
    if callable(append_timeline) and not getattr(append_timeline, "_history_wrapped", False):
        original = append_timeline
        def append_timeline_event_wrapper(event_type, bot=None, symbol=None, side=None, trade_id=None, state=None, details=None, *args, **kwargs):
            result = original(event_type, bot=bot, symbol=symbol, side=side, trade_id=trade_id, state=state, details=details, *args, **kwargs)
            try:
                payload = dict(details or {}) if isinstance(details, dict) else {"details": details}
                payload.update({"bot": bot, "symbol": symbol, "side": side, "state": state})
                log_event(event_type, payload, source="central", trade_id=trade_id)
            except Exception as exc:
                print("ERRO HISTORY append_timeline_event:", exc)
            return result
        append_timeline_event_wrapper._history_wrapped = True
        globals_dict["append_timeline_event"] = append_timeline_event_wrapper

    loaded = globals_dict.get("LOADED_BOTS")
    if isinstance(loaded, dict):
        for key, module in list(loaded.items()):
            try:
                wrap_bot_module(module, key)
            except Exception as exc:
                print(f"ERRO HISTORY wrap bot {key}: {exc}")

    return True


def load_events(limit=None, filters=None):
    events = _read_jsonl_tail(HISTORY_EVENTS_FILE, limit=limit or HISTORY_MAX_READ)
    if not filters:
        return events

    filters = filters or {}
    bot = str(filters.get("bot") or "").strip().upper()
    symbol = str(filters.get("symbol") or "").strip().upper()
    setup = str(filters.get("setup") or "").strip().upper()
    side = str(filters.get("side") or "").strip().upper()
    result = str(filters.get("result") or "").strip().upper()
    event_type = str(filters.get("event_type") or "").strip().upper()
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    def _match_date(ts_value):
        if not ts_value:
            return True
        try:
            dt = datetime.strptime(str(ts_value), "%d/%m/%Y %H:%M")
        except Exception:
            return True
        if date_from:
            try:
                if dt < datetime.strptime(str(date_from), "%d/%m/%Y %H:%M"):
                    return False
            except Exception:
                pass
        if date_to:
            try:
                if dt > datetime.strptime(str(date_to), "%d/%m/%Y %H:%M"):
                    return False
            except Exception:
                pass
        return True

    filtered = []
    for event in events:
        if bot and str(event.get("bot") or "").upper() != bot:
            continue
        if symbol and str(event.get("symbol") or "").upper() != symbol:
            continue
        if setup and str(event.get("setup") or "").upper() != setup:
            continue
        if side and str(event.get("side") or "").upper() != side:
            continue
        if result and str(event.get("result") or "").upper() != result:
            continue
        if event_type and str(event.get("event") or "").upper() != event_type:
            continue
        if not _match_date(event.get("ts")):
            continue
        filtered.append(event)
    return filtered


def calculate_stats(events=None, filters=None, rows=None):
    rows = rows if rows is not None else (events if events is not None else load_events(filters=filters))
    rows = list(rows or [])

    totals = {
        "total_events": len(rows),
        "signals": 0,
        "entries": 0,
        "closed": 0,
        "blocked": 0,
        "denied": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "tp50": 0,
        "stops": 0,
        "pnl_total_pct": 0.0,
        "pnl_avg_pct": 0.0,
    }

    for event in rows:
        raw = event.get("raw") if isinstance(event.get("raw"), dict) else {}

        event_name = normalize_event_type(
            event.get("event") or event.get("event_type") or event.get("type"),
            event,
        )

        reason = str(
            event.get("reason")
            or event.get("result")
            or event.get("resultado")
            or event.get("decision")
            or event.get("status")
            or raw.get("result_type")
            or ""
        ).upper()

        raw_reason = str(
            event.get("reason")
            or event.get("result")
            or event.get("resultado")
            or event.get("decision")
            or event.get("status")
            or event.get("event")
            or event.get("event_type")
            or event.get("type")
            or raw.get("event")
            or raw.get("event_type")
            or raw.get("result_type")
            or ""
        ).lower()

        if event_name == "SIGNAL_CREATED":
            totals["signals"] += 1

        if event_name == "TRADE_OPENED":
            totals["entries"] += 1

        if event_name == "TRADE_CLOSED":
            totals["closed"] += 1

        if event_name in {"TRADE_BLOCKED", "RISK_DECISION"}:
            totals["blocked"] += 1
            if reason in {"DENY", "DENIED", "BLOCKED"} or "deny" in raw_reason or "blocked" in raw_reason:
                totals["denied"] += 1

        if event_name == "TP50_HIT":
            totals["tp50"] += 1

        if event_name == "BREAKEVEN":
            totals["breakeven"] += 1

        if event_name == "TRADE_CLOSED" and (
            reason in {"STOP", "STOPLOSS", "SL", "STOP_LOSS", "LOSS"}
            or "stop" in raw_reason
            or "sl" in raw_reason
        ):
            totals["stops"] += 1

        if event_name == "TRADE_CLOSED":
            pnl = (
                _safe_float(event.get("pnl_pct"), None)
                or _safe_float(event.get("result_pct"), None)
                or _safe_float(event.get("pnl"), None)
                or _safe_float(raw.get("pnl"), None)
                or _safe_float(raw.get("pnl_pct"), None)
                or _safe_float(raw.get("result_pct"), None)
                or _safe_float(event.get("resultado_pct"), None)
            )

            if pnl is None:
                pnl = _safe_float(event.get("result"), None)

            result_type = str(
                event.get("result")
                or raw.get("result_type")
                or raw.get("result")
                or ""
            ).upper()

            if pnl is not None:
                totals["pnl_total_pct"] += pnl

                if pnl > 0 or result_type == "WIN":
                    totals["wins"] += 1
                elif pnl < 0 or result_type == "LOSS":
                    totals["losses"] += 1
                else:
                    totals["breakeven"] += 1
            else:
                if result_type == "WIN":
                    totals["wins"] += 1
                elif result_type == "LOSS":
                    totals["losses"] += 1
                elif result_type in {"BE", "BREAKEVEN"}:
                    totals["breakeven"] += 1

    if totals["closed"]:
        totals["pnl_avg_pct"] = round(totals["pnl_total_pct"] / totals["closed"], 4)
    else:
        totals["pnl_avg_pct"] = 0.0

    totals["pnl_total_pct"] = round(totals["pnl_total_pct"], 4)
    return totals


def query_history(bot=None, symbol=None, setup=None, side=None, result=None, days=None, limit=None):
    filters = {}
    if bot:
        filters["bot"] = bot
    if symbol:
        filters["symbol"] = symbol
    if setup:
        filters["setup"] = setup
    if side:
        filters["side"] = side
    if result:
        filters["result"] = result

    if days:
        try:
            days_value = int(days)
        except Exception:
            days_value = None
        if days_value is not None and days_value > 0:
            cutoff = (agora_sp() - timedelta(days=days_value)).strftime("%d/%m/%Y %H:%M")
            filters["date_from"] = cutoff

    events = load_events(limit=limit or HISTORY_MAX_READ, filters=filters)
    return {
        "filters": {
            "bot": bot or None,
            "symbol": symbol or None,
            "setup": setup or None,
            "side": side or None,
            "result": result or None,
            "days": int(days) if str(days or "").strip().isdigit() else None,
            "limit": int(limit) if str(limit or "").strip().isdigit() else None,
        },
        "stats": calculate_stats(rows=events),
        "events": events,
    }


def calculate_performance_metrics(events=None):
    rows = list(events or [])
    closed_trades = []
    for event in rows:
        event_name = normalize_event_type(event.get("event") or event.get("event_type") or event.get("type"), event)
        if event_name != "TRADE_CLOSED":
            continue
        pnl = _safe_float(event.get("pnl_pct") or event.get("result_pct") or event.get("pnl") or event.get("resultado_pct"), None)
        if pnl is None:
            pnl = _safe_float(event.get("result"), None)
        if pnl is None:
            continue
        closed_trades.append(pnl)

    trades = len(closed_trades)
    wins = sum(1 for pnl in closed_trades if pnl > 0)
    losses = sum(1 for pnl in closed_trades if pnl < 0)
    breakeven = sum(1 for pnl in closed_trades if pnl == 0)
    win_rate_pct = round((wins / trades) * 100, 2) if trades else 0.0
    pnl_total_pct = round(sum(closed_trades), 4)
    pnl_avg_pct = round(pnl_total_pct / trades, 4) if trades else 0.0

    win_values = [pnl for pnl in closed_trades if pnl > 0]
    loss_values = [abs(pnl) for pnl in closed_trades if pnl < 0]
    avg_win_pct = round(sum(win_values) / len(win_values), 4) if win_values else 0.0
    avg_loss_pct = round(sum(loss_values) / len(loss_values), 4) if loss_values else 0.0
    payoff_ratio = round(avg_win_pct / avg_loss_pct, 4) if avg_loss_pct else 0.0
    profit_factor_pct = round(sum(win_values) / sum(loss_values), 4) if loss_values and sum(win_values) else 0.0
    expectancy_pct = round((win_rate_pct / 100) * avg_win_pct - ((100 - win_rate_pct) / 100) * avg_loss_pct, 4) if trades else 0.0

    max_win_streak = 0
    max_loss_streak = 0
    current_win_streak = 0
    current_loss_streak = 0
    for pnl in closed_trades:
        if pnl > 0:
            current_win_streak += 1
            current_loss_streak = 0
            max_win_streak = max(max_win_streak, current_win_streak)
        elif pnl < 0:
            current_loss_streak += 1
            current_win_streak = 0
            max_loss_streak = max(max_loss_streak, current_loss_streak)
        else:
            current_win_streak = 0
            current_loss_streak = 0

    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": win_rate_pct,
        "pnl_total_pct": pnl_total_pct,
        "pnl_avg_pct": pnl_avg_pct,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "payoff_ratio": payoff_ratio,
        "profit_factor_pct": profit_factor_pct,
        "expectancy_pct": expectancy_pct,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
    }


def group_stats(group_by="bot", events=None, filters=None):
    rows = events if events is not None else load_events(filters=filters)
    rows = list(rows or [])
    if group_by not in {"bot", "symbol", "setup"}:
        raise ValueError("group_by deve ser 'bot', 'symbol' ou 'setup'")

    buckets = defaultdict(list)
    for event in rows:
        key = None
        if group_by == "bot":
            key = sanitize_bot(_extract_field(event, ["bot", "bot_name", "strategy", "source"], default=""), event)
            key = key or sanitize_bot(event.get("bot"), event)
            key = key or "N/A"
        elif group_by == "symbol":
            symbol = _extract_symbol(event)
            key = symbol or str(event.get("symbol") or "N/A").upper()
            key = key or "N/A"
        else:
            setup = _extract_setup(event)
            key = setup or str(event.get("setup") or "N/A").upper()
            key = key or "N/A"
        buckets[key].append(event)

    return {key: calculate_stats(rows=items) for key, items in sorted(buckets.items())}


def build_history_payload(limit=None):
    events = load_events(limit=limit or HISTORY_MAX_READ)
    by_event = Counter()
    by_bot = Counter()
    by_symbol = Counter()
    by_setup = Counter()
    by_side = Counter()
    closed = []
    blocked = []
    tp50 = []

    for e in events:
        event = e.get("event") or "EVENT"
        by_event[event] += 1
        bot_key = sanitize_bot(_extract_field(e, ["bot", "bot_name", "strategy", "source"], default=""), e) or sanitize_bot(e.get("bot"), e) or "N/A"
        symbol_key = _extract_symbol(e) or str(e.get("symbol") or "N/A").upper() or "N/A"
        setup_key = _extract_setup(e) or str(e.get("setup") or "N/A").upper() or "N/A"
        if bot_key:
            by_bot[bot_key] += 1
        if symbol_key:
            by_symbol[symbol_key] += 1
        if setup_key:
            by_setup[setup_key] += 1
        if e.get("side"):
            by_side[e.get("side")] += 1
        if event == "TRADE_CLOSED":
            closed.append(e)
        if event == "TRADE_BLOCKED" or str(e.get("result") or "").upper() in {"DENY", "DENIED", "BLOCKED"}:
            blocked.append(e)
        if event == "TP50_HIT":
            tp50.append(e)

    pnl_values = [_safe_float(x.get("result_pct"), None) for x in closed]
    pnl_values = [x for x in pnl_values if x is not None]
    r_values = [_safe_float(x.get("result_r"), None) for x in closed]
    r_values = [x for x in r_values if x is not None]
    wins = len([x for x in pnl_values if x > 0])
    losses = len([x for x in pnl_values if x < 0])
    be = len([x for x in pnl_values if x == 0])
    gross_win = sum([x for x in pnl_values if x > 0])
    gross_loss = abs(sum([x for x in pnl_values if x < 0]))

    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "files": {
            "history_events": str(HISTORY_EVENTS_FILE),
            "decision_log": str(DECISION_LOG_FILE),
            "timeline": str(TIMELINE_LOG_FILE),
            "export": str(HISTORY_EXPORT_FILE),
        },
        "totals": {
            "events": len(events),
            "signals": by_event.get("SIGNAL_CREATED", 0),
            "opened": by_event.get("TRADE_OPENED", 0),
            "closed": len(closed),
            "blocked": len(blocked),
            "tp50": len(tp50),
            "breakeven": by_event.get("BREAKEVEN", 0),
            "trailing": by_event.get("TRAILING_UPDATED", 0),
        },
        "performance": {
            "wins": wins,
            "losses": losses,
            "breakeven": be,
            "win_rate_pct": round((wins / max(wins + losses, 1)) * 100, 2),
            "pnl_total_pct": round(sum(pnl_values), 4),
            "pnl_avg_pct": round(sum(pnl_values) / max(len(pnl_values), 1), 4) if pnl_values else 0.0,
            "r_total": round(sum(r_values), 4),
            "r_avg": round(sum(r_values) / max(len(r_values), 1), 4) if r_values else 0.0,
            "profit_factor_pct": round(gross_win / gross_loss, 4) if gross_loss > 0 else (999 if gross_win > 0 else 0),
        },
        "by_event": dict(by_event.most_common()),
        "by_bot": dict(by_bot.most_common()),
        "by_symbol": dict(by_symbol.most_common(30)),
        "by_setup": dict(by_setup.most_common(30)),
        "by_side": dict(by_side.most_common()),
        "recent_events": events[-50:],
    }


def build_history_report(days=None):
    payload = build_history_payload()
    totals = payload.get("totals", {})
    perf = payload.get("performance", {})
    by_bot = payload.get("by_bot", {})
    by_symbol = payload.get("by_symbol", {})

    lines = [
        "📚 SUPER HISTORY — CENTRAL QUANT",
        f"Data/hora: {payload.get('generated_at')}",
        "",
        "Eventos registrados:",
        f"Sinais: {totals.get('signals', 0)}",
        f"Entradas: {totals.get('opened', 0)}",
        f"Encerrados: {totals.get('closed', 0)}",
        f"Bloqueados: {totals.get('blocked', 0)}",
        f"TP50: {totals.get('tp50', 0)}",
        f"BE: {totals.get('breakeven', 0)}",
        f"Trailing: {totals.get('trailing', 0)}",
        "",
        "Performance registrada:",
        f"Wins: {perf.get('wins', 0)} | Losses: {perf.get('losses', 0)} | BE: {perf.get('breakeven', 0)}",
        f"Win rate: {perf.get('win_rate_pct', 0)}%",
        f"PnL total: {perf.get('pnl_total_pct', 0)}%",
        f"R total: {perf.get('r_total', 0)}R",
        f"Profit Factor %: {perf.get('profit_factor_pct', 0)}",
        "",
        "Eventos por bot:",
    ]
    if by_bot:
        for bot, count in list(by_bot.items())[:12]:
            lines.append(f"- {bot}: {count}")
    else:
        lines.append("- Ainda sem eventos de robôs no Super History.")

    lines += ["", "Top ativos:"]
    if by_symbol:
        for symbol, count in list(by_symbol.items())[:12]:
            lines.append(f"- {symbol}: {count}")
    else:
        lines.append("- Ainda sem ativos registrados.")

    lines += [
        "",
        "Observação:",
        "O Super History registra eventos novos a partir desta versão. Histórico antigo do Redis pode ser migrado depois em uma V2.",
    ]
    return "\n".join(lines)


def build_riskstats_payload():
    payload = build_history_payload()
    events = load_events()
    closed_by_bot = defaultdict(list)
    closed_by_symbol = defaultdict(list)
    blocked_by_reason = Counter()

    for e in events:
        if e.get("event") == "TRADE_CLOSED":
            closed_by_bot[e.get("bot") or "N/A"].append(e)
            closed_by_symbol[e.get("symbol") or "N/A"].append(e)
        if e.get("event") == "TRADE_BLOCKED":
            reason = e.get("reason") or e.get("result") or "N/A"
            blocked_by_reason[str(reason)] += 1

    def stats(rows):
        pnls = [_safe_float(x.get("result_pct"), None) for x in rows]
        pnls = [x for x in pnls if x is not None]
        wins = len([x for x in pnls if x > 0])
        losses = len([x for x in pnls if x < 0])
        gross_win = sum([x for x in pnls if x > 0])
        gross_loss = abs(sum([x for x in pnls if x < 0]))
        return {
            "trades": len(rows),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(wins / max(wins + losses, 1) * 100, 2),
            "pnl_total_pct": round(sum(pnls), 4),
            "pnl_avg_pct": round(sum(pnls) / max(len(pnls), 1), 4) if pnls else 0.0,
            "profit_factor_pct": round(gross_win / gross_loss, 4) if gross_loss > 0 else (999 if gross_win > 0 else 0),
        }

    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "summary": payload.get("performance", {}),
        "totals": payload.get("totals", {}),
        "by_bot_closed": {bot: stats(rows) for bot, rows in closed_by_bot.items()},
        "by_symbol_closed": {symbol: stats(rows) for symbol, rows in list(closed_by_symbol.items())[:50]},
        "blocked_by_reason": dict(blocked_by_reason.most_common(30)),
    }


def build_riskstats_report():
    payload = build_riskstats_payload()
    summary = payload.get("summary", {})
    lines = [
        "📊 RISKSTATS — SUPER HISTORY",
        f"Data/hora: {payload.get('generated_at')}",
        "",
        f"Trades encerrados: {payload.get('totals', {}).get('closed', 0)}",
        f"Win rate: {summary.get('win_rate_pct', 0)}%",
        f"PnL total: {summary.get('pnl_total_pct', 0)}%",
        f"R total: {summary.get('r_total', 0)}R",
        f"Profit Factor %: {summary.get('profit_factor_pct', 0)}",
        "",
        "Por robô:",
    ]
    by_bot = payload.get("by_bot_closed", {})
    if by_bot:
        for bot, s in by_bot.items():
            lines.append(f"- {bot}: {s.get('trades')} trades | WR {s.get('win_rate_pct')}% | PnL {s.get('pnl_total_pct')}% | PF {s.get('profit_factor_pct')}")
    else:
        lines.append("- Ainda sem trades encerrados no Super History.")

    blocked = payload.get("blocked_by_reason", {})
    lines += ["", "Bloqueios por motivo:"]
    if blocked:
        for reason, count in blocked.items():
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- Ainda sem bloqueios registrados.")
    return "\n".join(lines)


def build_export_payload():
    payload = build_history_payload(limit=HISTORY_MAX_READ)
    payload["riskstats"] = build_riskstats_payload()
    _write_json(HISTORY_EXPORT_FILE, payload)
    return payload


def build_export_report():
    payload = build_export_payload()
    return (
        "📦 EXPORT HISTORY — CENTRAL QUANT\n\n"
        f"Arquivo gerado: {HISTORY_EXPORT_FILE}\n"
        f"Eventos exportados: {payload.get('totals', {}).get('events', 0)}\n"
        f"Gerado em: {payload.get('generated_at')}"
    )


def audit_events(events=None):
    rows = list(events if events is not None else load_events())

    required_by_event = {
        "TRADE_OPENED": ["bot", "symbol", "side", "setup", "entry", "stop", "tp50"],
        "TP50_HIT": ["bot", "symbol", "side", "setup", "tp50"],
        "BREAKEVEN": ["bot", "symbol", "side", "setup"],
        "BREAKEVEN_MOVED": ["bot", "symbol", "side", "setup"],
        "TRAILING_UPDATED": ["bot", "symbol", "side", "setup"],
        "TRADE_CLOSED": ["bot", "symbol", "side", "setup", "entry", "exit_price", "result_pct"],
        "TRADE_BLOCKED": ["bot", "symbol", "side", "setup", "result"],
        "RISK_DECISION": ["bot", "symbol", "side", "setup", "result"],
        "SIGNAL_CREATED": ["bot", "symbol", "side", "setup"],
    }

    admin_events = {
        "CENTRAL_COMMAND",
        "MEMORY",
        "HEALTH",
        "BOT_STATUS",
        "CENTRAL_STATUS",
        "WATCHDOG",
        "STARTUP",
        "RISK_SNAPSHOT",
    }

    audit = {}
    for event in rows:
        bot = str(event.get("bot") or "N/A").upper()
        event_name = normalize_event_type(
            event.get("event") or event.get("event_type") or event.get("type"),
            event,
        )

        if bot not in audit:
            audit[bot] = {
                "events": 0,
                "by_event": {},
                "missing": {},
                "examples": {},
            }

        audit[bot]["events"] += 1
        audit[bot]["by_event"][event_name] = audit[bot]["by_event"].get(event_name, 0) + 1

        if event_name in admin_events:
            continue

        required = required_by_event.get(event_name, ["bot", "symbol", "side", "setup"])
        for field in required:
            value = event.get(field)
            if value is None or value == "":
                key = f"missing_{field}"
                audit[bot]["missing"][key] = audit[bot]["missing"].get(key, 0) + 1

                if key not in audit[bot]["examples"]:
                    audit[bot]["examples"][key] = {
                        "event": event_name,
                        "symbol": event.get("symbol"),
                        "setup": event.get("setup"),
                        "trade_id": event.get("trade_id"),
                        "raw_event": event.get("event_raw"),
                    }

    total_events = sum(item["events"] for item in audit.values())
    total_missing = sum(sum(item["missing"].values()) for item in audit.values())

    return {
        "ok": True,
        "generated_at": data_hora_sp_str(),
        "summary": {
            "events": total_events,
            "bots": len(audit),
            "missing_fields": total_missing,
            "quality_score": round(100 - min(100, (total_missing / max(total_events, 1)) * 10), 2),
        },
        "bots": audit,
    }