"""Default-off composition for production-shaped C3 startup evidence.

The contract assembles attestations supplied by injected authorities without
rewriting or projecting any field.  It can only rehearse an injected startup
callback offline; it does not import the runtime, open the Registry or grant
Live/order authority.  A later runtime integration must bind the exact same
provider, gate and lock instances.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_startup_admission_gate_contract_v1 as gate_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-COMPOSITION-CONTRACT-V1"
)
RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_EXPLICIT_OFFLINE_PRODUCTION_STARTUP_COMPOSITION_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CALLBACK_RECEIPT_KEYS = frozenset(
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


def _valid_sha256(value: Any) -> str | None:
    candidate = str(value or "").lower().strip()
    return candidate if _SHA256_RE.fullmatch(candidate) else None


def production_startup_composition_dependency_identity_sha256_v1(value: Any) -> str:
    """Bind a dependency to its exact process-local instance and implementation."""

    if value is None:
        raise TypeError("dependency is required")
    owner = getattr(value, "__self__", None)
    function = getattr(value, "__func__", None)
    identity_target = owner if owner is not None else value
    implementation = function if function is not None else type(value)
    module = str(getattr(implementation, "__module__", "") or "")
    qualname = str(getattr(implementation, "__qualname__", "") or "")
    if not module or not qualname:
        raise TypeError("dependency identity is unavailable")
    material = f"{module}:{qualname}:{id(identity_target)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _same_callable_binding(left: Any, right: Any) -> bool:
    left_owner = getattr(left, "__self__", None)
    right_owner = getattr(right, "__self__", None)
    left_function = getattr(left, "__func__", None)
    right_function = getattr(right, "__func__", None)
    if left_owner is not None or right_owner is not None:
        return bool(
            left_owner is right_owner
            and left_function is not None
            and left_function is right_function
        )
    return left is right


class RuntimeProductionStartupCompositionBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_BLOCKED")
        super().__init__(self.reason)


@dataclass(frozen=True)
class RuntimeProductionStartupCompositionConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    offline_rehearsal_only: bool = True
    expected_gate_identity_sha256: str | None = field(default=None, repr=False)
    expected_trading_controls_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_startup_state_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_seam_binding_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_maintenance_completion_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_startup_callback_identity_sha256: str | None = field(
        default=None, repr=False
    )


class RuntimeProductionStartupCompositionContractV1:
    """Bind exact production-evidence providers to one offline gate rehearsal."""

    def __init__(
        self,
        *,
        gate: gate_contract.RuntimeStartupAdmissionGateContractV1,
        atomic_lock: Any,
        trading_controls: Callable[[], Mapping[str, Any]],
        startup_state: Callable[[], Mapping[str, Any]],
        seam_binding_evidence: Callable[[], Mapping[str, Any]],
        maintenance_completion_evidence: Callable[[], Mapping[str, Any]],
        startup_callback: Callable[[Any], Mapping[str, Any]],
        config: RuntimeProductionStartupCompositionConfigV1 | None = None,
    ) -> None:
        if type(gate) is not gate_contract.RuntimeStartupAdmissionGateContractV1:
            raise TypeError("exact runtime startup admission gate is required")
        providers = (
            trading_controls,
            startup_state,
            seam_binding_evidence,
            maintenance_completion_evidence,
            startup_callback,
        )
        if not all(callable(value) for value in providers):
            raise TypeError("all startup composition providers are required")
        if atomic_lock is None or not all(
            callable(getattr(atomic_lock, name, None))
            for name in ("__enter__", "__exit__")
        ):
            raise TypeError("one context-manager atomic lock is required")
        if getattr(gate, "_lock", None) is not atomic_lock:
            raise TypeError("gate and composition must share the same atomic lock")
        if not _same_callable_binding(getattr(gate, "_startup_state", None), startup_state):
            raise TypeError("gate and composition must share the startup-state authority")
        self._gate = gate
        self._lock = atomic_lock
        self._trading_controls = trading_controls
        self._startup_state = startup_state
        self._seam_binding_evidence = seam_binding_evidence
        self._maintenance_completion_evidence = maintenance_completion_evidence
        self._startup_callback = startup_callback
        self._config = config or RuntimeProductionStartupCompositionConfigV1()
        self._rehearsal_count = 0

    def __repr__(self) -> str:
        return "<RuntimeProductionStartupCompositionContractV1 protected>"

    def _dependencies(self) -> tuple[tuple[str, Any, str | None], ...]:
        return (
            ("gate", self._gate, self._config.expected_gate_identity_sha256),
            (
                "trading_controls",
                self._trading_controls,
                self._config.expected_trading_controls_identity_sha256,
            ),
            (
                "startup_state",
                self._startup_state,
                self._config.expected_startup_state_identity_sha256,
            ),
            (
                "seam_binding",
                self._seam_binding_evidence,
                self._config.expected_seam_binding_identity_sha256,
            ),
            (
                "maintenance_completion",
                self._maintenance_completion_evidence,
                self._config.expected_maintenance_completion_identity_sha256,
            ),
            (
                "startup_callback",
                self._startup_callback,
                self._config.expected_startup_callback_identity_sha256,
            ),
        )

    def _configuration_ready(self) -> bool:
        if not (
            self._config.enabled is True
            and self._config.scope_attestation
            == RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_ATTESTATION_V1
            and self._config.offline_rehearsal_only is True
        ):
            return False
        try:
            return all(
                bool(
                    _valid_sha256(expected)
                    and hmac.compare_digest(
                        str(expected),
                        production_startup_composition_dependency_identity_sha256_v1(
                            dependency
                        ),
                    )
                )
                for _, dependency, expected in self._dependencies()
            )
        except TypeError:
            return False

    def snapshot(self) -> dict[str, Any]:
        ready = self._configuration_ready()
        return {
            "ok": ready,
            "status": (
                "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_OFFLINE_READY"
                if ready
                else "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_DORMANT_DEFAULT_OFF"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_CONTRACT_V1_VERSION,
            "enabled": ready,
            "default_off": not ready,
            "offline_rehearsal_only": True,
            "dependencies_instance_bound": ready,
            "same_atomic_lock": getattr(self._gate, "_lock", None) is self._lock,
            "rehearsal_count": self._rehearsal_count,
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

    def _require_enabled(self) -> None:
        if self._config.enabled is not True:
            raise RuntimeProductionStartupCompositionBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_ATTESTATION_V1
            or self._config.offline_rehearsal_only is not True
        ):
            raise RuntimeProductionStartupCompositionBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_INVALID"
            )
        for name, dependency, expected in self._dependencies():
            supplied = _valid_sha256(expected)
            try:
                actual = production_startup_composition_dependency_identity_sha256_v1(
                    dependency
                )
            except TypeError as exc:
                raise RuntimeProductionStartupCompositionBlocked(
                    f"C3_RUNTIME_PRODUCTION_STARTUP_{name.upper()}_IDENTITY_INVALID"
                ) from exc
            if not supplied or not hmac.compare_digest(supplied, actual):
                raise RuntimeProductionStartupCompositionBlocked(
                    f"C3_RUNTIME_PRODUCTION_STARTUP_{name.upper()}_IDENTITY_MISMATCH"
                )

    @staticmethod
    def _callback_receipt_safe(receipt: Any, permit: Any) -> bool:
        return bool(
            isinstance(receipt, Mapping)
            and set(receipt) == _CALLBACK_RECEIPT_KEYS
            and receipt.get("ok") is True
            and receipt.get("status") == "C3_RUNTIME_STARTUP_CALLBACK_REHEARSED_OFFLINE"
            and receipt.get("startup_started") is True
            and receipt.get("runtime_activation_allowed") is False
            and receipt.get("live_allowed") is False
            and receipt.get("order_submission_authorized") is False
            and receipt.get("same_atomic_lock") is True
            and receipt.get("generation") == permit.generation
            and receipt.get("process_boot_epoch_sha256")
            == permit.process_boot_epoch_sha256
            and receipt.get("evidence_sha256") == permit.evidence_sha256
            and receipt.get("synthetic_only") is True
            and receipt.get("runtime_integrated") is False
            and receipt.get("production_ready") is False
            and receipt.get("no_order_sent") is True
        )

    def _build_request_without_projection(self) -> dict[str, Any]:
        try:
            evidence = {
                "trading_controls": copy.deepcopy(dict(self._trading_controls())),
                "startup_state": copy.deepcopy(dict(self._startup_state())),
                "seam_binding": copy.deepcopy(dict(self._seam_binding_evidence())),
                "maintenance_completion": copy.deepcopy(
                    dict(self._maintenance_completion_evidence())
                ),
            }
        except Exception as exc:
            raise RuntimeProductionStartupCompositionBlocked(
                "C3_RUNTIME_PRODUCTION_STARTUP_EVIDENCE_COLLECTION_FAILED"
            ) from exc
        request = {
            "ack": gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_ACK_V1,
            "scope_attestation": gate_contract.RUNTIME_STARTUP_ADMISSION_GATE_SCOPE_ATTESTATION_V1,
            "evidence": evidence,
        }
        request["request_sha256"] = (
            gate_contract.runtime_startup_admission_request_sha256_v1(request)
        )
        return request

    def rehearse_offline(self) -> dict[str, Any]:
        """Exercise the exact gate/callback chain without runtime integration."""

        self._require_enabled()
        request = self._build_request_without_projection()
        try:
            with self._gate.startup_admission(request) as permit:
                callback_receipt = self._startup_callback(permit)
                if not self._callback_receipt_safe(callback_receipt, permit):
                    raise RuntimeProductionStartupCompositionBlocked(
                        "C3_RUNTIME_PRODUCTION_STARTUP_CALLBACK_RECEIPT_INVALID"
                    )
        except RuntimeProductionStartupCompositionBlocked:
            raise
        except Exception as exc:
            raise RuntimeProductionStartupCompositionBlocked(
                getattr(exc, "reason", "C3_RUNTIME_PRODUCTION_STARTUP_ADMISSION_FAILED")
            ) from exc
        self._rehearsal_count += 1
        return {
            "ok": True,
            "status": "C3_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_REHEARSED_OFFLINE",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_CONTRACT_V1_VERSION,
            "request_sha256": request["request_sha256"],
            "evidence_sha256": permit.evidence_sha256,
            "callback_receipt": copy.deepcopy(dict(callback_receipt)),
            "production_evidence_projected": False,
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


__all__ = [
    "RUNTIME_PRODUCTION_STARTUP_COMPOSITION_SCOPE_ATTESTATION_V1",
    "RuntimeProductionStartupCompositionBlocked",
    "RuntimeProductionStartupCompositionConfigV1",
    "RuntimeProductionStartupCompositionContractV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_COMPOSITION_CONTRACT_V1_VERSION",
    "production_startup_composition_dependency_identity_sha256_v1",
]
