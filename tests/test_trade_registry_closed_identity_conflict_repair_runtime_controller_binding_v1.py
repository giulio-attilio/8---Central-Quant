from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def binding_inputs() -> dict:
    return harness.build_synthetic_c3_repair_controller_binding_inputs_v1(ROOT)


def _reseal(inputs: dict) -> None:
    spec = inputs["controller_binding_spec"]
    spec["spec_sha256"] = contract.controller_binding_spec_sha256_v1(spec)


def test_valid_contract_allows_only_synthetic_dormant_binding(
    binding_inputs: dict,
) -> None:
    result = contract.evaluate_c3_repair_controller_binding_offline_v1(
        **copy.deepcopy(binding_inputs)
    )

    assert result["ok"] is True
    assert result["binding_contract_verified"] is True
    assert result["upstream_readiness_binding_verified"] is True
    assert result["binding_plan_verified"] is True
    assert result["default_off_config_verified"] is True
    assert result["synthetic_binding_allowed"] is True
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True


def test_binding_plan_is_exact_and_minimal() -> None:
    assert contract.canonical_c3_controller_binding_plan_v1() == [
        {
            "target": "controller.writer_coordination_status",
            "source": "runtime_seam.c3_closed_repair_writer_coordination_status_v1",
            "required": True,
        },
        {
            "target": "controller.maintenance_lease",
            "source": "dormant_coordinator.maintenance_lease",
            "required": True,
        },
        {
            "target": "controller.config",
            "source": "runtime_operation.ClosedIdentityRepairRuntimeConfigV1",
            "required": True,
        },
    ]


def test_harness_constructs_exact_binding_but_apply_stays_default_off() -> None:
    result = harness.run_synthetic_c3_repair_controller_binding_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["controller_constructed"] is True
    assert result["controller_apply_enabled"] is False
    assert result["coordination_binding_exact"] is True
    assert result["maintenance_binding_exact"] is True
    assert result["dependency_calls"] == {
        "registry_loader": 0,
        "conflict_auditor": 0,
        "registry_lock": 0,
        "trading_controls": 0,
    }
    assert result["controller_snapshot"]["writer_coordination_bound"] is True
    assert result["controller_snapshot"]["maintenance_lease_bound"] is True
    assert result["default_off_apply_result"]["status"] == "REPAIR_APPLY_DEFAULT_OFF"
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("controller_config", "apply_enabled"), True, "CONTROLLER_BINDING_CONFIG_NOT_DEFAULT_OFF"),
        (("controller_config", "apply_scope_attestation"), "x", "CONTROLLER_BINDING_CONFIG_NOT_DEFAULT_OFF"),
        (("authorization_state", "activation_requested"), True, "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED"),
        (("authorization_state", "activation_receipt"), {"sha256": "a" * 64}, "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED"),
        (("authorization_state", "production_authorization"), "claimed", "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED"),
        (("authorization_state", "production_dependencies_bound"), True, "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED"),
    ],
)
def test_any_activation_or_production_claim_fails_closed(
    binding_inputs: dict,
    path: tuple[str, str],
    value: object,
    reason: str,
) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["controller_binding_spec"][path[0]][path[1]] = value
    _reseal(inputs)

    result = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)

    assert result["ok"] is False
    assert reason in result["reasons"]
    assert result["synthetic_binding_allowed"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False


def test_missing_or_redirected_binding_fails_closed(binding_inputs: dict) -> None:
    for mutation in ("missing", "redirected"):
        inputs = copy.deepcopy(binding_inputs)
        plan = inputs["controller_binding_spec"]["binding_plan"]
        if mutation == "missing":
            plan.pop()
        else:
            plan[0]["source"] = "untrusted.status"
        inputs["controller_binding_spec"]["binding_plan_sha256"] = (
            contract._stable_sha256(plan)
        )
        _reseal(inputs)

        result = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)

        assert result["ok"] is False
        assert "CONTROLLER_BINDING_PLAN_INVALID" in result["reasons"]
        assert result["apply_allowed"] is False


@pytest.mark.parametrize(
    ("container", "reason"),
    [
        ("controller_config", "CONTROLLER_BINDING_CONFIG_NOT_DEFAULT_OFF"),
        (
            "authorization_state",
            "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED",
        ),
        ("safety_envelope", "CONTROLLER_BINDING_SAFETY_ENVELOPE_INVALID"),
    ],
)
def test_unknown_nested_field_fails_closed(
    binding_inputs: dict, container: str, reason: str
) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["controller_binding_spec"][container]["unexpected_authority"] = True
    _reseal(inputs)

    result = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)

    assert result["ok"] is False
    assert reason in result["reasons"]
    assert result["activation_allowed"] is False


def test_unknown_top_level_field_fails_closed(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["controller_binding_spec"]["unexpected_runtime_binding"] = True
    _reseal(inputs)

    result = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)

    assert result["ok"] is False
    assert "CONTROLLER_BINDING_SPEC_ENVELOPE_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False


def test_tampered_upstream_receipt_fails_closed(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["readiness_binding_result"]["binding_receipt"]["writer_count"] = 18

    result = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)

    assert result["ok"] is False
    assert "CONTROLLER_BINDING_UPSTREAM_READINESS_RECEIPT_INVALID" in result["reasons"]
    assert result["binding_receipt"] is None


def test_contract_has_no_runtime_or_external_surface() -> None:
    tree = ast.parse(inspect.getsource(contract))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imports
    assert "trade_registry" not in imports
    assert "broker" not in imports
    source = inspect.getsource(contract)
    for token in (
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
    assert not hasattr(contract, "activate")
    assert not hasattr(contract, "apply")
