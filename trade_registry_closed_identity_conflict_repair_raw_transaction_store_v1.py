"""Synthetic-only raw Registry transaction store with durable rollback.

The store is constrained to a fixed synthetic filename below a caller-supplied
directory.  It is disabled by default and requires an explicit test-scope
attestation before it can create any file.  It never discovers or accepts the
Central's real Registry path.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-TRANSACTION-STORE-V1"
)

SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1 = (
    "SYNTHETIC_TEMPORARY_TEST_STORAGE_ONLY_V1"
)
_TARGET_NAME = "synthetic_trade_registry.json"
_WAL_NAME = "synthetic_trade_registry.repair.wal.jsonl"
_BACKUP_DIRECTORY_NAME = "synthetic_trade_registry_backups"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WAL_STATES = frozenset({"PREPARED", "COMMITTED", "ABORTED", "ROLLED_BACK"})


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


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _payload_bytes(value: Mapping[str, Any]) -> bytes:
    return _canonical_json(dict(value)).encode("utf-8")


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _validate_root(storage_root: str | os.PathLike[str]) -> Path:
    root = Path(storage_root).resolve(strict=False)
    if root == Path(root.anchor):
        raise ValueError("storage_root cannot be a filesystem root")
    return root


class RawTransactionStoreBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExactRawRegistrySnapshotV1:
    raw_document_sha256: str
    generation_token: str
    size_bytes: int
    payload: Mapping[str, Any] = field(repr=False)
    raw_bytes: bytes = field(repr=False)


def raw_transaction_request_sha256_v1(request: Mapping[str, Any]) -> str:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in request.items()
            if key != "transaction_sha256"
        }
    )


def build_raw_transaction_request_v1(
    source: ExactRawRegistrySnapshotV1,
    candidate_registry: Mapping[str, Any],
    *,
    idempotency_key: str,
    maintenance_epoch: str,
) -> dict[str, Any]:
    idempotency_sha = _valid_sha256(idempotency_key)
    epoch = _valid_sha256(maintenance_epoch)
    if not idempotency_sha:
        raise ValueError("idempotency_key must be a lowercase SHA-256")
    if not epoch:
        raise ValueError("maintenance_epoch must be a lowercase SHA-256")
    candidate = json.loads(_canonical_json(dict(candidate_registry)))
    candidate_bytes = _payload_bytes(candidate)
    request = {
        "request_version": "SYNTHETIC_RAW_REGISTRY_TRANSACTION_REQUEST_V1",
        "scope_attestation": SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1,
        "idempotency_key": idempotency_sha,
        "maintenance_epoch": epoch,
        "expected_raw_document_sha256": source.raw_document_sha256,
        "expected_generation_token": source.generation_token,
        "candidate_registry": candidate,
        "candidate_raw_document_sha256": _bytes_sha256(candidate_bytes),
    }
    request["transaction_sha256"] = raw_transaction_request_sha256_v1(request)
    return request


class IsolatedRawRegistryTransactionStoreV1:
    """Apply one synthetic raw transaction under an attested maintenance lock."""

    def __init__(
        self,
        storage_root: str | os.PathLike[str],
        *,
        enabled: bool = False,
        scope_attestation: str | None = None,
        directory_fsync: Callable[[Path], None] | None = None,
        replacer: Callable[[str, str], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        replace_timeout_seconds: float = 0.5,
        replace_poll_interval_seconds: float = 0.01,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        if replace_timeout_seconds <= 0 or replace_poll_interval_seconds <= 0:
            raise ValueError("replace timeout and poll interval must be positive")
        self._root = _validate_root(storage_root)
        self._enabled = bool(enabled)
        self._scope_attestation = str(scope_attestation or "")
        if self._enabled and self._scope_attestation != SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1:
            raise ValueError("synthetic temporary storage attestation required")
        if self._enabled and directory_fsync is None:
            raise ValueError("enabled store requires injected directory_fsync")
        self._lock_namespace = coordinator_module.canonical_runtime_lock_namespace_v1()
        self._directory_fsync = directory_fsync
        self._replacer = replacer or os.replace
        self._monotonic = monotonic or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._replace_timeout = float(replace_timeout_seconds)
        self._replace_poll = float(replace_poll_interval_seconds)
        self._fault_injector = fault_injector or (lambda step: None)
        self._target = self._root / _TARGET_NAME
        self._wal = self._root / _WAL_NAME
        self._backups = self._root / _BACKUP_DIRECTORY_NAME
        if self._enabled:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def storage_root(self) -> Path:
        return self._root

    @property
    def target_path(self) -> Path:
        return self._target

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise RawTransactionStoreBlocked("RAW_TRANSACTION_STORE_DEFAULT_OFF")

    def _sync_directory(self, directory: Path) -> None:
        try:
            self._directory_fsync(directory)
        except RawTransactionStoreBlocked:
            raise
        except Exception as exc:
            raise RawTransactionStoreBlocked("DIRECTORY_FSYNC_FAILED") from exc

    def initialize_synthetic_registry(self, payload: Mapping[str, Any]) -> None:
        self._require_enabled()
        if self._target.exists():
            raise RawTransactionStoreBlocked("SYNTHETIC_REGISTRY_ALREADY_EXISTS")
        data = _payload_bytes(payload)
        try:
            with self._target.open("xb") as file_obj:
                file_obj.write(data)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            self._sync_directory(self._root)
        except RawTransactionStoreBlocked:
            raise
        except Exception as exc:
            raise RawTransactionStoreBlocked("SYNTHETIC_REGISTRY_INITIALIZE_FAILED") from exc

    def load_exact_raw_registry(self) -> ExactRawRegistrySnapshotV1:
        self._require_enabled()
        try:
            with self._target.open("rb") as file_obj:
                raw = file_obj.read()
                stat = os.fstat(file_obj.fileno())
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RawTransactionStoreBlocked("RAW_REGISTRY_READ_FAILED") from exc
        if not isinstance(payload, Mapping):
            raise RawTransactionStoreBlocked("RAW_REGISTRY_NOT_OBJECT")
        raw_sha = _bytes_sha256(raw)
        generation = _stable_sha256(
            {
                "raw_document_sha256": raw_sha,
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
        )
        return ExactRawRegistrySnapshotV1(
            raw_document_sha256=raw_sha,
            generation_token=generation,
            size_bytes=len(raw),
            payload=json.loads(_canonical_json(payload)),
            raw_bytes=raw,
        )

    def _read_wal(self) -> list[dict[str, Any]]:
        if not self._wal.exists():
            return []
        try:
            lines = self._wal.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines if line.strip()]
        except Exception as exc:
            raise RawTransactionStoreBlocked("WAL_READ_FAILED") from exc
        previous_sha = "0" * 64
        for sequence, record in enumerate(records, start=1):
            if not isinstance(record, Mapping):
                raise RawTransactionStoreBlocked("WAL_RECORD_INVALID")
            supplied_sha = _valid_sha256(record.get("record_sha256"))
            expected_sha = _stable_sha256(
                {key: value for key, value in record.items() if key != "record_sha256"}
            )
            if (
                record.get("sequence") != sequence
                or record.get("previous_record_sha256") != previous_sha
                or record.get("state") not in _WAL_STATES
                or not supplied_sha
                or not hmac.compare_digest(supplied_sha, expected_sha)
            ):
                raise RawTransactionStoreBlocked("WAL_CHAIN_INVALID")
            previous_sha = supplied_sha
        return [dict(record) for record in records]

    @staticmethod
    def _unresolved_prepared_records(
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in records:
            transaction_sha = str(record.get("transaction_sha256") or "")
            if transaction_sha:
                latest[transaction_sha] = record
        return [
            record for record in latest.values() if record.get("state") == "PREPARED"
        ]

    def _append_wal(self, state: str, request: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
        if state not in _WAL_STATES:
            raise RawTransactionStoreBlocked("WAL_STATE_INVALID")
        source_raw_document_sha256 = request.get(
            "expected_raw_document_sha256",
            request.get("source_raw_document_sha256"),
        )
        if not _valid_sha256(source_raw_document_sha256):
            raise RawTransactionStoreBlocked("WAL_SOURCE_HASH_INVALID")
        records = self._read_wal()
        previous_sha = records[-1]["record_sha256"] if records else "0" * 64
        record = {
            "sequence": len(records) + 1,
            "previous_record_sha256": previous_sha,
            "state": state,
            "transaction_sha256": request["transaction_sha256"],
            "idempotency_key": request["idempotency_key"],
            "source_raw_document_sha256": source_raw_document_sha256,
            "candidate_raw_document_sha256": request["candidate_raw_document_sha256"],
            **extra,
        }
        record["record_sha256"] = _stable_sha256(record)
        try:
            with self._wal.open("a", encoding="utf-8", newline="\n") as file_obj:
                file_obj.write(_canonical_json(record) + "\n")
                file_obj.flush()
                os.fsync(file_obj.fileno())
            self._sync_directory(self._root)
        except RawTransactionStoreBlocked:
            raise
        except Exception as exc:
            raise RawTransactionStoreBlocked("WAL_APPEND_FAILED") from exc
        return record

    def _write_backup(self, source: ExactRawRegistrySnapshotV1, transaction_sha: str) -> Path:
        self._backups.mkdir(parents=True, exist_ok=True)
        self._sync_directory(self._root)
        path = self._backups / f"{source.raw_document_sha256}.{transaction_sha}.json"
        if path.exists():
            if _bytes_sha256(path.read_bytes()) != source.raw_document_sha256:
                raise RawTransactionStoreBlocked("BACKUP_IMMUTABILITY_CONFLICT")
            return path
        try:
            with path.open("xb") as file_obj:
                file_obj.write(source.raw_bytes)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            self._sync_directory(self._backups)
        except RawTransactionStoreBlocked:
            raise
        except Exception as exc:
            raise RawTransactionStoreBlocked("BACKUP_CREATE_FAILED") from exc
        if _bytes_sha256(path.read_bytes()) != source.raw_document_sha256:
            raise RawTransactionStoreBlocked("BACKUP_DURABILITY_CHECK_FAILED")
        return path

    def _stage_bytes(self, data: bytes) -> Path:
        descriptor: int | None = None
        temp_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(
                prefix=".synthetic_trade_registry.", suffix=".tmp", dir=str(self._root)
            )
            temp_path = Path(raw_path)
            with os.fdopen(descriptor, "wb") as file_obj:
                descriptor = None
                file_obj.write(data)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            return temp_path
        except Exception as exc:
            if descriptor is not None:
                os.close(descriptor)
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise RawTransactionStoreBlocked("CANDIDATE_STAGE_FAILED") from exc

    def _replace_with_deadline(self, source: Path, target: Path) -> None:
        deadline = self._monotonic() + self._replace_timeout
        while True:
            try:
                self._replacer(str(source), str(target))
                return
            except PermissionError as exc:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise RawTransactionStoreBlocked("ATOMIC_REPLACE_TIMEOUT") from exc
                self._sleeper(min(self._replace_poll, remaining))

    def _maintenance_shape_valid(self, attestation: Mapping[str, Any]) -> bool:
        return bool(
            isinstance(attestation, Mapping)
            and attestation.get("state") == "QUIESCED"
            and _valid_sha256(attestation.get("maintenance_epoch"))
            and attestation.get("lock_namespace_sha256") == self._lock_namespace
            and attestation.get("registered_writer_count") == 19
            and attestation.get("inflight_mutations") == 0
            and attestation.get("shared_lock_acquired") is True
        )

    def _maintenance_valid(self, attestation: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
        return bool(
            self._maintenance_shape_valid(attestation)
            and attestation.get("maintenance_epoch") == request.get("maintenance_epoch")
        )

    def _validated_backup_bytes(self, prepared: Mapping[str, Any]) -> bytes:
        backup_name = str(prepared.get("backup_name") or "")
        if not backup_name or Path(backup_name).name != backup_name:
            raise RawTransactionStoreBlocked("RECOVERY_BACKUP_NAME_INVALID")
        backup = self._backups / backup_name
        try:
            raw = backup.read_bytes()
        except Exception as exc:
            raise RawTransactionStoreBlocked("RECOVERY_BACKUP_READ_FAILED") from exc
        expected_sha = str(prepared.get("source_raw_document_sha256") or "")
        if not _valid_sha256(expected_sha) or not hmac.compare_digest(
            _bytes_sha256(raw), expected_sha
        ):
            raise RawTransactionStoreBlocked("RECOVERY_BACKUP_INTEGRITY_FAILED")
        return raw

    def _restore_exact_bytes(self, raw: bytes, expected_sha: str) -> None:
        staged = self._stage_bytes(raw)
        try:
            self._replace_with_deadline(staged, self._target)
            staged = None
            self._sync_directory(self._root)
            restored = self.load_exact_raw_registry()
            if not hmac.compare_digest(
                restored.raw_document_sha256, expected_sha
            ):
                raise RawTransactionStoreBlocked("RECOVERY_RESTORE_VERIFY_FAILED")
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)

    def _base_result(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "RAW_TRANSACTION_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_V1_VERSION,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_ready": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "rollback_attempted": False,
            "rollback_confirmed": False,
            "idempotent_replay": False,
            "broker_called": False,
            "no_order_sent": True,
            "reason": None,
        }

    def apply_synthetic_transaction(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base_result()
        if not self._enabled:
            result["reason"] = "RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        try:
            canonical_request = json.loads(_canonical_json(dict(request)))
        except Exception:
            result["reason"] = "TRANSACTION_REQUEST_INVALID"
            return result
        supplied_transaction_sha = _valid_sha256(
            canonical_request.get("transaction_sha256")
        )
        candidate = canonical_request.get("candidate_registry")
        request_valid = bool(
            canonical_request.get("request_version")
            == "SYNTHETIC_RAW_REGISTRY_TRANSACTION_REQUEST_V1"
            and canonical_request.get("scope_attestation")
            == SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1
            and _valid_sha256(canonical_request.get("idempotency_key"))
            and _valid_sha256(canonical_request.get("maintenance_epoch"))
            and _valid_sha256(
                canonical_request.get("expected_raw_document_sha256")
            )
            and _valid_sha256(canonical_request.get("expected_generation_token"))
            and isinstance(candidate, Mapping)
            and canonical_request.get("candidate_raw_document_sha256")
            == _bytes_sha256(_payload_bytes(candidate))
            and supplied_transaction_sha
            and hmac.compare_digest(
                supplied_transaction_sha,
                raw_transaction_request_sha256_v1(canonical_request),
            )
        )
        if not request_valid:
            result["reason"] = "TRANSACTION_REQUEST_INTEGRITY_FAILED"
            return result
        if not self._maintenance_valid(maintenance_attestation, canonical_request):
            result["reason"] = "MAINTENANCE_ATTESTATION_INVALID"
            return result

        staged: Path | None = None
        backup: Path | None = None
        source: ExactRawRegistrySnapshotV1 | None = None
        prepared = False
        replaced = False
        try:
            records = self._read_wal()
            if self._unresolved_prepared_records(records):
                raise RawTransactionStoreBlocked(
                    "UNRESOLVED_PREPARED_TRANSACTION"
                )
            matching = [
                record
                for record in records
                if record.get("idempotency_key")
                == canonical_request["idempotency_key"]
            ]
            if any(
                record.get("transaction_sha256") != supplied_transaction_sha
                for record in matching
            ):
                raise RawTransactionStoreBlocked("IDEMPOTENCY_CONFLICT")
            committed = [record for record in matching if record.get("state") == "COMMITTED"]
            if committed:
                current = self.load_exact_raw_registry()
                if (
                    committed[-1].get("transaction_sha256")
                    != supplied_transaction_sha
                    or current.raw_document_sha256
                    != canonical_request["candidate_raw_document_sha256"]
                ):
                    raise RawTransactionStoreBlocked("IDEMPOTENCY_CONFLICT")
                result.update(
                    {
                        "ok": True,
                        "status": "RAW_TRANSACTION_ALREADY_COMMITTED",
                        "idempotent_replay": True,
                        "write_executed": False,
                        "registry_write": False,
                        "transaction_sha256": supplied_transaction_sha,
                    }
                )
                return result
            if matching and matching[-1].get("state") == "PREPARED":
                raise RawTransactionStoreBlocked("UNRESOLVED_PREPARED_TRANSACTION")

            source = self.load_exact_raw_registry()
            if (
                source.raw_document_sha256
                != canonical_request["expected_raw_document_sha256"]
                or source.generation_token
                != canonical_request["expected_generation_token"]
            ):
                raise RawTransactionStoreBlocked("COMPARE_AND_SWAP_MISMATCH")
            backup = self._write_backup(source, supplied_transaction_sha)
            result["write_executed"] = True
            self._fault_injector("AFTER_BACKUP")
            self._append_wal(
                "PREPARED",
                canonical_request,
                source_generation_token=source.generation_token,
                backup_name=backup.name,
            )
            prepared = True
            self._fault_injector("AFTER_WAL_PREPARED")
            staged = self._stage_bytes(_payload_bytes(candidate))
            current = self.load_exact_raw_registry()
            if (
                current.raw_document_sha256
                != canonical_request["expected_raw_document_sha256"]
                or current.generation_token
                != canonical_request["expected_generation_token"]
            ):
                raise RawTransactionStoreBlocked("COMPARE_AND_SWAP_MISMATCH")
            self._replace_with_deadline(staged, self._target)
            staged = None
            replaced = True
            result["registry_write"] = True
            self._sync_directory(self._root)
            self._fault_injector("AFTER_REPLACE")
            verified = self.load_exact_raw_registry()
            if verified.raw_document_sha256 != canonical_request["candidate_raw_document_sha256"]:
                raise RawTransactionStoreBlocked("CANDIDATE_VERIFY_FAILED")
            self._fault_injector("BEFORE_WAL_COMMIT")
            commit = self._append_wal(
                "COMMITTED",
                canonical_request,
                backup_name=backup.name,
                committed_raw_document_sha256=verified.raw_document_sha256,
            )
            result.update(
                {
                    "ok": True,
                    "status": "RAW_TRANSACTION_COMMITTED_SYNTHETIC_ONLY",
                    "write_executed": True,
                    "registry_write": True,
                    "transaction_sha256": supplied_transaction_sha,
                    "source_raw_document_sha256": source.raw_document_sha256,
                    "candidate_raw_document_sha256": verified.raw_document_sha256,
                    "backup_name": backup.name,
                    "wal_commit_record_sha256": commit["record_sha256"],
                }
            )
            return result
        except Exception as exc:
            reason = (
                exc.reason
                if isinstance(exc, RawTransactionStoreBlocked)
                else "INJECTED_OR_INTERNAL_TRANSACTION_FAILURE"
            )
            result["reason"] = reason
            result["transaction_sha256"] = supplied_transaction_sha
            if replaced and source is not None:
                result["rollback_attempted"] = True
                try:
                    staged = self._stage_bytes(source.raw_bytes)
                    self._replace_with_deadline(staged, self._target)
                    staged = None
                    self._sync_directory(self._root)
                    restored = self.load_exact_raw_registry()
                    result["rollback_confirmed"] = hmac.compare_digest(
                        restored.raw_document_sha256,
                        source.raw_document_sha256,
                    )
                    if result["rollback_confirmed"]:
                        self._append_wal(
                            "ROLLED_BACK",
                            canonical_request,
                            failure_reason=reason,
                            restored_raw_document_sha256=restored.raw_document_sha256,
                        )
                except Exception:
                    result["rollback_confirmed"] = False
            elif prepared:
                try:
                    self._append_wal(
                        "ABORTED", canonical_request, failure_reason=reason
                    )
                except Exception:
                    pass
            result["status"] = (
                "RAW_TRANSACTION_FAILED_ROLLED_BACK"
                if result["rollback_confirmed"]
                else "RAW_TRANSACTION_FAILED_CLOSED"
            )
            return result
        finally:
            if staged is not None:
                try:
                    staged.unlink(missing_ok=True)
                except Exception:
                    pass

    def reconcile_synthetic_prepared_transaction(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Resolve one interrupted synthetic transaction under a fresh lease."""

        result = self._base_result()
        result["status"] = "RAW_TRANSACTION_RECOVERY_BLOCKED"
        transaction_sha = _valid_sha256(transaction_sha256)
        if not self._enabled:
            result["reason"] = "RAW_TRANSACTION_STORE_DEFAULT_OFF"
            return result
        if not transaction_sha:
            result["reason"] = "RECOVERY_TRANSACTION_SHA_INVALID"
            return result
        if not self._maintenance_shape_valid(maintenance_attestation):
            result["reason"] = "MAINTENANCE_ATTESTATION_INVALID"
            return result
        result["transaction_sha256"] = transaction_sha
        try:
            records = self._read_wal()
            matching = [
                record
                for record in records
                if record.get("transaction_sha256") == transaction_sha
            ]
            if not matching:
                raise RawTransactionStoreBlocked("RECOVERY_TRANSACTION_NOT_FOUND")
            latest = matching[-1]
            latest_state = latest.get("state")
            if latest_state in {"COMMITTED", "ABORTED", "ROLLED_BACK"}:
                result.update(
                    {
                        "ok": True,
                        "status": f"RAW_TRANSACTION_RECOVERY_ALREADY_{latest_state}",
                        "idempotent_replay": True,
                        "terminal_state": latest_state,
                    }
                )
                return result
            if latest_state != "PREPARED":
                raise RawTransactionStoreBlocked("RECOVERY_STATE_INVALID")

            backup_raw = self._validated_backup_bytes(latest)
            source_sha = str(latest["source_raw_document_sha256"])
            candidate_sha = str(latest["candidate_raw_document_sha256"])
            current = None
            try:
                current = self.load_exact_raw_registry()
            except RawTransactionStoreBlocked:
                current = None

            if current is not None and hmac.compare_digest(
                current.raw_document_sha256, source_sha
            ):
                terminal = self._append_wal(
                    "ABORTED",
                    latest,
                    failure_reason="RECOVERY_SOURCE_INTACT",
                    recovery_maintenance_epoch=maintenance_attestation[
                        "maintenance_epoch"
                    ],
                )
                result.update(
                    {
                        "ok": True,
                        "status": "RAW_TRANSACTION_RECOVERY_ABORTED_SOURCE_INTACT",
                        "write_executed": True,
                        "registry_write": False,
                        "terminal_state": "ABORTED",
                        "wal_terminal_record_sha256": terminal["record_sha256"],
                    }
                )
                return result

            if current is not None and hmac.compare_digest(
                current.raw_document_sha256, candidate_sha
            ):
                self._sync_directory(self._root)
                terminal = self._append_wal(
                    "COMMITTED",
                    latest,
                    backup_name=latest.get("backup_name"),
                    committed_raw_document_sha256=candidate_sha,
                    recovery_maintenance_epoch=maintenance_attestation[
                        "maintenance_epoch"
                    ],
                )
                result.update(
                    {
                        "ok": True,
                        "status": "RAW_TRANSACTION_RECOVERY_COMMITTED_CANDIDATE_PRESENT",
                        "write_executed": True,
                        "registry_write": False,
                        "terminal_state": "COMMITTED",
                        "wal_terminal_record_sha256": terminal["record_sha256"],
                    }
                )
                return result

            if current is not None:
                raise RawTransactionStoreBlocked(
                    "RECOVERY_AMBIGUOUS_TARGET_HASH"
                )

            result["rollback_attempted"] = True
            self._restore_exact_bytes(backup_raw, source_sha)
            result["write_executed"] = True
            result["registry_write"] = True
            result["rollback_confirmed"] = True
            terminal = self._append_wal(
                "ROLLED_BACK",
                latest,
                failure_reason="RECOVERY_TARGET_MISSING_OR_UNREADABLE",
                restored_raw_document_sha256=source_sha,
                recovery_maintenance_epoch=maintenance_attestation[
                    "maintenance_epoch"
                ],
            )
            result.update(
                {
                    "ok": True,
                    "status": "RAW_TRANSACTION_RECOVERY_ROLLED_BACK_FROM_BACKUP",
                    "terminal_state": "ROLLED_BACK",
                    "wal_terminal_record_sha256": terminal["record_sha256"],
                }
            )
            return result
        except Exception as exc:
            result["reason"] = (
                exc.reason
                if isinstance(exc, RawTransactionStoreBlocked)
                else "RECOVERY_INTERNAL_FAILURE"
            )
            return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_TRANSACTION_STORE_V1_VERSION",
    "SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1",
    "ExactRawRegistrySnapshotV1",
    "IsolatedRawRegistryTransactionStoreV1",
    "RawTransactionStoreBlocked",
    "build_raw_transaction_request_v1",
    "raw_transaction_request_sha256_v1",
]
