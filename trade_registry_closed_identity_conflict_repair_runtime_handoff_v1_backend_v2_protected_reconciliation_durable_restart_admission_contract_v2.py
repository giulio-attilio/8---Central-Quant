"""Dormant admission of a durable C3 reconciliation authority after restart.

The contract reads only caller-injected synthetic durable storage, proves that
the durable grant is still the current ISSUED record, and binds that proof to a
fresh quiesced in-memory authority.  It cannot call the restart barrier,
resolver, backend, broker, or runtime.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESTART-ADMISSION-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_TEMP_STORAGE_ONLY"
)
DURABLE_RESTART_ADMISSION_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ADMISSION_KEYS = frozenset(
    {
        "admission_version", "scope_attestation", "obligation_sha256",
        "obligation_id_sha256", "source_evidence_sha256",
        "adapter_plan_sha256", "request_binding_sha256",
        "transaction_sha256", "durable_root_identity_sha256",
        "durable_storage_binding_sha256", "durable_record_sha256",
        "durable_grant_sha256", "durable_issued_at_epoch",
        "durable_expires_at_epoch", "durable_current_generation",
        "fresh_authority_sha256", "fresh_authorization_receipt_sha256",
        "fresh_maintenance_epoch", "fresh_permit_binding_sha256",
        "fresh_lease_token_sha256", "fresh_session_anchor_identity_sha256",
        "fresh_authorization_issuer_identity_sha256",
        "fresh_single_use_ledger_identity_sha256", "admitted_at_epoch",
        "expires_at_epoch", "durable_authority_currently_issued_verified",
        "fresh_quiesced_lease_verified", "restart_admission_single_use_required",
        "downstream_current_state_revalidation_required",
        "original_process_session_reuse_allowed", "resolution_prepared",
        "barrier_call_allowed", "resolver_call_allowed",
        "resolution_authority_granted", "temporary_filesystem_accessed",
        "write_executed", "real_registry_accessed", "network_accessed",
        "broker_called", "production_authority", "production_durable",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "admission_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def durable_restart_admission_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "admission_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedDurableRestartAdmissionV2:
    obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(repr=False)
    durable_authority_receipt: durable_v2.ProtectedDurableReconciliationAuthorityReceiptV2 = field(repr=False)
    fresh_authority: resolution_v2.ProtectedFreshReconciliationAuthorityV2 = field(repr=False)
    admission: Mapping[str, Any] = field(repr=False)
    admission_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableRestartAdmissionV2(<protected>)"


@dataclass(frozen=True)
class DormantDurableRestartAdmissionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_durable_root_identity_sha256: str | None = field(default=None, repr=False)
    expected_durable_storage_binding_sha256: str | None = field(default=None, repr=False)
    expected_durable_record_sha256: str | None = field(default=None, repr=False)
    expected_fresh_authority_sha256: str | None = field(default=None, repr=False)
    maximum_authority_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_authority_ttl_seconds <= 300:
            raise ValueError("maximum_authority_ttl_seconds must be between 1 and 300")


def protected_durable_restart_admission_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableRestartAdmissionV2:
        return False
    obligation = value.obligation
    durable_receipt = value.durable_authority_receipt
    fresh = value.fresh_authority
    admission = value.admission
    if (
        not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation)
        or not durable_v2.protected_durable_reconciliation_authority_receipt_valid_v2(durable_receipt)
        or durable_receipt.receipt["state"] != "ISSUED"
        or type(admission) is not dict
        or set(admission) != _ADMISSION_KEYS
    ):
        return False
    record = obligation.obligation
    durable = durable_receipt.receipt
    authority = fresh.authority if type(fresh) is resolution_v2.ProtectedFreshReconciliationAuthorityV2 else {}
    try:
        return bool(
            resolution_v2.fresh_reconciliation_authority_valid_v2(
                fresh,
                obligation,
                now_epoch=admission["admitted_at_epoch"],
                maximum_ttl_seconds=300,
                expected_single_use_ledger=fresh.single_use_ledger,
                expected_authorization_issuer=fresh.authorization_issuer,
            )
            and admission["admission_version"] == DURABLE_RESTART_ADMISSION_VERSION_V2
            and admission["scope_attestation"] == OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2
            and admission["obligation_sha256"] == obligation.obligation_sha256 == durable["obligation_sha256"]
            and admission["obligation_id_sha256"] == record["obligation_id_sha256"]
            and admission["source_evidence_sha256"] == record["source_evidence_sha256"]
            and admission["adapter_plan_sha256"] == record["adapter_plan_sha256"]
            and admission["request_binding_sha256"] == record["request_binding_sha256"]
            and admission["transaction_sha256"] == record["transaction_sha256"] == durable["transaction_sha256"]
            and admission["durable_root_identity_sha256"] == durable["root_identity_sha256"]
            and admission["durable_storage_binding_sha256"] == durable["storage_binding_sha256"]
            and admission["durable_record_sha256"] == durable["record_sha256"]
            and admission["durable_grant_sha256"] == durable["grant_sha256"]
            and admission["durable_issued_at_epoch"] == durable_receipt.record["issued_at_epoch"]
            and admission["durable_expires_at_epoch"] == durable_receipt.record["expires_at_epoch"]
            and type(admission["durable_current_generation"]) is int
            and admission["durable_current_generation"] >= durable["generation"]
            and admission["fresh_authority_sha256"] == fresh.authority_sha256
            and admission["fresh_authorization_receipt_sha256"] == fresh.authorization_receipt["receipt_sha256"]
            and admission["fresh_maintenance_epoch"] == authority["maintenance_epoch"]
            and admission["fresh_permit_binding_sha256"] == authority["permit_binding_sha256"]
            and admission["fresh_lease_token_sha256"] == authority["lease_token_sha256"]
            and admission["fresh_session_anchor_identity_sha256"] == authority["process_session_anchor_object_identity_sha256"]
            and admission["fresh_authorization_issuer_identity_sha256"] == authority["authorization_issuer_object_identity_sha256"]
            and admission["fresh_single_use_ledger_identity_sha256"] == authority["single_use_ledger_object_identity_sha256"]
            and type(admission["admitted_at_epoch"]) is int
            and admission["admitted_at_epoch"] < admission["expires_at_epoch"]
            and admission["expires_at_epoch"] == min(durable_receipt.record["expires_at_epoch"], authority["expires_at_epoch"])
            and admission["durable_authority_currently_issued_verified"] is True
            and admission["fresh_quiesced_lease_verified"] is True
            and admission["restart_admission_single_use_required"] is True
            and admission["downstream_current_state_revalidation_required"] is True
            and admission["original_process_session_reuse_allowed"] is False
            and all(admission[key] is False for key in (
                "resolution_prepared", "barrier_call_allowed", "resolver_call_allowed",
                "resolution_authority_granted", "write_executed",
                "real_registry_accessed", "network_accessed", "broker_called",
                "production_authority", "production_durable", "runtime_integrated",
                "activation_allowed", "live_allowed",
            ))
            and admission["temporary_filesystem_accessed"] is True
            and admission["synthetic_only"] is True
            and value.admission_sha256 == admission["admission_sha256"]
            and _valid_sha(admission["admission_sha256"])
            and hmac.compare_digest(
                admission["admission_sha256"],
                durable_restart_admission_sha256_v2(admission),
            )
        )
    except Exception:
        return False


class DormantDurableRestartAdmissionContractV2:
    def __init__(
        self,
        config: DormantDurableRestartAdmissionConfigV2 | None = None,
        *,
        durable_authority_ledger: durable_v2.DormantDurableReconciliationAuthorityLedgerV2 | None = None,
    ) -> None:
        self._config = config or DormantDurableRestartAdmissionConfigV2()
        self._durable_authority_ledger = durable_authority_ledger

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_RESTART_ADMISSION_V2_BLOCKED",
            "reason": reason,
            "protected_admission": None,
            "durable_authority_currently_issued_verified": False,
            "fresh_quiesced_lease_verified": False,
            "temporary_filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
            "barrier_called": False,
            "resolver_called": False,
            "resolution_prepared": False,
            "resolution_authority_granted": False,
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
        config = self._config
        if not config.enabled:
            return "DURABLE_RESTART_ADMISSION_V2_DEFAULT_OFF"
        if config.scope_attestation != OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2:
            return "DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_INVALID"
        pins = (
            config.expected_obligation_sha256,
            config.expected_durable_root_identity_sha256,
            config.expected_durable_storage_binding_sha256,
            config.expected_durable_record_sha256,
            config.expected_fresh_authority_sha256,
        )
        if not all(_valid_sha(item) for item in pins):
            return "DURABLE_RESTART_ADMISSION_PINS_INVALID"
        if type(self._durable_authority_ledger) is not durable_v2.DormantDurableReconciliationAuthorityLedgerV2:
            return "DURABLE_AUTHORITY_LEDGER_REQUIRED"
        return None

    def issue_offline(
        self,
        obligation: Any,
        durable_authority_receipt: Any,
        fresh_authority: Any,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_INVALID")
        if type(now_epoch) is not int:
            return self._failed("DURABLE_RESTART_ADMISSION_TIME_INVALID")
        config = self._config
        if obligation.obligation_sha256 != config.expected_obligation_sha256:
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_NOT_PINNED")
        if not durable_v2.protected_durable_reconciliation_authority_receipt_valid_v2(durable_authority_receipt):
            return self._failed("DURABLE_AUTHORITY_RECEIPT_INVALID")
        durable = durable_authority_receipt.receipt
        if (
            durable["state"] != "ISSUED"
            or durable["obligation_sha256"] != obligation.obligation_sha256
            or durable["transaction_sha256"] != obligation.obligation["transaction_sha256"]
            or durable["root_identity_sha256"] != config.expected_durable_root_identity_sha256
            or durable["storage_binding_sha256"] != config.expected_durable_storage_binding_sha256
            or durable["record_sha256"] != config.expected_durable_record_sha256
        ):
            return self._failed("DURABLE_AUTHORITY_RECEIPT_NOT_PINNED")
        current = self._durable_authority_ledger.verify_current_issued_offline(
            durable_authority_receipt, now_epoch=now_epoch
        )
        if current.get("ok") is not True:
            failed = self._failed(str(current.get("reason") or "DURABLE_AUTHORITY_CURRENT_STATE_NOT_VERIFIED"))
            failed["temporary_filesystem_accessed"] = current.get("filesystem_accessed") is True
            failed["interprocess_lock_acquired"] = current.get("interprocess_lock_acquired") is True
            return failed
        if current["protected_receipt"].receipt["record_sha256"] != durable["record_sha256"]:
            failed = self._failed("DURABLE_AUTHORITY_CURRENT_RECORD_MISMATCH")
            failed.update({"temporary_filesystem_accessed": True, "interprocess_lock_acquired": True})
            return failed
        if (
            not resolution_v2.fresh_reconciliation_authority_valid_v2(
                fresh_authority,
                obligation,
                now_epoch=now_epoch,
                maximum_ttl_seconds=config.maximum_authority_ttl_seconds,
                expected_single_use_ledger=getattr(fresh_authority, "single_use_ledger", None),
                expected_authorization_issuer=getattr(fresh_authority, "authorization_issuer", None),
            )
            or fresh_authority.authority_sha256 != config.expected_fresh_authority_sha256
        ):
            failed = self._failed("FRESH_QUIESCED_RECONCILIATION_AUTHORITY_NOT_PINNED")
            failed.update({"temporary_filesystem_accessed": True, "interprocess_lock_acquired": True, "durable_authority_currently_issued_verified": True})
            return failed
        record = obligation.obligation
        authority = fresh_authority.authority
        admission = {
            "admission_version": DURABLE_RESTART_ADMISSION_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2,
            "obligation_sha256": obligation.obligation_sha256,
            "obligation_id_sha256": record["obligation_id_sha256"],
            "source_evidence_sha256": record["source_evidence_sha256"],
            "adapter_plan_sha256": record["adapter_plan_sha256"],
            "request_binding_sha256": record["request_binding_sha256"],
            "transaction_sha256": record["transaction_sha256"],
            "durable_root_identity_sha256": durable["root_identity_sha256"],
            "durable_storage_binding_sha256": durable["storage_binding_sha256"],
            "durable_record_sha256": durable["record_sha256"],
            "durable_grant_sha256": durable["grant_sha256"],
            "durable_issued_at_epoch": durable_authority_receipt.record["issued_at_epoch"],
            "durable_expires_at_epoch": durable_authority_receipt.record["expires_at_epoch"],
            "durable_current_generation": current["generation"],
            "fresh_authority_sha256": fresh_authority.authority_sha256,
            "fresh_authorization_receipt_sha256": fresh_authority.authorization_receipt["receipt_sha256"],
            "fresh_maintenance_epoch": authority["maintenance_epoch"],
            "fresh_permit_binding_sha256": authority["permit_binding_sha256"],
            "fresh_lease_token_sha256": authority["lease_token_sha256"],
            "fresh_session_anchor_identity_sha256": authority["process_session_anchor_object_identity_sha256"],
            "fresh_authorization_issuer_identity_sha256": authority["authorization_issuer_object_identity_sha256"],
            "fresh_single_use_ledger_identity_sha256": authority["single_use_ledger_object_identity_sha256"],
            "admitted_at_epoch": now_epoch,
            "expires_at_epoch": min(durable_authority_receipt.record["expires_at_epoch"], authority["expires_at_epoch"]),
            "durable_authority_currently_issued_verified": True,
            "fresh_quiesced_lease_verified": True,
            "restart_admission_single_use_required": True,
            "downstream_current_state_revalidation_required": True,
            "original_process_session_reuse_allowed": False,
            "resolution_prepared": False,
            "barrier_call_allowed": False,
            "resolver_call_allowed": False,
            "resolution_authority_granted": False,
            "temporary_filesystem_accessed": True,
            "write_executed": False,
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
        admission["admission_sha256"] = durable_restart_admission_sha256_v2(admission)
        protected = ProtectedDurableRestartAdmissionV2(
            obligation=obligation,
            durable_authority_receipt=durable_authority_receipt,
            fresh_authority=fresh_authority,
            admission=admission,
            admission_sha256=admission["admission_sha256"],
        )
        if not protected_durable_restart_admission_valid_v2(protected):
            failed = self._failed("DURABLE_RESTART_ADMISSION_SELF_VALIDATION_FAILED")
            failed.update({"temporary_filesystem_accessed": True, "interprocess_lock_acquired": True, "durable_authority_currently_issued_verified": True, "fresh_quiesced_lease_verified": True})
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESTART_ADMISSION_ISSUED_OFFLINE",
                "reason": None,
                "protected_admission": protected,
                "durable_authority_currently_issued_verified": True,
                "fresh_quiesced_lease_verified": True,
                "temporary_filesystem_accessed": True,
                "interprocess_lock_acquired": True,
            }
        )
        return result


__all__ = [
    "DURABLE_RESTART_ADMISSION_VERSION_V2",
    "DormantDurableRestartAdmissionConfigV2",
    "DormantDurableRestartAdmissionContractV2",
    "OFFLINE_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_SCOPE_ATTESTATION_V2",
    "ProtectedDurableRestartAdmissionV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESTART_ADMISSION_CONTRACT_V2_VERSION",
    "durable_restart_admission_sha256_v2",
    "protected_durable_restart_admission_valid_v2",
]
