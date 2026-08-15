"""Versioned physical-window contract for trade-evidence JSONL readers.

This module is deliberately operationally inert.  It contains only constants
and pure helpers extracted from the physical semantics of
``trade_timeline_validator``'s bounded reverse JSONL reader.  In particular it
does not open journals, indexes, Redis, or network resources and it does not
select trade evidence.

Phase C0 keeps the legacy reader authoritative.  The contract below gives the
offline index builder and physical page planner one canonical vocabulary while
parity is proven before any future serving integration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PHYSICAL_CONTRACT_VERSION = (
    "2026-08-15-TRADE-EVIDENCE-PHYSICAL-WINDOW-CONTRACT-V1"
)
CURSOR_CONTRACT_VERSION = 1
SUMMARY_CONTRACT_VERSION = 1

BYTE_BUDGET = 64 * 1024 * 1024
RECORD_BUDGET = 100_000
BLOCK_BYTES = 64 * 1024
CURSOR_MAX_CHARS = 4096
DIRECTION = "REVERSE"

# Compatibility-oriented names make the relationship with the legacy reader
# explicit without importing that operational module.
JSONL_MAX_BYTES = BYTE_BUDGET
JSONL_MAX_VALID_LINES = RECORD_BUDGET
JSONL_BLOCK_BYTES = BLOCK_BYTES
JSONL_CURSOR_VERSION = CURSOR_CONTRACT_VERSION

TIMESTAMP_KEYS = (
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

PHYSICAL_METADATA_FIELDS = (
    "files_considered",
    "files_read",
    "bytes_scanned",
    "lines_scanned",
    "valid_lines",
    "invalid_lines",
    "records_examined",
    "time_range_scanned",
    "stop_reason",
    "source_size_bytes",
    "snapshot_eof",
    "next_scan_cursor",
    "coverage_limited",
    "coverage_complete",
    "partial",
    "conclusive",
    "evidence_status",
    "direction",
)

STOP_REASONS = (
    "NOT_SCANNED",
    "SOURCE_MISSING",
    "SOURCE_CHANGED",
    "START_OF_SNAPSHOT",
    "BYTE_BUDGET",
    "RECORD_BUDGET",
    "LINE_EXCEEDS_BYTE_BUDGET",
    "PRIOR_PAGE_COVERAGE_LIMITED",
)


# This document is the hash authority.  It intentionally describes observable
# behavior rather than Python implementation details, so harmless refactors do
# not invalidate an index while any semantic change necessarily updates the
# canonical document and therefore the hash.
_PHYSICAL_CONTRACT_DOCUMENT: dict[str, Any] = {
    "version": PHYSICAL_CONTRACT_VERSION,
    "summary_contract_version": SUMMARY_CONTRACT_VERSION,
    "direction": DIRECTION,
    "budgets": {
        "bytes": BYTE_BUDGET,
        "records": RECORD_BUDGET,
        "record_definition": "physical_line_with_non_whitespace_bytes",
        "record_limit_at_offset_zero_is_complete": True,
    },
    "blocks": {
        "bytes": BLOCK_BYTES,
        "direction": "backward_from_page_end",
        "region_start": "max(0,page_end-byte_budget)",
        "bytes_scanned": (
            "sum_of_reverse_scan_chunk_lengths_excluding_cursor_alignment_probe"
        ),
        "record_budget_may_read_older_prefix_in_same_block": True,
        "replay_offset_application": (
            "applied_only_to_oldest_loaded_chunk_without_carrying_the_"
            "remaining_offset_into_newer_chunks"
        ),
        "chunk_boundary_empty_line": (
            "an_empty_line_whose_LF_is_the_first_byte_of_a_newer_reverse_"
            "chunk_is_not_counted_when_the_preceding_chunk_ends_in_LF"
        ),
        "short_read": "SOURCE_CHANGED",
    },
    "page": {
        "first_page_end": "snapshot_eof",
        "continuation_page_end": "cursor.next_end",
        "byte_boundary": (
            "when_region_start>0_discard_carry_through_first_LF_even_if_"
            "region_start_is_a_physical_line_start"
        ),
        "record_boundary": "start_of_the_100000th_selected_nonblank_line",
        "stop_precedence": "RECORD_BUDGET_before_BYTE_BUDGET",
        "replay_order": "ascending_physical_offset",
        "append_after_snapshot": "excluded",
        "continuation_is_tainted": True,
        "tainted_at_start_without_new_cursor": (
            "PRIOR_PAGE_COVERAGE_LIMITED_except_oversized_continuation_"
            "which_preserves_LINE_EXCEEDS_BYTE_BUDGET"
        ),
        "tainted_with_new_limit": "preserve_RECORD_or_BYTE_stop_reason",
    },
    "physical_line": {
        "delimiter": "LF_byte",
        "delimiter_excluded_from_json_document": True,
        "CR_before_LF_retained": True,
        "blank_test": "bytes.strip_is_empty",
        "terminal_without_LF": "examined_and_parsed",
        "terminal_incomplete_document": "invalid_JSON_or_UTF8",
        "trailing_LF": "does_not_create_a_phantom_empty_line",
        "lines_scanned": (
            "reverse_state_machine_examined_lines_including_blank_with_the_"
            "documented_chunk_boundary_empty_line_exception"
        ),
        "records_examined": "selected_nonblank_physical_lines",
    },
    "classification": {
        "decode": "UTF-8_strict",
        "JSON": "json.loads_once_per_selected_nonblank_line",
        "invalid_UTF8": "invalid_lines_plus_one",
        "invalid_JSON": "invalid_lines_plus_one",
        "valid_mapping": "valid_lines_plus_one_and_timestamp_eligible",
        "valid_nonmapping": "valid_lines_plus_one_not_timestamp_eligible",
        "blank": "no_parse_no_valid_invalid_or_record_increment",
        "oversized_barrier": "no_fragment_parse",
    },
    "timestamp": {
        "keys": list(TIMESTAMP_KEYS),
        "walk": "depth_first_mapping_in_insertion_order_then_list_or_tuple",
        "selection": "first_nonempty_value_even_when_unparseable",
        "numeric_milliseconds_threshold": 10_000_000_000,
        "naive_timezone": "UTC",
        "formats": [
            "datetime.fromisoformat_after_global_Z_to_+00:00",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ],
        "unparseable": "stripped_text_is_normalized_value",
        "whitespace_value": "captures_key_then_empty_normalized_value_is_ignored_without_key_fallback",
        "nonfinite_or_out_of_range_numeric": "legacy_datetime_exception_propagates",
        "range": "lexical_min_max_of_truthy_normalized_mapping_timestamps",
    },
    "cursor": {
        "version": CURSOR_CONTRACT_VERSION,
        "maximum_characters": CURSOR_MAX_CHARS,
        "fields": [
            "v",
            "path",
            "dev",
            "ino",
            "snapshot_eof",
            "next_end",
            "oversized",
            "tainted",
        ],
        "required_fields": [
            "v",
            "path",
            "dev",
            "ino",
            "snapshot_eof",
            "next_end",
        ],
        "path": "sha256(normcase(abspath(fspath(path)))_UTF8_surrogatepass)",
        "serialization": "JSON_sort_keys_compact_UTF8_then_URLsafe_base64_without_padding",
        "bounds": "snapshot_eof>=0_and_0<=next_end<=snapshot_eof",
        "extra_fields": "accepted_and_discarded_on_decode",
        "flag_decode": "Python_bool_coercion",
        "oversized_implies_tainted_on_encode": True,
        "continuation_alignment": "byte_before_positive_next_end_is_LF_unless_oversized",
    },
    "source_change": {
        "open": "lstat_regular_non_symlink_matches_fstat_dev_inode",
        "cursor": "path_dev_inode_match_and_size_at_least_snapshot_eof",
        "after_read": "path_still_same_dev_inode_and_descriptor_size_at_least_snapshot_eof",
        "result": "partial_nonconclusive_SOURCE_CHANGED_without_cursor",
        "missing_without_cursor": "SOURCE_MISSING_but_default_complete_and_conclusive",
        "missing_with_cursor": "SOURCE_CHANGED",
        "normal_branch_rows": "already_selected_rows_are_still_replayed_after_post_read_SOURCE_CHANGED",
        "undetected_by_legacy": "same_inode_same_or_larger_size_rewrite_or_truncate_then_regrow",
        "planner_requirement": "stronger_checks_return_NOT_REPRODUCIBLE_for_detected_mutation",
    },
    "oversized": {
        "definition": "no_LF_boundary_reproducible_within_byte_budget",
        "exact_budget_edge": (
            "when_region_start>0_a_line_of_exactly_byte_budget_can_still_be_"
            "unalignable_if_its_preceding_LF_is_outside_the_region"
        ),
        "segment_barrier_flag_alone_is_not_a_boundary_proof": True,
        "behavior": "skip_backward_without_parsing_fragment",
        "continuation_page_flag": (
            "shadow_window_oversized_remains_true_even_when_offset_zero_is_"
            "reached_and_no_next_cursor_is_emitted"
        ),
        "status": "partial_nonconclusive_LINE_EXCEEDS_BYTE_BUDGET",
    },
    "stop_reasons": list(STOP_REASONS),
    "observable_metadata_fields": list(PHYSICAL_METADATA_FIELDS),
}

PHYSICAL_CONTRACT_CANONICAL_JSON = json.dumps(
    _PHYSICAL_CONTRACT_DOCUMENT,
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
)
PHYSICAL_CONTRACT_HASH = hashlib.sha256(
    PHYSICAL_CONTRACT_CANONICAL_JSON.encode("utf-8")
).hexdigest()


def physical_contract_document() -> dict[str, Any]:
    """Return a detached JSON-compatible copy of the hash authority."""

    return json.loads(PHYSICAL_CONTRACT_CANONICAL_JSON)


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from _walk_mappings(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _walk_mappings(child)


def parse_timestamp(value: Any) -> tuple[Optional[float], Optional[str]]:
    """Normalize a timestamp exactly as the legacy coverage reader does.

    A non-empty but unparseable value deliberately returns its stripped text as
    the normalized value.  Consequently it participates lexically in the
    legacy coverage range; changing that surprising behavior would be a public
    physical-contract change rather than a cleanup.
    """

    if value in (None, ""):
        return None, None
    if isinstance(value, (int, float)):
        epoch = float(value)
        if epoch > 10_000_000_000:
            epoch /= 1000.0
        return epoch, datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    text = str(value).strip()
    try:
        numeric = float(text)
        return parse_timestamp(numeric)
    except ValueError:
        pass
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
        except ValueError:
            continue
    return None, text


def first_timestamp(
    record: Mapping[str, Any],
    preferred: Optional[str] = None,
    *,
    timestamp_keys: Iterable[str] = TIMESTAMP_KEYS,
) -> tuple[Optional[float], Optional[str]]:
    """Return the first timestamp encountered by the legacy depth-first walk."""

    keys = ((preferred,) if preferred else ()) + tuple(timestamp_keys)
    for item in _walk_mappings(record):
        for key in keys:
            if key and item.get(key) not in (None, ""):
                return parse_timestamp(item[key])
    return None, None


def update_timestamp_range(
    time_range: MutableMapping[str, Optional[str]],
    record: Mapping[str, Any],
) -> None:
    """Apply one mapping record to a legacy-shaped timestamp range in place."""

    _epoch, normalized = first_timestamp(record)
    if not normalized:
        return
    oldest = time_range.get("oldest")
    newest = time_range.get("newest")
    if oldest is None or normalized < oldest:
        time_range["oldest"] = normalized
    if newest is None or normalized > newest:
        time_range["newest"] = normalized


def timestamp_range(records: Iterable[Mapping[str, Any]]) -> dict[str, Optional[str]]:
    """Calculate the exact legacy lexical min/max for mapping records."""

    result: dict[str, Optional[str]] = {"oldest": None, "newest": None}
    for record in records:
        update_timestamp_range(result, record)
    return result


@dataclass(frozen=True)
class LineClassification:
    """Pure classification of one complete physical-line document.

    ``raw_document`` excludes the LF delimiter but deliberately retains a CR
    that preceded it.  ``value`` is populated for any valid JSON value,
    including scalars and lists; use ``valid_json`` to distinguish JSON ``null``
    from an invalid line.  ``nonblank`` means a materialized, examined
    nonblank document; it is false for an unmaterialized oversized barrier,
    whose whitespace content is intentionally unknown and never parsed.
    """

    blank: bool
    nonblank: bool
    valid_json: bool
    invalid_json: bool
    invalid_utf8: bool
    mapping: bool
    nonmapping_json: bool
    oversized_barrier: bool
    records_examined: int
    valid_lines: int
    invalid_lines: int
    value: Any = None
    event_epoch: Optional[float] = None
    event_timestamp: Optional[str] = None

    def summary_counts(self) -> dict[str, int]:
        """Return additive counters used by V2 segment/page summaries."""

        return {
            "physical_lines": 1,
            "blank_lines": int(self.blank),
            "valid_json_lines": int(self.valid_json),
            "invalid_json_lines": int(self.invalid_json),
            "invalid_utf8_lines": int(self.invalid_utf8),
            "mapping_records": int(self.mapping),
            "nonmapping_json_lines": int(self.nonmapping_json),
            "oversized_barrier_lines": int(self.oversized_barrier),
            "records_examined": int(self.records_examined),
            "valid_lines": int(self.valid_lines),
            "invalid_lines": int(self.invalid_lines),
        }


def classify_physical_line(
    raw_line: Optional[bytes],
    *,
    newline_terminated: bool = False,
    oversized: bool = False,
) -> LineClassification:
    """Classify one physical line without changing legacy semantics.

    Args:
        raw_line: The exact line bytes.  With ``newline_terminated=False`` these
            are the bytes passed to the legacy JSON decoder (LF excluded, CR
            retained).  With ``newline_terminated=True`` exactly one trailing
            LF is removed before classification.
        newline_terminated: Whether ``raw_line`` includes its terminating LF.
        oversized: Marks a line whose full document was intentionally not
            materialized.  Such a barrier is never parsed as a fragment.
    """

    if oversized:
        return LineClassification(
            blank=False,
            nonblank=False,
            valid_json=False,
            invalid_json=False,
            invalid_utf8=False,
            mapping=False,
            nonmapping_json=False,
            oversized_barrier=True,
            records_examined=0,
            valid_lines=0,
            invalid_lines=0,
        )
    if raw_line is None:
        raise ValueError("raw_line is required unless oversized is true")
    if not isinstance(raw_line, bytes):
        raise TypeError("raw_line must be bytes")
    raw_document = raw_line
    if newline_terminated:
        if not raw_document.endswith(b"\n"):
            raise ValueError("newline-terminated physical line must end with LF")
        raw_document = raw_document[:-1]
    if b"\n" in raw_document:
        raise ValueError("raw_line contains more than one physical line")
    if not raw_document.strip():
        return LineClassification(
            blank=True,
            nonblank=False,
            valid_json=False,
            invalid_json=False,
            invalid_utf8=False,
            mapping=False,
            nonmapping_json=False,
            oversized_barrier=False,
            records_examined=0,
            valid_lines=0,
            invalid_lines=0,
        )
    try:
        decoded = raw_document.decode("utf-8")
    except UnicodeDecodeError:
        return LineClassification(
            blank=False,
            nonblank=True,
            valid_json=False,
            invalid_json=False,
            invalid_utf8=True,
            mapping=False,
            nonmapping_json=False,
            oversized_barrier=False,
            records_examined=1,
            valid_lines=0,
            invalid_lines=1,
        )
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError:
        return LineClassification(
            blank=False,
            nonblank=True,
            valid_json=False,
            invalid_json=True,
            invalid_utf8=False,
            mapping=False,
            nonmapping_json=False,
            oversized_barrier=False,
            records_examined=1,
            valid_lines=0,
            invalid_lines=1,
        )
    is_mapping = isinstance(value, Mapping)
    event_epoch: Optional[float] = None
    event_timestamp: Optional[str] = None
    if is_mapping:
        event_epoch, event_timestamp = first_timestamp(value)
    return LineClassification(
        blank=False,
        nonblank=True,
        valid_json=True,
        invalid_json=False,
        invalid_utf8=False,
        mapping=is_mapping,
        nonmapping_json=not is_mapping,
        oversized_barrier=False,
        records_examined=1,
        valid_lines=1,
        invalid_lines=0,
        value=value,
        event_epoch=event_epoch,
        event_timestamp=event_timestamp,
    )


def path_fingerprint(path: Path | str | os.PathLike[str]) -> str:
    """Return the platform-normalized source fingerprint used by cursor V1."""

    normalized = os.path.normcase(os.path.abspath(os.fspath(path)))
    return hashlib.sha256(
        normalized.encode("utf-8", errors="surrogatepass")
    ).hexdigest()


def encode_scan_cursor(
    path: Path | str | os.PathLike[str],
    file_stat: os.stat_result,
    snapshot_eof: int,
    next_end: int,
    *,
    oversized_line: bool = False,
    coverage_tainted: bool = False,
    cursor_version: int = CURSOR_CONTRACT_VERSION,
) -> str:
    """Encode a cursor byte-for-byte compatibly with the legacy reader."""

    payload = {
        "v": int(cursor_version),
        "path": path_fingerprint(path),
        "dev": int(file_stat.st_dev),
        "ino": int(file_stat.st_ino),
        "snapshot_eof": int(snapshot_eof),
        "next_end": int(next_end),
        "oversized": bool(oversized_line),
        "tainted": bool(coverage_tainted or oversized_line),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_scan_cursor(
    token: str,
    *,
    cursor_version: int = CURSOR_CONTRACT_VERSION,
) -> dict[str, Any]:
    """Decode and structurally validate a legacy cursor V1 token."""

    if not isinstance(token, str) or not token or len(token) > CURSOR_MAX_CHARS:
        raise ValueError("invalid scan cursor")
    try:
        padded = token + "=" * (-len(token) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError, base64.binascii.Error) as exc:
        raise ValueError("invalid scan cursor") from exc
    required = {"v", "path", "dev", "ino", "snapshot_eof", "next_end"}
    if (
        not isinstance(value, Mapping)
        or not required.issubset(value)
        or value.get("v") != int(cursor_version)
    ):
        raise ValueError("invalid scan cursor")
    try:
        decoded = {
            "v": int(value["v"]),
            "path": str(value["path"]),
            "dev": int(value["dev"]),
            "ino": int(value["ino"]),
            "snapshot_eof": int(value["snapshot_eof"]),
            "next_end": int(value["next_end"]),
            "oversized": bool(value.get("oversized", False)),
            "tainted": bool(value.get("tainted", False)),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid scan cursor") from exc
    if decoded["snapshot_eof"] < 0 or not (
        0 <= decoded["next_end"] <= decoded["snapshot_eof"]
    ):
        raise ValueError("invalid scan cursor")
    return decoded


def cursor_targets_path(
    decoded: Optional[Mapping[str, Any]],
    path: Path | str | os.PathLike[str],
) -> bool:
    """Return whether a decoded cursor names ``path`` under cursor V1 rules."""

    return bool(decoded and decoded.get("path") == path_fingerprint(path))


__all__ = [
    "BLOCK_BYTES",
    "BYTE_BUDGET",
    "CURSOR_CONTRACT_VERSION",
    "CURSOR_MAX_CHARS",
    "DIRECTION",
    "JSONL_BLOCK_BYTES",
    "JSONL_CURSOR_VERSION",
    "JSONL_MAX_BYTES",
    "JSONL_MAX_VALID_LINES",
    "LineClassification",
    "PHYSICAL_CONTRACT_CANONICAL_JSON",
    "PHYSICAL_CONTRACT_HASH",
    "PHYSICAL_CONTRACT_VERSION",
    "PHYSICAL_METADATA_FIELDS",
    "RECORD_BUDGET",
    "STOP_REASONS",
    "SUMMARY_CONTRACT_VERSION",
    "TIMESTAMP_KEYS",
    "classify_physical_line",
    "cursor_targets_path",
    "decode_scan_cursor",
    "encode_scan_cursor",
    "first_timestamp",
    "parse_timestamp",
    "path_fingerprint",
    "physical_contract_document",
    "timestamp_range",
    "update_timestamp_range",
]
