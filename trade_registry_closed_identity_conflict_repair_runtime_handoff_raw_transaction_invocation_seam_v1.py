"""Offline invocation seam for the protected C3 raw transaction chain.

Only an exact in-memory store double may be invoked.  Production stores,
files, runtime installation and real Registry access are intentionally absent.
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

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-INVOCATION-SEAM-V1"
)

OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1 = (
    "C3_RAW_TRANSACTION_INVOCATION_SEAM_OFFLINE_ONLY_V1"
)
SYNTHETIC_STORE_BINDING_VERSION_V1 = "C3_SYNTHETIC_RAW_STORE_INSTANCE_BINDING_V1"
SYNTHETIC_RECOVERY_COMMAND_VERSION_V1 = (
    "C3_SYNTHETIC_PREPARED_TRANSACTION_RECOVERY_COMMAND_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
_CONSUMER_RECEIPT_KEYS = frozenset(
    {
        "adapter_receipt_sha256",
        "handoff_transaction_id",
        "raw_transaction_sha256",
        "maintenance_attestation_sha256",
        "maintenance_epoch",
        "live_lease_token_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "expires_at_epoch",
        "intent_sha256",
        "same_permit_instance_verified",
        "lease_live_verified_synthetic",
        "canonical_lock_namespace_verified",
        "backend_capabilities_verified_synthetic",
        "backend_storage_scope",
        "invocation_material_exposed",
        "backend_referenced",
        "raw_transaction_store_called",
        "transaction_persistence_allowed",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "consumer_receipt_sha256",
    }
)
_STORE_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "store_instance_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "storage_scope",
        "synthetic_store_double",
        "production_store_referenced",
        "binding_sha256",
    }
)
_RECOVERY_COMMAND_KEYS = frozenset(
    {
        "command_version",
        "raw_transaction_sha256",
        "store_instance_sha256",
        "store_binding_sha256",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "failed_maintenance_epoch",
        "prepared_record_sha256",
        "issued_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "production_authority",
        "command_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "INVOCATION_SEAM_IS_SYNTHETIC_OFFLINE_ONLY",
    "ONLY_EXACT_IN_MEMORY_STORE_DOUBLE_IS_ACCEPTED",
    "STORE_BINDING_IS_SYNTHETIC_NON_PRODUCTION",
    "NO_REGISTRY_BYTES_ARE_PERSISTED",
    "NO_PRODUCTION_STORE_IS_REFERENCED",
    "RUNTIME_IS_NOT_INTEGRATED",
    "PRODUCTION_REQUEST_SCHEMA_IS_NOT_DEFINED",
    "PRODUCTION_POSTCONDITIONS_ARE_NOT_BOUND",
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


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _receipt_sha256(value: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: item for key, item in value.items() if key != field_name}
    )


@dataclass(frozen=True)
class DormantRawTransactionInvocationSeamConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_recovery_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_recovery_ttl_seconds <= 300:
            raise ValueError("max_recovery_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticPreparedRecoveryCommandV1:
    command_version: str = field(repr=False)
    raw_transaction_sha256: str = field(repr=False)
    store_instance_sha256: str = field(repr=False)
    store_binding_sha256: str = field(repr=False)
    source_raw_document_sha256: str = field(repr=False)
    candidate_raw_document_sha256: str = field(repr=False)
    failed_maintenance_epoch: str = field(repr=False)
    prepared_record_sha256: str = field(repr=False)
    issued_at_epoch: int = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    synthetic_only: bool = field(repr=False)
    production_authority: bool = field(repr=False)
    command_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticPreparedRecoveryCommandV1(<protected>)"


class SyntheticStoreInterrupted(RuntimeError):
    pass


class InMemoryAttestedRawTransactionStoreDoubleV1:
    """Hash-only transaction state machine; never writes Registry bytes."""

    def __init__(
        self,
        *,
        backend_capability_attestation: Mapping[str, Any],
        nonce: str,
        fault_mode: str | None = None,
    ) -> None:
        canonical_namespace = coordinator.canonical_runtime_lock_namespace_v1()
        if not consumer._backend_attestation_valid(
            backend_capability_attestation, canonical_namespace
        ):
            raise ValueError("synthetic backend capability attestation invalid")
        if fault_mode not in {None, "AFTER_PREPARED", "INVALID_SUCCESS"}:
            raise ValueError("fault_mode invalid")
        self._capability_sha256 = backend_capability_attestation[
            "attestation_sha256"
        ]
        self._namespace = canonical_namespace
        self._instance_sha256 = _stable_sha256(
            {
                "kind": "C3_IN_MEMORY_RAW_TRANSACTION_STORE_DOUBLE_V1",
                "backend_capability_attestation_sha256": self._capability_sha256,
                "lock_namespace_sha256": canonical_namespace,
                "nonce": str(nonce),
            }
        )
        self._fault_mode = fault_mode
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        binding = {
            "binding_version": SYNTHETIC_STORE_BINDING_VERSION_V1,
            "store_instance_sha256": self._instance_sha256,
            "backend_capability_attestation_sha256": self._capability_sha256,
            "lock_namespace_sha256": self._namespace,
            "storage_scope": "TEMPORARY_TEST",
            "synthetic_store_double": True,
            "production_store_referenced": False,
        }
        binding["binding_sha256"] = _stable_sha256(binding)
        self._binding = binding

    @property
    def instance_sha256(self) -> str:
        return self._instance_sha256

    @property
    def capability_attestation_sha256(self) -> str:
        return self._capability_sha256

    @property
    def lock_namespace_sha256(self) -> str:
        return self._namespace

    def binding_attestation(self) -> dict[str, Any]:
        return json.loads(_canonical_json(self._binding))

    @staticmethod
    def _request_valid(
        request: Mapping[str, Any], maintenance: Mapping[str, Any]
    ) -> bool:
        try:
            candidate = request.get("candidate_registry")
            return bool(
                request.get("request_version")
                == "SYNTHETIC_RAW_REGISTRY_TRANSACTION_REQUEST_V1"
                and request.get("scope_attestation")
                == raw_store.SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1
                and _valid_sha256(request.get("transaction_sha256"))
                and request.get("transaction_sha256")
                == raw_store.raw_transaction_request_sha256_v1(request)
                and _valid_sha256(request.get("idempotency_key"))
                and _valid_sha256(request.get("expected_raw_document_sha256"))
                and _valid_sha256(request.get("expected_generation_token"))
                and isinstance(candidate, Mapping)
                and request.get("candidate_raw_document_sha256")
                == _bytes_sha256(_canonical_json(candidate).encode("utf-8"))
                and request.get("maintenance_epoch")
                == maintenance.get("maintenance_epoch")
                and maintenance.get("state") == "QUIESCED"
                and maintenance.get("lock_namespace_sha256")
                == coordinator.canonical_runtime_lock_namespace_v1()
                and maintenance.get("registered_writer_count") == 19
                and maintenance.get("inflight_mutations") == 0
                and maintenance.get("shared_lock_acquired") is True
            )
        except Exception:
            return False

    def apply_attested_transaction_offline_double(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self._request_valid(request, maintenance_attestation):
            return {
                "ok": False,
                "status": "SYNTHETIC_STORE_DOUBLE_REQUEST_INVALID",
                "terminal_state": None,
                "write_executed": False,
                "registry_write": False,
            }
        transaction_sha = request["transaction_sha256"]
        with self._lock:
            existing = self._records.get(transaction_sha)
            if existing and existing["state"] == "COMMITTED":
                return self._success_result(existing, idempotent_replay=True)
            if existing and existing["state"] == "PREPARED":
                raise SyntheticStoreInterrupted("UNRESOLVED_PREPARED_TRANSACTION")
            prepared_sha = _stable_sha256(
                {
                    "state": "PREPARED",
                    "transaction_sha256": transaction_sha,
                    "source_raw_document_sha256": request[
                        "expected_raw_document_sha256"
                    ],
                    "candidate_raw_document_sha256": request[
                        "candidate_raw_document_sha256"
                    ],
                    "maintenance_epoch": request["maintenance_epoch"],
                    "store_instance_sha256": self._instance_sha256,
                }
            )
            record = {
                "state": "PREPARED",
                "transaction_sha256": transaction_sha,
                "source_raw_document_sha256": request[
                    "expected_raw_document_sha256"
                ],
                "candidate_raw_document_sha256": request[
                    "candidate_raw_document_sha256"
                ],
                "prepared_record_sha256": prepared_sha,
                "maintenance_epoch": request["maintenance_epoch"],
            }
            self._records[transaction_sha] = record
            if self._fault_mode == "AFTER_PREPARED":
                raise SyntheticStoreInterrupted("SYNTHETIC_INTERRUPTION_AFTER_PREPARED")
            record["state"] = "COMMITTED"
            record["commit_record_sha256"] = _stable_sha256(
                {
                    **record,
                    "state": "COMMITTED",
                    "store_instance_sha256": self._instance_sha256,
                }
            )
            if self._fault_mode == "INVALID_SUCCESS":
                return {"ok": True, "status": "UNATTESTED_SUCCESS"}
            return self._success_result(record, idempotent_replay=False)

    @staticmethod
    def _success_result(
        record: Mapping[str, Any], *, idempotent_replay: bool
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "SYNTHETIC_STORE_DOUBLE_TRANSACTION_COMMITTED",
            "terminal_state": "COMMITTED",
            "transaction_sha256": record["transaction_sha256"],
            "source_raw_document_sha256": record[
                "source_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": record[
                "candidate_raw_document_sha256"
            ],
            "prepared_record_sha256": record["prepared_record_sha256"],
            "commit_record_sha256": record["commit_record_sha256"],
            "idempotent_replay": idempotent_replay,
            "synthetic_store_double_called": True,
            "production_store_called": False,
            "write_executed": False,
            "registry_write": False,
        }

    def reconcile_attested_transaction_offline_double(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not (
            _valid_sha256(transaction_sha256)
            and maintenance_attestation.get("state") == "QUIESCED"
            and maintenance_attestation.get("lock_namespace_sha256")
            == self._namespace
            and maintenance_attestation.get("registered_writer_count") == 19
            and maintenance_attestation.get("inflight_mutations") == 0
            and maintenance_attestation.get("shared_lock_acquired") is True
        ):
            return {
                "ok": False,
                "status": "SYNTHETIC_STORE_DOUBLE_RECOVERY_INPUT_INVALID",
                "write_executed": False,
                "registry_write": False,
            }
        with self._lock:
            record = self._records.get(transaction_sha256)
            if not record or record.get("state") != "PREPARED":
                return {
                    "ok": False,
                    "status": "SYNTHETIC_STORE_DOUBLE_PREPARED_NOT_FOUND",
                    "write_executed": False,
                    "registry_write": False,
                }
            if maintenance_attestation.get("maintenance_epoch") == record.get(
                "maintenance_epoch"
            ):
                return {
                    "ok": False,
                    "status": "SYNTHETIC_STORE_DOUBLE_FRESH_RECOVERY_LEASE_REQUIRED",
                    "write_executed": False,
                    "registry_write": False,
                }
            record["state"] = "ABORTED"
            record["recovery_epoch"] = maintenance_attestation[
                "maintenance_epoch"
            ]
            record["terminal_record_sha256"] = _stable_sha256(
                {
                    **record,
                    "state": "ABORTED",
                    "reason": "SYNTHETIC_SOURCE_INTACT",
                    "store_instance_sha256": self._instance_sha256,
                }
            )
            return {
                "ok": True,
                "status": "SYNTHETIC_STORE_DOUBLE_RECOVERY_ABORTED_SOURCE_INTACT",
                "terminal_state": "ABORTED",
                "transaction_sha256": transaction_sha256,
                "source_raw_document_sha256": record[
                    "source_raw_document_sha256"
                ],
                "candidate_raw_document_sha256": record[
                    "candidate_raw_document_sha256"
                ],
                "prepared_record_sha256": record["prepared_record_sha256"],
                "terminal_record_sha256": record["terminal_record_sha256"],
                "recovery_maintenance_epoch": record["recovery_epoch"],
                "synthetic_store_double_called": True,
                "production_store_called": False,
                "write_executed": False,
                "registry_write": False,
            }

    def transaction_state(self, transaction_sha256: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(transaction_sha256)
            if record is None:
                return None
            return {
                key: value
                for key, value in record.items()
                if key
                in {
                    "state",
                    "transaction_sha256",
                    "source_raw_document_sha256",
                    "candidate_raw_document_sha256",
                    "prepared_record_sha256",
                    "commit_record_sha256",
                    "terminal_record_sha256",
                    "maintenance_epoch",
                    "recovery_epoch",
                }
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for record in self._records.values():
                state = str(record.get("state") or "UNKNOWN")
                states[state] = states.get(state, 0) + 1
            return {
                "store_instance_sha256": self._instance_sha256,
                "record_count": len(self._records),
                "states": states,
                "synthetic_only": True,
                "in_memory_only": True,
                "production_store": False,
                "registry_bytes_stored": False,
            }


def _consumer_result_valid(
    value: Any,
    adapter_result: Mapping[str, Any],
    now_epoch: int,
) -> tuple[
    bool,
    consumer.ProtectedRawTransactionInvocationIntentV1 | None,
    Mapping[str, Any] | None,
    Mapping[str, Any] | None,
]:
    if not isinstance(value, Mapping):
        return False, None, None, None
    intent = value.get("protected_intent")
    receipt = value.get("consumer_receipt")
    projection_valid, projected, request, maintenance = (
        consumer._adapter_projection_valid(adapter_result, now_epoch)
    )
    if not (
        projection_valid
        and projected is not None
        and request is not None
        and maintenance is not None
        and type(intent) is consumer.ProtectedRawTransactionInvocationIntentV1
        and isinstance(receipt, Mapping)
        and set(receipt) == _CONSUMER_RECEIPT_KEYS
    ):
        return False, None, None, None
    values = {
        "adapter_receipt_sha256": intent.adapter_receipt_sha256,
        "handoff_transaction_id": intent.handoff_transaction_id,
        "raw_transaction_sha256": intent.raw_transaction_sha256,
        "maintenance_attestation_sha256": intent.maintenance_attestation_sha256,
        "maintenance_epoch": intent.maintenance_epoch,
        "live_lease_token_sha256": intent.live_lease_token_sha256,
        "backend_capability_attestation_sha256": (
            intent.backend_capability_attestation_sha256
        ),
        "lock_namespace_sha256": intent.lock_namespace_sha256,
        "expires_at_epoch": intent.expires_at_epoch,
    }
    expected_intent_sha = _stable_sha256(
        {
            **values,
            "intent_version": "C3_PROTECTED_RAW_TRANSACTION_INVOCATION_INTENT_V1",
        }
    )
    try:
        valid = bool(
            value.get("ok") is True
            and value.get("version")
            == consumer.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_V1_VERSION
            and value.get("invocation_intent_projected") is True
            and value.get("backend_referenced") is False
            and value.get("raw_transaction_store_called") is False
            and value.get("transaction_persistence_allowed") is False
            and value.get("runtime_integrated") is False
            and value.get("apply_allowed") is False
            and value.get("live_allowed") is False
            and now_epoch < intent.expires_at_epoch
            and _valid_sha256(intent.intent_sha256)
            and hmac.compare_digest(intent.intent_sha256, expected_intent_sha)
            and all(receipt.get(key) == item for key, item in values.items())
            and receipt.get("intent_sha256") == intent.intent_sha256
            and receipt.get("same_permit_instance_verified") is True
            and receipt.get("lease_live_verified_synthetic") is True
            and receipt.get("canonical_lock_namespace_verified") is True
            and receipt.get("backend_capabilities_verified_synthetic") is True
            and receipt.get("backend_storage_scope") == "TEMPORARY_TEST"
            and receipt.get("invocation_material_exposed") is False
            and receipt.get("backend_referenced") is False
            and receipt.get("raw_transaction_store_called") is False
            and receipt.get("transaction_persistence_allowed") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
            and _valid_sha256(receipt.get("consumer_receipt_sha256"))
            and hmac.compare_digest(
                receipt["consumer_receipt_sha256"],
                _receipt_sha256(receipt, "consumer_receipt_sha256"),
            )
            and intent.adapter_receipt_sha256
            == adapter_result["adapter_receipt"]["adapter_receipt_sha256"]
            and intent.handoff_transaction_id == projected.handoff_transaction_id
            and intent.raw_transaction_sha256 == request["transaction_sha256"]
            and intent.maintenance_attestation_sha256
            == maintenance["attestation_sha256"]
            and intent.maintenance_epoch == request["maintenance_epoch"]
        )
    except Exception:
        valid = False
    return valid, intent if valid else None, request if valid else None, maintenance if valid else None


def _store_binding_valid(
    store: InMemoryAttestedRawTransactionStoreDoubleV1,
    intent: consumer.ProtectedRawTransactionInvocationIntentV1,
) -> bool:
    if type(store) is not InMemoryAttestedRawTransactionStoreDoubleV1:
        return False
    binding = store.binding_attestation()
    return bool(
        set(binding) == _STORE_BINDING_KEYS
        and binding.get("binding_version") == SYNTHETIC_STORE_BINDING_VERSION_V1
        and binding.get("store_instance_sha256") == store.instance_sha256
        and binding.get("backend_capability_attestation_sha256")
        == store.capability_attestation_sha256
        == intent.backend_capability_attestation_sha256
        and binding.get("lock_namespace_sha256")
        == store.lock_namespace_sha256
        == intent.lock_namespace_sha256
        == coordinator.canonical_runtime_lock_namespace_v1()
        and binding.get("storage_scope") == "TEMPORARY_TEST"
        and binding.get("synthetic_store_double") is True
        and binding.get("production_store_referenced") is False
        and _valid_sha256(binding.get("binding_sha256"))
        and binding["binding_sha256"] == _receipt_sha256(binding, "binding_sha256")
    )


class DormantRawTransactionInvocationSeamV1:
    def __init__(
        self,
        *,
        config: DormantRawTransactionInvocationSeamConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_witness: consumer.InMemoryLiveMaintenanceLeaseWitnessV1 | None = None,
        store_double: InMemoryAttestedRawTransactionStoreDoubleV1 | None = None,
    ) -> None:
        self._config = config or DormantRawTransactionInvocationSeamConfigV1()
        self._clock = clock
        self._lease_witness = lease_witness
        self._store = store_double

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_RAW_TRANSACTION_INVOCATION_SEAM_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "consumer_intent_verified": False,
            "adapter_material_revalidated": False,
            "same_permit_instance_verified": False,
            "lease_live_verified_synthetic": False,
            "store_instance_bound_synthetic": False,
            "deadline_revalidated": False,
            "postconditions_verified": False,
            "synthetic_store_double_called": False,
            "production_store_called": False,
            "recovery_required": False,
            "transaction_persistence_allowed": False,
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
            "synthetic_store_result": None,
            "protected_recovery_command": None,
            "invocation_receipt": None,
        }

    def _preflight(
        self,
        *,
        consumer_result: Mapping[str, Any],
        adapter_result: Mapping[str, Any],
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
    ) -> tuple[dict[str, Any], Any, Any, Any, int | None]:
        result = self._base()
        reasons = result["reasons"]
        if self._config.enabled is not True:
            reasons.append("INVOCATION_SEAM_DEFAULT_OFF")
            return result, None, None, None, None
        if (
            self._config.scope_attestation
            != OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1
        ):
            reasons.append("INVOCATION_SEAM_OFFLINE_SCOPE_ATTESTATION_REQUIRED")
            return result, None, None, None, None
        if (
            type(self._lease_witness)
            is not consumer.InMemoryLiveMaintenanceLeaseWitnessV1
            or type(self._store)
            is not InMemoryAttestedRawTransactionStoreDoubleV1
        ):
            reasons.append("EXACT_SYNTHETIC_DEPENDENCIES_REQUIRED")
            return result, None, None, None, None
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            reasons.append("INVOCATION_SEAM_CLOCK_INVALID")
            return result, None, None, None, None
        valid, intent, request, maintenance = _consumer_result_valid(
            consumer_result, adapter_result, now_epoch
        )
        if not valid or intent is None or request is None or maintenance is None:
            reasons.append("CONSUMER_INTENT_OR_ADAPTER_MATERIAL_INVALID")
            return result, None, None, None, now_epoch
        result["consumer_intent_verified"] = True
        result["adapter_material_revalidated"] = True
        result["deadline_revalidated"] = True
        if not self._lease_witness.validate_live(
            maintenance_permit,
            live_lease_token,
            now_epoch=now_epoch,
        ):
            reasons.append("MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH")
            return result, None, None, None, now_epoch
        if not (
            intent.live_lease_token_sha256 == live_lease_token.token_sha256
            and intent.maintenance_epoch == maintenance_permit.maintenance_epoch
            and intent.lock_namespace_sha256
            == maintenance_permit.lock_namespace_sha256
        ):
            reasons.append("CONSUMER_INTENT_LIVE_LEASE_BINDING_INVALID")
            return result, None, None, None, now_epoch
        result["same_permit_instance_verified"] = True
        result["lease_live_verified_synthetic"] = True
        if not _store_binding_valid(self._store, intent):
            reasons.append("SYNTHETIC_STORE_INSTANCE_BINDING_INVALID")
            return result, None, None, None, now_epoch
        result["store_instance_bound_synthetic"] = True
        return result, intent, request, maintenance, now_epoch

    def invoke_offline(
        self,
        *,
        consumer_result: Mapping[str, Any],
        adapter_result: Mapping[str, Any],
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
    ) -> dict[str, Any]:
        result, intent, request, maintenance, now_epoch = self._preflight(
            consumer_result=consumer_result,
            adapter_result=adapter_result,
            maintenance_permit=maintenance_permit,
            live_lease_token=live_lease_token,
        )
        if intent is None or request is None or maintenance is None or now_epoch is None:
            return result
        result["synthetic_store_double_called"] = True
        try:
            store_result = self._store.apply_attested_transaction_offline_double(
                request, maintenance
            )
        except SyntheticStoreInterrupted:
            state = self._store.transaction_state(intent.raw_transaction_sha256)
            if not isinstance(state, Mapping) or state.get("state") != "PREPARED":
                result["reasons"].append("SYNTHETIC_INTERRUPTION_STATE_UNVERIFIED")
                return result
            values = {
                "command_version": SYNTHETIC_RECOVERY_COMMAND_VERSION_V1,
                "raw_transaction_sha256": intent.raw_transaction_sha256,
                "store_instance_sha256": self._store.instance_sha256,
                "store_binding_sha256": self._store.binding_attestation()[
                    "binding_sha256"
                ],
                "source_raw_document_sha256": state[
                    "source_raw_document_sha256"
                ],
                "candidate_raw_document_sha256": state[
                    "candidate_raw_document_sha256"
                ],
                "failed_maintenance_epoch": maintenance_permit.maintenance_epoch,
                "prepared_record_sha256": state["prepared_record_sha256"],
                "issued_at_epoch": now_epoch,
                "expires_at_epoch": min(
                    intent.expires_at_epoch,
                    now_epoch + self._config.max_recovery_ttl_seconds,
                ),
                "synthetic_only": True,
                "production_authority": False,
            }
            command = ProtectedSyntheticPreparedRecoveryCommandV1(
                **values,
                command_sha256=_stable_sha256(values),
            )
            receipt = {
                "raw_transaction_sha256": intent.raw_transaction_sha256,
                "store_instance_sha256": self._store.instance_sha256,
                "store_binding_sha256": values["store_binding_sha256"],
                "prepared_record_sha256": state["prepared_record_sha256"],
                "failed_maintenance_epoch": maintenance_permit.maintenance_epoch,
                "recovery_command_sha256": command.command_sha256,
                "recovery_required": True,
                "synthetic_store_double_called": True,
                "production_store_called": False,
                "write_executed": False,
                "registry_write": False,
            }
            receipt["invocation_receipt_sha256"] = _stable_sha256(receipt)
            result.update(
                status="C3_SYNTHETIC_TRANSACTION_INTERRUPTED_AFTER_PREPARED",
                recovery_required=True,
                protected_recovery_command=command,
                invocation_receipt=receipt,
            )
            return result
        except Exception:
            result["reasons"].append("SYNTHETIC_STORE_DOUBLE_FAILED_CLOSED")
            return result

        result["synthetic_store_result"] = store_result
        postconditions = bool(
            isinstance(store_result, Mapping)
            and store_result.get("ok") is True
            and store_result.get("status")
            == "SYNTHETIC_STORE_DOUBLE_TRANSACTION_COMMITTED"
            and store_result.get("terminal_state") == "COMMITTED"
            and store_result.get("transaction_sha256")
            == intent.raw_transaction_sha256
            and store_result.get("source_raw_document_sha256")
            == request["expected_raw_document_sha256"]
            and store_result.get("candidate_raw_document_sha256")
            == request["candidate_raw_document_sha256"]
            and _valid_sha256(store_result.get("prepared_record_sha256"))
            and _valid_sha256(store_result.get("commit_record_sha256"))
            and store_result.get("synthetic_store_double_called") is True
            and store_result.get("production_store_called") is False
            and store_result.get("write_executed") is False
            and store_result.get("registry_write") is False
        )
        if not postconditions:
            result["reasons"].append("SYNTHETIC_STORE_POSTCONDITIONS_INVALID")
            result["recovery_required"] = True
            return result
        receipt = {
            "consumer_intent_sha256": intent.intent_sha256,
            "raw_transaction_sha256": intent.raw_transaction_sha256,
            "store_instance_sha256": self._store.instance_sha256,
            "store_binding_sha256": self._store.binding_attestation()[
                "binding_sha256"
            ],
            "prepared_record_sha256": store_result["prepared_record_sha256"],
            "commit_record_sha256": store_result["commit_record_sha256"],
            "terminal_state": "COMMITTED",
            "postconditions_verified": True,
            "synthetic_store_double_called": True,
            "production_store_called": False,
            "write_executed": False,
            "registry_write": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["invocation_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_SYNTHETIC_RAW_TRANSACTION_COMMITTED_OFFLINE",
            postconditions_verified=True,
            invocation_receipt=receipt,
        )
        return result

    def recover_offline(
        self,
        *,
        recovery_command: ProtectedSyntheticPreparedRecoveryCommandV1,
        recovery_maintenance_permit: coordinator.WriterMaintenancePermitV1,
        recovery_live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
        recovery_maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        result["status"] = "C3_RAW_TRANSACTION_RECOVERY_SEAM_BLOCKED"
        if self._config.enabled is not True:
            result["reasons"].append("INVOCATION_SEAM_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1
            or type(self._lease_witness)
            is not consumer.InMemoryLiveMaintenanceLeaseWitnessV1
            or type(self._store)
            is not InMemoryAttestedRawTransactionStoreDoubleV1
        ):
            result["reasons"].append("RECOVERY_SEAM_DEPENDENCIES_INVALID")
            return result
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        command_payload = (
            {
                key: getattr(recovery_command, key)
                for key in _RECOVERY_COMMAND_KEYS
                if key != "command_sha256"
            }
            if type(recovery_command)
            is ProtectedSyntheticPreparedRecoveryCommandV1
            else None
        )
        command_valid = bool(
            isinstance(command_payload, Mapping)
            and type(now_epoch) is int
            and recovery_command.command_version
            == SYNTHETIC_RECOVERY_COMMAND_VERSION_V1
            and recovery_command.synthetic_only is True
            and recovery_command.production_authority is False
            and recovery_command.store_instance_sha256
            == self._store.instance_sha256
            and recovery_command.store_binding_sha256
            == self._store.binding_attestation()["binding_sha256"]
            and recovery_command.issued_at_epoch <= now_epoch
            and now_epoch < recovery_command.expires_at_epoch
            and recovery_command.command_sha256 == _stable_sha256(command_payload)
        )
        if not command_valid:
            result["reasons"].append("SYNTHETIC_RECOVERY_COMMAND_INVALID_OR_EXPIRED")
            return result
        attestation_valid = False
        if (
            isinstance(recovery_maintenance_attestation, Mapping)
            and type(recovery_maintenance_permit)
            is coordinator.WriterMaintenancePermitV1
        ):
            supplied_sha = _valid_sha256(
                recovery_maintenance_attestation.get("attestation_sha256")
            )
            attestation_valid = bool(
                set(recovery_maintenance_attestation) == _MAINTENANCE_KEYS
                and recovery_maintenance_attestation.get("attestation_version")
                == adapter.MAINTENANCE_ATTESTATION_VERSION_V1
                and recovery_maintenance_attestation.get("state") == "QUIESCED"
                and recovery_maintenance_attestation.get("maintenance_epoch")
                == recovery_maintenance_permit.maintenance_epoch
                and recovery_maintenance_permit.maintenance_epoch
                != recovery_command.failed_maintenance_epoch
                and recovery_maintenance_attestation.get("lock_namespace_sha256")
                == recovery_maintenance_permit.lock_namespace_sha256
                == coordinator.canonical_runtime_lock_namespace_v1()
                and recovery_maintenance_attestation.get(
                    "registered_writer_count"
                )
                == 19
                and recovery_maintenance_attestation.get("inflight_mutations")
                == 0
                and recovery_maintenance_attestation.get(
                    "shared_lock_acquired"
                )
                is True
                and recovery_maintenance_permit.registered_writer_count == 19
                and recovery_maintenance_permit.inflight_mutations == 0
                and recovery_maintenance_permit.shared_lock_acquired is True
                and type(
                    recovery_maintenance_attestation.get("issued_at_epoch")
                )
                is int
                and type(
                    recovery_maintenance_attestation.get("expires_at_epoch")
                )
                is int
                and recovery_maintenance_attestation["issued_at_epoch"]
                <= now_epoch
                and now_epoch
                < recovery_maintenance_attestation["expires_at_epoch"]
                <= recovery_command.expires_at_epoch
                and recovery_maintenance_attestation.get("synthetic_only") is True
                and recovery_maintenance_attestation.get("production_evidence")
                is False
                and supplied_sha
                and supplied_sha
                == adapter.maintenance_attestation_sha256_v1(
                    recovery_maintenance_attestation
                )
            )
        if not attestation_valid:
            result["reasons"].append("FRESH_RECOVERY_MAINTENANCE_ATTESTATION_INVALID")
            return result
        if not self._lease_witness.validate_live(
            recovery_maintenance_permit,
            recovery_live_lease_token,
            now_epoch=now_epoch,
        ):
            result["reasons"].append("FRESH_RECOVERY_LEASE_NOT_LIVE")
            return result
        result["same_permit_instance_verified"] = True
        result["lease_live_verified_synthetic"] = True
        result["store_instance_bound_synthetic"] = True
        result["deadline_revalidated"] = True
        result["synthetic_store_double_called"] = True
        recovered = self._store.reconcile_attested_transaction_offline_double(
            recovery_command.raw_transaction_sha256,
            recovery_maintenance_attestation,
        )
        valid_recovery = bool(
            isinstance(recovered, Mapping)
            and recovered.get("ok") is True
            and recovered.get("status")
            == "SYNTHETIC_STORE_DOUBLE_RECOVERY_ABORTED_SOURCE_INTACT"
            and recovered.get("terminal_state") == "ABORTED"
            and recovered.get("transaction_sha256")
            == recovery_command.raw_transaction_sha256
            and recovered.get("source_raw_document_sha256")
            == recovery_command.source_raw_document_sha256
            and recovered.get("candidate_raw_document_sha256")
            == recovery_command.candidate_raw_document_sha256
            and recovered.get("prepared_record_sha256")
            == recovery_command.prepared_record_sha256
            and recovered.get("recovery_maintenance_epoch")
            == recovery_maintenance_permit.maintenance_epoch
            and _valid_sha256(recovered.get("terminal_record_sha256"))
            and recovered.get("production_store_called") is False
            and recovered.get("write_executed") is False
            and recovered.get("registry_write") is False
        )
        if not valid_recovery:
            result["reasons"].append("SYNTHETIC_RECOVERY_POSTCONDITIONS_INVALID")
            result["recovery_required"] = True
            return result
        receipt = {
            "recovery_command_sha256": recovery_command.command_sha256,
            "raw_transaction_sha256": recovery_command.raw_transaction_sha256,
            "store_instance_sha256": self._store.instance_sha256,
            "fresh_maintenance_epoch": recovery_maintenance_permit.maintenance_epoch,
            "terminal_state": "ABORTED",
            "terminal_record_sha256": recovered["terminal_record_sha256"],
            "postconditions_verified": True,
            "synthetic_store_double_called": True,
            "production_store_called": False,
            "write_executed": False,
            "registry_write": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["recovery_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_SYNTHETIC_PREPARED_TRANSACTION_RECOVERED_ABORTED_OFFLINE",
            postconditions_verified=True,
            recovery_required=False,
            invocation_receipt=receipt,
            synthetic_store_result=recovered,
        )
        return result


__all__ = [
    "DormantRawTransactionInvocationSeamConfigV1",
    "DormantRawTransactionInvocationSeamV1",
    "InMemoryAttestedRawTransactionStoreDoubleV1",
    "OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1",
    "ProtectedSyntheticPreparedRecoveryCommandV1",
    "SYNTHETIC_RECOVERY_COMMAND_VERSION_V1",
    "SYNTHETIC_STORE_BINDING_VERSION_V1",
    "SyntheticStoreInterrupted",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_V1_VERSION",
]
