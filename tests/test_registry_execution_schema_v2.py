from __future__ import annotations

import ast
import builtins
import copy
from pathlib import Path

import pytest

import registry_execution_schema as schema
from registry_execution_identity import REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_execution_schema.py"


def _row(**overrides):
    execution_id = overrides.pop("execution_id", "exec_00000000-0000-4000-8000-000000000001")
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
        "lifecycle_state": schema.OPEN,
        "execution_provenance": {"source": "unit-test"},
        "signal_id": "signal-1",
        "decision_id": "decision-1",
        "position_side": "LONG",
        "metadata": {},
    }
    row.update(overrides)
    return row


def _live_row(**overrides):
    row = _row(
        execution_id="exec_00000000-0000-4000-8000-000000000002",
        execution_mode=schema.LIVE,
        registry_mode=schema.REAL,
    )
    row.update(overrides)
    return row


def _ids(index):
    return set(index)


def test_001_valid_paper_row():
    result = schema.validate_registry_execution_row(_row())
    assert result.ok is True
    assert result.status == schema.REGISTRY_SCHEMA_VALID
    assert result.schema_version == schema.SCHEMA_VERSION


def test_002_valid_live_structural_row():
    result = schema.validate_registry_execution_row(_live_row())
    assert result.ok is True


@pytest.mark.parametrize("position_side", ["LONG", "SHORT", "BOTH", "NET", "UNKNOWN"])
def test_position_side_contract_accepts_all_structural_values(position_side):
    result = schema.validate_registry_execution_row(_live_row(position_side=position_side))
    assert result.ok is True


def test_invalid_position_side_is_rejected():
    result = schema.validate_registry_execution_row(_live_row(position_side="INVALID"))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "position_side" in result.errors


@pytest.mark.parametrize("side", ["BOTH", "NET"])
def test_economic_side_does_not_accept_position_side_values(side):
    result = schema.validate_registry_execution_row(_live_row(side=side))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "side" in result.errors


@pytest.mark.parametrize("registry_mode", [schema.REAL, schema.UNKNOWN, schema.CONFLICT])
def test_live_registry_mode_coherence_accepts_allowed_modes(registry_mode):
    result = schema.validate_registry_execution_row(_live_row(registry_mode=registry_mode))
    assert result.ok is True


@pytest.mark.parametrize("registry_mode", [schema.PAPER, schema.VERIFY, schema.SYNC_ONLY])
def test_live_registry_mode_coherence_rejects_disallowed_modes(registry_mode):
    result = schema.validate_registry_execution_row(_live_row(registry_mode=registry_mode))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "registry_mode" in result.errors


@pytest.mark.parametrize("registry_mode", [schema.REAL, schema.UNKNOWN, schema.CONFLICT])
def test_paper_registry_mode_coherence_rejects_non_paper_modes(registry_mode):
    result = schema.validate_registry_execution_row(_row(registry_mode=registry_mode))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "registry_mode" in result.errors


def test_paper_registry_mode_coherence_accepts_paper():
    result = schema.validate_registry_execution_row(_row(registry_mode=schema.PAPER))
    assert result.ok is True


def test_003_missing_execution_id():
    row = _row()
    row.pop("execution_id")
    assert schema.validate_registry_execution_row(row).status == schema.REGISTRY_SCHEMA_REQUIRED_FIELD_MISSING


def test_004_lifecycle_differs_from_execution():
    result = schema.validate_registry_execution_row(_row(lifecycle_id="exec_00000000-0000-4000-8000-000000000099"))
    assert result.status == REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT


@pytest.mark.parametrize("field", ["logical_trade_id", "bot", "setup", "symbol"])
def test_005_to_008_missing_identity_fields(field):
    row = _row()
    row.pop(field)
    assert schema.validate_registry_execution_row(row).status == schema.REGISTRY_SCHEMA_REQUIRED_FIELD_MISSING


def test_009_invalid_side():
    result = schema.validate_registry_execution_row(_row(side="SIDEWAYS"))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "side" in result.errors


def test_010_invalid_owner():
    result = schema.validate_registry_execution_row(_row(owner_type="ROBOT"))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID


def test_011_manual_external_rejected_as_execution_row():
    result = schema.validate_registry_execution_row(_row(owner_type=schema.MANUAL_EXTERNAL))
    assert result.status == schema.REGISTRY_SCHEMA_EXTERNAL_NOT_EXECUTION


def test_012_verify_rejected_as_execution_row():
    result = schema.validate_registry_execution_row(_row(execution_mode=schema.VERIFY))
    assert result.status == schema.REGISTRY_SCHEMA_VERIFY_NOT_EXECUTION


@pytest.mark.parametrize("field", ["signal_id", "decision_id", "position_side"])
def test_013_to_015_live_required_fields(field):
    row = _live_row()
    row[field] = None
    result = schema.validate_registry_execution_row(row)
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert field in result.errors


def test_016_paper_legacy_missing_signal_decision_requires_explicit_marker():
    row = _row(signal_id=None, decision_id=None, legacy_missing=True)
    result = schema.validate_registry_execution_row(row)
    assert result.ok is True
    assert schema.LEGACY_MISSING in result.warnings


def test_017_metadata_canonical_identity_conflict_rejected():
    result = schema.validate_registry_execution_row(_row(metadata={"identity": {"execution_id": "other"}}))
    assert result.status == schema.REGISTRY_SCHEMA_METADATA_CONFLICT


def test_018_build_logical_trade_id():
    assert schema.build_logical_trade_id(" falcon ", "falcon15", "btcusdt", "long") == "FALCON:FALCON15:BTCUSDT:LONG"


def test_019_logical_trade_id_canonical_format():
    assert schema.is_logical_trade_id("FALCON:FALCON15:BTCUSDT:LONG") is True
    assert schema.is_logical_trade_id("falcon:FALCON15:BTCUSDT:LONG") is False


def test_020_logical_trade_id_is_not_execution_id():
    assert schema.is_logical_trade_id("exec_00000000-0000-4000-8000-000000000001") is False


def test_021_index_builder_execution_id():
    row = _row()
    indexes = schema.build_registry_v2_indexes([row])
    assert indexes["by_execution_id"][row["execution_id"]] is row
    assert indexes["by_lifecycle_id_alias"][row["lifecycle_id"]] == row["execution_id"]


def test_022_index_logical_id_contains_two_executions():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    indexes = schema.build_registry_v2_indexes(rows)
    assert set(indexes["by_logical_trade_id"][rows[0]["logical_trade_id"]]) == {
        rows[0]["execution_id"], rows[1]["execution_id"]
    }


def test_023_two_same_bot_setup_symbol_side_coexist_in_index():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    indexes = schema.build_registry_v2_indexes(rows)
    key = ("FALCON", "BTCUSDT", "LONG")
    assert set(indexes["by_bot_symbol_side"][key]) == {row["execution_id"] for row in rows}


def test_024_duplicate_execution_id_fails():
    with pytest.raises(schema.RegistrySchemaIndexConflict) as error:
        schema.build_registry_v2_indexes([_row(), _row()])
    assert error.value.status == "REGISTRY_SCHEMA_EXECUTION_ID_CONFLICT"


def test_025_lifecycle_alias_divergence_fails():
    row = _row(lifecycle_id="exec_00000000-0000-4000-8000-000000000099")
    with pytest.raises(schema.RegistrySchemaIndexConflict) as error:
        schema.build_registry_v2_indexes([row])
    assert error.value.status == REGISTRY_EXECUTION_LIFECYCLE_ID_CONFLICT


def test_026_by_bot_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert set(schema.build_registry_v2_indexes(rows)["by_bot"]["FALCON"]) == {r["execution_id"] for r in rows}


def test_027_by_symbol_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert set(schema.build_registry_v2_indexes(rows)["by_symbol"]["BTCUSDT"]) == {r["execution_id"] for r in rows}


def test_028_by_bot_symbol_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert set(schema.build_registry_v2_indexes(rows)["by_bot_symbol"]["FALCON", "BTCUSDT"]) == {r["execution_id"] for r in rows}


def test_029_by_bot_symbol_side_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert set(schema.build_registry_v2_indexes(rows)["by_bot_symbol_side"]["FALCON", "BTCUSDT", "LONG"]) == {r["execution_id"] for r in rows}


def test_030_by_owner_type_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert set(schema.build_registry_v2_indexes(rows)["by_owner_type"][schema.CENTRAL]) == {r["execution_id"] for r in rows}


def test_031_by_state_groups():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003", lifecycle_state=schema.PARTIALLY_CLOSED)]
    indexes = schema.build_registry_v2_indexes(rows)
    assert indexes["by_state"][schema.OPEN] == (rows[0]["execution_id"],)
    assert indexes["by_state"][schema.PARTIALLY_CLOSED] == (rows[1]["execution_id"],)


def test_032_by_signal_id_allows_duplicates():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert len(schema.build_registry_v2_indexes(rows)["by_signal_id"]["signal-1"]) == 2


def test_033_by_decision_id_allows_duplicates():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    assert len(schema.build_registry_v2_indexes(rows)["by_decision_id"]["decision-1"]) == 2


def test_034_input_rows_unchanged_after_validation():
    row = _row()
    before = copy.deepcopy(row)
    schema.validate_registry_execution_row(row)
    assert row == before


def test_035_input_rows_unchanged_after_index_build():
    rows = [_row(), _row(execution_id="exec_00000000-0000-4000-8000-000000000003")]
    before = copy.deepcopy(rows)
    schema.build_registry_v2_indexes(rows)
    assert rows == before


def test_036_no_file_io(monkeypatch):
    def forbidden_open(*args, **kwargs):
        raise AssertionError("V2.1 schema must not open files")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    assert schema.validate_registry_execution_row(_row()).ok is True
    assert schema.build_registry_v2_indexes([_row()])


def test_037_no_environment_access():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.Name) and node.id == "environ" for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr == "environ" for node in ast.walk(tree))


def test_038_no_runtime_imports():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    assert roots <= {"__future__", "collections", "dataclasses", "typing", "registry_execution_identity"}
    assert roots.isdisjoint({"bots", "broker", "flask", "main", "redis", "requests", "subprocess", "trade_registry"})


def test_039_no_persistence_capabilities():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    forbidden_calls = {"open", "connect", "create", "request", "get", "post", "put", "delete"}
    forbidden_attributes = {"environ", "write", "write_text", "write_bytes", "read_text", "read_bytes"}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden_attributes for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Name) and node.id in {"subprocess", "threading", "requests"} for node in ast.walk(tree))


def test_040_python_311_compatible_syntax_features():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 11))
    assert isinstance(tree, ast.Module)


def test_result_envelope_is_frozen_and_has_no_timestamp():
    result = schema.validate_registry_execution_row(_row())
    with pytest.raises(AttributeError):
        result.ok = False
    assert not hasattr(result, "timestamp")


def test_custom_legacy_marker_is_supported_without_mutation():
    row = _row(signal_id=None, decision_id=None, legacy_missing_marker="ADAPTER_LEGACY")
    result = schema.validate_registry_execution_row(row, legacy_missing_marker="ADAPTER_LEGACY")
    assert result.ok is True
    assert "legacy_missing_marker" in row


def test_non_mapping_row_fails_closed():
    result = schema.validate_registry_execution_row([("execution_id", "x")])
    assert result.ok is False
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID


def test_invalid_logical_trade_id_does_not_infer_from_row_fields():
    row = _row(logical_trade_id="exec_00000000-0000-4000-8000-000000000001")
    result = schema.validate_registry_execution_row(row)
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "logical_trade_id" in result.errors


def test_indexes_preserve_input_order_for_non_unique_keys():
    first = _row()
    second = _row(execution_id="exec_00000000-0000-4000-8000-000000000003")
    indexes = schema.build_registry_v2_indexes([first, second])
    assert indexes["by_logical_trade_id"][first["logical_trade_id"]] == (first["execution_id"], second["execution_id"])


def test_paper_missing_signal_or_decision_without_marker_is_invalid():
    result = schema.validate_registry_execution_row(_row(signal_id=None))
    assert result.status == schema.REGISTRY_SCHEMA_FIELD_INVALID
    assert "signal_id" in result.errors


def test_index_builder_does_not_choose_first_or_latest():
    rows = [
        _row(),
        _row(execution_id="exec_00000000-0000-4000-8000-000000000003"),
        _row(execution_id="exec_00000000-0000-4000-8000-000000000004"),
    ]
    ids = schema.build_registry_v2_indexes(rows)["by_bot"]["FALCON"]
    assert ids == tuple(row["execution_id"] for row in rows)
