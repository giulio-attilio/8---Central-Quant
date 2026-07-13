"""Persistent Smart Predator PAPER event log and daily summary helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from history_memory_guard import AUTOMATIC_MAX_BYTES, AUTOMATIC_MAX_RECORDS, iter_jsonl_tail


VERSION = "2026-07-12-PREDATOR-DAILY-SUMMARY-FROM-EVENT-LOG-V1"
_lock = threading.RLock()
_state = {"last_run": None, "last_error": None, "events_count_today": 0, "closed_count_today": 0, "warning_count": 0}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_log_path() -> Path:
    base = Path(os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR") or (Path(__file__).resolve().parent / "data"))
    return base / "predator_paper_events.jsonl"


def history_event_log_path() -> Path:
    return event_log_path().parent / "history_events.jsonl"


def _safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _event_key(event: Dict[str, Any]) -> str:
    material = {
        key: event.get(key)
        for key in ("event", "date", "datetime", "symbol", "symbol_clean", "side", "entry", "exit", "price", "new_sl", "pnl_pct", "pnl_r")
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def append_predator_event(event: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(event, dict):
        raise TypeError("event must be a dict")
    row = copy.deepcopy(event)
    row.setdefault("schema_version", 1)
    row.setdefault("source", "SMART_PREDATOR")
    row.setdefault("execution_mode", "PAPER")
    row.setdefault("recorded_at", _now())
    row["event_key"] = _event_key(row)
    path = event_log_path()
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(_safe(row), ensure_ascii=False) + "\n")
        return {"ok": True, "status": "APPENDED", "path": str(path), "event_key": row["event_key"]}
    except OSError as exc:
        _state["last_error"] = str(exc)
        return {"ok": False, "status": "WRITE_ERROR", "path": str(path), "error": str(exc)}


def read_predator_event_log() -> Dict[str, Any]:
    path = event_log_path()
    events: List[Dict[str, Any]] = []
    invalid = 0
    warnings: List[str] = []
    source_pages: List[Dict[str, Any]] = []

    def read_rows(source_path: Path, central_history: bool = False) -> None:
        nonlocal invalid
        if not source_path.exists():
            warnings.append(f"Fonte persistente não existe: {source_path}")
            return
        page = iter_jsonl_tail(
            source_path,
            max_records=AUTOMATIC_MAX_RECORDS,
            max_bytes=AUTOMATIC_MAX_BYTES,
            operation=(
                "predator_daily_summary.history_events"
                if central_history else "predator_daily_summary.predator_events"
            ),
        )
        source_pages.append(page)
        if page["partial"]:
            warnings.append(
                f"Fonte {source_path.name} limitada à cauda; métricas do período são parciais."
            )
        invalid += int(page.get("invalid_lines") or 0)
        for row in page["records"]:
            try:
                if isinstance(row, dict):
                    if central_history:
                        source = str(row.get("source") or "").upper()
                        bot = str(row.get("bot") or (row.get("raw") or {}).get("bot") or "").upper()
                        if "PREDATOR" not in source and bot not in {"PREDATOR", "SMART_PREDATOR", "SMARTPREDATOR"}:
                            continue
                        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
                        normalized = copy.deepcopy(raw)
                        for key in ("event", "symbol", "side", "score", "entry", "exit_price", "result_pct", "result_r", "reason", "ts", "epoch"):
                            if normalized.get(key) is None and row.get(key) is not None:
                                normalized[key] = row.get(key)
                        event_name = str(normalized.get("event") or row.get("event_raw") or row.get("event") or "").upper()
                        if event_name == "SIGNAL_CREATED":
                            event_name = "ENTRY"
                        elif event_name == "TRADE_CLOSED":
                            event_name = str(normalized.get("reason") or "CLOSE").upper()
                        normalized["event"] = event_name
                        normalized.setdefault("pnl_pct", normalized.get("result_pct"))
                        normalized.setdefault("pnl_r", normalized.get("result_r"))
                        normalized.setdefault("exit", normalized.get("exit_price"))
                        if not normalized.get("date"):
                            ts = str(normalized.get("ts") or "")
                            try:
                                normalized["date"] = datetime.strptime(ts[:10], "%d/%m/%Y").strftime("%Y-%m-%d")
                            except ValueError:
                                normalized["date"] = ts[:10]
                        normalized["persistent_source"] = "CENTRAL_HISTORY_EVENTS"
                        events.append(normalized)
                    else:
                        events.append(row)
            except (TypeError, ValueError, json.JSONDecodeError):
                invalid += 1

    try:
        read_rows(path)
        read_rows(history_event_log_path(), central_history=True)
    except OSError as exc:
        _state["last_error"] = str(exc)
        return {"ok": False, "status": "EVENT_LOG_READ_ERROR", "events": [], "invalid_lines": 0, "warnings": [str(exc)], "path": str(path)}
    if invalid:
        warnings.append(f"Event logs contêm {invalid} linha(s) inválida(s).")
    ok = path.exists() or history_event_log_path().exists()
    partial = any(bool(page.get("partial")) for page in source_pages)
    return {
        "ok": ok,
        "status": "LOADED" if ok else "EVENT_LOG_MISSING",
        "events": events,
        "invalid_lines": invalid,
        "warnings": warnings,
        "path": str(path),
        "history_path": str(history_event_log_path()),
        "partial": partial,
        "coverage_complete": not partial,
        "records_examined": sum(int(page.get("records_examined") or 0) for page in source_pages),
        "bytes_read": sum(int(page.get("bytes_read") or 0) for page in source_pages),
        "max_records": AUTOMATIC_MAX_RECORDS,
        "max_bytes": AUTOMATIC_MAX_BYTES,
        "source_size_bytes": sum(int(page.get("source_size_bytes") or 0) for page in source_pages),
    }


def load_events_for_period(date_prefix: str, memory_events: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not isinstance(date_prefix, str):
        raise TypeError("date_prefix must be a string")
    log = read_predator_event_log()
    log_rows = [row for row in log.get("events", []) if str(row.get("date") or "").startswith(date_prefix)]
    memory_rows = [copy.deepcopy(row) for row in (memory_events or []) if isinstance(row, dict) and str(row.get("date") or "").startswith(date_prefix)]
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in log_rows + memory_rows:
        by_key.setdefault(str(row.get("event_key") or _event_key(row)), row)
    warnings = list(log.get("warnings") or [])
    memory_only = max(0, len({_event_key(x) for x in memory_rows}) - len({_event_key(x) for x in log_rows} & {_event_key(x) for x in memory_rows}))
    if memory_only:
        warnings.append(f"Há {memory_only} evento(s) do período apenas na memória/Redis; event log pode estar incompleto.")
    if not by_key:
        warnings.append("Nenhum evento persistente do Predator foi encontrado para o período; resumo não é conclusivo.")
    return {
        "ok": bool(log.get("ok")),
        "source": "PREDATOR_EVENT_LOG_AND_CENTRAL_HISTORY_WITH_MEMORY_FALLBACK",
        "events": list(by_key.values()),
        "events_count": len(by_key),
        "log_events_count": len(log_rows),
        "memory_events_count": len(memory_rows),
        "warnings": warnings,
        "warning_count": len(warnings),
        "path": log.get("path"),
        **{key: log.get(key) for key in (
            "partial", "coverage_complete", "records_examined", "bytes_read",
            "max_records", "max_bytes", "source_size_bytes",
        )},
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def build_daily_metrics(date_prefix: str, memory_events: Optional[Iterable[Dict[str, Any]]] = None, active_count: int = 0, registry_closed_count: Optional[int] = None) -> Dict[str, Any]:
    global _state
    loaded = load_events_for_period(date_prefix, memory_events)
    rows = loaded["events"]
    entries = [x for x in rows if str(x.get("event") or "").upper() in {"ENTRY", "SIGNAL", "SIGNAL_CREATED"}]
    closes = [x for x in rows if str(x.get("event") or "").upper() in {"SL", "TRAIL", "BE", "CLOSE", "TRADE_CLOSED"}]
    tp50 = [x for x in rows if str(x.get("event") or "").upper() == "TP50"]
    trailing = [x for x in rows if str(x.get("event") or "").upper() == "TRAILING"]
    pnl_values = [_float(x.get("pnl_pct", x.get("pnl", x.get("result_pct")))) for x in closes]
    r_values = [_float(x.get("pnl_r", x.get("result_r"))) for x in closes]
    warnings = list(loaded["warnings"])
    if registry_closed_count is not None and int(registry_closed_count) != len(closes):
        warnings.append(f"Divergência event log x Registry: fechados no período={len(closes)}, Registry informado={registry_closed_count}.")
    result = {
        **loaded,
        "signals_h1": len(entries),
        "long": sum(1 for x in entries if str(x.get("side") or "").upper() == "LONG"),
        "short": sum(1 for x in entries if str(x.get("side") or "").upper() == "SHORT"),
        "score_95_plus": sum(1 for x in entries if _float(x.get("score")) >= 95),
        "score_90_94": sum(1 for x in entries if 90 <= _float(x.get("score")) < 95),
        "score_85_89": sum(1 for x in entries if 85 <= _float(x.get("score")) < 90),
        "score_80_84": sum(1 for x in entries if 80 <= _float(x.get("score")) < 85),
        "score_70_79": sum(1 for x in entries if 70 <= _float(x.get("score")) < 80),
        "tp50_hits": len(tp50),
        "be_activated": len(tp50),
        "trailing_updates": len(trailing),
        "trail_exits": sum(1 for x in closes if str(x.get("event") or "").upper() == "TRAIL"),
        "sl_exits": sum(1 for x in closes if str(x.get("event") or "").upper() == "SL"),
        "closed": len(closes),
        "wins": sum(1 for x in pnl_values if x > 0.15),
        "breakeven": sum(1 for x in pnl_values if -0.15 <= x <= 0.15),
        "losses": sum(1 for x in pnl_values if x < -0.15),
        "pnl_pct": sum(pnl_values),
        "realized_r": sum(r_values),
        "mfe_avg_pct": sum(_float(x.get("mfe_max_pct")) for x in closes) / len(closes) if closes else 0.0,
        "mae_avg_pct": sum(_float(x.get("mae_min_pct")) for x in closes) / len(closes) if closes else 0.0,
        "giveback_avg_pct": sum(_float(x.get("mfe_gave_back_pct")) for x in closes) / len(closes) if closes else 0.0,
        "active": int(active_count or 0),
        "warnings": warnings,
        "warning_count": len(warnings),
    }
    _state = {"last_run": _now(), "last_error": None if loaded.get("ok") else "; ".join(warnings), "events_count_today": len(rows), "closed_count_today": len(closes), "warning_count": len(warnings)}
    return result


def daily_summary_health() -> Dict[str, Any]:
    return {
        "predator_daily_summary_source": "PREDATOR_EVENT_LOG_AND_CENTRAL_HISTORY_WITH_MEMORY_FALLBACK",
        "predator_daily_summary_from_event_log_enabled": True,
        "predator_daily_summary_last_run": _state.get("last_run"),
        "predator_daily_summary_last_error": _state.get("last_error"),
        "predator_daily_summary_events_count_today": _state.get("events_count_today", 0),
        "predator_daily_summary_closed_count_today": _state.get("closed_count_today", 0),
        "predator_daily_summary_warning_count": _state.get("warning_count", 0),
        "predator_daily_summary_event_log": str(event_log_path()),
    }
