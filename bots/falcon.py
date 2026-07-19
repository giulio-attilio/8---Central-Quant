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
from redis_bandwidth import redis_get as bandwidth_redis_get, redis_set as bandwidth_redis_set
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

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
redis_lock = threading.Lock()
position_mutation_lock = threading.RLock()
management_alert_guard_lock = threading.RLock()
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
        result = central_trade_registry.register_open_trade(
            bot="FALCON",
            symbol=normalize_symbol_for_central(pos.get("symbol")),
            side=pos.get("side"),
            entry=pos.get("entry"),
            sl=pos.get("stop") or pos.get("initial_stop"),
            tp50=pos.get("tp50"),
            setup=pos.get("setup"),
            qty=pos.get("qty") or pos.get("amount"),
            source="falcon",
            lifecycle_id=pos.get("lifecycle_id"),
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
        client_tag = f"FALCON-TP50-{str(pos.get('setup') or 'FALCON')}-{int(time.time())}"
        order = central_broker.close_position_market(
            symbol=pos.get("symbol"),
            side=pos.get("side"),
            amount=close_amount,
            client_tag=client_tag,
            reason="TP50_REAL_PARTIAL",
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
                verify_order = central_broker.place_market_order(
                    symbol=sig.get("symbol"),
                    side=sig.get("side"),
                    notional_usdt=effective_real_notional,
                    reduce_only=False,
                    client_tag=f"FALCON-VERIFY-{sig.get('setup')}-{int(time.time())}",
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
        client_tag = f"FALCON-LIVE-{sig.get('setup')}-{int(time.time())}"
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
        )
        sig["live_order"] = order
        sig["live_order_id"] = order.get("id") or order.get("order_id")
        sig["bingx_order_id"] = sig.get("live_order_id")
        HEALTH["last_execution_order"] = order
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

                    pid = sig["id"]
                    register_falcon_trade_registry_open(sig)
                    positions[pid] = sig
                    save_positions(positions)
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
    sig["disaster_stop_confirmed"] = bool(
        disaster.get("ok") is True
        and disaster.get("created") is True
        and disaster.get("order_id")
    )
    sig["real_management_version"] = FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION
    sig["registry_mode"] = "REAL"
    return sig


# Envolve a função de entrada existente sem reescrever o gate.
_ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1 = execute_signal_if_allowed

def execute_signal_if_allowed(sig, positions=None):
    allowed, decision = _ORIGINAL_EXECUTE_SIGNAL_IF_ALLOWED_BEFORE_RPM_V1(sig, positions=positions)
    order = sig.get("live_order") if isinstance(sig, dict) and isinstance(sig.get("live_order"), dict) else {}
    if allowed and order.get("sent"):
        falcon_sync_live_order_state(sig, order)
    return allowed, decision


# Envolve o registro para persistir IDs/quantidade do broker no OPEN real.
_ORIGINAL_REGISTER_FALCON_TRADE_REGISTRY_OPEN_BEFORE_RPM_V1 = register_falcon_trade_registry_open

def register_falcon_trade_registry_open(pos):
    result = _ORIGINAL_REGISTER_FALCON_TRADE_REGISTRY_OPEN_BEFORE_RPM_V1(pos)
    if falcon_is_live_real_position(pos) and central_trade_registry is not None and isinstance(result, dict) and result.get("ok"):
        try:
            trade_id = result.get("trade_id") or pos.get("trade_registry_id")
            live_order = pos.get("live_order") if isinstance(pos.get("live_order"), dict) else {}
            central_trade_registry.update_trade(
                trade_id,
                qty=falcon_real_remaining_qty(pos),
                execution_mode="LIVE",
                registry_mode="REAL",
                lifecycle_id=pos.get("lifecycle_id"),
                order_id=pos.get("live_order_id"),
                broker_order_id=pos.get("live_order_id"),
                client_order_id=pos.get("live_client_order_id") or live_order.get("client_order_id"),
                metadata={
                    "registry_mode": "REAL",
                    "lifecycle_id": pos.get("lifecycle_id"),
                    "execution_sent": True,
                    "broker_entry_reference": pos.get("broker_entry_reference"),
                    "broker_ack_at": pos.get("broker_ack_at"),
                    "broker_order_id": pos.get("live_order_id"),
                    "client_order_id": pos.get("live_client_order_id") or live_order.get("client_order_id"),
                    "broker_stop_order_id": pos.get("broker_stop_order_id"),
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
                    "real_management_version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
                },
            )
        except Exception as exc:
            HEALTH["last_real_management_error"] = f"registry live metadata: {exc}"
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
    HEALTH["falcon_disaster_stop_active_verified"] = bool(live_rows) and all(bool(row.get("disaster_stop_active_verified")) for row in live_rows)
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
            order_status = str((order_snapshot or {}).get("status") or "UNKNOWN").upper().strip()
            actual_stop_order_id = str((order_snapshot or {}).get("order_id") or (order_snapshot or {}).get("id") or "").strip()
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
                if flags["active"] and stop_order_identity_match and quantity_match and protective_type and result.get("entry_ownership_verified"):
                    result.update({"ok": True, "status": "DISASTER_STOP_ACTIVE_VERIFIED", "management_allowed": True})
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
    pos["disaster_stop_active_verified"] = bool(result.get("stop_order_active") and result.get("stop_order_identity_match") and result.get("protection_matches_position") and result.get("stop_order_protective_verified") and result.get("entry_ownership_verified"))
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


def _falcon_resize_runner_stop(pos, runner_amount, stop_price, reason):
    old_order_id = pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
    old_stop = safe_float(pos.get("broker_stop_price"), safe_float(pos.get("stop"), None))
    token_payload = falcon_issue_management_token(pos, "REPLACE_STOP", {"reason": reason, "amount": runner_amount, "new_stop": stop_price})
    token = token_payload.get("token") if isinstance(token_payload, dict) else None
    if not token:
        return {"ok": False, "status": "STOP_REPLACE_AUTH_TOKEN_MISSING", "auth": token_payload}
    try:
        result = central_broker.replace_position_stop_order(
            symbol=pos.get("symbol"),
            side=pos.get("side"),
            old_order_id=old_order_id,
            old_stop_price=old_stop,
            new_stop_price=stop_price,
            amount=runner_amount,
            expected_position_amount=runner_amount,
            client_tag=f"FALCON-{reason}-{int(time.time())}",
            reason=reason,
            execution_auth_token=token,
            allow_same_price=(reason == "TP50_RESIZE"),
        )
        HEALTH["last_stop_replace_status"] = result.get("status") if isinstance(result, dict) else None
        return result
    except Exception as exc:
        return {"ok": False, "status": "STOP_REPLACE_EXCEPTION", "error": str(exc)}


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
        failsafe = central_broker.managed_close_position_market(
            symbol=pos.get("symbol"),
            side=pos.get("side"),
            amount=runner_amount,
            expected_position_amount=runner_amount,
            client_tag=f"FALCON-TP50-FS-{int(time.time())}",
            reason="TP50_STOP_RESIZE_FAILED",
            execution_auth_token=token,
        ) if token else {"ok": False, "status": "FAILSAFE_AUTH_MISSING", "auth": auth}
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

    close_result = central_broker.managed_close_position_market(
        symbol=pos.get("symbol"),
        side=pos.get("side"),
        amount=close_amount,
        expected_position_amount=total_amount,
        client_tag=f"FALCON-TP50-{str(pos.get('setup') or 'FALCON')}-{int(time.time())}",
        reason="TP50_REAL_PARTIAL",
        execution_auth_token=token,
    )
    pos["tp50_pre_amount"] = total_amount
    pos["tp50_intended_amount"] = close_amount
    pos["tp50_real_order_id"] = close_result.get("order_id") if isinstance(close_result, dict) else None
    if not (isinstance(close_result, dict) and close_result.get("sent")):
        result.update({"ok": False, "status": (close_result or {}).get("status", "TP50_REAL_CLOSE_FAILED"), "close_order": close_result})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result
    if not close_result.get("confirmed"):
        pos["tp50_partial_pending"] = True
        result.update({"ok": True, "status": "TP50_REAL_PARTIAL_PENDING_CONFIRMATION", "sent": True, "confirmed": False, "close_order": close_result})
        HEALTH["last_tp50_execution_status"] = result["status"]
        return result

    runner = safe_float(close_result.get("remaining_amount"), safe_float(partial.get("runner_amount"), 0.0))
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
            HEALTH["last_live_stop_status"] = "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE"
            close_position(pid, pos, final_stop_fill.get("average"), "STOP_BROKER_CONFIRMED")
            return {"closed": True, "status": "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot, "order_snapshot": final_order_snapshot}
        verification = falcon_verify_live_disaster_stop(pos, force=True)
        HEALTH["last_live_stop_status"] = verification.get("status")
        return {
            "closed": False,
            "status": verification.get("status") or "BROKER_FLAT_AFTER_CANCEL_WITHOUT_CONFIRMED_FILL",
            "central_only_reconcile_required": bool(verification.get("central_only_reconcile_required")),
            "cancel_stop": cancel_result,
            "snapshot": post_cancel_snapshot,
            "order_snapshot": final_order_snapshot,
            "verification": verification,
        }
    post_cancel_amount = safe_float((post_cancel_snapshot or {}).get("amount"), current_amount)
    if not (isinstance(post_cancel_snapshot, dict) and post_cancel_snapshot.get("ok")):
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR"
        return {"closed": False, "status": "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot}
    if not post_cancel_snapshot.get("ownership_safe") or abs((post_cancel_amount or 0.0) - remaining_expected) > max(FALCON_MANAGEMENT_AMOUNT_TOLERANCE, remaining_expected * 1e-6):
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_POST_CANCEL_OWNERSHIP_UNSAFE"
        return {"closed": False, "status": "STOP_FAILSAFE_POST_CANCEL_OWNERSHIP_UNSAFE", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot}

    close_auth = falcon_issue_management_token(pos, "STOP_FAILSAFE_CLOSE", {"amount": post_cancel_amount})
    close_token = close_auth.get("token") if isinstance(close_auth, dict) else None
    failsafe = central_broker.managed_close_position_market(
        symbol=pos.get("symbol"),
        side=pos.get("side"),
        amount=post_cancel_amount,
        expected_position_amount=post_cancel_amount,
        client_tag=f"FALCON-STOP-FS-{int(time.time())}",
        reason="STOP_BROKER_NOT_CONFIRMED",
        execution_auth_token=close_token,
    ) if close_token else {"ok": False, "status": "STOP_FAILSAFE_AUTH_MISSING", "auth": close_auth}

    if failsafe.get("confirmed"):
        exit_price = safe_float(failsafe.get("average"), price)
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_MARKET_CONFIRMED"
        close_position(pid, pos, exit_price, "STOP_FAILSAFE_MARKET")
        return {"closed": True, "status": "STOP_FAILSAFE_MARKET_CONFIRMED", "cancel_stop": cancel_result, "failsafe": failsafe}

    HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED"
    HEALTH["last_real_management_error"] = "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED"
    safe_send_telegram(
        f"🔴 FALCON LIVE CRÍTICO — {pos.get('symbol')}\n\n"
        f"Stop cruzado, mas fechamento não foi confirmado.\n"
        f"Status: {failsafe.get('status')}\n"
        f"Quantidade broker: {current_amount}\n"
        f"Verificação manual imediata necessária.",
        event_type="LIVE_MANAGEMENT_ERROR",
        mode="LIVE",
        operational_critical=True,
    )
    return {"closed": False, "status": "STOP_FAILSAFE_CRITICAL_NOT_CONFIRMED", "cancel_stop": cancel_result, "failsafe": failsafe}


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
        "rules": [
            "LIVE TP50 exige confirmação da redução e proteção do runner.",
            "BE/trailing local só muda após confirmação do stop na BingX.",
            "Divergência de quantidade bloqueia fechamento/troca de stop.",
            "Stop LIVE cruzado exige confirmação broker ou market fail-safe.",
        ],
    }
    return payload


start_threads()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
