# execution_orchestrator_v1.txt
# CENTRAL QUANT — EXECUTION ORCHESTRATOR V1
# Versao: 2026-07-07-EXECUTION-ORCHESTRATOR-V1.1-AUDIT-ORIGIN
#
# Objetivo:
# - Camada entre Decision/Risk/Allocator e execução real.
# - Ainda NÃO envia ordem real.
# - Cria plano de execução, idempotency_key, valida payload mínimo e registra evento.
# - Permite a Central evoluir para PAPER/LIVE sem quebrar a arquitetura.
#
# Arquivo recomendado:
#   /opt/render/project/src/execution_orchestrator.py
#
# Endpoints recomendados no main.py:
#   GET  /execution/health
#   POST /execution/plan
#   GET  /execution/log


# ============================
# execution_orchestrator.py
# ============================

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


VERSION = "2026-07-07-EXECUTION-ORCHESTRATOR-V1.1-AUDIT-ORIGIN"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_LOG_FILE = DATA_DIR / "execution_orchestrator_log.jsonl"
EXECUTION_SEEN_FILE = DATA_DIR / "execution_orchestrator_seen.json"

DEFAULT_MODE = os.getenv("CENTRAL_EXECUTION_MODE", "OBSERVATION_ONLY").upper()
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _load_seen() -> Dict[str, Any]:
    if not EXECUTION_SEEN_FILE.exists():
        return {}
    try:
        return json.loads(EXECUTION_SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_seen(data: Dict[str, Any]) -> None:
    EXECUTION_SEEN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _clean_symbol(symbol: Any) -> Optional[str]:
    if not symbol:
        return None
    return str(symbol).replace("/", "").replace(":USDT", "").upper()


def _normalize_side(side: Any) -> Optional[str]:
    if not side:
        return None
    s = str(side).upper()
    if s in ("BUY", "LONG"):
        return "LONG"
    if s in ("SELL", "SHORT"):
        return "SHORT"
    return None


def build_idempotency_key(payload: Dict[str, Any]) -> str:
    """
    Chave estável para impedir execução duplicada.
    Usa campos de decisão/sinal quando existirem.
    """
    raw = {
        "decision_id": payload.get("decision_id") or payload.get("id") or payload.get("signal_id"),
        "bot": payload.get("bot"),
        "setup": payload.get("setup") or payload.get("strategy"),
        "symbol": _clean_symbol(payload.get("symbol")),
        "side": _normalize_side(payload.get("side")),
        "entry": payload.get("entry") or payload.get("entry_price"),
        "sl": payload.get("sl") or payload.get("stop") or payload.get("stop_loss"),
        "tp50": payload.get("tp50") or payload.get("tp_50"),
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24].upper()


def validate_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    warnings = []

    symbol = _clean_symbol(payload.get("symbol"))
    side = _normalize_side(payload.get("side"))
    bot = payload.get("bot")
    setup = payload.get("setup") or payload.get("strategy")

    entry = _safe_float(payload.get("entry") or payload.get("entry_price"))
    sl = _safe_float(payload.get("sl") or payload.get("stop") or payload.get("stop_loss"))
    tp50 = _safe_float(payload.get("tp50") or payload.get("tp_50"))
    risk_pct = _safe_float(payload.get("risk_pct") or payload.get("risk") or payload.get("risk_percent"))

    decision = str(payload.get("decision") or payload.get("base_decision") or "UNKNOWN").upper()

    if not symbol:
        errors.append("symbol ausente")
    if side not in ("LONG", "SHORT"):
        errors.append("side inválido ou ausente")
    if not bot:
        warnings.append("bot ausente")
    if not setup:
        warnings.append("setup ausente")
    if entry is None or entry <= 0:
        errors.append("entry inválido ou ausente")
    if sl is None or sl <= 0:
        errors.append("stop/sl inválido ou ausente")
    if tp50 is None or tp50 <= 0:
        warnings.append("tp50 ausente ou inválido")
    if decision not in ("ALLOW", "REDUCE_SIZE", "READY", "APPROVE", "APPROVED"):
        errors.append(f"decisão não executável: {decision}")

    if side == "LONG" and entry and sl and sl >= entry:
        errors.append("SL de LONG deve ficar abaixo da entrada")
    if side == "SHORT" and entry and sl and sl <= entry:
        errors.append("SL de SHORT deve ficar acima da entrada")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized": {
            "symbol": symbol,
            "side": side,
            "bot": bot,
            "setup": setup,
            "entry": entry,
            "sl": sl,
            "tp50": tp50,
            "risk_pct": risk_pct,
            "decision": decision,
        }
    }


def build_execution_plan(
    payload: Dict[str, Any],
    mode: Optional[str] = None,
    requested_qty: Optional[float] = None,
    capital_allocated: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Cria o plano operacional.
    Neste V1, o plano é apenas decisional/logável.
    Não executa ordem.
    """
    mode = (mode or DEFAULT_MODE).upper()
    validation = validate_execution_payload(payload)
    idem_key = build_idempotency_key(payload)

    normalized = validation["normalized"]

    plan = {
        "ok": validation["ok"],
        "version": VERSION,
        "generated_at": _now_br(),
        "epoch": time.time(),
        "mode": mode,
        "execution_enabled": REAL_EXECUTION_ENABLED,
        "idempotency_key": idem_key,
        "status": "READY_FOR_EXECUTION" if validation["ok"] else "BLOCKED",
        "action": "PLAN_ONLY",
        "route": "DECISION_TO_ORCHESTRATOR_TO_EXECUTOR",
        "payload": normalized,
        "requested_qty": requested_qty,
        "capital_allocated": capital_allocated,
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "safety": {
            "real_execution_blocked": not REAL_EXECUTION_ENABLED,
            "requires_lifecycle_record": True,
            "requires_idempotency": True,
            "requires_outcome_evaluation": True,
            "exchange_executor_called": False,
        },
        "notes": [
            "Execution Orchestrator V1 não envia ordem real.",
            "A BingX/exchange continua bloqueada até CENTRAL_REAL_EXECUTION_ENABLED=true.",
            "A Central mantém a verdade operacional; corretora será apenas executor/custodiante.",
        ],
    }

    if mode in ("LIVE", "REAL") and not REAL_EXECUTION_ENABLED:
        plan["ok"] = False
        plan["status"] = "BLOCKED"
        plan["errors"].append("execução real solicitada, mas CENTRAL_REAL_EXECUTION_ENABLED=false")

    return plan


def orchestrate_execution(
    payload: Dict[str, Any],
    mode: Optional[str] = None,
    requested_qty: Optional[float] = None,
    capital_allocated: Optional[float] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Função principal.
    - Gera plano.
    - Bloqueia duplicidade.
    - Registra JSONL.
    - Não envia ordem real neste V1.
    """
    plan = build_execution_plan(
        payload=payload,
        mode=mode,
        requested_qty=requested_qty,
        capital_allocated=capital_allocated,
    )

    seen = _load_seen()
    idem_key = plan["idempotency_key"]

    if idem_key in seen:
        plan["ok"] = False
        plan["status"] = "DUPLICATE_BLOCKED"
        plan["errors"].append("idempotency_key já processada")
        plan["previous_seen_at"] = seen[idem_key].get("seen_at")

    execution_origin = payload.get("_execution_attempt_audit_v1") if isinstance(payload.get("_execution_attempt_audit_v1"), dict) else {}
    event = {
        "event": "EXECUTION_PLAN_CREATED",
        "version": VERSION,
        "generated_at": _now_br(),
        "epoch": time.time(),
        "dry_run": dry_run,
        "origin_type": execution_origin.get("origin_type"),
        "origin_confidence": execution_origin.get("origin_confidence"),
        "origin_reason": execution_origin.get("origin_reason"),
        "request_path": ((execution_origin.get("request") or {}).get("path") if isinstance(execution_origin.get("request"), dict) else None),
        "bot": (plan.get("payload") or {}).get("bot"),
        "setup": (plan.get("payload") or {}).get("setup"),
        "symbol": (plan.get("payload") or {}).get("symbol"),
        "side": (plan.get("payload") or {}).get("side"),
        "plan": plan,
    }

    _append_jsonl(EXECUTION_LOG_FILE, event)

    if plan["status"] == "READY_FOR_EXECUTION":
        seen[idem_key] = {
            "seen_at": _now_br(),
            "symbol": plan["payload"].get("symbol"),
            "side": plan["payload"].get("side"),
            "bot": plan["payload"].get("bot"),
            "setup": plan["payload"].get("setup"),
            "mode": plan["mode"],
        }
        _save_seen(seen)

    return {
        "ok": plan["ok"],
        "payload": plan,
    }


def execution_health() -> Dict[str, Any]:
    seen = _load_seen()

    return {
        "ok": True,
        "module": "execution_orchestrator",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "mode": DEFAULT_MODE,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "files": {
            "execution_log": str(EXECUTION_LOG_FILE),
            "execution_seen": str(EXECUTION_SEEN_FILE),
        },
        "seen_count": len(seen),
        "notes": [
            "V1 seguro: cria plano e loga, mas não executa ordem real.",
            "Próxima fase: conectar Paper Executor.",
            "Somente depois: conectar BingX Executor com stop de desastre.",
        ],
    }


def read_execution_log(limit: int = 20) -> Dict[str, Any]:
    if not EXECUTION_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "items": [],
            "count": 0,
        }

    lines = EXECUTION_LOG_FILE.read_text(encoding="utf-8").splitlines()
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
