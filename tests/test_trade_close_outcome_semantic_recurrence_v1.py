from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))


def _function_nodes(wanted, *, strip_decorators=False):
    nodes = []
    for node in MAIN_TREE.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in wanted:
            continue
        cloned = copy.deepcopy(node)
        if strip_decorators:
            cloned.decorator_list = []
        nodes.append(cloned)
    assert {node.name for node in nodes} == set(wanted)
    return nodes


def _build_namespace(trade, commit_result=None):
    wanted = {
        "_tco_v1_float",
        "_tco_v1_norm_symbol",
        "_tco_v1_norm_side",
        "_tco_v1_norm_bot",
        "_tco_v1_trade_meta",
        "_tco_v1_resolve_exit_price",
        "_tco_v1_resolve_realized_pnl",
        "_tco_v1_compute_pnl",
        "_tco_v1_compute_r",
        "_tco_v1_tp50_result",
        "_tco_v1_infer_close_reason",
        "trade_close_outcome_v1_build",
    }
    selected = {"key": "closed_index|0|SYNTHETIC", "trade": copy.deepcopy(trade)}
    commit_calls = []
    namespace = {
        "TRADE_CLOSE_OUTCOME_V1_VERSION": "TEST-SEMANTIC-V1",
        "_tco_v1_now": lambda: "05/09/2026 19:00:00",
        "_tco_v1_find_closed_trade": lambda **_kwargs: {
            "ok": True,
            "status": "MATCH_FOUND",
            "count": 1,
            "selected": copy.deepcopy(selected),
            "trade_registry_file": "synthetic-memory-only",
        },
        "_closed_trade_identity_state_v1": lambda _trade: {
            "strong_identity": {
                "client_order_id": "SYNTHETIC-CLIENT",
                "order_id": "SYNTHETIC-ORDER",
            },
            "specific_identity_states": [],
            "legacy_fallback": {},
            "registry_mode": "REAL",
            "execution_mode": "LIVE",
            "has_alias_conflict": False,
            "alias_conflicts": [],
        },
        "trade_close_outcome_v1_commit": lambda *args: commit_calls.append(args)
        or copy.deepcopy(
            commit_result
            or {"attempted": True, "committed": True, "status": "OUTCOME_SAVED"}
        ),
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=_function_nodes(wanted), type_ignores=[])),
            str(MAIN_FILE),
            "exec",
        ),
        namespace,
    )
    namespace["_test_commit_calls"] = commit_calls
    return namespace


def _synthetic_broker_reconciled_trade():
    return {
        "trade_id": "SYNTHETIC:CLOSED:BTCUSDT:SHORT",
        "status": "CLOSED",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "entry": 64107.9,
        "exit_price": 64469.9,
        "qty": 0.0001,
        "sl": 64440.46571428572,
        "pnl_r": -1.26907189,
        "r_multiple": -1.26907189,
        "close_reason": "STOP",
        "metadata": {"exit_reason": "STOP"},
    }


def test_outcome_keeps_net_r_canonical_and_exposes_gross_r_separately():
    namespace = _build_namespace(_synthetic_broker_reconciled_trade())

    outcome = namespace["trade_close_outcome_v1_build"](
        symbol="BTCUSDT",
        side="SHORT",
        bot="FALCON",
        setup="FALCON15",
        trade_id="SYNTHETIC:CLOSED:BTCUSDT:SHORT",
        exit_price=64469.9,
        realized_pnl=-0.03577698,
        fee=0.006428,
        close_reason="STOP",
        canonical_pnl_r=-1.26907189,
        commit=False,
    )

    assert outcome["ok"] is True
    assert outcome["close_reason"] == "STOP"
    assert outcome["pnl_r"] == pytest.approx(-1.26907189)
    assert outcome["r_multiple"] == pytest.approx(-1.26907189)
    assert outcome["net_r_multiple"] == pytest.approx(-1.26907189)
    assert outcome["gross_r_multiple"] == pytest.approx(-1.08850668)
    assert outcome["r_calculation"]["canonical_r_source"] == (
        "explicit_canonical_pnl_r"
    )
    assert outcome["learning_payload"]["pnl_r"] == pytest.approx(-1.26907189)
    assert outcome["learning_payload"]["gross_r_multiple"] == pytest.approx(
        -1.08850668
    )
    assert namespace["_test_commit_calls"] == []


def test_outcome_blocks_conflicting_explicit_net_r_without_commit():
    namespace = _build_namespace(_synthetic_broker_reconciled_trade())

    outcome = namespace["trade_close_outcome_v1_build"](
        symbol="BTCUSDT",
        side="SHORT",
        bot="FALCON",
        setup="FALCON15",
        trade_id="SYNTHETIC:CLOSED:BTCUSDT:SHORT",
        exit_price=64469.9,
        realized_pnl=-0.03577698,
        fee=0.006428,
        close_reason="STOP",
        canonical_pnl_r=-9.0,
        commit=True,
    )

    assert outcome["ok"] is False
    assert outcome["status"] == "CANONICAL_PNL_R_EVIDENCE_CONFLICT"
    assert outcome["commit"] == {
        "attempted": False,
        "committed": False,
        "status": "COMMIT_BLOCKED_CANONICAL_PNL_R_EVIDENCE_CONFLICT",
    }
    assert namespace["_test_commit_calls"] == []


def test_reevaluation_preserves_registry_stop_and_canonical_pnl_r():
    namespace = _build_namespace(_synthetic_broker_reconciled_trade())

    outcome = namespace["trade_close_outcome_v1_build"](
        symbol="BTCUSDT",
        side="SHORT",
        bot="FALCON",
        setup="FALCON15",
        trade_id="SYNTHETIC:CLOSED:BTCUSDT:SHORT",
        exit_price=64469.9,
        realized_pnl=-0.03577698,
        fee=0.006428,
        commit=False,
    )

    assert outcome["ok"] is True
    assert outcome["close_reason"] == "STOP"
    assert outcome["close_reason_source"] == "registry"
    assert outcome["pnl_r"] == pytest.approx(-1.26907189)
    assert outcome["r_multiple"] == pytest.approx(-1.26907189)
    assert outcome["gross_r_multiple"] == pytest.approx(-1.08850668)
    assert outcome["r_calculation"]["canonical_r_source"] == (
        "registry_canonical_pnl_r"
    )
    assert namespace["_test_commit_calls"] == []


def test_commit_without_net_r_evidence_never_promotes_gross_r():
    trade = _synthetic_broker_reconciled_trade()
    trade.pop("qty")
    trade.pop("pnl_r")
    trade.pop("r_multiple")
    namespace = _build_namespace(trade)

    outcome = namespace["trade_close_outcome_v1_build"](
        symbol="BTCUSDT",
        side="SHORT",
        bot="FALCON",
        setup="FALCON15",
        trade_id="SYNTHETIC:CLOSED:BTCUSDT:SHORT",
        exit_price=64469.9,
        close_reason="STOP",
        commit=True,
    )

    assert outcome["ok"] is False
    assert outcome["status"] == "NET_PNL_R_EVIDENCE_UNAVAILABLE"
    assert outcome["gross_r_multiple"] == pytest.approx(-1.08850668)
    assert outcome["commit"] == {
        "attempted": False,
        "committed": False,
        "status": "COMMIT_BLOCKED_NET_PNL_R_EVIDENCE_UNAVAILABLE",
    }
    assert namespace["_test_commit_calls"] == []


def test_commit_aligns_all_statistical_r_aliases_and_preserves_gross_r():
    wanted = {"trade_close_outcome_v1_commit"}
    original = _synthetic_broker_reconciled_trade()
    registry = {"closed_trades": [copy.deepcopy(original)]}
    saved = []
    namespace = {
        "TRADE_CLOSE_OUTCOME_V1_VERSION": "TEST-SEMANTIC-V1",
        "TRADE_CLOSE_OUTCOME_V1_LATEST_FILE": "unused-latest",
        "TRADE_CLOSE_OUTCOME_V1_EVENTS_FILE": "unused-events",
        "_closed_trade_identity_state_v1": lambda _trade: {
            "canonical_key": "SYNTHETIC",
            "has_alias_conflict": False,
        },
        "_closed_trade_records_equivalent_v1": lambda left, right: (
            left.get("trade_id") == right.get("trade_id")
        ),
        "_tco_v1_load_registry": lambda: registry,
        "_tco_v1_closed_items": lambda payload: (
            payload["closed_trades"],
            [("closed_index|0|SYNTHETIC", payload["closed_trades"][0])],
        ),
        "_tco_v1_now": lambda: "05/09/2026 19:00:00",
        "_tco_v1_atomic_write_json": lambda *_args: None,
        "_tco_v1_append_event": lambda *_args: True,
        "central_trade_registry": SimpleNamespace(
            save_registry=lambda payload: saved.append(copy.deepcopy(payload)) or True
        ),
    }
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(
                    body=_function_nodes(wanted, strip_decorators=True),
                    type_ignores=[],
                )
            ),
            str(MAIN_FILE),
            "exec",
        ),
        namespace,
    )
    outcome = {
        "ok": True,
        "status": "OUTCOME_EVALUATED",
        "data_quality": "HIGH_REAL",
        "exit_price": 64469.9,
        "realized_pnl": -0.03577698,
        "net_pnl": -0.04220498,
        "pnl_pct": -0.564673,
        "pnl_r": -1.26907189,
        "r_multiple": -1.26907189,
        "gross_r_multiple": -1.08850668,
        "close_reason": "STOP",
        "tp50_result": {"hit": False},
    }

    result = namespace["trade_close_outcome_v1_commit"](
        {},
        {
            "key": "closed_index|0|SYNTHETIC",
            "trade": copy.deepcopy(original),
        },
        outcome,
    )

    assert result["committed"] is True
    assert len(saved) == 1
    stored = saved[0]["closed_trades"][0]
    assert stored["close_reason"] == "STOP"
    assert stored["pnl_r"] == pytest.approx(-1.26907189)
    assert stored["result_r"] == pytest.approx(-1.26907189)
    assert stored["r_multiple"] == pytest.approx(-1.26907189)
    assert stored["metadata"]["outcome"]["gross_r_multiple"] == pytest.approx(
        -1.08850668
    )
