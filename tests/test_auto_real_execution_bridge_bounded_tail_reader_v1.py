from __future__ import annotations

import ast
import copy
import inspect
import json
import os
import stat
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
BLOCK_BYTES = 64 * 1024
READER_FUNCTIONS = {
    "_arb_v1_tail_lexical_path",
    "_arb_v1_tail_stat_value",
    "_arb_v1_tail_source_changed",
    "_arb_v1_count_events_snapshot",
    "_arb_v1_read_events_page",
    "_arb_v1_read_events",
}
_READER_CODE = None


def _load_reader(namespace):
    global _READER_CODE
    if _READER_CODE is None:
        tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
        functions = {
            node.name: copy.deepcopy(node)
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in READER_FUNCTIONS
        }
        assert set(functions) == READER_FUNCTIONS
        module = ast.Module(
            body=sorted(functions.values(), key=lambda node: node.lineno),
            type_ignores=[],
        )
        ast.fix_missing_locations(module)
        _READER_CODE = compile(module, str(MAIN), "exec")
    exec(_READER_CODE, namespace)
    return namespace


@pytest.fixture()
def reader(tmp_path):
    path = tmp_path / "data" / "auto_real_execution_bridge_v1_events.jsonl"
    path.parent.mkdir(parents=True)
    namespace = {
        "json": json,
        "os": os,
        "stat": stat,
        "Path": Path,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE": path,
        "AUTO_REAL_EXECUTION_BRIDGE_V1_TAIL_BLOCK_BYTES": BLOCK_BYTES,
    }
    return _load_reader(namespace)


def _event(index, event="PREVIEW", **updates):
    row = {
        "event": event,
        "status": event,
        "signal_id": f"SIGNAL-{index}",
        "trade_id": f"TRADE-{index}",
        "symbol": "BTCUSDT",
        "generated_at": f"2026-08-13T12:{index % 60:02d}:00-03:00",
    }
    row.update(updates)
    return row


def _write_rows(path, rows, *, final_newline=True, newline="\n"):
    payload = newline.join(
        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        for row in rows
    )
    if rows and final_newline:
        payload += newline
    path.write_bytes(payload.encode("utf-8"))


def _legacy_rows(path, limit=20):
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                rows.append({"raw": line})
    return rows[-int(limit or 20) :]


def test_small_file_preserves_legacy_rows_and_public_shape(reader):
    rows = [_event(index) for index in range(5)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    page = reader["_arb_v1_read_events_page"](path, limit=20)
    result = reader["_arb_v1_read_events"](limit=20)

    assert page["rows"] == _legacy_rows(path, 20) == rows
    assert result == {
        "ok": True,
        "count": 5,
        "returned_count": 5,
        "rows": rows,
    }
    assert isinstance(result, dict)
    assert isinstance(result["rows"], list)
    assert list(inspect.signature(reader["_arb_v1_read_events"]).parameters) == [
        "limit"
    ]


def test_more_records_than_limit_returns_exact_chronological_tail(reader):
    rows = [_event(index) for index in range(101)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    result = reader["_arb_v1_read_events"](limit=7)

    assert result == {
        "ok": True,
        "count": 101,
        "returned_count": 7,
        "rows": rows[-7:],
    }
    assert [row["signal_id"] for row in result["rows"]] == [
        f"SIGNAL-{index}" for index in range(94, 101)
    ]


def test_large_fixture_reads_only_small_tail_region(reader):
    rows = [_event(index, padding="x" * 512) for index in range(25_000)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    page = reader["_arb_v1_read_events_page"](path, limit=100)

    assert page["rows"] == rows[-100:]
    assert page["bytes_read"] < page["source_size_bytes"] // 10
    assert page["count_bytes_read"] == page["source_size_bytes"]
    assert page["total_count"] == len(rows)
    assert page["tail_limited"] is True
    assert page["records_examined"] == 100


def test_utf8_multibyte_crosses_blocks_after_byte_reassembly(reader):
    repeated = "ação🚀fim" * 200
    rows = [_event(1, text="início"), _event(2, text=repeated)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)
    data = path.read_bytes()
    rocket_start = data.index("🚀".encode("utf-8"))
    rocket_end = rocket_start + len("🚀".encode("utf-8"))
    block_size = next(
        size
        for size in range(2, 64)
        if any(
            rocket_start < len(data) - step * size < rocket_end
            for step in range(1, len(data) // size + 1)
        )
    )

    page = reader["_arb_v1_read_events_page"](
        path,
        limit=2,
        block_size=block_size,
    )

    assert path.stat().st_size > block_size * 2
    assert page["rows"] == rows


def test_line_larger_than_two_blocks_and_exact_limit_boundary(reader):
    rows = [
        _event(0),
        _event(1, text="á🚀" * 1_000),
        _event(2),
        _event(3),
    ]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    page = reader["_arb_v1_read_events_page"](path, limit=3, block_size=47)

    assert len(json.dumps(rows[1], ensure_ascii=False).encode("utf-8")) > 2 * 47
    assert page["rows"] == rows[-3:]
    assert page["records_examined"] == 3
    assert page["tail_limited"] is True


@pytest.mark.parametrize("final_newline", [True, False])
def test_valid_final_json_is_accepted_with_or_without_newline(reader, final_newline):
    rows = [_event(1), _event(2, text="ação🚀")]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows, final_newline=final_newline)

    page = reader["_arb_v1_read_events_page"](path, limit=2)

    assert page["rows"] == rows
    assert page["incomplete_last_line"] is False
    assert page["total_count"] == 2
    result = reader["_arb_v1_read_events"](limit=1)
    assert result["count"] == 2
    assert result["returned_count"] == 1
    assert result["rows"] == rows[-1:]


def test_crlf_preserves_existing_whitespace_tolerance(reader):
    rows = [_event(1), _event(2)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows, newline="\r\n")

    assert reader["_arb_v1_read_events_page"](path, limit=2)["rows"] == rows


def test_invalid_unterminated_final_fragment_is_ignored(reader):
    rows = [_event(1), _event(2)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)
    with path.open("ab") as handle:
        handle.write(b'{"event":"LIVE_SENT","payload":')

    page = reader["_arb_v1_read_events_page"](path, limit=20)

    assert page["rows"] == rows
    assert page["records_examined"] == 3
    assert page["incomplete_last_line"] is True
    assert page["total_count"] == 3

    result = reader["_arb_v1_read_events"](limit=20)
    assert result["count"] == 3
    assert result["returned_count"] == 2
    assert result["rows"] == rows


def test_complete_invalid_json_preserves_legacy_raw_record(reader):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    path.write_bytes(
        (
            json.dumps(_event(1), separators=(",", ":"))
            + "\n{not-json}\n"
            + json.dumps(_event(2), separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
    )

    page = reader["_arb_v1_read_events_page"](path, limit=3, block_size=37)

    assert page["rows"] == [_event(1), {"raw": "{not-json}"}, _event(2)]
    assert page["total_count"] == 3
    result = reader["_arb_v1_read_events"](limit=2)
    assert result["count"] == 3
    assert result["returned_count"] == 2


def test_count_skips_blank_lines_like_legacy_reader(reader):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    path.write_bytes(
        (
            "\n  \r\n"
            + json.dumps(_event(1), separators=(",", ":"))
            + "\n\t\n{not-json}\n"
        ).encode("utf-8")
    )

    result = reader["_arb_v1_read_events"](limit=1)

    assert result["count"] == 2
    assert result["returned_count"] == 1
    assert result["rows"] == [{"raw": "{not-json}"}]


def test_invalid_utf8_complete_line_preserves_public_failure_shape(reader):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, [_event(1)])
    with path.open("ab") as handle:
        handle.write(b"\xff\n")

    result = reader["_arb_v1_read_events"](limit=2)

    assert result["ok"] is False
    assert result["rows"] == []
    assert "error" in result


def test_missing_empty_and_none_configured_file(reader):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]

    empty_result = {"ok": True, "count": 0, "returned_count": 0, "rows": []}
    assert reader["_arb_v1_read_events"]() == empty_result
    path.touch()
    assert reader["_arb_v1_read_events"]() == empty_result
    reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"] = None
    assert reader["_arb_v1_read_events"]() == empty_result


def test_symlink_and_non_regular_file_are_rejected(reader, tmp_path, monkeypatch):
    original = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    target = tmp_path / "outside.jsonl"
    _write_rows(target, [_event(1)])
    link = original.parent / "bridge-link.jsonl"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        real_lstat = Path.lstat

        def symlink_lstat(path):
            if path == link:
                return os.stat_result(
                    (stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0)
                )
            return real_lstat(path)

        monkeypatch.setattr(Path, "lstat", symlink_lstat)

    reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"] = link
    symlink_result = reader["_arb_v1_read_events"]()
    assert symlink_result["ok"] is False
    assert "SYMLINK_REJECTED" in symlink_result["error"]

    directory = original.parent / "bridge-directory"
    directory.mkdir()
    reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"] = directory
    directory_result = reader["_arb_v1_read_events"]()
    assert directory_result["ok"] is False
    assert "NOT_REGULAR_FILE" in directory_result["error"]


def test_alternate_and_traversal_paths_are_rejected(reader):
    configured = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    alternate = configured.parent / "alternate.jsonl"
    _write_rows(alternate, [_event(1)])

    with pytest.raises(ValueError, match="UNEXPECTED_PATH"):
        reader["_arb_v1_read_events_page"](alternate)

    traversal = configured.parent / "nested" / ".." / configured.name
    assert reader["_arb_v1_tail_lexical_path"](traversal) == reader[
        "_arb_v1_tail_lexical_path"
    ](configured)
    with pytest.raises(ValueError, match="UNEXPECTED_PATH"):
        reader["_arb_v1_read_events_page"](traversal)


def test_concurrent_append_returns_initial_snapshot_then_next_read_sees_event(
    reader,
    monkeypatch,
):
    rows = [_event(1), _event(2)]
    appended = _event(3, event="LIVE_SENT")
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)
    initial_size = path.stat().st_size
    real_fdopen = os.fdopen
    appended_once = False

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
            nonlocal appended_once
            data = self._handle.read(size)
            if not appended_once:
                appended_once = True
                with path.open("ab") as writer:
                    writer.write(
                        (json.dumps(appended, separators=(",", ":")) + "\n").encode(
                            "utf-8"
                        )
                    )
            return data

    monkeypatch.setattr(
        os,
        "fdopen",
        lambda *args, **kwargs: AppendAfterRead(real_fdopen(*args, **kwargs)),
    )

    first = reader["_arb_v1_read_events_page"](path, limit=3)
    second = reader["_arb_v1_read_events_page"](path, limit=3)

    assert first["source_size_bytes"] == initial_size
    assert first["rows"] == rows
    assert first["total_count"] == 2
    assert second["rows"] == rows + [appended]
    assert second["total_count"] == 3


def test_truncate_during_read_is_detected_and_public_failure_is_controlled(
    reader,
    monkeypatch,
):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, [_event(index) for index in range(20)])
    real_fstat = os.fstat
    calls = 0

    def shrinking_fstat(descriptor):
        nonlocal calls
        calls += 1
        snapshot = real_fstat(descriptor)
        if calls % 2 == 0:
            changed = list(snapshot)
            changed[6] = max(0, snapshot.st_size - 1)
            return os.stat_result(changed)
        return snapshot

    monkeypatch.setattr(os, "fstat", shrinking_fstat)

    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        reader["_arb_v1_read_events_page"](path, limit=5)
    result = reader["_arb_v1_read_events"](limit=5)
    assert result["ok"] is False
    assert result["rows"] == []


def test_replacement_during_read_is_detected_and_public_failure_is_controlled(
    reader,
    monkeypatch,
):
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, [_event(index) for index in range(3)])
    real_lstat = Path.lstat
    calls = 0

    def replacing_lstat(source):
        nonlocal calls
        snapshot = real_lstat(source)
        if source == path:
            calls += 1
            if calls % 2 == 0:
                changed = list(snapshot)
                changed[1] = snapshot.st_ino + 1
                return os.stat_result(changed)
        return snapshot

    monkeypatch.setattr(Path, "lstat", replacing_lstat)

    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        reader["_arb_v1_read_events_page"](path, limit=2)
    result = reader["_arb_v1_read_events"](limit=2)
    assert result["ok"] is False
    assert result["rows"] == []


def test_limit_none_zero_one_negative_and_above_default_preserve_old_rows(reader):
    rows = [_event(index) for index in range(30)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    for limit in (None, 0, 1, -1, -5, 35):
        result = reader["_arb_v1_read_events"](limit=limit)
        assert result["ok"] is True
        assert result["rows"] == _legacy_rows(path, limit)
        assert result["count"] == len(rows)
        assert result["returned_count"] == len(result["rows"])

    with pytest.raises(ValueError):
        reader["_arb_v1_read_events"](limit="not-an-integer")


def test_all_critical_event_types_remain_visible_without_post_filters(reader):
    event_types = ["LIVE_SENT", "BLOCKED", "ERROR", "PREVIEW", "NOT_ELIGIBLE"]
    rows = [_event(index, event=event) for index, event in enumerate(event_types)]
    path = reader["AUTO_REAL_EXECUTION_BRIDGE_V1_EVENTS_FILE"]
    _write_rows(path, rows)

    result = reader["_arb_v1_read_events"](limit=5)

    assert result["rows"] == rows
    assert result["count"] == len(rows)
    assert result["returned_count"] == len(rows)
    assert [row["event"] for row in result["rows"]] == event_types


def test_reader_path_has_no_integral_file_read_or_automatic_logging(reader):
    source = "\n".join(
        inspect.getsource(reader[name])
        for name in (
            "_arb_v1_read_events_page",
            "_arb_v1_read_events",
        )
    )

    assert ".readlines(" not in source
    assert ".read_text(" not in source
    assert "mmap" not in source
    assert "for line in f" not in source
    assert "print(" not in source
    assert "_arb_v1_append_event" not in source


def test_count_pass_is_streaming_constant_memory_and_does_not_parse_json(reader):
    source = inspect.getsource(reader["_arb_v1_count_events_snapshot"])

    assert "json.loads" not in source
    assert ".read()" not in source
    assert ".readlines(" not in source
    assert ".read_text(" not in source
    assert "chunks" not in source
    assert "rows" not in source
    assert "read_size = min(block_size, snapshot_size - cursor)" in source
