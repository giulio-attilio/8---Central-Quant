from __future__ import annotations

import json
import socket
import sqlite3
import uuid
from pathlib import Path
from typing import Callable

import pytest

import trade_evidence_identity_offset_index_v1 as index_module
from trade_evidence_identity_offset_source_envelope_v1 import MAX_SQLITE_FETCH_BATCH


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in completeness V2 tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _line(**values: object) -> bytes:
    return (
        json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _config() -> index_module.BuildConfig:
    return index_module.BuildConfig(
        block_bytes=64,
        segment_target_bytes=256,
        batch_bytes=8 * 1024,
        batch_lines=32,
        max_line_bytes=2 * 1024 * 1024,
        anchor_bytes=64,
        busy_timeout_ms=25,
    )


def _paths(tmp_path: Path, name: str = "timeline") -> tuple[Path, Path]:
    root = tmp_path / name
    root.mkdir(parents=True)
    return root / "timeline.jsonl", root / "timeline.identity-offset-v2.sqlite3"


def _build_v2(
    tmp_path: Path,
    raw: bytes,
    *,
    name: str = "timeline",
) -> tuple[Path, Path]:
    source, index = _paths(tmp_path, name)
    source.write_bytes(raw)
    index_module.build_index_v2(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )
    return source, index


def _state(index: Path) -> dict[str, object]:
    connection = sqlite3.connect(index)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM source_state WHERE singleton_id=1"
        ).fetchone()
        assert row is not None
        return dict(row)
    finally:
        connection.close()


def _target_identity_id(connection: sqlite3.Connection, value: str = "T") -> int:
    row = connection.execute(
        "SELECT identity_id FROM identities WHERE identity_value=?",
        (value,),
    ).fetchone()
    assert row is not None
    return int(row[0])


def _record_at(connection: sqlite3.Connection, ordinal: int) -> tuple[int, int]:
    row = connection.execute(
        """
        SELECT record_id, start_offset FROM records
        ORDER BY start_offset LIMIT 1 OFFSET ?
        """,
        (ordinal,),
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def _remove_posting(connection: sqlite3.Connection) -> None:
    connection.execute(
        "DELETE FROM postings WHERE identity_id=?",
        (_target_identity_id(connection),),
    )


def _remove_identity_and_postings(connection: sqlite3.Connection) -> None:
    identity_id = _target_identity_id(connection)
    connection.execute("DELETE FROM postings WHERE identity_id=?", (identity_id,))
    connection.execute("DELETE FROM identities WHERE identity_id=?", (identity_id,))


def _remove_record_and_postings(connection: sqlite3.Connection) -> None:
    record_id, start_offset = _record_at(connection, 0)
    connection.execute(
        "DELETE FROM postings WHERE record_id=? AND start_offset=?",
        (record_id, start_offset),
    )
    connection.execute("DELETE FROM records WHERE record_id=?", (record_id,))


def _swap_identity_ownership(connection: sqlite3.Connection) -> None:
    target = _target_identity_id(connection, "T")
    other = _target_identity_id(connection, "O")
    connection.execute(
        "UPDATE identities SET identity_value='__TEMP__' WHERE identity_id=?",
        (target,),
    )
    connection.execute(
        "UPDATE identities SET identity_value='T' WHERE identity_id=?",
        (other,),
    )
    connection.execute(
        "UPDATE identities SET identity_value='O' WHERE identity_id=?",
        (target,),
    )


def _move_posting_to_wrong_offset(connection: sqlite3.Connection) -> None:
    identity_id = _target_identity_id(connection)
    wrong_record_id, wrong_offset = _record_at(connection, 1)
    connection.execute("DELETE FROM postings WHERE identity_id=?", (identity_id,))
    connection.execute(
        """
        INSERT INTO postings(identity_id, start_offset, record_id)
        VALUES (?, ?, ?)
        """,
        (identity_id, wrong_offset, wrong_record_id),
    )


def _add_extra_posting(connection: sqlite3.Connection) -> None:
    identity_id = _target_identity_id(connection)
    wrong_record_id, wrong_offset = _record_at(connection, 1)
    connection.execute(
        """
        INSERT INTO postings(identity_id, start_offset, record_id)
        VALUES (?, ?, ?)
        """,
        (identity_id, wrong_offset, wrong_record_id),
    )


def _alter_identity_class(connection: sqlite3.Connection) -> None:
    identity_id = _target_identity_id(connection)
    current = str(
        connection.execute(
            "SELECT identity_class FROM identities WHERE identity_id=?",
            (identity_id,),
        ).fetchone()[0]
    )
    changed = "SECONDARY" if current == "STRONG" else "STRONG"
    connection.execute(
        "UPDATE identities SET identity_class=? WHERE identity_id=?",
        (changed, identity_id),
    )


def _add_orphan_identity(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO identities(
            identity_type, identity_value, identity_group, identity_class
        ) VALUES ('trade_id', 'ORPHAN-IDENTITY', 'TRADE', 'STRONG')
        """
    )


def _add_record_outside_watermark(connection: sqlite3.Connection) -> None:
    watermark = int(
        connection.execute("SELECT safe_watermark FROM source_state").fetchone()[0]
    )
    segment_id = int(
        connection.execute(
            "SELECT segment_id FROM segments ORDER BY segment_id LIMIT 1"
        ).fetchone()[0]
    )
    line_number = int(
        connection.execute("SELECT MAX(line_number) FROM records").fetchone()[0]
    ) + 1
    connection.execute(
        """
        INSERT INTO records(
            segment_id, line_number, start_offset, byte_length,
            terminator_length, event_type, record_hash
        ) VALUES (?, ?, ?, 1, 1, 'OUTSIDE', ?)
        """,
        (segment_id, line_number, watermark, b"x" * 16),
    )


def _add_posting_outside_watermark(connection: sqlite3.Connection) -> None:
    # The seal must reject the row independently of FK enforcement.  A corrupt
    # SQLite writer can disable foreign_keys, as this isolated adversarial
    # fixture does.
    connection.execute("PRAGMA foreign_keys=OFF")
    watermark = int(
        connection.execute("SELECT safe_watermark FROM source_state").fetchone()[0]
    )
    connection.execute(
        """
        INSERT INTO postings(identity_id, start_offset, record_id)
        VALUES (?, ?, 999999999)
        """,
        (_target_identity_id(connection), watermark),
    )


Tamper = Callable[[sqlite3.Connection], None]


def test_serving_seal_fetch_batch_preserves_the_c1_hard_ceiling() -> None:
    assert index_module.SERVING_COMPLETENESS_FETCH_BATCH <= MAX_SQLITE_FETCH_BATCH


def test_full_certification_requires_matching_physical_and_serving_lineage(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_uuid="LINEAGE", event_type="OPEN"),
        name="lineage",
    )
    with sqlite3.connect(index) as connection:
        connection.execute(
            "UPDATE source_state SET serving_certification_kind=? "
            "WHERE singleton_id=1",
            (index_module.CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND,),
        )

    certification = index_module.read_index_certification(index)

    assert certification.physical_certified is True
    assert certification.serving_certified is True
    assert certification.full_certified is False
    assert certification.certification_state == index_module.CERTIFICATION_STATE_PHYSICAL
    validation = index_module.validate_index_v2(
        source,
        index,
        "timeline",
    )
    assert validation.status == index_module.INDEX_V2_UNCERTIFIED
    assert validation.reasons == ("CERTIFICATION_PAIR_MISMATCH",)


def test_v2_baseline_persists_deterministic_full_completeness_seal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN", client_order_id="C-1")
        + _line(trade_id="T", event_type="FILL", fill_id="F-1"),
    )
    metadata = index_module.read_index_certification(index)

    assert metadata.lifecycle_state == "READY"
    assert metadata.physical_certified is True
    assert metadata.serving_certified is True
    assert metadata.full_certified is True
    assert metadata.certification_state == index_module.CERTIFICATION_STATE_FULL
    assert metadata.certified_watermark == source.stat().st_size
    assert metadata.serving_certified_watermark == source.stat().st_size
    assert metadata.serving_record_count == 2
    assert metadata.serving_identity_count >= 3
    assert metadata.serving_posting_count >= 4

    connection = sqlite3.connect(index)
    try:
        first = index_module.calculate_serving_completeness_seal(
            connection,
            metadata.serving_certified_watermark,
        )
        monkeypatch.setattr(index_module, "SERVING_COMPLETENESS_FETCH_BATCH", 1)
        second = index_module.calculate_serving_completeness_seal(
            connection,
            metadata.serving_certified_watermark,
        )
        with pytest.raises(
            index_module.IndexValidationError,
            match="records extend beyond",
        ):
            index_module.calculate_serving_completeness_seal(connection, 0)
        physical_hash = bytes(
            connection.execute(
                "SELECT certified_summary_hash FROM source_state"
            ).fetchone()[0]
        )
        assert index_module.verify_serving_completeness_seal(connection) is True
    finally:
        connection.close()

    assert first == second
    assert len(first.digest) * 8 >= 128
    assert first.digest != physical_hash
    assert first.contract_version == index_module.SERVING_COMPLETENESS_CONTRACT_VERSION


def test_v1_default_schema_and_certification_remain_unchanged(tmp_path: Path) -> None:
    source, index = _paths(tmp_path, "v1")
    source.write_bytes(_line(trade_id="T", event_type="OPEN"))
    index_module.build_index(
        source,
        index,
        "timeline",
        config=_config(),
        measure_memory=False,
    )

    assert index_module.SCHEMA_VERSION == index_module.SCHEMA_VERSION_V1
    assert index_module.INDEX_VERSION == index_module.INDEX_VERSION_V1
    metadata = index_module.read_index_certification(index)
    assert metadata.schema_version == index_module.SCHEMA_VERSION_V1
    assert metadata.serving_certified is False
    assert metadata.full_certified is False
    assert metadata.certification_state == index_module.CERTIFICATION_STATE_NONE

    connection = sqlite3.connect(index)
    try:
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(source_state)")
        }
        assert "serving_completeness_hash" not in columns
        assert index_module.verify_serving_completeness_seal(connection) is False
    finally:
        connection.close()


@pytest.mark.parametrize(
    "tamper",
    [
        _remove_posting,
        _remove_identity_and_postings,
        _remove_record_and_postings,
        _swap_identity_ownership,
        _move_posting_to_wrong_offset,
        _add_extra_posting,
        _alter_identity_class,
        _add_orphan_identity,
        _add_record_outside_watermark,
        _add_posting_outside_watermark,
    ],
    ids=[
        "remove-posting",
        "remove-identity-postings",
        "remove-record-postings",
        "swap-ownership",
        "move-posting",
        "add-posting",
        "strong-secondary",
        "orphan-identity",
        "record-outside-watermark",
        "posting-outside-watermark",
    ],
)
def test_serving_seal_detects_adversarial_table_tamper(
    tmp_path: Path,
    tamper: Tamper,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN")
        + _line(trade_id="O", event_type="OPEN"),
    )
    before = _state(index)
    connection = sqlite3.connect(index)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tamper(connection)
        connection.commit()
    finally:
        connection.close()

    connection = sqlite3.connect(index)
    try:
        assert index_module.verify_certified_summary_hash(connection) is True
        assert index_module.verify_serving_completeness_seal(connection) is False
    finally:
        connection.close()
    metadata = index_module.read_index_certification(index)
    assert metadata.physical_certified is True
    assert metadata.serving_certified is False
    assert metadata.full_certified is False
    assert metadata.certification_state == index_module.CERTIFICATION_STATE_PHYSICAL
    assert bytes(_state(index)["certified_summary_hash"]) == bytes(
        before["certified_summary_hash"]
    )
    validation = index_module.validate_index_v2(source, index, "timeline")
    assert validation.status == index_module.INDEX_V2_CORRUPT
    assert any("SERVING_COMPLETENESS_SEAL_MISMATCH" in reason for reason in validation.reasons)


@pytest.mark.parametrize(
    "sql,parameters",
    [
        ("UPDATE source_state SET generation_uuid=?", (str(uuid.uuid4()),)),
        ("UPDATE source_state SET identity_contract_hash=?", ("changed",)),
        ("UPDATE source_state SET normalized_path_hash=?", ("changed",)),
        ("UPDATE source_state SET dev=?", ("999999",)),
        ("UPDATE source_state SET source_id=?", ("history_manager",)),
        ("UPDATE source_state SET serving_contract_version=?", ("changed",)),
        ("UPDATE source_state SET serving_certified_watermark=0", ()),
    ],
    ids=[
        "generation",
        "identity-contract",
        "source-path-hash",
        "source-device",
        "source-id",
        "serving-contract",
        "watermark",
    ],
)
def test_serving_seal_binds_generation_contract_source_and_watermark(
    tmp_path: Path,
    sql: str,
    parameters: tuple[object, ...],
) -> None:
    _source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
    )
    connection = sqlite3.connect(index)
    try:
        connection.execute(sql, parameters)
        connection.commit()
        assert index_module.verify_serving_completeness_seal(connection) is False
    finally:
        connection.close()


def test_baseline_physical_and_serving_certificates_commit_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, index = _paths(tmp_path, "baseline-atomic")
    source.write_bytes(_line(trade_id="T", event_type="OPEN"))
    original = index_module.calculate_serving_completeness_seal
    injected = False

    def fail_inside_certification(connection, watermark):
        nonlocal injected
        seal = original(connection, watermark)
        if connection.in_transaction and not injected:
            injected = True
            raise RuntimeError("serving seal commit fault")
        return seal

    monkeypatch.setattr(
        index_module,
        "calculate_serving_completeness_seal",
        fail_inside_certification,
    )
    with pytest.raises(RuntimeError, match="serving seal commit fault"):
        index_module.build_index_v2(
            source,
            index,
            "timeline",
            config=_config(),
            measure_memory=False,
        )

    state = _state(index)
    assert injected is True
    assert state["state"] == "REVALIDATING"
    assert state["certification_kind"] == index_module.CERTIFICATION_UNCERTIFIED
    assert state["serving_certification_kind"] == index_module.CERTIFICATION_UNCERTIFIED
    assert int(state["certified_watermark"]) == 0
    assert int(state["serving_certified_watermark"]) == 0


def test_baseline_rejects_physical_summary_mutation_after_deep_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, index = _paths(tmp_path, "baseline-physical-toctou")
    source.write_bytes(
        _line(trade_id="T", event_type="OPEN")
        + _line(trade_id="T", event_type="FILL", fill_id="F-1")
    )
    original = index_module.calculate_serving_completeness_seal
    autocommit_calls = 0

    def mutate_segment_after_second_serving_witness(connection, watermark):
        nonlocal autocommit_calls
        seal = original(connection, watermark)
        if not connection.in_transaction:
            autocommit_calls += 1
            if autocommit_calls == 2:
                connection.execute(
                    "UPDATE segments SET segment_hash=zeroblob(16)"
                )
        return seal

    monkeypatch.setattr(
        index_module,
        "calculate_serving_completeness_seal",
        mutate_segment_after_second_serving_witness,
    )
    with pytest.raises(
        index_module.IndexBuildError,
        match="physical summary changed during V2 deep baseline certification",
    ):
        index_module.build_index_v2(
            source,
            index,
            "timeline",
            config=_config(),
            measure_memory=False,
        )

    state = _state(index)
    metadata = index_module.read_index_certification(index)
    assert autocommit_calls == 2
    assert state["state"] == "REVALIDATING"
    assert state["certification_kind"] == index_module.CERTIFICATION_UNCERTIFIED
    assert state["serving_certification_kind"] == index_module.CERTIFICATION_UNCERTIFIED
    assert metadata.full_certified is False


def test_proven_append_extends_physical_and_serving_certificate_together(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
    )
    before = _state(index)
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE", fill_id="F-1"))

    report = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )
    after = _state(index)
    metadata = index_module.read_index_certification(index)

    assert report.ok is True
    assert report.final_validation_status == index_module.INDEX_V2_CERTIFIED
    assert metadata.full_certified is True
    assert metadata.certification_state == index_module.CERTIFICATION_STATE_FULL
    assert metadata.certified_watermark == report.safe_watermark_after
    assert metadata.serving_certified_watermark == report.safe_watermark_after
    assert (
        metadata.certification_kind
        == index_module.CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND
    )
    assert (
        metadata.serving_certification_kind
        == index_module.CERTIFICATION_DEEP_BASELINE_PLUS_PROVEN_APPEND
    )
    assert bytes(after["certified_summary_hash"]) != bytes(
        before["certified_summary_hash"]
    )
    assert bytes(after["serving_completeness_hash"]) != bytes(
        before["serving_completeness_hash"]
    )
    assert metadata.serving_record_count == 2


def test_catchup_certification_fault_never_publishes_one_new_seal_without_the_other(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
    )
    before = _state(index)
    before_watermark = int(before["safe_watermark"])
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE"))
    original = index_module.calculate_serving_completeness_seal
    injected = False

    def fail_new_seal_inside_transaction(connection, watermark):
        nonlocal injected
        seal = original(connection, watermark)
        if connection.in_transaction and int(watermark) > before_watermark and not injected:
            injected = True
            raise RuntimeError("catchup serving seal commit fault")
        return seal

    monkeypatch.setattr(
        index_module,
        "calculate_serving_completeness_seal",
        fail_new_seal_inside_transaction,
    )
    with pytest.raises(RuntimeError, match="catchup serving seal commit fault"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    after = _state(index)
    assert injected is True
    assert int(after["safe_watermark"]) > before_watermark
    for field in (
        "certified_watermark",
        "certified_summary_hash",
        "certification_kind",
        "serving_certified_watermark",
        "serving_completeness_hash",
        "serving_certification_kind",
        "serving_record_count",
        "serving_identity_count",
        "serving_posting_count",
    ):
        assert after[field] == before[field]

    monkeypatch.setattr(
        index_module,
        "calculate_serving_completeness_seal",
        original,
    )
    recovered = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )
    recovered_state = _state(index)
    recovered_metadata = index_module.read_index_certification(index)

    assert recovered.mode == "CERTIFICATION_RECOVERY"
    assert recovered.processed_append_bytes == 0
    assert recovered_metadata.full_certified is True
    assert recovered_metadata.certified_watermark == recovered.safe_watermark_after
    assert (
        recovered_metadata.serving_certified_watermark
        == recovered.safe_watermark_after
    )
    with sqlite3.connect(index) as connection:
        record_counts = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT start_offset) FROM records"
        ).fetchone()
        posting_counts = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT identity_id || ':' || start_offset || ':' || record_id) "
            "FROM postings"
        ).fetchone()
    assert record_counts == (2, 2)
    assert posting_counts is not None
    assert int(posting_counts[0]) == int(posting_counts[1])
    assert int(recovered_state["safe_watermark"]) == source.stat().st_size


def test_catchup_full_pair_advances_only_after_precommit_postvalidation(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
        name="postvalidation-boundary",
    )
    before = _state(index)
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE", fill_id="F-2"))

    observed_points: list[str] = []

    def fail_after_postvalidation(
        point: str,
        _context: object,
    ) -> None:
        observed_points.append(point)
        if point == "after_catchup_post_validation_before_certification":
            raise RuntimeError("postvalidation boundary fault")

    with pytest.raises(RuntimeError, match="postvalidation boundary fault"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
            fault_injector=fail_after_postvalidation,
        )

    faulted = _state(index)
    assert "after_catchup_post_validation_before_certification" in observed_points
    assert int(faulted["safe_watermark"]) > int(before["safe_watermark"])
    for field in (
        "certified_watermark",
        "certified_summary_hash",
        "certification_kind",
        "serving_certified_watermark",
        "serving_completeness_hash",
        "serving_certification_kind",
        "serving_record_count",
        "serving_identity_count",
        "serving_posting_count",
    ):
        assert faulted[field] == before[field]

    recovered = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )
    metadata = index_module.read_index_certification(index)
    assert recovered.mode == "CERTIFICATION_RECOVERY"
    assert metadata.full_certified is True
    assert metadata.certified_watermark == source.stat().st_size
    assert metadata.serving_certified_watermark == source.stat().st_size


def test_catchup_rejects_certified_prefix_physical_summary_toctou(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
        name="catchup-prefix-physical-toctou",
    )
    before = _state(index)
    before_watermark = int(before["certified_watermark"])
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE", fill_id="F-2"))

    original = index_module.calculate_serving_completeness_seal
    injected = False

    def mutate_certified_prefix_after_first_full_serving_witness(
        connection: sqlite3.Connection,
        watermark: int,
    ) -> object:
        nonlocal injected
        seal = original(connection, watermark)
        if (
            not connection.in_transaction
            and int(watermark) > before_watermark
            and not injected
        ):
            injected = True
            connection.execute(
                """
                UPDATE segments SET segment_hash=zeroblob(16)
                WHERE end_offset <= ?
                """,
                (before_watermark,),
            )
        return seal

    monkeypatch.setattr(
        index_module,
        "calculate_serving_completeness_seal",
        mutate_certified_prefix_after_first_full_serving_witness,
    )
    with pytest.raises(
        index_module.IndexBuildError,
        match="prior physical summary changed before append deep validation",
    ):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    after = _state(index)
    metadata = index_module.read_index_certification(index)
    assert injected is True
    assert int(after["safe_watermark"]) == source.stat().st_size
    for field in (
        "certified_watermark",
        "certified_summary_hash",
        "certification_kind",
        "serving_certified_watermark",
        "serving_completeness_hash",
        "serving_certification_kind",
        "serving_record_count",
        "serving_identity_count",
        "serving_posting_count",
    ):
        assert after[field] == before[field]
    assert metadata.full_certified is False


def test_catchup_retry_after_durable_batch_recovers_without_duplicates(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="INITIAL", event_type="OPEN"),
        name="durable-batch-recovery",
    )
    certified_before = int(_state(index)["certified_watermark"])
    with source.open("ab") as handle:
        for number in range(40):
            handle.write(
                _line(
                    trade_id=f"APPEND-{number}",
                    event_type="UPDATE",
                )
            )

    faulted = False

    def fail_after_first_durable_batch(point: str, _context: object) -> None:
        nonlocal faulted
        if point == "after_batch_commit" and not faulted:
            faulted = True
            raise RuntimeError("durable batch fault")

    with pytest.raises(RuntimeError, match="durable batch fault"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
            fault_injector=fail_after_first_durable_batch,
        )
    lagged = _state(index)
    assert faulted is True
    assert int(lagged["safe_watermark"]) > certified_before
    assert int(lagged["safe_watermark"]) < source.stat().st_size
    assert int(lagged["certified_watermark"]) == certified_before
    assert int(lagged["serving_certified_watermark"]) == certified_before

    recovered = index_module.catch_up_index(
        source,
        index,
        "timeline",
        measure_memory=False,
    )
    metadata = index_module.read_index_certification(index)
    with sqlite3.connect(index) as connection:
        counts = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT start_offset) FROM records"
        ).fetchone()

    assert recovered.mode == "CERTIFICATION_RECOVERY"
    assert recovered.processed_append_bytes > 0
    assert metadata.full_certified is True
    assert metadata.certified_watermark == source.stat().st_size
    assert metadata.serving_certified_watermark == source.stat().st_size
    assert counts == (41, 41)


def test_catchup_recovery_rejects_certified_prefix_tamper_before_writing(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
        name="recovery-prefix-tamper",
    )
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE"))

    def fail_after_postvalidation(point: str, _context: object) -> None:
        if point == "after_catchup_post_validation_before_certification":
            raise RuntimeError("leave recoverable lag")

    with pytest.raises(RuntimeError, match="leave recoverable lag"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
            fault_injector=fail_after_postvalidation,
        )
    lagged_state = _state(index)
    with sqlite3.connect(index) as connection:
        before_records = int(
            connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        )
        _alter_identity_class(connection)

    with pytest.raises(
        index_module.IndexBuildError,
        match="SERVING_COMPLETENESS_PREFIX_MISMATCH",
    ):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    rejected_state = _state(index)
    with sqlite3.connect(index) as connection:
        after_records = int(
            connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        )
    assert rejected_state["safe_watermark"] == lagged_state["safe_watermark"]
    assert after_records == before_records


def test_catchup_recovery_deeply_rejects_tamper_in_uncertified_lag(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
        name="recovery-lag-tamper",
    )
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE"))

    def fail_after_postvalidation(point: str, _context: object) -> None:
        if point == "after_catchup_post_validation_before_certification":
            raise RuntimeError("leave recoverable lag")

    with pytest.raises(RuntimeError, match="leave recoverable lag"):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
            fault_injector=fail_after_postvalidation,
        )
    lagged_state = _state(index)
    with sqlite3.connect(index) as connection:
        record_id, _offset = _record_at(connection, 1)
        connection.execute(
            "UPDATE records SET event_type='TAMPERED' WHERE record_id=?",
            (record_id,),
        )

    with pytest.raises(
        index_module.IndexBuildError,
        match="RECOVERY_DEEP_PROOF_FAILED:.*RECORD_METADATA_MISMATCH",
    ):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    assert _state(index)["safe_watermark"] == lagged_state["safe_watermark"]


def test_catchup_rejects_tampered_serving_prefix_before_first_append_write(
    tmp_path: Path,
) -> None:
    source, index = _build_v2(
        tmp_path,
        _line(trade_id="T", event_type="OPEN"),
    )
    before_watermark = int(_state(index)["safe_watermark"])
    connection = sqlite3.connect(index)
    try:
        _alter_identity_class(connection)
        connection.commit()
    finally:
        connection.close()
    with source.open("ab") as handle:
        handle.write(_line(trade_id="T", event_type="CLOSE"))

    with pytest.raises(
        index_module.IndexBuildError,
        match="SERVING_COMPLETENESS_SEAL_MISMATCH",
    ):
        index_module.catch_up_index(
            source,
            index,
            "timeline",
            measure_memory=False,
        )

    assert int(_state(index)["safe_watermark"]) == before_watermark
