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

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
redis_lock = threading.Lock()

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


def safe_send_telegram(message, *, event_type="FALCON_NOTIFICATION", mode=None, operational_critical=False):
    result = send_automatic_telegram(
        _safe_send_telegram_transport,
        message,
        bot="FALCON",
        event_type=event_type,
        mode=mode or FALCON_MODE,
        severity="CRITICAL" if operational_critical else None,
        operational_critical=operational_critical,
    )
    return bool(result.get("sent"))


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
        f"Modo: {FALCON_MODE} / {'BINGX AUTO' if FALCON_MODE == 'LIVE' else ('VERIFY SEM ENVIO' if FALCON_MODE == 'VERIFY' else 'BINGX BLOQUEADA')}"
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
    sig["broker_entry_reference"] = order.get("price_ref")
    sig["broker_stop_order_id"] = disaster.get("order_id") or sig.get("broker_stop_order_id")
    sig["disaster_stop_order_id"] = sig.get("broker_stop_order_id")
    sig["broker_stop_price"] = disaster.get("stop_price") or sig.get("stop")
    sig["broker_stop_amount"] = disaster.get("amount") or amount
    sig["broker_stop_status"] = disaster.get("status")
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
                order_id=pos.get("live_order_id"),
                broker_order_id=pos.get("live_order_id"),
                client_order_id=pos.get("live_client_order_id") or live_order.get("client_order_id"),
                metadata={
                    "registry_mode": "REAL",
                    "execution_sent": True,
                    "broker_order_id": pos.get("live_order_id"),
                    "client_order_id": pos.get("live_client_order_id") or live_order.get("client_order_id"),
                    "broker_stop_order_id": pos.get("broker_stop_order_id"),
                    "broker_stop_price": pos.get("broker_stop_price"),
                    "broker_stop_amount": pos.get("broker_stop_amount"),
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
                "tp50_real_executed": pos.get("tp50_real_executed"),
                "tp50_real_order_id": pos.get("tp50_real_order_id"),
                "real_management_version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
                **metadata,
            },
        }
        return central_trade_registry.update_trade(trade_id, **top)
    except Exception as exc:
        HEALTH["last_real_management_error"] = f"registry management: {exc}"
        return None


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
        pos["broker_stop_order_id"] = stop_result.get("new_order_id") or pos.get("broker_stop_order_id")
        pos["disaster_stop_order_id"] = pos.get("broker_stop_order_id")
        pos["broker_stop_amount"] = runner_amount
        pos["broker_stop_price"] = safe_float(pos.get("stop"))
        pos["broker_stop_status"] = stop_result.get("status")
        falcon_update_registry_management(pos, tp50_status="REAL_EXECUTED", stop_resize=stop_result)
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
        pos["broker_stop_order_id"] = rollback.get("order_id")
        pos["disaster_stop_order_id"] = rollback.get("order_id")
        pos["broker_stop_amount"] = runner_amount
        pos["broker_stop_price"] = rollback.get("stop_price") or pos.get("stop")
        pos["broker_stop_status"] = "ROLLBACK_PROTECTED"
        falcon_update_registry_management(pos, tp50_status="REAL_EXECUTED_STOP_ROLLBACK", stop_resize=stop_result)
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
        pos["stop"] = new_stop
        pos["broker_stop_price"] = new_stop
        pos["broker_stop_amount"] = remaining
        pos["broker_stop_order_id"] = result.get("new_order_id") or pos.get("broker_stop_order_id")
        pos["disaster_stop_order_id"] = pos.get("broker_stop_order_id")
        pos["broker_stop_status"] = result.get("status")
        falcon_update_registry_management(pos, stop_update_reason=reason, stop_update=result)
    HEALTH["last_real_management_action"] = {"action": reason, "status": result.get("status") if isinstance(result, dict) else None, "symbol": pos.get("symbol"), "ts": data_hora_sp_str()}
    if not applied:
        HEALTH["last_real_management_error"] = result.get("status") if isinstance(result, dict) else "STOP_UPDATE_UNKNOWN"
    return {"ok": applied, "applied": applied, "status": result.get("status") if isinstance(result, dict) else "STOP_UPDATE_UNKNOWN", "broker_result": result}


def falcon_handle_live_stop_cross(pid, pos, price):
    remaining_expected = falcon_real_remaining_qty(pos)
    snapshot = central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side")) if central_broker and hasattr(central_broker, "managed_position_snapshot") else {"ok": False, "status": "POSITION_HELPER_MISSING"}
    current_amount = safe_float(snapshot.get("amount"), None) if isinstance(snapshot, dict) else None
    stop_order_id = pos.get("broker_stop_order_id") or pos.get("disaster_stop_order_id")
    order_snapshot = central_broker.managed_order_snapshot(pos.get("symbol"), stop_order_id) if central_broker and hasattr(central_broker, "managed_order_snapshot") else {}

    if snapshot.get("ok") and snapshot.get("position_closed"):
        exit_price = safe_float(order_snapshot.get("average"), safe_float(pos.get("stop"), price))
        HEALTH["last_live_stop_status"] = "BROKER_STOP_CONFIRMED_POSITION_CLOSED"
        close_position(pid, pos, exit_price, "STOP_BROKER_CONFIRMED")
        return {"closed": True, "status": "BROKER_STOP_CONFIRMED_POSITION_CLOSED", "snapshot": snapshot, "order_snapshot": order_snapshot}

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
    stop_invalid = order_status in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED", "ERROR", "ORDER_SNAPSHOT_ERROR"}
    if first_seen is None:
        pos["live_stop_crossed_epoch"] = now
        pos["live_stop_crossed_at"] = data_hora_sp_str()
        record_event("LIVE_STOP_TRIGGER_WAIT", pos, {"price": price, "broker_snapshot": snapshot, "stop_order": order_snapshot})
        if not (FALCON_MANAGEMENT_FAILSAFE_ENABLED and stop_invalid):
            HEALTH["last_live_stop_status"] = "WAITING_BROKER_STOP_EXECUTION"
            return {"closed": False, "status": "WAITING_BROKER_STOP_EXECUTION", "snapshot": snapshot, "order_snapshot": order_snapshot}
        first_seen = now - FALCON_MANAGEMENT_STOP_GRACE_SECONDS

    elapsed = now - first_seen
    if not FALCON_MANAGEMENT_FAILSAFE_ENABLED or (elapsed < FALCON_MANAGEMENT_STOP_GRACE_SECONDS and not stop_invalid):
        HEALTH["last_live_stop_status"] = "WAITING_BROKER_STOP_EXECUTION"
        return {"closed": False, "status": "WAITING_BROKER_STOP_EXECUTION", "elapsed": elapsed, "snapshot": snapshot, "order_snapshot": order_snapshot}

    # Evita que um stop residual dispare depois do market fail-safe e reverta a perna.
    cancel_result = None
    if stop_order_id and hasattr(central_broker, "cancel_managed_stop_order"):
        cancel_auth = falcon_issue_management_token(pos, "STOP_FAILSAFE_CANCEL", {"order_id": stop_order_id})
        cancel_token = cancel_auth.get("token") if isinstance(cancel_auth, dict) else None
        if cancel_token:
            cancel_result = central_broker.cancel_managed_stop_order(pos.get("symbol"), stop_order_id, execution_auth_token=cancel_token, reason="STOP_FAILSAFE_PRE_CLOSE")

    # Reconsulta após tentar cancelar: se o stop executou nesse intervalo, não envia market duplicado.
    post_cancel_snapshot = central_broker.managed_position_snapshot(pos.get("symbol"), pos.get("side"))
    if isinstance(post_cancel_snapshot, dict) and post_cancel_snapshot.get("position_closed"):
        exit_price = safe_float((order_snapshot or {}).get("average"), safe_float(pos.get("stop"), price))
        HEALTH["last_live_stop_status"] = "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE"
        close_position(pid, pos, exit_price, "STOP_BROKER_CONFIRMED")
        return {"closed": True, "status": "BROKER_STOP_CONFIRMED_AFTER_CANCEL_RACE", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot}
    post_cancel_amount = safe_float((post_cancel_snapshot or {}).get("amount"), current_amount)
    if not (isinstance(post_cancel_snapshot, dict) and post_cancel_snapshot.get("ok")):
        HEALTH["last_live_stop_status"] = "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR"
        return {"closed": False, "status": "STOP_FAILSAFE_POST_CANCEL_SNAPSHOT_ERROR", "cancel_stop": cancel_result, "snapshot": post_cancel_snapshot}

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
    payload["real_position_management"] = {
        "version": FALCON_REAL_POSITION_MANAGEMENT_HARDENING_VERSION,
        "enabled": True,
        "failsafe_enabled": FALCON_MANAGEMENT_FAILSAFE_ENABLED,
        "stop_grace_seconds": FALCON_MANAGEMENT_STOP_GRACE_SECONDS,
        "tp50_retry_seconds": FALCON_TP50_RETRY_SECONDS,
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
