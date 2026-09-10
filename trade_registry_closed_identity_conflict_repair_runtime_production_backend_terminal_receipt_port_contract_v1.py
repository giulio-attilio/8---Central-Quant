"""Dormant offline port for C3 backend apply/recovery terminal receipts.

Only hash-bound synthetic evidence and the protected provider/store/adapter
binding are accepted.  The port performs no backend, provider, Registry,
filesystem, runtime, network, or broker operation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as binding_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-TERMINAL-RECEIPT-PORT-CONTRACT-V1"
)
OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_OFFLINE_ONLY_V1"
)
SYNTHETIC_BACKEND_TERMINAL_EVIDENCE_VERSION_V1 = (
    "C3_PRODUCTION_BACKEND_TERMINAL_EVIDENCE_SYNTHETIC_V1"
)
PROTECTED_BACKEND_TERMINAL_PORT_RECEIPT_VERSION_V1 = (
    "C3_PROTECTED_PRODUCTION_BACKEND_TERMINAL_PORT_RECEIPT_OFFLINE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_STATES = frozenset({"COMMITTED", "ABORTED", "ROLLED_BACK"})
_APPLY_STATES = _TERMINAL_STATES | {"AMBIGUOUS"}
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "operation",
        "binding_sha256",
        "store_projection_sha256",
        "source_store_snapshot_sha256",
        "adapter_snapshot_sha256",
        "command_sha256",
        "original_invocation_command_sha256",
        "request_sha256",
        "transaction_sha256",
        "backend_instance_sha256",
        "authorization_consumption_receipt_sha256",
        "previous_maintenance_epoch",
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
        "completed_at_epoch",
        "deadline_observed",
        "durability_required",
        "durability_verified",
        "synthetic_only",
        "production_evidence",
        "write_executed",
        "registry_write",
        "evidence_sha256",
    }
)
_PORT_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "operation",
        "binding_sha256",
        "store_projection_sha256",
        "source_store_snapshot_sha256",
        "adapter_snapshot_sha256",
        "command_sha256",
        "original_invocation_command_sha256",
        "request_sha256",
        "transaction_sha256",
        "backend_instance_sha256",
        "authorization_consumption_receipt_sha256",
        "previous_maintenance_epoch",
        "maintenance_epoch",
        "terminal_state",
        "adapter_store_result",
        "adapter_store_result_sha256",
        "source_evidence_sha256",
        "deadline_epoch",
        "completed_at_epoch",
        "deadline_observed",
        "terminal_contract_normalized",
        "durability_required",
        "durability_verified",
        "synthetic_only",
        "production_authority",
        "backend_call_allowed",
        "runtime_integrated",
        "production_ready",
        "write_executed",
        "registry_write",
        "receipt_sha256",
    }
)

_PRODUCTION_BLOCKERS = (
    "TERMINAL_EVIDENCE_IS_SYNTHETIC_ONLY",
    "DURABILITY_IS_REQUIRED_BUT_NOT_VERIFIED",
    "PRODUCTION_BACKEND_IS_NOT_IMPORTED_OR_CALLED",
    "PRODUCTION_PROVIDER_AND_STORE_ARE_NOT_IMPORTED_OR_CALLED",
    "TERMINAL_RECORDS_ARE_NOT_PERSISTED",
    "STARTUP_RECOVERY_IS_NOT_INTEGRATED",
    "RUNTIME_IS_NOT_INTEGRATED",
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


def backend_terminal_evidence_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("terminal evidence must be a mapping")
    return _hash_without(value, "evidence_sha256")


def backend_terminal_port_receipt_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("terminal port receipt must be a mapping")
    return _hash_without(value, "receipt_sha256")


@dataclass(frozen=True)
class DormantProductionBackendTerminalReceiptPortConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_binding_sha256: str | None = field(default=None, repr=False)
    max_completion_window_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_completion_window_seconds <= 300:
            raise ValueError(
                "max_completion_window_seconds must be between 1 and 300"
            )


@dataclass(frozen=True, repr=False)
class ProtectedProductionBackendTerminalPortReceiptV1:
    operation: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    request_sha256: str = field(repr=False)
    transaction_sha256: str = field(repr=False)
    terminal_state: str = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionBackendTerminalPortReceiptV1(<protected>)"


def _operation_shape_valid(evidence: Mapping[str, Any]) -> bool:
    operation = evidence.get("operation")
    state = evidence.get("terminal_state")
    command_sha = evidence.get("command_sha256")
    original_command_sha = evidence.get("original_invocation_command_sha256")
    previous_epoch = evidence.get("previous_maintenance_epoch")
    maintenance_epoch = evidence.get("maintenance_epoch")
    if operation == "APPLY":
        return bool(
            state in _APPLY_STATES
            and command_sha == original_command_sha
            and previous_epoch is None
        )
    if operation == "RECOVERY":
        return bool(
            state in _TERMINAL_STATES
            and command_sha != original_command_sha
            and _valid_sha256(previous_epoch)
            and previous_epoch != maintenance_epoch
        )
    return False


def _terminal_semantics_valid(value: Mapping[str, Any]) -> bool:
    ambiguous = value.get("terminal_state") == "AMBIGUOUS"
    return bool(
        type(value.get("idempotent_replay")) is bool
        and (
            (
                ambiguous
                and value.get("operation") == "APPLY"
                and value.get("postconditions_verified") is False
                and value.get("recovery_required") is True
                and value.get("ambiguous") is True
            )
            or (
                not ambiguous
                and value.get("postconditions_verified") is True
                and value.get("recovery_required") is False
                and value.get("ambiguous") is False
            )
        )
    )


def _terminal_evidence_valid(
    value: Any,
    *,
    protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
    now_epoch: int,
    max_completion_window_seconds: int,
) -> bool:
    if type(value) is not dict or set(value) != _EVIDENCE_KEYS:
        return False
    binding = protected_binding.binding
    supplied_sha = _valid_sha256(value.get("evidence_sha256"))
    deadline_epoch = value.get("deadline_epoch")
    completed_at_epoch = value.get("completed_at_epoch")
    try:
        return bool(
            value.get("evidence_version")
            == SYNTHETIC_BACKEND_TERMINAL_EVIDENCE_VERSION_V1
            and value.get("binding_sha256") == protected_binding.binding_sha256
            and value.get("store_projection_sha256")
            == binding.get("store_projection_sha256")
            and value.get("source_store_snapshot_sha256")
            == binding.get("source_store_snapshot_sha256")
            and value.get("adapter_snapshot_sha256")
            == binding.get("adapter_snapshot_sha256")
            and value.get("backend_instance_sha256")
            == binding.get("backend_instance_sha256")
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "command_sha256",
                    "original_invocation_command_sha256",
                    "request_sha256",
                    "transaction_sha256",
                    "backend_instance_sha256",
                    "authorization_consumption_receipt_sha256",
                    "maintenance_epoch",
                    "source_raw_document_sha256",
                    "candidate_raw_document_sha256",
                    "prepared_record_sha256",
                    "terminal_record_sha256",
                )
            )
            and _operation_shape_valid(value)
            and _terminal_semantics_valid(value)
            and type(deadline_epoch) is int
            and type(completed_at_epoch) is int
            and completed_at_epoch == now_epoch
            and completed_at_epoch < deadline_epoch
            and 1 <= deadline_epoch - completed_at_epoch
            <= max_completion_window_seconds
            and value.get("deadline_observed") is True
            and value.get("durability_required") is True
            and value.get("durability_verified") is False
            and value.get("synthetic_only") is True
            and value.get("production_evidence") is False
            and value.get("write_executed") is False
            and value.get("registry_write") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, backend_terminal_evidence_sha256_v1(value)
            )
        )
    except Exception:
        return False


def protected_backend_terminal_port_receipt_valid_v1(value: Any) -> bool:
    if not isinstance(value, ProtectedProductionBackendTerminalPortReceiptV1):
        return False
    receipt = value.receipt
    if type(receipt) is not dict or set(receipt) != _PORT_RECEIPT_KEYS:
        return False
    store_result = receipt.get("adapter_store_result")
    if type(store_result) is not dict or set(store_result) != adapter_contract._STORE_RESULT_KEYS:
        return False
    supplied_receipt_sha = _valid_sha256(receipt.get("receipt_sha256"))
    supplied_result_sha = _valid_sha256(store_result.get("result_sha256"))
    try:
        return bool(
            receipt.get("receipt_version")
            == PROTECTED_BACKEND_TERMINAL_PORT_RECEIPT_VERSION_V1
            and receipt.get("operation") == value.operation
            and receipt.get("binding_sha256") == value.binding_sha256
            and receipt.get("request_sha256") == value.request_sha256
            and receipt.get("transaction_sha256") == value.transaction_sha256
            and receipt.get("terminal_state") == value.terminal_state
            and all(
                _valid_sha256(receipt.get(field_name))
                for field_name in (
                    "binding_sha256",
                    "store_projection_sha256",
                    "source_store_snapshot_sha256",
                    "adapter_snapshot_sha256",
                    "command_sha256",
                    "original_invocation_command_sha256",
                    "request_sha256",
                    "transaction_sha256",
                    "backend_instance_sha256",
                    "authorization_consumption_receipt_sha256",
                    "maintenance_epoch",
                    "adapter_store_result_sha256",
                    "source_evidence_sha256",
                )
            )
            and _operation_shape_valid(receipt)
            and type(receipt.get("deadline_epoch")) is int
            and type(receipt.get("completed_at_epoch")) is int
            and receipt.get("completed_at_epoch") < receipt.get("deadline_epoch")
            and receipt.get("adapter_store_result_sha256") == supplied_result_sha
            and store_result.get("operation") == value.operation
            and store_result.get("request_sha256") == value.request_sha256
            and store_result.get("transaction_sha256") == value.transaction_sha256
            and store_result.get("terminal_state") == value.terminal_state
            and store_result.get("store_snapshot_sha256")
            == receipt.get("adapter_snapshot_sha256")
            and store_result.get("backend_instance_sha256")
            == receipt.get("backend_instance_sha256")
            and store_result.get("maintenance_epoch")
            == receipt.get("maintenance_epoch")
            and store_result.get("deadline_epoch") == receipt.get("deadline_epoch")
            and all(
                _valid_sha256(store_result.get(field_name))
                for field_name in (
                    "store_snapshot_sha256",
                    "request_sha256",
                    "transaction_sha256",
                    "backend_instance_sha256",
                    "maintenance_epoch",
                    "source_raw_document_sha256",
                    "candidate_raw_document_sha256",
                    "prepared_record_sha256",
                    "terminal_record_sha256",
                )
            )
            and _terminal_semantics_valid(store_result)
            and store_result.get("deadline_observed") is True
            and store_result.get("synthetic_only") is True
            and store_result.get("production_evidence") is False
            and store_result.get("write_executed") is False
            and store_result.get("registry_write") is False
            and supplied_result_sha
            and hmac.compare_digest(
                supplied_result_sha,
                adapter_contract.synthetic_store_double_result_sha256_v1(
                    store_result
                ),
            )
            and receipt.get("deadline_observed") is True
            and receipt.get("terminal_contract_normalized") is True
            and receipt.get("durability_required") is True
            and receipt.get("durability_verified") is False
            and receipt.get("synthetic_only") is True
            and receipt.get("production_authority") is False
            and receipt.get("backend_call_allowed") is False
            and receipt.get("runtime_integrated") is False
            and receipt.get("production_ready") is False
            and receipt.get("write_executed") is False
            and receipt.get("registry_write") is False
            and supplied_receipt_sha
            and supplied_receipt_sha == value.receipt_sha256
            and hmac.compare_digest(
                supplied_receipt_sha,
                backend_terminal_port_receipt_sha256_v1(receipt),
            )
        )
    except Exception:
        return False


class DormantProductionBackendTerminalReceiptPortV1:
    def __init__(
        self,
        *,
        config: DormantProductionBackendTerminalReceiptPortConfigV1 | None = None,
    ) -> None:
        self._config = config or DormantProductionBackendTerminalReceiptPortConfigV1()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "binding_verified": False,
            "terminal_evidence_verified": False,
            "terminal_contract_normalized": False,
            "durability_required": True,
            "durability_verified": False,
            "production_authority": False,
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "runtime_integrated": False,
            "production_ready": False,
            "apply_allowed": False,
            "recovery_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "reasons": [],
            "protected_terminal_receipt": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def _normalize_offline(
        self,
        *,
        expected_operation: str,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        terminal_evidence: Mapping[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["reasons"].append("TERMINAL_RECEIPT_PORT_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append("TERMINAL_RECEIPT_PORT_OFFLINE_SCOPE_REQUIRED")
            return result
        expected_binding_sha = _valid_sha256(
            self._config.expected_binding_sha256
        )
        if not expected_binding_sha:
            result["reasons"].append("EXPECTED_PROTECTED_BINDING_SHA_REQUIRED")
            return result
        if not (
            binding_contract.protected_provider_store_adapter_binding_valid_v1(
                protected_binding
            )
            and hmac.compare_digest(
                protected_binding.binding_sha256, expected_binding_sha
            )
        ):
            result["reasons"].append("PROTECTED_PROVIDER_STORE_BINDING_INVALID")
            return result
        result["binding_verified"] = True
        if type(now_epoch) is not int:
            result["reasons"].append("TERMINAL_RECEIPT_PORT_CLOCK_INVALID")
            return result
        try:
            evidence = _canonical_copy(dict(terminal_evidence))
        except Exception:
            result["reasons"].append("SYNTHETIC_TERMINAL_EVIDENCE_INVALID")
            return result
        if evidence.get("operation") != expected_operation:
            result["reasons"].append("TERMINAL_RECEIPT_OPERATION_MISMATCH")
            return result
        if not _terminal_evidence_valid(
            evidence,
            protected_binding=protected_binding,
            now_epoch=now_epoch,
            max_completion_window_seconds=self._config.max_completion_window_seconds,
        ):
            result["reasons"].append("SYNTHETIC_TERMINAL_EVIDENCE_INVALID")
            return result
        result["terminal_evidence_verified"] = True
        store_result = {
            "result_version": adapter_contract.SYNTHETIC_STORE_DOUBLE_RESULT_VERSION_V1,
            "operation": evidence["operation"],
            "store_snapshot_sha256": evidence["adapter_snapshot_sha256"],
            "request_sha256": evidence["request_sha256"],
            "transaction_sha256": evidence["transaction_sha256"],
            "backend_instance_sha256": evidence["backend_instance_sha256"],
            "maintenance_epoch": evidence["maintenance_epoch"],
            "source_raw_document_sha256": evidence[
                "source_raw_document_sha256"
            ],
            "candidate_raw_document_sha256": evidence[
                "candidate_raw_document_sha256"
            ],
            "terminal_state": evidence["terminal_state"],
            "prepared_record_sha256": evidence["prepared_record_sha256"],
            "terminal_record_sha256": evidence["terminal_record_sha256"],
            "postconditions_verified": evidence["postconditions_verified"],
            "recovery_required": evidence["recovery_required"],
            "ambiguous": evidence["ambiguous"],
            "idempotent_replay": evidence["idempotent_replay"],
            "deadline_epoch": evidence["deadline_epoch"],
            "deadline_observed": True,
            "synthetic_only": True,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        }
        store_result["result_sha256"] = (
            adapter_contract.synthetic_store_double_result_sha256_v1(
                store_result
            )
        )
        receipt = {
            "receipt_version": PROTECTED_BACKEND_TERMINAL_PORT_RECEIPT_VERSION_V1,
            "operation": evidence["operation"],
            "binding_sha256": evidence["binding_sha256"],
            "store_projection_sha256": evidence["store_projection_sha256"],
            "source_store_snapshot_sha256": evidence[
                "source_store_snapshot_sha256"
            ],
            "adapter_snapshot_sha256": evidence["adapter_snapshot_sha256"],
            "command_sha256": evidence["command_sha256"],
            "original_invocation_command_sha256": evidence[
                "original_invocation_command_sha256"
            ],
            "request_sha256": evidence["request_sha256"],
            "transaction_sha256": evidence["transaction_sha256"],
            "backend_instance_sha256": evidence["backend_instance_sha256"],
            "authorization_consumption_receipt_sha256": evidence[
                "authorization_consumption_receipt_sha256"
            ],
            "previous_maintenance_epoch": evidence[
                "previous_maintenance_epoch"
            ],
            "maintenance_epoch": evidence["maintenance_epoch"],
            "terminal_state": evidence["terminal_state"],
            "adapter_store_result": _canonical_copy(store_result),
            "adapter_store_result_sha256": store_result["result_sha256"],
            "source_evidence_sha256": evidence["evidence_sha256"],
            "deadline_epoch": evidence["deadline_epoch"],
            "completed_at_epoch": evidence["completed_at_epoch"],
            "deadline_observed": True,
            "terminal_contract_normalized": True,
            "durability_required": True,
            "durability_verified": False,
            "synthetic_only": True,
            "production_authority": False,
            "backend_call_allowed": False,
            "runtime_integrated": False,
            "production_ready": False,
            "write_executed": False,
            "registry_write": False,
        }
        receipt["receipt_sha256"] = backend_terminal_port_receipt_sha256_v1(
            receipt
        )
        protected_receipt = ProtectedProductionBackendTerminalPortReceiptV1(
            operation=receipt["operation"],
            binding_sha256=receipt["binding_sha256"],
            request_sha256=receipt["request_sha256"],
            transaction_sha256=receipt["transaction_sha256"],
            terminal_state=receipt["terminal_state"],
            receipt=_canonical_copy(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_backend_terminal_port_receipt_valid_v1(
            protected_receipt
        ):
            result["reasons"].append("PROTECTED_TERMINAL_RECEIPT_INVALID")
            return result
        result.update(
            ok=True,
            status=f"C3_PRODUCTION_BACKEND_{expected_operation}_TERMINAL_RECEIPT_NORMALIZED_OFFLINE_ONLY",
            terminal_contract_normalized=True,
            protected_terminal_receipt=protected_receipt,
        )
        return result

    def normalize_apply_offline(
        self,
        *,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        terminal_evidence: Mapping[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        return self._normalize_offline(
            expected_operation="APPLY",
            protected_binding=protected_binding,
            terminal_evidence=terminal_evidence,
            now_epoch=now_epoch,
        )

    def normalize_recovery_offline(
        self,
        *,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        terminal_evidence: Mapping[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        return self._normalize_offline(
            expected_operation="RECOVERY",
            protected_binding=protected_binding,
            terminal_evidence=terminal_evidence,
            now_epoch=now_epoch,
        )


__all__ = [
    "DormantProductionBackendTerminalReceiptPortConfigV1",
    "DormantProductionBackendTerminalReceiptPortV1",
    "OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1",
    "PROTECTED_BACKEND_TERMINAL_PORT_RECEIPT_VERSION_V1",
    "ProtectedProductionBackendTerminalPortReceiptV1",
    "SYNTHETIC_BACKEND_TERMINAL_EVIDENCE_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_CONTRACT_V1_VERSION",
    "backend_terminal_evidence_sha256_v1",
    "backend_terminal_port_receipt_sha256_v1",
    "protected_backend_terminal_port_receipt_valid_v1",
]
