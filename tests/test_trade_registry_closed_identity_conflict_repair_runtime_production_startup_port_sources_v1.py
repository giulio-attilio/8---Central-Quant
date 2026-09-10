from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


def test_five_source_adapters_validate_direct_dtos_and_callback_under_gate():
    result = harness.run_offline_production_startup_port_sources_v1()
    assert result["ok"] is True
    assert result["status"].endswith("HARNESS_VERIFIED")
    assert set(result["adapter_snapshots"]) == {
        "startup_adapter",
        "seam_adapter",
        "maintenance_adapter",
        "verifier_adapter",
        "callback_adapter",
    }
    assert all(item["ok"] is True for item in result["adapter_snapshots"].values())
    assert result["callback_calls"] == 1
    assert result["simulated_runtime_started"] is True


def test_sources_are_consumed_without_projection_and_outer_result_is_honest():
    result = harness.run_offline_production_startup_port_sources_v1()
    assert result["production_evidence_projected"] is False
    assert result["production_evidence_simulated"] is True
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["real_registry_accessed"] is False


def test_production_callback_receipt_never_grants_live_or_orders():
    result = harness.run_offline_production_startup_port_sources_v1()
    receipt = result["callback_receipt"]
    assert receipt["runtime_activation_allowed"] is False
    assert receipt["live_allowed"] is False
    assert receipt["order_submission_authorized"] is False
    assert receipt["no_order_sent"] is True


def test_all_five_adapters_are_default_off_without_explicit_scope():
    values = harness.build_offline_production_startup_port_sources_v1(
        adapters_enabled=False
    )
    adapters = (
        values["startup_adapter"],
        values["seam_adapter"],
        values["maintenance_adapter"],
        values["verifier_adapter"],
        values["callback_adapter"],
    )
    assert all(adapter.snapshot()["default_off"] is True for adapter in adapters)
    with pytest.raises(contract.RuntimeProductionStartupPortSourceBlocked):
        values["startup_adapter"].read()
    assert values["callback_source"].calls == 0


def test_callback_rejects_valid_looking_permit_when_gate_did_not_issue_it():
    values = harness.build_offline_production_startup_port_sources_v1()
    permit = gate_contract.RuntimeStartupAdmissionPermitV1(
        startup_allowed=True,
        runtime_activation_allowed=False,
        live_allowed=False,
        order_submission_authorized=False,
        same_atomic_lock=True,
        generation=4,
        process_boot_epoch_sha256="a" * 64,
        evidence_sha256="b" * 64,
        authority_receipt_sha256="c" * 64,
        seam_binding_receipt_sha256="d" * 64,
        maintenance_completion_receipt_sha256="e" * 64,
    )
    with pytest.raises(
        contract.RuntimeProductionStartupPortSourceBlocked,
        match="ACTIVE_PERMIT_REQUIRED",
    ):
        values["callback_adapter"].start(permit)
    assert values["callback_source"].calls == 0


@pytest.mark.parametrize(
    "phase",
    [
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
        "state_provider_failed",
        "seam_provider_failed",
        "maintenance_provider_failed",
        "source_identity_mismatch",
        "callback_failed",
        "callback_receipt_invalid",
    ],
)
def test_invalid_source_evidence_authority_or_callback_fails_closed(phase):
    result = harness.run_offline_production_startup_port_sources_v1(
        fail_phase=phase
    )
    assert result["ok"] is False
    assert result["status"].endswith("HARNESS_BLOCKED")
    assert result["simulated_runtime_started"] is False
    assert result["live_allowed"] is False
    assert result["order_submission_authorized"] is False
    assert result["no_order_sent"] is True


def test_all_adapter_repr_values_are_protected():
    values = harness.build_offline_production_startup_port_sources_v1()
    adapters = (
        values["startup_adapter"],
        values["seam_adapter"],
        values["maintenance_adapter"],
        values["verifier_adapter"],
        values["callback_adapter"],
    )
    assert all("protected" in repr(adapter) for adapter in adapters)
    assert all("sha256" not in repr(adapter).lower() for adapter in adapters)


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


def test_harness_has_no_real_storage_secret_or_service_reference():
    root = Path(__file__).resolve().parents[1]
    source = (
        root
        / "trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_harness_v1.py"
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


def test_runtime_main_remains_unintegrated_with_source_adapters():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "runtime_production_startup_port_sources_contract_v1" not in source
    assert "ProductionStartupStatePortAdapterV1" not in source
