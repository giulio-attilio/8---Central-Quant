"""Synthetic harness for the dormant pre-bootstrap runtime adapter contract."""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_bridge_v1 as bridge
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_harness_v1 as bridge_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_runtime_maintenance_adapter_contract_v1 as adapter_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-RUNTIME-MAINTENANCE-ADAPTER-HARNESS-V1"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeShapedMaintenancePermitV1:
    """Exact six-field shape currently exposed by the runtime coordinator."""

    maintenance_epoch: str
    state: str
    lock_namespace_sha256: str
    registered_writer_count: int
    inflight_mutations: int
    shared_lock_acquired: bool


class SyntheticRuntimeMaintenancePortsV1:
    """In-memory ports shaped like the future maintenance runtime boundary."""

    def __init__(self, request: dict[str, Any], fail_phase: str | None = None):
        self.request = copy.deepcopy(request)
        self.fail_phase = fail_phase
        self.source = bridge_harness.synthetic_registry_before_v1()
        self.candidate = bridge_harness.synthetic_registry_candidate_v1()
        self.registry = copy.deepcopy(self.source)
        self.open_before = copy.deepcopy(self.source["open_trades"])
        self.events: list[str] = []
        self.lease_enter_count = 0
        self.lease_exit_count = 0
        self.raw_permit_identity: int | None = None
        self.callback_permit_identities: list[int] = []

    def _fails(self, phase: str) -> bool:
        return phase in str(self.fail_phase or "").split("+")

    @staticmethod
    def _safe_result(**values: Any) -> dict[str, Any]:
        return {
            "synthetic_only": True,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            **values,
        }

    def observe(self) -> dict[str, Any]:
        self.events.append("observe")
        return copy.deepcopy(self.request["evidence"])

    def coordinator_status(self) -> dict[str, Any]:
        self.events.append("coordinator_status")
        status = {
            "enabled": True,
            "maintenance_only": True,
            "coordination_ready": False,
            "registered_writer_count": 19,
            "all_writers_registered": True,
            "inflight_mutations": 0,
            "shared_lock_backend_ready": True,
            "maintenance_lease_store_ready": True,
            "writer_mutations_allowed": False,
            "runtime_activation_allowed": False,
            "startup_recovery_verified": False,
        }
        if self._fails("unsafe_coordinator"):
            status["writer_mutations_allowed"] = True
        return status

    @contextmanager
    def runtime_maintenance_lease(self):
        self.events.append("runtime_maintenance_enter")
        self.lease_enter_count += 1
        permit = RuntimeShapedMaintenancePermitV1(
            maintenance_epoch="a" * 64,
            state=("ACTIVE" if self._fails("invalid_raw_permit") else "QUIESCED"),
            lock_namespace_sha256="b" * 64,
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
        )
        self.raw_permit_identity = id(permit)
        try:
            yield permit
        finally:
            self.lease_exit_count += 1
            self.events.append("runtime_maintenance_exit")

    def _record_permit(self, permit: Any) -> bool:
        identity = id(permit)
        self.callback_permit_identities.append(identity)
        return identity == self.raw_permit_identity

    def repair_under_maintenance(
        self, preview: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("repair_under_maintenance")
        same = self._record_permit(permit)
        if self._fails("repair_rejected_no_write"):
            return self._safe_result(
                ok=False,
                status="SYNTHETIC_REPAIR_REJECTED",
                simulated_registry_write=False,
            )
        if not same or _sha(self.registry) != preview.get("source_registry_sha256"):
            return self._safe_result(
                ok=False,
                status="SYNTHETIC_REPAIR_DRIFT",
                simulated_registry_write=False,
            )
        self.registry = copy.deepcopy(self.candidate)
        if self._fails("repair_rejected_after_write"):
            return self._safe_result(
                ok=False,
                status="SYNTHETIC_REPAIR_REJECTED_AFTER_WRITE",
                simulated_registry_write=True,
            )
        return self._safe_result(
            ok=True,
            status="SYNTHETIC_CLOSED_REPAIR_APPLIED",
            simulated_registry_write=True,
            preservation_verified=True,
            gross_r_preservation_verified=True,
            open_trades_preserved_exactly=self.registry["open_trades"]
            == self.open_before,
            conflict_count_after=0,
            source_registry_sha256=_sha(self.source),
            candidate_registry_sha256=_sha(self.registry),
            changed_paths=bridge_harness.synthetic_changed_paths_v1(),
        )

    def bootstrap_under_maintenance(
        self, repair_result: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("bootstrap_under_maintenance")
        same = self._record_permit(permit)
        if self._fails("bootstrap_rejected"):
            return self._safe_result(ok=False, status="SYNTHETIC_BOOTSTRAP_REJECTED")
        return self._safe_result(
            ok=same,
            status="SYNTHETIC_BOOTSTRAP_COMPLETED",
            source_registry_sha256=_sha(self.registry),
            conflict_count_after=0,
            migration_done=True,
            restart_readiness_attested=True,
            last_load_ok=True,
            last_write_ok=True,
            write_allowed=True,
        )

    def recovery_under_existing_maintenance(
        self, bootstrap_result: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("recovery_under_existing_maintenance")
        same = self._record_permit(permit)
        if self._fails("recovery_rejected"):
            return self._safe_result(ok=False, status="SYNTHETIC_RECOVERY_REJECTED")
        return self._safe_result(
            ok=same,
            status="SYNTHETIC_STARTUP_RECOVERY_COMPLETED",
            startup_recovery_verified=True,
            prepared_transactions_after=0,
            resolved_transactions_after=0,
            unresolved_transactions_after=0,
            maintenance_epoch=permit.maintenance_epoch,
            lock_namespace_sha256=permit.lock_namespace_sha256,
        )

    def postflight_under_maintenance(
        self, recovery_result: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("postflight_under_maintenance")
        same = self._record_permit(permit)
        if self._fails("postflight_rejected"):
            return self._safe_result(ok=False, status="SYNTHETIC_POSTFLIGHT_REJECTED")
        return self._safe_result(
            ok=same,
            status="SYNTHETIC_READINESS_PROJECTED",
            registry_storage_ready=True,
            coordination_ready=True,
            registered_writer_count=19,
            startup_recovery_verified=True,
            runtime_integrated=False,
            production_ready=False,
            live_allowed=False,
        )

    def rollback_under_maintenance(
        self, repair_result: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("rollback_under_maintenance")
        same = self._record_permit(permit)
        if self._fails("rollback_rejected"):
            return self._safe_result(ok=False, status="SYNTHETIC_ROLLBACK_REJECTED")
        self.registry = copy.deepcopy(self.source)
        return self._safe_result(
            ok=same,
            status="SYNTHETIC_PREBOOTSTRAP_ROLLBACK_VERIFIED",
            source_restored=_sha(self.registry) == _sha(self.source),
            open_trades_preserved_exactly=self.registry["open_trades"]
            == self.open_before,
        )


def build_synthetic_runtime_maintenance_composition_v1(
    *,
    fail_phase: str | None = None,
    adapter_enabled: bool = True,
    bridge_enabled: bool = True,
) -> tuple[
    bridge.PrebootstrapMaintenanceBridgeV1,
    adapter_contract.PrebootstrapRuntimeMaintenanceAdapterContractV1,
    SyntheticRuntimeMaintenancePortsV1,
    dict[str, Any],
]:
    request = bridge_harness.build_synthetic_prebootstrap_request_v1()
    ports = SyntheticRuntimeMaintenancePortsV1(request, fail_phase=fail_phase)
    adapter = adapter_contract.PrebootstrapRuntimeMaintenanceAdapterContractV1(
        coordinator_status=ports.coordinator_status,
        runtime_maintenance_lease=ports.runtime_maintenance_lease,
        repair_under_maintenance=ports.repair_under_maintenance,
        bootstrap_under_maintenance=ports.bootstrap_under_maintenance,
        recovery_under_existing_maintenance=ports.recovery_under_existing_maintenance,
        postflight_under_maintenance=ports.postflight_under_maintenance,
        rollback_under_maintenance=ports.rollback_under_maintenance,
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
        observe=ports.observe,
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
    return composed, adapter, ports, request


def run_synthetic_runtime_maintenance_composition_v1() -> dict[str, Any]:
    composed, adapter, ports, request = (
        build_synthetic_runtime_maintenance_composition_v1()
    )
    result = composed.run_offline(request)
    return {
        "ok": result.get("ok") is True,
        "status": result.get("status"),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_HARNESS_V1_VERSION,
        "bridge_result": result,
        "adapter_snapshot": adapter.snapshot(),
        "events": list(ports.events),
        "one_outer_lease_used": ports.lease_enter_count == ports.lease_exit_count == 1,
        "same_raw_permit_used": bool(
            ports.callback_permit_identities
            and set(ports.callback_permit_identities)
            == {ports.raw_permit_identity}
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
    "RuntimeShapedMaintenancePermitV1",
    "SyntheticRuntimeMaintenancePortsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_RUNTIME_MAINTENANCE_ADAPTER_HARNESS_V1_VERSION",
    "build_synthetic_runtime_maintenance_composition_v1",
    "run_synthetic_runtime_maintenance_composition_v1",
]
