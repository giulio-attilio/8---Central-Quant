# ==============================================================================
# CENTRAL QUANT - BROKER BINGX SAFE MODE
# Versão: 2026-07-06-BROKER-BINGX-SAFE-V2.6.2-EXECUTION-AUTH-TOKEN
#
# Objetivo:
# - Isolar toda comunicação real com a BingX em um único arquivo.
# - Suportar modos PAPER / READY / VERIFY / LIVE.
# - Nunca enviar ordem real se ENABLE_REAL_TRADING=false.
# - Em VERIFY, montar uma prévia completa da ordem: preço, quantidade,
#   precisão detalhada, margin mode, leverage, reduceOnly, clientOrderId, payload e
#   assinatura HMAC, sem enviar a ordem.
# - Em LIVE, enviar automaticamente apenas se EXECUTION_MODE=LIVE,
#   ENABLE_REAL_TRADING=true e BROKER_DRY_RUN=false.
#
# Correções desta versão:
# - Corrige bug "name 'margin' is not defined" em amount_details().
# - Mantém margem/alavancagem por robô via Render.
# - Calcula quantidade pela exposição efetiva = margem * alavancagem.
# - Arredonda campos exibidos para evitar floats como 59.138999999999996.
# - Adiciona Execution Audit Log V1 para registrar previews, bloqueios, erros e ordens reais.
# - Adiciona Hedge Mode Support V2.6: envia positionSide=LONG/SHORT quando habilitado.
# - V2.6.1 Preview Isolation: qualquer VERIFY/DRY_RUN retorna antes de create_order().
# - V2.6.2 Execution Authorization Token: envio real exige token curto gerado pelo Execution Engine.
# - Adiciona campos de apresentação para VERIFY:
#   margin_usdt_display, leverage_display, planned_exposure_usdt_display,
#   actual_exposure_usdt_display, estimated_margin_after_open_usdt_display,
#   estimated_max_loss_usdt_display.
#
# Variáveis principais no Render:
# - BINGX_API_KEY
# - BINGX_API_SECRET
# - ENABLE_REAL_TRADING=false
# - EXECUTION_MODE=PAPER ou READY ou VERIFY ou LIVE
# - BINGX_DEFAULT_TYPE=swap
# - BINGX_MARGIN_MODE=isolated ou cross
# - DEFAULT_REAL_MARGIN_USDT=20
# - DEFAULT_REAL_LEVERAGE=3
# - <BOT>_REAL_MARGIN_USDT / <BOT>_REAL_LEVERAGE para configuração por robô
# - BINGX_DEFAULT_LEVERAGE=3
# - BINGX_TIMEOUT_MS=15000
# ============================================================================

import hashlib
import secrets
import hmac
import json
import os
import time
from pathlib import Path
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
BINGX_DEFAULT_LEVERAGE = int(os.environ.get("BINGX_DEFAULT_LEVERAGE", os.environ.get("DEFAULT_REAL_LEVERAGE", "3")))
DEFAULT_REAL_MARGIN_USDT = float(
    os.environ.get(
        "DEFAULT_REAL_MARGIN_USDT",
        os.environ.get("REAL_TRADING_MARGIN_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "20")),
    )
)
DEFAULT_REAL_LEVERAGE = int(
    os.environ.get("DEFAULT_REAL_LEVERAGE", os.environ.get("REAL_TRADING_LEVERAGE", str(BINGX_DEFAULT_LEVERAGE)))
)
BINGX_TIMEOUT_MS = int(os.environ.get("BINGX_TIMEOUT_MS", "15000"))
ENABLE_REAL_TRADING = env_bool("ENABLE_REAL_TRADING", False)
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "PAPER").strip().upper()
BROKER_DRY_RUN = env_bool("BROKER_DRY_RUN", EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING)

# Hedge Mode:
# - AUTO/true: envia positionSide=LONG/SHORT nas ordens.
# - false/oneway: não envia positionSide.
# Para sua conta BingX atual, o erro 109400 indicou Hedge Mode ativo.
BINGX_POSITION_MODE = os.environ.get("BINGX_POSITION_MODE", os.environ.get("BINGX_HEDGE_MODE", "HEDGE")).strip().upper()
BINGX_HEDGE_MODE_ENABLED = env_bool("BINGX_HEDGE_MODE_ENABLED", BINGX_POSITION_MODE in {"HEDGE", "HEDGED", "DUAL", "TRUE", "YES", "1", "ON"})

# Execution Authorization Token:
# - Em LIVE real, o broker só chama create_order() se receber um token válido.
# - O token é gerado pelo Execution Engine e expira rapidamente.
# - Preview/VERIFY/DRY_RUN não exige token porque nunca chama create_order().
EXECUTION_AUTH_TOKEN_ENABLED = env_bool("EXECUTION_AUTH_TOKEN_ENABLED", True)
EXECUTION_AUTH_TOKEN_TTL_SECONDS = int(os.environ.get("EXECUTION_AUTH_TOKEN_TTL_SECONDS", "30"))
_EXECUTION_AUTH_TOKENS = {}

# Endpoint usado apenas para prévia/assinatura no VERIFY.
# O envio real continua usando ccxt.create_order(), pois é mais seguro e padronizado.
BINGX_SWAP_ORDER_ENDPOINT = "/openApi/swap/v2/trade/order"

# Log local/ephemeral de execução. A Central lê este arquivo em /live, /sync e /executions.
EXECUTIONS_LOG_FILE = os.environ.get("EXECUTIONS_LOG_FILE", "daily_history/executions_log.jsonl")
EXECUTIONS_LOG_MAX_READ = int(os.environ.get("EXECUTIONS_LOG_MAX_READ", "50"))

# Audit log persistente/estruturado para rastrear toda tentativa de execução.
# Diferente do log operacional, este arquivo é pensado para auditoria posterior.
EXECUTION_AUDIT_LOG_FILE = os.environ.get("EXECUTION_AUDIT_LOG_FILE", str(Path("daily_history") / "execution_audit_log.jsonl"))
EXECUTION_AUDIT_LOG_MAX_READ = int(os.environ.get("EXECUTION_AUDIT_LOG_MAX_READ", "100"))

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


def round_float(value, ndigits=8, default=None):
    try:
        if value is None:
            return default
        return round(float(value), ndigits)
    except Exception:
        return default


def money(value, ndigits=2, default=None):
    return round_float(value, ndigits=ndigits, default=default)


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


def bingx_position_side(side: str):
    """
    PositionSide exigido pela BingX quando a conta está em Hedge Mode.
    LONG -> positionSide LONG
    SHORT -> positionSide SHORT
    Em One-Way Mode, retorna None.
    """
    if not BINGX_HEDGE_MODE_ENABLED:
        return None
    s = str(side or "").upper().strip()
    if s in {"LONG", "BUY"}:
        return "LONG"
    if s in {"SHORT", "SELL"}:
        return "SHORT"
    return None


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
# EXECUTIONS LOG
# ==============================================================================

def _json_default(value):
    try:
        return str(value)
    except Exception:
        return None


def log_execution_event(event: dict):
    """Registra prévias VERIFY/DRY_RUN, ordens LIVE e erros do broker."""
    try:
        payload = dict(event or {})
        payload.setdefault("ts", agora_sp_str())
        payload.setdefault("execution_mode", EXECUTION_MODE)
        payload.setdefault("enable_real_trading", ENABLE_REAL_TRADING)
        path = Path(EXECUTIONS_LOG_FILE)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception:
        return False


def _audit_sanitize(value):
    """Remove ou mascara dados sensíveis antes de persistir auditoria."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lk = str(k).lower()
            if any(token in lk for token in ["secret", "signature", "apikey", "api_key", "x-bx-apikey"]):
                out[k] = mask_secret(str(v)) if v else v
            elif lk in {"raw", "info"}:
                # Evita salvar payloads muito grandes da exchange.
                out[k] = str(v)[:1000]
            else:
                out[k] = _audit_sanitize(v)
        return out
    if isinstance(value, list):
        return [_audit_sanitize(x) for x in value[:20]]
    return value


def log_execution_audit_event(event: dict):
    """
    Execution Audit Log V1.
    Registra eventos relevantes da camada broker sem guardar segredos.
    Eventos típicos:
    - BROKER_PREVIEW
    - BROKER_DRY_RUN
    - BROKER_CONSTRAINTS_BLOCKED
    - BROKER_LIVE_SENT
    - BROKER_LIVE_ERROR
    - BROKER_NOT_READY
    """
    try:
        payload = _audit_sanitize(dict(event or {}))
        payload.setdefault("audit_version", "2026-07-06-EXECUTION-AUDIT-LOG-V1")
        payload.setdefault("ts", agora_sp_str())
        payload.setdefault("epoch", time.time())
        payload.setdefault("exchange", "bingx")
        payload.setdefault("execution_mode", EXECUTION_MODE)
        payload.setdefault("enable_real_trading", ENABLE_REAL_TRADING)
        payload.setdefault("broker_dry_run", BROKER_DRY_RUN)
        payload.setdefault("api_key_masked", mask_secret(BINGX_API_KEY))
        path = Path(EXECUTION_AUDIT_LOG_FILE)
        if path.parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
        return True
    except Exception:
        return False


def get_execution_audit_log(limit: int = None):
    """Retorna os últimos eventos do Execution Audit Log V1."""
    try:
        limit = int(limit or EXECUTION_AUDIT_LOG_MAX_READ)
        limit = max(1, min(limit, 500))
        path = Path(EXECUTION_AUDIT_LOG_FILE)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                out.append({"raw": line})
        return out
    except Exception as exc:
        return [{"ok": False, "error": str(exc)}]


def get_executions_log(limit: int = None):
    """Retorna os últimos eventos de execução registrados pelo broker."""
    try:
        limit = int(limit or EXECUTIONS_LOG_MAX_READ)
        path = Path(EXECUTIONS_LOG_FILE)
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                out.append({"raw": line})
        return out
    except Exception as exc:
        return [{"ok": False, "error": str(exc)}]


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




def _cleanup_execution_auth_tokens():
    now = time.time()
    expired = [token for token, data in list(_EXECUTION_AUTH_TOKENS.items()) if float(data.get("expires_at", 0)) < now]
    for token in expired:
        _EXECUTION_AUTH_TOKENS.pop(token, None)


def issue_execution_auth_token(context: dict = None, ttl_seconds: int = None):
    """
    Gera token efêmero para autorizar UMA tentativa de envio real.
    Chamado pelo Execution Engine imediatamente antes de chamar o broker em LIVE real.
    """
    _cleanup_execution_auth_tokens()
    ttl = int(ttl_seconds or EXECUTION_AUTH_TOKEN_TTL_SECONDS)
    token = secrets.token_urlsafe(32)
    now = time.time()
    _EXECUTION_AUTH_TOKENS[token] = {
        "created_at": now,
        "expires_at": now + max(1, ttl),
        "used": False,
        "context": dict(context or {}),
    }
    return {
        "ok": True,
        "token": token,
        "expires_at": _EXECUTION_AUTH_TOKENS[token]["expires_at"],
        "ttl_seconds": ttl,
        "context": dict(context or {}),
    }


def validate_execution_auth_token(token: str, context: dict = None, consume: bool = True):
    """
    Valida token de autorização de execução real.
    Em caso de sucesso, consome o token para evitar replay.
    """
    if not EXECUTION_AUTH_TOKEN_ENABLED:
        return {"ok": True, "status": "AUTH_DISABLED", "reason": "EXECUTION_AUTH_TOKEN_ENABLED=false"}

    _cleanup_execution_auth_tokens()

    if not token:
        return {"ok": False, "status": "MISSING_EXECUTION_AUTH_TOKEN", "reason": "execution_auth_token ausente"}

    data = _EXECUTION_AUTH_TOKENS.get(str(token))
    if not data:
        return {"ok": False, "status": "INVALID_EXECUTION_AUTH_TOKEN", "reason": "token inexistente ou expirado"}

    if data.get("used"):
        return {"ok": False, "status": "USED_EXECUTION_AUTH_TOKEN", "reason": "token já utilizado"}

    if float(data.get("expires_at", 0)) < time.time():
        _EXECUTION_AUTH_TOKENS.pop(str(token), None)
        return {"ok": False, "status": "EXPIRED_EXECUTION_AUTH_TOKEN", "reason": "token expirado"}

    if consume:
        data["used"] = True

    return {
        "ok": True,
        "status": "EXECUTION_AUTH_TOKEN_OK",
        "reason": "token válido",
        "expires_at": data.get("expires_at"),
        "context": data.get("context"),
    }


def is_real_live_send_enabled() -> bool:
    """
    Única condição autorizada para chamar create_order().
    Se qualquer uma das três travas estiver diferente, o broker deve retornar preview.
    """
    return EXECUTION_MODE == "LIVE" and ENABLE_REAL_TRADING is True and BROKER_DRY_RUN is False


def status_payload(check_ready: bool = False):
    payload = {
        "ok": True,
        "ts": agora_sp_str(),
        "exchange": "bingx",
        "execution_mode": EXECUTION_MODE,
        "enable_real_trading": ENABLE_REAL_TRADING,
        "broker_dry_run": BROKER_DRY_RUN,
        "position_mode": BINGX_POSITION_MODE,
        "hedge_mode_enabled": BINGX_HEDGE_MODE_ENABLED,
        "api_key_configured": bool(BINGX_API_KEY),
        "api_secret_configured": bool(BINGX_API_SECRET),
        "api_key_masked": mask_secret(BINGX_API_KEY),
        "default_type": BINGX_DEFAULT_TYPE,
        "margin_mode": BINGX_MARGIN_MODE,
        "default_leverage": BINGX_DEFAULT_LEVERAGE,
        "default_real_margin_usdt": DEFAULT_REAL_MARGIN_USDT,
        "default_real_leverage": DEFAULT_REAL_LEVERAGE,
        "default_effective_notional_usdt": DEFAULT_REAL_MARGIN_USDT * DEFAULT_REAL_LEVERAGE,
        "timeout_ms": BINGX_TIMEOUT_MS,
        "execution_audit_log_file": EXECUTION_AUDIT_LOG_FILE,
        "preview_isolation_version": "2026-07-06-BROKER-V2.6.1",
        "live_send_enabled": is_real_live_send_enabled(),
        "execution_auth_token_enabled": EXECUTION_AUTH_TOKEN_ENABLED,
        "execution_auth_token_ttl_seconds": EXECUTION_AUTH_TOKEN_TTL_SECONDS,
        "active_execution_auth_tokens": len(_EXECUTION_AUTH_TOKENS),
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


def _bot_env_prefix(bot):
    bot = str(bot or "").upper().strip()
    aliases = {
        "TRENDPRO": "TREND",
        "TREND_PRO": "TREND",
        "SMARTPREDATOR": "PREDATOR",
        "SMART_PREDATOR": "PREDATOR",
        "SMART PREDATOR": "PREDATOR",
    }
    return aliases.get(bot, bot)


def execution_config_for_bot(bot=None, margin_usdt=None, leverage=None):
    """
    Retorna configuração de margem/alavancagem por robô.
    Variáveis no Render:
    - FALCON_REAL_MARGIN_USDT / FALCON_REAL_LEVERAGE
    - PREDATOR_REAL_MARGIN_USDT / PREDATOR_REAL_LEVERAGE
    - DEFAULT_REAL_MARGIN_USDT / DEFAULT_REAL_LEVERAGE como fallback.
    """
    prefix = _bot_env_prefix(bot)
    margin_env = os.environ.get(f"{prefix}_REAL_MARGIN_USDT") if prefix else None
    lev_env = os.environ.get(f"{prefix}_REAL_LEVERAGE") if prefix else None

    try:
        margin = float(margin_usdt if margin_usdt is not None else (margin_env if margin_env is not None else DEFAULT_REAL_MARGIN_USDT))
    except Exception:
        margin = DEFAULT_REAL_MARGIN_USDT

    try:
        lev = int(leverage if leverage is not None else (lev_env if lev_env is not None else DEFAULT_REAL_LEVERAGE))
    except Exception:
        lev = DEFAULT_REAL_LEVERAGE

    if margin <= 0:
        margin = DEFAULT_REAL_MARGIN_USDT
    if lev <= 0:
        lev = DEFAULT_REAL_LEVERAGE

    planned_exposure = float(margin) * int(lev)

    return {
        "bot": prefix or None,
        "margin_usdt": float(margin),
        "leverage": int(lev),
        "effective_notional_usdt": planned_exposure,
        "planned_exposure_usdt": planned_exposure,
        "margin_mode": BINGX_MARGIN_MODE,
    }


def amount_from_notional(symbol, notional_usdt):
    """
    Calcula quantidade a partir do notional e retorna tupla compatível:
    amount, price_ref.
    """
    details = amount_details(symbol, notional_usdt)
    return details["amount"], details["price_ref"]


def amount_details(symbol, notional_usdt, margin_usdt=None, leverage=None):
    """
    Calcula quantidade a partir da exposição efetiva em USDT.
    Não usa variáveis externas margin/lev para evitar NameError.
    """
    sym = normalize_symbol(symbol)
    price = fetch_last_price(sym)
    if price <= 0:
        raise RuntimeError(f"preço inválido para {symbol}: {price}")

    planned_notional = float(notional_usdt)
    raw_amount = planned_notional / price

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

    actual_notional = amount * price if amount is not None and price is not None else None
    info = market_info(sym) if market else {"symbol": sym}

    return {
        "ok": True,
        "symbol": sym,
        "bingx_symbol": bingx_api_symbol(sym),
        "margin_usdt": margin_usdt,
        "leverage": leverage,
        "planned_notional_usdt": planned_notional,
        "notional_usdt": money(actual_notional, 8),
        "planned_exposure_usdt": money(planned_notional, 8),
        "actual_exposure_usdt": money(actual_notional, 8),
        "price_ref": price,
        "amount_raw": raw_amount,
        "amount": amount,
        "amount_final": amount,
        "effective_notional_usdt": money(actual_notional, 8),
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

def build_order_preview(
    symbol,
    side,
    margin_usdt=None,
    reduce_only=False,
    client_tag=None,
    leverage=None,
    bot=None,
    notional_usdt=None,
    risk_pct=None,
    free_balance_usdt=None,
    execution_auth_token=None,
):
    """
    Monta a prévia completa de uma ordem market.
    Não envia nada. Usada em READY/VERIFY e para debug antes do LIVE.

    risk_pct é opcional e pode ser passado pelo robô para calcular perda máxima estimada.
    free_balance_usdt é opcional. Se não vier, tentamos usar get_balance().
    """
    started = time.perf_counter()
    sym = normalize_symbol(symbol)
    order_side = normalize_side(side)
    api_side = bingx_api_side(side)
    position_side = bingx_position_side(side)

    cfg = execution_config_for_bot(bot=bot, margin_usdt=margin_usdt, leverage=leverage)
    margin = cfg["margin_usdt"]
    lev = cfg["leverage"]
    planned_exposure = float(notional_usdt) if notional_usdt is not None else cfg["effective_notional_usdt"]

    details = amount_details(sym, planned_exposure, margin_usdt=margin, leverage=lev)
    amount = details["amount"]
    price = details["price_ref"]
    market = details.get("market") or {}
    actual_exposure = details.get("effective_notional_usdt")

    client_order_id = str(client_tag or f"CQ-{int(time.time())}")[:32]

    free_balance = safe_float(free_balance_usdt)
    if free_balance is None:
        try:
            free_balance = safe_float(get_balance().get("free_usdt"))
        except Exception:
            free_balance = None

    estimated_margin_after_open = None
    if free_balance is not None:
        estimated_margin_after_open = free_balance - margin

    risk_pct_val = safe_float(risk_pct)
    estimated_max_loss_usdt = None
    if risk_pct_val is not None and actual_exposure is not None:
        estimated_max_loss_usdt = float(actual_exposure) * (risk_pct_val / 100.0)

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
    if position_side:
        api_payload["positionSide"] = position_side
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

    precision_payload = {
        "amount_raw": details.get("amount_raw"),
        "amount_final": amount,
        "amount": amount,
        "price_ref": price,
        "planned_exposure_usdt": money(planned_exposure, 2),
        "actual_exposure_usdt": money(actual_exposure, 2),
        "effective_notional_usdt": money(actual_exposure, 2),
        "market_symbol": market.get("symbol", sym),
        "market_id": market.get("id"),
        "amount_precision": market.get("amount_precision"),
        "price_precision": market.get("price_precision"),
        "min_amount": market.get("min_amount"),
        "min_cost": market.get("min_cost"),
        "precision_raw": market.get("precision"),
        "limits_raw": market.get("limits"),
        "precision_error": details.get("precision_error"),
    }

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
        "position_side": position_side,
        "hedge_mode_enabled": BINGX_HEDGE_MODE_ENABLED,
        "position_mode": BINGX_POSITION_MODE,
        "order_type": "market",
        "reduce_only": bool(reduce_only),
        "client_tag": client_tag,
        "client_order_id": client_order_id,
        "margin_usdt": margin,
        "margin_usdt_display": money(margin, 2),
        "leverage": lev,
        "leverage_display": f"{lev}x",
        "notional_usdt": money(actual_exposure, 8),
        "planned_exposure_usdt": money(planned_exposure, 8),
        "planned_exposure_usdt_display": money(planned_exposure, 2),
        "actual_exposure_usdt": money(actual_exposure, 8),
        "actual_exposure_usdt_display": money(actual_exposure, 2),
        "effective_notional_usdt": money(actual_exposure, 8),
        "effective_notional_usdt_display": money(actual_exposure, 2),
        "price_ref": price,
        "amount_raw": details.get("amount_raw"),
        "amount": amount,
        "amount_final": amount,
        "margin_mode": BINGX_MARGIN_MODE,
        "free_balance_usdt": free_balance,
        "estimated_margin_after_open_usdt": money(estimated_margin_after_open, 8),
        "estimated_margin_after_open_usdt_display": money(estimated_margin_after_open, 2),
        "risk_pct": risk_pct_val,
        "estimated_max_loss_usdt": money(estimated_max_loss_usdt, 8),
        "estimated_max_loss_usdt_display": money(estimated_max_loss_usdt, 4),
        "precision": precision_payload,
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
    """Texto curto para Telegram/log, caso a Central/Falcon/Predator queira exibir a prévia."""
    if not isinstance(preview, dict):
        return f"{title}\nPrévia indisponível."
    if not preview.get("ok"):
        return f"{title}\n❌ {preview.get('status')}\nErro: {preview.get('error')}"

    risk_line = ""
    if preview.get("risk_pct") is not None:
        risk_line = (
            f"Risco setup: {preview.get('risk_pct')}%\n"
            f"Perda máx. estimada: {preview.get('estimated_max_loss_usdt_display')} USDT\n"
        )

    balance_line = ""
    if preview.get("free_balance_usdt") is not None:
        balance_line = (
            f"Saldo livre atual: {preview.get('free_balance_usdt')} USDT\n"
            f"Saldo livre após abertura estimado: {preview.get('estimated_margin_after_open_usdt_display')} USDT\n"
        )

    return (
        f"{title}\n\n"
        f"Status: {preview.get('status')} | Enviada: {preview.get('sent')}\n"
        f"Modo: {preview.get('execution_mode')} | Real trading: {preview.get('enable_real_trading')}\n"
        f"Exchange: {preview.get('exchange')} | Endpoint: {preview.get('method')} {preview.get('endpoint')}\n\n"
        f"Símbolo: {preview.get('symbol')} | BingX: {preview.get('bingx_symbol')}\n"
        f"Side: {preview.get('api_side')} | PositionSide: {preview.get('position_side')} | Type: MARKET | ReduceOnly: {preview.get('reduce_only')}\n"
        f"Margin: {preview.get('margin_mode')} | Leverage: {preview.get('leverage_display')}\n\n"
        f"EXECUÇÃO\n"
        f"Margem usada: {preview.get('margin_usdt_display')} USDT\n"
        f"Alavancagem: {preview.get('leverage_display')}\n"
        f"Exposição planejada: {preview.get('planned_exposure_usdt_display')} USDT\n"
        f"Exposição efetiva: {preview.get('actual_exposure_usdt_display')} USDT\n"
        f"Preço ref.: {preview.get('price_ref')}\n"
        f"Quantidade raw: {preview.get('amount_raw')}\n"
        f"Quantidade enviada: {preview.get('amount')}\n"
        f"{risk_line}"
        f"{balance_line}\n"
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

def place_market_order(
    symbol,
    side,
    margin_usdt=None,
    reduce_only=False,
    client_tag=None,
    leverage=None,
    bot=None,
    notional_usdt=None,
    risk_pct=None,
    free_balance_usdt=None,
):
    """
    Broker V2.6.1 — Preview Isolation.

    Regra de ouro:
    - VERIFY, PAPER, READY, BROKER_DRY_RUN=true ou ENABLE_REAL_TRADING=false:
      monta preview, assinatura e constraints, mas retorna ANTES de create_order().
    - create_order() só pode ser chamado quando:
      EXECUTION_MODE=LIVE + ENABLE_REAL_TRADING=true + BROKER_DRY_RUN=false.
    """
    started = time.perf_counter()
    sym = normalize_symbol(symbol)
    order_side = normalize_side(side)

    cfg = execution_config_for_bot(bot=bot, margin_usdt=margin_usdt, leverage=leverage)
    margin = cfg["margin_usdt"]
    lev = cfg["leverage"]
    planned_exposure = float(notional_usdt) if notional_usdt is not None else cfg["effective_notional_usdt"]

    if margin <= 0 or planned_exposure <= 0:
        result = {
            "ok": False,
            "status": "REJECTED",
            "sent": False,
            "error": "margin/planned_exposure inválido",
            "symbol": sym,
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
        }
        log_execution_audit_event({"event": "BROKER_REJECTED_INVALID_SIZE", **result})
        return result

    live_send_enabled = is_real_live_send_enabled()

    # SEMPRE monta preview antes, tanto para validação quanto para a ordem real.
    try:
        preview = build_order_preview(
            sym,
            side,
            margin_usdt=margin,
            reduce_only=reduce_only,
            client_tag=client_tag,
            leverage=lev,
            bot=bot,
            notional_usdt=planned_exposure,
            risk_pct=risk_pct,
            free_balance_usdt=free_balance_usdt,
        )
    except Exception as exc:
        result = {
            "ok": False,
            "status": "PREVIEW_ERROR",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_PREVIEW_ERROR", **result})
        return result

    # Se constraints existirem e falharem, nunca envia.
    if preview.get("constraints_ok") is False:
        result = dict(preview)
        result.update({
            "ok": False,
            "status": "CONSTRAINTS_BLOCKED",
            "sent": False,
            "reason": "Exchange constraints bloquearam a ordem antes do envio.",
            "preview_isolation": True,
            "live_send_enabled": live_send_enabled,
        })
        log_execution_event({
            "event": "place_market_order",
            "mode": EXECUTION_MODE,
            "status": result.get("status"),
            "sent": False,
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "position_side": result.get("position_side"),
            "margin_usdt": result.get("margin_usdt"),
            "leverage": result.get("leverage"),
            "notional_usdt": result.get("notional_usdt"),
            "amount": result.get("amount"),
            "price_ref": result.get("price_ref"),
            "client_order_id": result.get("client_order_id"),
            "constraint_reasons": result.get("constraint_reasons"),
        })
        log_execution_audit_event({
            "event": "BROKER_CONSTRAINTS_BLOCKED",
            "sent": False,
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "position_side": result.get("position_side"),
            "margin_usdt": result.get("margin_usdt"),
            "leverage": result.get("leverage"),
            "notional_usdt": result.get("notional_usdt"),
            "amount": result.get("amount"),
            "price_ref": result.get("price_ref"),
            "client_order_id": result.get("client_order_id"),
            "constraint_reasons": result.get("constraint_reasons"),
            "preview_isolation": True,
        })
        return result

    # PREVIEW ISOLATION: se não está 100% LIVE real, retorna aqui.
    # NUNCA chama create_order() neste bloco.
    if not live_send_enabled:
        result = dict(preview)
        result.update({
            "ok": bool(preview.get("ok")),
            "status": "VERIFY" if EXECUTION_MODE == "VERIFY" else "DRY_RUN",
            "sent": False,
            "reason": "PREVIEW_ISOLATION: EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
            "preview_isolation": True,
            "live_send_enabled": False,
        })
        log_execution_event({
            "event": "place_market_order",
            "mode": EXECUTION_MODE,
            "status": result.get("status"),
            "sent": False,
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "position_side": result.get("position_side"),
            "margin_usdt": result.get("margin_usdt"),
            "leverage": result.get("leverage"),
            "notional_usdt": result.get("notional_usdt"),
            "planned_exposure_usdt": result.get("planned_exposure_usdt"),
            "actual_exposure_usdt": result.get("actual_exposure_usdt"),
            "amount": result.get("amount"),
            "price_ref": result.get("price_ref"),
            "client_order_id": result.get("client_order_id"),
            "latency_ms": result.get("latency_ms"),
            "payload": result.get("payload"),
            "precision": result.get("precision"),
            "market_id": result.get("market_id"),
            "market_symbol": result.get("market_symbol"),
            "effective_notional_usdt": result.get("effective_notional_usdt"),
            "signature_ok": result.get("signature_ok"),
            "risk_pct": result.get("risk_pct"),
            "estimated_max_loss_usdt": result.get("estimated_max_loss_usdt"),
            "preview_isolation": True,
        })
        log_execution_audit_event({
            "event": "BROKER_PREVIEW_ISOLATED",
            "status": result.get("status"),
            "sent": False,
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "position_side": result.get("position_side"),
            "margin_usdt": result.get("margin_usdt"),
            "leverage": result.get("leverage"),
            "notional_usdt": result.get("notional_usdt"),
            "planned_exposure_usdt": result.get("planned_exposure_usdt"),
            "actual_exposure_usdt": result.get("actual_exposure_usdt"),
            "amount": result.get("amount"),
            "price_ref": result.get("price_ref"),
            "client_order_id": result.get("client_order_id"),
            "constraints_ok": result.get("constraints_ok"),
            "signature_ok": result.get("signature_ok"),
            "risk_pct": result.get("risk_pct"),
            "estimated_max_loss_usdt": result.get("estimated_max_loss_usdt"),
            "payload": result.get("payload"),
            "preview_isolation": True,
            "live_send_enabled": False,
        })
        return result

    # A partir daqui é LIVE real autorizado pelas envs, mas ainda precisa do token efêmero.

    # LIVE real autorizado pelas envs, mas ainda exige token efêmero do Execution Engine.
    auth_payload = validate_execution_auth_token(
        execution_auth_token,
        context={
            "symbol": sym,
            "side": order_side,
            "position_side": bingx_position_side(side),
            "margin_usdt": margin,
            "leverage": lev,
            "planned_exposure": planned_exposure,
            "client_tag": client_tag,
        },
        consume=True,
    )
    if not auth_payload.get("ok"):
        result = {
            "ok": False,
            "status": "EXECUTION_AUTH_DENIED",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "position_side": bingx_position_side(side),
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
            "preview": preview,
            "preview_isolation": True,
            "live_send_enabled": live_send_enabled,
            "auth": auth_payload,
            "error": auth_payload.get("reason"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_EXECUTION_AUTH_DENIED", **result})
        return result

    ready = ready_check(cache_seconds=0)
    if not ready.get("ok"):
        result = {
            "ok": False,
            "status": "NOT_READY",
            "sent": False,
            "symbol": sym,
            "error": ready.get("error"),
            "ready": ready,
            "preview_isolation": True,
            "live_send_enabled": live_send_enabled,
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_NOT_READY", **result})
        return result

    amount = preview["amount"]
    price = preview["price_ref"]

    params = {}
    if reduce_only:
        params["reduceOnly"] = True
    position_side = bingx_position_side(side)
    if position_side:
        params["positionSide"] = position_side
    if client_tag:
        params["clientOrderId"] = str(client_tag)[:32]

    ex = exchange()
    try:
        margin_set = None
        leverage_set = None
        try:
            margin_set = ex.set_margin_mode(BINGX_MARGIN_MODE, sym)
        except Exception as exc:
            margin_set = {"ok": False, "error": str(exc)}
        try:
            # BingX Hedge Mode exige side no set_leverage.
            if position_side:
                leverage_set = ex.set_leverage(lev, sym, {"side": position_side})
            else:
                leverage_set = ex.set_leverage(lev, sym)
        except Exception as exc:
            leverage_set = {"ok": False, "error": str(exc)}

        order = ex.create_order(sym, "market", order_side, amount, None, params)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        result = {
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
            "position_side": position_side,
            "hedge_mode_enabled": BINGX_HEDGE_MODE_ENABLED,
            "position_mode": BINGX_POSITION_MODE,
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": preview.get("notional_usdt"),
            "planned_exposure_usdt": preview.get("planned_exposure_usdt"),
            "actual_exposure_usdt": preview.get("actual_exposure_usdt"),
            "amount": amount,
            "price_ref": price,
            "margin_mode": BINGX_MARGIN_MODE,
            "reduce_only": bool(reduce_only),
            "client_tag": client_tag,
            "client_order_id": preview.get("client_order_id"),
            "preview": preview,
            "preview_isolation": True,
            "live_send_enabled": True,
            "margin_set": margin_set,
            "leverage_set": leverage_set,
            "raw": order,
        }
        log_execution_event({"event": "place_market_order", **{k: v for k, v in result.items() if k != "raw"}})
        log_execution_audit_event({"event": "BROKER_LIVE_SENT", **{k: v for k, v in result.items() if k != "raw"}})
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "status": "ERROR",
            "sent": False,
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": order_side,
            "position_side": position_side,
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
            "amount": preview.get("amount") if isinstance(preview, dict) else None,
            "price_ref": preview.get("price_ref") if isinstance(preview, dict) else None,
            "preview": preview if isinstance(preview, dict) else None,
            "preview_isolation": True,
            "live_send_enabled": True,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_LIVE_ERROR", **result})
        return result

def close_position_market(symbol, side, amount=None, notional_usdt=None):
    """Fechamento simples. side deve ser lado da posição: LONG fecha vendendo; SHORT fecha comprando."""
    close_side = "sell" if str(side).upper() in {"LONG", "BUY"} else "buy"
    close_position_side = bingx_position_side(side)
    sym = normalize_symbol(symbol)

    if amount is None:
        if notional_usdt is None:
            return {"ok": False, "status": "REJECTED", "sent": False, "error": "amount ou notional_usdt obrigatório"}
        amount, _price = amount_from_notional(sym, float(notional_usdt))

    if EXECUTION_MODE != "LIVE" or not ENABLE_REAL_TRADING or BROKER_DRY_RUN:
        result = {
            "ok": True,
            "status": "DRY_RUN",
            "sent": False,
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": close_side,
            "position_side": close_position_side,
            "amount": amount,
            "reduce_only": True,
            "reason": "EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
        }
        log_execution_event({"event": "close_position_market", **result})
        log_execution_audit_event({"event": "BROKER_CLOSE_DRY_RUN", **result})
        return result

    ex = exchange()
    started = time.perf_counter()
    try:
        params = {"reduceOnly": True}
        if close_position_side:
            params["positionSide"] = close_position_side
        order = ex.create_order(sym, "market", close_side, float(amount), None, params)
        result = {
            "ok": True,
            "status": "SENT",
            "sent": True,
            "id": order.get("id"),
            "order_id": order.get("id"),
            "symbol": sym,
            "bingx_symbol": bingx_api_symbol(sym),
            "side": close_side,
            "position_side": close_position_side,
            "amount": amount,
            "reduce_only": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "raw": order,
        }
        log_execution_event({"event": "close_position_market", **{k: v for k, v in result.items() if k != "raw"}})
        log_execution_audit_event({"event": "BROKER_CLOSE_SENT", **{k: v for k, v in result.items() if k != "raw"}})
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "status": "ERROR",
            "sent": False,
            "symbol": sym,
            "side": close_side,
            "position_side": close_position_side,
            "amount": amount,
            "reduce_only": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
        }
        log_execution_event({"event": "close_position_market", **result})
        log_execution_audit_event({"event": "BROKER_CLOSE_ERROR", **result})
        return result
