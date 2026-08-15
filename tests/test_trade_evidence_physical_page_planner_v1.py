from __future__ import annotations

import json
import os
import random
import socket
import sqlite3
import time
import tracemalloc
from pathlib import Path
from typing import Any, Mapping

import pytest

import trade_evidence_identity_offset_index_v1 as index_v1
import trade_evidence_physical_page_planner_v1 as planner_v1
import trade_timeline_validator as validator


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("network access is forbidden in C0 planner tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _config(
    *,
    block_bytes: int = 64,
    segment_target_bytes: int = 128,
    max_line_bytes: int = 4096,
) -> index_v1.BuildConfig:
    return index_v1.BuildConfig(
        block_bytes=block_bytes,
        segment_target_bytes=segment_target_bytes,
        batch_bytes=max(
            16 * 1024,
            segment_target_bytes * 4,
            block_bytes * 8,
        ),
        batch_lines=5000,
        max_line_bytes=max(max_line_bytes, block_bytes),
        anchor_bytes=64,
        busy_timeout_ms=50,
    )


def _build(
    source: Path,
    index: Path,
    *,
    config: index_v1.BuildConfig | None = None,
) -> None:
    report = index_v1.build_index_v2(
        source,
        index,
        "timeline",
        config=config or _config(),
        measure_memory=False,
    )
    assert report.published is True
    validation = index_v1.validate_index_v2(
        source, index, "timeline", deep=True
    )
    assert validation.status == index_v1.INDEX_V2_CERTIFIED


def _legacy(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cursor: str | None = None,
    byte_budget: int | None = None,
    record_budget: int | None = None,
    block_bytes: int | None = None,
    retain_rows: bool = True,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    if byte_budget is not None:
        monkeypatch.setattr(validator, "JSONL_MAX_BYTES", byte_budget)
    if record_budget is not None:
        monkeypatch.setattr(validator, "JSONL_MAX_VALID_LINES", record_budget)
    if block_bytes is not None:
        monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", block_bytes)
    metadata = validator._new_reader_metadata()
    rows: list[Mapping[str, Any]] = []
    for row in validator._read_path(
        source,
        metadata,
        scan_cursor=cursor,
        capture_shadow_window=True,
    ):
        if retain_rows:
            rows.append(row)
    return rows, metadata


def _assert_exact_physical_parity(
    legacy: Mapping[str, Any],
    plan: planner_v1.PhysicalPagePlan,
) -> None:
    assert plan.status == planner_v1.REPRODUCIBLE, plan.to_dict()
    expected = plan.legacy_physical_metadata()
    actual = {name: legacy.get(name) for name in expected}
    assert actual == expected, {
        name: {"legacy": actual[name], "planner": expected[name]}
        for name in expected
        if actual[name] != expected[name]
    }
    window = legacy.get("_shadow_physical_window") or {}
    if window.get("page_start") is not None:
        assert plan.page_start == int(window["page_start"])
    assert plan.page_end == int(window.get("page_end", plan.page_end))


def test_small_mixed_physical_classification_matches_legacy_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(
        b"\r\n"
        b"42\r\n"
        b'{"timestamp":"bad","trade_id":"T"}\r\n'
        b"\xff\r\n"
        b"{oops}\n"
        b'["x"]\n'
        b'{"timestamp":"2026-08-15T12:00:00Z","trade_id":"T"}\n'
    )
    _build(source, index, config=_config(segment_target_bytes=24))

    _rows, legacy = _legacy(source, monkeypatch)
    plan = planner_v1.plan_physical_page(source, index, "timeline")

    _assert_exact_physical_parity(legacy, plan)
    assert plan.lines_scanned == 7
    assert plan.records_examined == 6
    assert plan.blank_lines == 1
    assert plan.valid_lines == 4
    assert plan.invalid_lines == 2
    assert plan.invalid_utf8 == 1
    assert plan.invalid_json == 1
    assert plan.mapping_records == 2
    assert plan.nonmapping_json == 2
    assert plan.time_range_scanned == {
        "oldest": "2026-08-15T12:00:00+00:00",
        "newest": "bad",
    }


def test_record_budget_and_tainted_cursor_page_two_match_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b"1\n2\n\n3\n")
    _build(source, index)

    _rows, legacy_first = _legacy(
        source,
        monkeypatch,
        byte_budget=64,
        record_budget=2,
        block_bytes=64,
    )
    first = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=64,
        record_budget=2,
        block_bytes=64,
    )
    _assert_exact_physical_parity(legacy_first, first)
    assert first.page_start == 2
    assert first.bytes_scanned == 7
    assert first.lines_scanned == 3
    assert first.records_examined == 2
    assert first.blank_lines == 1
    assert first.stop_reason == "RECORD_BUDGET"
    decoded_first = validator._decode_scan_cursor(first.next_scan_cursor)
    assert first.cursor_inputs == {
        name: decoded_first[name]
        for name in first.cursor_inputs
    }

    cursor = legacy_first["next_scan_cursor"]
    _rows, legacy_second = _legacy(
        source,
        monkeypatch,
        cursor=cursor,
        byte_budget=64,
        record_budget=2,
        block_bytes=64,
    )
    second = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        scan_cursor=cursor,
        byte_budget=64,
        record_budget=2,
        block_bytes=64,
    )
    _assert_exact_physical_parity(legacy_second, second)
    assert second.stop_reason == "PRIOR_PAGE_COVERAGE_LIMITED"
    assert second.partial is True
    assert second.next_scan_cursor is None


def test_byte_boundary_discards_carry_even_at_real_line_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b"1\n2\n3\n")
    _build(source, index)

    _rows, legacy = _legacy(
        source,
        monkeypatch,
        byte_budget=4,
        record_budget=100,
        block_bytes=4,
    )
    plan = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=4,
        record_budget=100,
        block_bytes=4,
    )

    _assert_exact_physical_parity(legacy, plan)
    assert plan.page_start == 4
    assert plan.bytes_scanned == 4
    assert plan.records_examined == 1
    assert plan.stop_reason == "BYTE_BUDGET"


@pytest.mark.parametrize(
    ("payload", "byte_budget", "block_bytes", "expected"),
    [
        (
            b"{bad}\n \r\n",
            8,
            2,
            {"page_start": 6, "lines_scanned": 1, "invalid_lines": 1},
        ),
        (
            b'{"timestamp":"bad"}\n \r\n\n{"timestamp":"bad"}\n',
            24,
            3,
            {"page_start": 23, "lines_scanned": 1, "invalid_lines": 0},
        ),
    ],
)
def test_legacy_cross_block_carry_and_blank_quirks_match_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    byte_budget: int,
    block_bytes: int,
    expected: Mapping[str, int],
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(payload)
    _build(source, index)

    _rows, legacy = _legacy(
        source,
        monkeypatch,
        byte_budget=byte_budget,
        record_budget=100,
        block_bytes=block_bytes,
    )
    plan = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=byte_budget,
        record_budget=100,
        block_bytes=block_bytes,
    )

    _assert_exact_physical_parity(legacy, plan)
    for name, value in expected.items():
        assert getattr(plan, name) == value


def test_deterministic_small_adversarial_matrix_has_zero_metadata_differences(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rng = random.Random(20260815)
    physical_lines = (
        b"\n",
        b" \r\n",
        b"0\n",
        b"[]\n",
        b"{bad}\n",
        b"\xff\n",
        b'{"timestamp":"bad"}\n',
        b'{"timestamp":"2026-08-15T12:00:00Z"}\r\n',
        b"X" * 19 + b"\n",
    )
    for case in range(32):
        source = tmp_path / f"timeline-{case}.jsonl"
        index = tmp_path / f"timeline-{case}.sqlite3"
        source.write_bytes(
            b"".join(
                rng.choice(physical_lines)
                for _ in range(rng.randint(2, 18))
            )
        )
        _build(source, index)
        byte_budget = rng.randint(5, 48)
        record_budget = rng.randint(1, 8)
        block_bytes = rng.randint(2, 9)

        _rows, legacy = _legacy(
            source,
            monkeypatch,
            byte_budget=byte_budget,
            record_budget=record_budget,
            block_bytes=block_bytes,
        )
        plan = planner_v1.plan_physical_page(
            source,
            index,
            "timeline",
            byte_budget=byte_budget,
            record_budget=record_budget,
            block_bytes=block_bytes,
        )

        _assert_exact_physical_parity(legacy, plan)


def test_invalid_rows_consume_record_budget_and_exact_limit_at_zero_is_complete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b"{bad}\n\xff\n")
    _build(source, index)

    _rows, legacy = _legacy(
        source,
        monkeypatch,
        record_budget=2,
        byte_budget=64,
        block_bytes=8,
    )
    plan = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        record_budget=2,
        byte_budget=64,
        block_bytes=8,
    )

    _assert_exact_physical_parity(legacy, plan)
    assert plan.records_examined == 2
    assert plan.invalid_lines == 2
    assert plan.page_start == 0
    assert plan.stop_reason == "START_OF_SNAPSHOT"
    assert plan.coverage_complete is True


@pytest.mark.parametrize(
    ("fragment", "valid_lines", "invalid_lines", "mapping_records"),
    [
        (b'{"event":"TERMINAL","trade_id":"T"}', 2, 0, 2),
        (b'{"event":"PARTIAL"', 1, 1, 1),
    ],
)
def test_terminal_line_without_lf_matches_legacy_from_certified_tail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fragment: bytes,
    valid_lines: int,
    invalid_lines: int,
    mapping_records: int,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b'{"event":"BASE","trade_id":"T"}\n')
    _build(source, index)
    with source.open("ab") as handle:
        handle.write(fragment)
    catchup = index_v1.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )
    assert catchup.safe_watermark_after == catchup.safe_watermark_before

    _rows, legacy = _legacy(source, monkeypatch)
    plan = planner_v1.plan_physical_page(source, index, "timeline")

    _assert_exact_physical_parity(legacy, plan)
    assert plan.lines_scanned == 2
    assert plan.valid_lines == valid_lines
    assert plan.invalid_lines == invalid_lines
    assert plan.mapping_records == mapping_records


def test_exact_budget_line_is_oversized_and_small_boundary_cap_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b"0\n" + b"x" * 4 + b"\n")
    _build(
        source,
        index,
        config=_config(block_bytes=4, max_line_bytes=4),
    )

    _rows, legacy = _legacy(
        source,
        monkeypatch,
        byte_budget=5,
        record_budget=100,
        block_bytes=5,
    )
    plan = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=5,
        record_budget=100,
        block_bytes=5,
        max_boundary_scan_bytes=5,
    )
    _assert_exact_physical_parity(legacy, plan)
    assert plan.stop_reason == "LINE_EXCEEDS_BYTE_BUDGET"
    assert plan.oversized is True

    refused = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=5,
        record_budget=100,
        block_bytes=5,
        max_boundary_scan_bytes=4,
    )
    assert refused.status == planner_v1.NOT_REPRODUCIBLE
    assert refused.reason == "BOUNDARY_SCAN_LIMIT"


def test_oversized_continuation_preserves_stop_and_page_flag_at_offset_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(b"X" * 40 + b"\n")
    _build(source, index)
    cursor: str | None = None
    last: planner_v1.PhysicalPagePlan | None = None
    for _ in range(3):
        _rows, legacy = _legacy(
            source,
            monkeypatch,
            cursor=cursor,
            byte_budget=16,
            record_budget=100,
            block_bytes=4,
        )
        last = planner_v1.plan_physical_page(
            source,
            index,
            "timeline",
            scan_cursor=cursor,
            byte_budget=16,
            record_budget=100,
            block_bytes=4,
        )
        _assert_exact_physical_parity(legacy, last)
        assert last.oversized is True
        cursor = legacy["next_scan_cursor"]
    assert last is not None
    assert last.next_scan_cursor is None
    assert last.stop_reason == "LINE_EXCEEDS_BYTE_BUDGET"


def test_actual_100k_nonblank_boundary_matches_without_full_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    with source.open("wb") as handle:
        for _ in range(100_001):
            handle.write(b"0\n")
    _build(
        source,
        index,
        config=_config(segment_target_bytes=4096),
    )

    _rows, legacy = _legacy(source, monkeypatch, retain_rows=False)
    plan = planner_v1.plan_physical_page(source, index, "timeline")

    _assert_exact_physical_parity(legacy, plan)
    assert plan.stop_reason == "RECORD_BUDGET"
    assert plan.records_examined == 100_000
    assert plan.page_start == 2
    assert plan.boundary_scan_bytes < source.stat().st_size


def test_append_after_snapshot_is_ignored_and_mutations_are_refused(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    original = b'{"trade_id":"T","event":"A"}\n'
    source.write_bytes(original)
    _build(source, index)

    def append_after_snapshot(point: str, _context: Mapping[str, Any]) -> None:
        if point == "after_snapshot":
            with source.open("ab") as handle:
                handle.write(b'{"trade_id":"T","event":"LATE"}\n')

    appended = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        fault_injector=append_after_snapshot,
    )
    assert appended.status == planner_v1.REPRODUCIBLE
    assert appended.snapshot_eof == len(original)
    assert appended.source_size_bytes == len(original)
    assert appended.lines_scanned == 1
    assert source.stat().st_size > appended.snapshot_eof

    guarded_source = tmp_path / "guarded.jsonl"
    guarded_index = tmp_path / "guarded-v2.sqlite3"
    guarded_source.write_bytes(original)
    _build(guarded_source, guarded_index)

    def rewrite_then_append(point: str, _context: Mapping[str, Any]) -> None:
        if point == "after_snapshot":
            changed = guarded_source.read_bytes().replace(b'"A"', b'"B"')
            guarded_source.write_bytes(
                changed + b'{"trade_id":"T","event":"LATE"}\n'
            )

    guarded = planner_v1.plan_physical_page(
        guarded_source,
        guarded_index,
        "timeline",
        fault_injector=rewrite_then_append,
    )
    assert guarded.status == planner_v1.NOT_REPRODUCIBLE
    assert guarded.reason == "SOURCE_REWRITTEN_DURING_PLAN"

    # A later request has no append witness/certification and must refuse.
    stale = planner_v1.plan_physical_page(source, index, "timeline")
    assert stale.status == planner_v1.NOT_REPRODUCIBLE
    assert stale.reason == "SOURCE_CHANGED_AFTER_CERTIFICATION"

    # Rebuild a fresh generation, then prove same-size rewrite and os.replace
    # are never declared equivalent.
    rewritten_index = tmp_path / "timeline.rewrite-v2.sqlite3"
    _build(source, rewritten_index)
    current = source.read_bytes()
    changed = current.replace(b'"A"', b'"B"', 1)
    source.write_bytes(changed)
    old_stat = source.stat()
    os.utime(
        source,
        ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000),
    )
    rewrite = planner_v1.plan_physical_page(
        source, rewritten_index, "timeline"
    )
    assert rewrite.status == planner_v1.NOT_REPRODUCIBLE
    assert rewrite.reason in {
        "CERTIFIED_SOURCE_METADATA_MISMATCH",
        "CERTIFIED_ANCHOR_MISMATCH",
    }

    regrow_index = tmp_path / "timeline.regrow-v2.sqlite3"
    _build(source, regrow_index)
    regrown = bytearray(source.read_bytes())
    regrown[-2] = ord("Z") if regrown[-2] != ord("Z") else ord("Y")
    with source.open("wb") as handle:
        handle.write(regrown)
    regrow = planner_v1.plan_physical_page(source, regrow_index, "timeline")
    assert regrow.status == planner_v1.NOT_REPRODUCIBLE
    assert regrow.reason in {
        "CERTIFIED_SOURCE_METADATA_MISMATCH",
        "CERTIFIED_ANCHOR_MISMATCH",
    }

    replacement_index = tmp_path / "timeline.replace-v2.sqlite3"
    _build(source, replacement_index)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(source.read_bytes())
    os.replace(replacement, source)
    replaced = planner_v1.plan_physical_page(
        source, replacement_index, "timeline"
    )
    assert replaced.status == planner_v1.NOT_REPRODUCIBLE
    assert replaced.reason == "SOURCE_FILE_ID_MISMATCH"


def test_append_proof_rechecks_source_after_the_bounded_hash_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(
        b"".join(
            (
                json.dumps(
                    {"trade_id": f"PROOF-{number}", "event": "EVENT"},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            for number in range(400)
        )
    )
    snapshot_size = source.stat().st_size
    _build(source, index)
    original_proof = planner_v1._prove_append_only_growth

    def append_after_snapshot(point: str, _context: Mapping[str, Any]) -> None:
        if point == "after_snapshot":
            with source.open("ab") as handle:
                handle.write(b'{"trade_id":"LATE","event":"APPEND"}\n')

    def rewrite_after_proof(*args: Any, **kwargs: Any):
        result = original_proof(*args, **kwargs)
        with source.open("r+b") as handle:
            handle.seek(snapshot_size // 2)
            original = handle.read(1)
            handle.seek(snapshot_size // 2)
            handle.write(b"Z" if original != b"Z" else b"Y")
            handle.seek(0, os.SEEK_END)
            handle.write(b'{"trade_id":"LATER","event":"APPEND"}\n')
        return result

    monkeypatch.setattr(
        planner_v1,
        "_prove_append_only_growth",
        rewrite_after_proof,
    )
    plan = planner_v1.plan_physical_page(
        source,
        index,
        "timeline",
        fault_injector=append_after_snapshot,
    )

    assert plan.status == planner_v1.NOT_REPRODUCIBLE
    assert plan.reason == "SOURCE_CHANGED_DURING_APPEND_PROOF"


def test_planner_rejects_coherent_post_certification_summary_tamper(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    source.write_bytes(
        b'{"timestamp":"2026-08-15T12:00:00Z","trade_id":"T"}\n'
    )
    _build(source, index)
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE segments SET oldest_timestamp='ZZZ', newest_timestamp='ZZZ'"
        )
        connection.commit()

    plan = planner_v1.plan_physical_page(source, index, "timeline")

    assert plan.status == planner_v1.NOT_REPRODUCIBLE
    assert plan.reason == "CERTIFIED_SUMMARY_HASH_MISMATCH"


def test_default_64_mib_window_preserves_cross_block_replay_quirk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline-default-carry.jsonl"
    index = tmp_path / "timeline-default-carry-v2.sqlite3"
    target_size = validator.JSONL_MAX_BYTES + 1
    first_line = b"X" * (2 * validator.JSONL_BLOCK_BYTES - 1) + b"\n"
    with source.open("wb") as handle:
        handle.write(first_line)
        remaining = target_size - len(first_line)
        while remaining:
            line_length = min(1024 * 1024, remaining)
            handle.write(b" " * (line_length - 1) + b"\n")
            remaining -= line_length
    _build(
        source,
        index,
        config=_config(
            block_bytes=1024 * 1024,
            segment_target_bytes=512 * 1024,
            max_line_bytes=64 * 1024 * 1024,
        ),
    )

    _rows, legacy = _legacy(source, monkeypatch, retain_rows=False)
    plan = planner_v1.plan_physical_page(source, index, "timeline")

    _assert_exact_physical_parity(legacy, plan)
    assert plan.page_start == len(first_line)
    assert plan.invalid_lines == 1
    assert plan.bytes_scanned == validator.JSONL_MAX_BYTES
    assert plan.boundary_scan_bytes < planner_v1.DEFAULT_MAX_BOUNDARY_SCAN_BYTES


def test_over_64_mib_planner_matches_legacy_with_bounded_boundary_io_and_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    index = tmp_path / "timeline.physical-v2.sqlite3"
    prefix = b'{"timestamp":"2026-08-15T12:00:00Z","trade_id":"OTHER","padding":"'
    suffix = b'"}\n'
    line = prefix + (b"x" * (4096 - len(prefix) - len(suffix))) + suffix
    assert len(line) == 4096
    with source.open("wb") as handle:
        for _ in range(16_385):
            handle.write(line)
    assert source.stat().st_size > validator.JSONL_MAX_BYTES
    _build(
        source,
        index,
        config=_config(
            block_bytes=1024 * 1024,
            segment_target_bytes=512 * 1024,
            max_line_bytes=64 * 1024 * 1024,
        ),
    )

    tracemalloc.start()
    legacy_started = time.perf_counter()
    _rows, legacy = _legacy(source, monkeypatch, retain_rows=False)
    legacy_duration = time.perf_counter() - legacy_started
    _current, legacy_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tracemalloc.start()
    planner_started = time.perf_counter()
    plan = planner_v1.plan_physical_page(source, index, "timeline")
    planner_duration = time.perf_counter() - planner_started
    _current, planner_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    _assert_exact_physical_parity(legacy, plan)
    assert legacy["bytes_scanned"] == validator.JSONL_MAX_BYTES
    assert plan.boundary_scan_bytes < 2 * 1024 * 1024
    assert plan.boundary_scan_bytes < legacy["bytes_scanned"] // 16
    assert plan.segment_rows_consulted < 1024
    assert planner_peak < 32 * 1024 * 1024
    print(
        json.dumps(
            {
                "source_size_bytes": source.stat().st_size,
                "legacy_bytes_scanned": legacy["bytes_scanned"],
                "legacy_duration_seconds": round(legacy_duration, 6),
                "legacy_peak_tracemalloc_bytes": legacy_peak,
                "planner_boundary_scan_bytes": plan.boundary_scan_bytes,
                "planner_validation_bytes": plan.validation_bytes,
                "planner_segment_rows_consulted": plan.segment_rows_consulted,
                "planner_duration_seconds": round(planner_duration, 6),
                "planner_peak_tracemalloc_bytes": planner_peak,
            },
            sort_keys=True,
        )
    )
