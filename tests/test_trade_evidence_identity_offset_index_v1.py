from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

import trade_evidence_identity_contract as identity_contract
import trade_evidence_identity_offset_index_v1 as offset_index
import trade_timeline_validator as timeline_validator


def _blocked_network(*_args, **_kwargs):
    raise AssertionError("network access is forbidden in shadow-index tests")


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", _blocked_network)
    monkeypatch.setattr(socket, "create_connection", _blocked_network)


def _config(
    *,
    block_bytes: int = 7,
    segment_target_bytes: int = 256,
    batch_bytes: int = 512,
    batch_lines: int = 3,
    max_line_bytes: int = 4 * 1024,
    anchor_bytes: int = 32,
) -> offset_index.BuildConfig:
    return offset_index.BuildConfig(
        block_bytes=block_bytes,
        segment_target_bytes=segment_target_bytes,
        batch_bytes=batch_bytes,
        batch_lines=batch_lines,
        max_line_bytes=max_line_bytes,
        anchor_bytes=anchor_bytes,
        busy_timeout_ms=50,
    )


def _json_bytes(record, terminator: bytes = b"\n") -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + terminator
    )


def _build(
    tmp_path: Path,
    payload: bytes,
    *,
    name: str = "timeline",
    source_id: str = "timeline",
    config: offset_index.BuildConfig | None = None,
):
    source = tmp_path / f"{name}.jsonl"
    index = tmp_path / f"{name}.jsonl.identity-offset-v1.sqlite3"
    source.write_bytes(payload)
    original = source.read_bytes()
    report = offset_index.build_index(
        source,
        index,
        source_id,
        config=config or _config(),
        measure_memory=False,
    )
    assert source.read_bytes() == original
    return source, index, report


def _query_one(index: Path, sql: str, parameters=()):
    with sqlite3.connect(index) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(sql, parameters).fetchone()


def test_identity_contract_is_a_deterministic_freeze_of_validator_taxonomy():
    assert identity_contract.IDENTITY_KEYS == frozenset(timeline_validator.IDENTITY_KEYS)
    assert identity_contract.IDENTITY_KEY_ALIASES == timeline_validator.IDENTITY_KEY_ALIASES
    assert identity_contract.IDENTITY_GROUPS == timeline_validator.IDENTITY_GROUPS
    assert identity_contract.STRONG_IDENTITY_GROUPS == frozenset(
        timeline_validator.STRONG_IDENTITY_GROUPS
    )
    assert identity_contract.SECONDARY_IDENTITY_GROUPS == frozenset(
        timeline_validator.SECONDARY_IDENTITY_GROUPS
    )

    manifest = identity_contract.identity_contract_manifest()
    first = identity_contract.identity_contract_hash()
    second = identity_contract.identity_contract_hash()
    assert first == second == identity_contract.IDENTITY_CONTRACT_HASH
    assert len(first) == 64
    assert int(first, 16) >= 0
    assert manifest["excluded_event_identity_fields"] == ["event_id", "uid"]
    assert {"symbol", "side", "bot", "setup", "timestamp"}.issubset(
        manifest["unsafe_identity_fields"]
    )


def test_recursive_extractor_preserves_types_aliases_and_identity_classes():
    record = {
        "trade_id": " TRADE-1 ",
        "trade_uuid": "SAME-TEXT",
        "registry_record_id": "SAME-TEXT",
        "uid": "EVENT-UID-NOT-TRADE-IDENTITY",
        "event_id": "EVENT-ID-NOT-TRADE-IDENTITY",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "raw": {
            "details": [
                {
                    "trade_lifecycle_id": "LIFE-1",
                    "clientorderid": "CLIENT-1",
                    "execution_id": "EXEC-1",
                },
                {
                    "broker_stop_client_order_id": "FDS1-OPAQUE-1",
                    "client_order_id": "CLIENT-1-DS",
                    "fill_ids": ["FILL-1", "FILL-2"],
                },
            ],
            "decision_id": "DECISION-1",
            "signal_id": "SIGNAL-1",
        },
    }

    pairs = identity_contract.extract_identity_pairs(record)
    assert pairs == timeline_validator._identity_pairs(record)
    assert pairs["registry_id"] == {"SAME-TEXT"}
    assert pairs["lifecycle_id"] == {"LIFE-1"}
    assert pairs["client_order_id"] == {
        "CLIENT-1",
        "CLIENT-1-DS",
        "FDS1-OPAQUE-1",
    }

    typed = {
        (item.identity_type, item.identity_value): (
            item.identity_group,
            item.identity_class,
        )
        for item in identity_contract.extract_typed_identities(record)
    }
    assert typed[("trade_id", "TRADE-1")] == ("trade", "SECONDARY")
    assert typed[("execution_id", "EXEC-1")] == ("execution", "SECONDARY")
    assert typed[("decision_id", "DECISION-1")] == ("decision", "SECONDARY")
    assert typed[("signal_id", "SIGNAL-1")] == ("signal", "SECONDARY")
    assert typed[("trade_uuid", "SAME-TEXT")] == ("trade_uuid", "STRONG")
    assert typed[("registry_id", "SAME-TEXT")] == ("registry", "STRONG")
    assert typed[("lifecycle_id", "LIFE-1")] == ("lifecycle", "STRONG")
    assert typed[("client_order_id", "CLIENT-1")] == ("client_order", "STRONG")
    assert typed[("client_order_id", "FDS1-OPAQUE-1")] == (
        "client_order",
        "STRONG",
    )
    assert typed[("fill_ids", "FILL-1")] == ("fill", "STRONG")
    assert typed[("fill_ids", "FILL-2")] == ("fill", "STRONG")
    assert ("client_order_id", "CLIENT-1-DS") not in typed
    assert not any(item[0] in {"uid", "event_id", "symbol", "side"} for item in typed)


def test_binary_offsets_lengths_hashes_and_lookup_order_cover_lf_crlf_and_utf8(tmp_path):
    rows = [
        {
            "trade_id": "SHARED-TRADE",
            "registry_record_id": "REG-1",
            "event_type": "POSITION_OPEN",
            "timestamp": "2026-08-14T12:00:00Z",
        },
        {
            "trade_id": "SHARED-TRADE",
            "lifecycle_id": "LIFE-1",
            "event_type": "POSITION_OPEN",
            "note": "ação-漢字",
            "occurred_at": "2026-08-14T12:01:00+00:00",
        },
        {
            "trade_id": "SHARED-TRADE",
            "broker_order_id": "ORDER-1",
            "event": "LIVE_TRADE_CLOSED",
            "event_ts": "2026-08-14T12:02:00Z",
        },
    ]
    physical_lines = (
        _json_bytes(rows[0], b"\n"),
        _json_bytes(rows[1], b"\r\n"),
        _json_bytes(rows[2], b"\n"),
    )
    payload = b"".join(physical_lines)
    source, index, report = _build(
        tmp_path,
        payload,
        config=_config(block_bytes=1, segment_target_bytes=512, batch_bytes=1024),
    )

    assert report.published is True
    assert report.safe_watermark == report.source_bytes == len(payload)
    assert report.mapping_records == 3
    offsets = (0, len(physical_lines[0]), len(physical_lines[0]) + len(physical_lines[1]))

    records = offset_index.lookup_records(
        index,
        "trade_id",
        "SHARED-TRADE",
        0,
        len(payload),
    )
    assert tuple(item.start_offset for item in records) == offsets
    assert tuple(item.byte_length for item in records) == tuple(map(len, physical_lines))
    assert tuple(item.terminator_length for item in records) == (1, 2, 1)
    assert tuple(item.line_number for item in records) == (1, 2, 3)
    assert tuple(item.event_timestamp for item in records) == (
        "2026-08-14T12:00:00+00:00",
        "2026-08-14T12:01:00+00:00",
        "2026-08-14T12:02:00+00:00",
    )
    assert all(item.event_epoch is not None for item in records)
    assert tuple(item.record_hash for item in records) == tuple(
        hashlib.blake2b(line, digest_size=16).digest() for line in physical_lines
    )
    assert all(item.identity_class == "SECONDARY" for item in records)
    assert offset_index.lookup_offsets(
        index,
        "trade_id",
        "SHARED-TRADE",
        offsets[1],
        len(payload),
    ) == offsets[1:]
    assert offset_index.lookup_offsets(
        index,
        "registry_record_id",
        "REG-1",
        0,
        len(payload),
    ) == (0,)

    with source.open("rb") as handle:
        factual = tuple(offset_index.read_and_verify_record(handle, item) for item in records)
    assert factual == tuple(rows)
    segment = _query_one(
        index,
        "SELECT oldest_timestamp, newest_timestamp FROM segments",
    )
    assert dict(segment) == {
        "oldest_timestamp": "2026-08-14T12:00:00+00:00",
        "newest_timestamp": "2026-08-14T12:02:00+00:00",
    }


def test_complete_line_classification_tracks_blank_mapping_nonmapping_and_corruption(tmp_path):
    mapping = {
        "trade_id": "CLASSIFY-1",
        "trade_uuid": "UUID-CLASSIFY-1",
        "event_type": "POSITION_OPEN",
    }
    payload = b"".join(
        (
            b"\n",
            b" \t\r\n",
            _json_bytes(mapping),
            b"42\n",
            b"[1,2,3]\r\n",
            b'{"broken":\n',
            b'\xff\n',
        )
    )
    _source, index, report = _build(tmp_path, payload, name="classifications")

    assert report.published is True
    assert report.safe_watermark == len(payload)
    assert report.total_physical_lines == 7
    assert report.blank_lines == 2
    assert report.valid_json == 3
    assert report.invalid_json == 1
    assert report.mapping_records == 1
    assert report.nonmapping_json == 2
    assert report.postings == 2
    assert report.strong_postings == 1
    assert report.secondary_postings == 1

    totals = _query_one(
        index,
        """
        SELECT SUM(invalid_utf8_lines) AS invalid_utf8,
               SUM(invalid_json_lines) AS invalid_json,
               SUM(blank_lines) AS blank_lines,
               SUM(nonmapping_json_lines) AS nonmapping
        FROM segments
        """,
    )
    assert dict(totals) == {
        "invalid_utf8": 1,
        "invalid_json": 1,
        "blank_lines": 2,
        "nonmapping": 2,
    }
    assert offset_index.lookup_offsets(
        index,
        "trade_uuid",
        "UUID-CLASSIFY-1",
        0,
        len(payload),
    )


@pytest.mark.parametrize(
    "identity_type,identity_value",
    [
        ("uid", "UID-1"),
        ("event_id", "EVENT-1"),
        ("symbol", "BTCUSDT"),
        ("bot_name", "FALCON"),
        ("epoch", "123"),
        ("unknown_identity", "VALUE"),
        ("client_order_id", "ENTRY-1-DS"),
    ],
)
def test_lookup_rejects_unsafe_unknown_and_legacy_derived_identity_types(
    tmp_path,
    identity_type,
    identity_value,
):
    payload = _json_bytes(
        {
            "trade_id": "LOOKUP-1",
            "client_order_id": "CLIENT-1",
            "event_type": "POSITION_OPEN",
        }
    )
    _source, index, _report = _build(
        tmp_path,
        payload,
        name=f"lookup-{identity_type}",
    )

    with pytest.raises(ValueError, match="not indexable"):
        offset_index.lookup_offsets(index, identity_type, identity_value, 0, len(payload))


def test_read_and_verify_record_rejects_wrong_offset_hash_event_and_identity(tmp_path):
    row = {
        "trade_id": "VERIFY-1",
        "trade_uuid": "UUID-VERIFY-1",
        "event_type": "POSITION_OPEN",
    }
    payload = _json_bytes(row, b"\r\n")
    source, index, _report = _build(tmp_path, payload, name="verify")
    metadata = offset_index.lookup_records(
        index,
        "trade_uuid",
        "UUID-VERIFY-1",
        0,
        len(payload),
    )[0]

    with source.open("rb") as handle:
        assert offset_index.read_and_verify_record(handle, metadata) == row
        with pytest.raises(offset_index.IndexValidationError, match="boundary"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, start_offset=metadata.start_offset + 1),
            )
        with pytest.raises(offset_index.IndexValidationError, match="hash"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, record_hash=b"\x00" * 16),
            )
        with pytest.raises(offset_index.IndexValidationError, match="event type"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, event_type="SOMETHING_ELSE"),
            )
        with pytest.raises(offset_index.IndexValidationError, match="writer version"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, writer_version="FOREIGN-WRITER"),
            )
        with pytest.raises(offset_index.IndexValidationError, match="identity"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, identity_value="UUID-FOREIGN"),
            )
        with pytest.raises(offset_index.IndexValidationError, match="taxonomy"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, identity_group="registry"),
            )
        with pytest.raises(offset_index.IndexValidationError, match="taxonomy"):
            offset_index.read_and_verify_record(
                handle,
                replace(metadata, identity_class="SECONDARY"),
            )


@pytest.mark.parametrize(
    "tail,expected_kind,expected_valid,expected_invalid,expected_mappings",
    [
        (
            _json_bytes(
                {"trade_id": "TAIL-VALID", "event_type": "POSITION_OPEN"},
                b"",
            ),
            "VALID_MAPPING",
            2,
            0,
            2,
        ),
        (b'{"broken":', "INVALID_JSON", 1, 1, 1),
        (b'{"note":"\xc3', "INVALID_UTF8", 1, 0, 1),
    ],
)
def test_terminal_fragment_never_advances_watermark_or_creates_postings(
    tmp_path,
    tail,
    expected_kind,
    expected_valid,
    expected_invalid,
    expected_mappings,
):
    complete = _json_bytes(
        {"trade_id": "COMPLETE-1", "event_type": "POSITION_OPEN"}
    )
    payload = complete + tail
    source, index, report = _build(
        tmp_path,
        payload,
        name=f"tail-{expected_kind.lower()}",
    )

    assert report.published is False
    assert index.exists() is False
    assert report.staging_path is not None
    staging = Path(report.staging_path)
    assert staging.exists()
    assert report.safe_watermark == len(complete)
    assert report.trailing_fragment_bytes == len(tail)
    assert report.total_physical_lines == 2
    assert report.valid_json == expected_valid
    assert report.invalid_json == expected_invalid
    assert report.mapping_records == expected_mappings
    assert report.postings == 1

    state = _query_one(
        staging,
        "SELECT safe_watermark, trailing_fragment_kind FROM source_state",
    )
    assert int(state["safe_watermark"]) == len(complete)
    assert state["trailing_fragment_kind"] == expected_kind
    assert offset_index.lookup_offsets(
        staging,
        "trade_id",
        "COMPLETE-1",
        0,
        len(payload),
    ) == (0,)
    assert offset_index.lookup_offsets(
        staging,
        "trade_id",
        "TAIL-VALID",
        0,
        len(payload),
    ) == ()
    validation = offset_index.validate_index(source, staging, "timeline", deep=True)
    assert validation.status == offset_index.INDEX_PARTIAL


def test_long_line_is_indexed_but_oversized_line_is_a_bounded_barrier(tmp_path):
    config = _config(
        block_bytes=16,
        segment_target_bytes=4 * 1024,
        batch_bytes=8 * 1024,
        batch_lines=10,
        max_line_bytes=128,
        anchor_bytes=16,
    )
    long_line = _json_bytes(
        {
            "trade_id": "LONG-INDEXED",
            "event_type": "POSITION_OPEN",
            "padding": "x" * 20,
        }
    )
    oversized_line = _json_bytes(
        {
            "trade_id": "OVERSIZED-NOT-INDEXED",
            "event_type": "POSITION_OPEN",
            "padding": "y" * 256,
        }
    )
    final_line = _json_bytes(
        {"trade_id": "AFTER-BARRIER", "event_type": "TRAILING_UPDATED"}
    )
    assert config.block_bytes < len(long_line) <= config.max_line_bytes
    assert len(oversized_line) > config.max_line_bytes
    payload = long_line + oversized_line + final_line
    _source, index, report = _build(
        tmp_path,
        payload,
        name="oversized",
        config=config,
    )

    assert report.published is True
    assert report.safe_watermark == len(payload)
    assert report.total_physical_lines == 3
    assert report.mapping_records == 2
    assert report.oversized_barriers == 1
    assert report.peak_pending_line_bytes == config.max_line_bytes
    assert offset_index.lookup_offsets(
        index,
        "trade_id",
        "LONG-INDEXED",
        0,
        len(payload),
    ) == (0,)
    assert offset_index.lookup_offsets(
        index,
        "trade_id",
        "OVERSIZED-NOT-INDEXED",
        0,
        len(payload),
    ) == ()
    assert offset_index.lookup_offsets(
        index,
        "trade_id",
        "AFTER-BARRIER",
        0,
        len(payload),
    ) == (len(long_line) + len(oversized_line),)

    segment = _query_one(
        index,
        """
        SELECT has_long_line, has_oversized_barrier, oversized_barrier_lines,
               max_line_bytes
        FROM segments
        """,
    )
    assert int(segment["has_long_line"]) == 1
    assert int(segment["has_oversized_barrier"]) == 1
    assert int(segment["oversized_barrier_lines"]) == 1
    assert int(segment["max_line_bytes"]) == len(oversized_line)


def test_revalidator_classifies_missing_complete_and_append_lag_as_partial(tmp_path):
    source = tmp_path / "revalidate.jsonl"
    index = tmp_path / "revalidate.sqlite3"
    source.write_bytes(_json_bytes({"trade_id": "R-1", "event_type": "POSITION_OPEN"}))

    missing = offset_index.validate_index(source, index, "timeline")
    assert missing.status == offset_index.INDEX_MISSING

    report = offset_index.build_index(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    assert report.published is True
    complete = offset_index.validate_index(source, index, "timeline", deep=False)
    deep_complete = offset_index.validate_index(source, index, "timeline", deep=True)
    assert complete.status == offset_index.INDEX_COMPLETE_FOR_SNAPSHOT
    assert deep_complete.status == offset_index.INDEX_COMPLETE_FOR_SNAPSHOT

    indexed_snapshot = report.safe_watermark
    with source.open("ab") as handle:
        handle.write(_json_bytes({"trade_id": "R-2", "event_type": "POSITION_OPEN"}))
    partial = offset_index.validate_index(source, index, "timeline")
    historical_snapshot = offset_index.validate_index(
        source,
        index,
        "timeline",
        snapshot_eof=indexed_snapshot,
    )
    assert partial.status == offset_index.INDEX_PARTIAL
    assert partial.reasons == ("WATERMARK_BEHIND_SNAPSHOT",)
    assert historical_snapshot.status == offset_index.INDEX_COMPLETE_FOR_SNAPSHOT


def test_revalidator_classifies_stale_source_changed_and_corrupt(tmp_path):
    payload = _json_bytes({"trade_id": "STATE-1", "event_type": "POSITION_OPEN"})

    stale_source, stale_index, _ = _build(tmp_path, payload, name="stale")
    with sqlite3.connect(stale_index) as connection:
        connection.execute(
            "UPDATE source_state SET identity_contract_hash='obsolete-contract'"
        )
        connection.commit()
    stale = offset_index.validate_index(stale_source, stale_index, "timeline")
    assert stale.status == offset_index.INDEX_STALE
    assert stale.reasons == ("IDENTITY_CONTRACT_MISMATCH",)

    changed_source, changed_index, _ = _build(tmp_path, payload, name="changed")
    with changed_source.open("r+b") as handle:
        first = handle.read(1)
        handle.seek(0)
        handle.write(b"[" if first != b"[" else b"{")
    changed = offset_index.validate_index(changed_source, changed_index, "timeline")
    assert changed.status == offset_index.INDEX_SOURCE_CHANGED
    assert "PREFIX_ANCHOR_MISMATCH" in changed.reasons

    corrupt_source = tmp_path / "corrupt-source.jsonl"
    corrupt_index = tmp_path / "corrupt-index.sqlite3"
    corrupt_source.write_bytes(payload)
    corrupt_index.write_bytes(b"not a sqlite database")
    corrupt = offset_index.validate_index(corrupt_source, corrupt_index, "timeline")
    assert corrupt.status == offset_index.INDEX_CORRUPT


def test_revalidator_detects_source_shrink_before_anchor_validation(tmp_path):
    payload = b"".join(
        _json_bytes(
            {
                "trade_id": f"SHRINK-{index}",
                "event_type": "POSITION_OPEN",
                "padding": "x" * 40,
            }
        )
        for index in range(4)
    )
    source, index, report = _build(tmp_path, payload, name="source-shrink")
    assert report.safe_watermark == len(payload)

    with source.open("r+b") as handle:
        handle.truncate(len(payload) - 1)

    result = offset_index.validate_index(source, index, "timeline")

    assert result.status == offset_index.INDEX_SOURCE_CHANGED
    assert result.reasons == ("SOURCE_SHRINK",)


def test_revalidator_detects_atomic_source_replacement_by_file_identity(tmp_path):
    payload = _json_bytes(
        {"trade_id": "REPLACED-1", "event_type": "POSITION_OPEN"}
    )
    source, index, _ = _build(tmp_path, payload, name="source-replacement")
    before = source.stat()
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(payload)

    os.replace(replacement, source)

    after = source.stat()
    if (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino):
        pytest.skip("filesystem does not expose a new file identity after replacement")
    result = offset_index.validate_index(source, index, "timeline")
    assert result.status == offset_index.INDEX_SOURCE_CHANGED
    assert result.reasons == ("SOURCE_FILE_ID_MISMATCH",)


def test_revalidator_distinguishes_watermark_anchor_from_prefix_mismatch(tmp_path):
    payload = b"".join(
        _json_bytes(
            {
                "trade_id": f"ANCHOR-{index}",
                "event_type": "TRAILING_UPDATED",
                "padding": "z" * 48,
            }
        )
        for index in range(5)
    )
    source, index, report = _build(
        tmp_path,
        payload,
        name="watermark-anchor",
        config=_config(anchor_bytes=32),
    )
    assert report.safe_watermark > 2 * 32

    mutation_offset = len(payload) - 2
    assert mutation_offset > 32
    with source.open("r+b") as handle:
        handle.seek(mutation_offset)
        original = handle.read(1)
        assert original != b"\n"
        handle.seek(mutation_offset)
        handle.write(b"]" if original != b"]" else b"}")

    result = offset_index.validate_index(source, index, "timeline")

    assert result.status == offset_index.INDEX_SOURCE_CHANGED
    assert result.reasons == ("WATERMARK_ANCHOR_MISMATCH",)
    assert "PREFIX_ANCHOR_MISMATCH" not in result.reasons


def test_zero_watermark_staging_keeps_initial_prefix_anchor_for_validate_and_resume(
    tmp_path,
):
    source = tmp_path / "zero-watermark-prefix.jsonl"
    index = tmp_path / "zero-watermark-prefix.sqlite3"
    payload = _json_bytes(
        {
            "trade_id": "PREFIX-W0-1",
            "event_type": "POSITION_OPEN",
            "padding": "x" * 64,
        }
    )
    source.write_bytes(payload)

    def crash_before_batch_sql_commit(point, _context):
        if point == "before_batch_sql_commit":
            raise RuntimeError("simulated crash before batch SQL commit")

    with pytest.raises(RuntimeError, match="simulated crash"):
        offset_index.build_index(
            source,
            index,
            "timeline",
            config=_config(batch_lines=1),
            fault_injector=crash_before_batch_sql_commit,
            measure_memory=False,
        )

    assert index.exists() is False
    staging_candidates = offset_index.find_staging_indexes(index)
    assert len(staging_candidates) == 1
    staging = staging_candidates[0]
    state = _query_one(
        staging,
        """
        SELECT state, safe_watermark, prefix_anchor_length,
               watermark_anchor_length
        FROM source_state
        """,
    )
    assert state["state"] == "BUILDING"
    assert int(state["safe_watermark"]) == 0
    assert int(state["prefix_anchor_length"]) == min(32, len(payload))
    assert int(state["watermark_anchor_length"]) == 0
    counts = _query_one(
        staging,
        """
        SELECT (SELECT COUNT(*) FROM segments) AS segments,
               (SELECT COUNT(*) FROM records) AS records,
               (SELECT COUNT(*) FROM postings) AS postings
        """,
    )
    assert dict(counts) == {"segments": 0, "records": 0, "postings": 0}

    with source.open("r+b") as handle:
        original = handle.read(1)
        handle.seek(0)
        handle.write(b"[" if original != b"[" else b"{")

    validation = offset_index.validate_index(source, staging, "timeline")
    assert validation.status == offset_index.INDEX_SOURCE_CHANGED
    assert validation.reasons == ("PREFIX_ANCHOR_MISMATCH",)

    with pytest.raises(offset_index.IndexBuildError) as resume_error:
        offset_index.build_index(
            source,
            index,
            "timeline",
            resume=True,
            staging_path=staging,
            measure_memory=False,
        )
    assert "INDEX_SOURCE_CHANGED" in str(resume_error.value)
    assert "PREFIX_ANCHOR_MISMATCH" in str(resume_error.value)


@pytest.mark.parametrize(
    "mutation,expected_reason",
    [
        (
            "UPDATE source_state SET index_version='obsolete-index-version'",
            "INDEX_VERSION_MISMATCH",
        ),
        (
            "UPDATE source_state SET schema_version=schema_version + 1",
            "INDEX_VERSION_MISMATCH",
        ),
        ("PRAGMA user_version=999", "SQLITE_VERSION_MISMATCH"),
    ],
)
def test_revalidator_classifies_index_and_schema_version_mismatches_as_stale(
    tmp_path,
    mutation,
    expected_reason,
):
    payload = _json_bytes(
        {"trade_id": "VERSION-1", "event_type": "POSITION_OPEN"}
    )
    source, index, _ = _build(
        tmp_path,
        payload,
        name=f"version-{expected_reason.lower()}-{len(mutation)}",
    )
    with sqlite3.connect(index) as connection:
        connection.execute(mutation)
        connection.commit()

    result = offset_index.validate_index(source, index, "timeline")

    assert result.status == offset_index.INDEX_STALE
    assert result.reasons == (expected_reason,)


def test_revalidator_rejects_wrong_source_id_and_wrong_source_path(tmp_path):
    payload = _json_bytes(
        {"trade_id": "SOURCE-SCOPE-1", "event_type": "POSITION_OPEN"}
    )
    source, index, _ = _build(tmp_path, payload, name="source-scope")

    wrong_id = offset_index.validate_index(source, index, "history_manager")
    assert wrong_id.status == offset_index.INDEX_SOURCE_CHANGED
    assert wrong_id.reasons == ("SOURCE_ID_MISMATCH",)

    other_source = tmp_path / "same-bytes-different-path.jsonl"
    other_source.write_bytes(payload)
    wrong_path = offset_index.validate_index(other_source, index, "timeline")
    assert wrong_path.status == offset_index.INDEX_SOURCE_CHANGED
    assert wrong_path.reasons == ("SOURCE_PATH_MISMATCH",)


def test_sqlite_unique_constraints_reject_duplicate_offsets_lines_identities_and_postings(
    tmp_path,
):
    payload = _json_bytes(
        {
            "trade_id": "UNIQUE-1",
            "trade_uuid": "UUID-UNIQUE-1",
            "event_type": "POSITION_OPEN",
        }
    )
    _source, index, _ = _build(tmp_path, payload, name="unique-constraints")

    with sqlite3.connect(index) as connection:
        connection.row_factory = sqlite3.Row
        record = connection.execute("SELECT * FROM records").fetchone()
        identity = connection.execute("SELECT * FROM identities ORDER BY identity_id").fetchone()
        posting = connection.execute("SELECT * FROM postings ORDER BY identity_id").fetchone()

        def unique_column_sets(table: str) -> set[tuple[str, ...]]:
            result: set[tuple[str, ...]] = set()
            for index_row in connection.execute(f"PRAGMA index_list({table})"):
                if not int(index_row["unique"]):
                    continue
                columns = tuple(
                    str(column["name"])
                    for column in connection.execute(
                        f"PRAGMA index_info({index_row['name']})"
                    )
                )
                result.add(columns)
            return result

        assert {
            ("start_offset",),
            ("line_number",),
            ("record_id", "start_offset"),
        }.issubset(
            unique_column_sets("records")
        )
        assert ("identity_type", "identity_value") in unique_column_sets("identities")
        assert (
            "identity_id",
            "start_offset",
            "record_id",
        ) in unique_column_sets("postings")
        assert {("start_offset",), ("end_offset",)}.issubset(
            unique_column_sets("segments")
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO identities (
                    identity_type, identity_value, identity_group, identity_class
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    identity["identity_type"],
                    identity["identity_value"],
                    identity["identity_group"],
                    identity["identity_class"],
                ),
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO postings(identity_id, start_offset, record_id)
                VALUES (?, ?, ?)
                """,
                (
                    posting["identity_id"],
                    posting["start_offset"],
                    posting["record_id"],
                ),
            )
        connection.rollback()

        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO postings(identity_id, start_offset, record_id)
                VALUES (?, ?, ?)
                """,
                (
                    posting["identity_id"],
                    int(posting["start_offset"]) + 1,
                    posting["record_id"],
                ),
            )
        connection.rollback()

        duplicate_record_parameters = (
            record["segment_id"],
            int(record["line_number"]) + 100,
            record["start_offset"],
            record["byte_length"],
            record["terminator_length"],
            record["event_type"],
            record["event_epoch"],
            record["event_timestamp"],
            record["writer_version"],
            record["record_hash"],
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO records (
                    segment_id, line_number, start_offset, byte_length,
                    terminator_length, event_type, event_epoch, event_timestamp,
                    writer_version, record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                duplicate_record_parameters,
            )
        connection.rollback()


def test_deep_revalidator_detects_invalid_utf8_segment_counter_tamper(tmp_path):
    payload = b"\xff\n" + _json_bytes(
        {"trade_id": "AFTER-INVALID-UTF8", "event_type": "POSITION_OPEN"}
    )
    source, index, _ = _build(tmp_path, payload, name="utf8-counter")
    with sqlite3.connect(index) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute("UPDATE segments SET invalid_utf8_lines=0")
        connection.commit()

    result = offset_index.validate_index(source, index, "timeline", deep=True)

    assert result.status == offset_index.INDEX_CORRUPT
    assert "SEGMENT_CLASSIFICATION_COUNTS" in result.reasons
