from __future__ import annotations

import copy
import json
import os
import socket
import sqlite3
import tracemalloc
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
import trade_evidence_identity_offset_source_envelope_v1 as envelope_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_source_envelope_v1 import (
    BUILT,
    COMPLETENESS_FULL_CERTIFIED,
    COMPLETENESS_UNCERTIFIED,
    COMPLETENESS_UNKNOWN,
    FALLBACK_REQUIRED,
    INDEX_ONLY,
    INDEX_PLUS_TAIL,
    NEGATIVE_CERTIFIED,
    NEGATIVE_UNSAFE,
    NOT_NEGATIVE,
    EnvelopeCaps,
    PinnedSourceIndexSession,
    build_indexed_source_envelope,
    plan_and_build_indexed_source_envelope,
)
from trade_evidence_physical_page_planner_v1 import (
    DEFAULT_MAX_SEGMENT_ROWS,
    NOT_REPRODUCIBLE,
    REPRODUCIBLE,
    plan_physical_page,
)
from trade_evidence_physical_window_contract_v1 import encode_scan_cursor


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in C1 tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _line(**values: object) -> bytes:
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _config(*, max_line_bytes: int = 2 * 1024 * 1024) -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=64,
        segment_target_bytes=512,
        batch_bytes=16 * 1024,
        batch_lines=64,
        max_line_bytes=max_line_bytes,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )


def _paths(tmp_path: Path, source_id: str = "timeline") -> tuple[Path, Path]:
    return (
        tmp_path / f"{source_id}.jsonl",
        tmp_path / f"{source_id}.identity-offset-v2.sqlite3",
    )


def _build_v2(
    tmp_path: Path,
    raw: bytes,
    *,
    source_id: str = "timeline",
    config: index_module.BuildConfig | None = None,
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, index = _paths(tmp_path, source_id)
    source.write_bytes(raw)
    index_module.build_index_v2(
        source,
        index,
        source_id,
        config=config or _config(),
        measure_memory=False,
    )
    return source, index


def _context(trade_id: str, **typed: str) -> validator.CorrelationContext:
    context = validator.new_correlation_context(trade_id)
    context.registry_anchored = True
    for identity_type, value in typed.items():
        group = validator.IDENTITY_GROUPS[identity_type]
        context.trusted_typed.setdefault(identity_type, set()).add(value)
        context.trusted.setdefault(group, set()).add(value)
    return context


def _build(
    source: Path,
    index: Path,
    context: validator.CorrelationContext,
    *,
    source_id: str = "timeline",
    plan=None,
    caps: EnvelopeCaps = EnvelopeCaps(),
    fault_injector=None,
    expected_snapshot=None,
):
    physical_plan = plan
    if physical_plan is None:
        physical_plan = plan_physical_page(source, index, source_id)
        assert physical_plan.status == REPRODUCIBLE, physical_plan
    return build_indexed_source_envelope(
        source=source_id,
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        physical_plan=physical_plan,
        expected_snapshot=expected_snapshot,
        caps=caps,
        fault_injector=fault_injector,
    )


def _plan_and_build(
    source: Path,
    index: Path,
    context: validator.CorrelationContext,
    *,
    source_id: str = "timeline",
    caps: EnvelopeCaps = EnvelopeCaps(),
    fault_injector=None,
    **planner_options: object,
):
    return plan_and_build_indexed_source_envelope(
        source=source_id,
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        caps=caps,
        fault_injector=fault_injector,
        **planner_options,
    )


def test_v2_certified_index_only_builds_private_envelope_without_mutating_input(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-1", event_type="POSITION_OPEN", client_order_id="C-1")
        + _line(client_order_id="C-1", event_type="ORDER_FILLED", fill_id="F-1"),
    )
    context = _context("T-1")
    before = copy.deepcopy(context)

    result = _plan_and_build(source, index, context)

    assert result.status == BUILT
    assert result.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert result.index_mode == INDEX_ONLY
    assert [row["event_type"] for row in result.correlated_rows] == [
        "POSITION_OPEN",
        "ORDER_FILLED",
    ]
    assert result.factual_offsets == tuple(sorted(result.factual_offsets))
    assert context == before
    assert result.clone_context_after().trusted["fill"] == {"F-1"}
    private = result.to_legacy_private_envelope()
    assert private["_evidence_correlated"] is True
    assert private["_reader_metadata"]["evidence_status"] == "EVIDENCE_FOUND"


def test_v1_is_rejected_as_unsupported_schema(tmp_path: Path) -> None:
    source, index = _paths(tmp_path)
    source.write_bytes(_line(trade_id="T-V1", event_type="OPEN"))
    index_module.build_index(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    plan = plan_physical_page(source, index, "timeline")
    context = _context("T-V1")

    result = build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        physical_plan=plan,
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "UNSUPPORTED_SCHEMA"


def test_uncertified_v2_and_identity_contract_mismatch_fail_closed(tmp_path: Path) -> None:
    source, index = _build_v2(tmp_path, _line(trade_id="T-U", event_type="OPEN"))
    plan = plan_physical_page(source, index, "timeline")
    context = _context("T-U")
    with sqlite3.connect(index) as connection:
        connection.execute(
            """
            UPDATE source_state
            SET certification_kind='UNCERTIFIED', certified_watermark=0,
                certified_anchor_offset=0, certified_anchor_length=0,
                certified_anchor=?, certified_summary_hash=?, certified_at=NULL,
                certified_source_size=NULL, certified_source_mtime_ns=NULL,
                certified_source_ctime_ns=NULL
            """,
            (b"\x00" * 16, b"\x00" * 16),
        )
    result = _build(source, index, context, plan=plan)
    assert result.fallback_reason == "INDEX_V2_UNCERTIFIED"

    source2, index2 = _build_v2(
        tmp_path / "contract", _line(trade_id="T-C", event_type="OPEN")
    )
    plan2 = plan_physical_page(source2, index2, "timeline")
    with sqlite3.connect(index2) as connection:
        connection.execute(
            "UPDATE source_state SET identity_contract_hash='mismatch'"
        )
    result2 = _build(source2, index2, _context("T-C"), plan=plan2)
    assert result2.fallback_reason == "IDENTITY_CONTRACT_MISMATCH"

    source3, index3 = _build_v2(
        tmp_path / "physical", _line(trade_id="T-PC", event_type="OPEN")
    )
    plan3 = plan_physical_page(source3, index3, "timeline")
    with sqlite3.connect(index3) as connection:
        connection.execute(
            "UPDATE source_state SET physical_contract_hash='mismatch'"
        )
    result3 = _build(source3, index3, _context("T-PC"), plan=plan3)
    assert result3.fallback_reason == "PHYSICAL_CONTRACT_MISMATCH"


def test_certified_summary_seal_tamper_is_rejected(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path, _line(trade_id="T-SEAL", event_type="OPEN", timestamp="2026-01-01")
    )
    plan = plan_physical_page(source, index, "timeline")
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE segments SET oldest_timestamp='ZZZ', newest_timestamp='ZZZ'"
        )
    result = _build(source, index, _context("T-SEAL"), plan=plan)
    assert result.fallback_reason == "CERTIFIED_SUMMARY_HASH_MISMATCH"


def test_source_id_path_and_target_context_mismatches_fail_closed(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path, _line(trade_id="T-M", event_type="OPEN"), source_id="history_manager"
    )
    plan = plan_physical_page(source, index, "history_manager")
    context = _context("T-M")
    wrong_source = build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        physical_plan=plan,
    )
    assert wrong_source.fallback_reason == "SOURCE_ID_MISMATCH"

    wrong_target = build_indexed_source_envelope(
        source="history_manager",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(_context("OTHER")),
        correlation_context=context,
        physical_plan=plan,
    )
    assert wrong_target.fallback_reason == "TARGET_CONTEXT_MISMATCH"


def test_plan_is_bound_to_pinned_source_path_and_file_identity(tmp_path: Path) -> None:
    raw = _line(trade_id="T-PLAN", event_type="OPEN")
    source, index = _build_v2(tmp_path / "left", raw)
    other_source, other_index = _build_v2(tmp_path / "right", raw)
    foreign_plan = plan_physical_page(other_source, other_index, "timeline")

    result = _build(
        source,
        index,
        _context("T-PLAN"),
        plan=foreign_plan,
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "PLAN_PATH_FINGERPRINT_MISMATCH"


def test_external_plan_entrypoint_is_testing_only_and_never_claims_completeness(
    tmp_path: Path,
) -> None:
    first = _line(trade_id="T-EXTERNAL", event_type="FIRST")
    source, index = _build_v2(
        tmp_path,
        first + _line(trade_id="T-EXTERNAL", event_type="SECOND"),
    )
    context = _context("T-EXTERNAL")
    legitimate = plan_physical_page(source, index, "timeline")
    sliced = replace(
        legitimate,
        page_start=len(first),
        replay_start=len(first),
    )

    direct = _build(source, index, context, plan=sliced)
    lifecycle = _plan_and_build(source, index, context)

    assert direct.status == BUILT
    assert [row["event_type"] for row in direct.correlated_rows] == ["SECOND"]
    assert direct.completeness_status == COMPLETENESS_UNCERTIFIED
    assert "build_indexed_source_envelope" not in envelope_module.__all__
    assert [row["event_type"] for row in lifecycle.correlated_rows] == [
        "FIRST",
        "SECOND",
    ]
    assert lifecycle.completeness_status == COMPLETENESS_FULL_CERTIFIED


def test_index_plus_streaming_terminal_tail_preserves_order(tmp_path: Path) -> None:
    first = _line(
        trade_id="T-TAIL", event_type="POSITION_OPEN", client_order_id="ENTRY-1"
    )
    terminal = json.dumps(
        {"client_order_id": "ENTRY-1", "event_type": "POSITION_CLOSE"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    source, index = _build_v2(tmp_path, first)
    with source.open("ab") as handle:
        handle.write(terminal)
    index_module.catch_up_index(source, index, "timeline", measure_memory=False)
    context = _context("T-TAIL")

    result = _build(source, index, context)

    assert result.status == BUILT
    assert result.index_mode == INDEX_PLUS_TAIL
    assert [row["event_type"] for row in result.correlated_rows] == [
        "POSITION_OPEN",
        "POSITION_CLOSE",
    ]
    assert result.metrics.tail_bytes == len(terminal)
    assert result.factual_offsets[1] == len(first)
    assert result.raw_source_metadata["terminal_tail_incomplete"] is True


def test_incomplete_terminal_tail_can_never_certify_negative(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="FOREIGN", event_type="HEAD"),
    )
    fragment = b'{"trade_id":"T-INCOMPLETE'
    with source.open("ab") as handle:
        handle.write(fragment)
    index_module.catch_up_index(source, index, "timeline", measure_memory=False)
    # This operational hint is not a completeness witness.  The C2 reader
    # must derive terminal integrity from its pinned journal descriptor.
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE source_state SET trailing_fragment_bytes=0, "
            "trailing_fragment_kind='NONE' WHERE singleton_id=1"
        )
    context = _context("T-INCOMPLETE")

    result = _plan_and_build(source, index, context)

    assert result.status == BUILT
    assert result.index_mode == INDEX_PLUS_TAIL
    assert result.correlated_rows == ()
    assert result.physical_metadata["invalid_lines"] == 1
    assert result.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert result.negative_status == NEGATIVE_UNSAFE
    assert result.raw_source_metadata["terminal_tail_incomplete"] is True


def test_unsigned_cursor_can_never_certify_negative_even_when_not_tainted(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-CURSOR-UNSAFE", event_type="OPEN"),
    )
    cursor = encode_scan_cursor(
        source,
        source.stat(),
        source.stat().st_size,
        0,
        coverage_tainted=False,
    )
    context = _context("T-CURSOR-UNSAFE")

    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        scan_cursor=cursor,
    )

    assert result.status == BUILT
    assert result.correlated_rows == ()
    assert result.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert result.negative_status == NEGATIVE_UNSAFE
    assert result.raw_source_metadata["scan_cursor_supplied"] is True


def test_tail_candidate_identity_and_factual_caps_return_fallback(tmp_path: Path) -> None:
    terminal = json.dumps(
        {"trade_id": "T-CAPS", "event_type": "TAIL"}, separators=(",", ":")
    ).encode()
    head = _line(trade_id="T-CAPS", event_type="HEAD")
    source, index = _build_v2(tmp_path / "tail", head)
    with source.open("ab") as handle:
        handle.write(terminal)
    index_module.catch_up_index(source, index, "timeline", measure_memory=False)
    tail_context = _context("T-CAPS")
    tail_before = copy.deepcopy(tail_context)
    tail_result = _build(
        source,
        index,
        tail_context,
        caps=EnvelopeCaps(max_tail_bytes=1),
    )
    assert tail_result.fallback_reason == "TAIL_BYTE_CAP_EXCEEDED"
    assert tail_context == tail_before

    source2, index2 = _build_v2(
        tmp_path / "candidate",
        b"".join(_line(trade_id="T-CAND", event_type=f"E-{i}") for i in range(4)),
    )
    candidate_context = _context("T-CAND")
    candidate_before = copy.deepcopy(candidate_context)
    candidate_result = _build(
        source2,
        index2,
        candidate_context,
        caps=EnvelopeCaps(max_candidate_offsets=1),
    )
    assert candidate_result.fallback_reason == "CANDIDATE_OFFSET_CAP_EXCEEDED"
    assert candidate_context == candidate_before

    factual_context = _context("T-CAND")
    factual_before = copy.deepcopy(factual_context)
    factual_result = _build(
        source2,
        index2,
        factual_context,
        caps=EnvelopeCaps(max_candidate_offsets=10, max_factual_records=1),
    )
    assert factual_result.fallback_reason == "FACTUAL_RECORD_CAP_EXCEEDED"
    assert factual_context == factual_before


def test_identity_query_and_promoted_identity_caps_return_fallback(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path / "query",
        _line(exchange_order_id="ORDER-X", event_type="ORDER")
    )
    query_context = _context("T-Q", broker_order_id="ORDER-X")
    query_before = copy.deepcopy(query_context)
    query_result = _build(
        source,
        index,
        query_context,
        caps=EnvelopeCaps(max_identity_queries=1),
    )
    assert query_result.fallback_reason == "IDENTITY_QUERY_CAP_EXCEEDED"
    assert query_context == query_before

    source2, index2 = _build_v2(
        tmp_path / "promotion",
        _line(
            trade_id="T-P",
            event_type="OPEN",
            trade_uuid="U-P",
            lifecycle_id="L-P",
            client_order_id="C-P",
        ),
    )
    promotion_context = _context("T-P")
    promotion_before = copy.deepcopy(promotion_context)
    promotion_result = _build(
        source2,
        index2,
        promotion_context,
        caps=EnvelopeCaps(max_promoted_identities=1),
    )
    assert promotion_result.fallback_reason == "PROMOTED_IDENTITY_CAP_EXCEEDED"
    assert promotion_context == promotion_before


def test_high_cardinality_is_streamed_until_cap_without_partial_envelope(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path,
        b"".join(
            _line(trade_id="T-HIGH", event_type="OBS", sequence=i)
            for i in range(1_200)
        ),
    )
    result = _build(
        source,
        index,
        _context("T-HIGH"),
        caps=EnvelopeCaps(max_candidate_offsets=1_000),
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "CANDIDATE_OFFSET_CAP_EXCEEDED"
    assert result.correlated_rows == ()
    assert result.factual_offsets == ()
    assert result.metrics.candidate_count <= 1_000


def test_tens_of_thousands_same_identity_hits_hard_factual_cap(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path,
        b"".join(
            _line(trade_id="T-HARD", event_type="OBS", sequence=i)
            for i in range(25_300)
        ),
        config=replace(_config(), segment_target_bytes=16 * 1024),
    )
    result = _build(
        source,
        index,
        _context("T-HARD"),
    )
    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "FACTUAL_RECORD_CAP_EXCEEDED"
    assert result.metrics.candidate_count <= 25_000
    assert result.correlated_rows == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_candidate_offsets", envelope_module.MAX_CANDIDATE_OFFSETS + 1),
        ("max_factual_records", envelope_module.MAX_FACTUAL_RECORDS + 1),
        ("max_identity_queries", envelope_module.MAX_IDENTITY_QUERIES + 1),
        ("max_promoted_identities", envelope_module.MAX_PROMOTED_IDENTITIES + 1),
        ("max_heap_cursors", envelope_module.MAX_HEAP_CURSORS + 1),
        ("max_tail_lines", envelope_module.MAX_TAIL_LINES + 1),
        ("busy_timeout_ms", envelope_module.DEFAULT_BUSY_TIMEOUT_MS + 1),
    ],
)
def test_configurable_limits_cannot_exceed_c1_hard_caps(field: str, value: int) -> None:
    with pytest.raises(ValueError, match="hard cap"):
        replace(EnvelopeCaps(), **{field: value}).validate()


def test_heap_cursor_and_total_journal_byte_caps_are_enforced(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path / "heap",
        _line(
            trade_id="T-HEAP",
            exchange_order_id="ORDER-HEAP",
            event_type="OBS",
        ),
    )
    heap_result = _build(
        source,
        index,
        _context("T-HEAP", broker_order_id="ORDER-HEAP"),
        caps=EnvelopeCaps(max_heap_cursors=1),
    )
    assert heap_result.fallback_reason == "HEAP_CURSOR_CAP_EXCEEDED"

    source2, index2 = _build_v2(
        tmp_path / "bytes", _line(trade_id="T-BYTES", event_type="OBS")
    )
    byte_result = _build(
        source2,
        index2,
        _context("T-BYTES"),
        caps=EnvelopeCaps(max_source_journal_bytes=64),
    )
    assert byte_result.fallback_reason == "SOURCE_JOURNAL_BYTE_CAP_EXCEEDED"

    plan = plan_physical_page(source2, index2, "timeline")
    charged_plan = replace(plan, boundary_scan_bytes=32)
    planner_charge = charged_plan.boundary_scan_bytes + charged_plan.validation_bytes
    charged_result = _build(
        source2,
        index2,
        _context("MISSING"),
        plan=charged_plan,
        caps=EnvelopeCaps(
            max_source_journal_bytes=source2.stat().st_size + planner_charge
        ),
    )
    assert charged_result.status == FALLBACK_REQUIRED
    assert charged_result.fallback_reason == "SOURCE_JOURNAL_BYTE_CAP_EXCEEDED"


def test_zero_evidence_certification_distinguishes_trusted_and_external_plans(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        b"".join(_line(trade_id="OTHER", event_type="OBS", sequence=i) for i in range(8)),
    )
    unproven = _build(source, index, _context("MISSING"))
    assert unproven.status == BUILT
    assert unproven.correlated_rows == ()
    assert unproven.negative_status == NEGATIVE_UNSAFE
    assert unproven.completeness_status == COMPLETENESS_UNCERTIFIED

    empty_source, empty_index = _build_v2(
        tmp_path / "no-mapping",
        b"\n[]\n{bad}\n",
    )
    certified = _plan_and_build(empty_source, empty_index, _context("MISSING"))
    assert certified.status == BUILT
    assert certified.correlated_rows == ()
    assert certified.metrics.record_count == 0
    assert certified.raw_source_metadata["plan"]["mapping_records"] == 0
    assert certified.negative_status == NEGATIVE_CERTIFIED
    assert certified.completeness_status == COMPLETENESS_FULL_CERTIFIED

    tampered_source, tampered_index = _build_v2(
        tmp_path / "missing-posting",
        _line(trade_id="T-MISSING-POSTING", event_type="OPEN"),
    )
    tampered_plan = plan_physical_page(
        tampered_source, tampered_index, "timeline"
    )
    with sqlite3.connect(tampered_index) as connection:
        connection.execute("DELETE FROM postings")
        connection.execute("DELETE FROM identities")
    tampered = _build(
        tampered_source,
        tampered_index,
        _context("T-MISSING-POSTING"),
        plan=tampered_plan,
    )
    assert tampered.status == FALLBACK_REQUIRED
    assert tampered.fallback_reason == "SERVING_COMPLETENESS_SEAL_MISMATCH"
    assert tampered.completeness_status == COMPLETENESS_UNKNOWN

    partial_plan = plan_physical_page(
        source,
        index,
        "timeline",
        byte_budget=128,
        record_budget=100,
        block_bytes=32,
    )
    assert partial_plan.coverage_complete is False
    unsafe = _build(
        source,
        index,
        _context("MISSING"),
        plan=partial_plan,
        caps=EnvelopeCaps(),
    )
    assert unsafe.status == BUILT
    assert unsafe.negative_status == NEGATIVE_UNSAFE


@pytest.mark.parametrize(
    "tamper",
    [
        "remove_posting",
        "remove_identity_and_postings",
        "remove_record_and_postings",
        "swap_identity_ownership",
        "move_posting_to_wrong_record",
        "add_wrong_but_fk_coherent_posting",
        "change_identity_class",
    ],
)
def test_logical_index_tamper_matrix_fails_serving_completeness_before_lookup(
    tmp_path: Path, tamper: str
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-TAMPER", event_type="TARGET")
        + _line(trade_id="OTHER", event_type="OTHER"),
    )
    with sqlite3.connect(index) as connection:
        connection.row_factory = sqlite3.Row
        target_identity = connection.execute(
            "SELECT identity_id FROM identities "
            "WHERE identity_type='trade_id' AND identity_value='T-TAMPER'"
        ).fetchone()[0]
        other_identity = connection.execute(
            "SELECT identity_id FROM identities "
            "WHERE identity_type='trade_id' AND identity_value='OTHER'"
        ).fetchone()[0]
        target_record = connection.execute(
            "SELECT record_id, start_offset FROM records ORDER BY start_offset LIMIT 1"
        ).fetchone()
        other_record = connection.execute(
            "SELECT record_id, start_offset FROM records ORDER BY start_offset LIMIT 1 OFFSET 1"
        ).fetchone()
        if tamper == "remove_posting":
            connection.execute(
                "DELETE FROM postings WHERE identity_id=?",
                (target_identity,),
            )
        elif tamper == "remove_identity_and_postings":
            connection.execute("DELETE FROM postings WHERE identity_id=?", (target_identity,))
            connection.execute("DELETE FROM identities WHERE identity_id=?", (target_identity,))
        elif tamper == "remove_record_and_postings":
            connection.execute(
                "DELETE FROM postings WHERE record_id=? AND start_offset=?",
                (target_record["record_id"], target_record["start_offset"]),
            )
            connection.execute(
                "DELETE FROM records WHERE record_id=?",
                (target_record["record_id"],),
            )
        elif tamper == "swap_identity_ownership":
            connection.execute(
                "UPDATE identities SET identity_value='__SWAP__' WHERE identity_id=?",
                (target_identity,),
            )
            connection.execute(
                "UPDATE identities SET identity_value='T-TAMPER' WHERE identity_id=?",
                (other_identity,),
            )
            connection.execute(
                "UPDATE identities SET identity_value='OTHER' WHERE identity_id=?",
                (target_identity,),
            )
        elif tamper == "move_posting_to_wrong_record":
            connection.execute("DELETE FROM postings WHERE identity_id=?", (target_identity,))
            connection.execute(
                "INSERT INTO postings(identity_id,start_offset,record_id) VALUES(?,?,?)",
                (target_identity, other_record["start_offset"], other_record["record_id"]),
            )
        elif tamper == "add_wrong_but_fk_coherent_posting":
            connection.execute(
                "INSERT INTO postings(identity_id,start_offset,record_id) VALUES(?,?,?)",
                (target_identity, other_record["start_offset"], other_record["record_id"]),
            )
        elif tamper == "change_identity_class":
            connection.execute(
                "UPDATE identities SET identity_class="
                "CASE identity_class WHEN 'STRONG' THEN 'SECONDARY' ELSE 'STRONG' END "
                "WHERE identity_id=?",
                (target_identity,),
            )
        else:  # pragma: no cover - parametrization is closed above
            raise AssertionError(tamper)
        assert index_module.verify_certified_summary_hash(connection) is True
        assert index_module.verify_serving_completeness_seal(connection) is False
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    result = _plan_and_build(source, index, _context("T-TAMPER"))

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "SERVING_COMPLETENESS_SEAL_MISMATCH"
    assert result.completeness_status == COMPLETENESS_UNKNOWN


def test_positive_partial_logical_tamper_fails_serving_completeness_before_lookup(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        b"".join(
            _line(trade_id="T-FIVE", event_type=f"EVENT_{number}")
            for number in range(5)
        ),
    )
    with sqlite3.connect(index) as connection:
        identity_id = connection.execute(
            "SELECT identity_id FROM identities "
            "WHERE identity_type='trade_id' AND identity_value='T-FIVE'"
        ).fetchone()[0]
        missing = connection.execute(
            "SELECT record_id, start_offset FROM records ORDER BY start_offset LIMIT 1 OFFSET 2"
        ).fetchone()
        connection.execute(
            "DELETE FROM postings WHERE identity_id=? AND record_id=? AND start_offset=?",
            (identity_id, missing[0], missing[1]),
        )
        assert index_module.verify_certified_summary_hash(connection) is True
        assert index_module.verify_serving_completeness_seal(connection) is False

    result = _plan_and_build(source, index, _context("T-FIVE"))

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "SERVING_COMPLETENESS_SEAL_MISMATCH"
    assert result.completeness_status == COMPLETENESS_UNKNOWN


def test_resealed_coherent_logical_tamper_cannot_create_a_certified_negative(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-RESEALED", event_type="OPEN"),
    )
    with sqlite3.connect(index) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM postings")
        connection.execute("DELETE FROM identities")
        connection.execute("DELETE FROM records")
        connection.execute(
            "UPDATE segments SET mapping_records=0, "
            "nonmapping_json_lines=valid_json_lines, "
            "strong_postings=0, secondary_postings=0"
        )
        watermark = connection.execute(
            "SELECT certified_watermark FROM source_state WHERE singleton_id=1"
        ).fetchone()[0]
        resealed = index_module.calculate_certified_summary_hash(connection, watermark)
        connection.execute(
            "UPDATE source_state SET certified_summary_hash=? WHERE singleton_id=1",
            (resealed,),
        )
        assert index_module.verify_certified_summary_hash(connection) is True
        assert index_module.verify_serving_completeness_seal(connection) is False
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    result = _plan_and_build(source, index, _context("T-RESEALED"))

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "SERVING_COMPLETENESS_SEAL_MISMATCH"
    assert result.completeness_status == COMPLETENESS_UNKNOWN


def test_invalid_utf8_json_nonmapping_and_duplicates_keep_physical_metadata(tmp_path: Path) -> None:
    raw = (
        b"{broken}\n"
        + b"\xff\n"
        + b"[1,2]\n"
        + _line(trade_id="T-PHYS", event_type="OBS", value=1)
        + _line(trade_id="T-PHYS", event_type="OBS", value=1)
    )
    source, index = _build_v2(tmp_path, raw)
    result = _build(source, index, _context("T-PHYS"))

    assert result.status == BUILT
    assert len(result.correlated_rows) == 2
    assert result.physical_metadata["invalid_lines"] == 2
    assert result.physical_metadata["valid_lines"] == 3
    assert result.physical_metadata["lines_scanned"] == 5
    assert result.source_coverage["records_examined"] == 5


def test_oversized_physical_page_preserves_fail_closed_coverage(tmp_path: Path) -> None:
    source, index = _build_v2(tmp_path, b"X" * 300 + b"\n")
    context = _context("MISSING")

    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        byte_budget=64,
        record_budget=100,
        block_bytes=16,
    )

    assert result.status == BUILT
    assert result.correlated_rows == ()
    assert result.raw_source_metadata["plan"]["oversized"] is True
    assert result.physical_metadata["stop_reason"] == "LINE_EXCEEDS_BYTE_BUDGET"
    assert result.physical_metadata["coverage_complete"] is False
    assert result.negative_status == NEGATIVE_UNSAFE


def test_planner_not_reproducible_and_snapshot_witness_change_fallback(tmp_path: Path) -> None:
    source, index = _build_v2(tmp_path, _line(trade_id="T-W", event_type="OPEN"))
    context = _context("T-W")
    before = copy.deepcopy(context)
    plan = plan_physical_page(source, index, "timeline")
    refused = replace(plan, status=NOT_REPRODUCIBLE, reason="TEST_REFUSAL")
    result = _build(source, index, context, plan=refused)
    assert result.fallback_reason == "PLANNER_NOT_REPRODUCIBLE:TEST_REFUSAL"
    assert context == before

    metrics = None
    with PinnedSourceIndexSession(source, index, "timeline") as session:
        expected = session.snapshot_for_plan(plan)
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE source_state SET generation_uuid=?",
            (str(uuid.uuid4()),),
        )
    changed = _build(
        source,
        index,
        context,
        plan=plan,
        expected_snapshot=expected,
    )
    assert changed.fallback_reason == "SERVING_COMPLETENESS_SEAL_MISMATCH"
    assert context == before
    assert metrics is None


@pytest.mark.parametrize("mutation", ["append", "rewrite", "rewrite_append"])
def test_source_mutation_during_build_discards_staged_result(
    tmp_path: Path, mutation: str
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-MUT", event_type="OPEN")
        + _line(trade_id="T-MUT", event_type="CLOSE"),
    )
    context = _context("T-MUT")

    def mutate(point: str, _detail: object) -> None:
        if point != "after_session_open":
            return
        if mutation == "append":
            with source.open("ab") as handle:
                handle.write(_line(trade_id="T-MUT", event_type="LATE"))
        else:
            with source.open("r+b") as handle:
                handle.seek(1)
                value = handle.read(1)
                handle.seek(1)
                handle.write(b"X" if value != b"X" else b"Y")
                if mutation == "rewrite_append":
                    handle.seek(0, os.SEEK_END)
                    handle.write(_line(trade_id="T-MUT", event_type="LATE"))

    result = _build(source, index, context, fault_injector=mutate)
    assert result.status == FALLBACK_REQUIRED
    assert result.correlated_rows == ()
    assert context == _context("T-MUT")


def test_source_mutation_during_result_projection_is_caught_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-LATE-CHECK", event_type="OPEN"),
    )
    context = _context("T-LATE-CHECK")
    before = copy.deepcopy(context)
    original = envelope_module._events_for_source
    mutated = False

    def mutate_after_first_final_check(component: str, rows: object):
        nonlocal mutated
        events = original(component, rows)
        if not mutated:
            mutated = True
            with source.open("ab") as handle:
                handle.write(_line(trade_id="T-LATE-CHECK", event_type="LATE"))
        return events

    monkeypatch.setattr(envelope_module, "_events_for_source", mutate_after_first_final_check)
    result = _build(source, index, context)

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason in {
        "SOURCE_MUTATED_DURING_BUILD",
        "SOURCE_PATH_MUTATED_DURING_BUILD",
    }
    assert result.correlated_rows == ()
    assert context == before


def test_factual_hash_mismatch_and_index_stat_change_fail_closed(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path / "hash", _line(trade_id="T-HASH", event_type="OPEN")
    )

    def rewrite(point: str, _detail: object) -> None:
        if point == "after_session_open":
            with source.open("r+b") as handle:
                handle.seek(1)
                handle.write(b"Z")

    hash_context = _context("T-HASH")
    hash_before = copy.deepcopy(hash_context)
    mismatch = _build(source, index, hash_context, fault_injector=rewrite)
    assert mismatch.fallback_reason == "FACTUAL_RECORD_VERIFICATION_FAILED"
    assert hash_context == hash_before

    source2, index2 = _build_v2(
        tmp_path / "index", _line(trade_id="T-IDX", event_type="OPEN")
    )

    def touch_index(point: str, _detail: object) -> None:
        if point == "before_final_check":
            current = index2.stat().st_mtime_ns
            os.utime(index2, ns=(current, current + 1_000_000))

    changed = _build(source2, index2, _context("T-IDX"), fault_injector=touch_index)
    assert changed.fallback_reason == "INDEX_GENERATION_CHANGED_DURING_BUILD"


def test_preopen_truncate_regrow_and_replace_are_rejected(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path / "regrow",
        _line(trade_id="T-REGROW", event_type="OPEN")
        + _line(trade_id="T-REGROW", event_type="CLOSE"),
    )
    plan = plan_physical_page(source, index, "timeline")
    original = source.read_bytes()
    with source.open("r+b") as handle:
        handle.truncate(0)
        handle.write(original)
    regrown = _build(source, index, _context("T-REGROW"), plan=plan)
    assert regrown.status == FALLBACK_REQUIRED
    assert regrown.fallback_reason in {
        "CERTIFIED_SOURCE_METADATA_MISMATCH",
        "CERTIFIED_SOURCE_SIZE_MISMATCH",
    }

    source2, index2 = _build_v2(
        tmp_path / "replace", _line(trade_id="T-REPLACE", event_type="OPEN")
    )
    plan2 = plan_physical_page(source2, index2, "timeline")
    replacement = source2.with_name("replacement.jsonl")
    replacement.write_bytes(source2.read_bytes())
    os.replace(replacement, source2)
    replaced = _build(source2, index2, _context("T-REPLACE"), plan=plan2)
    assert replaced.status == FALLBACK_REQUIRED
    assert replaced.fallback_reason == "SOURCE_FILE_ID_MISMATCH"


def test_truncate_during_build_is_never_returned_as_valid_envelope(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-TRUNC", event_type="OPEN")
        + _line(trade_id="T-TRUNC", event_type="CLOSE"),
    )

    def truncate(point: str, _detail: object) -> None:
        if point == "after_session_open":
            with source.open("r+b") as handle:
                handle.truncate(1)

    result = _build(source, index, _context("T-TRUNC"), fault_injector=truncate)
    assert result.status == FALLBACK_REQUIRED
    assert result.correlated_rows == ()


def test_sqlite_query_only_session_and_busy_are_fail_closed(tmp_path: Path) -> None:
    source, index = _build_v2(tmp_path, _line(trade_id="T-SQL", event_type="OPEN"))
    with PinnedSourceIndexSession(source, index, "timeline") as session:
        assert session.connection is not None
        assert session.connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert session.snapshot is not None
        assert session.snapshot.dev == os.fstat(session.source_handle.fileno()).st_dev

    lock = sqlite3.connect(index, isolation_level=None)
    plan = plan_physical_page(source, index, "timeline")
    assert plan.status == REPRODUCIBLE
    try:
        lock.execute("BEGIN EXCLUSIVE")
        busy_context = _context("T-SQL")
        busy_before = copy.deepcopy(busy_context)
        result = _build(
            source,
            index,
            busy_context,
            plan=plan,
            caps=EnvelopeCaps(busy_timeout_ms=1),
        )
    finally:
        lock.execute("ROLLBACK")
        lock.close()
    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "SQLITE_BUSY"
    assert busy_context == busy_before


def test_sqlite_lookup_plans_are_indexed_and_missing_required_index_fails_closed(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-QUERY", event_type="OPEN"),
    )
    with sqlite3.connect(index) as connection:
        candidate_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT r.record_id, r.start_offset FROM identities i "
                "JOIN postings p ON p.identity_id=i.identity_id "
                "JOIN records r ON r.record_id=p.record_id "
                "WHERE i.identity_type=? AND i.identity_value=? "
                "AND p.start_offset>=? AND p.start_offset<? "
                "AND r.start_offset+r.byte_length<=? "
                "ORDER BY p.start_offset,p.record_id",
                ("trade_id", "T-QUERY", 0, source.stat().st_size, source.stat().st_size),
            )
        )
        verification_plan = " ".join(
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN "
                "SELECT i.identity_type, i.identity_value, i.identity_group, i.identity_class "
                "FROM postings AS p INDEXED BY postings_record_idx "
                "JOIN identities i ON i.identity_id=p.identity_id "
                "WHERE p.record_id=? AND p.start_offset=? "
                "ORDER BY i.identity_type,i.identity_value,i.identity_group,i.identity_class",
                (1, 0),
            )
        )
        assert "SCAN p" not in candidate_plan
        assert "postings_record_idx" in verification_plan
        assert "SCAN p" not in verification_plan
        connection.execute("DROP INDEX postings_record_idx")

    result = _plan_and_build(source, index, _context("T-QUERY"))
    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "REQUIRED_QUERY_INDEX_MISSING"

    with sqlite3.connect(index) as connection:
        connection.execute(
            "CREATE INDEX postings_record_idx "
            "ON postings(record_id,start_offset,identity_id) WHERE record_id<0"
        )
    partial = _plan_and_build(source, index, _context("T-QUERY"))
    assert partial.status == FALLBACK_REQUIRED
    assert partial.fallback_reason == "REQUIRED_QUERY_INDEX_MISSING"

    analyzed_source, analyzed_index = _build_v2(
        tmp_path / "analyzed",
        _line(trade_id="T-ANALYZE", event_type="OPEN"),
    )
    with sqlite3.connect(analyzed_index) as connection:
        connection.execute("ANALYZE")
    analyzed = _plan_and_build(
        analyzed_source,
        analyzed_index,
        _context("T-ANALYZE"),
    )
    assert analyzed.status == FALLBACK_REQUIRED
    assert analyzed.fallback_reason == "UNTRUSTED_QUERY_PLANNER_STATS"


def test_session_enter_failures_close_source_and_sqlite_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-RESOURCE", event_type="OPEN"),
    )
    opened: list[object] = []
    real_path_open = Path.open

    def capture_open(path: Path, *args: object, **kwargs: object):
        handle = real_path_open(path, *args, **kwargs)
        if path == source:
            opened.append(handle)
        return handle

    def fail_fstat(_descriptor: int) -> os.stat_result:
        raise OSError("injected fstat failure")

    monkeypatch.setattr(Path, "open", capture_open)
    monkeypatch.setattr(envelope_module.os, "fstat", fail_fstat)
    session = PinnedSourceIndexSession(source, index, "timeline")
    with pytest.raises(envelope_module._Fallback) as failure:
        session.__enter__()
    assert failure.value.reason == "ELIGIBILITY_VALIDATION_FAILED"
    assert opened and all(handle.closed for handle in opened)
    assert session.source_handle is None
    assert session.connection is None

    monkeypatch.undo()

    def unexpected(_session: PinnedSourceIndexSession) -> None:
        raise RuntimeError("injected unexpected validation failure")

    monkeypatch.setattr(PinnedSourceIndexSession, "_validate_index_snapshot", unexpected)
    second = PinnedSourceIndexSession(source, index, "timeline")
    with pytest.raises(envelope_module._Fallback) as unexpected_failure:
        second.__enter__()
    assert unexpected_failure.value.reason == "ELIGIBILITY_VALIDATION_FAILED"
    assert second.source_handle is None
    assert second.connection is None


def test_result_is_defensively_copyable_and_fallback_cannot_project(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path, _line(trade_id="T-COPY", event_type="OPEN", nested={"x": [1]})
    )
    context = _context("T-COPY")
    result = _build(source, index, context)
    private = result.to_legacy_private_envelope()
    private["records"][0]["nested"]["x"].append(2)
    private["_correlation_context"].trusted["trade"].add("MUTATED")
    assert result.correlated_rows[0]["nested"]["x"] == (1,)
    assert "MUTATED" not in result.clone_context_after().trusted["trade"]

    refused = _build(
        source,
        index,
        context,
        plan=replace(
            plan_physical_page(source, index, "timeline"),
            status=NOT_REPRODUCIBLE,
            reason="NO",
        ),
    )
    with pytest.raises(RuntimeError):
        refused.to_legacy_private_envelope()


def test_plan_and_build_pins_session_before_planning(tmp_path: Path) -> None:
    source, index = _build_v2(
        tmp_path, _line(trade_id="T-PIN", event_type="OPEN")
    )
    context = _context("T-PIN")
    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
    )
    assert result.status == BUILT
    assert result.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert result.metrics.planner_ms >= 0
    assert result.metrics.source_journal_bytes == (
        result.metrics.boundary_bytes
        + result.metrics.factual_journal_bytes
        + result.metrics.tail_bytes
    )
    assert result.metrics.source_journal_bytes <= EnvelopeCaps().max_source_journal_bytes
    assert result.raw_source_metadata["snapshot"]["page_end"] == len(source.read_bytes())


@pytest.mark.parametrize(
    ("planner_options", "reason"),
    [
        (
            {"max_boundary_scan_bytes": EnvelopeCaps().max_boundary_bytes + 1},
            "PLANNER_BOUNDARY_CAP_EXCEEDED",
        ),
        ({"max_append_proof_bytes": 2}, "PLANNER_APPEND_PROOF_CAP_EXCEEDED"),
        (
            {"max_segment_rows": DEFAULT_MAX_SEGMENT_ROWS + 1},
            "PLANNER_SEGMENT_ROW_CAP_EXCEEDED",
        ),
        ({"page_end": 0}, "PLANNER_OPTION_FORBIDDEN"),
        ({"snapshot_eof": 0}, "PLANNER_OPTION_FORBIDDEN"),
    ],
)
def test_plan_and_build_rejects_unbounded_planner_options_before_planning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    planner_options: dict[str, int],
    reason: str,
) -> None:
    source, index = _build_v2(
        tmp_path, _line(trade_id="T-PLANNER-CAP", event_type="OPEN")
    )
    context = _context("T-PLANNER-CAP")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("planner must not run after a C1 cap violation")

    monkeypatch.setattr(envelope_module, "plan_physical_page", forbidden)
    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        **planner_options,
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == reason


def test_boundary_cap_is_checked_before_session_or_planner_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-BOUNDARY-PRECHECK", event_type="OPEN"),
    )
    context = _context("T-BOUNDARY-PRECHECK")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("planner must not run after the source precheck fails")

    monkeypatch.setattr(envelope_module, "plan_physical_page", forbidden)
    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        caps=EnvelopeCaps(max_boundary_bytes=16),
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "BOUNDARY_BYTE_CAP_EXCEEDED"
    assert result.metrics.boundary_bytes == 0
    assert result.metrics.source_journal_bytes == 0


def test_more_than_64_mib_builder_memory_is_bounded(tmp_path: Path) -> None:
    source, index = _paths(tmp_path)
    target_size = 64 * 1024 * 1024 + 4096
    line_size = 4096
    rows = target_size // line_size
    with source.open("wb") as handle:
        for sequence in range(rows):
            trade = "T-LARGE" if sequence in {rows - 2, rows - 1} else f"O-{sequence}"
            prefix = json.dumps(
                {"trade_id": trade, "event_type": "OBS", "sequence": sequence},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            handle.write(prefix + b" " * (line_size - len(prefix) - 1) + b"\n")
    assert source.stat().st_size > 64 * 1024 * 1024
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=index_module.BuildConfig(
            block_bytes=64 * 1024,
            segment_target_bytes=512 * 1024,
            batch_bytes=4 * 1024 * 1024,
            batch_lines=2_000,
            max_line_bytes=64 * 1024 * 1024,
            anchor_bytes=64 * 1024,
            busy_timeout_ms=25,
        ),
        measure_memory=False,
    )
    plan = plan_physical_page(source, index, "timeline")
    tracemalloc.start()
    try:
        result = _build(source, index, _context("T-LARGE"), plan=plan)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.status == BUILT
    assert len(result.correlated_rows) == 2
    assert result.metrics.factual_journal_bytes < 1024 * 1024
    assert peak < 64 * 1024 * 1024
