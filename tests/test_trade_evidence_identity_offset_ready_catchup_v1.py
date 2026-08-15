from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

import trade_evidence_identity_offset_index_v1 as index_v1
import trade_evidence_identity_offset_shadow_compare_v1 as shadow_v1
import trade_timeline_validator as validator
from tools import build_trade_evidence_identity_offset_index_v1 as cli


class _SimulatedCrash(RuntimeError):
    pass


def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("network access is forbidden in READY catch-up tests")


@pytest.fixture(autouse=True)
def _safe_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)


def _line(record: Mapping[str, Any], *, newline: bytes = b"\n") -> bytes:
    return json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + newline


def _event(number: int, **updates: Any) -> dict[str, Any]:
    record = {
        "trade_uuid": f"CATCHUP-UUID-{number}",
        "event_type": "POSITION_OPEN",
        "event_id": f"CATCHUP-EVENT-{number}",
        "timestamp": f"2026-08-14T12:00:{number % 60:02d}Z",
    }
    record.update(updates)
    return record


def _config(*, batch_lines: int = 2) -> index_v1.BuildConfig:
    return index_v1.BuildConfig(
        block_bytes=32,
        segment_target_bytes=256,
        batch_bytes=2048,
        batch_lines=batch_lines,
        max_line_bytes=4096,
        anchor_bytes=16,
        busy_timeout_ms=25,
    )


def _build_ready(
    tmp_path: Path,
    *,
    initial: bytes | None = None,
    batch_lines: int = 2,
) -> tuple[Path, Path, index_v1.BuildReport]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.identity-offset-v1.sqlite3"
    source.write_bytes(initial if initial is not None else _line(_event(1)))
    report = index_v1.build_index(
        source,
        index,
        "timeline",
        config=_config(batch_lines=batch_lines),
        measure_memory=False,
    )
    assert report.published is True
    assert report.state == "READY"
    return source, index, report


def _state(index: Path) -> sqlite3.Row:
    with sqlite3.connect(index) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM source_state").fetchone()
        assert row is not None
        return row


def _counts(index: Path) -> dict[str, int]:
    with sqlite3.connect(index) as connection:
        return {
            "segments": int(connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]),
            "records": int(connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]),
            "identities": int(connection.execute("SELECT COUNT(*) FROM identities").fetchone()[0]),
            "postings": int(connection.execute("SELECT COUNT(*) FROM postings").fetchone()[0]),
        }


def _segments(index: Path) -> tuple[tuple[Any, ...], ...]:
    with sqlite3.connect(index) as connection:
        return tuple(
            connection.execute(
                """
                SELECT start_offset, end_offset, first_line_number,
                       last_line_number, hex(segment_hash)
                FROM segments ORDER BY start_offset
                """
            )
        )


def _fault_once(target: str) -> Callable[[str, Mapping[str, Any]], None]:
    fired = False

    def inject(point: str, _context: Mapping[str, Any]) -> None:
        nonlocal fired
        if point == target and not fired:
            fired = True
            raise _SimulatedCrash(target)

    return inject


def _assert_deep_valid(source: Path, index: Path) -> index_v1.ValidationResult:
    result = index_v1.validate_index(source, index, "timeline", deep=True)
    assert result.status in {
        index_v1.INDEX_COMPLETE_FOR_SNAPSHOT,
        index_v1.INDEX_PARTIAL,
    }
    assert result.state == "READY"
    return result


def _normalized_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(report))
    value.pop("generated_at", None)
    summary = value.get("summary")
    if isinstance(summary, dict):
        summary.pop("duration_ms", None)
    return value


def test_ready_resume_remains_rejected_but_catchup_is_incremental_and_idempotent(
    tmp_path: Path,
) -> None:
    source, index, built = _build_ready(tmp_path)
    old_segments = _segments(index)
    generation = built.generation_uuid
    appended = b"".join(
        (
            _line(_event(2)),
            b'{"broken":}\n',
            b'\xff\xfe\n',
            _line(_event(3, trade_id="SECONDARY-CATCHUP")),
        )
    )
    with source.open("ab") as handle:
        handle.write(appended)

    with pytest.raises(index_v1.IndexBuildError, match="only BUILDING or REVALIDATING"):
        index_v1.build_index(source, index, "timeline", resume=True)

    first = index_v1.catch_up_index(source, index, "timeline")
    after_first = _counts(index)
    state_after_first = _state(index)

    assert first.ok is True
    assert first.mode == "CATCH_UP"
    assert first.generation_uuid == generation
    assert first.safe_watermark_before == built.safe_watermark
    assert first.safe_watermark_after == source.stat().st_size
    assert first.processed_append_bytes == len(appended)
    assert first.physical_lines_processed == 4
    assert first.valid_json == 2
    assert first.invalid_json == 1
    assert first.invalid_utf8 == 1
    assert first.mapping_records == 2
    assert first.new_postings > 0
    assert first.new_strong_postings > 0
    assert first.new_secondary_postings > 0
    assert first.trailing_fragment_bytes == 0
    assert first.final_validation_status == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    assert _segments(index)[: len(old_segments)] == old_segments
    assert str(state_after_first["state"]) == "READY"
    assert int(state_after_first["safe_watermark"]) == int(
        state_after_first["build_snapshot_eof"]
    )

    second = index_v1.catch_up_index(source, index, "timeline")

    assert second.mode == "NO_OP"
    assert second.processed_append_bytes == 0
    assert second.committed_batches == 0
    assert second.safe_watermark_before == second.safe_watermark_after
    assert second.generation_uuid == generation
    assert _counts(index) == after_first
    assert _segments(index)[: len(old_segments)] == old_segments
    assert _assert_deep_valid(source, index).status == index_v1.INDEX_COMPLETE_FOR_SNAPSHOT


def test_terminal_fragment_waits_for_lf_then_indexes_once(tmp_path: Path) -> None:
    source, index, built = _build_ready(tmp_path)
    fragment = b'{"trade_uuid":"FRAGMENT-'
    with source.open("ab") as handle:
        handle.write(fragment)

    partial = index_v1.catch_up_index(source, index, "timeline")
    counts_before_completion = _counts(index)

    assert partial.mode == "CATCH_UP"
    assert partial.safe_watermark_after == built.safe_watermark
    assert partial.processed_append_bytes == 0
    assert partial.trailing_fragment_bytes == len(fragment)
    assert _state(index)["trailing_fragment_kind"] == "INVALID_JSON"

    completion = b'UUID","event_type":"POSITION_OPEN"}\n'
    with source.open("ab") as handle:
        handle.write(completion)
    completed = index_v1.catch_up_index(source, index, "timeline")

    assert completed.safe_watermark_before == built.safe_watermark
    assert completed.safe_watermark_after == source.stat().st_size
    assert completed.mapping_records == 1
    assert completed.physical_lines_processed == 1
    assert completed.trailing_fragment_bytes == 0
    assert _counts(index)["records"] == counts_before_completion["records"] + 1
    assert index_v1.catch_up_index(source, index, "timeline").mode == "NO_OP"
    assert _assert_deep_valid(source, index).complete


def test_live_append_after_snapshot_stays_for_next_catchup(tmp_path: Path) -> None:
    source, index, _built = _build_ready(tmp_path)
    first_append = _line(_event(2))
    later_append = _line(_event(3))
    with source.open("ab") as handle:
        handle.write(first_append)
    captured_snapshot = source.stat().st_size
    appended_after_snapshot = False

    def live_writer(point: str, context: Mapping[str, Any]) -> None:
        nonlocal appended_after_snapshot
        if point == "after_catchup_snapshot" and not appended_after_snapshot:
            assert int(context["catchup_snapshot_eof"]) == captured_snapshot
            with source.open("ab") as handle:
                handle.write(later_append)
            appended_after_snapshot = True

    first = index_v1.catch_up_index(
        source,
        index,
        "timeline",
        fault_injector=live_writer,
    )

    assert first.catchup_snapshot_eof == captured_snapshot
    assert first.safe_watermark_after == captured_snapshot
    assert first.source_size_after == captured_snapshot + len(later_append)
    assert first.remaining_lag_bytes == len(later_append)
    assert first.final_validation_status == index_v1.INDEX_PARTIAL
    assert first.final_validation_reasons == ("WATERMARK_BEHIND_SNAPSHOT",)

    second = index_v1.catch_up_index(source, index, "timeline")
    assert second.safe_watermark_before == captured_snapshot
    assert second.safe_watermark_after == source.stat().st_size
    assert second.mapping_records == 1
    assert second.remaining_lag_bytes == 0
    assert _assert_deep_valid(source, index).complete


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("truncate", "SOURCE_SHRINK"),
        ("truncate_regrow", "PREFIX_HASH_PROOF_FAILED"),
        ("replace", "SOURCE_FILE_ID_MISMATCH"),
        ("rewrite_middle", "PREFIX_HASH_PROOF_FAILED"),
        ("watermark_anchor", "WATERMARK_ANCHOR_MISMATCH"),
        ("segment_hash", "PREFIX_HASH_PROOF_FAILED"),
        ("schema_version", "INDEX_VERSION_MISMATCH"),
        ("identity_contract", "IDENTITY_CONTRACT_MISMATCH"),
    ],
)
def test_incompatible_source_or_index_metadata_aborts_without_advancing_watermark(
    tmp_path: Path,
    mutation: str,
    reason: str,
) -> None:
    initial = b"".join(_line(_event(number, padding="x" * 80)) for number in range(1, 7))
    source, index, _built = _build_ready(tmp_path, initial=initial)
    watermark_before = int(_state(index)["safe_watermark"])
    generation_before = str(_state(index)["generation_uuid"])
    counts_before = _counts(index)

    if mutation == "truncate":
        source.write_bytes(initial[:-10])
    elif mutation == "truncate_regrow":
        changed = bytearray(initial)
        changed[len(changed) // 2] ^= 1
        source.write_bytes(bytes(changed))
    elif mutation == "replace":
        replacement = source.with_suffix(".replacement")
        replacement.write_bytes(initial)
        os.replace(replacement, source)
    elif mutation == "rewrite_middle":
        with source.open("r+b") as handle:
            handle.seek(len(initial) // 2)
            original = handle.read(1)
            handle.seek(len(initial) // 2)
            handle.write(bytes((original[0] ^ 1,)))
    elif mutation == "watermark_anchor":
        with sqlite3.connect(index) as connection:
            connection.execute(
                "UPDATE source_state SET watermark_anchor=?",
                (hashlib.blake2b(b"wrong", digest_size=16).digest(),),
            )
    elif mutation == "segment_hash":
        with sqlite3.connect(index) as connection:
            connection.execute(
                "UPDATE segments SET segment_hash=? WHERE segment_id="
                "(SELECT MIN(segment_id) FROM segments)",
                (hashlib.blake2b(b"wrong-segment", digest_size=16).digest(),),
            )
    elif mutation == "schema_version":
        with sqlite3.connect(index) as connection:
            connection.execute("UPDATE source_state SET schema_version=999")
    elif mutation == "identity_contract":
        with sqlite3.connect(index) as connection:
            connection.execute(
                "UPDATE source_state SET identity_contract_hash='wrong-contract'"
            )
    else:  # pragma: no cover - parametrization is exhaustive.
        raise AssertionError(mutation)

    with pytest.raises(index_v1.IndexBuildError, match=reason):
        index_v1.catch_up_index(source, index, "timeline")

    assert int(_state(index)["safe_watermark"]) == watermark_before
    assert str(_state(index)["generation_uuid"]) == generation_before
    assert _counts(index) == counts_before


@pytest.mark.parametrize(
    "fault_point,expect_progress",
    [
        ("before_batch_commit", False),
        ("after_record_before_postings", False),
        ("before_watermark_update", False),
        ("after_batch_commit", True),
        ("before_catchup_final_validation", True),
    ],
)
def test_crash_retry_has_no_gap_or_duplicate_and_never_uses_resume(
    tmp_path: Path,
    fault_point: str,
    expect_progress: bool,
) -> None:
    source, index, built = _build_ready(tmp_path, batch_lines=2)
    appended_records = [_event(number) for number in range(2, 8)]
    with source.open("ab") as handle:
        for record in appended_records:
            handle.write(_line(record))

    with pytest.raises(_SimulatedCrash, match=fault_point):
        index_v1.catch_up_index(
            source,
            index,
            "timeline",
            fault_injector=_fault_once(fault_point),
        )

    crashed_state = _state(index)
    crashed_watermark = int(crashed_state["safe_watermark"])
    assert str(crashed_state["state"]) == "READY"
    assert crashed_watermark == int(crashed_state["build_snapshot_eof"])
    assert (crashed_watermark > built.safe_watermark) is expect_progress
    _assert_deep_valid(source, index)

    with pytest.raises(index_v1.IndexBuildError, match="only BUILDING or REVALIDATING"):
        index_v1.build_index(source, index, "timeline", resume=True)
    retry = index_v1.catch_up_index(source, index, "timeline")

    assert retry.safe_watermark_after == source.stat().st_size
    assert str(_state(index)["generation_uuid"]) == built.generation_uuid
    assert _counts(index)["records"] == 1 + len(appended_records)
    with sqlite3.connect(index) as connection:
        duplicate_segments = connection.execute(
            """
            SELECT start_offset, COUNT(*) FROM segments
            GROUP BY start_offset HAVING COUNT(*) > 1
            """
        ).fetchall()
        duplicate_records = connection.execute(
            """
            SELECT start_offset, COUNT(*) FROM records
            GROUP BY start_offset HAVING COUNT(*) > 1
            """
        ).fetchall()
        duplicate_postings = connection.execute(
            """
            SELECT identity_id, start_offset, record_id, COUNT(*) FROM postings
            GROUP BY identity_id, start_offset, record_id HAVING COUNT(*) > 1
            """
        ).fetchall()
    assert duplicate_segments == duplicate_records == duplicate_postings == []
    assert _assert_deep_valid(source, index).complete


def test_ready_batches_are_atomic_to_a_concurrent_reader(tmp_path: Path) -> None:
    source, index, built = _build_ready(tmp_path, batch_lines=2)
    with source.open("ab") as handle:
        handle.write(_line(_event(2)))
        handle.write(_line(_event(3)))
    observations: list[tuple[str, int, int, int]] = []

    def observe(point: str, _context: Mapping[str, Any]) -> None:
        if point not in {"before_batch_sql_commit", "after_batch_commit"}:
            return
        with sqlite3.connect(index) as reader:
            state = reader.execute(
                "SELECT state, safe_watermark, build_snapshot_eof FROM source_state"
            ).fetchone()
            records = int(reader.execute("SELECT COUNT(*) FROM records").fetchone()[0])
        observations.append((str(state[0]), int(state[1]), int(state[2]), records))

    report = index_v1.catch_up_index(
        source,
        index,
        "timeline",
        fault_injector=observe,
    )

    assert observations[0] == ("READY", built.safe_watermark, built.safe_watermark, 1)
    assert observations[1] == (
        "READY",
        report.safe_watermark_after,
        report.safe_watermark_after,
        3,
    )
    assert report.committed_batches == 1


def test_cli_catchup_report_validate_deep_and_verify_shadow(tmp_path: Path, capsys) -> None:
    source, index, _built = _build_ready(tmp_path)
    with source.open("ab") as handle:
        handle.write(_line(_event(2)))
    report_path = tmp_path / "catchup-report.json"

    code = cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--catch-up",
            "--report-json",
            str(report_path),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["mode"] == "CATCH_UP"
    assert payload["safe_watermark_after"] == source.stat().st_size
    assert json.loads(report_path.read_text(encoding="utf-8")) == payload
    assert cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--validate",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == (
        index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    )
    assert cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--deep-validate",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == (
        index_v1.INDEX_COMPLETE_FOR_SNAPSHOT
    )
    assert cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--verify-shadow",
            "--identity",
            "trade_uuid=CATCHUP-UUID-2",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cli.main(
        [
            "--source",
            str(source),
            "--index",
            str(index),
            "--source-id",
            "timeline",
            "--resume",
        ]
    ) == 2
    resume_error = json.loads(capsys.readouterr().err)
    assert "only BUILDING or REVALIDATING" in resume_error["message"]


def test_large_ready_prefix_is_verified_bounded_and_only_append_is_indexed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "large-timeline.jsonl"
    index = tmp_path / "large-timeline.sqlite3"
    noise = _line({"event_type": "NOISE", "padding": "x" * 256})
    with source.open("wb") as handle:
        for _ in range(8_000):
            handle.write(noise)
    config = index_v1.BuildConfig(
        block_bytes=64 * 1024,
        segment_target_bytes=512 * 1024,
        batch_bytes=2 * 1024 * 1024,
        batch_lines=5_000,
        max_line_bytes=1024 * 1024,
        anchor_bytes=64 * 1024,
        busy_timeout_ms=50,
    )
    built = index_v1.build_index(
        source,
        index,
        "timeline",
        config=config,
        measure_memory=False,
    )
    prefix_bytes = source.stat().st_size
    append = _line(_event(99))
    with source.open("ab") as handle:
        handle.write(append)

    report = index_v1.catch_up_index(source, index, "timeline", measure_memory=True)

    assert prefix_bytes > 2 * 1024 * 1024
    assert report.verified_prefix_bytes == prefix_bytes
    assert report.processed_append_bytes == len(append)
    assert report.mapping_records == 1
    assert report.physical_lines_processed == 1
    assert report.safe_watermark_after == source.stat().st_size
    assert report.peak_tracemalloc_bytes < 32 * 1024 * 1024
    assert report.duration_seconds > 0
    assert report.throughput_mib_per_second >= 0
    assert report.generation_uuid == built.generation_uuid
    assert _assert_deep_valid(source, index).complete


def test_phase_b_remains_legacy_authoritative_and_matches_caught_up_ready_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trade_id = "CATCHUP-SHADOW-TRADE"
    trade_uuid = "CATCHUP-SHADOW-UUID"
    registry = {
        "trade_id": trade_id,
        "trade_uuid": trade_uuid,
        "registry_id": "CATCHUP-SHADOW-REGISTRY",
        "lifecycle_id": "CATCHUP-SHADOW-LIFECYCLE",
        "status": "OPEN",
        "opened_at": "2026-08-14T12:00:00Z",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
    }
    (tmp_path / "trade_registry.json").write_text(
        json.dumps(registry, separators=(",", ":")),
        encoding="utf-8",
    )
    history = tmp_path / "history_events.jsonl"
    timeline = tmp_path / "timeline.jsonl"
    history.write_bytes(
        _line(
            {
                "trade_id": trade_id,
                "trade_uuid": trade_uuid,
                "event_type": "SIGNAL_RECEIVED",
                "event_id": "H-BEFORE-CATCHUP",
                "timestamp": "2026-08-14T12:00:01Z",
            }
        )
    )
    timeline.write_bytes(
        _line(
            {
                "trade_id": trade_id,
                "trade_uuid": trade_uuid,
                "event_type": "POSITION_OPEN",
                "event_id": "T-BEFORE-CATCHUP",
                "timestamp": "2026-08-14T12:00:02Z",
            }
        )
    )
    history_index = tmp_path / "history.sqlite3"
    timeline_index = tmp_path / "timeline.sqlite3"
    phase_b_config = index_v1.BuildConfig(
        block_bytes=64,
        segment_target_bytes=512,
        batch_bytes=4096,
        batch_lines=4,
        max_line_bytes=validator.JSONL_MAX_BYTES,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )
    assert index_v1.build_index(
        history,
        history_index,
        "history_manager",
        config=phase_b_config,
        measure_memory=False,
    ).published
    assert index_v1.build_index(
        timeline,
        timeline_index,
        "timeline",
        config=phase_b_config,
        measure_memory=False,
    ).published
    with history.open("ab") as handle:
        handle.write(
            _line(
                {
                    "trade_uuid": trade_uuid,
                    "execution_id": "CATCHUP-EXECUTION",
                    "event_type": "RISK_APPROVED",
                    "event_id": "H-AFTER-CATCHUP",
                    "timestamp": "2026-08-14T12:00:03Z",
                }
            )
        )
    with timeline.open("ab") as handle:
        handle.write(
            _line(
                {
                    "trade_uuid": trade_uuid,
                    "event_type": "BREAK_EVEN",
                    "event_id": "T-AFTER-CATCHUP",
                    "timestamp": "2026-08-14T12:00:04Z",
                }
            )
        )
    assert index_v1.catch_up_index(history, history_index, "history_manager").ok
    assert index_v1.catch_up_index(timeline, timeline_index, "timeline").ok

    for name in (
        "TRADE_EVIDENCE_INDEX_SHADOW_ENABLED",
        "TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED",
        "TRADE_EVIDENCE_INDEX_HISTORY_PATH",
        "TRADE_EVIDENCE_INDEX_TIMELINE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))
    baseline = validator.validate_trade_timeline(trade_id)
    observed: list[shadow_v1.ShadowCompareReport] = []
    real_observer = shadow_v1.observe_evidence_bundle

    def capture(bundle: Any, **kwargs: Any) -> shadow_v1.ShadowCompareReport:
        result = real_observer(bundle, **kwargs)
        observed.append(result)
        return result

    monkeypatch.setattr(shadow_v1, "observe_evidence_bundle", capture)
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "true")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "true")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_HISTORY_PATH", str(history_index))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_TIMELINE_PATH", str(timeline_index))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE", "1")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED", "false")
    active = validator.validate_trade_timeline(trade_id)

    assert _normalized_report(active) == _normalized_report(baseline)
    assert len(observed) == 1
    assert observed[0].status == shadow_v1.MATCH
    assert all(
        item.mode == "INDEX_ONLY" and item.status == shadow_v1.MATCH
        for item in observed[0].sources.values()
    )
    assert "_shadow_index_capture" not in json.dumps(active, default=str)


def test_missing_or_non_ready_index_is_never_created_or_caught_up(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    missing = tmp_path / "missing.sqlite3"
    source.write_bytes(_line(_event(1)))

    with pytest.raises(index_v1.IndexBuildError, match="existing index"):
        index_v1.catch_up_index(source, missing, "timeline")
    assert not missing.exists()

    _source, index, built = _build_ready(tmp_path / "non-ready")
    with sqlite3.connect(index) as connection:
        connection.execute("UPDATE source_state SET state='REVALIDATING'")
    with pytest.raises(index_v1.IndexBuildError, match="only READY"):
        index_v1.catch_up_index(_source, index, "timeline")
    assert int(_state(index)["safe_watermark"]) == built.safe_watermark
