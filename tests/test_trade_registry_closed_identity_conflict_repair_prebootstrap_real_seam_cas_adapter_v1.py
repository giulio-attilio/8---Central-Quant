from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_harness_v1 as harness


def _build(**kwargs):
    return harness.build_synthetic_real_seam_cas_adapter_composition_v1(**kwargs)


def test_adapter_is_default_off_without_touching_surface():
    values = _build(adapter_enabled=False)
    before = (
        values["surface"].coordinator_cas_count,
        values["surface"].guard_cas_count,
    )
    assert values["adapter"].snapshot()["default_off"] is True
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason == "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_DEFAULT_OFF"
    assert before == (
        values["surface"].coordinator_cas_count,
        values["surface"].guard_cas_count,
    )


def test_repr_protects_adapter_binding_and_config():
    values = _build()
    binding = values["adapter"].bind_offline()
    assert repr(values["adapter"]) == "<PrebootstrapRealSeamCasAdapterContractV1 protected>"
    assert repr(binding) == "<PrebootstrapRealSeamCasAdapterBindingV1 protected>"
    config = contract.PrebootstrapRealSeamCasAdapterConfigV1(
        enabled=True,
        scope_attestation="hidden-scope",
        process_boot_epoch_sha256="a" * 64,
    )
    assert "hidden-scope" not in repr(config)
    assert "a" * 64 not in repr(config)


def test_full_real_seam_shaped_rehearsal_is_offline_and_closed():
    result = harness.run_synthetic_real_seam_cas_adapter_composition_v1()
    assert result["ok"] is True
    assert result["binding"]["writer_guard_bound"] is True
    assert result["writer"]["allowed"] is False
    assert result["bridge_result"]["ok"] is True
    assert result["active_state"]["mode"] == "MAINTENANCE_ONLY"
    assert result["restored_state"]["mode"] == "DORMANT"
    assert result["runtime_integrated"] is False
    assert result["no_order_sent"] is True


def test_binding_uses_exact_same_guard_instance_and_lock():
    values = _build()
    binding = values["adapter"].bind_offline()
    assert values["surface"].current_writer_guard() is binding.writer_guard
    assert binding.binding_snapshot()["same_atomic_lock"] is True
    assert binding.binding_snapshot()["registered_writer_count"] == 19
    assert binding.binding_snapshot()["all_writers_routed"] is True


def test_binding_is_one_shot_per_adapter_instance():
    values = _build()
    values["adapter"].bind_offline()
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason == "PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_ALREADY_BOUND"


@pytest.mark.parametrize(
    ("phase", "suffix"),
    [
        ("wrong_module", "MODULE_IDENTITY_MISMATCH"),
        ("coordinator_drift", "DORMANT_IDENTITY_MISMATCH"),
        ("guard_already_bound", "WRITER_GUARD_ALREADY_BOUND"),
        ("runtime_started", "RUNTIME_ALREADY_STARTED"),
        ("workers_started", "RUNTIME_ALREADY_STARTED"),
        ("server_started", "RUNTIME_ALREADY_STARTED"),
    ],
)
def test_unsafe_surface_or_started_runtime_is_rejected(phase, suffix):
    values = _build(fail_phase=phase)
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason.endswith(suffix)
    assert values["surface"].coordinator_cas_count == 0


def test_guard_cas_failure_leaves_coordinator_dormant():
    values = _build(fail_phase="guard_cas_failed")
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason.endswith("WRITER_GUARD_CAS_FAILED")
    assert values["surface"].current is values["dormant_coordinator"]
    assert values["surface"].current_writer_guard() is None


@pytest.mark.parametrize("phase", ["guard_receipt_corrupt", "writer_route_missing"])
def test_invalid_guard_attestation_is_rolled_back(phase):
    values = _build(fail_phase=phase)
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason.endswith("WRITER_GUARD_BINDING_UNSAFE")
    assert values["surface"].current_writer_guard() is None
    assert values["surface"].current is values["dormant_coordinator"]


def test_failed_guard_rollback_fails_closed():
    values = _build(fail_phase="guard_receipt_corrupt+guard_rollback_failed")
    with pytest.raises(contract.PrebootstrapRealSeamCasAdapterBlocked) as raised:
        values["adapter"].bind_offline()
    assert raised.value.reason.endswith("WRITER_GUARD_ROLLBACK_FAILED")
    assert values["surface"].current is values["dormant_coordinator"]


def test_coordinator_cas_failure_is_contained_by_port():
    values = _build(fail_phase="coordinator_cas_failed")
    binding, installer, request = harness.bind_synthetic_real_seam_cas_adapter_v1(values)
    installer_module = __import__(
        "trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1"
    )
    with pytest.raises(
        installer_module.PrebootstrapStartupOnlySeamInstallationBlocked
    ):
        with installer.maintenance_only_installation(request):
            pass
    assert values["surface"].current is values["dormant_coordinator"]
    assert binding.port.contract_snapshot()["poisoned"] is True


def test_writer_is_allowed_after_dormant_restore_but_reinstall_is_impossible():
    values = _build()
    binding, installer, request = harness.bind_synthetic_real_seam_cas_adapter_v1(values)
    with installer.maintenance_only_installation(request):
        assert values["surface"].attempt_writer("WRITER_1")["allowed"] is False
    allowed = values["surface"].attempt_writer("WRITER_2")
    assert allowed["allowed"] is True
    assert binding.port.snapshot_installation_state()["writer_invocations_seen"] == 2


def test_contract_and_harness_do_not_import_main_or_real_seam():
    source = "\n".join(
        inspect.getsource(module).lower() for module in (contract, harness)
    )
    forbidden = (
        "import main",
        "import trade_registry_closed_identity_conflict_repair_runtime_seam_v1",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
        "open(",
    )
    assert not any(value in source for value in forbidden)


def test_files_do_not_reference_real_storage_or_external_services():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_contract_v1.py",
        root / "trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_harness_v1.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8").lower() for path in paths)
    assert ".env" not in source
    assert "/data/trade_registry" not in source
    assert "central_data_dir" not in source
    assert "bingx" not in source
    assert "render.com" not in source
