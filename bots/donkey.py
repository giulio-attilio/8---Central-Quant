# Ajuste Central Quant: startup guard padronizado em 0 por padrão; arquitetura alinhada em DONKEY.
# TREND PRO MTF H4/H1 + POI
# Versão: 2026-06-25-DONKEY-H4-V2-BOOTSTRAP-WATCHDOG
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

BOT_NAME = os.environ.get("BOT_NAME", "Donkey H4")
WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DONKEY_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DONKEY_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = os.environ.get("DONKEY_WATCHLIST_FILE", "watchlists/donkey.json")

POSITIONS_KEY = "donkey:positions"
SIGNALS_KEY = "donkey:signals"
TRADES_KEY = "donkey:trades"
DAILY_SUMMARY_KEY = "donkey:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "donkey:monthly_summary_sent"
REENTRY_BLOCK_KEY = "donkey:reentry_block"
BE_MONITOR_KEY = "donkey:be_monitor"
POI_COOLDOWN_KEY = "donkey:poi_cooldown"
EARLY_COOLDOWN_KEY = "donkey:early_cooldown"
DONKEY_COOLDOWN_KEY = "donkey:donkey_cooldown"
DONKEY_CONFIRM_KEY = "donkey:donkey_confirmed"
DONKEY_POI_COOLDOWN_KEY = "donkey:donkey_poi_cooldown"

# ====================================================
# CONFIGURAÇÕES PRINCIPAIS
# ====================================================

TIMEFRAME_H4 = "4h"
TIMEFRAME_H1 = "1h"

EMA_FAST = 9
EMA_MID = 21
EMA50 = 50
EMA200 = 200

EMA20 = 20

# ====================================================
# DONKEY H4 - SETUP INDEPENDENTE
# ====================================================
ENABLE_DONKEY_H4 = True
ENABLE_EARLY_DONKEY_H4 = False
DONKEY_TIMEFRAME = "4h"
DONKEY_EMA_FAST = 20
DONKEY_EMA_SLOW = 50
DONKEY_MACD_FAST = 12
DONKEY_MACD_SLOW = 26
DONKEY_MACD_SIGNAL = 9
DONKEY_BUFFER_PCT = 0.5  # 0,5% de margem no stop/trailing
DONKEY_SWING_LEN = 5
DONKEY_POI_COOLDOWN_SECONDS = 8 * 60 * 60  # 2 candles H4
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
MAX_RISK_H1 = 2.0

# Donkey: bloqueia qualquer entrada/POI com risco acima do limite operacional.
# Objetivo: evitar sinais com risco 3% a 6% que distorcem o resultado.
DONKEY_MAX_RISK_PCT = MAX_RISK_H1

# Donkey: ao bater TP50, stop sobe imediatamente para breakeven com pequeno lucro.
# Isso evita TP50 virar loss depois.
DONKEY_MOVE_SL_TO_BE_ON_TP50 = True
DONKEY_BE_OFFSET_PCT = 0.10

# Gestão Donkey pós-TP50:
# NOVO MODELO:
# - Ao atingir TP50, considera 50% realizado imediatamente.
# - O stop do restante sobe para BE + offset.
# - Os 50% restantes seguem pela EMA20 H4 até fechamento contra a tendência.
# - O antigo Trailing50/Chandelier fica desligado para o Donkey.
DONKEY_USE_TRAILING50_EMA20_100 = False
DONKEY_PARTIAL_TP50_ENABLED = True
DONKEY_PARTIAL_TP50_PCT = 50.0
DONKEY_REMAINING_AFTER_TP50_PCT = 50.0
DONKEY_EXIT_REMAINDER_ON_H4_EMA20 = True

# Cooldown pós-saída Donkey.
# Evita fechar e reabrir o mesmo ativo no mesmo ciclo.
# Após STOP/SL100/fechamento completo, novas entradas ficam bloqueadas por 1 candle H4.
DONKEY_POST_EXIT_COOLDOWN_SECONDS = int(os.environ.get("DONKEY_POST_EXIT_COOLDOWN_SECONDS", str(4 * 60 * 60)))
DONKEY_POST_EXIT_COOLDOWN_KEY = "donkey:post_exit_cooldown"

# Estado persistente de boot/deploy para auditoria e proteção pós-deploy.
BOOT_STATE_KEY = "donkey:boot_state"
BOOT_HISTORY_KEY = "donkey:boot_history"
THREAD_HEARTBEAT_KEY = "donkey:thread_heartbeat"

# Limite de exposição operacional.
MAX_OPEN_POSITIONS = 25

# ====================================================
# TREND PRO ELITE - FILTROS OBRIGATÓRIOS
# ====================================================
# O Trend PRO agora vira Trend PRO Elite: menos sinais, maior qualidade.
ENABLE_TRENDPRO_ELITE_FILTER = False

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
ENABLE_EARLY = False
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
ENABLE_REENTRY_AFTER_TP50 = False
REENTRY_AFTER_CLOSE_SECONDS = 2 * 60 * 60  # 2 candles H1
REENTRY_COOLDOWN_SECONDS = 60 * 60

# Proteção para não checar stop logo após BE/Trailing.
PROTECTION_SECONDS = 300


# Relatório mensal automático: dia 01, consolidando mês anterior.
MONTHLY_SUMMARY_DAY = 1
MONTHLY_SUMMARY_HOUR = 8
MONTHLY_SUMMARY_MINUTE = 5

# Resumo diário automático do Donkey.
# Envia 1 vez por dia a partir de 23:55 no horário de São Paulo.
DAILY_SUMMARY_HOUR = int(os.environ.get("DAILY_SUMMARY_HOUR", "23"))
DAILY_SUMMARY_MINUTE = int(os.environ.get("DAILY_SUMMARY_MINUTE", "55"))

# Proteção anti-lote após restart/sleep do Render.
# Durante os primeiros minutos após o processo subir, o robô gerencia posições abertas,
# mas NÃO envia novos sinais/POIs/confirmações acumulados.
# Novos sinais detectados nesse período são marcados no histórico para não serem enviados atrasados depois.
STARTUP_SIGNAL_GRACE_SECONDS = int(
    os.environ.get(
        "DONKEY_STARTUP_SIGNAL_GRACE_SECONDS",
        os.environ.get("STARTUP_SIGNAL_GRACE_SECONDS", "600")
    )
)
SERVICE_STARTED_TS = time.time()

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

redis = Redis(
    url=UPSTASH_REDIS_REST_URL,
    token=UPSTASH_REDIS_REST_TOKEN
)


# ====================================================
# CAMADA DE RESILIÊNCIA API (CCXT SAFE FETCH)
# ====================================================

def safe_fetch_ohlcv(symbol, timeframe, limit, max_retries=3):
    """
    Busca OHLCV com retry/backoff.

    Importante:
    - Falha em UM ativo/timeframe é tratada como WARNING, não como erro crítico.
    - O scanner deve pular esse ativo e seguir para o próximo.
    - HEALTH["last_error"] fica reservado para falha estrutural do robô/scanner.
    """
    ultimo_erro = None

    for attempt in range(max_retries):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            ultimo_erro = e
            print(f"AVISO API OHLCV ({attempt + 1}/{max_retries}) {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            ultimo_erro = e
            print(f"ERRO API OHLCV {symbol} {timeframe}: {e}")
            time.sleep(2 ** attempt)

    aviso = f"Falha OHLCV {symbol} {timeframe} após {max_retries} tentativas"
    if ultimo_erro:
        aviso += f": {ultimo_erro}"

    HEALTH["last_warning"] = aviso
    print("WARNING:", aviso)
    return []


def safe_fetch_ticker(symbol, max_retries=3):
    """
    Busca ticker com retry/backoff.

    Falha pontual vira WARNING e não derruba o health geral da Central.
    """
    ultimo_erro = None

    for attempt in range(max_retries):
        try:
            return exchange.fetch_ticker(symbol)
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            ultimo_erro = e
            print(f"AVISO API TICKER ({attempt + 1}/{max_retries}) {symbol}: {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            ultimo_erro = e
            print(f"ERRO API TICKER {symbol}: {e}")
            time.sleep(2 ** attempt)

    aviso = f"Falha ticker {symbol} após {max_retries} tentativas"
    if ultimo_erro:
        aviso += f": {ultimo_erro}"

    HEALTH["last_warning"] = aviso
    print("WARNING:", aviso)
    return None


def safe_load_markets(max_retries=3):
    for attempt in range(max_retries):
        try:
            return exchange.load_markets()
        except (RateLimitExceeded, NetworkError, ExchangeError) as e:
            print(f"AVISO API LOAD_MARKETS ({attempt + 1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
        except Exception as e:
            print(f"ERRO API LOAD_MARKETS: {e}")
            time.sleep(2 ** attempt)

    HEALTH["last_error"] = "Falha crítica ao carregar markets da BingX"
    return None

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


def carregar_watchlist():
    candidatos = []

    if WATCHLIST_FILE:
        candidatos.append(WATCHLIST_FILE)

    # Fallback para compatibilidade com a primeira versão da Central.
    if "watchlist.json" not in candidatos:
        candidatos.append("watchlist.json")

    for arquivo in candidatos:
        try:
            with open(arquivo, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
                print(f"WATCHLIST INVÁLIDA {arquivo}: esperado lista JSON")
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"ERRO WATCHLIST {arquivo}:", e)

    print(f"NENHUMA WATCHLIST ENCONTRADA. Tentadas: {candidatos}")
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
        HEALTH["watchlist_valid"] = 0
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


def carregar_boot_state():
    return redis_get_json(BOOT_STATE_KEY, {})


def salvar_boot_state(dados):
    redis_set_json(BOOT_STATE_KEY, dados)


def registrar_boot():
    """Registra cada inicialização/deploy do serviço."""
    try:
        anterior = carregar_boot_state()
        historico = redis_get_json(BOOT_HISTORY_KEY, [])
        agora_txt = data_hora_sp_str()
        agora_ts = time.time()

        estado = {
            "last_boot": agora_txt,
            "last_boot_ts": agora_ts,
            "previous_boot": anterior.get("last_boot"),
            "previous_boot_ts": anterior.get("last_boot_ts"),
            "deploy_counter": int(anterior.get("deploy_counter", 0) or 0) + 1,
            "boot_completed": False,
            "boot_completed_at": None,
            "startup_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
            "bot": BOT_NAME
        }

        historico.append({
            "boot": agora_txt,
            "boot_ts": agora_ts,
            "previous_boot": anterior.get("last_boot"),
            "deploy_counter": estado["deploy_counter"]
        })
        historico = historico[-50:]

        salvar_boot_state(estado)
        redis_set_json(BOOT_HISTORY_KEY, historico)
        print(f"BOOT REGISTRADO - {BOT_NAME} | deploy_counter={estado['deploy_counter']} | startup_guard={STARTUP_SIGNAL_GRACE_SECONDS}s")
        return estado
    except Exception as e:
        print("ERRO REGISTRAR BOOT:", e)
        return {}


def marcar_boot_completo():
    try:
        estado = carregar_boot_state()
        if estado.get("boot_completed") is True:
            return
        estado["boot_completed"] = True
        estado["boot_completed_at"] = data_hora_sp_str()
        estado["boot_completed_ts"] = time.time()
        salvar_boot_state(estado)
        print("BOOTSTRAP FINALIZADO - OPERAÇÃO NORMAL INICIADA")
    except Exception as e:
        print("ERRO MARCAR BOOT COMPLETO:", e)


def segundos_restantes_startup_guard():
    try:
        restante = STARTUP_SIGNAL_GRACE_SECONDS - (time.time() - SERVICE_STARTED_TS)
        return max(0, int(restante))
    except Exception:
        return 0


def atualizar_thread_heartbeat(nome):
    try:
        dados = redis_get_json(THREAD_HEARTBEAT_KEY, {})
        dados[nome] = {
            "datetime": data_hora_sp_str(),
            "ts": time.time()
        }
        redis_set_json(THREAD_HEARTBEAT_KEY, dados)
    except Exception:
        pass


def carregar_thread_heartbeat():
    return redis_get_json(THREAD_HEARTBEAT_KEY, {})


def calcular_estado_operacional_donkey():
    """Métricas operacionais atuais para /health e auditoria diária."""
    posicoes = carregar_posicoes()
    abertas = [
        p for p in posicoes.values()
        if p.get("status") != "ENCERRADO" and is_donkey_signal_type(p.get("signal_type"))
    ]

    em_tp50 = [p for p in abertas if bool(p.get("tp50_hit") or p.get("partial_tp50_done"))]
    aguardando_ema20 = [p for p in abertas if bool(p.get("partial_tp50_done")) and DONKEY_EXIT_REMAINDER_ON_H4_EMA20]
    protegidas_be = [p for p in abertas if bool(p.get("breakeven")) or bool(p.get("partial_tp50_done"))]
    runners = [p for p in abertas if bool(p.get("partial_tp50_done")) and float(p.get("remaining_position_pct", 0) or 0) > 0]

    return {
        "donkey_positions_open": len(abertas),
        "donkey_positions_tp50": len(em_tp50),
        "donkey_positions_waiting_ema20": len(aguardando_ema20),
        "donkey_positions_protected_be": len(protegidas_be),
        "donkey_runners_active": len(runners)
    }


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


def carregar_donkey_post_exit_cooldown():
    return redis_get_json(DONKEY_POST_EXIT_COOLDOWN_KEY, {})


def salvar_donkey_post_exit_cooldown(dados):
    redis_set_json(DONKEY_POST_EXIT_COOLDOWN_KEY, dados)


def donkey_em_cooldown_pos_saida(symbol):
    """
    Bloqueia nova entrada no mesmo ativo após STOP/SL100/fechamento completo.
    Objetivo: impedir STOP e novo BUY/SELL no mesmo ciclo e aguardar 1 candle H4.
    """
    dados = carregar_donkey_post_exit_cooldown()
    ultimo = float(dados.get(symbol, 0) or 0)
    return time.time() - ultimo < DONKEY_POST_EXIT_COOLDOWN_SECONDS


def tempo_restante_cooldown_pos_saida(symbol):
    dados = carregar_donkey_post_exit_cooldown()
    ultimo = float(dados.get(symbol, 0) or 0)
    restante = DONKEY_POST_EXIT_COOLDOWN_SECONDS - (time.time() - ultimo)
    return max(0, int(restante))


def marcar_donkey_post_exit_cooldown(symbol):
    dados = carregar_donkey_post_exit_cooldown()
    dados[symbol] = time.time()

    if len(dados) > 500:
        itens = sorted(dados.items(), key=lambda x: x[1])
        dados = dict(itens[-500:])

    salvar_donkey_post_exit_cooldown(dados)


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


# ====================================================
# WATCHDOG
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

def montar_watchdog_status():
    minutes_since_scanner = minutos_desde_health("last_scanner_run")
    minutes_since_management = minutos_desde_health("last_management_run")

    scanner_stalled = minutes_since_scanner is not None and minutes_since_scanner > WATCHDOG_THRESHOLD_MINUTES
    management_stalled = minutes_since_management is not None and minutes_since_management > WATCHDOG_THRESHOLD_MINUTES

    boot_state = carregar_boot_state()
    heartbeats = carregar_thread_heartbeat()
    startup_stalled = False
    try:
        # Se o processo ficou tempo demais no bootstrap, é alerta.
        startup_stalled = startup_signal_guard_active() and (time.time() - SERVICE_STARTED_TS) > (STARTUP_SIGNAL_GRACE_SECONDS + 120)
    except Exception:
        startup_stalled = False

    ok = HEALTH.get("last_error") is None and not scanner_stalled and not management_stalled and not startup_stalled

    reasons = []
    if HEALTH.get("last_error") is not None:
        reasons.append(f"last_error: {HEALTH.get('last_error')}")
    if scanner_stalled:
        reasons.append(f"scanner parado há {minutes_since_scanner} min")
    if management_stalled:
        reasons.append(f"gestão parada há {minutes_since_management} min")
    if startup_stalled:
        reasons.append("bootstrap excedeu o tempo esperado")

    return {
        "ok": ok,
        "bot": BOT_NAME,
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
        "startup_mode": startup_signal_guard_active(),
        "startup_remaining_seconds": segundos_restantes_startup_guard(),
        "boot_completed": boot_state.get("boot_completed"),
        "last_boot": boot_state.get("last_boot"),
        "previous_boot": boot_state.get("previous_boot"),
        "deploy_counter": boot_state.get("deploy_counter"),
        "thread_heartbeats": heartbeats,
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
    safe_send_telegram_donkey(msg)
    HEALTH["last_watchdog_alert"] = data_hora_sp_str()
    HEALTH["last_watchdog_alert_ts"] = time.time()

def watchdog_loop():
    print(f"WATCHDOG INICIADO - {BOT_NAME}")
    while True:
        try:
            HEALTH["watchdog_last_check"] = data_hora_sp_str()
            atualizar_thread_heartbeat("watchdog")
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
    boot_state = carregar_boot_state()
    operacional = calcular_estado_operacional_donkey()

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
        "donkey_max_risk_pct": DONKEY_MAX_RISK_PCT,
        "donkey_move_sl_to_be_on_tp50": DONKEY_MOVE_SL_TO_BE_ON_TP50,
        "donkey_be_offset_pct": DONKEY_BE_OFFSET_PCT,
        "donkey_use_trailing50_ema20_100": DONKEY_USE_TRAILING50_EMA20_100,
        "donkey_partial_tp50_enabled": DONKEY_PARTIAL_TP50_ENABLED,
        "donkey_partial_tp50_pct": DONKEY_PARTIAL_TP50_PCT,
        "donkey_remaining_after_tp50_pct": DONKEY_REMAINING_AFTER_TP50_PCT,
        "donkey_exit_remainder_on_h4_ema20": DONKEY_EXIT_REMAINDER_ON_H4_EMA20,
        "donkey_post_exit_cooldown_seconds": DONKEY_POST_EXIT_COOLDOWN_SECONDS,
        "donkey_poi_cooldown_seconds": DONKEY_POI_COOLDOWN_SECONDS,
        "donkey_selective_mode": True,
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
        "donkey_h4_enabled": ENABLE_DONKEY_H4,
        "early_donkey_h4_enabled": ENABLE_EARLY_DONKEY_H4,
        "donkey_confirm_key": DONKEY_CONFIRM_KEY,
        "donkey_buffer_pct": DONKEY_BUFFER_PCT,
        "donkey_risk_usdt": DONKEY_RISK_USDT,
        "donkey_telegram_configured": bool(DONKEY_TOKEN and DONKEY_CHAT_ID),
        "resumos_separados": True,
        "mfe_enabled": True,
        "service_mode": "DONKEY_ONLY",
        "bot": BOT_NAME,
        "watchdog_status": watchdog.get("status"),
        "minutes_since_scanner": watchdog.get("minutes_since_scanner"),
        "minutes_since_management": watchdog.get("minutes_since_management"),
        "watchdog_check_seconds": WATCHDOG_CHECK_SECONDS,
        "watchdog_threshold_minutes": WATCHDOG_THRESHOLD_MINUTES,
        "watchdog_alert_cooldown_seconds": WATCHDOG_ALERT_COOLDOWN_SECONDS,
        "last_watchdog_alert": HEALTH.get("last_watchdog_alert"),
        "watchdog_last_check": HEALTH.get("watchdog_last_check"),
        "daily_summary_time": f"{DAILY_SUMMARY_HOUR:02d}:{DAILY_SUMMARY_MINUTE:02d}",
        "daily_summary_sent_today": resumo_diario_ja_enviado(),
        "startup_signal_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
        "startup_signal_guard_active": startup_signal_guard_active(),
        "startup_mode": startup_signal_guard_active(),
        "startup_mode_txt": startup_mode_txt(),
        "startup_remaining_seconds": segundos_restantes_startup_guard(),
        "boot_completed": boot_state.get("boot_completed"),
        "last_boot": boot_state.get("last_boot"),
        "previous_boot": boot_state.get("previous_boot"),
        "deploy_counter": boot_state.get("deploy_counter"),
        "boot_completed_at": boot_state.get("boot_completed_at"),
        **operacional
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

    if donkey_em_cooldown_pos_saida(symbol):
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

    if donkey_em_cooldown_pos_saida(symbol):
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
    - Quando EARLY_DONKEY vira DONKEY completo.
    - Recalcula entrada, risco e TP50 pelo preço atual da confirmação.
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

    if side == "LONG":
        confirmado = close > ema20 and ema20 > ema50 and macd > 0
    else:
        confirmado = close < ema20 and ema20 < ema50 and macd < 0

    if not confirmado:
        return None

    early_entry = float(posicao.get("entry", close))
    sl_atual = float(posicao.get("sl", 0))

    if sl_atual <= 0:
        return None

    entry_confirmada = close
    risk_abs = abs(entry_confirmada - sl_atual)

    if risk_abs <= 0:
        return None

    if side == "LONG":
        tp50 = entry_confirmada + risk_abs * TP50_R
    else:
        tp50 = entry_confirmada - risk_abs * TP50_R

    risk_pct = risk_abs / entry_confirmada * 100

    if USE_MAX_RISK_FILTER and risk_pct > DONKEY_MAX_RISK_PCT:
        print(
            f"CONFIRMAÇÃO DONKEY IGNORADA POR RISCO ALTO: "
            f"{nome_limpo(symbol)} | {risk_pct:.2f}% > {DONKEY_MAX_RISK_PCT:.2f}%"
        )
        return None

    posicoes = carregar_posicoes()
    p = posicoes.get(symbol, posicao)
    p["entry"] = entry_confirmada
    p["entry_confirmed"] = entry_confirmada
    p["early_entry"] = early_entry
    p["sl"] = sl_atual
    p["tp50"] = tp50
    p["risk_abs"] = risk_abs
    p["risk_pct"] = risk_pct
    p["signal_type"] = "DONKEY"
    p["origin"] = "DONKEY"
    p["confirmed_at"] = time.time()
    p["tp50_hit"] = False
    posicoes[symbol] = p
    salvar_posicoes(posicoes)

    marcar_donkey_confirmado(symbol, side, timestamp)

    return {
        "type": "DONKEY_CONFIRMADO",
        "signal_type": "DONKEY_CONFIRMADO",
        "symbol": symbol,
        "symbol_clean": nome_limpo(symbol),
        "signal": side,
        "side": side,
        "timestamp": timestamp,
        "entry": entry_confirmada,
        "current_price": entry_confirmada,
        "sl": sl_atual,
        "tp50": tp50,
        "risk_abs": risk_abs,
        "risk_pct": risk_pct,
        "ema20": ema20,
        "ema50": ema50,
        "macd": macd,
        "early_entry": early_entry
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

    if USE_MAX_RISK_FILTER and risk_pct > DONKEY_MAX_RISK_PCT:
        print(
            f"POI DONKEY IGNORADO POR RISCO ALTO: "
            f"{nome_limpo(symbol)} | {risk_pct:.2f}% > {DONKEY_MAX_RISK_PCT:.2f}%"
        )
        return None

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


def registrar_fechamento_donkey(symbol, p, exit_price, resultado_total, closed_by, result_type=None, extra=None):
    """
    Registra fechamento do Donkey.

    resultado_total pode ser:
    - 100% da posição antes do TP50;
    - resultado ponderado quando houve SL50 + SL100.
    """
    if extra is None:
        extra = {}

    registrar_evento_trade({
        "event": "CLOSE",
        "date": data_hoje_sp_str(),
        "datetime": data_hora_sp_str(),
        "symbol": symbol,
        "symbol_clean": p["symbol_clean"],
        "side": p["side"],
        "entry": float(p["entry"]),
        "exit": float(exit_price),
        "pnl": float(resultado_total),
        "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
        "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - float(resultado_total),
        "result_type": result_type or ("WIN" if resultado_total > 0 else "LOSS"),
        "signal_type": "DONKEY",
        "closed_by": closed_by,
        **extra
    })

    # Cooldown pós-saída completa: impede reabrir o mesmo ativo imediatamente
    # no mesmo ciclo de scanner. Mantém o Donkey alinhado ao H4.
    marcar_donkey_post_exit_cooldown(symbol)

    p["closed_at"] = time.time()
    p["closed_datetime"] = data_hora_sp_str()
    p["closed_reason"] = closed_by
    p["status"] = "ENCERRADO"


def buscar_candle_h4_fechado(symbol):
    ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=120)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    return df_h4.iloc[-2]


def ema20_h4_invalidou(symbol, side):
    """
    Trailing100 / SL100:
    usa fechamento do candle H4 contra a EMA20.
    LONG: fecha abaixo da EMA20.
    SHORT: fecha acima da EMA20.
    """
    candle_h4 = buscar_candle_h4_fechado(symbol)
    close_h4 = float(candle_h4["close"])
    ema20_h4 = float(candle_h4["ema20"])
    timestamp_h4 = int(candle_h4["time"])

    invalidou = (
        (side == "LONG" and close_h4 < ema20_h4) or
        (side == "SHORT" and close_h4 > ema20_h4)
    )

    return invalidou, close_h4, ema20_h4, timestamp_h4



def calcular_pnl_total_com_parcial_donkey(p, exit_price):
    """
    Calcula PnL total ponderado quando houve realização parcial no TP50.
    Exemplo:
    - 50% saiu no TP50 com +2%
    - 50% saiu no preço final com +8%
    - resultado total = +5%
    """
    side = p.get("side")
    entry = float(p.get("entry"))
    parcial_pct = float(p.get("partial_realized_position_pct", 0) or 0)
    restante_pct = float(p.get("remaining_position_pct", 100) or 100)

    parcial_result = float(p.get("partial_realized_result_pct", 0) or 0)
    final_result = pnl_pct(side, entry, float(exit_price))

    total = (parcial_result * (parcial_pct / 100.0)) + (final_result * (restante_pct / 100.0))
    return total


def enviar_tp50_parcial_donkey(p, tp50, resultado):
    msg = (
        f"🎯 TP50 DONKEY - {p['symbol_clean']}\n\n"
        f"TP50 atingido ✅\n\n"
        f"50% da posição realizado ✅\n\n"
        f"Resultado da parcial:\n"
        f"{fmt_pct(resultado)}\n\n"
        f"Lucro garantido na posição total:\n"
        f"{fmt_pct(resultado * (DONKEY_PARTIAL_TP50_PCT / 100.0))}\n\n"
        f"Stop do restante:\n"
        f"BE + {DONKEY_BE_OFFSET_PCT}% ✅\n\n"
        f"Restante:\n"
        f"{DONKEY_REMAINING_AFTER_TP50_PCT:.0f}% aguardando fechamento H4 contra EMA20"
    )
    safe_send_telegram_donkey(msg)


def enviar_saida_ema20_donkey(p, exit_price, resultado_total):
    parcial_txt = "N/A"
    try:
        parcial_txt = fmt_pct(float(p.get("partial_realized_result_pct", 0)))
    except Exception:
        pass

    restante_result = pnl_pct(p["side"], float(p["entry"]), float(exit_price))

    msg = (
        f"🐴 🟣 SAÍDA EMA20 DONKEY - {p['symbol_clean']}\n\n"
        f"Fechamento H4 contra EMA20 confirmado ✅\n\n"
        f"Saída restante:\n"
        f"{fmt_br(exit_price)}\n\n"
        f"Resultado da parcial TP50:\n"
        f"{parcial_txt}\n\n"
        f"Resultado dos 50% restantes:\n"
        f"{fmt_pct(restante_result)}\n\n"
        f"Resultado total ponderado:\n"
        f"{fmt_pct(resultado_total)}"
    )
    safe_send_telegram_donkey(msg)



def gerenciar_donkey_position(symbol, p, preco_atual):
    """
    Gestão Donkey H4 - modelo parcial 50% + EMA20.

    Fluxo:
    1) Antes do TP50: stop normal em tempo real.
    2) Ao atingir TP50:
       - marca 50% realizado no TP50;
       - move stop do restante para BE + offset;
       - não usa mais Trailing50/Chandelier para o Donkey.
    3) Após TP50:
       - 50% restante só sai por fechamento H4 contra EMA20
         ou pelo stop BE+offset se o preço voltar.
    """
    alterou = False

    try:
        side = p["side"]
        entry = float(p["entry"])
        sl = float(p["sl"])
        tp50 = float(p["tp50"])
    except Exception as e:
        print(f"ERRO DADOS POSIÇÃO DONKEY {symbol}: {e}")
        return False

    # ====================================================
    # 1) STOP antes/depois do TP50
    # ====================================================
    if not stop_em_carencia(p):
        stop_hit = (
            (side == "LONG" and preco_atual <= sl) or
            (side == "SHORT" and preco_atual >= sl)
        )

        if stop_hit:
            # Se já houve parcial, o fechamento é apenas do restante.
            if p.get("partial_tp50_done"):
                resultado_total = calcular_pnl_total_com_parcial_donkey(p, sl)
                resultado_restante = pnl_pct(side, entry, sl)
                resultado_tipo = "WIN" if resultado_total > 0.15 else ("BREAKEVEN" if resultado_total >= -0.15 else "LOSS")

                enviar_stop(p, preco_atual, sl, resultado_total)

                registrar_evento_trade({
                    "event": "CLOSE",
                    "date": data_hoje_sp_str(),
                    "datetime": data_hora_sp_str(),
                    "symbol": symbol,
                    "symbol_clean": p["symbol_clean"],
                    "side": side,
                    "entry": entry,
                    "exit": sl,
                    "pnl": resultado_total,
                    "pnl_total_weighted": resultado_total,
                    "pnl_remainder_pct": resultado_restante,
                    "partial_realized": True,
                    "partial_realized_pct": float(p.get("partial_realized_result_pct", 0)),
                    "partial_realized_price": float(p.get("partial_realized_price", tp50)),
                    "partial_realized_position_pct": float(p.get("partial_realized_position_pct", DONKEY_PARTIAL_TP50_PCT)),
                    "remaining_position_pct": float(p.get("remaining_position_pct", DONKEY_REMAINING_AFTER_TP50_PCT)),
                    "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                    "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado_total,
                    "result_type": resultado_tipo,
                    "breakeven": bool(p.get("breakeven")),
                    "tp50_hit": bool(p.get("tp50_hit")),
                    "status": p.get("status"),
                    "exit_model": "PARTIAL50_STOP_REMAINDER"
                })

                marcar_donkey_post_exit_cooldown(symbol)

                p["closed_at"] = time.time()
                p["closed_datetime"] = data_hora_sp_str()
                p["closed_reason"] = resultado_tipo
                p["status"] = "ENCERRADO"
                return True

            # Sem parcial: comportamento normal.
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
                "status": p.get("status"),
                "exit_model": "FULL_STOP"
            })

            if resultado_tipo == "BREAKEVEN":
                adicionar_monitor_be(p, entry, sl)

            marcar_donkey_post_exit_cooldown(symbol)

            p["closed_at"] = time.time()
            p["closed_datetime"] = data_hora_sp_str()
            p["closed_reason"] = resultado_tipo
            p["status"] = "ENCERRADO"
            return True

    # ====================================================
    # 2) TP50: realiza 50% e move stop restante para BE+offset
    # ====================================================
    if DONKEY_PARTIAL_TP50_ENABLED and not p.get("tp50_hit"):
        tp50_hit = (
            (side == "LONG" and preco_atual >= tp50) or
            (side == "SHORT" and preco_atual <= tp50)
        )

        if tp50_hit:
            resultado_tp50 = pnl_pct(side, entry, tp50)

            if side == "LONG":
                novo_stop = entry * (1 + DONKEY_BE_OFFSET_PCT / 100)
            else:
                novo_stop = entry * (1 - DONKEY_BE_OFFSET_PCT / 100)

            p["tp50_hit"] = True
            p["tp50_message_sent"] = True
            p["partial_tp50_done"] = True
            p["partial_realized"] = True
            p["partial_realized_price"] = tp50
            p["partial_realized_result_pct"] = resultado_tp50
            p["partial_realized_position_pct"] = DONKEY_PARTIAL_TP50_PCT
            p["remaining_position_pct"] = DONKEY_REMAINING_AFTER_TP50_PCT
            p["sl"] = novo_stop
            p["breakeven"] = True
            p["breakeven_activated_at"] = time.time()
            p["tp50_activated_at"] = time.time()
            p["status"] = "PARCIAL 50% + EMA20"
            alterou = True

            enviar_tp50_parcial_donkey(p, tp50, resultado_tp50)

            registrar_evento_trade({
                "event": "TP50",
                "date": data_hoje_sp_str(),
                "datetime": data_hora_sp_str(),
                "symbol": symbol,
                "symbol_clean": p["symbol_clean"],
                "side": side,
                "entry": entry,
                "tp50": tp50,
                "pnl": resultado_tp50,
                "partial_realized": True,
                "partial_realized_price": tp50,
                "partial_realized_result_pct": resultado_tp50,
                "partial_realized_position_pct": DONKEY_PARTIAL_TP50_PCT,
                "remaining_position_pct": DONKEY_REMAINING_AFTER_TP50_PCT,
                "stop_after_tp50": float(p["sl"]),
                "management_model": "PARTIAL50_EMA20"
            })

            return True

    # ====================================================
    # 3) Saída final dos 50% restantes por EMA20 H4
    # ====================================================
    if p.get("partial_tp50_done") and DONKEY_EXIT_REMAINDER_ON_H4_EMA20:
        try:
            ohlcv_h4 = safe_fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=80)
            if not ohlcv_h4:
                return alterou

            df_h4 = pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"])
            df_h4 = preparar_df(df_h4)
            candle_h4 = df_h4.iloc[-2]
            close_h4 = float(candle_h4["close"])
            ema20_h4 = float(candle_h4["ema20"])

            sair_ema20 = (
                (side == "LONG" and close_h4 < ema20_h4) or
                (side == "SHORT" and close_h4 > ema20_h4)
            )

            ultimo_timestamp = int(candle_h4["time"])
            if p.get("last_ema20_exit_check_ts") == ultimo_timestamp:
                return alterou

            if sair_ema20:
                p["last_ema20_exit_check_ts"] = ultimo_timestamp
                resultado_total = calcular_pnl_total_com_parcial_donkey(p, close_h4)
                resultado_tipo = "WIN" if resultado_total > 0.15 else ("BREAKEVEN" if resultado_total >= -0.15 else "LOSS")

                enviar_saida_ema20_donkey(p, close_h4, resultado_total)

                registrar_evento_trade({
                    "event": "CLOSE",
                    "date": data_hoje_sp_str(),
                    "datetime": data_hora_sp_str(),
                    "symbol": symbol,
                    "symbol_clean": p["symbol_clean"],
                    "side": side,
                    "entry": entry,
                    "exit": close_h4,
                    "pnl": resultado_total,
                    "pnl_total_weighted": resultado_total,
                    "pnl_remainder_pct": pnl_pct(side, entry, close_h4),
                    "partial_realized": True,
                    "partial_realized_price": float(p.get("partial_realized_price", tp50)),
                    "partial_realized_result_pct": float(p.get("partial_realized_result_pct", 0)),
                    "partial_realized_position_pct": float(p.get("partial_realized_position_pct", DONKEY_PARTIAL_TP50_PCT)),
                    "remaining_position_pct": float(p.get("remaining_position_pct", DONKEY_REMAINING_AFTER_TP50_PCT)),
                    "mfe_max_pct": float(p.get("mfe_max_pct", 0)),
                    "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - resultado_total,
                    "result_type": resultado_tipo,
                    "breakeven": bool(p.get("breakeven")),
                    "tp50_hit": bool(p.get("tp50_hit")),
                    "status": "EMA20 H4 EXIT",
                    "exit_model": "PARTIAL50_EMA20"
                })

                marcar_donkey_post_exit_cooldown(symbol)

                p["closed_at"] = time.time()
                p["closed_datetime"] = data_hora_sp_str()
                p["closed_reason"] = "EMA20 H4"
                p["status"] = "ENCERRADO"
                return True

            p["last_ema20_exit_check_ts"] = ultimo_timestamp
            alterou = True

        except Exception as e:
            print(f"ERRO EMA20 DONKEY {nome_limpo(symbol)}:", e)

    return alterou


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
        f"TP50 recalculado:\n{fmt_br(s['tp50'])}"
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
        f"🐴 🟣 TRAILING50 DONKEY - {p['symbol_clean']}\n\n"
        f"Stop da metade protegida:\n{fmt_br(novo_stop)}\n\n"
        f"Proteção da metade:\n{fmt_pct(lucro_protegido)}\n\n"
        f"Trailing100:\nFechamento H4 contra EMA20"
    )


def enviar_donkey_sl50(p, stop, resultado):
    safe_send_telegram_donkey(
        f"🐴 🟠 SL50 DONKEY - {p['symbol_clean']}\n\n"
        f"50% da posição saiu no Trailing50 ✅\n\n"
        f"Saída SL50:\n{fmt_br(stop)}\n\n"
        f"Resultado da metade:\n{fmt_pct(resultado)}\n\n"
        f"Restante:\n50% aguardando fechamento H4 contra EMA20"
    )


def enviar_donkey_sl100(p, close_h4, ema20_h4, resultado_sl100, resultado_total, exit_pct):
    safe_send_telegram_donkey(
        f"🐴 🔴 SL100 DONKEY - {p['symbol_clean']}\n\n"
        f"Candle H4 fechou contra a EMA20 ✅\n\n"
        f"Fechamento H4:\n{fmt_br(close_h4)}\n\n"
        f"EMA20 H4:\n{fmt_br(ema20_h4)}\n\n"
        f"Percentual encerrado agora:\n{exit_pct}%\n\n"
        f"Resultado SL100:\n{fmt_pct(resultado_sl100)}\n\n"
        f"Resultado final ponderado:\n{fmt_pct(resultado_total)}"
    )


def enviar_tp50(p, tp50, pnl_tp):
    origem = origem_msg_trade(p)

    if origem == "DONKEY":
        status = (
            "Gestão 50/100 ativada ✅\n"
            "Trailing50: cálculo atual protege 50%\n"
            "Trailing100: fechamento H4 contra EMA20"
        )
        parcial_txt = "TP50 atingido; gestão dupla ativada ✅"
    else:
        status = "Aguardando Breakeven 1,5R ✅"
        parcial_txt = "Parcial 50% realizada ✅"

    enviar_por_origem(p, 
        f"🎯 TP50 {origem} - {p['symbol_clean']}\n\n"
        f"{parcial_txt}\n\n"
        f"Resultado no TP50:\n"
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

    if donkey_em_cooldown_pos_saida(symbol):
        restante_min = tempo_restante_cooldown_pos_saida(symbol) // 60
        print(
            f"SINAL DONKEY IGNORADO POR COOLDOWN PÓS-SAÍDA: "
            f"{nome_limpo(symbol)} | restante ~{restante_min} min"
        )
        return False

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

    try:
        risk_pct_sinal = float(s.get("risk_pct", 999))
    except Exception:
        risk_pct_sinal = 999

    if USE_MAX_RISK_FILTER and risk_pct_sinal > DONKEY_MAX_RISK_PCT:
        print(
            f"SINAL DONKEY IGNORADO POR RISCO ALTO: "
            f"{nome_limpo(symbol)} | {risk_pct_sinal:.2f}% > {DONKEY_MAX_RISK_PCT:.2f}%"
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
        "management_mode": None,
        "remaining_pct": 100.0,
        "sl50_hit": False,
        "sl50_price": None,
        "sl50_pnl": None,
        "sl50_datetime": None,
        "sl100_hit": False,
        "sl100_price": None,
        "sl100_pnl": None,
        "last_ema20_exit_h4_ts": None,
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

            if p.get("signal_type") in ["DONKEY", "EARLY_DONKEY"]:
                if gerenciar_donkey_position(symbol, p, preco_atual):
                    alterou = True
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
            f"Parcial 50% {check_bool(p.get('partial_tp50_done'))}\n"
            f"Restante EMA20 {check_bool(p.get('partial_tp50_done'))}\n"
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
            f"Parcial 50% {check_bool(p.get('partial_tp50_done'))}\n"
            f"Restante EMA20 {check_bool(p.get('partial_tp50_done'))}\n"
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
        f"Parciais 50% realizadas: {len(parciais_tp50)}",
        f"Saídas EMA20 H4: {len(saidas_ema20)}",
        f"Trailings atualizados: {len(trailings)}",
        "",
        "PnL realizado:",
        fmt_pct(pnl_total),
        "",
        "MFE médio:",
        fmt_pct(mfe_medio),
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
    parciais_tp50 = [t for t in tp50s if t.get("partial_realized")]
    saidas_ema20 = [t for t in fechados if t.get("exit_model") == "PARTIAL50_EMA20"]
    sl50s = [t for t in fechados if t.get("exit_model") == "PARTIAL50_STOP_REMAINDER"]
    sl100s = saidas_ema20
    trailing50s = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") in ["TRAILING50", "SL50"]]
    trailing100s = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") in ["TRAILING100", "SL100"]]

    lucro_tp50 = sum(float(t.get("partial_realized_result_pct", t.get("pnl", 0)) or 0) for t in parciais_tp50)
    lucro_final = sum(float(t.get("pnl", 0) or 0) for t in fechados)

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)
    mfe_medio = (sum(float(t.get("mfe_max_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0
    devolucao_media = (sum(float(t.get("mfe_gave_back_pct", 0)) for t in fechados) / len(fechados)) if fechados else 0

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
        f"TP50 parciais realizados: {len(parciais_tp50)}",
        f"SL50 / stop do restante: {len(sl50s)}",
        f"SL100 EMA20 H4: {len(sl100s)}",
        f"Trailing50: {len(trailing50s)}",
        f"Trailing100: {len(trailing100s)}",
        f"Trailings atualizados: {len(trailings)}",
        "",
        "Lucro parcial TP50:",
        fmt_pct(lucro_tp50),
        "Lucro final realizado:",
        fmt_pct(lucro_final),
        "",
        "PnL realizado:",
        fmt_pct(pnl_total),
        "",
        "MFE médio:",
        fmt_pct(mfe_medio),
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

    operacional = calcular_estado_operacional_donkey()
    linhas += [
        "",
        f"Runners ativos: {operacional.get('donkey_runners_active', 0)}",
        f"Aguardando EMA20 H4: {operacional.get('donkey_positions_waiting_ema20', 0)}",
        f"Protegidas em BE/parcial: {operacional.get('donkey_positions_protected_be', 0)}",
        "",
        f"Trades Donkey ainda ativos: {len(ativos)}"
    ]
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


def enviar_resumo_diario_se_preciso():
    agora = agora_sp()

    if agora.hour != DAILY_SUMMARY_HOUR or agora.minute < DAILY_SUMMARY_MINUTE:
        return

    if resumo_diario_ja_enviado():
        return

    try:
        safe_send_telegram_donkey(montar_resumo_donkey())
        marcar_resumo_diario_enviado()
        print("Resumo diário Donkey enviado automaticamente.")
    except Exception as e:
        print("ERRO RESUMO DIARIO DONKEY:", e)


def startup_signal_guard_active():
    try:
        return (time.time() - SERVICE_STARTED_TS) < STARTUP_SIGNAL_GRACE_SECONDS
    except Exception:
        return False


def startup_mode_txt():
    if startup_signal_guard_active():
        return f"BOOTSTRAPPING ({segundos_restantes_startup_guard()}s restantes)"
    return "OPERACIONAL"


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
                    enviar_texto(chat_id, montar_resumo_donkey())

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
                    enviar_texto(chat_id, montar_posicoes_donkey())


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

                elif texto == "/reset_donkey_all":
                    salvar_posicoes({})
                    salvar_monitor_be([])
                    salvar_trades([])
                    salvar_sinais({})
                    salvar_donkey_confirmed({})
                    salvar_donkey_cooldown({})
                    salvar_donkey_poi_cooldown({})

                    enviar_texto(
                        chat_id,
                        "✅ Donkey zerado: posições, monitor BE, histórico, sinais e cooldowns apagados."
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
                elif comando == "/reset_donkey_all":
                    salvar_posicoes({})
                    salvar_monitor_be([])
                    salvar_trades([])
                    salvar_sinais({})
                    salvar_donkey_confirmed({})
                    salvar_donkey_cooldown({})
                    salvar_donkey_poi_cooldown({})
                    enviar_texto_donkey(chat_id, "✅ Donkey zerado: posições, monitor BE, histórico, sinais e cooldowns apagados.")
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

    print("SCANNER DONKEY INICIADO")
    HEALTH["started_at"] = data_hora_sp_str()
    safe_send_telegram(
        "🐴 Robô Donkey H4 iniciado\n\n"
        f"Filtros ativos:\n"
        f"Donkey H4 ativo: {check_bool(ENABLE_DONKEY_H4)}\n"
        f"Early Donkey H4 ativo: {check_bool(ENABLE_EARLY_DONKEY_H4)}\n"
        f"Modo seletivo: ✅\n"
        f"Buffer stop/trailing: {DONKEY_BUFFER_PCT}%\n"
        f"Risco máximo por sinal: {DONKEY_MAX_RISK_PCT}%\n"
        f"POI cooldown: {DONKEY_POI_COOLDOWN_SECONDS // 3600}h\n"
        f"Limite de posições: {MAX_OPEN_POSITIONS}\n"
        f"Cooldown pós-saída: {DONKEY_POST_EXIT_COOLDOWN_SECONDS // 60} min\n"
        f"Gestão: TP50 realiza 50% + restante EMA20 H4\n"
        f"Timeframe: {DONKEY_TIMEFRAME}"
    )

    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            atualizar_thread_heartbeat("scanner")

            # Gestão exclusiva Donkey.
            posicoes = carregar_posicoes()
            alterou = False

            for symbol, p in list(posicoes.items()):
                if p.get("status") == "ENCERRADO":
                    continue
                if p.get("signal_type") not in ["DONKEY", "EARLY_DONKEY"]:
                    continue

                try:
                    ticker = safe_fetch_ticker(symbol)
                    preco_atual = float(ticker["last"])

                    if atualizar_mfe_posicao(p, preco_atual):
                        alterou = True

                    if gerenciar_donkey_position(symbol, p, preco_atual):
                        alterou = True

                except Exception as e:
                    print(f"ERRO GESTÃO DONKEY {symbol}:", e)

            if alterou:
                salvar_posicoes(posicoes)

            HEALTH["last_management_run"] = data_hora_sp_str()
            atualizar_thread_heartbeat("management")

            enviar_resumo_mensal_se_preciso()
            enviar_resumo_diario_se_preciso()

            watchlist = carregar_watchlist()
            watchlist = validar_watchlist_bingx(watchlist, avisar_telegram=True)
            HEALTH["last_watchlist_count"] = len(watchlist)

            sinais_enviados = 0
            startup_guard = startup_signal_guard_active()
            if not startup_guard:
                marcar_boot_completo()
            if startup_guard:
                print(
                    "STARTUP GUARD ATIVO: novos sinais/POIs/confirmações serão ignorados "
                    "neste ciclo para evitar lote atrasado após restart/sleep."
                )

            for symbol in watchlist:
                try:
                    posicoes = carregar_posicoes()

                    # Posição ativa Donkey: confirmar e POI Donkey.
                    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
                        if posicoes[symbol].get("signal_type") not in ["DONKEY", "EARLY_DONKEY"]:
                            continue

                        if posicoes[symbol].get("signal_type") == "EARLY_DONKEY":
                            donkey_confirmado = detectar_confirmacao_donkey_h4(symbol, posicoes[symbol])
                            if donkey_confirmado:
                                if startup_guard:
                                    print(f"CONFIRMAÇÃO DONKEY IGNORADA NO STARTUP GUARD: {nome_limpo(symbol)}")
                                else:
                                    enviar_donkey_confirmado(donkey_confirmado)
                                    registrar_evento_trade({
                                        "event": "DONKEY_CONFIRMADO",
                                        "date": data_hoje_sp_str(),
                                        "datetime": data_hora_sp_str(),
                                        "symbol": donkey_confirmado["symbol"],
                                        "symbol_clean": donkey_confirmado["symbol_clean"],
                                        "side": donkey_confirmado["side"],
                                        "entry": donkey_confirmado["entry"],
                                        "current_price": donkey_confirmado["current_price"],
                                        "sl": donkey_confirmado["sl"],
                                        "tp50": donkey_confirmado["tp50"],
                                        "risk_pct": donkey_confirmado["risk_pct"],
                                        "signal_type": "DONKEY_CONFIRMADO"
                                    })

                        poi_donkey = detectar_poi_donkey_h4(symbol, posicoes[symbol])
                        if poi_donkey:
                            if startup_guard:
                                print(f"POI DONKEY IGNORADO NO STARTUP GUARD: {nome_limpo(symbol)}")
                            else:
                                enviar_poi_donkey(poi_donkey)
                                registrar_evento_trade({
                                    "event": "POI_DONKEY",
                                    "date": data_hoje_sp_str(),
                                    "datetime": data_hora_sp_str(),
                                    "symbol": poi_donkey["symbol"],
                                    "symbol_clean": poi_donkey["symbol_clean"],
                                    "side": poi_donkey["side"],
                                    "entry": poi_donkey["entry"],
                                    "sl": poi_donkey["sl"],
                                    "tp50": poi_donkey["tp50"],
                                    "risk_pct": poi_donkey["risk_pct"],
                                    "signal_type": "POI_DONKEY"
                                })

                        continue

                    # Novos sinais Donkey.
                    early_donkey = detectar_early_donkey_h4(symbol)
                    if early_donkey:
                        timestamp = int(early_donkey["timestamp"])
                        chave = f"EARLY_DONKEY_{symbol}_{timestamp}_{early_donkey['signal']}"
                        historico = carregar_sinais()
                        if chave not in historico:
                            if startup_guard:
                                historico[chave] = True
                                salvar_sinais(historico)
                                print(f"EARLY DONKEY IGNORADO NO STARTUP GUARD: {nome_limpo(symbol)} {early_donkey['signal']}")
                            elif registrar_posicao(early_donkey):
                                historico[chave] = True
                                salvar_sinais(historico)
                                enviar_early_donkey(early_donkey)
                                sinais_enviados += 1
                        continue

                    donkey_signal = detectar_donkey_h4(symbol)
                    if donkey_signal:
                        timestamp = int(donkey_signal["timestamp"])
                        chave = f"DONKEY_{symbol}_{timestamp}_{donkey_signal['signal']}"
                        historico = carregar_sinais()
                        if chave not in historico:
                            if startup_guard:
                                historico[chave] = True
                                salvar_sinais(historico)
                                print(f"DONKEY IGNORADO NO STARTUP GUARD: {nome_limpo(symbol)} {donkey_signal['signal']}")
                            elif registrar_posicao(donkey_signal):
                                historico[chave] = True
                                salvar_sinais(historico)
                                enviar_donkey(donkey_signal)
                                sinais_enviados += 1
                        continue

                except Exception as e:
                    print(f"ERRO DONKEY EM {symbol}:", e)

            HEALTH["last_donkey_signals_sent"] = sinais_enviados
            HEALTH["last_signals_sent"] = sinais_enviados
            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
            print(f"Sinais Donkey enviados: {sinais_enviados}")

        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO SCANNER DONKEY:", e)

        time.sleep(60)


@app.route("/health")
def health():
    try:
        return json.loads(montar_health_tecnico())
    except Exception as e:
        return {"ok": False, "bot": BOT_NAME, "error": str(e)}


@app.route("/watchdog")
def watchdog():
    return montar_watchdog_status()

@app.route("/")
def home():
    return "Donkey H4 Online"


# ====================================================
# THREAD GUARD - REINÍCIO AUTOMÁTICO DE THREADS
# ====================================================

def run_thread_guarded(nome, target):
    while True:
        try:
            target()
        except Exception as e:
            HEALTH["last_error"] = f"Thread {nome} travou: {e}"
            print(f"ERRO FATAL THREAD {nome}:", e)
            try:
                safe_send_telegram_donkey(
                    f"🔴 THREAD DONKEY TRAVOU: {nome}\n\n"
                    f"Erro:\n{str(e)}\n\n"
                    "A thread será reiniciada automaticamente."
                )
            except Exception:
                pass
            time.sleep(10)


def iniciar_threads_monitoradas():
    registrar_boot()
    # IMPORTANTE: apenas UM listener Telegram deve rodar.
    # O listener duplicado listen_donkey_commands fica definido no arquivo,
    # mas NÃO é iniciado para evitar erro 409 getUpdates.
    threading.Thread(target=run_thread_guarded, args=("scanner", scanner), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("telegram_commands", listen_commands), daemon=True).start()
    threading.Thread(target=run_thread_guarded, args=("watchdog", watchdog_loop), daemon=True).start()


iniciar_threads_monitoradas()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
