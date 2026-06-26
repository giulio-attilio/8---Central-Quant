# ==============================================================================
# CENTRAL QUANT - BROKER BINGX SAFE MODE
# Versão: 2026-06-26-BROKER-BINGX-SAFE
#
# Objetivo:
# - Isolar toda comunicação real com a BingX em um único arquivo.
# - Suportar modos PAPER / READY / VERIFY / LIVE.
# - Nunca enviar ordem real se ENABLE_REAL_TRADING=false.
# - Fornecer ready_check(), status_payload(), get_balance(), get_positions(),
#   place_market_order() para a Central e para o Falcon.
#
# Variáveis principais no Render:
# - BINGX_API_KEY
# - BINGX_API_SECRET
# - ENABLE_REAL_TRADING=false
# - EXECUTION_MODE=PAPER ou READY ou VERIFY ou LIVE
# - BINGX_DEFAULT_TYPE=swap
# - BINGX_MARGIN_MODE=isolated ou cross
# - BINGX_DEFAULT_LEVERAGE=1
# ============================================================================

import os
import time
from datetime import datetime, timezone, timedelta

import ccxt

TIMEZONE_BR = timezone(timedelta(hours=-3))


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


BINGX_API_KEY = os.environ.get("BINGX_API_KEY") or os.environ.get("BINGX_KEY")
BINGX_API_SECRET = os.environ.get("BINGX_API_SECRET") or os.environ.get("BINGX_SECRET")
BINGX_DEFAULT_TYPE = os.environ.get("BINGX_DEFAULT_TYPE", "swap")
BINGX_MARGIN_MODE = os.environ.get("BINGX_MARGIN_MODE", "isolated")
BINGX_DEFAULT_LEVERAGE = int(os.environ.get("BINGX_DEFAULT_LEVERAGE", "1"))
BINGX_TIMEOUT_MS = int(os.environ.get("BINGX_TIMEOUT_MS", "15000"))
ENABLE_REAL_TRADING = env_bool("ENABLE_REAL_TRADING", False)
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "PAPER").strip().upper()
BROKER_DRY_RUN = env_bool("BROKER_DRY_RUN", EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING)

_exchange = None
_last_ready = None
_last_ready_ts = 0


def agora_sp_str():
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M")


def normalize_symbol(symbol: str) -> str:
    s = str(symbol or "").upper().strip()
    if not s:
        return s
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT:USDT"
    return s


def normalize_side(side: str) -> str:
    s = str(side or "").upper().strip()
    if s in {"LONG", "BUY"}:
        return "buy"
    if s in {"SHORT", "SELL"}:
        return "sell"
    raise ValueError(f"side inválido: {side}")


def exchange():
    global _exchange
    if _exchange is not None:
        return _exchange
    if not BINGX_API_KEY or not BINGX_API_SECRET:
        raise RuntimeError("BINGX_API_KEY/BINGX_API_SECRET ausentes")
    ex = ccxt.bingx({
        "apiKey": BINGX_API_KEY,
        "secret": BINGX_API_SECRET,
        "enableRateLimit": True,
        "timeout": BINGX_TIMEOUT_MS,
        "options": {"defaultType": BINGX_DEFAULT_TYPE},
    })
    ex.options["defaultType"] = BINGX_DEFAULT_TYPE
    _exchange = ex
    return _exchange


def status_payload(check_ready: bool = False):
    payload = {
        "ok": True,
        "ts": agora_sp_str(),
        "exchange": "bingx",
        "execution_mode": EXECUTION_MODE,
        "enable_real_trading": ENABLE_REAL_TRADING,
        "broker_dry_run": BROKER_DRY_RUN,
        "api_key_configured": bool(BINGX_API_KEY),
        "api_secret_configured": bool(BINGX_API_SECRET),
        "default_type": BINGX_DEFAULT_TYPE,
        "margin_mode": BINGX_MARGIN_MODE,
        "default_leverage": BINGX_DEFAULT_LEVERAGE,
    }
    if check_ready:
        payload["ready"] = ready_check()
    return payload


def get_balance():
    ex = exchange()
    bal = ex.fetch_balance({"type": BINGX_DEFAULT_TYPE})
    usdt = (bal.get("USDT") or {}) if isinstance(bal, dict) else {}
    return {
        "ok": True,
        "total_usdt": usdt.get("total"),
        "free_usdt": usdt.get("free"),
        "used_usdt": usdt.get("used"),
        "raw_keys": list(bal.keys())[:20] if isinstance(bal, dict) else [],
    }


def get_positions(symbols=None):
    ex = exchange()
    markets = None
    if symbols:
        markets = [normalize_symbol(s) for s in symbols]
    try:
        positions = ex.fetch_positions(markets)
    except TypeError:
        positions = ex.fetch_positions()
    return positions or []


def fetch_last_price(symbol):
    ex = exchange()
    ticker = ex.fetch_ticker(normalize_symbol(symbol))
    price = ticker.get("last") or ticker.get("close") or ticker.get("bid") or ticker.get("ask")
    if not price:
        raise RuntimeError(f"não foi possível obter preço de {symbol}")
    return float(price)


def amount_from_notional(symbol, notional_usdt):
    price = fetch_last_price(symbol)
    if price <= 0:
        raise RuntimeError(f"preço inválido para {symbol}: {price}")
    amount = float(notional_usdt) / price
    ex = exchange()
    try:
        market = ex.market(normalize_symbol(symbol))
        amount = float(ex.amount_to_precision(market["symbol"], amount))
    except Exception:
        amount = round(amount, 6)
    return amount, price


def ready_check(cache_seconds: int = 30):
    global _last_ready, _last_ready_ts
    now = time.time()
    if _last_ready is not None and now - _last_ready_ts <= cache_seconds:
        return dict(_last_ready)
    try:
        ex = exchange()
        server_time = None
        try:
            server_time = ex.fetch_time()
        except Exception:
            server_time = None
        balance = get_balance()
        payload = {
            "ok": True,
            "status": "READY",
            "ts": agora_sp_str(),
            "server_time": server_time,
            "balance": balance,
            "api_key_configured": bool(BINGX_API_KEY),
            "api_secret_configured": bool(BINGX_API_SECRET),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "NOT_READY",
            "ts": agora_sp_str(),
            "error": str(exc),
            "api_key_configured": bool(BINGX_API_KEY),
            "api_secret_configured": bool(BINGX_API_SECRET),
        }
    _last_ready = dict(payload)
    _last_ready_ts = now
    return payload


def place_market_order(symbol, side, notional_usdt, reduce_only=False, client_tag=None):
    """
    Envia ordem market apenas se LIVE + ENABLE_REAL_TRADING=true + BROKER_DRY_RUN=false.
    Caso contrário, retorna DRY_RUN sem enviar nada.
    """
    sym = normalize_symbol(symbol)
    order_side = normalize_side(side)
    notional = float(notional_usdt)
    if notional <= 0:
        return {"ok": False, "status": "REJECTED", "error": "notional_usdt inválido", "symbol": sym}

    if EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING or BROKER_DRY_RUN:
        try:
            amount, price = amount_from_notional(sym, notional)
        except Exception:
            amount, price = None, None
        return {
            "ok": True,
            "status": "DRY_RUN",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "notional_usdt": notional,
            "amount": amount,
            "price_ref": price,
            "reason": "EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
            "client_tag": client_tag,
        }

    ready = ready_check(cache_seconds=0)
    if not ready.get("ok"):
        return {"ok": False, "status": "NOT_READY", "sent": False, "symbol": sym, "error": ready.get("error"), "ready": ready}

    amount, price = amount_from_notional(sym, notional)
    params = {}
    if reduce_only:
        params["reduceOnly"] = True
    if client_tag:
        # Algumas corretoras ignoram; mantemos como metadado se aceito.
        params["clientOrderId"] = str(client_tag)[:32]

    ex = exchange()
    try:
        # Tentativa conservadora de leverage/margin. Se falhar, não bloqueia ordem.
        try:
            ex.set_margin_mode(BINGX_MARGIN_MODE, sym)
        except Exception:
            pass
        try:
            ex.set_leverage(BINGX_DEFAULT_LEVERAGE, sym)
        except Exception:
            pass

        order = ex.create_order(sym, "market", order_side, amount, None, params)
        return {
            "ok": True,
            "status": "SENT",
            "sent": True,
            "id": order.get("id"),
            "order_id": order.get("id"),
            "symbol": sym,
            "side": order_side,
            "notional_usdt": notional,
            "amount": amount,
            "price_ref": price,
            "raw": order,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "notional_usdt": notional,
            "amount": amount,
            "price_ref": price,
            "error": str(exc),
        }


def close_position_market(symbol, side, amount=None, notional_usdt=None):
    """Fechamento simples. side deve ser lado da posição: LONG fecha vendendo; SHORT fecha comprando."""
    close_side = "sell" if str(side).upper() in {"LONG", "BUY"} else "buy"
    sym = normalize_symbol(symbol)
    if amount is None:
        if notional_usdt is None:
            return {"ok": False, "status": "REJECTED", "error": "amount ou notional_usdt obrigatório"}
        amount, _price = amount_from_notional(sym, float(notional_usdt))
    if EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING or BROKER_DRY_RUN:
        return {"ok": True, "status": "DRY_RUN", "sent": False, "symbol": sym, "side": close_side, "amount": amount, "reduce_only": True}
    ex = exchange()
    try:
        order = ex.create_order(sym, "market", close_side, float(amount), None, {"reduceOnly": True})
        return {"ok": True, "status": "SENT", "sent": True, "id": order.get("id"), "raw": order}
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "sent": False, "error": str(exc)}
