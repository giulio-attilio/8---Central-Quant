from __future__ import annotations

import ast
import copy
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1 as adapter_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def adapter_inputs() -> dict:
    return harness.build_synthetic_c3_package_apply_request_adapter_inputs_v1(ROOT)


def _reseal_instance(inputs: dict) -> None:
    value = inputs["preview_instance_attestation"]
    value["attestation_sha256"] = (
        adapter_module.preview_instance_attestation_sha256_v1(value)
    )


def _reseal_intent(inputs: dict) -> None:
    value = inputs["apply_request_intent"]
    value["intent_sha256"] = adapter_module.apply_request_intent_sha256_v1(value)


def _adapter(
    *,
    now: int = harness._NOW,
    store: adapter_module.InMemoryProjectedApplyReservationStoreV1 | None = None,
) -> adapter_module.DormantPackageApplyRequestAdapterV1:
    return adapter_module.DormantPackageApplyRequestAdapterV1(
        config=adapter_module.DormantApplyRequestAdapterConfigV1(
            enabled=True,
            scope_attestation=adapter_module.OFFLINE_ADAPTER_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: now,
        reservation_store=(
            store
            if store is not None
            else adapter_module.InMemoryProjectedApplyReservationStoreV1()
        ),
    )


def test_default_adapter_fails_closed_and_does_not_project_request(
    adapter_inputs: dict,
) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    before = copy.deepcopy(inputs)

    result = adapter_module.DormantPackageApplyRequestAdapterV1().prepare(**inputs)

    assert result["ok"] is False
    assert result["status"] == "C3_PACKAGE_APPLY_REQUEST_ADAPTER_DEFAULT_OFF"
    assert result["protected_request"] is None
    assert result["reservation"] is None
    assert result["apply_invocation_allowed"] is False
    assert result["apply_allowed"] is False
    assert inputs == before


def test_valid_adapter_projects_protected_non_executable_request(
    adapter_inputs: dict,
) -> None:
    result = _adapter().prepare(**copy.deepcopy(adapter_inputs))

    assert result["ok"] is True
    assert result["adapter_contract_verified"] is True
    assert result["package_verified"] is True
    assert result["same_instance_preview_verified_synthetic"] is True
    assert result["same_runtime_instance_verified"] is False
    assert result["deadline_verified"] is True
    assert result["reservation_verified"] is True
    assert result["request_projected"] is True
    assert result["request_serialization_allowed"] is False
    assert result["apply_invocation_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    protected = result["protected_request"]
    assert repr(protected) == "ProtectedDormantApplyRequestV1(<protected>)"
    assert not hasattr(protected, "to_payload")
    assert not hasattr(protected, "serialize")
    assert not hasattr(protected, "send")
    assert not hasattr(protected, "apply")


def test_exact_projected_request_schema_is_hash_bound(adapter_inputs: dict) -> None:
    intent = adapter_inputs["apply_request_intent"]

    assert intent["request_payload_fields"] == ["ack", "preview_receipt_sha256"]
    assert len(intent["apply_ack_sha256"]) == 64
    assert intent["max_apply_count"] == 1
    assert intent["apply_invocation_requested"] is False
    assert intent["serialization_allowed"] is False
    assert intent["runtime_adapter_bound"] is False
    assert len(intent["intent_sha256"]) == 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pending_preview_present", False),
        ("pending_preview_same_instance", False),
        ("controller_apply_enabled", True),
        ("apply_scope_attested", True),
        ("real_controller_referenced", True),
        ("preview_receipt_sha256", "f" * 64),
    ],
)
def test_any_weakened_same_instance_attestation_fails_closed(
    adapter_inputs: dict, field: str, value: object
) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    inputs["preview_instance_attestation"][field] = value
    _reseal_instance(inputs)

    result = _adapter().prepare(**inputs)

    assert result["ok"] is False
    assert "APPLY_ADAPTER_PREVIEW_INSTANCE_ATTESTATION_INVALID" in result["reasons"]
    assert result["protected_request"] is None
    assert result["apply_invocation_allowed"] is False


def test_replaced_synthetic_instance_breaks_intent_binding(
    adapter_inputs: dict,
) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    inputs["preview_instance_attestation"]["controller_instance_sha256"] = "f" * 64
    _reseal_instance(inputs)

    result = _adapter().prepare(**inputs)

    assert result["ok"] is False
    assert "APPLY_ADAPTER_REQUEST_INTENT_INVALID" in result["reasons"]
    assert result["same_runtime_instance_verified"] is False
    assert result["protected_request"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operation", "APPLY"),
        ("request_payload_fields", ["preview_receipt_sha256"]),
        ("max_apply_count", True),
        ("max_apply_count", 2),
        ("apply_invocation_requested", True),
        ("serialization_allowed", True),
        ("runtime_adapter_bound", True),
    ],
)
def test_any_executable_or_weakened_intent_fails_closed(
    adapter_inputs: dict, field: str, value: object
) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    inputs["apply_request_intent"][field] = value
    _reseal_intent(inputs)

    result = _adapter().prepare(**inputs)

    assert result["ok"] is False
    assert "APPLY_ADAPTER_REQUEST_INTENT_INVALID" in result["reasons"]
    assert result["protected_request"] is None
    assert result["apply_allowed"] is False


@pytest.mark.parametrize(
    "container",
    ["preview_instance_attestation", "apply_request_intent"],
)
def test_unknown_fields_fail_closed(adapter_inputs: dict, container: str) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    inputs[container]["unexpected_runtime_authority"] = True
    if container == "preview_instance_attestation":
        _reseal_instance(inputs)
    else:
        _reseal_intent(inputs)

    result = _adapter().prepare(**inputs)

    assert result["ok"] is False
    assert result["protected_request"] is None
    assert result["apply_invocation_allowed"] is False


def test_exact_expiry_is_rejected(adapter_inputs: dict) -> None:
    expiry = adapter_inputs["preview_instance_attestation"]["expires_at_epoch"]

    result = _adapter(now=expiry).prepare(**copy.deepcopy(adapter_inputs))

    assert result["ok"] is False
    assert "APPLY_ADAPTER_DEADLINE_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["protected_request"] is None


def test_package_reservation_is_terminal_after_abort(adapter_inputs: dict) -> None:
    store = adapter_module.InMemoryProjectedApplyReservationStoreV1()
    adapter = _adapter(store=store)

    first = adapter.prepare(**copy.deepcopy(adapter_inputs))
    assert first["ok"] is True
    assert store.abort_without_invocation(first["reservation"]) is True
    assert store.abort_without_invocation(first["reservation"]) is False

    replay = adapter.prepare(**copy.deepcopy(adapter_inputs))
    assert replay["ok"] is False
    assert "APPLY_ADAPTER_PACKAGE_ALREADY_RESERVED" in replay["reasons"]
    assert store.snapshot()["states"] == {"ABORTED_WITHOUT_INVOCATION": 1}


def test_concurrent_prepare_has_exactly_one_reservation(adapter_inputs: dict) -> None:
    store = adapter_module.InMemoryProjectedApplyReservationStoreV1()
    adapter = _adapter(store=store)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _index: adapter.prepare(**copy.deepcopy(adapter_inputs)),
                range(16),
            )
        )

    assert sum(result["ok"] is True for result in results) == 1
    assert sum(
        "APPLY_ADAPTER_PACKAGE_ALREADY_RESERVED" in result["reasons"]
        for result in results
    ) == 15
    assert store.snapshot()["reservation_count"] == 1


def test_tampered_package_receipt_fails_before_reservation(
    adapter_inputs: dict,
) -> None:
    inputs = copy.deepcopy(adapter_inputs)
    inputs["controlled_package_result"]["package_receipt"][
        "preview_receipt_sha256"
    ] = "f" * 64
    store = adapter_module.InMemoryProjectedApplyReservationStoreV1()

    result = _adapter(store=store).prepare(**inputs)

    assert result["ok"] is False
    assert "APPLY_ADAPTER_PACKAGE_INVALID" in result["reasons"]
    assert store.snapshot()["reservation_count"] == 0


def test_harness_aborts_without_invocation_and_denies_reuse() -> None:
    result = harness.run_synthetic_c3_package_apply_request_adapter_harness_v1(
        ROOT
    )

    assert result["ok"] is True
    assert result["protected_surface_safe"] is True
    assert result["reservation_aborted_without_invocation"] is True
    assert result["duplicate_denied_before_abort"] is True
    assert result["duplicate_denied_after_abort"] is True
    assert result["same_runtime_instance_verified"] is False
    assert result["request_serialization_allowed"] is False
    assert result["apply_invocation_allowed"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_adapter_modules_have_no_controller_or_external_surface() -> None:
    modules = (adapter_module, harness)
    source = "\n".join(inspect.getsource(module) for module in modules)
    imported = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported
    assert "trade_registry" not in imported
    assert "trade_registry_closed_identity_conflict_repair_runtime_operation_v1" not in imported
    assert "broker" not in imported
    for token in (
        "controller.apply(",
        ".to_payload(",
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "os.environ",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(adapter_module, "apply")
    assert not hasattr(adapter_module, "activate")
