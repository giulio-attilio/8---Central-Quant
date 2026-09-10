"""In-memory harness for the pre-bootstrap maintenance-only entrypoint."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_bridge_v1 as bridge
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_harness_v1 as bridge_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_only_coordinator_entrypoint_contract_v1 as entrypoint_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_harness_v1 as adapter_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-MAINTENANCE-ONLY-COORDINATOR-ENTRYPOINT-HARNESS-V1"
)


class SyntheticMaintenanceOnlyCoordinatorV1:
    """Runtime-shaped coordinator with synthetic lock and lease state."""

    def __init__(self, fail_phase: str | None = None) -> None:
        self.fail_phase = fail_phase
        self.namespace = "b" * 64
        self.lease_state: str | None = None
        self.events: list[str] = []
        self.lease_enter_count = 0
        self.lease_exit_count = 0
        self.mutation_attempts = 0
        self.last_permit_identity: int | None = None

    def _fails(self, phase: str) -> bool:
        return phase in str(self.fail_phase or "").split("+")

    def snapshot(self) -> dict[str, Any]:
        self.events.append("coordinator_snapshot")
        return {
            "enabled": True,
            "default_off": False,
            "lock_namespace_sha256": (
                "invalid" if self._fails("invalid_namespace") else self.namespace
            ),
            "writer_count": 19,
            "registered_writer_count": (
                18 if self._fails("writer_missing") else 19
            ),
            "all_writers_registered": not self._fails("writer_missing"),
            "inflight_mutations": 1 if self._fails("inflight_writer") else 0,
            "maintenance_lease_state": (
                "REQUESTED"
                if self._fails("stale_active_lease")
                else self.lease_state
            ),
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def storage_readiness(self) -> dict[str, Any]:
        self.events.append("storage_readiness")
        return {
            "shared_lock_backend_ready": not self._fails("lock_backend_unready"),
            "maintenance_lease_store_ready": not self._fails("lease_store_unready"),
            "lock_namespace_sha256": self.namespace,
            "synthetic_only": True,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    @contextmanager
    def maintenance_lease(self):
        self.events.append("coordinator_maintenance_enter")
        self.lease_enter_count += 1
        if self._fails("lease_acquire_failed"):
            raise RuntimeError("synthetic lease acquisition failed")
        self.lease_state = "QUIESCED"
        permit = adapter_harness.RuntimeShapedMaintenancePermitV1(
            maintenance_epoch="a" * 64,
            state="ACTIVE" if self._fails("invalid_permit") else "QUIESCED",
            lock_namespace_sha256=(
                "c" * 64 if self._fails("permit_namespace_mismatch") else self.namespace
            ),
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
        )
        self.last_permit_identity = id(permit)
        try:
            yield permit
        finally:
            self.lease_exit_count += 1
            if self._fails("lease_release_exception"):
                raise RuntimeError("synthetic lease release failed")
            if not self._fails("release_unverified"):
                self.lease_state = "RELEASED"
            self.events.append("coordinator_maintenance_exit")

    @contextmanager
    def mutation(self, _writer_id: str):
        self.mutation_attempts += 1
        yield object()


class SyntheticMaintenanceOnlyCompositionV1:
    def __init__(self, request: dict[str, Any], fail_phase: str | None = None):
        self.request = copy.deepcopy(request)
        self.fail_phase = fail_phase
        self.coordinator = SyntheticMaintenanceOnlyCoordinatorV1(fail_phase)
        self.operations = adapter_harness.SyntheticRuntimeMaintenancePortsV1(
            request,
            fail_phase=fail_phase,
        )
        self.control_reads = 0

    def _fails(self, phase: str) -> bool:
        return phase in str(self.fail_phase or "").split("+")

    def trading_controls(self) -> dict[str, Any]:
        self.control_reads += 1
        controls = copy.deepcopy(self.request["evidence"]["trading_controls"])
        if self._fails("unsafe_trading_controls"):
            controls["enable_real_trading"] = True
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


def build_synthetic_maintenance_only_composition_v1(
    *,
    fail_phase: str | None = None,
    entrypoint_enabled: bool = True,
    adapter_enabled: bool = True,
    bridge_enabled: bool = True,
):
    request = bridge_harness.build_synthetic_prebootstrap_request_v1()
    environment = SyntheticMaintenanceOnlyCompositionV1(
        request,
        fail_phase=fail_phase,
    )
    entrypoint = entrypoint_contract.PrebootstrapMaintenanceOnlyCoordinatorEntrypointContractV1(
        coordinator=environment.coordinator,
        trading_controls=environment.trading_controls,
        config=entrypoint_contract.PrebootstrapMaintenanceOnlyCoordinatorConfigV1(
            enabled=entrypoint_enabled,
            scope_attestation=(
                entrypoint_contract.PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_SCOPE_ATTESTATION_V1
                if entrypoint_enabled
                else None
            ),
        ),
    )
    adapter = adapter_contract.PrebootstrapRuntimeMaintenanceAdapterContractV1(
        coordinator_status=entrypoint.coordination_status,
        runtime_maintenance_lease=entrypoint.maintenance_lease,
        repair_under_maintenance=environment.repair_under_maintenance,
        bootstrap_under_maintenance=environment.bootstrap_under_maintenance,
        recovery_under_existing_maintenance=environment.recovery_under_existing_maintenance,
        postflight_under_maintenance=environment.postflight_under_maintenance,
        rollback_under_maintenance=environment.rollback_under_maintenance,
        config=adapter_contract.PrebootstrapRuntimeMaintenanceAdapterConfigV1(
            enabled=adapter_enabled,
            scope_attestation=(
                adapter_contract.PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_SCOPE_ATTESTATION_V1
                if adapter_enabled
                else None
            ),
        ),
    )
    composed = bridge.PrebootstrapMaintenanceBridgeV1(
        observe=environment.observe,
        maintenance_lease=adapter.maintenance_lease,
        repair=adapter.repair,
        bootstrap=adapter.bootstrap,
        startup_recovery=adapter.startup_recovery,
        postflight=adapter.postflight,
        rollback=adapter.rollback,
        config=bridge.PrebootstrapMaintenanceBridgeConfigV1(
            enabled=bridge_enabled,
            scope_attestation=(
                bridge.PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1
                if bridge_enabled
                else None
            ),
        ),
    )
    return composed, adapter, entrypoint, environment, request


def run_synthetic_maintenance_only_composition_v1() -> dict[str, Any]:
    composed, adapter, entrypoint, environment, request = (
        build_synthetic_maintenance_only_composition_v1()
    )
    result = composed.run_offline(request)
    return {
        "ok": result.get("ok") is True,
        "status": result.get("status"),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_HARNESS_V1_VERSION,
        "bridge_result": result,
        "adapter_snapshot": adapter.snapshot(),
        "entrypoint_snapshot": entrypoint.snapshot(),
        "coordinator_events": list(environment.coordinator.events),
        "operation_events": list(environment.operations.events),
        "one_lease_used": bool(
            environment.coordinator.lease_enter_count
            == environment.coordinator.lease_exit_count
            == 1
        ),
        "same_raw_permit_used": bool(
            environment.operations.callback_permit_identities
            and set(environment.operations.callback_permit_identities)
            == {environment.coordinator.last_permit_identity}
        ),
        "writer_mutations_allowed": False,
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
    "SyntheticMaintenanceOnlyCompositionV1",
    "SyntheticMaintenanceOnlyCoordinatorV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_MAINTENANCE_ONLY_COORDINATOR_ENTRYPOINT_HARNESS_V1_VERSION",
    "build_synthetic_maintenance_only_composition_v1",
    "run_synthetic_maintenance_only_composition_v1",
]
