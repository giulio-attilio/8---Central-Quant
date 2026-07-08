# ==============================================================================
# TURTLE BREAKOUT PRO 2.0 - CENTRAL QUANT
# Versão: 2026-07-08-TURTLE-BREAKOUT-PRO-2-0-RISK-GUARD-CONNECTOR-V1
#
# Robô de pesquisa/paper para Central Quant.
# NÃO executa ordens reais na BingX.
#
# Objetivo:
# - Ficar no mesmo padrão estrutural dos outros robôs da Central Quant.
# - Mudar apenas a estratégia: Turtle Breakout 20/55.
# - Gerar sinais por Telegram.
# - Registrar trades paper.
# - Registrar eventos de gestão: SIGNAL, TP50, BE, STOP, SAÍDA TURTLE.
# - Medir MFE/MAE em % e em R.
# - Medir devolução média de MFE.
# - Medir captura de tendência.
# - Medir runner aberto atual.
# - Gerar Score Turtle e qualidade do sinal.
# - Registrar funil Turtle igual ao Cobra.
# - Medir expectancy em R.
# - Medir Profit Factor em % e em R.
# - Separar estatísticas por setup e por direção LONG/SHORT.
# - Controlar candle novo por ativo, não por BTC.
# - Comparar Turtle20 x Turtle55 separadamente.
# - Enviar resumo diário 23:55 e resumo mensal.
# - Expor HEALTH compatível com /central, /bots e /health.
#
# Estratégia:
# - TURTLE20:
#   Entrada: rompimento de 20 candles fechados.
#   Saída: rompimento contrário de 10 candles fechados.
#
# - TURTLE55:
#   Entrada: rompimento de 55 candles fechados.
#   Saída: rompimento contrário de 20 candles fechados.
#
# Gestão:
# - Stop inicial: 2 ATR.
# - TP50: 1R.
# - Após TP50: stop vai para BE.
# - Saída final: canal Turtle contrário.
#
# Variáveis principais:
# - ENABLE_TURTLE=true
# - TURTLE_TOKEN / TURTLE_CHAT_ID
# - UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN
# - TURTLE_WATCHLIST_FILE=watchlists/turtle.json
# - TURTLE_ENABLED_SETUPS=20,55   ou 20   ou 55
# ==============================================================================

import os
import json
import time
import threading
import traceback
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
from exchange_manager import get_exchange, load_markets_once
from ccxt.base.errors import NetworkError, RateLimitExceeded, ExchangeError
from flask import Flask, request
from upstash_redis import Redis

# ==============================================================================
# TRADE REGISTRY — CENTRAL QUANT
# ==============================================================================
try:
    from trade_registry import (
        make_trade_id,
        register_open_trade,
        update_trade,
        close_trade,
    )
    TRADE_REGISTRY_LOADED = True
    TRADE_REGISTRY_IMPORT_ERROR = None
except Exception as _trade_registry_exc:
    make_trade_id = None
    register_open_trade = None
    update_trade = None
    close_trade = None
    TRADE_REGISTRY_LOADED = False
    TRADE_REGISTRY_IMPORT_ERROR = str(_trade_registry_exc)

app = Flask(__name__)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on", "y"}


# ==============================================================================
# CONFIG
# ==============================================================================

BOT_NAME = os.environ.get("BOT_NAME", "Turtle Breakout PRO 2.0")
TIMEZONE_BR = timezone(timedelta(hours=-3))

TOKEN = (
    os.environ.get("TURTLE_TOKEN")
    or os.environ.get("TURTLE_TELEGRAM_BOT_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
)

CHAT_ID = (
    os.environ.get("TURTLE_CHAT_ID")
    or os.environ.get("TURTLE_TELEGRAM_CHAT_ID")
    or os.environ.get("TELEGRAM_CHAT_ID")
)

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = os.environ.get("TURTLE_WATCHLIST_FILE", "watchlists/turtle.json")

TIMEFRAME = os.environ.get("TURTLE_TIMEFRAME", "1h")
OHLCV_LIMIT = int(os.environ.get("TURTLE_OHLCV_LIMIT", "220"))

ATR_LEN = int(os.environ.get("TURTLE_ATR_LEN", "14"))
ATR_STOP_MULT = float(os.environ.get("TURTLE_ATR_STOP_MULT", "2.0"))
TP50_R = float(os.environ.get("TURTLE_TP50_R", "1.0"))

MIN_ATR_PCT = float(os.environ.get("TURTLE_MIN_ATR_PCT", "0.25"))
MAX_RISK_PCT = float(os.environ.get("TURTLE_MAX_RISK_PCT", "6.0"))

# Score Turtle
SCORE_MIN_QUALITY_TO_SIGNAL = int(os.environ.get("TURTLE_SCORE_MIN_QUALITY_TO_SIGNAL", "0"))
VOLUME_REL_LOOKBACK = int(os.environ.get("TURTLE_VOLUME_REL_LOOKBACK", "20"))
IDEAL_ATR_PCT = float(os.environ.get("TURTLE_IDEAL_ATR_PCT", "1.20"))
IDEAL_BREAKOUT_ATR = float(os.environ.get("TURTLE_IDEAL_BREAKOUT_ATR", "0.35"))
IDEAL_CHANNEL_ATR = float(os.environ.get("TURTLE_IDEAL_CHANNEL_ATR", "3.0"))

MAX_OPEN_POSITIONS = int(os.environ.get("TURTLE_MAX_OPEN_POSITIONS", "40"))
ALLOW_SAME_SYMBOL_BOTH_SETUPS = str(os.environ.get("TURTLE_ALLOW_SAME_SYMBOL_BOTH_SETUPS", "true")).lower() in {"1", "true", "yes", "sim", "on"}

SCAN_SLEEP_SECONDS = int(os.environ.get("TURTLE_SCAN_SLEEP_SECONDS", "60"))
MANAGEMENT_SLEEP_SECONDS = int(os.environ.get("TURTLE_MANAGEMENT_SLEEP_SECONDS", "20"))
COMMAND_SLEEP_SECONDS = int(os.environ.get("TURTLE_COMMAND_SLEEP_SECONDS", "2"))
WATCHDOG_SLEEP_SECONDS = int(os.environ.get("TURTLE_WATCHDOG_SLEEP_SECONDS", "300"))

WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("TURTLE_WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("TURTLE_WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

STARTUP_GUARD_SECONDS = int(os.environ.get("TURTLE_STARTUP_GUARD_SECONDS", "300"))
SIGNAL_COOLDOWN_CANDLES = int(os.environ.get("TURTLE_SIGNAL_COOLDOWN_CANDLES", "3"))

DAILY_SUMMARY_HOUR = int(os.environ.get("TURTLE_DAILY_SUMMARY_HOUR", "23"))
DAILY_SUMMARY_MINUTE = int(os.environ.get("TURTLE_DAILY_SUMMARY_MINUTE", "55"))

MONTHLY_SUMMARY_DAY = int(os.environ.get("TURTLE_MONTHLY_SUMMARY_DAY", "1"))
MONTHLY_SUMMARY_HOUR = int(os.environ.get("TURTLE_MONTHLY_SUMMARY_HOUR", "0"))
MONTHLY_SUMMARY_MINUTE = int(os.environ.get("TURTLE_MONTHLY_SUMMARY_MINUTE", "5"))

ENABLED_SETUPS_RAW = os.environ.get("TURTLE_ENABLED_SETUPS", "20,55")

# ==============================================================================
# TURTLE RISK GUARD CONNECTOR V1
# ==============================================================================
# Liga o Turtle diretamente ao Risk Guard da Central antes de registrar sinal PAPER.
# Também honra os toggles legados ENABLE_TURTLE20 / ENABLE_TURTLE55, quando existirem no Render.
TURTLE_RISK_GUARD_CONNECTOR_VERSION = "2026-07-08-TURTLE-RISK-GUARD-CONNECTOR-V1"
TURTLE_RISK_GUARD_CONNECTOR_ENABLED = env_bool("TURTLE_RISK_GUARD_CONNECTOR_ENABLED", True)
TURTLE_RISK_GUARD_FAIL_CLOSED = env_bool("TURTLE_RISK_GUARD_FAIL_CLOSED", True)
TURTLE_RISK_GUARD_TIMEOUT_SECONDS = float(os.environ.get("TURTLE_RISK_GUARD_TIMEOUT_SECONDS", "6"))
TURTLE_RISK_GUARD_URL = os.environ.get(
    "TURTLE_RISK_GUARD_URL",
    os.environ.get(
        "CENTRAL_CAN_OPEN_TRADE_URL",
        f"http://127.0.0.1:{os.environ.get('PORT', '10000')}/can_open_trade",
    ),
)

ALL_SETUPS = {
    "TURTLE20": {
        "short": "20",
        "label": "Turtle 20",
        "entry_len": int(os.environ.get("TURTLE20_ENTRY_LEN", "20")),
        "exit_len": int(os.environ.get("TURTLE20_EXIT_LEN", "10")),
    },
    "TURTLE55": {
        "short": "55",
        "label": "Turtle 55",
        "entry_len": int(os.environ.get("TURTLE55_ENTRY_LEN", "55")),
        "exit_len": int(os.environ.get("TURTLE55_EXIT_LEN", "20")),
    },
}


def build_enabled_setups():
    raw = str(ENABLED_SETUPS_RAW or "20,55").replace(" ", "")
    parts = [x for x in raw.split(",") if x]
    enabled = {}
    lower_parts = [p.lower() for p in parts]
    for key, cfg in ALL_SETUPS.items():
        if cfg["short"] in parts or key.lower() in lower_parts:
            enabled[key] = cfg
    return enabled or ALL_SETUPS.copy()


SETUPS = build_enabled_setups()

POSITIONS_KEY = "turtle_pro:positions"
SIGNALS_KEY = "turtle_pro:signals"
TRADES_KEY = "turtle_pro:trades"
EVENTS_KEY = "turtle_pro:events"
STATE_KEY = "turtle_pro:state"
COOLDOWN_KEY = "turtle_pro:cooldowns"
DAILY_SUMMARY_KEY = "turtle_pro:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "turtle_pro:monthly_summary_sent"
LAST_CANDLES_KEY = "turtle_pro:last_scanned_candles_by_symbol"
FUNNEL_KEY = "turtle_pro:funnel"

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

exchange = get_exchange()   

redis_lock = threading.Lock()

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

    "signals_turtle20_today": 0,
    "signals_turtle55_today": 0,
    "signals_buy_today": 0,
    "signals_sell_today": 0,

    "tp50_today": 0,
    "be_today": 0,
    "stops_today": 0,
    "turtle_exits_today": 0,

    "mfe_avg_pct": 0.0,
    "mae_avg_pct": 0.0,
    "mfe_avg_r": 0.0,
    "mae_avg_r": 0.0,
    "giveback_avg_pct": 0.0,
    "giveback_avg_r": 0.0,
    "expectancy_r": 0.0,
    "profit_factor_pct": 0.0,
    "profit_factor_r": 0.0,
    "trend_capture_pct": 0.0,
    "open_runner_symbol": None,
    "open_runner_setup": None,
    "open_runner_side": None,
    "open_runner_r": 0.0,
    "open_runner_pct": 0.0,
    "best_setup": None,
    "worst_setup": None,
    "top_mfe_month": [],
    "runners_3r": 0,
    "runners_5r": 0,
    "runners_10r": 0,

    "setups": {},
    "directions": {},
    "ranking_month": [],
    "enabled_setups": list(SETUPS.keys()),
    "mode": "PAPER",
    "risk_guard_connector_version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
    "risk_guard_connector_enabled": TURTLE_RISK_GUARD_CONNECTOR_ENABLED,
    "risk_guard_url": TURTLE_RISK_GUARD_URL,
    "risk_guard_fail_closed": TURTLE_RISK_GUARD_FAIL_CLOSED,
    "last_risk_guard_decision": None,
    "risk_guard_blocked_today": 0,
    "trade_registry_loaded": TRADE_REGISTRY_LOADED,
    "trade_registry_import_error": TRADE_REGISTRY_IMPORT_ERROR,

    "funnel_today": {
        "ativos_analisados": 0,
        "rompimentos_20_buy": 0,
        "rompimentos_20_sell": 0,
        "rompimentos_55_buy": 0,
        "rompimentos_55_sell": 0,
        "reprovados_atr": 0,
        "reprovados_risco": 0,
        "reprovados_score": 0,
        "reprovados_cooldown": 0,
        "reprovados_posicao_ativa": 0,
        "reprovados_risk_guard": 0,
        "sinais_enviados": 0,
    },
}

# ==============================================================================
# UTIL
# ==============================================================================

def agora_sp():
    return datetime.now(TIMEZONE_BR)


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
        return False
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
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
    candidates = [
        WATCHLIST_FILE,
        "watchlists/turtle.json",
        "watchlist_turtle.json",
        "watchlist.json",
    ]

    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict):
                    data = data.get("symbols", data.get("watchlist", []))

                symbols = []
                invalid = []

                for item in data:
                    s = str(item).upper().strip()
                    s = s.replace("/", "").replace(":USDT", "")
                    if not s:
                        continue
                    if not s.endswith("USDT"):
                        s = f"{s}USDT"
                    if len(s) < 6:
                        invalid.append(str(item))
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

    fallback = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "LINKUSDT", "1000PEPEUSDT", "1000BONKUSDT",
        "WIFUSDT", "FLOKIUSDT", "SHIBUSDT", "ENAUSDT", "OPUSDT", "ARBUSDT",
    ]

    HEALTH["watchlist_total"] = len(fallback)
    HEALTH["watchlist_valid"] = len(fallback)
    HEALTH["watchlist_invalid"] = []
    HEALTH["last_watchlist_count"] = len(fallback)
    HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
    return fallback


def safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=OHLCV_LIMIT):
    try:
        data = exchange.fetch_ohlcv(to_ccxt_symbol(symbol), timeframe=timeframe, limit=limit)
        if not data or len(data) < 80:
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
    tr = pd.concat(
        [
            (df["high"] - df["low"]).abs(),
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = tr.rolling(ATR_LEN).mean()
    return df


def closed_candles(df):
    if df is None or len(df) < 80:
        return None
    # Último candle pode estar em formação; usa apenas candles fechados.
    return df.iloc[:-1].copy()


def position_id(symbol, setup, side):
    return f"{setup}:{symbol}:{side}"


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


def get_cooldowns():
    data = redis_get_json(COOLDOWN_KEY, {})
    return data if isinstance(data, dict) else {}


def save_cooldowns(data):
    return redis_set_json(COOLDOWN_KEY, data)


def get_last_candles_by_symbol():
    data = redis_get_json(LAST_CANDLES_KEY, {})
    return data if isinstance(data, dict) else {}


def save_last_candles_by_symbol(data):
    return redis_set_json(LAST_CANDLES_KEY, data)


def candle_hours():
    tf = TIMEFRAME.lower()
    if tf.endswith("m"):
        return max(1 / 60, int(tf[:-1]) / 60)
    if tf.endswith("h"):
        return int(tf[:-1])
    if tf.endswith("d"):
        return 24 * int(tf[:-1])
    return 1


def is_in_cooldown(symbol, setup, side, current_candle_ts):
    cds = get_cooldowns()
    key = position_id(symbol, setup, side)
    last_ts = cds.get(key)
    if not last_ts:
        return False
    try:
        elapsed_hours = (int(current_candle_ts) - int(last_ts)) / 3600000
        elapsed_candles = elapsed_hours / candle_hours()
        return elapsed_candles < SIGNAL_COOLDOWN_CANDLES
    except Exception:
        return False


def set_cooldown(symbol, setup, side, current_candle_ts):
    cds = get_cooldowns()
    cds[position_id(symbol, setup, side)] = int(current_candle_ts)
    save_cooldowns(cds)


def signal_date_matches(signal, br_date):
    return str(signal.get("created_at", "")).startswith(br_date)


def trade_month_matches(trade, br_month):
    return br_month in str(trade.get("closed_at", ""))


def trade_date_matches(trade, br_date):
    return str(trade.get("closed_at", "")).startswith(br_date)


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
    return event


# ==============================================================================
# TRADE REGISTRY HELPERS
# ==============================================================================
def turtle_registry_id(pos):
    if not TRADE_REGISTRY_LOADED or make_trade_id is None:
        return None
    try:
        return pos.get("trade_registry_id") or make_trade_id(
            "TURTLE",
            pos.get("symbol"),
            pos.get("side"),
            pos.get("setup", "TURTLE"),
        )
    except Exception:
        return None


def turtle_registry_open(sig):
    if not TRADE_REGISTRY_LOADED or register_open_trade is None:
        return {"ok": False, "error": TRADE_REGISTRY_IMPORT_ERROR or "TRADE_REGISTRY_NOT_LOADED"}
    try:
        result = register_open_trade(
            bot="TURTLE",
            symbol=sig.get("symbol"),
            side=sig.get("side"),
            entry=safe_float(sig.get("entry")),
            sl=safe_float(sig.get("stop", sig.get("initial_stop"))),
            tp50=safe_float(sig.get("tp50")),
            setup=sig.get("setup", "TURTLE"),
            qty=None,
            source="turtle.py",
            metadata={
                "bot_name": BOT_NAME,
                "setup_label": sig.get("setup_label"),
                "timeframe": sig.get("timeframe"),
                "score_turtle": sig.get("score_turtle"),
                "quality": sig.get("quality"),
                "risk_pct": sig.get("risk_pct"),
                "atr_pct": sig.get("atr_pct"),
                "volume_rel": sig.get("volume_rel"),
                "breakout_atr": sig.get("breakout_atr"),
                "channel_atr": sig.get("channel_atr"),
                "signal_ts": sig.get("signal_ts"),
                "mode": "PAPER",
            },
        )
        if result.get("ok") and result.get("trade_id"):
            sig["trade_registry_id"] = result.get("trade_id")
            sig["trade_registry_opened"] = True
            sig["trade_registry_opened_at"] = data_hora_sp_str()
        return result
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def turtle_registry_update(pos, event, **updates):
    if not TRADE_REGISTRY_LOADED or update_trade is None:
        return {"ok": False, "error": TRADE_REGISTRY_IMPORT_ERROR or "TRADE_REGISTRY_NOT_LOADED"}
    try:
        trade_id = turtle_registry_id(pos)
        if not trade_id:
            return {"ok": False, "error": "TRADE_ID_NOT_AVAILABLE"}

        payload = {
            "last_event": event,
            "last_event_at": data_hora_sp_str(),
            "status": pos.get("status", "OPEN"),
            "sl": safe_float(pos.get("stop")),
            "tp50": safe_float(pos.get("tp50")),
            "tp50_hit": bool(pos.get("tp50_hit")),
            "breakeven": bool(pos.get("be_moved")),
            "mfe_pct": safe_float(pos.get("mfe_pct")),
            "mae_pct": safe_float(pos.get("mae_pct")),
            "mfe_r": safe_float(pos.get("mfe_r")),
            "mae_r": safe_float(pos.get("mae_r")),
            "best_price": safe_float(pos.get("best_price")),
            "worst_price": safe_float(pos.get("worst_price")),
            "management_cycles": int(pos.get("management_cycles", 0) or 0),
        }
        payload.update(updates)
        return update_trade(trade_id, **payload)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def turtle_registry_close(pos, exit_price, reason, result_pct=None, result_r=None):
    if not TRADE_REGISTRY_LOADED or close_trade is None:
        return {"ok": False, "error": TRADE_REGISTRY_IMPORT_ERROR or "TRADE_REGISTRY_NOT_LOADED"}
    try:
        trade_id = turtle_registry_id(pos)
        if not trade_id:
            return {"ok": False, "error": "TRADE_ID_NOT_AVAILABLE"}
        return close_trade(
            trade_id,
            exit_price=safe_float(exit_price),
            pnl_pct=safe_float(result_pct),
            pnl_r=safe_float(result_r),
            reason=reason,
            metadata={
                "bot": "TURTLE",
                "setup": pos.get("setup"),
                "setup_label": pos.get("setup_label"),
                "symbol": pos.get("symbol"),
                "side": pos.get("side"),
                "mfe_pct": safe_float(pos.get("mfe_pct")),
                "mae_pct": safe_float(pos.get("mae_pct")),
                "mfe_r": safe_float(pos.get("mfe_r")),
                "mae_r": safe_float(pos.get("mae_r")),
                "giveback_pct": safe_float(pos.get("giveback_pct")),
                "giveback_r": safe_float(pos.get("giveback_r")),
                "tp50_hit": bool(pos.get("tp50_hit")),
                "be_moved": bool(pos.get("be_moved")),
                "mode": "PAPER",
            },
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ==============================================================================
# FUNIL TURTLE
# ==============================================================================

def get_funnel():
    data = redis_get_json(FUNNEL_KEY, {})
    if not isinstance(data, dict):
        data = {}
    today = date_key()
    if data.get("date") != today:
        data = {
            "date": today,
            "ativos_analisados": 0,
            "rompimentos_20_buy": 0,
            "rompimentos_20_sell": 0,
            "rompimentos_55_buy": 0,
            "rompimentos_55_sell": 0,
            "reprovados_atr": 0,
            "reprovados_risco": 0,
            "reprovados_score": 0,
            "reprovados_cooldown": 0,
            "reprovados_posicao_ativa": 0,
            "reprovados_risk_guard": 0,
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
    return {
        "ativos_analisados": int(data.get("ativos_analisados", 0) or 0),
        "rompimentos_20_buy": int(data.get("rompimentos_20_buy", 0) or 0),
        "rompimentos_20_sell": int(data.get("rompimentos_20_sell", 0) or 0),
        "rompimentos_55_buy": int(data.get("rompimentos_55_buy", 0) or 0),
        "rompimentos_55_sell": int(data.get("rompimentos_55_sell", 0) or 0),
        "reprovados_atr": int(data.get("reprovados_atr", 0) or 0),
        "reprovados_risco": int(data.get("reprovados_risco", 0) or 0),
        "reprovados_score": int(data.get("reprovados_score", 0) or 0),
        "reprovados_cooldown": int(data.get("reprovados_cooldown", 0) or 0),
        "reprovados_posicao_ativa": int(data.get("reprovados_posicao_ativa", 0) or 0),
        "reprovados_risk_guard": int(data.get("reprovados_risk_guard", 0) or 0),
        "sinais_enviados": int(data.get("sinais_enviados", 0) or 0),
    }

# ==============================================================================
# SCORE TURTLE
# ==============================================================================

def quality_from_score(score):
    score = int(score or 0)
    if score >= 80:
        return "ALTA 🟢"
    if score >= 65:
        return "MÉDIA 🟡"
    return "BAIXA 🔴"


def calc_turtle_score(row, prev, side, close, atr, entry_high, entry_low, entry_len):
    score = 0

    atr_pct = atr / close * 100.0 if close else 0.0
    atr_score = min(25, max(0, int((atr_pct / IDEAL_ATR_PCT) * 25)))
    score += atr_score

    try:
        vol_ma = prev["volume"].tail(VOLUME_REL_LOOKBACK).mean()
        vol_rel = safe_float(row["volume"]) / vol_ma if vol_ma and vol_ma > 0 else 1.0
    except Exception:
        vol_rel = 1.0
    vol_score = min(25, max(0, int((vol_rel / 2.0) * 25)))
    score += vol_score

    if side == "LONG":
        breakout_size = close - entry_high
    else:
        breakout_size = entry_low - close
    breakout_atr = breakout_size / atr if atr > 0 else 0.0
    breakout_score = min(25, max(0, int((breakout_atr / IDEAL_BREAKOUT_ATR) * 25)))
    score += breakout_score

    channel_high = prev["high"].tail(entry_len).max()
    channel_low = prev["low"].tail(entry_len).min()
    channel_atr = (channel_high - channel_low) / atr if atr > 0 else 0.0
    # Pontua melhor se o canal não for nem apertado demais nem esticado demais.
    if channel_atr <= 0:
        channel_score = 0
    elif channel_atr <= IDEAL_CHANNEL_ATR:
        channel_score = int((channel_atr / IDEAL_CHANNEL_ATR) * 25)
    else:
        channel_score = max(0, int(25 - min(25, (channel_atr - IDEAL_CHANNEL_ATR) * 3)))
    score += channel_score

    score = max(0, min(100, int(score)))

    return {
        "score_turtle": score,
        "quality": quality_from_score(score),
        "volume_rel": round(vol_rel, 4),
        "breakout_atr": round(breakout_atr, 4),
        "channel_atr": round(channel_atr, 4),
    }

# ==============================================================================
# SINAIS
# ==============================================================================

def analyze_symbol_setup(symbol, setup_key, setup_cfg, closed):
    entry_len = int(setup_cfg["entry_len"])
    exit_len = int(setup_cfg["exit_len"])

    min_needed = max(entry_len, exit_len, ATR_LEN) + 5
    if closed is None or len(closed) < min_needed:
        return None

    df = add_indicators(closed)
    row = df.iloc[-1]
    prev = df.iloc[:-1]

    if len(prev) < min_needed:
        return None

    entry_high = prev["high"].tail(entry_len).max()
    entry_low = prev["low"].tail(entry_len).min()

    close = safe_float(row["close"])
    atr = safe_float(row["atr"])

    if close <= 0 or atr <= 0:
        return None

    atr_pct = atr / close * 100.0
    if atr_pct < MIN_ATR_PCT:
        funnel_inc("reprovados_atr")
        return None

    side = None
    stop = None
    tp50 = None

    if close > entry_high:
        side = "LONG"
        stop = close - ATR_STOP_MULT * atr
        tp50 = close + TP50_R * abs(close - stop)
        if setup_key == "TURTLE20":
            funnel_inc("rompimentos_20_buy")
        elif setup_key == "TURTLE55":
            funnel_inc("rompimentos_55_buy")
    elif close < entry_low:
        side = "SHORT"
        stop = close + ATR_STOP_MULT * atr
        tp50 = close - TP50_R * abs(close - stop)
        if setup_key == "TURTLE20":
            funnel_inc("rompimentos_20_sell")
        elif setup_key == "TURTLE55":
            funnel_inc("rompimentos_55_sell")

    if not side:
        return None

    rp = risk_pct(close, stop)
    if rp <= 0 or rp > MAX_RISK_PCT:
        funnel_inc("reprovados_risco")
        return None

    current_ts = int(row["ts"])
    if is_in_cooldown(symbol, setup_key, side, current_ts):
        funnel_inc("reprovados_cooldown")
        return None

    score_data = calc_turtle_score(row, prev, side, close, atr, entry_high, entry_low, entry_len)
    if score_data["score_turtle"] < SCORE_MIN_QUALITY_TO_SIGNAL:
        funnel_inc("reprovados_score")
        return None

    return {
        "id": position_id(symbol, setup_key, side),
        "bot": "Turtle Breakout PRO 2.0",
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
        "score_turtle": score_data["score_turtle"],
        "quality": score_data["quality"],
        "volume_rel": score_data["volume_rel"],
        "breakout_atr": score_data["breakout_atr"],
        "channel_atr": score_data["channel_atr"],
        "entry_len": entry_len,
        "exit_len": exit_len,
        "timeframe": TIMEFRAME,
        "signal_ts": current_ts,
        "signal_dt": str(row["dt"]),
        "created_at": data_hora_sp_str(),
        "status": "OPEN",
        "tp50_hit": False,
        "be_moved": False,
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


def should_skip_due_to_open_position(positions, symbol, setup_key, side):
    if ALLOW_SAME_SYMBOL_BOTH_SETUPS:
        return position_id(symbol, setup_key, side) in positions

    for p in positions.values():
        if p.get("symbol") == symbol:
            return True
    return False


def signal_message(sig):
    emoji = "🟢" if sig["side"] == "LONG" else "🔴"
    return (
        f"🐢 {emoji} {sig['setup_label'].upper()} {sig['direction']} - {sig['symbol']}\n\n"
        f"Timeframe: {sig['timeframe']}\n"
        f"Entrada: rompimento {sig['entry_len']} candles fechados\n"
        f"Saída: canal {sig['exit_len']} candles fechados\n\n"
        f"Entrada:\n{fmt_price(sig['entry'])}\n\n"
        f"SL ATR:\n{fmt_price(sig['stop'])}\n\n"
        f"TP50:\n{fmt_price(sig['tp50'])}\n\n"
        f"ATR:\n{fmt_pct(sig['atr_pct'])}\n\n"
        f"Score Turtle:\n{sig.get('score_turtle', 0)}/100\n"
        f"Qualidade:\n{sig.get('quality', 'N/A')}\n\n"
        f"Volume relativo:\n{safe_float(sig.get('volume_rel'), 1):.2f}x\n"
        f"Breakout em ATR:\n{safe_float(sig.get('breakout_atr'), 0):.2f}\n"
        f"Canal em ATR:\n{safe_float(sig.get('channel_atr'), 0):.2f}\n\n"
        f"Risco:\n{sig['risk_pct']:.2f}%\n\n"
        f"Modo: PAPER / SEM BINGX"
    )


def turtle_setup_env_gate(sig):
    """Gate local para toggles legados ENABLE_TURTLE20 / ENABLE_TURTLE55.

    Observação: o código original do Turtle usa TURTLE_ENABLED_SETUPS.
    Este conector passa a respeitar também ENABLE_TURTLE20=false e ENABLE_TURTLE55=false
    para preservar decisões operacionais antigas do Render.
    """
    setup = str((sig or {}).get("setup") or "").upper().strip()
    reasons = []
    warnings = []

    if setup == "TURTLE20" and os.environ.get("ENABLE_TURTLE20") is not None and not env_bool("ENABLE_TURTLE20", True):
        reasons.append("Turtle Risk Guard Connector V1: ENABLE_TURTLE20=false no Render.")
    if setup == "TURTLE55" and os.environ.get("ENABLE_TURTLE55") is not None and not env_bool("ENABLE_TURTLE55", True):
        reasons.append("Turtle Risk Guard Connector V1: ENABLE_TURTLE55=false no Render.")

    return {
        "ok": True,
        "source": "LOCAL_ENV_GATE",
        "allowed": len(reasons) == 0,
        "decision": "ALLOW" if len(reasons) == 0 else "DENY",
        "reasons": reasons,
        "warnings": warnings,
        "setup": setup,
        "version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
    }


def build_turtle_risk_guard_payload(sig):
    sig = sig if isinstance(sig, dict) else {}
    return {
        "bot": "TURTLE",
        "bot_name": BOT_NAME,
        "setup": sig.get("setup"),
        "symbol": sig.get("symbol"),
        "side": sig.get("side"),
        "mode": "PAPER",
        "execution_mode": "PAPER",
        "intended_live": False,
        "reduce_only": False,
        "source": "turtle.py",
        "connector": "TURTLE_RISK_GUARD_CONNECTOR_V1",
        "entry": sig.get("entry"),
        "stop": sig.get("stop") or sig.get("initial_stop"),
        "sl": sig.get("stop") or sig.get("initial_stop"),
        "tp50": sig.get("tp50"),
        "risk_pct": sig.get("risk_pct"),
        "score": sig.get("score_turtle"),
        "quality": sig.get("quality"),
        "signal_id": sig.get("id"),
        "timeframe": sig.get("timeframe") or TIMEFRAME,
        "created_at": sig.get("created_at") or data_hora_sp_str(),
    }


def call_turtle_risk_guard(sig):
    if not TURTLE_RISK_GUARD_CONNECTOR_ENABLED:
        return {
            "ok": True,
            "allowed": True,
            "decision": "ALLOW",
            "source": "CONNECTOR_DISABLED",
            "reasons": [],
            "warnings": ["TURTLE_RISK_GUARD_CONNECTOR_ENABLED=false"],
            "version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
        }

    local_gate = turtle_setup_env_gate(sig)
    if not local_gate.get("allowed", True):
        return local_gate

    payload = build_turtle_risk_guard_payload(sig)
    try:
        r = requests.post(TURTLE_RISK_GUARD_URL, json=payload, timeout=TURTLE_RISK_GUARD_TIMEOUT_SECONDS)
        if r.status_code != 200:
            return {
                "ok": False,
                "allowed": not TURTLE_RISK_GUARD_FAIL_CLOSED,
                "decision": "DENY" if TURTLE_RISK_GUARD_FAIL_CLOSED else "ALLOW",
                "source": "CENTRAL_HTTP_ERROR",
                "status_code": r.status_code,
                "reasons": [f"Turtle Risk Guard Connector V1: Central retornou HTTP {r.status_code}."] if TURTLE_RISK_GUARD_FAIL_CLOSED else [],
                "warnings": [r.text[:240]],
                "payload": payload,
                "version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
            }
        data = r.json()
        if not isinstance(data, dict):
            data = {"ok": False, "allowed": False, "decision": "DENY", "reasons": ["payload inválido da Central"], "warnings": []}

        allowed = bool(data.get("allowed", data.get("ok", False)))
        decision = str(data.get("decision") or ("ALLOW" if allowed else "DENY")).upper()
        if decision in {"DENY", "BLOCK", "BLOCKED", "REJECT", "REJECTED"}:
            allowed = False

        data["allowed"] = allowed
        data["decision"] = "ALLOW" if allowed else "DENY"
        data.setdefault("source", "CENTRAL_CAN_OPEN_TRADE")
        data.setdefault("version", TURTLE_RISK_GUARD_CONNECTOR_VERSION)
        data.setdefault("payload", payload)
        return data
    except Exception as exc:
        return {
            "ok": False,
            "allowed": not TURTLE_RISK_GUARD_FAIL_CLOSED,
            "decision": "DENY" if TURTLE_RISK_GUARD_FAIL_CLOSED else "ALLOW",
            "source": "CENTRAL_UNAVAILABLE",
            "reasons": [f"Turtle Risk Guard Connector V1: Central indisponível: {exc}"] if TURTLE_RISK_GUARD_FAIL_CLOSED else [],
            "warnings": [str(exc)],
            "payload": payload,
            "version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
        }


def turtle_risk_guard_allows(sig):
    decision = call_turtle_risk_guard(sig)
    allowed = bool(decision.get("allowed", False))
    sig["risk_guard_connector"] = decision
    HEALTH["last_risk_guard_decision"] = {
        "allowed": allowed,
        "decision": decision.get("decision"),
        "source": decision.get("source"),
        "setup": sig.get("setup"),
        "side": sig.get("side"),
        "symbol": sig.get("symbol"),
        "reasons": decision.get("reasons") or [],
        "warnings": decision.get("warnings") or [],
        "ts": data_hora_sp_str(),
    }
    if not allowed:
        HEALTH["risk_guard_blocked_today"] = int(HEALTH.get("risk_guard_blocked_today", 0) or 0) + 1
        HEALTH["last_warning"] = "; ".join([str(x) for x in (decision.get("reasons") or [])[:3]]) or "Turtle Risk Guard Connector V1 bloqueou sinal."
    return allowed, decision


def risk_guard_connector_payload():
    return {
        "ok": True,
        "module": "turtle_risk_guard_connector_v1",
        "version": TURTLE_RISK_GUARD_CONNECTOR_VERSION,
        "generated_at": data_hora_sp_str(),
        "enabled": TURTLE_RISK_GUARD_CONNECTOR_ENABLED,
        "url": TURTLE_RISK_GUARD_URL,
        "fail_closed": TURTLE_RISK_GUARD_FAIL_CLOSED,
        "timeout_seconds": TURTLE_RISK_GUARD_TIMEOUT_SECONDS,
        "env_gates": {
            "ENABLE_TURTLE20": os.environ.get("ENABLE_TURTLE20"),
            "ENABLE_TURTLE55": os.environ.get("ENABLE_TURTLE55"),
            "TURTLE_ENABLED_SETUPS": ENABLED_SETUPS_RAW,
            "active_setups_in_code": list(SETUPS.keys()),
        },
        "last_decision": HEALTH.get("last_risk_guard_decision"),
        "blocked_today": HEALTH.get("risk_guard_blocked_today", 0),
        "notes": [
            "O conector roda antes de turtle_registry_open, antes de salvar posição PAPER e antes de enviar Telegram.",
            "Gestão/fechamento de posições antigas não é bloqueada.",
            "ENABLE_TURTLE20=false e ENABLE_TURTLE55=false agora são respeitados como gates locais, além do /can_open_trade da Central.",
        ],
    }


def risk_guard_connector_text():
    payload = risk_guard_connector_payload()
    env = payload.get("env_gates", {})
    last = payload.get("last_decision") or {}
    lines = [
        "🐢 TURTLE RISK GUARD CONNECTOR V1",
        f"Data/hora: {payload.get('generated_at')}",
        f"Status: {'✅ ATIVO' if payload.get('enabled') else '⚪ DESATIVADO'}",
        f"Fail closed: {payload.get('fail_closed')}",
        f"URL: {payload.get('url')}",
        "",
        "Env / setups:",
        f"- ENABLE_TURTLE20: {env.get('ENABLE_TURTLE20')}",
        f"- ENABLE_TURTLE55: {env.get('ENABLE_TURTLE55')}",
        f"- TURTLE_ENABLED_SETUPS: {env.get('TURTLE_ENABLED_SETUPS')}",
        f"- Setups ativos no código: {', '.join(env.get('active_setups_in_code') or [])}",
        "",
        f"Bloqueios nesta sessão: {payload.get('blocked_today')}",
    ]
    if last:
        lines += [
            "",
            "Última decisão:",
            f"- {last.get('symbol')} {last.get('setup')} {last.get('side')} | {last.get('decision')} | source={last.get('source')}",
        ]
        for r in last.get("reasons") or []:
            lines.append(f"  motivo: {r}")
        for w in last.get("warnings") or []:
            lines.append(f"  aviso: {w}")
    lines += ["", "Notas:"]
    for note in payload.get("notes") or []:
        lines.append(f"- {note}")
    return "\n".join(lines)


def scanner_loop():
    started = time.time()

    while True:
        signals_sent = 0

        try:
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

                    if should_skip_due_to_open_position(positions, symbol, setup_key, sig["side"]):
                        funnel_inc("reprovados_posicao_ativa")
                        continue

                    if time.time() - started < STARTUP_GUARD_SECONDS:
                        set_cooldown(symbol, setup_key, sig["side"], sig["signal_ts"])
                        continue

                    risk_allowed, risk_decision = turtle_risk_guard_allows(sig)
                    if not risk_allowed:
                        funnel_inc("reprovados_risk_guard")
                        set_cooldown(symbol, setup_key, sig["side"], sig["signal_ts"])
                        record_event(
                            "TRADE_BLOCKED",
                            sig,
                            {
                                "risk_guard_connector": risk_decision,
                                "reasons": risk_decision.get("reasons", []),
                                "warnings": risk_decision.get("warnings", []),
                                "result": "DENY",
                            },
                        )
                        continue

                    pid = sig["id"]
                    registry_result = turtle_registry_open(sig)
                    sig["trade_registry_result"] = registry_result
                    positions[pid] = sig
                    save_positions(positions)

                    redis_list_append(SIGNALS_KEY, sig)
                    record_event("SIGNAL", sig, {"entry": sig["entry"], "stop": sig["stop"], "tp50": sig["tp50"]})
                    set_cooldown(symbol, setup_key, sig["side"], sig["signal_ts"])

                    safe_send_telegram(signal_message(sig))
                    funnel_inc("sinais_enviados")
                    signals_sent += 1

                last_candles[symbol] = symbol_last_closed_ts

            save_last_candles_by_symbol(last_candles)

            HEALTH["last_signals_sent"] = signals_sent
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            # refresh_health_stats()  # Memory Guard V2: estatísticas pesadas só no summary_loop

        except Exception as exc:
            HEALTH["last_error"] = f"scanner: {exc}"
            traceback.print_exc()

        time.sleep(SCAN_SLEEP_SECONDS)

# ==============================================================================
# GESTÃO PAPER
# ==============================================================================

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


def turtle_exit_signal(pos):
    symbol = pos["symbol"]
    side = pos["side"]
    exit_len = int(pos["exit_len"])

    df = safe_fetch_ohlcv(symbol)
    closed = closed_candles(df)
    if closed is None or len(closed) < exit_len + 5:
        return False, None

    row = closed.iloc[-1]
    prev = closed.iloc[:-1]

    exit_high = prev["high"].tail(exit_len).max()
    exit_low = prev["low"].tail(exit_len).min()
    close = safe_float(row["close"])

    if side == "LONG" and close < exit_low:
        return True, close
    if side == "SHORT" and close > exit_high:
        return True, close

    return False, close


def close_position(pid, pos, exit_price, reason):
    entry = safe_float(pos["entry"])
    initial_stop = safe_float(pos.get("initial_stop", pos["stop"]))
    side = pos["side"]

    result_pct = pnl_pct_for_side(side, entry, exit_price)
    result_r = r_for_side(side, entry, initial_stop, exit_price)

    giveback_pct = safe_float(pos.get("mfe_pct")) - result_pct
    giveback_r = safe_float(pos.get("mfe_r")) - result_r

    trade = dict(pos)
    trade.update(
        {
            "status": "CLOSED",
            "exit_price": exit_price,
            "exit_reason": reason,
            "closed_at": data_hora_sp_str(),
            "result_pct": result_pct,
            "result_r": result_r,
            "giveback_pct": giveback_pct,
            "giveback_r": giveback_r,
        }
    )

    registry_close_result = turtle_registry_close(trade, exit_price, reason, result_pct=result_pct, result_r=result_r)
    trade["trade_registry_close_result"] = registry_close_result

    redis_list_append(TRADES_KEY, trade)
    record_event(reason, trade, {"exit_price": exit_price, "result_pct": result_pct, "result_r": result_r})

    if result_pct > 0.05:
        emoji = "✅"
    elif result_pct < -0.05:
        emoji = "❌"
    else:
        emoji = "🟡"

    safe_send_telegram(
        f"🐢 SAÍDA {pos.get('setup_label', pos.get('setup'))} - {pos['symbol']}\n\n"
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

                if "initial_stop" not in pos:
                    pos["initial_stop"] = stop

                price = safe_fetch_price(symbol)
                if price is None:
                    continue

                pos = update_mfe_mae(pos, price)

                stopped = (side == "LONG" and price <= stop) or (side == "SHORT" and price >= stop)
                if stopped:
                    close_position(pid, pos, price, "STOP")
                    closed_pids.append(pid)
                    changed = True
                    continue

                if not pos.get("tp50_hit"):
                    tp_hit = (side == "LONG" and price >= tp50) or (side == "SHORT" and price <= tp50)
                    if tp_hit:
                        pos["tp50_hit"] = True
                        pos["be_moved"] = True
                        pos["stop"] = entry
                        pos["candles_to_tp50"] = int(pos.get("management_cycles", 0))
                        changed = True

                        record_event("TP50", pos, {"price": price, "candles_to_tp50": pos["candles_to_tp50"]})
                        record_event("BE", pos, {"new_stop": entry})
                        turtle_registry_update(pos, "TP50", price=safe_float(price), candles_to_tp50=pos["candles_to_tp50"])
                        turtle_registry_update(pos, "BE", new_sl=safe_float(entry))

                        safe_send_telegram(
                            f"🐢 TP50 {pos.get('setup_label', pos.get('setup'))} - {symbol}\n\n"
                            f"Direção: {side}\n"
                            f"Preço atual: {fmt_price(price)}\n"
                            f"Stop movido para BE: {fmt_price(entry)}\n"
                            f"Tempo até TP50: {pos['candles_to_tp50']} ciclos de gestão\n\n"
                            f"MFE: {fmt_pct(pos.get('mfe_pct', 0))} | {fmt_r(pos.get('mfe_r', 0))}"
                        )

                exit_signal, exit_close = turtle_exit_signal(pos)
                if exit_signal and exit_close is not None:
                    close_position(pid, pos, exit_close, f"SAÍDA TURTLE {pos['exit_len']}")
                    closed_pids.append(pid)
                    changed = True
                    continue

                pos["management_cycles"] = int(pos.get("management_cycles", 0)) + 1
                positions[pid] = pos

            for pid in closed_pids:
                positions.pop(pid, None)

            if changed:
                save_positions(positions)
            else:
                HEALTH["last_positions_count"] = len(positions)

            HEALTH["last_management_run"] = data_hora_sp_str()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            # refresh_health_stats()  # Memory Guard V2: estatísticas pesadas só no summary_loop

        except Exception as exc:
            HEALTH["last_error"] = f"management: {exc}"
            traceback.print_exc()

        time.sleep(MANAGEMENT_SLEEP_SECONDS)

# ==============================================================================
# ESTATÍSTICAS
# ==============================================================================

def avg(values):
    vals = [safe_float(v) for v in values if v is not None]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def profit_factor(values):
    vals = [safe_float(v) for v in values]
    gross_profit = sum(x for x in vals if x > 0)
    gross_loss = abs(sum(x for x in vals if x < 0))
    if gross_loss > 0:
        return gross_profit / gross_loss
    return gross_profit


def calc_stats(trades):
    trades = trades or []
    if not trades:
        return {
            "count": 0,
            "wins": 0,
            "losses": 0,
            "be": 0,
            "winrate": 0.0,
            "pnl_pct": 0.0,
            "pnl_r": 0.0,
            "mfe_avg_pct": 0.0,
            "mae_avg_pct": 0.0,
            "mfe_avg_r": 0.0,
            "mae_avg_r": 0.0,
            "giveback_avg_pct": 0.0,
            "giveback_avg_r": 0.0,
            "expectancy_r": 0.0,
            "profit_factor_pct": 0.0,
            "profit_factor_r": 0.0,
            "trend_capture_pct": 0.0,
            "top_mfe": [],
            "runners_3r": 0,
            "runners_5r": 0,
            "runners_10r": 0,
            "tp50_hits": 0,
            "avg_management_cycles": 0.0,
            "avg_candles_to_tp50": 0.0,
            "best_trade": None,
            "worst_trade": None,
            "biggest_runner": None,
            "biggest_loss": None,
        }

    results_pct = [safe_float(t.get("result_pct")) for t in trades]
    results_r = [safe_float(t.get("result_r")) for t in trades]

    wins = [x for x in results_pct if x > 0.05]
    losses = [x for x in results_pct if x < -0.05]

    top = sorted(
        [
            {
                "symbol": t.get("symbol"),
                "setup": t.get("setup"),
                "side": t.get("side"),
                "mfe_pct": safe_float(t.get("mfe_pct")),
                "mfe_r": safe_float(t.get("mfe_r")),
                "closed_at": t.get("closed_at"),
            }
            for t in trades
        ],
        key=lambda x: x["mfe_r"],
        reverse=True,
    )[:5]

    best = max(trades, key=lambda t: safe_float(t.get("result_r"))) if trades else None
    worst = min(trades, key=lambda t: safe_float(t.get("result_r"))) if trades else None
    biggest_runner = max(trades, key=lambda t: safe_float(t.get("mfe_r"))) if trades else None
    biggest_loss = min(trades, key=lambda t: safe_float(t.get("result_r"))) if trades else None

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
        "trend_capture_pct": (
            sum([max(0.0, safe_float(t.get("result_r"))) for t in trades])
            / sum([safe_float(t.get("mfe_r")) for t in trades if safe_float(t.get("mfe_r")) > 0])
            * 100.0
        ) if sum([safe_float(t.get("mfe_r")) for t in trades if safe_float(t.get("mfe_r")) > 0]) > 0 else 0.0,
        "top_mfe": top,
        "runners_3r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 3.0),
        "runners_5r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 5.0),
        "runners_10r": sum(1 for t in trades if safe_float(t.get("mfe_r")) >= 10.0),
        "tp50_hits": sum(1 for t in trades if t.get("tp50_hit")),
        "avg_management_cycles": avg([t.get("management_cycles") for t in trades]),
        "avg_candles_to_tp50": avg([t.get("candles_to_tp50") for t in trades if t.get("candles_to_tp50") is not None]),
        "best_trade": best,
        "worst_trade": worst,
        "biggest_runner": biggest_runner,
        "biggest_loss": biggest_loss,
    }


def slim_trade(trade, metric="result"):
    if not trade:
        return None
    return {
        "symbol": trade.get("symbol"),
        "setup": trade.get("setup"),
        "side": trade.get("side"),
        "closed_at": trade.get("closed_at"),
        "result_pct": safe_float(trade.get("result_pct")),
        "result_r": safe_float(trade.get("result_r")),
        "mfe_pct": safe_float(trade.get("mfe_pct")),
        "mfe_r": safe_float(trade.get("mfe_r")),
        "exit_reason": trade.get("exit_reason"),
    }


def slim_stats(stats):
    stats = dict(stats or {})
    stats["top_mfe"] = (stats.get("top_mfe") or [])[:5]
    stats["best_trade"] = slim_trade(stats.get("best_trade"))
    stats["worst_trade"] = slim_trade(stats.get("worst_trade"))
    stats["biggest_runner"] = slim_trade(stats.get("biggest_runner"), metric="mfe")
    stats["biggest_loss"] = slim_trade(stats.get("biggest_loss"))
    return stats
    

def trades_today():
    br_date = date_key_br()
    return [t for t in get_trades() if trade_date_matches(t, br_date)]


def trades_month():
    br_month = month_key_br()
    return [t for t in get_trades() if trade_month_matches(t, br_month)]


def signals_today():
    br_date = date_key_br()
    return [s for s in get_signals() if signal_date_matches(s, br_date)]


def signals_month():
    br_month = month_key_br()
    return [s for s in get_signals() if br_month in str(s.get("created_at", ""))]


def split_by_setup(items):
    out = {}
    for setup_key in SETUPS:
        out[setup_key] = [x for x in items if x.get("setup") == setup_key]
    return out


def split_by_direction(items):
    return {
        "LONG": [x for x in items if x.get("side") == "LONG"],
        "SHORT": [x for x in items if x.get("side") == "SHORT"],
    }


def build_ranking_month(month_trades):
    rows = []
    for setup_key, setup_trades in split_by_setup(month_trades).items():
        s = calc_stats(setup_trades)
        if s["count"] <= 0:
            continue

        rows.append({
            "name": setup_key,
            "label": SETUPS[setup_key]["label"],
            "trades": s["count"],
            "profit_factor_r": s["profit_factor_r"],
            "expectancy_r": s["expectancy_r"],
            "pnl_r": s["pnl_r"],
            "winrate": s["winrate"],
        })

    rows.sort(key=lambda x: (x["profit_factor_r"], x["expectancy_r"], x["pnl_r"]), reverse=True)
    return rows


def get_open_runner():
    positions = get_positions()
    if not positions:
        return None
    best = None
    for p in positions.values():
        r = safe_float(p.get("mfe_r"))
        if best is None or r > safe_float(best.get("mfe_r")):
            best = p
    return best


def refresh_health_stats():
    month_trades = trades_month()
    month_signals = signals_month()
    today_trades = trades_today()
    today_signals = signals_today()
    today_events = [e for e in get_events() if str(e.get("created_at", "")).startswith(date_key_br())]

    stats = slim_stats(calc_stats(month_trades))
    HEALTH["funnel_today"] = funnel_snapshot()

    HEALTH["signals_today"] = len(today_signals)
    HEALTH["signals_month"] = len(month_signals)
    HEALTH["trades_closed_today"] = len(today_trades)
    HEALTH["trades_closed_month"] = len(month_trades)

    HEALTH["signals_turtle20_today"] = sum(1 for s in today_signals if s.get("setup") == "TURTLE20")
    HEALTH["signals_turtle55_today"] = sum(1 for s in today_signals if s.get("setup") == "TURTLE55")
    HEALTH["signals_buy_today"] = sum(1 for s in today_signals if s.get("side") == "LONG")
    HEALTH["signals_sell_today"] = sum(1 for s in today_signals if s.get("side") == "SHORT")

    HEALTH["tp50_today"] = sum(1 for e in today_events if e.get("event_type") == "TP50")
    HEALTH["be_today"] = sum(1 for e in today_events if e.get("event_type") == "BE")
    HEALTH["stops_today"] = sum(1 for e in today_events if e.get("event_type") == "STOP")
    HEALTH["turtle_exits_today"] = sum(1 for e in today_events if str(e.get("event_type", "")).startswith("SAÍDA TURTLE"))

    HEALTH["mfe_avg_pct"] = round(stats["mfe_avg_pct"], 4)
    HEALTH["mae_avg_pct"] = round(stats["mae_avg_pct"], 4)
    HEALTH["mfe_avg_r"] = round(stats["mfe_avg_r"], 4)
    HEALTH["mae_avg_r"] = round(stats["mae_avg_r"], 4)
    HEALTH["giveback_avg_pct"] = round(stats["giveback_avg_pct"], 4)
    HEALTH["giveback_avg_r"] = round(stats["giveback_avg_r"], 4)
    HEALTH["expectancy_r"] = round(stats["expectancy_r"], 4)
    HEALTH["profit_factor_pct"] = round(stats["profit_factor_pct"], 4)
    HEALTH["profit_factor_r"] = round(stats["profit_factor_r"], 4)
    HEALTH["trend_capture_pct"] = round(stats["trend_capture_pct"], 4)

    open_runner = get_open_runner()
    if open_runner:
        HEALTH["open_runner_symbol"] = open_runner.get("symbol")
        HEALTH["open_runner_setup"] = open_runner.get("setup")
        HEALTH["open_runner_side"] = open_runner.get("side")
        HEALTH["open_runner_r"] = round(safe_float(open_runner.get("mfe_r")), 4)
        HEALTH["open_runner_pct"] = round(safe_float(open_runner.get("mfe_pct")), 4)
    else:
        HEALTH["open_runner_symbol"] = None
        HEALTH["open_runner_setup"] = None
        HEALTH["open_runner_side"] = None
        HEALTH["open_runner_r"] = 0.0
        HEALTH["open_runner_pct"] = 0.0

    HEALTH["top_mfe_month"] = stats["top_mfe"]
    HEALTH["runners_3r"] = stats["runners_3r"]
    HEALTH["runners_5r"] = stats["runners_5r"]
    HEALTH["runners_10r"] = stats["runners_10r"]

    setup_stats = {}
    for setup_key, setup_trades in split_by_setup(month_trades).items():
        setup_stats[setup_key] = slim_stats(calc_stats(setup_trades))
    HEALTH["setups"] = setup_stats

    direction_stats = {}
    for direction, direction_trades in split_by_direction(month_trades).items():
        direction_stats[direction] = slim_stats(calc_stats(direction_trades))
    HEALTH["directions"] = direction_stats

    HEALTH["ranking_month"] = build_ranking_month(month_trades)
    HEALTH["best_setup"] = HEALTH["ranking_month"][0]["name"] if HEALTH["ranking_month"] else None
    HEALTH["worst_setup"] = HEALTH["ranking_month"][-1]["name"] if HEALTH["ranking_month"] else None
    HEALTH["last_summary_run"] = data_hora_sp_str()


def setup_summary_lines(trades):
    by_setup = split_by_setup(trades)
    lines = []
    for setup_key, setup_trades in by_setup.items():
        s = calc_stats(setup_trades)
        label = SETUPS[setup_key]["label"]
        lines.append(
            f"{label}:\n"
            f"Trades: {s['count']} | WR: {s['winrate']:.2f}%\n"
            f"PF %: {s['profit_factor_pct']:.2f} | PF R: {s['profit_factor_r']:.2f}\n"
            f"Expectancy: {fmt_r(s['expectancy_r'])}\n"
            f"Captura: {s['trend_capture_pct']:.2f}%\n"
            f"PnL: {fmt_pct(s['pnl_pct'])} | {fmt_r(s['pnl_r'])}\n"
            f"MFE médio: {fmt_pct(s['mfe_avg_pct'])} | {fmt_r(s['mfe_avg_r'])}\n"
            f"MAE médio: {fmt_pct(s['mae_avg_pct'])} | {fmt_r(s['mae_avg_r'])}\n"
            f"Devolução média: {fmt_pct(s['giveback_avg_pct'])} | {fmt_r(s['giveback_avg_r'])}"
        )
    return "\n\n".join(lines) if lines else "N/A"


def direction_summary_lines(trades):
    lines = []
    for direction, direction_trades in split_by_direction(trades).items():
        s = calc_stats(direction_trades)
        lines.append(
            f"{direction}:\n"
            f"Trades: {s['count']} | WR: {s['winrate']:.2f}%\n"
            f"PF R: {s['profit_factor_r']:.2f} | Expectancy: {fmt_r(s['expectancy_r'])}\n"
            f"PnL: {fmt_pct(s['pnl_pct'])} | {fmt_r(s['pnl_r'])}"
        )
    return "\n\n".join(lines) if lines else "N/A"


def ranking_text_from_rows(rows):
    if not rows:
        return "N/A"
    lines = []
    for i, row in enumerate(rows, 1):
        lines.append(
            f"{i}. {row['label']} | Trades: {row['trades']} | PF R: {row['profit_factor_r']:.2f} | Exp: {fmt_r(row['expectancy_r'])}"
        )
    return "\n".join(lines)


def trade_line(trade, metric="result"):
    if not trade:
        return "N/A"
    if metric == "mfe":
        return f"{trade.get('symbol')} {trade.get('setup')} {fmt_pct(trade.get('mfe_pct'))} | {fmt_r(trade.get('mfe_r'))}"
    return f"{trade.get('symbol')} {trade.get('setup')} {fmt_pct(trade.get('result_pct'))} | {fmt_r(trade.get('result_r'))}"


def build_summary(period_name, trades, period_signals_override=None):
    refresh_health_stats()
    stats = calc_stats(trades)
    positions = get_positions()
    open_by_setup = {k: 0 for k in SETUPS}
    for p in positions.values():
        setup = p.get("setup")
        if setup in open_by_setup:
            open_by_setup[setup] += 1

    if period_signals_override is not None:
        period_signals = period_signals_override
    else:
        period_signals = signals_today() if period_name == "DIA" else signals_month()

    top_lines = []
    for item in stats["top_mfe"]:
        top_lines.append(
            f"{item.get('symbol')} {item.get('setup')} {fmt_pct(item.get('mfe_pct'))} | {fmt_r(item.get('mfe_r'))}"
        )
    top_text = "\n".join(top_lines) if top_lines else "N/A"

    setup_text = setup_summary_lines(trades)
    direction_text = direction_summary_lines(trades)
    ranking_text = ranking_text_from_rows(build_ranking_month(trades))

    return (
        f"🐢 RESUMO TURTLE BREAKOUT PRO 2.0 - {period_name}\n"
        f"{agora_sp().strftime('%d/%m/%Y')}\n\n"
        f"Sinais Turtle: {len(period_signals)}\n"
        f"Turtle 20: {sum(1 for s in period_signals if s.get('setup') == 'TURTLE20')}\n"
        f"Turtle 55: {sum(1 for s in period_signals if s.get('setup') == 'TURTLE55')}\n"
        f"LONG: {sum(1 for s in period_signals if s.get('side') == 'LONG')}\n"
        f"SHORT: {sum(1 for s in period_signals if s.get('side') == 'SHORT')}\n\n"
        f"🐢 FUNIL TURTLE\n"
        f"Ativos analisados: {HEALTH.get('funnel_today', {}).get('ativos_analisados', 0)}\n"
        f"Rompimentos 20 BUY: {HEALTH.get('funnel_today', {}).get('rompimentos_20_buy', 0)}\n"
        f"Rompimentos 20 SELL: {HEALTH.get('funnel_today', {}).get('rompimentos_20_sell', 0)}\n"
        f"Rompimentos 55 BUY: {HEALTH.get('funnel_today', {}).get('rompimentos_55_buy', 0)}\n"
        f"Rompimentos 55 SELL: {HEALTH.get('funnel_today', {}).get('rompimentos_55_sell', 0)}\n"
        f"Reprovados por ATR: {HEALTH.get('funnel_today', {}).get('reprovados_atr', 0)}\n"
        f"Reprovados por risco: {HEALTH.get('funnel_today', {}).get('reprovados_risco', 0)}\n"
        f"Reprovados por score: {HEALTH.get('funnel_today', {}).get('reprovados_score', 0)}\n"
        f"Reprovados por cooldown: {HEALTH.get('funnel_today', {}).get('reprovados_cooldown', 0)}\n"
        f"Reprovados por posição ativa: {HEALTH.get('funnel_today', {}).get('reprovados_posicao_ativa', 0)}\n"
        f"Reprovados pelo Risk Guard: {HEALTH.get('funnel_today', {}).get('reprovados_risk_guard', 0)}\n"
        f"Sinais enviados: {HEALTH.get('funnel_today', {}).get('sinais_enviados', 0)}\n\n"
        f"Trades encerrados: {stats['count']}\n"
        f"Wins: {stats['wins']}\n"
        f"Breakeven: {stats['be']}\n"
        f"Loss: {stats['losses']}\n"
        f"Win rate: {stats['winrate']:.2f}%\n"
        f"Profit Factor %: {stats['profit_factor_pct']:.2f}\n"
        f"Profit Factor R: {stats['profit_factor_r']:.2f}\n"
        f"Expectancy: {fmt_r(stats['expectancy_r'])} por trade\n"
        f"Captura de tendência: {stats['trend_capture_pct']:.2f}%\n\n"
        f"TP50 atingidos: {stats['tp50_hits']}\n"
        f"Tempo médio até TP50: {stats['avg_candles_to_tp50']:.1f} ciclos de gestão\n"
        f"Stops: {HEALTH['stops_today'] if period_name == 'DIA' else 'ver eventos'}\n"
        f"Saídas Turtle: {HEALTH['turtle_exits_today'] if period_name == 'DIA' else 'ver eventos'}\n\n"
        f"PnL realizado:\n"
        f"{fmt_pct(stats['pnl_pct'])} | {fmt_r(stats['pnl_r'])}\n\n"
        f"MFE médio:\n"
        f"{fmt_pct(stats['mfe_avg_pct'])} | {fmt_r(stats['mfe_avg_r'])}\n\n"
        f"MAE médio:\n"
        f"{fmt_pct(stats['mae_avg_pct'])} | {fmt_r(stats['mae_avg_r'])}\n\n"
        f"Devolução média:\n"
        f"{fmt_pct(stats['giveback_avg_pct'])} | {fmt_r(stats['giveback_avg_r'])}\n\n"
        f"Maior runner aberto:\n"
        f"{HEALTH.get('open_runner_symbol') or 'N/A'} {HEALTH.get('open_runner_setup') or ''} {fmt_pct(HEALTH.get('open_runner_pct', 0))} | {fmt_r(HEALTH.get('open_runner_r', 0))}\n\n"
        f"Runners:\n"
        f"3R+: {stats['runners_3r']}\n"
        f"5R+: {stats['runners_5r']}\n"
        f"10R+: {stats['runners_10r']}\n\n"
        f"Por setup:\n"
        f"{setup_text}\n\n"
        f"Por direção:\n"
        f"{direction_text}\n\n"
        f"Ranking dos setups:\n"
        f"{ranking_text}\n\n"
        f"Top 5 MFE do período:\n"
        f"{top_text}\n\n"
        f"Maior runner:\n"
        f"{trade_line(stats['biggest_runner'], metric='mfe')}\n\n"
        f"Melhor trade:\n"
        f"{trade_line(stats['best_trade'])}\n\n"
        f"Pior trade:\n"
        f"{trade_line(stats['worst_trade'])}\n\n"
        f"Trades ainda ativos: {len(positions)}\n"
        f"Turtle20 ativos: {open_by_setup.get('TURTLE20', 0)}\n"
        f"Turtle55 ativos: {open_by_setup.get('TURTLE55', 0)}\n\n"
        f"Modo: PAPER / SEM BINGX"
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
# WATCHDOG
# ==============================================================================

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
                    safe_send_telegram(
                        "🚨 WATCHDOG TURTLE BREAKOUT PRO 2.0\n\n"
                        + "\n".join([f"- {r}" for r in reasons])
                    )
                    HEALTH["last_watchdog_alert"] = data_hora_sp_str()
                    HEALTH["last_watchdog_alert_ts"] = time.time()
            else:
                HEALTH["watchdog_last_status"] = "OK"

        except Exception as exc:
            HEALTH["last_warning"] = f"watchdog: {exc}"

        time.sleep(WATCHDOG_SLEEP_SECONDS)

# ==============================================================================
# TELEGRAM COMMANDS
# ==============================================================================

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


def positions_text():
    positions = get_positions()
    if not positions:
        return "🐢 Turtle: nenhuma posição paper aberta."

    lines = ["🐢 POSIÇÕES TURTLE PAPER\n"]

    for p in positions.values():
        price = safe_fetch_price(p["symbol"])
        current = ""
        if price:
            pnl = pnl_pct_for_side(p["side"], p["entry"], price)
            rr = r_for_side(p["side"], p["entry"], p.get("initial_stop", p["stop"]), price)
            current = f"Atual: {fmt_price(price)} | {fmt_pct(pnl)} | {fmt_r(rr)}\n"

        lines.append(
            f"{p.get('setup_label', p.get('setup'))} - {p['symbol']} {p['side']}\n"
            f"Entrada: {fmt_price(p['entry'])}\n"
            f"SL: {fmt_price(p['stop'])}\n"
            f"TP50: {fmt_price(p['tp50'])}\n"
            f"{current}"
            f"MFE: {fmt_pct(p.get('mfe_pct', 0))} | {fmt_r(p.get('mfe_r', 0))}\n"
            f"MAE: {fmt_pct(p.get('mae_pct', 0))} | {fmt_r(p.get('mae_r', 0))}\n"
        )

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n\n..."
    return text


def top_mfe_text():
    stats = calc_stats(trades_month())
    if not stats["top_mfe"]:
        return "🐢 TOP 5 MFE DO MÊS\n\nN/A"

    lines = ["🐢 TOP 5 MFE DO MÊS\n"]
    for x in stats["top_mfe"]:
        lines.append(
            f"{x.get('symbol')} {x.get('setup')} {x.get('side')}\n"
            f"MFE: {fmt_pct(x.get('mfe_pct'))} | {fmt_r(x.get('mfe_r'))}\n"
        )
    return "\n".join(lines)


def events_text():
    events = [e for e in get_events() if str(e.get("created_at", "")).startswith(date_key_br())]
    if not events:
        return "🐢 EVENTOS TURTLE DO DIA\n\nN/A"

    lines = ["🐢 EVENTOS TURTLE DO DIA\n"]
    for e in events[-30:]:
        lines.append(
            f"{e.get('created_at')} - {e.get('event_type')} - {e.get('symbol')} {e.get('setup')} {e.get('side')}"
        )
    return "\n".join(lines)


def ranking_command_text():
    rows = build_ranking_month(trades_month())
    return "🏆 RANKING TURTLE DO MÊS\n\n" + ranking_text_from_rows(rows)



def funnel_text():
    f = funnel_snapshot()
    return (
        "🐢 FUNIL TURTLE DO DIA\n\n"
        f"Ativos analisados: {f['ativos_analisados']}\n"
        f"Rompimentos 20 BUY: {f['rompimentos_20_buy']}\n"
        f"Rompimentos 20 SELL: {f['rompimentos_20_sell']}\n"
        f"Rompimentos 55 BUY: {f['rompimentos_55_buy']}\n"
        f"Rompimentos 55 SELL: {f['rompimentos_55_sell']}\n\n"
        f"Reprovados por ATR: {f['reprovados_atr']}\n"
        f"Reprovados por risco: {f['reprovados_risco']}\n"
        f"Reprovados por score: {f['reprovados_score']}\n"
        f"Reprovados por cooldown: {f['reprovados_cooldown']}\n"
        f"Reprovados por posição ativa: {f['reprovados_posicao_ativa']}\n\n"
        f"Sinais enviados: {f['sinais_enviados']}"
    )

def handle_command(text):
    text = (text or "").strip().lower()

    if text in ["/start", "/comandos"]:
        safe_send_telegram(
            "🐢 COMANDOS TURTLE BREAKOUT PRO 2.0\n\n"
            "/health - status do robô\n"
            "/posicoes - posições paper abertas\n"
            "/resumo - resumo do dia\n"
            "/mensal - resumo do mês\n"
            "/setups - estatísticas por setup\n"
            "/direcoes - estatísticas LONG x SHORT\n"
            "/ranking - ranking mensal dos setups\n"
            "/score - explica o Score Turtle\n"
            "/funil - funil de detecção do dia\n"
            "/eventos - eventos de gestão do dia\n"
            "/top - Top 5 MFE do mês\n"
            "/watchlist - tamanho da watchlist\n"
            "/teste - testar Telegram"
        )
        return

    if text == "/teste":
        safe_send_telegram("✅ Turtle Breakout PRO 2.0 online em modo PAPER / SEM BINGX.")
        return

    if text == "/health":
        refresh_health_stats()
        safe_send_telegram(json.dumps(HEALTH, ensure_ascii=False, indent=2)[:3900])
        return

    if text == "/watchlist":
        wl = load_watchlist()
        safe_send_telegram(
            f"🐢 WATCHLIST TURTLE\n\n"
            f"Total: {len(wl)}\n"
            f"Inválidos: {len(HEALTH.get('watchlist_invalid', []))}"
        )
        return

    if text == "/posicoes":
        safe_send_telegram(positions_text())
        return

    if text == "/resumo":
        safe_send_telegram(build_summary("DIA", trades_today()))
        return

    if text == "/mensal":
        safe_send_telegram(build_summary("MÊS", trades_month()))
        return

    if text == "/setups":
        safe_send_telegram("🐢 ESTATÍSTICAS POR SETUP - MÊS\n\n" + setup_summary_lines(trades_month()))
        return

    if text == "/direcoes":
        safe_send_telegram("🐢 ESTATÍSTICAS LONG x SHORT - MÊS\n\n" + direction_summary_lines(trades_month()))
        return

    if text == "/ranking":
        safe_send_telegram(ranking_command_text())
        return

    if text == "/funil":
        safe_send_telegram(funnel_text())
        return

    if text == "/score":
        safe_send_telegram(
            "🐢 SCORE TURTLE\n\n"
            "O Score Turtle vai de 0 a 100 e mede a qualidade do rompimento sem alterar a essência Turtle.\n\n"
            "Componentes:\n"
            "- ATR %: volatilidade suficiente\n"
            "- Volume relativo: expansão no rompimento\n"
            "- Breakout em ATR: força do rompimento\n"
            "- Canal em ATR: estrutura do range rompido\n\n"
            "Qualidade:\n"
            "80+: ALTA 🟢\n"
            "65-79: MÉDIA 🟡\n"
            "0-64: BAIXA 🔴"
        )
        return

    if text == "/eventos":
        safe_send_telegram(events_text())
        return

    if text == "/top":
        safe_send_telegram(top_mfe_text())
        return


def command_loop():
    offset = None

    while True:
        try:
            updates = telegram_get_updates(offset)
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                if CHAT_ID and chat_id != str(CHAT_ID):
                    continue

                text = msg.get("text", "")
                if text.startswith("/"):
                    HEALTH["last_command_run"] = data_hora_sp_str()
                    handle_command(text)

        except Exception as exc:
            HEALTH["last_warning"] = f"command: {exc}"

        time.sleep(COMMAND_SLEEP_SECONDS)

# ==============================================================================
# FLASK ROUTES
# ==============================================================================

@app.route("/")
def home():
    return f"{BOT_NAME} Online - PAPER / SEM BINGX"


@app.route("/health")
def health_route():
    refresh_health_stats()
    return HEALTH


@app.route("/positions")
def positions_route():
    return get_positions()


@app.route("/trades")
def trades_route():
    return {"trades": get_trades()[-300:]}


@app.route("/signals")
def signals_route():
    return {"signals": get_signals()[-300:]}


@app.route("/events")
def events_route():
    return {"events": get_events()[-300:]}


@app.route("/funnel")
def funnel_route():
    refresh_health_stats()
    return {"funnel_today": HEALTH.get("funnel_today", funnel_snapshot())}


@app.route("/summary")
def summary_route():
    refresh_health_stats()
    return {
        "day": calc_stats(trades_today()),
        "month": calc_stats(trades_month()),
        "setups": HEALTH.get("setups", {}),
        "directions": HEALTH.get("directions", {}),
        "ranking_month": HEALTH.get("ranking_month", []),
        "funnel_today": HEALTH.get("funnel_today", {}),
        "events_today": {
            "tp50": HEALTH.get("tp50_today"),
            "be": HEALTH.get("be_today"),
            "stops": HEALTH.get("stops_today"),
            "turtle_exits": HEALTH.get("turtle_exits_today"),
        },
        "health": HEALTH,
    }


@app.route("/riskguardconnector")
@app.route("/turtle/riskguardconnector")
@app.route("/turtle/risk/guard/connector")
def risk_guard_connector_route():
    return risk_guard_connector_payload()


@app.route("/riskguardconnector/text")
@app.route("/turtle/riskguardconnector/text")
@app.route("/turtle/risk/guard/connector/text")
def risk_guard_connector_text_route():
    return {"text": risk_guard_connector_text()}


@app.route("/reset_paper", methods=["POST"])
def reset_paper_route():
    # Proteção simples para evitar reset acidental.
    token = request.args.get("token") or request.headers.get("X-Reset-Token")
    expected = os.environ.get("TURTLE_RESET_TOKEN")
    if expected and token != expected:
        return {"ok": False, "error": "token inválido"}, 403

    redis_set_json(POSITIONS_KEY, {})
    redis_set_json(SIGNALS_KEY, [])
    redis_set_json(TRADES_KEY, [])
    redis_set_json(EVENTS_KEY, [])
    redis_set_json(COOLDOWN_KEY, {})
    redis_set_json(LAST_CANDLES_KEY, {})
    redis_set_json(FUNNEL_KEY, {})
    refresh_health_stats()
    return {"ok": True, "message": "paper resetado"}

# ==============================================================================
# STARTUP
# ==============================================================================

def startup():
    HEALTH["started_at"] = data_hora_sp_str()

    try:
        load_watchlist()
    except Exception:
        pass

    safe_send_telegram(
        "🐢 Turtle Breakout PRO 2.0 iniciado\n\n"
        "Modo: PAPER / SEM BINGX\n"
        f"Timeframe: {TIMEFRAME}\n\n"
        f"Setups ativos: {', '.join(SETUPS.keys())}\n"
        f"Risk Guard Connector: {'ON' if TURTLE_RISK_GUARD_CONNECTOR_ENABLED else 'OFF'} | fail_closed={TURTLE_RISK_GUARD_FAIL_CLOSED}\n"
        f"ENABLE_TURTLE20={os.environ.get('ENABLE_TURTLE20')} | ENABLE_TURTLE55={os.environ.get('ENABLE_TURTLE55')}\n"
        f"Turtle20: entrada {ALL_SETUPS['TURTLE20']['entry_len']} / saída {ALL_SETUPS['TURTLE20']['exit_len']}\n"
        f"Turtle55: entrada {ALL_SETUPS['TURTLE55']['entry_len']} / saída {ALL_SETUPS['TURTLE55']['exit_len']}\n\n"
        f"Stop: {ATR_STOP_MULT} ATR\n"
        f"TP50: {TP50_R}R\n"
        "MFE/MAE, funil Turtle, devolução, captura de tendência, Score Turtle, runner aberto, expectancy, PF em R, ranking e estatísticas LONG/SHORT ativados."
    )

    threading.Thread(target=scanner_loop, daemon=True).start()
    threading.Thread(target=management_loop, daemon=True).start()
    threading.Thread(target=summary_loop, daemon=True).start()
    threading.Thread(target=watchdog_loop, daemon=True).start()
   # threading.Thread(target=command_loop, daemon=True).start()


startup()

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=porta)
