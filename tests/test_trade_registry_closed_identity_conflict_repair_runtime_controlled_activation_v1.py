from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def activation_inputs() -> dict:
    return harness.build_synthetic_c3_controlled_activation_inputs_v1(ROOT)


def _reseal(inputs: dict) -> None:
    proposal = inputs["activation_proposal"]
    proposal["proposal_sha256"] = contract.controlled_activation_proposal_sha256_v1(
        proposal
    )


def test_valid_offline_proposal_remains_default_off(activation_inputs: dict) -> None:
    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **copy.deepcopy(activation_inputs)
    )

    assert result["ok"] is True
    assert result["proposal_contract_verified"] is True
    assert result["upstream_patch_plan_verified"] is True
    assert result["writer_inventory_verified"] is True
    assert result["safety_controls_verified"] is True
    assert result["dormant_seam_verified"] is True
    assert result["production_ready"] is False
    assert result["activation_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["live_allowed"] is False
    assert result["activation_callable_present"] is False
    assert result["activation_token"] is None
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_receipt_binds_exact_19_writers_and_keeps_production_blockers(
    activation_inputs: dict,
) -> None:
    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **copy.deepcopy(activation_inputs)
    )
    receipt = result["proposal_receipt"]

    assert receipt["writer_count"] == 19
    assert len(receipt["writer_inventory_sha256"]) == 64
    assert len(receipt["proposal_receipt_sha256"]) == 64
    assert receipt["source_hashes_must_be_rechecked"] is True
    assert receipt["activation_allowed"] is False
    assert receipt["runtime_patch_allowed"] is False
    assert receipt["production_blockers"]


def test_harness_is_deterministic_in_memory_and_non_activating() -> None:
    result = harness.run_synthetic_c3_controlled_activation_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["deterministic"] is True
    assert result["offline_only"] is True
    assert result["synthetic_only"] is True
    assert result["activation_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("activation_requested",), True, "CONTROLLED_ACTIVATION_PROPOSAL_ENVELOPE_UNSAFE"),
        (("activation_callable_present",), True, "CONTROLLED_ACTIVATION_PROPOSAL_ENVELOPE_UNSAFE"),
        (("safety_controls", "enable_real_trading"), True, "CONTROLLED_ACTIVATION_TRADING_CONTROLS_UNSAFE"),
        (("safety_controls", "broker_dry_run"), False, "CONTROLLED_ACTIVATION_TRADING_CONTROLS_UNSAFE"),
        (("safety_controls", "falcon_mode"), "LIVE", "CONTROLLED_ACTIVATION_TRADING_CONTROLS_UNSAFE"),
        (("safety_controls", "auto_deploy_enabled"), True, "CONTROLLED_ACTIVATION_TRADING_CONTROLS_UNSAFE"),
        (("authorization", "production_activation_authorized"), True, "CONTROLLED_ACTIVATION_AUTHORIZATION_SCOPE_INVALID"),
    ],
)
def test_any_activation_or_live_claim_fails_closed(
    activation_inputs: dict,
    path: tuple[str, ...],
    value: object,
    reason: str,
) -> None:
    inputs = copy.deepcopy(activation_inputs)
    target = inputs["activation_proposal"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    _reseal(inputs)

    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )

    assert result["ok"] is False
    assert result["activation_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["live_allowed"] is False
    assert reason in result["reasons"]


def test_missing_writer_fails_closed_even_when_resealed(activation_inputs: dict) -> None:
    inputs = copy.deepcopy(activation_inputs)
    proposal = inputs["activation_proposal"]
    proposal["writer_inventory"].pop()
    proposal["writer_inventory_sha256"] = contract._stable_sha256(
        proposal["writer_inventory"]
    )
    _reseal(inputs)

    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )

    assert result["ok"] is False
    assert "CONTROLLED_ACTIVATION_WRITER_INVENTORY_NOT_EXACT" in result["reasons"]
    assert result["activation_allowed"] is False


def test_enabled_dormant_seam_claim_fails_closed(activation_inputs: dict) -> None:
    inputs = copy.deepcopy(activation_inputs)
    inputs["activation_proposal"]["dormant_seam_evidence"]["enabled"] = True
    _reseal(inputs)

    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )

    assert result["ok"] is False
    assert "CONTROLLED_ACTIVATION_DORMANT_SEAM_INVALID" in result["reasons"]
    assert result["runtime_install_allowed"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_duration_seconds", 0),
        ("max_duration_seconds", 301),
        ("rollback_deadline_seconds", 121),
        ("max_inflight_mutations_before_activation", 1),
    ],
)
def test_unbounded_or_busy_window_fails_closed(
    activation_inputs: dict, field: str, value: object
) -> None:
    inputs = copy.deepcopy(activation_inputs)
    inputs["activation_proposal"]["activation_window"][field] = value
    _reseal(inputs)

    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )

    assert result["ok"] is False
    assert "CONTROLLED_ACTIVATION_WINDOW_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False


def test_tampered_upstream_receipt_breaks_chain(activation_inputs: dict) -> None:
    inputs = copy.deepcopy(activation_inputs)
    inputs["upstream_patch_plan_result"]["patch_plan_receipt"][
        "writer_operation_count"
    ] = 18

    result = contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )

    assert result["ok"] is False
    assert "CONTROLLED_ACTIVATION_UPSTREAM_PATCH_PLAN_INVALID" in result["reasons"]
    assert result["proposal_receipt"] is None


def test_validation_preserves_inputs(activation_inputs: dict) -> None:
    inputs = copy.deepcopy(activation_inputs)
    before = copy.deepcopy(inputs)

    contract.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(**inputs)

    assert inputs == before


def test_modules_expose_no_runtime_activation_or_external_surface() -> None:
    modules = (contract, harness)
    imported_modules = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported_modules
    assert "trade_registry" not in imported_modules
    assert "broker" not in imported_modules
    source = "\n".join(inspect.getsource(module) for module in modules)
    for token in (
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "importlib",
        "os.environ",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(contract, "activate")
    assert not hasattr(contract, "apply")
    assert not hasattr(harness, "activate")
    assert not hasattr(harness, "apply")
