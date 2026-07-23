from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import trade_registry


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
OPEN_ORDER_ID = "2078483751332171776"
LIFECYCLE_ID = (
    "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114"
)
CLIENT_ORDER_ID = "FALCON-LIVE-FALCON15-1784384114"
ACK = "REAL_CLOSE_STRONG_IDENTITY_BACKFILL_V1"


def _records():
    shared = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
        "qty": 9.0,
    }
    verify = {
        **shared,
        "registry_mode": "VERIFY",
        "execution_mode": "VERIFY",
        "entry": 1.1123,
        "lifecycle_id": "VERIFY-LIFECYCLE",
        "client_order_id": "VERIFY-CLIENT",
        "order_id": "VERIFY-ORDER",
        "broker_order_id": "VERIFY-ORDER",
        "outcome_status": "CLOSED",
    }
    historical_real = {
        **shared,
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "entry": 1.0871,
        "sl": 1.084175,
        "exit_price": 1.0902,
        "pnl_pct": 0.2851623585686696,
        "closed_at": "18/07/2026 18:37",
        "outcome": {
            "outcome_status": "OUTCOME_RECORDED",
            "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
            "outcome_id": "XRP-MANUAL-OUTCOME",
            "data_quality": "MANUAL_CONFIRMED",
            "exit_price": 1.0902,
        },
    }
    return verify, historical_real


def _payload(**updates):
    payload = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "open_order_id": OPEN_ORDER_ID,
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "entry": 1.0871,
        "qty": 9,
    }
    payload.update(updates)
    return payload


def _registry_state():
    verify, historical_real = _records()
    return {
        "ok": True,
        "open_trades": {},
        "closed_trades": [verify, historical_real],
    }


def _install_registry_fakes(monkeypatch, state):
    saves = []
    monkeypatch.setattr(
        trade_registry,
        "load_registry_read_only",
        lambda: copy.deepcopy(state),
    )
    monkeypatch.setattr(
        trade_registry,
        "load_registry",
        lambda: copy.deepcopy(state),
    )

    def save(payload):
        state.clear()
        state.update(copy.deepcopy(payload))
        saves.append(copy.deepcopy(payload))

    monkeypatch.setattr(trade_registry, "save_registry", save)
    return saves


def _financial_snapshot(trade):
    return {
        key: copy.deepcopy(trade.get(key))
        for key in (
            "trade_id",
            "entry",
            "qty",
            "exit_price",
            "pnl_pct",
            "status",
            "closed_at",
            "outcome",
        )
    }


def test_preview_selects_only_real_live_candidate_and_never_writes(monkeypatch):
    state = _registry_state()
    saves = _install_registry_fakes(monkeypatch, state)

    result = trade_registry.preview_historical_strong_identity_backfill(
        _payload()
    )

    assert result["status"] == "HISTORICAL_STRONG_IDENTITY_BACKFILL_READY"
    assert result["candidate_count"] == 1
    assert result["registry_index"] == 1
    assert result["candidate"]["registry_mode"] == "REAL"
    assert result["candidate"]["execution_mode"] == "LIVE"
    assert result["candidate"]["entry"] == pytest.approx(1.0871)
    assert result["candidate"]["qty"] == pytest.approx(9)
    assert result["current_identity"] == {
        "lifecycle_id": None,
        "client_order_id": None,
        "order_id": None,
    }
    assert result["proposed_identity"] == {
        "lifecycle_id": LIFECYCLE_ID,
        "client_order_id": CLIENT_ORDER_ID,
        "order_id": OPEN_ORDER_ID,
    }
    assert result["outcome"]["outcome_source"] == (
        "MANUAL_CLOSE_RECONCILIATION"
    )
    assert result["no_order_sent_by_this_route"] is True
    assert result["broker_called"] is False
    assert result["committed"] is False
    assert saves == []


@pytest.mark.parametrize(
    ("update", "expected_reason"),
    [
        ({"entry": 1.1123}, "ENTRY_DIVERGENCE"),
        ({"qty": 18}, "QTY_DIVERGENCE"),
        ({"registry_mode": "VERIFY"}, "REGISTRY_MODE_REAL_REQUIRED"),
        ({"execution_mode": "PAPER"}, "EXECUTION_MODE_LIVE_REQUIRED"),
    ],
)
def test_preview_blocks_divergent_or_non_live_request(
    monkeypatch,
    update,
    expected_reason,
):
    state = _registry_state()
    saves = _install_registry_fakes(monkeypatch, state)

    result = trade_registry.preview_historical_strong_identity_backfill(
        _payload(**update)
    )

    assert result["committed"] is False
    if expected_reason.endswith("_REQUIRED"):
        assert result["status"] == (
            "HISTORICAL_STRONG_IDENTITY_BACKFILL_INVALID_REQUEST"
        )
        assert expected_reason in result["diagnostics"]["request_issues"]
    else:
        assert result["status"] == (
            "HISTORICAL_STRONG_IDENTITY_BACKFILL_NOT_FOUND"
        )
        assert any(
            expected_reason in item["reasons"]
            for item in result["diagnostics"]["rejected_candidates"]
        )
    assert saves == []


def test_preview_blocks_no_candidate_and_multiple_candidates(monkeypatch):
    state = _registry_state()
    saves = _install_registry_fakes(monkeypatch, state)

    missing = trade_registry.preview_historical_strong_identity_backfill(
        _payload(symbol="ETHUSDT")
    )
    state["closed_trades"].append(copy.deepcopy(state["closed_trades"][1]))
    ambiguous = trade_registry.preview_historical_strong_identity_backfill(
        _payload()
    )

    assert missing["status"] == (
        "HISTORICAL_STRONG_IDENTITY_BACKFILL_NOT_FOUND"
    )
    assert ambiguous["status"] == (
        "HISTORICAL_STRONG_IDENTITY_BACKFILL_AMBIGUOUS"
    )
    assert ambiguous["candidate_count"] == 2
    assert saves == []


def test_existing_or_foreign_strong_identity_conflict_blocks(monkeypatch):
    state = _registry_state()
    state["closed_trades"][1]["client_order_id"] = "OTHER-CLIENT"
    saves = _install_registry_fakes(monkeypatch, state)

    existing_conflict = (
        trade_registry.preview_historical_strong_identity_backfill(_payload())
    )

    state = _registry_state()
    state["closed_trades"][0].update(
        {
            "lifecycle_id": LIFECYCLE_ID,
            "client_order_id": CLIENT_ORDER_ID,
            "order_id": OPEN_ORDER_ID,
        }
    )
    saves = _install_registry_fakes(monkeypatch, state)
    foreign_ownership = (
        trade_registry.preview_historical_strong_identity_backfill(_payload())
    )

    assert existing_conflict["status"] == "STRONG_IDENTITY_ALIAS_CONFLICT"
    assert foreign_ownership["status"] == "STRONG_IDENTITY_ALIAS_CONFLICT"
    assert foreign_ownership["diagnostics"][
        "identity_ownership_conflicts"
    ]
    assert saves == []


def test_atomic_commit_updates_only_real_and_preserves_financial_fields(
    monkeypatch,
):
    state = _registry_state()
    verify_before = copy.deepcopy(state["closed_trades"][0])
    financial_before = _financial_snapshot(state["closed_trades"][1])
    saves = _install_registry_fakes(monkeypatch, state)

    result = trade_registry.backfill_historical_strong_identity(
        _payload(),
        ack=ACK,
    )

    assert result["status"] == "HISTORICAL_STRONG_IDENTITY_BACKFILLED"
    assert result["committed"] is True
    assert len(saves) == 1
    assert state["closed_trades"][0] == verify_before
    updated = state["closed_trades"][1]
    assert _financial_snapshot(updated) == financial_before
    assert updated["lifecycle_id"] == LIFECYCLE_ID
    assert updated["client_order_id"] == CLIENT_ORDER_ID
    assert updated["broker_order_id"] == OPEN_ORDER_ID
    assert updated["order_id"] == OPEN_ORDER_ID
    assert updated["open_order_id"] == OPEN_ORDER_ID
    assert updated["registry_mode"] == "REAL"
    assert updated["execution_mode"] == "LIVE"
    assert updated["metadata"][
        "historical_strong_identity_backfill_v1"
    ]["source"] == "REAL_CLOSE_RECONCILIATION_ADMINISTRATIVE_BACKFILL"


def test_ack_idempotency_and_changed_retry_are_fail_closed(monkeypatch):
    state = _registry_state()
    saves = _install_registry_fakes(monkeypatch, state)

    wrong_ack = trade_registry.backfill_historical_strong_identity(
        _payload(),
        ack="WRONG",
    )
    first = trade_registry.backfill_historical_strong_identity(
        _payload(),
        ack=ACK,
    )
    retry = trade_registry.backfill_historical_strong_identity(
        _payload(),
        ack=ACK,
    )
    changed = trade_registry.backfill_historical_strong_identity(
        _payload(open_order_id="OTHER-ORDER"),
        ack=ACK,
    )

    assert wrong_ack["status"] == "ACK_REQUIRED"
    assert first["status"] == "HISTORICAL_STRONG_IDENTITY_BACKFILLED"
    assert retry["status"] == "ALREADY_BACKFILLED"
    assert retry["committed"] is False
    assert changed["status"] == "STRONG_IDENTITY_ALIAS_CONFLICT"
    assert changed["committed"] is False
    assert len(saves) == 1


def _main_nodes(names):
    nodes = [
        copy.deepcopy(node)
        for node in MAIN_TREE.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    for node in nodes:
        node.decorator_list = []
    ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    return nodes


def test_route_preview_and_authenticated_commit_security_contract():
    nodes = _main_nodes(
        {
            "_rtlm_v15_is_auth_material_key",
            "_rtlm_v15_contains_auth_material",
            "_rtlm_v15_admin_auth",
            "real_close_identity_backfill_v1_route",
        }
    )
    calls = []
    resolver_calls = []

    class Registry:
        def preview_historical_strong_identity_backfill(self, payload):
            calls.append(("preview", copy.deepcopy(payload)))
            return {"ok": True, "status": "READY", "committed": False}

        def backfill_historical_strong_identity(self, payload, ack=None):
            calls.append(("commit", copy.deepcopy(payload), ack))
            return {"ok": True, "status": "DONE", "committed": True}

    class Request:
        def __init__(self):
            self.args = {}
            self.form = {}
            self.values = {}
            self.headers = {}

        def get_json(self, silent=True):
            return None

    current_request = Request()

    def resolver(**kwargs):
        resolver_calls.append(copy.deepcopy(kwargs))
        assert kwargs == {"allow_env_fallback": False}
        token = current_request.headers.get("X-Execution-Auth-Token")
        if token == "VALID-ADMIN-TOKEN":
            return {
                "ok": True,
                "status": "EXECUTION_AUTH_OK",
                "matched_source": "request.headers.X-Execution-Auth-Token",
            }
        return {
            "ok": False,
            "status": (
                "MISSING_EXECUTION_AUTH_TOKEN"
                if not token
                else "INVALID_EXECUTION_AUTH_TOKEN"
            ),
        }

    namespace = {
        "request": current_request,
        "_rcrm_v1_bool": lambda value, default=False: (
            str(value or "").lower() == "true"
        ),
        "_ee_auth_resolver_v1_get_from_mapping": lambda mapping, key: (
            mapping.get(key) if hasattr(mapping, "get") else None
        ),
        "_ee_auth_resolver_v1_resolve": resolver,
        "REAL_CLOSE_IDENTITY_BACKFILL_V1_ACK": ACK,
        "central_trade_registry": Registry(),
    }
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(body=nodes, type_ignores=[])
            ),
            str(MAIN_FILE),
            "exec",
        ),
        namespace,
    )

    current_request.args = _payload()
    preview, preview_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()
    assert resolver_calls == []

    current_request.args = {**_payload(), "commit": "true", "ack": ACK}
    current_request.headers = {}
    missing, missing_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()
    current_request.headers = {"X-Execution-Auth-Token": "WRONG-TOKEN"}
    invalid, invalid_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()

    current_request.headers = {"X-Execution-Auth-Token": "VALID-ADMIN-TOKEN"}
    current_request.args = {
        **_payload(),
        "commit": "true",
        "ack": "WRONG",
    }
    wrong_ack, wrong_ack_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()

    current_request.args = {
        **_payload(),
        "commit": "true",
        "ack": ACK,
    }
    current_request.headers = {"X-Execution-Auth-Token": "VALID-ADMIN-TOKEN"}
    committed, commit_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()

    current_request.args = {
        **_payload(),
        "commit": "true",
        "ack": ACK,
        "execution_auth_token": "VALID-ADMIN-TOKEN",
    }
    current_request.headers = {}
    query_token, query_token_status = namespace[
        "real_close_identity_backfill_v1_route"
    ]()

    assert (preview_status, preview["status"]) == (200, "READY")
    assert (missing_status, missing["status"]) == (
        403,
        "EXECUTION_AUTH_REQUIRED",
    )
    assert (invalid_status, invalid["status"]) == (
        403,
        "EXECUTION_AUTH_INVALID",
    )
    assert (wrong_ack_status, wrong_ack["status"]) == (400, "ACK_REQUIRED")
    assert (commit_status, committed["status"]) == (200, "DONE")
    assert (query_token_status, query_token["status"]) == (
        403,
        "EXECUTION_AUTH_HEADER_REQUIRED",
    )
    assert calls[0][0] == "preview"
    assert calls[1][0] == "commit"
    assert len(calls) == 2
    for payload in (
        preview,
        missing,
        invalid,
        wrong_ack,
        committed,
        query_token,
    ):
        assert payload["no_order_sent_by_this_route"] is True
        assert payload["broker_called"] is False
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "VALID-ADMIN-TOKEN" not in serialized
        assert "WRONG-TOKEN" not in serialized


def test_backfilled_real_is_selected_and_manual_outcome_conflict_remains(
    monkeypatch,
):
    state = _registry_state()
    _install_registry_fakes(monkeypatch, state)
    committed = trade_registry.backfill_historical_strong_identity(
        _payload(),
        ack=ACK,
    )
    assert committed["committed"] is True

    wanted = {
        "_rcrm_v1_float",
        "_rcrm_v1_norm_symbol",
        "_rcrm_v1_norm_side",
        "_rcrm_v1_meta",
        "_rcrm_v1_first",
        "_rcrm_v1_find_closed_trade",
        "_rcrm_v11_selected_strong_identity",
        "_rcrm_v1_values",
        "_rcrm_v1_metrics",
        "_rcrm_v11_manual_outcome_conflict",
        "_rcrm_v11_validate_broker_identity",
        "real_close_reconciliation_v1_run",
    }
    nodes = _main_nodes(wanted)
    assert {node.name for node in nodes} == wanted
    broker_calls = []
    registry_updates = []
    outcome_calls = []
    audit_calls = []

    class Registry:
        STRONG_IDENTITY_ALIASES = trade_registry.STRONG_IDENTITY_ALIASES
        strong_identity_alias_state = staticmethod(
            trade_registry.strong_identity_alias_state
        )
        normalize_strong_identity_value = staticmethod(
            trade_registry.normalize_strong_identity_value
        )

        def load_registry_read_only(self):
            return copy.deepcopy(state)

        def update_closed_trade(self, **kwargs):
            registry_updates.append(copy.deepcopy(kwargs))
            return {"ok": True}

    def reconcile(**kwargs):
        broker_calls.append(copy.deepcopy(kwargs))
        return {
            "ok": True,
            "complete": True,
            "status": "BROKER_CLOSE_RECONCILED",
            "open_order_id": OPEN_ORDER_ID,
            "client_order_id": CLIENT_ORDER_ID.lower(),
            "symbol": "XRPUSDT",
            "side": "LONG",
            "entry_price": 1.0871,
            "exit_price": 1.089,
            "expected_qty": 9.0,
            "closed_qty": 9.0,
            "qty_complete": True,
            "realized_pnl_gross": 0.0171,
            "opening_fee": 0.00489195,
            "closing_fee": 0.00490050,
            "fee_total": 0.00979245,
            "funding": -0.00049847,
            "net_pnl": 0.00680908,
            "financial_dedup_ok": True,
            "close_order_ids": ["CLOSE-XRP"],
            "data_quality": "HIGH_BROKER_RECONCILED_DEDUPED",
        }

    namespace = {
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST-BACKFILL-V1",
        "REAL_CLOSE_RECONCILIATION_V1_LATEST_FILE": "unused",
        "REAL_CLOSE_RECONCILIATION_V1_EVENTS_FILE": "unused",
        "BROKER_IMPORT_ERROR": None,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "central_trade_registry": Registry(),
        "central_broker": SimpleNamespace(reconcile_closed_trade=reconcile),
        "_rcrm_v1_execution_evidence": lambda _trade: pytest.fail(
            "execution evidence must not be used"
        ),
        "_rcrm_v1_now": lambda: "23/07/2026 08:00:00",
        "_rcrm_v1_public": lambda value: value,
        "_rcrm_v1_write": lambda *_args: audit_calls.append("write"),
        "_rcrm_v1_append": lambda *_args: audit_calls.append("append"),
        "trade_close_outcome_v1_build": lambda **kwargs: outcome_calls.append(
            copy.deepcopy(kwargs)
        ),
    }
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(body=nodes, type_ignores=[])
            ),
            str(MAIN_FILE),
            "exec",
        ),
        namespace,
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_payload(),
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_OUTCOME_CONFLICT"
    assert result["trade"]["registry_mode_before"] == "REAL"
    assert result["trade"]["registry_entry"] == pytest.approx(1.0871)
    assert result["outcome_conflict"]["manual_outcome_present"] is True
    assert result["outcome_conflict"]["broker"]["exit_price"] == pytest.approx(
        1.089
    )
    assert result["outcome_conflict"]["existing"][
        "exit_price"
    ] == pytest.approx(1.0902)
    assert result["complete"] is False
    assert result["committed"] is False
    assert len(broker_calls) == 1
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == ["write", "append"]
