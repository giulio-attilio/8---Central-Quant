# trade_registry.py
# CENTRAL QUANT — Trade Registry
# Versão: 2026-07-11-TRADE-REGISTRY-V1.2-CLOSED-TRADE-RECONCILIATION

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
import threading
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
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
    "load_registry_raw_read_only",
    "save_registry",
    "make_trade_id",
    "register_open_trade",
    "update_trade",
    "close_trade",
    "get_open_trades",
    "get_trade",
    "get_closed_trade",
    "update_closed_trade",
    "STRONG_IDENTITY_ALIASES",
    "strong_identity_alias_state",
    "normalize_strong_identity_value",
    "closed_trade_identity_state",
    "merge_closed_trade_records",
    "audit_closed_trade_identities",
    "preview_historical_strong_identity_backfill",
    "backfill_historical_strong_identity",
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


def _closed_trade_records_from_collection(value: Any) -> List[Dict[str, Any]]:
    """Preserve a historical dict key as non-identity collection context.

    Some legacy Registry snapshots represented ``closed_trades`` as an object
    instead of a list.  Object keys are not guaranteed to be factual record or
    exchange identifiers: numeric indexes are common and can be reused by
    independent snapshots.  Therefore an arbitrary key must never be promoted
    to the strong/specific ``registry_record_id`` identity field.

    A key that is the only available canonical ``trade_id`` is retained for
    legacy compatibility.  Every other non-empty key is exposed solely as
    ``registry_collection_key``.  An explicit ``registry_record_id`` already
    present in the record (or its metadata) is left untouched and continues to
    participate in canonical CLOSED identity.
    """
    if isinstance(value, list):
        if any(not isinstance(record, dict) for record in value):
            raise ValueError("invalid trade registry closed trade record")
        return [copy.deepcopy(record) for record in value]
    if not isinstance(value, dict):
        raise ValueError("invalid trade registry closed_trades")
    records: List[Dict[str, Any]] = []
    for collection_key, record in value.items():
        if not isinstance(record, dict):
            raise ValueError("invalid trade registry closed trade record")
        item = copy.deepcopy(record)
        key_text = str(collection_key or "").strip()
        trade_id = str(item.get("trade_id") or "").strip()
        if key_text and not trade_id and ":" in key_text:
            # Historical registries commonly used the canonical trade_id as the
            # object key while omitting it from the value.
            item["trade_id"] = key_text
            trade_id = key_text
        elif key_text and key_text != trade_id:
            # This is provenance of the source collection, not proof of an
            # execution identity.  In particular, indexes such as "69" can
            # recur in unrelated Registry snapshots.
            item["registry_collection_key"] = key_text
        records.append(item)
    return records


def _normalize_registry(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("invalid trade registry payload")
    data.setdefault("ok", True)
    data.setdefault("version", VERSION)
    data.setdefault("updated_at", _now())
    data.setdefault("open_trades", {})
    data.setdefault("closed_trades", [])
    if not isinstance(data.get("open_trades"), dict):
        raise ValueError("invalid trade registry open_trades")
    data["closed_trades"] = _closed_trade_records_from_collection(
        data.get("closed_trades")
    )
    if any(
        not isinstance(value, dict)
        for value in data["open_trades"].values()
    ):
        raise ValueError("invalid trade registry open trade record")
    data["open_trades"] = {
        str(key): _normalize_trade_record(value)
        for key, value in data["open_trades"].items()
    }
    data["closed_trades"] = [
        _normalize_trade_record(value)
        for value in data["closed_trades"]
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
            legacy = json.loads(
                Path(TRADE_REGISTRY_LEGACY_FILE).read_text(encoding="utf-8")
            )
            if not isinstance(legacy, dict):
                raise ValueError("invalid legacy trade registry payload")
            reg = _normalize_registry(legacy)
            write_result = save_registry(reg)
            if write_result is False:
                raise OSError("trade registry migration was not persisted")
            return reg
        if not path.exists():
            reg = _empty_registry()
            write_result = save_registry(reg)
            if write_result is False:
                raise OSError("empty trade registry initialization was not persisted")
            return reg
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("invalid trade registry payload")
        return _normalize_registry(data)


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


def load_registry_raw_read_only() -> Dict[str, Any]:
    """Read the exact Registry document without normalization or mutation."""
    path = Path(TRADE_REGISTRY_FILE)
    legacy_path = Path(TRADE_REGISTRY_LEGACY_FILE)
    with _lock:
        source = path
        if not source.exists() and legacy_path != path and legacy_path.exists():
            source = legacy_path
        if not source.exists():
            return {
                "ok": True,
                "version": VERSION,
                "open_trades": {},
                "closed_trades": [],
            }
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid trade registry payload")
        result = copy.deepcopy(payload)
        result.setdefault("open_trades", {})
        result.setdefault("closed_trades", [])
        return result


def save_registry(registry: Dict[str, Any]) -> bool:
    _ensure_data_dir()
    registry = _normalize_registry(registry)
    registry["updated_at"] = _now()
    tmp = str(TRADE_REGISTRY_FILE) + ".tmp"
    with _lock:
        with open(tmp, "w", encoding="utf-8") as file_obj:
            json.dump(registry, file_obj, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, TRADE_REGISTRY_FILE)
    return True


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
        if save_registry(registry) is False:
            return {
                "ok": False,
                "error": "TRADE_REGISTRY_SAVE_FAILED",
                "trade_id": trade_id,
            }
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
        if save_registry(registry) is False:
            return {
                "ok": False,
                "error": "TRADE_REGISTRY_SAVE_FAILED",
                "trade_id": trade_id,
            }
    _observe_shadow_registry_snapshot("TRADE_UPDATED", trade)
    return {"ok": True, "action": "TRADE_UPDATED", "trade_id": trade_id, "trade": trade}


def _closed_trade_indexes(
    closed_trades: Iterable[Dict[str, Any]],
    trade_id: Optional[str] = None,
    bot: Any = None,
    symbol: Any = None,
    side: Any = None,
    setup: Any = None,
) -> List[int]:
    expected_id = str(trade_id or "")
    bot_n = str(bot or "").upper().strip() or None
    symbol_n = _normalize_symbol(symbol) if symbol else None
    side_n = _normalize_side(side) if side else None
    setup_n = _normalize_identity_setup(setup) or None
    matches: List[int] = []
    for index, trade in enumerate(closed_trades):
        if not isinstance(trade, dict):
            continue
        if expected_id and str(trade.get("trade_id") or "") != expected_id:
            continue
        if bot_n and str(trade.get("bot") or "").upper().strip() != bot_n:
            continue
        if symbol_n and _normalize_symbol(trade.get("symbol")) != symbol_n:
            continue
        if side_n and _normalize_side(trade.get("side")) != side_n:
            continue
        if setup_n and _normalize_identity_setup(trade.get("setup")) != setup_n:
            continue
        matches.append(index)
    return matches


def _closed_trade_index(
    closed_trades: Iterable[Dict[str, Any]],
    trade_id: Optional[str] = None,
    bot: Any = None,
    symbol: Any = None,
    side: Any = None,
    setup: Any = None,
) -> Optional[int]:
    """Return an index only when the legacy selector is unambiguous."""
    matches = _closed_trade_indexes(
        closed_trades,
        trade_id=trade_id,
        bot=bot,
        symbol=symbol,
        side=side,
        setup=setup,
    )
    return matches[0] if len(matches) == 1 else None


def get_trade(trade_id: str) -> Dict[str, Any]:
    registry = load_registry()
    if trade_id in registry.get("open_trades", {}):
        return {"ok": True, "status": "OPEN", "trade_id": trade_id, "trade": registry["open_trades"][trade_id]}
    matching_indexes = _closed_trade_indexes(
        registry.get("closed_trades", []), trade_id=trade_id
    )
    if len(matching_indexes) > 1:
        return {
            "ok": False,
            "error": "CLOSED_TRADE_IDENTITY_AMBIGUOUS",
            "trade_id": trade_id,
            "candidate_count": len(matching_indexes),
        }
    index = matching_indexes[0] if matching_indexes else None
    if index is not None:
        return {"ok": True, "status": "CLOSED", "trade_id": trade_id, "index": index, "trade": registry["closed_trades"][index]}
    return {"ok": False, "error": "TRADE_NOT_FOUND", "trade_id": trade_id}


def get_closed_trade(
    trade_id: Optional[str] = None,
    bot: Any = None,
    symbol: Any = None,
    side: Any = None,
    setup: Any = None,
    expected_identity: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    registry = load_registry()
    closed_trades = registry.get("closed_trades", [])
    matching_indexes = _closed_trade_indexes(
        closed_trades,
        trade_id=trade_id,
        bot=bot,
        symbol=symbol,
        side=side,
        setup=setup,
    )
    expected = expected_identity if isinstance(expected_identity, dict) else {}
    expected_states = {
        field: strong_identity_alias_state(expected, field)
        for field in STRONG_IDENTITY_ALIASES
    }
    if any(state.get("conflict") for state in expected_states.values()):
        return {
            "ok": False,
            "error": "EXPECTED_STRONG_IDENTITY_ALIAS_CONFLICT",
            "trade_id": trade_id,
        }
    expected_strong = {
        field: state.get("value")
        for field, state in expected_states.items()
        if state.get("value")
    }
    if expected_strong:
        matching_indexes = [
            index
            for index in matching_indexes
            if all(
                not strong_identity_alias_state(closed_trades[index], field).get(
                    "conflict"
                )
                and strong_identity_alias_state(
                    closed_trades[index], field
                ).get("value")
                == value
                for field, value in expected_strong.items()
            )
        ]
    if not matching_indexes:
        return {"ok": False, "error": "CLOSED_TRADE_NOT_FOUND", "trade_id": trade_id}
    if len(matching_indexes) != 1:
        return {
            "ok": False,
            "error": "CLOSED_TRADE_IDENTITY_AMBIGUOUS",
            "trade_id": trade_id,
            "candidate_count": len(matching_indexes),
        }
    index = matching_indexes[0]
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
            matching_indexes = _closed_trade_indexes(
                closed_trades,
                trade_id=trade_id,
                bot=bot,
                symbol=symbol,
                side=side,
                setup=setup,
            )
            if len(matching_indexes) > 1:
                return {
                    "ok": False,
                    "error": "CLOSED_TRADE_IDENTITY_AMBIGUOUS",
                    "trade_id": trade_id,
                    "candidate_count": len(matching_indexes),
                }
            index = matching_indexes[0] if matching_indexes else None
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
        if save_registry(registry) is False:
            return {
                "ok": False,
                "error": "TRADE_REGISTRY_SAVE_FAILED",
                "trade_id": trade_id,
                "index": index,
            }
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
    if field in CLOSED_TRADE_LEGACY_IDENTITY_ALIASES:
        state = _closed_trade_legacy_identity_states(trade).get(field) or {}
        return state.get("value") if not state.get("conflict") else None
    for source in (trade, metadata):
        value = source.get(field)
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

CLOSED_TRADE_IDENTITY_VERSION = (
    "2026-07-23-CLOSED-TRADE-CANONICAL-IDENTITY-V1"
)
CLOSED_TRADE_SPECIFIC_ID_FIELDS = (
    "registry_record_id",
    "historical_record_id",
    "closed_trade_id",
    "record_id",
    "position_id",
    "falcon_position_id",
    "execution_attempt_id",
    "attempt_id",
    "execution_id",
    "trade_uuid",
    "position_uuid",
)
CLOSED_TRADE_CONTEXTUAL_SPECIFIC_ID_FIELDS = frozenset(
    {
        "record_id",
        "position_id",
        "falcon_position_id",
        "execution_attempt_id",
        "attempt_id",
    }
)
CLOSED_TRADE_TRANSIENT_METADATA_FIELDS = (
    "closed_history_sources",
    "closed_identity_merge",
)
CLOSED_TRADE_FINANCIAL_FIELDS = frozenset(
    {
        "outcome",
        "outcome_status",
        "outcome_source",
        "outcome_id",
        "outcome_hash",
        "data_quality",
        "outcome_data_quality",
        "exit",
        "exit_price",
        "exit_avg_price",
        "average_exit_price",
        "closed_quantity",
        "closed_qty",
        "close_qty",
        "remaining_qty",
        "close_timestamp",
        "closed_at",
        "close_reason",
        "exit_reason",
        "pnl",
        "pnl_pct",
        "pnl_r",
        "result",
        "result_pct",
        "result_r",
        "r_multiple",
        "gross_pnl",
        "gross_pnl_usdt",
        "pnl_usdt",
        "profit_usdt",
        "profit_loss",
        "realized_pnl",
        "realized_pnl_usdt",
        "net_pnl",
        "net_pnl_usdt",
        "fee",
        "fees",
        "opening_fee",
        "closing_fee",
        "funding",
        "funding_fee",
        "broker_close_order_id",
        "close_order_id",
        "exit_order_id",
        "tp50_hit",
        "financial_reconciliation_pending",
        "learning_eligible",
    }
)
CLOSED_TRADE_FINANCIAL_NUMERIC_FIELDS = frozenset(
    {
        "exit",
        "exit_price",
        "exit_avg_price",
        "average_exit_price",
        "closed_quantity",
        "closed_qty",
        "close_qty",
        "remaining_qty",
        "pnl",
        "pnl_pct",
        "pnl_r",
        "result",
        "result_pct",
        "result_r",
        "r_multiple",
        "gross_pnl",
        "gross_pnl_usdt",
        "pnl_usdt",
        "profit_usdt",
        "profit_loss",
        "realized_pnl",
        "realized_pnl_usdt",
        "net_pnl",
        "net_pnl_usdt",
        "fee",
        "fees",
        "opening_fee",
        "closing_fee",
        "funding",
        "funding_fee",
    }
)

# Semantic aliases that represent the same financial fact.  They are compared
# under one canonical field so differently shaped historical copies cannot be
# fused into a contradictory hybrid (for example ``exit`` from one source and
# ``exit_price`` from another).
CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES = {
    "outcome_status": ("outcome_status",),
    "outcome_source": ("outcome_source",),
    "outcome_id": ("outcome_id",),
    "outcome_hash": ("outcome_hash",),
    "data_quality": ("data_quality", "outcome_data_quality"),
    "exit_price": (
        "exit",
        "exit_price",
        "exit_avg_price",
        "average_exit_price",
    ),
    "closed_quantity": ("closed_quantity", "closed_qty", "close_qty"),
    "remaining_qty": ("remaining_qty",),
    "close_timestamp": ("close_timestamp", "closed_at"),
    "close_reason": ("close_reason", "exit_reason"),
    "pnl": ("pnl",),
    "pnl_pct": ("pnl_pct", "result_pct"),
    "pnl_r": ("pnl_r", "result_r", "r_multiple"),
    "result": ("result",),
    "gross_pnl_usdt": (
        "gross_pnl",
        "gross_pnl_usdt",
        "pnl_usdt",
        "profit_usdt",
        "profit_loss",
        "realized_pnl",
        "realized_pnl_usdt",
    ),
    "net_pnl_usdt": ("net_pnl", "net_pnl_usdt"),
    "fee": ("fee",),
    "fees": ("fees",),
    "opening_fee": ("opening_fee",),
    "closing_fee": ("closing_fee",),
    "funding": ("funding", "funding_fee"),
    "close_order_id": (
        "broker_close_order_id",
        "close_order_id",
        "exit_order_id",
    ),
    "tp50_hit": ("tp50_hit",),
    "financial_reconciliation_pending": (
        "financial_reconciliation_pending",
    ),
    "learning_eligible": ("learning_eligible",),
}
CLOSED_TRADE_FINANCIAL_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES.items()
    for alias in aliases
}

CLOSED_TRADE_LEGACY_IDENTITY_ALIASES = {
    "trade_id": ("trade_id",),
    "registry_mode": ("registry_mode",),
    "execution_mode": ("execution_mode",),
    "opened_at": (
        "opened_at",
        "open_timestamp",
        "created_at",
        "entry_timestamp",
    ),
    "closed_at": ("closed_at", "close_timestamp", "exit_timestamp"),
    "entry": ("entry", "entry_price", "filled_entry_price"),
    "qty": ("qty", "initial_qty", "quantity", "quantity_opened"),
    "bot": ("bot",),
    "setup": ("setup", "signal_type", "setup_label"),
    "symbol": ("symbol", "symbol_clean"),
    "side": ("side", "direction"),
    "status": ("status",),
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


def _closed_trade_stable_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        return repr(value)


def _closed_trade_digest(value: Any) -> str:
    return hashlib.sha256(_closed_trade_stable_json(value).encode("utf-8")).hexdigest()


def _closed_trade_identity_document(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Exclude obsolete merge annotations from the exact-copy fingerprint."""
    document = copy.deepcopy(trade) if isinstance(trade, dict) else {}
    document.pop("closed_history_identity_merge", None)
    metadata = document.get("metadata")
    if isinstance(metadata, dict):
        metadata = copy.deepcopy(metadata)
        for field in CLOSED_TRADE_TRANSIENT_METADATA_FIELDS:
            metadata.pop(field, None)
        if metadata:
            document["metadata"] = metadata
        else:
            document.pop("metadata", None)
    return document


def _closed_trade_first_value(trade: Dict[str, Any], aliases: Iterable[str]) -> Any:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    for source in (trade, metadata):
        for alias in aliases:
            value = source.get(alias)
            if value not in (None, ""):
                return value
    return None


def _closed_trade_legacy_identity_value(field: str, value: Any) -> str:
    if field in {"opened_at", "closed_at"}:
        return _closed_trade_timestamp(value)
    if field in {"entry", "qty"}:
        return _closed_trade_number(value)
    if field == "setup":
        return _normalize_identity_setup(value)
    if field == "symbol":
        normalized = _normalize_symbol(value)
        return "" if normalized == "UNKNOWN" else normalized
    if field == "side":
        normalized = _normalize_side(value)
        return "" if normalized == "UNKNOWN" else normalized
    if field in {
        "registry_mode",
        "execution_mode",
        "bot",
        "status",
    }:
        normalized = _closed_trade_text(value, upper=True)
        return "" if normalized == "UNKNOWN" else normalized
    return _closed_trade_text(value)


def _closed_trade_legacy_identity_states(
    trade: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = (
        trade.get("metadata")
        if isinstance(trade.get("metadata"), dict)
        else {}
    )
    states: Dict[str, Dict[str, Any]] = {}
    for field, aliases in CLOSED_TRADE_LEGACY_IDENTITY_ALIASES.items():
        normalized_values: List[str] = []
        aliases_present: List[str] = []
        for source_name, source in (("trade", trade), ("metadata", metadata)):
            for alias in aliases:
                raw_value = source.get(alias)
                if raw_value in (None, ""):
                    continue
                value = _closed_trade_legacy_identity_value(field, raw_value)
                if not value:
                    continue
                aliases_present.append(f"{source_name}.{alias}")
                if value not in normalized_values:
                    normalized_values.append(value)
        conflict = len(normalized_values) > 1
        states[field] = {
            "field": field,
            "present": bool(normalized_values),
            "value": (
                normalized_values[0] if len(normalized_values) == 1 else None
            ),
            "normalized_values": normalized_values,
            "aliases_present": aliases_present,
            "conflict": conflict,
            "reason": (
                "LEGACY_IDENTITY_ALIAS_CONFLICT" if conflict else None
            ),
        }
    return states


def _closed_trade_text(value: Any, *, upper: bool = False) -> str:
    text = str(value or "").strip()
    return text.upper() if upper else text


def _closed_trade_number(value: Any) -> str:
    try:
        if value in (None, ""):
            return ""
        number = Decimal(str(value).replace(",", ".").strip())
        if not number.is_finite():
            return ""
        if number == 0:
            return "0"
        return format(number.normalize(), "f")
    except (InvalidOperation, ValueError, TypeError):
        return ""


def _closed_trade_timestamp(value: Any) -> str:
    text = _closed_trade_text(value)
    if not text:
        return ""
    try:
        candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat()
    except Exception:
        pass
    try:
        parsed = datetime.strptime(text, "%d/%m/%Y %H:%M:%S").replace(
            tzinfo=TIMEZONE_BR
        )
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return text


def _closed_trade_specific_identity_states(trade: Dict[str, Any]) -> List[Dict[str, Any]]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    states: List[Dict[str, Any]] = []
    for field in CLOSED_TRADE_SPECIFIC_ID_FIELDS:
        values: List[str] = []
        aliases_present: List[str] = []
        for source_name, source in (("trade", trade), ("metadata", metadata)):
            raw_value = source.get(field)
            value = _closed_trade_text(raw_value)
            if not value:
                continue
            aliases_present.append(f"{source_name}.{field}")
            if value not in values:
                values.append(value)
        states.append(
            {
                "field": field,
                "present": bool(values),
                "value": values[0] if len(values) == 1 else None,
                "normalized_values": values,
                "aliases_present": aliases_present,
                "conflict": len(values) > 1,
                "reason": (
                    "SPECIFIC_IDENTITY_ALIAS_CONFLICT"
                    if len(values) > 1
                    else None
                ),
            }
        )
    return states


def _closed_trade_legacy_components(
    trade: Dict[str, Any],
    states: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, str]:
    states = states or _closed_trade_legacy_identity_states(trade)

    def value(field: str, default: str = "") -> str:
        normalized = (states.get(field) or {}).get("value")
        return str(normalized) if normalized not in (None, "") else default

    return {
        "trade_id": value("trade_id"),
        "registry_mode": value("registry_mode", "UNKNOWN"),
        "execution_mode": value("execution_mode", "UNKNOWN"),
        "opened_at": value("opened_at"),
        "closed_at": value("closed_at"),
        "entry": value("entry"),
        "qty": value("qty"),
        # Ownership fields make the legacy fallback more conservative without
        # weakening the tuple required by the historical compatibility contract.
        "bot": value("bot"),
        "setup": value("setup"),
        "symbol": value("symbol"),
        "side": value("side"),
        "status": value("status"),
    }


def closed_trade_identity_state(trade: Dict[str, Any]) -> Dict[str, Any]:
    """Build a conservative, deterministic identity for one CLOSED execution.

    ``trade_id`` is intentionally not unique over time in Central Quant.  It is
    therefore used only as one component of the legacy fallback, never as the
    primary CLOSED key.
    """
    trade = copy.deepcopy(trade) if isinstance(trade, dict) else {}
    strong_states = {
        field: strong_identity_alias_state(trade, field)
        for field in STRONG_IDENTITY_ALIASES
    }
    specific_states = _closed_trade_specific_identity_states(trade)
    legacy_states = _closed_trade_legacy_identity_states(trade)
    conflicts = [
        {
            "field": field,
            "normalized_values": list(state.get("normalized_values") or []),
            "aliases_present": list(state.get("aliases_present") or []),
            "reason": state.get("reason"),
        }
        for field, state in strong_states.items()
        if state.get("conflict")
    ]
    conflicts.extend(
        {
            "field": state.get("field"),
            "normalized_values": list(state.get("normalized_values") or []),
            "aliases_present": list(state.get("aliases_present") or []),
            "reason": state.get("reason"),
        }
        for state in specific_states
        if state.get("conflict")
    )
    conflicts.extend(
        {
            "field": state.get("field"),
            "normalized_values": list(state.get("normalized_values") or []),
            "aliases_present": list(state.get("aliases_present") or []),
            "reason": state.get("reason"),
        }
        for state in legacy_states.values()
        if state.get("conflict")
    )
    fingerprint = _closed_trade_digest(_closed_trade_identity_document(trade))
    legacy = _closed_trade_legacy_components(trade, legacy_states)
    strong_values = {
        field: state.get("value")
        for field, state in strong_states.items()
        if state.get("value")
    }
    merge_tokens: List[str] = []
    identity_kind = "LEGACY_FALLBACK"
    primary_token = ""

    if conflicts:
        identity_kind = "CONFLICT_QUARANTINED"
        primary_token = f"conflict|{fingerprint}"
        merge_tokens = [f"exact_conflict|{fingerprint}"]
    else:
        lifecycle_id = strong_values.get("lifecycle_id")
        client_order_id = strong_values.get("client_order_id")
        order_id = strong_values.get("order_id")
        if lifecycle_id:
            merge_tokens.append(f"lifecycle|{lifecycle_id}")
        if client_order_id and order_id:
            merge_tokens.append(f"client_order|{client_order_id}|{order_id}")
        for state in specific_states:
            if state.get("value"):
                field = str(state.get("field") or "")
                if field in CLOSED_TRADE_CONTEXTUAL_SPECIFIC_ID_FIELDS:
                    contextual_identity = {
                        "field": field,
                        "value": state.get("value"),
                        "trade_id": legacy.get("trade_id"),
                        "registry_mode": legacy.get("registry_mode"),
                        "execution_mode": legacy.get("execution_mode"),
                        "opened_at": legacy.get("opened_at"),
                        "closed_at": legacy.get("closed_at"),
                    }
                    temporal_identity = (
                        contextual_identity.get("opened_at")
                        or contextual_identity.get("closed_at")
                    )
                    modes_known = (
                        contextual_identity.get("registry_mode") != "UNKNOWN"
                        and contextual_identity.get("execution_mode") != "UNKNOWN"
                    )
                    if (
                        contextual_identity.get("trade_id")
                        and temporal_identity
                        and modes_known
                    ):
                        merge_tokens.append(
                            "specific_context|"
                            + _closed_trade_digest(contextual_identity)
                        )
                else:
                    merge_tokens.append(
                        f"specific|{field}|{state.get('value')}"
                    )
        if lifecycle_id:
            identity_kind = "LIFECYCLE_ID"
            primary_token = f"lifecycle|{lifecycle_id}"
        elif client_order_id and order_id:
            identity_kind = "CLIENT_AND_ORDER_ID"
            primary_token = f"client_order|{client_order_id}|{order_id}"
        else:
            specific_token = next(
                (
                    token
                    for token in merge_tokens
                    if token.startswith(("specific|", "specific_context|"))
                ),
                None,
            )
            if specific_token:
                identity_kind = "SPECIFIC_EXECUTION_ID"
                primary_token = specific_token
            elif strong_values:
                # A client ID or order ID by itself is not sufficient to fuse
                # historical executions.  Exact duplicate documents can still
                # deduplicate without bridging unrelated records.
                identity_kind = "PARTIAL_STRONG_IDENTITY"
                primary_token = (
                    "partial|"
                    + _closed_trade_digest(strong_values)
                    + "|"
                    + fingerprint
                )
                merge_tokens = [f"exact|{fingerprint}"]
            else:
                legacy_required = (
                    legacy.get("trade_id"),
                    (
                        legacy.get("registry_mode")
                        if legacy.get("registry_mode") != "UNKNOWN"
                        else ""
                    ),
                    (
                        legacy.get("execution_mode")
                        if legacy.get("execution_mode") != "UNKNOWN"
                        else ""
                    ),
                    legacy.get("opened_at") or legacy.get("closed_at"),
                    legacy.get("entry"),
                    legacy.get("qty"),
                )
                legacy_complete = all(legacy_required)
                if legacy_complete:
                    primary_token = "legacy|" + _closed_trade_digest(legacy)
                    merge_tokens = [primary_token]
                else:
                    identity_kind = "LEGACY_INCOMPLETE_EXACT_ONLY"
                    primary_token = f"legacy_incomplete|{fingerprint}"
                    merge_tokens = [f"exact_legacy|{fingerprint}"]

    legacy_components = legacy
    invalid_closed_status = bool(
        legacy_components.get("status")
        and legacy_components.get("status") != "CLOSED"
    )
    return {
        "version": CLOSED_TRADE_IDENTITY_VERSION,
        "canonical_key": primary_token,
        "identity_kind": identity_kind,
        "merge_tokens": sorted(set(merge_tokens)),
        "fingerprint": fingerprint,
        "trade_id": legacy_components.get("trade_id"),
        "registry_mode": legacy_components.get("registry_mode"),
        "execution_mode": legacy_components.get("execution_mode"),
        "strong_identity": strong_values,
        "strong_identity_states": strong_states,
        "specific_identity_states": specific_states,
        "legacy_identity_states": legacy_states,
        "legacy_fallback": legacy_components,
        "legacy_fallback_complete": bool(
            identity_kind == "LEGACY_FALLBACK"
        ),
        "invalid_closed_status": invalid_closed_status,
        "has_alias_conflict": bool(conflicts),
        "alias_conflicts": conflicts,
    }


def _closed_trade_state_value(
    state: Dict[str, Any], field: str
) -> str:
    value = (state.get("legacy_fallback") or {}).get(field)
    if (
        field == "trade_id"
        and value == "UNKNOWN:DEFAULT:UNKNOWN:UNKNOWN"
    ):
        return ""
    if field in {
        "registry_mode",
        "execution_mode",
        "bot",
        "setup",
        "symbol",
        "side",
        "status",
    } and value == "UNKNOWN":
        return ""
    if (
        field == "setup"
        and value == "DEFAULT"
        and not _closed_trade_state_value(state, "bot")
    ):
        # ``_normalize_trade_record`` historically materialized DEFAULT beside
        # an UNKNOWN bot even when a sparse source supplied no setup at all.
        # Treat only that generic pair as absent; a factual bot + DEFAULT setup
        # remains a real identity value.
        return ""
    return str(value or "")


def _closed_trade_states_compatible(
    left_state: Dict[str, Any],
    right_state: Dict[str, Any],
    *,
    require_shared_token: bool = True,
) -> Tuple[bool, Optional[str]]:
    left_invalid_status = bool(left_state.get("invalid_closed_status"))
    right_invalid_status = bool(right_state.get("invalid_closed_status"))
    if left_invalid_status or right_invalid_status:
        if (
            left_invalid_status
            and right_invalid_status
            and left_state.get("fingerprint") == right_state.get("fingerprint")
        ):
            return True, None
        return False, "NON_CLOSED_RECORD_IN_CLOSED_HISTORY"
    left_conflict = bool(left_state.get("has_alias_conflict"))
    right_conflict = bool(right_state.get("has_alias_conflict"))
    if left_conflict or right_conflict:
        if (
            left_conflict
            and right_conflict
            and left_state.get("fingerprint") == right_state.get("fingerprint")
        ):
            return True, None
        return False, "STRONG_IDENTITY_ALIAS_CONFLICT"

    for field in STRONG_IDENTITY_ALIASES:
        left_value = (left_state.get("strong_identity") or {}).get(field)
        right_value = (right_state.get("strong_identity") or {}).get(field)
        if left_value and right_value and left_value != right_value:
            return False, f"{field.upper()}_DIVERGENCE"

    left_specific = {
        state.get("field"): state.get("value")
        for state in (left_state.get("specific_identity_states") or [])
        if state.get("value")
    }
    right_specific = {
        state.get("field"): state.get("value")
        for state in (right_state.get("specific_identity_states") or [])
        if state.get("value")
    }
    for field in sorted(set(left_specific) & set(right_specific)):
        if left_specific[field] != right_specific[field]:
            return False, f"{str(field).upper()}_DIVERGENCE"

    for field in (
        "trade_id",
        "registry_mode",
        "execution_mode",
        "bot",
        "setup",
        "symbol",
        "side",
        "opened_at",
        "closed_at",
        "status",
    ):
        left_value = _closed_trade_state_value(left_state, field)
        right_value = _closed_trade_state_value(right_state, field)
        if left_value and right_value and left_value != right_value:
            return False, f"{field.upper()}_DIVERGENCE"

    for field in ("entry", "qty"):
        left_value = (left_state.get("legacy_fallback") or {}).get(field)
        right_value = (right_state.get("legacy_fallback") or {}).get(field)
        if left_value and right_value and left_value != right_value:
            return False, f"{field.upper()}_DIVERGENCE"

    shared_tokens = set(left_state.get("merge_tokens") or []) & set(
        right_state.get("merge_tokens") or []
    )
    if require_shared_token and not shared_tokens:
        return False, "NO_SHARED_EXECUTION_IDENTITY"
    return True, None


def _closed_trade_values_compatible(
    left: Dict[str, Any], right: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    return _closed_trade_states_compatible(
        closed_trade_identity_state(left),
        closed_trade_identity_state(right),
    )


def _closed_trade_semantically_empty(
    value: Any, path: Tuple[str, ...] = ()
) -> bool:
    if value in (None, "", [], {}):
        return True
    field = str(path[-1] if path else "")
    text = str(value).upper().strip() if isinstance(value, str) else ""
    if field in {
        "registry_mode",
        "execution_mode",
        "bot",
        "symbol",
        "symbol_clean",
        "side",
        "direction",
        "status",
    } and text == "UNKNOWN":
        return True
    if field in {"setup", "signal_type", "setup_label"} and text == "DEFAULT":
        return True
    return False


def _closed_trade_nonempty_count(
    value: Any, path: Tuple[str, ...] = ()
) -> int:
    if isinstance(value, dict):
        return sum(
            1 + _closed_trade_nonempty_count(item, path + (str(key),))
            for key, item in value.items()
            if not _closed_trade_semantically_empty(
                item, path + (str(key),)
            )
        )
    if isinstance(value, list):
        return sum(
            _closed_trade_nonempty_count(item, path) for item in value
        )
    return int(not _closed_trade_semantically_empty(value, path))


def _closed_trade_outcome_authority(trade: Dict[str, Any]) -> int:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    outcome = trade.get("outcome") if isinstance(trade.get("outcome"), dict) else {}
    metadata_outcome = (
        metadata.get("outcome")
        if isinstance(metadata.get("outcome"), dict)
        else {}
    )
    texts = {
        str(source.get(field) or "").upper().strip()
        for source in (trade, metadata, outcome, metadata_outcome)
        for field in ("outcome_status", "outcome_source", "data_quality")
    }
    score = 0
    if "MANUAL_CLOSE_RECONCILIATION" in texts:
        score += 1000
    if texts & {"OUTCOME_RECORDED", "OUTCOME_CONFIRMED", "MANUAL_CONFIRMED"}:
        score += 500
    if texts & {"BROKER_CONFIRMED", "HIGH_REAL", "FACTUAL"}:
        score += 250
    if any(
        source.get(field) not in (None, "")
        for source in (trade, metadata, outcome, metadata_outcome)
        for field in ("outcome_id", "outcome_hash", "exit_price", "realized_pnl")
    ):
        score += 100
    return score


def _closed_trade_outcome_source_score(source: Dict[str, Any]) -> int:
    source = source if isinstance(source, dict) else {}
    texts = {
        str(source.get(field) or "").upper().strip()
        for field in ("outcome_status", "outcome_source", "data_quality")
    }
    score = 0
    if "MANUAL_CLOSE_RECONCILIATION" in texts:
        score += 1000
    if texts & {"OUTCOME_RECORDED", "OUTCOME_CONFIRMED", "MANUAL_CONFIRMED"}:
        score += 500
    if texts & {"BROKER_CONFIRMED", "HIGH_REAL", "FACTUAL"}:
        score += 250
    return score


def _closed_trade_authoritative_outcome_values(
    trade: Dict[str, Any],
) -> Dict[str, Any]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    outcome = trade.get("outcome") if isinstance(trade.get("outcome"), dict) else {}
    metadata_outcome = (
        metadata.get("outcome")
        if isinstance(metadata.get("outcome"), dict)
        else {}
    )
    sources = [trade, metadata, outcome, metadata_outcome]
    ranked_sources = sorted(
        enumerate(sources),
        key=lambda item: (_closed_trade_outcome_source_score(item[1]), -item[0]),
        reverse=True,
    )
    fields = tuple(sorted(CLOSED_TRADE_FINANCIAL_FIELDS - {"outcome"}))
    values: Dict[str, Any] = {}
    for field in fields:
        for _index, source in ranked_sources:
            value = source.get(field)
            if value not in (None, ""):
                values[field] = copy.deepcopy(value)
                break
    return values


def _closed_trade_authoritative_outcome_document(
    trade: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the strongest nested outcome document in one Registry record."""
    trade = trade if isinstance(trade, dict) else {}
    metadata = (
        trade.get("metadata")
        if isinstance(trade.get("metadata"), dict)
        else {}
    )
    candidates = [
        value
        for value in (trade.get("outcome"), metadata.get("outcome"))
        if isinstance(value, dict) and value
    ]
    if not candidates:
        return None
    ranked = sorted(
        (copy.deepcopy(value) for value in candidates),
        key=lambda value: (
            _closed_trade_outcome_source_score(value),
            _closed_trade_nonempty_count(value),
            _closed_trade_stable_json(value),
        ),
        reverse=True,
    )
    return ranked[0]


def _closed_trade_preference_key(trade: Dict[str, Any]) -> Tuple[Any, ...]:
    state = closed_trade_identity_state(trade)
    strong_count = len(state.get("strong_identity") or {})
    registry_mode = str(state.get("registry_mode") or "").upper()
    execution_mode = str(state.get("execution_mode") or "").upper()
    return (
        100 if registry_mode == "REAL" else 10 if registry_mode == "VERIFY" else 0,
        50 if execution_mode == "LIVE" else 0,
        strong_count,
        _closed_trade_outcome_authority(trade),
        _closed_trade_nonempty_count(trade),
        state.get("fingerprint") or "",
    )


def _closed_trade_conservative_value(
    preferred: Any,
    other: Any,
    *,
    protect_financial: bool = False,
    path: Tuple[str, ...] = (),
) -> Any:
    if _closed_trade_semantically_empty(preferred, path):
        return copy.deepcopy(other)
    if _closed_trade_semantically_empty(other, path):
        return copy.deepcopy(preferred)
    if isinstance(preferred, dict) and isinstance(other, dict):
        merged = copy.deepcopy(preferred)
        for key in sorted(set(preferred) | set(other)):
            child_path = path + (str(key),)
            if protect_financial and (
                str(key) in CLOSED_TRADE_FINANCIAL_FIELDS
                or "outcome" in child_path
            ):
                continue
            if key not in merged:
                merged[key] = copy.deepcopy(other.get(key))
            elif key in other:
                merged[key] = _closed_trade_conservative_value(
                    merged.get(key),
                    other.get(key),
                    protect_financial=protect_financial,
                    path=child_path,
                )
        return merged
    if isinstance(preferred, list) and isinstance(other, list):
        values = {
            _closed_trade_stable_json(item): copy.deepcopy(item)
            for item in preferred + other
        }
        return [values[key] for key in sorted(values)]
    # The preferred record is selected by factual/outcome authority.  Conflicting
    # non-empty values never overwrite it.
    return copy.deepcopy(preferred)


def _closed_trade_financial_projection(trade: Dict[str, Any]) -> Dict[str, Any]:
    projection: Dict[str, Any] = {}
    for field, values in _closed_trade_financial_source_values(trade).items():
        if len(values) == 1:
            projection[field] = copy.deepcopy(next(iter(values.values())))
    return projection


def _closed_trade_financial_value_key(field: str, value: Any) -> str:
    canonical = CLOSED_TRADE_FINANCIAL_ALIAS_TO_CANONICAL.get(field, field)
    if canonical == "close_timestamp":
        return _closed_trade_stable_json(_closed_trade_timestamp(value))
    if any(
        alias in CLOSED_TRADE_FINANCIAL_NUMERIC_FIELDS
        for alias in CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES.get(
            canonical, (canonical,)
        )
    ):
        normalized = _closed_trade_number(value)
        if not normalized:
            return "invalid_numeric|" + _closed_trade_stable_json(value)
        return _closed_trade_stable_json(normalized)
    if canonical in {
        "outcome_status",
        "outcome_source",
        "data_quality",
        "close_reason",
    }:
        return _closed_trade_stable_json(_closed_trade_text(value, upper=True))
    return _closed_trade_stable_json(value)


def _closed_trade_financial_source_values(
    trade: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    outcome = trade.get("outcome") if isinstance(trade.get("outcome"), dict) else {}
    metadata_outcome = (
        metadata.get("outcome")
        if isinstance(metadata.get("outcome"), dict)
        else {}
    )
    values: Dict[str, Dict[str, Any]] = {}
    for source in (trade, metadata, outcome, metadata_outcome):
        for canonical, aliases in CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES.items():
            for alias in aliases:
                value = source.get(alias)
                if value in (None, "", [], {}):
                    continue
                values.setdefault(canonical, {})[
                    _closed_trade_financial_value_key(canonical, value)
                ] = copy.deepcopy(value)
    return values


def _closed_trade_has_financial_family_value(
    trade: Dict[str, Any], canonical: str
) -> bool:
    trade = trade if isinstance(trade, dict) else {}
    metadata = (
        trade.get("metadata")
        if isinstance(trade.get("metadata"), dict)
        else {}
    )
    outcome = (
        trade.get("outcome")
        if isinstance(trade.get("outcome"), dict)
        else {}
    )
    metadata_outcome = (
        metadata.get("outcome")
        if isinstance(metadata.get("outcome"), dict)
        else {}
    )
    aliases = CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES.get(
        canonical, (canonical,)
    )
    return any(
        source.get(alias) not in (None, "", [], {})
        for source in (trade, metadata, outcome, metadata_outcome)
        for alias in aliases
    )


def _closed_trade_financial_conflict_state(
    records: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Classify financial differences without hiding factual contradictions.

    A confirmed/manual or broker-factual projection may safely replace an
    empty/generic projection.  Two factual projections that disagree, however,
    must remain separate and block any automatic Registry rewrite.
    """
    evidence_by_field: Dict[str, List[Tuple[int, str]]] = {}
    internal_conflict_fields = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        authority = _closed_trade_outcome_authority(record)
        source_values = _closed_trade_financial_source_values(record)
        internal_conflict_fields.update(
            field for field, values in source_values.items() if len(values) > 1
        )
        for field, value in _closed_trade_financial_projection(record).items():
            evidence_by_field.setdefault(field, []).append(
                (authority, _closed_trade_financial_value_key(field, value))
            )

    difference_fields: List[str] = []
    material_fields = set(internal_conflict_fields)
    for field, evidence in evidence_by_field.items():
        all_values = {value for _authority, value in evidence}
        if len(all_values) <= 1:
            continue
        difference_fields.append(field)
        maximum_authority = max(authority for authority, _value in evidence)
        if maximum_authority >= 250:
            # Generic/provisional aliases cannot mask a factual confirmation,
            # but Broker/manual confirmations must agree with one another.
            comparable_values = {
                value
                for authority, value in evidence
                if authority >= 250
            }
        else:
            # With no confirmed authority there is no safe winner.
            comparable_values = all_values
        if len(comparable_values) > 1:
            material_fields.add(field)

    return {
        "financial_difference_fields": sorted(difference_fields),
        "internal_financial_conflict_fields": sorted(internal_conflict_fields),
        "material_financial_conflict_fields": sorted(material_fields),
        "financial_difference_count": len(difference_fields),
        "material_financial_conflict_count": len(material_fields),
    }


def _closed_trade_merge_group(
    members: List[Dict[str, Any]], sources: Optional[List[str]] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ranked = sorted(
        (copy.deepcopy(member) for member in members if isinstance(member, dict)),
        key=_closed_trade_preference_key,
        reverse=True,
    )
    merged = ranked[0] if ranked else {}
    outcome_record = (
        max(
            ranked,
            key=lambda record: (
                _closed_trade_outcome_authority(record),
                _closed_trade_preference_key(record),
            ),
        )
        if ranked
        else {}
    )
    outcome_authority = _closed_trade_outcome_authority(outcome_record)
    financial_state = _closed_trade_financial_conflict_state(ranked)
    for record in ranked[1:]:
        merged = _closed_trade_conservative_value(
            merged,
            record,
            protect_financial=outcome_authority > 0,
        )
    if (
        ranked
        and outcome_authority > 0
        and not financial_state.get("material_financial_conflict_fields")
    ):
        # Re-project the most authoritative factual/manual outcome after the
        # structural merge so a generic CLOSED alias cannot mask it.
        merged.update(_closed_trade_authoritative_outcome_values(outcome_record))
        authoritative_outcome = (
            _closed_trade_authoritative_outcome_document(outcome_record)
        )
        if authoritative_outcome:
            merged["outcome"] = copy.deepcopy(authoritative_outcome)
            metadata = (
                copy.deepcopy(merged.get("metadata"))
                if isinstance(merged.get("metadata"), dict)
                else {}
            )
            metadata["outcome"] = copy.deepcopy(authoritative_outcome)
            merged["metadata"] = metadata
    # A unique non-conflicting factual value may enrich an incomplete copy, but
    # no field is synthesized when the sources disagree.
    all_financial_values: Dict[str, Dict[str, Any]] = {}
    for record in ranked:
        for field, values in _closed_trade_financial_source_values(record).items():
            all_financial_values.setdefault(field, {}).update(values)
    for field, values in all_financial_values.items():
        if (
            not _closed_trade_has_financial_family_value(merged, field)
            and len(values) == 1
        ):
            merged[field] = copy.deepcopy(next(iter(values.values())))

    return merged, {
        "copy_count": len(ranked),
        "source_count": len({str(source) for source in (sources or []) if source}),
        "outcome_authority": outcome_authority,
        **financial_state,
    }


def merge_closed_trade_records(
    records: Iterable[Dict[str, Any]],
    *,
    sources: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Merge only records proven to represent the same CLOSED execution."""
    source_list = list(sources) if sources is not None else []
    input_records = list(records) if records is not None else []
    invalid_input_type_counts: Dict[str, int] = {}
    for record in input_records:
        if isinstance(record, dict):
            continue
        record_type = type(record).__name__
        invalid_input_type_counts[record_type] = (
            invalid_input_type_counts.get(record_type, 0) + 1
        )
    invalid_input_records = [
        {
            "reason": "INVALID_CLOSED_RECORD_TYPE",
            "record_type": record_type,
            "count": count,
        }
        for record_type, count in sorted(invalid_input_type_counts.items())
    ]
    items: List[Dict[str, Any]] = []
    for index, record in enumerate(input_records):
        if not isinstance(record, dict):
            continue
        state = closed_trade_identity_state(record)
        items.append(
            {
                "record": copy.deepcopy(record),
                "state": state,
                "input_index": index,
                "source": (
                    str(source_list[index])
                    if index < len(source_list) and source_list[index]
                    else None
                ),
            }
        )
    items.sort(
        key=lambda item: (
            str(item["state"].get("canonical_key") or ""),
            str(item["state"].get("fingerprint") or ""),
        )
    )

    # Build connected components from typed identity tokens first.  A component
    # is merged only when every pair is compatible.  This prevents an incomplete
    # bridge (for example client/order shared by two different lifecycles) from
    # being assigned to whichever record happens to sort first.
    token_members: Dict[str, List[int]] = {}
    for index, item in enumerate(items):
        for token in item["state"].get("merge_tokens") or []:
            token_members.setdefault(str(token), []).append(index)
    adjacency = [set([index]) for index in range(len(items))]
    for member_indexes in token_members.values():
        if len(member_indexes) <= 1:
            continue
        anchor = member_indexes[0]
        for member_index in member_indexes[1:]:
            adjacency[anchor].add(member_index)
            adjacency[member_index].add(anchor)

    components: List[List[int]] = []
    seen_indexes = set()
    for start in range(len(items)):
        if start in seen_indexes:
            continue
        pending = [start]
        component: List[int] = []
        seen_indexes.add(start)
        while pending:
            current = pending.pop()
            component.append(current)
            for linked in sorted(adjacency[current]):
                if linked not in seen_indexes:
                    seen_indexes.add(linked)
                    pending.append(linked)
        components.append(sorted(component))

    groups: List[List[Dict[str, Any]]] = []
    ambiguous: List[Dict[str, Any]] = []
    for component_indexes in components:
        component = [items[index] for index in component_indexes]
        incompatibilities: List[str] = []
        for left in range(len(component)):
            for right in range(left + 1, len(component)):
                compatible, reason = _closed_trade_states_compatible(
                    component[left]["state"],
                    component[right]["state"],
                    require_shared_token=False,
                )
                if not compatible:
                    incompatibilities.append(str(reason or "INCOMPATIBLE"))
        if not incompatibilities:
            groups.append(component)
            continue
        ambiguous.append(
            {
                "trade_ids": sorted(
                    {
                        str(member["state"].get("trade_id") or "")
                        for member in component
                        if member["state"].get("trade_id")
                    }
                ),
                "reason": "AMBIGUOUS_EXECUTION_IDENTITY_BRIDGE_PRESERVED",
                "record_count": len(component),
                "incompatibility_reasons": sorted(set(incompatibilities)),
            }
        )
        # Doubt means preserve every original execution independently.
        groups.extend([[member] for member in component])

    output: List[Dict[str, Any]] = []
    merge_groups: List[Dict[str, Any]] = []
    financial_conflicts: List[Dict[str, Any]] = []
    for group in groups:
        member_records = [member.get("record") or {} for member in group]
        member_sources = [
            member.get("source") for member in group if member.get("source")
        ]
        merged, group_diagnostics = _closed_trade_merge_group(
            member_records, member_sources if member_sources else None
        )
        material_financial_conflicts = list(
            group_diagnostics.get("material_financial_conflict_fields") or []
        )
        if material_financial_conflicts and len(group) > 1:
            # A single hybrid CLOSED would invent certainty.  Preserve every
            # source record and require an explicit financial reconciliation.
            output.extend(copy.deepcopy(member_records))
        else:
            output.append(merged)
        if material_financial_conflicts:
            merged_state = closed_trade_identity_state(merged)
            financial_conflicts.append(
                {
                    "trade_id": merged_state.get("trade_id"),
                    "canonical_key": merged_state.get("canonical_key"),
                    "record_count": len(group),
                    "reason": "FACTUAL_FINANCIAL_OUTCOME_CONFLICT_PRESERVED",
                    "financial_conflict_fields": material_financial_conflicts,
                    "financial_difference_fields": list(
                        group_diagnostics.get("financial_difference_fields")
                        or []
                    ),
                }
            )
        if len(group) > 1 and not material_financial_conflicts:
            state = closed_trade_identity_state(merged)
            merge_groups.append(
                {
                    "trade_id": state.get("trade_id"),
                    "canonical_key": state.get("canonical_key"),
                    "identity_kind": state.get("identity_kind"),
                    "copy_count": len(group),
                    "source_count": group_diagnostics.get("source_count", 0),
                    "financial_difference_count": group_diagnostics.get(
                        "financial_difference_count", 0
                    ),
                }
            )
    output.sort(
        key=lambda record: (
            str(closed_trade_identity_state(record).get("canonical_key") or ""),
            str(closed_trade_identity_state(record).get("fingerprint") or ""),
        )
    )

    input_by_trade_id: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        trade_id = str(item["state"].get("trade_id") or "")
        if trade_id:
            input_by_trade_id.setdefault(trade_id, []).append(item)
    duplicate_trade_ids = {
        trade_id: values
        for trade_id, values in input_by_trade_id.items()
        if len(values) > 1
    }
    real_verify_groups = 0
    for values in duplicate_trade_ids.values():
        registry_modes = {
            str(item["state"].get("registry_mode") or "").upper()
            for item in values
        }
        execution_modes = {
            str(item["state"].get("execution_mode") or "").upper()
            for item in values
        }
        has_real = "REAL" in registry_modes or "LIVE" in execution_modes
        has_verify = (
            "VERIFY" in registry_modes
            or bool(execution_modes & {"VERIFY", "DRY_RUN", "PREVIEW"})
        )
        if has_real and has_verify:
            real_verify_groups += 1
    alias_conflicts = [
        {
            "record_fingerprint": item["state"].get("fingerprint"),
            "trade_id": item["state"].get("trade_id"),
            "registry_mode": item["state"].get("registry_mode"),
            "conflicts": copy.deepcopy(item["state"].get("alias_conflicts") or []),
        }
        for item in items
        if item["state"].get("has_alias_conflict")
    ]
    strong_alias_conflict_records = [
        item
        for item in alias_conflicts
        if any(
            conflict.get("reason") == "STRONG_IDENTITY_ALIAS_CONFLICT"
            for conflict in (item.get("conflicts") or [])
        )
    ]
    specific_alias_conflict_records = [
        item
        for item in alias_conflicts
        if any(
            conflict.get("reason") == "SPECIFIC_IDENTITY_ALIAS_CONFLICT"
            for conflict in (item.get("conflicts") or [])
        )
    ]
    legacy_alias_conflict_records = [
        item
        for item in alias_conflicts
        if any(
            conflict.get("reason") == "LEGACY_IDENTITY_ALIAS_CONFLICT"
            for conflict in (item.get("conflicts") or [])
        )
    ]
    invalid_closed_records = [
        {
            "record_fingerprint": item["state"].get("fingerprint"),
            "trade_id": item["state"].get("trade_id"),
            "registry_mode": item["state"].get("registry_mode"),
            "status": (
                item["state"].get("legacy_fallback") or {}
            ).get("status"),
            "reason": "NON_CLOSED_RECORD_IN_CLOSED_HISTORY",
        }
        for item in items
        if item["state"].get("invalid_closed_status")
    ]
    diagnostics = {
        "version": CLOSED_TRADE_IDENTITY_VERSION,
        "input_record_count": len(input_records),
        "valid_input_record_count": len(items),
        "invalid_input_record_count": sum(
            invalid_input_type_counts.values()
        ),
        "output_record_count": len(output),
        "preserved_record_count": len(output),
        # Every output row is either one proven merged execution or one
        # deliberately preserved uncertain/conflicting record.  Counting
        # canonical-key strings would undercount conflicts that deliberately
        # share a lifecycle token.
        "distinct_execution_count": len(groups),
        "duplicate_execution_copy_count": max(0, len(items) - len(output)),
        "trade_id_collision_group_count": len(duplicate_trade_ids),
        "trade_id_collision_record_count": sum(
            len(values) for values in duplicate_trade_ids.values()
        ),
        "real_verify_collision_group_count": real_verify_groups,
        "identity_alias_conflict_count": len(alias_conflicts),
        "strong_alias_conflict_count": len(
            strong_alias_conflict_records
        ),
        "specific_alias_conflict_count": len(
            specific_alias_conflict_records
        ),
        "legacy_alias_conflict_count": len(
            legacy_alias_conflict_records
        ),
        "invalid_closed_record_count": len(invalid_closed_records),
        "ambiguous_identity_bridge_count": len(ambiguous),
        "financial_conflict_count": sum(
            len(item.get("financial_conflict_fields") or [])
            for item in financial_conflicts
        ),
        "merge_group_count": len(merge_groups),
        "safe_to_commit": (
            not alias_conflicts
            and not invalid_input_records
            and not invalid_closed_records
            and not ambiguous
            and not financial_conflicts
        ),
        "merge_groups": merge_groups[:100],
        "invalid_input_records": invalid_input_records[:100],
        "alias_conflicts": alias_conflicts[:100],
        "invalid_closed_records": invalid_closed_records[:100],
        "ambiguous_identity_bridges": ambiguous[:100],
        "financial_conflicts": financial_conflicts[:100],
    }
    return {"records": output, "diagnostics": diagnostics}


def audit_closed_trade_identities(
    closed_trades: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a read-only projection of CLOSED identity collisions."""
    merged = merge_closed_trade_records(closed_trades)
    diagnostics = copy.deepcopy(merged.get("diagnostics") or {})
    diagnostics.update(
        {
            "ok": bool(diagnostics.get("safe_to_commit")),
            "audit_completed": True,
            "status": (
                "CLOSED_IDENTITY_AUDIT_OK"
                if diagnostics.get("safe_to_commit")
                else "CLOSED_IDENTITY_REVIEW_REQUIRED"
            ),
            "read_only": True,
            "write_executed": False,
            "automatic_changes": False,
        }
    )
    return diagnostics


HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_ACK = (
    "REAL_CLOSE_STRONG_IDENTITY_BACKFILL_V1"
)
HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_VERSION = (
    "2026-07-23-HISTORICAL-STRONG-IDENTITY-BACKFILL-V1"
)


def _historical_backfill_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return None


def _historical_backfill_outcome_summary(trade: Dict[str, Any]) -> Dict[str, Any]:
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("metadata") if isinstance(trade.get("metadata"), dict) else {}
    outcome = trade.get("outcome") if isinstance(trade.get("outcome"), dict) else {}

    def first(key: str) -> Any:
        for source in (trade, metadata, outcome):
            value = source.get(key)
            if value not in (None, ""):
                return value
        return None

    return {
        "outcome_status": first("outcome_status"),
        "outcome_source": first("outcome_source"),
        "outcome_id": first("outcome_id"),
        "exit_price": first("exit_price"),
        "data_quality": first("data_quality"),
        "financial_reconciliation_pending": first(
            "financial_reconciliation_pending"
        ),
    }


def _historical_backfill_request_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    strong_states = {
        field: strong_identity_alias_state(payload, field)
        for field in STRONG_IDENTITY_ALIASES
    }
    issues: List[str] = []
    alias_conflicts = []
    for field, state in strong_states.items():
        if state.get("conflict"):
            alias_conflicts.append(
                {
                    "field": field,
                    "normalized_values": list(
                        state.get("normalized_values") or []
                    ),
                    "aliases_present": list(state.get("aliases_present") or []),
                    "reason": "STRONG_IDENTITY_ALIAS_CONFLICT",
                }
            )
        elif not state.get("present"):
            issues.append(f"{field.upper()}_REQUIRED")

    def first(*keys: str) -> Any:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None

    weak = {
        "trade_id": str(first("trade_id") or "").strip(),
        "bot": str(first("bot") or "").upper().strip(),
        "setup": _normalize_identity_setup(first("setup")),
        "symbol": _normalize_symbol(first("symbol")),
        "side": _normalize_side(first("side")),
        "registry_mode": str(
            first("registry_mode", "expected_registry_mode") or ""
        ).upper().strip(),
        "execution_mode": str(
            first("execution_mode", "expected_execution_mode") or ""
        ).upper().strip(),
        "entry": _historical_backfill_float(
            first("entry", "entry_price", "factual_entry")
        ),
        "qty": _historical_backfill_float(
            first("qty", "quantity", "initial_qty", "factual_qty")
        ),
    }
    for field in (
        "trade_id",
        "bot",
        "setup",
        "symbol",
        "side",
        "registry_mode",
        "execution_mode",
    ):
        if not weak[field] or weak[field] == "UNKNOWN":
            issues.append(f"{field.upper()}_REQUIRED")
    if weak["entry"] is None:
        issues.append("ENTRY_REQUIRED")
    if weak["qty"] is None or weak["qty"] <= 0:
        issues.append("QTY_REQUIRED")
    if weak["registry_mode"] != "REAL":
        issues.append("REGISTRY_MODE_REAL_REQUIRED")
    if weak["execution_mode"] != "LIVE":
        issues.append("EXECUTION_MODE_LIVE_REQUIRED")
    return {
        "ok": not issues and not alias_conflicts,
        "weak_identity": weak,
        "proposed_identity": {
            field: state.get("value")
            for field, state in strong_states.items()
        },
        "strong_states": strong_states,
        "issues": list(dict.fromkeys(issues)),
        "alias_conflicts": alias_conflicts,
    }


def _historical_backfill_candidate_summary(
    index: int,
    trade: Dict[str, Any],
) -> Dict[str, Any]:
    strong_states = {
        field: strong_identity_alias_state(trade, field)
        for field in STRONG_IDENTITY_ALIASES
    }
    return {
        "registry_index": index,
        "trade_id": str(trade.get("trade_id") or "").strip() or None,
        "status": str(trade.get("status") or "").upper().strip() or None,
        "bot": str(trade.get("bot") or "").upper().strip() or None,
        "setup": trade.get("setup"),
        "setup_canonical": _normalize_identity_setup(trade.get("setup")),
        "symbol": _normalize_symbol(trade.get("symbol")),
        "side": _normalize_side(trade.get("side")),
        "registry_mode": str(trade.get("registry_mode") or "").upper().strip()
        or None,
        "execution_mode": str(trade.get("execution_mode") or "").upper().strip()
        or None,
        "entry": _historical_backfill_float(
            trade.get("entry")
            if trade.get("entry") not in (None, "")
            else trade.get("entry_price")
        ),
        "qty": _historical_backfill_float(
            trade.get("qty")
            if trade.get("qty") not in (None, "")
            else trade.get("initial_qty")
        ),
        "current_identity": {
            field: state.get("value")
            for field, state in strong_states.items()
        },
        "strong_identity_states": strong_states,
        "outcome": _historical_backfill_outcome_summary(trade),
    }


def _historical_backfill_evaluate(
    registry: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    request_state = _historical_backfill_request_state(payload)
    base = {
        "ok": True,
        "module": "historical_strong_identity_backfill_v1",
        "version": HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_VERSION,
        "read_only": True,
        "no_order_sent_by_this_route": True,
        "broker_called": False,
        "committed": False,
        "candidate_count": 0,
        "registry_index": None,
        "proposed_identity": request_state.get("proposed_identity") or {},
        "diagnostics": {
            "request_issues": request_state.get("issues") or [],
            "request_alias_conflicts": request_state.get("alias_conflicts")
            or [],
            "weak_identity": request_state.get("weak_identity") or {},
            "rejected_candidates": [],
            "identity_ownership_conflicts": [],
        },
    }
    if not request_state.get("ok"):
        return {
            **base,
            "ok": False,
            "status": (
                "STRONG_IDENTITY_ALIAS_CONFLICT"
                if request_state.get("alias_conflicts")
                else "HISTORICAL_STRONG_IDENTITY_BACKFILL_INVALID_REQUEST"
            ),
        }

    weak = request_state["weak_identity"]
    closed = registry.get("closed_trades", []) if isinstance(registry, dict) else []
    closed = closed if isinstance(closed, list) else []
    matching_indexes: List[int] = []
    rejected = []
    entry_tolerance = max(abs(weak["entry"]) * 1e-8, 1e-10)
    qty_tolerance = max(abs(weak["qty"]) * 1e-9, 1e-12)
    for index, trade in enumerate(closed):
        if not isinstance(trade, dict):
            continue
        reasons = []
        candidate_entry = _historical_backfill_float(
            trade.get("entry")
            if trade.get("entry") not in (None, "")
            else trade.get("entry_price")
        )
        candidate_qty = _historical_backfill_float(
            trade.get("qty")
            if trade.get("qty") not in (None, "")
            else trade.get("initial_qty")
        )
        comparisons = (
            (
                "TRADE_ID_MISMATCH",
                str(trade.get("trade_id") or "").strip() == weak["trade_id"],
            ),
            (
                "BOT_MISMATCH",
                str(trade.get("bot") or "").upper().strip() == weak["bot"],
            ),
            (
                "SETUP_MISMATCH",
                _normalize_identity_setup(trade.get("setup")) == weak["setup"],
            ),
            (
                "SYMBOL_MISMATCH",
                _normalize_symbol(trade.get("symbol")) == weak["symbol"],
            ),
            (
                "SIDE_MISMATCH",
                _normalize_side(trade.get("side")) == weak["side"],
            ),
            (
                "REGISTRY_MODE_NOT_REAL",
                str(trade.get("registry_mode") or "").upper().strip()
                == "REAL",
            ),
            (
                "EXECUTION_MODE_NOT_LIVE",
                str(trade.get("execution_mode") or "").upper().strip()
                == "LIVE",
            ),
            (
                "STATUS_NOT_CLOSED",
                str(trade.get("status") or "").upper().strip() == "CLOSED",
            ),
            (
                "ENTRY_DIVERGENCE",
                candidate_entry is not None
                and abs(candidate_entry - weak["entry"]) <= entry_tolerance,
            ),
            (
                "QTY_DIVERGENCE",
                candidate_qty is not None
                and abs(candidate_qty - weak["qty"]) <= qty_tolerance,
            ),
        )
        reasons.extend(reason for reason, matched in comparisons if not matched)
        if reasons:
            if str(trade.get("trade_id") or "").strip() == weak["trade_id"]:
                rejected.append(
                    {
                        "registry_index": index,
                        "registry_mode": str(
                            trade.get("registry_mode") or ""
                        ).upper().strip()
                        or None,
                        "execution_mode": str(
                            trade.get("execution_mode") or ""
                        ).upper().strip()
                        or None,
                        "reasons": reasons,
                    }
                )
            continue
        matching_indexes.append(index)

    base["candidate_count"] = len(matching_indexes)
    base["diagnostics"]["rejected_candidates"] = rejected[:50]
    base["diagnostics"]["entry_tolerance"] = entry_tolerance
    base["diagnostics"]["qty_tolerance"] = qty_tolerance
    if not matching_indexes:
        return {
            **base,
            "status": "HISTORICAL_STRONG_IDENTITY_BACKFILL_NOT_FOUND",
        }
    if len(matching_indexes) != 1:
        return {
            **base,
            "status": "HISTORICAL_STRONG_IDENTITY_BACKFILL_AMBIGUOUS",
        }

    index = matching_indexes[0]
    trade = closed[index]
    candidate = _historical_backfill_candidate_summary(index, trade)
    base["registry_index"] = index
    base["candidate"] = candidate
    base["current_identity"] = candidate["current_identity"]
    base["outcome"] = candidate["outcome"]
    proposed = request_state["proposed_identity"]
    current_states = candidate["strong_identity_states"]
    candidate_conflicts = [
        {
            "field": field,
            "normalized_values": list(state.get("normalized_values") or []),
            "aliases_present": list(state.get("aliases_present") or []),
            "reason": "STRONG_IDENTITY_ALIAS_CONFLICT",
        }
        for field, state in current_states.items()
        if state.get("conflict")
    ]
    mismatches = [
        {
            "field": field,
            "current": state.get("value"),
            "proposed": proposed.get(field),
            "reason": "STRONG_IDENTITY_ALIAS_CONFLICT",
        }
        for field, state in current_states.items()
        if state.get("present")
        and not state.get("conflict")
        and state.get("value") != proposed.get(field)
    ]
    if candidate_conflicts or mismatches:
        base["diagnostics"]["candidate_alias_conflicts"] = candidate_conflicts
        base["diagnostics"]["candidate_identity_mismatches"] = mismatches
        return {**base, "status": "STRONG_IDENTITY_ALIAS_CONFLICT"}

    ownership_conflicts = []
    open_trades = registry.get("open_trades", {}) if isinstance(registry, dict) else {}
    records = []
    if isinstance(open_trades, dict):
        records.extend(
            ("open_trades", key, value)
            for key, value in open_trades.items()
            if isinstance(value, dict)
        )
    records.extend(
        ("closed_trades", other_index, value)
        for other_index, value in enumerate(closed)
        if isinstance(value, dict) and other_index != index
    )
    for source, record_key, other in records:
        for field, expected in proposed.items():
            state = strong_identity_alias_state(other, field)
            if expected not in (state.get("normalized_values") or []):
                continue
            ownership_conflicts.append(
                {
                    "source": source,
                    "registry_key": record_key,
                    "field": field,
                    "registry_mode": str(
                        other.get("registry_mode") or ""
                    ).upper().strip()
                    or None,
                    "has_manual_outcome": bool(
                        str(
                            _historical_backfill_outcome_summary(other).get(
                                "outcome_source"
                            )
                            or ""
                        ).upper()
                        == "MANUAL_CLOSE_RECONCILIATION"
                    ),
                    "reason": "STRONG_IDENTITY_ALREADY_ASSIGNED",
                }
            )
    if ownership_conflicts:
        base["diagnostics"][
            "identity_ownership_conflicts"
        ] = ownership_conflicts
        return {**base, "status": "STRONG_IDENTITY_ALIAS_CONFLICT"}

    already_backfilled = all(
        current_states[field].get("present")
        and current_states[field].get("value") == proposed[field]
        for field in STRONG_IDENTITY_ALIASES
    )
    return {
        **base,
        "status": (
            "ALREADY_BACKFILLED"
            if already_backfilled
            else "HISTORICAL_STRONG_IDENTITY_BACKFILL_READY"
        ),
        "safe_to_commit": True,
        "already_backfilled": already_backfilled,
    }


def preview_historical_strong_identity_backfill(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Read-only preview for one historical CLOSED Registry record."""
    try:
        registry = load_registry_read_only()
        return _historical_backfill_evaluate(registry, payload)
    except Exception:
        return {
            "ok": False,
            "module": "historical_strong_identity_backfill_v1",
            "version": HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_VERSION,
            "status": "TRADE_REGISTRY_READ_ERROR",
            "read_only": True,
            "no_order_sent_by_this_route": True,
            "broker_called": False,
            "committed": False,
        }


def backfill_historical_strong_identity(
    payload: Dict[str, Any],
    *,
    ack: Any = None,
) -> Dict[str, Any]:
    """Atomically backfill strong aliases without changing trade economics."""
    if str(ack or "").strip() != HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_ACK:
        return {
            "ok": False,
            "module": "historical_strong_identity_backfill_v1",
            "version": HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_VERSION,
            "status": "ACK_REQUIRED",
            "required_ack": HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_ACK,
            "no_order_sent_by_this_route": True,
            "broker_called": False,
            "committed": False,
        }
    with _lock:
        registry = load_registry()
        evaluated = _historical_backfill_evaluate(registry, payload)
        if evaluated.get("status") == "ALREADY_BACKFILLED":
            return {**evaluated, "read_only": False, "committed": False}
        if (
            evaluated.get("status")
            != "HISTORICAL_STRONG_IDENTITY_BACKFILL_READY"
            or not evaluated.get("safe_to_commit")
        ):
            return {**evaluated, "read_only": False, "committed": False}

        index = evaluated["registry_index"]
        proposed = evaluated["proposed_identity"]
        closed = registry.get("closed_trades", [])
        trade = dict(closed[index])
        before_financial = {
            key: copy.deepcopy(trade.get(key))
            for key in (
                "trade_id",
                "entry",
                "entry_price",
                "qty",
                "initial_qty",
                "exit",
                "exit_price",
                "outcome",
                "pnl",
                "pnl_pct",
                "pnl_r",
                "status",
                "closed_at",
                "close_timestamp",
            )
        }
        trade.update(
            {
                "lifecycle_id": proposed["lifecycle_id"],
                "client_order_id": proposed["client_order_id"],
                "broker_order_id": proposed["order_id"],
                "order_id": proposed["order_id"],
                "open_order_id": proposed["order_id"],
                "registry_mode": "REAL",
                "execution_mode": "LIVE",
            }
        )
        metadata = dict(trade.get("metadata") or {})
        metadata["historical_strong_identity_backfill_v1"] = {
            "version": HISTORICAL_STRONG_IDENTITY_BACKFILL_V1_VERSION,
            "applied_at": _now(),
            "source": "REAL_CLOSE_RECONCILIATION_ADMINISTRATIVE_BACKFILL",
            "registry_index": index,
            "proposed_identity": copy.deepcopy(proposed),
        }
        trade["metadata"] = metadata
        after_financial = {
            key: copy.deepcopy(trade.get(key))
            for key in before_financial
        }
        if before_financial != after_financial:
            return {
                **evaluated,
                "ok": False,
                "status": "FINANCIAL_FIELDS_CHANGED_DURING_BACKFILL",
                "read_only": False,
                "committed": False,
            }
        closed[index] = trade
        registry["closed_trades"] = closed
        if save_registry(registry) is False:
            return {
                **evaluated,
                "ok": False,
                "status": "TRADE_REGISTRY_SAVE_FAILED",
                "read_only": False,
                "committed": False,
            }
        result = _historical_backfill_evaluate(registry, payload)
        return {
            **result,
            "status": "HISTORICAL_STRONG_IDENTITY_BACKFILLED",
            "read_only": False,
            "committed": True,
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
        if save_registry(registry) is False:
            return {
                "ok": False,
                "error": "TRADE_REGISTRY_SAVE_FAILED",
                "trade_id": trade_id,
                "outcome_id": trade.get("outcome_id"),
            }

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
            or (
                strong_state is None
                and (
                    len(current_values) != 1
                    or current_values[0] != normalized_expected
                )
            )
            or (
                strong_state is not None
                and current_value != normalized_expected
            )
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
            existing = get_closed_trade(
                trade_id=trade_id,
                expected_identity=expected_identity,
            )
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
                # A CLOSED record is immutable through close_trade().  Reusing a
                # deterministic trade_id for a later execution must never
                # rewrite the older outcome merely because the new OPEN record
                # is absent.  Explicit administrative reconciliation uses
                # update_closed_trade() with strong expected_identity.
                return {
                    "ok": True,
                    "action": "TRADE_ALREADY_CLOSED",
                    "trade_id": trade_id,
                    "trade": existing.get("trade"),
                }
            if existing.get("error") not in (
                None,
                "",
                "CLOSED_TRADE_NOT_FOUND",
            ):
                return existing
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
    write_result = save_registry(registry)
    if write_result is False:
        return {"ok": False, "error": "TRADE_REGISTRY_RESET_NOT_PERSISTED"}
    return {"ok": True, "action": "TRADE_REGISTRY_RESET"}
