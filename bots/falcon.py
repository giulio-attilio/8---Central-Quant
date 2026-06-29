# Ajuste Central Quant: startup guard padronizado em 0 por padrão; arquitetura alinhada em FALCON.
# ==============================================================================
# FALCON STRIKE - ORB PRO - CENTRAL QUANT
# Versao: 2026-06-28-FALCON-STRIKE-ORB-V1-SUPER-HISTORY
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
import pandas as pd
import numpy as np
import ccxt
from ccxt.base.errors import NetworkError, RateLimitExceeded, ExchangeError
from flask import Flask
from upstash_redis import Redis

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

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
redis_lock = threading.Lock()

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

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
    "last_execution_decision": None,
    "last_execution_order": None,
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


def safe_send_telegram(message):
    try:
        return send_telegram(message)
    except Exception:
        return False


def redis_get_json(key, default):
    try:
        with redis_lock:
            raw = redis.get(key)
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
            redis.set(key, json.dumps(value, ensure_ascii=False))
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
    data = redis_get_json(POSITIONS_KEY, {})
    return data if isinstance(data, dict) else {}


def save_positions(positions):
    HEALTH["last_positions_count"] = len(positions)
    return redis_set_json(POSITIONS_KEY, positions)


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
    pos = pos if isinstance(pos, dict) else {}
    event = event if isinstance(event, dict) else {}
    extra = extra if isinstance(extra, dict) else {}

    execution_decision = pos.get("execution_decision") or extra.get("execution_decision") or {}
    reasons = execution_decision.get("reasons") if isinstance(execution_decision, dict) else None
    warnings = execution_decision.get("warnings") if isinstance(execution_decision, dict) else None

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
        "score": pos.get("score_falcon"),
        "quality": pos.get("quality"),
        "timeframe": pos.get("timeframe") or TIMEFRAME,
        "mode": FALCON_MODE,
        "event_created_at": event.get("created_at") or data_hora_sp_str(),
        "mfe_pct": pos.get("mfe_pct") or event.get("mfe_pct"),
        "mae_pct": pos.get("mae_pct") or event.get("mae_pct"),
        "mfe_r": pos.get("mfe_r") or event.get("mfe_r"),
        "mae_r": pos.get("mae_r") or event.get("mae_r"),
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
        "mfe_pct": safe_float(pos.get("mfe_pct")),
        "mae_pct": safe_float(pos.get("mae_pct")),
        "mfe_r": safe_float(pos.get("mfe_r")),
        "mae_r": safe_float(pos.get("mae_r")),
    }
    if extra:
        event.update(extra)
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
        "notional_usdt": FALCON_REAL_NOTIONAL_USDT,
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
                    notional_usdt=FALCON_REAL_NOTIONAL_USDT,
                    reduce_only=False,
                    client_tag=f"FALCON-VERIFY-{sig.get('setup')}-{int(time.time())}",
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

    try:
        order = central_broker.place_market_order(
            symbol=sig.get("symbol"),
            side=sig.get("side"),
            notional_usdt=FALCON_REAL_NOTIONAL_USDT,
            reduce_only=False,
            client_tag=f"FALCON-{sig.get('setup')}-{int(time.time())}",
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
                    positions[pid] = sig
                    save_positions(positions)
                    redis_list_append(SIGNALS_KEY, sig)
                    record_event("SIGNAL", sig, {"entry": sig["entry"], "stop": sig["stop"], "tp50": sig["tp50"], "execution_decision": execution_decision})
                    msg = signal_message(sig)
                    extra_exec = execution_decision_text(execution_decision)
                    if extra_exec:
                        msg += "\n\n" + extra_exec
                    safe_send_telegram(msg)
                    if FALCON_MODE == "VERIFY":
                        safe_send_telegram(verify_message(sig))
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
        f"{emoji}"
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
                        record_event("TP50", pos, {"price": price, "candles_to_tp50": pos["candles_to_tp50"]})
                        safe_send_telegram(
                            f"🎯 TP50 FALCON - {symbol}\n\n"
                            f"Setup: {pos.get('setup')}\n"
                            f"Direção: {side}\n"
                            f"Preço atual: {fmt_price(price)}\n"
                            f"Resultado: {fmt_pct(pnl_pct_for_side(side, entry, tp50))} | +1,00R\n\n"
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
    now = agora_sp()
    if now.hour != DAILY_SUMMARY_HOUR or now.minute < DAILY_SUMMARY_MINUTE:
        return
    key = f"{DAILY_SUMMARY_KEY}:{date_key()}"
    if redis_get_json(key, False):
        return
    safe_send_telegram(build_summary("DIA", trades_today()))
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
    safe_send_telegram(build_summary(f"MÊS {previous_label}", trades, period_signals_override=period_signals))
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
                    safe_send_telegram("🚨 WATCHDOG FALCON STRIKE\n\n" + "\n".join([f"- {r}" for r in reasons]))
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
                safe_send_telegram(f"🔴 THREAD FALCON TRAVOU: {name}\n\nErro:\n{exc}\n\nA thread será reiniciada.")
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
        f"Modo: {FALCON_MODE} / {'BINGX AUTO' if FALCON_MODE == 'LIVE' else ('VERIFY SEM ENVIO' if FALCON_MODE == 'VERIFY' else 'BINGX BLOQUEADA')}"
    )
    threading.Thread(target=run_thread_guarded, args=("scanner", scanner_loop), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("management", management_loop), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("summary", summary_loop), daemon=True).start()
    # Comandos do Falcon ficam centralizados no roteador da Central Quant.
    # NÃO iniciar commands_loop aqui para evitar conflito 409 getUpdates.
    # threading.Thread(target=run_thread_guarded, args=("commands", commands_loop), daemon=True).start()

    threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog_loop), daemon=True).start()


start_threads()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
