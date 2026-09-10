"""Dormant filesystem-backed reference contract for C3 durable authority.

Only caller-injected storage is used.  The reference persists a hash-bound
authority record through the generic WAL, requires an OS interprocess lock,
and supports deterministic crash recovery.  It is synthetic, default-off,
and is not a production authority or runtime integration.
"""

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
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-DURABLE-AUTHORITY-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_TEMP_STORAGE_ONLY"
)
DURABLE_AUTHORITY_LEDGER_VERSION_V2 = "C3_DURABLE_AUTHORITY_LEDGER_REFERENCE_V2_1_AUTHENTICATED_ROOT"
DURABLE_AUTHORITY_RECORD_VERSION_V2 = "C3_DURABLE_AUTHORITY_RECORD_REFERENCE_V2"
DURABLE_AUTHORITY_RECEIPT_VERSION_V2 = "C3_DURABLE_AUTHORITY_RECEIPT_REFERENCE_V2_1_AUTHENTICATED_ROOT"
AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2 = (
    "C3_AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_V2"
)
ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2 = "HMAC-SHA256-REFERENCE"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version", "root_identity_sha256", "storage_binding_sha256",
        "key_id_sha256", "key_epoch", "previous_attestation_sha256",
        "issued_at_epoch", "expires_at_epoch", "signature_algorithm",
        "signature_sha256", "attestation_sha256",
    }
)
_RECORD_KEYS = frozenset(
    {
        "record_version", "root_identity_sha256", "obligation_sha256",
        "obligation_id_sha256", "transaction_sha256", "subject_binding_sha256",
        "grant_sha256", "issued_at_epoch", "expires_at_epoch", "state",
        "issuance_count", "consumption_count", "consumed_at_epoch",
        "terminal_evidence_sha256", "synthetic_only", "production_authority",
        "pre_resolution_record_sha256", "admission_sha256",
        "preparation_sha256", "terminal_state", "resolved_at_epoch",
        "resolution_source_evidence_sha256", "resolution_adapter_plan_sha256",
        "resolution_request_binding_sha256", "resolution_request_sha256",
        "resolution_binding_sha256", "record_sha256",
    }
)
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "root_identity_sha256", "storage_binding_sha256",
        "root_authority_attestation_sha256",
        "record_sha256", "obligation_sha256", "transaction_sha256",
        "grant_sha256", "state", "issuance_count", "consumption_count",
        "generation", "restart_persistent_reference", "synthetic_only",
        "production_authority", "production_durable", "receipt_sha256",
    }
)


def root_authority_signature_payload_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {
            key: item
            for key, item in value.items()
            if key not in {"signature_sha256", "attestation_sha256"}
        }
    )


def authenticated_root_authority_attestation_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "attestation_sha256"}
    )


def authenticated_root_authority_attestation_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _ROOT_ATTESTATION_KEYS:
        return False
    try:
        return bool(
            value["attestation_version"]
            == AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2
            and all(
                _valid_sha(value[key])
                for key in (
                    "root_identity_sha256", "storage_binding_sha256",
                    "key_id_sha256", "signature_sha256", "attestation_sha256",
                )
            )
            and type(value["key_epoch"]) is int
            and value["key_epoch"] >= 1
            and (
                value["previous_attestation_sha256"] is None
                if value["key_epoch"] == 1
                else _valid_sha(value["previous_attestation_sha256"])
            )
            and type(value["issued_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and value["issued_at_epoch"] < value["expires_at_epoch"]
            and value["signature_algorithm"] == ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2
            and hmac.compare_digest(
                value["attestation_sha256"],
                authenticated_root_authority_attestation_sha256_v2(value),
            )
        )
    except Exception:
        return False


def authenticated_root_authority_attestation_verified_v2(
    value: Any,
    verifier: Any,
) -> bool:
    if not authenticated_root_authority_attestation_valid_v2(value):
        return False
    verify = getattr(verifier, "verify_root_authority_signature_v2", None)
    if not callable(verify):
        return False
    try:
        return bool(
            verify(
                key_id_sha256=value["key_id_sha256"],
                payload_sha256=root_authority_signature_payload_sha256_v2(value),
                signature_sha256=value["signature_sha256"],
            )
            is True
        )
    except Exception:
        return False


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return hash_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def durable_authority_storage_binding_sha256_v2(
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


def durable_authority_record_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "record_sha256")


def durable_authority_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "receipt_sha256")


def durable_resolution_binding_sha256_v2(
    *,
    obligation_sha256: str,
    pre_resolution_record_sha256: str,
    admission_sha256: str,
    preparation_sha256: str,
    source_evidence_sha256: str,
    adapter_plan_sha256: str,
    request_binding_sha256: str,
    request_sha256: str,
    terminal_evidence_sha256: str,
    terminal_state: str,
    resolved_at_epoch: int,
) -> str:
    return hash_v2.stable_sha256_v2(
        {
            "kind": "C3_DURABLE_RECONCILIATION_RESOLUTION_BINDING_V2",
            "obligation_sha256": obligation_sha256,
            "pre_resolution_record_sha256": pre_resolution_record_sha256,
            "admission_sha256": admission_sha256,
            "preparation_sha256": preparation_sha256,
            "source_evidence_sha256": source_evidence_sha256,
            "adapter_plan_sha256": adapter_plan_sha256,
            "request_binding_sha256": request_binding_sha256,
            "request_sha256": request_sha256,
            "terminal_evidence_sha256": terminal_evidence_sha256,
            "terminal_state": terminal_state,
            "resolved_at_epoch": resolved_at_epoch,
        }
    )


def durable_authority_record_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _RECORD_KEYS:
        return False
    try:
        return bool(
            all(
                _valid_sha(value[key])
                for key in (
                    "root_identity_sha256", "obligation_sha256",
                    "obligation_id_sha256", "transaction_sha256",
                    "subject_binding_sha256", "grant_sha256", "record_sha256",
                )
            )
            and value["state"] in {"ISSUED", "CONSUMED", "RESOLVED", "REVOKED"}
            and type(value["issued_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and value["issued_at_epoch"] < value["expires_at_epoch"]
            and value["issuance_count"] == 1
            and value["consumption_count"] in {0, 1}
            and (
                value["state"] == "ISSUED"
                and value["consumption_count"] == 0
                and value["consumed_at_epoch"] is None
                and value["terminal_evidence_sha256"] is None
                and all(
                    value[key] is None
                    for key in (
                        "pre_resolution_record_sha256", "admission_sha256",
                        "preparation_sha256", "terminal_state",
                        "resolved_at_epoch", "resolution_source_evidence_sha256",
                        "resolution_adapter_plan_sha256",
                        "resolution_request_binding_sha256",
                        "resolution_request_sha256", "resolution_binding_sha256",
                    )
                )
                or value["state"] == "CONSUMED"
                and value["consumption_count"] == 1
                and type(value["consumed_at_epoch"]) is int
                and value["issued_at_epoch"] <= value["consumed_at_epoch"]
                and _valid_sha(value["terminal_evidence_sha256"])
                and all(
                    value[key] is None
                    for key in (
                        "pre_resolution_record_sha256", "admission_sha256",
                        "preparation_sha256", "terminal_state",
                        "resolved_at_epoch", "resolution_source_evidence_sha256",
                        "resolution_adapter_plan_sha256",
                        "resolution_request_binding_sha256",
                        "resolution_request_sha256", "resolution_binding_sha256",
                    )
                )
                or value["state"] == "RESOLVED"
                and value["consumption_count"] == 1
                and type(value["consumed_at_epoch"]) is int
                and value["issued_at_epoch"] <= value["consumed_at_epoch"]
                and value["resolved_at_epoch"] == value["consumed_at_epoch"]
                and value["terminal_state"] in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
                and all(
                    _valid_sha(value[key])
                    for key in (
                        "terminal_evidence_sha256", "pre_resolution_record_sha256",
                        "admission_sha256", "preparation_sha256",
                        "resolution_source_evidence_sha256",
                        "resolution_adapter_plan_sha256",
                        "resolution_request_binding_sha256",
                        "resolution_request_sha256",
                        "resolution_binding_sha256",
                    )
                )
                or value["state"] == "REVOKED"
                and value["consumption_count"] == 0
                and all(
                    value[key] is None
                    for key in (
                        "pre_resolution_record_sha256", "admission_sha256",
                        "preparation_sha256", "terminal_state",
                        "resolved_at_epoch", "resolution_source_evidence_sha256",
                        "resolution_adapter_plan_sha256",
                        "resolution_request_binding_sha256",
                        "resolution_request_sha256", "resolution_binding_sha256",
                    )
                )
            )
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and hmac.compare_digest(
                value["record_sha256"], durable_authority_record_sha256_v2(value)
            )
        )
    except Exception:
        return False


@dataclass(frozen=True, repr=False)
class ProtectedDurableReconciliationAuthorityReceiptV2:
    record: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableReconciliationAuthorityReceiptV2(<protected>)"


def protected_durable_reconciliation_authority_receipt_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDurableReconciliationAuthorityReceiptV2:
        return False
    receipt = value.receipt
    record = value.record
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        return False
    try:
        return bool(
            durable_authority_record_valid_v2(record)
            and receipt["receipt_version"] == DURABLE_AUTHORITY_RECEIPT_VERSION_V2
            and receipt["root_identity_sha256"] == record["root_identity_sha256"]
            and _valid_sha(receipt["root_authority_attestation_sha256"])
            and _valid_sha(receipt["storage_binding_sha256"])
            and receipt["record_sha256"] == record["record_sha256"]
            and receipt["obligation_sha256"] == record["obligation_sha256"]
            and receipt["transaction_sha256"] == record["transaction_sha256"]
            and receipt["grant_sha256"] == record["grant_sha256"]
            and receipt["state"] == record["state"]
            and receipt["issuance_count"] == record["issuance_count"]
            and receipt["consumption_count"] == record["consumption_count"]
            and type(receipt["generation"]) is int
            and receipt["generation"] >= 1
            and receipt["restart_persistent_reference"] is True
            and receipt["synthetic_only"] is True
            and receipt["production_authority"] is False
            and receipt["production_durable"] is False
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and _valid_sha(receipt["receipt_sha256"])
            and hmac.compare_digest(
                receipt["receipt_sha256"], durable_authority_receipt_sha256_v2(receipt)
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantDurableReconciliationAuthorityConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_root_identity_sha256: str | None = field(default=None, repr=False)
    expected_storage_binding_sha256: str | None = field(default=None, repr=False)
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not 0 < self.lock_timeout_seconds <= 5:
            raise ValueError("lock_timeout_seconds must be between 0 and 5")


class _HeldLockContext:
    def __init__(self, handle: storage_v1.InterprocessFileLockHandleV1) -> None:
        self._handle = handle

    def __enter__(self) -> "_HeldLockContext":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._handle.release()


class DormantDurableReconciliationAuthorityLedgerV2:
    """WAL-backed synthetic reference ledger with restart recovery."""

    def __init__(
        self,
        config: DormantDurableReconciliationAuthorityConfigV2 | None = None,
        *,
        storage: wal_v2.RegistryV2WalStorage | None = None,
        lock_backend: storage_v1.CrossPlatformInterprocessFileLockBackendV1 | None = None,
        root_authority_attestation: Mapping[str, Any] | None = None,
        root_authority_verifier: Any = None,
    ) -> None:
        self._config = config or DormantDurableReconciliationAuthorityConfigV2()
        self._storage = storage
        self._lock_backend = lock_backend
        self._root_authority_attestation = (
            copy.deepcopy(dict(root_authority_attestation))
            if isinstance(root_authority_attestation, Mapping)
            else None
        )
        self._root_authority_verifier = root_authority_verifier
        self._bound_resolution_preparation: Any = None

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_RECONCILIATION_AUTHORITY_V2_BLOCKED",
            "reason": reason,
            "protected_receipt": None,
            "generation": None,
            "wal_state": None,
            "filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
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
            return "DURABLE_RECONCILIATION_AUTHORITY_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_SCOPE_ATTESTATION_V2:
            return "DURABLE_RECONCILIATION_AUTHORITY_SCOPE_INVALID"
        if not _valid_sha(self._config.expected_root_identity_sha256):
            return "EXPECTED_DURABLE_ROOT_IDENTITY_REQUIRED"
        if not _valid_sha(self._config.expected_storage_binding_sha256):
            return "EXPECTED_DURABLE_STORAGE_BINDING_REQUIRED"
        if type(self._storage) is not wal_v2.RegistryV2WalStorage:
            return "DURABLE_AUTHORITY_STORAGE_REQUIRED"
        if type(self._lock_backend) is not storage_v1.CrossPlatformInterprocessFileLockBackendV1:
            return "INTERPROCESS_LOCK_BACKEND_REQUIRED"
        if self._lock_backend.enabled is not True:
            return "INTERPROCESS_LOCK_BACKEND_DEFAULT_OFF"
        lock_root = self._lock_backend.storage_root.resolve(strict=False)
        storage_paths = (
            Path(self._storage.snapshot_path),
            Path(self._storage.journal_path),
            Path(self._storage.lock_path),
            Path(self._storage.backup_dir),
        )
        if any(path.resolve(strict=False).parent != lock_root for path in storage_paths):
            return "INTERPROCESS_LOCK_STORAGE_ROOT_MISMATCH"
        if not hmac.compare_digest(
            self._config.expected_storage_binding_sha256,
            durable_authority_storage_binding_sha256_v2(self._storage),
        ):
            return "DURABLE_AUTHORITY_STORAGE_BINDING_MISMATCH"
        if not authenticated_root_authority_attestation_verified_v2(
            self._root_authority_attestation,
            self._root_authority_verifier,
        ):
            return "AUTHENTICATED_ROOT_AUTHORITY_REQUIRED"
        if (
            self._root_authority_attestation["root_identity_sha256"]
            != self._config.expected_root_identity_sha256
            or self._root_authority_attestation["storage_binding_sha256"]
            != self._config.expected_storage_binding_sha256
        ):
            return "AUTHENTICATED_ROOT_AUTHORITY_BINDING_MISMATCH"
        return None

    def _root_active_at(self, epoch: int) -> bool:
        return bool(
            type(epoch) is int
            and self._root_authority_attestation["issued_at_epoch"]
            <= epoch
            < self._root_authority_attestation["expires_at_epoch"]
        )

    def _receipt_root_pinned(self, receipt: Mapping[str, Any]) -> bool:
        return bool(
            receipt["root_identity_sha256"]
            == self._config.expected_root_identity_sha256
            and receipt["storage_binding_sha256"]
            == self._config.expected_storage_binding_sha256
            and receipt["root_authority_attestation_sha256"]
            == self._root_authority_attestation["attestation_sha256"]
        )

    def _acquire(self) -> _HeldLockContext | None:
        handle = self._lock_backend.acquire(
            self._config.expected_storage_binding_sha256,
            self._config.lock_timeout_seconds,
        )
        return _HeldLockContext(handle) if handle is not None else None

    def _read_snapshot(self) -> dict[str, Any] | None:
        path = Path(self._storage.snapshot_path)
        if not path.exists():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if type(value) is not dict:
            raise ValueError("DURABLE_AUTHORITY_SNAPSHOT_MAPPING_REQUIRED")
        integrity = value.get("integrity")
        if not isinstance(integrity, Mapping) or integrity.get("snapshot_digest") != wal_v2.compute_snapshot_digest(value):
            raise ValueError("DURABLE_AUTHORITY_SNAPSHOT_INTEGRITY_INVALID")
        return value

    def _snapshot_valid(self, snapshot: Any) -> bool:
        try:
            records = snapshot["authorities"]
            return bool(
                type(snapshot) is dict
                and snapshot["ledger_version"] == DURABLE_AUTHORITY_LEDGER_VERSION_V2
                and snapshot["root_identity_sha256"] == self._config.expected_root_identity_sha256
                and snapshot["storage_binding_sha256"] == self._config.expected_storage_binding_sha256
                and snapshot["root_authority_attestation"]
                == self._root_authority_attestation
                and snapshot["root_authority_attestation_sha256"]
                == self._root_authority_attestation["attestation_sha256"]
                and authenticated_root_authority_attestation_verified_v2(
                    snapshot["root_authority_attestation"],
                    self._root_authority_verifier,
                )
                and type(snapshot["generation"]) is int
                and snapshot["generation"] >= 0
                and type(records) is dict
                and all(key == record.get("obligation_sha256") and durable_authority_record_valid_v2(record) for key, record in records.items())
                and snapshot["synthetic_only"] is True
                and snapshot["production_authority"] is False
                and snapshot["production_durable"] is False
            )
        except Exception:
            return False

    def open_offline(self) -> dict[str, Any]:
        reason = self._config_reason()
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
                        "ledger_version": DURABLE_AUTHORITY_LEDGER_VERSION_V2,
                        "root_identity_sha256": self._config.expected_root_identity_sha256,
                        "storage_binding_sha256": self._config.expected_storage_binding_sha256,
                        "root_authority_attestation": copy.deepcopy(
                            self._root_authority_attestation
                        ),
                        "root_authority_attestation_sha256": self._root_authority_attestation[
                            "attestation_sha256"
                        ],
                        "generation": 0,
                        "authorities": {},
                        "synthetic_only": True,
                        "production_authority": False,
                        "production_durable": False,
                    }
                    wal_v2.write_initial_snapshot(self._storage, snapshot)
                    write_executed = True
                else:
                    write_executed = False
                if not self._snapshot_valid(self._read_snapshot()):
                    return self._failed("DURABLE_AUTHORITY_SNAPSHOT_INVALID")
        except Exception:
            return self._failed("DURABLE_AUTHORITY_STORAGE_OPEN_FAILED")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RECONCILIATION_AUTHORITY_LEDGER_OPENED_OFFLINE",
                "reason": None,
                "generation": snapshot["generation"],
                "wal_state": wal_v2.CLEAN,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": write_executed,
            }
        )
        return result

    @staticmethod
    def _resolved_scan_blocked() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "DURABLE_RECONCILIATION_RESOLVED_SCAN_V2_BLOCKED",
            "reason": None,
            "root_identity_sha256": None,
            "storage_binding_sha256": None,
            "root_authority_attestation_sha256": None,
            "generation": None,
            "records": [],
            "record_count": 0,
            "complete_scan_verified": False,
            "wal_integrity_verified": False,
            "filesystem_accessed": False,
            "interprocess_lock_acquired": False,
            "write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
            "synthetic_only": True,
        }

    def _resolved_scan_from_snapshot(
        self, snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        blocked = self._resolved_scan_blocked()
        projected = []
        for record in snapshot["authorities"].values():
            if record["state"] != "RESOLVED":
                continue
            protected = self._protect(record, snapshot["generation"])
            item = {
                "record_version": "C3_DURABLE_RESOLVED_RECORD_PROJECTION_V2",
                "obligation_sha256": record["obligation_sha256"],
                "transaction_sha256": record["transaction_sha256"],
                "resolution_receipt_sha256": protected.receipt_sha256,
                "terminal_result_sha256": record["terminal_evidence_sha256"],
                "resolved_at_epoch": record["resolved_at_epoch"],
                "projection_committed": False,
                "state": "RESOLVED",
            }
            item["record_sha256"] = hash_v2.stable_sha256_v2(item)
            projected.append(item)
        projected.sort(key=lambda item: item["record_sha256"])
        return {
            **blocked,
            "ok": True,
            "status": "DURABLE_RECONCILIATION_RESOLVED_SCAN_V2_COMPLETE",
            "reason": None,
            "root_identity_sha256": snapshot["root_identity_sha256"],
            "storage_binding_sha256": snapshot["storage_binding_sha256"],
            "root_authority_attestation_sha256": snapshot[
                "root_authority_attestation_sha256"
            ],
            "generation": snapshot["generation"],
            "records": projected,
            "record_count": len(projected),
            "complete_scan_verified": True,
            "wal_integrity_verified": True,
            "filesystem_accessed": True,
            "interprocess_lock_acquired": True,
        }

    def list_resolved_records_offline(self) -> dict[str, Any]:
        """Return a complete, sanitized projection of synthetic RESOLVED records."""

        blocked = self._resolved_scan_blocked()
        reason = self._config_reason()
        if reason is not None:
            blocked["reason"] = reason
            return blocked
        try:
            lock = self._acquire()
        except Exception:
            blocked["reason"] = "RESOLVED_SCAN_LOCK_ACQUISITION_FAILED"
            return blocked
        if lock is None:
            blocked["reason"] = "INTERPROCESS_LOCK_TIMEOUT"
            return blocked
        try:
            with lock:
                snapshot, failure = self._read_valid_locked()
        except Exception:
            blocked.update(
                {
                    "reason": "RESOLVED_SCAN_STORAGE_READ_FAILED",
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return blocked
        if failure is not None or snapshot is None:
            blocked.update(
                {
                    "reason": failure or "DURABLE_AUTHORITY_SNAPSHOT_INVALID",
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return blocked
        return self._resolved_scan_from_snapshot(snapshot)

    @staticmethod
    def _apply_mutation(snapshot: Mapping[str, Any], payload: Mapping[str, Any]) -> Mapping[str, Any]:
        candidate = copy.deepcopy(dict(snapshot))
        if payload["mutation_kind"] == "ROTATE_ROOT_AUTHORITY":
            candidate["root_authority_attestation"] = copy.deepcopy(
                dict(payload["root_authority_attestation"])
            )
            candidate["root_authority_attestation_sha256"] = payload[
                "root_authority_attestation_sha256"
            ]
            return candidate
        records = copy.deepcopy(dict(candidate.get("authorities") or {}))
        key = payload["obligation_sha256"]
        if payload["mutation_kind"] == "ISSUE":
            records[key] = copy.deepcopy(dict(payload["record"]))
        elif payload["mutation_kind"] == "CONSUME":
            record = copy.deepcopy(dict(records[key]))
            record.update(
                {
                    "state": "CONSUMED",
                    "consumption_count": 1,
                    "consumed_at_epoch": payload["consumed_at_epoch"],
                    "terminal_evidence_sha256": payload["terminal_evidence_sha256"],
                }
            )
            record["record_sha256"] = durable_authority_record_sha256_v2(record)
            records[key] = record
        elif payload["mutation_kind"] == "RESOLVE":
            record = copy.deepcopy(dict(records[key]))
            record.update(
                {
                    "state": "RESOLVED",
                    "consumption_count": 1,
                    "consumed_at_epoch": payload["resolved_at_epoch"],
                    "terminal_evidence_sha256": payload["terminal_evidence_sha256"],
                    "pre_resolution_record_sha256": payload["pre_resolution_record_sha256"],
                    "admission_sha256": payload["admission_sha256"],
                    "preparation_sha256": payload["preparation_sha256"],
                    "resolution_source_evidence_sha256": payload["resolution_source_evidence_sha256"],
                    "resolution_adapter_plan_sha256": payload["resolution_adapter_plan_sha256"],
                    "resolution_request_binding_sha256": payload["resolution_request_binding_sha256"],
                    "resolution_request_sha256": payload["resolution_request_sha256"],
                    "terminal_state": payload["terminal_state"],
                    "resolved_at_epoch": payload["resolved_at_epoch"],
                    "resolution_binding_sha256": payload["resolution_binding_sha256"],
                }
            )
            record["record_sha256"] = durable_authority_record_sha256_v2(record)
            records[key] = record
        else:
            return candidate
        candidate["authorities"] = records
        return candidate

    def _read_valid_locked(self) -> tuple[dict[str, Any] | None, str | None]:
        try:
            snapshot = self._read_snapshot()
        except Exception:
            return None, "DURABLE_AUTHORITY_SNAPSHOT_READ_FAILED"
        if not self._snapshot_valid(snapshot):
            return None, "DURABLE_AUTHORITY_SNAPSHOT_INVALID"
        inspection = wal_v2.inspect_wal_recovery_state(self._storage)
        if inspection.status != wal_v2.CLEAN:
            return None, "DURABLE_AUTHORITY_WAL_RECOVERY_REQUIRED"
        return snapshot, None

    def _protect(self, record: Mapping[str, Any], generation: int) -> ProtectedDurableReconciliationAuthorityReceiptV2:
        receipt = {
            "receipt_version": DURABLE_AUTHORITY_RECEIPT_VERSION_V2,
            "root_identity_sha256": record["root_identity_sha256"],
            "storage_binding_sha256": self._config.expected_storage_binding_sha256,
            "root_authority_attestation_sha256": self._root_authority_attestation[
                "attestation_sha256"
            ],
            "record_sha256": record["record_sha256"],
            "obligation_sha256": record["obligation_sha256"],
            "transaction_sha256": record["transaction_sha256"],
            "grant_sha256": record["grant_sha256"],
            "state": record["state"],
            "issuance_count": record["issuance_count"],
            "consumption_count": record["consumption_count"],
            "generation": generation,
            "restart_persistent_reference": True,
            "synthetic_only": True,
            "production_authority": False,
            "production_durable": False,
        }
        receipt["receipt_sha256"] = durable_authority_receipt_sha256_v2(receipt)
        return ProtectedDurableReconciliationAuthorityReceiptV2(
            record=copy.deepcopy(dict(record)),
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

    def rotate_root_authority_offline(
        self,
        root_authority_attestation: Any,
        *,
        rotated_at_epoch: int,
        fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if not authenticated_root_authority_attestation_verified_v2(
            root_authority_attestation,
            self._root_authority_verifier,
        ):
            return self._failed("ROTATED_ROOT_AUTHORITY_AUTHENTICATION_INVALID")
        current_attestation = self._root_authority_attestation
        if (
            root_authority_attestation["root_identity_sha256"]
            != self._config.expected_root_identity_sha256
            or root_authority_attestation["storage_binding_sha256"]
            != self._config.expected_storage_binding_sha256
            or root_authority_attestation["key_epoch"]
            != current_attestation["key_epoch"] + 1
            or root_authority_attestation["previous_attestation_sha256"]
            != current_attestation["attestation_sha256"]
            or type(rotated_at_epoch) is not int
            or not root_authority_attestation["issued_at_epoch"]
            <= rotated_at_epoch
            < root_authority_attestation["expires_at_epoch"]
        ):
            return self._failed("ROTATED_ROOT_AUTHORITY_CHAIN_INVALID")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        if (
            snapshot["root_authority_attestation_sha256"]
            != current_attestation["attestation_sha256"]
        ):
            return self._failed("ROOT_AUTHORITY_ROTATION_COMPARE_AND_SWAP_MISMATCH")
        if any(
            record.get("state") == "ISSUED"
            for record in snapshot["authorities"].values()
        ):
            return self._failed("ROOT_AUTHORITY_ROTATION_REQUIRES_ZERO_ISSUED_AUTHORITIES")
        new_attestation = copy.deepcopy(dict(root_authority_attestation))
        payload = {
            "mutation_kind": "ROTATE_ROOT_AUTHORITY",
            "obligation_sha256": self._config.expected_root_identity_sha256,
            "root_authority_attestation": new_attestation,
            "root_authority_attestation_sha256": new_attestation[
                "attestation_sha256"
            ],
            "rotated_at_epoch": rotated_at_epoch,
        }
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        try:
            applied = wal_v2.apply_temp_wal_mutation(
                self._storage,
                snapshot,
                payload,
                "DURABLE_AUTHORITY_ROTATE_ROOT",
                self._config.expected_root_identity_sha256,
                None,
                new_attestation["attestation_sha256"],
                snapshot["generation"],
                self._apply_mutation,
                fault_hook=fault_hook,
                lock=lock,
                schema_version=DURABLE_AUTHORITY_LEDGER_VERSION_V2,
            )
        except Exception:
            failed = self._failed("ROOT_AUTHORITY_ROTATION_INTERRUPTED")
            failed.update(
                {
                    "wal_state": wal_v2.WAL_RECOVERY_REQUIRED,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                    "write_executed": True,
                }
            )
            return failed
        if not applied.ok:
            return self._failed("ROOT_AUTHORITY_ROTATION_WAL_REJECTED")
        self._root_authority_attestation = new_attestation
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "ROOT_AUTHORITY_ROTATED_OFFLINE",
                "reason": None,
                "generation": applied.generation,
                "wal_state": wal_v2.CLEAN,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": True,
                "root_authority_attestation_sha256": new_attestation[
                    "attestation_sha256"
                ],
            }
        )
        return result

    def issue_once_offline(
        self,
        *,
        obligation_sha256: str,
        obligation_id_sha256: str,
        transaction_sha256: str,
        subject_binding_sha256: str,
        grant_sha256: str,
        issued_at_epoch: int,
        expires_at_epoch: int,
        fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if not all(_valid_sha(item) for item in (obligation_sha256, obligation_id_sha256, transaction_sha256, subject_binding_sha256, grant_sha256)):
            return self._failed("DURABLE_AUTHORITY_ISSUE_BINDING_INVALID")
        if type(issued_at_epoch) is not int or type(expires_at_epoch) is not int or issued_at_epoch >= expires_at_epoch:
            return self._failed("DURABLE_AUTHORITY_ISSUE_TIME_INVALID")
        if not self._root_active_at(issued_at_epoch):
            return self._failed("AUTHENTICATED_ROOT_AUTHORITY_NOT_ACTIVE")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        existing = snapshot["authorities"].get(obligation_sha256)
        immutable = {
            "root_identity_sha256": self._config.expected_root_identity_sha256,
            "obligation_sha256": obligation_sha256,
            "obligation_id_sha256": obligation_id_sha256,
            "transaction_sha256": transaction_sha256,
            "subject_binding_sha256": subject_binding_sha256,
            "grant_sha256": grant_sha256,
            "issued_at_epoch": issued_at_epoch,
            "expires_at_epoch": expires_at_epoch,
        }
        if existing is not None:
            if any(existing.get(key) != value for key, value in immutable.items()):
                return self._failed("DURABLE_AUTHORITY_REISSUE_CONFLICT")
            if existing["state"] != "ISSUED":
                return self._failed("DURABLE_AUTHORITY_ALREADY_TERMINAL")
            protected = self._protect(existing, snapshot["generation"])
            result = self._failed("")
            result.update({"ok": True, "status": "DURABLE_AUTHORITY_ALREADY_ISSUED_IDEMPOTENT", "reason": None, "protected_receipt": protected, "generation": snapshot["generation"], "wal_state": wal_v2.CLEAN, "filesystem_accessed": True, "interprocess_lock_acquired": True})
            return result
        record = {
            "record_version": DURABLE_AUTHORITY_RECORD_VERSION_V2,
            **immutable,
            "state": "ISSUED",
            "issuance_count": 1,
            "consumption_count": 0,
            "consumed_at_epoch": None,
            "terminal_evidence_sha256": None,
            "pre_resolution_record_sha256": None,
            "admission_sha256": None,
            "preparation_sha256": None,
            "resolution_source_evidence_sha256": None,
            "resolution_adapter_plan_sha256": None,
            "resolution_request_binding_sha256": None,
            "resolution_request_sha256": None,
            "terminal_state": None,
            "resolved_at_epoch": None,
            "resolution_binding_sha256": None,
            "synthetic_only": True,
            "production_authority": False,
        }
        record["record_sha256"] = durable_authority_record_sha256_v2(record)
        payload = {"mutation_kind": "ISSUE", "obligation_sha256": obligation_sha256, "record": record}
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        try:
            applied = wal_v2.apply_temp_wal_mutation(
                self._storage, snapshot, payload, "DURABLE_AUTHORITY_ISSUE",
                obligation_sha256, None, grant_sha256, snapshot["generation"],
                self._apply_mutation, fault_hook=fault_hook, lock=lock,
                schema_version=DURABLE_AUTHORITY_LEDGER_VERSION_V2,
            )
        except Exception:
            failed = self._failed("DURABLE_AUTHORITY_ISSUE_INTERRUPTED")
            failed.update(
                {
                    "wal_state": wal_v2.WAL_RECOVERY_REQUIRED,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                    "write_executed": True,
                }
            )
            return failed
        if not applied.ok:
            return self._failed("DURABLE_AUTHORITY_ISSUE_WAL_REJECTED")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            current, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        protected = self._protect(current["authorities"][obligation_sha256], current["generation"])
        result = self._failed("")
        result.update({"ok": True, "status": "DURABLE_AUTHORITY_ISSUED_OFFLINE", "reason": None, "protected_receipt": protected, "generation": current["generation"], "wal_state": wal_v2.CLEAN, "filesystem_accessed": True, "interprocess_lock_acquired": True, "write_executed": True})
        return result

    def consume_once_offline(
        self,
        protected_receipt: Any,
        *,
        terminal_evidence_sha256: str,
        consumed_at_epoch: int,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if not protected_durable_reconciliation_authority_receipt_valid_v2(protected_receipt) or protected_receipt.receipt["state"] != "ISSUED":
            return self._failed("ISSUED_DURABLE_AUTHORITY_RECEIPT_REQUIRED")
        if not self._receipt_root_pinned(protected_receipt.receipt):
            return self._failed("DURABLE_AUTHORITY_RECEIPT_NOT_PINNED")
        if not _valid_sha(terminal_evidence_sha256) or type(consumed_at_epoch) is not int:
            return self._failed("DURABLE_AUTHORITY_CONSUMPTION_INPUT_INVALID")
        if not self._root_active_at(consumed_at_epoch):
            return self._failed("AUTHENTICATED_ROOT_AUTHORITY_NOT_ACTIVE")
        obligation_sha256 = protected_receipt.receipt["obligation_sha256"]
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        record = snapshot["authorities"].get(obligation_sha256)
        if record is None:
            return self._failed("DURABLE_AUTHORITY_RECORD_NOT_CURRENT")
        if record["state"] != "ISSUED" or record["consumption_count"] != 0:
            return self._failed("DURABLE_AUTHORITY_ALREADY_CONSUMED")
        if record["record_sha256"] != protected_receipt.receipt["record_sha256"]:
            return self._failed("DURABLE_AUTHORITY_RECORD_NOT_CURRENT")
        if not record["issued_at_epoch"] <= consumed_at_epoch < record["expires_at_epoch"]:
            return self._failed("DURABLE_AUTHORITY_CONSUMPTION_TIME_INVALID")
        payload = {"mutation_kind": "CONSUME", "obligation_sha256": obligation_sha256, "record_sha256": record["record_sha256"], "terminal_evidence_sha256": terminal_evidence_sha256, "consumed_at_epoch": consumed_at_epoch}
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        applied = wal_v2.apply_temp_wal_mutation(
            self._storage, snapshot, payload, "DURABLE_AUTHORITY_CONSUME",
            obligation_sha256, None, record["record_sha256"], snapshot["generation"],
            self._apply_mutation, lock=lock,
            schema_version=DURABLE_AUTHORITY_LEDGER_VERSION_V2,
        )
        if not applied.ok:
            return self._failed("DURABLE_AUTHORITY_CONSUMPTION_WAL_REJECTED")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            current, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        protected = self._protect(current["authorities"][obligation_sha256], current["generation"])
        result = self._failed("")
        result.update({"ok": True, "status": "DURABLE_AUTHORITY_CONSUMED_OFFLINE", "reason": None, "protected_receipt": protected, "generation": current["generation"], "wal_state": wal_v2.CLEAN, "filesystem_accessed": True, "interprocess_lock_acquired": True, "write_executed": True})
        return result

    def verify_current_issued_offline(
        self,
        protected_receipt: Any,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if (
            not protected_durable_reconciliation_authority_receipt_valid_v2(
                protected_receipt
            )
            or protected_receipt.receipt["state"] != "ISSUED"
        ):
            return self._failed("ISSUED_DURABLE_AUTHORITY_RECEIPT_REQUIRED")
        if type(now_epoch) is not int:
            return self._failed("DURABLE_AUTHORITY_VERIFICATION_TIME_INVALID")
        receipt = protected_receipt.receipt
        if not self._receipt_root_pinned(receipt):
            return self._failed("DURABLE_AUTHORITY_RECEIPT_NOT_PINNED")
        if not self._root_active_at(now_epoch):
            return self._failed("AUTHENTICATED_ROOT_AUTHORITY_NOT_ACTIVE")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        record = snapshot["authorities"].get(receipt["obligation_sha256"])
        if (
            record is None
            or record["record_sha256"] != receipt["record_sha256"]
            or record["state"] != "ISSUED"
            or record["consumption_count"] != 0
        ):
            failed = self._failed("DURABLE_AUTHORITY_NOT_CURRENTLY_ISSUED")
            failed.update(
                {
                    "generation": snapshot["generation"],
                    "wal_state": wal_v2.CLEAN,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        if not record["issued_at_epoch"] <= now_epoch < record["expires_at_epoch"]:
            failed = self._failed("DURABLE_AUTHORITY_NOT_CURRENTLY_VALID")
            failed.update(
                {
                    "generation": snapshot["generation"],
                    "wal_state": wal_v2.CLEAN,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        current = self._protect(record, snapshot["generation"])
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_AUTHORITY_CURRENTLY_ISSUED_VERIFIED_OFFLINE",
                "reason": None,
                "protected_receipt": current,
                "generation": snapshot["generation"],
                "wal_state": wal_v2.CLEAN,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
            }
        )
        return result

    def bind_resolution_preparation_offline(
        self,
        protected_preparation: Any,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        try:
            import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2
        except Exception:
            return self._failed("DURABLE_RESOLUTION_PREPARATION_CONTRACT_UNAVAILABLE")
        if not preparation_v2.protected_durable_resolution_preparation_valid_v2(
            protected_preparation
        ):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_INVALID")
        durable_receipt = (
            protected_preparation.protected_admission.durable_authority_receipt
        )
        if not self._receipt_root_pinned(durable_receipt.receipt):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_STORAGE_NOT_PINNED")
        if (
            self._bound_resolution_preparation is not None
            and protected_preparation is not self._bound_resolution_preparation
        ):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_ALREADY_BOUND")
        self._bound_resolution_preparation = protected_preparation
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_PREPARATION_BOUND_OFFLINE",
                "reason": None,
            }
        )
        return result

    def resolve_once_offline(
        self,
        protected_preparation: Any,
        *,
        fault_hook: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if (
            self._bound_resolution_preparation is None
            or protected_preparation is not self._bound_resolution_preparation
        ):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_INSTANCE_NOT_BOUND")
        try:
            import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2 as preparation_v2
        except Exception:
            return self._failed("DURABLE_RESOLUTION_PREPARATION_CONTRACT_UNAVAILABLE")
        if not preparation_v2.protected_durable_resolution_preparation_valid_v2(
            protected_preparation
        ):
            return self._failed("DURABLE_RESOLUTION_PREPARATION_INVALID")
        prepared = protected_preparation.preparation
        protected_receipt = (
            protected_preparation.protected_admission.durable_authority_receipt
        )
        admission_sha256 = prepared["admission_sha256"]
        preparation_sha256 = protected_preparation.preparation_sha256
        source_evidence_sha256 = prepared["source_evidence_sha256"]
        adapter_plan_sha256 = prepared["adapter_plan_sha256"]
        request_binding_sha256 = prepared["request_binding_sha256"]
        request_sha256 = prepared["request_sha256"]
        terminal_evidence_sha256 = prepared["terminal_evidence_sha256"]
        terminal_state = prepared["terminal_state"]
        resolved_at_epoch = prepared["prepared_at_epoch"]
        if not self._root_active_at(resolved_at_epoch):
            return self._failed("AUTHENTICATED_ROOT_AUTHORITY_NOT_ACTIVE")
        if (
            not protected_durable_reconciliation_authority_receipt_valid_v2(
                protected_receipt
            )
            or protected_receipt.receipt["state"] != "ISSUED"
        ):
            return self._failed("ISSUED_DURABLE_AUTHORITY_RECEIPT_REQUIRED")
        if not self._receipt_root_pinned(protected_receipt.receipt):
            return self._failed("DURABLE_AUTHORITY_RECEIPT_NOT_PINNED")
        receipt = protected_receipt.receipt
        obligation_sha256 = receipt["obligation_sha256"]
        pre_resolution_record_sha256 = receipt["record_sha256"]
        resolution_binding_sha256 = durable_resolution_binding_sha256_v2(
            obligation_sha256=obligation_sha256,
            pre_resolution_record_sha256=pre_resolution_record_sha256,
            admission_sha256=admission_sha256,
            preparation_sha256=preparation_sha256,
            source_evidence_sha256=source_evidence_sha256,
            adapter_plan_sha256=adapter_plan_sha256,
            request_binding_sha256=request_binding_sha256,
            request_sha256=request_sha256,
            terminal_evidence_sha256=terminal_evidence_sha256,
            terminal_state=terminal_state,
            resolved_at_epoch=resolved_at_epoch,
        )
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        record = snapshot["authorities"].get(obligation_sha256)
        expected_resolution = {
            "pre_resolution_record_sha256": pre_resolution_record_sha256,
            "admission_sha256": admission_sha256,
            "preparation_sha256": preparation_sha256,
            "resolution_source_evidence_sha256": source_evidence_sha256,
            "resolution_adapter_plan_sha256": adapter_plan_sha256,
            "resolution_request_binding_sha256": request_binding_sha256,
            "resolution_request_sha256": request_sha256,
            "terminal_evidence_sha256": terminal_evidence_sha256,
            "terminal_state": terminal_state,
            "resolved_at_epoch": resolved_at_epoch,
            "resolution_binding_sha256": resolution_binding_sha256,
        }
        if record is not None and record["state"] == "RESOLVED":
            if any(record.get(key) != value for key, value in expected_resolution.items()):
                return self._failed("DURABLE_RESOLUTION_REPLAY_CONFLICT")
            protected = self._protect(record, snapshot["generation"])
            result = self._failed("")
            result.update(
                {
                    "ok": True,
                    "status": "DURABLE_RESOLUTION_ALREADY_COMMITTED_IDEMPOTENT",
                    "reason": None,
                    "protected_receipt": protected,
                    "generation": snapshot["generation"],
                    "wal_state": wal_v2.CLEAN,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                    "write_executed": False,
                }
            )
            return result
        if record is None or record["state"] != "ISSUED":
            return self._failed("DURABLE_AUTHORITY_ALREADY_TERMINAL")
        if record["record_sha256"] != pre_resolution_record_sha256:
            return self._failed("DURABLE_AUTHORITY_RECORD_NOT_CURRENT")
        if not record["issued_at_epoch"] <= resolved_at_epoch < record["expires_at_epoch"]:
            return self._failed("DURABLE_RESOLUTION_TIME_INVALID")
        payload = {
            "mutation_kind": "RESOLVE",
            "obligation_sha256": obligation_sha256,
            **expected_resolution,
        }
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        try:
            applied = wal_v2.apply_temp_wal_mutation(
                self._storage,
                snapshot,
                payload,
                "DURABLE_AUTHORITY_RESOLVE",
                obligation_sha256,
                None,
                resolution_binding_sha256,
                snapshot["generation"],
                self._apply_mutation,
                fault_hook=fault_hook,
                lock=lock,
                schema_version=DURABLE_AUTHORITY_LEDGER_VERSION_V2,
            )
        except Exception:
            failed = self._failed("DURABLE_RESOLUTION_INTERRUPTED")
            failed.update(
                {
                    "wal_state": wal_v2.WAL_RECOVERY_REQUIRED,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                    "write_executed": True,
                }
            )
            return failed
        if not applied.ok:
            failed = self._failed("DURABLE_RESOLUTION_WAL_REJECTED")
            failed.update(
                {
                    "wal_state": applied.state,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            current, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        protected = self._protect(
            current["authorities"][obligation_sha256], current["generation"]
        )
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_COMMITTED_OFFLINE",
                "reason": None,
                "protected_receipt": protected,
                "generation": current["generation"],
                "wal_state": wal_v2.CLEAN,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": True,
            }
        )
        return result

    def read_resolved_offline(
        self,
        *,
        obligation_sha256: str,
    ) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        if not _valid_sha(obligation_sha256):
            return self._failed("DURABLE_RESOLUTION_LOOKUP_INVALID")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        record = snapshot["authorities"].get(obligation_sha256)
        if record is None or record["state"] != "RESOLVED":
            failed = self._failed("DURABLE_RESOLUTION_NOT_FOUND")
            failed.update(
                {
                    "generation": snapshot["generation"],
                    "wal_state": wal_v2.CLEAN,
                    "filesystem_accessed": True,
                    "interprocess_lock_acquired": True,
                }
            )
            return failed
        protected = self._protect(record, snapshot["generation"])
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "DURABLE_RESOLUTION_READ_OFFLINE",
                "reason": None,
                "protected_receipt": protected,
                "generation": snapshot["generation"],
                "wal_state": wal_v2.CLEAN,
                "filesystem_accessed": True,
                "interprocess_lock_acquired": True,
                "write_executed": False,
            }
        )
        return result

    def recover_offline(self) -> dict[str, Any]:
        reason = self._config_reason()
        if reason is not None:
            return self._failed(reason)
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        result = wal_v2.recover_temp_wal(
            self._storage,
            lambda payload: self._apply_mutation if payload.get("mutation_kind") in {"ISSUE", "CONSUME", "RESOLVE", "ROTATE_ROOT_AUTHORITY"} else None,
            lock=lock,
        )
        if not result.ok:
            return self._failed("DURABLE_AUTHORITY_WAL_RECOVERY_FAILED")
        lock = self._acquire()
        if lock is None:
            return self._failed("INTERPROCESS_LOCK_TIMEOUT")
        with lock:
            snapshot, failure = self._read_valid_locked()
        if failure is not None:
            return self._failed(failure)
        response = self._failed("")
        response.update({"ok": True, "status": "DURABLE_AUTHORITY_WAL_RECOVERED_OFFLINE", "reason": None, "generation": snapshot["generation"], "wal_state": wal_v2.CLEAN, "filesystem_accessed": True, "interprocess_lock_acquired": True, "write_executed": result.event_id is not None})
        return response


__all__ = [
    "AUTHENTICATED_ROOT_AUTHORITY_ATTESTATION_VERSION_V2",
    "DURABLE_AUTHORITY_LEDGER_VERSION_V2",
    "DURABLE_AUTHORITY_RECEIPT_VERSION_V2",
    "DURABLE_AUTHORITY_RECORD_VERSION_V2",
    "DormantDurableReconciliationAuthorityConfigV2",
    "DormantDurableReconciliationAuthorityLedgerV2",
    "OFFLINE_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_SCOPE_ATTESTATION_V2",
    "ROOT_AUTHORITY_SIGNATURE_ALGORITHM_V2",
    "ProtectedDurableReconciliationAuthorityReceiptV2",
    "authenticated_root_authority_attestation_sha256_v2",
    "authenticated_root_authority_attestation_valid_v2",
    "authenticated_root_authority_attestation_verified_v2",
    "durable_authority_receipt_sha256_v2",
    "durable_authority_record_sha256_v2",
    "durable_resolution_binding_sha256_v2",
    "durable_authority_record_valid_v2",
    "durable_authority_storage_binding_sha256_v2",
    "protected_durable_reconciliation_authority_receipt_valid_v2",
    "root_authority_signature_payload_sha256_v2",
]
