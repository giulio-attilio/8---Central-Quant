# TREND PRO MTF H4/H1 + POI
# Versão: 2026-06-24-TRENDPRO-CENTRAL-QUANT-PADRAO-FINAL
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
# - DONKEY H4 adicionado como setup independente no H4.
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

BOT_NAME = os.environ.get("BOT_NAME", "Trend PRO Elite")

WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

TOKEN = (
    os.environ.get("TREND_PRO_ELITE_TOKEN")
    or os.environ.get("TRENDPRO_TELEGRAM_BOT_TOKEN")
    or os.environ.get("TRENDPRO_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
)

CHAT_ID = (
    os.environ.get("TREND_PRO_ELITE_CHAT_ID")
    or os.environ.get("TRENDPRO_TELEGRAM_CHAT_ID")
    or os.environ.get("TRENDPRO_CHAT_ID")
    or os.environ.get("TELEGRAM_CHAT_ID")
)

DONKEY_TOKEN = os.environ.get("DONKEY_TELEGRAM_BOT_TOKEN")
DONKEY_CHAT_ID = os.environ.get("DONKEY_TELEGRAM_CHAT_ID")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = os.environ.get("TRENDPRO_WATCHLIST_FILE", "watchlists/trendpro.json")

POSITIONS_KEY = "trendpro:positions"
SIGNALS_KEY = "trendpro:signals"
TRADES_KEY = "trendpro:trades"
DAILY_SUMMARY_KEY = "trendpro:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "trendpro:monthly_summary_sent"
REENTRY_BLOCK_KEY = "trendpro:reentry_block"
BE_MONITOR_KEY = "trendpro:be_monitor"
POI_COOLDOWN_KEY = "trendpro:poi_cooldown"
EARLY_COOLDOWN_KEY = "trendpro:early_cooldown"
DONKEY_COOLDOWN_KEY = "trendpro:donkey_cooldown"
DONKEY_CONFIRM_KEY = "trendpro:donkey_confirmed"
DONKEY_POI_COOLDOWN_KEY = "trendpro:donkey_poi_cooldown"
FUNNEL_KEY = "trendpro:funnel"

# ====================================================
# CONFIGURAÇÕES PRINCIPAIS
# ====================================================

TIMEFRAME_H4 = "4h"
TIMEFRAME_H1 = "1h"

# Central Quant:
# ENABLE_TRENDPRO=true liga o Trend PRO na Central e permite envio de sinais.
# TREND_PRO_ENABLED foi mantido apenas como compatibilidade legada.
def env_bool(name, default="false"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "sim", "on"}

TREND_PRO_ENABLED = env_bool("ENABLE_TRENDPRO", os.environ.get("TREND_PRO_ENABLED", "false"))
TREND_PRO_AUTO_TRADE = env_bool("TREND_PRO_AUTO_TRADE", "false")
STARTUP_SIGNAL_GRACE_SECONDS = int(os.environ.get("TRENDPRO_STARTUP_SIGNAL_GRACE_SECONDS", "600"))
SERVICE_STARTED_TS = time.time()


EMA_FAST = 9
EMA_MID = 21
EMA50 = 50
EMA200 = 200

EMA20 = 20

# ====================================================
# DONKEY H4 - SETUP INDEPENDENTE
# ====================================================
ENABLE_DONKEY_H4 = False
ENABLE_EARLY_DONKEY_H4 = False
DONKEY_TIMEFRAME = "4h"
DONKEY_EMA_FAST = 20
DONKEY_EMA_SLOW = 50
DONKEY_MACD_FAST = 12
DONKEY_MACD_SLOW = 26
DONKEY_MACD_SIGNAL = 9
DONKEY_BUFFER_PCT = 0.5  # 0,5% de margem no stop/trailing
DONKEY_SWING_LEN = 5
DONKEY_POI_COOLDOWN_SECONDS = 4 * 60 * 60  # 1 candle H4
DONKEY_RISK_USDT = float(os.environ.get("DONKEY_RISK_USDT", "10"))


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
MAX_RISK_H1 = 2.5

# Limite de exposição operacional.
MAX_OPEN_POSITIONS = 20

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

# EARLY continua ativo como trade mais ousado, com score menor.
EARLY_THRESHOLD = 50
EARLY_MIN_ADX_H4 = 15.0

# POI altera operacionalmente a posição; por isso também passa por filtro.
POI_THRESHOLD = 60
POI_MIN_ADX_H4 = 20.0
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
EARLYDX_H4_MIN = 20.0
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
    "last_watchlist_count": 0,
    "last_signals_sent": 0,
    "last_donkey_signals_sent": 0,
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




# ====================================================
# CAMADA DE RESILIÊNCIA API (CCXT SAFE FETCH)
# ====================================================

def safe_fetch_ohlcv(symbol, timeframe, limit, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso TRENDPRO OHLCV ({attempt+1}/{max_retries}) {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso TRENDPRO OHLCV genérico ({attempt+1}/{max_retries}) {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)

    HEALTH["last_warning"] = f"Falha OHLCV {symbol} {timeframe} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return []


def safe_fetch_ticker(symbol, max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.fetch_ticker(symbol)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso TRENDPRO Ticker ({attempt+1}/{max_retries}) {symbol}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso TRENDPRO Ticker genérico ({attempt+1}/{max_retries}) {symbol}: {e}")
            time.sleep(2 ** attempt)

    HEALTH["last_warning"] = f"Falha Ticker {symbol} após {max_retries} tentativas"
    print(HEALTH["last_warning"])
    return None


def safe_load_markets(max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.load_markets()
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"Aviso TRENDPRO load_markets ({attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"Aviso TRENDPRO load_markets genérico ({attempt+1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)

    HEALTH["last_warning"] = "Falha ao carregar markets da exchange após tentativas"
    print(HEALTH["last_warning"])
    return None

def carregar_watchlist():
    candidatos = [WATCHLIST_FILE]
    for item in ["watchlists/trendpro.json", "watchlist_trendpro.json", "watchlist.json"]:
        if item not in candidatos:
            candidatos.append(item)

    for arquivo in candidatos:
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        except Exception:
            pass

    print("ERRO WATCHLIST: nenhum arquivo válido encontrado para Trend PRO Elite")
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


# ====================================================
# FUNIL TREND PRO - DIAGNÓSTICO
# ====================================================

FUNIL_PADRAO = {
    "scanner_runs": 0,
    "ativos_analisados": 0,
    "startup_guard_ignorados": 0,
    "posicao_ativa_ignorados": 0,

    "normal_detectados": 0,
    "early_detectados": 0,
    "reentry_detectados": 0,
    "poi_detectados": 0,
    "recuperados_detectados": 0,

    "score_55_plus": 0,
    "score_70_plus": 0,
    "score_80_plus": 0,

    "reprovados_risco": 0,
    "reprovados_score": 0,
    "reprovados_adx": 0,
    "reprovados_volume": 0,
    "reprovados_bb": 0,
    "reprovados_spike": 0,
    "reprovados_cooldown": 0,

    "sinais_enviados": 0,
    "last_update": None,
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

def montar_funil_texto():
    f = funil_hoje()
    return (
        "📈 FUNIL TREND PRO DO DIA\n\n"
        f"Ativos analisados: {f.get('ativos_analisados', f.get('symbols_scanned', 0))}\n"
        f"Normal detectados: {f.get('normal_detectados', f.get('normal_detected', 0))}\n"
        f"Early detectados: {f.get('early_detectados', f.get('early_detected', 0))}\n"
        f"Reentry detectados: {f.get('reentry_detectados', f.get('reentry_detected', 0))}\n"
        f"POIs detectados: {f.get('poi_detectados', f.get('poi_detected', 0))}\n\n"
        f"Score 55+: {f.get('score_55_plus', 0)}\n"
        f"Score 70+: {f.get('score_70_plus', 0)}\n"
        f"Score 80+: {f.get('score_80_plus', 0)}\n\n"
        f"Reprovados por risco: {f.get('reprovados_risco', f.get('risk_rejected', 0))}\n"
        f"Reprovados por score: {f.get('reprovados_score', f.get('score_rejected', 0))}\n"
        f"Reprovados por ADX: {f.get('reprovados_adx', f.get('adx_rejected', 0))}\n"
        f"Reprovados por spike/dado suspeito: {f.get('reprovados_spike', f.get('spike_rejected', 0))}\n"
        f"Reprovados por cooldown: {f.get('reprovados_cooldown', f.get('cooldown_rejected', 0))}\n"
        f"Reprovados por posição ativa: {f.get('reprovados_posicao_ativa', f.get('active_position_rejected', 0))}\n"
        f"Ignorados por startup guard: {f.get('startup_guard_ignorados', f.get('startup_guard_ignored', 0))}\n\n"
        f"Sinais enviados: {f.get('sinais_enviados', f.get('signals_sent', 0))}"
    )


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
        base["last_update"] = data_hora_sp_str()

        dados[hoje] = base

        if len(dados) > 45:
            chaves = sorted(dados.keys())[-45:]
            dados = {k: dados[k] for k in chaves}

        salvar_funil(dados)
    except Exception as e:
        print("ERRO REGISTRAR FUNIL TRENDPRO:", e)

def registrar_score_funil(s):
    try:
        score = int(s.get("signal_score", 0))
        if score >= 55:
            registrar_funil("score_55_plus")
        if score >= 70:
            registrar_funil("score_70_plus")
        if score >= 80:
            registrar_funil("score_80_plus")
    except Exception:
        pass

def registrar_reprovacao_funil(motivo):
    motivo = str(motivo or "").lower()
    if "score" in motivo:
        registrar_funil("reprovados_score")
    elif "adx" in motivo:
        registrar_funil("reprovados_adx")
    elif "volume" in motivo:
        registrar_funil("reprovados_volume")
    elif "bollinger" in motivo or "bb" in motivo:
        registrar_funil("reprovados_bb")
    else:
        registrar_funil("reprovados_score")

def montar_funil():
    f = funil_hoje()

    return (
        "📈 FUNIL TREND PRO DO DIA\n\n"
        f"Scanner runs: {f.get('scanner_runs', 0)}\n"
        f"Ativos analisados: {f.get('ativos_analisados', 0)}\n"
        f"Startup guard ignorados: {f.get('startup_guard_ignorados', 0)}\n"
        f"Posição ativa ignorados: {f.get('posicao_ativa_ignorados', 0)}\n\n"

        f"Normal detectados: {f.get('normal_detectados', 0)}\n"
        f"Early detectados: {f.get('early_detectados', 0)}\n"
        f"Reentry detectados: {f.get('reentry_detectados', 0)}\n"
        f"POI detectados: {f.get('poi_detectados', 0)}\n"
        f"Recuperados detectados: {f.get('recuperados_detectados', 0)}\n\n"

        f"Score 55+: {f.get('score_55_plus', 0)}\n"
        f"Score 70+: {f.get('score_70_plus', 0)}\n"
        f"Score 80+: {f.get('score_80_plus', 0)}\n\n"

        f"Reprovados por risco: {f.get('reprovados_risco', 0)}\n"
        f"Reprovados por score: {f.get('reprovados_score', 0)}\n"
        f"Reprovados por ADX: {f.get('reprovados_adx', 0)}\n"
        f"Reprovados por volume: {f.get('reprovados_volume', 0)}\n"
        f"Reprovados por Bollinger: {f.get('reprovados_bb', 0)}\n"
        f"Reprovados por spike: {f.get('reprovados_spike', 0)}\n"
        f"Reprovados por cooldown: {f.get('reprovados_cooldown', 0)}\n\n"

        f"Sinais enviados: {f.get('sinais_enviados', 0)}\n"
        f"Última atualização: {f.get('last_update') or 'N/A'}"
    )


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


def carregar_donkey_cooldown():
    return redis_get_json(DONKEY_COOLDOWN_KEY, {})


def carregar_donkey_confirmed():
    return redis_get_json(DONKEY_CONFIRM_KEY, {})


def salvar_donkey_confirmed(dados):
    redis_set_json(DONKEY_CONFIRM_KEY, dados)


def donkey_confirmado_ja_enviado(symbol, side, timestamp):
    dados = carregar_donkey_confirmed()
    chave = f"{symbol}_{side}_{timestamp}"
    return bool(dados.get(chave, False))


def marcar_donkey_confirmado(symbol, side, timestamp):
    dados = carregar_donkey_confirmed()
    chave = f"{symbol}_{side}_{timestamp}"
    dados[chave] = True

    if len(dados) > 500:
        itens = list(dados.items())
        dados = dict(itens[-500:])

    salvar_donkey_confirmed(dados)



def salvar_donkey_cooldown(dados):
    redis_set_json(DONKEY_COOLDOWN_KEY, dados)


def carregar_donkey_poi_cooldown():
    return redis_get_json(DONKEY_POI_COOLDOWN_KEY, {})


def salvar_donkey_poi_cooldown(dados):
    redis_set_json(DONKEY_POI_COOLDOWN_KEY, dados)


def donkey_poi_em_cooldown(symbol, side):
    dados = carregar_donkey_poi_cooldown()
    chave = f"{symbol}_{side}"
    ultimo = float(dados.get(chave, 0))
    return time.time() - ultimo < DONKEY_POI_COOLDOWN_SECONDS


def marcar_donkey_poi_cooldown(symbol, side):
    dados = carregar_donkey_poi_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = time.time()
    if len(dados) > 300:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-300:])
    salvar_donkey_poi_cooldown(dados)


def donkey_em_cooldown(symbol, side, timestamp):
    dados = carregar_donkey_cooldown()
    chave = f"{symbol}_{side}"
    return int(dados.get(chave, 0)) == int(timestamp)


def marcar_donkey_cooldown(symbol, side, timestamp):
    dados = carregar_donkey_cooldown()
    chave = f"{symbol}_{side}"
    dados[chave] = int(timestamp)

    if len(dados) > 300:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-300:])

    salvar_donkey_cooldown(dados)


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


def existe_posicao_ativa(symbol):
    posicoes = carregar_posicoes()
    return symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO"


def pnl_pct(side, entry, price):
    if side == "LONG":
        return ((price - entry) / entry) * 100
    return ((entry - price) / entry) * 100


def atualizar_mfe_posicao(p, preco_atual):
    """
    MFE = Maximum Favorable Excursion.
    Guarda o maior PnL favorável que a posição já atingiu enquanto estava aberta.
    Isso ajuda a descobrir se o setup é ruim ou se a gestão está devolvendo lucro.
    """
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


def check_bool(valor):
    return "✅" if valor else "❌"


def fmt_risco(valor):
    try:
        return f"{float(valor):.2f}".replace(".", ",")
    except Exception:
        return str(valor)


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
    """
    Wrapper para garantir UTF-8 mesmo se send_telegram vier de telegram_utils.
    """
    msg = normalizar_texto(msg)

    try:
        send_telegram(msg)
    except UnicodeError:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
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





def safe_send_telegram_donkey(msg):
    """
    Envia mensagens exclusivas do Donkey para o bot/canal Donkey H4.
    Se DONKEY_TELEGRAM_BOT_TOKEN ou DONKEY_TELEGRAM_CHAT_ID não estiverem configurados,
    apenas registra no log e NÃO envia ao Trend PRO.
    """
    msg = normalizar_texto(msg)

    if not DONKEY_TOKEN or not DONKEY_CHAT_ID:
        print("DONKEY TELEGRAM NÃO CONFIGURADO:")
        print(msg)
        return

    payload = {
        "chat_id": DONKEY_CHAT_ID,
        "text": msg
    }

    try:
        requests.post(
            f"https://api.telegram.org/bot{DONKEY_TOKEN}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20
        )
    except Exception as e:
        print("ERRO TELEGRAM DONKEY:", e)


def eh_origem_donkey(p):
    origem = origem_msg_trade(p)
    return origem in [
        "DONKEY",
        "EARLY DONKEY",
        "POI DONKEY",
        "DONKEY CONFIRMADO"
    ]


def enviar_por_origem(p, msg):
    if eh_origem_donkey(p):
        safe_send_telegram_donkey(msg)
    else:
        safe_send_telegram(msg)



def is_donkey_signal_type(signal_type):
    return signal_type in ["DONKEY", "EARLY_DONKEY", "POI_DONKEY", "DONKEY_CONFIRMADO"]


def is_donkey_trade_event(t):
    signal_type = t.get("signal_type")
    event = t.get("event")
    if is_donkey_signal_type(signal_type):
        return True
    if event in ["POI_DONKEY", "DONKEY_CONFIRMADO"]:
        return True
    return False


def is_trend_trade_event(t):
    return not is_donkey_trade_event(t)


def mes_anterior_ref():
    hoje = agora_sp()
    primeiro_mes_atual = hoje.replace(day=1)
    ultimo_mes_anterior = primeiro_mes_atual - timedelta(days=1)
    return ultimo_mes_anterior.strftime("%Y-%m"), ultimo_mes_anterior.strftime("%m/%Y")


def montar_eventos_texto():
    hoje = data_hoje_sp_str()
    trades = carregar_trades()
    eventos = [
        t for t in trades
        if t.get("date") == hoje and t.get("event") in ["TP50", "TRAILING", "SL", "TRAIL", "BE", "CLOSE", "EXIT"]
    ]

    if not eventos:
        return "📋 EVENTOS TREND PRO DO DIA\n\nNenhum evento de gestão registrado hoje."

    linhas = ["📋 EVENTOS TREND PRO DO DIA", ""]
    for t in eventos[-40:]:
        simbolo = t.get("symbol_clean", t.get("symbol", "N/A"))
        evento = t.get("event", "N/A")
        lado = t.get("side", "")
        pnl = t.get("pnl", t.get("pnl_pct", t.get("result_pct", None)))
        if pnl is not None:
            linhas.append(f"{evento} - {simbolo} {lado} | {fmt_pct(pnl)}")
        else:
            linhas.append(f"{evento} - {simbolo} {lado}")
    return "\n".join(linhas)


def montar_resumo_mensal():
    mes_ref, mes_txt = mes_anterior_ref()
    trades = carregar_trades()

    do_mes = [
        t for t in trades
        if str(t.get("date", "")).startswith(mes_ref)
    ]

    entries = [t for t in do_mes if t.get("event") == "ENTRY"]
    pois = [t for t in do_mes if t.get("event") == "POI"]
    pois_donkey = [t for t in do_mes if t.get("event") == "POI_DONKEY"]
    exits = [t for t in do_mes if t.get("event") in ["EXIT", "SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in do_mes if t.get("event") == "TP50"]
    trails = [t for t in do_mes if t.get("event") == "TRAILING"]
    donkey_confirmados = [t for t in do_mes if t.get("event") == "DONKEY_CONFIRMADO"]

    longs = [t for t in entries if t.get("side") == "LONG"]
    shorts = [t for t in entries if t.get("side") == "SHORT"]
    earlys = [t for t in entries if t.get("signal_type") == "EARLY"]
    recuperados = [t for t in entries if t.get("signal_type") == "RECUPERADO"]
    reentries = [t for t in entries if t.get("signal_type") == "REENTRY"]
    donkeys = [t for t in entries if t.get("signal_type") == "DONKEY"]
    early_donkeys = [t for t in entries if t.get("signal_type") == "EARLY_DONKEY"]

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
    mfe_medio = (sum(float(t.get("mfe_max_pct", 0)) for t in exits) / len(exits)) if exits else 0
    devolucao_media = (sum(float(t.get("mfe_gave_back_pct", 0)) for t in exits) / len(exits)) if exits else 0
    mfe_winners = (sum(float(t.get("mfe_max_pct", 0)) for t in wins) / len(wins)) if wins else 0
    mfe_losers = (sum(float(t.get("mfe_max_pct", 0)) for t in losses) / len(losses)) if losses else 0
    mfe_breakevens = (sum(float(t.get("mfe_max_pct", 0)) for t in bes) / len(bes)) if bes else 0

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
        f"DONKEY H4: {len(donkeys)}\n"
        f"EARLY DONKEY H4: {len(early_donkeys)}\n"
        f"DONKEY CONFIRMADOS: {len(donkey_confirmados)}\n"
        f"POIs H1: {len(pois)}\n"
        f"POIs DONKEY: {len(pois_donkey)}\n\n"
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
        f"MFE médio: {fmt_pct(mfe_medio)}\n"
        f"MFE médio dos wins: {fmt_pct(mfe_winners)}\n"
        f"MFE médio dos losses: {fmt_pct(mfe_losers)}\n"
        f"MFE médio dos BEs: {fmt_pct(mfe_breakevens)}\n"
        f"Devolução média: {fmt_pct(devolucao_media)}\n\n"
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



def startup_signal_guard_active():
    return time.time() - SERVICE_STARTED_TS < STARTUP_SIGNAL_GRACE_SECONDS




# ====================================================
# WATCHDOG
# ====================================================

def parse_data_hora_sp(valor):
    """
    Converte datas no padrão do HEALTH: dd/mm/YYYY HH:MM.
    Retorna None se o campo ainda não existe ou estiver inválido.
    """
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

    ok = (
        HEALTH.get("last_error") is None and
        not scanner_stalled and
        not management_stalled
    )

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
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "minutes_since_scanner": minutes_since_scanner,
        "minutes_since_management": minutes_since_management,
        "last_error": HEALTH.get("last_error"),
        "last_warning": HEALTH.get("last_warning"),
        "watchlist_file": WATCHLIST_FILE,
        "watchlist_total": HEALTH.get("watchlist_total"),
        "watchlist_valida": HEALTH.get("watchlist_valid"),
        "watchlist_invalida": len(HEALTH.get("watchlist_invalid", [])),
        "watchlist_invalidos": HEALTH.get("watchlist_invalid", []),
        "telegram_configured": bool(TOKEN and CHAT_ID),
        "startup_signal_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
        "startup_signal_guard_active": startup_signal_guard_active(),
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
    watchdog = montar_watchdog_status()

    payload = {
        "ok": watchdog.get("ok", HEALTH.get("last_error") is None),
        "uptime_horas": calcular_uptime_horas(),
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
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
        "be_trigger_r": BE_TRIGGER_R,
        "resumos_separados": True,
        "mfe_enabled": True,
        "mfe_split_enabled": True,
        "service_mode": "TREND_PRO_ONLY",
        "bot": BOT_NAME,
        "watchdog_status": watchdog.get("status"),
        "minutes_since_scanner": watchdog.get("minutes_since_scanner"),
        "minutes_since_management": watchdog.get("minutes_since_management"),
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_watchdog_alert": HEALTH.get("last_watchdog_alert"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "funnel_enabled": True,
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
    if origem == "DONKEY":
        return "DONKEY H4"
    if origem == "EARLY_DONKEY":
        return "EARLY DONKEY"
    if origem == "POI_DONKEY":
        return "POI DONKEY"

    return str(origem)


def origem_msg_trade(p):
    origem = origem_trade_txt(p)

    if origem == "NORMAL":
        return "ELITE"

    if origem == "DONKEY H4":
        return "DONKEY"

    return origem

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
    df["ema20"] = df["close"].ewm(span=EMA20, adjust=False).mean()
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

    macd_fast = df["close"].ewm(span=DONKEY_MACD_FAST, adjust=False).mean()
    macd_slow = df["close"].ewm(span=DONKEY_MACD_SLOW, adjust=False).mean()
    df["macd"] = macd_fast - macd_slow
    df["macd_signal"] = df["macd"].ewm(span=DONKEY_MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

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
    if score >= 55:
        registrar_funil("score_55_plus")
    if score >= 70:
        registrar_funil("score_70_plus")
    if score >= 80:
        registrar_funil("score_80_plus")
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
        registrar_funil("reprovados_score")
        return False, f"{label}: Score abaixo do mínimo: {score}/{threshold}"

    if adx_h4 < min_adx_h4:
        registrar_funil("reprovados_adx")
        return False, f"{label}: ADX H4 abaixo do mínimo: {adx_h4:.2f}/{min_adx_h4:.2f}"

    if require_high_volume and not volume_ok:
        return False, f"{label}: Volume H1 baixo"

    if require_bb_expanding and not bb_ok:
        return False, f"{label}: Bollinger H1 comprimindo"

    return True, f"{label}: Aprovado no filtro Trend PRO Elite"


# ====================================================
# SINAL H1 ALINHADO AO H4
# ====================================================

def analisar_sinal_h1(symbol):
    ohlcv_h1 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300)
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300)

    if not ohlcv_h1 or not ohlcv_h4 or len(ohlcv_h1) < 50 or len(ohlcv_h4) < 50:
        HEALTH["last_warning"] = f"OHLCV insuficiente para {nome_limpo(symbol)}"
        return None, pd.DataFrame(), pd.DataFrame()

    df_h1 = pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"])
    df_h4 = pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"])

    df_h1 = preparar_df(df_h1)
    df_h4 = preparar_df(df_h4)

    timestamp = int(df_h1.iloc[-2]["time"])
    candle_h1 = df_h1.iloc[-2]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle_h1.get("spike_suspeito", False)):
        registrar_funil("reprovados_spike")
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
        registrar_funil("reprovados_risco")
        print(f"SINAL IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None, df_h1, df_h4

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle_h1)

    registrar_funil("normal_detectados")

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

    if not ohlcv_h1 or not ohlcv_h4 or len(ohlcv_h1) < 50 or len(ohlcv_h4) < 50:
        HEALTH["last_warning"] = f"OHLCV insuficiente para {nome_limpo(symbol)}"
        return None

    df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))

    candle = df_h1.iloc[-2]
    prev = df_h1.iloc[-3]
    candle_h4 = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        registrar_funil("reprovados_spike")
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
        registrar_funil("reprovados_cooldown")
        return None

    entry = close
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100

    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1:
        registrar_funil("reprovados_risco")
        print(f"EARLY IGNORADO POR RISCO ALTO: {nome_limpo(symbol)} | {risk_pct:.2f}%")
        return None

    pontos, qualidade = calcular_qualidade(signal, h4_state, candle)

    registrar_funil("early_detectados")
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
# DONKEY H4
# ====================================================

def calcular_donkey_position_size(entry, sl):
    """
    Calcula o tamanho teórico da posição com base no risco fixo em USDT.
    Ajuste DONKEY_RISK_USDT no ambiente se quiser outro valor.
    """
    try:
        risk_abs = abs(float(entry) - float(sl))
        if risk_abs <= 0:
            return None
        return float(DONKEY_RISK_USDT) / risk_abs
    except Exception:
        return None


def calcular_donkey_trailing(symbol, side):
    ohlcv = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=120)
    df = preparar_df(pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"]))

    ultimos = df.iloc[-(DONKEY_SWING_LEN + 1):-1]

    if side == "LONG":
        swing_low = float(ultimos["low"].min())
        return swing_low * (1 - DONKEY_BUFFER_PCT / 100)

    swing_high = float(ultimos["high"].max())
    return swing_high * (1 + DONKEY_BUFFER_PCT / 100)


def detectar_donkey_h4(symbol):
    """
    DONKEY H4:
    BUY: candle H4 fechado acima da EMA20, EMA20 acima da EMA50 e MACD acima de zero.
    SELL: candle H4 fechado abaixo da EMA20, EMA20 abaixo da EMA50 e MACD abaixo de zero.
    Não envia novo DONKEY enquanto houver posição aberta no ativo.
    """
    if not ENABLE_DONKEY_H4:
        return None

    if existe_posicao_ativa(symbol):
        return None

    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"DONKEY IGNORADO POR CANDLE H4 SUSPEITO: {nome_limpo(symbol)}")
        return None

    timestamp = int(candle["time"])
    close = float(candle["close"])
    high = float(candle["high"])
    low = float(candle["low"])
    ema20 = float(candle["ema20"])
    ema50 = float(candle["ema50"])
    macd = float(candle["macd"])

    signal = None
    if close > ema20 and ema20 > ema50 and macd > 0:
        signal = "LONG"
    if close < ema20 and ema20 < ema50 and macd < 0:
        signal = "SHORT"
    if not signal:
        return None

    if donkey_em_cooldown(symbol, signal, timestamp):
        return None

    entry = close
    if signal == "LONG":
        sl = low * (1 - DONKEY_BUFFER_PCT / 100)
        risk_abs = abs(entry - sl)
        tp50 = entry + risk_abs * TP50_R
    else:
        sl = high * (1 + DONKEY_BUFFER_PCT / 100)
        risk_abs = abs(sl - entry)
        tp50 = entry - risk_abs * TP50_R

    if risk_abs <= 0:
        return None

    risk_pct = risk_abs / entry * 100
    marcar_donkey_cooldown(symbol, signal, timestamp)

    return {
        "type": "DONKEY",
        "signal_type": "DONKEY",
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
        "h4_state": 1 if signal == "LONG" else -1,
        "h1_state": 0,
        "adx_h4": float(candle.get("adx", 0)),
        "adx_h1": 0.0,
        "volume_ok": bool(candle.get("volume_ok", False)),
        "bb_ok": bool(candle.get("bb_ok", False)),
        "qualidade_pontos": 0,
        "qualidade": "DONKEY H4 🐴",
        "signal_score": 0,
        "elite_candidate": False,
        "donkey_risk_usdt": float(DONKEY_RISK_USDT),
        "donkey_ema20": ema20,
        "donkey_ema50": ema50,
        "donkey_macd": macd
    }


def detectar_early_donkey_h4(symbol):
    """
    EARLY DONKEY H4:
    - BUY: candle H4 fechado acima da EMA20 e MACD acima de zero, mas EMA20 ainda <= EMA50.
    - SELL: candle H4 fechado abaixo da EMA20 e MACD abaixo de zero, mas EMA20 ainda >= EMA50.
    - Serve para estatística da entrada antecipada antes da confirmação EMA20/EMA50.
    """
    if not ENABLE_EARLY_DONKEY_H4:
        return None

    if existe_posicao_ativa(symbol):
        return None

    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"EARLY DONKEY IGNORADO POR CANDLE H4 SUSPEITO: {nome_limpo(symbol)}")
        return None

    timestamp = int(candle["time"])
    close = float(candle["close"])
    high = float(candle["high"])
    low = float(candle["low"])
    ema20 = float(candle["ema20"])
    ema50 = float(candle["ema50"])
    macd = float(candle["macd"])

    signal = None

    if close > ema20 and macd > 0 and ema20 <= ema50:
        signal = "LONG"

    if close < ema20 and macd < 0 and ema20 >= ema50:
        signal = "SHORT"

    if not signal:
        return None

    if donkey_em_cooldown(symbol, f"EARLY_{signal}", timestamp):
        return None

    entry = close

    if signal == "LONG":
        sl = low * (1 - DONKEY_BUFFER_PCT / 100)
        risk_abs = abs(entry - sl)
        tp50 = entry + risk_abs * TP50_R
    else:
        sl = high * (1 + DONKEY_BUFFER_PCT / 100)
        risk_abs = abs(sl - entry)
        tp50 = entry - risk_abs * TP50_R

    if risk_abs <= 0:
        return None

    risk_pct = risk_abs / entry * 100
    marcar_donkey_cooldown(symbol, f"EARLY_{signal}", timestamp)

    return {
        "type": "EARLY_DONKEY",
        "signal_type": "EARLY_DONKEY",
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
        "h4_state": 1 if signal == "LONG" else -1,
        "h1_state": 0,
        "adx_h4": float(candle.get("adx", 0)),
        "adx_h1": 0.0,
        "volume_ok": bool(candle.get("volume_ok", False)),
        "bb_ok": bool(candle.get("bb_ok", False)),
        "qualidade_pontos": 0,
        "qualidade": "EARLY DONKEY H4 🐴",
        "signal_score": 0,
        "elite_candidate": False,
        "donkey_risk_usdt": float(DONKEY_RISK_USDT),
        "donkey_ema20": ema20,
        "donkey_ema50": ema50,
        "donkey_macd": macd
    }


def detectar_confirmacao_donkey_h4(symbol, posicao):
    """
    DONKEY CONFIRMADO:
    - Não abre nova posição.
    - Só registra estatística quando uma posição EARLY_DONKEY vira DONKEY completo.
    - BUY confirmado: close H4 > EMA20, EMA20 > EMA50, MACD > 0.
    - SELL confirmado: close H4 < EMA20, EMA20 < EMA50, MACD < 0.
    """
    if posicao.get("signal_type") != "EARLY_DONKEY":
        return None

    side = posicao.get("side")
    if side not in ["LONG", "SHORT"]:
        return None

    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        return None

    timestamp = int(candle["time"])
    close = float(candle["close"])
    ema20 = float(candle["ema20"])
    ema50 = float(candle["ema50"])
    macd = float(candle["macd"])

    if donkey_confirmado_ja_enviado(symbol, side, timestamp):
        return None

    confirmado = False

    if side == "LONG":
        confirmado = close > ema20 and ema20 > ema50 and macd > 0
    else:
        confirmado = close < ema20 and ema20 < ema50 and macd < 0

    if not confirmado:
        return None

    marcar_donkey_confirmado(symbol, side, timestamp)

    return {
        "type": "DONKEY_CONFIRMADO",
        "signal_type": "DONKEY_CONFIRMADO",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": timestamp,
        "entry": float(posicao.get("entry", close)),
        "current_price": close,
        "sl": float(posicao.get("sl", 0)),
        "tp50": float(posicao.get("tp50", 0)),
        "risk_pct": float(posicao.get("risk_pct", 0)),
        "ema20": ema20,
        "ema50": ema50,
        "macd": macd,
        "early_entry": float(posicao.get("entry", close))
    }


def detectar_poi_donkey_h4(symbol, posicao):
    """
    POI DONKEY H4:
    BUY: posição DONKEY LONG, candle H4 toca EMA20 e fecha acima dela, EMA20 > EMA50, MACD > 0.
    SELL: posição DONKEY SHORT, candle H4 toca EMA20 e fecha abaixo dela, EMA20 < EMA50, MACD < 0.
    """
    if not ENABLE_DONKEY_H4:
        return None

    if posicao.get("signal_type") not in ["DONKEY", "EARLY_DONKEY"]:
        return None

    side = posicao.get("side")
    if side not in ["LONG", "SHORT"]:
        return None

    if donkey_poi_em_cooldown(symbol, side):
        return None

    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]

    if bool(candle.get("spike_suspeito", False)):
        print(f"POI DONKEY IGNORADO POR CANDLE H4 SUSPEITO: {nome_limpo(symbol)}")
        return None

    timestamp = int(candle["time"])
    close = float(candle["close"])
    high = float(candle["high"])
    low = float(candle["low"])
    ema20 = float(candle["ema20"])
    ema50 = float(candle["ema50"])
    macd = float(candle["macd"])

    if not (low <= ema20 <= high):
        return None

    if side == "LONG":
        confirmado = close > ema20 and ema20 > ema50 and macd > 0
    else:
        confirmado = close < ema20 and ema20 < ema50 and macd < 0

    if not confirmado:
        return None

    entry = close
    sl = float(posicao["sl"])
    risk_abs = abs(entry - sl)
    if risk_abs <= 0:
        return None

    risk_pct = risk_abs / entry * 100
    tp50 = entry + risk_abs * TP50_R if side == "LONG" else entry - risk_abs * TP50_R

    marcar_donkey_poi_cooldown(symbol, side)

    return {
        "type": "POI_DONKEY",
        "signal_type": "POI_DONKEY",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": timestamp,
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "h4_state": 1 if side == "LONG" else -1,
        "h1_state": 0,
        "adx_h4": float(candle.get("adx", 0)),
        "adx_h1": 0.0,
        "volume_ok": bool(candle.get("volume_ok", False)),
        "bb_ok": bool(candle.get("bb_ok", False)),
        "qualidade_pontos": 0,
        "qualidade": "POI DONKEY H4 🐴",
        "signal_score": 0,
        "elite_candidate": False
    }


def gerenciar_donkey_position(symbol, p, preco_atual):
    """
    Gestão exclusiva do DONKEY H4.
    Retorna True se alterou/encerrou a posição.
    """
    side = p["side"]
    entry = float(p["entry"])
    sl = float(p["sl"])

    # Stop em tempo real no stop atual.
    if not stop_em_carencia(p):
        if side == "LONG" and preco_atual <= sl:
            resultado = pnl_pct(side, entry, sl)
            enviar_stop(p, preco_atual, sl, resultado)

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
                "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado,
                "result_type": "WIN" if resultado > 0 else "LOSS",
                "signal_type": "DONKEY",
                "closed_by": "DONKEY_STOP"
            })

            p["closed_at"] = time.time()
            p["closed_datetime"] = data_hora_sp_str()
            p["closed_reason"] = "DONKEY_STOP"
            p["status"] = "ENCERRADO"
            return True

        if side == "SHORT" and preco_atual >= sl:
            resultado = pnl_pct(side, entry, sl)
            enviar_stop(p, preco_atual, sl, resultado)

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
                "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado,
                "result_type": "WIN" if resultado > 0 else "LOSS",
                "signal_type": "DONKEY",
                "closed_by": "DONKEY_STOP"
            })

            p["closed_at"] = time.time()
            p["closed_datetime"] = data_hora_sp_str()
            p["closed_reason"] = "DONKEY_STOP"
            p["status"] = "ENCERRADO"
            return True

    # Invalidação por candle H4 fechado além da EMA20.
    try:
        ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=120)
        df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
        candle_h4 = df_h4.iloc[-2]
        close_h4 = float(candle_h4["close"])
        ema20_h4 = float(candle_h4["ema20"])

        invalidou = (
            (side == "LONG" and close_h4 < ema20_h4) or
            (side == "SHORT" and close_h4 > ema20_h4)
        )

        if invalidou:
            resultado = pnl_pct(side, entry, close_h4)
            enviar_stop(p, close_h4, close_h4, resultado)

            registrar_evento_trade({
                "event": "CLOSE",
                "date": data_hoje_sp_str(),
                "datetime": data_hora_sp_str(),
                "symbol": symbol,
                "symbol_clean": p["symbol_clean"],
                "side": side,
                "entry": entry,
                "exit": close_h4,
                "pnl": resultado,
                "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado,
                "result_type": "WIN" if resultado > 0 else "LOSS",
                "signal_type": "DONKEY",
                "closed_by": "DONKEY_EMA20_CLOSE"
            })

            p["closed_at"] = time.time()
            p["closed_datetime"] = data_hora_sp_str()
            p["closed_reason"] = "DONKEY_EMA20_CLOSE"
            p["status"] = "ENCERRADO"
            return True

    except Exception as e:
        print(f"ERRO INVALIDAÇÃO DONKEY {nome_limpo(symbol)}:", e)

    # TP50 informativo/operacional em 1R.
    # Importante: retorna True logo após enviar a mensagem para persistir
    # tp50_hit/tp50_message_sent no Redis e evitar duplicação a cada ciclo.
    try:
        tp50 = float(p["tp50"])

        if not p.get("tp50_hit") and not p.get("tp50_message_sent"):
            if side == "LONG" and preco_atual >= tp50:
                p["tp50_hit"] = True
                p["tp50_message_sent"] = True
                p["status"] = "DONKEY TRAILING"
                p["tp50_activated_at"] = time.time()
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
                    "signal_type": "DONKEY"
                })

                return True

            if side == "SHORT" and preco_atual <= tp50:
                p["tp50_hit"] = True
                p["tp50_message_sent"] = True
                p["status"] = "DONKEY TRAILING"
                p["tp50_activated_at"] = time.time()
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
                    "signal_type": "DONKEY"
                })

                return True

    except Exception as e:
        print(f"ERRO TP50 DONKEY {nome_limpo(symbol)}:", e)

    # Trailing por swing H4 com margem 0,5%.
    try:
        novo_stop = calcular_donkey_trailing(symbol, side)

        if side == "LONG" and novo_stop > float(p["sl"]):
            p["sl"] = novo_stop
            p["status"] = "DONKEY TRAILING"
            p["trailing_activated_at"] = time.time()
            enviar_donkey_trailing(p, novo_stop)

            registrar_evento_trade({
                "event": "TRAILING",
                "date": data_hoje_sp_str(),
                "datetime": data_hora_sp_str(),
                "symbol": symbol,
                "symbol_clean": p["symbol_clean"],
                "side": side,
                "new_stop": novo_stop,
                "signal_type": "DONKEY"
            })

            return True

        if side == "SHORT" and novo_stop < float(p["sl"]):
            if p.get("last_trailing_message_stop") == novo_stop:
                return False
            p["sl"] = novo_stop
            p["status"] = "DONKEY TRAILING"
            p["trailing_activated_at"] = time.time()
            p["last_trailing_message_stop"] = novo_stop
            enviar_donkey_trailing(p, novo_stop)

            registrar_evento_trade({
                "event": "TRAILING",
                "date": data_hoje_sp_str(),
                "datetime": data_hora_sp_str(),
                "symbol": symbol,
                "symbol_clean": p["symbol_clean"],
                "side": side,
                "new_stop": novo_stop,
                "signal_type": "DONKEY"
            })

            return True

    except Exception as e:
        print(f"ERRO TRAILING DONKEY {nome_limpo(symbol)}:", e)

    return False


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
    tipo = " RECUPERADO" if s.get("signal_type") == "RECUPERADO" else ""

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


def enviar_donkey(s):
    emoji = "🐴 🟢" if s["signal"] == "LONG" else "🐴 🔴"
    nome = "DONKEY BUY" if s["signal"] == "LONG" else "DONKEY SELL"

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%"
    )

    safe_send_telegram_donkey(msg)


def enviar_early_donkey(s):
    emoji = "🐴 🚀 🟢" if s["signal"] == "LONG" else "🐴 🚀 🔴"
    nome = "EARLY DONKEY BUY" if s["signal"] == "LONG" else "EARLY DONKEY SELL"

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%"
    )

    safe_send_telegram_donkey(msg)


def enviar_donkey_confirmado(s):
    emoji = "🐴 ✅ 🟢" if s["signal"] == "LONG" else "🐴 ✅ 🔴"
    nome = "DONKEY BUY CONFIRMADO" if s["signal"] == "LONG" else "DONKEY SELL CONFIRMADO"

    msg = (
        f"{emoji} {nome} - {s['symbol_clean']}\n\n"
        f"Early Donkey virou Donkey completo ✅\n\n"
        f"Entrada Early:\n{fmt_br(s['early_entry'])}\n\n"
        f"Preço atual:\n{fmt_br(s['current_price'])}\n\n"
        f"SL atual:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}"
    )

    safe_send_telegram_donkey(msg)


def enviar_poi_donkey(s):
    msg = (
        f"🐴 🔵 POI DONKEY - {s['symbol_clean']}\n\n"
        f"Entrada:\n{fmt_br(s['entry'])}\n\n"
        f"SL:\n{fmt_br(s['sl'])}\n\n"
        f"TP50:\n{fmt_br(s['tp50'])}\n\n"
        f"{risco_label(s['risk_pct'])} - Risco: {fmt_risco(s['risk_pct'])}%"
    )

    safe_send_telegram_donkey(msg)


def enviar_donkey_trailing(p, novo_stop):
    lucro_protegido = pnl_pct(
        p["side"],
        float(p["entry"]),
        float(novo_stop)
    )

    safe_send_telegram_donkey(
        f"🐴 🟣 TRAILING DONKEY - {p['symbol_clean']}\n\n"
        f"Novo Stop:\n{fmt_br(novo_stop)}\n\n"
        f"Lucro protegido:\n{fmt_pct(lucro_protegido)}"
    )


def enviar_tp50(p, tp50, pnl_tp):
    origem = origem_msg_trade(p)

    if origem == "DONKEY":
        status = "Aguardando trailing H4 ✅"
    else:
        status = "Aguardando Breakeven 1,5R ✅"

    enviar_por_origem(p, 
        f"🎯 TP50 {origem} - {p['symbol_clean']}\n\n"
        f"Parcial 50% realizada ✅\n\n"
        f"Resultado parcial:\n"
        f"{fmt_pct(pnl_tp)}\n\n"
        f"Status:\n"
        f"{status}"
    )


def enviar_trailing_ativado(p, novo_stop):
    origem = origem_msg_trade(p)
    lucro_protegido = pnl_pct(p["side"], float(p["entry"]), float(novo_stop))

    enviar_por_origem(p, 
        f"🟣 TRAILING ATIVADO {origem} - {p['symbol_clean']}\n\n"
        f"Novo Stop:\n{fmt_br(novo_stop)}\n\n"
        f"Lucro protegido:\n{fmt_pct(lucro_protegido)}\n\n"
        f"Status:\nBreakeven ativo ✅"
    )


def enviar_trailing(p, novo_stop):
    origem = origem_msg_trade(p)
    lucro_protegido = pnl_pct(p["side"], float(p["entry"]), float(novo_stop))

    safe_send_telegram(
        f"🟣 TRAILING {origem} - {p['symbol_clean']}\n\n"
        f"Novo Stop:\n{fmt_br(novo_stop)}\n\n"
        f"Lucro protegido:\n{fmt_pct(lucro_protegido)}"
    )


def enviar_stop(p, preco_atual, stop, resultado):
    origem = origem_msg_trade(p)
    titulo_base = "🟣 TRAIL STOP" if resultado >= 0 else "🟠 STOP"

    enviar_por_origem(p, 
        f"{titulo_base} {origem} - {p['symbol_clean']}\n\n"
        f"Preço atual:\n{fmt_br(preco_atual)}\n\n"
        f"Saída:\n{fmt_br(stop)}\n\n"
        f"Resultado:\n{fmt_pct(resultado)}"
    )


# ====================================================
# POSIÇÕES
# ====================================================

def registrar_posicao(s):
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
        "tp50": s["tp50"],
        "risk_abs": s["risk_abs"],
        "risk_pct": s["risk_pct"],
        "status": "ATIVO",
        "mfe_max_pct": 0.0,
        "mfe_updated_at": None,
        "breakeven": False,
        "tp50_hit": False,
        "tp50_message_sent": False,
        "be_trigger_message_sent": False,
        "timestamp": s["timestamp"],
        "created_at": time.time(),
        "active_since": time.time(),
        "breakeven_activated_at": None,
        "last_trailing_message_stop": None,
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
        "donkey_position_size": s.get("donkey_position_size"),
        "donkey_risk_usdt": s.get("donkey_risk_usdt")
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
        "elite_candidate": bool(s.get("elite_candidate", s.get("signal_score", calcular_signal_score(s)) >= ELITE_THRESHOLD)),
        "donkey_position_size": s.get("donkey_position_size"),
        "donkey_risk_usdt": s.get("donkey_risk_usdt")
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


def gerenciar_posicoes():
    posicoes = carregar_posicoes()
    alterou = False

    for symbol, p in list(posicoes.items()):
        if p.get("status") == "ENCERRADO":
            continue

        try:
            ticker = safe_fetch_ticker(symbol)
            preco_atual = float(ticker["last"])

            if atualizar_mfe_posicao(p, preco_atual):
                alterou = True

            if p.get("signal_type") in ["DONKEY", "EARLY_DONKEY", "POI_DONKEY", "DONKEY_CONFIRMADO"]:
                # Serviço Trend PRO não gerencia posições Donkey.
                continue

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
                        "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                        "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado,
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
                        "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                        "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado,
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
            if not p.get("tp50_hit") and not p.get("tp50_message_sent"):
                if side == "LONG" and preco_atual >= tp50:
                    p["tp50_hit"] = True
                    p["tp50_message_sent"] = True
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
                    p["tp50_message_sent"] = True
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
            if p.get("tp50_hit") and not p.get("breakeven") and not p.get("be_trigger_message_sent"):
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
                        p["be_trigger_message_sent"] = True
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
                        p["be_trigger_message_sent"] = True
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
                    if p.get("last_trailing_message_stop") == novo_stop:
                        continue
                    p["sl"] = novo_stop
                    p["trailing_activated_at"] = time.time()
                    p["last_trailing_message_stop"] = novo_stop
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
                    if p.get("last_trailing_message_stop") == novo_stop:
                        continue
                    p["sl"] = novo_stop
                    p["trailing_activated_at"] = time.time()
                    p["last_trailing_message_stop"] = novo_stop
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
    trades_trend = [t for t in trades if is_trend_trade_event(t)]

    entradas = [t for t in trades_trend if t.get("date") == hoje and t.get("event") == "ENTRY"]
    pois = [t for t in trades_trend if t.get("date") == hoje and t.get("event") == "POI"]
    earlys = [t for t in entradas if t.get("signal_type") == "EARLY"]
    recuperados = [t for t in entradas if t.get("signal_type") == "RECUPERADO"]
    reentries = [t for t in entradas if t.get("signal_type") == "REENTRY"]
    fechados = [t for t in trades_trend if t.get("date") == hoje and t.get("event") == "CLOSE"]
    tp50s = [t for t in trades_trend if t.get("date") == hoje and t.get("event") == "TP50"]
    trailings = [t for t in trades_trend if t.get("date") == hoje and t.get("event") == "TRAILING"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)
    mfe_medio = (sum(float(t.get("mfe_max_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0
    devolucao_media = (sum(float(t.get("mfe_gave_back_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0
    mfe_winners = (sum(float(t.get("mfe_max_pct", 0)) for t in wins) / len(wins)) if wins else 0
    mfe_losers = (sum(float(t.get("mfe_max_pct", 0)) for t in losses) / len(losses)) if losses else 0
    mfe_breakevens = (sum(float(t.get("mfe_max_pct", 0)) for t in bes) / len(bes)) if bes else 0

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]
    melhor = max(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None
    pior = min(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None

    linhas = [
        "📈 RESUMO TREND PRO",
        data_br,
        "",
        f"Sinais H1 do dia: {len(entradas)}",
        f"LONG: {len(longs)}",
        f"SHORT: {len(shorts)}",
        f"EARLY: {len(earlys)}",
        f"RECUPERADO: {len(recuperados)}",
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
        fmt_pct(pnl_total),
        "",
        "MFE médio:",
        fmt_pct(mfe_medio),
        "MFE médio dos wins:",
        fmt_pct(mfe_winners),
        "MFE médio dos losses:",
        fmt_pct(mfe_losers),
        "MFE médio dos BEs:",
        fmt_pct(mfe_breakevens),
        "Devolução média:",
        fmt_pct(devolucao_media),
        "",
        "Melhor trade:",
        f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('pnl', 0))}" if melhor else "N/A",
        "",
        "Pior trade:",
        f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('pnl', 0))}" if pior else "N/A",
    ]

    posicoes = carregar_posicoes()
    ativos = []
    for symbol, p in posicoes.items():
        if p.get("status") == "ENCERRADO":
            continue
        if is_donkey_signal_type(p.get("signal_type")):
            continue
        try:
            ticker = safe_fetch_ticker(symbol)
            preco = float(ticker["last"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
            ativos.append(f"{p['symbol_clean']} {p['side']} | PnL {fmt_pct(pnl)}")
        except Exception:
            ativos.append(f"{p.get('symbol_clean', symbol)} {p.get('side', '')} | PnL N/A")

    funil = funil_hoje()
    linhas += [
        "",
        "📈 FUNIL TREND PRO DO DIA",
        f"Ativos analisados: {funil.get('ativos_analisados', 0)}",
        f"Normal detectados: {funil.get('normal_detectados', 0)}",
        f"Early detectados: {funil.get('early_detectados', 0)}",
        f"Reentry detectados: {funil.get('reentry_detectados', 0)}",
        f"POI detectados: {funil.get('poi_detectados', 0)}",
        f"Score 55+: {funil.get('score_55_plus', 0)}",
        f"Score 70+: {funil.get('score_70_plus', 0)}",
        f"Score 80+: {funil.get('score_80_plus', 0)}",
        f"Reprovados por risco: {funil.get('reprovados_risco', 0)}",
        f"Reprovados por score: {funil.get('reprovados_score', 0)}",
        f"Reprovados por ADX: {funil.get('reprovados_adx', 0)}",
        f"Reprovados por spike: {funil.get('reprovados_spike', 0)}",
        f"Sinais enviados: {funil.get('sinais_enviados', 0)}",
    ]

    linhas += ["", f"Trades Trend PRO ainda ativos: {len(ativos)}"]
    if ativos:
        linhas.extend(ativos[:20])

    return "\n".join(linhas)


def montar_resumo_donkey():
    hoje = data_hoje_sp_str()
    data_br = agora_sp().strftime("%d/%m/%Y")
    trades = carregar_trades()
    trades_donkey = [t for t in trades if is_donkey_trade_event(t)]

    entradas = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "ENTRY"]
    donkeys = [t for t in entradas if t.get("signal_type") == "DONKEY"]
    early_donkeys = [t for t in entradas if t.get("signal_type") == "EARLY_DONKEY"]
    pois_donkey = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "POI_DONKEY"]
    confirmados = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "DONKEY_CONFIRMADO"]
    fechados = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "CLOSE"]
    tp50s = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "TP50"]
    trailings = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "TRAILING"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)
    mfe_medio = (sum(float(t.get("mfe_max_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0
    devolucao_media = (sum(float(t.get("mfe_gave_back_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0
    mfe_winners = (sum(float(t.get("mfe_max_pct", 0)) for t in wins) / len(wins)) if wins else 0
    mfe_losers = (sum(float(t.get("mfe_max_pct", 0)) for t in losses) / len(losses)) if losses else 0
    mfe_breakevens = (sum(float(t.get("mfe_max_pct", 0)) for t in bes) / len(bes)) if bes else 0

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]
    melhor = max(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None
    pior = min(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None

    linhas = [
        "🐴 📈 RESUMO DONKEY H4",
        data_br,
        "",
        f"Sinais Donkey do dia: {len(entradas)}",
        f"LONG: {len(longs)}",
        f"SHORT: {len(shorts)}",
        f"DONKEY H4: {len(donkeys)}",
        f"EARLY DONKEY H4: {len(early_donkeys)}",
        f"DONKEY CONFIRMADOS: {len(confirmados)}",
        f"POIs DONKEY: {len(pois_donkey)}",
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
        fmt_pct(pnl_total),
        "",
        "MFE médio:",
        fmt_pct(mfe_medio),
        "MFE médio dos wins:",
        fmt_pct(mfe_winners),
        "MFE médio dos losses:",
        fmt_pct(mfe_losers),
        "MFE médio dos BEs:",
        fmt_pct(mfe_breakevens),
        "Devolução média:",
        fmt_pct(devolucao_media),
        "",
        "Melhor trade:",
        f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('pnl', 0))}" if melhor else "N/A",
        "",
        "Pior trade:",
        f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('pnl', 0))}" if pior else "N/A",
    ]

    posicoes = carregar_posicoes()
    ativos = []
    for symbol, p in posicoes.items():
        if p.get("status") == "ENCERRADO":
            continue
        if not is_donkey_signal_type(p.get("signal_type")):
            continue
        try:
            ticker = safe_fetch_ticker(symbol)
            preco = float(ticker["last"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
            ativos.append(f"{p['symbol_clean']} {p['side']} | Origem: {origem_trade_txt(p)} | PnL {fmt_pct(pnl)}")
        except Exception:
            ativos.append(f"{p.get('symbol_clean', symbol)} {p.get('side', '')} | Origem: {origem_trade_txt(p)} | PnL N/A")

    linhas += ["", f"Trades Donkey ainda ativos: {len(ativos)}"]
    if ativos:
        linhas.extend(ativos[:20])

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


def listen_commands():
    last_update_id = 0

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}",
                timeout=30
            ).json()

            for update in resp.get("result", []):
                last_update_id = update.get("update_id", last_update_id)

                msg = update.get("message", {})
                texto = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")

                if not chat_id:
                    continue

                if texto == "/status":
                    enviar_texto(chat_id, montar_status())

                elif texto == "/watchlist":
                    enviar_texto(chat_id, montar_watchlist())

                elif texto == "/resumo":
                    enviar_texto(chat_id, montar_resumo_diario())

                elif texto == "/funil":
                    enviar_texto(chat_id, montar_funil_texto())

                elif texto == "/eventos":
                    enviar_texto(chat_id, montar_eventos_texto())

                elif texto == "/resumo_donkey":
                    safe_send_telegram_donkey(montar_resumo_donkey())

                elif texto == "/be":
                    enviar_texto(chat_id, montar_monitor_be())

                elif texto == "/limparbe":
                    salvar_monitor_be([])
                    enviar_texto(chat_id, "✅ Monitor BE limpo com segurança.")

                elif texto == "/reset":
                    # RESET SEGURO:
                    # Não apaga posições abertas.
                    # Não apaga histórico de trades.
                    # Limpa apenas cooldowns e bloqueios operacionais.
                    salvar_sinais({})
                    salvar_bloqueios_reentrada({})
                    salvar_monitor_be([])
                    salvar_poi_cooldown({})
                    salvar_early_cooldown({})
                    redis_set_json(DAILY_SUMMARY_KEY, {})

                    reset_msg = (
                        "✅ Reset operacional realizado.\n\n"
                        "O que foi limpo:\n"
                        "- Histórico de sinais/cooldowns\n"
                        "- Bloqueios de reentrada\n"
                        "- Monitor BE\n"
                        "- Cooldown POI\n"
                        "- Cooldown EARLY\n"
                        "- Controle de resumo diário\n\n"
                        "O que NÃO foi apagado:\n"
                        "- Posições abertas\n"
                        "- Histórico de trades"
                    )

                    enviar_texto(chat_id, reset_msg)

                elif texto == "/mensal":
                    enviar_texto(chat_id, montar_resumo_mensal())

                elif texto == "/watchlist":
                    wl = carregar_watchlist()
                    wl_validada = validar_watchlist_bingx(wl, avisar_telegram=False)
                    msg = (
                        f"Watchlist configurada: {len(wl)} ativos\n"
                        f"Watchlist válida BingX: {len(wl_validada)} ativos\n\n"
                        + "\n".join([nome_limpo(x) for x in wl_validada])
                    )
                    enviar_texto(chat_id, msg)

                elif texto == "/posicoes":
                    posicoes = carregar_posicoes()
                    abertas = [
                        p for p in posicoes.values()
                        if p.get("status") != "ENCERRADO"
                        and not is_donkey_signal_type(p.get("signal_type"))
                    ]

                    if not abertas:
                        enviar_texto(chat_id, "Nenhuma posição Trend PRO aberta.")
                    else:
                        linhas = []

                        for p in abertas:
                            try:
                                ticker = safe_fetch_ticker(p["symbol"])
                                preco = float(ticker["last"])
                                pnl = pnl_pct(p["side"], float(p["entry"]), preco)
                            except Exception:
                                pnl = 0.0

                            origem = origem_trade_txt(p)
                            entrada_txt = fmt_br(p.get("entry", 0))
                            update_type = p.get("last_update_type")

                            mfe_txt = fmt_pct(p.get("mfe_max_pct", 0))

                            linha = (
                                f"{nome_limpo(p['symbol'])} {p['side']} | "
                                f"Origem: {origem} | "
                                f"Entrada: {entrada_txt} | "
                                f"PnL {fmt_pct(pnl)} | "
                                f"MFE {mfe_txt}"
                            )

                            if update_type:
                                linha += f" | Últ. ajuste: {update_type}"

                            linhas.append(linha)

                        msg = (
                            f"Posições Trend PRO abertas: {len(abertas)}/{MAX_OPEN_POSITIONS}\n\n"
                            + "\n".join(linhas[:50])
                        )

                        enviar_texto(chat_id, msg)


                elif texto == "/top":
                    posicoes = carregar_posicoes()
                    abertas = [
                        p for p in posicoes.values()
                        if p.get("status") != "ENCERRADO"
                    ]

                    ranking = []

                    for p in abertas:
                        try:
                            ticker = safe_fetch_ticker(p["symbol"])
                            preco = float(ticker["last"])
                            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
                            ranking.append((pnl, p))
                        except Exception:
                            pass

                    ranking.sort(key=lambda x: x[0], reverse=True)

                    if not ranking:
                        enviar_texto(chat_id, "Nenhuma posição aberta para ranking.")
                    else:
                        linhas = []

                        for pnl, p in ranking[:10]:
                            linhas.append(
                                f"{nome_limpo(p['symbol'])} {p['side']} | "
                                f"Origem: {origem_trade_txt(p)} | "
                                f"{fmt_pct(pnl)}"
                            )

                        enviar_texto(chat_id, "Top posições abertas:\n\n" + "\n".join(linhas))


                elif texto == "/comandos":
                    comandos_msg = (
                        "📌 Comandos disponíveis:\n\n"
                        "/health - painel técnico do robô\n"
                        "/teste - testa conexão com Telegram\n"
                        "/posicoes - lista posições abertas com origem\n"
                        "/top - mostra melhores posições abertas\n"
                        "/resumo - envia resumo do dia\n"
                        "/mensal - envia resumo do mês anterior\n"
                        "/watchlist - mostra ativos monitorados\n"
                        "/reset - limpa cooldowns/bloqueios sem apagar posições\n"
                        "/limparbe - limpa monitor BE caso fique inconsistente\n"
                        "/comandos - mostra esta lista"
                    )
                    enviar_texto(chat_id, comandos_msg)


                elif texto == "/status":
                    enviar_texto(chat_id, "O /status foi substituído pelo /health. Use /health para o painel técnico.")

                elif texto == "/health":
                    enviar_texto(chat_id, montar_health_tecnico())

                elif texto == "/reset_donkey_positions":
                    salvar_posicoes({})
                    salvar_monitor_be([])

                    enviar_texto(
                        chat_id,
                        "✅ Posições Donkey zeradas."
                    )

                elif texto == "/teste":
                    enviar_texto(chat_id, "✅ Robô operacional e conectado.")

        except Exception as e:
            print("ERRO COMANDOS:", e)

        time.sleep(2)



def enviar_texto_donkey(chat_id, msg):
    try:
        msg = normalizar_texto(msg)
        if not DONKEY_TOKEN:
            print("DONKEY_TOKEN não configurado.")
            return
        payload = {"chat_id": chat_id, "text": msg}
        requests.post(
            f"https://api.telegram.org/bot{DONKEY_TOKEN}/sendMessage",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=20
        )
    except Exception as e:
        print("Erro ao responder Telegram Donkey:", e)


def montar_posicoes_donkey():
    posicoes = carregar_posicoes()
    linhas = []
    for symbol, p in posicoes.items():
        if p.get("status") == "ENCERRADO":
            continue
        if not is_donkey_signal_type(p.get("signal_type")):
            continue
        try:
            ticker = safe_fetch_ticker(symbol)
            preco_atual = float(ticker["last"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco_atual)
            linhas.append(
                f"{p['symbol_clean']} {p['side']} | Origem: {origem_trade_txt(p)} | "
                f"Entrada: {fmt_br(p['entry'])} | PnL {fmt_pct(pnl)} | "
                f"MFE {fmt_pct(p.get('mfe_max_pct', 0))}"
            )
        except Exception:
            linhas.append(
                f"{p.get('symbol_clean', symbol)} {p.get('side', '')} | "
                f"Origem: {origem_trade_txt(p)} | Entrada: {fmt_br(p.get('entry', 0))} | PnL N/A"
            )
    if not linhas:
        return "🐴 Nenhuma posição Donkey aberta."
    return "🐴 Posições Donkey abertas: " + str(len(linhas)) + "\n\n" + "\n".join(linhas)


def listen_donkey_commands():
    if not DONKEY_TOKEN:
        print("DONKEY_TOKEN não configurado. Listener Donkey não iniciado.")
        return

    last_update_id = 0
    try:
        requests.get(f"https://api.telegram.org/bot{DONKEY_TOKEN}/deleteWebhook", timeout=10)
    except Exception as e:
        print("AVISO deleteWebhook Donkey:", e)

    while True:
        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{DONKEY_TOKEN}/getUpdates?offset={last_update_id + 1}",
                timeout=30
            ).json()

            if not resp.get("ok", True):
                print("ERRO TELEGRAM DONKEY getUpdates:", resp)
                time.sleep(5)
                continue

            for update in resp.get("result", []):
                last_update_id = update.get("update_id", last_update_id)
                msg = update.get("message", {})
                texto = msg.get("text", "")
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id:
                    continue
                comando = texto.strip().split()[0].lower() if texto else ""
                if "@" in comando:
                    comando = comando.split("@")[0]

                if comando == "/resumo":
                    enviar_texto_donkey(chat_id, montar_resumo_donkey())
                elif comando == "/posicoes":
                    enviar_texto_donkey(chat_id, montar_posicoes_donkey())
                elif comando == "/health":
                    enviar_texto_donkey(chat_id, montar_health_tecnico())
                elif comando == "/comandos":
                    enviar_texto_donkey(
                        chat_id,
                        "🐴 Comandos Donkey H4:\n"
                        "/resumo - resumo Donkey\n"
                        "/posicoes - posições Donkey\n"
                        "/health - status técnico"
                    )
        except Exception as e:
            print("ERRO COMANDOS DONKEY:", e)
            time.sleep(10)



# ====================================================
# SCANNER
# ====================================================

def scanner():
    global ultimo_relatorio_hora

    print("SCANNER INICIADO")
    HEALTH["started_at"] = data_hora_sp_str()
    safe_send_telegram(
        f"🤖 Robô {BOT_NAME} iniciado\n\n"
        f"Filtros ativos:\n"
        f"Score mínimo: {ELITE_THRESHOLD}/100\n"
        f"ADX H4 mínimo: {ELITE_MIN_ADX_H4}\n"
        f"Volume H1 obrigatório: {check_bool(REQUIRE_HIGH_VOLUME)}\n"
        f"Recuperado ativo: {check_bool(ENABLE_RECOVERED_SIGNAL)}\n"
        f"Relatório automático: {check_bool(ENABLE_AUTO_POSITION_REPORT)}\n"
        f"Modo: {'ATIVO ✅' if TREND_PRO_ENABLED else 'STAND-BY ⚪'}\n"
        f"Auto trade: {'SIM' if TREND_PRO_AUTO_TRADE else 'NÃO'}\n"
        f"Watchdog: ✅ {WATCHDOG_THRESHOLD_MINUTES} min"
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
            registrar_funil("scanner_runs")
            registrar_funil("ativos_analisados", len(watchlist))
            sinais = []
            sinais_enviados = 0

            if not TREND_PRO_ENABLED:
                HEALTH["last_warning"] = "Trend PRO Elite em stand-by; scanner não envia sinais."
                HEALTH["last_positions_count"] = contar_posicoes_ativas()
                HEALTH["last_signals_sent"] = 0
                HEALTH["last_success"] = data_hora_sp_str()
                HEALTH["last_error"] = None
                time.sleep(60)
                continue

            for symbol in watchlist:
                try:
                    registrar_funil("ativos_analisados")
                    if startup_signal_guard_active():
                        registrar_funil("startup_guard_ignorados")
                        print(f"STARTUP GUARD TRENDPRO: ignorando novos sinais temporariamente em {nome_limpo(symbol)}")
                        continue

                    # POI primeiro para posições ativas.
                    posicoes = carregar_posicoes()
                    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
                        registrar_funil("posicao_ativa_ignorados")
                        # Trend PRO Only:
                        # Não gerencia, não confirma e não envia POI Donkey.
                        # Posições Donkey ficam exclusivamente no serviço Donkey.
                        if posicoes[symbol].get("signal_type") in ["DONKEY", "EARLY_DONKEY", "POI_DONKEY", "DONKEY_CONFIRMADO"]:
                            continue

                        poi = detectar_poi(symbol, posicoes[symbol])
                        if poi:
                            registrar_funil("poi_detectados")
                            registrar_score_funil(poi)
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
                                registrar_reprovacao_funil(motivo)
                                print(f"POI BLOQUEADO PELO TREND PRO ELITE: {nome_limpo(symbol)} | {motivo}")
                        continue

                    # REENTRY para posições encerradas que já atingiram TP50.
                    if symbol in posicoes and posicoes[symbol].get("status") == "ENCERRADO":
                        reentry = detectar_reentry(symbol, posicoes[symbol])
                        if reentry:
                            registrar_funil("reentry_detectados")
                            registrar_score_funil(reentry)
                            aprovado, motivo = passa_filtro_trendpro_elite(
                                reentry,
                                threshold=ELITE_THRESHOLD,
                                min_adx_h4=ELITE_MIN_ADX_H4,
                                require_high_volume=REQUIRE_HIGH_VOLUME,
                                require_bb_expanding=REQUIRE_BB_EXPANDING,
                                label="REENTRY"
                            )

                            if not aprovado:
                                registrar_reprovacao_funil(motivo)
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
                                    registrar_funil("sinais_enviados")
                            continue

                    early = detectar_early_a(symbol)

                    if early:
                        registrar_funil("early_detectados")
                        registrar_score_funil(early)
                        aprovado, motivo = passa_filtro_trendpro_elite(
                            early,
                            threshold=EARLY_THRESHOLD,
                            min_adx_h4=EARLY_MIN_ADX_H4,
                            require_high_volume=EARLY_REQUIRE_VOLUME,
                            require_bb_expanding=False,
                            label="EARLY"
                        )

                        if not aprovado:
                            registrar_reprovacao_funil(motivo)
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
                                registrar_funil("sinais_enviados")
                        continue

                    resultado, df_h1, df_h4 = analisar_sinal_h1(symbol)

                    if not resultado:
                        continue

                    if resultado.get("signal_type") == "RECUPERADO":
                        registrar_funil("recuperados_detectados")
                    else:
                        registrar_funil("normal_detectados")
                    registrar_score_funil(resultado)

                    aprovado, motivo = passa_filtro_trendpro_elite(
                        resultado,
                        threshold=ELITE_THRESHOLD,
                        min_adx_h4=ELITE_MIN_ADX_H4,
                        require_high_volume=REQUIRE_HIGH_VOLUME,
                        require_bb_expanding=REQUIRE_BB_EXPANDING,
                        label="SINAL"
                    )

                    if not aprovado:
                        registrar_reprovacao_funil(motivo)
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
                    registrar_funil("reprovados_posicao_ativa")
                    continue

                chave = f"{s['symbol']}_{s['timestamp']}_{s['signal']}"

                if chave in historico:
                    continue

                if registrar_posicao(s):
                    historico[chave] = True
                    enviar_sinal_h1(s)
                    sinais_enviados += 1
                    registrar_funil("sinais_enviados")
                    registrar_funil("sinais_enviados")

            salvar_sinais(historico)

            HEALTH["last_signals_sent"] = sinais_enviados
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            print(f"Sinais enviados: {len(sinais)}")

        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO SCANNER:", e)

        time.sleep(60)



@app.route("/funil")
def funil_route():
    return funil_hoje()



@app.route("/eventos")
def eventos_route():
    return montar_eventos_texto(), 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/health")
def health():
    watchdog = montar_watchdog_status()
    try:
        posicoes = carregar_posicoes()
        abertas = [
            p for p in posicoes.values()
            if p.get("status") != "ENCERRADO"
        ]
        HEALTH["last_positions_count"] = len(abertas)
    except Exception:
        pass

    return {
        "ok": watchdog.get("ok", True),
        "bot": BOT_NAME,
        "version": "2026-06-23-TREND-PRO-ELITE-CENTRAL-QUANT-PADRONIZADO",
        "service_mode": "TREND_PRO_ELITE",
        "standby": not TREND_PRO_ENABLED,
        "trend_pro_enabled": TREND_PRO_ENABLED,
        "trend_pro_auto_trade": TREND_PRO_AUTO_TRADE,
        "started_at": HEALTH.get("started_at"),
        "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"),
        "last_success": HEALTH.get("last_success"),
        "last_error": HEALTH.get("last_error"),
        "minutes_since_scanner": watchdog.get("minutes_since_scanner"),
        "minutes_since_management": watchdog.get("minutes_since_management"),
        "watchdog_status": watchdog.get("status"),
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_watchdog_alert": HEALTH.get("last_watchdog_alert"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "last_watchlist_count": HEALTH.get("last_watchlist_count"),
        "last_signals_sent": HEALTH.get("last_signals_sent"),
        "last_positions_count": HEALTH.get("last_positions_count"),
        "config": {
            "timeframe_h4": TIMEFRAME_H4,
            "timeframe_h1": TIMEFRAME_H1,
            "supertrend_factor": SUPERTREND_FACTOR,
            "early_adx_h4_min": EARLYDX_H4_MIN,
            "spike_filter": ENABLE_SPIKE_FILTER,
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
        "be_trigger_r": BE_TRIGGER_R,
            "poi_cooldown_seconds": POI_COOLDOWN_SECONDS,
            "tp50_r": TP50_R,
            "tp50_min_atr": TP50_MIN_ATR,
            "be_trigger_r": BE_TRIGGER_R,
            "enable_reentry": ENABLE_REENTRY_AFTER_TP50,
            "reentry_after_close_seconds": REENTRY_AFTER_CLOSE_SECONDS,
                    "resumos_separados": True
        }
    }



@app.route("/watchdog")
def watchdog():
    return montar_watchdog_status()

@app.route("/")
def home():
    return f"{BOT_NAME} Online"


def run_thread_guarded(nome, target):
    while True:
        try:
            target()
        except Exception as e:
            try:
                HEALTH["last_error"] = f"Thread {nome} travou: {e}"
            except Exception:
                pass

            print(f"ERRO FATAL THREAD TRENDPRO {nome}:", e)

            try:
                safe_send_telegram(
                    f"🚨 TRENDPRO THREAD TRAVOU: {nome}\n\n"
                    f"Erro:\n{str(e)}\n\n"
                    "A thread será reiniciada automaticamente."
                )
            except Exception:
                pass

            time.sleep(10)


threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog_loop), daemon=True).start()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
