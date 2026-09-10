"""Dormant binding adapter for production C3 runtime startup ports.

The adapter binds exact injected port instances to a disabled admission gate
and a disabled startup composition.  Binding performs no provider call, I/O,
Registry access or runtime startup and exposes no activation method.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as composition_contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-PORT-BINDING-ADAPTER-CONTRACT-V1"
)
RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_DORMANT_PRODUCTION_STARTUP_PORT_BINDING_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower().strip()
    return candidate if _SHA256_RE.fullmatch(candidate) else None


def runtime_production_startup_ports_identity_sha256_v1(ports: Any) -> str:
    if type(ports) is not RuntimeProductionStartupPortsV1:
        raise TypeError("exact runtime production startup ports are required")
    material = (
        f"{type(ports).__module__}:{type(ports).__qualname__}:{id(ports)}:"
        f"{id(ports.atomic_lock)}"
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class RuntimeProductionStartupPortBindingBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True, repr=False)
class RuntimeProductionStartupPortsV1:
    atomic_lock: Any = field(repr=False)
    trading_controls: Any = field(repr=False)
    startup_state: Any = field(repr=False)
    seam_binding_evidence: Any = field(repr=False)
    maintenance_completion_evidence: Any = field(repr=False)
    production_evidence_verifier: Any = field(repr=False)
    startup_callback: Any = field(repr=False)
    authority_root_sha256: str | None = field(default=None, repr=False)
    synthetic_only: bool = False
    runtime_integrated: bool = True

    def __repr__(self) -> str:
        return "<RuntimeProductionStartupPortsV1 protected>"


@dataclass(frozen=True)
class RuntimeProductionStartupPortBindingAdapterConfigV1:
    enabled: bool = False
    dormant_only: bool = True
    scope_attestation: str | None = field(default=None, repr=False)
    expected_ports_identity_sha256: str | None = field(default=None, repr=False)


class DormantRuntimeProductionStartupPortBindingV1:
    def __init__(
        self,
        *,
        ports: RuntimeProductionStartupPortsV1,
        gate: gate_contract.RuntimeStartupAdmissionGateContractV1,
        composition: composition_contract.RuntimeProductionStartupCompositionContractV1,
    ) -> None:
        self._ports = ports
        self._gate = gate
        self._composition = composition

    def __repr__(self) -> str:
        return "<DormantRuntimeProductionStartupPortBindingV1 protected>"

    @property
    def gate(self) -> gate_contract.RuntimeStartupAdmissionGateContractV1:
        return self._gate

    @property
    def composition(
        self,
    ) -> composition_contract.RuntimeProductionStartupCompositionContractV1:
        return self._composition

    def gate_identity_sha256_v1(self) -> str:
        """Return the public process-local identity of the bound gate."""

        return composition_contract.production_startup_composition_dependency_identity_sha256_v1(
            self._gate
        )

    def source_identity_sha256_v1(self, source_name: str) -> str:
        """Return one bound source identity without exposing protected ports."""

        sources = {
            "startup_state": self._ports.startup_state,
            "seam_binding": self._ports.seam_binding_evidence,
            "maintenance_completion": self._ports.maintenance_completion_evidence,
            "evidence_verifier": self._ports.production_evidence_verifier,
            "startup_callback": self._ports.startup_callback,
        }
        if source_name not in sources:
            raise KeyError("unknown runtime production startup source")
        return composition_contract.production_startup_composition_dependency_identity_sha256_v1(
            sources[source_name]
        )

    def snapshot(self) -> dict[str, Any]:
        gate_snapshot = self._gate.snapshot()
        composition_snapshot = self._composition.snapshot()
        same_lock = bool(
            getattr(self._gate, "_lock", None) is self._ports.atomic_lock
            and getattr(self._composition, "_lock", None) is self._ports.atomic_lock
        )
        return {
            "ok": bool(
                gate_snapshot.get("default_off") is True
                and composition_snapshot.get("default_off") is True
                and same_lock
            ),
            "status": "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_BOUND_DORMANT",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_CONTRACT_V1_VERSION,
            "ports_instance_bound": True,
            "same_atomic_lock": same_lock,
            "gate_default_off": gate_snapshot.get("default_off") is True,
            "composition_default_off": composition_snapshot.get("default_off") is True,
            "production_authority_configured": bool(
                _valid_sha256(self._ports.authority_root_sha256)
            ),
            "activation_possible": False,
            "providers_invoked": False,
            "startup_callback_invoked": False,
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


class RuntimeProductionStartupPortBindingAdapterContractV1:
    """Create one immutable dormant binding without invoking any source port."""

    def __init__(
        self,
        *,
        ports: RuntimeProductionStartupPortsV1,
        config: RuntimeProductionStartupPortBindingAdapterConfigV1 | None = None,
    ) -> None:
        if type(ports) is not RuntimeProductionStartupPortsV1:
            raise TypeError("exact runtime production startup ports are required")
        self._ports = ports
        self._config = config or RuntimeProductionStartupPortBindingAdapterConfigV1()
        self._binding: DormantRuntimeProductionStartupPortBindingV1 | None = None

    def __repr__(self) -> str:
        return "<RuntimeProductionStartupPortBindingAdapterContractV1 protected>"

    def _reason(self) -> str | None:
        if self._config.enabled is not False or self._config.dormant_only is not True:
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_MUST_REMAIN_DORMANT"
        if (
            self._config.scope_attestation
            != RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_ATTESTATION_V1
        ):
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_REQUIRED"
        expected = _valid_sha256(self._config.expected_ports_identity_sha256)
        if not expected:
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_IDENTITY_REQUIRED"
        try:
            actual = runtime_production_startup_ports_identity_sha256_v1(self._ports)
        except TypeError:
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_IDENTITY_INVALID"
        if not hmac.compare_digest(expected, actual):
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_IDENTITY_MISMATCH"
        if self._ports.synthetic_only is not False:
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_SYNTHETIC_FORBIDDEN"
        if self._ports.runtime_integrated is not True:
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORTS_RUNTIME_BINDING_REQUIRED"
        required_callables = (
            self._ports.trading_controls,
            self._ports.startup_state,
            self._ports.seam_binding_evidence,
            self._ports.maintenance_completion_evidence,
            self._ports.production_evidence_verifier,
            self._ports.startup_callback,
        )
        if not all(callable(value) for value in required_callables):
            return "C3_RUNTIME_PRODUCTION_STARTUP_PORT_CALLABLES_REQUIRED"
        if self._ports.atomic_lock is None or not all(
            callable(getattr(self._ports.atomic_lock, name, None))
            for name in ("__enter__", "__exit__")
        ):
            return "C3_RUNTIME_PRODUCTION_STARTUP_ATOMIC_LOCK_REQUIRED"
        if self._ports.authority_root_sha256 not in (None, "") and not _valid_sha256(
            self._ports.authority_root_sha256
        ):
            return "C3_RUNTIME_PRODUCTION_STARTUP_AUTHORITY_ROOT_INVALID"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        return {
            "ok": reason is None,
            "status": (
                "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_DORMANT_READY"
                if reason is None
                else "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_BLOCKED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_CONTRACT_V1_VERSION,
            "reason": reason,
            "enabled": False,
            "default_off": True,
            "dormant_only": True,
            "binding_created": self._binding is not None,
            "providers_invoked": False,
            "production_authority_configured": bool(
                _valid_sha256(self._ports.authority_root_sha256)
            ),
            "activation_possible": False,
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

    def bind_dormant(self) -> DormantRuntimeProductionStartupPortBindingV1:
        reason = self._reason()
        if reason is not None:
            raise RuntimeProductionStartupPortBindingBlocked(reason)
        if self._binding is not None:
            raise RuntimeProductionStartupPortBindingBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_REPLAY_BLOCKED"
            )
        verifier_identity = (
            gate_contract.production_evidence_verifier_identity_sha256_v1(
                self._ports.production_evidence_verifier
            )
        )
        gate = gate_contract.RuntimeStartupAdmissionGateContractV1(
            startup_state=self._ports.startup_state,
            production_evidence_verifier=self._ports.production_evidence_verifier,
            atomic_lock=self._ports.atomic_lock,
            config=gate_contract.RuntimeStartupAdmissionGateConfigV1(
                enabled=False,
                scope_attestation=None,
                expected_authority_root_sha256=self._ports.authority_root_sha256,
                expected_verifier_identity_sha256=verifier_identity,
            ),
        )
        identities = {
            "gate": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                gate
            ),
            "trading_controls": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._ports.trading_controls
            ),
            "startup_state": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._ports.startup_state
            ),
            "seam_binding": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._ports.seam_binding_evidence
            ),
            "maintenance_completion": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._ports.maintenance_completion_evidence
            ),
            "startup_callback": composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._ports.startup_callback
            ),
        }
        composition = (
            composition_contract.RuntimeProductionStartupCompositionContractV1(
                gate=gate,
                atomic_lock=self._ports.atomic_lock,
                trading_controls=self._ports.trading_controls,
                startup_state=self._ports.startup_state,
                seam_binding_evidence=self._ports.seam_binding_evidence,
                maintenance_completion_evidence=self._ports.maintenance_completion_evidence,
                startup_callback=self._ports.startup_callback,
                config=composition_contract.RuntimeProductionStartupCompositionConfigV1(
                    enabled=False,
                    scope_attestation=None,
                    offline_rehearsal_only=True,
                    expected_gate_identity_sha256=identities["gate"],
                    expected_trading_controls_identity_sha256=identities[
                        "trading_controls"
                    ],
                    expected_startup_state_identity_sha256=identities[
                        "startup_state"
                    ],
                    expected_seam_binding_identity_sha256=identities[
                        "seam_binding"
                    ],
                    expected_maintenance_completion_identity_sha256=identities[
                        "maintenance_completion"
                    ],
                    expected_startup_callback_identity_sha256=identities[
                        "startup_callback"
                    ],
                ),
            )
        )
        binding = DormantRuntimeProductionStartupPortBindingV1(
            ports=self._ports,
            gate=gate,
            composition=composition,
        )
        if binding.snapshot().get("ok") is not True:
            raise RuntimeProductionStartupPortBindingBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_POSTCONDITION_FAILED"
            )
        self._binding = binding
        return binding


__all__ = [
    "DormantRuntimeProductionStartupPortBindingV1",
    "RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_SCOPE_ATTESTATION_V1",
    "RuntimeProductionStartupPortBindingAdapterConfigV1",
    "RuntimeProductionStartupPortBindingAdapterContractV1",
    "RuntimeProductionStartupPortBindingBlocked",
    "RuntimeProductionStartupPortsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_BINDING_ADAPTER_CONTRACT_V1_VERSION",
    "runtime_production_startup_ports_identity_sha256_v1",
]
