"""Dormant production-shaped backend boundary for C3 CLOSED repair.

This module is an offline contract projection only.  It separates the
temporary upstream capability from a future production-shaped capability,
binds an invocation to a live synthetic maintenance lease and a deadline,
normalizes synthetic terminal receipts, and models recovery under a fresh
lease.  It has no backend, store, filesystem, network, or runtime call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-BOUNDARY-CONTRACT-V1"
)

OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_BACKEND_BOUNDARY_OFFLINE_ONLY_V1"
)
PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_CONTRACT_ONLY_V1"
)
PRODUCTION_BACKEND_INVOCATION_COMMAND_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_INVOCATION_COMMAND_CONTRACT_ONLY_V1"
)
PRODUCTION_BACKEND_TERMINAL_RECEIPT_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_SYNTHETIC_V1"
)
PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_GRANT_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_GRANT_SYNTHETIC_V1"
)
PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1 = (
    "RECONCILE_C3_PRODUCTION_TRANSACTION_ONCE"
)
PRODUCTION_BACKEND_RECOVERY_COMMAND_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_RECOVERY_COMMAND_CONTRACT_ONLY_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKEND_LABEL_RE = re.compile(r"^[A-Z0-9_.:-]{1,160}$")
_BOUNDARY_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version",
        "backend_instance_sha256",
        "backend_kind",
        "registry_path_binding_sha256",
        "lock_namespace_sha256",
        "upstream_synthetic_capability_attestation_sha256",
        "production_backend_capability_attestation_sha256",
        "storage_scope",
        "request_schema_version",
        "result_schema_version",
        "recovery_request_schema_version",
        "recovery_supported",
        "synthetic_contract_only",
        "production_backend_referenced",
        "production_authority",
        "attestation_sha256",
    }
)
_MAINTENANCE_ATTESTATION_KEYS = frozenset(
    {
        "state",
        "maintenance_epoch",
        "lock_namespace_sha256",
        "registered_writer_count",
        "inflight_mutations",
        "shared_lock_acquired",
        "expires_at_epoch",
    }
)
_INVOCATION_COMMAND_KEYS = frozenset(
    {
        "command_version",
        "scope_attestation",
        "envelope_sha256",
        "request_sha256",
        "transaction_sha256",
        "idempotency_key",
        "backend_boundary_attestation",
        "backend_boundary_attestation_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "upstream_synthetic_capability_attestation_sha256",
        "production_backend_capability_attestation_sha256",
        "maintenance_attestation",
        "deadline_epoch",
        "production_request",
        "synthetic_contract_only",
        "production_authority",
        "backend_call_allowed",
        "command_sha256",
    }
)
_TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "execution_scope",
        "command_sha256",
        "request_sha256",
        "transaction_sha256",
        "backend_boundary_attestation_sha256",
        "backend_instance_sha256",
        "authorization_consumption_receipt_sha256",
        "maintenance_epoch",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "terminal_state",
        "prepared_record_sha256",
        "terminal_record_sha256",
        "postconditions_verified",
        "recovery_required",
        "ambiguous",
        "idempotent_replay",
        "deadline_epoch",
        "deadline_observed",
        "production_evidence",
        "write_executed",
        "registry_write",
        "receipt_sha256",
    }
)
_RECOVERY_GRANT_KEYS = frozenset(
    {
        "grant_version",
        "authorized_action",
        "subject_binding_sha256",
        "max_consumption_count",
        "issued_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "production_signature_verified",
        "production_authority",
        "grant_sha256",
    }
)
_RECOVERY_CONSUMPTION_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "grant_sha256",
        "subject_binding_sha256",
        "authorized_action",
        "consumption_count",
        "consumed_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "production_authority",
        "receipt_sha256",
    }
)
_RECOVERY_COMMAND_KEYS = frozenset(
    {
        "command_version",
        "scope_attestation",
        "original_invocation_command_sha256",
        "original_request_sha256",
        "transaction_sha256",
        "backend_boundary_attestation",
        "backend_boundary_attestation_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "upstream_synthetic_capability_attestation_sha256",
        "production_backend_capability_attestation_sha256",
        "original_authorization_consumption_receipt_sha256",
        "recovery_request",
        "recovery_request_sha256",
        "recovery_authorization_grant_sha256",
        "recovery_authorization_subject_binding_sha256",
        "recovery_authorization_consumption_receipt",
        "recovery_authorization_consumption_receipt_sha256",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "previous_maintenance_epoch",
        "fresh_maintenance_attestation",
        "recovery_policy",
        "deadline_epoch",
        "synthetic_contract_only",
        "production_authority",
        "backend_call_allowed",
        "command_sha256",
    }
)

_PRODUCTION_BLOCKERS = (
    "BOUNDARY_IS_AN_OFFLINE_CONTRACT_ONLY",
    "UPSTREAM_CAPABILITY_IS_SYNTHETIC_TEMPORARY_TEST",
    "PRODUCTION_CAPABILITY_IS_HASH_ONLY",
    "PRODUCTION_BACKEND_IS_NOT_REFERENCED",
    "AUTHORIZATION_CONSUMPTION_IS_MEMORY_ONLY",
    "TERMINAL_RECEIPTS_ARE_SYNTHETIC_ONLY",
    "BACKEND_STORE_IS_NOT_CALLED",
    "RUNTIME_IS_NOT_INTEGRATED",
    "LIVE_TRADING_REMAINS_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _hash_without(value: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: item for key, item in value.items() if key != field_name}
    )


def production_backend_boundary_attestation_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("boundary attestation must be a mapping")
    return _hash_without(value, "attestation_sha256")


def production_backend_invocation_command_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("invocation command must be a mapping")
    return _hash_without(value, "command_sha256")


def production_backend_terminal_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("terminal receipt must be a mapping")
    return _hash_without(value, "receipt_sha256")


def production_backend_recovery_grant_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("recovery grant must be a mapping")
    return _hash_without(value, "grant_sha256")


def production_backend_recovery_command_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("recovery command must be a mapping")
    return _hash_without(value, "command_sha256")


@dataclass(frozen=True)
class DormantProductionBackendBoundaryConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_deadline_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_deadline_seconds <= 300:
            raise ValueError("max_deadline_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedProductionBackendInvocationCommandV1:
    request_sha256: str = field(repr=False)
    transaction_sha256: str = field(repr=False)
    backend_boundary_attestation_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    deadline_epoch: int = field(repr=False)
    command: Mapping[str, Any] = field(repr=False)
    command_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionBackendInvocationCommandV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedProductionBackendRecoveryCommandV1:
    original_request_sha256: str = field(repr=False)
    transaction_sha256: str = field(repr=False)
    backend_boundary_attestation_sha256: str = field(repr=False)
    fresh_maintenance_epoch: str = field(repr=False)
    deadline_epoch: int = field(repr=False)
    command: Mapping[str, Any] = field(repr=False)
    command_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionBackendRecoveryCommandV1(<protected>)"


class InMemorySyntheticRecoveryAuthorizationLedgerV1:
    """One-shot recovery authorization ledger with no durable authority."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, str] = {}

    def consume_once(
        self,
        grant: Mapping[str, Any],
        *,
        subject_binding_sha256: str,
        now_epoch: int,
    ) -> dict[str, Any] | None:
        grant_sha = _valid_sha256(grant.get("grant_sha256"))
        if not grant_sha or grant.get("subject_binding_sha256") != subject_binding_sha256:
            return None
        with self._lock:
            if grant_sha in self._records:
                return None
            receipt = {
                "receipt_version": "C3_SYNTHETIC_RECOVERY_AUTHORIZATION_CONSUMPTION_RECEIPT_V1",
                "grant_sha256": grant_sha,
                "subject_binding_sha256": subject_binding_sha256,
                "authorized_action": PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1,
                "consumption_count": 1,
                "consumed_at_epoch": now_epoch,
                "expires_at_epoch": grant["expires_at_epoch"],
                "synthetic_only": True,
                "production_authority": False,
            }
            receipt["receipt_sha256"] = _hash_without(receipt, "receipt_sha256")
            self._records[grant_sha] = receipt["receipt_sha256"]
            return receipt

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "record_count": len(self._records),
                "durable": False,
                "synthetic_only": True,
                "production_authority": False,
            }


def _maintenance_attestation(
    permit: coordinator.WriterMaintenancePermitV1,
    deadline_epoch: int,
) -> dict[str, Any]:
    return {
        "state": permit.state,
        "maintenance_epoch": permit.maintenance_epoch,
        "lock_namespace_sha256": permit.lock_namespace_sha256,
        "registered_writer_count": permit.registered_writer_count,
        "inflight_mutations": permit.inflight_mutations,
        "shared_lock_acquired": permit.shared_lock_acquired,
        "expires_at_epoch": deadline_epoch,
    }


def _maintenance_attestation_valid(
    value: Any,
    *,
    expected_epoch: str,
    deadline_epoch: int,
) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value) == _MAINTENANCE_ATTESTATION_KEYS
        and value.get("state") == "QUIESCED"
        and value.get("maintenance_epoch") == expected_epoch
        and value.get("lock_namespace_sha256")
        == coordinator.canonical_runtime_lock_namespace_v1()
        and value.get("registered_writer_count") == 19
        and value.get("inflight_mutations") == 0
        and value.get("shared_lock_acquired") is True
        and value.get("expires_at_epoch") == deadline_epoch
    )


def build_production_backend_boundary_attestation_offline_v1(
    envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
    *,
    backend_kind: str,
    production_backend_capability_attestation_sha256: str,
) -> dict[str, Any]:
    valid, request = envelope_contract._protected_request_valid(envelope)
    production_sha = _valid_sha256(
        production_backend_capability_attestation_sha256
    )
    normalized_kind = str(backend_kind or "").upper().strip()
    if not (
        valid
        and request is not None
        and production_sha
        and production_sha != request["backend_capability_attestation_sha256"]
        and _BACKEND_LABEL_RE.fullmatch(normalized_kind)
    ):
        raise ValueError("separate production-shaped capability required")
    attestation = {
        "attestation_version": PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_VERSION_V1,
        "backend_instance_sha256": request["backend_instance_sha256"],
        "backend_kind": normalized_kind,
        "registry_path_binding_sha256": request["registry_path_binding_sha256"],
        "lock_namespace_sha256": request["lock_namespace_sha256"],
        "upstream_synthetic_capability_attestation_sha256": request[
            "backend_capability_attestation_sha256"
        ],
        "production_backend_capability_attestation_sha256": production_sha,
        "storage_scope": "EXPLICIT_PRODUCTION",
        "request_schema_version": envelope_contract.PRODUCTION_REQUEST_VERSION_V1,
        "result_schema_version": envelope_contract.PRODUCTION_RESULT_VERSION_V1,
        "recovery_request_schema_version": envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1,
        "recovery_supported": True,
        "synthetic_contract_only": True,
        "production_backend_referenced": False,
        "production_authority": False,
    }
    attestation["attestation_sha256"] = (
        production_backend_boundary_attestation_sha256_v1(attestation)
    )
    return attestation


def _boundary_attestation_valid(
    value: Any,
    request: Mapping[str, Any],
) -> bool:
    if not isinstance(value, Mapping) or set(value) != _BOUNDARY_ATTESTATION_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("attestation_sha256"))
    upstream_sha = request.get("backend_capability_attestation_sha256")
    production_sha = _valid_sha256(
        value.get("production_backend_capability_attestation_sha256")
    )
    try:
        return bool(
            value.get("attestation_version")
            == PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_VERSION_V1
            and value.get("backend_instance_sha256")
            == request.get("backend_instance_sha256")
            and _BACKEND_LABEL_RE.fullmatch(str(value.get("backend_kind") or ""))
            and value.get("registry_path_binding_sha256")
            == request.get("registry_path_binding_sha256")
            and value.get("lock_namespace_sha256")
            == request.get("lock_namespace_sha256")
            == coordinator.canonical_runtime_lock_namespace_v1()
            and value.get("upstream_synthetic_capability_attestation_sha256")
            == upstream_sha
            and production_sha
            and production_sha != upstream_sha
            and value.get("storage_scope") == "EXPLICIT_PRODUCTION"
            and value.get("request_schema_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and value.get("result_schema_version")
            == envelope_contract.PRODUCTION_RESULT_VERSION_V1
            and value.get("recovery_request_schema_version")
            == envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1
            and value.get("recovery_supported") is True
            and value.get("synthetic_contract_only") is True
            and value.get("production_backend_referenced") is False
            and value.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                production_backend_boundary_attestation_sha256_v1(value),
            )
        )
    except Exception:
        return False


def _invocation_command_valid(
    value: Any,
) -> tuple[bool, Mapping[str, Any] | None]:
    if type(value) is not ProtectedProductionBackendInvocationCommandV1:
        return False, None
    try:
        command = _canonical_copy(dict(value.command))
        request = command.get("production_request")
        boundary_attestation = command.get("backend_boundary_attestation")
        valid = bool(
            set(command) == _INVOCATION_COMMAND_KEYS
            and command.get("command_version")
            == PRODUCTION_BACKEND_INVOCATION_COMMAND_VERSION_V1
            and command.get("scope_attestation")
            == OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1
            and command.get("request_sha256") == value.request_sha256
            and command.get("transaction_sha256") == value.transaction_sha256
            and command.get("backend_boundary_attestation_sha256")
            == value.backend_boundary_attestation_sha256
            and command.get("backend_instance_sha256")
            == value.backend_instance_sha256
            and command.get("deadline_epoch") == value.deadline_epoch
            and isinstance(request, Mapping)
            and set(request) == envelope_contract._PRODUCTION_REQUEST_KEYS
            and request.get("request_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and request.get("request_sha256")
            == envelope_contract.production_request_sha256_v1(request)
            and request.get("request_sha256") == value.request_sha256
            and request.get("transaction_sha256") == value.transaction_sha256
            and request.get("backend_instance_sha256")
            == value.backend_instance_sha256
            and command.get("idempotency_key") == request.get("idempotency_key")
            and command.get("registry_path_binding_sha256")
            == request.get("registry_path_binding_sha256")
            and _boundary_attestation_valid(boundary_attestation, request)
            and boundary_attestation.get("attestation_sha256")
            == command.get("backend_boundary_attestation_sha256")
            and command.get(
                "upstream_synthetic_capability_attestation_sha256"
            )
            == request.get("backend_capability_attestation_sha256")
            and _valid_sha256(
                command.get("production_backend_capability_attestation_sha256")
            )
            and command.get("production_backend_capability_attestation_sha256")
            != request.get("backend_capability_attestation_sha256")
            and request.get("expires_at_epoch") >= value.deadline_epoch
            and _maintenance_attestation_valid(
                command.get("maintenance_attestation"),
                expected_epoch=request.get("maintenance_epoch"),
                deadline_epoch=value.deadline_epoch,
            )
            and command.get("synthetic_contract_only") is True
            and command.get("production_authority") is False
            and command.get("backend_call_allowed") is False
            and command.get("command_sha256")
            == production_backend_invocation_command_sha256_v1(command)
            and value.command_sha256 == command["command_sha256"]
        )
    except Exception:
        return False, None
    return valid, command if valid else None


def _recovery_envelope_valid(
    recovery: Any,
    envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
) -> tuple[bool, Mapping[str, Any] | None]:
    if type(recovery) is not envelope_contract.ProtectedProductionRecoveryEnvelopeV1:
        return False, None
    envelope_valid, original = envelope_contract._protected_request_valid(envelope)
    try:
        request = _canonical_copy(dict(recovery.request))
        valid = bool(
            envelope_valid
            and original is not None
            and set(request) == envelope_contract._RECOVERY_REQUEST_KEYS
            and request.get("recovery_request_sha256")
            == envelope_contract.recovery_request_sha256_v1(request)
            and request.get("original_request_sha256")
            == original.get("request_sha256")
            and request.get("transaction_sha256")
            == original.get("transaction_sha256")
            and request.get("backend_instance_sha256")
            == original.get("backend_instance_sha256")
            and request.get("registry_path_binding_sha256")
            == original.get("registry_path_binding_sha256")
            and request.get("authorization_consumption_receipt_sha256")
            == original.get("authorization_consumption_receipt_sha256")
            and request.get("source_raw_document_sha256")
            == original.get("expected_raw_document_sha256")
            and request.get("candidate_raw_document_sha256")
            == original.get("candidate_raw_document_sha256")
            and request.get("previous_maintenance_epoch")
            == original.get("maintenance_epoch")
            and _valid_sha256(request.get("fresh_maintenance_epoch"))
            and request.get("fresh_maintenance_epoch")
            != original.get("maintenance_epoch")
            and request.get("synthetic_only") is True
            and request.get("production_authority") is False
            and recovery.original_request_sha256
            == request.get("original_request_sha256")
            and recovery.transaction_sha256 == request.get("transaction_sha256")
            and recovery.backend_instance_sha256
            == request.get("backend_instance_sha256")
            and recovery.fresh_maintenance_epoch
            == request.get("fresh_maintenance_epoch")
            and recovery.expires_at_epoch == request.get("expires_at_epoch")
            and recovery.envelope_sha256
            == _stable_sha256(
                {
                    "original_request_sha256": recovery.original_request_sha256,
                    "transaction_sha256": recovery.transaction_sha256,
                    "backend_instance_sha256": recovery.backend_instance_sha256,
                    "fresh_maintenance_epoch": recovery.fresh_maintenance_epoch,
                    "expires_at_epoch": recovery.expires_at_epoch,
                    "recovery_request_sha256": request[
                        "recovery_request_sha256"
                    ],
                }
            )
        )
    except Exception:
        return False, None
    return valid, request if valid else None


def _recovery_subject_sha256(
    invocation_command: Mapping[str, Any],
    recovery_request: Mapping[str, Any],
    boundary_attestation: Mapping[str, Any],
) -> str:
    return _stable_sha256(
        {
            "original_invocation_command_sha256": invocation_command[
                "command_sha256"
            ],
            "original_request_sha256": recovery_request[
                "original_request_sha256"
            ],
            "transaction_sha256": recovery_request["transaction_sha256"],
            "recovery_request_sha256": recovery_request[
                "recovery_request_sha256"
            ],
            "backend_boundary_attestation_sha256": boundary_attestation[
                "attestation_sha256"
            ],
            "fresh_maintenance_epoch": recovery_request[
                "fresh_maintenance_epoch"
            ],
            "expires_at_epoch": recovery_request["expires_at_epoch"],
        }
    )


def build_synthetic_recovery_authorization_grant_v1(
    invocation_command: ProtectedProductionBackendInvocationCommandV1,
    recovery: envelope_contract.ProtectedProductionRecoveryEnvelopeV1,
    envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
    boundary_attestation: Mapping[str, Any],
    *,
    issued_at_epoch: int,
    expires_at_epoch: int,
) -> dict[str, Any]:
    command_valid, command = _invocation_command_valid(invocation_command)
    recovery_valid, recovery_request = _recovery_envelope_valid(recovery, envelope)
    envelope_valid, original_request = envelope_contract._protected_request_valid(
        envelope
    )
    if not (
        command_valid
        and command is not None
        and recovery_valid
        and recovery_request is not None
        and envelope_valid
        and original_request is not None
        and _boundary_attestation_valid(boundary_attestation, original_request)
        and command["backend_boundary_attestation_sha256"]
        == boundary_attestation["attestation_sha256"]
        and type(issued_at_epoch) is int
        and type(expires_at_epoch) is int
        and issued_at_epoch < expires_at_epoch <= recovery.expires_at_epoch
    ):
        raise ValueError("valid synthetic recovery authorization inputs required")
    grant = {
        "grant_version": PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_GRANT_VERSION_V1,
        "authorized_action": PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1,
        "subject_binding_sha256": _recovery_subject_sha256(
            command, recovery_request, boundary_attestation
        ),
        "max_consumption_count": 1,
        "issued_at_epoch": issued_at_epoch,
        "expires_at_epoch": expires_at_epoch,
        "synthetic_only": True,
        "production_signature_verified": False,
        "production_authority": False,
    }
    grant["grant_sha256"] = production_backend_recovery_grant_sha256_v1(grant)
    return grant


def _recovery_grant_valid(
    grant: Any,
    *,
    subject_binding_sha256: str,
    now_epoch: int,
    deadline_epoch: int,
    max_ttl_seconds: int,
) -> bool:
    if not isinstance(grant, Mapping) or set(grant) != _RECOVERY_GRANT_KEYS:
        return False
    supplied_sha = _valid_sha256(grant.get("grant_sha256"))
    try:
        return bool(
            grant.get("grant_version")
            == PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_GRANT_VERSION_V1
            and grant.get("authorized_action")
            == PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1
            and grant.get("subject_binding_sha256") == subject_binding_sha256
            and grant.get("max_consumption_count") == 1
            and type(grant.get("issued_at_epoch")) is int
            and type(grant.get("expires_at_epoch")) is int
            and grant["issued_at_epoch"] <= now_epoch
            and now_epoch < grant["expires_at_epoch"] <= deadline_epoch
            and 0
            < grant["expires_at_epoch"] - grant["issued_at_epoch"]
            <= max_ttl_seconds
            and grant.get("synthetic_only") is True
            and grant.get("production_signature_verified") is False
            and grant.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                production_backend_recovery_grant_sha256_v1(grant),
            )
        )
    except Exception:
        return False


def _recovery_consumption_valid(
    receipt: Any,
    *,
    grant_sha256: str,
    subject_binding_sha256: str,
) -> bool:
    return bool(
        isinstance(receipt, Mapping)
        and set(receipt) == _RECOVERY_CONSUMPTION_RECEIPT_KEYS
        and receipt.get("receipt_version")
        == "C3_SYNTHETIC_RECOVERY_AUTHORIZATION_CONSUMPTION_RECEIPT_V1"
        and receipt.get("grant_sha256") == grant_sha256
        and receipt.get("subject_binding_sha256") == subject_binding_sha256
        and receipt.get("authorized_action")
        == PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1
        and receipt.get("consumption_count") == 1
        and receipt.get("synthetic_only") is True
        and receipt.get("production_authority") is False
        and receipt.get("receipt_sha256")
        == _hash_without(receipt, "receipt_sha256")
    )


def _recovery_command_valid(
    value: Any,
) -> tuple[bool, Mapping[str, Any] | None]:
    if type(value) is not ProtectedProductionBackendRecoveryCommandV1:
        return False, None
    try:
        command = _canonical_copy(dict(value.command))
        maintenance = command.get("fresh_maintenance_attestation")
        recovery_request = command.get("recovery_request")
        boundary_attestation = command.get("backend_boundary_attestation")
        recovery_consumption = command.get(
            "recovery_authorization_consumption_receipt"
        )
        boundary_request_view = {
            "backend_instance_sha256": command.get("backend_instance_sha256"),
            "registry_path_binding_sha256": command.get(
                "registry_path_binding_sha256"
            ),
            "lock_namespace_sha256": coordinator.canonical_runtime_lock_namespace_v1(),
            "backend_capability_attestation_sha256": command.get(
                "upstream_synthetic_capability_attestation_sha256"
            ),
        }
        valid = bool(
            set(command) == _RECOVERY_COMMAND_KEYS
            and command.get("command_version")
            == PRODUCTION_BACKEND_RECOVERY_COMMAND_VERSION_V1
            and command.get("scope_attestation")
            == OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1
            and command.get("original_request_sha256")
            == value.original_request_sha256
            and command.get("transaction_sha256") == value.transaction_sha256
            and command.get("backend_boundary_attestation_sha256")
            == value.backend_boundary_attestation_sha256
            and _boundary_attestation_valid(
                boundary_attestation, boundary_request_view
            )
            and boundary_attestation.get("attestation_sha256")
            == command.get("backend_boundary_attestation_sha256")
            and command.get("fresh_maintenance_attestation", {}).get(
                "maintenance_epoch"
            )
            == value.fresh_maintenance_epoch
            and command.get("deadline_epoch") == value.deadline_epoch
            and _valid_sha256(
                command.get("upstream_synthetic_capability_attestation_sha256")
            )
            and _valid_sha256(
                command.get("production_backend_capability_attestation_sha256")
            )
            and command.get("upstream_synthetic_capability_attestation_sha256")
            != command.get("production_backend_capability_attestation_sha256")
            and isinstance(recovery_request, Mapping)
            and set(recovery_request) == envelope_contract._RECOVERY_REQUEST_KEYS
            and recovery_request.get("recovery_request_sha256")
            == envelope_contract.recovery_request_sha256_v1(recovery_request)
            and recovery_request.get("recovery_request_sha256")
            == command.get("recovery_request_sha256")
            and recovery_request.get("original_request_sha256")
            == command.get("original_request_sha256")
            and recovery_request.get("transaction_sha256")
            == command.get("transaction_sha256")
            and recovery_request.get("backend_instance_sha256")
            == command.get("backend_instance_sha256")
            and recovery_request.get("registry_path_binding_sha256")
            == command.get("registry_path_binding_sha256")
            and recovery_request.get("source_raw_document_sha256")
            == command.get("source_raw_document_sha256")
            and recovery_request.get("candidate_raw_document_sha256")
            == command.get("candidate_raw_document_sha256")
            and recovery_request.get("previous_maintenance_epoch")
            == command.get("previous_maintenance_epoch")
            and recovery_request.get("fresh_maintenance_epoch")
            == value.fresh_maintenance_epoch
            and recovery_request.get("recovery_policy")
            == command.get("recovery_policy")
            and recovery_request.get("expires_at_epoch")
            == command.get("deadline_epoch")
            and _recovery_consumption_valid(
                recovery_consumption,
                grant_sha256=command.get("recovery_authorization_grant_sha256"),
                subject_binding_sha256=command.get(
                    "recovery_authorization_subject_binding_sha256"
                ),
            )
            and recovery_consumption.get("receipt_sha256")
            == command.get(
                "recovery_authorization_consumption_receipt_sha256"
            )
            and _maintenance_attestation_valid(
                maintenance,
                expected_epoch=value.fresh_maintenance_epoch,
                deadline_epoch=value.deadline_epoch,
            )
            and command.get("synthetic_contract_only") is True
            and command.get("production_authority") is False
            and command.get("backend_call_allowed") is False
            and command.get("command_sha256")
            == production_backend_recovery_command_sha256_v1(command)
            and value.command_sha256 == command["command_sha256"]
        )
    except Exception:
        return False, None
    return valid, command if valid else None


class DormantProductionBackendBoundaryV1:
    def __init__(
        self,
        *,
        config: DormantProductionBackendBoundaryConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_witness: consumer.InMemoryLiveMaintenanceLeaseWitnessV1 | None = None,
        recovery_authorization_ledger: InMemorySyntheticRecoveryAuthorizationLedgerV1
        | None = None,
    ) -> None:
        self._config = config or DormantProductionBackendBoundaryConfigV1()
        self._clock = clock
        self._lease_witness = lease_witness
        self._recovery_ledger = recovery_authorization_ledger

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_BACKEND_BOUNDARY_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_contract_only": True,
            "upstream_capability_verified_synthetic": False,
            "production_capability_separated": False,
            "same_live_lease_verified_synthetic": False,
            "deadline_verified_synthetic": False,
            "invocation_command_projected": False,
            "terminal_contract_normalized": False,
            "recovery_command_projected": False,
            "recovery_authorization_consumed_once_synthetic": False,
            "production_authority": False,
            "backend_referenced": False,
            "backend_called": False,
            "production_store_called": False,
            "runtime_integrated": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "reasons": [],
            "protected_invocation_command": None,
            "protected_recovery_command": None,
            "terminal_result": None,
            "recovery_authorization_consumption_receipt": None,
        }

    def _enabled_now(self, result: dict[str, Any]) -> int | None:
        reasons = result["reasons"]
        if self._config.enabled is not True:
            reasons.append("PRODUCTION_BACKEND_BOUNDARY_DEFAULT_OFF")
            return None
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1
        ):
            reasons.append("PRODUCTION_BACKEND_BOUNDARY_OFFLINE_SCOPE_REQUIRED")
            return None
        if (
            type(self._lease_witness)
            is not consumer.InMemoryLiveMaintenanceLeaseWitnessV1
            or type(self._recovery_ledger)
            is not InMemorySyntheticRecoveryAuthorizationLedgerV1
        ):
            reasons.append("EXACT_SYNTHETIC_BOUNDARY_DEPENDENCIES_REQUIRED")
            return None
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            reasons.append("PRODUCTION_BACKEND_BOUNDARY_CLOCK_INVALID")
            return None
        return now_epoch

    def project_invocation_offline(
        self,
        *,
        envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
        backend_boundary_attestation: Mapping[str, Any],
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
    ) -> dict[str, Any]:
        result = self._base()
        now_epoch = self._enabled_now(result)
        if now_epoch is None:
            return result
        envelope_valid, request = envelope_contract._protected_request_valid(envelope)
        if not envelope_valid or request is None:
            result["reasons"].append("PRODUCTION_INVOCATION_ENVELOPE_INVALID")
            return result
        result["upstream_capability_verified_synthetic"] = True
        if not _boundary_attestation_valid(backend_boundary_attestation, request):
            result["reasons"].append("PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_INVALID")
            return result
        result["production_capability_separated"] = True
        if not (
            self._lease_witness.validate_live(
                maintenance_permit,
                live_lease_token,
                now_epoch=now_epoch,
            )
            and maintenance_permit.maintenance_epoch == request["maintenance_epoch"]
            and maintenance_permit.lock_namespace_sha256
            == request["lock_namespace_sha256"]
        ):
            result["reasons"].append("SAME_LIVE_MAINTENANCE_LEASE_REQUIRED")
            return result
        result["same_live_lease_verified_synthetic"] = True
        deadline = min(
            envelope.expires_at_epoch,
            live_lease_token.expires_at_epoch,
            now_epoch + self._config.max_deadline_seconds,
        )
        if not now_epoch < deadline:
            result["reasons"].append("PRODUCTION_BACKEND_BOUNDARY_DEADLINE_EXPIRED")
            return result
        result["deadline_verified_synthetic"] = True
        maintenance = _maintenance_attestation(maintenance_permit, deadline)
        command = {
            "command_version": PRODUCTION_BACKEND_INVOCATION_COMMAND_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1,
            "envelope_sha256": envelope.envelope_sha256,
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "idempotency_key": request["idempotency_key"],
            "backend_boundary_attestation": _canonical_copy(
                backend_boundary_attestation
            ),
            "backend_boundary_attestation_sha256": backend_boundary_attestation[
                "attestation_sha256"
            ],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "registry_path_binding_sha256": request[
                "registry_path_binding_sha256"
            ],
            "upstream_synthetic_capability_attestation_sha256": request[
                "backend_capability_attestation_sha256"
            ],
            "production_backend_capability_attestation_sha256": (
                backend_boundary_attestation[
                    "production_backend_capability_attestation_sha256"
                ]
            ),
            "maintenance_attestation": maintenance,
            "deadline_epoch": deadline,
            "production_request": _canonical_copy(request),
            "synthetic_contract_only": True,
            "production_authority": False,
            "backend_call_allowed": False,
        }
        command["command_sha256"] = production_backend_invocation_command_sha256_v1(
            command
        )
        protected = ProtectedProductionBackendInvocationCommandV1(
            request_sha256=request["request_sha256"],
            transaction_sha256=request["transaction_sha256"],
            backend_boundary_attestation_sha256=backend_boundary_attestation[
                "attestation_sha256"
            ],
            backend_instance_sha256=request["backend_instance_sha256"],
            deadline_epoch=deadline,
            command=command,
            command_sha256=command["command_sha256"],
        )
        if not _invocation_command_valid(protected)[0]:
            result["reasons"].append("PRODUCTION_BACKEND_INVOCATION_COMMAND_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_INVOCATION_COMMAND_PROJECTED_OFFLINE",
            invocation_command_projected=True,
            protected_invocation_command=protected,
            production_blockers=list(_PRODUCTION_BLOCKERS),
        )
        return result

    def normalize_terminal_receipt_offline(
        self,
        *,
        envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
        invocation_command: ProtectedProductionBackendInvocationCommandV1,
        terminal_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        now_epoch = self._enabled_now(result)
        if now_epoch is None:
            return result
        envelope_valid, request = envelope_contract._protected_request_valid(envelope)
        command_valid, command = _invocation_command_valid(invocation_command)
        if not (
            envelope_valid
            and request is not None
            and command_valid
            and command is not None
            and command["envelope_sha256"] == envelope.envelope_sha256
            and isinstance(terminal_receipt, Mapping)
            and set(terminal_receipt) == _TERMINAL_RECEIPT_KEYS
        ):
            result["reasons"].append("TERMINAL_BOUNDARY_INPUT_INVALID")
            return result
        supplied_sha = _valid_sha256(terminal_receipt.get("receipt_sha256"))
        state = str(terminal_receipt.get("terminal_state") or "")
        ambiguous = state == "AMBIGUOUS"
        valid = bool(
            terminal_receipt.get("receipt_version")
            == PRODUCTION_BACKEND_TERMINAL_RECEIPT_VERSION_V1
            and terminal_receipt.get("execution_scope")
            == "SYNTHETIC_BACKEND_BOUNDARY_EVALUATION"
            and terminal_receipt.get("command_sha256") == command["command_sha256"]
            and terminal_receipt.get("request_sha256") == request["request_sha256"]
            and terminal_receipt.get("transaction_sha256")
            == request["transaction_sha256"]
            and terminal_receipt.get("backend_boundary_attestation_sha256")
            == command["backend_boundary_attestation_sha256"]
            and terminal_receipt.get("backend_instance_sha256")
            == request["backend_instance_sha256"]
            and terminal_receipt.get("authorization_consumption_receipt_sha256")
            == request["authorization_consumption_receipt_sha256"]
            and terminal_receipt.get("maintenance_epoch")
            == request["maintenance_epoch"]
            and terminal_receipt.get("source_raw_document_sha256")
            == request["expected_raw_document_sha256"]
            and terminal_receipt.get("candidate_raw_document_sha256")
            == request["candidate_raw_document_sha256"]
            and state in {"COMMITTED", "ABORTED", "ROLLED_BACK", "AMBIGUOUS"}
            and _valid_sha256(terminal_receipt.get("prepared_record_sha256"))
            and _valid_sha256(terminal_receipt.get("terminal_record_sha256"))
            and terminal_receipt.get("deadline_epoch") == command["deadline_epoch"]
            and terminal_receipt.get("deadline_observed") is True
            and now_epoch < command["deadline_epoch"]
            and type(terminal_receipt.get("idempotent_replay")) is bool
            and terminal_receipt.get("production_evidence") is False
            and terminal_receipt.get("write_executed") is False
            and terminal_receipt.get("registry_write") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                production_backend_terminal_receipt_sha256_v1(terminal_receipt),
            )
            and (
                (
                    state in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
                    and terminal_receipt.get("postconditions_verified") is True
                    and terminal_receipt.get("recovery_required") is False
                    and terminal_receipt.get("ambiguous") is False
                )
                or (
                    ambiguous
                    and terminal_receipt.get("postconditions_verified") is False
                    and terminal_receipt.get("recovery_required") is True
                    and terminal_receipt.get("ambiguous") is True
                )
            )
        )
        if not valid:
            result["reasons"].append("PRODUCTION_BACKEND_TERMINAL_RECEIPT_INVALID")
            return result
        terminal = {
            "result_version": envelope_contract.PRODUCTION_RESULT_VERSION_V1,
            "execution_scope": "SYNTHETIC_CONTRACT_EVALUATION",
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "authorization_consumption_receipt_sha256": request[
                "authorization_consumption_receipt_sha256"
            ],
            "maintenance_epoch": request["maintenance_epoch"],
            "source_raw_document_sha256": request[
                "expected_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": request[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": state,
            "prepared_record_sha256": terminal_receipt["prepared_record_sha256"],
            "terminal_record_sha256": terminal_receipt["terminal_record_sha256"],
            "postconditions_verified": terminal_receipt[
                "postconditions_verified"
            ],
            "recovery_required": terminal_receipt["recovery_required"],
            "ambiguous": terminal_receipt["ambiguous"],
            "idempotent_replay": terminal_receipt["idempotent_replay"],
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        terminal["result_sha256"] = envelope_contract.terminal_result_sha256_v1(
            terminal
        )
        evaluation = envelope_contract.evaluate_terminal_result_contract_offline_v1(
            envelope, terminal
        )
        if evaluation.get("ok") is not True:
            result["reasons"].append("NORMALIZED_TERMINAL_RESULT_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_NORMALIZED_OFFLINE",
            terminal_contract_normalized=True,
            terminal_result=terminal,
            terminal_state=state,
            recovery_required=ambiguous,
            deadline_verified_synthetic=now_epoch <= command["deadline_epoch"],
            production_blockers=list(_PRODUCTION_BLOCKERS),
        )
        return result

    def project_recovery_offline(
        self,
        *,
        envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
        invocation_command: ProtectedProductionBackendInvocationCommandV1,
        recovery_envelope: envelope_contract.ProtectedProductionRecoveryEnvelopeV1,
        ambiguous_terminal_result: Mapping[str, Any],
        backend_boundary_attestation: Mapping[str, Any],
        fresh_maintenance_permit: coordinator.WriterMaintenancePermitV1,
        fresh_live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
        recovery_authorization_grant: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        now_epoch = self._enabled_now(result)
        if now_epoch is None:
            return result
        envelope_valid, request = envelope_contract._protected_request_valid(envelope)
        command_valid, command = _invocation_command_valid(invocation_command)
        recovery_valid, recovery_request = _recovery_envelope_valid(
            recovery_envelope, envelope
        )
        terminal_evaluation = (
            envelope_contract.evaluate_terminal_result_contract_offline_v1(
                envelope, ambiguous_terminal_result
            )
        )
        if not (
            envelope_valid
            and request is not None
            and command_valid
            and command is not None
            and recovery_valid
            and recovery_request is not None
            and terminal_evaluation.get("ok") is True
            and terminal_evaluation.get("terminal_state") == "AMBIGUOUS"
            and command["envelope_sha256"] == envelope.envelope_sha256
            and _boundary_attestation_valid(backend_boundary_attestation, request)
            and command["backend_boundary_attestation_sha256"]
            == backend_boundary_attestation["attestation_sha256"]
        ):
            result["reasons"].append("RECOVERY_BOUNDARY_INPUT_INVALID")
            return result
        if not (
            self._lease_witness.validate_live(
                fresh_maintenance_permit,
                fresh_live_lease_token,
                now_epoch=now_epoch,
            )
            and fresh_maintenance_permit.maintenance_epoch
            == recovery_request["fresh_maintenance_epoch"]
            and fresh_maintenance_permit.maintenance_epoch
            != recovery_request["previous_maintenance_epoch"]
            and fresh_maintenance_permit.lock_namespace_sha256
            == request["lock_namespace_sha256"]
        ):
            result["reasons"].append("FRESH_LIVE_MAINTENANCE_LEASE_REQUIRED")
            return result
        result["same_live_lease_verified_synthetic"] = True
        deadline = min(
            recovery_request["expires_at_epoch"],
            fresh_live_lease_token.expires_at_epoch,
            now_epoch + self._config.max_deadline_seconds,
        )
        if not now_epoch < deadline:
            result["reasons"].append("PRODUCTION_BACKEND_RECOVERY_DEADLINE_EXPIRED")
            return result
        result["deadline_verified_synthetic"] = True
        subject_sha = _recovery_subject_sha256(
            command, recovery_request, backend_boundary_attestation
        )
        if not _recovery_grant_valid(
            recovery_authorization_grant,
            subject_binding_sha256=subject_sha,
            now_epoch=now_epoch,
            deadline_epoch=deadline,
            max_ttl_seconds=self._config.max_deadline_seconds,
        ):
            result["reasons"].append("SYNTHETIC_RECOVERY_AUTHORIZATION_INVALID")
            return result
        consumption = self._recovery_ledger.consume_once(
            recovery_authorization_grant,
            subject_binding_sha256=subject_sha,
            now_epoch=now_epoch,
        )
        if not _recovery_consumption_valid(
            consumption,
            grant_sha256=recovery_authorization_grant["grant_sha256"],
            subject_binding_sha256=subject_sha,
        ):
            result["reasons"].append(
                "RECOVERY_AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID"
            )
            return result
        result["recovery_authorization_consumed_once_synthetic"] = True
        maintenance = _maintenance_attestation(fresh_maintenance_permit, deadline)
        recovery_command = {
            "command_version": PRODUCTION_BACKEND_RECOVERY_COMMAND_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1,
            "original_invocation_command_sha256": command["command_sha256"],
            "original_request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_boundary_attestation": _canonical_copy(
                backend_boundary_attestation
            ),
            "backend_boundary_attestation_sha256": backend_boundary_attestation[
                "attestation_sha256"
            ],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "registry_path_binding_sha256": request[
                "registry_path_binding_sha256"
            ],
            "upstream_synthetic_capability_attestation_sha256": request[
                "backend_capability_attestation_sha256"
            ],
            "production_backend_capability_attestation_sha256": (
                backend_boundary_attestation[
                    "production_backend_capability_attestation_sha256"
                ]
            ),
            "original_authorization_consumption_receipt_sha256": request[
                "authorization_consumption_receipt_sha256"
            ],
            "recovery_request": _canonical_copy(recovery_request),
            "recovery_request_sha256": recovery_request[
                "recovery_request_sha256"
            ],
            "recovery_authorization_grant_sha256": recovery_authorization_grant[
                "grant_sha256"
            ],
            "recovery_authorization_subject_binding_sha256": subject_sha,
            "recovery_authorization_consumption_receipt": _canonical_copy(
                consumption
            ),
            "recovery_authorization_consumption_receipt_sha256": consumption[
                "receipt_sha256"
            ],
            "source_raw_document_sha256": request[
                "expected_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": request[
                "candidate_raw_document_sha256"
            ],
            "previous_maintenance_epoch": request["maintenance_epoch"],
            "fresh_maintenance_attestation": maintenance,
            "recovery_policy": envelope_contract.PRODUCTION_RECOVERY_POLICY_V1,
            "deadline_epoch": deadline,
            "synthetic_contract_only": True,
            "production_authority": False,
            "backend_call_allowed": False,
        }
        recovery_command["command_sha256"] = (
            production_backend_recovery_command_sha256_v1(recovery_command)
        )
        protected = ProtectedProductionBackendRecoveryCommandV1(
            original_request_sha256=request["request_sha256"],
            transaction_sha256=request["transaction_sha256"],
            backend_boundary_attestation_sha256=backend_boundary_attestation[
                "attestation_sha256"
            ],
            fresh_maintenance_epoch=fresh_maintenance_permit.maintenance_epoch,
            deadline_epoch=deadline,
            command=recovery_command,
            command_sha256=recovery_command["command_sha256"],
        )
        valid_command = _recovery_command_valid(protected)[0]
        if not valid_command:
            result["reasons"].append("PRODUCTION_BACKEND_RECOVERY_COMMAND_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_RECOVERY_COMMAND_PROJECTED_OFFLINE",
            recovery_command_projected=True,
            protected_recovery_command=protected,
            recovery_authorization_consumption_receipt=consumption,
            production_blockers=list(_PRODUCTION_BLOCKERS),
        )
        return result


__all__ = [
    "DormantProductionBackendBoundaryConfigV1",
    "DormantProductionBackendBoundaryV1",
    "InMemorySyntheticRecoveryAuthorizationLedgerV1",
    "OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1",
    "PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_VERSION_V1",
    "PRODUCTION_BACKEND_INVOCATION_COMMAND_VERSION_V1",
    "PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_ACTION_V1",
    "PRODUCTION_BACKEND_RECOVERY_AUTHORIZATION_GRANT_VERSION_V1",
    "PRODUCTION_BACKEND_RECOVERY_COMMAND_VERSION_V1",
    "PRODUCTION_BACKEND_TERMINAL_RECEIPT_VERSION_V1",
    "ProtectedProductionBackendInvocationCommandV1",
    "ProtectedProductionBackendRecoveryCommandV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_CONTRACT_V1_VERSION",
    "build_production_backend_boundary_attestation_offline_v1",
    "build_synthetic_recovery_authorization_grant_v1",
    "production_backend_boundary_attestation_sha256_v1",
    "production_backend_invocation_command_sha256_v1",
    "production_backend_recovery_command_sha256_v1",
    "production_backend_recovery_grant_sha256_v1",
    "production_backend_terminal_receipt_sha256_v1",
]
