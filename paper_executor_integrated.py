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
import sys
import time
import hashlib
import math
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

from paper_state_storage import (
    PAPER_STATE_LOCK,
    append_paper_text,
    ensure_paper_data_dir,
    paper_data_mount_verified,
    paper_file_exists,
    read_paper_text,
    resolve_paper_data_dir,
    write_json_atomically,
)


VERSION = "2026-07-04-PAPER-EXECUTOR-INTEGRATED-V2"

def _resolve_data_dir() -> Path:
    """Use the same persistent-data precedence as the Central runtime."""
    return resolve_paper_data_dir(__file__)


DATA_DIR = _resolve_data_dir()


def _paper_data_mount_verified(*, platform_name: str | None = None) -> bool:
    """Reject /data state when Render's persistent disk is not mounted."""
    return paper_data_mount_verified(DATA_DIR, platform_name=platform_name)


def _paper_file_access_verified(path: Path) -> bool:
    """Verify both the configured data root and this exact file path."""
    return _paper_data_mount_verified() and paper_data_mount_verified(Path(path))


def _ensure_paper_data_dir() -> bool:
    # Do not create an ephemeral /data directory if a configured Render disk
    # failed to mount. Execution and health guards remain fail-closed as well.
    return ensure_paper_data_dir(DATA_DIR)


_ensure_paper_data_dir()

PAPER_POSITIONS_FILE = DATA_DIR / "paper_integrated_positions.json"
PAPER_LOG_FILE = DATA_DIR / "paper_integrated_executor_log.jsonl"
PAPER_SEEN_FILE = DATA_DIR / "paper_integrated_seen.json"
FALCON_PAPER_RECONCILIATION_LATCH_FILE = (
    DATA_DIR / "falcon_paper_persistence_reconciliation.json"
)
FALCON_PAPER_RECONCILIATION_LATCH_VERSION = (
    "FALCON_PAPER_PERSISTENCE_LATCH_V1"
)

PAPER_EXECUTION_ENABLED = os.getenv("CENTRAL_PAPER_EXECUTION_ENABLED", "false").lower() == "true"
REAL_EXECUTION_ENABLED = os.getenv("CENTRAL_REAL_EXECUTION_ENABLED", "false").lower() == "true"
PAPER_MIN_FREE_DISK_BYTES = 256 * 1024 * 1024
PAPER_MAX_OPEN_POSITIONS_DEFAULT = 10
_PAPER_EXECUTION_LOCK = PAPER_STATE_LOCK


def _paper_max_open_positions() -> Optional[int]:
    """Return the finite PAPER admission cap, or None for invalid configuration.

    The integrated executor is reachable independently of Falcon's legacy
    scanner.  Reuse its established limit by default, while allowing a single
    explicit Central override.  Zero is a valid kill setting; negatives and
    malformed values fail closed.
    """
    configured = os.getenv("CENTRAL_PAPER_MAX_OPEN_POSITIONS")
    if configured is None or not configured.strip():
        configured = os.getenv(
            "FALCON_MAX_OPEN_POSITIONS", str(PAPER_MAX_OPEN_POSITIONS_DEFAULT)
        )
    try:
        value = int(configured)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _falcon_paper_reconciliation_gate() -> Dict[str, Any]:
    """Fail closed for Falcon while its accepted-signal latch needs review."""
    runtime_main = sys.modules.get("main")
    loaded_bots = getattr(runtime_main, "LOADED_BOTS", None)
    falcon_module = (
        loaded_bots.get("FALCON") if isinstance(loaded_bots, dict) else None
    )
    falcon_health = getattr(falcon_module, "HEALTH", None)
    if (
        isinstance(falcon_health, dict)
        and falcon_health.get("falcon_paper_persistence_reconciliation_required")
        is True
    ):
        return {
            "blocked": True,
            "status": "FALCON_PAPER_RECONCILIATION_REQUIRED_IN_MEMORY",
        }

    path = FALCON_PAPER_RECONCILIATION_LATCH_FILE
    if not _paper_file_access_verified(path):
        return {"blocked": True, "status": "PAPER_DATA_MOUNT_NOT_VERIFIED"}
    try:
        if not paper_file_exists(path):
            return {"blocked": False, "status": "NO_RECONCILIATION_LATCH"}
    except Exception as exc:
        return {
            "blocked": True,
            "status": "FALCON_PAPER_RECONCILIATION_LATCH_READ_FAILED",
            "error_type": type(exc).__name__,
        }

    try:
        payload = json.loads(
            read_paper_text(path, encoding="utf-8", max_bytes=16384)
        )
    except Exception as exc:
        return {
            "blocked": True,
            "status": "FALCON_PAPER_RECONCILIATION_LATCH_READ_FAILED",
            "error_type": type(exc).__name__,
        }
    if (
        not isinstance(payload, dict)
        or payload.get("version") != FALCON_PAPER_RECONCILIATION_LATCH_VERSION
        or payload.get("reconciliation_required") is not True
    ):
        return {
            "blocked": True,
            "status": "FALCON_PAPER_RECONCILIATION_LATCH_INVALID",
        }
    return {"blocked": True, "status": "FALCON_PAPER_RECONCILIATION_REQUIRED"}


def _paper_persistence_guard() -> Dict[str, Any]:
    """Fail closed when persistent storage cannot safely accept a PAPER entry."""
    if not _paper_data_mount_verified():
        return {
            "allowed": False,
            "status": "PAPER_DATA_MOUNT_NOT_VERIFIED",
            "free_bytes": None,
            "minimum_free_bytes": PAPER_MIN_FREE_DISK_BYTES,
            "error_type": None,
        }
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
    if not _paper_file_access_verified(path):
        return default
    try:
        if not paper_file_exists(path):
            return default
        return json.loads(read_paper_text(path, encoding="utf-8"))
    except Exception:
        return default


def _read_state_json(
    path: Path, default: Any, *, required: bool = False
) -> Any:
    """Read execution state strictly so corruption cannot masquerade as empty state."""
    if not _paper_file_access_verified(path):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    if required:
        # Open directly: a required ledger disappearing after a prior presence
        # check must raise, never be reinterpreted as an empty default.
        return json.loads(read_paper_text(path, encoding="utf-8"))
    if not paper_file_exists(path):
        return default
    return json.loads(read_paper_text(path, encoding="utf-8"))


def _paper_state_shape_is_valid(positions: Any, seen: Any) -> bool:
    """Reject persisted position rows whose identity or lifecycle is ambiguous."""
    if not isinstance(positions, list) or not isinstance(seen, dict):
        return False

    position_keys = []
    for position in positions:
        if not isinstance(position, dict):
            return False
        key = position.get("idempotency_key")
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            return False
        if position.get("status") not in {"OPEN", "CLOSED"}:
            return False
        for field in ("entry", "sl_initial", "sl_current"):
            numeric_value = _safe_float(position.get(field))
            if numeric_value is None or numeric_value <= 0:
                return False
        position_keys.append(key)
    if len(position_keys) != len(set(position_keys)):
        return False

    return all(
        isinstance(key, str)
        and bool(key.strip())
        and key == key.strip()
        and isinstance(value, dict)
        for key, value in seen.items()
    )


def _write_json(path: Path, payload: Any) -> bool:
    """Durably replace one PAPER state file; report failures to the caller."""
    return write_json_atomically(path, payload)


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> bool:
    if not _paper_file_access_verified(path):
        return False
    append_paper_text(
        path,
        json.dumps(payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return True


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        result = float(value)
        return result if math.isfinite(result) else default
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
    requested_qty = _safe_float(plan.get("requested_qty"))
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
    if requested_qty is None or requested_qty <= 0:
        errors.append("requested_qty ausente ou não positivo")

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
    max_open_positions = _paper_max_open_positions()

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

    if max_open_positions is None:
        result = {
            "ok": False,
            "status": "PAPER_POSITION_LIMIT_CONFIG_INVALID",
            "reason": "limite de posições PAPER inválido; execução bloqueada",
            "version": VERSION,
            "generated_at": _now_br(),
            "errors": ["CENTRAL_PAPER_MAX_OPEN_POSITIONS_INVALID"],
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
        if str(normalized.get("bot") or "").upper().strip() == "FALCON":
            reconciliation_gate = _falcon_paper_reconciliation_gate()
            if reconciliation_gate.get("blocked") is True:
                result = {
                    "ok": False,
                    "status": reconciliation_gate.get("status")
                    or "FALCON_PAPER_RECONCILIATION_REQUIRED",
                    "reason": "reconciliação PAPER do Falcon pendente; nova entrada bloqueada",
                    "version": VERSION,
                    "generated_at": _now_br(),
                    "errors": [
                        reconciliation_gate.get("status")
                        or "FALCON_PAPER_RECONCILIATION_REQUIRED"
                    ],
                    "warnings": validation["warnings"],
                    "exchange_executor_called": False,
                    "paper_executor_called": True,
                }
                return {"ok": False, "payload": result}

        if not (
            _paper_file_access_verified(PAPER_POSITIONS_FILE)
            and _paper_file_access_verified(PAPER_SEEN_FILE)
        ):
            result = {
                "ok": False,
                "status": "PAPER_DATA_MOUNT_NOT_VERIFIED",
                "reason": "caminho do estado PAPER não foi validado; execução bloqueada",
                "version": VERSION,
                "generated_at": _now_br(),
                "errors": ["PAPER_DATA_MOUNT_NOT_VERIFIED"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            return {"ok": False, "payload": result}

        try:
            positions_file_present = paper_file_exists(PAPER_POSITIONS_FILE)
            seen_file_present = paper_file_exists(PAPER_SEEN_FILE)
        except OSError:
            positions_file_present = False
            seen_file_present = False
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
            seen = _read_state_json(
                PAPER_SEEN_FILE, {}, required=seen_file_present
            ) if seen_file_present else {}
            positions = _read_state_json(
                PAPER_POSITIONS_FILE, [], required=True
            )
        except Exception:
            seen, positions = None, None
        if not _paper_state_shape_is_valid(positions, seen):
            result = {
                "ok": False,
                "status": "PAPER_STATE_INVALID",
                "reason": "estado PAPER inválido ou sem identidade idempotente; execução bloqueada",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "errors": ["estado PAPER não preserva formato e identidade idempotente válidos"],
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

        open_position_count = sum(
            1
            for item in positions
            if isinstance(item, dict) and item.get("status") == "OPEN"
        )
        if open_position_count >= max_open_positions:
            result = {
                "ok": False,
                "status": "PAPER_MAX_OPEN_POSITIONS_REACHED",
                "reason": "limite agregado de posições PAPER atingido",
                "version": VERSION,
                "generated_at": _now_br(),
                "idempotency_key": idem,
                "open_positions": open_position_count,
                "max_open_positions": max_open_positions,
                "errors": ["PAPER_MAX_OPEN_POSITIONS_REACHED"],
                "warnings": validation["warnings"],
                "exchange_executor_called": False,
                "paper_executor_called": True,
            }
            try:
                _append_jsonl(PAPER_LOG_FILE, {"event": result["status"], "payload": result})
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
    max_open_positions = _paper_max_open_positions()
    with _PAPER_EXECUTION_LOCK:
        falcon_reconciliation = _falcon_paper_reconciliation_gate()
    positions_path_verified = _paper_file_access_verified(PAPER_POSITIONS_FILE)
    seen_path_verified = _paper_file_access_verified(PAPER_SEEN_FILE)
    # Presence is informational; content is read only after both path guards pass.
    try:
        positions_file_present = paper_file_exists(PAPER_POSITIONS_FILE)
        seen_file_present = paper_file_exists(PAPER_SEEN_FILE)
    except OSError:
        positions_file_present = False
        seen_file_present = False
        positions_path_verified = False
        seen_path_verified = False
    state_files_present = positions_file_present and seen_file_present
    mount_verified = (
        _paper_data_mount_verified()
        and positions_path_verified
        and seen_path_verified
    )
    state_files_status = (
        "PAPER_STATE_FILES_MISSING" if mount_verified else "PAPER_DATA_MOUNT_NOT_VERIFIED"
    )
    positions = None
    seen = None
    state_files_valid = False
    if state_files_present and mount_verified:
        try:
            positions = _read_state_json(
                PAPER_POSITIONS_FILE, [], required=True
            )
            seen = _read_state_json(PAPER_SEEN_FILE, {}, required=True)
        except Exception:
            state_files_status = "PAPER_STATE_FILES_INVALID"
        else:
            state_files_valid = _paper_state_shape_is_valid(positions, seen)
            state_files_status = (
                "PAPER_STATE_FILES_PRESENT" if state_files_valid else "PAPER_STATE_FILES_INVALID"
            )

    if state_files_valid:
        open_positions = [p for p in positions if p.get("status") == "OPEN"]
        closed_positions = [p for p in positions if p.get("status") == "CLOSED"]
        pending_outcome = [p for p in closed_positions if not p.get("outcome_evaluated")]
        total_count = len(positions)
        open_count = len(open_positions)
        closed_count = len(closed_positions)
        pending_outcome_count = len(pending_outcome)
        seen_count = len(seen)
    else:
        total_count = open_count = closed_count = pending_outcome_count = seen_count = None

    admission_ready = bool(
        not PAPER_EXECUTION_ENABLED
        or (
            mount_verified
            and state_files_valid
            and max_open_positions is not None
            and falcon_reconciliation.get("blocked") is not True
        )
    )
    if not PAPER_EXECUTION_ENABLED:
        admission_status = "PAPER_EXECUTOR_DISABLED"
    elif not state_files_valid or not mount_verified:
        admission_status = state_files_status
    elif max_open_positions is None:
        admission_status = "PAPER_POSITION_LIMIT_CONFIG_INVALID"
    elif falcon_reconciliation.get("blocked") is True:
        admission_status = falcon_reconciliation.get("status")
    else:
        admission_status = "PAPER_ADMISSION_READY"

    return {
        "ok": admission_ready,
        "module": "paper_executor_integrated",
        "loaded": True,
        "version": VERSION,
        "generated_at": _now_br(),
        "paper_execution_enabled": PAPER_EXECUTION_ENABLED,
        "real_execution_enabled": REAL_EXECUTION_ENABLED,
        "admission_ready": admission_ready,
        "admission_status": admission_status,
        "max_open_positions": max_open_positions,
        "position_limit_config_valid": max_open_positions is not None,
        "falcon_reconciliation_required": (
            falcon_reconciliation.get("blocked") is True
        ),
        "falcon_reconciliation_status": falcon_reconciliation.get("status"),
        "state_files_present": state_files_present,
        "state_files_valid": state_files_valid,
        "state_files_status": state_files_status,
        "data_mount_verified": mount_verified,
        "open_positions": open_count,
        "closed_positions": closed_count,
        "pending_outcome": pending_outcome_count,
        "total_positions": total_count,
        "seen_count": seen_count,
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
    health = paper_integrated_health()
    if health["state_files_status"] != "PAPER_STATE_FILES_PRESENT":
        return {
            "ok": False,
            "status": health["state_files_status"],
            "generated_at": health["generated_at"],
            "count": None,
            "positions": None,
        }

    try:
        positions = _read_state_json(
            PAPER_POSITIONS_FILE, [], required=True
        )
    except Exception:
        return {
            "ok": False,
            "status": "PAPER_STATE_FILES_INVALID",
            "generated_at": _now_br(),
            "count": None,
            "positions": None,
        }
    open_positions = [p for p in positions if p.get("status") == "OPEN"]

    return {
        "ok": True,
        "generated_at": _now_br(),
        "count": len(open_positions),
        "positions": open_positions,
    }


def read_paper_integrated_log(limit: int = 20) -> Dict[str, Any]:
    if not _paper_file_access_verified(PAPER_LOG_FILE):
        return {
            "ok": False,
            "status": "PAPER_DATA_MOUNT_NOT_VERIFIED",
            "generated_at": _now_br(),
            "count": None,
            "items": None,
        }
    if not paper_file_exists(PAPER_LOG_FILE):
        return {
            "ok": True,
            "status": "PAPER_LOG_MISSING",
            "generated_at": _now_br(),
            "count": 0,
            "items": [],
        }

    try:
        lines = read_paper_text(PAPER_LOG_FILE, encoding="utf-8").splitlines()
    except Exception:
        return {
            "ok": False,
            "status": "PAPER_LOG_READ_FAILED",
            "generated_at": _now_br(),
            "count": None,
            "items": None,
        }
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
