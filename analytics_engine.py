# ==========================================================
# CENTRAL QUANT
# ANALYTICS ENGINE
#
# Versão:
# 2026-07-03-ANALYTICS-V3
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


def diagnose_stats(stats):
    trades = int(stats.get("trades", 0) or 0)
    wr = float(stats.get("win_rate_pct", 0) or 0)
    pnl_total = float(stats.get("pnl_total_pct", 0) or 0)
    pnl_avg = float(stats.get("pnl_avg_pct", 0) or 0)
    tp50 = float(stats.get("tp50_hit_rate_pct", 0) or 0)
    mfe = float(stats.get("mfe_avg_pct", 0) or 0)
    mae = float(stats.get("mae_avg_pct", 0) or 0)
    giveback = float(stats.get("giveback_avg_pct", 0) or 0)

    strengths = []
    weaknesses = []
    notes = []

    if trades >= 20:
        strengths.append("Amostra operacional relevante")
    elif trades < 10:
        weaknesses.append("Amostra ainda insuficiente")

    if wr >= 55:
        strengths.append("Win rate elevado")
    elif trades >= 10 and wr < 35:
        weaknesses.append("Win rate baixo")

    if pnl_total >= 8:
        strengths.append("PnL acumulado forte")
    elif pnl_total > 0:
        strengths.append("PnL acumulado positivo")
    elif pnl_total < -3:
        weaknesses.append("PnL acumulado negativo")

    if pnl_avg > 0:
        strengths.append("Expectancy positiva por trade")
    elif trades >= 10 and pnl_avg < 0:
        weaknesses.append("Expectancy negativa por trade")

    if tp50 >= 55:
        strengths.append("Boa taxa de TP50")
    elif trades >= 10 and tp50 < 25:
        weaknesses.append("Baixa taxa de TP50")

    if mfe >= 3:
        strengths.append("Boa capacidade de gerar runners")
    elif trades >= 10 and mfe < 1:
        weaknesses.append("Baixo MFE médio")

    if giveback >= 3:
        weaknesses.append("Giveback elevado")
    elif giveback > 0 and giveback <= 1.5:
        strengths.append("Boa retenção de lucro")

    if mae < -1.5:
        weaknesses.append("MAE elevado contra a posição")

    if not strengths:
        notes.append("Sem pontos fortes estatísticos claros ainda")

    if not weaknesses:
        notes.append("Sem fragilidade crítica detectada na amostra atual")

    return {
        "strengths": strengths,
        "weaknesses": weaknesses,
        "notes": notes,
    }


def bot_ranking():
    analytics = history_manager.build_trade_record_analytics()
    ranking = []

    for bot, stats in analytics.get("by_bot", {}).items():
        score = analytics_score(stats)
        diagnosis = diagnose_stats(stats)

        item = {
            "bot": bot,
            "score": score,
            "confidence": confidence_label(int(stats.get("trades", 0) or 0)),
            "recommendation": recommendation(score, stats),
            "strengths": diagnosis.get("strengths", []),
            "weaknesses": diagnosis.get("weaknesses", []),
            "notes": diagnosis.get("notes", []),
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
        "version": "2026-07-03-ANALYTICS-V3",
        "generated_at": analytics.get("generated_at"),
        "bots": ranking,
    }


def setup_ranking():
    analytics = history_manager.build_trade_record_analytics()

    ranking = []

    for setup, stats in analytics.get("by_setup", {}).items():

        score = analytics_score(stats)
        diagnosis = diagnose_stats(stats)

        item = {
            "setup": setup,
            "score": score,
            "confidence": confidence_label(
                int(stats.get("trades", 0) or 0)
            ),
            "recommendation": recommendation(score, stats),
            "strengths": diagnosis.get("strengths", []),
            "weaknesses": diagnosis.get("weaknesses", []),
            "notes": diagnosis.get("notes", []),
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
        "version": "2026-07-03-ANALYTICS-V3",
        "generated_at": analytics.get("generated_at"),
        "setups": ranking,
    }


    def portfolio_advisor():
        bots = bot_ranking().get("bots", [])
        setups = setup_ranking().get("setups", [])

        core = []
        observe = []
        insufficient = []
        reduce = []
        alerts = []

        for item in bots:
            name = item.get("bot")
            rec = item.get("recommendation")
            conf = item.get("confidence")
            score = item.get("score", 0)
            pnl = item.get("pnl_total_pct", 0)
            giveback = item.get("giveback_avg_pct", 0)

            row = {
                "name": name,
                "score": score,
                "confidence": conf,
                "recommendation": rec,
                "pnl_total_pct": pnl,
                "trades": item.get("trades"),
            }

            if conf in {"MÉDIA", "ALTA"} and pnl > 0 and score >= 65:
                core.append(row)
            elif conf == "AMOSTRA INSUFICIENTE":
                insufficient.append(row)
            elif pnl < 0 or score < 35:
                reduce.append(row)
            else:
                observe.append(row)

            if giveback and giveback >= 3:
                alerts.append({
                    "type": "GIVEBACK_ELEVADO",
                    "name": name,
                    "giveback_avg_pct": giveback,
                })

        setup_core = []
        setup_watch = []
        setup_reduce = []

        for item in setups:
            name = item.get("setup")
            conf = item.get("confidence")
            score = item.get("score", 0)
            pnl = item.get("pnl_total_pct", 0)

            row = {
                "name": name,
                "score": score,
                "confidence": conf,
                "recommendation": item.get("recommendation"),
                "pnl_total_pct": pnl,
                "trades": item.get("trades"),
            }

            if conf in {"MÉDIA", "ALTA"} and pnl > 0 and score >= 65:
                setup_core.append(row)
            elif pnl < 0 and score < 40:
                setup_reduce.append(row)
            else:
                setup_watch.append(row)

        return {
            "ok": True,
            "version": "2026-07-03-PORTFOLIO-ADVISOR-V1",
            "generated_at": bot_ranking().get("generated_at"),
            "portfolio": {
                "core_bots": core,
                "observe_bots": observe,
                "insufficient_sample_bots": insufficient,
                "reduce_bots": reduce,
                "core_setups": setup_core,
                "watch_setups": setup_watch,
                "reduce_setups": setup_reduce,
                "alerts": alerts,
            },
        }