# trade_registry.py
# CENTRAL QUANT — Trade Registry
# Versão: 2026-07-11-TRADE-REGISTRY-V1.1-PERSISTENT-METADATA

import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path


def _resolve_data_dir():
    configured = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return Path(configured)
    try:
        if os.path.isdir("/data"):
            return Path("/data")
    except Exception:
        pass
    return Path(__file__).resolve().parent / "data"

DATA_DIR = str(_resolve_data_dir())
TRADE_REGISTRY_FILE = os.environ.get("TRADE_REGISTRY_FILE", str(Path(DATA_DIR) / "trade_registry.json"))
TRADE_REGISTRY_LEGACY_FILE = str(Path(__file__).resolve().parent / "data" / "trade_registry.json")
VERSION = "2026-07-11-TRADE-REGISTRY-V1.1-PERSISTENT-METADATA"
_lock = threading.Lock()

__all__ = [
    "DATA_DIR", "TRADE_REGISTRY_FILE", "TRADE_REGISTRY_LEGACY_FILE",
    "load_registry", "save_registry", "make_trade_id", "register_open_trade",
    "update_trade", "close_trade", "get_open_trades", "get_trade_registry_snapshot",
    "reset_trade_registry",
]



def _now():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir():
    Path(TRADE_REGISTRY_FILE).parent.mkdir(parents=True, exist_ok=True)


def _empty_registry():
    return {"ok": True, "version": VERSION, "updated_at": _now(), "open_trades": {}, "closed_trades": []}


def _normalize_registry(data):
    if not isinstance(data, dict):
        data = _empty_registry()
    data.setdefault("ok", True)
    data.setdefault("version", VERSION)
    data.setdefault("updated_at", _now())
    data.setdefault("open_trades", {})
    data.setdefault("closed_trades", [])
    if not isinstance(data.get("open_trades"), dict):
        data["open_trades"] = {}
    if not isinstance(data.get("closed_trades"), list):
        data["closed_trades"] = []
    data["version"] = VERSION
    data["registry_file_active"] = TRADE_REGISTRY_FILE
    data["persistent_storage_enabled"] = str(Path(TRADE_REGISTRY_FILE)).startswith("/data") or bool(os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR"))
    return data


def load_registry():
    _ensure_data_dir()
    path = Path(TRADE_REGISTRY_FILE)
    if not path.exists() and TRADE_REGISTRY_LEGACY_FILE != TRADE_REGISTRY_FILE and Path(TRADE_REGISTRY_LEGACY_FILE).exists():
        try:
            legacy = json.loads(Path(TRADE_REGISTRY_LEGACY_FILE).read_text(encoding="utf-8"))
            reg = _normalize_registry(legacy)
            save_registry(reg)
            return reg
        except Exception:
            pass
    if not path.exists():
        reg = _empty_registry()
        save_registry(reg)
        return reg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _normalize_registry(data)
    except Exception:
        return _empty_registry()


def save_registry(registry):
    _ensure_data_dir()
    registry = _normalize_registry(registry)
    registry["updated_at"] = _now()
    tmp = str(TRADE_REGISTRY_FILE) + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, TRADE_REGISTRY_FILE)


def make_trade_id(bot, symbol, side, setup=None):
    bot = str(bot or "UNKNOWN").upper()
    symbol = str(symbol or "UNKNOWN").upper().replace("/", "").replace(":USDT", "").replace("-", "")
    side = str(side or "UNKNOWN").upper()
    setup = str(setup or "DEFAULT").upper()
    return f"{bot}:{setup}:{symbol}:{side}"


def register_open_trade(bot, symbol, side, entry, sl=None, tp50=None, setup=None, qty=None, source="central", metadata=None):
    registry = load_registry()
    trade_id = make_trade_id(bot, symbol, side, setup)
    meta = dict(metadata or {})
    trade = {
        "trade_id": trade_id,
        "status": "OPEN",
        "bot": bot,
        "setup": setup or "DEFAULT",
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "qty": qty,
        "source": source,
        "opened_at": _now(),
        "opened_epoch": time.time(),
        "last_update": _now(),
        "metadata": meta,
    }
    registry["open_trades"][trade_id] = trade
    save_registry(registry)
    return {"ok": True, "action": "OPEN_REGISTERED", "trade_id": trade_id, "trade": trade}


def update_trade(trade_id, **updates):
    registry = load_registry()
    trade = registry["open_trades"].get(trade_id)
    if not trade:
        return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}
    for key, value in updates.items():
        if value is not None:
            if key == "metadata" and isinstance(value, dict):
                trade.setdefault("metadata", {}).update(value)
            else:
                trade[key] = value
    trade["last_update"] = _now()
    registry["open_trades"][trade_id] = trade
    save_registry(registry)
    return {"ok": True, "action": "TRADE_UPDATED", "trade_id": trade_id, "trade": trade}


def close_trade(trade_id, exit_price=None, pnl_pct=None, pnl_r=None, reason=None, metadata=None):
    registry = load_registry()
    trade = registry["open_trades"].pop(trade_id, None)
    if not trade:
        return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}
    trade["status"] = "CLOSED"
    trade["exit_price"] = exit_price
    trade["pnl_pct"] = pnl_pct
    trade["pnl_r"] = pnl_r
    # Compatibilidade com robôs que usam result_pct/result_r.
    trade["result_pct"] = pnl_pct if pnl_pct is not None else trade.get("result_pct")
    trade["result_r"] = pnl_r if pnl_r is not None else trade.get("result_r")
    trade["close_reason"] = reason
    trade["closed_at"] = _now()
    trade["closed_epoch"] = time.time()
    trade["last_update"] = _now()
    if metadata:
        trade.setdefault("metadata", {}).update(metadata)
    registry["closed_trades"].append(trade)
    save_registry(registry)
    return {"ok": True, "action": "TRADE_CLOSED", "trade_id": trade_id, "trade": trade}


def get_open_trades(bot=None, symbol=None, side=None):
    registry = load_registry()
    trades = list(registry.get("open_trades", {}).values())
    if bot:
        trades = [t for t in trades if str(t.get("bot")).upper() == str(bot).upper()]
    if symbol:
        norm = str(symbol).upper().replace("/", "").replace(":USDT", "").replace("-", "")
        trades = [t for t in trades if str(t.get("symbol")).upper().replace("/", "").replace(":USDT", "").replace("-", "") == norm]
    if side:
        trades = [t for t in trades if str(t.get("side")).upper() == str(side).upper()]
    return {"ok": True, "count": len(trades), "trades": trades}


def get_trade_registry_snapshot():
    registry = load_registry()
    open_trades = list(registry.get("open_trades", {}).values())
    closed_trades = registry.get("closed_trades", [])
    by_bot, by_symbol, by_side = {}, {}, {}
    for trade in open_trades:
        bot = trade.get("bot", "UNKNOWN")
        symbol = trade.get("symbol", "UNKNOWN")
        side = trade.get("side", "UNKNOWN")
        by_bot[bot] = by_bot.get(bot, 0) + 1
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        by_side[side] = by_side.get(side, 0) + 1
    return {
        "ok": True,
        "version": registry.get("version"),
        "updated_at": registry.get("updated_at"),
        "registry_file_active": TRADE_REGISTRY_FILE,
        "persistent_storage_enabled": registry.get("persistent_storage_enabled"),
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "by_bot": by_bot,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "open_trades": open_trades,
    }


def reset_trade_registry(confirm=False):
    if not confirm:
        return {"ok": False, "error": "CONFIRM_REQUIRED"}
    registry = _empty_registry()
    save_registry(registry)
    return {"ok": True, "action": "TRADE_REGISTRY_RESET"}
