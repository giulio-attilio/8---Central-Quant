"""Fail-open, opt-in observability for decision_log.jsonl writes."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path


_ENABLED_ENV = "CENTRAL_DECISION_LOG_WRITE_FORENSICS_ENABLED"


def _enabled() -> bool:
    return str(os.environ.get(_ENABLED_ENV) or "").strip().lower() in {
        "1", "true", "yes", "sim", "on"
    }


def _safe_log(message: str) -> None:
    try:
        print(message)
    except Exception:
        pass


def _file_size(path) -> int | None:
    try:
        return int(Path(path).stat().st_size)
    except OSError:
        return None


def _request_context() -> tuple[object, object]:
    try:
        flask_module = sys.modules.get("flask")
        has_request_context = getattr(flask_module, "has_request_context", None)
        request = getattr(flask_module, "request", None)
        if callable(has_request_context) and has_request_context() and request is not None:
            return request.endpoint, request.path
    except Exception:
        pass
    return None, None


def _reduced_stack(writer: str) -> tuple[object, list[str]]:
    labels = []
    try:
        frame = sys._getframe(1)
        while frame is not None and len(labels) < 8:
            module_name = str(frame.f_globals.get("__name__") or "UNKNOWN")
            if module_name != __name__:
                labels.append(f"{module_name}.{frame.f_code.co_name}")
            frame = frame.f_back
    except Exception:
        pass
    caller = labels[0] if labels else None
    if writer in labels:
        position = labels.index(writer)
        caller = labels[position + 1] if len(labels) > position + 1 else None
    return caller, labels


def _item_metadata(item) -> dict:
    record = item if isinstance(item, dict) else {}
    return {
        "bot": record.get("bot"),
        "event_type": record.get("event") or record.get("event_type") or record.get("decision"),
        "decision_id": record.get("decision_id") or record.get("trade_id") or record.get("uid"),
        "duplicate_key": record.get("duplicate_key"),
    }


class _DecisionLogWriteProbe:
    def __init__(self, path, item, *, writer: str, serialized_bytes: int | None = None):
        self.path = Path(path)
        self.writer = str(writer)
        self.serialized_bytes = serialized_bytes
        self.metadata = _item_metadata(item)
        self.active = _enabled() and self.path.name.lower() == "decision_log.jsonl"
        self.started = None
        self.file_size_before = None
        self.route_endpoint = None
        self.route_path = None
        self.caller = None
        self.stack = []

    def begin(self) -> None:
        if not self.active:
            return
        try:
            self.started = time.perf_counter()
            self.file_size_before = _file_size(self.path)
            self.route_endpoint, self.route_path = _request_context()
            self.caller, self.stack = _reduced_stack(self.writer)
        except Exception:
            self.active = False

    def finish(self, write_success: bool) -> None:
        if not self.active:
            return
        try:
            duration_ms = None
            if self.started is not None:
                duration_ms = round((time.perf_counter() - self.started) * 1000, 3)
            event = {
                "timestamp": round(time.time(), 3),
                "operation": "DECISION_LOG_APPEND",
                "writer": self.writer,
                "caller": self.caller,
                "stack": self.stack,
                "thread": threading.current_thread().name,
                "route_endpoint": self.route_endpoint,
                "route_path": self.route_path,
                **self.metadata,
                "serialized_bytes": self.serialized_bytes,
                "file_size_before": self.file_size_before,
                "file_size_after": _file_size(self.path),
                "duplicate_detected": None,
                "write_success": bool(write_success),
                "duration_ms": duration_ms,
            }
            _safe_log("DECISION_LOG_WRITE_FORENSICS " + json.dumps(event, ensure_ascii=True, default=str))
        except Exception:
            pass


def decision_log_write_probe(path, item, *, writer: str, serialized_bytes: int | None = None):
    """Return a no-op-safe probe; callers must never depend on it for writes."""
    return _DecisionLogWriteProbe(
        path, item, writer=writer, serialized_bytes=serialized_bytes
    )
