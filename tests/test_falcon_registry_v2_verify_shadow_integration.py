from __future__ import annotations

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from falcon_registry_v2_verify_shadow import (
    OBSERVED,
    SHADOW_STAGE_POST_DECISION,
    SHADOW_STAGE_PRE_DECISION,
)
from falcon_registry_v2_verify_shadow_runtime_adapter import (
    FalconRegistryV2VerifyShadowRuntimeAdapter,
)


ROOT = Path(__file__).resolve().parents[1]
FALCON_SOURCE = ROOT / "bots" / "falcon.py"
_DEFAULT_RESPONSE = object()


class _Response:
    def __init__(self, payload):
        self.status_code = 200
        self.text = "ok"
        self._payload = payload

    def json(self):
        return copy.deepcopy(self._payload)


class _BrokerProbe:
    def __init__(self):
        self.calls = []

    def ensure_partial_capable_notional(self, **kwargs):
        self.calls.append(("ensure_partial_capable_notional", copy.deepcopy(kwargs)))
        return {
            "ok": True,
            "allowed": True,
            "partial_capable": True,
            "notional_usdt": kwargs["planned_notional_usdt"],
            "status": "PARTIAL_CAPABLE",
        }

    def ready_check(self):
        self.calls.append(("ready_check", {}))
        return {"ok": True, "status": "READY"}

    def __getattr__(self, name):
        def unexpected_mutation(*args, **kwargs):
            del args, kwargs
            raise AssertionError(f"unexpected broker call: {name}")

        return unexpected_mutation


class _RegistryProbe:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def unexpected_registry_call(*args, **kwargs):
            del args, kwargs
            self.calls.append(name)
            raise AssertionError(f"unexpected Registry call: {name}")

        return unexpected_registry_call


def _definition(tree, name, node_type, *, first=False):
    nodes = [
        node for node in tree.body if isinstance(node, node_type) and node.name == name
    ]
    assert nodes, f"{name} not found"
    return copy.deepcopy(nodes[0] if first else nodes[-1])


def _load_verify_flow(
    *,
    shadow_enabled,
    observer,
    allowed=True,
    mode="VERIFY",
    include_helper=True,
    json_value=_DEFAULT_RESPONSE,
):
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    body = [
        _definition(tree, "central_can_open_trade", ast.FunctionDef),
        _definition(tree, "execute_signal_if_allowed", ast.FunctionDef, first=True),
    ]
    if include_helper:
        body = [
            _definition(tree, "FalconV2VerifyShadowObservationError", ast.ClassDef),
            _definition(tree, "_falcon_observe_v2_verify_shadow", ast.FunctionDef),
            *body,
        ]
    module = ast.Module(
        body=body,
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    broker = _BrokerProbe()
    registry = _RegistryProbe()
    request_calls = []

    def decision_response(payload):
        signal_id = payload["signal_id"]
        request_id = payload["decision_request_id"]
        return {
            "allowed": allowed,
            "decision": "ALLOW" if allowed else "DENY",
            "reasons": ["current V1 decision"],
            "warnings": [],
            "risk_pct": payload["risk_pct"],
            "notional_usdt": payload["notional_usdt"],
            "decision_request_id": request_id,
            "decision_id": "FALCON-DECISION-V2.7A.2:decision-a",
            "decision_identity_version": "V2.7A.2",
            "decision_identity_provenance": {
                "identity_version": "V2.7A.2",
                "request_id": request_id,
                "signal_id": signal_id,
                "mechanism": "SECRETS_TOKEN_URLSAFE_AFTER_TERMINAL_RESULT",
            },
            "decision_identity_v2_7a_2": {
                "status": "COMPLETED",
                "identity_available": True,
                "decision_request_id": request_id,
                "signal_id": signal_id,
            },
        }

    def post(url, json, timeout):
        request_calls.append((url, copy.deepcopy(json), timeout))
        payload = decision_response(json) if json_value is _DEFAULT_RESPONSE else json_value
        return _Response(payload)

    def issue_request_identity(signal):
        signal_id = signal["signal_id"]
        return {
            "decision_request_id": "FALCON-DECISION-REQUEST-V2.7A.2:request-a",
            "decision_request_identity_version": "V2.7A.2",
            "decision_request_identity_provenance": {
                "identity_version": "V2.7A.2",
                "signal_id": signal_id,
                "issuer_file": "bots/falcon.py",
                "issuer_function": "central_can_open_trade",
                "mechanism": "SECRETS_TOKEN_URLSAFE",
                "signal_correlation_method": "EXACT_SIGNAL_ID",
            },
        }

    def partial_sizing(signal):
        return broker.ensure_partial_capable_notional(
            symbol=signal.get("symbol"),
            planned_notional_usdt=signal.get("real_notional_usdt"),
            max_notional_usdt=20.0,
            min_parts=2,
        )

    namespace = {
        "__name__": "isolated_falcon_v28_verify_flow",
        "FALCON_MODE": mode,
        "FALCON_USE_CENTRAL_RISK": True,
        "FALCON_SINGLE_LIVE_EXECUTION_PATH_VERSION": "test-live-contract",
        "FALCON_REAL_NOTIONAL_USDT": 5.0,
        "FALCON_REAL_MAX_NOTIONAL_USDT": 20.0,
        "FALCON_REAL_MAX_POSITIONS": 1,
        "FALCON_REQUIRE_REAL_TP50_CAPABLE": False,
        "ENABLE_REAL_TRADING": False,
        "BROKER_IMPORT_ERROR": None,
        "CENTRAL_CAN_OPEN_TRADE_URL": "http://local.test/can_open_trade",
        "FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED": shadow_enabled,
        "FALCON_REGISTRY_V2_VERIFY_SHADOW_OBSERVER": observer,
        "ensure_decision_request_identity": issue_request_identity,
        "requests": SimpleNamespace(post=post),
        "central_broker": broker,
        "central_trade_registry": registry,
        "HEALTH": {"last_execution_decision": None, "last_execution_order": None},
        "normalize_symbol_for_central": lambda value: value,
        "safe_float": lambda value, default=0.0: default if value is None else float(value),
        "get_positions": lambda: {},
        "falcon_live_positions_count": lambda positions: 0,
        "falcon_resolve_partial_capable_notional": partial_sizing,
    }
    exec(compile(module, str(FALCON_SOURCE), "exec"), namespace)
    return namespace, broker, registry, request_calls


def _signal(**updates):
    value = {
        "id": "FALCON15:BTCUSDT:LONG:2026-08-09",
        "bot": "FALCON",
        "setup": "FALCON15",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "entry": 100.0,
        "stop": 99.0,
        "tp50": 101.0,
        "risk_pct": 1.0,
        "signal_id": "FALCON-SIGNAL-V2.7A.1:signal-a",
        "signal_identity_version": "V2.7A.1",
        "signal_identity_provenance": {
            "identity_version": "V2.7A.1",
            "plan_provenance": {
                "plan_owner_type": "CENTRAL",
                "ownership_scope": "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP",
            },
        },
    }
    value.update(updates)
    return value


def _run_flow(
    *,
    shadow_enabled,
    observer=None,
    allowed=True,
    signal_updates=None,
    mode="VERIFY",
    include_helper=True,
    json_value=_DEFAULT_RESPONSE,
):
    namespace, broker, registry, request_calls = _load_verify_flow(
        shadow_enabled=shadow_enabled,
        observer=observer,
        allowed=allowed,
        mode=mode,
        include_helper=include_helper,
        json_value=json_value,
    )
    signal = _signal(**(signal_updates or {}))
    before = copy.deepcopy(signal)
    result = namespace["execute_signal_if_allowed"](signal, positions={})
    return {
        "namespace": namespace,
        "broker": broker,
        "registry": registry,
        "request_calls": request_calls,
        "signal_before": before,
        "signal_after": signal,
        "result": result,
    }


def _adapter_observer(calls):
    adapter = FalconRegistryV2VerifyShadowRuntimeAdapter()

    def observe(facts):
        diagnostic = adapter.observe(facts, enabled=True)
        calls.append((copy.deepcopy(facts), diagnostic))
        return diagnostic

    return observe


def test_optional_shadow_helper_absent_keeps_exact_v1_central_result_and_request():
    namespace, broker, registry, request_calls = _load_verify_flow(
        shadow_enabled=False,
        observer=None,
        include_helper=False,
    )
    signal = _signal()

    result = namespace["central_can_open_trade"](signal)

    assert "_falcon_observe_v2_verify_shadow" not in namespace
    assert result["allowed"] is True
    assert result["decision"] == "ALLOW"
    assert len(request_calls) == 1
    assert broker.calls == []
    assert registry.calls == []


@pytest.mark.parametrize("helper", (None, object()))
def test_optional_shadow_helper_noncallable_keeps_exact_v1_central_result(helper):
    absent_namespace, _, _, absent_requests = _load_verify_flow(
        shadow_enabled=False,
        observer=None,
        include_helper=False,
    )
    absent_signal = _signal()
    absent_result = absent_namespace["central_can_open_trade"](absent_signal)

    namespace, broker, registry, request_calls = _load_verify_flow(
        shadow_enabled=True,
        observer=None,
        include_helper=False,
    )
    namespace["_falcon_observe_v2_verify_shadow"] = helper
    signal = _signal()
    result = namespace["central_can_open_trade"](signal)

    assert result == absent_result
    assert signal == absent_signal
    assert request_calls == absent_requests
    assert broker.calls == []
    assert registry.calls == []


def test_live_central_seam_without_optional_helper_preserves_v1_payload_and_result():
    namespace, broker, registry, request_calls = _load_verify_flow(
        shadow_enabled=True,
        observer=None,
        mode="LIVE",
        include_helper=False,
    )
    signal = _signal()

    result = namespace["central_can_open_trade"](signal)

    assert result["allowed"] is True
    assert len(request_calls) == 1
    _, payload, timeout = request_calls[0]
    assert timeout == 8
    assert payload["mode"] == "LIVE"
    assert payload["intended_live"] is True
    assert payload["falcon_single_live_execution_path_v1"] == "test-live-contract"
    assert payload["signal_id"] == "FALCON-SIGNAL-V2.7A.1:signal-a"
    assert broker.calls == []
    assert registry.calls == []


def test_invalid_central_payload_uses_exact_v1_fallback_shadow_off_and_on():
    expected = {
        "allowed": False,
        "decision": "DENY",
        "status": "FALCON_LIVE_CENTRAL_RISK_INVALID",
        "reasons": ["Central returned an invalid payload."],
        "warnings": [],
    }
    observed = []
    off_namespace, off_broker, off_registry, off_requests = _load_verify_flow(
        shadow_enabled=False,
        observer=None,
        json_value=["not", "a", "mapping"],
    )
    on_namespace, on_broker, on_registry, on_requests = _load_verify_flow(
        shadow_enabled=True,
        observer=_adapter_observer(observed),
        json_value=["not", "a", "mapping"],
    )
    off_signal = _signal()
    on_signal = _signal()

    off_result = off_namespace["central_can_open_trade"](off_signal)
    on_result = on_namespace["central_can_open_trade"](on_signal)

    assert off_result == expected
    assert on_result == expected
    assert on_signal == off_signal
    assert on_requests == off_requests
    assert len(off_requests) == len(on_requests) == 1
    assert off_broker.calls == on_broker.calls == []
    assert off_registry.calls == on_registry.calls == []
    assert [facts["shadow_stage"] for facts, _ in observed] == [
        SHADOW_STAGE_PRE_DECISION,
        SHADOW_STAGE_POST_DECISION,
    ]


@pytest.mark.parametrize("allowed", (True, False))
def test_mutating_shadow_observer_isolated_from_productive_verify_flow(allowed):
    observed = []

    def mutating_observer(facts):
        if facts["shadow_stage"] == SHADOW_STAGE_PRE_DECISION:
            facts["signal"]["side"] = "SHORT"
            facts["signal"]["symbol"] = "MUTATED"
            facts["signal"]["risk_pct"] = 999
            facts["signal"]["decision_request_id"] = "MUTATED"
        else:
            facts["decision"]["allowed"] = False
            facts["decision"]["decision"] = "DENY"
            facts["decision"]["risk_pct"] = 999
            facts["decision"]["decision_id"] = "MUTATED"
            facts["paired_pre"]["observer_snapshot"]["signal"]["side"] = (
                "POST_MUTATED"
            )
        observed.append(facts)
        return {"observer_snapshot": facts}

    baseline = _run_flow(shadow_enabled=False, allowed=allowed)
    isolated = _run_flow(
        shadow_enabled=True,
        observer=mutating_observer,
        allowed=allowed,
    )
    by_stage = {facts["shadow_stage"]: facts for facts in observed}
    productive_decision = isolated["result"][1]

    assert isolated["result"] == baseline["result"]
    assert isolated["result"][0] is allowed
    assert productive_decision["allowed"] is allowed
    assert productive_decision["decision"] == ("ALLOW" if allowed else "DENY")
    assert productive_decision["decision_id"] == "FALCON-DECISION-V2.7A.2:decision-a"
    assert productive_decision["risk_pct"] == 1.0
    assert isolated["signal_after"] == baseline["signal_after"]
    assert isolated["signal_after"]["side"] == "LONG"
    assert isolated["signal_after"]["symbol"] == "BTCUSDT"
    assert isolated["signal_after"]["risk_pct"] == 1.0
    assert isolated["signal_after"]["decision_request_id"] == (
        "FALCON-DECISION-REQUEST-V2.7A.2:request-a"
    )
    assert isolated["signal_after"]["real_notional_usdt"] == 5.0
    assert isolated["signal_after"]["partial_capable_sizing"]["notional_usdt"] == 5.0
    assert isolated["request_calls"] == baseline["request_calls"]
    assert len(isolated["request_calls"]) == 1
    assert isolated["broker"].calls == baseline["broker"].calls
    assert isolated["registry"].calls == baseline["registry"].calls == []

    assert by_stage[SHADOW_STAGE_PRE_DECISION]["signal"] is not isolated["signal_after"]
    assert by_stage[SHADOW_STAGE_POST_DECISION]["signal"] is not isolated["signal_after"]
    assert by_stage[SHADOW_STAGE_POST_DECISION]["decision"] is not productive_decision
    assert (
        by_stage[SHADOW_STAGE_POST_DECISION]["paired_pre"]["observer_snapshot"][
            "signal"
        ]
        is not isolated["signal_after"]
    )
    assert by_stage[SHADOW_STAGE_PRE_DECISION]["signal"]["side"] == "SHORT"
    assert by_stage[SHADOW_STAGE_PRE_DECISION]["signal"]["symbol"] == "MUTATED"
    assert by_stage[SHADOW_STAGE_PRE_DECISION]["signal"]["risk_pct"] == 999
    assert (
        by_stage[SHADOW_STAGE_PRE_DECISION]["signal"]["decision_request_id"]
        == "MUTATED"
    )
    assert (
        by_stage[SHADOW_STAGE_POST_DECISION]["paired_pre"]["observer_snapshot"][
            "signal"
        ]["side"]
        == "POST_MUTATED"
    )
    assert by_stage[SHADOW_STAGE_POST_DECISION]["decision"]["allowed"] is False
    assert by_stage[SHADOW_STAGE_POST_DECISION]["decision"]["decision"] == "DENY"
    assert by_stage[SHADOW_STAGE_POST_DECISION]["decision"]["risk_pct"] == 999
    assert by_stage[SHADOW_STAGE_POST_DECISION]["decision"]["decision_id"] == "MUTATED"


@pytest.mark.parametrize("allowed", (True, False))
def test_verify_shadow_off_on_preserves_v1_decision_risk_size_and_requests(allowed):
    observed = []
    off = _run_flow(shadow_enabled=False, allowed=allowed)
    on = _run_flow(
        shadow_enabled=True,
        observer=_adapter_observer(observed),
        allowed=allowed,
    )

    assert on["result"] == off["result"]
    assert on["signal_after"] == off["signal_after"]
    assert on["request_calls"] == off["request_calls"]
    assert on["broker"].calls == off["broker"].calls
    assert on["registry"].calls == off["registry"].calls == []
    assert on["result"][0] is allowed
    assert on["result"][1]["risk_pct"] == 1.0
    assert on["signal_after"]["real_notional_usdt"] == 5.0
    assert on["signal_after"]["partial_capable_sizing"]["notional_usdt"] == 5.0
    assert [facts["shadow_stage"] for facts, _ in observed] == [
        SHADOW_STAGE_PRE_DECISION,
        SHADOW_STAGE_POST_DECISION,
    ]
    assert all(diagnostic.status == OBSERVED for _, diagnostic in observed)
    assert all("execution_id" not in facts for facts, _ in observed)
    assert all("lifecycle_id" not in facts for facts, _ in observed)


def test_verify_shadow_broker_parity_has_no_mutable_or_shadow_attributable_call():
    observed = []
    off = _run_flow(shadow_enabled=False)
    on = _run_flow(shadow_enabled=True, observer=_adapter_observer(observed))

    assert off["broker"].calls == on["broker"].calls == [
        (
            "ensure_partial_capable_notional",
            {
                "symbol": "BTCUSDT",
                "planned_notional_usdt": 5.0,
                "max_notional_usdt": 20.0,
                "min_parts": 2,
            },
        ),
        ("ready_check", {}),
    ]
    assert [name for name, _ in on["broker"].calls if name not in {
        "ensure_partial_capable_notional", "ready_check"
    }] == []
    assert len(off["request_calls"]) == len(on["request_calls"]) == 1
    assert observed


def test_verify_shadow_observer_failure_isolated_from_exact_v1_result():
    baseline = _run_flow(shadow_enabled=False)
    namespace, broker, registry, request_calls = _load_verify_flow(
        shadow_enabled=True,
        observer=None,
    )
    expected_error = namespace["FalconV2VerifyShadowObservationError"]

    def expected_failure(facts):
        del facts
        raise expected_error("synthetic shadow projection failure")

    namespace["FALCON_REGISTRY_V2_VERIFY_SHADOW_OBSERVER"] = expected_failure
    signal = _signal()
    result = namespace["execute_signal_if_allowed"](signal, positions={})

    assert result == baseline["result"]
    assert signal == baseline["signal_after"]
    assert broker.calls == baseline["broker"].calls
    assert request_calls == baseline["request_calls"]
    assert registry.calls == []


@pytest.mark.parametrize("allowed", (True, False))
@pytest.mark.parametrize(
    "failing_stage", (SHADOW_STAGE_PRE_DECISION, SHADOW_STAGE_POST_DECISION)
)
def test_unexpected_shadow_observer_exception_isolated_from_verify_flow(
    allowed, failing_stage
):
    calls = []

    def unexpected_failure(facts):
        calls.append(facts["shadow_stage"])
        if facts["shadow_stage"] == failing_stage:
            raise RuntimeError("unexpected shadow observer failure")
        return {"shadow_stage": facts["shadow_stage"]}

    baseline = _run_flow(shadow_enabled=False, allowed=allowed)
    observed = _run_flow(
        shadow_enabled=True,
        observer=unexpected_failure,
        allowed=allowed,
    )
    decision = observed["result"][1]

    assert calls == [SHADOW_STAGE_PRE_DECISION, SHADOW_STAGE_POST_DECISION]
    assert observed["result"] == baseline["result"]
    assert observed["result"][0] is allowed
    assert decision["allowed"] is allowed
    assert decision["decision"] == ("ALLOW" if allowed else "DENY")
    assert decision["decision_id"] == "FALCON-DECISION-V2.7A.2:decision-a"
    assert decision["risk_pct"] == 1.0
    assert observed["signal_after"] == baseline["signal_after"]
    assert observed["signal_after"]["real_notional_usdt"] == 5.0
    assert observed["signal_after"]["partial_capable_sizing"]["notional_usdt"] == 5.0
    assert observed["request_calls"] == baseline["request_calls"]
    assert len(observed["request_calls"]) == 1
    assert observed["broker"].calls == baseline["broker"].calls
    assert observed["registry"].calls == baseline["registry"].calls == []


def test_observer_return_value_cannot_influence_allow_deny_or_execution_result():
    calls = []

    def irrelevant_observer(facts):
        calls.append(copy.deepcopy(facts))
        return object()

    baseline = _run_flow(shadow_enabled=False)
    observed = _run_flow(shadow_enabled=True, observer=irrelevant_observer)

    assert calls and [item["shadow_stage"] for item in calls] == [
        SHADOW_STAGE_PRE_DECISION,
        SHADOW_STAGE_POST_DECISION,
    ]
    assert observed["result"] == baseline["result"]
    assert observed["signal_after"] == baseline["signal_after"]
    assert observed["broker"].calls == baseline["broker"].calls
    assert observed["request_calls"] == baseline["request_calls"]


def test_productive_hook_preserves_raw_position_and_external_owner_facts():
    observed = []
    run = _run_flow(
        shadow_enabled=True,
        observer=_adapter_observer(observed),
        signal_updates={
            "positionSide": "BOTH",
            "position_side": "NET",
            "owner_type": "MANUAL_EXTERNAL",
        },
    )
    pre_diagnostic = observed[0][1]

    assert run["result"][0] is True
    assert pre_diagnostic.result.projection.position_side == "BOTH"
    assert pre_diagnostic.result.projection.raw_position_side == "NET"
    assert pre_diagnostic.result.projection.raw_position_side_conflict is True
    assert pre_diagnostic.result.projection.owner_type == "MANUAL_EXTERNAL"
    assert pre_diagnostic.result.projection.owner_status == "EXTERNAL_PRESERVED"


def test_productive_source_has_two_additive_observation_calls_at_the_factual_seam():
    tree = ast.parse(FALCON_SOURCE.read_text(encoding="utf-8"), filename=str(FALCON_SOURCE))
    central = _definition(tree, "central_can_open_trade", ast.FunctionDef)
    observer_calls = [
        node
        for node in ast.walk(central)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "shadow_observer"
    ]
    observer_lookups = [
        node
        for node in ast.walk(central)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Call)
        and isinstance(node.func.value.func, ast.Name)
        and node.func.value.func.id == "globals"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "_falcon_observe_v2_verify_shadow"
    ]
    request_calls = [
        node
        for node in ast.walk(central)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "requests"
        and node.func.attr == "post"
    ]

    assert len(observer_calls) == 2
    assert len(observer_lookups) == 1
    assert len(request_calls) == 1
    by_stage = {
        next(
            keyword.value.value
            for keyword in call.keywords
            if keyword.arg == "shadow_stage" and isinstance(keyword.value, ast.Constant)
        ): call
        for call in observer_calls
    }
    assert by_stage[SHADOW_STAGE_PRE_DECISION].lineno < request_calls[0].lineno
    assert by_stage[SHADOW_STAGE_POST_DECISION].lineno > request_calls[0].lineno

    uses = [
        node
        for node in ast.walk(central)
        if isinstance(node, ast.Name) and node.id == "shadow_pre_observation"
    ]
    assert sum(isinstance(node.ctx, ast.Store) for node in uses) == 1
    assert sum(isinstance(node.ctx, ast.Load) for node in uses) == 1


def test_productive_source_keeps_v28_dormant_without_import_or_auto_activation():
    source = FALCON_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(FALCON_SOURCE))
    helper = _definition(tree, "_falcon_observe_v2_verify_shadow", ast.FunctionDef)
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "FALCON_REGISTRY_V2_VERIFY_SHADOW_ENABLED"
            for target in node.targets
        )
    ]

    assert "falcon_registry_v2_verify_shadow" not in source
    assert len(assignments) == 1
    assert isinstance(assignments[0].value, ast.Constant)
    assert assignments[0].value.value is False
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"getenv", "start", "run", "submit"}
        for node in ast.walk(helper)
    )
    assert not any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in {"central_broker", "central_trade_registry"}
        for node in ast.walk(helper)
    )


def test_v28_files_do_not_own_decision_store_management_or_network_surfaces():
    forbidden_store_text = (
        "DecisionIdentityRecordStore",
        "set_decision_identity_record_store_for_tests",
        ".claim(",
        ".complete(",
    )
    for relative in (
        "falcon_registry_v2_verify_shadow.py",
        "falcon_registry_v2_verify_shadow_runtime_adapter.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(ROOT / relative))
        imported = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            (node.module or "").split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not imported.intersection({"broker", "requests", "redis", "trade_registry"})
        assert all(fragment not in source for fragment in forbidden_store_text)
