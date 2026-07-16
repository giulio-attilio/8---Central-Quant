from __future__ import annotations

import ast
import copy
import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace


MAIN = Path("main.py")
_COMPILED_FUNCTIONS = None


def _load_functions(names, namespace):
    global _COMPILED_FUNCTIONS
    if _COMPILED_FUNCTIONS is None:
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        module = ast.Module(body=selected, type_ignores=[])
        ast.fix_missing_locations(module)
        _COMPILED_FUNCTIONS = compile(module, "main.py", "exec")
    exec(_COMPILED_FUNCTIONS, namespace)
    return namespace


class _Registry:
    def __init__(self, payload, file_path):
        self.payload = payload
        self.saved = 0
        self.TRADE_REGISTRY_FILE = str(file_path)
        self._lock = threading.RLock()

    def save_registry(self, payload):
        saved = copy.deepcopy(payload)
        self.payload.clear()
        self.payload.update(saved)
        self.saved += 1


def _event(trade_id, *, exit_price=101.0, mode="PAPER", sent=False):
    return {
        "kind": "PAPER_CLOSED",
        "key": f"EVENT:{trade_id}:{exit_price}",
        "raw_public": {
            "trade_id": trade_id,
            "bot": "PREDATOR",
            "execution_mode": mode,
            "sent": sent,
            "symbol": "BTCUSDT",
            "side": "LONG",
            "setup": "SMART_PREDATOR",
            "entry": 100.0,
            "exit_price": exit_price,
            "closed_at": "2026-07-16 10:00:00",
            "pnl_pct": exit_price - 100.0,
        },
    }


def _harness(
    tmp_path,
    *,
    events=None,
    mode="PAPER",
    execution_enabled=False,
    firewall=True,
    real_count=0,
    storage_ok=True,
    other_counts=None,
    existing_closed=None,
    max_per_cycle=3,
):
    events = list(events or [_event("PREDATOR-1")])
    registry = {"open_trades": {}, "closed_trades": copy.deepcopy(existing_closed or [])}
    storage = _Registry(registry, tmp_path / "trade_registry.json")
    state = {
        "status": "NEVER_RUN",
        "last_run": None,
        "last_attempt_epoch": 0.0,
        "last_repaired_count": 0,
        "total_repaired_count": 0,
        "pending_count": None,
        "last_error": None,
        "reason": "NOT_RUN",
    }

    def extract(event):
        return copy.deepcopy(event.get("raw_public") or {})

    def build(event):
        raw = extract(event)
        if not raw.get("trade_id") or raw.get("entry") is None or raw.get("exit_price") is None:
            return None
        return {
            "trade_id": raw["trade_id"],
            "bot": "PREDATOR",
            "setup": raw.get("setup"),
            "symbol": raw.get("symbol"),
            "side": raw.get("side"),
            "entry": raw.get("entry"),
            "exit_price": raw.get("exit_price"),
            "closed_at": raw.get("closed_at"),
            "status": "CLOSED",
            "pnl_pct": raw.get("pnl_pct"),
            "metadata": {},
        }

    def signature(trade):
        return "|".join(str(trade.get(key) or "") for key in (
            "bot", "setup", "symbol", "side", "closed_at", "entry", "exit_price"
        ))

    def counts(current):
        closed_ids = {str(item.get("trade_id")) for item in current.get("closed_trades") or []}
        explicit_ids = {
            str((item.get("raw_public") or {}).get("trade_id"))
            for item in events
            if (item.get("raw_public") or {}).get("trade_id")
        }
        base = {
            "module_open_count": 0,
            "registry_open_count": 0,
            "registry_closed_count": len(current.get("closed_trades") or []),
            "paper_closed_events_count": len(events),
            "missing_registry_open_count": 0,
            "orphan_registry_open_count": 0,
            "missing_registry_closed_count": len(explicit_ids.difference(closed_ids)),
            "open_field_issue_count": 0,
            "stale_open_count": 0,
            "duplicate_module_open_trade_id_count": 0,
            "duplicate_registry_open_trade_id_count": 0,
        }
        base.update(other_counts or {})
        return base

    def lifecycle(**kwargs):
        current_counts = counts(registry)
        has_blocker = any(current_counts.get(key) for key in (
            "missing_registry_open_count", "orphan_registry_open_count", "missing_registry_closed_count",
            "open_field_issue_count", "duplicate_module_open_trade_id_count", "duplicate_registry_open_trade_id_count",
        ))
        return {
            "status": "BLOCKED_FOR_LIFECYCLE_REVIEW" if has_blocker else "OK_WITH_WARNINGS",
            "mode": mode,
            "execution_enabled": execution_enabled,
            "execution_firewall_enabled": firewall,
            "counts": current_counts,
            "pnl_audit_summary": {"real_sent_or_live_event_count": real_count},
        }

    namespace = {
        "Path": Path,
        "copy": copy,
        "json": json,
        "os": os,
        "threading": threading,
        "time": time,
        "PREDATOR_AUDIT_REQUEST_SHARED_LIMIT": 2000,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_VERSION": "TEST-V1",
        "PREDATOR_AUTO_CLOSED_SYNC_V1_ACK": "PREDATOR_AUTO_CLOSED_SYNC_FIX",
        "PREDATOR_AUTO_CLOSED_SYNC_V1_ENABLED": True,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_MAX_PER_CYCLE": max_per_cycle,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_COOLDOWN_SECONDS": 300,
        "PREDATOR_AUTO_CLOSED_SYNC_V1_EVENTS_FILE": str(tmp_path / "auto_events.jsonl"),
        "PREDATOR_AUTO_CLOSED_SYNC_V1_LATEST_FILE": str(tmp_path / "auto_latest.json"),
        "_PREDATOR_AUTO_CLOSED_SYNC_V1_LOCK": threading.RLock(),
        "_PREDATOR_AUTO_CLOSED_SYNC_V1_STATE": state,
        "_pprsf_v1_now": lambda: "2026-07-16 10:30:00",
        "_pprsf_v1_extract_closed_raw": extract,
        "_pprsf_v1_build_closed_trade_from_event": build,
        "_pprsf_v1_closed_signature": signature,
        "_pprsf_v1_open_dict": lambda current: current.get("open_trades") or {},
        "_pprsf_v1_closed_list": lambda current: current.get("closed_trades") or [],
        "_pprsf_v1_registry_available": lambda: True,
        "_pprsf_v1_load_registry": lambda: (copy.deepcopy(registry), None),
        "_ppla_v1_get_closed_paper_events": lambda limit=0: (copy.deepcopy(events), {}),
        "_pprsf_v1_recalculate_lifecycle_counts_from_registry": counts,
        "predator_paper_lifecycle_audit_v1_status": lifecycle,
        "_pacs_v1_storage_status": lambda: {
            "ok": storage_ok,
            "reason": "PERSISTENT_STORAGE_READY" if storage_ok else "NON_PERSISTENT_STORAGE",
            "active_file": storage.TRADE_REGISTRY_FILE,
        },
        "central_trade_registry": storage,
    }
    _load_functions({
        "_pacs_v1_bool",
        "_pacs_v1_explicit_trade_id",
        "_pacs_v1_event_safety",
        "_pacs_v1_plan_closed_repairs",
        "_pacs_v1_lifecycle_blockers",
        "_pacs_v1_atomic_write_json",
        "_pacs_v1_write_audit",
        "_pacs_v1_health_overlay",
        "predator_auto_closed_sync_v1_status",
        "predator_auto_closed_sync_v1_tick",
    }, namespace)
    return namespace, registry, storage


def test_preview_does_not_modify_registry(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    before = copy.deepcopy(registry)
    result = ns["predator_auto_closed_sync_v1_status"]()
    assert result["status"] == "REPAIR_READY"
    assert registry == before and storage.saved == 0


def test_manual_commit_requires_exact_ack(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, ack="WRONG")
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert "ACK_REQUIRED" in result["blockers"]
    assert not registry["closed_trades"] and storage.saved == 0


def test_does_not_repair_outside_paper(tmp_path):
    ns, registry, _ = _harness(tmp_path, mode="VERIFY")
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert not registry["closed_trades"]


def test_does_not_repair_when_execution_is_enabled(tmp_path):
    ns, registry, _ = _harness(tmp_path, execution_enabled=True)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert not registry["closed_trades"]


def test_does_not_repair_real_or_sent_event(tmp_path):
    ns, registry, _ = _harness(tmp_path, events=[_event("LIVE-1", sent=True)], real_count=1)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert not registry["closed_trades"]
    assert any("real_sent_or_live_event_count" in item for item in result["blockers"])


def test_ambiguous_trade_id_is_fail_closed(tmp_path):
    events = [_event("AMB-1", exit_price=101), _event("AMB-1", exit_price=102)]
    ns, registry, _ = _harness(tmp_path, events=events)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["ambiguous_count"] == 1
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert not registry["closed_trades"]


def test_paper_closed_repair_is_idempotent(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    first = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    second = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert first["status"] == "REPAIRED" and first["repaired_count"] == 1
    assert second["status"] == "OK_ALREADY_SYNCED" and second["repaired_count"] == 0
    assert len(registry["closed_trades"]) == 1 and storage.saved == 1


def test_existing_closed_is_not_duplicated(tmp_path):
    existing = [{
        "trade_id": "PREDATOR-1", "bot": "PREDATOR", "setup": "SMART_PREDATOR",
        "symbol": "BTCUSDT", "side": "LONG", "entry": 100.0, "exit_price": 101.0,
        "closed_at": "2026-07-16 10:00:00", "status": "CLOSED", "pnl_pct": 1.0,
    }]
    ns, registry, storage = _harness(tmp_path, existing_closed=existing)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "OK_ALREADY_SYNCED"
    assert len(registry["closed_trades"]) == 1 and storage.saved == 0


def test_repairs_are_limited_per_cycle(tmp_path):
    events = [_event(f"PREDATOR-{index}", exit_price=101 + index) for index in range(4)]
    ns, registry, _ = _harness(tmp_path, events=events, max_per_cycle=2)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "REPAIRED_PARTIAL"
    assert result["repaired_count"] == 2 and result["pending_count"] == 2
    assert len(registry["closed_trades"]) == 2


def test_health_and_lifecycle_reflect_successful_repair(tmp_path):
    ns, _, _ = _harness(tmp_path)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    health = ns["_pacs_v1_health_overlay"]()
    assert result["after_lifecycle_counts"]["missing_registry_closed_count"] == 0
    assert result["after_lifecycle_status"] == "OK_WITH_WARNINGS"
    assert health["predator_auto_closed_sync_status"] == "REPAIRED"
    assert health["predator_auto_closed_sync_repaired_count"] == 1
    assert health["predator_auto_closed_sync_enabled"] is True


def test_nonpersistent_storage_blocks_repair(tmp_path):
    ns, registry, storage = _harness(tmp_path, storage_ok=False)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert "NON_PERSISTENT_STORAGE" in result["blockers"]
    assert not registry["closed_trades"] and storage.saved == 0


def test_other_lifecycle_divergence_blocks_repair(tmp_path):
    ns, registry, _ = _harness(tmp_path, other_counts={"orphan_registry_open_count": 1})
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert not registry["closed_trades"]


def test_audit_journal_records_repair_without_pnl_duplication(tmp_path):
    ns, registry, _ = _harness(tmp_path)
    result = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert result["repaired_count"] == 1
    assert len(registry["closed_trades"]) == 1
    lines = (tmp_path / "auto_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["repaired_trade_ids"] == ["PREDATOR-1"]


def test_repeated_automatic_block_does_not_spam_audit_journal(tmp_path):
    ns, _, _ = _harness(tmp_path, mode="LIVE")
    first = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    second = ns["predator_auto_closed_sync_v1_status"](commit=True, automatic=True)
    assert first["status"] == second["status"] == "BLOCKED_FAIL_CLOSED"
    lines = (tmp_path / "auto_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_implementation_has_no_broker_order_or_execution_engine_dependency():
    source = MAIN.read_text(encoding="utf-8")
    start = source.index("# PREDATOR AUTO CLOSED REGISTRY SYNC HARDENING V1")
    end = source.index('if __name__ == "__main__":', start)
    block = source[start:end]
    forbidden = (
        "central_broker", "broker.py", "place_order", "cancel_order", "close_position",
        "execution_engine", "execution_orchestrator", "ENABLE_REAL_TRADING", "BROKER_DRY_RUN",
    )
    assert all(item not in block for item in forbidden)


def test_required_endpoint_and_health_fields_are_exposed():
    source = MAIN.read_text(encoding="utf-8")
    assert '/predator/autoclosedsync/text' in source
    for field in (
        "predator_auto_closed_sync_status",
        "predator_auto_closed_sync_last_run",
        "predator_auto_closed_sync_repaired_count",
        "predator_auto_closed_sync_last_error",
        "predator_auto_closed_sync_enabled",
        "predator_auto_closed_sync_reason",
    ):
        assert field in source
