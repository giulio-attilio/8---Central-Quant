from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import broker
import trade_registry


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"
MAIN_TREE = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))

OPEN_ORDER_ID = "2078483751332171776"
CLOSE_ORDER_ID = "XRP-MANUAL-CLOSE-ORDER"


def _main_function_nodes(wanted):
    return [
        copy.deepcopy(node)
        for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]


def _deduped_income(rows):
    dedup = broker._rcr_v1_dedupe_income(rows)
    return {
        "ok": True,
        "items": dedup["items"],
        "count": dedup["deduped_count"],
        "raw_count": dedup["raw_count"],
        "deduped_count": dedup["deduped_count"],
        "duplicates_removed": dedup["duplicates_removed"],
        "duplicate_conflicts": dedup["conflicts"],
        "dedup_ok": dedup["dedup_ok"],
        "attempts": [],
    }


def _broker_rows(closing_volume="9"):
    opening = {
        "id": "OPEN-TRADE-XRP",
        "order": OPEN_ORDER_ID,
        "timestamp": 1_784_384_114_000,
        "side": "buy",
        "price": 1.0871,
        "amount": 18,
        "fee": {"cost": 0.00489195},
        "info": {
            "orderId": OPEN_ORDER_ID,
            "tranId": "OPEN-FILL-XRP",
            "volume": "9",
            "positionSide": "LONG",
        },
    }
    closing = {
        "id": "CLOSE-TRADE-XRP",
        "order": CLOSE_ORDER_ID,
        "timestamp": 1_784_384_214_000,
        "side": "sell",
        "price": 1.089,
        "amount": 18,
        "fee": {"cost": 0.00490050},
        "realizedPnl": 0.0171,
        "info": {
            "orderId": CLOSE_ORDER_ID,
            "tranId": "CLOSE-FILL-XRP",
            "volume": str(closing_volume),
            "positionSide": "LONG",
        },
    }
    return opening, closing


def _income_rows():
    opening_fee = {
        "tranId": "OPEN-FEE-XRP",
        "tradeId": "OPEN-TRADE-XRP",
        "incomeType": "COMMISSION",
        "info": "Position opening fee",
        "income": "-0.00489195",
        "time": 1_784_384_114_100,
        "symbol": "XRP-USDT",
    }
    return [
        opening_fee,
        copy.deepcopy(opening_fee),
        {
            "tranId": "CLOSE-FEE-XRP",
            "tradeId": "CLOSE-TRADE-XRP",
            "incomeType": "COMMISSION",
            "info": "Position closingfee",
            "income": "-0.00490050",
            "time": 1_784_384_214_100,
            "symbol": "XRP-USDT",
        },
        {
            "tranId": "CLOSE-PNL-XRP",
            "tradeId": "CLOSE-TRADE-XRP",
            "incomeType": "REALIZED_PNL",
            "info": "Realized PnL",
            "income": "0.0171",
            "time": 1_784_384_214_100,
            "symbol": "XRP-USDT",
        },
        {
            "tranId": "FUNDING-XRP",
            "incomeType": "FUNDING_FEE",
            "income": "-0.00049847",
            "time": 1_784_384_200_000,
            "symbol": "XRP-USDT",
        },
    ]


def _run_broker_reconciliation(monkeypatch, closing_volume="9", income_rows=None):
    opening, closing = _broker_rows(closing_volume=closing_volume)
    order = {
        "id": OPEN_ORDER_ID,
        "timestamp": 1_784_384_114_000,
        "average": 1.0871,
        "amount": 18,
        "info": {
            "orderId": OPEN_ORDER_ID,
            "volume": "9",
            "commission": "0.00489195",
        },
    }
    income = _deduped_income(_income_rows() if income_rows is None else income_rows)
    monkeypatch.setattr(
        broker,
        "fetch_order_by_id",
        lambda *_args, **_kwargs: {"ok": True, "order": copy.deepcopy(order)},
    )
    monkeypatch.setattr(
        broker,
        "fetch_order_trades",
        lambda *_args, **_kwargs: {
            "ok": True,
            "all_trades": [copy.deepcopy(opening), copy.deepcopy(closing)],
            "error": None,
        },
    )
    monkeypatch.setattr(
        broker,
        "fetch_realized_income",
        lambda *_args, **_kwargs: copy.deepcopy(income),
    )
    monkeypatch.setattr(broker, "get_positions", lambda *_args, **_kwargs: [])

    return broker.reconcile_closed_trade(
        symbol="XRPUSDT",
        side="LONG",
        open_order_id=OPEN_ORDER_ID,
        client_order_id="FALCON-LIVE-FALCON15-1784384114",
        opened_epoch=1_784_384_114,
        qty=9,
        entry_price=1.0871,
    )


def test_xrp_factual_volume_fees_funding_and_net_pnl(monkeypatch):
    result = _run_broker_reconciliation(monkeypatch)

    assert result["complete"] is True
    assert result["status"] == "BROKER_CLOSE_RECONCILED"
    assert result["expected_qty"] == pytest.approx(9)
    assert result["closed_qty"] == pytest.approx(9)
    assert result["qty_complete"] is True
    assert result["qty_exceeds_expected"] is False
    assert result["exit_price"] == pytest.approx(1.089)
    assert result["realized_pnl_gross"] == pytest.approx(0.0171)
    assert result["opening_fee"] == pytest.approx(0.00489195)
    assert result["closing_fee"] == pytest.approx(0.00490050)
    assert result["funding"] == pytest.approx(-0.00049847)
    assert result["net_pnl"] == pytest.approx(0.00680908)
    assert result["opening_fee_source"] == "INCOME_LEDGER_DEDUPED"
    assert result["closing_fee_source"] == "INCOME_LEDGER_DEDUPED"
    assert result["income_duplicates_removed"] == 1
    assert all("orderId" not in item for item in _income_rows())
    assert result["fee_income_tran_ids"] == [
        "CLOSE-FEE-XRP",
        "OPEN-FEE-XRP",
    ]
    assert result["sent"] is False
    assert result["would_send_order"] is False


def test_raw_bingx_volume_precedes_ccxt_amount_and_info_amount_is_never_qty():
    assert broker._rcr_v1_amount(
        {"amount": 18, "info": {"volume": "9", "amount": "999"}}
    ) == pytest.approx(9)
    assert broker._rcr_v1_amount(
        {"info": {"qty": "7", "amount": "999"}}
    ) == pytest.approx(7)
    assert broker._rcr_v1_amount({"info": {"amount": "999"}}) == 0


def test_closing_quantity_above_expected_is_blocked(monkeypatch):
    result = _run_broker_reconciliation(monkeypatch, closing_volume="10")

    assert result["complete"] is False
    assert result["status"] == "CLOSING_QTY_EXCEEDS_EXPECTED"
    assert result["closed_qty"] == pytest.approx(10)
    assert result["qty_complete"] is False
    assert result["qty_exceeds_expected"] is True
    assert "CLOSING_QTY_EXCEEDS_EXPECTED" in result["issues"]


def test_fee_without_unique_temporal_or_identity_association_is_inconclusive(
    monkeypatch,
):
    rows = _income_rows()
    rows.append(
        {
            "tranId": "AMBIGUOUS-FEE-XRP",
            "tradeId": "",
            "incomeType": "COMMISSION",
            "info": "",
            "income": "-0.001",
            "time": 1_784_384_164_000,
            "symbol": "XRP-USDT",
        }
    )

    result = _run_broker_reconciliation(monkeypatch, income_rows=rows)

    assert result["complete"] is False
    assert result["status"] == "FEE_ASSOCIATION_INCONCLUSIVE"
    assert result["fee_association_ok"] is False
    assert result["fee_association_ambiguities"] == [
        {
            "tran_id": "AMBIGUOUS-FEE-XRP",
            "trade_id": None,
            "reason": "MULTIPLE_FEE_ASSOCIATIONS",
            "semantic_roles": [],
            "reference_roles": [],
            "time_roles": ["CLOSING", "OPENING"],
        }
    ]
    assert "AMBIGUOUS_FEE_ASSOCIATION" in result["issues"]


def test_fee_info_text_alone_without_symbol_and_time_is_not_associated():
    common = {
        "symbol": "XRPUSDT",
        "opening_reference_ids": {"OPEN-TRADE-XRP"},
        "closing_reference_ids": {"CLOSE-TRADE-XRP"},
        "opening_window": (1_784_384_000.0, 1_784_384_200.0),
        "closing_window": (1_784_384_200.0, 1_784_384_300.0),
    }
    missing_symbol = broker._rcr_v11_fee_income_role(
        {
            "tranId": "NO-SYMBOL",
            "tradeId": "OPEN-TRADE-XRP",
            "incomeType": "COMMISSION",
            "info": "Position opening fee",
            "time": 1_784_384_114_000,
        },
        **common,
    )
    missing_time = broker._rcr_v11_fee_income_role(
        {
            "tranId": "NO-TIME",
            "tradeId": "OPEN-TRADE-XRP",
            "incomeType": "COMMISSION",
            "info": "Position opening fee",
            "symbol": "XRP-USDT",
        },
        **common,
    )

    assert missing_symbol["role"] is None
    assert missing_symbol["ambiguous"] is False
    assert missing_time["role"] is None
    assert missing_time["ambiguous"] is False


@pytest.mark.parametrize(
    (
        "info_text",
        "trade_id",
        "timestamp_ms",
        "semantic_roles",
        "reference_roles",
        "time_roles",
    ),
    [
        (
            "Position opening fee",
            "UNLINKED-TRADE",
            1_784_385_100_000,
            ["OPENING"],
            [],
            ["CLOSING"],
        ),
        (
            "Position closingfee",
            "UNLINKED-TRADE",
            1_784_384_100_000,
            ["CLOSING"],
            [],
            ["OPENING"],
        ),
        (
            "",
            "OPEN-TRADE-XRP",
            1_784_385_100_000,
            [],
            ["OPENING"],
            ["CLOSING"],
        ),
        (
            "",
            "CLOSE-TRADE-XRP",
            1_784_384_100_000,
            [],
            ["CLOSING"],
            ["OPENING"],
        ),
    ],
)
def test_fee_phase_evidence_conflicting_with_time_is_fail_closed(
    info_text,
    trade_id,
    timestamp_ms,
    semantic_roles,
    reference_roles,
    time_roles,
):
    result = broker._rcr_v11_fee_income_role(
        {
            "tranId": "CONFLICTING-FEE",
            "tradeId": trade_id,
            "incomeType": "COMMISSION",
            "info": info_text,
            "income": "-0.001",
            "time": timestamp_ms,
            "symbol": "XRP-USDT",
        },
        symbol="XRPUSDT",
        opening_reference_ids={"OPEN-TRADE-XRP"},
        closing_reference_ids={"CLOSE-TRADE-XRP"},
        opening_window=(1_784_384_000.0, 1_784_384_200.0),
        closing_window=(1_784_385_000.0, 1_784_385_200.0),
    )

    assert result["role"] is None
    assert result["ambiguous"] is True
    assert result["reason"] == "CONFLICTING_FEE_ASSOCIATION_EVIDENCE"
    assert result["semantic_roles"] == semantic_roles
    assert result["reference_roles"] == reference_roles
    assert result["time_roles"] == time_roles


@pytest.mark.parametrize(
    ("role", "info_text", "trade_id", "timestamp_ms"),
    [
        (
            "OPENING",
            "Position opening fee",
            "OPEN-TRADE-XRP",
            1_784_384_100_000,
        ),
        (
            "CLOSING",
            "Position closingfee",
            "CLOSE-TRADE-XRP",
            1_784_385_100_000,
        ),
    ],
)
def test_compatible_fee_phase_evidence_remains_associated(
    role,
    info_text,
    trade_id,
    timestamp_ms,
):
    result = broker._rcr_v11_fee_income_role(
        {
            "tranId": f"{role}-FEE",
            "tradeId": trade_id,
            "incomeType": "COMMISSION",
            "info": info_text,
            "income": "-0.001",
            "time": timestamp_ms,
            "symbol": "XRP-USDT",
        },
        symbol="XRPUSDT",
        opening_reference_ids={"OPEN-TRADE-XRP"},
        closing_reference_ids={"CLOSE-TRADE-XRP"},
        opening_window=(1_784_384_000.0, 1_784_384_200.0),
        closing_window=(1_784_385_000.0, 1_784_385_200.0),
    )

    assert result["role"] == role
    assert result["ambiguous"] is False
    assert result["reason"] is None
    assert result["semantic_roles"] == [role]
    assert result["reference_roles"] == [role]
    assert result["time_roles"] == [role]


def test_conflicting_fee_phase_makes_full_reconciliation_inconclusive(monkeypatch):
    rows = _income_rows()
    rows[0]["time"] = 1_784_384_500_000
    rows[1]["time"] = 1_784_384_500_000

    result = _run_broker_reconciliation(monkeypatch, income_rows=rows)

    assert result["complete"] is False
    assert result["fee_association_ok"] is False
    assert result["financial_dedup_ok"] is False
    assert result["status"] == "FEE_ASSOCIATION_INCONCLUSIVE"
    assert result["fee_association_ambiguities"][0]["reason"] == (
        "CONFLICTING_FEE_ASSOCIATION_EVIDENCE"
    )


def _load_main_reconciliation_namespace(
    trade,
    broker_result,
    *,
    selected_identity=None,
    find_diagnostics=None,
):
    wanted = {
        "_rcrm_v1_float",
        "_rcrm_v1_norm_symbol",
        "_rcrm_v1_norm_side",
        "_rcrm_v1_meta",
        "_rcrm_v1_metrics",
        "_rcrm_v11_manual_outcome_conflict",
        "_rcrm_v11_validate_broker_identity",
        "real_close_reconciliation_v1_run",
    }
    nodes = _main_function_nodes(wanted)
    assert {node.name for node in nodes} == wanted
    registry_calls = []
    outcome_calls = []
    audit_calls = []
    selected_identity = selected_identity or {
        "ok": True,
        "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114",
        "client_order_id": "FALCON-LIVE-FALCON15-1784384114",
        "order_id": OPEN_ORDER_ID,
        "states": {},
        "issues": [],
        "source": "TRADE_REGISTRY_CANONICAL_ALIASES",
    }
    find_diagnostics = find_diagnostics or {
        "strong_identity_supplied": False,
        "supplied_identity": {},
    }

    class Registry:
        STRONG_IDENTITY_ALIASES = trade_registry.STRONG_IDENTITY_ALIASES

        def update_closed_trade(self, **kwargs):
            registry_calls.append(copy.deepcopy(kwargs))
            return {"ok": True}

        strong_identity_alias_state = staticmethod(
            trade_registry.strong_identity_alias_state
        )
        normalize_strong_identity_value = staticmethod(
            trade_registry.normalize_strong_identity_value
        )

    namespace = {
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST-V1.1",
        "REAL_CLOSE_RECONCILIATION_V1_LATEST_FILE": "unused-latest",
        "REAL_CLOSE_RECONCILIATION_V1_EVENTS_FILE": "unused-events",
        "BROKER_IMPORT_ERROR": None,
        "central_broker": SimpleNamespace(
            reconcile_closed_trade=lambda **_kwargs: copy.deepcopy(broker_result)
        ),
        "central_trade_registry": Registry(),
        "_rcrm_v1_now": lambda: "22/07/2026 16:00:00",
        "_rcrm_v1_find_closed_trade": lambda _payload: {
            "ok": True,
            "trade_id": trade["trade_id"],
            "trade": copy.deepcopy(trade),
            "diagnostics": copy.deepcopy(find_diagnostics),
        },
        "_rcrm_v11_selected_strong_identity": lambda _trade: copy.deepcopy(
            selected_identity
        ),
        "_rcrm_v1_values": lambda _trade, **_kwargs: {
            "lifecycle_id": selected_identity.get("lifecycle_id"),
            "order_id": OPEN_ORDER_ID,
            "client_order_id": "FALCON-LIVE-FALCON15-1784384114",
            "identity_sources": {
                "lifecycle_id": "TRADE_REGISTRY_CANONICAL_ALIASES",
                "client_order_id": "TRADE_REGISTRY_CANONICAL_ALIASES",
                "order_id": "TRADE_REGISTRY_CANONICAL_ALIASES",
            },
            "legacy_execution_evidence_used": False,
            "entry": 1.0871,
            "stop": 1.084175,
            "qty": 9.0,
            "opened_at": None,
            "opened_epoch": 1_784_384_114,
        },
        "_rcrm_v1_public": lambda value: value,
        "_rcrm_v1_write": lambda *_args: audit_calls.append("write"),
        "_rcrm_v1_append": lambda *_args: audit_calls.append("append"),
        "trade_close_outcome_v1_build": lambda **kwargs: outcome_calls.append(
            copy.deepcopy(kwargs)
        )
        or {"commit": {"committed": True}},
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN_FILE), "exec"), namespace)
    return namespace, registry_calls, outcome_calls, audit_calls


def _complete_broker_result(**updates):
    result = {
        "ok": True,
        "complete": True,
        "status": "BROKER_CLOSE_RECONCILED",
        "open_order_id": OPEN_ORDER_ID,
        "client_order_id": "FALCON-LIVE-FALCON15-1784384114",
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
        "close_order_ids": [CLOSE_ORDER_ID],
        "data_quality": "HIGH_BROKER_RECONCILED_DEDUPED",
    }
    result.update(updates)
    return result


def test_manual_outcome_exit_conflict_blocks_registry_and_outcome_writes():
    trade = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
        "source": "TRADE_REGISTRY",
        "registry_mode": "REAL",
        "execution_mode": "LIVE",
        "metadata": {"outcome_status": "OUTCOME_RECORDED"},
        "outcome": {
            "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
            "outcome_id": "XRP-MANUAL-OUTCOME",
            "data_quality": "MANUAL_CONFIRMED",
            "exit_price": 1.0902,
        },
    }
    namespace, registry_calls, outcome_calls, audit_calls = (
        _load_main_reconciliation_namespace(trade, _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"trade_id": trade["trade_id"]},
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_OUTCOME_CONFLICT"
    assert result["broker_complete"] is True
    assert result["complete"] is False
    assert result["committed"] is False
    assert result["commit_blocked_reason"] == "MANUAL_OUTCOME_EXIT_PRICE_CONFLICT"
    assert result["outcome_conflict"]["existing"]["exit_price"] == pytest.approx(1.0902)
    assert result["outcome_conflict"]["broker"]["exit_price"] == pytest.approx(1.089)
    assert registry_calls == []
    assert outcome_calls == []
    assert audit_calls == ["write", "append"]


def test_main_propagates_inconclusive_fee_as_commit_blocker():
    trade = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
    }
    broker_result = _complete_broker_result(
        complete=False,
        status="FEE_ASSOCIATION_INCONCLUSIVE",
        financial_dedup_ok=False,
    )
    namespace, registry_calls, outcome_calls, audit_calls = (
        _load_main_reconciliation_namespace(trade, broker_result)
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"trade_id": trade["trade_id"]},
        commit=True,
        source="test",
    )

    assert result["status"] == "FEE_ASSOCIATION_INCONCLUSIVE"
    assert result["complete"] is False
    assert result["commit_blocked_reason"] == "FEE_ASSOCIATION_INCONCLUSIVE"
    assert registry_calls == []
    assert outcome_calls == []
    assert audit_calls == ["write", "append"]


def test_main_propagates_excess_quantity_as_commit_blocker():
    trade = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
    }
    broker_result = _complete_broker_result(
        complete=False,
        status="CLOSING_QTY_EXCEEDS_EXPECTED",
        closed_qty=18,
        qty_complete=False,
    )
    namespace, registry_calls, outcome_calls, _audit_calls = (
        _load_main_reconciliation_namespace(trade, broker_result)
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"trade_id": trade["trade_id"]},
        commit=True,
        source="test",
    )

    assert result["status"] == "CLOSING_QTY_EXCEEDS_EXPECTED"
    assert result["complete"] is False
    assert result["commit_blocked_reason"] == "CLOSING_QTY_EXCEEDS_EXPECTED"
    assert registry_calls == []
    assert outcome_calls == []


def _strong_identity_records():
    shared = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "XRPUSDT",
        "side": "LONG",
        "status": "CLOSED",
        "qty": 9.0,
    }
    verify = dict(
        shared,
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:OLD-VERIFY-XRP",
        client_order_id="FALCON-VERIFY-FALCON15-OLD-XRP",
        broker_order_id="VERIFY-ORDER-XRP",
        order_id="VERIFY-ORDER-XRP",
        registry_mode="VERIFY",
        execution_mode="VERIFY",
        entry=1.1123,
        sl=1.1080085714285715,
        outcome_status="CLOSED",
        outcome_source="FALCON",
    )
    real = dict(
        shared,
        lifecycle_id="CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114",
        client_order_id="FALCON-LIVE-FALCON15-1784384114",
        broker_order_id=OPEN_ORDER_ID,
        order_id=OPEN_ORDER_ID,
        registry_mode="REAL",
        execution_mode="LIVE",
        entry=1.0871,
        sl=1.084175,
        outcome={
            "outcome_status": "OUTCOME_RECORDED",
            "outcome_source": "MANUAL_CLOSE_RECONCILIATION",
            "outcome_id": "XRP-MANUAL-OUTCOME",
            "data_quality": "MANUAL_CONFIRMED",
            "exit_price": 1.0902,
        },
    )
    return verify, real


def _load_strong_lookup_namespace(closed_trades):
    wanted = {
        "_rcrm_v1_norm_symbol",
        "_rcrm_v1_norm_side",
        "_rcrm_v1_meta",
        "_rcrm_v1_find_closed_trade",
    }
    nodes = _main_function_nodes(wanted)
    assert {node.name for node in nodes} == wanted

    class ReadOnlyRegistry:
        STRONG_IDENTITY_ALIASES = trade_registry.STRONG_IDENTITY_ALIASES

        def __init__(self):
            self.reads = 0

        def load_registry_read_only(self):
            self.reads += 1
            return {"open_trades": {}, "closed_trades": copy.deepcopy(closed_trades)}

        def load_registry(self):
            raise AssertionError("mutating registry loader called")

        def get_closed_trade(self, **_kwargs):
            raise AssertionError("legacy ambiguous getter called")

        strong_identity_alias_state = staticmethod(
            trade_registry.strong_identity_alias_state
        )
        normalize_strong_identity_value = staticmethod(
            trade_registry.normalize_strong_identity_value
        )

    registry = ReadOnlyRegistry()
    namespace = {
        "central_trade_registry": registry,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN_FILE), "exec"), namespace)
    return namespace["_rcrm_v1_find_closed_trade"], registry


def test_strong_identity_fixture_has_verify_and_real_trade_id_collision():
    verify, real = _strong_identity_records()

    assert verify["trade_id"] == real["trade_id"]
    assert verify["registry_mode"] == "VERIFY"
    assert real["registry_mode"] == "REAL"
    assert verify["entry"] == pytest.approx(1.1123)
    assert real["entry"] == pytest.approx(1.0871)


@pytest.mark.parametrize(
    "strong_payload",
    [
        {
            "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114"
        },
        {"client_order_id": "FALCON-LIVE-FALCON15-1784384114"},
        {"open_order_id": OPEN_ORDER_ID},
        {"order_id": OPEN_ORDER_ID},
        {"broker_order_id": OPEN_ORDER_ID},
        {
            "lifecycle_id": "CENTRAL-FALCON-LIFECYCLE:FALCON-LIVE-FALCON15-1784384114",
            "client_order_id": "FALCON-LIVE-FALCON15-1784384114",
            "open_order_id": OPEN_ORDER_ID,
            "order_id": OPEN_ORDER_ID,
            "broker_order_id": OPEN_ORDER_ID,
        },
    ],
)
def test_each_strong_identity_and_all_together_select_only_real(strong_payload):
    verify, real = _strong_identity_records()
    find, registry = _load_strong_lookup_namespace([verify, real])
    payload = {
        "trade_id": real["trade_id"],
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
        **strong_payload,
    }

    result = find(payload)

    assert result["ok"] is True
    assert result["trade"]["registry_mode"] == "REAL"
    assert result["trade"]["entry"] == pytest.approx(1.0871)
    diagnostics = result["diagnostics"]
    assert diagnostics["candidate_count_before"] == 2
    assert diagnostics["candidate_count_after"] == 1
    assert diagnostics["matched_identity"]["registry_mode"] == "REAL"
    assert diagnostics["matched_identity"]["order_id"] == OPEN_ORDER_ID
    assert diagnostics["rejected_candidates"][0]["registry_mode"] == "VERIFY"
    assert registry.reads == 1


def test_strong_identifiers_pointing_to_different_records_are_conflict():
    verify, real = _strong_identity_records()
    find, _registry = _load_strong_lookup_namespace([verify, real])

    result = find(
        {
            "trade_id": real["trade_id"],
            "lifecycle_id": real["lifecycle_id"],
            "order_id": verify["order_id"],
        }
    )

    assert result["status"] == "REAL_CLOSE_STRONG_IDENTITY_CONFLICT"
    assert result["complete"] is False
    assert result["committed"] is False
    assert result["diagnostics"]["candidate_count_after"] == 0
    assert result["diagnostics"]["matched_identity"] is None


def test_unknown_strong_identity_never_falls_back_to_trade_id():
    verify, real = _strong_identity_records()
    find, _registry = _load_strong_lookup_namespace([verify, real])

    result = find(
        {
            "trade_id": real["trade_id"],
            "lifecycle_id": "UNKNOWN-LIFECYCLE",
        }
    )

    assert result["status"] == "REAL_CLOSE_STRONG_IDENTITY_NOT_FOUND"
    assert result["diagnostics"]["candidate_count_after"] == 0
    assert result["diagnostics"]["strong_identity_supplied"] is True


def test_ambiguous_strong_identity_is_blocked():
    _verify, real = _strong_identity_records()
    duplicate = copy.deepcopy(real)
    duplicate["client_order_id"] = "OTHER-CLIENT"
    duplicate["broker_order_id"] = "OTHER-ORDER"
    duplicate["order_id"] = "OTHER-ORDER"
    find, _registry = _load_strong_lookup_namespace([real, duplicate])

    result = find({"lifecycle_id": real["lifecycle_id"]})

    assert result["status"] == "REAL_CLOSE_STRONG_IDENTITY_AMBIGUOUS"
    assert result["diagnostics"]["candidate_count_after"] == 2


def test_legacy_lookup_without_strong_identity_requires_unique_candidate():
    verify, real = _strong_identity_records()
    unique_find, _registry = _load_strong_lookup_namespace([real])
    collision_find, _registry = _load_strong_lookup_namespace([verify, real])

    unique = unique_find({"trade_id": real["trade_id"]})
    collision = collision_find({"trade_id": real["trade_id"]})

    assert unique["ok"] is True
    assert unique["trade"]["registry_mode"] == "REAL"
    assert collision["status"] == "REAL_CLOSE_STRONG_IDENTITY_AMBIGUOUS"
    assert collision["complete"] is False


@pytest.mark.parametrize(
    ("mutate", "query", "field", "expected_alias"),
    [
        (
            lambda trade: trade.setdefault("metadata", {}).update(
                {"trade_lifecycle_id": "LC-CONFLICT"}
            ),
            lambda trade: {"lifecycle_id": trade["lifecycle_id"]},
            "lifecycle_id",
            "metadata.trade_lifecycle_id",
        ),
        (
            lambda trade: trade.setdefault("metadata", {}).update(
                {"clientOrderID": "CLIENT-CONFLICT"}
            ),
            lambda trade: {"client_order_id": trade["client_order_id"]},
            "client_order_id",
            "metadata.clientOrderID",
        ),
        (
            lambda trade: trade.setdefault("metadata", {}).update(
                {"broker_order_id": "ORDER-CONFLICT"}
            ),
            lambda trade: {"order_id": trade["order_id"]},
            "order_id",
            "metadata.broker_order_id",
        ),
        (
            lambda trade: trade.update(
                {"open_order_id": trade["order_id"], "orderId": "ORDER-CONFLICT"}
            ),
            lambda trade: {"open_order_id": trade["open_order_id"]},
            "order_id",
            "trade.orderId",
        ),
    ],
)
def test_internal_strong_alias_conflict_blocks_lookup(
    mutate,
    query,
    field,
    expected_alias,
):
    _verify, real = _strong_identity_records()
    mutate(real)
    find, _registry = _load_strong_lookup_namespace([real])

    result = find(query(real))

    assert result["status"] == "REAL_CLOSE_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["complete"] is False
    assert result["committed"] is False
    conflict = next(
        item
        for item in result["diagnostics"]["strong_identity_alias_conflicts"]
        if item["field"] == field
    )
    assert len(conflict["normalized_values"]) == 2
    assert expected_alias in conflict["aliases_present"]
    assert conflict["registry_index"] == 0
    assert conflict["registry_mode"] == "REAL"
    assert conflict["reason"] == "STRONG_IDENTITY_ALIAS_CONFLICT"


@pytest.mark.parametrize(
    ("payload", "field", "expected_aliases"),
    [
        (
            {"lifecycle_id": "LC-REAL", "trade_lifecycle_id": "LC-OTHER"},
            "lifecycle_id",
            {"trade.lifecycle_id", "trade.trade_lifecycle_id"},
        ),
        (
            {
                "client_order_id": "CLIENT-REAL",
                "clientOrderID": "CLIENT-OTHER",
            },
            "client_order_id",
            {"trade.client_order_id", "trade.clientOrderID"},
        ),
        (
            {"open_order_id": "ORDER-REAL", "broker_order_id": "ORDER-OTHER"},
            "order_id",
            {"trade.open_order_id", "trade.broker_order_id"},
        ),
    ],
)
def test_supplied_strong_alias_conflict_blocks_before_registry_read(
    payload,
    field,
    expected_aliases,
):
    _verify, real = _strong_identity_records()
    find, registry = _load_strong_lookup_namespace([real])

    result = find(payload)

    assert result["status"] == "REAL_CLOSE_SUPPLIED_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["complete"] is False
    assert result["broker_complete"] is False
    assert result["committed"] is False
    assert registry.reads == 0
    conflict = result["diagnostics"]["strong_identity_alias_conflicts"][0]
    assert conflict["field"] == field
    assert len(conflict["normalized_values"]) == 2
    assert set(conflict["aliases_present"]) == expected_aliases
    assert conflict["reason"] == "STRONG_IDENTITY_ALIAS_CONFLICT"


def test_all_repeated_supplied_strong_aliases_with_same_value_are_accepted():
    _verify, real = _strong_identity_records()
    payload = {
        "lifecycle_id": real["lifecycle_id"],
        "trade_lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        "clientOrderId": real["client_order_id"],
        "clientOrderID": real["client_order_id"],
        "client_tag": real["client_order_id"],
        "open_order_id": real["order_id"],
        "broker_order_id": real["order_id"],
        "order_id": real["order_id"],
        "orderId": real["order_id"],
        "live_order_id": real["order_id"],
        "entry_order_id": real["order_id"],
    }
    find, registry = _load_strong_lookup_namespace([real])

    result = find(payload)

    assert result["ok"] is True
    assert result["trade"]["registry_mode"] == "REAL"
    assert result["diagnostics"]["strong_identity_alias_conflicts"] == []
    assert registry.reads == 1


def test_supplied_client_id_aliases_are_case_insensitive():
    _verify, real = _strong_identity_records()
    find, registry = _load_strong_lookup_namespace([real])

    result = find(
        {
            "client_order_id": real["client_order_id"].lower(),
            "clientOrderID": real["client_order_id"].upper(),
        }
    )

    assert result["ok"] is True
    assert result["diagnostics"]["supplied_identity"]["client_order_id"] == real[
        "client_order_id"
    ]
    assert registry.reads == 1


def test_repeated_strong_aliases_with_same_values_remain_valid():
    _verify, real = _strong_identity_records()
    real.update(
        {
            "trade_lifecycle_id": real["lifecycle_id"],
            "clientOrderID": real["client_order_id"],
            "open_order_id": real["order_id"],
            "orderId": real["order_id"],
        }
    )
    real["metadata"] = {
        "lifecycle_id": real["lifecycle_id"],
        "client_tag": real["client_order_id"],
        "entry_order_id": real["order_id"],
    }
    find, _registry = _load_strong_lookup_namespace([real])

    result = find(_factual_xrp_request(real))

    assert result["ok"] is True
    assert result["diagnostics"]["strong_identity_alias_conflicts"] == []
    assert result["diagnostics"]["matched_identity"]["order_id"] == OPEN_ORDER_ID


def test_clean_real_candidate_wins_over_internally_conflicting_verify():
    verify, real = _strong_identity_records()
    verify["metadata"] = {
        "trade_lifecycle_id": real["lifecycle_id"],
        "clientOrderID": real["client_order_id"],
        "broker_order_id": real["order_id"],
    }
    find, _registry = _load_strong_lookup_namespace([verify, real])

    result = find(_factual_xrp_request(real))

    assert result["ok"] is True
    assert result["trade"]["registry_mode"] == "REAL"
    rejected_verify = next(
        item
        for item in result["diagnostics"]["rejected_candidates"]
        if item["registry_mode"] == "VERIFY"
    )
    assert "STRONG_IDENTITY_ALIAS_CONFLICT" in rejected_verify["reasons"]
    assert {
        item["field"]
        for item in rejected_verify["strong_identity_alias_conflicts"]
    } == {"lifecycle_id", "client_order_id", "order_id"}


def test_update_closed_trade_rejects_alias_conflict_atomically(monkeypatch):
    _verify, real = _strong_identity_records()
    real.setdefault("metadata", {})["broker_order_id"] = "ORDER-CONFLICT"
    registry = {"open_trades": {}, "closed_trades": [copy.deepcopy(real)]}
    saves = []
    monkeypatch.setattr(trade_registry, "load_registry", lambda: copy.deepcopy(registry))
    monkeypatch.setattr(
        trade_registry, "save_registry", lambda payload: saves.append(copy.deepcopy(payload))
    )

    result = trade_registry.update_closed_trade(
        trade_id=real["trade_id"],
        expected_identity={
            "lifecycle_id": real["lifecycle_id"],
            "client_order_id": real["client_order_id"],
            "order_id": real["order_id"],
        },
        outcome_status="SHOULD_NOT_WRITE",
    )

    assert result["ok"] is False
    assert result["error"] == "CLOSED_TRADE_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["alias_conflicts"][0]["reason"] == "STRONG_IDENTITY_ALIAS_CONFLICT"
    assert saves == []


def test_lookup_and_writer_share_all_canonical_strong_aliases(monkeypatch):
    _verify, real = _strong_identity_records()
    alias_only = {
        key: value
        for key, value in real.items()
        if key not in {"lifecycle_id", "client_order_id", "broker_order_id", "order_id"}
    }
    alias_only.update(
        {
            "trade_lifecycle_id": real["lifecycle_id"],
            "clientOrderID": real["client_order_id"],
            "open_order_id": real["order_id"],
        }
    )
    find, _registry = _load_strong_lookup_namespace([alias_only])
    found = find(_factual_xrp_request(real))
    assert found["ok"] is True

    registry = {"open_trades": {}, "closed_trades": [copy.deepcopy(alias_only)]}
    saves = []
    monkeypatch.setattr(trade_registry, "load_registry", lambda: copy.deepcopy(registry))
    monkeypatch.setattr(
        trade_registry, "save_registry", lambda payload: saves.append(copy.deepcopy(payload))
    )
    monkeypatch.setattr(
        trade_registry, "_observe_shadow_registry_snapshot", lambda *_args: None
    )
    updated = trade_registry.update_closed_trade(
        trade_id=real["trade_id"],
        expected_identity={
            "trade_lifecycle_id": real["lifecycle_id"],
            "clientOrderID": real["client_order_id"],
            "open_order_id": real["order_id"],
        },
        marker="UPDATED",
    )

    assert updated["ok"] is True
    assert len(saves) == 1
    assert saves[0]["closed_trades"][0]["marker"] == "UPDATED"


def _load_integrated_strong_runner(closed_trades, broker_result):
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
    nodes = _main_function_nodes(wanted)
    assert {node.name for node in nodes} == wanted
    registry_updates = []
    registry_reads = []
    broker_calls = []
    outcome_calls = []
    audit_calls = []

    class Registry:
        STRONG_IDENTITY_ALIASES = trade_registry.STRONG_IDENTITY_ALIASES

        def load_registry_read_only(self):
            registry_reads.append("read")
            return {"open_trades": {}, "closed_trades": copy.deepcopy(closed_trades)}

        def load_registry(self):
            raise AssertionError("mutating registry loader called")

        def get_closed_trade(self, **_kwargs):
            raise AssertionError("legacy ambiguous getter called")

        def update_closed_trade(self, **kwargs):
            registry_updates.append(copy.deepcopy(kwargs))
            return {"ok": True}

        strong_identity_alias_state = staticmethod(
            trade_registry.strong_identity_alias_state
        )
        normalize_strong_identity_value = staticmethod(
            trade_registry.normalize_strong_identity_value
        )

    def reconcile(**kwargs):
        broker_calls.append(copy.deepcopy(kwargs))
        return copy.deepcopy(broker_result)

    namespace = {
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST-REVIEW4",
        "REAL_CLOSE_RECONCILIATION_V1_LATEST_FILE": "unused-latest",
        "REAL_CLOSE_RECONCILIATION_V1_EVENTS_FILE": "unused-events",
        "BROKER_IMPORT_ERROR": None,
        "TRADE_REGISTRY_IMPORT_ERROR": None,
        "central_broker": SimpleNamespace(reconcile_closed_trade=reconcile),
        "central_trade_registry": Registry(),
        "_rcrm_v1_execution_evidence": lambda _trade: None,
        "_rcrm_v1_now": lambda: "22/07/2026 16:00:00",
        "_rcrm_v1_public": lambda value: value,
        "_rcrm_v1_write": lambda *_args: audit_calls.append("write"),
        "_rcrm_v1_append": lambda *_args: audit_calls.append("append"),
        "trade_close_outcome_v1_build": lambda **kwargs: outcome_calls.append(
            copy.deepcopy(kwargs)
        )
        or {"commit": {"committed": True}},
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(MAIN_FILE), "exec"), namespace)
    namespace["_test_registry_reads"] = registry_reads
    return namespace, registry_updates, broker_calls, outcome_calls, audit_calls


def _factual_xrp_request(real):
    return {
        "trade_id": real["trade_id"],
        "lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        "open_order_id": real["broker_order_id"],
        "symbol": "XRPUSDT",
        "side": "LONG",
        "bot": "FALCON",
        "setup": "FALCON15",
    }


def _move_strong_identity_to_aliases(
    trade,
    *,
    lifecycle_alias="lifecycle_id",
    client_alias="client_order_id",
    order_alias="order_id",
    metadata_only=False,
):
    item = copy.deepcopy(trade)
    values = {
        "lifecycle_id": trade.get("lifecycle_id"),
        "client_order_id": trade.get("client_order_id"),
        "order_id": trade.get("order_id") or trade.get("broker_order_id"),
    }
    metadata = dict(item.get("metadata") or {})
    for aliases in trade_registry.STRONG_IDENTITY_ALIASES.values():
        for alias in aliases:
            item.pop(alias, None)
            metadata.pop(alias, None)
    target = metadata if metadata_only else item
    target[lifecycle_alias] = values["lifecycle_id"]
    target[client_alias] = values["client_order_id"]
    target[order_alias] = values["order_id"]
    if metadata:
        item["metadata"] = metadata
    elif "metadata" in item:
        item.pop("metadata")
    return item


def _without_strong_identity_fields(trade, *fields):
    item = copy.deepcopy(trade)
    metadata = dict(item.get("metadata") or {})
    for field in fields:
        for alias in trade_registry.STRONG_IDENTITY_ALIASES[field]:
            item.pop(alias, None)
            metadata.pop(alias, None)
    if metadata:
        item["metadata"] = metadata
    elif "metadata" in item:
        item.pop("metadata")
    return item


@pytest.mark.parametrize("order_alias", ["open_order_id", "entry_order_id"])
def test_selected_order_alias_is_forwarded_canonically_to_broker(order_alias):
    _verify, real = _strong_identity_records()
    alias_real = _move_strong_identity_to_aliases(
        real,
        order_alias=order_alias,
    )
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([alias_real], _complete_broker_result())
    )
    payload = {
        "trade_id": real["trade_id"],
        "lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        order_alias: real["order_id"],
    }

    result = namespace["real_close_reconciliation_v1_run"](
        payload=payload,
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert result["selected_strong_identity"]["order_id"] == real["order_id"]
    assert result["trade"]["order_id"] == real["order_id"]
    assert registry_updates == []
    assert outcome_calls == []


def test_selected_client_order_id_alias_is_forwarded_canonically_to_broker():
    _verify, real = _strong_identity_records()
    alias_real = _move_strong_identity_to_aliases(
        real,
        client_alias="clientOrderID",
    )
    namespace, _registry_updates, broker_calls, _outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([alias_real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={
            "lifecycle_id": real["lifecycle_id"],
            "clientOrderID": real["client_order_id"].lower(),
            "order_id": real["order_id"],
        },
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert result["selected_strong_identity"]["client_order_id"] == real[
        "client_order_id"
    ]


def test_strong_aliases_only_in_metadata_flow_through_complete_runner():
    _verify, real = _strong_identity_records()
    alias_real = _move_strong_identity_to_aliases(
        real,
        lifecycle_alias="trade_lifecycle_id",
        client_alias="clientOrderID",
        order_alias="entry_order_id",
        metadata_only=True,
    )
    namespace, _registry_updates, broker_calls, _outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([alias_real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert result["selected_strong_identity"]["lifecycle_id"] == real[
        "lifecycle_id"
    ]
    assert result["selected_strong_identity"]["order_id"] == real["order_id"]


def test_strong_selection_never_uses_execution_evidence_from_other_lifecycle():
    _verify, real = _strong_identity_records()
    alias_real = _move_strong_identity_to_aliases(
        real,
        order_alias="open_order_id",
        client_alias="clientOrderID",
    )
    namespace, _registry_updates, broker_calls, _outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([alias_real], _complete_broker_result())
    )
    namespace["_rcrm_v1_execution_evidence"] = lambda _trade: pytest.fail(
        "execution evidence must not be read after strong selection"
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert result["diagnostics"]["legacy_execution_evidence_used"] is False
    assert set(result["diagnostics"]["identity_sources"].values()) == {
        "TRADE_REGISTRY_CANONICAL_ALIASES"
    }


def test_unique_legacy_lookup_marks_execution_evidence_identity_source():
    _verify, real = _strong_identity_records()
    legacy = copy.deepcopy(real)
    metadata = dict(legacy.get("metadata") or {})
    for aliases in trade_registry.STRONG_IDENTITY_ALIASES.values():
        for alias in aliases:
            legacy.pop(alias, None)
            metadata.pop(alias, None)
    legacy["metadata"] = metadata
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([legacy], _complete_broker_result())
    )
    namespace["_rcrm_v1_execution_evidence"] = lambda _trade: {
        "order_id": real["order_id"],
        "clientOrderID": real["client_order_id"],
    }

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"trade_id": real["trade_id"]},
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert result["diagnostics"]["legacy_execution_evidence_used"] is True
    assert result["diagnostics"]["identity_sources"]["order_id"] == (
        "LEGACY_EXECUTION_EVIDENCE"
    )
    assert result["diagnostics"]["identity_sources"]["client_order_id"] == (
        "LEGACY_EXECUTION_EVIDENCE"
    )
    assert registry_updates == []
    assert outcome_calls == []


def test_legacy_execution_evidence_cannot_authorize_registry_commit():
    _verify, real = _strong_identity_records()
    legacy = copy.deepcopy(real)
    legacy.pop("outcome", None)
    legacy["outcome_status"] = "RECONCILED_WITHOUT_PNL"
    legacy["outcome_source"] = ""
    metadata = dict(legacy.get("metadata") or {})
    for aliases in trade_registry.STRONG_IDENTITY_ALIASES.values():
        for alias in aliases:
            legacy.pop(alias, None)
            metadata.pop(alias, None)
    legacy["metadata"] = metadata
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([legacy], _complete_broker_result())
    )
    namespace["_rcrm_v1_execution_evidence"] = lambda _trade: {
        "order_id": real["order_id"],
        "clientOrderID": real["client_order_id"],
    }

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"trade_id": real["trade_id"]},
        commit=True,
        source="test",
    )

    assert len(broker_calls) == 1
    assert result["status"] == "REAL_CLOSE_LEGACY_IDENTITY_INSUFFICIENT"
    assert result["complete"] is False
    assert result["committed"] is False
    assert result["commit_blocked_reason"] == (
        "REAL_CLOSE_LEGACY_IDENTITY_INSUFFICIENT"
    )
    assert registry_updates == []
    assert outcome_calls == []


def test_only_conflicting_candidate_blocks_before_broker_or_writes():
    _verify, real = _strong_identity_records()
    real.setdefault("metadata", {})["clientOrderID"] = "CLIENT-CONFLICT"
    namespace, registry_updates, broker_calls, outcome_calls, audit_calls = (
        _load_integrated_strong_runner([real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["complete"] is False
    assert result["committed"] is False
    assert broker_calls == []
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == []


def test_supplied_alias_conflict_blocks_before_registry_broker_and_all_writes():
    _verify, real = _strong_identity_records()
    namespace, registry_updates, broker_calls, outcome_calls, audit_calls = (
        _load_integrated_strong_runner([real], _complete_broker_result())
    )
    payload = _factual_xrp_request(real)
    payload["trade_lifecycle_id"] = "LC-CONFLICT"

    result = namespace["real_close_reconciliation_v1_run"](
        payload=payload,
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_SUPPLIED_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["complete"] is False
    assert result["broker_complete"] is False
    assert result["committed"] is False
    assert namespace["_test_registry_reads"] == []
    assert broker_calls == []
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == []


def test_selected_strong_identity_incomplete_blocks_before_broker():
    _verify, real = _strong_identity_records()
    selected_identity = {
        "ok": False,
        "lifecycle_id": None,
        "client_order_id": real["client_order_id"],
        "order_id": real["order_id"],
        "states": {},
        "issues": [],
        "source": "TRADE_REGISTRY_CANONICAL_ALIASES",
    }
    namespace, registry_calls, outcome_calls, audit_calls = (
        _load_main_reconciliation_namespace(
            real,
            _complete_broker_result(),
            selected_identity=selected_identity,
            find_diagnostics={
                "strong_identity_supplied": True,
                "supplied_identity": {
                    "lifecycle_id": real["lifecycle_id"],
                    "client_order_id": real["client_order_id"],
                    "order_id": real["order_id"],
                },
            },
        )
    )
    namespace["central_broker"].reconcile_closed_trade = lambda **_kwargs: pytest.fail(
        "broker must not be called with incomplete selected identity"
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_SELECTED_STRONG_IDENTITY_INCOMPLETE"
    assert result["complete"] is False
    assert result["broker_complete"] is False
    assert result["committed"] is False
    assert "LIFECYCLE_ID_MISSING_AFTER_SELECTION" in result["diagnostics"][
        "selected_strong_identity_issues"
    ]
    assert registry_calls == []
    assert outcome_calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    ("supplied_field", "missing_fields", "expected_issues"),
    [
        (
            "lifecycle_id",
            ("client_order_id", "order_id"),
            {
                "CLIENT_ORDER_ID_MISSING_AFTER_SELECTION",
                "ORDER_ID_MISSING_AFTER_SELECTION",
            },
        ),
        (
            "client_order_id",
            ("lifecycle_id", "order_id"),
            {
                "LIFECYCLE_ID_MISSING_AFTER_SELECTION",
                "ORDER_ID_MISSING_AFTER_SELECTION",
            },
        ),
        (
            "order_id",
            ("lifecycle_id", "client_order_id"),
            {
                "LIFECYCLE_ID_MISSING_AFTER_SELECTION",
                "CLIENT_ORDER_ID_MISSING_AFTER_SELECTION",
            },
        ),
        (
            "lifecycle_id",
            ("order_id",),
            {"ORDER_ID_MISSING_AFTER_SELECTION"},
        ),
        (
            "lifecycle_id",
            ("client_order_id",),
            {"CLIENT_ORDER_ID_MISSING_AFTER_SELECTION"},
        ),
        (
            "client_order_id",
            ("lifecycle_id",),
            {"LIFECYCLE_ID_MISSING_AFTER_SELECTION"},
        ),
    ],
)
def test_any_strong_selection_requires_complete_canonical_identity_before_broker(
    supplied_field,
    missing_fields,
    expected_issues,
):
    _verify, real = _strong_identity_records()
    incomplete = _without_strong_identity_fields(real, *missing_fields)
    supplied_value = {
        "lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        "order_id": real["order_id"],
    }[supplied_field]
    namespace, registry_updates, broker_calls, outcome_calls, audit_calls = (
        _load_integrated_strong_runner(
            [incomplete],
            _complete_broker_result(),
        )
    )
    namespace["_rcrm_v1_execution_evidence"] = lambda _trade: pytest.fail(
        "execution evidence must not complete a strong selection"
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={supplied_field: supplied_value},
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_SELECTED_STRONG_IDENTITY_INCOMPLETE"
    assert result["complete"] is False
    assert result["broker_complete"] is False
    assert result["committed"] is False
    assert set(
        result["diagnostics"]["selected_strong_identity_issues"]
    ) == expected_issues
    assert namespace["_test_registry_reads"] == ["read"]
    assert broker_calls == []
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == []


def test_complete_selected_identity_still_reaches_broker_once():
    _verify, real = _strong_identity_records()
    namespace, registry_updates, broker_calls, outcome_calls, audit_calls = (
        _load_integrated_strong_runner([real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload={"lifecycle_id": real["lifecycle_id"]},
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert result["selected_strong_identity"]["lifecycle_id"] == real[
        "lifecycle_id"
    ]
    assert result["diagnostics"]["selected_strong_identity_issues"] == []
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == ["write", "append"]


def test_writer_receives_exact_selected_canonical_identity():
    _verify, real = _strong_identity_records()
    real = copy.deepcopy(real)
    real.pop("outcome", None)
    real["outcome_status"] = "RECONCILED_WITHOUT_PNL"
    real["outcome_source"] = ""
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert len(broker_calls) == 1
    assert len(registry_updates) == 1
    assert registry_updates[0]["expected_identity"] == {
        "lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        "order_id": real["order_id"],
    }
    assert len(outcome_calls) == 1
    assert result["selected_strong_identity"]["source"] == (
        "TRADE_REGISTRY_CANONICAL_ALIASES"
    )


def test_broker_client_id_case_difference_remains_match():
    _verify, real = _strong_identity_records()
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner(
            [real],
            _complete_broker_result(
                client_order_id=real["client_order_id"].lower()
            ),
        )
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=False,
        source="test",
    )

    assert len(broker_calls) == 1
    assert result["broker_identity_validation"]["comparisons"][
        "client_order_id"
    ]["result"] == "MATCH"
    assert "BROKER_CLIENT_ORDER_ID_CONFLICT" not in result[
        "broker_identity_validation"
    ]["issues"]
    assert registry_updates == []
    assert outcome_calls == []


def test_alias_only_real_identity_never_mixes_with_verify_collision():
    verify, real = _strong_identity_records()
    alias_real = _move_strong_identity_to_aliases(
        real,
        lifecycle_alias="trade_lifecycle_id",
        client_alias="clientOrderID",
        order_alias="entry_order_id",
        metadata_only=True,
    )
    alias_real.pop("outcome", None)
    alias_real["outcome_status"] = "RECONCILED_WITHOUT_PNL"
    alias_real["outcome_source"] = ""
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner(
            [verify, alias_real],
            _complete_broker_result(),
        )
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert result["diagnostics"]["matched_identity"]["registry_mode"] == "REAL"
    assert result["trade"]["registry_entry"] == pytest.approx(1.0871)
    assert len(broker_calls) == 1
    assert broker_calls[0]["open_order_id"] == real["order_id"]
    assert broker_calls[0]["client_order_id"] == real["client_order_id"]
    assert len(registry_updates) == 1
    assert registry_updates[0]["trade_id"] == real["trade_id"]
    assert registry_updates[0]["expected_identity"] == {
        "lifecycle_id": real["lifecycle_id"],
        "client_order_id": real["client_order_id"],
        "order_id": real["order_id"],
    }
    assert registry_updates[0]["entry"] == pytest.approx(1.0871)
    assert len(outcome_calls) == 1


def test_factual_xrp_selects_real_and_detects_manual_outcome_conflict():
    verify, real = _strong_identity_records()
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner([verify, real], _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_OUTCOME_CONFLICT"
    assert result["trade"]["registry_mode_before"] == "REAL"
    assert result["trade"]["registry_entry"] == pytest.approx(1.0871)
    assert result["outcome_conflict"]["manual_outcome_present"] is True
    assert result["outcome_conflict"]["broker"]["exit_price"] == pytest.approx(1.089)
    assert result["outcome_conflict"]["existing"]["exit_price"] == pytest.approx(1.0902)
    assert result["complete"] is False
    assert result["committed"] is False
    assert result["diagnostics"]["matched_identity"]["registry_mode"] == "REAL"
    assert len(broker_calls) == 1
    assert registry_updates == []
    assert outcome_calls == []


@pytest.mark.parametrize(
    ("records_builder", "payload_builder", "expected_status"),
    [
        (
            lambda verify, real: [verify, real],
            lambda verify, real: {
                "trade_id": real["trade_id"],
                "lifecycle_id": "UNKNOWN-LIFECYCLE",
            },
            "REAL_CLOSE_STRONG_IDENTITY_NOT_FOUND",
        ),
        (
            lambda verify, real: [verify, real],
            lambda verify, real: {
                "trade_id": real["trade_id"],
                "lifecycle_id": real["lifecycle_id"],
                "order_id": verify["order_id"],
            },
            "REAL_CLOSE_STRONG_IDENTITY_CONFLICT",
        ),
        (
            lambda verify, real: [real, copy.deepcopy(real)],
            lambda verify, real: {"lifecycle_id": real["lifecycle_id"]},
            "REAL_CLOSE_STRONG_IDENTITY_AMBIGUOUS",
        ),
        (
            lambda verify, real: [verify, real],
            lambda verify, real: {"trade_id": real["trade_id"]},
            "REAL_CLOSE_STRONG_IDENTITY_AMBIGUOUS",
        ),
    ],
)
def test_all_strong_identity_blocks_have_zero_operational_writes(
    records_builder,
    payload_builder,
    expected_status,
):
    verify, real = _strong_identity_records()
    records = records_builder(verify, real)
    namespace, registry_updates, broker_calls, outcome_calls, audit_calls = (
        _load_integrated_strong_runner(records, _complete_broker_result())
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=payload_builder(verify, real),
        commit=True,
        source="test",
    )

    assert result["status"] == expected_status
    assert result["complete"] is False
    assert result["committed"] is False
    assert broker_calls == []
    assert registry_updates == []
    assert outcome_calls == []
    assert audit_calls == []


@pytest.mark.parametrize(
    ("broker_update", "comparison_field"),
    [
        ({"open_order_id": "OTHER-ORDER"}, "order_id"),
        ({"client_order_id": "OTHER-CLIENT"}, "client_order_id"),
        ({"symbol": "ETHUSDT"}, "symbol"),
        ({"side": "SHORT"}, "side"),
        ({"expected_qty": 10.0}, "qty"),
        ({"entry_price": 1.2}, "entry_price"),
    ],
)
def test_broker_identity_divergence_blocks_registry_and_outcome(
    broker_update,
    comparison_field,
):
    _verify, real = _strong_identity_records()
    namespace, registry_updates, broker_calls, outcome_calls, _audit_calls = (
        _load_integrated_strong_runner(
            [real],
            _complete_broker_result(**broker_update),
        )
    )

    result = namespace["real_close_reconciliation_v1_run"](
        payload=_factual_xrp_request(real),
        commit=True,
        source="test",
    )

    assert result["status"] == "REAL_CLOSE_BROKER_IDENTITY_DIVERGENCE"
    assert result["complete"] is False
    assert result["committed"] is False
    assert result["broker_identity_validation"]["comparisons"][comparison_field][
        "result"
    ] == "CONFLICT"
    assert len(broker_calls) == 1
    assert registry_updates == []
    assert outcome_calls == []


def test_route_forwards_all_strong_identity_query_parameters():
    route_node = copy.deepcopy(
        next(
            node
            for node in MAIN_TREE.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "real_close_reconciliation_v1_route"
        )
    )
    route_node.decorator_list = []
    captured = []
    query = {
        "trade_id": "FALCON:FALCON15:XRPUSDT:LONG",
        "lifecycle_id": "LC-XRP",
        "trade_lifecycle_id": "LC-XRP",
        "client_order_id": "CLIENT-XRP",
        "clientOrderId": "CLIENT-XRP",
        "clientOrderID": "CLIENT-XRP",
        "client_tag": "CLIENT-XRP",
        "open_order_id": "OPEN-XRP",
        "broker_order_id": "OPEN-XRP",
        "order_id": "OPEN-XRP",
        "orderId": "OPEN-XRP",
        "live_order_id": "OPEN-XRP",
        "entry_order_id": "OPEN-XRP",
    }
    namespace = {
        "request": SimpleNamespace(method="GET", args=query, path="/realclosereconciliation"),
        "_rcrm_v1_bool": lambda value, default=False: default if value is None else bool(value),
        "REAL_CLOSE_RECONCILIATION_MAIN_V1_VERSION": "TEST-REVIEW4",
        "real_close_reconciliation_v1_run": lambda **kwargs: captured.append(
            copy.deepcopy(kwargs)
        )
        or {"ok": True, "status": "PREVIEW"},
    }
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[route_node], type_ignores=[])),
            str(MAIN_FILE),
            "exec",
        ),
        namespace,
    )

    response, status = namespace["real_close_reconciliation_v1_route"]()

    assert status == 200
    assert response["status"] == "PREVIEW"
    assert captured[0]["payload"] == query
    assert captured[0]["commit"] is False


def test_registry_atomic_update_uses_expected_strong_identity(monkeypatch):
    import trade_registry

    verify, real = _strong_identity_records()
    state = {"open_trades": {}, "closed_trades": [verify, real]}
    saved = []
    monkeypatch.setattr(trade_registry, "load_registry", lambda: copy.deepcopy(state))
    monkeypatch.setattr(
        trade_registry,
        "save_registry",
        lambda payload: saved.append(copy.deepcopy(payload)),
    )
    monkeypatch.setattr(
        trade_registry,
        "_observe_shadow_registry_snapshot",
        lambda *_args, **_kwargs: None,
    )

    result = trade_registry.update_closed_trade(
        trade_id=real["trade_id"],
        expected_identity={
            "lifecycle_id": real["lifecycle_id"],
            "client_order_id": real["client_order_id"],
            "order_id": real["order_id"],
        },
        outcome_status="BROKER_RECONCILED",
    )

    assert result["ok"] is True
    assert result["index"] == 1
    assert len(saved) == 1
    assert saved[0]["closed_trades"][0]["registry_mode"] == "VERIFY"
    assert saved[0]["closed_trades"][0].get("outcome_status") == "CLOSED"
    assert saved[0]["closed_trades"][1]["registry_mode"] == "REAL"
    assert saved[0]["closed_trades"][1]["outcome_status"] == "BROKER_RECONCILED"


def test_registry_rejects_conflicting_expected_identity_aliases_without_save(
    monkeypatch,
):
    _verify, real = _strong_identity_records()
    state = {"open_trades": {}, "closed_trades": [copy.deepcopy(real)]}
    saved = []
    monkeypatch.setattr(trade_registry, "load_registry", lambda: copy.deepcopy(state))
    monkeypatch.setattr(
        trade_registry,
        "save_registry",
        lambda payload: saved.append(copy.deepcopy(payload)),
    )

    result = trade_registry.update_closed_trade(
        trade_id=real["trade_id"],
        expected_identity={
            "lifecycle_id": real["lifecycle_id"],
            "trade_lifecycle_id": "LC-CONFLICT",
        },
        outcome_status="SHOULD_NOT_WRITE",
    )

    assert result["ok"] is False
    assert result["error"] == "EXPECTED_STRONG_IDENTITY_ALIAS_CONFLICT"
    assert result["alias_conflicts"][0]["field"] == "lifecycle_id"
    assert result["alias_conflicts"][0]["reason"] == "STRONG_IDENTITY_ALIAS_CONFLICT"
    assert saved == []


def test_registry_client_identity_is_case_insensitive_for_expected_and_record(
    monkeypatch,
):
    _verify, real = _strong_identity_records()
    real["metadata"] = {"clientOrderID": real["client_order_id"].lower()}
    state = {"open_trades": {}, "closed_trades": [copy.deepcopy(real)]}
    saved = []
    monkeypatch.setattr(trade_registry, "load_registry", lambda: copy.deepcopy(state))
    monkeypatch.setattr(
        trade_registry,
        "save_registry",
        lambda payload: saved.append(copy.deepcopy(payload)),
    )
    monkeypatch.setattr(
        trade_registry,
        "_observe_shadow_registry_snapshot",
        lambda *_args, **_kwargs: None,
    )

    result = trade_registry.update_closed_trade(
        trade_id=real["trade_id"],
        expected_identity={
            "client_order_id": real["client_order_id"].lower(),
            "clientOrderID": real["client_order_id"].upper(),
        },
        marker="CASE_INSENSITIVE_MATCH",
    )

    assert result["ok"] is True
    assert len(saved) == 1
    assert saved[0]["closed_trades"][0]["marker"] == "CASE_INSENSITIVE_MATCH"
