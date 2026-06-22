# TREND PRO MTF H4/H1 + POI
# Versão: 2026-06-22-MEME-HUNTER-PRO-V3-CENTRAL-QUANT-RESILIENTE
#
# Lógica:
# - H4 é apenas contexto/filtro.
# - H1 abre trade somente alinhado ao H4.
# - POI H1 gera reentrada/atualização operacional.
# - Novo POI só é enviado se o preço sair da zona EMA9/21 e retornar.
# - EARLY detecta entrada antecipada em rejeição da EMA21.
# - /health mostra status do robô.
# - Filtro anti-spike protege contra candles/dados suspeitos.
# - Sinal recuperado permite entrar em tendência H4/H1 já alinhada.
# - Recuperado agora exige toque na zona EMA9/EMA21 para evitar entrada tardia.
# - Risco ALTO é bloqueado por padrão.
# - POI não dispara logo após entrada/recuperado.
# - Não existe BUY/SELL H4 no Telegram.
# - TP50 = maior entre 1R e 1 ATR H1.
# - BE após TP50 com offset.
# - Trailing stop após TP50 usando Chandelier 2 ATR.
# - TP50 mínimo evita parciais muito curtas em POIs com risco pequeno.
# - REENTRY permite nova entrada depois de trade encerrado que atingiu TP50.
# - POI cooldown aumentado para 2 candles H1.
# - Mensagens explicam o motivo do RECUPERADO e do REENTRY.
# - Correção UTF-8 nas mensagens do Telegram e JSON/Redis.
# - /reset não apaga posições abertas nem histórico; limpa apenas cooldowns/bloqueios.
# - Relatório mensal no dia 01 sobre o mês anterior.
# - Validação da watchlist contra mercados reais da BingX.
# - /health melhorado substitui /status.
# - Limite máximo de 20 posições abertas.
# - /posicoes mostra origem do trade.
# - Corrigido registro de ENTRY antes do return True.
# - Histórico de sinais só é marcado após registro real da posição.
# - Telegram só envia sinal se a posição foi registrada.
# - Score Elite agora filtra sinais do Trend PRO Elite.
#
# Mensagens Telegram:
# 🟢 BUY H1
# 🔴 SELL H1
# 🔵 POI H1
# 🔁 REENTRY H1
# 🟡 TP50 ATINGIDO
# 🟣 TRAILING ATUALIZADO
# 🟠 SL/TRAIL

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

try:
    from strategy import calcular_atr
except Exception:
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

try:
    from telegram_utils import send_telegram, fmt_br, fmt_pct
except Exception:
    def fmt_br(v):
        try:
            return f"{float(v):,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            return str(v)

    def fmt_pct(v):
        try:
            return f"{float(v):+.2f}%".replace(".", ",")
        except Exception:
            return str(v)

    def send_telegram(msg):
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        msg = normalizar_texto(msg)

        if not token or not chat_id:
            print(msg)
            return

        payload = {
            "chat_id": chat_id,
            "text": msg
        }

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20
        )


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

WATCHLIST_FILE = os.environ.get("MEME_WATCHLIST_FILE", "watchlists/meme.json")

POSITIONS_KEY = "memepro:positions"
SIGNALS_KEY = "memepro:signals"
TRADES_KEY = "memepro:trades"
DAILY_SUMMARY_KEY = "memepro:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "memepro:monthly_summary_sent"
REENTRY_BLOCK_KEY = "memepro:reentry_block"
BE_MONITOR_KEY = "memepro:be_monitor"
POI_COOLDOWN_KEY = "memepro:poi_cooldown"
EARLY_COOLDOWN_KEY = "memepro:early_cooldown"
FUNNEL_KEY = "memepro:funnel"
EARLY_HUNTER_COOLDOWN_KEY = "memepro:early_hunter_cooldown"

# ====================================================
# CONFIGURAÇÕES PRINCIPAIS
# ====================================================

TIMEFRAME_H4 = "4h"
TIMEFRAME_H1 = "1h"

EMA_FAST = 9
EMA_MID = 21
EMA50 = 50
EMA200 = 200

SUPERTREND_PERIOD = 10
SUPERTREND_FACTOR = 3.0

ATR_LEN = 14
SWING_LEN = 5
ATR_BUFFER_STOP = 0.25

TP50_R = 1.0
TP50_MIN_ATR = 1.0  # TP50 mínimo = 1 ATR H1

# Gestão Elite:
# - TP50 continua em 1R.
# - Breakeven/trailing só ativa quando o trade andar 1,5R.
BE_TRIGGER_R = 1.5
BE_OFFSET_PCT = 0.10
TRAIL_ATR_MULT = 2.0

# Proteção anti-spike / dado ruim:
# Se o range do candle for absurdo em relação ao ATR, o candle é marcado como suspeito.
ENABLE_SPIKE_FILTER = True
SPIKE_RANGE_ATR_MULT = 6.0
SPIKE_BODY_ATR_MULT = 4.0

# Risco máximo agora bloqueia sinais ALTO por padrão.
USE_MAX_RISK_FILTER = True
MAX_RISK_H1 = float(os.environ.get("MEME_MAX_RISK_H1", "2.5"))

# Limite de exposição operacional.
MAX_OPEN_POSITIONS = int(os.environ.get("MEME_MAX_OPEN_POSITIONS", "20"))

# ====================================================
# TREND PRO ELITE - FILTROS OBRIGATÓRIOS
# ====================================================
# O Trend PRO agora vira Trend PRO Elite: menos sinais, maior qualidade.
ENABLE_TRENDPRO_ELITE_FILTER = True

# Filtro principal para sinais normais e REENTRY.
# Fase 1: mais permissivo para avaliação prática.
ELITE_THRESHOLD = 55
ELITE_MIN_ADX_H4 = 15.0
REQUIRE_HIGH_VOLUME = False
REQUIRE_BB_EXPANDING = False


# ====================================================
# MEME HUNTER PRO V3 - EARLY HUNTER
# ====================================================

def calcular_early_hunter_score(s):
    score = 0
    try:
        vol_ratio = float(s.get("vol_ratio", 0))
        if vol_ratio >= 2.5:
            score += 30
        elif vol_ratio >= 1.8:
            score += 25
        elif vol_ratio >= EARLY_HUNTER_VOLUME_MULT_MIN:
            score += 20
    except Exception:
        pass

    if bool(s.get("pre_breakout_ok", False)):
        score += 25
    if bool(s.get("bb_ok", False)):
        score += 10

    try:
        rsi = float(s.get("rsi14", 50))
        if s.get("side") == "LONG" and rsi >= EARLY_HUNTER_RSI_LONG:
            score += 10
        elif s.get("side") == "SHORT" and rsi <= EARLY_HUNTER_RSI_SHORT:
            score += 10
    except Exception:
        pass

    try:
        adx_h4 = float(s.get("adx_h4", 0))
        if adx_h4 >= 25:
            score += 10
        elif adx_h4 >= MEME_MIN_ADX_H4:
            score += 5
    except Exception:
        pass

    try:
        dist = float(s.get("dist_to_breakout_atr", 99))
        if dist <= 0.20:
            score += 10
        elif dist <= EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR:
            score += 5
    except Exception:
        pass

    return min(int(score), 100)

def detectar_early_hunter(symbol):
    if not ENABLE_EARLY_HUNTER:
        return None
    if existe_posicao_ativa(symbol):
        registrar_funil("reprovados_posicao_ativa")
        return None

    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)
    if not ohlcv_h1 or not ohlcv_h4:
        return None

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    registrar_funil("ativos_analisados")

    candle = df_h1.iloc[-2]
    candle_h4 = df_h4.iloc[-2]
    if bool(candle.get("spike_suspeito", False)):
        registrar_funil("reprovados_spike")
        return None

    lookback = int(EARLY_HUNTER_LOOKBACK)
    janela = df_h1.iloc[-(lookback + 2):-2]
    if len(janela) < lookback:
        return None

    close = float(candle["close"])
    ema9 = float(candle["ema9"])
    ema21 = float(candle["ema21"])
    ema50 = float(candle["ema50"])
    atr = float(candle["atr14"])
    if atr <= 0:
        return None

    max_prev = float(janela["high"].max())
    min_prev = float(janela["low"].min())
    dist_res_atr = (max_prev - close) / atr
    dist_sup_atr = (close - min_prev) / atr

    rsi = float(candle.get("rsi14", 50))
    vol_ratio = float(candle.get("vol_ratio", 0))
    bb_ok = bool(candle.get("bb_ok", False))
    h4_state = estado_tendencia(candle_h4)
    adx_h4 = float(candle_h4.get("adx", 0))

    if vol_ratio < EARLY_HUNTER_VOLUME_MULT_MIN:
        registrar_funil("reprovados_volume")
        return None
    if not passa_volume_financeiro(candle):
        registrar_funil("reprovados_volume_financeiro")
        return None
    if adx_h4 < MEME_MIN_ADX_H4:
        registrar_funil("reprovados_h4")
        return None
    if not bb_ok:
        registrar_funil("reprovados_bb")
        return None

    signal = None
    dist_to_breakout_atr = 99.0
    if ema9 > ema21 > ema50 and close < max_prev and dist_res_atr <= EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR and rsi >= EARLY_HUNTER_RSI_LONG and h4_state != -1:
        signal = "LONG"
        dist_to_breakout_atr = dist_res_atr
    elif ema9 < ema21 < ema50 and close > min_prev and dist_sup_atr <= EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR and rsi <= EARLY_HUNTER_RSI_SHORT and h4_state != 1:
        signal = "SHORT"
        dist_to_breakout_atr = dist_sup_atr
    else:
        registrar_funil("reprovados_rsi")
        return None

    if early_hunter_em_cooldown(symbol, signal):
        return None

    entry = close
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100
    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        registrar_funil("reprovados_risco")
        return None

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle)
    sinal = {
        "type": "SIGNAL",
        "signal_type": "EARLY_HUNTER",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": signal,
        "side": signal,
        "timestamp": int(candle["time"]),
        "entry": entry,
        "sl": sl,
        "initial_sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": estado_tendencia(candle),
        "adx_h4": adx_h4,
        "adx_h1": float(candle.get("adx", 0)),
        "volume_ok": True,
        "bb_ok": bb_ok,
        "qualidade_pontos": pontos,
        "qualidade": qualidade,
        "vol_ratio": vol_ratio,
        "rsi14": rsi,
        "dist_to_breakout_atr": dist_to_breakout_atr,
        "pre_breakout_ok": True,
        "breakout_ref": max_prev if signal == "LONG" else min_prev,
    }
    score = calcular_early_hunter_score(sinal)
    sinal["signal_score"] = score
    sinal["meme_score"] = score
    sinal["elite_candidate"] = score >= EARLY_HUNTER_SCORE_MIN
    if score < EARLY_HUNTER_SCORE_MIN:
        registrar_funil("reprovados_score")
        return None

    marcar_early_hunter_cooldown(symbol, signal)
    registrar_funil("early_hunter_detectados")
    return sinal

# ====================================================
# MEME HUNTER PRO V2 - BREAKOUT + VOLUME + MOMENTUM
# ====================================================
# A lógica principal agora deixa de procurar apenas pullback/POI
# e passa a priorizar rompimento com volume e momentum.
ENABLE_MEME_BREAKOUT_STRATEGY = True
ENABLE_LEGACY_TREND_ENTRIES = False
ENABLE_POI_ALERTS = False

MEME_BREAKOUT_LOOKBACK = int(os.environ.get("MEME_BREAKOUT_LOOKBACK", "20"))
MEME_VOLUME_MULT = float(os.environ.get("MEME_VOLUME_MULT", "2.0"))
MEME_VOLUME_EXTREME_MULT = float(os.environ.get("MEME_VOLUME_EXTREME_MULT", "3.0"))
MEME_MIN_SCORE = int(os.environ.get("MEME_MIN_SCORE", "70"))
MEME_MIN_ADX_H4 = float(os.environ.get("MEME_MIN_ADX_H4", "15.0"))
MEME_RSI_LONG = float(os.environ.get("MEME_RSI_LONG", "58.0"))
MEME_RSI_SHORT = float(os.environ.get("MEME_RSI_SHORT", "42.0"))
MEME_MAX_DIST_EMA9_PCT = float(os.environ.get("MEME_MAX_DIST_EMA9_PCT", "12.0"))
MEME_REQUIRE_BB_EXPANDING = True
MEME_REQUIRE_H1_EMA_STACK = True

# EARLY HUNTER - pré-rompimento para memecoins.
ENABLE_EARLY_HUNTER = str(os.environ.get("MEME_ENABLE_EARLY_HUNTER", "true")).strip().lower() in {"1", "true", "yes", "sim", "on"}
EARLY_HUNTER_SCORE_MIN = int(os.environ.get("MEME_EARLY_HUNTER_SCORE_MIN", "55"))
EARLY_HUNTER_LOOKBACK = int(os.environ.get("MEME_EARLY_HUNTER_LOOKBACK", "20"))
EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR = float(os.environ.get("MEME_EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR", "0.35"))
EARLY_HUNTER_VOLUME_MULT_MIN = float(os.environ.get("MEME_EARLY_HUNTER_VOLUME_MULT_MIN", "1.4"))
EARLY_HUNTER_RSI_LONG = float(os.environ.get("MEME_EARLY_HUNTER_RSI_LONG", "55.0"))
EARLY_HUNTER_RSI_SHORT = float(os.environ.get("MEME_EARLY_HUNTER_RSI_SHORT", "45.0"))
EARLY_HUNTER_COOLDOWN_SECONDS = int(os.environ.get("MEME_EARLY_HUNTER_COOLDOWN_SECONDS", "3600"))

# Filtro opcional de volume financeiro do candle H1 fechado.
USE_MIN_QUOTE_VOLUME_FILTER = str(os.environ.get("MEME_USE_MIN_QUOTE_VOLUME_FILTER", "false")).strip().lower() in {"1", "true", "yes", "sim", "on"}
MIN_QUOTE_VOLUME_H1_USDT = float(os.environ.get("MEME_MIN_QUOTE_VOLUME_H1_USDT", "5000000"))

# EARLY continua ativo como trade mais ousado, com score menor.
EARLY_THRESHOLD = 45
EARLY_MIN_ADX_H4 = 15.0

# POI altera operacionalmente a posição; por isso também passa por filtro.
POI_THRESHOLD = 50
POI_MIN_ADX_H4 = 15.0
POI_REQUIRE_HIGH_VOLUME = False

# RECUPERADO desligado por enquanto.
# Motivo: no histórico recente, muitos RECUPERADOS entraram tarde e deram stop.
# Reavaliar depois de alguns dias/uma semana comparando TP50, stops e volume de sinais.
ENABLE_RECOVERED_SIGNAL = False
RECOVERED_REQUIRE_EMA_ZONE = True

# Relatório automático de posições aos 50 minutos desligado.
# Use /posicoes, /status ou /resumo sob demanda.
ENABLE_AUTO_POSITION_REPORT = False

# Informativos.
ADX_LEN = 14
ADX_MIN = 20.0

# EARLY:
# Entrada antecipada na EMA21, antes da confirmação completa do BUY/SELL H1.
ENABLE_EARLY = True
EARLYDX_H4_MIN = 15.0
# Alias mantido para compatibilidade com versões anteriores.
EARLY_ADX_H4_MIN = EARLYDX_H4_MIN
EARLY_REQUIRE_VOLUME = False
EARLY_COOLDOWN_SECONDS = 60 * 60

# POI.
POI_COOLDOWN_SECONDS = 2 * 60 * 60  # 2 candles H1
POI_AFTER_ENTRY_COOLDOWN_SECONDS = 60 * 60  # evita POI logo após entrada
ALLOW_POI_UPDATE_ENTRY = True

# REENTRY:
# Nova entrada depois que um trade anterior atingiu TP50 e foi encerrado.
# Evita reentrar imediatamente no mesmo candle/correção.
ENABLE_REENTRY_AFTER_TP50 = True
REENTRY_AFTER_CLOSE_SECONDS = 2 * 60 * 60  # 2 candles H1
REENTRY_COOLDOWN_SECONDS = 60 * 60

# Proteção para não checar stop logo após BE/Trailing.
PROTECTION_SECONDS = 300

# Central Quant: evita sinais antigos após deploy/restart.
STARTUP_SIGNAL_GRACE_SECONDS = int(os.environ.get("MEME_STARTUP_SIGNAL_GRACE_SECONDS", "600"))
SERVICE_STARTED_TS = time.time()
STARTUP_MSG_COOLDOWN_SECONDS = int(os.environ.get("MEME_STARTUP_MSG_COOLDOWN_SECONDS", "3600"))

WATCHDOG_CHECK_SECONDS = int(os.environ.get("MEME_WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("MEME_WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("MEME_WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))


# Relatório mensal automático: dia 01, consolidando mês anterior.
MONTHLY_SUMMARY_DAY = 1
MONTHLY_SUMMARY_HOUR = 8
MONTHLY_SUMMARY_MINUTE = 5

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

redis = Redis(
    url=UPSTASH_REDIS_REST_URL,
    token=UPSTASH_REDIS_REST_TOKEN
)

ultimo_candle_h1 = {}
ultimo_relatorio_hora = None

HEALTH = {
    "started_at": None,
    "last_scanner_run": None,
    "last_management_run": None,
    "last_success": None,
    "last_error": None,
    "last_warning": None,
    "last_watchdog_alert": None,
    "last_watchdog_alert_ts": 0,
    "watchdog_last_check": None,
    "watchdog_last_status": "OK",
    "last_watchlist_count": 0,
    "last_signals_sent": 0,
    "last_positions_count": 0,
    "watchlist_total": 0,
    "watchlist_valid": 0,
    "watchlist_invalid": [],
    "last_invalid_watchlist_check": None
}




def run_thread_guarded(nome, target):
    while True:
        try:
            target()
            break
        except Exception as e:
            try:
                HEALTH["last_error"] = f"Thread {nome} travou: {e}"
            except Exception:
                pass
            print(f"ERRO FATAL THREAD MEME {nome}: {e}")
            time.sleep(10)

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


def carregar_watchlist():
    candidatos = [WATCHLIST_FILE]
    for item in ["watchlists/meme.json", "watchlist_meme.json", "watchlist.json"]:
        if item not in candidatos:
            candidatos.append(item)

    for arquivo in candidatos:
        try:
            with open(arquivo, "r") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        except Exception:
            pass

    print("ERRO WATCHLIST: nenhum arquivo válido encontrado para Meme Hunter")
    return []


def validar_watchlist_bingx(watchlist, avisar_telegram=False):
    """
    Valida a watchlist contra os mercados reais carregados pela BingX/CCXT.
    Ativos inválidos são ignorados para não quebrar o scanner.
    """
    validos = []
    invalidos = []

    try:
        markets = safe_load_markets()
    except Exception as e:
        print("ERRO AO CARREGAR MERCADOS BINGX:", e)
        HEALTH["watchlist_total"] = len(watchlist)
        HEALTH["watchlist_valid"] = len(watchlist)
        HEALTH["watchlist_invalid"] = []
        HEALTH["last_invalid_watchlist_check"] = data_hora_sp_str()
        HEALTH["last_warning"] = f"Erro load_markets BingX: {e}"
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
            + "\n\n"
            "Eles serão ignorados pelo scanner.\n"
            "Confira se o contrato usa prefixo, exemplo: 1000BONK/USDT:USDT."
        )

        print(msg)

        if avisar_telegram:
            try:
                safe_send_telegram(msg)
            except Exception as e:
                print("ERRO AO AVISAR WATCHLIST INVÁLIDA:", e)

    return validos


# ====================================================
# CAMADA DE RESILIÊNCIA API (CCXT SAFE FETCH)
# ====================================================

def safe_fetch_ohlcv(symbol, timeframe, limit, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso MEME OHLCV ({attempt+1}/{max_retries}) {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso MEME OHLCV genérico ({attempt+1}/{max_retries}) {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)
    HEALTH["last_warning"] = f"Falha OHLCV {symbol} {timeframe} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return []

def safe_fetch_ticker(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ticker(symbol)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso MEME Ticker ({attempt+1}/{max_retries}) {symbol}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso MEME Ticker genérico ({attempt+1}/{max_retries}) {symbol}: {e}")
            time.sleep(2 ** attempt)
    HEALTH["last_warning"] = f"Falha Ticker {symbol} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return None

def safe_load_markets(max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.load_markets()
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso MEME load_markets ({attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso MEME load_markets genérico ({attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
    HEALTH["last_warning"] = "Falha ao carregar markets da exchange após tentativas"
    print(HEALTH["last_warning"])
    return None


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

def redis_get_str(key, padrao=None):
    try:
        data = redis.get(key)
        if data is None:
            return padrao
        return data if isinstance(data, str) else str(data)
    except Exception as e:
        print(f"ERRO REDIS GET STR {key}:", e)
        return padrao

def redis_set_str(key, value):
    try:
        redis.set(key, str(value))
    except Exception as e:
        print(f"ERRO REDIS SET STR {key}:", e)


def carregar_posicoes():
    return redis_get_json(POSITIONS_KEY, {})


def salvar_posicoes(dados):
    redis_set_json(POSITIONS_KEY, dados)


def carregar_sinais():
    return redis_get_json(SIGNALS_KEY, {})


def salvar_sinais(dados):
    redis_set_json(SIGNALS_KEY, dados)


def carregar_bloqueios_reentrada():
    return redis_get_json(REENTRY_BLOCK_KEY, {})


def salvar_bloqueios_reentrada(dados):
    redis_set_json(REENTRY_BLOCK_KEY, dados)


def carregar_trades():
    return redis_get_json(TRADES_KEY, [])


def carregar_monthly_summary_sent():
    return redis_get_json(MONTHLY_SUMMARY_KEY, {})


def salvar_monthly_summary_sent(dados):
    redis_set_json(MONTHLY_SUMMARY_KEY, dados)



def salvar_trades(dados):
    redis_set_json(TRADES_KEY, dados)


def carregar_monitor_be():
    dados = redis_get_json(BE_MONITOR_KEY, [])
    if isinstance(dados, list):
        return dados
    return []


def salvar_monitor_be(dados):
    if not isinstance(dados, list):
        dados = []
    redis_set_json(BE_MONITOR_KEY, dados)


def carregar_poi_cooldown():
    return redis_get_json(POI_COOLDOWN_KEY, {})


def salvar_poi_cooldown(dados):
    redis_set_json(POI_COOLDOWN_KEY, dados)


def carregar_early_cooldown():
    return redis_get_json(EARLY_COOLDOWN_KEY, {})


def salvar_early_cooldown(dados):
    redis_set_json(EARLY_COOLDOWN_KEY, dados)


def early_em_cooldown(symbol, side):
    dados = carregar_early_cooldown()
    chave = f"{symbol}_{side}"
    ultimo = float(dados.get(chave, 0))
    return time.time() - ultimo < EARLY_COOLDOWN_SECONDS


def marcar_early_cooldown(symbol, side):
    dados = carregar_early_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = time.time()

    if len(dados) > 300:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-300:])

    salvar_early_cooldown(dados)


def registrar_evento_trade(evento):
    trades = carregar_trades()
    trades.append(evento)
    if len(trades) > 1000:
        trades = trades[-1000:]
    salvar_trades(trades)


# ====================================================
# FUNIL MEME - DIAGNÓSTICO
# ====================================================

FUNIL_PADRAO = {
    "ativos_analisados": 0,
    "breakout_detectados": 0,
    "early_hunter_detectados": 0,
    "reprovados_volume": 0,
    "reprovados_volume_financeiro": 0,
    "reprovados_rsi": 0,
    "reprovados_bb": 0,
    "reprovados_h4": 0,
    "reprovados_risco": 0,
    "reprovados_score": 0,
    "reprovados_spike": 0,
    "reprovados_posicao_ativa": 0,
    "startup_guard_ignorados": 0,
    "sinais_enviados": 0,
}

def carregar_funil():
    dados = redis_get_json(FUNNEL_KEY, {})
    return dados if isinstance(dados, dict) else {}

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
        print("ERRO REGISTRAR FUNIL MEME:", e)

def carregar_early_hunter_cooldown():
    dados = redis_get_json(EARLY_HUNTER_COOLDOWN_KEY, {})
    return dados if isinstance(dados, dict) else {}

def salvar_early_hunter_cooldown(dados):
    redis_set_json(EARLY_HUNTER_COOLDOWN_KEY, dados)

def early_hunter_em_cooldown(symbol, side):
    dados = carregar_early_hunter_cooldown()
    chave = f"{symbol}_{side}"
    ultimo = float(dados.get(chave, 0) or 0)
    return time.time() - ultimo < EARLY_HUNTER_COOLDOWN_SECONDS

def marcar_early_hunter_cooldown(symbol, side):
    dados = carregar_early_hunter_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = time.time()
    if len(dados) > 500:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-500:])
    salvar_early_hunter_cooldown(dados)

def quote_volume_h1(candle):
    try:
        return float(candle.get("close", 0)) * float(candle.get("volume", 0))
    except Exception:
        return 0.0

def passa_volume_financeiro(candle):
    if not USE_MIN_QUOTE_VOLUME_FILTER:
        return True
    return quote_volume_h1(candle) >= MIN_QUOTE_VOLUME_H1_USDT


def existe_posicao_ativa(symbol):
    posicoes = carregar_posicoes()
    return symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO"


def pnl_pct(side, entry, price):
    if side == "LONG":
        return ((price - entry) / entry) * 100
    return ((entry - price) / entry) * 100


def check_bool(valor):
    return "✅" if valor else "❌"


def fmt_risco(valor):
    try:
        return f"{float(valor):.2f}".replace(".", ",")
    except Exception:
        return str(valor)



def classificar_hunter_quality(score):
    try:
        score = int(score)
    except Exception:
        return "N/A"
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"

def quality_key_from_score(score):
    return f"Q_{classificar_hunter_quality(score).replace('+', 'PLUS')}"

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


def quote_volume_h1(candle):
    try:
        return float(candle.get("close", 0)) * float(candle.get("volume", 0))
    except Exception:
        return 0.0

def passa_volume_financeiro(candle):
    if not USE_MIN_QUOTE_VOLUME_FILTER:
        return True
    return quote_volume_h1(candle) >= MIN_QUOTE_VOLUME_H1_USDT

def estado_txt(state):
    if state == 1:
        return "BULLISH ✅"
    if state == -1:
        return "BEARISH ✅"
    return "NEUTRO ⚠️"



def normalizar_texto(msg):
    """
    Garante string UTF-8 limpa para Telegram.
    Corrige casos comuns de texto UTF-8 interpretado como Latin-1.
    """
    if msg is None:
        return ""

    msg = str(msg)

    # Corrige mojibake comum: RobÃ´, âœ…, ðŸ...
    try:
        if "Ã" in msg or "â" in msg or "ðŸ" in msg:
            msg = msg.encode("latin1").decode("utf-8")
    except Exception:
        pass

    return msg

def enviar_texto(chat_id, msg):
    try:
        msg = normalizar_texto(msg)
        payload = {
            "chat_id": chat_id,
            "text": msg
        }

        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20
        )
    except Exception as e:
        print("Erro ao responder Telegram:", e)



def safe_send_telegram(msg):
    msg = normalizar_texto(msg)
    if not TOKEN or not CHAT_ID:
        print(msg)
        return
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20
        )
    except Exception as e:
        print("ERRO TELEGRAM MEME:", e)




def mes_anterior_ref():
    hoje = agora_sp()
    primeiro_mes_atual = hoje.replace(day=1)
    ultimo_mes_anterior = primeiro_mes_atual - timedelta(days=1)
    return ultimo_mes_anterior.strftime("%Y-%m"), ultimo_mes_anterior.strftime("%m/%Y")


def montar_resumo_mensal():
    mes_ref, mes_txt = mes_anterior_ref()
    trades = carregar_trades()

    do_mes = [
        t for t in trades
        if str(t.get("date", "")).startswith(mes_ref)
    ]

    entries = [t for t in do_mes if t.get("event") == "ENTRY"]
    pois = [t for t in do_mes if t.get("event") == "POI"]
    exits = [t for t in do_mes if t.get("event") in ["EXIT", "SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in do_mes if t.get("event") == "TP50"]
    trails = [t for t in do_mes if t.get("event") == "TRAILING"]

    longs = [t for t in entries if t.get("side") == "LONG"]
    shorts = [t for t in entries if t.get("side") == "SHORT"]
    earlys = [t for t in entries if t.get("signal_type") == "EARLY"]
    recuperados = [t for t in entries if t.get("signal_type") == "RECUPERADO"]
    reentries = [t for t in entries if t.get("signal_type") == "REENTRY"]

    wins = []
    bes = []
    losses = []
    pnl_total = 0.0
    melhor = None
    pior = None

    for t in exits:
        try:
            pnl = float(t.get("pnl", t.get("pnl_pct", t.get("result_pct", 0))))
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

    melhor_txt = "N/A"
    if melhor:
        melhor_txt = f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('_pnl_calc', 0))}"

    pior_txt = "N/A"
    if pior:
        pior_txt = f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('_pnl_calc', 0))}"

    msg = (
        f"📊 RESUMO MENSAL\n"
        f"Mês: {mes_txt}\n\n"
        f"Sinais H1: {len(entries)}\n"
        f"LONG: {len(longs)}\n"
        f"SHORT: {len(shorts)}\n"
        f"EARLY: {len(earlys)}\n"
        f"RECUPERADO: {len(recuperados)}\n"
        f"REENTRY: {len(reentries)}\n"
        f"POIs H1: {len(pois)}\n\n"
        f"Trades encerrados: {fechados}\n"
        f"Wins: {len(wins)}\n"
        f"Breakeven: {len(bes)}\n"
        f"Loss: {len(losses)}\n"
        f"Win rate: {win_rate:.2f}%\n"
        f"Win rate sem BE: {win_rate_sem_be:.2f}%\n\n"
        f"TP50 atingidos: {len(tp50s)}\n"
        f"Trailings atualizados: {len(trails)}\n\n"
        f"PnL realizado:\n"
        f"{fmt_pct(pnl_total)}\n\n"
        f"Melhor trade:\n"
        f"{melhor_txt}\n\n"
        f"Pior trade:\n"
        f"{pior_txt}"
    )

    return msg


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


def montar_health_tecnico():
    try:
        posicoes = carregar_posicoes()
        abertas = [
            p for p in posicoes.values()
            if p.get("status") != "ENCERRADO"
        ]
        HEALTH["last_positions_count"] = len(abertas)
    except Exception:
        abertas = []

    positions_open = HEALTH.get("last_positions_count", 0)
    usage_pct = (positions_open / MAX_OPEN_POSITIONS * 100) if MAX_OPEN_POSITIONS else 0

    payload = {
        "ok": HEALTH.get("last_error") is None,
        "uptime_horas": calcular_uptime_horas(),
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "watchlist_file": WATCHLIST_FILE,
        "watchlist_total": HEALTH.get("watchlist_total", HEALTH.get("last_watchlist_count", 0)),
        "watchlist_valida": HEALTH.get("watchlist_valid", HEALTH.get("last_watchlist_count", 0)),
        "watchlist_invalida": len(HEALTH.get("watchlist_invalid", [])),
        "watchlist_invalidos": HEALTH.get("watchlist_invalid", []),
        "last_invalid_watchlist_check": HEALTH.get("last_invalid_watchlist_check"),
        "positions_open": positions_open,
        "positions_limit": MAX_OPEN_POSITIONS,
        "positions_usage_pct": round(usage_pct, 2),
        "can_open_new_positions": positions_open < MAX_OPEN_POSITIONS,
        "last_signals_sent": HEALTH.get("last_signals_sent", 0),
        "poi_cooldown_seconds": POI_COOLDOWN_SECONDS,
        "reentry_enabled": ENABLE_REENTRY_AFTER_TP50,
        "reentry_after_close_seconds": REENTRY_AFTER_CLOSE_SECONDS,
        "max_risk": MAX_RISK_H1,
        "use_max_risk_filter": USE_MAX_RISK_FILTER,
        "trendpro_elite_filter": ENABLE_TRENDPRO_ELITE_FILTER,
        "elite_threshold": ELITE_THRESHOLD,
        "elite_min_adx_h4": ELITE_MIN_ADX_H4,
        "require_high_volume": REQUIRE_HIGH_VOLUME,
        "require_bb_expanding": REQUIRE_BB_EXPANDING,
        "early_threshold": EARLY_THRESHOLD,
        "early_min_adx_h4": EARLY_MIN_ADX_H4,
        "poi_threshold": POI_THRESHOLD,
        "poi_min_adx_h4": POI_MIN_ADX_H4,
        "enable_recovered_signal": ENABLE_RECOVERED_SIGNAL,
        "auto_position_report": ENABLE_AUTO_POSITION_REPORT,
        "meme_breakout_strategy": ENABLE_MEME_BREAKOUT_STRATEGY,
        "legacy_trend_entries": ENABLE_LEGACY_TREND_ENTRIES,
        "poi_alerts": ENABLE_POI_ALERTS,
        "meme_min_score": MEME_MIN_SCORE,
        "meme_volume_mult": MEME_VOLUME_MULT,
        "meme_breakout_lookback": MEME_BREAKOUT_LOOKBACK,
        "be_trigger_r": BE_TRIGGER_R,
        "telegram_private_configured": bool(TOKEN and CHAT_ID),
        "early_hunter_enabled": ENABLE_EARLY_HUNTER,
        "early_hunter_score_min": EARLY_HUNTER_SCORE_MIN,
        "early_hunter_distance_to_breakout_atr": EARLY_HUNTER_DISTANCE_TO_BREAKOUT_ATR,
        "use_min_quote_volume_filter": USE_MIN_QUOTE_VOLUME_FILTER,
        "min_quote_volume_h1_usdt": MIN_QUOTE_VOLUME_H1_USDT,
        "startup_signal_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
        "startup_signal_guard_active": startup_signal_guard_active(),
        "startup_guard_restante_segundos": startup_guard_restante_segundos(),
        "watchdog_status": HEALTH.get("watchdog_last_status", "OK"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "funnel_today": funil_hoje()
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def contar_posicoes_ativas():
    try:
        posicoes = carregar_posicoes()
        abertas = [
            p for p in posicoes.values()
            if p.get("status") != "ENCERRADO"
        ]
        return len(abertas)
    except Exception:
        return 0


def limite_posicoes_atingido():
    return contar_posicoes_ativas() >= MAX_OPEN_POSITIONS


def origem_trade_txt(p):
    origem = (
        p.get("signal_type")
        or p.get("origin")
        or p.get("origem")
        or "NORMAL"
    )

    if origem == "NORMAL":
        return "NORMAL"
    if origem == "RECUPERADO":
        return "RECUPERADO"
    if origem in ["EARLY", "EARLY"]:
        return "EARLY"
    if origem == "REENTRY":
        return "REENTRY"
    if origem == "POI":
        return "POI"

    return str(origem)

# ====================================================
# INDICADORES
# ====================================================

def calcular_supertrend_df(df, period=10, multiplier=3.5):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
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
        final_upper.iloc[i] = (
            upperband.iloc[i]
            if upperband.iloc[i] < final_upper.iloc[i - 1]
            or close.iloc[i - 1] > final_upper.iloc[i - 1]
            else final_upper.iloc[i - 1]
        )

        final_lower.iloc[i] = (
            lowerband.iloc[i]
            if lowerband.iloc[i] > final_lower.iloc[i - 1]
            or close.iloc[i - 1] < final_lower.iloc[i - 1]
            else final_lower.iloc[i - 1]
        )

        if direction.iloc[i - 1] == -1:
            direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        else:
            direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1

        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]

    return supertrend, direction


def calcular_adx(df, period=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        [u if u > d and u > 0 else 0 for u, d in zip(up_move, down_move)],
        index=df.index
    )
    minus_dm = pd.Series(
        [d if d > u and d > 0 else 0 for u, d in zip(up_move, down_move)],
        index=df.index
    )

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




def marcar_spikes(df):
    """
    Marca candles com range/pavio anormal em relação ao ATR.
    Isso ajuda a evitar que um candle com dado ruim gere stop, ATR ou sinal falso.
    """
    df = df.copy()

    if not ENABLE_SPIKE_FILTER:
        df["spike_suspeito"] = False
        return df

    if "atr14" not in df.columns:
        df["atr14"] = calcular_atr(df, ATR_LEN)

    candle_range = (df["high"].astype(float) - df["low"].astype(float)).abs()
    candle_body = (df["close"].astype(float) - df["open"].astype(float)).abs()
    atr = df["atr14"].astype(float)

    spike_range = candle_range > (atr * SPIKE_RANGE_ATR_MULT)
    spike_body = candle_body > (atr * SPIKE_BODY_ATR_MULT)

    df["spike_suspeito"] = (spike_range | spike_body).fillna(False)

    return df


def preparar_df(df):
    df = df.copy()

    df["ema9"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=EMA_MID, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=EMA200, adjust=False).mean()
    df["atr14"] = calcular_atr(df, ATR_LEN)
    df = marcar_spikes(df)

    _, st_dir = calcular_supertrend_df(
        df,
        period=SUPERTREND_PERIOD,
        multiplier=SUPERTREND_FACTOR
    )
    df["supertrend_dir"] = st_dir

    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["volume_ok"] = df["volume"] > df["vol_avg20"]
    df["vol_ratio"] = df["volume"] / df["vol_avg20"]

    # RSI 14 para a lógica Meme Hunter PRO v2.
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    # Aceleração curta da EMA9.
    df["ema9_slope_pct"] = ((df["ema9"] - df["ema9"].shift(3)) / df["ema9"].shift(3)) * 100

    bb_basis = df["close"].rolling(20).mean()
    bb_dev = df["close"].rolling(20).std()
    bb_upper = bb_basis + 2 * bb_dev
    bb_lower = bb_basis - 2 * bb_dev
    bb_width = (bb_upper - bb_lower) / bb_basis
    df["bb_width"] = bb_width
    df["bb_width_avg"] = bb_width.rolling(100).mean()
    df["bb_ok"] = bb_width > df["bb_width_avg"]

    adx, plus_di, minus_di = calcular_adx(df, ADX_LEN)
    df["adx"] = adx
    df["plus_di"] = plus_di
    df["minus_di"] = minus_di
    df["adx_ok"] = adx >= ADX_MIN

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


def nascimento_sinal(df):
    candle = df.iloc[-2]
    prev = df.iloc[-3]

    state_now = estado_tendencia(candle)
    state_prev = estado_tendencia(prev)

    if state_now == 1 and state_prev != 1:
        return "LONG"
    if state_now == -1 and state_prev != -1:
        return "SHORT"
    return None


def calcular_stop_tp(signal, entry, df):
    candle = df.iloc[-2]
    atr = float(candle["atr14"])

    ultimos = df.iloc[-(SWING_LEN + 1):-1]

    if signal == "LONG":
        swing_low = float(ultimos["low"].min())
        sl = swing_low - atr * ATR_BUFFER_STOP
        risk_abs = abs(entry - sl)

        tp50_dist = max(
            risk_abs * TP50_R,
            atr * TP50_MIN_ATR
        )

        tp50 = entry + tp50_dist

    else:
        swing_high = float(ultimos["high"].max())
        sl = swing_high + atr * ATR_BUFFER_STOP
        risk_abs = abs(sl - entry)

        tp50_dist = max(
            risk_abs * TP50_R,
            atr * TP50_MIN_ATR
        )

        tp50 = entry - tp50_dist

    return float(sl), float(tp50), float(risk_abs)



def calcular_qualidade(side, h4_state, h1_candle):
    pontos = 0.0

    if side == "LONG" and h4_state == 1:
        pontos += 2
    elif side == "SHORT" and h4_state == -1:
        pontos += 2

    if bool(h1_candle.get("volume_ok", False)):
        pontos += 1

    if bool(h1_candle.get("bb_ok", False)):
        pontos += 1

    if bool(h1_candle.get("adx_ok", False)):
        pontos += 1

    if pontos >= 4:
        return pontos, "ALTA 🟢"
    if pontos >= 2:
        return pontos, "MÉDIA 🟡"
    return pontos, "BAIXA 🔴"


def calcular_signal_score(s):
    """
    Score informativo do futuro Elite PRO.
    Não altera entrada, não bloqueia sinal e não muda a gestão.
    Serve para medir quais sinais do Trend PRO têm confluência mais forte.
    """
    score = 0

    try:
        h4_state = int(s.get("h4_state", 0))
        h1_state = int(s.get("h1_state", 0))
    except Exception:
        h4_state = 0
        h1_state = 0

    # Alinhamento principal H4/H1.
    if h4_state != 0 and h1_state == h4_state:
        score += 25

    # Força da tendência no H4.
    try:
        adx_h4 = float(s.get("adx_h4", 0))
        if adx_h4 >= 40:
            score += 25
        elif adx_h4 >= 30:
            score += 15
        elif adx_h4 >= 20:
            score += 8
    except Exception:
        pass

    # Força da tendência no H1.
    try:
        adx_h1 = float(s.get("adx_h1", 0))
        if adx_h1 >= 30:
            score += 10
        elif adx_h1 >= 20:
            score += 5
    except Exception:
        pass

    # Volume e expansão de volatilidade.
    if bool(s.get("volume_ok", False)):
        score += 15

    if bool(s.get("bb_ok", False)):
        score += 10

    # Risco menor recebe mais pontos.
    try:
        risco = float(s.get("risk_pct", 99))
        if risco <= 1.0:
            score += 15
        elif risco <= 1.5:
            score += 10
        elif risco <= 2.0:
            score += 5
    except Exception:
        pass

    # Qualidade já calculada pelo Trend PRO.
    qualidade = str(s.get("qualidade", ""))
    if "ALTA" in qualidade:
        score += 10
    elif "MÉDIA" in qualidade:
        score += 5

    return min(int(score), 100)


def adicionar_signal_score(s):
    score = calcular_signal_score(s)
    s["signal_score"] = score
    s["elite_candidate"] = score >= ELITE_THRESHOLD
    return s



def passa_filtro_trendpro_elite(
    s,
    threshold=None,
    min_adx_h4=None,
    require_high_volume=None,
    require_bb_expanding=None,
    label="SINAL"
):
    """
    Filtro central do Trend PRO Elite.
    Bloqueia sinais fracos antes de registrar posição, enviar Telegram ou atualizar POI.
    """

    if not ENABLE_TRENDPRO_ELITE_FILTER:
        return True, "Filtro Elite desligado"

    if threshold is None:
        threshold = ELITE_THRESHOLD

    if min_adx_h4 is None:
        min_adx_h4 = ELITE_MIN_ADX_H4

    if require_high_volume is None:
        require_high_volume = REQUIRE_HIGH_VOLUME

    if require_bb_expanding is None:
        require_bb_expanding = REQUIRE_BB_EXPANDING

    try:
        score = int(s.get("signal_score", calcular_signal_score(s)))
    except Exception:
        score = 0

    try:
        adx_h4 = float(s.get("adx_h4", 0))
    except Exception:
        adx_h4 = 0.0

    volume_ok = bool(s.get("volume_ok", False))
    bb_ok = bool(s.get("bb_ok", False))

    if score < threshold:
        return False, f"{label}: Score abaixo do mínimo: {score}/{threshold}"

    if adx_h4 < min_adx_h4:
        return False, f"{label}: ADX H4 abaixo do mínimo: {adx_h4:.2f}/{min_adx_h4:.2f}"

    if require_high_volume and not volume_ok:
        return False, f"{label}: Volume H1 baixo"

    if require_bb_expanding and not bb_ok:
        return False, f"{label}: Bollinger H1 comprimindo"

    return True, f"{label}: Aprovado no filtro Trend PRO Elite"



# ====================================================
# MEME HUNTER PRO V2 - BREAKOUT + VOLUME + MOMENTUM
# ====================================================

def calcular_meme_breakout_score(s):
    """
    Score específico do Meme Hunter PRO v2.
    Prioriza volume anormal, rompimento real e expansão de volatilidade.
    """
    score = 0

    try:
        vol_ratio = float(s.get("vol_ratio", 0))
    except Exception:
        vol_ratio = 0.0

    if vol_ratio >= MEME_VOLUME_MULT:
        score += 25
    if vol_ratio >= MEME_VOLUME_EXTREME_MULT:
        score += 20

    if bool(s.get("breakout_ok", False)):
        score += 20

    if bool(s.get("bb_ok", False)):
        score += 15

    try:
        ema9_slope = float(s.get("ema9_slope_pct", 0))
        if s.get("side") == "LONG" and ema9_slope > 0:
            score += 10
        elif s.get("side") == "SHORT" and ema9_slope < 0:
            score += 10
    except Exception:
        pass

    try:
        adx_h4 = float(s.get("adx_h4", 0))
        if adx_h4 >= 25:
            score += 10
        elif adx_h4 >= MEME_MIN_ADX_H4:
            score += 5
    except Exception:
        pass

    try:
        rsi = float(s.get("rsi14", 50))
        if s.get("side") == "LONG" and rsi >= MEME_RSI_LONG:
            score += 10
        elif s.get("side") == "SHORT" and rsi <= MEME_RSI_SHORT:
            score += 10
    except Exception:
        pass

    return min(int(score), 100)


def detectar_breakout_meme(symbol):
    """
    Entrada principal do Meme Hunter PRO v2.

    LONG:
    - EMA9 > EMA21 > EMA50 no H1.
    - H4 não pode estar claramente contra.
    - Volume H1 >= 2x média 20.
    - Fechamento rompe máxima dos 20 candles anteriores.
    - Bollinger expandindo.
    - RSI com momentum.

    SHORT: lógica inversa.
    """
    if not ENABLE_MEME_BREAKOUT_STRATEGY:
        return None
    registrar_funil("ativos_analisados")

    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    candle = df_h1.iloc[-2]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        registrar_funil("reprovados_spike")
        print(f"BREAKOUT MEME IGNORADO POR CANDLE SUSPEITO: {nome_limpo(symbol)}")
        return None

    h4_state = estado_tendencia(candle_h4)
    h1_state = estado_tendencia(candle)

    try:
        adx_h4 = float(candle_h4.get("adx", 0))
    except Exception:
        adx_h4 = 0.0

    if adx_h4 < MEME_MIN_ADX_H4:
        registrar_funil("reprovados_h4")
        return None

    close = float(candle["close"])
    ema9 = float(candle["ema9"])
    ema21 = float(candle["ema21"])
    ema50 = float(candle["ema50"])
    rsi = float(candle.get("rsi14", 50))
    vol_ratio = float(candle.get("vol_ratio", 0))
    bb_ok = bool(candle.get("bb_ok", False))
    ema9_slope_pct = float(candle.get("ema9_slope_pct", 0))

    if vol_ratio < MEME_VOLUME_MULT:
        registrar_funil("reprovados_volume")
        return None

    if not passa_volume_financeiro(candle):
        registrar_funil("reprovados_volume_financeiro")
        return None

    if MEME_REQUIRE_BB_EXPANDING and not bb_ok:
        registrar_funil("reprovados_bb")
        return None

    # Evita comprar muito longe da EMA9 depois da explosão já esticada.
    try:
        dist_ema9_pct = ((close - ema9) / ema9) * 100
    except Exception:
        dist_ema9_pct = 999.0

    janela = df_h1.iloc[-(MEME_BREAKOUT_LOOKBACK + 2):-2]
    if len(janela) < MEME_BREAKOUT_LOOKBACK:
        return None

    max_prev = float(janela["high"].max())
    min_prev = float(janela["low"].min())

    long_ema_stack = ema9 > ema21 > ema50
    short_ema_stack = ema9 < ema21 < ema50

    long_breakout = close > max_prev
    short_breakout = close < min_prev

    signal = None

    if (
        long_breakout and
        rsi >= MEME_RSI_LONG and
        h4_state != -1 and
        (not MEME_REQUIRE_H1_EMA_STACK or long_ema_stack) and
        dist_ema9_pct <= MEME_MAX_DIST_EMA9_PCT
    ):
        signal = "LONG"

    if (
        short_breakout and
        rsi <= MEME_RSI_SHORT and
        h4_state != 1 and
        (not MEME_REQUIRE_H1_EMA_STACK or short_ema_stack) and
        abs(dist_ema9_pct) <= MEME_MAX_DIST_EMA9_PCT
    ):
        signal = "SHORT"

    if not signal:
        registrar_funil("reprovados_rsi")
        return None

    entry = close
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        registrar_funil("reprovados_risco")
        print(f"BREAKOUT MEME IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle)

    sinal = {
        "type": "SIGNAL",
        "signal_type": "BREAKOUT",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": signal,
        "side": signal,
        "timestamp": int(candle["time"]),
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": h1_state,
        "adx_h4": adx_h4,
        "adx_h1": float(candle.get("adx", 0)),
        "volume_ok": True,
        "bb_ok": bb_ok,
        "qualidade_pontos": pontos,
        "qualidade": qualidade,
        "vol_ratio": vol_ratio,
        "rsi14": rsi,
        "ema9_slope_pct": ema9_slope_pct,
        "breakout_ok": True,
        "breakout_lookback": MEME_BREAKOUT_LOOKBACK,
        "breakout_ref": max_prev if signal == "LONG" else min_prev,
    }

    meme_score = calcular_meme_breakout_score(sinal)
    sinal["signal_score"] = meme_score
    sinal["hunter_quality"] = classificar_hunter_quality(meme_score)
    sinal["meme_score"] = meme_score
    sinal["hunter_quality"] = classificar_hunter_quality(meme_score)
    sinal["elite_candidate"] = meme_score >= MEME_MIN_SCORE

    if meme_score < MEME_MIN_SCORE:
        registrar_funil("reprovados_score")
        print(f"BREAKOUT MEME BLOQUEADO POR SCORE: {nome_limpo(symbol)} | {meme_score}/{MEME_MIN_SCORE}")
        return None

    registrar_funil("breakout_detectados")

    print(
        f"BREAKOUT MEME APROVADO: {nome_limpo(symbol)} | {signal} | "
        f"Score={meme_score} | Vol={vol_ratio:.2f}x | RSI={rsi:.2f} | ADX_H4={adx_h4:.2f}"
    )

    return sinal

# ====================================================
# SINAL H1 ALINHADO AO H4
# ====================================================

def analisar_sinal_h1(symbol):
    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    df_h1 = pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"])
    df_h4 = pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"])

    df_h1 = preparar_df(df_h1)
    df_h4 = preparar_df(df_h4)

    timestamp = int(df_h1.iloc[-2]["time"])
    candle_h1 = df_h1.iloc[-2]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle_h1.get("spike_suspeito", False)):
        print(f"CANDLE H1 SUSPEITO IGNORADO: {nome_limpo(symbol)}")
        return None, df_h1, df_h4

    h4_state = estado_tendencia(candle_h4)
    h1_state = estado_tendencia(candle_h1)

    print(
        f"{nome_limpo(symbol)} | "
        f"H4={h4_state} | H1={h1_state} | "
        f"ADX_H4={float(candle_h4.get('adx', 0)):.2f} | "
        f"Volume_H1={bool(candle_h1.get('volume_ok', False))} | "
        f"BB_H1={bool(candle_h1.get('bb_ok', False))}"
    )

    signal = nascimento_sinal(df_h1)
    signal_type = "NORMAL"

    if signal == "LONG" and h4_state != 1:
        signal = None
    elif signal == "SHORT" and h4_state != -1:
        signal = None

    # SINAL RECUPERADO:
    # Se o robô iniciou depois que a tendência já nasceu, o nascimento do H1
    # pode ter acontecido horas antes.
    #
    # Para evitar entrada atrasada, o RECUPERADO só é aceito quando
    # o candle fechado toca a zona EMA9/EMA21.
    if signal is None and ENABLE_RECOVERED_SIGNAL and h4_state != 0 and h1_state == h4_state:
        ema9_h1 = float(candle_h1["ema9"])
        ema21_h1 = float(candle_h1["ema21"])
        zone_top = max(ema9_h1, ema21_h1)
        zone_bottom = min(ema9_h1, ema21_h1)

        inside_ema_zone = (
            float(candle_h1["low"]) <= zone_top and
            float(candle_h1["high"]) >= zone_bottom
        )

        recovered_confirmed = True

        if RECOVERED_REQUIRE_EMA_ZONE:
            recovered_confirmed = inside_ema_zone

        if recovered_confirmed:
            signal = "LONG" if h1_state == 1 else "SHORT"
            signal_type = "RECUPERADO"

    if not signal:
        return None, df_h1, df_h4

    entry = float(candle_h1["close"])
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        print(f"SINAL IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None, df_h1, df_h4

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle_h1)

    return adicionar_signal_score({
        "type": "SIGNAL",
        "signal_type": signal_type,
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": signal,
        "side": signal,
        "timestamp": timestamp,
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": h1_state,
        "adx_h4": float(df_h4.iloc[-2]["adx"]),
        "adx_h1": float(candle_h1["adx"]),
        "volume_ok": bool(candle_h1.get("volume_ok", False)),
        "bb_ok": bool(candle_h1.get("bb_ok", False)),
        "qualidade_pontos": pontos,
        "qualidade": qualidade
    }), df_h1, df_h4




# ====================================================
# EARLY - EMA21
# ====================================================

def detectar_early_a(symbol):
    """
    EARLY:
    - Entrada antecipada a favor do H4 e contra o pullback do H1.
    - EARLY BUY: H4 BULLISH e H1 BEARISH/contra-tendência.
    - EARLY SELL: H4 BEARISH e H1 BULLISH/contra-tendência.
    - Candle H1 fechado toca EMA21.
    - Volume H1 alto, se habilitado.
    - BUY: fecha acima da máxima do candle anterior.
    - SELL: fecha abaixo da mínima do candle anterior.
    - Não depende do H1 já estar alinhado; se H1 já alinhou, vira sinal normal.
    """

    if not ENABLE_EARLY:
        return None

    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    candle = df_h1.iloc[-2]
    prev = df_h1.iloc[-3]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"EARLY IGNORADO POR CANDLE SUSPEITO: {nome_limpo(symbol)}")
        return None

    h4_state = estado_tendencia(candle_h4)
    h1_state = estado_tendencia(candle)

    if h4_state == 0:
        return None

    # EARLY só vale quando o H1 ainda está em pullback contra o H4:
    # - H4 BULLISH + H1 BEARISH = possível EARLY BUY.
    # - H4 BEARISH + H1 BULLISH = possível EARLY SELL.
    # Se H1 já está alinhado ao H4, o sinal correto é NORMAL/ELITE, não EARLY.
    if h4_state == 1 and h1_state != -1:
        return None

    if h4_state == -1 and h1_state != 1:
        return None

    adx_h4 = float(candle_h4.get("adx", 0))
    if adx_h4 < EARLYDX_H4_MIN:
        return None

    volume_ok = bool(candle.get("volume_ok", False))
    if EARLY_REQUIRE_VOLUME and not volume_ok:
        return None

    ema21 = float(candle["ema21"])
    touched_ema21 = float(candle["low"]) <= ema21 <= float(candle["high"])

    if not touched_ema21:
        return None

    close = float(candle["close"])
    prev_high = float(prev["high"])
    prev_low = float(prev["low"])

    signal = None

    if h4_state == 1 and close > prev_high:
        signal = "LONG"

    if h4_state == -1 and close < prev_low:
        signal = "SHORT"

    if not signal:
        return None

    if early_em_cooldown(symbol, signal):
        return None

    entry = close
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        print(f"EARLY IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle)

    marcar_early_cooldown(symbol, signal)

    return adicionar_signal_score({
        "type": "EARLY",
        "signal_type": "EARLY",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": signal,
        "side": signal,
        "timestamp": int(candle["time"]),
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": h1_state,
        "adx_h4": adx_h4,
        "adx_h1": float(candle.get("adx", 0)),
        "volume_ok": volume_ok,
        "bb_ok": bool(candle.get("bb_ok", False)),
        "qualidade_pontos": pontos,
        "qualidade": qualidade
    })


# ====================================================
# POI H1
# ====================================================

def poi_em_cooldown(symbol, side):
    dados = carregar_poi_cooldown()
    chave = f"{symbol}_{side}"
    ultimo = float(dados.get(chave, 0))
    return time.time() - ultimo < POI_COOLDOWN_SECONDS


def marcar_poi_cooldown(symbol, side):
    dados = carregar_poi_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = time.time()

    if len(dados) > 300:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-300:])

    salvar_poi_cooldown(dados)


def detectar_poi(symbol, posicao):
    """
    POI H1:
    - Respeita cooldown de 1h.
    - Não envia POI logo após entrada/RECUPERADO.
    - Só envia novo POI se o preço tiver SAÍDO da zona EMA9/EMA21
      depois do último POI e depois RETORNADO para a zona.
    - Respeita risco máximo se USE_MAX_RISK_FILTER=True.
    """

    # Evita POI imediatamente após abrir/recuperar uma posição.
    try:
        active_since = float(posicao.get("active_since", posicao.get("created_at", 0)))
        if time.time() - active_since < POI_AFTER_ENTRY_COOLDOWN_SECONDS:
            return None
    except Exception:
        pass

    if poi_em_cooldown(symbol, posicao["side"]):
        return None

    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    candle = df_h1.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"POI IGNORADO POR CANDLE SUSPEITO: {nome_limpo(symbol)}")
        return None

    h4_state = estado_tendencia(df_h4.iloc[-2])
    h1_state = estado_tendencia(candle)

    side = posicao["side"]

    if side == "LONG" and not (h4_state == 1 and h1_state == 1):
        return None

    if side == "SHORT" and not (h4_state == -1 and h1_state == -1):
        return None

    ema9 = float(candle["ema9"])
    ema21 = float(candle["ema21"])
    poi_top = max(ema9, ema21)
    poi_bottom = min(ema9, ema21)

    inside_zone = (
        float(candle["low"]) <= poi_top and
        float(candle["high"]) >= poi_bottom
    )

    posicoes = carregar_posicoes()
    p_atual = posicoes.get(symbol, posicao)

    last_poi_zone = bool(p_atual.get("last_poi_zone", False))

    # Se saiu da zona, libera um novo POI futuro.
    if not inside_zone:
        if last_poi_zone:
            p_atual["last_poi_zone"] = False
            posicoes[symbol] = p_atual
            salvar_posicoes(posicoes)
        return None

    # Se ainda está na zona desde o último POI, não repete mensagem.
    if inside_zone and last_poi_zone:
        return None

    if side == "LONG":
        confirmed = float(candle["close"]) > ema21
    else:
        confirmed = float(candle["close"]) < ema21

    if not confirmed:
        return None

    entry = float(candle["close"])
    sl = float(p_atual["sl"])
    risk_abs = abs(entry - sl)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        print(f"POI IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None

    atr = float(candle["atr14"])

    tp50_dist = max(
        risk_abs * TP50_R,
        atr * TP50_MIN_ATR
    )

    if side == "LONG":
        tp50 = entry + tp50_dist
    else:
        tp50 = entry - tp50_dist

    marcar_poi_cooldown(symbol, side)

    # Marca que já houve POI nesta permanência dentro da zona.
    p_atual["last_poi_zone"] = True
    posicoes[symbol] = p_atual
    salvar_posicoes(posicoes)

    pontos, qualidade = calcular_qualidade(side, h4_state, candle)

    return adicionar_signal_score({
        "type": "POI",
        "signal_type": "POI",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": int(candle["time"]),
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": h1_state,
        "adx_h4": float(df_h4.iloc[-2]["adx"]),
        "adx_h1": float(candle.get("adx", 0)),
        "volume_ok": bool(candle.get("volume_ok", False)),
        "bb_ok": bool(candle.get("bb_ok", False)),
        "qualidade_pontos": pontos,
        "qualidade": qualidade
    })




# ====================================================
# REENTRY H1 APÓS TP50
# ====================================================

def detectar_reentry(symbol, posicao_fechada):
    """
    REENTRY:
    - Só vale para trade encerrado que atingiu TP50.
    - Não vale para SL antes do TP50.
    - Aguarda pelo menos REENTRY_AFTER_CLOSE_SECONDS após fechamento.
    - Exige H4/H1 ainda alinhados com o lado anterior.
    - Exige que o preço tenha saído da zona EMA9/EMA21 após o fechamento
      e depois retornado para a zona.
    """

    if not ENABLE_REENTRY_AFTER_TP50:
        return None

    if not posicao_fechada:
        return None

    if posicao_fechada.get("status") != "ENCERRADO":
        return None

    if not bool(posicao_fechada.get("tp50_hit", False)):
        return None

    try:
        closed_at = float(posicao_fechada.get("closed_at", 0))
        if time.time() - closed_at < REENTRY_AFTER_CLOSE_SECONDS:
            return None
    except Exception:
        return None

    try:
        last_reentry_at = float(posicao_fechada.get("last_reentry_at", 0))
        if time.time() - last_reentry_at < REENTRY_COOLDOWN_SECONDS:
            return None
    except Exception:
        pass

    side = posicao_fechada.get("side")
    if side not in ["LONG", "SHORT"]:
        return None

    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    candle = df_h1.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"REENTRY IGNORADO POR CANDLE SUSPEITO: {nome_limpo(symbol)}")
        return None

    h4_state = estado_tendencia(df_h4.iloc[-2])
    h1_state = estado_tendencia(candle)

    if side == "LONG" and not (h4_state == 1 and h1_state == 1):
        return None

    if side == "SHORT" and not (h4_state == -1 and h1_state == -1):
        return None

    ema9 = float(candle["ema9"])
    ema21 = float(candle["ema21"])
    zone_top = max(ema9, ema21)
    zone_bottom = min(ema9, ema21)

    inside_zone = (
        float(candle["low"]) <= zone_top and
        float(candle["high"]) >= zone_bottom
    )

    posicoes = carregar_posicoes()
    p_atual = posicoes.get(symbol, posicao_fechada)

    reentry_ready = bool(p_atual.get("reentry_ready", False))

    # Primeiro precisa sair da zona após o fechamento.
    if not inside_zone:
        if not reentry_ready:
            p_atual["reentry_ready"] = True
            posicoes[symbol] = p_atual
            salvar_posicoes(posicoes)
        return None

    # Se ainda não saiu da zona depois do fechamento, não reentra.
    if inside_zone and not reentry_ready:
        return None

    if side == "LONG":
        confirmed = float(candle["close"]) > ema21
    else:
        confirmed = float(candle["close"]) < ema21

    if not confirmed:
        return None

    entry = float(candle["close"])
    sl, tp50, risk_abs = calcular_stop_tp(side, entry, df_h1)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        print(f"REENTRY IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None

    try:
        candles_since_close = int((time.time() - float(posicao_fechada.get("closed_at", time.time()))) / (60 * 60))
    except Exception:
        candles_since_close = None

    pontos, qualidade = calcular_qualidade(side, h4_state, candle)

    p_atual["reentry_ready"] = False
    p_atual["last_reentry_at"] = time.time()
    posicoes[symbol] = p_atual
    salvar_posicoes(posicoes)

    return adicionar_signal_score({
        "type": "REENTRY",
        "signal_type": "REENTRY",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": int(candle["time"]),
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": h4_state,
        "h1_state": h1_state,
        "adx_h4": float(df_h4.iloc[-2]["adx"]),
        "adx_h1": float(candle["adx"]),
        "volume_ok": bool(candle.get("volume_ok", False)),
        "bb_ok": bool(candle.get("bb_ok", False)),
        "candles_since_close": candles_since_close,
        "qualidade_pontos": pontos,
        "qualidade": qualidade
    })

# ====================================================
# TELEGRAM
# ====================================================

def enviar_early_a(s):
    emoji = "🚀 🟢" if s["signal"] == "LONG" else "🚀 🔴"
    nome = "EARLY BUY" if s["signal"] == "LONG" else "EARLY SELL"
    volume_txt = "ALTO ✅" if s.get("volume_ok") else "BAIXO ⚠️"
    bollinger_txt = "EXPANDINDO ✅" if s.get("bb_ok") else "COMPRIMINDO ⚠️"

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"Entrada antecipada na EMA21\n"
        f"A favor do H4 e contra o pullback do H1\n\n"
        f"H4: {estado_txt(s['h4_state'])}\n"
        f"H1 Pullback: {estado_txt(s['h1_state'])}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%\n\n"
        f"Qualidade:\n{s.get('qualidade', 'N/A')}\n\n"
        f"Score Elite:\n{s.get('signal_score', calcular_signal_score(s))}/100\n\n"
        f"Informativos:\n"
        f"ADX H4: {fmt_br(s.get('adx_h4', 0))}\n"
        f"Volume H1: {volume_txt}\n"
        f"Bollinger H1: {bollinger_txt}"
    )

    safe_send_telegram(msg)


def enviar_sinal_h1(s):
    emoji = "🟢" if s["signal"] == "LONG" else "🔴"
    nome = "BUY" if s["signal"] == "LONG" else "SELL"
    if s.get("signal_type") == "RECUPERADO":
        tipo = " RECUPERADO"
    elif s.get("signal_type") == "BREAKOUT":
        tipo = " BREAKOUT"
    elif s.get("signal_type") == "EARLY_HUNTER":
        tipo = " EARLY HUNTER"
    else:
        tipo = ""

    volume_txt = "ALTO ✅" if s.get("volume_ok") else "BAIXO ⚠️"
    bollinger_txt = "EXPANDINDO ✅" if s.get("bb_ok") else "COMPRIMINDO ⚠️"

    motivo_extra = ""

    if s.get("signal_type") == "RECUPERADO":
        motivo_extra = (
            "Motivo do recuperado:\n"
            "Retorno à zona EMA9/EMA21 após alinhamento H4/H1 mantido ✅\n"
            "Tendência principal continua válida ✅\n"
            "Entrada de continuação após pullback ✅\n\n"
        )

    msg = (
        f"{emoji} {nome} H1{tipo} - {s['symbol_clean']}\n\n"
        f"{motivo_extra}"
        f"H4: {estado_txt(s['h4_state'])}\n"
        f"H1: {estado_txt(s['h1_state'])}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%\n\n"
        f"Qualidade:\n{s.get('qualidade', 'N/A')}\n\n"
        f"Score Elite:\n{s.get('signal_score', calcular_signal_score(s))}/100\n\n"
        f"Informativos:\n"
        f"ADX H4: {fmt_br(s.get('adx_h4', 0))}\n"
        f"Volume H1: {volume_txt}\n"
        f"Bollinger H1: {bollinger_txt}"
    )

    safe_send_telegram(msg)


def enviar_reentry(s):
    emoji = "🔁 🟢" if s["signal"] == "LONG" else "🔁 🔴"
    nome = "REENTRY BUY H1" if s["signal"] == "LONG" else "REENTRY SELL H1"

    volume_txt = "ALTO ✅" if s.get("volume_ok") else "BAIXO ⚠️"
    bollinger_txt = "EXPANDINDO ✅" if s.get("bb_ok") else "COMPRIMINDO ⚠️"

    candles_txt = "N/A" if s.get("candles_since_close") is None else str(s.get("candles_since_close"))

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"Motivo do reentry:\n"
        f"Trade anterior atingiu TP50 ✅\n"
        f"Preço voltou à zona EMA9/EMA21 ✅\n"
        f"Tendência principal permanece alinhada ✅\n"
        f"Candles desde saída: {candles_txt}\n\n"
        f"H4: {estado_txt(s['h4_state'])}\n"
        f"H1: {estado_txt(s['h1_state'])}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%\n\n"
        f"Qualidade:\n{s.get('qualidade', 'N/A')}\n\n"
        f"Score Elite:\n{s.get('signal_score', calcular_signal_score(s))}/100\n\n"
        f"Informativos:\n"
        f"ADX H4: {fmt_br(s.get('adx_h4', 0))}\n"
        f"Volume H1: {volume_txt}\n"
        f"Bollinger H1: {bollinger_txt}"
    )

    safe_send_telegram(msg)




def enviar_poi(s):
    emoji = "🔵"
    nome = "POI H1"

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"H4: {estado_txt(s['h4_state'])}\n"
        f"H1: {estado_txt(s['h1_state'])}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%"
    )

    safe_send_telegram(msg)


def enviar_tp50(p, tp50, pnl_tp):
    safe_send_telegram(
        f"🎯 TP50 ATINGIDO - {p['symbol_clean']}\n\n"
        f"Parcial 50% realizada ✅\n\n"
        f"Resultado parcial:\n"
        f"{fmt_pct(pnl_tp)}\n\n"
        f"Status:\n"
        f"Aguardando Breakeven 1,5R ✅"
    )


def enviar_trailing_ativado(p, novo_stop):
    lucro_protegido = pnl_pct(
        p["side"],
        float(p["entry"]),
        float(novo_stop)
    )

    safe_send_telegram(
        f"🟣 TRAILING ATIVADO - {p['symbol_clean']}\n\n"
        f"Novo Stop:\n"
        f"{fmt_br(novo_stop)}\n\n"
        f"Lucro protegido:\n"
        f"{fmt_pct(lucro_protegido)}\n\n"
        f"Status:\n"
        f"Breakeven ativo ✅"
    )


def enviar_trailing(p, novo_stop):
    lucro_protegido = pnl_pct(
        p["side"],
        float(p["entry"]),
        float(novo_stop)
    )

    safe_send_telegram(
        f"🟣 TRAILING ATUALIZADO - {p['symbol_clean']}\n\n"
        f"Novo Stop:\n"
        f"{fmt_br(novo_stop)}\n\n"
        f"Lucro protegido:\n"
        f"{fmt_pct(lucro_protegido)}"
    )


def enviar_stop(p, preco_atual, stop, resultado):
    titulo = "🟣 TRAIL STOP" if resultado >= 0 else "🟠 STOP"

    safe_send_telegram(
        f"{titulo} - {p['symbol_clean']}\n\n"
        f"Preço atual:\n"
        f"{fmt_br(preco_atual)}\n\n"
        f"Saída:\n"
        f"{fmt_br(stop)}\n\n"
        f"Resultado:\n"
        f"{fmt_pct(resultado)}"
    )


# ====================================================
# POSIÇÕES
# ====================================================

def registrar_posicao(s):
    if startup_signal_guard_active():
        try:
            historico = carregar_sinais()
            symbol_guard = s.get("symbol")
            ts_guard = s.get("timestamp")
            side_guard = s.get("signal", s.get("side"))
            st_guard = s.get("signal_type", "SIGNAL")
            for chave_guard in [
                f"{symbol_guard}_{ts_guard}_{side_guard}",
                f"{st_guard}_{symbol_guard}_{ts_guard}_{side_guard}",
                f"BREAKOUT_{symbol_guard}_{ts_guard}_{side_guard}",
                f"EARLY_HUNTER_{symbol_guard}_{ts_guard}_{side_guard}",
                f"EARLY_{symbol_guard}_{ts_guard}_{side_guard}",
                f"REENTRY_{symbol_guard}_{ts_guard}_{side_guard}",
            ]:
                historico[chave_guard] = True
            if len(historico) > 3000:
                historico = dict(list(historico.items())[-3000:])
            salvar_sinais(historico)
            registrar_funil("startup_guard_ignorados")
            print(f"STARTUP GUARD MEME: sinal ignorado {s.get('symbol_clean', symbol_guard)} {side_guard} ({startup_guard_restante_segundos()}s restantes)")
        except Exception as e:
            print("ERRO STARTUP GUARD MEME:", e)
        return False

    posicoes = carregar_posicoes()

    # BLOQUEIO CENTRAL DE LIMITE:
    # Garante que NORMAL, RECUPERADO, EARLY e REENTRY não abram acima do limite.
    symbol = s["symbol"]

    posicoes_ativas = [
        p for p in posicoes.values()
        if p.get("status") != "ENCERRADO"
    ]

    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
        print(f"POSIÇÃO JÁ ATIVA IGNORADA: {nome_limpo(symbol)}")
        return False

    if len(posicoes_ativas) >= MAX_OPEN_POSITIONS:
        print(
            f"SINAL IGNORADO POR LIMITE DE POSIÇÕES: "
            f"{nome_limpo(symbol)} | {len(posicoes_ativas)}/{MAX_OPEN_POSITIONS}"
        )
        return False

    posicoes[symbol] = {
        "symbol": symbol,
        "symbol_clean": s["symbol_clean"],
        "side": s["signal"],
        "entry": s["entry"],
        "sl": s["sl"],
        "initial_sl": s.get("initial_sl", s["sl"]),
        "tp50": s["tp50"],
        "risk_abs": s["risk_abs"],
        "risk_pct": s["risk_pct"],
        "status": "ATIVO",
        "breakeven": False,
        "tp50_hit": False,
        "timestamp": s["timestamp"],
        "created_at": time.time(),
        "active_since": time.time(),
        "breakeven_activated_at": None,
        "trailing_activated_at": None,
        "h4_state": s.get("h4_state"),
        "h1_state": s.get("h1_state"),
        "signal_type": s.get("signal_type", "NORMAL"),
        "signal_score": s.get("signal_score", calcular_signal_score(s)),
        "elite_candidate": bool(s.get("elite_candidate", s.get("signal_score", calcular_signal_score(s)) >= ELITE_THRESHOLD)),
        "last_poi_zone": False,
        "reentry_ready": False,
        "last_reentry_at": None,
        "closed_at": None,
        "closed_reason": None,
        "mfe_max_pct": 0.0,
        "mae_max_pct": 0.0,
        "mfe_max_r": 0.0,
        "mae_max_r": 0.0,
        "mfe_gave_back_pct": 0.0,
        "mfe_gave_back_r": 0.0
    }

    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": "ENTRY",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": symbol,
        "symbol_clean": s["symbol_clean"],
        "side": s["signal"],
        "entry": s["entry"],
        "sl": s["sl"],
        "tp50": s["tp50"],
        "risk_pct": s["risk_pct"],
        "h4_state": s.get("h4_state"),
        "h1_state": s.get("h1_state"),
        "qualidade": s.get("qualidade"),
        "qualidade_pontos": s.get("qualidade_pontos"),
        "signal_type": s.get("signal_type", "NORMAL"),
        "signal_score": s.get("signal_score", calcular_signal_score(s)),
        "elite_candidate": bool(s.get("elite_candidate", s.get("signal_score", calcular_signal_score(s)) >= ELITE_THRESHOLD))
    })

    return True


def atualizar_posicao_com_poi(poi):
    if not ALLOW_POI_UPDATE_ENTRY:
        return

    posicoes = carregar_posicoes()
    p = posicoes.get(poi["symbol"])

    if not p or p.get("status") == "ENCERRADO":
        return

    p["entry"] = poi["entry"]
    p["tp50"] = poi["tp50"]
    p["risk_abs"] = poi["risk_abs"]
    p["risk_pct"] = poi["risk_pct"]
    p["timestamp"] = poi["timestamp"]
    p["active_since"] = time.time()
    p["breakeven"] = False
    p["tp50_hit"] = False
    p["status"] = "ATIVO"
    p["breakeven_activated_at"] = None
    p["trailing_activated_at"] = None
    p["last_poi_zone"] = True
    p["last_update_type"] = "POI"

    posicoes[poi["symbol"]] = p
    salvar_posicoes(posicoes)

    registrar_evento_trade({
        "event": "POI",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": poi["symbol"],
        "symbol_clean": poi["symbol_clean"],
        "side": poi["side"],
        "entry": poi["entry"],
        "sl": poi["sl"],
        "tp50": poi["tp50"],
        "risk_pct": poi["risk_pct"],
        "h4_state": poi.get("h4_state"),
        "h1_state": poi.get("h1_state"),
        "signal_score": poi.get("signal_score"),
        "elite_candidate": poi.get("elite_candidate"),
        "qualidade": poi.get("qualidade"),
        "qualidade_pontos": poi.get("qualidade_pontos")
    })


def calcular_chandelier(symbol, side):
    ohlcv = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=80)
    df = pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])
    df["atr14"] = calcular_atr(df, ATR_LEN)
    df = marcar_spikes(df)

    candle = df.iloc[-2]
    atr = float(candle["atr14"])

    ultimos = df.iloc[-40:-1]
    if "spike_suspeito" in ultimos.columns:
        ultimos = ultimos[~ultimos["spike_suspeito"]]

    if len(ultimos) < 10:
        ultimos = df.iloc[-23:-1]

    if side == "LONG":
        highest_high = float(ultimos["high"].max())
        return highest_high - atr * TRAIL_ATR_MULT

    lowest_low = float(ultimos["low"].min())
    return lowest_low + atr * TRAIL_ATR_MULT


def stop_em_carencia(p):
    agora = time.time()

    for campo in ["breakeven_activated_at", "trailing_activated_at"]:
        val = p.get(campo)
        if val is None:
            continue
        try:
            if agora - float(val) < PROTECTION_SECONDS:
                return True
        except Exception:
            pass

    return False


def adicionar_monitor_be(p, entry, exit_price):
    monitores = carregar_monitor_be()

    monitores.append({
        "symbol": p["symbol"],
        "symbol_clean": p["symbol_clean"],
        "side": p["side"],
        "entry": entry,
        "exit_price": exit_price,
        "closed_at": time.time(),
        "closed_date": data_hoje_sp_str(),
        "closed_datetime": data_hora_sp_str(),
        "monitor_until": time.time() + 86400,
        "best_after_pct": 0.0,
        "active": True
    })

    if len(monitores) > 500:
        monitores = monitores[-500:]

    salvar_monitor_be(monitores)


def atualizar_monitor_be():
    monitores = carregar_monitor_be()

    if not monitores:
        return

    agora = time.time()
    alterou = False

    for m in monitores:
        if not m.get("active"):
            continue

        try:
            ticker = safe_fetch_ticker(m["symbol"])
            preco = float(ticker["last"])
            saida = float(m["exit_price"])

            if m["side"] == "LONG":
                movimento = ((preco - saida) / saida) * 100
            else:
                movimento = ((saida - preco) / saida) * 100

            if movimento > float(m.get("best_after_pct", 0)):
                m["best_after_pct"] = movimento
                alterou = True

            if agora >= float(m.get("monitor_until", 0)):
                m["active"] = False
                alterou = True

        except Exception as e:
            print("ERRO MONITOR BE:", e)

    if alterou:
        salvar_monitor_be(monitores)


def pnl_r(side, entry, sl_inicial, price):
    risk = abs(float(entry) - float(sl_inicial))
    if risk <= 0:
        return 0.0
    if side == "LONG":
        return (float(price) - float(entry)) / risk
    return (float(entry) - float(price)) / risk

def atualizar_mfe_mae_posicao(p, preco_atual):
    try:
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
    except Exception as e:
        print("ERRO MFE/MAE MEME:", e)
    return p

def gerenciar_posicoes():
    posicoes = carregar_posicoes()
    alterou = False

    for symbol, p in list(posicoes.items()):
        if p.get("status") == "ENCERRADO":
            continue

        try:
            ticker = safe_fetch_ticker(symbol)
            if not ticker:
                continue
            preco_atual = float(ticker["last"])
            p = atualizar_mfe_mae_posicao(p, preco_atual)

            # Proteção anti-spike para gestão:
            # se o último candle H1 fechado for suspeito, não atualiza stop/TP nesta rodada.
            try:
                ohlcv_check = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=80)
                df_check = pd.DataFrame(ohlcv_check, columns=["time", "open", "high", "low", "close", "volume"])
                df_check["atr14"] = calcular_atr(df_check, ATR_LEN)
                df_check = marcar_spikes(df_check)
                if bool(df_check.iloc[-2].get("spike_suspeito", False)):
                    print(f"GESTÃO PAUSADA POR CANDLE SUSPEITO: {nome_limpo(symbol)}")
                    continue
            except Exception as e:
                print(f"ERRO CHECAGEM SPIKE {nome_limpo(symbol)}:", e)

            side = p["side"]
            entry = float(p["entry"])
            sl = float(p["sl"])
            tp50 = float(p["tp50"])

            # STOP por preço em tempo real.
            if not stop_em_carencia(p):
                if side == "LONG" and preco_atual <= sl:
                    resultado = pnl_pct(side, entry, sl)
                    enviar_stop(p, preco_atual, sl, resultado)

                    resultado_tipo = (
                        "BREAKEVEN"
                        if p.get("breakeven") and -0.05 <= resultado <= 0.30
                        else ("WIN" if resultado > 0 else "LOSS")
                    )

                    registrar_evento_trade({
                        "event": "CLOSE",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "entry": entry,
                        "exit": sl,
                        "pnl": resultado,
                        "result_type": resultado_tipo,
                        "breakeven": bool(p.get("breakeven")),
                        "tp50_hit": bool(p.get("tp50_hit")),
                        "status": p.get("status")
                    })

                    if resultado_tipo == "BREAKEVEN":
                        adicionar_monitor_be(p, entry, sl)

                    p["closed_at"] = time.time()
                    p["closed_datetime"] = data_hora_sp_str()
                    p["closed_reason"] = resultado_tipo
                    p["reentry_ready"] = False
                    p["status"] = "ENCERRADO"
                    alterou = True
                    continue

                if side == "SHORT" and preco_atual >= sl:
                    resultado = pnl_pct(side, entry, sl)
                    enviar_stop(p, preco_atual, sl, resultado)

                    resultado_tipo = (
                        "BREAKEVEN"
                        if p.get("breakeven") and -0.05 <= resultado <= 0.30
                        else ("WIN" if resultado > 0 else "LOSS")
                    )

                    registrar_evento_trade({
                        "event": "CLOSE",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "entry": entry,
                        "exit": sl,
                        "pnl": resultado,
                        "result_type": resultado_tipo,
                        "breakeven": bool(p.get("breakeven")),
                        "tp50_hit": bool(p.get("tp50_hit")),
                        "status": p.get("status")
                    })

                    if resultado_tipo == "BREAKEVEN":
                        adicionar_monitor_be(p, entry, sl)

                    p["closed_at"] = time.time()
                    p["closed_datetime"] = data_hora_sp_str()
                    p["closed_reason"] = resultado_tipo
                    p["reentry_ready"] = False
                    p["status"] = "ENCERRADO"
                    alterou = True
                    continue

            # TP50 em 1R:
            # Realiza a parcial, mas NÃO move o stop para BE ainda.
            # O BE/trailing só ativa quando o preço andar 1,5R.
            if not p.get("tp50_hit"):
                if side == "LONG" and preco_atual >= tp50:
                    p["tp50_hit"] = True
                    p["status"] = "TP50 HIT"
                    p["tp50_activated_at"] = time.time()
                    alterou = True

                    enviar_tp50(p, tp50, pnl_pct(side, entry, tp50))

                    registrar_evento_trade({
                        "event": "TP50",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "entry": entry,
                        "tp50": tp50,
                        "be_trigger_r": BE_TRIGGER_R,
                        "be_trigger_price": entry + float(p.get("risk_abs", abs(entry - sl))) * BE_TRIGGER_R,
                        "stop_after_tp50": float(p["sl"])
                    })

                    continue

                if side == "SHORT" and preco_atual <= tp50:
                    p["tp50_hit"] = True
                    p["status"] = "TP50 HIT"
                    p["tp50_activated_at"] = time.time()
                    alterou = True

                    enviar_tp50(p, tp50, pnl_pct(side, entry, tp50))

                    registrar_evento_trade({
                        "event": "TP50",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "entry": entry,
                        "tp50": tp50,
                        "be_trigger_r": BE_TRIGGER_R,
                        "be_trigger_price": entry - float(p.get("risk_abs", abs(sl - entry))) * BE_TRIGGER_R,
                        "stop_after_tp50": float(p["sl"])
                    })

                    continue

            # BE/trailing em 1,5R:
            # Só depois do TP50 e somente uma vez.
            if p.get("tp50_hit") and not p.get("breakeven"):
                try:
                    risk_abs_pos = float(p.get("risk_abs", abs(entry - sl)))
                except Exception:
                    risk_abs_pos = abs(entry - sl)

                if side == "LONG":
                    be_trigger_price = entry + risk_abs_pos * BE_TRIGGER_R

                    if preco_atual >= be_trigger_price:
                        novo_stop_be = entry * (1 + BE_OFFSET_PCT / 100)
                        novo_stop_trail = calcular_chandelier(symbol, side)
                        novo_stop = max(float(p["sl"]), novo_stop_be, novo_stop_trail)

                        p["sl"] = novo_stop
                        p["breakeven"] = True
                        p["status"] = "TRAILING STOP"
                        p["breakeven_activated_at"] = time.time()
                        p["trailing_activated_at"] = time.time()
                        alterou = True

                        enviar_trailing_ativado(p, novo_stop)

                        registrar_evento_trade({
                            "event": "BE_TRIGGER",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p["symbol_clean"],
                            "side": side,
                            "entry": entry,
                            "be_trigger_r": BE_TRIGGER_R,
                            "be_trigger_price": be_trigger_price,
                            "new_stop": novo_stop
                        })

                        continue

                if side == "SHORT":
                    be_trigger_price = entry - risk_abs_pos * BE_TRIGGER_R

                    if preco_atual <= be_trigger_price:
                        novo_stop_be = entry * (1 - BE_OFFSET_PCT / 100)
                        novo_stop_trail = calcular_chandelier(symbol, side)
                        novo_stop = min(float(p["sl"]), novo_stop_be, novo_stop_trail)

                        p["sl"] = novo_stop
                        p["breakeven"] = True
                        p["status"] = "TRAILING STOP"
                        p["breakeven_activated_at"] = time.time()
                        p["trailing_activated_at"] = time.time()
                        alterou = True

                        enviar_trailing_ativado(p, novo_stop)

                        registrar_evento_trade({
                            "event": "BE_TRIGGER",
                            "date": data_hoje_sp_str(),
                            "datetime": data_hora_sp_str(),
                            "symbol": symbol,
                            "symbol_clean": p["symbol_clean"],
                            "side": side,
                            "entry": entry,
                            "be_trigger_r": BE_TRIGGER_R,
                            "be_trigger_price": be_trigger_price,
                            "new_stop": novo_stop
                        })

                        continue

            # Trailing somente após ativar BE em 1,5R.
            if p.get("tp50_hit") and p.get("breakeven"):
                novo_stop = calcular_chandelier(symbol, side)

                if side == "LONG" and novo_stop > float(p["sl"]):
                    p["sl"] = novo_stop
                    p["trailing_activated_at"] = time.time()
                    alterou = True
                    enviar_trailing(p, novo_stop)

                    registrar_evento_trade({
                        "event": "TRAILING",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "new_stop": novo_stop
                    })

                if side == "SHORT" and novo_stop < float(p["sl"]):
                    p["sl"] = novo_stop
                    p["trailing_activated_at"] = time.time()
                    alterou = True
                    enviar_trailing(p, novo_stop)

                    registrar_evento_trade({
                        "event": "TRAILING",
                        "date": data_hoje_sp_str(),
                        "datetime": data_hora_sp_str(),
                        "symbol": symbol,
                        "symbol_clean": p["symbol_clean"],
                        "side": side,
                        "new_stop": novo_stop
                    })

        except Exception as e:
            print(f"ERRO GESTÃO {symbol}: {e}")

    if alterou:
        salvar_posicoes(posicoes)


# ====================================================
# RELATÓRIOS / COMANDOS
# ====================================================

def obter_posicoes_ativas_ordenadas():
    posicoes = carregar_posicoes()
    ativos = []

    for p in posicoes.values():
        if p.get("status") == "ENCERRADO":
            continue

        try:
            ticker = safe_fetch_ticker(p["symbol"])
            preco = float(ticker["last"])
            resultado = pnl_pct(p["side"], float(p["entry"]), preco)

            item = dict(p)
            item["pnl_atual"] = resultado
            ativos.append(item)

        except Exception as e:
            print("ERRO AO ORDENAR POSIÇÃO:", e)

    ativos.sort(key=lambda x: x["pnl_atual"], reverse=True)
    return ativos


def enviar_relatorio_posicoes():
    ativos = obter_posicoes_ativas_ordenadas()
    data = agora_sp().strftime("%d/%m/%Y %H:%M")

    if not ativos:
        send_telegram(
            f"📊 RELATÓRIO DE POSIÇÕES\n"
            f"{data}\n\n"
            f"Nenhum trade ativo."
        )
        return

    linhas = ["📊 RELATÓRIO DE POSIÇÕES", data]

    for p in ativos:
        linhas.append(
            f"\n{p['symbol_clean']} - {p['side']}\n\n"
            f"PnL:\n{fmt_pct(p['pnl_atual'])}\n\n"
            f"Entrada:\n{fmt_br(p['entry'])}\n\n"
            f"Stop Atual:\n{fmt_br(p['sl'])}\n\n"
            f"TP50:\n{fmt_br(p['tp50'])}\n\n"
            f"Status:\n"
            f"Breakeven {check_bool(p.get('breakeven'))}\n"
            f"TP50 {check_bool(p.get('tp50_hit'))}\n"
            f"Trailing Stop {check_bool(p.get('status') == 'TRAILING STOP')}\n"
            f"────────────────"
        )

    send_telegram("\n".join(linhas))


def montar_status():
    ativos = obter_posicoes_ativas_ordenadas()
    linhas = ["📊 STATUS DO ROBÔ"]
    linhas.append(f"\nTrades ativos: {len(ativos)}")

    if not ativos:
        linhas.append("\nNenhum trade ativo.")
        return "\n".join(linhas)

    linhas.append("\n────────────────\n")

    for p in ativos:
        linhas.append(
            f"{p['symbol_clean']} - {p['side']}\n\n"
            f"PnL:\n{fmt_pct(p['pnl_atual'])}\n\n"
            f"Entrada:\n{fmt_br(p['entry'])}\n\n"
            f"Stop Atual:\n{fmt_br(p['sl'])}\n\n"
            f"TP50:\n{fmt_br(p['tp50'])}\n\n"
            f"Breakeven {check_bool(p.get('breakeven'))}\n"
            f"TP50 {check_bool(p.get('tp50_hit'))}\n"
            f"Trailing Stop {check_bool(p.get('status') == 'TRAILING STOP')}\n"
            f"────────────────\n"
        )

    return "\n".join(linhas)


def montar_watchlist():
    watchlist = carregar_watchlist()
    linhas = [f"👀 WATCHLIST ({len(watchlist)})\n"]

    for symbol in watchlist:
        try:
            ticker = safe_fetch_ticker(symbol)
            preco = float(ticker["last"])
            linhas.append(f"{nome_limpo(symbol)} | {fmt_br(preco)}")
        except Exception:
            linhas.append(f"{nome_limpo(symbol)} | erro")

    return "\n".join(linhas)


def montar_resumo_diario():
    hoje = data_hoje_sp_str()
    data_br = agora_sp().strftime("%d/%m/%Y")

    trades = carregar_trades()

    entradas = [t for t in trades if t.get("date") == hoje and t.get("event") == "ENTRY"]
    pois = [t for t in trades if t.get("date") == hoje and t.get("event") == "POI"]
    earlys = [t for t in trades if t.get("date") == hoje and t.get("event") == "ENTRY" and t.get("signal_type") == "EARLY"]
    reentries = [t for t in trades if t.get("date") == hoje and t.get("event") == "ENTRY" and t.get("signal_type") == "REENTRY"]
    fechados = [t for t in trades if t.get("date") == hoje and t.get("event") == "CLOSE"]
    tp50s = [t for t in trades if t.get("date") == hoje and t.get("event") == "TP50"]
    trailings = [t for t in trades if t.get("date") == hoje and t.get("event") == "TRAILING"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]

    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]

    melhor = max(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None
    pior = min(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None

    linhas = [
        "📈 RESUMO DO DIA",
        data_br,
        "",
        f"Sinais H1 do dia: {len(entradas)}",
        f"LONG: {len(longs)}",
        f"SHORT: {len(shorts)}",
        f"EARLY: {len(earlys)}",
        f"REENTRY: {len(reentries)}",
        f"POIs H1: {len(pois)}",
        "",
        f"Trades encerrados: {len(fechados)}",
        f"Wins: {len(wins)}",
        f"Breakeven: {len(bes)}",
        f"Loss: {len(losses)}",
        "",
        f"TP50 atingidos: {len(tp50s)}",
        f"Trailings atualizados: {len(trailings)}",
        "",
        "PnL realizado:",
        f"{fmt_pct(pnl_total)}"
    ]

    if melhor:
        linhas.extend(["", "Melhor trade:", f"{melhor.get('symbol_clean')} {fmt_pct(melhor.get('pnl', 0))}"])

    if pior:
        linhas.extend(["", "Pior trade:", f"{pior.get('symbol_clean')} {fmt_pct(pior.get('pnl', 0))}"])

    ativos = obter_posicoes_ativas_ordenadas()
    linhas.extend(["", f"Trades ainda ativos: {len(ativos)}"])

    for p in ativos[:10]:
        linhas.append(f"{p['symbol_clean']} {p['side']} | PnL {fmt_pct(p['pnl_atual'])}")

    return "\n".join(linhas)


def enviar_resumo_diario():
    send_telegram(montar_resumo_diario())


def resumo_diario_ja_enviado():
    enviados = redis_get_json(DAILY_SUMMARY_KEY, {})
    hoje = data_hoje_sp_str()
    return enviados.get(hoje) is True


def marcar_resumo_diario_enviado():
    enviados = redis_get_json(DAILY_SUMMARY_KEY, {})
    hoje = data_hoje_sp_str()
    enviados[hoje] = True

    if len(enviados) > 30:
        chaves = sorted(enviados.keys())
        for chave in chaves[:-30]:
            enviados.pop(chave, None)

    redis_set_json(DAILY_SUMMARY_KEY, enviados)


def montar_monitor_be():
    monitores = carregar_monitor_be()
    ativos = [m for m in monitores if m.get("active")]
    recentes = monitores[-20:]

    linhas = [
        "📉 MONITOR DE BREAKEVEN",
        "",
        f"Ativos em monitoramento: {len(ativos)}"
    ]

    if not recentes:
        linhas.append("\nNenhum breakeven monitorado ainda.")
        return "\n".join(linhas)

    linhas.append("\nÚltimos monitoramentos:")

    for m in reversed(recentes[-10:]):
        status = "ATIVO" if m.get("active") else "FINALIZADO"
        linhas.append(
            f"\n{m.get('symbol_clean')} - {m.get('side')}\n"
            f"Fechou: {m.get('closed_datetime')}\n"
            f"Após saída: +{fmt_br(m.get('best_after_pct', 0))}%\n"
            f"Status: {status}\n"
            f"────────────────"
        )

    return "\n".join(linhas)


def resetar_robo():
    global ultimo_candle_h1, ultimo_relatorio_hora

    salvar_posicoes({})
    salvar_sinais({})
    salvar_trades([])
    salvar_monitor_be([])
    salvar_poi_cooldown({})
    salvar_early_cooldown({})
    redis_set_json(DAILY_SUMMARY_KEY, {})

    ultimo_candle_h1 = {}
    ultimo_relatorio_hora = None


def processar_comando(texto):
    cmd = texto.strip().lower()
    if "@" in cmd:
        cmd = cmd.split("@")[0]

    if cmd in ["/start", "/help", "/comandos"]:
        return (
            "📌 Comandos disponíveis:\n\n"
            "/health - painel técnico do Meme Hunter\n"
            "/teste - testa conexão com Telegram\n"
            "/posicoes - lista posições abertas\n"
            "/top - mostra melhores posições abertas\n"
            "/resumo - envia resumo do dia\n"
            "/mensal - envia resumo mensal\n"
            "/watchlist - mostra ativos monitorados\n"
            "/be - monitor de breakeven\n"
            "/limparbe - limpa monitor BE\n"
            "/reset - limpa cooldowns/bloqueios sem apagar posições\n"
            "/comandos - mostra esta lista\n\n"
            "Setups ativos:\n"
            "🔥 Early Hunter - pré-rompimento\n"
            "🔥 Meme Breakout - rompimento confirmado"
        )

    if cmd in ["/health", "/status"]:
        return montar_health_tecnico()
    if cmd == "/teste":
        return "✅ Meme Hunter PRO conectado ao Telegram."
    if cmd in ["/posicoes", "/posições"]:
        return montar_status()
    if cmd == "/top":
        ativos = obter_posicoes_ativas_ordenadas()
        if not ativos:
            return "📊 TOP MEME HUNTER\n\nNenhuma posição ativa."
        linhas = ["📊 TOP MEME HUNTER\n"]
        for p in ativos[:10]:
            linhas.append(f"{p['symbol_clean']} {p['side']} | {fmt_pct(p.get('pnl_atual', 0))}")
        return "\n".join(linhas)
    if cmd == "/watchlist":
        wl = carregar_watchlist()
        wl_validada = validar_watchlist_bingx(wl, avisar_telegram=False)
        return (
            f"👀 WATCHLIST MEME HUNTER\n\n"
            f"Configurada: {len(wl)} ativos\n"
            f"Válida BingX: {len(wl_validada)} ativos\n\n"
            + "\n".join([nome_limpo(x) for x in wl_validada])
        )
    if cmd == "/resumo":
        return montar_resumo_diario()
    if cmd == "/mensal":
        return montar_resumo_mensal()
    if cmd == "/be":
        return montar_monitor_be()
    if cmd == "/limparbe":
        salvar_monitor_be([])
        return "✅ Monitor BE limpo com segurança."
    if cmd == "/reset":
        salvar_sinais({})
        salvar_bloqueios_reentrada({})
        salvar_monitor_be([])
        salvar_poi_cooldown({})
        salvar_early_cooldown({})
        salvar_early_hunter_cooldown({})
        redis_set_json(DAILY_SUMMARY_KEY, {})
        return (
            "✅ Reset operacional realizado.\n\n"
            "O que foi limpo:\n"
            "- Histórico de sinais/cooldowns\n"
            "- Bloqueios de reentrada\n"
            "- Monitor BE\n"
            "- Cooldown POI\n"
            "- Cooldown EARLY\n"
            "- Cooldown EARLY HUNTER\n"
            "- Controle de resumo diário\n\n"
            "O que NÃO foi apagado:\n"
            "- Posições abertas\n"
            "- Histórico de trades"
        )
    return None


def listen_commands():
    last_update_id = 0
    print("INTERPRETADOR DE COMANDOS MEME INICIADO")
    while True:
        try:
            if not TOKEN or not CHAT_ID:
                time.sleep(2)
                continue
            resp = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=20",
                timeout=30
            ).json()
            for update in resp.get("result", []):
                last_update_id = update.get("update_id", last_update_id)
                msg = update.get("message") or update.get("edited_message") or {}
                texto_raw = msg.get("text", "") or ""
                texto = texto_raw.strip().split()[0].lower() if texto_raw.strip() else ""
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id or str(chat_id) != str(CHAT_ID):
                    continue
                resposta = processar_comando(texto)
                if resposta:
                    enviar_texto(chat_id, resposta)
        except Exception as e:
            print("ERRO COMANDOS MEME:", e)
        time.sleep(2)


# ====================================================
# SCANNER
# ====================================================

def scanner():
    global ultimo_relatorio_hora

    print("SCANNER INICIADO")
    HEALTH["started_at"] = data_hora_sp_str()
    safe_send_telegram(
        "🔥 Robô Meme Hunter PRO iniciado\n\n"
        f"Filtros ativos:\n"
        f"Score mínimo: {ELITE_THRESHOLD}/100\n"
        f"ADX H4 mínimo: {ELITE_MIN_ADX_H4}\n"
        f"Volume H1 obrigatório: {check_bool(REQUIRE_HIGH_VOLUME)}\n"
        f"Recuperado ativo: {check_bool(ENABLE_RECOVERED_SIGNAL)}\n"
        f"Relatório automático: {check_bool(ENABLE_AUTO_POSITION_REPORT)}\n"
        f"Estratégia principal: Breakout + Volume + Momentum\n"
        f"Meme score mínimo: {MEME_MIN_SCORE}/100"
    )

    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            gerenciar_posicoes()
            HEALTH["last_management_run"] = data_hora_sp_str()
            atualizar_monitor_be()

            agora = time.localtime()

            if ENABLE_AUTO_POSITION_REPORT and agora.tm_min >= 50:
                chave_hora = f"{agora.tm_year}-{agora.tm_yday}-{agora.tm_hour}"

                if ultimo_relatorio_hora != chave_hora:
                    print("ENVIANDO RELATÓRIO DE POSIÇÕES")
                    enviar_relatorio_posicoes()
                    ultimo_relatorio_hora = chave_hora

            agora_brasil = agora_sp()

            if agora_brasil.hour == 23 and agora_brasil.minute >= 55:
                if not resumo_diario_ja_enviado():
                    print("ENVIANDO RESUMO DO DIA")
                    enviar_resumo_diario()
                    marcar_resumo_diario_enviado()

            enviar_resumo_mensal_se_preciso()

            watchlist = carregar_watchlist()
            watchlist = validar_watchlist_bingx(watchlist, avisar_telegram=True)
            HEALTH["last_watchlist_count"] = len(watchlist)
            sinais = []
            sinais_enviados = 0

            for symbol in watchlist:
                try:
                    # Posições ativas: na V2, a gestão fica com TP50/BE/trailing.
                    # POI herdado do Trend PRO fica desligado por padrão para evitar reentradas ruins em memes.
                    posicoes = carregar_posicoes()
                    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
                        if not ENABLE_POI_ALERTS:
                            continue
                        poi = detectar_poi(symbol, posicoes[symbol])
                        if poi:
                            aprovado, motivo = passa_filtro_trendpro_elite(
                                poi,
                                threshold=POI_THRESHOLD,
                                min_adx_h4=POI_MIN_ADX_H4,
                                require_high_volume=POI_REQUIRE_HIGH_VOLUME,
                                require_bb_expanding=False,
                                label="POI"
                            )

                            if aprovado:
                                enviar_poi(poi)
                                atualizar_posicao_com_poi(poi)
                            else:
                                print(f"POI BLOQUEADO PELO TREND PRO ELITE: {nome_limpo(symbol)} | {motivo}")
                        continue

                    # REENTRY para posições encerradas que já atingiram TP50.
                    if symbol in posicoes and posicoes[symbol].get("status") == "ENCERRADO":
                        reentry = detectar_reentry(symbol, posicoes[symbol])
                        if reentry:
                            aprovado, motivo = passa_filtro_trendpro_elite(
                                reentry,
                                threshold=ELITE_THRESHOLD,
                                min_adx_h4=ELITE_MIN_ADX_H4,
                                require_high_volume=REQUIRE_HIGH_VOLUME,
                                require_bb_expanding=REQUIRE_BB_EXPANDING,
                                label="REENTRY"
                            )

                            if not aprovado:
                                print(f"REENTRY BLOQUEADO PELO TREND PRO ELITE: {nome_limpo(symbol)} | {motivo}")
                                continue

                            timestamp = int(reentry["timestamp"])
                            chave_reentry = f"REENTRY_{symbol}_{timestamp}_{reentry['signal']}"

                            historico_tmp = carregar_sinais()
                            if chave_reentry not in historico_tmp:
                                if registrar_posicao(reentry):
                                    historico_tmp[chave_reentry] = True
                                    salvar_sinais(historico_tmp)
                                    enviar_reentry(reentry)
                                    sinais_enviados += 1
                            continue

                    breakout = detectar_early_hunter(symbol)
                    if not breakout:
                        breakout = detectar_breakout_meme(symbol)

                    if breakout:
                        timestamp = int(breakout["timestamp"])
                        chave_breakout = f"BREAKOUT_{symbol}_{timestamp}_{breakout['signal']}"

                        historico_tmp = carregar_sinais()
                        if chave_breakout not in historico_tmp:
                            if registrar_posicao(breakout):
                                historico_tmp[chave_breakout] = True
                                salvar_sinais(historico_tmp)
                                enviar_sinal_h1(breakout)
                                registrar_funil("sinais_enviados")
                                sinais_enviados += 1
                        continue

                    if not ENABLE_LEGACY_TREND_ENTRIES:
                        continue

                    early = detectar_early_a(symbol)

                    if early:
                        aprovado, motivo = passa_filtro_trendpro_elite(
                            early,
                            threshold=EARLY_THRESHOLD,
                            min_adx_h4=EARLY_MIN_ADX_H4,
                            require_high_volume=EARLY_REQUIRE_VOLUME,
                            require_bb_expanding=False,
                            label="EARLY"
                        )

                        if not aprovado:
                            print(f"EARLY BLOQUEADO PELO TREND PRO ELITE: {nome_limpo(symbol)} | {motivo}")
                            continue

                        timestamp = int(early["timestamp"])
                        chave_early = f"EARLY_{symbol}_{timestamp}_{early['signal']}"

                        historico_tmp = carregar_sinais()
                        if chave_early not in historico_tmp:
                            if registrar_posicao(early):
                                historico_tmp[chave_early] = True
                                salvar_sinais(historico_tmp)
                                enviar_early_a(early)
                                sinais_enviados += 1
                        continue

                    resultado, df_h1, df_h4 = analisar_sinal_h1(symbol)

                    if not resultado:
                        continue

                    aprovado, motivo = passa_filtro_trendpro_elite(
                        resultado,
                        threshold=ELITE_THRESHOLD,
                        min_adx_h4=ELITE_MIN_ADX_H4,
                        require_high_volume=REQUIRE_HIGH_VOLUME,
                        require_bb_expanding=REQUIRE_BB_EXPANDING,
                        label="SINAL"
                    )

                    if not aprovado:
                        print(f"SINAL BLOQUEADO PELO TREND PRO ELITE: {nome_limpo(symbol)} | {motivo}")
                        continue

                    timestamp = int(resultado["timestamp"])

                    if symbol in ultimo_candle_h1 and ultimo_candle_h1[symbol] == timestamp:
                        continue

                    ultimo_candle_h1[symbol] = timestamp
                    sinais.append(resultado)

                except Exception as e:
                    print(f"ERRO EM {symbol}:", e)

            sinais.sort(key=lambda x: x.get("risk_pct", 999))

            historico = carregar_sinais()

            for s in sinais:
                if existe_posicao_ativa(s["symbol"]):
                    continue

                chave = f"{s['symbol']}_{s['timestamp']}_{s['signal']}"

                if chave in historico:
                    continue

                if registrar_posicao(s):
                    historico[chave] = True
                    enviar_sinal_h1(s)
                    sinais_enviados += 1

            salvar_sinais(historico)

            HEALTH["last_signals_sent"] = sinais_enviados
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            print(f"Sinais enviados: {len(sinais)}")

        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO SCANNER:", e)

        time.sleep(60)



@app.route("/health")
def health():
    try:
        return json.loads(montar_health_tecnico())
    except Exception as e:
        return {
            "ok": False,
            "bot": "Meme Hunter PRO",
            "last_error": str(e),
            "health": HEALTH,
        }

@app.route("/watchdog")
def watchdog_status():
    return {
        "ok": HEALTH.get("watchdog_last_status", "OK") == "OK",
        "bot": "Meme Hunter PRO",
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "watchdog_status": HEALTH.get("watchdog_last_status", "OK"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
    }

@app.route("/")
def home():
    return "Meme Hunter PRO Online"


threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog), daemon=True).start()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
