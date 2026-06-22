# TREND PRO DONKEY H4
# Versão: 2026-06-20-DONKEY-H4-PURE
#
# Lógica:
# - Operação exclusiva no gráfico de 4 horas (H4).
# - ADX mínimo ajustado para 20.0 (Filtro anti-lateralização).
# - Trava de concorrência Thread-Safe para o Redis implementada.
# - Loop do scanner expandido para 240s para evitar ban por Rate Limit.
# - BUG FIX: corrigido erro visual que omitia o termo EARLY nas mensagens.
# - BUG FIX: blindagem com try/except no loop de tickers do comando /resumo.
# - ESTABILIDADE: Micro-delays de 300ms nos loops para evitar bloqueios por IP (Rate Limit).

from flask import Flask
import os
import json
import time
import threading
import requests
import pandas as pd
import ccxt
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

# Lock global para evitar concorrência de escrita/leitura no banco Redis
redis_lock = threading.Lock()

BOT_NAME = os.environ.get("BOT_NAME", "Donkey H4")
WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "45"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DONKEY_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DONKEY_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

WATCHLIST_FILE = "watchlist.json"

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
# CONFIGURAÇÕES PRINCIPAIS EXCLUSIVAS H4
# ====================================================

TIMEFRAME_H4 = "4h"
EMA20 = 20
EMA50 = 50

# ====================================================
# DONKEY H4 - SETUP INDEPENDENTE
# ====================================================
ENABLE_DONKEY_H4 = True
ENABLE_EARLY_DONKEY_H4 = True
DONKEY_TIMEFRAME = "4h"
DONKEY_EMA_FAST = 20
DONKEY_EMA_SLOW = 50
DONKEY_MACD_FAST = 12
DONKEY_MACD_SLOW = 26
DONKEY_MACD_SIGNAL = 9
DONKEY_BUFFER_PCT = 0.5  
DONKEY_SWING_LEN = 5
DONKEY_POI_COOLDOWN_SECONDS = 4 * 60 * 60  
DONKEY_RISK_USDT = float(os.environ.get("DONKEY_RISK_USDT", "10"))

SUPERTREND_PERIOD = 10
SUPERTREND_FACTOR = 3.0

ATR_LEN = 14
SWING_LEN = 5
ATR_BUFFER_STOP = 0.25

TP50_R = 1.0
TP50_MIN_ATR = 1.0  

ENABLE_SPIKE_FILTER = True
SPIKE_RANGE_ATR_MULT = 6.0
SPIKE_BODY_ATR_MULT = 4.0

DONKEY_MOVE_SL_TO_BE_ON_TP50 = True
DONKEY_BE_OFFSET_PCT = 0.10
DONKEY_USE_TRAILING50_EMA20_100 = True

MAX_OPEN_POSITIONS = 25

# ====================================================
# FILTROS E PARÂMETROS OPERACIONAIS H4
# ====================================================
ELITE_THRESHOLD = 55
ELITE_MIN_ADX_H4 = 20.0 

ADX_LEN = 14
ADX_MIN = 20.0

MONTHLY_SUMMARY_DAY = 1
MONTHLY_SUMMARY_HOUR = 8
MONTHLY_SUMMARY_MINUTE = 5

STARTUP_SIGNAL_GRACE_SECONDS = int(os.environ.get("STARTUP_SIGNAL_GRACE_SECONDS", "600"))
SERVICE_STARTED_TS = time.time()

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"

redis = Redis(
    url=UPSTASH_REDIS_REST_URL,
    token=UPSTASH_REDIS_REST_TOKEN
)

HEALTH = {
    "started_at": None,
    "last_scanner_run": None,
    "last_management_run": None,
    "last_success": None,
    "last_error": None,
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
    try:
        with open(WATCHLIST_FILE, "r") as f:
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

    if invalidos and avisar_telegram:
        msg = (
            "⚠️ Ativos inválidos na watchlist BingX:\n\n"
            + "\n".join(invalidos)
            + "\n\n"
            "Eles serão ignorados pelo scanner.\n"
        )
        print(msg)
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

def carregar_posicoes():
    return redis_get_json(POSITIONS_KEY, {})

def salvar_posicoes(dados):
    redis_set_json(POSITIONS_KEY, dados)

def carregar_trades():
    return redis_get_json(TRADES_KEY, [])

def carregar_monthly_summary_sent():
    return redis_get_json(MONTHLY_SUMMARY_KEY, {})

def salvar_monthly_summary_sent(dados):
    redis_set_json(MONTHLY_SUMMARY_KEY, dados)

def salvar_trades(dados):
    redis_set_json(TRADES_KEY, dados)

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

def fmt_risco(valor):
    try:
        return f"{float(valor):.2f}".replace(".", ",")
    except Exception:
        return str(valor)

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
    return origem in ["DONKEY", "EARLY DONKEY", "POI DONKEY", "DONKEY CONFIRMADO"]

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

def mes_anterior_ref():
    hoje = agora_sp()
    primeiro_mes_atual = hoje.replace(day=1)
    ultimo_mes_anterior = primeiro_mes_atual - timedelta(days=1)
    return ultimo_mes_anterior.strftime("%Y-%m"), ultimo_mes_anterior.strftime("%m/%Y")

def montar_resumo_mensal():
    mes_ref, mes_txt = mes_anterior_ref()
    trades = carregar_trades()
    do_mes = [t for t in trades if str(t.get("date", "")).startswith(mes_ref)]

    entries = [t for t in do_mes if t.get("event") == "ENTRY"]
    pois_donkey = [t for t in do_mes if t.get("event") == "POI_DONKEY"]
    exits = [t for t in do_mes if t.get("event") in ["EXIT", "SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in do_mes if t.get("event") == "TP50"]
    trails = [t for t in do_mes if t.get("event") == "TRAILING"]
    donkey_confirmados = [t for t in do_mes if t.get("event") == "DONKEY_CONFIRMADO"]

    longs = [t for t in entries if t.get("side") == "LONG"]
    shorts = [t for t in entries if t.get("side") == "SHORT"]
    donkeys = [t for t in entries if t.get("signal_type") == "DONKEY"]
    early_donkeys = [t for t in entries if t.get("signal_type") == "EARLY_DONKEY"]

    wins, bes, losses = [], [], []
    pnl_total = 0.0
    melhor, pior = None, None

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

    melhor_txt = f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('_pnl_calc', 0))}" if melhor else "N/A"
    pior_txt = f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('_pnl_calc', 0))}" if pior else "N/A"

    return (
        f"📊 RESUMO MENSAL DONKEY H4\nMês: {mes_txt}\n\nSinais H4: {len(entries)}\nLONG: {len(longs)}\nSHORT: {len(shorts)}\n"
        f"DONKEY H4: {len(donkeys)}\nEARLY DONKEY H4: {len(early_donkeys)}\nDONKEY CONFIRMADOS: {len(donkey_confirmados)}\n"
        f"POIs DONKEY: {len(pois_donkey)}\n\nTrades encerrados: {fechados}\nWins: {len(wins)}\nBreakeven: {len(bes)}\n"
        f"Loss: {len(losses)}\nWin rate: {win_rate:.2f}%\nWin rate sem BE: {win_rate_sem_be:.2f}%\n\n"
        f"TP50 atingidos: {len(tp50s)}\nTrailings atualizados: {len(trails)}\n\nPnL realizado:\n{fmt_pct(pnl_total)}\n\n"
        f"Melhor trade:\n{melhor_txt}\n\nPior trade:\n{pior_txt}"
    )

def enviar_resumo_mensal_se_preciso():
    with redis_lock:
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
    ok = HEALTH.get("last_error") is None and not scanner_stalled and not management_stalled

    reasons = []
    if HEALTH.get("last_error") is not None:
        reasons.append(f"last_error: {HEALTH.get('last_error')}")
    if scanner_stalled:
        reasons.append(f"scanner parado há {minutes_since_scanner} min")
    if management_stalled:
        reasons.append(f"gestão parada há {minutes_since_management} min")

    return {
        "ok": ok, "bot": BOT_NAME, "last_scanner_run": HEALTH.get("last_scanner_run"),
        "last_management_run": HEALTH.get("last_management_run"), "minutes_since_scanner": minutes_since_scanner,
        "minutes_since_management": minutes_since_management, "last_error": HEALTH.get("last_error"),
        "status": "OK" if ok else "ALERTA", "reasons": reasons
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
    msg = f"🚨 WATCHDOG - {BOT_NAME}\n\nO robô pode estar travado.\n\nMotivos:\n" + "\n".join([f"- {m}" for m in motivos])
    safe_send_telegram_donkey(msg)
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
                enviar_alerta_watchdog(status)
        except Exception as e:
            print("ERRO WATCHDOG:", e)
        time.sleep(WATCHDOG_CHECK_SECONDS)

def montar_health_tecnico():
    try:
        posicoes = carregar_posicoes()
        abertas = [p for p in posicoes.values() if p.get("status") != "ENCERRADO"]
        HEALTH["last_positions_count"] = len(abertas)
    except Exception:
        abertas = []

    positions_open = HEALTH.get("last_positions_count", 0)
    usage_pct = (positions_open / MAX_OPEN_POSITIONS * 100) if MAX_OPEN_POSITIONS else 0
    watchdog = montar_watchdog_status()

    payload = {
        "ok": HEALTH.get("last_error") is None, "uptime_horas": calcular_uptime_horas(),
        "last_scanner_run": HEALTH.get("last_scanner_run"), "last_management_run": HEALTH.get("last_management_run"),
        "positions_open": positions_open, "positions_limit": MAX_OPEN_POSITIONS, "positions_usage_pct": round(usage_pct, 2),
        "elite_min_adx_h4": ELITE_MIN_ADX_H4, "donkey_h4_enabled": ENABLE_DONKEY_H4, "watchdog_status": watchdog.get("status")
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def origem_trade_txt(p):
    origem = p.get("signal_type") or p.get("origin") or "NORMAL"
    mapeamento = {
        "DONKEY": "DONKEY H4",
        "EARLY_DONKEY": "EARLY DONKEY", 
        "POI_DONKEY": "POI DONKEY"
    }
    return mapeamento.get(origem, str(origem))

def origem_msg_trade(p):
    origem = origem_trade_txt(p)
    if origem == "DONKEY H4":
        return "DONKEY"
    if origem == "EARLY DONKEY":
        return "EARLY DONKEY"
    return origem

# ====================================================
# INDICADORES EXCLUSIVOS H4
# ====================================================

def calcular_supertrend_df(df, period=10, multiplier=3.5):
    high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
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

def calcular_adx(df, period=14):
    high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    up_move, down_move = high.diff(), -low.diff()

    plus_dm = pd.Series([u if u > d and u > 0 else 0 for u, d in zip(up_move, down_move)], index=df.index)
    minus_dm = pd.Series([d if d > u and d > 0 else 0 for u, d in zip(up_move, down_move)], index=df.index)

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx, plus_di, minus_di

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
    df["spike_suspeito"] = ((candle_range > (atr * SPIKE_RANGE_ATR_MULT)) | (candle_body > (atr * SPIKE_BODY_ATR_MULT))).fillna(False)
    return df

def preparar_df(df):
    df = df.copy()
    df["ema20"] = df["close"].ewm(span=EMA20, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean()
    df["atr14"] = calcular_atr(df, ATR_LEN)
    df = marcar_spikes(df)

    _, st_dir = calcular_supertrend_df(df, period=SUPERTREND_PERIOD, multiplier=SUPERTREND_FACTOR)
    df["supertrend_dir"] = st_dir

    adx, plus_di, minus_di = calcular_adx(df, ADX_LEN)
    df["adx"], df["plus_di"], df["minus_di"] = adx, plus_di, minus_di

    macd_fast = df["close"].ewm(span=DONKEY_MACD_FAST, adjust=False).mean()
    macd_slow = df["close"].ewm(span=DONKEY_MACD_SLOW, adjust=False).mean()
    df["macd"] = macd_fast - macd_slow
    df["macd_signal"] = df["macd"].ewm(span=DONKEY_MACD_SIGNAL, adjust=False).mean()
    return df

def detectar_early_donkey_h4(symbol):
    if not ENABLE_EARLY_DONKEY_H4 or existe_posicao_ativa(symbol): return None
    ohlcv_h4 = exchange.fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]
    if bool(candle.get("spike_suspeito", False)): return None

    close, high, low, ema20, ema50, macd = float(candle["close"]), float(candle["high"]), float(candle["low"]), float(candle["ema20"]), float(candle["ema50"]), float(candle["macd"])
    signal = "LONG" if (close > ema20 and macd > 0 and ema20 <= ema50) else ("SHORT" if (close < ema20 and macd < 0 and ema20 >= ema50) else None)
    if not signal or donkey_em_cooldown(symbol, f"EARLY_{signal}", int(candle["time"])): return None

    sl = low * (1 - DONKEY_BUFFER_PCT / 100) if signal == "LONG" else high * (1 + DONKEY_BUFFER_PCT / 100)
    risk_abs = abs(close - sl)
    marcar_donkey_cooldown(symbol, f"EARLY_{signal}", int(candle["time"]))

    return {
        "type": "EARLY_DONKEY", "signal_type": "EARLY_DONKEY", "symbol": symbol, "symbol_clean": nome_limpo(symbol),
        "signal": signal, "side": signal, "timestamp": int(candle["time"]), "entry": close, "sl": sl,
        "tp50": close + risk_abs * TP50_R if signal == "LONG" else close - risk_abs * TP50_R, "risk_abs": risk_abs,
        "risk_pct": risk_abs / close * 100, "h4_state": 1 if signal == "LONG" else -1, "qualidade": "EARLY DONKEY H4 🐴"
    }

def detectar_donkey_h4(symbol):
    if not ENABLE_DONKEY_H4 or existe_posicao_ativa(symbol): return None
    ohlcv_h4 = exchange.fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]
    if bool(candle.get("spike_suspeito", False)): return None

    close, high, low, ema20, ema50, macd = float(candle["close"]), float(candle["high"]), float(candle["low"]), float(candle["ema20"]), float(candle["ema50"]), float(candle["macd"])
    signal = "LONG" if (close > ema20 and ema20 > ema50 and macd > 0) else ("SHORT" if (close < ema20 and ema20 < ema50 and macd < 0) else None)
    if not signal or donkey_em_cooldown(symbol, signal, int(candle["time"])): return None

    sl = low * (1 - DONKEY_BUFFER_PCT / 100) if signal == "LONG" else high * (1 + DONKEY_BUFFER_PCT / 100)
    risk_abs = abs(close - sl)
    marcar_donkey_cooldown(symbol, signal, int(candle["time"]))

    return {
        "type": "DONKEY", "signal_type": "DONKEY", "symbol": symbol, "symbol_clean": nome_limpo(symbol),
        "signal": signal, "side": signal, "timestamp": int(candle["time"]), "entry": close, "sl": sl,
        "tp50": close + risk_abs * TP50_R if signal == "LONG" else close - risk_abs * TP50_R, "risk_abs": risk_abs,
        "risk_pct": risk_abs / close * 100, "h4_state": 1 if signal == "LONG" else -1, "qualidade": "DONKEY H4 🐴"
    }

def detectar_confirmacao_donkey_h4(symbol, posicao):
    if posicao.get("signal_type") != "EARLY_DONKEY": return None
    side = posicao.get("side")
    ohlcv_h4 = exchange.fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=200)
    df_h4 = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    candle = df_h4.iloc[-2]
    if bool(candle.get("spike_suspeito", False)) or donkey_confirmado_ja_enviado(symbol, side, int(candle["time"])): return None

    close, ema20, ema50, macd = float(candle["close"]), float(candle["ema20"]), float(candle["ema50"]), float(candle["macd"])
    confirmado = (close > ema20 and ema20 > ema50 and macd > 0) if side == "LONG" else (close < ema20 and ema20 < ema50 and macd < 0)
    if not confirmado: return None

    posicoes = carregar_posicoes()
    p = posicoes.get(symbol, posicao)
    risk_abs = abs(close - float(p["sl"]))
    p["entry"], p["tp50"], p["risk_abs"], p["signal_type"], p["status"] = close, (close + risk_abs * TP50_R if side == "LONG" else close - risk_abs * TP50_R), risk_abs, "DONKEY", "ATIVO"
    posicoes[symbol] = p
    salvar_posicoes(posicoes)
    marcar_donkey_confirmado(symbol, side, int(candle["time"]))

    return {"type": "DONKEY_CONFIRMADO", "symbol": symbol, "symbol_clean": nome_limpo(symbol), "signal": side, "side": side, "entry": close, "sl": p["sl"], "tp50": p["tp50"], "early_entry": posicao.get("entry")}

def registrar_fechamento_donkey(symbol, p, exit_price, resultado_total, closed_by):
    registrar_evento_trade({
        "event": "CLOSE", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "symbol": symbol,
        "symbol_clean": p["symbol_clean"], "side": p["side"], "entry": float(p["entry"]), "exit": float(exit_price),
        "pnl": float(resultado_total), "result_type": "WIN" if resultado_total > 0 else "LOSS", "signal_type": "DONKEY", "closed_by": closed_by
    })
    p["status"] = "ENCERRADO"

def buscar_candle_h4_fechado(symbol):
    ohlcv_h4 = exchange.fetch_ohlcv(symbol, timeframe=DONKEY_TIMEFRAME, limit=120)
    return preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"])).iloc[-2]

def gerenciar_donkey_position(symbol, p, preco_atual):
    side, entry, sl = p["side"], float(p["entry"]), float(p["sl"])
    tp50_hit, sl50_hit = bool(p.get("tp50_hit", False)), bool(p.get("sl50_hit", False))

    if (side == "LONG" and preco_atual <= sl) or (side == "SHORT" and preco_atual >= sl):
        res = pnl_pct(side, entry, sl)
        if not tp50_hit:
            enviar_stop(p, preco_atual, sl, res)
            registrar_fechamento_donkey(symbol, p, sl, res, "DONKEY_STOP")
            return True
        elif not sl50_hit:
            p["sl50_hit"], p["remaining_pct"], p["status"] = True, 50.0, "DONKEY SL50 / AGUARDANDO EMA20 H4"
            enviar_donkey_sl50(p, sl, res)
            return True

    if not p.get("tp50_hit"):
        if (side == "LONG" and preco_atual >= float(p["tp50"])) or (side == "SHORT" and preco_atual <= float(p["tp50"])):
            p["tp50_hit"] = True
            if DONKEY_MOVE_SL_TO_BE_ON_TP50:
                p["sl"] = entry * (1 + DONKEY_BE_OFFSET_PCT / 100) if side == "LONG" else entry * (1 - DONKEY_BE_OFFSET_PCT / 100)
            enviar_tp50(p, float(p["tp50"]), pnl_pct(side, entry, float(p["tp50"])))
            return True

    if tp50_hit:
        c4 = buscar_candle_h4_fechado(symbol)
        inv = (side == "LONG" and float(c4["close"]) < float(c4["ema20"])) or (side == "SHORT" and float(c4["close"]) > float(c4["ema20"]))
        if inv:
            res_sl100 = pnl_pct(side, entry, float(c4["close"]))
            res_tot = (float(p.get("sl50_pnl", 0)) * 0.5 + res_sl100 * 0.5) if sl50_hit else res_sl100
            enviar_donkey_sl100(p, float(c4["close"]), float(c4["ema20"]), res_sl100, res_tot, 50 if sl50_hit else 100)
            registrar_fechamento_donkey(symbol, p, float(c4["close"]), res_tot, "EMA20_H4_EXIT")
            return True
    return False

# ====================================================
# EMISSÃO TELEGRAM
# ====================================================

def enviar_early_donkey(s):
    safe_send_telegram_donkey(f"🐴 🚀 EARLY DONKEY {s['signal']} - {s['symbol_clean']}\n\nEntrada: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}")

def enviar_donkey(s):
    safe_send_telegram_donkey(f"🐴 DONKEY {s['signal']} - {s['symbol_clean']}\n\nEntrada: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}")

def enviar_donkey_confirmado(s):
    safe_send_telegram_donkey(f"🐴 ✅ DONKEY {s['signal']} CONFIRMADO - {s['symbol_clean']}\n\nEarly Donkey virou Donkey completo! ✅\n\nPreço Confirmação: {fmt_br(s['entry'])}\nTP50 Recalculado: {fmt_br(s['tp50'])}")

def enviar_donkey_sl50(p, stop, res):
    safe_send_telegram_donkey(f"🐴 🟠 SL50 - {p['symbol_clean']}\n\nMetade da posição reduzida no Trailing Stop: {fmt_pct(res)}")

def enviar_donkey_sl100(p, cl, ema, r100, rtot, pct):
    safe_send_telegram_donkey(f"🐴 🔴 SL100 - {p['symbol_clean']}\n\nFechamento H4 contra EMA20: {fmt_br(cl)}\nResultado Ponderado Final: {fmt_pct(rtot)}")

def enviar_tp50(p, tp, pnl):
    origem = origem_msg_trade(p)
    enviar_por_origem(p, f"🎯 TP50 {origem} - {p['symbol_clean']}\n\nParcial 50% Realizada: {fmt_pct(pnl)}")

def enviar_stop(p, pr, stop, res):
    origem = origem_msg_trade(p)
    enviar_por_origem(p, f"🟠 STOP {origem} - {p['symbol_clean']}\n\nSaída: {fmt_br(stop)}\nResultado: {fmt_pct(res)}")

# ====================================================
# PROCESSAMENTO CENTRAL (SCANNER LOOP COM DELAYS)
# ====================================================

def registrar_posicao(s):
    posicoes = carregar_posicoes()
    if s["symbol"] in posicoes and posicoes[s["symbol"]].get("status") != "ENCERRADO": return False
    if len([p for p in posicoes.values() if p.get("status") != "ENCERRADO"]) >= MAX_OPEN_POSITIONS: return False

    posicoes[s["symbol"]] = {
        "symbol": s["symbol"], "symbol_clean": s["symbol_clean"], "side": s["side"], "entry": s["entry"],
        "sl": s["sl"], "tp50": s["tp50"], "status": "ATIVO", "signal_type": s["signal_type"], "created_at": time.time()
    }
    salvar_posicoes(posicoes)
    registrar_evento_trade({"event": "ENTRY", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "symbol": s["symbol"], "side": s["side"], "entry": s["entry"], "signal_type": s["signal_type"]})
    return True

def montar_resumo_donkey():
    hoje = data_hoje_sp_str()
    data_br = agora_sp().strftime("%d/%m/%Y")
    trades = carregar_trades()
    trades_donkey = [t for t in trades if is_donkey_trade_event(t)]

    entradas = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "ENTRY"]
    donkeys = [t for t in entradas if t.get("signal_type") == "DONKEY"]
    early_donkeys = [t for t in entradas if t.get("signal_type") == "EARLY_DONKEY"]
    confirmados = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "DONKEY_CONFIRMADO"]
    fechados = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "CLOSE"]
    tp50s = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "TP50"]
    trailings = [t for t in trades_donkey if t.get("date") == hoje and t.get("event") == "TRAILING"]

    wins = [t for t in fechados if t.get("result_type") == "WIN"]
    losses = [t for t in fechados if t.get("result_type") == "LOSS"]
    bes = [t for t in fechados if t.get("result_type") == "BREAKEVEN"]
    pnl_total = sum(float(t.get("pnl", 0)) for t in fechados)

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]
    melhor = max(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None
    pior = min(fechados, key=lambda x: float(x.get("pnl", 0))) if fechados else None

    linhas = [
        "🐴 📈 RESUMO DONKEY H4", data_br, "",
        f"Sinais Donkey do dia: {len(entradas)}", f"LONG: {len(longs)}", f"SHORT: {len(shorts)}",
        f"DONKEY H4: {len(donkeys)}", f"EARLY DONKEY H4: {len(early_donkeys)}",
        f"DONKEY CONFIRMADOS: {len(confirmados)}", "",
        f"Trades encerrados: {len(fechados)}", f"Wins: {len(wins)}", f"Breakeven: {len(bes)}", f"Loss: {len(losses)}", "",
        f"TP50 atingidos: {len(tp50s)}", f"Trailings atualizados: {len(trailings)}", "",
        "PnL realizado:", fmt_pct(pnl_total), "",
        "Melhor trade:", f"{melhor.get('symbol_clean', melhor.get('symbol', 'N/A'))} {fmt_pct(melhor.get('pnl', 0))}" if melhor else "N/A", "",
        "Pior trade:", f"{pior.get('symbol_clean', pior.get('symbol', 'N/A'))} {fmt_pct(pior.get('pnl', 0))}" if pior else "N/A",
    ]

    posicoes = carregar_posicoes()
    ativos = []
    
    for symbol, p in posicoes.items():
        if p.get("status") == "ENCERRADO" or not is_donkey_signal_type(p.get("signal_type")): 
            continue
        try:
            ticker = exchange.fetch_ticker(symbol)
            preco = float(ticker["last"])
            pnl = pnl_pct(p["side"], float(p["entry"]), preco)
            ativos.append(f"{p['symbol_clean']} {p['side']} | Origem: {origem_trade_txt(p)} | PnL {fmt_pct(pnl)}")
        except Exception as e:
            print(f"Erro de conexão temporário na BingX para {symbol}: {e}")
            ativos.append(f"{p.get('symbol_clean', symbol)} {p.get('side', '')} | Origem: {origem_trade_txt(p)} | PnL N/A (BingX Off)")

    linhas += ["", f"Trades Donkey ainda ativos: {len(ativos)}"]
    if ativos: 
        linhas.extend(ativos[:20])

    return "\n".join(linhas)

def scanner():
    print("SCANNER DONKEY INICIADO")
    HEALTH["started_at"] = data_hora_sp_str()

    while True:
        try:
            with redis_lock:
                HEALTH["last_scanner_run"] = data_hora_sp_str()
                posicoes = carregar_posicoes()
                alterou = False

                for symbol, p in list(posicoes.items()):
                    if p.get("status") == "ENCERRADO" or p.get("signal_type") not in ["DONKEY", "EARLY_DONKEY"]: continue
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        if gerenciar_donkey_position(symbol, p, float(ticker["last"])): alterou = True
                        
                        # 300ms de respiro entre o gerenciamento de cada ativo
                        time.sleep(0.3)
                        
                    except Exception as e: print(f"ERRO GESTÃO {symbol}:", e)

                if alterou: salvar_posicoes(posicoes)
                HEALTH["last_management_run"] = data_hora_sp_str()

                enviar_resumo_mensal_se_preciso()

                watchlist = validar_watchlist_bingx(carregar_watchlist())
                startup_guard = (time.time() - SERVICE_STARTED_TS) < STARTUP_SIGNAL_GRACE_SECONDS

                for symbol in watchlist:
                    # 300ms de delay para evitar Rate Limit na leitura de histórico
                    time.sleep(0.3)
                    
                    posicoes = carregar_posicoes()
                    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
                        if posicoes[symbol].get("signal_type") == "EARLY_DONKEY":
                            conf = detectar_confirmacao_donkey_h4(symbol, posicoes[symbol])
                            if conf and not startup_guard: enviar_donkey_confirmado(conf)
                        continue

                    ed = detectar_early_donkey_h4(symbol)
                    if ed and registrar_posicao(ed) and not startup_guard: enviar_early_donkey(ed)

                    dk = detectar_donkey_h4(symbol)
                    if dk and registrar_posicao(dk) and not startup_guard: enviar_donkey(dk)

            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None
        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO CRÍTICO NO SCANNER:", e)
        
        time.sleep(240)

# ====================================================
# TELEGRAM COMMAND LISTENERS & FLASK
# ====================================================

def listen_commands():
    last_update_id = 0
    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id + 1}", timeout=30).json()
            for update in resp.get("result", []):
                last_update_id = update.get("update_id", last_update_id)
                msg = update.get("message", {})
                texto = msg.get("text", "").strip()
                chat_id = msg.get("chat", {}).get("id")
                if not chat_id: continue

                try:
                    if texto == "/health":
                        enviar_texto(chat_id, montar_health_tecnico())
                    elif texto == "/teste":
                        enviar_texto(chat_id, "✅ Robô operacional e conectado.")
                    elif texto == "/resumo":
                        enviar_texto(chat_id, montar_resumo_donkey())
                    elif texto == "/posicoes":
                        with redis_lock:
                            posicoes = carregar_posicoes()
                        linhas = []
                        for p in posicoes.values():
                            if p.get("status") == "ENCERRADO" or not is_donkey_signal_type(p.get("signal_type")): continue
                            linhas.append(f"{p['symbol_clean']} {p['side']} | Tipo: {origem_trade_txt(p)} | Status: {p['status']}")
                        enviar_texto(chat_id, "🐴 Posições Donkey Ativas:\n\n" + "\n".join(linhas) if linhas else "🐴 Nenhuma posição Donkey aberta.")
                except Exception as cmd_err:
                    print(f"Erro ao processar comando {texto}: {cmd_err}")
                    enviar_texto(chat_id, "⚠️ Ocorreu um erro ao gerar esse relatório. Tente novamente.")

        except Exception as e: 
            print("ERRO NA THREAD DO TELEGRAM:", e)
        time.sleep(3)

@app.route("/health")
def health(): return montar_health_tecnico()

@app.route("/")
def home(): return "Donkey H4 Online"

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=listen_commands, daemon=True).start()
threading.Thread(target=watchdog_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
