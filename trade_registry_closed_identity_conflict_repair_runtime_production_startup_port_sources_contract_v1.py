"""Default-off source adapters for the five missing C3 startup runtime ports.

Every adapter receives one injected source, pins its exact process-local
identity and validates the final DTO without projecting fields.  Defaults are
dormant and no adapter imports or discovers the runtime on its own.
"""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as composition_contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-PORT-SOURCES-CONTRACT-V1"
)
RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PRODUCTION_STARTUP_PORT_SOURCE_V1"
)

_PRODUCTION_CALLBACK_RECEIPT_KEYS = frozenset(
    {
        "ok",
        "status",
        "startup_started",
        "runtime_activation_allowed",
        "live_allowed",
        "order_submission_authorized",
        "same_atomic_lock",
        "generation",
        "process_boot_epoch_sha256",
        "evidence_sha256",
        "synthetic_only",
        "runtime_integrated",
        "production_ready",
        "no_order_sent",
    }
)


class RuntimeProductionStartupPortSourceBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class RuntimeProductionStartupPortSourceConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_source_identity_sha256: str | None = field(default=None, repr=False)


class _PinnedProductionStartupSourceV1:
    adapter_name = "UNSPECIFIED"

    def __init__(self, source: Any, config: RuntimeProductionStartupPortSourceConfigV1 | None):
        if not callable(source):
            raise TypeError("one callable source is required")
        self._source = source
        self._config = config or RuntimeProductionStartupPortSourceConfigV1()

    def _reason(self) -> str | None:
        if self._config.enabled is not True:
            return f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_SCOPE_ATTESTATION_V1
        ):
            return f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_SCOPE_INVALID"
        expected = self._config.expected_source_identity_sha256
        try:
            actual = composition_contract.production_startup_composition_dependency_identity_sha256_v1(
                self._source
            )
        except TypeError:
            return f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_IDENTITY_INVALID"
        if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
            return f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_IDENTITY_MISMATCH"
        return None

    def _require_enabled(self) -> None:
        reason = self._reason()
        if reason is not None:
            raise RuntimeProductionStartupPortSourceBlocked(reason)

    def bound_source_identity_sha256_v1(self) -> str:
        """Return the public identity of the exact callable held by the adapter."""

        return composition_contract.production_startup_composition_dependency_identity_sha256_v1(
            self._source
        )

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        return {
            "ok": reason is None,
            "status": (
                f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_OFFLINE_READY"
                if reason is None
                else f"C3_RUNTIME_PRODUCTION_{self.adapter_name}_SOURCE_DORMANT"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_CONTRACT_V1_VERSION,
            "enabled": reason is None,
            "default_off": reason is not None,
            "source_instance_bound": reason is None,
            "offline_harness_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "live_allowed": False,
            "order_submission_authorized": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


class ProductionStartupStatePortAdapterV1(_PinnedProductionStartupSourceV1):
    adapter_name = "STARTUP_STATE"

    def __repr__(self) -> str:
        return "<ProductionStartupStatePortAdapterV1 protected>"

    def read(self) -> dict[str, Any]:
        self._require_enabled()
        try:
            value = copy.deepcopy(dict(self._source()))
        except Exception as exc:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_STATE_SOURCE_READ_FAILED"
            ) from exc
        if not gate_contract.RuntimeStartupAdmissionGateContractV1._startup_state_safe(
            value
        ):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_STATE_SOURCE_UNSAFE"
            )
        return value


class ProductionSeamBindingPortAdapterV1(_PinnedProductionStartupSourceV1):
    adapter_name = "SEAM_BINDING"

    def __repr__(self) -> str:
        return "<ProductionSeamBindingPortAdapterV1 protected>"

    def read(self) -> dict[str, Any]:
        self._require_enabled()
        try:
            value = copy.deepcopy(dict(self._source()))
        except Exception as exc:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_SEAM_BINDING_SOURCE_READ_FAILED"
            ) from exc
        startup_generation = {"generation": value.get("generation_after")}
        if not gate_contract.RuntimeStartupAdmissionGateContractV1._seam_binding_safe(
            value, startup_generation
        ):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_SEAM_BINDING_SOURCE_UNSAFE"
            )
        return value


class ProductionMaintenanceCompletionPortAdapterV1(
    _PinnedProductionStartupSourceV1
):
    adapter_name = "MAINTENANCE_COMPLETION"

    def __repr__(self) -> str:
        return "<ProductionMaintenanceCompletionPortAdapterV1 protected>"

    def read(self) -> dict[str, Any]:
        self._require_enabled()
        try:
            value = copy.deepcopy(dict(self._source()))
        except Exception as exc:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_MAINTENANCE_COMPLETION_SOURCE_READ_FAILED"
            ) from exc
        if not gate_contract.RuntimeStartupAdmissionGateContractV1._maintenance_safe(
            value
        ):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_MAINTENANCE_COMPLETION_SOURCE_UNSAFE"
            )
        return value


class ProductionEvidenceVerifierPortAdapterV1(_PinnedProductionStartupSourceV1):
    adapter_name = "EVIDENCE_VERIFIER"

    def __init__(
        self,
        source: Any,
        *,
        authority_root_sha256: str,
        config: RuntimeProductionStartupPortSourceConfigV1 | None = None,
    ) -> None:
        super().__init__(source, config)
        self._authority_root_sha256 = str(authority_root_sha256 or "")

    def __repr__(self) -> str:
        return "<ProductionEvidenceVerifierPortAdapterV1 protected>"

    def verify(
        self, evidence: Mapping[str, Any], evidence_sha256: str
    ) -> dict[str, Any]:
        self._require_enabled()
        if not isinstance(evidence, Mapping):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_EVIDENCE_VERIFIER_INPUT_INVALID"
            )
        startup = evidence.get("startup_state")
        if not isinstance(startup, Mapping):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_EVIDENCE_VERIFIER_INPUT_INVALID"
            )
        try:
            value = copy.deepcopy(dict(self._source(evidence, evidence_sha256)))
        except Exception as exc:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_EVIDENCE_VERIFIER_SOURCE_FAILED"
            ) from exc
        if not gate_contract.RuntimeStartupAdmissionGateContractV1._authority_receipt_safe(
            value,
            evidence_sha=str(evidence_sha256 or ""),
            boot_sha=str(startup.get("process_boot_epoch_sha256") or ""),
            authority_root_sha=self._authority_root_sha256,
        ):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_EVIDENCE_VERIFIER_RECEIPT_INVALID"
            )
        return value


class PermitBoundRuntimeStartupCallbackAdapterV1(_PinnedProductionStartupSourceV1):
    adapter_name = "STARTUP_CALLBACK"

    def __init__(
        self,
        source: Any,
        *,
        gate: gate_contract.RuntimeStartupAdmissionGateContractV1,
        atomic_lock: Any,
        config: RuntimeProductionStartupPortSourceConfigV1 | None = None,
    ) -> None:
        super().__init__(source, config)
        if type(gate) is not gate_contract.RuntimeStartupAdmissionGateContractV1:
            raise TypeError("exact runtime startup admission gate is required")
        if getattr(gate, "_lock", None) is not atomic_lock:
            raise TypeError("callback, gate and seam must share one atomic lock")
        self._gate = gate
        self._lock = atomic_lock

    def __repr__(self) -> str:
        return "<PermitBoundRuntimeStartupCallbackAdapterV1 protected>"

    def bound_gate_identity_sha256_v1(self) -> str:
        """Return the public identity of the exact admission gate instance."""

        return composition_contract.production_startup_composition_dependency_identity_sha256_v1(
            self._gate
        )

    @staticmethod
    def _permit_safe(permit: Any) -> bool:
        return bool(
            type(permit) is gate_contract.RuntimeStartupAdmissionPermitV1
            and permit.startup_allowed is True
            and permit.runtime_activation_allowed is False
            and permit.live_allowed is False
            and permit.order_submission_authorized is False
            and permit.same_atomic_lock is True
        )

    @staticmethod
    def _receipt_safe(value: Any, permit: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and set(value) == _PRODUCTION_CALLBACK_RECEIPT_KEYS
            and value.get("ok") is True
            and value.get("status")
            == "C3_RUNTIME_STARTUP_COMPLETED_UNDER_ADMISSION"
            and value.get("startup_started") is True
            and value.get("runtime_activation_allowed") is False
            and value.get("live_allowed") is False
            and value.get("order_submission_authorized") is False
            and value.get("same_atomic_lock") is True
            and value.get("generation") == permit.generation
            and value.get("process_boot_epoch_sha256")
            == permit.process_boot_epoch_sha256
            and value.get("evidence_sha256") == permit.evidence_sha256
            and value.get("synthetic_only") is False
            and value.get("runtime_integrated") is True
            and value.get("production_ready") is True
            and value.get("no_order_sent") is True
        )

    def start(self, permit: Any) -> dict[str, Any]:
        self._require_enabled()
        if not self._permit_safe(permit):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_PERMIT_INVALID"
            )
        if getattr(self._gate, "_active_permit", None) is not permit:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_ACTIVE_PERMIT_REQUIRED"
            )
        if getattr(self._gate, "_lock", None) is not self._lock:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_LOCK_DRIFT"
            )
        try:
            value = copy.deepcopy(dict(self._source(permit)))
        except Exception as exc:
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_SOURCE_FAILED"
            ) from exc
        if not self._receipt_safe(value, permit):
            raise RuntimeProductionStartupPortSourceBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_RECEIPT_INVALID"
            )
        return value


__all__ = [
    "PermitBoundRuntimeStartupCallbackAdapterV1",
    "ProductionEvidenceVerifierPortAdapterV1",
    "ProductionMaintenanceCompletionPortAdapterV1",
    "ProductionSeamBindingPortAdapterV1",
    "ProductionStartupStatePortAdapterV1",
    "RUNTIME_PRODUCTION_STARTUP_PORT_SOURCE_SCOPE_ATTESTATION_V1",
    "RuntimeProductionStartupPortSourceBlocked",
    "RuntimeProductionStartupPortSourceConfigV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_PORT_SOURCES_CONTRACT_V1_VERSION",
]
