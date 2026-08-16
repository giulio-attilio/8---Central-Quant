from __future__ import annotations

import copy
import json
import os
import socket
import sqlite3
import uuid
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
import trade_evidence_identity_offset_source_envelope_v1 as envelope_module
import trade_evidence_physical_page_planner_v1 as planner_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_source_envelope_v1 import (
    BUILT,
    COMPLETENESS_FULL_CERTIFIED,
    COMPLETENESS_UNCERTIFIED,
    FALLBACK_REQUIRED,
    NEGATIVE_CERTIFIED,
    NEGATIVE_UNSAFE,
    NOT_NEGATIVE,
    PinnedSourceIndexSession,
    plan_and_build_from_pinned_session,
    plan_and_build_indexed_source_envelope,
)
from trade_evidence_physical_page_planner_v1 import (
    NOT_REPRODUCIBLE,
    REPRODUCIBLE,
    plan_physical_page_pinned,
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in pinned planner tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _line(**values: object) -> bytes:
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _build_v2(
    tmp_path: Path,
    raw: bytes,
    *,
    source_id: str = "timeline",
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / f"{source_id}.jsonl"
    index = tmp_path / f"{source_id}.identity-offset-v2.sqlite3"
    source.write_bytes(raw)
    index_module.build_index_v2(
        source,
        index,
        source_id,
        config=index_module.BuildConfig(
            block_bytes=64,
            segment_target_bytes=512,
            batch_bytes=16 * 1024,
            batch_lines=64,
            max_line_bytes=2 * 1024 * 1024,
            anchor_bytes=64,
            busy_timeout_ms=25,
        ),
        measure_memory=False,
    )
    return source, index


def _context(trade_id: str) -> validator.CorrelationContext:
    context = validator.new_correlation_context(trade_id)
    context.registry_anchored = True
    return context


def _pinned_arguments(session: PinnedSourceIndexSession) -> dict[str, Any]:
    assert session.connection is not None
    assert session.source_handle is not None
    assert session.snapshot is not None
    assert session._source_descriptor_open is not None
    assert session._source_path_open is not None
    return {
        "connection": session.connection,
        "source_handle": session.source_handle,
        "source_state": session.state,
        "source_descriptor": session._source_descriptor_open,
        "source_path_state": session._source_path_open,
        "expected_snapshot_eof": session.snapshot.source_size,
        "expected_generation_uuid": session.snapshot.index_generation_uuid,
    }


def test_pinned_planner_reuses_exact_resources_without_reopen_or_revalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-PINNED", event_type="OPEN")
        + _line(trade_id="T-PINNED", event_type="CLOSE"),
    )
    real_open = Path.open
    standalone_plan = planner_module.plan_physical_page(
        source, index, "timeline", max_append_proof_bytes=1
    )

    with PinnedSourceIndexSession(source, index, "timeline") as session:
        connection = session.connection
        handle = session.source_handle
        assert connection is not None and connection.in_transaction
        assert handle is not None and not handle.closed

        def forbidden_sqlite_open(_path: Path) -> sqlite3.Connection:
            raise AssertionError("pinned planner must not open another SQLite connection")

        def guarded_path_open(path: Path, *args: object, **kwargs: object):
            if path == source:
                raise AssertionError("pinned planner must not reopen the source")
            return real_open(path, *args, **kwargs)

        def forbidden_v2_revalidation(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("pinned planner must reuse the session state")

        monkeypatch.setattr(planner_module, "_sqlite_ro", forbidden_sqlite_open)
        monkeypatch.setattr(Path, "open", guarded_path_open)
        monkeypatch.setattr(
            planner_module, "_validate_v2_state", forbidden_v2_revalidation
        )

        plan = session.plan_physical_page(max_append_proof_bytes=1)

        assert plan.status == REPRODUCIBLE
        assert session.connection is connection
        assert session.source_handle is handle
        assert connection.in_transaction
        assert not handle.closed
        assert int(plan.cursor_inputs["dev"]) == session.snapshot.dev
        assert int(plan.cursor_inputs["ino"]) == session.snapshot.inode
        assert plan.snapshot_eof == session.snapshot.source_size
        assert plan.to_dict() == standalone_plan.to_dict()

    assert handle.closed
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_primary_lifecycle_uses_pinned_planner_and_bypasses_external_plan_builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-MAIN", event_type="OPEN"),
    )
    context = _context("T-MAIN")
    context_before = copy.deepcopy(context)
    observed: dict[str, Any] = {}
    real_pinned_planner = envelope_module.plan_physical_page_pinned

    def forbidden_external_builder(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("primary lifecycle must not use the external-plan builder")

    def observe_pinned_planner(*args: object, **kwargs: Any):
        observed.update(kwargs)
        connection = kwargs["connection"]
        source_handle = kwargs["source_handle"]
        assert connection.in_transaction
        assert not source_handle.closed
        return real_pinned_planner(*args, **kwargs)

    monkeypatch.setattr(
        envelope_module, "build_indexed_source_envelope", forbidden_external_builder
    )
    monkeypatch.setattr(
        envelope_module, "plan_physical_page_pinned", observe_pinned_planner
    )

    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
    )

    assert result.status == BUILT
    assert [row["event_type"] for row in result.correlated_rows] == ["OPEN"]
    assert context == context_before
    assert observed["source_state"]["generation_uuid"] == observed[
        "expected_generation_uuid"
    ]
    assert observed["expected_snapshot_eof"] == source.stat().st_size
    assert observed["source_handle"].closed
    with pytest.raises(sqlite3.ProgrammingError):
        observed["connection"].execute("SELECT 1")


def test_safe_composition_api_keeps_two_source_sessions_open(
    tmp_path: Path,
) -> None:
    history_source, history_index = _build_v2(
        tmp_path / "history",
        _line(trade_id="T-TWO", event_type="HISTORY"),
        source_id="history_manager",
    )
    timeline_source, timeline_index = _build_v2(
        tmp_path / "timeline",
        _line(trade_id="T-TWO", event_type="TIMELINE"),
        source_id="timeline",
    )
    context = _context("T-TWO")

    with ExitStack() as stack:
        history_session = stack.enter_context(
            PinnedSourceIndexSession(
                history_source, history_index, "history_manager"
            )
        )
        timeline_session = stack.enter_context(
            PinnedSourceIndexSession(timeline_source, timeline_index, "timeline")
        )
        history_connection = history_session.connection
        history_handle = history_session.source_handle
        timeline_connection = timeline_session.connection
        timeline_handle = timeline_session.source_handle

        history = plan_and_build_from_pinned_session(
            history_session,
            target_identity=validator.target_identity_from_context(context),
            correlation_context=context,
        )
        timeline_context = history.clone_context_after()
        timeline = plan_and_build_from_pinned_session(
            timeline_session,
            target_identity=validator.target_identity_from_context(timeline_context),
            correlation_context=timeline_context,
        )

        assert history.status == BUILT
        assert timeline.status == BUILT
        assert history_connection is not None and history_connection.in_transaction
        assert timeline_connection is not None and timeline_connection.in_transaction
        assert history_handle is not None and not history_handle.closed
        assert timeline_handle is not None and not timeline_handle.closed

    assert history_handle.closed
    assert timeline_handle.closed
    with pytest.raises(sqlite3.ProgrammingError):
        history_connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError):
        timeline_connection.execute("SELECT 1")


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"expected_snapshot_eof": -1}, "PINNED_SNAPSHOT_EOF_MISMATCH"),
        (
            {"expected_generation_uuid": str(uuid.UUID(int=0))},
            "PINNED_GENERATION_MISMATCH",
        ),
        (
            {"source_state": {"source_id": "timeline"}},
            "PINNED_INDEX_STATE_MISMATCH",
        ),
    ],
)
def test_pinned_planner_rejects_snapshot_generation_and_state_mismatch(
    tmp_path: Path,
    override: dict[str, Any],
    reason: str,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-MISMATCH", event_type="OPEN"),
    )
    with PinnedSourceIndexSession(source, index, "timeline") as session:
        arguments = _pinned_arguments(session)
        arguments.update(override)
        plan = plan_physical_page_pinned(
            source,
            index,
            "timeline",
            **arguments,
            max_append_proof_bytes=1,
        )

        assert plan.status == NOT_REPRODUCIBLE
        assert plan.reason == reason
        assert session.connection is not None and session.connection.in_transaction
        assert session.source_handle is not None and not session.source_handle.closed


def test_pinned_planner_rejects_connection_and_descriptor_mismatch(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-RESOURCE-MISMATCH", event_type="OPEN"),
    )
    other = tmp_path / "other.jsonl"
    other.write_bytes(source.read_bytes())

    with PinnedSourceIndexSession(source, index, "timeline") as session:
        arguments = _pinned_arguments(session)
        wrong_descriptor = {**arguments, "source_descriptor": other.stat()}
        plan = plan_physical_page_pinned(
            source,
            index,
            "timeline",
            **wrong_descriptor,
            max_append_proof_bytes=1,
        )
        assert plan.status == NOT_REPRODUCIBLE
        assert plan.reason == "PINNED_SOURCE_SNAPSHOT_MISMATCH"

        unpinned_connection = sqlite3.connect(
            index.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None
        )
        unpinned_connection.row_factory = sqlite3.Row
        try:
            missing_transaction = {**arguments, "connection": unpinned_connection}
            plan2 = plan_physical_page_pinned(
                source,
                index,
                "timeline",
                **missing_transaction,
                max_append_proof_bytes=1,
            )
        finally:
            unpinned_connection.close()
        assert plan2.status == NOT_REPRODUCIBLE
        assert plan2.reason == "PINNED_INDEX_TRANSACTION_MISSING"


def test_primary_planner_fault_closes_session_and_preserves_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-FAULT", event_type="OPEN"),
    )
    context = _context("T-FAULT")
    context_before = copy.deepcopy(context)
    captured: list[PinnedSourceIndexSession] = []
    real_enter = PinnedSourceIndexSession.__enter__

    def capture_enter(session: PinnedSourceIndexSession) -> PinnedSourceIndexSession:
        opened = real_enter(session)
        captured.append(opened)
        return opened

    def fail_planner(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected pinned planner failure")

    monkeypatch.setattr(PinnedSourceIndexSession, "__enter__", capture_enter)
    monkeypatch.setattr(envelope_module, "plan_physical_page_pinned", fail_planner)

    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.fallback_reason == "C1_PLAN_BUILD_FAILED:RuntimeError"
    assert context == context_before
    assert len(captured) == 1
    assert captured[0].source_handle is None
    assert captured[0].connection is None


def test_source_mutation_during_pinned_planning_is_not_reproducible(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-PLAN-MUTATION", event_type="OPEN"),
    )

    def append_after_snapshot(point: str, _detail: object) -> None:
        if point == "after_snapshot":
            with source.open("ab") as handle:
                handle.write(_line(trade_id="T-PLAN-MUTATION", event_type="LATE"))

    with PinnedSourceIndexSession(source, index, "timeline") as session:
        plan = session.plan_physical_page(
            max_append_proof_bytes=1,
            fault_injector=append_after_snapshot,
        )
        assert plan.status == NOT_REPRODUCIBLE
        assert plan.reason is not None
        with pytest.raises(envelope_module._Fallback) as failure:
            session.final_check()
        assert failure.value.reason == "SOURCE_MUTATED_DURING_BUILD"


def test_safe_api_preserves_pinned_planner_refusal_reason(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-PRE-PLAN-MUTATION", event_type="OPEN"),
    )
    context = _context("T-PRE-PLAN-MUTATION")
    context_before = copy.deepcopy(context)

    with PinnedSourceIndexSession(source, index, "timeline") as session:
        with source.open("ab") as handle:
            handle.write(_line(trade_id="T-PRE-PLAN-MUTATION", event_type="LATE"))
        result = plan_and_build_from_pinned_session(
            session,
            target_identity=validator.target_identity_from_context(context),
            correlation_context=context,
        )

        assert result.status == FALLBACK_REQUIRED
        assert result.fallback_reason == (
            "PLANNER_NOT_REPRODUCIBLE:PINNED_SOURCE_SNAPSHOT_MISMATCH"
        )
        assert result.correlated_rows == ()
        assert context == context_before
        assert session.connection is not None and session.connection.in_transaction
        assert session.source_handle is not None and not session.source_handle.closed


@pytest.mark.parametrize("mutation", ["source_append", "index_touch"])
def test_mutation_between_pinned_plan_and_build_discards_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-BETWEEN", event_type="OPEN"),
    )
    context = _context("T-BETWEEN")
    context_before = copy.deepcopy(context)
    real_pinned_planner = envelope_module.plan_physical_page_pinned

    def mutate_after_plan(*args: object, **kwargs: Any):
        plan = real_pinned_planner(*args, **kwargs)
        assert plan.status == REPRODUCIBLE
        if mutation == "source_append":
            with source.open("ab") as handle:
                handle.write(_line(trade_id="T-BETWEEN", event_type="LATE"))
        else:
            current = index.stat()
            os.utime(
                index,
                ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000),
            )
        return plan

    monkeypatch.setattr(
        envelope_module, "plan_physical_page_pinned", mutate_after_plan
    )
    result = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
    )

    assert result.status == FALLBACK_REQUIRED
    assert result.correlated_rows == ()
    assert context == context_before
    if mutation == "source_append":
        assert result.fallback_reason == "SOURCE_MUTATED_DURING_BUILD"
    else:
        assert result.fallback_reason == "INDEX_GENERATION_CHANGED_DURING_BUILD"


def test_only_session_planned_success_claims_full_serving_certificate(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-FULL", event_type="OPEN"),
    )
    context = _context("T-FULL")
    external_plan = planner_module.plan_physical_page(source, index, "timeline")
    external = envelope_module.build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        physical_plan=external_plan,
    )

    with PinnedSourceIndexSession(source, index, "timeline") as session:
        assert session.certification_state == index_module.CERTIFICATION_STATE_FULL
        safe = plan_and_build_from_pinned_session(
            session,
            target_identity=validator.target_identity_from_context(context),
            correlation_context=context,
        )
        assert safe.status == BUILT
        assert safe.completeness_status == COMPLETENESS_FULL_CERTIFIED
        assert safe.negative_status == NOT_NEGATIVE

    assert external.status == BUILT
    assert external.completeness_status == COMPLETENESS_UNCERTIFIED
    assert external.negative_status == NOT_NEGATIVE
    assert session.certification_state == index_module.CERTIFICATION_STATE_NONE


def test_full_certificate_only_certifies_conclusive_zero_evidence(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        b"".join(
            _line(trade_id=f"FOREIGN-{position}", event_type="OBS")
            for position in range(4)
        ),
    )
    context = _context("MISSING")

    complete = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
    )
    partial = plan_and_build_indexed_source_envelope(
        source="timeline",
        source_path=source,
        index_path=index,
        target_identity=validator.target_identity_from_context(context),
        correlation_context=context,
        byte_budget=64 * 1024,
        record_budget=1,
        block_bytes=64,
    )

    assert complete.status == BUILT
    assert complete.correlated_rows == ()
    assert complete.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert complete.negative_status == NEGATIVE_CERTIFIED
    assert complete.physical_metadata["coverage_complete"] is True
    assert partial.status == BUILT
    assert partial.correlated_rows == ()
    assert partial.completeness_status == COMPLETENESS_FULL_CERTIFIED
    assert partial.negative_status == NEGATIVE_UNSAFE
    assert partial.physical_metadata["coverage_complete"] is False


@pytest.mark.parametrize(
    ("statement", "reason"),
    [
        (
            "UPDATE source_state SET serving_contract_version='wrong' "
            "WHERE singleton_id=1",
            "SERVING_CONTRACT_MISMATCH",
        ),
        (
            "UPDATE source_state SET serving_record_count=serving_record_count+1 "
            "WHERE singleton_id=1",
            "SERVING_COMPLETENESS_SEAL_MISMATCH",
        ),
    ],
)
def test_serving_certificate_mismatch_fails_enter_without_resource_leak(
    tmp_path: Path,
    statement: str,
    reason: str,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-SEAL", event_type="OPEN"),
    )
    with sqlite3.connect(index) as connection:
        connection.execute(statement)

    session = PinnedSourceIndexSession(source, index, "timeline")
    with pytest.raises(envelope_module._Fallback) as failure:
        session.__enter__()

    assert failure.value.reason == reason
    assert session.connection is None
    assert session.source_handle is None
    assert session.certification_state == index_module.CERTIFICATION_STATE_NONE


def test_serving_seal_and_final_witness_use_the_pinned_transaction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T-WITNESS", event_type="OPEN"),
    )
    checked: list[sqlite3.Connection] = []
    real_verify = index_module.verify_serving_completeness_seal

    def observe_verify(connection: sqlite3.Connection) -> bool:
        assert connection.in_transaction
        checked.append(connection)
        return real_verify(connection)

    monkeypatch.setattr(
        envelope_module, "verify_serving_completeness_seal", observe_verify
    )
    with PinnedSourceIndexSession(source, index, "timeline") as session:
        assert checked == [session.connection]
        expected_rows = (
            int(session.state["serving_record_count"])
            + int(session.state["serving_identity_count"])
            + int(session.state["serving_posting_count"])
            + len(index_module.SERVING_SCHEMA_OBJECTS)
            + 2  # verify state row plus seal-header state row
        )
        assert session.metrics.certification_sqlite_rows == expected_rows
        assert session.metrics.certification_ms >= 0.0
        assert session._certification_witness_open is not None
        witness = list(session._certification_witness_open)
        witness[-1] = int(witness[-1]) + 1
        session._certification_witness_open = tuple(witness)

        with pytest.raises(envelope_module._Fallback) as failure:
            session.final_check()

        assert failure.value.reason == "CERTIFICATION_CHANGED_DURING_BUILD"
