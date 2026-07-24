from __future__ import annotations

import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
REGISTRY_PATH = ROOT / "trade_registry.py"
_MAIN_FUNCTIONS = None


def _main_function(name):
    global _MAIN_FUNCTIONS
    if _MAIN_FUNCTIONS is None:
        tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
        _MAIN_FUNCTIONS = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
    return _MAIN_FUNCTIONS[name]


def _compile_main_functions(names, namespace):
    nodes = []
    for name in names:
        node = copy.deepcopy(_main_function(name))
        node.decorator_list = []
        nodes.append(node)
    tree = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<closed-identity-residual-guards>", "exec"), namespace)
    return namespace


@pytest.fixture()
def registry_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json")
    )
    spec = importlib.util.spec_from_file_location(
        f"_closed_identity_residual_registry_{tmp_path.name}",
        REGISTRY_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TRADE_REGISTRY_LEGACY_FILE = str(
        tmp_path / "legacy-registry-that-does-not-exist.json"
    )
    return module


def _closed_trade(**updates):
    trade = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-XRP-REAL",
        "client_order_id": "CLIENT-XRP-REAL",
        "broker_order_id": "ORDER-XRP-REAL",
        "order_id": "ORDER-XRP-REAL",
        "entry": 1.0871,
        "qty": 9,
        "closed_at": "2026-07-18T18:37:00-03:00",
    }
    trade.update(updates)
    return trade


def _relation_namespace(registry_module):
    namespace = {
        "json": json,
        "central_trade_registry": registry_module,
    }
    return _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_merge_closed_trade_records_v1",
            "_closed_trade_record_relation_v1",
            "_closed_trade_records_equivalent_v1",
        ],
        namespace,
    )


def test_relation_conflicts_on_shared_lifecycle_with_divergent_client_and_order(
    registry_module,
):
    namespace = _relation_namespace(registry_module)
    left = _closed_trade()
    right = _closed_trade(
        client_order_id="CLIENT-OTHER",
        broker_order_id="ORDER-OTHER",
        order_id="ORDER-OTHER",
    )

    assert (
        namespace["_closed_trade_record_relation_v1"](left, right)
        == "CONFLICT"
    )
    assert (
        namespace["_closed_trade_records_equivalent_v1"](left, right)
        is False
    )


def test_relation_proves_complete_and_client_order_partial_copy_equivalent(
    registry_module,
):
    namespace = _relation_namespace(registry_module)
    complete = _closed_trade()
    partial = copy.deepcopy(complete)
    partial.pop("lifecycle_id")

    assert (
        namespace["_closed_trade_record_relation_v1"](complete, partial)
        == "EQUIVALENT"
    )
    assert (
        namespace["_closed_trade_records_equivalent_v1"](
            complete, partial
        )
        is True
    )


def test_trade_close_outcome_commit_rejects_fresh_identity_conflict_without_write(
    registry_module,
):
    selected = _closed_trade()
    fresh = _closed_trade(
        client_order_id="CLIENT-FRESH-DIVERGENT",
        broker_order_id="ORDER-FRESH-DIVERGENT",
        order_id="ORDER-FRESH-DIVERGENT",
    )
    registry_writes = []
    audit_writes = []
    central_registry = SimpleNamespace(
        closed_trade_identity_state=registry_module.closed_trade_identity_state,
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        save_registry=lambda payload: registry_writes.append(
            copy.deepcopy(payload)
        )
        or True,
    )
    namespace = {
        "json": json,
        "central_trade_registry": central_registry,
        "TRADE_CLOSE_OUTCOME_V1_VERSION": "test-v1",
        "_tco_v1_load_registry": lambda: {
            "closed_trades": [copy.deepcopy(fresh)]
        },
        "_tco_v1_now": lambda: "fixed-now",
        "_tco_v1_atomic_write_json": lambda *args: audit_writes.append(
            ("latest", args)
        ),
        "_tco_v1_append_event": lambda *args: audit_writes.append(
            ("event", args)
        ),
    }
    _compile_main_functions(
        [
            "_closed_trade_identity_state_v1",
            "_merge_closed_trade_records_v1",
            "_closed_trade_record_relation_v1",
            "_closed_trade_records_equivalent_v1",
            "_tco_v1_closed_items",
            "trade_close_outcome_v1_commit",
        ],
        namespace,
    )

    result = namespace["trade_close_outcome_v1_commit"](
        {},
        {"trade": copy.deepcopy(selected)},
        {"ok": True, "status": "OUTCOME_EVALUATED"},
    )

    assert result == {
        "attempted": True,
        "committed": False,
        "status": "CLOSED_TRADE_IDENTITY_CHANGED_BEFORE_UPDATE",
        "candidate_count": 0,
    }
    assert registry_writes == []
    assert audit_writes == []


def test_report_duplicates_uses_proven_equivalence_not_shared_lifecycle(
    registry_module,
):
    namespace = _relation_namespace(registry_module)
    _compile_main_functions(
        ["_trade_registry_report_duplicates"],
        namespace,
    )
    detect = namespace["_trade_registry_report_duplicates"]

    complete = _closed_trade()
    conflict = _closed_trade(
        client_order_id="CLIENT-CONFLICT",
        broker_order_id="ORDER-CONFLICT",
        order_id="ORDER-CONFLICT",
    )
    partial = copy.deepcopy(complete)
    partial.pop("lifecycle_id")

    assert detect([complete, conflict], canonical_closed=True) == []
    equivalent_duplicates = detect(
        [complete, partial], canonical_closed=True
    )
    assert len(equivalent_duplicates) == 1


def test_read_only_closed_identity_audit_rejects_malformed_raw_record_before_merge(
    tmp_path,
):
    calls = []
    registry = {
        "open_trades": {},
        "closed_trades": [_closed_trade(), "malformed-closed-record"],
    }
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: calls.append("load")
        or copy.deepcopy(registry),
        merge_closed_trade_records=lambda rows: calls.append("merge")
        or pytest.fail("merge must not run for malformed raw registry"),
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("registry writer called"),
    )
    namespace = {
        "central_trade_registry": module,
        "_trpsf_v1_iter_trades": lambda *args, **kwargs: pytest.fail(
            "raw records must be shape-validated before conversion"
        ),
        "_closed_trade_identity_state_v1": lambda trade: pytest.fail(
            "identity merge path must not run for malformed raw registry"
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_registry_shape_errors",
            "trade_registry_closed_identity_audit_v1",
        ],
        namespace,
    )

    payload = namespace["trade_registry_closed_identity_audit_v1"]()

    assert calls == ["load"]
    assert payload["ok"] is False
    assert payload["status"] == "CLOSED_IDENTITY_AUDIT_INVALID_REGISTRY_SHAPE"
    assert payload["reason"] == "READ_ONLY_REGISTRY_INVALID_SHAPE"
    assert payload["source_shape_errors"] == [
        "CLOSED_TRADES_INVALID_RECORD"
    ]
    assert payload["safe_to_commit"] is False
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
    assert not (tmp_path / "trade_registry.json").exists()


def test_closed_identity_financial_conflicts_routes_are_read_only_and_show_fields(
    registry_module,
):
    real = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-REAL-1",
        "client_order_id": "CLIENT-REAL-1",
        "order_id": "ORDER-REAL-1",
        "entry": 1.0871,
        "qty": 9,
        "closed_at": "2026-07-18T18:37:00-03:00",
        "outcome_status": "OUTCOME_RECORDED",
        "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
        "outcome_id": "OUTCOME-REAL-1",
        "exit_price": 1.0902,
        "pnl_pct": 0.2851623585686696,
        "fees": 0.5,
        "funding": 0.0,
        "net_pnl": 0.25,
    }
    verify = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "lifecycle_id": "LC-REAL-1",
        "client_order_id": "CLIENT-REAL-1",
        "order_id": "ORDER-REAL-1",
        "entry": 1.0871,
        "qty": 9,
        "closed_at": "2026-07-18T18:37:00-03:00",
        "outcome_status": "OUTCOME_RECORDED",
        "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
        "outcome_id": "OUTCOME-REAL-2",
        "exit_price": 1.0910,
        "pnl_pct": 0.3051623585686696,
        "fees": 0.6,
        "funding": 0.0,
        "net_pnl": 0.35,
    }
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: {
            "open_trades": {},
            "closed_trades": [real, verify],
        },
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("registry writer called"),
    )
    namespace = {
        "central_trade_registry": module,
        "_trpsf_v1_registry_shape_errors": lambda registry: [],
        "_trpsf_v1_iter_trades": lambda value, preserve_closed_collection_keys=False: list(value or []),
        "_closed_trade_identity_state_v1": registry_module.closed_trade_identity_state,
    }
    _compile_main_functions(
        [
            "_trpsf_v1_closed_trade_financial_source_values",
            "_trpsf_v1_closed_trade_outcome_summary",
            "_trpsf_v1_closed_trade_conflict_record_summary",
            "trade_registry_closed_identity_financial_conflicts_v1",
            "build_trade_registry_closed_identity_financial_conflicts_v1_text",
            "trade_registry_closed_identity_financial_conflicts_v1_route",
            "trade_registry_closed_identity_financial_conflicts_v1_text_route",
        ],
        namespace,
    )
    payload = namespace["trade_registry_closed_identity_financial_conflicts_v1"]()
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
    assert payload["broker_called"] is False
    assert payload["no_order_sent_by_this_route"] is True
    assert payload["safe_to_commit"] is False
    assert payload["conflict_count"] == 1
    assert payload["financial_conflict_count"] == 5
    assert payload["conflicts"][0]["conflict_index"] == 0
    assert payload["conflicts"][0]["trade_id"] == real["trade_id"]
    assert "exit_price" in payload["conflicts"][0]["conflicting_values_by_field"]
    assert "pnl_pct" in payload["conflicts"][0]["conflicting_values_by_field"]
    assert payload["conflicts"][0]["records"][0]["bot"] == "FALCON"
    assert payload["conflicts"][0]["records"][0]["registry_index"] == 0

    text, status, headers = namespace["trade_registry_closed_identity_financial_conflicts_v1_text_route"]()
    assert status == 200
    assert "conflict_index=0" in text
    assert "trade_id=FALCON:FALCON15:XRPUSDT:LONG" in text
    assert "exit_price=" in text
    assert "pnl_pct=" in text
    assert "no_order_sent_by_this_route=True" in text


def test_closed_identity_financial_conflicts_block_when_registry_shape_invalid(
    registry_module,
):
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: {
            "open_trades": {},
            "closed_trades": ["invalid"],
        },
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("registry writer called"),
    )
    namespace = {
        "central_trade_registry": module,
        "_trpsf_v1_registry_shape_errors": lambda registry: ["CLOSED_TRADES_INVALID_RECORD"],
        "_trpsf_v1_iter_trades": lambda value, preserve_closed_collection_keys=False: pytest.fail(
            "raw records must be shape-validated before conversion"
        ),
    }
    _compile_main_functions(
        ["trade_registry_closed_identity_financial_conflicts_v1"],
        namespace,
    )

    payload = namespace["trade_registry_closed_identity_financial_conflicts_v1"]()
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
    assert payload["status"] == "CLOSED_IDENTITY_AUDIT_INVALID_REGISTRY_SHAPE"
    assert payload["reason"] == "READ_ONLY_REGISTRY_INVALID_SHAPE"


def test_closed_identity_financial_conflicts_block_when_helpers_missing():
    namespace = {"central_trade_registry": SimpleNamespace()}
    _compile_main_functions(
        ["trade_registry_closed_identity_financial_conflicts_v1"],
        namespace,
    )
    payload = namespace["trade_registry_closed_identity_financial_conflicts_v1"]()
    assert payload["ok"] is False
    assert payload["reason"] == "READ_ONLY_REGISTRY_OR_IDENTITY_HELPER_UNAVAILABLE"
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
