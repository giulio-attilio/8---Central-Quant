# SMART PREDATOR - SMC H1
# Versão: 2026-06-23-SMART-PREDATOR-STANDBY-CENTRAL-QUANT
#
# Stand-by para Central Quant:
# - Estrutura padronizada como Donkey/Cobra/Meme.
# - Robô inicia, responde Telegram, health, watchlist, resumo, mensal, funil e watchdog.
# - Por padrão NÃO envia novos sinais: SMART_PREDATOR_ENABLED=false.
# - Para ativar no Render: SMART_PREDATOR_ENABLED=true.
# - Mantém lógica: Liquidity Sweep H1 + CHOCH M15 + Order Block H1 + Reteste.
# - Gestão: TP50 -> BE + offset -> Trailing ATR.
# - Futuro BingX real: usar SL/TP virtuais pela Central Quant.

from flask import Flask
import os
import json
import time
import threading
import requests
import numpy as np
import pandas as pd
import ccxt
from datetime import datetime, timezone, timedelta
from upstash_redis import Redis

app = Flask(__name__)

# ====================================================
# IDENTIDADE / STAND-BY / LOCKS
# ====================================================

BOT_NAME = os.environ.get("BOT_NAME", "Smart Predator")
SERVICE_MODE = "SMART_PREDATOR"
BOT_VERSION = "2026-06-23-SMART-PREDATOR-STANDBY-CENTRAL-QUANT"

redis_lock = threading.Lock()
ultimo_update_id = None

# ====================================================
# TELEGRAM / REDIS / EXCHANGE
# ====================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = os.environ.get("PREDATOR_WATCHLIST_FILE", "watchlists/predator.json")

POSITIONS_KEY = "smartpredator:positions"
SIGNALS_KEY = "smartpredator:signals"
TRADES_KEY = "smartpredator:trades"
DAILY_SUMMARY_KEY = "smartpredator:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "smartpredator:monthly_summary_sent"
SWEEP_STATE_KEY = "smartpredator:sweep_state"
SIGNAL_COOLDOWN_KEY = "smartpredator:signal_cooldown"
STARTUP_MESSAGE_KEY = "smartpredator:startup_message_sent_v3"
FUNNEL_STATS_KEY = "smartpredator:funnel_stats"

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

redis = Redis(
    url=UPSTASH_REDIS_REST_URL,
    token=UPSTASH_REDIS_REST_TOKEN
)

# ====================================================
# CONFIGURAÇÕES PRINCIPAIS
# ====================================================

TIMEFRAME_H1 = os.environ.get("PREDATOR_TIMEFRAME", "1h")
TIMEFRAME_H4 = os.environ.get("PREDATOR_CONTEXT_TIMEFRAME", "4h")
TIMEFRAME_M15 = os.environ.get("PREDATOR_CHOCH_TIMEFRAME", "15m")

# IMPORTANTE: default false para stand-by.
SMART_PREDATOR_ENABLED = os.environ.get("SMART_PREDATOR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "sim", "on"}
SMART_PREDATOR_AUTO_TRADE = os.environ.get("SMART_PREDATOR_AUTO_TRADE", "false").strip().lower() in {"1", "true", "yes", "sim", "on"}

SCANNER_SLEEP_SECONDS = int(os.environ.get("PREDATOR_SCANNER_SLEEP_SECONDS", os.environ.get("SCANNER_SLEEP_SECONDS", "60")))
COMMAND_SLEEP_SECONDS = int(os.environ.get("COMMAND_SLEEP_SECONDS", "2"))

SWING_LOOKBACK = int(os.environ.get("PREDATOR_SWING_LOOKBACK", "10"))
CHOCH_LOOKBACK = int(os.environ.get("PREDATOR_CHOCH_LOOKBACK", "8"))
OB_LOOKBACK = int(os.environ.get("PREDATOR_OB_LOOKBACK", "12"))

MIN_PREDATOR_SCORE = int(os.environ.get("PREDATOR_MIN_SCORE", os.environ.get("MIN_PREDATOR_SCORE", "70")))

ATR_LEN = int(os.environ.get("ATR_LEN", "14"))
ADX_LEN = int(os.environ.get("ADX_LEN", "14"))
EMA50 = 50

MIN_ADX_H4 = float(os.environ.get("PREDATOR_MIN_ADX_H4", os.environ.get("MIN_ADX_H4", "15")))
VOLUME_MULTIPLIER = float(os.environ.get("PREDATOR_VOLUME_MULTIPLIER", os.environ.get("VOLUME_MULTIPLIER", "1.2")))

MAX_OPEN_POSITIONS = int(os.environ.get("PREDATOR_MAX_OPEN_POSITIONS", os.environ.get("MAX_OPEN_POSITIONS", "20")))
USE_MAX_RISK_FILTER = os.environ.get("PREDATOR_USE_MAX_RISK_FILTER", os.environ.get("USE_MAX_RISK_FILTER", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
MAX_RISK_H1 = float(os.environ.get("PREDATOR_MAX_RISK_H1", os.environ.get("MAX_RISK_H1", "2.5")))

TP50_R = float(os.environ.get("PREDATOR_TP50_R", os.environ.get("TP50_R", "2.0")))
BE_OFFSET_PCT = float(os.environ.get("PREDATOR_BE_OFFSET_PCT", os.environ.get("BE_OFFSET_PCT", "0.10")))
TRAIL_ATR_MULT = float(os.environ.get("PREDATOR_TRAIL_ATR_MULT", os.environ.get("TRAIL_ATR_MULT", "2.0")))
PROTECTION_SECONDS = int(os.environ.get("PREDATOR_PROTECTION_SECONDS", os.environ.get("PROTECTION_SECONDS", "300")))

SIGNAL_COOLDOWN_SECONDS = int(os.environ.get("PREDATOR_SIGNAL_COOLDOWN_SECONDS", str(60 * 60)))

ENABLE_SPIKE_FILTER = os.environ.get("PREDATOR_ENABLE_SPIKE_FILTER", os.environ.get("ENABLE_SPIKE_FILTER", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
SPIKE_RANGE_ATR_MULT = float(os.environ.get("PREDATOR_SPIKE_RANGE_ATR_MULT", os.environ.get("SPIKE_RANGE_ATR_MULT", "6")))
SPIKE_BODY_ATR_MULT = float(os.environ.get("PREDATOR_SPIKE_BODY_ATR_MULT", os.environ.get("SPIKE_BODY_ATR_MULT", "4")))

DAILY_SUMMARY_HOUR = int(os.environ.get("PREDATOR_DAILY_SUMMARY_HOUR", os.environ.get("DAILY_SUMMARY_HOUR", "23")))
DAILY_SUMMARY_MINUTE = int(os.environ.get("PREDATOR_DAILY_SUMMARY_MINUTE", os.environ.get("DAILY_SUMMARY_MINUTE", "55")))

MONTHLY_SUMMARY_DAY = int(os.environ.get("PREDATOR_MONTHLY_SUMMARY_DAY", os.environ.get("MONTHLY_SUMMARY_DAY", "1")))
MONTHLY_SUMMARY_HOUR = int(os.environ.get("PREDATOR_MONTHLY_SUMMARY_HOUR", os.environ.get("MONTHLY_SUMMARY_HOUR", "23")))
MONTHLY_SUMMARY_MINUTE = int(os.environ.get("PREDATOR_MONTHLY_SUMMARY_MINUTE", os.environ.get("MONTHLY_SUMMARY_MINUTE", "55")))

WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

HEALTH = {
    "started_at": None,
    "last_scanner_run": None,
    "last_management_run": None,
    "last_success": None,
    "last_error": None,
    "last_warning": None,
    "last_signals_sent": 0,
    "last_positions_count": 0,
    "watchlist_total": 0,
    "watchlist_valid": 0,
    "watchlist_invalid": [],
    "last_invalid_watchlist_check": None,
    "last_watchdog_alert": None,
    "last_watchdog_alert_ts": 0,
    "watchdog_last_check": None,
    "watchdog_last_status": "OK"
}

DEFAULT_FUNNEL_STATS = {
    "scanner_runs": 0,
    "symbols_scanned": 0,
    "bullish_sweeps": 0,
    "bearish_sweeps": 0,
    "bullish_choch": 0,
    "bearish_choch": 0,
    "bullish_ob": 0,
    "bearish_ob": 0,
    "bullish_retests": 0,
    "bearish_retests": 0,
    "risk_rejected": 0,
    "score_70_plus": 0,
    "score_80_plus": 0,
    "score_85_plus": 0,
    "signals_detected": 0,
    "signals_sent": 0,
    "long_signals": 0,
    "short_signals": 0,
    "last_update": None
}

# ====================================================
# UTILITÁRIOS
# ====================================================

def agora_sp():
    return datetime.now(timezone(timedelta(hours=-3)))


def data_hoje_sp_str():
    return agora_sp().strftime("%Y-%m-%d")


def data_hora_sp_str():
    return agora_sp().strftime("%d/%m/%Y %H:%M")


def nome_limpo(symbol):
    return symbol.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")


def normalizar_texto(msg):
    if msg is None:
        return ""
    msg = str(msg)
    try:
        if "Ã" in msg or "â" in msg or "ðŸ" in msg:
            msg = msg.encode("latin1").decode("utf-8")
    except Exception:
        pass
    return msg


def fmt_br(v, casas=8):
    try:
        return f"{float(v):,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def fmt_pct(v):
    try:
        return f"{float(v):+.2f}%".replace(".", ",")
    except Exception:
        return str(v)


def check_bool(valor):
    return "✅" if valor else "❌"


def risco_label(risco_pct):
    try:
        r = float(risco_pct)
    except Exception:
        return "⚪ N/A"
    if r <= 1.5:
        return "🟢 IDEAL"
    if r <= 2.5:
        return "🟡 ATENÇÃO"
    return "🔴 ALTO"


def safe_send_telegram(msg):
    msg = normalizar_texto(msg)

    if not TOKEN or not CHAT_ID:
        print(msg)
        return

    partes = [msg[i:i + 3900] for i in range(0, len(msg), 3900)]
    if not partes:
        partes = [""]

    for parte in partes:
        payload = {"chat_id": CHAT_ID, "text": parte}
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=20
            )
            time.sleep(0.35)
        except Exception as e:
            print("ERRO TELEGRAM:", e)


def enviar_texto(chat_id, msg):
    msg = normalizar_texto(msg)

    if not TOKEN:
        print(msg)
        return

    partes = [msg[i:i + 3900] for i in range(0, len(msg), 3900)]
    if not partes:
        partes = [""]

    for parte in partes:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                data=json.dumps({"chat_id": chat_id, "text": parte}, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=20
            )
            time.sleep(0.35)
        except Exception as e:
            print("ERRO AO RESPONDER TELEGRAM:", e)


def redis_get_json(key, padrao):
    with redis_lock:
        try:
            data = redis.get(key)
            if data is None:
                return padrao
            if isinstance(data, str):
                return json.loads(data)
            return data
        except Exception as e:
            print(f"ERRO REDIS GET {key}:", e)
            return padrao


def redis_set_json(key, value):
    with redis_lock:
        try:
            redis.set(key, json.dumps(value, ensure_ascii=False))
        except Exception as e:
            print(f"ERRO REDIS SET {key}:", e)


def carregar_watchlist():
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("ERRO WATCHLIST:", e)
        return []


def validar_watchlist_bingx(watchlist, avisar_telegram=False):
    validos = []
    invalidos = []

    try:
        markets = exchange.load_markets()
    except Exception as e:
        print("ERRO AO CARREGAR MERCADOS BINGX:", e)
        HEALTH["watchlist_total"] = len(watchlist)
        HEALTH["watchlist_valid"] = len(watchlist)
        HEALTH["watchlist_invalid"] = []
        HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
        HEALTH["last_error"] = f"Erro load_markets BingX: {e}"
        return watchlist

    for symbol in watchlist:
        if symbol in markets:
            validos.append(symbol)
        else:
            invalidos.append(symbol)

    HEALTH["watchlist_total"] = len(watchlist)
    HEALTH["watchlist_valid"] = len(validos)
    HEALTH["watchlist_invalid"] = invalidos
    HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()

    if invalidos:
        msg = (
            "⚠️ Ativos inválidos na watchlist BingX:\n\n"
            + "\n".join(invalidos)
            + "\n\nEles serão ignorados pelo Smart Predator."
        )
        print(msg)
        if avisar_telegram:
            safe_send_telegram(msg)

    return validos


def carregar_posicoes():
    return redis_get_json(POSITIONS_KEY, {})


def salvar_posicoes(dados):
    redis_set_json(POSITIONS_KEY, dados)


def carregar_sinais():
    return redis_get_json(SIGNALS_KEY, {})


def salvar_sinais(dados):
    redis_set_json(SIGNALS_KEY, dados)


def carregar_trades():
    dados = redis_get_json(TRADES_KEY, [])
    return dados if isinstance(dados, list) else []


def salvar_trades(dados):
    if not isinstance(dados, list):
        dados = []
    redis_set_json(TRADES_KEY, dados)


def registrar_evento_trade(evento):
    trades = carregar_trades()
    trades.append(evento)
    if len(trades) > 3000:
        trades = trades[-3000:]
    salvar_trades(trades)


def carregar_sweep_state():
    return redis_get_json(SWEEP_STATE_KEY, {})


def salvar_sweep_state(dados):
    redis_set_json(SWEEP_STATE_KEY, dados)


def carregar_signal_cooldown():
    return redis_get_json(SIGNAL_COOLDOWN_KEY, {})


def salvar_signal_cooldown(dados):
    redis_set_json(SIGNAL_COOLDOWN_KEY, dados)


def em_cooldown(symbol, side):
    dados = carregar_signal_cooldown()
    chave = f"{symbol}_{side}"
    ultimo = float(dados.get(chave, 0))
    return time.time() - ultimo < SIGNAL_COOLDOWN_SECONDS


def marcar_cooldown(symbol, side):
    dados = carregar_signal_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = time.time()

    if len(dados) > 500:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-500:])

    salvar_signal_cooldown(dados)


def carregar_funnel_stats():
    dados = redis_get_json(FUNNEL_STATS_KEY, {})
    if not isinstance(dados, dict):
        dados = {}
    stats = DEFAULT_FUNNEL_STATS.copy()
    stats.update(dados)
    return stats


def salvar_funnel_stats(stats):
    if not isinstance(stats, dict):
        stats = DEFAULT_FUNNEL_STATS.copy()
    stats["last_update"] = data_hora_sp_str()
    redis_set_json(FUNNEL_STATS_KEY, stats)


def inc_funnel_stat(campo, valor=1):
    stats = carregar_funnel_stats()
    try:
        stats[campo] = int(stats.get(campo, 0)) + int(valor)
    except Exception:
        stats[campo] = valor
    salvar_funnel_stats(stats)


def resetar_funnel_stats():
    stats = DEFAULT_FUNNEL_STATS.copy()
    stats["last_update"] = data_hora_sp_str()
    redis_set_json(FUNNEL_STATS_KEY, stats)


def contar_posicoes_ativas():
    try:
        posicoes = carregar_posicoes()
        return len([p for p in posicoes.values() if p.get("status") != "ENCERRADO"])
    except Exception:
        return 0


def existe_posicao_ativa(symbol):
    posicoes = carregar_posicoes()
    return symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO"


def limite_posicoes_atingido():
    return contar_posicoes_ativas() >= MAX_OPEN_POSITIONS


def pnl_pct(side, entry, price):
    if side == "LONG":
        return ((price - entry) / entry) * 100
    return ((entry - price) / entry) * 100


def atualizar_mfe_posicao(p, preco_atual):
    try:
        side = p.get("side")
        entry = float(p.get("entry"))
        pnl_atual = pnl_pct(side, entry, float(preco_atual))
        mfe_atual = float(p.get("mfe_max_pct", 0))
        if pnl_atual > mfe_atual:
            p["mfe_max_pct"] = pnl_atual
            p["mfe_updated_at"] = data_hora_sp_str()
            return True
    except Exception:
        pass
    return False

# ====================================================
# INDICADORES
# ====================================================

def calcular_atr(df, period=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    return tr.ewm(alpha=1 / period, adjust=False).mean()


def calcular_adx(df, period=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()

    return adx, plus_di, minus_di


def preparar_df(df):
    df = df.copy()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean()
    df["atr14"] = calcular_atr(df, ATR_LEN)

    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["vol_avg20"]
    df["volume_ok"] = df["volume_ratio"] >= VOLUME_MULTIPLIER

    adx, plus_di, minus_di = calcular_adx(df, ADX_LEN)
    df["adx"] = adx

    candle_range = (df["high"] - df["low"]).abs()
    candle_body = (df["close"] - df["open"]).abs()
    atr = df["atr14"].astype(float)

    if ENABLE_SPIKE_FILTER:
        df["spike_suspeito"] = (
            (candle_range > atr * SPIKE_RANGE_ATR_MULT) |
            (candle_body > atr * SPIKE_BODY_ATR_MULT)
        ).fillna(False)
    else:
        df["spike_suspeito"] = False

    return df


def fetch_df(symbol, timeframe, limit=100):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    return preparar_df(df)


def contexto_h4_txt(candle_h4):
    try:
        close = float(candle_h4["close"])
        ema50 = float(candle_h4["ema50"])
        adx = float(candle_h4["adx"])

        if close > ema50:
            lado = "BULLISH"
        elif close < ema50:
            lado = "BEARISH"
        else:
            lado = "NEUTRO"

        return lado, adx
    except Exception:
        return "N/A", 0.0

# ====================================================
# SMART PREDATOR - SMC CORE
# ====================================================

def previous_low(df, lookback):
    return float(df["low"].iloc[-lookback-2:-2].min())


def previous_high(df, lookback):
    return float(df["high"].iloc[-lookback-2:-2].max())


def detect_bullish_sweep(df, lookback=10):
    if len(df) < lookback + 5:
        return None

    candle = df.iloc[-2]
    level = previous_low(df, lookback)
    swept = float(candle["low"]) < level and float(candle["close"]) > level

    if not swept:
        return None

    return {
        "type": "bullish_sweep",
        "level": level,
        "low": float(candle["low"]),
        "close": float(candle["close"]),
        "timestamp": int(candle["time"])
    }


def detect_bearish_sweep(df, lookback=10):
    if len(df) < lookback + 5:
        return None

    candle = df.iloc[-2]
    level = previous_high(df, lookback)
    swept = float(candle["high"]) > level and float(candle["close"]) < level

    if not swept:
        return None

    return {
        "type": "bearish_sweep",
        "level": level,
        "high": float(candle["high"]),
        "close": float(candle["close"]),
        "timestamp": int(candle["time"])
    }


def _m15_window_after_h1_sweep(df_m15, sweep):
    try:
        sweep_ts = int(sweep.get("timestamp"))
    except Exception:
        return df_m15.iloc[-12:-1]

    start = sweep_ts
    end = time.time() * 1000
    janela = df_m15[(df_m15["time"].astype(int) >= start) & (df_m15["time"].astype(int) < end)]

    if len(janela) < 2:
        return df_m15.iloc[-8:-1]

    return janela


def detect_bullish_choch_m15_after_sweep(df_m15, sweep):
    if df_m15 is None or len(df_m15) < 30 or not sweep:
        return None

    janela = _m15_window_after_h1_sweep(df_m15, sweep)
    if len(janela) < 2:
        return None

    for idx in list(janela.index):
        pos = df_m15.index.get_loc(idx)
        if pos < 4:
            continue

        candle = df_m15.iloc[pos]
        prev = df_m15.iloc[pos - 4:pos]
        internal_high = float(prev["high"].max())

        close = float(candle["close"])
        open_ = float(candle["open"])
        high = float(candle["high"])

        bullish_reversal = close > open_
        broke_structure = close > internal_high or high > internal_high

        if bullish_reversal and broke_structure:
            return {
                "type": "bullish_choch_m15",
                "timeframe": TIMEFRAME_M15,
                "level": internal_high,
                "close": close,
                "high": high,
                "timestamp": int(candle["time"])
            }

    return None


def detect_bearish_choch_m15_after_sweep(df_m15, sweep):
    if df_m15 is None or len(df_m15) < 30 or not sweep:
        return None

    janela = _m15_window_after_h1_sweep(df_m15, sweep)
    if len(janela) < 2:
        return None

    for idx in list(janela.index):
        pos = df_m15.index.get_loc(idx)
        if pos < 4:
            continue

        candle = df_m15.iloc[pos]
        prev = df_m15.iloc[pos - 4:pos]
        internal_low = float(prev["low"].min())

        close = float(candle["close"])
        open_ = float(candle["open"])
        low = float(candle["low"])

        bearish_reversal = close < open_
        broke_structure = close < internal_low or low < internal_low

        if bearish_reversal and broke_structure:
            return {
                "type": "bearish_choch_m15",
                "timeframe": TIMEFRAME_M15,
                "level": internal_low,
                "close": close,
                "low": low,
                "timestamp": int(candle["time"])
            }

    return None


def find_bullish_order_block(df, lookback=12):
    if len(df) < lookback + 5:
        return None

    recent = df.iloc[-lookback-2:-2]

    for i in range(len(recent) - 1, -1, -1):
        candle = recent.iloc[i]
        if float(candle["close"]) < float(candle["open"]):
            return {
                "type": "bullish",
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "open": float(candle["open"]),
                "close": float(candle["close"]),
                "timestamp": int(candle["time"])
            }

    return None


def find_bearish_order_block(df, lookback=12):
    if len(df) < lookback + 5:
        return None

    recent = df.iloc[-lookback-2:-2]

    for i in range(len(recent) - 1, -1, -1):
        candle = recent.iloc[i]
        if float(candle["close"]) > float(candle["open"]):
            return {
                "type": "bearish",
                "low": float(candle["low"]),
                "high": float(candle["high"]),
                "open": float(candle["open"]),
                "close": float(candle["close"]),
                "timestamp": int(candle["time"])
            }

    return None


def price_touched_zone(candle, zone_low, zone_high):
    return float(candle["low"]) <= float(zone_high) and float(candle["high"]) >= float(zone_low)


def is_retesting_bullish_ob(df, ob):
    candle = df.iloc[-2]
    touched = price_touched_zone(candle, ob["low"], ob["high"])
    rejection = float(candle["close"]) > float(candle["open"])
    ob_mid = (float(ob["low"]) + float(ob["high"])) / 2
    close_above_mid = float(candle["close"]) >= ob_mid
    return touched and rejection and close_above_mid


def is_retesting_bearish_ob(df, ob):
    candle = df.iloc[-2]
    touched = price_touched_zone(candle, ob["low"], ob["high"])
    rejection = float(candle["close"]) < float(candle["open"])
    ob_mid = (float(ob["low"]) + float(ob["high"])) / 2
    close_below_mid = float(candle["close"]) <= ob_mid
    return touched and rejection and close_below_mid


def is_retesting_bullish_ob_m15(df_m15, ob):
    if df_m15 is None or len(df_m15) < 10 or not ob:
        return False

    recent = df_m15.iloc[-6:-1]
    ob_mid = (float(ob["low"]) + float(ob["high"])) / 2

    for _, candle in recent.iterrows():
        touched = price_touched_zone(candle, ob["low"], ob["high"])
        rejection = float(candle["close"]) > float(candle["open"])
        close_above_mid = float(candle["close"]) >= ob_mid

        if touched and rejection and close_above_mid:
            return True

    return False


def is_retesting_bearish_ob_m15(df_m15, ob):
    if df_m15 is None or len(df_m15) < 10 or not ob:
        return False

    recent = df_m15.iloc[-6:-1]
    ob_mid = (float(ob["low"]) + float(ob["high"])) / 2

    for _, candle in recent.iterrows():
        touched = price_touched_zone(candle, ob["low"], ob["high"])
        rejection = float(candle["close"]) < float(candle["open"])
        close_below_mid = float(candle["close"]) <= ob_mid

        if touched and rejection and close_below_mid:
            return True

    return False


def calcular_predator_score(has_sweep, has_choch, has_ob, has_rejection, adx_h4, volume_ok):
    score = 0
    reasons = []

    if has_sweep:
        score += 30
        reasons.append("Liquidity Sweep confirmado ✅")

    if has_choch:
        score += 25
        reasons.append("CHOCH estrutural confirmado M15 ✅")

    if has_ob:
        score += 20
        reasons.append("Order Block H1 identificado ✅")

    if has_rejection:
        score += 15
        reasons.append("Reteste com rejeição no OB ✅")

    try:
        if float(adx_h4) >= MIN_ADX_H4:
            score += 5
            reasons.append(f"ADX H4 aceitável: {float(adx_h4):.2f} ✅")
        else:
            reasons.append(f"ADX H4 baixo: {float(adx_h4):.2f} ⚠️")
    except Exception:
        reasons.append("ADX H4 indisponível ⚠️")

    if volume_ok:
        score += 5
        reasons.append("Volume acima da média ✅")
    else:
        reasons.append("Volume sem destaque ⚠️")

    return min(int(score), 100), reasons


def classificar_predator(score):
    try:
        score = int(score)
    except Exception:
        return "FRACA 🔴"

    if score >= 85:
        return "EXCEPCIONAL 🔥"
    if score >= 80:
        return "IDEAL 🟢"
    if score >= 70:
        return "MÉDIA 🟡"
    return "FRACA 🔴"


def calcular_stop_tp_predator(side, entry, ob):
    if side == "LONG":
        sl = float(ob["low"])
        risk_abs = abs(float(entry) - sl)
        tp50 = float(entry) + risk_abs * TP50_R
    else:
        sl = float(ob["high"])
        risk_abs = abs(sl - float(entry))
        tp50 = float(entry) - risk_abs * TP50_R

    return float(sl), float(tp50), float(risk_abs)


def scan_smart_predator_symbol(symbol):
    inc_funnel_stat("symbols_scanned")

    if not SMART_PREDATOR_ENABLED:
        return None

    if existe_posicao_ativa(symbol):
        return None

    if limite_posicoes_atingido():
        return None

    df_h1 = fetch_df(symbol, TIMEFRAME_H1, limit=100)
    df_h4 = fetch_df(symbol, TIMEFRAME_H4, limit=100)
    df_m15 = fetch_df(symbol, TIMEFRAME_M15, limit=100)

    if len(df_h1) < 50 or len(df_h4) < 50 or len(df_m15) < 50:
        return None

    candle_h1 = df_h1.iloc[-2]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle_h1.get("spike_suspeito", False)):
        print(f"CANDLE H1 SUSPEITO IGNORADO: {nome_limpo(symbol)}")
        return None

    h4_context, adx_h4 = contexto_h4_txt(candle_h4)
    volume_ok = bool(candle_h1.get("volume_ok", False))

    bullish_sweep = detect_bullish_sweep(df_h1, SWING_LOOKBACK)
    bearish_sweep = detect_bearish_sweep(df_h1, SWING_LOOKBACK)

    if bullish_sweep:
        inc_funnel_stat("bullish_sweeps")

    if bearish_sweep:
        inc_funnel_stat("bearish_sweeps")

    print(
        f"{nome_limpo(symbol)} | "
        f"H4={h4_context} | ADX_H4={adx_h4:.2f} | "
        f"VolRatio={float(candle_h1.get('volume_ratio', 0)):.2f} | "
        f"SweepBull={bool(bullish_sweep)} | SweepBear={bool(bearish_sweep)}"
    )

    # LONG
    if bullish_sweep and not em_cooldown(symbol, "LONG"):
        bullish_choch = detect_bullish_choch_m15_after_sweep(df_m15, bullish_sweep)
        ob = find_bullish_order_block(df_h1, OB_LOOKBACK)

        if bullish_choch:
            inc_funnel_stat("bullish_choch")

        if ob:
            inc_funnel_stat("bullish_ob")

        if bullish_choch and ob:
            retest = is_retesting_bullish_ob(df_h1, ob) or is_retesting_bullish_ob_m15(df_m15, ob)

            if retest:
                inc_funnel_stat("bullish_retests")
                entry = float(candle_h1["close"])
                sl, tp50, risk_abs = calcular_stop_tp_predator("LONG", entry, ob)
                risk_pct = risk_abs / entry * 100 if entry else 999

                if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
                    inc_funnel_stat("risk_rejected")
                    print(f"SMART PREDATOR LONG IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
                    return None

                score, reasons = calcular_predator_score(True, True, True, True, adx_h4, volume_ok)

                if score >= 70:
                    inc_funnel_stat("score_70_plus")
                if score >= 80:
                    inc_funnel_stat("score_80_plus")
                if score >= 85:
                    inc_funnel_stat("score_85_plus")

                if score >= MIN_PREDATOR_SCORE:
                    inc_funnel_stat("signals_detected")
                    inc_funnel_stat("long_signals")
                    return {
                        "type": "SIGNAL",
                        "signal_type": "SMART_PREDATOR",
                        "symbol": symbol,
                        "symbol_clean": nome_limpo(symbol),
                        "signal": "LONG",
                        "side": "LONG",
                        "timestamp": int(candle_h1["time"]),
                        "entry": entry,
                        "sl": sl,
                        "tp50": tp50,
                        "risk_abs": risk_abs,
                        "risk_pct": risk_pct,
                        "score": score,
                        "quality": classificar_predator(score),
                        "reasons": reasons,
                        "sweep": bullish_sweep,
                        "choch": bullish_choch,
                        "ob": ob,
                        "h4_context": h4_context,
                        "adx_h4": float(adx_h4),
                        "adx_h1": float(candle_h1.get("adx", 0)),
                        "volume_ok": volume_ok,
                        "volume_ratio": float(candle_h1.get("volume_ratio", 0)),
                        "auto_trade": SMART_PREDATOR_AUTO_TRADE
                    }

    # SHORT
    if bearish_sweep and not em_cooldown(symbol, "SHORT"):
        bearish_choch = detect_bearish_choch_m15_after_sweep(df_m15, bearish_sweep)
        ob = find_bearish_order_block(df_h1, OB_LOOKBACK)

        if bearish_choch:
            inc_funnel_stat("bearish_choch")

        if ob:
            inc_funnel_stat("bearish_ob")

        if bearish_choch and ob:
            retest = is_retesting_bearish_ob(df_h1, ob) or is_retesting_bearish_ob_m15(df_m15, ob)

            if retest:
                inc_funnel_stat("bearish_retests")
                entry = float(candle_h1["close"])
                sl, tp50, risk_abs = calcular_stop_tp_predator("SHORT", entry, ob)
                risk_pct = risk_abs / entry * 100 if entry else 999

                if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
                    inc_funnel_stat("risk_rejected")
                    print(f"SMART PREDATOR SHORT IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
                    return None

                score, reasons = calcular_predator_score(True, True, True, True, adx_h4, volume_ok)

                if score >= 70:
                    inc_funnel_stat("score_70_plus")
                if score >= 80:
                    inc_funnel_stat("score_80_plus")
                if score >= 85:
                    inc_funnel_stat("score_85_plus")

                if score >= MIN_PREDATOR_SCORE:
                    inc_funnel_stat("signals_detected")
                    inc_funnel_stat("short_signals")
                    return {
                        "type": "SIGNAL",
                        "signal_type": "SMART_PREDATOR",
                        "symbol": symbol,
                        "symbol_clean": nome_limpo(symbol),
                        "signal": "SHORT",
                        "side": "SHORT",
                        "timestamp": int(candle_h1["time"]),
                        "entry": entry,
                        "sl": sl,
                        "tp50": tp50,
                        "risk_abs": risk_abs,
                        "risk_pct": risk_pct,
                        "score": score,
                        "quality": classificar_predator(score),
                        "reasons": reasons,
                        "sweep": bearish_sweep,
                        "choch": bearish_choch,
                        "ob": ob,
                        "h4_context": h4_context,
                        "adx_h4": float(adx_h4),
                        "adx_h1": float(candle_h1.get("adx", 0)),
                        "volume_ok": volume_ok,
                        "volume_ratio": float(candle_h1.get("volume_ratio", 0)),
                        "auto_trade": SMART_PREDATOR_AUTO_TRADE
                    }

    return None

# ====================================================
# MENSAGENS TELEGRAM
# ====================================================

def formatar_sinal_predator(s):
    side = s["side"]
    emoji = "🟢" if side == "LONG" else "🔴"
    modo = "REAL" if SMART_PREDATOR_AUTO_TRADE else "OBSERVAÇÃO"
    reasons_text = "\n".join(s.get("reasons", []))
    ob = s.get("ob", {})
    ob_txt = (
        f"OB Low: {fmt_br(ob.get('low', 0))}\n"
        f"OB High: {fmt_br(ob.get('high', 0))}"
    )

    return (
        f"🦈 {emoji} SMART PREDATOR - {side} H1\n\n"
        f"Ativo:\n{s.get('symbol_clean', nome_limpo(s.get('symbol', '')))}\n\n"
        f"Modo:\n{modo}\n\n"
        f"Setup:\nLiquidity Sweep + CHOCH + Order Block\n\n"
        f"Motivo:\n{reasons_text}\n\n"
        f"Order Block:\n{ob_txt}\n\n"
        f"Entrada:\n{fmt_br(s.get('entry'))}\n\n"
        f"SL:\n{fmt_br(s.get('sl'))}\n\n"
        f"TP50:\n{fmt_br(s.get('tp50'))}\n\n"
        f"Risco:\n{fmt_br(s.get('risk_pct'), 2)}% - {risco_label(s.get('risk_pct'))}\n\n"
        f"Score Predator:\n{s.get('score')}/100\n\n"
        f"Qualidade:\n{s.get('quality')}\n\n"
        f"Contexto H4:\n{s.get('h4_context')} | ADX {float(s.get('adx_h4', 0)):.2f}\n\n"
        f"Volume H1:\n{float(s.get('volume_ratio', 0)):.2f}x média"
    )


def mensagem_tp50(p, preco):
    return (
        f"🟡 TP50 ATINGIDO - SMART PREDATOR\n\n"
        f"{p.get('symbol_clean', nome_limpo(p.get('symbol', '')))} - {p.get('side')}\n\n"
        f"Preço:\n{fmt_br(preco)}\n\n"
        f"Entrada:\n{fmt_br(p.get('entry'))}\n\n"
        f"Novo status:\nBreakeven ativado ✅"
    )


def mensagem_trailing(p, antigo, novo):
    return (
        f"🟣 TRAILING ATUALIZADO - SMART PREDATOR\n\n"
        f"{p.get('symbol_clean', nome_limpo(p.get('symbol', '')))} - {p.get('side')}\n\n"
        f"Stop anterior:\n{fmt_br(antigo)}\n\n"
        f"Novo stop:\n{fmt_br(novo)}"
    )


def mensagem_saida(p, preco, motivo, resultado):
    return (
        f"🟠 {motivo} - SMART PREDATOR\n\n"
        f"{p.get('symbol_clean', nome_limpo(p.get('symbol', '')))} - {p.get('side')}\n\n"
        f"Entrada:\n{fmt_br(p.get('entry'))}\n\n"
        f"Saída:\n{fmt_br(preco)}\n\n"
        f"Resultado:\n{fmt_pct(resultado)}\n\n"
        f"MFE:\n{fmt_pct(p.get('mfe_max_pct', 0))}"
    )

# ====================================================
# POSIÇÕES / GESTÃO
# ====================================================

def registrar_posicao(s):
    posicoes = carregar_posicoes()
    symbol = s["symbol"]

    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
        print(f"POSIÇÃO JÁ ATIVA IGNORADA: {nome_limpo(symbol)}")
        return False

    if limite_posicoes_atingido():
        print("LIMITE DE POSIÇÕES ATINGIDO")
        return False

    posicoes[symbol] = {
        "symbol": symbol,
        "symbol_clean": s.get("symbol_clean", nome_limpo(symbol)),
        "side": s["side"],
        "entry": float(s["entry"]),
        "sl": float(s["sl"]),
        "initial_sl": float(s["sl"]),
        "tp50": float(s["tp50"]),
        "risk_abs": float(s.get("risk_abs", abs(float(s["entry"]) - float(s["sl"])))),
        "risk_pct": float(s.get("risk_pct", 0)),
        "score": int(s.get("score", 0)),
        "quality": s.get("quality", ""),
        "status": "ABERTO",
        "signal_type": "SMART_PREDATOR",
        "origin": "SMART_PREDATOR",
        "created_at": time.time(),
        "created_at_txt": data_hora_sp_str(),
        "date": data_hoje_sp_str(),
        "timestamp": int(s.get("timestamp", 0)),
        "tp50_hit": False,
        "tp50_hit_at": None,
        "be_active": False,
        "trailing_active": False,
        "last_protection_ts": 0,
        "mfe_max_pct": 0.0,
        "mfe_updated_at": None,
        "closed_at": None,
        "close_reason": None,
        "auto_trade": SMART_PREDATOR_AUTO_TRADE,
        "ob": s.get("ob", {}),
        "sweep": s.get("sweep", {}),
        "choch": s.get("choch", {}),
        "h4_context": s.get("h4_context"),
        "adx_h4": s.get("adx_h4"),
        "volume_ratio": s.get("volume_ratio")
    }

    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": "ENTRY",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": symbol,
        "symbol_clean": s.get("symbol_clean", nome_limpo(symbol)),
        "side": s["side"],
        "entry": float(s["entry"]),
        "sl": float(s["sl"]),
        "tp50": float(s["tp50"]),
        "risk_pct": float(s.get("risk_pct", 0)),
        "score": int(s.get("score", 0)),
        "quality": s.get("quality", ""),
        "signal_type": "SMART_PREDATOR",
        "auto_trade": SMART_PREDATOR_AUTO_TRADE,
        "h4_context": s.get("h4_context"),
        "adx_h4": s.get("adx_h4"),
        "volume_ratio": s.get("volume_ratio")
    })

    marcar_cooldown(symbol, s["side"])
    return True


def obter_preco_atual(symbol):
    ticker = exchange.fetch_ticker(symbol)
    return float(ticker["last"])


def calcular_trailing_stop(symbol, side):
    try:
        df = fetch_df(symbol, TIMEFRAME_H1, limit=50)
        candle = df.iloc[-2]
        atr = float(candle["atr14"])
        ultimos = df.iloc[-10:-1]

        if side == "LONG":
            highest = float(ultimos["high"].max())
            return highest - atr * TRAIL_ATR_MULT

        lowest = float(ultimos["low"].min())
        return lowest + atr * TRAIL_ATR_MULT
    except Exception as e:
        print("ERRO TRAILING:", e)
        return None


def encerrar_posicao(symbol, p, preco_saida, motivo):
    posicoes = carregar_posicoes()
    resultado = pnl_pct(p["side"], float(p["entry"]), float(preco_saida))
    mfe = float(p.get("mfe_max_pct", 0))
    giveback = max(0.0, mfe - resultado)

    p["status"] = "ENCERRADO"
    p["closed_at"] = time.time()
    p["closed_at_txt"] = data_hora_sp_str()
    p["close_reason"] = motivo
    p["exit_price"] = float(preco_saida)
    p["pnl_pct"] = float(resultado)
    p["mfe_gave_back_pct"] = float(giveback)

    posicoes[symbol] = p
    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": motivo,
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": symbol,
        "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
        "side": p.get("side"),
        "entry": float(p.get("entry")),
        "exit": float(preco_saida),
        "pnl": float(resultado),
        "pnl_pct": float(resultado),
        "mfe_max_pct": float(mfe),
        "mfe_gave_back_pct": float(giveback),
        "tp50_hit": bool(p.get("tp50_hit", False)),
        "score": int(p.get("score", 0)),
        "quality": p.get("quality", ""),
        "signal_type": "SMART_PREDATOR"
    })

    safe_send_telegram(mensagem_saida(p, preco_saida, motivo, resultado))


def gerenciar_posicoes():
    posicoes = carregar_posicoes()
    alterou = False

    for symbol, p in list(posicoes.items()):
        try:
            if p.get("status") == "ENCERRADO":
                continue

            side = p.get("side")
            entry = float(p.get("entry"))
            sl = float(p.get("sl"))
            tp50 = float(p.get("tp50"))

            try:
                preco = obter_preco_atual(symbol)
            except Exception as exchange_err:
                print(f"Erro ao buscar preço de {symbol}: {exchange_err}")
                continue

            if atualizar_mfe_posicao(p, preco):
                alterou = True

            # TP50
            if not bool(p.get("tp50_hit", False)):
                hit_tp50 = (
                    (side == "LONG" and preco >= tp50) or
                    (side == "SHORT" and preco <= tp50)
                )

                if hit_tp50:
                    p["tp50_hit"] = True
                    p["tp50_hit_at"] = time.time()
                    p["be_active"] = True
                    p["trailing_active"] = True
                    p["last_protection_ts"] = time.time()

                    if side == "LONG":
                        novo_sl = entry * (1 + BE_OFFSET_PCT / 100)
                        p["sl"] = max(sl, novo_sl)
                    else:
                        novo_sl = entry * (1 - BE_OFFSET_PCT / 100)
                        p["sl"] = min(sl, novo_sl)

                    registrar_evento_trade({
                        "event": "TP50",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                        "side": side,
                        "price": float(preco),
                        "entry": entry,
                        "tp50": tp50,
                        "signal_type": "SMART_PREDATOR"
                    })

                    safe_send_telegram(mensagem_tp50(p, preco))
                    alterou = True

            # Trailing após TP50
            if bool(p.get("trailing_active", False)):
                novo_trail = calcular_trailing_stop(symbol, side)

                if novo_trail:
                    sl_atual = float(p.get("sl"))

                    if side == "LONG" and novo_trail > sl_atual:
                        p["sl"] = float(novo_trail)
                        p["last_protection_ts"] = time.time()
                        registrar_evento_trade({
                            "event": "TRAILING",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                            "side": side,
                            "old_sl": sl_atual,
                            "new_sl": float(novo_trail),
                            "signal_type": "SMART_PREDATOR"
                        })
                        safe_send_telegram(mensagem_trailing(p, sl_atual, novo_trail))
                        alterou = True

                    if side == "SHORT" and novo_trail < sl_atual:
                        p["sl"] = float(novo_trail)
                        p["last_protection_ts"] = time.time()
                        registrar_evento_trade({
                            "event": "TRAILING",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                            "side": side,
                            "old_sl": sl_atual,
                            "new_sl": float(novo_trail),
                            "signal_type": "SMART_PREDATOR"
                        })
                        safe_send_telegram(mensagem_trailing(p, sl_atual, novo_trail))
                        alterou = True

            # Proteção temporal pós-ajuste
            try:
                last_protection = float(p.get("last_protection_ts", 0))
                if time.time() - last_protection < PROTECTION_SECONDS:
                    posicoes[symbol] = p
                    continue
            except Exception:
                pass

            # Stop / BE / Trail
            sl_atual = float(p.get("sl"))
            stop_hit = (
                (side == "LONG" and preco <= sl_atual) or
                (side == "SHORT" and preco >= sl_atual)
            )

            if stop_hit:
                if bool(p.get("trailing_active", False)):
                    motivo = "TRAIL"
                elif bool(p.get("be_active", False)):
                    motivo = "BE"
                else:
                    motivo = "SL"

                encerrar_posicao(symbol, p, sl_atual, motivo)
                continue

            posicoes[symbol] = p

        except Exception as e:
            print("ERRO GERENCIAR POSIÇÃO:", symbol, e)
            HEALTH["last_error"] = f"Erro gestão {symbol}: {e}"

    if alterou:
        salvar_posicoes(posicoes)

    HEALTH["last_management_run"] = data_hora_sp_str()
    HEALTH["last_positions_count"] = contar_posicoes_ativas()

# ====================================================
# RESUMOS / ESTATÍSTICAS
# ====================================================

def filtrar_trades_periodo(data_prefix):
    trades = carregar_trades()
    return [t for t in trades if str(t.get("date", "")).startswith(data_prefix)]


def montar_resumo_por_periodo(data_prefix, titulo, data_txt):
    trades = filtrar_trades_periodo(data_prefix)

    entradas = [t for t in trades if t.get("event") == "ENTRY"]
    exits = [t for t in trades if t.get("event") in ["SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in trades if t.get("event") == "TP50"]
    trails = [t for t in trades if t.get("event") == "TRAILING"]

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]

    excepcionais = [t for t in entradas if "EXCEPCIONAL" in str(t.get("quality", ""))]
    ideais = [t for t in entradas if "IDEAL" in str(t.get("quality", ""))]
    medios = [t for t in entradas if "MÉDIA" in str(t.get("quality", ""))]

    wins = []
    bes = []
    losses = []
    pnl_total = 0.0
    melhor = None
    pior = None

    for t in exits:
        try:
            pnl = float(t.get("pnl", t.get("pnl_pct", 0)))
        except Exception:
            pnl = 0.0

        pnl_total += pnl

        if pnl > 0.15:
            wins.append(t)
        elif pnl >= -0.15:
            bes.append(t)
        else:
            losses.append(t)

        if melhor is None or pnl > float(melhor.get("_pnl_calc", -999999)):
            t["_pnl_calc"] = pnl
            melhor = t

        if pior is None or pnl < float(pior.get("_pnl_calc", 999999)):
            t["_pnl_calc"] = pnl
            pior = t

    fechados = len(exits)
    win_rate = (len(wins) / fechados * 100) if fechados else 0
    win_rate_sem_be = (len(wins) / (len(wins) + len(losses)) * 100) if (len(wins) + len(losses)) else 0

    mfe_medio = (sum(float(t.get("mfe_max_pct", 0)) for t in exits) / len(exits)) if exits else 0
    devolucao_media = (sum(float(t.get("mfe_gave_back_pct", 0)) for t in exits) / len(exits)) if exits else 0

    melhor_txt = f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('_pnl_calc', 0))}" if melhor else "N/A"
    pior_txt = f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('_pnl_calc', 0))}" if pior else "N/A"

    posicoes = carregar_posicoes()
    ativos = [p for p in posicoes.values() if p.get("status") != "ENCERRADO"]
    modo = "REAL" if SMART_PREDATOR_AUTO_TRADE else "OBSERVAÇÃO"

    return (
        f"{titulo}\n"
        f"{data_txt}\n\n"
        f"Modo:\n{modo}\n\n"
        f"Smart Predator ativo:\n{check_bool(SMART_PREDATOR_ENABLED)}\n\n"
        f"Sinais H1 do período: {len(entradas)}\n"
        f"LONG: {len(longs)}\n"
        f"SHORT: {len(shorts)}\n\n"
        f"EXCEPCIONAL: {len(excepcionais)}\n"
        f"IDEAL: {len(ideais)}\n"
        f"MÉDIO: {len(medios)}\n\n"
        f"Trades encerrados: {fechados}\n"
        f"Wins: {len(wins)}\n"
        f"Breakeven: {len(bes)}\n"
        f"Loss: {len(losses)}\n"
        f"Win rate: {win_rate:.2f}%\n"
        f"Win rate sem BE: {win_rate_sem_be:.2f}%\n\n"
        f"TP50 atingidos: {len(tp50s)}\n"
        f"Trailings atualizados: {len(trails)}\n\n"
        f"PnL realizado:\n{fmt_pct(pnl_total)}\n\n"
        f"MFE médio:\n{fmt_pct(mfe_medio)}\n\n"
        f"Devolução média:\n{fmt_pct(devolucao_media)}\n\n"
        f"Melhor trade:\n{melhor_txt}\n\n"
        f"Pior trade:\n{pior_txt}\n\n"
        f"Trades Smart Predator ainda ativos: {len(ativos)}"
    )


def montar_resumo_diario():
    hoje = data_hoje_sp_str()
    data_br = agora_sp().strftime("%d/%m/%Y")
    return montar_resumo_por_periodo(hoje, "📊 RESUMO SMART PREDATOR", data_br)


def mes_anterior_ref():
    hoje = agora_sp()
    primeiro_mes_atual = hoje.replace(day=1)
    ultimo_mes_anterior = primeiro_mes_atual - timedelta(days=1)
    return ultimo_mes_anterior.strftime("%Y-%m"), ultimo_mes_anterior.strftime("%m/%Y")


def montar_resumo_mensal():
    mes_ref, mes_txt = mes_anterior_ref()
    return montar_resumo_por_periodo(mes_ref, "📊 RESUMO MENSAL SMART PREDATOR", f"Mês: {mes_txt}")


def carregar_daily_summary_sent():
    return redis_get_json(DAILY_SUMMARY_KEY, {})


def salvar_daily_summary_sent(dados):
    redis_set_json(DAILY_SUMMARY_KEY, dados)


def resumo_diario_ja_enviado():
    enviados = carregar_daily_summary_sent()
    hoje = data_hoje_sp_str()
    return enviados.get(hoje) is True


def marcar_resumo_diario_enviado():
    enviados = carregar_daily_summary_sent()
    hoje = data_hoje_sp_str()
    enviados[hoje] = True

    if len(enviados) > 45:
        chaves = sorted(enviados.keys())
        for chave in chaves[:-45]:
            enviados.pop(chave, None)

    salvar_daily_summary_sent(enviados)


def enviar_resumo_diario_se_preciso():
    agora = agora_sp()

    if agora.hour != DAILY_SUMMARY_HOUR:
        return
    if agora.minute < DAILY_SUMMARY_MINUTE:
        return
    if resumo_diario_ja_enviado():
        return

    safe_send_telegram(montar_resumo_diario())
    marcar_resumo_diario_enviado()


def carregar_monthly_summary_sent():
    return redis_get_json(MONTHLY_SUMMARY_KEY, {})


def salvar_monthly_summary_sent(dados):
    redis_set_json(MONTHLY_SUMMARY_KEY, dados)


def enviar_resumo_mensal_se_preciso():
    agora = agora_sp()

    if agora.day != MONTHLY_SUMMARY_DAY:
        return
    if agora.hour != MONTHLY_SUMMARY_HOUR or agora.minute < MONTHLY_SUMMARY_MINUTE:
        return

    enviados = carregar_monthly_summary_sent()
    mes_ref, _ = mes_anterior_ref()

    if enviados.get(mes_ref):
        return

    safe_send_telegram(montar_resumo_mensal())
    enviados[mes_ref] = True

    if len(enviados) > 36:
        itens = sorted(enviados.items())
        enviados = dict(itens[-36:])

    salvar_monthly_summary_sent(enviados)


def montar_stats_gerais():
    trades = carregar_trades()
    entradas = [t for t in trades if t.get("event") == "ENTRY"]
    exits = [t for t in trades if t.get("event") in ["SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in trades if t.get("event") == "TP50"]

    wins = []
    bes = []
    losses = []
    pnl_total = 0.0

    for t in exits:
        pnl = float(t.get("pnl", t.get("pnl_pct", 0)) or 0)
        pnl_total += pnl
        if pnl > 0.15:
            wins.append(t)
        elif pnl >= -0.15:
            bes.append(t)
        else:
            losses.append(t)

    por_score = {"70_74": [], "75_79": [], "80_84": [], "85_plus": []}

    for t in exits:
        score = int(t.get("score", 0) or 0)
        if 70 <= score <= 74:
            por_score["70_74"].append(t)
        elif 75 <= score <= 79:
            por_score["75_79"].append(t)
        elif 80 <= score <= 84:
            por_score["80_84"].append(t)
        elif score >= 85:
            por_score["85_plus"].append(t)

    linhas_score = []
    for faixa, itens in por_score.items():
        if not itens:
            linhas_score.append(f"{faixa}: 0 trades")
            continue
        w = [t for t in itens if float(t.get("pnl", t.get("pnl_pct", 0)) or 0) > 0.15]
        wr = len(w) / len(itens) * 100
        linhas_score.append(f"{faixa}: {len(itens)} trades | WR {wr:.2f}%")

    fechados = len(exits)
    win_rate = (len(wins) / fechados * 100) if fechados else 0
    win_rate_sem_be = (len(wins) / (len(wins) + len(losses)) * 100) if (len(wins) + len(losses)) else 0

    avg_mfe = sum(float(t.get("mfe_max_pct", 0)) for t in exits) / len(exits) if exits else 0
    avg_giveback = sum(float(t.get("mfe_gave_back_pct", 0)) for t in exits) / len(exits) if exits else 0

    return (
        f"📈 ESTATÍSTICAS SMART PREDATOR\n\n"
        f"Smart Predator ativo: {check_bool(SMART_PREDATOR_ENABLED)}\n"
        f"Modo: {'REAL' if SMART_PREDATOR_AUTO_TRADE else 'OBSERVAÇÃO'}\n\n"
        f"Sinais totais: {len(entradas)}\n"
        f"Trades encerrados: {fechados}\n"
        f"Wins: {len(wins)}\n"
        f"Breakeven: {len(bes)}\n"
        f"Loss: {len(losses)}\n"
        f"Win rate: {win_rate:.2f}%\n"
        f"Win rate sem BE: {win_rate_sem_be:.2f}%\n\n"
        f"TP50 atingidos: {len(tp50s)}\n"
        f"PnL realizado total: {fmt_pct(pnl_total)}\n"
        f"MFE médio: {fmt_pct(avg_mfe)}\n"
        f"Devolução média: {fmt_pct(avg_giveback)}\n\n"
        f"Por score:\n" + "\n".join(linhas_score)
    )


def montar_posicoes_texto():
    posicoes = carregar_posicoes()
    ativos = [p for p in posicoes.values() if p.get("status") != "ENCERRADO"]

    if not ativos:
        return "📭 Nenhuma posição Smart Predator ativa."

    linhas = ["📊 POSIÇÕES SMART PREDATOR\n"]

    for p in ativos:
        try:
            preco = obter_preco_atual(p["symbol"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
            atualizar_mfe_posicao(p, preco)

            linhas.append(
                f"{p.get('symbol_clean')} - {p.get('side')}\n"
                f"PnL: {fmt_pct(pnl)}\n"
                f"Entrada: {fmt_br(p.get('entry'))}\n"
                f"Stop Atual: {fmt_br(p.get('sl'))}\n"
                f"TP50: {fmt_br(p.get('tp50'))}\n"
                f"Score: {p.get('score')}/100\n"
                f"Status: {'TP50 ✅' if p.get('tp50_hit') else 'Aberto'}\n"
            )
        except Exception:
            linhas.append(f"{p.get('symbol_clean', '')} | erro ao calcular PnL\n")

    return "\n".join(linhas)


def montar_funnel_stats_json():
    return json.dumps(carregar_funnel_stats(), ensure_ascii=False, indent=2)


def montar_funnel_stats_texto():
    s = carregar_funnel_stats()

    return (
        "🦈 FUNIL SMART PREDATOR\n\n"
        f"Scanner runs: {s.get('scanner_runs', 0)}\n"
        f"Ativos escaneados: {s.get('symbols_scanned', 0)}\n\n"
        f"Liquidity Sweeps:\n"
        f"Bullish: {s.get('bullish_sweeps', 0)}\n"
        f"Bearish: {s.get('bearish_sweeps', 0)}\n\n"
        f"CHOCH:\n"
        f"Bullish: {s.get('bullish_choch', 0)}\n"
        f"Bearish: {s.get('bearish_choch', 0)}\n\n"
        f"Order Blocks:\n"
        f"Bullish: {s.get('bullish_ob', 0)}\n"
        f"Bearish: {s.get('bearish_ob', 0)}\n\n"
        f"Retestes:\n"
        f"Bullish: {s.get('bullish_retests', 0)}\n"
        f"Bearish: {s.get('bearish_retests', 0)}\n\n"
        f"Rejeitados por risco: {s.get('risk_rejected', 0)}\n\n"
        f"Score >= 70: {s.get('score_70_plus', 0)}\n"
        f"Score >= 80: {s.get('score_80_plus', 0)}\n"
        f"Score >= 85: {s.get('score_85_plus', 0)}\n\n"
        f"Sinais detectados: {s.get('signals_detected', 0)}\n"
        f"Sinais enviados: {s.get('signals_sent', 0)}\n"
        f"LONG: {s.get('long_signals', 0)}\n"
        f"SHORT: {s.get('short_signals', 0)}\n\n"
        f"Última atualização: {s.get('last_update')}"
    )

# ====================================================
# WATCHDOG / HEALTH
# ====================================================

def parse_data_hora_sp(valor):
    try:
        if not valor:
            return None
        return datetime.strptime(str(valor), "%d/%m/%Y %H:%M")
    except Exception:
        return None


def minutos_desde_health(campo):
    dt = parse_data_hora_sp(HEALTH.get(campo))
    if not dt:
        return None
    agora_local = agora_sp().replace(tzinfo=None)
    return round((agora_local - dt).total_seconds() / 60, 2)


def calcular_uptime_horas():
    try:
        started_at = HEALTH.get("started_at")
        if not started_at:
            return None
        inicio = datetime.strptime(started_at, "%d/%m/%Y %H:%M")
        agora_local = agora_sp().replace(tzinfo=None)
        return round((agora_local - inicio).total_seconds() / 3600, 2)
    except Exception:
        return None


def montar_watchdog_status():
    minutes_since_scanner = minutos_desde_health("last_scanner_run")
    minutes_since_management = minutos_desde_health("last_management_run")

    scanner_stalled = (
        minutes_since_scanner is not None and
        minutes_since_scanner > WATCHDOG_THRESHOLD_MINUTES
    )
    management_stalled = (
        minutes_since_management is not None and
        minutes_since_management > WATCHDOG_THRESHOLD_MINUTES
    )

    ok = (HEALTH.get("last_error") is None and not scanner_stalled and not management_stalled)

    reasons = []
    if HEALTH.get("last_error") is not None:
        reasons.append(f"last_error: {HEALTH.get('last_error')}")
    if scanner_stalled:
        reasons.append(f"scanner parado há {minutes_since_scanner} min")
    if management_stalled:
        reasons.append(f"gestão parada há {minutes_since_management} min")

    return {
        "ok": ok,
        "bot": BOT_NAME,
        "service_mode": SERVICE_MODE,
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "minutes_since_scanner": minutes_since_scanner,
        "minutes_since_management": minutes_since_management,
        "last_error": HEALTH.get("last_error"),
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_watchdog_alert": HEALTH.get("last_watchdog_alert"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "status": "OK" if ok else "ALERTA",
        "reasons": reasons
    }


def pode_enviar_alerta_watchdog():
    try:
        ultimo = float(HEALTH.get("last_watchdog_alert_ts", 0) or 0)
        return time.time() - ultimo >= WATCHDOG_ALERT_COOLDOWN_SECONDS
    except Exception:
        return True


def enviar_alerta_watchdog(status):
    if not pode_enviar_alerta_watchdog():
        return

    motivos = status.get("reasons") or ["motivo não identificado"]

    msg = (
        f"🚨 WATCHDOG - {BOT_NAME}\n\n"
        f"O robô pode estar travado.\n\n"
        f"Motivo:\n"
        + "\n".join([f"- {m}" for m in motivos])
        + "\n\n"
        f"Último scanner:\n{status.get('last_scanner_run')}\n\n"
        f"Última gestão:\n{status.get('last_management_run')}\n\n"
        f"Último erro:\n{status.get('last_error')}"
    )

    safe_send_telegram(msg)
    HEALTH["last_watchdog_alert"] = data_hora_sp_str()
    HEALTH["last_watchdog_alert_ts"] = time.time()


def watchdog_loop():
    print(f"WATCHDOG INICIADO - {BOT_NAME}")

    while True:
        try:
            HEALTH["watchdog_last_check"] = data_hora_sp_str()
            status = montar_watchdog_status()
            HEALTH["watchdog_last_status"] = status.get("status", "OK")

            if not status.get("ok", True):
                print("WATCHDOG ALERTA:", status)
                enviar_alerta_watchdog(status)

        except Exception as e:
            print("ERRO WATCHDOG:", e)

        time.sleep(WATCHDOG_CHECK_SECONDS)


def montar_health_tecnico():
    positions_open = contar_posicoes_ativas()
    usage_pct = (positions_open / MAX_OPEN_POSITIONS * 100) if MAX_OPEN_POSITIONS else 0
    watchdog = montar_watchdog_status()

    payload = {
        "ok": watchdog.get("ok", HEALTH.get("last_error") is None),
        "bot": BOT_NAME,
        "version": BOT_VERSION,
        "service_mode": SERVICE_MODE,
        "standby": not SMART_PREDATOR_ENABLED,
        "uptime_horas": calcular_uptime_horas(),
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "watchlist_file": WATCHLIST_FILE,
        "watchlist_total": HEALTH.get("watchlist_total"),
        "watchlist_valida": HEALTH.get("watchlist_valid"),
        "watchlist_invalida": len(HEALTH.get("watchlist_invalid", [])),
        "watchlist_invalidos": HEALTH.get("watchlist_invalid", []),
        "last_invalid_watchlist_check": HEALTH.get("last_invalid_watchlist_check"),
        "positions_open": positions_open,
        "positions_limit": MAX_OPEN_POSITIONS,
        "positions_usage_pct": round(usage_pct, 2),
        "can_open_new_positions": positions_open < MAX_OPEN_POSITIONS,
        "last_signals_sent": HEALTH.get("last_signals_sent", 0),
        "telegram_configured": bool(TOKEN and CHAT_ID),
        "smart_predator_enabled": SMART_PREDATOR_ENABLED,
        "smart_predator_auto_trade": SMART_PREDATOR_AUTO_TRADE,
        "timeframe_h1": TIMEFRAME_H1,
        "timeframe_h4": TIMEFRAME_H4,
        "timeframe_m15_choch": TIMEFRAME_M15,
        "swing_lookback": SWING_LOOKBACK,
        "choch_lookback": CHOCH_LOOKBACK,
        "ob_lookback": OB_LOOKBACK,
        "min_predator_score": MIN_PREDATOR_SCORE,
        "min_adx_h4": MIN_ADX_H4,
        "volume_multiplier": VOLUME_MULTIPLIER,
        "max_risk_h1": MAX_RISK_H1,
        "use_max_risk_filter": USE_MAX_RISK_FILTER,
        "tp50_r": TP50_R,
        "be_offset_pct": BE_OFFSET_PCT,
        "trail_atr_mult": TRAIL_ATR_MULT,
        "daily_summary_time": f"{DAILY_SUMMARY_HOUR:02d}:{DAILY_SUMMARY_MINUTE:02d}",
        "daily_summary_sent_today": resumo_diario_ja_enviado(),
        "monthly_summary_day": MONTHLY_SUMMARY_DAY,
        "monthly_summary_time": f"{MONTHLY_SUMMARY_HOUR:02d}:{MONTHLY_SUMMARY_MINUTE:02d}",
        "mfe_enabled": True,
        "funnel_enabled": True,
        "watchdog_status": watchdog.get("status"),
        "minutes_since_scanner": watchdog.get("minutes_since_scanner"),
        "minutes_since_management": watchdog.get("minutes_since_management"),
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_watchdog_alert": HEALTH.get("last_watchdog_alert"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check")
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)

# ====================================================
# STARTUP
# ====================================================

def startup_message_already_sent_today():
    dados = redis_get_json(STARTUP_MESSAGE_KEY, {})
    if not isinstance(dados, dict):
        return False
    return dados.get("date") == data_hoje_sp_str()


def marcar_startup_message_sent():
    redis_set_json(STARTUP_MESSAGE_KEY, {
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str()
    })


def montar_startup_message():
    modo = "REAL" if SMART_PREDATOR_AUTO_TRADE else "OBSERVAÇÃO"
    return (
        f"🦈 Robô {BOT_NAME} iniciado\n\n"
        f"Status:\n"
        f"Stand-by: {check_bool(not SMART_PREDATOR_ENABLED)}\n"
        f"Ativo para sinais: {check_bool(SMART_PREDATOR_ENABLED)}\n"
        f"Modo: {modo}\n\n"
        f"Lógica:\n"
        f"Liquidity Sweep + CHOCH M15 + Order Block + Reteste\n\n"
        f"Filtros ativos:\n"
        f"Timeframe principal: {TIMEFRAME_H1}\n"
        f"CHOCH: {TIMEFRAME_M15}\n"
        f"Contexto: {TIMEFRAME_H4}\n"
        f"Score mínimo: {MIN_PREDATOR_SCORE}/100\n"
        f"Risco máximo: {MAX_RISK_H1}%\n"
        f"Volume mínimo: {VOLUME_MULTIPLIER}x\n"
        f"Limite de posições: {MAX_OPEN_POSITIONS}\n"
        f"Resumo diário: {DAILY_SUMMARY_HOUR:02d}:{DAILY_SUMMARY_MINUTE:02d}\n"
        f"Watchdog: {WATCHDOG_THRESHOLD_MINUTES} min"
    )


def enviar_startup_message_once():
    if startup_message_already_sent_today():
        print("Mensagem inicial Smart Predator já enviada hoje. Pulando envio.")
        return
    safe_send_telegram(montar_startup_message())
    marcar_startup_message_sent()

# ====================================================
# COMANDOS TELEGRAM
# ====================================================

def resetar_estado_operacional():
    salvar_posicoes({})
    salvar_sinais({})
    salvar_trades([])
    salvar_sweep_state({})
    salvar_signal_cooldown({})
    resetar_funnel_stats()
    redis_set_json(DAILY_SUMMARY_KEY, {})
    redis_set_json(MONTHLY_SUMMARY_KEY, {})


def processar_comando(texto):
    cmd = texto.strip().lower()
    if "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ["/start", "/help", "/comandos"]:
        return (
            "📌 Comandos Smart Predator:\n\n"
            "/health - painel técnico\n"
            "/teste - testa conexão Telegram\n"
            "/posicoes - posições abertas\n"
            "/top - melhores posições abertas\n"
            "/resumo - resumo diário\n"
            "/mensal - resumo mensal\n"
            "/stats - estatísticas gerais\n"
            "/funil - funil do setup\n"
            "/watchlist - ativos monitorados\n"
            "/reset - limpa posições, sinais, histórico e funil\n"
            "/comandos - mostra esta lista"
        )

    if cmd == "/health":
        return montar_health_tecnico()

    if cmd == "/teste":
        return "✅ Smart Predator conectado ao Telegram."

    if cmd in ["/posicoes", "/positions"]:
        return montar_posicoes_texto()

    if cmd == "/top":
        return montar_top_posicoes()

    if cmd in ["/resumo", "/daily"]:
        return montar_resumo_diario()

    if cmd == "/mensal":
        return montar_resumo_mensal()

    if cmd == "/stats":
        return montar_stats_gerais()

    if cmd in ["/funil", "/funnel"]:
        return montar_funnel_stats_texto()

    if cmd == "/watchlist":
        wl = carregar_watchlist()
        validos = HEALTH.get("watchlist_valid", 0)
        return (
            f"📋 WATCHLIST SMART PREDATOR\n\n"
            f"Arquivo: {WATCHLIST_FILE}\n"
            f"Total: {len(wl)}\n"
            f"Válidos BingX: {validos}\n\n"
            + "\n".join([nome_limpo(x) for x in wl[:120]])
        )

    if cmd == "/reset":
        resetar_estado_operacional()
        return "✅ Smart Predator resetado."

    return None


def montar_top_posicoes():
    posicoes = carregar_posicoes()
    ranking = []

    for p in posicoes.values():
        if p.get("status") == "ENCERRADO":
            continue

        try:
            preco = obter_preco_atual(p["symbol"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
            ranking.append((pnl, p))
        except Exception:
            pass

    ranking.sort(key=lambda x: x[0], reverse=True)

    if not ranking:
        return "📊 TOP SMART PREDATOR\n\nNenhuma posição aberta."

    linhas = ["📊 TOP SMART PREDATOR\n"]

    for pnl, p in ranking[:10]:
        linhas.append(
            f"{p.get('symbol_clean', nome_limpo(p.get('symbol', '')))} {p.get('side')} | "
            f"{fmt_pct(pnl)} | Score {p.get('score', 0)}/100"
        )

    return "\n".join(linhas)


def listen_commands():
    global ultimo_update_id

    if not TOKEN:
        print("TELEGRAM TOKEN NÃO CONFIGURADO. COMANDOS DESATIVADOS.")
        return

    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
    except Exception as e:
        print("AVISO deleteWebhook Smart Predator:", e)

    print("INTERPRETADOR DE COMANDOS SMART PREDATOR INICIADO")

    while True:
        try:
            params = {"timeout": 20}
            if ultimo_update_id is not None:
                params["offset"] = ultimo_update_id + 1

            resp = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params=params,
                timeout=30
            ).json()

            if not resp.get("ok", True):
                print("ERRO TELEGRAM getUpdates:", resp)
                time.sleep(5)
                continue

            for update in resp.get("result", []):
                ultimo_update_id = update.get("update_id", ultimo_update_id)
                msg = update.get("message") or update.get("edited_message") or {}
                texto = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")

                if not texto or not chat_id:
                    continue

                if CHAT_ID and str(chat_id) != str(CHAT_ID):
                    continue

                cmd = texto.strip().split()[0].lower()
                resposta = processar_comando(cmd)

                if resposta:
                    enviar_texto(chat_id, resposta)

        except Exception as e:
            print("ERRO COMANDOS:", e)
            time.sleep(10)

        time.sleep(COMMAND_SLEEP_SECONDS)

# ====================================================
# SCANNER LOOP PRINCIPAL
# ====================================================

def scanner():
    print(f"SCANNER INICIADO - {BOT_NAME}")
    HEALTH["started_at"] = data_hora_sp_str()
    enviar_startup_message_once()

    while True:
        try:
            watchlist = carregar_watchlist()
            watchlist = validar_watchlist_bingx(watchlist, avisar_telegram=False)
            inc_funnel_stat("scanner_runs")

            HEALTH["last_scanner_run"] = data_hora_sp_str()
            HEALTH["last_signals_sent"] = 0
            HEALTH["last_error"] = None

            sinais_enviados = 0

            # Gestão sempre roda para posições já existentes.
            gerenciar_posicoes()

            if SMART_PREDATOR_ENABLED:
                for symbol in watchlist:
                    try:
                        s = scan_smart_predator_symbol(symbol)

                        if s:
                            ok = registrar_posicao(s)
                            if ok:
                                safe_send_telegram(formatar_sinal_predator(s))
                                inc_funnel_stat("signals_sent")
                                sinais_enviados += 1

                    except Exception as e:
                        print(f"ERRO SCANNER {symbol}:", e)
                        HEALTH["last_error"] = f"Erro scanner {nome_limpo(symbol)}: {e}"

                    time.sleep(0.2)
            else:
                HEALTH["last_warning"] = "Smart Predator em stand-by; scanner não envia sinais."

            HEALTH["last_signals_sent"] = sinais_enviados

            enviar_resumo_diario_se_preciso()
            enviar_resumo_mensal_se_preciso()

            HEALTH["last_success"] = data_hora_sp_str()

        except Exception as e:
            print("ERRO LOOP SCANNER:", e)
            HEALTH["last_error"] = str(e)

        time.sleep(SCANNER_SLEEP_SECONDS)

# ====================================================
# ROTAS FLASK
# ====================================================

@app.route("/")
def home():
    return f"{BOT_NAME} Online"


@app.route("/health")
def health():
    return montar_health_tecnico()


@app.route("/watchdog")
def watchdog():
    return montar_watchdog_status()


@app.route("/resumo")
def resumo():
    return montar_resumo_diario().replace("\n", "<br>")


@app.route("/posicoes")
def posicoes_rota():
    return montar_posicoes_texto().replace("\n", "<br>")


@app.route("/stats")
def stats_rota():
    return montar_stats_gerais().replace("\n", "<br>")


@app.route("/funil")
def funil_rota():
    return montar_funnel_stats_json()


@app.route("/funnel")
def funnel_rota():
    return montar_funnel_stats_json()

# ====================================================
# THREADS MONITORADAS
# ====================================================

def run_thread_guarded(nome, target):
    while True:
        try:
            target()
        except Exception as e:
            HEALTH["last_error"] = f"{nome}: {e}"
            print(f"ERRO THREAD {nome}:", e)
            time.sleep(10)


def iniciar_threads_monitoradas():
    threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog_loop), daemon=True).start()


iniciar_threads_monitoradas()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
