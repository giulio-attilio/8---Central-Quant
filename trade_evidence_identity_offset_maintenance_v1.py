"""Fail-safe automated maintenance for READY trade-evidence offset indexes.

The scheduler is default-off and never builds or rebuilds an index.  A tick
performs a bounded metadata/anchor check first and invokes the existing
``catch_up_index`` API only after threshold, cooldown, disk, and single-flight
guards pass.  Importing this module starts no thread and opens no file.
"""

from __future__ import annotations

import copy
import hashlib
import os
import shutil
import sqlite3
import stat
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from trade_evidence_identity_contract import IDENTITY_CONTRACT_HASH
from trade_evidence_identity_offset_index_v1 import (
    BUILDER_VERSION,
    HASH_BYTES,
    INDEX_COMPLETE_FOR_SNAPSHOT,
    INDEX_PARTIAL,
    INDEX_SOURCE_CHANGED,
    INDEX_VERSION,
    SCHEMA_VERSION,
    SQLITE_APPLICATION_ID,
    catch_up_index,
    normalized_path_hash,
)


VERSION = "2026-08-15-TRADE-EVIDENCE-IDENTITY-OFFSET-INDEX-V1-SAFE-AUTO-MAINTENANCE"
SOURCE_ORDER = ("history_manager", "timeline")

DISABLED = "DISABLED"
IDLE = "IDLE"
CHECKED_NO_ACTION = "CHECKED_NO_ACTION"
SKIP_SMALL_LAG = "SKIP_SMALL_LAG"
SKIP_NOT_READY = "SKIP_NOT_READY"
INDEX_MISSING = "INDEX_MISSING"
SOURCE_CHANGED = "SOURCE_CHANGED"
CATCH_UP_ELIGIBLE = "CATCH_UP_ELIGIBLE"
CATCH_UP_RUNNING = "CATCH_UP_RUNNING"
CATCH_UP_OK = "CATCH_UP_OK"
CATCH_UP_PARTIAL = "CATCH_UP_PARTIAL"
CATCH_UP_FAILED = "CATCH_UP_FAILED"
LOCK_BUSY = "LOCK_BUSY"
COOLDOWN = "COOLDOWN"
LOW_DISK = "LOW_DISK"

DEFAULT_INTERVAL_SECONDS = 3600.0
DEFAULT_MIN_LAG_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_LAG_BYTES = 64 * 1024 * 1024
DEFAULT_MIN_SECONDS_BETWEEN_RUNS = 3600.0
DEFAULT_BUSY_TIMEOUT_SECONDS = 0.25
DEFAULT_STARTUP_GRACE_SECONDS = 300.0
DEFAULT_MIN_FREE_BYTES = 512 * 1024 * 1024
MAX_INTERVAL_SECONDS = 7 * 24 * 3600.0
MAX_BUSY_TIMEOUT_SECONDS = 5.0
MAX_ANCHOR_BYTES = 1024 * 1024
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

try:
    import fcntl as _fcntl
except Exception:  # pragma: no cover - Windows path
    _fcntl = None

try:
    import msvcrt as _msvcrt
except Exception:  # pragma: no cover - POSIX path
    _msvcrt = None


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    source_path: Path
    index_path: Path

    @property
    def cooldown_stamp_path(self) -> Path:
        return self.index_path.with_name(
            self.index_path.name + ".auto-maintenance-v1.stamp"
        )


@dataclass(frozen=True)
class MaintenanceConfig:
    enabled: bool = False
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    min_lag_bytes: int = DEFAULT_MIN_LAG_BYTES
    max_lag_bytes: int = DEFAULT_MAX_LAG_BYTES
    min_seconds_between_runs: float = DEFAULT_MIN_SECONDS_BETWEEN_RUNS
    busy_timeout_seconds: float = DEFAULT_BUSY_TIMEOUT_SECONDS
    startup_grace_seconds: float = DEFAULT_STARTUP_GRACE_SECONDS
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES
    history_source_path: Path = Path("data/history_events.jsonl")
    history_index_path: Path = Path("data/history_events.identity-offset-v1.sqlite3")
    timeline_source_path: Path = Path("data/timeline.jsonl")
    timeline_index_path: Path = Path("data/timeline.identity-offset-v1.sqlite3")
    lock_path: Path = Path("data/.trade-evidence-index-auto-maintenance-v1.lock")

    @classmethod
    def from_environ(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        *,
        data_dir: Optional[Path | str] = None,
    ) -> "MaintenanceConfig":
        env = os.environ if environ is None else environ
        root = Path(data_dir) if data_dir is not None else Path(
            str(env.get("CENTRAL_DATA_DIR") or env.get("DATA_DIR") or "data")
        )

        def enabled(name: str) -> bool:
            return str(env.get(name, "") or "").strip().lower() in _TRUE_VALUES

        def positive_float(
            name: str,
            default: float,
            *,
            minimum: float,
            maximum: float,
        ) -> float:
            try:
                value = float(env.get(name, default))
            except (TypeError, ValueError):
                return default
            if value < minimum or value > maximum:
                return default
            return value

        def positive_int(name: str, default: int, *, maximum: int) -> int:
            try:
                value = int(env.get(name, default))
            except (TypeError, ValueError):
                return default
            if value <= 0 or value > maximum:
                return default
            return value

        def optional_path(name: str, fallback: Path) -> Path:
            raw = str(env.get(name, "") or "").strip()
            return Path(raw) if raw else fallback

        min_lag = positive_int(
            "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_MIN_LAG_BYTES",
            DEFAULT_MIN_LAG_BYTES,
            maximum=1024 * 1024 * 1024 * 1024,
        )
        max_lag = positive_int(
            "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_MAX_LAG_BYTES",
            DEFAULT_MAX_LAG_BYTES,
            maximum=1024 * 1024 * 1024 * 1024,
        )
        max_lag = max(min_lag, max_lag)
        history_index = optional_path(
            "TRADE_EVIDENCE_INDEX_HISTORY_PATH",
            root / "history_events.identity-offset-v1.sqlite3",
        )
        timeline_index = optional_path(
            "TRADE_EVIDENCE_INDEX_TIMELINE_PATH",
            root / "timeline.identity-offset-v1.sqlite3",
        )
        return cls(
            enabled=enabled("TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_ENABLED"),
            interval_seconds=positive_float(
                "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_INTERVAL_SECONDS",
                DEFAULT_INTERVAL_SECONDS,
                minimum=60.0,
                maximum=MAX_INTERVAL_SECONDS,
            ),
            min_lag_bytes=min_lag,
            max_lag_bytes=max_lag,
            min_seconds_between_runs=positive_float(
                "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_MIN_SECONDS_BETWEEN_RUNS",
                DEFAULT_MIN_SECONDS_BETWEEN_RUNS,
                minimum=60.0,
                maximum=MAX_INTERVAL_SECONDS,
            ),
            busy_timeout_seconds=positive_float(
                "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_BUSY_TIMEOUT_SECONDS",
                DEFAULT_BUSY_TIMEOUT_SECONDS,
                minimum=0.01,
                maximum=MAX_BUSY_TIMEOUT_SECONDS,
            ),
            startup_grace_seconds=positive_float(
                "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_STARTUP_GRACE_SECONDS",
                DEFAULT_STARTUP_GRACE_SECONDS,
                minimum=1.0,
                maximum=3600.0,
            ),
            min_free_bytes=positive_int(
                "TRADE_EVIDENCE_INDEX_AUTO_MAINTENANCE_MIN_FREE_BYTES",
                DEFAULT_MIN_FREE_BYTES,
                maximum=1024 * 1024 * 1024 * 1024,
            ),
            history_source_path=root / "history_events.jsonl",
            history_index_path=history_index,
            timeline_source_path=root / "timeline.jsonl",
            timeline_index_path=timeline_index,
            lock_path=root / ".trade-evidence-index-auto-maintenance-v1.lock",
        )

    def source_specs(self) -> tuple[SourceSpec, SourceSpec]:
        return (
            SourceSpec(
                "history_manager",
                Path(self.history_source_path),
                Path(self.history_index_path),
            ),
            SourceSpec(
                "timeline",
                Path(self.timeline_source_path),
                Path(self.timeline_index_path),
            ),
        )


@dataclass(frozen=True)
class MaintenanceCheck:
    status: str
    validation_status: str
    source_size: int = 0
    safe_watermark: int = 0
    lag_bytes: int = 0
    generation_uuid: Optional[str] = None
    state: Optional[str] = None
    error_type: Optional[str] = None


def _new_source_telemetry() -> dict[str, Any]:
    return {
        "last_status": DISABLED,
        "last_check_at": None,
        "last_run_at": None,
        "last_success_at": None,
        "last_error_type": None,
        "source_size": 0,
        "safe_watermark_before": 0,
        "safe_watermark_after": 0,
        "lag_before": 0,
        "lag_after": 0,
        "lag_above_max": False,
        "processed_append_bytes": 0,
        "duration_seconds": 0.0,
        "verified_prefix_bytes": 0,
        "generation_uuid_masked": None,
        "last_validation_status": None,
        "run_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "skip_small_lag_count": 0,
        "lock_busy_count": 0,
    }


_STATE_LOCK = threading.RLock()
_THREAD_LOCK = threading.Lock()
_PROCESS_SINGLE_FLIGHT = threading.Lock()
_STOP_EVENT = threading.Event()
_THREAD: Optional[threading.Thread] = None
_LAST_RUN_EPOCH = {source: 0.0 for source in SOURCE_ORDER}
_TELEMETRY: dict[str, Any] = {
    "version": VERSION,
    "enabled": False,
    "thread_started": False,
    "last_check_at": None,
    "last_run_at": None,
    "last_success_at": None,
    "last_error_type": None,
    "last_status": DISABLED,
    "interval_seconds": DEFAULT_INTERVAL_SECONDS,
    "min_lag_bytes": DEFAULT_MIN_LAG_BYTES,
    "max_lag_bytes": DEFAULT_MAX_LAG_BYTES,
    "min_seconds_between_runs": DEFAULT_MIN_SECONDS_BETWEEN_RUNS,
    "startup_grace_seconds": DEFAULT_STARTUP_GRACE_SECONDS,
    "sources": {source: _new_source_telemetry() for source in SOURCE_ORDER},
}


def _utc_iso(epoch: Optional[float] = None) -> str:
    value = time.time() if epoch is None else float(epoch)
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _mask_generation(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def _apply_config(config: MaintenanceConfig) -> None:
    with _STATE_LOCK:
        _TELEMETRY.update({
            "enabled": bool(config.enabled),
            "interval_seconds": config.interval_seconds,
            "min_lag_bytes": config.min_lag_bytes,
            "max_lag_bytes": config.max_lag_bytes,
            "min_seconds_between_runs": config.min_seconds_between_runs,
            "startup_grace_seconds": config.startup_grace_seconds,
        })
        if not config.enabled:
            _TELEMETRY["last_status"] = DISABLED


def get_maintenance_telemetry_snapshot() -> dict[str, Any]:
    """Return a detached, bounded snapshot; never inspect source or index files."""

    with _STATE_LOCK:
        return copy.deepcopy(_TELEMETRY)


def reset_maintenance_telemetry_for_tests() -> None:
    """Reset process-local state for isolated tests; never used by the scheduler."""

    global _THREAD
    with _THREAD_LOCK:
        _THREAD = None
        _STOP_EVENT.clear()
    with _STATE_LOCK:
        _TELEMETRY.clear()
        _TELEMETRY.update({
            "version": VERSION,
            "enabled": False,
            "thread_started": False,
            "last_check_at": None,
            "last_run_at": None,
            "last_success_at": None,
            "last_error_type": None,
            "last_status": DISABLED,
            "interval_seconds": DEFAULT_INTERVAL_SECONDS,
            "min_lag_bytes": DEFAULT_MIN_LAG_BYTES,
            "max_lag_bytes": DEFAULT_MAX_LAG_BYTES,
            "min_seconds_between_runs": DEFAULT_MIN_SECONDS_BETWEEN_RUNS,
            "startup_grace_seconds": DEFAULT_STARTUP_GRACE_SECONDS,
            "sources": {source: _new_source_telemetry() for source in SOURCE_ORDER},
        })
        for source in SOURCE_ORDER:
            _LAST_RUN_EPOCH[source] = 0.0


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _regular_lstat(path: Path) -> os.stat_result:
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise OSError("path is not a regular non-symlink file")
    return value


def _read_range(handle: Any, offset: int, length: int) -> bytes:
    if offset < 0 or length < 0:
        raise ValueError("invalid anchor range")
    handle.seek(offset, os.SEEK_SET)
    value = handle.read(length)
    if len(value) != length:
        raise OSError("short anchor read")
    return value


def _blake128(value: bytes) -> bytes:
    return hashlib.blake2b(value, digest_size=HASH_BYTES).digest()


def inspect_maintenance_source(
    spec: SourceSpec,
    config: MaintenanceConfig,
) -> MaintenanceCheck:
    """Read one SQLite state row plus bounded source anchors, without writes."""

    index = Path(spec.index_path)
    source = Path(spec.source_path)
    if not index.exists():
        return MaintenanceCheck(INDEX_MISSING, INDEX_MISSING)
    connection: Optional[sqlite3.Connection] = None
    try:
        index_stat = _regular_lstat(index)
        source_stat = _regular_lstat(source)
        connection = sqlite3.connect(
            index.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=config.busy_timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute(
            f"PRAGMA busy_timeout={max(1, int(config.busy_timeout_seconds * 1000))}"
        )
        connection.execute("PRAGMA query_only=ON")
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        state = connection.execute(
            "SELECT * FROM source_state WHERE singleton_id=1"
        ).fetchone()
        if state is None:
            raise sqlite3.DatabaseError("source_state missing")
        state_name = str(state["state"])
        watermark = int(state["safe_watermark"])
        generation_uuid = str(state["generation_uuid"])
        source_size = int(source_stat.st_size)
        lag = max(0, source_size - watermark)
        common = {
            "source_size": source_size,
            "safe_watermark": watermark,
            "lag_bytes": lag,
            "generation_uuid": generation_uuid,
            "state": state_name,
        }
        if state_name != "READY":
            return MaintenanceCheck(SKIP_NOT_READY, INDEX_PARTIAL, **common)
        if (
            application_id != SQLITE_APPLICATION_ID
            or user_version != SCHEMA_VERSION
            or int(state["schema_version"]) != SCHEMA_VERSION
            or str(state["index_version"]) != INDEX_VERSION
            or str(state["builder_version"]) != BUILDER_VERSION
            or str(state["identity_contract_hash"]) != IDENTITY_CONTRACT_HASH
            or str(state["source_id"]) != spec.source_id
            or str(state["source_path"]) != _normalized_path(source)
            or str(state["normalized_path_hash"]) != normalized_path_hash(source)
            or str(int(source_stat.st_dev)) != str(state["dev"])
            or str(int(source_stat.st_ino)) != str(state["inode"])
            or watermark != int(state["build_snapshot_eof"])
            or source_size < watermark
        ):
            return MaintenanceCheck(SOURCE_CHANGED, INDEX_SOURCE_CHANGED, **common)
        try:
            if str(uuid.UUID(generation_uuid)) != generation_uuid:
                raise ValueError("non-canonical UUID")
            anchor_bytes = int(state["anchor_bytes"])
            if not 0 < anchor_bytes <= MAX_ANCHOR_BYTES:
                raise ValueError("anchor_bytes out of bounds")
            initial_eof = int(state["initial_snapshot_eof"])
            prefix_length = min(anchor_bytes, initial_eof)
            watermark_length = min(anchor_bytes, watermark)
            watermark_offset = watermark - watermark_length
            snapshot_length = min(anchor_bytes, watermark)
            snapshot_offset = watermark - snapshot_length
            if (
                int(state["prefix_anchor_length"]) != prefix_length
                or int(state["watermark_anchor_length"]) != watermark_length
                or int(state["watermark_anchor_offset"]) != watermark_offset
                or int(state["snapshot_tail_anchor_length"]) != snapshot_length
                or int(state["snapshot_tail_anchor_offset"]) != snapshot_offset
            ):
                raise ValueError("anchor metadata shape mismatch")
            with source.open("rb") as handle:
                descriptor_stat = os.fstat(handle.fileno())
                if (
                    int(descriptor_stat.st_dev) != int(source_stat.st_dev)
                    or int(descriptor_stat.st_ino) != int(source_stat.st_ino)
                    or int(descriptor_stat.st_size) < source_size
                ):
                    raise OSError("source changed before anchor read")
                prefix = _blake128(_read_range(handle, 0, prefix_length))
                watermark_anchor = _blake128(
                    _read_range(handle, watermark_offset, watermark_length)
                )
                snapshot_anchor = _blake128(
                    _read_range(handle, snapshot_offset, snapshot_length)
                )
                if watermark and _read_range(handle, watermark - 1, 1) != b"\n":
                    raise ValueError("watermark is not newline aligned")
            final_stat = _regular_lstat(source)
            final_index_stat = _regular_lstat(index)
            if (
                int(final_stat.st_dev) != int(source_stat.st_dev)
                or int(final_stat.st_ino) != int(source_stat.st_ino)
                or int(final_stat.st_size) < source_size
                or int(final_index_stat.st_dev) != int(index_stat.st_dev)
                or int(final_index_stat.st_ino) != int(index_stat.st_ino)
                or prefix != bytes(state["prefix_anchor"])
                or watermark_anchor != bytes(state["watermark_anchor"])
                or snapshot_anchor != bytes(state["snapshot_tail_anchor"])
            ):
                raise OSError("source anchor mismatch")
        except (OSError, TypeError, ValueError):
            return MaintenanceCheck(SOURCE_CHANGED, INDEX_SOURCE_CHANGED, **common)
        validation = INDEX_COMPLETE_FOR_SNAPSHOT if lag == 0 else INDEX_PARTIAL
        status_name = SKIP_SMALL_LAG if lag < config.min_lag_bytes else CATCH_UP_ELIGIBLE
        return MaintenanceCheck(status_name, validation, **common)
    except FileNotFoundError:
        return MaintenanceCheck(SOURCE_CHANGED, INDEX_SOURCE_CHANGED, error_type="FileNotFoundError")
    except (OSError, sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
        return MaintenanceCheck(
            SOURCE_CHANGED,
            INDEX_SOURCE_CHANGED,
            error_type=type(exc).__name__,
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except sqlite3.DatabaseError:
                pass


class _HeldMaintenanceLock:
    def __init__(self, handle: Any, backend: str):
        self.handle = handle
        self.backend = backend

    def __enter__(self) -> "_HeldMaintenanceLock":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self.backend == "fcntl":
                _fcntl.flock(self.handle.fileno(), _fcntl.LOCK_UN)
            elif self.backend == "msvcrt":
                self.handle.seek(0)
                _msvcrt.locking(self.handle.fileno(), _msvcrt.LK_UNLCK, 1)
        finally:
            try:
                self.handle.close()
            finally:
                _PROCESS_SINGLE_FLIGHT.release()


def acquire_maintenance_file_lock(path: Path) -> Optional[_HeldMaintenanceLock]:
    """Acquire one fail-closed global lock shared by both source catch-ups."""

    if not _PROCESS_SINGLE_FLIGHT.acquire(blocking=False):
        return None
    handle = None
    try:
        lock_path = Path(path)
        if not lock_path.parent.exists() or not lock_path.parent.is_dir():
            raise OSError("lock parent is unavailable")
        try:
            current = lock_path.lstat()
        except FileNotFoundError:
            current = None
        if current is not None:
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                raise OSError("lock path is unsafe")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(os.fspath(lock_path), flags, 0o600)
        handle = os.fdopen(descriptor, "r+b", buffering=0)
        if _fcntl is not None:
            _fcntl.flock(handle.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            backend = "fcntl"
        elif _msvcrt is not None:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
            handle.seek(0)
            _msvcrt.locking(handle.fileno(), _msvcrt.LK_NBLCK, 1)
            backend = "msvcrt"
        else:
            raise OSError("no supported file-lock backend")
        return _HeldMaintenanceLock(handle, backend)
    except (BlockingIOError, OSError):
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        _PROCESS_SINGLE_FLIGHT.release()
        return None


def _cooldown_epoch(spec: SourceSpec) -> float:
    local = _LAST_RUN_EPOCH.get(spec.source_id, 0.0)
    stamp = spec.cooldown_stamp_path
    try:
        value = stamp.lstat()
    except FileNotFoundError:
        return local
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise OSError("cooldown stamp is unsafe")
    return max(local, float(value.st_mtime))


def _touch_cooldown_stamp(spec: SourceSpec, epoch: float) -> None:
    stamp = spec.cooldown_stamp_path
    try:
        value = stamp.lstat()
    except FileNotFoundError:
        value = None
    if value is not None:
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
            raise OSError("cooldown stamp is unsafe")
    flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(os.fspath(stamp), flags, 0o600)
    os.close(descriptor)
    os.utime(stamp, (epoch, epoch))


def _record_check(
    spec: SourceSpec,
    config: MaintenanceConfig,
    check: MaintenanceCheck,
    now_epoch: float,
) -> None:
    with _STATE_LOCK:
        source = _TELEMETRY["sources"][spec.source_id]
        source.update({
            "last_status": check.status,
            "last_check_at": _utc_iso(now_epoch),
            "last_error_type": check.error_type,
            "source_size": check.source_size,
            "safe_watermark_before": check.safe_watermark,
            "safe_watermark_after": check.safe_watermark,
            "lag_before": check.lag_bytes,
            "lag_after": check.lag_bytes,
            "lag_above_max": check.lag_bytes >= config.max_lag_bytes,
            "generation_uuid_masked": _mask_generation(check.generation_uuid),
            "last_validation_status": check.validation_status,
        })
        if check.status == SKIP_SMALL_LAG:
            source["skip_small_lag_count"] += 1


def _set_source_status(
    source_id: str,
    status_name: str,
    *,
    error_type: Optional[str] = None,
) -> None:
    with _STATE_LOCK:
        source = _TELEMETRY["sources"][source_id]
        source["last_status"] = status_name
        source["last_error_type"] = error_type
        if status_name == LOCK_BUSY:
            source["lock_busy_count"] += 1
        if status_name == CATCH_UP_FAILED:
            source["failure_count"] += 1


def _run_one_source(
    spec: SourceSpec,
    config: MaintenanceConfig,
    *,
    now_fn: Callable[[], float],
    inspect_fn: Callable[[SourceSpec, MaintenanceConfig], MaintenanceCheck],
    catch_up_fn: Callable[..., Any],
    disk_usage_fn: Callable[[Path], Any],
    lock_factory: Callable[[Path], Optional[Any]],
) -> str:
    now_epoch = float(now_fn())
    check = inspect_fn(spec, config)
    _record_check(spec, config, check, now_epoch)
    if check.status != CATCH_UP_ELIGIBLE:
        return check.status
    try:
        last_run = _cooldown_epoch(spec)
    except OSError as exc:
        _set_source_status(spec.source_id, CATCH_UP_FAILED, error_type=type(exc).__name__)
        return CATCH_UP_FAILED
    if last_run and now_epoch - last_run < config.min_seconds_between_runs:
        _set_source_status(spec.source_id, COOLDOWN)
        return COOLDOWN

    held_lock = lock_factory(config.lock_path)
    if held_lock is None:
        _set_source_status(spec.source_id, LOCK_BUSY)
        return LOCK_BUSY
    with held_lock:
        # A different worker may have advanced W before this process acquired
        # the global lock.  Re-check before paying the O(W) prefix proof.
        now_epoch = float(now_fn())
        check = inspect_fn(spec, config)
        _record_check(spec, config, check, now_epoch)
        if check.status != CATCH_UP_ELIGIBLE:
            return check.status
        try:
            last_run = _cooldown_epoch(spec)
        except OSError as exc:
            _set_source_status(spec.source_id, CATCH_UP_FAILED, error_type=type(exc).__name__)
            return CATCH_UP_FAILED
        if last_run and now_epoch - last_run < config.min_seconds_between_runs:
            _set_source_status(spec.source_id, COOLDOWN)
            return COOLDOWN
        try:
            free_bytes = int(disk_usage_fn(spec.index_path.parent).free)
        except (OSError, TypeError, ValueError) as exc:
            _set_source_status(spec.source_id, LOW_DISK, error_type=type(exc).__name__)
            return LOW_DISK
        required_free = max(config.min_free_bytes, check.lag_bytes * 4)
        if free_bytes < required_free:
            _set_source_status(spec.source_id, LOW_DISK)
            return LOW_DISK

        with _STATE_LOCK:
            source = _TELEMETRY["sources"][spec.source_id]
            source["last_status"] = CATCH_UP_RUNNING
            source["last_run_at"] = _utc_iso(now_epoch)
            source["last_error_type"] = None
            source["run_count"] += 1
            _TELEMETRY["last_run_at"] = _utc_iso(now_epoch)
            _LAST_RUN_EPOCH[spec.source_id] = now_epoch
        try:
            report = catch_up_fn(
                spec.source_path,
                spec.index_path,
                spec.source_id,
                measure_memory=False,
            )
            partial = (
                str(report.final_validation_status) == INDEX_PARTIAL
                or int(report.remaining_lag_bytes) > 0
            )
            status_name = CATCH_UP_PARTIAL if partial else CATCH_UP_OK
            success_at = _utc_iso(float(now_fn()))
            with _STATE_LOCK:
                source = _TELEMETRY["sources"][spec.source_id]
                source.update({
                    "last_status": status_name,
                    "last_success_at": success_at,
                    "last_error_type": None,
                    "source_size": int(report.source_size_after),
                    "safe_watermark_before": int(report.safe_watermark_before),
                    "safe_watermark_after": int(report.safe_watermark_after),
                    "lag_before": max(
                        0,
                        int(report.source_size_before) - int(report.safe_watermark_before),
                    ),
                    "lag_after": int(report.remaining_lag_bytes),
                    "lag_above_max": int(report.remaining_lag_bytes) >= config.max_lag_bytes,
                    "processed_append_bytes": int(report.processed_append_bytes),
                    "duration_seconds": float(report.duration_seconds),
                    "verified_prefix_bytes": int(report.verified_prefix_bytes),
                    "generation_uuid_masked": _mask_generation(report.generation_uuid),
                    "last_validation_status": str(report.final_validation_status),
                })
                source["success_count"] += 1
                _TELEMETRY["last_success_at"] = success_at
            return status_name
        except Exception as exc:
            _set_source_status(
                spec.source_id,
                CATCH_UP_FAILED,
                error_type=type(exc).__name__,
            )
            return CATCH_UP_FAILED
        finally:
            try:
                _touch_cooldown_stamp(spec, now_epoch)
            except OSError:
                # The local cooldown still prevents a tight retry in this
                # process; stamp failure cannot undo a completed catch-up.
                pass


def run_maintenance_tick(
    config: Optional[MaintenanceConfig] = None,
    *,
    now_fn: Callable[[], float] = time.time,
    inspect_fn: Callable[[SourceSpec, MaintenanceConfig], MaintenanceCheck] = inspect_maintenance_source,
    catch_up_fn: Callable[..., Any] = catch_up_index,
    disk_usage_fn: Callable[[Path], Any] = shutil.disk_usage,
    lock_factory: Callable[[Path], Optional[Any]] = acquire_maintenance_file_lock,
) -> dict[str, Any]:
    """Run one serial History-then-Timeline maintenance decision cycle."""

    selected = config or MaintenanceConfig.from_environ()
    _apply_config(selected)
    if not selected.enabled:
        return get_maintenance_telemetry_snapshot()
    checked_at = _utc_iso(float(now_fn()))
    with _STATE_LOCK:
        _TELEMETRY["last_check_at"] = checked_at
        _TELEMETRY["last_error_type"] = None
    statuses: list[str] = []
    try:
        for spec in selected.source_specs():
            try:
                status_name = _run_one_source(
                    spec,
                    selected,
                    now_fn=now_fn,
                    inspect_fn=inspect_fn,
                    catch_up_fn=catch_up_fn,
                    disk_usage_fn=disk_usage_fn,
                    lock_factory=lock_factory,
                )
            except Exception as exc:
                _set_source_status(
                    spec.source_id,
                    CATCH_UP_FAILED,
                    error_type=type(exc).__name__,
                )
                status_name = CATCH_UP_FAILED
            statuses.append(status_name)
    except Exception as exc:
        statuses.append(CATCH_UP_FAILED)
        with _STATE_LOCK:
            _TELEMETRY["last_error_type"] = type(exc).__name__
    if CATCH_UP_FAILED in statuses:
        aggregate = CATCH_UP_FAILED
    elif CATCH_UP_PARTIAL in statuses:
        aggregate = CATCH_UP_PARTIAL
    elif CATCH_UP_OK in statuses:
        aggregate = CATCH_UP_OK
    elif SOURCE_CHANGED in statuses:
        aggregate = SOURCE_CHANGED
    elif LOW_DISK in statuses:
        aggregate = LOW_DISK
    elif LOCK_BUSY in statuses:
        aggregate = LOCK_BUSY
    elif COOLDOWN in statuses:
        aggregate = COOLDOWN
    elif SKIP_NOT_READY in statuses:
        aggregate = SKIP_NOT_READY
    elif INDEX_MISSING in statuses:
        aggregate = INDEX_MISSING
    else:
        aggregate = CHECKED_NO_ACTION
    with _STATE_LOCK:
        _TELEMETRY["last_status"] = aggregate
        if aggregate == CATCH_UP_FAILED and _TELEMETRY["last_error_type"] is None:
            failing = next(
                (
                    _TELEMETRY["sources"][source]["last_error_type"]
                    for source in SOURCE_ORDER
                    if _TELEMETRY["sources"][source]["last_error_type"]
                ),
                None,
            )
            _TELEMETRY["last_error_type"] = failing
    return get_maintenance_telemetry_snapshot()


def maintenance_loop(
    config: MaintenanceConfig,
    *,
    stop_event: threading.Event = _STOP_EVENT,
    tick_fn: Callable[[MaintenanceConfig], Any] = run_maintenance_tick,
) -> None:
    """Daemon target with startup grace and isolated, bounded retries."""

    if not config.enabled:
        return
    if stop_event.wait(config.startup_grace_seconds):
        return
    while not stop_event.is_set():
        try:
            tick_fn(config)
        except Exception as exc:
            with _STATE_LOCK:
                _TELEMETRY["last_status"] = CATCH_UP_FAILED
                _TELEMETRY["last_error_type"] = type(exc).__name__
        if stop_event.wait(config.interval_seconds):
            return


def start_auto_maintenance(
    *,
    environ: Optional[Mapping[str, str]] = None,
    data_dir: Optional[Path | str] = None,
    config: Optional[MaintenanceConfig] = None,
    thread_factory: Callable[..., threading.Thread] = threading.Thread,
) -> bool:
    """Start at most one daemon thread; return without I/O when disabled."""

    global _THREAD
    selected = config or MaintenanceConfig.from_environ(environ, data_dir=data_dir)
    _apply_config(selected)
    if not selected.enabled:
        with _STATE_LOCK:
            _TELEMETRY["thread_started"] = False
        return False
    with _THREAD_LOCK:
        if _THREAD is not None:
            with _STATE_LOCK:
                _TELEMETRY["thread_started"] = True
            return False
        try:
            thread = thread_factory(
                target=maintenance_loop,
                args=(selected,),
                name="trade-evidence-index-auto-maintenance-v1",
                daemon=True,
            )
            _THREAD = thread
            thread.start()
        except Exception as exc:
            _THREAD = None
            with _STATE_LOCK:
                _TELEMETRY["thread_started"] = False
                _TELEMETRY["last_status"] = CATCH_UP_FAILED
                _TELEMETRY["last_error_type"] = type(exc).__name__
            return False
        with _STATE_LOCK:
            _TELEMETRY["thread_started"] = True
            _TELEMETRY["last_status"] = IDLE
        return True


__all__ = (
    "CATCH_UP_ELIGIBLE",
    "CATCH_UP_FAILED",
    "CATCH_UP_OK",
    "CATCH_UP_PARTIAL",
    "CHECKED_NO_ACTION",
    "COOLDOWN",
    "DISABLED",
    "IDLE",
    "INDEX_MISSING",
    "LOCK_BUSY",
    "LOW_DISK",
    "MaintenanceCheck",
    "MaintenanceConfig",
    "SKIP_NOT_READY",
    "SKIP_SMALL_LAG",
    "SOURCE_CHANGED",
    "SourceSpec",
    "VERSION",
    "acquire_maintenance_file_lock",
    "get_maintenance_telemetry_snapshot",
    "inspect_maintenance_source",
    "maintenance_loop",
    "reset_maintenance_telemetry_for_tests",
    "run_maintenance_tick",
    "start_auto_maintenance",
)
