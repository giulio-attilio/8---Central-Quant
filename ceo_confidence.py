# CEO CONFIDENCE INDEX V1 — CENTRAL QUANT
# Versão: 2026-07-04-CEO-CONFIDENCE-INDEX-V1
#
# Objetivo:
# - Sintetizar a confiança executiva global da Central Quant em um único score 0-100.
# - Não executa trades, não altera risco e não modifica estado operacional.
# - Usa snapshots já existentes: Executive Alerts, Pipeline, Exposição, Memória, Adaptive e Performance mensal.

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

VERSION = "2026-07-04-CEO-CONFIDENCE-INDEX-V1"
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


def _component_score(score: float, weight: float, label: str, reasons: List[str], strengths: List[str], risks: List[str], detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    score = round(_clamp(score), 2)
    weighted = round(score * weight, 4)
    return {
        "label": label,
        "score": score,
        "weight": weight,
        "weighted_score": weighted,
        "reasons": reasons,
        "strengths": strengths,
        "risks": risks,
        "detail": detail or {},
    }


def _label_for_score(score: float) -> str:
    score = _safe_float(score)
    if score >= 90:
        return "EXCELENTE"
    if score >= 80:
        return "MUITO_BOM"
    if score >= 70:
        return "BOM"
    if score >= 60:
        return "ATENÇÃO"
    if score >= 45:
        return "FRÁGIL"
    return "CRÍTICO"


def _action_for_score(score: float) -> str:
    score = _safe_float(score)
    if score >= 90:
        return "EXPANDIR_COM_DISCIPLINA"
    if score >= 80:
        return "MANTER_E_OTIMIZAR"
    if score >= 70:
        return "OPERAR_NORMAL_COM_MONITORAMENTO"
    if score >= 60:
        return "REDUZIR_RITMO_E_OBSERVAR"
    if score >= 45:
        return "MODO_DEFENSIVO"
    return "PAUSAR_EXPANSÃO_E_INVESTIGAR"


def _executive_alert_score(executive_alerts: Dict[str, Any]) -> Dict[str, Any]:
    hs = (executive_alerts or {}).get("health_score") or {}
    base = _safe_float(hs.get("score"), 70.0)
    critical = 0
    warning = 0
    notify = _safe_int((executive_alerts or {}).get("alerts_to_notify_count"), 0)
    for alert in (executive_alerts or {}).get("alerts") or []:
        level = str(alert.get("level") or "").upper()
        if level == "CRITICAL":
            critical += 1
        elif level == "WARNING":
            warning += 1
    score = base - (critical * 18) - (warning * 7) - (notify * 5)
    strengths, risks, reasons = [], [], []
    if critical:
        risks.append(f"{critical} alerta(s) crítico(s) ativo(s).")
    if warning:
        risks.append(f"{warning} warning(s) ativo(s).")
    if not critical and not warning:
        strengths.append("Executive Alert Manager sem alertas ativos.")
    reasons.append(f"Health executivo atual: {int(base)}/100.")
    return _component_score(score, 0.25, "executive_alert_health", reasons, strengths, risks, {"critical": critical, "warning": warning, "notify": notify})


def _pipeline_score(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    components = (((pipeline or {}).get("pipeline") or {}).get("components") or {})
    if not components:
        status = str((pipeline or {}).get("status") or "UNKNOWN").upper()
        score = 70.0 if status == "OK" else 35.0
        risks = [] if status == "OK" else ["Pipeline sem componentes detalhados ou com status não OK."]
        strengths = ["Pipeline principal reporta OK."] if status == "OK" else []
        return _component_score(score, 0.20, "pipeline_reliability", [f"Status pipeline: {status}."], strengths, risks, {"status": status})

    total = len(components)
    ok_count = 0
    failed = []
    for name, comp in components.items():
        ok = bool((comp or {}).get("ok"))
        if ok:
            ok_count += 1
        else:
            failed.append(name)
    ratio = ok_count / max(total, 1)
    score = 35.0 + ratio * 65.0
    strengths = [f"{ok_count}/{total} componentes saudáveis."] if ok_count else []
    risks = [f"Componente indisponível: {x}." for x in failed[:5]]
    return _component_score(score, 0.20, "pipeline_reliability", [f"Componentes OK: {ok_count}/{total}."], strengths, risks, {"ok_count": ok_count, "total": total, "failed": failed})


def _risk_exposure_score(exposure: Dict[str, Any], memory: Dict[str, Any]) -> Dict[str, Any]:
    total = _safe_int((exposure or {}).get("total_positions_open"), 0)
    longs = _safe_int((exposure or {}).get("long_positions_open"), 0)
    shorts = _safe_int((exposure or {}).get("short_positions_open"), 0)
    memory_pct = _safe_float((memory or {}).get("usage_pct"), 0.0)

    score = 85.0
    risks, strengths, reasons = [], [], []

    if total >= 50:
        score -= 25
        risks.append("Exposição global próxima/acima do limite operacional.")
    elif total >= 40:
        score -= 14
        risks.append("Exposição global elevada.")
    elif total >= 20:
        score -= 5
        risks.append("Exposição moderada; monitorar concentração.")
    else:
        strengths.append("Exposição global confortável.")

    if total > 0:
        dominant_pct = max(longs, shorts) / max(total, 1) * 100.0
        if dominant_pct >= 85:
            score -= 18
            risks.append(f"Concentração direcional muito alta: {dominant_pct:.1f}%.")
        elif dominant_pct >= 75:
            score -= 10
            risks.append(f"Concentração direcional elevada: {dominant_pct:.1f}%.")
        else:
            strengths.append("Concentração direcional controlada.")
    else:
        dominant_pct = 0.0
        strengths.append("Sem exposição aberta relevante.")

    if memory_pct >= 95:
        score -= 25
        risks.append(f"Memória em zona de bloqueio: {memory_pct:.1f}%.")
    elif memory_pct >= 90:
        score -= 14
        risks.append(f"Memória elevada: {memory_pct:.1f}%.")
    elif memory_pct >= 75:
        score -= 6
        risks.append(f"Memória em atenção: {memory_pct:.1f}%.")
    else:
        strengths.append("Memória dentro de zona saudável.")

    reasons.append(f"Exposição: {total} posições | LONG {longs} | SHORT {shorts} | memória {memory_pct:.1f}%.")
    return _component_score(score, 0.15, "risk_and_exposure", reasons, strengths, risks, {"positions": total, "long": longs, "short": shorts, "dominant_pct": round(dominant_pct, 2), "memory_pct": round(memory_pct, 2)})


def _learning_score(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    adaptive = (pipeline or {}).get("adaptive") or {}
    confidence = _safe_float(adaptive.get("confidence"), 0.0)
    trades = _safe_int(adaptive.get("trades"), 0)
    action = str(adaptive.get("recommended_action") or "WAIT_SAMPLE").upper()
    pending = _safe_int(((pipeline or {}).get("positions") or {}).get("pending_outcome"), 0)

    score = 45.0
    if trades >= 80:
        score += 30
    elif trades >= 40:
        score += 24
    elif trades >= 20:
        score += 17
    elif trades >= 10:
        score += 10
    elif trades >= 5:
        score += 5

    score += min(20.0, confidence * 0.20)

    risks, strengths, reasons = [], [], []
    if pending >= 8:
        score -= 20
        risks.append(f"Muitos outcomes pendentes: {pending}.")
    elif pending >= 3:
        score -= 10
        risks.append(f"Outcomes pendentes: {pending}.")
    else:
        strengths.append("Outcome backlog controlado.")

    if action in {"PAUSE", "BLOCK", "DISABLE", "REDUCE"}:
        score -= 12
        risks.append(f"Adaptive recomenda ação defensiva: {action}.")
    elif action in {"WAIT_SAMPLE", "OBSERVE"}:
        risks.append("Learning ainda em fase de amostra/observação.")
    else:
        strengths.append(f"Adaptive action operacional: {action}.")

    reasons.append(f"Adaptive confidence: {confidence:.1f}% | trades: {trades} | action: {action}.")
    return _component_score(score, 0.15, "learning_and_adaptive", reasons, strengths, risks, {"confidence": confidence, "trades": trades, "action": action, "pending_outcome": pending})


def _performance_score(monthly_stats: Dict[str, Any]) -> Dict[str, Any]:
    stats = monthly_stats or {}
    trades = _safe_int(stats.get("trades") or stats.get("closed_trades"), 0)
    win_rate = _safe_float(stats.get("win_rate_pct"), 0.0)
    pnl_total = _safe_float(stats.get("pnl_total_pct"), 0.0)
    pnl_avg = _safe_float(stats.get("pnl_avg_pct"), 0.0)
    profit_factor = _safe_float(stats.get("profit_factor") or stats.get("profit_factor_pct"), 0.0)
    r_total = _safe_float(stats.get("r_total"), 0.0)

    if trades <= 0:
        return _component_score(50.0, 0.15, "performance_quality", ["Sem trades encerrados no período; score neutro/conservador."], [], ["Sem amostra mensal para performance."], {"trades": trades})

    score = 45.0
    if trades >= 80:
        score += 12
    elif trades >= 40:
        score += 9
    elif trades >= 20:
        score += 6
    elif trades >= 10:
        score += 3

    if win_rate >= 65:
        score += 14
    elif win_rate >= 55:
        score += 10
    elif win_rate >= 45:
        score += 4
    elif win_rate < 35:
        score -= 10

    if pnl_total >= 10:
        score += 15
    elif pnl_total > 0:
        score += 8
    elif pnl_total <= -10:
        score -= 18
    elif pnl_total < 0:
        score -= 8

    if pnl_avg > 0.25:
        score += 8
    elif pnl_avg > 0:
        score += 4
    elif pnl_avg < -0.25:
        score -= 8

    if profit_factor >= 2:
        score += 8
    elif profit_factor >= 1.2:
        score += 4
    elif 0 < profit_factor < 1:
        score -= 8

    if r_total > 0:
        score += min(6, r_total)
    elif r_total < 0:
        score -= min(8, abs(r_total))

    strengths, risks = [], []
    if pnl_total > 0:
        strengths.append(f"PnL mensal positivo: {pnl_total:.2f}%.")
    else:
        risks.append(f"PnL mensal não positivo: {pnl_total:.2f}%.")
    if trades < 20:
        risks.append("Amostra mensal ainda pequena para decisão estatística forte.")
    reasons = [f"Trades: {trades} | win rate: {win_rate:.1f}% | PnL: {pnl_total:.2f}% | PF: {profit_factor}."]
    return _component_score(score, 0.15, "performance_quality", reasons, strengths, risks, {"trades": trades, "win_rate_pct": win_rate, "pnl_total_pct": pnl_total, "pnl_avg_pct": pnl_avg, "profit_factor": profit_factor, "r_total": r_total})


def _sample_score(monthly_stats: Dict[str, Any], pipeline: Dict[str, Any]) -> Dict[str, Any]:
    stats = monthly_stats or {}
    trades = _safe_int(stats.get("trades") or stats.get("closed_trades"), 0)
    adaptive_trades = _safe_int(((pipeline or {}).get("adaptive") or {}).get("trades"), 0)
    events = _safe_int(stats.get("events_total"), 0)
    score = 35.0
    sample = max(trades, adaptive_trades)
    if sample >= 100:
        score = 95.0
    elif sample >= 60:
        score = 85.0
    elif sample >= 30:
        score = 75.0
    elif sample >= 15:
        score = 65.0
    elif sample >= 5:
        score = 52.0
    if events >= 100:
        score = min(100, score + 5)
    risks = [] if sample >= 20 else ["Amostra estatística ainda limitada."]
    strengths = ["Amostra operacional relevante."] if sample >= 20 else []
    return _component_score(score, 0.10, "sample_and_data_quality", [f"Amostra considerada: {sample} trades | eventos: {events}."], strengths, risks, {"sample": sample, "events": events})


def build_ceo_confidence_index(
    executive_alerts: Optional[Dict[str, Any]] = None,
    pipeline: Optional[Dict[str, Any]] = None,
    exposure: Optional[Dict[str, Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
    monthly_stats: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calcula o CEO Confidence Index V1 usando snapshots já preparados pelo main.py."""
    executive_alerts = executive_alerts or {}
    pipeline = pipeline or {}
    exposure = exposure or {}
    memory = memory or {}
    monthly_stats = monthly_stats or {}

    components = [
        _executive_alert_score(executive_alerts),
        _pipeline_score(pipeline),
        _risk_exposure_score(exposure, memory),
        _learning_score(pipeline),
        _performance_score(monthly_stats),
        _sample_score(monthly_stats, pipeline),
    ]
    score = round(_clamp(sum(c.get("weighted_score", 0.0) for c in components)), 2)
    label = _label_for_score(score)
    action = _action_for_score(score)

    strengths: List[str] = []
    risks: List[str] = []
    reasons: List[str] = []
    for comp in components:
        strengths.extend(comp.get("strengths") or [])
        risks.extend(comp.get("risks") or [])
        reasons.extend(comp.get("reasons") or [])

    # Remove duplicados preservando ordem.
    def _unique(items: List[str]) -> List[str]:
        seen = set()
        out = []
        for item in items:
            key = str(item)
            if key not in seen:
                seen.add(key)
                out.append(item)
        return out

    strengths = _unique(strengths)[:12]
    risks = _unique(risks)[:12]
    reasons = _unique(reasons)[:12]

    if score >= 90:
        recommendation = "A Central está em estado excelente. Pode considerar expansão gradual, mantendo limites de risco e validação estatística."
    elif score >= 80:
        recommendation = "A Central está saudável. Manter operação, otimizar pesos e continuar acumulando amostra."
    elif score >= 70:
        recommendation = "A Central está boa, mas ainda exige monitoramento. Evitar aumento agressivo de risco."
    elif score >= 60:
        recommendation = "A Central requer atenção. Operar defensivamente até melhorar amostra, pipeline ou risco."
    elif score >= 45:
        recommendation = "A Central está frágil. Evitar expansão e investigar os pontos de risco antes de aumentar exposição."
    else:
        recommendation = "A Central está em condição crítica. Pausar expansão e investigar imediatamente."

    return {
        "ok": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "score": score,
        "label": label,
        "action": action,
        "recommendation": recommendation,
        "components": {c["label"]: c for c in components},
        "strengths": strengths,
        "risks": risks,
        "reasons": reasons,
        "mode": "OBSERVATION_ONLY",
        "notes": [
            "CEO Confidence Index V1 é consultivo e não executa trades.",
            "Score combina saúde executiva, pipeline, risco, learning, performance e qualidade da amostra.",
            "Enquanto não houver amostra mensal suficiente, performance e sample quality ficam conservadores.",
        ],
        "extra": extra or {},
    }


def build_ceo_confidence_text(payload: Dict[str, Any]) -> str:
    payload = payload or {}
    components = payload.get("components") or {}
    lines = [
        "🧭 CEO CONFIDENCE INDEX — CENTRAL QUANT V1",
        f"Data/hora: {payload.get('generated_at') or _now_br()}",
        "",
        f"Score: {payload.get('score', 0)}/100 — {payload.get('label', 'N/A')}",
        f"Ação executiva: {payload.get('action', 'N/A')}",
        f"Modo: {payload.get('mode', 'OBSERVATION_ONLY')}",
        "",
        "Leitura executiva:",
        f"{payload.get('recommendation', 'Sem recomendação disponível.')}",
        "",
        "Componentes:",
    ]
    for key in ["executive_alert_health", "pipeline_reliability", "risk_and_exposure", "learning_and_adaptive", "performance_quality", "sample_and_data_quality"]:
        comp = components.get(key) or {}
        if not comp:
            continue
        lines.append(f"- {key}: {comp.get('score')}/100 | peso {round(_safe_float(comp.get('weight')) * 100, 1)}%")

    strengths = payload.get("strengths") or []
    risks = payload.get("risks") or []

    lines += ["", "Forças:"]
    if strengths:
        for item in strengths[:6]:
            lines.append(f"- {item}")
    else:
        lines.append("- Nenhuma força estatística relevante ainda.")

    lines += ["", "Pontos de atenção:"]
    if risks:
        for item in risks[:8]:
            lines.append(f"- {item}")
    else:
        lines.append("- Nenhum ponto crítico identificado.")

    lines += ["", "Observação:", "Este índice é consultivo. Ele não altera lote, risco, execução ou bots automaticamente."]
    return "\n".join(lines)
