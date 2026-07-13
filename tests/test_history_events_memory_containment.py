from __future__ import annotations

import ast
import importlib
import json
import os
import socket
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import history_memory_guard as guard


ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, rows, final_newline=True):
    payload = b"\n".join(
        json.dumps(row, ensure_ascii=False).encode("utf-8") if isinstance(row, dict) else row
        for row in rows
    )
    if final_newline:
        payload += b"\n"
    path.write_bytes(payload)


@pytest.mark.parametrize("missing", [True, False])
def test_missing_and_empty_files(tmp_path, missing):
    path = tmp_path / "history_events.jsonl"
    if not missing:
        path.touch()
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == []
    assert result["coverage_complete"] is True
    assert result["bytes_read"] == 0


def test_one_utf8_line(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"event": "SINAL", "texto": "ação 🐢"}])
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == [{"event": "SINAL", "texto": "ação 🐢"}]
    assert result["partial"] is False


def test_incomplete_last_line_is_ignored(tmp_path):
    path = tmp_path / "history_events.jsonl"
    path.write_bytes(b'{"id": 1}\n{"id": 2}')
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == [{"id": 1}]
    assert result["incomplete_last_line"] is True
    assert result["partial"] is True


def test_invalid_json_is_isolated(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}, b"not-json", {"id": 2}])
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == [{"id": 1}, {"id": 2}]
    assert result["invalid_lines"] == 1


def test_reverse_order_and_max_records(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": number} for number in range(10)])
    normal = guard.iter_jsonl_tail(path, 3, 4096)
    reverse = guard.iter_jsonl_tail(path, 3, 4096, newest_first=True)
    assert [row["id"] for row in normal["records"]] == [7, 8, 9]
    assert [row["id"] for row in reverse["records"]] == [9, 8, 7]
    assert normal["partial"] is True
    assert normal["records_examined"] == 3


def test_records_cross_multiple_reverse_blocks_without_loss(tmp_path):
    path = tmp_path / "history_events.jsonl"
    rows = [{"id": number, "padding": "x" * 900} for number in range(180)]
    _write(path, rows)
    result = guard.iter_jsonl_tail(path, 180, 512 * 1024)
    assert [row["id"] for row in result["records"]] == list(range(180))
    assert result["bytes_read"] == path.stat().st_size


def test_newline_exactly_on_reverse_block_boundary(tmp_path):
    path = tmp_path / "history_events.jsonl"
    last = b'{"id": 2}\n'
    first = b'{"id": 1, "padding":"' + b"x" * (guard.READ_BLOCK_BYTES - len(last) - 24) + b'"}\n'
    path.write_bytes(first + last)
    assert path.stat().st_size == guard.READ_BLOCK_BYTES
    result = guard.iter_jsonl_tail(path, 10, 2 * guard.READ_BLOCK_BYTES)
    assert [row["id"] for row in result["records"]] == [1, 2]


def test_utf8_multibyte_crosses_reverse_block_boundary(tmp_path):
    path = tmp_path / "history_events.jsonl"
    emoji = "🐢".encode("utf-8")
    prefix = b'{"id":1,"text":"'
    suffix_overhead = b'","tail":"' + b'"}\n'
    suffix_fixed = b'","tail":"' + b"z" * (
        guard.READ_BLOCK_BYTES - 2 - len(suffix_overhead)
    ) + b'"}\n'
    raw = prefix + emoji + suffix_fixed
    emoji_at = raw.index(emoji)
    assert emoji_at < len(raw) - guard.READ_BLOCK_BYTES < emoji_at + len(emoji)
    path.write_bytes(raw)
    result = guard.iter_jsonl_tail(path, 10, 2 * guard.READ_BLOCK_BYTES)
    assert result["records"][0]["id"] == 1
    assert "🐢" in result["records"][0]["text"]


def test_max_bytes_bounds_physical_read(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": number, "padding": "x" * 30} for number in range(100)])
    result = guard.iter_jsonl_tail(path, 100, 256)
    assert 0 < result["bytes_read"] <= 256
    assert result["source_size_bytes"] > result["bytes_read"]
    assert result["partial"] is True
    assert result["coverage_complete"] is False


def test_complete_last_record_without_newline_is_conservatively_ignored(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}, {"id": 2}], final_newline=False)
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == [{"id": 1}]
    assert result["incomplete_last_line"] is True
    assert result["partial"] is True


def test_single_line_larger_than_byte_budget_never_expands_buffer(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"oversized": "x" * 4096}, {"id": "tail"}])
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["bytes_read"] <= 1024
    assert result["records"] == [{"id": "tail"}]
    assert result["partial"] is True


def test_absolute_record_boundaries(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": number} for number in range(guard.ABSOLUTE_MAX_RECORDS + 1)])
    one = guard.iter_jsonl_tail(path, 1, guard.ABSOLUTE_MAX_BYTES)
    maximum = guard.iter_jsonl_tail(path, guard.ABSOLUTE_MAX_RECORDS, guard.ABSOLUTE_MAX_BYTES)
    assert one["records"] == [{"id": guard.ABSOLUTE_MAX_RECORDS}]
    assert len(maximum["records"]) == guard.ABSOLUTE_MAX_RECORDS
    assert maximum["records"][0]["id"] == 1
    assert maximum["partial"] is True


def test_one_byte_budget_is_absolute(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}])
    result = guard.iter_jsonl_tail(path, 1, 1)
    assert result["bytes_read"] == 1
    assert result["records"] == []
    assert result["partial"] is True


def test_sparse_295_mb_file_reads_only_budget(tmp_path):
    path = tmp_path / "history_events.jsonl"
    with path.open("wb") as handle:
        handle.seek(295 * guard.MIB)
        handle.write(b'\n{"id": 295}\n')
    result = guard.iter_jsonl_tail(path, 10, 2 * guard.MIB)
    assert result["source_size_bytes"] > 295 * guard.MIB
    assert result["bytes_read"] <= 2 * guard.MIB
    assert result["records"][-1] == {"id": 295}
    assert result["partial"] is True


@pytest.mark.parametrize(
    "records,bytes_",
    [(0, 1), (guard.ABSOLUTE_MAX_RECORDS + 1, 1), (1, 0), (1, guard.ABSOLUTE_MAX_BYTES + 1), ("bad", 1)],
)
def test_invalid_limits_are_rejected(records, bytes_):
    with pytest.raises(ValueError):
        guard.validate_history_limits(records, bytes_)


def test_symlink_is_not_followed(tmp_path):
    target = tmp_path / "target.jsonl"
    link = tmp_path / "history_events.jsonl"
    _write(target, [{"secret": "must-not-read"}])
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink unavailable")
    with pytest.raises(ValueError, match="symlink"):
        guard.iter_jsonl_tail(link, 10, 1024)


def test_non_regular_file_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="regular file"):
        guard.iter_jsonl_tail(tmp_path, 10, 1024)


@pytest.mark.parametrize("mutation", ["grow", "truncate"])
def test_source_mutation_during_read_is_safe_and_partial(tmp_path, monkeypatch, mutation):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": number} for number in range(20)])
    original_fstat = guard.os.fstat
    mutated = False

    def mutate_after_open(descriptor):
        nonlocal mutated
        snapshot = original_fstat(descriptor)
        if not mutated:
            mutated = True
            if mutation == "grow":
                with path.open("ab") as handle:
                    handle.write(b'{"id":"grown"}\n')
            elif mutation == "truncate":
                os.truncate(path, 8)
        return snapshot

    monkeypatch.setattr(guard.os, "fstat", mutate_after_open)
    result = guard.iter_jsonl_tail(path, 100, 4096)
    assert result["partial"] is True
    assert result["coverage_complete"] is False
    assert result.get("source_changed_during_read") is True
    assert result["bytes_read"] <= 4096


def test_source_replacement_during_read_is_detected(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}])
    original_lstat = guard.Path.lstat
    calls = 0

    def replacement_visible_on_final_stat(self):
        nonlocal calls
        current = original_lstat(self)
        if self == path:
            calls += 1
            if calls >= 3:
                return SimpleNamespace(
                    st_mode=current.st_mode,
                    st_size=current.st_size,
                    st_dev=current.st_dev,
                    st_ino=current.st_ino + 1,
                )
        return current

    monkeypatch.setattr(guard.Path, "lstat", replacement_visible_on_final_stat)
    result = guard.iter_jsonl_tail(path, 10, 1024)
    assert result["records"] == [{"id": 1}]
    assert result["partial"] is True
    assert result["source_changed_during_read"] is True


def test_reader_source_has_no_unbounded_file_apis_or_dataframe():
    source = (ROOT / "history_memory_guard.py").read_text(encoding="utf-8")
    assert ".readlines(" not in source
    assert ".read_text(" not in source
    assert ".splitlines(" not in source
    assert "list(handle" not in source
    assert "pandas" not in source.lower()
    assert "DataFrame" not in source


def test_reader_has_no_write_network_broker_or_thread_start():
    tree = ast.parse((ROOT / "history_memory_guard.py").read_text(encoding="utf-8"))
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert calls.isdisjoint({"write", "write_text", "write_bytes", "unlink", "remove", "Thread", "start", "connect"})


def test_probe_logs_begin_and_end(tmp_path, capsys):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}])
    guard.iter_jsonl_tail(path, 10, 1024, operation="test_probe")
    output = capsys.readouterr().out
    assert "HISTORY_MEMORY_BEGIN operation=test_probe" in output
    assert "HISTORY_MEMORY_END operation=test_probe" in output
    assert "records=1" in output


def test_probe_logs_error(capsys):
    with pytest.raises(RuntimeError):
        with guard.history_memory_probe("failing_probe"):
            raise RuntimeError("expected")
    output = capsys.readouterr().out
    assert "HISTORY_MEMORY_ERROR operation=failing_probe exception_type=RuntimeError" in output
    assert "expected" not in output


def test_instrumentation_failure_never_blocks_reader(tmp_path, monkeypatch):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"id": 1}])
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("stdout unavailable")))
    assert guard.iter_jsonl_tail(path, 10, 1024)["records"] == [{"id": 1}]


def test_history_manager_uses_bounded_reader_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HISTORY_MAX_READ", "2")
    sys.modules.pop("history_manager", None)
    module = importlib.import_module("history_manager")
    _write(module.HISTORY_EVENTS_FILE, [{"id": number} for number in range(5)])
    page = module.load_events(include_metadata=True)
    assert [row["id"] for row in page["records"]] == [3, 4]
    assert page["partial"] is True
    assert page["max_records"] == 2


def test_query_and_payload_declare_partial_coverage(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HISTORY_MAX_READ", "2")
    sys.modules.pop("history_manager", None)
    module = importlib.import_module("history_manager")
    _write(module.HISTORY_EVENTS_FILE, [{"event": "SIGNAL_CREATED", "id": number} for number in range(5)])
    query = module.query_history()
    payload = module.build_history_payload()
    assert query["partial"] is True and query["coverage_complete"] is False
    assert payload["partial"] is True
    assert payload["totals"]["scope"] == "BOUNDED_TAIL"


def test_predator_summary_reader_has_no_integral_read():
    source = (ROOT / "predator_daily_summary.py").read_text(encoding="utf-8")
    function = source[source.index("def read_predator_event_log"):source.index("def load_events_for_period")]
    assert "read_text(" not in function
    assert "splitlines(" not in function
    assert "iter_jsonl_tail(" in function


def test_real_mapper_reader_has_no_append_all_scan():
    source = (ROOT / "real_pnl_r_mapper.py").read_text(encoding="utf-8")
    function = source[source.index("def _read_jsonl("):source.index("def _read_json(")]
    assert "for line in" not in function
    assert "iter_jsonl_tail(" in function


def test_root_health_and_watchdog_do_not_reference_history():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    functions = {node.name: ast.unparse(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in ("home", "health", "central_watchdog_status", "central_watchdog_loop"):
        assert "history_manager" not in functions[name]
        assert "load_events" not in functions[name]
    assert "BOT_NAME" in functions["home"] and "Online" in functions["home"]


def test_health_and_root_succeed_when_history_reader_would_raise():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    namespace = {
        "central_watchdog_status": lambda: {"ok": True},
        "central_trade_registry_snapshot": lambda include_trades=False: {"ok": True},
        "automatic_daily_summaries_health": lambda: {},
        "automatic_learning_refresh_health": lambda **kwargs: {},
        "LEARNING_AUTO_REFRESH_SECONDS": 900,
        "LEARNING_AUTO_REFRESH_MIN_SECONDS": 300,
        "LEARNING_AUTO_REFRESH_THREAD_STARTED": False,
        "LEARNING_AUTO_REFRESH_LEGACY_ENABLED": False,
        "build_disk_forensics_health": None,
        "STARTUP_DISK_FORENSICS_RESULT": {},
        "load_events": lambda *args, **kwargs: pytest.fail("History read attempted"),
        "BOT_NAME": "Central Quant",
    }
    for name in ("health", "home"):
        node = nodes[name]
        node.decorator_list = []
        isolated = ast.Module(body=[node], type_ignores=[])
        ast.fix_missing_locations(isolated)
        exec(compile(isolated, f"<isolated-{name}>", "exec"), namespace)
    assert namespace["health"]()["ok"] is True
    assert namespace["home"]() == "Central Quant Online"


def test_disabled_daily_and_learning_gate_before_heavy_work():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    daily = source[source.index("def central_daily_report_loop"):source.index("def start_central_runtime_once")]
    assert daily.index("if not automatic_daily_enabled") < daily.index("while True")
    learning = source[source.index("def learning_auto_refresh_loop"):source.index("def learning_auto_status_route")]
    assert learning.index("if not LEARNING_AUTO_REFRESH_ENABLED") < learning.index("import learning_engine")


def test_startup_and_telegram_idle_paths_do_not_read_history():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    startup = source[source.index("def start_central_runtime_once"):source.index("# ==========================================================\n# PATCH FINAL")]
    assert "load_events(" not in startup
    telegram = source[source.index("def central_telegram_command_loop"):source.index("def central_daily_report_loop")]
    assert "load_events(" not in telegram


def test_main_history_tail_helpers_use_guard():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    generic = source[source.index("def _read_jsonl_tail"):source.index("def _read_json_file")]
    predator = source[source.index("def _pppa_v1_read_jsonl_tail"):source.index("def _pppa_v1_read_json_records")]
    assert "readlines(" not in generic and "iter_jsonl_tail(" in generic
    assert "for line in" not in predator and "iter_jsonl_tail(" in predator


def test_manual_history_endpoints_validate_absolute_limits_and_return_metadata():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    functions = {node.name: ast.unparse(node) for node in tree.body if isinstance(node, ast.FunctionDef)}
    events_route = functions["history_events_route"]
    query_route = functions["history_query_route"]
    assert "validate_history_limits" in events_route
    assert "max_bytes" in events_route
    assert "include_metadata=True" in events_route
    assert "validate_history_limits" in query_route


def test_history_stats_uses_exactly_one_reader_call(monkeypatch):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "build_history_stats_payload")
    calls = []
    page = {
        "records": [{"event": "SIGNAL_CREATED"}],
        "partial": True,
        "coverage_complete": False,
        "records_examined": 1,
        "bytes_read": 20,
        "max_records": 2000,
        "max_bytes": 16 * 1024 * 1024,
        "source_size_bytes": 100,
    }
    fake = SimpleNamespace(
        load_events=lambda **kwargs: calls.append(kwargs) or page.copy(),
        data_hora_sp_str=lambda: "now",
        calculate_stats=lambda **kwargs: {},
        group_stats=lambda **kwargs: {},
    )
    monkeypatch.setitem(sys.modules, "history_manager", fake)
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = {}
    exec(compile(isolated, "<isolated-history-stats>", "exec"), namespace)
    result = namespace["build_history_stats_payload"]()
    assert calls == [{"include_metadata": True}]
    assert result["partial"] is True


def test_reader_result_is_json_serializable(tmp_path):
    path = tmp_path / "history_events.jsonl"
    _write(path, [{"text": "ação"}])
    json.dumps(guard.iter_jsonl_tail(path, 10, 1024), ensure_ascii=False)


def test_no_test_uses_real_data_network_redis_or_broker(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *args, **kwargs: pytest.fail("network attempted"))
    assert "redis" not in sys.modules
    assert "broker" not in sys.modules
