# EXECUTIVE DECISION ENGINE V1 — CENTRAL QUANT
# Versão: 2026-07-04-EXECUTIVE-DECISION-ENGINE-V1
#
# Objetivo:
# - Transformar Decision Pack, Strategic Advisor e CEO Confidence em diretivas operacionais concretas.
# - Não executa ordens, não altera risco, não muda pesos e não fecha posições.
# - Produz política operacional para a Central aplicar/consultar:
#   NO_NEW_LONG, NO_NEW_SHORT, NO_EXPANSION, REDUCE_ONLY, WAIT_SAMPLE, NORMAL_OPERATION.

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

VERSION = "2026-07-04-EXECUTIVE-DECISION-ENGINE-V1"
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


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _risk_from_decision_pack(decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("risk"))


def _confidence_from_any(ceo_confidence: Dict[str, Any], decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    if ceo_confidence:
        return ceo_confidence
    payload = _dict(decision_pack.get("payload")) or decision_pack
    conf = _dict(payload.get("ceo_confidence"))
    if conf:
        return conf
    return {
        "score": _safe_float(payload.get("ceo_confidence_score"), 0.0),
        "label": payload.get("ceo_confidence_label") or "N/A",
    }


def _strategy_from_any(strategic_advisor: Dict[str, Any], decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    if strategic_advisor:
        return strategic_advisor
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("strategic_advisor"))


def _learning_from_decision_pack(decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("learning"))


def _alerts_from_decision_pack(decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("executive_alerts"))


def _pipeline_from_decision_pack(decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("pipeline"))


def _monthly_from_decision_pack(decision_pack: Dict[str, Any]) -> Dict[str, Any]:
    payload = _dict(decision_pack.get("payload")) or decision_pack
    return _dict(payload.get("sample"))


def _new_directive(code: str, level: str, category: str, title: str, action: str, rationale: str, blocks: bool = False, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "code": code,
        "level": level,
        "category": category,
        "title": title,
        "action": action,
        "rationale": rationale,
        "blocks_expansion": bool(blocks),
        "policy": policy or {},
    }


def build_executive_decision(
    decision_pack: Optional[Dict[str, Any]] = None,
    strategic_advisor: Optional[Dict[str, Any]] = None,
    ceo_confidence: Optional[Dict[str, Any]] = None,
    executive_alerts: Optional[Dict[str, Any]] = None,
    pipeline: Optional[Dict[str, Any]] = None,
    exposure: Optional[Dict[str, Any]] = None,
    memory: Optional[Dict[str, Any]] = None,
    adaptive: Optional[Dict[str, Any]] = None,
    monthly_stats: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Gera uma decisão executiva operacional.

    Importante:
    - V1 é consultiva/decisional, mas não executora.
    - A saída pode ser usada pelo Risk Manager / Main para bloquear novas entradas no futuro.
    """
    decision_pack = _dict(decision_pack)
    strategic_advisor = _strategy_from_any(_dict(strategic_advisor), decision_pack)
    ceo_confidence = _confidence_from_any(_dict(ceo_confidence), decision_pack)

    risk = _dict(exposure) or _risk_from_decision_pack(decision_pack)
    learning = _dict(adaptive) or _learning_from_decision_pack(decision_pack)
    alerts = _dict(executive_alerts) or _alerts_from_decision_pack(decision_pack)
    pipe = _dict(pipeline) or _pipeline_from_decision_pack(decision_pack)
    sample = _dict(monthly_stats) or _monthly_from_decision_pack(decision_pack)

    score = _safe_float(ceo_confidence.get("score"), _safe_float(decision_pack.get("ceo_confidence", {}).get("score"), 0.0))
    label = str(ceo_confidence.get("label") or decision_pack.get("ceo_confidence", {}).get("label") or "N/A")

    positions = _safe_int(risk.get("positions") or risk.get("total_positions_open") or risk.get("total"), 0)
    long_count = _safe_int(risk.get("long") or risk.get("long_positions_open"), 0)
    short_count = _safe_int(risk.get("short") or risk.get("short_positions_open"), 0)
    dominant_side = str(risk.get("dominant_side") or ("LONG" if long_count >= short_count else "SHORT")).upper()
    if risk.get("dominant_pct") is not None:
        dominant_pct = _safe_float(risk.get("dominant_pct"), 0.0)
    else:
        dominant_pct = round((max(long_count, short_count) / max(positions, 1)) * 100.0, 2) if positions else 0.0

    memory_pct = _safe_float(risk.get("memory_pct") or _dict(memory).get("usage_pct"), 0.0)
    critical_alerts = _safe_int(alerts.get("critical"), 0)
    warning_alerts = _safe_int(alerts.get("warning"), 0)
    pending_outcome = _safe_int(pipe.get("pending_outcome") or _dict(pipe.get("positions")).get("pending_outcome"), 0)
    pipeline_status = str(pipe.get("status") or "UNKNOWN")
    components_ok = str(pipe.get("components_ok") or "")

    adaptive_confidence = _safe_float(learning.get("adaptive_confidence") or learning.get("confidence"), 0.0)
    monthly_trades = _safe_int(sample.get("monthly_trades") or sample.get("trades"), 0)

    strategic_blocks = bool(strategic_advisor.get("expansion_blocked") or strategic_advisor.get("blocks_expansion"))
    dp_expansion_allowed = decision_pack.get("expansion_allowed")
    if dp_expansion_allowed is None:
        dp_expansion_allowed = not strategic_blocks

    directives: List[Dict[str, Any]] = []

    if critical_alerts > 0:
        directives.append(_new_directive(
            "HALT_EXPANSION_CRITICAL_ALERT",
            "P0",
            "EXECUTIVE_ALERT",
            "Bloquear expansão por alerta crítico",
            "Não aceitar novas expansões até os alertas críticos serem resolvidos.",
            "Há alerta crítico ativo no Executive Alert Manager.",
            True,
            {"allow_new_entries": False, "allow_expansion": False, "reason": "critical_alert"},
        ))

    if pipeline_status in {"ERRO", "ERROR", "CRITICAL"}:
        directives.append(_new_directive(
            "HALT_EXPANSION_PIPELINE_ERROR",
            "P0",
            "PIPELINE",
            "Bloquear expansão por erro de pipeline",
            "Não aceitar novas entradas até o pipeline voltar para OK.",
            f"Pipeline status: {pipeline_status}.",
            True,
            {"allow_new_entries": False, "allow_expansion": False, "reason": "pipeline_error"},
        ))

    if dominant_pct >= 85.0 and dominant_side in {"LONG", "SHORT"}:
        policy = {
            "allow_new_long": dominant_side != "LONG",
            "allow_new_short": dominant_side != "SHORT",
            "allow_expansion": False,
            "dominant_side": dominant_side,
            "dominant_pct": dominant_pct,
            "release_condition": f"{dominant_side} abaixo de 75%",
        }
        directives.append(_new_directive(
            f"NO_NEW_{dominant_side}",
            "P1",
            "RISK",
            f"Bloquear novas entradas {dominant_side}",
            f"Não aceitar novas entradas {dominant_side} até concentração cair abaixo de 75%.",
            f"Concentração direcional crítica: {dominant_side} {dominant_pct}%.",
            True,
            policy,
        ))
    elif dominant_pct >= 75.0 and dominant_side in {"LONG", "SHORT"}:
        directives.append(_new_directive(
            f"LIMIT_NEW_{dominant_side}",
            "P2",
            "RISK",
            f"Limitar novas entradas {dominant_side}",
            f"Evitar aumento agressivo de exposição {dominant_side}; priorizar lado oposto ou aguardar redução.",
            f"Concentração direcional elevada: {dominant_side} {dominant_pct}%.",
            True,
            {"allow_expansion": False, "dominant_side": dominant_side, "dominant_pct": dominant_pct},
        ))

    if positions >= 50:
        directives.append(_new_directive(
            "REDUCE_ONLY_GLOBAL_EXPOSURE",
            "P1",
            "RISK",
            "Ativar modo reduce-only por exposição global",
            "Não aceitar novas entradas; permitir apenas gestão/saídas/redução.",
            f"Exposição global em {positions} posições.",
            True,
            {"reduce_only": True, "allow_new_entries": False, "positions": positions},
        ))
    elif positions >= 40:
        directives.append(_new_directive(
            "NO_EXPANSION_HIGH_EXPOSURE",
            "P2",
            "RISK",
            "Bloquear expansão por exposição elevada",
            "Manter operação normal, mas sem aumentar quantidade estrutural de posições.",
            f"Exposição global elevada: {positions} posições.",
            True,
            {"allow_expansion": False, "positions": positions},
        ))

    if memory_pct >= 90.0:
        directives.append(_new_directive(
            "REDUCE_ONLY_MEMORY_HIGH",
            "P1",
            "SYSTEM",
            "Ativar proteção por memória alta",
            "Evitar novas entradas e comandos pesados até memória normalizar.",
            f"Memória em {memory_pct}%.",
            True,
            {"allow_new_entries": False, "avoid_heavy_reports": True, "memory_pct": memory_pct},
        ))

    if adaptive_confidence < 30.0 or monthly_trades < 10:
        directives.append(_new_directive(
            "WAIT_SAMPLE",
            "P2",
            "LEARNING",
            "Manter coleta de amostra",
            "Não aumentar risco estrutural até learning e histórico terem amostra suficiente.",
            f"Adaptive confidence {adaptive_confidence}% | trades mês {monthly_trades}.",
            False,
            {"allow_risk_increase": False, "adaptive_confidence": adaptive_confidence, "monthly_trades": monthly_trades},
        ))

    if score < 60.0:
        directives.append(_new_directive(
            "NO_EXPANSION_LOW_CONFIDENCE",
            "P1",
            "CEO_CONFIDENCE",
            "Bloquear expansão por confiança baixa",
            "Não aumentar risco até CEO Confidence voltar acima de 70.",
            f"CEO Confidence em {score}/100.",
            True,
            {"allow_expansion": False, "ceo_confidence": score},
        ))
    elif score < 75.0:
        directives.append(_new_directive(
            "NORMAL_WITH_MONITORING",
            "P2",
            "CEO_CONFIDENCE",
            "Operação normal com monitoramento",
            "Manter operação, sem expansão agressiva.",
            f"CEO Confidence em {score}/100 — {label}.",
            False,
            {"allow_expansion": False, "ceo_confidence": score},
        ))

    if not directives:
        directives.append(_new_directive(
            "NORMAL_OPERATION",
            "P3",
            "SYSTEM",
            "Operação normal",
            "Manter operação normal conforme Risk Manager.",
            "Nenhum bloqueio executivo relevante detectado.",
            False,
            {"allow_expansion": True, "allow_new_entries": True},
        ))

    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    directives.sort(key=lambda x: priority_order.get(str(x.get("level")), 9))
    primary = directives[0]

    policy = {
        "allow_new_entries": True,
        "allow_new_long": True,
        "allow_new_short": True,
        "allow_expansion": True,
        "allow_risk_increase": True,
        "reduce_only": False,
        "avoid_heavy_reports": False,
    }
    for directive in directives:
        p = _dict(directive.get("policy"))
        for key, value in p.items():
            if key.startswith("allow_"):
                policy[key] = bool(policy.get(key, True) and bool(value))
            elif key in {"reduce_only", "avoid_heavy_reports"}:
                policy[key] = bool(policy.get(key, False) or bool(value))
            else:
                policy[key] = value

    expansion_blocked = not bool(policy.get("allow_expansion", True))
    if strategic_blocks or dp_expansion_allowed is False:
        expansion_blocked = True
        policy["allow_expansion"] = False

    if primary.get("code", "").startswith("NO_NEW_"):
        primary_decision = primary.get("code")
    elif policy.get("reduce_only"):
        primary_decision = "REDUCE_ONLY"
    elif not policy.get("allow_new_entries", True):
        primary_decision = "NO_NEW_ENTRIES"
    elif expansion_blocked:
        primary_decision = "NO_EXPANSION"
    else:
        primary_decision = "ALLOW_NORMAL"

    if primary_decision == "NO_NEW_LONG":
        assistant_action = "Aplicar política NO_NEW_LONG: novas entradas LONG devem ser bloqueadas até concentração cair abaixo de 75%."
    elif primary_decision == "NO_NEW_SHORT":
        assistant_action = "Aplicar política NO_NEW_SHORT: novas entradas SHORT devem ser bloqueadas até concentração cair abaixo de 75%."
    elif primary_decision == "REDUCE_ONLY":
        assistant_action = "Aplicar reduce-only: não abrir novas posições; permitir apenas gestão e redução."
    elif primary_decision == "NO_EXPANSION":
        assistant_action = "Manter operação normal sem expansão estrutural de risco, lote ou quantidade de posições."
    else:
        assistant_action = "Manter operação normal conforme Risk Manager e continuar coletando amostra."

    return {
        "ok": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": "EXECUTIVE_DECISION_ENGINE",
        "human_decision_required": False,
        "assistant_decision_required": True,
        "primary_decision": primary_decision,
        "primary_directive": primary,
        "policy": policy,
        "expansion_blocked": expansion_blocked,
        "assistant_action": assistant_action,
        "ceo_confidence": {"score": round(score, 2), "label": label},
        "risk": {
            "positions": positions,
            "long": long_count,
            "short": short_count,
            "dominant_side": dominant_side,
            "dominant_pct": round(dominant_pct, 2),
            "memory_pct": round(memory_pct, 2),
        },
        "pipeline": {
            "status": pipeline_status,
            "components_ok": components_ok,
            "pending_outcome": pending_outcome,
        },
        "learning": {
            "adaptive_confidence": adaptive_confidence,
            "monthly_trades": monthly_trades,
        },
        "directives": directives,
        "technical_commands": [
            "/executivedecision",
            "/decisionpack",
            "/strategy",
            "/ceoconfidence",
            "/risk",
            "/heat",
            "/traderegistry/report",
        ],
        "notes": [
            "V1 não altera ordens, risco ou pesos automaticamente.",
            "A saída policy foi desenhada para futura integração com Risk Manager.",
            "Enquanto human_decision_required=False, a decisão prática deve ser interpretada pelo assistente técnico.",
        ],
    }


def build_executive_decision_text(payload: Dict[str, Any], compact: bool = False) -> str:
    payload = _dict(payload)
    risk = _dict(payload.get("risk"))
    confidence = _dict(payload.get("ceo_confidence"))
    policy = _dict(payload.get("policy"))
    primary = _dict(payload.get("primary_directive"))
    directives = _list(payload.get("directives"))

    lines = [
        "⚖️ EXECUTIVE DECISION ENGINE — CENTRAL QUANT V1",
        f"Data/hora: {payload.get('generated_at')}",
        "",
        f"Decisão primária: {payload.get('primary_decision')}",
        f"Prioridade: {primary.get('level', 'N/A')}",
        f"Categoria: {primary.get('category', 'N/A')}",
        f"CEO Confidence: {confidence.get('score', 0)}/100 — {confidence.get('label', 'N/A')}",
        f"Bloqueia expansão: {'SIM' if payload.get('expansion_blocked') else 'NÃO'}",
        f"Decisão humana necessária: {'SIM' if payload.get('human_decision_required') else 'NÃO'}",
        "",
        "Ação operacional:",
        str(payload.get("assistant_action") or "N/A"),
        "",
        "Política atual:",
        f"- Novas entradas: {'SIM' if policy.get('allow_new_entries', True) else 'NÃO'}",
        f"- Novos LONG: {'SIM' if policy.get('allow_new_long', True) else 'NÃO'}",
        f"- Novos SHORT: {'SIM' if policy.get('allow_new_short', True) else 'NÃO'}",
        f"- Expansão: {'SIM' if policy.get('allow_expansion', True) else 'NÃO'}",
        f"- Aumento de risco: {'SIM' if policy.get('allow_risk_increase', True) else 'NÃO'}",
        f"- Reduce-only: {'SIM' if policy.get('reduce_only') else 'NÃO'}",
        "",
        "Estado usado na decisão:",
        f"- Exposição: {risk.get('positions', 0)} posições | LONG {risk.get('long', 0)} | SHORT {risk.get('short', 0)} | dominante {risk.get('dominant_side')} {risk.get('dominant_pct')}%",
        f"- Memória: {risk.get('memory_pct')}%",
        f"- Pipeline: {_dict(payload.get('pipeline')).get('status')} | componentes OK: {_dict(payload.get('pipeline')).get('components_ok')}",
        f"- Learning: confidence {_dict(payload.get('learning')).get('adaptive_confidence')}% | trades mês {_dict(payload.get('learning')).get('monthly_trades')}",
    ]

    if not compact:
        lines += ["", "Diretivas:"]
        for item in directives[:8]:
            lines.append(f"- {item.get('level')} | {item.get('code')} | {item.get('title')}")
            lines.append(f"  Ação: {item.get('action')}")

        lines += ["", "Comandos técnicos:"]
        for cmd in _list(payload.get("technical_commands"))[:10]:
            lines.append(f"- {cmd}")

        lines += [
            "",
            "Observação:",
            "Este motor decide a política operacional, mas V1 ainda não aplica bloqueios sozinho no Risk Manager.",
        ]

    return "\n".join(lines)
