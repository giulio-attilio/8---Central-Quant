"""Offline conformance contract for a future durable C3 raw backend.

The module validates synthetic evidence only.  It has no filesystem, Registry,
runtime, network, broker, or activation entrypoint.  Passing this contract is
not production readiness: every accepted receipt is explicitly synthetic and
non-durable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_CONTRACT_V2_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-CONFORMANCE-CONTRACT-V2"
)
OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2 = (
    "C3_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_OFFLINE_ONLY_V2"
)
BACKEND_SNAPSHOT_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_SNAPSHOT_SYNTHETIC_V2"
CAPABILITY_EVIDENCE_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_CAPABILITY_EVIDENCE_SYNTHETIC_V2"
PREPARED_RECORD_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_PREPARED_RECORD_SYNTHETIC_V2"
PREPARED_CATALOG_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_PREPARED_CATALOG_SYNTHETIC_V2"
TRANSACTION_REQUEST_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_TRANSACTION_REQUEST_SYNTHETIC_V2"
TRANSACTION_RESULT_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_TRANSACTION_RESULT_SYNTHETIC_V2"
RECOVERY_REQUEST_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_RECOVERY_REQUEST_SYNTHETIC_V2"
RECOVERY_RESULT_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_RECOVERY_RESULT_SYNTHETIC_V2"
RECOVERY_BATCH_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_RESUMABLE_RECOVERY_BATCH_SYNTHETIC_V2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CAPABILITIES_V2 = (
    "append_only_hash_chained_wal",
    "atomic_same_directory_replace",
    "compare_and_swap_hash_and_generation",
    "exact_raw_loader",
    "file_and_directory_fsync",
    "idempotency_key_enforcement",
    "immutable_content_addressed_backup",
    "interrupted_transaction_recovery",
    "rollback_to_exact_preimage",
)

_SNAPSHOT_KEYS = frozenset(
    {
        "snapshot_version", "backend_kind", "backend_instance_sha256",
        "backend_module_source_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "generation", "synthetic_only", "durable",
        "production_evidence", "filesystem_accessed", "snapshot_sha256",
    }
)
_CAPABILITY_KEYS = frozenset(
    {
        "evidence_version", "capability", "backend_instance_sha256",
        "backend_snapshot_sha256", "fixture_binding_sha256", "probe_kind",
        "observed", "synthetic_only", "durable", "production_evidence",
        "filesystem_accessed", "evidence_sha256",
    }
)
_PREPARED_RECORD_KEYS = frozenset(
    {
        "record_version", "request_sha256", "transaction_sha256",
        "original_invocation_command_sha256", "authorization_receipt_sha256",
        "backend_instance_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "source_raw_document_sha256",
        "candidate_raw_document_sha256", "wal_prepared_record_sha256",
        "previous_maintenance_epoch",
        "prepared_at_epoch", "deadline_epoch", "terminal_state",
        "synthetic_only", "durable", "production_evidence", "record_sha256",
    }
)
_CATALOG_KEYS = frozenset(
    {
        "catalog_version", "backend_instance_sha256", "backend_snapshot_sha256",
        "registry_path_binding_sha256", "lock_namespace_sha256", "generation",
        "records", "record_count", "prepared_count", "synthetic_only", "durable",
        "production_evidence", "catalog_sha256",
    }
)
_TRANSACTION_REQUEST_KEYS = frozenset(
    {
        "request_version", "backend_instance_sha256", "backend_snapshot_sha256",
        "registry_path_binding_sha256", "lock_namespace_sha256", "request_sha256",
        "transaction_sha256", "idempotency_key", "authorization_receipt_sha256",
        "maintenance_epoch", "expected_generation", "expected_raw_document_sha256",
        "candidate_raw_document_utf8", "candidate_raw_document_sha256", "deadline_epoch", "synthetic_only",
        "production_authority", "request_binding_sha256",
    }
)
_TRANSACTION_RESULT_KEYS = frozenset(
    {
        "result_version", "request_binding_sha256", "request_sha256",
        "transaction_sha256", "backend_instance_sha256", "backend_snapshot_sha256",
        "prepared_record_sha256", "terminal_record_sha256", "terminal_state",
        "generation_before", "generation_after", "deadline_epoch",
        "deadline_observed", "postconditions_verified", "recovery_required",
        "synthetic_only", "durable", "production_evidence", "write_executed",
        "registry_write", "result_sha256",
    }
)
_RECOVERY_REQUEST_KEYS = frozenset(
    {
        "request_version", "batch_epoch", "batch_plan_sha256", "catalog_sha256",
        "prepared_record_sha256", "wal_prepared_record_sha256",
        "original_request_sha256",
        "original_invocation_command_sha256", "original_authorization_receipt_sha256",
        "recovery_authorization_receipt_sha256", "transaction_sha256",
        "backend_instance_sha256", "backend_snapshot_sha256",
        "registry_path_binding_sha256", "lock_namespace_sha256",
        "source_raw_document_sha256", "candidate_raw_document_sha256",
        "previous_maintenance_epoch", "fresh_maintenance_epoch", "deadline_epoch",
        "checkpoint_index", "synthetic_only", "production_authority", "request_sha256",
    }
)
_RECOVERY_RESULT_KEYS = frozenset(
    {
        "result_version", "recovery_request_sha256", "batch_epoch",
        "batch_plan_sha256", "catalog_sha256", "prepared_record_sha256",
        "wal_prepared_record_sha256",
        "transaction_sha256", "backend_instance_sha256", "terminal_state",
        "terminal_record_sha256", "deadline_epoch", "deadline_observed",
        "postconditions_verified", "checkpoint_index", "synthetic_only", "durable",
        "production_evidence", "write_executed", "registry_write", "result_sha256",
    }
)
_BATCH_KEYS = frozenset(
    {
        "batch_version", "batch_epoch", "backend_instance_sha256",
        "backend_snapshot_sha256", "catalog_sha256", "catalog_generation",
        "item_record_sha256s", "item_count", "next_index", "terminal_result_sha256s",
        "complete", "deadline_epoch", "synthetic_only", "durable",
        "production_authority", "batch_plan_sha256",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_sha256_v2(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def raw_utf8_sha256_v2(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("raw UTF-8 document must be text")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return stable_sha256_v2({name: item for name, item in value.items() if name != key})


def _sha(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _exact_hash(value: Any, keys: frozenset[str], hash_key: str) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and bool(_sha(value.get(hash_key)))
        and value[hash_key] == _hash_without(value, hash_key)
    )


def backend_snapshot_valid_v2(value: Any) -> bool:
    return bool(
        _exact_hash(value, _SNAPSHOT_KEYS, "snapshot_sha256")
        and value["snapshot_version"] == BACKEND_SNAPSHOT_VERSION_V2
        and all(_sha(value[key]) for key in (
            "backend_instance_sha256", "backend_module_source_sha256",
            "registry_path_binding_sha256", "lock_namespace_sha256"
        ))
        and isinstance(value["generation"], int) and value["generation"] >= 0
        and value["synthetic_only"] is True and value["durable"] is False
        and value["production_evidence"] is False
        and isinstance(value["filesystem_accessed"], bool)
    )


def capability_evidence_valid_v2(value: Any, snapshot: Mapping[str, Any]) -> bool:
    return bool(
        _exact_hash(value, _CAPABILITY_KEYS, "evidence_sha256")
        and value["evidence_version"] == CAPABILITY_EVIDENCE_VERSION_V2
        and value["capability"] in REQUIRED_CAPABILITIES_V2
        and value["backend_instance_sha256"] == snapshot["backend_instance_sha256"]
        and value["backend_snapshot_sha256"] == snapshot["snapshot_sha256"]
        and bool(_sha(value["fixture_binding_sha256"]))
        and value["probe_kind"] in {
            "DETERMINISTIC_IN_MEMORY_FAULT_INJECTION",
            "TEMPORARY_FILESYSTEM_FAULT_INJECTION",
        }
        and value["observed"] is True and value["synthetic_only"] is True
        and value["durable"] is False and value["production_evidence"] is False
        and value["filesystem_accessed"] is snapshot["filesystem_accessed"]
    )


def prepared_record_valid_v2(value: Any, snapshot: Mapping[str, Any]) -> bool:
    return bool(
        _exact_hash(value, _PREPARED_RECORD_KEYS, "record_sha256")
        and value["record_version"] == PREPARED_RECORD_VERSION_V2
        and all(_sha(value[key]) for key in _PREPARED_RECORD_KEYS if key.endswith("_sha256"))
        and value["backend_instance_sha256"] == snapshot["backend_instance_sha256"]
        and value["registry_path_binding_sha256"] == snapshot["registry_path_binding_sha256"]
        and value["lock_namespace_sha256"] == snapshot["lock_namespace_sha256"]
        and value["terminal_state"] == "PREPARED"
        and isinstance(value["prepared_at_epoch"], int)
        and isinstance(value["deadline_epoch"], int)
        and value["prepared_at_epoch"] < value["deadline_epoch"]
        and value["synthetic_only"] is True and value["durable"] is False
        and value["production_evidence"] is False
    )


def prepared_catalog_valid_v2(value: Any, snapshot: Mapping[str, Any]) -> bool:
    if not _exact_hash(value, _CATALOG_KEYS, "catalog_sha256"):
        return False
    records = value.get("records")
    if not isinstance(records, list) or any(not prepared_record_valid_v2(record, snapshot) for record in records):
        return False
    record_hashes = [record["record_sha256"] for record in records]
    return bool(
        value["catalog_version"] == PREPARED_CATALOG_VERSION_V2
        and value["backend_instance_sha256"] == snapshot["backend_instance_sha256"]
        and value["backend_snapshot_sha256"] == snapshot["snapshot_sha256"]
        and value["registry_path_binding_sha256"] == snapshot["registry_path_binding_sha256"]
        and value["lock_namespace_sha256"] == snapshot["lock_namespace_sha256"]
        and value["generation"] == snapshot["generation"]
        and value["record_count"] == len(records)
        and value["prepared_count"] == len(records)
        and record_hashes == sorted(record_hashes) and len(record_hashes) == len(set(record_hashes))
        and value["synthetic_only"] is True and value["durable"] is False
        and value["production_evidence"] is False
    )


def transaction_request_valid_v2(value: Any, snapshot: Mapping[str, Any]) -> bool:
    return bool(
        _exact_hash(value, _TRANSACTION_REQUEST_KEYS, "request_binding_sha256")
        and value["request_version"] == TRANSACTION_REQUEST_VERSION_V2
        and all(_sha(value[key]) for key in _TRANSACTION_REQUEST_KEYS if key.endswith("_sha256"))
        and value["backend_instance_sha256"] == snapshot["backend_instance_sha256"]
        and value["backend_snapshot_sha256"] == snapshot["snapshot_sha256"]
        and value["registry_path_binding_sha256"] == snapshot["registry_path_binding_sha256"]
        and value["lock_namespace_sha256"] == snapshot["lock_namespace_sha256"]
        and isinstance(value["expected_generation"], int) and value["expected_generation"] >= 0
        and isinstance(value["deadline_epoch"], int)
        and isinstance(value["candidate_raw_document_utf8"], str)
        and value["candidate_raw_document_sha256"] == raw_utf8_sha256_v2(value["candidate_raw_document_utf8"])
        and value["synthetic_only"] is True and value["production_authority"] is False
    )


def transaction_result_valid_v2(value: Any, request: Mapping[str, Any]) -> bool:
    if not _exact_hash(value, _TRANSACTION_RESULT_KEYS, "result_sha256"):
        return False
    try:
        state = value["terminal_state"]
        generation_before = value["generation_before"]
        generation_after = value["generation_after"]
        state_postconditions_valid = (
            state in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
            and generation_after == generation_before + 1
            and value["postconditions_verified"] is True
            and value["recovery_required"] is False
        ) or (
            state == "AMBIGUOUS"
            and generation_after >= generation_before
            and value["postconditions_verified"] is False
            and value["recovery_required"] is True
        )
        return bool(
            value["result_version"] == TRANSACTION_RESULT_VERSION_V2
            and all(
                _sha(value[key])
                for key in (
                    "request_binding_sha256",
                    "request_sha256",
                    "transaction_sha256",
                    "backend_instance_sha256",
                    "backend_snapshot_sha256",
                    "prepared_record_sha256",
                    "terminal_record_sha256",
                )
            )
            and value["request_binding_sha256"]
            == request["request_binding_sha256"]
            and value["request_sha256"] == request["request_sha256"]
            and value["transaction_sha256"] == request["transaction_sha256"]
            and value["backend_instance_sha256"]
            == request["backend_instance_sha256"]
            and value["backend_snapshot_sha256"]
            == request["backend_snapshot_sha256"]
            and type(generation_before) is int
            and generation_before == request["expected_generation"]
            and type(generation_after) is int
            and generation_after >= 0
            and state_postconditions_valid
            and value["deadline_epoch"] == request["deadline_epoch"]
            and value["deadline_observed"] is True
            and value["synthetic_only"] is True
            and value["durable"] is False
            and value["production_evidence"] is False
            and type(value["write_executed"]) is bool
            and type(value["registry_write"]) is bool
            and (value["write_executed"] or not value["registry_write"])
        )
    except Exception:
        return False


def recovery_request_valid_v2(value: Any, record: Mapping[str, Any], batch: Mapping[str, Any]) -> bool:
    return bool(
        _exact_hash(value, _RECOVERY_REQUEST_KEYS, "request_sha256")
        and value["request_version"] == RECOVERY_REQUEST_VERSION_V2
        and all(_sha(value[key]) for key in _RECOVERY_REQUEST_KEYS if key.endswith("_sha256"))
        and value["batch_epoch"] == batch["batch_epoch"]
        and value["batch_plan_sha256"] == batch["batch_plan_sha256"]
        and value["catalog_sha256"] == batch["catalog_sha256"]
        and value["prepared_record_sha256"] == record["record_sha256"]
        and value["wal_prepared_record_sha256"] == record["wal_prepared_record_sha256"]
        and value["original_request_sha256"] == record["request_sha256"]
        and value["original_invocation_command_sha256"] == record["original_invocation_command_sha256"]
        and value["original_authorization_receipt_sha256"] == record["authorization_receipt_sha256"]
        and value["transaction_sha256"] == record["transaction_sha256"]
        and value["backend_instance_sha256"] == record["backend_instance_sha256"]
        and value["registry_path_binding_sha256"] == record["registry_path_binding_sha256"]
        and value["lock_namespace_sha256"] == record["lock_namespace_sha256"]
        and value["previous_maintenance_epoch"] == record["previous_maintenance_epoch"]
        and value["fresh_maintenance_epoch"] != record["previous_maintenance_epoch"]
        and value["checkpoint_index"] == batch["next_index"]
        and value["synthetic_only"] is True and value["production_authority"] is False
    )


def recovery_result_valid_v2(value: Any, request: Mapping[str, Any], checkpoint_index: int) -> bool:
    return bool(
        _exact_hash(value, _RECOVERY_RESULT_KEYS, "result_sha256")
        and value["result_version"] == RECOVERY_RESULT_VERSION_V2
        and value["recovery_request_sha256"] == request["request_sha256"]
        and value["batch_epoch"] == request["batch_epoch"]
        and value["batch_plan_sha256"] == request["batch_plan_sha256"]
        and value["catalog_sha256"] == request["catalog_sha256"]
        and value["prepared_record_sha256"] == request["prepared_record_sha256"]
        and value["wal_prepared_record_sha256"] == request["wal_prepared_record_sha256"]
        and value["transaction_sha256"] == request["transaction_sha256"]
        and value["backend_instance_sha256"] == request["backend_instance_sha256"]
        and value["terminal_state"] in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
        and value["checkpoint_index"] == checkpoint_index
        and value["deadline_epoch"] == request["deadline_epoch"]
        and value["deadline_observed"] is True and value["postconditions_verified"] is True
        and value["synthetic_only"] is True and value["durable"] is False
        and value["production_evidence"] is False
        and isinstance(value["write_executed"], bool)
        and isinstance(value["registry_write"], bool)
    )


def build_resumable_recovery_batch_offline_v2(
    snapshot: Mapping[str, Any], catalog: Mapping[str, Any], *, batch_epoch: str, deadline_epoch: int
) -> dict[str, Any]:
    if not backend_snapshot_valid_v2(snapshot) or not prepared_catalog_valid_v2(catalog, snapshot):
        raise ValueError("BACKEND_SNAPSHOT_OR_PREPARED_CATALOG_INVALID")
    if not _sha(batch_epoch) or not isinstance(deadline_epoch, int):
        raise ValueError("RECOVERY_BATCH_EPOCH_OR_DEADLINE_INVALID")
    batch = {
        "batch_version": RECOVERY_BATCH_VERSION_V2,
        "batch_epoch": batch_epoch,
        "backend_instance_sha256": snapshot["backend_instance_sha256"],
        "backend_snapshot_sha256": snapshot["snapshot_sha256"],
        "catalog_sha256": catalog["catalog_sha256"],
        "catalog_generation": catalog["generation"],
        "item_record_sha256s": [record["record_sha256"] for record in catalog["records"]],
        "item_count": catalog["prepared_count"],
        "next_index": 0,
        "terminal_result_sha256s": [],
        "complete": catalog["prepared_count"] == 0,
        "deadline_epoch": deadline_epoch,
        "synthetic_only": True,
        "durable": False,
        "production_authority": False,
    }
    batch["batch_plan_sha256"] = _hash_without(batch, "batch_plan_sha256")
    return batch


def recovery_batch_valid_v2(value: Any) -> bool:
    if not _exact_hash(value, _BATCH_KEYS, "batch_plan_sha256"):
        return False
    items = value.get("item_record_sha256s")
    results = value.get("terminal_result_sha256s")
    return bool(
        value["batch_version"] == RECOVERY_BATCH_VERSION_V2
        and all(_sha(value[key]) for key in (
            "batch_epoch", "backend_instance_sha256", "backend_snapshot_sha256", "catalog_sha256"
        ))
        and isinstance(items, list) and all(_sha(item) for item in items)
        and isinstance(results, list) and all(_sha(item) for item in results)
        and value["item_count"] == len(items)
        and value["next_index"] == len(results)
        and 0 <= value["next_index"] <= value["item_count"]
        and value["complete"] is (value["next_index"] == value["item_count"])
        and isinstance(value["deadline_epoch"], int)
        and value["synthetic_only"] is True and value["durable"] is False
        and value["production_authority"] is False
    )


def advance_recovery_batch_offline_v2(batch: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    if not recovery_batch_valid_v2(batch) or batch["complete"]:
        raise ValueError("RECOVERY_BATCH_INVALID_OR_COMPLETE")
    index = batch["next_index"]
    result_valid = bool(
        _exact_hash(result, _RECOVERY_RESULT_KEYS, "result_sha256")
        and result["result_version"] == RECOVERY_RESULT_VERSION_V2
        and result["batch_epoch"] == batch["batch_epoch"]
        and result["batch_plan_sha256"] == batch["batch_plan_sha256"]
        and result["catalog_sha256"] == batch["catalog_sha256"]
        and result["backend_instance_sha256"] == batch["backend_instance_sha256"]
        and result["checkpoint_index"] == index
        and result["deadline_epoch"] == batch["deadline_epoch"]
        and result["terminal_state"] in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
        and result["deadline_observed"] is True
        and result["postconditions_verified"] is True
        and result["synthetic_only"] is True
        and result["durable"] is False
        and result["production_evidence"] is False
        and isinstance(result["write_executed"], bool)
        and isinstance(result["registry_write"], bool)
    )
    if not result_valid:
        raise ValueError("RECOVERY_RESULT_INVALID")
    if result.get("prepared_record_sha256") != batch["item_record_sha256s"][index]:
        raise ValueError("RECOVERY_RESULT_OUT_OF_ORDER")
    advanced = dict(batch)
    advanced["terminal_result_sha256s"] = [*batch["terminal_result_sha256s"], result["result_sha256"]]
    advanced["next_index"] = index + 1
    advanced["complete"] = advanced["next_index"] == advanced["item_count"]
    advanced["batch_plan_sha256"] = _hash_without(advanced, "batch_plan_sha256")
    return advanced


class DurableRawTransactionBackendV2(Protocol):
    """Evidence-bearing interface only; it confers no execution authority."""

    def snapshot_offline(self) -> Mapping[str, Any]: ...
    def capability_evidence_offline(self) -> Sequence[Mapping[str, Any]]: ...
    def list_prepared_transactions_offline(self) -> Mapping[str, Any]: ...
    def apply_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...
    def reconcile_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class DurableRawTransactionBackendConformanceConfigV2:
    enabled: bool = False
    scope_attestation: str | None = None


class DurableRawTransactionBackendConformanceV2:
    def __init__(self, config: DurableRawTransactionBackendConformanceConfigV2 | None = None) -> None:
        self._config = config or DurableRawTransactionBackendConformanceConfigV2()

    def audit_offline(self, backend: DurableRawTransactionBackendV2) -> dict[str, Any]:
        reasons: list[str] = []
        if not self._config.enabled:
            reasons.append("DURABLE_BACKEND_CONFORMANCE_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2:
            reasons.append("DURABLE_BACKEND_CONFORMANCE_SCOPE_INVALID")
        required_methods = (
            "snapshot_offline", "capability_evidence_offline",
            "list_prepared_transactions_offline", "apply_attested_transaction_offline",
            "reconcile_attested_transaction_offline",
        )
        if any(not callable(getattr(backend, name, None)) for name in required_methods):
            reasons.append("DURABLE_BACKEND_V2_INTERFACE_INCOMPLETE")
        if reasons:
            return self._failed(reasons)
        try:
            snapshot = dict(backend.snapshot_offline())
            evidence = [dict(item) for item in backend.capability_evidence_offline()]
            catalog = dict(backend.list_prepared_transactions_offline())
        except Exception:
            return self._failed(["DURABLE_BACKEND_V2_EVIDENCE_COLLECTION_FAILED"])
        if not backend_snapshot_valid_v2(snapshot):
            reasons.append("DURABLE_BACKEND_V2_SNAPSHOT_INVALID")
        if len(evidence) != len(REQUIRED_CAPABILITIES_V2):
            reasons.append("DURABLE_BACKEND_V2_CAPABILITY_EVIDENCE_COUNT_INVALID")
        elif not backend_snapshot_valid_v2(snapshot) or any(not capability_evidence_valid_v2(item, snapshot) for item in evidence):
            reasons.append("DURABLE_BACKEND_V2_CAPABILITY_EVIDENCE_INVALID")
        elif sorted(item["capability"] for item in evidence) != sorted(REQUIRED_CAPABILITIES_V2):
            reasons.append("DURABLE_BACKEND_V2_CAPABILITY_SET_INVALID")
        if not backend_snapshot_valid_v2(snapshot) or not prepared_catalog_valid_v2(catalog, snapshot):
            reasons.append("DURABLE_BACKEND_V2_PREPARED_CATALOG_INVALID")
        if reasons:
            return self._failed(reasons)
        report = {
            "ok": True,
            "status": "DURABLE_BACKEND_V2_CONFORMS_OFFLINE_SYNTHETIC_ONLY",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_CONTRACT_V2_VERSION,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "capability_evidence_sha256s": [item["evidence_sha256"] for item in evidence],
            "prepared_catalog_sha256": catalog["catalog_sha256"],
            "prepared_count": catalog["prepared_count"],
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "filesystem_accessed": snapshot["filesystem_accessed"],
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "reasons": [],
        }
        report["report_sha256"] = stable_sha256_v2(report)
        return report

    @staticmethod
    def _failed(reasons: Sequence[str]) -> dict[str, Any]:
        result = {
            "ok": False,
            "status": "DURABLE_BACKEND_V2_CONFORMANCE_FAILED_CLOSED",
            "reasons": list(dict.fromkeys(reasons)),
            "synthetic_only": True,
            "durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
        }
        result["report_sha256"] = stable_sha256_v2(result)
        return result


__all__ = [
    "BACKEND_SNAPSHOT_VERSION_V2", "CAPABILITY_EVIDENCE_VERSION_V2",
    "DurableRawTransactionBackendConformanceConfigV2",
    "DurableRawTransactionBackendConformanceV2", "DurableRawTransactionBackendV2",
    "OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2",
    "PREPARED_CATALOG_VERSION_V2", "PREPARED_RECORD_VERSION_V2",
    "RECOVERY_BATCH_VERSION_V2", "RECOVERY_REQUEST_VERSION_V2", "RECOVERY_RESULT_VERSION_V2",
    "REQUIRED_CAPABILITIES_V2", "TRANSACTION_REQUEST_VERSION_V2", "TRANSACTION_RESULT_VERSION_V2",
    "advance_recovery_batch_offline_v2", "backend_snapshot_valid_v2",
    "build_resumable_recovery_batch_offline_v2", "capability_evidence_valid_v2",
    "prepared_catalog_valid_v2", "prepared_record_valid_v2", "recovery_batch_valid_v2",
    "recovery_request_valid_v2", "recovery_result_valid_v2", "raw_utf8_sha256_v2", "stable_sha256_v2",
    "transaction_request_valid_v2", "transaction_result_valid_v2",
]
