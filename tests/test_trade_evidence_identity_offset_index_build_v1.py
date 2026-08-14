from __future__ import annotations

import json
import socket
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest

import trade_evidence_identity_offset_index_v1 as index_v1
from tools import build_trade_evidence_identity_offset_index_v1 as cli


class _SimulatedCrash(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("network access is forbidden in shadow index tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _line(record: Mapping[str, Any], *, newline: bytes = b"\n") -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + newline
    )


def _write_records(path: Path, records: list[Mapping[str, Any]]) -> tuple[int, ...]:
    offsets: list[int] = []
    offset = 0
    with path.open("wb") as handle:
        for record in records:
            encoded = _line(record)
            offsets.append(offset)
            handle.write(encoded)
            offset += len(encoded)
    return tuple(offsets)


def _small_config(*, batch_lines: int = 2) -> index_v1.BuildConfig:
    return index_v1.BuildConfig(
        block_bytes=64,
        segment_target_bytes=4 * 1024,
        batch_bytes=4 * 1024,
        batch_lines=batch_lines,
        max_line_bytes=8 * 1024,
        anchor_bytes=64,
        busy_timeout_ms=50,
    )


def _fault_once(target: str):
    raised = False

    def inject(point: str, _context: Mapping[str, Any]) -> None:
        nonlocal raised
        if point == target and not raised:
            raised = True
            raise _SimulatedCrash(target)

    return inject


def _state(path: Path) -> sqlite3.Row:
    assert path.is_file()
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM source_state WHERE singleton_id=1"
        ).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def _scalar(path: Path, sql: str) -> int:
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute(sql).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.close()


def test_bounded_batches_publish_one_contiguous_safe_watermark(tmp_path: Path) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    records = [
        {
            "event": f"EVENT_{number}",
            "trade_id": "TRADE-BATCH",
            "trade_uuid": f"UUID-{number}",
        }
        for number in range(7)
    ]
    _write_records(source, records)

    report = index_v1.build_index(
        source,
        index,
        "history_manager",
        config=_small_config(batch_lines=2),
    )

    assert report.published is True
    assert report.state == "READY"
    assert report.committed_batches == 4
    assert report.max_batch_lines <= 2
    assert report.safe_watermark == source.stat().st_size
    assert report.mapping_records == len(records)
    assert report.postings == len(records) * 2
    state = _state(index)
    assert state["state"] == "READY"
    assert int(state["safe_watermark"]) == source.stat().st_size
    assert _scalar(index, "SELECT COUNT(*) FROM records") == len(records)
    assert _scalar(index, "SELECT MAX(end_offset) FROM segments") == source.stat().st_size
    assert _scalar(
        index,
        """
        SELECT COUNT(*) FROM (
            SELECT start_offset,
                   LAG(end_offset) OVER (ORDER BY start_offset) AS previous_end
            FROM segments
        ) WHERE previous_end IS NOT NULL AND start_offset != previous_end
        """,
    ) == 0
    validation = index_v1.validate_index(
        source, index, "history_manager", deep=True
    )
    assert validation.status == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT


def test_crash_inside_first_batch_transaction_rolls_back_and_resumes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    _write_records(
        source,
        [
            {"event": f"E{number}", "trade_id": "TRADE-BEFORE"}
            for number in range(4)
        ],
    )

    with pytest.raises(_SimulatedCrash, match="before_batch_sql_commit"):
        index_v1.build_index(
            source,
            index,
            "history_manager",
            config=_small_config(),
            fault_injector=_fault_once("before_batch_sql_commit"),
        )

    staging = index_v1.find_staging_indexes(index)
    assert len(staging) == 1
    state = _state(staging[0])
    assert state["state"] == "BUILDING"
    assert int(state["safe_watermark"]) == 0
    assert _scalar(staging[0], "SELECT COUNT(*) FROM segments") == 0
    assert _scalar(staging[0], "SELECT COUNT(*) FROM records") == 0
    assert _scalar(staging[0], "SELECT COUNT(*) FROM postings") == 0

    resumed = index_v1.build_index(
        source,
        index,
        "history_manager",
        resume=True,
        staging_path=staging[0],
    )
    assert resumed.published is True
    assert not staging[0].exists()
    assert index_v1.lookup_offsets(
        index, "trade_id", "TRADE-BEFORE", 0, source.stat().st_size
    ) == tuple(
        row.start_offset
        for row in index_v1.lookup_records(
            index, "trade_id", "TRADE-BEFORE", 0, source.stat().st_size
        )
    )
    assert len(
        index_v1.lookup_offsets(
            index, "trade_id", "TRADE-BEFORE", 0, source.stat().st_size
        )
    ) == 4


def test_crash_after_committed_batch_resumes_from_watermark_and_indexes_append(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.jsonl.identity-offset-v1.sqlite3"
    original = [
        {"event": f"ORIGINAL_{number}", "trade_id": "TRADE-RESUME"}
        for number in range(4)
    ]
    expected_offsets = list(_write_records(source, original))

    with pytest.raises(_SimulatedCrash, match="after_batch_commit"):
        index_v1.build_index(
            source,
            index,
            "timeline",
            config=_small_config(),
            fault_injector=_fault_once("after_batch_commit"),
        )

    staging = index_v1.find_staging_indexes(index)
    assert len(staging) == 1
    checkpoint = int(_state(staging[0])["safe_watermark"])
    assert 0 < checkpoint < source.stat().st_size
    committed_records = _scalar(staging[0], "SELECT COUNT(*) FROM records")
    assert committed_records == 2

    with source.open("ab") as handle:
        for number in range(2):
            expected_offsets.append(handle.tell())
            handle.write(
                _line(
                    {
                        "event": f"APPENDED_{number}",
                        "trade_id": "TRADE-RESUME",
                    }
                )
            )

    resumed = index_v1.build_index(
        source,
        index,
        "timeline",
        resume=True,
        staging_path=staging[0],
    )
    assert resumed.published is True
    assert resumed.safe_watermark == source.stat().st_size
    assert index_v1.lookup_offsets(
        index, "trade_id", "TRADE-RESUME", 0, source.stat().st_size
    ) == tuple(expected_offsets)
    assert _scalar(index, "SELECT COUNT(*) FROM records") == len(expected_offsets)
    assert _scalar(index, "SELECT COUNT(*) FROM postings") == len(expected_offsets)
    assert _scalar(
        index,
        "SELECT COUNT(*) - COUNT(DISTINCT start_offset) FROM records",
    ) == 0
    assert _scalar(
        index,
        """
        SELECT COUNT(*) FROM (
            SELECT identity_id, record_id, COUNT(*) AS occurrences
            FROM postings GROUP BY identity_id, record_id
            HAVING occurrences != 1
        )
        """,
    ) == 0
    assert _scalar(
        index,
        """
        SELECT COUNT(*) FROM (
            SELECT start_offset, COUNT(*) AS occurrences
            FROM segments GROUP BY start_offset
            HAVING occurrences != 1
        )
        """,
    ) == 0
    assert index_v1.verify_shadow(
        source,
        index,
        [("trade_id", "TRADE-RESUME")],
    ).ok


def test_corrupt_staging_is_rejected_preserved_and_never_published(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    _write_records(source, [{"event": "OPEN", "trade_uuid": "CORRUPT-STAGING"}])
    generation = str(uuid.uuid4())
    staging = Path(f"{index}.building.{generation}")
    corrupt_bytes = b"not-a-sqlite-shadow-index\x00\x01\x02"
    staging.write_bytes(corrupt_bytes)

    validation = index_v1.validate_index(
        source, staging, "history_manager", deep=True
    )
    assert validation.status == index_v1.INDEX_CORRUPT
    with pytest.raises(index_v1.IndexBuildError, match="staging validation failed"):
        index_v1.build_index(
            source,
            index,
            "history_manager",
            resume=True,
            staging_path=staging,
        )

    assert not index.exists()
    assert staging.read_bytes() == corrupt_bytes
    assert index_v1.find_staging_indexes(index) == (staging,)


def test_restart_indexes_terminal_fragment_only_after_physical_newline(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.jsonl.identity-offset-v1.sqlite3"
    first = json.dumps(
        {"event": "OPEN", "trade_id": "FRAGMENT-TRADE"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    source.write_bytes(first)

    partial = index_v1.build_index(
        source,
        index,
        "timeline",
        config=_small_config(),
    )
    assert partial.published is False
    assert partial.state == "BUILDING"
    assert partial.safe_watermark == 0
    assert partial.trailing_fragment_bytes == len(first)
    assert partial.staging_path is not None
    staging = Path(partial.staging_path)
    state = _state(staging)
    assert state["trailing_fragment_kind"] == "VALID_MAPPING"
    assert _scalar(staging, "SELECT COUNT(*) FROM records") == 0
    assert _scalar(staging, "SELECT COUNT(*) FROM postings") == 0

    second_offset = len(first) + 1
    with source.open("ab") as handle:
        handle.write(b"\n")
        handle.write(_line({"event": "UPDATE", "trade_id": "FRAGMENT-TRADE"}))

    resumed = index_v1.build_index(
        source,
        index,
        "timeline",
        resume=True,
        staging_path=staging,
    )
    assert resumed.published is True
    assert resumed.state == "READY"
    assert resumed.safe_watermark == source.stat().st_size
    assert index_v1.lookup_offsets(
        index,
        "trade_id",
        "FRAGMENT-TRADE",
        0,
        source.stat().st_size,
    ) == (0, second_offset)
    assert _scalar(index, "SELECT COUNT(*) FROM records") == 2
    assert (
        index_v1.validate_index(source, index, "timeline", deep=True).status
        == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    )


def test_existing_final_sqlite_sidecar_blocks_replace_and_preserves_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    _write_records(source, [{"event": "OPEN", "trade_uuid": "SIDECAR-UUID"}])

    with pytest.raises(_SimulatedCrash, match="before_atomic_replace"):
        index_v1.build_index(
            source,
            index,
            "history_manager",
            config=_small_config(),
            fault_injector=_fault_once("before_atomic_replace"),
        )
    staging = index_v1.find_staging_indexes(index)
    assert len(staging) == 1
    generation = str(_state(staging[0])["generation_uuid"])
    final_wal = Path(f"{index}-wal")
    final_wal.write_bytes(b"unrelated-or-stale-wal-sentinel")

    with pytest.raises(index_v1.IndexBuildError, match="SQLite sidecar exists"):
        index_v1.build_index(
            source,
            index,
            "history_manager",
            resume=True,
            staging_path=staging[0],
        )

    assert not index.exists()
    assert final_wal.read_bytes() == b"unrelated-or-stale-wal-sentinel"
    assert staging[0].exists()
    assert str(_state(staging[0])["generation_uuid"]) == generation
    assert _state(staging[0])["state"] == "REVALIDATING"

    final_wal.unlink()
    resumed = index_v1.build_index(
        source,
        index,
        "history_manager",
        resume=True,
        staging_path=staging[0],
    )
    assert resumed.published is True
    assert resumed.state == "READY"
    assert not staging[0].exists()


def test_crash_before_atomic_replace_preserves_revalidating_staging(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    _write_records(source, [{"event": "OPEN", "trade_uuid": "PUB-BEFORE"}])

    with pytest.raises(_SimulatedCrash, match="before_atomic_replace"):
        index_v1.build_index(
            source,
            index,
            "history_manager",
            config=_small_config(),
            fault_injector=_fault_once("before_atomic_replace"),
        )

    assert not index.exists()
    staging = index_v1.find_staging_indexes(index)
    assert len(staging) == 1
    assert _state(staging[0])["state"] == "REVALIDATING"
    validation = index_v1.validate_index(
        source, staging[0], "history_manager", deep=True
    )
    assert validation.status == index_v1.INDEX_PARTIAL
    assert "STATE_REVALIDATING" in validation.reasons

    resumed = index_v1.build_index(
        source,
        index,
        "history_manager",
        resume=True,
        staging_path=staging[0],
    )
    assert resumed.published is True
    assert resumed.state == "READY"
    assert not staging[0].exists()
    assert _state(index)["state"] == "READY"
    assert (
        index_v1.validate_index(source, index, "history_manager", deep=True).status
        == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    )


def test_crash_after_atomic_replace_never_exposes_ready_without_postvalidation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.jsonl.identity-offset-v1.sqlite3"
    _write_records(source, [{"event": "OPEN", "trade_uuid": "PUB-AFTER"}])

    with pytest.raises(_SimulatedCrash, match="after_atomic_replace"):
        index_v1.build_index(
            source,
            index,
            "timeline",
            config=_small_config(),
            fault_injector=_fault_once("after_atomic_replace"),
        )

    assert index.is_file()
    assert index_v1.find_staging_indexes(index) == ()
    state = _state(index)
    assert state["state"] == "REVALIDATING"
    assert state["published_at"] is None
    assert state["validated_at"] is None
    validation = index_v1.validate_index(source, index, "timeline", deep=True)
    assert validation.status == index_v1.INDEX_PARTIAL
    assert "STATE_REVALIDATING" in validation.reasons

    resume_code = cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--resume",
        ]
    )
    resume_payload = json.loads(capsys.readouterr().out)
    assert resume_code == 0
    assert resume_payload["mode"] == "resume"
    assert resume_payload["published"] is True
    assert resume_payload["state"] == "READY"
    assert _state(index)["state"] == "READY"
    assert (
        index_v1.validate_index(source, index, "timeline", deep=True).status
        == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    )


def test_manual_cli_build_validate_and_shadow_report_use_only_explicit_tmp_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.jsonl.identity-offset-v1.sqlite3"
    build_report = tmp_path / "reports" / "build.json"
    verify_report = tmp_path / "reports" / "verify.json"
    _write_records(
        source,
        [
            {
                "event": "OPEN",
                "trade_id": "CLI-TRADE",
                "raw": {"trade_uuid": "CLI-UUID"},
            }
        ],
    )

    build_code = cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--build",
            "--block-bytes",
            "64",
            "--segment-target-bytes",
            "512",
            "--batch-bytes",
            "1024",
            "--batch-lines",
            "2",
            "--max-line-bytes",
            "4096",
            "--anchor-bytes",
            "64",
            "--report-json",
            str(build_report),
        ]
    )
    build_stdout = json.loads(capsys.readouterr().out)
    assert build_code == 0
    assert build_stdout["mode"] == "build"
    assert build_stdout["published"] is True
    assert Path(build_stdout["source_path"]) == source.resolve()
    assert json.loads(build_report.read_text(encoding="utf-8"))["state"] == "READY"

    validate_code = cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--deep-validate",
        ]
    )
    validate_stdout = json.loads(capsys.readouterr().out)
    assert validate_code == 0
    assert validate_stdout["status"] == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT

    verify_code = cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--verify-shadow",
            "--identity",
            "trade_id=CLI-TRADE",
            "--report-json",
            str(verify_report),
        ]
    )
    verify_stdout = json.loads(capsys.readouterr().out)
    assert verify_code == 0
    assert verify_stdout["mode"] == "verify-shadow"
    assert verify_stdout["ok"] is True
    assert verify_stdout["identities_checked"] == 1
    assert json.loads(verify_report.read_text(encoding="utf-8"))["mismatches"] == []


def test_shadow_parity_compares_typed_offsets_hashes_order_and_event_types(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.jsonl"
    index = tmp_path / "history_events.jsonl.identity-offset-v1.sqlite3"
    duplicate = {
        "event": "OPEN",
        "trade_id": "PARITY-TRADE",
        "trade_uuid": "PARITY-UUID",
        "raw": {"execution_id": "PARITY-EXEC"},
    }
    _write_records(
        source,
        [
            duplicate,
            duplicate,
            {
                "event": "STOP_UPDATED",
                "trade_id": "PARITY-TRADE",
                "details": {
                    "position_uuid": "PARITY-UUID",
                    "clientorderid": "PARITY-CLIENT",
                },
            },
        ],
    )
    index_v1.build_index(
        source,
        index,
        "history_manager",
        config=_small_config(),
    )

    result = index_v1.verify_shadow(
        source,
        index,
        [
            ("trade_id", "PARITY-TRADE"),
            ("trade_uuid", "PARITY-UUID"),
            ("execution_id", "PARITY-EXEC"),
            ("clientorderid", "PARITY-CLIENT"),
        ],
    )

    assert result.ok is True
    assert result.mismatches == ()
    assert result.identities_checked == 4
    assert result.index_offsets == 9
    assert result.forward_offsets == 9
    assert result.full_forward_bytes == source.stat().st_size
    assert index_v1.lookup_offsets(
        index,
        "client_order_id",
        "PARITY-CLIENT",
        0,
        source.stat().st_size,
    ) == index_v1.lookup_offsets(
        index,
        "clientorderid",
        "PARITY-CLIENT",
        0,
        source.stat().st_size,
    )


def test_source_sampled_shadow_detects_a_coherently_removed_identity_posting(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.jsonl.identity-offset-v1.sqlite3"
    missing_type = "trade_uuid"
    missing_value = "SOURCE-ONLY-IDENTITY"
    _write_records(
        source,
        [{"event": "OPEN", missing_type: missing_value}],
    )
    index_v1.build_index(
        source,
        index,
        "timeline",
        config=_small_config(),
    )

    connection = sqlite3.connect(index)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        identity_row = connection.execute(
            """
            SELECT identity_id FROM identities
            WHERE identity_type=? AND identity_value=?
            """,
            (missing_type, missing_value),
        ).fetchone()
        assert identity_row is not None
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM postings WHERE identity_id=?", (int(identity_row[0]),)
        )
        connection.execute(
            "DELETE FROM identities WHERE identity_id=?", (int(identity_row[0]),)
        )
        connection.execute(
            "UPDATE segments SET strong_postings=strong_postings-1"
        )
        connection.commit()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()

    assert index_v1.lookup_offsets(
        index,
        missing_type,
        missing_value,
        0,
        source.stat().st_size,
    ) == ()
    result = index_v1.verify_shadow(
        source,
        index,
        identities=None,
        sample_limit=100,
    )

    assert result.ok is False
    assert result.sampling_mode == "SOURCE_STRATIFIED_BOTTOM_K"
    assert result.identities_checked == 1
    assert result.sampled_strong_identities == 1
    assert result.sampled_secondary_identities == 0
    assert result.index_offsets == 0
    assert result.forward_offsets == 1
    assert len(result.mismatches) == 1
    mismatch = result.mismatches[0]
    assert mismatch["identity_type"] == missing_type
    assert mismatch["identity_value"] == missing_value
    assert mismatch["index"] == []
    assert len(mismatch["forward"]) == 1


def test_over_64_mib_shadow_build_has_bounded_memory_and_low_factual_lookup_io(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history_events.large.jsonl"
    index = tmp_path / "history_events.large.identity-offset-v1.sqlite3"
    line_bytes = 4 * 1024
    events_per_trade = 5
    physical_lines = 16_385
    trades = physical_lines // events_per_trade
    assert physical_lines % events_per_trade == 0

    def representative_line(event_number: int) -> bytes:
        trade_number = event_number // events_per_trade
        record = {
            "event": "PERFORMANCE_EVENT",
            "event_number": event_number,
            "trade_id": f"PERF-TRADE-{trade_number:08d}",
            "trade_uuid": f"PERF-UUID-{trade_number:08d}",
            "lifecycle_id": f"PERF-LIFECYCLE-{trade_number:08d}",
            "client_order_id": f"PERF-CLIENT-{trade_number:08d}",
            "padding": "",
        }
        without_padding = _line(record)
        padding_bytes = line_bytes - len(without_padding)
        assert padding_bytes > 0
        record["padding"] = "x" * padding_bytes
        encoded = _line(record)
        assert len(encoded) == line_bytes
        return encoded

    with source.open("wb") as handle:
        for event_number in range(physical_lines):
            handle.write(representative_line(event_number))
    source_bytes = source.stat().st_size
    assert source_bytes == physical_lines * line_bytes
    assert source_bytes > 64 * 1024 * 1024

    config = index_v1.BuildConfig(
        block_bytes=32 * 1024,
        segment_target_bytes=2 * 1024 * 1024,
        batch_bytes=8 * 1024 * 1024,
        batch_lines=5_000,
        max_line_bytes=128 * 1024,
        anchor_bytes=64 * 1024,
        busy_timeout_ms=50,
    )
    report = index_v1.build_index(
        source,
        index,
        "history_manager",
        config=config,
        measure_memory=True,
    )

    assert report.published is True
    assert report.source_bytes == source_bytes
    assert report.safe_watermark == source_bytes
    assert report.total_physical_lines == physical_lines
    assert report.mapping_records == physical_lines
    assert report.unique_identities == trades * 4
    assert report.postings == physical_lines * 4
    assert report.strong_postings == physical_lines * 3
    assert report.secondary_postings == physical_lines
    assert report.postings_per_record == {
        "min": 4,
        "p50": 4,
        "avg": 4.0,
        "p95": 4,
        "max": 4,
    }
    assert report.index_db_bytes < source_bytes // 2
    assert report.db_source_ratio < 0.5
    assert report.peak_pending_line_bytes == line_bytes
    assert report.peak_tracemalloc_bytes < source_bytes // 4
    assert report.max_batch_bytes <= config.batch_bytes + config.max_line_bytes
    assert report.build_duration_seconds > 0
    assert report.throughput_mib_per_second > 0

    candidates = index_v1.lookup_records(
        index,
        "trade_uuid",
        "PERF-UUID-00000000",
        0,
        source_bytes,
    )
    assert len(candidates) == events_per_trade
    assert tuple(row.start_offset for row in candidates) == tuple(
        event_number * line_bytes for event_number in range(events_per_trade)
    )
    with source.open("rb") as handle:
        factual = [
            index_v1.read_and_verify_record(handle, candidate)
            for candidate in candidates
        ]
    assert {row["trade_id"] for row in factual} == {"PERF-TRADE-00000000"}
    assert [row["event_number"] for row in factual] == list(range(events_per_trade))

    parity = index_v1.verify_shadow(
        source,
        index,
        [("trade_uuid", "PERF-UUID-00000000")],
    )
    assert parity.ok is True
    assert parity.full_forward_bytes == source_bytes
    assert parity.factual_record_bytes == events_per_trade * line_bytes
    assert parity.factual_record_bytes < 1024 * 1024
    assert parity.lookup_duration_ms >= 0
