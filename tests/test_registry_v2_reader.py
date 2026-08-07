from __future__ import annotations

import ast
import builtins
import copy
import inspect
import json
from pathlib import Path

import pytest

import registry_v2_reader as reader
import registry_execution_schema as schema


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_v2_reader.py"


def _row(*, execution_id="exec_00000000-0000-4000-8000-000000000001", state=schema.OPEN, **overrides):
    row = {
        "execution_id": execution_id,
        "lifecycle_id": execution_id,
        "logical_trade_id": "FALCON:FALCON15:BTCUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "owner_type": schema.CENTRAL,
        "execution_mode": schema.PAPER,
        "registry_mode": schema.PAPER,
        "lifecycle_state": state,
        "execution_provenance": {"source": "reader-test"},
        "signal_id": "signal-1",
        "decision_id": "decision-1",
        "position_side": "LONG",
        "metadata": {},
    }
    row.update(overrides)
    return row


def _live_row(execution_id="exec_00000000-0000-4000-8000-000000000002"):
    return _row(
        execution_id=execution_id,
        execution_mode=schema.LIVE,
        registry_mode=schema.REAL,
        position_side="LONG",
    )


def _document(*, open_rows=(), closed_rows=(), external_observations=None):
    open_rows = list(open_rows)
    closed_rows = list(closed_rows)
    indexes = schema.build_registry_v2_indexes(open_rows + closed_rows)
    document = {
        "schema_version": schema.SCHEMA_VERSION,
        "registry_version": schema.REGISTRY_VERSION,
        "generation": 0,
        "snapshot_id": "snapshot-1",
        "updated_at": "2026-08-07T00:00:00Z",
        "integrity": {
            "snapshot_digest": "placeholder",
            "last_committed_event_seq": 0,
            "last_committed_event_id": None,
        },
        "wal": {
            "materialized_seq": 0,
            "materialized_event_id": None,
            "materialized_request_digest": None,
            "state": "CLEAN",
        },
        "open_trades": {row["execution_id"]: row for row in open_rows},
        "closed_trades": {row["execution_id"]: row for row in closed_rows},
        "external_observations": external_observations or {},
        "indexes": reader.project_indexes_for_json(indexes),
        "operation_ledger": {},
        "migration": {
            "phase": "V1_READ_ONLY",
            "source_snapshot_digest": None,
            "journal_cursor": 0,
        },
    }
    _refresh_digest(document)
    return document


def _refresh_digest(document):
    document["integrity"]["snapshot_digest"] = reader.compute_registry_v2_snapshot_digest(document)


def _write_json(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _source_tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_001_valid_empty_v2_snapshot(tmp_path):
    path = tmp_path / "empty.json"
    _write_json(path, _document())
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.status == reader.REGISTRY_V2_READ_OK
    assert result.open_count == result.closed_count == result.external_count == 0
    assert result.indexes_rebuilt is True
    assert result.index_match is True


def test_002_valid_one_paper_open_row(tmp_path):
    path = tmp_path / "paper.json"
    _write_json(path, _document(open_rows=[_row()]))
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.open_count == 1


def test_003_valid_one_live_structural_open_row(tmp_path):
    path = tmp_path / "live.json"
    _write_json(path, _document(open_rows=[_live_row()]))
    result = reader.read_registry_v2(path)
    assert result.ok is True


def test_004_valid_closed_row(tmp_path):
    path = tmp_path / "closed.json"
    row = _row(state=schema.CLOSED_RECONCILED)
    _write_json(path, _document(closed_rows=[row]))
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.closed_count == 1


def test_005_missing_file_does_not_create(tmp_path):
    path = tmp_path / "missing.json"
    result = reader.read_registry_v2(path)
    assert result.status == reader.REGISTRY_V2_FILE_NOT_FOUND
    assert path.exists() is False


def test_006_invalid_json(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_FILE_INVALID_JSON


def test_007_top_level_list_rejected(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_008_schema_version_unsupported(tmp_path):
    path = tmp_path / "schema.json"
    document = _document()
    document["schema_version"] = "OTHER"
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_SCHEMA_VERSION_UNSUPPORTED


def test_009_registry_version_unsupported(tmp_path):
    path = tmp_path / "registry.json"
    document = _document()
    document["registry_version"] = "9.9.9"
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_REGISTRY_VERSION_UNSUPPORTED


@pytest.mark.parametrize("generation", [-1, "0", True])
def test_010_to_012_invalid_generation_values(tmp_path, generation):
    path = tmp_path / "generation.json"
    document = _document()
    document["generation"] = generation
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_GENERATION_INVALID


def test_013_snapshot_id_missing(tmp_path):
    path = tmp_path / "snapshot-id.json"
    document = _document()
    document.pop("snapshot_id")
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_014_integrity_missing(tmp_path):
    path = tmp_path / "integrity.json"
    document = _document()
    document.pop("integrity")
    path.write_text(json.dumps(document), encoding="utf-8")
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_015_snapshot_digest_valid(tmp_path):
    path = tmp_path / "digest.json"
    document = _document()
    _write_json(path, document)
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.snapshot_digest == document["integrity"]["snapshot_digest"]


def test_016_snapshot_digest_invalid(tmp_path):
    path = tmp_path / "bad-digest.json"
    document = _document()
    document["integrity"]["snapshot_digest"] = "0" * 64
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_SNAPSHOT_DIGEST_INVALID


def test_017_digest_helper_does_not_mutate_input():
    document = _document()
    before = copy.deepcopy(document)
    reader.compute_registry_v2_snapshot_digest(document)
    assert document == before


def test_018_canonical_json_digest_is_deterministic():
    first = _document()
    second = copy.deepcopy(first)
    second = {key: second[key] for key in reversed(tuple(second))}
    assert reader.compute_registry_v2_snapshot_digest(first) == reader.compute_registry_v2_snapshot_digest(second)


@pytest.mark.parametrize("field", ["open_trades", "closed_trades", "external_observations"])
def test_019_to_021_collections_must_be_mappings(tmp_path, field):
    path = tmp_path / f"{field}.json"
    document = _document()
    document[field] = []
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_022_execution_key_must_match_row_id(tmp_path):
    path = tmp_path / "key-mismatch.json"
    document = _document(open_rows=[_row()])
    row = document["open_trades"].pop("exec_00000000-0000-4000-8000-000000000001")
    document["open_trades"]["other-execution"] = row
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_ROW_INVALID


def test_023_execution_in_open_and_closed_is_rejected(tmp_path):
    path = tmp_path / "duplicate-collections.json"
    row = _row()
    document = _document(open_rows=[row])
    document["closed_trades"][row["execution_id"]] = dict(row, lifecycle_state=schema.CLOSED_RECONCILED)
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_ROW_INVALID


def test_024_invalid_row_rejected(tmp_path):
    path = tmp_path / "invalid-row.json"
    row = _row(side="INVALID")
    document = _document()
    document["open_trades"][row["execution_id"]] = row
    _refresh_digest(document)
    _write_json(path, document)
    result = reader.read_registry_v2(path)
    assert result.status == reader.REGISTRY_V2_ROW_INVALID
    assert any("side" in error for error in result.errors)


def test_025_closed_state_in_open_rejected(tmp_path):
    path = tmp_path / "closed-open.json"
    document = _document(open_rows=[_row(state=schema.CLOSED_RECONCILED)])
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_ROW_INVALID


def test_026_open_state_in_closed_rejected(tmp_path):
    path = tmp_path / "open-closed.json"
    document = _document(closed_rows=[_row(state=schema.OPEN)])
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_ROW_INVALID


def test_027_lifecycle_conflict_propagates(tmp_path):
    path = tmp_path / "lifecycle-conflict.json"
    row = _row(lifecycle_id="exec_00000000-0000-4000-8000-000000000099")
    document = _document()
    document["open_trades"][row["execution_id"]] = row
    _refresh_digest(document)
    _write_json(path, document)
    result = reader.read_registry_v2(path)
    assert result.status == reader.REGISTRY_V2_ROW_INVALID
    assert any("execution_id_lifecycle_id_mismatch" in error for error in result.errors)


def test_028_two_same_logical_ids_coexist(tmp_path):
    path = tmp_path / "same-logical.json"
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    _write_json(path, _document(open_rows=rows))
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.open_count == 2


def test_029_rebuilt_indexes_match_persisted_indexes(tmp_path):
    path = tmp_path / "indexes.json"
    _write_json(path, _document(open_rows=[_row()]))
    result = reader.read_registry_v2(path)
    assert result.indexes_rebuilt is True
    assert result.index_match is True


def test_030_index_mismatch_is_diagnosed(tmp_path):
    path = tmp_path / "index-mismatch.json"
    document = _document(open_rows=[_row()])
    document["indexes"]["by_execution_id"]["extra"] = "extra"
    _refresh_digest(document)
    _write_json(path, document)
    result = reader.read_registry_v2(path)
    assert result.status == reader.REGISTRY_V2_INDEX_MISMATCH
    assert result.index_match is False


def test_031_by_execution_index_projection():
    row = _row()
    indexes = schema.build_registry_v2_indexes([row])
    projected = reader.project_indexes_for_json(indexes)
    assert projected["by_execution_id"][row["execution_id"]] == row["execution_id"]


def test_032_by_logical_index_projection():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    projected = reader.project_indexes_for_json(schema.build_registry_v2_indexes(rows))
    assert set(projected["by_logical_trade_id"][rows[0]["logical_trade_id"]]) == {row["execution_id"] for row in rows}


def test_033_composite_index_json_projection():
    projected = reader.project_indexes_for_json(schema.build_registry_v2_indexes([_row()]))
    assert "FALCON|BTCUSDT" in projected["by_bot_symbol"]
    assert "FALCON|BTCUSDT|LONG" in projected["by_bot_symbol_side"]


def test_034_by_signal_allows_duplicates():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    projected = reader.project_indexes_for_json(schema.build_registry_v2_indexes(rows))
    assert len(projected["by_signal_id"]["signal-1"]) == 2


def test_035_by_decision_allows_duplicates():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    projected = reader.project_indexes_for_json(schema.build_registry_v2_indexes(rows))
    assert len(projected["by_decision_id"]["decision-1"]) == 2


def test_036_reader_does_not_alter_document(tmp_path):
    path = tmp_path / "unchanged.json"
    document = _document(open_rows=[_row()])
    before = copy.deepcopy(document)
    _write_json(path, document)
    reader.read_registry_v2(path)
    assert document == before


def test_037_reader_does_not_change_file(tmp_path):
    path = tmp_path / "read-only.json"
    _write_json(path, _document())
    before = path.read_bytes()
    reader.read_registry_v2(path)
    assert path.read_bytes() == before


def test_038_no_mutating_path_calls_in_reader():
    forbidden = {"write", "write_text", "write_bytes", "mkdir", "touch", "rename", "replace", "unlink", "chmod", "fsync"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(_source_tree()))


def test_039_no_os_environ():
    tree = _source_tree()
    assert not any(isinstance(node, ast.Name) and node.id == "environ" for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr == "environ" for node in ast.walk(tree))


def test_040_no_runtime_imports():
    roots = set()
    for node in ast.walk(_source_tree()):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    assert roots <= {"__future__", "copy", "hashlib", "json", "collections", "dataclasses", "pathlib", "typing", "registry_execution_schema"}
    assert roots.isdisjoint({"bots", "broker", "flask", "main", "redis", "requests", "subprocess", "trade_registry"})


def test_041_no_network_capability():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source
    assert "redis" not in source


def test_042_python_311_syntax_compatible():
    assert isinstance(ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 11)), ast.Module)


def test_043_read_requires_explicit_path():
    assert inspect.signature(reader.read_registry_v2).parameters["path"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        reader.read_registry_v2()


def test_044_no_production_default_path_literals():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for literal in ("trade_registry.json", "registry_v2.json", "/data/", "/opt/render/"):
        assert literal not in source


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_045_to_047_non_finite_json_rejected(tmp_path, literal):
    path = tmp_path / "non-finite.json"
    path.write_text(f'{{"value": {literal}}}', encoding="utf-8")
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_FILE_INVALID_JSON


def test_048_wal_missing_field_rejected(tmp_path):
    path = tmp_path / "wal-missing.json"
    document = _document()
    document["wal"].pop("state")
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_049_wal_wrong_type_rejected(tmp_path):
    path = tmp_path / "wal-type.json"
    document = _document()
    document["wal"] = []
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_050_wal_clean_is_valid(tmp_path):
    path = tmp_path / "wal-clean.json"
    _write_json(path, _document())
    assert reader.read_registry_v2(path).ok is True


def test_051_invalid_materialized_seq_rejected(tmp_path):
    path = tmp_path / "wal-seq.json"
    document = _document()
    document["wal"]["materialized_seq"] = -1
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_DOCUMENT_INVALID


def test_052_duplicate_execution_id_across_collections_rejected(tmp_path):
    path = tmp_path / "duplicate-id.json"
    row = _row()
    document = _document(open_rows=[row])
    document["closed_trades"][row["execution_id"]] = dict(row, lifecycle_state=schema.CLOSED_PROVISIONAL)
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).ok is False


def test_053_persisted_index_extra_execution_detected(tmp_path):
    path = tmp_path / "extra-index-id.json"
    document = _document()
    document["indexes"]["by_logical_trade_id"]["EXTRA:SETUP:SYMBOL:LONG"] = ["extra"]
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_INDEX_MISMATCH


def test_054_persisted_index_missing_execution_detected(tmp_path):
    path = tmp_path / "missing-index-id.json"
    document = _document(open_rows=[_row()])
    document["indexes"]["by_execution_id"] = {}
    _refresh_digest(document)
    _write_json(path, document)
    assert reader.read_registry_v2(path).status == reader.REGISTRY_V2_INDEX_MISMATCH


def test_055_empty_persisted_indexes_match_empty_row_store(tmp_path):
    path = tmp_path / "empty-indexes.json"
    _write_json(path, _document())
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert result.index_match is True


def test_056_result_dataclass_is_frozen(tmp_path):
    path = tmp_path / "frozen.json"
    _write_json(path, _document())
    result = reader.read_registry_v2(path)
    with pytest.raises(AttributeError):
        result.ok = False


def test_reader_does_not_call_mutating_builtins(monkeypatch, tmp_path):
    path = tmp_path / "builtins.json"
    _write_json(path, _document())
    before = path.read_bytes()
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("builtins.open must not be used")))
    result = reader.read_registry_v2(path)
    assert result.ok is True
    assert path.read_bytes() == before
