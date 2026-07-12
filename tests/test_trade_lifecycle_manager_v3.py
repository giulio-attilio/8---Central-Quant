from __future__ import annotations

import importlib
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


@pytest.fixture()
def manager(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "shadow"))
    sys.modules.pop("trade_lifecycle_manager", None)
    module = importlib.import_module("trade_lifecycle_manager")
    module.reset_shadow_storage(confirm=True)
    return module


def lifecycle_payload(suffix: str = "A", **updates):
    payload = {
        "lifecycle_id": f"LC-{suffix}",
        "trade_id": f"TR-{suffix}",
        "signal_id": f"SIG-{suffix}",
        "decision_id": f"DEC-{suffix}",
        "bot": "FALCON",
        "setup": "ORB",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
        "quantity_planned": 2.0,
    }
    payload.update(updates)
    return payload


def event(event_type: str, number: int, **evidence):
    return {
        "event_id": f"EV-{number}",
        "event_type": event_type,
        "source_component": "TEST",
        "occurred_at": f"2026-07-11T00:00:{number:02d}+00:00",
        "evidence": evidence,
        "payload": {},
    }


def create(manager, suffix: str = "A", **updates):
    result = manager.create_lifecycle(lifecycle_payload(suffix, **updates), persist=False)
    assert result["ok"]
    return result


def advance_to_submitting(manager, suffix: str = "A"):
    create(manager, suffix)
    lifecycle_id = f"LC-{suffix}"
    sequence = [
        ("DECISION_PENDING_RECORDED", 1, {}),
        ("DECISION_ALLOWED_RECORDED", 2, {}),
        ("RISK_PENDING_RECORDED", 3, {}),
        ("RISK_APPROVED_RECORDED", 4, {}),
        ("ENTRY_INTENT_CREATED", 5, {"client_order_id": f"CLIENT-{suffix}"}),
        ("ENTRY_SUBMITTED", 6, {"client_order_id": f"CLIENT-{suffix}"}),
    ]
    for event_type, number, evidence in sequence:
        result = manager.apply_event(lifecycle_id, event(event_type, number, **evidence), persist=False)
        assert result["ok"], result
    return lifecycle_id


def advance_to_entry_confirmed(manager, suffix: str = "A"):
    lifecycle_id = advance_to_submitting(manager, suffix)
    result = manager.apply_event(
        lifecycle_id,
        event("ENTRY_FILL_RECORDED", 7, fill_id=f"FILL-{suffix}-1", quantity=2.0, price=100.0, exchange_order_id=f"ORDER-{suffix}"),
        persist=False,
    )
    assert result["current_state"] == "ENTRY_CONFIRMED"
    return lifecycle_id


def stop_evidence(quantity: float = 2.0):
    return {
        "order_id": "STOP-1",
        "status": "OPEN",
        "side": "SELL",
        "trigger_price": 90.0,
        "protected_quantity": quantity,
        "timestamp": "2026-07-11T00:01:00+00:00",
    }


def advance_to_managed(manager, suffix: str = "A"):
    lifecycle_id = advance_to_entry_confirmed(manager, suffix)
    assert manager.apply_event(lifecycle_id, event("DISASTER_STOP_REQUESTED", 8), persist=False)["ok"]
    assert manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 9, **stop_evidence()), persist=False)["ok"]
    result = manager.apply_event(lifecycle_id, event("POSITION_MANAGEMENT_STARTED", 10), persist=False)
    assert result["current_state"] == "POSITION_MANAGED"
    return lifecycle_id


def advance_to_close_confirmed(manager, suffix: str = "A"):
    lifecycle_id = advance_to_managed(manager, suffix)
    assert manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)["ok"]
    result = manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id=f"CLOSE-{suffix}", quantity=2.0), persist=False)
    assert result["current_state"] == "CLOSE_CONFIRMED"
    return lifecycle_id


def test_01_import_creates_no_thread(tmp_path, monkeypatch):
    before = {thread.ident for thread in __import__("threading").enumerate()}
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "no-thread"))
    sys.modules.pop("trade_lifecycle_manager", None)
    importlib.import_module("trade_lifecycle_manager")
    after = {thread.ident for thread in __import__("threading").enumerate()}
    assert after == before


def test_02_import_makes_no_network_call(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "no-network"))
    sys.modules.pop("trade_lifecycle_manager", None)
    importlib.import_module("trade_lifecycle_manager")


def test_03_imports_no_broker_exchange_or_main(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path / "imports"))
    for name in ("trade_lifecycle_manager", "broker", "exchange_manager", "main", "ccxt", "requests"):
        sys.modules.pop(name, None)
    importlib.import_module("trade_lifecycle_manager")
    for name in ("broker", "exchange_manager", "main", "ccxt", "requests"):
        assert name not in sys.modules


def test_04_create_lifecycle(manager):
    result = create(manager)
    assert result["current_state"] == "SIGNAL_DETECTED"
    assert result["shadow_mode"] is True


def test_05_lifecycle_id_is_required(manager):
    payload = lifecycle_payload()
    payload.pop("lifecycle_id")
    result = manager.create_lifecycle(payload, persist=False)
    assert result["blocked"] and not result["ok"]


def test_06_ids_are_preserved(manager):
    result = create(manager)
    snapshot = result["snapshot"]
    assert (snapshot["signal_id"], snapshot["decision_id"], snapshot["trade_id"], snapshot["lifecycle_id"]) == ("SIG-A", "DEC-A", "TR-A", "LC-A")


def test_07_valid_transition(manager):
    create(manager)
    result = manager.apply_event("LC-A", event("DECISION_PENDING_RECORDED", 1), persist=False)
    assert result["event_applied"] and result["current_state"] == "DECISION_PENDING"


def test_08_invalid_transition_does_not_change_state(manager):
    create(manager)
    result = manager.apply_event("LC-A", event("ENTRY_SUBMITTED", 1, client_order_id="X"), persist=False)
    assert result["blocked"] and result["current_state"] == "SIGNAL_DETECTED"
    assert manager.get_lifecycle("LC-A")["snapshot"]["state"] == "SIGNAL_DETECTED"


def test_09_duplicate_event_is_idempotent(manager):
    create(manager)
    item = event("DECISION_PENDING_RECORDED", 1)
    assert manager.apply_event("LC-A", item, persist=False)["event_applied"]
    duplicate = manager.apply_event("LC-A", item, persist=False)
    assert duplicate["duplicate"] and not duplicate["event_applied"]


def test_10_partial_fill(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(lifecycle_id, event("ENTRY_FILL_RECORDED", 7, fill_id="F1", quantity=0.5, price=100), persist=False)
    assert result["current_state"] == "ENTRY_PARTIALLY_FILLED"
    assert result["snapshot"]["quantity_open"] == pytest.approx(0.5)


def test_11_full_fill(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert snapshot["quantity_filled"] == pytest.approx(2.0)
    assert snapshot["entry_price_confirmed"] == 100.0


def test_12_duplicate_fill_does_not_increment_quantity(manager):
    lifecycle_id = advance_to_submitting(manager)
    fill = event("ENTRY_FILL_RECORDED", 7, fill_id="F1", quantity=0.5, price=100)
    manager.apply_event(lifecycle_id, fill, persist=False)
    duplicate = manager.apply_event(lifecycle_id, fill, persist=False)
    assert duplicate["duplicate"]
    assert duplicate["snapshot"]["quantity_filled"] == pytest.approx(0.5)


def test_13_entry_submission_unknown(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(lifecycle_id, event("ENTRY_SUBMISSION_BECAME_UNKNOWN", 7), persist=False)
    assert result["current_state"] == "ENTRY_SUBMISSION_UNKNOWN"


def test_14_reconciliation_required(manager):
    lifecycle_id = advance_to_submitting(manager)
    manager.apply_event(lifecycle_id, event("ENTRY_SUBMISSION_BECAME_UNKNOWN", 7), persist=False)
    result = manager.mark_reconciliation_required(lifecycle_id, "timeout", {"client_order_id": "CLIENT-A"}, persist=False)
    assert result["current_state"] == "RECONCILIATION_REQUIRED"


def test_15_entry_confirmed_stop_missing(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    result = manager.apply_event(lifecycle_id, event("DISASTER_STOP_FAILED", 8, reason="rejected"), persist=False)
    assert result["current_state"] == "ENTRY_CONFIRMED_STOP_MISSING"


def test_16_disaster_stop_requires_and_accepts_full_evidence(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    blocked = manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 8, order_id="S"), persist=False)
    assert blocked["blocked"] and blocked["current_state"] == "ENTRY_CONFIRMED"
    confirmed = manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 9, **stop_evidence()), persist=False)
    assert confirmed["current_state"] == "ENTRY_PROTECTED"


def test_17_tp50_partial(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 11, quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 12, fill_id="TP1", quantity=0.5), persist=False)
    assert result["current_state"] == "TP50_PENDING"
    assert result["snapshot"]["quantity_open"] == pytest.approx(1.5)


def test_18_tp50_confirmed(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 11, quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 12, fill_id="TP1", quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("TP50_CONFIRMED", 13), persist=False)
    assert result["current_state"] == "TP50_CONFIRMED"


def test_19_runner_protected(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 11, quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 12, fill_id="TP1", quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_CONFIRMED", 13), persist=False)
    result = manager.apply_event(lifecycle_id, event("RUNNER_PROTECTION_CONFIRMED", 14, protected_quantity=1.0), persist=False)
    assert result["current_state"] == "RUNNER_PROTECTED"


def test_20_break_even(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("BREAK_EVEN_REQUESTED", 11, stop_price=100), persist=False)
    result = manager.apply_event(lifecycle_id, event("BREAK_EVEN_CONFIRMED", 12, stop_price=100), persist=False)
    assert result["current_state"] == "BREAK_EVEN_ACTIVE"


def test_21_trailing(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TRAILING_REQUESTED", 11, stop_price=105), persist=False)
    result = manager.apply_event(lifecycle_id, event("TRAILING_CONFIRMED", 12, stop_price=105), persist=False)
    assert result["current_state"] == "TRAILING_ACTIVE"


def test_22_close_partial(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id="C1", quantity=1.0), persist=False)
    assert result["current_state"] == "CLOSE_PARTIALLY_CONFIRMED"
    assert result["snapshot"]["quantity_open"] == pytest.approx(1.0)


def test_23_close_total(manager):
    lifecycle_id = advance_to_close_confirmed(manager)
    snapshot = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert snapshot["state"] == "CLOSE_CONFIRMED"
    assert snapshot["quantity_open"] == pytest.approx(0.0)


def test_24_outcome(manager):
    lifecycle_id = advance_to_close_confirmed(manager)
    result = manager.record_outcome(lifecycle_id, {"outcome_id": "OUT-1", "pnl_r": 1.2}, persist=False)
    assert result["current_state"] == "OUTCOME_RECORDED"
    assert result["snapshot"]["outcome_id"] == "OUT-1"


def test_25_learning_eligibility(manager):
    lifecycle_id = advance_to_close_confirmed(manager)
    manager.record_outcome(lifecycle_id, {"outcome_id": "OUT-1", "pnl_r": 1.2}, persist=False)
    result = manager.apply_event(lifecycle_id, event("LEARNING_ELIGIBILITY_CONFIRMED", 15), persist=False)
    assert result["current_state"] == "LEARNING_ELIGIBLE"


def test_26_recovery(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    manager.apply_event(lifecycle_id, event("DISASTER_STOP_FAILED", 8, reason="reject"), persist=False)
    required = manager.mark_recovery_required(lifecycle_id, "stop missing", persist=False)
    assert required["current_state"] == "RECOVERY_REQUIRED"
    completed = manager.apply_event(
        lifecycle_id,
        event("RECOVERY_COMPLETED", 9, target_state="ENTRY_PROTECTED", **stop_evidence()),
        persist=False,
    )
    assert completed["current_state"] == "ENTRY_PROTECTED"


def test_27_manual_position_remains_external(manager):
    payload = {"lifecycle_id": "EXT-A", "external_position": True, "symbol": "BTCUSDT", "side": "LONG", "bot": "FALCON", "quantity": 3}
    created = manager.create_lifecycle(payload, persist=False)
    assert created["snapshot"]["state"] == "MANUAL_POSITION_DETECTED"
    assert created["snapshot"]["trade_id"] == "" and created["snapshot"]["bot"] == ""
    classified = manager.apply_event("EXT-A", event("EXTERNAL_POSITION_CLASSIFIED", 1, classification="MANUAL"), persist=False)
    assert classified["current_state"] == "EXTERNAL_EXPOSURE_ONLY"


def test_28_two_bots_same_symbol_and_side_are_independent(manager):
    create(manager, "A", bot="FALCON")
    create(manager, "B", bot="DONKEY", symbol="BTCUSDT", side="LONG")
    manager.apply_event("LC-A", event("DECISION_PENDING_RECORDED", 1), persist=False)
    assert manager.get_lifecycle("LC-A")["snapshot"]["state"] == "DECISION_PENDING"
    assert manager.get_lifecycle("LC-B")["snapshot"]["state"] == "SIGNAL_DETECTED"


def test_29_compare_match_with_registry(manager):
    create(manager)
    snapshot = manager.get_lifecycle("LC-A")["snapshot"]
    registry = {"trade_id": "TR-A", "bot": "FALCON", "setup": "ORB", "symbol": "BTCUSDT", "side": "LONG", "mode": "LIVE", "state": snapshot["state"], "quantity_open": 0.0}
    result = manager.compare_with_registry("LC-A", registry)
    assert result["status"] == "MATCH"


def test_30_compare_divergence_with_registry(manager):
    create(manager)
    result = manager.compare_with_registry("LC-A", {"trade_id": "OTHER", "bot": "DONKEY"})
    assert result["status"] == "DIVERGENCE"
    assert result["differences"]


def test_31_persistence_and_reload(tmp_path, monkeypatch):
    data_dir = tmp_path / "reload"
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(data_dir))
    sys.modules.pop("trade_lifecycle_manager", None)
    module = importlib.import_module("trade_lifecycle_manager")
    module.create_lifecycle(lifecycle_payload(), persist=True)
    module = importlib.reload(module)
    assert module.get_lifecycle("LC-A")["snapshot"]["trade_id"] == "TR-A"


def test_32_snapshot_write_is_atomic(manager):
    manager.create_lifecycle(lifecycle_payload(), persist=True)
    assert manager.SNAPSHOT_FILE.exists()
    assert not manager.SNAPSHOT_FILE.with_suffix(manager.SNAPSHOT_FILE.suffix + ".tmp").exists()
    assert json.loads(manager.SNAPSHOT_FILE.read_text(encoding="utf-8"))["schema_version"] == 1


def test_33_corrupt_file_is_reported(tmp_path, monkeypatch):
    data_dir = tmp_path / "corrupt"
    data_dir.mkdir()
    (data_dir / "trade_lifecycle_shadow_snapshot.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(data_dir))
    sys.modules.pop("trade_lifecycle_manager", None)
    module = importlib.import_module("trade_lifecycle_manager")
    health = module.trade_lifecycle_health()
    assert not health["ok"] and "snapshot_load_error" in health["last_error"]


def test_34_basic_concurrency_is_idempotent(manager):
    create(manager)
    item = event("DECISION_PENDING_RECORDED", 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: manager.apply_event("LC-A", item, persist=False), range(2)))
    assert sum(bool(result["event_applied"]) for result in results) == 1
    assert sum(bool(result["duplicate"]) for result in results) == 1


def test_35_reset_requires_confirmation(manager):
    create(manager)
    denied = manager.reset_shadow_storage()
    assert not denied["ok"] and manager.get_lifecycle("LC-A")["ok"]
    accepted = manager.reset_shadow_storage(confirm=True)
    assert accepted["ok"] and not manager.get_lifecycle("LC-A")["ok"]


def test_36_public_operations_make_no_external_call(manager, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("external call attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    create(manager)
    manager.apply_event("LC-A", event("DECISION_PENDING_RECORDED", 1), persist=True)
    health = manager.trade_lifecycle_health()
    assert health["shadow_mode"] and "Broker" in " ".join(health["notes"])


def test_37_close_fill_above_open_quantity_is_blocked(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id="OVER", quantity=2.1), persist=False)
    assert result["blocked"] and not result["event_applied"]


def test_38_overclose_does_not_add_fill_id(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id="OVER", quantity=3.0), persist=False)
    assert "OVER" not in result["snapshot"]["fill_ids"]


def test_39_overclose_preserves_quantities_and_state(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)
    before = manager.get_lifecycle(lifecycle_id)["snapshot"]
    result = manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id="OVER", quantity=3.0), persist=False)
    assert result["current_state"] == before["state"]
    assert result["snapshot"]["quantity_open"] == before["quantity_open"]
    assert result["snapshot"]["quantity_closed"] == before["quantity_closed"]


def test_40_tp50_fill_above_open_quantity_is_blocked(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 11, quantity=3.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 12, fill_id="TP-OVER", quantity=2.1), persist=False)
    assert result["blocked"]


def test_41_tp50_fill_above_requested_quantity_is_blocked(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 11, quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 12, fill_id="TP-OVER", quantity=1.1), persist=False)
    assert result["blocked"]


def test_42_entry_partial_recorded_updates_quantities(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(lifecycle_id, event("ENTRY_PARTIAL_RECORDED", 7, fill_id="EP-1", quantity=0.5, price=100), persist=False)
    assert result["current_state"] == "ENTRY_PARTIALLY_FILLED"
    assert result["snapshot"]["quantity_filled"] == pytest.approx(0.5)
    assert result["snapshot"]["quantity_open"] == pytest.approx(0.5)


def test_43_entry_partial_recorded_requires_fill_id(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(lifecycle_id, event("ENTRY_PARTIAL_RECORDED", 7, quantity=0.5), persist=False)
    assert result["blocked"]


def test_44_entry_partial_recorded_cannot_complete_planned_quantity(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(lifecycle_id, event("ENTRY_PARTIAL_RECORDED", 7, fill_id="EP-FULL", quantity=2.0), persist=False)
    assert result["blocked"] and result["snapshot"]["quantity_filled"] == 0.0


def test_45_close_partial_recorded_updates_quantities(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_PARTIAL_RECORDED", 12, fill_id="CP-1", quantity=0.5), persist=False)
    assert result["current_state"] == "CLOSE_PARTIALLY_CONFIRMED"
    assert result["snapshot"]["quantity_closed"] == pytest.approx(0.5)
    assert result["snapshot"]["quantity_open"] == pytest.approx(1.5)


def test_46_close_partial_recorded_requires_fill_id(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=1.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_PARTIAL_RECORDED", 12, quantity=0.5), persist=False)
    assert result["blocked"]


def test_47_close_partial_recorded_cannot_zero_position(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)
    result = manager.apply_event(lifecycle_id, event("CLOSE_PARTIAL_RECORDED", 12, fill_id="CP-FULL", quantity=2.0), persist=False)
    assert result["blocked"] and result["snapshot"]["quantity_open"] == pytest.approx(2.0)


def test_48_equal_events_without_ids_or_times_are_deduplicated(manager):
    create(manager)
    item = {"event_type": "DECISION_PENDING_RECORDED", "source_component": "TEST", "evidence": {}, "payload": {}}
    assert manager.apply_event("LC-A", item, persist=False)["event_applied"]
    assert manager.apply_event("LC-A", item, persist=False)["duplicate"]


def test_49_idless_events_with_different_content_are_not_deduplicated(manager):
    lifecycle_id = advance_to_submitting(manager)
    first = {"event_type": "ENTRY_FILL_RECORDED", "source_component": "TEST", "evidence": {"fill_id": "F-A", "quantity": 0.5}, "payload": {}}
    second = {"event_type": "ENTRY_FILL_RECORDED", "source_component": "TEST", "evidence": {"fill_id": "F-B", "quantity": 0.5}, "payload": {}}
    assert manager.apply_event(lifecycle_id, first, persist=False)["event_applied"]
    result = manager.apply_event(lifecycle_id, second, persist=False)
    assert result["event_applied"] and not result["duplicate"]


def test_50_repeated_blocked_event_is_duplicate(manager):
    create(manager)
    blocked = event("ENTRY_SUBMITTED", 1, client_order_id="X")
    assert manager.apply_event("LC-A", blocked, persist=False)["blocked"]
    repeated = manager.apply_event("LC-A", blocked, persist=False)
    assert repeated["duplicate"] and not repeated["event_applied"]


def test_51_repeated_blocked_event_creates_no_second_divergence(manager):
    create(manager)
    blocked = event("ENTRY_SUBMITTED", 1, client_order_id="X")
    manager.apply_event("LC-A", blocked, persist=False)
    before = len(manager.get_lifecycle("LC-A")["snapshot"]["divergences"])
    manager.apply_event("LC-A", blocked, persist=False)
    after = len(manager.get_lifecycle("LC-A")["snapshot"]["divergences"])
    assert after == before == 1


def test_52_repeated_blocked_event_does_not_increment_divergence_count(manager):
    create(manager)
    blocked = event("ENTRY_SUBMITTED", 1, client_order_id="X")
    manager.apply_event("LC-A", blocked, persist=False)
    before = manager.trade_lifecycle_health()["divergence_count"]
    manager.apply_event("LC-A", blocked, persist=False)
    assert manager.trade_lifecycle_health()["divergence_count"] == before


def test_53_blocked_event_preserves_quantity_invariants(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 11, quantity=2.0), persist=False)
    before = manager.get_lifecycle(lifecycle_id)["snapshot"]
    manager.apply_event(lifecycle_id, event("CLOSE_FILL_RECORDED", 12, fill_id="OVER", quantity=9.0), persist=False)
    after = manager.get_lifecycle(lifecycle_id)["snapshot"]
    assert after["quantity_filled"] == before["quantity_filled"]
    assert after["quantity_closed"] == before["quantity_closed"]
    assert after["quantity_open"] == pytest.approx(after["quantity_filled"] - after["quantity_closed"])
