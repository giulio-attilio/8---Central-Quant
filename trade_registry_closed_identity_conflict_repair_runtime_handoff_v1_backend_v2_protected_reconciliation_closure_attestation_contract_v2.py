"""Dormant immutable closure attestation for a resolved C3 obligation."""

from __future__ import annotations

import copy
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import registry_v2_wal as wal_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2 as envelope_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_CLOSURE_ATTESTATION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-CLOSURE-ATTESTATION-CONTRACT-V2"
)
OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2 = (
    "C3_RECONCILIATION_CLOSURE_ATTESTATION_IMMUTABLE_OFFLINE_ONLY"
)
RECONCILIATION_CLOSURE_ATTESTATION_VERSION_V2 = (
    "C3_RECONCILIATION_CLOSURE_ATTESTATION_V2"
)
DURABLE_CLOSURE_PROJECTION_SCOPE_V2 = (
    "C3_RECONCILIATION_CLOSURE_DURABLE_PROJECTION_TEMP_STORAGE_ONLY"
)
DURABLE_CLOSURE_PROJECTION_LEDGER_VERSION_V2 = (
    "C3_RECONCILIATION_CLOSURE_PROJECTION_LEDGER_V2"
)
DURABLE_CLOSURE_PROJECTION_RECORD_VERSION_V2 = (
    "C3_RECONCILIATION_CLOSURE_PROJECTION_RECORD_V2"
)
DURABLE_CLOSURE_PROJECTION_RECEIPT_VERSION_V2 = (
    "C3_RECONCILIATION_CLOSURE_PROJECTION_RECEIPT_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version", "scope_attestation", "closure_id_sha256",
        "idempotency_key_sha256", "obligation_sha256", "obligation_id_sha256",
        "outcome_envelope_sha256", "source_kind", "source_receipt_sha256",
        "source_evidence_sha256", "adapter_plan_sha256",
        "request_binding_sha256", "request_sha256", "transaction_sha256",
        "terminal_resolution_evidence_sha256", "terminal_state",
        "resolved_at_epoch", "closed_at_epoch", "obligation_original_state",
        "closure_state", "resolution_state", "reconciliation_required",
        "same_transaction_identity_verified", "terminal_resolution_verified",
        "obligation_preserved_immutable", "exact_obligation_instance_verified",
        "exact_envelope_instance_verified", "deterministic_reissue",
        "new_apply_allowed", "retry_allowed", "state_update_allowed",
        "runtime_mutation_allowed", "registry_write", "write_executed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "attestation_sha256",
    }
)
_IDENTITY_FIELDS = (
    "obligation_sha256", "obligation_id_sha256", "source_evidence_sha256",
    "adapter_plan_sha256", "request_binding_sha256", "request_sha256",
    "transaction_sha256",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def reconciliation_closure_attestation_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "attestation_sha256"}
    )


def _closure_id(obligation_sha256: str, envelope_sha256: str, source_receipt_sha256: str) -> str:
    return hash_v2.stable_sha256_v2(
        {
            "kind": "C3_RECONCILIATION_CLOSURE_ID_V2",
            "obligation_sha256": obligation_sha256,
            "outcome_envelope_sha256": envelope_sha256,
            "source_receipt_sha256": source_receipt_sha256,
        }
    )


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationClosureAttestationV2:
    original_obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(repr=False)
    outcome_envelope: envelope_v2.ProtectedResolutionOutcomeEnvelopeV2 = field(repr=False)
    attestation: Mapping[str, Any] = field(repr=False)
    attestation_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationClosureAttestationV2(<protected>)"


@dataclass(frozen=True)
class DormantReconciliationClosureAttestationConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_outcome_envelope_sha256: str | None = field(default=None, repr=False)
    expected_source_receipt_sha256: str | None = field(default=None, repr=False)
    expected_transaction_sha256: str | None = field(default=None, repr=False)


def protected_reconciliation_closure_attestation_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedReconciliationClosureAttestationV2:
        return False
    obligation = value.original_obligation
    outcome = value.outcome_envelope
    attestation = value.attestation
    if (
        not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation)
        or not envelope_v2.protected_resolution_outcome_envelope_valid_v2(outcome)
        or type(attestation) is not dict
        or set(attestation) != _ATTESTATION_KEYS
    ):
        return False
    original = obligation.obligation
    envelope = outcome.envelope
    is_legacy = envelope["source_kind"] == envelope_v2.ORIGINAL_SESSION_RECEIPT_SOURCE_V2
    try:
        return bool(
            (not is_legacy or outcome.native_source_receipt.obligation is obligation)
            and all(envelope[key] == original[key] for key in _IDENTITY_FIELDS)
            and attestation["attestation_version"] == RECONCILIATION_CLOSURE_ATTESTATION_VERSION_V2
            and attestation["scope_attestation"] == OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2
            and attestation["closure_id_sha256"] == _closure_id(obligation.obligation_sha256, outcome.envelope_sha256, envelope["source_receipt_sha256"])
            and attestation["idempotency_key_sha256"] == attestation["closure_id_sha256"]
            and all(attestation[key] == envelope[key] == original[key] for key in _IDENTITY_FIELDS)
            and attestation["outcome_envelope_sha256"] == outcome.envelope_sha256
            and attestation["source_kind"] == envelope["source_kind"]
            and attestation["source_receipt_sha256"] == envelope["source_receipt_sha256"]
            and attestation["terminal_resolution_evidence_sha256"] == envelope["terminal_resolution_evidence_sha256"]
            and attestation["terminal_state"] == envelope["terminal_state"]
            and attestation["resolved_at_epoch"] == envelope["resolved_at_epoch"]
            and attestation["closed_at_epoch"] == envelope["resolved_at_epoch"]
            and attestation["closed_at_epoch"] >= original["created_at_epoch"]
            and attestation["obligation_original_state"] == "UNRESOLVED" == original["resolution_state"]
            and attestation["closure_state"] == "RECONCILIATION_CLOSED_ATTESTED"
            and attestation["resolution_state"] == "RESOLVED"
            and attestation["reconciliation_required"] is False
            and all(attestation[key] is True for key in (
                "same_transaction_identity_verified", "terminal_resolution_verified",
                "obligation_preserved_immutable", "exact_obligation_instance_verified",
                "exact_envelope_instance_verified", "deterministic_reissue",
                "synthetic_only",
            ))
            and all(attestation[key] is False for key in (
                "new_apply_allowed", "retry_allowed", "state_update_allowed",
                "runtime_mutation_allowed", "registry_write", "write_executed",
                "real_registry_accessed", "network_accessed", "broker_called",
                "runtime_integrated", "activation_allowed", "live_allowed",
            ))
            and value.attestation_sha256 == attestation["attestation_sha256"]
            and _valid_sha(attestation["attestation_sha256"])
            and hmac.compare_digest(
                attestation["attestation_sha256"],
                reconciliation_closure_attestation_sha256_v2(attestation),
            )
        )
    except Exception:
        return False


class DormantReconciliationClosureAttestationContractV2:
    def __init__(
        self,
        config: DormantReconciliationClosureAttestationConfigV2 | None = None,
        *,
        original_obligation: obligation_v2.ProtectedReconciliationObligationV2 | None = None,
        outcome_envelope: envelope_v2.ProtectedResolutionOutcomeEnvelopeV2 | None = None,
    ) -> None:
        self._config = config or DormantReconciliationClosureAttestationConfigV2()
        self._original_obligation = original_obligation
        self._outcome_envelope = outcome_envelope

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "RECONCILIATION_CLOSURE_ATTESTATION_V2_BLOCKED",
            "reason": reason,
            "protected_attestation": None,
            "obligation_preserved_immutable": False,
            "state_update_allowed": False,
            "runtime_mutation_allowed": False,
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
            return "RECONCILIATION_CLOSURE_ATTESTATION_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2:
            return "RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                self._config.expected_obligation_sha256,
                self._config.expected_outcome_envelope_sha256,
                self._config.expected_source_receipt_sha256,
                self._config.expected_transaction_sha256,
            )
        ):
            return "RECONCILIATION_CLOSURE_ATTESTATION_PINS_INVALID"
        if type(self._original_obligation) is not obligation_v2.ProtectedReconciliationObligationV2:
            return "PINNED_ORIGINAL_OBLIGATION_REQUIRED"
        if type(self._outcome_envelope) is not envelope_v2.ProtectedResolutionOutcomeEnvelopeV2:
            return "PINNED_OUTCOME_ENVELOPE_REQUIRED"
        return None

    def issue_offline(self, original_obligation: Any, outcome_envelope: Any) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if original_obligation is not self._original_obligation:
            return self._failed("ORIGINAL_OBLIGATION_INSTANCE_NOT_PINNED")
        if outcome_envelope is not self._outcome_envelope:
            return self._failed("OUTCOME_ENVELOPE_INSTANCE_NOT_PINNED")
        if not obligation_v2.protected_reconciliation_obligation_valid_v2(original_obligation):
            return self._failed("ORIGINAL_OBLIGATION_INVALID")
        if not envelope_v2.protected_resolution_outcome_envelope_valid_v2(outcome_envelope):
            return self._failed("OUTCOME_ENVELOPE_INVALID")
        original = original_obligation.obligation
        envelope = outcome_envelope.envelope
        if (
            original_obligation.obligation_sha256 != self._config.expected_obligation_sha256
            or outcome_envelope.envelope_sha256 != self._config.expected_outcome_envelope_sha256
            or envelope["source_receipt_sha256"] != self._config.expected_source_receipt_sha256
            or original["transaction_sha256"] != self._config.expected_transaction_sha256
        ):
            return self._failed("RECONCILIATION_CLOSURE_INPUT_NOT_PINNED")
        if not all(envelope[key] == original[key] for key in _IDENTITY_FIELDS):
            return self._failed("OBLIGATION_OUTCOME_IDENTITY_MISMATCH")
        if (
            envelope["source_kind"] == envelope_v2.ORIGINAL_SESSION_RECEIPT_SOURCE_V2
            and outcome_envelope.native_source_receipt.obligation is not original_obligation
        ):
            return self._failed("LEGACY_SOURCE_OBLIGATION_INSTANCE_MISMATCH")
        closure_id = _closure_id(
            original_obligation.obligation_sha256,
            outcome_envelope.envelope_sha256,
            envelope["source_receipt_sha256"],
        )
        attestation = {
            "attestation_version": RECONCILIATION_CLOSURE_ATTESTATION_VERSION_V2,
            "scope_attestation": OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2,
            "closure_id_sha256": closure_id,
            "idempotency_key_sha256": closure_id,
            "obligation_sha256": original["obligation_sha256"],
            "obligation_id_sha256": original["obligation_id_sha256"],
            "outcome_envelope_sha256": outcome_envelope.envelope_sha256,
            "source_kind": envelope["source_kind"],
            "source_receipt_sha256": envelope["source_receipt_sha256"],
            "source_evidence_sha256": original["source_evidence_sha256"],
            "adapter_plan_sha256": original["adapter_plan_sha256"],
            "request_binding_sha256": original["request_binding_sha256"],
            "request_sha256": original["request_sha256"],
            "transaction_sha256": original["transaction_sha256"],
            "terminal_resolution_evidence_sha256": envelope["terminal_resolution_evidence_sha256"],
            "terminal_state": envelope["terminal_state"],
            "resolved_at_epoch": envelope["resolved_at_epoch"],
            "closed_at_epoch": envelope["resolved_at_epoch"],
            "obligation_original_state": "UNRESOLVED",
            "closure_state": "RECONCILIATION_CLOSED_ATTESTED",
            "resolution_state": "RESOLVED",
            "reconciliation_required": False,
            "same_transaction_identity_verified": True,
            "terminal_resolution_verified": True,
            "obligation_preserved_immutable": True,
            "exact_obligation_instance_verified": True,
            "exact_envelope_instance_verified": True,
            "deterministic_reissue": True,
            "new_apply_allowed": False,
            "retry_allowed": False,
            "state_update_allowed": False,
            "runtime_mutation_allowed": False,
            "registry_write": False,
            "write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        attestation["attestation_sha256"] = reconciliation_closure_attestation_sha256_v2(attestation)
        protected = ProtectedReconciliationClosureAttestationV2(
            original_obligation=original_obligation,
            outcome_envelope=outcome_envelope,
            attestation=attestation,
            attestation_sha256=attestation["attestation_sha256"],
        )
        if not protected_reconciliation_closure_attestation_valid_v2(protected):
            return self._failed("RECONCILIATION_CLOSURE_ATTESTATION_SELF_VALIDATION_FAILED")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "RECONCILIATION_CLOSURE_ATTESTED_OFFLINE",
                "reason": None,
                "protected_attestation": protected,
                "obligation_preserved_immutable": True,
            }
        )
        return result


_CLOSURE_PROJECTION_RECORD_KEYS = frozenset(
    {
        "record_version", "closure_id_sha256", "obligation_sha256",
        "obligation_id_sha256", "closure_attestation_sha256",
        "outcome_envelope_sha256", "source_receipt_sha256",
        "transaction_sha256", "resolution_state", "reconciliation_required",
        "retry_allowed", "committed_at_epoch", "synthetic_only",
        "production_authority", "record_sha256",
    }
)
_CLOSURE_PROJECTION_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "storage_binding_sha256", "record_sha256",
        "closure_id_sha256", "obligation_sha256", "generation",
        "restart_reconstructible", "synthetic_only", "production_durable",
        "runtime_integrated", "receipt_sha256",
    }
)


def durable_closure_projection_storage_binding_sha256_v2(
    storage: wal_v2.RegistryV2WalStorage,
) -> str:
    return hash_v2.stable_sha256_v2(
        {
            "snapshot_path": str(Path(storage.snapshot_path).resolve(strict=False)),
            "journal_path": str(Path(storage.journal_path).resolve(strict=False)),
            "lock_path": str(Path(storage.lock_path).resolve(strict=False)),
            "backup_dir": str(Path(storage.backup_dir).resolve(strict=False)),
        }
    )


def durable_closure_projection_record_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "record_sha256"}
    )


def durable_closure_projection_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def durable_closure_projection_record_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _CLOSURE_PROJECTION_RECORD_KEYS:
        return False
    try:
        return bool(
            value["record_version"] == DURABLE_CLOSURE_PROJECTION_RECORD_VERSION_V2
            and all(
                _valid_sha(value[key])
                for key in (
                    "closure_id_sha256", "obligation_sha256",
                    "obligation_id_sha256", "closure_attestation_sha256",
                    "outcome_envelope_sha256", "source_receipt_sha256",
                    "transaction_sha256", "record_sha256",
                )
            )
            and value["resolution_state"] == "RESOLVED"
            and value["reconciliation_required"] is False
            and value["retry_allowed"] is False
            and type(value["committed_at_epoch"]) is int
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and hmac.compare_digest(
                value["record_sha256"],
                durable_closure_projection_record_sha256_v2(value),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True, repr=False)
class ProtectedDurableClosureProjectionReceiptV2:
    record: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableClosureProjectionReceiptV2(<protected>)"


def protected_durable_closure_projection_receipt_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableClosureProjectionReceiptV2:
        return False
    record = value.record
    receipt = value.receipt
    if type(receipt) is not dict or set(receipt) != _CLOSURE_PROJECTION_RECEIPT_KEYS:
        return False
    try:
        return bool(
            durable_closure_projection_record_valid_v2(record)
            and receipt["receipt_version"]
            == DURABLE_CLOSURE_PROJECTION_RECEIPT_VERSION_V2
            and _valid_sha(receipt["storage_binding_sha256"])
            and receipt["record_sha256"] == record["record_sha256"]
            and receipt["closure_id_sha256"] == record["closure_id_sha256"]
            and receipt["obligation_sha256"] == record["obligation_sha256"]
            and type(receipt["generation"]) is int
            and receipt["generation"] >= 1
            and receipt["restart_reconstructible"] is True
            and receipt["synthetic_only"] is True
            and receipt["production_durable"] is False
            and receipt["runtime_integrated"] is False
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and hmac.compare_digest(
                receipt["receipt_sha256"],
                durable_closure_projection_receipt_sha256_v2(receipt),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantDurableClosureProjectionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_storage_binding_sha256: str | None = field(default=None, repr=False)
    expected_closure_attestation_sha256: str | None = field(
        default=None, repr=False
    )
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.lock_timeout_seconds <= 5:
            raise ValueError("lock_timeout_seconds must be between 0 and 5")


class _ClosureProjectionHeldLockV2:
    def __init__(self, handle: storage_v1.InterprocessFileLockHandleV1) -> None:
        self._handle = handle

    def __enter__(self) -> "_ClosureProjectionHeldLockV2":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._handle.release()


class DormantDurableClosureProjectionLedgerV2:
    """Temporary-WAL closure index; it never mutates the original obligation."""

    def __init__(
        self,
        config: DormantDurableClosureProjectionConfigV2 | None = None,
        *,
        protected_attestation: ProtectedReconciliationClosureAttestationV2 | None = None,
        storage: wal_v2.RegistryV2WalStorage | None = None,
        lock_backend: storage_v1.CrossPlatformInterprocessFileLockBackendV1 | None = None,
    ) -> None:
        self._config = config or DormantDurableClosureProjectionConfigV2()
        self._protected_attestation = protected_attestation
        self._storage = storage
        self._lock_backend = lock_backend

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_CLOSURE_PROJECTION_V2_BLOCKED",
            "reason": reason,
            "protected_receipt": None,
            "effective_resolution_state": None,
            "effective_reconciliation_required": True,
            "generation": None,
            "wal_state": None,
            "filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "production_durable": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    def _config_reason(self, *, require_attestation: bool = True) -> str | None:
        if self._config.enabled is not True:
            return "DURABLE_CLOSURE_PROJECTION_V2_DEFAULT_OFF"
        if self._config.scope_attestation != DURABLE_CLOSURE_PROJECTION_SCOPE_V2:
            return "DURABLE_CLOSURE_PROJECTION_SCOPE_INVALID"
        if not _valid_sha(self._config.expected_storage_binding_sha256):
            return "DURABLE_CLOSURE_PROJECTION_STORAGE_BINDING_REQUIRED"
        if require_attestation and not _valid_sha(
            self._config.expected_closure_attestation_sha256
        ):
            return "DURABLE_CLOSURE_PROJECTION_ATTESTATION_PIN_REQUIRED"
        if type(self._storage) is not wal_v2.RegistryV2WalStorage:
            return "DURABLE_CLOSURE_PROJECTION_STORAGE_REQUIRED"
        if type(self._lock_backend) is not storage_v1.CrossPlatformInterprocessFileLockBackendV1:
            return "DURABLE_CLOSURE_PROJECTION_LOCK_REQUIRED"
        if self._lock_backend.enabled is not True:
            return "DURABLE_CLOSURE_PROJECTION_LOCK_DEFAULT_OFF"
        if not hmac.compare_digest(
            self._config.expected_storage_binding_sha256,
            durable_closure_projection_storage_binding_sha256_v2(self._storage),
        ):
            return "DURABLE_CLOSURE_PROJECTION_STORAGE_BINDING_MISMATCH"
        if require_attestation and (
            type(self._protected_attestation)
            is not ProtectedReconciliationClosureAttestationV2
            or not protected_reconciliation_closure_attestation_valid_v2(
                self._protected_attestation
            )
            or self._protected_attestation.attestation_sha256
            != self._config.expected_closure_attestation_sha256
        ):
            return "DURABLE_CLOSURE_PROJECTION_ATTESTATION_INVALID"
        return None

    def _acquire(self) -> _ClosureProjectionHeldLockV2 | None:
        handle = self._lock_backend.acquire(
            self._config.expected_storage_binding_sha256,
            self._config.lock_timeout_seconds,
        )
        return _ClosureProjectionHeldLockV2(handle) if handle is not None else None

    def _read_snapshot(self) -> dict[str, Any] | None:
        path = Path(self._storage.snapshot_path)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if type(value) is not dict:
            raise ValueError("DURABLE_CLOSURE_PROJECTION_SNAPSHOT_MAPPING_REQUIRED")
        integrity = value.get("integrity")
        if (
            not isinstance(integrity, Mapping)
            or integrity.get("snapshot_digest")
            != wal_v2.compute_snapshot_digest(value)
        ):
            raise ValueError("DURABLE_CLOSURE_PROJECTION_SNAPSHOT_INTEGRITY_INVALID")
        return value

    def _snapshot_valid(self, snapshot: Any) -> bool:
        try:
            records = snapshot["closures"]
            return bool(
                type(snapshot) is dict
                and snapshot["ledger_version"]
                == DURABLE_CLOSURE_PROJECTION_LEDGER_VERSION_V2
                and snapshot["storage_binding_sha256"]
                == self._config.expected_storage_binding_sha256
                and type(snapshot["generation"]) is int
                and snapshot["generation"] >= 0
                and type(records) is dict
                and all(
                    key == record.get("obligation_sha256")
                    and durable_closure_projection_record_valid_v2(record)
                    for key, record in records.items()
                )
                and snapshot["synthetic_only"] is True
                and snapshot["production_durable"] is False
            )
        except Exception:
            return False

    def _read_valid_locked(self) -> tuple[dict[str, Any] | None, str | None]:
        try:
            snapshot = self._read_snapshot()
        except Exception:
            return None, "DURABLE_CLOSURE_PROJECTION_SNAPSHOT_READ_FAILED"
        if not self._snapshot_valid(snapshot):
            return None, "DURABLE_CLOSURE_PROJECTION_SNAPSHOT_INVALID"
        if wal_v2.inspect_wal_recovery_state(self._storage).status != wal_v2.CLEAN:
            return None, "DURABLE_CLOSURE_PROJECTION_WAL_RECOVERY_REQUIRED"
        return snapshot, None

    @staticmethod
    def _apply_mutation(
        snapshot: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        candidate = copy.deepcopy(dict(snapshot))
        records = copy.deepcopy(dict(candidate.get("closures") or {}))
        records[payload["obligation_sha256"]] = copy.deepcopy(
            dict(payload["record"])
        )
        candidate["closures"] = records
        return candidate

    def _protect(
        self, record: Mapping[str, Any], generation: int
    ) -> ProtectedDurableClosureProjectionReceiptV2:
        receipt = {
            "receipt_version": DURABLE_CLOSURE_PROJECTION_RECEIPT_VERSION_V2,
            "storage_binding_sha256": self._config.expected_storage_binding_sha256,
            "record_sha256": record["record_sha256"],
            "closure_id_sha256": record["closure_id_sha256"],
            "obligation_sha256": record["obligation_sha256"],
            "generation": generation,
            "restart_reconstructible": True,
            "synthetic_only": True,
            "production_durable": False,
            "runtime_integrated": False,
        }
        receipt["receipt_sha256"] = durable_closure_projection_receipt_sha256_v2(
            receipt
        )
        return ProtectedDurableClosureProjectionReceiptV2(
            record=copy.deepcopy(dict(record)),
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

    def open_offline(self) -> dict[str, Any]:
        reason = self._config_reason(require_attestation=False)
        if reason is not None:
            return self._failed(reason)
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        try:
            with lock:
                snapshot = self._read_snapshot()
                if snapshot is None:
                    snapshot = {
                        "ledger_version": DURABLE_CLOSURE_PROJECTION_LEDGER_VERSION_V2,
                        "storage_binding_sha256": self._config.expected_storage_binding_sha256,
                        "generation": 0,
                        "closures": {},
                        "synthetic_only": True,
                        "production_durable": False,
                    }
                    wal_v2.write_initial_snapshot(self._storage, snapshot)
                    wrote = True
                else:
                    wrote = False
                if not self._snapshot_valid(self._read_snapshot()):
                    return self._failed("DURABLE_CLOSURE_PROJECTION_SNAPSHOT_INVALID")
        except Exception:
            return self._failed("DURABLE_CLOSURE_PROJECTION_STORAGE_OPEN_FAILED")
        result = self._failed("")
        result.update(
            ok=True,
            status="DURABLE_CLOSURE_PROJECTION_OPENED_OFFLINE",
            reason=None,
            generation=snapshot["generation"],
            wal_state=wal_v2.CLEAN,
            filesystem_accessed=True,
            interprocess_lock_acquired=True,
            write_executed=wrote,
        )
        return result

    def commit_once_offline(
        self,
        protected_attestation: Any,
        *,
        fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if protected_attestation is not self._protected_attestation:
            return self._failed("CLOSURE_ATTESTATION_INSTANCE_NOT_PINNED")
        attestation = protected_attestation.attestation
        record = {
            "record_version": DURABLE_CLOSURE_PROJECTION_RECORD_VERSION_V2,
            "closure_id_sha256": attestation["closure_id_sha256"],
            "obligation_sha256": attestation["obligation_sha256"],
            "obligation_id_sha256": attestation["obligation_id_sha256"],
            "closure_attestation_sha256": protected_attestation.attestation_sha256,
            "outcome_envelope_sha256": attestation["outcome_envelope_sha256"],
            "source_receipt_sha256": attestation["source_receipt_sha256"],
            "transaction_sha256": attestation["transaction_sha256"],
            "resolution_state": "RESOLVED",
            "reconciliation_required": False,
            "retry_allowed": False,
            "committed_at_epoch": attestation["closed_at_epoch"],
            "synthetic_only": True,
            "production_authority": False,
        }
        record["record_sha256"] = durable_closure_projection_record_sha256_v2(
            record
        )
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        existing = snapshot["closures"].get(record["obligation_sha256"])
        if existing is not None:
            if existing != record:
                return self._failed("DURABLE_CLOSURE_PROJECTION_CONFLICT")
            protected = self._protect(existing, snapshot["generation"])
            result = self._failed("")
            result.update(
                ok=True,
                status="DURABLE_CLOSURE_PROJECTION_ALREADY_COMMITTED",
                reason=None,
                protected_receipt=protected,
                effective_resolution_state="RESOLVED",
                effective_reconciliation_required=False,
                generation=snapshot["generation"],
                wal_state=wal_v2.CLEAN,
                filesystem_accessed=True,
                interprocess_lock_acquired=True,
            )
            return result
        payload = {
            "mutation_kind": "COMMIT_CLOSURE_PROJECTION",
            "obligation_sha256": record["obligation_sha256"],
            "record": record,
        }
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        try:
            applied = wal_v2.apply_temp_wal_mutation(
                self._storage,
                snapshot,
                payload,
                "DURABLE_CLOSURE_PROJECTION_COMMIT",
                record["obligation_sha256"],
                None,
                record["closure_id_sha256"],
                snapshot["generation"],
                self._apply_mutation,
                fault_hook=fault_hook,
                lock=lock,
                schema_version=DURABLE_CLOSURE_PROJECTION_LEDGER_VERSION_V2,
            )
        except Exception:
            failed = self._failed("DURABLE_CLOSURE_PROJECTION_INTERRUPTED")
            failed.update(
                filesystem_accessed=True,
                interprocess_lock_acquired=True,
                write_executed=True,
                wal_state=wal_v2.WAL_RECOVERY_REQUIRED,
            )
            return failed
        if not applied.ok:
            return self._failed("DURABLE_CLOSURE_PROJECTION_WAL_REJECTED")
        committed = self.read_closure_offline(record["obligation_sha256"])
        if committed.get("ok") is True:
            committed.update(
                status="DURABLE_CLOSURE_PROJECTION_COMMITTED_OFFLINE",
                write_executed=True,
            )
        return committed

    def read_closure_offline(self, obligation_sha256: str) -> dict[str, Any]:
        reason = self._config_reason(require_attestation=False)
        if reason is not None:
            return self._failed(reason)
        if not _valid_sha(obligation_sha256):
            return self._failed("DURABLE_CLOSURE_PROJECTION_LOOKUP_INVALID")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        record = snapshot["closures"].get(obligation_sha256)
        if record is None:
            return self._failed("DURABLE_CLOSURE_PROJECTION_NOT_FOUND")
        protected = self._protect(record, snapshot["generation"])
        result = self._failed("")
        result.update(
            ok=True,
            status="DURABLE_CLOSURE_PROJECTION_READ_OFFLINE",
            reason=None,
            protected_receipt=protected,
            effective_resolution_state="RESOLVED",
            effective_reconciliation_required=False,
            generation=snapshot["generation"],
            wal_state=wal_v2.CLEAN,
            filesystem_accessed=True,
            interprocess_lock_acquired=True,
        )
        return result

    def recover_offline(self) -> dict[str, Any]:
        reason = self._config_reason(require_attestation=False)
        if reason is not None:
            return self._failed(reason)
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        recovered = wal_v2.recover_temp_wal(
            self._storage,
            lambda payload: self._apply_mutation
            if payload.get("mutation_kind") == "COMMIT_CLOSURE_PROJECTION"
            else None,
            lock=lock,
        )
        if not recovered.ok:
            return self._failed("DURABLE_CLOSURE_PROJECTION_RECOVERY_FAILED")
        result = self._failed("")
        result.update(
            ok=True,
            status="DURABLE_CLOSURE_PROJECTION_RECOVERED_OFFLINE",
            reason=None,
            generation=recovered.generation,
            wal_state=wal_v2.CLEAN,
            filesystem_accessed=True,
            interprocess_lock_acquired=True,
            write_executed=recovered.event_id is not None,
        )
        return result


__all__ = [
    "DURABLE_CLOSURE_PROJECTION_LEDGER_VERSION_V2",
    "DURABLE_CLOSURE_PROJECTION_RECEIPT_VERSION_V2",
    "DURABLE_CLOSURE_PROJECTION_RECORD_VERSION_V2",
    "DURABLE_CLOSURE_PROJECTION_SCOPE_V2",
    "DormantDurableClosureProjectionConfigV2",
    "DormantDurableClosureProjectionLedgerV2",
    "DormantReconciliationClosureAttestationConfigV2",
    "DormantReconciliationClosureAttestationContractV2",
    "OFFLINE_RECONCILIATION_CLOSURE_ATTESTATION_SCOPE_V2",
    "ProtectedReconciliationClosureAttestationV2",
    "ProtectedDurableClosureProjectionReceiptV2",
    "RECONCILIATION_CLOSURE_ATTESTATION_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_CLOSURE_ATTESTATION_CONTRACT_V2_VERSION",
    "durable_closure_projection_receipt_sha256_v2",
    "durable_closure_projection_record_sha256_v2",
    "durable_closure_projection_record_valid_v2",
    "durable_closure_projection_storage_binding_sha256_v2",
    "protected_durable_closure_projection_receipt_valid_v2",
    "protected_reconciliation_closure_attestation_valid_v2",
    "reconciliation_closure_attestation_sha256_v2",
]
