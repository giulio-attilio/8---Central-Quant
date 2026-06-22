# ====================================================
# ROBÔ TREND PRO MTF H4/H1 - VERSÃO ELITE PURA (2026)
# ====================================================
from flask import Flask
import os, json, time, threading, requests, ccxt
import pandas as pd
from datetime import datetime, timezone, timedelta
from upstash_redis import Redis
from concurrent.futures import ThreadPoolExecutor

try:
    from strategy import calcular_atr
except Exception:
    def calcular_atr(df, period=14):
        high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1 / period, adjust=False).mean()

try:
    from telegram_utils import send_telegram, fmt_br, fmt_pct
except Exception:
    def fmt_br(v):
        try: return f"{float(v):,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception: return str(v)
    def fmt_pct(v):
        try: return f"{float(v):+.2f}%".replace(".", ",")
        except Exception: return str(v)
    def send_telegram(msg):
        token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id: return print(normalizar_texto(msg))
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=json.dumps({"chat_id": chat_id, "text": normalizar_texto(msg)}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}, timeout=20)

app = Flask(__name__)
BOT_NAME = os.environ.get("BOT_NAME", "Trend PRO Elite")
WATCHDOG_CHECK_SECONDS = int(os.environ.get("WATCHDOG_CHECK_SECONDS", "300"))
WATCHDOG_THRESHOLD_MINUTES = int(os.environ.get("WATCHDOG_THRESHOLD_MINUTES", "20"))
WATCHDOG_ALERT_COOLDOWN_SECONDS = int(os.environ.get("WATCHDOG_ALERT_COOLDOWN_SECONDS", "3600"))
TOKEN, CHAT_ID = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
WATCHLIST_FILE = "watchlist.json"

POSITIONS_KEY, SIGNALS_KEY, TRADES_KEY = "trendpro:positions", "trendpro:signals", "trendpro:trades"
DAILY_SUMMARY_KEY, MONTHLY_SUMMARY_KEY, BE_MONITOR_KEY = "trendpro:daily_summary_sent", "trendpro:monthly_summary_sent", "trendpro:be_monitor"
POI_COOLDOWN_KEY, EARLY_COOLDOWN_KEY = "trendpro:poi_cooldown", "trendpro:early_cooldown"

TIMEFRAME_H4, TIMEFRAME_H1 = "4h", "1h"
EMA_FAST, EMA_MID, EMA50, EMA200 = 9, 21, 50, 200
SUPERTREND_PERIOD, SUPERTREND_FACTOR, ATR_LEN, SWING_LEN, ATR_BUFFER_STOP = 10, 3.0, 14, 5, 0.25
TP50_R, TP50_MIN_ATR, BE_TRIGGER_R, BE_OFFSET_PCT, TRAIL_ATR_MULT = 1.0, 1.0, 1.5, 0.10, 2.0

ENABLE_TRENDPRO_ELITE_FILTER, ELITE_THRESHOLD, ELITE_MIN_ADX_H4 = True, 55, 15.0
REQUIRE_HIGH_VOLUME, REQUIRE_BB_EXPANDING = False, False
EARLY_THRESHOLD, EARLY_MIN_ADX_H4, EARLY_REQUIRE_VOLUME, EARLY_COOLDOWN_SECONDS = 50, 15.0, False, 3600
POI_THRESHOLD, POI_MIN_ADX_H4, POI_REQUIRE_HIGH_VOLUME, POI_COOLDOWN_SECONDS = 60, 20.0, False, 7200
POI_AFTER_ENTRY_COOLDOWN_SECONDS, ALLOW_POI_UPDATE_ENTRY = 3600, True
ENABLE_RECOVERED_SIGNAL, RECOVERED_REQUIRE_EMA_ZONE = False, True
ENABLE_REENTRY_AFTER_TP50, REENTRY_AFTER_CLOSE_SECONDS, REENTRY_COOLDOWN_SECONDS = True, 7200, 3600
ENABLE_SPIKE_FILTER, SPIKE_RANGE_ATR_MULT, SPIKE_BODY_ATR_MULT = True, 6.0, 4.0
USE_MAX_RISK_FILTER, MAX_RISK_H1, MAX_OPEN_POSITIONS, PROTECTION_SECONDS = True, 2.5, 20, 300
ENABLE_AUTO_POSITION_REPORT, ADX_LEN, ADX_MIN = False, 14, 20.0
MONTHLY_SUMMARY_DAY, MONTHLY_SUMMARY_HOUR, MONTHLY_SUMMARY_MINUTE = 1, 8, 5

exchange = ccxt.bingx({"enableRateLimit": True})
exchange.options["defaultType"] = "swap"
redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)
redis_lock = threading.Lock()
ultimo_candle_h1, ultimo_relatorio_hora = {}, None

HEALTH = {
    "started_at": None, "last_scanner_run": None, "last_management_run": None, "last_success": None, "last_error": None,
    "last_watchlist_count": 0, "last_signals_sent": 0, "last_positions_count": 0, "watchlist_total": 0, "watchlist_valid": 0,
    "watchlist_invalid": [], "last_invalid_watchlist_check": None, "last_watchdog_alert": None, "last_watchdog_alert_ts": 0,
    "watchdog_last_check": None, "watchdog_last_status": "OK"
}

def agora_sp(): return datetime.now(timezone(timedelta(hours=-3)))
def data_hoje_sp_str(): return agora_sp().strftime("%Y-%m-%d")
def data_hora_sp_str(): return agora_sp().strftime("%d/%m/%Y %H:%M")
def nome_limpo(symbol): return symbol.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")
def carregar_watchlist():
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except Exception: return []

def validar_watchlist_bingx(watchlist, avisar_telegram=False):
    validos, invalidos = [], []
    try: markets = exchange.load_markets()
    except Exception as e:
        HEALTH.update({"watchlist_total": len(watchlist), "watchlist_valid": 0, "watchlist_invalid": [], "last_invalid_watchlist_check": data_hora_sp_str(), "last_error": f"Erro load_markets BingX: {e}"})
        return watchlist
    for s in watchlist: (validos.append(s) if s in markets else invalidos.append(s))
    HEALTH.update({"watchlist_total": len(watchlist), "watchlist_valid": len(validos), "watchlist_invalid": invalidos, "last_invalid_watchlist_check": data_hora_sp_str()})
    if invalidos and avisar_telegram: safe_send_telegram(f"⚠️ Ativos inválidos na watchlist BingX (ignorados pelo scanner):\n\n" + "\n".join(invalidos))
    return validos

def redis_get_json(key, padrao):
    with redis_lock:
        try:
            data = redis.get(key)
            return json.loads(data) if isinstance(data, str) else (data if data is not None else padrao)
        except Exception: return padrao

def redis_set_json(key, value):
    with redis_lock:
        try: redis.set(key, json.dumps(value, ensure_ascii=False))
        except Exception as e: print(f"ERRO REDIS SET {key}:", e)

def carregar_posicoes(): return redis_get_json(POSITIONS_KEY, {})
def salvar_posicoes(dados): redis_set_json(POSITIONS_KEY, dados)
def carregar_sinais(): return redis_get_json(SIGNALS_KEY, {})
def salvar_sinais(dados): redis_set_json(SIGNALS_KEY, dados)
def carregar_trades(): return redis_get_json(TRADES_KEY, [])
def salvar_trades(dados): redis_set_json(TRADES_KEY, dados)
def carregar_monthly_summary_sent(): return redis_get_json(MONTHLY_SUMMARY_KEY, {})
def salvar_monthly_summary_sent(dados): redis_set_json(MONTHLY_SUMMARY_KEY, dados)
def carregar_monitor_be(): return redis_get_json(BE_MONITOR_KEY, [])
def salvar_monitor_be(dados): redis_set_json(BE_MONITOR_KEY, dados if isinstance(dados, list) else [])
def carregar_poi_cooldown(): return redis_get_json(POI_COOLDOWN_KEY, {})
def salvar_poi_cooldown(dados): redis_set_json(POI_COOLDOWN_KEY, dados)
def carregar_early_cooldown(): return redis_get_json(EARLY_COOLDOWN_KEY, {})
def salvar_early_cooldown(dados): redis_set_json(EARLY_COOLDOWN_KEY, dados)

def early_em_cooldown(symbol, side): return time.time() - float(carregar_early_cooldown().get(f"{symbol}_{side}", 0)) < EARLY_COOLDOWN_SECONDS
def marcar_early_cooldown(symbol, side):
    dados = carregar_early_cooldown()
    dados[f"{symbol}_{side}"] = time.time()
    if len(dados) > 300: dados = dict(sorted(dados.items(), key=lambda x: x[1])[-300:])
    salvar_early_cooldown(dados)

def registrar_evento_trade(evento):
    trades = carregar_trades()
    trades.append(evento)
    if len(trades) > 1000: trades = trades[-1000:]
    salvar_trades(trades)

def existe_posicao_ativa(symbol):
    p = carregar_posicoes()
    return symbol in p and p[symbol].get("status") != "ENCERRADO"

def pnl_pct(side, entry, price): return ((price - entry) / entry) * 100 if side == "LONG" else ((entry - price) / entry) * 100
def atualizar_mfe_posicao(p, preco_atual):
    try:
        pnl_at = pnl_pct(p.get("side"), float(p.get("entry")), float(preco_atual))
        if pnl_at > float(p.get("mfe_max_pct", 0)):
            p.update({"mfe_max_pct": pnl_at, "mfe_updated_at": data_hora_sp_str()})
            return True
    except Exception: pass
    return False

def check_bool(v): return "✅" if v else "❌"
def risco_label(r_pct):
    try: r = float(r_pct)
    except Exception: return "⚪ N/A"
    return "🟢 IDEAL" if r <= 1.5 else ("🟡 ATENÇÃO" if r <= 2.5 else "🔴 ALTO")
def estado_txt(st): return "BULLISH ✅" if st == 1 else ("BEARISH ✅" if st == -1 else "NEUTRO ⚠️")

def normalizar_texto(msg):
    if msg is None: return ""
    msg = str(msg)
    try:
        if "Ã" in msg or "â" in msg or "ðŸ" in msg: msg = msg.encode("latin1").decode("utf-8")
    except Exception: pass
    return msg

def enviar_texto(chat_id, msg):
    try: requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=json.dumps({"chat_id": chat_id, "text": normalizar_texto(msg)}, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json; charset=utf-8"}, timeout=20)
    except Exception as e: print("Erro ao responder Telegram:", e)
def safe_send_telegram(msg): (send_telegram(msg) if TOKEN and CHAT_ID else print(normalizar_texto(msg)))
def origem_trade_txt(p): return str(p.get("signal_type") or p.get("origin") or "NORMAL")
def mes_anterior_ref():
    hj = agora_sp()
    u_mes = hj.replace(day=1) - timedelta(days=1)
    return u_mes.strftime("%Y-%m"), u_mes.strftime("%m/%Y")

def calcular_supertrend_df(df, period=10, multiplier=3.5):
    h, l, c = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    atr = (pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)).ewm(alpha=1 / period, adjust=False).mean()
    hl2 = (h + l) / 2
    up, lw = hl2 + multiplier * atr, hl2 - multiplier * atr
    f_up, f_lw = up.copy(), lw.copy()
    direction = pd.Series(index=df.index, dtype="int64")
    st = pd.Series(index=df.index, dtype="float64")
    direction.iloc[0], st.iloc[0] = 1, lw.iloc[0]
    for i in range(1, len(df)):
        f_up.iloc[i] = up.iloc[i] if up.iloc[i] < f_up.iloc[i - 1] or c.iloc[i - 1] > f_up.iloc[i - 1] else f_up.iloc[i - 1]
        f_lw.iloc[i] = lw.iloc[i] if lw.iloc[i] > f_lw.iloc[i - 1] or c.iloc[i - 1] < f_lw.iloc[i - 1] else f_lw.iloc[i - 1]
        direction.iloc[i] = (1 if c.iloc[i] > f_up.iloc[i] else -1) if direction.iloc[i - 1] == -1 else (-1 if c.iloc[i] < f_lw.iloc[i] else 1)
        st.iloc[i] = f_lw.iloc[i] if direction.iloc[i] == 1 else f_up.iloc[i]
    return st, direction

def calcular_adx(df, period=14):
    h, l, c = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    up, dn = h.diff(), -l.diff()
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    p_di = 100 * pd.Series([u if u > d and u > 0 else 0 for u, d in zip(up, dn)], index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr
    m_di = 100 * pd.Series([d if d > u and d > 0 else 0 for u, d in zip(up, dn)], index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr
    return (100 * (p_di - m_di).abs() / (p_di + m_di)).ewm(alpha=1 / period, adjust=False).mean(), p_di, m_di

def marcar_spikes(df):
    df = df.copy()
    if not ENABLE_SPIKE_FILTER: return df.assign(spike_suspeito=False)
    if "atr14" not in df.columns: df["atr14"] = calcular_atr(df, ATR_LEN)
    c_r, c_b, atr = (df["high"].astype(float) - df["low"].astype(float)).abs(), (df["close"].astype(float) - df["open"].astype(float)).abs(), df["atr14"].astype(float)
    df["spike_suspeito"] = ((c_r > (atr * SPIKE_RANGE_ATR_MULT)) | (c_b > (atr * SPIKE_BODY_ATR_MULT))).fillna(False)
    return df

def preparar_df(df):
    df = df.copy()
    df["ema9"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=EMA_MID, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=EMA200, adjust=False).mean()
    df["atr14"] = calcular_atr(df, ATR_LEN)
    df = marcar_spikes(df)
    _, st_dir = calcular_supertrend_df(df, period=SUPERTREND_PERIOD, multiplier=SUPERTREND_FACTOR)
    df["supertrend_dir"] = st_dir
    df["volume_ok"] = df["volume"] > df["volume"].rolling(20).mean()
    bb_b = df["close"].rolling(20).mean()
    df["bb_width"] = (4 * df["close"].rolling(20).std()) / bb_b
    df["bb_ok"] = df["bb_width"] > df["bb_width"].rolling(100).mean()
    adx, p_di, m_di = calcular_adx(df, ADX_LEN)
    df.update({"adx": adx, "plus_di": p_di, "minus_di": m_di, "adx_ok": adx >= ADX_MIN})
    return df

def estado_tendencia(c): return (1 if (int(c["supertrend_dir"]) == 1 and float(c["ema9"]) > float(c["ema21"])) else (-1 if (int(c["supertrend_dir"]) == -1 and float(c["ema9"]) < float(c["ema21"])) else 0))
def nascimento_sinal(df): return ("LONG" if estado_tendencia(df.iloc[-2]) == 1 and estado_tendencia(df.iloc[-3]) != 1 else ("SHORT" if estado_tendencia(df.iloc[-2]) == -1 and estado_tendencia(df.iloc[-3]) != -1 else None))

def calcular_stop_tp(sig, entry, df):
    c, atr, ul = df.iloc[-2], float(df.iloc[-2]["atr14"]), df.iloc[-(SWING_LEN + 1):-1]
    if sig == "LONG":
        sl = float(ul["low"].min()) - atr * ATR_BUFFER_STOP
        tp = entry + max(abs(entry - sl) * TP50_R, atr * TP50_MIN_ATR)
    else:
        sl = float(ul["high"].max()) + atr * ATR_BUFFER_STOP
        tp = entry - max(abs(sl - entry) * TP50_R, atr * TP50_MIN_ATR)
    return float(sl), float(tp), float(abs(entry - sl) if sig == "LONG" else abs(sl - entry))

def calcular_qualidade(side, h4_st, h1_c):
    p = 2.0 if ((side == "LONG" and h4_st == 1) or (side == "SHORT" and h4_st == -1)) else 0.0
    p += sum([bool(h1_c.get("volume_ok", False)), bool(h1_c.get("bb_ok", False)), bool(h1_c.get("adx_ok", False))])
    return p, ("ALTA 🟢" if p >= 4 else ("MÉDIA 🟡" if p >= 2 else "BAIXA 🔴"))

def calcular_signal_score(s):
    h4, h1, score = int(s.get("h4_state", 0)), int(s.get("h1_state", 0)), 0
    if h4 != 0 and h1 == h4: score += 25
    a_h4, a_h1 = float(s.get("adx_h4", 0)), float(s.get("adx_h1", 0))
    score += 25 if a_h4 >= 40 else (15 if a_h4 >= 30 else (8 if a_h4 >= 20 else 0))
    score += 10 if a_h1 >= 30 else (5 if a_h1 >= 20 else 0)
    if bool(s.get("volume_ok", False)): score += 15
    if bool(s.get("bb_ok", False)): score += 10
    r = float(s.get("risk_pct", 99))
    score += 15 if r <= 1.0 else (10 if r <= 1.5 else (5 if r <= 2.0 else 0))
    score += 10 if "ALTA" in str(s.get("qualidade", "")) else (5 if "MÉDIA" in str(s.get("qualidade", "")) else 0)
    return min(int(score), 100)

def adicionar_signal_score(s):
    sc = calcular_signal_score(s)
    s.update({"signal_score": sc, "elite_candidate": sc >= ELITE_THRESHOLD})
    return s

def passa_filtro_trendpro_elite(s, threshold=None, min_adx_h4=None, require_high_volume=None, require_bb_expanding=None, label="SINAL"):
    if not ENABLE_TRENDPRO_ELITE_FILTER: return True, "Desligado"
    th, m_adx = threshold or ELITE_THRESHOLD, min_adx_h4 or ELITE_MIN_ADX_H4
    vol = require_high_volume if require_high_volume is not None else REQUIRE_HIGH_VOLUME
    bb = require_bb_expanding if require_bb_expanding is not None else REQUIRE_BB_EXPANDING
    if int(s.get("signal_score", 0)) < th: return False, "Score baixo"
    if float(s.get("adx_h4", 0)) < m_adx: return False, "ADX H4 baixo"
    if vol and not bool(s.get("volume_ok", False)): return False, "Volume baixo"
    if bb and not bool(s.get("bb_ok", False)): return False, "Bollinger comprimindo"
    return True, "Aprovado"

def analisar_sinal_h1(symbol):
    df_h1 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    c_h1, c_h4 = df_h1.iloc[-2], df_h4.iloc[-2]
    if bool(c_h1.get("spike_suspeito", False)): return None, df_h1, df_h4
    h4_st, h1_st = estado_tendencia(c_h4), estado_tendencia(c_h1)
    sig = nascimento_sinal(df_h1)
    if (sig == "LONG" and h4_st != 1) or (sig == "SHORT" and h4_st != -1): sig = None
    if sig is None and ENABLE_RECOVERED_SIGNAL and h4_st != 0 and h1_st == h4_st:
        z_t, z_b = max(float(c_h1["ema9"]), float(c_h1["ema21"])), min(float(c_h1["ema9"]), float(c_h1["ema21"]))
        if not RECOVERED_REQUIRE_EMA_ZONE or (float(c_h1["low"]) <= z_t and float(c_h1["high"]) >= z_b): sig = "LONG" if h1_st == 1 else "SHORT"
    if not sig: return None, df_h1, df_h4
    en = float(c_h1["close"])
    sl, tp, r_abs = calcular_stop_tp(sig, en, df_h1)
    r_pct = (r_abs / en) * 100
    if USE_MAX_RISK_FILTER and r_pct > MAX_RISK_H1: return None, df_h1, df_h4
    pts, qual = calcular_qualidade(sig, h4_st, c_h1)
    return adicionar_signal_score({"type": "SIGNAL", "signal_type": "NORMAL", "symbol": symbol, "symbol_clean": nome_limpo(symbol), "signal": sig, "side": sig, "timestamp": int(c_h1["time"]), "entry": en, "sl": sl, "tp50": tp, "risk_abs": r_abs, "risk_pct": r_pct, "h4_state": h4_st, "h1_state": h1_st, "adx_h4": float(c_h4["adx"]), "adx_h1": float(c_h1["adx"]), "volume_ok": bool(c_h1.get("volume_ok", False)), "bb_ok": bool(c_h1.get("bb_ok", False)), "qualidade_pontos": pts, "qualidade": qual}), df_h1, df_h4

def detectar_early_a(symbol):
    if not ENABLE_EARLY: return None
    df_h1 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    c, prev, c_h4 = df_h1.iloc[-2], df_h1.iloc[-3], df_h4.iloc[-2]
    if bool(c.get("spike_suspeito", False)): return None
    h4_st, h1_st = estado_tendencia(c_h4), estado_tendencia(c)
    if h4_st == 0 or (h4_st == 1 and h1_st != -1) or (h4_st == -1 and h1_st != 1) or float(c_h4.get("adx", 0)) < ADX_MIN: return None
    if not (float(c["low"]) <= float(c["ema21"]) <= float(c["high"])): return None
    sig = "LONG" if (h4_st == 1 and float(c["close"]) > float(prev["high"])) else ("SHORT" if (h4_st == -1 and float(c["close"]) < float(prev["low"])) else None)
    if not sig or early_em_cooldown(symbol, sig): return None
    en = float(c["close"])
    sl, tp, r_abs = calcular_stop_tp(sig, en, df_h1)
    r_pct = (r_abs / en) * 100
    if USE_MAX_RISK_FILTER and r_pct > MAX_RISK_H1: return None
    marcar_early_cooldown(symbol, sig)
    pts, qual = calcular_qualidade(sig, h4_st, c)
    return adicionar_signal_score({"type": "EARLY", "signal_type": "EARLY", "symbol": symbol, "symbol_clean": nome_limpo(symbol), "signal": sig, "side": sig, "timestamp": int(c["time"]), "entry": en, "sl": sl, "tp50": tp, "risk_abs": r_abs, "risk_pct": r_pct, "h4_state": h4_st, "h1_state": h1_st, "adx_h4": float(c_h4["adx"]), "adx_h1": float(c["adx"]), "volume_ok": bool(c.get("volume_ok", False)), "bb_ok": bool(c.get("bb_ok", False)), "qualidade_pontos": pts, "qualidade": qual})

def poi_em_cooldown(symbol, side): return time.time() - float(carregar_poi_cooldown().get(f"{symbol}_{side}", 0)) < POI_COOLDOWN_SECONDS
def marcar_poi_cooldown(symbol, side):
    dados = carregar_poi_cooldown()
    dados[f"{symbol}_{side}"] = time.time()
    if len(dados) > 300: dados = dict(sorted(dados.items(), key=lambda x: x[1])[-300:])
    salvar_poi_cooldown(dados)

def detectar_poi(symbol, posicao):
    try:
        if time.time() - float(posicao.get("active_since", 0)) < POI_AFTER_ENTRY_COOLDOWN_SECONDS: return None
    except Exception: pass
    if poi_em_cooldown(symbol, posicao["side"]): return None
    df_h1 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    c, side = df_h1.iloc[-2], posicao["side"]
    if bool(c.get("spike_suspeito", False)): return None
    h4_st, h1_st = estado_tendencia(df_h4.iloc[-2]), estado_tendencia(c)
    if (side == "LONG" and not (h4_st == 1 and h1_st == 1)) or (side == "SHORT" and not (h4_st == -1 and h1_st == -1)): return None
    z_t, z_b = max(float(c["ema9"]), float(c["ema21"])), min(float(c["ema9"]), float(c["ema21"]))
    p_at = carregar_posicoes().get(symbol, posicao)
    if not (float(c["low"]) <= z_t and float(c["high"]) >= z_b):
        if bool(p_at.get("last_poi_zone", False)):
            p_at["last_poi_zone"] = False
            p = carregar_posicoes()
            p[symbol] = p_at
            salvar_posicoes(p)
        return None
    if bool(p_at.get("last_poi_zone", False)): return None
    if not ((float(c["close"]) > float(c["ema21"])) if side == "LONG" else (float(c["close"]) < float(c["ema21"]))): return None
    en, sl = float(c["close"]), float(p_at["sl"])
    r_abs = abs(en - sl)
    if USE_MAX_RISK_FILTER and ((r_abs / en) * 100) > MAX_RISK_H1: return None
    marcar_poi_cooldown(symbol, side)
    p_at["last_poi_zone"] = True
    p = carregar_posicoes()
    p[symbol] = p_at
    salvar_posicoes(p)
    pts, qual = calcular_qualidade(side, h4_st, c)
    return adicionar_signal_score({"type": "POI", "signal_type": "POI", "symbol": symbol, "symbol_clean": nome_limpo(symbol), "signal": side, "side": side, "timestamp": int(c["time"]), "entry": en, "sl": sl, "tp50": en + (r_abs * TP50_R if side == "LONG" else -r_abs * TP50_R), "risk_abs": r_abs, "risk_pct": (r_abs / en) * 100, "h4_state": h4_st, "h1_state": h1_st, "adx_h4": float(df_h4.iloc[-2]["adx"]), "adx_h1": float(c["adx"]), "volume_ok": bool(c.get("volume_ok", False)), "bb_ok": bool(c.get("bb_ok", False)), "qualidade_pontos": pts, "qualidade": qual})

def detectar_reentry(symbol, pos_fechada):
    if not ENABLE_REENTRY_AFTER_TP50 or not pos_fechada or pos_fechada.get("status") != "ENCERRADO" or not bool(pos_fechada.get("tp50_hit", False)): return None
    try:
        if time.time() - float(pos_fechada.get("closed_at", 0)) < REENTRY_AFTER_CLOSE_SECONDS: return None
        if time.time() - float(pos_fechada.get("last_reentry_at", 0) or 0) < REENTRY_COOLDOWN_SECONDS: return None
    except Exception: return None
    side = pos_fechada.get("side")
    df_h1 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    df_h4 = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=300), columns=["time", "open", "high", "low", "close", "volume"]))
    c = df_h1.iloc[-2]
    if bool(c.get("spike_suspeito", False)): return None
    h4_st, h1_st = estado_tendencia(df_h4.iloc[-2]), estado_tendencia(c)
    if (side == "LONG" and not (h4_st == 1 and h1_st == 1)) or (side == "SHORT" and not (h4_st == -1 and h1_st == -1)): return None
    z_t, z_b = max(float(c["ema9"]), float(c["ema21"])), min(float(c["ema9"]), float(c["ema21"]))
    p_at = carregar_posicoes().get(symbol, pos_fechada)
    r_ready = bool(p_at.get("reentry_ready", False))
    if not (float(c["low"]) <= z_t and float(c["high"]) >= z_b):
        if not r_ready:
            p_at["reentry_ready"] = True
            p = carregar_posicoes()
            p[symbol] = p_at
            salvar_posicoes(p)
        return None
    if not r_ready or not ((float(c["close"]) > float(c["ema21"])) if side == "LONG" else (float(c["close"]) < float(c["ema21"]))): return None
    en = float(c["close"])
    sl, tp, r_abs = calcular_stop_tp(side, en, df_h1)
    if USE_MAX_RISK_FILTER and ((r_abs / en) * 100) > MAX_RISK_H1: return None
    p_at.update({"reentry_ready": False, "last_reentry_at": time.time()})
    p = carregar_posicoes()
    p[symbol] = p_at
    salvar_posicoes(p)
    pts, qual = calcular_qualidade(side, h4_st, c)
    return adicionar_signal_score({"type": "REENTRY", "signal_type": "REENTRY", "symbol": symbol, "symbol_clean": nome_limpo(symbol), "signal": side, "side": side, "timestamp": int(c["time"]), "entry": en, "sl": sl, "tp50": tp, "risk_abs": r_abs, "risk_pct": (r_abs / en) * 100, "h4_state": h4_st, "h1_state": h1_st, "adx_h4": float(df_h4.iloc[-2]["adx"]), "adx_h1": float(c["adx"]), "volume_ok": bool(c.get("volume_ok", False)), "bb_ok": bool(c.get("bb_ok", False)), "candles_since_close": int((time.time() - float(pos_fechada.get("closed_at"))) / 3600), "qualidade_pontos": pts, "qualidade": qual})

def enviar_early_a(s): safe_send_telegram(f"{'🚀 🟢' if s['signal'] == 'LONG' else '🚀 🔴'} EARLY {s['signal']} - {s['symbol_clean']}\n\nEntrada antecipada na EMA21.\nH4: {estado_txt(s['h4_state'])}\nEntrada: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}\nRisco: {fmt_pct(s['risk_pct'])} ({risco_label(s['risk_pct'])})\nScore: {s['signal_score']}")
def enviar_sinal_h1(s): safe_send_telegram(f"{'🟢' if s['signal'] == 'LONG' else '🔴'} {s['signal']} H1 - {s['symbol_clean']}\n\nH4: {estado_txt(s['h4_state'])}\nH1: {estado_txt(s['h1_state'])}\n\nEntrada: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}\nRisco: {fmt_pct(s['risk_pct'])} ({risco_label(s['risk_pct'])})\nScore: {s['signal_score']}")
def enviar_reentry(s): safe_send_telegram(f"{'🔁 🟢' if s['signal'] == 'LONG' else '🔁 🔴'} REENTRY {s['signal']} - {s['symbol_clean']}\n\nCorreção na zona de médias.\nEntrada: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}\nScore: {s['signal_score']}")
def enviar_poi(s): safe_send_telegram(f"🔵 POI H1 - {s['symbol_clean']}\n\nRegião de valor: {fmt_br(s['entry'])}\nSL: {fmt_br(s['sl'])}\nTP50: {fmt_br(s['tp50'])}")
def enviar_tp50(p, tp, pnl): safe_send_telegram(f"🎯 TP50 ELITE - {p['symbol_clean']}\n\nParcial de 50% executada no alvo.\nResultado: {fmt_pct(pnl)}\nStatus: Protegido no SL original. Trava no BE em 1.5R.")
def enviar_trailing_ativado(p, n_sl): safe_send_telegram(f"🟣 BREAKEVEN ATIVADO - {p['symbol_clean']}\n\nAndou 1.5R. Stop na entrada.\nNovo Stop: {fmt_br(n_sl)}")
def enviar_trailing(p, n_sl): safe_send_telegram(f"🟣 TRAILING ATUALIZADO - {p['symbol_clean']}\n\nChandelier Protetor: {fmt_br(n_sl)}")
def enviar_stop(p, pr, st, res): safe_send_telegram(f"{'🟣 TRAIL STOP' if res >= 0 else '🟠 STOP LOSS'} - {p['symbol_clean']}\n\nEncerrado.\nSaída: {fmt_br(st)}\nResultado: {fmt_pct(res)}")

def registrar_posicao(s):
    p = carregar_posicoes()
    if s["symbol"] in p and p[s["symbol"]].get("status") != "ENCERRADO": return False
    if len([x for x in p.values() if x.get("status") != "ENCERRADO"]) >= MAX_OPEN_POSITIONS: return False
    p[s["symbol"]] = {"symbol": s["symbol"], "symbol_clean": s["symbol_clean"], "side": s["signal"], "entry": s["entry"], "sl": s["sl"], "tp50": s["tp50"], "risk_abs": s["risk_abs"], "risk_pct": s["risk_pct"], "status": "ATIVO", "mfe_max_pct": 0.0, "mfe_updated_at": None, "breakeven": False, "tp50_hit": False, "tp50_message_sent": False, "be_trigger_message_sent": False, "timestamp": s["timestamp"], "created_at": time.time(), "active_since": time.time(), "breakeven_activated_at": None, "last_trailing_message_stop": None, "trailing_activated_at": None, "h4_state": s.get("h4_state"), "h1_state": s.get("h1_state"), "signal_type": s.get("signal_type", "NORMAL"), "signal_score": s.get("signal_score"), "elite_candidate": bool(s.get("elite_candidate")), "last_poi_zone": False, "reentry_ready": False, "last_reentry_at": None, "closed_at": None, "closed_reason": None}
    salvar_posicoes(p)
    registrar_evento_trade({"event": "ENTRY", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), **p[s["symbol"]]})
    return True

def atualizar_posicao_com_poi(poi):
    if not ALLOW_POI_UPDATE_ENTRY: return
    p = carregar_posicoes()
    if poi["symbol"] not in p or p[poi["symbol"]].get("status") == "ENCERRADO": return
    p[poi["symbol"]].update({"entry": poi["entry"], "tp50": poi["tp50"], "risk_abs": poi["risk_abs"], "risk_pct": poi["risk_pct"], "timestamp": poi["timestamp"], "active_since": time.time(), "breakeven": False, "tp50_hit": False, "status": "ATIVO", "breakeven_activated_at": None, "trailing_activated_at": None, "last_poi_zone": True, "last_update_type": "POI"})
    salvar_posicoes(p)
    registrar_evento_trade({"event": "POI", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), **poi})

def calcular_chandelier(symbol, side):
    df = preparar_df(pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=80), columns=["time", "open", "high", "low", "close", "volume"]))
    atr, ul = float(df.iloc[-2]["atr14"]), df.iloc[-40:-1]
    if "spike_suspeito" in ul.columns: ul = ul[~ul["spike_suspeito"]]
    if len(ul) < 10: ul = df.iloc[-23:-1]
    return float(ul["high"].max()) - atr * TRAIL_ATR_MULT if side == "LONG" else float(ul["low"].min()) + atr * TRAIL_ATR_MULT

def stop_em_carencia(p):
    for f in ["breakeven_activated_at", "trailing_activated_at"]:
        if p.get(f) and (time.time() - float(p[f]) < PROTECTION_SECONDS): return True
    return False

def adicionar_monitor_be(p, entry, exit_price):
    m = carregar_monitor_be()
    m.append({"symbol": p["symbol"], "symbol_clean": p["symbol_clean"], "side": p["side"], "entry": entry, "exit_price": exit_price, "closed_at": time.time(), "closed_date": data_hoje_sp_str(), "closed_datetime": data_hora_sp_str(), "monitor_until": time.time() + 86400, "best_after_pct": 0.0, "active": True})
    salvar_monitor_be(m[-500:] if len(m) > 500 else m)
def atualizar_monitor_be():
    m_list, alt = carregar_monitor_be(), False
    if not m_list: return
    for m in m_list:
        if not m.get("active"): continue
        try:
            mov = pnl_pct(m["side"], float(m["exit_price"]), float(exchange.fetch_ticker(m["symbol"])["last"]))
            if mov > float(m.get("best_after_pct", 0)): m["best_after_pct"], alt = mov, True
            if time.time() >= float(m.get("monitor_until", 0)): m["active"], alt = False, True
        except Exception: pass
    if alt: salvar_monitor_be(m_list)

def gerenciar_posicoes():
    p_dict, alt = carregar_posicoes(), False
    for sym, p in list(p_dict.items()):
        if p.get("status") == "ENCERRADO": continue
        try:
            pr_at = float(exchange.fetch_ticker(sym)["last"])
            if atualizar_mfe_posicao(p, pr_at): alt = True
            if bool(preparar_df(pd.DataFrame(exchange.fetch_ohlcv(sym, timeframe=TIMEFRAME_H1, limit=40), columns=["time", "open", "high", "low", "close", "volume"])).iloc[-2].get("spike_suspeito", False)): continue
            side, entry, sl, tp = p["side"], float(p["entry"]), float(p["sl"]), float(p["tp50"])
            if not stop_em_carencia(p) and ((side == "LONG" and pr_at <= sl) or (side == "SHORT" and pr_at >= sl)):
                res = pnl_pct(side, entry, sl)
                enviar_stop(p, pr_at, sl, res)
                r_tp = "BREAKEVEN" if (p.get("breakeven") and -0.05 <= res <= 0.30) else ("WIN" if res > 0 else "LOSS")
                registrar_evento_trade({"event": "CLOSE", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "exit": sl, "pnl": res, "mfe_gave_back_pct": float(p.get("mfe_max_pct", 0)) - res, "result_type": r_tp, **p})
                if r_tp == "BREAKEVEN": adicionar_monitor_be(p, entry, sl)
                p.update({"closed_at": time.time(), "closed_datetime": data_hora_sp_str(), "closed_reason": r_tp, "reentry_ready": False, "status": "ENCERRADO"})
                alt = True
                continue
            if not p.get("tp50_hit") and not p.get("tp50_message_sent") and ((side == "LONG" and pr_at >= tp) or (side == "SHORT" and pr_at <= tp)):
                p.update({"tp50_hit": True, "tp50_message_sent": True, "status": "TP50 HIT", "tp50_activated_at": time.time()})
                alt = True
                enviar_tp50(p, tp, pnl_pct(side, entry, tp))
                registrar_evento_trade({"event": "TP50", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "be_trigger_price": entry + (float(p.get("risk_abs", 0)) * BE_TRIGGER_R if side == "LONG" else -float(p.get("risk_abs", 0)) * BE_TRIGGER_R), **p})
                continue
            if p.get("tp50_hit") and not p.get("breakeven") and not p.get("be_trigger_message_sent"):
                trig = entry + (float(p.get("risk_abs", 0)) * BE_TRIGGER_R if side == "LONG" else -float(p.get("risk_abs", 0)) * BE_TRIGGER_R)
                if (side == "LONG" and pr_at >= trig) or (side == "SHORT" and pr_at <= trig):
                    n_sl = max(sl, entry * (1 + BE_OFFSET_PCT / 100), calcular_chandelier(sym, side)) if side == "LONG" else min(sl, entry * (1 - BE_OFFSET_PCT / 100), calcular_chandelier(sym, side))
                    p.update({"sl": n_sl, "breakeven": True, "be_trigger_message_sent": True, "status": "TRAILING STOP", "breakeven_activated_at": time.time(), "trailing_activated_at": time.time()})
                    alt = True
                    enviar_trailing_ativado(p, n_sl)
                    registrar_evento_trade({"event": "BE_TRIGGER", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "new_stop": n_sl, **p})
                    continue
            if p.get("tp50_hit") and p.get("breakeven"):
                n_sl = calcular_chandelier(sym, side)
                if (side == "LONG" and n_sl > sl) or (side == "SHORT" and n_sl < sl):
                    if p.get("last_trailing_message_stop") == n_sl: continue
                    p.update({"sl": n_sl, "trailing_activated_at": time.time(), "last_trailing_message_stop": n_sl})
                    alt = True
                    enviar_trailing(p, n_sl)
                    registrar_evento_trade({"event": "TRAILING", "date": data_hoje_sp_str(), "datetime": data_hora_sp_str(), "new_stop": n_sl, **p})
        except Exception as e: print(f"ERRO GESTÃO {sym}: {e}")
    if alt: salvar_posicoes(p_dict)

def obtener_posicoes_ativas_ordenadas():
    p_dict, ativos = carregar_posicoes(), []
    for p in p_dict.values():
        if p.get("status") == "ENCERRADO": continue
        try:
            p_cp = dict(p)
            p_cp["pnl_atual"] = pnl_pct(p["side"], float(p["entry"]), float(exchange.fetch_ticker(p["symbol"])["last"]))
            ativos.append(p_cp)
        except Exception: pass
    return sorted(ativos, key=lambda x: x["pnl_atual"], reverse=True)

def enviar_relatorio_posicoes():
    at = obter_posicoes_ativas_ordenadas()
    if not at: return send_telegram(f"📊 RELATÓRIO DE POSIÇÕES\n{data_hora_sp_str()}\n\nNenhum trade ativo.")
    linhas = ["📊 RELATÓRIO DE POSIÇÕES", data_hora_sp_str()]
    for p in at: linhas.append(f"\n{p['symbol_clean']} - {p['side']}\n\nPnL: {fmt_pct(p['pnl_atual'])}\nEntrada: {fmt_br(p['entry'])}\nStop: {fmt_br(p['sl'])}\nTP50: {fmt_br(p['tp50'])}\nStatus: BE {check_bool(p.get('breakeven'))} | TP50 {check_bool(p.get('tp50_hit'))}\n────────────────")
    send_telegram("\n".join(linhas))

def montar_status():
    at = obter_posicoes_ativas_ordenadas()
    linhas = ["📊 STATUS DO ROBÔ", f"\nTrades ativos: {len(at)}"]
    if not at: return "\n".join(linhas) + "\nNenhum trade ativo."
    linhas.append("\n────────────────\n")
    for p in at: linhas.append(f"{p['symbol_clean']} - {p['side']}\n\nPnL: {fmt_pct(p['pnl_atual'])}\nEntrada: {fmt_br(p['entry'])}\nStop: {fmt_br(p['sl'])}\nTP50: {fmt_br(p['tp50'])}\nBreakeven {check_bool(p.get('breakeven'))}\nTP50 {check_bool(p.get('tp50_hit'))}\n────────────────\n")
    return "\n".join(linhas)

def montar_resumo_diario():
    hj, dt_br, tr = data_hoje_sp_str(), agora_sp().strftime("%d/%m/%Y"), carregar_trades()
    en = [t for t in tr if t.get("date") == hj and t.get("event") == "ENTRY"]
    pois = [t for t in tr if t.get("date") == hj and t.get("event") == "POI"]
    fe = [t for t in tr if t.get("date") == hj and t.get("event") == "CLOSE"]
    tp = [t for t in tr if t.get("date") == hj and t.get("event") == "TP50"]
    tl = [t for t in tr if t.get("date") == hj and t.get("event") == "TRAILING"]
    w, l, b = [t for t in fe if t.get("result_type") == "WIN"], [t for t in fe if t.get("result_type") == "LOSS"], [t for t in fe if t.get("result_type") == "BREAKEVEN"]
    melhor = max(fe, key=lambda x: float(x.get("pnl", 0))) if fe else None
    pior = min(fe, key=lambda x: float(x.get("pnl", 0))) if fe else None
    return "\n".join([f"📈 RESUMO TREND PRO ELITE", dt_br, "", f"Sinais H1 do dia: {len(en)}", f"LONG: {len([t for t in en if t.get('side') == 'LONG'])} | SHORT: {len([t for t in en if t.get('side') == 'SHORT'])}", f"EARLY: {len([t for t in en if t.get('signal_type') == 'EARLY'])} | REENTRY: {len([t for t in en if t.get('signal_type') == 'REENTRY'])}", f"POIs H1: {len(pois)}", "", f"Trades encerrados: {len(fe)} (Wins: {len(w)} | BE: {len(b)} | Loss: {len(l)})", "", f"TP50 atingidos: {len(tp)} | Trailings: {len(tl)}", "", f"PnL diário: {fmt_pct(sum(float(t.get('pnl', 0)) for t in fe))}", "", f"MFE Geral: {fmt_pct((sum(float(t.get('mfe_max_pct', 0)) for t in fe)/len(fe)) if fe else 0)}", f"Devolução: {fmt_pct((sum(float(t.get('mfe_gave_back_pct', 0)) for t in fe)/len(fe)) if fe else 0)}", "", f"Melhor: {melhor['symbol_clean'] if melhor else 'N/A'} {fmt_pct(melhor['pnl'] if melhor else 0)}", f"Pior: {pior['symbol_clean'] if pior else 'N/A'} {fmt_pct(pior['pnl'] if pior else 0)}"])

def montar_resumo_mensal():
    ref, txt = mes_anterior_ref()
    tr = [t for t in carregar_trades() if str(t.get("date", "")).startswith(ref)]
    ex = [t for t in tr if t.get("event") == "CLOSE"]
    w, l, b = [t for t in ex if t.get("result_type") == "WIN"], [t for t in ex if t.get("result_type") == "LOSS"], [t for t in ex if t.get("result_type") == "BREAKEVEN"]
    return f"📊 RESUMO MENSAL\nMês: {txt}\n\nSinais H1: {len([t for t in tr if t.get('event') == 'ENTRY'])}\nFechados: {len(ex)}\nWins: {len(w)} | BE: {len(b)} | Loss: {len(l)}\nWin Rate: {(len(w)/len(ex)*100 if ex else 0):.2f}%\n\nPnL: {fmt_pct(sum(float(t.get('pnl', 0)) for t in ex))}\nMFE Médio: {fmt_pct((sum(float(t.get('mfe_max_pct', 0)) for t in ex)/len(ex)) if ex else 0)}\nDevolução: {fmt_pct((sum(float(t.get('mfe_gave_back_pct', 0)) for t in ex)/len(ex)) if ex else 0)}"

def enviar_resumo_mensal_se_preciso():
    ag = agora_sp()
    if ag.day != MONTHLY_SUMMARY_DAY or ag.hour != MONTHLY_SUMMARY_HOUR or ag.minute < MONTHLY_SUMMARY_MINUTE: return
    env, ref = carregar_monthly_summary_sent(), mes_anterior_ref()[0]
    if env.get(ref): return
    safe_send_telegram(montar_resumo_mensal())
    env[ref] = True
    salvar_monthly_summary_sent(dict(sorted(env.items())[-36:]) if len(env) > 36 else env)

def montar_monitor_be():
    mon, activos = carregar_monitor_be(), [x for x in carregar_monitor_be() if x.get("active")]
    li = [f"📉 MONITOR BREAKEVEN ({len(activos)})", "\nÚltimas evoluções:"]
    for m in reversed(mon[-10:]): li.append(f"\n{m.get('symbol_clean')} | Pós-saída: +{m.get('best_after_pct',0):.2f}% | {'ATIVO' if m.get('active') else 'FINALIZADO'}")
    return "\n".join(li)

def parse_data_hora_sp(valor):
    try: return datetime.strptime(str(valor), "%d/%m/%Y %H:%M")
    except Exception: return None

def minutos_desde_health(f):
    dt = parse_data_hora_sp(HEALTH.get(f))
    return round(((agora_sp().replace(tzinfo=None)) - dt).total_seconds() / 60, 2) if dt else None

def montar_watchdog_status():
    ms = minutos_desde_health("last_scanner_run")
    mm = minutos_desde_health("last_management_run")
    st = (ms is not None and ms > WATCHDOG_THRESHOLD_MINUTES)
    mt = (mm is not None and mm > WATCHDOG_THRESHOLD_MINUTES)
    ok = (HEALTH.get("last_error") is None and not st and not mt)
    re = []
    if HEALTH.get("last_error"): re.append(f"Erro: {HEALTH.get('last_error')}")
    if st: re.append(f"Scanner parado ({ms} min)")
    if mt: re.append(f"Gestão parada ({mm} min)")
    return {"ok": ok, "status": "OK" if ok else "ALERTA", "reasons": re, "minutes_since_scanner": ms if ms else 0, "minutes_since_management": mm if mm else 0}

def watchdog_loop():
    while True:
        try:
            HEALTH["watchdog_last_check"] = data_hora_sp_str()
            wd = montar_watchdog_status()
            HEALTH["watchdog_last_status"] = wd["status"]
            if not wd["ok"] and (time.time() - float(HEALTH.get("last_watchdog_alert_ts", 0)) >= WATCHDOG_ALERT_COOLDOWN_SECONDS):
                safe_send_telegram(f"🚨 WATCHDOG ALERT - {BOT_NAME}\n\nRobô travado.\nMotivos:\n" + "\n".join([f"- {m}" for m in wd["reasons"]]))
                HEALTH.update({"last_watchdog_alert": data_hora_sp_str(), "last_watchdog_alert_ts": time.time()})
        except Exception as e: print("ERRO WATCHDOG LOOP:", e)
        time.sleep(WATCHDOG_CHECK_SECONDS)

def processar_ativo_paralelo(symbol):
    try:
        p_dict = carregar_posicoes()
        if symbol in p_dict and p_dict[symbol].get("status") != "ENCERRADO":
            poi = detectar_poi(symbol, p_dict[symbol])
            if poi and passa_filtro_trendpro_elite(poi, threshold=POI_THRESHOLD, min_adx_h4=POI_MIN_ADX_H4, require_high_volume=POI_REQUIRE_HIGH_VOLUME, require_bb_expanding=False, label="POI")[0]:
                enviar_poi(poi)
                atualizar_posicao_com_poi(poi)
            return
        if symbol in p_dict and p_dict[symbol].get("status") == "ENCERRADO":
            re = detectar_reentry(symbol, p_dict[symbol])
            if re and passa_filtro_trendpro_elite(re, label="REENTRY")[0]:
                ch_re = f"REENTRY_{symbol}_{int(re['timestamp'])}_{re['signal']}"
                hist = carregar_sinais()
                if ch_re not in hist and registrar_posicao(re):
                    hist[ch_re] = True
                    salvar_sinais(hist)
                    enviar_reentry(re)
            return
        ea = detectar_early_a(symbol)
        if ea and passa_filtro_trendpro_elite(ea, threshold=EARLY_THRESHOLD, min_adx_h4=EARLY_MIN_ADX_H4, require_high_volume=EARLY_REQUIRE_VOLUME, require_bb_expanding=False, label="EARLY")[0]:
            ch_ea = f"EARLY_{symbol}_{int(ea['timestamp'])}_{ea['signal']}"
            hist = carregar_sinais()
            if ch_ea not in hist and registrar_posicao(ea):
                hist[ch_ea] = True
                salvar_sinais(hist)
                enviar_early_a(ea)
            return
        res, _, _ = analisar_sinal_h1(symbol)
        if res and passa_filtro_trendpro_elite(res, label="SINAL")[0]:
            ts = int(res["timestamp"])
            if symbol in ultimo_candle_h1 and ultimo_candle_h1[symbol] == ts: return
            ultimo_candle_h1[symbol] = ts
            if not existe_posicao_ativa(symbol):
                ch = f"{symbol}_{ts}_{res['signal']}"
                hist = carregar_sinais()
                if ch not in hist and registrar_posicao(res):
                    hist[ch] = True
                    salvar_sinais(hist)
                    enviar_sinal_h1(res)
    except Exception as e: print(f"Erro no ativo {symbol}: {e}")

def scanner():
    print("SCANNER INICIADO - TREND PRO ELITE")
    HEALTH["started_at"] = data_hora_sp_str()
    safe_send_telegram(f"🤖 Robô {BOT_NAME} Inicializado!\n\nScore Mínimo: {ELITE_THRESHOLD}/100\nADX H4: {ELITE_MIN_ADX_H4}\nModo: 100% ISOLADO ✅")
    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            gerenciar_posicoes()
            HEALTH["last_management_run"] = data_hora_sp_str()
            atualizar_monitor_be()
            ag_br = agora_sp()
            if ag_br.hour == 23 and ag_br.minute >= 55:
                env = redis_get_json(DAILY_SUMMARY_KEY, {})
                if not env.get(data_hoje_sp_str()):
                    safe_send_telegram(montar_resumo_diario())
                    env[data_hoje_sp_str()] = True
                    redis_set_json(DAILY_SUMMARY_KEY, env)
            enviar_resumo_mensal_se_preciso()
            wl = validar_watchlist_bingx(carregar_watchlist(), avisar_telegram=False)
            HEALTH["last_watchlist_count"] = len(wl)
            with ThreadPoolExecutor(max_workers=5) as executor: executor.map(processar_ativo_paralelo, wl)
            HEALTH.update({"last_success": data_hora_sp_str(), "last_error": None})
        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("ERRO CRÍTICO SCANNER:", e)
        time.sleep(60)

def listen_commands():
    last_id = 0
    while True:
        try:
            resp = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_id + 1}", timeout=30).json()
            for up in resp.get("result", []):
                last_id = up.get("update_id", last_id)
                msg = up.get("message", {})
                tx, c_id = msg.get("text", ""), msg.get("chat", {}).get("id")
                if not c_id: continue
                if tx == "/status" or tx == "/health":
                    wd = montar_watchdog_status()
                    ab = [p for p in carregar_posicoes().values() if p.get("status") != "ENCERRADO"]
                    enviar_texto(c_id, json.dumps({"ok": wd["ok"], "bot": BOT_NAME, "uptime_horas": round((datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None) - datetime.strptime(HEALTH["started_at"], "%d/%m/%Y %H:%M")).total_seconds()/3600, 2) if HEALTH["started_at"] else 0, "positions_open": len(ab), "watchdog_status": wd["status"]}, ensure_ascii=False, indent=2))
                elif tx == "/posicoes":
                    ab = [p for p in carregar_posicoes().values() if p.get("status") != "ENCERRADO"]
                    if not ab: enviar_texto(c_id, "Nenhuma posição ativa.")
                    else:
                        li = [f"Posições ({len(ab)}/{MAX_OPEN_POSITIONS}):\n"]
                        for p in ab:
                            try: pnl = pnl_pct(p["side"], float(p["entry"]), float(exchange.fetch_ticker(p["symbol"])["last"]))
                            except Exception: pnl = 0.0
                            li.append(f"{p['symbol_clean']} {p['side']} | PnL: {fmt_pct(pnl)} | Entry: {fmt_br(p['entry'])}")
                        enviar_texto(c_id, "\n".join(li))
                elif tx == "/resumo": enviar_texto(c_id, montar_resumo_diario())
                elif tx == "/mensal": enviar_texto(c_id, montar_resumo_mensal())
                elif tx == "/be": enviar_texto(c_id, montar_monitor_be())
                elif tx == "/teste": enviar_texto(c_id, "✅ Trend PRO Elite operacional.")
                elif tx == "/reset":
                    salvar_sinais({}), salvar_monitor_be([]), salvar_poi_cooldown({}), salvar_early_cooldown({})
                    enviar_texto(c_id, "✅ Travas operacionais e cooldowns redefinidos.")
        except Exception as e: print("ERRO TELEGRAM CMD:", e)
        time.sleep(2)

@app.route("/health")
def health_endpoint(): return {"ok": montar_watchdog_status()["ok"], "bot": BOT_NAME, "watchdog": montar_watchdog_status(), "telemetria": HEALTH}
@app.route("/")
def home(): return f"{BOT_NAME} Elite - Running Isolated Mode"

threading.Thread(target=scanner, daemon=True).start()
threading.Thread(target=listen_commands, daemon=True).start()
threading.Thread(target=watchdog_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
