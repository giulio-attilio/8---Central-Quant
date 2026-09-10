"""Offline interlock between C3 activation proposal and startup port binding.

The interlock verifies exact dormant binding/source instances and an existing
controlled-activation proposal.  It only emits a sealed preparation receipt;
it has no activation method and always denies apply, runtime start, Live and
order submission.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_contract_v1 as upstream_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_composition_contract_v1 as identity_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_binding_adapter_contract_v1 as binding_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_port_sources_contract_v1 as sources_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-CONTROLLED-ACTIVATION-INTERLOCK-CONTRACT-V1"
)
RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_OFFLINE_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_V1"
)

_SOURCE_KEYS = frozenset(
    {
        "startup_state",
        "seam_binding",
        "maintenance_completion",
        "evidence_verifier",
        "startup_callback",
    }
)
_SOURCE_TYPES = {
    "startup_state": sources_contract.ProductionStartupStatePortAdapterV1,
    "seam_binding": sources_contract.ProductionSeamBindingPortAdapterV1,
    "maintenance_completion": sources_contract.ProductionMaintenanceCompletionPortAdapterV1,
    "evidence_verifier": sources_contract.ProductionEvidenceVerifierPortAdapterV1,
    "startup_callback": sources_contract.PermitBoundRuntimeStartupCallbackAdapterV1,
}


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class RuntimeProductionStartupControlledActivationInterlockBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class RuntimeProductionStartupControlledActivationInterlockConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_binding_identity_sha256: str | None = field(default=None, repr=False)
    expected_source_adapter_identities: Mapping[str, str] | None = field(
        default=None, repr=False
    )


class RuntimeProductionStartupControlledActivationInterlockContractV1:
    """Prepare, but never apply, one controlled startup activation plan."""

    def __init__(
        self,
        *,
        dormant_binding: binding_contract.DormantRuntimeProductionStartupPortBindingV1,
        source_adapters: Mapping[str, Any],
        config: RuntimeProductionStartupControlledActivationInterlockConfigV1
        | None = None,
    ) -> None:
        if type(dormant_binding) is not binding_contract.DormantRuntimeProductionStartupPortBindingV1:
            raise TypeError("exact dormant startup port binding is required")
        if not isinstance(source_adapters, Mapping) or set(source_adapters) != _SOURCE_KEYS:
            raise TypeError("the five exact source adapters are required")
        if any(type(source_adapters[name]) is not expected for name, expected in _SOURCE_TYPES.items()):
            raise TypeError("source adapter type mismatch")
        self._binding = dormant_binding
        self._sources = dict(source_adapters)
        self._config = config or RuntimeProductionStartupControlledActivationInterlockConfigV1()
        self._prepared_request_sha256: str | None = None

    def __repr__(self) -> str:
        return "<RuntimeProductionStartupControlledActivationInterlockContractV1 protected>"

    def _reason(self) -> str | None:
        if self._config.enabled is not True:
            return "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_DEFAULT_OFF"
        if self._config.scope_attestation != RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_SCOPE_ATTESTATION_V1:
            return "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_SCOPE_INVALID"
        expected_binding = self._config.expected_binding_identity_sha256
        actual_binding = identity_contract.production_startup_composition_dependency_identity_sha256_v1(
            self._binding
        )
        if not isinstance(expected_binding, str) or not hmac.compare_digest(
            expected_binding, actual_binding
        ):
            return "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_BINDING_IDENTITY_MISMATCH"
        identities = self._config.expected_source_adapter_identities
        if not isinstance(identities, Mapping) or set(identities) != _SOURCE_KEYS:
            return "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_SOURCE_IDENTITIES_REQUIRED"
        for name, adapter in self._sources.items():
            actual = identity_contract.production_startup_composition_dependency_identity_sha256_v1(
                adapter
            )
            expected = identities.get(name)
            if not isinstance(expected, str) or not hmac.compare_digest(expected, actual):
                return f"C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_{name.upper()}_IDENTITY_MISMATCH"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        return {
            "ok": reason is None,
            "status": (
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_OFFLINE_READY"
                if reason is None
                else "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_DORMANT"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_CONTRACT_V1_VERSION,
            "reason": reason,
            "default_off": reason is not None,
            "proposal_only": True,
            "prepared": self._prepared_request_sha256 is not None,
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

    def _require_cross_binding(self) -> None:
        binding_snapshot = self._binding.snapshot()
        if not (
            binding_snapshot.get("ok") is True
            and binding_snapshot.get("same_atomic_lock") is True
            and binding_snapshot.get("gate_default_off") is True
            and binding_snapshot.get("composition_default_off") is True
            and binding_snapshot.get("activation_possible") is False
            and binding_snapshot.get("providers_invoked") is False
            and binding_snapshot.get("startup_callback_invoked") is False
        ):
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_BINDING_UNSAFE"
            )
        for name, adapter in self._sources.items():
            if not hmac.compare_digest(
                self._binding.source_identity_sha256_v1(name),
                adapter.bound_source_identity_sha256_v1(),
            ):
                raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                    f"C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_{name.upper()}_CROSS_BINDING_MISMATCH"
                )
        if not hmac.compare_digest(
            self._sources["startup_callback"].bound_gate_identity_sha256_v1(),
            self._binding.gate_identity_sha256_v1(),
        ):
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_CALLBACK_GATE_MISMATCH"
            )
        if not all(adapter.snapshot().get("ok") is True for adapter in self._sources.values()):
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_SOURCE_ADAPTER_NOT_READY"
            )

    @staticmethod
    def _upstream_safe(value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        receipt = value.get("proposal_receipt")
        if not isinstance(receipt, Mapping):
            return False
        supplied = receipt.get("proposal_receipt_sha256")
        expected = _stable_sha256(
            {key: item for key, item in receipt.items() if key != "proposal_receipt_sha256"}
        )
        return bool(
            value.get("ok") is True
            and value.get("status")
            == "C3_CONTROLLED_RUNTIME_ACTIVATION_V1_VALID_OFFLINE_ACTIVATION_DENIED"
            and value.get("proposal_contract_verified") is True
            and value.get("writer_inventory_verified") is True
            and value.get("safety_controls_verified") is True
            and value.get("dormant_seam_verified") is True
            and value.get("production_ready") is False
            and value.get("activation_allowed") is False
            and value.get("runtime_install_allowed") is False
            and value.get("runtime_start_allowed") is False
            and value.get("live_allowed") is False
            and value.get("write_executed") is False
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("no_order_sent") is True
            and receipt.get("writer_count") == 19
            and receipt.get("all_offline_checks_passed") is True
            and receipt.get("source_hashes_must_be_rechecked") is True
            and receipt.get("activation_allowed") is False
            and receipt.get("runtime_start_allowed") is False
            and receipt.get("live_allowed") is False
            and isinstance(supplied, str)
            and hmac.compare_digest(supplied, expected)
        )

    def prepare_offline(self, upstream_activation_result: Mapping[str, Any]) -> dict[str, Any]:
        reason = self._reason()
        if reason is not None:
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(reason)
        if self._prepared_request_sha256 is not None:
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_REPLAY_BLOCKED"
            )
        self._require_cross_binding()
        try:
            upstream = copy.deepcopy(dict(upstream_activation_result))
        except Exception as exc:
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_UPSTREAM_INVALID"
            ) from exc
        if not self._upstream_safe(upstream):
            raise RuntimeProductionStartupControlledActivationInterlockBlocked(
                "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_UPSTREAM_UNSAFE"
            )
        request_sha = _stable_sha256(
            {
                "upstream_proposal_receipt_sha256": upstream["proposal_receipt"][
                    "proposal_receipt_sha256"
                ],
                "binding_identity_sha256": self._config.expected_binding_identity_sha256,
                "source_adapter_identities": dict(
                    self._config.expected_source_adapter_identities or {}
                ),
            }
        )
        self._prepared_request_sha256 = request_sha
        receipt = {
            "ok": True,
            "status": "C3_PRODUCTION_STARTUP_ACTIVATION_INTERLOCK_PREPARED_OFFLINE_APPLY_DENIED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_CONTRACT_V1_VERSION,
            "request_sha256": request_sha,
            "upstream_proposal_receipt_sha256": upstream["proposal_receipt"][
                "proposal_receipt_sha256"
            ],
            "exact_binding_verified": True,
            "five_source_adapters_verified": True,
            "same_callback_gate_verified": True,
            "source_hashes_must_be_rechecked": True,
            "production_authority_must_be_configured": True,
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
        receipt["receipt_sha256"] = _stable_sha256(receipt)
        return receipt


__all__ = [
    "RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_SCOPE_ATTESTATION_V1",
    "RuntimeProductionStartupControlledActivationInterlockBlocked",
    "RuntimeProductionStartupControlledActivationInterlockConfigV1",
    "RuntimeProductionStartupControlledActivationInterlockContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_CONTROLLED_ACTIVATION_INTERLOCK_CONTRACT_V1_VERSION",
]
