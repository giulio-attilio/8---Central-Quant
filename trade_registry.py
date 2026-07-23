# trade_registry.py
# CENTRAL QUANT — Trade Registry
# Versão: 2026-07-11-TRADE-REGISTRY-V1.2-CLOSED-TRADE-RECONCILIATION

from __future__ import annotations

import copy
import json
import logging
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

TIMEZONE_BR = timezone(timedelta(hours=-3))
LOGGER = logging.getLogger(__name__)


def _resolve_data_dir() -> Path:
    configured = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return Path(configured)
    try:
        if os.path.isdir("/data"):
            return Path("/data")
    except Exception:
        pass
    return Path(__file__).resolve().parent / "data"


DATA_DIR = str(_resolve_data_dir())
TRADE_REGISTRY_FILE = os.environ.get("TRADE_REGISTRY_FILE", str(Path(DATA_DIR) / "trade_registry.json"))
TRADE_REGISTRY_LEGACY_FILE = str(Path(__file__).resolve().parent / "data" / "trade_registry.json")
VERSION = "2026-07-11-TRADE-REGISTRY-V1.2-CLOSED-TRADE-RECONCILIATION"
_lock = threading.RLock()

__all__ = [
    "DATA_DIR",
    "TRADE_REGISTRY_FILE",
    "TRADE_REGISTRY_LEGACY_FILE",
    "load_registry",
    "load_registry_read_only",
    "save_registry",
    "make_trade_id",
    "register_open_trade",
    "update_trade",
    "close_trade",
    "get_open_trades",
    "get_trade",
    "get_closed_trade",
    "update_closed_trade",
    "record_manual_close_outcome",
    "set_trade_registry_mode",
    "get_trade_registry_snapshot",
    "reset_trade_registry",
]


def _now() -> str:
    return datetime.now(TIMEZONE_BR).strftime("%d/%m/%Y %H:%M:%S")


def _ensure_data_dir() -> None:
    Path(TRADE_REGISTRY_FILE).parent.mkdir(parents=True, exist_ok=True)


def _empty_registry() -> Dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "updated_at": _now(),
        "open_trades": {},
        "closed_trades": [],
    }


def _normalize_symbol(symbol: Any) -> str:
    return str(symbol or "UNKNOWN").upper().replace("/", "").replace(":USDT", "").replace("-", "").strip()


def _normalize_side(side: Any) -> str:
    value = str(side or "UNKNOWN").upper().strip()
    if value in {"BUY", "LONG"}:
        return "LONG"
    if value in {"SELL", "SHORT"}:
        return "SHORT"
    return value


def _normalize_mode(value: Any) -> Optional[str]:
    mode = str(value or "").upper().strip()
    aliases = {
        "LIVE": "REAL",
        "BROKER": "REAL",
        "BINGX": "REAL",
        "DRY_RUN": "VERIFY",
        "PREVIEW": "VERIFY",
        "OBSERVATION_ONLY": "VERIFY",
    }
    mode = aliases.get(mode, mode)
    return mode if mode in {"REAL", "PAPER", "VERIFY", "SYNC_ONLY", "UNKNOWN"} else None


def _boolish(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim", "on", "sent", "filled", "executed"}:
        return True
    if text in {"0", "false", "no", "nao", "não", "off", "blocked", "denied"}:
        return False
    return None


def _infer_registry_mode(trade: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = metadata if isinstance(metadata, dict) else {}
    explicit = (
        _normalize_mode(trade.get("registry_mode"))
        or _normalize_mode(metadata.get("registry_mode"))
        or _normalize_mode(trade.get("execution_mode"))
        or _normalize_mode(metadata.get("execution_mode"))
        or _normalize_mode(trade.get("mode"))
        or _normalize_mode(metadata.get("mode"))
    )
    # UNKNOWN é um estado provisório. Não deve vencer evidências mais fortes
    # de PAPER/VERIFY/REAL encontradas no próprio trade ou na metadata.
    if explicit and explicit != "UNKNOWN":
        return explicit

    sent = _boolish(trade.get("execution_sent"))
    if sent is None:
        sent = _boolish(metadata.get("execution_sent"))
    broker_id = (
        trade.get("broker_order_id")
        or trade.get("live_order_id")
        or trade.get("order_id")
        or metadata.get("broker_order_id")
        or metadata.get("live_order_id")
        or metadata.get("order_id")
    )
    source = " ".join(
        str(x or "").lower()
        for x in [
            trade.get("source"), metadata.get("source"), trade.get("status"), metadata.get("status"),
            trade.get("bot"), metadata.get("bot"), trade.get("setup"), metadata.get("setup"),
            trade.get("event"), metadata.get("event"),
        ]
    )
    if sent is True or broker_id or any(token in source for token in ("bingx", "broker", "live_sent", "real_execution")):
        return "REAL"
    if any(token in source for token in ("paper", "smart_predator", "predator", "turtle", "donkey", "meme", "cobra", "trendpro", "trend_pro")):
        return "PAPER"
    if any(token in source for token in ("verify", "dry_run", "preview")) or sent is False:
        return "VERIFY"
    return "UNKNOWN"


def _normalize_trade_record(trade: Dict[str, Any]) -> Dict[str, Any]:
    trade = dict(trade or {})
    meta = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    trade["metadata"] = meta
    trade["bot"] = str(trade.get("bot") or "UNKNOWN").upper().strip()
    trade["setup"] = str(trade.get("setup") or "DEFAULT").upper().strip()
    trade["symbol"] = _normalize_symbol(trade.get("symbol"))
    trade["side"] = _normalize_side(trade.get("side"))
    trade.setdefault("trade_id", make_trade_id(trade.get("bot"), trade.get("symbol"), trade.get("side"), trade.get("setup")))
    trade["registry_mode"] = _infer_registry_mode(trade, meta)
    meta.setdefault("registry_mode", trade["registry_mode"])
    return trade


def _normalize_registry(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = _empty_registry()
    data.setdefault("ok", True)
    data.setdefault("version", VERSION)
    data.setdefault("updated_at", _now())
    data.setdefault("open_trades", {})
    data.setdefault("closed_trades", [])
    if not isinstance(data.get("open_trades"), dict):
        data["open_trades"] = {}
    if not isinstance(data.get("closed_trades"), list):
        if isinstance(data.get("closed_trades"), dict):
            data["closed_trades"] = list(data["closed_trades"].values())
        else:
            data["closed_trades"] = []

    data["open_trades"] = {
        str(key): _normalize_trade_record(value)
        for key, value in data["open_trades"].items()
        if isinstance(value, dict)
    }
    data["closed_trades"] = [
        _normalize_trade_record(value)
        for value in data["closed_trades"]
        if isinstance(value, dict)
    ]
    data["version"] = VERSION
    data["registry_file_active"] = TRADE_REGISTRY_FILE
    data["persistent_storage_enabled"] = str(Path(TRADE_REGISTRY_FILE)).startswith("/data") or bool(
        os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    )
    return data


def load_registry() -> Dict[str, Any]:
    _ensure_data_dir()
    path = Path(TRADE_REGISTRY_FILE)
    with _lock:
        if not path.exists() and TRADE_REGISTRY_LEGACY_FILE != TRADE_REGISTRY_FILE and Path(TRADE_REGISTRY_LEGACY_FILE).exists():
            try:
                legacy = json.loads(Path(TRADE_REGISTRY_LEGACY_FILE).read_text(encoding="utf-8"))
                reg = _normalize_registry(legacy)
                save_registry(reg)
                return reg
            except Exception:
                pass
        if not path.exists():
            reg = _empty_registry()
            save_registry(reg)
            return reg
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _normalize_registry(data)
        except Exception:
            return _empty_registry()


def load_registry_read_only() -> Dict[str, Any]:
    """Read the active Registry snapshot without creating or migrating files."""
    path = Path(TRADE_REGISTRY_FILE)
    legacy_path = Path(TRADE_REGISTRY_LEGACY_FILE)
    with _lock:
        source = path
        if not source.exists() and legacy_path != path and legacy_path.exists():
            source = legacy_path
        if not source.exists():
            return _normalize_registry(_empty_registry())
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid trade registry payload")
        return _normalize_registry(payload)


def save_registry(registry: Dict[str, Any]) -> None:
    _ensure_data_dir()
    registry = _normalize_registry(registry)
    registry["updated_at"] = _now()
    tmp = str(TRADE_REGISTRY_FILE) + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as file_obj:
            json.dump(registry, file_obj, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, TRADE_REGISTRY_FILE)


def make_trade_id(bot: Any, symbol: Any, side: Any, setup: Any = None) -> str:
    bot_n = str(bot or "UNKNOWN").upper().strip()
    setup_n = str(setup or "DEFAULT").upper().strip()
    return f"{bot_n}:{setup_n}:{_normalize_symbol(symbol)}:{_normalize_side(side)}"


def _observe_shadow_registry_snapshot(event_type: str, trade: Dict[str, Any]) -> None:
    """Publish a post-persistence copy to Shadow Mode without affecting Registry."""
    try:
        from trade_lifecycle_shadow_runtime_adapter import (
            safe_observe_shadow_event,
            safe_reconcile_shadow_trade,
        )

        snapshot = copy.deepcopy(trade or {})
        snapshot.setdefault("source_component", "TRADE_REGISTRY")
        safe_observe_shadow_event(event_type, snapshot)
        safe_reconcile_shadow_trade(snapshot)
    except Exception as exc:
        # Shadow observability is never part of the Registry success contract.
        LOGGER.warning("trade registry shadow observation failed: %s", exc)
        return


def register_open_trade(
    bot: Any,
    symbol: Any,
    side: Any,
    entry: Any,
    sl: Any = None,
    tp50: Any = None,
    setup: Any = None,
    qty: Any = None,
    source: str = "central",
    metadata: Optional[Dict[str, Any]] = None,
    registry_mode: Any = None,
    execution_mode: Any = None,
    broker_order_id: Any = None,
    client_order_id: Any = None,
    **extra: Any,
) -> Dict[str, Any]:
    bot_n = str(bot or "UNKNOWN").upper().strip()
    setup_n = str(setup or "DEFAULT").upper().strip()
    symbol_n = _normalize_symbol(symbol)
    side_n = _normalize_side(side)
    trade_id = make_trade_id(bot_n, symbol_n, side_n, setup_n)
    meta = dict(metadata or {})
    mode = _normalize_mode(registry_mode) or _normalize_mode(execution_mode)
    if mode:
        meta["registry_mode"] = mode
    if execution_mode is not None:
        meta["execution_mode"] = str(execution_mode).upper().strip()
    if broker_order_id is not None:
        meta["broker_order_id"] = broker_order_id
    if client_order_id is not None:
        meta["client_order_id"] = client_order_id

    trade: Dict[str, Any] = {
        "trade_id": trade_id,
        "status": "OPEN",
        "bot": bot_n,
        "setup": setup_n,
        "symbol": symbol_n,
        "side": side_n,
        "entry": entry,
        "sl": sl,
        "tp50": tp50,
        "qty": qty,
        "source": source,
        "opened_at": _now(),
        "opened_epoch": time.time(),
        "last_update": _now(),
        "metadata": meta,
    }
    if execution_mode is not None:
        trade["execution_mode"] = str(execution_mode).upper().strip()
    if broker_order_id is not None:
        trade["broker_order_id"] = broker_order_id
        trade["order_id"] = broker_order_id
    if client_order_id is not None:
        trade["client_order_id"] = client_order_id
    for key, value in extra.items():
        if value is not None:
            trade[key] = value
    trade = _normalize_trade_record(trade)
    # Registry mutations are whole-document writes.  Hold the same reentrant
    # lock across load/modify/save so an older writer cannot resurrect a trade
    # that reconciliation has already moved to CLOSED.
    with _lock:
        registry = load_registry()
        registry["open_trades"][trade_id] = trade
        save_registry(registry)
    _observe_shadow_registry_snapshot("SIGNAL_CREATED", trade)
    return {"ok": True, "action": "OPEN_REGISTERED", "trade_id": trade_id, "trade": trade}


def update_trade(trade_id: str, **updates: Any) -> Dict[str, Any]:
    with _lock:
        registry = load_registry()
        trade = registry["open_trades"].get(trade_id)
        if not trade:
            return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}
        for key, value in updates.items():
            if value is None:
                continue
            if key == "metadata" and isinstance(value, dict):
                trade.setdefault("metadata", {}).update(value)
            else:
                trade[key] = value
        trade["last_update"] = _now()
        trade = _normalize_trade_record(trade)
        registry["open_trades"][trade_id] = trade
        save_registry(registry)
    _observe_shadow_registry_snapshot("TRADE_UPDATED", trade)
    return {"ok": True, "action": "TRADE_UPDATED", "trade_id": trade_id, "trade": trade}


def _closed_trade_index(closed_trades: Iterable[Dict[str, Any]], trade_id: Optional[str] = None, bot: Any = None, symbol: Any = None, side: Any = None, setup: Any = None) -> Optional[int]:
    expected_id = str(trade_id or "")
    bot_n = str(bot or "").upper().strip() or None
    symbol_n = _normalize_symbol(symbol) if symbol else None
    side_n = _normalize_side(side) if side else None
    setup_n = str(setup or "").upper().strip() or None
    matches = []
    for index, trade in enumerate(closed_trades):
        if not isinstance(trade, dict):
            continue
        if expected_id and str(trade.get("trade_id") or "") == expected_id:
            matches.append(index)
            continue
        if expected_id:
            continue
        if bot_n and str(trade.get("bot") or "").upper().strip() != bot_n:
            continue
        if symbol_n and _normalize_symbol(trade.get("symbol")) != symbol_n:
            continue
        if side_n and _normalize_side(trade.get("side")) != side_n:
            continue
        if setup_n and str(trade.get("setup") or "").upper().strip() != setup_n:
            continue
        matches.append(index)
    return matches[-1] if matches else None


def get_trade(trade_id: str) -> Dict[str, Any]:
    registry = load_registry()
    if trade_id in registry.get("open_trades", {}):
        return {"ok": True, "status": "OPEN", "trade_id": trade_id, "trade": registry["open_trades"][trade_id]}
    index = _closed_trade_index(registry.get("closed_trades", []), trade_id=trade_id)
    if index is not None:
        return {"ok": True, "status": "CLOSED", "trade_id": trade_id, "index": index, "trade": registry["closed_trades"][index]}
    return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}


def get_closed_trade(trade_id: Optional[str] = None, bot: Any = None, symbol: Any = None, side: Any = None, setup: Any = None) -> Dict[str, Any]:
    registry = load_registry()
    index = _closed_trade_index(registry.get("closed_trades", []), trade_id=trade_id, bot=bot, symbol=symbol, side=side, setup=setup)
    if index is None:
        return {"ok": False, "error": "CLOSED_TRADE_NOT_FOUND", "trade_id": trade_id}
    trade = registry["closed_trades"][index]
    return {"ok": True, "status": "CLOSED", "trade_id": trade.get("trade_id"), "index": index, "trade": trade}


def update_closed_trade(
    trade_id: Optional[str] = None,
    *,
    bot: Any = None,
    symbol: Any = None,
    side: Any = None,
    setup: Any = None,
    expected_identity: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **updates: Any,
) -> Dict[str, Any]:
    with _lock:
        registry = load_registry()
        closed_trades = registry.get("closed_trades", [])
        expected = expected_identity if isinstance(expected_identity, dict) else {}
        expected_states = {
            field: strong_identity_alias_state(expected, field)
            for field in STRONG_IDENTITY_ALIASES
        }
        expected_alias_conflicts = [
            {
                "field": field,
                "normalized_values": list(state.get("normalized_values") or []),
                "aliases_present": list(state.get("aliases_present") or []),
                "reason": "STRONG_IDENTITY_ALIAS_CONFLICT",
            }
            for field, state in expected_states.items()
            if state.get("conflict")
        ]
        if expected_alias_conflicts:
            return {
                "ok": False,
                "error": "EXPECTED_STRONG_IDENTITY_ALIAS_CONFLICT",
                "trade_id": trade_id,
                "alias_conflicts": expected_alias_conflicts,
            }
        expected_strong = {
            field: state.get("value")
            for field, state in expected_states.items()
            if state.get("present") and state.get("value")
        }
        if expected_strong:
            matching_indexes = []
            alias_conflicts = []
            for candidate_index, candidate in enumerate(closed_trades):
                if not isinstance(candidate, dict):
                    continue
                if trade_id and str(candidate.get("trade_id") or "").strip() != str(trade_id).strip():
                    continue
                states = {
                    field: strong_identity_alias_state(candidate, field)
                    for field in STRONG_IDENTITY_ALIASES
                }
                internally_consistent = not any(
                    state.get("conflict") for state in states.values()
                )
                exact_match = all(
                    states[field].get("present")
                    and states[field].get("value") == value
                    for field, value in expected_strong.items()
                )
                if internally_consistent and exact_match:
                    matching_indexes.append(candidate_index)
                    continue
                supplied_values_present = all(
                    value in (states[field].get("normalized_values") or [])
                    for field, value in expected_strong.items()
                )
                if supplied_values_present:
                    for field, state in states.items():
                        if not state.get("conflict"):
                            continue
                        alias_conflicts.append(
                            {
                                "field": field,
                                "normalized_values": list(state.get("normalized_values") or []),
                                "aliases_present": list(state.get("aliases_present") or []),
                                "registry_index": candidate_index,
                                "registry_mode": str(candidate.get("registry_mode") or "").upper().strip() or None,
                                "reason": "STRONG_IDENTITY_ALIAS_CONFLICT",
                            }
                        )
            if not matching_indexes and alias_conflicts:
                return {
                    "ok": False,
                    "error": "CLOSED_TRADE_STRONG_IDENTITY_ALIAS_CONFLICT",
                    "trade_id": trade_id,
                    "candidate_count": 0,
                    "alias_conflicts": alias_conflicts,
                }
            if len(matching_indexes) != 1:
                return {
                    "ok": False,
                    "error": "CLOSED_TRADE_STRONG_IDENTITY_COUNT_INVALID",
                    "trade_id": trade_id,
                    "candidate_count": len(matching_indexes),
                }
            index = matching_indexes[0]
        else:
            index = _closed_trade_index(closed_trades, trade_id=trade_id, bot=bot, symbol=symbol, side=side, setup=setup)
        if index is None:
            return {"ok": False, "error": "CLOSED_TRADE_NOT_FOUND", "trade_id": trade_id}

        trade = dict(closed_trades[index])
        for key, value in updates.items():
            if value is not None:
                trade[key] = value
        if metadata:
            trade.setdefault("metadata", {}).update(metadata)
        trade["last_update"] = _now()
        trade = _normalize_trade_record(trade)
        closed_trades[index] = trade
        registry["closed_trades"] = closed_trades
        save_registry(registry)
    _observe_shadow_registry_snapshot("OUTCOME_CONFIRMED", trade)
    return {
        "ok": True,
        "action": "CLOSED_TRADE_UPDATED",
        "trade_id": trade.get("trade_id"),
        "index": index,
        "trade": trade,
    }


def set_trade_registry_mode(
    trade_id: Optional[str],
    registry_mode: Any,
    *,
    closed: Optional[bool] = None,
    reason: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    mode = _normalize_mode(registry_mode)
    if not mode:
        return {"ok": False, "error": "INVALID_REGISTRY_MODE", "registry_mode": registry_mode}
    metadata = {
        "registry_mode": mode,
        "registry_mode_updated_at": _now(),
    }
    if reason:
        metadata["registry_mode_reason"] = reason
    if evidence:
        metadata["registry_mode_evidence"] = evidence

    registry = load_registry()
    if closed is not True and trade_id in registry.get("open_trades", {}):
        return update_trade(trade_id, registry_mode=mode, metadata=metadata)
    return update_closed_trade(trade_id=trade_id, registry_mode=mode, metadata=metadata)


def _identity_value(trade: Dict[str, Any], field: str) -> Any:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    if field in STRONG_IDENTITY_ALIASES:
        state = strong_identity_alias_state(trade, field)
        return state.get("value") if not state.get("conflict") else None
    aliases = {
        "trade_id": ("trade_id",),
        "symbol": ("symbol", "symbol_clean"),
        "side": ("side", "direction"),
        "bot": ("bot",),
        "setup": ("setup", "signal_type", "setup_label"),
        "registry_mode": ("registry_mode",),
        "execution_mode": ("execution_mode",),
        "status": ("status",),
    }
    for key in aliases.get(field, (field,)):
        value = trade.get(key)
        if value in (None, ""):
            value = metadata.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_identity_setup(value: Any) -> str:
    return "".join(str(value or "").upper().split())


STRONG_IDENTITY_ALIASES = {
    "lifecycle_id": ("lifecycle_id", "trade_lifecycle_id"),
    "client_order_id": (
        "client_order_id",
        "clientOrderId",
        "clientOrderID",
        "client_tag",
    ),
    "order_id": (
        "open_order_id",
        "broker_order_id",
        "order_id",
        "orderId",
        "live_order_id",
        "entry_order_id",
    ),
}


def normalize_strong_identity_value(field: str, value: Any) -> str:
    """Normalize one strong identifier without weakening exact identity."""
    if field not in STRONG_IDENTITY_ALIASES:
        return ""
    normalized = str(value or "").strip()
    if field == "client_order_id":
        return normalized.upper()
    return normalized


def strong_identity_alias_state(trade: Dict[str, Any], field: str) -> Dict[str, Any]:
    """Return the internally consistent value for one strong identity field.

    Top-level and metadata aliases are deliberately inspected together.  A
    record containing distinct non-empty values is corrupt for strong matching;
    callers must not select it merely because one alias happens to match.
    """
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    aliases = STRONG_IDENTITY_ALIASES.get(field, ())
    normalized_values: List[str] = []
    aliases_present: List[str] = []
    for source_name, source in (("trade", trade), ("metadata", metadata)):
        for alias in aliases:
            raw_value = source.get(alias)
            if raw_value in (None, ""):
                continue
            value = normalize_strong_identity_value(field, raw_value)
            if not value:
                continue
            aliases_present.append(f"{source_name}.{alias}")
            if value not in normalized_values:
                normalized_values.append(value)
    conflict = len(normalized_values) > 1
    return {
        "field": field,
        "present": bool(normalized_values),
        "value": normalized_values[0] if len(normalized_values) == 1 else None,
        "normalized_values": normalized_values,
        "aliases_present": aliases_present,
        "conflict": conflict,
        "reason": "STRONG_IDENTITY_ALIAS_CONFLICT" if conflict else None,
    }


def _identity_values(trade: Dict[str, Any], field: str) -> List[str]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    if field in STRONG_IDENTITY_ALIASES:
        return list(strong_identity_alias_state(trade, field).get("normalized_values") or [])
    aliases = {
        "trade_id": ("trade_id",),
        "symbol": ("symbol", "symbol_clean"),
        "side": ("side", "direction"),
        "bot": ("bot",),
        "setup": ("setup", "signal_type", "setup_label"),
        "registry_mode": ("registry_mode",),
        "execution_mode": ("execution_mode",),
        "status": ("status",),
    }
    values: List[str] = []
    for source in (trade, metadata):
        for key in aliases.get(field, (field,)):
            value = source.get(key)
            if value in (None, ""):
                continue
            if field == "symbol":
                text = _normalize_symbol(value)
            elif field == "side":
                text = _normalize_side(value)
            elif field == "setup":
                text = _normalize_identity_setup(value)
            elif field in {"bot", "registry_mode", "execution_mode", "status"}:
                text = str(value).upper().strip()
            else:
                text = str(value).strip()
            if text not in values:
                values.append(text)
    return values


def record_manual_close_outcome(
    trade_id: str,
    close_event_id: str,
    outcome: Dict[str, Any],
    *,
    expected_identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Atomically attach a factual administrative outcome to one closed trade.

    This function has no execution authority.  It only updates an existing
    CLOSED Registry record and makes retries idempotent by close_event_id.
    """
    event_id = str(close_event_id or "").strip()
    payload = dict(outcome or {})
    if not trade_id or not event_id:
        return {"ok": False, "error": "MANUAL_CLOSE_OUTCOME_IDENTITY_REQUIRED", "trade_id": trade_id}
    expected = expected_identity if isinstance(expected_identity, dict) else {}
    lifecycle_id = str(expected.get("lifecycle_id") or payload.get("lifecycle_id") or "").strip()
    if not lifecycle_id:
        return {"ok": False, "error": "MANUAL_CLOSE_OUTCOME_LIFECYCLE_ID_REQUIRED", "trade_id": trade_id}

    with _lock:
        registry = load_registry()
        open_trades = registry.get("open_trades", {})
        open_records = list(open_trades.values()) if isinstance(open_trades, dict) else []
        if any(
            isinstance(item, dict)
            and str(_identity_value(item, "lifecycle_id") or "").strip() == lifecycle_id
            for item in open_records
        ):
            return {
                "ok": False,
                "error": "TRADE_STILL_OPEN",
                "trade_id": trade_id,
                "lifecycle_id": lifecycle_id,
            }
        closed_trades = registry.get("closed_trades", [])
        matching_indexes = [
            index
            for index, item in enumerate(closed_trades)
            if (
                isinstance(item, dict)
                and str(_identity_value(item, "lifecycle_id") or "").strip() == lifecycle_id
                and str(item.get("status") or "").upper().strip() == "CLOSED"
                and str(item.get("bot") or "").upper().strip() == "FALCON"
            )
        ]
        if len(matching_indexes) != 1:
            return {
                "ok": False,
                "error": "CLOSED_FALCON_LIFECYCLE_CANDIDATE_COUNT_INVALID",
                "trade_id": trade_id,
                "lifecycle_id": lifecycle_id,
                "candidate_count": len(matching_indexes),
            }

        index = matching_indexes[0]
        trade = dict(closed_trades[index])
        if str(trade.get("trade_id") or "") != str(trade_id):
            return {
                "ok": False,
                "error": "TRADE_ID_MISMATCH",
                "trade_id": trade_id,
                "resolved_trade_id": trade.get("trade_id"),
                "lifecycle_id": lifecycle_id,
            }
        metadata = dict(trade.get("metadata") or {}) if isinstance(trade.get("metadata"), dict) else {}
        if str(trade.get("status") or "").upper().strip() != "CLOSED":
            return {"ok": False, "error": "TRADE_NOT_CLOSED", "trade_id": trade_id}
        if str(trade.get("bot") or "").upper().strip() != "FALCON":
            return {"ok": False, "error": "TRADE_NOT_FALCON", "trade_id": trade_id}
        if expected_identity is not None:
            identity_ok, identity_comparison = _identity_matches(trade, expected_identity)
            if not identity_ok:
                return {
                    "ok": False,
                    "error": "TRADE_IDENTITY_MISMATCH",
                    "trade_id": trade_id,
                    "identity_comparison": identity_comparison,
                }

        manual_keys = list(trade.get("manual_close_outcome_keys") or metadata.get("manual_close_outcome_keys") or [])
        manual_keys = [str(value) for value in manual_keys if value not in (None, "")]
        outcome_id = str(payload.get("outcome_id") or "").strip()
        existing_outcome_id = str(trade.get("outcome_id") or metadata.get("outcome_id") or "").strip()
        if event_id in manual_keys and outcome_id and existing_outcome_id and existing_outcome_id != outcome_id:
            return {
                "ok": False,
                "error": "CLOSE_EVENT_ID_OUTCOME_CONFLICT",
                "trade_id": trade_id,
                "existing_outcome_id": existing_outcome_id,
                "requested_outcome_id": outcome_id,
            }
        if event_id in manual_keys or (outcome_id and existing_outcome_id == outcome_id):
            return {
                "ok": True,
                "action": "ALREADY_APPLIED",
                "trade_id": trade_id,
                "trade": trade,
                "outcome_id": existing_outcome_id or outcome_id,
            }

        existing_status = str(trade.get("outcome_status") or metadata.get("outcome_status") or "").upper().strip()
        existing_source = str(trade.get("outcome_source") or metadata.get("outcome_source") or "").upper().strip()
        pending = _boolish(trade.get("financial_reconciliation_pending"))
        if pending is None:
            pending = _boolish(metadata.get("financial_reconciliation_pending"))
        economic_fields = (
            "exit_price", "pnl_pct", "result_pct", "pnl_r", "result_r",
            "realized_pnl", "gross_pnl_usdt", "outcome_id",
        )
        economic_evidence = any(
            trade.get(field) not in (None, "") or metadata.get(field) not in (None, "")
            for field in economic_fields
        )
        pending_statuses = {"", "PENDING_OUTCOME", "RECONCILED_WITHOUT_PNL"}
        stronger_source = bool(existing_source and existing_source != "MANUAL_CLOSE_RECONCILIATION")
        if existing_outcome_id or stronger_source or (existing_status not in pending_statuses and economic_evidence) or (pending is False and economic_evidence):
            return {
                "ok": False,
                "error": "STRONGER_FACTUAL_OUTCOME_ALREADY_EXISTS",
                "trade_id": trade_id,
                "existing_outcome_id": existing_outcome_id or None,
                "existing_outcome_status": existing_status or None,
                "existing_outcome_source": existing_source or None,
            }

        lifecycle_id = str(payload.get("lifecycle_id") or "").strip()
        idempotency_key = f"{lifecycle_id}:{event_id}" if lifecycle_id else event_id
        manual_keys = list(dict.fromkeys([*manual_keys, event_id, idempotency_key]))
        financial_fields = (
            "exit_price", "closed_quantity", "close_timestamp", "close_reason",
            "close_classification", "pnl_pct", "result_pct", "gross_pnl_usdt",
            "pnl_r", "result_r", "tp50_hit", "outcome_status", "outcome_source",
            "financial_reconciliation_pending", "learning_eligible", "outcome_id",
            "outcome_hash", "data_quality", "lifecycle_id", "close_event_id",
        )
        for field in financial_fields:
            if field in payload:
                trade[field] = payload.get(field)
        trade["manual_close_outcome_keys"] = manual_keys
        trade["last_update"] = _now()
        metadata.update({field: trade.get(field) for field in financial_fields if field in trade})
        metadata["manual_close_outcome_keys"] = list(manual_keys)
        trade["metadata"] = metadata
        trade = _normalize_trade_record(trade)
        closed_trades[index] = trade
        registry["closed_trades"] = closed_trades
        save_registry(registry)

    _observe_shadow_registry_snapshot("OUTCOME_CONFIRMED", trade)
    return {
        "ok": True,
        "action": "OUTCOME_RECORDED",
        "trade_id": trade_id,
        "outcome_id": trade.get("outcome_id"),
        "index": index,
        "trade": trade,
    }
def _identity_matches(trade: Dict[str, Any], expected_identity: Optional[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
    expected = expected_identity if isinstance(expected_identity, dict) else {}
    compared = {}
    for field in (
        "trade_id",
        "lifecycle_id",
        "order_id",
        "client_order_id",
        "symbol",
        "side",
        "bot",
        "setup",
        "registry_mode",
        "execution_mode",
        "status",
    ):
        expected_value = expected.get(field)
        if expected_value in (None, ""):
            continue
        if field in STRONG_IDENTITY_ALIASES:
            normalized_expected = normalize_strong_identity_value(
                field, expected_value
            )
        elif field == "symbol":
            normalized_expected = _normalize_symbol(expected_value)
        elif field == "side":
            normalized_expected = _normalize_side(expected_value)
        elif field == "setup":
            normalized_expected = _normalize_identity_setup(expected_value)
        elif field in {"bot", "registry_mode", "execution_mode", "status"}:
            normalized_expected = str(expected_value).upper().strip()
        else:
            normalized_expected = str(expected_value).strip()
        strong_state = (
            strong_identity_alias_state(trade, field)
            if field in STRONG_IDENTITY_ALIASES
            else None
        )
        current_values = (
            list(strong_state.get("normalized_values") or [])
            if strong_state is not None
            else _identity_values(trade, field)
        )
        current_value = (
            strong_state.get("value")
            if strong_state is not None
            else (current_values[0] if current_values else None)
        )
        compared[field] = {
            "expected": normalized_expected,
            "current": None if current_value in (None, "") else str(current_value),
            "all_current_values": current_values,
        }
        if strong_state is not None:
            compared[field].update(
                {
                    "aliases_present": list(strong_state.get("aliases_present") or []),
                    "conflict": bool(strong_state.get("conflict")),
                    "reason": strong_state.get("reason"),
                }
            )
        if (
            not current_values
            or (strong_state is not None and strong_state.get("conflict"))
            or current_value != normalized_expected
        ):
            return False, compared
    return bool(compared), compared


def close_trade(
    trade_id: str,
    exit_price: Any = None,
    pnl_pct: Any = None,
    pnl_r: Any = None,
    reason: Any = None,
    metadata: Optional[Dict[str, Any]] = None,
    registry_mode: Any = None,
    realized_pnl: Any = None,
    fee: Any = None,
    funding: Any = None,
    broker_close_order_id: Any = None,
    expected_identity: Optional[Dict[str, Any]] = None,
    expected_open_trade_id_count: Optional[int] = None,
    clear_financial_results: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    with _lock:
        registry = load_registry()
        if expected_open_trade_id_count is not None:
            expected_trade_id = str(trade_id or "").strip()
            matching_open_ids = [
                str(key)
                for key, item in registry.get("open_trades", {}).items()
                if isinstance(item, dict)
                and expected_trade_id in _identity_values(item, "trade_id")
            ]
            if len(matching_open_ids) != int(expected_open_trade_id_count):
                return {
                    "ok": False,
                    "error": "TRADE_OPEN_IDENTITY_COUNT_MISMATCH",
                    "trade_id": trade_id,
                    "expected_open_trade_id_count": int(expected_open_trade_id_count),
                    "actual_open_trade_id_count": len(matching_open_ids),
                    "matching_registry_keys": matching_open_ids,
                }
        current = registry["open_trades"].get(trade_id)
        if current and expected_identity is not None:
            identity_ok, identity_comparison = _identity_matches(current, expected_identity)
            if not identity_ok:
                return {
                    "ok": False,
                    "error": "TRADE_IDENTITY_MISMATCH",
                    "trade_id": trade_id,
                    "identity_comparison": identity_comparison,
                }
        trade = registry["open_trades"].pop(trade_id, None)
        if not trade:
            existing = get_closed_trade(trade_id=trade_id)
            if existing.get("ok"):
                if expected_identity is not None:
                    identity_ok, identity_comparison = _identity_matches(existing.get("trade") or {}, expected_identity)
                    if not identity_ok:
                        return {
                            "ok": False,
                            "error": "TRADE_IDENTITY_MISMATCH",
                            "trade_id": trade_id,
                            "identity_comparison": identity_comparison,
                        }
                    # Compare-and-close callers asked to close an OPEN record.
                    # A concurrent factual close wins and must never have its
                    # reason, outcome or economics rewritten by reconciliation.
                    return {
                        "ok": True,
                        "action": "TRADE_ALREADY_CLOSED",
                        "trade_id": trade_id,
                        "trade": existing.get("trade"),
                        "identity_comparison": identity_comparison,
                    }
                return update_closed_trade(
                    trade_id=trade_id,
                    exit_price=exit_price,
                    pnl_pct=pnl_pct,
                    pnl_r=pnl_r,
                    result_pct=pnl_pct,
                    result_r=pnl_r,
                    close_reason=reason,
                    realized_pnl=realized_pnl,
                    fee=fee,
                    funding=funding,
                    broker_close_order_id=broker_close_order_id,
                    registry_mode=_normalize_mode(registry_mode),
                    metadata=metadata,
                    **extra,
                )
            return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}

        trade["status"] = "CLOSED"
        trade["exit_price"] = exit_price
        trade["pnl_pct"] = pnl_pct
        trade["pnl_r"] = pnl_r
        trade["result_pct"] = None if clear_financial_results else (pnl_pct if pnl_pct is not None else trade.get("result_pct"))
        trade["result_r"] = None if clear_financial_results else (pnl_r if pnl_r is not None else trade.get("result_r"))
        if clear_financial_results:
            # A broker-flat reconciliation without factual close economics must
            # not leave an older provisional alias available to statistics or
            # learning.  Explicit metadata is preserved for audit; only the
            # top-level financial result projections are made unknown.
            for field in (
                "pnl_pct",
                "pnl_r",
                "result_pct",
                "result_r",
                "realized_pnl",
                "realized_pnl_usdt",
                "net_pnl",
                "net_pnl_usdt",
                "pnl_usdt",
                "profit_usdt",
                "profit_loss",
                "r_multiple",
                "outcome",
                "outcome_id",
                "broker_close_order_id",
                "close_order_id",
                "close_qty",
                "closed_qty",
                "fee",
                "funding",
            ):
                trade[field] = None
        trade["close_reason"] = reason
        trade["closed_at"] = _now()
        trade["closed_epoch"] = time.time()
        trade["last_update"] = _now()
        if realized_pnl is not None:
            trade["realized_pnl"] = realized_pnl
        if fee is not None:
            trade["fee"] = fee
        if funding is not None:
            trade["funding"] = funding
        if broker_close_order_id is not None:
            trade["broker_close_order_id"] = broker_close_order_id
        if registry_mode is not None:
            trade["registry_mode"] = _normalize_mode(registry_mode) or str(registry_mode).upper().strip()
        if metadata:
            trade.setdefault("metadata", {}).update(metadata)
        for key, value in extra.items():
            if value is not None:
                trade[key] = value
        trade = _normalize_trade_record(trade)
        registry["closed_trades"].append(trade)
        save_result = save_registry(registry)
        if save_result is False:
            return {
                "ok": False,
                "error": "TRADE_REGISTRY_SAVE_FAILED",
                "trade_id": trade_id,
            }
    _observe_shadow_registry_snapshot("CLOSE_CONFIRMED", trade)
    return {"ok": True, "action": "TRADE_CLOSED", "trade_id": trade_id, "trade": trade}


def get_open_trades(bot: Any = None, symbol: Any = None, side: Any = None) -> Dict[str, Any]:
    registry = load_registry()
    trades = list(registry.get("open_trades", {}).values())
    if bot:
        trades = [trade for trade in trades if str(trade.get("bot")).upper() == str(bot).upper()]
    if symbol:
        symbol_n = _normalize_symbol(symbol)
        trades = [trade for trade in trades if _normalize_symbol(trade.get("symbol")) == symbol_n]
    if side:
        side_n = _normalize_side(side)
        trades = [trade for trade in trades if _normalize_side(trade.get("side")) == side_n]
    return {"ok": True, "count": len(trades), "trades": trades}


def get_trade_registry_snapshot() -> Dict[str, Any]:
    registry = load_registry()
    open_trades = list(registry.get("open_trades", {}).values())
    closed_trades = registry.get("closed_trades", [])
    by_bot: Dict[str, int] = {}
    by_symbol: Dict[str, int] = {}
    by_side: Dict[str, int] = {}
    by_mode: Dict[str, int] = {}
    for trade in open_trades:
        bot = trade.get("bot", "UNKNOWN")
        symbol = trade.get("symbol", "UNKNOWN")
        side = trade.get("side", "UNKNOWN")
        mode = trade.get("registry_mode", "UNKNOWN")
        by_bot[bot] = by_bot.get(bot, 0) + 1
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
        by_side[side] = by_side.get(side, 0) + 1
        by_mode[mode] = by_mode.get(mode, 0) + 1
    return {
        "ok": True,
        "version": registry.get("version"),
        "updated_at": registry.get("updated_at"),
        "registry_file_active": TRADE_REGISTRY_FILE,
        "persistent_storage_enabled": registry.get("persistent_storage_enabled"),
        "open_count": len(open_trades),
        "closed_count": len(closed_trades),
        "by_bot": by_bot,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_mode": by_mode,
        "open_trades": open_trades,
    }


def reset_trade_registry(confirm: bool = False) -> Dict[str, Any]:
    if not confirm:
        return {"ok": False, "error": "CONFIRM_REQUIRED"}
    registry = _empty_registry()
    save_registry(registry)
    return {"ok": True, "action": "TRADE_REGISTRY_RESET"}
