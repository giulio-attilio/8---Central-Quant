from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_harness_v1 as harness


def test_direct_production_shaped_composition_rehearses_end_to_end_offline():
    result = harness.run_offline_production_startup_composition_v1()
    assert result["ok"] is True
    assert result["status"].endswith("HARNESS_VERIFIED")
    assert result["rehearsal"]["ok"] is True
    assert result["production_evidence_projected"] is False
    assert result["production_evidence_simulated"] is True
    assert result["simulated_runtime_started"] is True
    assert result["callback_calls"] == 1
    assert result["verifier_calls"] == 1


def test_composition_and_callback_never_grant_live_or_order_authority():
    result = harness.run_offline_production_startup_composition_v1()
    receipt = result["rehearsal"]["callback_receipt"]
    assert receipt["runtime_activation_allowed"] is False
    assert receipt["live_allowed"] is False
    assert receipt["order_submission_authorized"] is False
    assert receipt["no_order_sent"] is True
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False


def test_all_dependencies_are_bound_to_exact_process_local_instances():
    composition, _, gate = harness.build_offline_production_startup_composition_v1()
    snapshot = composition.snapshot()
    assert snapshot["ok"] is True
    assert snapshot["dependencies_instance_bound"] is True
    assert snapshot["same_atomic_lock"] is True
    assert getattr(composition, "_gate") is gate


def test_composition_is_default_off_and_fails_closed():
    composition, environment, _ = harness.build_offline_production_startup_composition_v1(
        composition_enabled=False
    )
    assert composition.snapshot()["default_off"] is True
    with pytest.raises(
        contract.RuntimeProductionStartupCompositionBlocked,
        match="DEFAULT_OFF",
    ):
        composition.rehearse_offline()
    assert environment.callback_calls == 0
    assert environment.simulated_runtime_started is False


@pytest.mark.parametrize(
    "phase",
    [
        "unsafe_trading",
        "writer_seen",
        "state_drift",
        "seam_incomplete",
        "seam_generation_mismatch",
        "maintenance_failed",
        "unresolved_transactions",
        "conflicts_remaining",
        "authority_rejected",
        "signature_invalid",
        "authority_revoked",
        "authority_stale",
        "authority_receipt_corrupt",
        "verifier_failed",
        "controls_provider_failed",
        "state_provider_failed",
        "seam_provider_failed",
        "maintenance_provider_failed",
        "dependency_pin_mismatch",
        "different_atomic_lock",
        "callback_failed",
        "callback_receipt_invalid",
    ],
)
def test_every_invalid_evidence_binding_or_callback_stays_closed(phase):
    result = harness.run_offline_production_startup_composition_v1(fail_phase=phase)
    assert result["ok"] is False
    assert result["status"].endswith("COMPOSITION_BLOCKED")
    assert result["simulated_runtime_started"] is False
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_second_invocation_is_blocked_after_one_successful_rehearsal():
    composition, environment, _ = harness.build_offline_production_startup_composition_v1()
    assert composition.rehearse_offline()["ok"] is True
    with pytest.raises(contract.RuntimeProductionStartupCompositionBlocked):
        composition.rehearse_offline()
    assert environment.callback_calls == 1


def test_protected_repr_does_not_expose_dependency_bindings():
    composition, _, _ = harness.build_offline_production_startup_composition_v1()
    value = repr(composition)
    assert value == "<RuntimeProductionStartupCompositionContractV1 protected>"
    assert "sha256" not in value.lower()


def test_contract_has_no_runtime_registry_filesystem_or_external_client_imports():
    source = inspect.getsource(contract).lower()
    forbidden = (
        "import main",
        "runtime_seam_v1",
        "central_trade_registry",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "open(",
    )
    assert not any(value in source for value in forbidden)


def test_harness_emits_final_dtos_directly_without_using_projection_helpers():
    source = inspect.getsource(harness).lower()
    assert "startup_admission_composition_harness_v1" not in source
    assert "build_production_shaped_startup_admission_request_v1" not in source
    assert "_project_production_shaped_gate_request" not in source


def test_harness_has_no_real_storage_secret_or_service_reference():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_harness_v1.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        ".env",
        "central_data_dir",
        "/data/trade_registry",
        "bingx",
        "render.com",
        "execution_auth_token",
    )
    assert not any(value in source for value in forbidden)


def test_runtime_main_remains_unintegrated_with_production_startup_composition():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "runtime_production_startup_composition_contract_v1" not in source
    assert "RuntimeProductionStartupCompositionContractV1" not in source
