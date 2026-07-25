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


def _compile_r_recalculation_namespace(registry_module):
    namespace = {
        "central_trade_registry": SimpleNamespace(
            CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES=
                registry_module.CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES,
        ),
    }
    _compile_main_functions(
        [
            "_trpsf_v1_closed_trade_allowed_containers",
            "_trpsf_v1_closed_trade_risk_input_alias_families",
            "_trpsf_v1_closed_trade_risk_input_sources",
            "_trpsf_v1_closed_trade_reported_r_candidate_sources",
            "_trpsf_v1_truncated_number",
            "_trpsf_v1_closed_trade_risk_input_comparison_value",
            "_trpsf_v1_closed_trade_resolve_risk_input_field",
            "_trpsf_v1_closed_trade_r_recalculation",
        ],
        namespace,
    )
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
            "_trpsf_v1_closed_trade_allowed_containers",
            "_trpsf_v1_closed_trade_risk_input_alias_families",
            "_trpsf_v1_closed_trade_risk_input_sources",
            "_trpsf_v1_closed_trade_reported_r_candidate_sources",
            "_trpsf_v1_truncated_number",
            "_trpsf_v1_closed_trade_risk_input_comparison_value",
            "_trpsf_v1_closed_trade_resolve_risk_input_field",
            "_trpsf_v1_closed_trade_r_recalculation",
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


def test_closed_identity_financial_conflict_r_recalculation_short_with_initial_stop(
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
        "client_order_id": "FALCON-LIVE-FALCON15-0001",
        "order_id": "2075588454201380865",
        "entry": 100.0,
        "initial_stop": 110.0,
        "qty": 1.0,
        "exit_price": 108.0,
        "pnl_r": -0.75,
        "metadata": {
            "outcome": {
                "r_multiple": -0.9,
            }
        },
    }
    namespace = _compile_r_recalculation_namespace(registry_module)
    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)
    assert result["status"] == "R_RECALCULATION_READY"
    assert result["initial_risk_per_unit"] == 10.0
    assert result["gross_r"] == -0.8
    assert result["gross_r_ready"] is True
    assert result["net_r_ready"] is False
    assert result["net_r_block_reasons"] == ["INITIAL_RISK_USDT_MISSING", "NET_PNL_MISSING"]
    assert result["partial_diagnostics"] is True
    assert result["required_missing_inputs"] == []
    assert result["required_conflicting_inputs"] == []
    assert result["optional_conflicting_inputs"] == []
    assert result["calculation_performed"] is True
    assert result["risk_formula"] == "(entry - exit_price) / (initial_stop - entry)"
    assert result["candidate_match_tolerance"] == 1e-8
    assert result["gross_pnl_from_prices"] == -8.0
    assert result["net_r"] is None
    assert result["missing_inputs"] == []
    assert result["conflicting_inputs"] == []
    assert result["invalid_inputs"] == []
    assert result["reported_r_candidates"] == [
        {
            "canonical_field": "pnl_r",
            "alias": "pnl_r",
            "path": "trade.pnl_r",
            "value": -0.75,
        },
        {
            "canonical_field": "result_r",
            "alias": "r_multiple",
            "path": "trade.metadata.outcome.r_multiple",
            "value": -0.9,
        },
    ]
    assert any(
        match["candidate"] == -0.75
        and match["absolute_difference"] == pytest.approx(0.05)
        and match["gross_r"] == -0.8
        and match["matches_within_tolerance"] is False
        for match in result["candidate_matches"]
    )
    assert result["input_resolution_by_field"]["entry"]["status"] == "RESOLVED"
    assert result["input_resolution_by_field"]["initial_stop"]["normalized_values"] == [110.0]
    assert result["risk_input_sources_by_field"]["initial_stop"][0]["path"] == "trade.initial_stop"
    assert result["risk_input_sources_by_field"]["side"][0]["path"] == "trade.side"


def test_closed_identity_financial_conflict_r_recalculation_long_with_initial_stop(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:LONG",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry": 100.0,
        "initial_stop": 90.0,
        "qty": 1.0,
        "exit_price": 108.0,
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_READY"
    assert result["gross_r"] == pytest.approx(0.8)
    assert result["gross_r_ready"] is True
    assert result["initial_risk_per_unit"] == pytest.approx(10.0)
    assert result["risk_formula"] == "(exit_price - entry) / (entry - initial_stop)"
    assert result["candidate_matches"] == []


def test_closed_identity_financial_conflict_r_recalculation_missing_stop(
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
        "client_order_id": "FALCON-LIVE-FALCON15-0002",
        "order_id": "2075588454201380866",
        "entry": 100.0,
        "qty": 1.0,
        "exit_price": 108.0,
        "pnl_r": -0.8,
        "metadata": {
            "outcome": {
                "r_multiple": -0.8,
            }
        },
    }
    namespace = _compile_r_recalculation_namespace(registry_module)
    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)
    assert result["status"] == "R_RECALCULATION_INPUTS_INCOMPLETE"
    assert result["required_missing_inputs"] == ["initial_stop"]
    assert result["required_conflicting_inputs"] == []
    assert result["missing_inputs"] == ["initial_stop"]
    assert result["conflicting_inputs"] == []
    assert result["calculation_performed"] is False
    assert result["gross_r_ready"] is False
    assert result["gross_r"] is None
    assert result["candidate_matches"] == []


@pytest.mark.parametrize(
    ("side", "initial_stop", "expected_invalid"),
    [
        ("SHORT", 90.0, "INITIAL_STOP_NOT_PROTECTIVE_FOR_SHORT"),
        ("LONG", 110.0, "INITIAL_STOP_NOT_PROTECTIVE_FOR_LONG"),
    ],
)
def test_closed_identity_financial_conflict_r_recalculation_invalid_initial_stop_direction(
    registry_module,
    side,
    initial_stop,
    expected_invalid,
):
    trade = {
        "trade_id": f"FALCON:FALCON15:BTCUSDT:{side}",
        "status": "CLOSED",
        "side": side,
        "entry": 100.0,
        "initial_stop": initial_stop,
        "exit_price": 108.0,
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_INVALID_INITIAL_RISK"
    assert expected_invalid in result["invalid_inputs"]
    assert result["gross_r"] is None
    assert result["gross_r_ready"] is False
    assert result["candidate_matches"] == []
    assert result["calculation_performed"] is False


def test_closed_identity_financial_conflict_r_recalculation_conflicting_initial_stop_blocks(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "initial_stop": 110.0,
        "metadata": {"outcome": {"initial_stop": 111.0}},
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_INPUTS_INCOMPLETE"
    assert result["required_missing_inputs"] == []
    assert result["required_conflicting_inputs"] == ["initial_stop"]
    assert result["optional_conflicting_inputs"] == []
    assert result["missing_inputs"] == []
    assert result["conflicting_inputs"] == ["initial_stop"]
    assert result["gross_r"] is None
    assert result["candidate_matches"] == []
    assert result["input_resolution_by_field"]["initial_stop"]["status"] == "CONFLICT"
    assert result["input_resolution_by_field"]["initial_stop"]["normalized_values"] == [110.0, 111.0]


def test_closed_identity_financial_conflict_r_recalculation_matching_entry_sources_resolve(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "metadata": {"entry_price": 100.0},
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_READY"
    assert result["input_resolution_by_field"]["entry"]["status"] == "RESOLVED"
    assert result["input_resolution_by_field"]["entry"]["conflict"] is False
    assert result["input_resolution_by_field"]["entry"]["normalized_values"] == [100.0, 100.0]


@pytest.mark.parametrize(
    ("patch", "expected_field"),
    [
        ({"metadata": {"outcome": {"exit": 109.0}}}, "exit_price"),
        ({"metadata": {"direction": "LONG"}}, "side"),
    ],
)
def test_closed_identity_financial_conflict_r_recalculation_required_conflicts_block(
    registry_module,
    patch,
    expected_field,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
    }
    trade.update(patch)
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_INPUTS_INCOMPLETE"
    assert result["gross_r"] is None
    assert result["candidate_matches"] == []
    assert expected_field in result["required_conflicting_inputs"]


def test_closed_identity_financial_conflict_r_recalculation_required_entry_conflict_blocks(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "metadata": {"entry_price": 101.0},
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_INPUTS_INCOMPLETE"
    assert result["gross_r"] is None
    assert result["required_conflicting_inputs"] == ["entry"]
    assert result["gross_r_ready"] is False


def test_closed_identity_financial_conflict_r_recalculation_optional_net_r_fields_fail_closed(
    registry_module,
):
    namespace = _compile_r_recalculation_namespace(registry_module)

    missing_risk_trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "net_pnl": -8.0,
    }
    missing_risk_result = namespace["_trpsf_v1_closed_trade_r_recalculation"](missing_risk_trade)
    assert missing_risk_result["status"] == "R_RECALCULATION_READY"
    assert missing_risk_result["gross_r"] == -0.8
    assert missing_risk_result["net_r"] is None
    assert "INITIAL_RISK_USDT_MISSING" in missing_risk_result["net_r_block_reasons"]

    non_positive_risk_trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "initial_risk_usdt": 0.0,
        "net_pnl": -8.0,
    }
    non_positive_risk_result = namespace["_trpsf_v1_closed_trade_r_recalculation"](non_positive_risk_trade)
    assert non_positive_risk_result["gross_r"] == -0.8
    assert non_positive_risk_result["net_r"] is None
    assert "INITIAL_RISK_USDT_NOT_POSITIVE" in non_positive_risk_result["net_r_block_reasons"]

    conflicting_net_pnl_trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "initial_risk_usdt": 10.0,
        "net_pnl": -8.0,
        "pnl_r": -0.8,
        "metadata": {"outcome": {"net_pnl": -7.5}},
    }
    conflicting_net_pnl_result = namespace["_trpsf_v1_closed_trade_r_recalculation"](conflicting_net_pnl_trade)
    assert conflicting_net_pnl_result["status"] == "R_RECALCULATION_READY"
    assert conflicting_net_pnl_result["gross_r"] == -0.8
    assert conflicting_net_pnl_result["net_r"] is None
    assert conflicting_net_pnl_result["required_conflicting_inputs"] == []
    assert "net_pnl" in conflicting_net_pnl_result["optional_conflicting_inputs"]
    assert "NET_PNL_CONFLICT" in conflicting_net_pnl_result["net_r_block_reasons"]
    assert conflicting_net_pnl_result["candidate_matches"] != []


def test_closed_identity_financial_conflict_r_recalculation_optional_initial_risk_conflict_does_not_block_gross_r(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "initial_risk_usdt": 10.0,
        "net_pnl": -8.0,
        "metadata": {"outcome": {"risk_usdt": 12.0}},
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_READY"
    assert result["gross_r"] == -0.8
    assert result["net_r"] is None
    assert "initial_risk_usdt" in result["optional_conflicting_inputs"]
    assert "INITIAL_RISK_USDT_CONFLICT" in result["net_r_block_reasons"]


def test_closed_identity_financial_conflict_r_recalculation_optional_qty_conflict_does_not_block_gross_r(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "qty": 1.0,
        "metadata": {"outcome": {"closed_qty": 2.0}},
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_READY"
    assert result["gross_r"] == -0.8
    assert result["gross_pnl_from_prices"] is None
    assert "qty" in result["optional_conflicting_inputs"]


def test_closed_identity_financial_conflict_r_recalculation_optional_fees_conflict_does_not_block_gross_r(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "initial_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
        "fees": 0.4,
        "metadata": {"fee": 0.6},
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_READY"
    assert result["gross_r"] == -0.8
    assert "fees" in result["optional_conflicting_inputs"]


def test_closed_identity_financial_conflict_r_recalculation_does_not_promote_auxiliary_stops(
    registry_module,
):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "status": "CLOSED",
        "entry": 100.0,
        "stop": 110.0,
        "stop_loss": 110.0,
        "original_stop": 110.0,
        "side": "SHORT",
        "exit_price": 108.0,
    }
    namespace = _compile_r_recalculation_namespace(registry_module)

    result = namespace["_trpsf_v1_closed_trade_r_recalculation"](trade)

    assert result["status"] == "R_RECALCULATION_INPUTS_INCOMPLETE"
    assert result["required_missing_inputs"] == ["initial_stop"]
    assert result["required_conflicting_inputs"] == []
    assert result["optional_conflicting_inputs"] == []
    assert result["missing_inputs"] == ["initial_stop"]
    assert result["input_resolution_by_field"]["initial_stop"]["status"] == "MISSING"
    assert result["risk_input_sources_by_field"]["stop"][0]["path"] == "trade.stop"
    assert result["risk_input_sources_by_field"]["stop_loss"][0]["path"] == "trade.stop_loss"
    assert result["risk_input_sources_by_field"]["original_stop"][0]["path"] == "trade.original_stop"
