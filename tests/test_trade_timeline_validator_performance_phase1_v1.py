from __future__ import annotations

import copy
import json
import math
import tracemalloc
from pathlib import Path

import live_trade_snapshot
import trade_timeline_validator as validator


TRADE_ID = "FALCON:PERFORMANCE-PHASE1:BTCUSDT:LONG"


def _reader(path: Path):
    metadata = validator._new_reader_metadata()
    rows = list(validator._read_path(path, metadata))
    return rows, metadata


def _sources():
    registry = {
        "open_trades": {
            TRADE_ID: {
                "trade_id": TRADE_ID,
                "registry_record_id": "REG-PERF-1",
                "lifecycle_id": "LIFE-PERF-1",
                "status": "OPEN",
                "bot": "FALCON",
                "setup": "PERFORMANCE-PHASE1",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "mode": "PAPER",
                "opened_at": "2026-08-14T12:00:00Z",
            }
        },
        "closed_trades": [],
    }
    timeline = [
        {
            "trade_id": TRADE_ID,
            "lifecycle_id": "LIFE-PERF-1",
            "event_type": "BROKER_ACK",
            "event_id": "ACK-1",
            "occurred_at": "2026-08-14T12:00:02Z",
        },
        {
            "trade_id": TRADE_ID,
            "lifecycle_id": "LIFE-PERF-1",
            "event_type": "POSITION_OPEN",
            "event_id": "OPEN-1",
            "occurred_at": "2026-08-14T12:00:01Z",
        },
        {
            "trade_id": TRADE_ID,
            "lifecycle_id": "LIFE-PERF-1",
            "event_type": "POSITION_OPEN",
            "event_id": "OPEN-2",
            "occurred_at": "2026-08-14T12:00:03Z",
        },
    ]
    return {"registry": registry, "timeline": timeline}


def _normalized_report(report):
    normalized = copy.deepcopy(report)
    normalized.pop("generated_at", None)
    normalized.get("summary", {}).pop("duration_ms", None)
    return normalized


def test_each_examined_jsonl_record_is_deserialized_once(monkeypatch, tmp_path):
    source = tmp_path / "timeline.jsonl"
    source.write_bytes(
        b'{"trade_id":"T-1","timestamp":"2026-08-14T12:00:00Z"}\r\n'
        b'{broken}\r\n'
        b'42\r\n'
        + '{"trade_id":"T-2","label":"açúcar","timestamp":"2026-08-14T12:00:02Z"}\r\n'.encode("utf-8")
        + b'{"trade_id":"INCOMPLETE"'
    )
    monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", 17)
    real_loads = validator.json.loads
    calls = 0

    def counted_loads(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_loads(*args, **kwargs)

    monkeypatch.setattr(validator.json, "loads", counted_loads)
    rows, metadata = _reader(source)

    assert [row["trade_id"] for row in rows] == ["T-1", "T-2"]
    assert metadata["records_examined"] == 5
    assert metadata["valid_lines"] == 3
    assert metadata["invalid_lines"] == 2
    assert metadata["lines_scanned"] == 5
    assert metadata["time_range_scanned"] == {
        "oldest": "2026-08-14T12:00:00+00:00",
        "newest": "2026-08-14T12:00:02+00:00",
    }
    assert calls == metadata["records_examined"]
    print(json.dumps({
        "legacy_json_loads_calls": metadata["records_examined"] * 2,
        "optimized_json_loads_calls": calls,
        "json_loads_reduction_pct": 50.0,
    }, sort_keys=True))


def test_incremental_replay_keeps_one_open_and_one_physical_read_per_block(monkeypatch, tmp_path):
    source = tmp_path / "history_events.jsonl"
    rows = [
        {"trade_id": f"T-{index}", "padding": "x" * 53}
        for index in range(23)
    ]
    source.write_bytes(b"".join(json.dumps(row).encode("utf-8") + b"\n" for row in rows))
    monkeypatch.setattr(validator, "JSONL_BLOCK_BYTES", 97)
    real_open = Path.open
    opens = 0
    reads = 0

    class ReadProbe:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def read(self, *args, **kwargs):
            nonlocal reads
            reads += 1
            return self.handle.read(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self.handle, name)

    def tracked_open(path, *args, **kwargs):
        nonlocal opens
        handle = real_open(path, *args, **kwargs)
        if path == source:
            opens += 1
            return ReadProbe(handle)
        return handle

    monkeypatch.setattr(Path, "open", tracked_open)
    found, metadata = _reader(source)

    assert found == rows
    assert opens == 1
    assert reads == math.ceil(source.stat().st_size / validator.JSONL_BLOCK_BYTES)
    assert metadata["bytes_scanned"] == source.stat().st_size
    assert metadata["source_size_bytes"] == source.stat().st_size
    print(json.dumps({
        "bytes_scanned": metadata["bytes_scanned"],
        "file_opens": opens,
        "physical_reads": reads,
    }, sort_keys=True))


def test_reader_has_no_page_sized_contiguous_replay_copy():
    source = Path(validator.__file__).read_text(encoding="utf-8")
    reader_source = source[source.index("def _read_path("):source.index("def identity_resolution_metadata(")]

    assert 'payload = b"".join(reversed(scan_chunks))' not in reader_source
    examine_source = reader_source[
        reader_source.index("def examine_line("):
        reader_source.index("while offset > region_start")
    ]
    assert "json.loads" not in examine_source


def _legacy_contiguous_copy_peak(path: Path) -> int:
    tracemalloc.start()
    with path.open("rb") as handle:
        page_end = path.stat().st_size
        region_start = max(0, page_end - validator.JSONL_MAX_BYTES)
        offset = page_end
        chunks = []
        while offset > region_start:
            block_start = max(region_start, offset - validator.JSONL_BLOCK_BYTES)
            handle.seek(block_start)
            chunks.append(handle.read(offset - block_start))
            offset = block_start
        payload = b"".join(reversed(chunks))
        assert len(payload) == min(path.stat().st_size, validator.JSONL_MAX_BYTES)
        _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_large_fixture_reduces_peak_memory_without_changing_byte_budget(tmp_path):
    source = tmp_path / "timeline.jsonl"
    invalid_line = b'{"broken":"' + (b"x" * (72 * 1024)) + b"\n"
    target_size = validator.JSONL_MAX_BYTES + (2 * 1024 * 1024)
    with source.open("wb") as handle:
        while handle.tell() <= target_size:
            handle.write(invalid_line)

    legacy_peak = _legacy_contiguous_copy_peak(source)
    tracemalloc.start()
    rows, metadata = _reader(source)
    _current, optimized_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert source.stat().st_size > validator.JSONL_MAX_BYTES
    assert rows == []
    assert metadata["bytes_scanned"] == validator.JSONL_MAX_BYTES
    assert metadata["stop_reason"] == "BYTE_BUDGET"
    assert optimized_peak < legacy_peak * 0.75
    print(json.dumps({
        "fixture_bytes": source.stat().st_size,
        "bytes_scanned": metadata["bytes_scanned"],
        "legacy_peak_bytes": legacy_peak,
        "optimized_peak_bytes": optimized_peak,
        "peak_reduction_pct": round((1 - optimized_peak / legacy_peak) * 100, 2),
    }, sort_keys=True))


def test_evidence_bundle_preserves_timeline_contract_and_is_not_public():
    sources = _sources()
    direct = validator.validate_trade_timeline(TRADE_ID, sources=copy.deepcopy(sources))
    bundle = validator.collect_evidence_bundle(TRADE_ID, sources=copy.deepcopy(sources))
    reused = validator.validate_trade_timeline(TRADE_ID, evidence_bundle=bundle)

    assert _normalized_report(reused) == _normalized_report(direct)
    assert isinstance(bundle, validator.EvidenceBundle)
    assert bundle.trade_id == TRADE_ID
    assert bundle.target_identity.trade_id == TRADE_ID
    assert bundle.registry_resolution["selection_basis"] == "unique_trade_id"
    assert bundle.source_fingerprints["timeline"] == {
        "source_size_bytes": 0,
        "snapshot_eof": 0,
    }
    assert isinstance(bundle.records["timeline"], tuple)

    snapshot = live_trade_snapshot.build_live_trade_snapshot(
        TRADE_ID,
        sources=copy.deepcopy(sources),
        now_epoch=1770000000.0,
    )
    snapshot_validator_sources = {name: [] for name in validator.COMPONENTS}
    snapshot_validator_sources.update(copy.deepcopy(sources))
    snapshot_timeline_reference = validator.validate_trade_timeline(
        TRADE_ID,
        sources=snapshot_validator_sources,
    )
    serialized = json.dumps(snapshot, sort_keys=True, default=str)
    assert "EvidenceBundle" not in serialized
    assert "_correlation_context" not in serialized
    assert snapshot["timeline_validation"]["events_found"] == snapshot_timeline_reference["events_found"]
    assert snapshot["timeline_validation"]["duplicate_events"] == snapshot_timeline_reference["events_duplicated"]
    assert snapshot["timeline_validation"]["divergences"] == snapshot_timeline_reference["divergences"]
    assert snapshot["timeline_validation"]["coverage"] == snapshot_timeline_reference["coverage"]
    assert snapshot["identity"]["selection_basis"] == snapshot_timeline_reference["identity"]["selection_basis"]
    assert snapshot["component_status"]["broker"]["status"] == "UNAVAILABLE"
    assert snapshot["timeline_validation"]["component_status"]["broker"] == "NO_EVIDENCE"
    assert snapshot["timeline_validation"]["coverage"]["sources"]["broker"] == {
        "evidence_found": False,
        "coverage_complete": True,
        "partial": False,
        "conclusive": True,
        "bytes_scanned": 0,
        "records_examined": 0,
        "direction": "IN_MEMORY",
        "time_range_scanned": {"oldest": None, "newest": None},
        "stop_reason": "IN_MEMORY_COMPLETE",
        "source_size_bytes": 0,
        "snapshot_eof": 0,
        "evidence_status": "COMPLETE_NO_EVIDENCE",
    }


def test_snapshot_correlates_and_extracts_each_source_only_once(monkeypatch):
    correlate_calls = 0
    extraction_calls = 0
    real_correlate = validator.correlate_source_records
    real_extract = validator._events_from_record

    def counted_correlate(*args, **kwargs):
        nonlocal correlate_calls
        correlate_calls += 1
        return real_correlate(*args, **kwargs)

    def counted_extract(*args, **kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        return real_extract(*args, **kwargs)

    monkeypatch.setattr(validator, "correlate_source_records", counted_correlate)
    monkeypatch.setattr(validator, "_events_from_record", counted_extract)

    result = live_trade_snapshot.build_live_trade_snapshot(
        TRADE_ID,
        sources=_sources(),
        now_epoch=1770000000.0,
    )

    # The legacy Snapshot path made these two correlations and then nine more
    # while rebuilding validator_sources. The bundle reuses both resolved rows.
    legacy_correlate_calls = 2 + len(validator.COMPONENTS)
    assert result["ok"] is True
    assert correlate_calls == 2
    assert extraction_calls == 4
    assert correlate_calls < legacy_correlate_calls * 0.25
    print(json.dumps({
        "legacy_correlate_calls": legacy_correlate_calls,
        "optimized_correlate_calls": correlate_calls,
        "correlation_reduction_pct": round(
            (1 - correlate_calls / legacy_correlate_calls) * 100,
            2,
        ),
    }, sort_keys=True))


def test_default_timeline_readers_are_not_correlated_again(monkeypatch, tmp_path):
    registry = _sources()["registry"]
    (tmp_path / "trade_registry.json").write_text(
        json.dumps(registry),
        encoding="utf-8",
    )
    (tmp_path / "timeline.jsonl").write_bytes(
        b"".join(
            json.dumps(row).encode("utf-8") + b"\n"
            for row in _sources()["timeline"][:2]
        )
    )
    sources = validator.build_default_sources({
        "CENTRAL_DATA_DIR": str(tmp_path),
        "TRADE_LIFECYCLE_SHADOW_DATA_DIR": str(tmp_path),
    })
    real_correlate = validator.correlate_source_records
    calls = 0

    def counted_correlate(*args, **kwargs):
        nonlocal calls
        calls += 1
        return real_correlate(*args, **kwargs)

    monkeypatch.setattr(validator, "correlate_source_records", counted_correlate)
    report = validator.validate_trade_timeline(TRADE_ID, sources=sources)

    legacy_calls = 3 + len(validator.COMPONENTS)
    assert report["components"]["registry"]["records"] == 1
    assert report["components"]["timeline"]["records"] == 2
    assert calls == 3
    assert calls < legacy_calls * 0.3
    print(json.dumps({
        "route": "trade_timeline",
        "legacy_correlate_calls": legacy_calls,
        "optimized_correlate_calls": calls,
        "correlation_reduction_pct": round((1 - calls / legacy_calls) * 100, 2),
    }, sort_keys=True))
