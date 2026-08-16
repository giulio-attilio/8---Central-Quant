"""Offline C1 indexed source-envelope builder for trade evidence journals.

This module is intentionally dormant.  It is not imported by the HTTP routes,
the legacy readers, Phase B, or automated maintenance.  It can only build a
private shadow envelope for ``history_manager`` or ``timeline`` from an
explicit schema-V2 index, a reproducible C0 physical plan, and factual journal
bytes.

The SQLite sidecar is never evidence.  Every selected record is relocated and
verified against the pinned journal descriptor before the existing Validator
correlator is allowed to see it.  Any eligibility, cap, integrity, or mutation
uncertainty returns ``FALLBACK_REQUIRED`` and discards partial rows/context.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import os
import sqlite3
import stat
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Callable, Iterable, Iterator, Mapping, Optional, Sequence

from trade_evidence_identity_contract import (
    IDENTITY_CONTRACT_HASH,
    IDENTITY_GROUPS,
    classify_identity,
    extract_typed_identities,
)
from trade_evidence_identity_offset_index_v1 import (
    BUILDER_VERSION_V2,
    CERTIFICATION_DEEP_BASELINE,
    CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND,
    CERTIFICATION_STATE_FULL,
    CERTIFICATION_STATE_NONE,
    HASH_BYTES,
    INDEX_VERSION_V2,
    SCHEMA_VERSION_V2,
    SERVING_COMPLETENESS_CONTRACT_VERSION,
    SQLITE_APPLICATION_ID,
    IndexedRecordMetadata,
    IndexValidationError,
    normalized_path_hash,
    read_and_verify_record,
    verify_certified_summary_hash,
    verify_serving_completeness_seal,
)
from trade_evidence_physical_page_planner_v1 import (
    DEFAULT_MAX_SEGMENT_ROWS,
    NOT_REPRODUCIBLE,
    REPRODUCIBLE,
    PhysicalPagePlan,
    plan_physical_page,
    plan_physical_page_pinned,
)
from trade_evidence_physical_window_contract_v1 import (
    CURSOR_CONTRACT_VERSION,
    PHYSICAL_CONTRACT_HASH,
    PHYSICAL_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
    classify_physical_line,
    path_fingerprint,
)


VERSION = "2026-08-15-TRADE-EVIDENCE-IDENTITY-OFFSET-INDEX-V1-PHASE-C1-SOURCE-ENVELOPE"
SUPPORTED_SOURCES = frozenset({"history_manager", "timeline"})

BUILT = "BUILT"
FALLBACK_REQUIRED = "FALLBACK_REQUIRED"
INDEX_ONLY = "INDEX_ONLY"
INDEX_PLUS_TAIL = "INDEX_PLUS_TAIL"
NO_INDEX_MODE = "NONE"
NEGATIVE_UNSAFE = "NEGATIVE_UNSAFE"
NEGATIVE_CERTIFIED = "NEGATIVE_CERTIFIED"
NOT_NEGATIVE = "NOT_NEGATIVE"
COMPLETENESS_UNCERTIFIED = "UNCERTIFIED_COMPLETENESS"
COMPLETENESS_UNKNOWN = "UNKNOWN"
COMPLETENESS_FULL_CERTIFIED = "FULL_CERTIFIED"

MAX_CANDIDATE_OFFSETS = 25_000
MAX_FACTUAL_RECORDS = 10_000
MAX_IDENTITY_QUERIES = 2_048
MAX_PROMOTED_IDENTITIES = 512
MAX_SQLITE_FETCH_BATCH = 256
MAX_HEAP_CURSORS = 2_048
MAX_TAIL_BYTES = 4 * 1024 * 1024
MAX_TAIL_LINES = 10_000
MAX_BOUNDARY_BYTES = 2 * 1024 * 1024
MAX_SOURCE_JOURNAL_BYTES = 8 * 1024 * 1024
DEFAULT_BUSY_TIMEOUT_MS = 50

_CERTIFIED_KINDS = frozenset(
    {CERTIFICATION_DEEP_BASELINE, CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND}
)
_SERVING_CERTIFICATION_FIELDS = (
    "serving_contract_version",
    "serving_certified_watermark",
    "serving_completeness_hash",
    "serving_certification_kind",
    "serving_certified_at",
    "serving_record_count",
    "serving_identity_count",
    "serving_posting_count",
)
_GROUP_TYPES = {
    group: tuple(
        sorted(
            identity_type
            for identity_type, candidate_group in IDENTITY_GROUPS.items()
            if candidate_group == group
        )
    )
    for group in frozenset(IDENTITY_GROUPS.values())
}
_SAFE_PINNED_PLANNER_OPTIONS = frozenset(
    {
        "byte_budget",
        "record_budget",
        "block_bytes",
        "max_boundary_scan_bytes",
        "max_segment_rows",
        "max_append_proof_bytes",
    }
)

FaultInjector = Optional[Callable[[str, Mapping[str, Any]], None]]


class _Fallback(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = str(reason)


def _frozen(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    if isinstance(value, set):
        return frozenset(_frozen(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, frozenset):
        return {_thaw(item) for item in value}
    return copy.deepcopy(value)


def _safe_deepcopy(value: Any, fallback: Any = None) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return fallback


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return int(left.st_dev) == int(right.st_dev) and int(left.st_ino) == int(right.st_ino)


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return bool(
        _same_file(left, right)
        and int(left.st_size) == int(right.st_size)
        and int(left.st_mtime_ns) == int(right.st_mtime_ns)
        and int(left.st_ctime_ns) == int(right.st_ctime_ns)
    )


def _blake128(value: bytes) -> bytes:
    return hashlib.blake2b(value, digest_size=16).digest()


def _certification_witness(state: Any) -> tuple[Any, ...]:
    """Normalize every physical/serving field that authorizes C2 serving."""

    return (
        str(state["state"]),
        str(state["generation_uuid"]),
        str(state["certification_kind"]),
        int(state["certified_watermark"]),
        str(state["serving_contract_version"]),
        int(state["serving_certified_watermark"]),
        bytes(state["serving_completeness_hash"]),
        str(state["serving_certification_kind"]),
        str(state["serving_certified_at"]),
        int(state["serving_record_count"]),
        int(state["serving_identity_count"]),
        int(state["serving_posting_count"]),
    )


@dataclass(frozen=True)
class EnvelopeCaps:
    max_candidate_offsets: int = MAX_CANDIDATE_OFFSETS
    max_factual_records: int = MAX_FACTUAL_RECORDS
    max_identity_queries: int = MAX_IDENTITY_QUERIES
    max_promoted_identities: int = MAX_PROMOTED_IDENTITIES
    max_sqlite_fetch_batch: int = MAX_SQLITE_FETCH_BATCH
    max_heap_cursors: int = MAX_HEAP_CURSORS
    max_tail_bytes: int = MAX_TAIL_BYTES
    max_tail_lines: int = MAX_TAIL_LINES
    max_boundary_bytes: int = MAX_BOUNDARY_BYTES
    max_source_journal_bytes: int = MAX_SOURCE_JOURNAL_BYTES
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS

    def validate(self) -> None:
        values = asdict(self)
        if any(int(value) <= 0 for value in values.values()):
            raise ValueError("all C1 caps must be positive")
        if self.max_sqlite_fetch_batch > MAX_SQLITE_FETCH_BATCH:
            raise ValueError("SQLite fetch batch exceeds the C1 hard cap")
        if self.max_source_journal_bytes > MAX_SOURCE_JOURNAL_BYTES:
            raise ValueError("journal byte budget exceeds the C1 hard cap")
        if self.max_boundary_bytes > MAX_BOUNDARY_BYTES:
            raise ValueError("boundary byte budget exceeds the C1 hard cap")
        if self.max_tail_bytes > MAX_TAIL_BYTES:
            raise ValueError("tail byte budget exceeds the C1 hard cap")
        hard_caps = (
            ("candidate offset", self.max_candidate_offsets, MAX_CANDIDATE_OFFSETS),
            ("factual record", self.max_factual_records, MAX_FACTUAL_RECORDS),
            ("identity query", self.max_identity_queries, MAX_IDENTITY_QUERIES),
            (
                "promoted identity",
                self.max_promoted_identities,
                MAX_PROMOTED_IDENTITIES,
            ),
            ("heap cursor", self.max_heap_cursors, MAX_HEAP_CURSORS),
            ("tail line", self.max_tail_lines, MAX_TAIL_LINES),
        )
        for label, value, maximum in hard_caps:
            if value > maximum:
                raise ValueError(f"{label} budget exceeds the C1 hard cap")
        if self.busy_timeout_ms > DEFAULT_BUSY_TIMEOUT_MS:
            raise ValueError("SQLite busy timeout exceeds the C1 hard cap")


@dataclass(frozen=True)
class SourceSnapshotMetadata:
    source_path: str
    path_fingerprint: str
    dev: int
    inode: int
    source_size: int
    snapshot_eof: int
    page_end: int
    mtime_ns: int
    ctime_ns: int
    source_generation_witness: str
    index_path: str
    index_generation_uuid: str
    index_schema_version: int
    index_version: str
    certified_watermark: int
    certification_kind: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceEnvelopeMetrics:
    index_lookup_ms: float = 0.0
    certification_ms: float = 0.0
    certification_sqlite_rows: int = 0
    planner_ms: float = 0.0
    planner_segment_rows: int = 0
    factual_journal_bytes: int = 0
    tail_bytes: int = 0
    boundary_bytes: int = 0
    source_journal_bytes: int = 0
    offset_count: int = 0
    candidate_count: int = 0
    record_count: int = 0
    identity_query_count: int = 0
    promotion_count: int = 0
    sqlite_rows_seen: int = 0
    duration_ms: float = 0.0
    mode: str = NO_INDEX_MODE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class _Metrics:
    index_lookup_ms: float = 0.0
    certification_ms: float = 0.0
    certification_sqlite_rows: int = 0
    planner_ms: float = 0.0
    planner_segment_rows: int = 0
    factual_journal_bytes: int = 0
    tail_bytes: int = 0
    boundary_bytes: int = 0
    source_journal_bytes: int = 0
    offset_count: int = 0
    candidate_count: int = 0
    record_count: int = 0
    identity_query_count: int = 0
    promotion_count: int = 0
    sqlite_rows_seen: int = 0
    duration_ms: float = 0.0
    mode: str = NO_INDEX_MODE

    def freeze(self) -> SourceEnvelopeMetrics:
        return SourceEnvelopeMetrics(**asdict(self))


@dataclass(frozen=True)
class IndexedSourceEnvelope:
    """Defensively-copyable, private result; never an HTTP payload."""

    source: str
    status: str
    fallback_reason: Optional[str]
    index_mode: str
    negative_status: str
    completeness_status: str
    correlated_rows: tuple[Mapping[str, Any], ...]
    physical_metadata: Mapping[str, Any]
    source_coverage: Mapping[str, Any]
    raw_source_metadata: Mapping[str, Any]
    identifiers_discovered: Mapping[str, Any]
    promotion_metadata: tuple[Mapping[str, Any], ...]
    context_before: Mapping[str, Any]
    context_after: Mapping[str, Any]
    factual_offsets: tuple[int, ...]
    events: tuple[Mapping[str, Any], ...]
    metrics: SourceEnvelopeMetrics
    _context_after_clone: Any = field(repr=False, compare=False, default=None)

    @property
    def ok(self) -> bool:
        return self.status == BUILT

    def clone_context_after(self) -> Any:
        return copy.deepcopy(self._context_after_clone)

    def to_legacy_private_envelope(self) -> dict[str, Any]:
        """Create a detached legacy-shaped value for parity tests only."""

        if not self.ok:
            raise RuntimeError("fallback results cannot be projected as source envelopes")
        return {
            "records": [_thaw(row) for row in self.correlated_rows],
            "_reader_metadata": _thaw(self.physical_metadata),
            "_identity_metadata": _thaw(
                self.raw_source_metadata.get("identity_metadata", {})
            ),
            "_evidence_correlated": True,
            "_correlation_context": self.clone_context_after(),
        }


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
        "registry_candidate_count": int(getattr(context, "registry_candidate_count", 0)),
        "registry_candidates": copy.deepcopy(getattr(context, "registry_candidates", [])),
        "registry_candidates_truncated": bool(
            getattr(context, "registry_candidates_truncated", False)
        ),
        "registry_selection_basis": getattr(context, "registry_selection_basis", None),
    }


def _known_group_values(context: Any) -> set[tuple[str, str]]:
    return {
        (str(group), str(value))
        for group, values in getattr(context, "trusted", {}).items()
        for value in values
        if str(value)
    }


def _known_typed_values(context: Any) -> set[tuple[str, str]]:
    return {
        (str(identity_type), str(value))
        for identity_type, values in getattr(context, "trusted_typed", {}).items()
        for value in values
        if str(value)
    }


def _source_generation_witness(
    source: Path, descriptor: os.stat_result, generation_uuid: str, certified: int
) -> str:
    payload = "\x00".join(
        (
            path_fingerprint(source),
            str(int(descriptor.st_dev)),
            str(int(descriptor.st_ino)),
            str(int(descriptor.st_size)),
            str(int(descriptor.st_mtime_ns)),
            str(int(descriptor.st_ctime_ns)),
            generation_uuid,
            str(int(certified)),
        )
    ).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(payload).hexdigest()


class PinnedSourceIndexSession:
    """One source descriptor plus one SQLite read transaction.

    The object is deliberately explicit and request-local so a future planner
    and legacy fallback can share it.  C1's ``plan_and_build`` helper opens it
    before planning and keeps it alive through factual reads and the final
    mutation check.
    """

    def __init__(
        self,
        source_path: Path | str,
        index_path: Path | str,
        source_id: str,
        *,
        caps: EnvelopeCaps = EnvelopeCaps(),
        metrics: Optional[_Metrics] = None,
    ) -> None:
        self.source_path = Path(source_path)
        self.index_path = Path(index_path)
        self.source_id = str(source_id)
        self.caps = caps
        self.metrics = metrics or _Metrics()
        self.connection: Optional[sqlite3.Connection] = None
        self.source_handle: Optional[BinaryIO] = None
        self.state: dict[str, Any] = {}
        self.snapshot: Optional[SourceSnapshotMetadata] = None
        self._source_descriptor_open: Optional[os.stat_result] = None
        self._source_path_open: Optional[os.stat_result] = None
        self._index_path_open: Optional[os.stat_result] = None
        self._journal_bytes = 0
        self._planner_journal_bytes = 0
        self._planner_bytes_accounted = False
        self._active_cursors = 0
        self._certification_state = CERTIFICATION_STATE_NONE
        self._certification_witness_open: Optional[tuple[Any, ...]] = None

    def __enter__(self) -> "PinnedSourceIndexSession":
        self.caps.validate()
        if self.source_id not in SUPPORTED_SOURCES:
            raise _Fallback("UNSUPPORTED_SOURCE")
        try:
            index_stat = self.index_path.lstat()
        except FileNotFoundError as exc:
            raise _Fallback("INDEX_MISSING") from exc
        if stat.S_ISLNK(index_stat.st_mode) or not stat.S_ISREG(index_stat.st_mode):
            raise _Fallback("INDEX_NOT_REGULAR_FILE")
        if Path(os.fspath(self.index_path) + "-wal").exists() or Path(
            os.fspath(self.index_path) + "-shm"
        ).exists():
            raise _Fallback("INDEX_SIDECAR_PRESENT")
        self._index_path_open = index_stat
        try:
            self.connection = sqlite3.connect(
                self.index_path.resolve().as_uri() + "?mode=ro",
                uri=True,
                isolation_level=None,
                timeout=max(0.001, self.caps.busy_timeout_ms / 1000.0),
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute(f"PRAGMA busy_timeout={int(self.caps.busy_timeout_ms)}")
            self.connection.execute("PRAGMA query_only=ON")
            self.connection.execute("PRAGMA foreign_keys=ON")
            self.connection.execute("BEGIN")
            self._validate_index_snapshot()
            self._open_source()
            self._validate_source_certificate()
        except _Fallback:
            self.close()
            raise
        except sqlite3.OperationalError as exc:
            self.close()
            text = str(exc).lower()
            raise _Fallback(
                "SQLITE_BUSY" if "busy" in text or "locked" in text else "SQLITE_OPEN_FAILED"
            ) from exc
        except (
            sqlite3.DatabaseError,
            IndexValidationError,
            OSError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            self.close()
            raise _Fallback("ELIGIBILITY_VALIDATION_FAILED") from exc
        except Exception as exc:
            # A failed __enter__ never receives __exit__; keep unexpected
            # validation failures fail-closed without leaking either resource.
            self.close()
            raise _Fallback("ELIGIBILITY_VALIDATION_FAILED") from exc
        return self

    def _validate_query_indexes(self) -> None:
        """Require the bounded lookup indexes relied upon by C1 queries."""

        assert self.connection is not None
        postings_indexes = {
            str(row[1]): row
            for row in self.connection.execute("PRAGMA index_list(postings)")
        }
        postings_record_index = postings_indexes.get("postings_record_idx")
        postings_record_columns = tuple(
            str(row[2])
            for row in self.connection.execute("PRAGMA index_info(postings_record_idx)")
        )
        if (
            postings_record_index is None
            or bool(postings_record_index[2])
            or str(postings_record_index[3]) != "c"
            or bool(postings_record_index[4])
            or postings_record_columns
            != ("record_id", "start_offset", "identity_id")
        ):
            raise _Fallback("REQUIRED_QUERY_INDEX_MISSING")

        identity_unique = False
        for row in self.connection.execute("PRAGMA index_list(identities)"):
            if not bool(row[2]) or bool(row[4]):
                continue
            index_name = str(row[1]).replace("'", "''")
            columns = tuple(
                str(info[2])
                for info in self.connection.execute(
                    f"PRAGMA index_info('{index_name}')"
                )
            )
            if columns == ("identity_type", "identity_value"):
                identity_unique = True
                break
        postings_primary_key = tuple(
            str(row[1])
            for row in sorted(
                self.connection.execute("PRAGMA table_info(postings)"),
                key=lambda item: int(item[5]) if int(item[5]) else 10_000,
            )
            if int(row[5])
        )
        if not identity_unique or postings_primary_key != (
            "identity_id",
            "start_offset",
            "record_id",
        ):
            raise _Fallback("REQUIRED_QUERY_INDEX_MISSING")

    def _validate_index_snapshot(self) -> None:
        assert self.connection is not None
        application_id = int(self.connection.execute("PRAGMA application_id").fetchone()[0])
        user_version = int(self.connection.execute("PRAGMA user_version").fetchone()[0])
        if application_id != SQLITE_APPLICATION_ID:
            raise _Fallback("SQLITE_APPLICATION_ID_MISMATCH")
        if user_version != SCHEMA_VERSION_V2:
            raise _Fallback("UNSUPPORTED_SCHEMA")
        required_tables = {"source_state", "segments", "records", "identities", "postings"}
        tables = {
            str(row[0])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not required_tables.issubset(tables):
            raise _Fallback("INDEX_TABLE_MISSING")
        # The V2 builder never ANALYZEs its sidecar.  Reject injected planner
        # statistics rather than allowing sqlite_stat tamper to turn bounded
        # point/range lookups into full-table scans.
        if any(name.startswith("sqlite_stat") for name in tables):
            raise _Fallback("UNTRUSTED_QUERY_PLANNER_STATS")
        self._validate_query_indexes()
        rows = self.connection.execute("SELECT * FROM source_state LIMIT 2").fetchall()
        if len(rows) != 1:
            raise _Fallback("SOURCE_STATE_INVALID")
        state = dict(rows[0])
        self.state = state
        if int(state["schema_version"]) != SCHEMA_VERSION_V2:
            raise _Fallback("UNSUPPORTED_SCHEMA")
        if str(state["index_version"]) != INDEX_VERSION_V2:
            raise _Fallback("INDEX_VERSION_MISMATCH")
        if str(state["builder_version"]) != BUILDER_VERSION_V2:
            raise _Fallback("BUILDER_VERSION_MISMATCH")
        if str(state["identity_contract_hash"]) != IDENTITY_CONTRACT_HASH:
            raise _Fallback("IDENTITY_CONTRACT_MISMATCH")
        if str(state["physical_contract_hash"]) != PHYSICAL_CONTRACT_HASH:
            raise _Fallback("PHYSICAL_CONTRACT_MISMATCH")
        if str(state["physical_contract_version"]) != PHYSICAL_CONTRACT_VERSION:
            raise _Fallback("PHYSICAL_CONTRACT_VERSION_MISMATCH")
        if int(state["cursor_contract_version"]) != CURSOR_CONTRACT_VERSION:
            raise _Fallback("CURSOR_CONTRACT_MISMATCH")
        if int(state["summary_contract_version"]) != SUMMARY_CONTRACT_VERSION:
            raise _Fallback("SUMMARY_CONTRACT_MISMATCH")
        if str(state["source_id"]) != self.source_id:
            raise _Fallback("SOURCE_ID_MISMATCH")
        if str(state["state"]) != "READY":
            raise _Fallback("INDEX_NOT_READY")
        if str(state["certification_kind"]) not in _CERTIFIED_KINDS:
            raise _Fallback("INDEX_V2_UNCERTIFIED")
        if not state.get("certified_at"):
            raise _Fallback("CERTIFICATION_TIMESTAMP_MISSING")
        try:
            generation = str(uuid.UUID(str(state["generation_uuid"])))
        except (ValueError, AttributeError) as exc:
            raise _Fallback("GENERATION_UUID_INVALID") from exc
        if generation != str(state["generation_uuid"]):
            raise _Fallback("GENERATION_UUID_INVALID")
        certified = int(state["certified_watermark"])
        safe = int(state["safe_watermark"])
        if not 0 <= certified <= safe:
            raise _Fallback("CERTIFIED_WATERMARK_INVALID")
        if not verify_certified_summary_hash(self.connection):
            raise _Fallback("CERTIFIED_SUMMARY_HASH_MISMATCH")
        missing_serving = tuple(
            field for field in _SERVING_CERTIFICATION_FIELDS if field not in state
        )
        if missing_serving:
            raise _Fallback("SERVING_CERTIFICATION_COLUMNS_MISSING")
        if (
            str(state["serving_contract_version"])
            != SERVING_COMPLETENESS_CONTRACT_VERSION
        ):
            raise _Fallback("SERVING_CONTRACT_MISMATCH")
        try:
            serving_watermark = int(state["serving_certified_watermark"])
            serving_hash = bytes(state["serving_completeness_hash"])
            serving_record_count = int(state["serving_record_count"])
            serving_identity_count = int(state["serving_identity_count"])
            serving_posting_count = int(state["serving_posting_count"])
        except (TypeError, ValueError) as exc:
            raise _Fallback("SERVING_CERTIFICATION_STATE_INVALID") from exc
        if serving_watermark != certified:
            raise _Fallback("SERVING_WATERMARK_MISMATCH")
        if len(serving_hash) != HASH_BYTES:
            raise _Fallback("SERVING_COMPLETENESS_HASH_SHAPE")
        if (
            str(state["serving_certification_kind"]) not in _CERTIFIED_KINDS
            or str(state["serving_certification_kind"])
            != str(state["certification_kind"])
        ):
            raise _Fallback("SERVING_CERTIFICATION_KIND_MISMATCH")
        if not state.get("serving_certified_at"):
            raise _Fallback("SERVING_CERTIFICATION_TIMESTAMP_MISSING")
        if min(
            serving_record_count,
            serving_identity_count,
            serving_posting_count,
        ) < 0:
            raise _Fallback("SERVING_CERTIFICATION_COUNT_INVALID")
        # The serving seal deliberately streams every records/identities/
        # postings row.  Count the exact SQLite rows delivered and isolate its
        # wall time so an offline/full-shadow caller cannot mistake this O(N)
        # certification cost for bounded candidate lookup work.  Restoring the
        # row factory in ``finally`` preserves the session's sqlite.Row API.
        original_row_factory = self.connection.row_factory

        def counted_row_factory(
            cursor: sqlite3.Cursor, row: tuple[Any, ...]
        ) -> Any:
            self.metrics.certification_sqlite_rows += 1
            if original_row_factory is None:
                return row
            return original_row_factory(cursor, row)

        certification_started = time.perf_counter()
        self.connection.row_factory = counted_row_factory
        try:
            serving_verified = verify_serving_completeness_seal(self.connection)
        finally:
            self.connection.row_factory = original_row_factory
            self.metrics.certification_ms += (
                time.perf_counter() - certification_started
            ) * 1000.0
        if not serving_verified:
            raise _Fallback("SERVING_COMPLETENESS_SEAL_MISMATCH")
        self._certification_witness_open = _certification_witness(state)
        self._certification_state = CERTIFICATION_STATE_FULL

    @property
    def certification_state(self) -> str:
        """Certification pinned by this transaction, never inferred by callers."""

        return self._certification_state

    def _open_source(self) -> None:
        try:
            path_state = self.source_path.lstat()
        except FileNotFoundError as exc:
            raise _Fallback("SOURCE_MISSING") from exc
        if stat.S_ISLNK(path_state.st_mode) or not stat.S_ISREG(path_state.st_mode):
            raise _Fallback("SOURCE_NOT_REGULAR_FILE")
        handle = self.source_path.open("rb", buffering=0)
        # Publish the handle immediately so __enter__'s failure cleanup owns it
        # even when fstat itself raises.
        self.source_handle = handle
        descriptor = os.fstat(handle.fileno())
        if not stat.S_ISREG(descriptor.st_mode) or not _same_file(path_state, descriptor):
            raise _Fallback("SOURCE_LSTAT_FSTAT_MISMATCH")
        self._source_path_open = path_state
        self._source_descriptor_open = descriptor

    def _validate_source_certificate(self) -> None:
        assert self.source_handle is not None
        assert self._source_descriptor_open is not None
        descriptor = self._source_descriptor_open
        state = self.state
        if (
            str(state["source_path"]) != _normalized_path(self.source_path)
            or str(state["normalized_path_hash"]) != normalized_path_hash(self.source_path)
        ):
            raise _Fallback("SOURCE_PATH_MISMATCH")
        if str(int(descriptor.st_dev)) != str(state["dev"]) or str(
            int(descriptor.st_ino)
        ) != str(state["inode"]):
            raise _Fallback("SOURCE_FILE_ID_MISMATCH")
        certified = int(state["certified_watermark"])
        certified_size = int(state["certified_source_size"])
        if certified_size < certified or int(descriptor.st_size) != certified_size:
            raise _Fallback("CERTIFIED_SOURCE_SIZE_MISMATCH")
        if (
            int(descriptor.st_mtime_ns) != int(state["certified_source_mtime_ns"])
            or int(descriptor.st_ctime_ns) != int(state["certified_source_ctime_ns"])
        ):
            raise _Fallback("CERTIFIED_SOURCE_METADATA_MISMATCH")
        anchor_length = int(state["certified_anchor_length"])
        anchor_offset = int(state["certified_anchor_offset"])
        expected_length = min(int(state["anchor_bytes"]), certified)
        if (
            anchor_length != expected_length
            or anchor_offset != certified - expected_length
            or len(bytes(state["certified_anchor"])) != 16
        ):
            raise _Fallback("CERTIFIED_ANCHOR_SHAPE")
        actual = self.read_exact(anchor_offset, anchor_length, kind="boundary")
        if _blake128(actual) != bytes(state["certified_anchor"]):
            raise _Fallback("CERTIFIED_ANCHOR_MISMATCH")
        if certified and self.read_exact(certified - 1, 1, kind="boundary") != b"\n":
            raise _Fallback("CERTIFIED_WATERMARK_NOT_ALIGNED")

        generation = str(state["generation_uuid"])
        self.snapshot = SourceSnapshotMetadata(
            source_path=_normalized_path(self.source_path),
            path_fingerprint=path_fingerprint(self.source_path),
            dev=int(descriptor.st_dev),
            inode=int(descriptor.st_ino),
            source_size=int(descriptor.st_size),
            snapshot_eof=int(descriptor.st_size),
            page_end=int(descriptor.st_size),
            mtime_ns=int(descriptor.st_mtime_ns),
            ctime_ns=int(descriptor.st_ctime_ns),
            source_generation_witness=_source_generation_witness(
                self.source_path, descriptor, generation, certified
            ),
            index_path=_normalized_path(self.index_path),
            index_generation_uuid=generation,
            index_schema_version=SCHEMA_VERSION_V2,
            index_version=INDEX_VERSION_V2,
            certified_watermark=certified,
            certification_kind=str(state["certification_kind"]),
        )

    def snapshot_for_plan(self, plan: PhysicalPagePlan) -> SourceSnapshotMetadata:
        if self.snapshot is None:
            raise _Fallback("SESSION_NOT_OPEN")
        return SourceSnapshotMetadata(
            **{
                **self.snapshot.to_dict(),
                "snapshot_eof": int(plan.snapshot_eof),
                "page_end": int(plan.page_end),
            }
        )

    def plan_physical_page(
        self,
        *,
        scan_cursor: Optional[str] = None,
        **planner_options: Any,
    ) -> PhysicalPagePlan:
        """Plan using this session's exact FD, transaction, state and snapshot."""

        if (
            self.connection is None
            or self.source_handle is None
            or self.snapshot is None
            or self._source_descriptor_open is None
            or self._source_path_open is None
        ):
            raise _Fallback("SESSION_NOT_OPEN")
        return plan_physical_page_pinned(
            self.source_path,
            self.index_path,
            self.source_id,
            connection=self.connection,
            source_handle=self.source_handle,
            source_state=self.state,
            source_descriptor=self._source_descriptor_open,
            source_path_state=self._source_path_open,
            expected_snapshot_eof=self.snapshot.source_size,
            expected_generation_uuid=self.snapshot.index_generation_uuid,
            scan_cursor=scan_cursor,
            **planner_options,
        )

    def bind_plan(
        self,
        plan: PhysicalPagePlan,
        expected_snapshot: Optional[SourceSnapshotMetadata] = None,
    ) -> SourceSnapshotMetadata:
        if plan.status != REPRODUCIBLE:
            reason = plan.reason or NOT_REPRODUCIBLE
            raise _Fallback(f"PLANNER_NOT_REPRODUCIBLE:{reason}")
        if self.snapshot is None:
            raise _Fallback("SESSION_NOT_OPEN")
        if int(plan.boundary_scan_bytes) + int(plan.validation_bytes) > self.caps.max_boundary_bytes:
            raise _Fallback("BOUNDARY_BYTE_CAP_EXCEEDED")
        if int(plan.certified_watermark) != int(self.state["certified_watermark"]):
            raise _Fallback("PLAN_CERTIFIED_WATERMARK_MISMATCH")
        if int(plan.source_size_bytes) != int(self.snapshot.source_size):
            raise _Fallback("PLAN_SOURCE_SIZE_MISMATCH")
        cursor_inputs = dict(plan.cursor_inputs)
        if str(cursor_inputs.get("path", "")) != self.snapshot.path_fingerprint:
            raise _Fallback("PLAN_PATH_FINGERPRINT_MISMATCH")
        try:
            plan_dev = int(cursor_inputs["dev"])
            plan_inode = int(cursor_inputs["ino"])
            cursor_snapshot_eof = int(cursor_inputs["snapshot_eof"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _Fallback("PLAN_SOURCE_WITNESS_INVALID") from exc
        if plan_dev != self.snapshot.dev or plan_inode != self.snapshot.inode:
            raise _Fallback("PLAN_SOURCE_FILE_ID_MISMATCH")
        if (
            cursor_snapshot_eof != int(plan.snapshot_eof)
            or int(plan.snapshot_eof) != int(self.snapshot.source_size)
        ):
            raise _Fallback("PLAN_SNAPSHOT_EOF_MISMATCH")
        if not (
            0
            <= int(plan.page_start)
            <= int(plan.page_end)
            <= int(plan.snapshot_eof)
            <= int(self.snapshot.source_size)
        ):
            raise _Fallback("PLAN_WINDOW_INVALID")
        bound = self.snapshot_for_plan(plan)
        if expected_snapshot is not None and bound != expected_snapshot:
            raise _Fallback("SOURCE_SNAPSHOT_WITNESS_MISMATCH")
        return bound

    @property
    def total_journal_bytes(self) -> int:
        return self._journal_bytes

    @property
    def pinned_planner_validation_bytes(self) -> int:
        """C0 validation bytes already read while this session was entered."""

        if self.certification_state != CERTIFICATION_STATE_FULL:
            raise _Fallback("SESSION_NOT_FULL_CERTIFIED")
        certified = int(self.state["certified_watermark"])
        return int(self.state["certified_anchor_length"]) + (1 if certified else 0)

    def _reserve_journal(self, length: int) -> None:
        if length < 0 or self._journal_bytes + length > self.caps.max_source_journal_bytes:
            raise _Fallback("SOURCE_JOURNAL_BYTE_CAP_EXCEEDED")
        self._journal_bytes += length
        self.metrics.source_journal_bytes = self._journal_bytes

    def account_planner_journal_bytes(self, length: int) -> None:
        """Charge C0 planner reads to the request-wide C1 journal budget once."""

        if self._planner_bytes_accounted:
            raise _Fallback("PLANNER_BYTES_ALREADY_ACCOUNTED")
        self._reserve_journal(length)
        self._planner_journal_bytes = length
        self._planner_bytes_accounted = True

    def read_exact(self, offset: int, length: int, *, kind: str) -> bytes:
        if self.source_handle is None or offset < 0 or length < 0:
            raise _Fallback("SOURCE_RANGE_INVALID")
        if (
            kind == "boundary"
            and self.metrics.boundary_bytes + length > self.caps.max_boundary_bytes
        ):
            raise _Fallback("BOUNDARY_BYTE_CAP_EXCEEDED")
        self._reserve_journal(length)
        self.source_handle.seek(offset, os.SEEK_SET)
        value = self.source_handle.read(length)
        if len(value) != length:
            raise _Fallback("SOURCE_SHORT_READ")
        if kind == "factual":
            self.metrics.factual_journal_bytes += length
        elif kind == "tail":
            self.metrics.tail_bytes += length
        else:
            self.metrics.boundary_bytes += length
            if self.metrics.boundary_bytes > self.caps.max_boundary_bytes:
                raise _Fallback("BOUNDARY_BYTE_CAP_EXCEEDED")
        return value

    def iter_lines(
        self,
        start: int,
        end: int,
        *,
        kind: str,
        byte_cap: int,
        line_cap: Optional[int],
    ) -> Iterator[tuple[int, bytes]]:
        if start < 0 or end < start:
            raise _Fallback("SOURCE_RANGE_INVALID")
        if end - start > byte_cap:
            raise _Fallback(
                "TAIL_BYTE_CAP_EXCEEDED" if kind == "tail" else "BOUNDARY_BYTE_CAP_EXCEEDED"
            )
        cursor = start
        line_start = start
        pending = bytearray()
        lines = 0
        while cursor < end:
            length = min(64 * 1024, end - cursor)
            chunk = self.read_exact(cursor, length, kind=kind)
            cursor += len(chunk)
            chunk_start = 0
            while chunk_start < len(chunk):
                newline = chunk.find(b"\n", chunk_start)
                if newline < 0:
                    pending.extend(chunk[chunk_start:])
                    break
                pending.extend(chunk[chunk_start : newline + 1])
                lines += 1
                if line_cap is not None and lines > line_cap:
                    raise _Fallback("TAIL_LINE_CAP_EXCEEDED")
                yield line_start, bytes(pending)
                pending.clear()
                line_start = cursor - len(chunk) + newline + 1
                chunk_start = newline + 1
        if pending:
            lines += 1
            if line_cap is not None and lines > line_cap:
                raise _Fallback("TAIL_LINE_CAP_EXCEEDED")
            yield line_start, bytes(pending)

    def _timed_execute(self, sql: str, parameters: Sequence[Any]) -> sqlite3.Cursor:
        assert self.connection is not None
        began = time.perf_counter()
        try:
            return self.connection.execute(sql, tuple(parameters))
        finally:
            self.metrics.index_lookup_ms += (time.perf_counter() - began) * 1000.0

    def open_candidate_stream(
        self,
        identity_type: str,
        identity_value: str,
        start: int,
        end: int,
    ) -> "_CandidateStream":
        if self._active_cursors >= self.caps.max_heap_cursors:
            raise _Fallback("HEAP_CURSOR_CAP_EXCEEDED")
        cursor = self._timed_execute(
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
        self._active_cursors += 1
        return _CandidateStream(self, cursor)

    def _candidate_rows_fetched(self, count: int) -> None:
        self.metrics.sqlite_rows_seen += count
        self.metrics.candidate_count += count
        if self.metrics.candidate_count > self.caps.max_candidate_offsets:
            raise _Fallback("CANDIDATE_OFFSET_CAP_EXCEEDED")

    def _cursor_closed(self) -> None:
        self._active_cursors = max(0, self._active_cursors - 1)

    @staticmethod
    def metadata_from_row(row: sqlite3.Row) -> IndexedRecordMetadata:
        return IndexedRecordMetadata(
            record_id=int(row["record_id"]),
            line_number=int(row["line_number"]),
            start_offset=int(row["start_offset"]),
            byte_length=int(row["byte_length"]),
            terminator_length=int(row["terminator_length"]),
            event_type=str(row["event_type"]),
            event_epoch=float(row["event_epoch"]) if row["event_epoch"] is not None else None,
            event_timestamp=(
                str(row["event_timestamp"]) if row["event_timestamp"] is not None else None
            ),
            writer_version=(
                str(row["writer_version"]) if row["writer_version"] is not None else None
            ),
            record_hash=bytes(row["record_hash"]),
            identity_type=str(row["identity_type"]),
            identity_value=str(row["identity_value"]),
            identity_group=str(row["identity_group"]),
            identity_class=str(row["identity_class"]),
        )

    def read_and_verify_factual(
        self, metadata: IndexedRecordMetadata, start: int, end: int
    ) -> Mapping[str, Any]:
        if (
            metadata.start_offset < start
            or metadata.start_offset + metadata.byte_length > end
            or metadata.byte_length <= 0
        ):
            raise _Fallback("INDEX_RECORD_OUTSIDE_PAGE")
        physical_bytes = metadata.byte_length + (1 if metadata.start_offset else 0)
        self._reserve_journal(physical_bytes)
        self.metrics.factual_journal_bytes += physical_bytes
        assert self.source_handle is not None
        try:
            record = read_and_verify_record(self.source_handle, metadata)
        except IndexValidationError as exc:
            raise _Fallback("FACTUAL_RECORD_VERIFICATION_FAILED") from exc
        self._verify_all_record_identities(metadata, record)
        return record

    def _verify_all_record_identities(
        self, metadata: IndexedRecordMetadata, record: Mapping[str, Any]
    ) -> None:
        actual = tuple(
            (
                item.identity_type,
                item.identity_value,
                item.identity_group,
                item.identity_class,
            )
            for item in extract_typed_identities(record)
        )
        if len(actual) > self.caps.max_promoted_identities + self.caps.max_identity_queries:
            raise _Fallback("FACTUAL_IDENTITY_CARDINALITY_CAP_EXCEEDED")
        cursor = self._timed_execute(
            """
            SELECT i.identity_type, i.identity_value, i.identity_group, i.identity_class
            FROM postings AS p INDEXED BY postings_record_idx
            JOIN identities i ON i.identity_id=p.identity_id
            WHERE p.record_id=? AND p.start_offset=?
            ORDER BY i.identity_type, i.identity_value, i.identity_group, i.identity_class
            """,
            (metadata.record_id, metadata.start_offset),
        )
        position = 0
        try:
            while True:
                began = time.perf_counter()
                rows = cursor.fetchmany(self.caps.max_sqlite_fetch_batch)
                self.metrics.index_lookup_ms += (time.perf_counter() - began) * 1000.0
                if not rows:
                    break
                self.metrics.sqlite_rows_seen += len(rows)
                for row in rows:
                    indexed = (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
                    if position >= len(actual) or actual[position] != indexed:
                        raise _Fallback("FACTUAL_IDENTITY_SET_MISMATCH")
                    position += 1
        finally:
            cursor.close()
        if position != len(actual):
            raise _Fallback("FACTUAL_IDENTITY_SET_MISMATCH")

    def final_check(self) -> None:
        if (
            self.source_handle is None
            or self.connection is None
            or self._source_descriptor_open is None
            or self._source_path_open is None
            or self._index_path_open is None
        ):
            raise _Fallback("SESSION_NOT_OPEN")
        final_descriptor = os.fstat(self.source_handle.fileno())
        try:
            final_path = self.source_path.lstat()
            final_index = self.index_path.lstat()
        except FileNotFoundError as exc:
            raise _Fallback("SOURCE_OR_INDEX_REMOVED_DURING_BUILD") from exc
        if not _same_snapshot(self._source_descriptor_open, final_descriptor):
            raise _Fallback("SOURCE_MUTATED_DURING_BUILD")
        if not _same_snapshot(self._source_path_open, final_path):
            raise _Fallback("SOURCE_PATH_MUTATED_DURING_BUILD")
        if not _same_snapshot(self._index_path_open, final_index):
            raise _Fallback("INDEX_GENERATION_CHANGED_DURING_BUILD")
        if Path(os.fspath(self.index_path) + "-wal").exists() or Path(
            os.fspath(self.index_path) + "-shm"
        ).exists():
            raise _Fallback("INDEX_SIDECAR_APPEARED_DURING_BUILD")
        state = self.connection.execute(
            "SELECT state, generation_uuid, certification_kind, certified_watermark, "
            "serving_contract_version, serving_certified_watermark, "
            "serving_completeness_hash, serving_certification_kind, "
            "serving_certified_at, serving_record_count, serving_identity_count, "
            "serving_posting_count "
            "FROM source_state WHERE singleton_id=1"
        ).fetchone()
        try:
            final_witness = _certification_witness(state) if state is not None else None
        except (KeyError, TypeError, ValueError):
            final_witness = None
        if (
            self._certification_witness_open is None
            or final_witness != self._certification_witness_open
        ):
            raise _Fallback("CERTIFICATION_CHANGED_DURING_BUILD")

    def close(self) -> None:
        try:
            if self.source_handle is not None:
                self.source_handle.close()
        finally:
            self.source_handle = None
            if self.connection is not None:
                try:
                    self.connection.execute("ROLLBACK")
                except sqlite3.DatabaseError:
                    pass
                finally:
                    self.connection.close()
                    self.connection = None
            self._certification_state = CERTIFICATION_STATE_NONE
            self._certification_witness_open = None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


class _CandidateStream:
    def __init__(self, session: PinnedSourceIndexSession, cursor: sqlite3.Cursor) -> None:
        self.session = session
        self.cursor = cursor
        self.buffer: deque[sqlite3.Row] = deque()
        self.closed = False

    def next(self) -> Optional[sqlite3.Row]:
        if self.closed:
            return None
        if not self.buffer:
            remaining = (
                self.session.caps.max_candidate_offsets
                - self.session.metrics.candidate_count
            )
            # Do not fetch beyond the global candidate budget.  At the exact
            # boundary we fail closed instead of probing one extra SQLite row.
            if remaining <= 0:
                raise _Fallback("CANDIDATE_OFFSET_CAP_EXCEEDED")
            began = time.perf_counter()
            rows = self.cursor.fetchmany(
                min(self.session.caps.max_sqlite_fetch_batch, remaining)
            )
            self.session.metrics.index_lookup_ms += (time.perf_counter() - began) * 1000.0
            if not rows:
                self.close()
                return None
            self.session._candidate_rows_fetched(len(rows))
            self.buffer.extend(rows)
        return self.buffer.popleft()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.cursor.close()
        finally:
            self.buffer.clear()
            self.session._cursor_closed()


def _events_for_source(component: str, rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    import trade_timeline_validator as validator

    events: list[dict[str, Any]] = []
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
    return tuple(_frozen(item) for item in events)


def _promotion_delta(before: Any, after: Any) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    before_typed = _known_typed_values(before)
    after_typed = _known_typed_values(after)
    before_grouped = _known_group_values(before)
    after_grouped = _known_group_values(after)
    typed: dict[str, list[str]] = {}
    grouped: dict[str, list[str]] = {}
    for identity_type, value in sorted(after_typed - before_typed):
        typed.setdefault(identity_type, []).append(value)
    for group, value in sorted(after_grouped - before_grouped):
        grouped.setdefault(group, []).append(value)
    return (
        {key: tuple(values) for key, values in typed.items()},
        {key: tuple(values) for key, values in grouped.items()},
    )


def _identity_delta_from_sets(
    before_typed: set[tuple[str, str]],
    before_grouped: set[tuple[str, str]],
    context: Any,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    typed: dict[str, list[str]] = {}
    grouped: dict[str, list[str]] = {}
    for identity_type, value in sorted(_known_typed_values(context) - before_typed):
        typed.setdefault(identity_type, []).append(value)
    for group, value in sorted(_known_group_values(context) - before_grouped):
        grouped.setdefault(group, []).append(value)
    return (
        {key: tuple(values) for key, values in typed.items()},
        {key: tuple(values) for key, values in grouped.items()},
    )


def _correlate_one(
    component: str,
    record: Mapping[str, Any],
    offset: int,
    context: Any,
    caps: EnvelopeCaps,
    metrics: _Metrics,
    promotions: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    import trade_timeline_validator as validator

    before_typed = _known_typed_values(context)
    before_grouped = _known_group_values(context)
    selected = validator.correlate_source_records(component, (record,), context)
    if not selected:
        return []
    typed, grouped = _identity_delta_from_sets(
        before_typed,
        before_grouped,
        context,
    )
    new_typed_count = sum(len(values) for values in typed.values())
    if metrics.promotion_count + new_typed_count > caps.max_promoted_identities:
        raise _Fallback("PROMOTED_IDENTITY_CAP_EXCEEDED")
    if new_typed_count or grouped:
        metrics.promotion_count += new_typed_count
        promotions.append(
            _frozen(
                {
                    "offset": int(offset),
                    "typed": typed,
                    "grouped": grouped,
                }
            )
        )
    return selected


def _process_factual_stream(
    session: PinnedSourceIndexSession,
    component: str,
    context: Any,
    lines: Iterable[tuple[int, bytes]],
    caps: EnvelopeCaps,
    metrics: _Metrics,
    promotions: list[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[int]]:
    rows: list[Mapping[str, Any]] = []
    offsets: list[int] = []
    for offset, raw_line in lines:
        try:
            classification = classify_physical_line(
                raw_line,
                newline_terminated=raw_line.endswith(b"\n"),
            )
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise _Fallback("PHYSICAL_LINE_CLASSIFICATION_FAILED") from exc
        if not classification.mapping:
            continue
        metrics.record_count += 1
        if metrics.record_count > caps.max_factual_records:
            raise _Fallback("FACTUAL_RECORD_CAP_EXCEEDED")
        selected = _correlate_one(
            component,
            classification.value,
            offset,
            context,
            caps,
            metrics,
            promotions,
        )
        for row in selected:
            rows.append(row)
            offsets.append(int(offset))
    return rows, offsets


def _retrieve_indexed_prefix(
    session: PinnedSourceIndexSession,
    component: str,
    context: Any,
    start: int,
    end: int,
    caps: EnvelopeCaps,
    metrics: _Metrics,
    promotions: list[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[int]]:
    if end <= start:
        return [], []
    heap: list[tuple[int, int, _CandidateStream, sqlite3.Row]] = []
    streams: list[_CandidateStream] = []
    scheduled: dict[tuple[str, str], int] = {}
    serial = 0

    def schedule(group: str, value: str, lower_bound: int) -> None:
        nonlocal serial
        for identity_type in _GROUP_TYPES.get(group, ()):
            if classify_identity(identity_type, value) is None:
                continue
            key = (identity_type, value)
            previous = scheduled.get(key)
            if previous is not None and previous <= lower_bound:
                continue
            if metrics.identity_query_count >= caps.max_identity_queries:
                raise _Fallback("IDENTITY_QUERY_CAP_EXCEEDED")
            scheduled[key] = lower_bound
            metrics.identity_query_count += 1
            stream = session.open_candidate_stream(
                identity_type,
                value,
                max(start, lower_bound),
                end,
            )
            streams.append(stream)
            row = stream.next()
            if row is not None:
                serial += 1
                heapq.heappush(heap, (int(row["start_offset"]), serial, stream, row))

    try:
        for group, value in sorted(_known_group_values(context)):
            schedule(group, value, start)

        matched: list[Mapping[str, Any]] = []
        matched_offsets: list[int] = []
        seen_offsets: set[int] = set()
        while heap:
            offset, _order, stream, row = heapq.heappop(heap)
            following = stream.next()
            if following is not None:
                serial += 1
                heapq.heappush(
                    heap,
                    (int(following["start_offset"]), serial, stream, following),
                )
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            metrics.offset_count += 1
            if metrics.offset_count > caps.max_candidate_offsets:
                raise _Fallback("CANDIDATE_OFFSET_CAP_EXCEEDED")
            metrics.record_count += 1
            if metrics.record_count > caps.max_factual_records:
                raise _Fallback("FACTUAL_RECORD_CAP_EXCEEDED")
            metadata = session.metadata_from_row(row)
            record = session.read_and_verify_factual(metadata, start, end)
            known_before = _known_group_values(context)
            selected = _correlate_one(
                component,
                record,
                metadata.start_offset,
                context,
                caps,
                metrics,
                promotions,
            )
            for selected_row in selected:
                matched.append(selected_row)
                matched_offsets.append(metadata.start_offset)
            for group, value in sorted(_known_group_values(context) - known_before):
                schedule(group, value, metadata.start_offset + 1)
        return matched, matched_offsets
    finally:
        for stream in streams:
            stream.close()


def _reader_metadata(plan: PhysicalPagePlan, context: Any, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    metadata = {
        "files_considered": 1,
        "files_read": 1,
        **plan.legacy_physical_metadata(),
    }
    matched = bool(rows)
    ambiguous = bool(
        getattr(context, "identity_ambiguous", False)
        and not getattr(context, "registry_anchored", False)
    )
    metadata["evidence_found"] = matched
    metadata["conclusive"] = bool(metadata["coverage_complete"] and not ambiguous)
    if ambiguous:
        metadata["evidence_status"] = "IDENTITY_AMBIGUOUS"
    elif matched:
        metadata["evidence_status"] = "EVIDENCE_FOUND"
    elif metadata["coverage_complete"]:
        metadata["evidence_status"] = "COMPLETE_NO_EVIDENCE"
    else:
        metadata["evidence_status"] = "NOT_FOUND_IN_SCANNED_REGION"
    return metadata


def _source_coverage(metadata: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    coverage = {
        "evidence_found": bool(metadata.get("evidence_found", bool(rows))),
        "coverage_complete": bool(metadata.get("coverage_complete", True)),
        "partial": bool(metadata.get("partial", False)),
        "conclusive": bool(metadata.get("conclusive", True)),
        "bytes_scanned": int(metadata.get("bytes_scanned", 0) or 0),
        "records_examined": int(metadata.get("records_examined", len(rows)) or 0),
        "direction": metadata.get("direction", "IN_MEMORY"),
        "time_range_scanned": dict(
            metadata.get("time_range_scanned") or {"oldest": None, "newest": None}
        ),
        "stop_reason": metadata.get("stop_reason", "IN_MEMORY_COMPLETE"),
        "source_size_bytes": int(metadata.get("source_size_bytes", 0) or 0),
        "snapshot_eof": int(metadata.get("snapshot_eof", 0) or 0),
        "evidence_status": metadata.get(
            "evidence_status", "EVIDENCE_FOUND" if rows else "COMPLETE_NO_EVIDENCE"
        ),
    }
    if metadata.get("next_scan_cursor"):
        coverage["next_scan_cursor"] = metadata["next_scan_cursor"]
    return coverage


def _target_matches_context(target_identity: Any, context: Any) -> bool:
    import trade_timeline_validator as validator

    try:
        return target_identity == validator.target_identity_from_context(context)
    except Exception:
        return False


def _empty_envelope(
    source: str,
    reason: str,
    context_before: Any,
    metrics: _Metrics,
    *,
    plan: Optional[PhysicalPagePlan] = None,
    snapshot: Optional[SourceSnapshotMetadata] = None,
) -> IndexedSourceEnvelope:
    try:
        projected_context = _context_projection(context_before)
    except Exception:
        projected_context = {"trade_id": str(getattr(context_before, "trade_id", ""))}
    context_projection = _frozen(projected_context)
    physical = _frozen(plan.legacy_physical_metadata() if plan is not None else {})
    raw = {
        "snapshot": snapshot.to_dict() if snapshot is not None else {},
        "plan": plan.to_dict() if plan is not None else {},
    }
    return IndexedSourceEnvelope(
        source=source,
        status=FALLBACK_REQUIRED,
        fallback_reason=reason,
        index_mode=metrics.mode,
        negative_status=NEGATIVE_UNSAFE,
        completeness_status=COMPLETENESS_UNKNOWN,
        correlated_rows=(),
        physical_metadata=physical,
        source_coverage=_frozen({}),
        raw_source_metadata=_frozen(raw),
        identifiers_discovered=_frozen({"typed": {}, "grouped": {}}),
        promotion_metadata=(),
        context_before=context_projection,
        context_after=context_projection,
        factual_offsets=(),
        events=(),
        metrics=metrics.freeze(),
        _context_after_clone=_safe_deepcopy(context_before),
    )


def _build_with_session(
    session: PinnedSourceIndexSession,
    *,
    source: str,
    target_identity: Any,
    correlation_context: Any,
    physical_plan: PhysicalPagePlan,
    expected_snapshot: Optional[SourceSnapshotMetadata],
    caps: EnvelopeCaps,
    fault_injector: FaultInjector,
    trusted_pinned_plan: bool,
    scan_cursor_supplied: bool,
) -> IndexedSourceEnvelope:
    import trade_timeline_validator as validator

    if not _target_matches_context(target_identity, correlation_context):
        raise _Fallback("TARGET_CONTEXT_MISMATCH")
    context_before = copy.deepcopy(correlation_context)
    context = copy.deepcopy(correlation_context)
    snapshot = session.bind_plan(physical_plan, expected_snapshot)
    certified = int(snapshot.certified_watermark)
    mode = INDEX_ONLY if int(physical_plan.page_end) <= certified else INDEX_PLUS_TAIL
    session.metrics.mode = mode
    terminal_tail_incomplete = False
    if (
        int(physical_plan.page_end) == int(snapshot.snapshot_eof)
        and int(physical_plan.page_end) > certified
    ):
        terminal_tail_incomplete = (
            session.read_exact(
                int(physical_plan.page_end) - 1,
                1,
                kind="boundary",
            )
            != b"\n"
        )
    if fault_injector is not None:
        fault_injector("after_session_open", snapshot.to_dict())

    replay_start = int(
        getattr(physical_plan, "replay_start", int(physical_plan.page_start))
    )
    if not 0 <= replay_start <= int(physical_plan.page_start):
        raise _Fallback("PLAN_REPLAY_RANGE_INVALID")
    rows: list[Mapping[str, Any]] = []
    offsets: list[int] = []
    promotions: list[Mapping[str, Any]] = []

    if replay_start < int(physical_plan.page_start):
        boundary_rows, boundary_offsets = _process_factual_stream(
            session,
            source,
            context,
            session.iter_lines(
                replay_start,
                int(physical_plan.page_start),
                kind="boundary",
                byte_cap=caps.max_boundary_bytes,
                line_cap=None,
            ),
            caps,
            session.metrics,
            promotions,
        )
        rows.extend(boundary_rows)
        offsets.extend(boundary_offsets)
    if fault_injector is not None:
        fault_injector("after_replay_boundary", {"replay_start": replay_start})

    prefix_start = int(physical_plan.page_start)
    prefix_end = min(int(physical_plan.page_end), certified)
    indexed_rows, indexed_offsets = _retrieve_indexed_prefix(
        session,
        source,
        context,
        prefix_start,
        prefix_end,
        caps,
        session.metrics,
        promotions,
    )
    rows.extend(indexed_rows)
    offsets.extend(indexed_offsets)
    if fault_injector is not None:
        fault_injector("after_indexed_prefix", {"prefix_end": prefix_end})

    tail_start = max(int(physical_plan.page_start), certified)
    tail_end = int(physical_plan.page_end)
    if tail_end > tail_start:
        if tail_start and session.read_exact(tail_start - 1, 1, kind="boundary") != b"\n":
            raise _Fallback("TAIL_START_NOT_ALIGNED")
        tail_rows, tail_offsets = _process_factual_stream(
            session,
            source,
            context,
            session.iter_lines(
                tail_start,
                tail_end,
                kind="tail",
                byte_cap=caps.max_tail_bytes,
                line_cap=caps.max_tail_lines,
            ),
            caps,
            session.metrics,
            promotions,
        )
        rows.extend(tail_rows)
        offsets.extend(tail_offsets)
    if fault_injector is not None:
        fault_injector("before_final_check", {"tail_end": tail_end})
    session.final_check()

    typed_discovered, grouped_discovered = _promotion_delta(context_before, context)
    identity_metadata = validator.identity_resolution_metadata(context)
    physical_metadata = _reader_metadata(physical_plan, context, rows)
    coverage = _source_coverage(physical_metadata, rows)
    # A FULL certificate authenticates both the C0 physical summaries and the
    # complete logical serving tables.  It can authorize a C2 claim only when
    # the plan itself was produced from this exact pinned transaction/FD.  The
    # C1 testing entrypoint accepts external plans and therefore remains
    # explicitly uncertified even when its index carries the same seals.
    full_certified = bool(
        trusted_pinned_plan
        and session.certification_state == CERTIFICATION_STATE_FULL
    )
    completeness_status = (
        COMPLETENESS_FULL_CERTIFIED
        if full_certified
        else COMPLETENESS_UNCERTIFIED
    )
    negative_status = NOT_NEGATIVE
    if not rows:
        negative_status = (
            NEGATIVE_CERTIFIED
            if full_certified
            and bool(physical_metadata.get("coverage_complete", False))
            and bool(physical_metadata.get("conclusive", False))
            and not terminal_tail_incomplete
            and not scan_cursor_supplied
            else NEGATIVE_UNSAFE
        )
    raw_source_metadata = {
        "snapshot": snapshot.to_dict(),
        "plan": physical_plan.to_dict(),
        "identity_metadata": identity_metadata,
        "terminal_tail_incomplete": terminal_tail_incomplete,
        "scan_cursor_supplied": bool(scan_cursor_supplied),
    }
    result = IndexedSourceEnvelope(
        source=source,
        status=BUILT,
        fallback_reason=None,
        index_mode=mode,
        negative_status=negative_status,
        completeness_status=completeness_status,
        correlated_rows=tuple(_frozen(copy.deepcopy(row)) for row in rows),
        physical_metadata=_frozen(physical_metadata),
        source_coverage=_frozen(coverage),
        raw_source_metadata=_frozen(raw_source_metadata),
        identifiers_discovered=_frozen(
            {"typed": typed_discovered, "grouped": grouped_discovered}
        ),
        promotion_metadata=tuple(promotions),
        context_before=_frozen(_context_projection(context_before)),
        context_after=_frozen(_context_projection(context)),
        factual_offsets=tuple(offsets),
        events=_events_for_source(source, rows),
        metrics=session.metrics.freeze(),
        _context_after_clone=copy.deepcopy(context),
    )
    # Metadata/event projection and defensive copies are still part of the
    # staged build.  Revalidate immediately before publication so mutation in
    # that post-read window discards the complete result and trial context.
    session.final_check()
    return result


def build_indexed_source_envelope(
    *,
    source: str,
    source_path: Path | str,
    index_path: Path | str,
    target_identity: Any,
    correlation_context: Any,
    physical_plan: PhysicalPagePlan,
    expected_snapshot: Optional[SourceSnapshotMetadata] = None,
    session: Optional[PinnedSourceIndexSession] = None,
    caps: EnvelopeCaps = EnvelopeCaps(),
    planner_ms: float = 0.0,
    fault_injector: FaultInjector = None,
) -> IndexedSourceEnvelope:
    """Internal/testing-only builder for an externally supplied physical plan.

    Runtime dispatch must use :func:`plan_and_build_indexed_source_envelope`.
    External plans cannot establish completeness or a certified negative.
    """

    started = time.perf_counter()
    metrics = session.metrics if session is not None else _Metrics()
    metrics.planner_ms = max(0.0, float(planner_ms))
    metrics.planner_segment_rows = int(physical_plan.segment_rows_consulted)
    plan_boundary_bytes = int(physical_plan.boundary_scan_bytes) + int(
        physical_plan.validation_bytes
    )
    if session is None:
        metrics.boundary_bytes = plan_boundary_bytes
    else:
        metrics.boundary_bytes += plan_boundary_bytes
    try:
        context_before = copy.deepcopy(correlation_context)
    except Exception:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source,
            "CONTEXT_CLONE_FAILED",
            correlation_context,
            metrics,
            plan=physical_plan,
        )
    active_session = session
    owns_session = session is None
    snapshot: Optional[SourceSnapshotMetadata] = None
    try:
        caps.validate()
        if metrics.boundary_bytes > caps.max_boundary_bytes:
            raise _Fallback("BOUNDARY_BYTE_CAP_EXCEEDED")
        if source not in SUPPORTED_SOURCES:
            raise _Fallback("UNSUPPORTED_SOURCE")
        if active_session is None:
            active_session = PinnedSourceIndexSession(
                source_path,
                index_path,
                source,
                caps=caps,
                metrics=metrics,
            )
            active_session.__enter__()
        elif (
            active_session.source_id != source
            or active_session.source_path != Path(source_path)
            or active_session.index_path != Path(index_path)
            or active_session.caps != caps
        ):
            raise _Fallback("SESSION_ARGUMENT_MISMATCH")
        active_session.account_planner_journal_bytes(plan_boundary_bytes)
        snapshot = active_session.snapshot_for_plan(physical_plan)
        result = _build_with_session(
            active_session,
            source=source,
            target_identity=target_identity,
            correlation_context=correlation_context,
            physical_plan=physical_plan,
            expected_snapshot=expected_snapshot,
            caps=caps,
            fault_injector=fault_injector,
            trusted_pinned_plan=False,
            scan_cursor_supplied=False,
        )
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return replace(result, metrics=metrics.freeze())
    except _Fallback as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source,
            exc.reason,
            context_before,
            metrics,
            plan=physical_plan,
            snapshot=snapshot,
        )
    except sqlite3.OperationalError as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        text = str(exc).lower()
        reason = "SQLITE_BUSY" if "busy" in text or "locked" in text else "SQLITE_READ_FAILED"
        return _empty_envelope(
            source, reason, context_before, metrics, plan=physical_plan, snapshot=snapshot
        )
    except Exception as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source,
            f"C1_BUILD_FAILED:{type(exc).__name__}",
            context_before,
            metrics,
            plan=physical_plan,
            snapshot=snapshot,
        )
    finally:
        if owns_session and active_session is not None:
            active_session.close()


def plan_and_build_from_pinned_session(
    session: PinnedSourceIndexSession,
    *,
    target_identity: Any,
    correlation_context: Any,
    scan_cursor: Optional[str] = None,
    fault_injector: FaultInjector = None,
    **planner_options: Any,
) -> IndexedSourceEnvelope:
    """Plan/build on an entered session without taking resource ownership.

    This is the safe composition API for callers that must keep multiple
    source/index snapshots pinned across a larger shadow/offline transaction.
    It derives source paths, caps and witnesses from ``session`` and accepts no
    externally supplied :class:`PhysicalPagePlan`.
    """

    source = session.source_id
    metrics = session.metrics
    caps = session.caps
    started = time.perf_counter()
    try:
        context_before = copy.deepcopy(correlation_context)
    except Exception:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source, "CONTEXT_CLONE_FAILED", correlation_context, metrics
        )
    try:
        if (
            session.connection is None
            or session.source_handle is None
            or session.snapshot is None
        ):
            raise _Fallback("SESSION_NOT_OPEN")
        caps.validate()
        options = dict(planner_options)
        if set(options) - _SAFE_PINNED_PLANNER_OPTIONS:
            raise _Fallback("PLANNER_OPTION_FORBIDDEN")
        try:
            requested_boundary = int(
                options.get("max_boundary_scan_bytes", caps.max_boundary_bytes)
            )
            requested_append_proof = int(
                options.get("max_append_proof_bytes", 1)
            )
            requested_segment_rows = int(
                options.get("max_segment_rows", DEFAULT_MAX_SEGMENT_ROWS)
            )
        except (TypeError, ValueError) as exc:
            raise _Fallback("PLANNER_CAP_INVALID") from exc
        if requested_boundary <= 0 or requested_append_proof <= 0:
            raise _Fallback("PLANNER_CAP_INVALID")
        if not 0 < requested_segment_rows <= DEFAULT_MAX_SEGMENT_ROWS:
            raise _Fallback("PLANNER_SEGMENT_ROW_CAP_EXCEEDED")
        if requested_boundary > caps.max_boundary_bytes:
            raise _Fallback("PLANNER_BOUNDARY_CAP_EXCEEDED")
        # A source that grows after this session was pinned is never usable by
        # this lifecycle.  One byte retains the planner's fail-closed probe.
        if requested_append_proof > 1:
            raise _Fallback("PLANNER_APPEND_PROOF_CAP_EXCEEDED")
        # Eligibility/anchor reads were charged while entering this exact
        # session.  Remaining validation is at most tail, growth and cursor.
        validation_allowance = 2 + (1 if scan_cursor is not None else 0)
        remaining = caps.max_source_journal_bytes - session.total_journal_bytes
        boundary_remaining = (
            caps.max_boundary_bytes - metrics.boundary_bytes - validation_allowance
        )
        boundary_allowance = min(
            requested_boundary,
            remaining - validation_allowance,
            boundary_remaining,
        )
        if boundary_allowance <= 0:
            raise _Fallback("PLANNER_SOURCE_JOURNAL_BUDGET_EXHAUSTED")
        options["max_boundary_scan_bytes"] = boundary_allowance
        options["max_append_proof_bytes"] = requested_append_proof
        planner_started = time.perf_counter()
        plan = session.plan_physical_page(
            scan_cursor=scan_cursor,
            **options,
        )
        metrics.planner_ms = (time.perf_counter() - planner_started) * 1000.0
        metrics.planner_segment_rows = int(plan.segment_rows_consulted)
        plan_boundary_bytes = int(plan.boundary_scan_bytes) + int(
            plan.validation_bytes
        )
        pinned_validation_bytes = session.pinned_planner_validation_bytes
        if (
            plan.status == REPRODUCIBLE
            and int(plan.validation_bytes) < pinned_validation_bytes
        ):
            raise _Fallback("PLANNER_VALIDATION_ACCOUNTING_MISMATCH")
        # The plan reports standalone-equivalent logical validation.  Anchor
        # and watermark-alignment bytes in that number were already physically
        # read/charged by this exact session during eligibility validation.
        reused_validation_bytes = min(
            int(plan.validation_bytes), pinned_validation_bytes
        )
        new_planner_bytes = plan_boundary_bytes - reused_validation_bytes
        if metrics.boundary_bytes + new_planner_bytes > caps.max_boundary_bytes:
            raise _Fallback("BOUNDARY_BYTE_CAP_EXCEEDED")
        metrics.boundary_bytes += new_planner_bytes
        session.account_planner_journal_bytes(new_planner_bytes)
        expected_snapshot = (
            session.snapshot_for_plan(plan) if plan.status == REPRODUCIBLE else None
        )
        result = _build_with_session(
            session,
            source=source,
            target_identity=target_identity,
            correlation_context=correlation_context,
            physical_plan=plan,
            expected_snapshot=expected_snapshot,
            caps=caps,
            fault_injector=fault_injector,
            trusted_pinned_plan=True,
            scan_cursor_supplied=scan_cursor is not None,
        )
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return replace(result, metrics=metrics.freeze())
    except _Fallback as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(source, exc.reason, context_before, metrics)
    except sqlite3.OperationalError as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        text = str(exc).lower()
        reason = "SQLITE_BUSY" if "busy" in text or "locked" in text else "SQLITE_READ_FAILED"
        return _empty_envelope(source, reason, context_before, metrics)
    except Exception as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source, f"C1_PLAN_BUILD_FAILED:{type(exc).__name__}", context_before, metrics
        )


def plan_and_build_indexed_source_envelope(
    *,
    source: str,
    source_path: Path | str,
    index_path: Path | str,
    target_identity: Any,
    correlation_context: Any,
    scan_cursor: Optional[str] = None,
    caps: EnvelopeCaps = EnvelopeCaps(),
    fault_injector: FaultInjector = None,
    **planner_options: Any,
) -> IndexedSourceEnvelope:
    """Own one pinned session around the safe plan/build composition API."""

    metrics = _Metrics()
    started = time.perf_counter()
    try:
        context_before = copy.deepcopy(correlation_context)
    except Exception:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source, "CONTEXT_CLONE_FAILED", correlation_context, metrics
        )
    try:
        with PinnedSourceIndexSession(
            source_path,
            index_path,
            source,
            caps=caps,
            metrics=metrics,
        ) as session:
            result = plan_and_build_from_pinned_session(
                session,
                target_identity=target_identity,
                correlation_context=correlation_context,
                scan_cursor=scan_cursor,
                fault_injector=fault_injector,
                **planner_options,
            )
            metrics.duration_ms = (time.perf_counter() - started) * 1000.0
            return replace(result, metrics=metrics.freeze())
    except _Fallback as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(source, exc.reason, context_before, metrics)
    except sqlite3.OperationalError as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        text = str(exc).lower()
        reason = "SQLITE_BUSY" if "busy" in text or "locked" in text else "SQLITE_READ_FAILED"
        return _empty_envelope(source, reason, context_before, metrics)
    except Exception as exc:
        metrics.duration_ms = (time.perf_counter() - started) * 1000.0
        return _empty_envelope(
            source, f"C1_PLAN_BUILD_FAILED:{type(exc).__name__}", context_before, metrics
        )


__all__ = (
    "BUILT",
    "COMPLETENESS_FULL_CERTIFIED",
    "COMPLETENESS_UNCERTIFIED",
    "COMPLETENESS_UNKNOWN",
    "EnvelopeCaps",
    "FALLBACK_REQUIRED",
    "INDEX_ONLY",
    "INDEX_PLUS_TAIL",
    "IndexedSourceEnvelope",
    "MAX_BOUNDARY_BYTES",
    "MAX_CANDIDATE_OFFSETS",
    "MAX_FACTUAL_RECORDS",
    "MAX_HEAP_CURSORS",
    "MAX_IDENTITY_QUERIES",
    "MAX_PROMOTED_IDENTITIES",
    "MAX_SOURCE_JOURNAL_BYTES",
    "MAX_SQLITE_FETCH_BATCH",
    "MAX_TAIL_BYTES",
    "MAX_TAIL_LINES",
    "NEGATIVE_CERTIFIED",
    "NEGATIVE_UNSAFE",
    "NOT_NEGATIVE",
    "PinnedSourceIndexSession",
    "SourceEnvelopeMetrics",
    "SourceSnapshotMetadata",
    "VERSION",
    "plan_and_build_from_pinned_session",
    "plan_and_build_indexed_source_envelope",
)
