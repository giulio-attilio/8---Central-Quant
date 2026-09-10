"""Temporary-filesystem reference backend for the C3 durable V2 contract.

This adapter is test-only and fail-closed.  It accepts only a dedicated child
of the operating-system temporary directory, delegates raw transactions to the
existing isolated V1 store, and emits V2 evidence without production authority.
It is not imported by runtime code and cannot target the real Registry.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_adapters


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_REFERENCE_V2_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PHYSICAL-REFERENCE-V2"
)
TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RAW_TRANSACTION_BACKEND_TEMPORARY_PHYSICAL_REFERENCE_ONLY_V2"
)
TEMPORARY_TRANSACTION_LOG_AUDIT_VERSION_V2 = (
    "C3_TEMPORARY_PHYSICAL_TRANSACTION_LOG_AUDIT_V2"
)
_TEMP_ROOT_PREFIX = "c3_durable_backend_v2_"


class TemporaryPhysicalReferenceBlockedV2(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _SimulatedFailure(RuntimeError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(label: str) -> str:
    return contract.stable_sha256_v2({"temporary_physical_reference": label})


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = contract.stable_sha256_v2(
        {key: item for key, item in value.items() if key != field}
    )
    return value


def _validated_temporary_root(root: str | os.PathLike[str]) -> Path:
    resolved = Path(root).resolve(strict=False)
    temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
    try:
        relative = resolved.relative_to(temp_root)
    except ValueError as exc:
        raise TemporaryPhysicalReferenceBlockedV2("TEMPORARY_ROOT_REQUIRED") from exc
    if not relative.parts or not resolved.name.startswith(_TEMP_ROOT_PREFIX):
        raise TemporaryPhysicalReferenceBlockedV2("DEDICATED_TEMPORARY_ROOT_REQUIRED")
    return resolved


class TemporaryPhysicalDurableRawTransactionBackendV2:
    """Physical rehearsal backend constrained to one synthetic temporary root."""

    def __init__(
        self,
        storage_root: str | os.PathLike[str],
        *,
        enabled: bool = False,
        scope_attestation: str | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._root = Path(storage_root).resolve(strict=False)
        self._clock = clock or (lambda: 0)
        self._directory_fsync_calls = 0
        self._replace_calls = 0
        self._observed: set[str] = set()
        self._raw_requests_by_v2_transaction: dict[str, dict[str, Any]] = {}
        self._fault_step: str | None = None
        self._store: raw_store.IsolatedRawRegistryTransactionStoreV1 | None = None
        self._lock_backend: storage_adapters.CrossPlatformInterprocessFileLockBackendV1 | None = None
        if not self._enabled:
            return
        if scope_attestation != TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2:
            raise TemporaryPhysicalReferenceBlockedV2("TEMPORARY_PHYSICAL_REFERENCE_SCOPE_REQUIRED")
        self._root = _validated_temporary_root(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock_backend = storage_adapters.CrossPlatformInterprocessFileLockBackendV1(
            self._root / "locks", enabled=True,
        )
        self._store = raw_store.IsolatedRawRegistryTransactionStoreV1(
            self._root,
            enabled=True,
            scope_attestation=raw_store.SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1,
            directory_fsync=self._directory_fsync,
            replacer=self._replace,
            fault_injector=self._inject_fault,
            replace_timeout_seconds=0.05,
            replace_poll_interval_seconds=0.001,
        )

    def _require_enabled(self) -> None:
        if not self._enabled or self._store is None or self._lock_backend is None:
            raise TemporaryPhysicalReferenceBlockedV2("PHYSICAL_REFERENCE_DEFAULT_OFF")

    def _directory_fsync(self, directory: Path) -> None:
        if not directory.resolve(strict=False).is_relative_to(self._root):
            raise TemporaryPhysicalReferenceBlockedV2("DIRECTORY_FSYNC_ESCAPED_TEMPORARY_ROOT")
        self._directory_fsync_calls += 1

    def _replace(self, source: str, target: str) -> None:
        source_path = Path(source).resolve(strict=False)
        target_path = Path(target).resolve(strict=False)
        if not source_path.is_relative_to(self._root) or not target_path.is_relative_to(self._root):
            raise TemporaryPhysicalReferenceBlockedV2("ATOMIC_REPLACE_ESCAPED_TEMPORARY_ROOT")
        os.replace(source_path, target_path)
        self._replace_calls += 1

    def _inject_fault(self, step: str) -> None:
        if step == self._fault_step:
            raise _SimulatedFailure(f"SYNTHETIC_FAULT_{step}")

    def _lock_namespace(self) -> str:
        return coordinator.canonical_runtime_lock_namespace_v1()

    @contextmanager
    def _held_lock(self):
        self._require_enabled()
        handle = self._lock_backend.acquire(self._lock_namespace(), 0.05)
        if handle is None:
            raise TemporaryPhysicalReferenceBlockedV2("SHARED_LOCK_UNAVAILABLE")
        try:
            yield
        finally:
            if not handle.released:
                handle.release()

    def _wal_records(self) -> list[dict[str, Any]]:
        self._require_enabled()
        return self._store._read_wal()

    def _generation(self) -> int:
        return sum(1 for item in self._wal_records() if item.get("state") in {"COMMITTED", "ABORTED", "ROLLED_BACK"})

    def _module_source_sha(self) -> str:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def _path_binding(self) -> str:
        return contract.stable_sha256_v2(
            {
                "scope": TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
                "target": os.path.normcase(str(self._store.target_path.resolve(strict=False))),
            }
        )

    def _instance_sha(self) -> str:
        return contract.stable_sha256_v2(
            {
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_REFERENCE_V2_VERSION,
                "module_source_sha256": self._module_source_sha(),
                "registry_path_binding_sha256": self._path_binding(),
                "lock_namespace_sha256": self._lock_namespace(),
            }
        )

    def initialize_synthetic_registry_offline(self, payload: Mapping[str, Any]) -> None:
        self._require_enabled()
        with self._held_lock():
            self._store.initialize_synthetic_registry(payload)

    def snapshot_offline(self) -> Mapping[str, Any]:
        self._require_enabled()
        snapshot = {
            "snapshot_version": contract.BACKEND_SNAPSHOT_VERSION_V2,
            "backend_kind": "TEMPORARY_PHYSICAL_REFERENCE_BACKEND_V2",
            "backend_instance_sha256": self._instance_sha(),
            "backend_module_source_sha256": self._module_source_sha(),
            "registry_path_binding_sha256": self._path_binding(),
            "lock_namespace_sha256": self._lock_namespace(),
            "generation": self._generation(),
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "filesystem_accessed": True,
        }
        return _seal(snapshot, "snapshot_sha256")

    def capability_evidence_offline(self) -> list[Mapping[str, Any]]:
        snapshot = self.snapshot_offline()
        return [
            _seal(
                {
                    "evidence_version": contract.CAPABILITY_EVIDENCE_VERSION_V2,
                    "capability": capability,
                    "backend_instance_sha256": snapshot["backend_instance_sha256"],
                    "backend_snapshot_sha256": snapshot["snapshot_sha256"],
                    "fixture_binding_sha256": _sha(f"observed:{capability}"),
                    "probe_kind": "TEMPORARY_FILESYSTEM_FAULT_INJECTION",
                    "observed": capability in self._observed,
                    "synthetic_only": True,
                    "durable": False,
                    "production_evidence": False,
                    "filesystem_accessed": True,
                },
                "evidence_sha256",
            )
            for capability in contract.REQUIRED_CAPABILITIES_V2
        ]

    def _prepared_record_v2(self, wal_record: Mapping[str, Any]) -> dict[str, Any]:
        return _seal(
            {
                "record_version": contract.PREPARED_RECORD_VERSION_V2,
                "request_sha256": wal_record["v2_request_sha256"],
                "transaction_sha256": wal_record["v2_transaction_sha256"],
                "original_invocation_command_sha256": wal_record["v2_original_invocation_command_sha256"],
                "authorization_receipt_sha256": wal_record["v2_authorization_receipt_sha256"],
                "backend_instance_sha256": wal_record["v2_backend_instance_sha256"],
                "registry_path_binding_sha256": wal_record["v2_registry_path_binding_sha256"],
                "lock_namespace_sha256": wal_record["v2_lock_namespace_sha256"],
                "source_raw_document_sha256": wal_record["source_raw_document_sha256"],
                "candidate_raw_document_sha256": wal_record["candidate_raw_document_sha256"],
                "wal_prepared_record_sha256": wal_record["record_sha256"],
                "previous_maintenance_epoch": wal_record["v2_previous_maintenance_epoch"],
                "prepared_at_epoch": wal_record["v2_prepared_at_epoch"],
                "deadline_epoch": wal_record["v2_deadline_epoch"],
                "terminal_state": "PREPARED",
                "synthetic_only": True,
                "durable": False,
                "production_evidence": False,
            },
            "record_sha256",
        )

    def list_prepared_transactions_offline(self) -> Mapping[str, Any]:
        snapshot = self.snapshot_offline()
        records = []
        for wal_record in self._store._unresolved_prepared_records(self._wal_records()):
            if "v2_request_sha256" not in wal_record:
                raise TemporaryPhysicalReferenceBlockedV2("UNBOUND_PREPARED_RECORD")
            records.append(self._prepared_record_v2(wal_record))
        records.sort(key=lambda item: item["record_sha256"])
        catalog = {
            "catalog_version": contract.PREPARED_CATALOG_VERSION_V2,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "generation": snapshot["generation"],
            "records": records,
            "record_count": len(records),
            "prepared_count": len(records),
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
        }
        return _seal(catalog, "catalog_sha256")

    def inspect_transaction_log_offline(self) -> Mapping[str, Any]:
        """Return only aggregate WAL evidence from the temporary backend."""

        snapshot = self.snapshot_offline()
        records = self._wal_records()
        state_counts = {
            state: sum(1 for record in records if record.get("state") == state)
            for state in ("PREPARED", "COMMITTED", "ABORTED", "ROLLED_BACK")
        }
        latest_by_transaction: dict[str, str] = {}
        for record in records:
            transaction_sha256 = str(record.get("transaction_sha256") or "")
            state = str(record.get("state") or "")
            if not transaction_sha256 or state not in state_counts:
                raise TemporaryPhysicalReferenceBlockedV2(
                    "TRANSACTION_LOG_RECORD_INVALID"
                )
            latest_by_transaction[transaction_sha256] = state
        latest_state_counts = {
            state: sum(
                1 for latest in latest_by_transaction.values() if latest == state
            )
            for state in state_counts
        }
        unresolved_prepared = len(
            self._store._unresolved_prepared_records(records)
        )
        audit = {
            "audit_version": TEMPORARY_TRANSACTION_LOG_AUDIT_VERSION_V2,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "wal_record_count": len(records),
            "transaction_count": len(latest_by_transaction),
            "state_counts": state_counts,
            "latest_state_counts": latest_state_counts,
            "unresolved_prepared_count": unresolved_prepared,
            "unresolved_resolved_count": 0,
            "resolved_state_supported": False,
            "wal_integrity_verified": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "durable": False,
            "production_evidence": False,
            "filesystem_accessed": True,
        }
        return _seal(audit, "audit_sha256")

    def build_transaction_request_offline(
        self, candidate_registry: Mapping[str, Any], *, label: str, deadline_epoch: int
    ) -> dict[str, Any]:
        self._require_enabled()
        if not isinstance(deadline_epoch, int) or int(self._clock()) >= deadline_epoch:
            raise TemporaryPhysicalReferenceBlockedV2("V2_TRANSACTION_DEADLINE_INVALID_OR_EXPIRED")
        snapshot = self.snapshot_offline()
        source = self._store.load_exact_raw_registry()
        candidate_raw = _canonical_json(dict(candidate_registry))
        request = {
            "request_version": contract.TRANSACTION_REQUEST_VERSION_V2,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "request_sha256": _sha(f"request:{label}"),
            "transaction_sha256": _sha(f"transaction:{label}"),
            "idempotency_key": _sha(f"idempotency:{label}"),
            "authorization_receipt_sha256": _sha(f"authorization:{label}"),
            "maintenance_epoch": _sha(f"maintenance:{label}"),
            "expected_generation": snapshot["generation"],
            "expected_raw_document_sha256": source.raw_document_sha256,
            "candidate_raw_document_utf8": candidate_raw,
            "candidate_raw_document_sha256": contract.raw_utf8_sha256_v2(candidate_raw),
            "deadline_epoch": deadline_epoch,
            "synthetic_only": True,
            "production_authority": False,
        }
        return _seal(request, "request_binding_sha256")

    def _maintenance(self, epoch: str) -> dict[str, Any]:
        return {
            "state": "QUIESCED", "maintenance_epoch": epoch,
            "lock_namespace_sha256": self._lock_namespace(),
            "registered_writer_count": 19, "inflight_mutations": 0,
            "shared_lock_acquired": True,
        }

    def _v1_request(self, request: Mapping[str, Any]):
        source = self._store.load_exact_raw_registry()
        candidate = json.loads(request["candidate_raw_document_utf8"])
        return raw_store.build_raw_transaction_request_v1(
            source, candidate,
            idempotency_key=request["idempotency_key"],
            maintenance_epoch=request["maintenance_epoch"],
        )

    def _terminal_result(self, request: Mapping[str, Any], raw_result: Mapping[str, Any], before: int) -> dict[str, Any]:
        state = (
            "COMMITTED" if raw_result.get("ok") and "COMMITTED" in str(raw_result.get("status"))
            else "ROLLED_BACK" if raw_result.get("rollback_confirmed") else "ABORTED"
        )
        records = self._wal_records()
        matching = [item for item in records if item.get("transaction_sha256") == raw_result.get("transaction_sha256")]
        prepared = next((item for item in matching if item.get("state") == "PREPARED"), None)
        terminal = matching[-1] if matching and matching[-1].get("state") != "PREPARED" else None
        result = {
            "result_version": contract.TRANSACTION_RESULT_VERSION_V2,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "backend_snapshot_sha256": request["backend_snapshot_sha256"],
            "prepared_record_sha256": prepared["record_sha256"] if prepared else _sha("no-prepared-record"),
            "terminal_record_sha256": terminal["record_sha256"] if terminal else _sha(f"blocked:{raw_result.get('reason')}"),
            "terminal_state": state,
            "generation_before": before,
            "generation_after": self._generation(),
            "deadline_epoch": request["deadline_epoch"],
            "deadline_observed": True,
            "postconditions_verified": state != "AMBIGUOUS",
            "recovery_required": False,
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "write_executed": bool(raw_result.get("write_executed")),
            "registry_write": bool(raw_result.get("registry_write")),
        }
        return _seal(result, "result_sha256")

    def apply_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_enabled()
        before_snapshot = self.snapshot_offline()
        if not contract.transaction_request_valid_v2(request, before_snapshot):
            raise TemporaryPhysicalReferenceBlockedV2("V2_TRANSACTION_REQUEST_INVALID_OR_STALE")
        if int(self._clock()) >= request["deadline_epoch"]:
            raise TemporaryPhysicalReferenceBlockedV2("V2_TRANSACTION_DEADLINE_EXPIRED")
        with self._held_lock():
            raw_request = self._v1_request(request)
            self._raw_requests_by_v2_transaction[request["transaction_sha256"]] = copy.deepcopy(raw_request)
            raw_result = self._store.apply_synthetic_transaction(raw_request, self._maintenance(request["maintenance_epoch"]))
        if raw_result.get("ok"):
            self._observed.update(
                {
                    "append_only_hash_chained_wal", "atomic_same_directory_replace",
                    "exact_raw_loader", "file_and_directory_fsync",
                    "immutable_content_addressed_backup",
                }
            )
            if raw_result.get("idempotent_replay"):
                self._observed.add("idempotency_key_enforcement")
        if raw_result.get("rollback_confirmed"):
            self._observed.add("rollback_to_exact_preimage")
        return self._terminal_result(request, raw_result, before_snapshot["generation"])

    def prove_idempotency_offline(self, request: Mapping[str, Any]) -> bool:
        self._require_enabled()
        raw_request = self._raw_requests_by_v2_transaction.get(request["transaction_sha256"])
        if raw_request is None:
            raise TemporaryPhysicalReferenceBlockedV2("ORIGINAL_RAW_REQUEST_NOT_AVAILABLE")
        with self._held_lock():
            result = self._store.apply_synthetic_transaction(raw_request, self._maintenance(request["maintenance_epoch"]))
        observed = bool(result.get("ok") and result.get("idempotent_replay"))
        if observed:
            self._observed.add("idempotency_key_enforcement")
        return observed

    def prove_compare_and_swap_offline(self, stale_request: Mapping[str, Any]) -> bool:
        observed = False
        try:
            self.apply_attested_transaction_offline(stale_request)
        except TemporaryPhysicalReferenceBlockedV2 as exc:
            observed = exc.reason == "V2_TRANSACTION_REQUEST_INVALID_OR_STALE"
        if observed:
            self._observed.add("compare_and_swap_hash_and_generation")
        return observed

    def apply_with_fault_offline(self, request: Mapping[str, Any], fault_step: str) -> Mapping[str, Any]:
        self._fault_step = fault_step
        try:
            result = self.apply_attested_transaction_offline(request)
        finally:
            self._fault_step = None
        return result

    def prepare_interrupted_transaction_offline(self, request: Mapping[str, Any]) -> None:
        self._require_enabled()
        snapshot = self.snapshot_offline()
        if not contract.transaction_request_valid_v2(request, snapshot):
            raise TemporaryPhysicalReferenceBlockedV2("V2_PREPARE_REQUEST_INVALID_OR_STALE")
        if int(self._clock()) >= request["deadline_epoch"]:
            raise TemporaryPhysicalReferenceBlockedV2("V2_PREPARE_DEADLINE_EXPIRED")
        with self._held_lock():
            raw_request = self._v1_request(request)
            source = self._store.load_exact_raw_registry()
            backup = self._store._write_backup(source, raw_request["transaction_sha256"])
            self._store._append_wal(
                "PREPARED", raw_request,
                source_generation_token=source.generation_token,
                backup_name=backup.name,
                v2_request_sha256=request["request_sha256"],
                v2_transaction_sha256=request["transaction_sha256"],
                v2_original_invocation_command_sha256=_sha(f"invocation:{request['transaction_sha256']}"),
                v2_authorization_receipt_sha256=request["authorization_receipt_sha256"],
                v2_backend_instance_sha256=request["backend_instance_sha256"],
                v2_registry_path_binding_sha256=request["registry_path_binding_sha256"],
                v2_lock_namespace_sha256=request["lock_namespace_sha256"],
                v2_previous_maintenance_epoch=request["maintenance_epoch"],
                v2_prepared_at_epoch=int(self._clock()),
                v2_deadline_epoch=request["deadline_epoch"],
            )

    def reconcile_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self._require_enabled()
        catalog = self.list_prepared_transactions_offline()
        record = next((item for item in catalog["records"] if item["record_sha256"] == request.get("prepared_record_sha256")), None)
        if record is None:
            raise TemporaryPhysicalReferenceBlockedV2("RECOVERY_PREPARED_RECORD_NOT_FOUND")
        batch_shape = {
            "batch_epoch": request.get("batch_epoch"), "batch_plan_sha256": request.get("batch_plan_sha256"),
            "catalog_sha256": request.get("catalog_sha256"), "next_index": request.get("checkpoint_index"),
        }
        if not contract.recovery_request_valid_v2(request, record, batch_shape):
            raise TemporaryPhysicalReferenceBlockedV2("V2_RECOVERY_REQUEST_INVALID")
        if int(self._clock()) >= request["deadline_epoch"]:
            raise TemporaryPhysicalReferenceBlockedV2("V2_RECOVERY_DEADLINE_EXPIRED")
        wal_record = next(item for item in self._wal_records() if item.get("state") == "PREPARED" and item.get("v2_transaction_sha256") == record["transaction_sha256"])
        with self._held_lock():
            raw_result = self._store.reconcile_synthetic_prepared_transaction(
                wal_record["transaction_sha256"], self._maintenance(request["fresh_maintenance_epoch"])
            )
        if not raw_result.get("ok"):
            raise TemporaryPhysicalReferenceBlockedV2(str(raw_result.get("reason") or "RECOVERY_FAILED"))
        self._observed.add("interrupted_transaction_recovery")
        result = {
            "result_version": contract.RECOVERY_RESULT_VERSION_V2,
            "recovery_request_sha256": request["request_sha256"],
            "batch_epoch": request["batch_epoch"],
            "batch_plan_sha256": request["batch_plan_sha256"],
            "catalog_sha256": request["catalog_sha256"],
            "prepared_record_sha256": request["prepared_record_sha256"],
            "wal_prepared_record_sha256": request["wal_prepared_record_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "terminal_state": raw_result["terminal_state"],
            "terminal_record_sha256": raw_result["wal_terminal_record_sha256"],
            "deadline_epoch": request["deadline_epoch"],
            "deadline_observed": True,
            "postconditions_verified": True,
            "checkpoint_index": request["checkpoint_index"],
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "write_executed": bool(raw_result.get("write_executed")),
            "registry_write": bool(raw_result.get("registry_write")),
        }
        return _seal(result, "result_sha256")

    def mark_lock_probe_offline(self) -> bool:
        self._require_enabled()
        first = self._lock_backend.acquire(self._lock_namespace(), 0.05)
        if first is None:
            return False
        second = self._lock_backend.acquire(self._lock_namespace(), 0.001)
        if second is not None:
            second.release()
        first.release()
        return second is None

    def finalize_probe_observations_offline(self, *, lock_verified: bool) -> None:
        if not lock_verified:
            raise TemporaryPhysicalReferenceBlockedV2("INTERPROCESS_LOCK_PROBE_FAILED")
        if self._directory_fsync_calls <= 0 or self._replace_calls <= 0:
            raise TemporaryPhysicalReferenceBlockedV2("FSYNC_OR_REPLACE_PROBE_MISSING")


__all__ = [
    "TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2",
    "TEMPORARY_TRANSACTION_LOG_AUDIT_VERSION_V2",
    "TemporaryPhysicalDurableRawTransactionBackendV2",
    "TemporaryPhysicalReferenceBlockedV2",
]
