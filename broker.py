# ==============================================================================
# CENTRAL QUANT - BROKER BINGX SAFE MODE
# Versão: 2026-06-26-BROKER-BINGX-SAFE-V1-VERIFY-PAYLOAD
#
# Objetivo:
# - Isolar toda comunicação real com a BingX em um único arquivo.
# - Suportar modos PAPER / READY / VERIFY / LIVE.
# - Nunca enviar ordem real se ENABLE_REAL_TRADING=false.
# - Em VERIFY, montar uma prévia completa da ordem: preço, quantidade,
#   precisão, margin mode, leverage, reduceOnly, clientOrderId, payload e
#   assinatura HMAC, sem enviar a ordem.
# - Em LIVE, enviar automaticamente apenas se EXECUTION_MODE=LIVE,
#   ENABLE_REAL_TRADING=true e BROKER_DRY_RUN=false.
#
# Variáveis principais no Render:
# - BINGX_API_KEY
# - BINGX_API_SECRET
# - ENABLE_REAL_TRADING=false
# - EXECUTION_MODE=PAPER ou READY ou VERIFY ou LIVE
# - BINGX_DEFAULT_TYPE=swap
# - BINGX_MARGIN_MODE=isolated ou cross
# - BINGX_DEFAULT_LEVERAGE=1
# - BINGX_TIMEOUT_MS=15000
# ============================================================================

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import ccxt

TIMEZONE_BR = timezone(timedelta(hours=-3))


# ==============================================================================
# CONFIG / ENV
# ============================================================================

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

# Endpoint usado apenas para prévia/assinatura no VERIFY.
# O envio real continua usando ccxt.create_order(), pois é mais seguro e padronizado.
BINGX_SWAP_ORDER_ENDPOINT = "/openApi/swap/v2/trade/order"

_exchange = None
_last_ready = None
_last_ready_ts = 0


# ==============================================================================
# UTIL
# ============================================================================

def agora_sp_str():
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M")


def now_ms() -> int:
    return int(time.time() * 1000)


def normalize_symbol(symbol: str) -> str:
    """Formato CCXT, exemplo BTCUSDT -> BTC/USDT:USDT."""
    s = str(symbol or "").upper().strip()
    if not s:
        return s
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT:USDT"
    return s


def bingx_api_symbol(symbol: str) -> str:
    """Formato usado em payload BingX, exemplo BTC/USDT:USDT -> BTC-USDT."""
    s = normalize_symbol(symbol)
    if "/USDT" in s:
        base = s.split("/", 1)[0]
        return f"{base}-USDT"
    return str(symbol or "").upper().replace("USDT", "-USDT")


def normalize_side(side: str) -> str:
    """Lado CCXT."""
    s = str(side or "").upper().strip()
    if s in {"LONG", "BUY"}:
        return "buy"
    if s in {"SHORT", "SELL"}:
        return "sell"
    raise ValueError(f"side inválido: {side}")


def bingx_api_side(side: str) -> str:
    """Lado para payload textual BingX."""
    return "BUY" if normalize_side(side) == "buy" else "SELL"


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    value = str(value)
    if len(value) <= keep * 2:
        return "***"
    return value[:keep] + "***" + value[-keep:]


def sign_query(params: dict) -> tuple[str, str]:
    """
    Assina uma query string com HMAC SHA256.
    Usado no VERIFY para validar que a ordem consegue ser montada/assinada.
    """
    if not BINGX_API_SECRET:
        raise RuntimeError("BINGX_API_SECRET ausente")
    ordered = {k: params[k] for k in sorted(params.keys()) if params[k] is not None}
    query = urlencode(ordered, doseq=False)
    signature = hmac.new(
        BINGX_API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return query, signature


# ==============================================================================
# EXCHANGE / STATUS
# ============================================================================

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
        "api_key_masked": mask_secret(BINGX_API_KEY),
        "default_type": BINGX_DEFAULT_TYPE,
        "margin_mode": BINGX_MARGIN_MODE,
        "default_leverage": BINGX_DEFAULT_LEVERAGE,
        "timeout_ms": BINGX_TIMEOUT_MS,
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


def market_info(symbol):
    ex = exchange()
    sym = normalize_symbol(symbol)
    try:
        ex.load_markets()
    except Exception:
        pass
    market = ex.market(sym)
    precision = market.get("precision") or {}
    limits = market.get("limits") or {}
    return {
        "ok": True,
        "symbol": market.get("symbol", sym),
        "id": market.get("id"),
        "base": market.get("base"),
        "quote": market.get("quote"),
        "settle": market.get("settle"),
        "type": market.get("type"),
        "contract": market.get("contract"),
        "linear": market.get("linear"),
        "precision": precision,
        "limits": limits,
        "amount_precision": precision.get("amount"),
        "price_precision": precision.get("price"),
        "min_amount": (limits.get("amount") or {}).get("min"),
        "min_cost": (limits.get("cost") or {}).get("min"),
    }


def amount_from_notional(symbol, notional_usdt):
    """
    Calcula quantidade a partir do notional e retorna detalhes de arredondamento.
    Mantém compatibilidade: pode ser usado como amount, price = amount_from_notional(...)
    porque retorna um dict apenas por função nova amount_details(); esta aqui segue tupla.
    """
    details = amount_details(symbol, notional_usdt)
    return details["amount"], details["price_ref"]


def amount_details(symbol, notional_usdt):
    sym = normalize_symbol(symbol)
    price = fetch_last_price(sym)
    if price <= 0:
        raise RuntimeError(f"preço inválido para {symbol}: {price}")
    notional = float(notional_usdt)
    raw_amount = notional / price
    ex = exchange()
    market = None
    amount = raw_amount
    precision_error = None
    try:
        market = ex.market(sym)
        amount = float(ex.amount_to_precision(market["symbol"], raw_amount))
    except Exception as exc:
        precision_error = str(exc)
        amount = round(raw_amount, 6)

    effective_notional = amount * price if amount is not None and price is not None else None
    info = market_info(sym) if market else {"symbol": sym}

    return {
        "ok": True,
        "symbol": sym,
        "bingx_symbol": bingx_api_symbol(sym),
        "notional_usdt": notional,
        "price_ref": price,
        "amount_raw": raw_amount,
        "amount": amount,
        "effective_notional_usdt": effective_notional,
        "precision_error": precision_error,
        "market": info,
    }


def ready_check(cache_seconds: int = 30):
    global _last_ready, _last_ready_ts
    now = time.time()
    if _last_ready is not None and now - _last_ready_ts <= cache_seconds:
        return dict(_last_ready)
    started = time.perf_counter()
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
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "balance": balance,
            "api_key_configured": bool(BINGX_API_KEY),
            "api_secret_configured": bool(BINGX_API_SECRET),
            "api_key_masked": mask_secret(BINGX_API_KEY),
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "status": "NOT_READY",
            "ts": agora_sp_str(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
            "api_key_configured": bool(BINGX_API_KEY),
            "api_secret_configured": bool(BINGX_API_SECRET),
            "api_key_masked": mask_secret(BINGX_API_KEY),
        }
    _last_ready = dict(payload)
    _last_ready_ts = now
    return payload


# ==============================================================================
# ORDER PREVIEW / VERIFY
# ============================================================================

def build_order_preview(symbol, side, notional_usdt, reduce_only=False, client_tag=None):
    """
    Monta a prévia completa de uma ordem market.
    Não envia nada. Usada em READY/VERIFY e para debug antes do LIVE.
    """
    started = time.perf_counter()
    sym = normalize_symbol(symbol)
    order_side = normalize_side(side)
    api_side = bingx_api_side(side)
    notional = float(notional_usdt)

    details = amount_details(sym, notional)
    amount = details["amount"]
    price = details["price_ref"]
    market = details.get("market") or {}
    client_order_id = str(client_tag or f"CQ-{int(time.time())}")[:32]

    # Payload informativo baseado no endpoint REST da BingX.
    # O envio real usa ccxt, mas esta estrutura valida a assinatura e a ordem que seria enviada.
    timestamp = now_ms()
    api_payload = {
        "symbol": bingx_api_symbol(sym),
        "side": api_side,
        "type": "MARKET",
        "quantity": amount,
        "timestamp": timestamp,
    }
    if reduce_only:
        api_payload["reduceOnly"] = "true"
    if client_order_id:
        api_payload["clientOrderID"] = client_order_id

    signature_ok = False
    query_string = None
    signature = None
    signature_error = None
    try:
        query_string, signature = sign_query(api_payload)
        signature_ok = True
    except Exception as exc:
        signature_error = str(exc)

    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    return {
        "ok": True,
        "status": "PREVIEW",
        "sent": False,
        "ts": agora_sp_str(),
        "latency_ms": latency_ms,
        "exchange": "bingx",
        "endpoint": BINGX_SWAP_ORDER_ENDPOINT,
        "method": "POST",
        "execution_mode": EXECUTION_MODE,
        "enable_real_trading": ENABLE_REAL_TRADING,
        "broker_dry_run": BROKER_DRY_RUN,
        "symbol": sym,
        "bingx_symbol": bingx_api_symbol(sym),
        "market_id": market.get("id"),
        "market_symbol": market.get("symbol", sym),
        "side": order_side,
        "api_side": api_side,
        "order_type": "market",
        "reduce_only": bool(reduce_only),
        "client_tag": client_tag,
        "client_order_id": client_order_id,
        "notional_usdt": notional,
        "price_ref": price,
        "amount_raw": details.get("amount_raw"),
        "amount": amount,
        "effective_notional_usdt": details.get("effective_notional_usdt"),
        "margin_mode": BINGX_MARGIN_MODE,
        "leverage": BINGX_DEFAULT_LEVERAGE,
        "precision": market.get("precision"),
        "limits": market.get("limits"),
        "amount_precision": market.get("amount_precision"),
        "price_precision": market.get("price_precision"),
        "min_amount": market.get("min_amount"),
        "min_cost": market.get("min_cost"),
        "payload": api_payload,
        "query_string": query_string,
        "signature_ok": signature_ok,
        "signature": signature,
        "signature_masked": mask_secret(signature, keep=6),
        "signature_error": signature_error,
        "headers_preview": {
            "X-BX-APIKEY": mask_secret(BINGX_API_KEY),
        },
    }


def format_order_preview_text(preview: dict, title: str = "🧪 VERIFY BINGX") -> str:
    """Texto curto para Telegram/log, caso a Central/Falcon queira exibir a prévia."""
    if not isinstance(preview, dict):
        return f"{title}\nPrévia indisponível."
    if not preview.get("ok"):
        return f"{title}\n❌ {preview.get('status')}\nErro: {preview.get('error')}"

    return (
        f"{title}\n\n"
        f"Status: {preview.get('status')} | Enviada: {preview.get('sent')}\n"
        f"Modo: {preview.get('execution_mode')} | Real trading: {preview.get('enable_real_trading')}\n"
        f"Exchange: {preview.get('exchange')} | Endpoint: {preview.get('method')} {preview.get('endpoint')}\n\n"
        f"Símbolo: {preview.get('symbol')} | BingX: {preview.get('bingx_symbol')}\n"
        f"Side: {preview.get('api_side')} | Type: MARKET | ReduceOnly: {preview.get('reduce_only')}\n"
        f"Margin: {preview.get('margin_mode')} | Leverage: {preview.get('leverage')}x\n\n"
        f"Preço ref.: {preview.get('price_ref')}\n"
        f"Notional: {preview.get('notional_usdt')} USDT\n"
        f"Quantidade raw: {preview.get('amount_raw')}\n"
        f"Quantidade enviada: {preview.get('amount')}\n"
        f"Notional efetivo: {preview.get('effective_notional_usdt')} USDT\n\n"
        f"Market ID: {preview.get('market_id')}\n"
        f"Amount precision: {preview.get('amount_precision')} | Price precision: {preview.get('price_precision')}\n"
        f"Min amount: {preview.get('min_amount')} | Min cost: {preview.get('min_cost')}\n\n"
        f"ClientOrderId: {preview.get('client_order_id')}\n"
        f"Payload: ✅ OK\n"
        f"Signature: {'✅ OK' if preview.get('signature_ok') else '❌ ERRO'}\n"
        f"Tempo: {preview.get('latency_ms')} ms\n\n"
        f"Resultado: 🚫 ORDEM NÃO ENVIADA ({preview.get('execution_mode')})"
    )


# ==============================================================================
# ORDER EXECUTION
# ============================================================================

def place_market_order(symbol, side, notional_usdt, reduce_only=False, client_tag=None):
    """
    Envia ordem market apenas se LIVE + ENABLE_REAL_TRADING=true + BROKER_DRY_RUN=false.
    Caso contrário, retorna DRY_RUN/PREVIEW sem enviar nada.
    """
    started = time.perf_counter()
    sym = normalize_symbol(symbol)
    order_side = normalize_side(side)
    notional = float(notional_usdt)
    if notional <= 0:
        return {"ok": False, "status": "REJECTED", "sent": False, "error": "notional_usdt inválido", "symbol": sym}

    # PAPER/READY/VERIFY nunca enviam ordem real.
    if EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING or BROKER_DRY_RUN:
        try:
            preview = build_order_preview(sym, side, notional, reduce_only=reduce_only, client_tag=client_tag)
            preview.update({
                "status": "DRY_RUN" if EXECUTION_MODE != "VERIFY" else "VERIFY",
                "sent": False,
                "reason": "EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
            })
            return preview
        except Exception as exc:
            return {
                "ok": False,
                "status": "DRY_RUN_ERROR",
                "sent": False,
                "symbol": sym,
                "side": order_side,
                "notional_usdt": notional,
                "error": str(exc),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "reason": "falha ao montar prévia dry-run",
            }

    ready = ready_check(cache_seconds=0)
    if not ready.get("ok"):
        return {"ok": False, "status": "NOT_READY", "sent": False, "symbol": sym, "error": ready.get("error"), "ready": ready}

    try:
        preview = build_order_preview(sym, side, notional, reduce_only=reduce_only, client_tag=client_tag)
        amount = preview["amount"]
        price = preview["price_ref"]
    except Exception as exc:
        return {
            "ok": False,
            "status": "PREVIEW_ERROR",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "notional_usdt": notional,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    params = {}
    if reduce_only:
        params["reduceOnly"] = True
    if client_tag:
        # Algumas corretoras ignoram; mantemos como metadado se aceito.
        params["clientOrderId"] = str(client_tag)[:32]

    ex = exchange()
    try:
        # Tentativa conservadora de leverage/margin. Se falhar, não bloqueia ordem.
        margin_set = None
        leverage_set = None
        try:
            margin_set = ex.set_margin_mode(BINGX_MARGIN_MODE, sym)
        except Exception as exc:
            margin_set = {"ok": False, "error": str(exc)}
        try:
            leverage_set = ex.set_leverage(BINGX_DEFAULT_LEVERAGE, sym)
        except Exception as exc:
            leverage_set = {"ok": False, "error": str(exc)}

        order = ex.create_order(sym, "market", order_side, amount, None, params)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        return {
            "ok": True,
            "status": "SENT",
            "sent": True,
            "ts": agora_sp_str(),
            "latency_ms": latency_ms,
            "id": order.get("id"),
            "order_id": order.get("id"),
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": order_side,
            "api_side": bingx_api_side(side),
            "notional_usdt": notional,
            "amount": amount,
            "price_ref": price,
            "margin_mode": BINGX_MARGIN_MODE,
            "leverage": BINGX_DEFAULT_LEVERAGE,
            "reduce_only": bool(reduce_only),
            "client_tag": client_tag,
            "client_order_id": preview.get("client_order_id"),
            "preview": preview,
            "margin_set": margin_set,
            "leverage_set": leverage_set,
            "raw": order,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "sent": False,
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": order_side,
            "notional_usdt": notional,
            "amount": preview.get("amount") if isinstance(preview, dict) else None,
            "price_ref": preview.get("price_ref") if isinstance(preview, dict) else None,
            "preview": preview if isinstance(preview, dict) else None,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def close_position_market(symbol, side, amount=None, notional_usdt=None):
    """Fechamento simples. side deve ser lado da posição: LONG fecha vendendo; SHORT fecha comprando."""
    close_side = "sell" if str(side).upper() in {"LONG", "BUY"} else "buy"
    sym = normalize_symbol(symbol)
    if amount is None:
        if notional_usdt is None:
            return {"ok": False, "status": "REJECTED", "sent": False, "error": "amount ou notional_usdt obrigatório"}
        amount, _price = amount_from_notional(sym, float(notional_usdt))

    if EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING or BROKER_DRY_RUN:
        return {
            "ok": True,
            "status": "DRY_RUN",
            "sent": False,
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": close_side,
            "amount": amount,
            "reduce_only": True,
            "reason": "EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
        }

    ex = exchange()
    started = time.perf_counter()
    try:
        order = ex.create_order(sym, "market", close_side, float(amount), None, {"reduceOnly": True})
        return {
            "ok": True,
            "status": "SENT",
            "sent": True,
            "id": order.get("id"),
            "order_id": order.get("id"),
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": close_side,
            "amount": amount,
            "reduce_only": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "raw": order,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "ERROR",
            "sent": False,
            "symbol": sym,
            "side": close_side,
            "amount": amount,
            "reduce_only": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
        }
