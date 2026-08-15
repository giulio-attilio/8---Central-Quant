from __future__ import annotations

import copy
import json
import socket
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

import trade_evidence_identity_offset_index_v1 as offset_index
import trade_evidence_identity_offset_shadow_compare_v1 as shadow_compare
import trade_timeline_validator as validator


TRADE_ID = "TURTLE:BTCUSDT:LONG"
INSTANCE_ID = "TRADE-UUID-NEW"


def _blocked_network(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("network access is forbidden in shadow parity tests")


@pytest.fixture(autouse=True)
def _isolate_test_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "create_connection", _blocked_network)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked_network)
    monkeypatch.setattr(socket.socket, "connect", _blocked_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_network)
    shadow_compare.reset_shadow_telemetry()


@dataclass(frozen=True)
class _ParityCase:
    root: Path
    history_path: Path
    timeline_path: Path
    history_index: Path
    timeline_index: Path
    history_offsets: Mapping[str, int]
    timeline_offsets: Mapping[str, int]
    expected_history_ids: tuple[str, ...]
    expected_timeline_ids: tuple[str, ...]


def _line(record: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> Mapping[str, int]:
    offsets: dict[str, int] = {}
    cursor = 0
    with path.open("wb") as handle:
        for record in records:
            event_id = str(record.get("event_id") or "")
            encoded = _line(record)
            if event_id:
                offsets[event_id] = cursor
            handle.write(encoded)
            cursor += len(encoded)
    return offsets


def _build_config() -> offset_index.BuildConfig:
    # The Phase B reader deliberately accepts only indexes built with the same
    # maximum physical-line contract as the legacy bounded reader.
    return offset_index.BuildConfig(
        block_bytes=64,
        segment_target_bytes=512,
        batch_bytes=4 * 1024,
        batch_lines=4,
        max_line_bytes=validator.JSONL_MAX_BYTES,
        anchor_bytes=64,
        busy_timeout_ms=50,
    )


def _build_index(source: Path, index: Path, source_id: str) -> None:
    original = source.read_bytes()
    report = offset_index.build_index(
        source,
        index,
        source_id,
        config=_build_config(),
        measure_memory=False,
    )
    assert report.published is True
    assert report.state == "READY"
    assert source.read_bytes() == original


def _registry_records() -> Mapping[str, Any]:
    common = {
        "trade_id": TRADE_ID,
        "bot": "TURTLE",
        "setup": "BREAKOUT",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    old = {
        **common,
        "trade_uuid": "TRADE-UUID-OLD",
        "registry_id": "REGISTRY-OLD",
        "lifecycle_id": "LIFECYCLE-OLD",
        "client_order_id": "ENTRY-OLD",
        "opened_at": "2026-08-13T10:00:00Z",
        "closed_at": "2026-08-13T11:00:00Z",
        "status": "CLOSED",
    }
    recent = {
        **common,
        "trade_uuid": INSTANCE_ID,
        "registry_id": "REGISTRY-NEW",
        "lifecycle_id": "LIFECYCLE-NEW",
        "client_order_id": "ENTRY-NEW",
        "opened_at": "2026-08-14T12:00:00Z",
        "status": "OPEN",
    }
    return {
        "open_trades": {"recent": recent},
        "closed_trades": [old],
    }


def _history_records() -> list[Mapping[str, Any]]:
    return [
        {
            "trade_id": TRADE_ID,
            "trade_uuid": "TRADE-UUID-OLD",
            "event": "SIGNAL_RECEIVED",
            "event_id": "H-OLD-INSTANCE",
            "timestamp": "2026-08-13T10:00:01Z",
        },
        {
            # Strong identity with no logical trade ID.
            "trade_uuid": INSTANCE_ID,
            "event": "SIGNAL_RECEIVED",
            "event_id": "H-OLDER-CURRENT",
            "timestamp": "2026-08-14T12:00:05Z",
        },
        {
            # One strong match promotes a secondary execution ID and an order.
            "trade_uuid": INSTANCE_ID,
            "execution_id": "EXECUTION-NEW",
            "broker_order_id": "ORDER-CROSS-TYPE",
            "event": "RISK_APPROVED",
            "event_id": "H-MULTI-PROMOTION",
            "timestamp": "2026-08-14T12:00:20Z",
        },
        {
            # This row is discoverable only after H-MULTI-PROMOTION.
            "execution_id": "EXECUTION-NEW",
            "event": "EXECUTION_REQUESTED",
            "event_id": "H-EXECUTION-ONLY-A",
            "timestamp": "2026-08-14T12:00:40Z",
        },
        {
            # broker_order_id and exchange_order_id must correlate by group.
            "exchange_order_id": "ORDER-CROSS-TYPE",
            "event": "LIVE_ORDER_SENT",
            "event_id": "H-CROSS-TYPE-ORDER",
            "timestamp": "2026-08-14T12:01:00Z",
        },
        {
            # A known order cannot override a conflicting scoped trade UUID.
            "trade_uuid": "TRADE-UUID-FOREIGN",
            "exchange_order_id": "ORDER-CROSS-TYPE",
            "event": "BROKER_ACK",
            "event_id": "H-SCOPED-CONFLICT",
            "timestamp": "2026-08-14T12:01:10Z",
        },
        {
            # A second non-repeatable request is intentionally duplicated.
            "execution_id": "EXECUTION-NEW",
            "event": "EXECUTION_REQUESTED",
            "event_id": "H-EXECUTION-ONLY-B",
            "timestamp": "2026-08-14T12:02:00Z",
        },
        {
            "execution_id": "EXECUTION-NEW",
            "decision_id": "DECISION-NEW",
            "event": "TP50",
            "event_id": "H-RECENT",
            "timestamp": "2026-08-14T12:08:00Z",
        },
        {
            # Physical order intentionally differs from timestamp order.
            "decision_id": "DECISION-NEW",
            "event": "BREAK_EVEN",
            "event_id": "H-TIMESTAMP-OUT-OF-ORDER",
            "timestamp": "2026-08-14T12:03:00Z",
        },
    ]


def _timeline_records() -> list[Mapping[str, Any]]:
    return [
        {
            "trade_id": TRADE_ID,
            "trade_uuid": "TRADE-UUID-OLD",
            "event": "POSITION_OPEN",
            "event_id": "T-OLD-INSTANCE",
            "timestamp": "2026-08-13T10:00:02Z",
        },
        {
            "lifecycle_id": "LIFECYCLE-NEW",
            "event": "POSITION_OPEN",
            "event_id": "T-STRONG-LIFECYCLE",
            "timestamp": "2026-08-14T12:04:00Z",
        },
        {
            # History promoted DECISION-NEW; this row then promotes a fill.
            "decision_id": "DECISION-NEW",
            "fill_id": "FILL-CROSS-TYPE",
            "event": "TP50",
            "event_id": "T-MULTI-PROMOTION",
            "timestamp": "2026-08-14T12:09:00Z",
        },
        {
            # fill_id and fill_ids are distinct typed keys in the same group.
            "fill_ids": ["FILL-CROSS-TYPE"],
            "event": "BREAK_EVEN",
            "event_id": "T-CROSS-TYPE-FILL",
            "timestamp": "2026-08-14T12:05:00Z",
        },
        {
            "fill_id": "FILL-CROSS-TYPE",
            "event": "POSITION_OPEN",
            "event_id": "T-DUPLICATE-POSITION",
            "timestamp": "2026-08-14T12:10:00Z",
        },
        {
            "lifecycle_id": "LIFECYCLE-FOREIGN",
            "fill_id": "FILL-CROSS-TYPE",
            "event": "TRAILING_UPDATED",
            "event_id": "T-SCOPED-CONFLICT",
            "timestamp": "2026-08-14T12:11:00Z",
        },
    ]


@pytest.fixture
def parity_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _ParityCase:
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    _shadow_off(monkeypatch)

    (tmp_path / "trade_registry.json").write_text(
        json.dumps(_registry_records(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    history_path = tmp_path / "history_events.jsonl"
    timeline_path = tmp_path / "timeline.jsonl"
    history_records = _history_records()
    timeline_records = _timeline_records()
    history_offsets = _write_jsonl(history_path, history_records)
    timeline_offsets = _write_jsonl(timeline_path, timeline_records)
    history_index = tmp_path / "history.identity-offset-v1.sqlite3"
    timeline_index = tmp_path / "timeline.identity-offset-v1.sqlite3"
    _build_index(history_path, history_index, "history_manager")
    _build_index(timeline_path, timeline_index, "timeline")

    excluded = {
        "H-OLD-INSTANCE",
        "H-SCOPED-CONFLICT",
        "T-OLD-INSTANCE",
        "T-SCOPED-CONFLICT",
    }
    return _ParityCase(
        root=tmp_path,
        history_path=history_path,
        timeline_path=timeline_path,
        history_index=history_index,
        timeline_index=timeline_index,
        history_offsets=history_offsets,
        timeline_offsets=timeline_offsets,
        expected_history_ids=tuple(
            str(row["event_id"])
            for row in history_records
            if row["event_id"] not in excluded
        ),
        expected_timeline_ids=tuple(
            str(row["event_id"])
            for row in timeline_records
            if row["event_id"] not in excluded
        ),
    )


def _shadow_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "TRADE_EVIDENCE_INDEX_SHADOW_ENABLED",
        "TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED",
        "TRADE_EVIDENCE_INDEX_HISTORY_PATH",
        "TRADE_EVIDENCE_INDEX_TIMELINE_PATH",
        "TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE",
        "TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


def _shadow_on(
    monkeypatch: pytest.MonkeyPatch,
    case: _ParityCase,
    *,
    history_index: Path | None = None,
    timeline_index: Path | None = None,
) -> None:
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "1")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "1")
    monkeypatch.setenv(
        "TRADE_EVIDENCE_INDEX_HISTORY_PATH",
        str(history_index if history_index is not None else case.history_index),
    )
    monkeypatch.setenv(
        "TRADE_EVIDENCE_INDEX_TIMELINE_PATH",
        str(timeline_index if timeline_index is not None else case.timeline_index),
    )
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE", "1")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED", "0")


def _normalized_report(report: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = copy.deepcopy(report)
    normalized.pop("generated_at", None)
    summary = normalized.get("summary")
    if isinstance(summary, dict):
        summary.pop("duration_ms", None)
    return normalized


def _validate(*, instance_id: str | None) -> Mapping[str, Any]:
    return validator.validate_trade_timeline(
        TRADE_ID,
        instance_id=instance_id,
    )


def _capture_observer(monkeypatch: pytest.MonkeyPatch) -> list[shadow_compare.ShadowCompareReport]:
    observed: list[shadow_compare.ShadowCompareReport] = []
    real_observer = shadow_compare.observe_evidence_bundle

    def capture(bundle: Any, **kwargs: Any) -> shadow_compare.ShadowCompareReport:
        result = real_observer(bundle, **kwargs)
        observed.append(result)
        return result

    monkeypatch.setattr(shadow_compare, "observe_evidence_bundle", capture)
    return observed


def _event_ids(rows: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(str(row.get("event_id") or "") for row in rows)


def test_resolved_history_timeline_match_preserves_exact_validator_response(
    parity_case: _ParityCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = _validate(instance_id=INSTANCE_ID)
    observed = _capture_observer(monkeypatch)
    _shadow_on(monkeypatch, parity_case)
    on = _validate(instance_id=INSTANCE_ID)

    assert _normalized_report(on) == _normalized_report(off)
    assert len(observed) == 1
    comparison = observed[0]
    assert comparison.status == shadow_compare.MATCH
    assert comparison.semantic_parity == shadow_compare.SEMANTIC_PARITY
    assert comparison.mismatch_categories == ()

    history = comparison.sources["history_manager"]
    timeline = comparison.sources["timeline"]
    assert history.status == timeline.status == shadow_compare.MATCH
    assert _event_ids(history.shadow_rows) == parity_case.expected_history_ids
    assert _event_ids(timeline.shadow_rows) == parity_case.expected_timeline_ids
    assert history.legacy_count == history.shadow_count == len(
        parity_case.expected_history_ids
    )
    assert timeline.legacy_count == timeline.shadow_count == len(
        parity_case.expected_timeline_ids
    )
    assert history.shadow_offsets == tuple(sorted(set(history.shadow_offsets)))
    assert timeline.shadow_offsets == tuple(sorted(set(timeline.shadow_offsets)))

    # These rows prove strong matching, within-source promotion, cross-type
    # grouping, and History -> Timeline promotion. Foreign scoped IDs stay out.
    assert {
        "H-OLDER-CURRENT",
        "H-MULTI-PROMOTION",
        "H-EXECUTION-ONLY-A",
        "H-CROSS-TYPE-ORDER",
        "H-RECENT",
        "H-TIMESTAMP-OUT-OF-ORDER",
    }.issubset(_event_ids(history.shadow_rows))
    assert {
        "T-STRONG-LIFECYCLE",
        "T-MULTI-PROMOTION",
        "T-CROSS-TYPE-FILL",
        "T-DUPLICATE-POSITION",
    }.issubset(_event_ids(timeline.shadow_rows))
    assert not {
        "H-OLD-INSTANCE",
        "H-SCOPED-CONFLICT",
    } & set(_event_ids(history.shadow_rows))
    assert not {
        "T-OLD-INSTANCE",
        "T-SCOPED-CONFLICT",
    } & set(_event_ids(timeline.shadow_rows))

    assert on["identity"]["ambiguous"] is False
    assert on["identity"]["selection_basis"] == "instance_id"
    assert on["components"]["history_manager"]["records"] == len(
        parity_case.expected_history_ids
    )
    assert on["components"]["timeline"]["records"] == len(
        parity_case.expected_timeline_ids
    )
    assert any(
        item["event"] == "EXECUTION_REQUESTED"
        and item["components"] == ["history_manager"]
        for item in on["events_duplicated"]
    )
    assert any(
        item["event"] == "POSITION_OPEN"
        and item["components"] == ["timeline"]
        for item in on["events_duplicated"]
    )

    history_times = [str(row["timestamp"]) for row in history.shadow_rows]
    assert history_times != sorted(history_times)
    event_times = [
        str(item["timestamp"])
        for item in on["events_found"]
        if item.get("timestamp") is not None
    ]
    assert event_times == sorted(event_times)


def test_reusable_trade_ambiguous_and_resolved_paths_preserve_response(
    parity_case: _ParityCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ambiguous_off = _validate(instance_id=None)
    observed = _capture_observer(monkeypatch)
    _shadow_on(monkeypatch, parity_case)
    ambiguous_on = _validate(instance_id=None)

    assert _normalized_report(ambiguous_on) == _normalized_report(ambiguous_off)
    assert ambiguous_on["identity"]["ambiguous"] is True
    assert ambiguous_on["identity"]["selection_basis"] == "ambiguous"
    assert len(observed) == 1
    ambiguous_comparison = observed[0]
    assert ambiguous_comparison.status == shadow_compare.NOT_COMPARABLE
    for source in shadow_compare.SHADOW_SOURCES:
        detail = ambiguous_comparison.sources[source]
        assert detail.status == shadow_compare.NOT_COMPARABLE
        assert detail.reasons == ("IDENTITY_AMBIGUOUS",)

    # The same physical evidence becomes eligible and matches when the Registry
    # occurrence is explicitly resolved.
    observed.clear()
    resolved_on = _validate(instance_id=INSTANCE_ID)
    assert len(observed) == 1
    assert observed[0].status == shadow_compare.MATCH
    assert resolved_on["identity"]["ambiguous"] is False
    assert resolved_on["identity"]["selection_basis"] == "instance_id"


def test_real_posting_mismatch_is_diagnostic_only_and_does_not_mutate_response(
    parity_case: _ParityCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = _validate(instance_id=INSTANCE_ID)
    missing_offset = parity_case.timeline_offsets["T-DUPLICATE-POSITION"]
    with sqlite3.connect(parity_case.timeline_index) as connection:
        deleted = connection.execute(
            "DELETE FROM postings WHERE start_offset=?",
            (missing_offset,),
        ).rowcount
    assert deleted > 0

    observed = _capture_observer(monkeypatch)
    _shadow_on(monkeypatch, parity_case)
    on = _validate(instance_id=INSTANCE_ID)

    assert _normalized_report(on) == _normalized_report(off)
    assert len(observed) == 1
    comparison = observed[0]
    assert comparison.status == shadow_compare.MISMATCH
    timeline = comparison.sources["timeline"]
    assert timeline.status == shadow_compare.MISMATCH
    assert shadow_compare.MISSING_INDEX_RECORD in timeline.mismatch_categories
    assert timeline.shadow_count == timeline.legacy_count - 1


def test_unavailable_index_and_observer_exception_never_mutate_response(
    parity_case: _ParityCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = _validate(instance_id=INSTANCE_ID)

    observed = _capture_observer(monkeypatch)
    _shadow_on(
        monkeypatch,
        parity_case,
        history_index=parity_case.root / "missing-history.sqlite3",
        timeline_index=parity_case.root / "missing-timeline.sqlite3",
    )
    unavailable = _validate(instance_id=INSTANCE_ID)
    assert _normalized_report(unavailable) == _normalized_report(off)
    assert len(observed) == 1
    assert observed[0].status == shadow_compare.INDEX_UNAVAILABLE
    assert {
        detail.index_status for detail in observed[0].sources.values()
    } == {offset_index.INDEX_MISSING}

    _shadow_on(monkeypatch, parity_case)

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("synthetic shadow observer failure")

    monkeypatch.setattr(shadow_compare, "observe_evidence_bundle", explode)
    isolated_exception = _validate(instance_id=INSTANCE_ID)
    assert _normalized_report(isolated_exception) == _normalized_report(off)
