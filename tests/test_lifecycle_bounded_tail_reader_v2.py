from __future__ import annotations

import importlib
import inspect
import json
import os
import stat
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    original = sys.modules.get("journal_manager")
    sys.modules.pop("journal_manager", None)
    module = importlib.import_module("journal_manager")
    try:
        yield module
    finally:
        sys.modules.pop("journal_manager", None)
        if original is not None:
            sys.modules["journal_manager"] = original


def _event(index: int, **updates):
    row = {
        "uid": f"event-{index}",
        "epoch": float(index),
        "event": "TRADE_OPENED",
        "trade_id": f"trade-{index}",
        "bot": "FALCON",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    row.update(updates)
    return row


def _write_rows(path: Path, rows, *, final_newline: bool = True):
    payload = "\n".join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        for row in rows
    )
    if final_newline and rows:
        payload += "\n"
    path.write_bytes(payload.encode("utf-8"))


def _legacy_valid_tail(path: Path, limit: int):
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    return [json.loads(line.strip()) for line in lines if line.strip()]


def test_small_file_matches_legacy_reader_and_public_api(journal):
    rows = [_event(index) for index in range(8)]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    expected = _legacy_valid_tail(journal.LIFECYCLE_FILE, 5)
    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=5)

    assert page["records"] == expected
    assert journal.load_lifecycle_events(limit=5) == expected
    assert isinstance(journal.load_lifecycle_events(limit=5), list)
    assert list(inspect.signature(journal.load_lifecycle_events).parameters) == ["limit"]
    assert page == {
        "records": expected,
        "source_size_bytes": journal.LIFECYCLE_FILE.stat().st_size,
        "bytes_read": journal.LIFECYCLE_FILE.stat().st_size,
        "records_returned": 5,
        "records_examined": 5,
        "partial": True,
        "incomplete_last_line": False,
    }


def test_default_returns_exactly_last_ten_thousand_in_chronological_order(journal):
    rows = [_event(index) for index in range(10_025)]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    actual = journal.load_lifecycle_events()

    assert len(actual) == journal.LIFECYCLE_MAX_READ == 10_000
    assert [row["uid"] for row in actual[:2]] == ["event-25", "event-26"]
    assert [row["uid"] for row in actual[-2:]] == ["event-10023", "event-10024"]
    assert [row["epoch"] for row in actual] == sorted(row["epoch"] for row in actual)
    assert journal.load_lifecycle_events(limit=10_025) == rows


def test_limit_contract_none_zero_one_negative_and_above_default(journal):
    rows = [_event(index) for index in range(5)]
    _write_rows(journal.LIFECYCLE_FILE, rows)
    journal.LIFECYCLE_MAX_READ = 3

    assert journal.load_lifecycle_events(limit=None) == rows[-3:]
    assert journal.load_lifecycle_events(limit=0) == rows[-3:]
    assert journal.load_lifecycle_events(limit=1) == rows[-1:]
    assert journal.load_lifecycle_events(limit=5) == rows
    with pytest.raises(ValueError, match="limit must be positive"):
        journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=-1)
    assert journal._read_lifecycle_jsonl_tail(journal.LIFECYCLE_FILE, limit=-1) == []
    assert journal.load_lifecycle_events(limit=-1) == []


def test_large_fixture_reads_only_a_small_tail_region(journal):
    rows = [_event(index, padding="x" * 512) for index in range(25_000)]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=25)

    assert len(page["records"]) == 25
    assert page["records"][0]["uid"] == "event-24975"
    assert page["bytes_read"] < page["source_size_bytes"] // 10
    assert page["partial"] is True


def test_utf8_multibyte_split_between_blocks_is_decoded_after_reassembly(journal):
    repeated_text = "ação🚀fim" * 200
    rows = [_event(1, text="início"), _event(2, text=repeated_text)]
    _write_rows(journal.LIFECYCLE_FILE, rows)
    data = journal.LIFECYCLE_FILE.read_bytes()
    rocket_start = data.index("🚀".encode("utf-8"))
    rocket_end = rocket_start + len("🚀".encode("utf-8"))
    block_size = next(
        size
        for size in range(2, 64)
        if any(
            rocket_start < len(data) - step * size < rocket_end
            for step in range(1, (len(data) // size) + 1)
        )
    )

    page = journal._read_lifecycle_jsonl_tail_page(
        journal.LIFECYCLE_FILE,
        limit=2,
        block_size=block_size,
    )

    assert journal.LIFECYCLE_FILE.stat().st_size > block_size * 2
    assert [row["text"] for row in page["records"]] == ["início", repeated_text]


def test_line_larger_than_block_size_is_reassembled(journal):
    rows = [_event(1), _event(2, text="á" * 10_000)]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    page = journal._read_lifecycle_jsonl_tail_page(
        journal.LIFECYCLE_FILE,
        limit=1,
        block_size=31,
    )

    assert len(json.dumps(rows[-1], ensure_ascii=False).encode("utf-8")) > 2 * 31
    assert page["records"] == [rows[-1]]
    assert len(page["records"][0]["text"]) == 10_000


@pytest.mark.parametrize("final_newline", [True, False])
def test_complete_final_json_is_returned_with_or_without_newline(journal, final_newline):
    rows = [_event(1), _event(2)]
    _write_rows(journal.LIFECYCLE_FILE, rows, final_newline=final_newline)

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)

    assert page["records"] == rows
    assert page["incomplete_last_line"] is False
    assert page["partial"] is False


@pytest.mark.parametrize("final_newline", [True, False])
def test_single_valid_json_line_is_returned_with_or_without_newline(
    journal,
    final_newline,
):
    row = _event(1, text="ação🚀")
    _write_rows(journal.LIFECYCLE_FILE, [row], final_newline=final_newline)

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=1)

    assert page["records"] == [row]
    assert page["partial"] is False
    assert page["incomplete_last_line"] is False


def test_crlf_preserves_legacy_whitespace_tolerance(journal):
    rows = [_event(1), _event(2)]
    payload = "\r\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    journal.LIFECYCLE_FILE.write_bytes((payload + "\r\n").encode("utf-8"))

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)

    assert page["records"] == rows
    assert page["incomplete_last_line"] is False


def test_invalid_unterminated_final_fragment_is_ignored_only_once(journal):
    rows = [_event(1), _event(2)]
    _write_rows(journal.LIFECYCLE_FILE, rows)
    with journal.LIFECYCLE_FILE.open("ab") as handle:
        handle.write(b'{"uid":"interrupted","event":')

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=10)

    assert page["records"] == rows
    assert page["records_examined"] == 3
    assert page["records_returned"] == 2
    assert page["incomplete_last_line"] is True
    assert page["partial"] is True


def test_invalid_final_line_with_newline_preserves_legacy_raw_record(journal):
    _write_rows(journal.LIFECYCLE_FILE, [_event(1)])
    with journal.LIFECYCLE_FILE.open("ab") as handle:
        handle.write(b"{not-json}\n")

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)

    assert page["records"] == [_event(1), {"raw": "{not-json}"}]
    assert page["incomplete_last_line"] is False


def test_invalid_final_line_without_newline_is_treated_as_interrupted(journal):
    _write_rows(journal.LIFECYCLE_FILE, [_event(1)])
    with journal.LIFECYCLE_FILE.open("ab") as handle:
        handle.write(b"{not-json}")

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)

    assert page["records"] == [_event(1)]
    assert page["incomplete_last_line"] is True
    assert page["partial"] is True


def test_invalid_utf8_preserves_legacy_fail_open_behavior(journal):
    _write_rows(journal.LIFECYCLE_FILE, [_event(1)])
    with journal.LIFECYCLE_FILE.open("ab") as handle:
        handle.write(b"\xff\n")

    with pytest.raises(UnicodeDecodeError):
        journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)
    assert journal._read_lifecycle_jsonl_tail(journal.LIFECYCLE_FILE, limit=2) == []


def test_invalid_complete_json_line_preserves_legacy_raw_record(journal):
    first = json.dumps(_event(1), separators=(",", ":"))
    last = json.dumps(_event(2), separators=(",", ":"))
    journal.LIFECYCLE_FILE.write_bytes(
        (first + "\n{not-json}\n" + last + "\n").encode("utf-8")
    )

    page = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=3)

    assert page["records"] == [_event(1), {"raw": "{not-json}"}, _event(2)]
    assert page["records_examined"] == 3
    assert page["incomplete_last_line"] is False


def test_invalid_complete_json_as_first_window_line_is_not_a_fragment(journal):
    journal.LIFECYCLE_FILE.write_bytes(
        (
            "{not-json}\n"
            + json.dumps(_event(1), separators=(",", ":"))
            + "\n"
            + json.dumps(_event(2), separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    )

    page = journal._read_lifecycle_jsonl_tail_page(
        journal.LIFECYCLE_FILE,
        limit=3,
        block_size=37,
    )

    assert page["records"] == [{"raw": "{not-json}"}, _event(1), _event(2)]
    assert page["records_examined"] == 3


def test_exact_limit_boundary_reassembles_long_nth_line_without_prefix_fragment(journal):
    rows = [
        _event(0),
        _event(1, text="á🚀" * 500),
        _event(2),
        _event(3),
    ]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    page = journal._read_lifecycle_jsonl_tail_page(
        journal.LIFECYCLE_FILE,
        limit=3,
        block_size=47,
    )

    assert page["records"] == rows[-3:]
    assert page["records_examined"] == 3
    assert page["records_returned"] == 3
    assert page["partial"] is True


def test_missing_and_empty_files_preserve_empty_result(journal):
    journal.LIFECYCLE_FILE.unlink()
    missing = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE)
    assert missing["records"] == []
    assert missing["source_size_bytes"] == 0
    assert journal.load_lifecycle_events() == []

    journal.LIFECYCLE_FILE.touch()
    empty = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE)
    assert empty["records"] == []
    assert empty["bytes_read"] == 0
    assert empty["partial"] is False


def test_symlink_is_rejected_without_following_target(journal, tmp_path, monkeypatch):
    target = tmp_path / "outside.jsonl"
    _write_rows(target, [_event(1)])
    link = journal.DATA_DIR / "lifecycle-link.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        original_lstat = Path.lstat

        def fake_lstat(path):
            if path == link:
                return os.stat_result((stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0))
            return original_lstat(path)

        monkeypatch.setattr(Path, "lstat", fake_lstat)
    journal.LIFECYCLE_FILE = link

    with pytest.raises(ValueError, match="SYMLINK_REJECTED"):
        journal._read_lifecycle_jsonl_tail_page(link)
    assert journal._read_lifecycle_jsonl_tail(link) == []


def test_non_regular_file_is_rejected(journal):
    directory = journal.DATA_DIR / "lifecycle-directory"
    directory.mkdir()
    journal.LIFECYCLE_FILE = directory

    with pytest.raises(ValueError, match="NOT_REGULAR_FILE"):
        journal._read_lifecycle_jsonl_tail_page(directory)
    assert journal._read_lifecycle_jsonl_tail(directory) == []


def test_unexpected_regular_path_is_rejected_before_open(journal, tmp_path):
    outside = tmp_path / "outside-lifecycle.jsonl"
    _write_rows(outside, [_event(1)])

    with pytest.raises(ValueError, match="UNEXPECTED_PATH"):
        journal._read_lifecycle_jsonl_tail_page(outside)

    traversal = journal.LIFECYCLE_FILE.parent / "nested" / ".." / journal.LIFECYCLE_FILE.name
    assert journal._lifecycle_tail_lexical_path(traversal) == journal._lifecycle_tail_lexical_path(
        journal.LIFECYCLE_FILE
    )
    with pytest.raises(ValueError, match="UNEXPECTED_PATH"):
        journal._read_lifecycle_jsonl_tail_page(traversal)


def test_snapshot_detector_covers_truncate_and_replacement(journal, tmp_path):
    source = journal.LIFECYCLE_FILE
    replacement = tmp_path / "replacement.jsonl"
    _write_rows(source, [_event(1), _event(2)])
    _write_rows(replacement, [_event(9)])
    initial = source.stat()
    truncated = list(initial)
    truncated[6] = max(0, initial.st_size - 1)
    truncated = os.stat_result(truncated)
    appended = list(initial)
    appended[6] = initial.st_size + 100
    appended = os.stat_result(appended)
    before_open_append = list(initial)
    before_open_append[6] = max(0, initial.st_size - 1)
    before_open_append = os.stat_result(before_open_append)

    assert journal._lifecycle_tail_snapshot_changed(initial, initial, truncated, truncated)
    assert journal._lifecycle_tail_snapshot_changed(initial, initial, initial, replacement.stat())
    assert not journal._lifecycle_tail_snapshot_changed(initial, initial, appended, appended)
    assert not journal._lifecycle_tail_snapshot_changed(
        before_open_append,
        initial,
        appended,
        appended,
    )


def test_concurrent_append_returns_initial_eof_snapshot_and_next_read_sees_append(
    journal,
    monkeypatch,
):
    rows = [_event(1), _event(2)]
    appended_row = _event(3)
    _write_rows(journal.LIFECYCLE_FILE, rows)
    initial_size = journal.LIFECYCLE_FILE.stat().st_size
    real_fdopen = os.fdopen
    append_done = False

    class AppendAfterRead:
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
            nonlocal append_done
            data = self._handle.read(size)
            if not append_done:
                append_done = True
                with journal.LIFECYCLE_FILE.open("ab") as writer:
                    writer.write(
                        (json.dumps(appended_row, separators=(",", ":")) + "\n").encode(
                            "utf-8"
                        )
                    )
            return data

    monkeypatch.setattr(
        journal.os,
        "fdopen",
        lambda *args, **kwargs: AppendAfterRead(real_fdopen(*args, **kwargs)),
    )

    first = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=3)
    second = journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=3)

    assert append_done is True
    assert first["source_size_bytes"] == initial_size
    assert first["records"] == rows
    assert second["records"] == rows + [appended_row]


def test_concurrent_path_replacement_is_detected_and_fail_open_is_controlled(
    journal,
    monkeypatch,
):
    _write_rows(journal.LIFECYCLE_FILE, [_event(index) for index in range(3)])
    real_lstat = Path.lstat
    source_calls = 0

    def lstat_with_replacement(path):
        nonlocal source_calls
        snapshot = real_lstat(path)
        if path == journal.LIFECYCLE_FILE:
            source_calls += 1
            if source_calls % 2 == 0:
                changed = list(snapshot)
                changed[1] = snapshot.st_ino + 1
                return os.stat_result(changed)
        return snapshot

    monkeypatch.setattr(Path, "lstat", lstat_with_replacement)

    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=2)
    assert journal._read_lifecycle_jsonl_tail(journal.LIFECYCLE_FILE, limit=2) == []


def test_structural_change_signal_never_returns_a_potentially_incoherent_tail(
    journal,
    monkeypatch,
):
    _write_rows(journal.LIFECYCLE_FILE, [_event(index) for index in range(20)])
    real_fstat = os.fstat
    calls = 0

    def fstat_with_truncate_after_read(descriptor):
        nonlocal calls
        calls += 1
        snapshot = real_fstat(descriptor)
        if calls % 2 == 0:
            changed = list(snapshot)
            changed[6] = max(0, snapshot.st_size - 1)
            return os.stat_result(changed)
        return snapshot

    monkeypatch.setattr(journal.os, "fstat", fstat_with_truncate_after_read)

    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        journal._read_lifecycle_jsonl_tail_page(journal.LIFECYCLE_FILE, limit=5)
    assert journal._read_lifecycle_jsonl_tail(journal.LIFECYCLE_FILE, limit=5) == []


def test_lifecycle_projection_equivalence_for_open_closed_signal_and_blocked(journal):
    rows = [
        _event(1, trade_id="OPEN", event="SIGNAL_CREATED"),
        _event(2, trade_id="OPEN", event="TRADE_OPENED"),
        _event(3, trade_id="OPEN", event="TP50_HIT"),
        _event(4, trade_id="OPEN", event="BREAKEVEN"),
        _event(5, trade_id="CLOSED", event="TRADE_OPENED"),
        _event(6, trade_id="CLOSED", event="TRADE_CLOSED", result_pct=1.25),
        _event(7, trade_id="SIGNAL", event="SIGNAL_CREATED"),
        _event(8, trade_id="BLOCKED", event="SIGNAL_CREATED"),
        _event(9, trade_id="BLOCKED", event="TRADE_BLOCKED"),
    ]
    _write_rows(journal.LIFECYCLE_FILE, rows)

    loaded = journal.load_lifecycle_events(limit=100)
    lifecycles = {
        item["trade_id"]: item
        for item in journal.build_trade_lifecycles(loaded)
    }

    assert loaded == rows
    assert lifecycles["OPEN"]["status"] == "OPEN"
    assert lifecycles["OPEN"]["events"] == [
        "SIGNAL_CREATED",
        "TRADE_OPENED",
        "TP50_HIT",
        "BREAKEVEN",
    ]
    assert lifecycles["CLOSED"]["status"] == "CLOSED"
    assert lifecycles["CLOSED"]["result_pct"] == 1.25
    assert lifecycles["SIGNAL"]["status"] == "SIGNAL_ONLY"
    assert lifecycles["BLOCKED"]["status"] == "BLOCKED"


def test_lifecycle_path_contains_no_integral_reader(journal):
    source = "\n".join(
        inspect.getsource(function)
        for function in (
            journal._read_lifecycle_jsonl_tail_page,
            journal._read_lifecycle_jsonl_tail,
            journal.load_lifecycle_events,
        )
    )

    assert ".readlines(" not in source
    assert ".read_text(" not in source
    assert "mmap" not in source
