# execution_orchestrator_v1.txt
# CENTRAL QUANT — EXECUTION ORCHESTRATOR V1
# Versao: 2026-07-11-EXECUTION-ORCHESTRATOR-V1.2-IDENTITY-ATOMIC-SEEN
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
import threading
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional


VERSION = "2026-07-11-EXECUTION-ORCHESTRATOR-V1.2-IDENTITY-ATOMIC-SEEN"

DATA_DIR = Path(os.getenv("CENTRAL_DATA_DIR", "/opt/render/project/src/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_LOG_FILE = DATA_DIR / "execution_orchestrator_log.jsonl"
EXECUTION_SEEN_FILE = DATA_DIR / "execution_orchestrator_seen.json"

DEFAULT_MODE = os.getenv("CENTRAL_EXECUTION_MODE", "OBSERVATION_ONLY").upper()
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"
_SEEN_LOCK = threading.RLock()


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
    """
    Persistência atômica do ledger de idempotência.

    Evita arquivo parcialmente escrito caso o processo seja interrompido
    durante a gravação.
    """
    EXECUTION_SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = EXECUTION_SEEN_FILE.with_suffix(EXECUTION_SEEN_FILE.suffix + ".tmp")
    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(EXECUTION_SEEN_FILE)


_BROKER_EXECUTION_STATE_VALUES = {
    "ENGINE_BROKER_CALL_PENDING",
    "ENGINE_BROKER_SEND_OUTCOME_UNKNOWN",
    "ENGINE_BROKER_RESULT_CONFIRMED",
    "ENGINE_BROKER_RECONCILED_TERMINAL",
}

# This is deliberately a small, bounded operational ledger scan.  Falcon must
# fail closed rather than load an unbounded idempotency file while deciding
# whether a prior broker call may still be unresolved.
_FALCON_BROKER_STATE_SCAN_MAX_BYTES = 2 * 1024 * 1024
_FALCON_BROKER_STATE_SCAN_MAX_RECORDS = 2_000


def _broker_execution_identity_projection(value: Dict[str, Any]) -> Dict[str, Any]:
    """Persist only reconciliation identities; never transport credentials."""
    value = value if isinstance(value, dict) else {}
    reservation = value.get("client_order_id_reservation")
    reservation = reservation if isinstance(reservation, dict) else {}
    disaster_stop = value.get("disaster_stop")
    disaster_stop = disaster_stop if isinstance(disaster_stop, dict) else {}
    return {
        "bot": value.get("bot"),
        "client_order_id": value.get("client_order_id"),
        "entry_order_id": value.get("entry_order_id"),
        "entry_amount": value.get("entry_amount"),
        "entry_filled_amount": value.get("entry_filled_amount"),
        "entry_acknowledged": value.get("entry_acknowledged"),
        "returned_client_order_id_matches": value.get(
            "returned_client_order_id_matches"
        ),
        "canonical_operation_id": value.get("canonical_operation_id"),
        "attempt_id": value.get("attempt_id"),
        "client_order_attempt_id": value.get("client_order_attempt_id"),
        "client_order_attempt_sequence": value.get(
            "client_order_attempt_sequence"
        ),
        "signal_id": value.get("signal_id"),
        "lifecycle_id": value.get("lifecycle_id"),
        "decision_id": value.get("decision_id"),
        "execution_intent_idempotency_key": value.get(
            "execution_intent_idempotency_key"
        ),
        "orchestrator_idempotency_key": value.get("orchestrator_idempotency_key"),
        "symbol": value.get("symbol"),
        "side": value.get("side"),
        "client_order_id_reservation": {
            key: reservation.get(key)
            for key in (
                "ok", "status", "send_allowed", "client_order_id",
                "canonical_operation_id", "attempt_id", "attempt_sequence",
                "attempt_identity_hash", "lifecycle_id", "persistent",
            )
            if reservation.get(key) is not None
        },
        "account_client_order_identity": value.get(
            "account_client_order_identity"
        ),
        "disaster_stop": {
            **{
                key: disaster_stop.get(key)
                for key in (
                    "order_id", "client_order_id", "status",
                    "amount", "filled_amount", "stop_price", "working_type",
                    "symbol", "side", "position_side", "reduce_only",
                    "close_position", "client_order_id_reserved",
                    "client_order_id_unique",
                    "expected_client_order_id", "expected_disaster_stop_client_order_id",
                )
                if disaster_stop.get(key) is not None
            },
            "client_order_id_reservation": {
                key: disaster_stop.get("client_order_id_reservation", {}).get(key)
                for key in (
                    "client_order_id", "canonical_operation_id", "attempt_id",
                    "attempt_sequence", "attempt_identity_hash", "persistent",
                    "status", "reservation_status", "reservation_state",
                    "client_order_id_reserved", "client_order_id_unique",
                )
                if isinstance(disaster_stop.get("client_order_id_reservation"), dict)
                and disaster_stop.get("client_order_id_reservation", {}).get(key)
                is not None
            },
        },
        # The stop reservation is created before its mutable broker boundary.
        # Keep its deterministic identity even when the exchange call returns
        # UNKNOWN before an order payload exists.
        "expected_disaster_stop_client_order_id": (
            disaster_stop.get("client_order_id")
        ),
        "disaster_stop_reservation": {
            key: disaster_stop.get("client_order_id_reservation", {}).get(key)
            for key in (
                "client_order_id", "canonical_operation_id", "attempt_id",
                "attempt_sequence", "attempt_identity_hash", "persistent",
                "status", "reservation_status", "reservation_state",
            )
            if isinstance(disaster_stop.get("client_order_id_reservation"), dict)
            and disaster_stop.get("client_order_id_reservation", {}).get(key)
            is not None
        },
    }


def record_execution_broker_state(
    idempotency_key: Any, state: Any, identity: Dict[str, Any]
) -> Dict[str, Any]:
    """Atomically persist one Engine broker-facing reconciliation state."""
    key = str(idempotency_key or "").strip()
    normalized_state = str(state or "").upper().strip()
    if not key or normalized_state not in _BROKER_EXECUTION_STATE_VALUES:
        return {
            "ok": False,
            "status": "ENGINE_BROKER_STATE_IDENTITY_REQUIRED",
            "persistent": False,
        }
    projection = _broker_execution_identity_projection(identity)
    if not projection.get("client_order_id") or not projection.get(
        "canonical_operation_id"
    ) or not projection.get("attempt_id"):
        return {
            "ok": False,
            "status": "ENGINE_BROKER_STATE_IDENTITY_REQUIRED",
            "persistent": False,
        }
    try:
        with _SEEN_LOCK:
            seen = _load_seen()
            entry = seen.get(key)
            if not isinstance(entry, dict):
                return {
                    "ok": False,
                    "status": "ENGINE_BROKER_STATE_ORCHESTRATOR_RECORD_REQUIRED",
                    "persistent": False,
                }
            previous = entry.get("broker_execution_state")
            previous = previous if isinstance(previous, dict) else {}
            previous_identity = previous.get("identity")
            if isinstance(previous_identity, dict) and any(
                previous_identity.get(field) not in (None, "")
                and projection.get(field) not in (None, "")
                and previous_identity.get(field) != projection.get(field)
                for field in (
                    "bot", "client_order_id", "canonical_operation_id", "attempt_id",
                    "signal_id", "lifecycle_id", "execution_intent_idempotency_key",
                )
            ):
                return {
                    "ok": False,
                    "status": "ENGINE_BROKER_STATE_IDENTITY_CONFLICT",
                    "persistent": True,
                }
            entry["broker_execution_state"] = {
                "state": normalized_state,
                "updated_at": _now_br(),
                "identity": projection,
            }
            seen[key] = entry
            _save_seen(seen)
        return {
            "ok": True,
            "status": normalized_state,
            "persistent": True,
            "state": normalized_state,
            "identity": projection,
        }
    except Exception:
        return {
            "ok": False,
            "status": "ENGINE_BROKER_STATE_PERSISTENCE_ERROR",
            "persistent": False,
        }


def load_execution_broker_state(idempotency_key: Any) -> Dict[str, Any]:
    """Read the persisted Engine reconciliation state after restart."""
    key = str(idempotency_key or "").strip()
    if not key:
        return {"ok": False, "status": "ENGINE_BROKER_STATE_IDENTITY_REQUIRED"}
    try:
        with _SEEN_LOCK:
            state = (_load_seen().get(key) or {}).get("broker_execution_state")
        if not isinstance(state, dict):
            return {"ok": True, "status": "ENGINE_BROKER_STATE_EMPTY", "state": {}}
        return {"ok": True, "status": state.get("state"), "state": dict(state)}
    except Exception:
        return {"ok": False, "status": "ENGINE_BROKER_STATE_READ_ERROR"}


def find_falcon_pending_broker_states(limit: int = 32) -> Dict[str, Any]:
    """Return a bounded projection of unresolved Falcon broker calls.

    This is a ledger integrity gate, not a history reader.  An oversized,
    malformed, or unexpectedly large ledger is treated as unavailable so the
    caller can fail closed before creating a new Falcon LIVE intent.
    """
    try:
        bounded_limit = max(1, min(int(limit or 32), 128))
    except (TypeError, ValueError):
        bounded_limit = 32
    try:
        with _SEEN_LOCK:
            if not EXECUTION_SEEN_FILE.exists():
                return {
                    "ok": True,
                    "status": "FALCON_ENGINE_BROKER_LEDGER_EMPTY",
                    "pending": [],
                    "pending_count": 0,
                    "read_bounded": True,
                }
            size = EXECUTION_SEEN_FILE.stat().st_size
            if size > _FALCON_BROKER_STATE_SCAN_MAX_BYTES:
                return {
                    "ok": False,
                    "status": "FALCON_ENGINE_BROKER_LEDGER_SIZE_LIMIT_EXCEEDED",
                    "pending": [],
                    "pending_count": None,
                    "read_bounded": True,
                }
            raw = EXECUTION_SEEN_FILE.read_text(encoding="utf-8")
            seen = json.loads(raw)
        if not isinstance(seen, dict):
            return {
                "ok": False,
                "status": "FALCON_ENGINE_BROKER_LEDGER_INVALID",
                "pending": [],
                "pending_count": None,
                "read_bounded": True,
            }
        if len(seen) > _FALCON_BROKER_STATE_SCAN_MAX_RECORDS:
            return {
                "ok": False,
                "status": "FALCON_ENGINE_BROKER_LEDGER_RECORD_LIMIT_EXCEEDED",
                "pending": [],
                "pending_count": None,
                "read_bounded": True,
            }
        pending = []
        for key, entry in seen.items():
            if not isinstance(entry, dict):
                continue
            broker_state = entry.get("broker_execution_state")
            broker_state = broker_state if isinstance(broker_state, dict) else {}
            state_name = str(broker_state.get("state") or "").upper().strip()
            if state_name not in {
                "ENGINE_BROKER_CALL_PENDING",
                "ENGINE_BROKER_SEND_OUTCOME_UNKNOWN",
            }:
                continue
            identity = broker_state.get("identity")
            identity = identity if isinstance(identity, dict) else {}
            bot = str(
                identity.get("bot") or entry.get("bot") or ""
            ).upper().strip()
            if bot != "FALCON":
                continue
            pending.append({
                "orchestrator_idempotency_key": str(key),
                "state": state_name,
                "identity": _broker_execution_identity_projection(identity),
                "updated_at": broker_state.get("updated_at"),
            })
            if len(pending) > bounded_limit:
                return {
                    "ok": False,
                    "status": "FALCON_ENGINE_BROKER_PENDING_LIMIT_EXCEEDED",
                    "pending": pending[:bounded_limit],
                    "pending_count": None,
                    "read_bounded": True,
                }
        return {
            "ok": True,
            "status": (
                "FALCON_ENGINE_BROKER_RECONCILIATION_PENDING"
                if pending
                else "FALCON_ENGINE_BROKER_LEDGER_CLEAR"
            ),
            "pending": pending,
            "pending_count": len(pending),
            "read_bounded": True,
        }
    except Exception:
        return {
            "ok": False,
            "status": "FALCON_ENGINE_BROKER_LEDGER_READ_ERROR",
            "pending": [],
            "pending_count": None,
            "read_bounded": True,
        }


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


def _identity_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Identidade canônica do fluxo.

    IDs explícitos prevalecem sobre atributos de mercado. Símbolo e lado
    ajudam na auditoria, mas nunca são prova suficiente de ownership.
    """
    return {
        "trade_id": payload.get("trade_id") or payload.get("trade_uuid"),
        "lifecycle_id": payload.get("lifecycle_id"),
        "signal_id": payload.get("signal_id"),
        "decision_id": payload.get("decision_id") or payload.get("id"),
        "client_order_id": payload.get("client_order_id") or payload.get("clientOrderId"),
        "client_order_attempt_id": payload.get("client_order_attempt_id"),
        "client_order_attempt_sequence": payload.get("client_order_attempt_sequence"),
        "execution_intent_idempotency_key": payload.get(
            "execution_intent_idempotency_key"
        ),
        "bot": payload.get("bot"),
        "setup": payload.get("setup") or payload.get("strategy"),
        "symbol": _clean_symbol(payload.get("symbol")),
        "side": _normalize_side(payload.get("side")),
    }


def _legacy_idempotency_key(payload: Dict[str, Any]) -> str:
    """
    Chave V1.1 mantida para reconhecer intents gravadas por versões anteriores.
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


def build_idempotency_key(payload: Dict[str, Any]) -> str:
    """
    Chave estável para impedir execução duplicada.

    Quando há IDs explícitos, a chave é baseada na identidade do lifecycle.
    Na ausência deles, usa fallback compatível com a V1.1.
    """
    identity = _identity_fields(payload)
    explicit_identity = {
        key: identity.get(key)
        for key in (
            "trade_id", "lifecycle_id", "signal_id", "decision_id",
            "client_order_id", "client_order_attempt_id",
            "execution_intent_idempotency_key",
        )
        if identity.get(key)
    }
    if not explicit_identity:
        return _legacy_idempotency_key(payload)

    raw = {
        **explicit_identity,
        "bot": identity.get("bot"),
        "setup": identity.get("setup"),
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
        "legacy_idempotency_key": _legacy_idempotency_key(payload),
        "identity": _identity_fields(payload),
        "execution_intent_idempotency_key": _identity_fields(payload).get(
            "execution_intent_idempotency_key"
        ),
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

    idem_key = plan["idempotency_key"]
    legacy_idem_key = plan.get("legacy_idempotency_key")

    with _SEEN_LOCK:
        seen = _load_seen()
        previous_key = None
        if idem_key in seen:
            previous_key = idem_key
        elif legacy_idem_key and legacy_idem_key in seen:
            previous_key = legacy_idem_key

        if previous_key:
            plan["ok"] = False
            plan["status"] = "DUPLICATE_BLOCKED"
            plan["errors"].append("intenção idempotente já registrada")
            plan["previous_seen_at"] = (seen.get(previous_key) or {}).get("seen_at")
            plan["previous_idempotency_key"] = previous_key

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

    # Preview/DRY RUN não deve consumir a identidade de uma futura execução.
    # A reserva persistente ocorre somente quando a chamada não é dry_run.
    if plan["status"] == "READY_FOR_EXECUTION":
        plan["idempotency_reserved"] = not dry_run
        if not dry_run:
            with _SEEN_LOCK:
                seen = _load_seen()
                # Revalida dentro do lock para reduzir corrida entre threads.
                if idem_key in seen or (legacy_idem_key and legacy_idem_key in seen):
                    plan["ok"] = False
                    plan["status"] = "DUPLICATE_BLOCKED"
                    plan["errors"].append("intenção idempotente registrada por chamada concorrente")
                else:
                    seen[idem_key] = {
                        "seen_at": _now_br(),
                        "symbol": plan["payload"].get("symbol"),
                        "side": plan["payload"].get("side"),
                        "bot": plan["payload"].get("bot"),
                        "setup": plan["payload"].get("setup"),
                        "mode": plan["mode"],
                        "identity": plan.get("identity"),
                        "legacy_idempotency_key": legacy_idem_key,
                    }
                    _save_seen(seen)
    else:
        plan["idempotency_reserved"] = False

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
            "V1.2 seguro: cria plano, identidade e ledger, mas não envia ordem diretamente.",
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
