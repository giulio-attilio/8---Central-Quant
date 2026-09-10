"""In-memory harness for the pre-bootstrap physical coordinator adapter."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_bridge_v1 as bridge
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_harness_v1 as bridge_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_only_coordinator_entrypoint_contract_v1 as entrypoint_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_contract_v1 as physical_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_contract_v1 as runtime_adapter_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_harness_v1 as runtime_adapter_harness
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-PHYSICAL-COORDINATOR-PORT-ADAPTER-HARNESS-V1"
)


class InMemorySharedLockHandleV1:
    def __init__(self, backend: "InMemorySharedLockBackendV1") -> None:
        self._backend = backend
        self._released = False

    def release(self) -> None:
        if self._released:
            raise RuntimeError("synthetic lock already released")
        self._backend.locked = False
        self._released = True


class InMemorySharedLockBackendV1:
    def __init__(self, storage_root: str, *, enabled: bool = True) -> None:
        self.storage_root = storage_root
        self.enabled = enabled
        self.locked = False
        self.acquire_count = 0

    def acquire(self, _namespace: str, _timeout_seconds: float):
        self.acquire_count += 1
        if not self.enabled or self.locked:
            return None
        self.locked = True
        return InMemorySharedLockHandleV1(self)


class InMemoryMaintenanceLeaseStoreV1:
    def __init__(self, storage_root: str, *, enabled: bool = True) -> None:
        self.storage_root = storage_root
        self.enabled = enabled
        self.value: dict[str, Any] | None = None
        self.read_count = 0
        self.write_count = 0

    def read(self, _namespace: str):
        self.read_count += 1
        return copy.deepcopy(self.value)

    def write(self, _namespace: str, lease):
        if not self.enabled:
            raise RuntimeError("synthetic lease store disabled")
        self.write_count += 1
        self.value = copy.deepcopy(dict(lease))


class SyntheticPhysicalCoordinatorCompositionV1:
    def __init__(self, request: dict[str, Any], fail_phase: str | None = None):
        self.request = copy.deepcopy(request)
        self.fail_phase = fail_phase
        root = "memory://c3-prebootstrap-maintenance"
        self.lock_backend = InMemorySharedLockBackendV1(
            root,
            enabled=not self._fails("lock_backend_disabled"),
        )
        self.lease_store = InMemoryMaintenanceLeaseStoreV1(
            (
                "memory://different-root"
                if self._fails("storage_root_mismatch")
                else root
            ),
            enabled=not self._fails("lease_store_disabled"),
        )
        self._clock_value = 1000.0
        self._nonce_value = 0
        self.coordinator = coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1(
            config=coordinator_module.WriterRuntimeCoordinatorConfigV1(enabled=True),
            lock_backend=self.lock_backend,
            lease_store=self.lease_store,
            clock=self.clock,
            nonce_source=self.nonce,
            lock_namespace=coordinator_module.canonical_runtime_lock_namespace_v1(),
            writer_inventory=coordinator_module.canonical_runtime_writer_inventory_v1(),
        )
        registrations = self.coordinator.register_all_declared_writers()
        if self._fails("writer_missing"):
            self.coordinator._registered.pop(registrations[-1]["writer_id"])
        self.operations = runtime_adapter_harness.SyntheticRuntimeMaintenancePortsV1(
            request,
            fail_phase=fail_phase,
        )
        self.control_reads = 0

    def _fails(self, phase: str) -> bool:
        return phase in str(self.fail_phase or "").split("+")

    def clock(self) -> float:
        self._clock_value += 1.0
        return self._clock_value

    def nonce(self) -> str:
        self._nonce_value += 1
        return f"synthetic-nonce-{self._nonce_value}"

    def trading_controls(self) -> dict[str, Any]:
        self.control_reads += 1
        controls = copy.deepcopy(self.request["evidence"]["trading_controls"])
        if self._fails("unsafe_trading_controls"):
            controls["live_trading_enabled"] = True
        return controls

    def observe(self) -> dict[str, Any]:
        return self.operations.observe()

    def _bind_raw_permit(self, permit: Any) -> None:
        if self.operations.raw_permit_identity is None:
            self.operations.raw_permit_identity = id(permit)

    def repair_under_maintenance(self, preview, permit):
        self._bind_raw_permit(permit)
        return self.operations.repair_under_maintenance(preview, permit)

    def bootstrap_under_maintenance(self, repair_result, permit):
        self._bind_raw_permit(permit)
        return self.operations.bootstrap_under_maintenance(repair_result, permit)

    def recovery_under_existing_maintenance(self, bootstrap_result, permit):
        self._bind_raw_permit(permit)
        return self.operations.recovery_under_existing_maintenance(
            bootstrap_result, permit
        )

    def postflight_under_maintenance(self, recovery_result, permit):
        self._bind_raw_permit(permit)
        return self.operations.postflight_under_maintenance(recovery_result, permit)

    def rollback_under_maintenance(self, repair_result, permit):
        self._bind_raw_permit(permit)
        return self.operations.rollback_under_maintenance(repair_result, permit)


def build_synthetic_physical_coordinator_composition_v1(
    *,
    fail_phase: str | None = None,
    physical_adapter_enabled: bool = True,
):
    request = bridge_harness.build_synthetic_prebootstrap_request_v1()
    environment = SyntheticPhysicalCoordinatorCompositionV1(
        request,
        fail_phase=fail_phase,
    )
    namespace = coordinator_module.canonical_runtime_lock_namespace_v1()
    root_binding = physical_contract.prebootstrap_physical_storage_root_binding_sha256_v1(
        environment.lock_backend.storage_root,
        lock_namespace_sha256=namespace,
    )
    selected_lock_backend = (
        InMemorySharedLockBackendV1(environment.lock_backend.storage_root)
        if environment._fails("dependency_identity_mismatch")
        else environment.lock_backend
    )
    physical_adapter = physical_contract.PrebootstrapPhysicalCoordinatorPortAdapterContractV1(
        coordinator=environment.coordinator,
        lock_backend=selected_lock_backend,
        maintenance_lease_store=environment.lease_store,
        config=physical_contract.PrebootstrapPhysicalCoordinatorPortAdapterConfigV1(
            enabled=physical_adapter_enabled,
            scope_attestation=(
                physical_contract.PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_SCOPE_ATTESTATION_V1
                if physical_adapter_enabled
                else None
            ),
            expected_storage_root_binding_sha256=(
                "d" * 64
                if environment._fails("root_binding_mismatch")
                else root_binding
            ),
            expected_lock_namespace_sha256=(
                "c" * 64
                if environment._fails("namespace_mismatch")
                else namespace
            ),
        ),
    )
    entrypoint = entrypoint_contract.PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1(
        coordinator=physical_adapter,
        trading_controls=environment.trading_controls,
        config=entrypoint_contract.PrebootstrapMaintenanceOnlyCoordinatorConfigV1(
            enabled=True,
            scope_attestation=entrypoint_contract.PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1,
        ),
    )
    runtime_adapter = runtime_adapter_contract.PrebootstrapRuntimeMaintenanceAdapterContractV1(
        coordinator_status=entrypoint.coordination_status,
        runtime_maintenance_lease=entrypoint.maintenance_lease,
        repair_under_maintenance=environment.repair_under_maintenance,
        bootstrap_under_maintenance=environment.bootstrap_under_maintenance,
        recovery_under_existing_maintenance=environment.recovery_under_existing_maintenance,
        postflight_under_maintenance=environment.postflight_under_maintenance,
        rollback_under_maintenance=environment.rollback_under_maintenance,
        config=runtime_adapter_contract.PrebootstrapRuntimeMaintenanceAdapterConfigV1(
            enabled=True,
            scope_attestation=runtime_adapter_contract.PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1,
        ),
    )
    composed = bridge.PrebootstrapMaintenanceBridgeV1(
        observe=environment.observe,
        maintenance_lease=runtime_adapter.maintenance_lease,
        repair=runtime_adapter.repair,
        bootstrap=runtime_adapter.bootstrap,
        startup_recovery=runtime_adapter.startup_recovery,
        postflight=runtime_adapter.postflight,
        rollback=runtime_adapter.rollback,
        config=bridge.PrebootstrapMaintenanceBridgeConfigV1(
            enabled=True,
            scope_attestation=bridge.PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1,
        ),
    )
    return (
        composed,
        runtime_adapter,
        entrypoint,
        physical_adapter,
        environment,
        request,
    )


def run_synthetic_physical_coordinator_composition_v1() -> dict[str, Any]:
    composed, runtime_adapter, entrypoint, physical_adapter, environment, request = (
        build_synthetic_physical_coordinator_composition_v1()
    )
    result = composed.run_offline(request)
    storage = physical_adapter.storage_readiness()
    return {
        "ok": result.get("ok") is True,
        "status": result.get("status"),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_HARNESS_V1_VERSION,
        "bridge_result": result,
        "runtime_adapter_snapshot": runtime_adapter.snapshot(),
        "entrypoint_snapshot": entrypoint.snapshot(),
        "physical_storage_readiness": storage,
        "same_storage_root_verified": storage.get("same_storage_root_verified")
        is True,
        "coordinator_dependency_identity_verified": storage.get(
            "coordinator_dependency_identity_verified"
        )
        is True,
        "same_raw_permit_used": bool(
            environment.operations.callback_permit_identities
            and len(set(environment.operations.callback_permit_identities)) == 1
            and set(environment.operations.callback_permit_identities)
            == {environment.operations.raw_permit_identity}
        ),
        "one_lock_acquired": environment.lock_backend.acquire_count == 1,
        "lease_released": bool(
            environment.lease_store.value
            and environment.lease_store.value.get("state") == "RELEASED"
        ),
        "runtime_integrated": False,
        "production_ready": False,
        "live_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


__all__ = [
    "InMemoryMaintenanceLeaseStoreV1",
    "InMemorySharedLockBackendV1",
    "SyntheticPhysicalCoordinatorCompositionV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_PHYSICAL_COORDINATOR_PORT_ADAPTER_HARNESS_V1_VERSION",
    "build_synthetic_physical_coordinator_composition_v1",
    "run_synthetic_physical_coordinator_composition_v1",
]
