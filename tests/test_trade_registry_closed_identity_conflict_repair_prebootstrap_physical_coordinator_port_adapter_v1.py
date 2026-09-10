from __future__ import annotations

import inspect

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


def _composition(**kwargs):
    return harness.build_synthetic_physical_coordinator_composition_v1(**kwargs)


def test_storage_root_binding_is_deterministic_and_protected() -> None:
    namespace = "b" * 64
    first = contract.prebootstrap_physical_storage_root_binding_sha256_v1(
        "memory://root",
        lock_namespace_sha256=namespace,
    )
    second = contract.prebootstrap_physical_storage_root_binding_sha256_v1(
        "memory://root",
        lock_namespace_sha256=namespace,
    )

    assert first == second
    assert len(first) == 64
    assert "memory" not in first


@pytest.mark.parametrize("root", ["", "/", "\\", "C:\\"])
def test_storage_root_binding_rejects_broad_roots(root: str) -> None:
    with pytest.raises(ValueError, match="explicit and non-root"):
        contract.prebootstrap_physical_storage_root_binding_sha256_v1(
            root,
            lock_namespace_sha256="b" * 64,
        )


def test_physical_adapter_is_default_off_without_reading_storage() -> None:
    (
        _composed,
        _runtime_adapter,
        _entrypoint,
        physical,
        environment,
        _request,
    ) = _composition(physical_adapter_enabled=False)

    snapshot = physical.snapshot()

    assert snapshot["default_off"] is True
    assert snapshot["runtime_integrated"] is False
    assert snapshot["real_registry_accessed"] is False
    assert environment.lease_store.read_count == 0
    assert environment.lock_backend.acquire_count == 0


def test_adapter_adds_storage_readiness_to_current_real_coordinator_shape() -> None:
    (
        _composed,
        _runtime_adapter,
        _entrypoint,
        physical,
        environment,
        _request,
    ) = _composition()

    assert not hasattr(environment.coordinator, "storage_readiness")
    assert callable(physical.storage_readiness)
    readiness = physical.storage_readiness()

    assert readiness["ok"] is True
    assert readiness["same_storage_root_verified"] is True
    assert readiness["coordinator_dependency_identity_verified"] is True
    assert readiness["shared_lock_backend_ready"] is True
    assert readiness["maintenance_lease_store_ready"] is True
    assert readiness["runtime_integrated"] is False
    assert readiness["real_registry_accessed"] is False


def test_full_physical_composition_succeeds_in_memory() -> None:
    result = harness.run_synthetic_physical_coordinator_composition_v1()

    assert result["ok"] is True
    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_VERIFIED"
    assert result["same_storage_root_verified"] is True
    assert result["coordinator_dependency_identity_verified"] is True
    assert result["same_raw_permit_used"] is True
    assert result["one_lock_acquired"] is True
    assert result["lease_released"] is True
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False
    assert result["write_executed"] is False
    assert result["registry_write"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


def test_physical_adapter_forwards_the_exact_coordinator_snapshot() -> None:
    (
        _composed,
        _runtime_adapter,
        _entrypoint,
        physical,
        environment,
        _request,
    ) = _composition()

    physical_snapshot = physical.snapshot()
    coordinator_snapshot = environment.coordinator.snapshot()

    assert physical_snapshot == coordinator_snapshot
    assert physical_snapshot["registered_writer_count"] == 19
    assert physical_snapshot["all_writers_registered"] is True


def test_maintenance_lease_is_the_real_coordinator_permit() -> None:
    (
        _composed,
        _runtime_adapter,
        _entrypoint,
        physical,
        environment,
        _request,
    ) = _composition()

    with physical.maintenance_lease() as permit:
        assert type(permit) is coordinator_module.WriterMaintenancePermitV1
        assert permit.state == "QUIESCED"
        assert permit.registered_writer_count == 19
        assert permit.inflight_mutations == 0
        assert permit.shared_lock_acquired is True

    assert environment.lock_backend.acquire_count == 1
    assert environment.lock_backend.locked is False
    assert environment.lease_store.value["state"] == "RELEASED"


@pytest.mark.parametrize(
    "fail_phase",
    [
        "dependency_identity_mismatch",
        "storage_root_mismatch",
        "lock_backend_disabled",
        "lease_store_disabled",
        "namespace_mismatch",
        "root_binding_mismatch",
        "writer_missing",
    ],
)
def test_invalid_physical_binding_blocks_before_lock_acquisition(
    fail_phase: str,
) -> None:
    composed, _runtime, _entrypoint, _physical, environment, request = _composition(
        fail_phase=fail_phase
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert environment.lock_backend.acquire_count == 0
    assert "repair_under_maintenance" not in environment.operations.events
    assert result["write_executed"] is False
    assert result["registry_write"] is False


def test_trading_control_failure_remains_upstream_of_physical_lease() -> None:
    composed, _runtime, _entrypoint, _physical, environment, request = _composition(
        fail_phase="unsafe_trading_controls"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert environment.lock_backend.acquire_count == 0


def test_post_mutation_failure_rolls_back_before_physical_lease_release() -> None:
    composed, _runtime, _entrypoint, _physical, environment, request = _composition(
        fail_phase="postflight_rejected"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_POSTFLIGHT_FAILED_CLOSED"
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is True
    assert environment.operations.registry == environment.operations.source
    assert environment.lease_store.value["state"] == "RELEASED"
    assert environment.operations.events[-1] == "rollback_under_maintenance"


def test_protected_repr_hides_root_binding_and_dependencies() -> None:
    _composed, _runtime, _entrypoint, physical, _environment, _request = (
        _composition()
    )

    assert repr(physical) == (
        "<PrebootstrapPhysicalCoordinatorPortAdapterContractV1 protected>"
    )


def test_contract_has_no_runtime_filesystem_or_external_imports() -> None:
    source = inspect.getsource(contract)
    forbidden = (
        "import main",
        "writer_runtime_coordinator_v1",
        "writer_runtime_storage_adapters_v1",
        "runtime_seam_v1",
        "runtime_operation_v1",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
    )

    assert all(token not in source for token in forbidden)
