"""In-memory harness for the C3 fail-closed runtime startup admission gate."""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-ADMISSION-GATE-HARNESS-V1"
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


class SyntheticProductionStartupEvidenceV1:
    def __init__(self, *, fail_phase: str | None = None) -> None:
        self.fail_phase = str(fail_phase or "")
        self.atomic_lock = threading.RLock()
        self.authority_root_sha256 = "a" * 64
        self.boot_sha256 = hashlib.sha256(b"synthetic-production-boot").hexdigest()
        self.state_reads = 0
        self.verifier_calls = 0
        self.runtime_started = False
        self.state = {
            "mode": "DORMANT",
            "startup_phase": "PRE_RUNTIME",
            "runtime_started": False,
            "workers_started": False,
            "server_accepting_requests": False,
            "writer_invocations_seen": 0,
            "generation": 2,
            "process_boot_epoch_sha256": self.boot_sha256,
            "current_coordinator_identity_sha256": "b" * 64,
            "writer_guard_bound": True,
            "writer_mutations_allowed": True,
            "runtime_activation_allowed": False,
            "synthetic_only": False,
            "runtime_integrated": True,
        }

    def _fails(self, phase: str) -> bool:
        return phase in self.fail_phase.split("+")

    def startup_state(self) -> dict[str, Any]:
        self.state_reads += 1
        if self._fails("state_read_failed"):
            raise RuntimeError("synthetic state read failure")
        value = copy.deepcopy(self.state)
        if self._fails("state_drift") and self.state_reads >= 2:
            value["runtime_started"] = True
            value["startup_phase"] = "RUNTIME_STARTED"
        return value

    def verify(self, evidence, evidence_sha256):
        self.verifier_calls += 1
        if self._fails("verifier_failed"):
            raise RuntimeError("synthetic verifier failure")
        receipt = {
            "ok": not self._fails("authority_rejected"),
            "status": "C3_PRODUCTION_STARTUP_EVIDENCE_AUTHENTICATED",
            "evidence_sha256": evidence_sha256,
            "process_boot_epoch_sha256": evidence["startup_state"][
                "process_boot_epoch_sha256"
            ],
            "authority_root_sha256": self.authority_root_sha256,
            "authority_generation": 7,
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

    def commit_simulated_runtime_start(self) -> None:
        self.runtime_started = True
        self.state["runtime_started"] = True
        self.state["startup_phase"] = "RUNTIME_STARTED"


def build_production_shaped_startup_admission_request_v1(
    environment: SyntheticProductionStartupEvidenceV1,
    *,
    fail_phase: str | None = None,
) -> dict[str, Any]:
    phase = str(fail_phase or "")
    startup_state = copy.deepcopy(environment.state)
    seam_binding = {
        "ok": True,
        "status": "C3_PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_BOUND_PRODUCTION",
        "writer_guard_bound": True,
        "same_atomic_lock": True,
        "registered_writer_count": 19,
        "all_writers_routed": True,
        "dynamic_at_invocation": True,
        "coordinator_restored": True,
        "generation_after": startup_state["generation"],
        "binding_receipt_sha256": "c" * 64,
        "synthetic_only": False,
        "runtime_integrated": True,
        "production_ready": True,
        "runtime_activation_allowed": False,
    }
    maintenance = {
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
        "maintenance_epoch": 3,
        "source_registry_sha256": "d" * 64,
        "candidate_registry_sha256": "e" * 64,
        "completion_receipt_sha256": "f" * 64,
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
    controls = copy.deepcopy(contract._SAFE_TRADING_CONTROLS)
    if "unsafe_trading" in phase.split("+"):
        controls["enable_real_trading"] = True
    if "writer_seen" in phase.split("+"):
        startup_state["writer_invocations_seen"] = 1
        environment.state["writer_invocations_seen"] = 1
    if "runtime_started" in phase.split("+"):
        startup_state["runtime_started"] = True
        startup_state["startup_phase"] = "RUNTIME_STARTED"
        environment.state.update(startup_state)
    if "guard_missing" in phase.split("+"):
        startup_state["writer_guard_bound"] = False
        environment.state["writer_guard_bound"] = False
    if "synthetic_state" in phase.split("+"):
        startup_state["synthetic_only"] = True
        startup_state["runtime_integrated"] = False
        environment.state.update(startup_state)
    if "seam_incomplete" in phase.split("+"):
        seam_binding["all_writers_routed"] = False
    if "generation_mismatch" in phase.split("+"):
        seam_binding["generation_after"] += 1
    if "maintenance_failed" in phase.split("+"):
        maintenance["ok"] = False
    if "unresolved_transactions" in phase.split("+"):
        maintenance["unresolved_transactions_after"] = 1
    if "conflict_remaining" in phase.split("+"):
        maintenance["conflicts_remaining"] = 1
    if "lease_not_released" in phase.split("+"):
        maintenance["maintenance_lease_released"] = False
    if "network_accessed" in phase.split("+"):
        maintenance["network_accessed"] = True
    if "order_sent" in phase.split("+"):
        maintenance["no_order_sent"] = False
    evidence = {
        "trading_controls": controls,
        "startup_state": startup_state,
        "seam_binding": seam_binding,
        "maintenance_completion": maintenance,
    }
    request = {
        "ack": contract.RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1,
        "scope_attestation": contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
        "evidence": evidence,
    }
    request["request_sha256"] = (
        contract.runtime_startup_admission_request_sha256_v1(request)
    )
    if "request_hash_corrupt" in phase.split("+"):
        request["request_sha256"] = "0" * 64
    return request


def build_synthetic_runtime_startup_admission_gate_v1(
    *, fail_phase: str | None = None, gate_enabled: bool = True
):
    environment = SyntheticProductionStartupEvidenceV1(fail_phase=fail_phase)
    request = build_production_shaped_startup_admission_request_v1(
        environment, fail_phase=fail_phase
    )
    verifier_sha = contract.production_evidence_verifier_identity_sha256_v1(
        environment.verify
    )
    gate = contract.RuntimeStartupAdmissionGateContractV1(
        startup_state=environment.startup_state,
        production_evidence_verifier=environment.verify,
        atomic_lock=environment.atomic_lock,
        config=contract.RuntimeStartupAdmissionGateConfigV1(
            enabled=gate_enabled,
            scope_attestation=(
                contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1
                if gate_enabled
                else None
            ),
            expected_authority_root_sha256=(
                environment.authority_root_sha256 if gate_enabled else None
            ),
            expected_verifier_identity_sha256=verifier_sha if gate_enabled else None,
        ),
    )
    return gate, environment, request


def run_synthetic_runtime_startup_admission_gate_v1() -> dict[str, Any]:
    gate, environment, request = build_synthetic_runtime_startup_admission_gate_v1()
    with gate.startup_admission(request) as permit:
        before_commit = copy.deepcopy(environment.state)
        environment.commit_simulated_runtime_start()
        active = gate.snapshot()
    return {
        "ok": bool(
            permit.startup_allowed is True
            and permit.runtime_activation_allowed is False
            and permit.live_allowed is False
            and permit.order_submission_authorized is False
            and permit.same_atomic_lock is True
            and before_commit.get("startup_phase") == "PRE_RUNTIME"
            and environment.runtime_started is True
            and active.get("active_admission") is True
            and gate.snapshot().get("active_admission") is False
        ),
        "status": "C3_RUNTIME_STARTUP_ADMISSION_GATE_REHEARSAL_VERIFIED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_HARNESS_V1_VERSION,
        "permit": permit,
        "state_before_commit": before_commit,
        "state_after_commit": copy.deepcopy(environment.state),
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


__all__ = [
    "SyntheticProductionStartupEvidenceV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_GATE_HARNESS_V1_VERSION",
    "build_production_shaped_startup_admission_request_v1",
    "build_synthetic_runtime_startup_admission_gate_v1",
    "run_synthetic_runtime_startup_admission_gate_v1",
]
