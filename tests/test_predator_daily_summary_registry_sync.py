from __future__ import annotations

import ast
import copy
import importlib
import json
import sys
import types
from pathlib import Path

import pytest


def _function_from_main(name: str, namespace: dict):
    source = Path("main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name)
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "main.py", "exec"), namespace)
    return namespace[name]


@pytest.fixture()
def summary_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    sys.modules.pop("predator_daily_summary", None)
    return importlib.import_module("predator_daily_summary")


def _entry(date="2026-07-12", side="LONG", score=95):
    return {"event": "ENTRY", "date": date, "datetime": f"{date} 10:00:00", "symbol": "BTCUSDT", "side": side, "score": score, "entry": 100}


def _close(date="2026-07-12", event="TRAIL", pnl=1.2):
    return {"event": event, "date": date, "datetime": f"{date} 15:00:00", "symbol": "BTCUSDT", "side": "LONG", "entry": 100, "exit": 101, "pnl_pct": pnl, "pnl_r": 1.5, "mfe_max_pct": 2.0, "mae_min_pct": -0.2, "mfe_gave_back_pct": 0.8}


def test_01_daily_summary_survives_restart(summary_module, monkeypatch):
    summary_module.append_predator_event(_entry())
    summary_module.append_predator_event(_close())
    sys.modules.pop("predator_daily_summary", None)
    reloaded = importlib.import_module("predator_daily_summary")
    metrics = reloaded.build_daily_metrics("2026-07-12")
    assert metrics["signals_h1"] == 1 and metrics["closed"] == 1


def test_02_daily_summary_does_not_zero_existing_log(summary_module):
    summary_module.append_predator_event(_entry())
    metrics = summary_module.build_daily_metrics("2026-07-12", memory_events=[])
    assert metrics["events_count"] == 1 and metrics["signals_h1"] == 1


def test_03_daily_summary_warns_when_source_incomplete(summary_module):
    metrics = summary_module.build_daily_metrics("2026-07-12", memory_events=[_entry()])
    assert metrics["warning_count"] > 0
    assert any("incompleto" in warning.lower() or "não existe" in warning.lower() for warning in metrics["warnings"])


class _Registry:
    def __init__(self, registry):
        self.registry = registry
        self.saved = 0

    def save_registry(self, registry):
        saved = copy.deepcopy(registry)
        self.registry.clear()
        self.registry.update(saved)
        self.saved += 1


def _repair_harness(tmp_path, closed_event=None):
    registry = {"open_trades": {}, "closed_trades": []}
    storage = _Registry(registry)
    event = closed_event or {"id": "E1"}

    def build(ev):
        if ev.get("safe"):
            return None
        return {"trade_id": "PREDATOR:CLOSED:1", "bot": "PREDATOR", "setup": "SMART_PREDATOR", "symbol": "BTCUSDT", "side": "LONG", "entry": 100, "exit_price": 101, "closed_at": "2026-07-12 15:00", "close_reason": "TRAIL", "pnl_pct": 1.0}

    def existing(reg):
        ids = {str(x.get("trade_id")) for x in reg["closed_trades"]}
        sigs = {"|".join(str(x.get(k) or "") for k in ("bot", "setup", "symbol", "side", "closed_at", "close_reason", "entry", "exit_price")) for x in reg["closed_trades"]}
        return ids, set(), sigs

    class _NoopStage:
        def __enter__(self):
            return self

        def finish(self, value=None, **kwargs):
            return value

        def __exit__(self, exc_type, exc, tb):
            return False

    namespace = {
        "request_cached_predator_audit": lambda audit: lambda function: function,
        "observe_predator_audit": lambda audit: lambda function: function,
        "predator_audit_stage": lambda *args, **kwargs: _NoopStage(),
        "PREDATOR_AUDIT_REQUEST_SHARED_LIMIT": 2000,
        "PREDATOR_PAPER_REGISTRY_SYNC_FIX_V1_VERSION": "TEST",
        "PREDATOR_PAPER_REGISTRY_SYNC_FIX_V1_EVENTS_FILE": str(tmp_path / "repair_events.jsonl"),
        "PREDATOR_PAPER_REGISTRY_SYNC_FIX_V1_LATEST_FILE": str(tmp_path / "repair_latest.json"),
        "_pprsf_v1_epoch_now": lambda: 1.0,
        "_pprsf_v1_now": lambda: "2026-07-12 16:00",
        "_pprsf_v1_load_registry": lambda: (registry, None),
        "predator_paper_lifecycle_audit_v1_status": lambda **kwargs: {"samples": {}, "counts": {}, "mode": "PAPER", "execution_enabled": False, "execution_firewall_enabled": True},
        "_ppla_v1_get_predator_module_positions_raw": lambda: [],
        "_ppla_v1_get_closed_paper_events": lambda limit=0: ([event], {}),
        "_pprsf_v1_existing_ids_and_signatures": existing,
        "_pprsf_v1_open_dict": lambda reg: reg["open_trades"],
        "_pprsf_v1_closed_list": lambda reg: reg["closed_trades"],
        "_pprsf_v1_build_open_trade_from_position": lambda pos: None,
        "_pprsf_v1_build_closed_trade_from_event": build,
        "_pprsf_v1_signature_trade": lambda trade: "open",
        "_pprsf_v1_closed_signature": lambda trade: "|".join(str(trade.get(k) or "") for k in ("bot", "setup", "symbol", "side", "closed_at", "close_reason", "entry", "exit_price")),
        "_pprsf_v1_public": lambda value, **kwargs: value,
        "central_trade_registry": storage,
        "Path": Path,
        "json": json,
    }
    fn = _function_from_main("predator_paper_registry_sync_fix_v1_status", namespace)
    return fn, registry, storage


def test_04_registry_repair_creates_pending_closed_on_commit(tmp_path):
    fn, registry, storage = _repair_harness(tmp_path)
    result = fn(commit=True, ack="PREDATOR_REGISTRY_SYNC_FIX")
    assert result["closed_repaired_count"] == 1 and len(registry["closed_trades"]) == 1 and storage.saved == 1


def test_05_registry_repair_preview_does_not_change_registry(tmp_path):
    fn, registry, storage = _repair_harness(tmp_path)
    result = fn(commit=False)
    assert result["status"] == "REPAIR_READY" and registry["closed_trades"] == [] and storage.saved == 0


def test_06_registry_repair_is_idempotent(tmp_path):
    fn, registry, storage = _repair_harness(tmp_path)
    first = fn(commit=True, ack="PREDATOR_REGISTRY_SYNC_FIX")
    second = fn(commit=True, ack="PREDATOR_REGISTRY_SYNC_FIX")
    assert first["closed_repaired_count"] == 1 and second["closed_repaired_count"] == 0 and len(registry["closed_trades"]) == 1


def test_07_safe_dry_run_is_not_repaired(tmp_path):
    fn, registry, storage = _repair_harness(tmp_path, {"safe": True})
    result = fn(commit=True, ack="PREDATOR_REGISTRY_SYNC_FIX")
    assert result["closed_repaired_count"] == 0 and registry["closed_trades"] == []


def _sync_report(awareness):
    namespace = {"_mpa_v1_build_payload": lambda: awareness, "data_hora_sp_str": lambda: "12/07/2026 10:00"}
    return _function_from_main("build_sync_report", namespace)()


def test_08_sync_classifies_bingx_only_as_manual_external():
    report = _sync_report({"status": "MANUAL_OR_EXTERNAL_POSITION_PRESENT", "summary": {"broker_bingx_open_count": 1, "central_live_count": 0}, "matched_positions": [], "central_only_positions": [], "manual_or_external_positions": [{"symbol": "ETHUSDT", "side": "LONG", "broker_position": {"notional": 20, "entry_price": 2000}}]})
    assert "MANUAL_OR_EXTERNAL_POSITION_PRESENT" in report and "Manual/externa: ETHUSDT LONG" in report


def _live_counts(request_symbol, broker_symbol, central=None):
    fake_broker = types.SimpleNamespace(get_positions=lambda: [{"symbol": broker_symbol, "side": "LONG", "contracts": 1, "notional": 20}])
    namespace = {
        "_rpg_safe_norm_symbol": lambda value: str(value or "").replace("/", "").upper(),
        "_rpg_safe_norm_side": lambda value: str(value or "").upper(),
        "_rpg_safe_float": lambda value, default=0.0: float(value or default),
        "_rpg_safe_int": lambda value, default=0: int(value or default),
        "_central_live_positions_payload": lambda: central or [],
        "registry_mode_segregation_v1_gate_check": lambda payload: {"real_open_count": 0, "unknown_open_count": 0, "ok": True},
        "central_broker": fake_broker,
        "MANUAL_POSITION_OWNERSHIP_ISOLATION_V1_VERSION": "TEST",
    }
    fn = _function_from_main("_rpg_safe_live_counts", namespace)
    return fn({"symbol": request_symbol, "side": "LONG"})


def test_09_manual_other_symbol_does_not_block_falcon():
    counts = _live_counts("BTCUSDT", "ETHUSDT")
    assert counts["manual_external_blocks_falcon"] is False and counts["manual_same_symbol_side_count"] == 0


def test_10_manual_same_symbol_side_blocks_new_falcon_entry():
    counts = _live_counts("BTCUSDT", "BTCUSDT")
    assert counts["manual_same_symbol_side_count"] == 1


def test_11_central_only_remains_critical_divergence():
    report = _sync_report({"status": "CENTRAL_ONLY_RECONCILE_REQUIRED", "summary": {"broker_bingx_open_count": 0, "central_live_count": 1}, "matched_positions": [], "manual_or_external_positions": [], "central_only_positions": [{"symbol": "BTCUSDT", "side": "LONG"}]})
    assert "ALERTA CRÍTICO" in report and "Só na Central" in report


def test_12_matched_position_remains_matched():
    report = _sync_report({"status": "CENTRAL_LIVE_MATCHED", "summary": {"broker_bingx_open_count": 1, "central_live_count": 1}, "matched_positions": [{"symbol": "BTCUSDT", "side": "LONG"}], "manual_or_external_positions": [], "central_only_positions": []})
    assert "Casadas: 1" in report and "BTCUSDT LONG" in report
