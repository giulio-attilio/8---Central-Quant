"""Bounded, read-only helpers for large historical JSONL files."""

from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path


MIB = 1024 * 1024
AUTOMATIC_MAX_RECORDS = 2_000
AUTOMATIC_MAX_BYTES = 16 * MIB
LIGHT_MAX_RECORDS = 200
LIGHT_MAX_BYTES = 2 * MIB
ABSOLUTE_MAX_RECORDS = 10_000
ABSOLUTE_MAX_BYTES = 64 * MIB
READ_BLOCK_BYTES = 64 * 1024


def _rss_mb():
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if value > 10_000_000:  # macOS reports bytes; Linux reports KiB.
            return round(value / (1024 * 1024), 3)
        return round(value / 1024, 3)
    except Exception:
        return None


def _safe_log(message):
    try:
        print(message)
    except Exception:
        pass


class _HistoryMemoryProbe:
    def __init__(self, operation, path=None):
        self.operation = str(operation or "history_read")
        self.path = Path(path) if path is not None else None
        self.started = None
        self.rss_before = None
        self.records = 0
        self.partial = None

    def __enter__(self):
        self.started = time.perf_counter()
        self.rss_before = _rss_mb()
        size_mb = None
        try:
            size_mb = round(self.path.lstat().st_size / MIB, 3) if self.path else None
        except OSError:
            pass
        _safe_log(
            "HISTORY_MEMORY_BEGIN"
            f" operation={self.operation} rss_mb={self.rss_before}"
            f" file_size_mb={size_mb} thread={threading.current_thread().name}"
        )
        return self

    def finish(self, records=0, partial=None):
        self.records = int(records or 0)
        self.partial = partial

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            _safe_log(
                "HISTORY_MEMORY_ERROR"
                f" operation={self.operation} exception_type={exception_type.__name__}"
            )
            return False
        rss_after = _rss_mb()
        delta = None
        if rss_after is not None and self.rss_before is not None:
            delta = round(rss_after - self.rss_before, 3)
        duration_ms = round((time.perf_counter() - self.started) * 1000, 3)
        _safe_log(
            "HISTORY_MEMORY_END"
            f" operation={self.operation} rss_mb={rss_after} delta_mb={delta}"
            f" records={self.records} partial={self.partial} duration_ms={duration_ms}"
        )
        return False


def history_memory_probe(operation, path=None):
    return _HistoryMemoryProbe(operation, path=path)


def validate_history_limits(max_records, max_bytes):
    try:
        records = int(max_records)
        byte_limit = int(max_bytes)
    except (TypeError, ValueError) as exc:
        raise ValueError("history limits must be integers") from exc
    if not 1 <= records <= ABSOLUTE_MAX_RECORDS:
        raise ValueError(f"max_records must be between 1 and {ABSOLUTE_MAX_RECORDS}")
    if not 1 <= byte_limit <= ABSOLUTE_MAX_BYTES:
        raise ValueError(f"max_bytes must be between 1 and {ABSOLUTE_MAX_BYTES}")
    return records, byte_limit


def iter_jsonl_tail(
    path,
    max_records=AUTOMATIC_MAX_RECORDS,
    max_bytes=AUTOMATIC_MAX_BYTES,
    newest_first=False,
    invalid_as_raw=False,
    operation="history_jsonl_tail",
):
    """Read a bounded JSONL tail without following symlinks or changing the file."""
    max_records, max_bytes = validate_history_limits(max_records, max_bytes)
    source = Path(path)
    metadata = {
        "partial": False,
        "coverage_complete": True,
        "records_examined": 0,
        "bytes_read": 0,
        "max_records": max_records,
        "max_bytes": max_bytes,
        "source_size_bytes": 0,
        "invalid_lines": 0,
        "incomplete_last_line": False,
    }

    with history_memory_probe(operation, source) as probe:
        if not source.exists():
            result = {"records": [], **metadata}
            probe.finish(0, False)
            return result

        source_stat = source.lstat()
        if stat.S_ISLNK(source_stat.st_mode):
            raise ValueError("history source symlink is not allowed")
        if not stat.S_ISREG(source_stat.st_mode):
            raise ValueError("history source must be a regular file")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(str(source), flags)
        try:
            opened_stat = os.fstat(descriptor)
            if not stat.S_ISREG(opened_stat.st_mode):
                raise ValueError("history source must be a regular file")
            source_size = int(opened_stat.st_size)
            metadata["source_size_bytes"] = source_size
            if source_size == 0:
                os.close(descriptor)
                descriptor = None
                result = {"records": [], **metadata}
                probe.finish(0, False)
                return result

            handle = os.fdopen(descriptor, "rb", closefd=True)
            descriptor = None
            chunks = []
            cursor = source_size
            remaining = min(source_size, max_bytes)
            recovered_from_truncate = False
            with handle:
                while remaining > 0:
                    block_size = min(READ_BLOCK_BYTES, remaining)
                    cursor -= block_size
                    try:
                        handle.seek(cursor)
                    except OSError:
                        if recovered_from_truncate:
                            raise
                        current_size = int(os.fstat(handle.fileno()).st_size)
                        if current_size >= source_size:
                            raise
                        recovered_from_truncate = True
                        metadata["partial"] = True
                        metadata["source_changed_during_read"] = True
                        chunks = []
                        cursor = current_size
                        remaining = min(current_size, max_bytes)
                        continue
                    chunk = handle.read(block_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
            data = b"".join(reversed(chunks))
            start = cursor
            expected_bytes = min(source_size, max_bytes)
            if len(data) < expected_bytes:
                metadata["partial"] = True
        finally:
            if descriptor is not None:
                os.close(descriptor)

        metadata["bytes_read"] = len(data)
        metadata["partial"] = bool(metadata["partial"] or start > 0)

        try:
            final_stat = source.lstat()
            replaced = (
                getattr(final_stat, "st_dev", None) != getattr(opened_stat, "st_dev", None)
                or getattr(final_stat, "st_ino", None) != getattr(opened_stat, "st_ino", None)
            )
            if replaced or int(final_stat.st_size) != source_size:
                metadata["partial"] = True
                metadata["source_changed_during_read"] = True
                metadata["source_size_bytes"] = max(source_size, int(final_stat.st_size))
        except OSError:
            metadata["partial"] = True
            metadata["source_changed_during_read"] = True

        if data and not data.endswith(b"\n"):
            metadata["incomplete_last_line"] = True
            metadata["partial"] = True
            boundary = data.rfind(b"\n")
            data = data[: boundary + 1] if boundary >= 0 else b""

        if start > 0 and data:
            boundary = data.find(b"\n")
            data = data[boundary + 1 :] if boundary >= 0 else b""

        raw_lines = data.split(b"\n")
        records_reversed = []
        for raw_line in reversed(raw_lines):
            if not raw_line.strip():
                continue
            if len(records_reversed) >= max_records:
                metadata["partial"] = True
                break
            metadata["records_examined"] += 1
            try:
                item = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                metadata["invalid_lines"] += 1
                if invalid_as_raw:
                    records_reversed.append({"raw": raw_line.decode("utf-8", errors="replace")})
                continue
            if isinstance(item, dict):
                records_reversed.append(item)
            else:
                metadata["invalid_lines"] += 1

        records = records_reversed if newest_first else list(reversed(records_reversed))
        metadata["coverage_complete"] = not metadata["partial"]
        result = {"records": records, **metadata}
        probe.finish(len(records), metadata["partial"])
        return result


__all__ = [
    "ABSOLUTE_MAX_BYTES",
    "ABSOLUTE_MAX_RECORDS",
    "AUTOMATIC_MAX_BYTES",
    "AUTOMATIC_MAX_RECORDS",
    "LIGHT_MAX_BYTES",
    "LIGHT_MAX_RECORDS",
    "history_memory_probe",
    "iter_jsonl_tail",
    "validate_history_limits",
]
