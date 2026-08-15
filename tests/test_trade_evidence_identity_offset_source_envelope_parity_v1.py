from __future__ import annotations

import copy
import json
import socket
from collections.abc import Mapping, Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_shadow_compare_v1 import compare_source_semantics
from trade_evidence_identity_offset_source_envelope_v1 import (
    BUILT,
    INDEX_PLUS_TAIL,
    NEGATIVE_UNSAFE,
    plan_and_build_indexed_source_envelope,
)
from trade_evidence_physical_page_planner_v1 import REPRODUCIBLE, plan_physical_page


TRADE_ID = "C1-PARITY-TRADE"
TRADE_UUID = "C1-PARITY-UUID"
ROOT_ORDER_ID = "C1-PARITY-ORDER"
OPENED_AT = "2026-08-15T12:00:00Z"

DEFAULT_BYTE_BUDGET = 8 * 1024 * 1024
DEFAULT_RECORD_BUDGET = 10_000
DEFAULT_BLOCK_BYTES = 64


@pytest.fixture(autouse=True)
def _forbid_network_and_shadow_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in C1 parity tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", raising=False)


def _line(record: Mapping[str, Any], *, newline: bool = True) -> bytes:
    raw = json.dumps(
        dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _write_records(
    path: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    terminal_newline: bool = True,
) -> dict[str, int]:
    chunks: list[bytes] = []
    offsets: dict[str, int] = {}
    cursor = 0
    for position, record in enumerate(records):
        event_id = record.get("event_id")
        if event_id not in (None, ""):
            offsets[str(event_id)] = cursor
        chunk = _line(
            record,
            newline=terminal_newline or position < len(records) - 1,
        )
        chunks.append(chunk)
        cursor += len(chunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(chunks))
    return offsets


def _build_config() -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=DEFAULT_BLOCK_BYTES,
        segment_target_bytes=512,
        batch_bytes=16 * 1024,
        batch_lines=64,
        max_line_bytes=2 * 1024 * 1024,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )


def _build_v2(source: Path, source_id: str) -> Path:
    index = source.with_suffix(".identity-offset-v2.sqlite3")
    report = index_module.build_index_v2(
        source,
        index,
        source_id,
        config=_build_config(),
        measure_memory=False,
    )
    assert report.published is True
    assert report.state == "READY"
    validation = index_module.validate_index_v2(
        source,
        index,
        source_id,
        snapshot_eof=source.stat().st_size,
        deep=True,
    )
    assert validation.status == index_module.INDEX_V2_CERTIFIED, validation
    return index


def _anchored_context(
    trade_id: str = TRADE_ID,
    *,
    trade_uuid: str = TRADE_UUID,
    broker_order_id: str = ROOT_ORDER_ID,
) -> validator.CorrelationContext:
    context = validator.new_correlation_context(trade_id)
    registry_record = {
        "trade_id": trade_id,
        "trade_uuid": trade_uuid,
        "registry_id": f"REGISTRY::{trade_uuid}",
        "lifecycle_id": f"LIFECYCLE::{trade_uuid}",
        "client_order_id": f"CLIENT::{trade_uuid}",
        "broker_order_id": broker_order_id,
        "bot": "FALCON",
        "setup": "PARITY",
        "symbol": "BTC-USDT",
        "side": "LONG",
        "opened_at": OPENED_AT,
        "status": "OPEN",
    }
    assert validator.correlate_source_records(
        "registry", (registry_record,), context
    ) == [registry_record]
    assert context.registry_anchored is True
    return context


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_plain(item) for item in value), key=repr))
    if isinstance(value, (list, tuple)):
        return tuple(_plain(item) for item in value)
    return value


def _context_view(context: validator.CorrelationContext) -> dict[str, Any]:
    return {
        field.name: _plain(getattr(context, field.name))
        for field in fields(validator.CorrelationContext)
    }


def _identity_delta(
    before: validator.CorrelationContext,
    after: validator.CorrelationContext,
) -> dict[str, dict[str, tuple[str, ...]]]:
    typed = {
        key: tuple(sorted(set(values) - set(before.trusted_typed.get(key, set()))))
        for key, values in sorted(after.trusted_typed.items())
        if set(values) - set(before.trusted_typed.get(key, set()))
    }
    grouped = {
        key: tuple(sorted(set(values) - set(before.trusted.get(key, set()))))
        for key, values in sorted(after.trusted.items())
        if set(values) - set(before.trusted.get(key, set()))
    }
    return {"typed": typed, "grouped": grouped}


def _legacy_events(
    source_id: str, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        events.extend(validator._events_from_record(source_id, row))
    events = validator._deduplicate_extracted(events)
    events.sort(
        key=lambda item: (
            item.get("epoch") is None,
            item.get("epoch") or 0.0,
            validator.EVENT_ORDER.index(item["event"])
            if item["event"] in validator.EVENT_ORDER
            else 999,
        )
    )
    return events


def _legacy_coverage(
    metadata: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    coverage = {
        "evidence_found": bool(metadata.get("evidence_found", bool(rows))),
        "coverage_complete": bool(metadata.get("coverage_complete", True)),
        "partial": bool(metadata.get("partial", False)),
        "conclusive": bool(metadata.get("conclusive", True)),
        "bytes_scanned": int(metadata.get("bytes_scanned", 0) or 0),
        "records_examined": int(metadata.get("records_examined", len(rows)) or 0),
        "direction": metadata.get("direction", "IN_MEMORY"),
        "time_range_scanned": dict(
            metadata.get("time_range_scanned")
            or {"oldest": None, "newest": None}
        ),
        "stop_reason": metadata.get("stop_reason", "IN_MEMORY_COMPLETE"),
        "source_size_bytes": int(metadata.get("source_size_bytes", 0) or 0),
        "snapshot_eof": int(metadata.get("snapshot_eof", 0) or 0),
        "evidence_status": metadata.get(
            "evidence_status",
            "EVIDENCE_FOUND" if rows else "COMPLETE_NO_EVIDENCE",
        ),
    }
    if metadata.get("next_scan_cursor"):
        coverage["next_scan_cursor"] = metadata["next_scan_cursor"]
    return coverage


def _legacy_envelope(
    source_id: str,
    source: Path,
    context: validator.CorrelationContext,
    monkeypatch: pytest.MonkeyPatch,
    *,
    byte_budget: int,
    record_budget: int,
    block_bytes: int,
) -> dict[str, Any]:
    monkeypatch.setattr(validator, "JSONL_MAX_BYTES", byte_budget)
    monkeypatch.setattr(validator, "JSONL_MAX_VALID_LINES", record_budget)
    monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", block_bytes)
    value = validator._default_reader(source_id, (source,), context)(context.trade_id)
    # The legacy private envelope aliases the shared mutable context. Detach the
    # observation point so a later source cannot rewrite this assertion's past.
    value["_correlation_context"] = copy.deepcopy(value["_correlation_context"])
    return value


def _c1_envelope(
    source_id: str,
    source: Path,
    index: Path,
    context: validator.CorrelationContext,
    *,
    byte_budget: int,
    record_budget: int,
    block_bytes: int,
):
    plan = plan_physical_page(
        source,
        index,
        source_id,
        byte_budget=byte_budget,
        record_budget=record_budget,
        block_bytes=block_bytes,
        max_append_proof_bytes=1,
    )
    assert plan.status == REPRODUCIBLE, plan
    result = plan_and_build_indexed_source_envelope(
        source=source_id,
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        byte_budget=byte_budget,
        record_budget=record_budget,
        block_bytes=block_bytes,
    )
    assert result.status == BUILT, result
    assert _plain(result.raw_source_metadata["plan"]) == _plain(plan.to_dict())
    return plan, result


def _assert_zero_tolerance_parity(
    source_id: str,
    context_before: validator.CorrelationContext,
    legacy: Mapping[str, Any],
    result: Any,
    expected_offsets: Sequence[int],
) -> None:
    projected = result.to_legacy_private_envelope()
    legacy_rows = legacy["records"]
    indexed_rows = projected["records"]
    legacy_after = legacy["_correlation_context"]
    indexed_after = projected["_correlation_context"]

    assert indexed_rows == legacy_rows
    assert projected["_reader_metadata"] == legacy["_reader_metadata"]
    assert projected["_identity_metadata"] == legacy["_identity_metadata"]
    assert projected["_evidence_correlated"] is legacy["_evidence_correlated"] is True
    assert indexed_after == legacy_after
    assert _context_view(indexed_after) == _context_view(legacy_after)
    assert _plain(result.context_before) == _context_view(context_before)
    assert _plain(result.context_after) == _context_view(legacy_after)
    assert _plain(result.identifiers_discovered) == _identity_delta(
        context_before, legacy_after
    )

    metadata = legacy["_reader_metadata"]
    assert _plain(result.source_coverage) == _plain(
        _legacy_coverage(metadata, legacy_rows)
    )
    legacy_events = _legacy_events(source_id, legacy_rows)
    assert _plain(result.events) == _plain(legacy_events)
    assert _plain(validator._duplicates(list(result.events))) == _plain(
        validator._duplicates(legacy_events)
    )
    assert _plain(validator._chronology(list(result.events))) == _plain(
        validator._chronology(legacy_events)
    )

    assert result.factual_offsets == tuple(expected_offsets)
    assert compare_source_semantics(
        source_id,
        legacy_rows,
        indexed_rows,
        legacy_context=legacy_after,
        shadow_context=indexed_after,
        legacy_offsets=expected_offsets,
        shadow_offsets=result.factual_offsets,
    ) == ()


def _run_pair(
    source_id: str,
    source: Path,
    index: Path,
    seed: validator.CorrelationContext,
    monkeypatch: pytest.MonkeyPatch,
    expected_offsets: Sequence[int],
    *,
    byte_budget: int = DEFAULT_BYTE_BUDGET,
    record_budget: int = DEFAULT_RECORD_BUDGET,
    block_bytes: int = DEFAULT_BLOCK_BYTES,
):
    context_before = copy.deepcopy(seed)
    legacy_context = copy.deepcopy(seed)
    indexed_context = copy.deepcopy(seed)
    indexed_input_before = copy.deepcopy(indexed_context)

    legacy = _legacy_envelope(
        source_id,
        source,
        legacy_context,
        monkeypatch,
        byte_budget=byte_budget,
        record_budget=record_budget,
        block_bytes=block_bytes,
    )
    plan, result = _c1_envelope(
        source_id,
        source,
        index,
        indexed_context,
        byte_budget=byte_budget,
        record_budget=record_budget,
        block_bytes=block_bytes,
    )
    assert indexed_context == indexed_input_before
    _assert_zero_tolerance_parity(
        source_id, context_before, legacy, result, expected_offsets
    )
    return plan, legacy, result


def _selected_offsets(
    offsets: Mapping[str, int], event_ids: Sequence[str]
) -> tuple[int, ...]:
    return tuple(offsets[event_id] for event_id in event_ids)


@pytest.mark.parametrize("source_id", ["history_manager", "timeline"])
def test_full_identity_promotion_event_and_physical_envelope_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_id: str,
) -> None:
    records = [
        {
            # Same text as the target trade_uuid, but a different identity group.
            "registry_id": TRADE_UUID,
            "event_type": "SIGNAL",
            "event_id": "FOREIGN-CROSS-GROUP",
            "timestamp": "2026-08-15T12:00:00.500Z",
        },
        {
            "trade_id": TRADE_ID,
            "event_type": "SIGNAL",
            "event_id": "PERFECT",
            "timestamp": "2026-08-15T12:00:01Z",
        },
        {
            "trade_uuid": TRADE_UUID,
            "execution_id": "EXEC-A",
            "decision_id": "DECISION-A",
            "event_type": "RISK_APPROVED",
            "event_id": "STRONG-MULTI-PROMOTION",
            "timestamp": "2026-08-15T12:00:02Z",
        },
        {
            "execution_id": "EXEC-A",
            "signal_id": "SIGNAL-A",
            "event_type": "EXECUTION_REQUESTED",
            "event_id": "SECONDARY-PROMOTION",
            "timestamp": "2026-08-15T12:00:03Z",
        },
        {
            "signal_id": "SIGNAL-A",
            "decision_id": "DECISION-A",
            "execution_id": "EXEC-A",
            "event_type": "LIVE_ORDER_SENT",
            "event_id": "CIRCULAR-PROMOTION",
            "timestamp": "2026-08-15T12:00:04Z",
        },
        {
            # broker_order_id in Registry must fan out to exchange_order_id.
            "exchange_order_id": ROOT_ORDER_ID,
            "fill_id": "FILL-A",
            "event_type": "POSITION_OPEN",
            "event_id": "CROSS-TYPE-ORDER",
            "timestamp": "2026-08-15T12:00:05Z",
        },
        {
            "fill_ids": ["FILL-A"],
            "event_type": "POSITION_OPEN",
            "event_id": "DUPLICATE-POSITION-OPEN",
            "timestamp": "2026-08-15T12:00:06Z",
        },
        {
            "fill_id": "FILL-A",
            "event_type": "LIVE_TRADE_CLOSED",
            "event_id": "CLOSE-BEFORE-OPEN-BY-TIME",
            "timestamp": "2026-08-15T12:00:04.500Z",
        },
    ]
    source = tmp_path / source_id / f"{source_id}.jsonl"
    offsets = _write_records(source, records)
    index = _build_v2(source, source_id)
    expected_ids = (
        "PERFECT",
        "STRONG-MULTI-PROMOTION",
        "SECONDARY-PROMOTION",
        "CIRCULAR-PROMOTION",
        "CROSS-TYPE-ORDER",
        "DUPLICATE-POSITION-OPEN",
        "CLOSE-BEFORE-OPEN-BY-TIME",
    )

    _plan, legacy, result = _run_pair(
        source_id,
        source,
        index,
        _anchored_context(),
        monkeypatch,
        _selected_offsets(offsets, expected_ids),
    )

    assert [row["event_id"] for row in legacy["records"]] == list(expected_ids)
    assert all(
        row["event_id"] != "FOREIGN-CROSS-GROUP" for row in result.correlated_rows
    )
    duplicates = validator._duplicates(_legacy_events(source_id, legacy["records"]))
    assert {
        "event": "POSITION_OPEN",
        "occurrences": 2,
        "duplicates": 1,
        "components": [source_id],
    } in duplicates
    assert validator._chronology(
        _legacy_events(source_id, legacy["records"])
    )["ordered"] is False
    assert result.clone_context_after().trusted["execution"] == {"EXEC-A"}
    assert result.clone_context_after().trusted["decision"] == {"DECISION-A"}
    assert result.clone_context_after().trusted["signal"] == {"SIGNAL-A"}
    assert result.clone_context_after().trusted["fill"] == {"FILL-A"}


def test_synthetic_replay_start_before_page_start_is_legacy_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b'{"trade_id":"T","event_type":"POSITION_OPEN"}'
    assert len(payload) <= 62
    first_physical_line = (
        b"X" * 65 + payload + b" " * (62 - len(payload)) + b"\n"
    )
    raw = first_physical_line + b" " * 127 + b"\n\n"
    assert len(first_physical_line) == 128
    assert len(raw) == 257
    source = tmp_path / "replay" / "timeline.jsonl"
    source.parent.mkdir(parents=True)
    source.write_bytes(raw)
    index = _build_v2(source, "timeline")

    plan, legacy, result = _run_pair(
        "timeline",
        source,
        index,
        _anchored_context(
            "T", trade_uuid="UUID-T", broker_order_id="ORDER-T"
        ),
        monkeypatch,
        (65,),
        byte_budget=256,
        record_budget=100,
        block_bytes=64,
    )

    assert plan.page_start == 128
    assert plan.replay_start == 65
    assert legacy["records"] == [
        {"trade_id": "T", "event_type": "POSITION_OPEN"}
    ]
    assert result.factual_offsets == (65,)


@pytest.mark.parametrize("source_id", ["history_manager", "timeline"])
def test_terminal_line_without_lf_uses_certified_prefix_plus_tail_with_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_id: str,
) -> None:
    head = {
        "trade_uuid": TRADE_UUID,
        "execution_id": "EXEC-TAIL",
        "event_type": "SIGNAL",
        "event_id": "TAIL-HEAD",
        "timestamp": "2026-08-15T12:00:01Z",
    }
    terminal = {
        "execution_id": "EXEC-TAIL",
        "event_type": "POSITION_OPEN",
        "event_id": "TERMINAL-NO-LF",
        "timestamp": "2026-08-15T12:00:02Z",
    }
    source = tmp_path / f"terminal-{source_id}" / f"{source_id}.jsonl"
    offsets = _write_records(source, (head,))
    index = _build_v2(source, source_id)
    terminal_offset = source.stat().st_size
    with source.open("ab") as handle:
        handle.write(_line(terminal, newline=False))
    catchup = index_module.catch_up_index(
        source, index, source_id, measure_memory=False
    )
    assert catchup.safe_watermark_after == catchup.safe_watermark_before
    certification = index_module.read_index_certification(index)
    assert certification.certified_source_size == source.stat().st_size
    assert index_module.validate_index_v2(
        source,
        index,
        source_id,
        snapshot_eof=certification.certified_watermark,
        deep=True,
    ).status == index_module.INDEX_V2_CERTIFIED

    _plan, legacy, result = _run_pair(
        source_id,
        source,
        index,
        _anchored_context(),
        monkeypatch,
        (offsets["TAIL-HEAD"], terminal_offset),
    )

    assert [row["event_id"] for row in legacy["records"]] == [
        "TAIL-HEAD",
        "TERMINAL-NO-LF",
    ]
    assert result.index_mode == INDEX_PLUS_TAIL
    assert result.metrics.tail_bytes == source.stat().st_size - terminal_offset


@pytest.mark.parametrize(
    ("record_budget", "negative_status", "coverage_complete"),
    [
        (DEFAULT_RECORD_BUDGET, NEGATIVE_UNSAFE, True),
        (1, NEGATIVE_UNSAFE, False),
    ],
)
def test_zero_evidence_certified_and_unsafe_have_exact_legacy_envelopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_budget: int,
    negative_status: str,
    coverage_complete: bool,
) -> None:
    source = tmp_path / f"zero-{record_budget}" / "history_manager.jsonl"
    _write_records(
        source,
        tuple(
            {
                "trade_id": f"FOREIGN-{position}",
                "event_type": "SIGNAL",
                "event_id": f"FOREIGN-{position}",
                "timestamp": f"2026-08-15T12:00:0{position}Z",
            }
            for position in range(1, 5)
        ),
    )
    index = _build_v2(source, "history_manager")

    plan, legacy, result = _run_pair(
        "history_manager",
        source,
        index,
        _anchored_context(),
        monkeypatch,
        (),
        record_budget=record_budget,
    )

    assert legacy["records"] == []
    assert result.correlated_rows == ()
    assert plan.coverage_complete is coverage_complete
    assert result.negative_status == negative_status


def test_zero_mapping_page_is_negative_certified_and_legacy_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "zero-no-mapping" / "history_manager.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"\n[]\n{bad}\n")
    index = _build_v2(source, "history_manager")

    plan, legacy, result = _run_pair(
        "history_manager",
        source,
        index,
        _anchored_context(),
        monkeypatch,
        (),
    )

    assert legacy["records"] == []
    assert result.correlated_rows == ()
    assert plan.mapping_records == 0
    assert result.metrics.record_count == 0
    assert result.negative_status == NEGATIVE_UNSAFE


def test_history_then_timeline_parity_and_intermediate_context_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_record = {
        "trade_uuid": TRADE_UUID,
        "decision_id": "DECISION-FROM-HISTORY",
        "event_type": "RISK_APPROVED",
        "event_id": "HISTORY-PROMOTION",
        "timestamp": "2026-08-15T12:00:01Z",
    }
    timeline_records = (
        {
            "decision_id": "DECISION-FROM-HISTORY",
            "event_type": "EXECUTION_REQUESTED",
            "event_id": "TIMELINE-FROM-HISTORY",
            "timestamp": "2026-08-15T12:00:02Z",
        },
        {
            "exchange_order_id": "ORDER-FROM-INTERMEDIATE",
            "event_type": "POSITION_OPEN",
            "event_id": "TIMELINE-FROM-INTERMEDIATE",
            "timestamp": "2026-08-15T12:00:03Z",
        },
    )
    history = tmp_path / "chain" / "history_manager.jsonl"
    timeline = tmp_path / "chain" / "timeline.jsonl"
    history_offsets = _write_records(history, (history_record,))
    timeline_offsets = _write_records(timeline, timeline_records)
    history_index = _build_v2(history, "history_manager")
    timeline_index = _build_v2(timeline, "timeline")
    seed = _anchored_context()

    _history_plan, legacy_history, indexed_history = _run_pair(
        "history_manager",
        history,
        history_index,
        seed,
        monkeypatch,
        (history_offsets["HISTORY-PROMOTION"],),
    )

    # Direct History -> Timeline sees History's promotions, but cannot invent
    # the order identity that belongs to the intervening components.
    direct_seed = indexed_history.clone_context_after()
    _direct_plan, legacy_direct, indexed_direct = _run_pair(
        "timeline",
        timeline,
        timeline_index,
        direct_seed,
        monkeypatch,
        (timeline_offsets["TIMELINE-FROM-HISTORY"],),
    )
    assert [row["event_id"] for row in legacy_direct["records"]] == [
        "TIMELINE-FROM-HISTORY"
    ]
    assert [row["event_id"] for row in indexed_direct.correlated_rows] == [
        "TIMELINE-FROM-HISTORY"
    ]

    # In the real component order, execution_engine/orchestrator/broker/shadow
    # run between History and Timeline and may legitimately promote identities.
    legacy_middle_context = copy.deepcopy(legacy_history["_correlation_context"])
    indexed_middle_context = indexed_history.clone_context_after()
    middle_record = {
        "trade_uuid": TRADE_UUID,
        "execution_id": "EXECUTION-FROM-INTERMEDIATE",
        "broker_order_id": "ORDER-FROM-INTERMEDIATE",
        "event_type": "LIVE_ORDER_SENT",
        "event_id": "INTERMEDIATE-PROMOTION",
        "timestamp": "2026-08-15T12:00:02.500Z",
    }
    assert validator.correlate_source_records(
        "execution_engine", (middle_record,), legacy_middle_context
    ) == [middle_record]
    assert validator.correlate_source_records(
        "execution_engine", (middle_record,), indexed_middle_context
    ) == [middle_record]
    assert legacy_middle_context == indexed_middle_context
    assert "ORDER-FROM-INTERMEDIATE" in indexed_middle_context.trusted["order"]

    _middle_plan, legacy_after_middle, indexed_after_middle = _run_pair(
        "timeline",
        timeline,
        timeline_index,
        indexed_middle_context,
        monkeypatch,
        _selected_offsets(
            timeline_offsets,
            ("TIMELINE-FROM-HISTORY", "TIMELINE-FROM-INTERMEDIATE"),
        ),
    )
    expected = ["TIMELINE-FROM-HISTORY", "TIMELINE-FROM-INTERMEDIATE"]
    assert [row["event_id"] for row in legacy_after_middle["records"]] == expected
    assert [row["event_id"] for row in indexed_after_middle.correlated_rows] == expected
    assert indexed_after_middle.clone_context_after() == legacy_after_middle[
        "_correlation_context"
    ]
