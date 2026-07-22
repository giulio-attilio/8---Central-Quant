from __future__ import annotations

import ast
import copy
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = ROOT / "main.py"
MAIN_SOURCE = MAIN_PATH.read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SOURCE)


def _final_top_level_function(name: str) -> ast.FunctionDef:
    matches = [
        node
        for node in MAIN_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert matches, name
    return copy.deepcopy(matches[-1])


def _compile_functions(names: tuple[str, ...], namespace: dict) -> dict:
    nodes = [_final_top_level_function(name) for name in names]
    module = ast.Module(body=sorted(nodes, key=lambda node: node.lineno), type_ignores=[])
    ast.fix_missing_locations(module)
    result = dict(namespace)
    exec(compile(module, str(MAIN_PATH), "exec"), result)
    return result


def _nested_function(parent: str, name: str) -> ast.FunctionDef:
    parent_node = _final_top_level_function(parent)
    matches = [
        node
        for node in ast.walk(parent_node)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, (parent, name)
    return copy.deepcopy(matches[0])


def test_execution_final_gate_uses_lifecycle_and_attempt_but_no_route_local_client_id():
    values = {
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "SOLUSDT",
        "side": "LONG",
        "entry": "76",
        "sl": "75",
        "tp50": "77",
        "signal_id": "SIG-FINAL-GATE-1",
    }
    namespace = _compile_functions(
        ("_efg_v1_build_payload",),
        {
            "_efg_v1_arg": lambda name, default="": str(values.get(name, default)),
            "_efg_v1_norm_symbol": lambda value: str(value).upper(),
            "_efg_v1_norm_side": lambda value: str(value).upper(),
            "_efg_v1_float": lambda value, default=None: float(value),
            "hashlib": hashlib,
        },
    )

    payload = namespace["_efg_v1_build_payload"]()

    expected_lifecycle = (
        "CENTRAL-EXECUTION-FINAL-GATE-LIFECYCLE:"
        + hashlib.sha256(b"SIG-FINAL-GATE-1").hexdigest().upper()
    )
    assert payload["lifecycle_id"] == expected_lifecycle
    assert payload["client_order_attempt_id"] == "SIG-FINAL-GATE-1"
    assert payload["client_order_attempt_sequence"] == "0"
    for alias in (
        "client_order_id", "broker_client_order_id", "clientOrderID",
        "clientOrderId", "client_tag",
    ):
        assert payload[alias] is None


def test_auto_bridge_strips_legacy_ids_and_passes_strong_identity_to_engine():
    captured: dict = {}
    stored: list[dict] = []
    context = SimpleNamespace(active=False)

    def run_execution_engine(*, payload, mode, dry_run):
        captured.update({"payload": dict(payload), "mode": mode, "dry_run": dry_run})
        return {"ok": True, "status": "ENGINE_TEST_RESULT", "sent": False}

    namespace = _compile_functions(
        ("auto_real_execution_bridge_v1_process",),
        {
            "_AUTO_REAL_EXECUTION_BRIDGE_V1_CONTEXT": context,
            "AUTO_REAL_EXECUTION_BRIDGE_V1_VERSION": "test",
            "_arb_v1_basic_eligibility": lambda payload, risk_result, source=None: {
                "eligible": True,
                "payload": dict(payload or {}),
                "config": {"require_signal_id": True},
                "reasons": [],
                "warnings": [],
                "signal_id": (payload or {}).get("signal_id"),
            },
            "_arb_v1_config": lambda: {"require_signal_id": True},
            "_arb_v1_signal_key": lambda *args, **kwargs: "signal:SIG-BRIDGE-1",
            "_arb_v1_now": lambda: "2026-07-21T00:00:00Z",
            "_arb_v1_payload_summary": lambda payload: dict(payload),
            "_arb_v1_load_state": lambda: {},
            "_arb_v1_save_state": lambda state: stored.append(copy.deepcopy(state)),
            "_arb_v1_call_final_gate_for_payload": lambda *args, **kwargs: {
                "ok": True,
                "failed_blocking_codes": [],
            },
            "_arb_v1_sanitize_public": lambda value: value,
            "_arb_v1_payload_with_auth": lambda payload: dict(payload),
            "_arb_v1_append_event": lambda event: None,
            "_arb_v1_notify_blocked": lambda *args, **kwargs: None,
            "run_execution_engine": run_execution_engine,
            "hashlib": hashlib,
            "time": time,
        },
    )
    process = namespace["auto_real_execution_bridge_v1_process"]

    result = process(
        payload={
            "signal_id": "SIG-BRIDGE-1",
            "bot": "FALCON",
            "symbol": "SOLUSDT",
            "side": "LONG",
            "client_order_id": "LEGACY-DO-NOT-FORWARD",
            "clientOrderID": "legacy-do-not-forward",
            "broker_client_order_id": "LEGACY-DO-NOT-FORWARD",
        },
        risk_result={},
        source="test",
        execute=True,
        dry_run=False,
    )

    engine_payload = captured["payload"]
    expected_lifecycle = (
        "CENTRAL-AUTO-BRIDGE-LIFECYCLE:"
        + hashlib.sha256(b"signal:SIG-BRIDGE-1").hexdigest().upper()
    )
    assert result["executed"] is True
    assert captured["mode"] == "LIVE"
    assert captured["dry_run"] is False
    assert engine_payload["lifecycle_id"] == expected_lifecycle
    assert engine_payload["client_order_attempt_id"] == "signal:SIG-BRIDGE-1"
    assert engine_payload["client_order_attempt_sequence"] == 0
    for alias in (
        "client_order_id", "clientOrderId", "clientOrderID",
        "broker_client_order_id", "client_tag",
    ):
        assert alias not in engine_payload
    assert stored


def test_execution_console_compatibility_helper_never_constructs_or_truncates_client_id():
    helper = _nested_function("execution_console_route", "_new_broker_client_order_id")
    module = ast.Module(body=[helper], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict = {}
    exec(compile(module, str(MAIN_PATH), "exec"), namespace)

    assert namespace["_new_broker_client_order_id"]("FALCON", "SOLUSDT", "LONG") is None
    assert not any(isinstance(node, ast.Subscript) for node in ast.walk(helper))

    route_source = ast.get_source_segment(
        MAIN_SOURCE,
        next(
            node
            for node in MAIN_TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == "execution_console_route"
        ),
    )
    assert 'broker_client_order_id_source = "EXECUTION_ENGINE_ACCOUNT_AUTHORITY"' in route_source
    assert 'request.form.get("lifecycle_id")' in route_source
    assert '"lifecycle_id": lifecycle_id_value' in route_source
    assert '"client_order_attempt_id": signal_id_value' in route_source
    assert '"client_order_attempt_sequence": 0' in route_source


def test_main_has_no_raw_exchange_create_order_writer_or_patch():
    raw_calls = []
    raw_mutations = []
    for node in ast.walk(MAIN_TREE):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "create_order":
                raw_calls.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"getattr", "setattr"} and len(node.args) >= 2:
                marker = node.args[1]
                if isinstance(marker, ast.Constant) and marker.value == "create_order":
                    raw_mutations.append(node.lineno)

    assert raw_calls == []
    assert raw_mutations == []

    namespace = _compile_functions(
        ("_dshm_v1_patch_exchange_create_order",),
        {"DISASTER_STOP_HEDGE_MODE_FIX_V1_VERSION": "test"},
    )

    class ExchangeBomb:
        def __getattr__(self, name):
            raise AssertionError(f"exchange accessed: {name}")

    result = namespace["_dshm_v1_patch_exchange_create_order"](
        "test.exchange", ExchangeBomb()
    )
    assert result["patched"] is False
    assert result["status"] == "ACCOUNT_CLIENT_ORDER_ID_BROKER_BOUNDARY_OWNS_CREATE_ORDER"


def test_falcon_live_audit_fail_safe_never_calls_broker_without_receipt():
    namespace = _compile_functions(
        ("_fleag_v1_fail_safe_close",),
        {
            "_fleag_v1_extract_live_result": lambda result: dict(result or {}),
            "_fleag_v1_norm_symbol": lambda value: str(value or "").upper(),
            "_fleag_v1_norm_side": lambda value: str(value or "").upper(),
        },
    )
    fail_safe = namespace["_fleag_v1_fail_safe_close"]

    blocked = fail_safe(
        {"symbol": "SOLUSDT", "side": "LONG"},
        {"amount": 0.13},
    )
    assert blocked["status"] == "ACCOUNT_CLIENT_ORDER_ID_RESERVATION_REQUIRED"
    assert blocked["sent"] is False
    assert blocked["broker_called"] is False
    assert blocked["reconciliation_required"] is True

    missing = fail_safe({}, {})
    assert missing["status"] == "FAILSAFE_CLOSE_MISSING_SYMBOL_SIDE"
    assert missing["sent"] is False
    assert missing["broker_called"] is False
