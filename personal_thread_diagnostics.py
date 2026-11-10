"""Bounded, value-free diagnostics for the personal service's Python threads."""

from __future__ import annotations

import re
import sys
import threading


_MAX_THREADS = 64
_MAX_FRAMES_PER_THREAD = 24
_SAFE_NAME = re.compile(r"[^A-Za-z0-9 _().:-]")


def _safe_thread_name(value: object) -> str:
    return _SAFE_NAME.sub("?", str(value or ""))[:80]


def _safe_basename(value: object) -> str:
    # Normalize both POSIX and Windows separators without returning a path.
    return str(value or "").replace("\\", "/").rsplit("/", 1)[-1][:120]


def collect_thread_diagnostics() -> dict:
    """Return bounded frame locations only; never inspect or serialize locals."""
    try:
        current_frames = sys._current_frames()
        threads = threading.enumerate()
    except Exception:
        return {
            "ok": False,
            "status": "THREAD_SNAPSHOT_UNAVAILABLE",
            "thread_count": 0,
            "threads_truncated": False,
            "threads": [],
        }

    thread_count = len(threads)
    rows = []
    for thread in threads[:_MAX_THREADS]:
        frame = current_frames.get(thread.ident)
        frames = []
        while frame is not None and len(frames) < _MAX_FRAMES_PER_THREAD:
            code = frame.f_code
            frames.append(
                {
                    "file": _safe_basename(code.co_filename),
                    "function": str(code.co_name)[:120],
                    "line": int(frame.f_lineno),
                }
            )
            frame = frame.f_back
        frames.reverse()
        rows.append(
            {
                "name": _safe_thread_name(thread.name),
                "ident": thread.ident,
                "native_id": getattr(thread, "native_id", None),
                "daemon": bool(thread.daemon),
                "alive": bool(thread.is_alive()),
                "stack_available": bool(frames),
                "stack_truncated": frame is not None,
                "frames": frames,
            }
        )

    return {
        "ok": True,
        "status": "THREAD_DIAGNOSTIC_ONLY",
        "thread_count": thread_count,
        "threads_truncated": thread_count > _MAX_THREADS,
        "threads": rows,
    }
