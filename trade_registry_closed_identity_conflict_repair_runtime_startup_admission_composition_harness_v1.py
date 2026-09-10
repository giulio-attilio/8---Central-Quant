"""Final offline composition: real seam shape through simulated runtime start.

This harness imports the dormant runtime seam but never imports ``main``.  It
temporarily swaps only process-local objects, restores them in ``finally`` and
uses a clearly labelled production-shaped test double for the admission gate.
"""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_physical_coordinator_port_adapter_harness_v1 as physical_harness
import trade_registry_closed_identity_conflict_repair_prebootstrap_real_seam_cas_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_prebootstrap_startup_only_seam_installation_contract_v1 as installer_contract
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_harness_v1 as gate_harness
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_COMPOSITION_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-ADMISSION-COMPOSITION-HARNESS-V1"
)


def _sha(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        default=repr,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@contextmanager
def _isolated_runtime_seam_state_v1(dormant_coordinator: Any):
    with runtime_seam._prebootstrap_seam_atomic_lock:
        previous_coordinator = runtime_seam._coordinator
        previous_guard = runtime_seam._prebootstrap_writer_guard
        previous_activation = copy.deepcopy(runtime_seam._controlled_activation_state)
        runtime_seam._coordinator = dormant_coordinator
        runtime_seam._prebootstrap_writer_guard = None
        runtime_seam._reset_controlled_activation_state_v1()
    try:
        yield {
            "previous_coordinator": previous_coordinator,
            "previous_guard": previous_guard,
        }
    finally:
        with runtime_seam._prebootstrap_seam_atomic_lock:
            runtime_seam._coordinator = previous_coordinator
            runtime_seam._prebootstrap_writer_guard = previous_guard
            runtime_seam._controlled_activation_state.clear()
            runtime_seam._controlled_activation_state.update(previous_activation)


class OfflineFinalStartupStateAuthorityV1:
    def __init__(self, state: dict[str, Any], *, fail_phase: str | None = None):
        self.state = copy.deepcopy(state)
        self.fail_phase = str(fail_phase or "")
        self.read_count = 0
        self.simulated_runtime_started = False

    def _fails(self, phase: str) -> bool:
        return phase in self.fail_phase.split("+")

    def snapshot(self) -> dict[str, Any]:
        self.read_count += 1
        value = copy.deepcopy(self.state)
        if self._fails("state_drift") and self.read_count >= 2:
            value["runtime_started"] = True
            value["startup_phase"] = "RUNTIME_STARTED"
        return value

    def commit_simulated_runtime_start(self) -> None:
        self.state["runtime_started"] = True
        self.state["startup_phase"] = "RUNTIME_STARTED"
        self.simulated_runtime_started = True


def _build_installation_request(values, port):
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
    return request


def _project_production_shaped_gate_request(
    *,
    restored_state: dict[str, Any],
    binding_snapshot: dict[str, Any],
    bridge_result: dict[str, Any],
    verifier_environment: gate_harness.SyntheticProductionStartupEvidenceV1,
    fail_phase: str | None,
):
    projected = copy.deepcopy(restored_state)
    projected["writer_guard_bound"] = binding_snapshot.get("writer_guard_bound") is True
    projected["synthetic_only"] = False
    projected["runtime_integrated"] = True
    if "runtime_started" in str(fail_phase or "").split("+"):
        projected["runtime_started"] = True
        projected["startup_phase"] = "RUNTIME_STARTED"
    state_authority = OfflineFinalStartupStateAuthorityV1(
        projected, fail_phase=fail_phase
    )
    verifier_environment.state = copy.deepcopy(projected)
    request = gate_harness.build_production_shaped_startup_admission_request_v1(
        verifier_environment,
        fail_phase=(
            "maintenance_failed"
            if "maintenance_attestation_corrupt" in str(fail_phase or "").split("+")
            else None
        ),
    )
    bridge_receipt = bridge_result.get("receipt") or {}
    seam_binding = request["evidence"]["seam_binding"]
    seam_binding["generation_after"] = projected["generation"]
    seam_binding["binding_receipt_sha256"] = _sha(binding_snapshot)
    maintenance = request["evidence"]["maintenance_completion"]
    # The maintenance bridge uses a SHA-256 process epoch, while the startup
    # gate's production-shaped evidence contract uses a monotonic integer.
    # This harness deliberately projects the completed synthetic maintenance
    # cycle as epoch 1; the original bridge receipt remains bound into the
    # completion receipt hash below.
    maintenance["maintenance_epoch"] = 1
    maintenance["source_registry_sha256"] = str(
        bridge_receipt.get("source_registry_sha256") or "d" * 64
    )
    maintenance["candidate_registry_sha256"] = str(
        bridge_receipt.get("candidate_registry_sha256") or "e" * 64
    )
    maintenance["conflicts_remaining"] = int(
        bridge_result.get("conflict_count_after") or 0
    )
    maintenance["completion_receipt_sha256"] = _sha(
        {
            "bridge_receipt": bridge_receipt,
            "restored_state": restored_state,
            "binding_snapshot": binding_snapshot,
        }
    )
    request["request_sha256"] = (
        gate_contract.runtime_startup_admission_request_sha256_v1(request)
    )
    return state_authority, request


def run_final_offline_runtime_startup_admission_composition_v1(
    *, fail_phase: str | None = None
) -> dict[str, Any]:
    phase = str(fail_phase or "")
    physical = physical_harness.build_synthetic_physical_coordinator_composition_v1()
    values = {
        "composed": physical[0],
        "runtime_adapter": physical[1],
        "entrypoint": physical[2],
        "physical_adapter": physical[3],
        "environment": physical[4],
        "bridge_request": physical[5],
    }
    dormant = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
    verifier_phase = next(
        (
            item
            for item in (
                "authority_rejected",
                "signature_invalid",
                "authority_revoked",
                "authority_stale",
                "authority_receipt_corrupt",
                "verifier_failed",
            )
            if item in phase.split("+")
        ),
        None,
    )
    verifier_environment = gate_harness.SyntheticProductionStartupEvidenceV1(
        fail_phase=verifier_phase
    )
    result = {
        "ok": False,
        "status": "C3_RUNTIME_STARTUP_ADMISSION_COMPOSITION_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_COMPOSITION_HARNESS_V1_VERSION,
        "failed_stage": None,
        "reason": None,
        "production_evidence_simulated": True,
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
    with _isolated_runtime_seam_state_v1(dormant) as isolated:
        runtime_state = {
            "runtime_started": False,
            "workers_started": False,
            "server_accepting_requests": False,
        }
        surface = runtime_seam.C3PrebootstrapSeamCasSurfaceV1(
            runtime_seam.C3PrebootstrapSeamCasSurfaceConfigV1(
                enabled=True,
                scope_attestation=runtime_seam.C3_PREBOOTSTRAP_SEAM_CAS_SURFACE_SCOPE_ATTESTATION_V1,
                synthetic_only=True,
                runtime_integrated=False,
            )
        )
        boot_sha = hashlib.sha256(b"final-offline-composition-boot").hexdigest()
        adapter = adapter_contract.PrebootstrapRealSeamCasAdapterContractV1(
            seam_surface=surface,
            dormant_coordinator=dormant,
            maintenance_coordinator=values["environment"].coordinator,
            runtime_state=lambda: copy.deepcopy(runtime_state),
            config=adapter_contract.PrebootstrapRealSeamCasAdapterConfigV1(
                enabled=True,
                scope_attestation=adapter_contract.PREBOOTSTRAP_REAL_SEAM_CAS_ADAPTER_SCOPE_ATTESTATION_V1,
                process_boot_epoch_sha256=boot_sha,
            ),
        )
        try:
            binding = adapter.bind_offline()
            if "writer_before_maintenance" in phase.split("+"):
                with runtime_seam._c3_closed_repair_writer_mutation_v1(
                    "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
                ):
                    pass
            request = _build_installation_request(values, binding.port)
            installer = installer_contract.PrebootstrapStartupOnlySeamInstallationContractV1(
                seam_port=binding.port,
                dormant_coordinator=dormant,
                maintenance_coordinator=values["environment"].coordinator,
                maintenance_coordinator_port=values["physical_adapter"],
                trading_controls=values["environment"].trading_controls,
                config=installer_contract.PrebootstrapStartupOnlySeamInstallationConfigV1(
                    enabled=True,
                    scope_attestation=installer_contract.PREBOOTSTRAP_STARTUP_ONLY_SEAM_INSTALLATION_SCOPE_ATTESTATION_V1,
                ),
            )
            with installer.maintenance_only_installation(request):
                bridge_result = values["composed"].run_offline(
                    values["bridge_request"]
                )
                if "bridge_failed" in phase.split("+"):
                    bridge_result = {**bridge_result, "ok": False}
                if bridge_result.get("ok") is not True:
                    raise RuntimeError("C3_FINAL_COMPOSITION_MAINTENANCE_FAILED")
            if "writer_before_gate" in phase.split("+"):
                with runtime_seam._c3_closed_repair_writer_mutation_v1(
                    "TRADE_REGISTRY_UPDATE_OPEN_TRADE"
                ):
                    pass
            restored_state = binding.port.snapshot_installation_state()
            binding_snapshot = binding.binding_snapshot()
        except Exception as exc:
            result.update(
                failed_stage="MAINTENANCE_COMPOSITION",
                reason=getattr(exc, "reason", str(exc) or type(exc).__name__),
            )
            result["seam_restored_after_harness"] = (
                runtime_seam._coordinator is dormant
            )
            return result
        state_authority, gate_request = _project_production_shaped_gate_request(
            restored_state=restored_state,
            binding_snapshot=binding_snapshot,
            bridge_result=bridge_result,
            verifier_environment=verifier_environment,
            fail_phase=phase,
        )
        verifier_sha = gate_contract.production_evidence_verifier_identity_sha256_v1(
            verifier_environment.verify
        )
        gate = gate_contract.RuntimeStartupAdmissionGateContractV1(
            startup_state=state_authority.snapshot,
            production_evidence_verifier=verifier_environment.verify,
            atomic_lock=surface.atomic_lock,
            config=gate_contract.RuntimeStartupAdmissionGateConfigV1(
                enabled=True,
                scope_attestation=gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
                expected_authority_root_sha256=(
                    verifier_environment.authority_root_sha256
                ),
                expected_verifier_identity_sha256=verifier_sha,
            ),
        )
        try:
            with gate.startup_admission(gate_request) as permit:
                state_authority.commit_simulated_runtime_start()
        except Exception as exc:
            result.update(
                failed_stage="STARTUP_ADMISSION",
                reason=getattr(exc, "reason", str(exc) or type(exc).__name__),
                seam_restored_after_harness=(runtime_seam._coordinator is dormant),
                simulated_runtime_started=state_authority.simulated_runtime_started,
            )
            return result
        result.update(
            ok=True,
            status="C3_RUNTIME_STARTUP_ADMISSION_FINAL_OFFLINE_COMPOSITION_VERIFIED",
            failed_stage=None,
            reason=None,
            bridge_result=bridge_result,
            restored_state=restored_state,
            binding_snapshot=binding_snapshot,
            permit=permit,
            simulated_runtime_started=state_authority.simulated_runtime_started,
            seam_restored_before_simulated_start=(runtime_seam._coordinator is dormant),
            original_seam_coordinator_preserved=(
                isolated["previous_coordinator"] is not None
            ),
        )
        return result


__all__ = [
    "OfflineFinalStartupStateAuthorityV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_ADMISSION_COMPOSITION_HARNESS_V1_VERSION",
    "run_final_offline_runtime_startup_admission_composition_v1",
]
