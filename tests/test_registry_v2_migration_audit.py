from __future__ import annotations

import ast
import copy
import inspect
import json
from pathlib import Path

import pytest

import registry_v2_migration_audit as audit


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_v2_migration_audit.py"


def _row(**overrides):
    row = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
    }
    row.update(overrides)
    return row


def _with_consistent_trade_id(row):
    consistent = dict(row)
    consistent["trade_id"] = ":".join(
        str(consistent[field]).strip().upper()
        for field in ("bot", "setup", "symbol", "side")
    )
    return consistent


def _v1_document(*, open_trades=None, closed_trades=None, extra=None):
    document = {
        "open_trades": {} if open_trades is None else open_trades,
        "closed_trades": [] if closed_trades is None else closed_trades,
    }
    if extra:
        document.update(extra)
    return document


def _write(path, document):
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _audit(path, document):
    _write(path, document)
    return audit.audit_registry_v1_for_v2(path)


def _record(result, index=0):
    return result.records[index]


def _source_tree():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_001_empty_v1_registry(tmp_path):
    result = _audit(tmp_path / "empty.json", _v1_document())
    assert result.ok is True
    assert result.status == audit.MIGRATION_AUDIT_OK
    assert result.total_records == 0


def test_002_open_dict_logical_only(tmp_path):
    result = _audit(tmp_path / "open.json", _v1_document(open_trades={"legacy-key": _row()}))
    record = _record(result)
    assert record.classification == audit.LEGACY_LOGICAL_ONLY
    assert record.recommendation == audit.ARCHIVE_READ_ONLY


def test_003_closed_list_logical_only(tmp_path):
    result = _audit(tmp_path / "closed.json", _v1_document(closed_trades=[_row()]))
    assert _record(result).source_locator == "closed_trades[0]"
    assert _record(result).classification == audit.LEGACY_LOGICAL_ONLY


def test_004_strong_lifecycle_proposes_same_id(tmp_path):
    result = _audit(tmp_path / "lifecycle.json", _v1_document(open_trades={"k": _row(lifecycle_id="legacy-life-1")}))
    record = _record(result)
    assert record.classification == audit.STRONG_LIFECYCLE_ID
    assert record.proposed_execution_id == "legacy-life-1"
    assert record.identity_source == "LEGACY_LIFECYCLE_ID"


def test_005_lifecycle_top_level_and_metadata_same(tmp_path):
    row = _row(lifecycle_id="legacy-life-1", metadata={"lifecycle_id": "legacy-life-1"})
    assert _record(_audit(tmp_path / "same.json", _v1_document(open_trades={"k": row}))).classification == audit.STRONG_LIFECYCLE_ID


def test_006_lifecycle_aliases_divergent_conflict(tmp_path):
    row = _row(lifecycle_id="legacy-life-1", metadata={"lifecycle_id": "legacy-life-2"})
    record = _record(_audit(tmp_path / "conflict.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.IDENTITY_CONFLICT
    assert "alias_conflict:lifecycle_id" in record.errors


@pytest.mark.parametrize("field,value", [
    ("client_order_id", "client-1"),
    ("broker_order_id", "broker-1"),
])
def test_007_to_008_strong_partial_without_lifecycle(tmp_path, field, value):
    record = _record(_audit(tmp_path / f"{field}.json", _v1_document(open_trades={"k": _row(**{field: value})})))
    assert record.classification == audit.STRONG_IDENTITY_PARTIAL
    assert record.recommendation == audit.ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION


def test_009_client_and_broker_without_lifecycle_partial(tmp_path):
    row = _row(client_order_id="client-1", broker_order_id="broker-1")
    record = _record(_audit(tmp_path / "client-broker.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.STRONG_IDENTITY_PARTIAL
    assert record.proposed_execution_id is None


def test_010_fill_id_without_lifecycle_partial(tmp_path):
    row = _row(fills=[{"fill_id": "fill-1"}])
    record = _record(_audit(tmp_path / "fill.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.STRONG_IDENTITY_PARTIAL


def test_011_logical_only_never_generates_execution_id(tmp_path):
    record = _record(_audit(tmp_path / "logical.json", _v1_document(open_trades={"k": _row()})))
    assert record.proposed_execution_id is None
    assert not record.audit_id.startswith("exec_")


def test_012_two_same_logical_open_rows_collision(tmp_path):
    rows = {"a": _row(), "b": _row(lifecycle_id="life-b")}
    result = _audit(tmp_path / "collision.json", _v1_document(open_trades=rows))
    assert len(result.collision_groups) == 1
    assert result.collision_groups[0].candidate_count == 2
    assert result.collision_groups[0].collision_risk is True


def test_013_open_and_closed_same_logical_collision(tmp_path):
    result = _audit(tmp_path / "open-closed.json", _v1_document(open_trades={"a": _row()}, closed_trades=[_row(lifecycle_id="life-closed")]))
    assert result.collision_groups[0].candidate_count == 2
    assert set(result.collision_groups[0].collections) == {"open_trades", "closed_trades"}


@pytest.mark.parametrize("field,first,second", [
    ("symbol", "BTCUSDT", "ETHUSDT"),
    ("side", "LONG", "SHORT"),
    ("bot", "FALCON", "TURTLE"),
    ("setup", "FALCON15", "TURTLE5"),
])
def test_014_to_017_different_logical_components_no_collision(tmp_path, field, first, second):
    first_row = _with_consistent_trade_id(_row(**{field: first}))
    second_row = _with_consistent_trade_id(_row(**{field: second}))
    result = _audit(tmp_path / f"different-{field}.json", _v1_document(open_trades={"a": first_row, "b": second_row}))
    assert result.collision_groups == ()


def test_018_paper_without_broker_evidence(tmp_path):
    record = _record(_audit(tmp_path / "paper.json", _v1_document(open_trades={"k": _row(execution_mode="PAPER")})))
    assert record.mode_claim == audit.PAPER
    assert record.classification == audit.LEGACY_LOGICAL_ONLY


def test_019_live_with_broker_evidence_real_candidate(tmp_path):
    row = _row(execution_mode="LIVE", broker_order_id="broker-1")
    record = _record(_audit(tmp_path / "live.json", _v1_document(open_trades={"k": row})))
    assert record.mode_claim == audit.REAL


@pytest.mark.parametrize("mode", ["PAPER", "VERIFY"])
def test_020_to_021_paper_or_verify_with_broker_evidence_mode_conflict(tmp_path, mode):
    row = _row(execution_mode=mode, broker_order_id="broker-1")
    record = _record(_audit(tmp_path / f"{mode}.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.MODE_CONFLICT
    assert record.recommendation == audit.QUARANTINE


@pytest.mark.parametrize("mode", ["PAPER", "VERIFY"])
def test_client_order_id_identity_does_not_prove_factual_broker_mode(tmp_path, mode):
    row = _row(execution_mode=mode, client_order_id="client-only")
    record = _record(_audit(tmp_path / f"{mode}-client-only.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.STRONG_IDENTITY_PARTIAL
    assert record.mode_claim == mode
    assert "broker_evidence:strong_id" not in record.mode_evidence


def test_live_with_client_order_only_is_unknown_not_real(tmp_path):
    row = _row(execution_mode="LIVE", client_order_id="client-only")
    record = _record(_audit(tmp_path / "live-client-only.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.STRONG_IDENTITY_PARTIAL
    assert record.mode_claim == audit.UNKNOWN
    assert audit.REAL not in record.mode_evidence


def test_live_without_strong_ids_is_unknown(tmp_path):
    record = _record(_audit(tmp_path / "live-no-ids.json", _v1_document(open_trades={"k": _row(execution_mode="LIVE")})))
    assert record.classification == audit.LEGACY_LOGICAL_ONLY
    assert record.mode_claim == audit.UNKNOWN


@pytest.mark.parametrize("field", ["broker_order_id", "exchange_order_id", "fill_id"])
def test_live_with_factual_broker_evidence_is_real(tmp_path, field):
    row = _row(
        execution_mode="LIVE",
        **({"fills": [{"fill_id": "fill-1"}]} if field == "fill_id" else {field: f"{field}-1"}),
    )
    record = _record(_audit(tmp_path / f"live-{field}.json", _v1_document(open_trades={"k": row})))
    assert record.mode_claim == audit.REAL


@pytest.mark.parametrize("field", ["broker_order_id", "fill_id"])
def test_paper_with_factual_broker_evidence_is_mode_conflict(tmp_path, field):
    row = _row(
        execution_mode="PAPER",
        **({"fills": [{"fill_id": "fill-1"}]} if field == "fill_id" else {field: f"{field}-1"}),
    )
    record = _record(_audit(tmp_path / f"paper-{field}.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.MODE_CONFLICT


def test_client_order_id_remains_strong_identity_only(tmp_path):
    row = _row(execution_mode="LIVE", client_order_id="client-only")
    record = _record(_audit(tmp_path / "client-identity.json", _v1_document(open_trades={"k": row})))
    assert "client_order_id=client-only" in record.strong_ids
    assert all("client_order_id" not in evidence for evidence in record.mode_evidence)


def test_022_missing_mode_unknown(tmp_path):
    record = _record(_audit(tmp_path / "unknown.json", _v1_document(open_trades={"k": _row()})))
    assert record.mode_claim == audit.UNKNOWN


def test_023_bot_name_does_not_infer_mode(tmp_path):
    record = _record(_audit(tmp_path / "bot-only.json", _v1_document(open_trades={"k": _row(execution_mode=None)})))
    assert record.mode_claim == audit.UNKNOWN


@pytest.mark.parametrize("marker", ["manual_position", "external_position"])
def test_024_to_025_manual_or_external_marker(tmp_path, marker):
    record = _record(_audit(tmp_path / f"{marker}.json", _v1_document(open_trades={"k": _row(**{marker: True})})))
    assert record.classification == audit.EXTERNAL_OR_MANUAL
    assert record.recommendation == audit.EXTERNAL_OBSERVATION_ONLY


def test_026_managed_by_central_false_external(tmp_path):
    record = _record(_audit(tmp_path / "managed-false.json", _v1_document(open_trades={"k": _row(managed_by_central=False)})))
    assert record.classification == audit.EXTERNAL_OR_MANUAL


def test_027_external_never_proposed_central(tmp_path):
    record = _record(_audit(tmp_path / "external.json", _v1_document(open_trades={"k": _row(owner_type="MANUAL_EXTERNAL", lifecycle_id="life-1")})))
    assert record.proposed_execution_id is None


def test_028_invalid_top_level_json(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text("{bad", encoding="utf-8")
    assert audit.audit_registry_v1_for_v2(path).status == audit.MIGRATION_AUDIT_FILE_INVALID_JSON


def test_029_missing_file(tmp_path):
    path = tmp_path / "missing.json"
    result = audit.audit_registry_v1_for_v2(path)
    assert result.status == audit.MIGRATION_AUDIT_FILE_NOT_FOUND
    assert path.exists() is False


def test_030_top_level_not_mapping(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    assert audit.audit_registry_v1_for_v2(path).status == audit.MIGRATION_AUDIT_DOCUMENT_INVALID


@pytest.mark.parametrize("field,value", [("open_trades", []), ("closed_trades", {})])
def test_031_to_032_invalid_collection_types(tmp_path, field, value):
    document = _v1_document()
    document[field] = value if field == "open_trades" else 1
    result = _audit(tmp_path / f"invalid-{field}.json", document)
    assert result.status == audit.MIGRATION_AUDIT_DOCUMENT_INVALID


def test_033_non_mapping_row_invalid(tmp_path):
    result = _audit(tmp_path / "row.json", _v1_document(closed_trades=["not-a-row"]))
    record = _record(result)
    assert record.classification == audit.INVALID_ROW
    assert record.recommendation == audit.INVALID_DO_NOT_MIGRATE


def test_034_audit_id_deterministic(tmp_path):
    document = _v1_document(open_trades={"k": _row()})
    first = _audit(tmp_path / "first.json", document)
    second = _audit(tmp_path / "second.json", document)
    # The source path is intentionally not part of the deterministic ID.
    assert first.records[0].audit_id == second.records[0].audit_id


def test_035_audit_id_differs_for_distinct_rows(tmp_path):
    document = _v1_document(open_trades={"a": _row(), "b": _row(symbol="ETHUSDT")})
    result = _audit(tmp_path / "distinct.json", document)
    assert result.records[0].audit_id != result.records[1].audit_id


def test_036_audit_id_never_starts_exec(tmp_path):
    result = _audit(tmp_path / "audit-id.json", _v1_document(open_trades={"k": _row(lifecycle_id="life-1")}))
    assert not result.records[0].audit_id.startswith("exec_")
    assert result.records[0].audit_id.startswith("legacyaudit_")


def test_037_row_digest_deterministic():
    assert audit.compute_legacy_row_digest({"b": 2, "a": 1}) == audit.compute_legacy_row_digest({"a": 1, "b": 2})


def test_038_row_digest_does_not_mutate():
    row = _row(metadata={"nested": {"value": 1}})
    before = copy.deepcopy(row)
    audit.compute_legacy_row_digest(row)
    assert row == before


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_039_non_finite_json_rejected(tmp_path, literal):
    path = tmp_path / "non-finite.json"
    path.write_text(f'{{"open_trades": {literal}, "closed_trades": []}}', encoding="utf-8")
    assert audit.audit_registry_v1_for_v2(path).status == audit.MIGRATION_AUDIT_FILE_INVALID_JSON


def test_040_source_digest_deterministic(tmp_path):
    document = _v1_document()
    first = _audit(tmp_path / "one.json", document)
    second = _audit(tmp_path / "two.json", document)
    assert first.source_digest == second.source_digest


def test_041_output_dataclasses_frozen(tmp_path):
    result = _audit(tmp_path / "frozen.json", _v1_document())
    with pytest.raises(AttributeError):
        result.ok = False


def test_042_no_writer_calls_in_source():
    forbidden = {"write", "write_text", "write_bytes", "mkdir", "touch", "rename", "replace", "unlink", "chmod", "fsync"}
    assert not any(isinstance(node, ast.Attribute) and node.attr in forbidden for node in ast.walk(_source_tree()))


def test_043_no_mkdir_temp_replace_literals_or_calls():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "tempfile" not in source
    assert ".mkdir(" not in source
    assert ".replace(" not in source


def test_044_no_environment_access():
    tree = _source_tree()
    assert not any(isinstance(node, ast.Name) and node.id == "environ" for node in ast.walk(tree))
    assert not any(isinstance(node, ast.Attribute) and node.attr == "environ" for node in ast.walk(tree))


def test_045_no_network_imports():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "requests" not in source
    assert "urllib" not in source
    assert "socket" not in source
    assert "redis" not in source


def test_046_to_048_no_runtime_imports():
    roots = set()
    for node in ast.walk(_source_tree()):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", maxsplit=1)[0])
    assert roots <= {"__future__", "hashlib", "json", "collections", "dataclasses", "pathlib", "typing", "registry_execution_schema"}
    assert "trade_registry" not in roots
    assert roots.isdisjoint({"bots", "broker", "main", "redis", "requests", "subprocess"})


def test_049_python_311_syntax():
    assert isinstance(ast.parse(MODULE_PATH.read_text(encoding="utf-8"), feature_version=(3, 11)), ast.Module)


def test_050_explicit_path_mandatory():
    assert inspect.signature(audit.audit_registry_v1_for_v2).parameters["path"].default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        audit.audit_registry_v1_for_v2()


def test_051_no_production_path_literals():
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for literal in ("trade_registry.json", "registry_v2.json", "/data/", "/opt/render/"):
        assert literal not in source


def test_052_report_preserves_source_locator(tmp_path):
    result = _audit(tmp_path / "locator.json", _v1_document(open_trades={"legacy-key": _row()}, closed_trades=[_row(symbol="ETHUSDT")]))
    assert result.records[0].source_locator == "open_trades.legacy-key"
    assert result.records[1].source_locator == "closed_trades[0]"


@pytest.mark.parametrize("field,value", [
    ("lifecycle_id", "same-life"),
    ("client_order_id", "same-client"),
    ("broker_order_id", "same-broker"),
])
def test_053_to_055_duplicate_strong_ids_flagged(tmp_path, field, value):
    document = _v1_document(open_trades={"a": _row(**{field: value}), "b": _row(**{field: value})})
    result = _audit(tmp_path / f"duplicate-{field}.json", document)
    assert all(record.classification == audit.IDENTITY_CONFLICT for record in result.records)
    assert all("duplicate_strong_identity" in record.errors for record in result.records)


@pytest.mark.parametrize("field", ["side", "symbol", "bot", "setup"])
def test_056_to_059_conflicting_aliases_are_reported(tmp_path, field):
    value = {"side": "LONG", "symbol": "BTCUSDT", "bot": "FALCON", "setup": "FALCON15"}[field]
    metadata = {field: "CONFLICTING" if field not in {"side"} else "SHORT"}
    row = _row(**{field: value, "metadata": metadata})
    record = _record(_audit(tmp_path / f"alias-{field}.json", _v1_document(open_trades={"k": row})))
    assert record.classification == audit.IDENTITY_CONFLICT
    assert any(field in error for error in record.errors)


@pytest.mark.parametrize("classification,recommendation,row", [
    (audit.STRONG_LIFECYCLE_ID, audit.V2_PROJECTION_CANDIDATE, _row(lifecycle_id="life-1")),
    (audit.STRONG_IDENTITY_PARTIAL, audit.ARCHIVE_READ_ONLY_UNTIL_RECONCILIATION, _row(client_order_id="client-1")),
    (audit.LEGACY_LOGICAL_ONLY, audit.ARCHIVE_READ_ONLY, _row()),
    (audit.MISSING_IDENTITY, audit.INVALID_DO_NOT_MIGRATE, {}),
])
def test_060_recommendation_contract(tmp_path, classification, recommendation, row):
    source_key = "" if classification == audit.MISSING_IDENTITY else "k"
    result = _audit(tmp_path / f"recommendation-{classification}.json", _v1_document(open_trades={source_key: row}))
    record = _record(result)
    assert record.classification == classification
    assert record.recommendation == recommendation


def test_061_raw_input_unchanged(tmp_path):
    document = _v1_document(open_trades={"k": _row(metadata={"nested": {"v": 1}})})
    before = copy.deepcopy(document)
    _audit(tmp_path / "unchanged.json", document)
    assert document == before


def test_062_input_file_bytes_unchanged(tmp_path):
    path = tmp_path / "bytes.json"
    _write(path, _v1_document())
    before = path.read_bytes()
    audit.audit_registry_v1_for_v2(path)
    assert path.read_bytes() == before


def test_063_no_v2_file_created(tmp_path):
    source = tmp_path / "v1.json"
    _audit(source, _v1_document())
    assert not (tmp_path / "registry_v2.json").exists()


def test_064_no_journal_file_created(tmp_path):
    _audit(tmp_path / "v1.json", _v1_document())
    assert not (tmp_path / "registry_v2_events.jsonl").exists()


def test_065_no_migration_state_created(tmp_path):
    _audit(tmp_path / "v1.json", _v1_document())
    assert list(tmp_path.iterdir()) == [tmp_path / "v1.json"]
