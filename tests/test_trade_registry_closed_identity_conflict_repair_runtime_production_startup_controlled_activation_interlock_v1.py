from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_controlled_activation_interlock_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_controlled_activation_interlock_harness_v1 as harness


def test_interlock_prepares_sealed_offline_receipt_without_applying_anything():
    result = harness.run_offline_startup_controlled_activation_interlock_v1()
    assert result["ok"] is True
    assert result["status"].endswith("HARNESS_VERIFIED")
    receipt = result["receipt"]
    assert receipt["exact_binding_verified"] is True
    assert receipt["five_source_adapters_verified"] is True
    assert receipt["same_callback_gate_verified"] is True
    assert len(receipt["request_sha256"]) == 64
    assert len(receipt["receipt_sha256"]) == 64


def test_interlock_never_enables_gate_runtime_live_or_orders():
    result = harness.run_offline_startup_controlled_activation_interlock_v1()
    receipt = result["receipt"]
    assert receipt["apply_allowed"] is False
    assert receipt["gate_enable_allowed"] is False
    assert receipt["runtime_start_allowed"] is False
    assert receipt["live_allowed"] is False
    assert receipt["order_submission_authorized"] is False
    assert result["binding_snapshot"]["gate_default_off"] is True
    assert result["binding_snapshot"]["composition_default_off"] is True


def test_preparation_does_not_invoke_any_bound_runtime_provider():
    result = harness.run_offline_startup_controlled_activation_interlock_v1()
    assert all(count == 0 for count in result["provider_calls"].values())
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


def test_interlock_exposes_no_apply_enable_or_activate_method():
    interlock, _, _, _, _ = (
        harness.build_offline_startup_controlled_activation_interlock_v1()
    )
    for name in ("apply", "activate", "enable_gate", "start_runtime", "go_live"):
        assert not hasattr(interlock, name)


def test_interlock_is_default_off_without_explicit_scope():
    interlock, _, _, source, upstream = (
        harness.build_offline_startup_controlled_activation_interlock_v1(
            fail_phase="interlock_default_off"
        )
    )
    assert interlock.snapshot()["default_off"] is True
    with pytest.raises(
        contract.RuntimeProductionStartupControlledActivationInterlockBlocked,
        match="DEFAULT_OFF",
    ):
        interlock.prepare_offline(upstream)
    assert all(count == 0 for count in source.calls.values())


@pytest.mark.parametrize(
    "phase",
    [
        "binding_identity_mismatch",
        "source_identity_mismatch",
        "source_cross_binding_mismatch",
        "callback_gate_mismatch",
        "source_adapter_default_off",
        "upstream_tampered",
    ],
)
def test_any_identity_cross_binding_source_or_upstream_failure_stays_closed(phase):
    result = harness.run_offline_startup_controlled_activation_interlock_v1(
        fail_phase=phase
    )
    assert result["ok"] is False
    assert result["status"].endswith("HARNESS_BLOCKED")
    assert all(count == 0 for count in result["provider_calls"].values())
    assert result["apply_allowed"] is False
    assert result["gate_enable_allowed"] is False
    assert result["runtime_start_allowed"] is False
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_preparation_replay_is_blocked_without_provider_calls():
    interlock, _, _, source, upstream = (
        harness.build_offline_startup_controlled_activation_interlock_v1()
    )
    assert interlock.prepare_offline(upstream)["ok"] is True
    with pytest.raises(
        contract.RuntimeProductionStartupControlledActivationInterlockBlocked,
        match="REPLAY_BLOCKED",
    ):
        interlock.prepare_offline(upstream)
    assert all(count == 0 for count in source.calls.values())


def test_interlock_repr_is_protected():
    interlock, _, _, _, _ = (
        harness.build_offline_startup_controlled_activation_interlock_v1()
    )
    assert repr(interlock) == (
        "<RuntimeProductionStartupControlledActivationInterlockContractV1 protected>"
    )


def test_cross_binding_uses_public_identity_contracts_only():
    source = inspect.getsource(
        contract.RuntimeProductionStartupControlledActivationInterlockContractV1._require_cross_binding
    )
    assert "self._binding._ports" not in source
    assert "adapter._source" not in source
    assert "adapter._gate" not in source
    assert "getattr(" not in source
    assert "source_identity_sha256_v1" in source
    assert "bound_source_identity_sha256_v1" in source
    assert "gate_identity_sha256_v1" in source
    assert "bound_gate_identity_sha256_v1" in source
    assert "upstream_contract._stable_sha256" not in inspect.getsource(contract)


def test_contract_has_no_main_runtime_seam_registry_or_external_surface():
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


def test_harness_has_no_secret_or_external_service_reference():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "trade_registry_closed_identity_conflict_repair_runtime_production_startup_controlled_activation_interlock_harness_v1.py"
    ).read_text(encoding="utf-8").lower()
    forbidden = (
        ".env",
        "central_data_dir",
        "bingx",
        "render.com",
        "execution_auth_token",
    )
    assert not any(value in source for value in forbidden)


def test_runtime_main_remains_unintegrated_with_activation_interlock():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "production_startup_controlled_activation_interlock_contract_v1" not in source
    assert "RuntimeProductionStartupControlledActivationInterlockContractV1" not in source
