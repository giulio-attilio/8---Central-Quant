"""Atomic synthetic WAL commit for a prepared durable C3 resolution."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_COMMIT_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESOLUTION-COMMIT-CONTRACT-V2"
)
OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RESOLUTION_ATOMIC_TEMP_WAL_COMMIT_ONLY"
)
DURABLE_RESOLUTION_COMMIT_RECEIPT_VERSION_V2 = (
    "C3_DURABLE_RESOLUTION_COMMIT_RECEIPT_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "scope_attestation", "preparation_sha256",
        "admission_sha256", "obligation_sha256", "obligation_id_sha256",
        "source_evidence_sha256", "adapter_plan_sha256",
        "request_binding_sha256", "request_sha256", "transaction_sha256",
        "pre_resolution_record_sha256",
        "resolved_record_sha256", "resolution_binding_sha256",
        "terminal_evidence_sha256", "terminal_state", "resolved_at_epoch",
        "durable_generation", "resolution_state", "consumption_count",
        "atomic_wal_transition_verified", "restart_reconstructible",
        "idempotent_replay_supported", "resolver_called", "barrier_called",
        "backend_called", "registry_write", "temporary_filesystem_accessed",
        "write_executed", "real_registry_accessed", "network_accessed",
        "broker_called", "production_authority", "production_durable",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "receipt_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def durable_resolution_commit_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedDurableResolutionCommitReceiptV2:
    resolved_durable_authority_receipt: durable_v2.ProtectedDurableReconciliationAuthorityReceiptV2 = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableResolutionCommitReceiptV2(<protected>)"


@dataclass(frozen=True)
class DormantDurableResolutionCommitConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_preparation_sha256: str | None = field(default=None, repr=False)
    expected_admission_sha256: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_pre_resolution_record_sha256: str | None = field(default=None, repr=False)
    expected_terminal_evidence_sha256: str | None = field(default=None, repr=False)


def protected_durable_resolution_commit_receipt_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableResolutionCommitReceiptV2:
        return False
    durable_receipt = value.resolved_durable_authority_receipt
    receipt = value.receipt
    if (
        not durable_v2.protected_durable_reconciliation_authority_receipt_valid_v2(durable_receipt)
        or durable_receipt.receipt["state"] != "RESOLVED"
        or type(receipt) is not dict
        or set(receipt) != _RECEIPT_KEYS
    ):
        return False
    record = durable_receipt.record
    try:
        return bool(
            receipt["receipt_version"] == DURABLE_RESOLUTION_COMMIT_RECEIPT_VERSION_V2
            and receipt["scope_attestation"] == OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2
            and receipt["preparation_sha256"] == record["preparation_sha256"]
            and receipt["admission_sha256"] == record["admission_sha256"]
            and receipt["obligation_sha256"] == record["obligation_sha256"]
            and receipt["obligation_id_sha256"] == record["obligation_id_sha256"]
            and receipt["source_evidence_sha256"] == record["resolution_source_evidence_sha256"]
            and receipt["adapter_plan_sha256"] == record["resolution_adapter_plan_sha256"]
            and receipt["request_binding_sha256"] == record["resolution_request_binding_sha256"]
            and receipt["request_sha256"] == record["resolution_request_sha256"]
            and receipt["transaction_sha256"] == record["transaction_sha256"]
            and receipt["pre_resolution_record_sha256"] == record["pre_resolution_record_sha256"]
            and receipt["resolved_record_sha256"] == durable_receipt.receipt["record_sha256"] == record["record_sha256"]
            and receipt["resolution_binding_sha256"] == record["resolution_binding_sha256"]
            and receipt["terminal_evidence_sha256"] == record["terminal_evidence_sha256"]
            and receipt["terminal_state"] == record["terminal_state"]
            and receipt["resolved_at_epoch"] == record["resolved_at_epoch"]
            and receipt["durable_generation"] == durable_receipt.receipt["generation"]
            and receipt["resolution_state"] == "RESOLVED"
            and receipt["consumption_count"] == 1 == record["consumption_count"]
            and all(receipt[key] is True for key in (
                "atomic_wal_transition_verified", "restart_reconstructible",
                "idempotent_replay_supported", "registry_write",
                "temporary_filesystem_accessed", "synthetic_only",
            ))
            and all(receipt[key] is False for key in (
                "resolver_called", "barrier_called", "backend_called",
                "real_registry_accessed", "network_accessed", "broker_called",
                "production_authority", "production_durable", "runtime_integrated",
                "activation_allowed", "live_allowed",
            ))
            and receipt["write_executed"] is True
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and _valid_sha(receipt["receipt_sha256"])
            and hmac.compare_digest(
                receipt["receipt_sha256"],
                durable_resolution_commit_receipt_sha256_v2(receipt),
            )
        )
    except Exception:
        return False


class DormantDurableResolutionCommitContractV2:
    def __init__(
        self,
        config: DormantDurableResolutionCommitConfigV2 | None = None,
        *,
        protected_preparation: preparation_v2.ProtectedDurableResolutionPreparationV2 | None = None,
        durable_authority_ledger: durable_v2.DormantDurableReconciliationAuthorityLedgerV2 | None = None,
    ) -> None:
        self._config = config or DormantDurableResolutionCommitConfigV2()
        self._protected_preparation = protected_preparation
        self._durable_authority_ledger = durable_authority_ledger

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_RESOLUTION_COMMIT_V2_BLOCKED",
            "reason": reason,
            "protected_receipt": None,
            "same_preparation_instance_verified": False,
            "atomic_wal_transition_verified": False,
            "restart_reconstructible": False,
            "idempotent_replay": False,
            "filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
            "resolver_called": False,
            "barrier_called": False,
            "backend_called": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    def _config_reason(self, *, require_preparation: bool = True) -> str | None:
        if not self._config.enabled:
            return "DURABLE_RESOLUTION_COMMIT_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2:
            return "DURABLE_RESOLUTION_COMMIT_SCOPE_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                self._config.expected_preparation_sha256,
                self._config.expected_admission_sha256,
                self._config.expected_obligation_sha256,
                self._config.expected_pre_resolution_record_sha256,
                self._config.expected_terminal_evidence_sha256,
            )
        ):
            return "DURABLE_RESOLUTION_COMMIT_PINS_INVALID"
        if (
            require_preparation
            and type(self._protected_preparation)
            is not preparation_v2.ProtectedDurableResolutionPreparationV2
        ):
            return "PINNED_DURABLE_RESOLUTION_PREPARATION_REQUIRED"
        if type(self._durable_authority_ledger) is not durable_v2.DormantDurableReconciliationAuthorityLedgerV2:
            return "DURABLE_AUTHORITY_LEDGER_REQUIRED"
        return None

    @staticmethod
    def _protect_resolved(
        resolved: durable_v2.ProtectedDurableReconciliationAuthorityReceiptV2,
    ) -> ProtectedDurableResolutionCommitReceiptV2 | None:
        record = resolved.record
        receipt = {
            "receipt_version": DURABLE_RESOLUTION_COMMIT_RECEIPT_VERSION_V2,
            "scope_attestation": OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2,
            "preparation_sha256": record["preparation_sha256"],
            "admission_sha256": record["admission_sha256"],
            "obligation_sha256": record["obligation_sha256"],
            "obligation_id_sha256": record["obligation_id_sha256"],
            "source_evidence_sha256": record["resolution_source_evidence_sha256"],
            "adapter_plan_sha256": record["resolution_adapter_plan_sha256"],
            "request_binding_sha256": record["resolution_request_binding_sha256"],
            "request_sha256": record["resolution_request_sha256"],
            "transaction_sha256": record["transaction_sha256"],
            "pre_resolution_record_sha256": record["pre_resolution_record_sha256"],
            "resolved_record_sha256": resolved.receipt["record_sha256"],
            "resolution_binding_sha256": record["resolution_binding_sha256"],
            "terminal_evidence_sha256": record["terminal_evidence_sha256"],
            "terminal_state": record["terminal_state"],
            "resolved_at_epoch": record["resolved_at_epoch"],
            "durable_generation": resolved.receipt["generation"],
            "resolution_state": "RESOLVED",
            "consumption_count": 1,
            "atomic_wal_transition_verified": True,
            "restart_reconstructible": True,
            "idempotent_replay_supported": True,
            "resolver_called": False,
            "barrier_called": False,
            "backend_called": False,
            "registry_write": True,
            "temporary_filesystem_accessed": True,
            "write_executed": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "production_durable": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        receipt["receipt_sha256"] = durable_resolution_commit_receipt_sha256_v2(receipt)
        protected = ProtectedDurableResolutionCommitReceiptV2(
            resolved_durable_authority_receipt=resolved,
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )
        return (
            protected
            if protected_durable_resolution_commit_receipt_valid_v2(protected)
            else None
        )

    def commit_offline(
        self,
        protected_preparation: Any,
        *,
        now_epoch: int,
        fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if protected_preparation is not self._protected_preparation:
            return self._failed("DURABLE_RESOLUTION_PREPARATION_INSTANCE_NOT_PINNED")
        if not preparation_v2.protected_durable_resolution_preparation_valid_v2(protected_preparation):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_INVALID")
        if type(now_epoch) is not int:
            return self._failed("DURABLE_RESOLUTION_COMMIT_TIME_INVALID")
        prepared = protected_preparation.preparation
        if not prepared["prepared_at_epoch"] <= now_epoch < prepared["expires_at_epoch"]:
            return self._failed("DURABLE_RESOLUTION_PREPARATION_EXPIRED")
        config = self._config
        if (
            protected_preparation.preparation_sha256 != config.expected_preparation_sha256
            or prepared["admission_sha256"] != config.expected_admission_sha256
            or prepared["obligation_sha256"] != config.expected_obligation_sha256
            or prepared["durable_record_sha256"] != config.expected_pre_resolution_record_sha256
            or prepared["terminal_evidence_sha256"] != config.expected_terminal_evidence_sha256
        ):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_NOT_PINNED")
        fresh = protected_preparation.protected_admission.fresh_authority
        if not fresh.lease_witness.validate_live(
            fresh.maintenance_permit,
            fresh.live_lease_token,
            now_epoch=now_epoch,
        ):
            failed = self._failed("FRESH_QUIESCED_RECONCILIATION_LEASE_NOT_LIVE")
            failed["same_preparation_instance_verified"] = True
            return failed
        binding = self._durable_authority_ledger.bind_resolution_preparation_offline(
            protected_preparation
        )
        if binding.get("ok") is not True:
            failed = self._failed(
                str(binding.get("reason") or "DURABLE_RESOLUTION_PREPARATION_BINDING_FAILED")
            )
            failed["same_preparation_instance_verified"] = True
            return failed
        durable_result = self._durable_authority_ledger.resolve_once_offline(
            protected_preparation,
            fault_hook=fault_hook,
        )
        if durable_result.get("ok") is not True:
            failed = self._failed(str(durable_result.get("reason") or "DURABLE_RESOLUTION_WAL_COMMIT_FAILED"))
            failed["same_preparation_instance_verified"] = True
            failed["filesystem_accessed"] = durable_result.get("filesystem_accessed") is True
            failed["interprocess_lock_acquired"] = durable_result.get("interprocess_lock_acquired") is True
            failed["write_executed"] = durable_result.get("write_executed") is True
            return failed
        resolved = durable_result.get("protected_receipt")
        if (
            not durable_v2.protected_durable_reconciliation_authority_receipt_valid_v2(resolved)
            or resolved.receipt["state"] != "RESOLVED"
        ):
            failed = self._failed("RESOLVED_DURABLE_AUTHORITY_RECEIPT_INVALID")
            failed.update({"same_preparation_instance_verified": True, "filesystem_accessed": True, "interprocess_lock_acquired": True, "write_executed": durable_result.get("write_executed") is True})
            return failed
        protected = self._protect_resolved(resolved)
        if protected is None:
            failed = self._failed("DURABLE_RESOLUTION_COMMIT_RECEIPT_SELF_VALIDATION_FAILED")
            failed.update({"same_preparation_instance_verified": True, "atomic_wal_transition_verified": True, "filesystem_accessed": True, "interprocess_lock_acquired": True, "write_executed": durable_result.get("write_executed") is True})
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_COMMITTED_OFFLINE",
                "reason": None,
                "protected_receipt": protected,
                "same_preparation_instance_verified": True,
                "atomic_wal_transition_verified": True,
                "restart_reconstructible": True,
                "idempotent_replay": durable_result.get("write_executed") is False,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": durable_result.get("write_executed") is True,
            }
        )
        return result

    def recover_receipt_offline(self) -> dict[str, Any]:
        reason = self._config_reason(require_preparation=False)
        if reason is not None:
            return self._failed(reason)
        durable_result = self._durable_authority_ledger.read_resolved_offline(
            obligation_sha256=str(self._config.expected_obligation_sha256)
        )
        if durable_result.get("ok") is not True:
            failed = self._failed(
                str(durable_result.get("reason") or "DURABLE_RESOLUTION_NOT_FOUND")
            )
            failed["filesystem_accessed"] = durable_result.get("filesystem_accessed") is True
            failed["interprocess_lock_acquired"] = durable_result.get("interprocess_lock_acquired") is True
            return failed
        resolved = durable_result.get("protected_receipt")
        if (
            not durable_v2.protected_durable_reconciliation_authority_receipt_valid_v2(resolved)
            or resolved.receipt["state"] != "RESOLVED"
            or resolved.record["preparation_sha256"]
            != self._config.expected_preparation_sha256
            or resolved.record["admission_sha256"]
            != self._config.expected_admission_sha256
            or resolved.record["pre_resolution_record_sha256"]
            != self._config.expected_pre_resolution_record_sha256
            or resolved.record["terminal_evidence_sha256"]
            != self._config.expected_terminal_evidence_sha256
        ):
            failed = self._failed("DURABLE_RESOLUTION_RECOVERY_PINS_MISMATCH")
            failed.update(
                {
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        protected = self._protect_resolved(resolved)
        if protected is None:
            failed = self._failed("DURABLE_RESOLUTION_RECOVERED_RECEIPT_INVALID")
            failed.update(
                {
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_RECEIPT_RECOVERED_OFFLINE",
                "reason": None,
                "protected_receipt": protected,
                "atomic_wal_transition_verified": True,
                "restart_reconstructible": True,
                "idempotent_replay": True,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": False,
            }
        )
        return result


__all__ = [
    "DURABLE_RESOLUTION_COMMIT_RECEIPT_VERSION_V2",
    "DormantDurableResolutionCommitConfigV2",
    "DormantDurableResolutionCommitContractV2",
    "OFFLINE_DURABLE_RESOLUTION_COMMIT_SCOPE_ATTESTATION_V2",
    "ProtectedDurableResolutionCommitReceiptV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_COMMIT_CONTRACT_V2_VERSION",
    "durable_resolution_commit_receipt_sha256_v2",
    "protected_durable_resolution_commit_receipt_valid_v2",
]
