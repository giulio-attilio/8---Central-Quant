from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"


def _load_functions(names: set[str], namespace: dict):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == names
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(SOURCE), "exec"), namespace)
    return namespace


def _load_broker_positions(*, raw):
    namespace = {
        "_broker_call": lambda name: (raw, None),
        "normalize_symbol_for_risk": lambda value: str(value or "").replace("/", "").upper(),
    }
    _load_functions({"_broker_open_positions"}, namespace)
    return namespace["_broker_open_positions"]


def _awareness_payload(*, broker_error=None, central_error_type=None, manual=None, central_only=None):
    manual = manual or []
    central_only = central_only or []
    return {
        "ok": not broker_error and not central_only,
        "summary": {
            "broker_error": broker_error,
            "central_error_type": central_error_type,
            "broker_bingx_open_count": len(manual),
            "central_live_count": len(central_only),
            "matched_count": 0,
        },
        "manual_or_external_positions": manual,
        "central_only_positions": central_only,
    }


def test_divergence_audit_uses_in_memory_awareness_without_persisting():
    calls = []

    def builder(*, persist):
        calls.append(persist)
        return _awareness_payload()

    namespace = {"_mpa_v1_build_payload": builder, "_mpa_v1_text": lambda _payload: "ok"}
    _load_functions({"bingx_divergence_payload"}, namespace)

    result = namespace["bingx_divergence_payload"]()

    assert result["ok"] is True
    assert result["status"] == "OK"
    assert calls == [False]


def test_broker_position_read_error_is_an_active_divergence():
    namespace = {
        "_mpa_v1_build_payload": lambda **_kwargs: _awareness_payload(
            broker_error="synthetic unavailable"
        )
    }
    _load_functions({"bingx_divergence_payload", "bingx_divergence_warning_payload"}, namespace)

    result = namespace["bingx_divergence_warning_payload"]()

    assert result["active"] is True
    assert result["status"] == "BROKER_POSITION_READ_ERROR"
    assert result["broker_error_present"] is True
    assert "synthetic unavailable" not in repr(result)


def test_central_position_read_error_is_an_active_divergence():
    namespace = {
        "_mpa_v1_build_payload": lambda **_kwargs: _awareness_payload(
            central_error_type="OSError"
        )
    }
    _load_functions({"bingx_divergence_payload", "bingx_divergence_warning_payload"}, namespace)

    result = namespace["bingx_divergence_warning_payload"]()

    assert result["active"] is True
    assert result["status"] == "CENTRAL_POSITION_READ_ERROR"
    assert result["central_error_present"] is True


def test_manual_or_external_position_is_not_treated_as_reconciled():
    namespace = {
        "_mpa_v1_build_payload": lambda **_kwargs: _awareness_payload(
            manual=[{"symbol": "BTCUSDT", "side": "LONG"}]
        )
    }
    _load_functions({"bingx_divergence_payload", "bingx_divergence_warning_payload"}, namespace)

    result = namespace["bingx_divergence_warning_payload"]()

    assert result["active"] is True
    assert result["manual_or_external_count"] == 1
    assert result["status"] == "MANUAL_OR_EXTERNAL_POSITION_PRESENT"


def test_live_divergence_denies_even_if_intended_live_flag_is_false():
    namespace = {}
    _load_functions({"_apply_bingx_divergence_gate"}, namespace)
    reasons, warnings = [], []

    namespace["_apply_bingx_divergence_gate"](
        "LIVE", False, {"active": True}, reasons, warnings
    )

    assert reasons == ["LIVE_BLOCKED_BY_BINGX_POSITION_RECONCILIATION"]
    assert warnings == []


def test_non_live_divergence_remains_a_warning_not_a_new_deny():
    namespace = {}
    _load_functions({"_apply_bingx_divergence_gate"}, namespace)
    reasons, warnings = [], []

    namespace["_apply_bingx_divergence_gate"](
        "PAPER", False, {"active": True, "message": "not reconciled"}, reasons, warnings
    )

    assert reasons == []
    assert warnings == ["not reconciled"]


def test_live_risk_decision_applies_divergence_gate_before_computing_allowed():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def can_open_trade_decision(payload: dict):")
    end = source.index("def build_execution_report():", start)
    body = source[start:end]

    assert "_apply_bingx_divergence_gate(" in body
    assert "allowed = len(reasons) == 0" in body


def test_manual_position_awareness_persistence_can_be_disabled_for_risk_reads():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_mpa_v1_build_payload"
    )
    assert any(arg.arg == "persist" for arg in function.args.kwonlyargs)
    guarded_persistence = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "persist"
    ]
    assert len(guarded_persistence) == 1
    strict_position_read = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_central_live_positions_payload"
    ]
    assert len(strict_position_read) == 1
    assert any(
        keyword.arg == "strict"
        and isinstance(keyword.value, ast.UnaryOp)
        and isinstance(keyword.value.op, ast.Not)
        and isinstance(keyword.value.operand, ast.Name)
        and keyword.value.operand.id == "persist"
        for keyword in strict_position_read[0].keywords
    )
    strict_broker_read = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_broker_open_positions"
    ]
    assert len(strict_broker_read) == 1
    assert any(
        keyword.arg == "strict"
        and isinstance(keyword.value, ast.UnaryOp)
        and isinstance(keyword.value.op, ast.Not)
        and isinstance(keyword.value.operand, ast.Name)
        and keyword.value.operand.id == "persist"
        for keyword in strict_broker_read[0].keywords
    )
    assert "_flad_v1_write_snapshot" in {
        node.func.id
        for node in ast.walk(guarded_persistence[0])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_strict_broker_position_read_rejects_none_instead_of_treating_it_as_flat():
    positions, error = _load_broker_positions(raw=None)(strict=True)

    assert positions == []
    assert error == "broker positions response invalid"


def test_strict_broker_position_read_accepts_an_explicit_empty_list():
    positions, error = _load_broker_positions(raw=[])(strict=True)

    assert positions == []
    assert error is None


def test_strict_broker_position_read_rejects_rows_without_quantity_evidence():
    positions, error = _load_broker_positions(raw=[{"symbol": "BTC/USDT"}])(strict=True)

    assert positions == []
    assert error == "broker positions quantity missing"


def test_strict_broker_position_read_recognizes_exchange_info_quantity():
    positions, error = _load_broker_positions(
        raw=[{"info": {"symbol": "BTCUSDT", "positionAmt": "0"}}]
    )(strict=True)

    assert error is None
    assert positions == []


def test_strict_broker_position_read_rejects_malformed_exchange_quantity():
    positions, error = _load_broker_positions(
        raw=[{"symbol": "BTC/USDT", "contracts": "unknown"}]
    )(strict=True)

    assert positions == []
    assert error == "broker positions quantity invalid"
