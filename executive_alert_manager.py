# executive_alert_manager.py
# CENTRAL QUANT — EXECUTIVE ALERT MANAGER V1
# Versão: 2026-07-04-EXECUTIVE-ALERT-MANAGER-V1

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

VERSION = "2026-07-04-EXECUTIVE-ALERT-MANAGER-V1"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTIVE_ALERT_STATE_FILE = DATA_DIR / "executive_alert_state.json"
EXECUTIVE_ALERT_LOG_FILE = DATA_DIR / "executive_alert_log.jsonl"

EXECUTIVE_ALERTS_ENABLED = os.getenv("CENTRAL_EXECUTIVE_ALERTS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "sim", "on"}
EXECUTIVE_ALERT_COOLDOWN_SECONDS = int(os.getenv("CENTRAL_EXECUTIVE_ALERT_COOLDOWN_SECONDS", "3600"))

MEMORY_WARNING_PCT = float(os.getenv("EXEC_ALERT_MEMORY_WARNING_PCT", "85"))
MEMORY_CRITICAL_PCT = float(os.getenv("EXEC_ALERT_MEMORY_CRITICAL_PCT", "92"))
PENDING_OUTCOME_WARNING = int(os.getenv("EXEC_ALERT_PENDING_OUTCOME_WARNING", "3"))
PENDING_OUTCOME_CRITICAL = int(os.getenv("EXEC_ALERT_PENDING_OUTCOME_CRITICAL", "8"))
PAPER_OPEN_WARNING = int(os.getenv("EXEC_ALERT_PAPER_OPEN_WARNING", "10"))
PAPER_OPEN_CRITICAL = int(os.getenv("EXEC_ALERT_PAPER_OPEN_CRITICAL", "20"))
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


def _alert_key(alert: Dict[str, Any]) -> str:
    base = {
        "level": alert.get("level"),
        "category": alert.get("category"),
        "code": alert.get("code"),
        "title": alert.get("title"),
    }
    raw = json.dumps(base, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24].upper()


def _component_ok(pipeline: Dict[str, Any], name: str) -> bool:
    try:
        return bool((((pipeline.get("pipeline") or {}).get("components") or {}).get(name) or {}).get("ok"))
    except Exception:
        return False


def _new_alert(level: str, category: str, code: str, title: str, message: str, action: str, data=None) -> Dict[str, Any]:
    alert = {
        "level": level,
        "category": category,
        "code": code,
        "title": title,
        "message": message,
        "action": action,
        "data": data or {},
        "generated_at": _now_br(),
        "epoch": time.time(),
        "version": VERSION,
    }
    alert["alert_key"] = _alert_key(alert)
    return alert


def executive_alert_manager_health() -> Dict[str, Any]:
    state = _read_json(EXECUTIVE_ALERT_STATE_FILE, {})
    alerts = state.get("alerts") if isinstance(state, dict) else {}
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
        "known_alerts": len(alerts or {}),
        "files": {"state": str(EXECUTIVE_ALERT_STATE_FILE), "log": str(EXECUTIVE_ALERT_LOG_FILE)},
        "notes": [
            "Executive Alert Manager decide quando avisar o CEO.",
            "V1 não envia Telegram diretamente; gera alerts_to_notify para o main enviar.",
            "Evita spam usando cooldown por alerta.",
        ],
    }


def build_executive_alerts(check_only: bool = False) -> Dict[str, Any]:
    generated_at = _now_br()

    if not EXECUTIVE_ALERTS_ENABLED:
        return {"ok": True, "enabled": False, "status": "DISABLED", "generated_at": generated_at, "version": VERSION, "alerts": [], "alerts_to_notify": []}

    alerts = []
    pipeline = {}

    if not callable(build_execution_pipeline_status):
        alerts.append(_new_alert(
            "CRITICAL", "PIPELINE", "PIPELINE_STATUS_UNAVAILABLE", "Pipeline Status indisponível",
            "O Executive Alert Manager não conseguiu carregar o status consolidado do pipeline.",
            "Verificar import do execution_pipeline_status.py.",
            {"import_error": PIPELINE_IMPORT_ERROR},
        ))
    else:
        try:
            pipeline = build_execution_pipeline_status()
        except Exception as exc:
            alerts.append(_new_alert(
                "CRITICAL", "PIPELINE", "PIPELINE_STATUS_ERROR", "Erro ao ler Pipeline Status",
                f"O status consolidado do pipeline falhou: {exc}",
                "Verificar logs do Render e execution_pipeline_status.py.",
                {"error": str(exc)},
            ))

    if pipeline:
        component_labels = {
            "execution_engine": "Execution Engine",
            "paper_executor": "Paper Executor",
            "paper_lifecycle": "Paper Lifecycle",
            "outcome_evaluator": "Outcome Evaluator",
            "adaptive_weights": "Adaptive Weights",
        }
        for comp, label in component_labels.items():
            if not _component_ok(pipeline, comp):
                alerts.append(_new_alert(
                    "CRITICAL", "PIPELINE", f"{comp.upper()}_OFFLINE", f"{label} indisponível",
                    f"O componente {label} não está saudável.",
                    f"Verificar {label} antes de permitir evolução do pipeline.",
                    {"component": comp},
                ))

        positions = pipeline.get("positions") or {}
        pending = _safe_int(positions.get("pending_outcome"))
        if pending >= PENDING_OUTCOME_CRITICAL:
            alerts.append(_new_alert("CRITICAL", "OUTCOME", "PENDING_OUTCOME_CRITICAL", "Muitos outcomes pendentes", f"Há {pending} trade(s) fechado(s) aguardando avaliação.", "Rodar /outcome/evaluate e verificar Outcome Evaluator.", {"pending_outcome": pending}))
        elif pending >= PENDING_OUTCOME_WARNING:
            alerts.append(_new_alert("WARNING", "OUTCOME", "PENDING_OUTCOME_WARNING", "Outcomes pendentes", f"Há {pending} trade(s) fechado(s) aguardando avaliação.", "Acompanhar no CEO Daily ou rodar /outcome/evaluate.", {"pending_outcome": pending}))

        paper_open = _safe_int(positions.get("open"))
        if paper_open >= PAPER_OPEN_CRITICAL:
            alerts.append(_new_alert("CRITICAL", "PAPER", "PAPER_OPEN_CRITICAL", "Excesso de posições PAPER abertas", f"Há {paper_open} posição(ões) PAPER abertas.", "Verificar Paper Lifecycle e fechamento das posições.", {"paper_open": paper_open}))
        elif paper_open >= PAPER_OPEN_WARNING:
            alerts.append(_new_alert("WARNING", "PAPER", "PAPER_OPEN_WARNING", "Muitas posições PAPER abertas", f"Há {paper_open} posição(ões) PAPER abertas.", "Acompanhar no CEO Daily.", {"paper_open": paper_open}))

        adaptive = pipeline.get("adaptive") or {}
        adaptive_action = str(adaptive.get("recommended_action") or "").upper().strip()
        confidence = _safe_float(adaptive.get("confidence"))
        if adaptive_action in {"REDUCE", "PAUSE", "PAUSE_SAMPLE", "BLOCK", "DISABLE"} and confidence >= ADAPTIVE_CONFIDENCE_ACTION_MIN:
            alerts.append(_new_alert(
                "WARNING", "ADAPTIVE", f"ADAPTIVE_{adaptive_action}", f"Adaptive recomenda {adaptive_action}",
                f"Adaptive Weights recomenda {adaptive_action} com confiança estatística de {confidence:.1f}%.",
                "Revisar Adaptive Weights antes de alterar pesos/lotes.",
                {"adaptive_action": adaptive_action, "confidence": confidence, "adaptive": adaptive},
            ))

        if bool(pipeline.get("real_execution_enabled")):
            alerts.append(_new_alert(
                "CRITICAL", "EXECUTION", "REAL_EXECUTION_ENABLED", "Execução real ativada",
                "A execução real está ativada.",
                "Confirmar se a ativação foi intencional e se o stop de desastre está configurado.",
                {"real_execution_enabled": True},
            ))

        if pipeline.get("status") == "ERRO":
            alerts.append(_new_alert("CRITICAL", "PIPELINE", "PIPELINE_STATUS_ERROR_GLOBAL", "Pipeline em ERRO", "O status consolidado do pipeline retornou ERRO.", "Investigar componentes do pipeline imediatamente.", {"status": pipeline.get("status")}))

    state = _read_json(EXECUTIVE_ALERT_STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    known = state.get("alerts") or {}
    if not isinstance(known, dict):
        known = {}

    now_epoch = time.time()
    alerts_to_notify = []

    for alert in alerts:
        key = alert.get("alert_key")
        old = known.get(key) or {}
        last_notified = _safe_float(old.get("last_notified_epoch"), 0.0)
        should_notify = (now_epoch - last_notified) >= EXECUTIVE_ALERT_COOLDOWN_SECONDS
        alert["notify"] = bool(should_notify)
        if should_notify:
            alerts_to_notify.append(alert)
        known[key] = {
            **old,
            "first_seen_at": old.get("first_seen_at") or generated_at,
            "first_seen_epoch": old.get("first_seen_epoch") or now_epoch,
            "last_seen_at": generated_at,
            "last_seen_epoch": now_epoch,
            "level": alert.get("level"),
            "category": alert.get("category"),
            "code": alert.get("code"),
            "title": alert.get("title"),
            "active": True,
            "count": _safe_int(old.get("count")) + 1,
        }
        if should_notify:
            known[key]["last_notified_at"] = generated_at
            known[key]["last_notified_epoch"] = now_epoch

    active_keys = {a.get("alert_key") for a in alerts}
    resolved = []
    for key, old in list(known.items()):
        if key not in active_keys and old.get("active"):
            old["active"] = False
            old["resolved_at"] = generated_at
            old["resolved_epoch"] = now_epoch
            known[key] = old
            resolved.append({"alert_key": key, "title": old.get("title"), "category": old.get("category"), "code": old.get("code"), "resolved_at": generated_at})

    result = {
        "ok": True,
        "enabled": True,
        "status": "ALERTS_FOUND" if alerts else "NO_ALERTS",
        "generated_at": generated_at,
        "version": VERSION,
        "alerts_count": len(alerts),
        "alerts_to_notify_count": len(alerts_to_notify),
        "alerts": alerts,
        "alerts_to_notify": alerts_to_notify,
        "resolved": resolved,
        "pipeline_status": pipeline.get("status") if isinstance(pipeline, dict) else None,
    }

    if not check_only:
        _write_json(EXECUTIVE_ALERT_STATE_FILE, {
            "updated_at": generated_at,
            "updated_epoch": now_epoch,
            "alerts": known,
            "last_result": {"status": result.get("status"), "alerts_count": len(alerts), "alerts_to_notify_count": len(alerts_to_notify)},
            "version": VERSION,
        })
        _append_jsonl(EXECUTIVE_ALERT_LOG_FILE, {
            "event": "EXECUTIVE_ALERT_CHECK",
            "generated_at": generated_at,
            "epoch": now_epoch,
            "version": VERSION,
            "alerts_count": len(alerts),
            "alerts_to_notify_count": len(alerts_to_notify),
            "alerts": alerts,
            "alerts_to_notify": alerts_to_notify,
            "resolved": resolved,
        })

    return result


def build_executive_alert_text(alert: Dict[str, Any]) -> str:
    level = str(alert.get("level") or "INFO").upper()
    emoji = "🚨" if level == "CRITICAL" else ("⚠️" if level == "WARNING" else "ℹ️")
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
    lines = [
        "🚨 EXECUTIVE ALERT MANAGER — CENTRAL QUANT",
        f"Data/hora: {_now_br()}",
        f"Status: {result.get('status')}",
        f"Alertas ativos: {result.get('alerts_count', 0)}",
        f"Alertas para notificar: {result.get('alerts_to_notify_count', 0)}",
        "",
    ]
    if not alerts:
        lines += ["Nenhum alerta executivo ativo.", "", "A Central não precisa interromper o CEO neste momento."]
        return "\n".join(lines)
    for alert in alerts[:max(1, int(limit))]:
        lines += [
            f"{'🚨' if alert.get('level') == 'CRITICAL' else '⚠️'} {alert.get('title')}",
            f"- Nível: {alert.get('level')}",
            f"- Categoria: {alert.get('category')}",
            f"- Resumo: {alert.get('message')}",
            f"- Ação: {alert.get('action')}",
            "",
        ]
    return "\n".join(lines).strip()


def read_executive_alert_log(limit: int = 20) -> Dict[str, Any]:
    if not EXECUTIVE_ALERT_LOG_FILE.exists():
        return {"ok": True, "generated_at": _now_br(), "count": 0, "items": []}
    lines = EXECUTIVE_ALERT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    selected = lines[-max(1, int(limit)):]
    items = []
    for line in selected:
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return {"ok": True, "generated_at": _now_br(), "count": len(items), "items": items}
