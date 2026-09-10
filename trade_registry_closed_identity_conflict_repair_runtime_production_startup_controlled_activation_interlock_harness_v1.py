"""In-memory harness for the C3 startup controlled-activation interlock."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_harness_v1 as upstream_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as identity_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_controlled_activation_interlock_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_harness_v1 as binding_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_contract_v1 as sources_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-CONTROLLED-ACTIVATION-INTERLOCK-HARNESS-V1"
)


def _source_config(source: Any, *, enabled: bool = True):
    return sources_contract.RuntimeProductionStartupPortSourceConfigV1(
        enabled=enabled,
        scope_attestation=(
            sources_contract.RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_SCOPE_ATTESTATION_V1
            if enabled
            else None
        ),
        expected_source_identity_sha256=identity_contract.production_startup_composition_dependency_identity_sha256_v1(
            source
        ),
    )


@lru_cache(maxsize=1)
def _valid_upstream_activation_result_v1():
    root = Path(__file__).resolve().parent
    result = upstream_harness.run_synthetic_c3_controlled_activation_harness_v1(root)
    return copy.deepcopy(result["activation_result"])


def build_offline_startup_controlled_activation_interlock_v1(
    *, fail_phase: str | None = None
):
    phase = str(fail_phase or "")
    binding_adapter, ports, source = (
        binding_harness.build_dormant_production_startup_port_binding_adapter_v1()
    )
    binding = binding_adapter.bind_dormant()
    source_enabled = "source_adapter_default_off" not in phase.split("+")
    startup_source = ports.startup_state
    if "source_cross_binding_mismatch" in phase.split("+"):
        replacement = binding_harness.CountingProductionRuntimeStartupPortsV1()
        startup_source = replacement.startup_state
    adapters = {
        "startup_state": sources_contract.ProductionStartupStatePortAdapterV1(
            startup_source,
            _source_config(startup_source, enabled=source_enabled),
        ),
        "seam_binding": sources_contract.ProductionSeamBindingPortAdapterV1(
            ports.seam_binding_evidence,
            _source_config(ports.seam_binding_evidence),
        ),
        "maintenance_completion": sources_contract.ProductionMaintenanceCompletionPortAdapterV1(
            ports.maintenance_completion_evidence,
            _source_config(ports.maintenance_completion_evidence),
        ),
        "evidence_verifier": sources_contract.ProductionEvidenceVerifierPortAdapterV1(
            ports.production_evidence_verifier,
            authority_root_sha256=ports.authority_root_sha256 or "",
            config=_source_config(ports.production_evidence_verifier),
        ),
        "startup_callback": sources_contract.PermitBoundRuntimeStartupCallbackAdapterV1(
            ports.startup_callback,
            gate=binding.gate,
            atomic_lock=ports.atomic_lock,
            config=_source_config(ports.startup_callback),
        ),
    }
    if "callback_gate_mismatch" in phase.split("+"):
        adapters["startup_callback"]._gate = object()
    binding_identity = identity_contract.production_startup_composition_dependency_identity_sha256_v1(
        binding
    )
    source_identities = {
        name: identity_contract.production_startup_composition_dependency_identity_sha256_v1(
            adapter
        )
        for name, adapter in adapters.items()
    }
    if "binding_identity_mismatch" in phase.split("+"):
        binding_identity = "0" * 64
    if "source_identity_mismatch" in phase.split("+"):
        source_identities["maintenance_completion"] = "0" * 64
    enabled = "interlock_default_off" not in phase.split("+")
    interlock = contract.RuntimeProductionStartupControlledActivationInterlockContractV1(
        dormant_binding=binding,
        source_adapters=adapters,
        config=contract.RuntimeProductionStartupControlledActivationInterlockConfigV1(
            enabled=enabled,
            scope_attestation=(
                contract.RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_SCOPE_ATTESTATION_V1
                if enabled
                else None
            ),
            expected_binding_identity_sha256=binding_identity,
            expected_source_adapter_identities=source_identities,
        ),
    )
    upstream = copy.deepcopy(_valid_upstream_activation_result_v1())
    if "upstream_tampered" in phase.split("+"):
        upstream["live_allowed"] = True
    return interlock, binding, adapters, source, upstream


def run_offline_startup_controlled_activation_interlock_v1(
    *, fail_phase: str | None = None
) -> dict[str, Any]:
    interlock, binding, adapters, source, upstream = (
        build_offline_startup_controlled_activation_interlock_v1(
            fail_phase=fail_phase
        )
    )
    result = {
        "ok": False,
        "status": "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_HARNESS_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_HARNESS_V1_VERSION,
        "reason": None,
        "provider_calls": dict(source.calls),
        "apply_allowed": False,
        "gate_enable_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "order_submission_authorized": False,
        "runtime_integrated": False,
        "production_ready": False,
        "real_registry_accessed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }
    try:
        receipt = interlock.prepare_offline(upstream)
    except Exception as exc:
        result.update(
            reason=getattr(exc, "reason", str(exc) or type(exc).__name__),
            provider_calls=dict(source.calls),
        )
        return result
    result.update(
        ok=True,
        status="C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_HARNESS_VERIFIED",
        reason=None,
        receipt=receipt,
        interlock_snapshot=interlock.snapshot(),
        binding_snapshot=binding.snapshot(),
        source_adapter_snapshots={
            name: adapter.snapshot() for name, adapter in adapters.items()
        },
        provider_calls=dict(source.calls),
    )
    return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_HARNESS_V1_VERSION",
    "build_offline_startup_controlled_activation_interlock_v1",
    "run_offline_startup_controlled_activation_interlock_v1",
]
