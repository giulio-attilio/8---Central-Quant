"""Observabilidade de memoria, sem autoridade operacional, para o Predator Audit.

O modulo nao importa componentes da Central, nao cria threads e nao persiste dados.
Toda falha de medicao/log e deliberadamente fail-open.
"""

from __future__ import annotations

import ctypes
import functools
import itertools
import json
import os
import sys
import threading
import time
import traceback
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path


_LOCK = threading.RLock()
_LOCAL = threading.local()
_ACTIVE = {}
_RECENT_STARTS = OrderedDict()
_RUN_SEQUENCE = 0
_RECENT_LIMIT = 64
_DUPLICATE_WINDOW_SECONDS = 60.0


def _enabled():
    value = os.environ.get("PREDATOR_AUDIT_MEMORY_OBSERVABILITY_ENABLED", "true")
    return str(value).strip().lower() not in {"0", "false", "no", "nao", "não", "off"}


def _round_mb(value):
    try:
        return round(float(value), 3)
    except Exception:
        return None


def current_rss_mb():
    """Retorna RSS corrente (nao apenas pico), quando suportado pelo host."""
    try:
        statm = Path("/proc/self/statm")
        if statm.exists():
            fields = statm.read_text(encoding="ascii").split()
            if len(fields) >= 2:
                return _round_mb(int(fields[1]) * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024))
    except Exception:
        pass

    try:
        if os.name == "nt":
            class _ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = _ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            process = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                process, ctypes.byref(counters), counters.cb
            )
            if ok:
                return _round_mb(counters.WorkingSetSize / (1024 * 1024))
    except Exception:
        pass

    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            value /= 1024.0
        return _round_mb(value / 1024.0)
    except Exception:
        return None


def _safe_field(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, (list, tuple)):
        return [_safe_field(item) for item in value[:12]]
    if isinstance(value, dict):
        return {
            str(key)[:80]: _safe_field(item)
            for key, item in itertools.islice(value.items(), 20)
        }
    return str(type(value).__name__)


def _emit(event, **fields):
    if not _enabled():
        return
    try:
        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        payload.update({key: _safe_field(value) for key, value in fields.items()})
        print(f"{event} {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}", flush=True)
    except Exception:
        pass


def _stack_summary(limit=8):
    try:
        frames = traceback.extract_stack(limit=limit + 6)
        selected = []
        for frame in frames[:-2]:
            if Path(frame.filename).name == Path(__file__).name:
                continue
            selected.append(f"{Path(frame.filename).name}:{frame.name}:{frame.lineno}")
        return selected[-limit:]
    except Exception:
        return []


def estimate_object(value, max_nodes=1500, max_items=80):
    """Estimativa limitada; nao retém referencias depois do retorno."""
    result = {
        "type": type(value).__name__,
        "count": None,
        "shallow_bytes": 0,
        "estimated_bytes": 0,
        "nodes_examined": 0,
        "partial": False,
    }
    try:
        result["count"] = len(value) if hasattr(value, "__len__") else None
    except Exception:
        pass
    try:
        result["shallow_bytes"] = int(sys.getsizeof(value))
    except Exception:
        pass

    try:
        memory_usage = getattr(value, "memory_usage", None)
        if callable(memory_usage) and type(value).__name__ in {"DataFrame", "Series"}:
            usage = memory_usage(index=True, deep=True)
            total = int(usage.sum()) if hasattr(usage, "sum") else int(usage)
            result["estimated_bytes"] = total
            result["shape"] = list(getattr(value, "shape", ()))[:2]
            result["nodes_examined"] = 1
            return result
    except Exception:
        pass

    seen = set()
    queue = deque([value])
    total = 0
    examined = 0
    truncated = False
    try:
        while queue and examined < max(1, int(max_nodes)):
            current = queue.popleft()
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            examined += 1
            try:
                total += sys.getsizeof(current)
            except Exception:
                pass
            children = []
            if isinstance(current, dict):
                if len(current) > max_items:
                    truncated = True
                for key, item in itertools.islice(current.items(), max_items):
                    children.extend((key, item))
            elif isinstance(current, (list, tuple, set, frozenset, deque)):
                if len(current) > max_items:
                    truncated = True
                children.extend(itertools.islice(current, max_items))
            queue.extend(children)
        result["estimated_bytes"] = int(total)
        result["nodes_examined"] = examined
        result["partial"] = bool(queue) or truncated
    except Exception:
        result["estimated_bytes"] = int(total)
        result["nodes_examined"] = examined
        result["partial"] = True
    return result


class _AuditProbe:
    def __init__(self, audit, metadata=None):
        self.audit = str(audit)
        self.metadata = metadata or {}
        self.run_id = None
        self.rss_before = None
        self.started = None
        self.active_registered = False

    def __enter__(self):
        global _RUN_SEQUENCE
        if not _enabled():
            return self
        self.started = time.perf_counter()
        self.rss_before = current_rss_mb()
        now = time.monotonic()
        try:
            with _LOCK:
                _RUN_SEQUENCE += 1
                self.run_id = f"{self.audit}:{_RUN_SEQUENCE}"
                active_before = int(_ACTIVE.get(self.audit, 0))
                _ACTIVE[self.audit] = active_before + 1
                self.active_registered = True
                previous = _RECENT_STARTS.get(self.audit)
                _RECENT_STARTS[self.audit] = now
                _RECENT_STARTS.move_to_end(self.audit)
                while len(_RECENT_STARTS) > _RECENT_LIMIT:
                    _RECENT_STARTS.popitem(last=False)
            local_stack = getattr(_LOCAL, "stack", None)
            if local_stack is None:
                local_stack = []
                _LOCAL.stack = local_stack
            local_stack.append((self.audit, self.run_id))
            duplicate_ms = None if previous is None else round((now - previous) * 1000.0, 3)
            stack = _stack_summary()
            _emit(
                "PREDATOR_AUDIT_BEGIN",
                audit=self.audit,
                run_id=self.run_id,
                rss_mb=self.rss_before,
                caller=stack[-1] if stack else None,
                thread=threading.current_thread().name,
                thread_ident=threading.get_ident(),
                stack=stack,
                active_before=active_before,
                reentrant=active_before > 0,
                duplicate_within_window=duplicate_ms is not None
                and duplicate_ms <= _DUPLICATE_WINDOW_SECONDS * 1000.0,
                milliseconds_since_previous_start=duplicate_ms,
                metadata=self.metadata,
            )
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc, tb):
        if not _enabled():
            return False
        rss_after = current_rss_mb()
        duration_ms = None
        if self.started is not None:
            duration_ms = round((time.perf_counter() - self.started) * 1000.0, 3)
        delta = None
        if rss_after is not None and self.rss_before is not None:
            delta = _round_mb(rss_after - self.rss_before)
        try:
            if exc is not None:
                _emit(
                    "PREDATOR_AUDIT_ERROR",
                    audit=self.audit,
                    run_id=self.run_id,
                    error_type=type(exc).__name__,
                    error=str(exc)[:240],
                )
            _emit(
                "PREDATOR_AUDIT_END",
                audit=self.audit,
                run_id=self.run_id,
                rss_before_mb=self.rss_before,
                rss_after_mb=rss_after,
                delta_mb=delta,
                duration_ms=duration_ms,
                rss_returned_to_start=delta is not None and delta <= 0.5,
            )
        finally:
            try:
                local_stack = getattr(_LOCAL, "stack", [])
                if local_stack and local_stack[-1] == (self.audit, self.run_id):
                    local_stack.pop()
                else:
                    local_stack[:] = [item for item in local_stack if item != (self.audit, self.run_id)]
            except Exception:
                pass
            if self.active_registered:
                try:
                    with _LOCK:
                        remaining = max(0, int(_ACTIVE.get(self.audit, 1)) - 1)
                        if remaining:
                            _ACTIVE[self.audit] = remaining
                        else:
                            _ACTIVE.pop(self.audit, None)
                except Exception:
                    pass
        return False


class _AuditStage:
    def __init__(self, audit, stage, records_in=None, metadata=None):
        self.audit = str(audit)
        self.stage = str(stage)
        self.records_in = records_in
        self.metadata = metadata or {}
        self.rss_before = None
        self.started = None
        self.finished_fields = {}
        self.run_id = None

    def __enter__(self):
        if not _enabled():
            return self
        self.started = time.perf_counter()
        self.rss_before = current_rss_mb()
        try:
            for audit_name, run_id in reversed(getattr(_LOCAL, "stack", [])):
                if audit_name == self.audit:
                    self.run_id = run_id
                    break
        except Exception:
            self.run_id = None
        _emit(
            "PREDATOR_AUDIT_STAGE_BEGIN",
            audit=self.audit,
            run_id=self.run_id,
            stage=self.stage,
            rss_mb=self.rss_before,
            records_in=self.records_in,
            thread=threading.current_thread().name,
            metadata=self.metadata,
        )
        return self

    def finish(self, value=None, records_processed=None, objects_produced=None, **fields):
        try:
            if value is not None:
                fields["object"] = estimate_object(value)
            if records_processed is not None:
                fields["records_processed"] = records_processed
            if objects_produced is not None:
                fields["objects_produced"] = objects_produced
            self.finished_fields.update(fields)
        except Exception:
            pass
        return value

    def __exit__(self, exc_type, exc, tb):
        if not _enabled():
            return False
        rss_after = current_rss_mb()
        delta = None
        if rss_after is not None and self.rss_before is not None:
            delta = _round_mb(rss_after - self.rss_before)
        duration_ms = None
        if self.started is not None:
            duration_ms = round((time.perf_counter() - self.started) * 1000.0, 3)
        fields = dict(self.finished_fields)
        if exc is not None:
            fields.update(error_type=type(exc).__name__, error=str(exc)[:240])
        _emit(
            "PREDATOR_AUDIT_STAGE_END",
            audit=self.audit,
            run_id=self.run_id,
            stage=self.stage,
            rss_before_mb=self.rss_before,
            rss_after_mb=rss_after,
            delta_mb=delta,
            duration_ms=duration_ms,
            **fields,
        )
        return False


def predator_audit_probe(audit, **metadata):
    return _AuditProbe(audit, metadata=metadata)


def predator_audit_stage(audit, stage, records_in=None, **metadata):
    return _AuditStage(audit, stage, records_in=records_in, metadata=metadata)


def observe_predator_audit(audit):
    """Decorator exclusivamente observacional; preserva assinatura introspectiva."""
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            metadata = {
                "include_samples": kwargs.get("include_samples"),
                "limit": kwargs.get("limit"),
                "use_cache": kwargs.get("use_cache"),
            }
            with predator_audit_probe(audit, **metadata):
                return function(*args, **kwargs)
        return wrapped
    return decorate


__all__ = [
    "current_rss_mb",
    "estimate_object",
    "observe_predator_audit",
    "predator_audit_probe",
    "predator_audit_stage",
]
