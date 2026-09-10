"""Dormant, non-executable preparation bound to durable restart admission."""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_PREPARATION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-RESOLUTION-PREPARATION-CONTRACT-V2"
)
OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RESOLUTION_PREPARATION_TEMP_STORAGE_NON_EXECUTABLE_ONLY"
)
DURABLE_RESOLUTION_PREPARATION_VERSION_V2 = (
    "C3_DURABLE_RESOLUTION_PREPARATION_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PREPARATION_KEYS = frozenset(
    {
        "preparation_version", "scope_attestation", "admission_sha256",
        "obligation_sha256", "obligation_id_sha256", "source_evidence_sha256",
        "adapter_plan_sha256", "request_binding_sha256", "request_sha256",
        "transaction_sha256",
        "durable_root_identity_sha256", "durable_storage_binding_sha256",
        "durable_record_sha256", "durable_grant_sha256",
        "durable_current_generation", "fresh_authority_sha256",
        "fresh_authorization_receipt_sha256", "fresh_maintenance_epoch",
        "fresh_lease_token_sha256", "terminal_evidence_sha256",
        "terminal_state", "prepared_at_epoch", "expires_at_epoch",
        "exact_admission_instance_verified",
        "durable_authority_currently_issued_verified",
        "fresh_quiesced_lease_currently_live_verified",
        "terminal_evidence_verified", "durable_consumption_required",
        "durable_authority_consumed", "single_use_resolution_required",
        "resolver_call_allowed", "resolver_called", "barrier_called",
        "resolution_executed", "resolution_authority_granted",
        "temporary_filesystem_accessed", "write_executed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "production_authority", "production_durable", "runtime_integrated",
        "activation_allowed", "live_allowed", "synthetic_only",
        "preparation_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def durable_resolution_preparation_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "preparation_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedDurableResolutionPreparationV2:
    protected_admission: admission_v2.ProtectedDurableRestartAdmissionV2 = field(repr=False)
    terminal_resolution_evidence: Mapping[str, Any] = field(repr=False)
    preparation: Mapping[str, Any] = field(repr=False)
    preparation_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableResolutionPreparationV2(<protected>)"


@dataclass(frozen=True)
class DormantDurableResolutionPreparationConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_admission_sha256: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_durable_record_sha256: str | None = field(default=None, repr=False)
    expected_terminal_evidence_sha256: str | None = field(default=None, repr=False)


def protected_durable_resolution_preparation_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableResolutionPreparationV2:
        return False
    admission = value.protected_admission
    terminal = value.terminal_resolution_evidence
    preparation = value.preparation
    if (
        not admission_v2.protected_durable_restart_admission_valid_v2(admission)
        or type(preparation) is not dict
        or set(preparation) != _PREPARATION_KEYS
    ):
        return False
    admission_record = admission.admission
    obligation = admission.obligation
    fresh = admission.fresh_authority
    try:
        return bool(
            resolution_v2.terminal_resolution_evidence_valid_v2(
                terminal,
                obligation,
                fresh,
                now_epoch=preparation["prepared_at_epoch"],
            )
            and preparation["preparation_version"] == DURABLE_RESOLUTION_PREPARATION_VERSION_V2
            and preparation["scope_attestation"] == OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2
            and preparation["admission_sha256"] == admission.admission_sha256
            and preparation["obligation_sha256"] == admission_record["obligation_sha256"]
            and preparation["obligation_id_sha256"] == admission_record["obligation_id_sha256"]
            and preparation["source_evidence_sha256"] == admission_record["source_evidence_sha256"]
            and preparation["adapter_plan_sha256"] == admission_record["adapter_plan_sha256"]
            and preparation["request_binding_sha256"] == admission_record["request_binding_sha256"]
            and preparation["request_sha256"] == obligation.obligation["request_sha256"]
            and preparation["transaction_sha256"] == admission_record["transaction_sha256"]
            and preparation["durable_root_identity_sha256"] == admission_record["durable_root_identity_sha256"]
            and preparation["durable_storage_binding_sha256"] == admission_record["durable_storage_binding_sha256"]
            and preparation["durable_record_sha256"] == admission_record["durable_record_sha256"]
            and preparation["durable_grant_sha256"] == admission_record["durable_grant_sha256"]
            and type(preparation["durable_current_generation"]) is int
            and preparation["durable_current_generation"] >= admission_record["durable_current_generation"]
            and preparation["fresh_authority_sha256"] == admission_record["fresh_authority_sha256"]
            and preparation["fresh_authorization_receipt_sha256"] == admission_record["fresh_authorization_receipt_sha256"]
            and preparation["fresh_maintenance_epoch"] == admission_record["fresh_maintenance_epoch"]
            and preparation["fresh_lease_token_sha256"] == admission_record["fresh_lease_token_sha256"]
            and preparation["terminal_evidence_sha256"] == terminal["evidence_sha256"]
            and preparation["terminal_state"] == terminal["terminal_state"]
            and type(preparation["prepared_at_epoch"]) is int
            and preparation["prepared_at_epoch"] < preparation["expires_at_epoch"]
            and preparation["expires_at_epoch"] == admission_record["expires_at_epoch"]
            and all(preparation[key] is True for key in (
                "exact_admission_instance_verified",
                "durable_authority_currently_issued_verified",
                "fresh_quiesced_lease_currently_live_verified",
                "terminal_evidence_verified", "durable_consumption_required",
                "single_use_resolution_required", "temporary_filesystem_accessed",
                "synthetic_only",
            ))
            and all(preparation[key] is False for key in (
                "durable_authority_consumed", "resolver_call_allowed",
                "resolver_called", "barrier_called", "resolution_executed",
                "resolution_authority_granted", "write_executed",
                "real_registry_accessed", "network_accessed", "broker_called",
                "production_authority", "production_durable", "runtime_integrated",
                "activation_allowed", "live_allowed",
            ))
            and value.preparation_sha256 == preparation["preparation_sha256"]
            and _valid_sha(preparation["preparation_sha256"])
            and hmac.compare_digest(
                preparation["preparation_sha256"],
                durable_resolution_preparation_sha256_v2(preparation),
            )
        )
    except Exception:
        return False


class DormantDurableResolutionPreparationContractV2:
    def __init__(
        self,
        config: DormantDurableResolutionPreparationConfigV2 | None = None,
        *,
        protected_admission: admission_v2.ProtectedDurableRestartAdmissionV2 | None = None,
        durable_authority_ledger: durable_v2.DormantDurableReconciliationAuthorityLedgerV2 | None = None,
    ) -> None:
        self._config = config or DormantDurableResolutionPreparationConfigV2()
        self._protected_admission = protected_admission
        self._durable_authority_ledger = durable_authority_ledger

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_RESOLUTION_PREPARATION_V2_BLOCKED",
            "reason": reason,
            "protected_preparation": None,
            "exact_admission_instance_verified": False,
            "durable_authority_currently_issued_verified": False,
            "fresh_quiesced_lease_currently_live_verified": False,
            "terminal_evidence_verified": False,
            "temporary_filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
            "durable_authority_consumed": False,
            "resolver_called": False,
            "barrier_called": False,
            "resolution_executed": False,
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
        if not self._config.enabled:
            return "DURABLE_RESOLUTION_PREPARATION_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2:
            return "DURABLE_RESOLUTION_PREPARATION_SCOPE_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                self._config.expected_admission_sha256,
                self._config.expected_obligation_sha256,
                self._config.expected_durable_record_sha256,
                self._config.expected_terminal_evidence_sha256,
            )
        ):
            return "DURABLE_RESOLUTION_PREPARATION_PINS_INVALID"
        if type(self._protected_admission) is not admission_v2.ProtectedDurableRestartAdmissionV2:
            return "PINNED_DURABLE_RESTART_ADMISSION_REQUIRED"
        if type(self._durable_authority_ledger) is not durable_v2.DormantDurableReconciliationAuthorityLedgerV2:
            return "DURABLE_AUTHORITY_LEDGER_REQUIRED"
        return None

    def prepare_offline(
        self,
        protected_admission: Any,
        terminal_resolution_evidence: Any,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if protected_admission is not self._protected_admission:
            return self._failed("DURABLE_RESTART_ADMISSION_INSTANCE_NOT_PINNED")
        if not admission_v2.protected_durable_restart_admission_valid_v2(protected_admission):
            return self._failed("DURABLE_RESTART_ADMISSION_INVALID")
        if type(now_epoch) is not int:
            return self._failed("DURABLE_RESOLUTION_PREPARATION_TIME_INVALID")
        admission = protected_admission.admission
        config = self._config
        if (
            protected_admission.admission_sha256 != config.expected_admission_sha256
            or admission["obligation_sha256"] != config.expected_obligation_sha256
            or admission["durable_record_sha256"] != config.expected_durable_record_sha256
        ):
            return self._failed("DURABLE_RESTART_ADMISSION_NOT_PINNED")
        current = self._durable_authority_ledger.verify_current_issued_offline(
            protected_admission.durable_authority_receipt,
            now_epoch=now_epoch,
        )
        if current.get("ok") is not True:
            failed = self._failed(str(current.get("reason") or "DURABLE_AUTHORITY_CURRENT_STATE_NOT_VERIFIED"))
            failed["exact_admission_instance_verified"] = True
            failed["temporary_filesystem_accessed"] = current.get("filesystem_accessed") is True
            failed["interprocess_lock_acquired"] = current.get("interprocess_lock_acquired") is True
            return failed
        fresh = protected_admission.fresh_authority
        lease_live = fresh.lease_witness.validate_live(
            fresh.maintenance_permit,
            fresh.live_lease_token,
            now_epoch=now_epoch,
        )
        if not lease_live:
            failed = self._failed("FRESH_QUIESCED_RECONCILIATION_LEASE_NOT_LIVE")
            failed.update({"exact_admission_instance_verified": True, "durable_authority_currently_issued_verified": True, "temporary_filesystem_accessed": True, "interprocess_lock_acquired": True})
            return failed
        obligation = protected_admission.obligation
        if (
            not resolution_v2.terminal_resolution_evidence_valid_v2(
                terminal_resolution_evidence,
                obligation,
                fresh,
                now_epoch=now_epoch,
            )
            or terminal_resolution_evidence["evidence_sha256"] != config.expected_terminal_evidence_sha256
        ):
            failed = self._failed("TERMINAL_RESOLUTION_EVIDENCE_NOT_PINNED")
            failed.update({"exact_admission_instance_verified": True, "durable_authority_currently_issued_verified": True, "fresh_quiesced_lease_currently_live_verified": True, "temporary_filesystem_accessed": True, "interprocess_lock_acquired": True})
            return failed
        durable = protected_admission.durable_authority_receipt.receipt
        preparation = {
            "preparation_version": DURABLE_RESOLUTION_PREPARATION_VERSION_V2,
            "scope_attestation": OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2,
            "admission_sha256": protected_admission.admission_sha256,
            "obligation_sha256": admission["obligation_sha256"],
            "obligation_id_sha256": admission["obligation_id_sha256"],
            "source_evidence_sha256": admission["source_evidence_sha256"],
            "adapter_plan_sha256": admission["adapter_plan_sha256"],
            "request_binding_sha256": admission["request_binding_sha256"],
            "request_sha256": obligation.obligation["request_sha256"],
            "transaction_sha256": admission["transaction_sha256"],
            "durable_root_identity_sha256": admission["durable_root_identity_sha256"],
            "durable_storage_binding_sha256": admission["durable_storage_binding_sha256"],
            "durable_record_sha256": admission["durable_record_sha256"],
            "durable_grant_sha256": admission["durable_grant_sha256"],
            "durable_current_generation": current["generation"],
            "fresh_authority_sha256": admission["fresh_authority_sha256"],
            "fresh_authorization_receipt_sha256": admission["fresh_authorization_receipt_sha256"],
            "fresh_maintenance_epoch": admission["fresh_maintenance_epoch"],
            "fresh_lease_token_sha256": admission["fresh_lease_token_sha256"],
            "terminal_evidence_sha256": terminal_resolution_evidence["evidence_sha256"],
            "terminal_state": terminal_resolution_evidence["terminal_state"],
            "prepared_at_epoch": now_epoch,
            "expires_at_epoch": admission["expires_at_epoch"],
            "exact_admission_instance_verified": True,
            "durable_authority_currently_issued_verified": True,
            "fresh_quiesced_lease_currently_live_verified": True,
            "terminal_evidence_verified": True,
            "durable_consumption_required": True,
            "durable_authority_consumed": False,
            "single_use_resolution_required": True,
            "resolver_call_allowed": False,
            "resolver_called": False,
            "barrier_called": False,
            "resolution_executed": False,
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
        preparation["preparation_sha256"] = durable_resolution_preparation_sha256_v2(preparation)
        protected = ProtectedDurableResolutionPreparationV2(
            protected_admission=protected_admission,
            terminal_resolution_evidence=terminal_resolution_evidence,
            preparation=preparation,
            preparation_sha256=preparation["preparation_sha256"],
        )
        if not protected_durable_resolution_preparation_valid_v2(protected):
            failed = self._failed("DURABLE_RESOLUTION_PREPARATION_SELF_VALIDATION_FAILED")
            failed.update({"exact_admission_instance_verified": True, "durable_authority_currently_issued_verified": True, "fresh_quiesced_lease_currently_live_verified": True, "terminal_evidence_verified": True, "temporary_filesystem_accessed": True, "interprocess_lock_acquired": True})
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_PREPARATION_ISSUED_OFFLINE",
                "reason": None,
                "protected_preparation": protected,
                "exact_admission_instance_verified": True,
                "durable_authority_currently_issued_verified": True,
                "fresh_quiesced_lease_currently_live_verified": True,
                "terminal_evidence_verified": True,
                "temporary_filesystem_accessed": True,
                "interprocess_lock_acquired": True,
            }
        )
        return result


__all__ = [
    "DURABLE_RESOLUTION_PREPARATION_VERSION_V2",
    "DormantDurableResolutionPreparationConfigV2",
    "DormantDurableResolutionPreparationContractV2",
    "OFFLINE_DURABLE_RESOLUTION_PREPARATION_SCOPE_ATTESTATION_V2",
    "ProtectedDurableResolutionPreparationV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_RESOLUTION_PREPARATION_CONTRACT_V2_VERSION",
    "durable_resolution_preparation_sha256_v2",
    "protected_durable_resolution_preparation_valid_v2",
]
