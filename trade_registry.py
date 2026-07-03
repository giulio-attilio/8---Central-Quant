# trade_registry.py
# CENTRAL QUANT — Trade Registry
# Versão: 2026-07-03-TRADE-REGISTRY-V1

import os
import json
import time
import threading
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
TRADE_REGISTRY_FILE = os.path.join(DATA_DIR, "trade_registry.json")

_lock = threading.Lock()


def _now():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _empty_registry():
    return {
        "ok": True,
        "version": "2026-07-03-TRADE-REGISTRY-V1",
        "updated_at": _now(),
        "open_trades": {},
        "closed_trades": []
    }


def load_registry():
    _ensure_data_dir()

    if not os.path.exists(TRADE_REGISTRY_FILE):
        reg = _empty_registry()
        save_registry(reg)
        return reg

    try:
        with open(TRADE_REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return _empty_registry()

        data.setdefault("ok", True)
        data.setdefault("version", "2026-07-03-TRADE-REGISTRY-V1")
        data.setdefault("updated_at", _now())
        data.setdefault("open_trades", {})
        data.setdefault("closed_trades", [])

        return data

    except Exception:
        return _empty_registry()


def save_registry(registry):
    _ensure_data_dir()
    registry["updated_at"] = _now()

    tmp = TRADE_REGISTRY_FILE + ".tmp"

    with _lock:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)

        os.replace(tmp, TRADE_REGISTRY_FILE)


def make_trade_id(bot, symbol, side, setup=None):
    bot = str(bot or "UNKNOWN").upper()
    symbol = str(symbol or "UNKNOWN").upper()
    side = str(side or "UNKNOWN").upper()
    setup = str(setup or "DEFAULT").upper()
    return f"{bot}:{setup}:{symbol}:{side}"


def register_open_trade(
    bot,
    symbol,
    side,
    entry,
    sl=None,
    tp50=None,
    setup=None,
    qty=None,
    source="central",
    metadata=None
):
    registry = load_registry()

    trade_id = make_trade_id(bot, symbol, side, setup)

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
        "metadata": metadata or {}
    }

    registry["open_trades"][trade_id] = trade
    save_registry(registry)

    return {
        "ok": True,
        "action": "OPEN_REGISTERED",
        "trade_id": trade_id,
        "trade": trade
    }


def update_trade(trade_id, **updates):
    registry = load_registry()

    trade = registry["open_trades"].get(trade_id)

    if not trade:
        return {
            "ok": False,
            "error": "TRADE_NOT_FOUND",
            "trade_id": trade_id
        }

    for key, value in updates.items():
        if value is not None:
            trade[key] = value

    trade["last_update"] = _now()
    registry["open_trades"][trade_id] = trade
    save_registry(registry)

    return {
        "ok": True,
        "action": "TRADE_UPDATED",
        "trade_id": trade_id,
        "trade": trade
    }


def close_trade(
    trade_id,
    exit_price=None,
    pnl_pct=None,
    pnl_r=None,
    reason=None,
    metadata=None
):
    registry = load_registry()

    trade = registry["open_trades"].pop(trade_id, None)

    if not trade:
        return {
            "ok": False,
            "error": "TRADE_NOT_FOUND",
            "trade_id": trade_id
        }

    trade["status"] = "CLOSED"
    trade["exit_price"] = exit_price
    trade["pnl_pct"] = pnl_pct
    trade["pnl_r"] = pnl_r
    trade["close_reason"] = reason
    trade["closed_at"] = _now()
    trade["closed_epoch"] = time.time()
    trade["last_update"] = _now()

    if metadata:
        trade.setdefault("metadata", {}).update(metadata)

    registry["closed_trades"].append(trade)
    save_registry(registry)

    return {
        "ok": True,
        "action": "TRADE_CLOSED",
        "trade_id": trade_id,
        "trade": trade
    }


def get_open_trades(bot=None, symbol=None, side=None):
    registry = load_registry()
    trades = list(registry.get("open_trades", {}).values())

    if bot:
        trades = [t for t in trades if str(t.get("bot")).upper() == str(bot).upper()]

    if symbol:
        trades = [t for t in trades if str(t.get("symbol")).upper() == str(symbol).upper()]

    if side:
        trades = [t for t in trades if str(t.get("side")).upper() == str(side).upper()]

    return {
        "ok": True,
        "count": len(trades),
        "trades": trades
    }


def get_trade_registry_snapshot():
    registry = load_registry()
    open_trades = list(registry.get("open_trades", {}).values())
    closed_trades = registry.get("closed_trades", [])

    by_bot = {}
    by_symbol = {}
    by_side = {}

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
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "by_bot": by_bot,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "open_trades": open_trades
    }


def reset_trade_registry(confirm=False):
    if not confirm:
        return {
            "ok": False,
            "error": "CONFIRM_REQUIRED"
        }

    registry = _empty_registry()
    save_registry(registry)

    return {
        "ok": True,
        "action": "TRADE_REGISTRY_RESET"
    }