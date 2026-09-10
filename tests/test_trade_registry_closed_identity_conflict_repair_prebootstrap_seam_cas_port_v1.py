from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as installer_contract


def _build(**kwargs):
    return harness.build_synthetic_seam_cas_port_composition_v1(**kwargs)


def _cas_install(values):
    state = values["port"].snapshot_installation_state()
    return values["port"].compare_and_swap_coordinator(
        expected_generation=state["generation"],
        expected_coordinator=values["dormant_coordinator"],
        replacement_coordinator=values["environment"].coordinator,
        replacement_mode="MAINTENANCE_ONLY",
    )


def test_contract_is_default_off_without_touching_backend():
    values = _build(port_enabled=False)
    assert values["port"].contract_snapshot()["default_off"] is True
    assert values["backend"].get_count == 0
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].snapshot_installation_state()
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_DEFAULT_OFF"
    assert values["backend"].get_count == 0


def test_contract_and_config_repr_protect_identity_material():
    values = _build()
    assert repr(values["port"]) == "<PrebootstrapSeamCasPortContractV1 protected>"
    config = contract.PrebootstrapSeamCasPortConfigV1(
        enabled=True,
        scope_attestation="secret-scope",
        process_boot_epoch_sha256="a" * 64,
    )
    assert "secret-scope" not in repr(config)
    assert "a" * 64 not in repr(config)


def test_full_startup_installer_composition_is_verified_offline():
    result = harness.run_synthetic_seam_cas_port_composition_v1()
    assert result["ok"] is True
    assert result["active_state"]["mode"] == "MAINTENANCE_ONLY"
    assert result["restored_state"]["mode"] == "DORMANT"
    assert result["writer_block_reason"].endswith("MAINTENANCE_ONLY")
    assert result["bridge_result"]["ok"] is True
    assert result["runtime_integrated"] is False
    assert result["no_order_sent"] is True


def test_snapshot_exposes_exact_startup_proof_without_runtime_authority():
    values = _build()
    state = values["port"].snapshot_installation_state()
    assert state["mode"] == "DORMANT"
    assert state["startup_phase"] == "PRE_RUNTIME"
    assert state["generation"] == 0
    assert state["writer_invocations_seen"] == 0
    assert state["writer_mutations_allowed"] is True
    assert state["runtime_activation_allowed"] is False
    assert len(state["process_boot_epoch_sha256"]) == 64
    assert len(state["current_coordinator_identity_sha256"]) == 64


def test_cas_generation_is_monotonic_across_install_and_restore():
    values = _build()
    installed = _cas_install(values)
    restored = values["port"].compare_and_swap_coordinator(
        expected_generation=installed["generation_after"],
        expected_coordinator=values["environment"].coordinator,
        replacement_coordinator=values["dormant_coordinator"],
        replacement_mode="DORMANT",
    )
    assert installed["generation_before"] == 0
    assert installed["generation_after"] == 1
    assert restored["generation_before"] == 1
    assert restored["generation_after"] == 2
    assert values["port"].current_coordinator() is values["dormant_coordinator"]


def test_cas_receipt_is_self_hashed_and_sanitized():
    receipt = _cas_install(_build())
    supplied = receipt.pop("receipt_sha256")
    assert supplied == hashlib.sha256(
        contract._canonical_json(receipt).encode("utf-8")
    ).hexdigest()
    assert receipt["write_executed"] is False
    assert receipt["registry_write"] is False
    assert receipt["runtime_activation_allowed"] is False


def test_writer_is_blocked_during_maintenance_and_counted():
    values = _build()
    _cas_install(values)
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].before_writer_invocation("WRITER_1")
    assert raised.value.reason == (
        "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_BLOCKED_MAINTENANCE_ONLY"
    )
    assert values["port"].snapshot_installation_state()["writer_invocations_seen"] == 1


def test_writer_seen_before_installation_blocks_future_cas():
    values = _build()
    assert values["port"].before_writer_invocation("WRITER_1")["ok"] is True
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        _cas_install(values)
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_ALREADY_INVOKED"


@pytest.mark.parametrize("phase", ["runtime_started", "workers_started", "server_started"])
def test_any_started_runtime_surface_blocks_cas(phase):
    values = _build(fail_phase=phase)
    state = values["port"].snapshot_installation_state()
    assert state["startup_phase"] == "RUNTIME_STARTED"
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        _cas_install(values)
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_RUNTIME_ALREADY_STARTED"


def test_stale_generation_is_rejected_without_backend_write():
    values = _build()
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].compare_and_swap_coordinator(
            expected_generation=1,
            expected_coordinator=values["dormant_coordinator"],
            replacement_coordinator=values["environment"].coordinator,
            replacement_mode="MAINTENANCE_ONLY",
        )
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_GENERATION_MISMATCH"
    assert values["backend"].set_count == 0


def test_wrong_expected_coordinator_is_rejected():
    values = _build()
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].compare_and_swap_coordinator(
            expected_generation=0,
            expected_coordinator=object(),
            replacement_coordinator=values["environment"].coordinator,
            replacement_mode="MAINTENANCE_ONLY",
        )
    assert raised.value.reason.endswith("EXPECTED_COORDINATOR_MISMATCH")


def test_invalid_transition_is_rejected():
    values = _build()
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].compare_and_swap_coordinator(
            expected_generation=0,
            expected_coordinator=values["dormant_coordinator"],
            replacement_coordinator=object(),
            replacement_mode="DORMANT",
        )
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_TRANSITION_INVALID"


def test_backend_write_failure_restores_expected_coordinator():
    values = _build(fail_phase="setter_fail_once")
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        _cas_install(values)
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_BACKEND_WRITE_FAILED"
    assert values["backend"].current is values["dormant_coordinator"]
    assert values["port"].contract_snapshot()["poisoned"] is False


def test_unverified_backend_commit_is_restored_fail_closed():
    values = _build(fail_phase="setter_drift")
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        _cas_install(values)
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_BACKEND_COMMIT_UNVERIFIED"
    assert values["backend"].current is values["dormant_coordinator"]


def test_failed_restore_poisons_port():
    values = _build(fail_phase="setter_drift+rollback_failed")
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked):
        _cas_install(values)
    assert values["port"].contract_snapshot()["poisoned"] is True
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].current_coordinator()
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_POISONED"


def test_external_coordinator_drift_poisons_port():
    values = _build()
    values["backend"].current = object()
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].snapshot_installation_state()
    assert raised.value.reason == "PREBOOTSTRAP_SEAM_CAS_PORT_COORDINATOR_DRIFT"
    assert values["port"].contract_snapshot()["poisoned"] is True


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        ("runtime_state_failed", "RUNTIME_STATE_FAILED"),
        ("runtime_state_invalid", "RUNTIME_STATE_INVALID"),
    ],
)
def test_runtime_state_failures_are_closed(phase, reason):
    values = _build(fail_phase=phase, build_installer=False)
    with pytest.raises(contract.PrebootstrapSeamCasPortBlocked) as raised:
        values["port"].snapshot_installation_state()
    assert raised.value.reason.endswith(reason)


def test_invalid_coordinator_identity_fails_post_install_and_restores():
    values = _build(fail_phase="identity_invalid")
    with pytest.raises(installer_contract.PrebootstrapStartupOnlySeamInstallationBlocked):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass
    assert values["backend"].current is values["dormant_coordinator"]


def test_installer_body_failure_still_restores_dormant_coordinator():
    values = _build()
    with pytest.raises(RuntimeError, match="body failure"):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            raise RuntimeError("body failure")
    assert values["backend"].current is values["dormant_coordinator"]
    assert values["port"].snapshot_installation_state()["generation"] == 2


def test_rollback_failure_is_fail_closed():
    values = _build(fail_phase="rollback_failed")
    with pytest.raises(
        installer_contract.PrebootstrapStartupOnlySeamInstallationBlocked
    ) as raised:
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass
    assert raised.value.reason == "PREBOOTSTRAP_STARTUP_ONLY_SEAM_ROLLBACK_FAILED"


def test_contract_and_harness_have_no_real_runtime_or_io_imports():
    sources = "\n".join(
        inspect.getsource(module)
        for module in (contract, harness)
    ).lower()
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
    assert not any(value in sources for value in forbidden)
    assert "synthetic_only" in sources


def test_files_do_not_reference_env_or_real_registry_paths():
    root = Path(__file__).resolve().parents[1]
    files = (
        root / "trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_contract_v1.py",
        root / "trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_harness_v1.py",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files).lower()
    assert ".env" not in source
    assert "/data/trade_registry" not in source
    assert "central_data_dir" not in source
    assert "bingx" not in source
    assert "render.com" not in source
