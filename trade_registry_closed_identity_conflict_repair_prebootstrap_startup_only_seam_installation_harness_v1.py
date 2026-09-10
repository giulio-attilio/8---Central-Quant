"""Synthetic harness for startup-only C3 seam installation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as physical_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PREBOOTSTRAP-STARTUP-ONLY-SEAM-INSTALLATION-HARNESS-V1"
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


class SyntheticStartupOnlySeamPortV1:
    def __init__(
        self,
        *,
        dormant_coordinator: Any,
        maintenance_coordinator: Any,
        fail_phase: str | None = None,
    ) -> None:
        self.dormant_coordinator = dormant_coordinator
        self.maintenance_coordinator = maintenance_coordinator
        self.fail_phase = fail_phase
        self.current = dormant_coordinator
        self.mode = "DORMANT"
        self.generation = 7
        self.process_boot_epoch_sha256 = "f" * 64
        self.runtime_started = False
        self.workers_started = False
        self.server_accepting_requests = False
        self.writer_invocations_seen = 0
        self.cas_count = 0
        self.rollback_count = 0
        self.writer_attempts: list[dict[str, Any]] = []
        self.events: list[str] = []

    def _fails(self, phase: str) -> bool:
        return phase in str(self.fail_phase or "").split("+")

    def _identity_sha(self, coordinator: Any) -> str:
        if coordinator is self.dormant_coordinator:
            return "d" * 64
        if coordinator is self.maintenance_coordinator:
            return "e" * 64
        return "0" * 64

    def snapshot_installation_state(self) -> dict[str, Any]:
        self.events.append("seam_snapshot")
        runtime_started = self.runtime_started or self._fails("runtime_started")
        workers_started = self.workers_started or self._fails("workers_started")
        serving = self.server_accepting_requests or self._fails("server_started")
        writer_count = self.writer_invocations_seen
        if self._fails("writer_seen_before_startup") and self.mode == "DORMANT":
            writer_count = 1
        mutations_allowed = self.mode == "DORMANT"
        if self._fails("postcondition_writer_allowed") and self.mode == "MAINTENANCE_ONLY":
            mutations_allowed = True
        return {
            "mode": self.mode,
            "startup_phase": "PRE_RUNTIME",
            "runtime_started": runtime_started,
            "workers_started": workers_started,
            "server_accepting_requests": serving,
            "writer_invocations_seen": writer_count,
            "generation": self.generation,
            "process_boot_epoch_sha256": self.process_boot_epoch_sha256,
            "current_coordinator_identity_sha256": self._identity_sha(self.current),
            "writer_mutations_allowed": mutations_allowed,
            "runtime_activation_allowed": False,
            "synthetic_only": True,
            "runtime_integrated": False,
        }

    def current_coordinator(self) -> Any:
        self.events.append("seam_current_coordinator")
        return self.current

    def compare_and_swap_coordinator(
        self,
        *,
        expected_generation: int,
        expected_coordinator: Any,
        replacement_coordinator: Any,
        replacement_mode: str,
    ) -> dict[str, Any]:
        self.events.append(f"seam_cas_{replacement_mode.lower()}")
        if replacement_mode == "DORMANT":
            self.rollback_count += 1
            if self._fails("rollback_failed"):
                raise RuntimeError("synthetic rollback failed")
        else:
            self.cas_count += 1
            if self._fails("cas_failed"):
                raise RuntimeError("synthetic CAS failed")
        if self.generation != expected_generation or self.current is not expected_coordinator:
            raise RuntimeError("synthetic CAS mismatch")
        before = self.generation
        self.current = replacement_coordinator
        self.mode = replacement_mode
        self.generation += 1
        receipt = {
            "ok": True,
            "status": "SYNTHETIC_SEAM_COORDINATOR_CAS_COMMITTED",
            "generation_before": before,
            "generation_after": self.generation,
            "mode_after": replacement_mode,
            "runtime_started": False,
            "writer_mutations_allowed": replacement_mode == "DORMANT",
            "runtime_activation_allowed": False,
            "synthetic_only": True,
            "write_executed": False,
            "registry_write": False,
        }
        if self._fails("receipt_corrupt") and replacement_mode == "MAINTENANCE_ONLY":
            receipt["generation_after"] += 1
        receipt["receipt_sha256"] = _sha(receipt)
        return receipt

    def attempt_writer(self, writer_id: str) -> dict[str, Any]:
        self.writer_invocations_seen += 1
        allowed = self.mode != "MAINTENANCE_ONLY"
        result = {
            "writer_id": str(writer_id),
            "allowed": allowed,
            "mode": self.mode,
            "runtime_activation_allowed": False,
        }
        self.writer_attempts.append(result)
        return result


def build_synthetic_startup_only_seam_installation_v1(
    *,
    fail_phase: str | None = None,
    installer_enabled: bool = True,
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
    seam = SyntheticStartupOnlySeamPortV1(
        dormant_coordinator=dormant,
        maintenance_coordinator=environment.coordinator,
        fail_phase=fail_phase,
    )
    startup_state = seam.snapshot_installation_state()
    storage = physical_adapter.storage_readiness()
    installation_request = {
        "ack": contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_ACK_V1,
        "scope_attestation": contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
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
        contract.startup_only_seam_installation_request_sha256_v1(
            installation_request
        )
    )
    installer = contract.PrebootstrapStartupOnlySeamInstallationContractV1(
        seam_port=seam,
        dormant_coordinator=dormant,
        maintenance_coordinator=environment.coordinator,
        maintenance_coordinator_port=physical_adapter,
        trading_controls=environment.trading_controls,
        config=contract.PrebootstrapStartupOnlySeamInstallationConfigV1(
            enabled=installer_enabled,
            scope_attestation=(
                contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1
                if installer_enabled
                else None
            ),
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
        "seam": seam,
        "installer": installer,
        "installation_request": installation_request,
    }


def run_synthetic_startup_only_seam_installation_v1() -> dict[str, Any]:
    values = build_synthetic_startup_only_seam_installation_v1()
    seam = values["seam"]
    installer = values["installer"]
    with installer.maintenance_only_installation(
        values["installation_request"]
    ) as permit:
        installed_state = seam.snapshot_installation_state()
        writer_attempt = seam.attempt_writer("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP")
        bridge_result = values["composed"].run_offline(values["bridge_request"])
        active = {
            "permit_mode": permit.mode,
            "installed_state": installed_state,
            "writer_attempt": writer_attempt,
            "bridge_result": bridge_result,
        }
    restored = seam.snapshot_installation_state()
    return {
        "ok": bool(
            active["bridge_result"].get("ok") is True
            and active["writer_attempt"].get("allowed") is False
            and active["installed_state"].get("mode") == "MAINTENANCE_ONLY"
            and restored.get("mode") == "DORMANT"
            and seam.current_coordinator() is values["dormant_coordinator"]
        ),
        "status": "C3_PREBOOTSTRAP_STARTUP_ONLY_SEAM_REHEARSAL_VERIFIED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_HARNESS_V1_VERSION,
        "active": active,
        "restored_state": restored,
        "cas_count": seam.cas_count,
        "rollback_count": seam.rollback_count,
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
    "SyntheticStartupOnlySeamPortV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_HARNESS_V1_VERSION",
    "build_synthetic_startup_only_seam_installation_v1",
    "run_synthetic_startup_only_seam_installation_v1",
]
