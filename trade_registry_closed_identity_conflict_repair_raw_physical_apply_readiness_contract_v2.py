"""Dormant physical-apply readiness V2 for raw CLOSED repair rehearsals.

This gate validates cryptographically linked synthetic transaction evidence.
Passing means only that the offline evidence is internally coherent.  It never
means production readiness and can never authorize translation, persistence,
runtime integration, apply or trading.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_composition_contract_v2 as composition
import trade_registry_closed_identity_conflict_repair_raw_path_binding_contract_v1 as raw_binding
import trade_registry_closed_identity_conflict_repair_raw_transaction_rehearsal_offline_v2 as rehearsal


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_CONTRACT_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PHYSICAL-APPLY-READINESS-CONTRACT-V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTESTATION_VERSION = "SYNTHETIC_RAW_PHYSICAL_APPLY_READINESS_ATTESTATIONS_V2"
_AUTHORITY = "SYNTHETIC_RAW_REGISTRY_DOCUMENT_V2"
_AUTHORIZATION_SCOPE = "RAW_PHYSICAL_APPLY_READINESS_REVIEW_ONLY_V2"
_OPERATION = "SYNTHETIC_RAW_CLOSED_IDENTITY_CONFLICT_REPAIR_REHEARSAL_V2"
_PRODUCTION_BLOCKERS = (
    "PHYSICAL_RAW_APPLIER_DOES_NOT_EXIST",
    "REAL_STORAGE_AUTHORITY_NOT_OBSERVED",
    "REAL_INTERPROCESS_LOCK_NOT_ACQUIRED",
    "REAL_WRITERS_NOT_QUIESCED",
    "DURABLE_PRODUCTION_BACKUP_NOT_CREATED",
    "REAL_COMPARE_AND_SWAP_NOT_ACQUIRED",
    "PRODUCTION_EVIDENCE_NOT_REVALIDATED",
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


def raw_physical_apply_readiness_attestations_sha256_v2(
    attestations: Mapping[str, Any],
) -> str:
    if not isinstance(attestations, Mapping):
        raise TypeError("attestations must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in attestations.items()
            if key != "attestations_sha256"
        }
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "readiness_verification_allowed": False,
        "offline_evidence_valid": False,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "status": "RAW_CLOSED_IDENTITY_CONFLICT_PHYSICAL_APPLY_READINESS_V2_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_CONTRACT_V2_VERSION,
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
        "gate_receipt": None,
    }


def _check_transaction(
    transaction: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> None:
    supplied_sha = _valid_sha256(transaction.get("transaction_sha256"))
    checks["transaction_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            rehearsal.raw_repair_rehearsal_transaction_sha256_v2(transaction),
        )
    )
    checks["transaction_safety_envelope_valid"] = bool(
        transaction.get("operation") == _OPERATION
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
        and transaction.get("broker_called") is False
        and transaction.get("no_order_sent") is True
    )
    request_binding = {
        "operation": _OPERATION,
        "upstream_plan_sha256": transaction.get("upstream_plan_sha256"),
        "binding_plan_sha256": transaction.get("binding_plan_sha256"),
        "raw_path_receipt_sha256": transaction.get("raw_path_receipt_sha256"),
        "composition_preview_receipt_sha256": transaction.get(
            "composition_preview_receipt_sha256"
        ),
        "source_raw_registry_document_sha256": transaction.get(
            "source_raw_registry_document_sha256"
        ),
        "candidate_raw_registry_document_sha256": transaction.get(
            "candidate_raw_registry_document_sha256"
        ),
        "candidate_snapshot_sha256": transaction.get("candidate_snapshot_sha256"),
    }
    request_digest = _stable_sha256(request_binding)
    idempotency_key = _stable_sha256(
        {"operation": _OPERATION, "request_digest": request_digest}
    )
    checks["transaction_idempotency_valid"] = bool(
        transaction.get("request_digest") == request_digest
        and transaction.get("idempotency_key") == idempotency_key
    )
    compare_and_swap = transaction.get("compare_and_swap")
    checks["transaction_compare_and_swap_dormant"] = bool(
        isinstance(compare_and_swap, Mapping)
        and compare_and_swap.get("required") is True
        and compare_and_swap.get("fail_closed_on_mismatch") is True
        and compare_and_swap.get("source_snapshot_envelope_sha256")
        == transaction.get("source_snapshot_envelope_sha256")
        and compare_and_swap.get("source_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
    )
    for check, reason in (
        ("transaction_sha256_valid", "RAW_TRANSACTION_SHA256_INVALID"),
        (
            "transaction_safety_envelope_valid",
            "RAW_TRANSACTION_SAFETY_ENVELOPE_INVALID",
        ),
        ("transaction_idempotency_valid", "RAW_TRANSACTION_IDEMPOTENCY_INVALID"),
        (
            "transaction_compare_and_swap_dormant",
            "RAW_TRANSACTION_COMPARE_AND_SWAP_INVALID",
        ),
    ):
        if not checks[check]:
            reasons.append(reason)


def _check_composition_receipt(
    receipt: Mapping[str, Any],
    transaction: Mapping[str, Any],
    reasons: list[str],
    checks: dict[str, bool],
) -> None:
    supplied_sha = _valid_sha256(receipt.get("receipt_sha256"))
    checks["composition_receipt_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            composition.raw_composition_preview_receipt_sha256_v2(receipt),
        )
    )
    preservation = receipt.get("preservation_proof")
    checks["composition_receipt_chain_valid"] = bool(
        supplied_sha == transaction.get("composition_preview_receipt_sha256")
        and receipt.get("upstream_plan_sha256")
        == transaction.get("upstream_plan_sha256")
        and receipt.get("binding_plan_sha256")
        == transaction.get("binding_plan_sha256")
        and receipt.get("raw_path_receipt_sha256")
        == transaction.get("raw_path_receipt_sha256")
        and receipt.get("source_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and receipt.get("candidate_raw_registry_document_sha256")
        == transaction.get("candidate_raw_registry_document_sha256")
        and receipt.get("proposal_count") == transaction.get("proposal_count")
        and receipt.get("changed_path_count")
        == transaction.get("changed_path_count")
        and receipt.get("round_trip_verified") is True
        and receipt.get("translation_allowed") is False
        and receipt.get("apply_allowed") is False
        and isinstance(preservation, Mapping)
        and preservation
        and all(value is True for value in preservation.values())
    )
    if not checks["composition_receipt_sha256_valid"]:
        reasons.append("RAW_COMPOSITION_RECEIPT_SHA256_INVALID")
    if not checks["composition_receipt_chain_valid"]:
        reasons.append("RAW_COMPOSITION_RECEIPT_CHAIN_INVALID")


def _check_candidate_backup_rollback(
    transaction: Mapping[str, Any],
    reasons: list[str],
    checks: dict[str, bool],
) -> None:
    candidate = transaction.get("candidate_snapshot")
    backup = transaction.get("backup_envelope")
    rollback = transaction.get("rollback_envelope")
    if not all(isinstance(value, Mapping) for value in (candidate, backup, rollback)):
        reasons.append("RAW_TRANSACTION_RECOVERY_ENVELOPES_REQUIRED")
        checks["candidate_snapshot_valid"] = False
        checks["backup_preimage_valid"] = False
        checks["rollback_preimage_valid"] = False
        checks["original_and_candidate_states_valid"] = False
        return
    candidate_document = candidate.get("raw_registry_document")
    backup_snapshot = backup.get("snapshot")
    backup_document = (
        backup_snapshot.get("raw_registry_document")
        if isinstance(backup_snapshot, Mapping)
        else None
    )
    rollback_document = rollback.get("rollback_document")
    checks["candidate_snapshot_valid"] = bool(
        isinstance(candidate_document, Mapping)
        and candidate.get("candidate_snapshot_sha256")
        == transaction.get("candidate_snapshot_sha256")
        and composition.raw_composition_candidate_snapshot_sha256_v2(candidate)
        == transaction.get("candidate_snapshot_sha256")
        and raw_binding.raw_registry_document_sha256_v1(candidate_document)
        == transaction.get("candidate_raw_registry_document_sha256")
        and candidate.get("translation_allowed") is False
        and candidate.get("apply_allowed") is False
    )
    checks["backup_preimage_valid"] = bool(
        isinstance(backup_snapshot, Mapping)
        and isinstance(backup_document, Mapping)
        and backup.get("immutable_preimage") is True
        and backup.get("snapshot_envelope_sha256")
        == transaction.get("source_snapshot_envelope_sha256")
        and raw_binding.raw_registry_snapshot_envelope_sha256_v1(backup_snapshot)
        == transaction.get("source_snapshot_envelope_sha256")
        and backup.get("raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and raw_binding.raw_registry_document_sha256_v1(backup_document)
        == transaction.get("source_raw_registry_document_sha256")
    )
    checks["rollback_preimage_valid"] = bool(
        isinstance(rollback_document, Mapping)
        and rollback.get("rollback_verified") is True
        and rollback.get("from_raw_registry_document_sha256")
        == transaction.get("candidate_raw_registry_document_sha256")
        and rollback.get("to_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and rollback.get("rollback_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and raw_binding.raw_registry_document_sha256_v1(rollback_document)
        == transaction.get("source_raw_registry_document_sha256")
        and rollback_document == backup_document
        and rollback.get("inverse_entry_count") == transaction.get("proposal_count")
        and rollback.get("inverse_path_count")
        == transaction.get("changed_path_count")
    )
    original_state = (
        rehearsal.classify_raw_registry_document_against_rehearsal_offline_v2(
            backup_document, transaction
        )
        if isinstance(backup_document, Mapping)
        else {}
    )
    candidate_state = (
        rehearsal.classify_raw_registry_document_against_rehearsal_offline_v2(
            candidate_document, transaction
        )
        if isinstance(candidate_document, Mapping)
        else {}
    )
    checks["original_and_candidate_states_valid"] = bool(
        original_state.get("ok") is True
        and original_state.get("state") == "ORIGINAL"
        and candidate_state.get("ok") is True
        and candidate_state.get("state") == "CANDIDATE_ALREADY_PRESENT"
        and original_state.get("apply_allowed") is False
        and candidate_state.get("apply_allowed") is False
    )
    for check, reason in (
        ("candidate_snapshot_valid", "RAW_TRANSACTION_CANDIDATE_INVALID"),
        ("backup_preimage_valid", "RAW_TRANSACTION_BACKUP_INVALID"),
        ("rollback_preimage_valid", "RAW_TRANSACTION_ROLLBACK_INVALID"),
        (
            "original_and_candidate_states_valid",
            "RAW_TRANSACTION_STATE_CLASSIFICATION_INVALID",
        ),
    ):
        if not checks[check]:
            reasons.append(reason)


def _check_record_bindings(
    transaction: Mapping[str, Any],
    receipt: Mapping[str, Any],
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    entries = receipt.get("entries")
    transaction_bindings = transaction.get("record_bindings")
    if not isinstance(entries, list) or not isinstance(transaction_bindings, list):
        reasons.append("RAW_RECORD_BINDINGS_REQUIRED")
        checks["record_binding_manifest_valid"] = False
        return ""
    expected = [
        {
            "proposal_ordinal": entry.get("proposal_ordinal"),
            "proposal_type": entry.get("proposal_type"),
            "registry_index": entry.get("registry_index"),
            "registry_collection_key": entry.get("registry_collection_key"),
            "collection_shape": entry.get("collection_shape"),
            "record_fingerprint_before": entry.get("record_fingerprint_before"),
            "raw_record_sha256_before": entry.get("raw_record_sha256_before"),
            "raw_record_sha256_after": entry.get(
                "raw_record_sha256_after_proposed"
            ),
            "changed_paths": list(entry.get("changed_paths") or []),
        }
        for entry in entries
        if isinstance(entry, Mapping)
    ]
    manifest_sha = _stable_sha256(expected)
    checks["record_binding_manifest_valid"] = bool(
        len(expected) == transaction.get("proposal_count")
        and transaction_bindings == expected
        and sum(len(item["changed_paths"]) for item in expected)
        == transaction.get("changed_path_count")
    )
    if not checks["record_binding_manifest_valid"]:
        reasons.append("RAW_RECORD_BINDING_MANIFEST_INVALID")
    return manifest_sha


def _check_attestations(
    attestations: Mapping[str, Any],
    transaction: Mapping[str, Any],
    receipt: Mapping[str, Any],
    record_manifest_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> tuple[str, str]:
    supplied_sha = _valid_sha256(attestations.get("attestations_sha256"))
    checks["attestations_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            raw_physical_apply_readiness_attestations_sha256_v2(attestations),
        )
    )
    checks["attestation_envelope_safe"] = bool(
        attestations.get("attestation_version") == _ATTESTATION_VERSION
        and attestations.get("synthetic_only") is True
        and attestations.get("offline_only") is True
        and attestations.get("production_observation") is False
        and attestations.get("transaction_sha256")
        == transaction.get("transaction_sha256")
        and attestations.get("composition_preview_receipt_sha256")
        == receipt.get("receipt_sha256")
    )

    chain = attestations.get("chain_evidence")
    checks["chain_evidence_valid"] = bool(
        isinstance(chain, Mapping)
        and chain.get("upstream_plan_sha256")
        == transaction.get("upstream_plan_sha256")
        and chain.get("binding_plan_sha256")
        == transaction.get("binding_plan_sha256")
        and chain.get("raw_path_receipt_sha256")
        == transaction.get("raw_path_receipt_sha256")
        and chain.get("composition_preview_receipt_sha256")
        == receipt.get("receipt_sha256")
        and chain.get("transaction_sha256")
        == transaction.get("transaction_sha256")
        and chain.get("record_binding_manifest_sha256") == record_manifest_sha
        and chain.get("proposal_count") == transaction.get("proposal_count")
        and chain.get("changed_path_count") == transaction.get("changed_path_count")
        and chain.get("raw_paths_complete") is True
        and chain.get("independently_revalidated") is True
    )
    authority = attestations.get("schema_authority")
    collection_shapes = {
        str(item.get("collection_shape") or "")
        for item in transaction.get("record_bindings", [])
        if isinstance(item, Mapping)
    }
    checks["schema_authority_valid"] = bool(
        isinstance(authority, Mapping)
        and authority.get("selected_authority") == _AUTHORITY
        and authority.get("authority_selection_explicit") is True
        and authority.get("collection_shape") in {"list", "dict"}
        and collection_shapes == {authority.get("collection_shape")}
        and authority.get("whole_registry_preimage_bound") is True
        and authority.get("source_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and authority.get("candidate_raw_registry_document_sha256")
        == transaction.get("candidate_raw_registry_document_sha256")
        and authority.get("open_trades_immutable") is True
        and authority.get("ownership_fields_immutable") is True
        and authority.get("order_fields_immutable") is True
        and authority.get("protection_fields_immutable") is True
    )

    writer_inventory = attestations.get("writer_inventory")
    writers = (
        writer_inventory.get("writers")
        if isinstance(writer_inventory, Mapping)
        else None
    )
    writer_sha = _stable_sha256(writers) if isinstance(writers, list) else ""
    checks["writer_inventory_synthetic_safe"] = bool(
        isinstance(writer_inventory, Mapping)
        and isinstance(writers, list)
        and writers
        and writer_inventory.get("inventory_complete") is True
        and writer_inventory.get("real_observation") is False
        and writer_inventory.get("writer_inventory_sha256") == writer_sha
        and all(
            isinstance(writer, Mapping)
            and writer.get("synthetic_only") is True
            and writer.get("real_writer_quiesced") is False
            for writer in writers
        )
    )
    lock = attestations.get("lock")
    checks["lock_attestation_synthetic_safe"] = bool(
        isinstance(lock, Mapping)
        and lock.get("synthetic_lock_rehearsal_verified") is True
        and lock.get("real_interprocess_lock_acquired") is False
        and lock.get("production_writers_quiesced") is False
        and lock.get("fail_closed_on_timeout") is True
        and lock.get("writer_inventory_sha256") == writer_sha
        and lock.get("transaction_sha256") == transaction.get("transaction_sha256")
    )
    backup = attestations.get("backup")
    checks["backup_attestation_synthetic_safe"] = bool(
        isinstance(backup, Mapping)
        and backup.get("synthetic_backup_verified") is True
        and backup.get("durable_production_backup_created") is False
        and backup.get("restore_rehearsal_verified") is True
        and backup.get("source_raw_registry_document_sha256")
        == transaction.get("source_raw_registry_document_sha256")
        and backup.get("transaction_sha256") == transaction.get("transaction_sha256")
    )
    isolation = attestations.get("operational_isolation")
    checks["operational_isolation_valid"] = bool(
        isinstance(isolation, Mapping)
        and isolation.get("runtime_integrated") is False
        and isolation.get("filesystem_accessed") is False
        and isolation.get("network_accessed") is False
        and isolation.get("external_service_called") is False
        and isolation.get("real_registry_accessed") is False
        and isolation.get("order_submission_authorized") is False
    )
    authorization = attestations.get("authorization")
    checks["authorization_scope_safe"] = bool(
        isinstance(authorization, Mapping)
        and authorization.get("scope") == _AUTHORIZATION_SCOPE
        and authorization.get("readiness_review_authorized") is True
        and authorization.get("production_apply_authorized") is False
        and authorization.get("live_activation_authorized") is False
        and authorization.get("order_submission_authorized") is False
        and authorization.get("separate_production_authorization_required") is True
    )
    for check, reason in (
        ("attestations_sha256_valid", "RAW_READINESS_ATTESTATIONS_SHA256_INVALID"),
        ("attestation_envelope_safe", "RAW_READINESS_ATTESTATION_ENVELOPE_INVALID"),
        ("chain_evidence_valid", "RAW_READINESS_CHAIN_EVIDENCE_INVALID"),
        ("schema_authority_valid", "RAW_READINESS_SCHEMA_AUTHORITY_INVALID"),
        (
            "writer_inventory_synthetic_safe",
            "RAW_READINESS_WRITER_INVENTORY_INVALID",
        ),
        ("lock_attestation_synthetic_safe", "RAW_READINESS_LOCK_ATTESTATION_INVALID"),
        (
            "backup_attestation_synthetic_safe",
            "RAW_READINESS_BACKUP_ATTESTATION_INVALID",
        ),
        ("operational_isolation_valid", "RAW_READINESS_ISOLATION_INVALID"),
        ("authorization_scope_safe", "RAW_READINESS_AUTHORIZATION_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha, writer_sha


def evaluate_closed_identity_conflict_raw_physical_apply_readiness_offline_v2(
    transaction: Mapping[str, Any],
    composition_preview_receipt: Mapping[str, Any],
    readiness_attestations: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate complete offline V2 evidence while permanently denying apply."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (
            transaction,
            composition_preview_receipt,
            readiness_attestations,
        )
    ):
        reasons.append("RAW_READINESS_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        transaction_copy = _canonical_copy(transaction)
        receipt_copy = _canonical_copy(composition_preview_receipt)
        attestations_copy = _canonical_copy(readiness_attestations)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RAW_READINESS_INPUT_NOT_CANONICALIZABLE")
        return base

    _check_transaction(transaction_copy, reasons, checks)
    _check_composition_receipt(receipt_copy, transaction_copy, reasons, checks)
    _check_candidate_backup_rollback(transaction_copy, reasons, checks)
    record_manifest_sha = _check_record_bindings(
        transaction_copy, receipt_copy, reasons, checks
    )
    attestations_sha, writer_sha = _check_attestations(
        attestations_copy,
        transaction_copy,
        receipt_copy,
        record_manifest_sha,
        reasons,
        checks,
    )
    reasons[:] = sorted(set(str(item) for item in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_RAW_READINESS_CHECKS_FAILED")
        return base

    gate_receipt = {
        "transaction_sha256": transaction_copy["transaction_sha256"],
        "composition_preview_receipt_sha256": receipt_copy["receipt_sha256"],
        "raw_path_receipt_sha256": transaction_copy["raw_path_receipt_sha256"],
        "attestations_sha256": attestations_sha,
        "record_binding_manifest_sha256": record_manifest_sha,
        "writer_inventory_sha256": writer_sha,
        "selected_schema_authority": _AUTHORITY,
        "check_count": len(checks),
        "all_offline_checks_passed": True,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    gate_receipt["gate_receipt_sha256"] = _stable_sha256(gate_receipt)
    base.update(
        {
            "ok": True,
            "readiness_verification_allowed": True,
            "offline_evidence_valid": True,
            "production_ready": False,
            "translation_allowed": False,
            "apply_allowed": False,
            "status": "RAW_CLOSED_IDENTITY_CONFLICT_READINESS_V2_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "gate_receipt": gate_receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_CONTRACT_V2_VERSION",
    "evaluate_closed_identity_conflict_raw_physical_apply_readiness_offline_v2",
    "raw_physical_apply_readiness_attestations_sha256_v2",
]
