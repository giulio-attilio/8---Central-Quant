# STRATEGIC ADVISOR V1 — CENTRAL QUANT
# Versão: 2026-07-04-STRATEGIC-ADVISOR-V1
#
# Objetivo:
# - Transformar os sinais executivos da Central Quant em recomendações estratégicas operacionais.
# - Não executa trades, não altera risco, não altera pesos e não modifica estado.
# - Foi desenhado para uso assistido: o CEO não precisa decidir lendo relatórios; o assistente consulta
#   comandos técnicos da Central e devolve uma ação prática.

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

VERSION = "2026-07-04-STRATEGIC-ADVISOR-V1"
TIMEZONE_BR = timezone(timedelta(hours=-3))


def _now_br() -> str:
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    try:
        return max(low, min(high, float(value)))
    except Exception:
        return low


def _label_for_priority(score: float) -> str:
    score = _safe_float(score)
    if score >= 85:
        return "EXPANSÃO_DISCIPLINADA"
    if score >= 75:
        return "OTIMIZAÇÃO_CONTROLADA"
    if score >= 65:
        return "OPERAÇÃO_NORMAL_ASSISTIDA"
    if score >= 50:
        return "MODO_DEFENSIVO_ASSISTIDO"
    return "INVESTIGAÇÃO_PRIORITÁRIA"


def _make_recommendation(priority: str, category: str, title: str, rationale: str, action: str, commands: Optional[List[str]] = None, blocks_expansion: bool = False) -> Dict[str, Any]:
    return {
        "priority": priority,
        "category": category,
        "title": title,
        "rationale": rationale,
        "action": action,
        "technical_commands": commands or [],
        "human_decision_required": False,
        "assistant_decision_required": True,
        "blocks_expansion": bool(blocks_expansion),
    }


def _count_alerts(executive_alerts: Dict[str, Any]) -> Dict[str, int]:
    critical = 0
    warning = 0
    recovery = _safe_int((executive_alerts or {}).get("resolved_count"), 0)
    for alert in (executive_alerts or {}).get("alerts") or []:
        level = str(alert.get("level") or "").upper()
        if level == "CRITICAL":
            critical += 1
        elif level == "WARNING":
            warning += 1
    return {"critical": critical, "warning": warning, "recovery": recovery}


def _pipeline_health(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    components = (((pipeline or {}).get("pipeline") or {}).get("components") or {})
    total = len(components)
    ok_count = 0
    failed = []
    for name, comp in components.items():
        if bool((comp or {}).get("ok")):
            ok_count += 1
        else:
            failed.append(name)
    status = str((pipeline or {}).get("status") or "UNKNOWN").upper()
    return {"status": status, "total": total, "ok_count": ok_count, "failed": failed}


def _dominant_exposure(exposure: Dict[str, Any]) -> Dict[str, Any]:
    total = _safe_int((exposure or {}).get("total_positions_open"), 0)
    longs = _safe_int((exposure or {}).get("long_positions_open"), 0)
    shorts = _safe_int((exposure or {}).get("short_positions_open"), 0)
    if total <= 0:
        return {"total": 0, "long": 0, "short": 0, "dominant_side": "NONE", "dominant_pct": 0.0}
    dominant_side = "LONG" if longs >= shorts else "SHORT"
    dominant_pct = max(longs, shorts) / max(total, 1) * 100.0
    return {"total": total, "long": longs, "short": shorts, "dominant_side": dominant_side, "dominant_pct": round(dominant_pct, 2)}


def build_strategic_advisor(
    ceo_confidence: Optional[Dict[str, Any]] = None,
    executive_alerts: Optional[Dict[str, Any]] = None,
    pipeline: Optional[Dict[str, Any]] = None,
    exposure: Optional[Dict[str, Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
    monthly_stats: Optional[Dict[str, Any]] = None,
    portfolio_advisor: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ceo_confidence = ceo_confidence or {}
    executive_alerts = executive_alerts or {}
    pipeline = pipeline or {}
    exposure = exposure or {}
    memory = memory or {}
    monthly_stats = monthly_stats or {}
    portfolio_advisor = portfolio_advisor or {}
    extra = extra or {}

    confidence_score = _safe_float(ceo_confidence.get("score"), 50.0)
    confidence_label = str(ceo_confidence.get("label") or "UNKNOWN")
    confidence_action = str(ceo_confidence.get("action") or "UNKNOWN")
    alert_counts = _count_alerts(executive_alerts)
    pipe = _pipeline_health(pipeline)
    exp = _dominant_exposure(exposure)
    memory_pct = _safe_float((memory or {}).get("usage_pct"), 0.0)

    adaptive = (pipeline or {}).get("adaptive") or {}
    adaptive_confidence = _safe_float(adaptive.get("confidence"), 0.0)
    adaptive_trades = _safe_int(adaptive.get("trades"), 0)
    adaptive_action = str(adaptive.get("recommended_action") or "WAIT_SAMPLE").upper()
    positions = (pipeline or {}).get("positions") or {}
    pending_outcome = _safe_int(positions.get("pending_outcome"), 0)

    monthly_trades = _safe_int(monthly_stats.get("trades") or monthly_stats.get("closed_trades"), 0)
    monthly_pnl = _safe_float(monthly_stats.get("pnl_total_pct"), 0.0)
    monthly_pf = _safe_float(monthly_stats.get("profit_factor_pct") or monthly_stats.get("profit_factor"), 0.0)

    recommendations: List[Dict[str, Any]] = []
    strengths: List[str] = []
    risks: List[str] = []
    next_commands: List[str] = []

    # 1) Alertas e pipeline têm prioridade máxima.
    if alert_counts["critical"] > 0:
        risks.append(f"{alert_counts['critical']} alerta(s) crítico(s) ativo(s).")
        recommendations.append(_make_recommendation(
            "P0", "ALERTS", "Bloquear expansão e investigar alertas críticos",
            "Há alerta crítico ativo no Executive Alert Manager.",
            "Não aumentar risco, não liberar execução real e consultar detalhes técnicos antes de qualquer evolução.",
            ["/alerts", "/alertscheck", "/execution/pipeline/status"],
            blocks_expansion=True,
        ))
    else:
        strengths.append("Sem alertas críticos executivos ativos.")

    if pipe["failed"]:
        risks.append(f"Componentes com falha: {', '.join(pipe['failed'][:5])}.")
        recommendations.append(_make_recommendation(
            "P0", "PIPELINE", "Corrigir pipeline antes de evoluir risco",
            "Um ou mais componentes essenciais não estão saudáveis.",
            "Priorizar diagnóstico do pipeline e pausar qualquer expansão até normalizar.",
            ["/execution/pipeline/status", "/health", "/diagnostico"],
            blocks_expansion=True,
        ))
    elif pipe["total"] and pipe["ok_count"] == pipe["total"]:
        strengths.append(f"Pipeline saudável: {pipe['ok_count']}/{pipe['total']} componentes OK.")

    # 2) Risco e exposição.
    if exp["dominant_pct"] >= 85:
        risks.append(f"Concentração direcional muito alta: {exp['dominant_side']} {exp['dominant_pct']}%.")
        recommendations.append(_make_recommendation(
            "P1", "RISK", "Reduzir pressão direcional dominante",
            "A concentração direcional está em zona alta e pode distorcer o risco global.",
            f"Evitar novas entradas {exp['dominant_side']} até concentração cair abaixo de 75%.",
            ["/risk", "/heat", "/traderegistry/report"],
            blocks_expansion=True,
        ))
    elif exp["dominant_pct"] >= 75:
        risks.append(f"Concentração direcional elevada: {exp['dominant_side']} {exp['dominant_pct']}%.")
        recommendations.append(_make_recommendation(
            "P2", "RISK", "Monitorar concentração direcional",
            "A concentração ainda não exige bloqueio total, mas limita expansão agressiva.",
            f"Manter operação normal, mas evitar aumento agressivo de exposição {exp['dominant_side']}.",
            ["/risk", "/heat"],
            blocks_expansion=False,
        ))
    else:
        strengths.append("Concentração direcional aceitável.")

    if memory_pct >= 90:
        risks.append(f"Memória elevada: {memory_pct:.1f}%.")
        recommendations.append(_make_recommendation(
            "P1", "SYSTEM", "Reduzir risco operacional por memória",
            "Memória acima da zona saudável aumenta chance de instabilidade/restart.",
            "Rodar diagnóstico de memória; considerar GC, otimização ou separação de serviços se persistir.",
            ["/memory", "/memory/gc", "/health"],
            blocks_expansion=True,
        ))
    elif memory_pct > 0:
        strengths.append(f"Memória em zona controlada: {memory_pct:.1f}%.")

    # 3) Learning e amostra.
    if pending_outcome >= 8:
        risks.append(f"Outcome backlog crítico: {pending_outcome}.")
        recommendations.append(_make_recommendation(
            "P1", "LEARNING", "Normalizar backlog de outcomes",
            "A fila de outcomes pendentes compromete o ciclo de aprendizado.",
            "Rodar avaliação de outcomes e revisar lifecycle antes de adaptar pesos.",
            ["/outcome/evaluate", "/outcome/stats", "/paper/lifecycle/positions"],
            blocks_expansion=True,
        ))
    elif pending_outcome >= 3:
        risks.append(f"Outcome backlog em atenção: {pending_outcome}.")
        recommendations.append(_make_recommendation(
            "P2", "LEARNING", "Acompanhar outcomes pendentes",
            "Há outcomes suficientes para acompanhamento, mas ainda sem emergência.",
            "Verificar fila de outcomes no próximo ciclo técnico.",
            ["/outcome/stats", "/outcome/evaluate"],
            blocks_expansion=False,
        ))
    else:
        strengths.append("Outcome backlog controlado.")

    if adaptive_trades < 20 or adaptive_confidence < 50:
        risks.append("Learning ainda sem confiança estatística robusta.")
        recommendations.append(_make_recommendation(
            "P2", "LEARNING", "Priorizar coleta de amostra estatística",
            f"Adaptive possui {adaptive_trades} trades e confiança {adaptive_confidence:.1f}%.",
            "Não aumentar risco estrutural até a amostra crescer; manter coleta e análise diária.",
            ["/adaptive/weights", "/outcome/stats", "/history"],
            blocks_expansion=False,
        ))
    else:
        strengths.append(f"Learning com amostra em evolução: {adaptive_trades} trades, confiança {adaptive_confidence:.1f}%.")

    # 4) Performance mensal.
    if monthly_trades <= 0:
        risks.append("Sem amostra mensal de trades encerrados.")
        recommendations.append(_make_recommendation(
            "P3", "PERFORMANCE", "Aguardar amostra mensal antes de decisões de capital",
            "Sem trades encerrados no mês consolidado, performance não deve comandar aumento de capital.",
            "Usar o mês atual apenas para coleta e auditoria; não extrapolar resultado.",
            ["/monthly", "/history", "/analytics"],
            blocks_expansion=False,
        ))
    elif monthly_pnl > 0 and monthly_pf > 1:
        strengths.append(f"Performance mensal positiva: PnL {monthly_pnl:.2f}%, PF {monthly_pf:.2f}.")
    elif monthly_trades > 0:
        risks.append(f"Performance mensal ainda fraca/neutra: PnL {monthly_pnl:.2f}%, PF {monthly_pf:.2f}.")

    # Diretiva principal.
    expansion_blocked = any(r.get("blocks_expansion") for r in recommendations)
    if alert_counts["critical"] or pipe["failed"]:
        primary_directive = "INVESTIGAR_ANTES_DE_OPERAR"
    elif confidence_score >= 85 and not expansion_blocked and adaptive_confidence >= 60 and monthly_trades >= 20:
        primary_directive = "OTIMIZAR_E_CONSIDERAR_EXPANSÃO_GRADUAL"
    elif confidence_score >= 70:
        primary_directive = "OPERAR_NORMAL_COM_MONITORAMENTO_ASSISTIDO"
    elif confidence_score >= 55:
        primary_directive = "MODO_DEFENSIVO_COM_COLETA_DE_DADOS"
    else:
        primary_directive = "PAUSAR_EXPANSÃO_E_DIAGNOSTICAR"

    if not recommendations:
        recommendations.append(_make_recommendation(
            "P3", "NORMAL", "Manter operação assistida",
            "Nenhum bloqueio estratégico foi detectado.",
            "Manter operação normal e continuar coleta de dados para aprendizado.",
            ["/daily", "/ceoconfidence", "/alertscheck"],
            blocks_expansion=False,
        ))

    # Comandos técnicos consolidados para o assistente usar quando precisar decidir próximo passo.
    for rec in recommendations:
        for cmd in rec.get("technical_commands") or []:
            if cmd not in next_commands:
                next_commands.append(cmd)

    if "/strategy" not in next_commands:
        next_commands.insert(0, "/strategy")
    if "/ceoconfidence" not in next_commands:
        next_commands.insert(1, "/ceoconfidence")
    if "/alertscheck" not in next_commands:
        next_commands.insert(2, "/alertscheck")

    return {
        "ok": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": "ASSISTED_DECISION_ENGINE",
        "human_decision_required": False,
        "assistant_decision_required": True,
        "primary_directive": primary_directive,
        "strategic_label": _label_for_priority(confidence_score),
        "ceo_confidence_score": round(confidence_score, 2),
        "ceo_confidence_label": confidence_label,
        "ceo_confidence_action": confidence_action,
        "expansion_blocked": bool(expansion_blocked),
        "recommendations": recommendations[:10],
        "top_recommendation": recommendations[0] if recommendations else None,
        "strengths": strengths[:12],
        "risks": risks[:12],
        "next_technical_commands": next_commands[:12],
        "context": {
            "alerts": alert_counts,
            "pipeline": pipe,
            "exposure": exp,
            "memory_pct": round(memory_pct, 2),
            "adaptive": {
                "confidence": adaptive_confidence,
                "trades": adaptive_trades,
                "action": adaptive_action,
                "pending_outcome": pending_outcome,
            },
            "monthly": {
                "trades": monthly_trades,
                "pnl_total_pct": monthly_pnl,
                "profit_factor": monthly_pf,
            },
            "extra": extra,
        },
        "operational_note": "Este módulo não pede decisão humana. Ele organiza os comandos técnicos para o assistente decidir a próxima ação junto à Central Quant.",
    }


def build_strategic_advisor_text(payload: Dict[str, Any], compact: bool = False) -> str:
    payload = payload or {}
    lines: List[str] = [
        "🧭 STRATEGIC ADVISOR — CENTRAL QUANT V1",
        f"Data/hora: {payload.get('generated_at') or _now_br()}",
        "",
        f"Diretiva principal: {payload.get('primary_directive', 'UNKNOWN')}",
        f"Classificação estratégica: {payload.get('strategic_label', 'UNKNOWN')}",
        f"CEO Confidence: {payload.get('ceo_confidence_score', 0)}/100 — {payload.get('ceo_confidence_label', 'UNKNOWN')}",
        f"Bloqueia expansão: {'SIM' if payload.get('expansion_blocked') else 'NÃO'}",
        "Modo: ASSISTED_DECISION_ENGINE",
        "Decisão humana necessária: NÃO",
        "",
    ]

    top = payload.get("top_recommendation") or {}
    if top:
        lines += [
            "Recomendação principal:",
            f"{top.get('priority')} | {top.get('category')} | {top.get('title')}",
            f"Ação: {top.get('action')}",
            f"Motivo: {top.get('rationale')}",
            "",
        ]

    recs = payload.get("recommendations") or []
    if recs and not compact:
        lines.append("Fila estratégica:")
        for rec in recs[:6]:
            lines.append(f"- {rec.get('priority')} | {rec.get('category')}: {rec.get('title')}")
            lines.append(f"  Ação: {rec.get('action')}")
        lines.append("")

    strengths = payload.get("strengths") or []
    risks = payload.get("risks") or []
    if strengths:
        lines.append("Forças:")
        for item in strengths[:6]:
            lines.append(f"- {item}")
        lines.append("")
    if risks:
        lines.append("Pontos de atenção:")
        for item in risks[:8]:
            lines.append(f"- {item}")
        lines.append("")

    cmds = payload.get("next_technical_commands") or []
    if cmds:
        lines.append("Comandos técnicos sugeridos para análise assistida:")
        for cmd in cmds[:8]:
            lines.append(f"- {cmd}")
        lines.append("")

    lines += [
        "Observação:",
        payload.get("operational_note") or "Este módulo é consultivo e não altera execução automaticamente.",
    ]
    return "\n".join(lines)
