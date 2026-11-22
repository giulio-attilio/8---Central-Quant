from __future__ import annotations

import os
from pathlib import Path

import pytest

import trade_lifecycle_manager as lifecycle_manager
from trade_lifecycle_shadow_runtime_adapter import TradeLifecycleShadowRuntimeAdapter


def test_shadow_manager_uses_shared_data_dir_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", raising=False)
    monkeypatch.delenv("CENTRAL_DATA_DIR", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "persistent"))

    assert lifecycle_manager._resolve_data_dir() == tmp_path / "persistent"


def test_shadow_adapter_inherits_manager_storage_root(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", raising=False)
    monkeypatch.setattr(lifecycle_manager, "DATA_DIR", tmp_path / "shared")

    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=False)

    assert adapter.events_file.parent == tmp_path / "shared"
    assert adapter.state_file.parent == tmp_path / "shared"


@pytest.mark.skipif(os.name == "nt", reason="Render mount guard requires POSIX semantics")
def test_manager_snapshot_write_refuses_ephemeral_render_path(monkeypatch, tmp_path):
    target = tmp_path / "ephemeral" / "trade_lifecycle_shadow_snapshot.json"
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(lifecycle_manager, "DATA_DIR", target.parent)
    monkeypatch.setattr(lifecycle_manager, "SNAPSHOT_FILE", target)

    with pytest.raises(OSError, match="TRADE_LIFECYCLE_SHADOW_STORAGE_NOT_VERIFIED"):
        lifecycle_manager._atomic_write_snapshot()

    assert not target.exists()


@pytest.mark.skipif(os.name == "nt", reason="Render mount guard requires POSIX semantics")
def test_shadow_adapter_append_refuses_ephemeral_render_path(monkeypatch, tmp_path):
    target_dir = tmp_path / "ephemeral"
    monkeypatch.setenv("RENDER", "true")
    adapter = TradeLifecycleShadowRuntimeAdapter(enabled=False, data_dir=target_dir)

    with pytest.raises(OSError, match="SHADOW_STORAGE_NOT_VERIFIED"):
        adapter._append(adapter.events_file, {"event_type": "TEST"})

    assert not target_dir.exists()


def test_shadow_reset_does_not_clear_persistent_state(monkeypatch, tmp_path):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setattr(lifecycle_manager, "_is_persistent_data_path", lambda _path: True)
    monkeypatch.setattr(lifecycle_manager, "_lifecycles", {"preserve": {"id": "preserve"}})
    monkeypatch.setattr(lifecycle_manager, "_loaded", True)

    result = lifecycle_manager.reset_shadow_storage(confirm=True)

    assert result["status"] == "PERSISTENT_SHADOW_RESET_REQUIRES_SEPARATE_MAINTENANCE"
    assert result["reset"] is False
    assert "preserve" in lifecycle_manager._lifecycles
