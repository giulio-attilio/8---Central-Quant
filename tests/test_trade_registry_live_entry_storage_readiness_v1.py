from __future__ import annotations

import ast
import copy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class _ActiveFile:
    def __init__(self, value: str, *, exists: bool = True):
        self.value = value
        self._exists = exists

    def __str__(self):
        return self.value

    def exists(self):
        return self._exists


def _load_readiness(*, state, active_file):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=str(MAIN))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_trpsf_v1_falcon_live_entry_storage_readiness"
    )
    module = ast.Module(body=[copy.deepcopy(node)], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "_TRPSF_V1_STATE": state,
        "_trpsf_v1_active_file": lambda: active_file,
        "TRADE_REGISTRY_PERSISTENT_STORAGE_FIX_V1_VERSION": "TEST-V1",
    }
    exec(compile(module, str(MAIN), "exec"), namespace)
    return namespace["_trpsf_v1_falcon_live_entry_storage_readiness"]


def _ready_state(**changes):
    state = {
        "patched": True,
        "migration_done": True,
        "restart_readiness_attested": True,
        "last_load_ok": True,
        "last_write_ok": True,
        "write_allowed": True,
        "temporary_read_only": False,
    }
    state.update(changes)
    return state


def test_registry_live_entry_readiness_accepts_only_complete_persistent_proof():
    readiness = _load_readiness(
        state=_ready_state(),
        active_file=_ActiveFile("/data/trade_registry.json"),
    )()

    assert readiness["ok"] is True
    assert readiness["status"] == "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READY"
    assert readiness["read_only"] is True
    assert readiness["write_executed"] is False
    assert all(readiness["checks"].values())


def test_registry_live_entry_readiness_fails_closed_for_each_startup_gap():
    cases = [
        (_ready_state(patched=False), _ActiveFile("/data/trade_registry.json")),
        (_ready_state(migration_done=False), _ActiveFile("/data/trade_registry.json")),
        (
            _ready_state(restart_readiness_attested=False),
            _ActiveFile("/data/trade_registry.json"),
        ),
        (_ready_state(), _ActiveFile("/opt/render/project/src/data/trade_registry.json")),
        (_ready_state(), _ActiveFile("/data/trade_registry.json", exists=False)),
        (_ready_state(last_load_ok=None), _ActiveFile("/data/trade_registry.json")),
        (_ready_state(last_write_ok=None), _ActiveFile("/data/trade_registry.json")),
        (_ready_state(write_allowed=False), _ActiveFile("/data/trade_registry.json")),
        (_ready_state(temporary_read_only=True), _ActiveFile("/data/trade_registry.json")),
    ]

    for state, active_file in cases:
        readiness = _load_readiness(state=state, active_file=active_file)()
        assert readiness["ok"] is False
        assert readiness["status"] == "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_NOT_READY"
        assert readiness["write_executed"] is False


def test_registry_live_entry_readiness_converts_internal_error_to_closed_state():
    readiness = _load_readiness(
        state=_ready_state(),
        active_file=_ActiveFile("/data/trade_registry.json"),
    )
    readiness.__globals__["_trpsf_v1_active_file"] = lambda: (_ for _ in ()).throw(
        RuntimeError("unavailable")
    )

    result = readiness()

    assert result["ok"] is False
    assert result["status"] == "TRADE_REGISTRY_LIVE_ENTRY_STORAGE_READINESS_ERROR"
    assert result["error_type"] == "RuntimeError"
    assert result["write_executed"] is False
