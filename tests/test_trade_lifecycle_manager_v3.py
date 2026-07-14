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


def paper_event(event_type: str, number: int, **updates):
    opened = event_type == "PAPER_POSITION_OPENED"
    evidence = {
        "trade_id": "TR-A",
        "mode": "PAPER",
        "registry_source_component": "TRADE_REGISTRY",
        "registry_status": "OPEN" if opened else "CLOSED",
    }
    if not opened:
        evidence.update({"closed_at": "2026-07-13T21:30:35+00:00", "exit_price": 101.0})
    evidence.update(updates)
    return event(event_type, number, **evidence)


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


def registry_live_entry_confirmation(suffix: str = "A", **updates):
    evidence = {
        "registry_live_open_post_ack": True,
        "registry_source_component": "TRADE_REGISTRY",
        "registry_status": "OPEN",
        "mode": "LIVE",
        "execution_sent": True,
        "trade_id": f"TR-{suffix}",
        "client_order_id": f"CLIENT-{suffix}",
        "exchange_order_id": f"ORDER-{suffix}",
        "quantity": 2.0,
        "entry_price_theoretical": 100.0,
        "entry_price_reference": 100.25,
        "opened_at": "2026-07-14T11:00:22+00:00",
    }
    evidence.update(updates)
    return evidence


def broker_tp50_reduction(order_id: str = "TP50-ORDER-1", quantity: float = 0.5, **updates):
    evidence = {
        "broker_reduction_confirmed": True,
        "broker_order_id": order_id,
        "quantity": quantity,
    }
    evidence.update(updates)
    return evidence


def registry_live_close(suffix: str = "A", quantity: float = 2.0, **updates):
    evidence = {
        "registry_live_closed_factual": True,
        "registry_source_component": "TRADE_REGISTRY",
        "registry_status": "CLOSED",
        "mode": "LIVE",
        "trade_id": f"TR-{suffix}",
        "closed_at": "2026-07-14T12:32:04+00:00",
        "close_reason": "STOP_FAILSAFE_MARKET",
        "quantity": quantity,
        "exit_price": 77.621,
        "result_pct": -0.9218,
        "result_r": -1.0966,
    }
    evidence.update(updates)
    return evidence


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


def test_recovery_required_is_cleared_by_factual_disaster_stop_confirmation(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    manager.apply_event(lifecycle_id, event("DISASTER_STOP_FAILED", 8, reason="reject"), persist=False)
    manager.mark_recovery_required(lifecycle_id, "stop missing", persist=False)

    completed = manager.apply_event(
        lifecycle_id,
        event("DISASTER_STOP_CONFIRMED", 9, **stop_evidence()),
        persist=False,
    )

    assert completed["current_state"] == "ENTRY_PROTECTED"
    assert completed["snapshot"]["recovery"]["required"] is False
    assert completed["snapshot"]["recovery"]["completed"] is True
    assert completed["snapshot"]["recovery"]["completed_by"] == "DISASTER_STOP_CONFIRMED"


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


def test_54_paper_state_events_and_transitions_are_explicit(manager):
    assert manager.LifecycleState.PAPER_POSITION_OPEN.value == "PAPER_POSITION_OPEN"
    assert manager.LifecycleEvent.PAPER_POSITION_OPENED.value == "PAPER_POSITION_OPENED"
    assert manager.LifecycleEvent.PAPER_POSITION_CLOSED.value == "PAPER_POSITION_CLOSED"
    assert manager.TRANSITION_MATRIX["SIGNAL_DETECTED"]["PAPER_POSITION_OPENED"] == "PAPER_POSITION_OPEN"
    assert manager.TRANSITION_MATRIX["PAPER_POSITION_OPEN"]["PAPER_POSITION_CLOSED"] == "CLOSE_CONFIRMED"
    assert "CLOSE_CONFIRMED" not in manager.TRANSITION_MATRIX["SIGNAL_DETECTED"]


def test_55_paper_open_and_close_record_expected_history(manager):
    created = create(manager, mode="PAPER", quantity_planned=0.0)
    opened = manager.apply_event("LC-A", paper_event("PAPER_POSITION_OPENED", 1), persist=False)
    closed = manager.apply_event("LC-A", paper_event("PAPER_POSITION_CLOSED", 2), persist=False)

    assert created["current_state"] == "SIGNAL_DETECTED"
    assert opened["current_state"] == "PAPER_POSITION_OPEN"
    assert closed["current_state"] == "CLOSE_CONFIRMED"
    history = closed["snapshot"]["history"]
    assert [(item["previous_state"], item["current_state"]) for item in history] == [
        ("", "SIGNAL_DETECTED"),
        ("SIGNAL_DETECTED", "PAPER_POSITION_OPEN"),
        ("PAPER_POSITION_OPEN", "CLOSE_CONFIRMED"),
    ]
    assert all(item.get("trade_id") == "TR-A" for item in history)
    assert all(item.get("lifecycle_id") == "LC-A" for item in history)
    assert all(item.get("mode") == "PAPER" for item in history)


def test_56_paper_events_are_blocked_out_of_order(manager):
    create(manager, mode="PAPER", quantity_planned=0.0)
    paper_close = manager.apply_event("LC-A", paper_event("PAPER_POSITION_CLOSED", 1), persist=False)
    live_close = manager.apply_event("LC-A", event("CLOSE_CONFIRMED", 2), persist=False)
    assert paper_close["blocked"] and paper_close["current_state"] == "SIGNAL_DETECTED"
    assert live_close["blocked"] and live_close["current_state"] == "SIGNAL_DETECTED"


def test_57_live_lifecycle_rejects_paper_events(manager):
    create(manager, mode="LIVE")
    result = manager.apply_event("LC-A", paper_event("PAPER_POSITION_OPENED", 1), persist=False)
    assert result["blocked"]
    assert result["current_state"] == "SIGNAL_DETECTED"
    assert "PAPER lifecycle mode" in " ".join(result["reasons"])


def test_58_paper_open_and_close_are_idempotent(manager):
    create(manager, mode="PAPER", quantity_planned=0.0)
    opened_event = paper_event("PAPER_POSITION_OPENED", 1)
    assert manager.apply_event("LC-A", opened_event, persist=False)["event_applied"]
    assert manager.apply_event("LC-A", opened_event, persist=False)["duplicate"]

    closed_event = paper_event("PAPER_POSITION_CLOSED", 2)
    first_close = manager.apply_event("LC-A", closed_event, persist=False)
    same_close = manager.apply_event("LC-A", closed_event, persist=False)
    before_semantic_duplicate = manager.get_lifecycle("LC-A")["snapshot"]
    different_close = manager.apply_event("LC-A", paper_event("PAPER_POSITION_CLOSED", 3), persist=False)
    after_semantic_duplicate = manager.get_lifecycle("LC-A")["snapshot"]

    assert first_close["event_applied"]
    assert same_close["duplicate"]
    assert different_close["duplicate"] and different_close["status"] == "PAPER_POSITION_ALREADY_CLOSED"
    assert after_semantic_duplicate["updated_at"] == before_semantic_duplicate["updated_at"]
    assert after_semantic_duplicate["close"] == before_semantic_duplicate["close"]
    assert after_semantic_duplicate["outcome"] == before_semantic_duplicate["outcome"]
    assert after_semantic_duplicate["divergences"] == before_semantic_duplicate["divergences"]


def test_59_paper_events_preserve_trade_and_lifecycle_identity(manager):
    create(manager, mode="PAPER", quantity_planned=0.0)
    wrong_trade = manager.apply_event("LC-A", paper_event("PAPER_POSITION_OPENED", 1, trade_id="TR-OTHER"), persist=False)
    wrong_lifecycle_event = paper_event("PAPER_POSITION_OPENED", 2)
    wrong_lifecycle_event["lifecycle_id"] = "LC-OTHER"
    wrong_lifecycle = manager.apply_event("LC-A", wrong_lifecycle_event, persist=False)
    assert wrong_trade["blocked"]
    assert wrong_lifecycle["blocked"]
    assert manager.get_lifecycle("LC-A")["snapshot"]["state"] == "SIGNAL_DETECTED"


def test_60_paper_open_closed_projection_matches_registry(manager):
    create(manager, mode="PAPER", quantity_planned=0.0)
    manager.apply_event("LC-A", paper_event("PAPER_POSITION_OPENED", 1), persist=False)
    opened = manager.compare_with_registry("LC-A", {"trade_id": "TR-A", "mode": "PAPER", "status": "OPEN"})
    manager.apply_event("LC-A", paper_event("PAPER_POSITION_CLOSED", 2), persist=False)
    closed = manager.compare_with_registry("LC-A", {"trade_id": "TR-A", "mode": "PAPER", "status": "CLOSED"})
    assert not any(item["field"] == "open_closed_status" for item in opened["differences"])
    assert not any(item["field"] == "open_closed_status" for item in closed["differences"])


def test_61_registry_live_open_post_ack_confirms_entry_without_inventing_fill(manager):
    lifecycle_id = advance_to_submitting(manager)
    result = manager.apply_event(
        lifecycle_id,
        event("ENTRY_CONFIRMED", 21, **registry_live_entry_confirmation()),
        persist=False,
    )

    assert result["current_state"] == "ENTRY_CONFIRMED"
    assert result["snapshot"]["quantity_filled"] == pytest.approx(2.0)
    assert result["snapshot"]["quantity_open"] == pytest.approx(2.0)
    assert result["snapshot"]["fill_ids"] == []
    assert result["snapshot"]["entry_confirmation"] == {
        "confirmed": True,
        "source": "REGISTRY_LIVE_OPEN_POST_ACK",
        "event_id": "EV-21",
        "trade_id": "TR-A",
        "client_order_id": "CLIENT-A",
        "exchange_order_id": "ORDER-A",
        "quantity": 2.0,
        "entry_price_theoretical": 100.0,
        "entry_price_reference": 100.25,
        "entry_price_confirmed": None,
        "opened_at": "2026-07-14T11:00:22+00:00",
        "confirmed_at": result["snapshot"]["entry_confirmation"]["confirmed_at"],
    }
    assert result["snapshot"]["entry_price_theoretical"] == 100.0
    assert result["snapshot"]["entry_price_reference"] == 100.25
    assert result["snapshot"]["entry_price_confirmed"] is None


@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("registry_live_open_post_ack", False),
        ("registry_source_component", "OTHER"),
        ("registry_status", "CLOSED"),
        ("mode", "PAPER"),
        ("execution_sent", False),
        ("trade_id", None),
        ("client_order_id", None),
        ("exchange_order_id", None),
        ("quantity", 0.0),
    ],
)
def test_62_registry_live_entry_confirmation_rejects_weak_evidence(manager, field, bad_value):
    lifecycle_id = advance_to_submitting(manager)
    evidence = registry_live_entry_confirmation()
    evidence[field] = bad_value
    result = manager.apply_event(lifecycle_id, event("ENTRY_CONFIRMED", 21, **evidence), persist=False)

    assert result["blocked"]
    assert result["current_state"] == "ENTRY_SUBMITTING"
    assert result["snapshot"]["quantity_filled"] == 0.0
    assert result["snapshot"]["quantity_open"] == 0.0
    assert result["snapshot"]["fill_ids"] == []


def test_63_registry_live_entry_confirmation_requires_explicit_event_id(manager):
    lifecycle_id = advance_to_submitting(manager)
    item = event("ENTRY_CONFIRMED", 21, **registry_live_entry_confirmation())
    item.pop("event_id")
    result = manager.apply_event(lifecycle_id, item, persist=False)

    assert result["blocked"]
    assert any("requires event_id" in reason for reason in result["reasons"])
    assert result["snapshot"]["fill_ids"] == []


def test_64_registry_live_entry_confirmation_is_idempotent_by_order(manager):
    lifecycle_id = advance_to_submitting(manager)
    first = manager.apply_event(lifecycle_id, event("ENTRY_CONFIRMED", 21, **registry_live_entry_confirmation()), persist=False)
    duplicate = manager.apply_event(lifecycle_id, event("ENTRY_CONFIRMED", 22, **registry_live_entry_confirmation()), persist=False)

    assert first["event_applied"]
    assert duplicate["duplicate"] and duplicate["status"] == "DUPLICATE_REGISTRY_ENTRY_CONFIRMATION"
    assert duplicate["snapshot"]["quantity_filled"] == pytest.approx(2.0)
    assert duplicate["snapshot"]["fill_ids"] == []


def test_65_tp50_broker_reduction_without_fill_preserves_identity_and_quantities(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=1.0), persist=False)
    result = manager.apply_event(
        lifecycle_id,
        event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction()),
        persist=False,
    )

    assert result["current_state"] == "TP50_PENDING"
    assert result["snapshot"]["quantity_closed"] == pytest.approx(0.5)
    assert result["snapshot"]["quantity_open"] == pytest.approx(1.5)
    assert result["snapshot"]["fill_ids"] == ["FILL-A-1"]
    assert result["snapshot"]["tp50"]["broker_order_ids"] == ["TP50-ORDER-1"]
    assert result["snapshot"]["tp50"]["quantity_confirmed"] == pytest.approx(0.5)


def test_66_tp50_broker_reduction_is_idempotent_by_broker_order(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction()), persist=False)
    duplicate = manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 23, **broker_tp50_reduction()), persist=False)

    assert duplicate["duplicate"] and duplicate["status"] == "DUPLICATE_BROKER_REDUCTION"
    assert duplicate["snapshot"]["quantity_closed"] == pytest.approx(0.5)
    assert duplicate["snapshot"]["quantity_open"] == pytest.approx(1.5)
    assert duplicate["snapshot"]["fill_ids"] == ["FILL-A-1"]


def test_67_tp50_same_broker_order_with_different_quantity_is_blocked(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction()), persist=False)
    result = manager.apply_event(
        lifecycle_id,
        event("TP50_FILL_RECORDED", 23, **broker_tp50_reduction(quantity=0.4)),
        persist=False,
    )

    assert result["blocked"]
    assert any("different quantity" in reason for reason in result["reasons"])
    assert result["snapshot"]["quantity_closed"] == pytest.approx(0.5)
    assert result["snapshot"]["quantity_open"] == pytest.approx(1.5)


def test_68_tp50_broker_reduction_requires_order_id(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=1.0), persist=False)
    result = manager.apply_event(
        lifecycle_id,
        event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction(order_id=None)),
        persist=False,
    )

    assert result["blocked"]
    assert result["snapshot"]["quantity_closed"] == 0.0
    assert result["snapshot"]["fill_ids"] == ["FILL-A-1"]


def test_69_registry_live_closed_confirms_close_without_inventing_fill(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 21, quantity=2.0), persist=False)
    result = manager.apply_event(
        lifecycle_id,
        event("CLOSE_CONFIRMED", 22, **registry_live_close()),
        persist=False,
    )

    assert result["current_state"] == "CLOSE_CONFIRMED"
    assert result["snapshot"]["quantity_closed"] == pytest.approx(2.0)
    assert result["snapshot"]["quantity_open"] == 0.0
    assert result["snapshot"]["fill_ids"] == ["FILL-A-1"]
    assert result["snapshot"]["close"]["factual_registry_close"] is True
    assert result["snapshot"]["close"]["close_reason"] == "STOP_FAILSAFE_MARKET"
    assert result["snapshot"]["close"]["quantity_confirmed"] == pytest.approx(2.0)


def test_70_registry_live_close_is_semantically_idempotent(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 21, quantity=2.0), persist=False)
    manager.apply_event(lifecycle_id, event("CLOSE_CONFIRMED", 22, **registry_live_close()), persist=False)
    duplicate = manager.apply_event(lifecycle_id, event("CLOSE_CONFIRMED", 23, **registry_live_close()), persist=False)

    assert duplicate["duplicate"] and duplicate["status"] == "DUPLICATE_REGISTRY_CLOSE"
    assert duplicate["snapshot"]["quantity_closed"] == pytest.approx(2.0)
    assert duplicate["snapshot"]["quantity_open"] == 0.0
    assert duplicate["snapshot"]["fill_ids"] == ["FILL-A-1"]


@pytest.mark.parametrize(
    "updates",
    [
        {"quantity": 1.0},
        {"registry_source_component": "OTHER"},
        {"registry_status": "OPEN"},
        {"mode": "PAPER"},
        {"trade_id": None},
        {"closed_at": None},
        {"close_reason": None},
    ],
)
def test_71_registry_live_close_rejects_incomplete_or_inconsistent_evidence(manager, updates):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 21, quantity=2.0), persist=False)
    result = manager.apply_event(
        lifecycle_id,
        event("CLOSE_CONFIRMED", 22, **registry_live_close(**updates)),
        persist=False,
    )

    assert result["blocked"]
    assert result["current_state"] == "CLOSE_PENDING"
    assert result["snapshot"]["quantity_closed"] == 0.0
    assert result["snapshot"]["quantity_open"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "status",
    [
        "DISASTER_STOP_CREATED",
        "ROLLBACK_PROTECTED",
        "STOP_REPLACED",
        "STOP_REPLACED_EDIT",
        "STOP_REPLACED_CANCEL_CREATE",
    ],
)
def test_72_disaster_stop_accepts_explicit_active_broker_statuses(manager, status):
    lifecycle_id = advance_to_entry_confirmed(manager)
    evidence = stop_evidence()
    evidence.update({"status": status, "symbol": "BTC/USDT:USDT", "position_side": "LONG", "action_side": "SELL"})
    result = manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 21, **evidence), persist=False)

    assert result["current_state"] == "ENTRY_PROTECTED"
    assert result["snapshot"]["disaster_stop"]["status"] == status
    assert result["snapshot"]["disaster_stop"]["side"] == "SHORT"
    assert result["snapshot"]["disaster_stop"]["position_side"] == "LONG"


@pytest.mark.parametrize(
    "updates,reason_fragment",
    [
        ({"symbol": "ETHUSDT"}, "symbol does not match"),
        ({"position_side": "SHORT"}, "position_side does not match"),
        ({"action_side": "BUY"}, "action side is not protective"),
        ({"status": "CANCELED"}, "status is not active"),
    ],
)
def test_73_disaster_stop_rejects_identity_side_or_inactive_status(manager, updates, reason_fragment):
    lifecycle_id = advance_to_entry_confirmed(manager)
    evidence = stop_evidence()
    evidence.update({"symbol": "BTCUSDT", "position_side": "LONG", "action_side": "SELL", **updates})
    result = manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 21, **evidence), persist=False)

    assert result["blocked"]
    assert result["current_state"] == "ENTRY_CONFIRMED"
    assert any(reason_fragment in reason for reason in result["reasons"])


def test_74_registry_closed_quantity_projection_is_status_aware(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 21, quantity=2.0), persist=False)
    manager.apply_event(lifecycle_id, event("CLOSE_CONFIRMED", 22, **registry_live_close()), persist=False)
    result = manager.compare_with_registry(
        lifecycle_id,
        {
            "trade_id": "TR-A", "bot": "FALCON", "setup": "ORB",
            "symbol": "BTCUSDT", "side": "LONG", "mode": "LIVE",
            "status": "CLOSED", "qty": 2.0,
        },
    )

    assert result["status"] == "MATCH"
    assert not any(item["field"] == "quantity_open" for item in result["differences"])


def test_75_registry_open_remaining_quantity_precedes_initial_qty(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=1.0), persist=False)
    manager.apply_event(lifecycle_id, event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction()), persist=False)
    result = manager.compare_with_registry(
        lifecycle_id,
        {
            "trade_id": "TR-A", "bot": "FALCON", "setup": "ORB",
            "symbol": "BTCUSDT", "side": "LONG", "mode": "LIVE",
            "status": "OPEN", "qty": 2.0, "metadata": {"remaining_qty": 1.5},
        },
    )

    assert result["status"] == "MATCH"
    assert not any(item["field"] == "quantity_open" for item in result["differences"])


def test_76_full_live_factual_cycle_can_finish_without_invented_fill_ids(manager):
    lifecycle_id = advance_to_submitting(manager)
    entry = manager.apply_event(
        lifecycle_id,
        event("ENTRY_CONFIRMED", 21, **registry_live_entry_confirmation()),
        persist=False,
    )
    stop = stop_evidence()
    stop.update({"status": "DISASTER_STOP_CREATED", "symbol": "BTCUSDT", "position_side": "LONG", "action_side": "SELL"})
    protected = manager.apply_event(lifecycle_id, event("DISASTER_STOP_CONFIRMED", 22, **stop), persist=False)
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 23, quantity=2.0), persist=False)
    closed = manager.apply_event(lifecycle_id, event("CLOSE_CONFIRMED", 24, **registry_live_close()), persist=False)
    outcome = manager.record_outcome(
        lifecycle_id,
        {"outcome_id": "CENTRAL-OUTCOME-TR-A", "result_pct": -0.9218, "result_r": -1.0966, "exit_reason": "STOP_FAILSAFE_MARKET"},
        persist=False,
    )

    assert entry["snapshot"]["fill_ids"] == []
    assert protected["current_state"] == "ENTRY_PROTECTED"
    assert closed["current_state"] == "CLOSE_CONFIRMED"
    assert outcome["current_state"] == "OUTCOME_RECORDED"
    assert outcome["snapshot"]["quantity_open"] == 0.0
    assert outcome["snapshot"]["quantity_closed"] == pytest.approx(2.0)
    assert outcome["snapshot"]["fill_ids"] == []


@pytest.mark.parametrize(
    "price_field",
    ["entry_price_confirmed", "executed_price", "average_price", "average", "fill_price"],
)
def test_77_registry_live_entry_records_only_explicit_factual_execution_price(manager, price_field):
    lifecycle_id = advance_to_submitting(manager)
    evidence = registry_live_entry_confirmation(**{price_field: 100.75})
    result = manager.apply_event(lifecycle_id, event("ENTRY_CONFIRMED", 21, **evidence), persist=False)

    assert result["current_state"] == "ENTRY_CONFIRMED"
    assert result["snapshot"]["entry_price_confirmed"] == pytest.approx(100.75)
    assert result["snapshot"]["entry_confirmation"]["entry_price_confirmed"] == pytest.approx(100.75)
    assert result["snapshot"]["entry_price_theoretical"] == pytest.approx(100.0)
    assert result["snapshot"]["entry_price_reference"] == pytest.approx(100.25)
    assert result["snapshot"]["fill_ids"] == []


def test_78_registry_live_entry_never_promotes_generic_price_to_confirmed(manager):
    lifecycle_id = advance_to_submitting(manager)
    evidence = registry_live_entry_confirmation(entry_price_reference=None, price=101.5)
    result = manager.apply_event(lifecycle_id, event("ENTRY_CONFIRMED", 21, **evidence), persist=False)

    assert result["current_state"] == "ENTRY_CONFIRMED"
    assert result["snapshot"]["entry_price_reference"] == pytest.approx(101.5)
    assert result["snapshot"]["entry_price_confirmed"] is None
    assert result["snapshot"]["entry_confirmation"]["entry_price_confirmed"] is None
    assert result["snapshot"]["fill_ids"] == []


@pytest.mark.parametrize(
    "source_state,setup_events",
    [
        ("TP50_PENDING", [("TP50_REQUESTED", {"quantity": 1.0})]),
        (
            "TP50_CONFIRMED",
            [
                ("TP50_REQUESTED", {"quantity": 1.0}),
                ("TP50_FILL_RECORDED", broker_tp50_reduction(quantity=1.0)),
                ("TP50_CONFIRMED", {}),
            ],
        ),
        ("BREAK_EVEN_PENDING", [("BREAK_EVEN_REQUESTED", {"stop_price": 100.0})]),
        ("TRAILING_PENDING", [("TRAILING_REQUESTED", {"stop_price": 101.0})]),
    ],
)
def test_79_factual_failsafe_close_can_start_from_protected_pending_states(manager, source_state, setup_events):
    lifecycle_id = advance_to_managed(manager)
    for offset, (event_type, evidence) in enumerate(setup_events, start=21):
        result = manager.apply_event(lifecycle_id, event(event_type, offset, **evidence), persist=False)
        assert result["ok"], result
    assert manager.get_lifecycle(lifecycle_id)["snapshot"]["state"] == source_state

    open_quantity = manager.get_lifecycle(lifecycle_id)["snapshot"]["quantity_open"]
    close_requested = manager.apply_event(
        lifecycle_id,
        event("CLOSE_REQUESTED", 30, quantity=open_quantity, reason="STOP_FAILSAFE"),
        persist=False,
    )

    assert close_requested["event_applied"]
    assert close_requested["previous_state"] == source_state
    assert close_requested["current_state"] == "CLOSE_PENDING"


def test_80_factual_failsafe_close_can_finish_after_recovery_required(manager):
    lifecycle_id = advance_to_entry_confirmed(manager)
    stop_failed = manager.apply_event(
        lifecycle_id,
        event("DISASTER_STOP_FAILED", 21, reason="STOP_REPLACEMENT_FAILED"),
        persist=False,
    )
    assert stop_failed["current_state"] == "ENTRY_CONFIRMED_STOP_MISSING"
    recovery = manager.mark_recovery_required(
        lifecycle_id,
        "STOP_REPLACEMENT_FAILED",
        {"broker_stop_status": "REPLACE_FAILED"},
        persist=False,
    )
    assert recovery["current_state"] == "RECOVERY_REQUIRED"

    close_requested = manager.apply_event(
        lifecycle_id,
        event("CLOSE_REQUESTED", 22, quantity=2.0, reason="STOP_FAILSAFE_MARKET"),
        persist=False,
    )
    closed = manager.apply_event(
        lifecycle_id,
        event("CLOSE_CONFIRMED", 23, **registry_live_close()),
        persist=False,
    )

    assert close_requested["previous_state"] == "RECOVERY_REQUIRED"
    assert close_requested["current_state"] == "CLOSE_PENDING"
    assert closed["current_state"] == "CLOSE_CONFIRMED"
    assert closed["snapshot"]["quantity_closed"] == pytest.approx(2.0)
    assert closed["snapshot"]["quantity_open"] == 0.0


def test_81_registry_close_confirms_position_already_reduced_to_zero_by_tp50(manager):
    lifecycle_id = advance_to_managed(manager)
    entry_order_id = manager.get_lifecycle(lifecycle_id)["snapshot"]["exchange_order_id"]
    manager.apply_event(lifecycle_id, event("TP50_REQUESTED", 21, quantity=2.0), persist=False)
    reduced = manager.apply_event(
        lifecycle_id,
        event("TP50_FILL_RECORDED", 22, **broker_tp50_reduction(quantity=2.0)),
        persist=False,
    )
    manager.apply_event(lifecycle_id, event("TP50_CONFIRMED", 23), persist=False)
    manager.apply_event(
        lifecycle_id,
        event("CLOSE_REQUESTED", 24, quantity=2.0, reason="TP50_FAILSAFE_FULL_CLOSE"),
        persist=False,
    )
    closed = manager.apply_event(
        lifecycle_id,
        event(
            "CLOSE_CONFIRMED",
            25,
            **registry_live_close(close_reason="TP50_FAILSAFE_FULL_CLOSE"),
        ),
        persist=False,
    )

    assert reduced["snapshot"]["quantity_open"] == 0.0
    assert closed["current_state"] == "CLOSE_CONFIRMED"
    assert closed["snapshot"]["quantity_closed"] == pytest.approx(2.0)
    assert closed["snapshot"]["quantity_open"] == 0.0
    assert closed["snapshot"]["exchange_order_id"] == entry_order_id
    assert "TP50-ORDER-1" not in closed["snapshot"]["fill_ids"]


def test_82_management_order_ids_never_replace_entry_exchange_order_identity(manager):
    lifecycle_id = advance_to_managed(manager)
    entry_order_id = manager.get_lifecycle(lifecycle_id)["snapshot"]["exchange_order_id"]
    manager.apply_event(
        lifecycle_id,
        event("BREAK_EVEN_REQUESTED", 21, order_id="STOP-BE-1", stop_price=100.0),
        persist=False,
    )
    confirmed = manager.apply_event(
        lifecycle_id,
        event("BREAK_EVEN_CONFIRMED", 22, order_id="STOP-BE-1", stop_price=100.0),
        persist=False,
    )

    assert confirmed["current_state"] == "BREAK_EVEN_ACTIVE"
    assert confirmed["snapshot"]["exchange_order_id"] == entry_order_id


def test_83_replacement_stop_refreshes_physical_protection_without_changing_management_state(manager):
    lifecycle_id = advance_to_managed(manager)
    replacement = stop_evidence()
    replacement.update({
        "order_id": "STOP-2",
        "status": "STOP_REPLACED_EDIT",
        "timestamp": "2026-07-11T00:02:00+00:00",
    })

    result = manager.apply_event(
        lifecycle_id,
        event("DISASTER_STOP_CONFIRMED", 21, **replacement),
        persist=False,
    )

    assert result["event_applied"]
    assert result["previous_state"] == "POSITION_MANAGED"
    assert result["current_state"] == "POSITION_MANAGED"
    assert result["snapshot"]["disaster_stop"]["order_id"] == "STOP-2"
    assert result["snapshot"]["disaster_stop"]["confirmed"] is True


def test_84_unprotected_stop_update_invalidates_old_stop_until_recovery(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(
        lifecycle_id,
        event("TRAILING_REQUESTED", 21, stop_price=101.0),
        persist=False,
    )
    required = manager.mark_recovery_required(
        lifecycle_id,
        "STOP_REPLACE_CRITICAL_UNPROTECTED",
        {"stop_update_failed": True, "status": "STOP_REPLACE_CRITICAL_UNPROTECTED"},
        persist=False,
    )

    assert required["current_state"] == "RECOVERY_REQUIRED"
    assert required["snapshot"]["disaster_stop"]["confirmed"] is False
    assert required["snapshot"]["disaster_stop"]["invalidated_by"] == "STOP_UPDATE_FAILED"
    assert required["snapshot"]["recovery"]["previous_disaster_stop"]["order_id"] == "STOP-1"

    replacement = stop_evidence()
    replacement.update({
        "order_id": "ROLLBACK-STOP-2",
        "status": "ROLLBACK_PROTECTED",
        "timestamp": "2026-07-11T00:02:00+00:00",
    })
    recovered = manager.apply_event(
        lifecycle_id,
        event("DISASTER_STOP_CONFIRMED", 22, **replacement),
        persist=False,
    )

    assert recovered["current_state"] == "ENTRY_PROTECTED"
    assert recovered["snapshot"]["recovery"]["required"] is False
    assert recovered["snapshot"]["disaster_stop"]["confirmed"] is True
    assert recovered["snapshot"]["disaster_stop"]["order_id"] == "ROLLBACK-STOP-2"


def test_85_closed_registry_comparison_ignores_historical_protection_flag(manager):
    lifecycle_id = advance_to_managed(manager)
    manager.apply_event(lifecycle_id, event("TRAILING_REQUESTED", 21, stop_price=101.0), persist=False)
    manager.mark_recovery_required(
        lifecycle_id,
        "STOP_REPLACE_CRITICAL_UNPROTECTED",
        {"stop_update_failed": True, "status": "STOP_REPLACE_CRITICAL_UNPROTECTED"},
        persist=False,
    )
    manager.apply_event(lifecycle_id, event("CLOSE_REQUESTED", 22, quantity=2.0), persist=False)
    manager.apply_event(lifecycle_id, event("CLOSE_CONFIRMED", 23, **registry_live_close()), persist=False)

    result = manager.compare_with_registry(
        lifecycle_id,
        {
            "trade_id": "TR-A",
            "bot": "FALCON",
            "setup": "ORB",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "mode": "LIVE",
            "status": "CLOSED",
            "qty": 2.0,
            "metadata": {"disaster_stop_confirmed": True},
        },
    )

    assert result["status"] == "MATCH"
    assert not any(item["field"] == "protection" for item in result["differences"])
