"""Dormant writer-coordination contract for the raw CLOSED repair boundary.

This module binds the complete audited writer inventory to a maintenance lease
and one shared-lock namespace.  It accepts only synthetic rehearsal evidence,
has no runtime hooks and can never authorize Registry persistence or apply.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_physical_storage_boundary_contract_v1 as storage_boundary


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-COORDINATION-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_WRITER_COORDINATION_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_WRITER_COORDINATION_REHEARSAL_V1"
_AUTHORITY_ID = "SYNTHETIC_RAW_REGISTRY_AUTHORITY_V1"
_LOCK_DERIVATION = "SHA256_CANONICAL_STORAGE_AUTHORITY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_EVENT_SEQUENCE = (
    "WRITER_INVENTORY_BOUND",
    "MAINTENANCE_LEASE_REQUESTED",
    "NEW_WRITES_FENCED",
    "ALL_WRITERS_ACKNOWLEDGED",
    "ZERO_INFLIGHT_CONFIRMED",
    "SYNTHETIC_SHARED_LOCK_ACQUIRED",
    "STORAGE_BOUNDARY_PREFLIGHT_REHEARSED",
    "SYNTHETIC_SHARED_LOCK_RELEASED",
    "MAINTENANCE_LEASE_RELEASED",
)
_PRODUCTION_BLOCKERS = (
    "WRITER_COORDINATION_IS_CONTRACT_ONLY",
    "RUNTIME_WRITER_REGISTRATION_ABSENT",
    "REAL_MAINTENANCE_LEASE_NOT_ISSUED",
    "REAL_NEW_WRITES_NOT_FENCED",
    "REAL_INFLIGHT_MUTATIONS_NOT_DRAINED",
    "REAL_SHARED_LOCK_NOT_ACQUIRED",
    "PHYSICAL_APPLY_ENTRYPOINT_ABSENT",
    "SEPARATE_PRODUCTION_APPLY_AUTHORIZATION_REQUIRED",
)

_EXPECTED_WRITERS = (
    ("TRADE_REGISTRY_LOAD_INITIALIZE_OR_MIGRATE", "trade_registry.py", "load_registry", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_REGISTER_OPEN_TRADE", "trade_registry.py", "register_open_trade", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_UPDATE_OPEN_TRADE", "trade_registry.py", "update_trade", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_UPDATE_CLOSED_TRADE", "trade_registry.py", "update_closed_trade", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_HISTORICAL_STRONG_IDENTITY_BACKFILL", "trade_registry.py", "backfill_historical_strong_identity", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_RECORD_MANUAL_CLOSE_OUTCOME", "trade_registry.py", "record_manual_close_outcome", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_CLOSE_TRADE", "trade_registry.py", "close_trade", "PROCESS_LOCAL_FULL_RMW"),
    ("TRADE_REGISTRY_RESET", "trade_registry.py", "reset_trade_registry", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_SYNC_MANUAL_REGISTER_OPEN", "main.py", "_trs_v1_manual_register_open_trade", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_LIFECYCLE_UPDATE_OPEN_SNAPSHOT", "main.py", "_rtlm_v1_update_open_trade_snapshot", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_PERSISTENCE_RESTORE_LATEST_SNAPSHOT", "main.py", "registry_persistence_v1_restore_from_latest_snapshot", "PROCESS_LOCAL_FULL_RMW"),
    ("MAIN_PERSISTENCE_RECOVER_CLOSED_TRADE", "main.py", "registry_persistence_v12_recover_closed_trade_from_params", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_TRADE_CLOSE_OUTCOME_COMMIT", "main.py", "trade_close_outcome_v1_commit", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_REGISTRY_MODE_SEGREGATION_COMMIT", "main.py", "registry_mode_segregation_v1_analyze", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_MARK_REGISTRY_MISSING_TRADES", "main.py", "mark_registry_missing_trades", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_PREDATOR_PAPER_REGISTRY_SYNC", "main.py", "predator_paper_registry_sync_fix_v1_status", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_PREDATOR_ORPHAN_OPEN_FIX", "main.py", "predator_registry_orphan_open_fix_v1_status", "PROCESS_LOCAL_SAVE_ONLY"),
    ("MAIN_PREDATOR_AUTO_CLOSED_SYNC", "main.py", "predator_auto_closed_sync_v1_status", "PROCESS_LOCAL_FULL_RMW"),
    ("MAIN_TRADE_REGISTRY_STORAGE_BOOTSTRAP", "main.py", "_trpsf_v1_bootstrap_registry", "PROCESS_LOCAL_FULL_RMW"),
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


def canonical_closed_repair_writer_inventory_v1() -> list[dict[str, str]]:
    """Return an isolated copy of the 19 audited logical writer surfaces."""

    return [
        {
            "writer_id": writer_id,
            "component": component,
            "function": function,
            "audited_current_lock_scope": lock_scope,
            "required_target_lock_scope": "SHARED_INTERPROCESS_FULL_RMW",
        }
        for writer_id, component, function, lock_scope in _EXPECTED_WRITERS
    ]


def closed_repair_writer_coordination_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def closed_repair_writer_coordination_rehearsal_sha256_v1(
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
        "coordination_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "status": "CLOSED_REPAIR_WRITER_COORDINATION_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_CONTRACT_V1_VERSION,
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
        "coordination_receipt": None,
    }


def _check_boundary(
    boundary_result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[str, str]:
    receipt = boundary_result.get("boundary_receipt")
    receipt_sha = (
        _valid_sha256(receipt.get("boundary_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _stable_sha256(
            {
                key: value
                for key, value in receipt.items()
                if key != "boundary_receipt_sha256"
            }
        )
        if isinstance(receipt, Mapping)
        else ""
    )
    transaction_sha = (
        str(receipt.get("transaction_sha256") or "")
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_storage_boundary_valid"] = bool(
        boundary_result.get("ok") is True
        and boundary_result.get("boundary_contract_verified") is True
        and boundary_result.get("synthetic_rehearsal_valid") is True
        and boundary_result.get("production_ready") is False
        and boundary_result.get("translation_allowed") is False
        and boundary_result.get("apply_allowed") is False
        and boundary_result.get("physical_apply_entrypoint_present") is False
        and boundary_result.get("write_executed") is False
        and boundary_result.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt_sha
        and hmac.compare_digest(receipt_sha, expected_sha)
        and _valid_sha256(transaction_sha)
        and receipt.get("all_offline_checks_passed") is True
        and receipt.get("production_blockers")
    )
    if not checks["upstream_storage_boundary_valid"]:
        reasons.append("WRITER_COORDINATION_UPSTREAM_BOUNDARY_INVALID")
    return receipt_sha, transaction_sha


def _check_spec(
    spec: Mapping[str, Any],
    boundary_receipt_sha: str,
    transaction_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> tuple[str, str, str]:
    supplied_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, closed_repair_writer_coordination_spec_sha256_v1(spec)
        )
    )
    inventory = spec.get("writer_inventory")
    expected_inventory = canonical_closed_repair_writer_inventory_v1()
    expected_inventory_sha = _stable_sha256(expected_inventory)
    writer_ids = [item["writer_id"] for item in expected_inventory]
    checks["writer_inventory_exact"] = bool(
        isinstance(inventory, list)
        and inventory == expected_inventory
        and len(inventory) == 19
        and len({item.get("writer_id") for item in inventory}) == 19
        and spec.get("writer_inventory_sha256") == expected_inventory_sha
    )
    authority = spec.get("storage_authority")
    expected_authority_sha = _stable_sha256(
        {
            "authority_id": _AUTHORITY_ID,
            "synthetic_only": True,
            "canonical_runtime_path_required_later": True,
        }
    )
    checks["storage_authority_contract_valid"] = bool(
        isinstance(authority, Mapping)
        and authority.get("authority_id") == _AUTHORITY_ID
        and authority.get("synthetic_only") is True
        and authority.get("canonical_runtime_path_required_later") is True
        and authority.get("authority_sha256") == expected_authority_sha
        and authority.get("real_path_observed") is False
    )
    lock = spec.get("shared_lock_protocol")
    expected_namespace_sha = _stable_sha256(
        {
            "authority_sha256": expected_authority_sha,
            "purpose": "TRADE_REGISTRY_FULL_RMW_COORDINATION",
        }
    )
    checks["shared_lock_protocol_valid"] = bool(
        isinstance(lock, Mapping)
        and lock.get("namespace_derivation") == _LOCK_DERIVATION
        and lock.get("lock_namespace_sha256") == expected_namespace_sha
        and lock.get("covered_writer_ids") == writer_ids
        and lock.get("exclusive") is True
        and lock.get("interprocess") is True
        and lock.get("reentrant_within_owner") is True
        and lock.get("bounded_timeout") is True
        and lock.get("fail_closed_on_timeout") is True
        and lock.get("scope") == "READ_THROUGH_DURABLE_COMMIT_OR_ABORT"
    )
    lease = spec.get("maintenance_lease_protocol")
    checks["maintenance_lease_protocol_valid"] = bool(
        isinstance(lease, Mapping)
        and lease.get("states") == ["REQUESTED", "DRAINING", "QUIESCED", "RELEASED"]
        and lease.get("epoch_bound") is True
        and lease.get("new_mutations_fenced_while_active") is True
        and lease.get("all_registered_writers_ack_required") is True
        and lease.get("zero_inflight_required") is True
        and lease.get("unknown_writer_fails_closed") is True
        and lease.get("missing_ack_fails_closed") is True
        and lease.get("stale_epoch_fails_closed") is True
        and lease.get("release_requires_lock_released") is True
    )
    mutation = spec.get("writer_mutation_protocol")
    checks["writer_mutation_protocol_valid"] = bool(
        isinstance(mutation, Mapping)
        and mutation.get("register_before_mutation") is True
        and mutation.get("lease_check_before_read") is True
        and mutation.get("increment_inflight_before_read") is True
        and mutation.get("shared_lock_before_read") is True
        and mutation.get("decrement_inflight_after_commit_or_abort") is True
        and mutation.get("ack_only_at_zero_inflight") is True
        and mutation.get("normalization_forbidden_for_raw_repair") is True
    )
    safety = spec.get("safety_envelope")
    checks["spec_safety_envelope_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_boundary_receipt_sha256") == boundary_receipt_sha
        and spec.get("transaction_sha256") == transaction_sha
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("runtime_install_allowed") is False
        and safety.get("real_writer_contacted") is False
        and safety.get("real_lease_issued") is False
        and safety.get("real_lock_acquired") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("production_apply_authorized") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "WRITER_COORDINATION_SPEC_SHA256_INVALID"),
        ("writer_inventory_exact", "WRITER_COORDINATION_INVENTORY_NOT_EXACT"),
        ("storage_authority_contract_valid", "WRITER_COORDINATION_AUTHORITY_INVALID"),
        ("shared_lock_protocol_valid", "WRITER_COORDINATION_SHARED_LOCK_INVALID"),
        ("maintenance_lease_protocol_valid", "WRITER_COORDINATION_LEASE_PROTOCOL_INVALID"),
        ("writer_mutation_protocol_valid", "WRITER_COORDINATION_MUTATION_PROTOCOL_INVALID"),
        ("spec_safety_envelope_valid", "WRITER_COORDINATION_SPEC_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha, expected_inventory_sha, expected_namespace_sha


def _check_rehearsal(
    receipt: Mapping[str, Any],
    boundary_receipt_sha: str,
    transaction_sha: str,
    spec_sha: str,
    inventory_sha: str,
    namespace_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(receipt.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            closed_repair_writer_coordination_rehearsal_sha256_v1(receipt),
        )
    )
    acknowledgements = receipt.get("writer_acknowledgements")
    expected_ids = [item[0] for item in _EXPECTED_WRITERS]
    lease = receipt.get("maintenance_lease")
    epoch = lease.get("epoch") if isinstance(lease, Mapping) else None
    ack_manifest_sha = _stable_sha256(acknowledgements) if isinstance(acknowledgements, list) else ""
    checks["rehearsal_chain_valid"] = bool(
        receipt.get("rehearsal_version") == _REHEARSAL_VERSION
        and receipt.get("upstream_boundary_receipt_sha256") == boundary_receipt_sha
        and receipt.get("transaction_sha256") == transaction_sha
        and receipt.get("coordination_spec_sha256") == spec_sha
        and receipt.get("writer_inventory_sha256") == inventory_sha
        and receipt.get("writer_count") == 19
        and tuple(receipt.get("event_sequence") or ()) == _REQUIRED_EVENT_SEQUENCE
    )
    checks["writer_acknowledgements_valid"] = bool(
        isinstance(acknowledgements, list)
        and all(isinstance(item, Mapping) for item in acknowledgements)
        and [item.get("writer_id") for item in acknowledgements] == expected_ids
        and all(
            item.get("lease_epoch") == epoch
            and item.get("new_mutations_fenced") is True
            and item.get("inflight_mutations") == 0
            and item.get("acknowledged") is True
            for item in acknowledgements
        )
        and receipt.get("writer_acknowledgements_sha256") == ack_manifest_sha
    )
    checks["maintenance_lease_rehearsal_valid"] = bool(
        isinstance(lease, Mapping)
        and _valid_sha256(epoch)
        and lease.get("initial_state") == "REQUESTED"
        and lease.get("drain_state") == "DRAINING"
        and lease.get("quiesced_state") == "QUIESCED"
        and lease.get("final_state") == "RELEASED"
        and lease.get("new_mutations_fenced") is True
        and lease.get("unknown_writer_count") == 0
        and lease.get("missing_ack_count") == 0
        and lease.get("stale_epoch_count") == 0
        and lease.get("inflight_mutation_count") == 0
    )
    lock = receipt.get("shared_lock")
    checks["shared_lock_rehearsal_valid"] = bool(
        isinstance(lock, Mapping)
        and lock.get("lock_namespace_sha256") == namespace_sha
        and lock.get("synthetic_acquired") is True
        and lock.get("synthetic_released") is True
        and lock.get("acquired_after_quiescence") is True
        and lock.get("released_before_lease") is True
        and lock.get("fail_closed_on_timeout") is True
        and lock.get("real_lock_acquired") is False
    )
    boundary_preflight = receipt.get("storage_boundary_preflight")
    checks["storage_boundary_preflight_safe"] = bool(
        isinstance(boundary_preflight, Mapping)
        and boundary_preflight.get("boundary_contract_verified") is True
        and boundary_preflight.get("production_ready") is False
        and boundary_preflight.get("apply_allowed") is False
        and boundary_preflight.get("physical_apply_entrypoint_present") is False
        and boundary_preflight.get("candidate_materialized") is False
    )
    safety = receipt.get("safety_envelope")
    checks["rehearsal_safety_envelope_valid"] = bool(
        isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("real_writer_contacted") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("runtime_integrated") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("broker_called") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        ("rehearsal_sha256_valid", "WRITER_COORDINATION_REHEARSAL_SHA256_INVALID"),
        ("rehearsal_chain_valid", "WRITER_COORDINATION_REHEARSAL_CHAIN_INVALID"),
        ("writer_acknowledgements_valid", "WRITER_COORDINATION_ACKNOWLEDGEMENTS_INVALID"),
        ("maintenance_lease_rehearsal_valid", "WRITER_COORDINATION_LEASE_REHEARSAL_INVALID"),
        ("shared_lock_rehearsal_valid", "WRITER_COORDINATION_LOCK_REHEARSAL_INVALID"),
        ("storage_boundary_preflight_safe", "WRITER_COORDINATION_BOUNDARY_PREFLIGHT_INVALID"),
        ("rehearsal_safety_envelope_valid", "WRITER_COORDINATION_REHEARSAL_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def evaluate_closed_repair_writer_coordination_offline_v1(
    storage_boundary_result: Mapping[str, Any],
    coordination_spec: Mapping[str, Any],
    rehearsal_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate synthetic writer coordination while always denying runtime use."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (storage_boundary_result, coordination_spec, rehearsal_receipt)
    ):
        reasons.append("WRITER_COORDINATION_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        boundary_copy = _canonical_copy(storage_boundary_result)
        spec_copy = _canonical_copy(coordination_spec)
        rehearsal_copy = _canonical_copy(rehearsal_receipt)
    except (TypeError, ValueError, OverflowError):
        reasons.append("WRITER_COORDINATION_INPUT_NOT_CANONICALIZABLE")
        return base

    boundary_sha, transaction_sha = _check_boundary(boundary_copy, reasons, checks)
    spec_sha, inventory_sha, namespace_sha = _check_spec(
        spec_copy, boundary_sha, transaction_sha, reasons, checks
    )
    rehearsal_sha = _check_rehearsal(
        rehearsal_copy,
        boundary_sha,
        transaction_sha,
        spec_sha,
        inventory_sha,
        namespace_sha,
        reasons,
        checks,
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_WRITER_COORDINATION_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_boundary_receipt_sha256": boundary_sha,
        "transaction_sha256": transaction_sha,
        "coordination_spec_sha256": spec_sha,
        "writer_inventory_sha256": inventory_sha,
        "lock_namespace_sha256": namespace_sha,
        "rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "all_offline_checks_passed": True,
        "runtime_install_allowed": False,
        "production_ready": False,
        "apply_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["coordination_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "coordination_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "production_ready": False,
            "translation_allowed": False,
            "apply_allowed": False,
            "runtime_install_allowed": False,
            "status": "CLOSED_REPAIR_WRITER_COORDINATION_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "coordination_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_CONTRACT_V1_VERSION",
    "canonical_closed_repair_writer_inventory_v1",
    "closed_repair_writer_coordination_rehearsal_sha256_v1",
    "closed_repair_writer_coordination_spec_sha256_v1",
    "evaluate_closed_repair_writer_coordination_offline_v1",
]
