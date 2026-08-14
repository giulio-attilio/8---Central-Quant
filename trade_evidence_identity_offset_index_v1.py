"""Shadow-only persistent offset index for trade evidence JSONL journals.

Phase A deliberately does not integrate with ``trade_timeline_validator`` or
any operational read/write path.  Journals remain the sole factual evidence;
this module only builds and validates derived SQLite sidecars from explicit
paths supplied by a caller.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import stat
import sys
import time
import tracemalloc
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Optional, Sequence

from trade_evidence_identity_contract import (
    IDENTITY_CLASS_SECONDARY,
    IDENTITY_CLASS_STRONG,
    IDENTITY_CONTRACT_HASH,
    canonical_identity_key,
    classify_identity,
    extract_typed_identities,
)


SCHEMA_VERSION = 1
INDEX_VERSION = "2026-08-14-TRADE-EVIDENCE-IDENTITY-OFFSET-INDEX-V1"
BUILDER_VERSION = INDEX_VERSION + "-PHASE-A-SHADOW-BUILD"

SOURCE_IDS = frozenset({"history_manager", "timeline"})
SOURCE_STATES = frozenset({"BUILDING", "READY", "REVALIDATING", "STALE", "CORRUPT"})

INDEX_COMPLETE_FOR_SNAPSHOT = "INDEX_COMPLETE_FOR_SNAPSHOT"
INDEX_PARTIAL = "INDEX_PARTIAL"
INDEX_STALE = "INDEX_STALE"
INDEX_MISSING = "INDEX_MISSING"
INDEX_SOURCE_CHANGED = "INDEX_SOURCE_CHANGED"
INDEX_CORRUPT = "INDEX_CORRUPT"

DEFAULT_BLOCK_BYTES = 1024 * 1024
DEFAULT_SEGMENT_TARGET_BYTES = 512 * 1024
DEFAULT_BATCH_BYTES = 8 * 1024 * 1024
DEFAULT_BATCH_LINES = 5_000
DEFAULT_MAX_LINE_BYTES = 64 * 1024 * 1024
DEFAULT_ANCHOR_BYTES = 64 * 1024
DEFAULT_BUSY_TIMEOUT_MS = 250
HASH_BYTES = 16
EVENT_TIMESTAMP_KEYS = (
    "occurred_at",
    "event_ts",
    "timestamp",
    "ts",
    "created_at",
    "generated_at",
    "received_at",
    "updated_at",
    "last_update",
    "opened_at",
    "closed_at",
    "epoch",
)
SQLITE_APPLICATION_ID = 0x43514931  # ASCII "CQI1"

FaultInjector = Optional[Callable[[str, Mapping[str, Any]], None]]


class IndexBuildError(RuntimeError):
    """The explicit shadow build could not be completed safely."""


class IndexValidationError(RuntimeError):
    """A factual indexed record failed source verification."""


@dataclass(frozen=True)
class BuildConfig:
    block_bytes: int = DEFAULT_BLOCK_BYTES
    segment_target_bytes: int = DEFAULT_SEGMENT_TARGET_BYTES
    batch_bytes: int = DEFAULT_BATCH_BYTES
    batch_lines: int = DEFAULT_BATCH_LINES
    max_line_bytes: int = DEFAULT_MAX_LINE_BYTES
    anchor_bytes: int = DEFAULT_ANCHOR_BYTES
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS

    def validate(self) -> None:
        for name in (
            "block_bytes",
            "segment_target_bytes",
            "batch_bytes",
            "batch_lines",
            "max_line_bytes",
            "anchor_bytes",
            "busy_timeout_ms",
        ):
            if int(getattr(self, name)) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_line_bytes < self.block_bytes:
            raise ValueError("max_line_bytes must be at least block_bytes")


@dataclass(frozen=True)
class ValidationResult:
    status: str
    reasons: tuple[str, ...] = ()
    source_id: Optional[str] = None
    state: Optional[str] = None
    safe_watermark: int = 0
    source_size: int = 0
    snapshot_eof: int = 0
    generation_uuid: Optional[str] = None
    deep: bool = False

    @property
    def complete(self) -> bool:
        return self.status == INDEX_COMPLETE_FOR_SNAPSHOT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexedRecordMetadata:
    record_id: int
    line_number: int
    start_offset: int
    byte_length: int
    terminator_length: int
    event_type: str
    writer_version: Optional[str]
    record_hash: bytes
    identity_type: Optional[str] = None
    identity_value: Optional[str] = None
    identity_group: Optional[str] = None
    identity_class: Optional[str] = None
    event_epoch: Optional[float] = None
    event_timestamp: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["record_hash"] = self.record_hash.hex()
        return value


@dataclass
class BuildReport:
    source_path: str
    index_path: str
    staging_path: Optional[str]
    source_id: str
    generation_uuid: str
    published: bool
    state: str
    source_bytes: int
    processed_source_bytes: int
    initial_snapshot_eof: int
    build_snapshot_eof: int
    safe_watermark: int
    trailing_fragment_bytes: int
    total_physical_lines: int
    blank_lines: int
    valid_json: int
    invalid_json: int
    invalid_utf8: int
    mapping_records: int
    nonmapping_json: int
    oversized_barriers: int
    segments: int
    unique_identities: int
    postings: int
    strong_postings: int
    secondary_postings: int
    postings_per_record: Mapping[str, float | int]
    index_db_bytes: int
    db_source_ratio: float
    wal_bytes: int
    build_duration_seconds: float
    peak_tracemalloc_bytes: int
    max_rss_bytes: Optional[int]
    throughput_mib_per_second: float
    committed_batches: int
    max_batch_bytes: int
    max_batch_lines: int
    peak_pending_line_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowVerificationResult:
    ok: bool
    source_path: str
    index_path: str
    scope_start: int
    scope_end: int
    identities_checked: int
    sampled_strong_identities: int
    sampled_secondary_identities: int
    sampling_mode: str
    index_offsets: int
    forward_offsets: int
    mismatches: tuple[Mapping[str, Any], ...]
    full_forward_bytes: int
    factual_record_bytes: int
    lookup_duration_ms: float
    forward_duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _PhysicalLine:
    line_number: int
    start_offset: int
    byte_length: int
    terminated: bool
    terminator_length: int
    raw: Optional[bytes]
    line_hash: bytes
    nonblank: bool
    long_line: bool
    oversized: bool


@dataclass(frozen=True)
class _PendingRecord:
    line_number: int
    start_offset: int
    byte_length: int
    terminator_length: int
    event_type: str
    event_epoch: Optional[float]
    event_timestamp: Optional[str]
    writer_version: Optional[str]
    record_hash: bytes
    identities: tuple[Any, ...]


@dataclass
class _PendingSegment:
    start_offset: int
    first_line_number: int
    end_offset: int = 0
    last_line_number: int = 0
    last_line_start_offset: int = -1
    physical_lines: int = 0
    blank_lines: int = 0
    valid_json_lines: int = 0
    invalid_json_lines: int = 0
    invalid_utf8_lines: int = 0
    mapping_records: int = 0
    nonmapping_json_lines: int = 0
    strong_postings: int = 0
    secondary_postings: int = 0
    max_line_bytes: int = 0
    has_long_line: bool = False
    has_oversized_barrier: bool = False
    oversized_barrier_lines: int = 0
    oldest_timestamp: Optional[str] = None
    newest_timestamp: Optional[str] = None
    records: list[_PendingRecord] = field(default_factory=list)

    def add_line(self, line: _PhysicalLine, classification: Mapping[str, Any]) -> None:
        self.end_offset = line.start_offset + line.byte_length
        self.last_line_number = line.line_number
        self.last_line_start_offset = line.start_offset
        self.physical_lines += 1
        self.max_line_bytes = max(self.max_line_bytes, line.byte_length)
        self.has_long_line = bool(self.has_long_line or line.long_line)
        self.has_oversized_barrier = bool(self.has_oversized_barrier or line.oversized)
        if classification["barrier"]:
            self.oversized_barrier_lines += 1
        elif classification["blank"]:
            self.blank_lines += 1
        elif classification["valid_json"]:
            self.valid_json_lines += 1
            if classification["mapping"]:
                self.mapping_records += 1
            else:
                self.nonmapping_json_lines += 1
        elif classification["invalid_utf8"]:
            self.invalid_utf8_lines += 1
        elif classification["invalid_json"]:
            self.invalid_json_lines += 1
        record = classification.get("record")
        if record is not None:
            self.records.append(record)
            if record.event_timestamp:
                if self.oldest_timestamp is None or record.event_timestamp < self.oldest_timestamp:
                    self.oldest_timestamp = record.event_timestamp
                if self.newest_timestamp is None or record.event_timestamp > self.newest_timestamp:
                    self.newest_timestamp = record.event_timestamp
            self.strong_postings += sum(
                1 for item in record.identities if item.identity_class == IDENTITY_CLASS_STRONG
            )
            self.secondary_postings += sum(
                1 for item in record.identities if item.identity_class == IDENTITY_CLASS_SECONDARY
            )

    @property
    def byte_length(self) -> int:
        return self.end_offset - self.start_offset

SCHEMA_SQL = """
CREATE TABLE source_state (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    schema_version INTEGER NOT NULL,
    index_version TEXT NOT NULL,
    identity_contract_hash TEXT NOT NULL,
    source_id TEXT NOT NULL CHECK (source_id IN ('history_manager', 'timeline')),
    source_path TEXT NOT NULL,
    normalized_path_hash TEXT NOT NULL,
    dev TEXT NOT NULL,
    inode TEXT NOT NULL,
    generation_uuid TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('BUILDING', 'READY', 'REVALIDATING', 'STALE', 'CORRUPT')),
    safe_watermark INTEGER NOT NULL CHECK (safe_watermark >= 0),
    observed_eof INTEGER NOT NULL CHECK (observed_eof >= 0),
    last_complete_line_offset INTEGER NOT NULL,
    last_complete_line_number INTEGER NOT NULL,
    initial_snapshot_eof INTEGER NOT NULL CHECK (initial_snapshot_eof >= 0),
    build_snapshot_eof INTEGER NOT NULL CHECK (build_snapshot_eof >= 0),
    prefix_anchor BLOB NOT NULL,
    prefix_anchor_length INTEGER NOT NULL CHECK (prefix_anchor_length >= 0),
    watermark_anchor BLOB NOT NULL,
    watermark_anchor_offset INTEGER NOT NULL CHECK (watermark_anchor_offset >= 0),
    watermark_anchor_length INTEGER NOT NULL CHECK (watermark_anchor_length >= 0),
    snapshot_tail_anchor BLOB NOT NULL,
    snapshot_tail_anchor_offset INTEGER NOT NULL CHECK (snapshot_tail_anchor_offset >= 0),
    snapshot_tail_anchor_length INTEGER NOT NULL CHECK (snapshot_tail_anchor_length >= 0),
    builder_version TEXT NOT NULL,
    block_bytes INTEGER NOT NULL,
    segment_target_bytes INTEGER NOT NULL,
    batch_bytes INTEGER NOT NULL,
    batch_lines INTEGER NOT NULL,
    max_line_bytes INTEGER NOT NULL,
    anchor_bytes INTEGER NOT NULL,
    trailing_fragment_bytes INTEGER NOT NULL DEFAULT 0,
    trailing_fragment_kind TEXT,
    created_at TEXT NOT NULL,
    published_at TEXT,
    validated_at TEXT,
    CHECK (safe_watermark <= observed_eof),
    CHECK (build_snapshot_eof >= initial_snapshot_eof),
    CHECK (block_bytes > 0),
    CHECK (segment_target_bytes > 0),
    CHECK (batch_bytes > 0),
    CHECK (batch_lines > 0),
    CHECK (max_line_bytes >= block_bytes),
    CHECK (anchor_bytes > 0),
    CHECK (length(prefix_anchor) = 16),
    CHECK (length(watermark_anchor) = 16),
    CHECK (length(snapshot_tail_anchor) = 16),
    CHECK (
        (safe_watermark = 0 AND last_complete_line_offset = -1 AND last_complete_line_number = 0)
        OR
        (safe_watermark > 0 AND last_complete_line_offset >= 0
         AND last_complete_line_offset < safe_watermark AND last_complete_line_number >= 1)
    )
);

CREATE TABLE segments (
    segment_id INTEGER PRIMARY KEY,
    source_state_id INTEGER NOT NULL DEFAULT 1 REFERENCES source_state(singleton_id),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    end_offset INTEGER NOT NULL CHECK (end_offset > start_offset),
    first_line_number INTEGER NOT NULL CHECK (first_line_number >= 1),
    last_line_number INTEGER NOT NULL CHECK (last_line_number >= first_line_number),
    last_line_start_offset INTEGER NOT NULL
        CHECK (last_line_start_offset >= start_offset AND last_line_start_offset < end_offset),
    physical_lines INTEGER NOT NULL CHECK (physical_lines > 0),
    blank_lines INTEGER NOT NULL CHECK (blank_lines >= 0),
    valid_json_lines INTEGER NOT NULL CHECK (valid_json_lines >= 0),
    invalid_json_lines INTEGER NOT NULL CHECK (invalid_json_lines >= 0),
    invalid_utf8_lines INTEGER NOT NULL CHECK (invalid_utf8_lines >= 0),
    mapping_records INTEGER NOT NULL CHECK (mapping_records >= 0),
    nonmapping_json_lines INTEGER NOT NULL CHECK (nonmapping_json_lines >= 0),
    strong_postings INTEGER NOT NULL CHECK (strong_postings >= 0),
    secondary_postings INTEGER NOT NULL CHECK (secondary_postings >= 0),
    max_line_bytes INTEGER NOT NULL CHECK (max_line_bytes > 0),
    has_long_line INTEGER NOT NULL CHECK (has_long_line IN (0, 1)),
    has_oversized_barrier INTEGER NOT NULL CHECK (has_oversized_barrier IN (0, 1)),
    oversized_barrier_lines INTEGER NOT NULL CHECK (oversized_barrier_lines >= 0),
    oldest_timestamp TEXT,
    newest_timestamp TEXT,
    segment_hash BLOB NOT NULL CHECK (length(segment_hash) = 16),
    CHECK (mapping_records + nonmapping_json_lines = valid_json_lines),
    CHECK (
        blank_lines + valid_json_lines + invalid_json_lines + invalid_utf8_lines
        + oversized_barrier_lines = physical_lines
    ),
    CHECK (
        (has_oversized_barrier = 0 AND oversized_barrier_lines = 0)
        OR (has_oversized_barrier = 1 AND oversized_barrier_lines > 0)
    ),
    CHECK (
        (oldest_timestamp IS NULL AND newest_timestamp IS NULL)
        OR (oldest_timestamp IS NOT NULL AND newest_timestamp IS NOT NULL
            AND oldest_timestamp <= newest_timestamp)
    ),
    UNIQUE (start_offset),
    UNIQUE (end_offset)
);

CREATE TABLE records (
    record_id INTEGER PRIMARY KEY,
    segment_id INTEGER NOT NULL REFERENCES segments(segment_id) ON DELETE RESTRICT,
    line_number INTEGER NOT NULL CHECK (line_number >= 1),
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    byte_length INTEGER NOT NULL CHECK (byte_length > 0),
    terminator_length INTEGER NOT NULL CHECK (terminator_length IN (1, 2)),
    event_type TEXT NOT NULL,
    event_epoch REAL,
    event_timestamp TEXT,
    writer_version TEXT,
    record_hash BLOB NOT NULL CHECK (length(record_hash) = 16),
    UNIQUE (start_offset),
    UNIQUE (line_number),
    UNIQUE (record_id, start_offset)
);

CREATE TABLE identities (
    identity_id INTEGER PRIMARY KEY,
    identity_type TEXT NOT NULL,
    identity_value TEXT NOT NULL,
    identity_group TEXT NOT NULL,
    identity_class TEXT NOT NULL CHECK (identity_class IN ('STRONG', 'SECONDARY')),
    UNIQUE (identity_type, identity_value)
);

CREATE TABLE postings (
    identity_id INTEGER NOT NULL REFERENCES identities(identity_id) ON DELETE RESTRICT,
    start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
    record_id INTEGER NOT NULL,
    PRIMARY KEY (identity_id, start_offset, record_id),
    FOREIGN KEY (record_id, start_offset)
        REFERENCES records(record_id, start_offset) ON DELETE RESTRICT
) WITHOUT ROWID;

CREATE INDEX records_segment_offset_idx ON records(segment_id, start_offset);
CREATE INDEX postings_record_idx ON postings(record_id, start_offset, identity_id);
"""

REQUIRED_TABLES = frozenset({"source_state", "segments", "records", "identities", "postings"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def normalized_path_hash(path: Path | str) -> str:
    normalized = _normalized_path(Path(path))
    return hashlib.sha256(normalized.encode("utf-8", errors="surrogatepass")).hexdigest()


def _validate_source_id(source_id: str) -> str:
    value = str(source_id or "").strip()
    if value not in SOURCE_IDS:
        raise ValueError(f"source_id must be one of {sorted(SOURCE_IDS)}")
    return value


def _source_stat(path: Path) -> os.stat_result:
    value = path.lstat()
    if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
        raise IndexBuildError("source must be a regular non-symlink file")
    return value


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return int(left.st_dev) == int(right.st_dev) and int(left.st_ino) == int(right.st_ino)


def _blake128(value: bytes) -> bytes:
    return hashlib.blake2b(value, digest_size=HASH_BYTES).digest()


def _read_exact_range(handle: BinaryIO, offset: int, length: int) -> bytes:
    if offset < 0 or length < 0:
        raise ValueError("offset and length must be non-negative")
    current = handle.tell()
    try:
        handle.seek(offset, os.SEEK_SET)
        value = handle.read(length)
    finally:
        handle.seek(current, os.SEEK_SET)
    if len(value) != length:
        raise IndexValidationError("source range is shorter than indexed metadata")
    return value


def _watermark_anchor_values(
    handle: BinaryIO, watermark: int, anchor_bytes: int
) -> dict[str, Any]:
    watermark_length = min(anchor_bytes, watermark)
    watermark_offset = watermark - watermark_length
    tail = (
        _read_exact_range(handle, watermark_offset, watermark_length)
        if watermark_length
        else b""
    )
    return {
        "watermark_anchor": _blake128(tail),
        "watermark_anchor_offset": watermark_offset,
        "watermark_anchor_length": watermark_length,
    }


def _sqlite_connect(path: Path, *, readonly: bool, busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS) -> sqlite3.Connection:
    if readonly:
        connection = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=max(0.001, busy_timeout_ms / 1000.0),
            isolation_level=None,
        )
    else:
        connection = sqlite3.connect(
            os.fspath(path),
            timeout=max(0.001, busy_timeout_ms / 1000.0),
            isolation_level=None,
        )
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    connection.execute("PRAGMA foreign_keys=ON")
    if readonly:
        connection.execute("PRAGMA query_only=ON")
    return connection


def _hash_range(handle: BinaryIO, offset: int, length: int, block_bytes: int) -> bytes:
    if offset < 0 or length < 0:
        raise ValueError("offset and length must be non-negative")
    current = handle.tell()
    digest = hashlib.blake2b(digest_size=HASH_BYTES)
    remaining = length
    try:
        handle.seek(offset, os.SEEK_SET)
        while remaining:
            chunk = handle.read(min(block_bytes, remaining))
            if not chunk:
                raise IndexValidationError("source range is shorter than indexed metadata")
            digest.update(chunk)
            remaining -= len(chunk)
    finally:
        handle.seek(current, os.SEEK_SET)
    return digest.digest()


def _snapshot_tail_anchor(handle: BinaryIO, snapshot_eof: int, anchor_bytes: int) -> dict[str, Any]:
    length = min(anchor_bytes, snapshot_eof)
    offset = snapshot_eof - length
    value = _read_exact_range(handle, offset, length) if length else b""
    return {
        "snapshot_tail_anchor": _blake128(value),
        "snapshot_tail_anchor_offset": offset,
        "snapshot_tail_anchor_length": length,
    }


def _initialize_database(
    path: Path,
    source: Path,
    source_id: str,
    generation_uuid: str,
    source_stat: os.stat_result,
    snapshot_eof: int,
    config: BuildConfig,
) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _sqlite_connect(path, readonly=False, busy_timeout_ms=config.busy_timeout_ms)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(f"PRAGMA application_id={SQLITE_APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.executescript(SCHEMA_SQL)
        now = _utc_now()
        empty_anchor = _blake128(b"")
        with source.open("rb") as source_handle:
            prefix_length = min(config.anchor_bytes, snapshot_eof)
            prefix_value = (
                _read_exact_range(source_handle, 0, prefix_length)
                if prefix_length
                else b""
            )
            prefix_anchor = _blake128(prefix_value)
            snapshot_tail = _snapshot_tail_anchor(source_handle, snapshot_eof, config.anchor_bytes)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO source_state (
                singleton_id, schema_version, index_version, identity_contract_hash,
                source_id, source_path, normalized_path_hash, dev, inode,
                generation_uuid, state, safe_watermark, observed_eof,
                last_complete_line_offset, last_complete_line_number,
                initial_snapshot_eof, build_snapshot_eof,
                prefix_anchor, prefix_anchor_length,
                watermark_anchor, watermark_anchor_offset, watermark_anchor_length,
                snapshot_tail_anchor, snapshot_tail_anchor_offset, snapshot_tail_anchor_length,
                builder_version, block_bytes, segment_target_bytes, batch_bytes,
                batch_lines, max_line_bytes, anchor_bytes, created_at
            ) VALUES (
                1, :schema_version, :index_version, :contract_hash,
                :source_id, :source_path, :path_hash, :dev, :inode,
                :generation_uuid, 'BUILDING', 0, :observed_eof, -1, 0,
                :initial_snapshot_eof, :build_snapshot_eof,
                :prefix_anchor, :prefix_anchor_length,
                :empty_anchor, 0, 0,
                :snapshot_tail_anchor, :snapshot_tail_offset, :snapshot_tail_length,
                :builder_version, :block_bytes, :segment_target_bytes,
                :batch_bytes, :batch_lines, :max_line_bytes, :anchor_bytes,
                :created_at
            )
            """,
            {
                "schema_version": SCHEMA_VERSION,
                "index_version": INDEX_VERSION,
                "contract_hash": IDENTITY_CONTRACT_HASH,
                "source_id": source_id,
                "source_path": _normalized_path(source),
                "path_hash": normalized_path_hash(source),
                "dev": str(int(source_stat.st_dev)),
                "inode": str(int(source_stat.st_ino)),
                "generation_uuid": generation_uuid,
                "observed_eof": snapshot_eof,
                "initial_snapshot_eof": snapshot_eof,
                "build_snapshot_eof": snapshot_eof,
                "prefix_anchor": prefix_anchor,
                "prefix_anchor_length": prefix_length,
                "empty_anchor": empty_anchor,
                "snapshot_tail_anchor": snapshot_tail["snapshot_tail_anchor"],
                "snapshot_tail_offset": snapshot_tail["snapshot_tail_anchor_offset"],
                "snapshot_tail_length": snapshot_tail["snapshot_tail_anchor_length"],
                "builder_version": BUILDER_VERSION,
                "block_bytes": config.block_bytes,
                "segment_target_bytes": config.segment_target_bytes,
                "batch_bytes": config.batch_bytes,
                "batch_lines": config.batch_lines,
                "max_line_bytes": config.max_line_bytes,
                "anchor_bytes": config.anchor_bytes,
                "created_at": now,
            },
        )
        connection.execute("COMMIT")
        return connection
    except Exception:
        connection.close()
        raise


def _load_source_state(connection: sqlite3.Connection) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM source_state WHERE singleton_id=1").fetchone()
    if row is None:
        raise IndexValidationError("source_state singleton is missing")
    return row


def _direct_value(record: Mapping[str, Any], *keys: str) -> Any:
    containers: list[Mapping[str, Any]] = [record]
    for name in ("metadata", "payload", "evidence", "trade", "snapshot", "result"):
        value = record.get(name)
        if isinstance(value, Mapping):
            containers.append(value)
    for container in containers:
        for key in keys:
            value = container.get(key)
            if value not in (None, ""):
                return value
    return None


def _event_type(record: Mapping[str, Any]) -> str:
    value = _direct_value(record, "event_type", "event", "action", "type")
    direct = str(value or "").upper().strip().replace(" ", "_")
    if direct:
        return direct
    # Match the Validator's factual fallback for records that wrap the event
    # more deeply than the well-known direct containers.
    for item in _walk_mappings(record):
        for key in ("event_type", "event", "action", "type"):
            if item.get(key) not in (None, ""):
                return str(item[key]).upper().strip().replace(" ", "_")
    return ""


def _writer_version(record: Mapping[str, Any]) -> Optional[str]:
    value = _direct_value(record, "writer_version", "producer_version")
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def _parse_event_timestamp(value: Any) -> tuple[Optional[float], Optional[str]]:
    """Snapshot the Validator's timestamp normalization without importing it."""

    if value in (None, ""):
        return None, None
    text = str(value).strip()
    numeric: Optional[float] = None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        try:
            numeric = float(text)
        except ValueError:
            numeric = None
    if numeric is not None:
        if numeric > 10_000_000_000:
            numeric /= 1000.0
        try:
            if math.isfinite(numeric):
                return numeric, datetime.fromtimestamp(numeric, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            pass
        return None, text or None
    normalized = text.replace("Z", "+00:00")
    for parser in (
        lambda: datetime.fromisoformat(normalized),
        lambda: datetime.strptime(text, "%d/%m/%Y %H:%M:%S"),
        lambda: datetime.strptime(text, "%d/%m/%Y %H:%M"),
        lambda: datetime.strptime(text, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parser()
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp(), parsed.astimezone(timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            continue
    return None, text or None


def _first_event_timestamp(record: Mapping[str, Any]) -> tuple[Optional[float], Optional[str]]:
    for item in _walk_mappings(record):
        for key in EVENT_TIMESTAMP_KEYS:
            if item.get(key) not in (None, ""):
                return _parse_event_timestamp(item[key])
    return None, None


def _iter_physical_lines(
    handle: BinaryIO,
    *,
    start_offset: int,
    end_offset: int,
    first_line_number: int,
    block_bytes: int,
    max_line_bytes: int,
) -> Iterable[_PhysicalLine]:
    if not 0 <= start_offset <= end_offset:
        raise ValueError("invalid physical line range")
    handle.seek(start_offset, os.SEEK_SET)
    absolute = start_offset
    line_start = start_offset
    line_number = first_line_number
    line_length = 0
    line_buffer: Optional[bytearray] = bytearray()
    line_hasher = hashlib.blake2b(digest_size=HASH_BYTES)
    nonblank = False

    while absolute < end_offset:
        chunk = handle.read(min(block_bytes, end_offset - absolute))
        if not chunk:
            raise IndexBuildError("short read while scanning source snapshot")
        cursor = 0
        while cursor < len(chunk):
            newline = chunk.find(b"\n", cursor)
            piece_end = newline + 1 if newline >= 0 else len(chunk)
            piece = chunk[cursor:piece_end]
            line_hasher.update(piece)
            line_length += len(piece)
            if piece.strip(b" \t\r\n\v\f"):
                nonblank = True
            if line_buffer is not None:
                if len(line_buffer) + len(piece) <= max_line_bytes:
                    line_buffer.extend(piece)
                else:
                    line_buffer = None
            absolute += len(piece)
            cursor = piece_end
            if newline >= 0:
                raw = bytes(line_buffer) if line_buffer is not None else None
                terminator_length = 2 if raw is not None and raw.endswith(b"\r\n") else 1
                yield _PhysicalLine(
                    line_number=line_number,
                    start_offset=line_start,
                    byte_length=line_length,
                    terminated=True,
                    terminator_length=terminator_length,
                    raw=raw,
                    line_hash=line_hasher.digest(),
                    nonblank=nonblank,
                    long_line=line_length > block_bytes,
                    oversized=line_buffer is None,
                )
                line_number += 1
                line_start = absolute
                line_length = 0
                line_buffer = bytearray()
                line_hasher = hashlib.blake2b(digest_size=HASH_BYTES)
                nonblank = False

    if line_length:
        yield _PhysicalLine(
            line_number=line_number,
            start_offset=line_start,
            byte_length=line_length,
            terminated=False,
            terminator_length=0,
            raw=bytes(line_buffer) if line_buffer is not None else None,
            line_hash=line_hasher.digest(),
            nonblank=nonblank,
            long_line=line_length > block_bytes,
            oversized=line_buffer is None,
        )


def _classify_line(line: _PhysicalLine) -> dict[str, Any]:
    result: dict[str, Any] = {
        "barrier": bool(line.oversized),
        "blank": bool(not line.nonblank and not line.oversized),
        "valid_json": False,
        "invalid_json": False,
        "invalid_utf8": False,
        "mapping": False,
        "record": None,
    }
    if line.oversized:
        return result
    if not line.nonblank:
        return result
    if line.raw is None:
        return result
    raw_document = line.raw[:-1] if line.terminated else line.raw
    try:
        decoded = raw_document.decode("utf-8")
    except UnicodeDecodeError:
        result["invalid_utf8"] = True
        return result
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError:
        result["invalid_json"] = True
        return result
    result["valid_json"] = True
    if not isinstance(value, Mapping):
        return result
    result["mapping"] = True
    identities = extract_typed_identities(value)
    event_epoch, event_timestamp = _first_event_timestamp(value)
    result["record"] = _PendingRecord(
        line_number=line.line_number,
        start_offset=line.start_offset,
        byte_length=line.byte_length,
        terminator_length=line.terminator_length,
        event_type=_event_type(value),
        event_epoch=event_epoch,
        event_timestamp=event_timestamp,
        writer_version=_writer_version(value),
        record_hash=line.line_hash,
        identities=identities,
    )
    return result


def _invoke_fault(fault_injector: FaultInjector, point: str, **context: Any) -> None:
    if fault_injector is not None:
        fault_injector(point, context)


def _commit_segments(
    connection: sqlite3.Connection,
    handle: BinaryIO,
    segments: Sequence[_PendingSegment],
    *,
    config: BuildConfig,
    observed_eof: int,
    fault_injector: FaultInjector,
) -> None:
    if not segments:
        return
    final_segment = segments[-1]
    watermark = final_segment.end_offset
    anchors = _watermark_anchor_values(handle, watermark, config.anchor_bytes)
    # Source reads and hashing deliberately happen before BEGIN IMMEDIATE so a
    # slow filesystem cannot stretch the SQLite write-lock/transaction.
    segment_hashes = tuple(
        _hash_range(handle, segment.start_offset, segment.byte_length, config.block_bytes)
        for segment in segments
    )
    _invoke_fault(
        fault_injector,
        "before_batch_commit",
        safe_watermark=watermark,
        segments=len(segments),
    )
    connection.execute("BEGIN IMMEDIATE")
    try:
        state = _load_source_state(connection)
        expected_start = int(state["safe_watermark"])
        if segments[0].start_offset != expected_start:
            raise IndexBuildError("batch does not begin at the persisted safe watermark")
        for segment, segment_hash in zip(segments, segment_hashes):
            cursor = connection.execute(
                """
                INSERT INTO segments (
                    start_offset, end_offset, first_line_number, last_line_number,
                    last_line_start_offset,
                    physical_lines, blank_lines, valid_json_lines, invalid_json_lines,
                    invalid_utf8_lines,
                    mapping_records, nonmapping_json_lines, strong_postings,
                    secondary_postings, max_line_bytes, has_long_line,
                    has_oversized_barrier, oversized_barrier_lines,
                    oldest_timestamp, newest_timestamp, segment_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    segment.start_offset,
                    segment.end_offset,
                    segment.first_line_number,
                    segment.last_line_number,
                    segment.last_line_start_offset,
                    segment.physical_lines,
                    segment.blank_lines,
                    segment.valid_json_lines,
                    segment.invalid_json_lines,
                    segment.invalid_utf8_lines,
                    segment.mapping_records,
                    segment.nonmapping_json_lines,
                    segment.strong_postings,
                    segment.secondary_postings,
                    segment.max_line_bytes,
                    int(segment.has_long_line),
                    int(segment.has_oversized_barrier),
                    segment.oversized_barrier_lines,
                    segment.oldest_timestamp,
                    segment.newest_timestamp,
                    segment_hash,
                ),
            )
            segment_id = int(cursor.lastrowid)
            for record in segment.records:
                record_cursor = connection.execute(
                    """
                    INSERT INTO records (
                        segment_id, line_number, start_offset, byte_length,
                        terminator_length, event_type, event_epoch, event_timestamp,
                        writer_version, record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment_id,
                        record.line_number,
                        record.start_offset,
                        record.byte_length,
                        record.terminator_length,
                        record.event_type,
                        record.event_epoch,
                        record.event_timestamp,
                        record.writer_version,
                        record.record_hash,
                    ),
                )
                record_id = int(record_cursor.lastrowid)
                for identity in record.identities:
                    connection.execute(
                        """
                        INSERT INTO identities (
                            identity_type, identity_value, identity_group, identity_class
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(identity_type, identity_value) DO NOTHING
                        """,
                        (
                            identity.identity_type,
                            identity.identity_value,
                            identity.identity_group,
                            identity.identity_class,
                        ),
                    )
                    identity_row = connection.execute(
                        """
                        SELECT identity_id, identity_group, identity_class
                        FROM identities
                        WHERE identity_type=? AND identity_value=?
                        """,
                        (identity.identity_type, identity.identity_value),
                    ).fetchone()
                    if identity_row is None:
                        raise IndexBuildError("identity upsert could not be read back")
                    if (
                        identity_row["identity_group"] != identity.identity_group
                        or identity_row["identity_class"] != identity.identity_class
                    ):
                        raise IndexBuildError("identity taxonomy changed inside one build")
                    connection.execute(
                        """
                        INSERT INTO postings(identity_id, start_offset, record_id)
                        VALUES (?, ?, ?)
                        """,
                        (int(identity_row["identity_id"]), record.start_offset, record_id),
                    )
        connection.execute(
            """
            UPDATE source_state SET
                safe_watermark=?, observed_eof=?,
                last_complete_line_offset=?, last_complete_line_number=?,
                watermark_anchor=?, watermark_anchor_offset=?, watermark_anchor_length=?
            WHERE singleton_id=1
            """,
            (
                watermark,
                observed_eof,
                final_segment.last_line_start_offset,
                final_segment.last_line_number,
                anchors["watermark_anchor"],
                anchors["watermark_anchor_offset"],
                anchors["watermark_anchor_length"],
            ),
        )
        _invoke_fault(
            fault_injector,
            "before_batch_sql_commit",
            safe_watermark=watermark,
            segments=len(segments),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    _invoke_fault(
        fault_injector,
        "after_batch_commit",
        safe_watermark=watermark,
        segments=len(segments),
    )


def _database_sidecars(path: Path) -> tuple[Path, Path, Path]:
    return (
        Path(os.fspath(path) + "-wal"),
        Path(os.fspath(path) + "-shm"),
        Path(os.fspath(path) + "-journal"),
    )


def _fsync_file(path: Path) -> None:
    # Windows rejects fsync on a read-only descriptor.  The handle is opened
    # write-capable solely to flush the already-written SQLite sidecar; no
    # journal source ever passes through this helper.
    with path.open("r+b", buffering=0) as handle:
        os.fsync(handle.fileno())


def _fsync_parent(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(os.fspath(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _staging_path(index_path: Path, generation_uuid: str) -> Path:
    return Path(os.fspath(index_path) + f".building.{generation_uuid}")


def find_staging_indexes(index_path: Path | str) -> tuple[Path, ...]:
    path = Path(index_path)
    return tuple(sorted(path.parent.glob(path.name + ".building.*")))


def _max_rss_bytes() -> Optional[int]:
    try:
        import resource

        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value if sys.platform == "darwin" else value * 1024
    except (ImportError, AttributeError, OSError, ValueError):
        return None


def _mark_state(connection: sqlite3.Connection, state: str, *, published: bool = False) -> None:
    if state not in SOURCE_STATES:
        raise ValueError("invalid source state")
    now = _utc_now()
    connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute(
            """
            UPDATE source_state
            SET state=?, published_at=CASE WHEN ? THEN COALESCE(published_at, ?) ELSE published_at END,
                validated_at=CASE WHEN ? THEN ? ELSE validated_at END
            WHERE singleton_id=1
            """,
            (state, int(published), now, int(state == "READY"), now),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _publish_staging(
    source: Path,
    index_path: Path,
    staging_path: Path,
    source_id: str,
    *,
    fault_injector: FaultInjector,
) -> None:
    for sidecar in (*_database_sidecars(staging_path), *_database_sidecars(index_path)):
        if sidecar.exists():
            raise IndexBuildError(f"refusing atomic publication while SQLite sidecar exists: {sidecar}")
    _fsync_file(staging_path)
    _invoke_fault(fault_injector, "before_atomic_replace", staging_path=str(staging_path))
    os.replace(staging_path, index_path)
    _fsync_parent(index_path)
    _invoke_fault(fault_injector, "after_atomic_replace", index_path=str(index_path))
    _finish_revalidating_final(source, index_path, source_id)


def _finish_revalidating_final(
    source: Path,
    index_path: Path,
    source_id: str,
) -> None:
    """Finish a DB already present at its final name after a safe crash.

    This is also the last publication step.  The final-path bytes are deeply
    revalidated while still REVALIDATING; READY is a subsequent, tiny SQLite
    transaction.  A crash before that transaction remains explicitly PARTIAL
    and ``--resume`` can call this function again.
    """

    result = validate_index(source, index_path, source_id, deep=True)
    if result.status != INDEX_PARTIAL or result.state != "REVALIDATING":
        raise IndexBuildError(f"post-publication validation failed: {result.status}: {result.reasons}")
    connection = _sqlite_connect(index_path, readonly=False)
    try:
        state = _load_source_state(connection)
        if str(state["state"]) != "REVALIDATING":
            raise IndexBuildError("only a REVALIDATING final index can be finalized")
        if int(state["safe_watermark"]) != int(state["build_snapshot_eof"]):
            raise IndexBuildError("partial staging cannot be marked READY")
        build_snapshot_eof = int(state["build_snapshot_eof"])
        _mark_state(connection, "READY", published=True)
    finally:
        connection.close()
    _fsync_file(index_path)
    _fsync_parent(index_path)
    post_ready = validate_index(
        source,
        index_path,
        source_id,
        snapshot_eof=build_snapshot_eof,
        deep=False,
    )
    if post_ready.status != INDEX_COMPLETE_FOR_SNAPSHOT:
        raise IndexBuildError(
            f"READY post-check failed: {post_ready.status}: {post_ready.reasons}"
        )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _basic_invariant_errors(connection: sqlite3.Connection) -> list[str]:
    errors: list[str] = []
    if not REQUIRED_TABLES.issubset(_table_names(connection)):
        return ["REQUIRED_TABLE_MISSING"]
    try:
        states = connection.execute("SELECT COUNT(*) FROM source_state").fetchone()[0]
        if int(states) != 1:
            errors.append("SOURCE_STATE_CARDINALITY")
            return errors
        state = _load_source_state(connection)
        watermark = int(state["safe_watermark"])
        observed_eof = int(state["observed_eof"])
        initial_snapshot_eof = int(state["initial_snapshot_eof"])
        build_snapshot_eof = int(state["build_snapshot_eof"])
        anchor_bytes = int(state["anchor_bytes"])
        try:
            _stored_config(state).validate()
        except (TypeError, ValueError):
            errors.append("STORED_CONFIG_INVALID")
        expected_prefix_length = min(anchor_bytes, initial_snapshot_eof)
        expected_watermark_length = min(anchor_bytes, watermark)
        expected_snapshot_tail_length = min(anchor_bytes, build_snapshot_eof)
        if observed_eof < build_snapshot_eof:
            errors.append("OBSERVED_EOF_BEHIND_BUILD_SNAPSHOT")
        if build_snapshot_eof < initial_snapshot_eof:
            errors.append("BUILD_SNAPSHOT_BEHIND_INITIAL_SNAPSHOT")
        if (
            len(bytes(state["prefix_anchor"])) != HASH_BYTES
            or int(state["prefix_anchor_length"]) != expected_prefix_length
        ):
            errors.append("PREFIX_ANCHOR_SHAPE")
        if (
            len(bytes(state["watermark_anchor"])) != HASH_BYTES
            or int(state["watermark_anchor_length"]) != expected_watermark_length
            or int(state["watermark_anchor_offset"]) != watermark - expected_watermark_length
        ):
            errors.append("WATERMARK_ANCHOR_SHAPE")
        if (
            len(bytes(state["snapshot_tail_anchor"])) != HASH_BYTES
            or int(state["snapshot_tail_anchor_length"]) != expected_snapshot_tail_length
            or int(state["snapshot_tail_anchor_offset"])
            != build_snapshot_eof - expected_snapshot_tail_length
        ):
            errors.append("SNAPSHOT_TAIL_ANCHOR_SHAPE")
        try:
            if str(uuid.UUID(str(state["generation_uuid"]))) != str(state["generation_uuid"]):
                errors.append("GENERATION_UUID_INVALID")
        except (ValueError, AttributeError):
            errors.append("GENERATION_UUID_INVALID")
        segment_summary = connection.execute(
            """
            SELECT COUNT(*) AS count_rows, MIN(start_offset) AS first_start,
                   MAX(end_offset) AS last_end,
                   MIN(first_line_number) AS first_line,
                   MAX(last_line_number) AS last_line,
                   COALESCE(SUM(mapping_records), 0) AS mapping_records,
                   COALESCE(SUM(strong_postings), 0) AS strong_postings,
                   COALESCE(SUM(secondary_postings), 0) AS secondary_postings
            FROM segments
            """
        ).fetchone()
        segment_count = int(segment_summary["count_rows"] or 0)
        record_count = int(connection.execute("SELECT COUNT(*) FROM records").fetchone()[0])
        posting_count = int(connection.execute("SELECT COUNT(*) FROM postings").fetchone()[0])
        if watermark == 0:
            if (
                int(state["last_complete_line_offset"]) != -1
                or int(state["last_complete_line_number"]) != 0
            ):
                errors.append("ZERO_WATERMARK_LAST_LINE_STATE")
            if segment_count or record_count or posting_count:
                errors.append("ROWS_BEFORE_ZERO_WATERMARK")
        else:
            if not 0 <= int(state["last_complete_line_offset"]) < watermark:
                errors.append("LAST_COMPLETE_LINE_OFFSET_RANGE")
            if not segment_count:
                errors.append("MISSING_SEGMENTS")
            if segment_summary["first_start"] is None or int(segment_summary["first_start"]) != 0:
                errors.append("FIRST_SEGMENT_NOT_ZERO")
            if segment_summary["last_end"] is None or int(segment_summary["last_end"]) != watermark:
                errors.append("LAST_SEGMENT_NOT_WATERMARK")
            gap = connection.execute(
                """
                SELECT 1 FROM (
                    SELECT start_offset,
                           LAG(end_offset) OVER (ORDER BY start_offset) AS previous_end
                    FROM segments
                ) WHERE previous_end IS NOT NULL AND start_offset != previous_end LIMIT 1
                """
            ).fetchone()
            if gap is not None:
                errors.append("SEGMENT_GAP_OR_OVERLAP")
            line_gap = connection.execute(
                """
                SELECT 1 FROM (
                    SELECT first_line_number,
                           LAG(last_line_number) OVER (ORDER BY start_offset) AS previous_line
                    FROM segments
                ) WHERE previous_line IS NOT NULL
                    AND first_line_number != previous_line + 1 LIMIT 1
                """
            ).fetchone()
            if line_gap is not None:
                errors.append("SEGMENT_LINE_GAP_OR_OVERLAP")
            if int(segment_summary["first_line"] or 0) != 1:
                errors.append("FIRST_SEGMENT_LINE_NOT_ONE")
            if int(segment_summary["last_line"] or 0) != int(
                state["last_complete_line_number"]
            ):
                errors.append("LAST_SEGMENT_LINE_MISMATCH")
            last_segment = connection.execute(
                """
                SELECT last_line_start_offset FROM segments
                ORDER BY start_offset DESC LIMIT 1
                """
            ).fetchone()
            if (
                last_segment is None
                or int(last_segment["last_line_start_offset"])
                != int(state["last_complete_line_offset"])
            ):
                errors.append("LAST_COMPLETE_LINE_OFFSET_MISMATCH")
        if connection.execute(
            """
            SELECT 1 FROM segments
            WHERE last_line_number - first_line_number + 1 != physical_lines
               OR mapping_records + nonmapping_json_lines != valid_json_lines
               OR blank_lines + valid_json_lines + invalid_json_lines
                    + invalid_utf8_lines + oversized_barrier_lines != physical_lines
               OR (has_oversized_barrier = 0 AND oversized_barrier_lines != 0)
               OR (has_oversized_barrier = 1 AND oversized_barrier_lines = 0)
            LIMIT 1
            """
        ).fetchone() is not None:
            errors.append("SEGMENT_CLASSIFICATION_COUNTS")
        if int(segment_summary["mapping_records"] or 0) != record_count:
            errors.append("MAPPING_RECORD_COUNT_MISMATCH")
        expected_postings = int(segment_summary["strong_postings"] or 0) + int(
            segment_summary["secondary_postings"] or 0
        )
        if expected_postings != posting_count:
            errors.append("POSTING_COUNT_MISMATCH")
        if connection.execute(
            """
            SELECT 1 FROM records r JOIN segments s ON s.segment_id=r.segment_id
            WHERE r.start_offset < s.start_offset
               OR r.start_offset + r.byte_length > s.end_offset
            LIMIT 1
            """
        ).fetchone() is not None:
            errors.append("RECORD_OUTSIDE_SEGMENT")
        if connection.execute(
            """
            SELECT 1 FROM postings p
            LEFT JOIN records r
              ON r.record_id=p.record_id AND r.start_offset=p.start_offset
            LEFT JOIN identities i ON i.identity_id=p.identity_id
            WHERE r.record_id IS NULL OR i.identity_id IS NULL
            LIMIT 1
            """
        ).fetchone() is not None:
            errors.append("POSTING_TARGET_MISMATCH")
        if connection.execute(
            """
            SELECT 1 FROM identities i
            LEFT JOIN postings p ON p.identity_id=i.identity_id
            WHERE p.identity_id IS NULL LIMIT 1
            """
        ).fetchone() is not None:
            errors.append("ORPHAN_IDENTITY")
        if str(state["state"]) == "READY" and int(state["safe_watermark"]) < int(
            state["build_snapshot_eof"]
        ):
            errors.append("READY_BEFORE_BUILD_SNAPSHOT")
    except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"INVARIANT_QUERY_FAILED:{type(exc).__name__}")
    return errors


def _deep_invariant_errors(
    connection: sqlite3.Connection,
    handle: BinaryIO,
    state: sqlite3.Row,
) -> list[str]:
    errors: list[str] = []
    quick = connection.execute("PRAGMA quick_check").fetchall()
    if len(quick) != 1 or str(quick[0][0]).lower() != "ok":
        errors.append("SQLITE_QUICK_CHECK_FAILED")
        return errors
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        errors.append("FOREIGN_KEY_VIOLATION")
        return errors
    block_bytes = int(state["block_bytes"])
    max_line_bytes = int(state["max_line_bytes"])
    for segment in connection.execute("SELECT * FROM segments ORDER BY start_offset"):
        try:
            actual_segment_hash = _hash_range(
                handle,
                int(segment["start_offset"]),
                int(segment["end_offset"]) - int(segment["start_offset"]),
                block_bytes,
            )
        except IndexValidationError:
            errors.append(f"SEGMENT_SHORT_READ:{segment['segment_id']}")
            continue
        if actual_segment_hash != bytes(segment["segment_hash"]):
            errors.append(f"SEGMENT_HASH_MISMATCH:{segment['segment_id']}")
            continue
        actual_counts = {
            "physical_lines": 0,
            "blank_lines": 0,
            "valid_json_lines": 0,
            "invalid_json_lines": 0,
            "invalid_utf8_lines": 0,
            "mapping_records": 0,
            "nonmapping_json_lines": 0,
            "strong_postings": 0,
            "secondary_postings": 0,
            "oversized_barrier_lines": 0,
        }
        actual_max_line_bytes = 0
        actual_has_long_line = False
        actual_has_oversized_barrier = False
        actual_oldest_timestamp: Optional[str] = None
        actual_newest_timestamp: Optional[str] = None
        actual_last_line_start_offset = -1
        records = {
            int(row["start_offset"]): row
            for row in connection.execute(
                "SELECT * FROM records WHERE segment_id=? ORDER BY start_offset",
                (int(segment["segment_id"]),),
            )
        }
        for line in _iter_physical_lines(
            handle,
            start_offset=int(segment["start_offset"]),
            end_offset=int(segment["end_offset"]),
            first_line_number=int(segment["first_line_number"]),
            block_bytes=block_bytes,
            max_line_bytes=max_line_bytes,
        ):
            if not line.terminated:
                errors.append(f"SEGMENT_NOT_NEWLINE_TERMINATED:{segment['segment_id']}")
                break
            classification = _classify_line(line)
            actual_counts["physical_lines"] += 1
            actual_last_line_start_offset = line.start_offset
            actual_max_line_bytes = max(actual_max_line_bytes, line.byte_length)
            actual_has_long_line = bool(actual_has_long_line or line.long_line)
            actual_has_oversized_barrier = bool(
                actual_has_oversized_barrier or line.oversized
            )
            if classification["barrier"]:
                actual_counts["oversized_barrier_lines"] += 1
            elif classification["blank"]:
                actual_counts["blank_lines"] += 1
            elif classification["valid_json"]:
                actual_counts["valid_json_lines"] += 1
                if classification["mapping"]:
                    actual_counts["mapping_records"] += 1
                else:
                    actual_counts["nonmapping_json_lines"] += 1
            elif classification["invalid_json"]:
                actual_counts["invalid_json_lines"] += 1
            elif classification["invalid_utf8"]:
                actual_counts["invalid_utf8_lines"] += 1
            record = classification.get("record")
            if record is None:
                continue
            stored = records.pop(line.start_offset, None)
            if stored is None:
                errors.append(f"MISSING_RECORD:{line.start_offset}")
                continue
            if bytes(stored["record_hash"]) != line.line_hash:
                errors.append(f"RECORD_HASH_MISMATCH:{line.start_offset}")
            if (
                int(stored["line_number"]) != line.line_number
                or int(stored["byte_length"]) != line.byte_length
                or int(stored["terminator_length"]) != line.terminator_length
                or str(stored["event_type"]) != record.event_type
                or (
                    float(stored["event_epoch"])
                    if stored["event_epoch"] is not None
                    else None
                )
                != record.event_epoch
                or (
                    str(stored["event_timestamp"])
                    if stored["event_timestamp"] is not None
                    else None
                )
                != record.event_timestamp
                or (
                    str(stored["writer_version"])
                    if stored["writer_version"] is not None
                    else None
                )
                != record.writer_version
            ):
                errors.append(f"RECORD_METADATA_MISMATCH:{line.start_offset}")
            if record.event_timestamp:
                if (
                    actual_oldest_timestamp is None
                    or record.event_timestamp < actual_oldest_timestamp
                ):
                    actual_oldest_timestamp = record.event_timestamp
                if (
                    actual_newest_timestamp is None
                    or record.event_timestamp > actual_newest_timestamp
                ):
                    actual_newest_timestamp = record.event_timestamp
            expected_identities = {
                (
                    item.identity_type,
                    item.identity_value,
                    item.identity_group,
                    item.identity_class,
                )
                for item in record.identities
            }
            actual_identities = {
                (
                    str(row["identity_type"]),
                    str(row["identity_value"]),
                    str(row["identity_group"]),
                    str(row["identity_class"]),
                )
                for row in connection.execute(
                    """
                    SELECT i.identity_type, i.identity_value, i.identity_group, i.identity_class
                    FROM postings p JOIN identities i ON i.identity_id=p.identity_id
                    WHERE p.record_id=?
                    """,
                    (int(stored["record_id"]),),
                )
            }
            if expected_identities != actual_identities:
                errors.append(f"RECORD_IDENTITIES_MISMATCH:{line.start_offset}")
            actual_counts["strong_postings"] += sum(
                1 for item in record.identities if item.identity_class == IDENTITY_CLASS_STRONG
            )
            actual_counts["secondary_postings"] += sum(
                1 for item in record.identities if item.identity_class == IDENTITY_CLASS_SECONDARY
            )
        if records:
            errors.append(f"EXTRA_RECORDS:{segment['segment_id']}")
        for name, actual in actual_counts.items():
            if actual != int(segment[name]):
                errors.append(f"SEGMENT_COUNT_MISMATCH:{segment['segment_id']}:{name}")
        if actual_max_line_bytes != int(segment["max_line_bytes"]):
            errors.append(f"SEGMENT_MAX_LINE_MISMATCH:{segment['segment_id']}")
        if actual_last_line_start_offset != int(segment["last_line_start_offset"]):
            errors.append(f"SEGMENT_LAST_LINE_OFFSET_MISMATCH:{segment['segment_id']}")
        if int(actual_has_long_line) != int(segment["has_long_line"]):
            errors.append(f"SEGMENT_LONG_LINE_MISMATCH:{segment['segment_id']}")
        if int(actual_has_oversized_barrier) != int(segment["has_oversized_barrier"]):
            errors.append(f"SEGMENT_BARRIER_MISMATCH:{segment['segment_id']}")
        stored_oldest = (
            str(segment["oldest_timestamp"])
            if segment["oldest_timestamp"] is not None
            else None
        )
        stored_newest = (
            str(segment["newest_timestamp"])
            if segment["newest_timestamp"] is not None
            else None
        )
        if (
            stored_oldest != actual_oldest_timestamp
            or stored_newest != actual_newest_timestamp
        ):
            errors.append(f"SEGMENT_TIMESTAMP_RANGE_MISMATCH:{segment['segment_id']}")
    return errors


def validate_index(
    source_path: Path | str,
    index_path: Path | str,
    source_id: str,
    *,
    snapshot_eof: Optional[int] = None,
    deep: bool = False,
) -> ValidationResult:
    """Classify a shadow index without modifying either source or index."""

    source = Path(source_path)
    index = Path(index_path)
    expected_source_id = _validate_source_id(source_id)
    if not index.exists():
        return ValidationResult(status=INDEX_MISSING, reasons=("INDEX_FILE_MISSING",), source_id=expected_source_id, deep=deep)
    try:
        connection = _sqlite_connect(index, readonly=True)
    except sqlite3.DatabaseError as exc:
        return ValidationResult(
            status=INDEX_CORRUPT,
            reasons=(f"SQLITE_OPEN_FAILED:{type(exc).__name__}",),
            source_id=expected_source_id,
            deep=deep,
        )
    try:
        tables = _table_names(connection)
        if not REQUIRED_TABLES.issubset(tables):
            return ValidationResult(status=INDEX_CORRUPT, reasons=("REQUIRED_TABLE_MISSING",), source_id=expected_source_id, deep=deep)
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        state = _load_source_state(connection)
        common = {
            "source_id": str(state["source_id"]),
            "state": str(state["state"]),
            "safe_watermark": int(state["safe_watermark"]),
            "generation_uuid": str(state["generation_uuid"]),
            "deep": deep,
        }
        if application_id != SQLITE_APPLICATION_ID or user_version != SCHEMA_VERSION:
            return ValidationResult(status=INDEX_STALE, reasons=("SQLITE_VERSION_MISMATCH",), **common)
        if int(state["schema_version"]) != SCHEMA_VERSION or str(state["index_version"]) != INDEX_VERSION:
            return ValidationResult(status=INDEX_STALE, reasons=("INDEX_VERSION_MISMATCH",), **common)
        if str(state["builder_version"]) != BUILDER_VERSION:
            return ValidationResult(status=INDEX_STALE, reasons=("BUILDER_VERSION_MISMATCH",), **common)
        if str(state["identity_contract_hash"]) != IDENTITY_CONTRACT_HASH:
            return ValidationResult(status=INDEX_STALE, reasons=("IDENTITY_CONTRACT_MISMATCH",), **common)
        if str(state["source_id"]) != expected_source_id:
            return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SOURCE_ID_MISMATCH",), **common)
        if (
            str(state["normalized_path_hash"]) != normalized_path_hash(source)
            or str(state["source_path"]) != _normalized_path(source)
        ):
            return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SOURCE_PATH_MISMATCH",), **common)
        if str(state["state"]) == "CORRUPT":
            return ValidationResult(status=INDEX_CORRUPT, reasons=("STATE_CORRUPT",), **common)
        if str(state["state"]) == "STALE":
            return ValidationResult(status=INDEX_STALE, reasons=("STATE_STALE",), **common)
        invariant_errors = _basic_invariant_errors(connection)
        if invariant_errors:
            return ValidationResult(
                status=INDEX_CORRUPT,
                reasons=tuple(invariant_errors),
                **common,
            )
        try:
            path_stat = _source_stat(source)
            handle = source.open("rb")
        except (FileNotFoundError, OSError, IndexBuildError) as exc:
            return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=(f"SOURCE_UNAVAILABLE:{type(exc).__name__}",), **common)
        with handle:
            descriptor_stat = os.fstat(handle.fileno())
            current_size = int(descriptor_stat.st_size)
            requested_snapshot = current_size if snapshot_eof is None else int(snapshot_eof)
            common.update(source_size=current_size, snapshot_eof=max(0, requested_snapshot))
            if not _same_file(path_stat, descriptor_stat):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("LSTAT_FSTAT_MISMATCH",), **common)
            if str(int(descriptor_stat.st_dev)) != str(state["dev"]) or str(int(descriptor_stat.st_ino)) != str(state["inode"]):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SOURCE_FILE_ID_MISMATCH",), **common)
            watermark = int(state["safe_watermark"])
            if requested_snapshot < 0 or requested_snapshot > current_size:
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SNAPSHOT_OUTSIDE_SOURCE",), **common)
            if current_size < int(state["build_snapshot_eof"]) or current_size < watermark:
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SOURCE_SHRINK",), **common)
            try:
                anchor_bytes = int(state["anchor_bytes"])
                watermark_anchors = _watermark_anchor_values(
                    handle, watermark, anchor_bytes
                )
                prefix_length = int(state["prefix_anchor_length"])
                prefix = (
                    _blake128(_read_exact_range(handle, 0, prefix_length))
                    if prefix_length
                    else _blake128(b"")
                )
                build_snapshot_eof = int(state["build_snapshot_eof"])
                snapshot_tail_length = min(anchor_bytes, build_snapshot_eof)
                snapshot_tail_offset = build_snapshot_eof - snapshot_tail_length
                snapshot_tail = (
                    _blake128(_read_exact_range(handle, snapshot_tail_offset, snapshot_tail_length))
                    if snapshot_tail_length
                    else _blake128(b"")
                )
            except (IndexValidationError, OSError):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("ANCHOR_RANGE_INVALID",), **common)
            if prefix != bytes(state["prefix_anchor"]):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("PREFIX_ANCHOR_MISMATCH",), **common)
            if watermark_anchors["watermark_anchor"] != bytes(state["watermark_anchor"]):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("WATERMARK_ANCHOR_MISMATCH",), **common)
            if snapshot_tail != bytes(state["snapshot_tail_anchor"]):
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("SNAPSHOT_TAIL_ANCHOR_MISMATCH",), **common)
            if watermark and _read_exact_range(handle, watermark - 1, 1) != b"\n":
                return ValidationResult(status=INDEX_SOURCE_CHANGED, reasons=("WATERMARK_NOT_NEWLINE_ALIGNED",), **common)
            last_complete_line_offset = int(state["last_complete_line_offset"])
            if (
                watermark
                and last_complete_line_offset
                and _read_exact_range(handle, last_complete_line_offset - 1, 1) != b"\n"
            ):
                return ValidationResult(
                    status=INDEX_SOURCE_CHANGED,
                    reasons=("LAST_COMPLETE_LINE_BOUNDARY_MISMATCH",),
                    **common,
                )
            if deep:
                deep_errors = _deep_invariant_errors(connection, handle, state)
                if deep_errors:
                    source_mismatch = any(
                        "HASH_MISMATCH" in reason or "SHORT_READ" in reason
                        for reason in deep_errors
                    )
                    return ValidationResult(
                        status=INDEX_SOURCE_CHANGED if source_mismatch else INDEX_CORRUPT,
                        reasons=tuple(deep_errors),
                        **common,
                    )
            try:
                final_descriptor_stat = os.fstat(handle.fileno())
                final_path_stat = _source_stat(source)
            except (FileNotFoundError, OSError, IndexBuildError) as exc:
                return ValidationResult(
                    status=INDEX_SOURCE_CHANGED,
                    reasons=(f"SOURCE_CHANGED_DURING_VALIDATION:{type(exc).__name__}",),
                    **common,
                )
            if not _same_file(final_descriptor_stat, final_path_stat):
                return ValidationResult(
                    status=INDEX_SOURCE_CHANGED,
                    reasons=("SOURCE_REPLACED_DURING_VALIDATION",),
                    **common,
                )
            if int(final_descriptor_stat.st_size) < current_size:
                return ValidationResult(
                    status=INDEX_SOURCE_CHANGED,
                    reasons=("SOURCE_SHRANK_DURING_VALIDATION",),
                    **common,
                )
            if str(state["state"]) in {"BUILDING", "REVALIDATING"}:
                return ValidationResult(status=INDEX_PARTIAL, reasons=(f"STATE_{state['state']}",), **common)
            if watermark < requested_snapshot:
                return ValidationResult(status=INDEX_PARTIAL, reasons=("WATERMARK_BEHIND_SNAPSHOT",), **common)
            return ValidationResult(status=INDEX_COMPLETE_FOR_SNAPSHOT, reasons=(), **common)
    except (sqlite3.DatabaseError, IndexValidationError, KeyError, TypeError, ValueError) as exc:
        return ValidationResult(
            status=INDEX_CORRUPT,
            reasons=(f"INDEX_VALIDATION_FAILED:{type(exc).__name__}",),
            source_id=expected_source_id,
            deep=deep,
        )
    finally:
        connection.close()


def _stored_config(state: sqlite3.Row) -> BuildConfig:
    config = BuildConfig(
        block_bytes=int(state["block_bytes"]),
        segment_target_bytes=int(state["segment_target_bytes"]),
        batch_bytes=int(state["batch_bytes"]),
        batch_lines=int(state["batch_lines"]),
        max_line_bytes=int(state["max_line_bytes"]),
        anchor_bytes=int(state["anchor_bytes"]),
        busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
    )
    config.validate()
    return config


def _prepare_resume(
    source: Path,
    index: Path,
    source_id: str,
    staging_path: Optional[Path],
) -> tuple[Path, sqlite3.Connection, sqlite3.Row, BuildConfig]:
    candidate = staging_path
    if candidate is None:
        candidates = find_staging_indexes(index)
        if len(candidates) > 1:
            raise IndexBuildError(
                "resume requires exactly one staging index or an explicit staging_path"
            )
        if candidates:
            if index.exists():
                try:
                    final_connection = _sqlite_connect(index, readonly=True)
                    try:
                        final_state = str(_load_source_state(final_connection)["state"])
                    finally:
                        final_connection.close()
                except (sqlite3.DatabaseError, IndexValidationError, OSError):
                    final_state = "UNREADABLE"
                if final_state == "REVALIDATING":
                    raise IndexBuildError(
                        "resume is ambiguous: both staging and REVALIDATING final indexes exist"
                    )
            candidate = candidates[0]
        elif index.exists():
            # Atomic replace may have completed immediately before a crash.
            # The final filename then contains state REVALIDATING and is the
            # only safe generation that --resume may finish in place.
            candidate = index
        else:
            raise IndexBuildError(
                "resume requires one staging index or a REVALIDATING final index"
            )
    if not candidate.exists():
        raise IndexBuildError("staging index does not exist")
    validation = validate_index(source, candidate, source_id, deep=False)
    if validation.status not in {INDEX_PARTIAL, INDEX_COMPLETE_FOR_SNAPSHOT}:
        raise IndexBuildError(
            f"staging validation failed: {validation.status}: {validation.reasons}"
        )
    connection = _sqlite_connect(candidate, readonly=False)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        state = _load_source_state(connection)
        state_name = str(state["state"])
        if state_name not in {"BUILDING", "REVALIDATING"}:
            raise IndexBuildError("only BUILDING or REVALIDATING indexes can be resumed")
        is_final_path = _normalized_path(candidate) == _normalized_path(index)
        if is_final_path and state_name != "REVALIDATING":
            raise IndexBuildError("a final-path resume requires state REVALIDATING")
        if not is_final_path:
            expected_staging = _staging_path(index, str(state["generation_uuid"]))
            if _normalized_path(candidate) != _normalized_path(expected_staging):
                raise IndexBuildError("staging filename generation does not match source_state")
        return candidate, connection, state, _stored_config(state)
    except Exception:
        connection.close()
        raise


def _update_resume_snapshot(
    connection: sqlite3.Connection,
    handle: BinaryIO,
    snapshot_eof: int,
    config: BuildConfig,
) -> None:
    tail = _snapshot_tail_anchor(handle, snapshot_eof, config.anchor_bytes)
    connection.execute("BEGIN IMMEDIATE")
    try:
        state = _load_source_state(connection)
        if snapshot_eof < int(state["build_snapshot_eof"]):
            raise IndexBuildError("source shrank below the previous build snapshot")
        connection.execute(
            """
            UPDATE source_state SET
                build_snapshot_eof=?, observed_eof=?, trailing_fragment_bytes=0,
                trailing_fragment_kind=NULL,
                snapshot_tail_anchor=?, snapshot_tail_anchor_offset=?,
                snapshot_tail_anchor_length=?
            WHERE singleton_id=1
            """,
            (
                snapshot_eof,
                snapshot_eof,
                tail["snapshot_tail_anchor"],
                tail["snapshot_tail_anchor_offset"],
                tail["snapshot_tail_anchor_length"],
            ),
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise


def _tail_kind(line: _PhysicalLine, classification: Mapping[str, Any]) -> str:
    if classification["barrier"]:
        return "OVERSIZED"
    if classification["blank"]:
        return "BLANK"
    if classification["invalid_json"]:
        return "INVALID_JSON"
    if classification["invalid_utf8"]:
        return "INVALID_UTF8"
    if classification["mapping"]:
        return "VALID_MAPPING"
    if classification["valid_json"]:
        return "VALID_NONMAPPING"
    return "UNCLASSIFIED"


def _postings_distribution(connection: sqlite3.Connection) -> dict[str, float | int]:
    summary = connection.execute(
        """
        WITH counts AS (
            SELECT r.record_id, COUNT(p.identity_id) AS posting_count
            FROM records r LEFT JOIN postings p ON p.record_id=r.record_id
            GROUP BY r.record_id
        )
        SELECT COUNT(*) AS records, COALESCE(MIN(posting_count), 0) AS minimum,
               COALESCE(AVG(posting_count), 0.0) AS average,
               COALESCE(MAX(posting_count), 0) AS maximum
        FROM counts
        """
    ).fetchone()
    count = int(summary["records"] or 0)
    if not count:
        return {"min": 0, "p50": 0, "avg": 0.0, "p95": 0, "max": 0}

    def percentile(fraction: float) -> int:
        offset = min(count - 1, max(0, math.ceil(count * fraction) - 1))
        row = connection.execute(
            """
            WITH counts AS (
                SELECT r.record_id, COUNT(p.identity_id) AS posting_count
                FROM records r LEFT JOIN postings p ON p.record_id=r.record_id
                GROUP BY r.record_id
            )
            SELECT posting_count FROM counts ORDER BY posting_count LIMIT 1 OFFSET ?
            """,
            (offset,),
        ).fetchone()
        return int(row[0])

    return {
        "min": int(summary["minimum"]),
        "p50": percentile(0.50),
        "avg": round(float(summary["average"]), 6),
        "p95": percentile(0.95),
        "max": int(summary["maximum"]),
    }


def _collect_build_report(
    source: Path,
    database_path: Path,
    *,
    final_index_path: Path,
    staging_path: Optional[Path],
    published: bool,
    duration: float,
    peak_tracemalloc: int,
    committed_batches: int,
    max_batch_bytes: int,
    max_batch_lines: int,
    peak_pending_line_bytes: int,
    processed_source_bytes: int,
    tail_classification: Optional[Mapping[str, Any]],
) -> BuildReport:
    connection = _sqlite_connect(database_path, readonly=True)
    try:
        state = _load_source_state(connection)
        counts = connection.execute(
            """
            SELECT COUNT(*) AS segments,
                   COALESCE(SUM(physical_lines), 0) AS physical_lines,
                   COALESCE(SUM(blank_lines), 0) AS blank_lines,
                   COALESCE(SUM(valid_json_lines), 0) AS valid_json,
                   COALESCE(SUM(invalid_json_lines), 0) AS invalid_json,
                   COALESCE(SUM(invalid_utf8_lines), 0) AS invalid_utf8,
                   COALESCE(SUM(mapping_records), 0) AS mapping_records,
                   COALESCE(SUM(nonmapping_json_lines), 0) AS nonmapping_json,
                   COALESCE(SUM(oversized_barrier_lines), 0) AS oversized_barriers,
                   COALESCE(SUM(strong_postings), 0) AS strong_postings,
                   COALESCE(SUM(secondary_postings), 0) AS secondary_postings
            FROM segments
            """
        ).fetchone()
        identity_count = int(connection.execute("SELECT COUNT(*) FROM identities").fetchone()[0])
        posting_count = int(connection.execute("SELECT COUNT(*) FROM postings").fetchone()[0])
        distribution = _postings_distribution(connection)
        tail_present = int(state["trailing_fragment_bytes"]) > 0
        tail_blank = int(bool(tail_present and tail_classification and tail_classification["blank"]))
        tail_valid = int(bool(tail_present and tail_classification and tail_classification["valid_json"]))
        tail_invalid = int(bool(tail_present and tail_classification and tail_classification["invalid_json"]))
        tail_invalid_utf8 = int(
            bool(tail_present and tail_classification and tail_classification["invalid_utf8"])
        )
        tail_mapping = int(bool(tail_present and tail_classification and tail_classification["mapping"]))
        tail_nonmapping = int(bool(tail_valid and not tail_mapping))
        source_bytes = int(source.stat().st_size)
        db_bytes = int(database_path.stat().st_size)
        wal_path = Path(os.fspath(database_path) + "-wal")
        wal_bytes = int(wal_path.stat().st_size) if wal_path.exists() else 0
        return BuildReport(
            source_path=_normalized_path(source),
            index_path=_normalized_path(final_index_path),
            staging_path=_normalized_path(staging_path) if staging_path is not None else None,
            source_id=str(state["source_id"]),
            generation_uuid=str(state["generation_uuid"]),
            published=published,
            state=str(state["state"]),
            source_bytes=source_bytes,
            processed_source_bytes=processed_source_bytes,
            initial_snapshot_eof=int(state["initial_snapshot_eof"]),
            build_snapshot_eof=int(state["build_snapshot_eof"]),
            safe_watermark=int(state["safe_watermark"]),
            trailing_fragment_bytes=int(state["trailing_fragment_bytes"]),
            total_physical_lines=int(counts["physical_lines"]) + int(tail_present),
            blank_lines=int(counts["blank_lines"]) + tail_blank,
            valid_json=int(counts["valid_json"]) + tail_valid,
            invalid_json=int(counts["invalid_json"]) + tail_invalid,
            invalid_utf8=int(counts["invalid_utf8"]) + tail_invalid_utf8,
            mapping_records=int(counts["mapping_records"]) + tail_mapping,
            nonmapping_json=int(counts["nonmapping_json"]) + tail_nonmapping,
            oversized_barriers=int(counts["oversized_barriers"])
            + int(
                bool(
                    tail_present
                    and (
                        tail_classification is None
                        or tail_classification.get("barrier", False)
                    )
                )
            ),
            segments=int(counts["segments"]),
            unique_identities=identity_count,
            postings=posting_count,
            strong_postings=int(counts["strong_postings"]),
            secondary_postings=int(counts["secondary_postings"]),
            postings_per_record=distribution,
            index_db_bytes=db_bytes,
            db_source_ratio=round(db_bytes / source_bytes, 8) if source_bytes else 0.0,
            wal_bytes=wal_bytes,
            build_duration_seconds=round(duration, 6),
            peak_tracemalloc_bytes=peak_tracemalloc,
            max_rss_bytes=_max_rss_bytes(),
            throughput_mib_per_second=round(
                (processed_source_bytes / (1024 * 1024)) / duration,
                6,
            )
            if duration > 0
            else 0.0,
            committed_batches=committed_batches,
            max_batch_bytes=max_batch_bytes,
            max_batch_lines=max_batch_lines,
            peak_pending_line_bytes=peak_pending_line_bytes,
        )
    finally:
        connection.close()


def build_index(
    source_path: Path | str,
    index_path: Path | str,
    source_id: str,
    *,
    resume: bool = False,
    staging_path: Path | str | None = None,
    config: Optional[BuildConfig] = None,
    publish: bool = True,
    fault_injector: FaultInjector = None,
    measure_memory: bool = True,
) -> BuildReport:
    """Build or resume one explicit shadow index with bounded memory.

    A terminal fragment without a physical newline is reported but remains
    outside the safe watermark.  Such a staging DB is never published READY.
    """

    source = Path(source_path)
    index = Path(index_path)
    identity = _validate_source_id(source_id)
    if _normalized_path(source) == _normalized_path(index):
        raise ValueError("source and index paths must differ")
    selected_config = config or BuildConfig()
    selected_config.validate()
    started = time.perf_counter()
    started_tracemalloc = bool(measure_memory and not tracemalloc.is_tracing())
    if started_tracemalloc:
        tracemalloc.start()
    connection: Optional[sqlite3.Connection] = None
    actual_staging: Optional[Path] = None
    published = False
    committed_batches = 0
    max_batch_bytes_seen = 0
    max_batch_lines_seen = 0
    peak_pending_line_bytes = 0
    processed_source_bytes = 0
    tail_classification: Optional[Mapping[str, Any]] = None
    resuming_revalidating = False
    try:
        path_stat = _source_stat(source)
        with source.open("rb") as handle:
            descriptor_stat = os.fstat(handle.fileno())
            if not _same_file(path_stat, descriptor_stat):
                raise IndexBuildError("source changed between lstat and open")
            if resume:
                actual_staging, connection, state, selected_config = _prepare_resume(
                    source,
                    index,
                    identity,
                    Path(staging_path) if staging_path is not None else None,
                )
                descriptor_stat = os.fstat(handle.fileno())
                if (
                    str(int(descriptor_stat.st_dev)) != str(state["dev"])
                    or str(int(descriptor_stat.st_ino)) != str(state["inode"])
                ):
                    raise IndexBuildError("source file identity changed before resume")
                resuming_revalidating = str(state["state"]) == "REVALIDATING"
                if resuming_revalidating:
                    snapshot_eof = int(state["build_snapshot_eof"])
                    if int(state["safe_watermark"]) != snapshot_eof:
                        raise IndexBuildError(
                            "REVALIDATING index is not complete for its build snapshot"
                        )
                else:
                    snapshot_eof = int(descriptor_stat.st_size)
                    _update_resume_snapshot(connection, handle, snapshot_eof, selected_config)
                    state = _load_source_state(connection)
            else:
                snapshot_eof = int(descriptor_stat.st_size)
                generation_uuid = str(uuid.uuid4())
                actual_staging = _staging_path(index, generation_uuid)
                if actual_staging.exists():
                    raise IndexBuildError("generated staging path already exists")
                connection = _initialize_database(
                    actual_staging,
                    source,
                    identity,
                    generation_uuid,
                    descriptor_stat,
                    snapshot_eof,
                    selected_config,
                )
                state = _load_source_state(connection)

            watermark = int(state["safe_watermark"])
            if watermark and _read_exact_range(handle, watermark - 1, 1) != b"\n":
                raise IndexBuildError("persisted safe watermark is not newline-aligned")
            first_line_number = int(state["last_complete_line_number"]) + 1
            pending_segments: list[_PendingSegment] = []
            current_segment: Optional[_PendingSegment] = None
            batch_bytes_seen = 0
            batch_lines_seen = 0

            def finalize_segment() -> None:
                nonlocal current_segment
                if current_segment is not None and current_segment.physical_lines:
                    pending_segments.append(current_segment)
                current_segment = None

            def commit_batch() -> None:
                nonlocal pending_segments, batch_bytes_seen, batch_lines_seen
                nonlocal committed_batches, max_batch_bytes_seen, max_batch_lines_seen
                if not pending_segments:
                    return
                max_batch_bytes_seen = max(max_batch_bytes_seen, batch_bytes_seen)
                max_batch_lines_seen = max(max_batch_lines_seen, batch_lines_seen)
                _commit_segments(
                    connection,
                    handle,
                    pending_segments,
                    config=selected_config,
                    observed_eof=snapshot_eof,
                    fault_injector=fault_injector,
                )
                committed_batches += 1
                pending_segments = []
                batch_bytes_seen = 0
                batch_lines_seen = 0

            scan_end_offset = watermark if resuming_revalidating else snapshot_eof
            processed_source_bytes = max(0, scan_end_offset - watermark)
            for line in _iter_physical_lines(
                handle,
                start_offset=watermark,
                end_offset=scan_end_offset,
                first_line_number=first_line_number,
                block_bytes=selected_config.block_bytes,
                max_line_bytes=selected_config.max_line_bytes,
            ):
                peak_pending_line_bytes = max(
                    peak_pending_line_bytes,
                    min(line.byte_length, selected_config.max_line_bytes),
                )
                classification = _classify_line(line)
                if not line.terminated:
                    tail_classification = classification if line.raw is not None else None
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        connection.execute(
                            """
                            UPDATE source_state SET trailing_fragment_bytes=?,
                                trailing_fragment_kind=?, observed_eof=?
                            WHERE singleton_id=1
                            """,
                            (
                                line.byte_length,
                                _tail_kind(line, classification),
                                snapshot_eof,
                            ),
                        )
                        connection.execute("COMMIT")
                    except Exception:
                        connection.execute("ROLLBACK")
                        raise
                    break
                if current_segment is None:
                    current_segment = _PendingSegment(
                        start_offset=line.start_offset,
                        first_line_number=line.line_number,
                    )
                current_segment.add_line(line, classification)
                batch_bytes_seen += line.byte_length
                batch_lines_seen += 1
                close_segment = bool(
                    current_segment.byte_length >= selected_config.segment_target_bytes
                    or batch_bytes_seen >= selected_config.batch_bytes
                    or batch_lines_seen >= selected_config.batch_lines
                )
                if close_segment:
                    finalize_segment()
                if (
                    batch_bytes_seen >= selected_config.batch_bytes
                    or batch_lines_seen >= selected_config.batch_lines
                ):
                    finalize_segment()
                    commit_batch()

            finalize_segment()
            commit_batch()
            final_descriptor = os.fstat(handle.fileno())
            final_path_stat = _source_stat(source)
            if not _same_file(descriptor_stat, final_descriptor) or not _same_file(
                descriptor_stat, final_path_stat
            ):
                raise IndexBuildError("source changed generation during build")
            if int(final_descriptor.st_size) < snapshot_eof:
                raise IndexBuildError("source shrank during build")
            state = _load_source_state(connection)
            complete_for_build_snapshot = int(state["safe_watermark"]) == int(
                state["build_snapshot_eof"]
            )
            if complete_for_build_snapshot and not resuming_revalidating:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        UPDATE source_state SET state='REVALIDATING', observed_eof=?,
                            trailing_fragment_bytes=0, trailing_fragment_kind=NULL
                        WHERE singleton_id=1
                        """,
                        (int(final_descriptor.st_size),),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
            _invoke_fault(
                fault_injector,
                "after_build_before_publish",
                safe_watermark=int(state["safe_watermark"]),
                snapshot_eof=int(state["build_snapshot_eof"]),
            )
        if connection is None or actual_staging is None:
            raise IndexBuildError("builder did not create or open a staging database")
        connection.close()
        connection = None
        prepublish = validate_index(source, actual_staging, identity, deep=True)
        if prepublish.status not in {INDEX_PARTIAL, INDEX_COMPLETE_FOR_SNAPSHOT}:
            raise IndexBuildError(
                f"staging deep validation failed: {prepublish.status}: {prepublish.reasons}"
            )
        state_connection = _sqlite_connect(actual_staging, readonly=True)
        try:
            final_state = _load_source_state(state_connection)
            can_publish = bool(
                str(final_state["state"]) == "REVALIDATING"
                and int(final_state["safe_watermark"])
                == int(final_state["build_snapshot_eof"])
            )
        finally:
            state_connection.close()
        database_path = actual_staging
        if publish and can_publish:
            if _normalized_path(actual_staging) == _normalized_path(index):
                _finish_revalidating_final(source, index, identity)
            else:
                _publish_staging(
                    source,
                    index,
                    actual_staging,
                    identity,
                    fault_injector=fault_injector,
                )
            published = True
            database_path = index
            actual_staging_for_report: Optional[Path] = None
        else:
            actual_staging_for_report = (
                None
                if _normalized_path(actual_staging) == _normalized_path(index)
                else actual_staging
            )
        duration = max(time.perf_counter() - started, 1e-9)
        peak = tracemalloc.get_traced_memory()[1] if measure_memory and tracemalloc.is_tracing() else 0
        return _collect_build_report(
            source,
            database_path,
            final_index_path=index,
            staging_path=actual_staging_for_report,
            published=published,
            duration=duration,
            peak_tracemalloc=peak,
            committed_batches=committed_batches,
            max_batch_bytes=max_batch_bytes_seen,
            max_batch_lines=max_batch_lines_seen,
            peak_pending_line_bytes=peak_pending_line_bytes,
            processed_source_bytes=processed_source_bytes,
            tail_classification=tail_classification,
        )
    finally:
        if connection is not None:
            connection.close()
        if started_tracemalloc and tracemalloc.is_tracing():
            tracemalloc.stop()


def _identity_for_lookup(identity_type: Any, identity_value: Any) -> tuple[str, str]:
    canonical_type = canonical_identity_key(identity_type)
    value = str(identity_value).strip() if identity_value is not None else ""
    if not value:
        raise ValueError("identity_value is required")
    # Classification is the one shared immutable contract.  This rejects
    # unsafe/unknown types and legacy derived ``*-DS`` client IDs rather than
    # silently turning an empty lookup into apparent absence.
    if classify_identity(canonical_type, value) is None:
        raise ValueError("identity type is not indexable")
    return canonical_type, value


def lookup_records(
    index_path: Path | str,
    identity_type: str,
    identity_value: str,
    start_offset: int,
    end_offset: int,
) -> tuple[IndexedRecordMetadata, ...]:
    """Return ordered shadow candidates; no ownership decision is performed."""

    index = Path(index_path)
    canonical_type, value = _identity_for_lookup(identity_type, identity_value)
    start = int(start_offset)
    end = int(end_offset)
    if start < 0 or end < start:
        raise ValueError("invalid lookup range")
    connection = _sqlite_connect(index, readonly=True)
    try:
        state = _load_source_state(connection)
        safe_end = min(end, int(state["safe_watermark"]))
        if safe_end <= start:
            return ()
        rows = connection.execute(
            """
            SELECT r.record_id, r.line_number, r.start_offset, r.byte_length,
                   r.terminator_length, r.event_type, r.event_epoch,
                   r.event_timestamp, r.writer_version, r.record_hash,
                   i.identity_type, i.identity_value, i.identity_group, i.identity_class
            FROM identities i
            JOIN postings p ON p.identity_id=i.identity_id
            JOIN records r ON r.record_id=p.record_id
            WHERE i.identity_type=? AND i.identity_value=?
              AND p.start_offset>=? AND p.start_offset<?
            ORDER BY p.start_offset, p.record_id
            """,
            (canonical_type, value, start, safe_end),
        ).fetchall()
        return tuple(
            IndexedRecordMetadata(
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
                event_epoch=(
                    float(row["event_epoch"])
                    if row["event_epoch"] is not None
                    else None
                ),
                event_timestamp=(
                    str(row["event_timestamp"])
                    if row["event_timestamp"] is not None
                    else None
                ),
            )
            for row in rows
        )
    finally:
        connection.close()


def lookup_offsets(
    index_path: Path | str,
    identity_type: str,
    identity_value: str,
    start_offset: int,
    end_offset: int,
) -> tuple[int, ...]:
    return tuple(
        row.start_offset
        for row in lookup_records(
            index_path,
            identity_type,
            identity_value,
            start_offset,
            end_offset,
        )
    )


def _read_exact_record_bytes(handle: BinaryIO, metadata: IndexedRecordMetadata) -> bytes:
    if metadata.start_offset < 0 or metadata.byte_length <= 0:
        raise IndexValidationError("invalid record offset metadata")
    if metadata.start_offset:
        preceding = _read_exact_range(handle, metadata.start_offset - 1, 1)
        if preceding != b"\n":
            raise IndexValidationError("record offset is not a physical line boundary")
    raw = _read_exact_range(handle, metadata.start_offset, metadata.byte_length)
    if not raw.endswith(b"\n") or b"\n" in raw[:-1]:
        raise IndexValidationError("record length is not one newline-terminated physical line")
    actual_terminator = 2 if raw.endswith(b"\r\n") else 1
    if actual_terminator != metadata.terminator_length:
        raise IndexValidationError("record terminator does not match indexed metadata")
    if _blake128(raw) != metadata.record_hash:
        raise IndexValidationError("record hash does not match journal bytes")
    return raw


def read_and_verify_record(
    source_fd: BinaryIO,
    record_metadata: IndexedRecordMetadata,
) -> Mapping[str, Any]:
    """Relocate and verify one factual journal Mapping from shadow metadata."""

    raw = _read_exact_record_bytes(source_fd, record_metadata)
    try:
        value = json.loads(raw[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IndexValidationError("indexed factual record is not valid UTF-8 JSON") from exc
    if not isinstance(value, Mapping):
        raise IndexValidationError("indexed factual record is not a JSON Mapping")
    if _event_type(value) != record_metadata.event_type:
        raise IndexValidationError("event type does not match indexed metadata")
    event_epoch, event_timestamp = _first_event_timestamp(value)
    if (
        event_epoch != record_metadata.event_epoch
        or event_timestamp != record_metadata.event_timestamp
    ):
        raise IndexValidationError("event timestamp does not match indexed metadata")
    if _writer_version(value) != record_metadata.writer_version:
        raise IndexValidationError("writer version does not match indexed metadata")
    if record_metadata.identity_type is not None:
        actual = {
            (
                item.identity_type,
                item.identity_value,
                item.identity_group,
                item.identity_class,
            )
            for item in extract_typed_identities(value)
        }
        expected = (
            record_metadata.identity_type,
            record_metadata.identity_value or "",
            record_metadata.identity_group,
            record_metadata.identity_class,
        )
        if expected not in actual:
            raise IndexValidationError(
                "queried typed identity taxonomy is absent from factual record"
            )
    return value


def _shadow_identity_rank(identity: tuple[str, str]) -> bytes:
    payload = (identity[0] + "\x00" + identity[1]).encode(
        "utf-8", errors="surrogatepass"
    )
    return hashlib.blake2b(payload, digest_size=HASH_BYTES).digest()


def _select_stratified_shadow_identities(
    candidates: Mapping[str, Mapping[tuple[str, str], Sequence[tuple[int, str, str]]]],
    limit: int,
) -> tuple[tuple[str, str], ...]:
    if limit <= 0:
        return ()
    strong = sorted(
        candidates.get(IDENTITY_CLASS_STRONG, {}), key=_shadow_identity_rank
    )
    secondary = sorted(
        candidates.get(IDENTITY_CLASS_SECONDARY, {}), key=_shadow_identity_rank
    )
    strong_quota = (limit + 1) // 2
    secondary_quota = limit // 2
    chosen = strong[:strong_quota] + secondary[:secondary_quota]
    chosen_set = set(chosen)
    remainder = sorted(
        (item for item in strong + secondary if item not in chosen_set),
        key=_shadow_identity_rank,
    )
    chosen.extend(remainder[: max(0, limit - len(chosen))])
    return tuple(chosen[:limit])


def verify_shadow(
    source_path: Path | str,
    index_path: Path | str,
    identities: Optional[Sequence[tuple[str, str]]] = None,
    *,
    start_offset: int = 0,
    end_offset: Optional[int] = None,
    sample_limit: int = 100,
    mismatch_limit: int = 100,
) -> ShadowVerificationResult:
    """Compare indexed postings with a full forward enumeration through W."""

    source = Path(source_path)
    index = Path(index_path)
    if sample_limit < 0:
        raise ValueError("sample_limit must be non-negative")
    if mismatch_limit <= 0:
        raise ValueError("mismatch_limit must be positive")
    explicit_sampling = identities is not None
    normalized_identities = tuple(
        dict.fromkeys(
            _identity_for_lookup(identity_type, identity_value)
            for identity_type, identity_value in tuple(identities or ())
        )
    )
    selected = set(normalized_identities)
    connection = _sqlite_connect(index, readonly=True)
    try:
        state = _load_source_state(connection)
        watermark = int(state["safe_watermark"])
        block_bytes = int(state["block_bytes"])
        max_line_bytes = int(state["max_line_bytes"])
    finally:
        connection.close()
    start = int(start_offset)
    scope_end = watermark if end_offset is None else min(int(end_offset), watermark)
    if start < 0 or scope_end < start:
        raise ValueError("invalid verification range")
    forward: dict[tuple[str, str], list[tuple[int, str, str]]] = (
        {item: [] for item in normalized_identities} if explicit_sampling else {}
    )
    candidate_forward: dict[
        str, dict[tuple[str, str], list[tuple[int, str, str]]]
    ] = {
        IDENTITY_CLASS_STRONG: {},
        IDENTITY_CLASS_SECONDARY: {},
    }
    forward_started = time.perf_counter()
    with source.open("rb") as handle:
        source_stat = os.fstat(handle.fileno())
        if scope_end > int(source_stat.st_size):
            raise IndexValidationError("verification scope exceeds source size")
        if start and _read_exact_range(handle, start - 1, 1) != b"\n":
            raise IndexValidationError("verification start is not a physical line boundary")
        if scope_end and _read_exact_range(handle, scope_end - 1, 1) != b"\n":
            raise IndexValidationError("verification end is not a physical line boundary")
        for line in _iter_physical_lines(
            handle,
            start_offset=start,
            end_offset=scope_end,
            first_line_number=1,
            block_bytes=block_bytes,
            max_line_bytes=max_line_bytes,
        ):
            if not line.terminated:
                raise IndexValidationError("safe verification scope ended inside a line")
            classification = _classify_line(line)
            record = classification.get("record")
            if record is None:
                continue
            occurrence = (line.start_offset, line.line_hash.hex(), record.event_type)
            if explicit_sampling:
                present = {
                    (item.identity_type, item.identity_value) for item in record.identities
                }
                for identity in selected & present:
                    forward[identity].append(occurrence)
            else:
                for item in record.identities:
                    identity = (item.identity_type, item.identity_value)
                    bucket = candidate_forward[item.identity_class]
                    existing = bucket.get(identity)
                    if existing is not None:
                        existing.append(occurrence)
                        continue
                    if sample_limit == 0:
                        continue
                    if len(bucket) >= sample_limit:
                        worst = max(bucket, key=_shadow_identity_rank)
                        if _shadow_identity_rank(identity) >= _shadow_identity_rank(worst):
                            continue
                        del bucket[worst]
                    bucket[identity] = [occurrence]
    forward_duration_ms = (time.perf_counter() - forward_started) * 1000.0

    if not explicit_sampling:
        normalized_identities = _select_stratified_shadow_identities(
            candidate_forward, sample_limit
        )
        selected = set(normalized_identities)
        forward = {
            identity: list(
                candidate_forward[
                    classify_identity(identity[0], identity[1]) or ""
                ][identity]
            )
            for identity in normalized_identities
        }

    lookup_started = time.perf_counter()
    indexed: dict[tuple[str, str], list[tuple[int, str, str]]] = {}
    indexed_records: dict[tuple[str, str], tuple[IndexedRecordMetadata, ...]] = {}
    for identity_type, identity_value in normalized_identities:
        rows = lookup_records(index, identity_type, identity_value, start, scope_end)
        indexed_records[(identity_type, identity_value)] = rows
        indexed[(identity_type, identity_value)] = [
            (row.start_offset, row.record_hash.hex(), row.event_type) for row in rows
        ]
    lookup_duration_ms = (time.perf_counter() - lookup_started) * 1000.0

    mismatches: list[Mapping[str, Any]] = []
    for identity in normalized_identities:
        if indexed.get(identity, []) != forward.get(identity, []):
            mismatches.append(
                {
                    "identity_type": identity[0],
                    "identity_value": identity[1],
                    "index": indexed.get(identity, []),
                    "forward": forward.get(identity, []),
                }
            )
            if len(mismatches) >= mismatch_limit:
                break

    factual_record_bytes = 0
    verified_records: dict[int, Mapping[str, Any]] = {}
    with source.open("rb") as handle:
        for rows in indexed_records.values():
            for row in rows:
                factual = verified_records.get(row.record_id)
                if factual is None:
                    factual = read_and_verify_record(handle, row)
                    verified_records[row.record_id] = factual
                    factual_record_bytes += row.byte_length
                elif (
                    row.identity_type,
                    row.identity_value,
                    row.identity_group,
                    row.identity_class,
                ) not in {
                    (
                        item.identity_type,
                        item.identity_value,
                        item.identity_group,
                        item.identity_class,
                    )
                    for item in extract_typed_identities(factual)
                }:
                    raise IndexValidationError(
                        "queried typed identity is absent from cached factual record"
                    )
    return ShadowVerificationResult(
        ok=not mismatches,
        source_path=_normalized_path(source),
        index_path=_normalized_path(index),
        scope_start=start,
        scope_end=scope_end,
        identities_checked=len(normalized_identities),
        sampled_strong_identities=sum(
            1
            for identity in normalized_identities
            if classify_identity(identity[0], identity[1]) == IDENTITY_CLASS_STRONG
        ),
        sampled_secondary_identities=sum(
            1
            for identity in normalized_identities
            if classify_identity(identity[0], identity[1]) == IDENTITY_CLASS_SECONDARY
        ),
        sampling_mode=("EXPLICIT" if explicit_sampling else "SOURCE_STRATIFIED_BOTTOM_K"),
        index_offsets=sum(len(value) for value in indexed.values()),
        forward_offsets=sum(len(value) for value in forward.values()),
        mismatches=tuple(mismatches),
        full_forward_bytes=scope_end - start,
        factual_record_bytes=factual_record_bytes,
        lookup_duration_ms=round(lookup_duration_ms, 6),
        forward_duration_ms=round(forward_duration_ms, 6),
    )


__all__ = (
    "BUILDER_VERSION",
    "BuildConfig",
    "BuildReport",
    "DEFAULT_ANCHOR_BYTES",
    "DEFAULT_BATCH_BYTES",
    "DEFAULT_BATCH_LINES",
    "DEFAULT_BLOCK_BYTES",
    "DEFAULT_MAX_LINE_BYTES",
    "DEFAULT_SEGMENT_TARGET_BYTES",
    "INDEX_COMPLETE_FOR_SNAPSHOT",
    "INDEX_CORRUPT",
    "INDEX_MISSING",
    "INDEX_PARTIAL",
    "INDEX_SOURCE_CHANGED",
    "INDEX_STALE",
    "INDEX_VERSION",
    "IndexBuildError",
    "IndexedRecordMetadata",
    "IndexValidationError",
    "SCHEMA_VERSION",
    "SOURCE_IDS",
    "ShadowVerificationResult",
    "ValidationResult",
    "build_index",
    "find_staging_indexes",
    "lookup_offsets",
    "lookup_records",
    "normalized_path_hash",
    "read_and_verify_record",
    "validate_index",
    "verify_shadow",
)
