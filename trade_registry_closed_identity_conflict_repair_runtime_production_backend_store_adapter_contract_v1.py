"""Offline-only adapter from the C3 backend boundary to a memory store double.

The adapter proves the future call shape without importing or invoking the
production store.  Its only accepted store is the exact in-memory double in
this module.  No filesystem, network, Registry, runtime, or broker surface is
available here.
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
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-STORE-ADAPTER-CONTRACT-V1"
)
OFFLINE_PRODUCTION_BACKEND_STORE_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_BACKEND_STORE_ADAPTER_OFFLINE_ONLY_V1"
)
SYNTHETIC_STORE_DOUBLE_SNAPSHOT_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_STORE_DOUBLE_SNAPSHOT_SYNTHETIC_V1"
)
SYNTHETIC_STORE_DOUBLE_RESULT_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_STORE_DOUBLE_RESULT_SYNTHETIC_V1"
)
SYNTHETIC_RECOVERY_TERMINAL_RECEIPT_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_RECOVERY_TERMINAL_RECEIPT_SYNTHETIC_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_KEYS = frozenset(
    {
        "snapshot_version",
        "store_instance_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "production_backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "request_schema_version",
        "result_schema_version",
        "recovery_request_schema_version",
        "apply_supported",
        "recovery_supported",
        "enabled",
        "synthetic_only",
        "durable",
        "production_backend_referenced",
        "production_authority",
        "snapshot_sha256",
    }
)
_STORE_RESULT_KEYS = frozenset(
    {
        "result_version",
        "operation",
        "store_snapshot_sha256",
        "request_sha256",
        "transaction_sha256",
        "backend_instance_sha256",
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
        "synthetic_only",
        "production_evidence",
        "write_executed",
        "registry_write",
        "result_sha256",
    }
)
_RECOVERY_TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "execution_scope",
        "recovery_command_sha256",
        "original_invocation_command_sha256",
        "original_request_sha256",
        "transaction_sha256",
        "store_snapshot_sha256",
        "backend_boundary_attestation_sha256",
        "backend_instance_sha256",
        "recovery_authorization_consumption_receipt_sha256",
        "previous_maintenance_epoch",
        "fresh_maintenance_epoch",
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

_PRODUCTION_BLOCKERS = (
    "STORE_IS_AN_IN_MEMORY_SYNTHETIC_DOUBLE",
    "STORE_DOUBLE_IS_NOT_DURABLE",
    "PRODUCTION_STORE_IS_NOT_IMPORTED_OR_CALLED",
    "PRODUCTION_BACKEND_IS_NOT_REFERENCED",
    "PRODUCTION_AUTHORITY_IS_FALSE",
    "RUNTIME_IS_NOT_INTEGRATED",
    "STARTUP_RECOVERY_IS_NOT_INTEGRATED",
    "READINESS_IS_NOT_ACTIVATED",
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


def synthetic_store_double_snapshot_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("store snapshot must be a mapping")
    return _hash_without(value, "snapshot_sha256")


def synthetic_store_double_result_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("store result must be a mapping")
    return _hash_without(value, "result_sha256")


def synthetic_recovery_terminal_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("recovery receipt must be a mapping")
    return _hash_without(value, "receipt_sha256")


@dataclass(frozen=True)
class DormantProductionBackendStoreAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_store_snapshot_sha256: str | None = field(default=None, repr=False)
    max_call_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_call_seconds <= 300:
            raise ValueError("max_call_seconds must be between 1 and 300")


class InMemoryProductionBackendStoreDoubleV1:
    """Exact memory-only store double; it never persists or mutates a Registry."""

    def __init__(
        self,
        *,
        backend_instance_sha256: str,
        registry_path_binding_sha256: str,
        production_backend_capability_attestation_sha256: str,
        apply_terminal_state: str = "COMMITTED",
        recovery_terminal_state: str = "COMMITTED",
    ) -> None:
        backend_sha = _valid_sha256(backend_instance_sha256)
        path_sha = _valid_sha256(registry_path_binding_sha256)
        capability_sha = _valid_sha256(
            production_backend_capability_attestation_sha256
        )
        apply_state = str(apply_terminal_state or "").upper().strip()
        recovery_state = str(recovery_terminal_state or "").upper().strip()
        if not (backend_sha and path_sha and capability_sha):
            raise ValueError("exact synthetic store identity required")
        if apply_state not in {"COMMITTED", "ABORTED", "ROLLED_BACK", "AMBIGUOUS"}:
            raise ValueError("apply_terminal_state invalid")
        if recovery_state not in {"COMMITTED", "ABORTED", "ROLLED_BACK"}:
            raise ValueError("recovery_terminal_state invalid")
        self._backend_sha = backend_sha
        self._path_sha = path_sha
        self._capability_sha = capability_sha
        self._apply_state = apply_state
        self._recovery_state = recovery_state
        self._store_instance_sha = _stable_sha256(
            {
                "kind": "IN_MEMORY_PRODUCTION_BACKEND_STORE_DOUBLE_V1",
                "backend_instance_sha256": backend_sha,
                "registry_path_binding_sha256": path_sha,
                "production_backend_capability_attestation_sha256": capability_sha,
            }
        )
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}
        self._apply_call_count = 0
        self._recovery_call_count = 0

    def snapshot(self) -> dict[str, Any]:
        value = {
            "snapshot_version": SYNTHETIC_STORE_DOUBLE_SNAPSHOT_VERSION_V1,
            "store_instance_sha256": self._store_instance_sha,
            "backend_instance_sha256": self._backend_sha,
            "registry_path_binding_sha256": self._path_sha,
            "production_backend_capability_attestation_sha256": self._capability_sha,
            "lock_namespace_sha256": coordinator.canonical_runtime_lock_namespace_v1(),
            "request_schema_version": envelope_contract.PRODUCTION_REQUEST_VERSION_V1,
            "result_schema_version": envelope_contract.PRODUCTION_RESULT_VERSION_V1,
            "recovery_request_schema_version": envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1,
            "apply_supported": True,
            "recovery_supported": True,
            "enabled": True,
            "synthetic_only": True,
            "durable": False,
            "production_backend_referenced": False,
            "production_authority": False,
        }
        value["snapshot_sha256"] = synthetic_store_double_snapshot_sha256_v1(
            value
        )
        return value

    def counters(self) -> dict[str, int]:
        with self._lock:
            return {
                "apply_call_count": self._apply_call_count,
                "recovery_call_count": self._recovery_call_count,
            }

    def _result(
        self,
        *,
        operation: str,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
        terminal_state: str,
        idempotent_replay: bool,
        prepared_record_sha256: str | None = None,
    ) -> dict[str, Any]:
        ambiguous = terminal_state == "AMBIGUOUS"
        prepared_sha = prepared_record_sha256 or _stable_sha256(
            {
                "kind": "SYNTHETIC_STORE_PREPARED_RECORD_V1",
                "transaction_sha256": request["transaction_sha256"],
            }
        )
        terminal_sha = _stable_sha256(
            {
                "kind": f"SYNTHETIC_STORE_{operation}_{terminal_state}_RECORD_V1",
                "transaction_sha256": request["transaction_sha256"],
                "maintenance_epoch": maintenance_attestation[
                    "maintenance_epoch"
                ],
            }
        )
        result = {
            "result_version": SYNTHETIC_STORE_DOUBLE_RESULT_VERSION_V1,
            "operation": operation,
            "store_snapshot_sha256": self.snapshot()["snapshot_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": self._backend_sha,
            "maintenance_epoch": maintenance_attestation["maintenance_epoch"],
            "source_raw_document_sha256": request[
                "expected_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": request[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": terminal_state,
            "prepared_record_sha256": prepared_sha,
            "terminal_record_sha256": terminal_sha,
            "postconditions_verified": not ambiguous,
            "recovery_required": ambiguous,
            "ambiguous": ambiguous,
            "idempotent_replay": idempotent_replay,
            "deadline_epoch": maintenance_attestation["expires_at_epoch"],
            "deadline_observed": True,
            "synthetic_only": True,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        result["result_sha256"] = synthetic_store_double_result_sha256_v1(result)
        return result

    def apply_attested_transaction(
        self,
        request: Mapping[str, Any],
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        canonical_request = _canonical_copy(dict(request))
        canonical_maintenance = _canonical_copy(dict(maintenance_attestation))
        if not (
            set(canonical_request) == envelope_contract._PRODUCTION_REQUEST_KEYS
            and canonical_request.get("request_sha256")
            == envelope_contract.production_request_sha256_v1(canonical_request)
            and canonical_request.get("backend_instance_sha256") == self._backend_sha
            and canonical_request.get("registry_path_binding_sha256")
            == self._path_sha
            and boundary_contract._maintenance_attestation_valid(
                canonical_maintenance,
                expected_epoch=canonical_request.get("maintenance_epoch"),
                deadline_epoch=canonical_maintenance.get("expires_at_epoch"),
            )
            and canonical_maintenance.get("expires_at_epoch")
            <= canonical_request.get("expires_at_epoch")
        ):
            raise ValueError("synthetic store apply input invalid")
        transaction_sha = canonical_request["transaction_sha256"]
        with self._lock:
            self._apply_call_count += 1
            existing = self._records.get(transaction_sha)
            if existing is not None:
                return self._result(
                    operation="APPLY",
                    request=existing["request"],
                    maintenance_attestation=canonical_maintenance,
                    terminal_state=existing["terminal_state"],
                    idempotent_replay=True,
                    prepared_record_sha256=existing["prepared_record_sha256"],
                )
            result = self._result(
                operation="APPLY",
                request=canonical_request,
                maintenance_attestation=canonical_maintenance,
                terminal_state=self._apply_state,
                idempotent_replay=False,
            )
            self._records[transaction_sha] = {
                "request": canonical_request,
                "original_maintenance_epoch": canonical_maintenance[
                    "maintenance_epoch"
                ],
                "terminal_state": self._apply_state,
                "prepared_record_sha256": result["prepared_record_sha256"],
            }
            return result

    def reconcile_attested_transaction(
        self,
        transaction_sha256: str,
        maintenance_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        transaction_sha = _valid_sha256(transaction_sha256)
        canonical_maintenance = _canonical_copy(dict(maintenance_attestation))
        with self._lock:
            self._recovery_call_count += 1
            record = self._records.get(transaction_sha)
            if not (
                record is not None
                and canonical_maintenance.get("maintenance_epoch")
                != record["original_maintenance_epoch"]
                and boundary_contract._maintenance_attestation_valid(
                    canonical_maintenance,
                    expected_epoch=canonical_maintenance.get("maintenance_epoch"),
                    deadline_epoch=canonical_maintenance.get("expires_at_epoch"),
                )
            ):
                raise ValueError("synthetic store recovery input invalid")
            if record["terminal_state"] in {"COMMITTED", "ABORTED", "ROLLED_BACK"}:
                previous = record.get("recovery_result")
                if not (
                    isinstance(previous, Mapping)
                    and previous.get("maintenance_epoch")
                    == canonical_maintenance.get("maintenance_epoch")
                ):
                    raise ValueError("synthetic store recovery lease mismatch")
                replay = _canonical_copy(previous)
                replay["idempotent_replay"] = True
                replay["result_sha256"] = synthetic_store_double_result_sha256_v1(
                    replay
                )
                return replay
            if record["terminal_state"] != "AMBIGUOUS":
                raise ValueError("synthetic store recovery state invalid")
            result = self._result(
                operation="RECOVERY",
                request=record["request"],
                maintenance_attestation=canonical_maintenance,
                terminal_state=self._recovery_state,
                idempotent_replay=False,
                prepared_record_sha256=record["prepared_record_sha256"],
            )
            record["terminal_state"] = self._recovery_state
            record["recovery_result"] = _canonical_copy(result)
            return result


def _store_snapshot_valid(
    snapshot: Any,
    *,
    invocation_command: Mapping[str, Any],
) -> bool:
    if not isinstance(snapshot, Mapping) or set(snapshot) != _SNAPSHOT_KEYS:
        return False
    supplied_sha = _valid_sha256(snapshot.get("snapshot_sha256"))
    try:
        return bool(
            snapshot.get("snapshot_version")
            == SYNTHETIC_STORE_DOUBLE_SNAPSHOT_VERSION_V1
            and _valid_sha256(snapshot.get("store_instance_sha256"))
            and snapshot.get("backend_instance_sha256")
            == invocation_command.get("backend_instance_sha256")
            and snapshot.get("registry_path_binding_sha256")
            == invocation_command.get("registry_path_binding_sha256")
            and snapshot.get("production_backend_capability_attestation_sha256")
            == invocation_command.get(
                "production_backend_capability_attestation_sha256"
            )
            and snapshot.get("lock_namespace_sha256")
            == coordinator.canonical_runtime_lock_namespace_v1()
            and snapshot.get("request_schema_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and snapshot.get("result_schema_version")
            == envelope_contract.PRODUCTION_RESULT_VERSION_V1
            and snapshot.get("recovery_request_schema_version")
            == envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1
            and snapshot.get("apply_supported") is True
            and snapshot.get("recovery_supported") is True
            and snapshot.get("enabled") is True
            and snapshot.get("synthetic_only") is True
            and snapshot.get("durable") is False
            and snapshot.get("production_backend_referenced") is False
            and snapshot.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                synthetic_store_double_snapshot_sha256_v1(snapshot),
            )
        )
    except Exception:
        return False


def _store_result_valid(
    result: Any,
    *,
    operation: str,
    request: Mapping[str, Any],
    maintenance_attestation: Mapping[str, Any],
    store_snapshot_sha256: str,
    allow_ambiguous: bool,
) -> bool:
    if not isinstance(result, Mapping) or set(result) != _STORE_RESULT_KEYS:
        return False
    supplied_sha = _valid_sha256(result.get("result_sha256"))
    state = str(result.get("terminal_state") or "")
    ambiguous = state == "AMBIGUOUS"
    allowed_states = (
        {"COMMITTED", "ABORTED", "ROLLED_BACK", "AMBIGUOUS"}
        if allow_ambiguous
        else {"COMMITTED", "ABORTED", "ROLLED_BACK"}
    )
    try:
        return bool(
            result.get("result_version") == SYNTHETIC_STORE_DOUBLE_RESULT_VERSION_V1
            and result.get("operation") == operation
            and result.get("store_snapshot_sha256") == store_snapshot_sha256
            and result.get("request_sha256") == request.get("request_sha256")
            and result.get("transaction_sha256")
            == request.get("transaction_sha256")
            and result.get("backend_instance_sha256")
            == request.get("backend_instance_sha256")
            and result.get("maintenance_epoch")
            == maintenance_attestation.get("maintenance_epoch")
            and result.get("source_raw_document_sha256")
            == request.get("expected_raw_document_sha256")
            and result.get("candidate_raw_document_sha256")
            == request.get("candidate_raw_document_sha256")
            and state in allowed_states
            and _valid_sha256(result.get("prepared_record_sha256"))
            and _valid_sha256(result.get("terminal_record_sha256"))
            and result.get("deadline_epoch")
            == maintenance_attestation.get("expires_at_epoch")
            and result.get("deadline_observed") is True
            and type(result.get("idempotent_replay")) is bool
            and result.get("synthetic_only") is True
            and result.get("production_evidence") is False
            and result.get("write_executed") is False
            and result.get("registry_write") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, synthetic_store_double_result_sha256_v1(result)
            )
            and (
                (
                    ambiguous
                    and result.get("postconditions_verified") is False
                    and result.get("recovery_required") is True
                    and result.get("ambiguous") is True
                )
                or (
                    not ambiguous
                    and result.get("postconditions_verified") is True
                    and result.get("recovery_required") is False
                    and result.get("ambiguous") is False
                )
            )
        )
    except Exception:
        return False


class DormantProductionBackendStoreAdapterV1:
    def __init__(
        self,
        *,
        config: DormantProductionBackendStoreAdapterConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_witness: consumer.InMemoryLiveMaintenanceLeaseWitnessV1 | None = None,
        boundary: boundary_contract.DormantProductionBackendBoundaryV1 | None = None,
        store_double: InMemoryProductionBackendStoreDoubleV1 | None = None,
    ) -> None:
        self._config = config or DormantProductionBackendStoreAdapterConfigV1()
        self._clock = clock
        self._lease_witness = lease_witness
        self._boundary = boundary
        self._store = store_double

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_BACKEND_STORE_ADAPTER_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "boundary_command_verified": False,
            "store_snapshot_verified_synthetic": False,
            "same_live_lease_verified_synthetic": False,
            "deadline_verified_synthetic": False,
            "store_double_called": False,
            "terminal_contract_normalized": False,
            "recovery_terminal_normalized": False,
            "production_authority": False,
            "production_store_called": False,
            "production_backend_called": False,
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
            "store_double_result": None,
            "terminal_result": None,
            "recovery_terminal_receipt": None,
        }

    def _enabled_now(self, result: dict[str, Any]) -> int | None:
        if self._config.enabled is not True:
            result["reasons"].append("PRODUCTION_BACKEND_STORE_ADAPTER_DEFAULT_OFF")
            return None
        if not _valid_sha256(self._config.expected_store_snapshot_sha256):
            result["reasons"].append(
                "EXPECTED_SYNTHETIC_STORE_SNAPSHOT_SHA_REQUIRED"
            )
            return None
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_BACKEND_STORE_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append(
                "PRODUCTION_BACKEND_STORE_ADAPTER_OFFLINE_SCOPE_REQUIRED"
            )
            return None
        if not (
            type(self._lease_witness)
            is consumer.InMemoryLiveMaintenanceLeaseWitnessV1
            and type(self._boundary)
            is boundary_contract.DormantProductionBackendBoundaryV1
            and type(self._store) is InMemoryProductionBackendStoreDoubleV1
        ):
            result["reasons"].append("EXACT_SYNTHETIC_STORE_ADAPTER_DEPENDENCIES_REQUIRED")
            return None
        try:
            now_epoch = self._clock() if callable(self._clock) else None
        except Exception:
            now_epoch = None
        if type(now_epoch) is not int:
            result["reasons"].append("PRODUCTION_BACKEND_STORE_ADAPTER_CLOCK_INVALID")
            return None
        return now_epoch

    def invoke_offline(
        self,
        *,
        envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
        invocation_command: boundary_contract.ProtectedProductionBackendInvocationCommandV1,
        maintenance_permit: coordinator.WriterMaintenancePermitV1,
        live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
    ) -> dict[str, Any]:
        result = self._base()
        now_epoch = self._enabled_now(result)
        if now_epoch is None:
            return result
        envelope_valid, request = envelope_contract._protected_request_valid(envelope)
        command_valid, command = boundary_contract._invocation_command_valid(
            invocation_command
        )
        if not (
            envelope_valid
            and request is not None
            and command_valid
            and command is not None
            and command["envelope_sha256"] == envelope.envelope_sha256
        ):
            result["reasons"].append("PRODUCTION_BACKEND_INVOCATION_COMMAND_INVALID")
            return result
        result["boundary_command_verified"] = True
        snapshot = self._store.snapshot()
        if not (
            _store_snapshot_valid(snapshot, invocation_command=command)
            and hmac.compare_digest(
                snapshot["snapshot_sha256"],
                str(self._config.expected_store_snapshot_sha256),
            )
        ):
            result["reasons"].append("SYNTHETIC_STORE_SNAPSHOT_BINDING_INVALID")
            return result
        result["store_snapshot_verified_synthetic"] = True
        if not (
            self._lease_witness.validate_live(
                maintenance_permit, live_lease_token, now_epoch=now_epoch
            )
            and maintenance_permit.maintenance_epoch
            == command["maintenance_attestation"]["maintenance_epoch"]
            and live_lease_token.expires_at_epoch >= command["deadline_epoch"]
        ):
            result["reasons"].append("SAME_LIVE_MAINTENANCE_LEASE_REQUIRED")
            return result
        result["same_live_lease_verified_synthetic"] = True
        if not now_epoch < command["deadline_epoch"]:
            result["reasons"].append("STORE_ADAPTER_INVOCATION_DEADLINE_EXPIRED")
            return result
        if command["deadline_epoch"] - now_epoch > self._config.max_call_seconds:
            result["reasons"].append("STORE_ADAPTER_CALL_BUDGET_EXCEEDED")
            return result
        result["deadline_verified_synthetic"] = True
        try:
            delegated = self._store.apply_attested_transaction(
                command["production_request"], command["maintenance_attestation"]
            )
        except Exception:
            result["reasons"].append("SYNTHETIC_STORE_DOUBLE_APPLY_FAILED_CLOSED")
            return result
        result["store_double_called"] = True
        try:
            completed_at = self._clock()
        except Exception:
            completed_at = None
        if type(completed_at) is not int or not completed_at < command["deadline_epoch"]:
            result["reasons"].append("STORE_ADAPTER_INVOCATION_DEADLINE_EXCEEDED")
            return result
        if not _store_result_valid(
            delegated,
            operation="APPLY",
            request=request,
            maintenance_attestation=command["maintenance_attestation"],
            store_snapshot_sha256=snapshot["snapshot_sha256"],
            allow_ambiguous=True,
        ):
            result["reasons"].append("SYNTHETIC_STORE_DOUBLE_RESULT_INVALID")
            return result
        receipt = {
            "receipt_version": boundary_contract.PRODUCTION_BACKEND_TERMINAL_RECEIPT_VERSION_V1,
            "execution_scope": "SYNTHETIC_BACKEND_BOUNDARY_EVALUATION",
            "command_sha256": command["command_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_boundary_attestation_sha256": command[
                "backend_boundary_attestation_sha256"
            ],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "authorization_consumption_receipt_sha256": request[
                "authorization_consumption_receipt_sha256"
            ],
            "maintenance_epoch": request["maintenance_epoch"],
            "source_raw_document_sha256": delegated[
                "source_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": delegated[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": delegated["terminal_state"],
            "prepared_record_sha256": delegated["prepared_record_sha256"],
            "terminal_record_sha256": delegated["terminal_record_sha256"],
            "postconditions_verified": delegated["postconditions_verified"],
            "recovery_required": delegated["recovery_required"],
            "ambiguous": delegated["ambiguous"],
            "idempotent_replay": delegated["idempotent_replay"],
            "deadline_epoch": command["deadline_epoch"],
            "deadline_observed": True,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        receipt["receipt_sha256"] = (
            boundary_contract.production_backend_terminal_receipt_sha256_v1(
                receipt
            )
        )
        normalized = self._boundary.normalize_terminal_receipt_offline(
            envelope=envelope,
            invocation_command=invocation_command,
            terminal_receipt=receipt,
        )
        if normalized.get("ok") is not True:
            result["reasons"].append("BOUNDARY_TERMINAL_NORMALIZATION_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_STORE_ADAPTER_INVOKED_SYNTHETIC_ONLY",
            terminal_contract_normalized=True,
            store_double_result=delegated,
            terminal_result=normalized["terminal_result"],
            terminal_state=normalized["terminal_state"],
            recovery_required=normalized["recovery_required"],
            production_blockers=list(_PRODUCTION_BLOCKERS),
        )
        return result

    def recover_offline(
        self,
        *,
        envelope: envelope_contract.ProtectedProductionInvocationEnvelopeV1,
        invocation_command: boundary_contract.ProtectedProductionBackendInvocationCommandV1,
        recovery_command: boundary_contract.ProtectedProductionBackendRecoveryCommandV1,
        fresh_maintenance_permit: coordinator.WriterMaintenancePermitV1,
        fresh_live_lease_token: consumer.ProtectedSyntheticLiveLeaseTokenV1,
    ) -> dict[str, Any]:
        result = self._base()
        now_epoch = self._enabled_now(result)
        if now_epoch is None:
            return result
        envelope_valid, request = envelope_contract._protected_request_valid(envelope)
        invocation_valid, invocation = boundary_contract._invocation_command_valid(
            invocation_command
        )
        recovery_valid, recovery = boundary_contract._recovery_command_valid(
            recovery_command
        )
        if not (
            envelope_valid
            and request is not None
            and invocation_valid
            and invocation is not None
            and recovery_valid
            and recovery is not None
            and invocation["envelope_sha256"] == envelope.envelope_sha256
            and recovery["original_invocation_command_sha256"]
            == invocation["command_sha256"]
            and recovery["original_request_sha256"] == request["request_sha256"]
        ):
            result["reasons"].append("PRODUCTION_BACKEND_RECOVERY_COMMAND_INVALID")
            return result
        result["boundary_command_verified"] = True
        snapshot = self._store.snapshot()
        if not (
            _store_snapshot_valid(snapshot, invocation_command=invocation)
            and hmac.compare_digest(
                snapshot["snapshot_sha256"],
                str(self._config.expected_store_snapshot_sha256),
            )
        ):
            result["reasons"].append("SYNTHETIC_STORE_SNAPSHOT_BINDING_INVALID")
            return result
        result["store_snapshot_verified_synthetic"] = True
        maintenance = recovery["fresh_maintenance_attestation"]
        if not (
            self._lease_witness.validate_live(
                fresh_maintenance_permit,
                fresh_live_lease_token,
                now_epoch=now_epoch,
            )
            and fresh_maintenance_permit.maintenance_epoch
            == maintenance["maintenance_epoch"]
            and fresh_live_lease_token.expires_at_epoch
            >= recovery["deadline_epoch"]
        ):
            result["reasons"].append("FRESH_LIVE_MAINTENANCE_LEASE_REQUIRED")
            return result
        result["same_live_lease_verified_synthetic"] = True
        if not now_epoch < recovery["deadline_epoch"]:
            result["reasons"].append("STORE_ADAPTER_RECOVERY_DEADLINE_EXPIRED")
            return result
        if recovery["deadline_epoch"] - now_epoch > self._config.max_call_seconds:
            result["reasons"].append("STORE_ADAPTER_RECOVERY_BUDGET_EXCEEDED")
            return result
        result["deadline_verified_synthetic"] = True
        try:
            delegated = self._store.reconcile_attested_transaction(
                recovery["transaction_sha256"], maintenance
            )
        except Exception:
            result["reasons"].append("SYNTHETIC_STORE_DOUBLE_RECOVERY_FAILED_CLOSED")
            return result
        result["store_double_called"] = True
        try:
            completed_at = self._clock()
        except Exception:
            completed_at = None
        if type(completed_at) is not int or not completed_at < recovery["deadline_epoch"]:
            result["reasons"].append("STORE_ADAPTER_RECOVERY_DEADLINE_EXCEEDED")
            return result
        if not _store_result_valid(
            delegated,
            operation="RECOVERY",
            request=request,
            maintenance_attestation=maintenance,
            store_snapshot_sha256=snapshot["snapshot_sha256"],
            allow_ambiguous=False,
        ):
            result["reasons"].append("SYNTHETIC_STORE_DOUBLE_RECOVERY_RESULT_INVALID")
            return result
        terminal_receipt = {
            "receipt_version": SYNTHETIC_RECOVERY_TERMINAL_RECEIPT_VERSION_V1,
            "execution_scope": "SYNTHETIC_STORE_ADAPTER_RECOVERY_EVALUATION",
            "recovery_command_sha256": recovery["command_sha256"],
            "original_invocation_command_sha256": invocation["command_sha256"],
            "original_request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "store_snapshot_sha256": snapshot["snapshot_sha256"],
            "backend_boundary_attestation_sha256": recovery[
                "backend_boundary_attestation_sha256"
            ],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "recovery_authorization_consumption_receipt_sha256": recovery[
                "recovery_authorization_consumption_receipt_sha256"
            ],
            "previous_maintenance_epoch": request["maintenance_epoch"],
            "fresh_maintenance_epoch": maintenance["maintenance_epoch"],
            "source_raw_document_sha256": delegated[
                "source_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": delegated[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": delegated["terminal_state"],
            "prepared_record_sha256": delegated["prepared_record_sha256"],
            "terminal_record_sha256": delegated["terminal_record_sha256"],
            "postconditions_verified": True,
            "recovery_required": False,
            "ambiguous": False,
            "idempotent_replay": delegated["idempotent_replay"],
            "deadline_epoch": recovery["deadline_epoch"],
            "deadline_observed": True,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        terminal_receipt["receipt_sha256"] = (
            synthetic_recovery_terminal_receipt_sha256_v1(terminal_receipt)
        )
        terminal_result = {
            "result_version": envelope_contract.PRODUCTION_RESULT_VERSION_V1,
            "execution_scope": "SYNTHETIC_CONTRACT_EVALUATION",
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "authorization_consumption_receipt_sha256": request[
                "authorization_consumption_receipt_sha256"
            ],
            "maintenance_epoch": request["maintenance_epoch"],
            "source_raw_document_sha256": delegated[
                "source_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": delegated[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": delegated["terminal_state"],
            "prepared_record_sha256": delegated["prepared_record_sha256"],
            "terminal_record_sha256": delegated["terminal_record_sha256"],
            "postconditions_verified": True,
            "recovery_required": False,
            "ambiguous": False,
            "idempotent_replay": delegated["idempotent_replay"],
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        terminal_result["result_sha256"] = (
            envelope_contract.terminal_result_sha256_v1(terminal_result)
        )
        evaluated = envelope_contract.evaluate_terminal_result_contract_offline_v1(
            envelope, terminal_result
        )
        receipt_valid = bool(
            set(terminal_receipt) == _RECOVERY_TERMINAL_RECEIPT_KEYS
            and terminal_receipt["receipt_sha256"]
            == synthetic_recovery_terminal_receipt_sha256_v1(terminal_receipt)
            and evaluated.get("ok") is True
        )
        if not receipt_valid:
            result["reasons"].append("RECOVERY_TERMINAL_NORMALIZATION_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_STORE_ADAPTER_RECOVERED_SYNTHETIC_ONLY",
            recovery_terminal_normalized=True,
            store_double_result=delegated,
            terminal_result=terminal_result,
            terminal_state=delegated["terminal_state"],
            recovery_required=False,
            recovery_terminal_receipt=terminal_receipt,
            production_blockers=list(_PRODUCTION_BLOCKERS),
        )
        return result


__all__ = [
    "DormantProductionBackendStoreAdapterConfigV1",
    "DormantProductionBackendStoreAdapterV1",
    "InMemoryProductionBackendStoreDoubleV1",
    "OFFLINE_PRODUCTION_BACKEND_STORE_ADAPTER_SCOPE_ATTESTATION_V1",
    "SYNTHETIC_RECOVERY_TERMINAL_RECEIPT_VERSION_V1",
    "SYNTHETIC_STORE_DOUBLE_RESULT_VERSION_V1",
    "SYNTHETIC_STORE_DOUBLE_SNAPSHOT_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_CONTRACT_V1_VERSION",
    "synthetic_recovery_terminal_receipt_sha256_v1",
    "synthetic_store_double_result_sha256_v1",
    "synthetic_store_double_snapshot_sha256_v1",
]
