"""Protected terminal evidence for the temporary physical C3 backend V2.

This is an offline normalizer only.  It joins already-produced synthetic
request/result mappings and never calls a backend, filesystem, runtime,
network, broker, or production Registry.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_TERMINAL_EVIDENCE_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PHYSICAL-TERMINAL-EVIDENCE-CONTRACT-V2"
)
OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RAW_BACKEND_PHYSICAL_TERMINAL_EVIDENCE_OFFLINE_ONLY_V2"
)
PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2 = (
    "C3_DURABLE_RAW_BACKEND_PHYSICAL_TERMINAL_EVIDENCE_PROTECTED_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "operation", "backend_snapshot_sha256",
        "backend_instance_sha256", "backend_module_source_sha256",
        "registry_path_binding_sha256", "lock_namespace_sha256",
        "backend_result_sha256",
        "operation_request_sha256", "original_request_sha256",
        "transaction_sha256", "authorization_receipt_sha256",
        "original_authorization_receipt_sha256", "previous_maintenance_epoch",
        "maintenance_epoch", "source_raw_document_sha256",
        "candidate_raw_document_sha256", "catalog_record_sha256",
        "wal_prepared_record_sha256", "terminal_record_sha256",
        "terminal_state", "batch_epoch", "batch_plan_sha256",
        "prepared_catalog_sha256", "checkpoint_index", "deadline_epoch",
        "completed_at_epoch", "deadline_observed", "postconditions_verified",
        "recovery_required", "temporary_storage_only", "filesystem_accessed",
        "durability_required", "durability_verified", "synthetic_only",
        "production_evidence", "production_authority", "runtime_integrated",
        "activation_allowed", "live_allowed", "write_executed",
        "registry_write", "receipt_sha256",
    }
)


def physical_terminal_evidence_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("physical terminal evidence must be a mapping")
    return backend_contract.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


@dataclass(frozen=True, repr=False)
class ProtectedPhysicalTerminalEvidenceReceiptV2:
    operation: str = field(repr=False)
    transaction_sha256: str = field(repr=False)
    terminal_state: str = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedPhysicalTerminalEvidenceReceiptV2(<protected>)"


@dataclass(frozen=True)
class PhysicalTerminalEvidencePortConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_completion_window_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_completion_window_seconds <= 300:
            raise ValueError("max_completion_window_seconds must be between 1 and 300")


def protected_physical_terminal_evidence_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedPhysicalTerminalEvidenceReceiptV2):
        return False
    receipt = value.receipt
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        return False
    supplied = str(receipt.get("receipt_sha256") or "")
    operation = receipt.get("operation")
    apply_shape = bool(
        operation == "APPLY"
        and receipt.get("previous_maintenance_epoch") is None
        and receipt.get("catalog_record_sha256") is None
        and receipt.get("batch_epoch") is None
        and receipt.get("batch_plan_sha256") is None
        and receipt.get("prepared_catalog_sha256") is None
        and receipt.get("checkpoint_index") is None
        and receipt.get("authorization_receipt_sha256")
        == receipt.get("original_authorization_receipt_sha256")
    )
    recovery_shape = bool(
        operation == "RECOVERY"
        and _valid_sha256(receipt.get("previous_maintenance_epoch"))
        and receipt.get("previous_maintenance_epoch") != receipt.get("maintenance_epoch")
        and _valid_sha256(receipt.get("catalog_record_sha256"))
        and _valid_sha256(receipt.get("batch_epoch"))
        and _valid_sha256(receipt.get("batch_plan_sha256"))
        and _valid_sha256(receipt.get("prepared_catalog_sha256"))
        and type(receipt.get("checkpoint_index")) is int
        and receipt.get("authorization_receipt_sha256")
        != receipt.get("original_authorization_receipt_sha256")
    )
    try:
        return bool(
            receipt.get("receipt_version") == PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2
            and operation == value.operation
            and receipt.get("transaction_sha256") == value.transaction_sha256
            and receipt.get("terminal_state") == value.terminal_state
            and (apply_shape or recovery_shape)
            and all(
                _valid_sha256(receipt.get(key))
                for key in (
                    "backend_snapshot_sha256", "backend_instance_sha256",
                    "backend_module_source_sha256", "registry_path_binding_sha256",
                    "lock_namespace_sha256", "backend_result_sha256",
                    "operation_request_sha256",
                    "original_request_sha256", "transaction_sha256",
                    "authorization_receipt_sha256",
                    "original_authorization_receipt_sha256",
                    "maintenance_epoch", "source_raw_document_sha256",
                    "candidate_raw_document_sha256", "wal_prepared_record_sha256",
                    "terminal_record_sha256",
                )
            )
            and receipt.get("terminal_state") in {"COMMITTED", "ABORTED", "ROLLED_BACK", "AMBIGUOUS"}
            and type(receipt.get("deadline_epoch")) is int
            and type(receipt.get("completed_at_epoch")) is int
            and receipt.get("completed_at_epoch") < receipt.get("deadline_epoch")
            and receipt.get("deadline_observed") is True
            and receipt.get("postconditions_verified")
            is (receipt.get("terminal_state") != "AMBIGUOUS")
            and receipt.get("recovery_required")
            is (receipt.get("terminal_state") == "AMBIGUOUS")
            and receipt.get("temporary_storage_only") is True
            and receipt.get("filesystem_accessed") is True
            and receipt.get("durability_required") is True
            and receipt.get("durability_verified") is False
            and receipt.get("synthetic_only") is True
            and receipt.get("production_evidence") is False
            and receipt.get("production_authority") is False
            and receipt.get("runtime_integrated") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
            and type(receipt.get("write_executed")) is bool
            and type(receipt.get("registry_write")) is bool
            and (
                receipt.get("registry_write") is False
                or receipt.get("write_executed") is True
            )
            and supplied == value.receipt_sha256
            and hmac.compare_digest(
                supplied, physical_terminal_evidence_receipt_sha256_v2(receipt)
            )
        )
    except Exception:
        return False


class PhysicalTerminalEvidencePortV2:
    def __init__(
        self,
        config: PhysicalTerminalEvidencePortConfigV2 | None = None,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or PhysicalTerminalEvidencePortConfigV2()
        self._clock = clock or (lambda: 0)

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PHYSICAL_TERMINAL_EVIDENCE_V2_FAILED_CLOSED",
            "reason": reason,
            "protected_receipt": None,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "filesystem_accessed": False,
            "write_executed": False,
        }

    def _ready(self) -> str | None:
        if not self._config.enabled:
            return "PHYSICAL_TERMINAL_EVIDENCE_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2:
            return "PHYSICAL_TERMINAL_EVIDENCE_SCOPE_INVALID"
        return None

    def _protect(self, receipt: dict[str, Any]) -> dict[str, Any]:
        receipt["receipt_sha256"] = physical_terminal_evidence_receipt_sha256_v2(receipt)
        protected = ProtectedPhysicalTerminalEvidenceReceiptV2(
            operation=receipt["operation"],
            transaction_sha256=receipt["transaction_sha256"],
            terminal_state=receipt["terminal_state"],
            receipt=dict(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_physical_terminal_evidence_valid_v2(protected):
            return self._failed("PHYSICAL_TERMINAL_EVIDENCE_INTERNAL_VALIDATION_FAILED")
        return {
            "ok": True,
            "status": "PHYSICAL_TERMINAL_EVIDENCE_V2_PROTECTED_OFFLINE",
            "protected_receipt": protected,
            "receipt_sha256": protected.receipt_sha256,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "durability_verified": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "backend_called": False,
            "filesystem_accessed": False,
            "write_executed": False,
        }

    def _base_receipt(
        self,
        *,
        operation: str,
        snapshot: Mapping[str, Any],
        backend_result_sha256: str,
        operation_request_sha256: str,
        original_request_sha256: str,
        transaction_sha256: str,
        authorization_receipt_sha256: str,
        original_authorization_receipt_sha256: str,
        previous_maintenance_epoch: str | None,
        maintenance_epoch: str,
        source_raw_document_sha256: str,
        candidate_raw_document_sha256: str,
        catalog_record_sha256: str | None,
        wal_prepared_record_sha256: str,
        terminal_record_sha256: str,
        terminal_state: str,
        batch_epoch: str | None,
        batch_plan_sha256: str | None,
        prepared_catalog_sha256: str | None,
        checkpoint_index: int | None,
        deadline_epoch: int,
        postconditions_verified: bool,
        recovery_required: bool,
        write_executed: bool,
        registry_write: bool,
    ) -> dict[str, Any]:
        completed = int(self._clock())
        return {
            "receipt_version": PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2,
            "operation": operation,
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_module_source_sha256": snapshot["backend_module_source_sha256"],
            "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "backend_result_sha256": backend_result_sha256,
            "operation_request_sha256": operation_request_sha256,
            "original_request_sha256": original_request_sha256,
            "transaction_sha256": transaction_sha256,
            "authorization_receipt_sha256": authorization_receipt_sha256,
            "original_authorization_receipt_sha256": original_authorization_receipt_sha256,
            "previous_maintenance_epoch": previous_maintenance_epoch,
            "maintenance_epoch": maintenance_epoch,
            "source_raw_document_sha256": source_raw_document_sha256,
            "candidate_raw_document_sha256": candidate_raw_document_sha256,
            "catalog_record_sha256": catalog_record_sha256,
            "wal_prepared_record_sha256": wal_prepared_record_sha256,
            "terminal_record_sha256": terminal_record_sha256,
            "terminal_state": terminal_state,
            "batch_epoch": batch_epoch,
            "batch_plan_sha256": batch_plan_sha256,
            "prepared_catalog_sha256": prepared_catalog_sha256,
            "checkpoint_index": checkpoint_index,
            "deadline_epoch": deadline_epoch,
            "completed_at_epoch": completed,
            "deadline_observed": completed < deadline_epoch,
            "postconditions_verified": postconditions_verified,
            "recovery_required": recovery_required,
            "temporary_storage_only": True,
            "filesystem_accessed": True,
            "durability_required": True,
            "durability_verified": False,
            "synthetic_only": True,
            "production_evidence": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "write_executed": write_executed,
            "registry_write": registry_write,
        }

    def normalize_apply_offline(
        self,
        *,
        snapshot: Mapping[str, Any],
        request: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        now = int(self._clock())
        if (
            not backend_contract.backend_snapshot_valid_v2(snapshot)
            or snapshot.get("filesystem_accessed") is not True
            or not backend_contract.transaction_request_valid_v2(request, snapshot)
            or not backend_contract.transaction_result_valid_v2(result, request)
            or now >= request.get("deadline_epoch", 0)
            or request["deadline_epoch"] - now > self._config.max_completion_window_seconds
        ):
            return self._failed("PHYSICAL_APPLY_EVIDENCE_INVALID")
        receipt = self._base_receipt(
            operation="APPLY", snapshot=snapshot,
            backend_result_sha256=result["result_sha256"],
            operation_request_sha256=request["request_binding_sha256"],
            original_request_sha256=request["request_sha256"],
            transaction_sha256=request["transaction_sha256"],
            authorization_receipt_sha256=request["authorization_receipt_sha256"],
            original_authorization_receipt_sha256=request["authorization_receipt_sha256"],
            previous_maintenance_epoch=None,
            maintenance_epoch=request["maintenance_epoch"],
            source_raw_document_sha256=request["expected_raw_document_sha256"],
            candidate_raw_document_sha256=request["candidate_raw_document_sha256"],
            catalog_record_sha256=None,
            wal_prepared_record_sha256=result["prepared_record_sha256"],
            terminal_record_sha256=result["terminal_record_sha256"],
            terminal_state=result["terminal_state"],
            batch_epoch=None, batch_plan_sha256=None,
            prepared_catalog_sha256=None, checkpoint_index=None,
            deadline_epoch=result["deadline_epoch"],
            postconditions_verified=result["postconditions_verified"],
            recovery_required=result["recovery_required"],
            write_executed=result["write_executed"],
            registry_write=result["registry_write"],
        )
        return self._protect(receipt)

    def normalize_recovery_offline(
        self,
        *,
        snapshot: Mapping[str, Any],
        catalog_record: Mapping[str, Any],
        batch: Mapping[str, Any],
        request: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        now = int(self._clock())
        if (
            not backend_contract.backend_snapshot_valid_v2(snapshot)
            or snapshot.get("filesystem_accessed") is not True
            or not backend_contract.prepared_record_valid_v2(catalog_record, snapshot)
            or not backend_contract.recovery_batch_valid_v2(batch)
            or batch["backend_snapshot_sha256"] != snapshot["snapshot_sha256"]
            or not backend_contract.recovery_request_valid_v2(request, catalog_record, batch)
            or not backend_contract.recovery_result_valid_v2(result, request, batch["next_index"])
            or now >= request.get("deadline_epoch", 0)
            or request["deadline_epoch"] - now > self._config.max_completion_window_seconds
        ):
            return self._failed("PHYSICAL_RECOVERY_EVIDENCE_INVALID")
        receipt = self._base_receipt(
            operation="RECOVERY", snapshot=snapshot,
            backend_result_sha256=result["result_sha256"],
            operation_request_sha256=request["request_sha256"],
            original_request_sha256=request["original_request_sha256"],
            transaction_sha256=request["transaction_sha256"],
            authorization_receipt_sha256=request["recovery_authorization_receipt_sha256"],
            original_authorization_receipt_sha256=request["original_authorization_receipt_sha256"],
            previous_maintenance_epoch=request["previous_maintenance_epoch"],
            maintenance_epoch=request["fresh_maintenance_epoch"],
            source_raw_document_sha256=request["source_raw_document_sha256"],
            candidate_raw_document_sha256=request["candidate_raw_document_sha256"],
            catalog_record_sha256=request["prepared_record_sha256"],
            wal_prepared_record_sha256=request["wal_prepared_record_sha256"],
            terminal_record_sha256=result["terminal_record_sha256"],
            terminal_state=result["terminal_state"],
            batch_epoch=request["batch_epoch"],
            batch_plan_sha256=request["batch_plan_sha256"],
            prepared_catalog_sha256=request["catalog_sha256"],
            checkpoint_index=request["checkpoint_index"],
            deadline_epoch=result["deadline_epoch"],
            postconditions_verified=result["postconditions_verified"],
            recovery_required=False,
            write_executed=result["write_executed"],
            registry_write=result["registry_write"],
        )
        return self._protect(receipt)


__all__ = [
    "OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2",
    "PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2",
    "PhysicalTerminalEvidencePortConfigV2", "PhysicalTerminalEvidencePortV2",
    "ProtectedPhysicalTerminalEvidenceReceiptV2",
    "physical_terminal_evidence_receipt_sha256_v2",
    "protected_physical_terminal_evidence_valid_v2",
]
