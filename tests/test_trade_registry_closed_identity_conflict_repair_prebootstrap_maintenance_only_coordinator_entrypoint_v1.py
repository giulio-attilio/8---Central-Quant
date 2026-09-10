from __future__ import annotations

import inspect

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_only_coordinator_entrypoint_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_only_coordinator_entrypoint_harness_v1 as harness


def _composition(**kwargs):
    return harness.build_synthetic_maintenance_only_composition_v1(**kwargs)


def test_entrypoint_is_default_off_and_does_not_collect_evidence() -> None:
    _bridge, _adapter, entrypoint, environment, _request = _composition(
        entrypoint_enabled=False
    )

    snapshot = entrypoint.snapshot()

    assert snapshot["default_off"] is True
    assert snapshot["writer_mutations_allowed"] is False
    assert snapshot["runtime_activation_allowed"] is False
    assert snapshot["runtime_integrated"] is False
    assert snapshot["production_ready"] is False
    assert snapshot["live_allowed"] is False
    assert environment.control_reads == 0
    assert environment.coordinator.events == []


def test_default_off_entrypoint_blocks_composed_bridge_before_lease() -> None:
    composed, _adapter, _entrypoint, environment, request = _composition(
        entrypoint_enabled=False
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert environment.coordinator.lease_enter_count == 0


def test_maintenance_status_is_ready_without_claiming_runtime_readiness() -> None:
    _bridge, _adapter, entrypoint, _environment, _request = _composition()

    status = entrypoint.coordination_status()

    assert status["ok"] is True
    assert status["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_ONLY_READY"
    assert status["enabled"] is True
    assert status["maintenance_only"] is True
    assert status["registered_writer_count"] == 19
    assert status["all_writers_registered"] is True
    assert status["inflight_mutations"] == 0
    assert status["writer_mutations_allowed"] is False
    assert status["runtime_activation_allowed"] is False
    assert status["startup_recovery_verified"] is False
    assert status["coordination_ready"] is False
    assert status["runtime_integrated"] is False
    assert status["production_ready"] is False
    assert status["live_allowed"] is False


def test_full_composition_uses_entrypoint_adapter_and_bridge_successfully() -> None:
    result = harness.run_synthetic_maintenance_only_composition_v1()

    assert result["ok"] is True
    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_VERIFIED"
    assert result["one_lease_used"] is True
    assert result["same_raw_permit_used"] is True
    assert result["writer_mutations_allowed"] is False
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False
    assert result["write_executed"] is False
    assert result["registry_write"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


def test_adapter_receives_status_and_lease_from_same_entrypoint_instance() -> None:
    _bridge, adapter, entrypoint, _environment, _request = _composition()

    assert adapter._coordinator_port is entrypoint


def test_writer_mutation_is_denied_without_calling_underlying_coordinator() -> None:
    _bridge, _adapter, entrypoint, environment, _request = _composition()

    with pytest.raises(
        contract.PrebootstrapMaintenanceOnlyCoordinatorBlocked,
        match="PREBOOTSTRAP_MAINTENANCE_ONLY_WRITER_MUTATIONS_FORBIDDEN",
    ):
        with entrypoint.writer_mutation("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"):
            pass

    assert environment.coordinator.mutation_attempts == 0


def test_runtime_activation_is_unconditionally_denied() -> None:
    _bridge, _adapter, entrypoint, _environment, _request = _composition()

    with pytest.raises(
        contract.PrebootstrapMaintenanceOnlyCoordinatorBlocked,
        match="PREBOOTSTRAP_MAINTENANCE_ONLY_RUNTIME_ACTIVATION_FORBIDDEN",
    ):
        entrypoint.request_runtime_activation()


@pytest.mark.parametrize(
    "fail_phase",
    [
        "unsafe_trading_controls",
        "writer_missing",
        "inflight_writer",
        "stale_active_lease",
        "invalid_namespace",
        "lock_backend_unready",
        "lease_store_unready",
    ],
)
def test_unsafe_preconditions_block_before_underlying_lease(
    fail_phase: str,
) -> None:
    composed, _adapter, _entrypoint, environment, request = _composition(
        fail_phase=fail_phase
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert environment.coordinator.lease_enter_count == 0
    assert "repair_under_maintenance" not in environment.operations.events


@pytest.mark.parametrize(
    "fail_phase",
    ["invalid_permit", "permit_namespace_mismatch", "lease_acquire_failed"],
)
def test_lease_or_permit_failure_blocks_all_work(fail_phase: str) -> None:
    composed, _adapter, _entrypoint, environment, request = _composition(
        fail_phase=fail_phase
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert "repair_under_maintenance" not in environment.operations.events
    assert result["write_executed"] is False
    assert result["registry_write"] is False


def test_nested_maintenance_lease_is_denied() -> None:
    _bridge, _adapter, entrypoint, environment, _request = _composition()

    with entrypoint.maintenance_lease() as first:
        with pytest.raises(
            contract.PrebootstrapMaintenanceOnlyCoordinatorBlocked,
            match="PREBOOTSTRAP_MAINTENANCE_ONLY_NESTED_LEASE_FORBIDDEN",
        ):
            with entrypoint.maintenance_lease():
                pass
        assert id(first) == environment.coordinator.last_permit_identity

    assert environment.coordinator.lease_enter_count == 1
    assert environment.coordinator.lease_exit_count == 1


def test_release_is_verified_after_success() -> None:
    _bridge, _adapter, entrypoint, environment, _request = _composition()

    with entrypoint.maintenance_lease():
        assert entrypoint.snapshot()["active_maintenance_lease"] is True

    assert entrypoint.snapshot()["active_maintenance_lease"] is False
    assert entrypoint.snapshot()["last_release_verified"] is True
    assert environment.coordinator.lease_state == "RELEASED"


@pytest.mark.parametrize(
    "fail_phase",
    ["release_unverified", "lease_release_exception"],
)
def test_release_failure_is_explicit_and_fail_closed(fail_phase: str) -> None:
    _bridge, _adapter, entrypoint, _environment, _request = _composition(
        fail_phase=fail_phase
    )

    with pytest.raises(
        contract.PrebootstrapMaintenanceOnlyCoordinatorBlocked,
        match=(
            "PREBOOTSTRAP_MAINTENANCE_ONLY_RELEASE_UNVERIFIED"
            if fail_phase == "release_unverified"
            else "PREBOOTSTRAP_MAINTENANCE_ONLY_LEASE_FAILED_CLOSED"
        ),
    ):
        with entrypoint.maintenance_lease():
            pass

    assert entrypoint.snapshot()["last_release_verified"] is False


def test_post_mutation_failure_rolls_back_under_the_entrypoint_lease() -> None:
    composed, _adapter, _entrypoint, environment, request = _composition(
        fail_phase="recovery_rejected"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_RECOVERY_FAILED_CLOSED"
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is True
    assert environment.operations.registry == environment.operations.source
    assert environment.coordinator.lease_enter_count == 1
    assert environment.coordinator.lease_exit_count == 1
    assert set(environment.operations.callback_permit_identities) == {
        environment.coordinator.last_permit_identity
    }


def test_entrypoint_repr_does_not_expose_configuration_or_coordinator() -> None:
    _bridge, _adapter, entrypoint, _environment, _request = _composition()

    assert repr(entrypoint) == (
        "<PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1 protected>"
    )


def test_contract_and_harness_do_not_import_runtime_or_external_capabilities() -> None:
    source = inspect.getsource(contract) + inspect.getsource(harness)
    forbidden = (
        "import main",
        "runtime_seam_v1",
        "writer_runtime_coordinator_v1",
        "runtime_operation_v1",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
    )

    assert all(token not in source for token in forbidden)
