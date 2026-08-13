from __future__ import annotations

import ast
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import memory_source_observability as source_observability


ROOT = Path(__file__).resolve().parents[1]


def test_logger_uses_loaded_runtime_identity_and_scalar_text_only(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "main",
        SimpleNamespace(CENTRAL_RUNTIME_BOOT_ID="central-boot-test"),
    )
    output = io.StringIO()
    with redirect_stdout(output):
        emitted = source_observability.emit_memory_source_observation(
            "TURTLE_SUMMARY_LOAD_MEMORY",
            cycle_id="turtle-summary-1",
            rss_start_mb=10.0,
            rss_end_mb=12.5,
            rss_delta_mb=2.5,
            elapsed_ms=25.0,
        )

    rendered = output.getvalue()
    assert emitted is True
    assert rendered.startswith("TURTLE_SUMMARY_LOAD_MEMORY | sampled_at=")
    assert "cycle_id=turtle-summary-1" in rendered
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


def test_helper_remains_stdlib_only_and_does_not_import_operational_modules():
    helper_source = (ROOT / "memory_source_observability.py").read_text(encoding="utf-8")
    tree = ast.parse(helper_source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    for forbidden in ("main", "pandas", "redis", "requests"):
        assert forbidden not in imported
