from __future__ import annotations

import inspect
from dataclasses import fields

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_harness_v1 as harness


def _composition(**kwargs):
    return harness.build_synthetic_runtime_maintenance_composition_v1(**kwargs)


def test_adapter_is_default_off_and_production_incapable() -> None:
    composed, adapter, ports, request = _composition(adapter_enabled=False)

    snapshot = adapter.snapshot()
    result = composed.run_offline(request)

    assert snapshot["default_off"] is True
    assert snapshot["runtime_integrated"] is False
    assert snapshot["production_ready"] is False
    assert snapshot["apply_allowed"] is False
    assert snapshot["activation_allowed"] is False
    assert snapshot["live_allowed"] is False
    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert ports.lease_enter_count == 0


def test_runtime_shaped_permit_has_only_the_six_current_runtime_fields() -> None:
    assert [item.name for item in fields(harness.RuntimeShapedMaintenancePermitV1)] == [
        "maintenance_epoch",
        "state",
        "lock_namespace_sha256",
        "registered_writer_count",
        "inflight_mutations",
        "shared_lock_acquired",
    ]


def test_status_and_lease_must_come_from_same_coordinator_instance() -> None:
    _composed, _adapter, first, _request = _composition()
    _other_composed, _other_adapter, second, _other_request = _composition()

    with pytest.raises(
        TypeError,
        match="must be bound to the same instance",
    ):
        contract.PrebootstrapRuntimeMaintenanceAdapterContractV1(
            coordinator_status=first.coordinator_status,
            runtime_maintenance_lease=second.runtime_maintenance_lease,
            repair_under_maintenance=first.repair_under_maintenance,
            bootstrap_under_maintenance=first.bootstrap_under_maintenance,
            recovery_under_existing_maintenance=first.recovery_under_existing_maintenance,
            postflight_under_maintenance=first.postflight_under_maintenance,
            rollback_under_maintenance=first.rollback_under_maintenance,
        )


def test_adapter_projects_missing_maintenance_guards_without_mutating_raw_permit() -> None:
    _composed, adapter, ports, _request = _composition()

    with adapter.maintenance_lease() as permit:
        assert permit.maintenance_only is True
        assert permit.writer_mutations_allowed is False
        assert permit.runtime_activation_allowed is False
        assert not hasattr(adapter._active_raw_permit, "maintenance_only")
        assert id(adapter._active_raw_permit) == ports.raw_permit_identity

    assert adapter.snapshot()["active_lease"] is False


def test_happy_path_uses_one_outer_lease_and_one_raw_permit() -> None:
    result = harness.run_synthetic_runtime_maintenance_composition_v1()

    assert result["ok"] is True
    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_VERIFIED"
    assert result["one_outer_lease_used"] is True
    assert result["same_raw_permit_used"] is True
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["live_allowed"] is False
    assert result["write_executed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["no_order_sent"] is True


def test_happy_path_phase_order_is_explicit() -> None:
    composed, _adapter, ports, request = _composition()

    result = composed.run_offline(request)

    assert result["ok"] is True
    assert ports.events == [
        "observe",
        "coordinator_status",
        "runtime_maintenance_enter",
        "repair_under_maintenance",
        "bootstrap_under_maintenance",
        "recovery_under_existing_maintenance",
        "postflight_under_maintenance",
        "runtime_maintenance_exit",
    ]
    assert ports.lease_enter_count == ports.lease_exit_count == 1
    assert len(set(ports.callback_permit_identities)) == 1


def test_adapter_rejects_callback_outside_active_lease() -> None:
    _composed, adapter, _ports, request = _composition()

    with pytest.raises(
        contract.PrebootstrapRuntimeMaintenanceAdapterBlocked,
        match="PREBOOTSTRAP_RUNTIME_PERMIT_IDENTITY_MISMATCH",
    ):
        adapter.repair(request["evidence"]["preview_receipt"], object())


def test_adapter_rejects_different_bridge_permit_instance() -> None:
    _composed, adapter, _ports, request = _composition()

    with adapter.maintenance_lease() as permit:
        replacement = contract.PrebootstrapMaintenancePermitAdapterV1(
            **{
                item.name: getattr(permit, item.name)
                for item in fields(contract.PrebootstrapMaintenancePermitAdapterV1)
            }
        )
        with pytest.raises(
            contract.PrebootstrapRuntimeMaintenanceAdapterBlocked,
            match="PREBOOTSTRAP_RUNTIME_PERMIT_IDENTITY_MISMATCH",
        ):
            adapter.repair(request["evidence"]["preview_receipt"], replacement)


def test_nested_runtime_maintenance_lease_is_forbidden() -> None:
    _composed, adapter, _ports, _request = _composition()

    with adapter.maintenance_lease():
        with pytest.raises(
            contract.PrebootstrapRuntimeMaintenanceAdapterBlocked,
            match="PREBOOTSTRAP_RUNTIME_NESTED_LEASE_FORBIDDEN",
        ):
            with adapter.maintenance_lease():
                pass


def test_bootstrap_cannot_run_before_repair() -> None:
    _composed, adapter, _ports, _request = _composition()

    with adapter.maintenance_lease() as permit:
        with pytest.raises(
            contract.PrebootstrapRuntimeMaintenanceAdapterBlocked,
            match="PREBOOTSTRAP_RUNTIME_PHASE_ORDER_INVALID",
        ):
            adapter.bootstrap({}, permit)


def test_non_applicable_preview_is_mandatory() -> None:
    _composed, adapter, _ports, request = _composition()
    preview = dict(request["evidence"]["preview_receipt"])
    preview["apply_allowed"] = True

    with adapter.maintenance_lease() as permit:
        with pytest.raises(
            contract.PrebootstrapRuntimeMaintenanceAdapterBlocked,
            match="PREBOOTSTRAP_RUNTIME_PREVIEW_MUST_REMAIN_NON_APPLICABLE",
        ):
            adapter.repair(preview, permit)


def test_unsafe_maintenance_only_coordinator_fails_before_lease() -> None:
    composed, _adapter, ports, request = _composition(
        fail_phase="unsafe_coordinator"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert ports.lease_enter_count == 0
    assert ports.events == ["observe", "coordinator_status"]


def test_invalid_runtime_permit_fails_closed_and_releases_context() -> None:
    composed, _adapter, ports, request = _composition(
        fail_phase="invalid_raw_permit"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_FAILED_CLOSED"
    assert ports.lease_enter_count == ports.lease_exit_count == 1
    assert "repair_under_maintenance" not in ports.events


@pytest.mark.parametrize(
    ("fail_phase", "expected_status"),
    [
        ("repair_rejected_after_write", "PREBOOTSTRAP_REPAIR_FAILED_CLOSED"),
        ("bootstrap_rejected", "PREBOOTSTRAP_BOOTSTRAP_FAILED_CLOSED"),
        ("recovery_rejected", "PREBOOTSTRAP_RECOVERY_FAILED_CLOSED"),
        ("postflight_rejected", "PREBOOTSTRAP_POSTFLIGHT_FAILED_CLOSED"),
    ],
)
def test_every_post_mutation_failure_rolls_back_inside_same_lease(
    fail_phase: str, expected_status: str
) -> None:
    composed, _adapter, ports, request = _composition(fail_phase=fail_phase)

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == expected_status
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is True
    assert ports.registry == ports.source
    assert ports.events[-2:] == [
        "rollback_under_maintenance",
        "runtime_maintenance_exit",
    ]
    assert ports.lease_enter_count == ports.lease_exit_count == 1
    assert set(ports.callback_permit_identities) == {ports.raw_permit_identity}


def test_repair_rejection_without_mutation_does_not_claim_rollback() -> None:
    composed, _adapter, ports, request = _composition(
        fail_phase="repair_rejected_no_write"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_REPAIR_FAILED_CLOSED"
    assert result["rollback_attempted"] is False
    assert "rollback_under_maintenance" not in ports.events
    assert ports.registry == ports.source


def test_failed_rollback_is_explicit_and_fail_closed() -> None:
    composed, _adapter, _ports, request = _composition(
        fail_phase="bootstrap_rejected+rollback_rejected"
    )

    result = composed.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "PREBOOTSTRAP_ROLLBACK_FAILED_CLOSED"
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is False


def test_bridge_replay_is_blocked_without_opening_another_lease() -> None:
    composed, _adapter, ports, request = _composition()

    first = composed.run_offline(request)
    second = composed.run_offline(request)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status"] == "PREBOOTSTRAP_REQUEST_REPLAY_BLOCKED"
    assert ports.lease_enter_count == 1


def test_protected_representations_do_not_expose_scope_or_permit_hashes() -> None:
    _composed, adapter, _ports, _request = _composition()

    assert repr(adapter) == "<PrebootstrapRuntimeMaintenanceAdapterContractV1 protected>"
    with adapter.maintenance_lease() as permit:
        rendered = repr(permit)
        assert "a" * 64 not in rendered
        assert "b" * 64 not in rendered
        assert permit.permit_binding_sha256 not in rendered


def test_contract_and_harness_have_no_runtime_or_external_capability_imports() -> None:
    contract_source = inspect.getsource(contract)
    harness_source = inspect.getsource(harness)
    combined = contract_source + harness_source

    forbidden = (
        "import main",
        "runtime_seam_v1",
        "runtime_operation_v1",
        "import requests",
        "import urllib",
        "import socket",
        "import os",
        "from pathlib",
    )
    assert all(token not in combined for token in forbidden)
