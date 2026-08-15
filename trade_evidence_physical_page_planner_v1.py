"""Offline physical-page planner for Trade Evidence Index schema V2.

The planner reproduces only the physical window and coverage metadata of the
legacy reverse JSONL reader.  It never selects trade evidence and is not wired
to an HTTP/runtime path.  Fully covered certified segments are summarized from
SQLite; only the byte-budget edge, partial segments, and an uncertified tail
are read from the factual journal.

Uncertainty is explicit: no plan is returned as reproducible when the V2
contract, certification, source generation, boundary budget, or segment
summaries cannot prove exact equivalence.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Mapping, Optional

from trade_evidence_physical_window_contract_v1 import (
    BLOCK_BYTES,
    BYTE_BUDGET,
    CURSOR_CONTRACT_VERSION,
    DIRECTION,
    PHYSICAL_CONTRACT_HASH,
    PHYSICAL_CONTRACT_VERSION,
    RECORD_BUDGET,
    SUMMARY_CONTRACT_VERSION,
    classify_physical_line,
    decode_scan_cursor,
    encode_scan_cursor,
    path_fingerprint,
)


PLANNER_VERSION = "2026-08-15-TRADE-EVIDENCE-PHYSICAL-PAGE-PLANNER-V1"
REPRODUCIBLE = "REPRODUCIBLE"
NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"

DEFAULT_MAX_BOUNDARY_SCAN_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_SEGMENT_ROWS = 4096
DEFAULT_MAX_APPEND_PROOF_BYTES = 8 * 1024 * 1024

_CERTIFIED_KINDS = frozenset(
    {"DEEP_BASELINE", "DEEP_BASELINE_PLUS_PROVEN_APPEND"}
)

FaultInjector = Optional[Callable[[str, Mapping[str, Any]], None]]


class _PlanningRefused(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PhysicalPagePlan:
    status: str
    reason: Optional[str]
    page_start: int
    page_end: int
    snapshot_eof: int
    source_size_bytes: int
    bytes_scanned: int
    lines_scanned: int
    records_examined: int
    blank_lines: int
    valid_lines: int
    invalid_lines: int
    invalid_utf8: int
    invalid_json: int
    mapping_records: int
    nonmapping_json: int
    time_range_scanned: Mapping[str, Optional[str]]
    stop_reason: str
    coverage_complete: bool
    coverage_limited: bool
    partial: bool
    conclusive: bool
    evidence_status: str
    next_end: Optional[int]
    next_scan_cursor: Optional[str]
    cursor_inputs: Mapping[str, Any]
    oversized: bool
    tainted: bool
    boundary_scan_bytes: int
    validation_bytes: int
    segment_rows_consulted: int
    planner_mode: str
    certified_watermark: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def legacy_physical_metadata(self) -> dict[str, Any]:
        """Project the fields emitted directly by ``_read_path``."""

        return {
            "lines_scanned": self.lines_scanned,
            "valid_lines": self.valid_lines,
            "invalid_lines": self.invalid_lines,
            "partial": self.partial,
            "bytes_scanned": self.bytes_scanned,
            "coverage_limited": self.coverage_limited,
            "coverage_complete": self.coverage_complete,
            "conclusive": self.conclusive,
            "records_examined": self.records_examined,
            "direction": DIRECTION,
            "time_range_scanned": dict(self.time_range_scanned),
            "stop_reason": self.stop_reason,
            "source_size_bytes": self.source_size_bytes,
            "snapshot_eof": self.snapshot_eof,
            "next_scan_cursor": self.next_scan_cursor,
            "evidence_status": self.evidence_status,
        }


@dataclass
class _Counts:
    lines_scanned: int = 0
    records_examined: int = 0
    blank_lines: int = 0
    valid_lines: int = 0
    invalid_lines: int = 0
    invalid_utf8: int = 0
    invalid_json: int = 0
    mapping_records: int = 0
    nonmapping_json: int = 0
    oldest: Optional[str] = None
    newest: Optional[str] = None

    def add_timestamp(self, value: Optional[str]) -> None:
        if not value:
            return
        if self.oldest is None or value < self.oldest:
            self.oldest = value
        if self.newest is None or value > self.newest:
            self.newest = value

    def add_segment(self, row: Mapping[str, Any]) -> None:
        self.lines_scanned += int(row["physical_lines"])
        self.records_examined += int(row["records_examined_lines"])
        self.blank_lines += int(row["blank_lines"])
        self.valid_lines += int(row["valid_json_lines"])
        invalid_utf8 = int(row["invalid_utf8_lines"])
        invalid_json = int(row["invalid_json_lines"])
        self.invalid_utf8 += invalid_utf8
        self.invalid_json += invalid_json
        self.invalid_lines += invalid_utf8 + invalid_json
        self.mapping_records += int(row["mapping_records"])
        self.nonmapping_json += int(row["nonmapping_json_lines"])
        self.add_timestamp(
            str(row["oldest_timestamp"])
            if row["oldest_timestamp"] is not None
            else None
        )
        self.add_timestamp(
            str(row["newest_timestamp"])
            if row["newest_timestamp"] is not None
            else None
        )

    def add_line(self, raw_document: bytes) -> None:
        classification = classify_physical_line(raw_document)
        self.lines_scanned += 1
        self.records_examined += classification.records_examined
        self.blank_lines += int(classification.blank)
        self.valid_lines += classification.valid_lines
        self.invalid_lines += classification.invalid_lines
        self.invalid_utf8 += int(classification.invalid_utf8)
        self.invalid_json += int(classification.invalid_json)
        self.mapping_records += int(classification.mapping)
        self.nonmapping_json += int(classification.nonmapping_json)
        self.add_timestamp(classification.event_timestamp)

    def apply_replay_classification(self, replay: "_Counts") -> None:
        """Keep reverse-selection counts but use legacy forward-replay parsing."""

        self.valid_lines = replay.valid_lines
        self.invalid_lines = replay.invalid_lines
        self.invalid_utf8 = replay.invalid_utf8
        self.invalid_json = replay.invalid_json
        self.mapping_records = replay.mapping_records
        self.nonmapping_json = replay.nonmapping_json
        self.oldest = replay.oldest
        self.newest = replay.newest


@dataclass
class _Metrics:
    boundary_scan_bytes: int = 0
    validation_bytes: int = 0
    segment_rows_consulted: int = 0


def _oldest_loaded_chunk_length(bytes_scanned: int, block_bytes: int) -> int:
    if bytes_scanned <= 0:
        return 0
    remainder = bytes_scanned % block_bytes
    return remainder or min(block_bytes, bytes_scanned)


def _legacy_replay_start(
    page_start: int,
    page_end: int,
    bytes_scanned: int,
    block_bytes: int,
) -> int:
    """Mirror the legacy replay offset, including its first-chunk quirk."""

    loaded_start = page_end - bytes_scanned
    first_chunk_length = _oldest_loaded_chunk_length(bytes_scanned, block_bytes)
    replay_offset = max(0, page_start - loaded_start)
    return loaded_start + min(replay_offset, first_chunk_length)


def _legacy_lost_boundary_blank_lines(
    reader: "_BoundedReader",
    page_start: int,
    page_end: int,
    bytes_scanned: int,
    block_bytes: int,
) -> int:
    """Count empty lines skipped by the legacy reverse chunk state machine."""

    if bytes_scanned <= 0:
        return 0
    loaded_start = page_end - bytes_scanned
    boundary = loaded_start + _oldest_loaded_chunk_length(
        bytes_scanned,
        block_bytes,
    )
    lost = 0
    while boundary < page_end:
        if (
            boundary >= page_start
            and boundary > 0
            and reader.read(boundary - 1, boundary + 1) == b"\n\n"
        ):
            lost += 1
        boundary += block_bytes
    return lost


@dataclass
class _BoundedReader:
    handle: BinaryIO
    maximum_bytes: int
    metrics: _Metrics
    cache: list[tuple[int, int, bytes]] = field(default_factory=list)

    def read(self, start: int, end: int) -> bytes:
        if start < 0 or end < start:
            raise _PlanningRefused("BOUNDARY_RANGE_INVALID")
        for cached_start, cached_end, value in self.cache:
            if cached_start <= start and end <= cached_end:
                relative_start = start - cached_start
                return value[relative_start : relative_start + (end - start)]
        length = end - start
        if self.metrics.boundary_scan_bytes + length > self.maximum_bytes:
            raise _PlanningRefused("BOUNDARY_SCAN_LIMIT")
        self.handle.seek(start, os.SEEK_SET)
        value = self.handle.read(length)
        self.metrics.boundary_scan_bytes += len(value)
        if len(value) != length:
            raise _PlanningRefused("SOURCE_SHORT_READ")
        self.cache.append((start, end, value))
        return value


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _blake128(value: bytes) -> bytes:
    return hashlib.blake2b(value, digest_size=16).digest()


def _sqlite_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=0.05)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("BEGIN")
    return connection


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    }


def _read_validation_range(
    handle: BinaryIO,
    start: int,
    length: int,
    metrics: _Metrics,
) -> bytes:
    if start < 0 or length < 0:
        raise _PlanningRefused("CERTIFIED_ANCHOR_RANGE_INVALID")
    handle.seek(start, os.SEEK_SET)
    value = handle.read(length)
    metrics.validation_bytes += len(value)
    if len(value) != length:
        raise _PlanningRefused("CERTIFIED_ANCHOR_SHORT_READ")
    return value


def _validate_v2_state(
    connection: sqlite3.Connection,
    handle: BinaryIO,
    source: Path,
    source_id: str,
    descriptor: os.stat_result,
    metrics: _Metrics,
    max_segment_rows: int,
) -> sqlite3.Row:
    import trade_evidence_identity_offset_index_v1 as index_v1

    required_state = {
        "physical_contract_hash",
        "physical_contract_version",
        "cursor_contract_version",
        "summary_contract_version",
        "certified_watermark",
        "certification_kind",
        "certified_at",
        "certified_anchor",
        "certified_anchor_offset",
        "certified_anchor_length",
        "certified_summary_hash",
        "certified_source_size",
        "certified_source_mtime_ns",
        "certified_source_ctime_ns",
    }
    if not required_state.issubset(_table_columns(connection, "source_state")):
        raise _PlanningRefused("SCHEMA_V2_REQUIRED")
    if "records_examined_lines" not in _table_columns(connection, "segments"):
        raise _PlanningRefused("SUMMARY_V2_REQUIRED")
    application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
    user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if application_id != int(index_v1.SQLITE_APPLICATION_ID):
        raise _PlanningRefused("SQLITE_APPLICATION_ID_MISMATCH")
    if user_version != int(index_v1.SCHEMA_VERSION_V2):
        raise _PlanningRefused("SCHEMA_V2_REQUIRED")
    state = connection.execute(
        "SELECT * FROM source_state WHERE singleton_id=1"
    ).fetchone()
    if state is None:
        raise _PlanningRefused("SOURCE_STATE_MISSING")
    if int(state["schema_version"]) != int(index_v1.SCHEMA_VERSION_V2):
        raise _PlanningRefused("SCHEMA_VERSION_MISMATCH")
    if str(state["index_version"]) != str(index_v1.INDEX_VERSION_V2):
        raise _PlanningRefused("INDEX_VERSION_MISMATCH")
    if str(state["builder_version"]) != str(index_v1.BUILDER_VERSION_V2):
        raise _PlanningRefused("BUILDER_VERSION_MISMATCH")
    if str(state["physical_contract_hash"]) != PHYSICAL_CONTRACT_HASH:
        raise _PlanningRefused("PHYSICAL_CONTRACT_MISMATCH")
    if str(state["physical_contract_version"]) != PHYSICAL_CONTRACT_VERSION:
        raise _PlanningRefused("PHYSICAL_CONTRACT_VERSION_MISMATCH")
    if int(state["cursor_contract_version"]) != CURSOR_CONTRACT_VERSION:
        raise _PlanningRefused("CURSOR_CONTRACT_MISMATCH")
    if int(state["summary_contract_version"]) != SUMMARY_CONTRACT_VERSION:
        raise _PlanningRefused("SUMMARY_CONTRACT_MISMATCH")
    if str(state["source_id"]) != str(source_id):
        raise _PlanningRefused("SOURCE_ID_MISMATCH")
    if (
        str(state["source_path"]) != _normalized_path(source)
        or str(state["normalized_path_hash"]) != index_v1.normalized_path_hash(source)
    ):
        raise _PlanningRefused("SOURCE_PATH_MISMATCH")
    if str(state["state"]) != "READY":
        raise _PlanningRefused("INDEX_NOT_READY")
    try:
        generation = str(uuid.UUID(str(state["generation_uuid"])))
    except (ValueError, AttributeError) as exc:
        raise _PlanningRefused("GENERATION_UUID_INVALID") from exc
    if generation != str(state["generation_uuid"]):
        raise _PlanningRefused("GENERATION_UUID_INVALID")
    if str(state["certification_kind"]) not in _CERTIFIED_KINDS:
        raise _PlanningRefused("INDEX_V2_UNCERTIFIED")
    if not state["certified_at"]:
        raise _PlanningRefused("CERTIFICATION_TIMESTAMP_MISSING")
    certified = int(state["certified_watermark"])
    safe = int(state["safe_watermark"])
    if not 0 <= certified <= safe:
        raise _PlanningRefused("CERTIFIED_WATERMARK_INVALID")
    sealed_rows = int(
        connection.execute(
            "SELECT COUNT(*) FROM segments WHERE start_offset < ?",
            (certified,),
        ).fetchone()[0]
    )
    metrics.segment_rows_consulted += sealed_rows
    if metrics.segment_rows_consulted > max_segment_rows:
        raise _PlanningRefused("SEGMENT_ROW_LIMIT")
    if not index_v1.verify_certified_summary_hash(connection):
        raise _PlanningRefused("CERTIFIED_SUMMARY_HASH_MISMATCH")
    if str(int(descriptor.st_dev)) != str(state["dev"]) or str(
        int(descriptor.st_ino)
    ) != str(state["inode"]):
        raise _PlanningRefused("SOURCE_FILE_ID_MISMATCH")
    certified_size = int(state["certified_source_size"])
    if certified_size < certified or int(descriptor.st_size) < certified_size:
        raise _PlanningRefused("SOURCE_SHRINK")
    # C0 has no writer-generation witness capable of distinguishing an append
    # from a rewrite-plus-append.  Therefore a source that changed after its
    # certification snapshot is not declared equivalent.  A future tail
    # contract may relax this only after it has an independently proven append
    # witness; sparse anchors alone are insufficient.
    if int(descriptor.st_size) != certified_size:
        raise _PlanningRefused("SOURCE_CHANGED_AFTER_CERTIFICATION")
    if (
        int(descriptor.st_mtime_ns) != int(state["certified_source_mtime_ns"])
        or int(descriptor.st_ctime_ns) != int(state["certified_source_ctime_ns"])
    ):
        raise _PlanningRefused("CERTIFIED_SOURCE_METADATA_MISMATCH")
    anchor_length = int(state["certified_anchor_length"])
    anchor_offset = int(state["certified_anchor_offset"])
    expected_length = min(int(state["anchor_bytes"]), certified)
    if (
        anchor_length != expected_length
        or anchor_offset != certified - expected_length
        or len(bytes(state["certified_anchor"])) != 16
    ):
        raise _PlanningRefused("CERTIFIED_ANCHOR_SHAPE")
    actual_anchor = _blake128(
        _read_validation_range(handle, anchor_offset, anchor_length, metrics)
    )
    if actual_anchor != bytes(state["certified_anchor"]):
        raise _PlanningRefused("CERTIFIED_ANCHOR_MISMATCH")
    if certified:
        if _read_validation_range(handle, certified - 1, 1, metrics) != b"\n":
            raise _PlanningRefused("CERTIFIED_WATERMARK_NOT_ALIGNED")
        segment_end = connection.execute(
            "SELECT 1 FROM segments WHERE end_offset=? LIMIT 1", (certified,)
        ).fetchone()
        if segment_end is None:
            raise _PlanningRefused("CERTIFIED_SEGMENT_BOUNDARY_MISSING")
    return state


def _iter_documents(data: bytes, base_offset: int) -> Iterable[tuple[int, bytes]]:
    cursor = 0
    while cursor < len(data):
        newline = data.find(b"\n", cursor)
        if newline < 0:
            yield base_offset + cursor, data[cursor:]
            return
        yield base_offset + cursor, data[cursor:newline]
        cursor = newline + 1


def _find_nth_nonblank_from_end(
    data: bytes,
    base_offset: int,
    ordinal: int,
) -> Optional[int]:
    if ordinal <= 0:
        raise ValueError("ordinal must be positive")
    cursor = len(data)
    if cursor and data.endswith(b"\n"):
        cursor -= 1
    while cursor >= 0:
        previous = data.rfind(b"\n", 0, cursor)
        start = previous + 1
        if data[start:cursor].strip():
            ordinal -= 1
            if ordinal == 0:
                return base_offset + start
        if previous < 0:
            return None
        cursor = previous
    return None


def _count_nonblank(data: bytes) -> int:
    return sum(1 for _offset, raw in _iter_documents(data, 0) if raw.strip())


def _first_lf_after_region(
    reader: _BoundedReader,
    start: int,
    end: int,
    block_bytes: int,
) -> Optional[int]:
    offset = start
    while offset < end:
        block_end = min(end, offset + block_bytes)
        chunk = reader.read(offset, block_end)
        newline = chunk.find(b"\n")
        if newline >= 0:
            return offset + newline
        offset = block_end
    return None


def _previous_lf_from_page_end(
    reader: _BoundedReader,
    region_start: int,
    page_end: int,
    block_bytes: int,
) -> tuple[Optional[int], int]:
    offset = page_end
    legacy_bytes = 0
    while offset > region_start:
        block_start = max(region_start, offset - block_bytes)
        chunk = reader.read(block_start, offset)
        legacy_bytes += len(chunk)
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            return block_start + newline + 1, legacy_bytes
        offset = block_start
    return None, legacy_bytes


def _legacy_record_budget_bytes(
    page_end: int,
    region_start: int,
    target_start: int,
    block_bytes: int,
) -> int:
    loaded_start = page_end
    while loaded_start > region_start:
        block_start = max(region_start, loaded_start - block_bytes)
        if target_start > block_start or (
            target_start == 0 and block_start == 0
        ):
            return page_end - block_start
        loaded_start = block_start
    return page_end - region_start


def _overlapping_segments(
    connection: sqlite3.Connection,
    start: int,
    end: int,
    *,
    descending: bool,
) -> Iterable[sqlite3.Row]:
    order = "DESC" if descending else "ASC"
    return connection.execute(
        f"""
        SELECT * FROM segments
        WHERE end_offset>? AND start_offset<?
        ORDER BY start_offset {order}
        """,
        (start, end),
    )


def _stream_hash_for_append_proof(
    handle: BinaryIO,
    start: int,
    end: int,
    metrics: _Metrics,
    remaining_bytes: list[int],
) -> bytes:
    length = end - start
    if start < 0 or length < 0:
        raise _PlanningRefused("APPEND_PROOF_RANGE_INVALID")
    if length > remaining_bytes[0]:
        raise _PlanningRefused("APPEND_PROOF_LIMIT")
    remaining_bytes[0] -= length
    digest = hashlib.blake2b(digest_size=16)
    handle.seek(start, os.SEEK_SET)
    pending = length
    while pending:
        chunk = handle.read(min(pending, 1024 * 1024))
        metrics.validation_bytes += len(chunk)
        if not chunk:
            raise _PlanningRefused("APPEND_PROOF_SHORT_READ")
        digest.update(chunk)
        pending -= len(chunk)
    return digest.digest()


def _prove_append_only_growth(
    connection: sqlite3.Connection,
    handle: BinaryIO,
    source: Path,
    state: Mapping[str, Any],
    snapshot_eof: int,
    initial_tail_hash: Optional[bytes],
    metrics: _Metrics,
    *,
    max_append_proof_bytes: int,
    max_segment_rows: int,
) -> tuple[os.stat_result, os.stat_result]:
    """Prove bytes at or before the pinned snapshot survived a growth event.

    Size/mtime alone cannot distinguish append from rewrite-plus-append.  The
    exceptional growth path therefore re-hashes certified segments used by the
    snapshot and compares any uncertified terminal suffix with a digest captured
    before the growth.  If that bounded proof is too expensive, planning is
    refused rather than asserting equivalence.
    """

    proof_start = os.fstat(handle.fileno())
    proof_path_start = source.lstat()
    remaining = [max_append_proof_bytes]
    certified = int(state["certified_watermark"])
    proof_end = min(snapshot_eof, certified)
    covered = 0
    for row in connection.execute(
        """
        SELECT start_offset, end_offset, segment_hash
        FROM segments
        WHERE start_offset < ?
        ORDER BY start_offset
        """,
        (proof_end,),
    ):
        metrics.segment_rows_consulted += 1
        if metrics.segment_rows_consulted > max_segment_rows:
            raise _PlanningRefused("SEGMENT_ROW_LIMIT")
        start = int(row["start_offset"])
        end = int(row["end_offset"])
        if start != covered:
            raise _PlanningRefused("APPEND_PROOF_SEGMENT_GAP")
        actual = _stream_hash_for_append_proof(
            handle,
            start,
            end,
            metrics,
            remaining,
        )
        if actual != bytes(row["segment_hash"]):
            raise _PlanningRefused("SOURCE_REWRITTEN_DURING_PLAN")
        covered = end
        if covered >= proof_end:
            break
    if covered < proof_end:
        raise _PlanningRefused("APPEND_PROOF_SEGMENT_GAP")

    tail_start = min(certified, snapshot_eof)
    if tail_start < snapshot_eof:
        if initial_tail_hash is None:
            raise _PlanningRefused("APPEND_PROOF_LIMIT")
        final_tail_hash = _stream_hash_for_append_proof(
            handle,
            tail_start,
            snapshot_eof,
            metrics,
            remaining,
        )
        if final_tail_hash != initial_tail_hash:
            raise _PlanningRefused("SOURCE_REWRITTEN_DURING_PLAN")
    proof_snapshot_end = os.fstat(handle.fileno())
    proof_path_end = source.lstat()
    if (
        int(proof_start.st_dev) != int(proof_snapshot_end.st_dev)
        or int(proof_start.st_ino) != int(proof_snapshot_end.st_ino)
        or int(proof_start.st_size) != int(proof_snapshot_end.st_size)
        or int(proof_start.st_mtime_ns) != int(proof_snapshot_end.st_mtime_ns)
        or int(proof_start.st_ctime_ns) != int(proof_snapshot_end.st_ctime_ns)
        or int(proof_path_start.st_dev) != int(proof_path_end.st_dev)
        or int(proof_path_start.st_ino) != int(proof_path_end.st_ino)
        or int(proof_path_start.st_size) != int(proof_path_end.st_size)
        or int(proof_path_start.st_mtime_ns) != int(proof_path_end.st_mtime_ns)
        or int(proof_path_start.st_ctime_ns) != int(proof_path_end.st_ctime_ns)
    ):
        raise _PlanningRefused("SOURCE_CHANGED_DURING_APPEND_PROOF")
    return proof_snapshot_end, proof_path_end


def _record_budget_start(
    connection: sqlite3.Connection,
    reader: _BoundedReader,
    metrics: _Metrics,
    start: int,
    end: int,
    certified: int,
    record_budget: int,
    max_segment_rows: int,
) -> Optional[int]:
    remaining = record_budget
    certified_end = min(end, certified)
    tail_start = max(start, certified_end)
    if tail_start < end:
        tail = reader.read(tail_start, end)
        count = _count_nonblank(tail)
        if count >= remaining:
            found = _find_nth_nonblank_from_end(tail, tail_start, remaining)
            if found is None:
                raise _PlanningRefused("TAIL_RECORD_COUNT_MISMATCH")
            return found
        remaining -= count

    if start >= certified_end:
        return None
    for row in _overlapping_segments(
        connection, start, certified_end, descending=True
    ):
        metrics.segment_rows_consulted += 1
        if metrics.segment_rows_consulted > max_segment_rows:
            raise _PlanningRefused("SEGMENT_ROW_LIMIT")
        effective_start = max(start, int(row["start_offset"]))
        effective_end = min(certified_end, int(row["end_offset"]))
        full = (
            effective_start == int(row["start_offset"])
            and effective_end == int(row["end_offset"])
        )
        if int(row["has_oversized_barrier"]):
            raise _PlanningRefused("OVERSIZED_BARRIER")
        if full:
            count = int(row["records_examined_lines"])
            if count < remaining:
                remaining -= count
                continue
        data = reader.read(effective_start, effective_end)
        count = _count_nonblank(data)
        if count >= remaining:
            found = _find_nth_nonblank_from_end(
                data, effective_start, remaining
            )
            if found is None:
                raise _PlanningRefused("SEGMENT_RECORD_COUNT_MISMATCH")
            return found
        remaining -= count
    return None


def _aggregate_page(
    connection: sqlite3.Connection,
    reader: _BoundedReader,
    metrics: _Metrics,
    start: int,
    end: int,
    certified: int,
    max_segment_rows: int,
) -> _Counts:
    result = _Counts()
    certified_end = min(end, certified)
    if start < certified_end:
        for row in _overlapping_segments(
            connection, start, certified_end, descending=False
        ):
            metrics.segment_rows_consulted += 1
            if metrics.segment_rows_consulted > max_segment_rows:
                raise _PlanningRefused("SEGMENT_ROW_LIMIT")
            effective_start = max(start, int(row["start_offset"]))
            effective_end = min(certified_end, int(row["end_offset"]))
            full = (
                effective_start == int(row["start_offset"])
                and effective_end == int(row["end_offset"])
            )
            if int(row["has_oversized_barrier"]):
                raise _PlanningRefused("OVERSIZED_BARRIER")
            if full:
                result.add_segment(row)
                continue
            for _offset, raw in _iter_documents(
                reader.read(effective_start, effective_end), effective_start
            ):
                result.add_line(raw)
    tail_start = max(start, certified_end)
    if tail_start < end:
        for _offset, raw in _iter_documents(
            reader.read(tail_start, end), tail_start
        ):
            result.add_line(raw)
    return result


def _not_reproducible(
    reason: str,
    *,
    snapshot_eof: int = 0,
    page_end: int = 0,
    source_size: int = 0,
    metrics: Optional[_Metrics] = None,
) -> PhysicalPagePlan:
    selected = metrics or _Metrics()
    return PhysicalPagePlan(
        status=NOT_REPRODUCIBLE,
        reason=reason,
        page_start=0,
        page_end=max(0, page_end),
        snapshot_eof=max(0, snapshot_eof),
        source_size_bytes=max(0, source_size),
        bytes_scanned=0,
        lines_scanned=0,
        records_examined=0,
        blank_lines=0,
        valid_lines=0,
        invalid_lines=0,
        invalid_utf8=0,
        invalid_json=0,
        mapping_records=0,
        nonmapping_json=0,
        time_range_scanned={"oldest": None, "newest": None},
        stop_reason="NOT_REPRODUCIBLE",
        coverage_complete=False,
        coverage_limited=True,
        partial=True,
        conclusive=False,
        evidence_status="NOT_REPRODUCIBLE",
        next_end=None,
        next_scan_cursor=None,
        cursor_inputs={},
        oversized=False,
        tainted=True,
        boundary_scan_bytes=selected.boundary_scan_bytes,
        validation_bytes=selected.validation_bytes,
        segment_rows_consulted=selected.segment_rows_consulted,
        planner_mode=NOT_REPRODUCIBLE,
        certified_watermark=0,
    )


def _coverage_plan(
    *,
    source: Path,
    descriptor: os.stat_result,
    snapshot_eof: int,
    page_start: int,
    page_end: int,
    bytes_scanned: int,
    counts: _Counts,
    stop_reason: str,
    next_end: Optional[int],
    oversized: bool,
    cursor_tainted: bool,
    metrics: _Metrics,
    certified_watermark: int,
    page_oversized: Optional[bool] = None,
    preserve_oversized_stop: bool = False,
) -> PhysicalPagePlan:
    partial = bool(next_end is not None and next_end > 0)
    tainted = bool(cursor_tainted or oversized)
    if tainted:
        partial = True
    if cursor_tainted and next_end is None and not preserve_oversized_stop:
        stop_reason = "PRIOR_PAGE_COVERAGE_LIMITED"
    next_cursor = None
    if next_end is not None and next_end > 0:
        next_cursor = encode_scan_cursor(
            source,
            descriptor,
            snapshot_eof,
            next_end,
            oversized_line=oversized,
            coverage_tainted=True,
        )
    mode = (
        "SEGMENT_SUMMARIES_PLUS_BOUNDARY"
        if metrics.boundary_scan_bytes
        else "SEGMENT_SUMMARIES"
    )
    next_cursor_tainted = bool(next_end is not None and next_end > 0)
    return PhysicalPagePlan(
        status=REPRODUCIBLE,
        reason=None,
        page_start=page_start,
        page_end=page_end,
        snapshot_eof=snapshot_eof,
        source_size_bytes=int(descriptor.st_size),
        bytes_scanned=bytes_scanned,
        lines_scanned=counts.lines_scanned,
        records_examined=counts.records_examined,
        blank_lines=counts.blank_lines,
        valid_lines=counts.valid_lines,
        invalid_lines=counts.invalid_lines,
        invalid_utf8=counts.invalid_utf8,
        invalid_json=counts.invalid_json,
        mapping_records=counts.mapping_records,
        nonmapping_json=counts.nonmapping_json,
        time_range_scanned={"oldest": counts.oldest, "newest": counts.newest},
        stop_reason=stop_reason,
        coverage_complete=not partial,
        coverage_limited=partial,
        partial=partial,
        conclusive=not partial,
        evidence_status="COVERAGE_LIMITED" if partial else "COMPLETE_NO_EVIDENCE",
        next_end=next_end,
        next_scan_cursor=next_cursor,
        cursor_inputs={
            "path": path_fingerprint(source),
            "dev": int(descriptor.st_dev),
            "ino": int(descriptor.st_ino),
            "snapshot_eof": snapshot_eof,
            "next_end": next_end,
            "oversized": oversized,
            "tainted": next_cursor_tainted,
        },
        oversized=oversized if page_oversized is None else page_oversized,
        tainted=tainted,
        boundary_scan_bytes=metrics.boundary_scan_bytes,
        validation_bytes=metrics.validation_bytes,
        segment_rows_consulted=metrics.segment_rows_consulted,
        planner_mode=mode,
        certified_watermark=certified_watermark,
    )


def plan_physical_page(
    source_path: Path | str,
    index_path: Path | str,
    source_id: str,
    *,
    scan_cursor: Optional[str] = None,
    snapshot_eof: Optional[int] = None,
    page_end: Optional[int] = None,
    byte_budget: int = BYTE_BUDGET,
    record_budget: int = RECORD_BUDGET,
    block_bytes: int = BLOCK_BYTES,
    max_boundary_scan_bytes: int = DEFAULT_MAX_BOUNDARY_SCAN_BYTES,
    max_segment_rows: int = DEFAULT_MAX_SEGMENT_ROWS,
    max_append_proof_bytes: int = DEFAULT_MAX_APPEND_PROOF_BYTES,
    fault_injector: FaultInjector = None,
) -> PhysicalPagePlan:
    """Plan one exact legacy physical page from a certified schema-V2 index.

    Explicit budget overrides exist for deterministic unit tests and offline
    analysis.  A future serving gate must require the contract defaults.
    """

    source = Path(source_path)
    index = Path(index_path)
    metrics = _Metrics()
    selected_snapshot = 0
    selected_page_end = 0
    source_size = 0
    if (
        byte_budget <= 0
        or record_budget <= 0
        or block_bytes <= 0
        or max_boundary_scan_bytes <= 0
        or max_segment_rows <= 0
        or max_append_proof_bytes <= 0
    ):
        return _not_reproducible("PLANNER_CONFIG_INVALID")
    if scan_cursor is not None and (
        snapshot_eof is not None or page_end is not None
    ):
        return _not_reproducible("CURSOR_AND_EXPLICIT_WINDOW")
    try:
        path_state = source.lstat()
        if stat.S_ISLNK(path_state.st_mode) or not stat.S_ISREG(path_state.st_mode):
            raise _PlanningRefused("SOURCE_NOT_REGULAR_FILE")
        connection = _sqlite_ro(index)
    except FileNotFoundError:
        return _not_reproducible("SOURCE_OR_INDEX_MISSING")
    except (OSError, sqlite3.DatabaseError) as exc:
        return _not_reproducible(f"OPEN_FAILED:{type(exc).__name__}")

    try:
        with source.open("rb") as handle:
            descriptor = os.fstat(handle.fileno())
            source_size = int(descriptor.st_size)
            if (
                int(path_state.st_dev) != int(descriptor.st_dev)
                or int(path_state.st_ino) != int(descriptor.st_ino)
                or not stat.S_ISREG(descriptor.st_mode)
            ):
                raise _PlanningRefused("LSTAT_FSTAT_MISMATCH")
            state = _validate_v2_state(
                connection,
                handle,
                source,
                source_id,
                descriptor,
                metrics,
                max_segment_rows,
            )
            certified = int(state["certified_watermark"])
            decoded = decode_scan_cursor(scan_cursor) if scan_cursor else None
            if decoded is not None:
                if decoded["path"] != path_fingerprint(source):
                    raise _PlanningRefused("CURSOR_SOURCE_MISMATCH")
                if (
                    int(decoded["dev"]) != int(descriptor.st_dev)
                    or int(decoded["ino"]) != int(descriptor.st_ino)
                    or source_size < int(decoded["snapshot_eof"])
                ):
                    raise _PlanningRefused("CURSOR_GENERATION_MISMATCH")
                selected_snapshot = int(decoded["snapshot_eof"])
                selected_page_end = int(decoded["next_end"])
                cursor_tainted = bool(decoded.get("tainted"))
                cursor_oversized = bool(decoded.get("oversized"))
                if selected_page_end > 0 and not cursor_oversized:
                    handle.seek(selected_page_end - 1, os.SEEK_SET)
                    metrics.validation_bytes += 1
                    if handle.read(1) != b"\n":
                        raise _PlanningRefused("CURSOR_NOT_LINE_ALIGNED")
            else:
                selected_snapshot = (
                    source_size if snapshot_eof is None else int(snapshot_eof)
                )
                selected_page_end = (
                    selected_snapshot if page_end is None else int(page_end)
                )
                cursor_tainted = False
                cursor_oversized = False
            if not (
                0
                <= selected_page_end
                <= selected_snapshot
                <= source_size
            ):
                raise _PlanningRefused("WINDOW_OUTSIDE_SOURCE")
            initial_tail_hash: Optional[bytes] = None
            tail_start = min(certified, selected_snapshot)
            tail_length = selected_snapshot - tail_start
            if 0 < tail_length <= max_append_proof_bytes:
                initial_tail_hash = _stream_hash_for_append_proof(
                    handle,
                    tail_start,
                    selected_snapshot,
                    metrics,
                    [max_append_proof_bytes],
                )
            if fault_injector is not None:
                fault_injector(
                    "after_snapshot",
                    {
                        "snapshot_eof": selected_snapshot,
                        "page_end": selected_page_end,
                    },
                )

            def assert_final_source_unchanged() -> None:
                if fault_injector is not None:
                    fault_injector(
                        "before_final_source_check",
                        {
                            "snapshot_eof": selected_snapshot,
                            "page_end": selected_page_end,
                        },
                    )
                final_descriptor = os.fstat(handle.fileno())
                try:
                    final_path = source.lstat()
                except FileNotFoundError as exc:
                    raise _PlanningRefused(
                        "SOURCE_REMOVED_DURING_PLAN"
                    ) from exc
                if (
                    int(final_descriptor.st_dev) != int(descriptor.st_dev)
                    or int(final_descriptor.st_ino) != int(descriptor.st_ino)
                    or int(final_path.st_dev) != int(descriptor.st_dev)
                    or int(final_path.st_ino) != int(descriptor.st_ino)
                    or int(final_descriptor.st_size) < selected_snapshot
                ):
                    raise _PlanningRefused("SOURCE_CHANGED_DURING_PLAN")
                if int(final_descriptor.st_size) == int(descriptor.st_size):
                    if (
                        int(final_descriptor.st_mtime_ns)
                        != int(descriptor.st_mtime_ns)
                        or int(final_descriptor.st_ctime_ns)
                        != int(descriptor.st_ctime_ns)
                    ):
                        raise _PlanningRefused("SOURCE_REWRITTEN_DURING_PLAN")
                elif int(final_descriptor.st_size) > int(descriptor.st_size):
                    append_proof_stat, append_proof_path_stat = _prove_append_only_growth(
                        connection,
                        handle,
                        source,
                        state,
                        selected_snapshot,
                        initial_tail_hash,
                        metrics,
                        max_append_proof_bytes=max_append_proof_bytes,
                        max_segment_rows=max_segment_rows,
                    )
                    proof_descriptor = os.fstat(handle.fileno())
                    proof_path = source.lstat()
                    if (
                        int(proof_descriptor.st_dev) != int(descriptor.st_dev)
                        or int(proof_descriptor.st_ino) != int(descriptor.st_ino)
                        or int(proof_path.st_dev) != int(descriptor.st_dev)
                        or int(proof_path.st_ino) != int(descriptor.st_ino)
                        or int(proof_descriptor.st_size) < selected_snapshot
                        or int(proof_descriptor.st_size)
                        != int(append_proof_stat.st_size)
                        or int(proof_descriptor.st_mtime_ns)
                        != int(append_proof_stat.st_mtime_ns)
                        or int(proof_descriptor.st_ctime_ns)
                        != int(append_proof_stat.st_ctime_ns)
                        or int(proof_path.st_size)
                        != int(append_proof_path_stat.st_size)
                        or int(proof_path.st_mtime_ns)
                        != int(append_proof_path_stat.st_mtime_ns)
                        or int(proof_path.st_ctime_ns)
                        != int(append_proof_path_stat.st_ctime_ns)
                    ):
                        raise _PlanningRefused("SOURCE_CHANGED_DURING_APPEND_PROOF")

            reader = _BoundedReader(handle, max_boundary_scan_bytes, metrics)
            region_start = max(0, selected_page_end - byte_budget)
            if cursor_oversized:
                next_boundary, legacy_bytes = _previous_lf_from_page_end(
                    reader, region_start, selected_page_end, block_bytes
                )
                next_end = (
                    next_boundary
                    if next_boundary is not None
                    else (region_start if region_start > 0 else None)
                )
                plan = _coverage_plan(
                    source=source,
                    descriptor=descriptor,
                    snapshot_eof=selected_snapshot,
                    page_start=selected_page_end,
                    page_end=selected_page_end,
                    bytes_scanned=legacy_bytes,
                    counts=_Counts(),
                    stop_reason="LINE_EXCEEDS_BYTE_BUDGET",
                    next_end=next_end,
                    oversized=bool(next_boundary is None and region_start > 0),
                    cursor_tainted=True,
                    metrics=metrics,
                    certified_watermark=certified,
                    page_oversized=True,
                    preserve_oversized_stop=True,
                )
            else:
                aligned_start = region_start
                if region_start > 0:
                    newline = _first_lf_after_region(
                        reader, region_start, selected_page_end, block_bytes
                    )
                    if newline is None or newline + 1 >= selected_page_end:
                        plan = _coverage_plan(
                            source=source,
                            descriptor=descriptor,
                            snapshot_eof=selected_snapshot,
                            page_start=selected_page_end,
                            page_end=selected_page_end,
                            bytes_scanned=selected_page_end - region_start,
                            counts=_Counts(),
                            stop_reason="LINE_EXCEEDS_BYTE_BUDGET",
                            next_end=region_start,
                            oversized=True,
                            cursor_tainted=cursor_tainted,
                            metrics=metrics,
                            certified_watermark=certified,
                        )
                        assert_final_source_unchanged()
                        return plan
                    aligned_start = newline + 1
                record_start = _record_budget_start(
                    connection,
                    reader,
                    metrics,
                    aligned_start,
                    selected_page_end,
                    certified,
                    record_budget,
                    max_segment_rows,
                )
                record_hit = bool(record_start is not None and record_start > 0)
                if record_hit:
                    page_start_value = int(record_start)
                    next_end = page_start_value
                    stop_reason = "RECORD_BUDGET"
                    legacy_bytes = _legacy_record_budget_bytes(
                        selected_page_end,
                        region_start,
                        page_start_value,
                        block_bytes,
                    )
                elif region_start > 0:
                    page_start_value = aligned_start
                    next_end = aligned_start
                    stop_reason = "BYTE_BUDGET"
                    legacy_bytes = selected_page_end - region_start
                else:
                    page_start_value = 0
                    next_end = None
                    stop_reason = "START_OF_SNAPSHOT"
                    legacy_bytes = selected_page_end
                counts = _aggregate_page(
                    connection,
                    reader,
                    metrics,
                    page_start_value,
                    selected_page_end,
                    certified,
                    max_segment_rows,
                )
                lost_blank_lines = _legacy_lost_boundary_blank_lines(
                    reader,
                    page_start_value,
                    selected_page_end,
                    legacy_bytes,
                    block_bytes,
                )
                if lost_blank_lines:
                    counts.lines_scanned -= lost_blank_lines
                    counts.blank_lines -= lost_blank_lines
                    if counts.lines_scanned < 0 or counts.blank_lines < 0:
                        raise _PlanningRefused("LEGACY_BOUNDARY_COUNT_INVALID")
                replay_start = _legacy_replay_start(
                    page_start_value,
                    selected_page_end,
                    legacy_bytes,
                    block_bytes,
                )
                if replay_start != page_start_value:
                    replay_counts = _aggregate_page(
                        connection,
                        reader,
                        metrics,
                        replay_start,
                        selected_page_end,
                        certified,
                        max_segment_rows,
                    )
                    counts.apply_replay_classification(replay_counts)
                plan = _coverage_plan(
                    source=source,
                    descriptor=descriptor,
                    snapshot_eof=selected_snapshot,
                    page_start=page_start_value,
                    page_end=selected_page_end,
                    bytes_scanned=legacy_bytes,
                    counts=counts,
                    stop_reason=stop_reason,
                    next_end=next_end,
                    oversized=False,
                    cursor_tainted=cursor_tainted,
                    metrics=metrics,
                    certified_watermark=certified,
                )

            assert_final_source_unchanged()
            return plan
    except _PlanningRefused as exc:
        return _not_reproducible(
            exc.reason,
            snapshot_eof=selected_snapshot,
            page_end=selected_page_end,
            source_size=source_size,
            metrics=metrics,
        )
    except (OSError, sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
        return _not_reproducible(
            f"PLANNER_FAILED:{type(exc).__name__}",
            snapshot_eof=selected_snapshot,
            page_end=selected_page_end,
            source_size=source_size,
            metrics=metrics,
        )
    finally:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.DatabaseError:
            pass
        connection.close()


__all__ = [
    "DEFAULT_MAX_APPEND_PROOF_BYTES",
    "DEFAULT_MAX_BOUNDARY_SCAN_BYTES",
    "DEFAULT_MAX_SEGMENT_ROWS",
    "NOT_REPRODUCIBLE",
    "PLANNER_VERSION",
    "PhysicalPagePlan",
    "REPRODUCIBLE",
    "plan_physical_page",
]
