from __future__ import annotations

import copy
import ast
import datetime
import json
import os
import socket
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
import trade_evidence_identity_offset_full_shadow_v2 as full_shadow_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_full_shadow_v2 import (
    FALLBACK_REQUIRED,
    FullShadowCaps,
    MATCH,
    NOT_COMPARABLE,
    IndexedJournalSpec,
    run_full_response_shadow_v2,
    snapshot_public_payload,
    timeline_public_payload,
)
from trade_evidence_identity_offset_source_envelope_v1 import EnvelopeCaps


TRADE_ID = "C2-FULL-SHADOW-TRADE"
TRADE_UUID = "C2-FULL-SHADOW-UUID"
OPENED_AT = "2026-08-15T12:00:00Z"
NOW_EPOCH = 1_787_000_000.0


@pytest.fixture(autouse=True)
def _forbid_network_and_runtime_shadow(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in C2 tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", raising=False)
    monkeypatch.delenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", raising=False)


def _line(record: Mapping[str, Any], *, newline: bool = True) -> bytes:
    value = json.dumps(
        dict(record), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return value + (b"\n" if newline else b"")


def _write(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_line(row) for row in rows))


def _config() -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=64,
        segment_target_bytes=512,
        batch_bytes=16 * 1024,
        batch_lines=64,
        max_line_bytes=2 * 1024 * 1024,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )


def _build(source: Path, source_id: str) -> Path:
    index = source.with_suffix(".c2.sqlite3")
    report = index_module.build_index_v2(
        source,
        index,
        source_id,
        config=_config(),
        measure_memory=False,
    )
    assert report.published is True
    certification = index_module.read_index_certification(index)
    assert certification.full_certified is True, certification
    return index


def _registry_envelope() -> tuple[dict[str, Any], validator.CorrelationContext]:
    context = validator.new_correlation_context(TRADE_ID)
    record = {
        "trade_id": TRADE_ID,
        "trade_uuid": TRADE_UUID,
        "registry_id": f"REGISTRY::{TRADE_UUID}",
        "lifecycle_id": f"LIFECYCLE::{TRADE_UUID}",
        "client_order_id": f"CLIENT::{TRADE_UUID}",
        "broker_order_id": "ORDER-ROOT",
        "bot": "FALCON",
        "setup": "C2",
        "symbol": "BTC-USDT",
        "side": "LONG",
        "opened_at": OPENED_AT,
        "status": "OPEN",
        "remaining_quantity": "0.01",
    }
    assert validator.correlate_source_records("registry", (record,), context) == [record]
    envelope = {
        "records": [record],
        "_identity_metadata": validator.identity_resolution_metadata(context),
        "_evidence_correlated": True,
        "_correlation_context": context,
    }
    return envelope, context


def _static_sources() -> dict[str, Any]:
    return {
        "lifecycle": [
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "SIGNAL",
                "current_state": "ENTRY_CONFIRMED",
                "timestamp": "2026-08-15T12:00:00.500Z",
            }
        ],
        "execution_engine": [
            {
                "decision_id": "DECISION-HISTORY",
                "execution_id": "EXEC-MIDDLE",
                "broker_order_id": "ORDER-MIDDLE",
                "event_type": "EXECUTION_REQUESTED",
                "timestamp": "2026-08-15T12:00:02Z",
            }
        ],
        "execution_orchestrator": [
            {
                "execution_id": "EXEC-MIDDLE",
                "event_type": "LIVE_ORDER_SENT",
                "timestamp": "2026-08-15T12:00:03Z",
            }
        ],
        "broker": [
            {
                "exchange_order_id": "ORDER-MIDDLE",
                "fill_id": "FILL-MIDDLE",
                "event_type": "BROKER_ACK",
                "timestamp": "2026-08-15T12:00:04Z",
            }
        ],
        "shadow_runtime": [
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "SHADOW_VALIDATED",
                "timestamp": "2026-08-15T12:00:04.500Z",
            }
        ],
        "telegram": [
            {
                "trade_uuid": TRADE_UUID,
                "event_type": "TELEGRAM_SENT",
                "timestamp": "2026-08-15T12:00:07Z",
            }
        ],
        "falcon": [],
        "external_exposure": [],
    }


def _fixture(tmp_path: Path, *, foreign_only: bool = False):
    history = tmp_path / "history_manager.jsonl"
    timeline = tmp_path / "timeline.jsonl"
    if foreign_only:
        history_rows = [
            {
                "trade_id": "FOREIGN-HISTORY",
                "event_type": "SIGNAL",
                "timestamp": "2026-08-15T12:00:01Z",
            }
        ]
        timeline_rows = [
            {
                "trade_id": "FOREIGN-TIMELINE",
                "event_type": "POSITION_OPEN",
                "timestamp": "2026-08-15T12:00:05Z",
            }
        ]
    else:
        history_rows = [
            {
                "trade_id": "FOREIGN-HISTORY",
                "event_type": "SIGNAL",
                "timestamp": "2026-08-15T11:59:59Z",
            },
            {
                "trade_uuid": TRADE_UUID,
                "decision_id": "DECISION-HISTORY",
                "event_type": "RISK_APPROVED",
                "timestamp": "2026-08-15T12:00:01Z",
            },
        ]
        timeline_rows = [
            {
                "decision_id": "DECISION-HISTORY",
                "event_type": "EXECUTION_REQUESTED",
                "timestamp": "2026-08-15T12:00:02.500Z",
            },
            {
                "exchange_order_id": "ORDER-MIDDLE",
                "event_type": "POSITION_OPEN",
                "timestamp": "2026-08-15T12:00:05Z",
            },
            {
                "fill_ids": ["FILL-MIDDLE"],
                "event_type": "POSITION_OPEN",
                "timestamp": "2026-08-15T12:00:06Z",
            },
        ]
    _write(history, history_rows)
    _write(timeline, timeline_rows)
    history_index = _build(history, "history_manager")
    timeline_index = _build(timeline, "timeline")
    registry, context = _registry_envelope()
    return {
        "registry": registry,
        "context": context,
        "history": history,
        "timeline": timeline,
        "history_index": history_index,
        "timeline_index": timeline_index,
    }


def _run(data: Mapping[str, Any], **kwargs: Any):
    return run_full_response_shadow_v2(
        TRADE_ID,
        resolved_registry_envelope=data["registry"],
        static_sources=_static_sources(),
        history=IndexedJournalSpec(data["history"], data["history_index"]),
        timeline=IndexedJournalSpec(data["timeline"], data["timeline_index"]),
        now_epoch=NOW_EPOCH,
        **kwargs,
    )


def _normalized_validator(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop("generated_at", None)
    if isinstance(result.get("summary"), dict):
        result["summary"].pop("duration_ms", None)
    return result


def _normalized_snapshot(value: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop("generated_at", None)
    result.pop("duration_ms", None)
    return result


def test_full_bundle_validator_snapshot_and_public_payload_are_zero_tolerance(
    tmp_path: Path,
) -> None:
    data = _fixture(tmp_path)
    original_context = copy.deepcopy(data["context"])

    result = _run(data, measure_memory=True)

    assert result.report.status == MATCH, result.report.to_dict()
    assert all(result.report.parity.values())
    assert result.report.mismatch_categories == ()
    assert data["context"] == original_context
    assert result.legacy_bundle is not None
    assert result.hybrid_bundle is not None
    assert result.legacy_bundle.records == result.hybrid_bundle.records
    assert result.legacy_bundle.events == result.hybrid_bundle.events
    assert result.legacy_bundle.matched_identifiers == result.hybrid_bundle.matched_identifiers
    assert _normalized_validator(result.legacy_validator or {}) == _normalized_validator(
        result.hybrid_validator or {}
    )
    assert _normalized_snapshot(result.legacy_snapshot or {}) == _normalized_snapshot(
        result.hybrid_snapshot or {}
    )
    assert _normalized_validator(
        result.legacy_timeline_payload or {}
    ) == _normalized_validator(result.hybrid_timeline_payload or {})
    assert _normalized_snapshot(
        result.legacy_snapshot_payload or {}
    ) == _normalized_snapshot(result.hybrid_snapshot_payload or {})
    assert result.report.metrics.hybrid_journal_bytes <= 16 * 1024 * 1024
    assert result.report.metrics.total_journal_bytes == (
        result.report.metrics.legacy_journal_bytes
        + result.report.metrics.hybrid_journal_bytes
    )
    assert result.report.metrics.peak_tracemalloc_bytes is not None
    for source in ("history_manager", "timeline"):
        assert result.report.source_results[source][
            "evidence_completeness"
        ] == "POSITIVE_CERTIFIED_COMPLETE"
    assert set(result.report.to_dict()) == {
        "version",
        "status",
        "reason",
        "parity",
        "mismatch_categories",
        "source_results",
        "digests",
        "metrics",
        "normalized_fields",
    }


def test_real_order_preserves_history_then_intermediate_then_timeline_promotions(
    tmp_path: Path,
) -> None:
    data = _fixture(tmp_path)

    result = _run(data)

    assert result.report.status == MATCH
    assert result.hybrid_bundle is not None
    assert [
        row["event_type"] for row in result.hybrid_bundle.records["timeline"]
    ] == ["EXECUTION_REQUESTED", "POSITION_OPEN", "POSITION_OPEN"]
    context = result.hybrid_bundle.correlation
    assert "DECISION-HISTORY" in context.trusted["decision"]
    assert "ORDER-MIDDLE" in context.trusted["order"]
    assert "FILL-MIDDLE" in context.trusted["fill"]


def test_full_certified_zero_evidence_is_negative_certified(tmp_path: Path) -> None:
    data = _fixture(tmp_path, foreign_only=True)

    result = _run(data)

    assert result.report.status == MATCH, result.report.to_dict()
    for source in ("history_manager", "timeline"):
        source_result = result.report.source_results[source]
        assert source_result["completeness_status"] == "FULL_CERTIFIED"
        assert source_result["negative_status"] == "NEGATIVE_CERTIFIED"
        assert source_result["records"] == 0


def test_serving_table_tamper_never_builds_apparently_complete(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    with sqlite3.connect(data["history_index"]) as connection:
        identity = connection.execute(
            "SELECT identity_id FROM identities WHERE identity_type='trade_uuid' "
            "AND identity_value=?",
            (TRADE_UUID,),
        ).fetchone()
        assert identity is not None
        connection.execute("DELETE FROM postings WHERE identity_id=?", (identity[0],))

    result = _run(data)

    assert result.report.status in {FALLBACK_REQUIRED, NOT_COMPARABLE}
    assert "COMPLETENESS" in result.report.mismatch_categories or "INDEX_MUTATION" in result.report.mismatch_categories
    assert result.hybrid_bundle is None


@pytest.mark.parametrize(
    "stage",
    [
        "history_manager:after_session_open",
        "between_history_and_intermediates",
        "before_timeline",
        "after_timeline",
        "during_validator",
        "before_snapshot",
    ],
)
def test_source_mutation_at_full_pipeline_stages_is_not_comparable_and_atomic(
    tmp_path: Path,
    stage: str,
) -> None:
    data = _fixture(tmp_path)
    original_context = copy.deepcopy(data["context"])
    fired = False

    def inject(point: str, _detail: Mapping[str, Any]) -> None:
        nonlocal fired
        if point == stage and not fired:
            fired = True
            with data["history"].open("ab") as handle:
                handle.write(
                    _line(
                        {
                            "trade_uuid": TRADE_UUID,
                            "event_type": "LATE_MUTATION",
                        }
                    )
                )

    result = _run(data, fault_injector=inject)

    assert fired is True
    assert result.report.status == NOT_COMPARABLE, result.report.to_dict()
    assert "SOURCE_MUTATION" in result.report.mismatch_categories
    assert result.hybrid_bundle is None
    assert data["context"] == original_context


@pytest.mark.parametrize(
    ("mutation", "stage"),
    [
        ("append", "after_sessions_pinned"),
        ("truncate", "after_sessions_pinned"),
        ("truncate_regrow", "after_sessions_pinned"),
        ("replace", "after_legacy_bundle"),
        ("same_size_rewrite", "after_sessions_pinned"),
        ("rewrite_append", "after_sessions_pinned"),
    ],
)
def test_full_pipeline_source_mutation_matrix_discards_staged_result(
    tmp_path: Path,
    mutation: str,
    stage: str,
) -> None:
    data = _fixture(tmp_path)
    source = data["history"]
    original_bytes = source.read_bytes()
    original_stat = source.stat()
    original_context = copy.deepcopy(data["context"])
    replacement = tmp_path / "history-replacement.jsonl"
    replacement.write_bytes(
        original_bytes.replace(b"FOREIGN-HISTORY", b"CHANGED-HISTORY", 1)
    )
    fired = False

    def rewrite_bytes(payload: bytes) -> None:
        with source.open("r+b") as handle:
            handle.seek(0)
            handle.write(payload)
            handle.truncate(len(payload))

    def inject(point: str, _detail: Mapping[str, Any]) -> None:
        nonlocal fired
        if point != stage or fired:
            return
        fired = True
        if mutation == "append":
            with source.open("ab") as handle:
                handle.write(_line({"trade_uuid": TRADE_UUID, "event_type": "LATE"}))
        elif mutation == "truncate":
            with source.open("r+b") as handle:
                handle.truncate(max(1, len(original_bytes) // 2))
        elif mutation == "truncate_regrow":
            with source.open("r+b") as handle:
                handle.truncate(0)
                handle.write(original_bytes)
            os.utime(
                source,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 2_000_000_000),
            )
        elif mutation == "replace":
            os.replace(replacement, source)
        elif mutation == "same_size_rewrite":
            changed = original_bytes.replace(
                b"FOREIGN-HISTORY", b"CHANGED-HISTORY", 1
            )
            assert len(changed) == len(original_bytes) and changed != original_bytes
            rewrite_bytes(changed)
            os.utime(
                source,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 2_000_000_000),
            )
        elif mutation == "rewrite_append":
            changed = original_bytes.replace(
                b"FOREIGN-HISTORY", b"CHANGED-HISTORY", 1
            ) + _line({"trade_uuid": TRADE_UUID, "event_type": "LATE"})
            rewrite_bytes(changed)
        else:  # pragma: no cover - parametrization is closed above.
            raise AssertionError(f"unsupported mutation: {mutation}")

    result = _run(data, fault_injector=inject)

    assert fired is True
    assert result.report.status in {NOT_COMPARABLE, FALLBACK_REQUIRED}, (
        mutation,
        result.report.to_dict(),
    )
    assert "SOURCE_MUTATION" in result.report.mismatch_categories
    assert result.legacy_bundle is None
    assert result.hybrid_bundle is None
    assert data["context"] == original_context


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_unexpected_sqlite_sidecar_during_full_pipeline_is_not_comparable(
    tmp_path: Path,
    suffix: str,
) -> None:
    data = _fixture(tmp_path)
    original_context = copy.deepcopy(data["context"])
    sidecar = Path(f'{data["history_index"]}{suffix}')
    fired = False

    def inject(point: str, _detail: Mapping[str, Any]) -> None:
        nonlocal fired
        if point == "after_sessions_pinned" and not fired:
            fired = True
            sidecar.write_bytes(b"unexpected-c2-sidecar")

    result = _run(data, fault_injector=inject)

    assert fired is True
    assert result.report.status == NOT_COMPARABLE, result.report.to_dict()
    assert "INDEX_MUTATION" in result.report.mismatch_categories
    assert result.legacy_bundle is None
    assert result.hybrid_bundle is None
    assert data["context"] == original_context


@pytest.mark.parametrize(
    ("mutation", "statement", "parameters"),
    [
        (
            "certification_revoke",
            "UPDATE source_state SET certification_kind='UNCERTIFIED', "
            "serving_certification_kind='UNCERTIFIED' WHERE singleton_id=1",
            (),
        ),
        (
            "generation_change",
            "UPDATE source_state SET generation_uuid=? WHERE singleton_id=1",
            (str(uuid.UUID(int=0)),),
        ),
    ],
)
def test_index_certification_or_generation_change_during_full_pipeline_fails_closed(
    tmp_path: Path,
    mutation: str,
    statement: str,
    parameters: tuple[Any, ...],
) -> None:
    data = _fixture(tmp_path)
    original_context = copy.deepcopy(data["context"])
    fired = False

    def inject(point: str, _detail: Mapping[str, Any]) -> None:
        nonlocal fired
        if point == "after_legacy_bundle" and not fired:
            fired = True
            with sqlite3.connect(data["history_index"]) as connection:
                connection.execute(statement, parameters)

    result = _run(data, fault_injector=inject)

    assert fired is True
    assert result.report.status in {NOT_COMPARABLE, FALLBACK_REQUIRED}, (
        mutation,
        result.report.to_dict(),
    )
    assert set(result.report.mismatch_categories) & {
        "INDEX_MUTATION",
        "COMPLETENESS",
    }
    assert result.legacy_bundle is None
    assert result.hybrid_bundle is None
    assert data["context"] == original_context


def test_every_full_pipeline_fault_point_preserves_official_context_integrally(
    tmp_path: Path,
) -> None:
    data = _fixture(tmp_path)
    fault_points = (
        "before_legacy_bundle",
        "after_legacy_bundle",
        "after_sessions_pinned",
        "history_manager:after_session_open",
        "history_manager:after_replay_boundary",
        "history_manager:after_indexed_prefix",
        "history_manager:before_final_check",
        "between_history_and_intermediates",
        "before_timeline",
        "timeline:after_session_open",
        "timeline:after_replay_boundary",
        "timeline:after_indexed_prefix",
        "timeline:before_final_check",
        "after_timeline",
        "during_validator",
        "before_snapshot",
        "after_snapshot",
    )

    for expected_point in fault_points:
        original_context = copy.deepcopy(data["context"])
        fired: list[str] = []

        def inject(point: str, _detail: Mapping[str, Any]) -> None:
            if point == expected_point:
                fired.append(point)
                raise RuntimeError(f"injected full-pipeline fault: {point}")

        result = _run(data, fault_injector=inject)

        assert fired == [expected_point], expected_point
        assert result.report.status in {NOT_COMPARABLE, FALLBACK_REQUIRED}, (
            expected_point,
            result.report.to_dict(),
        )
        assert result.legacy_bundle is None, expected_point
        assert result.hybrid_bundle is None, expected_point
        assert data["context"] == original_context, expected_point


def test_failure_report_preserves_partial_legacy_and_index_io_metrics(
    tmp_path: Path,
) -> None:
    data = _fixture(tmp_path)

    def inject(point: str, _detail: Mapping[str, Any]) -> None:
        if point == "between_history_and_intermediates":
            raise RuntimeError("stop after indexed History")

    result = _run(data, fault_injector=inject)

    assert result.report.status in {FALLBACK_REQUIRED, NOT_COMPARABLE}, (
        result.report.to_dict()
    )
    assert result.report.metrics.legacy_journal_bytes > 0
    assert result.report.metrics.hybrid_journal_bytes > 0
    assert result.report.metrics.total_journal_bytes == (
        result.report.metrics.legacy_journal_bytes
        + result.report.metrics.hybrid_journal_bytes
    )
    assert result.report.metrics.total_sqlite_rows > 0
    assert result.report.metrics.total_duration_ms > 0


def test_v1_indexes_are_rejected_without_touching_legacy_result(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    v1 = tmp_path / "history-v1.sqlite3"
    report = index_module.build_index(
        data["history"],
        v1,
        "history_manager",
        config=_config(),
        measure_memory=False,
    )
    assert report.published is True
    data = {**data, "history_index": v1}
    original_context = copy.deepcopy(data["context"])

    result = _run(data)

    assert result.report.status in {FALLBACK_REQUIRED, NOT_COMPARABLE}
    assert result.hybrid_bundle is None
    assert data["context"] == original_context


def test_incomplete_static_source_set_is_not_comparable(tmp_path: Path) -> None:
    data = _fixture(tmp_path)

    result = run_full_response_shadow_v2(
        TRADE_ID,
        resolved_registry_envelope=data["registry"],
        static_sources={},
        history=IndexedJournalSpec(data["history"], data["history_index"]),
        timeline=IndexedJournalSpec(data["timeline"], data["timeline_index"]),
        now_epoch=NOW_EPOCH,
    )

    assert result.report.status == NOT_COMPARABLE
    assert result.report.reason == "STATIC_SOURCE_SET_INCOMPLETE"
    assert result.hybrid_bundle is None


def test_registry_and_static_input_caps_fail_before_clone_or_reader(
    tmp_path: Path,
) -> None:
    data = _fixture(tmp_path)
    huge_registry = {**data["registry"], "padding": "X" * 256}

    result = run_full_response_shadow_v2(
        TRADE_ID,
        resolved_registry_envelope=huge_registry,
        static_sources=_static_sources(),
        history=IndexedJournalSpec(data["history"], data["history_index"]),
        timeline=IndexedJournalSpec(data["timeline"], data["timeline_index"]),
        now_epoch=NOW_EPOCH,
        full_caps=FullShadowCaps(max_static_source_bytes=128),
    )

    assert result.report.status == FALLBACK_REQUIRED
    assert result.report.reason == "STATIC_SOURCE_BYTE_CAP_EXCEEDED"
    assert result.legacy_bundle is None
    assert result.hybrid_bundle is None


def test_source_journal_cap_is_fallback_not_source_mutation(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    tiny_history_caps = EnvelopeCaps(max_source_journal_bytes=1)

    result = run_full_response_shadow_v2(
        TRADE_ID,
        resolved_registry_envelope=data["registry"],
        static_sources=_static_sources(),
        history=IndexedJournalSpec(
            data["history"], data["history_index"], caps=tiny_history_caps
        ),
        timeline=IndexedJournalSpec(data["timeline"], data["timeline_index"]),
        now_epoch=NOW_EPOCH,
    )

    assert result.report.status == FALLBACK_REQUIRED, result.report.to_dict()
    assert "CAP" in str(result.report.reason)
    assert result.report.mismatch_categories == ("COMPLETENESS",)
    assert result.legacy_bundle is None
    assert result.hybrid_bundle is None


def test_snapshot_bundle_seam_does_not_reinvoke_sources(tmp_path: Path) -> None:
    import live_trade_snapshot

    data = _fixture(tmp_path)
    result = _run(data)
    assert result.report.status == MATCH
    assert result.hybrid_bundle is not None

    def forbidden(_trade_id: str) -> None:
        raise AssertionError("snapshot tried to re-read a source")

    rebuilt = live_trade_snapshot.build_live_trade_snapshot(
        TRADE_ID,
        sources={"registry": forbidden},
        evidence_bundle=result.hybrid_bundle,
        now_epoch=NOW_EPOCH,
    )

    assert _normalized_snapshot(rebuilt) == _normalized_snapshot(
        result.hybrid_snapshot or {}
    )


def _compile_main_route(function_name: str, args: Mapping[str, Any]):
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    node = copy.deepcopy(node)
    node.decorator_list = []
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    namespace = {
        "request": SimpleNamespace(args=dict(args)),
        "app": SimpleNamespace(logger=SimpleNamespace(exception=lambda *_a, **_k: None)),
        "datetime": datetime.datetime,
        "timezone": datetime.timezone,
    }
    exec(compile(isolated, f"<{function_name}>", "exec"), namespace)
    return namespace[function_name]


def test_public_payload_helpers_match_ast_isolated_http_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _fixture(tmp_path)
    result = _run(data)
    assert result.report.status == MATCH
    assert result.hybrid_validator is not None
    assert result.hybrid_snapshot is not None

    timeline_calls: list[str] = []

    def validate(trade_id: str, **_kwargs: Any):
        timeline_calls.append(trade_id)
        return copy.deepcopy(result.hybrid_validator)

    monkeypatch.setitem(
        sys.modules,
        "trade_timeline_validator",
        SimpleNamespace(validate_trade_timeline=validate),
    )
    timeline_route = _compile_main_route(
        "trade_timeline_validator_v1_route", {"trade_id": TRADE_ID}
    )
    timeline_route_payload, timeline_status = timeline_route()
    assert timeline_status == 200
    assert timeline_route_payload == timeline_public_payload(
        result.hybrid_validator, TRADE_ID
    )
    assert timeline_calls == [TRADE_ID]

    snapshot_calls: list[str] = []

    def snapshot(trade_id: str, **_kwargs: Any):
        snapshot_calls.append(trade_id)
        return copy.deepcopy(result.hybrid_snapshot)

    monkeypatch.setitem(
        sys.modules,
        "live_trade_snapshot",
        SimpleNamespace(build_live_trade_snapshot=snapshot),
    )
    snapshot_route = _compile_main_route(
        "live_trade_snapshot_v1_route", {"trade_id": TRADE_ID}
    )
    snapshot_route_payload, snapshot_status = snapshot_route()
    assert snapshot_status == 200
    assert snapshot_route_payload == snapshot_public_payload(
        result.hybrid_snapshot, TRADE_ID
    )
    assert snapshot_calls == [TRADE_ID]


def test_full_metrics_include_final_digest_time_and_peak_allocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _fixture(tmp_path)
    original_digest = full_shadow_module._digest
    digest_calls = 0
    last_digest_finished = 0.0

    def measured_digest(value: Any) -> str:
        nonlocal digest_calls, last_digest_finished
        digest_calls += 1
        scratch = bytearray(8 * 1024 * 1024)
        scratch[-1] = 1
        time.sleep(0.002)
        result = original_digest(value)
        assert scratch[-1] == 1
        last_digest_finished = time.perf_counter()
        return result

    monkeypatch.setattr(full_shadow_module, "_digest", measured_digest)
    external_started = time.perf_counter()
    result = _run(data, measure_memory=True)

    assert result.report.status == MATCH, result.report.to_dict()
    assert digest_calls == 10
    assert result.report.metrics.total_duration_ms + 5.0 >= (
        last_digest_finished - external_started
    ) * 1000.0
    assert result.report.metrics.peak_tracemalloc_bytes is not None
    assert result.report.metrics.peak_tracemalloc_bytes >= 8 * 1024 * 1024


def test_c2_module_has_no_productive_caller() -> None:
    module_name = "trade_evidence_identity_offset_full_shadow_v2"
    root = Path(__file__).resolve().parents[1]
    forbidden = (
        "main.py",
        "trade_timeline_validator.py",
        "live_trade_snapshot.py",
        "trade_evidence_identity_offset_shadow_compare_v1.py",
        "trade_evidence_identity_offset_maintenance_v1.py",
    )
    for name in forbidden:
        assert module_name not in (root / name).read_text(encoding="utf-8")
