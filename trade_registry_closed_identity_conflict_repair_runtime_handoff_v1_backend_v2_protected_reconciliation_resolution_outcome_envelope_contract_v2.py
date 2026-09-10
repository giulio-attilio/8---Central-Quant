"""Neutral offline envelope for native legacy and durable C3 receipts."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2 as durable_commit_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as legacy_resolution_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_OUTCOME_ENVELOPE_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESOLUTION-OUTCOME-ENVELOPE-CONTRACT-V2"
)
OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2 = (
    "C3_RESOLUTION_OUTCOME_NATIVE_RECEIPT_ENVELOPE_OFFLINE_ONLY"
)
RESOLUTION_OUTCOME_ENVELOPE_VERSION_V2 = "C3_RESOLUTION_OUTCOME_ENVELOPE_V2"
ORIGINAL_SESSION_RECEIPT_SOURCE_V2 = "ORIGINAL_SESSION"
DURABLE_RESTART_RECEIPT_SOURCE_V2 = "DURABLE_RESTART"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_KINDS = {ORIGINAL_SESSION_RECEIPT_SOURCE_V2, DURABLE_RESTART_RECEIPT_SOURCE_V2}
_ENVELOPE_KEYS = frozenset(
    {
        "envelope_version", "scope_attestation", "source_kind",
        "source_receipt_sha256", "obligation_sha256", "obligation_id_sha256",
        "source_evidence_sha256", "adapter_plan_sha256",
        "request_binding_sha256", "request_sha256", "transaction_sha256",
        "terminal_resolution_evidence_sha256", "terminal_state",
        "resolved_at_epoch", "resolution_state", "reconciliation_required",
        "same_transaction_identity_verified", "terminal_resolution_verified",
        "new_apply_allowed", "retry_allowed", "source_native_validator_passed",
        "original_session_continuity_verified", "durable_atomic_commit_verified",
        "restart_reconstructible", "conversion_performed",
        "fabricated_session_evidence", "source_registry_write_recorded",
        "source_temporary_filesystem_accessed", "envelope_write_executed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "envelope_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def resolution_outcome_envelope_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "envelope_sha256"}
    )


def _native_receipt_valid(source_kind: str, value: Any) -> bool:
    if source_kind == ORIGINAL_SESSION_RECEIPT_SOURCE_V2:
        return legacy_resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(value)
    if source_kind == DURABLE_RESTART_RECEIPT_SOURCE_V2:
        return durable_commit_v2.protected_durable_resolution_commit_receipt_valid_v2(value)
    return False


@dataclass(frozen=True, repr=False)
class ProtectedResolutionOutcomeEnvelopeV2:
    native_source_receipt: Any = field(repr=False)
    envelope: Mapping[str, Any] = field(repr=False)
    envelope_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedResolutionOutcomeEnvelopeV2(<protected>)"


@dataclass(frozen=True)
class DormantResolutionOutcomeEnvelopeConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_source_kind: str | None = field(default=None, repr=False)
    expected_source_receipt_sha256: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_transaction_sha256: str | None = field(default=None, repr=False)


def protected_resolution_outcome_envelope_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedResolutionOutcomeEnvelopeV2:
        return False
    envelope = value.envelope
    if type(envelope) is not dict or set(envelope) != _ENVELOPE_KEYS:
        return False
    source_kind = envelope["source_kind"]
    source = value.native_source_receipt
    if not _native_receipt_valid(source_kind, source):
        return False
    receipt = source.receipt
    is_legacy = source_kind == ORIGINAL_SESSION_RECEIPT_SOURCE_V2
    try:
        return bool(
            envelope["envelope_version"] == RESOLUTION_OUTCOME_ENVELOPE_VERSION_V2
            and envelope["scope_attestation"] == OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2
            and envelope["source_receipt_sha256"] == source.receipt_sha256
            and envelope["obligation_sha256"] == receipt["obligation_sha256"]
            and envelope["obligation_id_sha256"] == receipt["obligation_id_sha256"]
            and envelope["source_evidence_sha256"] == receipt["source_evidence_sha256"]
            and envelope["adapter_plan_sha256"] == receipt["adapter_plan_sha256"]
            and envelope["request_sha256"] == receipt["request_sha256"]
            and envelope["transaction_sha256"] == receipt["transaction_sha256"]
            and (
                envelope["request_binding_sha256"]
                == source.terminal_resolution_evidence["request_binding_sha256"]
                if is_legacy
                else envelope["request_binding_sha256"] == receipt["request_binding_sha256"]
            )
            and envelope["terminal_resolution_evidence_sha256"]
            == (
                receipt["terminal_resolution_evidence_sha256"]
                if is_legacy
                else receipt["terminal_evidence_sha256"]
            )
            and envelope["terminal_state"] == receipt["terminal_state"]
            and envelope["resolved_at_epoch"] == receipt["resolved_at_epoch"]
            and envelope["resolution_state"] == "RESOLVED" == receipt["resolution_state"]
            and envelope["reconciliation_required"] is False
            and envelope["same_transaction_identity_verified"] is True
            and envelope["terminal_resolution_verified"] is True
            and envelope["new_apply_allowed"] is False
            and envelope["retry_allowed"] is False
            and envelope["source_native_validator_passed"] is True
            and envelope["original_session_continuity_verified"] is is_legacy
            and envelope["durable_atomic_commit_verified"] is (not is_legacy)
            and envelope["restart_reconstructible"] is (not is_legacy)
            and envelope["conversion_performed"] is False
            and envelope["fabricated_session_evidence"] is False
            and envelope["source_registry_write_recorded"] is (not is_legacy)
            and envelope["source_temporary_filesystem_accessed"] is (not is_legacy)
            and all(envelope[key] is False for key in (
                "envelope_write_executed", "real_registry_accessed",
                "network_accessed", "broker_called", "runtime_integrated",
                "activation_allowed", "live_allowed",
            ))
            and envelope["synthetic_only"] is True
            and value.envelope_sha256 == envelope["envelope_sha256"]
            and _valid_sha(envelope["envelope_sha256"])
            and hmac.compare_digest(
                envelope["envelope_sha256"],
                resolution_outcome_envelope_sha256_v2(envelope),
            )
        )
    except Exception:
        return False


class DormantResolutionOutcomeEnvelopeContractV2:
    def __init__(
        self,
        config: DormantResolutionOutcomeEnvelopeConfigV2 | None = None,
        *,
        protected_source_receipt: Any = None,
    ) -> None:
        self._config = config or DormantResolutionOutcomeEnvelopeConfigV2()
        self._protected_source_receipt = protected_source_receipt

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "RESOLUTION_OUTCOME_ENVELOPE_V2_BLOCKED",
            "reason": reason,
            "protected_envelope": None,
            "source_native_validator_passed": False,
            "conversion_performed": False,
            "fabricated_session_evidence": False,
            "write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    def _config_reason(self) -> str | None:
        if not self._config.enabled:
            return "RESOLUTION_OUTCOME_ENVELOPE_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2:
            return "RESOLUTION_OUTCOME_ENVELOPE_SCOPE_INVALID"
        if self._config.expected_source_kind not in _SOURCE_KINDS:
            return "RESOLUTION_OUTCOME_SOURCE_KIND_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                self._config.expected_source_receipt_sha256,
                self._config.expected_obligation_sha256,
                self._config.expected_transaction_sha256,
            )
        ):
            return "RESOLUTION_OUTCOME_ENVELOPE_PINS_INVALID"
        if self._protected_source_receipt is None:
            return "PINNED_NATIVE_SOURCE_RECEIPT_REQUIRED"
        return None

    def issue_offline(self, protected_source_receipt: Any) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if protected_source_receipt is not self._protected_source_receipt:
            return self._failed("NATIVE_SOURCE_RECEIPT_INSTANCE_NOT_PINNED")
        source_kind = str(self._config.expected_source_kind)
        if not _native_receipt_valid(source_kind, protected_source_receipt):
            return self._failed("NATIVE_SOURCE_RECEIPT_INVALID_FOR_KIND")
        receipt = protected_source_receipt.receipt
        if (
            protected_source_receipt.receipt_sha256 != self._config.expected_source_receipt_sha256
            or receipt["obligation_sha256"] != self._config.expected_obligation_sha256
            or receipt["transaction_sha256"] != self._config.expected_transaction_sha256
        ):
            return self._failed("NATIVE_SOURCE_RECEIPT_NOT_PINNED")
        is_legacy = source_kind == ORIGINAL_SESSION_RECEIPT_SOURCE_V2
        request_binding_sha256 = (
            protected_source_receipt.terminal_resolution_evidence["request_binding_sha256"]
            if is_legacy
            else receipt["request_binding_sha256"]
        )
        envelope = {
            "envelope_version": RESOLUTION_OUTCOME_ENVELOPE_VERSION_V2,
            "scope_attestation": OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2,
            "source_kind": source_kind,
            "source_receipt_sha256": protected_source_receipt.receipt_sha256,
            "obligation_sha256": receipt["obligation_sha256"],
            "obligation_id_sha256": receipt["obligation_id_sha256"],
            "source_evidence_sha256": receipt["source_evidence_sha256"],
            "adapter_plan_sha256": receipt["adapter_plan_sha256"],
            "request_binding_sha256": request_binding_sha256,
            "request_sha256": receipt["request_sha256"],
            "transaction_sha256": receipt["transaction_sha256"],
            "terminal_resolution_evidence_sha256": (
                receipt["terminal_resolution_evidence_sha256"]
                if is_legacy
                else receipt["terminal_evidence_sha256"]
            ),
            "terminal_state": receipt["terminal_state"],
            "resolved_at_epoch": receipt["resolved_at_epoch"],
            "resolution_state": "RESOLVED",
            "reconciliation_required": False,
            "same_transaction_identity_verified": True,
            "terminal_resolution_verified": True,
            "new_apply_allowed": False,
            "retry_allowed": False,
            "source_native_validator_passed": True,
            "original_session_continuity_verified": is_legacy,
            "durable_atomic_commit_verified": not is_legacy,
            "restart_reconstructible": not is_legacy,
            "conversion_performed": False,
            "fabricated_session_evidence": False,
            "source_registry_write_recorded": not is_legacy,
            "source_temporary_filesystem_accessed": not is_legacy,
            "envelope_write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        envelope["envelope_sha256"] = resolution_outcome_envelope_sha256_v2(envelope)
        protected = ProtectedResolutionOutcomeEnvelopeV2(
            native_source_receipt=protected_source_receipt,
            envelope=envelope,
            envelope_sha256=envelope["envelope_sha256"],
        )
        if not protected_resolution_outcome_envelope_valid_v2(protected):
            return self._failed("RESOLUTION_OUTCOME_ENVELOPE_SELF_VALIDATION_FAILED")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "RESOLUTION_OUTCOME_ENVELOPE_ISSUED_OFFLINE",
                "reason": None,
                "protected_envelope": protected,
                "source_native_validator_passed": True,
            }
        )
        return result


__all__ = [
    "DURABLE_RESTART_RECEIPT_SOURCE_V2",
    "DormantResolutionOutcomeEnvelopeConfigV2",
    "DormantResolutionOutcomeEnvelopeContractV2",
    "OFFLINE_RESOLUTION_OUTCOME_ENVELOPE_SCOPE_ATTESTATION_V2",
    "ORIGINAL_SESSION_RECEIPT_SOURCE_V2",
    "ProtectedResolutionOutcomeEnvelopeV2",
    "RESOLUTION_OUTCOME_ENVELOPE_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_OUTCOME_ENVELOPE_CONTRACT_V2_VERSION",
    "protected_resolution_outcome_envelope_valid_v2",
    "resolution_outcome_envelope_sha256_v2",
]
