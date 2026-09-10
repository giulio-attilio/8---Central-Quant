"""In-memory harness for the dormant real-seam/CAS-port adapter contract."""

from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as physical_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as installer_contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-REAL-SEAM-CAS-ADAPTER-HARNESS-V1"
)


def _sha(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SyntheticRealRuntimeSeamSurfaceV1:
    module_name = adapter_contract.EXPECTED_RUNTIME_SEAM_MODULE_NAME_V1

    def __init__(self, dormant: Any, maintenance: Any, fail_phase: str | None = None):
        self.atomic_lock = threading.RLock()
        self.dormant = dormant
        self.maintenance = maintenance
        self.current = dormant
        self.guard = None
        self.fail_phase = str(fail_phase or "")
        self.runtime_started = False
        self.workers_started = False
        self.server_accepting_requests = False
        self.coordinator_cas_count = 0
        self.guard_cas_count = 0

    def _fails(self, phase: str) -> bool:
        return phase in self.fail_phase.split("+")

    def current_coordinator(self) -> Any:
        return self.current

    def coordinator_identity_sha256(self, value: Any) -> str:
        label = "dormant" if value is self.dormant else "maintenance" if value is self.maintenance else "unknown"
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    def compare_and_swap_coordinator(
        self, *, expected_coordinator: Any, replacement_coordinator: Any
    ) -> dict[str, Any]:
        self.coordinator_cas_count += 1
        if self._fails("coordinator_cas_failed"):
            raise RuntimeError("synthetic coordinator CAS failed")
        if self.current is not expected_coordinator:
            raise RuntimeError("synthetic coordinator identity mismatch")
        self.current = replacement_coordinator
        receipt = {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_REAL_SEAM_COORDINATOR_CAS_COMMITTED",
            "synthetic_only": True,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
        }
        if self._fails("coordinator_receipt_corrupt"):
            receipt["ok"] = False
        receipt["receipt_sha256"] = _sha(receipt)
        return receipt

    def current_writer_guard(self):
        return self.guard

    def compare_and_swap_writer_guard(
        self, *, expected_guard: Any, replacement_guard: Any, atomic_lock: Any
    ) -> dict[str, Any]:
        self.guard_cas_count += 1
        if self._fails("guard_cas_failed"):
            raise RuntimeError("synthetic guard CAS failed")
        if atomic_lock is not self.atomic_lock or self.guard is not expected_guard:
            raise RuntimeError("synthetic guard identity mismatch")
        if self._fails("guard_rollback_failed") and replacement_guard is None:
            raise RuntimeError("synthetic guard rollback failed")
        self.guard = replacement_guard
        receipt = {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_REAL_SEAM_WRITER_GUARD_CAS_COMMITTED",
            "registered_writer_count": 19,
            "all_writers_routed": not self._fails("writer_route_missing"),
            "dynamic_at_invocation": True,
            "same_atomic_lock": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
        }
        if self._fails("guard_receipt_corrupt") and replacement_guard is not None:
            receipt["registered_writer_count"] = 18
        receipt["receipt_sha256"] = _sha(receipt)
        return receipt

    def runtime_state(self) -> dict[str, bool]:
        return {
            "runtime_started": self.runtime_started or self._fails("runtime_started"),
            "workers_started": self.workers_started or self._fails("workers_started"),
            "server_accepting_requests": (
                self.server_accepting_requests or self._fails("server_started")
            ),
        }

    def attempt_writer(self, writer_id: str) -> dict[str, Any]:
        if self.guard is None:
            return {"allowed": True, "reason": "NO_GUARD"}
        try:
            result = self.guard(writer_id)
        except Exception as exc:
            return {
                "allowed": False,
                "reason": getattr(exc, "reason", type(exc).__name__),
            }
        return {"allowed": result.get("ok") is True, "reason": result.get("status")}


def build_synthetic_real_seam_cas_adapter_composition_v1(
    *, fail_phase: str | None = None, adapter_enabled: bool = True
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
    surface = SyntheticRealRuntimeSeamSurfaceV1(
        dormant, environment.coordinator, fail_phase=fail_phase
    )
    if "wrong_module" in str(fail_phase or "").split("+"):
        surface.module_name = "wrong_runtime_seam"
    if "coordinator_drift" in str(fail_phase or "").split("+"):
        surface.current = object()
    if "guard_already_bound" in str(fail_phase or "").split("+"):
        surface.guard = lambda _writer_id: None
    boot_sha = hashlib.sha256(b"synthetic-real-seam-process-boot").hexdigest()
    adapter = adapter_contract.PrebootstrapRealSeamCasAdapterContractV1(
        seam_surface=surface,
        dormant_coordinator=dormant,
        maintenance_coordinator=environment.coordinator,
        runtime_state=surface.runtime_state,
        config=adapter_contract.PrebootstrapRealSeamCasAdapterConfigV1(
            enabled=adapter_enabled,
            scope_attestation=(
                adapter_contract.PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1
                if adapter_enabled
                else None
            ),
            process_boot_epoch_sha256=boot_sha if adapter_enabled else None,
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
        "surface": surface,
        "adapter": adapter,
    }


def bind_synthetic_real_seam_cas_adapter_v1(values: dict[str, Any]):
    binding = values["adapter"].bind_offline()
    port = binding.port
    startup_state = port.snapshot_installation_state()
    storage = values["physical_adapter"].storage_readiness()
    request = {
        "ack": installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1,
        "scope_attestation": installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
        "evidence": {
            "trading_controls": values["environment"].trading_controls(),
            "startup_state": startup_state,
            "replacement_coordinator_binding_sha256": storage[
                "storage_root_binding_sha256"
            ],
            "synthetic_only": True,
            "runtime_binding_satisfied": False,
            "production_authorization_valid": False,
        },
    }
    request["request_sha256"] = (
        installer_contract.startup_only_seam_installation_request_sha256_v1(request)
    )
    installer = installer_contract.PrebootstrapStartupOnlySeamInstallationContractV1(
        seam_port=port,
        dormant_coordinator=values["dormant_coordinator"],
        maintenance_coordinator=values["environment"].coordinator,
        maintenance_coordinator_port=values["physical_adapter"],
        trading_controls=values["environment"].trading_controls,
        config=installer_contract.PrebootstrapStartupOnlySeamInstallationConfigV1(
            enabled=True,
            scope_attestation=installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
        ),
    )
    return binding, installer, request


def run_synthetic_real_seam_cas_adapter_composition_v1() -> dict[str, Any]:
    values = build_synthetic_real_seam_cas_adapter_composition_v1()
    binding, installer, request = bind_synthetic_real_seam_cas_adapter_v1(values)
    with installer.maintenance_only_installation(request):
        writer = values["surface"].attempt_writer(
            "MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP"
        )
        bridge_result = values["composed"].run_offline(values["bridge_request"])
        active = binding.port.snapshot_installation_state()
    restored = binding.port.snapshot_installation_state()
    return {
        "ok": bool(
            writer.get("allowed") is False
            and bridge_result.get("ok") is True
            and active.get("mode") == "MAINTENANCE_ONLY"
            and restored.get("mode") == "DORMANT"
            and values["surface"].current is values["dormant_coordinator"]
        ),
        "status": "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_REHEARSAL_VERIFIED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_HARNESS_V1_VERSION,
        "binding": binding.binding_snapshot(),
        "writer": writer,
        "bridge_result": bridge_result,
        "active_state": active,
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
    "SyntheticRealRuntimeSeamSurfaceV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_HARNESS_V1_VERSION",
    "bind_synthetic_real_seam_cas_adapter_v1",
    "build_synthetic_real_seam_cas_adapter_composition_v1",
    "run_synthetic_real_seam_cas_adapter_composition_v1",
]
