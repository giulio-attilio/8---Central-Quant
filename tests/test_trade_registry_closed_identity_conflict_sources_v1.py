from __future__ import annotations

import ast
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
REGISTRY_PATH = ROOT / "trade_registry.py"


def _main_function(name):
    tree = ast.parse(MAIN_PATH.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }[name]


def _compile_main_functions(names, namespace):
    nodes = []
    for name in names:
        node = copy.deepcopy(_main_function(name))
        node.decorator_list = []
        nodes.append(node)
    tree = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(tree)
    exec(compile(tree, "<closed-identity-conflict-sources>", "exec"), namespace)
    return namespace


@pytest.fixture()
def registry_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CENTRAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TRADE_REGISTRY_FILE", str(tmp_path / "trade_registry.json"))
    spec = importlib.util.spec_from_file_location(
        f"_closed_identity_conflict_sources_{tmp_path.name}",
        REGISTRY_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closed_identity_financial_conflict_sources_are_reported_by_path(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "client_order_id": "FALCON-LIVE-FALCON15-1783693821",
        "order_id": "2075588454201380864",
        "entry": 64107.9,
        "qty": 0.0001,
        "closed_at": "2026-11-07T11:35:46-03:00",
        "data_quality": "HIGH_REAL",
        "close_reason": "STOP",
        "pnl_r": -1.08850668,
        "metadata": {
            "outcome": {
                "close_reason": "BROKER_RECONCILED_CLOSE",
                "pnl_r": -1.26907189,
            }
        },
    }
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: {
            "open_trades": {},
            "closed_trades": [trade],
        },
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES=registry_module.CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES,
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
            "_trpsf_v1_closed_trade_financial_conflict_sources",
            "trade_registry_closed_identity_financial_conflicts_v1",
            "build_trade_registry_closed_identity_financial_conflicts_v1_text",
        ],
        namespace,
    )

    payload = namespace["trade_registry_closed_identity_financial_conflicts_v1"]()
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
    assert payload["automatic_changes"] is False
    assert payload["broker_called"] is False
    assert payload["no_order_sent_by_this_route"] is True
    assert payload["conflict_count"] == 1
    assert payload["financial_conflict_count"] == 2

    conflict = payload["conflicts"][0]
    assert conflict["financial_conflict_fields"] == ["close_reason", "pnl_r"]
    assert conflict["conflicting_value_sources_by_field"]["close_reason"] == [
        {
            "canonical_field": "close_reason",
            "alias": "close_reason",
            "path": "trade.close_reason",
            "value": "STOP",
        },
        {
            "canonical_field": "close_reason",
            "alias": "close_reason",
            "path": "trade.metadata.outcome.close_reason",
            "value": "BROKER_RECONCILED_CLOSE",
        },
    ]
    assert conflict["conflicting_value_sources_by_field"]["pnl_r"] == [
        {
            "canonical_field": "pnl_r",
            "alias": "pnl_r",
            "path": "trade.pnl_r",
            "value": -1.08850668,
        },
        {
            "canonical_field": "pnl_r",
            "alias": "pnl_r",
            "path": "trade.metadata.outcome.pnl_r",
            "value": -1.26907189,
        },
    ]

    text = namespace["build_trade_registry_closed_identity_financial_conflicts_v1_text"]()
    assert "field=close_reason path=trade.close_reason alias=close_reason value=STOP" in text
    assert "field=close_reason path=trade.metadata.outcome.close_reason alias=close_reason value=BROKER_RECONCILED_CLOSE" in text
    assert "field=pnl_r path=trade.pnl_r alias=pnl_r value=-1.08850668" in text
    assert "field=pnl_r path=trade.metadata.outcome.pnl_r alias=pnl_r value=-1.26907189" in text
