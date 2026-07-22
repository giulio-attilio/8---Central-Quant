from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import broker


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "main.py"

OPEN_ORDER_ID = "2078483751332171776"
CLOSE_ORDER_ID = "XRP-MANUAL-CLOSE-ORDER"


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


def _load_main_reconciliation_namespace(trade, broker_result):
    wanted = {
        "_rcrm_v1_float",
        "_rcrm_v1_norm_symbol",
        "_rcrm_v1_norm_side",
        "_rcrm_v1_meta",
        "_rcrm_v1_metrics",
        "_rcrm_v11_manual_outcome_conflict",
        "real_close_reconciliation_v1_run",
    }
    tree = ast.parse(MAIN_FILE.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in nodes} == wanted
    registry_calls = []
    outcome_calls = []
    audit_calls = []

    class Registry:
        def update_closed_trade(self, **kwargs):
            registry_calls.append(copy.deepcopy(kwargs))
            return {"ok": True}

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
        },
        "_rcrm_v1_values": lambda _trade: {
            "order_id": OPEN_ORDER_ID,
            "client_order_id": "FALCON-LIVE-FALCON15-1784384114",
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
