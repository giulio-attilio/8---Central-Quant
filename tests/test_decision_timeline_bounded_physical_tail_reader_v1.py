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
    "_counter_top_lines",
    "_read_physical_tail_lines_v1",
    "_read_jsonl_tail_v3",
    "_awe_extract_outcome_records",
    "_compact_decisionlog_block",
    "build_evolution_dashboard_v3",
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
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    namespace = {
        "json": json,
        "os": os,
        "stat": stat,
        "Path": Path,
        "_DECISION_TIMELINE_TAIL_BLOCK_BYTES": BLOCK_BYTES,
        "CENTRAL_DATA_DIR": data_dir,
        "CENTRAL_DECISION_LOG_FILE": data_dir / "decision_log.jsonl",
        "CENTRAL_TIMELINE_LOG_FILE": data_dir / "timeline.jsonl",
        "data_hora_sp_str": lambda: "13/08/2026 12:00:00",
    }
    return _load_reader(namespace)


def _write_physical_lines(path, lines, *, final_newline=True, newline=b"\n"):
    path = Path(path)
    payload = newline.join(
        line if isinstance(line, bytes) else str(line).encode("utf-8")
        for line in lines
    )
    if lines and final_newline:
        payload += newline
    path.write_bytes(payload)


def _json_line(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _legacy_v3(path, limit=200):
    try:
        source = Path(path)
        if not source.exists():
            return []
        lines = source.read_text(encoding="utf-8").splitlines()[-int(limit) :]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
    except Exception:
        return []


def _legacy_awe(paths, limit=600):
    records = []
    for path in paths:
        try:
            if not path or not Path(path).exists():
                continue
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()[-int(limit) :]
            for line in lines:
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                outcome = (
                    item.get("outcome")
                    or item.get("final_outcome")
                    or item.get("trade_outcome")
                    or item.get("result_label")
                )
                if outcome is None:
                    raw_result = str(
                        item.get("trade_result") or item.get("pnl_result") or ""
                    ).upper().strip()
                    outcome = (
                        raw_result
                        if raw_result
                        in {
                            "WIN",
                            "LOSS",
                            "BE",
                            "BREAKEVEN",
                            "TP",
                            "SL",
                            "STOP",
                            "PROFIT",
                            "LOSS",
                        }
                        else None
                    )
                if outcome is None:
                    continue
                decision = str(
                    item.get("decision")
                    or item.get("policy_decision")
                    or item.get("execution_decision")
                    or ""
                ).upper().strip()
                records.append(
                    {
                        "decision": decision,
                        "outcome": str(outcome).upper().strip(),
                        "raw": item,
                    }
                )
        except Exception:
            continue
    return records[-int(limit) :]


def _awe_paths(reader):
    return [
        reader["CENTRAL_DECISION_LOG_FILE"],
        reader["CENTRAL_TIMELINE_LOG_FILE"],
        reader["CENTRAL_DATA_DIR"] / "learning_engine_v1.jsonl",
    ]


def test_v3_matches_legacy_and_limits_physical_lines_before_parse(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    last_dict = {"id": "last", "decision": "ALLOW"}
    lines = [
        _json_line({"id": "outside"}),
        "",
        "{invalid",
        "7",
        "[1,2]",
        _json_line(last_dict),
    ]
    _write_physical_lines(source, lines)

    page = reader["_read_physical_tail_lines_v1"](source, 4, block_size=5)
    actual = reader["_read_jsonl_tail_v3"](source, 4)

    assert page["lines"] == lines[-4:]
    assert page["physical_lines_returned"] == 4
    assert actual == _legacy_v3(source, 4) == [7, [1, 2], last_dict]


def test_awe_matches_legacy_source_priority_filters_and_global_tail(reader):
    paths = _awe_paths(reader)
    fixtures = [
        [
            _json_line({"decision": "ALLOW", "outcome": "WIN", "id": "d1"}),
            "",
            "not-json",
            "9",
            _json_line({"decision": "DENY", "trade_result": "LOSS", "id": "d2"}),
        ],
        [
            _json_line({"policy_decision": "WAIT", "final_outcome": "SL", "id": "t1"}),
            _json_line({"decision": "ALLOW", "result": "WIN", "id": "ignored"}),
        ],
        [
            "[]",
            _json_line({"execution_decision": "REDUCE", "result_label": "BE", "id": "l1"}),
        ],
    ]
    for path, lines in zip(paths, fixtures):
        _write_physical_lines(path, lines)

    expected = _legacy_awe(paths, 4)
    actual = reader["_awe_extract_outcome_records"](4)

    assert actual == expected
    assert [row["raw"]["id"] for row in actual] == ["d2", "t1", "l1"]


def test_awe_does_not_scan_past_600_physical_lines_for_an_outcome(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    hidden_outcome = _json_line(
        {"decision": "ALLOW", "outcome": "WIN", "id": "outside-window"}
    )
    non_outcomes = [_json_line({"id": index}) for index in range(600)]
    _write_physical_lines(source, [hidden_outcome, *non_outcomes])

    assert reader["_awe_extract_outcome_records"](600) == []


def test_awe_keeps_chronological_order_after_per_source_and_global_limits(reader):
    paths = _awe_paths(reader)
    for source_index, path in enumerate(paths):
        _write_physical_lines(
            path,
            [
                _json_line(
                    {
                        "decision": "ALLOW",
                        "outcome": "WIN",
                        "id": f"{source_index}-{row_index}",
                    }
                )
                for row_index in range(5)
            ],
        )

    actual = reader["_awe_extract_outcome_records"](3)

    assert [row["raw"]["id"] for row in actual] == ["2-2", "2-3", "2-4"]
    assert actual == _legacy_awe(paths, 3)


def test_missing_empty_and_one_line_files(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]

    assert reader["_read_jsonl_tail_v3"](source, 5) == []
    missing = reader["_read_physical_tail_lines_v1"](source, 5)
    assert missing["lines"] == []
    assert missing["source_size_bytes"] == missing["bytes_read"] == 0

    source.touch()
    assert reader["_read_jsonl_tail_v3"](source, 5) == []

    row = {"text": "ação🚀"}
    _write_physical_lines(source, [_json_line(row)], final_newline=False)
    assert reader["_read_jsonl_tail_v3"](source, 1) == [row]


def test_utf8_is_decoded_after_multibyte_line_reassembly(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    text = "ação🚀fim" * 400
    rows = [{"id": 1}, {"id": 2, "text": text}]
    _write_physical_lines(source, [_json_line(row) for row in rows])
    payload = source.read_bytes()
    rocket_start = payload.index("🚀".encode("utf-8"))
    rocket_end = rocket_start + len("🚀".encode("utf-8"))
    block_size = next(
        size
        for size in range(2, 80)
        if any(
            rocket_start < len(payload) - step * size < rocket_end
            for step in range(1, len(payload) // size + 1)
        )
    )

    page = reader["_read_physical_tail_lines_v1"](
        source,
        2,
        block_size=block_size,
    )

    assert source.stat().st_size > 2 * block_size
    assert [json.loads(line) for line in page["lines"]] == rows


def test_line_larger_than_twice_block_is_reassembled(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    rows = [{"id": 1}, {"id": 2, "text": "á" * 20_000}]
    _write_physical_lines(source, [_json_line(row) for row in rows])

    page = reader["_read_physical_tail_lines_v1"](source, 1, block_size=31)

    assert len(_json_line(rows[-1]).encode("utf-8")) > 2 * 31
    assert [json.loads(line) for line in page["lines"]] == rows[-1:]


@pytest.mark.parametrize("final_newline", [True, False])
def test_valid_final_json_with_or_without_newline_is_accepted(reader, final_newline):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    rows = [{"id": 1}, {"id": 2}]
    _write_physical_lines(
        source,
        [_json_line(row) for row in rows],
        final_newline=final_newline,
    )

    page = reader["_read_physical_tail_lines_v1"](source, 2)

    assert reader["_read_jsonl_tail_v3"](source, 2) == rows
    assert page["incomplete_last_line"] is (not final_newline)


def test_invalid_unterminated_final_fragment_consumes_window_but_is_ignored(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    row = {"id": "valid"}
    _write_physical_lines(
        source,
        [_json_line(row), '{"id":"partial"'],
        final_newline=False,
    )

    assert reader["_read_jsonl_tail_v3"](source, 1) == []
    assert reader["_read_jsonl_tail_v3"](source, 2) == [row]


def test_crlf_matches_legacy_json_parsing(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    rows = [{"id": 1, "text": "ação"}, {"id": 2}]
    _write_physical_lines(
        source,
        [_json_line(row) for row in rows],
        newline=b"\r\n",
    )

    assert reader["_read_jsonl_tail_v3"](source, 2) == _legacy_v3(source, 2) == rows


def test_limit_none_zero_one_negative_and_above_default_match_legacy(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    lines = [
        _json_line({"id": 0}),
        "invalid",
        "3",
        _json_line({"id": 3}),
        _json_line({"id": 4}),
    ]
    _write_physical_lines(source, lines)

    assert reader["_read_jsonl_tail_v3"](source, None) == []
    for limit in (0, 1, -1, -3, 2000):
        assert reader["_read_jsonl_tail_v3"](source, limit) == _legacy_v3(
            source,
            limit,
        )

    awe_paths = _awe_paths(reader)
    _write_physical_lines(
        source,
        [
            _json_line({"id": index, "decision": "ALLOW", "outcome": "WIN"})
            for index in range(6)
        ],
    )
    with pytest.raises(TypeError):
        reader["_awe_extract_outcome_records"](None)
    for limit in (0, 1, -1, -3, 2000):
        assert reader["_awe_extract_outcome_records"](limit) == _legacy_awe(
            awe_paths,
            limit,
        )


def test_symlink_non_regular_and_traversal_are_rejected_fail_open(
    reader,
    tmp_path,
    monkeypatch,
):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    _write_physical_lines(source, [_json_line({"id": 1})])

    traversal = source.parent / "nested" / ".." / source.name
    with pytest.raises(ValueError, match="UNEXPECTED_TRAVERSAL"):
        reader["_read_physical_tail_lines_v1"](traversal, 1)
    assert reader["_read_jsonl_tail_v3"](traversal, 1) == []

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="NOT_REGULAR_FILE"):
        reader["_read_physical_tail_lines_v1"](directory, 1)

    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        real_lstat = Path.lstat

        def symlink_lstat(path):
            if path == link:
                return os.stat_result(
                    (stat.S_IFLNK | 0o777, 0, 0, 1, 0, 0, 0, 0, 0, 0)
                )
            return real_lstat(path)

        monkeypatch.setattr(Path, "lstat", symlink_lstat)
    with pytest.raises(ValueError, match="SYMLINK_REJECTED"):
        reader["_read_physical_tail_lines_v1"](link, 1)


def test_concurrent_append_is_excluded_until_next_snapshot(reader, monkeypatch):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    initial_rows = [{"id": 1}, {"id": 2}]
    appended = {"id": 3}
    _write_physical_lines(source, [_json_line(row) for row in initial_rows])
    initial_size = source.stat().st_size
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
                with source.open("ab") as writer:
                    writer.write((_json_line(appended) + "\n").encode("utf-8"))
            return data

    monkeypatch.setattr(
        os,
        "fdopen",
        lambda *args, **kwargs: AppendAfterRead(real_fdopen(*args, **kwargs)),
    )

    first = reader["_read_physical_tail_lines_v1"](source, 3)
    second = reader["_read_jsonl_tail_v3"](source, 3)

    assert first["source_size_bytes"] == initial_size
    assert [json.loads(line) for line in first["lines"]] == initial_rows
    assert second == initial_rows + [appended]


def test_truncate_during_read_is_detected_and_public_reader_fails_open(
    reader,
    monkeypatch,
):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    _write_physical_lines(source, [_json_line({"id": index}) for index in range(30)])
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
        reader["_read_physical_tail_lines_v1"](source, 5)
    assert reader["_read_jsonl_tail_v3"](source, 5) == []


def test_replacement_and_disappearing_path_are_detected(reader, monkeypatch):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    _write_physical_lines(source, [_json_line({"id": index}) for index in range(5)])
    real_lstat = Path.lstat
    calls = 0

    def replacing_lstat(path):
        nonlocal calls
        snapshot = real_lstat(path)
        if path == source:
            calls += 1
            if calls % 2 == 0:
                changed = list(snapshot)
                changed[1] = snapshot.st_ino + 1
                return os.stat_result(changed)
        return snapshot

    monkeypatch.setattr(Path, "lstat", replacing_lstat)
    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        reader["_read_physical_tail_lines_v1"](source, 2)
    assert reader["_read_jsonl_tail_v3"](source, 2) == []

    calls = 0

    def disappearing_lstat(path):
        nonlocal calls
        snapshot = real_lstat(path)
        if path == source:
            calls += 1
            if calls % 2 == 0:
                raise FileNotFoundError(path)
        return snapshot

    monkeypatch.setattr(Path, "lstat", disappearing_lstat)
    with pytest.raises(OSError, match="SOURCE_CHANGED_DURING_READ"):
        reader["_read_physical_tail_lines_v1"](source, 2)
    assert reader["_read_jsonl_tail_v3"](source, 2) == []


def test_large_fixture_reads_only_a_small_tail_region(reader):
    source = reader["CENTRAL_DECISION_LOG_FILE"]
    rows = [
        {"id": index, "decision": "ALLOW", "padding": "x" * 512}
        for index in range(25_000)
    ]
    _write_physical_lines(source, [_json_line(row) for row in rows])

    page = reader["_read_physical_tail_lines_v1"](source, 100)
    parsed = [json.loads(line) for line in page["lines"]]

    assert parsed == rows[-100:]
    assert page["physical_lines_returned"] == 100
    assert page["bytes_read"] < page["source_size_bytes"] // 10
    assert page["tail_limited"] is True


def test_evolution_and_ceo_compact_counts_and_text_remain_unchanged(reader):
    decision_rows = [
        {"id": 1, "decision": "ALLOW", "bot": "FALCON"},
        {"id": 2, "decision": "DENY", "bot": "TURTLE", "reason": "risk"},
    ]
    timeline_rows = [{"event": "ENTRY"}, {"event": "CLOSE"}]
    _write_physical_lines(
        reader["CENTRAL_DECISION_LOG_FILE"],
        [_json_line(row) for row in decision_rows],
    )
    _write_physical_lines(
        reader["CENTRAL_TIMELINE_LOG_FILE"],
        [_json_line(row) for row in timeline_rows],
    )

    evolution = reader["build_evolution_dashboard_v3"]()
    compact = reader["_compact_decisionlog_block"]()

    assert "ALLOW: 1 | DENY: 1" in evolution
    assert "VERIFY: 0 | LIVE: 0" in evolution
    assert "2 | ALLOW: 1 | DENY/BLOCK: 1" in compact


def test_reader_sources_have_no_integral_read_apis_or_automatic_logging(reader):
    source = "\n".join(
        inspect.getsource(reader[name])
        for name in (
            "_read_physical_tail_lines_v1",
            "_read_jsonl_tail_v3",
            "_awe_extract_outcome_records",
        )
    )

    assert ".read_text(" not in source
    assert ".readlines(" not in source
    assert "list(file" not in source
    assert "mmap" not in source
    assert "print(" not in source
    assert "_read_new_jsonl" not in source
    assert "decision_log_offset" not in source
