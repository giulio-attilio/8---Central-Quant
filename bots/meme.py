# ==============================================================================
# ROBÔ MEME HUNTER ELITE - CENTRAL QUANT PRO
# Versão: 2026-06-22-MEME-HUNTER-CENTRAL-QUANT-RESILIENTE
#
# Padrão Central Quant:
# - watchlist própria: watchlists/meme.json
# - fallback: watchlist_meme.json / watchlist.json
# - sem execução real de ordens por padrão
# - safe_fetch_ohlcv / safe_fetch_ticker / safe_fetch_tickers / safe_load_markets
# - falha isolada da BingX vira last_warning, não last_error
# - startup guard anti-sinal atrasado
# - startup message com cooldown
# - comandos Telegram: /comandos /health /teste /posicoes /top /resumo /mensal /watchlist
# - health completo para supervisor Central Quant
# - funil de diagnóstico do Hunter Breakout
# ============================================================================== 

from flask import Flask
import os
import json
import time
import threading
import requests
import pandas as pd
import ccxt
from ccxt.base.errors import NetworkError, RateLimitExceeded, ExchangeError
from datetime import datetime, timezone, timedelta
from upstash_redis import Redis

app = Flask(__name__)

TOKEN = (
    os.environ.get("MEME_HUNTER_TOKEN")
    or os.environ.get("MEME_TELEGRAM_BOT_TOKEN")
    or os.environ.get("MEME_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
)
CHAT_ID = (
    os.environ.get("MEME_HUNTER_CHAT_ID")
    or os.environ.get("MEME_TELEGRAM_CHAT_ID")
    or os.environ.get("MEME_CHAT_ID")
    or os.environ.get("TELEGRAM_CHAT_ID")
)
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

ENABLE_REAL_ORDERS = str(os.environ.get("MEME_ENABLE_REAL_ORDERS", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
BINGX_API_KEY = os.environ.get("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.environ.get("BINGX_SECRET_KEY", "")
ALAVANCAGEM_PADRAO = int(os.environ.get("MEME_LEVERAGE", "3"))
VALOR_POR_TRADE_USDT = float(os.environ.get("MEME_TRADE_USDT", "15"))

WATCHLIST_FILE = os.environ.get("MEME_WATCHLIST_FILE", "watchlists/meme.json")
POSITIONS_KEY = "memepro:positions"
SIGNALS_KEY = "memepro:signals"
TRADES_KEY = "memepro:trades"
DAILY_SUMMARY_KEY = "memepro:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "memepro:monthly_summary_sent"
FUNNEL_KEY = "memepro:funnel"
EARLY_HUNTER_COOLDOWN_KEY = "memepro:early_hunter_cooldown"

TIMEFRAME_H4 = "4h"
TIMEFRAME_H1 = "1h"
EMA_FAST = 9
EMA_MID = 21
EMA50 = 50
SUPERTREND_PERIOD = 10
SUPERTREND_FACTOR = 3.0
ATR_LEN = 14
SWING_LEN = 5
ATR_BUFFER_STOP = 0.25
TP50_R = 1.0
TP50_MIN_ATR = 1.0
BE_TRIGGER_R = 1.5
BE_OFFSET_PCT = 0.10
TRAIL_ATR_MULT = 2.0
ENABLE_SPIKE_FILTER = True
SPIKE_RANGE_ATR_MULT = 6.0
SPIKE_BODY_ATR_MULT = 4.0
USE_MAX_RISK_FILTER = True
MAX_RISK_H1 = float(os.environ.get("MEME_MAX_RISK_H1", "2.5"))
MAX_OPEN_POSITIONS = int(os.environ.get("MEME_MAX_OPEN_POSITIONS", "20"))

ENABLE_HUNTER_BREAKOUT = True
HUNTER_SCORE_MIN = int(os.environ.get("MEME_HUNTER_SCORE_MIN", "60"))
HUNTER_BREAKOUT_LOOKBACK = int(os.environ.get("MEME_HUNTER_LOOKBACK", "10"))
HUNTER_VOLUME_MULT_MIN = float(os.environ.get("MEME_HUNTER_VOLUME_MULT_MIN", "1.8"))
HUNTER_RSI_BUY_MIN = float(os.environ.get("MEME_HUNTER_RSI_BUY_MIN", "60"))
HUNTER_RSI_SELL_MAX = float(os.environ.get("MEME_HUNTER_RSI_SELL_MAX", "40"))
HUNTER_MAX_DISTANCE_EMA9_ATR = float(os.environ.get("MEME_HUNTER_MAX_DISTANCE_EMA9_ATR", "2.5"))
HUNTER_MIN_ADX_H4 = float(os.environ.get("MEME_HUNTER_MIN_ADX_H4", "12"))

# Early Hunter: entrada antecipada antes do rompimento confirmado.
ENABLE_EARLY_HUNTER = str(os.environ.get("MEME_ENABLE_EARLY_HUNTER", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
EARLY_HUNTER_SCORE_MIN = int(os.environ.get("MEME_EARLY_HUNTER_SCORE_MIN", "55"))
EARLY_HUNTER_LOOKBACK = int(os.environ.get("MEME_EARLY_HUNTER_LOOKBACK", "10"))
EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR = float(os.environ.get("MEME_EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR", "0.35"))
EARLY_HUNTER_VOLUME_MULT_MIN = float(os.environ.get("MEME_EARLY_HUNTER_VOLUME_MULT_MIN", "1.3"))
EARLY_HUNTER_RSI_BUY_MIN = float(os.environ.get("MEME_EARLY_HUNTER_RSI_BUY_MIN", "55"))
EARLY_HUNTER_RSI_SELL_MAX = float(os.environ.get("MEME_EARLY_HUNTER_RSI_SELL_MAX", "45"))
EARLY_HUNTER_COOLDOWN_SECONDS = int(os.environ.get("MEME_EARLY_HUNTER_COOLDOWN_SECONDS", "3600"))

# Filtro de volume financeiro aproximado no candle H1 fechado.
# Por padrão fica desligado para não bloquear memecoins menores no primeiro teste.
USE_MIN_QUOTE_VOLUME_FILTER = str(os.environ.get("MEME_USE_MIN_QUOTE_VOLUME_FILTER", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
MIN_QUOTE_VOLUME_H1_USDT = float(os.environ.get("MEME_MIN_QUOTE_VOLUME_H1_USDT", "5000000"))

SCAN_SLEEP_SECONDS = int(os.environ.get("MEME_SCAN_SLEEP_SECONDS", "60"))
COMMAND_SLEEP_SECONDS = int(os.environ.get("MEME_COMMAND_SLEEP_SECONDS", "2"))
DAILY_SUMMARY_HOUR = int(os.environ.get("MEME_DAILY_SUMMARY_HOUR", "23"))
DAILY_SUMMARY_MINUTE = int(os.environ.get("MEME_DAILY_SUMMARY_MINUTE", "55"))
MONTHLY_SUMMARY_DAY = 1
MONTHLY_SUMMARY_HOUR = int(os.environ.get("MEME_MONTHLY_SUMMARY_HOUR", "23"))
MONTHLY_SUMMARY_MINUTE = int(os.environ.get("MEME_MONTHLY_SUMMARY_MINUTE", "55"))
STARTUP_SIGNAL_GRACE_SECONDS = int(os.environ.get("MEME_STARTUP_SIGNAL_GRACE_SECONDS", "600"))
SERVICE_STARTED_TS = time.time()
STARTUP_MSG_COOLDOWN_SECONDS = int(os.environ.get("MEME_STARTUP_MSG_COOLDOWN_SECONDS", "3600"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("MEME_WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_CHECK_SECONDS = int(os.environ.get("MEME_WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("MEME_WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

exchange = None
redis = None
erros_inicializacao = []
try:
    cfg = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
    if ENABLE_REAL_ORDERS and BINGX_API_KEY and BINGX_SECRET_KEY:
        cfg["apiKey"] = BINGX_API_KEY
        cfg["secret"] = BINGX_SECRET_KEY
    exchange = ccxt.bingx(cfg)
except Exception as e:
    erros_inicializacao.append(f"Erro CCXT BingX: {e}")
try:
    if not UPSTASH_REDIS_REST_URL or not UPSTASH_REDIS_REST_TOKEN:
        raise ValueError("Variáveis Upstash ausentes")
    redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
except Exception as e:
    erros_inicializacao.append(f"Erro Upstash Redis: {e}")

ultimo_candle_h1 = {}
ultimo_update_id = None
HEALTH = {
    "started_at": None, "last_scanner_run": None, "last_management_run": None,
    "last_success": None, "last_error": None, "last_warning": None,
    "last_watchlist_count": 0, "watchlist_total": 0, "watchlist_valid": 0,
    "watchlist_invalid": [], "last_invalid_watchlist_check": None,
    "last_signals_sent": 0, "last_positions_count": 0,
    "last_watchdog_alert": None, "last_watchdog_alert_ts": 0,
    "watchdog_last_check": None, "watchdog_last_status": "OK",
}
FUNIL_PADRAO = {
    "ativos_analisados": 0, "rompimentos_buy": 0, "rompimentos_sell": 0,
    "volume_ok": 0, "rsi_ok": 0, "bb_ok": 0, "ema_ok": 0, "h4_ok": 0,
    "distancia_ok": 0, "early_hunter_detectados": 0,
    "hunter_detectados": 0, "reprovados_spike": 0,
    "reprovados_volume": 0, "reprovados_rsi": 0, "reprovados_bb": 0,
    "reprovados_ema": 0, "reprovados_h4": 0, "reprovados_distancia": 0,
    "reprovados_risco": 0, "reprovados_score": 0, "reprovados_posicao_ativa": 0,
    "reprovados_volume_financeiro": 0,
    "reprovados_early_cooldown": 0,
    "sinais_enviados": 0, "startup_guard_ignorados": 0,
}

def agora_sp(): return datetime.now(timezone(timedelta(hours=-3)))
def data_hoje_sp_str(): return agora_sp().strftime("%Y-%m-%d")
def data_hora_sp_str(): return agora_sp().strftime("%d/%m/%Y %H:%M")
def nome_limpo(symbol): return symbol.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")
def normalizar_texto(msg):
    if msg is None: return ""
    msg = str(msg)
    try:
        if "Ã" in msg or "â" in msg or "ðŸ" in msg:
            msg = msg.encode("latin1").decode("utf-8")
    except Exception:
        pass
    return msg

def fmt_br(v):
    try: return f"{float(v):,.8f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
    except Exception: return str(v)
def fmt_pct(v):
    try: return f"{float(v):+.2f}%".replace(".", ",")
    except Exception: return str(v)
def fmt_r(v):
    try: return f"{float(v):.2f}R".replace(".", ",")
    except Exception: return str(v)
def fmt_risco(valor):
    try: return f"{float(valor):.2f}".replace(".", ",")
    except Exception: return str(valor)
def check_bool(v): return "✅" if bool(v) else "❌"
def risco_label(risco_pct):
    try: r = float(risco_pct)
    except Exception: return "⚪ N/A"
    if r <= 1.5: return "🟢 IDEAL"
    if r <= 2.5: return "🟡 ATENÇÃO"
    return "🔴 ALTO"
def side_nome(side): return "BUY" if side == "LONG" else "SELL"

def send_telegram_safe(msg):
    msg = normalizar_texto(msg)
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM MEME NÃO CONFIGURADO:")
        print(msg)
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=json.dumps({"chat_id": CHAT_ID, "text": msg}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"}, timeout=20)
    except Exception as e:
        print("ERRO TELEGRAM MEME:", e)
def send_telegram(msg): send_telegram_safe(msg)
def safe_send_telegram(msg): send_telegram_safe(msg)

def redis_get_json(key, padrao):
    if redis is None: return padrao
    try:
        data = redis.get(key)
        if data is None: return padrao
        return json.loads(data) if isinstance(data, str) else data
    except Exception as e:
        print(f"ERRO REDIS GET {key}:", e); return padrao
def redis_set_json(key, value):
    if redis is None: return
    try: redis.set(key, json.dumps(value, ensure_ascii=False))
    except Exception as e: print(f"ERRO REDIS SET {key}:", e)
def redis_get_str(key, padrao=None):
    if redis is None: return padrao
    try:
        data = redis.get(key)
        if data is None: return padrao
        return data if isinstance(data, str) else str(data)
    except Exception as e:
        print(f"ERRO REDIS GET STR {key}:", e); return padrao
def redis_set_str(key, value):
    if redis is None: return
    try: redis.set(key, str(value))
    except Exception as e: print(f"ERRO REDIS SET STR {key}:", e)

def carregar_posicoes(): return redis_get_json(POSITIONS_KEY, {})
def salvar_posicoes(dados): redis_set_json(POSITIONS_KEY, dados)
def carregar_sinais(): return redis_get_json(SIGNALS_KEY, {})
def salvar_sinais(dados): redis_set_json(SIGNALS_KEY, dados)
def carregar_trades(): return redis_get_json(TRADES_KEY, [])
def salvar_trades(dados): redis_set_json(TRADES_KEY, dados)
def registrar_evento_trade(evento):
    trades = carregar_trades(); trades.append(evento)
    salvar_trades(trades[-2000:])
def carregar_funil():
    dados = redis_get_json(FUNNEL_KEY, {})
    return dados if isinstance(dados, dict) else {}
def salvar_funil(dados): redis_set_json(FUNNEL_KEY, dados)
def funil_hoje():
    dados = carregar_funil(); hoje = data_hoje_sp_str(); base = dict(FUNIL_PADRAO)
    atual = dados.get(hoje, {})
    if isinstance(atual, dict): base.update(atual)
    return base
def registrar_funil(campo, qtd=1):
    try:
        dados = carregar_funil(); hoje = data_hoje_sp_str(); atual = dados.get(hoje, {})
        if not isinstance(atual, dict): atual = {}
        base = dict(FUNIL_PADRAO); base.update(atual); base[campo] = int(base.get(campo, 0)) + int(qtd)
        dados[hoje] = base
        if len(dados) > 45:
            chaves = sorted(dados.keys())[-45:]; dados = {k: dados[k] for k in chaves}
        salvar_funil(dados)
    except Exception as e:
        print("ERRO REGISTRAR FUNIL MEME:", e)

def safe_fetch_ohlcv(symbol, timeframe, limit, max_retries=3):
    if exchange is None:
        HEALTH["last_warning"] = "Exchange não inicializada"; return []
    for attempt in range(max_retries):
        try: return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except Exception as e:
            print(f"Aviso OHLCV MEME ({attempt+1}/{max_retries}) {symbol} {timeframe}: {e}"); time.sleep(2 ** attempt)
    HEALTH["last_warning"] = f"Falha OHLCV {symbol} {timeframe} após {max_retries} tentativas"; print(HEALTH["last_warning"]); return []
def safe_fetch_ticker(symbol, max_retries=3):
    if exchange is None:
        HEALTH["last_warning"] = "Exchange não inicializada"; return None
    for attempt in range(max_retries):
        try: return exchange.fetch_ticker(symbol)
        except Exception as e:
            print(f"Aviso Ticker MEME ({attempt+1}/{max_retries}) {symbol}: {e}"); time.sleep(2 ** attempt)
    HEALTH["last_warning"] = f"Falha Ticker {symbol} após {max_retries} tentativas"; print(HEALTH["last_warning"]); return None
def safe_fetch_tickers(symbols, max_retries=3):
    if exchange is None:
        HEALTH["last_warning"] = "Exchange não inicializada"; return {}
    for attempt in range(max_retries):
        try: return exchange.fetch_tickers(symbols)
        except Exception as e:
            print(f"Aviso Tickers MEME ({attempt+1}/{max_retries}): {e}"); time.sleep(2 ** attempt)
    HEALTH["last_warning"] = "Falha fetch_tickers após tentativas"; print(HEALTH["last_warning"]); return {}
def safe_load_markets(max_retries=3):
    if exchange is None:
        HEALTH["last_warning"] = "Exchange não inicializada"; return None
    for attempt in range(max_retries):
        try: return exchange.load_markets()
        except Exception as e:
            print(f"Aviso load_markets MEME ({attempt+1}/{max_retries}): {e}"); time.sleep(2 ** attempt)
    HEALTH["last_warning"] = "Falha ao carregar markets da exchange após tentativas"; print(HEALTH["last_warning"]); return None

def carregar_watchlist():
    candidatos = [WATCHLIST_FILE]
    for item in ["watchlists/meme.json", "watchlist_meme.json", "watchlist.json"]:
        if item not in candidatos: candidatos.append(item)
    for arquivo in candidatos:
        try:
            with open(arquivo, "r") as f:
                dados = json.load(f)
                if isinstance(dados, list): return dados
        except Exception: pass
    return []
def validar_watchlist_bingx(watchlist, avisar_telegram=False):
    markets = safe_load_markets()
    if not markets:
        HEALTH["watchlist_total"] = len(watchlist); HEALTH["watchlist_valid"] = len(watchlist); HEALTH["watchlist_invalid"] = []; HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str(); return watchlist
    validos = [s for s in watchlist if s in markets]
    invalidos = [s for s in watchlist if s not in markets]
    HEALTH["watchlist_total"] = len(watchlist); HEALTH["watchlist_valid"] = len(validos); HEALTH["watchlist_invalid"] = invalidos; HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
    if invalidos and avisar_telegram:
        send_telegram_safe("⚠️ Ativos inválidos na watchlist BingX:\n\n" + "\n".join(invalidos) + "\n\nEles serão ignorados pelo Meme Hunter.")
    return validos

def calcular_atr(df, period=14):
    high = df["high"].astype(float); low = df["low"].astype(float); close = df["close"].astype(float); prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()
def calcular_rsi(series, period=14):
    series = series.astype(float); delta = series.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean(); avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10); return 100 - (100 / (1 + rs))
def calcular_supertrend_df(df, period=10, multiplier=3.0):
    high = df["high"].astype(float); low = df["low"].astype(float); close = df["close"].astype(float); prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean(); hl2 = (high + low) / 2
    upperband = hl2 + multiplier * atr; lowerband = hl2 - multiplier * atr
    final_upper = upperband.copy(); final_lower = lowerband.copy(); direction = pd.Series(index=df.index, dtype="int64"); supertrend = pd.Series(index=df.index, dtype="float64")
    direction.iloc[0] = 1; supertrend.iloc[0] = lowerband.iloc[0]
    for i in range(1, len(df)):
        final_upper.iloc[i] = upperband.iloc[i] if upperband.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1] else final_upper.iloc[i - 1]
        final_lower.iloc[i] = lowerband.iloc[i] if lowerband.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1] else final_lower.iloc[i - 1]
        direction.iloc[i] = (1 if close.iloc[i] > final_upper.iloc[i] else -1) if direction.iloc[i - 1] == -1 else (-1 if close.iloc[i] < final_lower.iloc[i] else 1)
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    return supertrend, direction
def calcular_adx(df, period=14):
    high = df["high"].astype(float); low = df["low"].astype(float); close = df["close"].astype(float)
    up_move = high.diff(); down_move = -low.diff()
    plus_dm = pd.Series([u if u > d and u > 0 else 0 for u, d in zip(up_move, down_move)], index=df.index)
    minus_dm = pd.Series([d if d > u and d > 0 else 0 for u, d in zip(up_move, down_move)], index=df.index)
    prev_close = close.shift(1); tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean(); plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr; minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di); adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di
def marcar_spikes(df):
    df = df.copy()
    if not ENABLE_SPIKE_FILTER: df["spike_suspeito"] = False; return df
    if "atr14" not in df.columns: df["atr14"] = calcular_atr(df, ATR_LEN)
    candle_range = (df["high"].astype(float) - df["low"].astype(float)).abs(); candle_body = (df["close"].astype(float) - df["open"].astype(float)).abs(); atr = df["atr14"].astype(float)
    df["spike_suspeito"] = ((candle_range > atr * SPIKE_RANGE_ATR_MULT) | (candle_body > atr * SPIKE_BODY_ATR_MULT)).fillna(False); return df
def preparar_df(df):
    df = df.copy(); df["ema9"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean(); df["ema21"] = df["close"].ewm(span=EMA_MID, adjust=False).mean(); df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean(); df["atr14"] = calcular_atr(df, ATR_LEN)
    _, st_dir = calcular_supertrend_df(df, SUPERTREND_PERIOD, SUPERTREND_FACTOR); df["supertrend_dir"] = st_dir
    df["vol_avg20"] = df["volume"].rolling(20).mean(); df["volume_ratio"] = df["volume"] / df["vol_avg20"]; df["rsi14"] = calcular_rsi(df["close"], 14)
    bb_basis = df["close"].rolling(20).mean(); bb_dev = df["close"].rolling(20).std(); bb_upper = bb_basis + 2 * bb_dev; bb_lower = bb_basis - 2 * bb_dev; bb_width = (bb_upper - bb_lower) / bb_basis
    df["bb_width"] = bb_width; df["bb_width_avg"] = bb_width.rolling(100).mean(); df["bb_ok"] = bb_width > df["bb_width_avg"]
    adx, plus_di, minus_di = calcular_adx(df, 14); df["adx"] = adx; df["plus_di"] = plus_di; df["minus_di"] = minus_di
    return marcar_spikes(df)
def estado_tendencia(candle):
    try:
        if int(candle["supertrend_dir"]) == 1 and float(candle["ema9"]) > float(candle["ema21"]): return 1
        if int(candle["supertrend_dir"]) == -1 and float(candle["ema9"]) < float(candle["ema21"]): return -1
    except Exception: pass
    return 0
def calcular_stop_tp(signal, entry, df):
    candle = df.iloc[-2]; atr = float(candle["atr14"]); ultimos = df.iloc[-(SWING_LEN + 1):-1]
    if signal == "LONG":
        sl = float(ultimos["low"].min()) - atr * ATR_BUFFER_STOP; risk_abs = abs(entry - sl); tp50 = entry + max(risk_abs * TP50_R, atr * TP50_MIN_ATR)
    else:
        sl = float(ultimos["high"].max()) + atr * ATR_BUFFER_STOP; risk_abs = abs(sl - entry); tp50 = entry - max(risk_abs * TP50_R, atr * TP50_MIN_ATR)
    return float(sl), float(tp50), float(risk_abs)

def calcular_hunter_score(s):
    score = 0; volume_ratio = float(s.get("volume_ratio", 0))
    score += 35 if volume_ratio >= 4 else 30 if volume_ratio >= 3 else 25 if volume_ratio >= HUNTER_VOLUME_MULT_MIN else 0
    if s.get("breakout_ok"): score += 25
    if s.get("bb_ok"): score += 15
    rsi = float(s.get("rsi", 50)); side = s.get("side")
    if side == "LONG": score += 15 if rsi >= 70 else 10 if rsi >= HUNTER_RSI_BUY_MIN else 0
    else: score += 15 if rsi <= 30 else 10 if rsi <= HUNTER_RSI_SELL_MAX else 0
    adx_h4 = float(s.get("adx_h4", 0)); score += 10 if adx_h4 >= 25 else 5 if adx_h4 >= HUNTER_MIN_ADX_H4 else 0
    dist = float(s.get("dist_ema9_atr", 99)); score += 10 if dist <= 1.5 else 5 if dist <= HUNTER_MAX_DISTANCE_EMA9_ATR else 0
    return min(int(score), 100)

def existe_posicao_ativa(symbol):
    posicoes = carregar_posicoes(); return symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO"
def contar_posicoes_ativas():
    posicoes = carregar_posicoes(); return len([p for p in posicoes.values() if p.get("status") != "ENCERRADO"])
def limite_posicoes_atingido(): return contar_posicoes_ativas() >= MAX_OPEN_POSITIONS
def pnl_pct(side, entry, price): return ((price - entry) / entry) * 100 if side == "LONG" else ((entry - price) / entry) * 100
def pnl_r(side, entry, sl_inicial, price):
    risk = abs(float(entry) - float(sl_inicial))
    if risk <= 0: return 0.0
    return (float(price) - float(entry)) / risk if side == "LONG" else (float(entry) - float(price)) / risk

def detectar_hunter_breakout(symbol):
    if not ENABLE_HUNTER_BREAKOUT: return None
    if existe_posicao_ativa(symbol): registrar_funil("reprovados_posicao_ativa"); return None
    ohlcv_h1 = safe_fetch_ohlcv(symbol, TIMEFRAME_H1, 300); ohlcv_h4 = safe_fetch_ohlcv(symbol, TIMEFRAME_H4, 300)
    if not ohlcv_h1 or not ohlcv_h4: return None
    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"])); df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    registrar_funil("ativos_analisados")
    candle = df_h1.iloc[-2]; candle_h4 = df_h4.iloc[-2]; timestamp = int(candle["time"])
    if bool(candle.get("spike_suspeito", False)): registrar_funil("reprovados_spike"); return None
    lookback = int(HUNTER_BREAKOUT_LOOKBACK)
    if len(df_h1) < lookback + 5: return None
    anteriores = df_h1.iloc[-(lookback + 2):-2]; max_look = float(anteriores["high"].max()); min_look = float(anteriores["low"].min())
    close = float(candle["close"]); ema9 = float(candle["ema9"]); ema21 = float(candle["ema21"]); ema50 = float(candle["ema50"]); atr = float(candle["atr14"])
    volume_ratio = float(candle.get("volume_ratio", 0) or 0); rsi = float(candle.get("rsi14", 50) or 50); bb_ok = bool(candle.get("bb_ok", False)); adx_h4 = float(candle_h4.get("adx", 0) or 0); h4_state = estado_tendencia(candle_h4); dist_ema9_atr = abs(close - ema9) / atr if atr > 0 else 99
    if close > max_look: registrar_funil("rompimentos_buy")
    if close < min_look: registrar_funil("rompimentos_sell")
    if volume_ratio < HUNTER_VOLUME_MULT_MIN: registrar_funil("reprovados_volume"); return None
    registrar_funil("volume_ok")
    if adx_h4 < HUNTER_MIN_ADX_H4: registrar_funil("reprovados_h4"); return None
    registrar_funil("h4_ok")
    if dist_ema9_atr > HUNTER_MAX_DISTANCE_EMA9_ATR: registrar_funil("reprovados_distancia"); return None
    registrar_funil("distancia_ok")
    signal = None; breakout_ok = False
    if ema9 > ema21 >= ema50:
        registrar_funil("ema_ok")
        if close > max_look and rsi >= HUNTER_RSI_BUY_MIN and bb_ok: signal = "LONG"; breakout_ok = True
    elif ema9 < ema21 <= ema50:
        registrar_funil("ema_ok")
        if close < min_look and rsi <= HUNTER_RSI_SELL_MAX and bb_ok: signal = "SHORT"; breakout_ok = True
    else:
        registrar_funil("reprovados_ema"); return None
    if not signal:
        registrar_funil("reprovados_bb" if not bb_ok else "reprovados_rsi"); return None
    registrar_funil("bb_ok"); registrar_funil("rsi_ok")
    entry = close; sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1); risk_pct = risk_abs / entry * 100 if entry else 99
    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1: registrar_funil("reprovados_risco"); return None
    sinal = {"type":"HUNTER_BREAKOUT", "signal_type":"HUNTER_BREAKOUT", "symbol":symbol, "symbol_clean":nome_limpo(symbol), "signal":signal, "side":signal, "timestamp":timestamp, "entry":entry, "sl":sl, "initial_sl":sl, "tp50":tp50, "risk_abs":risk_abs, "risk_pct":risk_pct, "h4_state":h4_state, "adx_h4":adx_h4, "adx_h1":float(candle.get("adx",0) or 0), "volume_ratio":volume_ratio, "rsi":rsi, "bb_ok":bb_ok, "breakout_ok":breakout_ok, "max_look":max_look, "min_look":min_look, "dist_ema9_atr":dist_ema9_atr, "created_at":time.time()}
    score = calcular_hunter_score(sinal); sinal["hunter_score"] = score; sinal["score"] = score
    if score < HUNTER_SCORE_MIN: registrar_funil("reprovados_score"); return None
    registrar_funil("hunter_detectados"); return sinal

def executar_ordem_real_bingx(symbol, side, preco_referencia):
    if not ENABLE_REAL_ORDERS:
        print(f"[SINAL ONLY] Ordem real desativada: {side} {symbol} em {preco_referencia}"); return True
    if exchange is None or not BINGX_API_KEY or not BINGX_SECRET_KEY: return True
    try:
        try: exchange.set_leverage(ALAVANCAGEM_PADRAO, symbol)
        except Exception: pass
        quantidade = (VALOR_POR_TRADE_USDT * ALAVANCAGEM_PADRAO) / preco_referencia
        markets = safe_load_markets() or {}
        if symbol in markets: quantidade = exchange.amount_to_precision(symbol, quantidade)
        exchange.create_market_order(symbol, "buy" if side == "LONG" else "sell", quantidade); return True
    except Exception as e:
        HEALTH["last_error"] = f"Erro ordem real BingX {symbol}: {e}"; send_telegram_safe(f"❌ Erro ao abrir ordem real em {symbol}: {e}"); return False
def fechar_ordem_real_bingx(symbol, side_posicao): return True if not ENABLE_REAL_ORDERS else True

def registrar_posicao(s):
    if limite_posicoes_atingido() or existe_posicao_ativa(s["symbol"]): return False
    if not executar_ordem_real_bingx(s["symbol"], s["side"], float(s["entry"])): return False
    posicoes = carregar_posicoes(); p = {"symbol":s["symbol"], "symbol_clean":s["symbol_clean"], "side":s["side"], "signal_type":s["signal_type"], "entry":float(s["entry"]), "sl":float(s["sl"]), "initial_sl":float(s["initial_sl"]), "tp50":float(s["tp50"]), "risk_abs":float(s["risk_abs"]), "risk_pct":float(s["risk_pct"]), "hunter_score":int(s.get("hunter_score",0)), "score":int(s.get("score",0)), "volume_ratio":float(s.get("volume_ratio",0)), "rsi":float(s.get("rsi",0)), "status":"ACTIVE", "tp50_hit":False, "breakeven":False, "trailing_active":False, "mfe_max_pct":0.0, "mae_max_pct":0.0, "mfe_max_r":0.0, "mae_max_r":0.0, "mfe_gave_back_pct":0.0, "mfe_gave_back_r":0.0, "created_at":time.time(), "active_since":time.time(), "date":data_hoje_sp_str()}
    posicoes[s["symbol"]] = p; salvar_posicoes(posicoes)
    registrar_evento_trade({"event":"ENTRY", "date":data_hoje_sp_str(), "datetime":data_hora_sp_str(), "symbol":s["symbol"], "symbol_clean":s["symbol_clean"], "side":s["side"], "signal_type":s["signal_type"], "entry":float(s["entry"]), "sl":float(s["sl"]), "tp50":float(s["tp50"]), "risk_pct":float(s["risk_pct"]), "hunter_score":int(s.get("hunter_score",0)), "score":int(s.get("score",0)), "volume_ratio":float(s.get("volume_ratio",0))})
    return True

def atualizar_mfe_mae(p, preco_atual):
    pnl_atual = pnl_pct(p["side"], float(p["entry"]), float(preco_atual)); r_atual = pnl_r(p["side"], float(p["entry"]), float(p.get("initial_sl", p.get("sl"))), float(preco_atual))
    if pnl_atual > float(p.get("mfe_max_pct",0)): p["mfe_max_pct"] = pnl_atual; p["mfe_max_r"] = r_atual
    if pnl_atual < float(p.get("mae_max_pct",0)): p["mae_max_pct"] = pnl_atual; p["mae_max_r"] = r_atual
    p["mfe_gave_back_pct"] = max(0.0, float(p.get("mfe_max_pct",0)) - pnl_atual); p["mfe_gave_back_r"] = max(0.0, float(p.get("mfe_max_r",0)) - r_atual); return p
def calcular_chandelier(symbol, side):
    ohlcv = safe_fetch_ohlcv(symbol, TIMEFRAME_H1, 120)
    if not ohlcv: return None
    df = preparar_df(pd.DataFrame(ohlcv, columns=["time","open","high","low","close","volume"])); candle = df.iloc[-2]; atr = float(candle["atr14"]); janela = df.iloc[-23:-1]
    if "spike_suspeito" in janela.columns: janela = janela[~janela["spike_suspeito"]]
    if janela.empty: janela = df.iloc[-23:-1]
    return float(janela["high"].max()) - atr * TRAIL_ATR_MULT if side == "LONG" else float(janela["low"].min()) + atr * TRAIL_ATR_MULT
def classificar_resultado(pnl):
    try: pnl = float(pnl)
    except Exception: return "N/A"
    if pnl > 0.15: return "WIN"
    if pnl >= -0.15: return "BREAKEVEN"
    return "LOSS"
def fechar_posicao(symbol, p, price, reason):
    pnl = pnl_pct(p["side"], float(p["entry"]), float(price)); p = atualizar_mfe_mae(p, price); p["status"] = "ENCERRADO"; p["closed_at"] = time.time(); p["closed_price"] = float(price); p["pnl"] = pnl; p["result_type"] = classificar_resultado(pnl)
    posicoes = carregar_posicoes(); posicoes[symbol] = p; salvar_posicoes(posicoes)
    registrar_evento_trade({"event":"CLOSE", "date":data_hoje_sp_str(), "datetime":data_hora_sp_str(), "symbol":symbol, "symbol_clean":p.get("symbol_clean", nome_limpo(symbol)), "side":p.get("side"), "signal_type":p.get("signal_type"), "reason":reason, "entry":float(p.get("entry")), "exit":float(price), "pnl":pnl, "result_type":p["result_type"], "tp50_hit":bool(p.get("tp50_hit")), "mfe_max_pct":float(p.get("mfe_max_pct",0)), "mae_max_pct":float(p.get("mae_max_pct",0)), "mfe_gave_back_pct":float(p.get("mfe_gave_back_pct",0)), "mfe_max_r":float(p.get("mfe_max_r",0)), "mae_max_r":float(p.get("mae_max_r",0)), "mfe_gave_back_r":float(p.get("mfe_gave_back_r",0)), "hunter_score":int(p.get("hunter_score",0)), "score":int(p.get("score",0))})
    send_telegram_safe(f"🟣 MEME ENCERRADO - {p.get('symbol_clean', nome_limpo(symbol))}\n\nSetup:\nHunter Breakout\n\nLado:\n{side_nome(p['side'])}\n\nMotivo:\n{reason}\n\nEntrada:\n{fmt_br(p['entry'])}\n\nSaída:\n{fmt_br(price)}\n\nResultado:\n{p['result_type']}\n\nPnL:\n{fmt_pct(pnl)}")
def gerenciar_posicoes(tickers_cache=None):
    HEALTH["last_management_run"] = data_hora_sp_str(); posicoes = carregar_posicoes(); alterou = False
    for symbol, p in list(posicoes.items()):
        if p.get("status") == "ENCERRADO": continue
        try:
            ticker = tickers_cache.get(symbol) if isinstance(tickers_cache, dict) else None
            if not ticker: ticker = safe_fetch_ticker(symbol)
            if not ticker: continue
            price = float(ticker["last"]); p = atualizar_mfe_mae(p, price); side = p["side"]; entry = float(p["entry"]); sl = float(p["sl"]); tp50 = float(p["tp50"]); r_atual = pnl_r(side, entry, float(p.get("initial_sl", sl)), price)
            if (side == "LONG" and price <= sl) or (side == "SHORT" and price >= sl): fechar_posicao(symbol, p, price, "SL/TRAIL"); continue
            if not p.get("tp50_hit") and ((side == "LONG" and price >= tp50) or (side == "SHORT" and price <= tp50)):
                p["tp50_hit"] = True; p["tp50_hit_at"] = time.time(); p["status"] = "TP50 HIT"; registrar_evento_trade({"event":"TP50", "date":data_hoje_sp_str(), "datetime":data_hora_sp_str(), "symbol":symbol, "symbol_clean":p.get("symbol_clean", nome_limpo(symbol)), "side":side, "signal_type":p.get("signal_type"), "price":price}); send_telegram_safe(f"🎯 TP50 MEME - {p['symbol_clean']}\n\nTP50 atingido ✅\n\nPreço:\n{fmt_br(price)}\n\nResultado no TP50:\n{fmt_pct(pnl_pct(side, entry, price))}"); alterou = True
            if not p.get("breakeven") and r_atual >= BE_TRIGGER_R:
                new_sl = entry * (1 + BE_OFFSET_PCT / 100) if side == "LONG" else entry * (1 - BE_OFFSET_PCT / 100)
                p["sl"] = max(sl, new_sl) if side == "LONG" else min(sl, new_sl); p["breakeven"] = True; p["status"] = "BREAKEVEN"; registrar_evento_trade({"event":"BREAKEVEN", "date":data_hoje_sp_str(), "datetime":data_hora_sp_str(), "symbol":symbol, "symbol_clean":p.get("symbol_clean", nome_limpo(symbol)), "side":side, "signal_type":p.get("signal_type"), "new_sl":p["sl"]}); send_telegram_safe(f"🟢 BREAKEVEN MEME - {p['symbol_clean']}\n\nNovo Stop:\n{fmt_br(p['sl'])}"); alterou = True
            if p.get("tp50_hit") and p.get("breakeven"):
                new_trail = calcular_chandelier(symbol, side)
                if new_trail is not None and ((side == "LONG" and new_trail > float(p["sl"])) or (side == "SHORT" and new_trail < float(p["sl"]))):
                    p["sl"] = float(new_trail); p["status"] = "TRAILING STOP"; p["trailing_active"] = True; registrar_evento_trade({"event":"TRAILING", "date":data_hoje_sp_str(), "datetime":data_hora_sp_str(), "symbol":symbol, "symbol_clean":p.get("symbol_clean", nome_limpo(symbol)), "side":side, "signal_type":p.get("signal_type"), "new_sl":p["sl"]}); send_telegram_safe(f"🟣 TRAILING MEME - {p['symbol_clean']}\n\nStop Atual:\n{fmt_br(p['sl'])}"); alterou = True
            posicoes[symbol] = p
        except Exception as e: print(f"ERRO GESTÃO MEME {symbol}:", e)
    if alterou: salvar_posicoes(posicoes)

def enviar_sinal_hunter(s):
    emoji = "🐸🟢" if s["side"] == "LONG" else "🐸🔴"; nome = "MEME HUNTER BUY" if s["side"] == "LONG" else "MEME HUNTER SELL"; rompimento_txt = "máxima" if s["side"] == "LONG" else "mínima"
    send_telegram_safe(f"{emoji} {nome} - {s['symbol_clean']}\n\nEstratégia:\nHunter Breakout ✅\n\nMotivo:\nRompimento da {rompimento_txt} de {HUNTER_BREAKOUT_LOOKBACK} candles ✅\nVolume explosivo ✅\nMomentum forte ✅\nBollinger expandindo ✅\n\nEntrada:\n{fmt_br(s['entry'])}\n\nSL:\n{fmt_br(s['sl'])}\n\nTP50:\n{fmt_br(s['tp50'])}\n\n{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%\n\nScore Hunter:\n{s.get('hunter_score', 0)}/100\n\nInformativos:\nVolume: {float(s.get('volume_ratio', 0)):.2f}x média\nRSI H1: {fmt_br(s.get('rsi', 0))}\nADX H4: {fmt_br(s.get('adx_h4', 0))}\nDistância EMA9/ATR: {fmt_br(s.get('dist_ema9_atr', 0))}")

def obter_posicoes_ativas_ordenadas():
    ativos = []
    for symbol, p in carregar_posicoes().items():
        if p.get("status") == "ENCERRADO": continue
        p = dict(p); ticker = safe_fetch_ticker(symbol)
        if ticker:
            price = float(ticker["last"]); p["preco_atual"] = price; p["pnl_atual"] = pnl_pct(p["side"], float(p["entry"]), price); p["r_atual"] = pnl_r(p["side"], float(p["entry"]), float(p.get("initial_sl", p.get("sl"))), price)
        else: p["pnl_atual"] = 0; p["r_atual"] = 0
        ativos.append(p)
    ativos.sort(key=lambda x: x.get("pnl_atual", 0), reverse=True); return ativos
def montar_posicoes():
    ativos = obter_posicoes_ativas_ordenadas(); data = data_hora_sp_str()
    if not ativos: return f"📊 POSIÇÕES MEME HUNTER\n{data}\n\nNenhum trade ativo."
    linhas = ["📊 POSIÇÕES MEME HUNTER", data]
    for p in ativos:
        linhas.append(f"\n{p['symbol_clean']} - {side_nome(p['side'])}\n\nSetup:\nHunter Breakout\n\nPnL:\n{fmt_pct(p.get('pnl_atual', 0))} | {fmt_r(p.get('r_atual', 0))}\n\nEntrada:\n{fmt_br(p['entry'])}\n\nStop Atual:\n{fmt_br(p['sl'])}\n\nTP50:\n{fmt_br(p['tp50'])}\n\nScore Hunter:\n{p.get('hunter_score', 0)}/100\n\nStatus:\nBreakeven {check_bool(p.get('breakeven'))}\nTP50 {check_bool(p.get('tp50_hit'))}\nTrailing {check_bool(p.get('trailing_active'))}\n───────────────")
    return "\n".join(linhas)
def filtrar_trades_periodo(periodo="dia"):
    trades = carregar_trades(); hoje = data_hoje_sp_str(); mes = agora_sp().strftime("%Y-%m")
    if periodo == "dia": return [t for t in trades if t.get("date") == hoje]
    if periodo == "mes": return [t for t in trades if str(t.get("date", "")).startswith(mes)]
    return trades
def calcular_metricas_resumo(periodo="dia"):
    trades = filtrar_trades_periodo(periodo); entradas = [t for t in trades if t.get("event") == "ENTRY"]; fechados = [t for t in trades if t.get("event") == "CLOSE"]; tp50s = [t for t in trades if t.get("event") == "TP50"]; trailings = [t for t in trades if t.get("event") == "TRAILING"]
    wins = [t for t in fechados if t.get("result_type") == "WIN"]; losses = [t for t in fechados if t.get("result_type") == "LOSS"]; bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados); score_medio = sum(int(t.get("hunter_score", t.get("score", 0))) for t in entradas) / len(entradas) if entradas else 0; win_rate = len(wins) / len(fechados) * 100 if fechados else 0
    return {"entradas":entradas,"fechados":fechados,"tp50s":tp50s,"trailings":trailings,"wins":wins,"losses":losses,"bes":bes,"pnl_total":pnl_total,"score_medio":score_medio,"win_rate":win_rate}
def montar_resumo(periodo="dia"):
    data_txt = agora_sp().strftime("%d/%m/%Y") if periodo == "dia" else agora_sp().strftime("%m/%Y") if periodo == "mes" else "Histórico"; m = calcular_metricas_resumo(periodo); entradas = m["entradas"]; fechados = m["fechados"]; ativos = obter_posicoes_ativas_ordenadas(); funil = funil_hoje() if periodo == "dia" else None
    longs = [t for t in entradas if t.get("side") == "LONG"]; shorts = [t for t in entradas if t.get("side") == "SHORT"]
    linhas = ["📈 RESUMO MEME HUNTER", data_txt, "", f"Sinais H1 do período: {len(entradas)}", f"LONG: {len(longs)}", f"SHORT: {len(shorts)}", f"HUNTER BREAKOUT: {len(entradas)}", ""]
    if funil:
        linhas += ["🐸 FUNIL HUNTER", f"Ativos analisados: {funil.get('ativos_analisados',0)}", f"Rompimentos BUY: {funil.get('rompimentos_buy',0)}", f"Rompimentos SELL: {funil.get('rompimentos_sell',0)}", f"Volume OK: {funil.get('volume_ok',0)}", f"RSI OK: {funil.get('rsi_ok',0)}", f"Bollinger OK: {funil.get('bb_ok',0)}", f"Hunter detectados: {funil.get('hunter_detectados',0)}", f"Reprovados volume: {funil.get('reprovados_volume',0)}", f"Reprovados risco: {funil.get('reprovados_risco',0)}", f"Reprovados score: {funil.get('reprovados_score',0)}", f"Sinais enviados: {funil.get('sinais_enviados',0)}", ""]
    linhas += [f"Trades encerrados: {len(fechados)}", f"Wins: {len(m['wins'])}", f"Breakeven: {len(m['bes'])}", f"Loss: {len(m['losses'])}", f"Win rate: {m['win_rate']:.2f}%".replace(".", ","), "", f"TP50 atingidos: {len(m['tp50s'])}", f"Trailings atualizados: {len(m['trailings'])}", "", "PnL realizado:", fmt_pct(m["pnl_total"]), "", "Score médio:", f"{m['score_medio']:.1f}/100".replace(".", ","), "", f"Trades ainda ativos: {len(ativos)}"]
    if ativos: linhas.extend([f"{p['symbol_clean']} {side_nome(p['side'])} | {fmt_pct(p.get('pnl_atual', 0))}" for p in ativos[:20]])
    return "\n".join(linhas)
def resumo_diario_ja_enviado(): return redis_get_str(DAILY_SUMMARY_KEY) == data_hoje_sp_str()
def marcar_resumo_diario_enviado(): redis_set_str(DAILY_SUMMARY_KEY, data_hoje_sp_str())
def enviar_resumo_diario_se_preciso():
    agora = agora_sp()
    if agora.hour < DAILY_SUMMARY_HOUR or (agora.hour == DAILY_SUMMARY_HOUR and agora.minute < DAILY_SUMMARY_MINUTE): return
    if resumo_diario_ja_enviado(): return
    send_telegram_safe(montar_resumo("dia")); marcar_resumo_diario_enviado()
def enviar_resumo_mensal_se_preciso():
    agora = agora_sp()
    if agora.day != MONTHLY_SUMMARY_DAY or agora.hour < MONTHLY_SUMMARY_HOUR or (agora.hour == MONTHLY_SUMMARY_HOUR and agora.minute < MONTHLY_SUMMARY_MINUTE): return
    mes = agora.strftime("%Y-%m")
    if redis_get_str(MONTHLY_SUMMARY_KEY) == mes: return
    send_telegram_safe(montar_resumo("mes")); redis_set_str(MONTHLY_SUMMARY_KEY, mes)
def calcular_uptime_horas():
    try:
        if not HEALTH.get("started_at"): return None
        inicio = datetime.strptime(HEALTH["started_at"], "%d/%m/%Y %H:%M"); return round((agora_sp().replace(tzinfo=None) - inicio).total_seconds()/3600, 2)
    except Exception: return None
def startup_signal_guard_active(): return time.time() - float(SERVICE_STARTED_TS) < STARTUP_SIGNAL_GRACE_SECONDS
def startup_guard_restante_segundos(): return max(0, int(STARTUP_SIGNAL_GRACE_SECONDS - (time.time() - float(SERVICE_STARTED_TS))))
def montar_health_tecnico():
    HEALTH["last_positions_count"] = contar_posicoes_ativas(); positions_open = HEALTH.get("last_positions_count", 0); usage_pct = positions_open / MAX_OPEN_POSITIONS * 100 if MAX_OPEN_POSITIONS else 0; hoje = calcular_metricas_resumo("dia"); mes = calcular_metricas_resumo("mes")
    return json.dumps({"ok": HEALTH.get("last_error") is None, "bot":"Meme Hunter", "uptime_horas":calcular_uptime_horas(), "started_at":HEALTH.get("started_at"), "last_scanner_run":HEALTH.get("last_scanner_run"), "last_management_run":HEALTH.get("last_management_run"), "last_success":HEALTH.get("last_success"), "last_error":HEALTH.get("last_error"), "last_warning":HEALTH.get("last_warning"), "watchlist_file":WATCHLIST_FILE, "watchlist_total":HEALTH.get("watchlist_total"), "watchlist_valid":HEALTH.get("watchlist_valid"), "watchlist_invalid":HEALTH.get("watchlist_invalid"), "last_invalid_watchlist_check":HEALTH.get("last_invalid_watchlist_check"), "positions_open":positions_open, "positions_limit":MAX_OPEN_POSITIONS, "positions_usage_pct":round(usage_pct,2), "can_open_new_positions":positions_open < MAX_OPEN_POSITIONS, "telegram_private_configured":bool(TOKEN and CHAT_ID), "real_orders_enabled":ENABLE_REAL_ORDERS, "funnel_today":funil_hoje(), "today":{"signals":len(hoje["entradas"]),"closed":len(hoje["fechados"]),"wins":len(hoje["wins"]),"breakeven":len(hoje["bes"]),"losses":len(hoje["losses"]),"tp50":len(hoje["tp50s"]),"trailing":len(hoje["trailings"]),"pnl_pct":round(hoje["pnl_total"],4),"win_rate":round(hoje["win_rate"],2)}, "month":{"signals":len(mes["entradas"]),"closed":len(mes["fechados"]),"wins":len(mes["wins"]),"breakeven":len(mes["bes"]),"losses":len(mes["losses"]),"tp50":len(mes["tp50s"]),"trailing":len(mes["trailings"]),"pnl_pct":round(mes["pnl_total"],4),"win_rate":round(mes["win_rate"],2)}, "hunter_score_min":HUNTER_SCORE_MIN, "hunter_breakout_lookback":HUNTER_BREAKOUT_LOOKBACK, "hunter_volume_mult_min":HUNTER_VOLUME_MULT_MIN, "max_risk_h1":MAX_RISK_H1, "startup_signal_grace_seconds":STARTUP_SIGNAL_GRACE_SECONDS, "startup_signal_guard_active":startup_signal_guard_active(), "startup_guard_restante_segundos":startup_guard_restante_segundos(), "watchdog_status":HEALTH.get("watchdog_last_status","OK")}, ensure_ascii=False, indent=2)
def processar_comando(texto):
    cmd = texto.strip().lower().split("@")[0]
    if cmd in ["/start","/help","/comandos"]: return "📌 Comandos disponíveis:\n\n/health - painel técnico do Meme Hunter\n/teste - testa conexão com Telegram\n/posicoes - lista posições abertas\n/top - mostra melhores posições abertas\n/resumo - envia resumo do dia\n/mensal - envia resumo do mês\n/mes - envia resumo do mês\n/estatisticas - histórico geral\n/watchlist - mostra ativos monitorados\n/comandos - mostra esta lista"
    if cmd == "/health": return montar_health_tecnico()
    if cmd == "/teste": return "✅ Meme Hunter conectado ao Telegram."
    if cmd in ["/posicoes", "/posições"]: return montar_posicoes()
    if cmd == "/top":
        ativos = obter_posicoes_ativas_ordenadas()
        if not ativos: return "📊 TOP MEME HUNTER\n\nNenhuma posição ativa."
        return "📊 TOP MEME HUNTER\n\n" + "\n".join([f"{p['symbol_clean']} {side_nome(p['side'])} | {fmt_pct(p.get('pnl_atual',0))} | {fmt_r(p.get('r_atual',0))}" for p in ativos[:10]])
    if cmd == "/resumo": return montar_resumo("dia")
    if cmd in ["/mensal", "/mes"]: return montar_resumo("mes")
    if cmd == "/estatisticas": return montar_resumo("all")
    if cmd == "/watchlist": return "👀 WATCHLIST MEME HUNTER\n\n" + "\n".join([nome_limpo(s) for s in carregar_watchlist()])
    return None
def listen_commands():
    global ultimo_update_id
    print("INTERPRETADOR DE COMANDOS MEME INICIADO")
    while True:
        try:
            if not TOKEN or not CHAT_ID: time.sleep(COMMAND_SLEEP_SECONDS); continue
            params = {"timeout":20}
            if ultimo_update_id is not None: params["offset"] = ultimo_update_id + 1
            data = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params=params, timeout=30).json()
            for upd in data.get("result", []):
                ultimo_update_id = upd.get("update_id", ultimo_update_id); msg = upd.get("message") or upd.get("edited_message")
                if not msg: continue
                if str(msg.get("chat", {}).get("id")) != str(CHAT_ID): continue
                texto = msg.get("text", "")
                if not texto: continue
                resposta = processar_comando(texto.strip().split()[0])
                if resposta: send_telegram_safe(resposta)
        except Exception as e: print("ERRO LISTEN COMMANDS MEME:", e)
        time.sleep(COMMAND_SLEEP_SECONDS)
def avisar_startup_meme_uma_vez():
    chave = "memepro:startup_msg_last_ts"; agora = time.time(); ultimo = float(redis_get_str(chave) or 0)
    if agora - ultimo < STARTUP_MSG_COOLDOWN_SECONDS: print("Startup Meme já avisado recentemente. Pulando Telegram."); return
    redis_set_str(chave, str(agora)); send_telegram_safe(f"🐸 Meme Hunter iniciado\n\nBot privado online ✅\nWatchlist: {WATCHLIST_FILE}\nScore mínimo: {HUNTER_SCORE_MIN}\nVolume mínimo: {HUNTER_VOLUME_MULT_MIN}x\nRisco máximo H1: {MAX_RISK_H1}%\nOrdens reais: {'ATIVADAS ⚠️' if ENABLE_REAL_ORDERS else 'DESATIVADAS ✅'}\nStartup guard: {STARTUP_SIGNAL_GRACE_SECONDS}s")
def parse_data_hora_sp(valor):
    try: return datetime.strptime(str(valor), "%d/%m/%Y %H:%M").replace(tzinfo=timezone(timedelta(hours=-3))) if valor else None
    except Exception: return None
def minutos_desde(valor):
    dt = parse_data_hora_sp(valor); return (agora_sp() - dt).total_seconds()/60 if dt else None
def watchdog():
    time.sleep(60)
    while True:
        try:
            HEALTH["watchdog_last_check"] = data_hora_sp_str(); reasons = []
            ms = minutos_desde(HEALTH.get("last_scanner_run")); mm = minutos_desde(HEALTH.get("last_management_run"))
            if ms is not None and ms > WATCHDOG_THRESHOLD_MINUTES: reasons.append(f"Scanner parado há {int(ms)} minutos")
            if mm is not None and mm > WATCHDOG_THRESHOLD_MINUTES: reasons.append(f"Gestão parada há {int(mm)} minutos")
            if HEALTH.get("last_error"): reasons.append(f"Erro: {HEALTH.get('last_error')}")
            HEALTH["watchdog_last_status"] = "ALERTA" if reasons else "OK"
        except Exception as e: print("ERRO WATCHDOG MEME:", e)
        time.sleep(WATCHDOG_CHECK_SECONDS)
def run_thread_guarded(nome, target):
    while True:
        try: target()
        except Exception as e:
            HEALTH["last_error"] = f"Thread {nome} travou: {e}"; print(f"ERRO FATAL THREAD MEME {nome}:", e); time.sleep(10)
def scanner():
    print("SCANNER MEME HUNTER INICIADO"); HEALTH["started_at"] = data_hora_sp_str(); validar_watchlist_bingx(carregar_watchlist(), avisar_telegram=True); avisar_startup_meme_uma_vez()
    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str(); watchlist = validar_watchlist_bingx(carregar_watchlist(), avisar_telegram=False); HEALTH["last_watchlist_count"] = len(watchlist)
            tickers_cache = safe_fetch_tickers(watchlist); gerenciar_posicoes(tickers_cache); enviar_resumo_diario_se_preciso(); enviar_resumo_mensal_se_preciso(); HEALTH["last_positions_count"] = contar_posicoes_ativas(); sinais_enviados = 0
            if contar_posicoes_ativas() < MAX_OPEN_POSITIONS:
                for symbol in watchlist:
                    try:
                        if limite_posicoes_atingido(): break
                        if existe_posicao_ativa(symbol): registrar_funil("reprovados_posicao_ativa"); continue
                        ohlcv_h1 = safe_fetch_ohlcv(symbol, TIMEFRAME_H1, 3)
                        if not ohlcv_h1 or len(ohlcv_h1) < 3: continue
                        timestamp = int(ohlcv_h1[-2][0])
                        if ultimo_candle_h1.get(symbol) == timestamp: continue
                        ultimo_candle_h1[symbol] = timestamp
                        s = detectar_hunter_breakout(symbol)
                        if not s: continue
                        historico = carregar_sinais(); chave = f"{s['signal_type']}_{s['symbol']}_{s['timestamp']}_{s['side']}"
                        if chave in historico: continue
                        if startup_signal_guard_active():
                            historico[chave] = True; salvar_sinais(dict(list(historico.items())[-3000:])); registrar_funil("startup_guard_ignorados"); print(f"STARTUP GUARD MEME: sinal antigo ignorado {s['symbol_clean']} {s['side']}"); continue
                        if registrar_posicao(s):
                            historico[chave] = True; salvar_sinais(dict(list(historico.items())[-3000:])); registrar_funil("sinais_enviados"); enviar_sinal_hunter(s); sinais_enviados += 1
                    except Exception as e: print(f"ERRO SCAN MEME {symbol}:", e)
            HEALTH["last_signals_sent"] = sinais_enviados; HEALTH["last_success"] = data_hora_sp_str(); HEALTH["last_error"] = None
        except Exception as e:
            HEALTH["last_error"] = str(e); print("ERRO SCANNER MEME:", e)
        time.sleep(SCAN_SLEEP_SECONDS)

@app.route("/")
def home(): return "Meme Hunter Online"
@app.route("/health")
def health(): return json.loads(montar_health_tecnico())
@app.route("/watchdog")
def watchdog_status(): return {"ok": HEALTH.get("watchdog_last_status", "OK") == "OK", "bot":"Meme Hunter", "last_scanner_run":HEALTH.get("last_scanner_run"), "last_management_run":HEALTH.get("last_management_run"), "last_error":HEALTH.get("last_error"), "last_warning":HEALTH.get("last_warning"), "watchdog_status":HEALTH.get("watchdog_last_status", "OK"), "watchdog_last_check":HEALTH.get("watchdog_last_check")}

threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog), daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
