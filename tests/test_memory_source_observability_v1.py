from __future__ import annotations

import ast
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import memory_source_observability as source_observability
import registry_v2_wal as wal
import trade_lifecycle_shadow_runtime_adapter as shadow


ROOT = Path(__file__).resolve().parents[1]


class _ShadowManager:
    pass


def _storage(tmp_path: Path) -> wal.RegistryV2WalStorage:
    return wal.RegistryV2WalStorage(
        snapshot_path=tmp_path / "registry.json",
        journal_path=tmp_path / "registry.wal.jsonl",
        lock_path=tmp_path / "registry.lock",
        backup_dir=tmp_path / "backups",
    )


def test_shadow_span_reuses_single_existing_read_and_counts_lines(tmp_path, monkeypatch):
    adapter = shadow.TradeLifecycleShadowRuntimeAdapter(
        enabled=True,
        data_dir=tmp_path,
        manager=_ShadowManager(),
    )
    existing = {
        "event_id": "existing-event",
        "event_type": "SHADOW_VALIDATED",
    }
    adapter.events_file.write_text(
        json.dumps(existing) + "\n" + "not-json\n",
        encoding="utf-8",
    )
    expected_file_bytes = adapter.events_file.stat().st_size

    original_open = Path.open
    read_opens = []

    def counting_open(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if path == adapter.events_file and "r" in str(mode):
            read_opens.append(str(mode))
        return original_open(path, *args, **kwargs)

    class FakeTime:
        values = iter((1.0, 10.0, 10.125))

        @classmethod
        def monotonic(cls):
            return next(cls.values)

        @staticmethod
        def sleep(_seconds):
            return None

    observations = []
    rss_values = iter((100.0, 225.5))
    monkeypatch.setattr(Path, "open", counting_open)
    monkeypatch.setattr(shadow, "time", FakeTime())
    monkeypatch.setattr(shadow, "memory_source_current_rss_mb", lambda: next(rss_values))
    monkeypatch.setattr(
        shadow,
        "emit_memory_source_observation",
        lambda event_name, **fields: observations.append((event_name, fields)),
    )

    result = adapter._append_event_once(
        {"event_id": "new-event", "event_type": "SHADOW_VALIDATED"}
    )

    assert result is True
    assert read_opens == ["r"]
    assert len(observations) == 1
    event_name, fields = observations[0]
    assert event_name == "SHADOW_JOURNAL_MEMORY"
    assert fields == {
        "file_bytes": expected_file_bytes,
        "lines_scanned": 2,
        "rss_before_mb": 100.0,
        "rss_after_mb": 225.5,
        "rss_delta_mb": 125.5,
        "elapsed_ms": 125.0,
    }
    assert all(
        value is None or isinstance(value, (str, int, float, bool))
        for value in fields.values()
    )


def test_wal_span_reuses_single_read_and_existing_parsed_result(tmp_path, monkeypatch):
    storage = _storage(tmp_path)
    storage.journal_path.write_bytes(b"existing-journal-bytes\n")
    expected_bytes = storage.journal_path.stat().st_size

    original_read_bytes = Path.read_bytes
    read_calls = []

    def counting_read_bytes(path):
        if path == storage.journal_path:
            read_calls.append(path)
        return original_read_bytes(path)

    class FakeTime:
        values = iter((20.0, 20.25))

        @classmethod
        def monotonic(cls):
            return next(cls.values)

    parsed = ("event-1", "event-2")
    observations = []
    rss_values = iter((300.0, 420.75))
    monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)
    monkeypatch.setattr(wal, "time", FakeTime())
    monkeypatch.setattr(wal, "_parse_journal_bytes", lambda raw: parsed)
    monkeypatch.setattr(wal, "memory_source_current_rss_mb", lambda: next(rss_values))
    monkeypatch.setattr(
        wal,
        "observe_registry_v2_wal_memory",
        lambda **fields: observations.append(fields),
    )

    result = wal.read_journal(storage)

    assert result is parsed
    assert read_calls == [storage.journal_path]
    assert observations == [{
        "journal_bytes": expected_bytes,
        "event_count": 2,
        "rss_before_mb": 300.0,
        "rss_after_mb": 420.75,
        "rss_delta_mb": 120.75,
        "elapsed_ms": 250.0,
    }]
    assert all(
        value is None or isinstance(value, (str, int, float, bool))
        for value in observations[0].values()
    )


def test_observability_failure_preserves_shadow_and_wal_results(tmp_path, monkeypatch):
    adapter = shadow.TradeLifecycleShadowRuntimeAdapter(
        enabled=True,
        data_dir=tmp_path / "shadow",
        manager=_ShadowManager(),
    )
    adapter.events_file.parent.mkdir(parents=True, exist_ok=True)
    adapter.events_file.write_text("", encoding="utf-8")

    storage = _storage(tmp_path / "wal")
    storage.journal_path.parent.mkdir(parents=True, exist_ok=True)
    storage.journal_path.write_bytes(b"journal\n")
    parsed = ("functional-result",)

    def fail_logger(*_args, **_kwargs):
        raise RuntimeError("observability unavailable")

    monkeypatch.setattr(shadow, "emit_memory_source_observation", fail_logger)
    monkeypatch.setattr(wal, "observe_registry_v2_wal_memory", fail_logger)
    monkeypatch.setattr(wal, "_parse_journal_bytes", lambda raw: parsed)

    assert adapter._append_event_once(
        {"event_id": "fail-open-event", "event_type": "SHADOW_VALIDATED"}
    ) is True
    assert wal.read_journal(storage) is parsed


def test_logger_uses_loaded_runtime_identity_and_scalar_text_only(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(CENTRAL_RUNTIME_BOOT_ID="central-boot-test"),
    )
    output = io.StringIO()
    with redirect_stdout(output):
        emitted = source_observability.emit_memory_source_observation(
            "SHADOW_JOURNAL_MEMORY",
            file_bytes=123,
            lines_scanned=4,
            rss_before_mb=10.0,
            rss_after_mb=12.5,
            rss_delta_mb=2.5,
            elapsed_ms=25.0,
        )

    rendered = output.getvalue()
    assert emitted is True
    assert rendered.startswith("SHADOW_JOURNAL_MEMORY | sampled_at=")
    assert "file_bytes=123" in rendered
    assert "boot_id=central-boot-test" in rendered
    assert "{" not in rendered
    assert "[" not in rendered


def test_boot_id_prefers_dunder_main_then_main_then_unknown(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "__main__",
        SimpleNamespace(CENTRAL_RUNTIME_BOOT_ID="dunder-main-boot"),
    )
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(CENTRAL_RUNTIME_BOOT_ID="imported-main-boot"),
    )
    assert source_observability._runtime_boot_id() == "dunder-main-boot"

    monkeypatch.setitem(sys.modules, "__main__", SimpleNamespace())
    assert source_observability._runtime_boot_id() == "imported-main-boot"

    monkeypatch.setitem(sys.modules, "main", SimpleNamespace())
    assert source_observability._runtime_boot_id() == "unknown"


def test_registry_v2_wal_observation_is_aggregated_once_per_minute(monkeypatch):
    state = {
        "window_started": None,
        "calls": 0,
        "max_journal_bytes": None,
        "max_event_count": None,
        "max_rss_delta_mb": None,
        "max_elapsed_ms": None,
        "last_rss_before_mb": None,
        "last_rss_after_mb": None,
    }
    monotonic_values = iter((0.0, 30.0, 60.0, 61.0, 120.0))
    emitted = []
    monkeypatch.setattr(source_observability, "_REGISTRY_V2_WAL_MEMORY_STATE", state)
    monkeypatch.setattr(
        source_observability.time,
        "monotonic",
        lambda: next(monotonic_values),
    )
    monkeypatch.setattr(
        source_observability,
        "emit_memory_source_observation",
        lambda event_name, **fields: emitted.append((event_name, fields)) or True,
    )

    first = source_observability.observe_registry_v2_wal_memory(
        journal_bytes=100,
        event_count=2,
        rss_before_mb=300.0,
        rss_after_mb=310.0,
        rss_delta_mb=10.0,
        elapsed_ms=20.0,
    )
    second = source_observability.observe_registry_v2_wal_memory(
        journal_bytes=200,
        event_count=4,
        rss_before_mb=310.0,
        rss_after_mb=335.0,
        rss_delta_mb=25.0,
        elapsed_ms=40.0,
    )
    third = source_observability.observe_registry_v2_wal_memory(
        journal_bytes=150,
        event_count=3,
        rss_before_mb=335.0,
        rss_after_mb=340.0,
        rss_delta_mb=5.0,
        elapsed_ms=30.0,
    )
    fourth = source_observability.observe_registry_v2_wal_memory(
        journal_bytes=250,
        event_count=5,
        rss_before_mb=340.0,
        rss_after_mb=342.0,
        rss_delta_mb=2.0,
        elapsed_ms=50.0,
    )
    fifth = source_observability.observe_registry_v2_wal_memory(
        journal_bytes=225,
        event_count=6,
        rss_before_mb=342.0,
        rss_after_mb=350.0,
        rss_delta_mb=8.0,
        elapsed_ms=45.0,
    )

    assert (first, second, third, fourth, fifth) == (False, False, True, False, True)
    assert emitted == [
        (
            "REGISTRY_V2_WAL_MEMORY",
            {
                "window_seconds": 60,
                "calls": 3,
                "max_journal_bytes": 200,
                "max_event_count": 4,
                "max_rss_delta_mb": 25.0,
                "max_elapsed_ms": 40.0,
                "last_rss_before_mb": 335.0,
                "last_rss_after_mb": 340.0,
            },
        ),
        (
            "REGISTRY_V2_WAL_MEMORY",
            {
                "window_seconds": 60,
                "calls": 2,
                "max_journal_bytes": 250,
                "max_event_count": 6,
                "max_rss_delta_mb": 8.0,
                "max_elapsed_ms": 50.0,
                "last_rss_before_mb": 342.0,
                "last_rss_after_mb": 350.0,
            },
        ),
    ]


def test_instrumented_modules_do_not_import_main_and_keep_one_content_read():
    shadow_source = (ROOT / "trade_lifecycle_shadow_runtime_adapter.py").read_text(encoding="utf-8")
    wal_source = (ROOT / "registry_v2_wal.py").read_text(encoding="utf-8")
    helper_source = (ROOT / "memory_source_observability.py").read_text(encoding="utf-8")

    for source in (shadow_source, wal_source, helper_source):
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "main" not in imported

    wal_tree = ast.parse(wal_source)
    read_journal = next(
        node
        for node in wal_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "read_journal"
    )
    read_bytes_calls = [
        node
        for node in ast.walk(read_journal)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "read_bytes"
    ]
    assert len(read_bytes_calls) == 1
