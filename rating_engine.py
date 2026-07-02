# ==============================================================================
# CENTRAL QUANT - RATING ENGINE
# Versão: 2026-07-02-RATING-ENGINE-V1
#
# Objetivo:
# - Transformar métricas do Performance Engine em leitura estatística objetiva.
# - Gerar score 0-100, rating, confidence, sample_status e risk_bias.
# - Não decide sozinho execução real; apenas fornece camada analítica para a Central.
# ==============================================================================


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.replace("%", "").replace(",", ".").strip()
        return float(value)
    except Exception:
        return default


def _safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def clamp(value, min_value=0.0, max_value=100.0):
    try:
        value = float(value)
    except Exception:
        value = min_value
    return max(min_value, min(max_value, value))


def sample_status_for_trades(trades):
    trades = _safe_int(trades, 0)
    if trades <= 0:
        return "NO_SAMPLE"
    if trades < 10:
        return "INSUFFICIENT"
    if trades < 30:
        return "LOW"
    if trades < 100:
        return "MEDIUM"
    if trades < 300:
        return "HIGH"
    return "ROBUST"


def confidence_for_trades(trades):
    """
    Confiança estatística baseada apenas na amostra.
    Não mede qualidade da estratégia; mede confiabilidade da leitura.
    """
    trades = _safe_int(trades, 0)
    if trades <= 0:
        return 0
    if trades < 10:
        return int(round(10 + trades * 3.0))          # 1-9 -> 13-37
    if trades < 30:
        return int(round(40 + (trades - 10) * 1.5))   # 10-29 -> 40-68
    if trades < 100:
        return int(round(70 + (trades - 30) * 0.25))  # 30-99 -> 70-87
    if trades < 300:
        return int(round(88 + (trades - 100) * 0.05)) # 100-299 -> 88-98
    return 99


def rating_from_score(score, trades):
    trades = _safe_int(trades, 0)
    score = _safe_float(score, 0.0)

    if trades <= 0:
        return "SEM AMOSTRA"
    if trades < 10:
        return "AMOSTRA INSUFICIENTE"

    if score >= 95:
        return "S+"
    if score >= 90:
        return "S"
    if score >= 85:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "E"


def risk_bias_from_score(score, confidence, trades):
    trades = _safe_int(trades, 0)
    score = _safe_float(score, 0.0)
    confidence = _safe_float(confidence, 0.0)

    if trades <= 0:
        return "NO_SAMPLE"
    if trades < 10 or confidence < 40:
        return "WAIT_SAMPLE"
    if score >= 85 and confidence >= 70:
        return "INCREASE_GRADUAL"
    if score >= 70 and confidence >= 60:
        return "MAINTAIN"
    if score >= 55:
        return "REDUCE"
    return "PAUSE_OR_OBSERVE"


def _score_profit_factor(pf):
    pf = _safe_float(pf, 0.0)
    if pf <= 0:
        return 0
    if pf >= 3.0:
        return 100
    if pf >= 2.0:
        return 80 + (pf - 2.0) * 20
    if pf >= 1.5:
        return 65 + (pf - 1.5) * 30
    if pf >= 1.0:
        return 45 + (pf - 1.0) * 40
    return max(0, pf * 45)


def _score_expectancy(expectancy):
    expectancy = _safe_float(expectancy, 0.0)
    # expectancy em % por trade. +2% ou mais é excelente; -2% ou pior é péssimo.
    return clamp(50 + expectancy * 25, 0, 100)


def _score_win_rate(win_rate):
    win_rate = _safe_float(win_rate, 0.0)
    # 50% = neutro; 70%+ forte; 30%- fraco.
    return clamp(50 + (win_rate - 50) * 1.5, 0, 100)


def _score_pnl(pnl_total, trades):
    pnl_total = _safe_float(pnl_total, 0.0)
    trades = max(_safe_int(trades, 0), 1)
    pnl_avg = pnl_total / trades
    return clamp(50 + pnl_avg * 20, 0, 100)


def _score_giveback(avg_giveback):
    """Menor devolução é melhor."""
    avg_giveback = abs(_safe_float(avg_giveback, 0.0))
    if avg_giveback <= 0:
        return 70
    return clamp(100 - avg_giveback * 20, 0, 100)


def score_item(metrics):
    trades = _safe_int(metrics.get("trades"), 0)
    if trades <= 0:
        return 0

    pf = _safe_float(metrics.get("profit_factor_pct"), 0.0)
    expectancy = _safe_float(metrics.get("expectancy_pct"), 0.0)
    win_rate = _safe_float(metrics.get("win_rate_pct"), 0.0)
    pnl_total = _safe_float(metrics.get("pnl_total_pct"), 0.0)
    giveback = _safe_float(metrics.get("avg_giveback_pct"), 0.0)

    score = (
        _score_profit_factor(pf) * 0.30
        + _score_expectancy(expectancy) * 0.30
        + _score_win_rate(win_rate) * 0.20
        + _score_pnl(pnl_total, trades) * 0.10
        + _score_giveback(giveback) * 0.10
    )

    # Penaliza amostra pequena, mas sem zerar: qualidade aparente ≠ confiança.
    if trades < 5:
        score *= 0.55
    elif trades < 10:
        score *= 0.70
    elif trades < 30:
        score *= 0.85

    return int(round(clamp(score, 0, 100)))


def rate_item(metrics):
    trades = _safe_int(metrics.get("trades"), 0)
    score = score_item(metrics)
    confidence = confidence_for_trades(trades)
    sample_status = sample_status_for_trades(trades)

    return {
        "score_0_100": score,
        "rating": rating_from_score(score, trades),
        "confidence": confidence,
        "sample_status": sample_status,
        "risk_bias": risk_bias_from_score(score, confidence, trades),
    }
