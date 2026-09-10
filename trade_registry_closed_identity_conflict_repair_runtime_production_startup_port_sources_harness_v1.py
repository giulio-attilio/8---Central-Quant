"""In-memory harness for the five production startup source adapters."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as composition_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_harness_v1 as composition_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-PORT-SOURCES-HARNESS-V1"
)


class SyntheticPermitBoundProductionStartupSourceV1:
    def __init__(self, *, fail_phase: str | None = None) -> None:
        self.fail_phase = str(fail_phase or "")
        self.calls = 0
        self.simulated_runtime_started = False

    def __call__(self, permit: Any) -> dict[str, Any]:
        self.calls += 1
        if "callback_failed" in self.fail_phase.split("+"):
            raise RuntimeError("synthetic production callback failure")
        value = {
            "ok": True,
            "status": "C3_RUNTIME_STARTUP_COMPLETED_UNDER_ADMISSION",
            "startup_started": True,
            "runtime_activation_allowed": False,
            "live_allowed": False,
            "order_submission_authorized": False,
            "same_atomic_lock": True,
            "generation": permit.generation,
            "process_boot_epoch_sha256": permit.process_boot_epoch_sha256,
            "evidence_sha256": permit.evidence_sha256,
            "synthetic_only": False,
            "runtime_integrated": True,
            "production_ready": True,
            "no_order_sent": True,
        }
        if "callback_receipt_invalid" in self.fail_phase.split("+"):
            value["order_submission_authorized"] = True
            return value
        self.simulated_runtime_started = True
        return value


def _config(source: Any, *, enabled: bool, pin_mismatch: bool = False):
    identity = (
        composition_contract.production_startup_composition_dependency_identity_sha256_v1(
            source
        )
    )
    if pin_mismatch:
        identity = "0" * 64
    return contract.RuntimeProductionStartupPortSourceConfigV1(
        enabled=enabled,
        scope_attestation=(
            contract.RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_SCOPE_ATTESTATION_V1
            if enabled
            else None
        ),
        expected_source_identity_sha256=identity,
    )


def build_offline_production_startup_port_sources_v1(
    *, fail_phase: str | None = None, adapters_enabled: bool = True
):
    phase = str(fail_phase or "")
    environment = composition_harness.DirectProductionShapedStartupAuthoritiesV1(
        fail_phase=phase
    )
    startup_source = environment.startup_state
    seam_source = environment.seam_binding_evidence
    maintenance_source = environment.maintenance_completion_evidence
    verifier_source = environment.verify_production_evidence
    callback_source = SyntheticPermitBoundProductionStartupSourceV1(fail_phase=phase)
    mismatched = "source_identity_mismatch" in phase.split("+")
    startup_adapter = contract.ProductionStartupStatePortAdapterV1(
        startup_source,
        _config(startup_source, enabled=adapters_enabled, pin_mismatch=mismatched),
    )
    seam_adapter = contract.ProductionSeamBindingPortAdapterV1(
        seam_source,
        _config(seam_source, enabled=adapters_enabled),
    )
    maintenance_adapter = contract.ProductionMaintenanceCompletionPortAdapterV1(
        maintenance_source,
        _config(maintenance_source, enabled=adapters_enabled),
    )
    verifier_adapter = contract.ProductionEvidenceVerifierPortAdapterV1(
        verifier_source,
        authority_root_sha256=environment.authority_root_sha256,
        config=_config(verifier_source, enabled=adapters_enabled),
    )
    verifier = verifier_adapter.verify
    state_reader = startup_adapter.read
    gate = gate_contract.RuntimeStartupAdmissionGateContractV1(
        startup_state=state_reader,
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
    callback_adapter = contract.PermitBoundRuntimeStartupCallbackAdapterV1(
        callback_source,
        gate=gate,
        atomic_lock=environment.atomic_lock,
        config=_config(callback_source, enabled=adapters_enabled),
    )
    return {
        "environment": environment,
        "startup_adapter": startup_adapter,
        "seam_adapter": seam_adapter,
        "maintenance_adapter": maintenance_adapter,
        "verifier_adapter": verifier_adapter,
        "callback_adapter": callback_adapter,
        "callback_source": callback_source,
        "gate": gate,
    }


def run_offline_production_startup_port_sources_v1(
    *, fail_phase: str | None = None, adapters_enabled: bool = True
) -> dict[str, Any]:
    values = build_offline_production_startup_port_sources_v1(
        fail_phase=fail_phase, adapters_enabled=adapters_enabled
    )
    result = {
        "ok": False,
        "status": "C3_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_HARNESS_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_HARNESS_V1_VERSION,
        "reason": None,
        "callback_calls": values["callback_source"].calls,
        "simulated_runtime_started": False,
        "production_evidence_simulated": True,
        "production_evidence_projected": False,
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
        startup = values["startup_adapter"].read()
        seam = values["seam_adapter"].read()
        maintenance = values["maintenance_adapter"].read()
        evidence = {
            "trading_controls": copy.deepcopy(gate_contract._SAFE_TRADING_CONTROLS),
            "startup_state": startup,
            "seam_binding": seam,
            "maintenance_completion": maintenance,
        }
        request = {
            "ack": gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1,
            "scope_attestation": gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
            "evidence": evidence,
        }
        request["request_sha256"] = (
            gate_contract.runtime_startup_admission_request_sha256_v1(request)
        )
        with values["gate"].startup_admission(request) as permit:
            callback_receipt = values["callback_adapter"].start(permit)
    except Exception as exc:
        result.update(
            reason=getattr(exc, "reason", str(exc) or type(exc).__name__),
            callback_calls=values["callback_source"].calls,
            simulated_runtime_started=values[
                "callback_source"
            ].simulated_runtime_started,
        )
        return result
    result.update(
        ok=True,
        status="C3_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_HARNESS_VERIFIED",
        reason=None,
        callback_receipt=callback_receipt,
        callback_calls=values["callback_source"].calls,
        simulated_runtime_started=values["callback_source"].simulated_runtime_started,
        adapter_snapshots={
            name: values[name].snapshot()
            for name in (
                "startup_adapter",
                "seam_adapter",
                "maintenance_adapter",
                "verifier_adapter",
                "callback_adapter",
            )
        },
    )
    return result


__all__ = [
    "SyntheticPermitBoundProductionStartupSourceV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_HARNESS_V1_VERSION",
    "build_offline_production_startup_port_sources_v1",
    "run_offline_production_startup_port_sources_v1",
]
