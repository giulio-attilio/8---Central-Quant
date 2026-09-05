"""Dormant physical-storage boundary contract for raw CLOSED repair V2.

The contract describes the capabilities that a future physical adapter would
have to provide.  It validates only synthetic, in-memory rehearsal evidence;
it exposes no apply function and permanently denies persistence, runtime
integration and production readiness.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_rehearsal_offline_v2 as rehearsal


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PHYSICAL-STORAGE-BOUNDARY-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_RAW_PHYSICAL_STORAGE_BOUNDARY_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_RAW_PHYSICAL_STORAGE_BOUNDARY_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_SEQUENCE = (
    "SYNTHETIC_LOCK_ACQUIRED",
    "SYNTHETIC_WRITERS_QUIESCED",
    "SYNTHETIC_EXACT_SOURCE_READ",
    "SYNTHETIC_IMMUTABLE_BACKUP_REHEARSED",
    "SYNTHETIC_CAS_VERIFIED",
    "SYNTHETIC_WAL_PREPARED_REHEARSED",
    "SYNTHETIC_LOCK_RELEASED",
)
_MANDATORY_CAPABILITIES = (
    "exact_raw_loader",
    "shared_interprocess_lock",
    "writer_quiescence",
    "immutable_versioned_backup",
    "generation_and_hash_cas",
    "append_only_wal",
    "file_and_directory_fsync",
    "atomic_same_directory_replace",
    "rollback_recovery",
)
_PRODUCTION_BLOCKERS = (
    "BOUNDARY_IS_CONTRACT_ONLY",
    "PHYSICAL_APPLY_ENTRYPOINT_ABSENT",
    "REAL_STORAGE_NOT_ACCESSED",
    "REAL_SHARED_LOCK_NOT_ACQUIRED",
    "REAL_WRITERS_NOT_QUIESCED",
    "REAL_BACKUP_NOT_CREATED",
    "REAL_CAS_NOT_EXECUTED",
    "REAL_WAL_NOT_WRITTEN",
    "REAL_FSYNC_NOT_EXECUTED",
    "SEPARATE_PRODUCTION_APPLY_AUTHORIZATION_REQUIRED",
)


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


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def raw_physical_storage_boundary_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def raw_physical_storage_boundary_rehearsal_sha256_v1(
    receipt: Mapping[str, Any],
) -> str:
    if not isinstance(receipt, Mapping):
        raise TypeError("receipt must be a mapping")
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != "rehearsal_sha256"}
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "boundary_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "physical_apply_entrypoint_present": False,
        "status": "RAW_PHYSICAL_STORAGE_BOUNDARY_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_CONTRACT_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "read_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "persistence_allowed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "boundary_receipt": None,
    }


def _check_transaction(
    transaction: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> None:
    supplied_sha = _valid_sha256(transaction.get("transaction_sha256"))
    checks["transaction_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            rehearsal.raw_repair_rehearsal_transaction_sha256_v2(transaction),
        )
        and transaction.get("state") == "REHEARSED_NOT_APPLIED"
        and transaction.get("dormant") is True
        and transaction.get("offline_only") is True
        and transaction.get("synthetic_only") is True
        and transaction.get("translation_allowed") is False
        and transaction.get("apply_allowed") is False
        and transaction.get("write_executed") is False
        and transaction.get("registry_write") is False
        and transaction.get("runtime_integrated") is False
        and transaction.get("persistence_allowed") is False
    )
    if not checks["transaction_valid"]:
        reasons.append("RAW_BOUNDARY_TRANSACTION_INVALID")


def _check_readiness(
    readiness_result: Mapping[str, Any],
    transaction: Mapping[str, Any],
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    gate = readiness_result.get("gate_receipt")
    gate_sha = _valid_sha256(gate.get("gate_receipt_sha256")) if isinstance(gate, Mapping) else ""
    expected_gate_sha = (
        _stable_sha256({key: value for key, value in gate.items() if key != "gate_receipt_sha256"})
        if isinstance(gate, Mapping)
        else ""
    )
    checks["readiness_gate_valid"] = bool(
        readiness_result.get("ok") is True
        and readiness_result.get("offline_evidence_valid") is True
        and readiness_result.get("production_ready") is False
        and readiness_result.get("translation_allowed") is False
        and readiness_result.get("apply_allowed") is False
        and readiness_result.get("write_executed") is False
        and readiness_result.get("registry_write") is False
        and isinstance(gate, Mapping)
        and gate_sha
        and hmac.compare_digest(gate_sha, expected_gate_sha)
        and gate.get("transaction_sha256") == transaction.get("transaction_sha256")
        and gate.get("all_offline_checks_passed") is True
        and gate.get("production_ready") is False
        and gate.get("translation_allowed") is False
        and gate.get("apply_allowed") is False
        and gate.get("production_blockers")
    )
    if not checks["readiness_gate_valid"]:
        reasons.append("RAW_BOUNDARY_READINESS_GATE_INVALID")
    return gate_sha


def _check_spec(
    spec: Mapping[str, Any],
    transaction: Mapping[str, Any],
    gate_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, raw_physical_storage_boundary_spec_sha256_v1(spec)
        )
    )
    capabilities = spec.get("capabilities")
    checks["mandatory_capabilities_complete"] = bool(
        isinstance(capabilities, Mapping)
        and tuple(sorted(capabilities)) == tuple(sorted(_MANDATORY_CAPABILITIES))
        and all(capabilities.get(name) is True for name in _MANDATORY_CAPABILITIES)
    )
    shared_lock = spec.get("shared_lock_contract")
    checks["shared_lock_contract_valid"] = bool(
        isinstance(shared_lock, Mapping)
        and shared_lock.get("all_registry_writers_same_namespace") is True
        and shared_lock.get("exclusive") is True
        and shared_lock.get("interprocess") is True
        and shared_lock.get("bounded_timeout") is True
        and shared_lock.get("fail_closed_on_timeout") is True
    )
    quiescence = spec.get("writer_quiescence_contract")
    checks["writer_quiescence_contract_valid"] = bool(
        isinstance(quiescence, Mapping)
        and quiescence.get("complete_inventory_required") is True
        and quiescence.get("lease_epoch_required") is True
        and quiescence.get("all_writers_ack_required") is True
        and quiescence.get("zero_inflight_mutations_required") is True
        and quiescence.get("fail_closed_on_unknown_writer") is True
    )
    backup = spec.get("backup_contract")
    checks["backup_contract_valid"] = bool(
        isinstance(backup, Mapping)
        and backup.get("content_addressed") is True
        and backup.get("immutable") is True
        and backup.get("versioned") is True
        and backup.get("transaction_bound") is True
        and backup.get("restore_digest_required") is True
        and backup.get("durability_confirmation_required") is True
    )
    cas = spec.get("compare_and_swap_contract")
    checks["compare_and_swap_contract_valid"] = bool(
        isinstance(cas, Mapping)
        and cas.get("expected_raw_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and cas.get("expected_snapshot_envelope_sha256")
        == transaction.get("source_snapshot_envelope_sha256")
        and cas.get("generation_token_required") is True
        and cas.get("verified_under_shared_lock") is True
        and cas.get("fail_closed_on_mismatch") is True
    )
    journal = spec.get("journal_contract")
    checks["journal_contract_valid"] = bool(
        isinstance(journal, Mapping)
        and journal.get("append_only") is True
        and journal.get("transaction_sha256") == transaction.get("transaction_sha256")
        and journal.get("idempotency_key") == transaction.get("idempotency_key")
        and journal.get("prepared_before_candidate") is True
        and journal.get("commit_after_durable_replace") is True
        and journal.get("recovery_state_required") is True
    )
    durability = spec.get("durability_contract")
    checks["durability_contract_valid"] = bool(
        isinstance(durability, Mapping)
        and durability.get("same_directory_temp") is True
        and durability.get("temp_file_fsync") is True
        and durability.get("atomic_replace") is True
        and durability.get("parent_directory_fsync") is True
        and durability.get("journal_fsync") is True
    )
    recovery = spec.get("recovery_contract")
    checks["recovery_contract_valid"] = bool(
        isinstance(recovery, Mapping)
        and recovery.get("rollback_preimage_required") is True
        and recovery.get("partial_state_detection_required") is True
        and recovery.get("candidate_already_present_detection_required") is True
        and recovery.get("manual_recovery_on_ambiguity") is True
    )
    safety = spec.get("safety_envelope")
    checks["spec_safety_envelope_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("transaction_sha256") == transaction.get("transaction_sha256")
        and spec.get("readiness_gate_receipt_sha256") == gate_sha
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("apply_entrypoint_present") is False
        and safety.get("real_storage_accessed") is False
        and safety.get("real_lock_acquired") is False
        and safety.get("real_writers_quiesced") is False
        and safety.get("real_backup_created") is False
        and safety.get("real_cas_executed") is False
        and safety.get("real_journal_written") is False
        and safety.get("real_fsync_executed") is False
        and safety.get("production_apply_authorized") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "RAW_BOUNDARY_SPEC_SHA256_INVALID"),
        ("mandatory_capabilities_complete", "RAW_BOUNDARY_CAPABILITIES_INCOMPLETE"),
        ("shared_lock_contract_valid", "RAW_BOUNDARY_SHARED_LOCK_CONTRACT_INVALID"),
        ("writer_quiescence_contract_valid", "RAW_BOUNDARY_QUIESCENCE_CONTRACT_INVALID"),
        ("backup_contract_valid", "RAW_BOUNDARY_BACKUP_CONTRACT_INVALID"),
        ("compare_and_swap_contract_valid", "RAW_BOUNDARY_CAS_CONTRACT_INVALID"),
        ("journal_contract_valid", "RAW_BOUNDARY_JOURNAL_CONTRACT_INVALID"),
        ("durability_contract_valid", "RAW_BOUNDARY_DURABILITY_CONTRACT_INVALID"),
        ("recovery_contract_valid", "RAW_BOUNDARY_RECOVERY_CONTRACT_INVALID"),
        ("spec_safety_envelope_valid", "RAW_BOUNDARY_SPEC_SAFETY_ENVELOPE_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def _check_rehearsal(
    receipt: Mapping[str, Any],
    transaction: Mapping[str, Any],
    gate_sha: str,
    spec_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(receipt.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            raw_physical_storage_boundary_rehearsal_sha256_v1(receipt),
        )
    )
    source_sha = transaction.get("source_raw_registry_document_sha256")
    expected_content_address = "sha256:" + _stable_sha256(
        {
            "source_raw_registry_document_sha256": source_sha,
            "transaction_sha256": transaction.get("transaction_sha256"),
        }
    )
    backup = receipt.get("backup")
    cas = receipt.get("compare_and_swap")
    journal = receipt.get("journal")
    durability = receipt.get("durability")
    checks["rehearsal_chain_valid"] = bool(
        receipt.get("rehearsal_version") == _REHEARSAL_VERSION
        and receipt.get("transaction_sha256") == transaction.get("transaction_sha256")
        and receipt.get("readiness_gate_receipt_sha256") == gate_sha
        and receipt.get("boundary_spec_sha256") == spec_sha
        and receipt.get("source_raw_registry_document_sha256") == source_sha
        and tuple(receipt.get("event_sequence") or ()) == _REQUIRED_SEQUENCE
    )
    checks["rehearsal_lock_and_quiescence_valid"] = bool(
        receipt.get("synthetic_lock_exclusive") is True
        and receipt.get("synthetic_all_writers_quiesced") is True
        and receipt.get("synthetic_unknown_writer_count") == 0
        and receipt.get("synthetic_inflight_mutation_count") == 0
    )
    checks["rehearsal_backup_valid"] = bool(
        isinstance(backup, Mapping)
        and backup.get("content_address") == expected_content_address
        and backup.get("raw_registry_document_sha256") == source_sha
        and backup.get("transaction_sha256") == transaction.get("transaction_sha256")
        and backup.get("immutable") is True
        and backup.get("restore_digest_verified") is True
        and backup.get("synthetic_memory_only") is True
    )
    checks["rehearsal_cas_valid"] = bool(
        isinstance(cas, Mapping)
        and cas.get("source_hash_matched") is True
        and cas.get("generation_matched") is True
        and cas.get("verified_under_synthetic_shared_lock") is True
        and cas.get("fail_closed_on_mismatch") is True
    )
    checks["rehearsal_journal_valid"] = bool(
        isinstance(journal, Mapping)
        and journal.get("append_only") is True
        and journal.get("prepared_rehearsal_present") is True
        and journal.get("candidate_write_event_present") is False
        and journal.get("commit_event_present") is False
        and journal.get("synthetic_memory_only") is True
    )
    checks["rehearsal_durability_plan_valid"] = bool(
        isinstance(durability, Mapping)
        and durability.get("requirements_modeled") is True
        and durability.get("filesystem_touched") is False
        and durability.get("temp_file_fsync_executed") is False
        and durability.get("atomic_replace_executed") is False
        and durability.get("parent_directory_fsync_executed") is False
        and durability.get("journal_fsync_executed") is False
    )
    checks["rehearsal_safety_envelope_valid"] = bool(
        receipt.get("synthetic_memory_mutation_executed") is True
        and receipt.get("source_document_preserved") is True
        and receipt.get("candidate_persisted") is False
        and receipt.get("apply_entrypoint_present") is False
        and receipt.get("write_executed") is False
        and receipt.get("registry_write") is False
        and receipt.get("runtime_integrated") is False
        and receipt.get("real_storage_accessed") is False
        and receipt.get("broker_called") is False
        and receipt.get("no_order_sent") is True
    )
    for check, reason in (
        ("rehearsal_sha256_valid", "RAW_BOUNDARY_REHEARSAL_SHA256_INVALID"),
        ("rehearsal_chain_valid", "RAW_BOUNDARY_REHEARSAL_CHAIN_INVALID"),
        ("rehearsal_lock_and_quiescence_valid", "RAW_BOUNDARY_REHEARSAL_LOCK_INVALID"),
        ("rehearsal_backup_valid", "RAW_BOUNDARY_REHEARSAL_BACKUP_INVALID"),
        ("rehearsal_cas_valid", "RAW_BOUNDARY_REHEARSAL_CAS_INVALID"),
        ("rehearsal_journal_valid", "RAW_BOUNDARY_REHEARSAL_JOURNAL_INVALID"),
        ("rehearsal_durability_plan_valid", "RAW_BOUNDARY_REHEARSAL_DURABILITY_INVALID"),
        ("rehearsal_safety_envelope_valid", "RAW_BOUNDARY_REHEARSAL_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def evaluate_closed_identity_conflict_raw_physical_storage_boundary_offline_v1(
    transaction: Mapping[str, Any],
    readiness_result: Mapping[str, Any],
    boundary_spec: Mapping[str, Any],
    rehearsal_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the dormant boundary while permanently denying physical apply."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (transaction, readiness_result, boundary_spec, rehearsal_receipt)
    ):
        reasons.append("RAW_BOUNDARY_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        transaction_copy = _canonical_copy(transaction)
        readiness_copy = _canonical_copy(readiness_result)
        spec_copy = _canonical_copy(boundary_spec)
        rehearsal_copy = _canonical_copy(rehearsal_receipt)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_BOUNDARY_INPUT_NOT_CANONICALIZABLE")
        return base

    _check_transaction(transaction_copy, reasons, checks)
    gate_sha = _check_readiness(readiness_copy, transaction_copy, reasons, checks)
    spec_sha = _check_spec(spec_copy, transaction_copy, gate_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(
        rehearsal_copy,
        transaction_copy,
        gate_sha,
        spec_sha,
        reasons,
        checks,
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_RAW_BOUNDARY_CHECKS_FAILED")
        return base

    boundary_receipt = {
        "transaction_sha256": transaction_copy["transaction_sha256"],
        "readiness_gate_receipt_sha256": gate_sha,
        "boundary_spec_sha256": spec_sha,
        "rehearsal_sha256": rehearsal_sha,
        "mandatory_capabilities": list(_MANDATORY_CAPABILITIES),
        "all_offline_checks_passed": True,
        "physical_apply_entrypoint_present": False,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    boundary_receipt["boundary_receipt_sha256"] = _stable_sha256(boundary_receipt)
    base.update(
        {
            "ok": True,
            "boundary_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "production_ready": False,
            "translation_allowed": False,
            "apply_allowed": False,
            "physical_apply_entrypoint_present": False,
            "status": "RAW_PHYSICAL_STORAGE_BOUNDARY_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "boundary_receipt": boundary_receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_CONTRACT_V1_VERSION",
    "evaluate_closed_identity_conflict_raw_physical_storage_boundary_offline_v1",
    "raw_physical_storage_boundary_rehearsal_sha256_v1",
    "raw_physical_storage_boundary_spec_sha256_v1",
]
