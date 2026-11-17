import json

import pytest

from paper_registry_source_preview import main as preview_main
from paper_registry_source_preview import preview_paper_registry_sources

_SOURCE_BOTS = ("COBRA", "DONKEY", "FALCON", "MEME", "PREDATOR", "TRENDPRO", "TURTLE")


def _registry(position):
    return {"open_trades": {"legacy-key": position}, "closed_trades": []}


def _sources(*positions):
    return _source_snapshot({"TURTLE": {f"p{index}": position for index, position in enumerate(positions)}})


def _source_snapshot(positions_by_bot=None, status_by_bot=None):
    positions = {bot: {} for bot in _SOURCE_BOTS}
    positions.update(positions_by_bot or {})
    statuses = {bot: "OK" for bot in _SOURCE_BOTS}
    statuses.update(status_by_bot or {})
    return {"positions_by_bot": positions, "source_status_by_bot": statuses}


def _row(status, registry=None, sources=None):
    report = preview_paper_registry_sources(registry or _registry({"bot": "TURTLE"}), sources or _sources())
    assert report["status"] == "PREVIEW_ONLY_NOT_MIGRATABLE"
    assert report["all_rows_ineligible_for_import"] is True
    assert report["rows"][0]["eligible_for_import"] is False
    return report["rows"][0]


def test_strong_identity_match_is_review_only_and_report_is_sanitized():
    registry = _registry({
        "bot": "TURTLE", "symbol": "BTCUSDT", "side": "LONG",
        "lifecycle_id": "private-lifecycle-123", "execution_mode": "PAPER",
    })
    sources = _sources({
        "symbol": "BTCUSDT", "side": "LONG", "lifecycle_id": "private-lifecycle-123",
        "execution_mode": "PAPER",
    })
    report = preview_paper_registry_sources(registry, sources)
    row = report["rows"][0]
    assert row["status"] == "STRONG_IDENTITY_MATCH_REVIEW"
    assert row["mode_status"] == "PAPER_CONFIRMED_BY_BOTH_SNAPSHOTS"
    assert row["source_ref"] is not None
    assert report["source_reconciliation_counts"] == {
        "unique_strong_match_open": 1,
        "unique_review_only_match_open": 0,
        "unique_strong_match_closed": 0,
        "unique_review_only_match_closed": 0,
        "ambiguous_or_conflicting_candidate": 0,
        "orphan_no_registry_candidate": 0,
        "unresolved_incomplete_snapshot": 0,
    }
    assert "private-lifecycle-123" not in json.dumps(report)
    assert "BTCUSDT" not in json.dumps(report)


def test_duplicate_source_strong_identity_is_ambiguous():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1"})
    sources = _sources({"lifecycle_id": "lc-1"}, {"lifecycle_id": "lc-1"})
    report = preview_paper_registry_sources(registry, sources)
    assert report["rows"][0]["status"] == "AMBIGUOUS_STRONG_ID"
    assert report["source_reconciliation_counts"]["ambiguous_or_conflicting_candidate"] == 2


def test_strong_identity_in_another_bot_is_a_conflict():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1"})
    sources = _source_snapshot({"FALCON": {"p1": {"lifecycle_id": "lc-1"}}})
    assert _row("STRONG_ID_BOT_CONFLICT", registry, sources)["status"] == "STRONG_ID_BOT_CONFLICT"


def test_missing_source_key_is_not_treated_as_an_empty_position_set():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1"})
    sources = _source_snapshot(
        {"TURTLE": {"p1": {"lifecycle_id": "lc-1"}}},
        {"DONKEY": "KEY_MISSING"},
    )
    sources["positions_by_bot"].pop("DONKEY")

    report = preview_paper_registry_sources(registry, sources)

    assert report["source_snapshot_complete"] is False
    assert report["source_incomplete_bots"] == ["DONKEY"]
    assert report["rows"][0]["status"] == "SOURCE_SNAPSHOT_INCOMPLETE"
    assert report["rows"][0]["source_ref"] is None
    assert report["rows"][0]["eligible_for_import"] is False
    assert report["source_reconciliation_counts"]["unresolved_incomplete_snapshot"] == 1
    assert report["source_reconciliation_counts"]["orphan_no_registry_candidate"] == 0


def test_explicitly_read_empty_keys_are_complete_not_missing():
    report = preview_paper_registry_sources(_registry({"bot": "TURTLE"}), _sources())
    assert report["source_snapshot_complete"] is True
    assert report["source_incomplete_bots"] == []
    assert report["source_bot_status_counts"] == {"OK": len(_SOURCE_BOTS)}


def test_source_diagnostics_report_modes_status_close_markers_and_identity_presence_only():
    sources = _source_snapshot({
        "FALCON": {
            "private-position-a": {
                "status": "OPEN",
                "execution_mode": "PAPER",
                "signal_id": "private-signal-a",
                "trade_registry_id": "private-trade-a",
            },
            "private-position-b": {
                "status": "ENCERRADO",
                "execution_mode": "PAPER",
                "closed_at": "private-close-time",
            },
        },
        "TURTLE": {
            "private-position-c": {
                "status": "OPEN",
                "execution_id": "private-execution-c",
                "lifecycle_id": "private-lifecycle-c",
                "registry_v2_register_idempotency_key": "private-idempotency-c",
            },
        },
    })

    report = preview_paper_registry_sources(
        _registry({"bot": "TURTLE", "lifecycle_id": "no-match"}),
        sources,
    )

    falcon = report["source_diagnostics"]["by_bot"]["FALCON"]
    assert falcon["record_count"] == 2
    assert falcon["status_counts"] == {"ENCERRADO": 1, "OPEN": 1}
    assert falcon["execution_mode_counts"] == {"PAPER": 2}
    assert falcon["records_with_close_marker"] == 1
    assert falcon["records_without_close_marker"] == 1
    assert falcon["identity_field_presence_counts"] == {
        "signal_id": 1,
        "trade_id": 1,
    }

    turtle = report["source_diagnostics"]["by_bot"]["TURTLE"]
    assert turtle["execution_mode_counts"] == {"<UNSET>": 1}
    assert turtle["records_without_close_marker"] == 1
    assert turtle["identity_field_presence_counts"] == {
        "lifecycle_id": 1,
        "registry_v2_register_idempotency_key": 1,
    }
    assert "private-position" not in json.dumps(report)
    assert "private-lifecycle-c" not in json.dumps(report)
    assert report["all_rows_ineligible_for_import"] is True


def test_registry_register_idempotency_key_is_counted_but_not_used_as_lifecycle_identity():
    registry = _registry({
        "bot": "TURTLE",
        "registry_v2_register_idempotency_key": "private-register-event-key",
    })
    sources = _sources({
        "registry_v2_register_idempotency_key": "private-register-event-key",
    })

    report = preview_paper_registry_sources(registry, sources)

    assert report["rows"][0]["status"] == "UNMATCHED"
    assert report["rows"][0]["source_ref"] is None
    assert report["rows"][0]["eligible_for_import"] is False
    assert report["source_diagnostics"]["by_bot"]["TURTLE"][
        "identity_field_presence_counts"
    ]["registry_v2_register_idempotency_key"] == 1
    assert "private-register-event-key" not in json.dumps(report)


def test_ok_source_status_requires_a_position_snapshot_even_if_empty():
    sources = _source_snapshot()
    sources["positions_by_bot"].pop("DONKEY")
    with pytest.raises(ValueError, match="source_positions_missing_for_ok_bot"):
        preview_paper_registry_sources(_registry({"bot": "TURTLE"}), sources)


def test_unmatched_strong_identity_does_not_fall_back_to_logical_id():
    registry = _registry({"bot": "TURTLE", "trade_id": "logical-1", "lifecycle_id": "lc-registry"})
    sources = _sources({"trade_registry_id": "logical-1", "lifecycle_id": "lc-source"})
    assert _row("STRONG_ID_NOT_FOUND", registry, sources)["status"] == "STRONG_ID_NOT_FOUND"


def test_partial_strong_id_overlap_is_not_treated_as_a_match():
    registry = _registry({
        "bot": "TURTLE", "lifecycle_id": "lc-1", "client_order_id": "client-1",
    })
    sources = _sources({"lifecycle_id": "lc-1", "client_order_id": "client-other"})
    assert _row("STRONG_ID_PARTIAL_CONFLICT", registry, sources)["status"] == "STRONG_ID_PARTIAL_CONFLICT"


def test_conflicting_source_identity_aliases_block_strong_match():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1"})
    sources = _sources({"lifecycle_id": "lc-1", "execution_id": "lc-other"})
    assert _row("SOURCE_IDENTITY_ALIAS_CONFLICT", registry, sources)["status"] == "SOURCE_IDENTITY_ALIAS_CONFLICT"


def test_unique_logical_id_is_review_only_and_registry_mode_claim_is_not_proof():
    registry = _registry({"bot": "TURTLE", "trade_id": "legacy-1", "registry_mode": "PAPER"})
    sources = _sources({"trade_registry_id": "legacy-1", "execution_mode": "PAPER"})
    row = _row("LOGICAL_ID_REVIEW_ONLY", registry, sources)
    assert row["status"] == "LOGICAL_ID_REVIEW_ONLY"
    assert row["registry_mode_claim"] == "PAPER"
    assert row["mode_status"] == "MODE_UNVERIFIED"


def test_predator_nested_registry_result_id_conflict_blocks_logical_review_match():
    registry = _registry({"bot": "PREDATOR", "trade_id": "logical-from-registry"})
    sources = _source_snapshot({
        "PREDATOR": {
            "private-position-locator": {
                "trade_registry_id": "logical-from-position",
                "trade_registry_open_result": {
                    "ok": True,
                    "trade_id": "logical-from-registry",
                    "trade": {"trade_id": "logical-from-registry"},
                },
            },
        },
    })

    report = preview_paper_registry_sources(registry, sources)

    row = report["rows"][0]
    assert row["status"] == "SOURCE_IDENTITY_ALIAS_CONFLICT"
    assert row["eligible_for_import"] is False
    assert report["all_rows_ineligible_for_import"] is True
    assert report["source_diagnostics"]["by_bot"]["PREDATOR"][
        "identity_field_presence_counts"
    ] == {"trade_id": 1}
    encoded = json.dumps(report)
    assert "logical-from-position" not in encoded
    assert "logical-from-registry" not in encoded
    assert "private-position-locator" not in encoded


def test_predator_nested_registry_result_id_is_counted_without_promoting_identity():
    registry = _registry({"bot": "PREDATOR", "trade_id": "logical-only"})
    sources = _source_snapshot({
        "PREDATOR": {
            "private-position-locator": {
                "trade_registry_open_result": {
                    "ok": True,
                    "trade_id": "logical-only",
                },
            },
        },
    })

    report = preview_paper_registry_sources(registry, sources)

    row = report["rows"][0]
    assert row["status"] == "LOGICAL_ID_REVIEW_ONLY"
    assert row["eligible_for_import"] is False
    assert report["all_rows_ineligible_for_import"] is True
    assert report["source_diagnostics"]["by_bot"]["PREDATOR"][
        "identity_field_presence_counts"
    ] == {"trade_id": 1}


def test_trendpro_registry_trade_id_alias_is_review_only_and_sanitized():
    registry = _registry({"bot": "TRENDPRO", "trade_id": "private-logical-id", "registry_mode": "PAPER"})
    sources = _source_snapshot({
        "TRENDPRO": {"private-source-locator": {"registry_trade_id": "private-logical-id"}},
    })

    report = preview_paper_registry_sources(registry, sources)

    row = report["rows"][0]
    assert row["status"] == "LOGICAL_ID_REVIEW_ONLY"
    assert row["mode_status"] == "MODE_UNVERIFIED"
    assert row["source_ref"] is not None
    assert row["eligible_for_import"] is False
    assert report["all_rows_ineligible_for_import"] is True
    assert report["source_diagnostics"]["by_bot"]["TRENDPRO"][
        "identity_field_presence_counts"
    ] == {"trade_id": 1}
    assert "private-logical-id" not in json.dumps(report)
    assert "private-source-locator" not in json.dumps(report)


def test_donkey_registry_key_derivation_is_review_only_and_uses_closed_history():
    registry = {
        "open_trades": {},
        "closed_trades": [{
            "bot": "DONKEY",
            "trade_id": "DONKEY:DONKEY_ORIGINAL:BTCUSDT:LONG",
            "registry_mode": "PAPER",
        }],
    }
    sources = _source_snapshot({
        "DONKEY": {
            "private-position-locator": {
                "symbol": "BTC/USDT:USDT",
                "symbol_clean": "BTCUSDT",
                "side": "BUY",
                "signal_type": "DONKEY_ORIGINAL",
                "status": "PARCIAL 50% + EMA20",
            },
        },
    })

    report = preview_paper_registry_sources(registry, sources)

    assert report["registry_closed_status_counts"] == {
        "LOGICAL_ID_REVIEW_ONLY": 1,
    }
    assert report["source_diagnostics"]["by_bot"]["DONKEY"][
        "derived_logical_trade_id_records"
    ] == 1
    assert report["unmatched_source_count"] == 0
    assert report["source_reconciliation_counts"]["unique_review_only_match_closed"] == 1
    assert report["source_reconciliation_counts"]["orphan_no_registry_candidate"] == 0
    assert report["all_rows_ineligible_for_import"] is True
    assert "BTCUSDT" not in json.dumps(report)
    assert "private-position-locator" not in json.dumps(report)


def test_duplicate_donkey_derived_logical_ids_remain_ambiguous():
    registry = {
        "open_trades": [{
            "bot": "DONKEY",
            "trade_id": "DONKEY:DONKEY:BTCUSDT:LONG",
            "registry_mode": "PAPER",
        }],
        "closed_trades": [],
    }
    repeated_position = {
        "symbol_clean": "BTCUSDT",
        "side": "BUY",
        "signal_type": "DONKEY",
        "status": "PARCIAL 50% + EMA20",
    }
    sources = _source_snapshot({
        "DONKEY": {
            "reentry-a": dict(repeated_position),
            "reentry-b": dict(repeated_position),
        },
    })

    report = preview_paper_registry_sources(registry, sources)

    assert report["registry_status_counts"] == {"AMBIGUOUS_LOGICAL_ID": 1}
    assert report["source_diagnostics"]["by_bot"]["DONKEY"][
        "derived_logical_trade_id_records"
    ] == 2
    assert report["unmatched_source_count"] == 2
    assert report["all_rows_ineligible_for_import"] is True


def test_conflicting_registry_mode_claims_are_reported_separately():
    registry = _registry({
        "bot": "TURTLE", "lifecycle_id": "lc-1", "registry_mode": "PAPER",
        "metadata": {"registry_mode": "REAL"},
    })
    sources = _sources({"lifecycle_id": "lc-1", "execution_mode": "PAPER"})

    report = preview_paper_registry_sources(registry, sources)

    assert report["registry_mode_claim_counts"] == {"CONFLICT": 1}
    assert report["rows"][0]["registry_mode_claim"] == "CONFLICT"
    assert report["rows"][0]["mode_status"] == "MODE_UNVERIFIED"


def test_generic_mode_field_does_not_confirm_execution_mode():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1", "mode": "PAPER"})
    sources = _sources({"lifecycle_id": "lc-1", "metadata": {"mode": "PAPER"}})

    row = _row("STRONG_IDENTITY_MATCH_REVIEW", registry, sources)

    assert row["status"] == "STRONG_IDENTITY_MATCH_REVIEW"
    assert row["mode_status"] == "MODE_UNVERIFIED"


def test_duplicate_logical_id_cannot_be_resolved_by_registry_row_order():
    registry = {
        "open_trades": {"a": {"bot": "TURTLE", "trade_id": "legacy-1"}, "b": {"bot": "TURTLE", "trade_id": "legacy-1"}},
        "closed_trades": [],
    }
    sources = _sources({"trade_registry_id": "legacy-1"})
    report = preview_paper_registry_sources(registry, sources)
    assert {row["status"] for row in report["rows"]} == {"AMBIGUOUS_LOGICAL_ID"}


def test_unique_composite_match_is_review_only_and_requires_all_fields():
    position = {
        "bot": "TURTLE", "symbol": "BTCUSDT", "side": "LONG", "setup": "BREAKOUT",
        "entry_time": "2026-11-16T10:00:00Z", "entry_price": 90000,
        "registry_mode": "PAPER",
    }
    registry = _registry(position)
    sources = _sources({key: value for key, value in position.items() if key != "registry_mode"})
    row = _row("COMPOSITE_REVIEW_ONLY", registry, sources)
    assert row["status"] == "COMPOSITE_REVIEW_ONLY"
    assert row["mode_status"] == "MODE_UNVERIFIED"


def test_composite_match_is_ambiguous_when_registry_has_duplicate_lifecycles():
    position = {
        "bot": "TURTLE", "symbol": "BTCUSDT", "side": "LONG", "setup": "BREAKOUT",
        "entry_time": "2026-11-16T10:00:00Z", "entry_price": 90000,
    }
    registry = {"open_trades": {"a": position, "b": dict(position)}, "closed_trades": []}
    report = preview_paper_registry_sources(registry, _sources(position))
    assert {row["status"] for row in report["rows"]} == {"AMBIGUOUS_COMPOSITE"}


def test_composite_match_is_not_suggested_when_source_has_an_unmatched_id():
    position = {
        "bot": "TURTLE", "symbol": "BTCUSDT", "side": "LONG", "setup": "BREAKOUT",
        "entry_time": "2026-11-16T10:00:00Z", "entry_price": 90000,
    }
    source = dict(position, lifecycle_id="lc-source")
    row = _row("COMPOSITE_HAS_SOURCE_ID_UNMATCHED", _registry(position), _sources(source))
    assert row["status"] == "COMPOSITE_HAS_SOURCE_ID_UNMATCHED"
    assert row["source_ref"] is None


def test_closed_registry_history_participates_in_logical_id_uniqueness():
    registry = {
        "open_trades": {"open": {"bot": "TURTLE", "trade_id": "reused-logical-id"}},
        "closed_trades": [{"bot": "TURTLE", "trade_id": "reused-logical-id"}],
    }
    sources = _sources({"trade_registry_id": "reused-logical-id"})
    report = preview_paper_registry_sources(registry, sources)
    assert report["registry_closed_count"] == 1
    assert report["rows"][0]["status"] == "AMBIGUOUS_LOGICAL_ID"


def test_source_matching_only_closed_registry_is_classified_and_not_unmatched():
    registry = {
        "open_trades": {"open": {"bot": "TURTLE", "symbol": "ETHUSDT"}},
        "closed_trades": [{
            "bot": "TURTLE", "lifecycle_id": "closed-lifecycle-1",
            "execution_mode": "PAPER",
        }],
    }
    sources = _sources({
        "lifecycle_id": "closed-lifecycle-1",
        "execution_mode": "PAPER",
    })

    report = preview_paper_registry_sources(registry, sources)

    assert report["registry_status_counts"] == {"UNMATCHED": 1}
    assert report["registry_closed_status_counts"] == {
        "STRONG_IDENTITY_MATCH_REVIEW": 1,
    }
    assert report["registry_closed_mode_status_counts"] == {
        "PAPER_CONFIRMED_BY_BOTH_SNAPSHOTS": 1,
    }
    assert report["unmatched_source_count"] == 0
    assert report["source_reconciliation_counts"]["unique_strong_match_closed"] == 1
    assert report["source_reconciliation_counts"]["orphan_no_registry_candidate"] == 0


def test_source_without_any_registry_candidate_is_orphan_only_for_complete_snapshot():
    report = preview_paper_registry_sources(
        _registry({"bot": "TURTLE"}),
        _sources({"symbol": "BTCUSDT"}),
    )

    assert report["source_snapshot_complete"] is True
    assert report["source_reconciliation_counts"]["orphan_no_registry_candidate"] == 1
    assert report["source_reconciliation_counts"]["unresolved_incomplete_snapshot"] == 0
    assert report["all_rows_ineligible_for_import"] is True
    assert all(row["eligible_for_import"] is False for row in report["rows"])
    assert report["unmatched_source_count"] == 1


def test_source_position_id_is_review_only_and_never_import_eligible():
    registry = _registry({
        "bot": "TURTLE", "registry_mode": "PAPER",
        "metadata": {"position_id": "turtle-pos-1"},
    })
    sources = _sources({"id": "turtle-pos-1", "execution_mode": "PAPER"})

    report = preview_paper_registry_sources(registry, sources)

    row = report["rows"][0]
    assert row["status"] == "POSITION_ID_REVIEW_ONLY"
    assert row["registry_mode_claim"] == "PAPER"
    assert row["mode_status"] == "MODE_UNVERIFIED"
    assert row["eligible_for_import"] is False
    assert report["all_rows_ineligible_for_import"] is True
    assert "turtle-pos-1" not in json.dumps(report)


def test_duplicate_source_position_id_is_ambiguous():
    registry = _registry({"bot": "TURTLE", "metadata": {"position_id": "pos-1"}})
    sources = _sources({"id": "pos-1"}, {"id": "pos-1"})

    row = preview_paper_registry_sources(registry, sources)["rows"][0]

    assert row["status"] == "AMBIGUOUS_POSITION_ID"
    assert row["source_ref"] is None
    assert row["eligible_for_import"] is False


def test_unmatched_position_id_does_not_fall_back_to_composite_match():
    position = {
        "bot": "TURTLE", "symbol": "BTCUSDT", "side": "LONG", "setup": "BREAKOUT",
        "entry_time": "2026-11-16T10:00:00Z", "entry_price": 90000,
    }
    registry = _registry(dict(position, metadata={"position_id": "legacy-pos"}))
    sources = _sources(dict(position, id="different-pos"))

    row = preview_paper_registry_sources(registry, sources)["rows"][0]

    assert row["status"] == "POSITION_ID_NOT_FOUND"
    assert row["source_ref"] is None
    assert row["eligible_for_import"] is False


def test_open_position_id_reused_in_closed_history_is_ambiguous():
    registry = {
        "open_trades": {
            "open": {"bot": "TURTLE", "metadata": {"position_id": "reused-pos"}},
        },
        "closed_trades": [
            {"bot": "TURTLE", "metadata": {"position_id": "reused-pos"}},
        ],
    }
    sources = _sources({"id": "reused-pos"})

    row = preview_paper_registry_sources(registry, sources)["rows"][0]

    assert row["status"] == "AMBIGUOUS_POSITION_ID"
    assert row["source_ref"] is None
    assert row["eligible_for_import"] is False


def test_conflicting_trade_and_position_review_ids_do_not_match_partially():
    registry = _registry({
        "bot": "TURTLE", "trade_id": "logical-registry-id",
        "metadata": {"position_id": "registry-position-id"},
    })
    sources = _sources({
        "trade_registry_id": "logical-registry-id",
        "id": "different-source-position-id",
    })

    row = preview_paper_registry_sources(registry, sources)["rows"][0]

    assert row["status"] == "PARTIAL_REVIEW_ID_CONFLICT"
    assert row["source_ref"] is None
    assert row["eligible_for_import"] is False


def test_mode_conflict_is_separate_from_identity_match():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1", "execution_mode": "PAPER"})
    sources = _sources({"lifecycle_id": "lc-1", "execution_mode": "LIVE"})
    row = _row("STRONG_IDENTITY_MATCH_REVIEW", registry, sources)
    assert row["status"] == "STRONG_IDENTITY_MATCH_REVIEW"
    assert row["mode_status"] == "MODE_CONFLICT"


def test_conflicting_aliases_do_not_produce_a_match():
    registry = _registry({"bot": "TURTLE", "lifecycle_id": "lc-1", "execution_id": "lc-2"})
    sources = _sources({"lifecycle_id": "lc-1"})
    assert _row("IDENTITY_ALIAS_CONFLICT", registry, sources)["status"] == "IDENTITY_ALIAS_CONFLICT"


def test_missing_bot_source_snapshot_is_rejected():
    with pytest.raises(ValueError, match="source_positions_by_bot_invalid"):
        preview_paper_registry_sources(_registry({"bot": "TURTLE"}), {})


def test_source_bot_key_conflict_is_rejected():
    sources = _source_snapshot({"FALCON": {"p1": {"bot": "TURTLE"}}})
    with pytest.raises(ValueError, match="source_bot_key_conflict"):
        preview_paper_registry_sources(_registry({"bot": "TURTLE"}), sources)


def test_malformed_position_rows_are_not_silently_dropped():
    with pytest.raises(ValueError, match="source_position_invalid"):
        preview_paper_registry_sources(_registry({"bot": "TURTLE"}), _source_snapshot({"TURTLE": {"bad": None}}))
    with pytest.raises(ValueError, match="registry_open_trades_row_invalid"):
        preview_paper_registry_sources({"open_trades": {"bad": None}, "closed_trades": []}, _sources())


def test_preview_module_is_offline_and_contains_no_write_or_network_client():
    from pathlib import Path

    source = Path("paper_registry_source_preview.py").read_text(encoding="utf-8").lower()
    for forbidden in ("import requests", "import redis", "import urllib", "import socket", "import subprocess"):
        assert forbidden not in source
    # In-memory str.replace is used to mirror DONKEY's symbol normalization;
    # filesystem mutation methods remain prohibited in this preview module.
    for forbidden in (".write_text(", ".write_bytes(", ".unlink(", ".rename("):
        assert forbidden not in source


def test_cli_reads_local_snapshots_and_prints_sanitized_report_without_modifying_them(tmp_path, capsys):
    registry_path = tmp_path / "registry.json"
    source_path = tmp_path / "sources.json"
    registry_path.write_text(json.dumps(_registry({"bot": "TURTLE", "trade_id": "private-id"})), encoding="utf-8")
    source_path.write_text(json.dumps(_sources({"trade_registry_id": "private-id"})), encoding="utf-8")
    registry_before = registry_path.read_bytes()
    source_before = source_path.read_bytes()

    result = preview_main([
        "--registry-snapshot", str(registry_path),
        "--source-snapshot", str(source_path),
    ])

    output = capsys.readouterr().out
    assert result == 0
    assert "private-id" not in output
    sanitized = json.loads(output)
    assert sanitized["all_rows_ineligible_for_import"] is True
    assert sanitized["row_details_omitted"] is True
    assert "rows" not in sanitized
    assert "registry_snapshot_sha256" not in sanitized
    assert "source_snapshot_sha256" not in sanitized
    assert "registry-open_trades-0001-" not in output
    assert "source-0001-" not in output
    assert registry_path.read_bytes() == registry_before
    assert source_path.read_bytes() == source_before


def test_cli_omits_caller_controlled_status_mode_and_bot_labels(tmp_path, capsys):
    registry_path = tmp_path / "registry.json"
    source_path = tmp_path / "sources.json"
    private_registry_mode = "SYNTHETIC_PRIVATE_REGISTRY_MODE_SENTINEL"
    registry_path.write_text(
        json.dumps(_registry({"bot": "TURTLE", "registry_mode": private_registry_mode})),
        encoding="utf-8",
    )
    sources = _source_snapshot(
        {
            "TURTLE": {
                "private-locator": {
                    "status": "SYNTHETIC_PRIVATE_STATUS_SENTINEL",
                    "execution_mode": "SYNTHETIC_PRIVATE_MODE_SENTINEL",
                },
            },
        },
        {
            "COBRA": "SYNTHETIC_PRIVATE_SOURCE_STATUS_SENTINEL",
        },
    )
    source_path.write_text(json.dumps(sources), encoding="utf-8")

    result = preview_main([
        "--registry-snapshot", str(registry_path),
        "--source-snapshot", str(source_path),
    ])

    output = capsys.readouterr().out
    assert result == 0
    for sentinel in (
        "SYNTHETIC_PRIVATE_STATUS_SENTINEL",
        "SYNTHETIC_PRIVATE_MODE_SENTINEL",
        "SYNTHETIC_PRIVATE_SOURCE_STATUS_SENTINEL",
        private_registry_mode,
        "private-locator",
    ):
        assert sentinel not in output
    sanitized = json.loads(output)
    assert sanitized["all_rows_ineligible_for_import"] is True
    assert sanitized["registry_mode_claim_counts"] == {"INVALID": 1}
    assert sanitized["source_reconciliation_counts"]["unresolved_incomplete_snapshot"] == 1
    assert "source_diagnostics" not in sanitized
    assert "source_incomplete_bots" not in sanitized
