from __future__ import annotations

import pytest

import trade_registry_closed_identity_conflict_repair_production_provider_v1 as provider_module
import trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1 as store_module
import trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1 as invocation_module
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_module


def test_production_coordinator_is_default_off_passthrough() -> None:
    coordinator = coordinator_module.build_production_closed_repair_writer_runtime_coordinator_v1()

    assert coordinator.enabled is False
    assert coordinator.snapshot()["default_off"] is True
    with coordinator.mutation("UNBOUND_WRITER") as permit:
        assert permit.admitted is True
        assert permit.coordinated is False
        assert permit.shared_lock_acquired is False
    with pytest.raises(
        coordinator_module.WriterRuntimeCoordinationBlocked,
        match="COORDINATOR_DEFAULT_OFF",
    ):
        with coordinator.maintenance_lease():
            pass


def test_production_invocation_adapter_is_default_off_without_callback() -> None:
    adapter = invocation_module.build_production_writer_invocation_adapter_v1()

    assert adapter.enabled is False
    assert adapter.bound_writer_count == 0
    assert adapter.snapshot()["default_off"] is True
    result = adapter.invoke("UNBOUND_WRITER", {"synthetic": True})
    assert result["ok"] is False
    assert result["reason"] == "PRODUCTION_WRITER_INVOCATION_ADAPTER_DEFAULT_OFF"
    assert result["callable_invoked"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_production_transaction_store_is_default_off_without_backend() -> None:
    store = store_module.build_production_raw_transaction_store_v1()

    assert store.enabled is False
    assert store.snapshot()["default_off"] is True
    apply_result = store.apply_attested_transaction({}, {})
    reconcile_result = store.reconcile_attested_transaction("0" * 64, {})
    assert apply_result["reason"] == "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
    assert reconcile_result["reason"] == "PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF"
    assert apply_result["write_executed"] is False
    assert reconcile_result["write_executed"] is False
    with pytest.raises(
        store_module.ProductionRawTransactionStoreBlocked,
        match="PRODUCTION_RAW_TRANSACTION_STORE_DEFAULT_OFF",
    ):
        store.load_exact_raw_registry()


def test_production_provider_is_default_off_without_dependencies() -> None:
    provider = provider_module.build_production_closed_repair_provider_v1()

    assert provider.enabled is False
    assert provider.snapshot()["default_off"] is True
    invoke_result = provider.invoke("UNBOUND_WRITER", {})
    apply_result = provider.apply_attested_transaction({}, {})
    reconcile_result = provider.reconcile_attested_transaction("0" * 64, {})
    assert invoke_result["reason"] == "PROVIDER_DEFAULT_OFF"
    assert apply_result["reason"] == "PROVIDER_DEFAULT_OFF"
    assert reconcile_result["reason"] == "PROVIDER_DEFAULT_OFF"
    assert invoke_result["no_order_sent"] is True
    with pytest.raises(
        provider_module.ProductionClosedRepairProviderBlocked,
        match="PROVIDER_DEFAULT_OFF",
    ):
        provider.load_exact_raw_registry()


def test_disabled_storage_adapters_do_not_create_or_open_files(tmp_path) -> None:
    storage_root = tmp_path / "must-remain-absent"
    lock_backend = storage_module.CrossPlatformInterprocessFileLockBackendV1(
        storage_root
    )
    lease_store = storage_module.DurableJsonMaintenanceLeaseStoreV1(storage_root)

    assert lock_backend.enabled is False
    assert lease_store.enabled is False
    assert storage_root.exists() is False
    assert lock_backend.acquire("0" * 64, 0.01) is None
    assert lease_store.read("0" * 64) is None
    assert storage_root.exists() is False
    with pytest.raises(
        storage_module.RuntimeStorageAdapterBlocked,
        match="LEASE_STORE_DEFAULT_OFF",
    ):
        lease_store.write("0" * 64, {})
    assert storage_root.exists() is False
