from __future__ import annotations

import copy
import importlib
import json
import socket
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


def _reload(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, enabled: bool = True):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "shadow"))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_INGESTION_PERSIST", "true")
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DEAD_LETTER_ENABLED", "true")
    sys.modules.pop("trade_lifecycle_shadow_bridge", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    bridge = importlib.import_module("trade_lifecycle_shadow_bridge")
    bridge.reset_shadow_bridge_storage(confirm=True)
    bridge._manager.reset_shadow_storage(confirm=True)
    return bridge


@pytest.fixture()
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return _reload(tmp_path, monkeypatch)


def lifecycle_payload(**updates):
    value = {
        "lifecycle_id": "LC-A",
        "trade_id": "TR-A",
        "signal_id": "SIG-A",
        "decision_id": "DEC-A",
        "bot": "FALCON",
        "setup": "ORB",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
        "quantity_planned": 2.0,
    }
    value.update(updates)
    return value


def create(bridge, **updates):
    return bridge.emit_shadow_lifecycle_created(lifecycle_payload(**updates), source_component="TEST", persist=True)


def emit(bridge, event_type="DECISION_PENDING_RECORDED", **updates):
    args = {
        "lifecycle_id": "LC-A",
        "source_component": "TEST",
        "event_id": "EV-1",
        "evidence": {},
        "payload": {},
        "persist": True,
    }
    args.update(updates)
    return bridge.emit_shadow_event(event_type, **args)


def test_01_import_creates_no_thread(tmp_path, monkeypatch):
    before = {item.ident for item in threading.enumerate()}
    _reload(tmp_path, monkeypatch)
    assert {item.ident for item in threading.enumerate()} == before


def test_02_import_creates_no_directory(tmp_path, monkeypatch):
    target = tmp_path / "absent"
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(target))
    sys.modules.pop("trade_lifecycle_shadow_bridge", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    importlib.import_module("trade_lifecycle_shadow_bridge")
    assert not target.exists()


def test_03_import_creates_no_file(tmp_path, monkeypatch):
    target = tmp_path / "empty"
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(target))
    sys.modules.pop("trade_lifecycle_shadow_bridge", None)
    sys.modules.pop("trade_lifecycle_manager", None)
    importlib.import_module("trade_lifecycle_shadow_bridge")
    assert not list(target.glob("*")) if target.exists() else True


def test_04_import_uses_no_network(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    _reload(tmp_path, monkeypatch)


def test_05_imports_no_broker(tmp_path, monkeypatch):
    sys.modules.pop("broker", None)
    _reload(tmp_path, monkeypatch)
    assert "broker" not in sys.modules


def test_06_imports_no_exchange(tmp_path, monkeypatch):
    sys.modules.pop("exchange_manager", None)
    _reload(tmp_path, monkeypatch)
    assert "exchange_manager" not in sys.modules


def test_07_imports_no_main(tmp_path, monkeypatch):
    sys.modules.pop("main", None)
    _reload(tmp_path, monkeypatch)
    assert "main" not in sys.modules


def test_08_feature_flag_defaults_off(tmp_path, monkeypatch):
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED", raising=False)
    module = _reload(tmp_path, monkeypatch, enabled=False)
    monkeypatch.delenv("TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED", raising=False)
    assert module.shadow_bridge_health()["enabled"] is False


def test_09_disabled_does_not_forward(tmp_path, monkeypatch):
    module = _reload(tmp_path, monkeypatch, enabled=False)
    result = emit(module)
    assert result["status"] == "DISABLED" and not result["forwarded"]


def test_10_disabled_does_not_write(tmp_path, monkeypatch):
    module = _reload(tmp_path, monkeypatch, enabled=False)
    emit(module)
    assert not Path(module.shadow_bridge_health()["storage_paths"]["ingestion"]).exists()


def test_11_explicit_valid_lifecycle_creation(bridge):
    assert create(bridge)["status"] == "LIFECYCLE_CREATED"


def test_12_existing_lifecycle_is_duplicate(bridge):
    create(bridge)
    assert create(bridge)["status"] == "DUPLICATE"


def test_13_creation_without_lifecycle_id_is_dead_letter(bridge):
    assert create(bridge, lifecycle_id="")["status"] == "DEAD_LETTER"


def test_14_operational_creation_without_trade_id_is_dead_letter(bridge):
    assert create(bridge, trade_id="")["status"] == "DEAD_LETTER"


def test_15_manual_position_stays_external(bridge):
    result = bridge.emit_shadow_lifecycle_created(
        {"lifecycle_id": "EXT-1", "external_position": True, "bot": "FALCON", "symbol": "BTCUSDT", "side": "LONG"},
        source_component="AWARENESS",
    )
    snapshot = result["manager_result"]["snapshot"]
    assert snapshot["state"] == "MANUAL_POSITION_DETECTED" and snapshot["trade_id"] == "" and snapshot["bot"] == ""


def test_16_valid_event_is_forwarded(bridge):
    create(bridge)
    assert emit(bridge)["forwarded"]


def test_17_applied_event_returns_applied(bridge):
    create(bridge)
    assert emit(bridge)["status"] == "APPLIED"


def test_18_duplicate_event_returns_duplicate(bridge):
    create(bridge)
    emit(bridge)
    assert emit(bridge)["status"] == "DUPLICATE"


def test_19_blocked_event_returns_blocked(bridge):
    create(bridge)
    assert emit(bridge, "ENTRY_SUBMITTED")["status"] == "BLOCKED"


def test_20_blocked_event_creates_dead_letter(bridge):
    create(bridge)
    assert emit(bridge, "ENTRY_SUBMITTED")["dead_letter"]


def test_21_missing_lifecycle_creates_dead_letter(bridge):
    assert emit(bridge)["status"] == "DEAD_LETTER"


def test_22_missing_lifecycle_id_is_not_invented(bridge):
    result = emit(bridge, lifecycle_id="")
    assert result["dead_letter"] and result["lifecycle_id"] == ""


def test_23_missing_source_is_dead_letter(bridge):
    assert emit(bridge, source_component="")["status"] == "DEAD_LETTER"


def test_24_unknown_event_is_dead_letter(bridge):
    assert emit(bridge, "NOT_CANONICAL")["status"] == "DEAD_LETTER"


def test_25_invalid_evidence_type_raises(bridge):
    with pytest.raises(TypeError):
        emit(bridge, evidence=[])


def test_26_invalid_payload_type_raises(bridge):
    with pytest.raises(TypeError):
        emit(bridge, payload=[])


def test_27_invalid_persist_type_raises(bridge):
    with pytest.raises(TypeError):
        emit(bridge, persist="yes")


def test_28_manager_exception_returns_error(bridge, monkeypatch):
    create(bridge)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert emit(bridge)["status"] == "ERROR"


def test_29_manager_exception_does_not_escape(bridge, monkeypatch):
    create(bridge)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert emit(bridge)["operational_impact"] is False


def test_30_operational_impact_always_false(bridge):
    assert create(bridge)["operational_impact"] is False
    assert emit(bridge, lifecycle_id="")["operational_impact"] is False


def test_31_journal_contains_attempt(bridge):
    create(bridge)
    log = bridge.read_shadow_ingestion_log()
    assert log["count"] == 1 and log["items"][0]["status"] == "LIFECYCLE_CREATED"


def test_32_dead_letter_has_reason_code(bridge):
    emit(bridge, lifecycle_id="")
    assert bridge.read_shadow_dead_letters()["items"][0]["reason_code"] == "MISSING_LIFECYCLE_ID"


def test_33_correlation_id_is_auditable_and_stable(bridge):
    create(bridge)
    first = emit(bridge)
    second = emit(bridge)
    assert first["correlation_id"] == second["correlation_id"]
    assert first["correlation_id"].startswith("CENTRAL-SHADOW-BRIDGE-")


def test_34_external_event_id_is_preserved(bridge):
    create(bridge)
    result = emit(bridge, event_id="EXTERNAL-7")
    assert result["manager_result"]["snapshot"]["events_applied"][-1]["event_id"] == "EXTERNAL-7"


def test_35_input_dict_is_not_mutated(bridge):
    evidence = {"nested": {"x": 1}}
    payload = {"items": [1, 2]}
    before = copy.deepcopy((evidence, payload))
    emit(bridge, evidence=evidence, payload=payload)
    assert (evidence, payload) == before


def test_36_storage_is_lazy(tmp_path, monkeypatch):
    module = _reload(tmp_path, monkeypatch)
    target = Path(module.shadow_bridge_health()["storage_paths"]["ingestion"])
    assert not target.exists()


def test_37_journal_is_append_only(bridge):
    create(bridge)
    emit(bridge)
    path = Path(bridge.shadow_bridge_health()["storage_paths"]["ingestion"])
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2


def test_38_concurrent_writes_keep_valid_jsonl(bridge):
    create(bridge)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: emit(bridge, event_id=f"BAD-{i}", event_type="ENTRY_SUBMITTED"), range(8)))
    path = Path(bridge.shadow_bridge_health()["storage_paths"]["ingestion"])
    assert all(isinstance(json.loads(line), dict) for line in path.read_text(encoding="utf-8").splitlines())


def test_39_health_contains_all_counters(bridge):
    health = bridge.shadow_bridge_health()
    expected = {"events_received", "events_forwarded", "events_applied", "events_duplicate", "events_blocked", "events_dead_letter", "internal_errors"}
    assert expected <= health.keys()


def test_40_health_reflects_enabled(bridge, monkeypatch):
    assert bridge.shadow_bridge_health()["enabled"]
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_INGESTION_ENABLED", "off")
    assert not bridge.shadow_bridge_health()["enabled"]


def test_41_health_includes_manager_defensively(bridge, monkeypatch):
    monkeypatch.setattr(bridge._manager, "trade_lifecycle_health", lambda: (_ for _ in ()).throw(RuntimeError("health")))
    assert bridge.shadow_bridge_health()["lifecycle_manager"]["ok"] is False


def test_42_missing_journal_returns_empty(bridge):
    assert bridge.read_shadow_ingestion_log()["items"] == []


def test_43_corrupt_line_is_counted_without_losing_valid_lines(bridge):
    create(bridge)
    path = Path(bridge.shadow_bridge_health()["storage_paths"]["ingestion"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{broken\n")
    result = bridge.read_shadow_ingestion_log()
    assert result["invalid_lines"] == 1 and result["count"] == 1


def test_44_limit_returns_last_items(bridge):
    create(bridge)
    emit(bridge)
    assert bridge.read_shadow_ingestion_log(limit=1)["count"] == 1


def test_45_zero_limit_returns_empty(bridge):
    create(bridge)
    assert bridge.read_shadow_ingestion_log(limit=0)["items"] == []


def test_46_reset_requires_confirmation(bridge):
    assert bridge.reset_shadow_bridge_storage()["status"] == "CONFIRM_REQUIRED"


def test_47_reset_removes_only_bridge_files(bridge):
    create(bridge)
    paths = bridge.shadow_bridge_health()["storage_paths"]
    bridge.reset_shadow_bridge_storage(confirm=True)
    assert not Path(paths["ingestion"]).exists() and not Path(paths["dead_letters"]).exists()


def test_48_reset_does_not_remove_manager_storage(bridge):
    create(bridge)
    manager_path = bridge._manager.SNAPSHOT_FILE
    assert manager_path.exists()
    bridge.reset_shadow_bridge_storage(confirm=True)
    assert manager_path.exists()


def test_49_reset_zeros_counters(bridge):
    create(bridge)
    bridge.reset_shadow_bridge_storage(confirm=True)
    assert bridge.shadow_bridge_health()["events_received"] == 0


def test_50_public_operations_make_zero_external_calls(bridge, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    create(bridge)
    emit(bridge)


def test_51_registry_is_never_imported_or_changed(bridge):
    sys.modules.pop("trade_registry", None)
    create(bridge)
    assert "trade_registry" not in sys.modules


def test_52_no_automatic_runtime_integration(monkeypatch):
    isolated_modules = (
        "trade_lifecycle_shadow_bridge",
        "trade_lifecycle_manager",
        "main",
        "execution_engine",
        "execution_orchestrator",
    )
    for module_name in isolated_modules:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    importlib.import_module("trade_lifecycle_shadow_bridge")

    assert "main" not in sys.modules
    assert "execution_engine" not in sys.modules
    assert "execution_orchestrator" not in sys.modules


def test_53_emit_event_never_creates_lifecycle(bridge):
    emit(bridge)
    assert bridge._manager.trade_lifecycle_health()["lifecycle_count"] == 0


def test_54_out_of_order_event_stays_blocked(bridge):
    create(bridge)
    result = emit(bridge, "ENTRY_SUBMITTED")
    assert result["blocked"] and result["manager_result"]["current_state"] == "SIGNAL_DETECTED"


def test_55_dead_letter_never_schedules_retry(bridge):
    emit(bridge, lifecycle_id="")
    assert bridge.read_shadow_dead_letters()["items"][0]["retry_scheduled"] is False


def test_56_disabled_does_not_increment_forwarded(tmp_path, monkeypatch):
    module = _reload(tmp_path, monkeypatch, enabled=False)
    emit(module)
    assert module.shadow_bridge_health()["events_forwarded"] == 0


def test_57_duplicate_does_not_increment_applied(bridge):
    create(bridge)
    emit(bridge)
    before = bridge.shadow_bridge_health()["events_applied"]
    emit(bridge)
    assert bridge.shadow_bridge_health()["events_applied"] == before


def test_58_blocked_increments_blocked_once(bridge):
    create(bridge)
    emit(bridge, "ENTRY_SUBMITTED")
    before = bridge.shadow_bridge_health()["events_blocked"]
    emit(bridge, "ENTRY_SUBMITTED")
    assert before == 1 and bridge.shadow_bridge_health()["events_blocked"] == 1


def test_59_dead_letter_increments_once_per_attempt(bridge):
    emit(bridge, lifecycle_id="")
    assert bridge.shadow_bridge_health()["events_dead_letter"] == 1


def test_60_internal_error_increments_counter(bridge, monkeypatch):
    create(bridge)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    emit(bridge)
    assert bridge.shadow_bridge_health()["internal_errors"] == 1


def _force_ingestion_failure(bridge, monkeypatch):
    original = bridge._append

    def selective(path, record):
        if path.name == "trade_lifecycle_shadow_ingestion.jsonl":
            return "forced ingestion persistence failure"
        return original(path, record)

    monkeypatch.setattr(bridge, "_append", selective)


def _force_dead_letter_failure(bridge, monkeypatch):
    original = bridge._append

    def selective(path, record):
        if path.name == "trade_lifecycle_shadow_dead_letters.jsonl":
            return "forced dead letter persistence failure"
        return original(path, record)

    monkeypatch.setattr(bridge, "_append", selective)


def _event_with_failed_journal(bridge, monkeypatch):
    bridge.emit_shadow_lifecycle_created(lifecycle_payload(), source_component="TEST", persist=False)
    _force_ingestion_failure(bridge, monkeypatch)
    return emit(bridge)


def test_61_ingestion_journal_write_failure_returns_error(bridge, monkeypatch):
    assert _event_with_failed_journal(bridge, monkeypatch)["status"] == "ERROR"


def test_62_journal_failure_does_not_escape(bridge, monkeypatch):
    result = _event_with_failed_journal(bridge, monkeypatch)
    assert result["ok"] is False


def test_63_journal_failure_has_no_operational_impact(bridge, monkeypatch):
    assert _event_with_failed_journal(bridge, monkeypatch)["operational_impact"] is False


def test_64_journal_failure_preserves_manager_result(bridge, monkeypatch):
    result = _event_with_failed_journal(bridge, monkeypatch)
    assert result["manager_result"]["event_applied"] is True


def test_65_journal_failure_updates_last_error(bridge, monkeypatch):
    _event_with_failed_journal(bridge, monkeypatch)
    assert "forced ingestion" in bridge.shadow_bridge_health()["last_error"]


def test_66_journal_failure_makes_health_unhealthy(bridge, monkeypatch):
    _event_with_failed_journal(bridge, monkeypatch)
    assert bridge.shadow_bridge_health()["ok"] is False


def test_67_journal_failure_increments_internal_errors_once(bridge, monkeypatch):
    _event_with_failed_journal(bridge, monkeypatch)
    assert bridge.shadow_bridge_health()["internal_errors"] == 1


def test_68_dead_letter_write_failure_returns_error(bridge, monkeypatch):
    _force_dead_letter_failure(bridge, monkeypatch)
    assert emit(bridge, lifecycle_id="")["status"] == "ERROR"


def test_69_dead_letter_failure_preserves_dead_letter_true(bridge, monkeypatch):
    _force_dead_letter_failure(bridge, monkeypatch)
    assert emit(bridge, lifecycle_id="")["dead_letter"] is True


def test_70_dead_letter_failure_preserves_original_reason_code(bridge, monkeypatch):
    _force_dead_letter_failure(bridge, monkeypatch)
    result = emit(bridge, lifecycle_id="")
    assert result["dead_letter_reason_code"] == "MISSING_LIFECYCLE_ID"


def test_71_dead_letter_failure_schedules_no_retry(bridge, monkeypatch):
    _force_dead_letter_failure(bridge, monkeypatch)
    assert emit(bridge, lifecycle_id="")["retry_scheduled"] is False


def test_72_dead_letter_failure_increments_internal_errors_once(bridge, monkeypatch):
    _force_dead_letter_failure(bridge, monkeypatch)
    emit(bridge, lifecycle_id="")
    assert bridge.shadow_bridge_health()["internal_errors"] == 1


def test_73_unexpected_manager_result_returns_error(bridge, monkeypatch):
    bridge.emit_shadow_lifecycle_created(lifecycle_payload(), source_component="TEST", persist=False)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: {"ok": True, "status": "UNEXPECTED"})
    assert emit(bridge)["status"] == "ERROR"


def test_74_unexpected_manager_result_updates_last_error(bridge, monkeypatch):
    bridge.emit_shadow_lifecycle_created(lifecycle_payload(), source_component="TEST", persist=False)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: {"ok": True})
    emit(bridge)
    assert "unexpected_manager_result" in bridge.shadow_bridge_health()["last_error"]


def test_75_unexpected_manager_result_makes_health_unhealthy(bridge, monkeypatch):
    bridge.emit_shadow_lifecycle_created(lifecycle_payload(), source_component="TEST", persist=False)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: {})
    emit(bridge)
    assert bridge.shadow_bridge_health()["ok"] is False


def test_76_unexpected_manager_result_creates_dead_letter(bridge, monkeypatch):
    bridge.emit_shadow_lifecycle_created(lifecycle_payload(), source_component="TEST", persist=False)
    monkeypatch.setattr(bridge._manager, "apply_event", lambda *a, **k: {"ok": True, "status": "ODD"})
    result = emit(bridge)
    assert result["dead_letter"] and bridge.read_shadow_dead_letters()["items"][-1]["reason_code"] == "MANAGER_ERROR"


def _blocked_creation(bridge, monkeypatch):
    monkeypatch.setattr(
        bridge._manager,
        "create_lifecycle",
        lambda *a, **k: {
            "ok": False,
            "status": "INVALID_CONTRACT",
            "blocked": True,
            "duplicate": False,
            "reasons": ["blocked by manager"],
            "warnings": [],
            "trade_id": "TR-A",
        },
    )
    return create(bridge)


def test_77_blocked_creation_increments_blocked_counter(bridge, monkeypatch):
    _blocked_creation(bridge, monkeypatch)
    assert bridge.shadow_bridge_health()["events_blocked"] == 1


def test_78_blocked_creation_does_not_increment_applied(bridge, monkeypatch):
    _blocked_creation(bridge, monkeypatch)
    assert bridge.shadow_bridge_health()["events_applied"] == 0


def test_79_blocked_creation_increments_dead_letter_once(bridge, monkeypatch):
    result = _blocked_creation(bridge, monkeypatch)
    assert result["status"] == "DEAD_LETTER"
    assert bridge.shadow_bridge_health()["events_dead_letter"] == 1


def test_80_duplicate_markdown_document_was_removed():
    duplicate = Path("docs/internal/Trade-Lifecycle-Manager-V3.1-Shadow-Event-Ingestion.md.md")
    assert not duplicate.exists()
