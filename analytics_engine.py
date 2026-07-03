# ==========================================================
# CENTRAL QUANT
# ANALYTICS ENGINE
#
# Versão:
# 2026-07-03-ANALYTICS-V1
# ==========================================================

from collections import defaultdict

import history_manager


def _score_pf(pf):
    if pf >= 2.5:
        return 100
    if pf >= 2.0:
        return 90
    if pf >= 1.5:
        return 75
    if pf >= 1.2:
        return 60
    if pf >= 1.0:
        return 45
    return 20


def _score_wr(wr):
    if wr >= 70:
        return 100
    if wr >= 60:
        return 85
    if wr >= 50:
        return 70
    if wr >= 40:
        return 55
    return 25


def _score_expectancy(exp):
    if exp >= 3:
        return 100
    if exp >= 2:
        return 90
    if exp >= 1:
        return 75
    if exp >= 0:
        return 60
    return 20


def _score_sample(n):

    if n >= 200:
        return 100

    if n >= 100:
        return 90

    if n >= 50:
        return 75

    if n >= 30:
        return 60

    if n >= 20:
        return 45

    if n >= 10:
        return 30

    return 10


def analytics_score(stats):

    pf = stats.get("profit_factor_pct", 0)
    wr = stats.get("win_rate_pct", 0)
    pnl = stats.get("pnl_avg_pct", 0)
    trades = stats.get("trades", 0)

    score = (
        _score_pf(pf) * 0.35
        + _score_wr(wr) * 0.25
        + _score_expectancy(pnl) * 0.25
        + _score_sample(trades) * 0.15
    )

    return round(score, 1)


def recommendation(score):

    if score >= 90:
        return "AUMENTAR EXPOSIÇÃO"

    if score >= 75:
        return "MANTER"

    if score >= 60:
        return "OBSERVAR"

    if score >= 40:
        return "REDUZIR RISCO"

    return "PAUSAR"


def bot_ranking():

    analytics = history_manager.build_trade_record_analytics()

    ranking = []

    for bot, stats in analytics["by_bot"].items():

        score = analytics_score(stats)

        ranking.append({

            "bot": bot,

            "score": score,

            "recommendation": recommendation(score),

            **stats

        })

    ranking.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return {

        "ok": True,

        "bots": ranking,

        "generated_at": analytics["generated_at"]

    }