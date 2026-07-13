"""Bounded, read-only filesystem diagnostics for Central Quant startup."""

from __future__ import annotations

import heapq
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


VERSION = "1.0.0-READ-ONLY"
_FALSE_VALUES = frozenset({"0", "false", "no", "não", "nao", "off"})
_MAX_ERRORS = 100
_RECENT_FILES_LIMIT = 20
_MAX_RESPONSE_BYTES = 512 * 1024

_CRITICAL_NAMES = (
    "trade_registry.json",
    "trade_registry_backup_latest.json",
    "closed_trades.jsonl",
    "trade_journal.jsonl",
    "trade_lifecycle.jsonl",
    "learning_audit.jsonl",
    "learning_state.json",
    "learning_export.json",
    "executive_policy.json",
    "executive_policy_log.jsonl",
    "central_runtime_events.jsonl",
    "central_runtime_state.json",
    "decision_log.jsonl",
    "timeline.jsonl",
    "memory_profiler_snapshots.jsonl",
    "memory_profiler_state.json",
    "memory_profiler_error.log",
    "runtime_stability_events.jsonl",
    "history_events.jsonl",
    "history_export.json",
    "history_export.jsonl",
    "history_seen.json",
    "trade_journal_seen.json",
    "trade_journal_export.json",
    "trade_lifecycle_export.json",
    "trade_lifecycle_shadow_runtime_events.jsonl",
    "trade_lifecycle_shadow_runtime_divergences.jsonl",
    "trade_lifecycle_shadow_runtime_state.json",
    "trade_lifecycle_shadow_events.jsonl",
    "trade_lifecycle_shadow_divergences.jsonl",
    "trade_lifecycle_shadow_snapshot.json",
)


def _env_enabled(environ) -> bool:
    value = str(environ.get("CENTRAL_STARTUP_DISK_FORENSICS_ENABLED", "true"))
    return value.strip().lower() not in _FALSE_VALUES


def _bounded_int(environ, name, default, minimum, maximum):
    try:
        value = int(environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def disk_forensics_config(environ=None):
    environ = os.environ if environ is None else environ
    return {
        "enabled": _env_enabled(environ),
        "max_files": _bounded_int(
            environ, "CENTRAL_STARTUP_DISK_FORENSICS_MAX_FILES", 30, 1, 100
        ),
        "max_dirs": _bounded_int(
            environ, "CENTRAL_STARTUP_DISK_FORENSICS_MAX_DIRS", 20, 1, 50
        ),
        "max_scan_files": _bounded_int(
            environ,
            "CENTRAL_STARTUP_DISK_FORENSICS_MAX_SCAN_FILES",
            100000,
            1,
            1000000,
        ),
    }


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _modified_at(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _normal_path(path):
    return os.path.normcase(os.path.abspath(os.path.normpath(os.fspath(path))))


def _is_within(path, root):
    try:
        return os.path.commonpath((_normal_path(path), _normal_path(root))) == _normal_path(
            root
        )
    except (OSError, ValueError, TypeError):
        return False


def _relative_path(path, root):
    if not _is_within(path, root):
        return None
    try:
        relative = os.path.relpath(_normal_path(path), _normal_path(root))
    except (OSError, ValueError, TypeError):
        return None
    relative = relative.replace("\\", "/")
    if relative == ".":
        return "."
    if relative == ".." or relative.startswith("../") or "/../" in relative:
        return None
    return relative.lstrip("/")


def _sanitize_error(exc, roots=()):
    text = f"{type(exc).__name__}: {exc}".replace("\r", " ").replace("\n", " ")
    for root in roots:
        raw = os.fspath(root)
        if raw:
            text = text.replace(raw, "<root>")
            text = text.replace(raw.replace("\\", "/"), "<root>")
    return text[:300]


def _classification_hint(relative_path):
    value = str(relative_path or "").lower().replace("\\", "/")
    name = value.rsplit("/", 1)[-1]
    if "registry" in value:
        return "REGISTRY"
    if "shadow" in value:
        return "SHADOW"
    if "lifecycle" in value:
        return "LIFECYCLE"
    if "journal" in value:
        return "JOURNAL"
    if "export" in value:
        return "EXPORT"
    if "snapshot" in value:
        return "SNAPSHOT"
    if "__pycache__" in value or name.endswith((".pyc", ".pyo")):
        return "PYTHON_CACHE"
    if "cache" in value:
        return "CACHE"
    if "tmp" in value or "temp" in value or name.endswith((".tmp", ".temp")):
        return "TEMP"
    if name.endswith((".log", ".jsonl")) or "log" in name or "events" in name:
        return "LOG"
    return "UNKNOWN"


def _push_limited(heap, key, record, limit, serial):
    item = (key, serial, record)
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif key > heap[0][0]:
        heapq.heapreplace(heap, item)


def _base_result(enabled, max_scan_files):
    return {
        "ok": True,
        "module": "startup_disk_forensics",
        "version": VERSION,
        "enabled": bool(enabled),
        "read_only": True,
        "generated_at": _now(),
        "partial": False,
        "scan": {
            "roots": [],
            "scanned_roots": [],
            "files_examined": 0,
            "directories_examined": 0,
            "symlinks_skipped": 0,
            "errors_count": 0,
            "max_scan_files": int(max_scan_files),
        },
        "filesystems": [],
        "largest_files": [],
        "largest_directories": [],
        "recent_files": [],
        "critical_files": [],
        "errors": [],
        "authorities": {
            "write_access": False,
            "delete_access": False,
            "registry_write_access": False,
            "lifecycle_write_access": False,
            "broker_access": False,
            "execution_control": False,
        },
    }


def _add_error(result, scope, exc, roots=()):
    result["scan"]["errors_count"] += 1
    if len(result["errors"]) < _MAX_ERRORS:
        result["errors"].append(
            {"scope": str(scope)[:80], "error": _sanitize_error(exc, roots)}
        )


def _candidate_roots(project_root, central_data_dir, additional_roots=None):
    project = Path(project_root)
    if additional_roots is None:
        additional_roots = (
            ("persistent_data", Path("/data")),
            ("render_project_data", Path("/opt/render/project/src/data")),
        )
    return (
        ("project", project),
        ("project_data", project / "data"),
        ("central_data", Path(central_data_dir)) if central_data_dir else None,
        *tuple(additional_roots),
    )


def _collect_roots(project_root, central_data_dir, result, additional_roots=None):
    roots = []
    seen = set()
    for candidate in _candidate_roots(
        project_root, central_data_dir, additional_roots=additional_roots
    ):
        if candidate is None:
            continue
        label, path = candidate
        normalized = _normal_path(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            if path.is_symlink():
                result["scan"]["symlinks_skipped"] += 1
                continue
            if not path.exists() or not path.is_dir():
                if label in {"project", "central_data"}:
                    _add_error(result, label, FileNotFoundError("root not available"), (path,))
                continue
            roots.append({"label": label, "path": Path(normalized)})
        except OSError as exc:
            _add_error(result, label, exc, (path,))
    result["scan"]["roots"] = [item["label"] for item in roots]
    return roots


def _filesystem_records(roots, result):
    records = []
    seen = set()
    for item in roots:
        try:
            usage = shutil.disk_usage(item["path"])
            try:
                device = os.stat(item["path"], follow_symlinks=False).st_dev
            except (AttributeError, OSError):
                device = (usage.total, usage.free)
            if device in seen:
                continue
            seen.add(device)
            record = {
                "root": item["label"],
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
                "usage_pct": round((usage.used / usage.total) * 100, 2)
                if usage.total
                else 0.0,
            }
            if hasattr(os, "statvfs"):
                try:
                    inode = os.statvfs(item["path"])
                    total = int(inode.f_files)
                    free = int(inode.f_ffree)
                    record["inodes"] = {
                        "total": total,
                        "used": max(0, total - free),
                        "free": free,
                        "usage_pct": round(((total - free) / total) * 100, 2)
                        if total
                        else None,
                    }
                except OSError:
                    pass
            records.append(record)
        except OSError as exc:
            _add_error(result, f"disk_usage:{item['label']}", exc, (item["path"],))
    return records


def _select_scan_roots(roots):
    """Return roots not contained by any other collected root, regardless of order."""
    selected = []
    for item in roots:
        path = item["path"]
        if any(
            _normal_path(path) != _normal_path(other["path"])
            and _is_within(path, other["path"])
            for other in roots
        ):
            continue
        if any(_normal_path(path) == _normal_path(other["path"]) for other in selected):
            continue
        selected.append(item)
    return selected


def _finalize_directory_frame(
    stack,
    root_item,
    root,
    result,
    largest_dirs,
    max_dirs,
    serial,
    partial=False,
):
    frame = stack.pop()
    try:
        frame["iterator"].close()
    except OSError as exc:
        _add_error(result, "iterator_close", exc, (root,))
        partial = True
        result["partial"] = True
    frame_partial = bool(frame.get("partial") or partial)
    directory_record = {
        "root": root_item["label"],
        "relative_path": frame["relative"],
        "size_bytes": int(frame["size"]),
        "file_count": int(frame["files"]),
        "directory_count": int(frame["dirs"]),
        "partial": frame_partial,
    }
    serial += 1
    _push_limited(
        largest_dirs,
        directory_record["size_bytes"],
        directory_record,
        max_dirs,
        serial,
    )
    if stack:
        parent = stack[-1]
        parent["size"] += frame["size"]
        parent["files"] += frame["files"]
        parent["dirs"] += frame["dirs"] + 1
        parent["partial"] = bool(parent.get("partial") or frame_partial)
    return serial


def _scan_roots(roots, result, max_files, max_dirs, max_scan_files):
    largest_files = []
    recent_files = []
    largest_dirs = []
    serial = 0
    scan_roots = _select_scan_roots(roots)
    result["scan"]["scanned_roots"] = [item["label"] for item in scan_roots]
    limit_reached = False

    for root_item in scan_roots:
        if limit_reached:
            break
        root = root_item["path"]
        try:
            iterator = os.scandir(root)
        except OSError as exc:
            _add_error(result, f"scan:{root_item['label']}", exc, (root,))
            result["partial"] = True
            continue
        stack = [
            {
                "path": root,
                "relative": ".",
                "iterator": iterator,
                "size": 0,
                "files": 0,
                "dirs": 0,
                "partial": False,
            }
        ]
        result["scan"]["directories_examined"] += 1
        while stack:
            frame = stack[-1]
            try:
                entry = next(frame["iterator"])
            except StopIteration:
                serial = _finalize_directory_frame(
                    stack,
                    root_item,
                    root,
                    result,
                    largest_dirs,
                    max_dirs,
                    serial,
                )
                continue
            except OSError as exc:
                _add_error(result, "iterator", exc, (root,))
                result["partial"] = True
                serial = _finalize_directory_frame(
                    stack,
                    root_item,
                    root,
                    result,
                    largest_dirs,
                    max_dirs,
                    serial,
                    partial=True,
                )
                continue

            try:
                if entry.is_symlink():
                    result["scan"]["symlinks_skipped"] += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    relative = _relative_path(entry.path, root)
                    if relative is None:
                        continue
                    try:
                        child_iterator = os.scandir(entry.path)
                    except OSError as exc:
                        _add_error(result, "scandir", exc, (root,))
                        frame["dirs"] += 1
                        frame["partial"] = True
                        result["partial"] = True
                        continue
                    stack.append(
                        {
                            "path": Path(entry.path),
                            "relative": relative,
                            "iterator": child_iterator,
                            "size": 0,
                            "files": 0,
                            "dirs": 0,
                            "partial": False,
                        }
                    )
                    result["scan"]["directories_examined"] += 1
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat_result = entry.stat(follow_symlinks=False)
                relative = _relative_path(entry.path, root)
                if relative is None:
                    continue
                size = int(stat_result.st_size)
                modified = float(stat_result.st_mtime)
                record = {
                    "root": root_item["label"],
                    "relative_path": relative,
                    "size_bytes": size,
                    "size_mb": round(size / (1024 * 1024), 3),
                    "modified_at": _modified_at(modified),
                    "suffix": Path(entry.name).suffix.lower()[:20],
                    "classification_hint": _classification_hint(relative),
                }
                frame["size"] += size
                frame["files"] += 1
                result["scan"]["files_examined"] += 1
                serial += 1
                _push_limited(largest_files, size, record, max_files, serial)
                recent_record = {
                    "root": record["root"],
                    "relative_path": relative,
                    "size_bytes": size,
                    "modified_at": record["modified_at"],
                    "classification_hint": record["classification_hint"],
                }
                _push_limited(
                    recent_files,
                    modified,
                    recent_record,
                    _RECENT_FILES_LIMIT,
                    serial,
                )
                if result["scan"]["files_examined"] >= max_scan_files:
                    result["partial"] = True
                    limit_reached = True
                    break
            except OSError as exc:
                _add_error(result, "entry", exc, (root,))
                frame["partial"] = True
                result["partial"] = True

        while stack:
            serial = _finalize_directory_frame(
                stack,
                root_item,
                root,
                result,
                largest_dirs,
                max_dirs,
                serial,
                partial=True,
            )

    result["largest_files"] = [
        item[2] for item in sorted(largest_files, key=lambda row: row[0], reverse=True)
    ]
    result["recent_files"] = [
        item[2] for item in sorted(recent_files, key=lambda row: row[0], reverse=True)
    ]
    result["largest_directories"] = [
        item[2] for item in sorted(largest_dirs, key=lambda row: row[0], reverse=True)
    ]


def _critical_candidates(roots, project_root):
    candidates = []
    for item in roots:
        if item["label"] == "project":
            continue
        for name in _CRITICAL_NAMES:
            candidates.append((item, item["path"] / name))
    project_item = next((item for item in roots if item["label"] == "project"), None)
    if project_item:
        candidates.append((project_item, Path(project_root) / "predator_paper_events.jsonl"))
        for name in _CRITICAL_NAMES:
            candidates.append((project_item, Path(project_root) / "data" / name))
    return candidates


def _critical_records(roots, project_root, result):
    records = []
    seen = set()
    for root_item, path in _critical_candidates(roots, project_root):
        normalized = _normal_path(path)
        if normalized in seen or not _is_within(path, root_item["path"]):
            continue
        seen.add(normalized)
        relative = _relative_path(path, root_item["path"])
        record = {
            "root": root_item["label"],
            "relative_path": relative,
            "exists": False,
            "size_bytes": None,
            "modified_at": None,
            "regular_file": False,
            "symlink": False,
            "readable": False,
            "error": None,
        }
        try:
            record["symlink"] = path.is_symlink()
            record["exists"] = path.exists() or record["symlink"]
            if record["exists"] and not record["symlink"]:
                stat_result = path.stat()
                record["regular_file"] = path.is_file()
                record["size_bytes"] = int(stat_result.st_size)
                record["modified_at"] = _modified_at(stat_result.st_mtime)
                record["readable"] = bool(os.access(path, os.R_OK))
        except OSError as exc:
            record["error"] = _sanitize_error(exc, (root_item["path"],))
            _add_error(result, "critical_file", exc, (root_item["path"],))
        records.append(record)
    return records


def _trim_result(result):
    def encoded_size(payload):
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    trim_order = (
        "errors",
        "critical_files",
        "recent_files",
        "largest_directories",
        "largest_files",
    )
    while encoded_size(result) > _MAX_RESPONSE_BYTES:
        trimmed = False
        for key in trim_order:
            values = result.get(key)
            if isinstance(values, list) and values:
                values.pop()
                result["partial"] = True
                trimmed = True
                break
        if not trimmed:
            break
    if encoded_size(result) <= _MAX_RESPONSE_BYTES:
        return result

    scan = result.get("scan") if isinstance(result.get("scan"), dict) else {}
    minimum = {
        "ok": bool(result.get("ok")),
        "module": "startup_disk_forensics",
        "version": VERSION,
        "enabled": bool(result.get("enabled")),
        "read_only": True,
        "generated_at": result.get("generated_at") if isinstance(result.get("generated_at"), str) else _now(),
        "partial": True,
        "scan": {
            "roots": [],
            "scanned_roots": [],
            "files_examined": int(scan.get("files_examined", 0) or 0),
            "directories_examined": int(scan.get("directories_examined", 0) or 0),
            "symlinks_skipped": int(scan.get("symlinks_skipped", 0) or 0),
            "errors_count": int(scan.get("errors_count", 0) or 0),
            "max_scan_files": int(scan.get("max_scan_files", 0) or 0),
        },
        "filesystems": list(result.get("filesystems") or []),
        "largest_files": [],
        "largest_directories": [],
        "recent_files": [],
        "critical_files": [],
        "errors": [{"scope": "response", "error": "diagnostic payload truncated"}],
        "authorities": dict(result.get("authorities") or {}),
    }
    while encoded_size(minimum) > _MAX_RESPONSE_BYTES and minimum["filesystems"]:
        minimum["filesystems"].pop()
    if encoded_size(minimum) > _MAX_RESPONSE_BYTES:
        minimum["errors"] = []
    if encoded_size(minimum) > _MAX_RESPONSE_BYTES:
        minimum["generated_at"] = _now()
        minimum["filesystems"] = []
        minimum["errors"] = []
        minimum["authorities"] = {
            "write_access": False,
            "delete_access": False,
            "registry_write_access": False,
            "lifecycle_write_access": False,
            "broker_access": False,
            "execution_control": False,
        }
    return minimum


def run_startup_disk_forensics(
    project_root, central_data_dir=None, environ=None, additional_roots=None
):
    """Inspect allowed roots without opening file contents or mutating disk."""
    config = disk_forensics_config(environ)
    result = _base_result(config["enabled"], config["max_scan_files"])
    if not config["enabled"]:
        return result
    roots = _collect_roots(
        project_root,
        central_data_dir,
        result,
        additional_roots=additional_roots,
    )
    result["filesystems"] = _filesystem_records(roots, result)
    _scan_roots(
        roots,
        result,
        config["max_files"],
        config["max_dirs"],
        config["max_scan_files"],
    )
    result["critical_files"] = _critical_records(roots, project_root, result)
    return _trim_result(result)


def build_disk_forensics_health(result):
    """Build a filesystem-free health projection from the in-memory result."""
    payload = result if isinstance(result, dict) else {}
    filesystems = payload.get("filesystems") or []
    filesystem = max(filesystems, key=lambda item: item.get("usage_pct", 0), default={})
    largest = (payload.get("largest_files") or [{}])[0]
    available = bool(payload.get("ok") and payload.get("enabled") and filesystems)
    return {
        "disk_forensics_available": available,
        "disk_forensics_usage_pct": filesystem.get("usage_pct"),
        "disk_forensics_free_mb": round(filesystem.get("free_bytes", 0) / (1024 * 1024), 2)
        if filesystem
        else None,
        "disk_forensics_partial": bool(payload.get("partial")) if available else None,
        "disk_forensics_largest_file": largest.get("relative_path") if largest else None,
        "disk_forensics_largest_file_mb": largest.get("size_mb") if largest else None,
    }


def build_startup_summary(result):
    health = build_disk_forensics_health(result)
    largest_file = health.get("disk_forensics_largest_file")
    normalized = str(largest_file or "").replace("\\", "/")
    drive, _ = os.path.splitdrive(normalized)
    windows_absolute = (
        len(normalized) >= 3
        and normalized[1] == ":"
        and normalized[2] == "/"
    )
    if (
        not normalized
        or drive
        or windows_absolute
        or normalized.startswith("/")
        or ".." in normalized.split("/")
    ):
        largest_file = None
    return (
        "DISK FORENSICS\n"
        f"usage_pct={health.get('disk_forensics_usage_pct')}\n"
        f"free_mb={health.get('disk_forensics_free_mb')}\n"
        f"largest_file={largest_file}\n"
        f"largest_file_mb={health.get('disk_forensics_largest_file_mb')}\n"
        f"partial={health.get('disk_forensics_partial')}"
    )


__all__ = [
    "VERSION",
    "build_disk_forensics_health",
    "build_startup_summary",
    "disk_forensics_config",
    "run_startup_disk_forensics",
]
