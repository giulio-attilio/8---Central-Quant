# executive_alert_manager.py
# CENTRAL QUANT — EXECUTIVE ALERT MANAGER V2
# Versão: 2026-07-04-EXECUTIVE-ALERT-MANAGER-V2
#
# Objetivo:
# - Decidir quando a Central Quant deve interromper o CEO.
# - Gerar alertas inteligentes por severidade.
# - Evitar spam usando cooldown e estado persistente.
# - Detectar recuperação de alertas críticos.
# - Calcular Health Score operacional interno.
# - Não executa trades, não altera risco e não chama corretora.
#
# Compatibilidade:
# - Mantém os mesmos nomes de funções do V1:
#   executive_alert_manager_health
#   build_executive_alerts
#   build_executive_alerts_text
#   build_executive_alert_text
#   read_executive_alert_log

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional


VERSION = "2026-07-04-EXECUTIVE-ALERT-MANAGER-V2"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTIVE_ALERT_STATE_FILE = DATA_DIR / "executive_alert_state.json"
EXECUTIVE_ALERT_LOG_FILE = DATA_DIR / "executive_alert_log.jsonl"

EXECUTIVE_ALERTS_ENABLED = os.getenv("CENTRAL_EXECUTIVE_ALERTS_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "sim", "on"
}

EXECUTIVE_ALERT_COOLDOWN_SECONDS = int(os.getenv("CENTRAL_EXECUTIVE_ALERT_COOLDOWN_SECONDS", "3600"))
EXECUTIVE_RECOVERY_ALERTS_ENABLED = os.getenv("CENTRAL_EXECUTIVE_RECOVERY_ALERTS_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "sim", "on"
}

# Limiares V2.
MEMORY_WARNING_PCT = float(os.getenv("EXEC_ALERT_MEMORY_WARNING_PCT", "85"))
MEMORY_CRITICAL_PCT = float(os.getenv("EXEC_ALERT_MEMORY_CRITICAL_PCT", "92"))

PENDING_OUTCOME_WARNING = int(os.getenv("EXEC_ALERT_PENDING_OUTCOME_WARNING", "3"))
PENDING_OUTCOME_CRITICAL = int(os.getenv("EXEC_ALERT_PENDING_OUTCOME_CRITICAL", "8"))

PAPER_OPEN_WARNING = int(os.getenv("EXEC_ALERT_PAPER_OPEN_WARNING", "10"))
PAPER_OPEN_CRITICAL = int(os.getenv("EXEC_ALERT_PAPER_OPEN_CRITICAL", "20"))

CENTRAL_POSITIONS_WARNING = int(os.getenv("EXEC_ALERT_CENTRAL_POSITIONS_WARNING", "40"))
CENTRAL_POSITIONS_CRITICAL = int(os.getenv("EXEC_ALERT_CENTRAL_POSITIONS_CRITICAL", "50"))

SIDE_CONCENTRATION_WARNING_PCT = float(os.getenv("EXEC_ALERT_SIDE_CONCENTRATION_WARNING_PCT", "75"))
SIDE_CONCENTRATION_CRITICAL_PCT = float(os.getenv("EXEC_ALERT_SIDE_CONCENTRATION_CRITICAL_PCT", "85"))

ADAPTIVE_CONFIDENCE_ACTION_MIN = float(os.getenv("EXEC_ALERT_ADAPTIVE_CONFIDENCE_ACTION_MIN", "70"))


try:
    from execution_pipeline_status import build_execution_pipeline_status
except Exception as exc:
    build_execution_pipeline_status = None
    PIPELINE_IMPORT_ERROR = str(exc)
else:
    PIPELINE_IMPORT_ERROR = None


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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
        return int(value)
    except Exception:
        return default


def _pct(part: int, total: int) -> float:
    try:
        total = int(total)
        if total <= 0:
            return 0.0
        return round((float(part) / float(total)) * 100.0, 2)
    except Exception:
        return 0.0


def _alert_key(alert: Dict[str, Any]) -> str:
    base = {
        "level": alert.get("level"),
        "category": alert.get("category"),
        "code": alert.get("code"),
        "title": alert.get("title"),
    }
    raw = json.dumps(base, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24].upper()


def _new_alert(
    level: str,
    category: str,
    code: str,
    title: str,
    message: str,
    action: str,
    data: Optional[Dict[str, Any]] = None,
    impact_score: int = 10,
) -> Dict[str, Any]:
    level = str(level or "INFO").upper().strip()
    alert = {
        "level": level,
        "category": str(category or "GENERAL").upper().strip(),
        "code": str(code or "UNKNOWN").upper().strip(),
        "title": title,
        "message": message,
        "action": action,
        "impact_score": int(impact_score),
        "data": data or {},
        "generated_at": _now_br(),
        "epoch": time.time(),
        "version": VERSION,
    }
    alert["alert_key"] = _alert_key(alert)
    return alert


def _component_statuses(pipeline: Dict[str, Any]) -> Dict[str, bool]:
    components = (((pipeline.get("pipeline") or {}).get("components") or {}) if isinstance(pipeline, dict) else {})
    out = {}
    for key in ["execution_engine", "paper_executor", "paper_lifecycle", "outcome_evaluator", "adaptive_weights"]:
        out[key] = bool((components.get(key) or {}).get("ok"))
    return out


def _extract_memory_pct(pipeline: Dict[str, Any]) -> Optional[float]:
    """
    Tenta obter memória pelo health do Execution Engine/Orchestrator quando disponível.
    Se não existir no pipeline, retorna None.
    """
    try:
        components = ((pipeline.get("pipeline") or {}).get("components") or {})
        engine_health = ((components.get("execution_engine") or {}).get("health") or {})
        value = engine_health.get("memory_pct") or engine_health.get("memory_usage_pct")
        if value is not None:
            return _safe_float(value, None)
    except Exception:
        pass
    return None


def _calculate_health_score(alerts: List[Dict[str, Any]], pipeline: Dict[str, Any]) -> Dict[str, Any]:
    score = 100
    reasons = []

    for alert in alerts:
        impact = _safe_int(alert.get("impact_score"), 0)
        score -= impact
        reasons.append({
            "code": alert.get("code"),
            "title": alert.get("title"),
            "impact": impact,
            "level": alert.get("level"),
        })

    # Pequena penalidade se pipeline não estiver OK, mesmo sem alerta específico.
    if isinstance(pipeline, dict) and pipeline.get("status") == "ATENCAO":
        score -= 5
        reasons.append({"code": "PIPELINE_ATTENTION", "title": "Pipeline em atenção", "impact": 5, "level": "WARNING"})
    elif isinstance(pipeline, dict) and pipeline.get("status") == "ERRO":
        score -= 25
        reasons.append({"code": "PIPELINE_ERROR", "title": "Pipeline em erro", "impact": 25, "level": "CRITICAL"})

    score = max(0, min(100, int(score)))

    if score >= 90:
        label = "EXCELENTE"
    elif score >= 80:
        label = "BOM"
    elif score >= 70:
        label = "ATENÇÃO"
    else:
        label = "CRÍTICO"

    return {
        "score": score,
        "label": label,
        "reasons": reasons,
    }


def executive_alert_manager_health() -> Dict[str, Any]:
    state = _read_json(EXECUTIVE_ALERT_STATE_FILE, {})
    return {
        "ok": True,
        "module": "executive_alert_manager",
        "loaded": True,
        "enabled": EXECUTIVE_ALERTS_ENABLED,
        "version": VERSION,
        "generated_at": _now_br(),
        "pipeline_loaded": callable(build_execution_pipeline_status),
        "pipeline_import_error": PIPELINE_IMPORT_ERROR,
        "cooldown_seconds": EXECUTIVE_ALERT_COOLDOWN_SECONDS,
        "recovery_alerts_enabled": EXECUTIVE_RECOVERY_ALERTS_ENABLED,
        "known_alerts": len((state.get("alerts") or {}) if isinstance(state, dict) else {}),
        "files": {
            "state": str(EXECUTIVE_ALERT_STATE_FILE),
            "log": str(EXECUTIVE_ALERT_LOG_FILE),
        },
        "thresholds": {
            "pending_outcome_warning": PENDING_OUTCOME_WARNING,
            "pending_outcome_critical": PENDING_OUTCOME_CRITICAL,
            "paper_open_warning": PAPER_OPEN_WARNING,
            "paper_open_critical": PAPER_OPEN_CRITICAL,
            "central_positions_warning": CENTRAL_POSITIONS_WARNING,
            "central_positions_critical": CENTRAL_POSITIONS_CRITICAL,
            "side_concentration_warning_pct": SIDE_CONCENTRATION_WARNING_PCT,
            "side_concentration_critical_pct": SIDE_CONCENTRATION_CRITICAL_PCT,
            "adaptive_confidence_action_min": ADAPTIVE_CONFIDENCE_ACTION_MIN,
        },
        "notes": [
            "V2 calcula Health Score operacional interno.",
            "V2 detecta recuperação de alertas ativos.",
            "V2 continua sem enviar Telegram diretamente; main deve enviar alerts_to_notify.",
        ],
    }


def _collect_alerts_from_pipeline(pipeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []

    components = _component_statuses(pipeline)
    component_labels = {
        "execution_engine": "Execution Engine",
        "paper_executor": "Paper Executor",
        "paper_lifecycle": "Paper Lifecycle",
        "outcome_evaluator": "Outcome Evaluator",
        "adaptive_weights": "Adaptive Weights",
    }

    for comp, ok in components.items():
        if not ok:
            label = component_labels.get(comp, comp)
            alerts.append(_new_alert(
                level="CRITICAL",
                category="PIPELINE",
                code=f"{comp.upper()}_OFFLINE",
                title=f"{label} indisponível",
                message=f"O componente {label} não está saudável.",
                action=f"Verificar {label} antes de continuar a operação autônoma.",
                data={"component": comp},
                impact_score=25,
            ))

    if pipeline.get("status") == "ERRO":
        alerts.append(_new_alert(
            level="CRITICAL",
            category="PIPELINE",
            code="PIPELINE_STATUS_ERROR",
            title="Pipeline em ERRO",
            message="O status consolidado do pipeline retornou ERRO.",
            action="Investigar os componentes do pipeline imediatamente.",
            data={"pipeline_status": pipeline.get("status")},
            impact_score=25,
        ))

    positions = pipeline.get("positions") or {}
    pending = _safe_int(positions.get("pending_outcome"))
    paper_open = _safe_int(positions.get("open"))
    paper_closed = _safe_int(positions.get("closed"))

    if pending >= PENDING_OUTCOME_CRITICAL:
        alerts.append(_new_alert(
            level="CRITICAL",
            category="OUTCOME",
            code="PENDING_OUTCOME_CRITICAL",
            title="Muitos outcomes pendentes",
            message=f"Há {pending} trade(s) fechado(s) aguardando Outcome Evaluator.",
            action="Rodar /outcome/evaluate e verificar se o Outcome Evaluator está persistindo resultados.",
            data={"pending_outcome": pending},
            impact_score=20,
        ))
    elif pending >= PENDING_OUTCOME_WARNING:
        alerts.append(_new_alert(
            level="WARNING",
            category="OUTCOME",
            code="PENDING_OUTCOME_WARNING",
            title="Outcomes pendentes",
            message=f"Há {pending} trade(s) fechado(s) aguardando avaliação.",
            action="Acompanhar. Se persistir, rodar /outcome/evaluate.",
            data={"pending_outcome": pending},
            impact_score=8,
        ))

    if paper_open >= PAPER_OPEN_CRITICAL:
        alerts.append(_new_alert(
            level="CRITICAL",
            category="PAPER",
            code="PAPER_OPEN_CRITICAL",
            title="Excesso de posições PAPER abertas",
            message=f"Há {paper_open} posição(ões) PAPER abertas.",
            action="Verificar Paper Lifecycle e critérios de fechamento.",
            data={"paper_open": paper_open},
            impact_score=15,
        ))
    elif paper_open >= PAPER_OPEN_WARNING:
        alerts.append(_new_alert(
            level="WARNING",
            category="PAPER",
            code="PAPER_OPEN_WARNING",
            title="Muitas posições PAPER abertas",
            message=f"Há {paper_open} posição(ões) PAPER abertas.",
            action="Acompanhar no CEO Daily.",
            data={"paper_open": paper_open},
            impact_score=6,
        ))

    # Exposição da Central real/registry quando disponível via daily_report_summary.
    summary = pipeline.get("daily_report_summary") or {}
    central_open = _safe_int(summary.get("paper_open"), 0)
    # Se o summary não tiver central positions, não força alerta.

    adaptive = pipeline.get("adaptive") or {}
    adaptive_action = str(adaptive.get("recommended_action") or "").upper().strip()
    confidence = _safe_float(adaptive.get("confidence"))
    if adaptive_action in {"REDUCE", "PAUSE", "PAUSE_SAMPLE", "BLOCK", "DISABLE", "REDUCE_WEIGHT"} and confidence >= ADAPTIVE_CONFIDENCE_ACTION_MIN:
        alerts.append(_new_alert(
            level="WARNING",
            category="ADAPTIVE",
            code=f"ADAPTIVE_{adaptive_action}",
            title=f"Adaptive recomenda {adaptive_action}",
            message=f"Adaptive Weights recomenda {adaptive_action} com confiança estatística de {confidence:.1f}%.",
            action="Revisar Adaptive Weights antes de alterar pesos/lotes.",
            data={"adaptive_action": adaptive_action, "confidence": confidence, "adaptive": adaptive},
            impact_score=10,
        ))

    if bool(pipeline.get("real_execution_enabled")):
        alerts.append(_new_alert(
            level="CRITICAL",
            category="EXECUTION",
            code="REAL_EXECUTION_ENABLED",
            title="Execução real ativada",
            message="A execução real está ativada.",
            action="Confirmar se a ativação foi intencional e se o stop de desastre está configurado.",
            data={"real_execution_enabled": True},
            impact_score=30,
        ))

    memory_pct = _extract_memory_pct(pipeline)
    if memory_pct is not None:
        if memory_pct >= MEMORY_CRITICAL_PCT:
            alerts.append(_new_alert(
                level="CRITICAL",
                category="MEMORY",
                code="MEMORY_CRITICAL",
                title="Memória Render crítica",
                message=f"Uso de memória em {memory_pct:.1f}%. Risco de restart.",
                action="Reduzir relatórios pesados, verificar vazamento e considerar GC/deploy.",
                data={"memory_pct": memory_pct},
                impact_score=20,
            ))
        elif memory_pct >= MEMORY_WARNING_PCT:
            alerts.append(_new_alert(
                level="WARNING",
                category="MEMORY",
                code="MEMORY_WARNING",
                title="Memória Render elevada",
                message=f"Uso de memória em {memory_pct:.1f}%.",
                action="Monitorar e evitar relatórios pesados.",
                data={"memory_pct": memory_pct},
                impact_score=8,
            ))

    return alerts


def build_executive_alerts(check_only: bool = False) -> Dict[str, Any]:
    generated_at = _now_br()
    now_epoch = time.time()

    if not EXECUTIVE_ALERTS_ENABLED:
        return {
            "ok": True,
            "enabled": False,
            "status": "DISABLED",
            "generated_at": generated_at,
            "version": VERSION,
            "health_score": {"score": 100, "label": "DISABLED", "reasons": []},
            "alerts": [],
            "alerts_to_notify": [],
            "resolved": [],
        }

    pipeline = {}
    if not callable(build_execution_pipeline_status):
        alerts = [_new_alert(
            level="CRITICAL",
            category="PIPELINE",
            code="PIPELINE_STATUS_UNAVAILABLE",
            title="Pipeline Status indisponível",
            message="O Executive Alert Manager não conseguiu carregar execution_pipeline_status.py.",
            action="Verificar import do execution_pipeline_status.py.",
            data={"import_error": PIPELINE_IMPORT_ERROR},
            impact_score=30,
        )]
    else:
        try:
            pipeline = build_execution_pipeline_status()
            alerts = _collect_alerts_from_pipeline(pipeline)
        except Exception as exc:
            alerts = [_new_alert(
                level="CRITICAL",
                category="PIPELINE",
                code="PIPELINE_STATUS_ERROR",
                title="Erro ao ler Pipeline Status",
                message=f"O status consolidado do pipeline falhou: {exc}",
                action="Verificar logs do Render e execution_pipeline_status.py.",
                data={"error": str(exc)},
                impact_score=30,
            )]

    health_score = _calculate_health_score(alerts, pipeline)

    state = _read_json(EXECUTIVE_ALERT_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    known = state.get("alerts") or {}
    if not isinstance(known, dict):
        known = {}

    alerts_to_notify = []

    for alert in alerts:
        key = alert.get("alert_key")
        old = known.get(key) or {}
        last_notified = _safe_float(old.get("last_notified_epoch"), 0.0)

        should_notify = False
        if alert.get("level") in {"CRITICAL", "WARNING"}:
            should_notify = (now_epoch - last_notified) >= EXECUTIVE_ALERT_COOLDOWN_SECONDS

        alert["notify"] = bool(should_notify)
        alert["previously_active"] = bool(old.get("active"))

        if should_notify:
            alerts_to_notify.append(alert)

        known[key] = {
            "first_seen_at": old.get("first_seen_at") or generated_at,
            "first_seen_epoch": old.get("first_seen_epoch") or now_epoch,
            "last_seen_at": generated_at,
            "last_seen_epoch": now_epoch,
            "last_notified_at": generated_at if should_notify else old.get("last_notified_at"),
            "last_notified_epoch": now_epoch if should_notify else old.get("last_notified_epoch"),
            "level": alert.get("level"),
            "category": alert.get("category"),
            "code": alert.get("code"),
            "title": alert.get("title"),
            "active": True,
            "count": _safe_int(old.get("count")) + 1,
        }

    active_keys = {a.get("alert_key") for a in alerts}
    resolved = []
    recovery_to_notify = []

    for key, old in list(known.items()):
        if key not in active_keys and old.get("active"):
            old["active"] = False
            old["resolved_at"] = generated_at
            old["resolved_epoch"] = now_epoch
            known[key] = old

            recovery = {
                "level": "RECOVERY",
                "category": old.get("category"),
                "code": f"{old.get('code')}_RESOLVED",
                "title": f"Resolvido: {old.get('title')}",
                "message": f"O alerta '{old.get('title')}' foi resolvido.",
                "action": "Nenhuma ação necessária se o status permanecer normal.",
                "alert_key": key,
                "generated_at": generated_at,
                "epoch": now_epoch,
                "version": VERSION,
                "resolved_alert": {
                    "title": old.get("title"),
                    "category": old.get("category"),
                    "code": old.get("code"),
                    "first_seen_at": old.get("first_seen_at"),
                    "resolved_at": generated_at,
                },
            }
            resolved.append(recovery)
            if EXECUTIVE_RECOVERY_ALERTS_ENABLED and old.get("level") == "CRITICAL":
                recovery_to_notify.append(recovery)

    alerts_to_notify.extend(recovery_to_notify)

    result = {
        "ok": True,
        "enabled": True,
        "status": "ALERTS_FOUND" if alerts else "NO_ALERTS",
        "generated_at": generated_at,
        "version": VERSION,
        "health_score": health_score,
        "alerts_count": len(alerts),
        "alerts_to_notify_count": len(alerts_to_notify),
        "alerts": alerts,
        "alerts_to_notify": alerts_to_notify,
        "resolved": resolved,
        "pipeline_status": pipeline.get("status") if isinstance(pipeline, dict) else None,
        "executive_summary": _build_executive_summary(health_score, alerts, resolved),
        "notes": [
            "CRITICAL e WARNING podem gerar notificação conforme cooldown.",
            "RECOVERY pode notificar quando um alerta crítico é resolvido.",
            "V2 calcula Health Score para uso interno e CEO Daily.",
        ],
    }

    if not check_only:
        state = {
            "updated_at": generated_at,
            "updated_epoch": now_epoch,
            "alerts": known,
            "last_result": {
                "status": result.get("status"),
                "health_score": health_score,
                "alerts_count": result.get("alerts_count"),
                "alerts_to_notify_count": result.get("alerts_to_notify_count"),
                "resolved_count": len(resolved),
            },
            "version": VERSION,
        }
        _write_json(EXECUTIVE_ALERT_STATE_FILE, state)
        _append_jsonl(EXECUTIVE_ALERT_LOG_FILE, {
            "event": "EXECUTIVE_ALERT_CHECK",
            "generated_at": generated_at,
            "epoch": now_epoch,
            "version": VERSION,
            "health_score": health_score,
            "alerts_count": len(alerts),
            "alerts_to_notify_count": len(alerts_to_notify),
            "alerts": alerts,
            "alerts_to_notify": alerts_to_notify,
            "resolved": resolved,
        })

    return result


def _build_executive_summary(health_score: Dict[str, Any], alerts: List[Dict[str, Any]], resolved: List[Dict[str, Any]]) -> str:
    score = _safe_int(health_score.get("score"), 100)
    if not alerts:
        if resolved:
            return "A Central está saudável e alguns alertas anteriores foram resolvidos."
        return "A Central está saudável. Nenhuma interrupção do CEO é necessária."

    critical = [a for a in alerts if a.get("level") == "CRITICAL"]
    warning = [a for a in alerts if a.get("level") == "WARNING"]

    if critical:
        return f"A Central requer atenção imediata: {len(critical)} alerta(s) crítico(s) ativo(s)."
    if warning:
        return f"A Central opera com atenção: {len(warning)} alerta(s) de warning ativo(s)."
    return f"A Central possui alertas informativos. Health Score atual: {score}/100."


def build_executive_alert_text(alert: Dict[str, Any]) -> str:
    level = str(alert.get("level") or "INFO").upper()
    emoji = "🚨" if level == "CRITICAL" else ("⚠️" if level == "WARNING" else ("✅" if level == "RECOVERY" else "ℹ️"))

    return "\n".join([
        f"{emoji} CENTRAL QUANT — EXECUTIVE ALERT",
        "",
        f"Nível: {level}",
        f"Categoria: {alert.get('category')}",
        f"Título: {alert.get('title')}",
        "",
        "Resumo:",
        str(alert.get("message") or ""),
        "",
        "Ação sugerida:",
        str(alert.get("action") or "Nenhuma ação definida."),
        "",
        f"Data/hora: {_now_br()}",
    ])


def build_executive_alerts_text(limit: int = 10, notify_only: bool = False) -> str:
    result = build_executive_alerts(check_only=True)
    alerts = result.get("alerts_to_notify") if notify_only else result.get("alerts")
    alerts = alerts or []
    health = result.get("health_score") or {}

    lines = [
        "🚨 EXECUTIVE ALERT MANAGER — CENTRAL QUANT",
        f"Data/hora: {_now_br()}",
        f"Status: {result.get('status')}",
        f"Health Score: {health.get('score', 100)}/100 — {health.get('label', 'OK')}",
        f"Alertas ativos: {result.get('alerts_count', 0)}",
        f"Alertas para notificar: {result.get('alerts_to_notify_count', 0)}",
        "",
        str(result.get("executive_summary") or ""),
        "",
    ]

    if not alerts:
        lines += [
            "Nenhum alerta executivo ativo.",
            "",
            "A Central não precisa interromper o CEO neste momento.",
        ]
        return "\n".join(lines)

    for alert in alerts[:max(1, int(limit))]:
        emoji = "🚨" if alert.get("level") == "CRITICAL" else "⚠️"
        lines += [
            f"{emoji} {alert.get('title')}",
            f"- Nível: {alert.get('level')}",
            f"- Categoria: {alert.get('category')}",
            f"- Resumo: {alert.get('message')}",
            f"- Ação: {alert.get('action')}",
            "",
        ]

    return "\n".join(lines).strip()


def read_executive_alert_log(limit: int = 20) -> Dict[str, Any]:
    if not EXECUTIVE_ALERT_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = EXECUTIVE_ALERT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, int(limit)):]

    items = []
    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            continue

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(items),
        "items": items,
    }
