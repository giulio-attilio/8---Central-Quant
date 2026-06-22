# COBRA ATTACK BOT
# Versao: 2026-06-21-COBRA-CENTRAL-QUANT-RESILIENTE-V2
#
# Adaptado para Central Quant PRO.
# Melhorias: watchlist separada, warnings não críticos, startup guard, startup message cooldown.

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

# ====================================================
# CONFIGURACOES TELEGRAM / REDIS / EXCHANGE
# ====================================================

TOKEN = (
    os.environ.get("COBRA_ATTACK_TOKEN")
    or os.environ.get("COBRA_TELEGRAM_BOT_TOKEN")
    or os.environ.get("COBRA_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
)
CHAT_ID = (
    os.environ.get("COBRA_ATTACK_CHAT_ID")
    or os.environ.get("COBRA_TELEGRAM_CHAT_ID")
    or os.environ.get("COBRA_CHAT_ID")
    or os.environ.get("TELEGRAM_CHAT_ID")
)

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = os.environ.get("COBRA_WATCHLIST_FILE", "watchlists/cobra.json")

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

# ====================================================
# CHAVES REDIS
# ====================================================

POSITIONS_KEY = "cobra:positions"
SIGNALS_KEY = "cobra:signals"
TRADES_KEY = "cobra:trades"
STATE_KEY = "cobra:state"
DAILY_SUMMARY_KEY = "cobra:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "cobra:monthly_summary_sent"
FUNNEL_KEY = "cobra:funnel"

# ====================================================
# PARAMETROS PRINCIPAIS
# ====================================================

TIMEFRAME_H1 = "1h"
TIMEFRAME_H4 = "4h"

BB_LEN = 20
BB_STD = 2.0
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_LEN = 14
ATR_LEN = 14
EMA_FAST = 9
EMA_MID = 21
EMA50 = 50
EMA200 = 200
SUPERTREND_PERIOD = 10
SUPERTREND_FACTOR = 3.0

EARLY_COBRA_MAX_CANDLES = 3
COBRA_MAX_CANDLES = 5
EARLY_COBRA_MIN_SCORE = 70
COBRA_MIN_SCORE = 75

ATR_BUFFER_STOP = 0.20
TP50_R = 1.0
BE_TRIGGER_R = 1.5
BE_OFFSET_PCT = 0.10
TRAIL_ATR_MULT = 2.0

MAX_OPEN_POSITIONS = int(os.environ.get("COBRA_MAX_OPEN_POSITIONS", "20"))
USE_MAX_RISK_FILTER = True
MAX_RISK_H1 = float(os.environ.get("COBRA_MAX_RISK_H1", "3.5"))

ENABLE_SPIKE_FILTER = True
SPIKE_RANGE_ATR_MULT = 6.0
SPIKE_BODY_ATR_MULT = 4.0

SCAN_SLEEP_SECONDS = 60
COMMAND_SLEEP_SECONDS = 2
PROTECTION_SECONDS = 300

# Proteção anti-lote após deploy/restart do Render.
STARTUP_SIGNAL_GRACE_SECONDS = int(os.environ.get("COBRA_STARTUP_SIGNAL_GRACE_SECONDS", "600"))
SERVICE_STARTED_TS = time.time()
STARTUP_ALERT_COOLDOWN_SECONDS = int(os.environ.get("COBRA_STARTUP_ALERT_COOLDOWN_SECONDS", "3600"))

MONTHLY_SUMMARY_DAY = 1
DAILY_SUMMARY_HOUR = 23
DAILY_SUMMARY_MINUTE = 55
MONTHLY_SUMMARY_HOUR = 23
MONTHLY_SUMMARY_MINUTE = 55

ultimo_candle_h1 = {}
ultimo_update_id = None

HEALTH = {
    "started_at": None,
    "last_scanner_run": None,
    "last_management_run": None,
    "last_success": None,
    "last_error": None,
    "last_watchlist_count": 0,
    "watchlist_total": 0,
    "watchlist_valid": 0,
    "watchlist_invalid": [],
    "last_signals_sent": 0,
    "last_positions_count": 0,
    "last_warning": None,
    "last_invalid_watchlist_check": None,
}

# ====================================================
# CAMADA DE RESILIENCIA API (CCXT SAFE FETCH)
# ====================================================

def safe_fetch_ohlcv(symbol, timeframe, limit, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso: Erro API OHLCV ({attempt+1}/{max_retries}) para {symbol}: {e}")
            time.sleep(2 ** attempt) # Backoff exponencial: 1s, 2s, 4s...
    HEALTH["last_warning"] = f"Falha OHLCV {symbol} {timeframe} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return []

def safe_fetch_ticker(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ticker(symbol)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso: Erro API Ticker ({attempt+1}/{max_retries}) para {symbol}: {e}")
            time.sleep(2 ** attempt)
    HEALTH["last_warning"] = f"Falha Ticker {symbol} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return None

def safe_load_markets(max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.load_markets()
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso: Erro API Load Markets ({attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
    HEALTH["last_warning"] = "Falha ao carregar markets da exchange após retries"
    print(HEALTH["last_warning"])
    return None

# ====================================================
# UTILITARIOS
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
        if "Ãƒ" in msg or "Ã¢" in msg or "Ã°Å¸" in msg:
            msg = msg.encode("latin1").decode("utf-8")
    except Exception:
        pass
    return msg

def fmt_br(v):
    try:
        return f"{float(v):,.8f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")
    except Exception:
        return str(v)

def fmt_pct(v):
    try:
        return f"{float(v):+.2f}%".replace(".", ",")
    except Exception:
        return str(v)

def fmt_r(v):
    try:
        return f"{float(v):.2f}R".replace(".", ",")
    except Exception:
        return str(v)

def check_bool(v):
    return "✅" if bool(v) else "❌"

def send_telegram(msg):
    msg = normalizar_texto(msg)
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM COBRA NAO CONFIGURADO:")
        print(msg)
        return
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20,
        )
    except Exception as e:
        print("ERRO TELEGRAM COBRA:", e)



def startup_signal_guard_active():
    try:
        return time.time() - SERVICE_STARTED_TS < STARTUP_SIGNAL_GRACE_SECONDS
    except Exception:
        return False

def enviar_startup_cobra_uma_vez():
    chave = "cobra:startup_msg_last_ts"
    agora = time.time()
    try:
        ultimo = redis.get(chave)
        ultimo = float(ultimo or 0)
        if agora - ultimo < STARTUP_ALERT_COOLDOWN_SECONDS:
            print("Startup Cobra já avisado recentemente. Pulando Telegram.")
            return
        redis.set(chave, str(agora))
    except Exception as e:
        print("Erro na trava startup Cobra:", e)

    send_telegram(
        "🐍 Cobra Attack iniciado.\n\n"
        "Bot privado online.\n"
        f"Watchlist: {WATCHLIST_FILE}\n"
        f"Startup guard: {STARTUP_SIGNAL_GRACE_SECONDS}s"
    )

def redis_get_json(key, padrao):
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
    try:
        redis.set(key, json.dumps(value, ensure_ascii=False))
    except Exception as e:
        print(f"ERRO REDIS SET {key}:", e)

def carregar_posicoes():
    return redis_get_json(POSITIONS_KEY, {})

def salvar_posicoes(dados):
    redis_set_json(POSITIONS_KEY, dados)

def carregar_sinais():
    return redis_get_json(SIGNALS_KEY, {})

def salvar_sinais(dados):
    redis_set_json(SIGNALS_KEY, dados)

def carregar_trades():
    return redis_get_json(TRADES_KEY, [])

def salvar_trades(dados):
    redis_set_json(TRADES_KEY, dados)

def carregar_state():
    return redis_get_json(STATE_KEY, {})

def salvar_state(dados):
    redis_set_json(STATE_KEY, dados)

def registrar_evento_trade(evento):
    trades = carregar_trades()
    trades.append(evento)
    if len(trades) > 2000:
        trades = trades[-2000:]
    salvar_trades(trades)

# ====================================================
# FUNIL COBRA - DIAGNOSTICO DE SINAIS BLOQUEADOS
# ====================================================

FUNIL_PADRAO = {
    "ativos_analisados": 0,
    "macd_buy": 0,
    "macd_sell": 0,
    "bollinger_buy": 0,
    "bollinger_sell": 0,
    "early_detectados": 0,
    "cobra_detectados": 0,
    "reprovados_risco": 0,
    "reprovados_score": 0,
    "reprovados_spike": 0,
    "reprovados_posicao_ativa": 0,
    "sinais_enviados": 0,
}

def carregar_funil():
    dados = redis_get_json(FUNNEL_KEY, {})
    if not isinstance(dados, dict):
        dados = {}
    return dados

def salvar_funil(dados):
    redis_set_json(FUNNEL_KEY, dados)

def funil_hoje():
    dados = carregar_funil()
    hoje = data_hoje_sp_str()
    base = dict(FUNIL_PADRAO)
    atual = dados.get(hoje, {})
    if isinstance(atual, dict):
        base.update(atual)
    return base

def registrar_funil(campo, qtd=1):
    try:
        dados = carregar_funil()
        hoje = data_hoje_sp_str()
        atual = dados.get(hoje, {})
        if not isinstance(atual, dict):
            atual = {}
        base = dict(FUNIL_PADRAO)
        base.update(atual)
        base[campo] = int(base.get(campo, 0)) + int(qtd)
        dados[hoje] = base

        if len(dados) > 45:
            chaves = sorted(dados.keys())[-45:]
            dados = {k: dados[k] for k in chaves}

        salvar_funil(dados)
    except Exception as e:
        print("ERRO REGISTRAR FUNIL COBRA:", e)

def carregar_watchlist():
    candidatos = [WATCHLIST_FILE]
    if WATCHLIST_FILE != "watchlist.json":
        candidatos.append("watchlist.json")
    if WATCHLIST_FILE != "watchlists/cobra.json":
        candidatos.append("watchlists/cobra.json")

    for arquivo in candidatos:
        try:
            with open(arquivo, "r") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        except Exception as e:
            pass

    return []

def validar_watchlist_bingx(watchlist, avisar_telegram=False):
    validos = []
    invalidos = []
    
    markets = safe_load_markets()
    if not markets:
        return watchlist # Retorna intacto se a API falhou

    for symbol in watchlist:
        if symbol in markets:
            validos.append(symbol)
        else:
            invalidos.append(symbol)

    HEALTH["watchlist_total"] = len(watchlist)
    HEALTH["watchlist_valid"] = len(validos)
    HEALTH["watchlist_invalid"] = invalidos
    HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()

    if invalidos and avisar_telegram:
        send_telegram(
            "⚠️ Ativos inválidos na watchlist BingX:\n\n"
            + "\n".join(invalidos)
            + "\n\nEles serão ignorados pelo Cobra Attack."
        )

    return validos

def existe_posicao_ativa(symbol):
    posicoes = carregar_posicoes()
    return symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO"

def contar_posicoes_ativas():
    posicoes = carregar_posicoes()
    return len([p for p in posicoes.values() if p.get("status") != "ENCERRADO"])

def limite_posicoes_atingido():
    return contar_posicoes_ativas() >= MAX_OPEN_POSITIONS

def pnl_pct(side, entry, price):
    if side == "LONG":
        return ((price - entry) / entry) * 100
    return ((entry - price) / entry) * 100

def pnl_r(side, entry, sl_inicial, price):
    risk = abs(float(entry) - float(sl_inicial))
    if risk <= 0:
        return 0.0
    if side == "LONG":
        return (float(price) - float(entry)) / risk
    return (float(entry) - float(price)) / risk

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
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()

def calcular_rsi(series, period=14):
    delta = series.astype(float).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)

def calcular_supertrend_df(df, period=10, multiplier=3.0):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    hl2 = (high + low) / 2
    upperband = hl2 + multiplier * atr
    lowerband = hl2 - multiplier * atr
    final_upper = upperband.copy()
    final_lower = lowerband.copy()
    direction = pd.Series(index=df.index, dtype="int64")
    supertrend = pd.Series(index=df.index, dtype="float64")
    direction.iloc[0] = 1
    supertrend.iloc[0] = lowerband.iloc[0]

    for i in range(1, len(df)):
        final_upper.iloc[i] = upperband.iloc[i] if upperband.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1] else final_upper.iloc[i - 1]
        final_lower.iloc[i] = lowerband.iloc[i] if lowerband.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1] else final_lower.iloc[i - 1]
        if direction.iloc[i - 1] == -1:
            direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    return supertrend, direction

def marcar_spikes(df):
    df = df.copy()
    if not ENABLE_SPIKE_FILTER:
        df["spike_suspeito"] = False
        return df
    if "atr14" not in df.columns:
        df["atr14"] = calcular_atr(df, ATR_LEN)
    candle_range = (df["high"].astype(float) - df["low"].astype(float)).abs()
    candle_body = (df["close"].astype(float) - df["open"].astype(float)).abs()
    atr = df["atr14"].astype(float)
    df["spike_suspeito"] = ((candle_range > atr * SPIKE_RANGE_ATR_MULT) | (candle_body > atr * SPIKE_BODY_ATR_MULT)).fillna(False)
    return df

def preparar_df(df):
    df = df.copy()
    df["ema9"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=EMA_MID, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=EMA200, adjust=False).mean()
    df["atr14"] = calcular_atr(df, ATR_LEN)

    bb_basis = df["close"].rolling(BB_LEN).mean()
    bb_dev = df["close"].rolling(BB_LEN).std()
    df["bb_middle"] = bb_basis
    df["bb_upper"] = bb_basis + BB_STD * bb_dev
    df["bb_lower"] = bb_basis - BB_STD * bb_dev
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / bb_basis
    df["bb_width_avg"] = df["bb_width"].rolling(100).mean()
    df["bb_expanding"] = df["bb_width"] > df["bb_width_avg"]

    macd_fast = df["close"].ewm(span=MACD_FAST, adjust=False).mean()
    macd_slow = df["close"].ewm(span=MACD_SLOW, adjust=False).mean()
    df["macd"] = macd_fast - macd_slow
    df["macd_signal"] = df["macd"].ewm(span=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    df["rsi"] = calcular_rsi(df["close"], RSI_LEN)
    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["volume_ok"] = df["volume"] > df["vol_avg20"]

    _, st_dir = calcular_supertrend_df(df, SUPERTREND_PERIOD, SUPERTREND_FACTOR)
    df["supertrend_dir"] = st_dir
    df = marcar_spikes(df)
    return df

def estado_tendencia(candle):
    super_bull = int(candle["supertrend_dir"]) == 1
    super_bear = int(candle["supertrend_dir"]) == -1
    ema_bull = float(candle["ema9"]) > float(candle["ema21"])
    ema_bear = float(candle["ema9"]) < float(candle["ema21"])
    if super_bull and ema_bull:
        return 1
    if super_bear and ema_bear:
        return -1
    return 0

def h4_txt_para_side(h4_state, side):
    if h4_state == 0:
        return "NEUTRO ⚪"
    if side == "LONG":
        return "BULLISH ✅" if h4_state == 1 else "BEARISH ⚠️"
    return "BEARISH ✅" if h4_state == -1 else "BULLISH ⚠️"

def h4_score(h4_state, side):
    if h4_state == 0:
        return 5
    if side == "LONG" and h4_state == 1:
        return 10
    if side == "SHORT" and h4_state == -1:
        return 10
    return 0

def h4_contexto_categoria(h4_state, side):
    try:
        h4_state = int(h4_state)
    except Exception:
        h4_state = 0

    if h4_state == 0:
        return "NEUTRO"
    if side == "LONG" and h4_state == 1:
        return "FAVORAVEL"
    if side == "SHORT" and h4_state == -1:
        return "FAVORAVEL"
    return "CONTRA"

def macd_cross_up(df, idx):
    return float(df.iloc[idx]["macd"]) > float(df.iloc[idx]["macd_signal"]) and float(df.iloc[idx - 1]["macd"]) <= float(df.iloc[idx - 1]["macd_signal"])

def macd_cross_down(df, idx):
    return float(df.iloc[idx]["macd"]) < float(df.iloc[idx]["macd_signal"]) and float(df.iloc[idx - 1]["macd"]) >= float(df.iloc[idx - 1]["macd_signal"])

# ====================================================
# COBRA - DETECCAO
# ====================================================

def calcular_score_cobra(side, h4_state, candle):
    score = 0
    score += 30  
    score += 30  

    volume_ok = bool(candle.get("volume_ok", False))
    if volume_ok:
        score += 10

    rsi = float(candle.get("rsi", 50))
    if side == "LONG" and rsi < 35:
        score += 10
    if side == "SHORT" and rsi > 65:
        score += 10

    score += h4_score(h4_state, side)

    close = float(candle["close"])
    ema21 = float(candle["ema21"])
    atr = float(candle["atr14"])
    dist_atr = abs(close - ema21) / atr if atr > 0 else 0
    if dist_atr >= 0.5:
        score += 10

    return min(int(score), 100)

def qualidade_cobra(score):
    if score >= 85:
        return "EXCELENTE 🐍"
    if score >= 70:
        return "BOA 🟢"
    if score >= 55:
        return "MÉDIA 🟡"
    return "FRACA 🔴"

def calcular_stop_tp_cobra(side, entry, df_h1, return_idx, confirm_idx):
    candle = df_h1.iloc[confirm_idx]
    atr = float(candle["atr14"])
    start_idx = max(0, return_idx - 1)
    janela = df_h1.iloc[start_idx:confirm_idx + 1]

    if side == "LONG":
        sl = float(janela["low"].min()) - atr * ATR_BUFFER_STOP
        risk_abs = abs(entry - sl)
        tp50 = entry + risk_abs * TP50_R
    else:
        sl = float(janela["high"].max()) + atr * ATR_BUFFER_STOP
        risk_abs = abs(sl - entry)
        tp50 = entry - risk_abs * TP50_R

    return float(sl), float(tp50), float(risk_abs)

def detectar_cobra(symbol):
    if existe_posicao_ativa(symbol):
        registrar_funil("reprovados_posicao_ativa")
        return None

    # USO DA FUNÇÃO SEGURA
    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)
    
    if not ohlcv_h1 or not ohlcv_h4:
        return None

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    registrar_funil("ativos_analisados")

    confirm_idx = len(df_h1) - 2
    candle = df_h1.iloc[confirm_idx]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        registrar_funil("reprovados_spike")
        return None

    if macd_cross_up(df_h1, confirm_idx):
        registrar_funil("macd_buy")
    if macd_cross_down(df_h1, confirm_idx):
        registrar_funil("macd_sell")

    h4_state = estado_tendencia(candle_h4)

    for return_idx in range(confirm_idx, max(1, confirm_idx - COBRA_MAX_CANDLES) - 1, -1):
        prev = df_h1.iloc[return_idx - 1]
        ret = df_h1.iloc[return_idx]

        buy_return = float(prev["close"]) < float(prev["bb_lower"]) and float(ret["close"]) > float(ret["bb_lower"])
        sell_return = float(prev["close"]) > float(prev["bb_upper"]) and float(ret["close"]) < float(ret["bb_upper"])

        if buy_return:
            registrar_funil("bollinger_buy")
        if sell_return:
            registrar_funil("bollinger_sell")

        candles_after_return = confirm_idx - return_idx

        if buy_return and macd_cross_up(df_h1, confirm_idx):
            return montar_sinal_cobra(symbol, "LONG", df_h1, df_h4, return_idx, confirm_idx, candles_after_return, h4_state)

        if sell_return and macd_cross_down(df_h1, confirm_idx):
            return montar_sinal_cobra(symbol, "SHORT", df_h1, df_h4, return_idx, confirm_idx, candles_after_return, h4_state)

    return None

def montar_sinal_cobra(symbol, side, df_h1, df_h4, return_idx, confirm_idx, candles_after_return, h4_state):
    candle = df_h1.iloc[confirm_idx]
    timestamp = int(candle["time"])

    if candles_after_return <= EARLY_COBRA_MAX_CANDLES:
        setup = "EARLY_COBRA"
        min_score = EARLY_COBRA_MIN_SCORE
        registrar_funil("early_detectados")
    elif candles_after_return <= COBRA_MAX_CANDLES:
        setup = "COBRA"
        min_score = COBRA_MIN_SCORE
        registrar_funil("cobra_detectados")
    else:
        return None

    entry = float(candle["close"])
    sl, tp50, risk_abs = calcular_stop_tp_cobra(side, entry, df_h1, return_idx, confirm_idx)
    if risk_abs <= 0:
        return None

    risk_pct = risk_abs / entry * 100
    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        registrar_funil("reprovados_risco")
        return None

    score = calcular_score_cobra(side, h4_state, candle)
    if score < min_score:
        registrar_funil("reprovados_score")
        return None

    return {
        "type": "COBRA_SIGNAL",
        "signal_type": setup,
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": timestamp,
        "entry": entry,
        "sl": sl,
        "initial_sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h4_text": h4_txt_para_side(h4_state, side),
        "score": score,
        "qualidade": qualidade_cobra(score),
        "candles_after_return": int(candles_after_return),
        "return_timestamp": int(df_h1.iloc[return_idx]["time"]),
        "volume_ok": bool(candle.get("volume_ok", False)),
        "rsi": float(candle.get("rsi", 50)),
        "bb_expanding": bool(candle.get("bb_expanding", False)),
        "atr14": float(candle.get("atr14", 0)),
        "created_at": time.time(),
    }

# ====================================================
# MENSAGENS
# ====================================================

def side_emoji(side):
    return "🟢" if side == "LONG" else "🔴"

def side_nome(side):
    return "BUY" if side == "LONG" else "SELL"

def setup_nome(setup):
    return "EARLY COBRA" if setup == "EARLY_COBRA" else "COBRA"

def enviar_sinal_cobra(s):
    side = s["side"]
    setup = setup_nome(s["signal_type"])
    side_txt = side_nome(side)
    janela = s.get("candles_after_return", 0)
    if janela == 0:
        janela_txt = "mesmo candle do retorno ✅"
    else:
        janela_txt = f"{janela}º candle após retorno ✅"

    banda_txt = "BANDA INFERIOR" if side == "LONG" else "BANDA SUPERIOR"
    macd_txt = "CRUZAMENTO BUY ✅" if side == "LONG" else "CRUZAMENTO SELL ✅"
    volume_txt = "ALTO ✅" if s.get("volume_ok") else "NORMAL"

    msg = (
        f"🐍 {setup} {side_txt} - {s['symbol_clean']}\n\n"
        f"H4:\n{s['h4_text']}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"Risco:\n{fmt_pct(s['risk_pct'])}\n\n"
        f"Score Cobra:\n{s['score']}/100\n\n"
        f"Qualidade:\n{s['qualidade']}\n\n"
        f"Informativos:\n\n"
        f"Bollinger:\nSAIU DA {banda_txt} E RETORNOU ✅\n\n"
        f"MACD:\n{macd_txt}\n\n"
        f"Janela:\n{janela_txt}\n\n"
        f"Volume:\n{volume_txt}\n\n"
        f"RSI:\n{float(s.get('rsi', 0)):.2f}".replace(".", ",")
    )
    send_telegram(msg)

def enviar_tp50(p, price):
    send_telegram(
        f"🟡 TP50 ATINGIDO - {p['symbol_clean']}\n\n"
        f"Setup:\n{setup_nome(p.get('signal_type'))}\n\n"
        f"Preço:\n{fmt_br(price)}\n\n"
        f"Entrada:\n{fmt_br(p['entry'])}\n\n"
        f"PnL atual:\n{fmt_pct(pnl_pct(p['side'], float(p['entry']), float(price)))}"
    )

def enviar_be(p, new_sl):
    send_telegram(
        f"🟢 BREAKEVEN ATIVADO - {p['symbol_clean']}\n\n"
        f"Setup:\n{setup_nome(p.get('signal_type'))}\n\n"
        f"Novo Stop:\n{fmt_br(new_sl)}"
    )

def enviar_trailing(p, new_sl):
    send_telegram(
        f"🟣 TRAILING ATUALIZADO - {p['symbol_clean']}\n\n"
        f"Setup:\n{setup_nome(p.get('signal_type'))}\n\n"
        f"Stop Atual:\n{fmt_br(new_sl)}"
    )

def enviar_fechamento(p, price, reason, pnl):
    result_type = classificar_resultado(pnl)
    send_telegram(
        f"🟠 COBRA ENCERRADO - {p['symbol_clean']}\n\n"
        f"Setup:\n{setup_nome(p.get('signal_type'))}\n\n"
        f"Lado:\n{side_nome(p['side'])}\n\n"
        f"Motivo:\n{reason}\n\n"
        f"Entrada:\n{fmt_br(p['entry'])}\n\n"
        f"Saída:\n{fmt_br(price)}\n\n"
        f"Resultado:\n{result_type}\n\n"
        f"PnL:\n{fmt_pct(pnl)}\n\n"
        f"MFE máximo:\n{fmt_pct(p.get('mfe_max_pct', 0))}\n\n"
        f"Devolução:\n{fmt_pct(p.get('mfe_gave_back_pct', 0))}"
    )

# ====================================================
# REGISTRO E GESTAO
# ====================================================

def registrar_posicao(s):
    if limite_posicoes_atingido():
        return False
    if existe_posicao_ativa(s["symbol"]):
        return False

    posicoes = carregar_posicoes()
    p = {
        "symbol": s["symbol"],
        "symbol_clean": s["symbol_clean"],
        "side": s["side"],
        "signal_type": s["signal_type"],
        "entry": float(s["entry"]),
        "sl": float(s["sl"]),
        "initial_sl": float(s["initial_sl"]),
        "tp50": float(s["tp50"]),
        "risk_abs": float(s["risk_abs"]),
        "risk_pct": float(s["risk_pct"]),
        "score": int(s["score"]),
        "qualidade": s["qualidade"],
        "h4_state": int(s["h4_state"]),
        "h4_text": s["h4_text"],
        "candles_after_return": int(s["candles_after_return"]),
        "status": "ACTIVE",
        "tp50_hit": False,
        "breakeven": False,
        "trailing_active": False,
        "mfe_max_pct": 0.0,
        "mae_max_pct": 0.0,
        "mfe_max_r": 0.0,
        "mae_max_r": 0.0,
        "mfe_gave_back_pct": 0.0,
        "created_at": time.time(),
        "active_since": time.time(),
        "date": data_hoje_sp_str(),
    }
    posicoes[s["symbol"]] = p
    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": "ENTRY",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": s["symbol"],
        "symbol_clean": s["symbol_clean"],
        "side": s["side"],
        "signal_type": s["signal_type"],
        "entry": float(s["entry"]),
        "sl": float(s["sl"]),
        "tp50": float(s["tp50"]),
        "risk_pct": float(s["risk_pct"]),
        "score": int(s["score"]),
        "h4_state": int(s["h4_state"]),
        "h4_context": h4_contexto_categoria(int(s["h4_state"]), s["side"]),
    })
    return True

def atualizar_mfe_mae(p, preco_atual):
    side = p["side"]
    entry = float(p["entry"])
    initial_sl = float(p.get("initial_sl", p.get("sl")))
    pnl_atual = pnl_pct(side, entry, float(preco_atual))
    r_atual = pnl_r(side, entry, initial_sl, float(preco_atual))

    if pnl_atual > float(p.get("mfe_max_pct", 0)):
        p["mfe_max_pct"] = pnl_atual
        p["mfe_max_r"] = r_atual

    if pnl_atual < float(p.get("mae_max_pct", 0)):
        p["mae_max_pct"] = pnl_atual
        p["mae_max_r"] = r_atual

    p["mfe_gave_back_pct"] = max(0.0, float(p.get("mfe_max_pct", 0)) - pnl_atual)
    p["mfe_gave_back_r"] = max(0.0, float(p.get("mfe_max_r", 0)) - r_atual)
    return p

def calcular_chandelier_stop(symbol, side):
    # USO DA FUNÇÃO SEGURA
    ohlcv = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=120)
    if not ohlcv:
        return None # Retorna None se falhar

    df = preparar_df(pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df.iloc[-2]
    atr = float(candle["atr14"])
    janela = df.iloc[-23:-1]
    if side == "LONG":
        highest = float(janela["high"].max())
        return highest - atr * TRAIL_ATR_MULT
    lowest = float(janela["low"].min())
    return lowest + atr * TRAIL_ATR_MULT

def classificar_resultado(pnl):
    try:
        pnl = float(pnl)
    except Exception:
        return "N/A"
    if pnl > 0.15:
        return "WIN"
    if pnl >= -0.15:
        return "BREAKEVEN"
    return "LOSS"

def fechar_posicao(symbol, p, price, reason):
    pnl = pnl_pct(p["side"], float(p["entry"]), float(price))
    p = atualizar_mfe_mae(p, price)
    p["status"] = "ENCERRADO"
    p["closed_at"] = time.time()
    p["closed_price"] = float(price)
    p["pnl"] = pnl
    p["result_type"] = classificar_resultado(pnl)

    posicoes = carregar_posicoes()
    posicoes[symbol] = p
    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": "CLOSE",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": symbol,
        "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
        "side": p.get("side"),
        "signal_type": p.get("signal_type"),
        "reason": reason,
        "entry": float(p.get("entry")),
        "exit": float(price),
        "pnl": pnl,
        "result_type": p["result_type"],
        "tp50_hit": bool(p.get("tp50_hit")),
        "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
        "mae_max_pct": float(p.get("mae_max_pct", 0)),
        "mfe_gave_back_pct": float(p.get("mfe_gave_back_pct", 0)),
        "mfe_max_r": float(p.get("mfe_max_r", 0)),
        "mae_max_r": float(p.get("mae_max_r", 0)),
        "mfe_gave_back_r": float(p.get("mfe_gave_back_r", 0)),
        "score": int(p.get("score", 0)),
    })

    enviar_fechamento(p, price, reason, pnl)

def gerenciar_posicoes():
    HEALTH["last_management_run"] = data_hora_sp_str()
    posicoes = carregar_posicoes()
    alterou = False

    for symbol, p in list(posicoes.items()):
        if p.get("status") == "ENCERRADO":
            continue
        try:
            # USO DA FUNÇÃO SEGURA
            ticker = safe_fetch_ticker(symbol)
            if not ticker:
                continue

            price = float(ticker["last"])
            p = atualizar_mfe_mae(p, price)
            side = p["side"]
            entry = float(p["entry"])
            sl = float(p["sl"])
            tp50 = float(p["tp50"])
            initial_sl = float(p.get("initial_sl", sl))
            r_atual = pnl_r(side, entry, initial_sl, price)

            if side == "LONG" and price <= sl:
                fechar_posicao(symbol, p, price, "SL/TRAIL")
                continue
            if side == "SHORT" and price >= sl:
                fechar_posicao(symbol, p, price, "SL/TRAIL")
                continue

            if not bool(p.get("tp50_hit", False)):
                if (side == "LONG" and price >= tp50) or (side == "SHORT" and price <= tp50):
                    p["tp50_hit"] = True
                    p["tp50_hit_at"] = time.time()
                    registrar_evento_trade({
                        "event": "TP50",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                        "side": side,
                        "signal_type": p.get("signal_type"),
                        "price": price,
                    })
                    enviar_tp50(p, price)
                    alterou = True

            if not bool(p.get("breakeven", False)) and r_atual >= BE_TRIGGER_R:
                if side == "LONG":
                    new_sl = entry * (1 + BE_OFFSET_PCT / 100)
                    if new_sl > sl:
                        p["sl"] = new_sl
                else:
                    new_sl = entry * (1 - BE_OFFSET_PCT / 100)
                    if new_sl < sl:
                        p["sl"] = new_sl
                p["breakeven"] = True
                p["status"] = "BREAKEVEN"
                registrar_evento_trade({
                    "event": "BREAKEVEN",
                    "date": data_hoje_sp_str(),
                    "datetime": data_hora_sp_str(),
                    "symbol": symbol,
                    "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                    "side": side,
                    "signal_type": p.get("signal_type"),
                    "new_sl": p["sl"],
                })
                enviar_be(p, p["sl"])
                alterou = True

            if bool(p.get("tp50_hit", False)) and bool(p.get("breakeven", False)):
                new_trail = calcular_chandelier_stop(symbol, side)
                if new_trail is not None:
                    if side == "LONG" and new_trail > float(p["sl"]):
                        p["sl"] = float(new_trail)
                        p["status"] = "TRAILING STOP"
                        p["trailing_active"] = True
                        registrar_evento_trade({
                            "event": "TRAILING",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                            "side": side,
                            "signal_type": p.get("signal_type"),
                            "new_sl": p["sl"],
                        })
                        enviar_trailing(p, p["sl"])
                        alterou = True
                    if side == "SHORT" and new_trail < float(p["sl"]):
                        p["sl"] = float(new_trail)
                        p["status"] = "TRAILING STOP"
                        p["trailing_active"] = True
                        registrar_evento_trade({
                            "event": "TRAILING",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p.get("symbol_clean", nome_limpo(symbol)),
                            "side": side,
                            "signal_type": p.get("signal_type"),
                            "new_sl": p["sl"],
                        })
                        enviar_trailing(p, p["sl"])
                        alterou = True

            posicoes[symbol] = p
        except Exception as e:
            print(f"ERRO GESTAO {symbol}:", e)

    if alterou:
        salvar_posicoes(posicoes)

# ====================================================
# RELATORIOS E COMANDOS
# ====================================================

def obter_posicoes_ativas_ordenadas():
    posicoes = carregar_posicoes()
    ativos = []
    for symbol, p in posicoes.items():
        if p.get("status") == "ENCERRADO":
            continue
        try:
            # USO DA FUNÇÃO SEGURA AQUI TAMBÉM
            ticker = safe_fetch_ticker(symbol)
            if ticker:
                price = float(ticker["last"])
                p = dict(p)
                p["preco_atual"] = price
                p["pnl_atual"] = pnl_pct(p["side"], float(p["entry"]), price)
                p["r_atual"] = pnl_r(p["side"], float(p["entry"]), float(p.get("initial_sl", p.get("sl"))), price)
            else:
                p = dict(p)
                p["pnl_atual"] = 0
                p["r_atual"] = 0
            ativos.append(p)
        except Exception:
            p = dict(p)
            p["pnl_atual"] = 0
            p["r_atual"] = 0
            ativos.append(p)
    ativos.sort(key=lambda x: x.get("pnl_atual", 0), reverse=True)
    return ativos

def montar_posicoes():
    ativos = obter_posicoes_ativas_ordenadas()
    data = data_hora_sp_str()
    if not ativos:
        return f"📊 POSIÇÕES COBRA ATTACK\n{data}\n\nNenhum trade ativo."
    linhas = ["📊 POSIÇÕES COBRA ATTACK", data]
    for p in ativos:
        linhas.append(
            f"\n{p['symbol_clean']} - {side_nome(p['side'])}\n\n"
            f"Setup:\n{setup_nome(p.get('signal_type'))}\n\n"
            f"PnL:\n{fmt_pct(p.get('pnl_atual', 0))} | {fmt_r(p.get('r_atual', 0))}\n\n"
            f"Entrada:\n{fmt_br(p['entry'])}\n\n"
            f"Stop Atual:\n{fmt_br(p['sl'])}\n\n"
            f"TP50:\n{fmt_br(p['tp50'])}\n\n"
            f"Score:\n{p.get('score', 0)}/100\n\n"
            f"Status:\n"
            f"Breakeven {check_bool(p.get('breakeven'))}\n"
            f"TP50 {check_bool(p.get('tp50_hit'))}\n"
            f"Trailing {check_bool(p.get('trailing_active'))}\n"
            f"───────────────"
        )
    return "\n".join(linhas)

def filtrar_trades_periodo(periodo="dia"):
    trades = carregar_trades()
    hoje = data_hoje_sp_str()
    mes = agora_sp().strftime("%Y-%m")
    if periodo == "dia":
        return [t for t in trades if t.get("date") == hoje]
    if periodo == "mes":
        return [t for t in trades if str(t.get("date", "")).startswith(mes)]
    return trades

def calcular_metricas_resumo(periodo="dia"):
    trades = filtrar_trades_periodo(periodo)
    entradas = [t for t in trades if t.get("event") == "ENTRY"]
    fechados = [t for t in trades if t.get("event") == "CLOSE"]
    tp50s = [t for t in trades if t.get("event") == "TP50"]
    trailings = [t for t in trades if t.get("event") == "TRAILING"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]

    early = [t for t in entradas if t.get("signal_type") == "EARLY_COBRA"]
    cobra = [t for t in entradas if t.get("signal_type") == "COBRA"]
    early_fechados = [t for t in fechados if t.get("signal_type") == "EARLY_COBRA"]
    cobra_fechados = [t for t in fechados if t.get("signal_type") == "COBRA"]

    def wr(lista):
        if not lista:
            return 0.0
        w = len([t for t in lista if t.get("result_type") == "WIN"])
        return w / len(lista) * 100

    h4_favoravel = [t for t in entradas if t.get("h4_context") == "FAVORAVEL"]
    h4_neutro = [t for t in entradas if t.get("h4_context") == "NEUTRO"]
    h4_contra = [t for t in entradas if t.get("h4_context") == "CONTRA"]

    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)
    mfe_medio = sum(float(t.get("mfe_max_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    mae_medio = sum(float(t.get("mae_max_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    devolucao_media = sum(float(t.get("mfe_gave_back_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    mfe_medio_r = sum(float(t.get("mfe_max_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    mae_medio_r = sum(float(t.get("mae_max_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    devolucao_media_r = sum(float(t.get("mfe_gave_back_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    score_medio = sum(int(t.get("score", 0)) for t in entradas) / len(entradas) if entradas else 0
    win_rate = len(wins) / len(fechados) * 100 if fechados else 0

    return {
        "trades": trades,
        "entradas": entradas,
        "fechados": fechados,
        "tp50s": tp50s,
        "trailings": trailings,
        "wins": wins,
        "losses": losses,
        "bes": bes,
        "early": early,
        "cobra": cobra,
        "early_wr": wr(early_fechados),
        "cobra_wr": wr(cobra_fechados),
        "h4_favoravel": h4_favoravel,
        "h4_neutro": h4_neutro,
        "h4_contra": h4_contra,
        "pnl_total": pnl_total,
        "mfe_medio": mfe_medio,
        "mae_medio": mae_medio,
        "devolucao_media": devolucao_media,
        "mfe_medio_r": mfe_medio_r,
        "mae_medio_r": mae_medio_r,
        "devolucao_media_r": devolucao_media_r,
        "score_medio": score_medio,
        "win_rate": win_rate,
    }

def montar_resumo(periodo="dia"):
    data_txt = agora_sp().strftime("%d/%m/%Y") if periodo == "dia" else agora_sp().strftime("%m/%Y") if periodo == "mes" else "Histórico"
    trades = filtrar_trades_periodo(periodo)
    entradas = [t for t in trades if t.get("event") == "ENTRY"]
    fechados = [t for t in trades if t.get("event") == "CLOSE"]
    tp50s = [t for t in trades if t.get("event") == "TP50"]
    trailings = [t for t in trades if t.get("event") == "TRAILING"]

    early_buy = [t for t in entradas if t.get("signal_type") == "EARLY_COBRA" and t.get("side") == "LONG"]
    early_sell = [t for t in entradas if t.get("signal_type") == "EARLY_COBRA" and t.get("side") == "SHORT"]
    cobra_buy = [t for t in entradas if t.get("signal_type") == "COBRA" and t.get("side") == "LONG"]
    cobra_sell = [t for t in entradas if t.get("signal_type") == "COBRA" and t.get("side") == "SHORT"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)
    mfe_medio = sum(float(t.get("mfe_max_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    mae_medio = sum(float(t.get("mae_max_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    devolucao_media = sum(float(t.get("mfe_gave_back_pct", 0)) for t in fechados) / len(fechados) if fechados else 0
    mfe_medio_r = sum(float(t.get("mfe_max_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    mae_medio_r = sum(float(t.get("mae_max_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    devolucao_media_r = sum(float(t.get("mfe_gave_back_r", 0)) for t in fechados) / len(fechados) if fechados else 0
    score_medio = sum(int(t.get("score", 0)) for t in entradas) / len(entradas) if entradas else 0
    win_rate = len(wins) / len(fechados) * 100 if fechados else 0

    h4_favoravel = [t for t in entradas if t.get("h4_context") == "FAVORAVEL"]
    h4_neutro = [t for t in entradas if t.get("h4_context") == "NEUTRO"]
    h4_contra = [t for t in entradas if t.get("h4_context") == "CONTRA"]

    early_fechados = [t for t in fechados if t.get("signal_type") == "EARLY_COBRA"]
    cobra_fechados = [t for t in fechados if t.get("signal_type") == "COBRA"]
    early_wr = len([t for t in early_fechados if t.get("result_type") == "WIN"]) / len(early_fechados) * 100 if early_fechados else 0
    cobra_wr = len([t for t in cobra_fechados if t.get("result_type") == "WIN"]) / len(cobra_fechados) * 100 if cobra_fechados else 0

    melhor = max(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None
    pior = min(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None

    ativos = obter_posicoes_ativas_ordenadas()
    funil = funil_hoje() if periodo == "dia" else None

    linhas = [
        "🐍 RESUMO COBRA ATTACK",
        data_txt,
        "",
        f"Sinais Cobra: {len(entradas)}",
        f"Early Cobra BUY: {len(early_buy)}",
        f"Early Cobra SELL: {len(early_sell)}",
        f"Cobra BUY: {len(cobra_buy)}",
        f"Cobra SELL: {len(cobra_sell)}",
        "",
    ]

    if funil:
        linhas.extend([
            "🐍 FUNIL COBRA",
            f"Ativos analisados: {funil.get('ativos_analisados', 0)}",
            f"Bollinger BUY: {funil.get('bollinger_buy', 0)}",
            f"Bollinger SELL: {funil.get('bollinger_sell', 0)}",
            f"MACD BUY: {funil.get('macd_buy', 0)}",
            f"MACD SELL: {funil.get('macd_sell', 0)}",
            f"Early detectados: {funil.get('early_detectados', 0)}",
            f"Cobra detectados: {funil.get('cobra_detectados', 0)}",
            f"Reprovados por risco: {funil.get('reprovados_risco', 0)}",
            f"Reprovados por score: {funil.get('reprovados_score', 0)}",
            f"Reprovados por spike: {funil.get('reprovados_spike', 0)}",
            f"Reprovados por posição ativa: {funil.get('reprovados_posicao_ativa', 0)}",
            f"Sinais enviados: {funil.get('sinais_enviados', 0)}",
            "",
        ])

    linhas.extend([
        f"Trades encerrados: {len(fechados)}",
        f"Wins: {len(wins)}",
        f"Breakeven: {len(bes)}",
        f"Loss: {len(losses)}",
        f"Win rate: {win_rate:.2f}%".replace(".", ","),
        "",
        f"TP50 atingidos: {len(tp50s)}",
        f"Trailings atualizados: {len(trailings)}",
        "",
        "PnL realizado:",
        fmt_pct(pnl_total),
        "",
        "MFE médio:",
        f"{fmt_pct(mfe_medio)} | {fmt_r(mfe_medio_r)}",
        "MAE médio:",
        f"{fmt_pct(mae_medio)} | {fmt_r(mae_medio_r)}",
        "Devolução média:",
        f"{fmt_pct(devolucao_media)} | {fmt_r(devolucao_media_r)}",
        "",
        "H4 contexto:",
        f"Favorável: {len(h4_favoravel)}",
        f"Neutro: {len(h4_neutro)}",
        f"Contra: {len(h4_contra)}",
        "",
        "Win rate por setup:",
        f"Early Cobra: {early_wr:.2f}%".replace(".", ","),
        f"Cobra: {cobra_wr:.2f}%".replace(".", ","),
        "",
        "Score médio:",
        f"{score_medio:.1f}/100".replace(".", ","),
        "",
        "Melhor trade:",
        f"{melhor.get('symbol_clean')} {fmt_pct(melhor.get('pnl', 0))}" if melhor else "N/A",
        "",
        "Pior trade:",
        f"{pior.get('symbol_clean')} {fmt_pct(pior.get('pnl', 0))}" if pior else "N/A",
        "",
        f"Trades ainda ativos: {len(ativos)}",
    ])
    if ativos:
        linhas.extend([f"{p['symbol_clean']} {side_nome(p['side'])} | {setup_nome(p.get('signal_type'))} | {fmt_pct(p.get('pnl_atual', 0))}" for p in ativos[:20]])
    return "\n".join(linhas)

def montar_health_tecnico():
    hoje = calcular_metricas_resumo("dia")
    mes = calcular_metricas_resumo("mes")
    funil = funil_hoje()

    payload = {
        "ok": HEALTH.get("last_error") is None,
        "bot": "Cobra Attack",
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "last_warning": HEALTH.get("last_warning"),
        "watchlist_file": WATCHLIST_FILE,
        "daily_summary_time": f"{DAILY_SUMMARY_HOUR:02d}:{DAILY_SUMMARY_MINUTE:02d}",
        "monthly_summary_day": MONTHLY_SUMMARY_DAY,
        "monthly_summary_time": f"{MONTHLY_SUMMARY_HOUR:02d}:{MONTHLY_SUMMARY_MINUTE:02d}",
        "daily_summary_sent": redis_get_str(DAILY_SUMMARY_KEY),
        "monthly_summary_sent": redis_get_str(MONTHLY_SUMMARY_KEY),
        "watchlist_total": HEALTH.get("watchlist_total"),
        "watchlist_valid": HEALTH.get("watchlist_valid"),
        "watchlist_invalid": HEALTH.get("watchlist_invalid"),
        "last_invalid_watchlist_check": HEALTH.get("last_invalid_watchlist_check"),
        "positions_open": contar_posicoes_ativas(),
        "positions_limit": MAX_OPEN_POSITIONS,
        "telegram_private_configured": bool(TOKEN and CHAT_ID),
        "funnel_today": funil,
        "today": {
            "signals": len(hoje["entradas"]),
            "closed": len(hoje["fechados"]),
            "wins": len(hoje["wins"]),
            "breakeven": len(hoje["bes"]),
            "losses": len(hoje["losses"]),
            "tp50": len(hoje["tp50s"]),
            "trailing": len(hoje["trailings"]),
            "pnl_pct": round(hoje["pnl_total"], 4),
            "win_rate": round(hoje["win_rate"], 2),
        },
        "month": {
            "signals": len(mes["entradas"]),
            "closed": len(mes["fechados"]),
            "wins": len(mes["wins"]),
            "breakeven": len(mes["bes"]),
            "losses": len(mes["losses"]),
            "tp50": len(mes["tp50s"]),
            "trailing": len(mes["trailings"]),
            "pnl_pct": round(mes["pnl_total"], 4),
            "win_rate": round(mes["win_rate"], 2),
        },
        "timeframe_h1": TIMEFRAME_H1,
        "timeframe_h4_context": TIMEFRAME_H4,
        "early_cobra_window": EARLY_COBRA_MAX_CANDLES,
        "cobra_window": COBRA_MAX_CANDLES,
        "early_min_score": EARLY_COBRA_MIN_SCORE,
        "cobra_min_score": COBRA_MIN_SCORE,
        "tp50_r": TP50_R,
        "be_trigger_r": BE_TRIGGER_R,
        "trailing_atr_mult": TRAIL_ATR_MULT,
        "max_risk_h1": MAX_RISK_H1,
        "startup_signal_guard_active": startup_signal_guard_active(),
        "startup_signal_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def processar_comando(texto):
    cmd = texto.strip().lower()

    if cmd in ["/start", "/help", "/comandos"]:
        return (
            "🐍 Cobra Attack Online\n\n"
            "Comandos:\n"
            "/health\n"
            "/teste\n"
            "/posicoes\n"
            "/top\n"
            "/resumo\n"
            "/mes\n"
            "/estatisticas\n"
            "/watchlist\n"
            "/comandos"
        )

    if cmd == "/health":
        return montar_health_tecnico()

    if cmd == "/teste":
        return "✅ Cobra Attack conectado ao Telegram."
    if cmd in ["/posicoes", "/posições"]:
        return montar_posicoes()
    if cmd == "/resumo":
        return montar_resumo("dia")
    if cmd == "/mes":
        return montar_resumo("mes")
    if cmd == "/estatisticas":
        return montar_resumo("all")
    if cmd == "/watchlist":
        watchlist = carregar_watchlist()
        return "👀 WATCHLIST COBRA\n\n" + "\n".join([nome_limpo(s) for s in watchlist])
    return None

def listen_commands():
    global ultimo_update_id
    while True:
        try:
            if not TOKEN or not CHAT_ID:
                time.sleep(COMMAND_SLEEP_SECONDS)
                continue
            params = {"timeout": 20}
            if ultimo_update_id is not None:
                params["offset"] = ultimo_update_id + 1
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params=params, timeout=30)
            data = r.json()
            for upd in data.get("result", []):
                ultimo_update_id = upd.get("update_id")
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id"))
                if str(CHAT_ID) != chat_id:
                    continue
                texto = msg.get("text", "")
                resposta = processar_comando(texto)
                if resposta:
                    send_telegram(resposta)
        except Exception as e:
            print("ERRO LISTEN COMMANDS:", e)
        time.sleep(COMMAND_SLEEP_SECONDS)

# ====================================================
# RESUMOS AUTOMATICOS
# ====================================================

def redis_get_str(key, padrao=None):
    try:
        data = redis.get(key)
        if data is None:
            return padrao
        if isinstance(data, str):
            return data
        return str(data)
    except Exception as e:
        print(f"ERRO REDIS GET STR {key}:", e)
        return padrao

def redis_set_str(key, value):
    try:
        redis.set(key, str(value))
    except Exception as e:
        print(f"ERRO REDIS SET STR {key}:", e)

def horario_resumo_atingido():
    agora = agora_sp()
    if agora.hour > DAILY_SUMMARY_HOUR:
        return True
    if agora.hour == DAILY_SUMMARY_HOUR and agora.minute >= DAILY_SUMMARY_MINUTE:
        return True
    return False

def enviar_resumo_diario_se_preciso():
    try:
        if not horario_resumo_atingido():
            return
        hoje = data_hoje_sp_str()
        ja_enviado = redis_get_str(DAILY_SUMMARY_KEY)
        if ja_enviado == hoje:
            return
        send_telegram(montar_resumo("dia"))
        redis_set_str(DAILY_SUMMARY_KEY, hoje)
    except Exception as e:
        HEALTH["last_error"] = f"Erro resumo diario: {e}"
        print("ERRO RESUMO DIARIO COBRA:", e)

def enviar_resumo_mensal_se_preciso():
    try:
        agora = agora_sp()
        if agora.day != MONTHLY_SUMMARY_DAY:
            return
        if agora.hour < MONTHLY_SUMMARY_HOUR:
            return
        if agora.hour == MONTHLY_SUMMARY_HOUR and agora.minute < MONTHLY_SUMMARY_MINUTE:
            return
        mes = agora.strftime("%Y-%m")
        ja_enviado = redis_get_str(MONTHLY_SUMMARY_KEY)
        if ja_enviado == mes:
            return
        send_telegram(montar_resumo("mes"))
        redis_set_str(MONTHLY_SUMMARY_KEY, mes)
    except Exception as e:
        HEALTH["last_error"] = f"Erro resumo mensal: {e}"
        print("ERRO RESUMO MENSAL COBRA:", e)

def verificar_resumos_automaticos():
    enviar_resumo_diario_se_preciso()
    enviar_resumo_mensal_se_preciso()

# ====================================================
# SCANNER
# ====================================================

def scanner():
    HEALTH["started_at"] = data_hora_sp_str()
    watchlist_inicial = carregar_watchlist()
    validar_watchlist_bingx(watchlist_inicial, avisar_telegram=True)
    enviar_startup_cobra_uma_vez()

    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            gerenciar_posicoes()
            verificar_resumos_automaticos()

            watchlist = validar_watchlist_bingx(carregar_watchlist(), avisar_telegram=False)
            HEALTH["last_watchlist_count"] = len(watchlist)
            sinais_enviados = 0

            for symbol in watchlist:
                try:
                    if limite_posicoes_atingido():
                        break

                    # USO DA FUNÇÃO SEGURA
                    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=3)
                    if not ohlcv_h1 or len(ohlcv_h1) < 3:
                        continue

                    timestamp = int(ohlcv_h1[-2][0])
                    if ultimo_candle_h1.get(symbol) == timestamp:
                        continue
                    ultimo_candle_h1[symbol] = timestamp

                    s = detectar_cobra(symbol)
                    if not s:
                        continue

                    historico = carregar_sinais()
                    chave = f"{s['signal_type']}_{s['symbol']}_{s['timestamp']}_{s['side']}"
                    if chave in historico:
                        continue

                    if startup_signal_guard_active():
                        # Evita sinais atrasados logo após deploy/restart.
                        # Marca no histórico para não enviar o mesmo candle depois.
                        historico[chave] = True
                        if len(historico) > 3000:
                            historico = dict(list(historico.items())[-3000:])
                        salvar_sinais(historico)
                        print(f"STARTUP GUARD COBRA: sinal marcado e não enviado: {chave}")
                        continue

                    if startup_signal_guard_active():
                        historico[chave] = True
                        if len(historico) > 3000:
                            historico = dict(list(historico.items())[-3000:])
                        salvar_sinais(historico)
                        print(
                            f"STARTUP GUARD COBRA: sinal antigo ignorado "
                            f"{s['symbol_clean']} {s['side']} {s['signal_type']} "
                            f"({startup_guard_restante_segundos()}s restantes)"
                        )
                        continue

                    if registrar_posicao(s):
                        historico[chave] = True
                        if len(historico) > 3000:
                            historico = dict(list(historico.items())[-3000:])
                        salvar_sinais(historico)
                        registrar_funil("sinais_enviados")
                        enviar_sinal_cobra(s)
                        sinais_enviados += 1

                except Exception as e:
                    print(f"ERRO SCAN {symbol}:", e)

            HEALTH["last_signals_sent"] = sinais_enviados
            HEALTH["last_positions_count"] = contar_posicoes_ativas()
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None

        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO SCANNER COBRA:", e)

        time.sleep(SCAN_SLEEP_SECONDS)

# ====================================================
# WATCHDOG / MONITORAMENTO DE TRAVAMENTO
# ====================================================

WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("COBRA_WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_CHECK_SECONDS = int(os.environ.get("COBRA_WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("COBRA_WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

watchdog_last_alert = {
    "scanner": 0,
    "management": 0,
    "thread": 0,
    "startup": 0,
}

def parse_data_hora_sp(valor):
    try:
        if not valor:
            return None
        dt = datetime.strptime(str(valor), "%d/%m/%Y %H:%M")
        return dt.replace(tzinfo=timezone(timedelta(hours=-3)))
    except Exception:
        return None

def minutos_desde(valor):
    dt = parse_data_hora_sp(valor)
    if not dt:
        return None
    try:
        return (agora_sp() - dt).total_seconds() / 60
    except Exception:
        return None

def pode_alertar(chave):
    agora = time.time()
    ultimo = float(watchdog_last_alert.get(chave, 0))
    if agora - ultimo >= WATCHDOG_ALERT_COOLDOWN_SECONDS:
        watchdog_last_alert[chave] = agora
        return True
    return False

def enviar_alerta_travamento(titulo, detalhe):
    try:
        send_telegram(
            f"🔴 {titulo}\n\n"
            f"{detalhe}\n\n"
            f"Horário:\n{data_hora_sp_str()}"
        )
    except Exception as e:
        print("ERRO AO ENVIAR ALERTA WATCHDOG:", e)

def watchdog():
    time.sleep(60)
    while True:
        try:
            min_scanner = minutos_desde(HEALTH.get("last_scanner_run"))
            min_management = minutos_desde(HEALTH.get("last_management_run"))

            if min_scanner is not None and min_scanner > WATCHDOG_THRESHOLD_MINUTES:
                if pode_alertar("scanner"):
                    enviar_alerta_travamento(
                        "COBRA ATTACK PARADO",
                        f"Scanner sem atualizar há {int(min_scanner)} minutos.\n"
                        f"Último scanner:\n{HEALTH.get('last_scanner_run')}"
                    )

            if min_management is not None and min_management > WATCHDOG_THRESHOLD_MINUTES:
                if pode_alertar("management"):
                    enviar_alerta_travamento(
                        "GESTÃO COBRA PARADA",
                        f"Gestão sem atualizar há {int(min_management)} minutos.\n"
                        f"Última gestão:\n{HEALTH.get('last_management_run')}"
                    )

            if HEALTH.get("started_at") and not HEALTH.get("last_scanner_run"):
                min_started = minutos_desde(HEALTH.get("started_at"))
                if min_started is not None and min_started > WATCHDOG_THRESHOLD_MINUTES:
                    if pode_alertar("scanner"):
                        enviar_alerta_travamento(
                            "COBRA ATTACK SEM SCANNER",
                            f"Bot iniciou há {int(min_started)} minutos, mas o scanner ainda não registrou execução."
                        )

        except Exception as e:
            print("ERRO WATCHDOG:", e)

        time.sleep(WATCHDOG_CHECK_SECONDS)

def run_thread_guarded(nome, target):
    while True:
        try:
            target()
        except Exception as e:
            HEALTH["last_error"] = f"Thread {nome} travou: {e}"
            print(f"ERRO FATAL THREAD {nome}:", e)

            if pode_alertar("thread"):
                enviar_alerta_travamento(
                    f"COBRA THREAD TRAVOU: {nome}",
                    f"Erro:\n{str(e)}\n\nA thread será reiniciada automaticamente."
                )

            time.sleep(10)

def iniciar_threads_monitoradas():
    threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog), daemon=True).start()

# ====================================================
# ROTAS FLASK
# ====================================================

@app.route("/")
def home():
    return "Cobra Attack Online"

@app.route("/health")
def health():
    return json.loads(montar_health_tecnico())

@app.route("/watchdog")
def watchdog_status():
    return {
        "ok": True,
        "bot": "Cobra Attack",
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "minutes_since_scanner": minutos_desde(HEALTH.get("last_scanner_run")),
        "minutes_since_management": minutos_desde(HEALTH.get("last_management_run")),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
    }

iniciar_threads_monitoradas()

if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    except Exception as e:
        enviar_alerta_travamento(
            "COBRA ATTACK TRAVOU",
            f"Erro fatal no Flask/app:\n{str(e)}"
        )
        raise
