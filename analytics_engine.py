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
    bot_payload = bot_ranking()
    setup_payload = setup_ranking()

    bots = bot_payload.get("bots", [])
    setups = setup_payload.get("setups", [])

    core = []
    observe = []
    insufficient = []
    reduce = []
    alerts = []
    general_recommendations = []
    weekly_priorities = []

    for item in bots:
        name = item.get("bot")
        rec = item.get("recommendation")
        conf = item.get("confidence")
        score = item.get("score", 0) or 0
        pnl = item.get("pnl_total_pct", 0) or 0
        giveback = item.get("giveback_avg_pct", 0) or 0
        trades = item.get("trades", 0) or 0

        row = {
            "name": name,
            "score": score,
            "confidence": conf,
            "recommendation": rec,
            "pnl_total_pct": pnl,
            "trades": trades,
        }

        if conf in {"MÉDIA", "ALTA"} and pnl > 0 and score >= 65:
            core.append(row)
            general_recommendations.append({
                "name": name,
                "action": "AUMENTAR COM CAUTELA",
                "reason": "Robô com score forte, PnL positivo e confiança operacional relevante.",
            })

        elif conf == "AMOSTRA INSUFICIENTE":
            insufficient.append(row)

            if pnl > 0 and score >= 40:
                general_recommendations.append({
                    "name": name,
                    "action": "OBSERVAR POSITIVO",
                    "reason": "Resultado inicial positivo, mas ainda sem amostra suficiente.",
                })
            else:
                general_recommendations.append({
                    "name": name,
                    "action": "NÃO AUMENTAR",
                    "reason": "Amostra insuficiente ou desempenho ainda fraco.",
                })

        elif pnl < 0 or score < 35:
            reduce.append(row)
            general_recommendations.append({
                "name": name,
                "action": "REDUZIR / NÃO AUMENTAR",
                "reason": "PnL negativo ou score abaixo do mínimo desejado.",
            })

        else:
            observe.append(row)
            general_recommendations.append({
                "name": name,
                "action": "MANTER EM OBSERVAÇÃO",
                "reason": "Ainda não atende critérios claros para núcleo ou redução.",
            })

        if giveback and giveback >= 3:
            alerts.append({
                "type": "GIVEBACK_ELEVADO",
                "name": name,
                "giveback_avg_pct": giveback,
            })

            weekly_priorities.append(
                f"Reduzir giveback médio do {name}."
            )

        if trades < 20:
            weekly_priorities.append(
                f"Aguardar mais trades do {name} antes de promover para núcleo."
            )

    setup_core = []
    setup_watch = []
    setup_reduce = []

    for item in setups:
        name = item.get("setup")
        conf = item.get("confidence")
        score = item.get("score", 0) or 0
        pnl = item.get("pnl_total_pct", 0) or 0

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

    if not weekly_priorities:
        weekly_priorities.append("Manter coleta de dados e acompanhar evolução dos rankings.")

    return {
        "ok": True,
        "version": "2026-07-03-PORTFOLIO-ADVISOR-V2",
        "generated_at": bot_payload.get("generated_at"),
        "portfolio": {
            "core_bots": core,
            "observe_bots": observe,
            "insufficient_sample_bots": insufficient,
            "reduce_bots": reduce,
            "core_setups": setup_core,
            "watch_setups": setup_watch,
            "reduce_setups": setup_reduce,
            "alerts": alerts,
            "general_recommendations": general_recommendations,
            "weekly_priorities": list(dict.fromkeys(weekly_priorities)),
        },
    }


def decision_engine_observation():
    payload = portfolio_advisor()
    p = payload.get("portfolio", {})

    decisions = []

    core_names = {item.get("name") for item in p.get("core_bots", [])}
    insufficient_names = {item.get("name") for item in p.get("insufficient_sample_bots", [])}
    reduce_names = {item.get("name") for item in p.get("reduce_bots", [])}

    recs = p.get("general_recommendations", [])

    for rec in recs:
        name = rec.get("name")
        action = rec.get("action")

        if name in core_names:
            decision = "ALLOW"
            reason = "Robô faz parte do núcleo principal."
        elif action == "OBSERVAR POSITIVO":
            decision = "WAIT"
            reason = "Resultado inicial positivo, mas ainda com amostra insuficiente."
        elif name in reduce_names or action in {"NÃO AUMENTAR", "REDUZIR / NÃO AUMENTAR"}:
            decision = "BLOCK_OBSERVATION"
            reason = "Robô ainda não deve receber aumento de exposição."
        elif name in insufficient_names:
            decision = "WAIT"
            reason = "Amostra insuficiente para decisão operacional forte."
        else:
            decision = "OBSERVE"
            reason = "Sem sinal claro para aumentar ou reduzir."

        decisions.append({
            "name": name,
            "decision": decision,
            "reason": reason,
            "source_action": action,
        })

    return {
        "ok": True,
        "version": "2026-07-03-DECISION-ENGINE-V1-OBSERVATION",
        "generated_at": payload.get("generated_at"),
        "mode": "OBSERVATION_ONLY",
        "decisions": decisions,
    }


def portfolio_weights():
    payload = portfolio_advisor()
    p = payload.get("portfolio", {})

    bots = []

    all_bots = []
    all_bots += p.get("core_bots", [])
    all_bots += p.get("observe_bots", [])
    all_bots += p.get("insufficient_sample_bots", [])
    all_bots += p.get("reduce_bots", [])

    confidence_factor = {
        "ALTA": 1.30,
        "MÉDIA": 1.10,
        "BAIXA": 0.90,
        "AMOSTRA INSUFICIENTE": 0.65,
    }

    action_factor = {
        "AUMENTAR COM CAUTELA": 1.25,
        "OBSERVAR POSITIVO": 0.85,
        "MANTER EM OBSERVAÇÃO": 0.70,
        "NÃO AUMENTAR": 0.35,
        "REDUZIR / NÃO AUMENTAR": 0.20,
    }

    rec_map = {
        item.get("name"): item
        for item in p.get("general_recommendations", [])
    }

    for item in all_bots:
        name = item.get("name")
        score = item.get("score", 0) or 0
        pnl = item.get("pnl_total_pct", 0) or 0
        conf = item.get("confidence")
        trades = item.get("trades", 0) or 0

        rec = rec_map.get(name, {})
        action = rec.get("action")

        cf = confidence_factor.get(conf, 0.75)
        af = action_factor.get(action, 0.50)

        pnl_factor = 1.0
        if pnl > 10:
            pnl_factor = 1.25
        elif pnl > 3:
            pnl_factor = 1.10
        elif pnl > 0:
            pnl_factor = 1.00
        elif pnl > -3:
            pnl_factor = 0.60
        else:
            pnl_factor = 0.35

        sample_factor = 1.0
        if trades < 5:
            sample_factor = 0.55
        elif trades < 10:
            sample_factor = 0.70
        elif trades < 20:
            sample_factor = 0.85

        raw_strength = score * cf * af * pnl_factor * sample_factor

        if raw_strength < 1:
            raw_strength = 1

        bots.append({
            "name": name,
            "score": score,
            "confidence": conf,
            "pnl_total_pct": pnl,
            "trades": trades,
            "source_action": action,
            "raw_strength": round(raw_strength, 4),
        })

    total_strength = sum(item.get("raw_strength", 0) for item in bots)

    weighted = []
    for item in bots:
        if total_strength > 0:
            weight = item.get("raw_strength", 0) / total_strength * 100
        else:
            weight = 0

        item["suggested_weight_pct"] = round(weight, 2)
        weighted.append(item)

    weighted = sorted(
        weighted,
        key=lambda x: x.get("suggested_weight_pct", 0),
        reverse=True,
    )

    return {
        "ok": True,
        "version": "2026-07-03-PORTFOLIO-WEIGHTS-V1",
        "generated_at": payload.get("generated_at"),
        "mode": "OBSERVATION_ONLY",
        "weights": weighted,
        "notes": [
            "Pesos calculados apenas para observação.",
            "Ainda não interfere na execução real.",
            "Baseado em score, confiança, PnL, amostra e recomendação geral.",
        ],
    }    