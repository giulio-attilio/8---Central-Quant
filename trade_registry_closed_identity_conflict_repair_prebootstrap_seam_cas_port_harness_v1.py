"""In-memory harness for the startup-only C3 seam CAS port."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as physical_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_seam_cas_port_contract_v1 as port_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as installer_contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-SEAM-CAS-PORT-HARNESS-V1"
)


class InMemoryRuntimeSeamStateV1:
    def __init__(self, dormant: Any, maintenance: Any, fail_phase: str | None = None):
        self.dormant = dormant
        self.maintenance = maintenance
        self.current = dormant
        self.fail_phase = str(fail_phase or "")
        self.lock = threading.RLock()
        self.runtime_started = False
        self.workers_started = False
        self.server_accepting_requests = False
        self.get_count = 0
        self.set_count = 0
        self._fail_once_consumed = False

    def _fails(self, phase: str) -> bool:
        return phase in self.fail_phase.split("+")

    def get_coordinator(self) -> Any:
        self.get_count += 1
        if self._fails("getter_failed"):
            raise RuntimeError("synthetic getter failure")
        return self.current

    def set_coordinator(self, value: Any) -> None:
        self.set_count += 1
        if self._fails("setter_fail_once") and not self._fail_once_consumed:
            self._fail_once_consumed = True
            raise RuntimeError("synthetic setter failure")
        if self._fails("rollback_failed") and value is self.dormant:
            raise RuntimeError("synthetic rollback failure")
        if self._fails("setter_drift") and value is self.maintenance:
            self.current = object()
            return
        self.current = value

    def identity_sha256(self, value: Any) -> str:
        if self._fails("identity_invalid") and value is self.maintenance:
            return "invalid"
        label = (
            "dormant"
            if value is self.dormant
            else "maintenance"
            if value is self.maintenance
            else "unknown"
        )
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def startup_state(self) -> dict[str, bool]:
        if self._fails("runtime_state_failed"):
            raise RuntimeError("synthetic runtime state failure")
        if self._fails("runtime_state_invalid"):
            return {"runtime_started": "false"}  # type: ignore[dict-item,return-value]
        return {
            "runtime_started": self.runtime_started or self._fails("runtime_started"),
            "workers_started": self.workers_started or self._fails("workers_started"),
            "server_accepting_requests": (
                self.server_accepting_requests or self._fails("server_started")
            ),
        }


def build_synthetic_seam_cas_port_composition_v1(
    *,
    fail_phase: str | None = None,
    port_enabled: bool = True,
    build_installer: bool = True,
):
    (
        composed,
        runtime_adapter,
        entrypoint,
        physical_adapter,
        environment,
        bridge_request,
    ) = physical_harness.build_synthetic_physical_coordinator_composition_v1()
    dormant = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
    backend = InMemoryRuntimeSeamStateV1(
        dormant,
        environment.coordinator,
        fail_phase=fail_phase,
    )
    boot_sha = hashlib.sha256(b"synthetic-process-boot-epoch").hexdigest()
    port = port_contract.PrebootstrapSeamCasPortContractV1(
        dormant_coordinator=dormant,
        coordinator_getter=backend.get_coordinator,
        coordinator_setter=backend.set_coordinator,
        coordinator_identity_sha256=backend.identity_sha256,
        runtime_state=backend.startup_state,
        atomic_lock=backend.lock,
        config=port_contract.PrebootstrapSeamCasPortConfigV1(
            enabled=port_enabled,
            scope_attestation=(
                port_contract.PREBOOTSTRAP_SEAM_CAS_PORT_SCOPE_ATTESTATION_V1
                if port_enabled
                else None
            ),
            process_boot_epoch_sha256=boot_sha if port_enabled else None,
        ),
    )
    installation_request = None
    installer = None
    if port_enabled and build_installer:
        startup_state = port.snapshot_installation_state()
        storage = physical_adapter.storage_readiness()
        installation_request = {
            "ack": installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1,
            "scope_attestation": installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
            "evidence": {
                "trading_controls": environment.trading_controls(),
                "startup_state": startup_state,
                "replacement_coordinator_binding_sha256": storage[
                    "storage_root_binding_sha256"
                ],
                "synthetic_only": True,
                "runtime_binding_satisfied": False,
                "production_authorization_valid": False,
            },
        }
        installation_request["request_sha256"] = (
            installer_contract.startup_only_seam_installation_request_sha256_v1(
                installation_request
            )
        )
        installer = installer_contract.PrebootstrapStartupOnlySeamInstallationContractV1(
            seam_port=port,
            dormant_coordinator=dormant,
            maintenance_coordinator=environment.coordinator,
            maintenance_coordinator_port=physical_adapter,
            trading_controls=environment.trading_controls,
            config=installer_contract.PrebootstrapStartupOnlySeamInstallationConfigV1(
                enabled=True,
                scope_attestation=installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
            ),
        )
    return {
        "composed": composed,
        "runtime_adapter": runtime_adapter,
        "entrypoint": entrypoint,
        "physical_adapter": physical_adapter,
        "environment": environment,
        "bridge_request": bridge_request,
        "dormant_coordinator": dormant,
        "backend": backend,
        "port": port,
        "installer": installer,
        "installation_request": installation_request,
    }


def run_synthetic_seam_cas_port_composition_v1() -> dict[str, Any]:
    values = build_synthetic_seam_cas_port_composition_v1()
    port = values["port"]
    installer = values["installer"]
    with installer.maintenance_only_installation(
        values["installation_request"]
    ) as permit:
        writer_reason = None
        try:
            port.before_writer_invocation("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP")
        except port_contract.PrebootstrapSeamCasPortBlocked as exc:
            writer_reason = exc.reason
        active_state = port.snapshot_installation_state()
        bridge_result = values["composed"].run_offline(values["bridge_request"])
    restored = port.snapshot_installation_state()
    return {
        "ok": bool(
            permit.mode == "MAINTENANCE_ONLY"
            and writer_reason
            == "PREBOOTSTRAP_SEAM_CAS_PORT_WRITER_BLOCKED_MAINTENANCE_ONLY"
            and active_state.get("mode") == "MAINTENANCE_ONLY"
            and bridge_result.get("ok") is True
            and restored.get("mode") == "DORMANT"
            and port.current_coordinator() is values["dormant_coordinator"]
        ),
        "status": "C3_PREBOOTSTRAP_SEAM_CAS_PORT_COMPOSITION_VERIFIED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_HARNESS_V1_VERSION,
        "writer_block_reason": writer_reason,
        "active_state": active_state,
        "bridge_result": bridge_result,
        "restored_state": restored,
        "runtime_integrated": False,
        "production_ready": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


__all__ = [
    "InMemoryRuntimeSeamStateV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_SEAM_CAS_PORT_HARNESS_V1_VERSION",
    "build_synthetic_seam_cas_port_composition_v1",
    "run_synthetic_seam_cas_port_composition_v1",
]
