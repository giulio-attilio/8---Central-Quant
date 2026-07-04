# DECISION PACK V1 — CENTRAL QUANT
# Versão: 2026-07-04-DECISION-PACK-V1
#
# Objetivo:
# - Consolidar em um pacote técnico curto os dados que o assistente precisa
#   para decidir a próxima ação junto à Central Quant.
# - Não exige decisão humana e não altera execução, lote, risco ou robôs.
# - Serve como comando operacional de leitura: /decisionpack.

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

VERSION = "2026-07-04-DECISION-PACK-V1"
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


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _first(items: Any, default: Any = None) -> Any:
    if isinstance(items, list) and items:
        return items[0]
    return default


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _confidence_score(ceo_confidence: Dict[str, Any]) -> float:
    return _safe_float(ceo_confidence.get("score"), 0.0)


def _confidence_label(ceo_confidence: Dict[str, Any]) -> str:
    return str(ceo_confidence.get("label") or "N/A")


def _strategy_directive(strategy: Dict[str, Any]) -> str:
    return str(strategy.get("directive") or strategy.get("main_directive") or "N/A")


def _strategy_classification(strategy: Dict[str, Any]) -> str:
    return str(strategy.get("classification") or strategy.get("strategic_classification") or "N/A")


def _strategy_blocks_expansion(strategy: Dict[str, Any]) -> bool:
    return bool(strategy.get("blocks_expansion") or strategy.get("block_expansion") or False)


def _main_recommendation(strategy: Dict[str, Any]) -> Dict[str, Any]:
    rec = strategy.get("main_recommendation")
    if isinstance(rec, dict):
        return rec
    queue = strategy.get("queue") or strategy.get("strategic_queue") or []
    if isinstance(queue, list) and queue and isinstance(queue[0], dict):
        return queue[0]
    return {}


def _pipeline_components_ok(pipeline: Dict[str, Any]) -> str:
    components = (((pipeline.get("pipeline") or {}).get("components")) or {})
    if not isinstance(components, dict) or not components:
        return "N/A"
    ok_count = 0
    total = 0
    for comp in components.values():
        if isinstance(comp, dict):
            total += 1
            if comp.get("ok"):
                ok_count += 1
    return f"{ok_count}/{total}" if total else "N/A"


def _side_concentration(exposure: Dict[str, Any]) -> Dict[str, Any]:
    total = _safe_int(exposure.get("total_positions_open"), 0)
    long_pos = _safe_int(exposure.get("long_positions_open"), 0)
    short_pos = _safe_int(exposure.get("short_positions_open"), 0)
    dominant = "LONG" if long_pos >= short_pos else "SHORT"
    dominant_qty = max(long_pos, short_pos)
    pct = round((dominant_qty / total) * 100, 2) if total else 0.0
    return {"total": total, "long": long_pos, "short": short_pos, "dominant_side": dominant, "dominant_pct": pct}


def _extract_alert_counts(executive_alerts: Dict[str, Any]) -> Dict[str, int]:
    alerts = _list(executive_alerts.get("alerts"))
    critical = 0
    warning = 0
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        level = str(alert.get("level") or "").upper()
        if level == "CRITICAL":
            critical += 1
        elif level == "WARNING":
            warning += 1
    return {
        "active": _safe_int(executive_alerts.get("alerts_count"), len(alerts)),
        "to_notify": _safe_int(executive_alerts.get("alerts_to_notify_count"), 0),
        "critical": critical,
        "warning": warning,
        "resolved": _safe_int(executive_alerts.get("resolved_count"), 0),
    }


def _technical_commands(payload: Dict[str, Any]) -> List[str]:
    commands = ["/decisionpack", "/strategy", "/ceoconfidence", "/alertscheck"]
    risks = payload.get("risk_flags") or []
    if any("concentração" in str(x).lower() or "concentracao" in str(x).lower() for x in risks):
        commands += ["/risk", "/heat"]
    if any("learning" in str(x).lower() or "amostra" in str(x).lower() for x in risks):
        commands += ["/adaptive/weights", "/outcome/stats", "/history"]
    return list(dict.fromkeys(commands))


def build_decision_pack(
    *,
    ceo_confidence: Optional[Dict[str, Any]] = None,
    strategic_advisor: Optional[Dict[str, Any]] = None,
    executive_alerts: Optional[Dict[str, Any]] = None,
    pipeline: Optional[Dict[str, Any]] = None,
    exposure: Optional[Dict[str, Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
    adaptive: Optional[Dict[str, Any]] = None,
    outcome: Optional[Dict[str, Any]] = None,
    monthly_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ceo_confidence = _dict(ceo_confidence)
    strategic_advisor = _dict(strategic_advisor)
    executive_alerts = _dict(executive_alerts)
    pipeline = _dict(pipeline)
    exposure = _dict(exposure)
    memory = _dict(memory)
    adaptive = _dict(adaptive or pipeline.get("adaptive"))
    outcome = _dict(outcome)
    monthly_stats = _dict(monthly_stats)

    confidence = _confidence_score(ceo_confidence)
    confidence_label = _confidence_label(ceo_confidence)
    alert_counts = _extract_alert_counts(executive_alerts)
    side = _side_concentration(exposure)
    memory_pct = _safe_float(memory.get("usage_pct"), _safe_float(memory.get("memory_pct"), 0.0))
    adaptive_confidence = _safe_float(adaptive.get("confidence"), 0.0)
    adaptive_action = str(adaptive.get("recommended_action") or adaptive.get("action") or "N/A")
    monthly_trades = _safe_int(monthly_stats.get("trades") or (monthly_stats.get("overall") or {}).get("trades"), 0)
    pending_outcomes = _safe_int((pipeline.get("positions") or {}).get("pending_outcome"), 0)
    components_ok = _pipeline_components_ok(pipeline)

    risk_flags: List[str] = []
    strengths: List[str] = []

    if alert_counts["critical"] > 0:
        risk_flags.append(f"Alertas críticos ativos: {alert_counts['critical']}.")
    elif alert_counts["warning"] > 0:
        risk_flags.append(f"Warnings executivos ativos: {alert_counts['warning']}.")
    else:
        strengths.append("Executive Alert Manager sem alertas ativos.")

    if components_ok != "N/A":
        try:
            ok_part, total_part = components_ok.split("/")
            if int(float(ok_part)) >= int(float(total_part)):
                strengths.append(f"Pipeline saudável: {components_ok} componentes OK.")
            else:
                risk_flags.append(f"Pipeline parcialmente saudável: {components_ok} componentes OK.")
        except Exception:
            risk_flags.append(f"Pipeline parcialmente saudável: {components_ok} componentes OK.")

    if side["dominant_pct"] >= 85:
        risk_flags.append(f"Concentração direcional crítica: {side['dominant_side']} {side['dominant_pct']}%.")
    elif side["dominant_pct"] >= 75:
        risk_flags.append(f"Concentração direcional elevada: {side['dominant_side']} {side['dominant_pct']}%.")
    elif side["total"] > 0:
        strengths.append("Concentração direcional controlada.")

    if memory_pct >= 90:
        risk_flags.append(f"Memória alta: {memory_pct:.1f}%.")
    elif memory_pct > 0:
        strengths.append(f"Memória controlada: {memory_pct:.1f}%.")

    if adaptive_confidence < 35:
        risk_flags.append("Learning ainda com confiança estatística baixa.")
    elif adaptive_confidence < 60:
        risk_flags.append("Learning ainda em evolução/amostra.")
    else:
        strengths.append("Learning com confiança estatística útil.")

    if pending_outcomes >= 3:
        risk_flags.append(f"Outcomes pendentes: {pending_outcomes}.")
    else:
        strengths.append("Outcome backlog controlado.")

    if monthly_trades <= 0:
        risk_flags.append("Sem amostra mensal de trades encerrados.")
    elif monthly_trades < 20:
        risk_flags.append(f"Amostra mensal ainda limitada: {monthly_trades} trades.")
    else:
        strengths.append(f"Amostra mensal relevante: {monthly_trades} trades.")

    strategy_blocks = _strategy_blocks_expansion(strategic_advisor)

    if alert_counts["critical"] > 0 or confidence < 55:
        directive = "INVESTIGAR_ANTES_DE_EXPANDIR"
        classification = "DEFENSIVO"
        next_action = "Consultar /alertscheck e investigar o componente crítico antes de qualquer expansão ou alteração de risco."
        expansion_allowed = False
        priority = "P1"
    elif strategy_blocks or side["dominant_pct"] >= 75 or adaptive_confidence < 60 or monthly_trades < 20:
        directive = "OPERAR_NORMAL_SEM_EXPANSAO"
        classification = "OPERAÇÃO_ASSISTIDA"
        next_action = "Manter operação normal, não aumentar risco estrutural e acompanhar concentração, learning e amostra."
        expansion_allowed = False
        priority = "P2"
    elif confidence >= 85 and alert_counts["active"] == 0:
        directive = "OPERAR_COM_EXPANSAO_CONTROLADA"
        classification = "EXPANSÃO_CONTROLADA"
        next_action = "Central apta para estudar aumento controlado de alocação, respeitando Risk Manager e limites por robô."
        expansion_allowed = True
        priority = "P3"
    else:
        directive = "OPERAR_NORMAL_COM_MONITORAMENTO"
        classification = "OPERAÇÃO_NORMAL"
        next_action = "Manter operação normal e revisar novamente no próximo ciclo técnico."
        expansion_allowed = False
        priority = "P3"

    main_rec = _main_recommendation(strategic_advisor)
    technical_commands = _technical_commands({"risk_flags": risk_flags})

    result = {
        "ok": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": "ASSISTANT_DECISION_PACK",
        "human_decision_required": False,
        "directive": directive,
        "classification": classification,
        "priority": priority,
        "expansion_allowed": expansion_allowed,
        "next_action_for_assistant": next_action,
        "ceo_confidence": {
            "score": round(confidence, 2),
            "label": confidence_label,
        },
        "strategic_advisor": {
            "directive": _strategy_directive(strategic_advisor),
            "classification": _strategy_classification(strategic_advisor),
            "blocks_expansion": strategy_blocks,
            "main_recommendation": main_rec,
        },
        "executive_alerts": alert_counts,
        "pipeline": {
            "status": pipeline.get("status", "UNKNOWN"),
            "components_ok": components_ok,
            "pending_outcome": pending_outcomes,
        },
        "risk": {
            "positions": side["total"],
            "long": side["long"],
            "short": side["short"],
            "dominant_side": side["dominant_side"],
            "dominant_pct": side["dominant_pct"],
            "memory_pct": round(memory_pct, 2),
        },
        "learning": {
            "adaptive_action": adaptive_action,
            "adaptive_confidence": round(adaptive_confidence, 2),
            "adaptive_weight": adaptive.get("suggested_weight"),
        },
        "sample": {
            "monthly_trades": monthly_trades,
        },
        "strengths": strengths[:8],
        "risk_flags": risk_flags[:10],
        "technical_commands": technical_commands,
        "notes": [
            "Pacote técnico para leitura do assistente.",
            "Não executa trades, não altera risco, não muda pesos e não pede decisão humana.",
        ],
    }
    return result


def build_decision_pack_text(payload: Dict[str, Any], compact: bool = False) -> str:
    payload = _dict(payload)
    conf = _dict(payload.get("ceo_confidence"))
    risk = _dict(payload.get("risk"))
    learning = _dict(payload.get("learning"))
    pipeline = _dict(payload.get("pipeline"))
    alerts = _dict(payload.get("executive_alerts"))

    lines = [
        "🧩 DECISION PACK — CENTRAL QUANT V1",
        f"Data/hora: {payload.get('generated_at', _now_br())}",
        "",
        f"Diretiva técnica: {payload.get('directive')}",
        f"Classificação: {payload.get('classification')}",
        f"Prioridade: {payload.get('priority')}",
        f"CEO Confidence: {conf.get('score', 0)}/100 — {conf.get('label', 'N/A')}",
        f"Expansão permitida: {'SIM' if payload.get('expansion_allowed') else 'NÃO'}",
        f"Decisão humana necessária: {'SIM' if payload.get('human_decision_required') else 'NÃO'}",
        "",
        "Próxima ação do assistente:",
        str(payload.get("next_action_for_assistant") or "Sem ação definida."),
        "",
        "Resumo técnico:",
        f"- Alertas: ativos={alerts.get('active', 0)} | critical={alerts.get('critical', 0)} | warning={alerts.get('warning', 0)} | notify={alerts.get('to_notify', 0)}",
        f"- Pipeline: {pipeline.get('status', 'UNKNOWN')} | componentes OK: {pipeline.get('components_ok', 'N/A')} | outcomes pendentes: {pipeline.get('pending_outcome', 0)}",
        f"- Exposição: {risk.get('positions', 0)} posições | LONG {risk.get('long', 0)} | SHORT {risk.get('short', 0)} | dominante {risk.get('dominant_side', 'N/A')} {risk.get('dominant_pct', 0)}%",
        f"- Memória: {risk.get('memory_pct', 0)}%",
        f"- Learning: {learning.get('adaptive_action', 'N/A')} | confidence {learning.get('adaptive_confidence', 0)}% | weight {learning.get('adaptive_weight')}",
    ]

    if compact:
        flags = payload.get("risk_flags") or []
        if flags:
            lines += ["", "Pontos que limitam decisão:"] + [f"- {x}" for x in flags[:4]]
        lines += ["", "Comandos para próxima consulta:", " ".join(payload.get("technical_commands") or ["/decisionpack"])]
        return "\n".join(lines)

    lines += ["", "Forças:"]
    strengths = payload.get("strengths") or []
    if strengths:
        lines += [f"- {x}" for x in strengths]
    else:
        lines.append("- Nenhuma força específica registrada.")

    lines += ["", "Pontos que limitam decisão:"]
    flags = payload.get("risk_flags") or []
    if flags:
        lines += [f"- {x}" for x in flags]
    else:
        lines.append("- Nenhum limitador relevante no momento.")

    main_rec = _dict((_dict(payload.get("strategic_advisor"))).get("main_recommendation"))
    if main_rec:
        lines += [
            "",
            "Recomendação estratégica herdada:",
            f"- {main_rec.get('priority', 'P?')} | {main_rec.get('category', 'N/A')} | {main_rec.get('title', 'N/A')}",
            f"  Ação: {main_rec.get('action', 'N/A')}",
        ]

    lines += [
        "",
        "Comandos técnicos para o assistente:",
    ]
    lines += [f"- {cmd}" for cmd in (payload.get("technical_commands") or ["/decisionpack"])]
    lines += [
        "",
        "Observação:",
        "Este pacote é feito para o assistente decidir a próxima ação prática com base na Central Quant. Não exige leitura decisória do CEO.",
    ]
    return "\n".join(lines)
