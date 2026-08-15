from __future__ import annotations

import hashlib
import json
import socket

import pytest

import trade_evidence_physical_window_contract_v1 as contract
import trade_timeline_validator as validator


EXPECTED_CONTRACT_HASH = (
    "07ef4c66d690d0aaa53802c44b354137ada555e89670f9891e730af447ef52d8"
)


@pytest.fixture(autouse=True)
def _deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden in physical contract tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_contract_hash_is_canonical_stable_and_detached():
    canonical = contract.PHYSICAL_CONTRACT_CANONICAL_JSON

    assert contract.PHYSICAL_CONTRACT_HASH == EXPECTED_CONTRACT_HASH
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == EXPECTED_CONTRACT_HASH
    assert canonical == json.dumps(
        json.loads(canonical),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )

    detached = contract.physical_contract_document()
    detached["budgets"]["bytes"] = 1
    assert contract.physical_contract_document()["budgets"]["bytes"] == 64 * 1024 * 1024


def test_contract_constants_match_the_authoritative_legacy_reader():
    assert contract.BYTE_BUDGET == validator.JSONL_MAX_BYTES == 64 * 1024 * 1024
    assert contract.RECORD_BUDGET == validator.JSONL_MAX_VALID_LINES == 100_000
    assert contract.BLOCK_BYTES == validator.JSONL_BLOCK_BYTES == 64 * 1024
    assert contract.CURSOR_CONTRACT_VERSION == validator.JSONL_CURSOR_VERSION == 1
    assert contract.TIMESTAMP_KEYS == validator.TIMESTAMP_KEYS


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        0,
        1_700_000_000,
        1_700_000_000_000,
        "1700000000",
        "2026-08-15T12:34:56Z",
        "15/08/2026 12:34:56",
        "15/08/2026 12:34",
        "2026-08-15 12:34:56",
        "not-a-timestamp",
    ],
)
def test_timestamp_parser_has_exact_legacy_semantics(value):
    assert contract.parse_timestamp(value) == validator._parse_timestamp(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_timestamp_exception_type_matches_legacy(value):
    with pytest.raises((ValueError, OverflowError, OSError)) as legacy_error:
        validator._parse_timestamp(value)
    with pytest.raises(type(legacy_error.value)):
        contract.parse_timestamp(value)


def test_first_timestamp_walk_and_lexical_range_match_legacy():
    records = [
        {"outer": [{"timestamp": "2026-08-15T00:00:02Z"}]},
        {"occurred_at": "not-a-timestamp", "timestamp": "2020-01-01T00:00:00Z"},
        {"created_at": "2026-08-15T00:00:01Z"},
        {"timestamp": "   ", "created_at": "2026-08-15T00:00:00Z"},
    ]

    expected = {"oldest": None, "newest": None}
    for record in records:
        validator._update_scanned_time({"time_range_scanned": expected}, record)

    assert contract.first_timestamp(records[0]) == validator._first_timestamp(records[0])
    assert contract.timestamp_range(records) == expected
    assert expected == {
        "oldest": "2026-08-15T00:00:01+00:00",
        "newest": "not-a-timestamp",
    }


@pytest.mark.parametrize(
    ("raw", "newline_terminated", "expected"),
    [
        (b" \t\r\n", True, {"blank": True, "nonblank": False}),
        (
            b'{"timestamp":"2026-08-15T00:00:00Z"}\n',
            True,
            {"valid_json": True, "mapping": True, "records_examined": 1},
        ),
        (b"42\r\n", True, {"valid_json": True, "nonmapping_json": True}),
        (b"null\n", True, {"valid_json": True, "nonmapping_json": True}),
        (b"[1,2]", False, {"valid_json": True, "nonmapping_json": True}),
        (b"{broken}\n", True, {"invalid_json": True, "invalid_lines": 1}),
        (b"\xff\n", True, {"invalid_utf8": True, "invalid_lines": 1}),
        (b'{"terminal":true}', False, {"valid_json": True, "mapping": True}),
    ],
)
def test_physical_line_classification_covers_legacy_line_kinds(
    raw,
    newline_terminated,
    expected,
):
    result = contract.classify_physical_line(
        raw,
        newline_terminated=newline_terminated,
    )

    for field, value in expected.items():
        assert getattr(result, field) == value
    counts = result.summary_counts()
    assert (
        counts["blank_lines"]
        + counts["valid_json_lines"]
        + counts["invalid_json_lines"]
        + counts["invalid_utf8_lines"]
        + counts["oversized_barrier_lines"]
        == 1
    )


def test_oversized_barrier_is_never_parsed_as_a_fragment():
    result = contract.classify_physical_line(None, oversized=True)

    assert result.oversized_barrier is True
    assert result.nonblank is False
    assert result.records_examined == result.valid_lines == result.invalid_lines == 0
    assert result.value is None


def test_classification_aggregate_matches_legacy_reader_metadata(tmp_path):
    source = tmp_path / "timeline.jsonl"
    physical_lines = [
        b" \t\r\n",
        b'{"timestamp":"2026-08-15T00:00:02Z"}\n',
        b"{broken}\r\n",
        b"\xff\n",
        b"42\n",
        b"[1,2]\n",
        b'{"timestamp":"not-a-timestamp"}\n',
        b'{"timestamp":"2026-08-15T00:00:01Z"}',
    ]
    source.write_bytes(b"".join(physical_lines))

    metadata = validator._new_reader_metadata()
    rows = list(validator._read_path(source, metadata))
    classifications = [
        contract.classify_physical_line(
            raw,
            newline_terminated=raw.endswith(b"\n"),
        )
        for raw in physical_lines
    ]

    assert metadata["lines_scanned"] == len(classifications)
    assert metadata["records_examined"] == sum(
        item.records_examined for item in classifications
    )
    assert metadata["valid_lines"] == sum(item.valid_lines for item in classifications)
    assert metadata["invalid_lines"] == sum(
        item.invalid_lines for item in classifications
    )
    assert metadata["time_range_scanned"] == contract.timestamp_range(
        item.value for item in classifications if item.mapping
    )
    assert rows == [item.value for item in classifications if item.mapping]


def test_cursor_encoding_and_decoding_are_byte_for_byte_legacy_compatible(tmp_path):
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(b"{}\n")
    file_stat = source.stat()

    expected = validator._encode_scan_cursor(
        source,
        file_stat,
        file_stat.st_size,
        2,
        oversized_line=True,
        coverage_tainted=False,
    )
    actual = contract.encode_scan_cursor(
        source,
        file_stat,
        file_stat.st_size,
        2,
        oversized_line=True,
        coverage_tainted=False,
    )

    assert actual == expected
    assert contract.decode_scan_cursor(actual) == validator._decode_scan_cursor(expected)
    assert contract.path_fingerprint(source) == validator._path_fingerprint(source)
    assert contract.cursor_targets_path(contract.decode_scan_cursor(actual), source) is True
    assert contract.decode_scan_cursor(actual)["tainted"] is True


def test_legacy_validator_wrappers_keep_cursor_and_timestamp_seams_monkeypatchable(
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(b"{}\n")
    file_stat = source.stat()

    monkeypatch.setattr(validator, "JSONL_CURSOR_VERSION", 7)
    cursor = validator._encode_scan_cursor(
        source,
        file_stat,
        file_stat.st_size,
        0,
    )
    assert validator._decode_scan_cursor(cursor)["v"] == 7
    with pytest.raises(ValueError, match="invalid scan cursor"):
        contract.decode_scan_cursor(cursor)

    monkeypatch.setattr(validator, "TIMESTAMP_KEYS", ("custom_timestamp",))
    record = {"custom_timestamp": "2026-08-15T00:00:00Z"}
    assert validator._first_timestamp(record) == (
        1_786_752_000.0,
        "2026-08-15T00:00:00+00:00",
    )
    metadata = validator._new_reader_metadata()
    validator._update_scanned_time(metadata, record)
    assert metadata["time_range_scanned"] == {
        "oldest": "2026-08-15T00:00:00+00:00",
        "newest": "2026-08-15T00:00:00+00:00",
    }


@pytest.mark.parametrize(
    "token",
    ["", "not-a-cursor", "x" * (contract.CURSOR_MAX_CHARS + 1)],
)
def test_invalid_cursor_rejection_matches_legacy(token):
    with pytest.raises(ValueError, match="invalid scan cursor"):
        contract.decode_scan_cursor(token)
    with pytest.raises(ValueError, match="invalid scan cursor"):
        validator._decode_scan_cursor(token)
