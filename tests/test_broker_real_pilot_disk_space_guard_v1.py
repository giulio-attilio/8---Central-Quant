import ast
import os
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BROKER_SOURCE = ROOT / "broker.py"


@pytest.fixture
def guard_namespace():
    tree = ast.parse(BROKER_SOURCE.read_text(encoding="utf-8"))
    names = {
        "_broker_rpg_v1_persistent_disk_space",
        "broker_real_pilot_guard_v1_validate",
    }
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in functions} == names
    namespace = {
        "os": os,
        "shutil": shutil,
        "Path": Path,
        "CENTRAL_DATA_DIR": Path("/isolated-data"),
        "BROKER_REAL_PILOT_MIN_FREE_DISK_BYTES": 256 * 1024 * 1024,
        "BROKER_REAL_PILOT_GUARD_ENABLED": True,
        "BROKER_REAL_PILOT_FAIL_CLOSED": True,
        "BROKER_REAL_PILOT_ALLOW_REDUCE_ONLY_ALWAYS": True,
        "BROKER_REAL_PILOT_ALLOWED_BOTS": {"DONKEY"},
        "BROKER_REAL_PILOT_ALLOWED_SYMBOLS": {"*"},
        "BROKER_REAL_PILOT_MAX_NOTIONAL_USDT": 20.0,
        "BROKER_REAL_PILOT_MAX_OPEN_POSITIONS": 1,
        "ENABLE_REAL_TRADING": True,
        "BROKER_DRY_RUN": False,
        "EXECUTION_MODE": "LIVE",
        "_broker_rpg_v1_bool_env": lambda _names, default: (True, "TEST"),
        "_infer_bot_for_audit": lambda *, bot, client_tag: str(bot or "").upper(),
        "_broker_rpg_v1_norm_symbol": lambda value: str(value or "").upper().replace("/", "").replace(":USDT", ""),
        "_broker_rpg_v1_norm_side": lambda value: str(value or "").upper(),
        "round_float": lambda value, _digits, default: float(value) if value is not None else default,
        "_broker_rpg_v1_open_positions_count": lambda: {
            "ok": True, "count": 0, "open_items": [], "positions_checked": True,
        },
        "agora_sp_str": lambda: "TEST",
    }
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(BROKER_SOURCE), "exec"), namespace)
    return namespace


def _validate(namespace):
    return namespace["broker_real_pilot_guard_v1_validate"](
        symbol="BTCUSDT", side="BUY", bot="DONKEY", notional_usdt=10.0,
        live_send_enabled=True,
    )


def test_live_entry_guard_blocks_when_persistent_space_is_below_margin(guard_namespace):
    guard_namespace["_broker_rpg_v1_persistent_disk_space"] = lambda: {
        "ok": True, "path": "/isolated-data", "total_bytes": 2_000_000_000,
        "used_bytes": 1_950_000_000, "free_bytes": 50_000_000,
    }

    result = _validate(guard_namespace)

    check = next(item for item in result["checks"] if item["code"] == "PERSISTENT_DISK_FREE_SPACE")
    assert result["allowed"] is False
    assert check["ok"] is False
    assert check["details"]["minimum_free_bytes"] == 256 * 1024 * 1024
    assert check["details"]["free_bytes"] == 50_000_000


def test_live_entry_guard_fails_closed_when_disk_space_cannot_be_measured(guard_namespace):
    guard_namespace["_broker_rpg_v1_persistent_disk_space"] = lambda: {
        "ok": False, "path": "/isolated-data", "error_type": "OSError",
    }

    result = _validate(guard_namespace)

    assert result["allowed"] is False
    assert "PERSISTENT_DISK_FREE_SPACE" in [item["code"] for item in result["checks"] if not item["ok"]]


def test_live_entry_guard_allows_sufficient_space(guard_namespace):
    guard_namespace["_broker_rpg_v1_persistent_disk_space"] = lambda: {
        "ok": True, "path": "/isolated-data", "total_bytes": 2_000_000_000,
        "used_bytes": 1_500_000_000, "free_bytes": 500_000_000,
    }

    result = _validate(guard_namespace)

    assert result["allowed"] is True
    assert next(item for item in result["checks"] if item["code"] == "PERSISTENT_DISK_FREE_SPACE")["ok"] is True


def test_reduce_only_close_remains_available_when_disk_is_low(guard_namespace):
    guard_namespace["_broker_rpg_v1_persistent_disk_space"] = lambda: {
        "ok": True, "path": "/isolated-data", "total_bytes": 2_000_000_000,
        "used_bytes": 1_999_000_000, "free_bytes": 1_000_000,
    }

    result = guard_namespace["broker_real_pilot_guard_v1_validate"](
        symbol="BTCUSDT", side="SELL", bot="DONKEY", notional_usdt=10.0,
        reduce_only=True, live_send_enabled=True,
    )

    assert result["allowed"] is True
    assert result["status"] == "BROKER_REAL_PILOT_REDUCE_ONLY_ALLOWED"
    assert result["checks"] == []


def test_paper_guard_does_not_apply_disk_entry_interlock(guard_namespace):
    guard_namespace["_broker_rpg_v1_persistent_disk_space"] = lambda: (_ for _ in ()).throw(AssertionError("must not inspect disk in PAPER"))

    result = guard_namespace["broker_real_pilot_guard_v1_validate"](
        symbol="BTCUSDT", side="BUY", bot="DONKEY", notional_usdt=10.0,
        live_send_enabled=False,
    )

    assert result["allowed"] is True
    assert result["applies"] is False


def test_disk_probe_reads_usage_without_writing(guard_namespace, tmp_path):
    guard_namespace["CENTRAL_DATA_DIR"] = tmp_path

    result = guard_namespace["_broker_rpg_v1_persistent_disk_space"]()

    assert result["ok"] is True
    assert result["path"] == str(tmp_path)
    assert result["total_bytes"] >= result["free_bytes"]
    assert list(tmp_path.iterdir()) == []


def test_disk_probe_sanitizes_measurement_failure(guard_namespace, monkeypatch, tmp_path):
    guard_namespace["CENTRAL_DATA_DIR"] = tmp_path
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: (_ for _ in ()).throw(OSError("sensitive filesystem detail")))

    result = guard_namespace["_broker_rpg_v1_persistent_disk_space"]()

    assert result == {
        "ok": False,
        "path": str(tmp_path),
        "error_type": "OSError",
    }
