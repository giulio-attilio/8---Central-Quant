"""Dormant offline adapter from a protected handoff to a raw-store request.

This module only proves that synthetic in-memory material can satisfy both
contracts.  It never opens a registry, invokes a transaction store, persists a
WAL, installs a runtime hook or grants apply/live authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1 as handoff


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-REQUEST-ADAPTER-V1"
)

OFFLINE_HANDOFF_RAW_REQUEST_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_OFFLINE_ONLY_V1"
)
CANONICAL_RAW_PROOF_VERSION_V1 = "C3_CANONICAL_TO_EXACT_RAW_PROOF_V1"
MAINTENANCE_ATTESTATION_VERSION_V1 = (
    "C3_SYNTHETIC_RAW_TRANSACTION_MAINTENANCE_ATTESTATION_V1"
)

_RAW_REQUEST_VERSION_V1 = "SYNTHETIC_RAW_REGISTRY_TRANSACTION_REQUEST_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
_PROOF_KEYS = frozenset(
    {
        "proof_version",
        "handoff_transaction_id",
        "handoff_command_sha256",
        "source_registry_sha256",
        "source_raw_document_sha256",
        "source_generation_token",
        "candidate_registry_sha256",
        "candidate_raw_document_sha256",
        "changed_paths_sha256",
        "maintenance_attestation_sha256",
        "maintenance_epoch",
        "issued_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "real_registry_accessed",
        "proof_sha256",
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
_PRODUCTION_BLOCKERS = (
    "ADAPTER_IS_SYNTHETIC_OFFLINE_ONLY",
    "SOURCE_SNAPSHOT_IS_CALLER_SUPPLIED_IN_MEMORY",
    "MAINTENANCE_ATTESTATION_IS_SYNTHETIC",
    "LOCK_NAMESPACE_IS_NOT_BOUND_TO_A_PRODUCTION_STORE",
    "PROTECTED_REQUEST_IS_NOT_SERIALIZABLE",
    "RAW_TRANSACTION_STORE_IS_NOT_INVOKED",
    "TRANSACTION_WAL_IS_NOT_CREATED",
    "RUNTIME_IS_NOT_INTEGRATED",
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


def canonical_raw_proof_sha256_v1(proof: Mapping[str, Any]) -> str:
    if not isinstance(proof, Mapping):
        raise TypeError("proof must be a mapping")
    return _receipt_sha256(proof, "proof_sha256")


def maintenance_attestation_sha256_v1(
    attestation: Mapping[str, Any],
) -> str:
    if not isinstance(attestation, Mapping):
        raise TypeError("attestation must be a mapping")
    return _receipt_sha256(attestation, "attestation_sha256")


def _json_path(parent: str, key: str) -> str:
    return f"{parent}.{key}" if parent else key


def _leaf_differences(source: Any, candidate: Any, parent: str = "") -> list[str]:
    if isinstance(source, Mapping) and isinstance(candidate, Mapping):
        paths: list[str] = []
        for key in sorted(set(source) | set(candidate), key=str):
            child = _json_path(parent, str(key))
            if key not in source or key not in candidate:
                paths.append(child)
            else:
                paths.extend(_leaf_differences(source[key], candidate[key], child))
        return paths
    if isinstance(source, list) and isinstance(candidate, list):
        paths = []
        for index in range(max(len(source), len(candidate))):
            child = f"{parent}[{index}]"
            if index >= len(source) or index >= len(candidate):
                paths.append(child)
            else:
                paths.extend(
                    _leaf_differences(source[index], candidate[index], child)
                )
        return paths
    return [] if source == candidate else [parent or "$root"]


@dataclass(frozen=True)
class DormantHandoffRawRequestAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_proof_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_proof_ttl_seconds <= 300:
            raise ValueError("max_proof_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedHandoffRawTransactionRequestV1:
    handoff_transaction_id: str = field(repr=False)
    handoff_command_sha256: str = field(repr=False)
    raw_transaction_sha256: str = field(repr=False)
    canonical_raw_proof_sha256: str = field(repr=False)
    maintenance_attestation_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    request: Mapping[str, Any] = field(repr=False)
    maintenance_attestation: Mapping[str, Any] = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHandoffRawTransactionRequestV1(<protected>)"


def _command_integrity_valid(
    command: Any,
    now_epoch: int,
) -> bool:
    if type(command) is not handoff.ProtectedDurableHandoffCommandV1:
        return False
    binding = {
        "gateway_receipt_sha256": command.gateway_receipt_sha256,
        "authorization_receipt_sha256": command.authorization_receipt_sha256,
        "handoff_intent_sha256": command.handoff_intent_sha256,
        "preview_receipt_sha256": command.preview_receipt_sha256,
        "controller_instance_sha256": command.controller_instance_sha256,
        "source_registry_sha256": command.source_registry_sha256,
        "candidate_registry_sha256": command.candidate_registry_sha256,
        "changed_paths_sha256": command.changed_paths_sha256,
        "expires_at_epoch": command.expires_at_epoch,
    }
    sha_fields = (
        command.transaction_id,
        command.idempotency_key,
        command.handoff_binding_sha256,
        command.gateway_receipt_sha256,
        command.authorization_receipt_sha256,
        command.handoff_intent_sha256,
        command.preview_receipt_sha256,
        command.controller_instance_sha256,
        command.source_registry_sha256,
        command.candidate_registry_sha256,
        command.changed_paths_sha256,
        command.wal_prepared_record_sha256,
        command.command_sha256,
    )
    try:
        return bool(
            command.command_version == handoff.HANDOFF_COMMAND_VERSION_V1
            and all(_valid_sha256(value) for value in sha_fields)
            and command.idempotency_key == command.transaction_id
            and command.handoff_binding_sha256 == _stable_sha256(binding)
            and command.transaction_id
            == handoff.deterministic_handoff_transaction_id_v1(binding)
            and type(command.expires_at_epoch) is int
            and now_epoch < command.expires_at_epoch
            and hmac.compare_digest(
                command.command_sha256,
                handoff.protected_handoff_command_sha256_v1(command),
            )
        )
    except Exception:
        return False


def _snapshot_values(
    snapshot: Any,
) -> tuple[bool, Mapping[str, Any] | None, str]:
    if type(snapshot) is not raw_store.ExactRawRegistrySnapshotV1:
        return False, None, ""
    try:
        decoded = json.loads(snapshot.raw_bytes.decode("utf-8"))
        payload = json.loads(_canonical_json(dict(snapshot.payload)))
        decoded_canonical = json.loads(_canonical_json(decoded))
    except Exception:
        return False, None, ""
    valid = bool(
        isinstance(decoded, Mapping)
        and isinstance(snapshot.payload, Mapping)
        and decoded_canonical == payload
        and type(snapshot.raw_bytes) is bytes
        and type(snapshot.size_bytes) is int
        and snapshot.size_bytes == len(snapshot.raw_bytes)
        and _valid_sha256(snapshot.raw_document_sha256)
        and hmac.compare_digest(
            snapshot.raw_document_sha256,
            _bytes_sha256(snapshot.raw_bytes),
        )
        and _valid_sha256(snapshot.generation_token)
    )
    return valid, payload if valid else None, _stable_sha256(payload) if valid else ""


def _maintenance_valid(
    attestation: Any,
    command: handoff.ProtectedDurableHandoffCommandV1,
    now_epoch: int,
    max_ttl: int,
) -> bool:
    if not isinstance(attestation, Mapping) or set(attestation) != _MAINTENANCE_KEYS:
        return False
    supplied = _valid_sha256(attestation.get("attestation_sha256"))
    try:
        return bool(
            attestation.get("attestation_version")
            == MAINTENANCE_ATTESTATION_VERSION_V1
            and attestation.get("state") == "QUIESCED"
            and _valid_sha256(attestation.get("maintenance_epoch"))
            and _valid_sha256(attestation.get("lock_namespace_sha256"))
            and attestation.get("registered_writer_count") == 19
            and attestation.get("inflight_mutations") == 0
            and attestation.get("shared_lock_acquired") is True
            and type(attestation.get("issued_at_epoch")) is int
            and type(attestation.get("expires_at_epoch")) is int
            and attestation["issued_at_epoch"] <= now_epoch
            and now_epoch < attestation["expires_at_epoch"]
            and attestation["expires_at_epoch"] <= command.expires_at_epoch
            and 0
            < attestation["expires_at_epoch"] - attestation["issued_at_epoch"]
            <= max_ttl
            and attestation.get("synthetic_only") is True
            and attestation.get("production_evidence") is False
            and supplied
            and hmac.compare_digest(
                supplied,
                maintenance_attestation_sha256_v1(attestation),
            )
        )
    except Exception:
        return False


class DormantHandoffRawTransactionRequestAdapterV1:
    def __init__(
        self,
        *,
        config: DormantHandoffRawRequestAdapterConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or DormantHandoffRawRequestAdapterConfigV1()
        self._clock = clock

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_HANDOFF_RAW_REQUEST_ADAPTER_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "handoff_verified": False,
            "source_snapshot_verified": False,
            "canonical_raw_proof_verified": False,
            "changed_paths_verified": False,
            "maintenance_attestation_verified_synthetic": False,
            "deadline_verified": False,
            "request_projected": False,
            "request_serialization_allowed": False,
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
            "protected_request": None,
            "adapter_receipt": None,
        }

    def project_offline(
        self,
        *,
        command: handoff.ProtectedDurableHandoffCommandV1,
        source_snapshot: raw_store.ExactRawRegistrySnapshotV1,
        candidate_registry: Mapping[str, Any],
        changed_paths: Sequence[str],
        canonical_raw_proof: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]

        if self._config.enabled is not True:
            reasons.append("ADAPTER_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_HANDOFF_RAW_REQUEST_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            reasons.append("ADAPTER_OFFLINE_SCOPE_ATTESTATION_REQUIRED")
            return result
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            reasons.append("ADAPTER_CLOCK_INVALID")
            return result

        checks["handoff_command_integrity"] = _command_integrity_valid(
            command, now_epoch
        )
        if not checks["handoff_command_integrity"]:
            reasons.append("HANDOFF_COMMAND_INVALID_OR_EXPIRED")
            return result
        result["handoff_verified"] = True
        result["deadline_verified"] = True

        snapshot_valid, source_payload, source_logical_sha = _snapshot_values(
            source_snapshot
        )
        checks["exact_source_snapshot"] = snapshot_valid
        if not snapshot_valid or source_payload is None:
            reasons.append("SOURCE_SNAPSHOT_INVALID")
            return result
        checks["source_logical_binding"] = hmac.compare_digest(
            source_logical_sha, command.source_registry_sha256
        )
        if not checks["source_logical_binding"]:
            reasons.append("SOURCE_LOGICAL_HASH_MISMATCH")
            return result
        result["source_snapshot_verified"] = True

        try:
            candidate = json.loads(_canonical_json(dict(candidate_registry)))
            supplied_paths = sorted(str(path) for path in changed_paths)
            actual_paths = sorted(_leaf_differences(source_payload, candidate))
            candidate_logical_sha = _stable_sha256(candidate)
            candidate_raw_sha = _bytes_sha256(
                _canonical_json(candidate).encode("utf-8")
            )
            changed_paths_sha = _stable_sha256(supplied_paths)
        except Exception:
            reasons.append("CANDIDATE_OR_CHANGED_PATHS_INVALID")
            return result
        checks["candidate_logical_binding"] = bool(
            isinstance(candidate_registry, Mapping)
            and hmac.compare_digest(
                candidate_logical_sha, command.candidate_registry_sha256
            )
        )
        checks["changed_paths_exact"] = bool(
            supplied_paths
            and len(supplied_paths) == len(set(supplied_paths))
            and supplied_paths == actual_paths
            and hmac.compare_digest(changed_paths_sha, command.changed_paths_sha256)
        )
        if not checks["candidate_logical_binding"]:
            reasons.append("CANDIDATE_LOGICAL_HASH_MISMATCH")
            return result
        if not checks["changed_paths_exact"]:
            reasons.append("CHANGED_PATHS_BINDING_INVALID")
            return result
        result["changed_paths_verified"] = True

        checks["maintenance_attestation"] = _maintenance_valid(
            maintenance_attestation,
            command,
            now_epoch,
            self._config.max_proof_ttl_seconds,
        )
        if not checks["maintenance_attestation"]:
            reasons.append("MAINTENANCE_ATTESTATION_INVALID")
            return result
        result["maintenance_attestation_verified_synthetic"] = True
        maintenance_sha = maintenance_attestation["attestation_sha256"]
        maintenance_epoch = maintenance_attestation["maintenance_epoch"]

        supplied_proof_sha = (
            _valid_sha256(canonical_raw_proof.get("proof_sha256"))
            if isinstance(canonical_raw_proof, Mapping)
            else ""
        )
        proof_valid = False
        if isinstance(canonical_raw_proof, Mapping):
            try:
                proof_valid = bool(
                    set(canonical_raw_proof) == _PROOF_KEYS
                    and canonical_raw_proof.get("proof_version")
                    == CANONICAL_RAW_PROOF_VERSION_V1
                    and canonical_raw_proof.get("handoff_transaction_id")
                    == command.transaction_id
                    and canonical_raw_proof.get("handoff_command_sha256")
                    == command.command_sha256
                    and canonical_raw_proof.get("source_registry_sha256")
                    == source_logical_sha
                    and canonical_raw_proof.get("source_raw_document_sha256")
                    == source_snapshot.raw_document_sha256
                    and canonical_raw_proof.get("source_generation_token")
                    == source_snapshot.generation_token
                    and canonical_raw_proof.get("candidate_registry_sha256")
                    == candidate_logical_sha
                    and canonical_raw_proof.get("candidate_raw_document_sha256")
                    == candidate_raw_sha
                    and canonical_raw_proof.get("changed_paths_sha256")
                    == changed_paths_sha
                    and canonical_raw_proof.get("maintenance_attestation_sha256")
                    == maintenance_sha
                    and canonical_raw_proof.get("maintenance_epoch")
                    == maintenance_epoch
                    and type(canonical_raw_proof.get("issued_at_epoch")) is int
                    and type(canonical_raw_proof.get("expires_at_epoch")) is int
                    and canonical_raw_proof["issued_at_epoch"] <= now_epoch
                    and now_epoch < canonical_raw_proof["expires_at_epoch"]
                    and canonical_raw_proof["expires_at_epoch"]
                    <= maintenance_attestation["expires_at_epoch"]
                    and 0
                    < canonical_raw_proof["expires_at_epoch"]
                    - canonical_raw_proof["issued_at_epoch"]
                    <= self._config.max_proof_ttl_seconds
                    and canonical_raw_proof.get("synthetic_only") is True
                    and canonical_raw_proof.get("real_registry_accessed") is False
                    and supplied_proof_sha
                    and hmac.compare_digest(
                        supplied_proof_sha,
                        canonical_raw_proof_sha256_v1(canonical_raw_proof),
                    )
                )
            except Exception:
                proof_valid = False
        checks["canonical_to_exact_raw_proof"] = proof_valid
        if not proof_valid:
            reasons.append("CANONICAL_RAW_PROOF_INVALID")
            return result
        result["canonical_raw_proof_verified"] = True

        try:
            request = raw_store.build_raw_transaction_request_v1(
                source_snapshot,
                candidate,
                idempotency_key=command.idempotency_key,
                maintenance_epoch=maintenance_epoch,
            )
        except Exception:
            reasons.append("RAW_TRANSACTION_REQUEST_BUILD_FAILED")
            return result
        request_valid = bool(
            set(request) == _RAW_REQUEST_KEYS
            and request.get("request_version") == _RAW_REQUEST_VERSION_V1
            and request.get("scope_attestation")
            == raw_store.SYNTHETIC_TEMPORARY_STORAGE_ATTESTATION_V1
            and request.get("idempotency_key") == command.transaction_id
            and request.get("maintenance_epoch") == maintenance_epoch
            and request.get("expected_raw_document_sha256")
            == source_snapshot.raw_document_sha256
            and request.get("expected_generation_token")
            == source_snapshot.generation_token
            and request.get("candidate_registry") == candidate
            and request.get("candidate_raw_document_sha256")
            == candidate_raw_sha
            and _valid_sha256(request.get("transaction_sha256"))
            and hmac.compare_digest(
                request["transaction_sha256"],
                raw_store.raw_transaction_request_sha256_v1(request),
            )
        )
        checks["raw_request_exact_schema"] = request_valid
        if not request_valid:
            reasons.append("RAW_TRANSACTION_REQUEST_INTEGRITY_FAILED")
            return result

        protected = ProtectedHandoffRawTransactionRequestV1(
            handoff_transaction_id=command.transaction_id,
            handoff_command_sha256=command.command_sha256,
            raw_transaction_sha256=request["transaction_sha256"],
            canonical_raw_proof_sha256=supplied_proof_sha,
            maintenance_attestation_sha256=maintenance_sha,
            expires_at_epoch=canonical_raw_proof["expires_at_epoch"],
            request=request,
            maintenance_attestation=json.loads(
                _canonical_json(dict(maintenance_attestation))
            ),
        )
        receipt = {
            "handoff_transaction_id": command.transaction_id,
            "handoff_command_sha256": command.command_sha256,
            "raw_transaction_sha256": request["transaction_sha256"],
            "canonical_raw_proof_sha256": supplied_proof_sha,
            "maintenance_attestation_sha256": maintenance_sha,
            "source_registry_sha256": source_logical_sha,
            "source_raw_document_sha256": source_snapshot.raw_document_sha256,
            "candidate_registry_sha256": candidate_logical_sha,
            "candidate_raw_document_sha256": candidate_raw_sha,
            "changed_paths_sha256": changed_paths_sha,
            "expires_at_epoch": canonical_raw_proof["expires_at_epoch"],
            "request_projected": True,
            "request_material_exposed": False,
            "raw_transaction_store_called": False,
            "transaction_persistence_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["adapter_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_HANDOFF_RAW_TRANSACTION_REQUEST_PROJECTED_OFFLINE",
            request_projected=True,
            protected_request=protected,
            adapter_receipt=receipt,
        )
        return result


__all__ = [
    "CANONICAL_RAW_PROOF_VERSION_V1",
    "DormantHandoffRawRequestAdapterConfigV1",
    "DormantHandoffRawTransactionRequestAdapterV1",
    "MAINTENANCE_ATTESTATION_VERSION_V1",
    "OFFLINE_HANDOFF_RAW_REQUEST_ADAPTER_SCOPE_ATTESTATION_V1",
    "ProtectedHandoffRawTransactionRequestV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_REQUEST_ADAPTER_V1_VERSION",
    "canonical_raw_proof_sha256_v1",
    "maintenance_attestation_sha256_v1",
]
