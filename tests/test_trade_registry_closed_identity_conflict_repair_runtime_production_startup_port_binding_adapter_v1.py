from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_harness_v1 as harness


def test_adapter_binds_all_runtime_ports_without_invoking_them():
    result = harness.run_dormant_production_startup_port_binding_adapter_v1()
    assert result["ok"] is True
    assert result["status"].endswith("HARNESS_VERIFIED")
    assert all(count == 0 for count in result["provider_calls"].values())
    assert result["binding_snapshot"]["ports_instance_bound"] is True
    assert result["binding_snapshot"]["same_atomic_lock"] is True


def test_bound_gate_and_composition_remain_default_off():
    result = harness.run_dormant_production_startup_port_binding_adapter_v1()
    assert result["gate_snapshot"]["default_off"] is True
    assert result["composition_snapshot"]["default_off"] is True
    assert result["binding_snapshot"]["startup_callback_invoked"] is False
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False


def test_dormant_binding_accepts_absent_authority_but_cannot_activate():
    result = harness.run_dormant_production_startup_port_binding_adapter_v1(
        fail_phase="authority_root_unconfigured"
    )
    assert result["ok"] is True
    assert result["adapter_snapshot"]["production_authority_configured"] is False
    assert result["adapter_snapshot"]["activation_possible"] is False
    assert result["binding_snapshot"]["production_authority_configured"] is False
    assert result["gate_snapshot"]["default_off"] is True


def test_dormant_binding_exposes_no_activation_method():
    adapter, _, _ = harness.build_dormant_production_startup_port_binding_adapter_v1()
    binding = adapter.bind_dormant()
    assert not hasattr(adapter, "activate")
    assert not hasattr(binding, "activate")
    assert not hasattr(binding, "start_runtime")


def test_disabled_composition_cannot_invoke_bound_providers_or_callback():
    adapter, _, source = harness.build_dormant_production_startup_port_binding_adapter_v1()
    binding = adapter.bind_dormant()
    with pytest.raises(Exception, match="DEFAULT_OFF"):
        binding.composition.rehearse_offline()
    assert all(count == 0 for count in source.calls.values())


def test_binding_replay_is_blocked_without_provider_invocation():
    adapter, _, source = harness.build_dormant_production_startup_port_binding_adapter_v1()
    adapter.bind_dormant()
    with pytest.raises(
        contract.RuntimeProductionStartupPortBindingBlocked,
        match="REPLAY_BLOCKED",
    ):
        adapter.bind_dormant()
    assert all(count == 0 for count in source.calls.values())


@pytest.mark.parametrize(
    "phase",
    [
        "ports_identity_mismatch",
        "synthetic_ports",
        "runtime_binding_missing",
        "missing_callable",
        "invalid_atomic_lock",
        "invalid_authority_root",
        "adapter_enabled",
        "dormant_only_disabled",
        "scope_invalid",
    ],
)
def test_invalid_port_bundle_or_adapter_configuration_fails_closed(phase):
    result = harness.run_dormant_production_startup_port_binding_adapter_v1(
        fail_phase=phase
    )
    assert result["ok"] is False
    assert result["status"].endswith("HARNESS_BLOCKED")
    assert all(count == 0 for count in result["provider_calls"].values())
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_port_bundle_and_binding_repr_are_protected():
    result = harness.run_dormant_production_startup_port_binding_adapter_v1()
    assert result["ports_protected_repr"] == "<RuntimeProductionStartupPortsV1 protected>"
    assert result["binding_protected_repr"] == (
        "<DormantRuntimeProductionStartupPortBindingV1 protected>"
    )


def test_contract_does_not_import_main_runtime_seam_registry_or_external_clients():
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


def test_harness_contains_no_real_storage_secret_or_service_reference():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_harness_v1.py"
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


def test_runtime_main_integrates_only_the_dormant_port_binding_adapter():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "runtime_production_startup_port_binding_adapter_contract_v1" in source
    assert "RuntimeProductionStartupPortBindingAdapterContractV1" in source
    assert "_install_c3_production_startup_port_binding_dormant_v1" in source
    assert "C3_PRODUCTION_STARTUP_PORT_BINDING_DORMANT_V1" in source
