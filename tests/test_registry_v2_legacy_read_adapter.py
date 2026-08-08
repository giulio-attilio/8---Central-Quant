from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

import registry_execution_schema as schema
import registry_v2_legacy_read_adapter as adapter
import registry_v2_reader as reader


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "registry_v2_legacy_read_adapter.py"


def _row(
    execution_id: str = "exec-a",
    *,
    state: str = schema.OPEN,
    logical_trade_id: str = "FALCON:FALCON15:BTCUSDT:LONG",
    **overrides,
):
    row = {
        "execution_id": execution_id,
        "lifecycle_id": execution_id,
        "logical_trade_id": logical_trade_id,
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "owner_type": schema.CENTRAL,
        "execution_mode": schema.PAPER,
        "registry_mode": schema.PAPER,
        "lifecycle_state": state,
        "execution_provenance": {"source": "legacy-adapter-test"},
        "signal_id": f"signal-{execution_id}",
        "decision_id": f"decision-{execution_id}",
        "position_side": "LONG",
        "metadata": {},
    }
    row.update(overrides)
    return row


def _document(*, open_rows=(), closed_rows=(), external_observations=None):
    open_rows = list(open_rows)
    closed_rows = list(closed_rows)
    indexes = schema.build_registry_v2_indexes(open_rows + closed_rows)
    document = {
        "schema_version": schema.SCHEMA_VERSION,
        "registry_version": schema.REGISTRY_VERSION,
        "generation": 4,
        "snapshot_id": "adapter-test",
        "updated_at": "2026-08-08T00:00:00Z",
        "integrity": {"snapshot_digest": "placeholder"},
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
        "operation_ledger": {"derived": "unchanged"},
        "migration": {"phase": "V2_6_DORMANT", "journal_cursor": 0},
    }
    _refresh_digest(document)
    return document


def _refresh_digest(document):
    document["integrity"]["snapshot_digest"] = reader.compute_registry_v2_snapshot_digest(document)


def _close_row(row, close_event_id="close-a", digest=None):
    result = dict(row)
    close_event = {"close_event_id": close_event_id}
    if digest is not None:
        close_event["digest"] = digest
    result["close_events"] = [close_event]
    return result


def _set_index(document, name, key, value):
    document["indexes"][name] = {key: value}
    return document


def _temp_document(*, open_rows=(), closed_rows=(), external_observations=None):
    document = _document(
        open_rows=open_rows,
        closed_rows=closed_rows,
        external_observations=external_observations,
    )
    document["migration"]["phase"] = "V2_CORE_TEMPORARY"
    return document


def test_unique_open_logical_resolution_is_read_only():
    document = _document(open_rows=[_row()])
    before = copy.deepcopy(document)

    result = adapter.resolve_legacy_trade_v2(document, logical_trade_id="FALCON:FALCON15:BTCUSDT:LONG")

    assert result.ok
    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert result.execution_id == "exec-a"
    assert result.collection == "open_trades"
    assert document == before


def test_unique_closed_resolution_and_include_closed_filter():
    closed = _row(state=schema.CLOSED_PROVISIONAL)
    document = _document(closed_rows=[closed])

    included = adapter.resolve_legacy_trade_v2(document, trade_id=closed["logical_trade_id"])
    excluded = adapter.resolve_legacy_trade_v2(
        document,
        trade_id=closed["logical_trade_id"],
        include_closed=False,
    )

    assert included.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert included.collection == "closed_trades"
    assert excluded.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_same_logical_id_open_and_closed_is_ambiguous():
    logical = "FALCON:FALCON15:BTCUSDT:LONG"
    document = _document(
        open_rows=[_row("exec-open", logical_trade_id=logical)],
        closed_rows=[_row("exec-closed", state=schema.CLOSED_PROVISIONAL, logical_trade_id=logical)],
    )

    result = adapter.resolve_legacy_trade_v2(document, logical_trade_id=logical)

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert [candidate.execution_id for candidate in result.candidates] == ["exec-open", "exec-closed"]


def test_two_open_and_two_closed_same_logical_are_ambiguous_deterministically():
    logical = "FALCON:FALCON15:BTCUSDT:LONG"
    document = _document(
        open_rows=[_row("exec-z", logical_trade_id=logical), _row("exec-a", logical_trade_id=logical)],
        closed_rows=[
            _row("exec-y", state=schema.CLOSED_PROVISIONAL, logical_trade_id=logical),
            _row("exec-b", state=schema.CLOSED_RECONCILED, logical_trade_id=logical),
        ],
    )

    result = adapter.resolve_legacy_trade_v2(document, logical_trade_id=logical)

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert [candidate.execution_id for candidate in result.candidates] == [
        "exec-a", "exec-z", "exec-b", "exec-y",
    ]


def test_components_resolve_one_and_same_components_are_ambiguous():
    first = _row("exec-a")
    second = _row("exec-b")
    document = _document(open_rows=[first, second])

    unique = adapter.resolve_legacy_trade_v2(
        document,
        bot="FALCON",
        setup="FALCON15",
        symbol="BTCUSDT",
        side="LONG",
        execution_id="exec-a",
    )
    ambiguous = adapter.resolve_legacy_trade_v2(
        document,
        bot="FALCON",
        setup="FALCON15",
        symbol="BTCUSDT",
        side="LONG",
    )

    assert unique.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert unique.execution_id == "exec-a"
    assert ambiguous.status == adapter.REGISTRY_LEGACY_AMBIGUOUS


def test_incomplete_components_and_invalid_side_are_invalid():
    document = _document(open_rows=[_row()])

    incomplete = adapter.resolve_legacy_trade_v2(document, bot="FALCON", symbol="BTCUSDT")
    malformed_side = adapter.resolve_legacy_trade_v2(
        document, bot="FALCON", setup="FALCON15", symbol="BTCUSDT", side="BOTH",
    )

    assert incomplete.status == adapter.REGISTRY_LEGACY_INVALID
    assert malformed_side.status == adapter.REGISTRY_LEGACY_INVALID


def test_physical_execution_and_lifecycle_alias_rules():
    document = _document(open_rows=[_row()])

    exact = adapter.resolve_legacy_trade_v2(document, execution_id="exec-a")
    missing = adapter.resolve_legacy_trade_v2(document, execution_id="exec-missing")
    mismatch = adapter.resolve_legacy_trade_v2(document, execution_id="exec-a", lifecycle_id="other")

    assert exact.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert missing.status == adapter.REGISTRY_LEGACY_NOT_FOUND
    assert mismatch.status == adapter.REGISTRY_LEGACY_CONFLICT


def test_physical_execution_contradictory_logical_selector_is_conflict():
    document = _document(open_rows=[_row()])

    result = adapter.resolve_legacy_trade_v2(
        document,
        execution_id="exec-a",
        logical_trade_id="FALCON:FALCON15:ETHUSDT:LONG",
    )

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.execution_id is None


def test_strong_id_lookups_cover_all_canonical_fields():
    row = _row(
        client_order_id="client-a",
        broker_order_id="broker-a",
        exchange_order_id="exchange-a",
        fill_id="fill-a",
    )
    document = _document(open_rows=[row])

    results = [
        adapter.resolve_strong_id_v2(document, field, value)
        for field, value in (
            ("client_order_id", "client-a"),
            ("broker_order_id", "broker-a"),
            ("exchange_order_id", "exchange-a"),
            ("fill_id", "fill-a"),
        )
    ]

    assert all(result.status == adapter.REGISTRY_LEGACY_UNIQUE for result in results)
    assert all(result.execution_id == "exec-a" for result in results)


def test_close_event_id_lookup_is_unique_per_execution():
    document = _document(open_rows=[_close_row(_row(), "close-a")])

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert result.execution_id == "exec-a"
    assert result.candidates[0].close_event_ids == ("close-a",)


def test_duplicate_strong_ownership_is_ambiguous_not_first_match():
    document = _document(
        open_rows=[
            _row("exec-a", client_order_id="duplicate-client"),
            _row("exec-b", client_order_id="duplicate-client"),
        ]
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "duplicate-client")

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert {candidate.execution_id for candidate in result.candidates} == {"exec-a", "exec-b"}


def test_stale_strong_index_fails_closed_without_repairing_document():
    row = _row("exec-a")
    document = _temp_document(open_rows=[row])
    document["indexes"]["by_client_order_id"] = {"client-a": "exec-a"}
    _refresh_digest(document)
    before = copy.deepcopy(document)

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "client-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert "client_order_id_index_stale" in result.errors
    assert document == before


def test_strong_id_index_row_mismatch_fails_closed():
    row = _row("exec-a", client_order_id="client-a")
    document = _document(open_rows=[row])
    document["indexes"]["by_client_order_id"] = {
        "client-a": {"execution_id": "exec-b", "role": "TOP_LEVEL"},
    }
    _refresh_digest(document)

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "client-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert "client_order_id_index_stale" in result.errors


def test_external_only_is_explicit_and_central_is_never_adopted():
    external = {
        "manual-1": {
            "owner_type": schema.MANUAL_EXTERNAL,
            "logical_trade_id": "FALCON:FALCON15:BTCUSDT:LONG",
            "bot": "FALCON",
            "setup": "FALCON15",
            "symbol": "BTCUSDT",
            "side": "LONG",
        }
    }
    external_document = _document(external_observations=external)
    central_result = adapter.resolve_legacy_trade_v2(
        external_document, logical_trade_id="FALCON:FALCON15:BTCUSDT:LONG",
    )

    central_document = _document(open_rows=[_row()], external_observations=external)
    central_result_with_external = adapter.resolve_legacy_trade_v2(
        central_document, logical_trade_id="FALCON:FALCON15:BTCUSDT:LONG",
    )

    assert central_result.status == adapter.REGISTRY_LEGACY_EXTERNAL_ONLY
    assert not central_result.candidates
    assert central_result_with_external.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert central_result_with_external.execution_id == "exec-a"
    assert len(central_result_with_external.external_matches) == 1


@pytest.mark.parametrize(
    "selector",
    [
        {"logical_trade_id": "FALCON:FALCON15:BTCUSDT:LONG"},
        {"execution_id": "exec-a"},
        {"client_order_id": "client-a"},
    ],
)
def test_all_read_projections_preserve_document(selector):
    document = _document(open_rows=[_row("exec-a", client_order_id="client-a")])
    before = copy.deepcopy(document)

    result = adapter.resolve_legacy_trade_v2(document, **selector)

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert document == before
    assert document["generation"] == 4
    assert document["operation_ledger"] == {"derived": "unchanged"}


def test_explicit_path_is_routed_through_reader_and_not_written(tmp_path):
    path = tmp_path / "registry-v2.json"
    document = _document(open_rows=[_row()])
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    before = path.read_bytes()

    result = adapter.resolve_legacy_trade_v2(path, logical_trade_id=document["open_trades"]["exec-a"]["logical_trade_id"])

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert path.read_bytes() == before


def test_read_result_input_is_supported():
    document = _document(open_rows=[_row()])
    read_result = reader.RegistryV2ReadResult(
        ok=True,
        status=reader.REGISTRY_V2_READ_OK,
        path="explicit-test-document",
        document=document,
    )

    result = adapter.resolve_legacy_trade_v2(read_result, execution_id="exec-a")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert result.execution_id == "exec-a"


def test_no_selector_is_invalid_and_logical_id_is_not_a_mutation_api():
    document = _document(open_rows=[_row()])

    result = adapter.resolve_legacy_trade_v2(document)

    assert result.status == adapter.REGISTRY_LEGACY_INVALID
    assert not hasattr(adapter, "update_trade_v2")
    assert not hasattr(adapter, "close_trade_v2")


def test_source_guard_has_no_runtime_or_mutation_dependencies():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = {"requests", "httpx", "subprocess", "main", "broker"}
    forbidden_calls = {
        "apply_temp_wal_mutation",
        "register_trade_v2",
        "update_trade_v2",
        "partial_close_trade_v2",
        "close_trade_v2",
        "reconcile_trade_v2",
    }
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        for alias in node.names
    )
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (isinstance(node.func, ast.Attribute) or isinstance(node.func, ast.Name))
    }

    assert not imported.intersection(forbidden_modules)
    assert not called.intersection(forbidden_calls)
    assert "registry_v2_core" not in source
    assert "registry_v2_wal" not in source


def test_document_collections_remain_unchanged_after_ambiguous_read():
    logical = "FALCON:FALCON15:BTCUSDT:LONG"
    document = _document(open_rows=[_row("exec-a", logical_trade_id=logical), _row("exec-b", logical_trade_id=logical)])
    before = copy.deepcopy(document)

    result = adapter.resolve_legacy_trade_v2(document, logical_trade_id=logical)

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert document["open_trades"] == before["open_trades"]
    assert document["closed_trades"] == before["closed_trades"]
    assert document["operation_ledger"] == before["operation_ledger"]


def test_entry_order_strong_ids_are_factual_and_role_aware():
    row = _row(
        entry_order={
            "role": "ENTRY",
            "client_order_id": "entry-client",
            "broker_order_id": "entry-broker",
            "exchange_order_id": "entry-exchange",
        }
    )
    document = _document(open_rows=[row])

    results = [
        adapter.resolve_strong_id_v2(document, field, value)
        for field, value in (
            ("client_order_id", "entry-client"),
            ("broker_order_id", "entry-broker"),
            ("exchange_order_id", "entry-exchange"),
        )
    ]

    assert all(result.status == adapter.REGISTRY_LEGACY_UNIQUE for result in results)
    assert all(result.execution_id == "exec-a" for result in results)
    assert {fact.role for fact in results[0].candidates[0].strong_facts} == {"ENTRY"}


def test_order_strong_ids_include_stop_tp_and_close_roles():
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "stop-client"},
            "tp": {"role": "TP", "broker_order_id": "tp-broker"},
            "close": {"role": "CLOSE", "exchange_order_id": "close-exchange", "broker_order_id": "close-broker"},
        }
    )
    document = _document(open_rows=[row])

    lookups = [
        adapter.resolve_strong_id_v2(document, "client_order_id", "stop-client"),
        adapter.resolve_strong_id_v2(document, "broker_order_id", "tp-broker"),
        adapter.resolve_strong_id_v2(document, "exchange_order_id", "close-exchange"),
        adapter.resolve_strong_id_v2(document, "broker_order_id", "close-broker"),
    ]

    assert [result.status for result in lookups] == [adapter.REGISTRY_LEGACY_UNIQUE] * 4
    assert {
        fact.role
        for fact in lookups[0].candidates[0].strong_facts
        if fact.field == "client_order_id" and fact.value == "stop-client"
    } == {"STOP"}


def test_fill_id_is_extracted_from_fills():
    row = _row(fills=[{"fill_id": "fill-nested", "order_id": "broker-related", "role": "ENTRY"}])
    result = adapter.resolve_strong_id_v2(_document(open_rows=[row]), "fill_id", "fill-nested")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert result.candidates[0].strong_ids == (("fill_id", "fill-nested"),)
    assert result.candidates[0].strong_facts[0].source == "fills[0]"


def test_same_factual_id_in_multiple_roles_stays_one_candidate():
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "shared-client"},
            "tp": {"role": "TP", "client_order_id": "shared-client"},
        }
    )
    result = adapter.resolve_strong_id_v2(_document(open_rows=[row]), "client_order_id", "shared-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert result.execution_id == "exec-a"
    assert {fact.role for fact in result.candidates[0].strong_facts} == {"STOP", "TP"}


def test_same_nested_factual_id_in_two_executions_is_ambiguous():
    rows = [
        _row("exec-a", entry_order={"role": "ENTRY", "client_order_id": "shared-client"}),
        _row("exec-b", entry_order={"role": "ENTRY", "client_order_id": "shared-client"}),
    ]
    result = adapter.resolve_strong_id_v2(_document(open_rows=rows), "client_order_id", "shared-client")

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert [candidate.execution_id for candidate in result.candidates] == ["exec-a", "exec-b"]


def test_canonical_client_index_execution_and_role_match():
    row = _row(entry_order={"role": "ENTRY", "client_order_id": "indexed-client"})
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "indexed-client",
        {"execution_id": "exec-a", "role": "ENTRY"},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "indexed-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


@pytest.mark.parametrize(
    "index_value",
    [
        {"execution_id": "exec-b", "role": "ENTRY"},
        {"execution_id": "exec-a", "role": "STOP"},
    ],
)
def test_canonical_client_index_wrong_execution_or_role_conflicts(index_value):
    row = _row(entry_order={"role": "ENTRY", "client_order_id": "indexed-client"})
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "indexed-client",
        index_value,
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "indexed-client")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert "client_order_id_index_stale" in result.errors


def test_canonical_broker_and_fill_indexes_verify_execution_and_role():
    row = _row(
        orders={"stop": {"role": "STOP", "broker_order_id": "indexed-broker"}},
        fills=[{"role": "TP", "fill_id": "indexed-fill"}],
    )
    document = _document(open_rows=[row])
    document["indexes"]["by_broker_order_id"] = {
        "indexed-broker": {"execution_id": "exec-a", "role": "STOP"},
    }
    document["indexes"]["by_fill_id"] = {
        "indexed-fill": {"execution_id": "exec-a", "role": "TP"},
    }

    broker = adapter.resolve_strong_id_v2(document, "broker_order_id", "indexed-broker")
    fill = adapter.resolve_strong_id_v2(document, "fill_id", "indexed-fill")

    assert broker.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert fill.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_malformed_factual_index_value_does_not_fallback_to_row_scan():
    row = _row(entry_order={"role": "ENTRY", "client_order_id": "malformed-client"})
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "malformed-client",
        {"not_execution_id": "exec-a"},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "malformed-client")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_value_invalid",)


def test_temp_string_strong_index_remains_supported_as_legacy_fallback():
    row = _row(client_order_id="temp-client")
    document = _set_index(_temp_document(open_rows=[row]), "by_client_order_id", "temp-client", "exec-a")

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "temp-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_exchange_lookup_uses_canonical_broker_projection_when_exchange_index_absent():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "indexed-exchange"})
    document = _document(open_rows=[row])
    document["indexes"]["by_broker_order_id"] = {
        "indexed-exchange": {"execution_id": "exec-a", "role": "ENTRY"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "indexed-exchange")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_close_event_index_value_is_a_digest_not_execution_id():
    row = _close_row(_row(), "close-a", digest="digest-a")
    document = _set_index(
        _document(open_rows=[row]),
        "by_close_event_id",
        "exec-a|close-a",
        "digest-a",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_close_event_index_value_execution_id_is_rejected_as_stale_digest():
    row = _close_row(_row(), "close-a", digest="digest-a")
    document = _set_index(
        _document(open_rows=[row]),
        "by_close_event_id",
        "exec-a|close-a",
        "exec-a",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert "close_event_id_index_stale" in result.errors


def test_wrong_close_event_digest_conflicts():
    row = _close_row(_row(), "close-a", digest="digest-a")
    document = _set_index(
        _document(open_rows=[row]),
        "by_close_event_id",
        "exec-a|close-a",
        "wrong-digest",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("close_event_id_index_stale",)


def test_close_index_reference_to_nonexistent_event_conflicts():
    document = _set_index(
        _document(open_rows=[_row()]),
        "by_close_event_id",
        "exec-a|missing-close",
        "digest-a",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "missing-close")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("close_event_id_index_stale",)


def test_close_event_index_omission_conflicts_when_index_is_present():
    row = _close_row(_row(), "close-a", digest="digest-a")
    document = _document(open_rows=[row])
    document["indexes"]["by_close_event_id"] = {}

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("close_event_id_index_stale",)


def test_same_close_event_id_on_two_executions_is_ambiguous_when_index_is_coherent():
    rows = [
        _close_row(_row("exec-a"), "close-a", digest="digest-a"),
        _close_row(_row("exec-b"), "close-a", digest="digest-b"),
    ]
    document = _document(open_rows=rows)
    document["indexes"]["by_close_event_id"] = {
        "exec-a|close-a": "digest-a",
        "exec-b|close-a": "digest-b",
    }

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "close-a")

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert [candidate.execution_id for candidate in result.candidates] == ["exec-a", "exec-b"]


def test_non_temp_bare_strong_index_is_invalid_and_not_a_temp_inference():
    row = _row(client_order_id="canonical-client")
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "canonical-client",
        "exec-a",
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "canonical-client")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_value_invalid",)
    assert not adapter._is_v25_temp_projection(document)


def test_temp_provenance_allows_bare_strong_index_value():
    row = _row(client_order_id="temp-client-explicit")
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_client_order_id",
        "temp-client-explicit",
        "exec-a",
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "temp-client-explicit")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert adapter._is_v25_temp_projection(document)


def test_temp_provenance_also_accepts_structured_strong_index_value():
    row = _row(entry_order={"role": "ENTRY", "client_order_id": "temp-structured-client"})
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_client_order_id",
        "temp-structured-client",
        {"execution_id": "exec-a", "role": "ENTRY"},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "temp-structured-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_temp_close_index_accepts_execution_id_value_only_as_legacy_compatibility():
    row = _close_row(_row(), "temp-close-a")
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_close_event_id",
        "exec-a|temp-close-a",
        "exec-a",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "temp-close-a")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_temp_close_index_wrong_execution_value_conflicts():
    row = _close_row(_row(), "temp-close-a")
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_close_event_id",
        "exec-a|temp-close-a",
        "exec-b",
    )

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "temp-close-a")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("close_event_id_index_stale",)


def test_temp_close_event_id_is_ambiguous_when_each_execution_has_its_own_temp_owner():
    rows = [
        _close_row(_row("exec-a"), "shared-temp-close"),
        _close_row(_row("exec-b"), "shared-temp-close"),
    ]
    document = _temp_document(open_rows=rows)
    document["indexes"]["by_close_event_id"] = {
        "exec-a|shared-temp-close": "exec-a",
        "exec-b|shared-temp-close": "exec-b",
    }

    result = adapter.resolve_strong_id_v2(document, "close_event_id", "shared-temp-close")

    assert result.status == adapter.REGISTRY_LEGACY_AMBIGUOUS
    assert [candidate.execution_id for candidate in result.candidates] == ["exec-a", "exec-b"]


def test_exchange_index_empty_surface_does_not_hide_canonical_broker_projection():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-empty-fallback"})
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {}
    document["indexes"]["by_broker_order_id"] = {
        "exchange-empty-fallback": {"execution_id": "exec-a", "role": "ENTRY"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-empty-fallback")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_exchange_indexes_agree_when_both_surfaces_contain_the_value():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-both"})
    document = _document(open_rows=[row])
    owner = {"execution_id": "exec-a", "role": "ENTRY"}
    document["indexes"]["by_exchange_order_id"] = {"exchange-both": owner}
    document["indexes"]["by_broker_order_id"] = {"exchange-both": dict(owner)}

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-both")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_exchange_wrong_execution_in_one_present_index_is_not_ignored():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-divergent"})
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {
        "exchange-divergent": {"execution_id": "exec-b", "role": "ENTRY"},
    }
    document["indexes"]["by_broker_order_id"] = {
        "exchange-divergent": {"execution_id": "exec-a", "role": "ENTRY"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-divergent")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_stale",)


def test_exchange_wrong_role_in_second_present_index_is_not_ignored():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-role-divergent"})
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {
        "exchange-role-divergent": {"execution_id": "exec-a", "role": "ENTRY"},
    }
    document["indexes"]["by_broker_order_id"] = {
        "exchange-role-divergent": {"execution_id": "exec-a", "role": "STOP"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-role-divergent")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_stale",)


def test_exchange_malformed_present_index_is_not_ignored_when_other_index_is_valid():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-malformed"})
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {
        "exchange-malformed": {"not_execution_id": "exec-a"},
    }
    document["indexes"]["by_broker_order_id"] = {
        "exchange-malformed": {"execution_id": "exec-a", "role": "ENTRY"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-malformed")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_value_invalid",)


def test_exchange_canonical_indexes_without_applicable_entry_remain_stale():
    row = _row(entry_order={"role": "ENTRY", "exchange_order_id": "exchange-omitted"})
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {}
    document["indexes"]["by_broker_order_id"] = {}

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "exchange-omitted")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_stale",)


def test_canonical_index_missing_one_factual_role_is_stale():
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "shared-role-client"},
            "tp": {"role": "TP", "client_order_id": "shared-role-client"},
        }
    )
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "shared-role-client",
        {"execution_id": "exec-a", "role": "STOP"},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "shared-role-client")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_stale",)


@pytest.mark.parametrize(
    "index_value",
    [
        {"execution_id": "exec-a", "roles": ["STOP", "TP"]},
        [
            {"execution_id": "exec-a", "role": "STOP"},
            {"execution_id": "exec-a", "role": "TP"},
        ],
    ],
)
def test_canonical_index_can_represent_all_factual_roles(index_value):
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "shared-role-client"},
            "tp": {"role": "TP", "client_order_id": "shared-role-client"},
        }
    )
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "shared-role-client",
        index_value,
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "shared-role-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_canonical_index_with_extra_role_is_stale():
    row = _row(orders={"stop": {"role": "STOP", "client_order_id": "single-role-client"}})
    document = _set_index(
        _document(open_rows=[row]),
        "by_client_order_id",
        "single-role-client",
        {"execution_id": "exec-a", "roles": ["STOP", "TP"]},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "single-role-client")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_stale",)


def test_temp_bare_string_preserves_execution_only_compatibility_for_multiple_roles():
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "temp-multi-role-client"},
            "tp": {"role": "TP", "client_order_id": "temp-multi-role-client"},
        }
    )
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_client_order_id",
        "temp-multi-role-client",
        "exec-a",
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "temp-multi-role-client")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_temp_structured_index_still_requires_role_completeness():
    row = _row(
        orders={
            "stop": {"role": "STOP", "client_order_id": "temp-structured-incomplete"},
            "tp": {"role": "TP", "client_order_id": "temp-structured-incomplete"},
        }
    )
    document = _set_index(
        _temp_document(open_rows=[row]),
        "by_client_order_id",
        "temp-structured-incomplete",
        {"execution_id": "exec-a", "role": "STOP"},
    )

    result = adapter.resolve_strong_id_v2(document, "client_order_id", "temp-structured-incomplete")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_stale",)


def test_exchange_canonical_index_must_include_all_factual_roles():
    row = _row(
        entry_order={"role": "ENTRY", "exchange_order_id": "multi-role-exchange"},
        orders={"close": {"role": "CLOSE", "exchange_order_id": "multi-role-exchange"}},
    )
    document = _set_index(
        _document(open_rows=[row]),
        "by_exchange_order_id",
        "multi-role-exchange",
        {"execution_id": "exec-a", "role": "ENTRY"},
    )

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "multi-role-exchange")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_stale",)


def test_both_exchange_indexes_are_unique_when_both_have_complete_roles():
    row = _row(
        entry_order={"role": "ENTRY", "exchange_order_id": "complete-exchange"},
        orders={"close": {"role": "CLOSE", "exchange_order_id": "complete-exchange"}},
    )
    document = _document(open_rows=[row])
    complete = {"execution_id": "exec-a", "roles": ["ENTRY", "CLOSE"]}
    document["indexes"]["by_exchange_order_id"] = {"complete-exchange": complete}
    document["indexes"]["by_broker_order_id"] = {
        "complete-exchange": dict(complete),
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "complete-exchange")

    assert result.status == adapter.REGISTRY_LEGACY_UNIQUE


def test_one_exchange_index_incomplete_roles_conflicts_with_complete_second_index():
    row = _row(
        entry_order={"role": "ENTRY", "exchange_order_id": "incomplete-exchange"},
        orders={"close": {"role": "CLOSE", "exchange_order_id": "incomplete-exchange"}},
    )
    document = _document(open_rows=[row])
    document["indexes"]["by_exchange_order_id"] = {
        "incomplete-exchange": {"execution_id": "exec-a", "roles": ["ENTRY", "CLOSE"]},
    }
    document["indexes"]["by_broker_order_id"] = {
        "incomplete-exchange": {"execution_id": "exec-a", "role": "ENTRY"},
    }

    result = adapter.resolve_strong_id_v2(document, "exchange_order_id", "incomplete-exchange")

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("exchange_order_id_index_stale",)


def test_closed_only_canonical_client_is_unique_or_not_found_by_view():
    row = _row(
        "exec-closed-client",
        state=schema.CLOSED_PROVISIONAL,
        entry_order={"role": "ENTRY", "client_order_id": "closed-client"},
    )
    document = _set_index(
        _document(closed_rows=[row]),
        "by_client_order_id",
        "closed-client",
        {"execution_id": "exec-closed-client", "role": "ENTRY"},
    )

    included = adapter.resolve_strong_id_v2(document, "client_order_id", "closed-client")
    excluded = adapter.resolve_strong_id_v2(
        document,
        "client_order_id",
        "closed-client",
        include_closed=False,
    )

    assert included.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert included.collection == "closed_trades"
    assert excluded.status == adapter.REGISTRY_LEGACY_NOT_FOUND


@pytest.mark.parametrize(
    "field,value,index_name,row_override,role",
    [
        (
            "broker_order_id",
            "closed-broker",
            "by_broker_order_id",
            {"orders": {"stop": {"role": "STOP", "broker_order_id": "closed-broker"}}},
            "STOP",
        ),
        (
            "fill_id",
            "closed-fill",
            "by_fill_id",
            {"fills": [{"role": "ENTRY", "fill_id": "closed-fill"}]},
            "ENTRY",
        ),
        (
            "exchange_order_id",
            "closed-exchange",
            "by_broker_order_id",
            {"entry_order": {"role": "ENTRY", "exchange_order_id": "closed-exchange"}},
            "ENTRY",
        ),
    ],
)
def test_closed_only_canonical_strong_ids_are_not_found_when_closed_is_hidden(
    field,
    value,
    index_name,
    row_override,
    role,
):
    row = _row("exec-closed-strong", state=schema.CLOSED_PROVISIONAL, **row_override)
    document = _set_index(
        _document(closed_rows=[row]),
        index_name,
        value,
        {"execution_id": "exec-closed-strong", "role": role},
    )

    result = adapter.resolve_strong_id_v2(document, field, value, include_closed=False)

    assert result.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_closed_only_canonical_close_event_is_unique_or_not_found_by_view():
    row = _close_row(
        _row("exec-closed-close", state=schema.CLOSED_PROVISIONAL),
        "closed-close",
        digest="closed-digest",
    )
    document = _set_index(
        _document(closed_rows=[row]),
        "by_close_event_id",
        "exec-closed-close|closed-close",
        "closed-digest",
    )

    included = adapter.resolve_strong_id_v2(document, "close_event_id", "closed-close")
    excluded = adapter.resolve_strong_id_v2(
        document,
        "close_event_id",
        "closed-close",
        include_closed=False,
    )

    assert included.status == adapter.REGISTRY_LEGACY_UNIQUE
    assert included.collection == "closed_trades"
    assert excluded.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_closed_only_temp_strong_id_is_not_found_when_closed_is_hidden():
    row = _row(
        "exec-temp-closed",
        state=schema.CLOSED_PROVISIONAL,
        client_order_id="temp-closed-client",
    )
    document = _set_index(
        _temp_document(closed_rows=[row]),
        "by_client_order_id",
        "temp-closed-client",
        "exec-temp-closed",
    )

    result = adapter.resolve_strong_id_v2(
        document,
        "client_order_id",
        "temp-closed-client",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_closed_only_temp_close_event_is_not_found_when_closed_is_hidden():
    row = _close_row(_row("exec-temp-closed-close", state=schema.CLOSED_PROVISIONAL), "temp-closed-close")
    document = _set_index(
        _temp_document(closed_rows=[row]),
        "by_close_event_id",
        "exec-temp-closed-close|temp-closed-close",
        "exec-temp-closed-close",
    )

    result = adapter.resolve_strong_id_v2(
        document,
        "close_event_id",
        "temp-closed-close",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_closed_index_corruption_is_conflict_even_when_closed_is_hidden():
    row = _row(
        "exec-corrupt-closed",
        state=schema.CLOSED_PROVISIONAL,
        entry_order={"role": "ENTRY", "client_order_id": "corrupt-closed-client"},
    )
    document = _set_index(
        _document(closed_rows=[row]),
        "by_client_order_id",
        "corrupt-closed-client",
        {"execution_id": "exec-other", "role": "ENTRY"},
    )

    result = adapter.resolve_strong_id_v2(
        document,
        "client_order_id",
        "corrupt-closed-client",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("client_order_id_index_stale",)


def test_closed_close_digest_corruption_is_conflict_even_when_closed_is_hidden():
    row = _close_row(
        _row("exec-corrupt-close", state=schema.CLOSED_PROVISIONAL),
        "corrupt-close",
        digest="correct-digest",
    )
    document = _set_index(
        _document(closed_rows=[row]),
        "by_close_event_id",
        "exec-corrupt-close|corrupt-close",
        "wrong-digest",
    )

    result = adapter.resolve_strong_id_v2(
        document,
        "close_event_id",
        "corrupt-close",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT
    assert result.errors == ("close_event_id_index_stale",)


def test_open_physical_execution_and_closed_strong_id_remain_factually_conflicting():
    open_row = _row("exec-open")
    closed_row = _row(
        "exec-closed-owner",
        state=schema.CLOSED_PROVISIONAL,
        client_order_id="closed-owner-client",
    )
    document = _document(open_rows=[open_row], closed_rows=[closed_row])

    result = adapter.resolve_legacy_trade_v2(
        document,
        execution_id="exec-open",
        client_order_id="closed-owner-client",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_CONFLICT


def test_closed_physical_execution_and_own_strong_id_are_not_found_when_hidden():
    row = _row(
        "exec-closed-own",
        state=schema.CLOSED_PROVISIONAL,
        client_order_id="closed-own-client",
    )
    document = _document(closed_rows=[row])

    result = adapter.resolve_legacy_trade_v2(
        document,
        execution_id="exec-closed-own",
        client_order_id="closed-own-client",
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_NOT_FOUND


def test_closed_only_logical_resolution_remains_not_found_when_hidden():
    logical = "FALCON:FALCON15:BTCUSDT:LONG"
    document = _document(
        closed_rows=[
            _row(
                "exec-closed-logical",
                state=schema.CLOSED_PROVISIONAL,
                logical_trade_id=logical,
            )
        ]
    )

    result = adapter.resolve_legacy_trade_v2(
        document,
        logical_trade_id=logical,
        include_closed=False,
    )

    assert result.status == adapter.REGISTRY_LEGACY_NOT_FOUND
