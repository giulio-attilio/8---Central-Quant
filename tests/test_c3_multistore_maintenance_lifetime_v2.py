"""Synthetic physical maintenance leases; no runtime or real data access."""
from contextvars import copy_context
from copy import copy
from dataclasses import asdict, replace
from pathlib import Path
import tempfile
import threading

import pytest
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2 as harness


@pytest.fixture
def values():
    with tempfile.TemporaryDirectory(prefix="c3_current_maintenance_") as root:
        yield harness.build_authenticated_persistent_authority_production_adapters_context_v2(Path(root))


def recover(values, permit):
    return values["multistore"].recover_multistore_v2(
        maintenance_permit=permit, root_authority_attestation=values["attestation"], now_epoch=1500)


def current(values, permit):
    return values["maintenance_coordinator"].maintenance_permit_is_current_v1(
        permit, lock_backend=values["lock_backend"])


def no_stores(values):
    assert values["transaction_port"].call_count == 0
    assert values["resolved_port"].call_count == 0
    assert values["prepared"].call_count == 0


def outer_lock_available(values):
    competitor = storage.CrossPlatformInterprocessFileLockBackendV1(values["lock_backend"].storage_root, enabled=True)
    handle = competitor.acquire(values["maintenance_coordinator"].lock_namespace, 0.02)
    assert handle is not None
    handle.release()


def test_released_maintenance_permit_cannot_recover_stores():
    with tempfile.TemporaryDirectory(prefix="c3_released_permit_") as root:
        values = harness.build_authenticated_persistent_authority_production_adapters_context_v2(Path(root))
        coordinator = values["maintenance_coordinator"]
        with coordinator.maintenance_lease() as issued:
            stale = asdict(issued)
            assert coordinator.maintenance_permit_is_current_v1(stale, lock_backend=values["lock_backend"]) is True
        assert coordinator.snapshot()["maintenance_lease_state"] == "RELEASED"
        with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
            values["multistore"].recover_multistore_v2(
                maintenance_permit=stale,
                root_authority_attestation=values["attestation"], now_epoch=1500)
        assert values["transaction_port"].call_count == 0
        assert values["resolved_port"].call_count == 0


def test_active_lease_recovers_then_expires_without_promoting_production(values):
    coordinator = values["maintenance_coordinator"]
    with coordinator.maintenance_lease() as permit:
        supplied = asdict(permit)
        assert current(values, supplied) is True
        result = values["boundary"](supplied)
        assert result["ok"] is True, result.get("reason")
        assert result["production_ready"] is False
        assert result["live_allowed"] is False
        assert current(values, supplied) is True
    assert current(values, supplied) is False
    assert coordinator.snapshot()["maintenance_lease_state"] == "RELEASED"
    outer_lock_available(values)


def test_older_epoch_is_rejected_during_new_active_lease(values):
    coordinator = values["maintenance_coordinator"]
    with coordinator.maintenance_lease() as first:
        old = asdict(first)
    with coordinator.maintenance_lease() as second:
        assert second.maintenance_epoch != first.maintenance_epoch
        assert current(values, asdict(second)) is True
        with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
            recover(values, old)
        no_stores(values)


def test_copied_context_cannot_resurrect_released_ownership(values):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        supplied = asdict(issued)
        captured = copy_context()
        assert captured.run(current, values, supplied) is True
    assert captured.run(current, values, supplied) is False
    with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
        captured.run(recover, values, supplied)
    no_stores(values)


def test_copied_context_in_different_thread_is_rejected(values):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        supplied = asdict(issued)
        captured = copy_context()
        outcomes = []
        def run():
            outcomes.append(captured.run(current, values, supplied))
        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert outcomes == [False]
        assert current(values, supplied) is True
    no_stores(values)


def test_copied_coordinator_does_not_own_original_frame(values):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        other = copy(values["maintenance_coordinator"])
        assert other.maintenance_permit_is_current_v1(asdict(issued), lock_backend=values["lock_backend"]) is False
        assert current(values, asdict(issued)) is True


@pytest.mark.parametrize("field,value", [
    ("maintenance_epoch", "a" * 64), ("lock_namespace_sha256", "a" * 64),
    ("registered_writer_count", 19.0), ("inflight_mutations", False),
    ("shared_lock_acquired", 1), ("state", "RELEASED"),
])
def test_guard_rejects_changed_or_type_confused_permits(values, field, value):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        supplied = asdict(issued)
        supplied[field] = value
        assert current(values, supplied) is False
        no_stores(values)


@pytest.mark.parametrize("slot", ["_config", "_lock_backend", "_lease_store"])
def test_same_context_with_replaced_dependency_is_not_authoritative(values, slot):
    coordinator = values["maintenance_coordinator"]
    with coordinator.maintenance_lease() as issued:
        original = getattr(coordinator, slot)
        replacement = replace(original) if slot == "_config" else copy(original)
        try:
            setattr(coordinator, slot, replacement)
            assert current(values, asdict(issued)) is False
        finally:
            setattr(coordinator, slot, original)
        assert current(values, asdict(issued)) is True


@pytest.mark.parametrize("field,value", [
    ("state", "RELEASED"), ("maintenance_epoch", "a" * 64),
    ("writer_inventory_sha256", "a" * 64),
])
def test_guard_consults_current_persistent_lease(values, field, value):
    coordinator, store = values["maintenance_coordinator"], values["lease_store"]
    with coordinator.maintenance_lease() as issued:
        original = dict(store.read(coordinator.lock_namespace))
        try:
            store.write(coordinator.lock_namespace, {**original, field: value})
            with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
                recover(values, asdict(issued))
            no_stores(values)
        finally:
            store.write(coordinator.lock_namespace, original)


def test_lease_read_failure_is_closed_without_store_calls(values, monkeypatch):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        with monkeypatch.context() as patch:
            def unreadable(namespace):
                raise OSError("synthetic lease read failure")
            patch.setattr(values["lease_store"], "read", unreadable)
            with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
                recover(values, asdict(issued))
            no_stores(values)


def test_expiry_during_first_store_blocks_second_and_bridge(values, monkeypatch):
    manager = values["maintenance_coordinator"].maintenance_lease()
    issued = manager.__enter__()
    closed = False
    original = values["transaction_port"].recover_store_v2
    def end_lease(**kwargs):
        nonlocal closed
        receipt = original(**kwargs)
        closed = True
        manager.__exit__(None, None, None)
        return receipt
    monkeypatch.setattr(values["transaction_port"], "recover_store_v2", end_lease)
    try:
        result = values["boundary"](asdict(issued))
        assert result["ok"] is False
        assert result["reason"] == "PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED"
        assert values["transaction_port"].call_count == 1
        assert values["resolved_port"].call_count == 0
        assert values["prepared"].call_count == 0
    finally:
        if not closed:
            manager.__exit__(None, None, None)
    assert current(values, asdict(issued)) is False
    outer_lock_available(values)
    for namespace in values["lock_namespaces"]:
        handle = values["lock_backend"].acquire(namespace, 0.02)
        assert handle is not None
        handle.release()


def test_failed_lease_cleanup_revokes_admission_even_if_file_stays_quiesced(values, monkeypatch):
    coordinator, store = values["maintenance_coordinator"], values["lease_store"]
    original = store.write
    def fail_release(namespace, lease):
        if lease["state"] == "RELEASED":
            raise OSError("synthetic lease release write failure")
        return original(namespace, lease)
    monkeypatch.setattr(store, "write", fail_release)
    with pytest.raises(coordination.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_LEASE_RELEASE_FAILED"):
        with coordinator.maintenance_lease() as issued:
            supplied = asdict(issued)
            assert current(values, supplied) is True
    assert store.read(coordinator.lock_namespace)["state"] == "QUIESCED"
    assert current(values, supplied) is False
    with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
        recover(values, supplied)
    no_stores(values)
    outer_lock_available(values)


def test_disabled_guard_performs_no_reads_and_preserves_passthrough():
    class ForbiddenStore:
        def read(self, namespace):
            pytest.fail("disabled guard must not read persistence")
    coordinator = coordination.ClosedRepairWriterRuntimeCoordinatorV1(lease_store=ForbiddenStore())
    assert coordinator.maintenance_permit_is_current_v1({}, lock_backend=None) is False
    with coordinator.mutation("synthetic-disabled-writer") as permit:
        assert permit.status == "COORDINATOR_DEFAULT_OFF_PASSTHROUGH"
        assert permit.coordinated is False


def test_previous_maintenance_only_protection_is_preserved(values):
    coordinator = values["maintenance_coordinator"]
    writer = coordination.canonical_runtime_writer_inventory_v1()[0]["writer_id"]
    with pytest.raises(coordination.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_ONLY_WRITERS_FORBIDDEN"):
        with coordinator.mutation(writer):
            pytest.fail("maintenance-only coordinator must not admit mutations")


def test_previous_nonce_failure_cleanup_is_preserved(values, monkeypatch):
    def failed_nonce():
        raise ValueError("synthetic nonce failure")
    monkeypatch.setattr(values["maintenance_coordinator"], "_nonce_source", failed_nonce)
    with pytest.raises(ValueError, match="synthetic nonce failure"):
        with values["maintenance_coordinator"].maintenance_lease():
            pytest.fail("nonce failure must not issue a permit")
    assert values["maintenance_coordinator"]._active_maintenance_frame is None
    outer_lock_available(values)


def test_existing_mutation_and_reentrancy_still_work_without_maintenance(values):
    coordinator = values["maintenance_coordinator"]
    coordinator._config = replace(coordinator._config, maintenance_only=False)
    writer = coordination.canonical_runtime_writer_inventory_v1()[0]["writer_id"]
    with coordinator.mutation(writer) as first:
        assert first.coordinated is True
        assert first.depth == 1
        with coordinator.mutation(writer) as nested:
            assert nested.reentrant is True and nested.depth == 2
            assert nested.owner_token == first.owner_token
        with pytest.raises(coordination.WriterRuntimeCoordinationBlocked, match="MAINTENANCE_FROM_MUTATION_OWNER_FORBIDDEN"):
            with coordinator.maintenance_lease():
                pytest.fail("mutation owner must not obtain maintenance")
    assert coordinator.inflight_mutations == 0
    outer_lock_available(values)


def test_released_outer_handle_is_not_proof_of_current_ownership(values):
    coordinator = values["maintenance_coordinator"]
    with pytest.raises(coordination.WriterRuntimeCoordinationBlocked, match="SHARED_LOCK_RELEASE_FAILED"):
        with coordinator.maintenance_lease() as issued:
            coordinator._active_maintenance_frame.handle.release()
            assert current(values, asdict(issued)) is False
            with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
                recover(values, asdict(issued))
            no_stores(values)
    assert coordinator._active_maintenance_frame is None
    outer_lock_available(values)


def test_repinning_copied_coordinator_does_not_create_ownership(values):
    coordinator = values["maintenance_coordinator"]
    with coordinator.maintenance_lease() as issued:
        other = copy(coordinator)
        values["multistore"]._maintenance_coordinator = other
        values["multistore"]._config = replace(values["multistore"]._config,
            expected_maintenance_coordinator_object_identity_sha256=harness._object_identity(other))
        with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
            recover(values, asdict(issued))
        no_stores(values)


def test_missing_coordinator_refuses_before_inner_lock_acquisition(values, monkeypatch):
    with values["maintenance_coordinator"].maintenance_lease() as issued:
        values["multistore"]._maintenance_coordinator = None
        def forbidden(*args):
            pytest.fail("missing ownership must not acquire store locks")
        monkeypatch.setattr(values["lock_backend"], "acquire", forbidden)
        with pytest.raises(RuntimeError, match="MULTISTORE_MAINTENANCE_NOT_CURRENT"):
            recover(values, asdict(issued))
        no_stores(values)
