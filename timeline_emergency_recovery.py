"""One-shot, allowlisted, in-place recovery for the canonical timeline JSONL.

The recovery must run during early startup, before writers or worker threads.  It
never creates a lock file, backup, temporary file, or replacement file.  Once
copying starts there is deliberately no local rollback: a write failure can
leave bytes at the beginning of the file overwritten, although truncation is
deferred until the complete tail has been copied and synced.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path


MODULE = "timeline_emergency_recovery"
VERSION = "1.0.0"
TARGET_NAME = "timeline.jsonl"
MIB = 1024 * 1024
TRUE_VALUES = {"1", "true", "yes", "sim", "on"}
REGULAR_FILE_MASK = 0o170000
REGULAR_FILE_MODE = 0o100000

_STATE = "NOT_RUN"
_RESULT = None
_LOCK = threading.Lock()


def _env_true(value):
    return str(value or "").strip().lower() in TRUE_VALUES


def _number(environ, name, default, minimum, maximum, cast=float):
    try:
        value = cast(environ.get(name, default))
    except (TypeError, ValueError):
        value = cast(default)
    return max(cast(minimum), min(cast(maximum), value))


def timeline_emergency_recovery_config(environ=None):
    environ = os.environ if environ is None else environ
    return {
        "enabled": _env_true(
            environ.get("CENTRAL_TIMELINE_EMERGENCY_RECOVERY_ENABLED", "false")
        ),
        "min_usage_pct": _number(
            environ,
            "CENTRAL_TIMELINE_EMERGENCY_MIN_USAGE_PCT",
            95.0,
            80.0,
            100.0,
            float,
        ),
        "min_file_mb": _number(
            environ,
            "CENTRAL_TIMELINE_EMERGENCY_MIN_FILE_MB",
            256.0,
            64.0,
            4096.0,
            float,
        ),
        "keep_tail_mb": _number(
            environ,
            "CENTRAL_TIMELINE_EMERGENCY_KEEP_TAIL_MB",
            32.0,
            8.0,
            256.0,
            float,
        ),
        "block_mb": _number(
            environ,
            "CENTRAL_TIMELINE_EMERGENCY_BLOCK_MB",
            1,
            1,
            8,
            int,
        ),
    }


def _mb(value):
    if value is None:
        return None
    return round(float(value) / MIB, 6)


def _base_result(config):
    return {
        "ok": True,
        "module": MODULE,
        "version": VERSION,
        "enabled": bool(config.get("enabled")),
        "attempted": False,
        "status": "DISABLED",
        "read_only": not bool(config.get("enabled")),
        "operational_authority": False,
        "execution_control": False,
        "broker_access": False,
        "registry_write_access": False,
        "lifecycle_write_access": False,
        "target": TARGET_NAME,
        "before": {
            "file_size_bytes": None,
            "file_size_mb": None,
            "filesystem_usage_pct": None,
            "filesystem_free_bytes": None,
        },
        "after": {
            "file_size_bytes": None,
            "file_size_mb": None,
            "filesystem_usage_pct": None,
            "filesystem_free_bytes": None,
        },
        "source_start_offset": None,
        "bytes_preserved": 0,
        "bytes_freed": 0,
        "first_partial_line_discarded": False,
        "last_line_incomplete": False,
        "target_reached": False,
        "one_shot": True,
        "errors": [],
        "warnings": [],
    }


def _public_error(phase, exc):
    return f"{phase}:{type(exc).__name__}"


def _is_regular_mode(mode):
    return (int(mode) & REGULAR_FILE_MASK) == REGULAR_FILE_MODE


def _lexical_absolute(path):
    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _validate_timeline_target(central_data_dir, target=None):
    """Read-only validation helper; recovery itself never accepts a target."""
    try:
        data_dir = _lexical_absolute(central_data_dir)
        candidate = _lexical_absolute(
            target if target is not None else data_dir / TARGET_NAME
        )
    except Exception as exc:
        return {"ok": False, "status": "INVALID_TARGET", "error": _public_error("path", exc)}

    anchor = Path(data_dir.anchor) if data_dir.anchor else None
    if not data_dir.name or (anchor is not None and data_dir == anchor):
        return {"ok": False, "status": "INVALID_TARGET"}
    if candidate.name != TARGET_NAME:
        return {"ok": False, "status": "INVALID_TARGET"}
    if candidate.parent != data_dir or candidate != data_dir / TARGET_NAME:
        return {"ok": False, "status": "INVALID_TARGET"}

    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return {"ok": False, "status": "FILE_MISSING"}
    except Exception as exc:
        return {"ok": False, "status": "ERROR", "error": _public_error("lstat", exc)}

    if candidate.is_symlink():
        return {"ok": False, "status": "SYMLINK_REJECTED"}
    if not _is_regular_mode(metadata.st_mode):
        return {"ok": False, "status": "NOT_REGULAR_FILE"}
    if int(getattr(metadata, "st_nlink", 1) or 1) != 1:
        return {"ok": False, "status": "INVALID_TARGET", "warning": "hardlink_rejected"}
    return {
        "ok": True,
        "status": "VALID",
        "_data_dir": data_dir,
        "_target": candidate,
        "_metadata": metadata,
    }


def _disk_snapshot(path, file_size, disk_usage_func=None):
    usage = (disk_usage_func or shutil.disk_usage)(path)
    total = int(usage.total)
    used = int(usage.used)
    free = int(usage.free)
    usage_pct = round((used / total * 100.0) if total > 0 else 0.0, 6)
    return {
        "file_size_bytes": int(file_size),
        "file_size_mb": _mb(file_size),
        "filesystem_usage_pct": usage_pct,
        "filesystem_free_bytes": free,
    }


def _open_target(path):
    flags = os.O_RDWR
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(os.fspath(path), flags)
    try:
        return os.fdopen(descriptor, "r+b", buffering=0)
    except Exception:
        os.close(descriptor)
        raise


def _find_source_start(stream, approximate_offset, original_size, buffer):
    stream.seek(approximate_offset, os.SEEK_SET)
    position = approximate_offset
    while position < original_size:
        limit = min(len(buffer), original_size - position)
        count = stream.readinto(memoryview(buffer)[:limit])
        if not count:
            return None
        newline = buffer.find(b"\n", 0, count)
        if newline >= 0:
            return position + newline + 1
        position += count
    return None


def _last_line_incomplete(stream, original_size, one_byte):
    if original_size <= 0:
        return False
    stream.seek(original_size - 1, os.SEEK_SET)
    count = stream.readinto(one_byte)
    return bool(count == 1 and one_byte[0] != 10)


def _copy_tail_in_place(stream, source_start, original_size, buffer):
    read_offset = source_start
    write_offset = 0
    while read_offset < original_size:
        wanted = min(len(buffer), original_size - read_offset)
        stream.seek(read_offset, os.SEEK_SET)
        count = stream.readinto(memoryview(buffer)[:wanted])
        if not count:
            raise OSError("bounded read ended before EOF")
        stream.seek(write_offset, os.SEEK_SET)
        written = 0
        view = memoryview(buffer)
        while written < count:
            amount = stream.write(view[written:count])
            if not amount:
                raise OSError("bounded write made no progress")
            written += amount
        read_offset += count
        write_offset += count
    return write_offset


def _safe_after_snapshot(result, data_dir, target, disk_usage_func=None):
    try:
        size = target.lstat().st_size
        result["after"] = _disk_snapshot(data_dir, size, disk_usage_func)
        before_size = (result.get("before") or {}).get("file_size_bytes")
        if before_size is not None:
            result["bytes_freed"] = max(0, int(before_size) - int(size))
    except Exception as exc:
        result["warnings"].append(_public_error("after_snapshot", exc))


def _recover_once(central_data_dir, config, disk_usage_func=None):
    result = _base_result(config)
    if not config["enabled"]:
        return result

    result["read_only"] = True
    validation = _validate_timeline_target(central_data_dir)
    if not validation.get("ok"):
        result["status"] = validation.get("status", "ERROR")
        result["ok"] = result["status"] != "ERROR"
        if validation.get("error"):
            result["errors"].append(validation["error"])
        if validation.get("warning"):
            result["warnings"].append(validation["warning"])
        return result

    data_dir = validation["_data_dir"]
    target = validation["_target"]
    metadata = validation["_metadata"]
    original_size = int(metadata.st_size)
    try:
        result["before"] = _disk_snapshot(
            data_dir, original_size, disk_usage_func=disk_usage_func
        )
        result["after"] = dict(result["before"])
    except Exception as exc:
        result.update({"ok": False, "status": "ERROR"})
        result["errors"].append(_public_error("disk_usage", exc))
        return result

    if result["before"]["filesystem_usage_pct"] < config["min_usage_pct"]:
        result["status"] = "THRESHOLD_NOT_REACHED"
        return result

    minimum_bytes = int(config["min_file_mb"] * MIB)
    keep_tail_bytes = int(config["keep_tail_mb"] * MIB)
    if original_size < minimum_bytes:
        result["status"] = "FILE_BELOW_MINIMUM"
        return result
    if original_size <= keep_tail_bytes:
        result["status"] = "KEEP_TAIL_NOT_SMALLER"
        return result

    block_bytes = int(config["block_mb"] * MIB)
    buffer = bytearray(block_bytes)
    one_byte = bytearray(1)
    approximate_offset = max(0, original_size - keep_tail_bytes)
    copy_started = False
    phase = "open"
    try:
        with _open_target(target) as stream:
            opened = os.fstat(stream.fileno())
            if not _is_regular_mode(opened.st_mode):
                result["status"] = "NOT_REGULAR_FILE"
                return result
            if int(getattr(opened, "st_nlink", 1) or 1) != 1:
                result["status"] = "INVALID_TARGET"
                result["warnings"].append("hardlink_rejected")
                return result
            if (
                int(opened.st_size) != original_size
                or getattr(opened, "st_dev", None) != getattr(metadata, "st_dev", None)
                or getattr(opened, "st_ino", None) != getattr(metadata, "st_ino", None)
            ):
                result.update({"ok": False, "status": "ERROR"})
                result["errors"].append("target_changed_before_recovery")
                return result

            phase = "last_byte"
            result["last_line_incomplete"] = _last_line_incomplete(
                stream, original_size, one_byte
            )
            phase = "boundary"
            source_start = _find_source_start(
                stream, approximate_offset, original_size, buffer
            )
            if source_start is None or source_start >= original_size:
                result["status"] = "NO_COMPLETE_LINE_BOUNDARY"
                return result

            result["source_start_offset"] = source_start
            result["bytes_preserved"] = original_size - source_start
            result["first_partial_line_discarded"] = source_start > approximate_offset
            result["attempted"] = True
            result["read_only"] = False

            phase = "copy"
            copy_started = True
            copied = _copy_tail_in_place(stream, source_start, original_size, buffer)
            if copied != result["bytes_preserved"]:
                raise OSError("copy length mismatch")

            phase = "pre_truncate_sync"
            stream.flush()
            os.fsync(stream.fileno())
            phase = "truncate"
            stream.truncate(copied)
            phase = "post_truncate_sync"
            stream.flush()
            os.fsync(stream.fileno())

        result["bytes_freed"] = original_size - result["bytes_preserved"]
        result["status"] = "RECOVERED"
        result["target_reached"] = result["bytes_preserved"] <= keep_tail_bytes
        _safe_after_snapshot(result, data_dir, target, disk_usage_func)
        return result
    except Exception as exc:
        result.update({"ok": False, "status": "ERROR"})
        result["errors"].append(_public_error(phase, exc))
        if copy_started:
            result["warnings"].append(
                "in_place_copy_started_no_local_rollback_guaranteed"
            )
        _safe_after_snapshot(result, data_dir, target, disk_usage_func)
        return result


def run_timeline_emergency_recovery(
    central_data_dir, environ=None, disk_usage_func=None
):
    """Run at most once in this process and never raise into startup."""
    global _STATE, _RESULT
    with _LOCK:
        if _STATE != "NOT_RUN":
            previous = dict(_RESULT or {})
            previous["status"] = "ALREADY_RUN"
            previous["previous_status"] = (_RESULT or {}).get("status")
            previous["one_shot"] = True
            return previous

        _STATE = "RUNNING"
        config = timeline_emergency_recovery_config(environ)
        try:
            result = _recover_once(
                central_data_dir, config, disk_usage_func=disk_usage_func
            )
        except Exception as exc:
            result = _base_result(config)
            result.update({"ok": False, "status": "ERROR"})
            result["errors"].append(_public_error("recovery", exc))

        _RESULT = result
        if result.get("status") == "RECOVERED":
            _STATE = "COMPLETED"
        elif result.get("status") == "ERROR":
            _STATE = "ERROR"
        else:
            _STATE = "SKIPPED"
        return result


def build_timeline_emergency_recovery_health(result):
    """Pure in-memory health projection; performs no filesystem operation."""
    result = result if isinstance(result, dict) else {}
    before = result.get("before") if isinstance(result.get("before"), dict) else {}
    after = result.get("after") if isinstance(result.get("after"), dict) else {}
    return {
        "timeline_emergency_recovery_enabled": bool(result.get("enabled", False)),
        "timeline_emergency_recovery_status": result.get("status", "ERROR"),
        "timeline_emergency_recovery_attempted": bool(result.get("attempted", False)),
        "timeline_emergency_recovery_before_mb": before.get("file_size_mb"),
        "timeline_emergency_recovery_after_mb": after.get("file_size_mb"),
        "timeline_emergency_recovery_freed_mb": _mb(result.get("bytes_freed", 0)),
        "timeline_emergency_recovery_target_reached": bool(
            result.get("target_reached", False)
        ),
    }


def build_startup_summary(result):
    """Return the single sanitized startup evidence line."""
    result = result if isinstance(result, dict) else {}
    before = result.get("before") if isinstance(result.get("before"), dict) else {}
    after = result.get("after") if isinstance(result.get("after"), dict) else {}
    return (
        "TIMELINE EMERGENCY RECOVERY "
        f"status={result.get('status', 'ERROR')} "
        f"before_mb={before.get('file_size_mb')} "
        f"after_mb={after.get('file_size_mb')} "
        f"freed_mb={_mb(result.get('bytes_freed', 0))} "
        f"usage_before={before.get('filesystem_usage_pct')} "
        f"usage_after={after.get('filesystem_usage_pct')}"
    )


__all__ = [
    "build_startup_summary",
    "build_timeline_emergency_recovery_health",
    "run_timeline_emergency_recovery",
    "timeline_emergency_recovery_config",
]
