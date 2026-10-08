"""Execute only selected main.py functions with fakes; never import the app."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


MAIN = Path(__file__).resolve().parents[1] / "main.py"
TREE = ast.parse(MAIN.read_text(encoding="utf-8-sig"))
RUNNERS = [
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name == "real_close_auto_evaluator_v1_run"
]
assert len(RUNNERS) == 2
RECONCILIATION = next(
    node for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name == "real_close_reconciliation_v1_run"
)


def _load_runner(node, namespace):
    exec(
        compile(ast.Module(body=[node], type_ignores=[]), str(MAIN), "exec"),
        namespace,
    )
    return namespace[node.name]


@pytest.mark.parametrize(
    "commit_status,expected_status,expected_releases",
    [
        ("OUTCOME_SAVED_WITH_AUDIT_ERROR", "OUTCOME_AUTO_EVALUATED_AUDIT_PENDING", 0),
        ("OUTCOME_SAVED", "OUTCOME_AUTO_EVALUATED_AND_SAVED", 1),
    ],
)
def test_original_auto_evaluator_keeps_cooldown_when_audit_pending(
    commit_status, expected_status, expected_releases
):
    releases = []
    builds = []
    candidate = {
        "trade": {"symbol": "XRPUSDT", "side": "LONG", "bot": "FALCON"},
        "trade_id": "test-trade",
        "closed_identity_key": "test-identity",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
    }

    def build(**kwargs):
        builds.append(kwargs)
        return {"ok": True, "commit": {"committed": bool(kwargs["commit"]), "status": commit_status}}

    namespace = {
        "REAL_CLOSE_AUTO_EVALUATOR_V1_VERSION": "TEST",
        "REAL_CLOSE_AUTO_EVALUATOR_V1_STATE_FILE": "unused",
        "_rcae_v1_config": lambda: {
            "enabled": True,
            "auto_commit": True,
            "release_cooldown_on_outcome": True,
        },
        "_rcae_v1_now": lambda: "test-time",
        "_rcae_v1_payload_snapshot": lambda value: value,
        "_rcae_v1_find_candidates": lambda **_kwargs: {"ok": True, "candidates": [candidate]},
        "_rcae_v1_outcome_has_sufficient_quality": lambda _outcome: True,
        "_rcae_v1_candidate_public": lambda value: value,
        "_rcae_v1_sanitize_public": lambda value: value,
        "_rcae_v1_write_json": lambda *_args: None,
        "_rcae_v1_append_event": lambda *_args: None,
        "trade_close_outcome_v1_build": build,
        "pilot_cooldown_v1_release": lambda **kwargs: releases.append(kwargs) or {"ok": True},
    }
    runner = _load_runner(RUNNERS[0], namespace)
    result = runner(payload={"trade_id": "test-trade"}, commit=True)

    assert [item["commit"] for item in builds] == [False, True]
    assert result["committed"] is True
    assert result["audit_pending"] is (expected_releases == 0)
    assert result["status"] == expected_status
    assert result["outcome"]["commit"]["status"] == commit_status
    assert len(releases) == expected_releases
    assert (result["cooldown_release"] is not None) is bool(expected_releases)


@pytest.mark.parametrize(
    "audit_pending,expected_status",
    [
        (True, "BROKER_OUTCOME_AUTO_RECONCILED_AUDIT_PENDING"),
        (False, "BROKER_OUTCOME_AUTO_RECONCILED_AND_SAVED"),
    ],
)
def test_broker_auto_wrapper_preserves_audit_warning(audit_pending, expected_status):
    reconciliation = {
        "committed": True,
        "audit_pending": audit_pending,
        "outcome": {
            "commit": {
                "committed": True,
                "status": "OUTCOME_SAVED_WITH_AUDIT_ERROR" if audit_pending else "OUTCOME_SAVED",
            }
        },
    }
    candidate = {
        "trade": {"trade_id": "test-trade"},
        "trade_id": "test-trade",
        "bot": "FALCON",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "setup": "FALCON15",
    }
    namespace = {
        "_ORIGINAL_REAL_CLOSE_AUTO_EVALUATOR_RUN_FOR_RCR_V1": lambda **_kwargs: pytest.fail("fallback ran"),
        "_rcae_v1_config": lambda: {"auto_commit": True},
        "_rcae_v1_find_candidates": lambda **_kwargs: {"candidates": [candidate]},
        "_closed_trade_identity_state_v1": lambda _trade: {
            "strong_identity": {
                "lifecycle_id": "life",
                "client_order_id": "client",
                "order_id": "order",
            }
        },
        "real_close_reconciliation_v1_run": lambda **_kwargs: reconciliation,
        "REAL_CLOSE_AUTO_EVALUATOR_V1_VERSION": "TEST",
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST",
        "_rcrm_v1_now": lambda: "test-time",
    }
    runner = _load_runner(RUNNERS[1], namespace)
    result = runner(payload={"trade_id": "test-trade"}, commit=True)

    assert result["status"] == expected_status
    assert result["committed"] is True
    assert result["audit_pending"] is audit_pending
    assert result["broker_reconciliation"] is reconciliation


@pytest.mark.parametrize(
    "commit_status,expected_status,expected_pending",
    [
        ("OUTCOME_SAVED_WITH_AUDIT_ERROR", "BROKER_CLOSE_RECONCILED_AUDIT_PENDING", True),
        ("OUTCOME_SAVED", "BROKER_CLOSE_RECONCILED_AND_SAVED", False),
    ],
)
def test_reconciliation_reports_audit_warning_after_registry_save(
    commit_status, expected_status, expected_pending
):
    registry_updates = []
    outcomes = []
    broker_calls = []
    trade = {
        "trade_id": "test-trade", "bot": "FALCON", "setup": "FALCON15",
        "symbol": "XRPUSDT", "side": "LONG", "registry_mode": "REAL",
    }
    identity = {"lifecycle_id": "life", "client_order_id": "client", "order_id": "order", "issues": []}
    values = {
        "order_id": "order", "client_order_id": "client", "entry": 1.0,
        "stop": 0.9, "qty": 9, "opened_epoch": 1,
    }
    broker_result = {
        "ok": True, "complete": True, "status": "BROKER_CLOSE_RECONCILED",
        "entry_price": 1.0, "exit_price": 1.1, "expected_qty": 9,
        "net_pnl": 0.8, "realized_pnl_gross": 1.0, "funding": -0.1,
        "fee_total": 0.1, "financial_dedup_ok": True,
    }

    def reconcile(**kwargs):
        broker_calls.append(kwargs)
        return broker_result

    def outcome(**kwargs):
        outcomes.append(kwargs)
        return {"commit": {"committed": True, "status": commit_status}}

    namespace = {
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST",
        "REAL_CLOSE_RECONCILIATION_V1_LATEST_FILE": "unused",
        "REAL_CLOSE_RECONCILIATION_V1_EVENTS_FILE": "unused",
        "_rcrm_v1_now": lambda: "test-time",
        "_rcrm_v1_find_closed_trade": lambda _payload: {
            "ok": True, "trade_id": "test-trade", "trade": trade,
            "diagnostics": {"strong_identity_supplied": True, "supplied_identity": {}},
        },
        "_rcrm_v11_selected_strong_identity": lambda _trade: identity,
        "_rcrm_v1_values": lambda *_args, **_kwargs: values,
        "_rcrm_v1_norm_symbol": lambda value: value,
        "_rcrm_v1_norm_side": lambda value: value,
        "_rcrm_v1_float": lambda value, default=None: float(value) if value is not None else default,
        "_rcrm_v1_metrics": lambda *_args: {"r_net": 1.0, "r_price": 1.1, "pnl_pct": 10.0},
        "_rcrm_v1_causal_close_reason": lambda _trade: {"ok": True, "value": "STOP"},
        "_rcrm_v11_manual_outcome_conflict": lambda *_args: {"conflict": False},
        "_rcrm_v11_validate_broker_identity": lambda *_args: {"ok": True},
        "_rcrm_v1_public": lambda result: result,
        "_rcrm_v1_write": lambda *_args: None,
        "_rcrm_v1_append": lambda *_args: None,
        "central_broker": SimpleNamespace(reconcile_closed_trade=reconcile),
        "central_trade_registry": SimpleNamespace(
            normalize_strong_identity_value=lambda _field, value: value,
            update_closed_trade=lambda **kwargs: registry_updates.append(kwargs) or {"ok": True},
        ),
        "trade_close_outcome_v1_build": outcome,
    }
    runner = _load_runner(RECONCILIATION, namespace)
    result = runner(payload={"trade_id": "test-trade"}, commit=True, source="test")

    assert len(broker_calls) == len(registry_updates) == len(outcomes) == 1
    assert result["committed"] is True
    assert result["audit_pending"] is expected_pending
    assert result["status"] == expected_status
    assert result["outcome"]["commit"]["status"] == commit_status
