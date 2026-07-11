# ==============================================================================
# CENTRAL QUANT - BROKER BINGX SAFE MODE
# Versão: 2026-07-09-BROKER-DISASTER-STOP-HEDGE-MODE-FIX-V1.1
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
# - V2.7 Disaster Stop Manager: após MARKET real preenchida, cria stop de desastre na BingX.
# - V2.7.8 / Fix V1.1: em Hedge Mode, disaster stop NÃO envia reduceOnly e mantém positionSide.
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

# Automatic Broker Preview Firewall V1
# Bloqueia previews automáticos no broker para bots específicos quando o envio real não está habilitado.
# Objetivo: impedir que sinais automáticos como PREDATOR gerem BROKER_PREVIEW_ISOLATED/DRY_RUN em /live.
BROKER_AUTO_PREVIEW_FIREWALL_ENABLED = env_bool("BROKER_AUTO_PREVIEW_FIREWALL_ENABLED", True)
BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS = {
    x.strip().upper()
    for x in os.environ.get("BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS", os.environ.get("PREDATOR_BROKER_PREVIEW_BLOCK_BOTS", "PREDATOR")).split(",")
    if x.strip()
}
BROKER_AUTO_PREVIEW_FIREWALL_STATUS = os.environ.get("BROKER_AUTO_PREVIEW_FIREWALL_STATUS", "AUTO_BROKER_PREVIEW_BLOCKED").strip().upper()


# Real Pilot Guard V1 — trava final no broker antes de create_order().
# Mesmo que algum robô chame broker.place_market_order direto, o envio real só passa
# se o piloto real estiver armado, o bot estiver na whitelist e o tamanho estiver dentro do limite.
BROKER_REAL_PILOT_GUARD_ENABLED = env_bool("BROKER_REAL_PILOT_GUARD_ENABLED", env_bool("CENTRAL_REAL_PILOT_GUARD_ENABLED", True))
BROKER_REAL_PILOT_FAIL_CLOSED = env_bool("BROKER_REAL_PILOT_FAIL_CLOSED", True)
BROKER_REAL_PILOT_ALLOW_REDUCE_ONLY_ALWAYS = env_bool("BROKER_REAL_PILOT_ALLOW_REDUCE_ONLY_ALWAYS", True)
BROKER_REAL_PILOT_ALLOWED_BOTS = {
    x.strip().upper()
    for x in os.environ.get(
        "BROKER_REAL_PILOT_ALLOWED_BOTS",
        os.environ.get("CENTRAL_REAL_PILOT_ALLOWED_BOTS", os.environ.get("REAL_PILOT_ALLOWED_BOTS", "FALCON")),
    ).split(",")
    if x.strip()
}
BROKER_REAL_PILOT_ALLOWED_SYMBOLS = {
    x.strip().upper().replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "").replace("-", "")
    for x in os.environ.get(
        "BROKER_REAL_PILOT_ALLOWED_SYMBOLS",
        os.environ.get("CENTRAL_REAL_PILOT_ALLOWED_SYMBOLS", os.environ.get("REAL_PILOT_ALLOWED_SYMBOLS", "*")),
    ).split(",")
    if x.strip()
}
BROKER_REAL_PILOT_MAX_NOTIONAL_USDT = float(os.environ.get(
    "BROKER_REAL_PILOT_MAX_NOTIONAL_USDT",
    os.environ.get("CENTRAL_REAL_PILOT_MAX_NOTIONAL_USDT", os.environ.get("REAL_PILOT_MAX_NOTIONAL_USDT", "20")),
))
BROKER_REAL_PILOT_MAX_OPEN_POSITIONS = int(float(os.environ.get(
    "BROKER_REAL_PILOT_MAX_OPEN_POSITIONS",
    os.environ.get("CENTRAL_REAL_PILOT_MAX_OPEN_POSITIONS", os.environ.get("REAL_PILOT_MAX_OPEN_POSITIONS", "1")),
)))

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

# Disaster Stop Manager V2.7
DISASTER_STOP_ENABLED = env_bool("DISASTER_STOP_ENABLED", True)
DISASTER_STOP_REQUIRE_FOR_LIVE = env_bool("DISASTER_STOP_REQUIRE_FOR_LIVE", True)
DISASTER_STOP_WORKING_TYPE = os.environ.get("DISASTER_STOP_WORKING_TYPE", "MARK_PRICE").strip().upper()
DISASTER_STOP_PRICE_BUFFER_PCT = float(os.environ.get("DISASTER_STOP_PRICE_BUFFER_PCT", "0"))
DISASTER_STOP_CLIENT_SUFFIX = os.environ.get("DISASTER_STOP_CLIENT_SUFFIX", "-DS")

# Broker Disaster Stop Hedge Mode Fix V1.1
# BingX em Hedge Mode rejeita reduceOnly em ordens STOP/STOP_MARKET.
# Portanto, para disaster stop em Hedge Mode, removemos reduceOnly e preservamos positionSide=LONG/SHORT.
DISASTER_STOP_HEDGE_MODE_FIX_VERSION = "2026-07-09-BROKER-DISASTER-STOP-HEDGE-MODE-FIX-V1.1"
_LAST_DISASTER_STOP_ERROR = None
_LAST_DISASTER_STOP_PAYLOAD_SANITIZED = None
_LAST_DISASTER_STOP_RESULT = None

# Endpoint usado apenas para prévia/assinatura no VERIFY.
# O envio real continua usando ccxt.create_order(), pois é mais seguro e padronizado.
BINGX_SWAP_ORDER_ENDPOINT = "/openApi/swap/v2/trade/order"

# Log local/persistente de execução. A Central lê este arquivo em /live, /sync e /executions.
# V2.7.4: por padrão usa CENTRAL_DATA_DIR para sobreviver melhor a restarts/deploys no Render.
CENTRAL_DATA_DIR = Path(os.environ.get("CENTRAL_DATA_DIR", os.environ.get("DATA_DIR", "/data")))
BROKER_LEGACY_EXECUTIONS_LOG_FILE = Path("daily_history") / "executions_log.jsonl"
BROKER_LEGACY_AUDIT_LOG_FILE = Path("daily_history") / "execution_audit_log.jsonl"
EXECUTIONS_LOG_FILE = os.environ.get("EXECUTIONS_LOG_FILE", str(CENTRAL_DATA_DIR / "broker_executions_log.jsonl"))
EXECUTIONS_LOG_MAX_READ = int(os.environ.get("EXECUTIONS_LOG_MAX_READ", "50"))

# Audit log persistente/estruturado para rastrear toda tentativa de execução.
# Diferente do log operacional, este arquivo é pensado para auditoria posterior.
EXECUTION_AUDIT_LOG_FILE = os.environ.get("EXECUTION_AUDIT_LOG_FILE", str(CENTRAL_DATA_DIR / "broker_execution_audit_log.jsonl"))
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


def _read_jsonl_file(path, limit=None, source=None):
    try:
        limit = int(limit or EXECUTION_AUDIT_LOG_MAX_READ)
        limit = max(1, min(limit, 500))
        p = Path(path)
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    item.setdefault("_source_file", str(p))
                    item.setdefault("_source_name", source or str(p))
                    out.append(item)
            except Exception:
                out.append({"raw": line[:1000], "_source_file": str(p), "_source_name": source or str(p)})
        return out
    except Exception as exc:
        return [{"ok": False, "error": str(exc), "_source_file": str(path), "_source_name": source or str(path)}]


def get_execution_audit_log(limit: int = None):
    """Retorna os últimos eventos do Execution Audit Log, lendo caminho novo e legado."""
    try:
        limit = int(limit or EXECUTION_AUDIT_LOG_MAX_READ)
        limit = max(1, min(limit, 500))
    except Exception:
        limit = EXECUTION_AUDIT_LOG_MAX_READ
    rows = []
    rows.extend(_read_jsonl_file(EXECUTION_AUDIT_LOG_FILE, limit=limit, source="broker_execution_audit_primary"))
    try:
        if str(BROKER_LEGACY_AUDIT_LOG_FILE) != str(EXECUTION_AUDIT_LOG_FILE):
            rows.extend(_read_jsonl_file(BROKER_LEGACY_AUDIT_LOG_FILE, limit=limit, source="broker_execution_audit_legacy"))
    except Exception:
        pass
    rows = sorted(rows, key=lambda x: float(x.get("epoch") or 0) if isinstance(x, dict) else 0, reverse=True)
    return rows[:limit]


def get_executions_log(limit: int = None):
    """Retorna os últimos eventos de execução registrados pelo broker, lendo caminho novo e legado."""
    try:
        limit = int(limit or EXECUTIONS_LOG_MAX_READ)
        limit = max(1, min(limit, 500))
    except Exception:
        limit = EXECUTIONS_LOG_MAX_READ
    rows = []
    rows.extend(_read_jsonl_file(EXECUTIONS_LOG_FILE, limit=limit, source="broker_executions_primary"))
    try:
        if str(BROKER_LEGACY_EXECUTIONS_LOG_FILE) != str(EXECUTIONS_LOG_FILE):
            rows.extend(_read_jsonl_file(BROKER_LEGACY_EXECUTIONS_LOG_FILE, limit=limit, source="broker_executions_legacy"))
    except Exception:
        pass
    rows = sorted(rows, key=lambda x: float(x.get("epoch") or 0) if isinstance(x, dict) else 0, reverse=True)
    return rows[:limit]

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
        "disaster_stop_enabled": DISASTER_STOP_ENABLED,
        "disaster_stop_require_for_live": DISASTER_STOP_REQUIRE_FOR_LIVE,
        "disaster_stop_working_type": DISASTER_STOP_WORKING_TYPE,
        "disaster_stop_price_buffer_pct": DISASTER_STOP_PRICE_BUFFER_PCT,
        "disaster_stop_hedge_mode_fix_version": DISASTER_STOP_HEDGE_MODE_FIX_VERSION,
        "last_disaster_stop_error": _LAST_DISASTER_STOP_ERROR,
        "last_disaster_stop_payload_sanitized": _LAST_DISASTER_STOP_PAYLOAD_SANITIZED,
        "last_disaster_stop_status": (_LAST_DISASTER_STOP_RESULT or {}).get("status") if isinstance(_LAST_DISASTER_STOP_RESULT, dict) else None,
        "last_disaster_stop_created": (_LAST_DISASTER_STOP_RESULT or {}).get("created") if isinstance(_LAST_DISASTER_STOP_RESULT, dict) else None,
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
    disaster_stop_result = None  # V2.7.2: também existe em preview/dry-run
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
    stop_loss_price=None,
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


def _safe_float_broker(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", ".").replace("%", "").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def validate_disaster_stop_price(side: str, entry_price, stop_price):
    s = str(side or "").upper().strip()
    entry = _safe_float_broker(entry_price)
    stop = _safe_float_broker(stop_price)

    if stop is None or stop <= 0:
        return {"ok": False, "reason": "stop_loss_price ausente ou inválido", "entry": entry, "stop": stop}

    if entry is not None and entry > 0:
        if s in {"LONG", "BUY"} and stop >= entry:
            return {"ok": False, "reason": f"stop inválido para LONG: stop={stop} >= entry={entry}", "entry": entry, "stop": stop}
        if s in {"SHORT", "SELL"} and stop <= entry:
            return {"ok": False, "reason": f"stop inválido para SHORT: stop={stop} <= entry={entry}", "entry": entry, "stop": stop}

    return {"ok": True, "reason": "stop válido", "entry": entry, "stop": stop}


def _apply_disaster_stop_buffer(side: str, stop_price: float) -> float:
    stop = float(stop_price)
    pct = float(DISASTER_STOP_PRICE_BUFFER_PCT or 0)
    if pct <= 0:
        return stop
    s = str(side or "").upper().strip()
    if s in {"LONG", "BUY"}:
        return stop * (1 - pct / 100.0)
    if s in {"SHORT", "SELL"}:
        return stop * (1 + pct / 100.0)
    return stop


def _disaster_stop_hedge_mode_detected() -> bool:
    mode = str(BINGX_POSITION_MODE or "").upper().strip()
    return bool(BINGX_HEDGE_MODE_ENABLED or mode in {"HEDGE", "HEDGED", "DUAL", "TRUE", "YES", "1", "ON"})


def _set_last_disaster_stop_diagnostic(result=None, error=None, payload_sanitized=None):
    global _LAST_DISASTER_STOP_ERROR, _LAST_DISASTER_STOP_PAYLOAD_SANITIZED, _LAST_DISASTER_STOP_RESULT
    _LAST_DISASTER_STOP_ERROR = error
    _LAST_DISASTER_STOP_PAYLOAD_SANITIZED = payload_sanitized
    if isinstance(result, dict):
        _LAST_DISASTER_STOP_RESULT = {k: v for k, v in result.items() if k != "raw"}
    else:
        _LAST_DISASTER_STOP_RESULT = None


def _build_disaster_stop_hedge_mode_fix_payload(position_side, reduce_only_requested=True):
    hedge_mode_detected = _disaster_stop_hedge_mode_detected()
    reduce_only_sent = bool(reduce_only_requested and not hedge_mode_detected)
    return {
        "version": DISASTER_STOP_HEDGE_MODE_FIX_VERSION,
        "hedge_mode_detected": hedge_mode_detected,
        "position_mode": BINGX_POSITION_MODE,
        "hedge_mode_enabled": BINGX_HEDGE_MODE_ENABLED,
        "position_side": position_side,
        "reduce_only_requested": bool(reduce_only_requested),
        "reduce_only_sent": reduce_only_sent,
        "reduce_only_removed_for_hedge_mode": bool(reduce_only_requested and hedge_mode_detected),
        "disaster_stop_payload_safe": True,
        "token_value_exposed": False,
    }


def create_disaster_stop_order(symbol, side, amount, stop_loss_price, client_tag=None, entry_price=None):
    """
    Cria stop de desastre na BingX após abertura real.
    A posição aberta é fechada no sentido oposto:
    LONG -> SELL stop; SHORT -> BUY stop.

    Fix V1.1:
    - Em Hedge Mode, a BingX rejeita reduceOnly em STOP/STOP_MARKET.
    - Portanto, removemos reduceOnly quando hedge_mode está ativo e mantemos positionSide.
    """
    if not DISASTER_STOP_ENABLED:
        result = {"ok": True, "enabled": False, "created": False, "status": "DISASTER_STOP_DISABLED"}
        _set_last_disaster_stop_diagnostic(result=result, error=None, payload_sanitized=None)
        return result

    sym = normalize_symbol(symbol)
    normalized = normalize_side(side)
    position_side = bingx_position_side(side)

    validation = validate_disaster_stop_price(side, entry_price, stop_loss_price)
    if not validation.get("ok"):
        result = {
            "ok": False,
            "enabled": True,
            "created": False,
            "status": "DISASTER_STOP_INVALID",
            "reason": validation.get("reason"),
            "validation": validation,
            "disaster_stop_hedge_mode_fix": _build_disaster_stop_hedge_mode_fix_payload(position_side),
        }
        _set_last_disaster_stop_diagnostic(result=result, error=validation.get("reason"), payload_sanitized=None)
        return result

    stop_price = _apply_disaster_stop_buffer(side, float(stop_loss_price))
    close_side = "sell" if normalized == "buy" else "buy"
    client_order_id = (str(client_tag or f"CQ-{int(time.time())}")[:24] + DISASTER_STOP_CLIENT_SUFFIX)[:32]

    fix_payload = _build_disaster_stop_hedge_mode_fix_payload(position_side, reduce_only_requested=True)
    reduce_only_sent = bool(fix_payload.get("reduce_only_sent"))

    params = {
        "stopPrice": float(stop_price),
        "workingType": DISASTER_STOP_WORKING_TYPE,
        "clientOrderId": client_order_id,
    }
    if reduce_only_sent:
        params["reduceOnly"] = True
    if position_side:
        params["positionSide"] = position_side

    payload_sanitized = {
        "symbol": sym,
        "bingx_symbol": bingx_api_symbol(sym),
        "type": "stop_market",
        "side": close_side,
        "amount": float(amount),
        "stopPrice": float(stop_price),
        "workingType": DISASTER_STOP_WORKING_TYPE,
        "clientOrderId": client_order_id,
        "positionSide": position_side,
        "reduceOnly_in_payload": bool(reduce_only_sent),
        "reduceOnly_value": True if reduce_only_sent else None,
        "hedge_mode_detected": bool(fix_payload.get("hedge_mode_detected")),
        "reduce_only_removed_for_hedge_mode": bool(fix_payload.get("reduce_only_removed_for_hedge_mode")),
        "disaster_stop_payload_safe": True,
    }

    ex = exchange()
    try:
        order = ex.create_order(sym, "stop_market", close_side, float(amount), None, params)
        result = {
            "ok": True,
            "enabled": True,
            "created": True,
            "status": "DISASTER_STOP_CREATED",
            "symbol": sym,
            "side": close_side,
            "position_side": position_side,
            "amount": float(amount),
            "stop_price": float(stop_price),
            "original_stop_price": float(stop_loss_price),
            "type": "stop_market",
            "working_type": DISASTER_STOP_WORKING_TYPE,
            "reduce_only": bool(reduce_only_sent),
            "reduce_only_requested": True,
            "reduce_only_sent": bool(reduce_only_sent),
            "hedge_mode_detected": bool(fix_payload.get("hedge_mode_detected")),
            "reduce_only_removed_for_hedge_mode": bool(fix_payload.get("reduce_only_removed_for_hedge_mode")),
            "disaster_stop_payload_safe": True,
            "disaster_stop_payload_sanitized": payload_sanitized,
            "disaster_stop_hedge_mode_fix": fix_payload,
            "client_order_id": client_order_id,
            "order_id": order.get("id"),
            "raw": order,
        }
        _set_last_disaster_stop_diagnostic(result=result, error=None, payload_sanitized=payload_sanitized)
        log_execution_audit_event({"event": "BROKER_DISASTER_STOP_CREATED", **{k: v for k, v in result.items() if k != "raw"}})
        return result
    except Exception as exc:
        error_text = str(exc)
        result = {
            "ok": False,
            "enabled": True,
            "created": False,
            "status": "DISASTER_STOP_ERROR",
            "symbol": sym,
            "side": close_side,
            "position_side": position_side,
            "amount": float(amount),
            "stop_price": float(stop_price),
            "original_stop_price": float(stop_loss_price),
            "type": "stop_market",
            "working_type": DISASTER_STOP_WORKING_TYPE,
            "reduce_only": bool(reduce_only_sent),
            "reduce_only_requested": True,
            "reduce_only_sent": bool(reduce_only_sent),
            "hedge_mode_detected": bool(fix_payload.get("hedge_mode_detected")),
            "reduce_only_removed_for_hedge_mode": bool(fix_payload.get("reduce_only_removed_for_hedge_mode")),
            "disaster_stop_payload_safe": True,
            "disaster_stop_payload_sanitized": payload_sanitized,
            "disaster_stop_hedge_mode_fix": fix_payload,
            "client_order_id": client_order_id,
            "error": error_text,
        }
        _set_last_disaster_stop_diagnostic(result=result, error=error_text, payload_sanitized=payload_sanitized)
        log_execution_audit_event({"event": "BROKER_DISASTER_STOP_ERROR", **result})
        return result




def _bot_key_for_firewall(bot):
    try:
        value = str(bot or "UNKNOWN").upper().strip()
    except Exception:
        value = "UNKNOWN"
    aliases = {
        "SMART_PREDATOR": "PREDATOR",
        "SMARTPREDATOR": "PREDATOR",
    }
    return aliases.get(value, value)


def _infer_bot_for_audit(bot=None, client_tag=None):
    """Infere bot para auditoria sem alterar a lógica de execução."""
    explicit = _bot_key_for_firewall(bot)
    if explicit and explicit != "UNKNOWN":
        return explicit
    tag = str(client_tag or "").upper().strip()
    if tag.startswith("FALCON") or "FALCON-" in tag:
        return "FALCON"
    if tag.startswith("PREDATOR") or "SMART_PREDATOR" in tag or "SMARTPREDATOR" in tag:
        return "PREDATOR"
    if tag.startswith("DONKEY"):
        return "DONKEY"
    if tag.startswith("COBRA"):
        return "COBRA"
    if tag.startswith("TURTLE"):
        return "TURTLE"
    if tag.startswith("TRENDPRO") or tag.startswith("TREND_PRO"):
        return "TRENDPRO"
    if tag.startswith("MEME"):
        return "MEME"
    return "UNKNOWN"


def _classify_preview_audit(bot=None, client_tag=None, status=None, sent=False, live_send_enabled=False):
    """Classificação humana para /live e auditorias."""
    bot_key = _infer_bot_for_audit(bot=bot, client_tag=client_tag)
    tag = str(client_tag or "").upper().strip()
    status_norm = str(status or "").upper().strip()
    if bool(sent):
        return "LIVE_SENT"
    if status_norm == BROKER_AUTO_PREVIEW_FIREWALL_STATUS:
        return "AUTO_PREVIEW_BLOCKED"
    if bot_key == "FALCON" and ("VERIFY" in tag or status_norm in {"VERIFY", "DRY_RUN"}):
        return "FALCON_VERIFY_AUTHORIZED"
    if status_norm in {"VERIFY", "DRY_RUN"}:
        return "SAFE_DRY_RUN"
    if not live_send_enabled:
        return "PREVIEW_ISOLATED_NO_SEND"
    return "UNKNOWN_NO_SEND"


def broker_preview_firewall_health(limit: int = 20):
    """Status leve do Automatic Broker Preview Firewall."""
    blocked_recent = []
    try:
        rows = get_execution_audit_log(limit=max(1, min(int(limit), 100))) or []
        for item in rows:
            if isinstance(item, dict) and str(item.get("event") or "").upper() == BROKER_AUTO_PREVIEW_FIREWALL_STATUS:
                blocked_recent.append(item)
    except Exception:
        blocked_recent = []
    return {
        "ok": True,
        "module": "broker_auto_preview_firewall_v1",
        "version": "2026-07-07-BROKER-AUTO-PREVIEW-FIREWALL-V1",
        "generated_at": agora_sp_str(),
        "enabled": BROKER_AUTO_PREVIEW_FIREWALL_ENABLED,
        "blocked_bots": sorted(BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS),
        "status_code": BROKER_AUTO_PREVIEW_FIREWALL_STATUS,
        "execution_mode": EXECUTION_MODE,
        "enable_real_trading": ENABLE_REAL_TRADING,
        "broker_dry_run": BROKER_DRY_RUN,
        "audit_file": str(EXECUTION_AUDIT_LOG_FILE),
        "executions_file": str(EXECUTIONS_LOG_FILE),
        "blocked_recent_count": len(blocked_recent),
        "blocked_recent": blocked_recent[-limit:],
        "notes": [
            "Bloqueia preview automático antes de build_order_preview/place_market_order quando bot está na lista bloqueada.",
            "Não bloqueia execução real quando live_send_enabled=True; esse caminho continua protegido por token/guards.",
            "Para liberar preview automático, ajuste BROKER_AUTO_PREVIEW_FIREWALL_ENABLED=false ou remova o bot de BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS.",
        ],
    }


def _automatic_broker_preview_firewall(*, sym, side, bot, client_tag, live_send_enabled):
    """Retorna bloqueio para previews automáticos de bots específicos antes de tocar no broker."""
    bot_key = _bot_key_for_firewall(bot)
    if not BROKER_AUTO_PREVIEW_FIREWALL_ENABLED:
        return {"blocked": False, "reason": "BROKER_AUTO_PREVIEW_FIREWALL_ENABLED=false", "bot_key": bot_key}
    if live_send_enabled:
        return {"blocked": False, "reason": "live_send_enabled=true", "bot_key": bot_key}
    if bot_key not in BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS:
        return {"blocked": False, "reason": f"bot fora da lista bloqueada: {bot_key}", "bot_key": bot_key}
    return {
        "blocked": True,
        "reason": f"preview automático bloqueado para bot={bot_key}; envio real desarmado/preflight não manual",
        "bot_key": bot_key,
        "symbol": sym,
        "side": side,
        "client_tag": client_tag,
        "blocked_bots": sorted(BROKER_BLOCK_AUTOMATIC_PREVIEW_BOTS),
    }


def _broker_rpg_v1_bool_env(names, default=False):
    for name in names:
        try:
            if name in os.environ:
                return env_bool(name, default), name
        except Exception:
            pass
    return bool(default), None


def _broker_rpg_v1_norm_symbol(value):
    return str(value or "").upper().strip().replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "").replace("-", "").replace("/", "")


def _broker_rpg_v1_open_positions_count():
    try:
        positions = get_positions() or []
    except Exception as exc:
        return {"ok": False, "count": None, "error": str(exc), "positions_checked": False}
    open_items = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        info = p.get("info") if isinstance(p.get("info"), dict) else {}
        candidates = [
            p.get("contracts"), p.get("contractSize"), p.get("positionAmt"), p.get("notional"), p.get("positionValue"),
            info.get("positionAmt"), info.get("positionValue"), info.get("availableAmt"), info.get("size"),
        ]
        found = False
        for value in candidates:
            try:
                if value is not None and abs(float(value)) > 0:
                    found = True
                    break
            except Exception:
                continue
        if found:
            open_items.append({
                "symbol": p.get("symbol") or info.get("symbol"),
                "side": p.get("side") or info.get("positionSide"),
                "contracts": p.get("contracts") or info.get("positionAmt"),
                "notional": p.get("notional") or p.get("positionValue") or info.get("positionValue"),
            })
    return {"ok": True, "count": len(open_items), "open_items": open_items[:10], "positions_checked": True}


def broker_real_pilot_guard_v1_validate(*, symbol, side, bot=None, notional_usdt=None, preview=None, reduce_only=False, live_send_enabled=False, client_tag=None):
    pilot_enabled, pilot_source = _broker_rpg_v1_bool_env([
        "CENTRAL_REAL_PILOT_ENABLED", "REAL_PILOT_ENABLED", "EXECUTION_REAL_PILOT_ENABLED", "BINGX_REAL_PILOT_ENABLED"
    ], False)
    central_real_enabled, central_real_source = _broker_rpg_v1_bool_env([
        "CENTRAL_REAL_EXECUTION_ENABLED", "REAL_EXECUTION_ENABLED", "EXECUTION_REAL_ENABLED", "ENABLE_REAL_EXECUTION"
    ], False)
    bot_key = _infer_bot_for_audit(bot=bot, client_tag=client_tag)
    symbol_key = _broker_rpg_v1_norm_symbol(symbol)
    preview = preview if isinstance(preview, dict) else {}
    effective_notional = round_float(
        preview.get("actual_exposure_usdt")
        or preview.get("effective_notional_usdt")
        or preview.get("notional_usdt")
        or notional_usdt,
        8,
        None,
    )
    checks = []
    reasons = []

    def add(code, ok, message, details=None):
        item = {"code": code, "ok": bool(ok), "message": message, "details": details or {}}
        checks.append(item)
        if not ok:
            reasons.append(message)
        return item

    if not live_send_enabled:
        return {
            "ok": True,
            "allowed": True,
            "applies": False,
            "status": "BROKER_REAL_PILOT_GUARD_NOT_APPLICABLE",
            "version": "2026-07-08-BROKER-REAL-PILOT-GUARD-V1",
            "reason": "live_send_enabled=false; broker ficará em preview/dry-run",
        }

    if reduce_only and BROKER_REAL_PILOT_ALLOW_REDUCE_ONLY_ALWAYS:
        return {
            "ok": True,
            "allowed": True,
            "applies": True,
            "status": "BROKER_REAL_PILOT_REDUCE_ONLY_ALLOWED",
            "version": "2026-07-08-BROKER-REAL-PILOT-GUARD-V1",
            "bot": bot_key,
            "symbol": symbol_key,
            "reduce_only": True,
            "reasons": [],
            "checks": [],
        }

    add("BROKER_REAL_PILOT_GUARD_ENABLED", BROKER_REAL_PILOT_GUARD_ENABLED, "BROKER_REAL_PILOT_GUARD_ENABLED=false")
    add("CENTRAL_REAL_PILOT_ENABLED", pilot_enabled, "CENTRAL_REAL_PILOT_ENABLED/REAL_PILOT_ENABLED precisa estar true", {"source": pilot_source})
    add("CENTRAL_REAL_EXECUTION_ENABLED", central_real_enabled, "CENTRAL_REAL_EXECUTION_ENABLED precisa estar true", {"source": central_real_source})
    add("ENABLE_REAL_TRADING", ENABLE_REAL_TRADING is True, "ENABLE_REAL_TRADING precisa estar true")
    add("BROKER_DRY_RUN_FALSE", BROKER_DRY_RUN is False, "BROKER_DRY_RUN precisa estar false")
    add("EXECUTION_MODE_LIVE", EXECUTION_MODE == "LIVE", "EXECUTION_MODE precisa estar LIVE")
    add("BOT_ALLOWED", bot_key in BROKER_REAL_PILOT_ALLOWED_BOTS, f"Bot {bot_key} não está liberado no broker", {"allowed_bots": sorted(BROKER_REAL_PILOT_ALLOWED_BOTS)})
    symbol_allowed = "*" in BROKER_REAL_PILOT_ALLOWED_SYMBOLS or symbol_key in BROKER_REAL_PILOT_ALLOWED_SYMBOLS
    add("SYMBOL_ALLOWED", symbol_allowed, f"Símbolo {symbol_key} não está liberado no broker", {"allowed_symbols": sorted(BROKER_REAL_PILOT_ALLOWED_SYMBOLS)})
    add("NOTIONAL_LIMIT", effective_notional is not None and float(effective_notional) <= BROKER_REAL_PILOT_MAX_NOTIONAL_USDT, f"Notional {effective_notional} USDT acima do limite {BROKER_REAL_PILOT_MAX_NOTIONAL_USDT} USDT", {"notional_usdt": effective_notional, "max_notional_usdt": BROKER_REAL_PILOT_MAX_NOTIONAL_USDT})
    pos_count = _broker_rpg_v1_open_positions_count()
    open_ok = bool(pos_count.get("ok") and int(pos_count.get("count") or 0) < BROKER_REAL_PILOT_MAX_OPEN_POSITIONS)
    if not pos_count.get("ok") and BROKER_REAL_PILOT_FAIL_CLOSED:
        open_ok = False
    add("MAX_OPEN_REAL_POSITIONS", open_ok, f"Limite de posições reais atingido ou não confirmado: {pos_count.get('count')} / {BROKER_REAL_PILOT_MAX_OPEN_POSITIONS}", pos_count)

    allowed = len(reasons) == 0
    return {
        "ok": allowed,
        "allowed": allowed,
        "applies": True,
        "status": "BROKER_REAL_PILOT_GUARD_ALLOWED" if allowed else "BLOCKED_BY_BROKER_REAL_PILOT_GUARD",
        "version": "2026-07-08-BROKER-REAL-PILOT-GUARD-V1",
        "ts": agora_sp_str(),
        "bot": bot_key,
        "symbol": symbol_key,
        "side": str(side or "").upper(),
        "notional_usdt": effective_notional,
        "max_notional_usdt": BROKER_REAL_PILOT_MAX_NOTIONAL_USDT,
        "max_open_positions": BROKER_REAL_PILOT_MAX_OPEN_POSITIONS,
        "open_positions": pos_count,
        "checks": checks,
        "reasons": reasons,
        "token_value_exposed": False,
    }

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
    execution_auth_token=None,
    stop_loss_price=None,
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
    disaster_stop_result = None  # V2.7.3: inicializada dentro de place_market_order
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
    audit_bot = _infer_bot_for_audit(bot=bot, client_tag=client_tag)

    preview_firewall = _automatic_broker_preview_firewall(
        sym=sym,
        side=order_side,
        bot=audit_bot,
        client_tag=client_tag,
        live_send_enabled=live_send_enabled,
    )
    if preview_firewall.get("blocked"):
        result = {
            "ok": False,
            "status": BROKER_AUTO_PREVIEW_FIREWALL_STATUS,
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "bot": audit_bot,
            "execution_classification": _classify_preview_audit(bot=audit_bot, client_tag=client_tag, status=BROKER_AUTO_PREVIEW_FIREWALL_STATUS, sent=False, live_send_enabled=live_send_enabled),
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
            "client_order_id": client_tag,
            "reason": preview_firewall.get("reason"),
            "preview_firewall": preview_firewall,
            "preview_isolation": True,
            "live_send_enabled": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({
            "event": "place_market_order",
            "mode": EXECUTION_MODE,
            "status": result.get("status"),
            "sent": False,
            "symbol": result.get("symbol"),
            "side": result.get("side"),
            "bot": result.get("bot"),
            "execution_classification": result.get("execution_classification"),
            "client_order_id": result.get("client_order_id"),
            "reason": result.get("reason"),
            "preview_firewall": preview_firewall,
        })
        log_execution_audit_event({
            "event": BROKER_AUTO_PREVIEW_FIREWALL_STATUS,
            **result,
        })
        return result

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
            "bot": audit_bot,
            "execution_classification": _classify_preview_audit(
                bot=audit_bot,
                client_tag=client_tag,
                status=("VERIFY" if EXECUTION_MODE == "VERIFY" else "DRY_RUN"),
                sent=False,
                live_send_enabled=live_send_enabled,
            ),
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
            "bot": result.get("bot"),
            "execution_classification": result.get("execution_classification"),
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
            "bot": result.get("bot"),
            "execution_classification": result.get("execution_classification"),
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

    # A partir daqui é LIVE real autorizado pelas envs, mas ainda precisa passar pelo Real Pilot Guard do broker.
    real_pilot_guard = broker_real_pilot_guard_v1_validate(
        symbol=sym,
        side=order_side,
        bot=audit_bot,
        notional_usdt=planned_exposure,
        preview=preview,
        reduce_only=reduce_only,
        live_send_enabled=live_send_enabled,
        client_tag=client_tag,
    )
    if not real_pilot_guard.get("allowed"):
        result = {
            "ok": False,
            "status": "BLOCKED_BY_BROKER_REAL_PILOT_GUARD",
            "sent": False,
            "symbol": sym,
            "side": order_side,
            "bot": audit_bot,
            "position_side": bingx_position_side(side),
            "margin_usdt": margin,
            "leverage": lev,
            "notional_usdt": planned_exposure,
            "preview": preview,
            "real_pilot_guard_v1": real_pilot_guard,
            "preview_isolation": True,
            "live_send_enabled": live_send_enabled,
            "error": "; ".join(real_pilot_guard.get("reasons") or ["Real Pilot Guard bloqueou envio real"]),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_REAL_PILOT_GUARD_BLOCKED", **result})
        return result

    # LIVE real autorizado pelas envs e pelo piloto, mas ainda exige token efêmero do Execution Engine.
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
            "disaster_stop": disaster_stop_result,
            "preview_isolation": True,
            "live_send_enabled": live_send_enabled,
            "auth": auth_payload,
            "error": auth_payload.get("reason"),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        log_execution_event({"event": "place_market_order", **result})
        log_execution_audit_event({"event": "BROKER_EXECUTION_AUTH_DENIED", **result})
        return result

    if DISASTER_STOP_ENABLED and DISASTER_STOP_REQUIRE_FOR_LIVE:
        stop_validation = validate_disaster_stop_price(side, preview.get("price_ref") if isinstance(preview, dict) else None, stop_loss_price)
        if not stop_validation.get("ok"):
            result = {
                "ok": False,
                "status": "DISASTER_STOP_REQUIRED_BLOCKED",
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
                "stop_validation": stop_validation,
                "error": stop_validation.get("reason"),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
            log_execution_event({"event": "place_market_order", **result})
            log_execution_audit_event({"event": "BROKER_DISASTER_STOP_REQUIRED_BLOCKED", **result})
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

        disaster_stop_result = None
        if DISASTER_STOP_ENABLED:
            disaster_stop_result = create_disaster_stop_order(
                symbol=sym,
                side=side,
                amount=amount,
                stop_loss_price=stop_loss_price,
                client_tag=client_tag,
                entry_price=preview.get("price_ref") if isinstance(preview, dict) else None,
            )
            if DISASTER_STOP_REQUIRE_FOR_LIVE and not (isinstance(disaster_stop_result, dict) and disaster_stop_result.get("ok")):
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                result = {
                    "ok": False,
                    "status": "LIVE_SENT_BUT_DISASTER_STOP_FAILED",
                    "sent": True,
                    "requires_manual_attention": True,
                    "ts": agora_sp_str(),
                    "latency_ms": latency_ms,
                    "id": order.get("id"),
                    "order_id": order.get("id"),
                    "symbol": sym,
                    "bingx_symbol": bingx_api_symbol(sym),
                    "side": order_side,
                    "api_side": bingx_api_side(side),
                    "position_side": position_side,
                    "margin_usdt": margin,
                    "leverage": lev,
                    "notional_usdt": preview.get("notional_usdt"),
                    "amount": amount,
                    "price_ref": preview.get("price_ref") if isinstance(preview, dict) else None,
                    "client_tag": client_tag,
                    "client_order_id": preview.get("client_order_id") if isinstance(preview, dict) else None,
                    "preview": preview,
                    "disaster_stop": disaster_stop_result,
                    "raw": order,
                    "error": "Entrada enviada, mas stop de desastre falhou. Verifique/feche manualmente ou crie stop imediatamente.",
                }
                log_execution_event({"event": "place_market_order", **{k: v for k, v in result.items() if k != "raw"}})
                log_execution_audit_event({"event": "BROKER_LIVE_SENT_BUT_DISASTER_STOP_FAILED", **{k: v for k, v in result.items() if k != "raw"}})
                return result

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
            "disaster_stop": disaster_stop_result,
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



# ==============================================================================
# PATCH 2026-07-11 — FALCON LIVE PARTIAL / REAL RECON HELPERS V1
# ==============================================================================
# Objetivo:
# - Permitir sizing parcial-capaz: entrada >= 2x minQty para TP50 real.
# - Expor auditoria de TP50 real possível/impossível.
# - Fornecer busca defensiva de ordens/trades reais para reconciliação PnL/R.
# - Corrigir fechamento parcial em Hedge Mode removendo reduceOnly se necessário.
# Não altera env, não rearma LIVE e não envia ordem fora das travas já existentes.

FALCON_PARTIAL_CAPABLE_SIZING_VERSION = "2026-07-11-FALCON-PARTIAL-CAPABLE-SIZING-V1"
BINGX_REAL_RECONCILIATION_HELPERS_VERSION = "2026-07-11-BINGX-REAL-RECONCILIATION-HELPERS-V1"
BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION = "2026-07-11-BROKER-CLOSE-MARKET-HEDGE-SAFE-V1"


def _cq_patch_safe_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace(",", ".").replace("%", "").strip()
            if not value:
                return default
        return float(value)
    except Exception:
        return default


def broker_market_limits(symbol):
    """Retorna limites/precisão do mercado em formato estável para auditoria."""
    try:
        info = market_info(symbol)
        limits = info.get("limits") or {}
        amount_limits = limits.get("amount") or {}
        cost_limits = limits.get("cost") or {}
        precision = info.get("precision") or {}
        min_amount = _cq_patch_safe_float(info.get("min_amount") or amount_limits.get("min"), None)
        min_cost = _cq_patch_safe_float(info.get("min_cost") or cost_limits.get("min"), None)
        return {
            "ok": True,
            "version": FALCON_PARTIAL_CAPABLE_SIZING_VERSION,
            "symbol": normalize_symbol(symbol),
            "bingx_symbol": bingx_api_symbol(symbol),
            "min_amount": min_amount,
            "min_cost": min_cost,
            "amount_precision": info.get("amount_precision") or precision.get("amount"),
            "price_precision": info.get("price_precision") or precision.get("price"),
            "limits": limits,
            "precision": precision,
        }
    except Exception as exc:
        return {"ok": False, "version": FALCON_PARTIAL_CAPABLE_SIZING_VERSION, "symbol": normalize_symbol(symbol), "error": str(exc)}


def partial_capability_from_notional(symbol, notional_usdt, max_notional_usdt=None, min_parts=2):
    """
    Audita se uma ordem permite TP50 real.
    Regra: amount_total >= 2 * min_amount, de modo que TP50 e runner fiquem >= minQty.
    """
    sym = normalize_symbol(symbol)
    max_notional = _cq_patch_safe_float(max_notional_usdt, None)
    planned_notional = _cq_patch_safe_float(notional_usdt, 0.0) or 0.0
    try:
        details = amount_details(sym, planned_notional)
        limits = broker_market_limits(sym)
        min_amount = _cq_patch_safe_float((limits or {}).get("min_amount"), None)
        price_ref = _cq_patch_safe_float(details.get("price_ref"), None)
        amount = _cq_patch_safe_float(details.get("amount") or details.get("amount_final"), 0.0) or 0.0
        required_amount = (float(min_amount) * float(min_parts)) if min_amount else None
        required_notional = (required_amount * price_ref) if required_amount and price_ref else None
        partial_amount = (amount / 2.0) if amount else 0.0
        partial_capable = bool(min_amount and amount >= required_amount and partial_amount >= min_amount and (amount - partial_amount) >= min_amount)
        required_fits_max = True if max_notional is None or required_notional is None else required_notional <= max_notional + 1e-12
        return {
            "ok": True,
            "version": FALCON_PARTIAL_CAPABLE_SIZING_VERSION,
            "symbol": sym,
            "planned_notional_usdt": planned_notional,
            "max_notional_usdt": max_notional,
            "price_ref": price_ref,
            "amount": amount,
            "min_amount": min_amount,
            "min_parts": min_parts,
            "required_amount_for_real_tp50": required_amount,
            "required_notional_for_real_tp50": required_notional,
            "tp50_amount_if_half": partial_amount,
            "runner_amount_if_half": amount - partial_amount,
            "partial_capable": partial_capable,
            "required_fits_max_notional": required_fits_max,
            "status": "PARTIAL_CAPABLE" if partial_capable else ("NEEDS_NOTIONAL_UPSIZE" if required_fits_max else "BLOCKED_BY_MAX_NOTIONAL"),
            "amount_details": details,
            "market_limits": limits,
        }
    except Exception as exc:
        return {
            "ok": False,
            "version": FALCON_PARTIAL_CAPABLE_SIZING_VERSION,
            "symbol": sym,
            "planned_notional_usdt": planned_notional,
            "max_notional_usdt": max_notional,
            "partial_capable": False,
            "status": "PARTIAL_CAPABILITY_ERROR",
            "error": str(exc),
        }


def ensure_partial_capable_notional(symbol, planned_notional_usdt, max_notional_usdt=None, min_parts=2, safety_buffer_pct=0.25):
    """
    Se o notional planejado não permite TP50 real, sugere/retorna o menor notional
    que permita amount >= 2x minQty, desde que caiba no teto configurado.
    """
    audit = partial_capability_from_notional(symbol, planned_notional_usdt, max_notional_usdt=max_notional_usdt, min_parts=min_parts)
    if not audit.get("ok"):
        audit["allowed"] = False
        audit["notional_usdt"] = planned_notional_usdt
        return audit
    if audit.get("partial_capable"):
        audit["allowed"] = True
        audit["adjusted"] = False
        audit["notional_usdt"] = planned_notional_usdt
        return audit

    required = _cq_patch_safe_float(audit.get("required_notional_for_real_tp50"), None)
    max_notional = _cq_patch_safe_float(max_notional_usdt, None)
    if required is None or required <= 0:
        audit.update({"allowed": False, "adjusted": False, "notional_usdt": planned_notional_usdt, "reason": "required_notional_unavailable"})
        return audit
    adjusted = required * (1.0 + float(safety_buffer_pct or 0.0) / 100.0)
    if max_notional is not None and adjusted > max_notional + 1e-12:
        audit.update({
            "allowed": False,
            "adjusted": False,
            "notional_usdt": planned_notional_usdt,
            "suggested_notional_usdt": adjusted,
            "reason": f"notional necessário para TP50 real ({adjusted:.8f}) excede máximo ({max_notional:.8f})",
        })
        return audit
    # reaudita com o notional ajustado
    adjusted_audit = partial_capability_from_notional(symbol, adjusted, max_notional_usdt=max_notional_usdt, min_parts=min_parts)
    adjusted_audit.update({
        "allowed": bool(adjusted_audit.get("partial_capable")),
        "adjusted": True,
        "original_notional_usdt": planned_notional_usdt,
        "notional_usdt": adjusted,
        "adjustment_reason": "planned_notional_below_2x_min_qty_for_real_tp50",
    })
    return adjusted_audit


def tp50_partial_amount(symbol, total_amount):
    """Calcula quantidade real de TP50 respeitando minQty."""
    limits = broker_market_limits(symbol)
    min_amount = _cq_patch_safe_float((limits or {}).get("min_amount"), None)
    amount = _cq_patch_safe_float(total_amount, 0.0) or 0.0
    half = amount / 2.0
    ok = bool(min_amount and amount >= 2 * min_amount and half >= min_amount and (amount - half) >= min_amount)
    # Para BTC atual, se total=0.0002 e min=0.0001, retorna 0.0001.
    partial = min_amount if ok and half <= min_amount * 1.0000001 else half
    return {
        "ok": ok,
        "version": FALCON_PARTIAL_CAPABLE_SIZING_VERSION,
        "symbol": normalize_symbol(symbol),
        "total_amount": amount,
        "min_amount": min_amount,
        "tp50_amount": partial if ok else None,
        "runner_amount": (amount - partial) if ok else None,
        "status": "TP50_REAL_AMOUNT_OK" if ok else "TP50_REAL_AMOUNT_TOO_SMALL",
    }


# Mantém uma referência do fechamento antigo para fallback interno.
try:
    _ORIGINAL_CLOSE_POSITION_MARKET_BEFORE_20260711_PATCH = close_position_market
except Exception:
    _ORIGINAL_CLOSE_POSITION_MARKET_BEFORE_20260711_PATCH = None


def close_position_market(symbol, side, amount=None, notional_usdt=None, client_tag=None, reason="MANUAL_OR_TP50", allow_hedge_without_reduce_only=True):
    """
    Fechamento market seguro para parcial/TP50.
    Em Hedge Mode, remove reduceOnly por padrão porque a BingX pode rejeitar reduceOnly em algumas ordens;
    positionSide + lado oposto + quantidade exata fazem o fechamento da perna correta.
    """
    close_side = "sell" if str(side).upper() in {"LONG", "BUY"} else "buy"
    close_position_side = bingx_position_side(side)
    sym = normalize_symbol(symbol)

    if amount is None:
        if notional_usdt is None:
            return {"ok": False, "status": "REJECTED", "sent": False, "error": "amount ou notional_usdt obrigatório", "version": BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION}
        amount, _price = amount_from_notional(sym, float(notional_usdt))

    amount = float(amount)
    if amount <= 0:
        return {"ok": False, "status": "REJECTED", "sent": False, "error": "amount inválido", "amount": amount, "version": BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION}

    hedge_mode = _disaster_stop_hedge_mode_detected()
    reduce_only_sent = not (hedge_mode and allow_hedge_without_reduce_only)

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
            "reduce_only_requested": True,
            "reduce_only_sent": bool(reduce_only_sent),
            "reduce_only_removed_for_hedge_mode": bool(hedge_mode and not reduce_only_sent),
            "reason": "EXECUTION_MODE não LIVE ou ENABLE_REAL_TRADING=false ou BROKER_DRY_RUN=true",
            "close_reason": reason,
            "version": BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION,
        }
        log_execution_event({"event": "close_position_market", **result})
        log_execution_audit_event({"event": "BROKER_CLOSE_DRY_RUN", **result})
        return result

    ex = exchange()
    started = time.perf_counter()
    try:
        params = {}
        if reduce_only_sent:
            params["reduceOnly"] = True
        if close_position_side:
            params["positionSide"] = close_position_side
        if client_tag:
            params["clientOrderId"] = str(client_tag)[:32]
        order = ex.create_order(sym, "market", close_side, amount, None, params)
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
            "reduce_only_requested": True,
            "reduce_only_sent": bool(reduce_only_sent),
            "reduce_only_removed_for_hedge_mode": bool(hedge_mode and not reduce_only_sent),
            "close_reason": reason,
            "client_tag": client_tag,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "version": BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION,
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
            "reduce_only_requested": True,
            "reduce_only_sent": bool(reduce_only_sent),
            "reduce_only_removed_for_hedge_mode": bool(hedge_mode and not reduce_only_sent),
            "close_reason": reason,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": str(exc),
            "version": BROKER_CLOSE_MARKET_HEDGE_SAFE_VERSION,
        }
        log_execution_event({"event": "close_position_market", **result})
        log_execution_audit_event({"event": "BROKER_CLOSE_ERROR", **result})
        return result


def fetch_recent_orders(symbol=None, since=None, limit=100):
    """Busca defensiva de ordens recentes via CCXT para reconciliação. Não envia ordens."""
    sym = normalize_symbol(symbol) if symbol else None
    ex = exchange()
    rows = []
    errors = []
    for method_name in ["fetch_orders", "fetch_closed_orders", "fetch_open_orders"]:
        method = getattr(ex, method_name, None)
        if not callable(method):
            continue
        try:
            try:
                data = method(sym, since, limit) if sym else method(None, since, limit)
            except TypeError:
                data = method(sym) if sym else method()
            for item in data or []:
                if isinstance(item, dict):
                    item = dict(item)
                    item.setdefault("_source_method", method_name)
                    rows.append(item)
        except Exception as exc:
            errors.append({"method": method_name, "error": str(exc)})
    return {"ok": True, "version": BINGX_REAL_RECONCILIATION_HELPERS_VERSION, "symbol": sym, "count": len(rows), "orders": rows[-int(limit or 100):], "errors": errors}


def fetch_recent_my_trades(symbol=None, since=None, limit=100):
    """Busca defensiva de trades/fills recentes via CCXT para reconciliação. Não envia ordens."""
    sym = normalize_symbol(symbol) if symbol else None
    ex = exchange()
    try:
        try:
            data = ex.fetch_my_trades(sym, since, limit) if sym else ex.fetch_my_trades(None, since, limit)
        except TypeError:
            data = ex.fetch_my_trades(sym) if sym else ex.fetch_my_trades()
        return {"ok": True, "version": BINGX_REAL_RECONCILIATION_HELPERS_VERSION, "symbol": sym, "count": len(data or []), "trades": data or []}
    except Exception as exc:
        return {"ok": False, "version": BINGX_REAL_RECONCILIATION_HELPERS_VERSION, "symbol": sym, "error": str(exc), "trades": []}


def reconcile_order_from_bingx(symbol=None, order_id=None, client_order_id=None, since=None, limit=150):
    """Tenta localizar ordem/trades/fills relacionados para alimentar Real PnL/R."""
    orders_payload = fetch_recent_orders(symbol=symbol, since=since, limit=limit)
    trades_payload = fetch_recent_my_trades(symbol=symbol, since=since, limit=limit)
    oid = str(order_id or "").strip().lower()
    cid = str(client_order_id or "").strip().lower()

    def match_item(item):
        if not isinstance(item, dict):
            return False
        values = [item.get("id"), item.get("order"), item.get("orderId"), item.get("clientOrderId"), item.get("client_order_id")]
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        values += [info.get("orderId"), info.get("orderID"), info.get("clientOrderId"), info.get("clientOrderID")]
        vals = [str(x or "").strip().lower() for x in values]
        return bool((oid and oid in vals) or (cid and cid in vals))

    matched_orders = [o for o in (orders_payload.get("orders") or []) if match_item(o)]
    matched_trades = [t for t in (trades_payload.get("trades") or []) if match_item(t)]
    return {
        "ok": True,
        "version": BINGX_REAL_RECONCILIATION_HELPERS_VERSION,
        "symbol": normalize_symbol(symbol) if symbol else None,
        "order_id": order_id,
        "client_order_id": client_order_id,
        "matched_orders_count": len(matched_orders),
        "matched_trades_count": len(matched_trades),
        "matched_orders": matched_orders,
        "matched_trades": matched_trades,
        "orders_errors": orders_payload.get("errors"),
        "trades_error": trades_payload.get("error") if not trades_payload.get("ok") else None,
    }

# ==============================================================================
# PATCH 2026-07-11 — DISASTER STOP CLOSE-POSITION PREVIEW V1
# ==============================================================================
DISASTER_STOP_CLOSE_POSITION_PREVIEW_VERSION = "2026-07-11-DISASTER-STOP-CLOSE-POSITION-PREVIEW-V1"


def build_disaster_stop_close_position_preview(symbol, side, stop_loss_price, client_tag=None, entry_price=None):
    """
    Preview observacional de payload para testar hipótese de stop 'posição inteira'.
    Não envia ordem. A execução real desse modo só deve ser habilitada depois de teste controlado.
    """
    sym = normalize_symbol(symbol)
    normalized = normalize_side(side)
    position_side = bingx_position_side(side)
    validation = validate_disaster_stop_price(side, entry_price, stop_loss_price)
    stop_price = _apply_disaster_stop_buffer(side, float(stop_loss_price)) if validation.get("ok") else stop_loss_price
    close_side = "sell" if normalized == "buy" else "buy"
    client_order_id = (str(client_tag or f"CQ-CP-{int(time.time())}")[:24] + "-CPDS")[:32]
    payload = {
        "symbol": bingx_api_symbol(sym),
        "side": close_side.upper(),
        "type": "STOP_MARKET",
        "stopPrice": float(stop_price) if _cq_patch_safe_float(stop_price) else stop_price,
        "workingType": DISASTER_STOP_WORKING_TYPE,
        "closePosition": True,
        "clientOrderId": client_order_id,
    }
    if position_side:
        payload["positionSide"] = position_side
    return {
        "ok": bool(validation.get("ok")),
        "version": DISASTER_STOP_CLOSE_POSITION_PREVIEW_VERSION,
        "mode": "PREVIEW_ONLY_NO_ORDER_SENT",
        "symbol": sym,
        "side": close_side,
        "position_side": position_side,
        "stop_price": stop_price,
        "client_order_id": client_order_id,
        "validation": validation,
        "payload_preview": payload,
        "notes": [
            "Este preview não confirma que a BingX aceitará closePosition via CCXT/API.",
            "Só habilitar envio real depois de teste controlado em tamanho mínimo e com Falcon desarmado.",
        ],
    }
