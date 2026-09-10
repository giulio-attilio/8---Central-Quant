"""In-memory harness for the dormant production startup port binding."""

from __future__ import annotations

import hashlib
import threading
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-PORT-BINDING-ADAPTER-HARNESS-V1"
)


class CountingProductionRuntimeStartupPortsV1:
    def __init__(self) -> None:
        self.atomic_lock = threading.RLock()
        self.calls = {
            "trading_controls": 0,
            "startup_state": 0,
            "seam_binding_evidence": 0,
            "maintenance_completion_evidence": 0,
            "production_evidence_verifier": 0,
            "startup_callback": 0,
        }
        self.authority_root_sha256 = hashlib.sha256(
            b"dormant-production-runtime-port-root"
        ).hexdigest()

    def trading_controls(self):
        self.calls["trading_controls"] += 1
        return {}

    def startup_state(self):
        self.calls["startup_state"] += 1
        return {}

    def seam_binding_evidence(self):
        self.calls["seam_binding_evidence"] += 1
        return {}

    def maintenance_completion_evidence(self):
        self.calls["maintenance_completion_evidence"] += 1
        return {}

    def production_evidence_verifier(self, evidence, evidence_sha256):
        self.calls["production_evidence_verifier"] += 1
        return {}

    def startup_callback(self, permit):
        self.calls["startup_callback"] += 1
        return {}


def build_dormant_production_startup_port_binding_adapter_v1(
    *, fail_phase: str | None = None
):
    phase = str(fail_phase or "")
    source = CountingProductionRuntimeStartupPortsV1()
    atomic_lock: Any = source.atomic_lock
    callback: Any = source.startup_callback
    authority_root = source.authority_root_sha256
    synthetic_only = False
    runtime_integrated = True
    if "invalid_atomic_lock" in phase.split("+"):
        atomic_lock = object()
    if "missing_callable" in phase.split("+"):
        callback = None
    if "invalid_authority_root" in phase.split("+"):
        authority_root = "invalid"
    if "authority_root_unconfigured" in phase.split("+"):
        authority_root = None
    if "synthetic_ports" in phase.split("+"):
        synthetic_only = True
    if "runtime_binding_missing" in phase.split("+"):
        runtime_integrated = False
    ports = contract.RuntimeProductionStartupPortsV1(
        atomic_lock=atomic_lock,
        trading_controls=source.trading_controls,
        startup_state=source.startup_state,
        seam_binding_evidence=source.seam_binding_evidence,
        maintenance_completion_evidence=source.maintenance_completion_evidence,
        production_evidence_verifier=source.production_evidence_verifier,
        startup_callback=callback,
        authority_root_sha256=authority_root,
        synthetic_only=synthetic_only,
        runtime_integrated=runtime_integrated,
    )
    ports_identity = contract.runtime_production_startup_ports_identity_sha256_v1(
        ports
    )
    if "ports_identity_mismatch" in phase.split("+"):
        ports_identity = "0" * 64
    adapter = contract.RuntimeProductionStartupPortBindingAdapterContractV1(
        ports=ports,
        config=contract.RuntimeProductionStartupPortBindingAdapterConfigV1(
            enabled="adapter_enabled" in phase.split("+"),
            dormant_only="dormant_only_disabled" not in phase.split("+"),
            scope_attestation=(
                "invalid-scope"
                if "scope_invalid" in phase.split("+")
                else contract.RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_ATTESTATION_V1
            ),
            expected_ports_identity_sha256=ports_identity,
        ),
    )
    return adapter, ports, source


def run_dormant_production_startup_port_binding_adapter_v1(
    *, fail_phase: str | None = None
) -> dict[str, Any]:
    adapter, ports, source = build_dormant_production_startup_port_binding_adapter_v1(
        fail_phase=fail_phase
    )
    result = {
        "ok": False,
        "status": "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_HARNESS_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_HARNESS_V1_VERSION,
        "reason": None,
        "provider_calls": dict(source.calls),
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
        binding = adapter.bind_dormant()
    except Exception as exc:
        result["reason"] = getattr(exc, "reason", str(exc) or type(exc).__name__)
        result["provider_calls"] = dict(source.calls)
        return result
    result.update(
        ok=True,
        status="C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_HARNESS_VERIFIED",
        reason=None,
        adapter_snapshot=adapter.snapshot(),
        binding_snapshot=binding.snapshot(),
        gate_snapshot=binding.gate.snapshot(),
        composition_snapshot=binding.composition.snapshot(),
        provider_calls=dict(source.calls),
        ports_protected_repr=repr(ports),
        binding_protected_repr=repr(binding),
    )
    return result


__all__ = [
    "CountingProductionRuntimeStartupPortsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_HARNESS_V1_VERSION",
    "build_dormant_production_startup_port_binding_adapter_v1",
    "run_dormant_production_startup_port_binding_adapter_v1",
]
