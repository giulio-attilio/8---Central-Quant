# paper_executor_integrated.py
# CENTRAL QUANT — PAPER EXECUTOR INTEGRATED V2
# Versão: 2026-07-04-PAPER-EXECUTOR-INTEGRATED-V2
#
# Objetivo:
# - Ser o executor PAPER chamado pelo Execution Engine V2.
# - NÃO envia ordem real.
# - Recebe um plano já validado pelo Execution Orchestrator.
# - Abre posição paper em arquivo próprio.
# - Impede duplicidade por idempotency_key.
# - Mantém base para Trade Lifecycle, Outcome Evaluator e futura BingX.
#
# Arquivo:
#   /opt/render/project/src/paper_executor_integrated.py

import os
import json
import shutil
import time
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from paper_state_storage import PAPER_STATE_LOCK, write_json_atomically


VERSION = "2026-07-04-PAPER-EXECUTOR-INTEGRATED-V2"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
PAPER_LOG_FILE = DATA_DIR / "paper_integrated_executor_log.jsonl"
PAPER_SEEN_FILE = DATA_DIR / "paper_integrated_seen.json"

PAPER_EXECUTION_ENABLED = os.getenv("CENTRAL_PAPER_EXECUTION_ENABLED", "false").lower() == "true"
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"
PAPER_MIN_FREE_DISK_BYTES = 256 * 1024 * 1024
_PAPER_EXECUTION_LOCK = PAPER_STATE_LOCK


def _paper_persistence_guard() -> Dict[str, Any]:
    """Fail closed when persistent storage cannot safely accept a PAPER entry."""
    try:
        free_bytes = int(shutil.disk_usage(DATA_DIR).free)
    except Exception as exc:
        return {
            "allowed": False,
            "status": "PAPER_PERSISTENCE_BLOCKED",
            "free_bytes": None,
            "minimum_free_bytes": PAPER_MIN_FREE_DISK_BYTES,
            "error_type": type(exc).__name__,
        }
    allowed = free_bytes >= PAPER_MIN_FREE_DISK_BYTES
    return {
        "allowed": allowed,
        "status": "PAPER_PERSISTENCE_READY" if allowed else "PAPER_PERSISTENCE_BLOCKED",
        "free_bytes": free_bytes,
        "minimum_free_bytes": PAPER_MIN_FREE_DISK_BYTES,
        "error_type": None,
    }


def _now_br() -> str:
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _read_state_json(path: Path, default: Any) -> Any:
    """Read execution state strictly so corruption cannot masquerade as empty state."""
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> bool:
    """Durably replace one PAPER state file; report failures to the caller."""
    return write_json_atomically(path, payload)


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
    return str(symbol).replace("/", "").replace(":USDT", "").replace("-", "").upper()


def _normalize_side(side: Any) -> Optional[str]:
    if not side:
        return None
    s = str(side).upper().strip()
    if s in {"BUY", "LONG"}:
        return "LONG"
    if s in {"SELL", "SHORT"}:
        return "SHORT"
    return None


def _extract_plan(engine_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aceita:
    1) resultado do Execution Engine: {"payload": {"plan": {...}}}
    2) payload interno do Engine: {"plan": {...}}
    3) plano direto do Orchestrator
    """
    if not isinstance(engine_payload, dict):
        return {}

    if isinstance(engine_payload.get("payload"), dict) and isinstance(engine_payload["payload"].get("plan"), dict):
        return engine_payload["payload"]["plan"]

    if isinstance(engine_payload.get("plan"), dict):
        return engine_payload["plan"]

    if "idempotency_key" in engine_payload and isinstance(engine_payload.get("payload"), dict):
        return engine_payload

    return {}


def _build_trade_id(plan: Dict[str, Any]) -> str:
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}

    raw = {
        "idempotency_key": plan.get("idempotency_key"),
        "symbol": _clean_symbol(payload.get("symbol")),
        "side": _normalize_side(payload.get("side")),
        "bot": payload.get("bot"),
        "setup": payload.get("setup"),
        "entry": payload.get("entry"),
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False)
    return "PAPER-" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20].upper()


def validate_paper_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    warnings = []

    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}

    idempotency_key = plan.get("idempotency_key")
    if isinstance(idempotency_key, str):
        idempotency_key = idempotency_key.strip()
    symbol = _clean_symbol(payload.get("symbol"))
    side = _normalize_side(payload.get("side"))
    bot = payload.get("bot")
    setup = payload.get("setup")
    entry = _safe_float(payload.get("entry"))
    sl = _safe_float(payload.get("sl"))
    tp50 = _safe_float(payload.get("tp50"))
    risk_pct = _safe_float(payload.get("risk_pct"))
    requested_qty = _safe_float(plan.get("requested_qty"), 0.0)
    capital_allocated = _safe_float(plan.get("capital_allocated"))

    if not isinstance(idempotency_key, str) or not idempotency_key:
        errors.append("idempotency_key ausente ou inválida")
    if not symbol:
        errors.append("symbol ausente")
    if side not in {"LONG", "SHORT"}:
        errors.append("side inválido ou ausente")
    if entry is None or entry <= 0:
        errors.append("entry inválido ou ausente")
    if sl is None or sl <= 0:
        errors.append("sl inválido ou ausente")
    if tp50 is None or tp50 <= 0:
        warnings.append("tp50 ausente ou inválido")
    if not bot:
        warnings.append("bot ausente")
    if not setup:
        warnings.append("setup ausente")
    if requested_qty in [None, 0]:
        warnings.append("requested_qty ausente ou zero")

    if side == "LONG" and entry and sl and sl >= entry:
        errors.append("SL de LONG deve ficar abaixo da entrada")
    if side == "SHORT" and entry and sl and sl <= entry:
        errors.append("SL de SHORT deve ficar acima da entrada")

    if plan.get("status") not in {"READY_FOR_EXECUTION", "PLAN_CREATED", None}:
        warnings.append(f"status do plano incomum: {plan.get('status')}")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "normalized": {
            "idempotency_key": idempotency_key,
            "symbol": symbol,
            "side": side,
            "bot": bot,
            "setup": setup,
            "entry": entry,
            "sl": sl,
            "tp50": tp50,
            "risk_pct": risk_pct,
            "requested_qty": requested_qty,
            "capital_allocated": capital_allocated,
        },
    }


def execute_paper_from_engine(engine_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Função chamada pelo Execution Engine V2 quando mode=PAPER.
    """
    plan = _extract_plan(engine_payload)
    validation = validate_paper_plan(plan)
    normalized = validation["normalized"]

    if not PAPER_EXECUTION_ENABLED:
        result = {
            "ok": False,
            "status": "PAPER_BLOCKED",
            "reason": "CENTRAL_PAPER_EXECUTION_ENABLED=false",
            "version": VERSION,
            "generated_at": _now_br(),
            "errors": ["paper execution desabilitada por env"],
            "warnings": validation["warnings"],
            "exchange_executor_called": False,
            "paper_executor_called": True,
        }
        _append_jsonl(PAPER_LOG_FILE, {"event": "PAPER_BLOCKED", "payload": result})
        return {"ok": False, "payload": result}

    if not validation["ok"]:
        result = {
            "ok": False,
            "status": "PAPER_INVALID_PLAN",
            "reason": "plano inválido para execução paper",
            "version": VERSION,
            "generated_at": _now_br(),
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "exchange_executor_called": False,
            "paper_executor_called": True,
        }
        _append_jsonl(PAPER_LOG_FILE, {"event": "PAPER_INVALID_PLAN", "payload": result})
        return {"ok": False, "payload": result}

    persistence = _paper_persistence_guard()
    if not persistence["allowed"]:
        result = {
            "ok": False,
            "status": "PAPER_PERSISTENCE_BLOCKED",
            "reason": "espaço persistente insuficiente ou indisponível; nova posição PAPER bloqueada",
            "version": VERSION,
            "generated_at": _now_br(),
            "idempotency_key": normalized["idempotency_key"],
            "persistence": persistence,
            "errors": ["PAPER_PERSISTENT_DISK_BELOW_MINIMUM_OR_UNAVAILABLE"],
            "warnings": validation["warnings"],
            "exchange_executor_called": False,
            "paper_executor_called": True,
        }
        return {"ok": False, "payload": result}

    idem = normalized["idempotency_key"]
    trade_id = _build_trade_id(plan)

    position = {
        "trade_id": trade_id,
        "idempotency_key": idem,
        "status": "OPEN",
        "mode": "PAPER",
        "source": "PAPER_EXECUTOR_INTEGRATED_V2",
        "opened_at": _now_br(),
        "opened_epoch": time.time(),
        "symbol": normalized["symbol"],
        "side": normalized["side"],
        "bot": normalized["bot"],
        "setup": normalized["setup"],
        "entry": normalized["entry"],
        "sl_initial": normalized["sl"],
        "sl_current": normalized["sl"],
        "tp50": normalized["tp50"],
        "risk_pct": normalized["risk_pct"],
        "requested_qty": normalized["requested_qty"],
        "capital_allocated": normalized["capital_allocated"],
        "tp50_hit": False,
        "breakeven": False,
        "trailing_active": False,
        "exit_price": None,
        "closed_at": None,
        "close_reason": None,
        "pnl_pct": None,
        "r_result": None,
        "exchange_executor_called": False,
        "real_exchange_order_id": None,
        "lifecycle_registered": False,
        "outcome_evaluated": False,
        "raw_plan": plan,
        "notes": [
            "Posição paper aberta pelo Execution Engine V2.",
            "Nenhuma ordem real enviada.",
            "Próxima integração: Trade Lifecycle Manager.",
        ],
    }

    with _PAPER_EXECUTION_LOCK:
        positions_file_present = PAPER_POSITIONS_FILE.is_file()
        seen_file_present = PAPER_SEEN_FILE.is_file()
        if not positions_file_present:
            result = {
                "ok": False,
                "status": "PAPER_STATE_UNINITIALIZED",
                "reason": "ledger PAPER ausente; estado desconhecido, nova execução bloqueada",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "errors": ["PAPER_POSITION_LEDGER_MISSING"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}

        try:
            seen = _read_state_json(PAPER_SEEN_FILE, {}) if seen_file_present else {}
            positions = _read_state_json(PAPER_POSITIONS_FILE, [])
        except Exception:
            seen, positions = None, None
        if not isinstance(seen, dict) or not isinstance(positions, list):
            result = {
                "ok": False,
                "status": "PAPER_STATE_INVALID",
                "reason": "estado PAPER inválido; execução bloqueada para evitar duplicidade",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "errors": ["estado PAPER não é JSON object/list válido"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}

        existing_position = next(
            (
                item for item in positions
                if isinstance(item, dict) and str(item.get("idempotency_key") or "") == str(idem)
            ),
            None,
        )
        seen_entry = seen.get(idem)
        if idem in seen or existing_position is not None:
            # The position ledger is also an idempotency source of truth: this
            # covers a crash after positions were committed but before the seen cache.
            if not isinstance(seen_entry, dict):
                seen_entry = {}
            if existing_position is not None and idem not in seen:
                seen[idem] = {
                    "seen_at": existing_position.get("opened_at") or _now_br(),
                    "trade_id": existing_position.get("trade_id"),
                    "symbol": existing_position.get("symbol"),
                    "side": existing_position.get("side"),
                    "recovered_from_position_ledger": True,
                }
                _write_json(PAPER_SEEN_FILE, seen)
            result = {
                "ok": False,
                "status": "PAPER_DUPLICATE_BLOCKED",
                "reason": "idempotency_key já executada em PAPER",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "previous_seen_at": seen_entry.get("seen_at"),
                "trade_id": (existing_position or {}).get("trade_id") or seen_entry.get("trade_id"),
                "errors": ["execução paper duplicada"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            try:
                _append_jsonl(PAPER_LOG_FILE, {"event": "PAPER_DUPLICATE_BLOCKED", "payload": result})
            except Exception:
                pass
            return {"ok": False, "payload": result}

        if not seen_file_present:
            result = {
                "ok": False,
                "status": "PAPER_STATE_UNINITIALIZED",
                "reason": "cache de idempotência PAPER ausente; nova execução bloqueada",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "errors": ["PAPER_IDEMPOTENCY_STATE_MISSING"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}

        positions.append(position)
        # Recheck immediately before the atomic position-ledger replacement.
        persistence = _paper_persistence_guard()
        if not persistence["allowed"]:
            result = {
                "ok": False,
                "status": "PAPER_PERSISTENCE_BLOCKED",
                "reason": "espaço persistente caiu abaixo do mínimo antes da gravação",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "persistence": persistence,
                "errors": ["PAPER_PERSISTENT_DISK_BELOW_MINIMUM_OR_UNAVAILABLE"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}
        if not _write_json(PAPER_POSITIONS_FILE, positions):
            result = {
                "ok": False,
                "status": "PAPER_STATE_PERSISTENCE_FAILED",
                "reason": "posição PAPER não foi persistida; execução bloqueada",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "errors": ["falha ao persistir paper_integrated_positions.json"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}

        seen[idem] = {
            "seen_at": _now_br(),
            "trade_id": trade_id,
            "symbol": normalized["symbol"],
            "side": normalized["side"],
            "bot": normalized["bot"],
            "setup": normalized["setup"],
        }
        seen_persisted = _write_json(PAPER_SEEN_FILE, seen)

        result = {
            "ok": True,
            "status": "PAPER_OPENED",
            "version": VERSION,
            "generated_at": _now_br(),
            "trade_id": trade_id,
            "idempotency_key": idem,
            "position": position,
            "errors": [],
            "warnings": validation["warnings"] + ([] if seen_persisted else [
                "marcador de idempotência pendente; retry será bloqueado pelo ledger de posições"
            ]),
            "exchange_executor_called": False,
            "paper_executor_called": True,
            "real_execution_enabled": REAL_EXECUTION_ENABLED,
            "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        }

        try:
            _append_jsonl(PAPER_LOG_FILE, {
                "event": "PAPER_TRADE_OPENED",
                "version": VERSION,
                "generated_at": _now_br(),
                "epoch": time.time(),
                "trade_id": trade_id,
                "idempotency_key": idem,
                "result": result,
            })
        except Exception:
            result["warnings"].append("posição PAPER persistida, mas o log de auditoria falhou")

        return {"ok": True, "payload": result}


def paper_integrated_health() -> Dict[str, Any]:
    positions_file_present = PAPER_POSITIONS_FILE.is_file()
    seen_file_present = PAPER_SEEN_FILE.is_file()
    state_files_present = positions_file_present and seen_file_present
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    seen = _read_json(PAPER_SEEN_FILE, {})

    open_positions = [
        p for p in positions
        if isinstance(p, dict) and p.get("status") == "OPEN"
    ]

    return {
        "ok": True,
        "module": "paper_executor_integrated",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "state_files_present": state_files_present,
        "state_files_status": "PAPER_STATE_FILES_PRESENT" if state_files_present else "PAPER_STATE_FILES_MISSING",
        "open_positions": len(open_positions),
        "total_positions": len(positions),
        "seen_count": len(seen),
        "files": {
            "paper_positions": str(PAPER_POSITIONS_FILE),
            "paper_positions_present": positions_file_present,
            "paper_log": str(PAPER_LOG_FILE),
            "paper_seen": str(PAPER_SEEN_FILE),
            "paper_seen_present": seen_file_present,
        },
        "notes": [
            "Executor paper integrado ao Execution Engine V2.",
            "Não chama corretora.",
            "Abre posição paper somente se CENTRAL_PAPER_EXECUTION_ENABLED=true.",
        ],
    }


def get_paper_integrated_open_positions() -> Dict[str, Any]:
    positions = _read_json(PAPER_POSITIONS_FILE, [])
    open_positions = [
        p for p in positions
        if isinstance(p, dict) and p.get("status") == "OPEN"
    ]

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(open_positions),
        "positions": open_positions,
    }


def read_paper_integrated_log(limit: int = 20) -> Dict[str, Any]:
    if not PAPER_LOG_FILE.exists():
        return {
            "ok": True,
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    lines = PAPER_LOG_FILE.read_text(encoding="utf-8").splitlines()
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
