# Ajuste Central Quant: startup guard padronizado em 0 por padrão; arquitetura alinhada em FALCON.
# ==============================================================================
# FALCON STRIKE - ORB PRO - CENTRAL QUANT
# Versao: 2026-07-03-FALCON-STRIKE-ORB-V1-CQ-FRAMEWORK-TRADE-REGISTRY
#
# Robô de pesquisa/paper para Central Quant.
# NÃO executa ordens reais na BingX.
#
# Estratégia:
# - ORB = Opening Range Breakout.
# - FALCON15: range NY 09:30-09:45, opera rompimentos até 12:00 NY.
# - FALCON30: range NY 09:30-10:00, opera rompimentos até 12:00 NY.
# - Timeframe padrão: 15m.
# - Entrada BUY: candle fechado rompe acima da máxima do range.
# - Entrada SELL: candle fechado rompe abaixo da mínima do range.
# - Stop: lado oposto do range com buffer ATR.
# - TP50: 1R.
# - BE: após 1,5R, stop vai para BE + offset.
# - Trailing: após 2R, Chandelier/ATR no M15.
#
# Variáveis principais:
# - ENABLE_FALCON=true
# - FALCON_TOKEN / FALCON_CHAT_ID
# - UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN
# - FALCON_WATCHLIST_FILE=watchlists/falcon.json
# - FALCON_ENABLED_SETUPS=15,30
# ============================================================================

import os
import json
import hashlib
import secrets
import time
import threading
import traceback
from datetime import datetime, timezone, timedelta, time as dtime
from zoneinfo import ZoneInfo

import requests
from telegram_notification_policy import send_automatic_telegram
import pandas as pd
import numpy as np
from exchange_manager import get_exchange, load_markets_once
from ccxt.base.errors import NetworkError, RateLimitExceeded, ExchangeError
from flask import Flask
from upstash_redis import Redis
from redis_bandwidth import (
    redis_compare_and_delete as bandwidth_redis_compare_and_delete,
    redis_get_authoritative as bandwidth_redis_get_authoritative,
    redis_get as bandwidth_redis_get,
    redis_set as bandwidth_redis_set,
    redis_set_if_absent as bandwidth_redis_set_if_absent,
)
from falcon_client_order_id import (
    FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION,
    ROLE_BREAK_EVEN_STOP,
    ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
    ROLE_ENTRY,
    ROLE_INITIAL_DISASTER_STOP,
    ROLE_MANAGED_CLOSE,
    ROLE_REPLACEMENT_STOP,
    ROLE_ROLLBACK_STOP,
    ROLE_TP50_CLOSE,
    ROLE_TRAILING_STOP,
    canonical_falcon_order_identity,
    canonical_falcon_order_identity_hash,
    generate_falcon_client_order_id,
    is_valid_falcon_client_order_id,
)
from account_client_order_id import (
    ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX,
    account_client_order_id_ledger_key,
    authorize_account_client_order_next_attempt,
    record_account_client_order_attempt_outcome,
    reserve_account_client_order_attempt,
)
from automatic_daily_summaries import CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED

try:
    import broker as central_broker
except Exception as _broker_import_exc:
    central_broker = None
    BROKER_IMPORT_ERROR = str(_broker_import_exc)
else:
    BROKER_IMPORT_ERROR = None

try:
    import history_manager as super_history
except Exception as _history_import_exc:
    super_history = None
    HISTORY_IMPORT_ERROR = str(_history_import_exc)
else:
    HISTORY_IMPORT_ERROR = None

try:
    import trade_registry as central_trade_registry
except Exception as _trade_registry_import_exc:
    central_trade_registry = None
    TRADE_REGISTRY_IMPORT_ERROR = str(_trade_registry_import_exc)
else:
    TRADE_REGISTRY_IMPORT_ERROR = None

try:
    import cq_bot_framework as cq_framework
except Exception as _cq_framework_import_exc:
    cq_framework = None
    CQ_FRAMEWORK_IMPORT_ERROR = str(_cq_framework_import_exc)
else:
    CQ_FRAMEWORK_IMPORT_ERROR = None

app = Flask(__name__)

# ==============================================================================
# CONFIG
# ============================================================================

BOT_NAME = os.environ.get("BOT_NAME", "Falcon Strike ORB PRO")
TIMEZONE_BR = timezone(timedelta(hours=-3))
TIMEZONE_NY = ZoneInfo("America/New_York")

TOKEN = (
    os.environ.get("FALCON_TOKEN")
    or os.environ.get("FALCON_TELEGRAM_BOT_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
)
CHAT_ID = (
    os.environ.get("FALCON_CHAT_ID")
    or os.environ.get("FALCON_TELEGRAM_CHAT_ID")
    or os.environ.get("TELEGRAM_CHAT_ID")
)

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
WATCHLIST_FILE = os.environ.get("FALCON_WATCHLIST_FILE", "watchlists/falcon.json")

ENABLE_FALCON = str(os.environ.get("ENABLE_FALCON", "true")).lower() in {"1", "true", "yes", "sim", "on"}

# Execução real segura.
# PAPER: igual ao comportamento atual.
# READY: valida BingX/API/Risk, mas NÃO envia ordens.
# VERIFY: monta/valida a ordem completa, mas NÃO envia.
# LIVE: envia automaticamente se ENABLE_REAL_TRADING=true e a Central aprovar em /can_open_trade.
FALCON_MODE = os.environ.get("FALCON_MODE", os.environ.get("EXECUTION_MODE", "PAPER")).strip().upper()
ENABLE_REAL_TRADING = str(os.environ.get("ENABLE_REAL_TRADING", "false")).lower() in {"1", "true", "yes", "sim", "on"}
FALCON_REAL_NOTIONAL_USDT = float(os.environ.get("FALCON_REAL_NOTIONAL_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "5")))
FALCON_REAL_MAX_POSITIONS = int(os.environ.get("FALCON_REAL_MAX_POSITIONS", "1"))
FALCON_USE_CENTRAL_RISK = str(os.environ.get("FALCON_USE_CENTRAL_RISK", "true")).lower() in {"1", "true", "yes", "sim", "on"}
CENTRAL_CAN_OPEN_TRADE_URL = os.environ.get(
    "CENTRAL_CAN_OPEN_TRADE_URL",
    f"http://127.0.0.1:{os.environ.get('PORT', '10000')}/can_open_trade"
)
TIMEFRAME = os.environ.get("FALCON_TIMEFRAME", "15m")
OHLCV_LIMIT = int(os.environ.get("FALCON_OHLCV_LIMIT", "300"))

ORB_START_HOUR = int(os.environ.get("FALCON_ORB_START_HOUR_NY", "9"))
ORB_START_MINUTE = int(os.environ.get("FALCON_ORB_START_MINUTE_NY", "30"))
ORB_TRADE_END_HOUR = int(os.environ.get("FALCON_TRADE_END_HOUR_NY", "12"))
ORB_TRADE_END_MINUTE = int(os.environ.get("FALCON_TRADE_END_MINUTE_NY", "0"))

ATR_LEN = int(os.environ.get("FALCON_ATR_LEN", "14"))
ADX_LEN = int(os.environ.get("FALCON_ADX_LEN", "14"))
EMA_FAST = int(os.environ.get("FALCON_EMA_FAST", "20"))
EMA_SLOW = int(os.environ.get("FALCON_EMA_SLOW", "50"))

TP50_R = float(os.environ.get("FALCON_TP50_R", "1.0"))
BE_TRIGGER_R = float(os.environ.get("FALCON_BE_TRIGGER_R", "1.5"))
TRAIL_TRIGGER_R = float(os.environ.get("FALCON_TRAIL_TRIGGER_R", "2.0"))
BE_OFFSET_PCT = float(os.environ.get("FALCON_BE_OFFSET_PCT", "0.10"))
TRAIL_ATR_MULT = float(os.environ.get("FALCON_TRAIL_ATR_MULT", "2.0"))
STOP_ATR_BUFFER = float(os.environ.get("FALCON_STOP_ATR_BUFFER", "0.10"))

MIN_ATR_PCT = float(os.environ.get("FALCON_MIN_ATR_PCT", "0.20"))
MAX_RISK_PCT = float(os.environ.get("FALCON_MAX_RISK_PCT", "3.0"))
MIN_RANGE_ATR = float(os.environ.get("FALCON_MIN_RANGE_ATR", "0.40"))
MAX_RANGE_ATR = float(os.environ.get("FALCON_MAX_RANGE_ATR", "4.00"))
MIN_VOLUME_REL_TO_SIGNAL = float(os.environ.get("FALCON_MIN_VOLUME_REL_TO_SIGNAL", "1.10"))
MIN_ADX_TO_SIGNAL = float(os.environ.get("FALCON_MIN_ADX_TO_SIGNAL", "12"))
SCORE_MIN_QUALITY_TO_SIGNAL = int(os.environ.get("FALCON_SCORE_MIN_QUALITY_TO_SIGNAL", "55"))

# off = sem alinhamento, h1 = H1, h1_h4 = H1 + H4.
# Deixe off na V1 para gerar amostra; depois podemos subir para h1/h1_h4.
ALIGNMENT_MODE = os.environ.get("FALCON_ALIGNMENT_MODE", "off").lower().strip()

MAX_OPEN_POSITIONS = int(os.environ.get("FALCON_MAX_OPEN_POSITIONS", "10"))
ALLOW_SAME_SYMBOL_BOTH_SETUPS = str(os.environ.get("FALCON_ALLOW_SAME_SYMBOL_BOTH_SETUPS", "false")).lower() in {"1", "true", "yes", "sim", "on"}
ONE_TRADE_PER_SYMBOL_PER_DAY = str(os.environ.get("FALCON_ONE_TRADE_PER_SYMBOL_PER_DAY", "true")).lower() in {"1", "true", "yes", "sim", "on"}

SCAN_SLEEP_SECONDS = int(os.environ.get("FALCON_SCAN_SLEEP_SECONDS", "60"))
MANAGEMENT_SLEEP_SECONDS = int(os.environ.get("FALCON_MANAGEMENT_SLEEP_SECONDS", "20"))
COMMAND_SLEEP_SECONDS = int(os.environ.get("FALCON_COMMAND_SLEEP_SECONDS", "2"))
FALCON_COMMANDS_ENABLED = False  # comandos centralizados na Central Quant; nunca usar getUpdates aqui
WATCHDOG_SLEEP_SECONDS = int(os.environ.get("FALCON_WATCHDOG_SLEEP_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("FALCON_WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("FALCON_WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))
STARTUP_GUARD_SECONDS = int(
    os.environ.get(
        "FALCON_STARTUP_GUARD_SECONDS",
        os.environ.get("STARTUP_SIGNAL_GRACE_SECONDS", "0")
    )
)

DAILY_SUMMARY_HOUR = int(os.environ.get("FALCON_DAILY_SUMMARY_HOUR", "23"))
DAILY_SUMMARY_MINUTE = int(os.environ.get("FALCON_DAILY_SUMMARY_MINUTE", "55"))
MONTHLY_SUMMARY_DAY = int(os.environ.get("FALCON_MONTHLY_SUMMARY_DAY", "1"))
MONTHLY_SUMMARY_HOUR = int(os.environ.get("FALCON_MONTHLY_SUMMARY_HOUR", "0"))
MONTHLY_SUMMARY_MINUTE = int(os.environ.get("FALCON_MONTHLY_SUMMARY_MINUTE", "5"))

ENABLED_SETUPS_RAW = os.environ.get("FALCON_ENABLED_SETUPS", "15,30")
ALL_SETUPS = {
    "FALCON15": {"short": "15", "label": "Falcon 15", "range_minutes": 15},
    "FALCON30": {"short": "30", "label": "Falcon 30", "range_minutes": 30},
}


def build_enabled_setups():
    raw = str(ENABLED_SETUPS_RAW or "15,30").replace(" ", "")
    parts = [x for x in raw.split(",") if x]
    lower_parts = [p.lower() for p in parts]
    enabled = {}
    for key, cfg in ALL_SETUPS.items():
        if cfg["short"] in parts or key.lower() in lower_parts:
            enabled[key] = cfg
    return enabled or ALL_SETUPS.copy()


SETUPS = build_enabled_setups()

POSITIONS_KEY = "falcon:positions"
SIGNALS_KEY = "falcon:signals"
TRADES_KEY = "falcon:trades"
EVENTS_KEY = "falcon:events"
COOLDOWN_KEY = "falcon:cooldowns"
DAILY_SUMMARY_KEY = "falcon:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "falcon:monthly_summary_sent"
LAST_CANDLES_KEY = "falcon:last_scanned_candles_by_symbol"
FUNNEL_KEY = "falcon:funnel"
FALCON_MANAGEMENT_ALERT_GUARD_KEY = "falcon:management_alert_guard:v1"
FALCON_CENTRAL_ONLY_TOMBSTONES_KEY = "falcon:central_only_reconcile:tombstones:v1"
FALCON_TERMINAL_STOP_RECOVERY_KEY = "falcon:terminal_stop_emergency_recovery:v1"
FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX = "falcon:terminal_stop_emergency_lifecycle_lock:v2"
FALCON_CLIENT_ORDER_ID_RESERVATION_PREFIX = ACCOUNT_CLIENT_ORDER_ID_LEDGER_PREFIX

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
redis_lock = threading.Lock()
position_mutation_lock = threading.RLock()
manual_close_outcome_projection_lock = threading.RLock()
management_alert_guard_lock = threading.RLock()
terminal_stop_recovery_lock = threading.RLock()
_management_alert_guard_memory = {}
_central_only_tombstones_memory = {}

exchange = get_exchange()

HEALTH = {
    "started_at": None,
    "last_scanner_run": None,
    "last_management_run": None,
    "last_command_run": None,
    "last_summary_run": None,
    "last_success": None,
    "last_error": None,
    "last_warning": None,
    "last_invalid_watchlist_check": None,
    "last_watchdog_alert": None,
    "last_watchdog_alert_ts": 0,
    "watchdog_last_check": None,
    "watchdog_last_status": "OK",
    "last_signals_sent": 0,
    "last_positions_count": 0,
    "last_watchlist_count": 0,
    "watchlist_total": 0,
    "watchlist_valid": 0,
    "watchlist_invalid": [],
    "signals_today": 0,
    "signals_month": 0,
    "trades_closed_today": 0,
    "trades_closed_month": 0,
    "tp50_today": 0,
    "be_today": 0,
    "trailing_today": 0,
    "stops_today": 0,
    "signals_falcon15_today": 0,
    "signals_falcon30_today": 0,
    "signals_buy_today": 0,
    "signals_sell_today": 0,
    "mfe_avg_pct": 0.0,
    "mae_avg_pct": 0.0,
    "mfe_avg_r": 0.0,
    "mae_avg_r": 0.0,
    "giveback_avg_pct": 0.0,
    "giveback_avg_r": 0.0,
    "expectancy_r": 0.0,
    "profit_factor_pct": 0.0,
    "profit_factor_r": 0.0,
    "top_mfe_month": [],
    "runners_3r": 0,
    "runners_5r": 0,
    "runners_10r": 0,
    "enabled_setups": list(SETUPS.keys()),
    "mode": FALCON_MODE,
    "alignment_mode": ALIGNMENT_MODE,
    "funnel_today": {},
    "execution_mode": FALCON_MODE,
    "enable_real_trading": ENABLE_REAL_TRADING,
    "broker_loaded": central_broker is not None,
    "broker_import_error": BROKER_IMPORT_ERROR,
    "trade_registry_loaded": central_trade_registry is not None,
    "trade_registry_import_error": TRADE_REGISTRY_IMPORT_ERROR,
    "last_trade_registry_event": None,
    "cq_framework_loaded": cq_framework is not None,
    "cq_framework_import_error": CQ_FRAMEWORK_IMPORT_ERROR,
    "last_execution_decision": None,
    "last_execution_order": None,
    "falcon_disaster_stop_active_verified": False,
    "falcon_disaster_stop_trigger_type": None,
    "falcon_disaster_stop_order_status": None,
    "falcon_disaster_stop_order_id": None,
    "falcon_disaster_stop_last_checked_at": None,
    "falcon_disaster_stop_protection_matches_position": False,
    "falcon_stop_anomaly_detected": False,
    "falcon_stop_anomaly_last_reason": None,
    "falcon_management_spam_guard_status": "READY",
    "falcon_management_spam_guard_last_reason": None,
    "falcon_management_spam_guard_suppressed_count": 0,
    "falcon_management_spam_guard_last_suppressed_at": None,
    "falcon_central_only_pending_count": 0,
    "falcon_terminal_stop_recovery_status": "IDLE",
    "falcon_terminal_stop_recovery_incident_id": None,
    "falcon_terminal_stop_recovery_last_at": None,
    "falcon_terminal_stop_recovery_sent": None,
    "falcon_terminal_stop_recovery_confirmed": None,
    "falcon_client_order_id_generator_version": FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION,
    "falcon_disaster_stop_client_order_id": None,
    "falcon_disaster_stop_created": False,
    "falcon_disaster_stop_client_order_id_reserved": False,
    "falcon_disaster_stop_client_order_id_unique": False,
    "falcon_disaster_stop_operationally_armed": False,
    "falcon_client_order_id_collision_detected": False,
    "falcon_client_order_id_collision_role": None,
    "falcon_client_order_id_collision_last_at": None,
    "falcon_client_order_id_reservation_status": "NOT_ATTEMPTED",
}

# ==============================================================================
# UTIL
# ============================================================================

def agora_sp():
    return datetime.now(TIMEZONE_BR)


def agora_ny():
    return datetime.now(TIMEZONE_NY)


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def date_key():
    return agora_sp().strftime("%Y-%m-%d")


def date_key_br():
    return agora_sp().strftime("%d/%m/%Y")


def month_key_br():
    return agora_sp().strftime("%m/%Y")


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def fmt_price(value):
    try:
        v = float(value)
        if v >= 100:
            return f"{v:.2f}"
        if v >= 1:
            return f"{v:.4f}"
        if v >= 0.01:
            return f"{v:.6f}"
        return f"{v:.8f}"
    except Exception:
        return str(value)


def fmt_pct(value):
    try:
        return f"{float(value):+.2f}%".replace(".", ",")
    except Exception:
        return "+0,00%"


def fmt_r(value):
    try:
        return f"{float(value):+.2f}R"
    except Exception:
        return "+0.00R"


def parse_br_datetime(value):
    try:
        if not value:
            return None
        return datetime.strptime(str(value), "%d/%m/%Y %H:%M")
    except Exception:
        return None


def minutes_since(value):
    dt = parse_br_datetime(value)
    if not dt:
        return None
    return round((agora_sp().replace(tzinfo=None) - dt).total_seconds() / 60, 2)


def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        print(message)
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=15)
        if r.status_code != 200:
            HEALTH["last_warning"] = f"telegram {r.status_code}: {r.text[:200]}"
            return False
        return True
    except Exception as exc:
        HEALTH["last_warning"] = f"telegram: {exc}"
        return False


def _safe_send_telegram_transport(message):
    try:
        return send_telegram(message)
    except Exception:
        return False


def safe_send_telegram(
    message,
    *,
    event_type="FALCON_NOTIFICATION",
    mode=None,
    operational_critical=False,
    manual_command=False,
):
    result = send_automatic_telegram(
        _safe_send_telegram_transport,
        message,
        bot="FALCON",
        event_type=event_type,
        mode=mode or FALCON_MODE,
        severity="CRITICAL" if operational_critical else None,
        operational_critical=operational_critical,
        manual_command=manual_command,
    )
    return bool(result.get("sent"))


def redis_get_json(key, default):
    try:
        with redis_lock:
            raw = bandwidth_redis_get(redis, key, caller=__name__)
        if raw is None:
            return default
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            return json.loads(raw)
        return raw
    except Exception as exc:
        HEALTH["last_warning"] = f"redis get {key}: {exc}"
        return default


def redis_set_json(key, value):
    try:
        with redis_lock:
            bandwidth_redis_set(redis, key, json.dumps(value, ensure_ascii=False), caller=__name__)
        return True
    except Exception as exc:
        HEALTH["last_warning"] = f"redis set {key}: {exc}"
        return False


def _falcon_client_order_id_health_update(reservation):
    reservation = reservation if isinstance(reservation, dict) else {}
    role = str(reservation.get("role") or "").upper().strip() or None
    HEALTH["falcon_client_order_id_generator_version"] = (
        FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION
    )
    HEALTH["falcon_client_order_id_reservation_status"] = reservation.get(
        "status"
    )
    if role == ROLE_INITIAL_DISASTER_STOP:
        HEALTH["falcon_disaster_stop_client_order_id"] = reservation.get(
            "client_order_id"
        )
        HEALTH["falcon_disaster_stop_client_order_id_unique"] = (
            reservation.get("client_order_id_unique") is True
        )
        HEALTH["falcon_disaster_stop_client_order_id_reserved"] = (
            reservation.get("client_order_id_reserved") is True
        )
    collision = reservation.get("collision_detected") is True
    if collision:
        HEALTH["falcon_client_order_id_collision_detected"] = True
        HEALTH["falcon_client_order_id_collision_role"] = role
        HEALTH["falcon_client_order_id_collision_last_at"] = data_hora_sp_str()
    else:
        HEALTH.setdefault("falcon_client_order_id_collision_detected", False)


def falcon_client_order_id_reservation_key(client_order_id):
    try:
        return account_client_order_id_ledger_key(client_order_id)
    except Exception:
        return None


def falcon_reserve_client_order_id(client_order_id, identity):
    """Delegate Falcon reservations to the permanent account-wide authority."""
    try:
        canonical = canonical_falcon_order_identity(**dict(identity or {}))
        account_identity = {
            key: canonical.get(key)
            for key in (
                "account_namespace", "bot", "role", "lifecycle_id",
                "symbol", "side", "attempt_id", "attempt_sequence",
                "canonical_operation_id", "entry_client_order_id",
                "entry_order_id", "stop_revision", "order_type",
            )
        }
        result = reserve_account_client_order_attempt(
            account_identity,
            client_order_id=client_order_id,
            redis_client=redis,
            set_if_absent=bandwidth_redis_set_if_absent,
            get_authoritative=bandwidth_redis_get_authoritative,
            now=lambda: datetime.now(timezone.utc).isoformat(),
        )
        result = dict(result or {})
        result.update({
            "role": canonical.get("role"),
            "identity_hash": result.get("attempt_identity_hash"),
            "revision": canonical.get("revision"),
            "attempt": canonical.get("attempt"),
            "same_identity": result.get("same_attempt") is True,
        })
        _falcon_client_order_id_health_update(result)
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "send_allowed": False,
            "status": "CLIENT_ORDER_ID_RESERVATION_ERROR",
            "client_order_id": str(client_order_id or "") or None,
            "client_order_id_unique": False,
            "collision_detected": False,
            "same_identity": False,
            "reconciliation_required": True,
            "role": str((identity or {}).get("operation") or "") or None,
            "error_type": type(exc).__name__,
            "reservation_state": None,
            "persistent": False,
        }
        _falcon_client_order_id_health_update(result)
        return result


def falcon_prepare_canonical_client_order_id(identity):
    try:
        client_order_id = generate_falcon_client_order_id(**dict(identity or {}))
    except Exception as exc:
        result = {
            "ok": False,
            "send_allowed": False,
            "status": "CLIENT_ORDER_ID_GENERATION_ERROR",
            "client_order_id": None,
            "client_order_id_unique": False,
            "collision_detected": False,
            "reconciliation_required": True,
            "role": str((identity or {}).get("operation") or "") or None,
            "error_type": type(exc).__name__,
        }
        _falcon_client_order_id_health_update(result)
        return result
    return falcon_reserve_client_order_id(client_order_id, identity)


def falcon_prepare_initial_disaster_stop_client_order_id(
    *, entry_order_id, entry_client_order_id, symbol, side, revision=0,
    attempt=0, lifecycle_id=None
):
    lifecycle_id = str(lifecycle_id or "").strip() or (
        f"CENTRAL-FALCON-LIFECYCLE:{str(entry_client_order_id or '').strip()}"
        if str(entry_client_order_id or "").strip()
        else None
    )
    return falcon_prepare_canonical_client_order_id({
        "bot": "FALCON",
        "lifecycle_id": lifecycle_id,
        "entry_client_order_id": entry_client_order_id,
        "entry_order_id": entry_order_id,
        "symbol": symbol,
        "side": side,
        "operation": ROLE_INITIAL_DISASTER_STOP,
        "revision": revision,
        "attempt": attempt,
    })


def redis_list_append(key, item, max_len=5000):
    data = redis_get_json(key, [])
    if not isinstance(data, list):
        data = []
    data.append(item)
    if len(data) > max_len:
        data = data[-max_len:]
    return redis_set_json(key, data)


def to_ccxt_symbol(symbol):
    s = str(symbol).upper().strip()
    if "/" in s:
        return s
    if s.endswith("USDT"):
        return f"{s[:-4]}/USDT:USDT"
    return s


def load_watchlist():
    candidates = [WATCHLIST_FILE, "watchlists/falcon.json", "watchlist_falcon.json", "watchlist.json"]
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data = data.get("symbols", data.get("watchlist", []))
                symbols, invalid = [], []
                for item in data:
                    raw = str(item).upper().strip()
                    s = raw.replace("/", "").replace(":USDT", "")
                    if not s:
                        continue
                    if not s.endswith("USDT"):
                        s = f"{s}USDT"
                    if len(s) < 6:
                        invalid.append(raw)
                    else:
                        symbols.append(s)
                symbols = sorted(set(symbols))
                HEALTH["watchlist_total"] = len(symbols) + len(invalid)
                HEALTH["watchlist_valid"] = len(symbols)
                HEALTH["watchlist_invalid"] = invalid
                HEALTH["last_watchlist_count"] = len(symbols)
                HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
                return symbols
        except Exception as exc:
            HEALTH["last_warning"] = f"watchlist {path}: {exc}"

    fallback = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
    HEALTH["watchlist_total"] = len(fallback)
    HEALTH["watchlist_valid"] = len(fallback)
    HEALTH["watchlist_invalid"] = []
    HEALTH["last_watchlist_count"] = len(fallback)
    HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
    return fallback


def safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=OHLCV_LIMIT):
    try:
        data = exchange.fetch_ohlcv(to_ccxt_symbol(symbol), timeframe=timeframe, limit=limit)
        if not data or len(data) < 40:
            return None
        df = pd.DataFrame(data, columns=["ts", "open", "high", "low", "close", "volume"])
        df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        return df
    except (NetworkError, RateLimitExceeded, ExchangeError) as exc:
        HEALTH["last_warning"] = f"ohlcv {symbol}: {exc}"
        return None
    except Exception as exc:
        HEALTH["last_warning"] = f"ohlcv {symbol}: {exc}"
        return None


def safe_fetch_price(symbol):
    try:
        ticker = exchange.fetch_ticker(to_ccxt_symbol(symbol))
        return safe_float(ticker.get("last") or ticker.get("close"))
    except Exception as exc:
        HEALTH["last_warning"] = f"price {symbol}: {exc}"
        return None


def add_indicators(df):
    df = df.copy()
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]).abs(),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_LEN).mean()
    df["ema20"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    df["volume_rel"] = df["volume"] / df["vol_ma20"]

    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=df.index)
    atr_adx = tr.rolling(ADX_LEN).mean()
    plus_di = 100 * plus_dm.rolling(ADX_LEN).mean() / atr_adx
    minus_di = 100 * minus_dm.rolling(ADX_LEN).mean() / atr_adx
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.rolling(ADX_LEN).mean()
    return df


def closed_candles(df):
    if df is None or len(df) < 40:
        return None
    return df.iloc[:-1].copy()


def position_id(symbol, setup, side, ny_date):
    return f"{setup}:{symbol}:{side}:{ny_date}"


def risk_pct(entry, stop):
    entry = safe_float(entry)
    stop = safe_float(stop)
    if entry <= 0:
        return 0.0
    return abs(entry - stop) / entry * 100.0


def pnl_pct_for_side(side, entry, price):
    entry = safe_float(entry)
    price = safe_float(price)
    if entry <= 0 or price <= 0:
        return 0.0
    if side == "LONG":
        return (price - entry) / entry * 100.0
    return (entry - price) / entry * 100.0


def r_for_side(side, entry, initial_stop, price):
    entry = safe_float(entry)
    initial_stop = safe_float(initial_stop)
    price = safe_float(price)
    risk = abs(entry - initial_stop)
    if risk <= 0:
        return 0.0
    if side == "LONG":
        return (price - entry) / risk
    return (entry - price) / risk


def get_positions():
    with position_mutation_lock:
        data = redis_get_json(POSITIONS_KEY, {})
        return data if isinstance(data, dict) else {}


def save_positions(positions):
    with position_mutation_lock:
        safe_positions = positions if isinstance(positions, dict) else {}
        tombstone_filter = globals().get("falcon_filter_reconciled_positions")
        if callable(tombstone_filter):
            safe_positions = tombstone_filter(safe_positions)
        HEALTH["last_positions_count"] = len(safe_positions)
        return redis_set_json(POSITIONS_KEY, safe_positions)


def register_falcon_trade_registry_open(pos):
    """Registra abertura do Falcon no Trade Registry central.

    Falha de registry nunca pode travar o robô. O Redis local do Falcon continua
    sendo salvo, e a Central registra o erro no HEALTH para diagnóstico.
    """
    if central_trade_registry is None:
        HEALTH["last_trade_registry_event"] = {
            "ok": False,
            "action": "OPEN_SKIPPED",
            "error": TRADE_REGISTRY_IMPORT_ERROR or "trade_registry import failed",
            "ts": data_hora_sp_str(),
        }
        return None

    try:
        live_order = (
            pos.get("live_order")
            if isinstance(pos.get("live_order"), dict)
            else {}
        )
        execution_mode = str(
            pos.get("execution_mode") or FALCON_MODE or ""
        ).upper().strip()
        registry_mode = str(
            pos.get("registry_mode")
            or ("REAL" if execution_mode == "LIVE" else "")
        ).upper().strip() or None
        broker_order_id = (
            pos.get("live_order_id")
            or pos.get("bingx_order_id")
            or live_order.get("order_id")
            or live_order.get("id")
        )
        client_order_id = (
            pos.get("live_client_order_id")
            or live_order.get("client_order_id")
            or live_order.get("client_tag")
        )
        result = central_trade_registry.register_open_trade(
            bot="FALCON",
            symbol=normalize_symbol_for_central(pos.get("symbol")),
            side=pos.get("side"),
            entry=pos.get("entry"),
            sl=pos.get("stop") or pos.get("initial_stop"),
            tp50=pos.get("tp50"),
            setup=pos.get("setup"),
            qty=(
                pos.get("initial_qty")
                or pos.get("qty")
                or pos.get("amount")
            ),
            source="falcon",
            execution_mode=execution_mode or None,
            registry_mode=registry_mode,
            broker_order_id=broker_order_id,
            client_order_id=client_order_id,
            order_id=broker_order_id,
            lifecycle_id=pos.get("lifecycle_id"),
            reconciliation_required=bool(pos.get("reconciliation_required")),
            entry_acknowledged=pos.get("entry_acknowledged"),
            entry_ack_persistence_degraded=pos.get(
                "entry_ack_persistence_degraded"
            ),
            metadata={
                "falcon_position_id": pos.get("id"),
                "setup_label": pos.get("setup_label"),
                "risk_pct": pos.get("risk_pct"),
                "score": pos.get("score_falcon") or pos.get("score"),
                "quality": pos.get("quality"),
                "timeframe": pos.get("timeframe") or TIMEFRAME,
                "execution_mode": pos.get("execution_mode") or FALCON_MODE,
                "ny_date": pos.get("ny_date"),
                "created_at": pos.get("created_at"),
                "execution_decision": pos.get("execution_decision"),
                "lifecycle_id": pos.get("lifecycle_id"),
                "entry_acknowledged": pos.get("entry_acknowledged"),
                "entry_ack_persistence_degraded": pos.get("entry_ack_persistence_degraded"),
                "reconciliation_required": bool(pos.get("reconciliation_required")),
                "live_management_reconciliation_pending": pos.get("live_management_reconciliation_pending"),
                "live_management_block_reason": pos.get("live_management_block_reason"),
                "registry_mode": registry_mode,
                "execution_sent": bool(live_order.get("sent")),
                "broker_entry_reference": pos.get("broker_entry_reference"),
                "broker_ack_at": pos.get("broker_ack_at"),
                "broker_order_id": broker_order_id,
                "client_order_id": client_order_id,
                "broker_stop_order_id": pos.get("broker_stop_order_id"),
                "broker_stop_client_order_id": pos.get("broker_stop_client_order_id"),
                "disaster_stop_client_order_id": pos.get("disaster_stop_client_order_id"),
                "disaster_stop_client_order_id_reserved": pos.get("disaster_stop_client_order_id_reserved"),
                "disaster_stop_client_order_id_unique": pos.get("disaster_stop_client_order_id_unique"),
                "disaster_stop_created": pos.get("disaster_stop_created"),
                "disaster_stop_operationally_armed": pos.get("disaster_stop_operationally_armed"),
                "client_order_id_reservation_status": pos.get("client_order_id_reservation_status"),
                "falcon_client_order_id_generator_version": pos.get("falcon_client_order_id_generator_version"),
                "broker_stop_price": pos.get("broker_stop_price"),
                "broker_stop_amount": pos.get("broker_stop_amount"),
                "broker_stop_status": pos.get("broker_stop_status"),
                "broker_stop_trigger_type": pos.get("broker_stop_trigger_type"),
                "broker_stop_side": pos.get("broker_stop_side"),
                "broker_stop_symbol": pos.get("broker_stop_symbol"),
                "broker_stop_type": pos.get("broker_stop_type"),
                "broker_stop_position_side": pos.get("broker_stop_position_side"),
                "broker_stop_reduce_only": pos.get("broker_stop_reduce_only"),
                "broker_stop_close_position": pos.get("broker_stop_close_position"),
                "broker_stop_hedge_mode_detected": pos.get("broker_stop_hedge_mode_detected"),
                "broker_stop_confirmed_at": pos.get("broker_stop_confirmed_at"),
                "disaster_stop_confirmed": pos.get("disaster_stop_confirmed"),
                "initial_qty": pos.get("initial_qty"),
                "remaining_qty": pos.get("remaining_qty"),
                "partial_capable_sizing": pos.get("partial_capable_sizing"),
                "real_management_version": pos.get("real_management_version"),
            },
        )
        if isinstance(result, dict) and result.get("ok"):
            pos["trade_registry_id"] = result.get("trade_id")
        HEALTH["last_trade_registry_event"] = {
            "ok": bool(isinstance(result, dict) and result.get("ok")),
            "action": "OPEN_REGISTERED",
            "trade_id": pos.get("trade_registry_id"),
            "symbol": pos.get("symbol"),
            "setup": pos.get("setup"),
            "side": pos.get("side"),
            "ts": data_hora_sp_str(),
        }
        return result
    except Exception as exc:
        HEALTH["last_warning"] = f"trade_registry open falcon: {exc}"
        HEALTH["last_trade_registry_event"] = {
            "ok": False,
            "action": "OPEN_ERROR",
            "error": str(exc),
            "symbol": pos.get("symbol"),
            "setup": pos.get("setup"),
            "side": pos.get("side"),
            "ts": data_hora_sp_str(),
        }
        return None


def close_falcon_trade_registry(pos, exit_price=None, result_pct=None, result_r=None, reason=None):
    """Fecha no Trade Registry central a posição previamente registrada."""
    if central_trade_registry is None:
        HEALTH["last_trade_registry_event"] = {
            "ok": False,
            "action": "CLOSE_SKIPPED",
            "error": TRADE_REGISTRY_IMPORT_ERROR or "trade_registry import failed",
            "ts": data_hora_sp_str(),
        }
        return None

    try:
        trade_id = pos.get("trade_registry_id")
        if not trade_id:
            trade_id = central_trade_registry.make_trade_id(
                "FALCON",
                normalize_symbol_for_central(pos.get("symbol")),
                pos.get("side"),
                pos.get("setup"),
            )

        tp50_execution = pos.get("tp50_real_execution") if isinstance(pos.get("tp50_real_execution"), dict) else {}
        result = central_trade_registry.close_trade(
            trade_id=trade_id,
            exit_price=exit_price,
            pnl_pct=result_pct,
            pnl_r=result_r,
            reason=reason,
            metadata={
                "falcon_position_id": pos.get("id"),
                "exit_reason": reason,
                "closed_at_falcon": data_hora_sp_str(),
                "mfe_pct": pos.get("mfe_pct"),
                "mae_pct": pos.get("mae_pct"),
                "mfe_r": pos.get("mfe_r"),
                "mae_r": pos.get("mae_r"),
                "giveback_pct": pos.get("giveback_pct"),
                "giveback_r": pos.get("giveback_r"),
                # Cópia observacional dos fatos LIVE já concluídos. O close
                # oficial acima continua sendo a única mutação de lifecycle do
                # Registry; estes campos não autorizam nem executam gestão.
                "broker_entry_reference": pos.get("broker_entry_reference"),
                "broker_order_id": pos.get("live_order_id"),
                "client_order_id": pos.get("live_client_order_id"),
                "initial_qty": pos.get("initial_qty"),
                "remaining_qty": pos.get("remaining_qty"),
                "tp50_real_executed": pos.get("tp50_real_executed"),
                "tp50_real_order_id": pos.get("tp50_real_order_id"),
                "tp50_amount": pos.get("tp50_amount"),
                "tp50_fill_price": pos.get("tp50_fill_price"),
                "tp50_status": tp50_execution.get("status"),
            },
        )
        HEALTH["last_trade_registry_event"] = {
            "ok": bool(isinstance(result, dict) and result.get("ok")),
            "action": "TRADE_CLOSED",
            "trade_id": trade_id,
            "symbol": pos.get("symbol"),
            "setup": pos.get("setup"),
            "side": pos.get("side"),
            "reason": reason,
            "ts": data_hora_sp_str(),
            "error": None if not isinstance(result, dict) else result.get("error"),
        }
        return result
    except Exception as exc:
        HEALTH["last_warning"] = f"trade_registry close falcon: {exc}"
        HEALTH["last_trade_registry_event"] = {
            "ok": False,
            "action": "CLOSE_ERROR",
            "error": str(exc),
            "symbol": pos.get("symbol"),
            "setup": pos.get("setup"),
            "side": pos.get("side"),
            "ts": data_hora_sp_str(),
        }
        return None


def get_trades():
    data = redis_get_json(TRADES_KEY, [])
    return data if isinstance(data, list) else []


def falcon_project_manual_close_outcome(outcome):
    """Project one Registry-authoritative outcome into Falcon statistics only.

    The helper never calls close_position, Registry or Broker.  It writes only
    the bounded Falcon statistical history and is idempotent across retries.
    """
    row = dict(outcome or {}) if isinstance(outcome, dict) else {}
    outcome_id = str(row.get("outcome_id") or "").strip()
    lifecycle_id = str(row.get("lifecycle_id") or "").strip()
    close_event_id = str(row.get("close_event_id") or "").strip()
    projection_key = f"{lifecycle_id}:{close_event_id}" if lifecycle_id and close_event_id else ""
    if str(row.get("bot") or "").upper().strip() != "FALCON" or not outcome_id or not projection_key:
        return {
            "ok": False,
            "status": "INVALID_OUTCOME_PROJECTION",
            "projection_pending": True,
            "no_order_sent": True,
        }

    try:
        with manual_close_outcome_projection_lock:
            warning_before = HEALTH.get("last_warning")
            raw_trades = redis_get_json(TRADES_KEY, None)
            warning_after = HEALTH.get("last_warning")
            if raw_trades is None and warning_after != warning_before and str(warning_after or "").startswith("redis get"):
                raise RuntimeError("falcon trades read failed")
            if raw_trades is not None and not isinstance(raw_trades, list):
                raise ValueError("falcon trades storage invalid")
            trades = list(raw_trades or [])
            for existing in trades:
                if not isinstance(existing, dict):
                    continue
                existing_key = f"{existing.get('lifecycle_id')}:{existing.get('close_event_id')}"
                if str(existing.get("outcome_id") or "") == outcome_id or existing_key == projection_key:
                    HEALTH["falcon_manual_close_outcome_projection_pending"] = False
                    HEALTH["falcon_manual_close_outcome_projection_status"] = "ALREADY_PROJECTED"
                    HEALTH["falcon_manual_close_outcome_last_outcome_id"] = outcome_id
                    return {
                        "ok": True,
                        "status": "ALREADY_PROJECTED",
                        "already_projected": True,
                        "projection_pending": False,
                        "outcome_id": outcome_id,
                        "no_order_sent": True,
                    }

            projection = {
                "status": "CLOSED",
                "bot": "FALCON",
                "setup": row.get("setup"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "trade_id": row.get("trade_id"),
                "lifecycle_id": lifecycle_id,
                "order_id": row.get("order_id"),
                "close_event_id": close_event_id,
                "outcome_id": outcome_id,
                "outcome_hash": row.get("outcome_hash"),
                "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
                "data_quality": row.get("data_quality") or "MANUAL_CONFIRMED",
                "entry": row.get("entry"),
                "initial_stop": row.get("initial_stop"),
                "exit_price": row.get("exit_price"),
                "closed_quantity": row.get("closed_quantity"),
                "closed_at": row.get("close_timestamp"),
                "exit_reason": row.get("close_reason"),
                "close_reason": row.get("close_reason"),
                "close_classification": row.get("close_classification"),
                "pnl_pct": row.get("pnl_pct"),
                "result_pct": row.get("pnl_pct"),
                "gross_pnl_usdt": row.get("gross_pnl_usdt"),
                "pnl_r": row.get("result_r"),
                "result_r": row.get("result_r"),
                "tp50_hit": bool(row.get("tp50_hit")),
                "learning_eligible": bool(row.get("learning_eligible", True)),
                "manual_close_outcome_projection": True,
            }
            trades.append(projection)
            if len(trades) > 5000:
                trades = trades[-5000:]
            stored = redis_set_json(TRADES_KEY, trades)
            if not stored:
                HEALTH["falcon_manual_close_outcome_projection_pending"] = True
                HEALTH["falcon_manual_close_outcome_projection_status"] = "PROJECTION_WRITE_FAILED"
                HEALTH["falcon_manual_close_outcome_last_outcome_id"] = outcome_id
                return {
                    "ok": False,
                    "status": "PROJECTION_WRITE_FAILED",
                    "projection_pending": True,
                    "outcome_id": outcome_id,
                    "no_order_sent": True,
                }
    except Exception as exc:
        HEALTH["falcon_manual_close_outcome_projection_pending"] = True
        HEALTH["falcon_manual_close_outcome_projection_status"] = "PROJECTION_EXCEPTION"
        HEALTH["falcon_manual_close_outcome_last_outcome_id"] = outcome_id
        HEALTH["last_warning"] = f"falcon manual close outcome projection: {type(exc).__name__}"
        return {
            "ok": False,
            "status": "PROJECTION_EXCEPTION",
            "projection_pending": True,
            "outcome_id": outcome_id,
            "error_type": type(exc).__name__,
            "no_order_sent": True,
        }

    HEALTH["falcon_manual_close_outcome_projection_pending"] = False
    HEALTH["falcon_manual_close_outcome_projection_status"] = "PROJECTED"
    HEALTH["falcon_manual_close_outcome_last_outcome_id"] = outcome_id
    return {
        "ok": True,
        "status": "PROJECTED",
        "already_projected": False,
        "projection_pending": False,
        "outcome_id": outcome_id,
        "no_order_sent": True,
    }


def get_signals():
    data = redis_get_json(SIGNALS_KEY, [])
    return data if isinstance(data, list) else []


def get_events():
    data = redis_get_json(EVENTS_KEY, [])
    return data if isinstance(data, list) else []


def get_last_candles_by_symbol():
    data = redis_get_json(LAST_CANDLES_KEY, {})
    return data if isinstance(data, dict) else {}


def save_last_candles_by_symbol(data):
    return redis_set_json(LAST_CANDLES_KEY, data)


def falcon_history_result_from_pct(value):
    try:
        v = float(value)
    except Exception:
        return ""
    if v > 0.05:
        return "WIN"
    if v < -0.05:
        return "LOSS"
    return "BE"


def falcon_history_payload(pos, event=None, extra=None):
    """Payload padrão Falcon → History/Journal/Lifecycle/Context/Learning.

    Esta função preserva compatibilidade com o payload antigo, mas passa a enriquecer
    os eventos usando o CQ Bot Framework. Ela é tolerante a falhas: se o framework
    não carregar, o Falcon continua operando com o payload legado.
    """
    pos = pos if isinstance(pos, dict) else {}
    event = event if isinstance(event, dict) else {}
    extra = extra if isinstance(extra, dict) else {}

    execution_decision = pos.get("execution_decision") or extra.get("execution_decision") or {}
    reasons = execution_decision.get("reasons") if isinstance(execution_decision, dict) else None
    warnings = execution_decision.get("warnings") if isinstance(execution_decision, dict) else None

    # Payload legado mantido por compatibilidade com History/Analytics atuais.
    payload = {
        "bot": "FALCON",
        "bot_name": BOT_NAME,
        "symbol": pos.get("symbol") or event.get("symbol"),
        "setup": pos.get("setup") or event.get("setup"),
        "setup_label": pos.get("setup_label"),
        "side": pos.get("side") or event.get("side"),
        "direction": pos.get("direction"),
        "trade_id": pos.get("id") or pos.get("trade_id"),
        "entry": pos.get("entry"),
        "stop": pos.get("stop"),
        "initial_stop": pos.get("initial_stop"),
        "tp50": pos.get("tp50"),
        "risk_pct": pos.get("risk_pct"),
        "score": pos.get("score_falcon") or pos.get("score"),
        "quality": pos.get("quality"),
        "timeframe": pos.get("timeframe") or TIMEFRAME,
        "mode": FALCON_MODE,
        "execution_mode": pos.get("execution_mode") or FALCON_MODE,
        "event_created_at": event.get("created_at") or data_hora_sp_str(),
        "created_at": event.get("created_at") or data_hora_sp_str(),
        "mfe_pct": pos.get("mfe_pct") or event.get("mfe_pct"),
        "mae_pct": pos.get("mae_pct") or event.get("mae_pct"),
        "mfe_r": pos.get("mfe_r") or event.get("mfe_r"),
        "mae_r": pos.get("mae_r") or event.get("mae_r"),
        "atr": pos.get("atr") or event.get("atr"),
        "atr_pct": pos.get("atr_pct") or event.get("atr_pct"),
        "adx": pos.get("adx") or event.get("adx"),
        "volume_rel": pos.get("volume_rel") or event.get("volume_rel"),
        "volume_status": pos.get("volume_status") or event.get("volume_status"),
        "market_regime": pos.get("market_regime") or event.get("market_regime"),
        "btc_alignment": pos.get("btc_alignment") or event.get("btc_alignment"),
        "volatility": pos.get("volatility") or event.get("volatility"),
        "execution_decision": execution_decision,
        "reasons": reasons or extra.get("reasons") or [],
        "warnings": warnings or extra.get("warnings") or [],
        "falcon_event": event,
    }

    for k, v in extra.items():
        if k not in payload:
            payload[k] = v

    if extra.get("result_pct") is not None:
        payload["result_pct"] = extra.get("result_pct")
        payload["pnl_pct"] = extra.get("result_pct")
    if extra.get("result_r") is not None:
        payload["result_r"] = extra.get("result_r")
        payload["pnl_r"] = extra.get("result_r")
    if extra.get("exit_price") is not None:
        payload["exit_price"] = extra.get("exit_price")

    # Enriquecimento padronizado para Context/Learning/Decision futuros.
    if cq_framework is not None:
        try:
            standard = cq_framework.build_standard_payload(
                bot="FALCON",
                bot_name=BOT_NAME,
                mode=FALCON_MODE,
                position=pos,
                event=event,
                extra=extra,
                event_type=event.get("event_type") or extra.get("event") or payload.get("event"),
                now_str=payload.get("event_created_at") or data_hora_sp_str(),
            )
            for key, value in standard.items():
                # Campos de contexto/framework devem prevalecer quando existem.
                if key in {
                    "standard_payload_version", "context", "score_bucket", "risk_bucket",
                    "hour", "minute", "weekday", "session_br", "volume_status",
                    "market_regime", "volatility", "risk_decision", "risk_allowed",
                    "paper_positions", "memory_usage_pct", "raw_event"
                }:
                    payload[key] = value
                elif payload.get(key) in (None, "", [], {}):
                    payload[key] = value
        except Exception as exc:
            HEALTH["last_warning"] = f"cq framework payload falcon: {exc}"

    return payload


def falcon_log_super_history(global_event_type, pos, event=None, extra=None):
    if super_history is None:
        return None
    try:
        payload = falcon_history_payload(pos, event=event, extra=extra)
        trade_id = payload.get("trade_id")
        return super_history.log_event(global_event_type, payload, source="falcon", trade_id=trade_id)
    except Exception as exc:
        HEALTH["last_warning"] = f"super history falcon: {exc}"
        return None


def record_event(event_type, pos, extra=None):
    event = {
        "event_type": event_type,
        "symbol": pos.get("symbol"),
        "setup": pos.get("setup"),
        "side": pos.get("side"),
        "created_at": data_hora_sp_str(),
        "trade_id": pos.get("id") or pos.get("trade_id"),
        "entry": pos.get("entry"),
        "stop": pos.get("stop"),
        "tp50": pos.get("tp50"),
        "score": pos.get("score_falcon") or pos.get("score"),
        "quality": pos.get("quality"),
        "risk_pct": pos.get("risk_pct"),
        "adx": pos.get("adx"),
        "atr": pos.get("atr"),
        "atr_pct": pos.get("atr_pct"),
        "volume_rel": pos.get("volume_rel"),
        "execution_mode": pos.get("execution_mode") or FALCON_MODE,
        "mfe_pct": safe_float(pos.get("mfe_pct")),
        "mae_pct": safe_float(pos.get("mae_pct")),
        "mfe_r": safe_float(pos.get("mfe_r")),
        "mae_r": safe_float(pos.get("mae_r")),
    }
    if extra:
        event.update(extra)

    if cq_framework is not None:
        try:
            standard_event = cq_framework.build_standard_payload(
                bot="FALCON",
                bot_name=BOT_NAME,
                mode=FALCON_MODE,
                position=pos,
                event=event,
                extra=extra or {},
                event_type=event_type,
                now_str=event.get("created_at") or data_hora_sp_str(),
            )
            for key in [
                "standard_payload_version", "context", "score_bucket", "risk_bucket",
                "hour", "minute", "weekday", "session_br", "volume_status",
                "market_regime", "volatility", "paper_positions", "memory_usage_pct",
            ]:
                if standard_event.get(key) is not None:
                    event[key] = standard_event.get(key)
        except Exception as exc:
            HEALTH["last_warning"] = f"cq framework event falcon: {exc}"

    redis_list_append(EVENTS_KEY, event)

    et = str(event_type or "").upper()
    if et == "SIGNAL":
        falcon_log_super_history("SIGNAL_CREATED", pos, event=event, extra=extra)
        falcon_log_super_history("TRADE_OPENED", pos, event=event, extra=extra)
    elif et == "TRADE_BLOCKED":
        payload_extra = dict(extra or {})
        payload_extra.setdefault("result", "DENY")
        falcon_log_super_history("TRADE_BLOCKED", pos, event=event, extra=payload_extra)
    elif et == "TP50":
        falcon_log_super_history("TP50_HIT", pos, event=event, extra=extra)
    elif et == "BE":
        falcon_log_super_history("BREAKEVEN", pos, event=event, extra=extra)
    elif et == "TRAILING":
        falcon_log_super_history("TRAILING_UPDATED", pos, event=event, extra=extra)
    elif et in {"STOP", "CLOSE", "CLOSED", "TRADE_CLOSED"}:
        payload_extra = dict(extra or {})
        payload_extra.setdefault("result", falcon_history_result_from_pct(payload_extra.get("result_pct")))
        payload_extra.setdefault("exit_reason", event_type)
        falcon_log_super_history("TRADE_CLOSED", pos, event=event, extra=payload_extra)
    else:
        falcon_log_super_history(f"FALCON_{et or 'EVENT'}", pos, event=event, extra=extra)

    return event

# ==============================================================================
# FUNIL
# ============================================================================

def get_funnel():
    data = redis_get_json(FUNNEL_KEY, {})
    if not isinstance(data, dict):
        data = {}
    today = date_key()
    if data.get("date") != today:
        data = {
            "date": today,
            "ativos_analisados": 0,
            "fora_janela_ny": 0,
            "range_nao_formado": 0,
            "rompimentos_15_buy": 0,
            "rompimentos_15_sell": 0,
            "rompimentos_30_buy": 0,
            "rompimentos_30_sell": 0,
            "reprovados_atr": 0,
            "reprovados_range": 0,
            "reprovados_volume": 0,
            "reprovados_adx": 0,
            "reprovados_risco": 0,
            "reprovados_score": 0,
            "reprovados_alinhamento": 0,
            "reprovados_posicao_ativa": 0,
            "reprovados_trade_dia": 0,
            "sinais_enviados": 0,
        }
        redis_set_json(FUNNEL_KEY, data)
    return data


def save_funnel(data):
    return redis_set_json(FUNNEL_KEY, data)


def funnel_inc(field, amount=1):
    data = get_funnel()
    data[field] = int(data.get(field, 0) or 0) + amount
    save_funnel(data)
    return data


def funnel_snapshot():
    data = get_funnel()
    return {k: int(v or 0) if isinstance(v, (int, float)) or str(v).isdigit() else v for k, v in data.items()}

# ==============================================================================
# ORB
# ============================================================================

def ny_dt_from_row(row):
    dt_utc = row["dt"]
    if getattr(dt_utc, "tzinfo", None) is None:
        dt_utc = dt_utc.tz_localize("UTC")
    return dt_utc.to_pydatetime().astimezone(TIMEZONE_NY)


def ny_time_bounds(range_minutes):
    start = dtime(ORB_START_HOUR, ORB_START_MINUTE)
    start_minutes = ORB_START_HOUR * 60 + ORB_START_MINUTE
    end_minutes = start_minutes + int(range_minutes)
    range_end = dtime(end_minutes // 60, end_minutes % 60)
    trade_end = dtime(ORB_TRADE_END_HOUR, ORB_TRADE_END_MINUTE)
    return start, range_end, trade_end


def get_orb_range(closed, range_minutes):
    if closed is None or len(closed) < 30:
        return None

    start_t, end_t, _ = ny_time_bounds(range_minutes)
    last_ny = ny_dt_from_row(closed.iloc[-1])
    target_date = last_ny.date()

    rows = []
    for _, row in closed.iterrows():
        ndt = ny_dt_from_row(row)
        if ndt.date() == target_date and start_t <= ndt.time() < end_t:
            rows.append(row)

    if not rows:
        return None

    rdf = pd.DataFrame(rows)
    return {
        "ny_date": target_date.isoformat(),
        "range_high": safe_float(rdf["high"].max()),
        "range_low": safe_float(rdf["low"].min()),
        "range_start_ny": start_t.strftime("%H:%M"),
        "range_end_ny": end_t.strftime("%H:%M"),
        "candles": len(rdf),
    }


def is_trade_window(row, range_minutes):
    _, end_t, trade_end = ny_time_bounds(range_minutes)
    ndt = ny_dt_from_row(row)
    return end_t <= ndt.time() <= trade_end


def trend_state_for_timeframe(symbol, timeframe):
    df = safe_fetch_ohlcv(symbol, timeframe=timeframe, limit=120)
    closed = closed_candles(df)
    if closed is None or len(closed) < EMA_SLOW + 5:
        return 0
    c = add_indicators(closed).iloc[-1]
    close = safe_float(c["close"])
    ema20 = safe_float(c["ema20"])
    ema50 = safe_float(c["ema50"])
    if close > ema20 > ema50:
        return 1
    if close < ema20 < ema50:
        return -1
    return 0


def passes_alignment(symbol, side):
    if ALIGNMENT_MODE == "off":
        return True
    want = 1 if side == "LONG" else -1
    h1 = trend_state_for_timeframe(symbol, "1h")
    if ALIGNMENT_MODE == "h1":
        return h1 == want
    h4 = trend_state_for_timeframe(symbol, "4h")
    if ALIGNMENT_MODE == "h1_h4":
        return h1 == want and h4 == want
    return True


def quality_from_score(score):
    score = int(score or 0)
    if score >= 80:
        return "ALTA 🟢"
    if score >= 65:
        return "MÉDIA 🟡"
    return "BAIXA 🔴"


def calc_falcon_score(row, close, atr, range_size, breakout_size, volume_rel, adx):
    score = 0
    atr_pct = atr / close * 100 if close else 0
    score += min(20, max(0, int((atr_pct / 1.0) * 20)))
    score += min(25, max(0, int((safe_float(volume_rel, 1.0) / 2.0) * 25)))
    breakout_atr = breakout_size / atr if atr > 0 else 0
    score += min(25, max(0, int((breakout_atr / 0.35) * 25)))
    range_atr = range_size / atr if atr > 0 else 0
    if MIN_RANGE_ATR <= range_atr <= 2.0:
        score += 20
    elif range_atr <= MAX_RANGE_ATR:
        score += 10
    score += min(10, max(0, int((safe_float(adx) / 30) * 10)))
    score = max(0, min(100, int(score)))
    return score, breakout_atr, range_atr


def has_open_position_for_symbol(positions, symbol, setup=None, side=None):
    for p in positions.values():
        if p.get("symbol") != symbol:
            continue
        if ALLOW_SAME_SYMBOL_BOTH_SETUPS:
            if setup and p.get("setup") == setup:
                return True
        else:
            return True
    return False


def had_trade_today(symbol, ny_date):
    if not ONE_TRADE_PER_SYMBOL_PER_DAY:
        return False
    for s in get_signals():
        if s.get("symbol") == symbol and s.get("ny_date") == ny_date:
            return True
    for t in get_trades():
        if t.get("symbol") == symbol and t.get("ny_date") == ny_date:
            return True
    return False


def analyze_symbol_setup(symbol, setup_key, setup_cfg, closed):
    if closed is None or len(closed) < 80:
        return None

    df = add_indicators(closed)
    row = df.iloc[-1]

    if not is_trade_window(row, setup_cfg["range_minutes"]):
        funnel_inc("fora_janela_ny")
        return None

    orb = get_orb_range(df, setup_cfg["range_minutes"])
    if not orb or orb["range_high"] <= 0 or orb["range_low"] <= 0 or orb["range_high"] <= orb["range_low"]:
        funnel_inc("range_nao_formado")
        return None

    close = safe_float(row["close"])
    high = safe_float(row["high"])
    low = safe_float(row["low"])
    atr = safe_float(row["atr"])
    adx = safe_float(row.get("adx"), 0.0)
    volume_rel = safe_float(row.get("volume_rel"), 1.0)

    if close <= 0 or atr <= 0:
        return None

    atr_pct = atr / close * 100
    if atr_pct < MIN_ATR_PCT:
        funnel_inc("reprovados_atr")
        return None

    range_high = orb["range_high"]
    range_low = orb["range_low"]
    range_size = range_high - range_low
    range_atr = range_size / atr if atr > 0 else 0

    if range_atr < MIN_RANGE_ATR or range_atr > MAX_RANGE_ATR:
        funnel_inc("reprovados_range")
        return None

    side = None
    breakout_size = 0.0
    if close > range_high:
        side = "LONG"
        breakout_size = close - range_high
        funnel_inc("rompimentos_15_buy" if setup_key == "FALCON15" else "rompimentos_30_buy")
    elif close < range_low:
        side = "SHORT"
        breakout_size = range_low - close
        funnel_inc("rompimentos_15_sell" if setup_key == "FALCON15" else "rompimentos_30_sell")

    if not side:
        return None

    if volume_rel < MIN_VOLUME_REL_TO_SIGNAL:
        funnel_inc("reprovados_volume")
        return None

    if adx < MIN_ADX_TO_SIGNAL:
        funnel_inc("reprovados_adx")
        return None

    if not passes_alignment(symbol, side):
        funnel_inc("reprovados_alinhamento")
        return None

    if side == "LONG":
        stop = range_low - (atr * STOP_ATR_BUFFER)
        tp50 = close + TP50_R * abs(close - stop)
    else:
        stop = range_high + (atr * STOP_ATR_BUFFER)
        tp50 = close - TP50_R * abs(stop - close)

    rp = risk_pct(close, stop)
    if rp <= 0 or rp > MAX_RISK_PCT:
        funnel_inc("reprovados_risco")
        return None

    score, breakout_atr, range_atr = calc_falcon_score(row, close, atr, range_size, breakout_size, volume_rel, adx)
    if score < SCORE_MIN_QUALITY_TO_SIGNAL:
        funnel_inc("reprovados_score")
        return None

    current_ts = int(row["ts"])
    ny_date = orb["ny_date"]

    return {
        "id": position_id(symbol, setup_key, side, ny_date),
        "bot": BOT_NAME,
        "setup": setup_key,
        "setup_label": setup_cfg["label"],
        "symbol": symbol,
        "side": side,
        "direction": "BUY" if side == "LONG" else "SELL",
        "entry": close,
        "initial_stop": stop,
        "stop": stop,
        "tp50": tp50,
        "atr": atr,
        "atr_pct": atr_pct,
        "risk_pct": rp,
        "score_falcon": score,
        "quality": quality_from_score(score),
        "volume_rel": volume_rel,
        "adx": adx,
        "breakout_atr": breakout_atr,
        "range_atr": range_atr,
        "range_high": range_high,
        "range_low": range_low,
        "range_minutes": setup_cfg["range_minutes"],
        "range_start_ny": orb["range_start_ny"],
        "range_end_ny": orb["range_end_ny"],
        "ny_date": ny_date,
        "timeframe": TIMEFRAME,
        "signal_ts": current_ts,
        "signal_dt": str(row["dt"]),
        "created_at": data_hora_sp_str(),
        "status": "OPEN",
        "tp50_hit": False,
        "be_moved": False,
        "trailing_active": False,
        "mfe_pct": 0.0,
        "mae_pct": 0.0,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "best_price": close,
        "worst_price": close,
        "management_cycles": 0,
        "candles_to_tp50": None,
        "opened_candle_ts": current_ts,
    }


def signal_message(sig):
    emoji = "🟢" if sig["side"] == "LONG" else "🔴"
    return (
        f"🦅 {emoji} FALCON STRIKE {sig['setup']} {sig['direction']} - {sig['symbol']}\n\n"
        f"Estratégia: ORB NY\n"
        f"Range: {sig['range_start_ny']} → {sig['range_end_ny']} NY ({sig['range_minutes']}m)\n"
        f"Timeframe: {sig['timeframe']}\n\n"
        f"Range High: {fmt_price(sig['range_high'])}\n"
        f"Range Low: {fmt_price(sig['range_low'])}\n\n"
        f"Entrada:\n{fmt_price(sig['entry'])}\n\n"
        f"SL:\n{fmt_price(sig['stop'])}\n\n"
        f"TP50:\n{fmt_price(sig['tp50'])}\n\n"
        f"Risco:\n{sig['risk_pct']:.2f}%\n\n"
        f"Score Falcon:\n{sig.get('score_falcon', 0)}/100\n"
        f"Qualidade:\n{sig.get('quality', 'N/A')}\n\n"
        f"Volume relativo: {safe_float(sig.get('volume_rel'), 1):.2f}x\n"
        f"ADX M15: {safe_float(sig.get('adx'), 0):.2f}\n"
        f"Breakout em ATR: {safe_float(sig.get('breakout_atr'), 0):.2f}\n"
        f"Range em ATR: {safe_float(sig.get('range_atr'), 0):.2f}\n\n"
        f"Modo: {FALCON_MODE} / {'BINGX AUTO' if FALCON_MODE == 'LIVE' else ('VERIFY SEM ENVIO' if FALCON_MODE == 'VERIFY' else 'BINGX BLOQUEADA')}"
    )





def verify_message(sig):
    d = sig.get("execution_decision", {}) or {}
    ready = sig.get("bingx_ready", {}) or {}
    verify = sig.get("verify_order", {}) or {}
    lines = [
        "🧪 VERIFY",
        "",
        f"{sig.get('symbol')} {sig.get('side')}",
        sig.get("setup",""),
        "",
        f"Risk Manager: {'✅ ALLOW' if d.get('allowed') else '❌ DENY'}",
        f"Broker: {'✅ READY' if ready.get('ok') else '❌ NOT READY'}",
    ]
    if verify:
        if verify.get("balance") is not None:
            lines.append(f"Saldo: {verify.get('balance')}")
        if verify.get("qty") is not None:
            lines.append(f"Quantidade: {verify.get('qty')}")
        if verify.get("payload"):
            lines.append("Payload: ✅ OK")
        lines.append("Resultado")
        lines.append("🚫 VERIFY - Ordem NÃO enviada.")
    return "\n".join(lines)

# ==============================================================================
# EXECUÇÃO REAL SEGURA / CENTRAL RISK GATE
# ==============================================================================

def normalize_symbol_for_central(symbol):
    s = str(symbol or "").upper().strip()
    s = s.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT").replace(":USDT", "")
    return s


def falcon_live_positions_count(positions=None):
    positions = positions if positions is not None else get_positions()
    count = 0
    for p in (positions or {}).values():
        if not isinstance(p, dict):
            continue
        if str(p.get("status", "OPEN")).upper() in {"ENCERRADO", "CLOSED", "FECHADO"}:
            continue
        if p.get("execution_mode") == "LIVE" or p.get("live_order_id") or p.get("bingx_order_id"):
            count += 1
    return count


def central_can_open_trade(sig, positions=None):
    if not FALCON_USE_CENTRAL_RISK:
        return {"allowed": True, "decision": "ALLOW", "reasons": [], "warnings": ["FALCON_USE_CENTRAL_RISK=false"]}
    payload = {
        "bot": "FALCON",
        "symbol": normalize_symbol_for_central(sig.get("symbol")),
        "side": sig.get("side"),
        "setup": sig.get("setup"),
        "mode": FALCON_MODE,
        "intended_live": FALCON_MODE == "LIVE",
        "risk_pct": sig.get("risk_pct"),
        # Usa o notional já resolvido no sinal.
        # Não depende de variável local externa a esta função.
        "notional_usdt": safe_float(sig.get("real_notional_usdt"), FALCON_REAL_NOTIONAL_USDT),
        "entry": sig.get("entry"),
        "stop": sig.get("stop"),
        "tp50": sig.get("tp50"),
    }
    try:
        r = requests.post(CENTRAL_CAN_OPEN_TRADE_URL, json=payload, timeout=8)
        if r.status_code != 200:
            return {"allowed": False, "decision": "DENY", "reasons": [f"central HTTP {r.status_code}: {r.text[:160]}"]}
        data = r.json()
        return data if isinstance(data, dict) else {"allowed": False, "decision": "DENY", "reasons": ["central retornou payload inválido"]}
    except Exception as exc:
        return {"allowed": False, "decision": "DENY", "reasons": [f"central indisponível: {exc}"]}



# ==============================================================================
# PATCH 2026-07-11 — FALCON LIVE PARTIAL-CAPABLE SIZING / TP50 REAL V1
# ==============================================================================
FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION = "2026-07-16-FALCON-REAL-POSITION-OWNERSHIP-LIMIT-V1"
FALCON_OWNERSHIP_EVIDENCE_MAX_AGE_SECONDS = 30.0


def falcon_validate_position_ownership_limit_evidence(decision, sig=None, now_epoch=None):
    """Validate Central ownership evidence before the Broker can be reached."""
    decision = decision if isinstance(decision, dict) else {}
    sig = sig if isinstance(sig, dict) else {}
    evidence = decision.get("falcon_real_position_ownership_limit_v1")
    if not isinstance(evidence, dict):
        guard = decision.get("real_pilot_guard_v1") if isinstance(decision.get("real_pilot_guard_v1"), dict) else {}
        evidence = guard.get("falcon_real_position_ownership_limit_v1")
    reasons = []
    if not isinstance(evidence, dict):
        return {"ok": False, "status": "FALCON_OWNERSHIP_EVIDENCE_MISSING", "reasons": ["Falcon ownership evidence is required"], "evidence": None}
    if evidence.get("version") != FALCON_REAL_POSITION_OWNERSHIP_LIMIT_V1_VERSION:
        reasons.append("ownership evidence version mismatch")
    if evidence.get("allowed") is not True:
        reasons.append("ownership evidence did not allow the entry")
    if evidence.get("audit_ok") is not True or evidence.get("registry_mode_ok") is not True:
        reasons.append("Falcon audit or Registry ownership is not confirmed")
    numeric_checks = (
        ("falcon_central_only_pending_count", "Falcon Central-only position is pending"),
        ("falcon_ownership_uncertain_count", "Falcon ownership is uncertain"),
        ("central_bingx_critical_divergence_count", "Central x BingX critical divergence is active"),
        ("manual_same_symbol_side_count", "MANUAL_EXTERNAL_SAME_SYMBOL_SIDE_BLOCK"),
        ("manual_same_symbol_opposite_ambiguous_count", "Manual position mode is ambiguous for the requested symbol"),
    )
    for field, reason in numeric_checks:
        try:
            if int(evidence.get(field) or 0) > 0:
                reasons.append(reason)
        except (TypeError, ValueError):
            reasons.append(f"invalid ownership evidence field: {field}")
    expected_symbol = normalize_symbol_for_central(sig.get("symbol"))
    expected_side = str(sig.get("side") or "").upper().strip()
    expected_side = "LONG" if expected_side in {"BUY", "LONG"} else ("SHORT" if expected_side in {"SELL", "SHORT"} else expected_side)
    if expected_symbol and evidence.get("requested_symbol") != expected_symbol:
        reasons.append("ownership evidence symbol mismatch")
    if expected_side and evidence.get("requested_side") != expected_side:
        reasons.append("ownership evidence side mismatch")
    generated_epoch = evidence.get("generated_epoch")
    try:
        age = float(now_epoch if now_epoch is not None else time.time()) - float(generated_epoch)
        if age < -1.0 or age > FALCON_OWNERSHIP_EVIDENCE_MAX_AGE_SECONDS:
            reasons.append("ownership evidence expired")
    except (TypeError, ValueError):
        reasons.append("ownership evidence timestamp missing")
    return {
        "ok": not reasons,
        "status": "FALCON_OWNERSHIP_EVIDENCE_OK" if not reasons else "FALCON_OWNERSHIP_EVIDENCE_BLOCKED",
        "reasons": reasons,
        "evidence": evidence,
    }


FALCON_LIVE_PARTIAL_CAPABLE_SIZING_VERSION = "2026-07-11-FALCON-LIVE-PARTIAL-CAPABLE-SIZING-V1"
FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION = "2026-07-11-FALCON-TP50-REAL-EXECUTION-AUDIT-V1"
FALCON_REQUIRE_REAL_TP50_CAPABLE = str(os.environ.get("FALCON_REQUIRE_REAL_TP50_CAPABLE", "true")).lower() in {"1", "true", "yes", "sim", "on"}
FALCON_REAL_MAX_NOTIONAL_USDT = float(os.environ.get("FALCON_REAL_MAX_NOTIONAL_USDT", os.environ.get("REAL_TRADING_MAX_NOTIONAL_USDT", "20")))
FALCON_PARTIAL_MIN_PARTS = int(os.environ.get("FALCON_PARTIAL_MIN_PARTS", "2"))


def falcon_resolve_partial_capable_notional(sig):
    """Garante que o próximo LIVE tenha quantidade suficiente para TP50 real."""
    planned = safe_float(sig.get("real_notional_usdt"), FALCON_REAL_NOTIONAL_USDT)
    result = {
        "ok": True,
        "allowed": True,
        "version": FALCON_LIVE_PARTIAL_CAPABLE_SIZING_VERSION,
        "symbol": sig.get("symbol"),
        "planned_notional_usdt": planned,
        "notional_usdt": planned,
        "require_real_tp50_capable": FALCON_REQUIRE_REAL_TP50_CAPABLE,
        "max_notional_usdt": FALCON_REAL_MAX_NOTIONAL_USDT,
        "status": "NOT_CHECKED",
    }
    if central_broker is None or not hasattr(central_broker, "ensure_partial_capable_notional"):
        result.update({"ok": not FALCON_REQUIRE_REAL_TP50_CAPABLE, "allowed": not FALCON_REQUIRE_REAL_TP50_CAPABLE, "status": "BROKER_PARTIAL_HELPER_MISSING", "error": BROKER_IMPORT_ERROR})
        return result
    try:
        audit = central_broker.ensure_partial_capable_notional(
            symbol=sig.get("symbol"),
            planned_notional_usdt=planned,
            max_notional_usdt=FALCON_REAL_MAX_NOTIONAL_USDT,
            min_parts=FALCON_PARTIAL_MIN_PARTS,
        )
        result.update(audit if isinstance(audit, dict) else {})
        result["allowed"] = bool((not FALCON_REQUIRE_REAL_TP50_CAPABLE) or result.get("allowed") or result.get("partial_capable"))
        if result.get("allowed") and result.get("notional_usdt"):
            sig["real_notional_usdt"] = float(result.get("notional_usdt"))
        return result
    except Exception as exc:
        result.update({"ok": False, "allowed": not FALCON_REQUIRE_REAL_TP50_CAPABLE, "status": "PARTIAL_CAPABLE_SIZING_ERROR", "error": str(exc)})
        return result


def falcon_try_execute_tp50_real_partial(pos, price):
    """
    No LIVE, tenta executar TP50 real parcial apenas se a posição comportar minQty.
    Em PAPER/VERIFY/sem ordem real, registra TP50 virtual sem enviar ordem.
    """
    result = {
        "ok": True,
        "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        "status": "TP50_VIRTUAL_ONLY",
        "sent": False,
        "symbol": pos.get("symbol"),
        "side": pos.get("side"),
        "price": price,
        "reason": "not_live_or_no_real_order",
    }
    live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    amount = safe_float(pos.get("qty"), None)
    if amount is None or amount <= 0:
        amount = safe_float(live_order.get("amount"), None)
    has_real_order = bool(pos.get("live_order_id") or pos.get("bingx_order_id") or live_order.get("sent"))

    if FALCON_MODE != "LIVE" or not ENABLE_REAL_TRADING or not has_real_order:
        return result
    if central_broker is None or not hasattr(central_broker, "tp50_partial_amount") or not hasattr(central_broker, "close_position_market"):
        result.update({"ok": False, "status": "TP50_REAL_HELPER_MISSING", "reason": BROKER_IMPORT_ERROR or "broker helper missing"})
        return result

    try:
        partial = central_broker.tp50_partial_amount(pos.get("symbol"), amount)
        result["partial_audit"] = partial
        if not partial.get("ok"):
            result.update({"ok": True, "status": "TP50_VIRTUAL_ONLY_MIN_QTY", "reason": "posição não comporta parcial mínima"})
            return result
        close_amount = partial.get("tp50_amount")
        tp50_reservation = falcon_prepare_position_client_order_id(
            pos, ROLE_TP50_CLOSE, 0, attempt=0
        )
        if tp50_reservation.get("send_allowed") is not True:
            result.update({
                "ok": False,
                "status": "TP50_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
                "sent": False,
                "client_order_id_reservation": tp50_reservation,
                "reconciliation_required": True,
            })
            return result
        client_tag = tp50_reservation.get("client_order_id")
        order = central_broker.close_position_market(
            symbol=pos.get("symbol"),
            side=pos.get("side"),
            amount=close_amount,
            client_tag=client_tag,
            reason="TP50_REAL_PARTIAL",
            client_order_id_reservation=tp50_reservation,
        )
        result.update({
            "ok": bool(order.get("ok")),
            "status": "TP50_REAL_SENT" if order.get("sent") else order.get("status", "TP50_REAL_DRY_RUN"),
            "sent": bool(order.get("sent")),
            "tp50_amount": close_amount,
            "runner_amount": partial.get("runner_amount"),
            "client_tag": client_tag,
            "order": order,
            "reason": "real_partial_attempted",
        })
        return result
    except Exception as exc:
        result.update({"ok": False, "status": "TP50_REAL_ERROR", "error": str(exc), "reason": "exception"})
        return result


def execute_signal_if_allowed(sig, positions=None):
    """
    Decide e, se estiver LIVE, envia ordem real à BingX via broker.py.
    Em PAPER: não consulta execução real e preserva comportamento antigo.
    Em READY: consulta Central/BingX READY, mas não envia ordem.
    Em VERIFY: monta payload/quantidade em DRY_RUN, mas não envia ordem.
    Em LIVE: envia automaticamente se ENABLE_REAL_TRADING=true, Central ALLOW e broker carregado.
    """
    positions = positions if positions is not None else get_positions()
    mode = FALCON_MODE
    sig["execution_mode"] = mode
    sig["real_notional_usdt"] = FALCON_REAL_NOTIONAL_USDT
    partial_sizing = falcon_resolve_partial_capable_notional(sig) if mode in {"READY", "VERIFY", "LIVE"} else {"allowed": True, "notional_usdt": FALCON_REAL_NOTIONAL_USDT}
    sig["partial_capable_sizing"] = partial_sizing
    effective_real_notional = safe_float(partial_sizing.get("notional_usdt"), FALCON_REAL_NOTIONAL_USDT) if isinstance(partial_sizing, dict) else FALCON_REAL_NOTIONAL_USDT
    sig["real_notional_usdt"] = effective_real_notional
    if mode == "LIVE" and FALCON_REQUIRE_REAL_TP50_CAPABLE and not (isinstance(partial_sizing, dict) and partial_sizing.get("allowed")):
        decision = {"allowed": False, "decision": "DENY", "reasons": ["TP50 real obrigatório, mas quantidade/notional não comporta parcial mínima"], "warnings": [str(partial_sizing.get("reason") or partial_sizing.get("status")) if isinstance(partial_sizing, dict) else "partial sizing indisponível"], "partial_capable_sizing": partial_sizing}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    if mode == "PAPER":
        decision = {"allowed": True, "decision": "PAPER", "reasons": [], "warnings": []}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return True, decision

    if falcon_live_positions_count(positions) >= FALCON_REAL_MAX_POSITIONS:
        decision = {
            "allowed": False,
            "decision": "DENY",
            "reasons": [f"limite real Falcon atingido: {falcon_live_positions_count(positions)}/{FALCON_REAL_MAX_POSITIONS}"],
            "warnings": [],
        }
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    decision = central_can_open_trade(sig, positions=positions)
    sig["execution_decision"] = decision
    HEALTH["last_execution_decision"] = decision

    if not decision.get("allowed"):
        return False, decision

    if mode in {"READY", "VERIFY"}:
        ready = None
        if central_broker is not None:
            try:
                ready = central_broker.ready_check()
            except Exception as exc:
                ready = {"ok": False, "status": "READY_ERROR", "error": str(exc)}
        else:
            ready = {"ok": False, "status": "BROKER_IMPORT_ERROR", "error": BROKER_IMPORT_ERROR}
        sig["bingx_ready"] = ready

        verify_order = None
        if mode == "VERIFY" and central_broker is not None:
            try:
                # Em VERIFY o broker fica em dry-run: calcula quantidade/preço e monta payload sem enviar.
                verify_material = json.dumps(
                    {
                        "signal_id": sig.get("signal_id") or sig.get("id"),
                        "signal_ts": sig.get("signal_ts"),
                        "symbol": sig.get("symbol"),
                        "side": sig.get("side"),
                        "setup": sig.get("setup"),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                verify_lifecycle = "CENTRAL-FALCON-VERIFY:" + hashlib.sha256(
                    verify_material.encode("utf-8")
                ).hexdigest().upper()
                verify_client_tag = generate_falcon_client_order_id(
                    bot="FALCON",
                    lifecycle_id=verify_lifecycle,
                    entry_client_order_id="",
                    entry_order_id="",
                    symbol=sig.get("symbol"),
                    side=sig.get("side"),
                    operation=ROLE_ENTRY,
                    revision=0,
                    attempt=0,
                )
                verify_order = central_broker.place_market_order(
                    symbol=sig.get("symbol"),
                    side=sig.get("side"),
                    notional_usdt=effective_real_notional,
                    reduce_only=False,
                    client_tag=verify_client_tag,
                    bot="FALCON",
                    stop_loss_price=sig.get("stop"),
                )
                sig["verify_order"] = verify_order
            except Exception as exc:
                verify_order = {"ok": False, "status": "VERIFY_ERROR", "sent": False, "error": str(exc)}
                sig["verify_order"] = verify_order

        HEALTH["last_execution_order"] = {"mode": mode, "ready": ready, "verify_order": verify_order, "sent": False}
        # READY/VERIFY nunca bloqueiam o paper/sinal; só registram o estado.
        return True, decision

    if mode != "LIVE":
        decision = {"allowed": False, "decision": "DENY", "reasons": [f"FALCON_MODE inválido: {mode}"], "warnings": []}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    if not ENABLE_REAL_TRADING:
        decision = {"allowed": False, "decision": "DENY", "reasons": ["ENABLE_REAL_TRADING=false"], "warnings": []}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    if central_broker is None:
        decision = {"allowed": False, "decision": "DENY", "reasons": [f"broker import error: {BROKER_IMPORT_ERROR}"], "warnings": []}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    ownership_check = falcon_validate_position_ownership_limit_evidence(decision, sig=sig)
    sig["falcon_real_position_ownership_limit_v1"] = ownership_check
    if not ownership_check.get("ok"):
        decision = {
            "allowed": False,
            "decision": "DENY",
            "status": ownership_check.get("status"),
            "reasons": list(ownership_check.get("reasons") or ["Falcon ownership evidence unavailable"]),
            "warnings": [],
            "falcon_real_position_ownership_limit_v1": ownership_check,
        }
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision

    try:
        lifecycle_id = str(sig.get("lifecycle_id") or "").strip()
        if not lifecycle_id:
            lifecycle_evidence = {
                "signal_id": sig.get("signal_id") or sig.get("decision_id") or sig.get("id"),
                "signal_ts": sig.get("signal_ts"),
                "signal_dt": sig.get("signal_dt"),
                "created_at": sig.get("created_at"),
                "setup": sig.get("setup"),
                "symbol": sig.get("symbol"),
                "side": sig.get("side"),
            }
            if not any(
                lifecycle_evidence.get(field) not in (None, "")
                for field in ("signal_id", "signal_ts", "signal_dt", "created_at")
            ):
                decision = {
                    "allowed": False,
                    "decision": "DENY",
                    "status": "FALCON_ENTRY_LIFECYCLE_IDENTITY_REQUIRED",
                    "reasons": ["Identidade imutável do sinal ausente; entrada LIVE bloqueada."],
                    "warnings": [],
                }
                sig["execution_decision"] = decision
                HEALTH["last_execution_decision"] = decision
                return False, decision
            lifecycle_digest = hashlib.sha256(
                json.dumps(
                    lifecycle_evidence,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest().upper()
            lifecycle_id = f"CENTRAL-FALCON-LIFECYCLE:{lifecycle_digest[:32]}"
        sig["lifecycle_id"] = lifecycle_id
        entry_reservation = falcon_prepare_canonical_client_order_id(
            {
                "bot": "FALCON",
                "lifecycle_id": lifecycle_id,
                "entry_client_order_id": "",
                "entry_order_id": "",
                "symbol": sig.get("symbol"),
                "side": sig.get("side"),
                "operation": ROLE_ENTRY,
                "revision": 0,
                "attempt": 0,
            }
        )
        client_tag = str(entry_reservation.get("client_order_id") or "")
        supplied_client_tag = str(sig.get("entry_client_order_id") or "").strip()
        if supplied_client_tag and supplied_client_tag.upper() != client_tag.upper():
            entry_reservation = {
                **dict(entry_reservation),
                "ok": False,
                "send_allowed": False,
                "status": "FALCON_ENTRY_CLIENT_ORDER_ID_NON_CANONICAL",
                "reconciliation_required": True,
            }
        sig["entry_client_order_id"] = client_tag or supplied_client_tag
        sig["entry_client_order_id_reservation"] = dict(entry_reservation)
        if entry_reservation.get("send_allowed") is not True:
            decision = {
                "allowed": False,
                "decision": "DENY",
                "status": entry_reservation.get("status"),
                "reasons": [
                    "Falcon clientOrderID de entrada não obteve reserva "
                    "permanente account-wide; reconciliação factual obrigatória."
                ],
                "warnings": [],
            }
            sig["execution_decision"] = decision
            HEALTH["last_execution_decision"] = decision
            HEALTH["last_execution_order"] = {
                "mode": mode,
                "sent": False,
                "status": entry_reservation.get("status"),
                "client_order_id": client_tag or supplied_client_tag,
            }
            return False, decision
        execution_auth_token = None
        execution_auth_result = None
        if hasattr(central_broker, "issue_execution_auth_token"):
            execution_auth_result = central_broker.issue_execution_auth_token(
                context={
                    "bot": "FALCON",
                    "setup": sig.get("setup"),
                    "symbol": sig.get("symbol"),
                    "side": sig.get("side"),
                    # Usa o notional já resolvido no sinal.
        # Não depende de variável local externa a esta função.
        "notional_usdt": safe_float(sig.get("real_notional_usdt"), FALCON_REAL_NOTIONAL_USDT),
                    "client_tag": client_tag,
                    "stop_loss_price": sig.get("stop"),
                    "source": "falcon_real_pilot_connector_v1",
                }
            )
            if isinstance(execution_auth_result, dict) and execution_auth_result.get("ok"):
                execution_auth_token = execution_auth_result.get("token")
        else:
            execution_auth_result = {"ok": False, "status": "BROKER_AUTH_TOKEN_FUNCTION_MISSING"}

        if not execution_auth_token:
            decision = {
                "allowed": False,
                "decision": "DENY",
                "reasons": [f"Falcon Real Pilot Connector: token efêmero ausente: {execution_auth_result.get('status') if isinstance(execution_auth_result, dict) else execution_auth_result}"],
                "warnings": [],
            }
            sig["execution_decision"] = decision
            HEALTH["last_execution_decision"] = decision
            HEALTH["last_execution_order"] = {"mode": mode, "sent": False, "auth": execution_auth_result}
            return False, decision

        if entry_reservation.get("send_allowed") is not True:
            decision = {
                "allowed": False,
                "decision": "DENY",
                "status": entry_reservation.get("status"),
                "reasons": [
                    "Falcon clientOrderID de entrada não obteve reserva "
                    "persistente exclusiva; reconciliação factual obrigatória."
                ],
                "warnings": [],
            }
            sig["execution_decision"] = decision
            HEALTH["last_execution_decision"] = decision
            HEALTH["last_execution_order"] = {
                "mode": mode,
                "sent": False,
                "status": entry_reservation.get("status"),
                "client_order_id": client_tag,
            }
            return False, decision

        order = central_broker.place_market_order(
            symbol=sig.get("symbol"),
            side=sig.get("side"),
            notional_usdt=effective_real_notional,
            reduce_only=False,
            client_tag=client_tag,
            bot="FALCON",
            execution_auth_token=execution_auth_token,
            stop_loss_price=sig.get("stop"),
            falcon_position_ownership_limit=ownership_check.get("evidence"),
            disaster_stop_client_order_id_factory=(
                lambda **stop_identity: falcon_prepare_initial_disaster_stop_client_order_id(
                    **stop_identity, lifecycle_id=lifecycle_id
                )
            ),
            client_order_id_reservation=entry_reservation,
        )
        sig["live_order"] = order
        sig["live_order_id"] = order.get("id") or order.get("order_id")
        sig["bingx_order_id"] = sig.get("live_order_id")
        HEALTH["last_execution_order"] = order
        unsafe_entry_identity = bool(
            order.get("sent") is True
            and (
                order.get("returned_client_order_id_matches") is False
                or order.get("entry_acknowledged") is not True
            )
        )
        if unsafe_entry_identity:
            incident = falcon_handle_unsafe_live_entry_identity(sig, order)
            order["entry_identity_incident"] = incident
            sig["live_entry_identity_incident"] = incident
            decision = {
                "allowed": False,
                "decision": "DENY",
                "status": "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE",
                "reasons": [
                    "Entrada LIVE foi enviada, mas o clientOrderID retornado "
                    "não confirmou a identidade reservada; fail-safe obrigatório."
                ],
                "warnings": [],
                "reconciliation_required": True,
                "entry_identity_incident": incident,
            }
            sig["execution_decision"] = decision
            HEALTH["last_execution_decision"] = decision
            HEALTH["last_execution_order"] = order
            return False, decision
        if not order.get("ok"):
            decision = {"allowed": False, "decision": "DENY", "reasons": [f"ordem rejeitada: {order.get('error') or order.get('status')}"], "warnings": []}
            sig["execution_decision"] = decision
            HEALTH["last_execution_decision"] = decision
            return False, decision
        return True, decision
    except Exception as exc:
        decision = {"allowed": False, "decision": "DENY", "reasons": [f"erro broker place_order: {exc}"], "warnings": []}
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return False, decision


def execution_decision_text(decision):
    if not isinstance(decision, dict):
        return ""
    d = decision.get("decision") or ("ALLOW" if decision.get("allowed") else "DENY")
    reasons = decision.get("reasons") or []
    warnings = decision.get("warnings") or []
    out = [f"Execução: {d}"]
    if reasons:
        out.append("Motivos: " + "; ".join([str(x) for x in reasons[:3]]))
    if warnings:
        out.append("Avisos: " + "; ".join([str(x) for x in warnings[:3]]))
    return "\n".join(out)


def falcon_persist_accepted_signal(sig, positions):
    """Project one accepted signal to Registry and Falcon memory once.

    An accepted LIVE signal may represent an already-sent Broker order even
    when its response is operationally degraded.  Central persistence must
    therefore consume that fact exactly once and must never turn a repeated
    call into another entry attempt or overwrite a different lifecycle.
    """
    sig = sig if isinstance(sig, dict) else {}
    positions = positions if isinstance(positions, dict) else {}
    pid = str(sig.get("id") or "").strip()
    if not pid:
        return {
            "ok": False,
            "status": "FALCON_ACCEPTED_SIGNAL_ID_REQUIRED",
            "position_recognized": False,
            "registry_write_attempted": False,
            "memory_write_attempted": False,
        }

    existing = positions.get(pid)
    if isinstance(existing, dict):
        identity_fields = (
            "lifecycle_id",
            "live_order_id",
            "live_client_order_id",
        )
        identity_conflict = any(
            existing.get(field) not in (None, "")
            and sig.get(field) not in (None, "")
            and str(existing.get(field)) != str(sig.get(field))
            for field in identity_fields
        )
        if identity_conflict:
            result = {
                "ok": False,
                "status": "FALCON_ACCEPTED_SIGNAL_IDENTITY_COLLISION",
                "position_recognized": True,
                "registry_write_attempted": False,
                "memory_write_attempted": False,
                "reconciliation_required": True,
            }
            HEALTH["last_trade_registry_event"] = dict(result)
            return result
        return {
            "ok": True,
            "status": "FALCON_ACCEPTED_SIGNAL_ALREADY_SYNCHRONIZED",
            "position_recognized": True,
            "registry_write_attempted": False,
            "memory_write_attempted": False,
            "idempotent": True,
        }

    registry_result = register_falcon_trade_registry_open(sig)
    registry_ok = bool(
        isinstance(registry_result, dict) and registry_result.get("ok") is True
    )
    positions[pid] = sig
    memory_result = save_positions(positions)
    memory_ok = memory_result is True
    result = {
        "ok": bool(registry_ok and memory_ok),
        "status": (
            "FALCON_ACCEPTED_SIGNAL_SYNCHRONIZED"
            if registry_ok and memory_ok
            else "FALCON_ACCEPTED_SIGNAL_RECONCILIATION_REQUIRED"
        ),
        "position_recognized": True,
        "registry_write_attempted": True,
        "registry_write_succeeded": registry_ok,
        "memory_write_attempted": True,
        "memory_write_succeeded": memory_ok,
        "reconciliation_required": bool(
            sig.get("reconciliation_required") or not registry_ok or not memory_ok
        ),
    }
    if not result["ok"]:
        # Registry/Redis failures remain fail-open exactly as before.  The
        # ACK-degraded LIVE path already carries its explicit management gate
        # before this helper is called; do not broaden that gate to unrelated
        # trades here.
        HEALTH["last_warning"] = result["status"]
    return result


def scanner_loop():
    started = time.time()

    while True:
        signals_sent = 0
        try:
            if not ENABLE_FALCON:
                HEALTH["last_warning"] = "ENABLE_FALCON=false"
                time.sleep(SCAN_SLEEP_SECONDS)
                continue

            positions = get_positions()
            watchlist = load_watchlist()
            last_candles = get_last_candles_by_symbol()

            for symbol in watchlist:
                if len(positions) >= MAX_OPEN_POSITIONS:
                    break

                df = safe_fetch_ohlcv(symbol)
                closed = closed_candles(df)
                if closed is None or len(closed) == 0:
                    continue

                symbol_last_closed_ts = int(closed.iloc[-1]["ts"])
                if int(last_candles.get(symbol, 0) or 0) == symbol_last_closed_ts:
                    continue

                funnel_inc("ativos_analisados")

                for setup_key, setup_cfg in SETUPS.items():
                    if len(positions) >= MAX_OPEN_POSITIONS:
                        break

                    sig = analyze_symbol_setup(symbol, setup_key, setup_cfg, closed)
                    if not sig:
                        continue

                    if has_open_position_for_symbol(positions, symbol, setup_key, sig["side"]):
                        funnel_inc("reprovados_posicao_ativa")
                        continue

                    if had_trade_today(symbol, sig["ny_date"]):
                        funnel_inc("reprovados_trade_dia")
                        continue

                    if time.time() - started < STARTUP_GUARD_SECONDS:
                        continue

                    execution_allowed, execution_decision = execute_signal_if_allowed(sig, positions=positions)
                    if not execution_allowed:
                        funnel_inc("reprovados_risco")
                        HEALTH["last_warning"] = "execução bloqueada: " + "; ".join([str(x) for x in execution_decision.get("reasons", [])[:3]])
                        record_event(
                            "TRADE_BLOCKED",
                            sig,
                            {
                                "execution_decision": execution_decision,
                                "reasons": execution_decision.get("reasons", []),
                                "warnings": execution_decision.get("warnings", []),
                                "result": "DENY",
                            },
                        )
                        continue

                    falcon_persist_accepted_signal(sig, positions)
                    redis_list_append(SIGNALS_KEY, sig)
                    record_event("SIGNAL", sig, {"entry": sig["entry"], "stop": sig["stop"], "tp50": sig["tp50"], "execution_decision": execution_decision})
                    msg = signal_message(sig)
                    extra_exec = execution_decision_text(execution_decision)
                    if extra_exec:
                        msg += "\n\n" + extra_exec
                    safe_send_telegram(msg, event_type="SIGNAL_LIVE_AUTHORIZED" if sig.get("execution_mode") == "LIVE" else "SIGNAL_PAPER", mode=sig.get("execution_mode"))
                    if FALCON_MODE == "VERIFY":
                        safe_send_telegram(verify_message(sig), event_type="VERIFY_PREVIEW", mode="VERIFY")
                    funnel_inc("sinais_enviados")
                    signals_sent += 1

                last_candles[symbol] = symbol_last_closed_ts

            save_last_candles_by_symbol(last_candles)
            HEALTH["last_signals_sent"] = signals_sent
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            refresh_health_stats()

        except Exception as exc:
            HEALTH["last_error"] = f"scanner: {exc}"
            traceback.print_exc()

        time.sleep(SCAN_SLEEP_SECONDS)

# ==============================================================================
# GESTÃO PAPER
# ============================================================================

def update_mfe_mae(pos, price):
    side = pos["side"]
    entry = safe_float(pos["entry"])
    initial_stop = safe_float(pos.get("initial_stop", pos.get("stop")))
    pnl_pct = pnl_pct_for_side(side, entry, price)
    pnl_r = r_for_side(side, entry, initial_stop, price)
    pos["mfe_pct"] = max(safe_float(pos.get("mfe_pct")), pnl_pct)
    pos["mae_pct"] = min(safe_float(pos.get("mae_pct")), pnl_pct)
    pos["mfe_r"] = max(safe_float(pos.get("mfe_r")), pnl_r)
    pos["mae_r"] = min(safe_float(pos.get("mae_r")), pnl_r)
    if side == "LONG":
        pos["best_price"] = max(safe_float(pos.get("best_price"), entry), price)
        pos["worst_price"] = min(safe_float(pos.get("worst_price"), entry), price)
    else:
        pos["best_price"] = min(safe_float(pos.get("best_price"), entry), price)
        pos["worst_price"] = max(safe_float(pos.get("worst_price"), entry), price)
    return pos


def calc_chandelier_stop(pos):
    symbol = pos["symbol"]
    side = pos["side"]
    df = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=80)
    closed = closed_candles(df)
    if closed is None or len(closed) < 30:
        return None
    dfi = add_indicators(closed)
    row = dfi.iloc[-1]
    atr = safe_float(row["atr"])
    recent = dfi.tail(22)
    if atr <= 0:
        return None
    if side == "LONG":
        return safe_float(recent["high"].max()) - atr * TRAIL_ATR_MULT
    return safe_float(recent["low"].min()) + atr * TRAIL_ATR_MULT


def close_position(pid, pos, exit_price, reason):
    entry = safe_float(pos["entry"])
    initial_stop = safe_float(pos.get("initial_stop", pos["stop"]))
    side = pos["side"]
    result_pct = pnl_pct_for_side(side, entry, exit_price)
    result_r = r_for_side(side, entry, initial_stop, exit_price)
    giveback_pct = safe_float(pos.get("mfe_pct")) - result_pct
    giveback_r = safe_float(pos.get("mfe_r")) - result_r

    trade = dict(pos)
    trade.update({
        "status": "CLOSED",
        "exit_price": exit_price,
        "exit_reason": reason,
        "closed_at": data_hora_sp_str(),
        "result_pct": result_pct,
        "result_r": result_r,
        "giveback_pct": giveback_pct,
        "giveback_r": giveback_r,
    })

    close_falcon_trade_registry(
        trade,
        exit_price=exit_price,
        result_pct=result_pct,
        result_r=result_r,
        reason=reason,
    )

    redis_list_append(TRADES_KEY, trade)
    record_event(reason, trade, {"exit_price": exit_price, "result_pct": result_pct, "result_r": result_r})

    emoji = "✅" if result_pct > 0.05 else ("❌" if result_pct < -0.05 else "🟡")
    safe_send_telegram(
        f"🦅 SAÍDA FALCON - {pos['symbol']}\n\n"
        f"Setup: {pos.get('setup')}\n"
        f"Direção: {side}\n"
        f"Entrada: {fmt_price(entry)}\n"
        f"Saída: {fmt_price(exit_price)}\n"
        f"Motivo: {reason}\n\n"
        f"Resultado: {fmt_pct(result_pct)} | {fmt_r(result_r)}\n"
        f"MFE: {fmt_pct(pos.get('mfe_pct', 0))} | {fmt_r(pos.get('mfe_r', 0))}\n"
        f"MAE: {fmt_pct(pos.get('mae_pct', 0))} | {fmt_r(pos.get('mae_r', 0))}\n"
        f"Devolução: {fmt_pct(giveback_pct)} | {fmt_r(giveback_r)}\n\n"
        f"{emoji}",
        event_type="LIVE_TRADE_CLOSED" if str(pos.get("execution_mode") or "").upper() == "LIVE" else "PAPER_TRADE_CLOSED",
        mode=pos.get("execution_mode") or "PAPER",
    )
    return trade


def management_loop():
    while True:
        try:
            positions = get_positions()
            changed = False
            closed_pids = []

            for pid, pos in list(positions.items()):
                symbol = pos["symbol"]
                side = pos["side"]
                entry = safe_float(pos["entry"])
                stop = safe_float(pos["stop"])
                tp50 = safe_float(pos["tp50"])
                initial_stop = safe_float(pos.get("initial_stop", stop))
                risk_abs = abs(entry - initial_stop)

                price = safe_fetch_price(symbol)
                if price is None:
                    continue

                pos = update_mfe_mae(pos, price)

                stopped = (side == "LONG" and price <= stop) or (side == "SHORT" and price >= stop)
                if stopped:
                    close_position(pid, pos, stop, "STOP")
                    closed_pids.append(pid)
                    changed = True
                    continue

                if not pos.get("tp50_hit"):
                    tp_hit = (side == "LONG" and price >= tp50) or (side == "SHORT" and price <= tp50)
                    if tp_hit:
                        pos["tp50_hit"] = True
                        pos["candles_to_tp50"] = int(pos.get("management_cycles", 0))
                        tp50_real_execution = falcon_try_execute_tp50_real_partial(pos, price)
                        pos["tp50_real_execution"] = tp50_real_execution
                        pos["tp50_real_executed"] = bool(isinstance(tp50_real_execution, dict) and tp50_real_execution.get("sent"))
                        pos["tp50_virtual_only"] = not pos.get("tp50_real_executed")
                        record_event("TP50", pos, {"price": price, "candles_to_tp50": pos["candles_to_tp50"], "tp50_real_execution": tp50_real_execution})
                        tp50_status = (tp50_real_execution or {}).get("status") if isinstance(tp50_real_execution, dict) else "TP50_VIRTUAL_ONLY"
                        safe_send_telegram(
                            f"🎯 TP50 FALCON - {symbol}\n\n"
                            f"Setup: {pos.get('setup')}\n"
                            f"Direção: {side}\n"
                            f"Preço atual: {fmt_price(price)}\n"
                            f"Resultado: {fmt_pct(pnl_pct_for_side(side, entry, tp50))} | +1,00R\n\n"
                            f"TP50 real BingX: {tp50_status}\n"
                            f"Status: aguardando BE em {BE_TRIGGER_R}R"
                        )
                        changed = True

                current_r = r_for_side(side, entry, initial_stop, price)

                if pos.get("tp50_hit") and not pos.get("be_moved") and current_r >= BE_TRIGGER_R:
                    if side == "LONG":
                        new_stop = entry * (1 + BE_OFFSET_PCT / 100)
                        pos["stop"] = max(safe_float(pos["stop"]), new_stop)
                    else:
                        new_stop = entry * (1 - BE_OFFSET_PCT / 100)
                        pos["stop"] = min(safe_float(pos["stop"]), new_stop)
                    pos["be_moved"] = True
                    record_event("BE", pos, {"new_stop": pos["stop"], "trigger_r": current_r})
                    safe_send_telegram(
                        f"🟡 BE FALCON - {symbol}\n\n"
                        f"Setup: {pos.get('setup')}\n"
                        f"Stop movido para: {fmt_price(pos['stop'])}\n"
                        f"R atual: {fmt_r(current_r)}"
                    )
                    changed = True

                if pos.get("be_moved") and current_r >= TRAIL_TRIGGER_R:
                    trail = calc_chandelier_stop(pos)
                    if trail is not None:
                        old_stop = safe_float(pos["stop"])
                        if side == "LONG" and trail > old_stop:
                            pos["stop"] = trail
                            pos["trailing_active"] = True
                            record_event("TRAILING", pos, {"new_stop": trail})
                            safe_send_telegram(f"🟣 TRAILING FALCON - {symbol}\n\nNovo stop: {fmt_price(trail)}\nR atual: {fmt_r(current_r)}")
                            changed = True
                        elif side == "SHORT" and trail < old_stop:
                            pos["stop"] = trail
                            pos["trailing_active"] = True
                            record_event("TRAILING", pos, {"new_stop": trail})
                            safe_send_telegram(f"🟣 TRAILING FALCON - {symbol}\n\nNovo stop: {fmt_price(trail)}\nR atual: {fmt_r(current_r)}")
                            changed = True

                pos["management_cycles"] = int(pos.get("management_cycles", 0)) + 1
                positions[pid] = pos

            for pid in closed_pids:
                positions.pop(pid, None)

            falcon_refresh_management_safety_health(positions)
            save_positions(positions)
            HEALTH["last_management_run"] = data_hora_sp_str()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            refresh_health_stats()

        except Exception as exc:
            HEALTH["last_error"] = f"management: {exc}"
            traceback.print_exc()

        time.sleep(MANAGEMENT_SLEEP_SECONDS)

# ==============================================================================
# STATS / SUMMARY
# ============================================================================

def avg(values):
    vals = [safe_float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def profit_factor(values):
    vals = [safe_float(v) for v in values]
    gross_profit = sum(x for x in vals if x > 0)
    gross_loss = abs(sum(x for x in vals if x < 0))
    return gross_profit / gross_loss if gross_loss > 0 else gross_profit


def calc_stats(trades):
    trades = trades or []
    if not trades:
        return {"count": 0, "wins": 0, "losses": 0, "be": 0, "winrate": 0.0, "pnl_pct": 0.0, "pnl_r": 0.0, "mfe_avg_pct": 0.0, "mae_avg_pct": 0.0, "mfe_avg_r": 0.0, "mae_avg_r": 0.0, "giveback_avg_pct": 0.0, "giveback_avg_r": 0.0, "expectancy_r": 0.0, "profit_factor_pct": 0.0, "profit_factor_r": 0.0, "tp50_hits": 0, "best_trade": None, "worst_trade": None, "top_mfe": [], "runners_3r": 0, "runners_5r": 0, "runners_10r": 0}
    results_pct = [safe_float(t.get("result_pct")) for t in trades]
    results_r = [safe_float(t.get("result_r")) for t in trades]
    wins = [x for x in results_pct if x > 0.05]
    losses = [x for x in results_pct if x < -0.05]
    top = sorted([{"symbol": t.get("symbol"), "setup": t.get("setup"), "side": t.get("side"), "mfe_pct": safe_float(t.get("mfe_pct")), "mfe_r": safe_float(t.get("mfe_r")), "closed_at": t.get("closed_at")} for t in trades], key=lambda x: x["mfe_r"], reverse=True)[:5]
    return {
        "count": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "be": sum(1 for x in results_pct if -0.05 <= x <= 0.05),
        "winrate": len(wins) / len(trades) * 100.0 if trades else 0.0,
        "pnl_pct": sum(results_pct),
        "pnl_r": sum(results_r),
        "mfe_avg_pct": avg([t.get("mfe_pct") for t in trades]),
        "mae_avg_pct": avg([t.get("mae_pct") for t in trades]),
        "mfe_avg_r": avg([t.get("mfe_r") for t in trades]),
        "mae_avg_r": avg([t.get("mae_r") for t in trades]),
        "giveback_avg_pct": avg([t.get("giveback_pct") for t in trades]),
        "giveback_avg_r": avg([t.get("giveback_r") for t in trades]),
        "expectancy_r": avg(results_r),
        "profit_factor_pct": profit_factor(results_pct),
        "profit_factor_r": profit_factor(results_r),
        "tp50_hits": sum(1 for t in trades if t.get("tp50_hit")),
        "best_trade": max(trades, key=lambda t: safe_float(t.get("result_r"))) if trades else None,
        "worst_trade": min(trades, key=lambda t: safe_float(t.get("result_r"))) if trades else None,
        "top_mfe": top,
        "runners_3r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 3.0),
        "runners_5r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 5.0),
        "runners_10r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 10.0),
    }


def trades_today():
    br_date = date_key_br()
    return [t for t in get_trades() if str(t.get("closed_at", "")).startswith(br_date)]


def trades_month():
    br_month = month_key_br()
    return [t for t in get_trades() if br_month in str(t.get("closed_at", ""))]


def signals_today():
    br_date = date_key_br()
    return [s for s in get_signals() if str(s.get("created_at", "")).startswith(br_date)]


def signals_month():
    br_month = month_key_br()
    return [s for s in get_signals() if br_month in str(s.get("created_at", ""))]


def refresh_health_stats():
    # Limpa warning antigo do getUpdates quando os comandos estão centralizados na Central.
    if "getUpdates 409" in str(HEALTH.get("last_warning") or ""):
        HEALTH["last_warning"] = None
    month_trades = trades_month()
    month_signals = signals_month()
    today_trades = trades_today()
    today_signals = signals_today()
    today_events = [e for e in get_events() if str(e.get("created_at", "")).startswith(date_key_br())]
    stats = calc_stats(month_trades)

    HEALTH["funnel_today"] = funnel_snapshot()
    HEALTH["signals_today"] = len(today_signals)
    HEALTH["signals_month"] = len(month_signals)
    HEALTH["trades_closed_today"] = len(today_trades)
    HEALTH["trades_closed_month"] = len(month_trades)
    HEALTH["signals_falcon15_today"] = sum(1 for s in today_signals if s.get("setup") == "FALCON15")
    HEALTH["signals_falcon30_today"] = sum(1 for s in today_signals if s.get("setup") == "FALCON30")
    HEALTH["signals_buy_today"] = sum(1 for s in today_signals if s.get("side") == "LONG")
    HEALTH["signals_sell_today"] = sum(1 for s in today_signals if s.get("side") == "SHORT")
    HEALTH["tp50_today"] = sum(1 for e in today_events if e.get("event_type") == "TP50")
    HEALTH["be_today"] = sum(1 for e in today_events if e.get("event_type") == "BE")
    HEALTH["trailing_today"] = sum(1 for e in today_events if e.get("event_type") == "TRAILING")
    HEALTH["stops_today"] = sum(1 for e in today_events if e.get("event_type") == "STOP")
    HEALTH["mfe_avg_pct"] = round(stats["mfe_avg_pct"], 4)
    HEALTH["mae_avg_pct"] = round(stats["mae_avg_pct"], 4)
    HEALTH["mfe_avg_r"] = round(stats["mfe_avg_r"], 4)
    HEALTH["mae_avg_r"] = round(stats["mae_avg_r"], 4)
    HEALTH["giveback_avg_pct"] = round(stats["giveback_avg_pct"], 4)
    HEALTH["giveback_avg_r"] = round(stats["giveback_avg_r"], 4)
    HEALTH["expectancy_r"] = round(stats["expectancy_r"], 4)
    HEALTH["profit_factor_pct"] = round(stats["profit_factor_pct"], 4)
    HEALTH["profit_factor_r"] = round(stats["profit_factor_r"], 4)
    HEALTH["top_mfe_month"] = stats["top_mfe"]
    HEALTH["runners_3r"] = stats["runners_3r"]
    HEALTH["runners_5r"] = stats["runners_5r"]
    HEALTH["runners_10r"] = stats["runners_10r"]
    HEALTH["last_summary_run"] = data_hora_sp_str()


def trade_line(trade):
    if not trade:
        return "N/A"
    return f"{trade.get('symbol')} {trade.get('setup')} {fmt_pct(trade.get('result_pct'))} | {fmt_r(trade.get('result_r'))}"


def build_summary(period_name, trades, period_signals_override=None):
    refresh_health_stats()
    stats = calc_stats(trades)
    positions = get_positions()
    period_signals = period_signals_override if period_signals_override is not None else (signals_today() if period_name == "DIA" else signals_month())
    f = HEALTH.get("funnel_today", {})
    return (
        f"🦅 RESUMO FALCON STRIKE - {period_name}\n"
        f"{agora_sp().strftime('%d/%m/%Y')}\n\n"
        f"Sinais Falcon: {len(period_signals)}\n"
        f"Falcon15: {sum(1 for s in period_signals if s.get('setup') == 'FALCON15')}\n"
        f"Falcon30: {sum(1 for s in period_signals if s.get('setup') == 'FALCON30')}\n"
        f"LONG: {sum(1 for s in period_signals if s.get('side') == 'LONG')}\n"
        f"SHORT: {sum(1 for s in period_signals if s.get('side') == 'SHORT')}\n\n"
        f"🦅 FUNIL FALCON\n"
        f"Ativos analisados: {f.get('ativos_analisados', 0)}\n"
        f"Fora da janela NY: {f.get('fora_janela_ny', 0)}\n"
        f"Range não formado: {f.get('range_nao_formado', 0)}\n"
        f"Rompimentos 15 BUY: {f.get('rompimentos_15_buy', 0)}\n"
        f"Rompimentos 15 SELL: {f.get('rompimentos_15_sell', 0)}\n"
        f"Rompimentos 30 BUY: {f.get('rompimentos_30_buy', 0)}\n"
        f"Rompimentos 30 SELL: {f.get('rompimentos_30_sell', 0)}\n"
        f"Reprovados ATR: {f.get('reprovados_atr', 0)}\n"
        f"Reprovados Range: {f.get('reprovados_range', 0)}\n"
        f"Reprovados Volume: {f.get('reprovados_volume', 0)}\n"
        f"Reprovados ADX: {f.get('reprovados_adx', 0)}\n"
        f"Reprovados Risco: {f.get('reprovados_risco', 0)}\n"
        f"Reprovados Score: {f.get('reprovados_score', 0)}\n"
        f"Reprovados Alinhamento: {f.get('reprovados_alinhamento', 0)}\n"
        f"Reprovados posição ativa: {f.get('reprovados_posicao_ativa', 0)}\n"
        f"Reprovados trade no dia: {f.get('reprovados_trade_dia', 0)}\n"
        f"Sinais enviados: {f.get('sinais_enviados', 0)}\n\n"
        f"Trades encerrados: {stats['count']}\n"
        f"Wins: {stats['wins']}\n"
        f"Breakeven: {stats['be']}\n"
        f"Loss: {stats['losses']}\n"
        f"Win rate: {stats['winrate']:.2f}%\n"
        f"Profit Factor %: {stats['profit_factor_pct']:.2f}\n"
        f"Profit Factor R: {stats['profit_factor_r']:.2f}\n"
        f"Expectancy: {fmt_r(stats['expectancy_r'])}\n\n"
        f"TP50 hoje: {HEALTH.get('tp50_today', 0)}\n"
        f"BE hoje: {HEALTH.get('be_today', 0)}\n"
        f"Trailing hoje: {HEALTH.get('trailing_today', 0)}\n"
        f"Stops hoje: {HEALTH.get('stops_today', 0)}\n\n"
        f"PnL realizado:\n{fmt_pct(stats['pnl_pct'])} | {fmt_r(stats['pnl_r'])}\n\n"
        f"MFE médio:\n{fmt_pct(stats['mfe_avg_pct'])} | {fmt_r(stats['mfe_avg_r'])}\n"
        f"MAE médio:\n{fmt_pct(stats['mae_avg_pct'])} | {fmt_r(stats['mae_avg_r'])}\n"
        f"Devolução média:\n{fmt_pct(stats['giveback_avg_pct'])} | {fmt_r(stats['giveback_avg_r'])}\n\n"
        f"Runners:\n3R+: {stats['runners_3r']}\n5R+: {stats['runners_5r']}\n10R+: {stats['runners_10r']}\n\n"
        f"Melhor trade:\n{trade_line(stats['best_trade'])}\n\n"
        f"Pior trade:\n{trade_line(stats['worst_trade'])}\n\n"
        f"Trades ainda ativos: {len(positions)}\n"
        f"Modo: {FALCON_MODE} / {'BINGX AUTO' if FALCON_MODE == 'LIVE' else ('VERIFY SEM ENVIO' if FALCON_MODE == 'VERIFY' else 'BINGX BLOQUEADA')}"
    )


def maybe_send_daily_summary():
    if not CENTRAL_AUTO_DAILY_SUMMARIES_ENABLED:
        return
    now = agora_sp()
    if now.hour != DAILY_SUMMARY_HOUR or now.minute < DAILY_SUMMARY_MINUTE:
        return
    key = f"{DAILY_SUMMARY_KEY}:{date_key()}"
    if redis_get_json(key, False):
        return
    safe_send_telegram(build_summary("DIA", trades_today()), event_type="AUTOMATIC_DAILY_SUMMARY", mode="PAPER")
    redis_set_json(key, True)


def maybe_send_monthly_summary():
    now = agora_sp()
    if now.day != MONTHLY_SUMMARY_DAY or now.hour != MONTHLY_SUMMARY_HOUR or now.minute < MONTHLY_SUMMARY_MINUTE:
        return
    previous_month = now.replace(day=1) - timedelta(days=1)
    previous_label = previous_month.strftime("%m/%Y")
    key = f"{MONTHLY_SUMMARY_KEY}:{previous_label}"
    if redis_get_json(key, False):
        return
    trades = [t for t in get_trades() if previous_label in str(t.get("closed_at", ""))]
    period_signals = [s for s in get_signals() if previous_label in str(s.get("created_at", ""))]
    safe_send_telegram(build_summary(f"MÊS {previous_label}", trades, period_signals_override=period_signals), event_type="AUTOMATIC_MONTHLY_SUMMARY", mode="PAPER")
    redis_set_json(key, True)


def summary_loop():
    while True:
        try:
            maybe_send_daily_summary()
            maybe_send_monthly_summary()
            refresh_health_stats()
        except Exception as exc:
            HEALTH["last_warning"] = f"summary: {exc}"
        time.sleep(30)

# ==============================================================================
# WATCHDOG / COMMANDS
# ============================================================================

def watchdog_loop():
    while True:
        try:
            HEALTH["watchdog_last_check"] = data_hora_sp_str()
            reasons = []
            ms = minutes_since(HEALTH.get("last_scanner_run"))
            mm = minutes_since(HEALTH.get("last_management_run"))
            if ms is not None and ms > WATCHDOG_THRESHOLD_MINUTES:
                reasons.append(f"scanner parado há {ms} min")
            if mm is not None and mm > WATCHDOG_THRESHOLD_MINUTES:
                reasons.append(f"gestão parada há {mm} min")
            if HEALTH.get("last_error"):
                reasons.append(f"last_error={HEALTH.get('last_error')}")
            if reasons:
                HEALTH["watchdog_last_status"] = "ALERTA"
                last = float(HEALTH.get("last_watchdog_alert_ts", 0) or 0)
                if time.time() - last >= WATCHDOG_ALERT_COOLDOWN_SECONDS:
                    safe_send_telegram("🚨 WATCHDOG FALCON STRIKE\n\n" + "\n".join([f"- {r}" for r in reasons]), event_type="WATCHDOG_STALLED", operational_critical=True)
                    HEALTH["last_watchdog_alert"] = data_hora_sp_str()
                    HEALTH["last_watchdog_alert_ts"] = time.time()
            else:
                HEALTH["watchdog_last_status"] = "OK"
        except Exception as exc:
            HEALTH["last_warning"] = f"watchdog: {exc}"
        time.sleep(WATCHDOG_SLEEP_SECONDS)


def positions_text():
    positions = get_positions()
    if not positions:
        return "🦅 Falcon: nenhuma posição paper aberta."
    lines = ["🦅 POSIÇÕES FALCON PAPER\n"]
    for p in positions.values():
        price = safe_fetch_price(p["symbol"])
        current = ""
        if price:
            pnl = pnl_pct_for_side(p["side"], p["entry"], price)
            rr = r_for_side(p["side"], p["entry"], p.get("initial_stop", p["stop"]), price)
            current = f"Atual: {fmt_price(price)} | {fmt_pct(pnl)} | {fmt_r(rr)}\n"
        lines.append(
            f"{p.get('setup_label', p.get('setup'))} - {p['symbol']} {p['side']}\n"
            f"Range NY: {p.get('range_start_ny')} → {p.get('range_end_ny')}\n"
            f"Entrada: {fmt_price(p['entry'])}\n"
            f"SL: {fmt_price(p['stop'])}\n"
            f"TP50: {fmt_price(p['tp50'])}\n"
            f"{current}"
            f"MFE: {fmt_pct(p.get('mfe_pct', 0))} | {fmt_r(p.get('mfe_r', 0))}\n"
            f"MAE: {fmt_pct(p.get('mae_pct', 0))} | {fmt_r(p.get('mae_r', 0))}\n"
        )
    text = "\n".join(lines)
    return text[:3900]


def funnel_text():
    f = get_funnel()
    return (
        "🦅 FUNIL FALCON DO DIA\n\n"
        f"Ativos analisados: {f.get('ativos_analisados', 0)}\n"
        f"Fora da janela NY: {f.get('fora_janela_ny', 0)}\n"
        f"Range não formado: {f.get('range_nao_formado', 0)}\n\n"
        f"Rompimentos 15 BUY: {f.get('rompimentos_15_buy', 0)}\n"
        f"Rompimentos 15 SELL: {f.get('rompimentos_15_sell', 0)}\n"
        f"Rompimentos 30 BUY: {f.get('rompimentos_30_buy', 0)}\n"
        f"Rompimentos 30 SELL: {f.get('rompimentos_30_sell', 0)}\n\n"
        f"Reprovados ATR: {f.get('reprovados_atr', 0)}\n"
        f"Reprovados Range: {f.get('reprovados_range', 0)}\n"
        f"Reprovados Volume: {f.get('reprovados_volume', 0)}\n"
        f"Reprovados ADX: {f.get('reprovados_adx', 0)}\n"
        f"Reprovados Risco: {f.get('reprovados_risco', 0)}\n"
        f"Reprovados Score: {f.get('reprovados_score', 0)}\n"
        f"Reprovados Alinhamento: {f.get('reprovados_alinhamento', 0)}\n"
        f"Reprovados posição ativa: {f.get('reprovados_posicao_ativa', 0)}\n"
        f"Reprovados trade no dia: {f.get('reprovados_trade_dia', 0)}\n\n"
        f"Sinais enviados: {f.get('sinais_enviados', 0)}"
    )


def events_text(limit=20):
    events = get_events()[-limit:]
    if not events:
        return "🦅 Nenhum evento Falcon registrado ainda."
    lines = ["🦅 EVENTOS FALCON\n"]
    for e in reversed(events):
        lines.append(
            f"{e.get('created_at')} | {e.get('event_type')} | {e.get('symbol')} {e.get('side')} {e.get('setup')}\n"
            f"MFE {fmt_pct(e.get('mfe_pct', 0))} | {fmt_r(e.get('mfe_r', 0))}"
        )
    return "\n\n".join(lines)[:3900]


def health_payload():
    refresh_health_stats()
    if "getUpdates 409" in str(HEALTH.get("last_warning") or ""):
        HEALTH["last_warning"] = None
    return {
        "ok": HEALTH.get("last_error") is None,
        "bot": BOT_NAME,
        "mode": FALCON_MODE,
        "enabled": ENABLE_FALCON,
        "enabled_setups": list(SETUPS.keys()),
        "timeframe": TIMEFRAME,
        "orb_start_ny": f"{ORB_START_HOUR:02d}:{ORB_START_MINUTE:02d}",
        "trade_end_ny": f"{ORB_TRADE_END_HOUR:02d}:{ORB_TRADE_END_MINUTE:02d}",
        "alignment_mode": ALIGNMENT_MODE,
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "watchdog_status": HEALTH.get("watchdog_last_status"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "positions_open": len(get_positions()),
        "positions_limit": MAX_OPEN_POSITIONS,
        "watchlist_file": WATCHLIST_FILE,
        "watchlist_total": HEALTH.get("watchlist_total"),
        "watchlist_valid": HEALTH.get("watchlist_valid"),
        "watchlist_invalid": HEALTH.get("watchlist_invalid"),
        "signals_today": HEALTH.get("signals_today"),
        "trades_closed_today": HEALTH.get("trades_closed_today"),
        "tp50_today": HEALTH.get("tp50_today"),
        "be_today": HEALTH.get("be_today"),
        "trailing_today": HEALTH.get("trailing_today"),
        "stops_today": HEALTH.get("stops_today"),
        "funnel_today": HEALTH.get("funnel_today"),
    }


def telegram_get_updates(offset=None):
    if not TOKEN:
        return []
    try:
        params = {"timeout": 20}
        if offset:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        r = requests.get(url, params=params, timeout=25)
        if r.status_code != 200:
            HEALTH["last_warning"] = f"getUpdates {r.status_code}: {r.text[:160]}"
            return []
        return r.json().get("result", [])
    except Exception as exc:
        HEALTH["last_warning"] = f"getUpdates: {exc}"
        return []


def telegram_reply(chat_id, text):
    if not TOKEN:
        print(text)
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=15)
        return True
    except Exception:
        return False


def commands_loop():
    offset = None
    while True:
        try:
            updates = telegram_get_updates(offset)
            for upd in updates:
                offset = upd.get("update_id", 0) + 1
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat_id = (msg.get("chat") or {}).get("id")
                if not text or not chat_id:
                    continue
                cmd = text.split()[0].lower().split("@")[0]
                if cmd == "/health":
                    telegram_reply(chat_id, json.dumps(health_payload(), ensure_ascii=False, indent=2))
                elif cmd == "/posicoes":
                    telegram_reply(chat_id, positions_text())
                elif cmd == "/resumo":
                    telegram_reply(chat_id, build_summary("DIA", trades_today()))
                elif cmd == "/funil":
                    telegram_reply(chat_id, funnel_text())
                elif cmd == "/eventos":
                    telegram_reply(chat_id, events_text())
                elif cmd == "/watchlist":
                    wl = load_watchlist()
                    telegram_reply(chat_id, "🦅 WATCHLIST FALCON\n\n" + "\n".join(wl[:100]))
                elif cmd == "/reset":
                    redis_set_json(FUNNEL_KEY, {})
                    redis_set_json(LAST_CANDLES_KEY, {})
                    telegram_reply(chat_id, "✅ Reset operacional Falcon realizado. Posições e trades NÃO foram apagados.")
                elif cmd == "/reset_falcon_all":
                    redis_set_json(POSITIONS_KEY, {})
                    redis_set_json(SIGNALS_KEY, [])
                    redis_set_json(TRADES_KEY, [])
                    redis_set_json(EVENTS_KEY, [])
                    redis_set_json(FUNNEL_KEY, {})
                    redis_set_json(LAST_CANDLES_KEY, {})
                    telegram_reply(chat_id, "✅ Falcon zerado: posições, sinais, trades, eventos e funil apagados.")
                elif cmd == "/comandos":
                    telegram_reply(chat_id, "🦅 Comandos Falcon:\n/health\n/posicoes\n/resumo\n/funil\n/eventos\n/watchlist\n/reset")
            HEALTH["last_command_run"] = data_hora_sp_str()
        except Exception as exc:
            HEALTH["last_warning"] = f"commands: {exc}"
        time.sleep(COMMAND_SLEEP_SECONDS)

# ==============================================================================
# FLASK
# ============================================================================

@app.route("/")
def home():
    return "Falcon Strike ORB PRO Online"


@app.route("/health")
def health():
    return health_payload()


@app.route("/positions")
def positions_route():
    return get_positions()


@app.route("/summary")
def summary_route():
    return {"text": build_summary("DIA", trades_today())}


@app.route("/funnel")
def funnel_route():
    return get_funnel()


@app.route("/events")
def events_route():
    return {"events": get_events()[-50:]}

# ==============================================================================
# STARTUP
# ============================================================================

def run_thread_guarded(name, target):
    while True:
        try:
            target()
        except Exception as exc:
            HEALTH["last_error"] = f"Thread {name} travou: {exc}"
            traceback.print_exc()
            try:
                safe_send_telegram(f"🔴 THREAD FALCON TRAVOU: {name}\n\nErro:\n{exc}\n\nA thread será reiniciada.", event_type="RUNTIME_CRITICAL", operational_critical=True)
            except Exception:
                pass
            time.sleep(10)


def start_threads():
    HEALTH["started_at"] = data_hora_sp_str()
    safe_send_telegram(
        "🦅 Falcon Strike iniciado\n\n"
        f"Setups: {', '.join(SETUPS.keys())}\n"
        f"Timeframe: {TIMEFRAME}\n"
        f"ORB NY: {ORB_START_HOUR:02d}:{ORB_START_MINUTE:02d}\n"
        f"Opera até: {ORB_TRADE_END_HOUR:02d}:{ORB_TRADE_END_MINUTE:02d} NY\n"
        f"Alinhamento: {ALIGNMENT_MODE}\n"
        f"Modo: {FALCON_MODE} / {'BINGX AUTO' if FALCON_MODE == 'LIVE' else ('VERIFY SEM ENVIO' if FALCON_MODE == 'VERIFY' else 'BINGX BLOQUEADA')}",
        event_type="FALCON_STARTUP",
        mode=FALCON_MODE,
        operational_critical=False,
        manual_command=False,
    )
    threading.Thread(target=run_thread_guarded, args=("scanner", scanner_loop), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("management", management_loop), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("summary", summary_loop), daemon=True).start()
    # Comandos do Falcon ficam centralizados no roteador da Central Quant.
    # NÃO iniciar commands_loop aqui para evitar conflito 409 getUpdates.
    # threading.Thread(target=run_thread_guarded, args=("commands", commands_loop), daemon=True).start()

    threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog_loop), daemon=True).start()


# ==============================================================================
# PATCH 2026-07-11 — REAL POSITION MANAGEMENT HARDENING V1
# ==============================================================================
# Objetivos:
# - TP50 LIVE só é confirmado após redução real e proteção do runner.
# - Stop do runner é redimensionado após parcial para impedir reversão em Hedge Mode.
# - BE/trailing só alteram o stop local depois de confirmação da troca na BingX.
# - Cruzamento do stop LIVE nunca fecha apenas o Redis; confirma posição/ordem no broker.
# - Divergência de quantidade bloqueia a ação, preservando independência entre robôs.

FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION = "2026-07-11-FALCON-REAL-POSITION-MANAGEMENT-HARDENING-V1"
FALCON_MANAGEMENT_FAILSAFE_ENABLED = str(os.environ.get("FALCON_MANAGEMENT_FAILSAFE_ENABLED", "true")).lower() in {"1", "true", "yes", "sim", "on"}
FALCON_MANAGEMENT_STOP_GRACE_SECONDS = int(os.environ.get("FALCON_MANAGEMENT_STOP_GRACE_SECONDS", "15"))
FALCON_TP50_RETRY_SECONDS = int(os.environ.get("FALCON_TP50_RETRY_SECONDS", "20"))
FALCON_MANAGEMENT_AMOUNT_TOLERANCE = float(os.environ.get("FALCON_MANAGEMENT_AMOUNT_TOLERANCE", "0.0000000001"))
FALCON_STOP_VERIFY_INTERVAL_SECONDS = max(5, int(os.environ.get("FALCON_STOP_VERIFY_INTERVAL_SECONDS", "15")))
FALCON_STOP_VERIFY_PERSIST_SECONDS = max(15, int(os.environ.get("FALCON_STOP_VERIFY_PERSIST_SECONDS", "60")))
FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS = max(60, int(os.environ.get("FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS", "3600")))
FALCON_CENTRAL_ONLY_EVIDENCE_MAX_AGE_SECONDS = max(30, int(os.environ.get("FALCON_CENTRAL_ONLY_EVIDENCE_MAX_AGE_SECONDS", "30")))

HEALTH.setdefault("real_management_version", FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION)
HEALTH.setdefault("last_real_management_action", None)
HEALTH.setdefault("last_real_management_error", None)
HEALTH.setdefault("last_tp50_execution_status", None)
HEALTH.setdefault("last_stop_replace_status", None)
HEALTH.setdefault("last_live_stop_status", None)


def falcon_is_live_real_position(pos):
    if not isinstance(pos, dict):
        return False
    live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    has_order = bool(pos.get("live_order_id") or pos.get("bingx_order_id") or live_order.get("order_id") or live_order.get("id"))
    sent = bool(live_order.get("sent") or has_order)
    return str(pos.get("execution_mode") or "").upper() == "LIVE" and has_order and sent


def falcon_real_remaining_qty(pos):
    for key in ("remaining_qty", "runner_qty", "qty", "initial_qty", "amount"):
        value = safe_float(pos.get(key), None)
        if value is not None and value > 0:
            return value
    live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    return safe_float(live_order.get("amount"), 0.0)


def falcon_issue_management_token(pos, operation, extra=None):
    if central_broker is None or not hasattr(central_broker, "issue_execution_auth_token"):
        return {"ok": False, "status": "MANAGEMENT_AUTH_HELPER_MISSING", "token": None, "error": BROKER_IMPORT_ERROR}
    context = {
        "bot": "FALCON",
        "setup": pos.get("setup"),
        "symbol": pos.get("symbol"),
        "side": pos.get("side"),
        "operation": operation,
        "trade_id": pos.get("trade_registry_id") or pos.get("id"),
        "source": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
    }
    if isinstance(extra, dict):
        context.update(extra)
    try:
        return central_broker.issue_execution_auth_token(context=context)
    except Exception as exc:
        return {"ok": False, "status": "MANAGEMENT_AUTH_ERROR", "token": None, "error": str(exc)}


def falcon_sync_live_order_state(sig, order):
    if not isinstance(sig, dict) or not isinstance(order, dict) or not order.get("sent"):
        return sig
    amount = safe_float(order.get("amount"), None)
    if amount is None:
        preview = order.get("preview") if isinstance(order.get("preview"), dict) else {}
        amount = safe_float(preview.get("amount"), None)
    disaster = order.get("disaster_stop") if isinstance(order.get("disaster_stop"), dict) else {}
    if amount is not None and amount > 0:
        sig["qty"] = amount
        sig["initial_qty"] = amount
        sig["remaining_qty"] = amount
    sig["live_order_id"] = order.get("order_id") or order.get("id") or sig.get("live_order_id")
    sig["bingx_order_id"] = sig.get("live_order_id")
    sig["live_client_order_id"] = order.get("client_order_id") or order.get("client_tag")
    lifecycle_identity = sig.get("live_client_order_id") or sig.get("live_order_id")
    if lifecycle_identity and not sig.get("lifecycle_id"):
        sig["lifecycle_id"] = f"CENTRAL-FALCON-LIFECYCLE:{lifecycle_identity}"
    sig["broker_entry_reference"] = order.get("price_ref")
    sig["broker_ack_at"] = order.get("ts")
    sig["broker_stop_order_id"] = disaster.get("order_id") or sig.get("broker_stop_order_id")
    sig["disaster_stop_order_id"] = sig.get("broker_stop_order_id")
    sig["broker_stop_client_order_id"] = disaster.get("client_order_id")
    sig["disaster_stop_client_order_id"] = disaster.get("client_order_id")
    sig["disaster_stop_client_order_id_unique"] = (
        disaster.get("client_order_id_unique") is True
    )
    sig["stop_client_order_id_revision"] = 0
    sig["client_order_id_reservation_status"] = disaster.get(
        "client_order_id_reservation_status"
    )
    sig["falcon_client_order_id_generator_version"] = (
        FALCON_CLIENT_ORDER_ID_GENERATOR_VERSION
    )
    sig["broker_stop_price"] = disaster.get("stop_price") or sig.get("stop")
    sig["broker_stop_amount"] = disaster.get("amount") or amount
    sig["broker_stop_status"] = disaster.get("status")
    sig["broker_stop_trigger_type"] = disaster.get("working_type") or disaster.get("trigger_type")
    # Preserve the factual Broker response for the passive Lifecycle observer.
    # These fields never authorize or change the stop; they are copied only
    # after ``place_market_order`` has returned its disaster-stop result.
    sig["broker_stop_side"] = disaster.get("side")
    sig["broker_stop_symbol"] = disaster.get("symbol")
    sig["broker_stop_type"] = disaster.get("type")
    sig["broker_stop_position_side"] = disaster.get("position_side")
    sig["broker_stop_reduce_only"] = disaster.get("reduce_only")
    sig["broker_stop_close_position"] = disaster.get("close_position")
    sig["broker_stop_hedge_mode_detected"] = disaster.get("hedge_mode_detected")
    sig["broker_stop_confirmed_at"] = disaster.get("timestamp") or order.get("ts")
    sig["disaster_stop_created"] = disaster.get("stop_created") is True
    sig["disaster_stop_client_order_id_reserved"] = (
        disaster.get("client_order_id_reserved") is True
    )
    sig["disaster_stop_operationally_armed"] = (
        disaster.get("stop_operationally_armed") is True
    )
    sig["disaster_stop_confirmed"] = sig["disaster_stop_operationally_armed"]
    if "entry_acknowledged" in order:
        sig["entry_acknowledged"] = order.get("entry_acknowledged") is True
    if "entry_ack_persistence_degraded" in order:
        sig["entry_ack_persistence_degraded"] = (
            order.get("entry_ack_persistence_degraded") is True
        )
    if order.get("reconciliation_required") is True:
        # The broker facts above prove that the LIVE position exists.  A
        # persistence failure may still require reconciliation, so keep normal
        # management visibly blocked without discarding ownership/protection
        # evidence needed by emergency recovery.
        sig["reconciliation_required"] = True
        sig["live_management_reconciliation_pending"] = True
        sig["live_management_block_reason"] = (
            "ENTRY_ACK_PERSISTENCE_RECONCILIATION_REQUIRED"
        )
    HEALTH["falcon_disaster_stop_client_order_id"] = disaster.get(
        "client_order_id"
    )
    HEALTH["falcon_disaster_stop_client_order_id_unique"] = (
        disaster.get("client_order_id_unique") is True
    )
    HEALTH["falcon_disaster_stop_created"] = sig["disaster_stop_created"]
    HEALTH["falcon_disaster_stop_client_order_id_reserved"] = (
        sig["disaster_stop_client_order_id_reserved"]
    )
    HEALTH["falcon_disaster_stop_operationally_armed"] = (
        sig["disaster_stop_operationally_armed"]
    )
    HEALTH["falcon_client_order_id_reservation_status"] = disaster.get(
        "client_order_id_reservation_status"
    )
    sig["real_management_version"] = FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION
    sig["registry_mode"] = "REAL"
    return sig


def falcon_handle_unsafe_live_entry_identity(sig, order):
    """Persist and contain a sent entry whose returned client ID is unsafe.

    The raw ``create_order`` return is an irreversible send fact.  It must not
    be downgraded to ``not sent``, but neither the position nor a disaster stop
    may inherit Falcon ownership until the returned clientOrderID matches the
    account-wide reservation.  This path therefore persists one incident and
    uses the existing managed-close boundary under the same lifecycle/account
    idempotency authorities.
    """

    sig = sig if isinstance(sig, dict) else {}
    order = order if isinstance(order, dict) else {}
    intended_client_order_id = str(
        order.get("client_order_id")
        or order.get("client_tag")
        or sig.get("entry_client_order_id")
        or ""
    ).strip()
    returned_client_order_id = str(
        order.get("returned_client_order_id") or ""
    ).strip() or None
    entry_order_id = str(
        order.get("order_id") or order.get("id") or ""
    ).strip() or None
    lifecycle_id = str(sig.get("lifecycle_id") or "").strip() or None
    symbol = normalize_symbol_for_central(sig.get("symbol"))
    side = _falcon_management_norm_side(sig.get("side"))
    unsafe = bool(
        order.get("sent") is True
        and (
            order.get("returned_client_order_id_matches") is False
            or order.get("entry_acknowledged") is not True
        )
    )
    if not unsafe:
        return {
            "ok": True,
            "status": "LIVE_ENTRY_IDENTITY_INCIDENT_NOT_APPLICABLE",
            "incident_detected": False,
            "sent": order.get("sent"),
            "reconciliation_required": bool(order.get("reconciliation_required")),
        }

    sig["reconciliation_required"] = True
    sig["live_entry_identity_unsafe"] = True
    sig["entry_retry_blocked"] = True
    sig["live_management_reconciliation_pending"] = True
    sig["live_management_block_reason"] = (
        "ENTRY_CLIENT_ORDER_ID_IDENTITY_UNSAFE"
    )

    incident_digest = hashlib.sha256(
        "|".join(
            str(value or "")
            for value in (
                "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE",
                lifecycle_id,
                intended_client_order_id,
                entry_order_id,
                symbol,
                side,
            )
        ).encode("utf-8")
    ).hexdigest().upper()
    incident_id = f"FALCON-ENTRY-IDENTITY-{incident_digest[:32]}"

    try:
        existing = falcon_terminal_stop_recovery_load(incident_id)
    except Exception as exc:
        existing = {
            "ok": False,
            "source": "READ_ERROR",
            "error": _falcon_terminal_safe_text(exc),
        }
    if not isinstance(existing, dict) or existing.get("ok") is not True:
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_INCIDENT_READ_BLOCKED",
            "incident_detected": True,
            "incident_id": incident_id,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "incident_read": _falcon_terminal_sanitize_projection(existing),
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result
    existing_state = (
        dict(existing.get("incident") or {})
        if isinstance(existing, dict)
        and existing.get("ok") is True
        and isinstance(existing.get("incident"), dict)
        else {}
    )
    if existing_state:
        return {
            "ok": existing_state.get("attempt_state") == "FAILSAFE_CONFIRMED",
            "status": "LIVE_ENTRY_IDENTITY_UNSAFE_ALREADY_RECORDED",
            "incident_detected": True,
            "incident_id": incident_id,
            "idempotent": True,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "existing_incident": _falcon_terminal_sanitize_projection(
                existing_state
            ),
        }

    # The intended ID is retained only as the immutable reservation identity
    # for the emergency close.  It is never projected back as proven Broker
    # ownership and no disaster-stop fields are populated here.
    incident_position = dict(sig)
    incident_position.update(
        {
            "execution_mode": "LIVE",
            "registry_mode": "REAL",
            "live_order_id": entry_order_id,
            "bingx_order_id": entry_order_id,
            "live_client_order_id": intended_client_order_id,
            "client_order_id": intended_client_order_id,
        }
    )
    lifecycle_lock_id = falcon_terminal_stop_lifecycle_lock_id(incident_position)
    owner_nonce = secrets.token_hex(24)
    lifecycle_lock = falcon_terminal_stop_acquire_lifecycle_lock(
        lifecycle_lock_id, owner_nonce
    )
    if lifecycle_lock.get("acquired") is not True:
        latest = falcon_terminal_stop_recovery_load(incident_id)
        latest_state = (
            dict(latest.get("incident") or {})
            if isinstance(latest, dict)
            and latest.get("ok") is True
            and isinstance(latest.get("incident"), dict)
            else {}
        )
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_UNSAFE_LIFECYCLE_LOCK_BLOCKED",
            "incident_detected": True,
            "incident_id": incident_id,
            "idempotent": bool(latest_state),
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "lifecycle_lock": _falcon_terminal_sanitize_projection(
                lifecycle_lock
            ),
            "existing_incident": _falcon_terminal_sanitize_projection(
                latest_state
            ),
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result
    state = {
        "incident_type": "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE",
        "incident_id": incident_id,
        "attempt_state": "DETECTED",
        # ``sent`` belongs to the fail-safe attempt in the shared recovery
        # schema.  Keep the irreversible entry fact separate so readers never
        # mistake DETECTED for an already-sent emergency close.
        "entry_sent": True,
        "sent": False,
        "send_attempted": False,
        "confirmed": False,
        "entry_acknowledged": order.get("entry_acknowledged"),
        "entry_order_id": entry_order_id,
        "intended_client_order_id": intended_client_order_id or None,
        "returned_client_order_id": returned_client_order_id,
        "returned_client_order_id_matches": order.get(
            "returned_client_order_id_matches"
        ),
        "lifecycle_id": lifecycle_id,
        "symbol": symbol,
        "side": side,
        "disaster_stop_binding_allowed": False,
        "entry_retry_blocked": True,
        "reconciliation_required": True,
        "first_detected_at": data_hora_sp_str(),
        "updated_at": data_hora_sp_str(),
    }
    initial_persistence = falcon_terminal_stop_recovery_save(incident_id, state)
    if initial_persistence.get("ok") is not True:
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_INCIDENT_PERSISTENCE_BLOCKED",
            "incident_detected": True,
            "incident_id": incident_id,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "persistence": initial_persistence,
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result

    try:
        record_event(
            "FALCON_LIVE_ENTRY_IDENTITY_UNSAFE",
            sig,
            {
                "incident_id": incident_id,
                "entry_order_id": entry_order_id,
                "intended_client_order_id": intended_client_order_id or None,
                "returned_client_order_id": returned_client_order_id,
                "returned_client_order_id_matches": order.get(
                    "returned_client_order_id_matches"
                ),
                "disaster_stop_binding_allowed": False,
                "entry_retry_blocked": True,
                "reconciliation_required": True,
            },
        )
    except Exception as exc:
        HEALTH["last_warning"] = (
            "falcon unsafe entry identity event: "
            f"{_falcon_terminal_safe_text(exc)}"
        )

    # The immediate response proves that a call returned, but its unsafe client
    # identity is not enough to authorize a close.  Re-read the exact exchange
    # order ID and require symbol, opening side and positive factual fill.
    entry_snapshot = None
    factual_fill = None
    entry_snapshot_valid = False
    entry_snapshot_predicates = {
        "entry_order_id_known": bool(entry_order_id),
        "symbol_known": bool(symbol),
        "entry_side_known": side in {"LONG", "SHORT"},
        "read_ok": False,
        "read_only": False,
        "order_id_matches": False,
        "symbol_matches": False,
        "entry_side_matches": False,
        "position_side_matches": False,
        "positive_factual_fill": False,
        "terminal_status": False,
        "remaining_zero_or_absent": False,
        "full_fill_if_amount_known": False,
    }
    if (
        central_broker is not None
        and hasattr(central_broker, "managed_order_snapshot")
        and entry_order_id
    ):
        try:
            entry_snapshot = central_broker.managed_order_snapshot(
                symbol, entry_order_id
            )
        except Exception as exc:
            entry_snapshot = {
                "ok": False,
                "status": "ENTRY_ORDER_SNAPSHOT_ERROR",
                "read_only": True,
                "sent": False,
                "error": _falcon_terminal_safe_text(exc),
                "error_type": type(exc).__name__,
            }
        if isinstance(entry_snapshot, dict) and entry_snapshot.get("ok") is True:
            snapshot_order_id = str(entry_snapshot.get("order_id") or "").strip()
            snapshot_symbol = normalize_symbol_for_central(entry_snapshot.get("symbol"))
            snapshot_side = str(entry_snapshot.get("side") or "").upper().strip()
            snapshot_position_side = _falcon_management_norm_side(
                entry_snapshot.get("position_side")
            )
            expected_entry_side = "BUY" if side == "LONG" else "SELL"
            raw_factual_fill = entry_snapshot.get("filled")
            if raw_factual_fill in (None, ""):
                raw_factual_fill = entry_snapshot.get("executed_quantity")
            factual_fill = safe_float(
                raw_factual_fill,
                None,
            )
            snapshot_status = str(
                entry_snapshot.get("status") or ""
            ).upper().strip()
            snapshot_raw_status = str(
                entry_snapshot.get("raw_status") or ""
            ).upper().strip()
            terminal_statuses = {
                "CLOSED",
                "FILLED",
                "EXECUTED",
                "COMPLETED",
                "DONE",
                "FINISHED",
            }
            terminal_status = bool(
                snapshot_status in terminal_statuses
                or snapshot_raw_status in terminal_statuses
            )
            raw_remaining = entry_snapshot.get("remaining")
            if raw_remaining in (None, ""):
                raw_remaining = entry_snapshot.get("remaining_quantity")
            factual_remaining = safe_float(raw_remaining, None)
            factual_amount = safe_float(entry_snapshot.get("amount"), None)
            quantity_basis = factual_amount if factual_amount is not None else factual_fill
            quantity_tolerance = max(
                1e-12,
                abs(quantity_basis or 0.0) * 1e-6,
            )
            remaining_zero_or_absent = bool(
                factual_remaining is None
                or abs(factual_remaining) <= quantity_tolerance
            )
            full_fill_if_amount_known = bool(
                factual_amount is None
                or (
                    factual_fill is not None
                    and factual_fill + quantity_tolerance >= factual_amount
                )
            )
            snapshot_reduce_only = _falcon_management_bool(
                entry_snapshot.get("reduce_only")
            )
            snapshot_close_position = _falcon_management_bool(
                entry_snapshot.get("close_position")
            )
            entry_snapshot_predicates = {
                "read_ok": True,
                "read_only": entry_snapshot.get("read_only") is True,
                "order_id_matches": snapshot_order_id == entry_order_id,
                "symbol_matches": snapshot_symbol == symbol,
                "entry_side_matches": snapshot_side == expected_entry_side,
                # BingX one-way mode commonly reports BOTH.  This remains
                # constrained by exact order/symbol/opening-side/fill checks.
                "position_side_matches": snapshot_position_side in ("", side, "BOTH"),
                "not_reduce_only": snapshot_reduce_only is not True,
                "not_close_position": snapshot_close_position is not True,
                "positive_factual_fill": bool(
                    factual_fill is not None and factual_fill > 0
                ),
                "terminal_status": terminal_status,
                "remaining_zero_or_absent": remaining_zero_or_absent,
                "full_fill_if_amount_known": full_fill_if_amount_known,
            }
            entry_snapshot_valid = all(entry_snapshot_predicates.values())

    if not entry_snapshot_valid:
        state.update(
            {
                "attempt_state": "FACTUAL_ENTRY_FILL_REQUIRED",
                "entry_order_snapshot": _falcon_terminal_sanitize_projection(
                    entry_snapshot
                ),
                "entry_order_snapshot_predicates": dict(
                    entry_snapshot_predicates
                ),
                "updated_at": data_hora_sp_str(),
            }
        )
        final_persistence = falcon_terminal_stop_recovery_save(incident_id, state)
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_UNSAFE_FACTUAL_FILL_REQUIRED",
            "incident_detected": True,
            "incident_id": incident_id,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "persistence": final_persistence,
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result

    incident_position["qty"] = factual_fill
    incident_position["initial_qty"] = factual_fill
    incident_position["remaining_qty"] = factual_fill

    close_reservation = falcon_prepare_position_client_order_id(
        incident_position,
        ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
        0,
        attempt=0,
    )
    auth_extra = {
        "amount": factual_fill,
        "expected_position_amount": factual_fill,
        "reason": "ENTRY_CLIENT_ORDER_ID_UNSAFE_FAILSAFE",
        "idempotency_key": incident_id,
        "emergency_operation": "ENTRY_IDENTITY_UNSAFE_FAILSAFE_CLOSE",
        "lifecycle_id": lifecycle_id,
        "client_order_id": intended_client_order_id or None,
        "entry_order_id": entry_order_id,
    }
    auth = falcon_issue_management_token(
        incident_position,
        "managed_close_position_market",
        auth_extra,
    )
    token = auth.get("token") if isinstance(auth, dict) else None
    auth_context = (
        auth.get("context")
        if isinstance(auth, dict) and isinstance(auth.get("context"), dict)
        else {}
    )
    auth_amount = safe_float(auth_context.get("amount"), None)
    auth_expected_amount = safe_float(
        auth_context.get("expected_position_amount"), None
    )
    amount_tolerance = max(
        FALCON_MANAGEMENT_AMOUNT_TOLERANCE,
        abs(factual_fill) * 1e-6,
    )
    strong_incident_identity = bool(
        lifecycle_id
        and intended_client_order_id
        and entry_order_id
        and symbol
        and side in {"LONG", "SHORT"}
    )
    auth_context_matches = bool(
        strong_incident_identity
        and auth_context.get("operation") == "managed_close_position_market"
        and normalize_symbol_for_central(auth_context.get("symbol")) == symbol
        and _falcon_management_norm_side(auth_context.get("side")) == side
        and auth_context.get("reason")
        == "ENTRY_CLIENT_ORDER_ID_UNSAFE_FAILSAFE"
        and auth_context.get("idempotency_key") == incident_id
        and auth_context.get("emergency_operation")
        == "ENTRY_IDENTITY_UNSAFE_FAILSAFE_CLOSE"
        and auth_context.get("lifecycle_id") == lifecycle_id
        and auth_context.get("client_order_id")
        == (intended_client_order_id or None)
        and auth_context.get("entry_order_id") == entry_order_id
        and auth_amount is not None
        and auth_expected_amount is not None
        and abs(auth_amount - factual_fill) <= amount_tolerance
        and abs(auth_expected_amount - factual_fill) <= amount_tolerance
    )
    auth_projection = _falcon_terminal_auth_projection(
        auth, auth_context_matches
    )
    if (
        close_reservation.get("send_allowed") is not True
        or not strong_incident_identity
        or not isinstance(auth, dict)
        or auth.get("ok") is not True
        or not token
        or not auth_context_matches
    ):
        state.update(
            {
                "attempt_state": "FAILSAFE_PRE_SEND_BLOCKED",
                "factual_entry_fill": factual_fill,
                "client_order_id_reservation": (
                    _falcon_client_order_authority_projection(close_reservation)
                ),
                "auth": auth_projection,
                "lifecycle_lock_retained": True,
                "updated_at": data_hora_sp_str(),
            }
        )
        final_persistence = falcon_terminal_stop_recovery_save(incident_id, state)
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_PRE_SEND_BLOCKED",
            "incident_detected": True,
            "incident_id": incident_id,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "client_order_id_reservation": close_reservation,
            "lifecycle_lock": lifecycle_lock,
            "persistence": final_persistence,
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result

    state.update(
        {
            "attempt_state": "BROKER_CALL_PENDING",
            "send_attempted": False,
            "sent": False,
            "confirmed": False,
            "factual_entry_fill": factual_fill,
            "entry_order_snapshot": _falcon_terminal_sanitize_projection(
                entry_snapshot
            ),
            "entry_order_snapshot_predicates": dict(entry_snapshot_predicates),
            "client_order_id": close_reservation.get("client_order_id"),
            "client_order_id_reservation": (
                _falcon_client_order_authority_projection(close_reservation)
            ),
            "auth": auth_projection,
            "lifecycle_lock_retained": True,
            "updated_at": data_hora_sp_str(),
        }
    )
    pre_send_persistence = falcon_terminal_stop_recovery_save(incident_id, state)
    if pre_send_persistence.get("ok") is not True:
        result = {
            "ok": False,
            "status": "LIVE_ENTRY_IDENTITY_UNSAFE_PRE_SEND_PERSISTENCE_BLOCKED",
            "incident_detected": True,
            "incident_id": incident_id,
            "sent": True,
            "entry_retry_blocked": True,
            "disaster_stop_binding_allowed": False,
            "failsafe_attempted": False,
            "reconciliation_required": True,
            "client_order_id_reservation": close_reservation,
            "lifecycle_lock": lifecycle_lock,
            "persistence": pre_send_persistence,
        }
        HEALTH["last_real_management_error"] = result["status"]
        return result

    try:
        close_result = central_broker.managed_close_position_market(
            symbol=symbol,
            side=side,
            amount=factual_fill,
            expected_position_amount=factual_fill,
            client_tag=close_reservation.get("client_order_id"),
            reason="ENTRY_CLIENT_ORDER_ID_UNSAFE_FAILSAFE",
            execution_auth_token=token,
            client_order_id_reservation=close_reservation,
        )
    except Exception as exc:
        close_result = {
            "ok": False,
            "status": "MANAGED_CLOSE_ERROR",
            "sent": None,
            "confirmed": None,
            "send_attempted": True,
            "send_outcome_unknown": True,
            "phase": "BROKER_CALL_PENDING",
            "symbol": symbol,
            "side": side,
            "client_order_id": close_reservation.get("client_order_id"),
            "error": _falcon_terminal_safe_text(exc),
            "error_type": type(exc).__name__,
        }
    projected = _falcon_terminal_stop_result_projection(
        close_result,
        expected_client_order_id=close_reservation.get("client_order_id"),
        expected_symbol=symbol,
        expected_side=side,
        expected_amount=factual_fill,
    )
    confirmed = bool(
        projected.get("sent") is True and projected.get("confirmed") is True
    )
    state.update(
        {
            "attempt_state": "FAILSAFE_CONFIRMED" if confirmed else (
                "FAILSAFE_SEND_OUTCOME_UNKNOWN"
                if projected.get("send_outcome_unknown") is True
                else "FAILSAFE_NOT_CONFIRMED"
            ),
            "failsafe_result": projected,
            "send_attempted": projected.get("send_attempted") is True,
            "sent": projected.get("sent"),
            "confirmed": projected.get("confirmed"),
            "lifecycle_lock_retained": True,
            "updated_at": data_hora_sp_str(),
        }
    )
    final_persistence = falcon_terminal_stop_recovery_save(incident_id, state)
    status = (
        "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_CONFIRMED"
        if confirmed
        else "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_SEND_OUTCOME_UNKNOWN"
        if projected.get("send_outcome_unknown") is True
        else "LIVE_ENTRY_IDENTITY_UNSAFE_FAILSAFE_NOT_CONFIRMED"
    )
    HEALTH["last_real_management_action"] = {
        "action": "ENTRY_IDENTITY_UNSAFE_FAILSAFE_CLOSE",
        "status": status,
        "symbol": symbol,
        "ts": data_hora_sp_str(),
    }
    if not confirmed:
        HEALTH["last_real_management_error"] = status
    return {
        "ok": bool(confirmed and final_persistence.get("ok") is True),
        "status": status,
        "incident_detected": True,
        "incident_id": incident_id,
        "sent": True,
        "entry_retry_blocked": True,
        "disaster_stop_binding_allowed": False,
        "failsafe_attempted": True,
        "failsafe": projected,
        "reconciliation_required": True,
        "client_order_id_reservation": close_reservation,
        "lifecycle_lock": lifecycle_lock,
        "lifecycle_lock_retained": True,
        "persistence": final_persistence,
    }


# Envolve a função de entrada existente sem reescrever o gate.
_ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1 = execute_signal_if_allowed

def execute_signal_if_allowed(sig, positions=None):
    allowed, decision = _ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1(sig, positions=positions)
    order = sig.get("live_order") if isinstance(sig, dict) and isinstance(sig.get("live_order"), dict) else {}
    disaster = (
        order.get("disaster_stop")
        if isinstance(order.get("disaster_stop"), dict)
        else {}
    )
    protected_ack_persistence_degraded = bool(
        order.get("sent") is True
        and order.get("entry_acknowledged") is True
        and order.get("returned_client_order_id_matches") is not False
        and disaster.get("stop_operationally_armed") is True
    )
    safe_sent_identity = bool(
        order.get("sent") is True
        and order.get("returned_client_order_id_matches") is not False
    )
    if (allowed and safe_sent_identity) or protected_ack_persistence_degraded:
        falcon_sync_live_order_state(sig, order)
    if not allowed and protected_ack_persistence_degraded:
        # ``ok=False`` here describes the ACK journal failure, not an absent
        # entry.  Returning the persistence path lets the existing scanner save
        # this one factual position and register it exactly as it does for a
        # normal acknowledged entry.  It never invokes the broker again.
        sig["reconciliation_required"] = True
        sig["live_management_reconciliation_pending"] = True
        sig["live_management_block_reason"] = (
            "ENTRY_ACK_PERSISTENCE_RECONCILIATION_REQUIRED"
        )
        previous = decision if isinstance(decision, dict) else {}
        decision = {
            **dict(previous),
            "allowed": True,
            "decision": "LIVE_POSITION_RECOGNIZED_RECONCILIATION_REQUIRED",
            "status": order.get("status")
            or "LIVE_SENT_PROTECTED_ENTRY_ACK_PERSISTENCE_ERROR",
            "reconciliation_required": True,
            "management_allowed": False,
            "entry_acknowledged": True,
            "disaster_stop_operationally_armed": True,
            "reasons": [],
            "warnings": list(previous.get("warnings") or [])
            + [
                "Entrada e disaster stop confirmados; persistencia do ACK "
                "requer reconciliacao antes da gestao normal."
            ],
        }
        sig["execution_decision"] = decision
        HEALTH["last_execution_decision"] = decision
        return True, decision
    return allowed, decision


# Compatibilidade do ponto de extensao: todos os fatos LIVE/REAL agora fazem
# parte do unico ``register_open_trade`` acima. Nao existe segundo writer.
_ORIGINAL_REGISTER_FALCON_TRADE_REGISTRY_OPEN_BEFORE_RPM_V1 = register_falcon_trade_registry_open

def register_falcon_trade_registry_open(pos):
    result = _ORIGINAL_REGISTER_FALCON_TRADE_REGISTRY_OPEN_BEFORE_RPM_V1(pos)
    if isinstance(result, dict) and result.get("ok"):
        result = dict(result)
        result["registry_sync_writes"] = 1
        result["live_metadata_projected_in_open"] = bool(
            falcon_is_live_real_position(pos)
        )
    return result


def falcon_update_registry_management(pos, **metadata):
    if central_trade_registry is None:
        return None
    trade_id = pos.get("trade_registry_id")
    if not trade_id:
        trade_id = central_trade_registry.make_trade_id("FALCON", normalize_symbol_for_central(pos.get("symbol")), pos.get("side"), pos.get("setup"))
    try:
        top = {
            # qty permanece a quantidade inicial do trade; runner fica em metadata.
            "qty": safe_float(pos.get("initial_qty"), safe_float(pos.get("qty"), falcon_real_remaining_qty(pos))),
            "sl": pos.get("stop"),
            "metadata": {
                "remaining_qty": pos.get("remaining_qty"),
                "runner_qty": pos.get("runner_qty"),
                "broker_stop_order_id": pos.get("broker_stop_order_id"),
                "broker_stop_client_order_id": pos.get("broker_stop_client_order_id"),
                "disaster_stop_client_order_id": pos.get("disaster_stop_client_order_id"),
                "disaster_stop_client_order_id_reserved": pos.get("disaster_stop_client_order_id_reserved"),
                "disaster_stop_client_order_id_unique": pos.get("disaster_stop_client_order_id_unique"),
                "disaster_stop_created": pos.get("disaster_stop_created"),
                "disaster_stop_operationally_armed": pos.get("disaster_stop_operationally_armed"),
                "client_order_id_reservation_status": pos.get("client_order_id_reservation_status"),
                "falcon_client_order_id_generator_version": pos.get("falcon_client_order_id_generator_version"),
                "broker_stop_price": pos.get("broker_stop_price"),
                "broker_stop_amount": pos.get("broker_stop_amount"),
                "broker_stop_status": pos.get("broker_stop_status"),
                "broker_stop_trigger_type": pos.get("broker_stop_trigger_type"),
                "broker_stop_side": pos.get("broker_stop_side"),
                "broker_stop_symbol": pos.get("broker_stop_symbol"),
                "broker_stop_type": pos.get("broker_stop_type"),
                "broker_stop_position_side": pos.get("broker_stop_position_side"),
                "broker_stop_reduce_only": pos.get("broker_stop_reduce_only"),
                "broker_stop_close_position": pos.get("broker_stop_close_position"),
                "broker_stop_hedge_mode_detected": pos.get("broker_stop_hedge_mode_detected"),
                "broker_stop_confirmed_at": pos.get("broker_stop_confirmed_at"),
                "disaster_stop_confirmed": pos.get("disaster_stop_confirmed"),
                "tp50_real_executed": pos.get("tp50_real_executed"),
                "tp50_real_order_id": pos.get("tp50_real_order_id"),
                "tp50_amount": pos.get("tp50_amount"),
                "tp50_fill_price": pos.get("tp50_fill_price"),
                "real_management_version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
                **metadata,
            },
        }
        return central_trade_registry.update_trade(trade_id, **top)
    except Exception as exc:
        HEALTH["last_real_management_error"] = f"registry management: {exc}"
        return None


def _falcon_management_norm_symbol(value):
    return str(value or "").upper().strip().replace("/", "").replace(":USDT", "").replace("-", "")


def _falcon_management_norm_side(value):
    side = str(value or "").upper().strip()
    if side in {"BUY", "LONG"}:
        return "LONG"
    if side in {"SELL", "SHORT"}:
        return "SHORT"
    return side


def falcon_position_identity(pos, position_id=None):
    """Return the strong Central identity used by reconciliation and alert dedup."""
    pos = pos if isinstance(pos, dict) else {}
    live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    return {
        "position_id": str(position_id or pos.get("id") or "").strip() or None,
        "trade_id": str(pos.get("trade_registry_id") or pos.get("trade_id") or "").strip() or None,
        "lifecycle_id": str(pos.get("lifecycle_id") or "").strip() or None,
        "order_id": str(pos.get("live_order_id") or pos.get("bingx_order_id") or live_order.get("order_id") or live_order.get("id") or "").strip() or None,
        "client_order_id": str(pos.get("live_client_order_id") or pos.get("client_order_id") or live_order.get("client_order_id") or live_order.get("client_tag") or "").strip() or None,
        "symbol": _falcon_management_norm_symbol(pos.get("symbol")),
        "side": _falcon_management_norm_side(pos.get("side")),
    }


def falcon_position_client_order_identity(
    pos, operation, revision, attempt=0
):
    identity = falcon_position_identity(pos)
    return {
        "bot": "FALCON",
        "lifecycle_id": identity.get("lifecycle_id"),
        "entry_client_order_id": identity.get("client_order_id"),
        "entry_order_id": identity.get("order_id"),
        "symbol": identity.get("symbol"),
        "side": identity.get("side"),
        "operation": operation,
        "revision": revision,
        "attempt": attempt,
    }


def falcon_generate_position_client_order_id(
    pos, operation, revision, attempt=0
):
    return generate_falcon_client_order_id(
        **falcon_position_client_order_identity(
            pos, operation, revision, attempt=attempt
        )
    )


def falcon_prepare_position_client_order_id(
    pos, operation, revision, attempt=0
):
    identity = falcon_position_client_order_identity(
        pos, operation, revision, attempt=attempt
    )
    return falcon_prepare_canonical_client_order_id(identity)


def falcon_authorize_position_client_order_retry(
    pos,
    operation,
    revision,
    prior_reservation,
    next_attempt,
):
    """Authorize one contiguous retry through the account-wide authority."""
    prior = prior_reservation if isinstance(prior_reservation, dict) else {}
    try:
        next_identity = canonical_falcon_order_identity(
            **falcon_position_client_order_identity(
                pos,
                operation,
                revision,
                attempt=next_attempt,
            )
        )
        result = authorize_account_client_order_next_attempt(
            canonical_operation_id=prior.get("canonical_operation_id"),
            prior_attempt_id=prior.get("attempt_id"),
            next_attempt_id=next_identity.get("attempt_id"),
            next_attempt_sequence=next_identity.get("attempt_sequence"),
            reconciliation_status="NOT_CREATED",
            evidence_source="FALCON_TERMINAL_STOP_PRE_SEND_AUTHORITY",
            # The account authority accepts the ISO-8601 ``Z`` form in its
            # identity-safe evidence fields (``+`` is intentionally outside
            # that alphabet).
            reconciled_at=datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            redis_client=redis,
            set_if_absent=bandwidth_redis_set_if_absent,
            get_authoritative=bandwidth_redis_get_authoritative,
        )
        return {
            **dict(result or {}),
            "next_attempt": next_identity.get("attempt_sequence"),
            "next_attempt_id": next_identity.get("attempt_id"),
        }
    except Exception as exc:
        return {
            "ok": False,
            "send_allowed": False,
            "status": "CLIENT_ORDER_RETRY_AUTHORIZATION_ERROR",
            "next_attempt": next_attempt,
            "persistent": False,
            "reconciliation_required": True,
            "error_type": type(exc).__name__,
        }


def falcon_record_client_order_attempt_outcome(
    reservation,
    outcome_state,
    *,
    reason=None,
    failure_phase=None,
):
    """Append an immutable attempt outcome; the reserved ID is never released."""
    try:
        outcome_kwargs = {"outcome_state": outcome_state}
        if reason not in (None, ""):
            outcome_kwargs["reason"] = reason
        if failure_phase not in (None, ""):
            outcome_kwargs["failure_phase"] = failure_phase
        return record_account_client_order_attempt_outcome(
            reservation if isinstance(reservation, dict) else {},
            redis_client=redis,
            set_if_absent=bandwidth_redis_set_if_absent,
            get_authoritative=bandwidth_redis_get_authoritative,
            now=lambda: datetime.now(timezone.utc).isoformat(),
            **outcome_kwargs,
        )
    except Exception as exc:
        return {
            "ok": False,
            "status": "ATTEMPT_OUTCOME_PERSISTENCE_ERROR",
            "persistent": False,
            "id_released": False,
            "reconciliation_required": True,
            "error_type": type(exc).__name__,
        }


def _falcon_client_order_authority_projection(value):
    """Keep only durable, non-secret identity evidence in recovery state."""
    value = value if isinstance(value, dict) else {}
    return {
        key: value.get(key)
        for key in (
            "ok",
            "send_allowed",
            "status",
            "client_order_id",
            "client_order_id_reserved",
            "client_order_id_unique",
            "collision_detected",
            "same_attempt",
            "same_identity",
            "persistent",
            "reconciliation_required",
            "role",
            "identity_hash",
            "attempt_identity_hash",
            "canonical_operation_id",
            "attempt_id",
            "attempt_sequence",
            "prior_attempt_id",
            "prior_attempt_sequence",
            "proof_mode",
            "evidence_hash",
            "revision",
            "attempt",
            "next_attempt",
            "next_attempt_id",
            "attempt_disposition",
            "reason",
            "failure_phase",
            "id_released",
            "lifecycle_blocked",
            "error_type",
        )
        if value.get(key) is not None
    }


def falcon_position_identity_fingerprint(pos, position_id=None):
    identity = falcon_position_identity(pos, position_id=position_id)
    strong = identity.get("lifecycle_id") or identity.get("client_order_id") or identity.get("order_id") or identity.get("position_id")
    if not strong:
        return ""
    return "|".join([
        identity.get("symbol") or "",
        identity.get("side") or "",
        identity.get("position_id") or "",
        identity.get("lifecycle_id") or "",
        identity.get("client_order_id") or "",
        identity.get("order_id") or "",
    ])[:700]


def falcon_position_tombstone_keys(pos, position_id=None):
    """Build operational tombstone keys; reusable position IDs are never identity."""
    identity = falcon_position_identity(pos, position_id=position_id)
    keys = []
    for label, field in (
        ("LIFECYCLE", "lifecycle_id"),
        ("CLIENT", "client_order_id"),
        ("ORDER", "order_id"),
    ):
        value = identity.get(field)
        if value not in (None, ""):
            keys.append(f"{label}|{str(value).strip()}")
    return keys


def _falcon_prune_timestamped_map(value, now_epoch=None, max_items=500, max_age_seconds=2592000):
    now_epoch = safe_float(now_epoch, time.time())
    source = value if isinstance(value, dict) else {}
    kept = {}
    ordered = []
    for key, item in source.items():
        item = item if isinstance(item, dict) else {}
        epoch = safe_float(item.get("updated_epoch") or item.get("last_attempt_epoch") or item.get("reconciled_epoch"), 0.0)
        if epoch and now_epoch - epoch > max_age_seconds:
            continue
        ordered.append((epoch, str(key), item))
    for _, key, item in sorted(ordered, reverse=True)[:max_items]:
        kept[key] = item
    return kept


def falcon_filter_reconciled_positions(positions):
    """Drop exact tombstoned identities before any Redis save, including stale saves."""
    positions = positions if isinstance(positions, dict) else {}
    tombstones = _falcon_prune_timestamped_map(redis_get_json(FALCON_CENTRAL_ONLY_TOMBSTONES_KEY, {}))
    for key, value in _central_only_tombstones_memory.items():
        tombstones.setdefault(key, value)
    if not tombstones:
        return positions
    filtered = {}
    for pid, pos in positions.items():
        identity_keys = falcon_position_tombstone_keys(pos, position_id=pid)
        if any(key in tombstones for key in identity_keys):
            continue
        filtered[pid] = pos
    return filtered


def _falcon_management_alert_fingerprint(pos, reason, position_id=None):
    base = falcon_position_identity_fingerprint(pos, position_id=position_id)
    return f"{base}|{str(reason or '').upper().strip()}" if base else ""


def falcon_management_alert_decision(pos, reason, now_epoch=None, position_id=None):
    """Persist alert intent before transport so repeated management cycles are deduplicated."""
    now_epoch = safe_float(now_epoch, time.time())
    now_text = data_hora_sp_str()
    fingerprint = _falcon_management_alert_fingerprint(pos, reason, position_id=position_id)
    if not fingerprint:
        HEALTH["falcon_management_spam_guard_status"] = "IDENTITY_INSUFFICIENT"
        HEALTH["falcon_management_spam_guard_last_reason"] = reason
        return {"send": False, "suppressed": True, "status": "IDENTITY_INSUFFICIENT", "fingerprint": None}
    with management_alert_guard_lock:
        persisted_guard = redis_get_json(FALCON_MANAGEMENT_ALERT_GUARD_KEY, {})
        guard = _falcon_prune_timestamped_map(
            persisted_guard if isinstance(persisted_guard, dict) else _management_alert_guard_memory,
            now_epoch=now_epoch,
        )
        for key, value in _management_alert_guard_memory.items():
            guard.setdefault(key, value)
        previous = guard.get(fingerprint) if isinstance(guard.get(fingerprint), dict) else {}
        last_attempt = safe_float(previous.get("last_attempt_epoch"), 0.0)
        suppressed = bool(last_attempt and now_epoch - last_attempt < FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS)
        entry = dict(previous)
        entry.update({
            "fingerprint": fingerprint,
            "reason": str(reason or "").upper().strip(),
            "last_attempt_epoch": last_attempt if suppressed else now_epoch,
            "last_attempt_at": previous.get("last_attempt_at") if suppressed else now_text,
            "updated_epoch": now_epoch,
            "updated_at": now_text,
        })
        if suppressed:
            entry["suppressed_count"] = int(entry.get("suppressed_count") or 0) + 1
            entry["last_suppressed_at"] = now_text
        else:
            entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
        guard[fingerprint] = entry
        _management_alert_guard_memory.clear()
        _management_alert_guard_memory.update(guard)
        persisted = redis_set_json(FALCON_MANAGEMENT_ALERT_GUARD_KEY, guard)
    pos["management_alert_guard"] = dict(entry)
    pos["management_alert_reason"] = str(reason or "").upper().strip()
    HEALTH["falcon_management_spam_guard_last_reason"] = str(reason or "").upper().strip()
    if suppressed:
        HEALTH["falcon_management_spam_guard_status"] = "SUPPRESSED_COOLDOWN"
        HEALTH["falcon_management_spam_guard_suppressed_count"] = int(HEALTH.get("falcon_management_spam_guard_suppressed_count") or 0) + 1
        HEALTH["falcon_management_spam_guard_last_suppressed_at"] = now_text
    else:
        HEALTH["falcon_management_spam_guard_status"] = "ALERT_ALLOWED"
    return {
        "send": not suppressed,
        "suppressed": suppressed,
        "status": "SUPPRESSED_COOLDOWN" if suppressed else "ALERT_ALLOWED",
        "fingerprint": fingerprint,
        "cooldown_seconds": FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS,
        "persisted": bool(persisted),
        "entry": dict(entry),
    }


def falcon_clear_management_alert(pos=None, position_id=None, reason=None):
    pos = pos if isinstance(pos, dict) else {}
    base = falcon_position_identity_fingerprint(pos, position_id=position_id)
    expected = _falcon_management_alert_fingerprint(pos, reason, position_id=position_id) if reason else None
    removed = 0
    with management_alert_guard_lock:
        guard = _falcon_prune_timestamped_map(redis_get_json(FALCON_MANAGEMENT_ALERT_GUARD_KEY, {}))
        for key, value in _management_alert_guard_memory.items():
            guard.setdefault(key, value)
        for key in list(guard):
            if (expected and key == expected) or (base and key.startswith(base + "|")):
                guard.pop(key, None)
                removed += 1
        _management_alert_guard_memory.clear()
        _management_alert_guard_memory.update(guard)
        persisted = redis_set_json(FALCON_MANAGEMENT_ALERT_GUARD_KEY, guard)
    if removed:
        HEALTH["falcon_management_spam_guard_status"] = "CLEARED_AFTER_RECONCILIATION"
    return {"ok": bool(persisted), "removed": removed, "persisted": bool(persisted), "no_order_sent": True}


def falcon_reconcile_remove_position(position_id=None, order_id=None, client_order_id=None, lifecycle_id=None, trade_id=None):
    """Remove one exact Central-only position without Broker, PnL, Telegram or close logic."""
    requested = {
        "order_id": str(order_id).strip() if order_id not in (None, "") else None,
        "client_order_id": str(client_order_id).strip() if client_order_id not in (None, "") else None,
        "lifecycle_id": str(lifecycle_id).strip() if lifecycle_id not in (None, "") else None,
    }
    if not any(requested.values()):
        return {"ok": False, "status": "STRONG_IDENTITY_REQUIRED", "removed": False, "no_order_sent": True}
    now_epoch = time.time()
    now_text = data_hora_sp_str()
    with position_mutation_lock:
        positions = get_positions()
        matches = []
        identity_candidates = 0
        identity_conflicts = []
        rejected_reasons = []
        for pid, pos in positions.items():
            identity = falcon_position_identity(pos, position_id=pid)
            typed_matches = [
                bool(supplied and identity.get(field) and str(supplied) == str(identity.get(field)))
                for field, supplied in requested.items()
            ]
            conflicts = []
            for supplied, current, label in (
                (order_id, identity.get("order_id"), "order_id"),
                (client_order_id, identity.get("client_order_id"), "client_order_id"),
                (lifecycle_id, identity.get("lifecycle_id"), "lifecycle_id"),
                (trade_id, identity.get("trade_id"), "trade_id"),
            ):
                if supplied not in (None, "") and current not in (None, "") and str(supplied) != str(current):
                    conflicts.append(label)
            same_position = position_id not in (None, "") and str(pid) == str(position_id)
            if conflicts and (same_position or any(typed_matches)):
                identity_conflicts.append({"position_id": str(pid), "fields": sorted(conflicts)})
                continue
            if conflicts or not any(typed_matches):
                continue
            if position_id not in (None, "") and str(pid) != str(position_id):
                identity_conflicts.append({"position_id": str(pid), "fields": ["position_id"]})
                continue
            identity_candidates += 1
            evidence = pos.get("central_only_evidence") if isinstance(pos.get("central_only_evidence"), dict) else {}
            evidence_epoch = safe_float(evidence.get("checked_epoch"), 0.0)
            evidence_fresh = bool(
                evidence_epoch
                and -5 <= now_epoch - evidence_epoch <= FALCON_CENTRAL_ONLY_EVIDENCE_MAX_AGE_SECONDS
            )
            live_mode = str(pos.get("execution_mode") or "").upper() == "LIVE" or str(pos.get("registry_mode") or "").upper() == "REAL"
            evidence_position_qty = safe_float(evidence.get("position_qty"), None)
            evidence_matched_count = evidence.get("matched_count")
            try:
                evidence_matched_count = int(evidence_matched_count) if evidence_matched_count is not None else None
            except Exception:
                evidence_matched_count = None
            terminal_stop_status = str(evidence.get("stop_order_status") or "").upper().strip() in {
                "ORDER_NOT_FOUND", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "FAILED", "FILLED", "EXECUTED", "CLOSED",
            }
            evidence_identity_ok = all(
                evidence.get(field) in (None, "")
                or identity.get(field) not in (None, "") and str(evidence.get(field)) == str(identity.get(field))
                for field in ("trade_id", "lifecycle_id", "order_id", "client_order_id")
            )
            evidence_trade_id_ok = bool(
                identity.get("trade_id")
                and evidence.get("trade_id") not in (None, "")
                and str(evidence.get("trade_id")) == str(identity.get("trade_id"))
            )
            evidence_strong_match = any(
                evidence.get(field) not in (None, "")
                and identity.get(field) not in (None, "")
                and str(evidence.get(field)) == str(identity.get(field))
                for field in ("lifecycle_id", "order_id", "client_order_id")
            )
            evidence_identity_ok = bool(
                evidence_identity_ok
                and evidence_trade_id_ok
                and evidence_strong_match
                and _falcon_management_norm_symbol(evidence.get("symbol")) == identity.get("symbol")
                and _falcon_management_norm_side(evidence.get("side")) == identity.get("side")
            )
            eligible = bool(
                live_mode
                and pos.get("central_only_reconcile_required") is True
                and evidence.get("broker_flat") is True
                and evidence_position_qty is not None
                and 0 <= evidence_position_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE
                and evidence_matched_count is not None
                and evidence_matched_count == 0
                and evidence.get("read_only") is True
                and evidence.get("sent") is False
                and evidence.get("stop_order_active") is False
                and terminal_stop_status
                and evidence_identity_ok
                and evidence_fresh
            )
            if not eligible:
                rejected_reasons.append({"position_id": str(pid), "reason": "CENTRAL_ONLY_EVIDENCE_NOT_ELIGIBLE"})
                continue
            matches.append((pid, pos))
        if not matches:
            if identity_conflicts:
                return {
                    "ok": False,
                    "status": "POSITION_IDENTITY_CONFLICT",
                    "removed": False,
                    "conflicts": identity_conflicts,
                    "no_order_sent": True,
                }
            if identity_candidates:
                return {
                    "ok": False,
                    "status": "POSITION_NOT_RECONCILABLE",
                    "removed": False,
                    "reasons": rejected_reasons,
                    "no_order_sent": True,
                }
            return {"ok": True, "status": "ALREADY_REMOVED", "removed": False, "already_removed": True, "no_order_sent": True}
        if len(matches) != 1:
            return {"ok": False, "status": "AMBIGUOUS_POSITION_IDENTITY", "removed": False, "matches": len(matches), "no_order_sent": True}
        matched_pid, matched_pos = matches[0]
        tombstone_keys = falcon_position_tombstone_keys(matched_pos, position_id=matched_pid)
        if not tombstone_keys:
            return {"ok": False, "status": "POSITION_IDENTITY_MISSING", "removed": False, "no_order_sent": True}
        tombstones = _falcon_prune_timestamped_map(redis_get_json(FALCON_CENTRAL_ONLY_TOMBSTONES_KEY, {}), now_epoch=now_epoch)
        tombstone = {
            "position_id": str(matched_pid),
            "trade_id": trade_id or matched_pos.get("trade_registry_id"),
            "order_id": order_id,
            "client_order_id": client_order_id,
            "lifecycle_id": lifecycle_id,
            "reason": "CENTRAL_ONLY_BROKER_FLAT_RECONCILED",
            "reconciled_at": now_text,
            "reconciled_epoch": now_epoch,
            "updated_epoch": now_epoch,
        }
        for key in tombstone_keys:
            tombstones[key] = dict(tombstone, tombstone_key=key)
        if not redis_set_json(FALCON_CENTRAL_ONLY_TOMBSTONES_KEY, tombstones):
            return {"ok": False, "status": "TOMBSTONE_PERSIST_FAILED", "removed": False, "no_order_sent": True}
        _central_only_tombstones_memory.clear()
        _central_only_tombstones_memory.update(tombstones)
        positions.pop(matched_pid, None)
        saved = save_positions(positions)
        if not saved:
            return {"ok": False, "status": "POSITION_SAVE_FAILED", "removed": False, "no_order_sent": True}
        alert_clear = falcon_clear_management_alert(matched_pos, position_id=matched_pid)
        falcon_refresh_management_safety_health(positions)
        return {
            "ok": True,
            "status": "CENTRAL_ONLY_POSITION_REMOVED",
            "removed": True,
            "position_id": str(matched_pid),
            "tombstone_keys": tombstone_keys,
            "alert_clear": alert_clear,
            "no_order_sent": True,
        }


def _falcon_stop_status_flags(status, order_snapshot=None):
    status = str(status or "UNKNOWN").upper().strip()
    order_snapshot = order_snapshot if isinstance(order_snapshot, dict) else {}
    active = status in {"OPEN", "NEW", "ACTIVE", "PENDING", "TRIGGER_PENDING", "PARTIALLY_FILLED"}
    filled_qty = safe_float(order_snapshot.get("filled"), 0.0)
    filled = status in {"FILLED", "EXECUTED"} or (status == "CLOSED" and filled_qty > 0)
    triggered = status in {"TRIGGERED", "TRIGGERING"}
    cancelled = status in {"CANCELED", "CANCELLED", "EXPIRED"}
    rejected = status in {"REJECTED", "FAILED"}
    return {"active": active, "filled": filled, "triggered": triggered, "cancelled": cancelled, "rejected": rejected}


def _falcon_management_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim", "on"}:
        return True
    if text in {"0", "false", "no", "nao", "não", "off"}:
        return False
    return None


def _falcon_stop_creation_evidence(pos, identity, expected_stop_order_id):
    """Return immutable Central creation evidence eligible only by strong lifecycle identity."""
    pos = pos if isinstance(pos, dict) else {}
    identity = identity if isinstance(identity, dict) else {}
    live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
    disaster = live_order.get("disaster_stop") if isinstance(live_order.get("disaster_stop"), dict) else {}
    creation_order_id = str(
        disaster.get("order_id")
        or pos.get("broker_stop_order_id")
        or pos.get("disaster_stop_order_id")
        or ""
    ).strip()
    expected_order_id = str(expected_stop_order_id or "").strip()
    strong_lifecycle_identity = bool(
        identity.get("lifecycle_id")
        and (identity.get("order_id") or identity.get("client_order_id"))
    )
    eligible = bool(
        expected_order_id
        and creation_order_id == expected_order_id
        and strong_lifecycle_identity
    )
    return {
        "eligible": eligible,
        "order_id": creation_order_id or None,
        "lifecycle_id": identity.get("lifecycle_id"),
        "symbol": disaster.get("symbol") or pos.get("broker_stop_symbol"),
        "side": disaster.get("side") or pos.get("broker_stop_side"),
        "type": disaster.get("type") or pos.get("broker_stop_type"),
        "position_side": disaster.get("position_side") or pos.get("broker_stop_position_side"),
        "reduce_only": disaster.get("reduce_only") if disaster.get("reduce_only") is not None else pos.get("broker_stop_reduce_only"),
        "close_position": disaster.get("close_position") if disaster.get("close_position") is not None else pos.get("broker_stop_close_position"),
        "stop_price": disaster.get("stop_price") or pos.get("broker_stop_price") or pos.get("stop"),
        "working_type": disaster.get("working_type") or disaster.get("trigger_type") or pos.get("broker_stop_trigger_type"),
        "amount": disaster.get("amount") or pos.get("broker_stop_amount"),
        "hedge_mode_detected": disaster.get("hedge_mode_detected") if disaster.get("hedge_mode_detected") is not None else pos.get("broker_stop_hedge_mode_detected"),
        "source": "CENTRAL_DISASTER_STOP_CREATION_EVIDENCE",
    }


def _falcon_protective_stop_evidence(
    order_snapshot,
    identity,
    expected_amount=None,
    reference_price=None,
    creation_evidence=None,
    hedge_mode=None,
    expected_stop_order_id=None,
):
    """Pure, fail-closed semantic verification for one exact disaster-stop order."""
    order_snapshot = order_snapshot if isinstance(order_snapshot, dict) else {}
    identity = identity if isinstance(identity, dict) else {}
    creation = creation_evidence if isinstance(creation_evidence, dict) and creation_evidence.get("eligible") else {}

    def present(value):
        return value is not None and str(value).strip().upper() not in {"", "UNKNOWN", "NONE", "NULL"}

    def token(value):
        return str(value or "").upper().strip().replace("-", "_").replace(" ", "_")

    def factual_or_creation(key, *aliases):
        factual_value = order_snapshot.get(key)
        if not present(factual_value):
            for alias in aliases:
                factual_value = order_snapshot.get(alias)
                if present(factual_value):
                    break
        if present(factual_value):
            return factual_value, "BROKER"
        creation_value = creation.get(key)
        if not present(creation_value):
            for alias in aliases:
                creation_value = creation.get(alias)
                if present(creation_value):
                    break
        if present(creation_value):
            return creation_value, "CENTRAL_CREATION_FALLBACK"
        return None, "MISSING"

    actual_order_id = str(order_snapshot.get("order_id") or order_snapshot.get("id") or "").strip()
    expected_order_id = str(expected_stop_order_id or "").strip()
    order_identity_matches = bool(not expected_order_id or (actual_order_id and actual_order_id == expected_order_id))
    lifecycle_identity_present = bool(
        identity.get("lifecycle_id")
        and (identity.get("order_id") or identity.get("client_order_id"))
    )
    strong_ownership = bool(expected_order_id and order_identity_matches and lifecycle_identity_present)

    execution_type_value, execution_type_source = factual_or_creation("execution_type", "type")
    if present(order_snapshot.get("execution_type")):
        order_type_value, order_type_source = factual_or_creation("order_type")
    else:
        # Compatibility for snapshots produced before the normalizer exposed
        # execution_type and order_type independently.
        order_type_value, order_type_source = factual_or_creation("order_type", "type")
    plan_type_value, plan_type_source = factual_or_creation("plan_type")
    trigger_order_type_value, trigger_order_type_source = factual_or_creation("trigger_order_type")
    execution_type = token(execution_type_value)
    order_type = token(order_type_value)
    plan_type = token(plan_type_value)
    trigger_order_type = token(trigger_order_type_value)
    normalized_type_sources = order_snapshot.get("type_sources")
    if not isinstance(normalized_type_sources, list):
        normalized_type_sources = []
    source_type_tokens = [
        token(item.get("value"))
        for item in normalized_type_sources
        if isinstance(item, dict) and present(item.get("value"))
    ]
    type_tokens = [
        value
        for value in (execution_type, order_type, plan_type, trigger_order_type, *source_type_tokens)
        if value
    ]

    def is_take_profit_type(value):
        return bool(value == "TP" or "TAKE_PROFIT" in value or "TAKEPROFIT" in value)

    stop_loss_price_value, stop_loss_price_source = factual_or_creation("stop_loss_price")
    take_profit_price_value, take_profit_price_source = factual_or_creation("take_profit_price")
    stop_loss_price = safe_float(stop_loss_price_value, None)
    take_profit_price = safe_float(take_profit_price_value, None)
    stop_type_tokens = [value for value in type_tokens if "STOP" in value and not is_take_profit_type(value)]
    take_profit_type_tokens = [value for value in type_tokens if is_take_profit_type(value)]
    stop_loss_evidence_present = bool(stop_type_tokens or present(stop_loss_price_value))
    take_profit_evidence_present = bool(take_profit_type_tokens or present(take_profit_price_value))
    valid_types = {"STOP", "STOP_MARKET", "STOP_LOSS", "TRIGGER_MARKET"}
    direct_type = next((value for value in type_tokens if value in valid_types), None)
    explicit_market_sl_evidence = bool(
        present(stop_loss_price_value)
        or any(
            "STOP" in value and not is_take_profit_type(value)
            for value in (order_type, plan_type, trigger_order_type)
            if value
        )
        or any(
            item.get("field") != "execution_type"
            and "STOP" in token(item.get("value"))
            and not is_take_profit_type(token(item.get("value")))
            for item in normalized_type_sources
            if isinstance(item, dict)
        )
    )
    if stop_loss_evidence_present and take_profit_evidence_present:
        type_valid = False
        type_valid_reason = "SL_TP_EVIDENCE_CONFLICT"
    elif take_profit_evidence_present:
        type_valid = False
        type_valid_reason = "TAKE_PROFIT_EVIDENCE_PRESENT"
    elif execution_type == "MARKET":
        type_valid = bool(explicit_market_sl_evidence and strong_ownership)
        if not explicit_market_sl_evidence:
            type_valid_reason = "MARKET_WITHOUT_EXPLICIT_STOP_LOSS_EVIDENCE"
        elif not strong_ownership:
            type_valid_reason = "MARKET_WITHOUT_STRONG_OWNERSHIP"
        else:
            type_valid_reason = "MARKET_WITH_EXPLICIT_STOP_LOSS_EVIDENCE"
    elif direct_type:
        type_valid = True
        type_valid_reason = "DIRECT_PROTECTIVE_TYPE"
    else:
        type_valid = False
        type_valid_reason = "UNSUPPORTED_ORDER_TYPE"

    type_source_summary = [
        {
            "field": field,
            "value": value or None,
            "source": source,
        }
        for field, value, source in (
            ("execution_type", execution_type, execution_type_source),
            ("order_type", order_type, order_type_source),
            ("plan_type", plan_type, plan_type_source),
            ("trigger_order_type", trigger_order_type, trigger_order_type_source),
        )
        if value
    ]
    if normalized_type_sources:
        type_source_summary = [dict(item) for item in normalized_type_sources if isinstance(item, dict)]

    expected_symbol = _falcon_management_norm_symbol(identity.get("symbol"))
    symbol_value, symbol_source = factual_or_creation("symbol")
    actual_symbol = _falcon_management_norm_symbol(symbol_value)
    symbol_matches = bool(expected_symbol and actual_symbol and actual_symbol == expected_symbol)

    expected_position_side = _falcon_management_norm_side(identity.get("side"))
    expected_close_side = "SELL" if expected_position_side == "LONG" else "BUY"
    side_value, side_source = factual_or_creation("side")
    actual_side = token(side_value)
    close_side_matches = bool(expected_position_side in {"LONG", "SHORT"} and actual_side == expected_close_side)

    position_side_value, position_side_source = factual_or_creation("position_side")
    actual_position_side = _falcon_management_norm_side(position_side_value)
    reduce_only_value, reduce_only_source = factual_or_creation("reduce_only")
    close_position_value, close_position_source = factual_or_creation("close_position")
    reduce_only = _falcon_management_bool(reduce_only_value)
    close_position = _falcon_management_bool(close_position_value)
    reduce_only_confirmed = reduce_only is True
    close_position_token = token(close_position_value)
    close_position_confirmed = bool(close_position is True or close_position_token in {"100", "100%", "FULL", "ALL"})

    close_semantic = token(order_snapshot.get("close_semantic"))
    expected_close_semantic = f"CLOSE_{expected_position_side}" if expected_position_side in {"LONG", "SHORT"} else ""
    close_semantic_matches = bool(
        expected_close_semantic
        and (
            expected_close_semantic in close_semantic
            or close_semantic in {expected_position_side, f"CLOSE{expected_position_side}"}
        )
    )
    conflicting_close_semantic = bool(
        close_semantic
        and any(value in close_semantic for value in {"CLOSE_LONG", "CLOSE_SHORT"})
        and not close_semantic_matches
    )

    explicit_hedge = _falcon_management_bool(hedge_mode)
    if explicit_hedge is None:
        explicit_hedge = _falcon_management_bool(creation.get("hedge_mode_detected"))
    if explicit_hedge is None and actual_position_side in {"LONG", "SHORT"}:
        explicit_hedge = True
    hedge_mode_confirmed = explicit_hedge is True
    position_side_matches = bool(
        (
            actual_position_side == expected_position_side
            if actual_position_side
            else (close_position_confirmed or close_semantic_matches)
        )
        if hedge_mode_confirmed
        else actual_position_side in {"", expected_position_side}
    )
    if hedge_mode_confirmed:
        close_semantics_confirmed = bool(
            position_side_matches
            or close_position_confirmed
            or close_semantic_matches
        )
    else:
        close_semantics_confirmed = bool(reduce_only_confirmed or close_position_confirmed)

    stop_price_value, stop_price_source = factual_or_creation("stop_price")
    stop_price = safe_float(stop_price_value, None)
    reference = safe_float(reference_price, None)
    trigger_direction_valid = bool(
        stop_price is not None
        and stop_price > 0
        and reference is not None
        and reference > 0
        and (
            (expected_position_side == "LONG" and stop_price < reference)
            or (expected_position_side == "SHORT" and stop_price > reference)
        )
    )
    working_type_value, working_type_source = factual_or_creation("working_type")
    working_type = token(working_type_value)
    trigger_type_valid = working_type in {"MARK", "MARK_PRICE", "MARKET_PRICE"}

    remaining_amount = safe_float(order_snapshot.get("remaining"), None)
    amount_value, amount_source = factual_or_creation("amount")
    original_amount = safe_float(amount_value, None)
    amount = remaining_amount if remaining_amount is not None and remaining_amount > FALCON_MANAGEMENT_AMOUNT_TOLERANCE else original_amount
    expected = safe_float(expected_amount, None)
    close_percent = safe_float(str(order_snapshot.get("close_percent") or "").replace("%", ""), None)
    full_close_confirmed = bool(close_position_confirmed or (close_percent is not None and close_percent >= 100.0))
    quantity_covers_position = bool(
        full_close_confirmed
        or (
            amount is not None
            and amount > 0
            and (
                expected is None
                or expected <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE
                or amount + max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, max(amount, expected) * 1e-6) >= expected
            )
        )
    )

    conflicts = []
    creation_fallback_eligible = bool(creation)
    if creation_fallback_eligible:
        factual_symbol = _falcon_management_norm_symbol(order_snapshot.get("symbol"))
        creation_symbol = _falcon_management_norm_symbol(creation.get("symbol"))
        if factual_symbol and creation_symbol and factual_symbol != creation_symbol:
            conflicts.append("SYMBOL_CONFLICT")
        factual_side = token(order_snapshot.get("side"))
        creation_side = token(creation.get("side"))
        if factual_side and factual_side != "UNKNOWN" and creation_side and factual_side != creation_side:
            conflicts.append("SIDE_CONFLICT")
        factual_position_side = _falcon_management_norm_side(order_snapshot.get("position_side"))
        creation_position_side = _falcon_management_norm_side(creation.get("position_side"))
        if factual_position_side and creation_position_side and factual_position_side != creation_position_side:
            conflicts.append("POSITION_SIDE_CONFLICT")
        factual_type = direct_type or execution_type or token(order_snapshot.get("type"))
        creation_type = token(creation.get("type"))
        factual_type_stop = bool(stop_loss_evidence_present or factual_type in valid_types)
        creation_type_stop = creation_type in valid_types
        if factual_type and factual_type != "UNKNOWN" and creation_type and factual_type_stop != creation_type_stop:
            conflicts.append("ORDER_TYPE_CONFLICT")
        creation_lifecycle_id = str(creation.get("lifecycle_id") or "").strip()
        identity_lifecycle_id = str(identity.get("lifecycle_id") or "").strip()
        if creation_lifecycle_id and identity_lifecycle_id and creation_lifecycle_id != identity_lifecycle_id:
            conflicts.append("LIFECYCLE_ID_CONFLICT")
    if stop_loss_evidence_present and take_profit_evidence_present:
        conflicts.append("SL_TP_EVIDENCE_CONFLICT")
    factual_conflict = bool(conflicts or conflicting_close_semantic)
    if conflicting_close_semantic:
        conflicts.append("CLOSE_SEMANTIC_CONFLICT")

    status = token(order_snapshot.get("status"))
    status_active = status in {"OPEN", "NEW", "ACTIVE", "PENDING", "TRIGGER_PENDING", "PARTIALLY_FILLED"}
    protective_semantics_valid = bool(
        order_snapshot.get("ok")
        and order_identity_matches
        and type_valid
        and symbol_matches
        and close_side_matches
        and position_side_matches
        and close_semantics_confirmed
        and trigger_direction_valid
        and trigger_type_valid
        and quantity_covers_position
        and not factual_conflict
    )
    semantic_stop_valid = bool(protective_semantics_valid and status_active)
    predicates = {
        "type_valid": type_valid,
        "symbol_matches": symbol_matches,
        "close_side_matches": close_side_matches,
        "position_side_matches": position_side_matches,
        "reduce_only_confirmed": reduce_only_confirmed,
        "close_position_confirmed": close_position_confirmed,
        "close_semantics_confirmed": close_semantics_confirmed,
        "trigger_direction_valid": trigger_direction_valid,
        "trigger_type_valid": trigger_type_valid,
        "quantity_covers_position": quantity_covers_position,
        "status_active": status_active,
        "order_identity_matches": order_identity_matches,
        "strong_ownership": strong_ownership,
        "factual_conflict": factual_conflict,
        "semantic_stop_valid": semantic_stop_valid,
    }
    required_true_predicates = (
        "type_valid", "symbol_matches", "close_side_matches", "position_side_matches",
        "close_semantics_confirmed", "trigger_direction_valid", "trigger_type_valid",
        "quantity_covers_position", "status_active", "order_identity_matches",
    )
    failure_reasons = [name.upper() for name in required_true_predicates if predicates.get(name) is False]
    if factual_conflict:
        failure_reasons.append("FACTUAL_CONFLICT")
    return {
        "protective": protective_semantics_valid,
        "protective_semantics_valid": protective_semantics_valid,
        "semantic_stop_valid": semantic_stop_valid,
        "predicates": predicates,
        **predicates,
        "failure_reasons": failure_reasons,
        "factual_conflicts": conflicts,
        "order_type": order_type,
        "order_type_source": order_type_source,
        "execution_type": execution_type or None,
        "execution_type_source": execution_type_source,
        "plan_type": plan_type or None,
        "plan_type_source": plan_type_source,
        "trigger_order_type": trigger_order_type or None,
        "trigger_order_type_source": trigger_order_type_source,
        "stop_loss_price": stop_loss_price,
        "stop_loss_price_source": stop_loss_price_source,
        "take_profit_price": take_profit_price,
        "take_profit_price_source": take_profit_price_source,
        "stop_loss_evidence_present": stop_loss_evidence_present,
        "take_profit_evidence_present": take_profit_evidence_present,
        "type_source_summary": type_source_summary,
        "type_valid_reason": type_valid_reason,
        "expected_symbol": expected_symbol,
        "actual_symbol": actual_symbol,
        "symbol_source": symbol_source,
        "expected_close_side": expected_close_side,
        "actual_side": actual_side,
        "side_source": side_source,
        "expected_position_side": expected_position_side,
        "actual_position_side": actual_position_side,
        "position_side_source": position_side_source,
        "reduce_only": reduce_only,
        "reduce_only_source": reduce_only_source,
        "close_position": close_position,
        "close_position_source": close_position_source,
        "close_semantic": close_semantic or None,
        "close_semantics_confirmed": close_semantics_confirmed,
        "hedge_mode": hedge_mode_confirmed,
        "stop_price": stop_price,
        "stop_price_source": stop_price_source,
        "reference_price": reference,
        "working_type": working_type,
        "working_type_source": working_type_source,
        "amount": amount,
        "amount_source": amount_source,
        "expected_amount": expected,
        "full_close_confirmed": full_close_confirmed,
        "amount_matches": quantity_covers_position,
        "creation_fallback_eligible": creation_fallback_eligible,
    }


def _falcon_stop_not_found_evidence(order_snapshot):
    order_snapshot = order_snapshot if isinstance(order_snapshot, dict) else {}
    return str(order_snapshot.get("status") or "").upper().strip() == "ORDER_NOT_FOUND"


def _falcon_confirmed_stop_fill_evidence(pos, position_id, order_snapshot, expected_amount):
    """Confirm an exact, protective and quantity-complete disaster-stop fill."""
    pos = pos if isinstance(pos, dict) else {}
    order_snapshot = order_snapshot if isinstance(order_snapshot, dict) else {}
    expected_stop_id = str(pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id") or "").strip()
    actual_stop_id = str(order_snapshot.get("order_id") or order_snapshot.get("id") or "").strip()
    expected = safe_float(expected_amount, None)
    filled_qty = safe_float(order_snapshot.get("filled"), 0.0)
    average = safe_float(order_snapshot.get("average"), None)
    flags = _falcon_stop_status_flags(order_snapshot.get("status"), order_snapshot)
    protective = _falcon_protective_stop_evidence(
        order_snapshot,
        falcon_position_identity(pos, position_id=position_id),
        expected_amount=expected,
        reference_price=pos.get("entry"),
        expected_stop_order_id=expected_stop_id,
    )
    quantity_complete = bool(
        expected is not None
        and expected > 0
        and filled_qty > 0
        and abs(filled_qty - expected) <= max(
            FALCON_MANAGEMENT_AMOUNT_TOLERANCE,
            max(filled_qty, expected) * 1e-6,
        )
    )
    confirmed = bool(
        flags.get("filled")
        and expected_stop_id
        and actual_stop_id == expected_stop_id
        and pos.get("entry_ownership_verified") is True
        and protective.get("protective")
        and quantity_complete
        and average is not None
        and average > 0
    )
    return {
        "confirmed": confirmed,
        "expected_stop_order_id": expected_stop_id or None,
        "actual_stop_order_id": actual_stop_id or None,
        "entry_ownership_verified": pos.get("entry_ownership_verified") is True,
        "protective": bool(protective.get("protective")),
        "quantity_complete": quantity_complete,
        "filled_qty": filled_qty,
        "expected_qty": expected,
        "average": average,
        "flags": flags,
        "protective_evidence": protective,
    }


def _falcon_update_stop_health(result):
    HEALTH["falcon_disaster_stop_active_verified"] = bool(
        result.get("stop_order_active")
        and result.get("stop_order_identity_match")
        and result.get("protection_matches_position")
        and result.get("stop_order_protective_verified")
        and result.get("entry_ownership_verified")
        and result.get("client_order_id_reserved") is True
        and result.get("client_order_id_unique") is True
        and result.get("stop_client_order_id_match") is True
        and result.get("stop_operationally_armed") is True
    )
    HEALTH["falcon_disaster_stop_client_order_id"] = result.get(
        "disaster_stop_client_order_id"
    )
    HEALTH["falcon_disaster_stop_client_order_id_unique"] = (
        result.get("client_order_id_unique") is True
    )
    HEALTH["falcon_disaster_stop_client_order_id_reserved"] = (
        result.get("client_order_id_reserved") is True
    )
    HEALTH["falcon_disaster_stop_operationally_armed"] = (
        result.get("stop_operationally_armed") is True
    )
    HEALTH["falcon_disaster_stop_trigger_type"] = result.get("trigger_type")
    HEALTH["falcon_disaster_stop_order_status"] = result.get("stop_order_status")
    HEALTH["falcon_disaster_stop_order_id"] = result.get("stop_order_id")
    HEALTH["falcon_disaster_stop_last_checked_at"] = result.get("stop_order_last_checked_at")
    HEALTH["falcon_disaster_stop_protection_matches_position"] = bool(result.get("protection_matches_position"))
    HEALTH["falcon_stop_anomaly_detected"] = bool(result.get("stop_anomaly_detected"))
    HEALTH["falcon_stop_anomaly_last_reason"] = result.get("stop_anomaly_reason")
    predicates = result.get("stop_semantic_predicates") if isinstance(result.get("stop_semantic_predicates"), dict) else {}
    HEALTH["falcon_disaster_stop_semantic_predicates"] = dict(predicates)
    HEALTH["falcon_disaster_stop_semantic_failure_reasons"] = list(result.get("stop_semantic_failure_reasons") or [])
    HEALTH["falcon_disaster_stop_execution_type"] = result.get("execution_type")
    HEALTH["falcon_disaster_stop_plan_type"] = result.get("plan_type")
    HEALTH["falcon_disaster_stop_trigger_order_type"] = result.get("trigger_order_type")
    HEALTH["falcon_disaster_stop_stop_loss_evidence_present"] = result.get("stop_loss_evidence_present")
    HEALTH["falcon_disaster_stop_take_profit_evidence_present"] = result.get("take_profit_evidence_present")
    HEALTH["falcon_disaster_stop_type_source_summary"] = list(result.get("type_source_summary") or [])
    HEALTH["falcon_disaster_stop_type_valid_reason"] = result.get("type_valid_reason")
    for predicate_name in (
        "type_valid", "symbol_matches", "close_side_matches", "position_side_matches",
        "reduce_only_confirmed", "close_position_confirmed", "trigger_direction_valid",
        "close_semantics_confirmed", "quantity_covers_position", "status_active", "semantic_stop_valid",
    ):
        HEALTH[f"falcon_disaster_stop_{predicate_name}"] = result.get(predicate_name, predicates.get(predicate_name))
    if result.get("central_only_reconcile_required"):
        HEALTH["falcon_central_only_pending_count"] = max(1, int(HEALTH.get("falcon_central_only_pending_count") or 0))


def falcon_refresh_management_safety_health(positions):
    """Aggregate safety health so one healthy trade cannot hide another anomaly."""
    positions = positions if isinstance(positions, dict) else {}
    live_rows = [
        row for row in positions.values()
        if isinstance(row, dict)
        and (str(row.get("execution_mode") or "").upper() == "LIVE" or str(row.get("registry_mode") or "").upper() == "REAL")
    ]
    pending = [row for row in live_rows if row.get("central_only_reconcile_required")]
    anomalies = [row for row in live_rows if row.get("stop_anomaly_detected")]
    HEALTH["falcon_central_only_pending_count"] = len(pending)
    HEALTH["falcon_disaster_stop_active_verified"] = bool(live_rows) and all(
        bool(row.get("disaster_stop_active_verified"))
        and row.get("disaster_stop_client_order_id_unique") is True
        for row in live_rows
    )
    HEALTH["falcon_disaster_stop_protection_matches_position"] = bool(live_rows) and all(bool(row.get("protection_matches_position")) for row in live_rows)
    HEALTH["falcon_stop_anomaly_detected"] = bool(anomalies)
    selected = (anomalies or pending or live_rows)[-1] if (anomalies or pending or live_rows) else {}
    HEALTH["falcon_stop_anomaly_last_reason"] = selected.get("stop_anomaly_last_reason")
    HEALTH["falcon_disaster_stop_trigger_type"] = (selected.get("live_stop_verification") or {}).get("trigger_type") or selected.get("stop_order_trigger_type") or selected.get("broker_stop_trigger_type")
    HEALTH["falcon_disaster_stop_order_status"] = selected.get("stop_order_status")
    HEALTH["falcon_disaster_stop_order_id"] = selected.get("stop_order_id") or selected.get("broker_stop_order_id")
    HEALTH["falcon_disaster_stop_last_checked_at"] = selected.get("stop_order_last_checked_at")
    verification = selected.get("live_stop_verification") if isinstance(selected.get("live_stop_verification"), dict) else {}
    predicates = verification.get("stop_semantic_predicates") if isinstance(verification.get("stop_semantic_predicates"), dict) else {}
    HEALTH["falcon_disaster_stop_semantic_predicates"] = dict(predicates)
    HEALTH["falcon_disaster_stop_semantic_failure_reasons"] = list(verification.get("stop_semantic_failure_reasons") or [])
    HEALTH["falcon_disaster_stop_execution_type"] = verification.get("execution_type")
    HEALTH["falcon_disaster_stop_plan_type"] = verification.get("plan_type")
    HEALTH["falcon_disaster_stop_trigger_order_type"] = verification.get("trigger_order_type")
    HEALTH["falcon_disaster_stop_stop_loss_evidence_present"] = verification.get("stop_loss_evidence_present")
    HEALTH["falcon_disaster_stop_take_profit_evidence_present"] = verification.get("take_profit_evidence_present")
    HEALTH["falcon_disaster_stop_type_source_summary"] = list(verification.get("type_source_summary") or [])
    HEALTH["falcon_disaster_stop_type_valid_reason"] = verification.get("type_valid_reason")
    for predicate_name in (
        "type_valid", "symbol_matches", "close_side_matches", "position_side_matches",
        "reduce_only_confirmed", "close_position_confirmed", "trigger_direction_valid",
        "close_semantics_confirmed", "quantity_covers_position", "status_active", "semantic_stop_valid",
    ):
        HEALTH[f"falcon_disaster_stop_{predicate_name}"] = verification.get(predicate_name, predicates.get(predicate_name))
    return {
        "live_count": len(live_rows),
        "central_only_pending_count": len(pending),
        "anomaly_count": len(anomalies),
    }


def falcon_verify_live_disaster_stop(pos, now_epoch=None, force=False, persist_registry=True):
    """Read Broker position/stop facts before any normal LIVE management action."""
    now_epoch = safe_float(now_epoch, time.time())
    now_text = data_hora_sp_str()
    cached = pos.get("live_stop_verification") if isinstance(pos.get("live_stop_verification"), dict) else {}
    last_epoch = safe_float(pos.get("stop_order_last_checked_epoch"), 0.0)
    if not force and cached and last_epoch and now_epoch - last_epoch < FALCON_STOP_VERIFY_INTERVAL_SECONDS:
        result = dict(cached)
        result["cached"] = True
        _falcon_update_stop_health(result)
        return result
    identity = falcon_position_identity(pos)
    remaining = falcon_real_remaining_qty(pos)
    stop_order_id = pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
    creation_stop_evidence = _falcon_stop_creation_evidence(pos, identity, stop_order_id)
    result = {
        "ok": False,
        "status": "STOP_VERIFICATION_NOT_RUN",
        "management_allowed": False,
        "central_only_reconcile_required": False,
        "failsafe_eligible": False,
        "read_only": True,
        "sent": False,
        "stop_order_id": str(stop_order_id) if stop_order_id not in (None, "") else None,
        "disaster_stop_client_order_id": pos.get("disaster_stop_client_order_id") or pos.get("broker_stop_client_order_id"),
        "client_order_id_reserved": pos.get("disaster_stop_client_order_id_reserved") is True,
        "client_order_id_unique": pos.get("disaster_stop_client_order_id_unique") is True,
        "stop_operationally_armed": pos.get("disaster_stop_operationally_armed") is True,
        "entry_order_id": identity.get("order_id"),
        "entry_order_status": "UNKNOWN",
        "entry_order_filled_qty": None,
        "entry_ownership_verified": False,
        "trigger_price": safe_float(pos.get("broker_stop_price"), safe_float(pos.get("stop"), None)),
        "trigger_type": None,
        "trigger_type_creation_evidence": pos.get("broker_stop_trigger_type"),
        "stop_order_type": None,
        "execution_type": None,
        "plan_type": None,
        "trigger_order_type": None,
        "stop_loss_evidence_present": False,
        "take_profit_evidence_present": False,
        "type_source_summary": [],
        "type_valid_reason": "NOT_EVALUATED",
        "stop_side": pos.get("broker_stop_side"),
        "stop_position_side": None,
        "stop_reduce_only": None,
        "stop_close_position": None,
        "stop_order_status": "UNKNOWN",
        "stop_order_active": False,
        "stop_order_filled": False,
        "stop_order_triggered": False,
        "stop_order_cancelled": False,
        "stop_order_rejected": False,
        "stop_order_full_fill_confirmed": False,
        "stop_order_last_checked_at": now_text,
        "stop_order_last_checked_epoch": now_epoch,
        "protected_qty": None,
        "protected_qty_expected": safe_float(pos.get("broker_stop_amount"), remaining),
        "position_qty": None,
        "protection_matches_position": False,
        "stop_anomaly_detected": False,
        "stop_anomaly_reason": None,
        "semantic_stop_valid": False,
        "stop_semantic_predicates": {},
        "stop_semantic_failure_reasons": [],
        "stop_creation_evidence_eligible": bool(creation_stop_evidence.get("eligible")),
        "identity": identity,
    }
    if central_broker is None or not hasattr(central_broker, "managed_position_snapshot"):
        result.update({"status": "POSITION_VERIFICATION_HELPER_MISSING", "stop_anomaly_detected": True, "stop_anomaly_reason": "POSITION_VERIFICATION_HELPER_MISSING"})
    else:
        try:
            position_snapshot = central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side"), expected_amount=remaining)
        except Exception as exc:
            position_snapshot = {"ok": False, "status": "POSITION_SNAPSHOT_EXCEPTION", "error": str(exc), "read_only": True, "sent": False}
        result["position_snapshot"] = position_snapshot
        if not isinstance(position_snapshot, dict) or not position_snapshot.get("ok"):
            result.update({"status": "POSITION_VERIFICATION_ERROR", "stop_anomaly_detected": True, "stop_anomaly_reason": "POSITION_VERIFICATION_ERROR"})
        else:
            position_qty = safe_float(position_snapshot.get("amount"), 0.0)
            result["position_qty"] = position_qty
            entry_snapshot = {}
            entry_order_id = identity.get("order_id")
            if entry_order_id and hasattr(central_broker, "managed_order_snapshot"):
                try:
                    entry_snapshot = central_broker.managed_order_snapshot(pos.get("symbol"), entry_order_id)
                except Exception as exc:
                    entry_snapshot = {"ok": False, "status": "ENTRY_ORDER_SNAPSHOT_EXCEPTION", "error": str(exc), "read_only": True, "sent": False}
            elif not entry_order_id:
                entry_snapshot = {"ok": False, "status": "ENTRY_ORDER_ID_MISSING", "read_only": True, "sent": False}
            else:
                entry_snapshot = {"ok": False, "status": "ORDER_VERIFICATION_HELPER_MISSING", "read_only": True, "sent": False}
            result["entry_order_snapshot"] = entry_snapshot
            entry_status = str((entry_snapshot or {}).get("status") or "UNKNOWN").upper().strip()
            entry_filled = safe_float((entry_snapshot or {}).get("filled"), 0.0)
            expected_entry_side = "BUY" if identity.get("side") == "LONG" else "SELL"
            actual_entry_side = str((entry_snapshot or {}).get("side") or "").upper().strip()
            expected_client_id = str(identity.get("client_order_id") or "").strip()
            actual_client_id = str((entry_snapshot or {}).get("client_order_id") or "").strip()
            client_matches = bool(not expected_client_id or (actual_client_id and expected_client_id == actual_client_id))
            entry_quantity_covers_position = bool(
                entry_filled > 0
                and (
                    position_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE
                    or entry_filled + max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, entry_filled * 1e-6) >= position_qty
                )
            )
            entry_ownership_verified = bool(
                (entry_snapshot or {}).get("ok")
                and entry_status in {"FILLED", "EXECUTED", "CLOSED"}
                and actual_entry_side == expected_entry_side
                and client_matches
                and entry_quantity_covers_position
            )
            result.update({
                "entry_order_status": entry_status,
                "entry_order_filled_qty": entry_filled,
                "entry_order_side": actual_entry_side,
                "entry_order_client_id": actual_client_id or None,
                "entry_ownership_verified": entry_ownership_verified,
            })
            order_snapshot = {}
            if stop_order_id and hasattr(central_broker, "managed_order_snapshot"):
                try:
                    order_snapshot = central_broker.managed_order_snapshot(pos.get("symbol"), stop_order_id)
                except Exception as exc:
                    order_snapshot = {"ok": False, "status": "ORDER_SNAPSHOT_EXCEPTION", "error": str(exc), "read_only": True, "sent": False}
            elif not stop_order_id:
                order_snapshot = {"ok": False, "status": "ORDER_ID_MISSING", "read_only": True, "sent": False}
            else:
                order_snapshot = {"ok": False, "status": "ORDER_VERIFICATION_HELPER_MISSING", "read_only": True, "sent": False}
            result["order_snapshot"] = order_snapshot
            historical_order_snapshot = {}
            order_lookup_status = str((order_snapshot or {}).get("status") or "").upper().strip()
            if (
                stop_order_id
                and not (order_snapshot or {}).get("ok")
                and order_lookup_status == "ORDER_NOT_FOUND"
                and hasattr(central_broker, "managed_historical_order_snapshot")
            ):
                try:
                    historical_order_snapshot = central_broker.managed_historical_order_snapshot(
                        pos.get("symbol"),
                        stop_order_id,
                    )
                except Exception as exc:
                    historical_order_snapshot = {
                        "ok": False,
                        "status": "HISTORICAL_ORDER_SNAPSHOT_EXCEPTION",
                        "order_id": str(stop_order_id),
                        "error": _falcon_terminal_safe_text(exc),
                        "read_only": True,
                        "sent": False,
                    }
            result["historical_stop_order_snapshot"] = historical_order_snapshot
            order_status = str((order_snapshot or {}).get("status") or "UNKNOWN").upper().strip()
            actual_stop_order_id = str((order_snapshot or {}).get("order_id") or (order_snapshot or {}).get("id") or "").strip()
            expected_stop_client_id = str(
                pos.get("disaster_stop_client_order_id")
                or pos.get("broker_stop_client_order_id")
                or ""
            ).strip().upper()
            actual_stop_client_id = str(
                (order_snapshot or {}).get("client_order_id")
                or (order_snapshot or {}).get("clientOrderId")
                or (order_snapshot or {}).get("clientOrderID")
                or ""
            ).strip().upper()
            stop_client_order_id_match = bool(
                expected_stop_client_id
                and actual_stop_client_id
                and actual_stop_client_id == expected_stop_client_id
            )
            stop_order_identity_match = bool(
                stop_order_id not in (None, "")
                and actual_stop_order_id
                and actual_stop_order_id == str(stop_order_id).strip()
            )
            flags = _falcon_stop_status_flags(order_status, order_snapshot)
            filled_qty = safe_float((order_snapshot or {}).get("filled"), 0.0)
            fill_expected = safe_float(pos.get("broker_stop_amount"), remaining)
            terminal_stop_evidence = _falcon_protective_stop_evidence(
                order_snapshot,
                identity,
                expected_amount=remaining,
                reference_price=pos.get("entry"),
                creation_evidence=creation_stop_evidence,
                hedge_mode=creation_stop_evidence.get("hedge_mode_detected"),
                expected_stop_order_id=stop_order_id,
            )
            full_fill_confirmed = bool(
                flags["filled"]
                and result.get("entry_ownership_verified")
                and str((order_snapshot or {}).get("order_id") or (order_snapshot or {}).get("id") or "").strip() == str(stop_order_id or "").strip()
                and terminal_stop_evidence.get("protective")
                and filled_qty > 0
                and fill_expected is not None
                and fill_expected > 0
                and abs(filled_qty - fill_expected) <= max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, max(filled_qty, fill_expected) * 1e-6)
                and remaining > 0
                and abs(filled_qty - remaining) <= max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, max(filled_qty, remaining) * 1e-6)
            )
            result.update({
                "stop_order_status": order_status,
                "stop_order_identity_match": stop_order_identity_match,
                "stop_client_order_id_match": stop_client_order_id_match,
                "stop_order_client_id": actual_stop_client_id or None,
                "stop_order_active": flags["active"],
                "stop_order_filled": flags["filled"],
                "stop_order_full_fill_confirmed": full_fill_confirmed,
                "stop_order_triggered": flags["triggered"],
                "stop_order_cancelled": flags["cancelled"],
                "stop_order_rejected": flags["rejected"],
                "trigger_price": safe_float((order_snapshot or {}).get("stop_price"), result.get("trigger_price")),
                "trigger_type": (order_snapshot or {}).get("working_type"),
                "stop_order_type": (order_snapshot or {}).get("type"),
                "stop_side": (order_snapshot or {}).get("side") or result.get("stop_side"),
                "stop_position_side": (order_snapshot or {}).get("position_side"),
                "stop_reduce_only": _falcon_management_bool((order_snapshot or {}).get("reduce_only")),
                "stop_close_position": _falcon_management_bool((order_snapshot or {}).get("close_position")),
                "protected_qty": safe_float((order_snapshot or {}).get("remaining"), safe_float((order_snapshot or {}).get("amount"), None)),
                "terminal_stop_protective_evidence": terminal_stop_evidence,
            })
            if position_snapshot.get("position_closed") or position_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
                terminal_or_absent = bool(flags["filled"] or flags["cancelled"] or flags["rejected"] or _falcon_stop_not_found_evidence(order_snapshot))
                if terminal_or_absent:
                    manual_suspected = not full_fill_confirmed
                    result.update({
                        "ok": True,
                        "status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
                        "central_only_reconcile_required": True,
                        "management_allowed": False,
                        "stop_anomaly_detected": bool(not full_fill_confirmed or flags["cancelled"] or flags["rejected"]),
                        "stop_anomaly_reason": "BROKER_FLAT_STOP_NOT_FILLED" if manual_suspected else None,
                        "manual_user_close_suspected": manual_suspected,
                        "broker_stop_execution_suspected": bool(full_fill_confirmed),
                    })
                else:
                    result.update({
                        "status": "BROKER_FLAT_STOP_TERMINAL_STATE_UNCONFIRMED",
                        "management_allowed": False,
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": "BROKER_FLAT_WITH_ACTIVE_OR_UNKNOWN_STOP",
                        "manual_intervention_required": True,
                    })
            elif not position_snapshot.get("ownership_safe", True):
                result.update({"status": "POSITION_OWNERSHIP_UNSAFE", "stop_anomaly_detected": True, "stop_anomaly_reason": "POSITION_AMOUNT_MISMATCH"})
            elif not order_snapshot.get("ok"):
                order_error_status = str(order_snapshot.get("status") or "").upper().strip()
                not_found = order_error_status == "ORDER_ID_MISSING" or _falcon_stop_not_found_evidence(order_snapshot)
                result.update({
                    "status": "DISASTER_STOP_NOT_FOUND" if not_found else "STOP_ORDER_VERIFICATION_ERROR",
                    "stop_anomaly_detected": True,
                    "stop_anomaly_reason": "DISASTER_STOP_NOT_FOUND" if not_found else "STOP_ORDER_VERIFICATION_ERROR",
                    "failsafe_eligible": False,
                    "failsafe_block_reason": "LIFECYCLE_OWNERSHIP_NOT_PROVEN_BY_BROKER_POSITION_SNAPSHOT",
                    "manual_intervention_required": bool(not_found),
                })
            else:
                protected_qty = safe_float(result.get("protected_qty"), 0.0)
                quantity_match = bool(protected_qty > 0 and abs(protected_qty - position_qty) <= max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, max(protected_qty, position_qty) * 1e-6))
                result["protection_matches_position"] = quantity_match
                protective = _falcon_protective_stop_evidence(
                    order_snapshot,
                    identity,
                    expected_amount=position_qty,
                    reference_price=pos.get("entry"),
                    creation_evidence=creation_stop_evidence,
                    hedge_mode=creation_stop_evidence.get("hedge_mode_detected"),
                    expected_stop_order_id=stop_order_id,
                )
                protective_type = bool(protective.get("semantic_stop_valid"))
                quantity_match = bool(protective.get("quantity_covers_position"))
                if protected_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE and protective.get("full_close_confirmed"):
                    protected_qty = position_qty
                result["protected_qty"] = protected_qty
                result["protection_matches_position"] = quantity_match
                result["stop_order_protective_evidence"] = protective
                result["stop_order_protective_verified"] = protective_type
                result["semantic_stop_valid"] = protective_type
                result["stop_semantic_predicates"] = dict(protective.get("predicates") or {})
                result["stop_semantic_failure_reasons"] = list(protective.get("failure_reasons") or [])
                for diagnostic_name in (
                    "execution_type", "plan_type", "trigger_order_type",
                    "stop_loss_evidence_present", "take_profit_evidence_present",
                    "type_source_summary", "type_valid_reason",
                ):
                    result[diagnostic_name] = protective.get(diagnostic_name)
                for predicate_name in (
                    "type_valid", "symbol_matches", "close_side_matches", "position_side_matches",
                    "reduce_only_confirmed", "close_position_confirmed", "trigger_direction_valid",
                    "close_semantics_confirmed", "quantity_covers_position", "status_active", "semantic_stop_valid",
                ):
                    result[predicate_name] = protective.get(predicate_name)
                if (
                    flags["active"]
                    and stop_order_identity_match
                    and quantity_match
                    and protective_type
                    and result.get("entry_ownership_verified")
                    and result.get("client_order_id_reserved") is True
                    and result.get("client_order_id_unique") is True
                    and stop_client_order_id_match
                ):
                    result.update({
                        "ok": True,
                        "status": "DISASTER_STOP_ACTIVE_VERIFIED",
                        "management_allowed": True,
                        "stop_operationally_armed": True,
                    })
                elif not stop_client_order_id_match:
                    result.update({
                        "status": "DISASTER_STOP_CLIENT_ORDER_ID_MISMATCH",
                        "management_allowed": False,
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": "DISASTER_STOP_CLIENT_ORDER_ID_MISMATCH",
                    })
                elif result.get("client_order_id_reserved") is not True:
                    result.update({
                        "status": "DISASTER_STOP_CLIENT_ORDER_ID_RESERVATION_NOT_PROVEN",
                        "management_allowed": False,
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": "DISASTER_STOP_CLIENT_ORDER_ID_RESERVATION_NOT_PROVEN",
                    })
                elif result.get("client_order_id_unique") is not True:
                    result.update({
                        "status": "DISASTER_STOP_CLIENT_ORDER_ID_UNIQUENESS_NOT_PROVEN",
                        "management_allowed": False,
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": "DISASTER_STOP_CLIENT_ORDER_ID_UNIQUENESS_NOT_PROVEN",
                    })
                elif flags["cancelled"] or flags["rejected"] or flags["filled"] or flags["triggered"]:
                    result.update({
                        "status": "DISASTER_STOP_INACTIVE_WITH_POSITION_OPEN",
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": f"STOP_{order_status}_POSITION_STILL_OPEN",
                        "failsafe_eligible": False,
                        "failsafe_block_reason": "LIFECYCLE_OWNERSHIP_NOT_PROVEN_BY_BROKER_POSITION_SNAPSHOT",
                        "manual_intervention_required": True,
                    })
                elif flags["active"] and not quantity_match:
                    result.update({"status": "DISASTER_STOP_QUANTITY_MISMATCH", "stop_anomaly_detected": True, "stop_anomaly_reason": "PROTECTION_QUANTITY_MISMATCH"})
                elif flags["active"] and not stop_order_identity_match:
                    result.update({"status": "DISASTER_STOP_IDENTITY_MISMATCH", "stop_anomaly_detected": True, "stop_anomaly_reason": "STOP_ORDER_IDENTITY_MISMATCH"})
                elif flags["active"] and not protective_type:
                    result.update({
                        "status": "DISASTER_STOP_EVIDENCE_INSUFFICIENT",
                        "stop_anomaly_detected": True,
                        "stop_anomaly_reason": "STOP_TYPE_SIDE_OR_CLOSE_SEMANTICS_NOT_CONFIRMED",
                        "stop_anomaly_details": list(protective.get("failure_reasons") or []),
                    })
                elif flags["active"] and not result.get("entry_ownership_verified"):
                    result.update({"status": "ENTRY_LIFECYCLE_OWNERSHIP_NOT_CONFIRMED", "stop_anomaly_detected": True, "stop_anomaly_reason": "ENTRY_ORDER_FILL_IDENTITY_NOT_CONFIRMED"})
                else:
                    result.update({"status": "DISASTER_STOP_STATUS_UNKNOWN", "stop_anomaly_detected": True, "stop_anomaly_reason": "DISASTER_STOP_STATUS_UNKNOWN"})

    result["cached"] = False
    pos["stop_order_id"] = result.get("stop_order_id")
    pos["stop_order_status"] = result.get("stop_order_status")
    pos["stop_order_trigger_type"] = result.get("trigger_type")
    pos["stop_order_type"] = result.get("stop_order_type")
    pos["stop_order_side"] = result.get("stop_side")
    pos["stop_position_side"] = result.get("stop_position_side")
    pos["stop_reduce_only"] = result.get("stop_reduce_only")
    pos["stop_close_position"] = result.get("stop_close_position")
    pos["stop_order_active"] = result.get("stop_order_active")
    pos["stop_order_filled"] = result.get("stop_order_filled")
    pos["stop_order_full_fill_confirmed"] = result.get("stop_order_full_fill_confirmed")
    pos["stop_order_cancelled"] = result.get("stop_order_cancelled")
    pos["stop_order_rejected"] = result.get("stop_order_rejected")
    pos["stop_order_last_checked_at"] = result.get("stop_order_last_checked_at")
    pos["stop_order_last_checked_epoch"] = now_epoch
    pos["protected_qty"] = result.get("protected_qty")
    pos["position_qty"] = result.get("position_qty")
    pos["protection_matches_position"] = result.get("protection_matches_position")
    pos["entry_ownership_verified"] = result.get("entry_ownership_verified")
    pos["semantic_stop_valid"] = result.get("semantic_stop_valid")
    pos["stop_execution_type"] = result.get("execution_type")
    pos["stop_plan_type"] = result.get("plan_type")
    pos["stop_trigger_order_type"] = result.get("trigger_order_type")
    pos["stop_loss_evidence_present"] = result.get("stop_loss_evidence_present")
    pos["take_profit_evidence_present"] = result.get("take_profit_evidence_present")
    pos["stop_type_source_summary"] = list(result.get("type_source_summary") or [])
    pos["stop_type_valid_reason"] = result.get("type_valid_reason")
    pos["stop_semantic_predicates"] = dict(result.get("stop_semantic_predicates") or {})
    pos["stop_semantic_failure_reasons"] = list(result.get("stop_semantic_failure_reasons") or [])
    pos["disaster_stop_active_verified"] = bool(
        result.get("stop_order_active")
        and result.get("stop_order_identity_match")
        and result.get("protection_matches_position")
        and result.get("stop_order_protective_verified")
        and result.get("entry_ownership_verified")
        and result.get("client_order_id_unique") is True
    )
    pos["stop_anomaly_detected"] = result.get("stop_anomaly_detected")
    pos["stop_anomaly_last_reason"] = result.get("stop_anomaly_reason")
    pos["central_only_reconcile_required"] = bool(result.get("central_only_reconcile_required"))
    pos["live_management_block_reason"] = None if result.get("management_allowed") else result.get("status")
    if result.get("central_only_reconcile_required"):
        pos["central_only_evidence"] = {
            "status": "CENTRAL_ONLY_RECONCILE_REQUIRED",
            "broker_flat": True,
            "position_closed": True,
            "position_qty": result.get("position_qty"),
            "matched_count": (result.get("position_snapshot") or {}).get("matched_count"),
            "read_only": True,
            "sent": False,
            "checked_at": now_text,
            "checked_epoch": now_epoch,
            "symbol": identity.get("symbol"),
            "side": identity.get("side"),
            "trade_id": identity.get("trade_id"),
            "lifecycle_id": identity.get("lifecycle_id"),
            "order_id": identity.get("order_id"),
            "client_order_id": identity.get("client_order_id"),
            "stop_order_id": result.get("stop_order_id"),
            "stop_order_status": result.get("stop_order_status"),
            "stop_order_active": result.get("stop_order_active"),
            "stop_order_filled": result.get("stop_order_filled"),
            "stop_order_full_fill_confirmed": result.get("stop_order_full_fill_confirmed"),
            "stop_order_cancelled": result.get("stop_order_cancelled"),
            "stop_order_rejected": result.get("stop_order_rejected"),
            "stop_order_type": result.get("stop_order_type"),
            "stop_position_side": result.get("stop_position_side"),
            "stop_reduce_only": result.get("stop_reduce_only"),
            "stop_close_position": result.get("stop_close_position"),
            "trigger_price": result.get("trigger_price"),
            "trigger_type": result.get("trigger_type"),
            "manual_user_close_suspected": result.get("manual_user_close_suspected"),
            "stop_anomaly_suspected": result.get("stop_anomaly_detected"),
            "stop_order_average": (result.get("order_snapshot") or {}).get("average"),
            "stop_order_filled_qty": (result.get("order_snapshot") or {}).get("filled"),
            "stop_order_timestamp": (result.get("order_snapshot") or {}).get("timestamp"),
        }
    else:
        pos.pop("central_only_evidence", None)
    previous_signature = str(pos.get("stop_verification_signature") or "")
    signature = "|".join(str(result.get(key)) for key in (
        "status", "stop_order_status", "stop_order_active", "stop_order_filled",
        "stop_order_cancelled", "stop_order_rejected", "position_qty", "protected_qty",
        "protection_matches_position", "semantic_stop_valid", "entry_ownership_verified", "central_only_reconcile_required",
    ))
    pos["stop_verification_signature"] = signature
    pos["live_stop_verification"] = dict(result)
    last_persisted = safe_float(pos.get("stop_verification_persisted_epoch"), 0.0)
    should_persist = bool(persist_registry and (signature != previous_signature or now_epoch - last_persisted >= FALCON_STOP_VERIFY_PERSIST_SECONDS))
    if should_persist:
        falcon_update_registry_management(
            pos,
            stop_verification={key: result.get(key) for key in (
                "status", "stop_order_id", "trigger_price", "trigger_type", "stop_order_type", "stop_side",
                "stop_position_side", "stop_reduce_only", "stop_close_position", "entry_order_id", "entry_order_status",
                "entry_order_filled_qty", "entry_ownership_verified", "stop_order_status", "stop_order_identity_match", "stop_order_active",
                "stop_order_filled", "stop_order_full_fill_confirmed", "stop_order_triggered", "stop_order_cancelled",
                "stop_order_rejected", "stop_order_last_checked_at", "protected_qty", "position_qty",
                "protection_matches_position", "stop_order_protective_verified", "stop_anomaly_detected", "stop_anomaly_reason",
                "semantic_stop_valid", "stop_semantic_predicates", "stop_semantic_failure_reasons",
                "execution_type", "plan_type", "trigger_order_type",
                "stop_loss_evidence_present", "take_profit_evidence_present",
                "type_source_summary", "type_valid_reason",
                "type_valid", "symbol_matches", "close_side_matches", "position_side_matches",
                "reduce_only_confirmed", "close_position_confirmed", "trigger_direction_valid",
                "close_semantics_confirmed", "quantity_covers_position", "status_active",
                "central_only_reconcile_required", "read_only", "sent",
            )},
            central_only_evidence=pos.get("central_only_evidence"),
            disaster_stop_active_verified=pos.get("disaster_stop_active_verified"),
            stop_anomaly_detected=pos.get("stop_anomaly_detected"),
            stop_anomaly_last_reason=pos.get("stop_anomaly_last_reason"),
        )
        pos["stop_verification_persisted_epoch"] = now_epoch
    _falcon_update_stop_health(result)
    return result


FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION = "2026-07-20-FALCON-TERMINAL-STOP-EMERGENCY-RECOVERY-V1"
FALCON_TERMINAL_STOP_STATUSES = {"FAILED", "REJECTED", "EXPIRED", "CANCELED", "CANCELLED"}
FALCON_TERMINAL_STOP_UNRESOLVED_STATES = {
    "RESERVED",
    "SEND_ATTEMPTED",
    "BROKER_CALL_PENDING",
    "LIFECYCLE_LOCK_BLOCKED",
    "SEND_OUTCOME_UNKNOWN",
    "SENT_UNCONFIRMED",
    "CONFIRMED",
}


def _falcon_terminal_safe_text(value, limit=240):
    if value in (None, ""):
        return None
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    lowered = text.lower()
    if any(token in lowered for token in (
        "api_key", "apikey", "secret", "signature=", "authorization", "bearer ",
        "token=", "token:", "access_token", "password", "credential", "cookie:",
        "x-amz-signature", "sig=", "c:\\", "c:/", "/data/", "/home/", "/var/", "/opt/",
    )):
        return "REDACTED_SENSITIVE_VALUE"
    return text[:max(1, int(limit))]


def _falcon_terminal_registry_field(record, *names):
    record = record if isinstance(record, dict) else {}
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
        value = metadata.get(name)
        if value not in (None, ""):
            return value
    return None


def _falcon_terminal_bool(value):
    parsed = _falcon_management_bool(value)
    return bool(parsed is True)


def falcon_terminal_stop_incident_id(pos, verification=None):
    pos = pos if isinstance(pos, dict) else {}
    verification = verification if isinstance(verification, dict) else {}
    identity = verification.get("identity") if isinstance(verification.get("identity"), dict) else falcon_position_identity(pos)
    stop_order_id = verification.get("stop_order_id") or pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
    components = [
        identity.get("lifecycle_id"), identity.get("client_order_id"), identity.get("order_id"),
        stop_order_id, identity.get("symbol") or pos.get("symbol"), identity.get("side") or pos.get("side"),
    ]
    if not any(value not in (None, "") for value in components):
        return None
    digest = hashlib.sha256("|".join(str(value or "") for value in components).encode("utf-8")).hexdigest()
    return f"FALCON-TERMINAL-STOP-{digest[:32]}"


def falcon_terminal_stop_client_tag(incident_id):
    # Compatibilidade para readers legados. O writer operacional usa a
    # identidade completa em ``falcon_generate_position_client_order_id``.
    digest = hashlib.sha256(str(incident_id or "").encode("utf-8")).hexdigest().upper()
    return f"FEC1-{digest[:24]}"


def _falcon_terminal_sanitize_projection(value):
    """Recursively remove authentication material from durable/public evidence."""
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            normalized = str(key or "").lower().replace("-", "_")
            safe_authority_projection = normalized in {
                "client_order_id_retry_authorization",
                "retry_authorization_status",
            }
            sensitive = (
                any(fragment in normalized for fragment in (
                    "authorization", "api_key", "apikey", "signature", "cookie",
                    "secret", "header", "password", "credential", "nonce",
                ))
                and not safe_authority_projection
            ) or normalized in {"context", "raw_context"} or (
                "token" in normalized and normalized != "token_present"
            )
            if sensitive:
                continue
            clean[str(key)] = _falcon_terminal_sanitize_projection(item)
        return clean
    if isinstance(value, (list, tuple)):
        return [_falcon_terminal_sanitize_projection(item) for item in list(value)[:100]]
    if isinstance(value, str):
        return _falcon_terminal_safe_text(value, 500)
    return value


def falcon_terminal_stop_recovery_key(incident_id):
    incident_id = str(incident_id or "").strip()
    return f"{FALCON_TERMINAL_STOP_RECOVERY_KEY}:incident:{incident_id}" if incident_id else None


def falcon_terminal_stop_recovery_load(incident_id):
    """Read exactly one incident from Redis, bypassing every local cache."""
    key = falcon_terminal_stop_recovery_key(incident_id)
    if not key:
        return {"ok": False, "incident": {}, "source": "IDENTITY_REQUIRED"}
    try:
        with redis_lock:
            raw = bandwidth_redis_get_authoritative(redis, key, caller=__name__)
        if raw is None:
            return {"ok": True, "incident": {}, "source": "EMPTY", "key": key}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(payload, dict) or not isinstance(payload.get("incident"), dict):
            raise ValueError("terminal stop incident payload is missing or invalid")
        if str(payload.get("incident_id") or "") != str(incident_id):
            raise ValueError("terminal stop incident identity mismatch")
        return {
            "ok": True,
            "incident": dict(payload.get("incident") or {}),
            "source": "PERSISTED",
            "key": key,
        }
    except Exception as exc:
        return {
            "ok": False,
            "incident": {},
            "source": "READ_ERROR",
            "key": key,
            "error": _falcon_terminal_safe_text(exc),
        }


def falcon_terminal_stop_recovery_save(incident_id, incident_state):
    """Persist one incident key without a global read-modify-write ledger."""
    key = falcon_terminal_stop_recovery_key(incident_id)
    if not key or not isinstance(incident_state, dict):
        return {"ok": False, "status": "INCIDENT_PERSISTENCE_IDENTITY_REQUIRED"}
    try:
        clean_state = _falcon_terminal_sanitize_projection(dict(incident_state))
        payload = {
            "version": FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION,
            "incident_id": str(incident_id),
            "updated_at": data_hora_sp_str(),
            "incident": clean_state,
        }
        with redis_lock:
            write_result = bandwidth_redis_set(
                redis,
                key,
                json.dumps(payload, ensure_ascii=False),
                caller=__name__,
            )
        if write_result in (None, False):
            raise OSError("terminal stop incident persistence was not acknowledged")
        return {"ok": True, "status": "INCIDENT_PERSISTED", "key": key}
    except Exception as exc:
        return {"ok": False, "status": "INCIDENT_PERSISTENCE_ERROR", "error": _falcon_terminal_safe_text(exc)}


def falcon_terminal_stop_lifecycle_lock_id(pos):
    identity = falcon_position_identity(pos if isinstance(pos, dict) else {})
    components = (
        "FALCON",
        identity.get("lifecycle_id"),
        identity.get("client_order_id"),
        identity.get("order_id"),
        identity.get("symbol"),
        identity.get("side"),
    )
    if any(value in (None, "") for value in components):
        return None
    digest = hashlib.sha256("|".join(str(value) for value in components).encode("utf-8")).hexdigest()
    return f"FALCON-LIFECYCLE-{digest[:40]}"


def falcon_terminal_stop_acquire_lifecycle_lock(lifecycle_lock_id, owner_nonce):
    """Atomically reserve the whole lifecycle, independently of stop order ID."""
    if not lifecycle_lock_id or not owner_nonce:
        return {"ok": False, "acquired": False, "status": "LIFECYCLE_LOCK_IDENTITY_REQUIRED"}
    lock_key = f"{FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX}:{lifecycle_lock_id}"
    try:
        with redis_lock:
            result = bandwidth_redis_set_if_absent(
                redis, lock_key, str(owner_nonce), caller=__name__,
            )
            if result in (None, False):
                existing = bandwidth_redis_get_authoritative(redis, lock_key, caller=__name__)
            else:
                existing = None
        acquired = bool(result not in (None, False))
        return {
            "ok": acquired,
            "acquired": acquired,
            "status": "LIFECYCLE_LOCK_ACQUIRED" if acquired else "LIFECYCLE_LOCK_ALREADY_EXISTS",
            "lock_key": lock_key,
            "authoritative_lock_present": bool(existing not in (None, b"", "")) if not acquired else True,
        }
    except Exception as exc:
        return {
            "ok": False,
            "acquired": False,
            "status": "LIFECYCLE_LOCK_ERROR",
            "lock_key": lock_key,
            "error": _falcon_terminal_safe_text(exc),
        }


def falcon_terminal_stop_release_lifecycle_lock(lifecycle_lock_id, owner_nonce):
    """Atomically compare owner nonce and delete; never GET then DELETE."""
    if not lifecycle_lock_id or not owner_nonce:
        return {"ok": False, "released": False, "status": "LIFECYCLE_LOCK_IDENTITY_REQUIRED"}
    lock_key = f"{FALCON_TERMINAL_STOP_LIFECYCLE_LOCK_PREFIX}:{lifecycle_lock_id}"
    try:
        with redis_lock:
            released = bandwidth_redis_compare_and_delete(
                redis, lock_key, str(owner_nonce), caller=__name__,
            )
        return {
            "ok": bool(released),
            "released": bool(released),
            "status": "LIFECYCLE_LOCK_RELEASED" if released else "LIFECYCLE_LOCK_OWNERSHIP_MISMATCH",
        }
    except Exception as exc:
        return {
            "ok": False,
            "released": False,
            "status": "LIFECYCLE_LOCK_RELEASE_ERROR",
            "error": _falcon_terminal_safe_text(exc),
        }


def _falcon_terminal_registry_evidence(pos, registry_snapshot=None):
    """Resolve one open Falcon LIVE/REAL row by lifecycle, never by symbol/side."""
    pos = pos if isinstance(pos, dict) else {}
    identity = falcon_position_identity(pos)
    if registry_snapshot is None:
        if central_trade_registry is None or not hasattr(central_trade_registry, "load_registry_read_only"):
            return {"ok": False, "status": "REGISTRY_READ_ONLY_HELPER_MISSING", "matches": [], "same_leg_other_records": []}
        try:
            registry_snapshot = central_trade_registry.load_registry_read_only()
        except Exception as exc:
            return {
                "ok": False,
                "status": "REGISTRY_READ_ERROR",
                "error": _falcon_terminal_safe_text(exc),
                "matches": [],
                "same_leg_other_records": [],
            }
    open_value = registry_snapshot.get("open_trades", {}) if isinstance(registry_snapshot, dict) else {}
    open_rows = list(open_value.values()) if isinstance(open_value, dict) else list(open_value or [])
    open_rows = [row for row in open_rows if isinstance(row, dict)]
    lifecycle_id = str(identity.get("lifecycle_id") or "").strip()

    def is_falcon_live_real(row):
        bot = str(_falcon_terminal_registry_field(row, "bot") or "").upper().strip()
        execution_mode = str(_falcon_terminal_registry_field(row, "execution_mode", "mode") or "").upper().strip()
        registry_mode = str(_falcon_terminal_registry_field(row, "registry_mode") or "").upper().strip()
        return bool(bot == "FALCON" and execution_mode == "LIVE" and registry_mode == "REAL")

    falcon_live_rows = [row for row in open_rows if is_falcon_live_real(row)]
    all_lifecycle_records = [
        row for row in open_rows
        if lifecycle_id and str(_falcon_terminal_registry_field(row, "lifecycle_id") or "").strip() == lifecycle_id
    ]
    matches = [
        row for row in falcon_live_rows
        if lifecycle_id and str(_falcon_terminal_registry_field(row, "lifecycle_id") or "").strip() == lifecycle_id
    ]
    wanted_symbol = _falcon_management_norm_symbol(identity.get("symbol"))
    wanted_side = _falcon_management_norm_side(identity.get("side"))
    same_leg_other_records = []
    ignored_same_leg_records = []
    virtual_modes = {"PAPER", "VERIFY", "PREVIEW", "SIGNAL_ONLY", "VIRTUAL", "ADVISORY", "CONSULTATIVE"}
    for row in open_rows:
        symbol = _falcon_management_norm_symbol(_falcon_terminal_registry_field(row, "symbol"))
        side = _falcon_management_norm_side(_falcon_terminal_registry_field(row, "side"))
        row_lifecycle = str(_falcon_terminal_registry_field(row, "lifecycle_id") or "").strip()
        if symbol != wanted_symbol or side != wanted_side or row in matches:
            continue
        bot = str(_falcon_terminal_registry_field(row, "bot") or "").upper().strip()
        execution_mode = str(_falcon_terminal_registry_field(row, "execution_mode", "mode") or "").upper().strip()
        registry_mode = str(_falcon_terminal_registry_field(row, "registry_mode") or "").upper().strip()
        ownership = str(_falcon_terminal_registry_field(row, "ownership", "owner_type") or "").upper().strip()
        source = str(_falcon_terminal_registry_field(row, "position_source", "source") or "").upper().strip()
        manual_or_external = bool(
            bot in {"MANUAL", "EXTERNAL"}
            or ownership in {"MANUAL", "EXTERNAL"}
            or _falcon_terminal_bool(_falcon_terminal_registry_field(row, "external_position"))
            or _falcon_terminal_bool(_falcon_terminal_registry_field(row, "manual_position"))
        )
        explicit_real_external = bool(
            _falcon_terminal_bool(_falcon_terminal_registry_field(row, "external_real_exposure"))
            or _falcon_terminal_bool(_falcon_terminal_registry_field(row, "broker_position_confirmed"))
            or _falcon_terminal_bool(_falcon_terminal_registry_field(row, "real_position_confirmed"))
            or source in {"BROKER_EXTERNAL_POSITION", "MANUAL_BROKER_POSITION", "EXTERNAL_BROKER_POSITION"}
        )
        other_live_real = bool(execution_mode == "LIVE" and registry_mode == "REAL" and row_lifecycle != lifecycle_id)
        virtual_or_advisory = bool(execution_mode in virtual_modes or registry_mode in virtual_modes)
        conflict_reason = None
        if manual_or_external:
            conflict_reason = "MANUAL_OR_EXTERNAL_SAME_LEG"
        elif explicit_real_external:
            conflict_reason = "FACTUAL_EXTERNAL_REAL_EXPOSURE_SAME_LEG"
        elif other_live_real:
            conflict_reason = "OTHER_LIVE_REAL_LIFECYCLE_SAME_LEG"

        projection = {
            "bot": _falcon_terminal_safe_text(bot, 40),
            "lifecycle_id": _falcon_terminal_safe_text(row_lifecycle, 160),
            "trade_id": _falcon_terminal_safe_text(_falcon_terminal_registry_field(row, "trade_id"), 160),
            "execution_mode": _falcon_terminal_safe_text(execution_mode, 32),
            "registry_mode": _falcon_terminal_safe_text(registry_mode, 32),
            "ownership": _falcon_terminal_safe_text(ownership, 40),
            "source": _falcon_terminal_safe_text(source, 80),
            "conflict_reason": conflict_reason,
        }
        if conflict_reason:
            same_leg_other_records.append(projection)
        else:
            projection["ignored_reason"] = (
                "VIRTUAL_OR_ADVISORY_MODE" if virtual_or_advisory
                else "NO_FACTUAL_REAL_EXTERNAL_EXPOSURE"
            )
            ignored_same_leg_records.append(projection)
    return {
        "ok": bool(isinstance(registry_snapshot, dict)),
        "status": "REGISTRY_LIFECYCLE_MATCHED" if len(matches) == 1 else "REGISTRY_LIFECYCLE_MATCH_COUNT_INVALID",
        "open_count": len(open_rows),
        "falcon_live_real_count": len(falcon_live_rows),
        "all_lifecycle_match_count": len(matches),
        "all_lifecycle_record_count": len(all_lifecycle_records),
        "lifecycle_match_count": len(matches),
        "matches": matches,
        "same_leg_other_records": same_leg_other_records,
        "ignored_same_leg_records": ignored_same_leg_records,
    }


def _falcon_terminal_stop_facts(pos, verification):
    pos = pos if isinstance(pos, dict) else {}
    verification = verification if isinstance(verification, dict) else {}
    order = verification.get("order_snapshot") if isinstance(verification.get("order_snapshot"), dict) else {}
    historical = verification.get("historical_stop_order_snapshot") if isinstance(verification.get("historical_stop_order_snapshot"), dict) else {}
    expected_stop_id = str(verification.get("stop_order_id") or pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id") or "").strip()
    actual_stop_id = str(order.get("order_id") or order.get("id") or "").strip()
    raw_status = str(order.get("raw_status") or "").upper().strip()
    unified_status = str(order.get("status") or verification.get("stop_order_status") or "UNKNOWN").upper().strip()
    factual_status = raw_status or unified_status
    source = "EXACT_ORDER_SNAPSHOT"
    historical_terminal_found = False
    if not order.get("ok") and unified_status == "ORDER_NOT_FOUND":
        historical_id = str(historical.get("order_id") or historical.get("id") or "").strip()
        historical_raw = str(historical.get("raw_status") or "").upper().strip()
        historical_status = historical_raw or str(historical.get("status") or "").upper().strip()
        if (
            historical.get("ok") is True
            and historical.get("historical") is True
            and historical_id == expected_stop_id
            and str(historical.get("requested_order_id") or "").strip() == expected_stop_id
            and historical_status in FALCON_TERMINAL_STOP_STATUSES
        ):
            order = historical
            actual_stop_id = historical_id
            raw_status = historical_raw
            unified_status = str(historical.get("status") or historical_status).upper().strip()
            factual_status = historical_status
            historical_terminal_found = True
            source = "EXACT_HISTORICAL_TERMINAL_ORDER"
    filled = safe_float(
        order.get("executed_quantity")
        if "executed_quantity" in order
        else order.get("filled"),
        None,
    )
    remaining = safe_float(
        order.get("remaining_quantity")
        if "remaining_quantity" in order
        else order.get("remaining"),
        None,
    )
    identity = falcon_position_identity(pos)
    creation = _falcon_stop_creation_evidence(pos, identity, expected_stop_id)
    stop_symbol = order.get("symbol") or creation.get("symbol")
    stop_side = order.get("side") or creation.get("side")
    stop_position_side = order.get("position_side") or creation.get("position_side")
    stop_reduce_only = _falcon_management_bool(
        order.get("reduce_only")
        if order.get("reduce_only") is not None
        else creation.get("reduce_only")
    )
    stop_close_position = _falcon_management_bool(
        order.get("close_position")
        if order.get("close_position") is not None
        else creation.get("close_position")
    )
    stop_hedge_mode = _falcon_management_bool(creation.get("hedge_mode_detected"))
    fills_value = order.get("fills") if isinstance(order.get("fills"), list) else []
    sanitized_fills = []
    for fill in fills_value[:20]:
        if not isinstance(fill, dict):
            continue
        sanitized_fills.append({
            "fill_id": _falcon_terminal_safe_text(fill.get("id") or fill.get("fill_id"), 120),
            "order_id": _falcon_terminal_safe_text(fill.get("order_id") or fill.get("orderId"), 120),
            "amount": safe_float(fill.get("amount") or fill.get("qty") or fill.get("quantity"), None),
            "price": safe_float(fill.get("price"), None),
        })
    return {
        "expected_stop_order_id": expected_stop_id or None,
        "actual_stop_order_id": actual_stop_id or None,
        "order_identity_exact": bool(expected_stop_id and actual_stop_id == expected_stop_id),
        "raw_status": raw_status or None,
        "unified_status": unified_status or None,
        "terminal_status": factual_status or None,
        "terminal_factual": bool(
            factual_status in FALCON_TERMINAL_STOP_STATUSES
            and ((order.get("ok") and actual_stop_id == expected_stop_id) or historical_terminal_found)
        ),
        "historical_terminal_found": historical_terminal_found,
        "source": source,
        "read_only": order.get("read_only") is True,
        "symbol": _falcon_management_norm_symbol(stop_symbol),
        "side": str(stop_side or "").upper().strip() or None,
        "position_side": _falcon_management_norm_side(stop_position_side),
        "reduce_only": stop_reduce_only,
        "close_position": stop_close_position,
        "hedge_mode_detected": stop_hedge_mode,
        "creation_identity_eligible": creation.get("eligible") is True,
        "executed_quantity": filled,
        "remaining_quantity": remaining,
        "failure_code": _falcon_terminal_safe_text(order.get("failure_code") or order.get("error_code") or order.get("code")),
        "failure_reason": _falcon_terminal_safe_text(order.get("failure_reason") or order.get("error_message") or order.get("message")),
        "derived_order_id": _falcon_terminal_safe_text(order.get("derived_order_id") or order.get("triggered_order_id"), 120),
        "fills": sanitized_fills,
        "fills_count": len(fills_value),
    }


def _falcon_terminal_replacement_evidence(pos, verification, terminal_stop):
    pos = pos if isinstance(pos, dict) else {}
    verification = verification if isinstance(verification, dict) else {}
    terminal_stop = terminal_stop if isinstance(terminal_stop, dict) else {}
    expected_stop_id = str(terminal_stop.get("expected_stop_order_id") or "").strip()
    current_stop_id = str(
        pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id") or ""
    ).strip()
    replacement_in_progress = any(
        _falcon_terminal_bool(pos.get(name)) or _falcon_terminal_bool(verification.get(name))
        for name in (
            "stop_replacement_in_progress", "stop_replace_in_progress",
            "position_stop_replacement_in_progress", "stop_mutation_in_progress",
        )
    )
    candidates = []
    for source_name, value in (
        ("replacement_stop_snapshot", verification.get("replacement_stop_snapshot")),
        ("active_replacement_stop", verification.get("active_replacement_stop")),
        ("current_protective_order", verification.get("current_protective_order")),
        ("stop_update", pos.get("stop_update")),
        ("stop_resize", pos.get("stop_resize")),
    ):
        if not isinstance(value, dict):
            continue
        order_id = str(value.get("order_id") or value.get("new_order_id") or value.get("id") or "").strip()
        status = str(value.get("raw_status") or value.get("status") or "").upper().strip()
        active = bool(
            (value.get("ok") is True or value.get("blocking") is True)
            and order_id
            and order_id != expected_stop_id
            and status in {"OPEN", "ACTIVE", "NEW", "PENDING", "TRIGGER_PENDING", "ACCEPTED"}
        )
        candidates.append({
            "source": source_name,
            "order_id": _falcon_terminal_safe_text(order_id, 120),
            "status": _falcon_terminal_safe_text(status, 40),
            "active": active,
        })
    active_replacements = [item for item in candidates if item.get("active")]
    return {
        "replacement_in_progress": replacement_in_progress,
        "current_stop_order_id": current_stop_id or None,
        "expected_terminal_stop_order_id": expected_stop_id or None,
        "stop_id_changed": bool(expected_stop_id and current_stop_id and current_stop_id != expected_stop_id),
        "active_replacement_present": bool(active_replacements),
        "active_replacements": active_replacements,
    }


def _falcon_terminal_active_replacement_orders(pos, open_orders_snapshot, terminal_stop):
    """Conservatively identify an active protective replacement on the same leg."""
    pos = pos if isinstance(pos, dict) else {}
    snapshot = open_orders_snapshot if isinstance(open_orders_snapshot, dict) else {}
    terminal_stop = terminal_stop if isinstance(terminal_stop, dict) else {}
    identity = falcon_position_identity(pos)
    original_stop_id = str(terminal_stop.get("expected_stop_order_id") or "").strip()
    expected_side = "SELL" if identity.get("side") == "LONG" else "BUY"
    expected_qty = falcon_real_remaining_qty(pos)
    tolerance = max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, abs(expected_qty or 0.0) * 1e-6)
    candidates = []
    for order in snapshot.get("orders") if isinstance(snapshot.get("orders"), list) else []:
        if not isinstance(order, dict):
            continue
        order_id = str(order.get("order_id") or order.get("id") or "").strip()
        status = str(order.get("raw_status") or order.get("status") or "").upper().strip()
        type_text = "|".join(str(order.get(name) or "").upper() for name in (
            "type", "execution_type", "order_type", "plan_type", "trigger_order_type",
        ))
        stop_evidence = bool(
            "STOP" in type_text
            or order.get("stop_loss_price") not in (None, "")
            or order.get("stop_price") not in (None, "")
        )
        take_profit_evidence = bool(
            "TAKE_PROFIT" in type_text
            or "TAKEPROFIT" in type_text
            or order.get("take_profit_price") not in (None, "")
        )
        qty = safe_float(
            order.get("remaining_quantity")
            if order.get("remaining_quantity") not in (None, "")
            else order.get("remaining")
            if order.get("remaining") not in (None, "")
            else order.get("amount"),
            None,
        )
        quantity_covers = bool(
            _falcon_terminal_bool(order.get("close_position"))
            or (qty is not None and expected_qty > 0 and qty + tolerance >= expected_qty)
        )
        position_side = _falcon_management_norm_side(order.get("position_side"))
        reduce_only = _falcon_terminal_bool(order.get("reduce_only"))
        close_position = _falcon_terminal_bool(order.get("close_position"))
        hedge_mode = terminal_stop.get("hedge_mode_detected")
        position_side_matches = bool(
            position_side == identity.get("side")
            if hedge_mode is True
            else (
                position_side in (None, "", "BOTH")
                and (reduce_only or close_position)
            )
        )
        same_leg_stop_order = bool(
            order_id
            and order_id != original_stop_id
            and status in {"OPEN", "ACTIVE", "NEW", "PENDING", "TRIGGER_PENDING", "ACCEPTED"}
            and _falcon_management_norm_symbol(order.get("symbol")) == identity.get("symbol")
            and str(order.get("side") or "").upper().strip() == expected_side
            and stop_evidence
            and not take_profit_evidence
        )
        if same_leg_stop_order:
            strict_valid = bool(position_side_matches and quantity_covers)
            candidates.append({
                "ok": strict_valid,
                "blocking": True,
                "strict_valid": strict_valid,
                "ambiguous": not strict_valid,
                "order_id": _falcon_terminal_safe_text(order_id, 120),
                "status": _falcon_terminal_safe_text(status, 40),
                "raw_status": _falcon_terminal_safe_text(order.get("raw_status"), 40),
                "symbol": identity.get("symbol"),
                "side": expected_side,
                "position_side": position_side,
                "reduce_only": reduce_only,
                "close_position": close_position,
                "quantity_covers_position": quantity_covers,
                "position_side_matches": position_side_matches,
                "amount": qty,
                "source": "BROKER_OPEN_ORDERS_AFTER_LIFECYCLE_LOCK",
            })
    return candidates


def falcon_terminal_stop_emergency_decision(
    pos,
    verification,
    registry_snapshot=None,
    existing_recovery=None,
    related_lifecycle_recoveries=None,
):
    """Pure fail-closed authorization decision for the terminal-stop-only path."""
    pos = pos if isinstance(pos, dict) else {}
    verification = verification if isinstance(verification, dict) else {}
    existing_recovery = existing_recovery if isinstance(existing_recovery, dict) else {}
    related_lifecycle_recoveries = (
        related_lifecycle_recoveries
        if isinstance(related_lifecycle_recoveries, list)
        else []
    )
    identity = falcon_position_identity(pos)
    registry = _falcon_terminal_registry_evidence(pos, registry_snapshot=registry_snapshot)
    stop = _falcon_terminal_stop_facts(pos, verification)
    replacement = _falcon_terminal_replacement_evidence(pos, verification, stop)
    position = verification.get("position_snapshot") if isinstance(verification.get("position_snapshot"), dict) else {}
    entry = verification.get("entry_order_snapshot") if isinstance(verification.get("entry_order_snapshot"), dict) else {}
    expected_qty = falcon_real_remaining_qty(pos)
    broker_qty = safe_float(position.get("amount"), None)
    tolerance = max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, abs(expected_qty or 0.0) * 1e-6)
    reasons = []

    if verification.get("cached") is not False:
        reasons.append("FRESH_STOP_VERIFICATION_REQUIRED")
    if expected_qty is None or expected_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
        reasons.append("FALCON_REMAINING_QUANTITY_REQUIRED")
    if not FALCON_MANAGEMENT_FAILSAFE_ENABLED:
        reasons.append("TERMINAL_STOP_EMERGENCY_FAILSAFE_DISABLED")
    if central_broker is None or not hasattr(central_broker, "managed_close_position_market"):
        reasons.append("MANAGED_CLOSE_HELPER_REQUIRED")
    if not falcon_is_live_real_position(pos) or str(pos.get("registry_mode") or "").upper().strip() != "REAL":
        reasons.append("FALCON_LIVE_REAL_POSITION_REQUIRED")
    if not identity.get("lifecycle_id"):
        reasons.append("LIFECYCLE_ID_REQUIRED")
    if not identity.get("client_order_id"):
        reasons.append("CLIENT_ORDER_ID_REQUIRED")
    if not identity.get("order_id"):
        reasons.append("ENTRY_ORDER_ID_REQUIRED")
    if not stop.get("expected_stop_order_id"):
        reasons.append("DISASTER_STOP_ORDER_ID_REQUIRED")
    if not registry.get("ok"):
        reasons.append(str(registry.get("status") or "REGISTRY_READ_REQUIRED"))
    if registry.get("lifecycle_match_count") != 1:
        reasons.append("OPEN_FALCON_LIFECYCLE_MATCH_NOT_UNIQUE")

    candidate = registry.get("matches", [None])[0] if registry.get("lifecycle_match_count") == 1 else None
    if isinstance(candidate, dict):
        expected_pairs = (
            ("TRADE_ID", identity.get("trade_id"), _falcon_terminal_registry_field(candidate, "trade_id")),
            ("LIFECYCLE_ID", identity.get("lifecycle_id"), _falcon_terminal_registry_field(candidate, "lifecycle_id")),
            ("CLIENT_ORDER_ID", identity.get("client_order_id"), _falcon_terminal_registry_field(candidate, "client_order_id", "live_client_order_id")),
            ("ENTRY_ORDER_ID", identity.get("order_id"), _falcon_terminal_registry_field(candidate, "broker_order_id", "live_order_id", "order_id")),
            ("STOP_ORDER_ID", stop.get("expected_stop_order_id"), _falcon_terminal_registry_field(candidate, "broker_stop_order_id", "disaster_stop_order_id")),
            ("SYMBOL", identity.get("symbol"), _falcon_terminal_registry_field(candidate, "symbol")),
            ("SIDE", identity.get("side"), _falcon_terminal_registry_field(candidate, "side")),
        )
        for label, expected, actual in expected_pairs:
            expected_text = str(expected or "").upper().strip()
            actual_text = str(actual or "").upper().strip()
            if label == "SYMBOL":
                expected_text = _falcon_management_norm_symbol(expected)
                actual_text = _falcon_management_norm_symbol(actual)
            elif label == "SIDE":
                expected_text = _falcon_management_norm_side(expected)
                actual_text = _falcon_management_norm_side(actual)
            if not expected_text or not actual_text or expected_text != actual_text:
                reasons.append(f"REGISTRY_{label}_MISMATCH")

    expected_entry_side = "BUY" if identity.get("side") == "LONG" else "SELL"
    entry_order_id = str(entry.get("order_id") or entry.get("id") or "").strip()
    entry_client_id = str(entry.get("client_order_id") or "").strip()
    entry_status = str(entry.get("raw_status") or entry.get("status") or "").upper().strip()
    entry_filled = safe_float(
        entry.get("executed_quantity") if entry.get("executed_quantity") not in (None, "") else entry.get("filled"),
        None,
    )
    if not entry.get("ok") or entry_order_id != str(identity.get("order_id") or ""):
        reasons.append("ENTRY_BROKER_ORDER_ID_NOT_EXACT")
    if entry.get("read_only") is not True:
        reasons.append("ENTRY_READ_ONLY_SNAPSHOT_REQUIRED")
    if entry_client_id != str(identity.get("client_order_id") or ""):
        reasons.append("ENTRY_CLIENT_ORDER_ID_NOT_EXACT")
    if str(entry.get("side") or "").upper().strip() != expected_entry_side:
        reasons.append("ENTRY_SIDE_MISMATCH")
    if entry_status not in {"FILLED", "EXECUTED", "CLOSED"}:
        reasons.append("ENTRY_FILL_STATUS_NOT_FACTUAL")
    if entry_filled is None or broker_qty is None or entry_filled + tolerance < broker_qty:
        reasons.append("ENTRY_FILL_QUANTITY_DOES_NOT_COVER_POSITION")
    if entry.get("symbol") not in (None, "") and _falcon_management_norm_symbol(entry.get("symbol")) != identity.get("symbol"):
        reasons.append("ENTRY_SYMBOL_MISMATCH")

    if not stop.get("order_identity_exact"):
        reasons.append("STOP_ORDER_ID_NOT_EXACT")
    expected_stop_side = "SELL" if identity.get("side") == "LONG" else "BUY"
    if stop.get("symbol") != identity.get("symbol"):
        reasons.append("STOP_SYMBOL_MISMATCH")
    if str(stop.get("side") or "").upper().strip() != expected_stop_side:
        reasons.append("STOP_CLOSE_SIDE_MISMATCH")
    if stop.get("hedge_mode_detected") is True:
        if stop.get("position_side") != identity.get("side"):
            reasons.append("STOP_POSITION_SIDE_MISMATCH")
    elif stop.get("position_side") not in (None, "", "BOTH", identity.get("side")):
        reasons.append("STOP_POSITION_SIDE_MISMATCH")
    elif stop.get("reduce_only") is not True and stop.get("close_position") is not True:
        reasons.append("STOP_ONE_WAY_CLOSE_SEMANTICS_NOT_PROVEN")
    if not stop.get("terminal_factual"):
        reasons.append("STOP_TERMINAL_FACT_NOT_PROVEN")
    if stop.get("read_only") is not True:
        reasons.append("STOP_READ_ONLY_SNAPSHOT_REQUIRED")
    if stop.get("executed_quantity") is None:
        reasons.append("STOP_EXECUTED_QUANTITY_UNKNOWN")
    elif expected_qty > 0 and stop.get("executed_quantity") + tolerance >= expected_qty:
        reasons.append("STOP_FILL_SUFFICIENT")
    if stop.get("terminal_status") in {"CANCELED", "CANCELLED"}:
        derived_order_id = str(stop.get("derived_order_id") or "").strip()
        stop_fills = stop.get("fills") if isinstance(stop.get("fills"), list) else []
        original_stop_id = str(stop.get("expected_stop_order_id") or "").strip()
        foreign_fill_order_ids = {
            str(fill.get("order_id") or "").strip()
            for fill in stop_fills
            if isinstance(fill, dict)
            and str(fill.get("order_id") or "").strip()
            and str(fill.get("order_id") or "").strip() != original_stop_id
        }
        fill_amount_total = sum(
            max(0.0, safe_float(fill.get("amount"), 0.0) or 0.0)
            for fill in stop_fills
            if isinstance(fill, dict)
        )
        executed_quantity = safe_float(stop.get("executed_quantity"), None)
        if derived_order_id:
            reasons.append("CANCELED_STOP_DERIVED_ORDER_RECONCILIATION_REQUIRED")
        if foreign_fill_order_ids:
            reasons.append("CANCELED_STOP_DERIVED_FILL_RECONCILIATION_REQUIRED")
        if (
            stop_fills
            and (
                executed_quantity is None
                or abs(fill_amount_total - executed_quantity) > tolerance
            )
        ):
            reasons.append("CANCELED_STOP_FILL_EVIDENCE_CONFLICT")
        if replacement.get("replacement_in_progress"):
            reasons.append("CANCELED_STOP_REPLACEMENT_IN_PROGRESS")
        if replacement.get("active_replacement_present"):
            reasons.append("CANCELED_STOP_ACTIVE_REPLACEMENT_PRESENT")
        if replacement.get("stop_id_changed"):
            reasons.append("CANCELED_STOP_ID_CHANGED_AFTER_TERMINAL_OBSERVATION")

    if not position.get("ok"):
        reasons.append("BROKER_POSITION_SNAPSHOT_REQUIRED")
    if position.get("read_only") is not True:
        reasons.append("POSITION_READ_ONLY_SNAPSHOT_REQUIRED")
    if position.get("position_closed") or broker_qty is None or broker_qty <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
        reasons.append("BROKER_POSITION_NOT_OPEN")
    if _falcon_management_norm_symbol(position.get("symbol")) != identity.get("symbol"):
        reasons.append("BROKER_POSITION_SYMBOL_MISMATCH")
    if _falcon_management_norm_side(position.get("side")) != identity.get("side"):
        reasons.append("BROKER_POSITION_SIDE_MISMATCH")
    if position.get("ownership_safe") is not True:
        reasons.append("BROKER_POSITION_OWNERSHIP_UNSAFE")
    if broker_qty is not None and expected_qty > 0:
        if broker_qty > expected_qty + tolerance:
            reasons.append("BROKER_QTY_EXCEEDS_FALCON_QTY_POSSIBLE_MANUAL_AGGREGATION")
        elif abs(broker_qty - expected_qty) > tolerance:
            reasons.append("BROKER_QTY_DIFFERS_FROM_FALCON_REMAINING_QTY")
    if int(position.get("matched_count") or 0) != 1:
        reasons.append("BROKER_POSITION_MATCH_COUNT_NOT_UNIQUE")
    position_rows = position.get("positions") if isinstance(position.get("positions"), list) else []
    manual_evidence = any(
        _falcon_terminal_bool(row.get("manual_position"))
        or _falcon_terminal_bool(row.get("external_position"))
        or str(row.get("ownership") or "").upper().strip() in {"MANUAL", "EXTERNAL"}
        for row in position_rows if isinstance(row, dict)
    ) or _falcon_terminal_bool(position.get("manual_position_detected")) or _falcon_terminal_bool(position.get("external_position_detected"))
    if manual_evidence or registry.get("same_leg_other_records"):
        reasons.append("MANUAL_OR_EXTERNAL_POSITION_AGGREGATION_RISK")

    existing_state = str(existing_recovery.get("attempt_state") or "").upper().strip()
    already_sent_or_reserved = bool(
        existing_state in FALCON_TERMINAL_STOP_UNRESOLVED_STATES
        or existing_recovery.get("send_attempted") is True
        or existing_recovery.get("sent") is True
        or existing_recovery.get("confirmed") is True
    )
    if already_sent_or_reserved:
        reasons.append("FAILSAFE_ALREADY_RESERVED_SENT_OR_UNRESOLVED")
    if related_lifecycle_recoveries:
        reasons.append("FAILSAFE_ALREADY_ACTIVE_FOR_LIFECYCLE")

    incident_detected = bool(
        stop.get("terminal_factual")
        and stop.get("executed_quantity") is not None
        and (expected_qty <= 0 or stop.get("executed_quantity") + tolerance < expected_qty)
        and position.get("ok")
        and not position.get("position_closed")
        and broker_qty is not None
        and broker_qty > FALCON_MANAGEMENT_AMOUNT_TOLERANCE
    )
    try:
        emergency_client_order_id = falcon_generate_position_client_order_id(
            pos, ROLE_EMERGENCY_TERMINAL_STOP_CLOSE, 1, attempt=0
        )
    except Exception:
        emergency_client_order_id = None
        reasons.append("EMERGENCY_CLIENT_ORDER_ID_IDENTITY_REQUIRED")
    return {
        "ok": True,
        "version": FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION,
        "incident_id": falcon_terminal_stop_incident_id(pos, verification),
        "incident_detected": incident_detected,
        "eligible": bool(incident_detected and not reasons),
        "emergency_only": True,
        "normal_management_allowed": False,
        "status": "TERMINAL_STOP_EMERGENCY_ALLOWED" if incident_detected and not reasons else (
            "TERMINAL_STOP_EMERGENCY_BLOCKED" if incident_detected else "NO_TERMINAL_STOP_EMERGENCY"
        ),
        "reasons": list(dict.fromkeys(reasons)),
        "expected_qty": expected_qty,
        "broker_qty": broker_qty,
        "identity": identity,
        "registry": {
            "ok": registry.get("ok"),
            "status": registry.get("status"),
            "lifecycle_match_count": registry.get("lifecycle_match_count"),
            "all_lifecycle_match_count": registry.get("all_lifecycle_match_count"),
            "all_lifecycle_record_count": registry.get("all_lifecycle_record_count"),
            "same_leg_other_record_count": len(registry.get("same_leg_other_records") or []),
            "same_leg_conflicts": list(registry.get("same_leg_other_records") or []),
            "ignored_same_leg_record_count": len(registry.get("ignored_same_leg_records") or []),
        },
        "stop": stop,
        "replacement": replacement,
        "client_tag": emergency_client_order_id,
        "idempotency_key": falcon_terminal_stop_incident_id(pos, verification),
        "related_lifecycle_recovery_count": len(related_lifecycle_recoveries),
    }


def _falcon_terminal_stop_creation_projection(pos, verification):
    identity = falcon_position_identity(pos)
    creation = _falcon_stop_creation_evidence(
        pos,
        identity,
        verification.get("stop_order_id") or pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id"),
    )
    return {
        key: creation.get(key)
        for key in (
            "eligible", "order_id", "lifecycle_id", "symbol", "side", "type", "position_side",
            "reduce_only", "close_position", "stop_price", "working_type", "amount",
            "hedge_mode_detected", "source",
        )
    }


def _falcon_terminal_stop_result_projection(
    result,
    *,
    expected_client_order_id=None,
    expected_symbol=None,
    expected_side=None,
    expected_amount=None,
):
    result = result if isinstance(result, dict) else {}
    projected = {
        "ok": result.get("ok"),
        "status": _falcon_terminal_safe_text(result.get("status"), 120),
        "sent": result.get("sent"),
        "confirmed": result.get("confirmed"),
        "send_attempted": result.get("send_attempted"),
        "send_outcome_unknown": result.get("send_outcome_unknown"),
        "phase": _falcon_terminal_safe_text(result.get("phase"), 80),
        "order_id": _falcon_terminal_safe_text(result.get("order_id"), 120),
        "client_order_id": _falcon_terminal_safe_text(result.get("client_order_id") or result.get("client_tag"), 120),
        "symbol": _falcon_management_norm_symbol(result.get("symbol")),
        "side": _falcon_management_norm_side(result.get("side")),
        "timestamp": _falcon_terminal_safe_text(result.get("timestamp"), 120),
        "filled_amount": safe_float(result.get("filled_amount"), None),
        "remaining_amount": safe_float(result.get("remaining_amount"), None),
        "average": safe_float(result.get("average"), None),
        "error": _falcon_terminal_safe_text(result.get("error")),
        "error_type": _falcon_terminal_safe_text(result.get("error_type"), 120),
    }
    evidence_conflicts = []
    attempted = projected.get("send_attempted")
    sent = projected.get("sent")
    confirmed = projected.get("confirmed")
    unknown = projected.get("send_outcome_unknown")
    phase = str(projected.get("phase") or "").upper().strip()
    if sent is False:
        if attempted is not False:
            evidence_conflicts.append("NOT_SENT_WITHOUT_PRE_SEND_PROOF")
        if confirmed is not False:
            evidence_conflicts.append("NOT_SENT_WITH_NON_FALSE_CONFIRMATION")
        if unknown is not False:
            evidence_conflicts.append("NOT_SENT_WITH_UNKNOWN_OUTCOME")
        if phase != "PRE_SEND_SETUP":
            evidence_conflicts.append("NOT_SENT_OUTSIDE_PRE_SEND_SETUP")
    elif sent is True:
        if attempted is not True:
            evidence_conflicts.append("SENT_WITHOUT_SEND_ATTEMPT")
        if unknown is not False:
            evidence_conflicts.append("SENT_WITH_NON_FALSE_UNKNOWN_FLAG")
    elif sent is None:
        if confirmed is not None:
            evidence_conflicts.append("UNKNOWN_SEND_WITH_CONFIRMATION_VALUE")
        if unknown is not True:
            evidence_conflicts.append("UNKNOWN_SEND_WITHOUT_UNKNOWN_FLAG")
    else:
        evidence_conflicts.append("INVALID_SENT_TRI_STATE")
    if projected.get("confirmed") is True:
        if projected.get("sent") is not True:
            evidence_conflicts.append("CONFIRMED_WITHOUT_SENT")
        remaining = projected.get("remaining_amount")
        if remaining is None:
            evidence_conflicts.append("CONFIRMED_WITHOUT_FACTUAL_REMAINING_AMOUNT")
        elif remaining > FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
            evidence_conflicts.append("CONFIRMED_WITH_NON_FLAT_REMAINING_AMOUNT")
        if not projected.get("order_id"):
            evidence_conflicts.append("CONFIRMED_WITHOUT_FACTUAL_ORDER_ID")
        expected_client_text = str(expected_client_order_id or "").strip()
        if expected_client_text and projected.get("client_order_id") != expected_client_text:
            evidence_conflicts.append("CONFIRMED_CLIENT_ORDER_ID_MISMATCH")
        expected_symbol_norm = _falcon_management_norm_symbol(expected_symbol)
        if expected_symbol_norm and projected.get("symbol") != expected_symbol_norm:
            evidence_conflicts.append("CONFIRMED_SYMBOL_MISMATCH")
        expected_side_norm = _falcon_management_norm_side(expected_side)
        if expected_side_norm and projected.get("side") != expected_side_norm:
            evidence_conflicts.append("CONFIRMED_SIDE_MISMATCH")
        expected_amount_value = safe_float(expected_amount, None)
        if expected_amount_value is not None and expected_amount_value > 0:
            filled_amount = projected.get("filled_amount")
            amount_tolerance = max(
                FALCON_MANAGEMENT_AMOUNT_TOLERANCE,
                abs(expected_amount_value) * 1e-6,
            )
            if filled_amount is None or filled_amount + amount_tolerance < expected_amount_value:
                evidence_conflicts.append("CONFIRMED_FILLED_AMOUNT_INSUFFICIENT")
    if evidence_conflicts:
        projected["ok"] = False
        projected["send_attempted"] = None
        projected["sent"] = None
        projected["confirmed"] = None
        projected["send_outcome_unknown"] = True
        projected["evidence_conflicts"] = evidence_conflicts
        projected["error"] = "MANAGED_CLOSE_CONFIRMATION_EVIDENCE_CONFLICT"
    return projected


def _falcon_terminal_pre_send_not_sent_proven(projected):
    """Return True only for a coherent, factual pre-create non-send result."""
    projected = projected if isinstance(projected, dict) else {}
    return bool(
        projected.get("send_attempted") is False
        and projected.get("sent") is False
        and projected.get("confirmed") is False
        and projected.get("send_outcome_unknown") is False
        and str(projected.get("phase") or "").upper().strip() == "PRE_SEND_SETUP"
        and not projected.get("evidence_conflicts")
    )


def falcon_terminal_stop_critical_alert(pos, state, blocked=False):
    """One incident-scoped critical attempt; intentionally bypasses the common cooldown."""
    state = state if isinstance(state, dict) else {}
    previous = state.get("critical_alert") if isinstance(state.get("critical_alert"), dict) else {}
    if previous.get("attempted"):
        return {
            **previous,
            "suppressed": True,
            "suppression_reason": "INCIDENT_CRITICAL_ALERT_ALREADY_ATTEMPTED",
        }
    message = (
        f"FALCON LIVE CRITICAL - TERMINAL DISASTER STOP - {pos.get('symbol')}\n\n"
        f"Side: {pos.get('side')}\n"
        f"Lifecycle: {pos.get('lifecycle_id')}\n"
        f"Stop order: {pos.get('broker_stop_order_id') or pos.get('disaster_stop_order_id')}\n"
        f"Emergency blocked: {bool(blocked)}\n"
        f"Immediate factual verification required."
    )
    alert = {
        "critical_condition_detected": True,
        "attempted": True,
        "transport_called": True,
        "delivery_confirmed": False,
        "suppressed": False,
        "blocked": bool(blocked),
        "error": None,
        "attempted_at": data_hora_sp_str(),
    }
    try:
        alert["delivery_confirmed"] = bool(safe_send_telegram(
            message,
            event_type="FALCON_TERMINAL_DISASTER_STOP_EMERGENCY",
            mode="LIVE",
            operational_critical=True,
        ))
        if not alert["delivery_confirmed"]:
            alert["error"] = "DELIVERY_NOT_CONFIRMED"
    except Exception as exc:
        alert["error"] = _falcon_terminal_safe_text(exc)
    return alert


def _falcon_terminal_auth_projection(auth, context_matches):
    auth = auth if isinstance(auth, dict) else {}
    return {
        "ok": auth.get("ok") is True,
        "status": _falcon_terminal_safe_text(auth.get("status"), 120),
        "token_present": bool(auth.get("token")),
        "context_matches": bool(context_matches),
        "expires_at": _falcon_terminal_safe_text(auth.get("expires_at"), 80),
    }


def falcon_handle_terminal_stop_emergency(pid, pos, verification, registry_snapshot=None):
    """Persist, authorize and execute only the terminal-stop emergency recovery."""
    now_epoch = time.time()
    now_text = data_hora_sp_str()
    incident_id = falcon_terminal_stop_incident_id(pos, verification)
    base = {
        "ok": True,
        "version": FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION,
        "incident_id": incident_id,
        "incident_detected": False,
        "eligible": False,
        "attempted": False,
        "sent": False,
        "confirmed": False,
        "closed": False,
        "normal_management_allowed": False,
    }
    if not incident_id:
        return {**base, "ok": False, "status": "TERMINAL_STOP_INCIDENT_ID_UNAVAILABLE"}

    preliminary_stop = _falcon_terminal_stop_facts(pos, verification)
    preliminary_position = (
        verification.get("position_snapshot")
        if isinstance(verification.get("position_snapshot"), dict)
        else {}
    )
    preliminary_expected = falcon_real_remaining_qty(pos)
    preliminary_broker_qty = safe_float(preliminary_position.get("amount"), None)
    preliminary_tolerance = max(
        FALCON_MANAGEMENT_AMOUNT_TOLERANCE,
        abs(preliminary_expected or 0.0) * 1e-6,
    )
    preliminary_incident = bool(
        preliminary_stop.get("terminal_factual")
        and preliminary_stop.get("executed_quantity") is not None
        and (
            preliminary_expected <= 0
            or preliminary_stop.get("executed_quantity") + preliminary_tolerance
            < preliminary_expected
        )
        and preliminary_position.get("ok")
        and not preliminary_position.get("position_closed")
        and preliminary_broker_qty is not None
        and preliminary_broker_qty > FALCON_MANAGEMENT_AMOUNT_TOLERANCE
    )
    if not preliminary_incident:
        return {
            **base,
            "status": "NO_TERMINAL_STOP_EMERGENCY",
            "terminal_stop": preliminary_stop,
        }

    def persistence_block(status, error=None, incident_state=None):
        block_state = dict(incident_state or {})
        block_state.update({
            "version": FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION,
            "incident_id": incident_id,
            "critical_condition_detected": True,
            "attempt_state": status,
            "send_attempted": bool(block_state.get("send_attempted", False)),
            "sent": block_state.get("sent", False),
            "confirmed": block_state.get("confirmed", False),
            "persistence_error": _falcon_terminal_safe_text(error),
            "updated_at": data_hora_sp_str(),
            "updated_epoch": time.time(),
        })
        block_state["critical_alert"] = falcon_terminal_stop_critical_alert(
            pos,
            block_state,
            blocked=True,
        )
        pos["terminal_stop_emergency_recovery"] = dict(block_state)
        HEALTH["falcon_terminal_stop_recovery_status"] = status
        HEALTH["falcon_terminal_stop_recovery_incident_id"] = incident_id
        HEALTH["falcon_terminal_stop_recovery_last_at"] = data_hora_sp_str()
        HEALTH["falcon_terminal_stop_recovery_sent"] = block_state.get("sent")
        HEALTH["falcon_terminal_stop_recovery_confirmed"] = block_state.get("confirmed")
        return block_state

    # Per-incident Redis keys and the lifecycle SET NX are the cross-worker
    # authority.  Do not serialize acquisition behind a process-local lock.
    if incident_id:
        loaded = falcon_terminal_stop_recovery_load(incident_id)
        if not loaded.get("ok"):
            blocked_state = persistence_block(
                "PERSISTENCE_READ_BLOCKED",
                error=loaded.get("error"),
            )
            return {
                **base,
                "ok": False,
                "status": "TERMINAL_STOP_RECOVERY_PERSISTENCE_READ_REQUIRED",
                "error": loaded.get("error"),
                "critical_alert": blocked_state.get("critical_alert"),
            }
        previous = dict(loaded.get("incident") or {})
        decision = falcon_terminal_stop_emergency_decision(
            pos,
            verification,
            registry_snapshot=registry_snapshot,
            existing_recovery=previous,
            related_lifecycle_recoveries=[],
        )
        if not decision.get("incident_detected"):
            return {**base, "status": "NO_TERMINAL_STOP_EMERGENCY", "guard": decision}

        # The lifecycle lock is the authority for every incident mutation,
        # including blocked decisions.  Otherwise a stale reader can restore
        # an older state after the authoritative worker has already persisted
        # BROKER_CALL_PENDING or CONFIRMED.
        lifecycle_lock_id = falcon_terminal_stop_lifecycle_lock_id(pos)
        owner_nonce = secrets.token_hex(24)
        lifecycle_lock = falcon_terminal_stop_acquire_lifecycle_lock(
            lifecycle_lock_id,
            owner_nonce,
        )
        if not lifecycle_lock.get("acquired"):
            latest = falcon_terminal_stop_recovery_load(incident_id)
            authoritative_state = (
                dict(latest.get("incident") or {})
                if latest.get("ok") and isinstance(latest.get("incident"), dict)
                else {}
            )
            lock_projection = {
                "acquired": False,
                "status": lifecycle_lock.get("status"),
                "authoritative_lock_present": lifecycle_lock.get("authoritative_lock_present"),
                "reconciliation_required": True,
                "reconcile_by_client_order_id": falcon_position_identity(pos).get("client_order_id"),
            }
            return {
                **base,
                "ok": False,
                "incident_detected": True,
                "eligible": bool(decision.get("eligible")),
                "status": "TERMINAL_STOP_EMERGENCY_LIFECYCLE_LOCK_BLOCKED",
                "reasons": ["LIFECYCLE_LOCK_ACTIVE_OR_ORPHANED_RECONCILIATION_REQUIRED"],
                "guard": decision,
                "lifecycle_lock": lock_projection,
                "persistence": {
                    "ok": True,
                    "status": "NOT_WRITTEN_BY_LIFECYCLE_LOCK_LOSER",
                    "authoritative_state_preserved": True,
                },
                "authoritative_attempt_state": authoritative_state.get("attempt_state"),
                "critical_alert": authoritative_state.get("critical_alert"),
            }

        locked_loaded = falcon_terminal_stop_recovery_load(incident_id)
        if not locked_loaded.get("ok"):
            return {
                **base,
                "ok": False,
                "incident_detected": True,
                "eligible": False,
                "status": "TERMINAL_STOP_RECOVERY_PERSISTENCE_READ_REQUIRED",
                "error": locked_loaded.get("error"),
                "lifecycle_lock_release": None,
                "lifecycle_lock_retained": True,
            }
        previous = dict(locked_loaded.get("incident") or {})
        prior_attempt_state = str(
            previous.get("attempt_state") or ""
        ).upper().strip()
        prior_client_order_id_reservation = (
            dict(previous.get("client_order_id_reservation") or {})
            if isinstance(previous.get("client_order_id_reservation"), dict)
            else {}
        )
        decision = falcon_terminal_stop_emergency_decision(
            pos,
            verification,
            registry_snapshot=registry_snapshot,
            existing_recovery=previous,
            related_lifecycle_recoveries=[],
        )
        if not decision.get("incident_detected"):
            lifecycle_lock_release = falcon_terminal_stop_release_lifecycle_lock(
                lifecycle_lock_id,
                owner_nonce,
            )
            return {
                **base,
                "status": "NO_TERMINAL_STOP_EMERGENCY",
                "guard": decision,
                "lifecycle_lock_release": lifecycle_lock_release,
            }

        state = dict(previous)
        state.update({
            "version": FALCON_TERMINAL_STOP_EMERGENCY_RECOVERY_VERSION,
            "incident_id": incident_id,
            "idempotency_key": decision.get("idempotency_key"),
            "client_tag": decision.get("client_tag"),
            "first_detected_at": state.get("first_detected_at") or now_text,
            "first_detected_epoch": state.get("first_detected_epoch") or now_epoch,
            "updated_at": now_text,
            "updated_epoch": now_epoch,
            "critical_condition_detected": True,
            "identity": {
                key: falcon_position_identity(pos).get(key)
                for key in (
                    "trade_id", "lifecycle_id", "client_order_id", "order_id",
                    "symbol", "side",
                )
            },
            "stop_creation": _falcon_terminal_stop_creation_projection(pos, verification),
            "terminal_stop": decision.get("stop"),
            "guard_decision": {
                "status": decision.get("status"),
                "eligible": decision.get("eligible"),
                "reasons": list(decision.get("reasons") or []),
                "expected_qty": decision.get("expected_qty"),
                "broker_qty": decision.get("broker_qty"),
                "registry": dict(decision.get("registry") or {}),
            },
        })
        state["lifecycle_lock"] = {
            "acquired": True,
            "status": lifecycle_lock.get("status"),
            "lifecycle_lock_id": lifecycle_lock_id,
        }
        if not decision.get("eligible"):
            state["critical_alert"] = falcon_terminal_stop_critical_alert(
                pos, state, blocked=True
            )
            state["updated_at"] = data_hora_sp_str()
            state["updated_epoch"] = time.time()
            state["lifecycle_lock_release"] = {
                "status": "RELEASE_AFTER_BLOCKED_STATE_PERSISTENCE"
            }
            blocked_save = falcon_terminal_stop_recovery_save(incident_id, state)
            lock_release = None
            if blocked_save.get("ok"):
                lock_release = falcon_terminal_stop_release_lifecycle_lock(
                    lifecycle_lock_id,
                    owner_nonce,
                )
                state["lifecycle_lock_release"] = lock_release
            HEALTH["falcon_terminal_stop_recovery_status"] = "BLOCKED"
            HEALTH["falcon_terminal_stop_recovery_incident_id"] = incident_id
            HEALTH["falcon_terminal_stop_recovery_last_at"] = now_text
            pos["terminal_stop_emergency_recovery"] = dict(state)
            record_event("FALCON_TERMINAL_STOP_EMERGENCY_BLOCKED", pos, {
                "incident_id": incident_id,
                "reasons": list(decision.get("reasons") or []),
            })
            return {
                **base,
                "ok": bool(blocked_save.get("ok")),
                "incident_detected": True,
                "status": (
                    "TERMINAL_STOP_EMERGENCY_BLOCKED"
                    if blocked_save.get("ok")
                    else "TERMINAL_STOP_RECOVERY_PERSISTENCE_WRITE_REQUIRED"
                ),
                "guard": decision,
                "persistence": blocked_save,
                "lifecycle_lock_release": lock_release,
                "critical_alert": state.get("critical_alert"),
            }

        initial_save = falcon_terminal_stop_recovery_save(incident_id, state)
        if not initial_save.get("ok"):
            blocked_state = persistence_block(
                "PERSISTENCE_WRITE_BLOCKED",
                error=initial_save.get("error"),
                incident_state=state,
            )
            blocked_state["lifecycle_lock_retained"] = True
            return {
                **base,
                "ok": False,
                "incident_detected": True,
                "status": "TERMINAL_STOP_RECOVERY_PERSISTENCE_WRITE_REQUIRED",
                "guard": decision,
                "error": initial_save.get("error"),
                "lifecycle_lock_release": None,
                "lifecycle_lock_retained": True,
                "critical_alert": blocked_state.get("critical_alert"),
            }

        state["attempt_state"] = "READY_TO_SEND"
        state["attempt_count"] = int(state.get("attempt_count") or 0) + 1
        state["attempt_reserved_at"] = data_hora_sp_str()
        state["attempt_reserved_epoch"] = time.time()
        state["send_attempted"] = False
        state["sent"] = False
        state["confirmed"] = False
        state["current_attempt_id"] = None
        state["current_attempt_sequence"] = None
        state["prior_attempt_id"] = (
            prior_client_order_id_reservation.get("attempt_id")
            if prior_attempt_state == "NOT_SENT"
            else None
        )
        state["client_order_id"] = None
        state["disposition"] = "CLIENT_ORDER_ATTEMPT_NOT_RESERVED"
        state["retry_authorization_status"] = (
            "PENDING_PRIOR_PRE_SEND_RECONCILIATION"
            if prior_attempt_state == "NOT_SENT"
            else "NOT_REQUIRED_INITIAL_ATTEMPT"
        )
        state["reconciliation_basis"] = (
            "PENDING_ACCOUNT_AUTHORITY_RECONCILIATION"
            if prior_attempt_state == "NOT_SENT"
            else "INITIAL_ATTEMPT"
        )
        state["updated_at"] = state["attempt_reserved_at"]
        state["updated_epoch"] = state["attempt_reserved_epoch"]
        reservation_save = falcon_terminal_stop_recovery_save(incident_id, state)
        if not reservation_save.get("ok"):
            blocked_state = persistence_block(
                "RESERVATION_PERSISTENCE_BLOCKED",
                error=reservation_save.get("error"),
                incident_state=state,
            )
            blocked_state["lifecycle_lock_retained"] = True
            return {
                **base,
                "ok": False,
                "incident_detected": True,
                "eligible": True,
                "status": "TERMINAL_STOP_RECOVERY_RESERVATION_PERSISTENCE_REQUIRED",
                "guard": decision,
                "lifecycle_lock_release": None,
                "lifecycle_lock_retained": True,
                "critical_alert": blocked_state.get("critical_alert"),
            }
        original_stop_id = str((decision.get("stop") or {}).get("expected_stop_order_id") or "")

        # Serialize against local stop replacement and then refresh every
        # factual snapshot after the distributed lifecycle lock is held.
        with position_mutation_lock:
            fresh_registry_snapshot = registry_snapshot
            if central_trade_registry is not None and hasattr(
                central_trade_registry, "load_registry_read_only"
            ):
                try:
                    fresh_registry_snapshot = central_trade_registry.load_registry_read_only()
                except Exception as exc:
                    fresh_registry_snapshot = {
                        "open_trades": {},
                        "_terminal_revalidation_error": _falcon_terminal_safe_text(exc),
                    }
            try:
                fresh_verification = falcon_verify_live_disaster_stop(
                    pos,
                    force=True,
                    persist_registry=False,
                )
            except Exception as exc:
                fresh_verification = {
                    "ok": False,
                    "cached": False,
                    "status": "TERMINAL_STOP_FINAL_REVALIDATION_EXCEPTION",
                    "error": _falcon_terminal_safe_text(exc),
                }
            replacement_order_scan = None
            original_terminal_status = str(
                (decision.get("stop") or {}).get("terminal_status") or ""
            ).upper().strip()
            if original_terminal_status in {"CANCELED", "CANCELLED"}:
                if central_broker is None or not hasattr(
                    central_broker, "managed_open_orders_snapshot"
                ):
                    replacement_order_scan = {
                        "ok": False,
                        "status": "OPEN_ORDERS_REVALIDATION_HELPER_MISSING",
                        "read_only": True,
                        "orders": [],
                    }
                else:
                    try:
                        replacement_order_scan = central_broker.managed_open_orders_snapshot(
                            pos.get("symbol")
                        )
                    except Exception as exc:
                        replacement_order_scan = {
                            "ok": False,
                            "status": "OPEN_ORDERS_REVALIDATION_EXCEPTION",
                            "error": _falcon_terminal_safe_text(exc),
                            "read_only": True,
                            "orders": [],
                        }
                replacement_order_scan = (
                    replacement_order_scan
                    if isinstance(replacement_order_scan, dict)
                    else {"ok": False, "status": "OPEN_ORDERS_REVALIDATION_INVALID", "orders": []}
                )
                fresh_verification["replacement_order_scan"] = {
                    "ok": replacement_order_scan.get("ok") is True,
                    "status": _falcon_terminal_safe_text(replacement_order_scan.get("status"), 120),
                    "read_only": replacement_order_scan.get("read_only") is True,
                    "count": int(replacement_order_scan.get("count") or 0),
                    "error": _falcon_terminal_safe_text(replacement_order_scan.get("error")),
                }
                active_replacements = _falcon_terminal_active_replacement_orders(
                    pos,
                    replacement_order_scan,
                    decision.get("stop"),
                )
                if active_replacements:
                    fresh_verification["replacement_stop_snapshot"] = active_replacements[0]
            final_decision = falcon_terminal_stop_emergency_decision(
                pos,
                fresh_verification,
                registry_snapshot=fresh_registry_snapshot,
                existing_recovery={},
                related_lifecycle_recoveries=[],
            )
            final_stop_id = str((final_decision.get("stop") or {}).get("expected_stop_order_id") or "")
            current_position_stop_id = str(
                pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id") or ""
            )
            final_reasons = list(final_decision.get("reasons") or [])
            if original_terminal_status in {"CANCELED", "CANCELLED"} and (
                not isinstance(replacement_order_scan, dict)
                or replacement_order_scan.get("ok") is not True
                or replacement_order_scan.get("read_only") is not True
            ):
                final_reasons.append("CANCELED_STOP_OPEN_ORDERS_REVALIDATION_REQUIRED")
            if (
                not original_stop_id
                or final_stop_id != original_stop_id
                or current_position_stop_id != original_stop_id
            ):
                final_reasons.append("STOP_ID_CHANGED_DURING_FINAL_REVALIDATION")
            if fresh_verification.get("cached") is not False:
                final_reasons.append("FINAL_REVALIDATION_MUST_BE_FRESH")
            final_decision["reasons"] = list(dict.fromkeys(final_reasons))
            final_decision["eligible"] = bool(final_decision.get("incident_detected") and not final_decision["reasons"])
            final_decision["status"] = (
                "TERMINAL_STOP_EMERGENCY_ALLOWED"
                if final_decision.get("eligible")
                else "TERMINAL_STOP_EMERGENCY_BLOCKED"
            )
            state["final_revalidation"] = {
                "performed_after_lifecycle_lock": True,
                "status": final_decision.get("status"),
                "eligible": final_decision.get("eligible"),
                "reasons": list(final_decision.get("reasons") or []),
                "stop_order_id": final_stop_id or None,
                "position_qty": final_decision.get("broker_qty"),
                "replacement": dict(final_decision.get("replacement") or {}),
            }
            if not final_decision.get("eligible"):
                state.update({
                    "attempt_state": "FINAL_REVALIDATION_BLOCKED",
                    "send_attempted": False,
                    "sent": False,
                    "confirmed": False,
                    "updated_at": data_hora_sp_str(),
                    "updated_epoch": time.time(),
                })
                state["critical_alert"] = falcon_terminal_stop_critical_alert(pos, state, blocked=True)
                state["lifecycle_lock_release"] = {
                    "status": "RELEASE_AFTER_FINAL_REVALIDATION_PERSISTENCE"
                }
                final_save = falcon_terminal_stop_recovery_save(incident_id, state)
                lifecycle_lock_release = None
                if final_save.get("ok"):
                    lifecycle_lock_release = falcon_terminal_stop_release_lifecycle_lock(
                        lifecycle_lock_id, owner_nonce,
                    )
                    state["lifecycle_lock_release"] = lifecycle_lock_release
                pos["terminal_stop_emergency_recovery"] = dict(state)
                return {
                    **base,
                    "ok": False,
                    "incident_detected": True,
                    "status": "TERMINAL_STOP_EMERGENCY_FINAL_REVALIDATION_BLOCKED",
                    "guard": final_decision,
                    "persistence": final_save,
                    "lifecycle_lock_release": lifecycle_lock_release,
                    "critical_alert": state.get("critical_alert"),
                }

            decision = final_decision
            auth_extra = {
                "amount": decision.get("broker_qty"),
                "expected_position_amount": decision.get("broker_qty"),
                "reason": "STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN",
                "idempotency_key": incident_id,
                "emergency_operation": "TERMINAL_STOP_EMERGENCY_CLOSE",
                "lifecycle_id": falcon_position_identity(pos).get("lifecycle_id"),
                "client_order_id": falcon_position_identity(pos).get("client_order_id"),
                "entry_order_id": falcon_position_identity(pos).get("order_id"),
            }
            auth = falcon_issue_management_token(pos, "managed_close_position_market", auth_extra)
            token = auth.get("token") if isinstance(auth, dict) else None
            auth_context = auth.get("context") if isinstance(auth, dict) and isinstance(auth.get("context"), dict) else {}
            auth_amount = safe_float(auth_context.get("amount"), None)
            expected_auth_amount = safe_float(decision.get("broker_qty"), None)
            identity = falcon_position_identity(pos)
            auth_context_matches = bool(
                auth_context.get("operation") == "managed_close_position_market"
                and _falcon_management_norm_symbol(auth_context.get("symbol")) == identity.get("symbol")
                and _falcon_management_norm_side(auth_context.get("side")) == identity.get("side")
                and auth_context.get("reason") == "STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN"
                and auth_context.get("idempotency_key") == incident_id
                and auth_context.get("lifecycle_id") == identity.get("lifecycle_id")
                and auth_context.get("client_order_id") == identity.get("client_order_id")
                and auth_context.get("entry_order_id") == identity.get("order_id")
                and auth_amount is not None
                and expected_auth_amount is not None
                and abs(auth_amount - expected_auth_amount)
                <= max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, abs(expected_auth_amount) * 1e-6)
            )
            auth_projection = _falcon_terminal_auth_projection(auth, auth_context_matches)
            state["auth"] = auth_projection
            if not (isinstance(auth, dict) and auth.get("ok") is True and token and auth_context_matches):
                state.update({
                    "attempt_state": "BLOCKED_AUTH",
                    "send_attempted": False,
                    "sent": False,
                    "confirmed": False,
                    "updated_at": data_hora_sp_str(),
                    "updated_epoch": time.time(),
                })
                state["critical_alert"] = falcon_terminal_stop_critical_alert(pos, state, blocked=True)
                state["lifecycle_lock_release"] = {
                    "status": "RELEASE_AFTER_AUTH_BLOCK_PERSISTENCE"
                }
                auth_save = falcon_terminal_stop_recovery_save(incident_id, state)
                lifecycle_lock_release = None
                if auth_save.get("ok"):
                    lifecycle_lock_release = falcon_terminal_stop_release_lifecycle_lock(
                        lifecycle_lock_id, owner_nonce,
                    )
                    state["lifecycle_lock_release"] = lifecycle_lock_release
                pos["terminal_stop_emergency_recovery"] = dict(state)
                return {
                    **base,
                    "incident_detected": True,
                    "eligible": True,
                    "status": "TERMINAL_STOP_EMERGENCY_AUTH_BLOCKED",
                    "guard": decision,
                    "auth": auth_projection,
                    "persistence": auth_save,
                    "lifecycle_lock_release": lifecycle_lock_release,
                    "critical_alert": state.get("critical_alert"),
                }

            # A FEC1 is consumed only after every factual revalidation and the
            # complete management-token context have passed.  A prior factual
            # PRE_SEND failure must authorize a distinct contiguous attempt;
            # the lifetime authority never permits reuse of attempt 0.
            close_attempt = 0
            retry_authorization = None
            if prior_attempt_state == "NOT_SENT":
                try:
                    prior_attempt_sequence = int(
                        prior_client_order_id_reservation.get(
                            "attempt_sequence",
                            prior_client_order_id_reservation.get("attempt"),
                        )
                    )
                except (TypeError, ValueError):
                    prior_attempt_sequence = -1
                close_attempt = prior_attempt_sequence + 1
                retry_authorization = falcon_authorize_position_client_order_retry(
                    pos,
                    ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
                    1,
                    prior_client_order_id_reservation,
                    close_attempt,
                )
                state["client_order_id_retry_authorization"] = (
                    _falcon_client_order_authority_projection(retry_authorization)
                )
                state["retry_authorization_status"] = retry_authorization.get(
                    "status"
                )
                state["reconciliation_basis"] = retry_authorization.get(
                    "proof_mode"
                )
                if not (
                    retry_authorization.get("ok") is True
                    and retry_authorization.get("persistent") is True
                    and retry_authorization.get("reconciliation_required") is False
                    and retry_authorization.get("attempt_sequence") == close_attempt
                ):
                    state.update({
                        "attempt_state": "CLIENT_ORDER_ID_RETRY_AUTHORIZATION_BLOCKED",
                        "send_attempted": False,
                        "sent": False,
                        "confirmed": False,
                        "updated_at": data_hora_sp_str(),
                        "updated_epoch": time.time(),
                        "lifecycle_lock_retained": True,
                    })
                    state["critical_alert"] = falcon_terminal_stop_critical_alert(
                        pos, state, blocked=True
                    )
                    retry_save = falcon_terminal_stop_recovery_save(
                        incident_id, state
                    )
                    pos["terminal_stop_emergency_recovery"] = dict(state)
                    return {
                        **base,
                        "ok": False,
                        "incident_detected": True,
                        "eligible": True,
                        "status": "TERMINAL_STOP_EMERGENCY_RETRY_AUTHORIZATION_BLOCKED",
                        "guard": decision,
                        "retry_authorization": state.get(
                            "client_order_id_retry_authorization"
                        ),
                        "persistence": retry_save,
                        "lifecycle_lock_release": None,
                        "lifecycle_lock_retained": True,
                        "critical_alert": state.get("critical_alert"),
                    }

            close_id_reservation = falcon_prepare_position_client_order_id(
                pos,
                ROLE_EMERGENCY_TERMINAL_STOP_CLOSE,
                1,
                attempt=close_attempt,
            )
            state["client_order_id_reservation"] = (
                _falcon_client_order_authority_projection(close_id_reservation)
            )
            if close_id_reservation.get("send_allowed") is not True:
                state.update({
                    "attempt_state": "CLIENT_ORDER_ID_RESERVATION_BLOCKED",
                    "send_attempted": False,
                    "sent": False,
                    "confirmed": False,
                    "updated_at": data_hora_sp_str(),
                    "updated_epoch": time.time(),
                    "lifecycle_lock_retained": True,
                })
                state["critical_alert"] = falcon_terminal_stop_critical_alert(
                    pos, state, blocked=True
                )
                reservation_save = falcon_terminal_stop_recovery_save(
                    incident_id, state
                )
                pos["terminal_stop_emergency_recovery"] = dict(state)
                return {
                    **base,
                    "ok": False,
                    "incident_detected": True,
                    "eligible": True,
                    "status": "TERMINAL_STOP_EMERGENCY_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
                    "guard": decision,
                    "client_order_id_reservation": state.get("client_order_id_reservation"),
                    "persistence": reservation_save,
                    "lifecycle_lock_release": None,
                    "lifecycle_lock_retained": True,
                    "critical_alert": state.get("critical_alert"),
                    }
            state.update({
                "current_attempt_id": close_id_reservation.get("attempt_id"),
                "current_attempt_sequence": close_id_reservation.get(
                    "attempt_sequence"
                ),
                "prior_attempt_id": (
                    retry_authorization.get("prior_attempt_id")
                    if isinstance(retry_authorization, dict)
                    else None
                ),
                "client_order_id": close_id_reservation.get("client_order_id"),
                "disposition": "RESERVED_PRE_SEND",
                "retry_authorization_status": (
                    retry_authorization.get("status")
                    if isinstance(retry_authorization, dict)
                    else "NOT_REQUIRED_INITIAL_ATTEMPT"
                ),
                "reconciliation_basis": (
                    retry_authorization.get("proof_mode")
                    if isinstance(retry_authorization, dict)
                    else "INITIAL_ATTEMPT"
                ),
            })
            decision["client_tag"] = close_id_reservation.get("client_order_id")
            state["client_tag"] = close_id_reservation.get("client_order_id")

            state.update({
                "attempt_state": "BROKER_CALL_PENDING",
                "send_attempted": False,
                "sent": False,
                "confirmed": False,
                "attempted_at": data_hora_sp_str(),
                "attempted_epoch": time.time(),
                "updated_at": data_hora_sp_str(),
                "updated_epoch": time.time(),
            })
            attempted_save = falcon_terminal_stop_recovery_save(incident_id, state)
            if not attempted_save.get("ok"):
                pre_send_consumption = (
                    falcon_record_client_order_attempt_outcome(
                        close_id_reservation,
                        "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
                        reason="INCIDENT_STATE_PERSISTENCE_FAILED",
                        failure_phase="PRE_SEND_STATE_PERSISTENCE",
                    )
                )
                pre_send_consumption_projection = (
                    _falcon_client_order_authority_projection(
                        pre_send_consumption
                    )
                )
                state["account_attempt_outcome"] = (
                    pre_send_consumption_projection
                )
                state["disposition"] = (
                    pre_send_consumption_projection.get("attempt_disposition")
                    or "PRE_SEND_CONSUMPTION_PERSISTENCE_BLOCKED"
                )
                blocked_state = persistence_block(
                    "PRE_SEND_PERSISTENCE_BLOCKED",
                    error=attempted_save.get("error"),
                    incident_state=state,
                )
                # The broker has not been called, but the authoritative
                # BROKER_CALL_PENDING fact was not acknowledged.  Retain the
                # lifecycle lock so another worker cannot infer that a fresh
                # attempt is safe from an older READY_TO_SEND snapshot.
                blocked_state["lifecycle_lock_release"] = None
                blocked_state["lifecycle_lock_retained"] = True
                return {
                    **base,
                    "ok": False,
                    "incident_detected": True,
                    "eligible": True,
                    "status": "TERMINAL_STOP_RECOVERY_PRE_SEND_PERSISTENCE_REQUIRED",
                    "guard": decision,
                    "account_attempt_outcome": (
                        pre_send_consumption_projection
                    ),
                    "persistence": attempted_save,
                    "lifecycle_lock_release": None,
                    "lifecycle_lock_retained": True,
                    "critical_alert": blocked_state.get("critical_alert"),
                }

            broker_qty = decision.get("broker_qty")
            try:
                broker_result = central_broker.managed_close_position_market(
                    symbol=pos.get("symbol"),
                    side=pos.get("side"),
                    amount=broker_qty,
                    expected_position_amount=broker_qty,
                    client_tag=decision.get("client_tag"),
                    reason="STOP_TERMINAL_FAILURE_POSITION_STILL_OPEN",
                    execution_auth_token=token,
                    client_order_id_reservation=close_id_reservation,
                )
            except Exception as exc:
                broker_result = {
                    "ok": False,
                    "status": "TERMINAL_STOP_EMERGENCY_BROKER_EXCEPTION",
                    "phase": "BROKER_WRAPPER_UNKNOWN",
                    "send_attempted": None,
                    "sent": None,
                    "confirmed": None,
                    "send_outcome_unknown": True,
                    "error": _falcon_terminal_safe_text(exc),
                }

    projected = _falcon_terminal_stop_result_projection(
        broker_result,
        expected_client_order_id=decision.get("client_tag"),
        expected_symbol=pos.get("symbol"),
        expected_side=pos.get("side"),
        expected_amount=decision.get("broker_qty"),
    )
    if projected.get("sent") is None and projected.get("status") in {
        "MANAGED_CLOSE_ERROR", "TERMINAL_STOP_EMERGENCY_BROKER_EXCEPTION",
    }:
        projected["sent"] = None
        projected["confirmed"] = None
        projected["send_outcome_unknown"] = True
    attempt_state = "CONFIRMED" if projected.get("confirmed") is True else (
        "SENT_UNCONFIRMED" if projected.get("sent") is True else (
            "SEND_OUTCOME_UNKNOWN" if projected.get("sent") is None else "NOT_SENT"
        )
    )
    pre_send_not_sent_proven = _falcon_terminal_pre_send_not_sent_proven(
        projected
    )
    broker_attempt_outcome = (
        broker_result.get("attempt_outcome_persistence")
        if isinstance(broker_result, dict)
        and isinstance(broker_result.get("attempt_outcome_persistence"), dict)
        else None
    )
    broker_attempt_outcome_matches = bool(
        isinstance(broker_attempt_outcome, dict)
        and broker_attempt_outcome.get("ok") is True
        and broker_attempt_outcome.get("persistent") is True
        and broker_attempt_outcome.get("id_released") is False
        and str(broker_attempt_outcome.get("client_order_id") or "").upper()
        == str(close_id_reservation.get("client_order_id") or "").upper()
    )
    account_attempt_outcome = (
        dict(broker_attempt_outcome)
        if broker_attempt_outcome_matches
        else None
    )
    if pre_send_not_sent_proven:
        if not (
            broker_attempt_outcome_matches
            and broker_attempt_outcome.get("attempt_disposition")
            == "PRE_SEND_CONSUMED"
        ):
            account_attempt_outcome = falcon_record_client_order_attempt_outcome(
                close_id_reservation,
                "PRE_SEND_FAILED_ATTEMPT_CONSUMED",
                reason="FALCON_TERMINAL_STOP_PRE_SEND_FAILURE",
                failure_phase="PRE_SEND_SETUP",
            )
    elif projected.get("sent") is None and not (
        broker_attempt_outcome_matches
        and broker_attempt_outcome.get("attempt_disposition") == "SEND_CLAIMED"
    ):
        account_attempt_outcome = falcon_record_client_order_attempt_outcome(
            close_id_reservation,
            "CREATE_ORDER_OUTCOME_UNKNOWN",
        )
    account_attempt_outcome_projection = (
        _falcon_client_order_authority_projection(account_attempt_outcome)
        if isinstance(account_attempt_outcome, dict)
        else None
    )
    # A factual PRE_SEND result permits unlocking only after the permanent
    # account authority acknowledges that this exact attempt was consumed.
    release_after_persistence = bool(
        pre_send_not_sent_proven
        and isinstance(account_attempt_outcome, dict)
        and account_attempt_outcome.get("ok") is True
        and account_attempt_outcome.get("persistent") is True
        and account_attempt_outcome.get("id_released") is False
    )
    lifecycle_lock_release = None
    with terminal_stop_recovery_lock:
        latest = falcon_terminal_stop_recovery_load(incident_id)
        latest_ok = bool(latest.get("ok"))
        if latest_ok and isinstance(latest.get("incident"), dict) and latest.get("incident"):
            state = dict(latest.get("incident") or {})
        state.update({
            "attempt_state": attempt_state,
            "send_attempted": projected.get("send_attempted"),
            "sent": projected.get("sent"),
            "confirmed": projected.get("confirmed"),
            "failsafe_result": projected,
            "account_attempt_outcome": account_attempt_outcome_projection,
            "disposition": (
                (account_attempt_outcome_projection or {}).get(
                    "attempt_disposition"
                )
                or state.get("disposition")
            ),
            "lifecycle_lock_release": (
                {"status": "RELEASE_AFTER_NOT_SENT_PERSISTENCE"}
                if release_after_persistence
                else None
            ),
            "updated_at": data_hora_sp_str(),
            "updated_epoch": time.time(),
        })
        state["critical_alert"] = falcon_terminal_stop_critical_alert(
            pos,
            state,
            blocked=projected.get("confirmed") is not True,
        )
        if latest_ok:
            result_save = falcon_terminal_stop_recovery_save(incident_id, state)
        else:
            # Never overwrite a per-incident key after an authoritative read
            # failure.  The lifecycle lock remains held and blocks every resend.
            result_save = {
                "ok": False,
                "status": "POST_SEND_PERSISTENCE_READ_FAILED",
                "error": latest.get("error"),
            }

    if release_after_persistence and result_save.get("ok"):
        lifecycle_lock_release = falcon_terminal_stop_release_lifecycle_lock(
            lifecycle_lock_id,
            owner_nonce,
        )
        state["lifecycle_lock_release"] = lifecycle_lock_release

    pre_send_outcome_persistence_blocked = bool(
        pre_send_not_sent_proven and not release_after_persistence
    )
    if pre_send_outcome_persistence_blocked:
        state["lifecycle_lock_retained"] = True

    pos["terminal_stop_emergency_recovery"] = dict(state)
    pos["terminal_stop_emergency_incident_id"] = incident_id
    pos["terminal_stop_emergency_sent"] = projected.get("sent")
    pos["terminal_stop_emergency_confirmed"] = projected.get("confirmed")
    if projected.get("confirmed") is True:
        pos["remaining_qty"] = safe_float(projected.get("remaining_amount"), 0.0)
        pos["terminal_stop_emergency_reconcile_required"] = True
    falcon_update_registry_management(
        pos,
        terminal_stop_emergency_recovery={
            "version": state.get("version"),
            "incident_id": incident_id,
            "idempotency_key": incident_id,
            "client_tag": state.get("client_tag"),
            "first_detected_at": state.get("first_detected_at"),
            "attempt_state": state.get("attempt_state"),
            "current_attempt_id": state.get("current_attempt_id"),
            "current_attempt_sequence": state.get(
                "current_attempt_sequence"
            ),
            "prior_attempt_id": state.get("prior_attempt_id"),
            "client_order_id": state.get("client_order_id"),
            "disposition": state.get("disposition"),
            "retry_authorization_status": state.get(
                "retry_authorization_status"
            ),
            "reconciliation_basis": state.get("reconciliation_basis"),
            "send_attempted": state.get("send_attempted"),
            "sent": state.get("sent"),
            "confirmed": state.get("confirmed"),
            "terminal_stop": state.get("terminal_stop"),
            "failsafe_result": state.get("failsafe_result"),
            "critical_alert": state.get("critical_alert"),
            "persistence_confirmed": bool(result_save.get("ok")),
        },
    )
    record_event("FALCON_TERMINAL_STOP_EMERGENCY_RESULT", pos, {
        "incident_id": incident_id,
        "attempt_state": attempt_state,
        "failsafe_result": projected,
    })
    health_attempt_state = (
        "PRE_SEND_OUTCOME_PERSISTENCE_BLOCKED"
        if pre_send_outcome_persistence_blocked
        else attempt_state
    )
    HEALTH["falcon_terminal_stop_recovery_status"] = health_attempt_state
    HEALTH["falcon_terminal_stop_recovery_incident_id"] = incident_id
    HEALTH["falcon_terminal_stop_recovery_last_at"] = data_hora_sp_str()
    HEALTH["falcon_terminal_stop_recovery_sent"] = projected.get("sent")
    HEALTH["falcon_terminal_stop_recovery_confirmed"] = projected.get("confirmed")
    HEALTH["last_live_stop_status"] = (
        f"TERMINAL_STOP_EMERGENCY_{health_attempt_state}"
    )
    if projected.get("confirmed") is not True:
        HEALTH["last_real_management_error"] = (
            f"TERMINAL_STOP_EMERGENCY_{health_attempt_state}"
        )
    return {
        **base,
        "ok": bool(projected.get("ok") and result_save.get("ok")),
        "incident_detected": True,
        "eligible": True,
        "attempted": True,
        "sent": projected.get("sent"),
        "confirmed": projected.get("confirmed"),
        "status": f"TERMINAL_STOP_EMERGENCY_{health_attempt_state}",
        "guard": decision,
        "failsafe": projected,
        "account_attempt_outcome": account_attempt_outcome_projection,
        "persistence": result_save,
        "lifecycle_lock_release": lifecycle_lock_release,
        "lifecycle_lock_retained": bool(
            pre_send_outcome_persistence_blocked
            or not release_after_persistence
            or not (
                isinstance(lifecycle_lock_release, dict)
                and lifecycle_lock_release.get("released") is True
            )
        ),
        "critical_alert": state.get("critical_alert"),
    }


def _falcon_resize_runner_stop(pos, runner_amount, stop_price, reason):
    with position_mutation_lock:
        pos["stop_replacement_in_progress"] = True
        lifecycle_lock_id = falcon_terminal_stop_lifecycle_lock_id(pos)
        owner_nonce = secrets.token_hex(24)
        lifecycle_lock = falcon_terminal_stop_acquire_lifecycle_lock(
            lifecycle_lock_id,
            owner_nonce,
        )
        lock_acquired = lifecycle_lock.get("acquired") is True
        release_safe = False
        response = None
        try:
            if not lock_acquired:
                return {
                    "ok": False,
                    "status": "STOP_REPLACE_LIFECYCLE_LOCK_BLOCKED",
                    "lifecycle_lock": {
                        "acquired": False,
                        "status": _falcon_terminal_safe_text(lifecycle_lock.get("status"), 120),
                        "authoritative_lock_present": lifecycle_lock.get("authoritative_lock_present"),
                        "reconciliation_required": True,
                    },
                }
            old_order_id = pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
            old_stop = safe_float(pos.get("broker_stop_price"), safe_float(pos.get("stop"), None))
            token_payload = falcon_issue_management_token(pos, "REPLACE_STOP", {"reason": reason, "amount": runner_amount, "new_stop": stop_price})
            token = token_payload.get("token") if isinstance(token_payload, dict) else None
            if not token:
                release_safe = True
                response = {
                    "ok": False,
                    "status": "STOP_REPLACE_AUTH_TOKEN_MISSING",
                    "auth": _falcon_terminal_auth_projection(token_payload, False),
                }
                return response
            reason_key = str(reason or "").upper().strip()
            stop_role = (
                ROLE_BREAK_EVEN_STOP
                if "BREAK" in reason_key or reason_key in {"BE", "BREAKEVEN"}
                else ROLE_TRAILING_STOP
                if "TRAIL" in reason_key
                else ROLE_REPLACEMENT_STOP
            )
            logical_fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "role": stop_role,
                        "old_order_id": str(old_order_id or ""),
                        "stop_price": safe_float(stop_price, None),
                        "amount": safe_float(runner_amount, None),
                        "reason": reason_key,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            pending = (
                pos.get("stop_client_order_id_pending")
                if isinstance(pos.get("stop_client_order_id_pending"), dict)
                else {}
            )
            if pending.get("logical_fingerprint") == logical_fingerprint:
                stop_revision = int(pending.get("revision") or 0)
            else:
                current_stop_revision = pos.get("stop_client_order_id_revision")
                stop_revision = int(
                    0 if current_stop_revision is None else current_stop_revision
                ) + 1
                pending = {
                    "logical_fingerprint": logical_fingerprint,
                    "revision": stop_revision,
                    "role": stop_role,
                    "created_at": data_hora_sp_str(),
                }
                pos["stop_client_order_id_revision"] = stop_revision
                pos["stop_client_order_id_pending"] = pending

            stop_id_reservation = falcon_prepare_position_client_order_id(
                pos, stop_role, stop_revision, attempt=0
            )
            rollback_id_reservation = falcon_prepare_position_client_order_id(
                pos, ROLE_ROLLBACK_STOP, stop_revision, attempt=0
            )
            pending.update({
                "client_order_id": stop_id_reservation.get("client_order_id"),
                "rollback_client_order_id": rollback_id_reservation.get("client_order_id"),
                "reservation_status": stop_id_reservation.get("status"),
                "rollback_reservation_status": rollback_id_reservation.get("status"),
            })
            if not (
                stop_id_reservation.get("send_allowed") is True
                and rollback_id_reservation.get("send_allowed") is True
            ):
                response = {
                    "ok": False,
                    "status": "STOP_REPLACE_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
                    "sent": False,
                    "confirmed": False,
                    "send_attempted": False,
                    "send_outcome_unknown": False,
                    "client_order_id_reservation": stop_id_reservation,
                    "rollback_client_order_id_reservation": rollback_id_reservation,
                    "reconciliation_required": True,
                }
                HEALTH["last_stop_replace_status"] = response["status"]
                return response
            raw_result = central_broker.replace_position_stop_order(
                symbol=pos.get("symbol"),
                side=pos.get("side"),
                old_order_id=old_order_id,
                old_stop_price=old_stop,
                new_stop_price=stop_price,
                amount=runner_amount,
                expected_position_amount=runner_amount,
                client_tag=stop_id_reservation.get("client_order_id"),
                rollback_client_tag=rollback_id_reservation.get("client_order_id"),
                client_order_id_reservation=stop_id_reservation,
                rollback_client_order_id_reservation=rollback_id_reservation,
                reason=reason,
                execution_auth_token=token,
                allow_same_price=(reason == "TP50_RESIZE"),
            )
            response = _falcon_terminal_sanitize_projection(raw_result)
            response = response if isinstance(response, dict) else {
                "ok": False,
                "status": "STOP_REPLACE_INVALID_RESULT",
            }
            status = str(response.get("status") or "").upper().strip()
            new_order_id = str(response.get("new_order_id") or "").strip()
            rollback = response.get("rollback") if isinstance(response.get("rollback"), dict) else {}
            rollback_order_id = str(rollback.get("order_id") or "").strip() if rollback.get("ok") else ""
            replacement_strategy = str(
                response.get("replacement_strategy") or ""
            ).upper().strip()
            if response.get("ok") is True and new_order_id:
                pos["broker_stop_order_id"] = new_order_id
                pos["disaster_stop_order_id"] = new_order_id
                if replacement_strategy != "EDIT_ORDER":
                    pos["broker_stop_client_order_id"] = stop_id_reservation.get("client_order_id")
                    pos["disaster_stop_client_order_id"] = stop_id_reservation.get("client_order_id")
                    pos["disaster_stop_client_order_id_unique"] = True
                    pos["client_order_id_reservation_status"] = stop_id_reservation.get("status")
                pos.pop("stop_client_order_id_pending", None)
            elif rollback_order_id:
                pos["broker_stop_order_id"] = rollback_order_id
                pos["disaster_stop_order_id"] = rollback_order_id
                pos["broker_stop_client_order_id"] = rollback_id_reservation.get("client_order_id")
                pos["disaster_stop_client_order_id"] = rollback_id_reservation.get("client_order_id")
                pos["disaster_stop_client_order_id_unique"] = True
                pos["client_order_id_reservation_status"] = rollback_id_reservation.get("status")
                pos.pop("stop_client_order_id_pending", None)
            release_safe = bool(
                new_order_id
                or rollback_order_id
                or status in {
                    "STOP_REPLACE_INVALID_INPUT", "STOP_NOT_IMPROVED",
                    "STOP_REPLACE_POSITION_NOT_SAFE", "STOP_REPLACE_PRICE_ERROR",
                    "STOP_TRIGGER_ALREADY_CROSSED", "STOP_REPLACE_DRY_RUN",
                    "STOP_REPLACE_AUTH_DENIED", "POSITION_CLOSED_DURING_STOP_REPLACE",
                }
            )
            if _falcon_terminal_pre_send_not_sent_proven(response):
                pos.pop("stop_client_order_id_pending", None)
                release_safe = True
            if response.get("send_outcome_unknown") is True or response.get("sent") is None:
                release_safe = False
            HEALTH["last_stop_replace_status"] = status or None
            return response
        except Exception as exc:
            response = {
                "ok": False,
                "status": "STOP_REPLACE_EXCEPTION",
                "error": _falcon_terminal_safe_text(exc),
            }
            return response
        finally:
            if lock_acquired and release_safe:
                lifecycle_lock_release = falcon_terminal_stop_release_lifecycle_lock(
                    lifecycle_lock_id,
                    owner_nonce,
                )
                if isinstance(response, dict):
                    response["lifecycle_lock_release"] = lifecycle_lock_release
            pos["stop_replacement_in_progress"] = False


def _falcon_finalize_tp50_after_partial(pos, runner_amount, price, close_result):
    pos["tp50_partial_pending"] = False
    pos["tp50_real_order_id"] = (close_result or {}).get("order_id")
    pos["tp50_amount"] = safe_float((close_result or {}).get("filled_amount"), safe_float(pos.get("tp50_intended_amount"), 0.0))
    pos["tp50_fill_price"] = safe_float((close_result or {}).get("average"), price)
    pos["remaining_qty"] = max(0.0, runner_amount)
    pos["runner_qty"] = pos["remaining_qty"]

    if runner_amount <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
        return {
            "ok": True,
            "status": "TP50_REAL_EXECUTED_POSITION_CLOSED",
            "sent": True,
            "confirmed": True,
            "position_closed": True,
            "protected": True,
            "close_order": close_result,
            "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        }

    stop_result = _falcon_resize_runner_stop(pos, runner_amount, safe_float(pos.get("stop")), "TP50_RESIZE")
    if isinstance(stop_result, dict) and stop_result.get("ok"):
        stop_confirmed_at = data_hora_sp_str()
        pos["broker_stop_order_id"] = stop_result.get("new_order_id") or pos.get("broker_stop_order_id")
        pos["disaster_stop_order_id"] = pos.get("broker_stop_order_id")
        pos["broker_stop_amount"] = runner_amount
        pos["broker_stop_price"] = safe_float(pos.get("stop"))
        pos["broker_stop_status"] = stop_result.get("status")
        pos["broker_stop_confirmed_at"] = stop_confirmed_at
        falcon_update_registry_management(
            pos,
            tp50_status="REAL_EXECUTED",
            stop_resize=stop_result,
            stop_update_reason="TP50_RESIZE",
            stop_update=stop_result,
            stop_update_status=stop_result.get("status"),
            stop_update_failed=False,
            stop_update_recovered=False,
            stop_update_confirmed=True,
            stop_update_confirmed_at=stop_confirmed_at,
            stop_update_final_protection_confirmed=True,
            disaster_stop_confirmed=True,
        )
        return {
            "ok": True,
            "status": "TP50_REAL_EXECUTED_RUNNER_PROTECTED",
            "sent": True,
            "confirmed": True,
            "position_closed": False,
            "protected": True,
            "runner_amount": runner_amount,
            "close_order": close_result,
            "stop_resize": stop_result,
            "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        }

    rollback = stop_result.get("rollback") if isinstance(stop_result, dict) and isinstance(stop_result.get("rollback"), dict) else {}
    if rollback.get("ok"):
        rollback_confirmed_at = data_hora_sp_str()
        pos["broker_stop_order_id"] = rollback.get("order_id")
        pos["disaster_stop_order_id"] = rollback.get("order_id")
        pos["broker_stop_amount"] = runner_amount
        pos["broker_stop_price"] = rollback.get("stop_price") or pos.get("stop")
        pos["broker_stop_status"] = "ROLLBACK_PROTECTED"
        pos["broker_stop_confirmed_at"] = rollback_confirmed_at
        falcon_update_registry_management(
            pos,
            tp50_status="REAL_EXECUTED_STOP_ROLLBACK",
            stop_resize=stop_result,
            stop_update_reason="TP50_RESIZE",
            stop_update=stop_result,
            stop_update_status=stop_result.get("status"),
            stop_update_failed=True,
            stop_update_recovered=True,
            stop_update_confirmed=False,
            stop_update_confirmed_at=rollback_confirmed_at,
            stop_update_final_protection_confirmed=True,
            disaster_stop_confirmed=True,
        )
        return {
            "ok": True,
            "status": "TP50_REAL_EXECUTED_STOP_ROLLBACK_PROTECTED",
            "sent": True,
            "confirmed": True,
            "position_closed": False,
            "protected": True,
            "runner_amount": runner_amount,
            "close_order": close_result,
            "stop_resize": stop_result,
            "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        }

    stop_failure_confirmed_at = data_hora_sp_str()
    falcon_update_registry_management(
        pos,
        tp50_status="REAL_EXECUTED_STOP_UPDATE_FAILED",
        stop_resize=stop_result,
        stop_update_reason="TP50_RESIZE",
        stop_update=stop_result,
        stop_update_status=stop_result.get("status") if isinstance(stop_result, dict) else "STOP_UPDATE_FAILED",
        stop_update_failed=True,
        stop_update_recovered=False,
        stop_update_confirmed=False,
        stop_update_confirmed_at=stop_failure_confirmed_at,
        stop_update_final_protection_confirmed=False,
        broker_stop_order_id=None,
        broker_stop_price=None,
        broker_stop_amount=None,
        broker_stop_status=stop_result.get("status") if isinstance(stop_result, dict) else "STOP_UPDATE_FAILED",
        broker_stop_confirmed_at=stop_failure_confirmed_at,
        disaster_stop_confirmed=False,
    )

    if FALCON_MANAGEMENT_FAILSAFE_ENABLED and hasattr(central_broker, "managed_close_position_market"):
        auth = falcon_issue_management_token(pos, "TP50_RUNNER_FAILSAFE_CLOSE", {"amount": runner_amount})
        token = auth.get("token") if isinstance(auth, dict) else None
        if token:
            failsafe_reservation = falcon_prepare_position_client_order_id(
                pos, ROLE_MANAGED_CLOSE, 1, attempt=0
            )
            if failsafe_reservation.get("send_allowed") is True:
                failsafe = central_broker.managed_close_position_market(
                    symbol=pos.get("symbol"),
                    side=pos.get("side"),
                    amount=runner_amount,
                    expected_position_amount=runner_amount,
                    client_tag=failsafe_reservation.get("client_order_id"),
                    reason="TP50_STOP_RESIZE_FAILED",
                    execution_auth_token=token,
                    client_order_id_reservation=failsafe_reservation,
                )
            else:
                failsafe = {
                    "ok": False,
                    "status": "FAILSAFE_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
                    "sent": False,
                    "confirmed": False,
                    "client_order_id_reservation": failsafe_reservation,
                    "reconciliation_required": True,
                }
        else:
            failsafe = {
                "ok": False,
                "status": "FAILSAFE_AUTH_MISSING",
                "auth": _falcon_terminal_auth_projection(auth, False),
            }
        if failsafe.get("confirmed"):
            pos["remaining_qty"] = 0.0
            pos["runner_qty"] = 0.0
            return {
                "ok": True,
                "status": "TP50_REAL_EXECUTED_RUNNER_FAILSAFE_CLOSED",
                "sent": True,
                "confirmed": True,
                "position_closed": True,
                "protected": True,
                "close_order": close_result,
                "stop_resize": stop_result,
                "failsafe_close": failsafe,
                "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
            }
        return {
            "ok": False,
            "status": "TP50_REAL_CRITICAL_RUNNER_UNPROTECTED",
            "sent": True,
            "confirmed": True,
            "position_closed": False,
            "protected": False,
            "close_order": close_result,
            "stop_resize": stop_result,
            "failsafe_close": failsafe,
            "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        }

    return {
        "ok": False,
        "status": "TP50_REAL_CRITICAL_RUNNER_UNPROTECTED",
        "sent": True,
        "confirmed": True,
        "position_closed": False,
        "protected": False,
        "close_order": close_result,
        "stop_resize": stop_result,
        "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
    }


def falcon_try_execute_tp50_real_partial(pos, price):
    result = {
        "ok": True,
        "version": FALCON_TP50_REAL_EXECUTION_AUDIT_VERSION,
        "management_version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
        "status": "TP50_VIRTUAL_ONLY",
        "sent": False,
        "confirmed": False,
        "protected": True,
        "symbol": pos.get("symbol"),
        "side": pos.get("side"),
        "price": price,
        "reason": "not_live_or_no_real_order",
    }
    if not falcon_is_live_real_position(pos):
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result
    required = ["tp50_partial_amount", "managed_close_position_market", "managed_position_snapshot", "replace_position_stop_order"]
    missing = [name for name in required if central_broker is None or not hasattr(central_broker, name)]
    if missing:
        result.update({"ok": False, "status": "TP50_REAL_HELPER_MISSING", "reason": ",".join(missing)})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    # Recupera uma redução enviada anteriormente sem duplicar a ordem.
    if pos.get("tp50_partial_pending"):
        before = safe_float(pos.get("tp50_pre_amount"), falcon_real_remaining_qty(pos))
        intended = safe_float(pos.get("tp50_intended_amount"), 0.0)
        snapshot = central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side"))
        current = safe_float(snapshot.get("amount"), None) if isinstance(snapshot, dict) else None
        order_snapshot = central_broker.managed_order_snapshot(pos.get("symbol"), pos.get("tp50_real_order_id")) if hasattr(central_broker, "managed_order_snapshot") else {}
        if current is not None and current <= max(0.0, before - intended) + max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, before * 1e-6):
            recovered_close = {"order_id": pos.get("tp50_real_order_id"), "filled_amount": intended, "remaining_amount": current, "confirmed": True, "recovered": True, "order_snapshot": order_snapshot}
            result = _falcon_finalize_tp50_after_partial(pos, current, price, recovered_close)
            HEALTH["last_tp50_execution_status"] = result.get("status")
            return result
        status = str((order_snapshot or {}).get("status") or "UNKNOWN").upper()
        if status not in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "ERROR"}:
            result.update({"ok": True, "status": "TP50_REAL_PARTIAL_PENDING_CONFIRMATION", "sent": True, "confirmed": False, "position_snapshot": snapshot, "order_snapshot": order_snapshot})
            HEALTH["last_tp50_execution_status"] = result["status"]
            return result
        pos["tp50_partial_pending"] = False

    total_amount = falcon_real_remaining_qty(pos)
    partial = central_broker.tp50_partial_amount(pos.get("symbol"), total_amount)
    result["partial_audit"] = partial
    if not partial.get("ok"):
        result.update({"ok": False, "status": "TP50_REAL_BLOCKED_MIN_QTY", "reason": "posição LIVE não comporta parcial mínima"})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    close_amount = safe_float(partial.get("tp50_amount"), 0.0)
    auth = falcon_issue_management_token(pos, "TP50_REAL_PARTIAL", {"amount": close_amount, "expected_position_amount": total_amount})
    token = auth.get("token") if isinstance(auth, dict) else None
    if not token:
        result.update({"ok": False, "status": "TP50_REAL_AUTH_TOKEN_MISSING", "auth": auth})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    tp50_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "amount": safe_float(close_amount, None),
                "before": safe_float(total_amount, None),
                "role": ROLE_TP50_CLOSE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    tp50_pending = (
        pos.get("tp50_client_order_id_pending")
        if isinstance(pos.get("tp50_client_order_id_pending"), dict)
        else {}
    )
    if tp50_pending.get("logical_fingerprint") == tp50_fingerprint:
        tp50_revision = int(tp50_pending.get("revision") or 0)
    else:
        tp50_revision = int(pos.get("tp50_client_order_id_revision") or 0) + 1
        tp50_pending = {
            "logical_fingerprint": tp50_fingerprint,
            "revision": tp50_revision,
            "created_at": data_hora_sp_str(),
        }
        pos["tp50_client_order_id_revision"] = tp50_revision
        pos["tp50_client_order_id_pending"] = tp50_pending
    tp50_reservation = falcon_prepare_position_client_order_id(
        pos, ROLE_TP50_CLOSE, tp50_revision, attempt=0
    )
    tp50_pending.update({
        "client_order_id": tp50_reservation.get("client_order_id"),
        "reservation_status": tp50_reservation.get("status"),
    })
    if tp50_reservation.get("send_allowed") is not True:
        pos["tp50_partial_pending"] = True
        result.update({
            "ok": False,
            "status": "TP50_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
            "sent": False,
            "confirmed": False,
            "client_order_id_reservation": tp50_reservation,
            "reconciliation_required": True,
        })
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    close_result = central_broker.managed_close_position_market(
        symbol=pos.get("symbol"),
        side=pos.get("side"),
        amount=close_amount,
        expected_position_amount=total_amount,
        client_tag=tp50_reservation.get("client_order_id"),
        reason="TP50_REAL_PARTIAL",
        execution_auth_token=token,
        client_order_id_reservation=tp50_reservation,
    )
    pos["tp50_pre_amount"] = total_amount
    pos["tp50_intended_amount"] = close_amount
    pos["tp50_real_order_id"] = close_result.get("order_id") if isinstance(close_result, dict) else None
    if isinstance(close_result, dict) and (
        close_result.get("sent") is None
        or close_result.get("send_outcome_unknown") is True
    ):
        pos["tp50_partial_pending"] = True
        pos["tp50_client_order_id"] = tp50_reservation.get("client_order_id")
        result.update({
            "ok": False,
            "status": "TP50_REAL_PARTIAL_SEND_OUTCOME_UNKNOWN",
            "sent": None,
            "confirmed": None,
            "close_order": close_result,
            "reconciliation_required": True,
        })
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result
    if not (isinstance(close_result, dict) and close_result.get("sent")):
        if _falcon_terminal_pre_send_not_sent_proven(close_result or {}):
            pos.pop("tp50_client_order_id_pending", None)
        result.update({"ok": False, "status": (close_result or {}).get("status", "TP50_REAL_CLOSE_FAILED"), "close_order": close_result})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result
    if not close_result.get("confirmed"):
        pos["tp50_partial_pending"] = True
        pos["tp50_client_order_id"] = tp50_reservation.get("client_order_id")
        result.update({"ok": True, "status": "TP50_REAL_PARTIAL_PENDING_CONFIRMATION", "sent": True, "confirmed": False, "close_order": close_result})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    runner = safe_float(close_result.get("remaining_amount"), safe_float(partial.get("runner_amount"), 0.0))
    pos["tp50_client_order_id"] = tp50_reservation.get("client_order_id")
    pos.pop("tp50_client_order_id_pending", None)
    result = _falcon_finalize_tp50_after_partial(pos, runner, price, close_result)
    HEALTH["last_tp50_execution_status"] = result.get("status")
    HEALTH["last_real_management_action"] = {"action": "TP50", "status": result.get("status"), "symbol": pos.get("symbol"), "ts": data_hora_sp_str()}
    if not result.get("ok"):
        HEALTH["last_real_management_error"] = result.get("status")
    return result


def falcon_apply_live_stop_update(pos, new_stop, reason):
    remaining = falcon_real_remaining_qty(pos)
    if remaining <= FALCON_MANAGEMENT_AMOUNT_TOLERANCE:
        return {"ok": False, "status": "STOP_UPDATE_NO_REMAINING_POSITION"}
    result = _falcon_resize_runner_stop(pos, remaining, new_stop, reason)
    applied = bool(isinstance(result, dict) and result.get("ok") and str(result.get("status", "")).startswith("STOP_REPLACED"))
    if applied:
        stop_confirmed_at = data_hora_sp_str()
        pos["stop"] = new_stop
        pos["broker_stop_price"] = new_stop
        pos["broker_stop_amount"] = remaining
        pos["broker_stop_order_id"] = result.get("new_order_id") or pos.get("broker_stop_order_id")
        pos["disaster_stop_order_id"] = pos.get("broker_stop_order_id")
        pos["broker_stop_status"] = result.get("status")
        pos["broker_stop_confirmed_at"] = stop_confirmed_at
        falcon_update_registry_management(
            pos,
            stop_update_reason=reason,
            stop_update=result,
            stop_update_status=result.get("status"),
            stop_update_failed=False,
            stop_update_recovered=False,
            stop_update_confirmed=True,
            stop_update_confirmed_at=stop_confirmed_at,
            stop_update_final_protection_confirmed=True,
            disaster_stop_confirmed=True,
        )
    elif isinstance(result, dict) and result.get("ok") is False:
        # Persistir a falha factual somente como evidência observacional. A
        # chamada é fail-open e não altera o retorno nem tenta recovery/ordem.
        rollback = result.get("rollback") if isinstance(result.get("rollback"), dict) else {}
        rollback_protected = bool(rollback.get("ok") and rollback.get("order_id"))
        stop_observed_at = data_hora_sp_str()
        falcon_update_registry_management(
            pos,
            stop_update_reason=reason,
            stop_update=result,
            stop_update_status=result.get("status"),
            stop_update_failed=True,
            stop_update_recovered=rollback_protected,
            stop_update_confirmed=False,
            stop_update_confirmed_at=stop_observed_at,
            stop_update_final_protection_confirmed=rollback_protected,
            broker_stop_order_id=rollback.get("order_id") if rollback_protected else None,
            broker_stop_price=rollback.get("stop_price") if rollback_protected else None,
            broker_stop_amount=rollback.get("amount") if rollback_protected else None,
            broker_stop_status="ROLLBACK_PROTECTED" if rollback_protected else result.get("status"),
            broker_stop_confirmed_at=stop_observed_at,
            disaster_stop_confirmed=rollback_protected,
        )
    HEALTH["last_real_management_action"] = {"action": reason, "status": result.get("status") if isinstance(result, dict) else None, "symbol": pos.get("symbol"), "ts": data_hora_sp_str()}
    if not applied:
        HEALTH["last_real_management_error"] = result.get("status") if isinstance(result, dict) else "STOP_UPDATE_UNKNOWN"
    return {"ok": applied, "applied": applied, "status": result.get("status") if isinstance(result, dict) else "STOP_UPDATE_UNKNOWN", "broker_result": result}


def falcon_handle_live_stop_cross(pid, pos, price, force_fail_safe=False, verified_position_snapshot=None, verified_order_snapshot=None):
    remaining_expected = falcon_real_remaining_qty(pos)
    snapshot = verified_position_snapshot if isinstance(verified_position_snapshot, dict) else (
        central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side"), expected_amount=remaining_expected) if central_broker and hasattr(central_broker, "managed_position_snapshot") else {"ok": False, "status": "POSITION_HELPER_MISSING"}
    )
    current_amount = safe_float(snapshot.get("amount"), None) if isinstance(snapshot, dict) else None
    stop_order_id = pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
    order_snapshot = verified_order_snapshot if isinstance(verified_order_snapshot, dict) else (
        central_broker.managed_order_snapshot(pos.get("symbol"), stop_order_id) if central_broker and hasattr(central_broker, "managed_order_snapshot") else {}
    )

    if snapshot.get("ok") and snapshot.get("position_closed"):
        stop_fill = _falcon_confirmed_stop_fill_evidence(pos, pid, order_snapshot, remaining_expected)
        if stop_fill.get("confirmed"):
            HEALTH["last_live_stop_status"] = "BROKER_STOP_CONFIRMED_POSITION_CLOSED"
            close_position(pid, pos, stop_fill.get("average"), "STOP_BROKER_CONFIRMED")
            return {"closed": True, "status": "BROKER_STOP_CONFIRMED_POSITION_CLOSED", "snapshot": snapshot, "order_snapshot": order_snapshot}
        verification = falcon_verify_live_disaster_stop(pos, force=True)
        HEALTH["last_live_stop_status"] = verification.get("status")
        return {
            "closed": False,
            "status": verification.get("status") or "BROKER_FLAT_WITHOUT_CONFIRMED_STOP_FILL",
            "central_only_reconcile_required": bool(verification.get("central_only_reconcile_required")),
            "snapshot": snapshot,
            "order_snapshot": order_snapshot,
            "verification": verification,
        }

    if not snapshot.get("ok"):
        HEALTH["last_live_stop_status"] = "STOP_POSITION_SNAPSHOT_ERROR"
        HEALTH["last_real_management_error"] = snapshot.get("error") or snapshot.get("status")
        return {"closed": False, "status": "STOP_POSITION_SNAPSHOT_ERROR", "snapshot": snapshot}

    if remaining_expected > 0 and abs((current_amount or 0.0) - remaining_expected) > max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, remaining_expected * 1e-6):
        HEALTH["last_live_stop_status"] = "STOP_POSITION_AMOUNT_MISMATCH"
        HEALTH["last_real_management_error"] = "STOP_POSITION_AMOUNT_MISMATCH"
        return {"closed": False, "status": "STOP_POSITION_AMOUNT_MISMATCH", "snapshot": snapshot}

    now = time.time()
    first_seen = safe_float(pos.get("live_stop_crossed_epoch"), None)
    order_status = str((order_snapshot or {}).get("status") or "UNKNOWN").upper()
    # Erro transitório de leitura não prova ausência do stop e nunca acelera um
    # fechamento destrutivo. Somente um estado factual inativo/not-found pode
    # habilitar a política fail-safe existente.
    order_flags = _falcon_stop_status_flags(order_status, order_snapshot)
    stop_invalid = bool(order_flags.get("cancelled") or order_flags.get("rejected") or order_flags.get("filled") or _falcon_stop_not_found_evidence(order_snapshot))
    if first_seen is None:
        pos["live_stop_crossed_epoch"] = now
        pos["live_stop_crossed_at"] = data_hora_sp_str()
        record_event("LIVE_STOP_TRIGGER_WAIT", pos, {"price": price, "broker_snapshot": snapshot, "stop_order": order_snapshot})
        if not (FALCON_MANAGEMENT_FAILSAFE_ENABLED and (stop_invalid or force_fail_safe)):
            HEALTH["last_live_stop_status"] = "WAITING_BROKER_STOP_EXECUTION"
            return {"closed": False, "status": "WAITING_BROKER_STOP_EXECUTION", "snapshot": snapshot, "order_snapshot": order_snapshot}
        first_seen = now - FALCON_MANAGEMENT_STOP_GRACE_SECONDS

    elapsed = now - first_seen
    if not FALCON_MANAGEMENT_FAILSAFE_ENABLED or (elapsed < FALCON_MANAGEMENT_STOP_GRACE_SECONDS and not stop_invalid and not force_fail_safe):
        HEALTH["last_live_stop_status"] = "WAITING_BROKER_STOP_EXECUTION"
        return {"closed": False, "status": "WAITING_BROKER_STOP_EXECUTION", "elapsed": elapsed, "snapshot": snapshot, "order_snapshot": order_snapshot}

    protective_evidence = _falcon_protective_stop_evidence(
        order_snapshot,
        falcon_position_identity(pos, position_id=pid),
        expected_amount=remaining_expected,
    )
    protective_order_proven = bool(
        stop_order_id
        and protective_evidence.get("protective")
        and pos.get("entry_ownership_verified") is True
    )
    if not protective_order_proven:
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_OWNERSHIP_EVIDENCE_INSUFFICIENT"
        HEALTH["last_real_management_error"] = "STOP_FAILSAFE_OWNERSHIP_EVIDENCE_INSUFFICIENT"
        return {
            "closed": False,
            "status": "STOP_FAILSAFE_OWNERSHIP_EVIDENCE_INSUFFICIENT",
            "manual_intervention_required": True,
            "snapshot": snapshot,
            "order_snapshot": order_snapshot,
        }

    # The ordinary stop-cross fail-safe and the terminal-stop emergency are
    # both destructive closes for the same lifecycle.  Reserve the same
    # cross-worker lifecycle key before either path can issue auth, cancel a
    # stop, or call the market-close helper.
    lifecycle_lock_id = falcon_terminal_stop_lifecycle_lock_id(pos)
    owner_nonce = secrets.token_hex(24)
    lifecycle_lock = falcon_terminal_stop_acquire_lifecycle_lock(
        lifecycle_lock_id,
        owner_nonce,
    )
    lifecycle_lock_projection = {
        "acquired": lifecycle_lock.get("acquired") is True,
        "status": _falcon_terminal_safe_text(lifecycle_lock.get("status"), 120),
        "authoritative_lock_present": lifecycle_lock.get("authoritative_lock_present"),
        "reconciliation_required": lifecycle_lock.get("acquired") is not True,
        "reconcile_by_client_order_id": falcon_position_identity(pos).get("client_order_id"),
    }
    if lifecycle_lock.get("acquired") is not True:
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_LIFECYCLE_LOCK_BLOCKED"
        HEALTH["last_real_management_error"] = "STOP_FAILSAFE_LIFECYCLE_LOCK_BLOCKED"
        return {
            "closed": False,
            "status": "STOP_FAILSAFE_LIFECYCLE_LOCK_BLOCKED",
            "manual_intervention_required": True,
            "lifecycle_lock": lifecycle_lock_projection,
            "snapshot": snapshot,
            "order_snapshot": order_snapshot,
        }

    def release_lifecycle_lock_before_send():
        return falcon_terminal_stop_release_lifecycle_lock(
            lifecycle_lock_id,
            owner_nonce,
        )

    # Evita que um stop residual dispare depois do market fail-safe e reverta a perna.
    cancel_result = None
    if stop_order_id and hasattr(central_broker, "cancel_managed_stop_order"):
        cancel_auth = falcon_issue_management_token(pos, "STOP_FAILSAFE_CANCEL", {"order_id": stop_order_id})
        cancel_token = cancel_auth.get("token") if isinstance(cancel_auth, dict) else None
        if cancel_token:
            cancel_result = central_broker.cancel_managed_stop_order(pos.get("symbol"), stop_order_id, execution_auth_token=cancel_token, reason="STOP_FAILSAFE_PRE_CLOSE")

    # Reconsulta após tentar cancelar: se o stop executou nesse intervalo, não envia market duplicado.
    post_cancel_snapshot = central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side"), expected_amount=remaining_expected)
    if isinstance(post_cancel_snapshot, dict) and post_cancel_snapshot.get("position_closed"):
        final_order_snapshot = central_broker.managed_order_snapshot(pos.get("symbol"), stop_order_id) if hasattr(central_broker, "managed_order_snapshot") else order_snapshot
        final_stop_fill = _falcon_confirmed_stop_fill_evidence(pos, pid, final_order_snapshot, remaining_expected)
        if final_stop_fill.get("confirmed"):
            lifecycle_lock_release = release_lifecycle_lock_before_send()
            HEALTH["last_live_stop_status"] = "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE"
            close_position(pid, pos, final_stop_fill.get("average"), "STOP_BROKER_CONFIRMED")
            return {"closed": True, "status": "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot, "order_snapshot": final_order_snapshot, "lifecycle_lock_release": lifecycle_lock_release}
        verification = falcon_verify_live_disaster_stop(pos, force=True)
        lifecycle_lock_release = release_lifecycle_lock_before_send()
        HEALTH["last_live_stop_status"] = verification.get("status")
        return {
            "closed": False,
            "status": verification.get("status") or "BROKER_FLAT_AFTER_CANCEL_WITHOUT_CONFIRMED_FILL",
            "central_only_reconcile_required": bool(verification.get("central_only_reconcile_required")),
            "cancel_stop": cancel_result,
            "snapshot": post_cancel_snapshot,
            "order_snapshot": final_order_snapshot,
            "verification": verification,
            "lifecycle_lock_release": lifecycle_lock_release,
        }
    post_cancel_amount = safe_float((post_cancel_snapshot or {}).get("amount"), current_amount)
    if not (isinstance(post_cancel_snapshot, dict) and post_cancel_snapshot.get("ok")):
        lifecycle_lock_release = release_lifecycle_lock_before_send()
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR"
        return {"closed": False, "status": "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot, "lifecycle_lock_release": lifecycle_lock_release}
    if not post_cancel_snapshot.get("ownership_safe") or abs((post_cancel_amount or 0.0) - remaining_expected) > max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, remaining_expected * 1e-6):
        lifecycle_lock_release = release_lifecycle_lock_before_send()
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_POST_CANCEL_OWNERSHIP_UNSAFE"
        return {"closed": False, "status": "STOP_FAILSAFE_POST_CANCEL_OWNERSHIP_UNSAFE", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot, "lifecycle_lock_release": lifecycle_lock_release}

    legacy_close_reservation = falcon_prepare_position_client_order_id(
        pos, ROLE_EMERGENCY_TERMINAL_STOP_CLOSE, 1, attempt=0
    )
    if legacy_close_reservation.get("send_allowed") is not True:
        HEALTH["last_live_stop_status"] = (
            "STOP_FAILSAFE_CLIENT_ORDER_ID_RESERVATION_BLOCKED"
        )
        HEALTH["last_real_management_error"] = (
            "STOP_FAILSAFE_CLIENT_ORDER_ID_RESERVATION_BLOCKED"
        )
        return {
            "closed": False,
            "status": "STOP_FAILSAFE_CLIENT_ORDER_ID_RESERVATION_BLOCKED",
            "manual_intervention_required": True,
            "client_order_id_reservation": legacy_close_reservation,
            "cancel_stop": cancel_result,
            "snapshot": post_cancel_snapshot,
        }
    legacy_close_client_tag = legacy_close_reservation.get("client_order_id")
    close_auth = falcon_issue_management_token(pos, "STOP_FAILSAFE_CLOSE", {"amount": post_cancel_amount})
    close_token = close_auth.get("token") if isinstance(close_auth, dict) else None
    failsafe = central_broker.managed_close_position_market(
        symbol=pos.get("symbol"),
        side=pos.get("side"),
        amount=post_cancel_amount,
        expected_position_amount=post_cancel_amount,
        client_tag=legacy_close_client_tag,
        reason="STOP_BROKER_NOT_CONFIRMED",
        execution_auth_token=close_token,
        client_order_id_reservation=legacy_close_reservation,
    ) if close_token else {"ok": False, "status": "STOP_FAILSAFE_AUTH_MISSING", "auth": close_auth}

    failsafe_projection = _falcon_terminal_stop_result_projection(
        failsafe,
        expected_client_order_id=legacy_close_client_tag,
        expected_symbol=pos.get("symbol"),
        expected_side=pos.get("side"),
        expected_amount=post_cancel_amount,
    )
    lifecycle_lock_release = None
    if not close_token:
        lifecycle_lock_release = release_lifecycle_lock_before_send()
    elif _falcon_terminal_pre_send_not_sent_proven(failsafe_projection):
        lifecycle_lock_release = release_lifecycle_lock_before_send()

    if failsafe_projection.get("confirmed") is True:
        exit_price = safe_float(failsafe_projection.get("average"), price)
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_MARKET_CONFIRMED"
        close_position(pid, pos, exit_price, "STOP_FAILSAFE_MARKET")
        return {"closed": True, "status": "STOP_FAILSAFE_MARKET_CONFIRMED", "cancel_stop": cancel_result, "failsafe": failsafe_projection, "lifecycle_lock_release": lifecycle_lock_release}

    HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED"
    HEALTH["last_real_management_error"] = "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED"
    safe_send_telegram(
        f"🔴 FALCON LIVE CRÍTICO — {pos.get('symbol')}\n\n"
        f"Stop cruzado, mas fechamento não foi confirmado.\n"
        f"Status: {failsafe_projection.get('status')}\n"
        f"Quantidade broker: {current_amount}\n"
        f"Verificação manual imediata necessária.",
        event_type="LIVE_MANAGEMENT_ERROR",
        mode="LIVE",
        operational_critical=True,
    )
    return {"closed": False, "status": "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED", "cancel_stop": cancel_result, "failsafe": failsafe_projection, "lifecycle_lock_release": lifecycle_lock_release}


# Gestão substituta: PAPER permanece igual; LIVE usa confirmação broker.
def management_loop():
    while True:
        try:
            positions = get_positions()
            closed_pids = []

            for pid, pos in list(positions.items()):
                symbol = pos["symbol"]
                side = pos["side"]
                entry = safe_float(pos["entry"])
                stop = safe_float(pos["stop"])
                tp50 = safe_float(pos["tp50"])
                initial_stop = safe_float(pos.get("initial_stop", stop))
                is_real = falcon_is_live_real_position(pos)

                live_mode = str(pos.get("execution_mode") or "").upper() == "LIVE" or str(pos.get("registry_mode") or "").upper() == "REAL"
                if live_mode and not is_real:
                    pos["live_management_block_reason"] = "LIVE_ORDER_IDENTITY_INSUFFICIENT"
                    pos["stop_anomaly_detected"] = True
                    pos["stop_anomaly_last_reason"] = "LIVE_ORDER_IDENTITY_INSUFFICIENT"
                    HEALTH["falcon_stop_anomaly_detected"] = True
                    HEALTH["falcon_stop_anomaly_last_reason"] = "LIVE_ORDER_IDENTITY_INSUFFICIENT"
                    alert = falcon_management_alert_decision(pos, "LIVE_ORDER_IDENTITY_INSUFFICIENT", position_id=pid)
                    if alert.get("send"):
                        record_event("FALCON_LIVE_IDENTITY_INSUFFICIENT", pos, {"position_id": pid})
                        safe_send_telegram(
                            f"FALCON LIVE IDENTITY INSUFFICIENT - {symbol}\n\n"
                            f"Side: {side}\n"
                            f"A gestao LIVE foi bloqueada antes de TP50, BE, trailing ou close.\n"
                            f"Reconciliacao manual e necessaria.",
                            event_type="FALCON_LIVE_IDENTITY_INSUFFICIENT",
                            mode="LIVE",
                            operational_critical=True,
                        )
                    positions[pid] = pos
                    continue

                # Preflight obrigatório: nenhuma gestão normal pode ocorrer se
                # a perna já não existe no broker ou se a proteção física está
                # factual/criticamente inválida.
                if is_real:
                    verification = falcon_verify_live_disaster_stop(pos)
                    if not verification.get("management_allowed"):
                        reason = str(verification.get("status") or "LIVE_MANAGEMENT_PREFLIGHT_BLOCKED")
                        # Terminal protection recovery is deliberately evaluated
                        # before every normal-management ``continue``.  It can
                        # authorize only the emergency market close; TP50, BE,
                        # trailing and the ordinary stop-cross path remain
                        # blocked by the preflight result.
                        terminal_recovery = falcon_handle_terminal_stop_emergency(
                            pid,
                            pos,
                            verification,
                        )
                        pos["terminal_stop_emergency_last_decision"] = terminal_recovery
                        if terminal_recovery.get("incident_detected"):
                            positions[pid] = pos
                            continue
                        alert = falcon_management_alert_decision(pos, reason, position_id=pid)
                        if verification.get("central_only_reconcile_required"):
                            if alert.get("send"):
                                record_event("FALCON_CENTRAL_ONLY_RECONCILE_REQUIRED", pos, {"verification": verification})
                                safe_send_telegram(
                                    f"🔴 FALCON CENTRAL-ONLY RECONCILE REQUIRED - {symbol}\n\n"
                                    f"Side: {side}\n"
                                    f"Order: {pos.get('live_order_id') or pos.get('bingx_order_id')}\n"
                                    f"Client: {pos.get('live_client_order_id')}\n"
                                    f"A BingX está flat; TP50, parcial, BE, trailing e close normal foram interrompidos.\n"
                                    f"Use /falcon/centralonly/reconcile/text para preview factual.",
                                    event_type="FALCON_CENTRAL_ONLY_RECONCILE_REQUIRED",
                                    mode="LIVE",
                                    operational_critical=True,
                                )
                            positions[pid] = pos
                            continue

                        if alert.get("send"):
                            record_event("FALCON_DISASTER_STOP_VERIFICATION_BLOCKED", pos, {"verification": verification})
                            safe_send_telegram(
                                f"🔴 FALCON DISASTER STOP VERIFICATION BLOCKED - {symbol}\n\n"
                                f"Side: {side}\n"
                                f"Status: {verification.get('status')}\n"
                                f"Stop order: {verification.get('stop_order_id')} / {verification.get('stop_order_status')}\n"
                                f"Posição broker: {verification.get('position_qty')}\n"
                                f"Gestão normal bloqueada; intervenção manual pode ser necessária.",
                                event_type="FALCON_DISASTER_STOP_ANOMALY",
                                mode="LIVE",
                                operational_critical=True,
                            )

                        positions[pid] = pos
                        continue

                # A entrada e o disaster stop podem estar factual e
                # operacionalmente confirmados mesmo quando a persistencia do
                # ACK falha. Nesse estado, a verificacao/recovery de protecao
                # acima continua ativa, mas nenhuma gestao normal pode operar
                # ate que a reconciliacao explicita libere o lifecycle.
                if is_real and pos.get("live_management_reconciliation_pending") is True:
                    pos["live_management_block_reason"] = (
                        "ENTRY_ACK_PERSISTENCE_RECONCILIATION_REQUIRED"
                    )
                    positions[pid] = pos
                    continue

                if pos.get("live_management_block_reason") == (
                    "ENTRY_ACK_PERSISTENCE_RECONCILIATION_REQUIRED"
                ):
                    pos.pop("live_management_block_reason", None)

                price = safe_fetch_price(symbol)
                if price is None:
                    continue
                pos = update_mfe_mae(pos, price)

                stopped = (side == "LONG" and price <= stop) or (side == "SHORT" and price >= stop)
                if stopped:
                    if is_real:
                        live_stop = falcon_handle_live_stop_cross(pid, pos, price)
                        if live_stop.get("closed"):
                            closed_pids.append(pid)
                        else:
                            positions[pid] = pos
                        continue
                    close_position(pid, pos, stop, "STOP")
                    closed_pids.append(pid)
                    continue

                if not pos.get("tp50_hit"):
                    tp_hit = (side == "LONG" and price >= tp50) or (side == "SHORT" and price <= tp50)
                    if tp_hit:
                        last_attempt = safe_float(pos.get("tp50_last_attempt_epoch"), 0.0)
                        if not is_real or pos.get("tp50_partial_pending") or time.time() - last_attempt >= FALCON_TP50_RETRY_SECONDS:
                            pos["tp50_last_attempt_epoch"] = time.time()
                            tp50_real_execution = falcon_try_execute_tp50_real_partial(pos, price)
                            pos["tp50_real_execution"] = tp50_real_execution
                            success_real = is_real and bool(tp50_real_execution.get("confirmed")) and bool(tp50_real_execution.get("protected"))
                            virtual_success = not is_real
                            if success_real or virtual_success:
                                pos["tp50_hit"] = True
                                pos["candles_to_tp50"] = int(pos.get("management_cycles", 0))
                                pos["tp50_real_executed"] = bool(is_real and tp50_real_execution.get("sent"))
                                pos["tp50_virtual_only"] = not pos.get("tp50_real_executed")
                                pos["tp50_execution_classification"] = "REAL_EXECUTED" if pos.get("tp50_real_executed") else "VIRTUAL_ONLY"
                                record_event("TP50", pos, {"price": price, "candles_to_tp50": pos["candles_to_tp50"], "tp50_real_execution": tp50_real_execution})
                                safe_send_telegram(
                                    f"🎯 TP50 FALCON - {symbol}\n\n"
                                    f"Setup: {pos.get('setup')}\n"
                                    f"Direção: {side}\n"
                                    f"Preço atual: {fmt_price(price)}\n"
                                    f"Resultado: {fmt_pct(pnl_pct_for_side(side, entry, tp50))} | +1,00R\n\n"
                                    f"TP50 BingX: {tp50_real_execution.get('status')}\n"
                                    f"Runner protegido: {tp50_real_execution.get('protected')}",
                                    event_type="TP50_LIVE" if is_real else "TP50_PAPER",
                                    mode="LIVE" if is_real else "PAPER",
                                )
                                if tp50_real_execution.get("position_closed"):
                                    close_position(pid, pos, price, "TP50_FAILSAFE_FULL_CLOSE")
                                    closed_pids.append(pid)
                                    continue
                            else:
                                record_event("TP50_MANAGEMENT_PENDING", pos, {"price": price, "tp50_real_execution": tp50_real_execution})
                                if not tp50_real_execution.get("ok"):
                                    tp50_reason = f"TP50:{tp50_real_execution.get('status') or 'NOT_CONFIRMED'}"
                                    tp50_alert = falcon_management_alert_decision(pos, tp50_reason, position_id=pid)
                                    if tp50_alert.get("send"):
                                        safe_send_telegram(
                                            f"🔴 TP50 REAL NÃO CONFIRMADO - {symbol}\n\n"
                                            f"Status: {tp50_real_execution.get('status')}\n"
                                            f"Nenhuma nova parcial será presumida como executada.",
                                            event_type="LIVE_MANAGEMENT_ERROR",
                                            mode="LIVE",
                                            operational_critical=True,
                                        )

                current_r = r_for_side(side, entry, initial_stop, price)

                if pos.get("tp50_hit") and not pos.get("be_moved") and current_r >= BE_TRIGGER_R:
                    candidate = entry * (1 + BE_OFFSET_PCT / 100) if side == "LONG" else entry * (1 - BE_OFFSET_PCT / 100)
                    candidate = max(safe_float(pos["stop"]), candidate) if side == "LONG" else min(safe_float(pos["stop"]), candidate)
                    if is_real:
                        update = falcon_apply_live_stop_update(pos, candidate, "BE")
                        if update.get("applied"):
                            pos["be_moved"] = True
                            record_event("BE", pos, {"new_stop": pos["stop"], "trigger_r": current_r, "broker_update": update})
                            safe_send_telegram(f"🟡 BE REAL FALCON - {symbol}\n\nStop BingX confirmado: {fmt_price(pos['stop'])}\nR atual: {fmt_r(current_r)}", event_type="BREAK_EVEN_LIVE", mode="LIVE")
                    else:
                        pos["stop"] = candidate
                        pos["be_moved"] = True
                        record_event("BE", pos, {"new_stop": pos["stop"], "trigger_r": current_r})
                        safe_send_telegram(f"🟡 BE FALCON - {symbol}\n\nStop movido para: {fmt_price(pos['stop'])}\nR atual: {fmt_r(current_r)}", event_type="BREAK_EVEN_PAPER", mode="PAPER")

                if pos.get("be_moved") and current_r >= TRAIL_TRIGGER_R:
                    trail = calc_chandelier_stop(pos)
                    if trail is not None:
                        old_stop = safe_float(pos["stop"])
                        improved = (side == "LONG" and trail > old_stop) or (side == "SHORT" and trail < old_stop)
                        if improved:
                            if is_real:
                                update = falcon_apply_live_stop_update(pos, trail, "TRAILING")
                                if update.get("applied"):
                                    pos["trailing_active"] = True
                                    record_event("TRAILING", pos, {"new_stop": trail, "broker_update": update})
                                    safe_send_telegram(f"🟣 TRAILING REAL FALCON - {symbol}\n\nStop BingX confirmado: {fmt_price(trail)}\nR atual: {fmt_r(current_r)}", event_type="TRAILING_UPDATED_LIVE", mode="LIVE")
                            else:
                                pos["stop"] = trail
                                pos["trailing_active"] = True
                                record_event("TRAILING", pos, {"new_stop": trail})
                                safe_send_telegram(f"🟣 TRAILING FALCON - {symbol}\n\nNovo stop: {fmt_price(trail)}\nR atual: {fmt_r(current_r)}", event_type="TRAILING_UPDATED_PAPER", mode="PAPER")

                pos["management_cycles"] = int(pos.get("management_cycles", 0)) + 1
                positions[pid] = pos

            for pid in closed_pids:
                positions.pop(pid, None)

            falcon_refresh_management_safety_health(positions)
            save_positions(positions)
            HEALTH["last_management_run"] = data_hora_sp_str()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            refresh_health_stats()

        except Exception as exc:
            HEALTH["last_error"] = f"management: {exc}"
            HEALTH["last_real_management_error"] = str(exc)
            traceback.print_exc()

        time.sleep(MANAGEMENT_SLEEP_SECONDS)


_ORIGINAL_HEALTH_PAYLOAD_BEFORE_RPM_V1 = health_payload

def health_payload():
    payload = _ORIGINAL_HEALTH_PAYLOAD_BEFORE_RPM_V1()
    safety_fields = [
        "falcon_central_only_pending_count",
        "falcon_disaster_stop_active_verified",
        "falcon_disaster_stop_trigger_type",
        "falcon_disaster_stop_order_status",
        "falcon_disaster_stop_order_id",
        "falcon_disaster_stop_last_checked_at",
        "falcon_disaster_stop_protection_matches_position",
        "falcon_stop_anomaly_detected",
        "falcon_stop_anomaly_last_reason",
        "falcon_management_spam_guard_status",
        "falcon_management_spam_guard_last_reason",
        "falcon_management_spam_guard_suppressed_count",
        "falcon_management_spam_guard_last_suppressed_at",
        "falcon_terminal_stop_recovery_status",
        "falcon_terminal_stop_recovery_incident_id",
        "falcon_terminal_stop_recovery_last_at",
        "falcon_terminal_stop_recovery_sent",
        "falcon_terminal_stop_recovery_confirmed",
    ]
    for field in safety_fields:
        payload[field] = HEALTH.get(field)
    payload["real_position_management"] = {
        "version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
        "enabled": True,
        "failsafe_enabled": FALCON_MANAGEMENT_FAILSAFE_ENABLED,
        "stop_grace_seconds": FALCON_MANAGEMENT_STOP_GRACE_SECONDS,
        "tp50_retry_seconds": FALCON_TP50_RETRY_SECONDS,
        "stop_verify_interval_seconds": FALCON_STOP_VERIFY_INTERVAL_SECONDS,
        "stop_verify_persist_seconds": FALCON_STOP_VERIFY_PERSIST_SECONDS,
        "management_alert_cooldown_seconds": FALCON_MANAGEMENT_ALERT_COOLDOWN_SECONDS,
        "broker_helpers": {
            "managed_position_snapshot": bool(central_broker is not None and hasattr(central_broker, "managed_position_snapshot")),
            "managed_close_position_market": bool(central_broker is not None and hasattr(central_broker, "managed_close_position_market")),
            "replace_position_stop_order": bool(central_broker is not None and hasattr(central_broker, "replace_position_stop_order")),
            "cancel_managed_stop_order": bool(central_broker is not None and hasattr(central_broker, "cancel_managed_stop_order")),
        },
        "last_action": HEALTH.get("last_real_management_action"),
        "last_error": HEALTH.get("last_real_management_error"),
        "last_tp50_status": HEALTH.get("last_tp50_execution_status"),
        "last_stop_replace_status": HEALTH.get("last_stop_replace_status"),
        "last_live_stop_status": HEALTH.get("last_live_stop_status"),
        "disaster_stop_verification": {field: HEALTH.get(field) for field in safety_fields if field.startswith("falcon_disaster_stop_") or field.startswith("falcon_stop_anomaly_")},
        "spam_guard": {field: HEALTH.get(field) for field in safety_fields if field.startswith("falcon_management_spam_guard_")},
        "terminal_stop_emergency_recovery": {
            field: HEALTH.get(field)
            for field in safety_fields
            if field.startswith("falcon_terminal_stop_recovery_")
        },
        "rules": [
            "LIVE TP50 exige confirmação da redução e proteção do runner.",
            "BE/trailing local só muda após confirmação do stop na BingX.",
            "Divergência de quantidade bloqueia fechamento/troca de stop.",
            "Stop LIVE cruzado exige confirmação broker ou market fail-safe.",
            "Stop terminal com posição factual aberta usa recovery exclusivo, persistente e fail-closed.",
        ],
    }
    return payload


start_threads()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
