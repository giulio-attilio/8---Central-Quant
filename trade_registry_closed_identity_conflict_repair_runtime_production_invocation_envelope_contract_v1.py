"""Production-shaped C3 invocation envelope contract, offline only.

The module defines exact schemas and synthetic one-shot consumption semantics.
It cannot reference a backend, invoke a store, persist data or grant production
authority.  The word ``production`` describes the future interface shape only.
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
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_v1 as invocation_seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-INVOCATION-ENVELOPE-CONTRACT-V1"
)

OFFLINE_PRODUCTION_INVOCATION_ENVELOPE_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_INVOCATION_ENVELOPE_CONTRACT_OFFLINE_ONLY_V1"
)
PRODUCTION_REQUEST_VERSION_V1 = "C3_PRODUCTION_RAW_REGISTRY_TRANSACTION_REQUEST_V1"
PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1 = (
    "C3_PRODUCTION_RAW_REGISTRY_TRANSACTION_REQUEST_CONTRACT_ONLY_V1"
)
PRODUCTION_RESULT_VERSION_V1 = "C3_PRODUCTION_RAW_REGISTRY_TRANSACTION_RESULT_V1"
PRODUCTION_RECOVERY_REQUEST_VERSION_V1 = (
    "C3_PRODUCTION_RAW_REGISTRY_TRANSACTION_RECOVERY_REQUEST_V1"
)
PRODUCTION_RECOVERY_POLICY_V1 = (
    "RECONCILE_UNDER_FRESH_MAINTENANCE_LEASE_BEFORE_RETRY_V1"
)
BACKEND_IDENTITY_ATTESTATION_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_IDENTITY_ATTESTATION_CONTRACT_ONLY_V1"
)
AUTHORIZATION_GRANT_VERSION_V1 = (
    "C3_PRODUCTION_INVOCATION_AUTHORIZATION_GRANT_SYNTHETIC_V1"
)
AUTHORIZATION_ACTION_V1 = "APPLY_C3_CLOSED_IDENTITY_RAW_TRANSACTION_ONCE"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKEND_LABEL_RE = re.compile(r"^[A-Z0-9_.:-]{1,160}$")
_BACKEND_IDENTITY_KEYS = frozenset(
    {
        "attestation_version",
        "backend_instance_sha256",
        "backend_kind",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "storage_scope",
        "request_schema_version",
        "result_schema_version",
        "recovery_supported",
        "synthetic_only",
        "production_backend_referenced",
        "attestation_sha256",
    }
)
_AUTHORIZATION_GRANT_KEYS = frozenset(
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
_AUTHORIZATION_CONSUMPTION_RECEIPT_KEYS = frozenset(
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
_PRODUCTION_REQUEST_KEYS = frozenset(
    {
        "request_version",
        "scope_attestation",
        "subject_binding_sha256",
        "authorization_consumption_receipt_sha256",
        "upstream_raw_transaction_sha256",
        "handoff_transaction_id",
        "idempotency_key",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "expected_raw_document_sha256",
        "expected_generation_token",
        "candidate_registry",
        "candidate_raw_document_sha256",
        "expires_at_epoch",
        "recovery_policy",
        "transaction_sha256",
        "request_sha256",
    }
)
_TERMINAL_RESULT_KEYS = frozenset(
    {
        "result_version",
        "execution_scope",
        "request_sha256",
        "transaction_sha256",
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
        "production_evidence",
        "write_executed",
        "registry_write",
        "result_sha256",
    }
)
_RECOVERY_REQUEST_KEYS = frozenset(
    {
        "recovery_request_version",
        "scope_attestation",
        "original_request_sha256",
        "transaction_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "authorization_consumption_receipt_sha256",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "previous_maintenance_epoch",
        "fresh_maintenance_epoch",
        "recovery_policy",
        "expires_at_epoch",
        "synthetic_only",
        "production_authority",
        "recovery_request_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "ENVELOPE_IS_A_CONTRACT_PROJECTION_ONLY",
    "AUTHORIZATION_LEDGER_IS_SYNTHETIC_MEMORY_ONLY",
    "PRODUCTION_SIGNATURE_IS_NOT_VERIFIED",
    "PRODUCTION_AUTHORITY_IS_FALSE",
    "BACKEND_IDENTITY_IS_SYNTHETIC_AND_HASH_ONLY",
    "BACKEND_INSTANCE_IS_NOT_REFERENCED",
    "PRODUCTION_STORE_IS_NOT_INVOKED",
    "PRODUCTION_RESULT_EVIDENCE_IS_NOT_AVAILABLE",
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


def _without_hash(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field_name}


def backend_identity_attestation_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("backend identity attestation must be a mapping")
    return _stable_sha256(_without_hash(value, "attestation_sha256"))


def authorization_grant_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("authorization grant must be a mapping")
    return _stable_sha256(_without_hash(value, "grant_sha256"))


def terminal_result_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("terminal result must be a mapping")
    return _stable_sha256(_without_hash(value, "result_sha256"))


def production_request_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("production request must be a mapping")
    return _stable_sha256(_without_hash(value, "request_sha256"))


def recovery_request_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("recovery request must be a mapping")
    return _stable_sha256(_without_hash(value, "recovery_request_sha256"))


@dataclass(frozen=True)
class DormantProductionInvocationEnvelopeConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_envelope_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_envelope_ttl_seconds <= 300:
            raise ValueError("max_envelope_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedProductionInvocationEnvelopeV1:
    subject_binding_sha256: str = field(repr=False)
    authorization_consumption_receipt_sha256: str = field(repr=False)
    upstream_raw_transaction_sha256: str = field(repr=False)
    production_transaction_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    registry_path_binding_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    request: Mapping[str, Any] = field(repr=False)
    envelope_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionInvocationEnvelopeV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedProductionRecoveryEnvelopeV1:
    original_request_sha256: str = field(repr=False)
    transaction_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    fresh_maintenance_epoch: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    request: Mapping[str, Any] = field(repr=False)
    envelope_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionRecoveryEnvelopeV1(<protected>)"


class InMemorySyntheticAuthorizationConsumptionLedgerV1:
    """One-shot synthetic ledger; consumed grants cannot be replayed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}

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
                "receipt_version": "C3_SYNTHETIC_AUTHORIZATION_CONSUMPTION_RECEIPT_V1",
                "grant_sha256": grant_sha,
                "subject_binding_sha256": subject_binding_sha256,
                "authorized_action": AUTHORIZATION_ACTION_V1,
                "consumption_count": 1,
                "consumed_at_epoch": now_epoch,
                "expires_at_epoch": grant["expires_at_epoch"],
                "synthetic_only": True,
                "production_authority": False,
            }
            receipt["receipt_sha256"] = _stable_sha256(receipt)
            self._records[grant_sha] = {
                "state": "CONSUMED",
                "receipt_sha256": receipt["receipt_sha256"],
            }
            return receipt

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "record_count": len(self._records),
                "states": {
                    "CONSUMED": sum(
                        1
                        for record in self._records.values()
                        if record.get("state") == "CONSUMED"
                    )
                },
                "durable": False,
                "synthetic_only": True,
                "production_authority": False,
            }


def _backend_identity_valid(
    value: Any,
    upstream_capability_sha256: str,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != _BACKEND_IDENTITY_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("attestation_sha256"))
    try:
        return bool(
            value.get("attestation_version")
            == BACKEND_IDENTITY_ATTESTATION_VERSION_V1
            and _valid_sha256(value.get("backend_instance_sha256"))
            and _BACKEND_LABEL_RE.fullmatch(str(value.get("backend_kind") or ""))
            and _valid_sha256(value.get("registry_path_binding_sha256"))
            and value.get("backend_capability_attestation_sha256")
            == upstream_capability_sha256
            and value.get("lock_namespace_sha256")
            == coordinator.canonical_runtime_lock_namespace_v1()
            and value.get("storage_scope") == "EXPLICIT_PRODUCTION"
            and value.get("request_schema_version") == PRODUCTION_REQUEST_VERSION_V1
            and value.get("result_schema_version") == PRODUCTION_RESULT_VERSION_V1
            and value.get("recovery_supported") is True
            and value.get("synthetic_only") is True
            and value.get("production_backend_referenced") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                backend_identity_attestation_sha256_v1(value),
            )
        )
    except Exception:
        return False


def _authorization_grant_valid(
    value: Any,
    subject_binding_sha256: str,
    now_epoch: int,
    effective_expiry: int,
    max_ttl: int,
) -> bool:
    if not isinstance(value, Mapping) or set(value) != _AUTHORIZATION_GRANT_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("grant_sha256"))
    try:
        return bool(
            value.get("grant_version") == AUTHORIZATION_GRANT_VERSION_V1
            and value.get("authorized_action") == AUTHORIZATION_ACTION_V1
            and value.get("subject_binding_sha256") == subject_binding_sha256
            and value.get("max_consumption_count") == 1
            and type(value.get("issued_at_epoch")) is int
            and type(value.get("expires_at_epoch")) is int
            and value["issued_at_epoch"] <= now_epoch
            and now_epoch < value["expires_at_epoch"] <= effective_expiry
            and 0 < value["expires_at_epoch"] - value["issued_at_epoch"] <= max_ttl
            and value.get("synthetic_only") is True
            and value.get("production_signature_verified") is False
            and value.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(supplied_sha, authorization_grant_sha256_v1(value))
        )
    except Exception:
        return False


def _consumption_receipt_valid(
    value: Any,
    grant_sha256: str,
    subject_binding_sha256: str,
) -> bool:
    if (
        not isinstance(value, Mapping)
        or set(value) != _AUTHORIZATION_CONSUMPTION_RECEIPT_KEYS
    ):
        return False
    supplied_sha = _valid_sha256(value.get("receipt_sha256"))
    return bool(
        value.get("receipt_version")
        == "C3_SYNTHETIC_AUTHORIZATION_CONSUMPTION_RECEIPT_V1"
        and value.get("grant_sha256") == grant_sha256
        and value.get("subject_binding_sha256") == subject_binding_sha256
        and value.get("authorized_action") == AUTHORIZATION_ACTION_V1
        and value.get("consumption_count") == 1
        and value.get("synthetic_only") is True
        and value.get("production_authority") is False
        and supplied_sha
        and supplied_sha == _stable_sha256(_without_hash(value, "receipt_sha256"))
    )


def _protected_request_valid(
    envelope: Any,
) -> tuple[bool, Mapping[str, Any] | None]:
    if type(envelope) is not ProtectedProductionInvocationEnvelopeV1:
        return False, None
    try:
        request = _canonical_copy(dict(envelope.request))
        valid = bool(
            set(request) == _PRODUCTION_REQUEST_KEYS
            and request.get("request_version") == PRODUCTION_REQUEST_VERSION_V1
            and request.get("scope_attestation")
            == PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1
            and request.get("subject_binding_sha256")
            == envelope.subject_binding_sha256
            and request.get("authorization_consumption_receipt_sha256")
            == envelope.authorization_consumption_receipt_sha256
            and request.get("upstream_raw_transaction_sha256")
            == envelope.upstream_raw_transaction_sha256
            and request.get("transaction_sha256")
            == envelope.production_transaction_sha256
            and request.get("backend_instance_sha256")
            == envelope.backend_instance_sha256
            and request.get("registry_path_binding_sha256")
            == envelope.registry_path_binding_sha256
            and request.get("expires_at_epoch") == envelope.expires_at_epoch
            and request.get("recovery_policy") == PRODUCTION_RECOVERY_POLICY_V1
            and request.get("request_sha256") == production_request_sha256_v1(request)
            and envelope.envelope_sha256
            == _stable_sha256(
                {
                    "subject_binding_sha256": envelope.subject_binding_sha256,
                    "authorization_consumption_receipt_sha256": envelope.authorization_consumption_receipt_sha256,
                    "upstream_raw_transaction_sha256": envelope.upstream_raw_transaction_sha256,
                    "production_transaction_sha256": envelope.production_transaction_sha256,
                    "backend_instance_sha256": envelope.backend_instance_sha256,
                    "registry_path_binding_sha256": envelope.registry_path_binding_sha256,
                    "expires_at_epoch": envelope.expires_at_epoch,
                    "request_sha256": request["request_sha256"],
                }
            )
        )
    except Exception:
        return False, None
    return valid, request if valid else None


class DormantProductionInvocationEnvelopeBuilderV1:
    def __init__(
        self,
        *,
        config: DormantProductionInvocationEnvelopeConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_witness: consumer.InMemoryLiveMaintenanceLeaseWitnessV1 | None = None,
        authorization_ledger: InMemorySyntheticAuthorizationConsumptionLedgerV1
        | None = None,
    ) -> None:
        self._config = config or DormantProductionInvocationEnvelopeConfigV1()
        self._clock = clock
        self._lease_witness = lease_witness
        self._ledger = authorization_ledger

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_INVOCATION_ENVELOPE_CONTRACT_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "upstream_chain_verified": False,
            "same_live_lease_verified_synthetic": False,
            "backend_identity_verified_synthetic": False,
            "authorization_grant_verified_synthetic": False,
            "authorization_consumed_once_synthetic": False,
            "production_request_projected": False,
            "production_authorization_valid": False,
            "backend_referenced": False,
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
            "protected_envelope": None,
            "authorization_consumption_receipt": None,
            "projection_receipt": None,
        }

    def project_offline(
        self,
        *,
        consumer_result: Mapping[str, Any],
        adapter_result: Mapping[str, Any],
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
        backend_identity_attestation: Mapping[str, Any],
        authorization_grant: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons = result["reasons"]
        if self._config.enabled is not True:
            reasons.append("ENVELOPE_BUILDER_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_INVOCATION_ENVELOPE_SCOPE_ATTESTATION_V1
        ):
            reasons.append("ENVELOPE_BUILDER_OFFLINE_SCOPE_REQUIRED")
            return result
        if (
            type(self._lease_witness)
            is not consumer.InMemoryLiveMaintenanceLeaseWitnessV1
            or type(self._ledger)
            is not InMemorySyntheticAuthorizationConsumptionLedgerV1
        ):
            reasons.append("EXACT_SYNTHETIC_DEPENDENCIES_REQUIRED")
            return result
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            reasons.append("ENVELOPE_BUILDER_CLOCK_INVALID")
            return result
        chain_valid, intent, upstream_request, maintenance = (
            invocation_seam._consumer_result_valid(
                consumer_result,
                adapter_result,
                now_epoch,
            )
        )
        if not chain_valid or intent is None or upstream_request is None or maintenance is None:
            reasons.append("UPSTREAM_PROTECTED_CHAIN_INVALID_OR_EXPIRED")
            return result
        if not self._lease_witness.validate_live(
            maintenance_permit,
            live_lease_token,
            now_epoch=now_epoch,
        ) or not (
            intent.live_lease_token_sha256 == live_lease_token.token_sha256
            and intent.maintenance_epoch == maintenance_permit.maintenance_epoch
            and intent.lock_namespace_sha256
            == maintenance_permit.lock_namespace_sha256
            == coordinator.canonical_runtime_lock_namespace_v1()
        ):
            reasons.append("SAME_LIVE_MAINTENANCE_LEASE_REQUIRED")
            return result
        result["upstream_chain_verified"] = True
        result["same_live_lease_verified_synthetic"] = True

        if not _backend_identity_valid(
            backend_identity_attestation,
            intent.backend_capability_attestation_sha256,
        ):
            reasons.append("BACKEND_IDENTITY_ATTESTATION_INVALID")
            return result
        result["backend_identity_verified_synthetic"] = True
        effective_expiry = min(
            intent.expires_at_epoch,
            live_lease_token.expires_at_epoch,
            int(maintenance["expires_at_epoch"]),
            now_epoch + self._config.max_envelope_ttl_seconds,
        )
        subject = {
            "consumer_intent_sha256": intent.intent_sha256,
            "adapter_receipt_sha256": intent.adapter_receipt_sha256,
            "upstream_raw_transaction_sha256": intent.raw_transaction_sha256,
            "handoff_transaction_id": intent.handoff_transaction_id,
            "source_raw_document_sha256": upstream_request[
                "expected_raw_document_sha256"
            ],
            "expected_generation_token": upstream_request[
                "expected_generation_token"
            ],
            "candidate_raw_document_sha256": upstream_request[
                "candidate_raw_document_sha256"
            ],
            "maintenance_epoch": maintenance_permit.maintenance_epoch,
            "backend_identity_attestation_sha256": backend_identity_attestation[
                "attestation_sha256"
            ],
            "expires_at_epoch": effective_expiry,
        }
        subject_sha = _stable_sha256(subject)
        if not _authorization_grant_valid(
            authorization_grant,
            subject_sha,
            now_epoch,
            effective_expiry,
            self._config.max_envelope_ttl_seconds,
        ):
            reasons.append("SYNTHETIC_AUTHORIZATION_GRANT_INVALID")
            return result
        result["authorization_grant_verified_synthetic"] = True
        consumption = self._ledger.consume_once(
            authorization_grant,
            subject_binding_sha256=subject_sha,
            now_epoch=now_epoch,
        )
        if not _consumption_receipt_valid(
            consumption,
            authorization_grant["grant_sha256"],
            subject_sha,
        ):
            reasons.append("AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID")
            return result
        result["authorization_consumed_once_synthetic"] = True
        expires_at = min(effective_expiry, consumption["expires_at_epoch"])
        material = {
            "request_version": PRODUCTION_REQUEST_VERSION_V1,
            "scope_attestation": PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1,
            "subject_binding_sha256": subject_sha,
            "authorization_consumption_receipt_sha256": consumption[
                "receipt_sha256"
            ],
            "upstream_raw_transaction_sha256": intent.raw_transaction_sha256,
            "handoff_transaction_id": intent.handoff_transaction_id,
            "idempotency_key": intent.handoff_transaction_id,
            "backend_instance_sha256": backend_identity_attestation[
                "backend_instance_sha256"
            ],
            "registry_path_binding_sha256": backend_identity_attestation[
                "registry_path_binding_sha256"
            ],
            "backend_capability_attestation_sha256": (
                intent.backend_capability_attestation_sha256
            ),
            "lock_namespace_sha256": intent.lock_namespace_sha256,
            "maintenance_epoch": maintenance_permit.maintenance_epoch,
            "expected_raw_document_sha256": upstream_request[
                "expected_raw_document_sha256"
            ],
            "expected_generation_token": upstream_request[
                "expected_generation_token"
            ],
            "candidate_registry": _canonical_copy(
                upstream_request["candidate_registry"]
            ),
            "candidate_raw_document_sha256": upstream_request[
                "candidate_raw_document_sha256"
            ],
            "expires_at_epoch": expires_at,
            "recovery_policy": PRODUCTION_RECOVERY_POLICY_V1,
        }
        material["transaction_sha256"] = _stable_sha256(
            {**material, "identity_version": "C3_PRODUCTION_TRANSACTION_ID_V1"}
        )
        material["request_sha256"] = production_request_sha256_v1(material)
        envelope_values = {
            "subject_binding_sha256": subject_sha,
            "authorization_consumption_receipt_sha256": consumption[
                "receipt_sha256"
            ],
            "upstream_raw_transaction_sha256": intent.raw_transaction_sha256,
            "production_transaction_sha256": material["transaction_sha256"],
            "backend_instance_sha256": material["backend_instance_sha256"],
            "registry_path_binding_sha256": material[
                "registry_path_binding_sha256"
            ],
            "expires_at_epoch": expires_at,
        }
        envelope = ProtectedProductionInvocationEnvelopeV1(
            **envelope_values,
            request=material,
            envelope_sha256=_stable_sha256(
                {**envelope_values, "request_sha256": material["request_sha256"]}
            ),
        )
        valid_envelope, _ = _protected_request_valid(envelope)
        if not valid_envelope:
            reasons.append("PRODUCTION_SHAPED_REQUEST_INTEGRITY_FAILED")
            return result
        receipt = {
            "subject_binding_sha256": subject_sha,
            "authorization_consumption_receipt_sha256": consumption[
                "receipt_sha256"
            ],
            "upstream_raw_transaction_sha256": intent.raw_transaction_sha256,
            "production_transaction_sha256": material["transaction_sha256"],
            "production_request_sha256": material["request_sha256"],
            "backend_identity_attestation_sha256": backend_identity_attestation[
                "attestation_sha256"
            ],
            "backend_instance_sha256": material["backend_instance_sha256"],
            "registry_path_binding_sha256": material[
                "registry_path_binding_sha256"
            ],
            "expires_at_epoch": expires_at,
            "authorization_consumed_once_synthetic": True,
            "production_authorization_valid": False,
            "backend_referenced": False,
            "production_store_called": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["projection_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_PRODUCTION_INVOCATION_ENVELOPE_PROJECTED_OFFLINE",
            production_request_projected=True,
            protected_envelope=envelope,
            authorization_consumption_receipt=consumption,
            projection_receipt=receipt,
        )
        return result


def evaluate_terminal_result_contract_offline_v1(
    envelope: ProtectedProductionInvocationEnvelopeV1,
    terminal_result: Mapping[str, Any],
) -> dict[str, Any]:
    base = {
        "ok": False,
        "terminal_contract_valid": False,
        "terminal_state": None,
        "recovery_required": True,
        "production_terminal_verified": False,
        "production_authority": False,
        "write_executed": False,
        "registry_write": False,
        "reason": None,
    }
    request_valid, request = _protected_request_valid(envelope)
    if not request_valid or request is None or not isinstance(terminal_result, Mapping):
        base["reason"] = "TERMINAL_CONTRACT_INPUT_INVALID"
        return base
    supplied_sha = _valid_sha256(terminal_result.get("result_sha256"))
    state = str(terminal_result.get("terminal_state") or "")
    valid = bool(
        set(terminal_result) == _TERMINAL_RESULT_KEYS
        and terminal_result.get("result_version") == PRODUCTION_RESULT_VERSION_V1
        and terminal_result.get("execution_scope")
        == "SYNTHETIC_CONTRACT_EVALUATION"
        and terminal_result.get("request_sha256") == request["request_sha256"]
        and terminal_result.get("transaction_sha256")
        == request["transaction_sha256"]
        and terminal_result.get("backend_instance_sha256")
        == request["backend_instance_sha256"]
        and terminal_result.get("authorization_consumption_receipt_sha256")
        == request["authorization_consumption_receipt_sha256"]
        and terminal_result.get("maintenance_epoch")
        == request["maintenance_epoch"]
        and terminal_result.get("source_raw_document_sha256")
        == request["expected_raw_document_sha256"]
        and terminal_result.get("candidate_raw_document_sha256")
        == request["candidate_raw_document_sha256"]
        and state in {"COMMITTED", "ABORTED", "ROLLED_BACK", "AMBIGUOUS"}
        and _valid_sha256(terminal_result.get("prepared_record_sha256"))
        and _valid_sha256(terminal_result.get("terminal_record_sha256"))
        and terminal_result.get("production_evidence") is False
        and terminal_result.get("write_executed") is False
        and terminal_result.get("registry_write") is False
        and supplied_sha
        and supplied_sha == terminal_result_sha256_v1(terminal_result)
        and (
            (
                state in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
                and terminal_result.get("postconditions_verified") is True
                and terminal_result.get("recovery_required") is False
                and terminal_result.get("ambiguous") is False
            )
            or (
                state == "AMBIGUOUS"
                and terminal_result.get("postconditions_verified") is False
                and terminal_result.get("recovery_required") is True
                and terminal_result.get("ambiguous") is True
            )
        )
    )
    if not valid:
        base["reason"] = "TERMINAL_RESULT_CONTRACT_INVALID"
        return base
    base.update(
        ok=True,
        terminal_contract_valid=True,
        terminal_state=state,
        recovery_required=state == "AMBIGUOUS",
    )
    return base


def build_recovery_envelope_contract_offline_v1(
    envelope: ProtectedProductionInvocationEnvelopeV1,
    ambiguous_result: Mapping[str, Any],
    *,
    fresh_maintenance_epoch: str,
    expires_at_epoch: int,
) -> ProtectedProductionRecoveryEnvelopeV1:
    evaluation = evaluate_terminal_result_contract_offline_v1(
        envelope, ambiguous_result
    )
    request_valid, request = _protected_request_valid(envelope)
    fresh_epoch = _valid_sha256(fresh_maintenance_epoch)
    if not (
        evaluation.get("ok") is True
        and evaluation.get("terminal_state") == "AMBIGUOUS"
        and evaluation.get("recovery_required") is True
        and request_valid
        and request is not None
        and fresh_epoch
        and fresh_epoch != request["maintenance_epoch"]
        and type(expires_at_epoch) is int
        and 0 < expires_at_epoch <= envelope.expires_at_epoch
    ):
        raise ValueError("fresh recovery contract inputs required")
    material = {
        "recovery_request_version": PRODUCTION_RECOVERY_REQUEST_VERSION_V1,
        "scope_attestation": PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1,
        "original_request_sha256": request["request_sha256"],
        "transaction_sha256": request["transaction_sha256"],
        "backend_instance_sha256": request["backend_instance_sha256"],
        "registry_path_binding_sha256": request[
            "registry_path_binding_sha256"
        ],
        "authorization_consumption_receipt_sha256": request[
            "authorization_consumption_receipt_sha256"
        ],
        "source_raw_document_sha256": request[
            "expected_raw_document_sha256"
        ],
        "candidate_raw_document_sha256": request[
            "candidate_raw_document_sha256"
        ],
        "previous_maintenance_epoch": request["maintenance_epoch"],
        "fresh_maintenance_epoch": fresh_epoch,
        "recovery_policy": PRODUCTION_RECOVERY_POLICY_V1,
        "expires_at_epoch": expires_at_epoch,
        "synthetic_only": True,
        "production_authority": False,
    }
    material["recovery_request_sha256"] = recovery_request_sha256_v1(material)
    values = {
        "original_request_sha256": request["request_sha256"],
        "transaction_sha256": request["transaction_sha256"],
        "backend_instance_sha256": request["backend_instance_sha256"],
        "fresh_maintenance_epoch": fresh_epoch,
        "expires_at_epoch": expires_at_epoch,
    }
    return ProtectedProductionRecoveryEnvelopeV1(
        **values,
        request=material,
        envelope_sha256=_stable_sha256(
            {**values, "recovery_request_sha256": material["recovery_request_sha256"]}
        ),
    )


__all__ = [
    "AUTHORIZATION_ACTION_V1",
    "AUTHORIZATION_GRANT_VERSION_V1",
    "BACKEND_IDENTITY_ATTESTATION_VERSION_V1",
    "DormantProductionInvocationEnvelopeBuilderV1",
    "DormantProductionInvocationEnvelopeConfigV1",
    "InMemorySyntheticAuthorizationConsumptionLedgerV1",
    "OFFLINE_PRODUCTION_INVOCATION_ENVELOPE_SCOPE_ATTESTATION_V1",
    "PRODUCTION_RECOVERY_POLICY_V1",
    "PRODUCTION_RECOVERY_REQUEST_VERSION_V1",
    "PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1",
    "PRODUCTION_REQUEST_VERSION_V1",
    "PRODUCTION_RESULT_VERSION_V1",
    "ProtectedProductionInvocationEnvelopeV1",
    "ProtectedProductionRecoveryEnvelopeV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_CONTRACT_V1_VERSION",
    "authorization_grant_sha256_v1",
    "backend_identity_attestation_sha256_v1",
    "build_recovery_envelope_contract_offline_v1",
    "evaluate_terminal_result_contract_offline_v1",
    "production_request_sha256_v1",
    "recovery_request_sha256_v1",
    "terminal_result_sha256_v1",
]
