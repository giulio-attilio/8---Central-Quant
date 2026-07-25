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


def _write_jsonl(path, rows):
    lines = []
    for row in rows:
        if isinstance(row, str):
            lines.append(row)
        else:
            lines.append(json.dumps(row, ensure_ascii=False))
    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    path.write_text(payload, encoding="utf-8")


def _compile_stop_evidence_namespace(
    registry_module,
    tmp_path,
    trade=None,
    closed_trades=None,
    source_rows_by_file=None,
    request_args=None,
):
    source_rows_by_file = source_rows_by_file or {}
    for file_name, rows in source_rows_by_file.items():
        _write_jsonl(tmp_path / file_name, rows)
    if closed_trades is None:
        closed_trades = [] if trade is None else [copy.deepcopy(trade)]
    normalized_closed_trades = []
    for index, candidate in enumerate(closed_trades):
        if not isinstance(candidate, dict):
            continue
        normalized = copy.deepcopy(candidate)
        normalized.setdefault("registry_index", 59 if len(closed_trades) == 1 else index)
        normalized_closed_trades.append(normalized)
    registry = {
        "open_trades": {},
        "closed_trades": normalized_closed_trades,
    }
    module = SimpleNamespace(
        load_registry_raw_read_only=lambda: registry,
        load_registry=lambda: pytest.fail("mutating loader called"),
        save_registry=lambda payload: pytest.fail("registry writer called"),
        merge_closed_trade_records=registry_module.merge_closed_trade_records,
        CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES=registry_module.CLOSED_TRADE_FINANCIAL_ALIAS_FAMILIES,
    )
    namespace = {
        "central_trade_registry": module,
        "CENTRAL_DATA_DIR": tmp_path,
        "Path": Path,
        "json": json,
        "request": SimpleNamespace(args=request_args or {}),
        "_trpsf_v1_truncated_number": lambda value: float(value) if isinstance(value, (int, float, str)) and str(value).strip() not in {"", "None"} else None,
    }
    namespace["_test_registry_state"] = registry
    _compile_main_functions(
        [
            "_trpsf_v1_truncated_number",
            "_trpsf_v1_closed_trade_stop_evidence_alias_families",
            "_trpsf_v1_stop_evidence_alias_families",
            "_trpsf_v1_stop_evidence_candidate_paths",
            "_trpsf_v1_stop_evidence_iter_trades",
            "_trpsf_v1_stop_evidence_numeric",
            "_trpsf_v1_stop_evidence_scan_limits",
            "_trpsf_v1_stop_evidence_cap_list",
            "_trpsf_v1_stop_evidence_public_identity",
            "_trpsf_v1_stop_evidence_public_selection",
            "_trpsf_v1_stop_evidence_public_limits",
            "_trpsf_v1_stop_evidence_apply_public_limits",
            "_trpsf_v1_stop_evidence_identity_fields",
            "_trpsf_v1_stop_evidence_identity_tokens",
            "_trpsf_v1_stop_evidence_trade_identity",
            "_trpsf_v1_stop_evidence_trade_selector",
            "_trpsf_v1_stop_evidence_event_alias",
            "_trpsf_v1_stop_evidence_path_components",
            "_trpsf_v1_stop_evidence_is_registry_pre_execution_plan",
            "_trpsf_v1_stop_evidence_strong_identity_tokens",
            "_trpsf_v1_stop_evidence_line_should_parse",
            "_trpsf_v1_stop_evidence_record_identity_values",
            "_trpsf_v1_stop_evidence_record_matches_trade",
            "_trpsf_v1_stop_evidence_context",
            "_trpsf_v1_stop_evidence_event_phase",
            "_trpsf_v1_stop_evidence_parse_timestamp",
            "_trpsf_v1_stop_evidence_temporal_relation",
            "_trpsf_v1_stop_evidence_extract_occurrences",
            "_trpsf_v1_stop_evidence_scan_file",
            "_trpsf_v1_stop_evidence_load_registry_trade",
            "_trpsf_v1_stop_evidence_reported_r_candidates",
            "_trpsf_v1_closed_trade_stop_evidence_v1",
            "build_trade_registry_closed_identity_stop_evidence_v1_text",
            "trade_registry_closed_identity_stop_evidence_v1_route",
            "trade_registry_closed_identity_stop_evidence_v1_text_route",
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


def _base_stop_evidence_trade(**updates):
    trade = {
        "trade_id": "FALCON:FALCON15:BTCUSDT:SHORT",
        "lifecycle_id": "LC-BTC-001",
        "client_order_id": "FALCON-LIVE-FALCON15-1783693821",
        "order_id": "2075588454201380864",
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "entry": 100.0,
        "exit_price": 108.0,
        "opened_at": "2026-11-07T10:54:00-03:00",
        "closed_at": "2026-11-07T11:35:46-03:00",
        "pnl_r": -0.81,
        "result_r": -0.77,
        "metadata": {"outcome": {"r_multiple": -0.73}},
    }
    trade.update(updates)
    return trade


def _registry_first_closed_trade(namespace):
    registry_state = namespace.get("_test_registry_state") or {}
    closed_trades = registry_state.get("closed_trades") or []
    assert closed_trades and isinstance(closed_trades[0], dict)
    return closed_trades[0]


def test_stop_evidence_route_lifecycle_id_exact_finds_factual_initial_stop(registry_module, tmp_path):
    trade = _base_stop_evidence_trade(sl=107.0)
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "metadata": {"outcome": {"initial_stop": 106.0}},
                }
            ]
        },
        request_args={"lifecycle_id": trade["lifecycle_id"], "registry_index": "59"},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"], "registry_index": 59}
    )

    assert payload["status"] == "STOP_EVIDENCE_READY"
    assert payload["factual_initial_stop_found"] is True
    assert payload["factual_initial_stop"] == pytest.approx(106.0)
    assert payload["safe_to_use_for_r_recalculation"] is True
    assert payload["calculated_gross_r"] == pytest.approx(-1.3333333333333333)
    assert payload["factual_initial_stop_origin"]["source_file"] == "history_events.jsonl"
    assert any(
        item["classification"] == "INITIAL_STOP_CANDIDATE"
        and item["correlation_strength"] == "STRONG"
        and item["temporal_within_priority_window"] is True
        for item in payload["evidence"]
    )


def test_stop_evidence_route_client_order_and_order_exact_find_factual_stop(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_CREATED",
                    "timestamp": "2026-11-07T10:54:10-03:00",
                    "client_order_id": trade["client_order_id"],
                    "order_id": trade["order_id"],
                    "initial_stop": 105.0,
                }
            ]
        },
        request_args={"client_order_id": trade["client_order_id"], "order_id": trade["order_id"]},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={
            "client_order_id": trade["client_order_id"],
            "order_id": trade["order_id"],
        }
    )
    assert payload["status"] == "STOP_EVIDENCE_READY"
    assert payload["factual_initial_stop_found"] is True
    assert payload["factual_initial_stop"] == pytest.approx(105.0)


def test_stop_evidence_route_rejects_same_trade_id_with_divergent_lifecycle_event(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:25-03:00",
                    "trade_id": trade["trade_id"],
                    "lifecycle_id": "LC-BTC-DIVERGENT",
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["status"] == "STOP_EVIDENCE_NO_FACTUAL_INITIAL_STOP"
    assert payload["factual_initial_stop_found"] is False
    assert any(
        event["rejection_reason"] == "STRONG_IDENTITY_MISMATCH"
        for event in payload["rejected_events"]
    )


def test_stop_evidence_route_blocks_ambiguity_when_trade_id_maps_two_closed_trades(registry_module, tmp_path):
    trade_a = _base_stop_evidence_trade(
        lifecycle_id="LC-BTC-001",
        client_order_id="FALCON-LIVE-FALCON15-A",
        order_id="2075588454201381001",
    )
    trade_b = _base_stop_evidence_trade(
        lifecycle_id="LC-BTC-002",
        client_order_id="FALCON-LIVE-FALCON15-B",
        order_id="2075588454201381002",
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        closed_trades=[trade_a, trade_b],
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"trade_id": trade_a["trade_id"]}
    )
    assert payload["status"] == "STOP_EVIDENCE_TRADE_IDENTITY_AMBIGUOUS"
    assert payload["safe_to_use_for_r_recalculation"] is False


def test_stop_evidence_route_does_not_select_trade_by_symbol_and_side_only(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"symbol": trade["symbol"], "side": trade["side"]}
    )
    assert payload["status"] == "STOP_EVIDENCE_TRADE_NOT_FOUND"
    assert payload["factual_initial_stop_found"] is False


def test_stop_evidence_route_event_with_trade_id_only_is_weak_and_not_factual(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:30-03:00",
                    "trade_id": trade["trade_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["status"] == "STOP_EVIDENCE_NO_FACTUAL_INITIAL_STOP"
    assert payload["factual_initial_stop_found"] is False
    assert any(
        item["classification"] == "INITIAL_STOP_CANDIDATE"
        and item["correlation_strength"] == "WEAK"
        for item in payload["evidence"]
    )


def test_stop_evidence_route_rejects_event_with_divergent_strong_id(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:35-03:00",
                    "trade_id": trade["trade_id"],
                    "client_order_id": trade["client_order_id"],
                    "order_id": "ORDER-DIVERGENT",
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"client_order_id": trade["client_order_id"], "order_id": trade["order_id"]}
    )
    assert payload["factual_initial_stop_found"] is False
    assert any(
        event["rejection_reason"] == "STRONG_IDENTITY_MISMATCH"
        for event in payload["rejected_events"]
    )


def test_stop_evidence_unknown_expected_lifecycle_keeps_strong_client_order_correlation(
    registry_module,
    tmp_path,
):
    trade = _base_stop_evidence_trade(lifecycle_id=None)
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": "LC-EXTERNAL-ONLY",
                    "client_order_id": trade["client_order_id"],
                    "order_id": trade["order_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"client_order_id": trade["client_order_id"], "order_id": trade["order_id"]}
    )
    candidates = [
        item
        for item in payload["evidence"]
        if item.get("classification") == "INITIAL_STOP_CANDIDATE"
        and item.get("source_file") == "decision_log.jsonl"
    ]
    assert candidates
    assert candidates[0]["correlation_strength"] == "STRONG"
    assert candidates[0]["identity_unknown_expected_fields"] == ["lifecycle_id"]
    assert candidates[0]["identity_mismatch_fields"] == []
    assert candidates[0]["identity_match_fields"] == ["client_order_id", "order_id"]
    assert candidates[0]["identity_absent_in_event_fields"] == []
    assert "correlation_match_flags" not in candidates[0]
    assert payload["trade"]["lifecycle_id"] is None
    assert not any(
        event.get("rejection_reason") == "STRONG_IDENTITY_MISMATCH"
        for event in payload["rejected_events"]
    )


def test_stop_evidence_rejects_known_client_order_id_mismatch(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "client_order_id": "CLIENT-DIVERGENT",
                    "order_id": trade["order_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    rejections = [
        event
        for event in payload["rejected_events"]
        if event.get("rejection_reason") == "STRONG_IDENTITY_MISMATCH"
    ]
    assert rejections
    assert "client_order_id" in (rejections[0].get("identity_mismatch_fields") or [])
    assert isinstance(rejections[0].get("identity_match_fields"), list)
    assert isinstance(rejections[0].get("identity_unknown_expected_fields"), list)
    assert isinstance(rejections[0].get("identity_absent_in_event_fields"), list)


def test_stop_evidence_rejects_known_order_id_mismatch(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "client_order_id": trade["client_order_id"],
                    "order_id": "ORDER-DIVERGENT-EXPLICIT",
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert any(
        event.get("rejection_reason") == "STRONG_IDENTITY_MISMATCH"
        and "order_id" in (event.get("identity_mismatch_fields") or [])
        for event in payload["rejected_events"]
    )


def test_stop_evidence_route_classifies_sl_alias_as_current_stop(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "STOP_SET",
                    "timestamp": "2026-11-07T10:54:40-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "sl": 107.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert any(
        item["classification"] == "CURRENT_STOP" and item["alias"] == "sl"
        for item in payload["evidence"]
    )


def test_stop_evidence_registry_pre_execution_sl_is_candidate_but_not_factual(registry_module, tmp_path):
    trade = _base_stop_evidence_trade(
        metadata={
            "execution_decision": {
                "auto_real_execution_bridge_v1": {
                    "payload": {
                        "sl": 64440.46571428572,
                    },
                    "timestamp": "2026-07-10T11:30:00-03:00",
                }
            },
            "outcome": {"r_multiple": -0.73},
        }
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"], "registry_index": 59}
    )
    pre_execution_items = [
        item for item in payload["evidence"]
        if item.get("path") == "metadata.execution_decision.auto_real_execution_bridge_v1.payload.sl"
    ]
    assert pre_execution_items
    assert pre_execution_items[0]["classification"] == "INITIAL_STOP_CANDIDATE"
    assert pre_execution_items[0]["source_supports_factual_initial_stop"] is False
    assert pre_execution_items[0]["evidence_reason"] == "PRE_EXECUTION_PLAN_WITHOUT_STRONG_EXECUTION_IDENTITY"
    assert payload["factual_initial_stop_found"] is False


def test_stop_evidence_route_does_not_classify_result_closed_last_update_as_stop(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:45-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "result": 1,
                    "closed": 2,
                    "last_update": 3,
                    "realized_pnl": -4,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert not any(item["source_file"] == "history_events.jsonl" for item in payload["evidence"])


def test_stop_evidence_route_does_not_promote_stop_update(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "timeline.jsonl": [
                {
                    "event_type": "STOP_UPDATE",
                    "timestamp": "2026-11-07T10:59:00-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "metadata": {"stop": 107.5},
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert any(item["classification"] == "STOP_UPDATE" for item in payload["evidence"])
    assert payload["factual_initial_stop_found"] is False


def test_stop_evidence_route_does_not_promote_disaster_stop(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "execution_engine_log.jsonl": [
                {
                    "event_type": "DISASTER_STOP_TRIGGERED",
                    "timestamp": "2026-11-07T10:58:00-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "stop_loss": 112.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert any(item["classification"] == "DISASTER_STOP" for item in payload["evidence"])
    assert payload["factual_initial_stop_found"] is False


def test_stop_evidence_route_blocks_multiple_divergent_strong_initial_stops(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:10-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ],
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:15-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 107.0,
                }
            ],
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["status"] == "STOP_EVIDENCE_CONFLICTING_INITIAL_STOPS"
    assert payload["factual_initial_stop_found"] is False
    assert payload["safe_to_use_for_r_recalculation"] is False
    assert payload["strong_candidate_count"] == 2


def test_stop_evidence_route_reports_dynamic_r_candidates_from_trade(registry_module, tmp_path):
    trade = _base_stop_evidence_trade(
        pnl_r=-0.42,
        result_r=-0.52,
        metadata={"outcome": {"r_multiple": -0.62}},
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    values = {candidate["alias"]: candidate["value"] for candidate in payload["reported_r_candidates"]}
    assert values["pnl_r"] == pytest.approx(-0.42)
    assert values["result_r"] == pytest.approx(-0.52)
    assert values["r_multiple"] == pytest.approx(-0.62)
    assert all("absolute_difference" in candidate for candidate in payload["reported_r_candidates"])


def test_stop_evidence_route_has_no_hard_coded_btc_r_constants(registry_module, tmp_path):
    trade = _base_stop_evidence_trade(
        pnl_r=0.12345,
        result_r=0.23456,
        metadata={"outcome": {"r_multiple": 0.34567}},
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert "reported_pnl_r" not in payload["comparison"]
    assert "reported_r_multiple" not in payload["comparison"]
    assert not any(
        abs(candidate["value"] - (-1.26907189)) < 1e-12
        or abs(candidate["value"] - (-1.08850668)) < 1e-12
        for candidate in payload["reported_r_candidates"]
    )


def test_stop_evidence_route_reports_malformed_jsonl_in_diagnostics(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                "{ malformed_json_line",
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                },
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["malformed_record_count"] >= 1
    assert payload["status"] == "STOP_EVIDENCE_READY"


def test_stop_evidence_route_truncation_remains_fail_closed(registry_module, tmp_path, monkeypatch):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "4096")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "4096")
    trade = _base_stop_evidence_trade()
    rows = [
        {
            "event_type": "HEARTBEAT",
            "timestamp": "2026-11-07T10:54:10-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "sequence": index,
            "padding": "x" * 400,
        }
        for index in range(120)
    ]
    rows.append(
        {
            "event_type": "ENTRY_PLAN_SET",
            "timestamp": "2026-11-07T10:54:20-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "initial_stop": 106.0,
        }
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={"history_events.jsonl": rows},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["scan_truncated"] is True
    assert payload["status"] == "STOP_EVIDENCE_SOURCE_READ_ERROR"
    assert payload["safe_to_use_for_r_recalculation"] is False
    assert isinstance(payload.get("bytes_scanned"), int)
    assert isinstance(payload.get("total_file_bytes"), int)


def test_stop_evidence_route_large_unrelated_stream_does_not_force_source_error_when_scan_complete(
    registry_module,
    tmp_path,
):
    trade = _base_stop_evidence_trade()
    rows = [
        {
            "event_type": "HEARTBEAT",
            "timestamp": "2026-11-07T10:54:10-03:00",
            "lifecycle_id": f"OTHER-{index}",
            "sequence": index,
        }
        for index in range(500)
    ]
    rows.append(
        {
            "event_type": "ENTRY_PLAN_SET",
            "timestamp": "2026-11-07T10:54:20-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "initial_stop": 106.0,
        }
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={"history_events.jsonl": rows},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["scan_truncated"] is False
    assert payload["status"] == "STOP_EVIDENCE_READY"
    assert payload["source_read_errors"] == []


def test_stop_evidence_route_is_read_only_and_exposes_security_flags(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={},
        request_args={"lifecycle_id": trade["lifecycle_id"]},
    )

    payload, status_code, headers = namespace["trade_registry_closed_identity_stop_evidence_v1_route"]()
    assert status_code == 200
    assert headers["Cache-Control"] == "no-store"
    assert payload["read_only"] is True
    assert payload["write_executed"] is False
    assert payload["registry_write"] is False
    assert payload["broker_called"] is False
    assert payload["no_order_sent_by_this_route"] is True
    assert isinstance(payload["sources_checked"], list)
    assert isinstance(payload["sources_missing"], list)
    assert payload["trade_selection"] is not None
    assert "selected_trade" not in payload["trade_selection"]
    assert set(payload["trade_selection"].keys()) == {
        "status",
        "selection_reason",
        "identity_strength",
        "candidate_count",
        "compatible_candidate_count",
        "selected_identity",
        "mismatch_count",
        "mismatch_summary_truncated",
    }
    assert isinstance(payload.get("mismatch_diagnostic_count"), int)
    assert isinstance(payload.get("rejected_event_count"), int)
    assert isinstance(payload.get("evidence_count"), int)


def test_stop_evidence_route_public_diagnostic_limits_are_applied(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    rows = []
    for index in range(140):
        rows.append(
            {
                "event_type": "ENTRY_PLAN_SET",
                "timestamp": "2026-11-07T10:54:20-03:00",
                "lifecycle_id": trade["lifecycle_id"],
                "initial_stop": 106.0,
                "sequence": index,
            }
        )
    for index in range(80):
        rows.append(
            {
                "event_type": "ENTRY_PLAN_SET",
                "timestamp": "2026-11-07T10:54:20-03:00",
                "client_order_id": trade["client_order_id"],
                "order_id": f"ORDER-MISMATCH-{index}",
                "initial_stop": 106.0,
            }
        )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={"history_events.jsonl": rows},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"client_order_id": trade["client_order_id"], "order_id": trade["order_id"]}
    )
    assert payload["evidence_count"] > 100
    assert payload["evidence_truncated"] is True
    assert len(payload["evidence"]) == 100
    assert payload["rejected_event_count"] > 25
    assert payload["rejected_events_truncated"] is True
    assert len(payload["rejected_events"]) == 25


def test_stop_evidence_route_text_exposes_counters_and_scan_metrics(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "history_events.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
        request_args={"lifecycle_id": trade["lifecycle_id"]},
    )

    text = namespace["build_trade_registry_closed_identity_stop_evidence_v1_text"]()
    assert "bytes_scanned=" in text
    assert "total_file_bytes=" in text
    assert "mismatch_diagnostic_count=" in text
    assert "rejected_event_count=" in text
    assert "evidence_count=" in text


def test_stop_evidence_total_budget_never_exceeds_configured_cap_and_remaining_is_consistent(
    registry_module,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "4096")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "5000")
    trade = _base_stop_evidence_trade()
    noisy_rows = [
        {
            "event_type": "HEARTBEAT",
            "timestamp": "2026-11-07T10:54:10-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "payload": "x" * 300,
        }
        for _ in range(120)
    ]
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": noisy_rows,
            "execution_log.jsonl": noisy_rows,
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["total_scan_budget_bytes"] == 5000
    assert payload["bytes_scanned"] <= payload["total_scan_budget_bytes"]
    assert payload["total_scan_budget_remaining_bytes"] == (
        payload["total_scan_budget_bytes"] - payload["bytes_scanned"]
    )
    scanned_stats = [
        stat
        for stat in payload["source_scan_stats"]
        if stat.get("source_scan_budget_bytes", 0) > 0
    ]
    assert scanned_stats
    remaining = payload["total_scan_budget_bytes"]
    for stat in scanned_stats:
        assert stat["source_scan_budget_bytes"] <= remaining
        assert stat["bytes_scanned"] <= stat["source_scan_budget_bytes"]
        remaining -= stat["bytes_scanned"]
    assert remaining == payload["total_scan_budget_remaining_bytes"]


def test_stop_evidence_missing_source_does_not_consume_total_budget(registry_module, tmp_path, monkeypatch):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "2048")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "4096")
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    missing_stats = [
        stat
        for stat in payload["source_scan_stats"]
        if stat.get("reason") == "SOURCE_NOT_FOUND"
    ]
    assert missing_stats
    assert all(stat["source_scan_budget_bytes"] == 0 for stat in missing_stats)
    assert all(stat["bytes_scanned"] == 0 for stat in missing_stats)
    assert payload["bytes_scanned"] <= payload["total_scan_budget_bytes"]
    assert payload["total_scan_budget_remaining_bytes"] == (
        payload["total_scan_budget_bytes"] - payload["bytes_scanned"]
    )


def test_stop_evidence_budget_exhaustion_blocks_following_sources_and_is_fail_closed(
    registry_module,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "2040")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "2040")
    trade = _base_stop_evidence_trade()
    # This compact line is 30 bytes with newline, so head budget (1020) is fully consumed.
    large_noise = ['{"lifecycle_id":"LC-BTC-001"}' for _ in range(400)]
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": large_noise,
            # 26 chars + CRLF newline -> 28 bytes, matching remaining budget in this setup.
            "execution_log.jsonl": ["x" * 26],
            "execution_engine_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ],
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["scan_truncated"] is True
    assert payload["total_scan_budget_exhausted"] is True
    assert payload["status"] == "STOP_EVIDENCE_SOURCE_READ_ERROR"
    assert payload["safe_to_use_for_r_recalculation"] is False
    execution_stat = next(
        stat for stat in payload["source_scan_stats"]
        if stat["source_file"] == "execution_engine_log.jsonl"
    )
    assert execution_stat["reason"] == "TOTAL_SCAN_BUDGET_EXHAUSTED"


def test_stop_evidence_source_priority_is_deterministic_and_documented(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    expected_priority = [
        "decision_log.jsonl",
        "execution_log.jsonl",
        "execution_engine_log.jsonl",
        "broker_executions_log.jsonl",
        "broker_execution_audit_log.jsonl",
        "history_events.jsonl",
        "timeline.jsonl",
        "history_export.json",
    ]
    assert payload["source_scan_priority"] == expected_priority
    assert [stat["source_file"] for stat in payload["source_scan_stats"]] == expected_priority


def test_stop_evidence_cache_hit_avoids_reopening_source_files(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    real_open = open
    counters = {"reads": 0}

    def counting_open(*args, **kwargs):
        target = str(args[0]) if args else ""
        mode = str(args[1]) if len(args) > 1 else str(kwargs.get("mode", "r"))
        if (target.endswith(".jsonl") or target.endswith(".json")) and "r" in mode:
            counters["reads"] += 1
        return real_open(*args, **kwargs)

    namespace["open"] = counting_open

    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    reads_after_first = counters["reads"]
    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert counters["reads"] == reads_after_first


def test_stop_evidence_cache_invalidates_when_source_signature_changes(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    decision_path = tmp_path / "decision_log.jsonl"
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    decision_path.write_text(
        decision_path.read_text(encoding="utf-8") + json.dumps(
            {
                "event_type": "HEARTBEAT",
                "timestamp": "2026-11-07T10:55:00-03:00",
                "lifecycle_id": trade["lifecycle_id"],
                "payload": "mutated",
            }
        ) + "\n",
        encoding="utf-8",
    )

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False


def test_stop_evidence_cache_stores_only_sanitized_payload(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["cache_hit"] is False

    cache_state = namespace.get("_TRPSF_V1_STOP_EVIDENCE_CACHE_STATE") or {}
    entries = cache_state.get("entries") or {}
    assert entries
    cached_payload = next(iter(entries.values())).get("payload") or {}
    assert "selection_internal" not in cached_payload
    assert "selected_trade" not in (cached_payload.get("trade_selection") or {})


def test_stop_evidence_cache_invalidates_when_registry_entry_changes(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    registry_trade = _registry_first_closed_trade(namespace)
    registry_trade["entry"] = 101.0

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False
    assert second["trade"]["entry"] == pytest.approx(101.0)


def test_stop_evidence_cache_invalidates_when_registry_exit_price_changes(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    registry_trade = _registry_first_closed_trade(namespace)
    registry_trade["exit_price"] = 109.25

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False
    assert second["trade"]["exit_price"] == pytest.approx(109.25)


def test_stop_evidence_cache_invalidates_when_registry_pnl_fields_change(registry_module, tmp_path):
    trade = _base_stop_evidence_trade(
        pnl_r=-0.81,
        result_r=-0.77,
        metadata={"outcome": {"r_multiple": -0.73}},
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    registry_trade = _registry_first_closed_trade(namespace)
    registry_trade["pnl_r"] = -0.33
    metadata_obj = registry_trade.setdefault("metadata", {})
    outcome_obj = metadata_obj.setdefault("outcome", {})
    outcome_obj["r_multiple"] = -0.44

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False
    values = {item.get("alias"): item.get("value") for item in second.get("reported_r_candidates") or []}
    assert values.get("pnl_r") == pytest.approx(-0.33)
    assert values.get("r_multiple") == pytest.approx(-0.44)


def test_stop_evidence_cache_invalidates_when_registry_strong_identity_changes(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    registry_trade = _registry_first_closed_trade(namespace)
    registry_trade["client_order_id"] = "CLIENT-CHANGED-FOR-CACHE"

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False
    assert second["trade"]["client_order_id"] == "CLIENT-CHANGED-FOR-CACHE"


def test_stop_evidence_logs_unchanged_but_registry_changed_forces_cache_miss(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    registry_trade = _registry_first_closed_trade(namespace)
    registry_trade["registry_mode"] = "VERIFY"

    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False


def test_stop_evidence_cache_signature_changes_with_scan_budget(registry_module, tmp_path, monkeypatch):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "4096")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "12288")
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )

    first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert first["cache_hit"] is False

    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "2048")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "6144")
    second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert second["cache_hit"] is False
    assert second["total_scan_budget_bytes"] == 6144


def test_stop_evidence_cache_is_identity_scoped(registry_module, tmp_path):
    trade_a = _base_stop_evidence_trade(
        lifecycle_id="LC-BTC-001",
        client_order_id="CLIENT-A",
        order_id="ORDER-A",
    )
    trade_b = _base_stop_evidence_trade(
        lifecycle_id="LC-BTC-002",
        client_order_id="CLIENT-B",
        order_id="ORDER-B",
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        closed_trades=[trade_a, trade_b],
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade_a["lifecycle_id"],
                    "initial_stop": 106.0,
                },
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:30-03:00",
                    "lifecycle_id": trade_b["lifecycle_id"],
                    "initial_stop": 107.0,
                },
            ]
        },
    )

    a_first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade_a["lifecycle_id"]}
    )
    b_first = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade_b["lifecycle_id"]}
    )
    a_second = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade_a["lifecycle_id"]}
    )
    assert a_first["cache_hit"] is False
    assert b_first["cache_hit"] is False
    assert a_second["cache_hit"] is True


def test_stop_evidence_tail_scan_records_byte_offsets(registry_module, tmp_path, monkeypatch):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "4096")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "12288")
    trade = _base_stop_evidence_trade()
    rows = [
        {
            "event_type": "HEARTBEAT",
            "timestamp": "2026-11-07T10:54:10-03:00",
            "lifecycle_id": f"OTHER-{index}",
            "payload": "x" * 500,
        }
        for index in range(180)
    ]
    rows.append(
        {
            "event_type": "ENTRY_PLAN_SET",
            "timestamp": "2026-11-07T10:54:20-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "initial_stop": 106.0,
        }
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={"history_events.jsonl": rows},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    assert payload["scan_truncated"] is True
    tail_evidence = [
        item for item in payload["evidence"]
        if item.get("source_file") == "history_events.jsonl"
        and str(item.get("source_index") or "").startswith("byte:")
        and item.get("line_number") is None
    ]
    assert tail_evidence
    assert all(isinstance(item.get("byte_offset_start"), int) for item in tail_evidence)
    assert all(isinstance(item.get("byte_offset_end"), int) for item in tail_evidence)
    assert all(item.get("byte_offset_end") > item.get("byte_offset_start") for item in tail_evidence)


def test_stop_evidence_tail_strong_candidate_keeps_byte_offset_provenance(
    registry_module,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("STOP_EVIDENCE_MAX_SOURCE_SCAN_BYTES", "4096")
    monkeypatch.setenv("STOP_EVIDENCE_MAX_TOTAL_SCAN_BYTES", "12288")
    trade = _base_stop_evidence_trade()
    rows = [
        {
            "event_type": "HEARTBEAT",
            "timestamp": "2026-11-07T10:54:10-03:00",
            "lifecycle_id": f"OTHER-{index}",
            "payload": "x" * 500,
        }
        for index in range(180)
    ]
    rows.append(
        {
            "event_type": "ENTRY_PLAN_SET",
            "timestamp": "2026-11-07T10:54:20-03:00",
            "lifecycle_id": trade["lifecycle_id"],
            "initial_stop": 106.0,
        }
    )
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={"history_events.jsonl": rows},
    )

    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    strong_candidates = [
        item for item in payload["evidence"]
        if item.get("classification") == "INITIAL_STOP_CANDIDATE"
        and item.get("correlation_strength") == "STRONG"
        and item.get("source_file") == "history_events.jsonl"
    ]
    assert strong_candidates
    assert all(str(item.get("source_index") or "").startswith("byte:") for item in strong_candidates)
    assert all(isinstance(item.get("byte_offset_start"), int) for item in strong_candidates)
    assert all(isinstance(item.get("byte_offset_end"), int) for item in strong_candidates)
    assert payload["status"] == "STOP_EVIDENCE_SOURCE_READ_ERROR"


def test_stop_evidence_source_scan_stats_public_shape_is_limited(registry_module, tmp_path):
    trade = _base_stop_evidence_trade()
    namespace = _compile_stop_evidence_namespace(
        registry_module,
        tmp_path,
        trade=trade,
        source_rows_by_file={
            "decision_log.jsonl": [
                {
                    "event_type": "ENTRY_PLAN_SET",
                    "timestamp": "2026-11-07T10:54:20-03:00",
                    "lifecycle_id": trade["lifecycle_id"],
                    "initial_stop": 106.0,
                }
            ]
        },
    )
    payload = namespace["_trpsf_v1_closed_trade_stop_evidence_v1"](
        identity={"lifecycle_id": trade["lifecycle_id"]}
    )
    allowed_keys = {
        "source_file",
        "scan_strategy",
        "source_scan_budget_bytes",
        "bytes_scanned",
        "total_file_bytes",
        "scan_truncated",
        "byte_ranges_examined",
        "reason",
    }
    assert payload["source_scan_stats"]
    for stat in payload["source_scan_stats"]:
        assert set(stat.keys()) == allowed_keys
