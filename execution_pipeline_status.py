# execution_pipeline_status.py
# CENTRAL QUANT — EXECUTION PIPELINE STATUS V1
# Versão: 2026-07-04-EXECUTION-PIPELINE-STATUS-V1
#
# Objetivo:
# - Consolidar em um único status a saúde do pipeline:
#   Execution Engine → Paper Executor → Paper Lifecycle → Outcome Evaluator → Adaptive Weights
# - Servir como fonte para relatório diário/autonomia da Central.
# - Não executa trade, não altera risco e não chama corretora.
#
# Arquivo:
#   /opt/render/project/src/execution_pipeline_status.py

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


VERSION = "2026-07-04-EXECUTION-PIPELINE-STATUS-V1"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
OUTCOME_STATS_FILE = DATA_DIR / "outcome_stats.json"
ADAPTIVE_WEIGHTS_FILE = DATA_DIR / "adaptive_weights.json"


try:
    from execution_engine import execution_engine_health
except Exception as exc:
    execution_engine_health = None
    EXECUTION_ENGINE_IMPORT_ERROR = str(exc)
else:
    EXECUTION_ENGINE_IMPORT_ERROR = None


try:
    from paper_executor_integrated import paper_integrated_health
except Exception as exc:
    paper_integrated_health = None
    PAPER_EXECUTOR_IMPORT_ERROR = str(exc)
else:
    PAPER_EXECUTOR_IMPORT_ERROR = None


try:
    from paper_lifecycle import paper_lifecycle_health
except Exception as exc:
    paper_lifecycle_health = None
    PAPER_LIFECYCLE_IMPORT_ERROR = str(exc)
else:
    PAPER_LIFECYCLE_IMPORT_ERROR = None


try:
    from outcome_evaluator import outcome_evaluator_health
except Exception as exc:
    outcome_evaluator_health = None
    OUTCOME_EVALUATOR_IMPORT_ERROR = str(exc)
else:
    OUTCOME_EVALUATOR_IMPORT_ERROR = None


try:
    from adaptive_weights import adaptive_weights_health, get_adaptive_weights
except Exception as exc:
    adaptive_weights_health = None
    get_adaptive_weights = None
    ADAPTIVE_WEIGHTS_IMPORT_ERROR = str(exc)
else:
    ADAPTIVE_WEIGHTS_IMPORT_ERROR = None


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _safe_call(fn):
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _positions_summary() -> Dict[str, Any]:
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    if not isinstance(positions, list):
        positions = []

    open_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "OPEN"]
    closed_positions = [p for p in positions if isinstance(p, dict) and p.get("status") == "CLOSED"]
    pending_outcome = [p for p in closed_positions if not p.get("outcome_evaluated")]

    last_trade = None
    valid = [p for p in positions if isinstance(p, dict)]
    if valid:
        last_trade = sorted(
            valid,
            key=lambda p: p.get("closed_epoch") or p.get("opened_epoch") or 0,
            reverse=True,
        )[0]

    return {
        "total": len(valid),
        "open": len(open_positions),
        "closed": len(closed_positions),
        "pending_outcome": len(pending_outcome),
        "last_trade": last_trade,
    }


def _outcome_summary() -> Dict[str, Any]:
    stats = _read_json(OUTCOME_STATS_FILE, {})
    global_stats = stats.get("global") if isinstance(stats, dict) else {}
    if not isinstance(global_stats, dict):
        global_stats = {}

    return {
        "exists": OUTCOME_STATS_FILE.exists(),
        "updated_at": stats.get("updated_at") if isinstance(stats, dict) else None,
        "trades": global_stats.get("trades", 0),
        "wins": global_stats.get("wins", 0),
        "losses": global_stats.get("losses", 0),
        "win_rate_pct": global_stats.get("win_rate_pct", 0.0),
        "tp50_hit_rate_pct": global_stats.get("tp50_hit_rate_pct", 0.0),
        "pnl_total_pct": global_stats.get("pnl_total_pct", 0.0),
        "r_total": global_stats.get("r_total", 0.0),
        "r_avg": global_stats.get("r_avg", 0.0),
    }


def _adaptive_summary() -> Dict[str, Any]:
    weights_payload = _safe_call(get_adaptive_weights)
    weights = {}
    if isinstance(weights_payload, dict):
        weights = weights_payload.get("weights") or {}

    global_w = weights.get("global") if isinstance(weights, dict) else {}
    if not isinstance(global_w, dict):
        global_w = {}

    return {
        "exists": ADAPTIVE_WEIGHTS_FILE.exists(),
        "updated_at": weights.get("updated_at") if isinstance(weights, dict) else None,
        "source_outcome_updated_at": weights.get("source_outcome_updated_at") if isinstance(weights, dict) else None,
        "trades": global_w.get("trades", 0),
        "confidence": global_w.get("confidence"),
        "recommended_action": global_w.get("recommended_action"),
        "suggested_weight": global_w.get("suggested_weight"),
        "reason": global_w.get("reason"),
    }


def build_execution_pipeline_status() -> Dict[str, Any]:
    engine = _safe_call(execution_engine_health)
    paper = _safe_call(paper_integrated_health)
    lifecycle = _safe_call(paper_lifecycle_health)
    outcome = _safe_call(outcome_evaluator_health)
    adaptive = _safe_call(adaptive_weights_health)

    positions = _positions_summary()
    outcome_summary = _outcome_summary()
    adaptive_summary = _adaptive_summary()

    components = {
        "execution_engine": {
            "ok": bool(engine and engine.get("ok")),
            "loaded": callable(execution_engine_health),
            "import_error": EXECUTION_ENGINE_IMPORT_ERROR,
            "health": engine,
        },
        "paper_executor": {
            "ok": bool(paper and paper.get("ok")),
            "loaded": callable(paper_integrated_health),
            "import_error": PAPER_EXECUTOR_IMPORT_ERROR,
            "health": paper,
        },
        "paper_lifecycle": {
            "ok": bool(lifecycle and lifecycle.get("ok")),
            "loaded": callable(paper_lifecycle_health),
            "import_error": PAPER_LIFECYCLE_IMPORT_ERROR,
            "health": lifecycle,
        },
        "outcome_evaluator": {
            "ok": bool(outcome and outcome.get("ok")),
            "loaded": callable(outcome_evaluator_health),
            "import_error": OUTCOME_EVALUATOR_IMPORT_ERROR,
            "health": outcome,
        },
        "adaptive_weights": {
            "ok": bool(adaptive and adaptive.get("ok")),
            "loaded": callable(adaptive_weights_health),
            "import_error": ADAPTIVE_WEIGHTS_IMPORT_ERROR,
            "health": adaptive,
        },
    }

    alerts = []
    if not components["execution_engine"]["ok"]:
        alerts.append("Execution Engine indisponível.")
    if not components["paper_executor"]["ok"]:
        alerts.append("Paper Executor indisponível.")
    if not components["paper_lifecycle"]["ok"]:
        alerts.append("Paper Lifecycle indisponível.")
    if not components["outcome_evaluator"]["ok"]:
        alerts.append("Outcome Evaluator indisponível.")
    if not components["adaptive_weights"]["ok"]:
        alerts.append("Adaptive Weights indisponível.")
    if positions["pending_outcome"] > 0:
        alerts.append(f"{positions['pending_outcome']} trade(s) fechado(s) pendente(s) de Outcome.")
    if positions["open"] > 0:
        alerts.append(f"{positions['open']} posição(ões) PAPER aberta(s).")

    real_enabled = False
    try:
        real_enabled = bool(engine.get("real_execution_enabled")) if isinstance(engine, dict) else False
    except Exception:
        real_enabled = False

    status = "OK" if not alerts else "ATENCAO"
    if not all(v["ok"] for v in components.values()):
        status = "ERRO"

    return {
        "ok": status != "ERRO",
        "status": status,
        "version": VERSION,
        "generated_at": _now_br(),
        "real_execution_enabled": real_enabled,
        "real_execution_status": "ENABLED" if real_enabled else "BLOCKED",
        "pipeline": {
            "route": "EXECUTION_ENGINE_TO_PAPER_EXECUTOR_TO_LIFECYCLE_TO_OUTCOME_TO_ADAPTIVE_WEIGHTS",
            "components_ok": all(v["ok"] for v in components.values()),
            "components": components,
        },
        "positions": positions,
        "outcome": outcome_summary,
        "adaptive": adaptive_summary,
        "alerts": alerts,
        "daily_report_summary": {
            "engine": "OK" if components["execution_engine"]["ok"] else "ERRO",
            "paper_executor": "OK" if components["paper_executor"]["ok"] else "ERRO",
            "lifecycle": "OK" if components["paper_lifecycle"]["ok"] else "ERRO",
            "outcome": "OK" if components["outcome_evaluator"]["ok"] else "ERRO",
            "adaptive": "OK" if components["adaptive_weights"]["ok"] else "ERRO",
            "paper_open": positions["open"],
            "paper_closed": positions["closed"],
            "pending_outcome": positions["pending_outcome"],
            "evaluated_trades": outcome_summary.get("trades"),
            "adaptive_action": adaptive_summary.get("recommended_action"),
            "adaptive_confidence": adaptive_summary.get("confidence"),
            "real_execution": "BLOQUEADA" if not real_enabled else "ATIVA",
        },
        "notes": [
            "Status consolidado para uso interno e relatório diário.",
            "Não executa trade e não altera risco.",
            "Serve para detectar travas no pipeline autônomo.",
        ],
    }


def build_execution_pipeline_text() -> str:
    data = build_execution_pipeline_status()
    s = data.get("daily_report_summary") or {}
    alerts = data.get("alerts") or []

    lines = [
        "⚙️ EXECUTION PIPELINE — CENTRAL QUANT",
        f"Data/hora: {data.get('generated_at')}",
        f"Status: {data.get('status')}",
        "",
        "Componentes:",
        f"- Execution Engine: {s.get('engine')}",
        f"- Paper Executor: {s.get('paper_executor')}",
        f"- Paper Lifecycle: {s.get('lifecycle')}",
        f"- Outcome Evaluator: {s.get('outcome')}",
        f"- Adaptive Weights: {s.get('adaptive')}",
        "",
        "Execução:",
        f"- Execução real: {s.get('real_execution')}",
        f"- PAPER abertas: {s.get('paper_open')}",
        f"- PAPER fechadas: {s.get('paper_closed')}",
        f"- Outcomes pendentes: {s.get('pending_outcome')}",
        f"- Outcomes avaliados: {s.get('evaluated_trades')}",
        "",
        "Aprendizado:",
        f"- Adaptive action: {s.get('adaptive_action')}",
        f"- Adaptive confidence: {s.get('adaptive_confidence')}",
        "",
        "Alertas:",
    ]

    if not alerts:
        lines.append("- Nenhum alerta no pipeline ✅")
    else:
        for item in alerts:
            lines.append(f"- {item}")

    lines += [
        "",
        "Observação:",
        "Este status é para autonomia e relatório diário, não para acompanhamento manual contínuo.",
    ]

    return "\n".join(lines)
