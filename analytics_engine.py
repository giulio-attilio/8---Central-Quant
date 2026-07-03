# ==========================================================
# CENTRAL QUANT
# ANALYTICS ENGINE
#
# Versão:
# 2026-07-03-ANALYTICS-V2
# ==========================================================

import history_manager


def _score_win_rate(wr):
    if wr >= 65:
        return 100
    if wr >= 55:
        return 85
    if wr >= 45:
        return 70
    if wr >= 35:
        return 50
    if wr >= 25:
        return 35
    return 15


def _score_pnl_avg(pnl_avg):
    if pnl_avg >= 1.0:
        return 100
    if pnl_avg >= 0.5:
        return 85
    if pnl_avg >= 0.25:
        return 70
    if pnl_avg > 0:
        return 55
    if pnl_avg > -0.25:
        return 35
    return 10


def _score_pnl_total(pnl_total):
    if pnl_total >= 15:
        return 100
    if pnl_total >= 8:
        return 85
    if pnl_total >= 3:
        return 70
    if pnl_total > 0:
        return 55
    if pnl_total > -3:
        return 35
    return 10


def _score_tp50(rate):
    if rate >= 70:
        return 100
    if rate >= 55:
        return 85
    if rate >= 40:
        return 70
    if rate >= 25:
        return 45
    if rate > 0:
        return 25
    return 10


def _score_sample(n):
    if n >= 100:
        return 100
    if n >= 50:
        return 85
    if n >= 30:
        return 70
    if n >= 20:
        return 60
    if n >= 10:
        return 45
    if n >= 5:
        return 30
    return 15


def confidence_label(trades):
    if trades >= 50:
        return "ALTA"
    if trades >= 20:
        return "MÉDIA"
    if trades >= 10:
        return "BAIXA"
    return "AMOSTRA INSUFICIENTE"


def analytics_score(stats):
    wr = float(stats.get("win_rate_pct", 0) or 0)
    pnl_avg = float(stats.get("pnl_avg_pct", 0) or 0)
    pnl_total = float(stats.get("pnl_total_pct", 0) or 0)
    tp50 = float(stats.get("tp50_hit_rate_pct", 0) or 0)
    trades = int(stats.get("trades", 0) or 0)

    score = (
        _score_win_rate(wr) * 0.25
        + _score_pnl_avg(pnl_avg) * 0.25
        + _score_pnl_total(pnl_total) * 0.25
        + _score_tp50(tp50) * 0.15
        + _score_sample(trades) * 0.10
    )

    return round(score, 1)


def recommendation(score, stats):
    trades = int(stats.get("trades", 0) or 0)
    pnl_total = float(stats.get("pnl_total_pct", 0) or 0)
    pnl_avg = float(stats.get("pnl_avg_pct", 0) or 0)
    wr = float(stats.get("win_rate_pct", 0) or 0)

    if trades < 5:
        return "AGUARDAR AMOSTRA"

    if trades < 10:
        if pnl_total > 0 and pnl_avg > 0:
            return "OBSERVAR POSITIVO"
        return "OBSERVAR"

    if score >= 80 and pnl_total > 0:
        return "AUMENTAR GRADUALMENTE"

    if score >= 65 and pnl_total > 0:
        return "MANTER"

    if score >= 50 and pnl_total > 0:
        return "OBSERVAR"

    if pnl_total < 0 and wr < 35:
        return "REDUZIR RISCO"

    if pnl_total < -5:
        return "PAUSAR OU REDUZIR"

    return "OBSERVAR"


def bot_ranking():
    analytics = history_manager.build_trade_record_analytics()
    ranking = []

    for bot, stats in analytics.get("by_bot", {}).items():
        score = analytics_score(stats)

        item = {
            "bot": bot,
            "score": score,
            "confidence": confidence_label(int(stats.get("trades", 0) or 0)),
            "recommendation": recommendation(score, stats),
            **stats,
        }

        ranking.append(item)

    ranking.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("pnl_total_pct", 0),
            x.get("trades", 0),
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "version": "2026-07-03-ANALYTICS-V2",
        "generated_at": analytics.get("generated_at"),
        "bots": ranking,
    }