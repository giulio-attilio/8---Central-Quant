from __future__ import annotations

import copy
import json
import socket
from pathlib import Path
from typing import Any, Mapping

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_full_shadow_v2 import (
    MATCH,
    POSITIVE_UNSAFE,
    IndexedJournalSpec,
    run_full_response_shadow_v2,
)
from trade_evidence_physical_window_contract_v1 import encode_scan_cursor


TRADE_ID = "C2-PARITY-V2-TRADE"
TRADE_UUID = "C2-PARITY-V2-UUID"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in C2 parity tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", raising=False)


def _json_line(record: Mapping[str, Any], *, newline: bool = True) -> bytes:
    raw = json.dumps(
        dict(record), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return raw + (b"\n" if newline else b"")


def _config() -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=64 * 1024,
        segment_target_bytes=512 * 1024,
        batch_bytes=2 * 1024 * 1024,
        batch_lines=512,
        max_line_bytes=2 * 1024 * 1024,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )


def _build(source: Path, source_id: str) -> Path:
    index = source.with_suffix(".full-v2.sqlite3")
    report = index_module.build_index_v2(
        source,
        index,
        source_id,
        config=_config(),
        measure_memory=False,
    )
    assert report.published is True
    assert index_module.read_index_certification(index).full_certified is True
    return index


def _registry(*, ambiguous: bool = False) -> tuple[dict[str, Any], Any]:
    context = validator.new_correlation_context(TRADE_ID)
    base = {
        "trade_id": TRADE_ID,
        "trade_uuid": TRADE_UUID,
        "registry_id": f"REG::{TRADE_UUID}",
        "lifecycle_id": f"LC::{TRADE_UUID}",
        "client_order_id": f"CLIENT::{TRADE_UUID}",
        "symbol": "BTC-USDT",
        "side": "LONG",
        "bot": "TURTLE" if ambiguous else "FALCON",
        "setup": "C2-PARITY",
        "status": "OPEN",
    }
    if ambiguous:
        candidates = [
            {**base, "trade_uuid": "INSTANCE-A", "opened_at": "2026-08-15T10:00:00Z"},
            {**base, "trade_uuid": "INSTANCE-B", "opened_at": "2026-08-15T11:00:00Z"},
        ]
        assert validator.correlate_source_records("registry", candidates, context) == []
        records: list[Mapping[str, Any]] = []
    else:
        base["opened_at"] = "2026-08-15T12:00:00Z"
        assert validator.correlate_source_records("registry", (base,), context) == [base]
        records = [base]
    return (
        {
            "records": records,
            "_identity_metadata": validator.identity_resolution_metadata(context),
            "_evidence_correlated": True,
            "_correlation_context": context,
        },
        context,
    )


def _static() -> dict[str, Any]:
    return {
        "lifecycle": [],
        "execution_engine": [],
        "execution_orchestrator": [],
        "broker": [],
        "shadow_runtime": [],
        "telegram": [],
        "falcon": [],
        "external_exposure": [],
    }


def _run(
    registry: Mapping[str, Any],
    history: Path,
    history_index: Path,
    timeline: Path,
    timeline_index: Path,
    *,
    history_cursor: str | None = None,
    timeline_cursor: str | None = None,
    planner_options: Mapping[str, Any] | None = None,
    measure_memory: bool = False,
):
    return run_full_response_shadow_v2(
        TRADE_ID,
        resolved_registry_envelope=registry,
        static_sources=_static(),
        history=IndexedJournalSpec(
            history,
            history_index,
            scan_cursor=history_cursor,
            planner_options=dict(planner_options or {}),
        ),
        timeline=IndexedJournalSpec(
            timeline,
            timeline_index,
            scan_cursor=timeline_cursor,
            planner_options=dict(planner_options or {}),
        ),
        now_epoch=1_787_000_000.0,
        measure_memory=measure_memory,
    )


def test_invalid_json_and_terminal_no_lf_remain_full_response_exact(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history.jsonl"
    timeline = tmp_path / "timeline.jsonl"
    history.write_bytes(
        b"{bad}\n"
        + _json_line(
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "RISK_APPROVED",
                "timestamp": "2026-08-15T12:00:01Z",
            }
        )
    )
    timeline.write_bytes(
        _json_line(
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "EXECUTION_REQUESTED",
                "timestamp": "2026-08-15T12:00:02Z",
            }
        )
    )
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    with timeline.open("ab") as handle:
        handle.write(
            _json_line(
                {
                    "trade_uuid": TRADE_UUID,
                    "event_type": "POSITION_OPEN",
                    "timestamp": "2026-08-15T12:00:03Z",
                },
                newline=False,
            )
        )
    catchup = index_module.catch_up_index(
        timeline, timeline_index, "timeline", measure_memory=False
    )
    assert catchup.safe_watermark_after == catchup.safe_watermark_before
    registry, original_context = _registry()
    before = copy.deepcopy(original_context)

    result = _run(registry, history, history_index, timeline, timeline_index)

    assert result.report.status == MATCH, result.report.to_dict()
    assert result.report.source_results["timeline"]["index_mode"] == "INDEX_PLUS_TAIL"
    assert result.report.source_results["timeline"][
        "evidence_completeness"
    ] == POSITIVE_UNSAFE
    assert result.hybrid_bundle is not None
    assert result.hybrid_bundle.component_status["history_manager"]["invalid_lines"] == 1
    assert [
        row["event_type"] for row in result.hybrid_bundle.records["timeline"]
    ] == ["EXECUTION_REQUESTED", "POSITION_OPEN"]
    assert original_context == before


def test_first_and_continuation_cursor_pages_match_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(validator, "JSONL_MAX_VALID_LINES", 2)
    history = tmp_path / "history-cursor.jsonl"
    timeline = tmp_path / "timeline-cursor.jsonl"
    rows = [
        {
            "trade_uuid": TRADE_UUID,
            "event_type": f"EVENT_{position}",
            "timestamp": f"2026-08-15T12:00:0{position}Z",
        }
        for position in range(1, 5)
    ]
    history.write_bytes(b"".join(_json_line(row) for row in rows))
    timeline.write_bytes(b"".join(_json_line(row) for row in rows))
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    registry, _context = _registry()
    options = {
        "byte_budget": validator.JSONL_MAX_BYTES,
        "record_budget": 2,
        "block_bytes": validator.JSONL_BLOCK_BYTES,
    }

    first = _run(
        registry,
        history,
        history_index,
        timeline,
        timeline_index,
        planner_options=options,
    )
    assert first.report.status == MATCH, first.report.to_dict()
    assert first.legacy_bundle is not None
    cursor = first.legacy_bundle.source_coverage["history_manager"][
        "next_scan_cursor"
    ]
    assert cursor == first.hybrid_bundle.source_coverage["history_manager"][
        "next_scan_cursor"
    ]
    assert first.report.source_results["history_manager"][
        "evidence_completeness"
    ] == POSITIVE_UNSAFE

    continuation = _run(
        registry,
        history,
        history_index,
        timeline,
        timeline_index,
        history_cursor=cursor,
        planner_options=options,
    )
    assert continuation.report.status == MATCH, continuation.report.to_dict()
    assert continuation.legacy_bundle is not None
    assert continuation.legacy_bundle.source_coverage["history_manager"] == (
        continuation.hybrid_bundle.source_coverage["history_manager"]
    )
    assert continuation.legacy_bundle.source_coverage["history_manager"][
        "partial"
    ] is True
    assert continuation.report.source_results["history_manager"][
        "evidence_completeness"
    ] == POSITIVE_UNSAFE


def test_unsigned_cursor_with_positive_prefix_is_never_complete(
    tmp_path: Path,
) -> None:
    history = tmp_path / "history-forged-cursor.jsonl"
    timeline = tmp_path / "timeline-forged-cursor.jsonl"
    encoded_rows = [
        _json_line(
            {
                "trade_uuid": TRADE_UUID,
                "event_type": f"EVENT_{position}",
                "timestamp": f"2026-08-15T12:00:0{position}Z",
            }
        )
        for position in range(1, 6)
    ]
    history.write_bytes(b"".join(encoded_rows))
    timeline.write_bytes(encoded_rows[0])
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    registry, _context = _registry()
    forged_cursor = encode_scan_cursor(
        history,
        history.stat(),
        history.stat().st_size,
        sum(len(row) for row in encoded_rows[:4]),
        coverage_tainted=False,
    )

    result = _run(
        registry,
        history,
        history_index,
        timeline,
        timeline_index,
        history_cursor=forged_cursor,
    )

    assert result.report.status == MATCH, result.report.to_dict()
    assert len(result.hybrid_bundle.records["history_manager"]) == 4
    assert result.report.source_results["history_manager"][
        "evidence_completeness"
    ] == POSITIVE_UNSAFE


def test_reusable_turtle_ambiguity_matches_but_negative_remains_unsafe(
    tmp_path: Path,
) -> None:
    history = tmp_path / "ambiguous-history.jsonl"
    timeline = tmp_path / "ambiguous-timeline.jsonl"
    history.write_bytes(
        _json_line({"trade_id": "FOREIGN", "event_type": "SIGNAL"})
    )
    timeline.write_bytes(
        _json_line({"trade_id": "FOREIGN", "event_type": "POSITION_OPEN"})
    )
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    registry, context = _registry(ambiguous=True)
    assert context.identity_ambiguous is True

    result = _run(registry, history, history_index, timeline, timeline_index)

    assert result.report.status == MATCH, result.report.to_dict()
    for source in ("history_manager", "timeline"):
        assert result.report.source_results[source]["negative_status"] == "NEGATIVE_UNSAFE"
    assert result.hybrid_bundle is not None
    assert result.hybrid_bundle.registry_resolution["ambiguous"] is True


def test_full_pipeline_over_64_mib_is_exact_and_index_io_is_bounded(
    tmp_path: Path,
) -> None:
    history = tmp_path / "large-history.jsonl"
    timeline = tmp_path / "small-timeline.jsonl"
    blank_line = b" " * (64 * 1024 - 1) + b"\n"
    with history.open("wb") as handle:
        for _ in range(1025):
            handle.write(blank_line)
        handle.write(
            _json_line(
                {
                    "trade_uuid": TRADE_UUID,
                    "event_type": "RISK_APPROVED",
                    "timestamp": "2026-08-15T12:00:01Z",
                }
            )
        )
    assert history.stat().st_size > 64 * 1024 * 1024
    timeline.write_bytes(
        _json_line(
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "POSITION_OPEN",
                "timestamp": "2026-08-15T12:00:02Z",
            }
        )
    )
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    registry, _context = _registry()

    result = _run(
        registry,
        history,
        history_index,
        timeline,
        timeline_index,
        measure_memory=True,
    )

    assert result.report.status == MATCH, result.report.to_dict()
    metrics = result.report.metrics
    assert metrics.hybrid_journal_bytes < 16 * 1024 * 1024
    assert metrics.legacy_journal_bytes >= 64 * 1024 * 1024
    assert metrics.total_journal_bytes == (
        metrics.legacy_journal_bytes + metrics.hybrid_journal_bytes
    )
    assert metrics.history_journal_bytes < 8 * 1024 * 1024
    hybrid_composite_ms = (
        metrics.history_certification_ms
        + metrics.timeline_certification_ms
        + metrics.hybrid_bundle_ms
        + metrics.hybrid_validator_ms
        + metrics.hybrid_snapshot_ms
    )
    assert hybrid_composite_ms < 3_000
    assert metrics.peak_tracemalloc_bytes is not None
    # The measurement includes the 64-MiB authoritative legacy comparator;
    # this is a smoke ceiling, not a productive p95/RSS claim.
    assert metrics.peak_tracemalloc_bytes < 192 * 1024 * 1024
