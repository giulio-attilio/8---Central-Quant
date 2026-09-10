from __future__ import annotations

import ast
import copy
import inspect
import threading
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1 as gateway_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def gateway_inputs() -> dict:
    return harness.build_synthetic_dormant_invocation_gateway_inputs_v1(ROOT)


def _gateway(*, clock=None, store=None):
    return harness.build_synthetic_dormant_invocation_gateway_v1(
        clock=clock,
        lease_store=(
            store
            if store is not None
            else gateway_module.InMemoryDormantInvocationLeaseStoreV1()
        ),
    )


def _reseal_intent(inputs: dict) -> None:
    intent = inputs["invocation_intent"]
    intent["intent_sha256"] = gateway_module.dormant_invocation_intent_sha256_v1(
        intent
    )


def _reseal_authorization(inputs: dict) -> None:
    receipt = inputs["authorization_result"]["authorization_receipt"]
    receipt["authorization_receipt_sha256"] = gateway_module._receipt_sha256(
        receipt, "authorization_receipt_sha256"
    )


def test_valid_chain_projects_only_a_protected_non_executable_envelope(
    gateway_inputs: dict,
) -> None:
    result = _gateway().prepare(**copy.deepcopy(gateway_inputs))

    assert result["ok"] is True
    assert result["gateway_contract_verified"] is True
    assert result["static_conformance_verified"] is True
    assert result["adapter_verified"] is True
    assert result["authorization_verified_synthetic"] is True
    assert result["same_instance_preview_verified_synthetic"] is True
    assert result["same_runtime_instance_verified"] is False
    assert result["strict_deadline_verified"] is True
    assert result["http_envelope_projected"] is True
    assert result["lease_verified"] is True
    assert result["request_material_exposed"] is False
    assert result["serialization_allowed"] is False
    assert result["controller_invocation_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True

    envelope = result["protected_envelope"]
    assert type(envelope) is gateway_module.ProtectedDormantInvocationEnvelopeV1
    assert repr(envelope) == "ProtectedDormantInvocationEnvelopeV1(<protected>)"
    assert envelope.operation == "apply"
    assert envelope.ack == "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
    for method_name in ("serialize", "to_payload", "send", "apply", "invoke"):
        assert not hasattr(envelope, method_name)


def test_gateway_harness_proves_replay_and_abort_are_terminal() -> None:
    result = harness.run_synthetic_dormant_invocation_gateway_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["protected_surface_safe"] is True
    assert result["same_instance_preview_verified_synthetic"] is True
    assert result["same_runtime_instance_verified"] is False
    assert result["duplicate_denied"] is True
    assert result["abort_terminal"] is True
    assert result["controller_invocation_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["apply_allowed"] is False
    assert result["lease_store_snapshot"] == {
        "lease_count": 1,
        "states": {"ABORTED_WITHOUT_INVOCATION": 1},
        "durable": False,
        "raw_envelope_stored": False,
        "synthetic_only": True,
    }


def test_equivalent_but_distinct_controller_instance_fails_closed(
    gateway_inputs: dict,
) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    owner = inputs["preview_owner_instance"]
    inputs["invocation_target_instance"] = (
        gateway_module.SyntheticDormantControllerInstanceV1(
            controller_instance_sha256=owner.controller_instance_sha256,
            pending_preview_receipt_sha256=owner.pending_preview_receipt_sha256,
            expires_at_epoch=owner.expires_at_epoch,
        )
    )

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_SAME_SYNTHETIC_INSTANCE_REQUIRED" in result["reasons"]
    assert result["same_runtime_instance_verified"] is False
    assert result["protected_envelope"] is None
    assert result["controller_invocation_allowed"] is False


def test_preview_must_exist_on_the_exact_bound_instance(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    owner = inputs["preview_owner_instance"]
    wrong = gateway_module.SyntheticDormantControllerInstanceV1(
        controller_instance_sha256=owner.controller_instance_sha256,
        pending_preview_receipt_sha256="f" * 64,
        expires_at_epoch=owner.expires_at_epoch,
    )
    inputs["preview_owner_instance"] = wrong
    inputs["invocation_target_instance"] = wrong

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_SAME_SYNTHETIC_INSTANCE_REQUIRED" in result["reasons"]
    assert result["apply_allowed"] is False


def test_authorization_tampering_fails_closed(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["authorization_result"]["authorization_receipt"]["max_apply_count"] = 2

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_SYNTHETIC_AUTHORIZATION_INVALID" in result["reasons"]
    assert result["protected_envelope"] is None
    assert result["apply_allowed"] is False


def test_resealed_but_cross_bound_authorization_fails_closed(
    gateway_inputs: dict,
) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["authorization_result"]["authorization_receipt"][
        "preview_receipt_sha256"
    ] = "e" * 64
    _reseal_authorization(inputs)

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_SYNTHETIC_AUTHORIZATION_INVALID" in result["reasons"]
    assert result["controller_invocation_allowed"] is False


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("operation", "preview"),
        ("envelope_fields", ["ack", "preview_receipt_sha256"]),
        ("max_invocation_count", 2),
        ("serialization_requested", True),
        ("controller_call_requested", True),
        ("runtime_binding_requested", True),
    ],
)
def test_any_invocation_or_envelope_intent_drift_fails_closed(
    gateway_inputs: dict, field_name: str, value: object
) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["invocation_intent"][field_name] = value
    _reseal_intent(inputs)

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_INVOCATION_INTENT_INVALID" in result["reasons"]
    assert result["protected_envelope"] is None
    assert result["serialization_allowed"] is False
    assert result["controller_invocation_allowed"] is False


def test_unknown_intent_field_fails_closed(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["invocation_intent"]["runtime_authority"] = True
    _reseal_intent(inputs)

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_INVOCATION_INTENT_INVALID" in result["reasons"]
    assert result["apply_allowed"] is False


def test_exact_expiry_is_rejected(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    expiry = inputs["preview_owner_instance"].expires_at_epoch

    result = _gateway(clock=lambda: expiry).prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_DEADLINE_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["strict_deadline_verified"] is False
    assert result["protected_envelope"] is None


@pytest.mark.parametrize("clock", [None, lambda: True, lambda: "now"])
def test_missing_or_invalid_clock_fails_closed(gateway_inputs: dict, clock) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    gateway = gateway_module.DormantInvocationGatewayV1(
        config=gateway_module.DormantInvocationGatewayConfigV1(
            enabled=True,
            scope_attestation=gateway_module.OFFLINE_INVOCATION_GATEWAY_SCOPE_ATTESTATION_V1,
        ),
        clock=clock,
        lease_store=gateway_module.InMemoryDormantInvocationLeaseStoreV1(),
    )

    result = gateway.prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_CLOCK_UNAVAILABLE" in result["reasons"]
    assert result["controller_invocation_allowed"] is False


def test_same_gateway_binding_can_be_reserved_only_once(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    gateway = _gateway()

    first = gateway.prepare(**inputs)
    duplicate = gateway.prepare(**inputs)

    assert first["ok"] is True
    assert duplicate["ok"] is False
    assert "GATEWAY_REPLAY_OR_DUPLICATE_DETECTED" in duplicate["reasons"]
    assert duplicate["protected_envelope"] is None


def test_concurrent_reservation_has_exactly_one_winner(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    gateway = _gateway()
    barrier = threading.Barrier(8)
    results: list[dict] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        result = gateway.prepare(**inputs)
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert sum(result["ok"] is True for result in results) == 1
    assert sum(
        "GATEWAY_REPLAY_OR_DUPLICATE_DETECTED" in result["reasons"]
        for result in results
    ) == 7


def test_static_conformance_drift_blocks_gateway(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["static_conformance_result"]["drift_detected"] = True

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_STATIC_CONFORMANCE_INVALID_OR_DRIFTED" in result["reasons"]
    assert result["static_conformance_verified"] is False
    assert result["apply_allowed"] is False


def test_adapter_claiming_runtime_authority_is_rejected(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    inputs["adapter_result"]["runtime_binding_satisfied"] = True

    result = _gateway().prepare(**inputs)

    assert result["ok"] is False
    assert "GATEWAY_DORMANT_ADAPTER_INVALID" in result["reasons"]
    assert result["controller_invocation_allowed"] is False


def test_default_off_scope_and_mapping_guards(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    default_result = gateway_module.DormantInvocationGatewayV1().prepare(**inputs)
    wrong_scope = gateway_module.DormantInvocationGatewayV1(
        config=gateway_module.DormantInvocationGatewayConfigV1(
            enabled=True, scope_attestation="wrong"
        )
    ).prepare(**inputs)
    bad_mapping_inputs = copy.deepcopy(inputs)
    bad_mapping_inputs["invocation_intent"] = None
    bad_mapping = _gateway().prepare(**bad_mapping_inputs)

    assert default_result["status"] == "C3_DORMANT_INVOCATION_GATEWAY_DEFAULT_OFF"
    assert wrong_scope["status"] == "C3_DORMANT_INVOCATION_GATEWAY_SCOPE_REQUIRED"
    assert bad_mapping["reasons"] == ["GATEWAY_MAPPING_INPUTS_REQUIRED"]
    for result in (default_result, wrong_scope, bad_mapping):
        assert result["ok"] is False
        assert result["protected_envelope"] is None
        assert result["controller_invocation_allowed"] is False
        assert result["apply_allowed"] is False


def test_gateway_does_not_mutate_inputs(gateway_inputs: dict) -> None:
    inputs = copy.deepcopy(gateway_inputs)
    before = copy.deepcopy(inputs)

    result = _gateway().prepare(**inputs)

    assert result["ok"] is True
    assert inputs == before


def test_receipt_binds_all_upstreams_without_exposing_request_material(
    gateway_inputs: dict,
) -> None:
    result = _gateway().prepare(**copy.deepcopy(gateway_inputs))
    receipt = result["gateway_receipt"]
    supplied = receipt["gateway_receipt_sha256"]

    assert supplied == gateway_module._receipt_sha256(
        receipt, "gateway_receipt_sha256"
    )
    assert receipt["envelope_fields"] == [
        "operation",
        "ack",
        "preview_receipt_sha256",
    ]
    assert receipt["request_material_exposed"] is False
    assert receipt["serialization_allowed"] is False
    assert receipt["controller_invocation_allowed"] is False
    assert receipt["runtime_binding_satisfied"] is False
    assert receipt["production_ready"] is False
    assert receipt["apply_allowed"] is False


def test_gateway_modules_have_no_runtime_or_external_surface() -> None:
    modules = (gateway_module, harness)
    trees = [ast.parse(inspect.getsource(module)) for module in modules]
    imported = {
        alias.name
        for tree in trees
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    source = "\n".join(inspect.getsource(module) for module in modules)

    assert "main" not in imported
    assert "trade_registry_closed_identity_conflict_repair_runtime_operation_v1" not in imported
    runtime_module_name = (
        "trade_registry_closed_identity_conflict_repair_runtime_operation_v1"
    )
    assert all(
        getattr(value, "__name__", None) != runtime_module_name
        for module in modules
        for value in vars(module).values()
    )
    for token in (
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "os.environ",
        "controller.apply(",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(gateway_module, "apply")
    assert not hasattr(gateway_module, "invoke")
    assert not hasattr(gateway_module, "activate")
    assert not hasattr(gateway_module, "serialize")
