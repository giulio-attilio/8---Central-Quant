from __future__ import annotations

import broker


class _Exchange:
    def __init__(self, order=None, *, cancel_error=None):
        self.order = dict(order or {})
        self.cancel_error = cancel_error
        self.calls = []

    def fetch_order(self, order_id, symbol):
        self.calls.append(("fetch", order_id, symbol))
        return dict(self.order)

    def cancel_order(self, order_id, symbol):
        self.calls.append(("cancel", order_id, symbol))
        if self.cancel_error:
            raise self.cancel_error
        self.order["status"] = "canceled"
        self.order["info"] = {"status": "CANCELED"}
        return {"id": order_id}


def _order(**updates):
    value = {
        "id": "ENTRY-1",
        "symbol": "SOLUSDT",
        "clientOrderId": "ENTRY-CID-1",
        "side": "buy",
        "type": "market",
        "status": "open",
        "amount": 1.0,
        "filled": 0.4,
        "remaining": 0.6,
        "average": 100.0,
        "info": {"status": "PARTIALLY_FILLED"},
    }
    value.update(updates)
    return value


def _authorized_context():
    return {
        "operation": "cancel_managed_entry_order",
        "symbol": "SOLUSDT",
        "order_id": "ENTRY-1",
        "client_order_id": "ENTRY-CID-1",
        "side": "BUY",
        "position_side": "LONG",
        "reason": "INITIAL_STOP_FAILURE_ENTRY_CANCEL",
    }


def _configure(monkeypatch, ex, *, context=None, live=True):
    expected = _authorized_context()
    monkeypatch.setattr(broker, "normalize_symbol", lambda value: str(value or ""))
    monkeypatch.setattr(broker, "exchange", lambda: ex)
    monkeypatch.setattr(broker, "_rpm_live_write_enabled", lambda: live)
    monkeypatch.setattr(
        broker,
        "_rpm_validate_auth",
        lambda _token, _expected: {
            "ok": True,
            "context": dict(context if context is not None else expected),
        },
    )


def _cancel():
    return broker.cancel_managed_entry_order(
        symbol="SOLUSDT",
        order_id="ENTRY-1",
        client_order_id="ENTRY-CID-1",
        side="BUY",
        position_side="LONG",
        execution_auth_token="TEST-TOKEN",
        reason="INITIAL_STOP_FAILURE_ENTRY_CANCEL",
    )


def test_exact_partial_entry_cancel_requires_terminal_readback(monkeypatch):
    ex = _Exchange(_order())
    _configure(monkeypatch, ex)

    result = _cancel()

    assert result["ok"] is True
    assert result["terminal"] is True
    assert result["status"] == "ENTRY_ORDER_CANCELLED_AND_TERMINAL"
    assert result["sent"] is True
    assert result["filled"] == 0.4
    assert result["average"] == 100.0
    assert [call[0] for call in ex.calls] == ["fetch", "cancel", "fetch"]


def test_entry_cancel_identity_mismatch_never_calls_exchange_cancel(monkeypatch):
    ex = _Exchange(_order(clientOrderId="OTHER-CID"))
    _configure(monkeypatch, ex)

    result = _cancel()

    assert result["ok"] is False
    assert result["status"] == "ENTRY_CANCEL_ORDER_IDENTITY_MISMATCH"
    assert result["send_attempted"] is False
    assert all(call[0] != "cancel" for call in ex.calls)


def test_entry_cancel_requires_full_single_use_auth_scope(monkeypatch):
    ex = _Exchange(_order())
    context = _authorized_context()
    context["client_order_id"] = "OTHER-CID"
    _configure(monkeypatch, ex, context=context)

    result = _cancel()

    assert result["ok"] is False
    assert result["status"] == "ENTRY_CANCEL_AUTH_DENIED"
    assert ex.calls == []


def test_entry_cancel_transport_exception_is_unknown_and_not_reported_terminal(monkeypatch):
    ex = _Exchange(_order(), cancel_error=TimeoutError("synthetic timeout"))
    _configure(monkeypatch, ex)

    result = _cancel()

    assert result["ok"] is False
    assert result["status"] == "ENTRY_CANCEL_OUTCOME_UNKNOWN"
    assert result["send_attempted"] is True
    assert result["send_outcome_unknown"] is True
    assert result["terminal"] is False
    assert [call[0] for call in ex.calls] == ["fetch", "cancel"]


def test_entry_cancel_dry_run_never_reads_or_mutates_exchange(monkeypatch):
    ex = _Exchange(_order())
    _configure(monkeypatch, ex, live=False)

    result = _cancel()

    assert result["ok"] is True
    assert result["status"] == "ENTRY_CANCEL_DRY_RUN"
    assert result["sent"] is False
    assert result["would_send_order"] is True
    assert ex.calls == []
