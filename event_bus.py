# ==============================================================================
# CENTRAL QUANT - EVENT BUS
# Versão: 2026-06-29-EVENT-BUS-V1
#
# Objetivo:
# - Receber eventos HTTP internos em /eventbus/emit.
# - Deduplicar eventos por event_id/uid/trade_id.
# - Encaminhar tudo para history_manager.log_event().
# ============================================================================

import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import history_manager
    HISTORY_MANAGER_ERROR = None
except Exception as exc:
    history_manager = None
    HISTORY_MANAGER_ERROR = str(exc)

TIMEZONE_BR = timezone(timedelta(hours=-3))
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
EVENT_BUS_LOG_FILE = DATA_DIR / "event_bus.jsonl"
EVENT_BUS_SEEN_FILE = DATA_DIR / "event_bus_seen.json"
EVENT_BUS_SEEN_MAX = int(os.environ.get("EVENT_BUS_SEEN_MAX", "5000"))


def data_hora_sp_str():
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M")


def _json_default(value):
    try:
        return str(value)
    except Exception:
        return None


def _read_json(path, default):
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, payload):
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_default)
        return True
    except Exception:
        return False


def _append_jsonl(path, item):
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception:
        return False


def _uid(payload):
    if not isinstance(payload, dict):
        return f"raw-{time.time()}"
    for key in ["event_id", "uid", "id"]:
        if payload.get(key):
            return str(payload.get(key))
    return "|".join([
        str(payload.get("event") or payload.get("event_type") or payload.get("type") or "EVENT"),
        str(payload.get("trade_id") or payload.get("position_id") or ""),
        str(payload.get("bot") or payload.get("source") or ""),
        str(payload.get("symbol") or ""),
        str(payload.get("timestamp") or payload.get("created_at") or payload.get("ts") or ""),
    ])


def _seen(uid):
    try:
        data = _read_json(EVENT_BUS_SEEN_FILE, {})
        if not isinstance(data, dict):
            data = {}
        if uid in data:
            return True
        data[uid] = time.time()
        if len(data) > EVENT_BUS_SEEN_MAX:
            items = sorted(data.items(), key=lambda x: x[1])[-EVENT_BUS_SEEN_MAX:]
            data = dict(items)
        _write_json(EVENT_BUS_SEEN_FILE, data)
        return False
    except Exception:
        return False


def emit_from_http(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload precisa ser JSON object"}

    uid = _uid(payload)
    if _seen(uid):
        return {"ok": True, "dedup": True, "uid": uid}

    item = dict(payload)
    item.setdefault("received_at", data_hora_sp_str())
    item.setdefault("epoch", time.time())
    item["uid"] = uid
    _append_jsonl(EVENT_BUS_LOG_FILE, item)

    if history_manager is None:
        return {"ok": False, "uid": uid, "error": HISTORY_MANAGER_ERROR or "history_manager indisponível"}

    event_type = item.get("event") or item.get("event_type") or item.get("type") or "EVENT"
    source = item.get("source") or item.get("bot") or "event_bus"
    trade_id = item.get("trade_id") or item.get("position_id")
    result = history_manager.log_event(event_type, item, source=source, trade_id=trade_id)
    return {"ok": bool(result.get("ok", True)), "uid": uid, "history": result}
