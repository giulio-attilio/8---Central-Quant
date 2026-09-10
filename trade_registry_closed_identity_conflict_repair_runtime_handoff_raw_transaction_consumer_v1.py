"""Dormant consumer for a protected handoff raw-transaction projection.

The consumer proves, offline and in memory, that the projected request is bound
to the exact live maintenance permit, the canonical lock namespace and a
TEMPORARY_TEST backend capability attestation.  It exposes no store call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1 as production_store
import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as request_adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-CONSUMER-V1"
)

OFFLINE_HANDOFF_RAW_TRANSACTION_CONSUMER_SCOPE_ATTESTATION_V1 = (
    "C3_HANDOFF_RAW_TRANSACTION_CONSUMER_OFFLINE_ONLY_V1"
)
_BACKEND_CAPABILITY_ATTESTATION_VERSION = (
    "C3_DURABLE_RAW_TRANSACTION_BACKEND_CAPABILITIES_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BACKEND_LABEL_RE = re.compile(r"^[A-Z0-9_.:-]{1,160}$")
_REQUIRED_BACKEND_CAPABILITIES = frozenset(
    {
        "append_only_hash_chained_wal",
        "atomic_same_directory_replace",
        "compare_and_swap_hash_and_generation",
        "exact_raw_loader",
        "file_and_directory_fsync",
        "idempotency_key_enforcement",
        "immutable_content_addressed_backup",
        "interrupted_transaction_recovery",
        "rollback_to_exact_preimage",
    }
)
_RAW_REQUEST_KEYS = frozenset(
    {
        "request_version",
        "scope_attestation",
        "idempotency_key",
        "maintenance_epoch",
        "expected_raw_document_sha256",
        "expected_generation_token",
        "candidate_registry",
        "candidate_raw_document_sha256",
        "transaction_sha256",
    }
)
_MAINTENANCE_KEYS = frozenset(
    {
        "attestation_version",
        "state",
        "maintenance_epoch",
        "lock_namespace_sha256",
        "registered_writer_count",
        "inflight_mutations",
        "shared_lock_acquired",
        "issued_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "production_evidence",
        "attestation_sha256",
    }
)
_ADAPTER_RECEIPT_KEYS = frozenset(
    {
        "handoff_transaction_id",
        "handoff_command_sha256",
        "raw_transaction_sha256",
        "canonical_raw_proof_sha256",
        "maintenance_attestation_sha256",
        "source_registry_sha256",
        "source_raw_document_sha256",
        "candidate_registry_sha256",
        "candidate_raw_document_sha256",
        "changed_paths_sha256",
        "expires_at_epoch",
        "request_projected",
        "request_material_exposed",
        "raw_transaction_store_called",
        "transaction_persistence_allowed",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "adapter_receipt_sha256",
    }
)
_BACKEND_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version",
        "backend_kind",
        "storage_scope",
        "registry_path_binding_sha256",
        "lock_namespace_sha256",
        "capabilities",
        "attestation_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "CONSUMER_IS_SYNTHETIC_OFFLINE_ONLY",
    "LEASE_LIVENESS_WITNESS_IS_IN_MEMORY_ONLY",
    "BACKEND_CAPABILITY_ATTESTATION_IS_TEMPORARY_TEST_ONLY",
    "BACKEND_INSTANCE_IS_NOT_REFERENCED",
    "PROTECTED_INTENT_CONTAINS_HASHES_ONLY",
    "RAW_TRANSACTION_STORE_IS_NOT_INVOKED",
    "TRANSACTION_PERSISTENCE_IS_FORBIDDEN",
    "RUNTIME_IS_NOT_INTEGRATED",
    "SEPARATE_PRODUCTION_LEASE_WITNESS_REQUIRED",
    "SEPARATE_PRODUCTION_AUTHORIZATION_REQUIRED",
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


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _receipt_sha256(value: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: item for key, item in value.items() if key != field_name}
    )


@dataclass(frozen=True)
class DormantHandoffRawTransactionConsumerConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_consume_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_consume_ttl_seconds <= 300:
            raise ValueError("max_consume_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticLiveLeaseTokenV1:
    token_sha256: str = field(repr=False)
    permit_binding_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticLiveLeaseTokenV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedRawTransactionInvocationIntentV1:
    adapter_receipt_sha256: str = field(repr=False)
    handoff_transaction_id: str = field(repr=False)
    raw_transaction_sha256: str = field(repr=False)
    maintenance_attestation_sha256: str = field(repr=False)
    maintenance_epoch: str = field(repr=False)
    live_lease_token_sha256: str = field(repr=False)
    backend_capability_attestation_sha256: str = field(repr=False)
    lock_namespace_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    intent_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedRawTransactionInvocationIntentV1(<protected>)"


def _permit_binding(permit: coordinator.WriterMaintenancePermitV1) -> dict[str, Any]:
    return {
        "maintenance_epoch": permit.maintenance_epoch,
        "state": permit.state,
        "lock_namespace_sha256": permit.lock_namespace_sha256,
        "registered_writer_count": permit.registered_writer_count,
        "inflight_mutations": permit.inflight_mutations,
        "shared_lock_acquired": permit.shared_lock_acquired,
    }


class InMemoryLiveMaintenanceLeaseWitnessV1:
    """Synthetic identity-and-liveness witness; never a production authority."""

    def __init__(
        self,
        *,
        clock: Callable[[], int],
        nonce_source: Callable[[], str],
    ) -> None:
        if not callable(clock) or not callable(nonce_source):
            raise TypeError("clock and nonce_source must be callable")
        self._clock = clock
        self._nonce_source = nonce_source
        self._lock = threading.Lock()
        self._active_permit: coordinator.WriterMaintenancePermitV1 | None = None
        self._active_token: ProtectedSyntheticLiveLeaseTokenV1 | None = None

    @contextmanager
    def hold_offline(
        self,
        permit: coordinator.WriterMaintenancePermitV1,
        *,
        expires_at_epoch: int,
    ) -> Iterator[ProtectedSyntheticLiveLeaseTokenV1]:
        if type(permit) is not coordinator.WriterMaintenancePermitV1:
            raise TypeError("permit must be a WriterMaintenancePermitV1")
        now_epoch = self._clock()
        if not (
            type(now_epoch) is int
            and type(expires_at_epoch) is int
            and now_epoch < expires_at_epoch
            and permit.state == "QUIESCED"
            and permit.lock_namespace_sha256
            == coordinator.canonical_runtime_lock_namespace_v1()
            and permit.registered_writer_count == 19
            and permit.inflight_mutations == 0
            and permit.shared_lock_acquired is True
            and _valid_sha256(permit.maintenance_epoch)
        ):
            raise ValueError("synthetic maintenance permit invalid")
        permit_sha = _stable_sha256(_permit_binding(permit))
        token = ProtectedSyntheticLiveLeaseTokenV1(
            token_sha256=_stable_sha256(
                {
                    "kind": "C3_SYNTHETIC_LIVE_MAINTENANCE_LEASE_TOKEN_V1",
                    "permit_binding_sha256": permit_sha,
                    "expires_at_epoch": expires_at_epoch,
                    "nonce": str(self._nonce_source()),
                }
            ),
            permit_binding_sha256=permit_sha,
            expires_at_epoch=expires_at_epoch,
        )
        with self._lock:
            if self._active_permit is not None:
                raise RuntimeError("synthetic maintenance lease already active")
            self._active_permit = permit
            self._active_token = token
        try:
            yield token
        finally:
            with self._lock:
                self._active_permit = None
                self._active_token = None

    def validate_live(
        self,
        permit: coordinator.WriterMaintenancePermitV1,
        token: ProtectedSyntheticLiveLeaseTokenV1,
        *,
        now_epoch: int,
    ) -> bool:
        if (
            type(permit) is not coordinator.WriterMaintenancePermitV1
            or type(token) is not ProtectedSyntheticLiveLeaseTokenV1
            or type(now_epoch) is not int
        ):
            return False
        with self._lock:
            return bool(
                permit is self._active_permit
                and token is self._active_token
                and now_epoch < token.expires_at_epoch
                and token.permit_binding_sha256
                == _stable_sha256(_permit_binding(permit))
                and _valid_sha256(token.token_sha256)
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self._active_permit is not None,
                "synthetic_only": True,
                "durable": False,
                "production_authority": False,
            }


def _adapter_projection_valid(
    result: Any,
    now_epoch: int,
) -> tuple[
    bool,
    request_adapter.ProtectedHandoffRawTransactionRequestV1 | None,
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
]:
    if not isinstance(result, Mapping):
        return False, None, None, None
    protected = result.get("protected_request")
    receipt = result.get("adapter_receipt")
    if (
        type(protected)
        is not request_adapter.ProtectedHandoffRawTransactionRequestV1
        or not isinstance(receipt, Mapping)
        or set(receipt) != _ADAPTER_RECEIPT_KEYS
    ):
        return False, None, None, None
    request = protected.request
    maintenance = protected.maintenance_attestation
    if not isinstance(request, Mapping) or not isinstance(maintenance, Mapping):
        return False, None, None, None
    try:
        request_copy = json.loads(_canonical_json(dict(request)))
        maintenance_copy = json.loads(_canonical_json(dict(maintenance)))
        supplied_receipt_sha = _valid_sha256(receipt.get("adapter_receipt_sha256"))
        supplied_maintenance_sha = _valid_sha256(
            maintenance_copy.get("attestation_sha256")
        )
        valid = bool(
            result.get("ok") is True
            and result.get("version")
            == request_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_V1_VERSION
            and result.get("request_projected") is True
            and result.get("raw_transaction_store_called") is False
            and result.get("transaction_persistence_allowed") is False
            and result.get("runtime_integrated") is False
            and result.get("production_ready") is False
            and result.get("apply_allowed") is False
            and result.get("activation_allowed") is False
            and result.get("live_allowed") is False
            and set(request_copy) == _RAW_REQUEST_KEYS
            and set(maintenance_copy) == _MAINTENANCE_KEYS
            and request_copy.get("scope_attestation")
            == raw_store.SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1
            and request_copy.get("transaction_sha256")
            == raw_store.raw_transaction_request_sha256_v1(request_copy)
            and request_copy.get("transaction_sha256")
            == protected.raw_transaction_sha256
            and request_copy.get("idempotency_key")
            == protected.handoff_transaction_id
            and request_copy.get("maintenance_epoch")
            == maintenance_copy.get("maintenance_epoch")
            and request_copy.get("expected_raw_document_sha256")
            == receipt.get("source_raw_document_sha256")
            and request_copy.get("candidate_raw_document_sha256")
            == receipt.get("candidate_raw_document_sha256")
            and protected.handoff_transaction_id
            == receipt.get("handoff_transaction_id")
            and protected.handoff_command_sha256
            == receipt.get("handoff_command_sha256")
            and protected.raw_transaction_sha256
            == receipt.get("raw_transaction_sha256")
            and protected.canonical_raw_proof_sha256
            == receipt.get("canonical_raw_proof_sha256")
            and protected.maintenance_attestation_sha256
            == receipt.get("maintenance_attestation_sha256")
            and protected.expires_at_epoch == receipt.get("expires_at_epoch")
            and now_epoch < protected.expires_at_epoch
            and receipt.get("request_projected") is True
            and receipt.get("request_material_exposed") is False
            and receipt.get("raw_transaction_store_called") is False
            and receipt.get("transaction_persistence_allowed") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
            and supplied_receipt_sha
            and hmac.compare_digest(
                supplied_receipt_sha,
                _receipt_sha256(receipt, "adapter_receipt_sha256"),
            )
            and supplied_maintenance_sha
            and hmac.compare_digest(
                supplied_maintenance_sha,
                request_adapter.maintenance_attestation_sha256_v1(
                    maintenance_copy
                ),
            )
        )
    except Exception:
        valid = False
    return (
        valid,
        protected if valid else None,
        request_copy if valid else None,
        maintenance_copy if valid else None,
    )


def _backend_attestation_valid(value: Any, canonical_namespace: str) -> bool:
    if not isinstance(value, Mapping) or set(value) != _BACKEND_ATTESTATION_KEYS:
        return False
    try:
        capabilities = value.get("capabilities")
        supplied_sha = _valid_sha256(value.get("attestation_sha256"))
        return bool(
            value.get("attestation_version")
            == _BACKEND_CAPABILITY_ATTESTATION_VERSION
            and _BACKEND_LABEL_RE.fullmatch(str(value.get("backend_kind") or ""))
            and value.get("storage_scope") == "TEMPORARY_TEST"
            and _valid_sha256(value.get("registry_path_binding_sha256"))
            and value.get("lock_namespace_sha256") == canonical_namespace
            and isinstance(capabilities, Mapping)
            and set(capabilities) == _REQUIRED_BACKEND_CAPABILITIES
            and all(capabilities.get(name) is True for name in capabilities)
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                production_store.production_backend_capability_attestation_sha256_v1(
                    value
                ),
            )
        )
    except Exception:
        return False


class DormantHandoffRawTransactionConsumerV1:
    def __init__(
        self,
        *,
        config: DormantHandoffRawTransactionConsumerConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_witness: InMemoryLiveMaintenanceLeaseWitnessV1 | None = None,
    ) -> None:
        self._config = config or DormantHandoffRawTransactionConsumerConfigV1()
        self._clock = clock
        self._lease_witness = lease_witness

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_HANDOFF_RAW_TRANSACTION_CONSUMER_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "adapter_projection_verified": False,
            "same_permit_instance_verified": False,
            "lease_live_verified_synthetic": False,
            "canonical_lock_namespace_verified": False,
            "backend_capabilities_verified_synthetic": False,
            "deadline_revalidated": False,
            "invocation_intent_projected": False,
            "invocation_material_exposed": False,
            "backend_referenced": False,
            "raw_transaction_store_called": False,
            "transaction_persistence_allowed": False,
            "runtime_integrated": False,
            "runtime_binding_satisfied": False,
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
            "checks": {},
            "protected_intent": None,
            "consumer_receipt": None,
        }

    def consume_offline(
        self,
        *,
        adapter_result: Mapping[str, Any],
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: ProtectedSyntheticLiveLeaseTokenV1,
        backend_capability_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            reasons.append("CONSUMER_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_HANDOFF_RAW_TRANSACTION_CONSUMER_SCOPE_ATTESTATION_V1
        ):
            reasons.append("CONSUMER_OFFLINE_SCOPE_ATTESTATION_REQUIRED")
            return result
        if type(self._lease_witness) is not InMemoryLiveMaintenanceLeaseWitnessV1:
            reasons.append("SYNTHETIC_LIVE_LEASE_WITNESS_REQUIRED")
            return result
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            reasons.append("CONSUMER_CLOCK_INVALID")
            return result

        projection_valid, protected, request, maintenance = (
            _adapter_projection_valid(adapter_result, now_epoch)
        )
        checks["adapter_projection_integrity"] = projection_valid
        if not projection_valid or protected is None or request is None or maintenance is None:
            reasons.append("ADAPTER_PROJECTION_INVALID_OR_EXPIRED")
            return result
        result["adapter_projection_verified"] = True
        result["deadline_revalidated"] = True

        canonical_namespace = coordinator.canonical_runtime_lock_namespace_v1()
        permit_valid = bool(
            type(maintenance_permit) is coordinator.WriterMaintenancePermitV1
            and maintenance_permit.state == "QUIESCED"
            and maintenance_permit.lock_namespace_sha256 == canonical_namespace
            and maintenance_permit.registered_writer_count == 19
            and maintenance_permit.inflight_mutations == 0
            and maintenance_permit.shared_lock_acquired is True
            and maintenance_permit.maintenance_epoch
            == request.get("maintenance_epoch")
            == maintenance.get("maintenance_epoch")
            and maintenance.get("lock_namespace_sha256") == canonical_namespace
            and maintenance.get("state") == "QUIESCED"
            and maintenance.get("registered_writer_count") == 19
            and maintenance.get("inflight_mutations") == 0
            and maintenance.get("shared_lock_acquired") is True
        )
        checks["canonical_permit_binding"] = permit_valid
        if not permit_valid:
            reasons.append("CANONICAL_MAINTENANCE_PERMIT_INVALID")
            return result
        result["canonical_lock_namespace_verified"] = True

        lease_live = self._lease_witness.validate_live(
            maintenance_permit,
            live_lease_token,
            now_epoch=now_epoch,
        )
        checks["same_instance_live_lease"] = lease_live
        if not lease_live:
            reasons.append("MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH")
            return result
        result["same_permit_instance_verified"] = True
        result["lease_live_verified_synthetic"] = True

        backend_valid = _backend_attestation_valid(
            backend_capability_attestation,
            canonical_namespace,
        )
        checks["temporary_backend_capability_attestation"] = backend_valid
        if not backend_valid:
            reasons.append("TEMPORARY_BACKEND_CAPABILITY_ATTESTATION_INVALID")
            return result
        result["backend_capabilities_verified_synthetic"] = True

        effective_expiry = min(
            protected.expires_at_epoch,
            live_lease_token.expires_at_epoch,
            int(maintenance["expires_at_epoch"]),
            now_epoch + self._config.max_consume_ttl_seconds,
        )
        if now_epoch >= effective_expiry:
            reasons.append("CONSUMER_EFFECTIVE_DEADLINE_EXPIRED")
            return result
        values = {
            "adapter_receipt_sha256": adapter_result["adapter_receipt"][
                "adapter_receipt_sha256"
            ],
            "handoff_transaction_id": protected.handoff_transaction_id,
            "raw_transaction_sha256": protected.raw_transaction_sha256,
            "maintenance_attestation_sha256": (
                protected.maintenance_attestation_sha256
            ),
            "maintenance_epoch": maintenance_permit.maintenance_epoch,
            "live_lease_token_sha256": live_lease_token.token_sha256,
            "backend_capability_attestation_sha256": (
                backend_capability_attestation["attestation_sha256"]
            ),
            "lock_namespace_sha256": canonical_namespace,
            "expires_at_epoch": effective_expiry,
        }
        intent = ProtectedRawTransactionInvocationIntentV1(
            **values,
            intent_sha256=_stable_sha256(
                {
                    **values,
                    "intent_version": (
                        "C3_PROTECTED_RAW_TRANSACTION_INVOCATION_INTENT_V1"
                    ),
                }
            ),
        )
        receipt = {
            **values,
            "intent_sha256": intent.intent_sha256,
            "same_permit_instance_verified": True,
            "lease_live_verified_synthetic": True,
            "canonical_lock_namespace_verified": True,
            "backend_capabilities_verified_synthetic": True,
            "backend_storage_scope": "TEMPORARY_TEST",
            "invocation_material_exposed": False,
            "backend_referenced": False,
            "raw_transaction_store_called": False,
            "transaction_persistence_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["consumer_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_RAW_TRANSACTION_INVOCATION_INTENT_PROJECTED_OFFLINE",
            invocation_intent_projected=True,
            protected_intent=intent,
            consumer_receipt=receipt,
        )
        return result


__all__ = [
    "DormantHandoffRawTransactionConsumerConfigV1",
    "DormantHandoffRawTransactionConsumerV1",
    "InMemoryLiveMaintenanceLeaseWitnessV1",
    "OFFLINE_HANDOFF_RAW_TRANSACTION_CONSUMER_SCOPE_ATTESTATION_V1",
    "ProtectedRawTransactionInvocationIntentV1",
    "ProtectedSyntheticLiveLeaseTokenV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_V1_VERSION",
]
