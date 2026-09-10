"""Dormant offline composition of restart barrier and reconciliation resolver.

The composition admits only the exact protected barrier instance captured at
construction, evaluates original process-session continuity first, and invokes
the synthetic resolver only after that evaluation succeeds.  It has no runtime,
backend, Registry, filesystem, network, or trading binding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESTART-SAFE-RESOLUTION-COMPOSITION-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_OFFLINE_ONLY"
)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


@dataclass(frozen=True)
class DormantProtectedReconciliationRestartSafeResolutionCompositionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_barrier_sha256: str | None = field(default=None, repr=False)
    expected_reference_authority_sha256: str | None = field(
        default=None, repr=False
    )
    maximum_authority_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_authority_ttl_seconds <= 300:
            raise ValueError("maximum_authority_ttl_seconds must be between 1 and 300")


class DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2:
    """Fail-closed, non-runtime facade over barrier evaluation and resolver."""

    def __init__(
        self,
        config: DormantProtectedReconciliationRestartSafeResolutionCompositionConfigV2 | None = None,
        *,
        protected_barrier: barrier_v2.ProtectedReconciliationRestartBarrierV2 | None = None,
        resolution_contract: resolution_v2.DormantProtectedReconciliationResolutionContractV2 | None = None,
    ) -> None:
        self._config = config or DormantProtectedReconciliationRestartSafeResolutionCompositionConfigV2()
        self._protected_barrier = protected_barrier
        self._resolution_contract = resolution_contract

    @staticmethod
    def _failed(
        reason: str,
        *,
        barrier_reason: str | None = None,
        resolver_reason: str | None = None,
        barrier_evaluation_count: int = 0,
        resolver_invocation_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_V2_BLOCKED",
            "reason": reason,
            "barrier_reason": barrier_reason,
            "resolver_reason": resolver_reason,
            "protected_receipt": None,
            "barrier_evaluation_count": barrier_evaluation_count,
            "resolver_invocation_count": resolver_invocation_count,
            "original_session_continuity_confirmed": False,
            "synthetic_resolution_receipt_emitted": False,
            "resolution_authority_granted": False,
            "operational_execution": False,
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "registry_write": False,
            "write_executed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_V2_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_SCOPE_ATTESTATION_V2
        ):
            return "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_SCOPE_INVALID"
        for value, reason in (
            (self._config.expected_obligation_sha256, "EXPECTED_OBLIGATION_SHA256_REQUIRED"),
            (self._config.expected_barrier_sha256, "EXPECTED_BARRIER_SHA256_REQUIRED"),
            (
                self._config.expected_reference_authority_sha256,
                "EXPECTED_REFERENCE_AUTHORITY_SHA256_REQUIRED",
            ),
        ):
            if not _valid_sha(value):
                return reason
        return None

    def resolve_offline(
        self,
        protected_barrier: Any,
        current_authority: Any,
        terminal_resolution_evidence: Any,
        *,
        session_loss_declared: bool,
        now_epoch: int,
        durable_authority_evidence: Any = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if type(self._protected_barrier) is not barrier_v2.ProtectedReconciliationRestartBarrierV2:
            return self._failed("PINNED_PROTECTED_RESTART_BARRIER_REQUIRED")
        if type(self._resolution_contract) is not resolution_v2.DormantProtectedReconciliationResolutionContractV2:
            return self._failed("PINNED_PROTECTED_RECONCILIATION_RESOLVER_REQUIRED")
        if protected_barrier is not self._protected_barrier:
            return self._failed("PROTECTED_RESTART_BARRIER_INSTANCE_NOT_PINNED")
        if not barrier_v2.protected_reconciliation_restart_barrier_valid_v2(
            protected_barrier
        ):
            return self._failed("PROTECTED_RESTART_BARRIER_INVALID")
        if protected_barrier.obligation.obligation_sha256 != self._config.expected_obligation_sha256:
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_NOT_PINNED")
        if protected_barrier.barrier_sha256 != self._config.expected_barrier_sha256:
            return self._failed("PROTECTED_RESTART_BARRIER_SHA256_NOT_PINNED")
        if protected_barrier.reference_authority.authority_sha256 != self._config.expected_reference_authority_sha256:
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_NOT_PINNED")
        barrier_contract = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2(
            barrier_v2.DormantProtectedReconciliationRestartBarrierConfigV2(
                enabled=True,
                scope_attestation=barrier_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
                expected_obligation_sha256=self._config.expected_obligation_sha256,
                expected_reference_authority_sha256=self._config.expected_reference_authority_sha256,
                maximum_authority_ttl_seconds=self._config.maximum_authority_ttl_seconds,
            )
        )
        barrier_result = barrier_contract.evaluate_offline(
            protected_barrier,
            current_authority,
            session_loss_declared=session_loss_declared,
            now_epoch=now_epoch,
            durable_authority_evidence=durable_authority_evidence,
        )
        if not (
            barrier_result.get("ok") is True
            and barrier_result.get("barrier_passed_offline") is True
            and barrier_result.get("original_session_continuity_confirmed") is True
            and barrier_result.get("resolution_authority_granted") is False
            and barrier_result.get("resolution_executed") is False
        ):
            return self._failed(
                "PROTECTED_RESTART_BARRIER_REJECTED",
                barrier_reason=barrier_result.get("reason"),
                barrier_evaluation_count=1,
            )
        resolver_result = self._resolution_contract.resolve_offline(
            protected_barrier.obligation,
            current_authority,
            terminal_resolution_evidence,
            now_epoch=now_epoch,
            protected_restart_barrier=protected_barrier,
            session_loss_declared=False,
        )
        if resolver_result.get("ok") is not True:
            return self._failed(
                "PROTECTED_RECONCILIATION_RESOLVER_REJECTED",
                resolver_reason=resolver_result.get("reason"),
                barrier_evaluation_count=2,
                resolver_invocation_count=1,
            )
        protected_receipt = resolver_result.get("protected_receipt")
        if not resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(
            protected_receipt
        ):
            return self._failed(
                "PROTECTED_RECONCILIATION_RESOLVER_RECEIPT_INVALID",
                barrier_evaluation_count=2,
                resolver_invocation_count=1,
            )
        result = self._failed(
            "",
            barrier_evaluation_count=2,
            resolver_invocation_count=1,
        )
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_RESOLVED_OFFLINE",
                "reason": None,
                "protected_receipt": protected_receipt,
                "original_session_continuity_confirmed": True,
                "synthetic_resolution_receipt_emitted": True,
            }
        )
        return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_CONTRACT_V2_VERSION",
    "OFFLINE_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_SCOPE_ATTESTATION_V2",
    "DormantProtectedReconciliationRestartSafeResolutionCompositionConfigV2",
    "DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2",
]
