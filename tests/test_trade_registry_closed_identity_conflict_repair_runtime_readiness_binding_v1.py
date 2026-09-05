from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def binding_inputs() -> dict:
    return harness.build_synthetic_c3_runtime_readiness_binding_inputs_v1(ROOT)


def _reseal(inputs: dict) -> None:
    spec = inputs["readiness_binding_spec"]
    spec["spec_sha256"] = contract.readiness_binding_spec_sha256_v1(spec)


def test_valid_binding_policy_still_denies_runtime_and_live(binding_inputs: dict) -> None:
    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(
        **copy.deepcopy(binding_inputs)
    )

    assert result["ok"] is True
    assert result["binding_contract_verified"] is True
    assert result["upstream_activation_contract_verified"] is True
    assert result["source_hashes_verified"] is True
    assert result["runtime_readiness_policy_verified"] is True
    assert result["live_preflight_policy_verified"] is True
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["runtime_patch_allowed"] is False
    assert result["runtime_install_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True


def test_exact_readiness_vector_contains_all_critical_guards() -> None:
    assert contract.canonical_c3_runtime_readiness_vector_v1() == {
        "enabled": True,
        "coordination_ready": True,
        "runtime_activation_allowed": True,
        "registered_writer_count": 19,
        "all_writers_registered": True,
        "inflight_mutations": 0,
        "shared_lock_backend_ready": True,
        "maintenance_lease_store_ready": True,
        "registry_interlock_ready": True,
        "activation_receipt_verified": True,
        "source_hashes_verified": True,
        "rollback_ready": True,
        "kill_switch_ready": True,
    }


def test_receipt_binds_sources_vector_predicates_and_upstream(binding_inputs: dict) -> None:
    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(
        **copy.deepcopy(binding_inputs)
    )
    receipt = result["binding_receipt"]

    assert receipt["source_attestation_count"] == 4
    assert receipt["required_predicate_count"] == 13
    assert receipt["writer_count"] == 19
    assert len(receipt["upstream_proposal_receipt_sha256"]) == 64
    assert len(receipt["source_attestations_sha256"]) == 64
    assert len(receipt["required_runtime_readiness_vector_sha256"]) == 64
    assert len(receipt["live_preflight_predicates_sha256"]) == 64
    assert len(receipt["binding_receipt_sha256"]) == 64
    assert receipt["source_hashes_must_be_rechecked_after_patch"] is True
    assert receipt["runtime_binding_satisfied"] is False
    assert receipt["activation_allowed"] is False
    assert receipt["production_blockers"]


def test_harness_is_deterministic_read_only_and_non_activating() -> None:
    result = harness.run_synthetic_c3_runtime_readiness_binding_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["deterministic"] is True
    assert result["offline_only"] is True
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", False),
        ("coordination_ready", False),
        ("runtime_activation_allowed", False),
        ("registered_writer_count", 18),
        ("all_writers_registered", False),
        ("inflight_mutations", 1),
        ("shared_lock_backend_ready", False),
        ("maintenance_lease_store_ready", False),
        ("registry_interlock_ready", False),
        ("activation_receipt_verified", False),
        ("source_hashes_verified", False),
        ("rollback_ready", False),
        ("kill_switch_ready", False),
    ],
)
def test_any_weakened_readiness_guard_fails_closed(
    binding_inputs: dict, field: str, value: object
) -> None:
    inputs = copy.deepcopy(binding_inputs)
    vector = inputs["readiness_binding_spec"]["required_runtime_readiness_vector"]
    vector[field] = value
    inputs["readiness_binding_spec"]["required_runtime_readiness_vector_sha256"] = (
        contract._stable_sha256(vector)
    )
    _reseal(inputs)

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_RUNTIME_VECTOR_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False


def test_missing_preflight_predicate_fails_closed(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    predicates = inputs["readiness_binding_spec"]["live_preflight_predicates"]
    predicates.pop()
    inputs["readiness_binding_spec"]["live_preflight_predicates_sha256"] = (
        contract._stable_sha256(predicates)
    )
    _reseal(inputs)

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_LIVE_PREDICATES_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False


@pytest.mark.parametrize(
    "field",
    [
        "require_all_predicates",
        "missing_field_blocks",
        "unknown_field_blocks",
        "generic_ok_is_insufficient",
        "exact_boolean_identity_required",
        "activation_receipt_sha256_required",
        "source_attestation_sha256_required",
        "static_preflight_must_prove_predicate_semantics",
        "runtime_status_must_be_sampled_at_decision_time",
        "cached_readiness_forbidden",
    ],
)
def test_any_weakened_consumer_policy_fails_closed(
    binding_inputs: dict, field: str
) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["readiness_binding_spec"]["consumer_policy"][field] = False
    _reseal(inputs)

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_CONSUMER_POLICY_INVALID" in result["reasons"]
    assert result["runtime_binding_satisfied"] is False


def test_source_hash_drift_fails_closed_even_when_resealed(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    attestations = inputs["readiness_binding_spec"]["source_attestations"]
    attestations[0]["sha256"] = "f" * 64
    inputs["readiness_binding_spec"]["source_attestations_sha256"] = (
        contract._stable_sha256(attestations)
    )
    _reseal(inputs)

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_SOURCE_ATTESTATIONS_INVALID" in result["reasons"]
    assert result["source_hashes_verified"] is False


def test_tampered_upstream_activation_receipt_fails_closed(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["controlled_activation_result"]["proposal_receipt"]["writer_count"] = 18

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_UPSTREAM_ACTIVATION_RECEIPT_INVALID" in result["reasons"]
    assert result["binding_receipt"] is None


@pytest.mark.parametrize(
    "field",
    [
        "runtime_patch_authorized",
        "production_activation_authorized",
        "live_authorized",
        "order_submission_authorized",
    ],
)
def test_any_real_authorization_claim_fails_closed(
    binding_inputs: dict, field: str
) -> None:
    inputs = copy.deepcopy(binding_inputs)
    inputs["readiness_binding_spec"]["safety_envelope"][field] = True
    _reseal(inputs)

    result = contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert result["ok"] is False
    assert "READINESS_BINDING_SAFETY_ENVELOPE_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False


def test_validation_preserves_inputs(binding_inputs: dict) -> None:
    inputs = copy.deepcopy(binding_inputs)
    before = copy.deepcopy(inputs)

    contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(**inputs)

    assert inputs == before


def test_modules_have_no_runtime_activation_or_external_surface() -> None:
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
