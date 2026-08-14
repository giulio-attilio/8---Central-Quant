from __future__ import annotations

from datetime import datetime, timezone

from live_trade_snapshot import build_live_trade_snapshot
from trade_timeline_validator import (
    correlate_source_records,
    new_correlation_context,
    target_identity_from_context,
    validate_trade_timeline,
)


TURTLE_TRADE_ID = "TURTLE:TURTLE20:FLOKIUSDT:SHORT"


def _turtle_registry():
    return {
        "open_trades": {},
        "closed_trades": [
            {
                "trade_id": TURTLE_TRADE_ID,
                "registry_record_id": "registry-instance-a",
                "lifecycle_id": "lifecycle-a",
                "bot": "TURTLE",
                "setup": "TURTLE20",
                "symbol": "FLOKIUSDT",
                "side": "SHORT",
                "status": "CLOSED",
                "opened_at": "04/08/2026 11:01:14",
                "opened_epoch": 1785852074.0,
                "closed_at": "04/08/2026 14:40:31",
            },
            {
                "trade_id": TURTLE_TRADE_ID,
                "registry_record_id": "registry-instance-b",
                "lifecycle_id": "lifecycle-b",
                "bot": "TURTLE",
                "setup": "TURTLE20",
                "symbol": "FLOKIUSDT",
                "side": "SHORT",
                "status": "CLOSED",
                "opened_at": "10/08/2026 15:00:41",
                "opened_epoch": 1786384841.0,
                "closed_at": "13/08/2026 23:00:18",
                "closed_epoch": 1786672818.0,
            },
        ],
    }


def test_trade_id_only_does_not_choose_between_reused_turtle_instances():
    report = build_live_trade_snapshot(
        TURTLE_TRADE_ID,
        sources={"registry": _turtle_registry()},
    )

    assert report["registry"]["record_found"] is False
    assert report["trade"]["opened_at"] is None
    assert report["identity"]["identity_confidence"] == "AMBIGUOUS"
    assert report["identity"]["candidate_count"] == 2
    assert {row["opened_at"] for row in report["identity"]["candidates"]} == {
        "04/08/2026 11:01:14",
        "10/08/2026 15:00:41",
    }
    assert report["conclusive"] is False
    assert report["evidence_status"] == "IDENTITY_AMBIGUOUS"


def test_opened_at_selects_the_recent_turtle_instance():
    report = build_live_trade_snapshot(
        TURTLE_TRADE_ID,
        sources={"registry": _turtle_registry()},
        opened_at="10/08/2026 15:00:41",
    )

    assert report["registry"]["record_found"] is True
    assert report["trade"]["opened_at"] == "10/08/2026 15:00:41"
    assert report["trade"]["closed_at"] == "13/08/2026 23:00:18"
    assert report["identity"]["registry_id"] == "registry-instance-b"
    assert report["identity"]["selection_basis"] == "opened_at"
    assert report["identity"]["identity_confidence"] == "HIGH"

    context = new_correlation_context(
        TURTLE_TRADE_ID,
        opened_at="10/08/2026 15:00:41",
    )
    selected = correlate_source_records("registry", [_turtle_registry()], context)
    target = target_identity_from_context(context)
    assert selected[0]["registry_record_id"] == "registry-instance-b"
    assert "trade" not in target.strong
    assert target.secondary["trade"] == frozenset({TURTLE_TRADE_ID})
    assert target.strong["lifecycle"] == frozenset({"lifecycle-b"})


def test_opened_epoch_and_strong_instance_id_each_select_the_recent_instance():
    opened_epoch = datetime(2026, 8, 10, 18, 0, 41, tzinfo=timezone.utc).timestamp()
    by_epoch = validate_trade_timeline(
        TURTLE_TRADE_ID,
        sources={"registry": _turtle_registry()},
        opened_epoch=opened_epoch,
    )
    by_instance = build_live_trade_snapshot(
        TURTLE_TRADE_ID,
        sources={"registry": _turtle_registry()},
        instance_id="lifecycle-b",
    )

    assert by_epoch["components"]["registry"]["records"] == 1
    assert by_epoch["identity"]["selection_basis"] == "opened_epoch"
    assert by_epoch["identity"]["ambiguous"] is False
    assert by_instance["registry"]["record_found"] is True
    assert by_instance["trade"]["opened_at"] == "10/08/2026 15:00:41"
    assert by_instance["identity"]["selection_basis"] == "instance_id"
    assert by_instance["identity"]["lifecycle_id"] == "lifecycle-b"


def test_unique_non_reusable_trade_id_keeps_legacy_resolution():
    trade_id = "FALCON:unique-20260810-150041"
    registry = {
        "open_trades": {
            trade_id: {
                "trade_id": trade_id,
                "registry_record_id": "falcon-registry-1",
                "bot": "FALCON",
                "setup": "FALCON15",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "status": "OPEN",
                "opened_at": "2026-08-10T15:00:41+00:00",
            }
        },
        "closed_trades": [],
    }

    report = build_live_trade_snapshot(trade_id, sources={"registry": registry})

    assert report["registry"]["record_found"] is True
    assert report["identity"]["registry_id"] == "falcon-registry-1"
    assert report["identity"]["selection_basis"] == "unique_trade_id"
    assert report["identity"]["identity_confidence"] == "HIGH"


def test_unknown_instance_selector_does_not_fall_back_to_logical_journal_match():
    timeline = {
        "trade_id": TURTLE_TRADE_ID,
        "event_type": "POSITION_OPEN",
        "occurred_at": "10/08/2026 15:00:41",
    }

    report = build_live_trade_snapshot(
        TURTLE_TRADE_ID,
        sources={"registry": _turtle_registry(), "timeline": [timeline]},
        instance_id="does-not-exist",
    )

    assert report["registry"]["record_found"] is False
    assert report["identity"]["identity_confidence"] == "NONE"
    assert report["identity"]["selection_basis"] == "instance_id_not_found"
    assert report["trade"]["opened_at"] is None
