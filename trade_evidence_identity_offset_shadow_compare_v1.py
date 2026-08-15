"""Read-only Phase B shadow comparison for indexed trade evidence.

The legacy Trade Timeline reader remains the only authority.  This module is
called after a legacy ``EvidenceBundle`` has been built, operates exclusively
on request-local clones, and records bounded process-local telemetry.  It has
no builder, repair, migration, Registry, network, broker, or trading authority.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import json
import logging
import math
import os
import sqlite3
import stat
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterable, Mapping, Optional, Sequence

from trade_evidence_identity_contract import (
    IDENTITY_CONTRACT_HASH,
    IDENTITY_GROUPS,
    classify_identity,
    extract_identity_pairs,
)
from trade_evidence_identity_offset_index_v1 import (
    BUILDER_VERSION,
    INDEX_COMPLETE_FOR_SNAPSHOT,
    INDEX_CORRUPT,
    INDEX_MISSING,
    INDEX_PARTIAL,
    INDEX_SOURCE_CHANGED,
    INDEX_STALE,
    INDEX_VERSION,
    SCHEMA_VERSION,
    SQLITE_APPLICATION_ID,
    IndexedRecordMetadata,
    IndexValidationError,
    normalized_path_hash,
    read_and_verify_record,
)


VERSION = "2026-08-14-TRADE-EVIDENCE-IDENTITY-OFFSET-INDEX-V1-PHASE-B-SHADOW-COMPARE"
SHADOW_SOURCES = ("history_manager", "timeline")

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NOT_COMPARABLE = "NOT_COMPARABLE"
SHADOW_DISABLED = "SHADOW_DISABLED"
INDEX_UNAVAILABLE = "INDEX_UNAVAILABLE"

SEMANTIC_PARITY = "SEMANTIC_PARITY"
PHYSICAL_METADATA_PARITY = "PHYSICAL_METADATA_PARITY"

OFFSET_MISMATCH = "OFFSET_MISMATCH"
MISSING_INDEX_RECORD = "MISSING_INDEX_RECORD"
EXTRA_INDEX_RECORD = "EXTRA_INDEX_RECORD"
RECORD_HASH_MISMATCH = "RECORD_HASH_MISMATCH"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
EVENT_MISMATCH = "EVENT_MISMATCH"
ORDER_MISMATCH = "ORDER_MISMATCH"
PROMOTION_MISMATCH = "PROMOTION_MISMATCH"
DUPLICATE_MISMATCH = "DUPLICATE_MISMATCH"
CONFLICT_MISMATCH = "CONFLICT_MISMATCH"
CHRONOLOGY_MISMATCH = "CHRONOLOGY_MISMATCH"
SOURCE_METADATA_MISMATCH = "SOURCE_METADATA_MISMATCH"

MISMATCH_CATEGORIES = (
    OFFSET_MISMATCH,
    MISSING_INDEX_RECORD,
    EXTRA_INDEX_RECORD,
    RECORD_HASH_MISMATCH,
    IDENTITY_MISMATCH,
    EVENT_MISMATCH,
    ORDER_MISMATCH,
    PROMOTION_MISMATCH,
    DUPLICATE_MISMATCH,
    CONFLICT_MISMATCH,
    CHRONOLOGY_MISMATCH,
    SOURCE_METADATA_MISMATCH,
)

DEFAULT_SAMPLE_RATE = 1.0
DEFAULT_MAX_JOURNAL_BYTES = 8 * 1024 * 1024
DEFAULT_BUSY_TIMEOUT_MS = 50
DEFAULT_LOG_MIN_INTERVAL_SECONDS = 60.0
MAX_INDEX_QUERIES = 2_048
MAX_ANCHOR_BYTES = 1024 * 1024
JSONL_MAX_BYTES = 64 * 1024 * 1024
JSONL_BLOCK_BYTES = 64 * 1024

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_GROUP_TYPES = {
    group: tuple(sorted({key for key, candidate_group in IDENTITY_GROUPS.items() if candidate_group == group}))
    for group in frozenset(IDENTITY_GROUPS.values())
}


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUE_VALUES


def _parse_sample_rate(value: Any) -> float:
    if value in (None, ""):
        return DEFAULT_SAMPLE_RATE
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) and 0.0 <= parsed <= 1.0 else 0.0


def _parse_positive_int(value: Any, default: int, *, maximum: int) -> int:
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum)


@dataclass(frozen=True)
class ShadowConfig:
    enabled: bool = False
    compare_enabled: bool = False
    history_index_path: Optional[Path] = None
    timeline_index_path: Optional[Path] = None
    log_enabled: bool = True
    sample_rate: float = DEFAULT_SAMPLE_RATE
    max_journal_bytes: int = DEFAULT_MAX_JOURNAL_BYTES
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS

    @classmethod
    def from_environ(cls, environ: Optional[Mapping[str, str]] = None) -> "ShadowConfig":
        env = os.environ if environ is None else environ

        def optional_path(name: str) -> Optional[Path]:
            raw = str(env.get(name, "") or "").strip()
            return Path(raw) if raw else None

        return cls(
            enabled=_parse_bool(env.get("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED")),
            compare_enabled=_parse_bool(env.get("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED")),
            history_index_path=optional_path("TRADE_EVIDENCE_INDEX_HISTORY_PATH"),
            timeline_index_path=optional_path("TRADE_EVIDENCE_INDEX_TIMELINE_PATH"),
            log_enabled=_parse_bool(
                env.get("TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED"), default=True
            ),
            sample_rate=_parse_sample_rate(env.get("TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE")),
            max_journal_bytes=_parse_positive_int(
                env.get("TRADE_EVIDENCE_INDEX_SHADOW_MAX_JOURNAL_BYTES"),
                DEFAULT_MAX_JOURNAL_BYTES,
                maximum=JSONL_MAX_BYTES,
            ),
            busy_timeout_ms=_parse_positive_int(
                env.get("TRADE_EVIDENCE_INDEX_SHADOW_BUSY_TIMEOUT_MS"),
                DEFAULT_BUSY_TIMEOUT_MS,
                maximum=5_000,
            ),
        )

    @property
    def active(self) -> bool:
        return bool(self.enabled and self.compare_enabled)

    def index_path_for(self, source: str) -> Optional[Path]:
        if source == "history_manager":
            return self.history_index_path
        if source == "timeline":
            return self.timeline_index_path
        return None


def shadow_capture_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    """Cheap flag predicate used by the legacy reader before private capture."""

    env = os.environ if environ is None else environ
    return bool(
        _parse_bool(env.get("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED"))
        and _parse_bool(env.get("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED"))
    )


@dataclass(frozen=True)
class FactualRecord:
    start_offset: int
    byte_length: int
    record_hash: str
    record: Mapping[str, Any] = field(repr=False, compare=False)


@dataclass(frozen=True)
class ShadowMetrics:
    legacy_duration_ms: float = 0.0
    legacy_bytes_scanned: int = 0
    shadow_duration_ms: float = 0.0
    duration_overhead_percent: Optional[float] = None
    sqlite_lookup_ms: float = 0.0
    candidate_records: int = 0
    factual_records: int = 0
    factual_journal_bytes: int = 0
    tail_journal_bytes: int = 0
    anchor_journal_bytes: int = 0
    total_journal_bytes: int = 0


@dataclass(frozen=True)
class SourceComparison:
    source: str
    status: str
    index_status: str
    mode: str
    semantic_parity: str
    physical_metadata_parity: str
    mismatch_categories: tuple[str, ...]
    reasons: tuple[str, ...]
    legacy_count: int
    shadow_count: int
    shadow_offsets: tuple[int, ...]
    metrics: ShadowMetrics
    shadow_rows: tuple[Mapping[str, Any], ...] = field(default=(), repr=False, compare=False)
    shadow_context: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ShadowCompareReport:
    status: str
    semantic_parity: str
    physical_metadata_parity: str
    mismatch_categories: tuple[str, ...]
    sources: Mapping[str, SourceComparison]


class _ShadowUnavailable(RuntimeError):
    def __init__(self, index_status: str, reason: str, *, mode: str = "NONE"):
        super().__init__(reason)
        self.index_status = index_status
        self.reason = reason
        self.mode = mode


class _ShadowMismatch(RuntimeError):
    def __init__(self, category: str, reason: str):
        super().__init__(reason)
        self.category = category
        self.reason = reason


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _masked_trade_id(trade_id: Any) -> str:
    return hashlib.sha256(str(trade_id or "").encode("utf-8", errors="replace")).hexdigest()[:12]


def _new_source_telemetry() -> Dict[str, Any]:
    return {
        "shadow_requests": 0,
        "shadow_eligible": 0,
        "shadow_matches": 0,
        "shadow_mismatches": 0,
        "shadow_not_comparable": 0,
        "shadow_index_unavailable": 0,
        "shadow_last_status": SHADOW_DISABLED,
        "shadow_last_index_status": SHADOW_DISABLED,
        "shadow_last_at": None,
        "shadow_last_trade_id_masked": None,
        "shadow_last_source": None,
        "shadow_last_mismatch_category": None,
        "shadow_last_legacy_count": 0,
        "shadow_last_index_count": 0,
        "shadow_last_index_lookup_ms": 0.0,
        "shadow_last_legacy_duration_ms": 0.0,
        "shadow_last_duration_ms": 0.0,
        "shadow_last_duration_overhead_percent": None,
        "shadow_last_legacy_bytes_scanned": 0,
        "shadow_last_factual_journal_bytes": 0,
        "shadow_last_tail_journal_bytes": 0,
        "shadow_last_journal_bytes_read": 0,
        "shadow_total_index_journal_bytes_read": 0,
    }


_TELEMETRY_LOCK = threading.RLock()
_TELEMETRY: Dict[str, Any] = {
    "version": VERSION,
    "shadow_enabled": False,
    "shadow_compare_enabled": False,
    "sources": {source: _new_source_telemetry() for source in SHADOW_SOURCES},
}
_LAST_LOG_MONOTONIC = {source: 0.0 for source in SHADOW_SOURCES}


def get_shadow_telemetry_snapshot() -> Dict[str, Any]:
    """Return a detached, bounded, path-free diagnostic snapshot."""

    with _TELEMETRY_LOCK:
        return copy.deepcopy(_TELEMETRY)


def reset_shadow_telemetry() -> None:
    """Reset process-local counters; intended for isolated tests/diagnostics."""

    with _TELEMETRY_LOCK:
        _TELEMETRY.clear()
        _TELEMETRY.update({
            "version": VERSION,
            "shadow_enabled": False,
            "shadow_compare_enabled": False,
            "sources": {source: _new_source_telemetry() for source in SHADOW_SOURCES},
        })
        for source in SHADOW_SOURCES:
            _LAST_LOG_MONOTONIC[source] = 0.0


def _record_telemetry(
    result: SourceComparison,
    *,
    config: ShadowConfig,
    trade_id: str,
) -> None:
    with _TELEMETRY_LOCK:
        _TELEMETRY["shadow_enabled"] = bool(config.enabled)
        _TELEMETRY["shadow_compare_enabled"] = bool(config.compare_enabled)
        target = _TELEMETRY["sources"][result.source]
        target["shadow_requests"] += 1
        if result.status in {MATCH, MISMATCH}:
            target["shadow_eligible"] += 1
        if result.status == MATCH:
            target["shadow_matches"] += 1
        elif result.status == MISMATCH:
            target["shadow_mismatches"] += 1
        elif result.status == INDEX_UNAVAILABLE:
            target["shadow_index_unavailable"] += 1
        elif result.status == NOT_COMPARABLE:
            target["shadow_not_comparable"] += 1
        target.update({
            "shadow_last_status": result.status,
            "shadow_last_index_status": result.index_status,
            "shadow_last_at": _utc_now(),
            "shadow_last_trade_id_masked": _masked_trade_id(trade_id),
            "shadow_last_source": result.source,
            "shadow_last_mismatch_category": (
                result.mismatch_categories[0] if result.mismatch_categories else None
            ),
            "shadow_last_legacy_count": result.legacy_count,
            "shadow_last_index_count": result.shadow_count,
            "shadow_last_index_lookup_ms": result.metrics.sqlite_lookup_ms,
            "shadow_last_legacy_duration_ms": result.metrics.legacy_duration_ms,
            "shadow_last_duration_ms": result.metrics.shadow_duration_ms,
            "shadow_last_duration_overhead_percent": result.metrics.duration_overhead_percent,
            "shadow_last_legacy_bytes_scanned": result.metrics.legacy_bytes_scanned,
            "shadow_last_factual_journal_bytes": result.metrics.factual_journal_bytes,
            "shadow_last_tail_journal_bytes": result.metrics.tail_journal_bytes,
            "shadow_last_journal_bytes_read": result.metrics.total_journal_bytes,
        })
        target["shadow_total_index_journal_bytes_read"] += result.metrics.total_journal_bytes


def _sampled(
    trade_id: str,
    source: str,
    context: Any,
    sample_rate: float,
) -> bool:
    if sample_rate <= 0.0:
        return False
    if sample_rate >= 1.0:
        return True
    payload = json.dumps(
        {
            "trade_id": str(trade_id or ""),
            "source": source,
            "opened_at": getattr(context, "requested_opened_at", None),
            "opened_epoch": getattr(context, "requested_opened_epoch", None),
            "instance_id": getattr(context, "requested_instance_id", None),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    rank = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    return rank < int(sample_rate * (1 << 64))


def _path_fingerprint(path: Path) -> str:
    normalized = os.path.normcase(os.path.abspath(os.fspath(path)))
    return hashlib.sha256(normalized.encode("utf-8", errors="surrogatepass")).hexdigest()


def _blake128(value: bytes) -> bytes:
    return hashlib.blake2b(value, digest_size=16).digest()


def _regular_non_symlink(path: Path) -> os.stat_result:
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise _ShadowUnavailable(INDEX_CORRUPT, "INDEX_NOT_REGULAR_FILE")
    return value


class _PinnedReadSession:
    """One immutable SQLite snapshot plus one pinned factual source descriptor."""

    def __init__(
        self,
        source_path: Path,
        index_path: Path,
        source_id: str,
        capture: Mapping[str, Any],
        max_journal_bytes: int,
        busy_timeout_ms: int,
    ) -> None:
        self.source_path = source_path
        self.index_path = index_path
        self.source_id = source_id
        self.capture = capture
        self.max_journal_bytes = max_journal_bytes
        self.busy_timeout_ms = busy_timeout_ms
        self.connection: Optional[sqlite3.Connection] = None
        self.source_fd: Optional[BinaryIO] = None
        self.state: Dict[str, Any] = {}
        self.lookup_ms = 0.0
        self.anchor_bytes_read = 0
        self.factual_bytes_read = 0
        self.tail_bytes_read = 0
        self._other_bytes_read = 0
        self._source_open_stat: Optional[os.stat_result] = None

    @property
    def total_journal_bytes(self) -> int:
        return (
            self.anchor_bytes_read
            + self.factual_bytes_read
            + self.tail_bytes_read
            + self._other_bytes_read
        )

    def _reserve(self, length: int) -> None:
        if length < 0 or self.total_journal_bytes + length > self.max_journal_bytes:
            raise _ShadowUnavailable(INDEX_PARTIAL, "SHADOW_JOURNAL_BYTE_GUARD", mode="FALLBACK_REQUIRED")

    def _read_exact(self, offset: int, length: int, *, kind: str) -> bytes:
        if self.source_fd is None or offset < 0 or length < 0:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "INVALID_SOURCE_RANGE")
        self._reserve(length)
        self.source_fd.seek(offset, os.SEEK_SET)
        value = self.source_fd.read(length)
        if len(value) != length:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_SHORT_READ")
        if kind == "anchor":
            self.anchor_bytes_read += length
        elif kind == "tail":
            self.tail_bytes_read += length
        elif kind == "factual":
            self.factual_bytes_read += length
        else:
            self._other_bytes_read += length
        return value

    def _read_anchor_hash(self, offset: int, length: int) -> bytes:
        return _blake128(self._read_exact(offset, length, kind="anchor"))

    def __enter__(self) -> "_PinnedReadSession":
        if not self.index_path.exists():
            raise _ShadowUnavailable(INDEX_MISSING, "INDEX_FILE_MISSING")
        _regular_non_symlink(self.index_path)
        if Path(os.fspath(self.index_path) + "-wal").exists() or Path(
            os.fspath(self.index_path) + "-shm"
        ).exists():
            raise _ShadowUnavailable(INDEX_CORRUPT, "INDEX_SIDECAR_PRESENT")

        uri = self.index_path.resolve().as_uri() + "?mode=ro"
        try:
            self.connection = sqlite3.connect(
                uri,
                uri=True,
                isolation_level=None,
                timeout=max(0.001, self.busy_timeout_ms / 1000.0),
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute(f"PRAGMA busy_timeout={int(self.busy_timeout_ms)}")
            self.connection.execute("PRAGMA query_only=ON")
            self.connection.execute("BEGIN")
            self._validate_database_snapshot()
            self._open_and_validate_source()
        except _ShadowUnavailable:
            self.close()
            raise
        except sqlite3.OperationalError as exc:
            self.close()
            reason = "SQLITE_BUSY" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "SQLITE_OPEN_FAILED"
            raise _ShadowUnavailable(INDEX_CORRUPT, reason) from exc
        except (sqlite3.DatabaseError, OSError, ValueError, TypeError, KeyError) as exc:
            self.close()
            raise _ShadowUnavailable(INDEX_CORRUPT, "INDEX_VALIDATION_FAILED") from exc
        return self

    def _validate_database_snapshot(self) -> None:
        assert self.connection is not None
        required = {"source_state", "segments", "records", "identities", "postings"}
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required.issubset(tables):
            raise _ShadowUnavailable(INDEX_CORRUPT, "REQUIRED_TABLE_MISSING")
        application_id = int(self.connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        rows = self.connection.execute("SELECT * FROM source_state LIMIT 2").fetchall()
        if len(rows) != 1:
            raise _ShadowUnavailable(INDEX_CORRUPT, "SOURCE_STATE_INVALID")
        state = dict(rows[0])
        self.state = state
        if application_id != SQLITE_APPLICATION_ID or user_version != SCHEMA_VERSION:
            raise _ShadowUnavailable(INDEX_STALE, "SQLITE_VERSION_MISMATCH")
        if int(state["schema_version"]) != SCHEMA_VERSION or str(state["index_version"]) != INDEX_VERSION:
            raise _ShadowUnavailable(INDEX_STALE, "INDEX_VERSION_MISMATCH")
        if str(state["builder_version"]) != BUILDER_VERSION:
            raise _ShadowUnavailable(INDEX_STALE, "BUILDER_VERSION_MISMATCH")
        if str(state["identity_contract_hash"]) != IDENTITY_CONTRACT_HASH:
            raise _ShadowUnavailable(INDEX_STALE, "IDENTITY_CONTRACT_MISMATCH")
        if str(state["source_id"]) != self.source_id:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_ID_MISMATCH")
        source_state = str(state["state"])
        if source_state in {"BUILDING", "REVALIDATING"}:
            raise _ShadowUnavailable(INDEX_PARTIAL, f"STATE_{source_state}")
        if source_state == "STALE":
            raise _ShadowUnavailable(INDEX_STALE, "STATE_STALE")
        if source_state != "READY":
            raise _ShadowUnavailable(INDEX_CORRUPT, "STATE_CORRUPT")
        if (
            str(state["source_path"]) != os.path.normcase(os.path.abspath(os.fspath(self.source_path)))
            or str(state["normalized_path_hash"]) != normalized_path_hash(self.source_path)
        ):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_PATH_MISMATCH")
        watermark = int(state["safe_watermark"])
        build_eof = int(state["build_snapshot_eof"])
        initial_eof = int(state["initial_snapshot_eof"])
        anchor_bytes = int(state["anchor_bytes"])
        if (
            watermark < 0
            or watermark != build_eof
            or anchor_bytes <= 0
            or anchor_bytes > MAX_ANCHOR_BYTES
            or int(state["max_line_bytes"]) <= 0
            or int(state["max_line_bytes"]) > JSONL_MAX_BYTES
            or initial_eof < 0
            or build_eof < initial_eof
        ):
            raise _ShadowUnavailable(INDEX_CORRUPT, "SOURCE_STATE_INVARIANT")
        try:
            generation = str(uuid.UUID(str(state["generation_uuid"])))
        except (ValueError, TypeError, AttributeError) as exc:
            raise _ShadowUnavailable(INDEX_CORRUPT, "GENERATION_UUID_INVALID") from exc
        if generation != str(state["generation_uuid"]).lower():
            raise _ShadowUnavailable(INDEX_CORRUPT, "GENERATION_UUID_INVALID")
        expected_prefix_length = min(anchor_bytes, initial_eof)
        expected_watermark_length = min(anchor_bytes, watermark)
        expected_tail_length = min(anchor_bytes, build_eof)
        anchor_shapes = (
            int(state["prefix_anchor_length"]) == expected_prefix_length,
            int(state["watermark_anchor_length"]) == expected_watermark_length,
            int(state["watermark_anchor_offset"]) == watermark - expected_watermark_length,
            int(state["snapshot_tail_anchor_length"]) == expected_tail_length,
            int(state["snapshot_tail_anchor_offset"]) == build_eof - expected_tail_length,
            len(bytes(state["prefix_anchor"])) == 16,
            len(bytes(state["watermark_anchor"])) == 16,
            len(bytes(state["snapshot_tail_anchor"])) == 16,
        )
        if not all(anchor_shapes):
            raise _ShadowUnavailable(INDEX_CORRUPT, "ANCHOR_SHAPE_INVALID")
        first = self.connection.execute(
            "SELECT start_offset FROM segments ORDER BY start_offset LIMIT 1"
        ).fetchone()
        last = self.connection.execute(
            "SELECT end_offset FROM segments ORDER BY end_offset DESC LIMIT 1"
        ).fetchone()
        if watermark == 0:
            if first is not None or last is not None:
                raise _ShadowUnavailable(INDEX_CORRUPT, "SEGMENT_RANGE_MISMATCH")
        elif first is None or last is None or int(first[0]) != 0 or int(last[0]) != watermark:
            raise _ShadowUnavailable(INDEX_CORRUPT, "SEGMENT_RANGE_MISMATCH")

    def _open_and_validate_source(self) -> None:
        try:
            path_stat = self.source_path.lstat()
        except (FileNotFoundError, OSError) as exc:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_UNAVAILABLE") from exc
        if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_NOT_REGULAR_FILE")
        try:
            self.source_fd = self.source_path.open("rb")
        except (FileNotFoundError, OSError) as exc:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_UNAVAILABLE") from exc
        descriptor = os.fstat(self.source_fd.fileno())
        self._source_open_stat = descriptor
        if int(path_stat.st_dev) != int(descriptor.st_dev) or int(path_stat.st_ino) != int(descriptor.st_ino):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "LSTAT_FSTAT_MISMATCH")
        if (
            int(descriptor.st_dev) != int(self.capture.get("dev", -1))
            or int(descriptor.st_ino) != int(self.capture.get("ino", -1))
        ):
            raise _ShadowUnavailable(
                INDEX_SOURCE_CHANGED,
                "LEGACY_SOURCE_FILE_ID_CHANGED",
                mode="NOT_COMPARABLE",
            )
        if (
            str(int(descriptor.st_dev)) != str(self.state["dev"])
            or str(int(descriptor.st_ino)) != str(self.state["inode"])
        ):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_FILE_ID_MISMATCH")
        if str(self.capture.get("path_fingerprint") or "") != _path_fingerprint(self.source_path):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_PATH_FINGERPRINT_MISMATCH")
        snapshot_eof = int(self.capture.get("snapshot_eof", -1))
        page_start = int(self.capture.get("page_start", -1))
        page_end = int(self.capture.get("page_end", -1))
        if (
            bool(self.capture.get("source_changed"))
            or bool(self.capture.get("oversized"))
            or bool(self.capture.get("cursor_oversized"))
            or snapshot_eof < 0
            or page_start < 0
            or not page_start <= page_end <= snapshot_eof <= int(descriptor.st_size)
        ):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "LEGACY_WINDOW_NOT_STABLE", mode="NOT_COMPARABLE")
        captured_after_size = int(self.capture.get("descriptor_size_after_read", -1))
        captured_after_mtime = int(self.capture.get("descriptor_mtime_ns_after_read", -1))
        if int(descriptor.st_size) == captured_after_size and captured_after_mtime >= 0:
            if int(descriptor.st_mtime_ns) != captured_after_mtime:
                raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_CHANGED_AFTER_LEGACY")
        if str(int(descriptor.st_dev)) != str(self.state["dev"]) or str(int(descriptor.st_ino)) != str(self.state["inode"]):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "INDEX_SOURCE_ID_MISMATCH")
        if snapshot_eof > int(descriptor.st_size) or int(descriptor.st_size) < int(self.state["build_snapshot_eof"]):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_SHRINK")

        prefix_length = int(self.state["prefix_anchor_length"])
        watermark = int(self.state["safe_watermark"])
        watermark_length = int(self.state["watermark_anchor_length"])
        watermark_offset = int(self.state["watermark_anchor_offset"])
        tail_length = int(self.state["snapshot_tail_anchor_length"])
        tail_offset = int(self.state["snapshot_tail_anchor_offset"])
        if prefix_length > MAX_ANCHOR_BYTES or watermark_length > MAX_ANCHOR_BYTES or tail_length > MAX_ANCHOR_BYTES:
            raise _ShadowUnavailable(INDEX_CORRUPT, "ANCHOR_LENGTH_INVALID")
        if self._read_anchor_hash(0, prefix_length) != bytes(self.state["prefix_anchor"]):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "PREFIX_ANCHOR_MISMATCH")
        if self._read_anchor_hash(watermark_offset, watermark_length) != bytes(self.state["watermark_anchor"]):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "WATERMARK_ANCHOR_MISMATCH")
        if self._read_anchor_hash(tail_offset, tail_length) != bytes(self.state["snapshot_tail_anchor"]):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SNAPSHOT_TAIL_ANCHOR_MISMATCH")
        if watermark:
            if self._read_exact(watermark - 1, 1, kind="other") != b"\n":
                raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "WATERMARK_NOT_ALIGNED")
        if page_start:
            if self._read_exact(page_start - 1, 1, kind="other") != b"\n":
                raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "PAGE_START_NOT_ALIGNED")
        if page_end < snapshot_eof and page_end:
            if self._read_exact(page_end - 1, 1, kind="other") != b"\n":
                raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "PAGE_END_NOT_ALIGNED")

    def check_barrier(self, start: int, end: int) -> None:
        if self.connection is None or end <= start:
            return
        began = time.perf_counter()
        row = self.connection.execute(
            """
            SELECT 1 FROM segments
            WHERE start_offset < ? AND end_offset > ? AND has_oversized_barrier=1
            LIMIT 1
            """,
            (int(end), int(start)),
        ).fetchone()
        self.lookup_ms += (time.perf_counter() - began) * 1000.0
        if row is not None:
            raise _ShadowUnavailable(INDEX_PARTIAL, "OVERSIZED_BARRIER", mode="FALLBACK_REQUIRED")

    def open_candidate_cursor(
        self,
        identity_type: str,
        identity_value: str,
        start: int,
        end: int,
    ) -> sqlite3.Cursor:
        assert self.connection is not None
        began = time.perf_counter()
        cursor = self.connection.execute(
            """
            SELECT r.record_id, r.line_number, r.start_offset, r.byte_length,
                   r.terminator_length, r.event_type, r.event_epoch,
                   r.event_timestamp, r.writer_version, r.record_hash,
                   i.identity_type, i.identity_value, i.identity_group,
                   i.identity_class
            FROM identities i
            JOIN postings p ON p.identity_id=i.identity_id
            JOIN records r ON r.record_id=p.record_id
            WHERE i.identity_type=? AND i.identity_value=?
              AND p.start_offset>=? AND p.start_offset<?
              AND r.start_offset + r.byte_length <= ?
            ORDER BY p.start_offset, p.record_id
            """,
            (identity_type, identity_value, int(start), int(end), int(end)),
        )
        self.lookup_ms += (time.perf_counter() - began) * 1000.0
        return cursor

    def fetchone(self, cursor: sqlite3.Cursor) -> Optional[sqlite3.Row]:
        began = time.perf_counter()
        row = cursor.fetchone()
        self.lookup_ms += (time.perf_counter() - began) * 1000.0
        return row

    def metadata_from_row(self, row: sqlite3.Row) -> IndexedRecordMetadata:
        return IndexedRecordMetadata(
            record_id=int(row["record_id"]),
            line_number=int(row["line_number"]),
            start_offset=int(row["start_offset"]),
            byte_length=int(row["byte_length"]),
            terminator_length=int(row["terminator_length"]),
            event_type=str(row["event_type"]),
            writer_version=str(row["writer_version"]) if row["writer_version"] is not None else None,
            record_hash=bytes(row["record_hash"]),
            identity_type=str(row["identity_type"]),
            identity_value=str(row["identity_value"]),
            identity_group=str(row["identity_group"]),
            identity_class=str(row["identity_class"]),
            event_epoch=float(row["event_epoch"]) if row["event_epoch"] is not None else None,
            event_timestamp=str(row["event_timestamp"]) if row["event_timestamp"] is not None else None,
        )

    def read_factual(self, metadata: IndexedRecordMetadata) -> Mapping[str, Any]:
        assert self.source_fd is not None
        physical_bytes = metadata.byte_length + (1 if metadata.start_offset else 0)
        self._reserve(physical_bytes)
        # The verifier performs these reads even when it subsequently rejects
        # a boundary/hash/taxonomy.  Account before verification so failures do
        # not under-report factual I/O.
        self.factual_bytes_read += physical_bytes
        try:
            record = read_and_verify_record(self.source_fd, metadata)
        except IndexValidationError as exc:
            message = str(exc).lower()
            if "hash" in message:
                category = RECORD_HASH_MISMATCH
            elif "offset" in message or "boundary" in message or "range" in message:
                category = OFFSET_MISMATCH
            elif "identity" in message or "taxonomy" in message:
                category = IDENTITY_MISMATCH
            elif "event" in message or "timestamp" in message:
                category = EVENT_MISMATCH
            else:
                category = RECORD_HASH_MISMATCH
            raise _ShadowMismatch(category, "FACTUAL_RECORD_VALIDATION_FAILED") from exc
        return record

    def read_tail(self, start: int, end: int) -> bytes:
        return self._read_exact(start, end - start, kind="tail")

    def final_source_check(self) -> None:
        if self.source_fd is None or self._source_open_stat is None:
            return
        descriptor = os.fstat(self.source_fd.fileno())
        try:
            path_stat = self.source_path.lstat()
        except FileNotFoundError as exc:
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_REMOVED_DURING_SHADOW") from exc
        if (
            int(descriptor.st_dev) != int(path_stat.st_dev)
            or int(descriptor.st_ino) != int(path_stat.st_ino)
            or int(descriptor.st_dev) != int(self._source_open_stat.st_dev)
            or int(descriptor.st_ino) != int(self._source_open_stat.st_ino)
            or int(descriptor.st_size) < int(self.capture["snapshot_eof"])
        ):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_REPLACED_DURING_SHADOW")
        if (
            int(descriptor.st_size) == int(self._source_open_stat.st_size)
            and int(descriptor.st_mtime_ns) != int(self._source_open_stat.st_mtime_ns)
        ):
            raise _ShadowUnavailable(INDEX_SOURCE_CHANGED, "SOURCE_MUTATED_DURING_SHADOW")

    def close(self) -> None:
        try:
            if self.source_fd is not None:
                self.source_fd.close()
        finally:
            self.source_fd = None
            if self.connection is not None:
                try:
                    self.connection.close()
                finally:
                    self.connection = None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


def _record_fingerprint(record: Mapping[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _context_projection(context: Any) -> Mapping[str, Any]:
    return {
        "trade_id": str(getattr(context, "trade_id", "")),
        "trusted": {
            str(key): tuple(sorted(str(value) for value in values))
            for key, values in sorted(getattr(context, "trusted", {}).items())
            if values
        },
        "trusted_typed": {
            str(key): tuple(sorted(str(value) for value in values))
            for key, values in sorted(getattr(context, "trusted_typed", {}).items())
            if values
        },
        "profile": dict(getattr(context, "profile", {})),
        "opened_epoch": getattr(context, "opened_epoch", None),
        "closed_epoch": getattr(context, "closed_epoch", None),
        "registry_anchored": bool(getattr(context, "registry_anchored", False)),
        "identity_ambiguous": bool(getattr(context, "identity_ambiguous", False)),
        "requested_opened_at": getattr(context, "requested_opened_at", None),
        "requested_opened_epoch": getattr(context, "requested_opened_epoch", None),
        "requested_instance_id": getattr(context, "requested_instance_id", None),
    }


def _events_for_source(component: str, rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    import trade_timeline_validator as validator

    events: list[Dict[str, Any]] = []
    for row in rows:
        events.extend(validator._events_from_record(component, row))
    events = validator._deduplicate_extracted(events)
    events.sort(
        key=lambda item: (
            item.get("epoch") is None,
            item.get("epoch") or 0.0,
            validator.EVENT_ORDER.index(item["event"])
            if item["event"] in validator.EVENT_ORDER
            else 999,
        )
    )
    return events


def _conflicting_event_groups(events: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, str], ...]:
    grouped: Dict[tuple[str, str], set[tuple[Any, ...]]] = {}
    for item in events:
        key = (str(item.get("component") or ""), str(item.get("event") or ""))
        grouped.setdefault(key, set()).add(
            (
                item.get("event_id"),
                item.get("timestamp"),
                item.get("fact_order_id"),
                tuple(item.get("identifiers") or ()),
            )
        )
    return tuple(sorted(key for key, values in grouped.items() if len(values) > 1))


def compare_source_semantics(
    component: str,
    legacy_rows: Sequence[Mapping[str, Any]],
    shadow_rows: Sequence[Mapping[str, Any]],
    *,
    legacy_context: Any = None,
    shadow_context: Any = None,
    legacy_offsets: Optional[Sequence[int]] = None,
    shadow_offsets: Optional[Sequence[int]] = None,
) -> tuple[str, ...]:
    """Compare source semantics without inventing unavailable physical parity."""

    import trade_timeline_validator as validator

    categories: set[str] = set()
    legacy_fingerprints = [_record_fingerprint(row) for row in legacy_rows]
    shadow_fingerprints = [_record_fingerprint(row) for row in shadow_rows]
    if legacy_offsets is not None and shadow_offsets is not None:
        if tuple(int(value) for value in legacy_offsets) != tuple(int(value) for value in shadow_offsets):
            categories.add(OFFSET_MISMATCH)
    if legacy_fingerprints != shadow_fingerprints:
        legacy_counts = Counter(legacy_fingerprints)
        shadow_counts = Counter(shadow_fingerprints)
        if legacy_counts - shadow_counts:
            categories.add(MISSING_INDEX_RECORD)
        if shadow_counts - legacy_counts:
            categories.add(EXTRA_INDEX_RECORD)
        if legacy_counts == shadow_counts:
            categories.add(ORDER_MISMATCH)
        legacy_identities = [extract_identity_pairs(row) for row in legacy_rows]
        shadow_identities = [extract_identity_pairs(row) for row in shadow_rows]
        if legacy_identities != shadow_identities:
            categories.add(IDENTITY_MISMATCH)
    legacy_events = _events_for_source(component, legacy_rows)
    shadow_events = _events_for_source(component, shadow_rows)
    if legacy_events != shadow_events:
        categories.add(EVENT_MISMATCH)
        legacy_event_multiset = Counter(_record_fingerprint(item) for item in legacy_events)
        shadow_event_multiset = Counter(_record_fingerprint(item) for item in shadow_events)
        if legacy_event_multiset == shadow_event_multiset:
            categories.add(ORDER_MISMATCH)
    if validator._duplicates(list(legacy_events)) != validator._duplicates(list(shadow_events)):
        categories.add(DUPLICATE_MISMATCH)
    if _conflicting_event_groups(legacy_events) != _conflicting_event_groups(shadow_events):
        categories.add(CONFLICT_MISMATCH)
    if validator._chronology(list(legacy_events)) != validator._chronology(list(shadow_events)):
        categories.add(CHRONOLOGY_MISMATCH)
    if legacy_context is not None and shadow_context is not None:
        if _context_projection(legacy_context) != _context_projection(shadow_context):
            categories.add(PROMOTION_MISMATCH)
    return tuple(category for category in MISMATCH_CATEGORIES if category in categories)


def _known_group_values(context: Any) -> set[tuple[str, str]]:
    return {
        (str(group), str(value))
        for group, values in getattr(context, "trusted", {}).items()
        for value in values
        if str(value)
    }


def _iter_tail_lines(raw: bytes, absolute_start: int) -> Iterable[tuple[int, bytes]]:
    cursor = 0
    while cursor < len(raw):
        newline = raw.find(b"\n", cursor)
        if newline < 0:
            yield absolute_start + cursor, raw[cursor:]
            return
        yield absolute_start + cursor, raw[cursor : newline + 1]
        cursor = newline + 1


def _parse_tail_mapping(raw_line: bytes) -> Optional[Mapping[str, Any]]:
    payload = raw_line[:-1] if raw_line.endswith(b"\n") else raw_line
    if not payload.strip():
        return None
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _retrieve_indexed_records(
    session: _PinnedReadSession,
    component: str,
    context: Any,
    start: int,
    end: int,
) -> tuple[list[Mapping[str, Any]], list[FactualRecord], int]:
    import trade_timeline_validator as validator

    if end <= start:
        return [], [], 0
    heap: list[tuple[int, int, sqlite3.Cursor, sqlite3.Row]] = []
    scheduled: Dict[tuple[str, str], int] = {}
    serial = 0
    query_count = 0

    def schedule(group: str, value: str, after: int) -> None:
        nonlocal serial, query_count
        for identity_type in _GROUP_TYPES.get(group, ()):
            if classify_identity(identity_type, value) is None:
                continue
            key = (identity_type, value)
            previous = scheduled.get(key)
            if previous is not None and previous <= after:
                continue
            if query_count >= MAX_INDEX_QUERIES:
                raise _ShadowUnavailable(INDEX_PARTIAL, "IDENTITY_QUERY_GUARD", mode="FALLBACK_REQUIRED")
            scheduled[key] = after
            query_count += 1
            cursor = session.open_candidate_cursor(identity_type, value, max(start, after), end)
            row = session.fetchone(cursor)
            if row is not None:
                serial += 1
                heapq.heappush(heap, (int(row["start_offset"]), serial, cursor, row))

    for group, value in sorted(_known_group_values(context)):
        schedule(group, value, start)

    matched_rows: list[Mapping[str, Any]] = []
    factual_records: list[FactualRecord] = []
    seen_offsets: set[int] = set()
    candidates = 0
    while heap:
        offset, _, cursor, row = heapq.heappop(heap)
        next_row = session.fetchone(cursor)
        if next_row is not None:
            serial += 1
            heapq.heappush(heap, (int(next_row["start_offset"]), serial, cursor, next_row))
        if offset in seen_offsets:
            continue
        seen_offsets.add(offset)
        candidates += 1
        metadata = session.metadata_from_row(row)
        if metadata.start_offset < start or metadata.start_offset + metadata.byte_length > end:
            raise _ShadowMismatch(OFFSET_MISMATCH, "INDEX_RECORD_OUTSIDE_WINDOW")
        record = session.read_factual(metadata)
        before = _known_group_values(context)
        selected = validator.correlate_source_records(component, (record,), context)
        if not selected:
            continue
        matched_rows.extend(selected)
        factual_records.append(
            FactualRecord(
                start_offset=metadata.start_offset,
                byte_length=metadata.byte_length,
                record_hash=metadata.record_hash.hex(),
                record=record,
            )
        )
        for group, value in sorted(_known_group_values(context) - before):
            schedule(group, value, metadata.start_offset + 1)
    return matched_rows, factual_records, candidates


def _retrieve_tail_records(
    session: _PinnedReadSession,
    component: str,
    context: Any,
    start: int,
    end: int,
) -> tuple[list[Mapping[str, Any]], list[FactualRecord], int]:
    import trade_timeline_validator as validator

    if end <= start:
        return [], [], 0
    raw = session.read_tail(start, end)
    matched_rows: list[Mapping[str, Any]] = []
    factual: list[FactualRecord] = []
    examined = 0
    for offset, raw_line in _iter_tail_lines(raw, start):
        if len(raw_line) > JSONL_MAX_BYTES:
            raise _ShadowUnavailable(INDEX_PARTIAL, "OVERSIZED_BARRIER", mode="FALLBACK_REQUIRED")
        record = _parse_tail_mapping(raw_line)
        if record is None:
            continue
        examined += 1
        selected = validator.correlate_source_records(component, (record,), context)
        if not selected:
            continue
        matched_rows.extend(selected)
        factual.append(
            FactualRecord(
                start_offset=offset,
                byte_length=len(raw_line),
                record_hash=_blake128(raw_line).hex(),
                record=record,
            )
        )
    return matched_rows, factual, examined


def _empty_result(
    source: str,
    status: str,
    index_status: str,
    reason: str,
    legacy_count: int,
    *,
    mode: str = "NONE",
    metrics: Optional[ShadowMetrics] = None,
    categories: Sequence[str] = (),
) -> SourceComparison:
    return SourceComparison(
        source=source,
        status=status,
        index_status=index_status,
        mode=mode,
        semantic_parity=NOT_COMPARABLE if status not in {MATCH, MISMATCH} else (
            SEMANTIC_PARITY if status == MATCH else MISMATCH
        ),
        physical_metadata_parity=NOT_COMPARABLE,
        mismatch_categories=tuple(categories),
        reasons=(reason,),
        legacy_count=legacy_count,
        shadow_count=0,
        shadow_offsets=(),
        metrics=metrics or ShadowMetrics(),
    )


_WINDOW_NOT_COMPARABLE_REASONS = frozenset({
    "LEGACY_SOURCE_FILE_ID_CHANGED",
    "SOURCE_PATH_FINGERPRINT_MISMATCH",
    "LEGACY_WINDOW_NOT_STABLE",
    "SOURCE_CHANGED_AFTER_LEGACY",
    "SOURCE_UNAVAILABLE",
    "SOURCE_NOT_REGULAR_FILE",
    "LSTAT_FSTAT_MISMATCH",
    "SOURCE_SHRINK",
    "PREFIX_ANCHOR_MISMATCH",
    "WATERMARK_ANCHOR_MISMATCH",
    "SNAPSHOT_TAIL_ANCHOR_MISMATCH",
    "WATERMARK_NOT_ALIGNED",
    "PAGE_START_NOT_ALIGNED",
    "PAGE_END_NOT_ALIGNED",
    "SOURCE_REMOVED_DURING_SHADOW",
    "SOURCE_REPLACED_DURING_SHADOW",
    "SOURCE_MUTATED_DURING_SHADOW",
})


def _run_source_compare(
    bundle: Any,
    source: str,
    source_path: Path,
    index_path: Optional[Path],
    config: ShadowConfig,
) -> SourceComparison:
    shadow_started = time.perf_counter()
    legacy_rows = tuple(bundle.records.get(source, ()))
    raw_source = bundle.raw_sources.get(source)
    capture = raw_source.get("_shadow_index_capture") if isinstance(raw_source, Mapping) else None
    if not isinstance(capture, Mapping) or capture.get("component") != source:
        return _empty_result(source, NOT_COMPARABLE, NOT_COMPARABLE, "LEGACY_CAPTURE_UNAVAILABLE", len(legacy_rows))
    context_before = capture.get("context_before")
    context_after = capture.get("context_after")
    windows = capture.get("physical_windows")
    if context_before is None or context_after is None or not isinstance(windows, (tuple, list)) or len(windows) != 1:
        return _empty_result(source, NOT_COMPARABLE, NOT_COMPARABLE, "LEGACY_CAPTURE_INVALID", len(legacy_rows))
    if bool(getattr(context_before, "identity_ambiguous", False)) and not bool(
        getattr(context_before, "registry_anchored", False)
    ):
        return _empty_result(source, NOT_COMPARABLE, "IDENTITY_AMBIGUOUS", "IDENTITY_AMBIGUOUS", len(legacy_rows))
    if (
        (
            getattr(context_before, "requested_opened_at", None)
            or getattr(context_before, "requested_opened_epoch", None) is not None
            or getattr(context_before, "requested_instance_id", None)
        )
        and not bool(getattr(context_before, "registry_anchored", False))
    ):
        return _empty_result(source, NOT_COMPARABLE, "IDENTITY_AMBIGUOUS", "SELECTOR_NOT_RESOLVED", len(legacy_rows))
    if not _sampled(bundle.trade_id, source, context_before, config.sample_rate):
        return _empty_result(source, SHADOW_DISABLED, SHADOW_DISABLED, "SAMPLE_NOT_SELECTED", len(legacy_rows))
    if index_path is None:
        return _empty_result(source, INDEX_UNAVAILABLE, INDEX_MISSING, "INDEX_PATH_NOT_CONFIGURED", len(legacy_rows))

    session: Optional[_PinnedReadSession] = None

    def current_metrics(*, candidates: int = 0, factual_records: int = 0) -> ShadowMetrics:
        metrics = ShadowMetrics(
            legacy_duration_ms=float(capture.get("legacy_duration_ms", 0.0) or 0.0),
            legacy_bytes_scanned=int(capture.get("legacy_bytes_scanned", 0) or 0),
            shadow_duration_ms=round((time.perf_counter() - shadow_started) * 1000.0, 6),
            sqlite_lookup_ms=round(session.lookup_ms, 6) if session else 0.0,
            candidate_records=candidates,
            factual_records=factual_records,
            factual_journal_bytes=session.factual_bytes_read if session else 0,
            tail_journal_bytes=session.tail_bytes_read if session else 0,
            anchor_journal_bytes=session.anchor_bytes_read if session else 0,
            total_journal_bytes=session.total_journal_bytes if session else 0,
        )
        if metrics.legacy_duration_ms > 0:
            metrics = replace(
                metrics,
                duration_overhead_percent=round(
                    metrics.shadow_duration_ms / metrics.legacy_duration_ms * 100.0,
                    6,
                ),
            )
        return metrics

    try:
        trial_context = copy.deepcopy(context_before)
        capture_window = dict(windows[0])
        session = _PinnedReadSession(
            source_path,
            index_path,
            source,
            capture_window,
            config.max_journal_bytes,
            config.busy_timeout_ms,
        )
        with session:
            page_start = int(capture_window["page_start"])
            page_end = int(capture_window["page_end"])
            watermark = int(session.state["safe_watermark"])
            indexed_end = min(page_end, watermark)
            tail_start = max(page_start, watermark)
            mode = "INDEX_ONLY" if watermark >= page_end else "INDEX_PLUS_TAIL"
            session.check_barrier(page_start, indexed_end)
            indexed_rows, indexed_factual, indexed_candidates = _retrieve_indexed_records(
                session,
                source,
                trial_context,
                page_start,
                indexed_end,
            )
            tail_rows, tail_factual, tail_candidates = _retrieve_tail_records(
                session,
                source,
                trial_context,
                tail_start,
                page_end,
            )
            session.final_source_check()
            shadow_rows = tuple((*indexed_rows, *tail_rows))
            factual = tuple((*indexed_factual, *tail_factual))
            categories = compare_source_semantics(
                source,
                legacy_rows,
                shadow_rows,
                legacy_context=context_after,
                shadow_context=trial_context,
                shadow_offsets=tuple(item.start_offset for item in factual),
            )
            legacy_evidence_found = bool(
                (bundle.source_coverage.get(source) or {}).get(
                    "evidence_found", bool(legacy_rows)
                )
            )
            if legacy_evidence_found != bool(shadow_rows):
                categories = tuple(
                    category
                    for category in MISMATCH_CATEGORIES
                    if category in set(categories) | {SOURCE_METADATA_MISMATCH}
                )
            legacy_source_status = str(
                (bundle.component_status.get(source) or {}).get("status") or ""
            )
            shadow_source_status = "AVAILABLE" if shadow_rows else "NO_EVIDENCE"
            if (
                legacy_source_status in {"AVAILABLE", "NO_EVIDENCE"}
                and legacy_source_status != shadow_source_status
            ):
                categories = tuple(
                    category
                    for category in MISMATCH_CATEGORIES
                    if category in set(categories) | {SOURCE_METADATA_MISMATCH}
                )
            metrics = current_metrics(
                candidates=indexed_candidates + tail_candidates,
                factual_records=len(factual),
            )
            return SourceComparison(
                source=source,
                status=MISMATCH if categories else MATCH,
                index_status=(INDEX_COMPLETE_FOR_SNAPSHOT if mode == "INDEX_ONLY" else INDEX_PARTIAL),
                mode=mode,
                semantic_parity=MISMATCH if categories else SEMANTIC_PARITY,
                physical_metadata_parity=NOT_COMPARABLE,
                mismatch_categories=categories,
                reasons=(),
                legacy_count=len(legacy_rows),
                shadow_count=len(shadow_rows),
                shadow_offsets=tuple(item.start_offset for item in factual),
                metrics=metrics,
                shadow_rows=shadow_rows,
                shadow_context=trial_context,
            )
    except _ShadowMismatch as exc:
        metrics = current_metrics()
        return _empty_result(
            source,
            MISMATCH,
            INDEX_CORRUPT,
            exc.reason,
            len(legacy_rows),
            mode="ABORTED",
            metrics=metrics,
            categories=(exc.category,),
        )
    except _ShadowUnavailable as exc:
        metrics = current_metrics()
        window_not_comparable = bool(
            exc.mode == "NOT_COMPARABLE"
            or exc.reason in _WINDOW_NOT_COMPARABLE_REASONS
        )
        top_status = INDEX_UNAVAILABLE if exc.index_status in {
            INDEX_MISSING,
            INDEX_STALE,
            INDEX_SOURCE_CHANGED,
            INDEX_CORRUPT,
        } and not window_not_comparable else NOT_COMPARABLE
        return _empty_result(
            source,
            top_status,
            exc.index_status,
            exc.reason,
            len(legacy_rows),
            mode="NOT_COMPARABLE" if window_not_comparable else exc.mode,
            metrics=metrics,
        )
    except sqlite3.OperationalError as exc:
        reason = "SQLITE_BUSY" if "locked" in str(exc).lower() or "busy" in str(exc).lower() else "SQLITE_ERROR"
        return _empty_result(
            source,
            INDEX_UNAVAILABLE,
            INDEX_CORRUPT,
            reason,
            len(legacy_rows),
            metrics=current_metrics(),
        )
    except (sqlite3.DatabaseError, OSError, ValueError, TypeError, KeyError):
        return _empty_result(
            source,
            INDEX_UNAVAILABLE,
            INDEX_CORRUPT,
            "SHADOW_SOURCE_ERROR",
            len(legacy_rows),
            metrics=current_metrics(),
        )


def _all_events(records: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[Mapping[str, Any]]:
    import trade_timeline_validator as validator

    events: list[Dict[str, Any]] = []
    for component in validator.COMPONENTS:
        for record in records.get(component, ()):
            events.extend(validator._events_from_record(component, record))
    events = validator._deduplicate_extracted(events)
    events.sort(
        key=lambda item: (
            item.get("epoch") is None,
            item.get("epoch") or 0.0,
            validator.EVENT_ORDER.index(item["event"])
            if item["event"] in validator.EVENT_ORDER
            else 999,
        )
    )
    return events


def _aggregate_categories(bundle: Any, results: Mapping[str, SourceComparison]) -> tuple[str, ...]:
    import trade_timeline_validator as validator

    categories: set[str] = {
        category
        for result in results.values()
        for category in result.mismatch_categories
    }
    shadow_records = {
        component: tuple(bundle.records.get(component, ()))
        for component in validator.COMPONENTS
    }
    for source, result in results.items():
        if result.status in {MATCH, MISMATCH}:
            shadow_records[source] = result.shadow_rows
    legacy_events = list(bundle.events)
    shadow_events = _all_events(shadow_records)
    if legacy_events != shadow_events:
        categories.add(EVENT_MISMATCH)
        if Counter(_record_fingerprint(item) for item in legacy_events) == Counter(
            _record_fingerprint(item) for item in shadow_events
        ):
            categories.add(ORDER_MISMATCH)
    if validator._duplicates(legacy_events) != validator._duplicates(shadow_events):
        categories.add(DUPLICATE_MISMATCH)
    if _conflicting_event_groups(legacy_events) != _conflicting_event_groups(shadow_events):
        categories.add(CONFLICT_MISMATCH)
    if validator._chronology(legacy_events) != validator._chronology(shadow_events):
        categories.add(CHRONOLOGY_MISMATCH)
    legacy_facts = {
        name: validator._facts(list(bundle.records.get(name, ())), name)
        for name in validator.COMPONENTS
    }
    shadow_facts = {
        name: validator._facts(list(shadow_records.get(name, ())), name)
        for name in validator.COMPONENTS
    }
    legacy_conflicts = validator._compare("registry", "broker", legacy_facts) + validator._compare(
        "lifecycle", "shadow_runtime", legacy_facts
    )
    shadow_conflicts = validator._compare("registry", "broker", shadow_facts) + validator._compare(
        "lifecycle", "shadow_runtime", shadow_facts
    )
    if legacy_conflicts != shadow_conflicts:
        categories.add(CONFLICT_MISMATCH)
    return tuple(category for category in MISMATCH_CATEGORIES if category in categories)


def _maybe_log(
    logger: logging.Logger,
    result: SourceComparison,
    trade_id: str,
    config: ShadowConfig,
) -> None:
    if not config.log_enabled or result.status not in {MISMATCH, INDEX_UNAVAILABLE}:
        return
    now = time.monotonic()
    with _TELEMETRY_LOCK:
        if now - _LAST_LOG_MONOTONIC[result.source] < DEFAULT_LOG_MIN_INTERVAL_SECONDS:
            return
        _LAST_LOG_MONOTONIC[result.source] = now
    payload = {
        "event": "TRADE_EVIDENCE_INDEX_SHADOW_COMPARE",
        "module": "trade_evidence_identity_offset_shadow_compare_v1",
        "version": VERSION,
        "source": result.source,
        "status": result.status,
        "index_status": result.index_status,
        "mismatch_category": result.mismatch_categories[0] if result.mismatch_categories else None,
        "trade_id_masked": _masked_trade_id(trade_id),
        "legacy_count": result.legacy_count,
        "index_count": result.shadow_count,
    }
    logger.warning(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def observe_evidence_bundle(
    bundle: Any,
    *,
    environ: Optional[Mapping[str, str]] = None,
    logger: Optional[logging.Logger] = None,
    config: Optional[ShadowConfig] = None,
) -> ShadowCompareReport:
    """Run fail-safe shadow comparison and return internal diagnostics only."""

    import trade_timeline_validator as validator

    try:
        selected_config = config or ShadowConfig.from_environ(environ)
    except Exception:
        selected_config = ShadowConfig()
    active_logger = logger or logging.getLogger(__name__)
    results: Dict[str, SourceComparison] = {}
    try:
        configured_sources = validator.default_source_paths(environ)
    except Exception:
        configured_sources = {}
    for source in SHADOW_SOURCES:
        legacy_count = len(bundle.records.get(source, ()))
        if not selected_config.active:
            result = _empty_result(
                source,
                SHADOW_DISABLED,
                SHADOW_DISABLED,
                "SHADOW_DISABLED",
                legacy_count,
            )
        else:
            try:
                result = _run_source_compare(
                    bundle,
                    source,
                    Path(configured_sources[source][0]),
                    selected_config.index_path_for(source),
                    selected_config,
                )
            except Exception:
                result = _empty_result(
                    source,
                    INDEX_UNAVAILABLE,
                    INDEX_CORRUPT,
                    "SHADOW_EXCEPTION_ISOLATED",
                    legacy_count,
                )
        results[source] = result

    try:
        aggregate_categories = _aggregate_categories(bundle, results)
    except Exception:
        aggregate_categories = tuple(
            category
            for category in MISMATCH_CATEGORIES
            if any(category in result.mismatch_categories for result in results.values())
        )
    for result in results.values():
        try:
            _record_telemetry(result, config=selected_config, trade_id=bundle.trade_id)
        except Exception:
            pass
        try:
            _maybe_log(active_logger, result, bundle.trade_id, selected_config)
        except Exception:
            pass
    statuses = {result.status for result in results.values()}
    if MISMATCH in statuses:
        status = MISMATCH
    elif statuses == {MATCH}:
        status = MATCH
    elif statuses == {SHADOW_DISABLED}:
        status = SHADOW_DISABLED
    elif INDEX_UNAVAILABLE in statuses:
        status = INDEX_UNAVAILABLE
    else:
        status = NOT_COMPARABLE
    return ShadowCompareReport(
        status=status,
        semantic_parity=SEMANTIC_PARITY if status == MATCH else (
            MISMATCH if status == MISMATCH else NOT_COMPARABLE
        ),
        physical_metadata_parity=NOT_COMPARABLE,
        mismatch_categories=aggregate_categories,
        sources=dict(results),
    )


__all__ = (
    "CHRONOLOGY_MISMATCH",
    "CONFLICT_MISMATCH",
    "DUPLICATE_MISMATCH",
    "EVENT_MISMATCH",
    "EXTRA_INDEX_RECORD",
    "FactualRecord",
    "IDENTITY_MISMATCH",
    "INDEX_UNAVAILABLE",
    "MATCH",
    "MISMATCH",
    "MISMATCH_CATEGORIES",
    "MISSING_INDEX_RECORD",
    "NOT_COMPARABLE",
    "OFFSET_MISMATCH",
    "ORDER_MISMATCH",
    "PHYSICAL_METADATA_PARITY",
    "PROMOTION_MISMATCH",
    "RECORD_HASH_MISMATCH",
    "SEMANTIC_PARITY",
    "SHADOW_DISABLED",
    "SOURCE_METADATA_MISMATCH",
    "ShadowCompareReport",
    "ShadowConfig",
    "ShadowMetrics",
    "SourceComparison",
    "VERSION",
    "compare_source_semantics",
    "get_shadow_telemetry_snapshot",
    "observe_evidence_bundle",
    "reset_shadow_telemetry",
    "shadow_capture_enabled",
)
