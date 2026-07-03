# Ajuste Central Quant: startup guard padronizado em 0 por padrão; arquitetura alinhada em PREDATOR.
# SMART PREDATOR - SMC H1
# Versão: 2026-06-27-SMART-PREDATOR-V6-H4-CONTEXT-BLOCK
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
from exchange_manager import get_exchange, load_markets_once
from datetime import datetime, timezone, timedelta
from upstash_redis import Redis

# ====================================================
# BROKER / EXECUÇÃO REAL SAFE MODE
# ====================================================
try:
    import broker as bingx_broker
    BROKER_IMPORT_ERROR = None
except Exception as _broker_exc:
    bingx_broker = None
    BROKER_IMPORT_ERROR = str(_broker_exc)

app = Flask(__name__)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


# ====================================================
# IDENTIDADE / STAND-BY / LOCKS
# ====================================================

BOT_NAME = os.environ.get("BOT_NAME", "Smart Predator")
SERVICE_MODE = "SMART_PREDATOR"
BOT_VERSION = "2026-06-27-SMART-PREDATOR-V6-H4-CONTEXT-BLOCK"

# Padrão Central Quant: este bot não usa startup guard para sinais.
# Mantido explícito para padronização de /health e evitar bloqueios após deploy.
STARTUP_SIGNAL_GRACE_SECONDS = int(
    os.environ.get(
        "PREDATOR_STARTUP_SIGNAL_GRACE_SECONDS",
        os.environ.get("STARTUP_SIGNAL_GRACE_SECONDS", "0")
    )
)

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

exchange = get_exchange()

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

# Modos padronizados da Central Quant para execução real segura:
# PAPER  = comportamento atual, apenas simulação/estatística do robô.
# READY  = valida broker/central, sem montar ordem.
# VERIFY = consulta Risk Manager, monta ordem completa, NÃO envia ordem real.
# LIVE   = envia automaticamente se ENABLE_REAL_TRADING=true e Risk Manager permitir.
PREDATOR_MODE = os.environ.get("PREDATOR_MODE", os.environ.get("SMART_PREDATOR_MODE", "PAPER")).strip().upper()
PREDATOR_REAL_MARGIN_USDT = float(os.environ.get("PREDATOR_REAL_MARGIN_USDT", os.environ.get("SMART_PREDATOR_REAL_MARGIN_USDT", os.environ.get("DEFAULT_REAL_MARGIN_USDT", os.environ.get("REAL_TRADING_MARGIN_USDT", os.environ.get("PREDATOR_REAL_NOTIONAL_USDT", "20"))))))
PREDATOR_REAL_LEVERAGE = int(os.environ.get("PREDATOR_REAL_LEVERAGE", os.environ.get("SMART_PREDATOR_REAL_LEVERAGE", os.environ.get("DEFAULT_REAL_LEVERAGE", os.environ.get("REAL_TRADING_LEVERAGE", "3")))))
PREDATOR_REAL_NOTIONAL_USDT = PREDATOR_REAL_MARGIN_USDT * PREDATOR_REAL_LEVERAGE
PREDATOR_MAX_REAL_POSITIONS = int(os.environ.get("PREDATOR_MAX_REAL_POSITIONS", "1"))
PREDATOR_REQUIRE_CENTRAL_RISK = env_bool("PREDATOR_REQUIRE_CENTRAL_RISK", True)
PREDATOR_EXECUTION_NOTIFY = env_bool("PREDATOR_EXECUTION_NOTIFY", True)
CENTRAL_BASE_URL = os.environ.get("CENTRAL_BASE_URL", f"http://127.0.0.1:{os.environ.get('PORT', '10000')}").rstrip("/")

SCANNER_SLEEP_SECONDS = int(os.environ.get("PREDATOR_SCANNER_SLEEP_SECONDS", os.environ.get("SCANNER_SLEEP_SECONDS", "60")))
COMMAND_SLEEP_SECONDS = int(os.environ.get("COMMAND_SLEEP_SECONDS", "2"))

SWING_LOOKBACK = int(os.environ.get("PREDATOR_SWING_LOOKBACK", "10"))
CHOCH_LOOKBACK = int(os.environ.get("PREDATOR_CHOCH_LOOKBACK", "8"))
OB_LOOKBACK = int(os.environ.get("PREDATOR_OB_LOOKBACK", "12"))

MIN_PREDATOR_SCORE = int(os.environ.get("PREDATOR_MIN_SCORE", os.environ.get("MIN_PREDATOR_SCORE", "70")))

# Filtro V6: bloqueia entradas contra H4 forte por padrão.
# Evita casos como LONG contra H4 BEARISH com ADX forte.
PREDATOR_BLOCK_STRONG_H4_CONTRA = env_bool("PREDATOR_BLOCK_STRONG_H4_CONTRA", True)
PREDATOR_STRONG_H4_ADX = float(os.environ.get("PREDATOR_STRONG_H4_ADX", "30"))

# Exceção opcional e bem restritiva para reversões realmente excepcionais.
# Por padrão fica desligada. Para ativar: PREDATOR_ALLOW_EXCEPTIONAL_COUNTER_H4=true.
PREDATOR_ALLOW_EXCEPTIONAL_COUNTER_H4 = env_bool("PREDATOR_ALLOW_EXCEPTIONAL_COUNTER_H4", False)
PREDATOR_COUNTER_H4_EXCEPTION_MIN_SCORE = int(os.environ.get("PREDATOR_COUNTER_H4_EXCEPTION_MIN_SCORE", "95"))
PREDATOR_COUNTER_H4_EXCEPTION_MIN_VOLUME = float(os.environ.get("PREDATOR_COUNTER_H4_EXCEPTION_MIN_VOLUME", "2.5"))
PREDATOR_COUNTER_H4_EXCEPTION_MAX_RISK = float(os.environ.get("PREDATOR_COUNTER_H4_EXCEPTION_MAX_RISK", "0.70"))

ATR_LEN = int(os.environ.get("ATR_LEN", "14"))
ADX_LEN = int(os.environ.get("ADX_LEN", "14"))
EMA50 = 50

MIN_ADX_H4 = float(os.environ.get("PREDATOR_MIN_ADX_H4", os.environ.get("MIN_ADX_H4", "15")))
VOLUME_MULTIPLIER = float(os.environ.get("PREDATOR_VOLUME_MULTIPLIER", os.environ.get("VOLUME_MULTIPLIER", "1.2")))

MAX_OPEN_POSITIONS = int(os.environ.get("PREDATOR_MAX_OPEN_POSITIONS", os.environ.get("MAX_OPEN_POSITIONS", "8")))
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
    "watchdog_last_status": "OK",
    "execution_mode": PREDATOR_MODE,
    "execution_enabled": PREDATOR_MODE in {"READY", "VERIFY", "LIVE"},
    "execution_last_decision": None,
    "execution_last_result": None,
    "execution_last_error": None,
    "execution_last_run": None,
    "broker_import_error": BROKER_IMPORT_ERROR
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
    "score_90_plus": 0,
    "score_95_plus": 0,
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


def fmt_r(v):
    try:
        return f"{float(v):+.2f}R".replace(".", ",")
    except Exception:
        return str(v)


def fmt_pf(v):
    try:
        v = float(v)
        if v == float("inf"):
            return "∞"
        return f"{v:.2f}".replace(".", ",")
    except Exception:
        return str(v)


def safe_float(v, default=0.0):
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def pct_to_r(pct, risk_pct):
    risk_pct = abs(safe_float(risk_pct, 0.0))
    if risk_pct <= 0:
        return 0.0
    return safe_float(pct, 0.0) / risk_pct


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
        markets = load_markets_once()
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


def atualizar_mae_posicao(p, preco_atual):
    try:
        side = p.get("side")
        entry = float(p.get("entry"))
        pnl_atual = pnl_pct(side, entry, float(preco_atual))
        mae_atual = float(p.get("mae_min_pct", 0))
        if pnl_atual < mae_atual:
            p["mae_min_pct"] = pnl_atual
            p["mae_updated_at"] = data_hora_sp_str()
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



def is_h4_contra_signal(side, h4_context):
    side = str(side or "").upper().strip()
    h4_context = str(h4_context or "").upper().strip()

    if side == "LONG" and h4_context == "BEARISH":
        return True
    if side == "SHORT" and h4_context == "BULLISH":
        return True
    return False


def should_block_predator_by_h4_context(side, h4_context, adx_h4, score=None, volume_ratio=None, risk_pct=None):
    """
    Filtro V6 de decisão, não apenas pontuação.

    Regra principal:
    - LONG contra H4 BEARISH com ADX forte -> BLOQUEIA.
    - SHORT contra H4 BULLISH com ADX forte -> BLOQUEIA.

    Exceção opcional, desligada por padrão:
    - score >= 95
    - volume >= 2.5x
    - risco <= 0.70%
    """
    if not PREDATOR_BLOCK_STRONG_H4_CONTRA:
        return False, None

    try:
        adx = float(adx_h4)
    except Exception:
        adx = 0.0

    if not is_h4_contra_signal(side, h4_context):
        return False, None

    if adx < PREDATOR_STRONG_H4_ADX:
        return False, None

    reason = (
        f"Bloqueado: {side} contra H4 {h4_context} "
        f"com ADX forte {adx:.2f} >= {PREDATOR_STRONG_H4_ADX:.2f}"
    )

    if PREDATOR_ALLOW_EXCEPTIONAL_COUNTER_H4:
        sc = safe_float(score, 0.0)
        vr = safe_float(volume_ratio, 0.0)
        rp = safe_float(risk_pct, 999.0)

        if (
            sc >= PREDATOR_COUNTER_H4_EXCEPTION_MIN_SCORE
            and vr >= PREDATOR_COUNTER_H4_EXCEPTION_MIN_VOLUME
            and rp <= PREDATOR_COUNTER_H4_EXCEPTION_MAX_RISK
        ):
            return False, (
                "Exceção liberada: H4 contra forte, porém score/volume/risco "
                f"excepcionais | score={sc:.0f}, volume={vr:.2f}x, risco={rp:.2f}%"
            )

    return True, reason


def calcular_predator_score(
    has_sweep,
    has_choch,
    has_ob,
    has_rejection,
    adx_h4,
    volume_ok,
    risk_pct=None,
    volume_ratio=None,
    side=None,
    h4_context=None
):
    """
    Score v6:
    - Mantém SMC como base forte.
    - Penaliza H4 contra tendência.
    - Penaliza volume muito fraco.
    - Impede sinal contra H4 forte de receber 90+ facilmente.
    """

    score = 0
    reasons = []

    if has_sweep:
        score += 25
        reasons.append("Liquidity Sweep H1 confirmado ✅")

    if has_choch:
        score += 20
        reasons.append("CHOCH estrutural confirmado M15 ✅")

    if has_ob:
        score += 20
        reasons.append("Order Block H1 identificado ✅")

    if has_rejection:
        score += 15
        reasons.append("Reteste com rejeição no OB ✅")

    try:
        adx = float(adx_h4)
        if adx >= 30:
            score += 8
            reasons.append(f"ADX H4 forte: {adx:.2f} ✅")
        elif adx >= 22:
            score += 6
            reasons.append(f"ADX H4 bom: {adx:.2f} ✅")
        elif adx >= MIN_ADX_H4:
            score += 4
            reasons.append(f"ADX H4 aceitável: {adx:.2f} ✅")
        else:
            reasons.append(f"ADX H4 baixo: {adx:.2f} ⚠️")
    except Exception:
        adx = 0.0
        reasons.append("ADX H4 indisponível ⚠️")

    vr = safe_float(volume_ratio, 0.0)

    if volume_ok:
        if vr >= 2.0:
            score += 6
            reasons.append(f"Volume muito acima da média: {vr:.2f}x ✅")
        elif vr >= 1.5:
            score += 5
            reasons.append(f"Volume forte: {vr:.2f}x ✅")
        else:
            score += 3
            reasons.append(f"Volume acima da média: {vr:.2f}x ✅")
    else:
        if vr < 0.50:
            score -= 8
            reasons.append(f"Volume muito fraco: {vr:.2f}x ⚠️ Penalidade -8")
        elif vr < 0.80:
            score -= 4
            reasons.append(f"Volume fraco: {vr:.2f}x ⚠️ Penalidade -4")
        else:
            reasons.append(f"Volume sem destaque: {vr:.2f}x ⚠️")

    rp = safe_float(risk_pct, 999.0)

    if rp <= 1.0:
        score += 4
        reasons.append(f"Risco curto: {rp:.2f}% ✅")
    elif rp <= 1.5:
        score += 3
        reasons.append(f"Risco bom: {rp:.2f}% ✅")
    elif rp <= 2.0:
        score += 2
        reasons.append(f"Risco aceitável: {rp:.2f}% ✅")
    elif rp <= MAX_RISK_H1:
        score += 1
        reasons.append(f"Risco no limite: {rp:.2f}% ⚠️")
    else:
        reasons.append(f"Risco acima do limite: {rp:.2f}% ❌")

    h4_contra = False

    if h4_context and side:
        if side == "LONG" and h4_context == "BULLISH":
            score += 4
            reasons.append("Contexto H4 favorece LONG ✅")
        elif side == "SHORT" and h4_context == "BEARISH":
            score += 4
            reasons.append("Contexto H4 favorece SHORT ✅")
        elif h4_context == "NEUTRO":
            score += 1
            reasons.append("Contexto H4 neutro ⚪")
        else:
            h4_contra = True
            penalty = 15 if adx >= 30 else 10
            score -= penalty
            reasons.append(f"Contexto H4 contra o sinal: {h4_context} ⚠️ Penalidade -{penalty}")

    score = max(0, min(int(score), 100))

    # Teto de segurança:
    # contra H4 forte não pode ser 90+.
    if h4_contra and adx >= 30:
        score = min(score, 84)
        reasons.append("Teto aplicado: H4 contra com ADX forte limita score a 84 ⚠️")

    # Volume extremamente fraco não pode ser EXCEPCIONAL/MUITO FORTE.
    if vr > 0 and vr < 0.50:
        score = min(score, 84)
        reasons.append("Teto aplicado: volume abaixo de 0.50x limita score a 84 ⚠️")

    return score, reasons

def classificar_predator(score):
    try:
        score = int(score)
    except Exception:
        return "FRACA 🔴"

    if score >= 95:
        return "EXCEPCIONAL 🔥"
    if score >= 90:
        return "MUITO FORTE 🟢"
    if score >= 85:
        return "IDEAL 🟢"
    if score >= 80:
        return "BOA 🟡"
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

                score, reasons = calcular_predator_score(True, True, True, True, adx_h4, volume_ok, risk_pct, float(candle_h1.get("volume_ratio", 0)), "LONG", h4_context)

                blocked_h4, h4_block_reason = should_block_predator_by_h4_context(
                    "LONG",
                    h4_context,
                    adx_h4,
                    score=score,
                    volume_ratio=float(candle_h1.get("volume_ratio", 0)),
                    risk_pct=risk_pct,
                )
                if h4_block_reason:
                    reasons.append(("❌ " if blocked_h4 else "⚠️ ") + h4_block_reason)

                if blocked_h4:
                    inc_funnel_stat("risk_rejected")
                    print(f"SMART PREDATOR LONG BLOQUEADO POR H4 FORTE CONTRA: {nome_limpo(symbol)} | score={score} | ADX_H4={adx_h4:.2f} | H4={h4_context}")
                    return None

                if score >= 70:
                    inc_funnel_stat("score_70_plus")
                if score >= 80:
                    inc_funnel_stat("score_80_plus")
                if score >= 85:
                    inc_funnel_stat("score_85_plus")
                if score >= 90:
                    inc_funnel_stat("score_90_plus")
                if score >= 95:
                    inc_funnel_stat("score_95_plus")

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

                score, reasons = calcular_predator_score(True, True, True, True, adx_h4, volume_ok, risk_pct, float(candle_h1.get("volume_ratio", 0)), "SHORT", h4_context)

                blocked_h4, h4_block_reason = should_block_predator_by_h4_context(
                    "SHORT",
                    h4_context,
                    adx_h4,
                    score=score,
                    volume_ratio=float(candle_h1.get("volume_ratio", 0)),
                    risk_pct=risk_pct,
                )
                if h4_block_reason:
                    reasons.append(("❌ " if blocked_h4 else "⚠️ ") + h4_block_reason)

                if blocked_h4:
                    inc_funnel_stat("risk_rejected")
                    print(f"SMART PREDATOR SHORT BLOQUEADO POR H4 FORTE CONTRA: {nome_limpo(symbol)} | score={score} | ADX_H4={adx_h4:.2f} | H4={h4_context}")
                    return None

                if score >= 70:
                    inc_funnel_stat("score_70_plus")
                if score >= 80:
                    inc_funnel_stat("score_80_plus")
                if score >= 85:
                    inc_funnel_stat("score_85_plus")
                if score >= 90:
                    inc_funnel_stat("score_90_plus")
                if score >= 95:
                    inc_funnel_stat("score_95_plus")

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
# EXECUÇÃO REAL SAFE MODE / CENTRAL RISK
# ====================================================

def execution_mode_active():
    return PREDATOR_MODE in {"READY", "VERIFY", "LIVE"}


def predator_mode_label():
    """Rótulo operacional padronizado, igual ao padrão Falcon/Central Quant."""
    enable_real = env_bool("ENABLE_REAL_TRADING", False)
    mode = str(PREDATOR_MODE or "PAPER").strip().upper()

    if mode == "LIVE" and enable_real:
        return "LIVE / BINGX ATIVA"
    if mode == "LIVE" and not enable_real:
        return "LIVE BLOQUEADO / ENABLE_REAL_TRADING=false"
    if mode == "VERIFY":
        return "VERIFY / VERIFY SEM ENVIO"
    if mode == "READY":
        return "READY / BINGX VALIDANDO"
    return "PAPER / SEM BINGX"


def broker_ready_payload():
    if bingx_broker is None:
        return {"ok": False, "status": "BROKER_IMPORT_ERROR", "error": BROKER_IMPORT_ERROR}
    try:
        return bingx_broker.ready_check(cache_seconds=10)
    except Exception as exc:
        return {"ok": False, "status": "BROKER_ERROR", "error": str(exc)}


def central_can_open_trade(sig):
    """
    Consulta a Central Quant antes de qualquer tentativa de VERIFY/LIVE.
    Em LIVE, falha de comunicação vira DENY por segurança.
    Em VERIFY, também reporta a falha, mas a posição PAPER já pode continuar registrada.
    """
    payload = {
        "bot": "PREDATOR",
        "symbol": nome_limpo(sig.get("symbol", "")),
        "raw_symbol": sig.get("symbol"),
        "side": sig.get("side"),
        "setup": "SMART_PREDATOR",
        "score": sig.get("score"),
        "risk_pct": sig.get("risk_pct"),
        "margin_usdt": PREDATOR_REAL_MARGIN_USDT,
        "leverage": PREDATOR_REAL_LEVERAGE,
        "notional_usdt": PREDATOR_REAL_NOTIONAL_USDT,
        "mode": PREDATOR_MODE,
        "source": "smart_predator",
    }

    if not PREDATOR_REQUIRE_CENTRAL_RISK:
        return {"allowed": True, "decision": "ALLOW", "reasons": ["PREDATOR_REQUIRE_CENTRAL_RISK=false"], "payload": payload}

    try:
        r = requests.post(f"{CENTRAL_BASE_URL}/can_open_trade", json=payload, timeout=8)
        try:
            data = r.json()
        except Exception:
            data = {"allowed": False, "decision": "DENY", "reasons": [r.text[:300]]}
        data["http_status"] = r.status_code
        data["payload"] = payload
        return data
    except Exception as exc:
        return {
            "allowed": False,
            "decision": "DENY",
            "reasons": [f"Falha ao consultar Central Risk Manager: {exc}"],
            "payload": payload,
        }


def _decision_value(decision_payload):
    """Normaliza decisão ALLOW/DENY vinda da Central."""
    try:
        return str(
            decision_payload.get("decision")
            or decision_payload.get("result")
            or ("ALLOW" if decision_payload.get("allowed") else "DENY")
        ).upper()
    except Exception:
        return "DENY"


def _risk_reasons_text(risk_payload, local_gate=None):
    reasons = []
    try:
        raw = risk_payload.get("reasons") or risk_payload.get("reason") or []
        if isinstance(raw, str):
            raw = [raw]
        reasons.extend([str(x) for x in raw])
    except Exception:
        pass

    try:
        local_reasons = (local_gate or {}).get("reasons") or []
        if isinstance(local_reasons, str):
            local_reasons = [local_reasons]
        reasons.extend([str(x) for x in local_reasons])
    except Exception:
        pass

    return reasons or ["Sem motivo informado"]


def predator_risk_precheck(sig):
    """
    Trava obrigatória da arquitetura Central Quant.

    Toda entrada do Smart Predator, mesmo PAPER/VERIFY, precisa consultar
    /can_open_trade ANTES de registrar posição, enviar Telegram ou executar.
    """
    HEALTH["execution_last_run"] = data_hora_sp_str()

    local_gate = predator_local_live_gate(sig)
    risk = central_can_open_trade(sig)
    allowed = bool(risk.get("allowed")) and bool(local_gate.get("allowed", True))

    decision = _decision_value(risk)
    if not allowed:
        decision = "DENY"

    HEALTH["execution_last_decision"] = decision
    HEALTH["execution_last_result"] = "PRECHECK_ALLOW" if allowed else "PRECHECK_DENY"
    HEALTH["execution_last_error"] = None if allowed else "; ".join(_risk_reasons_text(risk, local_gate)[:3])

    sig["risk_precheck_decision"] = decision
    sig["risk_precheck_allowed"] = bool(allowed)
    sig["risk_precheck_at"] = data_hora_sp_str()
    sig["risk_precheck_payload"] = risk
    sig["risk_precheck_local_gate"] = local_gate

    return allowed, risk, local_gate


def registrar_bloqueio_risk_predator(sig, risk, local_gate=None):
    """Registra bloqueio local para auditoria do robô sem abrir posição."""
    try:
        reasons = _risk_reasons_text(risk, local_gate)
        evento = {
            "event": "RISK_DENY",
            "date": data_hoje_sp_str(),
            "datetime": data_hora_sp_str(),
            "symbol": sig.get("symbol"),
            "symbol_clean": sig.get("symbol_clean", nome_limpo(sig.get("symbol", ""))),
            "side": sig.get("side"),
            "setup": "SMART_PREDATOR",
            "signal_type": "SMART_PREDATOR",
            "score": int(sig.get("score", 0) or 0),
            "risk_pct": float(sig.get("risk_pct", 0) or 0),
            "decision": "DENY",
            "allowed": False,
            "reasons": reasons,
            "central_decision": risk,
            "local_gate": local_gate or {},
        }
        registrar_evento_trade(evento)
        inc_funnel_stat("risk_rejected")
        print(
            "SMART PREDATOR BLOQUEADO PELA CENTRAL: "
            f"{evento['symbol_clean']} {evento.get('side')} | "
            + " | ".join(reasons[:3])
        )
    except Exception as exc:
        print("ERRO registrar_bloqueio_risk_predator:", exc)


def count_live_positions_predator():
    posicoes = carregar_posicoes()
    total = 0
    for p in posicoes.values():
        if p.get("status") == "ENCERRADO":
            continue
        if str(p.get("execution_mode", "")).upper() == "LIVE" or p.get("live_order_id") or p.get("bingx_order_id"):
            total += 1
    return total


def predator_local_live_gate(sig):
    reasons = []
    if PREDATOR_MODE == "LIVE" and count_live_positions_predator() >= PREDATOR_MAX_REAL_POSITIONS:
        reasons.append(f"Predator LIVE já no limite: {count_live_positions_predator()}/{PREDATOR_MAX_REAL_POSITIONS}")
    return {"allowed": len(reasons) == 0, "reasons": reasons}


def build_predator_execution_message(sig, risk, broker_result=None, ready=None, local_gate=None):
    broker_result = broker_result or {}
    ready = ready or {}
    local_gate = local_gate or {}
    symbol = nome_limpo(sig.get("symbol", ""))
    side = sig.get("side")
    mode = PREDATOR_MODE
    emoji = "🧪" if mode == "VERIFY" else ("🟢" if mode == "LIVE" else "⚙️")
    allowed = bool(risk.get("allowed")) and bool(local_gate.get("allowed", True))
    decision = "ALLOW" if allowed else "DENY"
    risk_reasons = risk.get("reasons") or risk.get("reason") or []
    if isinstance(risk_reasons, str):
        risk_reasons = [risk_reasons]
    local_reasons = local_gate.get("reasons") or []

    amount = broker_result.get("amount")
    price_ref = broker_result.get("price_ref")
    margin = broker_result.get("margin_usdt", PREDATOR_REAL_MARGIN_USDT)
    leverage = broker_result.get("leverage", PREDATOR_REAL_LEVERAGE)

    planned_exposure = broker_result.get("planned_exposure_usdt", PREDATOR_REAL_NOTIONAL_USDT)
    actual_exposure = broker_result.get(
        "actual_exposure_usdt",
        broker_result.get("effective_notional_usdt", broker_result.get("notional_usdt", planned_exposure))
    )

    def _num(value, default=None):
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _money(value, ndigits=2):
        val = _num(value)
        if val is None:
            return "N/A"
        return f"{val:.{ndigits}f}"

    def _fmt_any(value, ndigits=8):
        val = _num(value)
        if val is None:
            return "N/A"
        txt = f"{val:.{ndigits}f}".rstrip("0").rstrip(".")
        return txt if txt else "0"

    margin_display = broker_result.get("margin_usdt_display") or _money(margin, 2)
    planned_exposure_display = broker_result.get("planned_exposure_usdt_display") or _money(planned_exposure, 2)
    actual_exposure_display = (
        broker_result.get("actual_exposure_usdt_display")
        or broker_result.get("effective_notional_usdt_display")
        or _money(actual_exposure, 2)
    )

    free_balance = None
    balance_after = None
    try:
        bal = (ready.get("balance") or {}) if isinstance(ready, dict) else {}
        free_balance = broker_result.get("free_balance_usdt")
        if free_balance is None:
            free_balance = bal.get("free_usdt")
        balance_after = broker_result.get("estimated_margin_after_open_usdt")
        if balance_after is None and free_balance is not None:
            balance_after = float(free_balance) - float(margin)
    except Exception:
        pass

    risk_pct_val = _num(sig.get("risk_pct"))
    max_loss_usdt = broker_result.get("estimated_max_loss_usdt")
    if max_loss_usdt is None and risk_pct_val is not None and actual_exposure is not None:
        try:
            max_loss_usdt = float(actual_exposure) * (risk_pct_val / 100.0)
        except Exception:
            max_loss_usdt = None

    payload = broker_result.get("request_preview") or broker_result.get("payload_preview") or broker_result.get("payload") or {}
    precision = broker_result.get("precision") or {}
    latency = broker_result.get("latency_ms") or broker_result.get("elapsed_ms")
    order_id = broker_result.get("order_id") or broker_result.get("id")
    status = broker_result.get("status")
    sent = broker_result.get("sent")

    if not allowed:
        result_txt = "🚫 ORDEM BLOQUEADA PELO RISK MANAGER"
    elif mode == "VERIFY":
        result_txt = "🚫 VERIFY: ordem NÃO enviada."
    elif mode == "LIVE" and sent:
        result_txt = f"✅ LIVE: ordem enviada. Order ID: {order_id}"
    elif mode == "LIVE":
        result_txt = f"🔴 LIVE: ordem NÃO enviada. Status: {status}"
    else:
        result_txt = f"Modo {mode}: sem envio real."

    lines = [
        f"{emoji} SMART PREDATOR EXECUTION — {mode}",
        "",
        f"Ativo: {symbol}",
        f"Side: {side}",
        "Setup: SMART_PREDATOR H1",
        f"Score: {sig.get('score')}/100 | Qualidade: {sig.get('quality')}",
        f"Entrada: {fmt_br(sig.get('entry'))}",
        f"SL: {fmt_br(sig.get('sl'))}",
        f"TP50: {fmt_br(sig.get('tp50'))}",
        f"Risco sinal: {fmt_br(sig.get('risk_pct'), 2)}%",
        "",
        "Risk Manager Central:",
        f"{'✅' if allowed else '❌'} {decision}",
    ]
    for r in list(risk_reasons)[:5] + list(local_reasons)[:5]:
        lines.append(f"- {r}")

    lines += [
        "",
        "Broker BingX:",
        f"Ready: {'✅' if ready.get('ok') else '❌'} {ready.get('status')}",
    ]
    bal = ready.get("balance") or {}
    if bal:
        lines.append(f"Saldo USDT: total {bal.get('total_usdt')} | free {bal.get('free_usdt')}")

    lines += [
        "",
        "Ordem planejada:",
        f"Margem usada: {margin_display} USDT",
        f"Alavancagem: {leverage}x",
        f"Exposição planejada: {planned_exposure_display} USDT",
        f"Exposição efetiva: {actual_exposure_display} USDT",
        f"Preço ref: {_fmt_any(price_ref, 8)}",
        f"Quantidade: {_fmt_any(amount, 8)}",
        f"Valor da posição: {actual_exposure_display} USDT",
        f"Perda máxima estimada: {_money(max_loss_usdt, 4)} USDT",
        f"Saldo livre após abertura estimado: {_money(balance_after, 2)} USDT",
        f"Margin: {getattr(bingx_broker, 'BINGX_MARGIN_MODE', 'N/A') if bingx_broker else 'N/A'}",
        f"ReduceOnly: False",
        f"Client tag: PREDATOR-{symbol}-{int(time.time())}",
    ]

    if precision:
        lines += [
            "",
            "Precisão:",
            f"Amount original: {precision.get('amount_raw')}",
            f"Amount final: {precision.get('amount_final')}",
            f"Market: {precision.get('market_symbol')}",
            f"Amount precision: {precision.get('amount_precision')}",
            f"Price precision: {precision.get('price_precision')}",
        ]

    if payload:
        lines += [
            "",
            "Payload/Signature:",
            "✅ Payload OK",
            "✅ Signature OK" if payload.get("signature") or broker_result.get("signature_ok") else "⚪ Signature preview indisponível",
        ]

    if latency is not None:
        lines.append(f"Tempo: {latency} ms")

    if broker_result.get("error"):
        lines += ["", f"Erro Broker: {broker_result.get('error')}"]

    lines += ["", "Resultado:", result_txt]
    return "\n".join(lines)


def update_position_execution_fields(sig, risk, broker_result):
    try:
        posicoes = carregar_posicoes()
        symbol = sig.get("symbol")
        p = posicoes.get(symbol)
        if not isinstance(p, dict):
            return
        p["execution_mode"] = PREDATOR_MODE
        p["execution_decision"] = risk.get("decision", "ALLOW" if risk.get("allowed") else "DENY")
        p["execution_allowed"] = bool(risk.get("allowed"))
        p["execution_checked_at"] = data_hora_sp_str()
        p["execution_margin_usdt"] = PREDATOR_REAL_MARGIN_USDT
        p["execution_leverage"] = PREDATOR_REAL_LEVERAGE
        p["execution_notional_usdt"] = PREDATOR_REAL_NOTIONAL_USDT
        p["execution_status"] = broker_result.get("status") if isinstance(broker_result, dict) else None
        p["execution_sent"] = bool(broker_result.get("sent")) if isinstance(broker_result, dict) else False
        p["live_order_id"] = broker_result.get("order_id") or broker_result.get("id") if isinstance(broker_result, dict) else None
        p["bingx_order_id"] = p.get("live_order_id")
        p["broker_result_last"] = broker_result if isinstance(broker_result, dict) else {}
        posicoes[symbol] = p
        salvar_posicoes(posicoes)
    except Exception as exc:
        print("ERRO update_position_execution_fields:", exc)


def execute_predator_signal_safe(sig, risk_prechecked=None, local_gate_prechecked=None):
    """Executa a camada VERIFY/LIVE do Smart Predator no padrão Falcon.

    Quando o scanner já consultou o Risk Manager antes do registro, reutiliza
    essa decisão para evitar dupla consulta e manter auditoria consistente.
    """
    if not execution_mode_active():
        return None

    HEALTH["execution_last_run"] = data_hora_sp_str()
    local_gate = local_gate_prechecked if isinstance(local_gate_prechecked, dict) else predator_local_live_gate(sig)
    risk = risk_prechecked if isinstance(risk_prechecked, dict) else central_can_open_trade(sig)
    allowed = bool(risk.get("allowed")) and bool(local_gate.get("allowed", True))
    ready = broker_ready_payload()
    broker_result = {}

    if not allowed:
        broker_result = {"ok": False, "status": "DENIED", "sent": False, "error": "Risk Manager DENY"}
    elif bingx_broker is None:
        broker_result = {"ok": False, "status": "BROKER_IMPORT_ERROR", "sent": False, "error": BROKER_IMPORT_ERROR}
    elif PREDATOR_MODE == "READY":
        broker_result = {"ok": True, "status": "READY_ONLY", "sent": False, "margin_usdt": PREDATOR_REAL_MARGIN_USDT, "leverage": PREDATOR_REAL_LEVERAGE, "notional_usdt": PREDATOR_REAL_NOTIONAL_USDT, "effective_notional_usdt": PREDATOR_REAL_NOTIONAL_USDT}
    else:
        client_tag = f"PREDATOR-{nome_limpo(sig.get('symbol'))}-{int(time.time())}"
        try:
            broker_result = bingx_broker.place_market_order(
                sig.get("symbol"),
                sig.get("side"),
                PREDATOR_REAL_MARGIN_USDT,
                reduce_only=False,
                client_tag=client_tag,
                leverage=PREDATOR_REAL_LEVERAGE,
                bot="PREDATOR",
            )
        except Exception as exc:
            broker_result = {"ok": False, "status": "BROKER_EXCEPTION", "sent": False, "error": str(exc)}

    HEALTH["execution_last_decision"] = risk.get("decision", "ALLOW" if risk.get("allowed") else "DENY")
    HEALTH["execution_last_result"] = broker_result.get("status")
    HEALTH["execution_last_error"] = broker_result.get("error")

    update_position_execution_fields(sig, risk, broker_result)

    msg = build_predator_execution_message(sig, risk, broker_result, ready, local_gate)
    if PREDATOR_EXECUTION_NOTIFY:
        safe_send_telegram(msg)
    return {"risk": risk, "ready": ready, "broker_result": broker_result, "message": msg}


def montar_execution_status_texto():
    ready = broker_ready_payload()
    bal = ready.get("balance") or {}
    return (
        "⚙️ EXECUÇÃO SMART PREDATOR\n\n"
        f"Modo Predator: {PREDATOR_MODE}\n"
        f"Central URL: {CENTRAL_BASE_URL}\n"
        f"Margem real: {PREDATOR_REAL_MARGIN_USDT} USDT\n"
        f"Alavancagem real: {PREDATOR_REAL_LEVERAGE}x\n"
        f"Exposição efetiva: {PREDATOR_REAL_NOTIONAL_USDT} USDT\n"
        f"Max posições LIVE Predator: {PREDATOR_MAX_REAL_POSITIONS}\n"
        f"Central Risk obrigatório: {PREDATOR_REQUIRE_CENTRAL_RISK}\n"
        f"Bloquear H4 forte contra: {PREDATOR_BLOCK_STRONG_H4_CONTRA}\n"
        f"ADX H4 forte contra: {PREDATOR_STRONG_H4_ADX}\n"
        f"Exceção H4 contra ativa: {PREDATOR_ALLOW_EXCEPTIONAL_COUNTER_H4}\n\n"
        f"Broker carregado: {bingx_broker is not None}\n"
        f"Broker import error: {BROKER_IMPORT_ERROR}\n"
        f"BingX READY: {ready.get('ok')} | {ready.get('status')}\n"
        f"Saldo USDT total/free: {bal.get('total_usdt')} / {bal.get('free_usdt')}\n\n"
        f"Última decisão: {HEALTH.get('execution_last_decision')}\n"
        f"Último resultado: {HEALTH.get('execution_last_result')}\n"
        f"Último erro: {HEALTH.get('execution_last_error')}"
    )

# ====================================================
# MENSAGENS TELEGRAM
# ====================================================

def formatar_sinal_predator(s):
    side = s["side"]
    emoji = "🟢" if side == "LONG" else "🔴"
    modo = predator_mode_label()
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
        "mae_min_pct": 0.0,
        "mae_updated_at": None,
        "management_cycles": 0,
        "cycles_to_tp50": None,
        "closed_at": None,
        "close_reason": None,
        "auto_trade": SMART_PREDATOR_AUTO_TRADE,
        "execution_mode": PREDATOR_MODE,
        "execution_decision": sig.get("risk_precheck_decision"),
        "execution_allowed": sig.get("risk_precheck_allowed"),
        "execution_checked_at": sig.get("risk_precheck_at"),
        "execution_margin_usdt": PREDATOR_REAL_MARGIN_USDT if execution_mode_active() else None,
        "execution_leverage": PREDATOR_REAL_LEVERAGE if execution_mode_active() else None,
        "execution_notional_usdt": PREDATOR_REAL_NOTIONAL_USDT if execution_mode_active() else None,
        "execution_status": None,
        "execution_sent": False,
        "live_order_id": None,
        "bingx_order_id": None,
        "broker_result_last": {},
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
        "risk_abs": float(s.get("risk_abs", 0)),
        "risk_pct": float(s.get("risk_pct", 0)),
        "score": int(s.get("score", 0)),
        "quality": s.get("quality", ""),
        "signal_type": "SMART_PREDATOR",
        "auto_trade": SMART_PREDATOR_AUTO_TRADE,
        "execution_mode": PREDATOR_MODE,
        "execution_margin_usdt": PREDATOR_REAL_MARGIN_USDT if execution_mode_active() else None,
        "execution_leverage": PREDATOR_REAL_LEVERAGE if execution_mode_active() else None,
        "execution_notional_usdt": PREDATOR_REAL_NOTIONAL_USDT if execution_mode_active() else None,
        "execution_decision": s.get("risk_precheck_decision"),
        "execution_allowed": s.get("risk_precheck_allowed"),
        "execution_checked_at": s.get("risk_precheck_at"),
        "central_risk_precheck": s.get("risk_precheck_payload"),
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
    mae = float(p.get("mae_min_pct", 0))
    giveback = max(0.0, mfe - resultado)
    risk_pct = abs(float(p.get("risk_pct", 0)) or 0.0)
    pnl_r = pct_to_r(resultado, risk_pct)
    mfe_r = pct_to_r(mfe, risk_pct)
    mae_r = pct_to_r(mae, risk_pct)
    giveback_r = pct_to_r(giveback, risk_pct)

    p["status"] = "ENCERRADO"
    p["closed_at"] = time.time()
    p["closed_at_txt"] = data_hora_sp_str()
    p["close_reason"] = motivo
    p["exit_price"] = float(preco_saida)
    p["pnl_pct"] = float(resultado)
    p["mae_min_pct"] = float(mae)
    p["mfe_gave_back_pct"] = float(giveback)
    p["pnl_r"] = float(pnl_r)
    p["mfe_max_r"] = float(mfe_r)
    p["mae_min_r"] = float(mae_r)
    p["mfe_gave_back_r"] = float(giveback_r)

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
        "risk_abs": float(p.get("risk_abs", 0)),
        "risk_pct": float(risk_pct),
        "pnl_r": float(pnl_r),
        "mfe_max_pct": float(mfe),
        "mfe_max_r": float(mfe_r),
        "mae_min_pct": float(mae),
        "mae_min_r": float(mae_r),
        "mfe_gave_back_pct": float(giveback),
        "mfe_gave_back_r": float(giveback_r),
        "management_cycles": int(p.get("management_cycles", 0) or 0),
        "cycles_to_tp50": p.get("cycles_to_tp50"),
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

            p["management_cycles"] = int(p.get("management_cycles", 0) or 0) + 1
            alterou = True

            if atualizar_mfe_posicao(p, preco):
                alterou = True

            if atualizar_mae_posicao(p, preco):
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
                    p["cycles_to_tp50"] = int(p.get("management_cycles", 0) or 0)
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
                        "cycles_to_tp50": int(p.get("cycles_to_tp50", 0) or 0),
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




# ==============================================================================
# MÉTRICAS EXECUTIVAS V2.0 — linguagem simples para relatório principal
# ==============================================================================

def _safe_float_metric(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _fmt_pct_metric(value, casas=2):
    try:
        return f"{float(value):+.{casas}f}%".replace(".", ",")
    except Exception:
        return "+0,00%"


def _fmt_num_metric(value, casas=2):
    try:
        return f"{float(value):.{casas}f}".replace(".", ",")
    except Exception:
        return "0,00"


def classificar_profit_factor(pf):
    pf = _safe_float_metric(pf)
    if pf < 1.0:
        return "🔴 Estratégia perdedora"
    if pf < 1.3:
        return "🟡 Lucro baixo"
    if pf < 1.8:
        return "🟢 Boa estratégia"
    return "⭐ Excelente estratégia"


def classificar_gerenciamento(valor):
    valor = _safe_float_metric(valor)
    if valor < 1.0:
        return "🔴 Ruim"
    if valor < 1.5:
        return "🟡 Aceitável"
    if valor < 2.0:
        return "🟢 Bom"
    return "⭐ Excelente"


def classificar_lucro_pct(valor):
    valor = _safe_float_metric(valor)
    if valor < 0:
        return "🔴 Negativo"
    if valor < 0.25:
        return "🟡 Baixo"
    if valor < 0.75:
        return "🟢 Muito bom"
    return "⭐ Excelente"


def classificar_captura_movimento(valor):
    valor = _safe_float_metric(valor)
    if valor < 30:
        return "🔴 Baixa"
    if valor < 45:
        return "🟡 Regular"
    if valor < 60:
        return "🟢 Muito boa"
    return "⭐ Excelente"


def classificar_devolucao(valor):
    valor = abs(_safe_float_metric(valor))
    if valor < 1:
        return "⭐ Excelente"
    if valor < 2:
        return "🟢 Muito bom"
    if valor < 3:
        return "🟡 Bom"
    return "🔴 Alta"


def ciclos_para_dias_horas(ciclos, minutos_por_ciclo=5):
    """
    Converte ciclos de gestão em tempo humano.
    Ajustável no Render via PREDATOR_MANAGEMENT_CYCLE_MINUTES.
    """
    try:
        import os
        minutos_por_ciclo = float(os.environ.get("PREDATOR_MANAGEMENT_CYCLE_MINUTES", minutos_por_ciclo))
        total_min = int(round(float(ciclos) * minutos_por_ciclo))
    except Exception:
        return "N/A"

    dias = total_min // 1440
    horas = (total_min % 1440) // 60
    minutos = total_min % 60

    partes = []
    if dias:
        partes.append(f"{dias}d")
    if horas:
        partes.append(f"{horas}h")
    if minutos and not dias:
        partes.append(f"{minutos}min")
    return " ".join(partes) if partes else "0min"


def metricas_executivas_predator_v2(
    profit_factor=None,
    eficiencia_gerenciamento=None,
    lucro_esperado_pct=None,
    lucro_medio_pos_tp50_pct=None,
    captura_movimento_pct=None,
    maior_lucro_pct=None,
    maior_perda_pct=None,
    lucro_devolvido_pct=None,
    tempo_tp50_ciclos=None,
    tempo_fechamento_ciclos=None,
    r3=None,
    r5=None,
    r10=None,
):
    """
    Bloco executivo V2.0:
    - relatório principal em %, linguagem simples e classificação automática;
    - R fica como auditoria/contagem de grandes vencedores.
    """
    pf = _safe_float_metric(profit_factor)
    eg = _safe_float_metric(eficiencia_gerenciamento)
    le = _safe_float_metric(lucro_esperado_pct)
    ptp = _safe_float_metric(lucro_medio_pos_tp50_pct)
    cap = _safe_float_metric(captura_movimento_pct)
    mfe = _safe_float_metric(maior_lucro_pct)
    mae = _safe_float_metric(maior_perda_pct)
    dev = _safe_float_metric(lucro_devolvido_pct)

    linhas = [
        "",
        "📈 QUALIDADE DA ESTRATÉGIA",
        "",
        "Profit Factor:",
        f"{_fmt_num_metric(pf)} {classificar_profit_factor(pf)}",
        "",
        "Referência:",
        "< 1,00 → perde dinheiro",
        "1,00–1,30 → lucro baixo",
        "1,30–1,80 → boa estratégia",
        "> 1,80 → excelente estratégia",
        "",
        "Eficiência do gerenciamento:",
        f"{_fmt_num_metric(eg)} {classificar_gerenciamento(eg)}",
        "Cada trade vencedor capturou, em média,",
        f"{_fmt_num_metric(eg)} vezes o risco inicial.",
        "",
        "Lucro esperado por trade:",
        f"{_fmt_pct_metric(le)} {classificar_lucro_pct(le)}",
        "",
        "Lucro médio após TP50:",
        f"{_fmt_pct_metric(ptp)} {classificar_lucro_pct(ptp)}",
        "",
        "Captura do movimento:",
        f"{_fmt_num_metric(cap)}% {classificar_captura_movimento(cap)}",
        "",
        "Maior lucro durante o trade:",
        _fmt_pct_metric(mfe),
        "",
        "Maior perda durante o trade:",
        _fmt_pct_metric(mae),
        "",
        "Lucro devolvido antes do fechamento:",
        f"{_fmt_pct_metric(dev).replace('+', '')} {classificar_devolucao(dev)}",
    ]

    if tempo_tp50_ciclos is not None or tempo_fechamento_ciclos is not None:
        linhas += ["", "⏱ TEMPO MÉDIO DOS TRADES"]
        if tempo_tp50_ciclos is not None:
            linhas.append(f"Até TP50: {ciclos_para_dias_horas(tempo_tp50_ciclos)}")
        if tempo_fechamento_ciclos is not None:
            linhas.append(f"Até fechamento: {ciclos_para_dias_horas(tempo_fechamento_ciclos)}")

    linhas += [
        "",
        "Grandes vencedores:",
        f"Acima de 3R: {int(_safe_float_metric(r3))}",
        f"Acima de 5R: {int(_safe_float_metric(r5))}",
        f"Acima de 10R: {int(_safe_float_metric(r10))}",
    ]
    return "\\n".join(linhas)


def montar_resumo_por_periodo(data_prefix, titulo, data_txt):
    trades = filtrar_trades_periodo(data_prefix)
    stats = calc_predator_stats(trades)
    entradas = stats["entries"]
    exits = stats["exits"]

    longs = [t for t in entradas if t.get("side") == "LONG"]
    shorts = [t for t in entradas if t.get("side") == "SHORT"]

    excepcionais = [t for t in entradas if safe_int(t.get("score", 0), 0) >= 95]
    muito_fortes = [t for t in entradas if 90 <= safe_int(t.get("score", 0), 0) <= 94]
    ideais = [t for t in entradas if 85 <= safe_int(t.get("score", 0), 0) <= 89]
    bons = [t for t in entradas if 80 <= safe_int(t.get("score", 0), 0) <= 84]
    medios = [t for t in entradas if 70 <= safe_int(t.get("score", 0), 0) <= 79]

    posicoes = carregar_posicoes()
    ativos = [p for p in posicoes.values() if p.get("status") != "ENCERRADO"]
    modo = predator_mode_label()

    return (
        f"{titulo}\n"
        f"{data_txt}\n\n"
        f"Modo:\n{modo}\n\n"
        f"Smart Predator ativo:\n{check_bool(SMART_PREDATOR_ENABLED)}\n\n"
        f"Sinais H1 do período: {len(entradas)}\n"
        f"LONG: {len(longs)}\n"
        f"SHORT: {len(shorts)}\n\n"
        f"EXCEPCIONAL 95+: {len(excepcionais)}\n"
        f"MUITO FORTE 90-94: {len(muito_fortes)}\n"
        f"IDEAL 85-89: {len(ideais)}\n"
        f"BOA 80-84: {len(bons)}\n"
        f"MÉDIA 70-79: {len(medios)}\n\n"
        f"Trades encerrados: {stats['count']}\n"
        f"Wins: {stats['wins']}\n"
        f"Breakeven: {stats['be']}\n"
        f"Loss: {stats['losses']}\n"
        f"Win rate: {stats['winrate']:.2f}%\n"
        f"Win rate sem BE: {stats['winrate_sem_be']:.2f}%\n"
        f"Profit Factor: {fmt_pf(stats['profit_factor_pct'])}\n"
        f"Eficiência do gerenciamento: {fmt_pf(stats['profit_factor_r'])}\n"
        f"Lucro esperado por trade: {fmt_r(stats['expectancy_r'])} por trade\n"
        f"Lucro médio após TP50: {fmt_r(stats['expectancy_after_tp50_r'])}\n"
        f"Captura do movimento: {stats['trend_capture_pct']:.2f}%\n\n"
        f"TP50 atingidos: {stats['tp50_hits']}\n"
        f"Tempo médio até TP50: {stats['avg_cycles_to_tp50']:.1f} ciclos de gestão\n"
        f"Tempo médio até fechamento: {stats['avg_management_cycles']:.1f} ciclos de gestão\n"
        f"Trailings atualizados: {len(stats['trails'])}\n\n"
        f"Resultado financeiro:\n{fmt_pct(stats['pnl_pct'])} | {fmt_r(stats['pnl_r'])}\n\n"
        f"Maior lucro durante o trade:\n{fmt_pct(stats['mfe_avg_pct'])} | {fmt_r(stats['mfe_avg_r'])}\n"
        f"Maior perda durante o trade:\n{fmt_pct(stats['mae_avg_pct'])} | {fmt_r(stats['mae_avg_r'])}\n"
        f"Lucro devolvido antes do fechamento:\n{fmt_pct(stats['giveback_avg_pct'])} | {fmt_r(stats['giveback_avg_r'])}\n\n"
        f"Grandes vencedores:\n3R+: {stats['runners_3r']}\n5R+: {stats['runners_5r']}\n10R+: {stats['runners_10r']}\n\n"
        f"LONG x SHORT:\n{stats_by_side_text(exits)}\n\n"
        f"Melhor trade:\n{trade_line_predator(stats['best_trade'])}\n\n"
        f"Pior trade:\n{trade_line_predator(stats['worst_trade'])}\n\n"
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


def trade_line_predator(t):
    if not t:
        return "N/A"
    return (
        f"{t.get('symbol_clean', t.get('symbol', 'N/A'))} "
        f"{t.get('side', '')} "
        f"{fmt_pct(t.get('pnl', t.get('pnl_pct', 0)))} | "
        f"{fmt_r(t.get('pnl_r', 0))} | "
        f"Score {t.get('score', 0)}"
    )


def calc_predator_stats(trades):
    entries = [t for t in trades if t.get("event") == "ENTRY"]
    exits = [t for t in trades if t.get("event") in ["SL", "TRAIL", "BE", "CLOSE"]]
    tp50s = [t for t in trades if t.get("event") == "TP50"]
    trails = [t for t in trades if t.get("event") == "TRAILING"]

    wins = []
    bes = []
    losses = []

    gross_win_pct = 0.0
    gross_loss_pct = 0.0
    gross_win_r = 0.0
    gross_loss_r = 0.0

    pnl_pct_total = 0.0
    pnl_r_total = 0.0
    mfe_pct_total = 0.0
    mfe_r_total = 0.0
    mae_pct_total = 0.0
    mae_r_total = 0.0
    giveback_pct_total = 0.0
    giveback_r_total = 0.0

    cycles_to_tp50 = []
    management_cycles = []

    best_trade = None
    worst_trade = None

    for t in exits:
        pnl_pct_v = safe_float(t.get("pnl", t.get("pnl_pct", 0)), 0.0)
        risk_pct_v = abs(safe_float(t.get("risk_pct", 0), 0.0))
        pnl_r_v = safe_float(t.get("pnl_r"), pct_to_r(pnl_pct_v, risk_pct_v))
        mfe_pct_v = safe_float(t.get("mfe_max_pct", 0), 0.0)
        mae_pct_v = safe_float(t.get("mae_min_pct", 0), 0.0)
        giveback_pct_v = safe_float(t.get("mfe_gave_back_pct", 0), 0.0)
        mfe_r_v = safe_float(t.get("mfe_max_r"), pct_to_r(mfe_pct_v, risk_pct_v))
        mae_r_v = safe_float(t.get("mae_min_r"), pct_to_r(mae_pct_v, risk_pct_v))
        giveback_r_v = safe_float(t.get("mfe_gave_back_r"), pct_to_r(giveback_pct_v, risk_pct_v))

        pnl_pct_total += pnl_pct_v
        pnl_r_total += pnl_r_v
        mfe_pct_total += mfe_pct_v
        mfe_r_total += mfe_r_v
        mae_pct_total += mae_pct_v
        mae_r_total += mae_r_v
        giveback_pct_total += giveback_pct_v
        giveback_r_total += giveback_r_v

        if pnl_pct_v > 0.15:
            wins.append(t)
            gross_win_pct += pnl_pct_v
            gross_win_r += pnl_r_v
        elif pnl_pct_v >= -0.15:
            bes.append(t)
        else:
            losses.append(t)
            gross_loss_pct += abs(pnl_pct_v)
            gross_loss_r += abs(pnl_r_v)

        if t.get("cycles_to_tp50") is not None:
            cycles_to_tp50.append(safe_float(t.get("cycles_to_tp50"), 0.0))
        if t.get("management_cycles") is not None:
            management_cycles.append(safe_float(t.get("management_cycles"), 0.0))

        if best_trade is None or pnl_pct_v > safe_float(best_trade.get("_pnl_calc", -999999)):
            t["_pnl_calc"] = pnl_pct_v
            best_trade = t
        if worst_trade is None or pnl_pct_v < safe_float(worst_trade.get("_pnl_calc", 999999)):
            t["_pnl_calc"] = pnl_pct_v
            worst_trade = t

    count = len(exits)
    non_be_count = len(wins) + len(losses)
    profit_factor_pct = gross_win_pct / gross_loss_pct if gross_loss_pct > 0 else (float("inf") if gross_win_pct > 0 else 0.0)
    profit_factor_r = gross_win_r / gross_loss_r if gross_loss_r > 0 else (float("inf") if gross_win_r > 0 else 0.0)
    expectancy_r = pnl_r_total / count if count else 0.0
    expectancy_pct = pnl_pct_total / count if count else 0.0

    tp50_exits = [t for t in exits if bool(t.get("tp50_hit", False))]
    expectancy_after_tp50_r = (
        sum(safe_float(t.get("pnl_r"), pct_to_r(t.get("pnl", t.get("pnl_pct", 0)), t.get("risk_pct", 0))) for t in tp50_exits) / len(tp50_exits)
        if tp50_exits else 0.0
    )

    trend_capture_pct = (
        (sum(max(0.0, safe_float(t.get("pnl", t.get("pnl_pct", 0)), 0.0)) for t in exits) /
         sum(max(0.0, safe_float(t.get("mfe_max_pct", 0), 0.0)) for t in exits) * 100)
        if exits and sum(max(0.0, safe_float(t.get("mfe_max_pct", 0), 0.0)) for t in exits) > 0 else 0.0
    )

    return {
        "entries": entries,
        "exits": exits,
        "tp50s": tp50s,
        "trails": trails,
        "count": count,
        "wins": len(wins),
        "be": len(bes),
        "losses": len(losses),
        "winrate": (len(wins) / count * 100) if count else 0.0,
        "winrate_sem_be": (len(wins) / non_be_count * 100) if non_be_count else 0.0,
        "profit_factor_pct": profit_factor_pct,
        "profit_factor_r": profit_factor_r,
        "expectancy_r": expectancy_r,
        "expectancy_pct": expectancy_pct,
        "expectancy_after_tp50_r": expectancy_after_tp50_r,
        "pnl_pct": pnl_pct_total,
        "pnl_r": pnl_r_total,
        "mfe_avg_pct": mfe_pct_total / count if count else 0.0,
        "mfe_avg_r": mfe_r_total / count if count else 0.0,
        "mae_avg_pct": mae_pct_total / count if count else 0.0,
        "mae_avg_r": mae_r_total / count if count else 0.0,
        "giveback_avg_pct": giveback_pct_total / count if count else 0.0,
        "giveback_avg_r": giveback_r_total / count if count else 0.0,
        "tp50_hits": len(tp50s),
        "avg_cycles_to_tp50": sum(cycles_to_tp50) / len(cycles_to_tp50) if cycles_to_tp50 else 0.0,
        "avg_management_cycles": sum(management_cycles) / len(management_cycles) if management_cycles else 0.0,
        "trend_capture_pct": trend_capture_pct,
        "runners_3r": sum(1 for t in exits if safe_float(t.get("mfe_max_r"), pct_to_r(t.get("mfe_max_pct", 0), t.get("risk_pct", 0))) >= 3),
        "runners_5r": sum(1 for t in exits if safe_float(t.get("mfe_max_r"), pct_to_r(t.get("mfe_max_pct", 0), t.get("risk_pct", 0))) >= 5),
        "runners_10r": sum(1 for t in exits if safe_float(t.get("mfe_max_r"), pct_to_r(t.get("mfe_max_pct", 0), t.get("risk_pct", 0))) >= 10),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
    }


def stats_by_side_text(exits):
    lines = []
    for side in ["LONG", "SHORT"]:
        rows = [t for t in exits if t.get("side") == side]
        st = calc_predator_stats(rows)
        lines.append(
            f"{side}: {st['count']} trades | WR {st['winrate']:.2f}% | "
            f"PF {fmt_pf(st['profit_factor_pct'])} | Exp {fmt_r(st['expectancy_r'])}"
        )
    return "\n".join(lines)


def stats_by_score_text(exits):
    buckets = {
        "70-79": [],
        "80-84": [],
        "85-89": [],
        "90-94": [],
        "95+": [],
    }
    for t in exits:
        score = safe_int(t.get("score", 0), 0)
        if 70 <= score <= 79:
            buckets["70-79"].append(t)
        elif 80 <= score <= 84:
            buckets["80-84"].append(t)
        elif 85 <= score <= 89:
            buckets["85-89"].append(t)
        elif 90 <= score <= 94:
            buckets["90-94"].append(t)
        elif score >= 95:
            buckets["95+"].append(t)

    lines = []
    for name, rows in buckets.items():
        st = calc_predator_stats(rows)
        lines.append(
            f"{name}: {st['count']} trades | WR {st['winrate']:.2f}% | "
            f"PF {fmt_pf(st['profit_factor_pct'])} | Exp {fmt_r(st['expectancy_r'])}"
        )
    return "\n".join(lines)


def asset_ranking_text(exits, limit=8):
    grouped = {}
    for t in exits:
        sym = t.get("symbol_clean") or nome_limpo(t.get("symbol", ""))
        grouped.setdefault(sym, []).append(t)

    rows = []
    for sym, items in grouped.items():
        st = calc_predator_stats(items)
        rows.append((st["pnl_pct"], sym, st))

    if not rows:
        return "N/A"

    rows.sort(key=lambda x: x[0], reverse=True)
    top = rows[:limit]
    bottom = list(reversed(rows[-limit:])) if len(rows) > limit else []

    top_lines = [
        f"{sym}: {fmt_pct(st['pnl_pct'])} | {st['count']} trades | WR {st['winrate']:.2f}% | PF {fmt_pf(st['profit_factor_pct'])}"
        for _, sym, st in top
    ]
    bottom_lines = [
        f"{sym}: {fmt_pct(st['pnl_pct'])} | {st['count']} trades | WR {st['winrate']:.2f}% | PF {fmt_pf(st['profit_factor_pct'])}"
        for _, sym, st in bottom
    ]

    if bottom_lines:
        return "Melhores:\n" + "\n".join(top_lines) + "\n\nPiores:\n" + "\n".join(bottom_lines)
    return "Melhores:\n" + "\n".join(top_lines)


def montar_stats_gerais():
    trades = carregar_trades()
    stats = calc_predator_stats(trades)
    exits = stats["exits"]

    return (
        f"📈 ESTATÍSTICAS SMART PREDATOR V4\n\n"
        f"Smart Predator ativo: {check_bool(SMART_PREDATOR_ENABLED)}\n"
        f"Modo: {predator_mode_label()}\n\n"
        f"Sinais totais: {len(stats['entries'])}\n"
        f"Trades encerrados: {stats['count']}\n"
        f"Wins: {stats['wins']}\n"
        f"Breakeven: {stats['be']}\n"
        f"Loss: {stats['losses']}\n"
        f"Win rate: {stats['winrate']:.2f}%\n"
        f"Win rate sem BE: {stats['winrate_sem_be']:.2f}%\n"
        f"Profit Factor: {fmt_pf(stats['profit_factor_pct'])}\n"
        f"Eficiência do gerenciamento: {fmt_pf(stats['profit_factor_r'])}\n"
        f"Lucro esperado por trade: {fmt_r(stats['expectancy_r'])} por trade\n"
        f"Lucro médio após TP50: {fmt_r(stats['expectancy_after_tp50_r'])}\n"
        f"Captura do movimento: {stats['trend_capture_pct']:.2f}%\n\n"
        f"TP50 atingidos: {stats['tp50_hits']}\n"
        f"Tempo médio até TP50: {stats['avg_cycles_to_tp50']:.1f} ciclos de gestão\n"
        f"Tempo médio até fechamento: {stats['avg_management_cycles']:.1f} ciclos de gestão\n\n"
        f"Resultado financeiro:\n{fmt_pct(stats['pnl_pct'])} | {fmt_r(stats['pnl_r'])}\n\n"
        f"Maior lucro durante o trade:\n{fmt_pct(stats['mfe_avg_pct'])} | {fmt_r(stats['mfe_avg_r'])}\n"
        f"Maior perda durante o trade:\n{fmt_pct(stats['mae_avg_pct'])} | {fmt_r(stats['mae_avg_r'])}\n"
        f"Lucro devolvido antes do fechamento:\n{fmt_pct(stats['giveback_avg_pct'])} | {fmt_r(stats['giveback_avg_r'])}\n\n"
        f"Grandes vencedores:\n3R+: {stats['runners_3r']}\n5R+: {stats['runners_5r']}\n10R+: {stats['runners_10r']}\n\n"
        f"LONG x SHORT:\n{stats_by_side_text(exits)}\n\n"
        f"Por score:\n{stats_by_score_text(exits)}\n\n"
        f"Ranking por ativo:\n{asset_ranking_text(exits, 8)}\n\n"
        f"Melhor trade:\n{trade_line_predator(stats['best_trade'])}\n\n"
        f"Pior trade:\n{trade_line_predator(stats['worst_trade'])}"
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
                f"MFE: {fmt_pct(p.get('mfe_max_pct', 0))}\n"
                f"MAE: {fmt_pct(p.get('mae_min_pct', 0))}\n"
                f"Ciclos em trade: {p.get('management_cycles', 0)}\n"
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
        f"Score >= 85: {s.get('score_85_plus', 0)}\n"
        f"Score >= 90: {s.get('score_90_plus', 0)}\n"
        f"Score >= 95: {s.get('score_95_plus', 0)}\n\n"
        f"Sinais detectados: {s.get('signals_detected', 0)}\n"
        f"Sinais enviados: {s.get('signals_sent', 0)}\n"
        f"LONG: {s.get('long_signals', 0)}\n"
        f"SHORT: {s.get('short_signals', 0)}\n\n"
        f"Última atualização: {s.get('last_update')}"
    )



# Aliases usados pela Central Quant para puxar FUNIL do robô.
# Mantém compatibilidade com o padrão Falcon/Turtle e evita aparecer N/A no /predator da Central.
def funnel_text():
    return montar_funnel_stats_texto()


def funil_texto():
    return montar_funnel_stats_texto()


def build_funnel_text():
    return montar_funnel_stats_texto()


def montar_funil_texto():
    return montar_funnel_stats_texto()


def montar_funil():
    return montar_funnel_stats_texto()


def montar_eventos_texto(limit=20):
    trades = carregar_trades()
    if not isinstance(trades, list) or not trades:
        return "📋 EVENTOS SMART PREDATOR\n\nNenhum evento registrado ainda."

    recentes = trades[-int(limit):]
    linhas = ["📋 EVENTOS SMART PREDATOR", ""]

    for t in reversed(recentes):
        try:
            event = t.get("event", "N/A")
            dt = t.get("datetime") or t.get("created_at_txt") or t.get("date", "")
            symbol = t.get("symbol_clean") or nome_limpo(t.get("symbol", ""))
            side = t.get("side", "")
            setup = t.get("signal_type", "SMART_PREDATOR")

            detalhe = ""
            if event == "ENTRY":
                detalhe = (
                    f"Entrada {fmt_br(t.get('entry'))} | SL {fmt_br(t.get('sl'))} | "
                    f"TP50 {fmt_br(t.get('tp50'))} | Score {t.get('score', 0)}"
                )
            elif event == "TP50":
                detalhe = f"Preço {fmt_br(t.get('price'))} | TP50 {fmt_br(t.get('tp50'))}"
            elif event == "TRAILING":
                detalhe = f"SL {fmt_br(t.get('old_sl'))} → {fmt_br(t.get('new_sl'))}"
            elif event in {"SL", "BE", "TRAIL", "CLOSE"}:
                detalhe = f"Resultado {fmt_pct(t.get('pnl_pct', t.get('pnl', 0)))} | {fmt_r(t.get('pnl_r', 0))}"
            else:
                detalhe = f"MFE {fmt_pct(t.get('mfe_max_pct', 0))} | {fmt_r(t.get('mfe_max_r', 0))}"

            linhas.append(f"{dt} | {event} | {symbol} {side} {setup}\n{detalhe}")
            linhas.append("")
        except Exception as exc:
            linhas.append(f"Evento inválido: {exc}")

    return "\n".join(linhas).strip()


def events_text():
    return montar_eventos_texto()


def eventos_texto():
    return montar_eventos_texto()


def build_events_text():
    return montar_eventos_texto()

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
        "predator_mode": PREDATOR_MODE,
        "execution_enabled": execution_mode_active(),
        "execution_margin_usdt": PREDATOR_REAL_MARGIN_USDT,
        "execution_leverage": PREDATOR_REAL_LEVERAGE,
        "execution_notional_usdt": PREDATOR_REAL_NOTIONAL_USDT,
        "execution_last_decision": HEALTH.get("execution_last_decision"),
        "execution_last_result": HEALTH.get("execution_last_result"),
        "execution_last_error": HEALTH.get("execution_last_error"),
        "execution_last_run": HEALTH.get("execution_last_run"),
        "broker_loaded": bingx_broker is not None,
        "broker_import_error": BROKER_IMPORT_ERROR,
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
        "startup_signal_grace_seconds": STARTUP_SIGNAL_GRACE_SECONDS,
        "startup_signal_guard_active": False,
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
    modo = predator_mode_label()
    return (
        f"🦈 Robô {BOT_NAME} iniciado\n\n"
        f"Status:\n"
        f"Stand-by: {check_bool(not SMART_PREDATOR_ENABLED)}\n"
        f"Ativo para sinais: {check_bool(SMART_PREDATOR_ENABLED)}\n"
        f"Modo: {modo}\n"
        f"Execução segura: {PREDATOR_MODE}\n"
        f"Margem VERIFY/LIVE: {PREDATOR_REAL_MARGIN_USDT} USDT\n"
        f"Alavancagem: {PREDATOR_REAL_LEVERAGE}x\n"
        f"Exposição efetiva: {PREDATOR_REAL_NOTIONAL_USDT} USDT\n\n"
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
            "/eventos - últimos eventos\n"
            "/ranking - ranking por ativo\n"
            "/execution - status execução VERIFY/LIVE\n"
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

    if cmd in ["/eventos", "/events"]:
        return montar_eventos_texto()

    if cmd in ["/ranking", "/ativos"]:
        return "🏆 RANKING SMART PREDATOR POR ATIVO\n\n" + asset_ranking_text(calc_predator_stats(carregar_trades())["exits"], 12)

    if cmd in ["/execution", "/exec", "/verify", "/live"]:
        return montar_execution_status_texto()

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
                            risk_allowed, risk_payload, local_gate = predator_risk_precheck(s)

                            if not risk_allowed:
                                registrar_bloqueio_risk_predator(s, risk_payload, local_gate)
                                continue

                            ok = registrar_posicao(s)
                            if ok:
                                safe_send_telegram(formatar_sinal_predator(s))
                                if execution_mode_active():
                                    execute_predator_signal_safe(
                                        s,
                                        risk_prechecked=risk_payload,
                                        local_gate_prechecked=local_gate,
                                    )
                                inc_funnel_stat("signals_sent")
                                sinais_enviados += 1

                    except Exception as e:
                        print(f"ERRO SCANNER {symbol}:", e)

                        erro_txt = str(e)
                        if "109500" in erro_txt or "quote service unavailable" in erro_txt:
                            HEALTH["last_warning"] = (
                                f"Erro temporário BingX {nome_limpo(symbol)}: {erro_txt}"
                            )
                            HEALTH["last_error"] = None
                        else:
                            HEALTH["last_error"] = (
                                f"Erro scanner {nome_limpo(symbol)}: {erro_txt}"
                            )

                    time.sleep(0.2)
            else:
                HEALTH["last_warning"] = "Smart Predator em stand-by; scanner não envia sinais."

            HEALTH["last_signals_sent"] = sinais_enviados

            enviar_resumo_diario_se_preciso()
            enviar_resumo_mensal_se_preciso()

            HEALTH["last_success"] = data_hora_sp_str()

        except Exception as e:
            print("ERRO LOOP SCANNER:", e)

            erro_txt = str(e)
            if "109500" in erro_txt or "quote service unavailable" in erro_txt:
                HEALTH["last_warning"] = f"Erro temporário BingX no scanner: {erro_txt}"
                HEALTH["last_error"] = None
            else:
                HEALTH["last_error"] = erro_txt

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


@app.route("/ranking")
def ranking_rota():
    return ("🏆 RANKING SMART PREDATOR POR ATIVO\n\n" + asset_ranking_text(calc_predator_stats(carregar_trades())["exits"], 12)).replace("\n", "<br>")


@app.route("/eventos")
def eventos_rota():
    return montar_eventos_texto().replace("\n", "<br>")


@app.route("/events")
def events_rota():
    return montar_eventos_texto().replace("\n", "<br>")


@app.route("/execution")
def execution_rota():
    return montar_execution_status_texto().replace("\n", "<br>")

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
