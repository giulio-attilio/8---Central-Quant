"""In-memory harness for the default-off production startup composition."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-COMPOSITION-HARNESS-V1"
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


class DirectProductionShapedStartupAuthoritiesV1:
    """Synthetic authorities that emit final DTOs directly, without projection."""

    def __init__(self, *, fail_phase: str | None = None) -> None:
        self.fail_phase = str(fail_phase or "")
        self.atomic_lock = threading.RLock()
        self.authority_root_sha256 = hashlib.sha256(
            b"offline-direct-production-authority-root"
        ).hexdigest()
        self.process_boot_epoch_sha256 = hashlib.sha256(
            b"offline-direct-production-boot"
        ).hexdigest()
        self.state_reads = 0
        self.verifier_calls = 0
        self.callback_calls = 0
        self.simulated_runtime_started = False
        self.state = {
            "mode": "DORMANT",
            "startup_phase": "PRE_RUNTIME",
            "runtime_started": False,
            "workers_started": False,
            "server_accepting_requests": False,
            "writer_invocations_seen": 0,
            "generation": 4,
            "process_boot_epoch_sha256": self.process_boot_epoch_sha256,
            "current_coordinator_identity_sha256": hashlib.sha256(
                b"offline-direct-production-coordinator"
            ).hexdigest(),
            "writer_guard_bound": True,
            "writer_mutations_allowed": True,
            "runtime_activation_allowed": False,
            "synthetic_only": False,
            "runtime_integrated": True,
        }
        self.controls = copy.deepcopy(gate_contract._SAFE_TRADING_CONTROLS)
        self.seam_binding = {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BOUND_PRODUCTION",
            "writer_guard_bound": True,
            "same_atomic_lock": True,
            "registered_writer_count": 19,
            "all_writers_routed": True,
            "dynamic_at_invocation": True,
            "coordinator_restored": True,
            "generation_after": self.state["generation"],
            "binding_receipt_sha256": hashlib.sha256(
                b"offline-direct-production-seam-binding"
            ).hexdigest(),
            "synthetic_only": False,
            "runtime_integrated": True,
            "production_ready": True,
            "runtime_activation_allowed": False,
        }
        self.maintenance = {
            "ok": True,
            "status": "C3_PREBOOTSTRAP_MAINTENANCE_COMPLETED",
            "observation_verified": True,
            "repair_verified": True,
            "bootstrap_verified": True,
            "recovery_verified": True,
            "postflight_verified": True,
            "rollback_verified": True,
            "maintenance_lease_released": True,
            "unresolved_transactions_after": 0,
            "conflicts_remaining": 0,
            "registry_preservation_verified": True,
            "authority_commit_verified": True,
            "maintenance_epoch": 9,
            "source_registry_sha256": hashlib.sha256(
                b"offline-direct-production-source-registry"
            ).hexdigest(),
            "candidate_registry_sha256": hashlib.sha256(
                b"offline-direct-production-candidate-registry"
            ).hexdigest(),
            "completion_receipt_sha256": hashlib.sha256(
                b"offline-direct-production-maintenance-completion"
            ).hexdigest(),
            "real_registry_accessed": True,
            "write_executed": True,
            "registry_write": True,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": False,
            "runtime_integrated": True,
            "production_authority": True,
        }

    def _fails(self, name: str) -> bool:
        return name in self.fail_phase.split("+")

    def trading_controls(self) -> dict[str, Any]:
        if self._fails("controls_provider_failed"):
            raise RuntimeError("synthetic controls provider failure")
        value = copy.deepcopy(self.controls)
        if self._fails("unsafe_trading"):
            value["enable_real_trading"] = True
        return value

    def startup_state(self) -> dict[str, Any]:
        self.state_reads += 1
        if self._fails("state_provider_failed"):
            raise RuntimeError("synthetic startup-state provider failure")
        value = copy.deepcopy(self.state)
        if self._fails("state_drift") and self.state_reads >= 2:
            value["runtime_started"] = True
            value["startup_phase"] = "RUNTIME_STARTED"
        if self._fails("writer_seen"):
            value["writer_invocations_seen"] = 1
        return value

    def seam_binding_evidence(self) -> dict[str, Any]:
        if self._fails("seam_provider_failed"):
            raise RuntimeError("synthetic seam provider failure")
        value = copy.deepcopy(self.seam_binding)
        if self._fails("seam_incomplete"):
            value["all_writers_routed"] = False
        if self._fails("seam_generation_mismatch"):
            value["generation_after"] += 1
        return value

    def maintenance_completion_evidence(self) -> dict[str, Any]:
        if self._fails("maintenance_provider_failed"):
            raise RuntimeError("synthetic maintenance provider failure")
        value = copy.deepcopy(self.maintenance)
        if self._fails("maintenance_failed"):
            value["ok"] = False
        if self._fails("unresolved_transactions"):
            value["unresolved_transactions_after"] = 1
        if self._fails("conflicts_remaining"):
            value["conflicts_remaining"] = 1
        return value

    def verify_production_evidence(
        self, evidence: dict[str, Any], evidence_sha256: str
    ) -> dict[str, Any]:
        self.verifier_calls += 1
        if self._fails("verifier_failed"):
            raise RuntimeError("synthetic authority verifier failure")
        receipt = {
            "ok": not self._fails("authority_rejected"),
            "status": "C3_PRODUCTION_STARTUP_EVIDENCE_AUTHENTICATED",
            "evidence_sha256": evidence_sha256,
            "process_boot_epoch_sha256": evidence["startup_state"][
                "process_boot_epoch_sha256"
            ],
            "authority_root_sha256": self.authority_root_sha256,
            "authority_generation": 11,
            "signature_verified": not self._fails("signature_invalid"),
            "revocation_checked": True,
            "authority_revoked": self._fails("authority_revoked"),
            "freshness_verified": not self._fails("authority_stale"),
            "production_authority": True,
            "synthetic_only": False,
            "runtime_integrated": True,
        }
        receipt["receipt_sha256"] = _sha(receipt)
        if self._fails("authority_receipt_corrupt"):
            receipt["receipt_sha256"] = "0" * 64
        return receipt

    def rehearse_runtime_start(self, permit: Any) -> dict[str, Any]:
        self.callback_calls += 1
        if self._fails("callback_failed"):
            raise RuntimeError("synthetic startup callback failure")
        receipt = {
            "ok": True,
            "status": "C3_RUNTIME_STARTUP_CALLBACK_REHEARSED_OFFLINE",
            "startup_started": True,
            "runtime_activation_allowed": False,
            "live_allowed": False,
            "order_submission_authorized": False,
            "same_atomic_lock": True,
            "generation": permit.generation,
            "process_boot_epoch_sha256": permit.process_boot_epoch_sha256,
            "evidence_sha256": permit.evidence_sha256,
            "synthetic_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "no_order_sent": True,
        }
        if self._fails("callback_receipt_invalid"):
            receipt["live_allowed"] = True
            return receipt
        self.state["runtime_started"] = True
        self.state["startup_phase"] = "RUNTIME_STARTED"
        self.simulated_runtime_started = True
        return receipt


def build_offline_production_startup_composition_v1(
    *,
    fail_phase: str | None = None,
    composition_enabled: bool = True,
):
    environment = DirectProductionShapedStartupAuthoritiesV1(fail_phase=fail_phase)
    state_provider = environment.startup_state
    verifier = environment.verify_production_evidence
    gate = gate_contract.RuntimeStartupAdmissionGateContractV1(
        startup_state=state_provider,
        production_evidence_verifier=verifier,
        atomic_lock=environment.atomic_lock,
        config=gate_contract.RuntimeStartupAdmissionGateConfigV1(
            enabled=True,
            scope_attestation=gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
            expected_authority_root_sha256=environment.authority_root_sha256,
            expected_verifier_identity_sha256=gate_contract.production_evidence_verifier_identity_sha256_v1(
                verifier
            ),
        ),
    )
    controls_provider = environment.trading_controls
    seam_provider = environment.seam_binding_evidence
    maintenance_provider = environment.maintenance_completion_evidence
    callback = environment.rehearse_runtime_start
    dependencies = {
        "gate": gate,
        "trading_controls": controls_provider,
        "startup_state": state_provider,
        "seam_binding": seam_provider,
        "maintenance_completion": maintenance_provider,
        "startup_callback": callback,
    }
    identities = {
        name: contract.production_startup_composition_dependency_identity_sha256_v1(
            value
        )
        for name, value in dependencies.items()
    }
    if "dependency_pin_mismatch" in str(fail_phase or "").split("+"):
        identities["startup_callback"] = "0" * 64
    composition_lock = (
        threading.RLock()
        if "different_atomic_lock" in str(fail_phase or "").split("+")
        else environment.atomic_lock
    )
    composition = contract.RuntimeProductionStartupCompositionContractV1(
        gate=gate,
        atomic_lock=composition_lock,
        trading_controls=controls_provider,
        startup_state=state_provider,
        seam_binding_evidence=seam_provider,
        maintenance_completion_evidence=maintenance_provider,
        startup_callback=callback,
        config=contract.RuntimeProductionStartupCompositionConfigV1(
            enabled=composition_enabled,
            scope_attestation=(
                contract.RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_ATTESTATION_V1
                if composition_enabled
                else None
            ),
            offline_rehearsal_only=True,
            expected_gate_identity_sha256=identities["gate"],
            expected_trading_controls_identity_sha256=identities[
                "trading_controls"
            ],
            expected_startup_state_identity_sha256=identities["startup_state"],
            expected_seam_binding_identity_sha256=identities["seam_binding"],
            expected_maintenance_completion_identity_sha256=identities[
                "maintenance_completion"
            ],
            expected_startup_callback_identity_sha256=identities[
                "startup_callback"
            ],
        ),
    )
    return composition, environment, gate


def run_offline_production_startup_composition_v1(
    *, fail_phase: str | None = None, composition_enabled: bool = True
) -> dict[str, Any]:
    result = {
        "ok": False,
        "status": "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_HARNESS_V1_VERSION,
        "reason": None,
        "production_evidence_projected": False,
        "production_evidence_simulated": True,
        "simulated_runtime_started": False,
        "runtime_integrated": False,
        "production_ready": False,
        "live_allowed": False,
        "order_submission_authorized": False,
        "real_registry_accessed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }
    try:
        composition, environment, gate = build_offline_production_startup_composition_v1(
            fail_phase=fail_phase,
            composition_enabled=composition_enabled,
        )
        rehearsal = composition.rehearse_offline()
    except Exception as exc:
        result["reason"] = getattr(exc, "reason", str(exc) or type(exc).__name__)
        if "environment" in locals():
            result["simulated_runtime_started"] = (
                environment.simulated_runtime_started
            )
            result["callback_calls"] = environment.callback_calls
        return result
    result.update(
        ok=True,
        status="C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_HARNESS_VERIFIED",
        reason=None,
        rehearsal=rehearsal,
        composition_snapshot=composition.snapshot(),
        gate_snapshot=gate.snapshot(),
        simulated_runtime_started=environment.simulated_runtime_started,
        callback_calls=environment.callback_calls,
        verifier_calls=environment.verifier_calls,
    )
    return result


__all__ = [
    "DirectProductionShapedStartupAuthoritiesV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_HARNESS_V1_VERSION",
    "build_offline_production_startup_composition_v1",
    "run_offline_production_startup_composition_v1",
]
