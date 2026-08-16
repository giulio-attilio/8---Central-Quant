from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
from tools import build_trade_evidence_identity_offset_index_v1 as index_cli
from trade_evidence_physical_window_contract_v1 import (
    CURSOR_CONTRACT_VERSION,
    PHYSICAL_CONTRACT_HASH,
    PHYSICAL_CONTRACT_VERSION,
    SUMMARY_CONTRACT_VERSION,
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in schema V2 tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _config() -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=32,
        segment_target_bytes=96,
        batch_bytes=512,
        batch_lines=4,
        max_line_bytes=128,
        anchor_bytes=32,
        busy_timeout_ms=25,
    )


def _json_line(**values: object) -> bytes:
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _state(index: Path) -> sqlite3.Row:
    with sqlite3.connect(index) as connection:
        connection.row_factory = sqlite3.Row
        value = connection.execute(
            "SELECT * FROM source_state WHERE singleton_id=1"
        ).fetchone()
        assert value is not None
        return value


def _rewrite_middle_and_append(source: Path, original_size: int, suffix: bytes) -> None:
    with source.open("r+b") as handle:
        handle.seek(original_size // 2)
        original = handle.read(1)
        handle.seek(original_size // 2)
        handle.write(b"Z" if original != b"Z" else b"Y")
        handle.seek(0, os.SEEK_END)
        handle.write(suffix)


def test_v1_default_and_explicit_v2_coexist_without_migration(tmp_path: Path) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="V1-V2"))
    v1_index = tmp_path / "timeline.identity-offset-v1.sqlite3"
    v2_index = tmp_path / "timeline.identity-offset-v2.sqlite3"

    index_module.build_index(
        source,
        v1_index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    index_module.build_index_v2(
        source,
        v2_index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )

    assert int(_state(v1_index)["schema_version"]) == index_module.SCHEMA_VERSION_V1
    assert int(_state(v2_index)["schema_version"]) == index_module.SCHEMA_VERSION_V2
    assert (
        index_module.validate_index(source, v1_index, "timeline").status
        == index_module.INDEX_COMPLETE_FOR_SNAPSHOT
    )
    assert (
        index_module.validate_index_v2(source, v1_index, "timeline").status
        == index_module.INDEX_V2_CONTRACT_MISMATCH
    )
    assert (
        index_module.validate_index(source, v2_index, "timeline").status
        == index_module.INDEX_STALE
    )
    assert (
        index_module.validate_index_v2(source, v2_index, "timeline").status
        == index_module.INDEX_V2_CERTIFIED
    )
    v1_metadata = index_module.read_index_certification(v1_index)
    assert v1_metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    assert v1_metadata.physical_contract_hash is None


def test_shared_physical_classification_is_opt_in_v2_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        _json_line(
            event="OPEN",
            trade_id="CLASSIFIER",
            occurred_at="2026-08-15T10:00:00Z",
        )
    )
    calls = 0
    original = index_module._physical_classify_line

    def tracked(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(index_module, "_physical_classify_line", tracked)
    index_module.build_index(
        source,
        tmp_path / "v1.sqlite3",
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    assert calls == 0

    index_module.build_index_v2(
        source,
        tmp_path / "v2.sqlite3",
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    assert calls > 0


def test_v2_deep_baseline_persists_physical_contract_and_exact_summaries(
    tmp_path: Path,
) -> None:
    source = tmp_path / "history.jsonl"
    source.write_bytes(
        b"".join(
            (
                _json_line(
                    event="OPEN",
                    trade_id="CERTIFIED",
                    occurred_at="2026-08-15T10:00:00Z",
                ),
                b" \t\r\n",
                b"42\n",
                b'{"broken":}\n',
                b"\xff\n",
                b" " * 200 + b"\n",
                b"x" * 200 + b"\n",
                _json_line(
                    event="CLOSE",
                    trade_id="CERTIFIED",
                    occurred_at="2026-08-15T11:00:00Z",
                ).replace(b"\n", b"\r\n"),
            )
        )
    )
    index = tmp_path / "history.identity-offset-v2.sqlite3"

    report = index_module.build_index_v2(
        source,
        index,
        "history_manager",
        config=_config(),
        measure_memory=False,
    )

    state = _state(index)
    assert report.published is True
    assert int(state["schema_version"]) == index_module.SCHEMA_VERSION_V2
    assert state["index_version"] == index_module.INDEX_VERSION_V2
    assert state["physical_contract_hash"] == PHYSICAL_CONTRACT_HASH
    assert state["physical_contract_version"] == PHYSICAL_CONTRACT_VERSION
    assert state["cursor_contract_version"] == str(CURSOR_CONTRACT_VERSION)
    assert state["summary_contract_version"] == str(SUMMARY_CONTRACT_VERSION)
    assert int(state["certified_watermark"]) == int(state["safe_watermark"])
    with sqlite3.connect(index) as connection:
        assert index_module.verify_certified_summary_hash(connection) is True
        calculated_summary_hash = index_module.calculate_certified_summary_hash(
            connection,
            int(state["certified_watermark"]),
        )
    assert bytes(state["certified_summary_hash"]) == calculated_summary_hash
    assert state["certification_kind"] == index_module.CERTIFICATION_DEEP_BASELINE
    assert state["certified_at"]
    assert int(state["certified_source_size"]) == source.stat().st_size
    with sqlite3.connect(index) as connection:
        summaries = connection.execute(
            """
            SELECT SUM(physical_lines), SUM(records_examined_lines),
                   SUM(blank_lines), SUM(valid_json_lines),
                   SUM(invalid_json_lines), SUM(invalid_utf8_lines),
                   SUM(mapping_records), SUM(nonmapping_json_lines),
                   SUM(oversized_barrier_lines), MIN(oldest_timestamp),
                   MAX(newest_timestamp)
            FROM segments
            """
        ).fetchone()
    assert summaries == (
        8,
        6,
        1,
        3,
        1,
        1,
        2,
        1,
        2,
        "2026-08-15T10:00:00+00:00",
        "2026-08-15T11:00:00+00:00",
    )
    validation = index_module.validate_index_v2(
        source,
        index,
        "history_manager",
        deep=True,
    )
    assert validation.status == index_module.INDEX_V2_CERTIFIED
    assert validation.complete is True


def test_v2_physical_contract_mismatch_is_not_certified(tmp_path: Path) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="CONTRACT"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE source_state SET physical_contract_hash='wrong-contract'"
        )
        connection.commit()

    validation = index_module.validate_index_v2(source, index, "timeline")
    assert validation.status == index_module.INDEX_V2_CONTRACT_MISMATCH
    assert validation.reasons == ("PHYSICAL_CONTRACT_MISMATCH",)
    assert index_module.read_index_certification(index).certified is False


def test_v2_coherent_segment_summary_tamper_breaks_certified_witness(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        _json_line(
            event="OPEN",
            trade_id="SUMMARY-WITNESS",
            occurred_at="2026-08-15T10:00:00Z",
        )
    )
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    with sqlite3.connect(index) as connection:
        assert index_module.verify_certified_summary_hash(connection) is True
        connection.execute(
            """
            UPDATE segments SET oldest_timestamp='2099-01-01T00:00:00+00:00',
                newest_timestamp='2099-01-01T00:00:00+00:00'
            WHERE segment_id=(SELECT MIN(segment_id) FROM segments)
            """
        )
        connection.commit()
        assert index_module.verify_certified_summary_hash(connection) is False

    validation = index_module.validate_index_v2(source, index, "timeline")
    assert validation.status == index_module.INDEX_V2_CORRUPT
    assert "CERTIFIED_SUMMARY_HASH_MISMATCH" in validation.reasons
    metadata = index_module.read_index_certification(index)
    assert metadata.certified_summary_verified is False
    assert metadata.certified is False


def test_v2_same_size_in_place_rewrite_is_rejected_by_snapshot_witness(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b"".join(
            _json_line(event=f"EVENT-{number}", trade_id=f"REWRITE-{number}")
            for number in range(20)
        )
    )
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    original_stat = source.stat()
    rewrite_offset = source.stat().st_size // 2
    with source.open("r+b") as handle:
        handle.seek(rewrite_offset)
        original = handle.read(1)
        handle.seek(rewrite_offset)
        handle.write(b"Z" if original != b"Z" else b"Y")
    os.utime(
        source,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000),
    )

    validation = index_module.validate_index_v2(source, index, "timeline")
    assert validation.status == index_module.INDEX_V2_SOURCE_CHANGED
    assert validation.reasons == ("CERTIFIED_SOURCE_TIMESTAMP_MISMATCH",)


def test_v2_baseline_never_certifies_rewrite_plus_append_after_deep_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b"".join(
            _json_line(event=f"EVENT-{number}", trade_id=f"BASELINE-{number}")
            for number in range(400)
        )
    )
    original_size = source.stat().st_size
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    original_deep = index_module._deep_invariant_errors
    revalidating_calls = 0

    def rewrite_after_deep(connection, handle, state, *, start_offset=0):
        nonlocal revalidating_calls
        errors = original_deep(
            connection,
            handle,
            state,
            start_offset=start_offset,
        )
        if str(state["state"]) == "REVALIDATING":
            revalidating_calls += 1
            if revalidating_calls == 2 and not errors:
                _rewrite_middle_and_append(
                    source,
                    original_size,
                    _json_line(event="LATE-APPEND", trade_id="BASELINE-LATE"),
                )
        return errors

    monkeypatch.setattr(index_module, "_deep_invariant_errors", rewrite_after_deep)
    with pytest.raises(index_module.IndexBuildError, match="source changed during V2 certification"):
        index_module.build_index_v2(
            source,
            index,
            "timeline",
            config=_config(),
            measure_memory=False,
        )

    assert index.exists()
    metadata = index_module.read_index_certification(index)
    assert metadata.certified is False
    assert metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    assert metadata.certified_watermark == 0


def test_v2_baseline_rechecks_source_after_summary_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b"".join(
            _json_line(event=f"EVENT-{number}", trade_id=f"SEAL-{number}")
            for number in range(400)
        )
    )
    original_size = source.stat().st_size
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    original_calculate = index_module.calculate_certified_summary_hash
    mutated = False

    def rewrite_inside_seal(connection, certified_watermark):
        nonlocal mutated
        result = original_calculate(connection, certified_watermark)
        if not mutated:
            mutated = True
            _rewrite_middle_and_append(
                source,
                original_size,
                _json_line(event="LATE-SEAL", trade_id="SEAL-LATE"),
            )
        return result

    monkeypatch.setattr(
        index_module,
        "calculate_certified_summary_hash",
        rewrite_inside_seal,
    )
    with pytest.raises(
        index_module.IndexBuildError,
        match=(
            "deep baseline certification failed"
            "|before V2 baseline certification commit"
        ),
    ):
        index_module.build_index_v2(
            source,
            index,
            "timeline",
            config=_config(),
            measure_memory=False,
        )

    metadata = index_module.read_index_certification(index)
    assert metadata.certified is False
    assert metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    assert metadata.certified_watermark == 0


def test_v2_catchup_never_promotes_rewrite_plus_append_after_append_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b"".join(
            _json_line(event=f"EVENT-{number}", trade_id=f"CATCHUP-{number}")
            for number in range(400)
        )
    )
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    before = index_module.read_index_certification(index)
    with source.open("ab") as handle:
        for number in range(20):
            handle.write(
                _json_line(event=f"APPEND-{number}", trade_id=f"CATCHUP-{number}")
            )
    catchup_snapshot_size = source.stat().st_size
    original_deep = index_module._deep_invariant_errors
    mutated = False

    def rewrite_after_append_proof(connection, handle, state, *, start_offset=0):
        nonlocal mutated
        errors = original_deep(
            connection,
            handle,
            state,
            start_offset=start_offset,
        )
        if start_offset == before.certified_watermark and not errors and not mutated:
            mutated = True
            _rewrite_middle_and_append(
                source,
                catchup_snapshot_size,
                _json_line(event="LATE-APPEND", trade_id="CATCHUP-LATE"),
            )
        return errors

    monkeypatch.setattr(
        index_module,
        "_deep_invariant_errors",
        rewrite_after_append_proof,
    )
    with pytest.raises(index_module.IndexBuildError, match="source changed before V2 certification"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    after = index_module.read_index_certification(index)
    assert after.certified_watermark == before.certified_watermark
    assert after.certification_kind == before.certification_kind
    validation = index_module.validate_index_v2(
        source,
        index,
        "timeline",
        snapshot_eof=before.certified_watermark,
    )
    assert validation.status == index_module.INDEX_V2_SOURCE_CHANGED
    assert validation.reasons == ("CERTIFIED_SOURCE_SIZE_MISMATCH",)


def test_v2_terminal_witness_refresh_rejects_rewrite_plus_growth(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b"".join(
            _json_line(event=f"EVENT-{number}", trade_id=f"TAIL-{number}")
            for number in range(400)
        )
    )
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    before = index_module.read_index_certification(index)
    with source.open("ab") as handle:
        handle.write(b'{"event":"PARTIAL"')
    catchup_snapshot_size = source.stat().st_size
    mutated = False

    def rewrite_before_tail_update(point: str, _context: object) -> None:
        nonlocal mutated
        if point == "before_trailing_fragment_update" and not mutated:
            mutated = True
            _rewrite_middle_and_append(source, catchup_snapshot_size, b"GROWTH")

    with pytest.raises(index_module.IndexBuildError, match="source changed during V2 READY catch-up"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            fault_injector=rewrite_before_tail_update,
            measure_memory=False,
        )

    after = index_module.read_index_certification(index)
    assert after.certified_watermark == before.certified_watermark
    assert after.certification_kind == before.certification_kind
    assert (
        index_module.validate_index_v2(
            source,
            index,
            "timeline",
            snapshot_eof=before.certified_watermark,
        ).status
        == index_module.INDEX_V2_SOURCE_CHANGED
    )


def test_v2_failed_post_certification_check_revokes_persisted_certificate(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="POST-CHECK"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    with source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="POST-CHECK"))
    mutated = False

    def append_after_certification(point: str, _context: object) -> None:
        nonlocal mutated
        if point == "before_catchup_final_validation" and not mutated:
            mutated = True
            with source.open("ab") as handle:
                handle.write(
                    _json_line(event="AFTER-CERT", trade_id="POST-CHECK")
                )

    with pytest.raises(index_module.IndexBuildError, match="final validation failed"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            fault_injector=append_after_certification,
            measure_memory=False,
        )

    state = _state(index)
    metadata = index_module.read_index_certification(index)
    assert state["state"] == "STALE"
    assert metadata.certified is False
    assert metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    assert metadata.certified_watermark == 0


def test_v2_publish_false_remains_explicitly_uncertified(tmp_path: Path) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="STAGING"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"

    report = index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        publish=False,
        measure_memory=False,
    )

    assert report.published is False
    assert report.staging_path is not None
    staging = Path(report.staging_path)
    metadata = index_module.read_index_certification(staging)
    assert metadata.certified is False
    assert metadata.certified_watermark == 0
    assert metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    with sqlite3.connect(staging) as connection:
        assert index_module.verify_certified_summary_hash(connection) is False
    validation = index_module.validate_index_v2(source, staging, "timeline", deep=True)
    assert validation.status == index_module.INDEX_V2_UNCERTIFIED
    assert validation.state == "REVALIDATING"


def test_v2_failed_deep_validation_never_creates_certification(tmp_path: Path) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="DEEP-FAIL"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    report = index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        publish=False,
        measure_memory=False,
    )
    staging = Path(str(report.staging_path))
    with sqlite3.connect(staging) as connection:
        connection.execute(
            "UPDATE segments SET records_examined_lines=0 WHERE segment_id=1"
        )
        connection.commit()

    with pytest.raises(index_module.IndexBuildError, match="deep validation failed"):
        index_module.build_index_v2(
            source,
            index,
            "timeline",
            resume=True,
            staging_path=staging,
            measure_memory=False,
        )

    metadata = index_module.read_index_certification(staging)
    assert metadata.certification_kind == index_module.CERTIFICATION_UNCERTIFIED
    assert metadata.certified_watermark == 0
    assert not index.exists()


def test_v2_catchup_extends_only_a_fully_certified_prior_watermark(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="APPEND"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    before = _state(index)
    with source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="APPEND"))
        handle.write(b'{"broken":}\n')

    report = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )

    after = _state(index)
    assert report.safe_watermark_before == int(before["safe_watermark"])
    assert report.safe_watermark_after == source.stat().st_size
    assert int(after["certified_watermark"]) == report.safe_watermark_after
    assert (
        after["certification_kind"]
        == index_module.CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND
    )
    assert bytes(after["certified_summary_hash"]) != bytes(
        before["certified_summary_hash"]
    )
    with sqlite3.connect(index) as connection:
        assert index_module.verify_certified_summary_hash(connection) is True
    assert report.final_validation_status == index_module.INDEX_V2_CERTIFIED
    assert (
        index_module.validate_index_v2(source, index, "timeline", deep=True).status
        == index_module.INDEX_V2_CERTIFIED
    )


def test_v2_catchup_never_invents_missing_prior_certification(tmp_path: Path) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="NO-PROMOTION"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    empty_anchor = hashlib.blake2b(b"", digest_size=16).digest()
    with sqlite3.connect(index) as connection:
        empty_summary_hash = index_module.calculate_certified_summary_hash(
            connection,
            0,
        )
        connection.execute(
            """
            UPDATE source_state SET certified_watermark=0,
                certified_anchor=?, certified_anchor_offset=0,
                certified_anchor_length=0, certified_summary_hash=?
            """,
            (empty_anchor, empty_summary_hash),
        )
        connection.commit()
    with source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="NO-PROMOTION"))

    report = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )

    metadata = index_module.read_index_certification(index)
    assert report.safe_watermark_after > report.safe_watermark_before
    assert metadata.safe_watermark == report.safe_watermark_after
    assert metadata.certified_watermark == 0
    assert metadata.certification_kind == index_module.CERTIFICATION_DEEP_BASELINE
    assert report.final_validation_status == index_module.INDEX_V2_UNCERTIFIED


def test_v2_terminal_fragment_refreshes_witness_without_extending_watermark(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="FRAGMENT"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    before = index_module.read_index_certification(index)
    with source.open("ab") as handle:
        handle.write(b'{"event":"PARTIAL"')

    report = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )

    after = index_module.read_index_certification(index)
    assert report.safe_watermark_after == report.safe_watermark_before
    assert after.certified_watermark == before.certified_watermark
    assert after.certification_kind == before.certification_kind
    assert after.certified_source_size == source.stat().st_size
    assert (
        index_module.validate_index_v2(
            source,
            index,
            "timeline",
            snapshot_eof=after.certified_watermark,
        ).status
        == index_module.INDEX_V2_CERTIFIED
    )
    assert (
        index_module.validate_index_v2(source, index, "timeline").status
        == index_module.INDEX_V2_UNCERTIFIED
    )
    with source.open("r+b") as handle:
        handle.truncate(after.certified_watermark)
    changed = index_module.validate_index_v2(source, index, "timeline")
    assert changed.status == index_module.INDEX_V2_SOURCE_CHANGED
    assert changed.reasons == ("SOURCE_SHRANK_BELOW_CERTIFIED_WITNESS",)


def test_v2_builder_refuses_existing_target_instead_of_overwriting_v1(
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="NO-OVERWRITE"))
    target = tmp_path / "existing.sqlite3"
    target.write_bytes(b"existing-v1-placeholder")
    original = target.read_bytes()

    with pytest.raises(index_module.IndexBuildError, match="refuses to replace"):
        index_module.build_index_v2(
            source,
            target,
            "timeline",
            config=_config(),
            measure_memory=False,
        )

    assert target.read_bytes() == original


def test_offline_cli_builds_and_deep_validates_v2_only_when_explicit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="CLI-V2"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    common = [
        "--source",
        str(source),
        "--index",
        str(index),
        "--source-id",
        "timeline",
        "--schema-v2",
    ]

    assert index_cli.main([*common, "--build"]) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["mode"] == "build"
    assert int(_state(index)["schema_version"]) == index_module.SCHEMA_VERSION_V2

    assert index_cli.main([*common, "--validate"]) == 0
    validated_shallow = json.loads(capsys.readouterr().out)
    assert validated_shallow["status"] == index_module.INDEX_V2_CERTIFIED

    assert index_cli.main([*common, "--deep-validate"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["status"] == index_module.INDEX_V2_CERTIFIED

    with source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="CLI-V2"))
    assert index_cli.main([*common, "--catch-up"]) == 0
    caught_up = json.loads(capsys.readouterr().out)
    assert caught_up["final_validation_status"] == index_module.INDEX_V2_CERTIFIED
    assert (
        _state(index)["certification_kind"]
        == index_module.CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND
    )

    assert index_cli.main([*common, "--verify-shadow"]) == 2
    rejected = json.loads(capsys.readouterr().err)
    assert "Phase B/V1" in rejected["message"]


def test_offline_cli_resumes_v2_only_with_explicit_schema_selection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(_json_line(event="OPEN", trade_id="CLI-V2-RESUME"))
    index = tmp_path / "timeline.identity-offset-v2.sqlite3"
    report = index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        publish=False,
        measure_memory=False,
    )
    staging = Path(str(report.staging_path))
    args = [
        "--source",
        str(source),
        "--index",
        str(index),
        "--source-id",
        "timeline",
        "--schema-v2",
        "--resume",
        "--staging",
        str(staging),
    ]

    assert index_cli.main(args) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["mode"] == "resume"
    assert resumed["published"] is True
    assert int(_state(index)["schema_version"]) == index_module.SCHEMA_VERSION_V2
    assert (
        index_module.validate_index_v2(source, index, "timeline").status
        == index_module.INDEX_V2_CERTIFIED
    )


def test_cli_catchup_schema_flag_is_enforced_before_any_write(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    v1_source = tmp_path / "v1.jsonl"
    v1_source.write_bytes(_json_line(event="OPEN", trade_id="CLI-V1"))
    v1_index = tmp_path / "v1.sqlite3"
    index_module.build_index(
        v1_source,
        v1_index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    with v1_source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="CLI-V1"))
    v1_before = int(_state(v1_index)["safe_watermark"])
    v1_args = [
        "--source",
        str(v1_source),
        "--index",
        str(v1_index),
        "--source-id",
        "timeline",
        "--schema-v2",
        "--catch-up",
    ]
    assert index_cli.main(v1_args) == 2
    assert "schema V2" in json.loads(capsys.readouterr().err)["message"]
    assert int(_state(v1_index)["safe_watermark"]) == v1_before

    v2_source = tmp_path / "v2.jsonl"
    v2_source.write_bytes(_json_line(event="OPEN", trade_id="CLI-V2"))
    v2_index = tmp_path / "v2.sqlite3"
    index_module.build_index_v2(
        v2_source,
        v2_index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    with v2_source.open("ab") as handle:
        handle.write(_json_line(event="CLOSE", trade_id="CLI-V2"))
    v2_before = int(_state(v2_index)["safe_watermark"])
    v2_args = [
        "--source",
        str(v2_source),
        "--index",
        str(v2_index),
        "--source-id",
        "timeline",
        "--catch-up",
    ]
    assert index_cli.main(v2_args) == 2
    assert "schema V1" in json.loads(capsys.readouterr().err)["message"]
    assert int(_state(v2_index)["safe_watermark"]) == v2_before
