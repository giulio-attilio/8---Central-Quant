"""Dormant offline restart barrier for protected reconciliation authority.

This policy object proves only that an evaluation still uses the exact
process-local session, issuer, and ledger captured when the barrier was
issued.  Session loss fails closed because durable authority validation is
deliberately not implemented here.  The module has no resolver, backend,
Registry, filesystem, network, runtime, or trading binding.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_BARRIER_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESTART-BARRIER-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESTART_BARRIER_OFFLINE_ONLY"
)
PROTECTED_RECONCILIATION_RESTART_BARRIER_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESTART_BARRIER_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_BARRIER_KEYS = frozenset(
    {
        "barrier_version", "scope_attestation", "obligation_sha256",
        "obligation_id_sha256", "transaction_sha256",
        "reference_authority_sha256", "reference_authorization_receipt_sha256",
        "reference_session_anchor_object_identity_sha256",
        "reference_authorization_issuer_object_identity_sha256",
        "reference_resolution_ledger_object_identity_sha256",
        "issued_at_epoch", "original_session_continuity_required",
        "restart_resolution_allowed", "cross_session_transfer_allowed",
        "authority_reissue_after_session_loss_allowed",
        "durable_authority_required_after_session_loss",
        "durable_authority_validation_implemented",
        "resolution_authority_granted", "resolution_execution_allowed",
        "backend_bound", "filesystem_accessed", "real_registry_accessed",
        "network_accessed", "broker_called", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "barrier_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def _identity_sha(kind: str, value: object) -> str:
    return backend_v2.stable_sha256_v2(
        {"kind": kind, "process_object_identity": id(value)}
    )


def protected_reconciliation_restart_barrier_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return backend_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "barrier_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationRestartBarrierV2:
    obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(repr=False)
    reference_authority: resolution_v2.ProtectedFreshReconciliationAuthorityV2 = field(
        repr=False
    )
    barrier: Mapping[str, Any] = field(repr=False)
    barrier_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationRestartBarrierV2(<protected>)"


@dataclass(frozen=True)
class DormantProtectedReconciliationRestartBarrierConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_reference_authority_sha256: str | None = field(
        default=None, repr=False
    )
    maximum_authority_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_authority_ttl_seconds <= 300:
            raise ValueError("maximum_authority_ttl_seconds must be between 1 and 300")


def protected_reconciliation_restart_barrier_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedReconciliationRestartBarrierV2:
        return False
    barrier = value.barrier
    obligation = value.obligation
    authority = value.reference_authority
    if type(barrier) is not dict or set(barrier) != _BARRIER_KEYS:
        return False
    if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
        return False
    try:
        issued_at = barrier["issued_at_epoch"]
        return bool(
            type(issued_at) is int
            and resolution_v2.fresh_reconciliation_authority_valid_v2(
                authority,
                obligation,
                now_epoch=issued_at,
                expected_single_use_ledger=authority.single_use_ledger,
                expected_authorization_issuer=authority.authorization_issuer,
            )
            and barrier["barrier_version"]
            == PROTECTED_RECONCILIATION_RESTART_BARRIER_VERSION_V2
            and barrier["scope_attestation"]
            == OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2
            and barrier["obligation_sha256"] == obligation.obligation_sha256
            and barrier["obligation_id_sha256"]
            == obligation.obligation["obligation_id_sha256"]
            and barrier["transaction_sha256"]
            == obligation.obligation["transaction_sha256"]
            and barrier["reference_authority_sha256"] == authority.authority_sha256
            and barrier["reference_authorization_receipt_sha256"]
            == authority.authorization_receipt["receipt_sha256"]
            and barrier["reference_session_anchor_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_process_session_anchor_v2",
                authority.process_session_anchor,
            )
            and barrier["reference_authorization_issuer_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_authorization_issuer_v2",
                authority.authorization_issuer,
            )
            and barrier["reference_resolution_ledger_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_resolution_ledger_v2",
                authority.single_use_ledger,
            )
            and barrier["original_session_continuity_required"] is True
            and barrier["restart_resolution_allowed"] is False
            and barrier["cross_session_transfer_allowed"] is False
            and barrier["authority_reissue_after_session_loss_allowed"] is False
            and barrier["durable_authority_required_after_session_loss"] is True
            and barrier["durable_authority_validation_implemented"] is False
            and barrier["resolution_authority_granted"] is False
            and barrier["resolution_execution_allowed"] is False
            and all(
                barrier[key] is False
                for key in (
                    "backend_bound", "filesystem_accessed", "real_registry_accessed",
                    "network_accessed", "broker_called", "production_authority",
                    "runtime_integrated", "activation_allowed", "live_allowed",
                )
            )
            and barrier["synthetic_only"] is True
            and value.barrier_sha256 == barrier["barrier_sha256"]
            and _valid_sha(barrier["barrier_sha256"])
            and hmac.compare_digest(
                barrier["barrier_sha256"],
                protected_reconciliation_restart_barrier_sha256_v2(barrier),
            )
        )
    except Exception:
        return False


class DormantProtectedReconciliationRestartBarrierContractV2:
    """Issue and evaluate a non-executing, process-local restart barrier."""

    def __init__(
        self,
        config: DormantProtectedReconciliationRestartBarrierConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantProtectedReconciliationRestartBarrierConfigV2()

    @staticmethod
    def _failed(reason: str, *, durable_authority_required: bool = False) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_RECONCILIATION_RESTART_BARRIER_V2_BLOCKED",
            "reason": reason,
            "protected_barrier": None,
            "barrier_passed_offline": False,
            "original_session_continuity_confirmed": False,
            "durable_authority_required": durable_authority_required,
            "resolution_authority_granted": False,
            "resolution_executed": False,
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
            return "PROTECTED_RECONCILIATION_RESTART_BARRIER_V2_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2
        ):
            return "PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_INVALID"
        if not _valid_sha(self._config.expected_obligation_sha256):
            return "EXPECTED_OBLIGATION_SHA256_REQUIRED"
        if not _valid_sha(self._config.expected_reference_authority_sha256):
            return "EXPECTED_REFERENCE_AUTHORITY_SHA256_REQUIRED"
        return None

    def issue_offline(
        self,
        obligation: Any,
        reference_authority: Any,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if type(now_epoch) is not int:
            return self._failed("NOW_EPOCH_INVALID")
        if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_INVALID")
        if obligation.obligation_sha256 != self._config.expected_obligation_sha256:
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_NOT_PINNED")
        if type(reference_authority) is not resolution_v2.ProtectedFreshReconciliationAuthorityV2:
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_INVALID")
        if not resolution_v2.fresh_reconciliation_authority_valid_v2(
            reference_authority,
            obligation,
            now_epoch=now_epoch,
            maximum_ttl_seconds=self._config.maximum_authority_ttl_seconds,
            expected_single_use_ledger=reference_authority.single_use_ledger,
            expected_authorization_issuer=reference_authority.authorization_issuer,
        ):
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_INVALID")
        if reference_authority.authority_sha256 != self._config.expected_reference_authority_sha256:
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_NOT_PINNED")
        record = obligation.obligation
        barrier = {
            "barrier_version": PROTECTED_RECONCILIATION_RESTART_BARRIER_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
            "obligation_sha256": obligation.obligation_sha256,
            "obligation_id_sha256": record["obligation_id_sha256"],
            "transaction_sha256": record["transaction_sha256"],
            "reference_authority_sha256": reference_authority.authority_sha256,
            "reference_authorization_receipt_sha256": reference_authority.authorization_receipt["receipt_sha256"],
            "reference_session_anchor_object_identity_sha256": _identity_sha(
                "synthetic_reconciliation_process_session_anchor_v2",
                reference_authority.process_session_anchor,
            ),
            "reference_authorization_issuer_object_identity_sha256": _identity_sha(
                "synthetic_reconciliation_authorization_issuer_v2",
                reference_authority.authorization_issuer,
            ),
            "reference_resolution_ledger_object_identity_sha256": _identity_sha(
                "synthetic_reconciliation_resolution_ledger_v2",
                reference_authority.single_use_ledger,
            ),
            "issued_at_epoch": now_epoch,
            "original_session_continuity_required": True,
            "restart_resolution_allowed": False,
            "cross_session_transfer_allowed": False,
            "authority_reissue_after_session_loss_allowed": False,
            "durable_authority_required_after_session_loss": True,
            "durable_authority_validation_implemented": False,
            "resolution_authority_granted": False,
            "resolution_execution_allowed": False,
            "backend_bound": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        barrier["barrier_sha256"] = protected_reconciliation_restart_barrier_sha256_v2(barrier)
        protected = ProtectedReconciliationRestartBarrierV2(
            obligation=obligation,
            reference_authority=reference_authority,
            barrier=copy.deepcopy(barrier),
            barrier_sha256=barrier["barrier_sha256"],
        )
        if not protected_reconciliation_restart_barrier_valid_v2(protected):
            return self._failed("PROTECTED_RECONCILIATION_RESTART_BARRIER_INTERNAL_INVALID")
        result = self._failed("PROTECTED_RECONCILIATION_RESTART_BARRIER_ISSUED")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_RECONCILIATION_RESTART_BARRIER_ISSUED_OFFLINE",
                "reason": None,
                "protected_barrier": protected,
            }
        )
        return result

    def evaluate_offline(
        self,
        protected_barrier: Any,
        current_authority: Any,
        *,
        session_loss_declared: bool,
        now_epoch: int,
        durable_authority_evidence: Any = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if durable_authority_evidence is not None:
            return self._failed(
                "DURABLE_AUTHORITY_VALIDATION_NOT_IMPLEMENTED",
                durable_authority_required=True,
            )
        if type(session_loss_declared) is not bool or type(now_epoch) is not int:
            return self._failed("RESTART_BARRIER_EVALUATION_INPUT_INVALID")
        if not protected_reconciliation_restart_barrier_valid_v2(protected_barrier):
            return self._failed("PROTECTED_RECONCILIATION_RESTART_BARRIER_INVALID")
        if protected_barrier.obligation.obligation_sha256 != self._config.expected_obligation_sha256:
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_NOT_PINNED")
        if protected_barrier.reference_authority.authority_sha256 != self._config.expected_reference_authority_sha256:
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_NOT_PINNED")
        if session_loss_declared:
            return self._failed(
                "RESTART_RESOLUTION_FORBIDDEN_DURABLE_AUTHORITY_REQUIRED",
                durable_authority_required=True,
            )
        reference = protected_barrier.reference_authority
        exact_continuity = bool(
            current_authority is reference
            and getattr(current_authority, "process_session_anchor", None)
            is reference.process_session_anchor
            and getattr(current_authority, "authorization_issuer", None)
            is reference.authorization_issuer
            and getattr(current_authority, "single_use_ledger", None)
            is reference.single_use_ledger
        )
        if not exact_continuity:
            return self._failed("ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN")
        if not resolution_v2.fresh_reconciliation_authority_valid_v2(
            current_authority,
            protected_barrier.obligation,
            now_epoch=now_epoch,
            maximum_ttl_seconds=self._config.maximum_authority_ttl_seconds,
            expected_single_use_ledger=reference.single_use_ledger,
            expected_authorization_issuer=reference.authorization_issuer,
        ):
            return self._failed("REFERENCE_RECONCILIATION_AUTHORITY_NO_LONGER_VALID")
        result = self._failed("ORIGINAL_SESSION_CONTINUITY_CONFIRMED")
        result.update(
            {
                "ok": True,
                "status": "ORIGINAL_SESSION_CONTINUITY_CONFIRMED_OFFLINE",
                "reason": None,
                "protected_barrier": protected_barrier,
                "barrier_passed_offline": True,
                "original_session_continuity_confirmed": True,
            }
        )
        return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_BARRIER_CONTRACT_V2_VERSION",
    "OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2",
    "PROTECTED_RECONCILIATION_RESTART_BARRIER_VERSION_V2",
    "ProtectedReconciliationRestartBarrierV2",
    "DormantProtectedReconciliationRestartBarrierConfigV2",
    "DormantProtectedReconciliationRestartBarrierContractV2",
    "protected_reconciliation_restart_barrier_sha256_v2",
    "protected_reconciliation_restart_barrier_valid_v2",
]
