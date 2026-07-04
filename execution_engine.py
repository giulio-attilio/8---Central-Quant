# execution_engine.py
# CENTRAL QUANT — EXECUTION ENGINE V2
# Versão: 2026-07-04-EXECUTION-ENGINE-V2
#
# Objetivo:
# - Ser o ponto único de decisão antes de qualquer execução.
# - Integrar Orchestrator V1 com a arquitetura Flask da Central.
# - Manter execução real bloqueada.
# - Preparar os modos OBSERVATION_ONLY, PAPER e LIVE.
#
# Neste V2:
# - OBSERVATION_ONLY: cria plano e loga.
# - PAPER: ainda fica bloqueado até o Paper Executor integrado ser criado.
# - LIVE/REAL: sempre bloqueado enquanto CENTRAL_REAL_EXECUTION_ENABLED=false.

import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from execution_orchestrator import orchestrate_execution, execution_health
except Exception as exc:
    orchestrate_execution = None
    execution_health = None
    ORCHESTRATOR_IMPORT_ERROR = str(exc)
else:
    ORCHESTRATOR_IMPORT_ERROR = None


VERSION = "2026-07-04-EXECUTION-ENGINE-V2"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_ENGINE_LOG_FILE = DATA_DIR / "execution_engine_log.jsonl"

DEFAULT_ENGINE_MODE = os.getenv("CENTRAL_EXECUTION_ENGINE_MODE", "OBSERVATION_ONLY").upper()
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"
PAPER_EXECUTION_ENABLED = os.getenv("CENTRAL_PAPER_EXECUTION_ENABLED", "false").lower() == "true"


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_mode(value: Optional[str]) -> str:
    mode = str(value or DEFAULT_ENGINE_MODE).upper().strip()
    if mode in {"OBS", "OBSERVATION", "OBSERVATION_ONLY"}:
        return "OBSERVATION_ONLY"
    if mode in {"PAPER", "SIM", "SIMULATION"}:
        return "PAPER"
    if mode in {"LIVE", "REAL"}:
        return "LIVE"
    return "OBSERVATION_ONLY"


def execution_engine_health() -> Dict[str, Any]:
    orchestrator_payload = None
    if callable(execution_health):
        try:
            orchestrator_payload = execution_health()
        except Exception as exc:
            orchestrator_payload = {"ok": False, "error": str(exc)}

    return {
        "ok": callable(orchestrate_execution),
        "module": "execution_engine",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": DEFAULT_ENGINE_MODE,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "orchestrator_loaded": callable(orchestrate_execution),
        "orchestrator_import_error": ORCHESTRATOR_IMPORT_ERROR,
        "orchestrator": orchestrator_payload,
        "files": {
            "execution_engine_log": str(EXECUTION_ENGINE_LOG_FILE),
        },
        "notes": [
            "Execution Engine V2 é o ponto único antes de qualquer executor.",
            "Modo OBSERVATION_ONLY cria plano e loga.",
            "Modo PAPER ainda fica bloqueado até o Paper Executor integrado.",
            "Modo LIVE/REAL permanece bloqueado enquanto CENTRAL_REAL_EXECUTION_ENABLED=false.",
        ],
    }


def run_execution_engine(
    payload: Dict[str, Any],
    mode: Optional[str] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    mode = _safe_mode(mode or payload.get("mode") if isinstance(payload, dict) else None)

    if not isinstance(payload, dict):
        payload = {}

    if not callable(orchestrate_execution):
        result = {
            "ok": False,
            "status": "ENGINE_BLOCKED",
            "reason": "execution_orchestrator indisponível",
            "error": ORCHESTRATOR_IMPORT_ERROR,
            "version": VERSION,
            "generated_at": _now_br(),
        }
        _append_jsonl(EXECUTION_ENGINE_LOG_FILE, {"event": "EXECUTION_ENGINE_BLOCKED", "payload": result})
        return {"ok": False, "payload": result}

    orchestration = orchestrate_execution(
        payload=payload,
        mode=mode,
        requested_qty=payload.get("requested_qty"),
        capital_allocated=payload.get("capital_allocated"),
        dry_run=dry_run,
    )

    plan = orchestration.get("payload", {}) if isinstance(orchestration, dict) else {}

    engine_status = "PLAN_CREATED"
    engine_ok = bool(orchestration.get("ok")) if isinstance(orchestration, dict) else False
    executor_route = "NONE"

    if mode == "OBSERVATION_ONLY":
        executor_route = "PLAN_ONLY"
    elif mode == "PAPER":
        engine_ok = False
        engine_status = "PAPER_EXECUTOR_NOT_CONNECTED"
        executor_route = "PAPER_PENDING"
        plan.setdefault("errors", []).append("Paper Executor integrado ainda não conectado ao Execution Engine V2")
    elif mode == "LIVE":
        executor_route = "LIVE_BLOCKED"
        if not REAL_EXECUTION_ENABLED:
            engine_ok = False
            engine_status = "LIVE_BLOCKED"
            plan.setdefault("errors", []).append("LIVE/REAL bloqueado: CENTRAL_REAL_EXECUTION_ENABLED=false")

    result = {
        "ok": engine_ok,
        "status": engine_status,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": mode,
        "executor_route": executor_route,
        "exchange_executor_called": False,
        "paper_executor_called": False,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "orchestration": orchestration,
        "plan": plan,
        "notes": [
            "Execution Engine V2 recebeu o payload e delegou validação ao Orchestrator.",
            "Nenhuma ordem real foi enviada.",
            "Próximo passo técnico: conectar Paper Executor integrado.",
        ],
    }

    _append_jsonl(EXECUTION_ENGINE_LOG_FILE, {
        "event": "EXECUTION_ENGINE_RUN",
        "version": VERSION,
        "generated_at": _now_br(),
        "epoch": time.time(),
        "mode": mode,
        "payload": payload,
        "result": result,
    })

    return {"ok": engine_ok, "payload": result}


def execution_engine_test() -> Dict[str, Any]:
    payload = {
        "decision": "ALLOW",
        "bot": "DONKEY",
        "setup": "DONKEY",
        "symbol": "ETHUSDT",
        "side": "LONG",
        "entry": 3500,
        "sl": 3430,
        "tp50": 3570,
        "risk_pct": 2.0,
        "capital_allocated": 4500,
        "requested_qty": 0.1,
        "signal_id": "EXECUTION-ENGINE-V2-TEST-DONKEY-ETHUSDT-LONG",
    }
    return run_execution_engine(payload=payload, mode="OBSERVATION_ONLY", dry_run=True)


def read_execution_engine_log(limit: int = 20) -> Dict[str, Any]:
    if not EXECUTION_ENGINE_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = EXECUTION_ENGINE_LOG_FILE.read_text(encoding="utf-8").splitlines()
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
