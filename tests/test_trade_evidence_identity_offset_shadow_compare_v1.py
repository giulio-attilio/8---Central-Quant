from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

import trade_evidence_identity_offset_index_v1 as index_v1
import trade_evidence_identity_offset_shadow_compare_v1 as shadow_v1
import trade_timeline_validator as validator


TRADE_ID = "SHADOW-TRADE-1"
TRADE_UUID = "UUID-SHADOW-1"
OPENED_AT = "2026-08-14T12:00:00Z"

_SHADOW_ENV = (
    "TRADE_EVIDENCE_INDEX_SHADOW_ENABLED",
    "TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED",
    "TRADE_EVIDENCE_INDEX_HISTORY_PATH",
    "TRADE_EVIDENCE_INDEX_TIMELINE_PATH",
    "TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED",
    "TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE",
    "TRADE_EVIDENCE_INDEX_SHADOW_MAX_JOURNAL_BYTES",
    "TRADE_EVIDENCE_INDEX_SHADOW_BUSY_TIMEOUT_MS",
)


def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("network access is forbidden in Phase B shadow tests")


@pytest.fixture(autouse=True)
def _safe_process(monkeypatch: pytest.MonkeyPatch):
    for name in _SHADOW_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    monkeypatch.setattr(socket.socket, "connect", _deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny_network)
    shadow_v1.reset_shadow_telemetry()
    yield
    shadow_v1.reset_shadow_telemetry()


@dataclass(frozen=True)
class LocalCase:
    root: Path
    history: Path
    timeline: Path
    history_index: Path
    timeline_index: Path
    trade_id: str


def _registry_row(
    *,
    trade_id: str = TRADE_ID,
    trade_uuid: str = TRADE_UUID,
    opened_at: str = OPENED_AT,
    **updates: Any,
) -> dict[str, Any]:
    row = {
        "trade_id": trade_id,
        "trade_uuid": trade_uuid,
        "registry_id": f"REG-{trade_uuid}",
        "lifecycle_id": f"LIFE-{trade_uuid}",
        "status": "OPEN",
        "opened_at": opened_at,
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
    }
    row.update(updates)
    return row


def _event(
    event_type: str,
    second: int,
    *,
    trade_id: str = TRADE_ID,
    trade_uuid: str = TRADE_UUID,
    event_id: str | None = None,
    **updates: Any,
) -> dict[str, Any]:
    row = {
        "trade_id": trade_id,
        "trade_uuid": trade_uuid,
        "event_type": event_type,
        "event_id": event_id or f"{event_type}-{second}",
        "timestamp": f"2026-08-14T12:00:{second:02d}Z",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "mode": "LIVE",
    }
    row.update(updates)
    return row


def _encoded_line(row: Mapping[str, Any], *, newline: bool = True) -> bytes:
    payload = json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def _write_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any] | bytes],
    *,
    final_newline: bool = True,
) -> None:
    payload = bytearray()
    for position, row in enumerate(rows):
        raw = bytes(row) if isinstance(row, bytes) else _encoded_line(row, newline=False)
        payload.extend(raw)
        if final_newline or position < len(rows) - 1:
            payload.extend(b"\n")
    path.write_bytes(bytes(payload))


def _build_index(source: Path, index: Path, source_id: str) -> None:
    report = index_v1.build_index(
        source,
        index,
        source_id,
        config=index_v1.BuildConfig(
            block_bytes=64,
            segment_target_bytes=256,
            batch_bytes=1024,
            batch_lines=4,
            max_line_bytes=validator.JSONL_MAX_BYTES,
            anchor_bytes=16,
            busy_timeout_ms=25,
        ),
    )
    assert report.published is True
    assert report.state == "READY"


def _enable_shadow(monkeypatch: pytest.MonkeyPatch, case: LocalCase) -> None:
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(case.root))
    monkeypatch.setenv("TRADE_LIFECYCLE_SHADOW_DATA_DIR", str(case.root))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "true")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "true")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_HISTORY_PATH", str(case.history_index))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_TIMELINE_PATH", str(case.timeline_index))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_LOG_ENABLED", "false")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE", "1")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_BUSY_TIMEOUT_MS", "25")


def _prepare_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    trade_id: str = TRADE_ID,
    registry_payload: Mapping[str, Any] | None = None,
    history_rows: Sequence[Mapping[str, Any] | bytes] | None = None,
    timeline_rows: Sequence[Mapping[str, Any] | bytes] | None = None,
    build_history: bool = True,
    build_timeline: bool = True,
) -> LocalCase:
    root = tmp_path / "data"
    root.mkdir()
    history = root / "history_events.jsonl"
    timeline = root / "timeline.jsonl"
    history_index = root / "history_events.jsonl.identity-offset-v1.sqlite3"
    timeline_index = root / "timeline.jsonl.identity-offset-v1.sqlite3"
    registry = registry_payload or _registry_row(trade_id=trade_id)
    (root / "trade_registry.json").write_text(
        json.dumps(registry, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    _write_jsonl(
        history,
        history_rows
        if history_rows is not None
        else [_event("SIGNAL_RECEIVED", 1, trade_id=trade_id, event_id="H-1")],
    )
    _write_jsonl(
        timeline,
        timeline_rows
        if timeline_rows is not None
        else [_event("POSITION_OPEN", 2, trade_id=trade_id, event_id="T-1")],
    )
    if build_history:
        _build_index(history, history_index, "history_manager")
    if build_timeline:
        _build_index(timeline, timeline_index, "timeline")
    case = LocalCase(
        root=root,
        history=history,
        timeline=timeline,
        history_index=history_index,
        timeline_index=timeline_index,
        trade_id=trade_id,
    )
    _enable_shadow(monkeypatch, case)
    return case


def _collect(
    case: LocalCase,
    *,
    opened_at: str | None = None,
) -> validator.EvidenceBundle:
    return validator.collect_evidence_bundle(case.trade_id, opened_at=opened_at)


def _observe(
    bundle: validator.EvidenceBundle,
    *,
    config: shadow_v1.ShadowConfig | None = None,
) -> shadow_v1.ShadowCompareReport:
    # Collection invokes the observer automatically. Resetting here makes
    # assertions below describe exactly the explicit observation under test.
    shadow_v1.reset_shadow_telemetry()
    return shadow_v1.observe_evidence_bundle(bundle, config=config)


def _normalized_report(report: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(report))
    value.pop("generated_at", None)
    summary = value.get("summary")
    if isinstance(summary, dict):
        summary.pop("duration_ms", None)
    return value


def _execute(connection_path: Path, sql: str, parameters: Sequence[Any] = ()) -> None:
    with sqlite3.connect(connection_path) as connection:
        connection.execute(sql, tuple(parameters))


def _replace_bytes_same_length(path: Path, old: bytes, new: bytes) -> None:
    assert len(old) == len(new)
    payload = path.read_bytes()
    assert payload.count(old) == 1
    path.write_bytes(payload.replace(old, new, 1))


def _refresh_record_hash(index: Path, source: Path, event_type: str) -> None:
    with sqlite3.connect(index) as connection:
        row = connection.execute(
            "SELECT record_id, start_offset, byte_length FROM records WHERE event_type=?",
            (event_type,),
        ).fetchone()
        assert row is not None
        record_id, start, length = map(int, row)
        raw = source.read_bytes()[start : start + length]
        assert len(raw) == length
        digest = hashlib.blake2b(raw, digest_size=16).digest()
        connection.execute(
            "UPDATE records SET record_hash=? WHERE record_id=?",
            (digest, record_id),
        )


def test_config_is_default_off_missing_safe_and_dynamically_parsed(monkeypatch):
    config = shadow_v1.ShadowConfig.from_environ({})
    assert config.enabled is False
    assert config.compare_enabled is False
    assert config.active is False
    assert config.history_index_path is None
    assert config.timeline_index_path is None
    assert shadow_v1.shadow_capture_enabled({}) is False

    environ = {
        "TRADE_EVIDENCE_INDEX_SHADOW_ENABLED": " TRUE ",
        "TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED": "yes",
        "TRADE_EVIDENCE_INDEX_SHADOW_SAMPLE_RATE": "invalid",
        "TRADE_EVIDENCE_INDEX_SHADOW_MAX_JOURNAL_BYTES": "-1",
    }
    config = shadow_v1.ShadowConfig.from_environ(environ)
    assert config.active is True
    assert config.sample_rate == 0.0
    assert config.max_journal_bytes == shadow_v1.DEFAULT_MAX_JOURNAL_BYTES
    assert shadow_v1.shadow_capture_enabled(environ) is True

    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "unexpected")
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", "true")
    assert shadow_v1.shadow_capture_enabled() is False


def test_shadow_disabled_does_not_open_sqlite(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "false")
    bundle = validator.collect_evidence_bundle(case.trade_id)

    monkeypatch.setattr(
        shadow_v1._PinnedReadSession,
        "__enter__",
        lambda self: (_ for _ in ()).throw(AssertionError("index opened")),
    )
    result = shadow_v1.observe_evidence_bundle(bundle)

    assert result.status == shadow_v1.SHADOW_DISABLED
    assert all(item.status == shadow_v1.SHADOW_DISABLED for item in result.sources.values())


def test_missing_index_is_informational_and_never_created(tmp_path, monkeypatch):
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        build_history=False,
        build_timeline=False,
    )
    bundle = _collect(case)
    result = _observe(bundle)

    assert result.status == shadow_v1.INDEX_UNAVAILABLE
    assert result.sources["history_manager"].index_status == index_v1.INDEX_MISSING
    assert result.sources["timeline"].index_status == index_v1.INDEX_MISSING
    assert not case.history_index.exists()
    assert not case.timeline_index.exists()


def test_ready_indexes_match_read_only_and_leave_no_sqlite_sidecars(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    before = {
        path: path.read_bytes()
        for path in (case.history, case.timeline, case.history_index, case.timeline_index)
    }

    result = _observe(bundle)

    assert result.status == shadow_v1.MATCH
    for source in shadow_v1.SHADOW_SOURCES:
        comparison = result.sources[source]
        assert comparison.status == shadow_v1.MATCH
        assert comparison.semantic_parity == shadow_v1.SEMANTIC_PARITY
        assert comparison.mode == "INDEX_ONLY"
        assert comparison.metrics.factual_records == comparison.legacy_count
        assert comparison.metrics.total_journal_bytes <= shadow_v1.DEFAULT_MAX_JOURNAL_BYTES
    assert {path: path.read_bytes() for path in before} == before
    assert not any(
        Path(os.fspath(index) + suffix).exists()
        for index in (case.history_index, case.timeline_index)
        for suffix in ("-wal", "-shm", "-journal")
    )


def test_deleted_posting_is_reported_as_missing_index_record(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    _execute(
        case.history_index,
        "DELETE FROM postings WHERE record_id IN (SELECT record_id FROM records WHERE event_type='SIGNAL_RECEIVED')",
    )
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MISMATCH
    assert shadow_v1.MISSING_INDEX_RECORD in history.mismatch_categories
    assert history.legacy_count == 1
    assert history.shadow_count == 0


def test_wrong_index_offset_is_isolated_and_categorized(tmp_path, monkeypatch):
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        history_rows=[
            _event("NOISE", 1, trade_id="OTHER-A", trade_uuid="OTHER-UUID-A"),
            _event("SIGNAL_RECEIVED", 2, event_id="H-OFFSET"),
            _event("NOISE", 3, trade_id="OTHER-B", trade_uuid="OTHER-UUID-B"),
        ],
    )
    with sqlite3.connect(case.history_index) as connection:
        record_id, start = connection.execute(
            "SELECT record_id, start_offset FROM records WHERE event_type='SIGNAL_RECEIVED'"
        ).fetchone()
        connection.execute(
            "UPDATE postings SET start_offset=? WHERE record_id=?",
            (int(start) + 1, int(record_id)),
        )
        connection.execute(
            "UPDATE records SET start_offset=? WHERE record_id=?",
            (int(start) + 1, int(record_id)),
        )
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MISMATCH
    assert shadow_v1.OFFSET_MISMATCH in history.mismatch_categories


def test_middle_source_mutation_is_record_hash_mismatch_not_authoritative(tmp_path, monkeypatch):
    target = _event("SIGNAL_RECEIVED", 2, event_id="H-TARGET")
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        history_rows=[
            _event("NOISE", 1, trade_id="OTHER-A", trade_uuid="OTHER-UUID-A", padding="x" * 80),
            target,
            _event("NOISE", 3, trade_id="OTHER-B", trade_uuid="OTHER-UUID-B", padding="y" * 80),
        ],
    )
    _replace_bytes_same_length(case.history, b'H-TARGET', b'H-TARGEX')
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MISMATCH
    assert shadow_v1.RECORD_HASH_MISMATCH in history.mismatch_categories


def test_factual_identity_taxonomy_mismatch_is_explicit(tmp_path, monkeypatch):
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        history_rows=[
            _event("NOISE", 1, trade_id="OTHER-A", trade_uuid="OTHER-UUID-A", padding="x" * 80),
            _event("SIGNAL_RECEIVED", 2, event_id="H-IDENTITY"),
            _event("NOISE", 3, trade_id="OTHER-B", trade_uuid="OTHER-UUID-B", padding="y" * 80),
        ],
    )
    _replace_bytes_same_length(case.history, b'SHADOW-TRADE-1', b'SHADOW-TRADE-X')
    _refresh_record_hash(case.history_index, case.history, "SIGNAL_RECEIVED")
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MISMATCH
    assert shadow_v1.IDENTITY_MISMATCH in history.mismatch_categories


def test_factual_event_metadata_mismatch_is_explicit(tmp_path, monkeypatch):
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        history_rows=[
            _event("NOISE", 1, trade_id="OTHER-A", trade_uuid="OTHER-UUID-A", padding="x" * 80),
            _event("CUSTOM_EVENT_A", 2, event_id="H-EVENT"),
            _event("NOISE", 3, trade_id="OTHER-B", trade_uuid="OTHER-UUID-B", padding="y" * 80),
        ],
    )
    _replace_bytes_same_length(case.history, b'CUSTOM_EVENT_A', b'CUSTOM_EVENT_B')
    _refresh_record_hash(case.history_index, case.history, "CUSTOM_EVENT_A")
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MISMATCH
    assert shadow_v1.EVENT_MISMATCH in history.mismatch_categories


@pytest.mark.parametrize(
    "legacy,shadow,expected",
    [
        ([_event("POSITION_OPEN", 1)], [], shadow_v1.MISSING_INDEX_RECORD),
        ([], [_event("POSITION_OPEN", 1)], shadow_v1.EXTRA_INDEX_RECORD),
        (
            [_event("POSITION_OPEN", 1), _event("BROKER_ACK", 2)],
            [_event("BROKER_ACK", 2), _event("POSITION_OPEN", 1)],
            shadow_v1.ORDER_MISMATCH,
        ),
    ],
)
def test_semantic_row_comparison_classifies_missing_extra_and_order(legacy, shadow, expected):
    categories = shadow_v1.compare_source_semantics("timeline", legacy, shadow)
    assert expected in categories


def test_semantic_comparison_detects_duplicate_and_chronology_mismatch():
    first = _event("POSITION_OPEN", 10, event_id="OPEN-A")
    second = _event("POSITION_OPEN", 11, event_id="OPEN-B")
    close = _event("LIVE_TRADE_CLOSED", 5, event_id="CLOSE-EARLY")

    duplicate_categories = shadow_v1.compare_source_semantics(
        "timeline",
        [first, second],
        [first],
    )
    chronology_categories = shadow_v1.compare_source_semantics(
        "timeline",
        [first, close],
        [first],
    )

    assert shadow_v1.DUPLICATE_MISMATCH in duplicate_categories
    assert shadow_v1.CHRONOLOGY_MISMATCH in chronology_categories


def test_conflicting_source_rows_receive_conflict_category():
    first = _event("POSITION_OPEN", 1, event_id="OPEN-A", quantity=1.0)
    second = _event("POSITION_OPEN", 2, event_id="OPEN-B", quantity=2.0)
    legacy = [first, second]
    indexed = [first]
    categories = shadow_v1.compare_source_semantics("timeline", legacy, indexed)
    assert shadow_v1.CONFLICT_MISMATCH in categories


def test_context_divergence_is_promotion_mismatch():
    legacy_context = validator.new_correlation_context(TRADE_ID)
    indexed_context = copy.deepcopy(legacy_context)
    indexed_context.trusted.setdefault("decision", set()).add("DECISION-NEW")
    indexed_context.trusted_typed.setdefault("decision_id", set()).add("DECISION-NEW")

    categories = shadow_v1.compare_source_semantics(
        "history_manager",
        [],
        [],
        legacy_context=legacy_context,
        shadow_context=indexed_context,
    )

    assert shadow_v1.PROMOTION_MISMATCH in categories


def test_reusable_turtle_is_not_comparable_until_opened_at_resolves_instance(tmp_path, monkeypatch):
    trade_id = "TURTLE:T20:BTCUSDT:LONG"
    first = _registry_row(
        trade_id=trade_id,
        trade_uuid="UUID-TURTLE-A",
        opened_at="2026-08-14T10:00:00Z",
        bot="TURTLE",
        trade_id_reusable=True,
    )
    second = _registry_row(
        trade_id=trade_id,
        trade_uuid="UUID-TURTLE-B",
        opened_at="2026-08-14T11:00:00Z",
        bot="TURTLE",
        trade_id_reusable=True,
    )
    registry = {"open_trades": {"A": first, "B": second}, "closed_trades": []}
    rows = [
        _event(
            "POSITION_OPEN",
            1,
            trade_id=trade_id,
            trade_uuid="UUID-TURTLE-A",
            bot="TURTLE",
        )
    ]
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        trade_id=trade_id,
        registry_payload=registry,
        history_rows=rows,
        timeline_rows=rows,
    )

    ambiguous_bundle = _collect(case)
    ambiguous = _observe(ambiguous_bundle)
    assert all(
        result.index_status == "IDENTITY_AMBIGUOUS"
        and result.status == shadow_v1.NOT_COMPARABLE
        for result in ambiguous.sources.values()
    )

    resolved_bundle = _collect(case, opened_at="2026-08-14T10:00:00Z")
    resolved = _observe(resolved_bundle)
    assert resolved.status == shadow_v1.MATCH


def test_strong_identity_and_secondary_chain_promote_only_forward(tmp_path, monkeypatch):
    history_rows = [
        _event("SIGNAL_RECEIVED", 1, trade_uuid=TRADE_UUID, trade_id="", event_id="STRONG"),
        {
            "trade_id": TRADE_ID,
            "decision_id": "DEC-1",
            "event_type": "RISK_APPROVED",
            "timestamp": "2026-08-14T12:00:02Z",
        },
        {
            "decision_id": "DEC-1",
            "execution_id": "EXEC-1",
            "event_type": "EXECUTION_REQUESTED",
            "timestamp": "2026-08-14T12:00:03Z",
        },
        {
            "execution_id": "EXEC-1",
            "signal_id": "SIG-1",
            "event_type": "LIVE_ORDER_SENT",
            "timestamp": "2026-08-14T12:00:04Z",
        },
    ]
    case = _prepare_case(tmp_path, monkeypatch, history_rows=history_rows)
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MATCH
    assert history.legacy_count == history.shadow_count == 4
    assert "EXEC-1" in history.shadow_context.trusted["execution"]
    assert "SIG-1" in history.shadow_context.trusted["signal"]


def test_sqlite_busy_and_corrupt_database_are_fail_safe(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    original_connect = shadow_v1.sqlite3.connect

    def busy(*_args: Any, **_kwargs: Any):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(shadow_v1.sqlite3, "connect", busy)
    busy_result = _observe(bundle)
    assert busy_result.status == shadow_v1.INDEX_UNAVAILABLE
    assert all(item.reasons == ("SQLITE_BUSY",) for item in busy_result.sources.values())

    monkeypatch.setattr(shadow_v1.sqlite3, "connect", original_connect)
    case.history_index.write_bytes(b"not-a-sqlite-index\x00")
    corrupt_result = _observe(bundle)
    assert corrupt_result.sources["history_manager"].status == shadow_v1.INDEX_UNAVAILABLE
    assert corrupt_result.sources["history_manager"].index_status == index_v1.INDEX_CORRUPT


@pytest.mark.parametrize(
    "column,value,reason",
    [
        ("index_version", "OLD-INDEX", "INDEX_VERSION_MISMATCH"),
        ("identity_contract_hash", "OLD-CONTRACT", "IDENTITY_CONTRACT_MISMATCH"),
    ],
)
def test_stale_version_and_identity_contract_are_informational(
    tmp_path,
    monkeypatch,
    column,
    value,
    reason,
):
    case = _prepare_case(tmp_path, monkeypatch)
    _execute(case.history_index, f"UPDATE source_state SET {column}=?", (value,))
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.INDEX_UNAVAILABLE
    assert history.index_status == index_v1.INDEX_STALE
    assert history.reasons == (reason,)


@pytest.mark.parametrize(
    "sql,parameters,reason",
    [
        (
            "UPDATE source_state SET generation_uuid=?",
            ("not-a-generation-uuid",),
            "GENERATION_UUID_INVALID",
        ),
        (
            """
            UPDATE source_state
            SET watermark_anchor_length=0,
                watermark_anchor_offset=safe_watermark
            """,
            (),
            "ANCHOR_SHAPE_INVALID",
        ),
    ],
)
def test_invalid_generation_and_anchor_shapes_are_rejected_before_lookup(
    tmp_path,
    monkeypatch,
    sql,
    parameters,
    reason,
):
    case = _prepare_case(tmp_path, monkeypatch)
    _execute(case.history_index, sql, parameters)
    bundle = _collect(case)
    result = _observe(bundle)

    history = result.sources["history_manager"]
    assert history.status == shadow_v1.INDEX_UNAVAILABLE
    assert history.index_status == index_v1.INDEX_CORRUPT
    assert history.reasons == (reason,)
    assert history.metrics.factual_journal_bytes == 0


def test_wrong_source_index_and_source_inode_replacement_are_rejected(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)

    wrong_config = replace(
        shadow_v1.ShadowConfig.from_environ(),
        history_index_path=case.timeline_index,
    )
    wrong = _observe(bundle, config=wrong_config)
    assert wrong.sources["history_manager"].index_status == index_v1.INDEX_SOURCE_CHANGED

    replacement = case.history.with_suffix(".replacement")
    replacement.write_bytes(case.history.read_bytes())
    os.replace(replacement, case.history)
    replaced = _observe(bundle)
    assert replaced.sources["history_manager"].status == shadow_v1.NOT_COMPARABLE
    assert replaced.sources["history_manager"].index_status == index_v1.INDEX_SOURCE_CHANGED


@pytest.mark.parametrize("terminal_newline", [True, False])
def test_safe_watermark_behind_eof_combines_index_and_tail(
    tmp_path,
    monkeypatch,
    terminal_newline,
):
    case = _prepare_case(tmp_path, monkeypatch)
    appended = _event("RISK_APPROVED", 3, event_id="H-TAIL")
    with case.history.open("ab") as handle:
        handle.write(_encoded_line(appended, newline=terminal_newline))

    bundle = _collect(case)
    result = _observe(bundle)
    history = result.sources["history_manager"]

    assert history.status == shadow_v1.MATCH
    assert history.mode == "INDEX_PLUS_TAIL"
    assert history.index_status == index_v1.INDEX_PARTIAL
    assert history.legacy_count == history.shadow_count == 2
    assert history.metrics.tail_journal_bytes > 0


def test_append_after_legacy_snapshot_does_not_enter_shadow_window(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    with case.history.open("ab") as handle:
        handle.write(_encoded_line(_event("NOISE", 9, trade_id="OTHER", trade_uuid="OTHER-UUID")))

    result = _observe(bundle)
    history = result.sources["history_manager"]
    assert history.status == shadow_v1.MATCH
    assert history.mode == "INDEX_ONLY"
    assert history.shadow_count == history.legacy_count == 1


def test_oversized_barrier_marks_fallback_required_without_full_scan(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    _execute(
        case.history_index,
        """
        UPDATE segments
        SET has_oversized_barrier=1,
            oversized_barrier_lines=1,
            physical_lines=physical_lines+1
        """,
    )
    bundle = _collect(case)
    result = _observe(bundle)
    history = result.sources["history_manager"]

    assert history.status == shadow_v1.NOT_COMPARABLE
    assert history.index_status == index_v1.INDEX_PARTIAL
    assert history.mode == "FALLBACK_REQUIRED"
    assert history.reasons == ("OVERSIZED_BARRIER",)
    assert history.metrics.factual_journal_bytes == 0


def test_sample_rate_zero_one_and_stable_hash_sampling(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    base = shadow_v1.ShadowConfig.from_environ()

    skipped = _observe(bundle, config=replace(base, sample_rate=0.0))
    selected = _observe(bundle, config=replace(base, sample_rate=1.0))
    context = bundle.raw_sources["history_manager"]["_shadow_index_capture"]["context_before"]
    first = shadow_v1._sampled(case.trade_id, "history_manager", context, 0.37)
    second = shadow_v1._sampled(case.trade_id, "history_manager", context, 0.37)

    assert skipped.status == shadow_v1.SHADOW_DISABLED
    assert selected.status == shadow_v1.MATCH
    assert first is second


def test_mixed_source_sampling_is_not_reported_as_global_match(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    history_context = bundle.raw_sources["history_manager"]["_shadow_index_capture"][
        "context_before"
    ]
    timeline_context = bundle.raw_sources["timeline"]["_shadow_index_capture"][
        "context_before"
    ]
    sample_rate = next(
        rate
        for rate in (step / 10_000 for step in range(1, 10_000))
        if shadow_v1._sampled(case.trade_id, "history_manager", history_context, rate)
        != shadow_v1._sampled(case.trade_id, "timeline", timeline_context, rate)
    )

    result = _observe(
        bundle,
        config=replace(shadow_v1.ShadowConfig.from_environ(), sample_rate=sample_rate),
    )

    assert result.status == shadow_v1.NOT_COMPARABLE
    assert {item.status for item in result.sources.values()} == {
        shadow_v1.MATCH,
        shadow_v1.SHADOW_DISABLED,
    }


def test_journal_byte_guard_aborts_before_unbounded_factual_read(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    config = replace(shadow_v1.ShadowConfig.from_environ(), max_journal_bytes=1)
    result = _observe(bundle, config=config)

    assert result.status == shadow_v1.NOT_COMPARABLE
    for comparison in result.sources.values():
        assert comparison.mode == "FALLBACK_REQUIRED"
        assert comparison.reasons == ("SHADOW_JOURNAL_BYTE_GUARD",)
        assert comparison.metrics.total_journal_bytes <= 1


def test_shadow_runtime_and_telemetry_exceptions_never_escape(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)

    monkeypatch.setattr(
        shadow_v1,
        "_run_source_compare",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("shadow failure")),
    )
    isolated = _observe(bundle)
    assert isolated.status == shadow_v1.INDEX_UNAVAILABLE
    assert all(item.reasons == ("SHADOW_EXCEPTION_ISOLATED",) for item in isolated.sources.values())

    monkeypatch.setattr(
        shadow_v1,
        "_record_telemetry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("telemetry failure")),
    )
    still_isolated = shadow_v1.observe_evidence_bundle(bundle)
    assert still_isolated.status == shadow_v1.INDEX_UNAVAILABLE


def test_sqlite_busy_after_session_open_preserves_io_metrics_and_closes(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    original_close = shadow_v1._PinnedReadSession.close
    closed: list[bool] = []

    def busy_after_open(*_args: Any, **_kwargs: Any) -> Any:
        raise sqlite3.OperationalError("database is locked during lookup")

    def observed_close(session: shadow_v1._PinnedReadSession) -> None:
        original_close(session)
        closed.append(session.source_fd is None and session.connection is None)

    monkeypatch.setattr(shadow_v1._PinnedReadSession, "open_candidate_cursor", busy_after_open)
    monkeypatch.setattr(shadow_v1._PinnedReadSession, "close", observed_close)
    result = _observe(bundle)

    assert result.status == shadow_v1.INDEX_UNAVAILABLE
    assert all(item.reasons == ("SQLITE_BUSY",) for item in result.sources.values())
    assert all(item.metrics.anchor_journal_bytes > 0 for item in result.sources.values())
    assert all(item.metrics.total_journal_bytes > 0 for item in result.sources.values())
    assert closed == [True, True]


def test_broken_config_mapping_is_isolated_by_public_observer(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)

    class BrokenMapping(dict):
        def get(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("configuration unavailable")

    result = shadow_v1.observe_evidence_bundle(bundle, environ=BrokenMapping())
    assert result.status == shadow_v1.SHADOW_DISABLED
    assert all(item.reasons == ("SHADOW_DISABLED",) for item in result.sources.values())


def test_off_match_mismatch_and_exception_preserve_legacy_response(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)

    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "false")
    baseline = validator.validate_trade_timeline(case.trade_id)

    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "true")
    matching = validator.validate_trade_timeline(case.trade_id)

    _execute(
        case.history_index,
        "DELETE FROM postings WHERE record_id IN (SELECT record_id FROM records WHERE event_type='SIGNAL_RECEIVED')",
    )
    mismatching = validator.validate_trade_timeline(case.trade_id)

    monkeypatch.setattr(
        shadow_v1,
        "observe_evidence_bundle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("observer exploded")),
    )
    failed = validator.validate_trade_timeline(case.trade_id)

    expected = _normalized_report(baseline)
    assert _normalized_report(matching) == expected
    assert _normalized_report(mismatching) == expected
    assert _normalized_report(failed) == expected
    serialized = json.dumps(failed, sort_keys=True, default=str)
    assert "_shadow_index_capture" not in serialized
    assert "observer exploded" not in serialized


@pytest.mark.parametrize("failure_call", [1, 2])
def test_context_capture_deepcopy_failure_never_changes_official_response(
    tmp_path,
    monkeypatch,
    failure_call,
):
    case = _prepare_case(tmp_path, monkeypatch)
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "false")
    expected = _normalized_report(validator.validate_trade_timeline(case.trade_id))
    monkeypatch.setenv("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", "true")
    original_deepcopy = copy.deepcopy
    calls = 0

    def flaky_deepcopy(value: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise RuntimeError("private shadow capture failed")
        return original_deepcopy(value, *args, **kwargs)

    monkeypatch.setattr(validator.copy, "deepcopy", flaky_deepcopy)
    actual = validator.validate_trade_timeline(case.trade_id)
    monkeypatch.setattr(validator.copy, "deepcopy", original_deepcopy)

    assert calls >= failure_call
    assert _normalized_report(actual) == expected
    assert "_shadow_index_capture" not in json.dumps(actual, sort_keys=True, default=str)


def test_source_metadata_mismatch_is_local_and_does_not_pollute_other_source(
    tmp_path,
    monkeypatch,
):
    case = _prepare_case(
        tmp_path,
        monkeypatch,
        timeline_rows=[
            _event("NOISE", 1, trade_id="OTHER-A", trade_uuid="OTHER-UUID-A"),
            _event("POSITION_OPEN", 2, event_id="T-METADATA-OFFSET"),
            _event("NOISE", 3, trade_id="OTHER-B", trade_uuid="OTHER-UUID-B"),
        ],
    )
    bundle = _collect(case)
    with sqlite3.connect(case.timeline_index) as connection:
        record_id, start = connection.execute(
            "SELECT record_id, start_offset FROM records WHERE event_type='POSITION_OPEN'"
        ).fetchone()
        connection.execute(
            "UPDATE postings SET start_offset=? WHERE record_id=?",
            (int(start) + 1, int(record_id)),
        )
        connection.execute(
            "UPDATE records SET start_offset=? WHERE record_id=?",
            (int(start) + 1, int(record_id)),
        )
    source_coverage = {
        name: dict(detail) for name, detail in bundle.source_coverage.items()
    }
    source_coverage["history_manager"]["evidence_found"] = False
    altered_bundle = replace(bundle, source_coverage=source_coverage)

    result = _observe(altered_bundle)
    history = result.sources["history_manager"]
    timeline = result.sources["timeline"]

    assert result.status == shadow_v1.MISMATCH
    assert shadow_v1.SOURCE_METADATA_MISMATCH in result.mismatch_categories
    assert shadow_v1.OFFSET_MISMATCH in result.mismatch_categories
    assert history.mismatch_categories == (shadow_v1.SOURCE_METADATA_MISMATCH,)
    assert timeline.mismatch_categories == (shadow_v1.OFFSET_MISMATCH,)
    assert shadow_v1.SOURCE_METADATA_MISMATCH not in timeline.mismatch_categories


def test_injected_sources_are_not_crossed_with_configured_physical_indexes(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    source_payload = [_event("POSITION_OPEN", 2)]
    original = copy.deepcopy(source_payload)
    sources = {name: [] for name in validator.COMPONENTS}
    sources["history_manager"] = source_payload
    sources["timeline"] = source_payload

    bundle = validator.collect_evidence_bundle(case.trade_id, sources=sources)
    result = _observe(bundle)

    assert result.status == shadow_v1.NOT_COMPARABLE
    assert all(item.reasons == ("LEGACY_CAPTURE_UNAVAILABLE",) for item in result.sources.values())
    assert source_payload == original


def test_observer_never_builds_repairs_or_mutates_local_artifacts(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    before = {
        path: path.read_bytes()
        for path in (case.history, case.timeline, case.history_index, case.timeline_index)
    }
    monkeypatch.setattr(
        index_v1,
        "build_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("auto-build attempted")),
    )
    monkeypatch.setattr(
        os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("publish attempted")),
    )

    result = _observe(bundle)

    assert result.status == shadow_v1.MATCH
    assert {path: path.read_bytes() for path in before} == before


def test_telemetry_snapshot_is_detached_bounded_and_redacted(tmp_path, monkeypatch):
    case = _prepare_case(tmp_path, monkeypatch)
    bundle = _collect(case)
    result = _observe(bundle)
    assert result.status == shadow_v1.MATCH

    first = shadow_v1.get_shadow_telemetry_snapshot()
    history = first["sources"]["history_manager"]
    assert history["shadow_requests"] == 1
    assert history["shadow_matches"] == 1
    assert history["shadow_last_trade_id_masked"] == hashlib.sha256(
        case.trade_id.encode("utf-8")
    ).hexdigest()[:12]
    assert history["shadow_last_journal_bytes_read"] > 0
    first["sources"]["history_manager"]["shadow_requests"] = 999
    first["sources"]["history_manager"]["nested"] = {"payload": "secret"}

    second = shadow_v1.get_shadow_telemetry_snapshot()
    serialized = json.dumps(second, sort_keys=True)
    assert second["sources"]["history_manager"]["shadow_requests"] == 1
    assert "nested" not in second["sources"]["history_manager"]
    assert case.trade_id not in serialized
    assert str(case.history) not in serialized
    assert set(second["sources"]) == set(shadow_v1.SHADOW_SOURCES)
