# ==============================================================================
# ROBÔ MEME HUNTER ELITE - VERSÃO FINAL QUANT & EXECUÇÃO REAL BINGX
# ==============================================================================
# Lógica Principal:
# - Foco total na estratégia Hunter Breakout (Volume + Rompimento + Momentum).
# - Otimizado para não estourar rate-limit da BingX (Usa fetch_tickers unificado).
# - Abre e gerencia posições reais na conta de Futuros Perpétuos (Swap) da BingX.
# - Proteção ativa contra Spikes e gerenciamento automatizado de TP50 e Trailing.

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

# --- Funções Auxiliares de Fallback ---
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
        try: return f"{float(v):,.6f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception: return str(v)
    def fmt_pct(v):
        try: return f"{float(v):+.2f}%".replace(".", ",")
        except Exception: return str(v)

app = Flask(__name__)

# --- Configurações de Ambiente ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
UPSTASH_REDIS_REST_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_REDIS_REST_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# --- Configurações de API da Conta Real BingX ---
BINGX_API_KEY = os.environ.get("BINGX_API_KEY", "")
BINGX_SECRET_KEY = os.environ.get("BINGX_SECRET_KEY", "")
ALAVANCAGEM_PADRAO = 3  # Configura alavancagem para ativos voláteis
VALOR_POR_TRADE_USDT = 15.0  # Margem utilizada por operação

WATCHLIST_FILE = "watchlist_meme.json"
POSITIONS_KEY = "memepro:positions"
SIGNALS_KEY = "memepro:signals"
TRADES_KEY = "memepro:trades"
DAILY_SUMMARY_KEY = "memepro:daily_summary_sent"
MONTHLY_SUMMARY_KEY = "memepro:monthly_summary_sent"
BE_MONITOR_KEY = "memepro:be_monitor"
POI_COOLDOWN_KEY = "memepro:poi_cooldown"
EARLY_COOLDOWN_KEY = "memepro:early_cooldown"

# --- Parâmetros Técnicos & Estratégia ---
TIMEFRAME_H4 = "4h"
TIMEFRAME_H1 = "1h"
EMA_FAST, EMA_MID, EMA50 = 9, 21, 50
SUPERTREND_PERIOD, SUPERTREND_FACTOR = 10, 3.0
ATR_LEN, SWING_LEN, ATR_BUFFER_STOP = 14, 5, 0.25

TP50_R = 1.0
TP50_MIN_ATR = 1.0
BE_TRIGGER_R = 1.5
BE_OFFSET_PCT = 0.10
TRAIL_ATR_MULT = 2.0

ENABLE_SPIKE_FILTER = True
SPIKE_RANGE_ATR_MULT = 6.0
SPIKE_BODY_ATR_MULT = 4.0

USE_MAX_RISK_FILTER = True
MAX_RISK_H1 = 2.5
MAX_OPEN_POSITIONS = 20
PROTECTION_SECONDS = 300

# --- Configuração Específica Hunter Breakout ---
ENABLE_HUNTER_BREAKOUT = True
HUNTER_BREAKOUT_ONLY = True  # Foco exclusivo na melhor estrutura para Memes
HUNTER_SCORE_MIN = 60
HUNTER_BREAKOUT_LOOKBACK = 10
HUNTER_VOLUME_MULT_MIN = 1.8
HUNTER_RSI_BUY_MIN = 60.0
HUNTER_RSI_SELL_MAX = 40.0
HUNTER_MAX_DISTANCE_EMA9_ATR = 2.5
HUNTER_MIN_ADX_H4 = 15.0

# --- Inicialização da API CCXT & Redis ---
exchange_config = {"enableRateLimit": True, "options": {"defaultType": "swap"}}
if BINGX_API_KEY and BINGX_SECRET_KEY:
    exchange_config["apiKey"] = BINGX_API_KEY
    exchange_config["secret"] = BINGX_SECRET_KEY

exchange = ccxt.bingx(exchange_config)
redis = Redis(url=UPSTASH_REDIS_REST_URL, token=UPSTASH_REDIS_REST_TOKEN)

ultimo_candle_h1 = {}
ultimo_relatorio_hora = None
HEALTH = {
    "started_at": None, "last_scanner_run": None, "last_management_run": None,
    "last_success": None, "last_error": None, "last_watchlist_count": 0,
    "last_signals_sent": 0, "last_positions_count": 0, "watchdog_status": "OK"
}

WATCHDOG_CHECK_SECONDS = 300
WATCHDOG_THRESHOLD_MINUTES = 20
WATCHDOG_ALERT_COOLDOWN_SECONDS = 3600
LAST_WATCHDOG_ALERT_TS = 0.0

# ==============================================================================
# FUNÇÕES DE INFRAESTRUTURA & UTILS
# ==============================================================================
def agora_sp(): return datetime.now(timezone(timedelta(hours=-3)))
def data_hoje_sp_str(): return agora_sp().strftime("%Y-%m-%d")
def data_hora_sp_str(): return agora_sp().strftime("%d/%m/%Y %H:%M")
def nome_limpo(symbol): return symbol.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")

def carregar_watchlist():
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except Exception: return []

def normalizar_texto(msg):
    if msg is None: return ""
    msg = str(msg)
    try:
        if "Ã" in msg or "â" in msg or "ðŸ" in msg:
            msg = msg.encode("latin1").decode("utf-8")
    except Exception: pass
    return msg

def send_telegram_safe(msg):
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
    except Exception as e: print("Erro Telegram:", e)

# --- Métodos de Persistência via Redis JSON ---
def redis_get_json(key, padrao):
    try:
        data = redis.get(key)
        if data is None: return padrao
        return json.loads(data) if isinstance(data, str) else data
    except Exception: return padrao

def redis_set_json(key, value):
    try: redis.set(key, json.dumps(value, ensure_ascii=False))
    except Exception as e: print(f"Erro Redis Set {key}:", e)

def carregar_posicoes(): return redis_get_json(POSITIONS_KEY, {})
def salvar_posicoes(dados): redis_set_json(POSITIONS_KEY, dados)
def carregar_sinais(): return redis_get_json(SIGNALS_KEY, {})
def salvar_sinais(dados): redis_set_json(SIGNALS_KEY, dados)
def carregar_trades(): return redis_get_json(TRADES_KEY, [])
def salvar_trades(dados): redis_set_json(TRADES_KEY, dados)
def registrar_evento_trade(evento):
    trades = carregar_trades()
    trades.append(evento)
    salvar_trades(trades[-1000:])

def pnl_pct(side, entry, price):
    if side == "LONG": return ((price - entry) / entry) * 100
    return ((entry - price) / entry) * 100

def risco_label(risco_pct):
    if risco_pct <= 1.5: return "🟢 IDEAL"
    if risco_pct <= 2.5: return "🟡 ATENÇÃO"
    return "🔴 ALTO"

# ==============================================================================
# MÓDULO DE EXECUÇÃO REAL DE ORDENS FINANCEIRAS (BINGX)
# ==============================================================================
def executar_ordem_real_bingx(symbol, side, preco_referencia):
    """
    Executa a abertura real de ordens a mercado na conta de futuros perpétuos.
    Lida com cálculo de tamanho de contrato, ajuste de alavancagem e margem.
    """
    if not BINGX_API_KEY or not BINGX_SECRET_KEY:
        print(f"[SIMULAÇÃO] Ordem de {side} para {symbol} registrada (Sem API configurada).")
        return True

    try:
        # 1. Alinha Alavancagem no Ativo
        try:
            exchange.set_leverage(ALAVANCAGEM_PADRAO, symbol)
        except Exception as e:
            print(f"Aviso ao definir alavancagem em {symbol}: {e}")

        # 2. Calcula Tamanho da Ordem com Base no Valor Nominal Alavancado
        valor_nominal_usdt = VALOR_POR_TRADE_USDT * ALAVANCAGEM_PADRAO
        quantidade_contratos = valor_nominal_usdt / preco_referencia

        # Arredonda de acordo com as regras de precisão da exchange
        markets = exchange.load_markets()
        market = markets.get(symbol)
        if market and 'amount' in market['precision']:
            quantidade_contratos = exchange.amount_to_precision(symbol, quantidade_contratos)

        # 3. Determina Direção da Execução
        ordem_side = "buy" if side == "LONG" else "sell"

        print(f"📦 ENVIANDO ORDEM PRIVADA BINGX: {ordem_side.upper()} {quantidade_contratos} contratos em {symbol}")
        ordem = exchange.create_market_order(symbol, ordem_side, quantidade_contratos)
        print(f"✅ ORDEM EXECUTADA COM SUCESSO! ID: {ordem.get('id')}")
        return True

    except Exception as e:
        print(f"🚨 ERRO CRÍTICO NA EXECUÇÃO FINANCEIRA EM {symbol}: {e}")
        send_telegram_safe(f"❌ Erro ao abrir ordem real em {symbol}: {str(e)}")
        return False

def fechar_ordem_real_bingx(symbol, side_posicao):
    """Fecha a posição aberta executando a ordem reversa a mercado."""
    if not BINGX_API_KEY or not BINGX_SECRET_KEY:
        return True
    try:
        posicoes_conta = exchange.fetch_positions(symbols=[symbol])
        quantidade = 0
        for p in posicoes_conta:
            if float(p.get('contracts', 0)) > 0:
                quantidade = float(p['contracts'])
                break
        
        if quantidade == 0:
            return True

        ordem_side = "sell" if side_posicao == "LONG" else "buy"
        exchange.create_market_order(symbol, ordem_side, quantidade)
        print(f"🏁 POSIÇÃO REAL ENCERRADA EM {symbol}")
        return True
    except Exception as e:
        print(f"Erro ao fechar posição real em {symbol}: {e}")
        return False

# ==============================================================================
# INDICADORES & PROCESSAMENTO DE DADOS
# ==============================================================================
def calcular_supertrend_df(df, period=10, multiplier=3.5):
    high, low, close = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    hl2 = (high + low) / 2
    upperband, lowerband = hl2 + multiplier * atr, hl2 - multiplier * atr
    final_upper, final_lower = upperband.copy(), lowerband.copy()
    direction = pd.Series(index=df.index, dtype="int64")
    supertrend = pd.Series(index=df.index, dtype="float64")
    direction.iloc[0] = 1
    supertrend.iloc[0] = lowerband.iloc[0]

    for i in range(1, len(df)):
        final_upper.iloc[i] = upperband.iloc[i] if upperband.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1] else final_upper.iloc[i - 1]
        final_lower.iloc[i] = lowerband.iloc[i] if lowerband.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1] else final_lower.iloc[i - 1]
        if direction.iloc[i - 1] == -1: direction.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        else: direction.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
        supertrend.iloc[i] = final_lower.iloc[i] if direction.iloc[i] == 1 else final_upper.iloc[i]
    return supertrend, direction

def marcar_spikes(df):
    df = df.copy()
    if not ENABLE_SPIKE_FILTER:
        df["spike_suspeito"] = False
        return df
    if "atr14" not in df.columns: df["atr14"] = calcular_atr(df, ATR_LEN)
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
    df["atr14"] = calcular_atr(df, ATR_LEN)
    df = marcar_spikes(df)
    _, st_dir = calcular_supertrend_df(df, SUPERTREND_PERIOD, SUPERTREND_FACTOR)
    df["supertrend_dir"] = st_dir
    df["vol_avg20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["vol_avg20"]
    
    # RSI cálculo manual limpo
    delta = df["close"].astype(float).diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    rs = gain.ewm(alpha=1/14, adjust=False).mean() / loss.ewm(alpha=1/14, adjust=False).mean().replace(0, 1e-10)
    df["rsi14"] = 100 - (100 / (1 + rs))

    bb_basis = df["close"].rolling(20).mean()
    bb_dev = df["close"].rolling(20).std()
    df["bb_ok"] = ((bb_basis + 2 * bb_dev) - (bb_basis - 2 * bb_dev)) / bb_basis > ((bb_basis + 2 * bb_dev) - (bb_basis - 2 * bb_dev)).rolling(100).mean()
    return df

def calcular_stop_tp(signal, entry, df):
    candle = df.iloc[-2]
    atr = float(candle["atr14"])
    ultimos = df.iloc[-(SWING_LEN + 1):-1]
    if signal == "LONG":
        sl = float(ultimos["low"].min()) - atr * ATR_BUFFER_STOP
        risk_abs = abs(entry - sl)
        tp50 = entry + max(risk_abs * TP50_R, atr * TP50_MIN_ATR)
    else:
        sl = float(ultimos["high"].max()) + atr * ATR_BUFFER_STOP
        risk_abs = abs(sl - entry)
        tp50 = entry - max(risk_abs * TP50_R, atr * TP50_MIN_ATR)
    return float(sl), float(tp50), float(risk_abs)

# ==============================================================================
# MOTOR DA ESTRATÉGIA: HUNTER BREAKOUT
# ==============================================================================
def detectar_hunter_breakout(symbol, df_h4_preparado=None):
    if not ENABLE_HUNTER_BREAKOUT: return None
    try:
        ohlcv_h1 = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=100)
        df_h1 = preparar_df(pd.DataFrame(ohlcv_h1, columns=["time", "open", "high", "low", "close", "volume"]))
        if df_h4_preparado is None:
            ohlcv_h4 = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H4, limit=50)
            df_h4_preparado = preparar_df(pd.DataFrame(ohlcv_h4, columns=["time", "open", "high", "low", "close", "volume"]))
    except Exception: return None

    candle, candle_h4 = df_h1.iloc[-2], df_h4_preparado.iloc[-2]
    if bool(candle.get("spike_suspeito", False)): return None

    lookback = int(HUNTER_BREAKOUT_LOOKBACK)
    anteriores = df_h1.iloc[-(lookback + 2):-2]
    max_look, min_look = float(anteriores["high"].max()), float(anteriores["low"].min())
    close, ema9, ema21, ema50, atr = float(candle["close"]), float(candle["ema9"]), float(candle["ema21"]), float(candle["ema50"]), float(candle["atr14"])
    volume_ratio, rsi, bb_ok = float(candle.get("volume_ratio", 0)), float(candle.get("rsi14", 50)), bool(candle.get("bb_ok", False))
    dist_ema9_atr = abs(close - ema9) / atr if atr > 0 else 99

    if volume_ratio < HUNTER_VOLUME_MULT_MIN or dist_ema9_atr > HUNTER_MAX_DISTANCE_EMA9_ATR: return None

    signal = None
    if ema9 > ema21 >= ema50 and close > max_look and rsi >= HUNTER_RSI_BUY_MIN and bb_ok: signal = "LONG"
    elif ema9 < ema21 <= ema50 and close < min_look and rsi <= HUNTER_RSI_SELL_MAX and bb_ok: signal = "SHORT"

    if not signal: return None

    entry = close
    sl, tp50, risk_abs = calcular_stop_tp(signal, entry, df_h1)
    risk_pct = risk_abs / entry * 100
    if USE_MAX_RISK_FILTER and risk_pct > MAX_RISK_H1: return None

    # Score de Confirmação Quantitativa
    score = 25 if volume_ratio >= 3.0 else 15
    score += 25 if bb_ok else 0
    score += 25 if rsi >= 65 or rsi <= 35 else 15
    score += 25 if dist_ema9_atr <= 1.5 else 10
    score = min(score, 100)

    if score < HUNTER_SCORE_MIN: return None

    return {
        "type": "HUNTER_BREAKOUT", "signal_type": "HUNTER_BREAKOUT", "symbol": symbol,
        "symbol_clean": nome_limpo(symbol), "signal": signal, "side": signal, "timestamp": int(candle["time"]),
        "entry": entry, "sl": sl, "tp50": tp50, "risk_abs": risk_abs, "risk_pct": risk_pct,
        "hunter_score": score, "signal_score": score, "volume_ratio": volume_ratio, "rsi": rsi, "dist_ema9_atr": dist_ema9_atr
    }

# ==============================================================================
# SISTEMA DE MONITORAMENTO DE POSIÇÕES (GERENCIAMENTO DE RISCO)
# ==============================================================================
def calcular_chandelier(symbol, side):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME_H1, limit=40)
        df = marcar_spikes(preparar_df(pd.DataFrame(ohlcv, columns=["time", "open", "high", "low", "close", "volume"])))
        ultimos = df.iloc[-20:-1]
        ultimos = ultimos[~ultimos["spike_suspeito"]] if "spike_suspeito" in ultimos.columns else ultimos
        atr = float(df.iloc[-2]["atr14"])
        if side == "LONG": return float(ultimos["high"].max()) - atr * TRAIL_ATR_MULT
        return float(ultimos["low"].min()) + atr * TRAIL_ATR_MULT
    except Exception: return float(exchange.fetch_ticker(symbol)["last"])

def gerenciar_posicoes(tickers_cache):
    posicoes = carregar_posicoes()
    alterou = False

    for symbol, p in list(posicoes.items()):
        if p.get("status") == "ENCERRADO": continue

        try:
            # Puxa o preço do cache unificado para poupar a API
            ticker = tickers_cache.get(symbol)
            if not ticker: continue
            preco_atual = float(ticker["last"])

            side, entry, sl, tp50 = p["side"], float(p["entry"]), float(p["sl"]), float(p["tp50"])

            # 1. Execução de Stop Loss Físico
            if (side == "LONG" and preco_atual <= sl) or (side == "SHORT" and preco_atual >= sl):
                resultado = pnl_pct(side, entry, sl)
                fechar_ordem_real_bingx(symbol, side)
                p["status"] = "ENCERRADO"
                p["closed_at"] = time.time()
                alterou = True
                
                send_telegram_safe(f"🟣 TRAIL STOP/SL ATINGIDO - {p['symbol_clean']}\nResultado: {fmt_pct(resultado)}")
                registrar_evento_trade({"event": "CLOSE", "symbol": symbol, "pnl": resultado, "result_type": "SL"})
                continue

            # 2. Execução de Alvo Parcial (TP50)
            if not p.get("tp50_hit") and ((side == "LONG" and preco_atual >= tp50) or (side == "SHORT" and preco_atual <= tp50)):
                p["tp50_hit"] = True
                p["status"] = "TP50 HIT"
                alterou = True
                send_telegram_safe(f"🎯 TP50 ATINGIDO - {p['symbol_clean']}\nParcial 50% no bolso! Aguardando gatilho BE a 1.5R.")
                registrar_evento_trade({"event": "TP50", "symbol": symbol, "entry": entry, "tp50": tp50})
                continue

            # 3. Gatilho de Breakeven e Ativação do Trailing (Apenas em 1.5R)
            if p.get("tp50_hit") and not p.get("breakeven"):
                risk_abs = float(p.get("risk_abs", abs(entry - sl)))
                gatilho_be = entry + (risk_abs * BE_TRIGGER_R) if side == "LONG" else entry - (risk_abs * BE_TRIGGER_R)

                if (side == "LONG" and preco_atual >= gatilho_be) or (side == "SHORT" and preco_atual <= gatilho_be):
                    novo_stop_be = entry * (1 + BE_OFFSET_PCT / 100) if side == "LONG" else entry * (1 - BE_OFFSET_PCT / 100)
                    p["sl"] = max(sl, novo_stop_be) if side == "LONG" else min(sl, novo_stop_be)
                    p["breakeven"] = True
                    p["status"] = "TRAILING STOP"
                    alterou = True
                    send_telegram_safe(f"🟣 TRAILING ATIVADO - {p['symbol_clean']}\nStop puxado para o lucro (Breakeven) com Offset.")
                    continue

            # 4. Atualização Dinâmica do Trailing (Chandelier ATR)
            if p.get("breakeven"):
                novo_stop_trail = calcular_chandelier(symbol, side)
                if side == "LONG" and novo_stop_trail > sl:
                    p["sl"] = novo_stop_trail
                    alterou = True
                elif side == "SHORT" and novo_stop_trail < sl:
                    p["sl"] = novo_stop_trail
                    alterou = True

        except Exception as e: print(f"Erro na gestão de {symbol}: {e}")

    if alterou: salvar_posicoes(posicoes)

# ====================================================
# LOOP CENTRAL DO SCANNER (PROCESSADOR PRINCIPAL)
# ====================================================
def scanner():
    print("▶️ MEME HUNTER ELITE INICIADO")
    HEALTH["started_at"] = data_hora_sp_str()
    send_telegram_safe(f"🐸 Robô Caçador de Memes Ativo!\nFoco: Estrutura Breakout H1\nScore Mínimo: {HUNTER_SCORE_MIN}")

    while True:
        try:
            HEALTH["last_scanner_run"] = data_hora_sp_str()
            watchlist = carregar_watchlist()
            if not watchlist:
                time.sleep(10)
                continue

            # --- REDUÇÃO DE CORRIDA DE REDE (CACHE DE TICKERS UNIFICADO) ---
            try:
                tickers_cache = exchange.fetch_tickers(watchlist)
            except Exception as e:
                print(f"Erro ao baixar tickers: {e}")
                time.sleep(10)
                continue

            # Executa gerenciamento dinâmico de saídas
            gerenciar_posicoes(tickers_cache)
            HEALTH["last_management_run"] = data_hora_sp_str()

            # Processamento de novos sinais de entrada
            posicoes = carregar_posicoes()
            posicoes_ativas = [p for p in posicoes.values() if p.get("status") != "ENCERRADO"]
            HEALTH["last_positions_count"] = len(posicoes_ativas)

            if len(posicoes_ativas) < MAX_OPEN_POSITIONS:
                for symbol in watchlist:
                    if symbol in posicoes and posicoes[symbol].get("status") != "ENCERRADO":
                        continue

                    hunter_signal = detectar_hunter_breakout(symbol)
                    if hunter_signal:
                        # Validação contra Slippage excessivo antes de disparar
                        tk_atual = tickers_cache.get(symbol)
                        if tk_atual:
                            distancia_slippage = abs(float(tk_atual["last"]) - hunter_signal["entry"]) / hunter_signal["entry"] * 100
                            if distancia_slippage > 0.75: # Se o preço correu mais de 0.75% do fechamento, aborta
                                print(f"Sinal abortado devido a alta derrapagem (Slippage): {nome_limpo(symbol)}")
                                continue

                        # Registro e execução financeira real
                        if executar_ordem_real_bingx(symbol, hunter_signal["side"], hunter_signal["entry"]):
                            posicoes[symbol] = {
                                "symbol": symbol, "symbol_clean": hunter_signal["symbol_clean"],
                                "side": hunter_signal["side"], "entry": hunter_signal["entry"],
                                "sl": hunter_signal["sl"], "tp50": hunter_signal["tp50"],
                                "risk_abs": hunter_signal["risk_abs"], "risk_pct": hunter_signal["risk_pct"],
                                "status": "ATIVO", "breakeven": False, "tp50_hit": False, "created_at": time.time()
                            }
                            salvar_posicoes(posicoes)
                            
                            # Dispara Alerta Formatado para o Telegram
                            msg = (
                                f"🐸🟢 HUNTER BREAKOUT BUY - {hunter_signal['symbol_clean']}\n\n"
                                f"Entrada Real: {fmt_br(hunter_signal['entry'])}\n"
                                f"Stop Técnico: {fmt_br(hunter_signal['sl'])}\n"
                                f"Alvo TP50: {fmt_br(hunter_signal['tp50'])}\n\n"
                                f"Risco da Op: {fmt_risco(hunter_signal['risk_pct'])}% ({risco_label(hunter_signal['risk_pct'])})\n"
                                f"Score de Força: {hunter_signal['hunter_score']}/100\n"
                                f"Volume Multiplicador: {hunter_signal['volume_ratio']:.2f}x"
                            ) if hunter_signal["side"] == "LONG" else (
                                f"🐸🔴 HUNTER BREAKOUT SELL - {hunter_signal['symbol_clean']}\n\n"
                                f"Entrada Real: {fmt_br(hunter_signal['entry'])}\n"
                                f"Stop Técnico: {fmt_br(hunter_signal['sl'])}\n"
                                f"Alvo TP50: {fmt_br(hunter_signal['tp50'])}\n\n"
                                f"Risco da Op: {fmt_risco(hunter_signal['risk_pct'])}% ({risco_label(hunter_signal['risk_pct'])})\n"
                                f"Score de Força: {hunter_signal['hunter_score']}/100\n"
                                f"Volume Multiplicador: {hunter_signal['volume_ratio']:.2f}x"
                            )
                            send_telegram_safe(msg)
                            registrar_evento_trade({"event": "ENTRY", "symbol": symbol, "side": hunter_signal["side"]})

            HEALTH["last_success"] = data_hora_sp_str()
            HEALTH["last_error"] = None

        except Exception as e:
            HEALTH["last_error"] = str(e)
            print("Erro no Scanner Loop:", e)

        time.sleep(10) # Frequência de varredura rápida para capturar volatilidade de memes

# ==============================================================================
# PROVEDORES DOS ENDPOINTS HTTP (PAINEL WEB FLASK)
# ==============================================================================
@app.route("/health")
def health_endpoint():
    return {
        "status": "OPERACIONAL",
        "watchdog": HEALTH["watchdog_status"],
        "started_at": HEALTH["started_at"],
        "last_scanner_run": HEALTH["last_scanner_run"],
        "last_management_run": HEALTH["last_management_run"],
        "posicoes_abertas_count": HEALTH["last_positions_count"],
        "last_error": HEALTH["last_error"]
    }

@app.route("/")
def home(): return "Meme Hunter Elite Quant Engine está Ativo e Rodando."

# Inicialização assíncrona das threads nativas
threading.Thread(target=scanner, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
