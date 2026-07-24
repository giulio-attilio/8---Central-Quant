from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from trade_registry import (
    closed_trade_identity_state as _canonical_closed_trade_identity_state,
    merge_closed_trade_records as _canonical_merge_closed_trade_records,
)


MAIN = Path("main.py")


def _functions(names, namespace):
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "main.py", "exec"), namespace)
    return namespace


class Registry:
    def __init__(self, payload):
        self.payload = payload
        self.saved = 0

    def save_registry(self, payload):
        value = copy.deepcopy(payload)
        self.payload.clear()
        self.payload.update(value)
        self.saved += 1


def _trade(trade_id, *, mode="PAPER", status="OPEN", bot="PREDATOR", pnl_marker=False):
    item = {
        "trade_id": trade_id,
        "bot": bot,
        "setup": "SMART_PREDATOR",
        "symbol": f"{trade_id}USDT",
        "side": "LONG",
        "status": status,
        "entry": 100,
        "qty": 1,
        "lifecycle_id": f"LC-{trade_id}",
        "client_order_id": f"CLIENT-{trade_id}",
        "order_id": f"ORDER-{trade_id}",
        "metadata": {"execution_mode": mode},
    }
    if pnl_marker:
        item["pnl_pct"] = 9.9
    return item


def _harness(tmp_path, *, existing_closed_same_id=False, audit_mode="PAPER", execution_enabled=False, firewall=True):
    valid = _trade("VALID")
    orphan = _trade("ORPHAN", pnl_marker=True)
    other_bot = _trade("OTHER", bot="FALCON")
    closed = [_trade("ORPHAN", status="CLOSED", pnl_marker=True)] if existing_closed_same_id else []
    registry = {"open_trades": {"VALID": valid, "ORPHAN": orphan, "OTHER": other_bot}, "closed_trades": closed}
    storage = Registry(registry)
    module_positions = [copy.deepcopy(valid)]

    def trade_id(item):
        return str(item.get("trade_id") or "")

    def trade_key(item):
        return "|".join(str(item.get(key) or "") for key in ("bot", "setup", "symbol", "side"))

    def recount(current):
        predator_open = [item for item in current["open_trades"].values() if item.get("bot") == "PREDATOR"]
        module_ids = {trade_id(item) for item in module_positions}
        return {
            "module_open_count": len(module_positions),
            "registry_open_count": len(predator_open),
            "registry_closed_count": len([item for item in current["closed_trades"] if item.get("bot") == "PREDATOR"]),
            "missing_registry_open_count": 0,
            "orphan_registry_open_count": len([item for item in predator_open if trade_id(item) not in module_ids]),
            "missing_registry_closed_count": 0,
        }

    state = {"status": "NEVER_RUN", "pending": None, "planned": 0, "repaired": 0, "last_run": None, "last_error": None}
    namespace = {
        "Path": Path,
        "json": json,
        "PREDATOR_ORPHAN_OPEN_FIX_V1_VERSION": "TEST-V1",
        "PREDATOR_ORPHAN_OPEN_FIX_V1_EVENTS_FILE": str(tmp_path / "events.jsonl"),
        "PREDATOR_ORPHAN_OPEN_FIX_V1_LATEST_FILE": str(tmp_path / "latest.json"),
        "_PREDATOR_ORPHAN_OPEN_FIX_V1_STATE": state,
        "_pprsf_v1_now": lambda: "2026-07-14 09:00",
        "_pprsf_v1_load_registry": lambda: (registry, None),
        "_pprsf_v1_open_dict": lambda current: current["open_trades"],
        "_pprsf_v1_closed_list": lambda current: current["closed_trades"],
        "_pprsf_v1_public": lambda value, **kwargs: copy.deepcopy(value),
        "_ppla_v1_get_trade_id": trade_id,
        "_ppla_v1_trade_key": trade_key,
        "_ppla_v1_get_predator_module_positions_raw": lambda: copy.deepcopy(module_positions),
        "predator_paper_lifecycle_audit_v1_status": lambda **kwargs: {
            "mode": audit_mode,
            "execution_enabled": execution_enabled,
            "execution_firewall_enabled": firewall,
            "counts": recount(registry),
        },
        "_pprsf_v1_recalculate_lifecycle_counts_from_registry": recount,
        "_closed_trade_identity_state_v1": (
            _canonical_closed_trade_identity_state
        ),
        "_merge_closed_trade_records_v1": (
            _canonical_merge_closed_trade_records
        ),
        "central_trade_registry": storage,
    }
    _functions({
        "_closed_trade_record_relation_v1",
        "_closed_trade_records_equivalent_v1",
        "_poof_v1_trade_mode",
        "_poof_v1_plan_orphans",
        "predator_registry_orphan_open_fix_v1_status",
        "build_predator_registry_orphan_open_fix_v1_text",
    }, namespace)
    return namespace, registry, storage


def test_preview_does_not_change_registry(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    before = copy.deepcopy(registry)
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=False)
    assert result["status"] == "REPAIR_READY"
    assert result["orphan_open_planned_count"] == 1
    assert registry == before and storage.saved == 0
    assert not (tmp_path / "events.jsonl").exists()


def test_commit_requires_exact_ack(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="WRONG")
    assert result["status"] == "COMMIT_BLOCKED"
    assert result["committed"] is False
    assert "ORPHAN" in registry["open_trades"] and storage.saved == 0


def test_commit_reconciles_only_orphan_predator_paper_open(tmp_path):
    ns, registry, storage = _harness(tmp_path)
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    assert result["status"] == "REPAIRED" and result["committed"] is True
    assert "ORPHAN" not in registry["open_trades"]
    assert "VALID" in registry["open_trades"]
    assert "OTHER" in registry["open_trades"]
    assert storage.saved == 1
    reconciled = next(item for item in registry["closed_trades"] if item["trade_id"] == "ORPHAN")
    assert reconciled["close_reason"] == "ORPHAN_REGISTRY_OPEN_RECONCILED"
    assert "pnl_pct" not in reconciled and "result_pct" not in reconciled
    assert reconciled["metadata"] == {
        "execution_mode": "PAPER",
        "sync_version": "TEST-V1",
        "synced_at": "2026-07-14 09:00",
        "source": "predator_orphan_open_fix_v1",
        "reason": "REGISTRY_OPEN_WITHOUT_MODULE_POSITION",
        "previous_status": "OPEN",
    }


def test_existing_closed_is_not_duplicated_or_recounted_in_pnl(tmp_path):
    ns, registry, _ = _harness(tmp_path, existing_closed_same_id=True)
    before_pnl = registry["closed_trades"][0]["pnl_pct"]
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    matching = [item for item in registry["closed_trades"] if item["trade_id"] == "ORPHAN"]
    assert result["orphan_open_repaired_count"] == 1
    assert len(matching) == 1 and matching[0]["pnl_pct"] == before_pnl


def test_after_lifecycle_has_zero_orphan_open(tmp_path):
    ns, _, _ = _harness(tmp_path)
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    assert result["after_lifecycle_counts"]["orphan_registry_open_count"] == 0
    assert result["orphan_open_pending_count"] == 0


def test_second_commit_is_idempotent(tmp_path):
    ns, registry, _ = _harness(tmp_path)
    first = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    second = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    assert first["orphan_open_repaired_count"] == 1
    assert second["orphan_open_repaired_count"] == 0
    assert len([item for item in registry["closed_trades"] if item["trade_id"] == "ORPHAN"]) == 1


def test_non_paper_orphan_is_skipped(tmp_path):
    ns, registry, _ = _harness(tmp_path)
    registry["open_trades"]["ORPHAN"]["metadata"]["execution_mode"] = "LIVE"
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    assert result["orphan_open_repaired_count"] == 0
    assert "ORPHAN" in registry["open_trades"]
    assert any(item["reason"] == "NOT_CONFIRMED_PAPER" for item in result["samples"]["skipped"])


def test_commit_is_blocked_unless_runtime_safety_is_explicitly_paper(tmp_path):
    ns, registry, storage = _harness(tmp_path, audit_mode="LIVE", execution_enabled=True, firewall=False)
    result = ns["predator_registry_orphan_open_fix_v1_status"](commit=True, ack="PREDATOR_ORPHAN_OPEN_FIX")
    assert result["status"] == "COMMIT_BLOCKED"
    assert result["committed"] is False
    assert "ORPHAN" in registry["open_trades"] and storage.saved == 0


def test_text_report_contains_safety_and_lifecycle_fields(tmp_path):
    ns, _, _ = _harness(tmp_path)
    text = ns["build_predator_registry_orphan_open_fix_v1_text"]()
    assert "execution_enabled" in text
    assert "Lifecycle antes" in text and "Lifecycle depois" in text
    assert "PREDATOR_ORPHAN_OPEN_FIX" in text


def test_implementation_contains_no_broker_or_order_calls():
    source = MAIN.read_text(encoding="utf-8")
    start = source.index("# PREDATOR REGISTRY ORPHAN OPEN CLEANUP V1")
    end = source.index("# TRADE REGISTRY PERSISTENT STORAGE FIX V1", start)
    block = source[start:end]
    forbidden = ("central_broker", "place_market_order", "cancel_order", "close_position", "ENABLE_REAL_TRADING", "BROKER_DRY_RUN")
    assert all(item not in block for item in forbidden)


def test_bots_overlay_exposes_required_fields():
    source = MAIN.read_text(encoding="utf-8")
    for field in (
        "predator_orphan_open_fix_status",
        "predator_orphan_open_pending_count",
        "predator_orphan_open_planned_count",
        "predator_orphan_open_repaired_count",
        "predator_orphan_open_fix_last_run",
        "predator_orphan_open_fix_last_error",
    ):
        assert field in source
