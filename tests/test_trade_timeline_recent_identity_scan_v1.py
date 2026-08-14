from __future__ import annotations

import json
import os
import stat
import tracemalloc
from pathlib import Path

import pytest

import trade_timeline_validator as validator


TRADE_ID = "RECENT-IDENTITY-1"


def _line(**updates):
    row = {
        "trade_id": TRADE_ID,
        "trade_uuid": "UUID-RECENT-1",
        "lifecycle_id": "LIFE-RECENT-1",
        "event_type": "POSITION_OPEN",
        "timestamp": "2026-08-14T12:00:00Z",
    }
    row.update(updates)
    return row


def _write_lines(path: Path, rows, *, final_newline: bool = True) -> None:
    with path.open("wb") as handle:
        for index, row in enumerate(rows):
            raw = row if isinstance(row, bytes) else json.dumps(row, ensure_ascii=False).encode("utf-8")
            handle.write(raw)
            if final_newline or index < len(rows) - 1:
                handle.write(b"\n")


def _read(path: Path, *, cursor: str | None = None):
    metadata = validator._new_reader_metadata()
    rows = list(validator._read_path(path, metadata, scan_cursor=cursor))
    return rows, metadata


def _registry(path: Path, *, closed: bool = False) -> None:
    row = {
        "trade_id": TRADE_ID,
        "trade_uuid": "UUID-RECENT-1",
        "lifecycle_id": "LIFE-RECENT-1",
        "registry_id": "REG-RECENT-1",
        "status": "CLOSED" if closed else "OPEN",
        "opened_at": "2026-08-14T11:59:00Z",
        "closed_at": "2026-08-14T12:10:00Z" if closed else None,
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    path.write_text(json.dumps(row), encoding="utf-8")


def test_reverse_reader_returns_tail_in_chronological_order_and_complete_coverage(tmp_path):
    source = tmp_path / "timeline.jsonl"
    expected = [_line(event_id=f"E-{index}", timestamp=f"2026-08-14T12:00:{index:02d}Z") for index in range(5)]
    _write_lines(source, expected)

    rows, metadata = _read(source)

    assert rows == expected
    assert metadata["direction"] == "REVERSE"
    assert metadata["coverage_complete"] is True
    assert metadata["conclusive"] is True
    assert metadata["stop_reason"] == "START_OF_SNAPSHOT"
    assert metadata["records_examined"] == metadata["valid_lines"] == 5
    assert metadata["time_range_scanned"] == {
        "oldest": "2026-08-14T12:00:00+00:00",
        "newest": "2026-08-14T12:00:04+00:00",
    }


def test_recent_trade_is_found_after_more_than_64_mib_noise_with_bounded_memory(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    noise_line = b'{"trade_id":"OTHER","event_type":"NOISE","padding":"xxxxxxxxxxxxxxxx"}\n'
    chunk = noise_line * 16_384
    with source.open("wb") as handle:
        target_size = validator.JSONL_MAX_BYTES + (2 * 1024 * 1024)
        while handle.tell() <= target_size:
            handle.write(chunk)
        handle.write(json.dumps(_line(event_id="RECENT-AT-EOF")).encode("utf-8") + b"\n")
    _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))

    tracemalloc.start()
    report = validator.validate_trade_timeline(TRADE_ID)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    timeline = report["components"]["timeline"]
    assert source.stat().st_size > validator.JSONL_MAX_BYTES
    assert timeline["records"] == 1
    assert any(item.get("event_id") == "RECENT-AT-EOF" for item in report["events_found"])
    assert timeline["bytes_scanned"] <= validator.JSONL_MAX_BYTES
    assert timeline["records_examined"] <= validator.JSONL_MAX_VALID_LINES
    assert timeline["source_size_bytes"] == source.stat().st_size
    assert timeline["partial"] is True
    assert report["conclusive"] is False
    assert peak < 192 * 1024 * 1024
    print(json.dumps({
        "source_size_bytes": timeline["source_size_bytes"],
        "bytes_scanned": timeline["bytes_scanned"],
        "records_examined": timeline["records_examined"],
        "matched_records": timeline["records"],
        "peak_tracemalloc_bytes": peak,
    }, sort_keys=True))


def test_cursor_continues_same_snapshot_until_old_trade_is_found(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    old = _line(event_id="OLD-TARGET", timestamp="2026-08-14T11:59:10Z")
    noise = [
        {"trade_id": "OTHER", "event_type": "NOISE", "padding": "x" * 48, "sequence": index}
        for index in range(18)
    ]
    _write_lines(source, [old, *noise])
    _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 420)

    report = validator.validate_trade_timeline(TRADE_ID)
    snapshot_eof = report["coverage"]["sources"]["timeline"]["snapshot_eof"]
    for _ in range(10):
        if any(item.get("event_id") == "OLD-TARGET" for item in report["events_found"]):
            break
        cursor = report["coverage"]["sources"]["timeline"].get("next_scan_cursor")
        assert cursor
        report = validator.validate_trade_timeline(TRADE_ID, scan_cursor=cursor)
        assert report["coverage"]["sources"]["timeline"]["snapshot_eof"] == snapshot_eof
        assert report["conclusive"] is False

    assert any(item.get("event_id") == "OLD-TARGET" for item in report["events_found"])
    assert report["conclusive"] is False


def test_old_trade_without_timestamp_outside_recent_page_is_non_conclusive(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    old_without_timestamp = _line(event_id="OLD-NO-TIME")
    old_without_timestamp.pop("timestamp")
    noise = [
        {"trade_id": "OTHER", "event_type": "NOISE", "padding": "x" * 48, "sequence": index}
        for index in range(18)
    ]
    _write_lines(source, [old_without_timestamp, *noise])
    _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 420)

    report = validator.validate_trade_timeline(TRADE_ID)

    assert report["components"]["timeline"]["records"] == 0
    assert report["coverage"]["sources"]["timeline"]["partial"] is True
    assert report["conclusive"] is False
    assert report["coverage"]["sources"]["timeline"]["evidence_status"] == "NOT_FOUND_IN_SCANNED_REGION"


def test_singleton_duplicate_outside_recent_page_cannot_look_conclusive(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    older_duplicate = _line(event_id="DUPLICATE-OLD", event_type="POSITION_OPEN")
    noise = [
        {"trade_id": "OTHER", "event_type": "NOISE", "padding": "x" * 48, "sequence": index}
        for index in range(18)
    ]
    recent = _line(event_id="DUPLICATE-RECENT", event_type="POSITION_OPEN")
    _write_lines(source, [older_duplicate, *noise, recent])
    _registry(tmp_path / "trade_registry.json")
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 420)

    report = validator.validate_trade_timeline(TRADE_ID)

    assert report["components"]["timeline"]["records"] == 1
    assert report["events_duplicated"] == []
    assert report["conclusive"] is False
    assert report["coverage"]["sources"]["timeline"]["next_scan_cursor"]


def test_stale_cursor_after_truncate_is_controlled_source_change(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    _write_lines(source, [_line(event_id=f"E-{index}", padding="x" * 80) for index in range(8)])
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 256)
    _rows, first = _read(source)
    cursor = first["next_scan_cursor"]
    source.write_bytes(b'{}\n')

    rows, metadata = _read(source, cursor=cursor)

    assert rows == []
    assert metadata["coverage_complete"] is False
    assert metadata["conclusive"] is False
    assert metadata["stop_reason"] == "SOURCE_CHANGED"
    assert metadata["evidence_status"] == "SOURCE_CHANGED"


def test_invalid_and_cross_source_cursors_are_rejected(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    other = tmp_path / "history_events.jsonl"
    _write_lines(source, [_line(padding="x" * 100), _line(event_id="TAIL")])
    _write_lines(other, [_line()])
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 128)
    _rows, metadata = _read(source)

    with pytest.raises(ValueError, match="invalid scan cursor"):
        _read(source, cursor="not-a-cursor")
    with pytest.raises(ValueError, match="another source"):
        _read(other, cursor=metadata["next_scan_cursor"])


def test_unanchored_reused_trade_id_cannot_promote_historical_strong_ids():
    context = validator.new_correlation_context("REUSED-LOGICAL-ID")
    historical = {
        "trade_id": "REUSED-LOGICAL-ID",
        "lifecycle_id": "OLD-LIFECYCLE",
        "event_type": "POSITION_OPEN",
    }
    unrelated_followup = {
        "lifecycle_id": "OLD-LIFECYCLE",
        "event_type": "LIVE_TRADE_CLOSED",
    }

    assert validator.correlate_source_records("timeline", [historical], context) == [historical]
    assert "OLD-LIFECYCLE" not in context.trusted.get("lifecycle", set())
    assert validator.correlate_source_records("timeline", [unrelated_followup], context) == []
    target = validator.target_identity_from_context(context)
    assert target.registry_anchored is False
    assert target.ambiguous is True


def test_registry_anchor_promotes_strong_identity_and_not_symbol_side_collision():
    context = validator.new_correlation_context(TRADE_ID)
    registry_row = {
        "trade_id": TRADE_ID,
        "registry_id": "REG-1",
        "lifecycle_id": "LIFE-1",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    assert validator.correlate_source_records("registry", [registry_row], context) == [registry_row]
    by_lifecycle = {"lifecycle_id": "LIFE-1", "event_type": "POSITION_OPEN"}
    collision = {"symbol": "BTCUSDT", "side": "LONG", "event_type": "POSITION_OPEN"}
    assert validator.correlate_source_records("timeline", [by_lifecycle], context) == [by_lifecycle]
    assert validator.correlate_source_records("timeline", [collision], context) == []
    assert validator.target_identity_from_context(context).registry_anchored is True


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_utf8_multibyte_crossing_tiny_blocks_and_newline_styles(tmp_path, monkeypatch, newline):
    source = tmp_path / "timeline.jsonl"
    expected = _line(note="ação-ç-漢字", padding="z" * 90)
    source.write_bytes(json.dumps(expected, ensure_ascii=False).encode("utf-8") + newline)
    monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", 7)

    rows, metadata = _read(source)

    assert rows == [expected]
    assert metadata["invalid_lines"] == 0
    assert metadata["coverage_complete"] is True


def test_line_larger_than_block_is_reconstructed_but_line_larger_than_page_is_limited(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    expected = _line(padding="x" * 300)
    _write_lines(source, [expected])
    monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", 16)
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 1024)
    rows, metadata = _read(source)
    assert rows == [expected]
    assert metadata["coverage_complete"] is True

    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", 64)
    rows, metadata = _read(source)
    assert rows == []
    assert metadata["bytes_scanned"] <= 64
    assert metadata["stop_reason"] == "LINE_EXCEEDS_BYTE_BUDGET"
    assert metadata["coverage_complete"] is False
    cursor = metadata.get("next_scan_cursor")
    for _ in range(16):
        if not cursor:
            break
        rows, metadata = _read(source, cursor=cursor)
        assert rows == []
        assert metadata["coverage_complete"] is False
        cursor = metadata.get("next_scan_cursor")
    assert cursor is None
    assert metadata["conclusive"] is False


def test_append_after_snapshot_is_benign_and_visible_only_on_next_read(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    initial = [_line(event_id="INITIAL")]
    appended = _line(event_id="APPENDED")
    _write_lines(source, initial)
    initial_size = source.stat().st_size
    real_open = Path.open
    appended_once = False

    class AppendAfterFirstRead:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            return self

        def __exit__(self, *args):
            return self._handle.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self._handle, name)

        def read(self, size=-1):
            nonlocal appended_once
            data = self._handle.read(size)
            if not appended_once:
                appended_once = True
                with real_open(source, "ab") as writer:
                    writer.write(json.dumps(appended).encode("utf-8") + b"\n")
            return data

    def open_with_append(path, *args, **kwargs):
        handle = real_open(path, *args, **kwargs)
        if path == source and args and args[0] == "rb":
            return AppendAfterFirstRead(handle)
        return handle

    monkeypatch.setattr(Path, "open", open_with_append)
    first_rows, first_metadata = _read(source)
    second_rows, _second_metadata = _read(source)

    assert first_rows == initial
    assert first_metadata["snapshot_eof"] == initial_size
    assert first_metadata["coverage_complete"] is True
    assert second_rows == initial + [appended]


def test_truncate_replacement_and_disappearing_path_are_source_changes(tmp_path, monkeypatch):
    source = tmp_path / "timeline.jsonl"
    _write_lines(source, [_line(event_id="EVIDENCE")])
    real_fstat = os.fstat
    fstat_calls = 0

    def shrinking_fstat(descriptor):
        nonlocal fstat_calls
        fstat_calls += 1
        current = real_fstat(descriptor)
        if fstat_calls >= 2:
            changed = list(current)
            changed[6] = max(0, current.st_size - 1)
            return os.stat_result(changed)
        return current

    monkeypatch.setattr(validator.os, "fstat", shrinking_fstat)
    _rows, metadata = _read(source)
    assert metadata["stop_reason"] == "SOURCE_CHANGED"
    assert metadata["coverage_complete"] is False

    monkeypatch.setattr(validator.os, "fstat", real_fstat)
    real_lstat = Path.lstat
    lstat_calls = 0

    def replaced_lstat(path):
        nonlocal lstat_calls
        current = real_lstat(path)
        if path == source:
            lstat_calls += 1
            if lstat_calls >= 2:
                changed = list(current)
                changed[1] = current.st_ino + 1
                return os.stat_result(changed)
        return current

    monkeypatch.setattr(Path, "lstat", replaced_lstat)
    _rows, metadata = _read(source)
    assert metadata["stop_reason"] == "SOURCE_CHANGED"

    lstat_calls = 0

    def missing_lstat(path):
        nonlocal lstat_calls
        current = real_lstat(path)
        if path == source:
            lstat_calls += 1
            if lstat_calls >= 2:
                raise FileNotFoundError(path)
        return current

    monkeypatch.setattr(Path, "lstat", missing_lstat)
    _rows, metadata = _read(source)
    assert metadata["stop_reason"] == "SOURCE_CHANGED"
    assert metadata["conclusive"] is False


def test_symlink_and_non_regular_sources_are_rejected(tmp_path, monkeypatch):
    regular = tmp_path / "regular.jsonl"
    _write_lines(regular, [_line()])
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(regular)
    except (OSError, NotImplementedError):
        real_lstat = Path.lstat

        def fake_symlink(path):
            if path == link:
                current = real_lstat(regular)
                values = list(current)
                values[0] = stat.S_IFLNK | 0o777
                return os.stat_result(values)
            return real_lstat(path)

        monkeypatch.setattr(Path, "lstat", fake_symlink)
    with pytest.raises(ValueError, match="regular non-symlink"):
        _read(link)

    directory = tmp_path / "directory.jsonl"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular non-symlink"):
        _read(directory)


def test_partial_without_identity_is_explicitly_non_conclusive():
    sources = {name: [] for name in validator.COMPONENTS}
    sources["timeline"] = {
        "records": [],
        "_reader_metadata": {
            "partial": True,
            "coverage_limited": True,
            "coverage_complete": False,
            "conclusive": False,
            "direction": "REVERSE",
            "stop_reason": "BYTE_BUDGET",
            "evidence_status": "NOT_FOUND_IN_SCANNED_REGION",
        },
    }

    report = validator.validate_trade_timeline("ABSENT", sources=sources)

    assert report["result"] == "FAIL"
    assert report["conclusive"] is False
    assert report["evidence_status"] == "NOT_FOUND_IN_SCANNED_REGION"
    assert report["coverage"]["sources"]["timeline"]["coverage_complete"] is False


def test_reader_source_avoids_unbounded_materialization_apis():
    source = Path(validator.__file__).read_text(encoding="utf-8")
    reader_source = source[source.index("def _read_path("):source.index("def _default_reader(")]
    default_source = source[source.index("def _default_reader("):source.index("def build_default_sources(")]
    assert ".read_text(" not in reader_source
    assert ".readlines(" not in reader_source
    assert ".splitlines(" not in reader_source
    assert "candidates.append" not in default_source
