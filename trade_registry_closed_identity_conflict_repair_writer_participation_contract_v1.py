"""Dormant per-writer participation contract for CLOSED repair coordination.

All registration, lease, inflight and lock tokens are synthetic and in-memory.
The contract validates protocol evidence for the 19 audited writers but exposes
no wrapper, runtime installation or Registry mutation surface.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-PARTICIPATION-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_WRITER_PARTICIPATION_SPEC_V1"
_BUNDLE_VERSION = "SYNTHETIC_CLOSED_REPAIR_WRITER_PARTICIPATION_BUNDLE_V1"
_PARTICIPANT_RECEIPT_VERSION = "SYNTHETIC_CLOSED_REPAIR_WRITER_PARTICIPANT_RECEIPT_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NORMAL_SEQUENCE = (
    "WRITER_REGISTERED",
    "MAINTENANCE_LEASE_ABSENT",
    "INFLIGHT_TOKEN_ISSUED",
    "SYNTHETIC_SHARED_LOCK_ACQUIRED",
    "WRITER_OPERATION_NOT_INVOKED_CONTRACT_ONLY",
    "SYNTHETIC_SHARED_LOCK_RELEASED",
    "INFLIGHT_TOKEN_COMPLETED",
)
_MAINTENANCE_SEQUENCE = (
    "WRITER_REGISTERED",
    "MAINTENANCE_LEASE_OBSERVED",
    "NEW_MUTATION_FENCED",
    "ZERO_INFLIGHT_CONFIRMED",
    "LEASE_ACK_TOKEN_ISSUED",
)
_PRODUCTION_BLOCKERS = (
    "PARTICIPATION_IS_CONTRACT_ONLY",
    "REAL_WRITER_ADAPTERS_ABSENT",
    "REAL_REGISTRATION_TOKENS_NOT_ISSUED",
    "REAL_LEASE_NOT_OBSERVED",
    "REAL_INFLIGHT_ACCOUNTING_NOT_ACTIVE",
    "REAL_SHARED_LOCK_NOT_ACQUIRED",
    "RUNTIME_INSTALL_NOT_AUTHORIZED",
    "PHYSICAL_APPLY_ENTRYPOINT_ABSENT",
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


def writer_participation_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def writer_participant_receipt_sha256_v1(receipt: Mapping[str, Any]) -> str:
    if not isinstance(receipt, Mapping):
        raise TypeError("receipt must be a mapping")
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != "participant_receipt_sha256"}
    )


def writer_participation_bundle_sha256_v1(bundle: Mapping[str, Any]) -> str:
    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    return _stable_sha256(
        {key: value for key, value in bundle.items() if key != "bundle_sha256"}
    )


def _coordination_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != "coordination_receipt_sha256"}
    )


def _maintenance_epoch(
    transaction_sha: str, inventory_sha: str, namespace_sha: str
) -> str:
    return _stable_sha256(
        {
            "transaction_sha256": transaction_sha,
            "writer_inventory_sha256": inventory_sha,
            "lock_namespace_sha256": namespace_sha,
            "lease_ordinal": 1,
        }
    )


def _registration_token(
    writer: Mapping[str, Any], inventory_sha: str, namespace_sha: str
) -> str:
    return _stable_sha256(
        {
            "token_type": "WRITER_REGISTRATION_TOKEN_V1",
            "writer": writer,
            "writer_inventory_sha256": inventory_sha,
            "lock_namespace_sha256": namespace_sha,
        }
    )


def _inflight_token(registration_token: str, transaction_sha: str) -> str:
    return _stable_sha256(
        {
            "token_type": "WRITER_INFLIGHT_TOKEN_V1",
            "registration_token": registration_token,
            "transaction_sha256": transaction_sha,
            "cycle_ordinal": 1,
        }
    )


def _lock_token(inflight_token: str, namespace_sha: str) -> str:
    return _stable_sha256(
        {
            "token_type": "WRITER_SHARED_LOCK_TOKEN_V1",
            "inflight_token": inflight_token,
            "lock_namespace_sha256": namespace_sha,
        }
    )


def _lease_ack_token(
    registration_token: str, maintenance_epoch: str
) -> str:
    return _stable_sha256(
        {
            "token_type": "WRITER_LEASE_ACK_TOKEN_V1",
            "registration_token": registration_token,
            "maintenance_epoch": maintenance_epoch,
            "inflight_mutations": 0,
        }
    )


def canonical_writer_participation_bindings_v1(
    coordination_receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Bind every audited writer identity to one synthetic registration token."""

    if not isinstance(coordination_receipt, Mapping):
        raise TypeError("coordination_receipt must be a mapping")
    inventory_sha = str(coordination_receipt.get("writer_inventory_sha256") or "")
    namespace_sha = str(coordination_receipt.get("lock_namespace_sha256") or "")
    return [
        {
            "writer": writer,
            "registration_token": _registration_token(
                writer, inventory_sha, namespace_sha
            ),
            "writer_inventory_sha256": inventory_sha,
            "lock_namespace_sha256": namespace_sha,
            "normal_cycle_required": True,
            "maintenance_cycle_required": True,
            "runtime_callable_bound": False,
        }
        for writer in coordination.canonical_closed_repair_writer_inventory_v1()
    ]


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "participation_contract_verified": False,
        "synthetic_participants_valid": False,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "status": "CLOSED_REPAIR_WRITER_PARTICIPATION_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_CONTRACT_V1_VERSION,
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
        "participation_receipt": None,
    }


def _check_coordination(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[Mapping[str, Any] | None, str]:
    receipt = result.get("coordination_receipt")
    supplied_sha = (
        _valid_sha256(receipt.get("coordination_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _coordination_receipt_sha256(receipt)
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_coordination_valid"] = bool(
        result.get("ok") is True
        and result.get("coordination_contract_verified") is True
        and result.get("synthetic_rehearsal_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and supplied_sha
        and hmac.compare_digest(supplied_sha, expected_sha)
        and receipt.get("writer_count") == 19
        and receipt.get("all_offline_checks_passed") is True
        and receipt.get("production_blockers")
    )
    if not checks["upstream_coordination_valid"]:
        reasons.append("WRITER_PARTICIPATION_UPSTREAM_COORDINATION_INVALID")
    return receipt if isinstance(receipt, Mapping) else None, supplied_sha


def _check_spec(
    spec: Mapping[str, Any],
    coordination_receipt: Mapping[str, Any] | None,
    coordination_receipt_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> tuple[str, list[dict[str, Any]]]:
    supplied_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, writer_participation_spec_sha256_v1(spec)
        )
    )
    expected_bindings = (
        canonical_writer_participation_bindings_v1(coordination_receipt)
        if isinstance(coordination_receipt, Mapping)
        else []
    )
    bindings = spec.get("writer_bindings")
    checks["writer_bindings_exact"] = bool(
        isinstance(bindings, list)
        and bindings == expected_bindings
        and len(bindings) == 19
        and len(
            {
                item["writer"]["writer_id"]
                for item in bindings
                if isinstance(item, Mapping)
                and isinstance(item.get("writer"), Mapping)
            }
        )
        == 19
        and spec.get("writer_bindings_sha256") == _stable_sha256(expected_bindings)
    )
    protocol = spec.get("individual_protocol")
    checks["individual_protocol_valid"] = bool(
        isinstance(protocol, Mapping)
        and protocol.get("registration_token_required") is True
        and protocol.get("lease_check_before_inflight") is True
        and protocol.get("active_lease_fences_new_mutation") is True
        and protocol.get("inflight_token_single_use") is True
        and protocol.get("lock_token_requires_inflight_token") is True
        and protocol.get("lock_namespace_must_match_coordination") is True
        and protocol.get("lock_release_before_inflight_completion") is True
        and protocol.get("lease_ack_requires_zero_inflight") is True
        and protocol.get("writer_callable_absent") is True
        and protocol.get("fail_closed_on_unknown_token") is True
    )
    safety = spec.get("safety_envelope")
    transaction_sha = (
        coordination_receipt.get("transaction_sha256")
        if isinstance(coordination_receipt, Mapping)
        else None
    )
    checks["spec_safety_envelope_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_coordination_receipt_sha256")
        == coordination_receipt_sha
        and spec.get("transaction_sha256") == transaction_sha
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("runtime_writer_bound") is False
        and safety.get("real_token_issued") is False
        and safety.get("real_lock_acquired") is False
        and safety.get("real_writer_called") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("apply_entrypoint_present") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "WRITER_PARTICIPATION_SPEC_SHA256_INVALID"),
        ("writer_bindings_exact", "WRITER_PARTICIPATION_BINDINGS_NOT_EXACT"),
        ("individual_protocol_valid", "WRITER_PARTICIPATION_PROTOCOL_INVALID"),
        ("spec_safety_envelope_valid", "WRITER_PARTICIPATION_SPEC_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha, expected_bindings


def _participant_valid(
    receipt: Mapping[str, Any],
    binding: Mapping[str, Any],
    transaction_sha: str,
    maintenance_epoch: str,
    namespace_sha: str,
) -> bool:
    writer = binding["writer"]
    writer_id = writer["writer_id"]
    registration_token = binding["registration_token"]
    expected_inflight_token = _inflight_token(registration_token, transaction_sha)
    expected_lock_token = _lock_token(expected_inflight_token, namespace_sha)
    expected_ack_token = _lease_ack_token(registration_token, maintenance_epoch)
    supplied_sha = _valid_sha256(receipt.get("participant_receipt_sha256"))
    normal = receipt.get("normal_cycle")
    maintenance = receipt.get("maintenance_cycle")
    safety = receipt.get("safety_envelope")
    return bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, writer_participant_receipt_sha256_v1(receipt)
        )
        and receipt.get("receipt_version") == _PARTICIPANT_RECEIPT_VERSION
        and receipt.get("writer_id") == writer_id
        and receipt.get("registration_token") == registration_token
        and isinstance(normal, Mapping)
        and normal.get("event_sequence") == list(_NORMAL_SEQUENCE)
        and normal.get("maintenance_lease_active") is False
        and normal.get("mutation_admitted") is True
        and normal.get("inflight_before") == 0
        and normal.get("inflight_during") == 1
        and normal.get("inflight_after") == 0
        and normal.get("inflight_token") == expected_inflight_token
        and normal.get("lock_namespace_sha256") == namespace_sha
        and normal.get("lock_token") == expected_lock_token
        and normal.get("synthetic_lock_acquired") is True
        and normal.get("synthetic_lock_released") is True
        and normal.get("writer_operation_executed") is False
        and isinstance(maintenance, Mapping)
        and maintenance.get("event_sequence") == list(_MAINTENANCE_SEQUENCE)
        and maintenance.get("maintenance_lease_active") is True
        and maintenance.get("maintenance_epoch") == maintenance_epoch
        and maintenance.get("new_mutation_admitted") is False
        and maintenance.get("inflight_mutations") == 0
        and maintenance.get("lease_ack_token") == expected_ack_token
        and maintenance.get("lease_acknowledged") is True
        and maintenance.get("shared_lock_attempted") is False
        and maintenance.get("writer_operation_executed") is False
        and isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("runtime_callable_bound") is False
        and safety.get("real_token_issued") is False
        and safety.get("real_lock_acquired") is False
        and safety.get("real_writer_called") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("no_order_sent") is True
    )


def _check_bundle(
    bundle: Mapping[str, Any],
    coordination_receipt: Mapping[str, Any] | None,
    coordination_receipt_sha: str,
    spec_sha: str,
    expected_bindings: list[dict[str, Any]],
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(bundle.get("bundle_sha256"))
    checks["bundle_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, writer_participation_bundle_sha256_v1(bundle)
        )
    )
    receipts = bundle.get("participant_receipts")
    receipts_sha = _stable_sha256(receipts) if isinstance(receipts, list) else ""
    transaction_sha = (
        str(coordination_receipt.get("transaction_sha256") or "")
        if isinstance(coordination_receipt, Mapping)
        else ""
    )
    inventory_sha = (
        str(coordination_receipt.get("writer_inventory_sha256") or "")
        if isinstance(coordination_receipt, Mapping)
        else ""
    )
    namespace_sha = (
        str(coordination_receipt.get("lock_namespace_sha256") or "")
        if isinstance(coordination_receipt, Mapping)
        else ""
    )
    maintenance_epoch = _maintenance_epoch(
        transaction_sha, inventory_sha, namespace_sha
    )
    checks["bundle_chain_valid"] = bool(
        bundle.get("bundle_version") == _BUNDLE_VERSION
        and bundle.get("upstream_coordination_receipt_sha256")
        == coordination_receipt_sha
        and bundle.get("participation_spec_sha256") == spec_sha
        and bundle.get("transaction_sha256") == transaction_sha
        and bundle.get("writer_inventory_sha256") == inventory_sha
        and bundle.get("lock_namespace_sha256") == namespace_sha
        and bundle.get("maintenance_epoch") == maintenance_epoch
        and bundle.get("writer_count") == 19
        and bundle.get("participant_receipts_sha256") == receipts_sha
    )
    expected_ids = [binding["writer"]["writer_id"] for binding in expected_bindings]
    receipts_well_formed = bool(
        isinstance(receipts, list)
        and len(receipts) == 19
        and all(isinstance(receipt, Mapping) for receipt in receipts)
    )
    checks["all_participant_receipts_valid"] = bool(
        receipts_well_formed
        and [receipt.get("writer_id") for receipt in receipts] == expected_ids
        and all(
            _participant_valid(
                receipt,
                binding,
                transaction_sha,
                maintenance_epoch,
                namespace_sha,
            )
            for receipt, binding in zip(receipts, expected_bindings)
        )
    )
    safety = bundle.get("safety_envelope")
    checks["bundle_safety_envelope_valid"] = bool(
        isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("all_writer_operations_executed") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("runtime_integrated") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        ("bundle_sha256_valid", "WRITER_PARTICIPATION_BUNDLE_SHA256_INVALID"),
        ("bundle_chain_valid", "WRITER_PARTICIPATION_BUNDLE_CHAIN_INVALID"),
        ("all_participant_receipts_valid", "WRITER_PARTICIPATION_PARTICIPANT_INVALID"),
        ("bundle_safety_envelope_valid", "WRITER_PARTICIPATION_BUNDLE_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def evaluate_closed_repair_writer_participation_offline_v1(
    coordination_result: Mapping[str, Any],
    participation_spec: Mapping[str, Any],
    participation_bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate all synthetic participants while always denying installation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (coordination_result, participation_spec, participation_bundle)
    ):
        reasons.append("WRITER_PARTICIPATION_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        coordination_copy = _canonical_copy(coordination_result)
        spec_copy = _canonical_copy(participation_spec)
        bundle_copy = _canonical_copy(participation_bundle)
    except (TypeError, ValueError, OverflowError):
        reasons.append("WRITER_PARTICIPATION_INPUT_NOT_CANONICALIZABLE")
        return base

    coordination_receipt, coordination_sha = _check_coordination(
        coordination_copy, reasons, checks
    )
    spec_sha, expected_bindings = _check_spec(
        spec_copy, coordination_receipt, coordination_sha, reasons, checks
    )
    bundle_sha = _check_bundle(
        bundle_copy,
        coordination_receipt,
        coordination_sha,
        spec_sha,
        expected_bindings,
        reasons,
        checks,
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_WRITER_PARTICIPATION_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_coordination_receipt_sha256": coordination_sha,
        "participation_spec_sha256": spec_sha,
        "participation_bundle_sha256": bundle_sha,
        "writer_count": 19,
        "all_registration_tokens_valid": True,
        "all_normal_cycles_valid": True,
        "all_maintenance_cycles_valid": True,
        "runtime_install_allowed": False,
        "production_ready": False,
        "apply_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["participation_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "participation_contract_verified": True,
            "synthetic_participants_valid": True,
            "production_ready": False,
            "translation_allowed": False,
            "apply_allowed": False,
            "runtime_install_allowed": False,
            "status": "CLOSED_REPAIR_WRITER_PARTICIPATION_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "participation_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_CONTRACT_V1_VERSION",
    "canonical_writer_participation_bindings_v1",
    "evaluate_closed_repair_writer_participation_offline_v1",
    "writer_participant_receipt_sha256_v1",
    "writer_participation_bundle_sha256_v1",
    "writer_participation_spec_sha256_v1",
]
