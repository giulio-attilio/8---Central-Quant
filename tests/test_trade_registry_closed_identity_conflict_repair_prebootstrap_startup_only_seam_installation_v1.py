from __future__ import annotations

import copy
import inspect

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_harness_v1 as harness


def _values(**kwargs):
    return harness.build_synthetic_startup_only_seam_installation_v1(**kwargs)


def test_installer_is_default_off_without_touching_seam() -> None:
    values = _values(installer_enabled=False)
    before_events = list(values["seam"].events)

    snapshot = values["installer"].snapshot()

    assert snapshot["default_off"] is True
    assert snapshot["installation_active"] is False
    assert snapshot["writer_mutations_allowed"] is False
    assert snapshot["runtime_activation_allowed"] is False
    assert snapshot["runtime_integrated"] is False
    assert snapshot["production_ready"] is False
    assert snapshot["live_allowed"] is False
    assert values["seam"].events == before_events


def test_default_off_installer_rejects_context() -> None:
    values = _values(installer_enabled=False)

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_DEFAULT_OFF",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].cas_count == 0


def test_complete_startup_only_rehearsal_succeeds_and_restores_dormant() -> None:
    result = harness.run_synthetic_startup_only_seam_installation_v1()

    assert result["ok"] is True
    assert result["status"] == (
        "C3_PREBOOTSTRAP_STARTUP_ONLY_SEAM_REHEARSAL_VERIFIED"
    )
    assert result["active"]["installed_state"]["mode"] == "MAINTENANCE_ONLY"
    assert result["active"]["writer_attempt"]["allowed"] is False
    assert result["active"]["bridge_result"]["ok"] is True
    assert result["restored_state"]["mode"] == "DORMANT"
    assert result["cas_count"] == 1
    assert result["rollback_count"] == 1
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False
    assert result["write_executed"] is False
    assert result["registry_write"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


def test_installation_uses_exact_coordinator_and_blocks_writer() -> None:
    values = _values()
    seam = values["seam"]

    with values["installer"].maintenance_only_installation(
        values["installation_request"]
    ) as permit:
        assert seam.current_coordinator() is values["environment"].coordinator
        assert seam.mode == "MAINTENANCE_ONLY"
        assert permit.mode == "MAINTENANCE_ONLY"
        assert permit.startup_phase == "PRE_RUNTIME"
        assert permit.writer_mutations_allowed is False
        assert permit.runtime_activation_allowed is False
        assert permit.runtime_started is False
        assert seam.attempt_writer("TRADE_REGISTRY_SAVE") == {
            "writer_id": "TRADE_REGISTRY_SAVE",
            "allowed": False,
            "mode": "MAINTENANCE_ONLY",
            "runtime_activation_allowed": False,
        }


def test_context_exit_restores_exact_dormant_coordinator_with_new_generation() -> None:
    values = _values()
    seam = values["seam"]
    initial_generation = seam.generation

    with values["installer"].maintenance_only_installation(
        values["installation_request"]
    ):
        assert seam.generation == initial_generation + 1

    assert seam.current_coordinator() is values["dormant_coordinator"]
    assert seam.mode == "DORMANT"
    assert seam.generation == initial_generation + 2
    assert seam.runtime_started is False


def test_installation_permit_repr_hides_boot_and_binding_hashes() -> None:
    values = _values()

    with values["installer"].maintenance_only_installation(
        values["installation_request"]
    ) as permit:
        rendered = repr(permit)
        assert permit.process_boot_epoch_sha256 not in rendered
        assert permit.replacement_coordinator_binding_sha256 not in rendered
        assert permit.installation_receipt_sha256 not in rendered


def test_nested_installation_is_forbidden() -> None:
    values = _values()
    installer = values["installer"]

    with installer.maintenance_only_installation(values["installation_request"]):
        with pytest.raises(
            contract.PrebootstrapStartupOnlySeamInstallationBlocked,
            match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_NESTED_INSTALLATION_FORBIDDEN",
        ):
            with installer.maintenance_only_installation(
                values["installation_request"]
            ):
                pass


def test_request_replay_is_blocked_before_second_cas() -> None:
    values = _values()
    installer = values["installer"]

    with installer.maintenance_only_installation(values["installation_request"]):
        pass
    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_REPLAY_BLOCKED",
    ):
        with installer.maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].cas_count == 1


def test_request_hash_tampering_fails_before_cas() -> None:
    values = _values()
    request = copy.deepcopy(values["installation_request"])
    request["evidence"]["startup_state"]["generation"] += 1

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_REQUEST_HASH_MISMATCH",
    ):
        with values["installer"].maintenance_only_installation(request):
            pass

    assert values["seam"].cas_count == 0


@pytest.mark.parametrize(
    "fail_phase",
    [
        "runtime_started",
        "workers_started",
        "server_started",
        "writer_seen_before_startup",
    ],
)
def test_non_startup_state_is_rejected_before_cas(fail_phase: str) -> None:
    values = _values(fail_phase=fail_phase)

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_PREFLIGHT_UNSAFE",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].cas_count == 0


def test_state_drift_after_evidence_is_rejected() -> None:
    values = _values()
    values["seam"].generation += 1

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_PREFLIGHT_UNSAFE",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].cas_count == 0


def test_cas_failure_is_fail_closed_and_consumes_one_shot_request() -> None:
    values = _values(fail_phase="cas_failed")
    installer = values["installer"]

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_CAS_FAILED",
    ):
        with installer.maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert installer.snapshot()["consumed_request_count"] == 1
    assert values["seam"].mode == "DORMANT"


@pytest.mark.parametrize(
    "fail_phase",
    ["receipt_corrupt", "postcondition_writer_allowed"],
)
def test_invalid_install_postcondition_rolls_back_to_dormant(
    fail_phase: str,
) -> None:
    values = _values(fail_phase=fail_phase)

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_POSTCONDITION_FAILED",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].mode == "DORMANT"
    assert values["seam"].current_coordinator() is values["dormant_coordinator"]
    assert values["seam"].rollback_count == 1


def test_body_failure_still_restores_dormant() -> None:
    values = _values()

    with pytest.raises(RuntimeError, match="synthetic body failure"):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            raise RuntimeError("synthetic body failure")

    assert values["seam"].mode == "DORMANT"
    assert values["seam"].current_coordinator() is values["dormant_coordinator"]


def test_rollback_failure_overrides_success_and_remains_explicit() -> None:
    values = _values(fail_phase="rollback_failed")

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_ROLLBACK_FAILED",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            pass

    assert values["seam"].mode == "MAINTENANCE_ONLY"
    assert values["seam"].current_coordinator() is values["environment"].coordinator


def test_rollback_failure_is_more_important_than_body_failure() -> None:
    values = _values(fail_phase="rollback_failed")

    with pytest.raises(
        contract.PrebootstrapStartupOnlySeamInstallationBlocked,
        match="PREBOOTSTRAP_STARTUP_ONLY_SEAM_ROLLBACK_FAILED",
    ):
        with values["installer"].maintenance_only_installation(
            values["installation_request"]
        ):
            raise RuntimeError("synthetic body failure")


def test_contract_repr_is_protected() -> None:
    values = _values()

    assert repr(values["installer"]) == (
        "<PrebootstrapStartupOnlySeamInstallationContractV1 protected>"
    )


def test_contract_has_no_real_seam_filesystem_or_external_imports() -> None:
    source = inspect.getsource(contract)
    forbidden = (
        "runtime_seam_v1",
        "import main",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
    )

    assert all(token not in source for token in forbidden)
