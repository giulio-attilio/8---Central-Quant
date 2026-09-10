"""Offline-only startup recovery contract for synthetic PREPARED records.

The contract plans and reconciles an in-memory ledger using protected recovery
receipts.  It does not import or call the production runtime, provider, store,
backend, Registry, filesystem, network, or broker.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_contract_v1 as receipt_port
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as binding_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-STARTUP-RECOVERY-CONTRACT-V1"
)
OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_OFFLINE_ONLY_V1"
)
SYNTHETIC_PREPARED_RECOVERY_RECORD_VERSION_V1 = (
    "C3_PREPARED_RECOVERY_LEDGER_RECORD_SYNTHETIC_V1"
)
SYNTHETIC_PREPARED_RECOVERY_LEDGER_SNAPSHOT_VERSION_V1 = (
    "C3_PREPARED_RECOVERY_LEDGER_SNAPSHOT_SYNTHETIC_V1"
)
PROTECTED_STARTUP_RECOVERY_PLAN_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_PLAN_OFFLINE_V1"
)
STARTUP_RECOVERY_PLAN_ITEM_VERSION_V1 = (
    "C3_STARTUP_RECOVERY_PLAN_ITEM_OFFLINE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_STATES = frozenset({"COMMITTED", "ABORTED", "ROLLED_BACK"})
_RECORD_KEYS = frozenset(
    {
        "record_version",
        "binding_sha256",
        "request_sha256",
        "transaction_sha256",
        "original_invocation_command_sha256",
        "backend_instance_sha256",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "prepared_record_sha256",
        "previous_maintenance_epoch",
        "prepared_at_epoch",
        "terminal_state",
        "terminal_receipt_sha256",
        "resolved_at_epoch",
        "synthetic_only",
        "durable",
        "production_evidence",
        "record_sha256",
    }
)
_LEDGER_SNAPSHOT_KEYS = frozenset(
    {
        "snapshot_version",
        "ledger_instance_sha256",
        "binding_sha256",
        "generation",
        "records",
        "record_count",
        "prepared_count",
        "terminal_count",
        "synthetic_only",
        "durable",
        "production_authority",
        "snapshot_sha256",
    }
)
_PLAN_ITEM_KEYS = frozenset(
    {
        "item_version",
        "record_sha256",
        "request_sha256",
        "transaction_sha256",
        "original_invocation_command_sha256",
        "backend_instance_sha256",
        "source_raw_document_sha256",
        "candidate_raw_document_sha256",
        "prepared_record_sha256",
        "previous_maintenance_epoch",
        "item_sha256",
    }
)
_PLAN_KEYS = frozenset(
    {
        "plan_version",
        "scope_attestation",
        "binding_sha256",
        "ledger_instance_sha256",
        "ledger_snapshot_sha256",
        "ledger_generation",
        "prepared_count",
        "items",
        "created_at_epoch",
        "deadline_epoch",
        "all_prepared_records_included",
        "atomic_batch_required",
        "synthetic_only",
        "production_authority",
        "backend_call_allowed",
        "runtime_integrated",
        "production_ready",
        "plan_sha256",
    }
)

_PRODUCTION_BLOCKERS = (
    "RECOVERY_LEDGER_IS_IN_MEMORY_AND_SYNTHETIC_ONLY",
    "PREPARED_RECORDS_ARE_NOT_DURABLE",
    "RECOVERY_RECEIPTS_ARE_SYNTHETIC_ONLY",
    "PRODUCTION_BACKEND_IS_NOT_IMPORTED_OR_CALLED",
    "PRODUCTION_STORE_AND_PROVIDER_ARE_NOT_IMPORTED_OR_CALLED",
    "REAL_STARTUP_IS_NOT_INTEGRATED",
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


def prepared_recovery_record_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("ledger record must be a mapping")
    return _hash_without(value, "record_sha256")


def prepared_recovery_ledger_snapshot_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("ledger snapshot must be a mapping")
    return _hash_without(value, "snapshot_sha256")


def startup_recovery_plan_item_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("plan item must be a mapping")
    return _hash_without(value, "item_sha256")


def startup_recovery_plan_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("startup recovery plan must be a mapping")
    return _hash_without(value, "plan_sha256")


def prepared_recovery_record_valid_v1(value: Any) -> bool:
    if type(value) is not dict or set(value) != _RECORD_KEYS:
        return False
    state = value.get("terminal_state")
    receipt_sha = value.get("terminal_receipt_sha256")
    resolved_at = value.get("resolved_at_epoch")
    supplied_sha = _valid_sha256(value.get("record_sha256"))
    try:
        return bool(
            value.get("record_version")
            == SYNTHETIC_PREPARED_RECOVERY_RECORD_VERSION_V1
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "binding_sha256",
                    "request_sha256",
                    "transaction_sha256",
                    "original_invocation_command_sha256",
                    "backend_instance_sha256",
                    "source_raw_document_sha256",
                    "candidate_raw_document_sha256",
                    "prepared_record_sha256",
                    "previous_maintenance_epoch",
                )
            )
            and type(value.get("prepared_at_epoch")) is int
            and value.get("prepared_at_epoch") >= 0
            and (
                (
                    state == "PREPARED"
                    and receipt_sha is None
                    and resolved_at is None
                )
                or (
                    state in _TERMINAL_STATES
                    and _valid_sha256(receipt_sha)
                    and type(resolved_at) is int
                    and resolved_at >= value.get("prepared_at_epoch")
                )
            )
            and value.get("synthetic_only") is True
            and value.get("durable") is False
            and value.get("production_evidence") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, prepared_recovery_record_sha256_v1(value)
            )
        )
    except Exception:
        return False


def _ledger_snapshot_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _LEDGER_SNAPSHOT_KEYS:
        return False
    records = value.get("records")
    supplied_sha = _valid_sha256(value.get("snapshot_sha256"))
    if not isinstance(records, list) or not all(
        prepared_recovery_record_valid_v1(record) for record in records
    ):
        return False
    transaction_ids = [record["transaction_sha256"] for record in records]
    prepared_count = sum(
        record["terminal_state"] == "PREPARED" for record in records
    )
    try:
        return bool(
            value.get("snapshot_version")
            == SYNTHETIC_PREPARED_RECOVERY_LEDGER_SNAPSHOT_VERSION_V1
            and _valid_sha256(value.get("ledger_instance_sha256"))
            and _valid_sha256(value.get("binding_sha256"))
            and type(value.get("generation")) is int
            and value.get("generation") >= 0
            and transaction_ids == sorted(transaction_ids)
            and len(set(transaction_ids)) == len(transaction_ids)
            and all(
                record["binding_sha256"] == value.get("binding_sha256")
                for record in records
            )
            and value.get("record_count") == len(records)
            and value.get("prepared_count") == prepared_count
            and value.get("terminal_count") == len(records) - prepared_count
            and value.get("synthetic_only") is True
            and value.get("durable") is False
            and value.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, prepared_recovery_ledger_snapshot_sha256_v1(value)
            )
        )
    except Exception:
        return False


def _plan_item_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _PLAN_ITEM_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("item_sha256"))
    try:
        return bool(
            value.get("item_version") == STARTUP_RECOVERY_PLAN_ITEM_VERSION_V1
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in _PLAN_ITEM_KEYS - {"item_version", "item_sha256"}
            )
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, startup_recovery_plan_item_sha256_v1(value)
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantProductionBackendStartupRecoveryConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_binding_sha256: str | None = field(default=None, repr=False)
    expected_initial_ledger_snapshot_sha256: str | None = field(
        default=None, repr=False
    )
    max_prepared_records: int = 64
    max_recovery_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_prepared_records <= 1024:
            raise ValueError("max_prepared_records must be between 1 and 1024")
        if not 1 <= self.max_recovery_seconds <= 300:
            raise ValueError("max_recovery_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedProductionBackendStartupRecoveryPlanV1:
    binding_sha256: str = field(repr=False)
    ledger_snapshot_sha256: str = field(repr=False)
    prepared_count: int = field(repr=False)
    deadline_epoch: int = field(repr=False)
    plan: Mapping[str, Any] = field(repr=False)
    plan_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionBackendStartupRecoveryPlanV1(<protected>)"


def protected_startup_recovery_plan_valid_v1(value: Any) -> bool:
    if not isinstance(value, ProtectedProductionBackendStartupRecoveryPlanV1):
        return False
    plan = value.plan
    if type(plan) is not dict or set(plan) != _PLAN_KEYS:
        return False
    items = plan.get("items")
    if not isinstance(items, list) or not all(_plan_item_valid(item) for item in items):
        return False
    transaction_ids = [item["transaction_sha256"] for item in items]
    supplied_sha = _valid_sha256(plan.get("plan_sha256"))
    try:
        return bool(
            plan.get("plan_version") == PROTECTED_STARTUP_RECOVERY_PLAN_VERSION_V1
            and plan.get("scope_attestation")
            == OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1
            and plan.get("binding_sha256") == value.binding_sha256
            and plan.get("ledger_snapshot_sha256")
            == value.ledger_snapshot_sha256
            and plan.get("prepared_count") == value.prepared_count == len(items)
            and plan.get("deadline_epoch") == value.deadline_epoch
            and all(
                _valid_sha256(plan.get(field_name))
                for field_name in (
                    "binding_sha256",
                    "ledger_instance_sha256",
                    "ledger_snapshot_sha256",
                )
            )
            and type(plan.get("ledger_generation")) is int
            and type(plan.get("created_at_epoch")) is int
            and type(plan.get("deadline_epoch")) is int
            and plan.get("created_at_epoch") < plan.get("deadline_epoch")
            and transaction_ids == sorted(transaction_ids)
            and len(set(transaction_ids)) == len(transaction_ids)
            and plan.get("all_prepared_records_included") is True
            and plan.get("atomic_batch_required") is True
            and plan.get("synthetic_only") is True
            and plan.get("production_authority") is False
            and plan.get("backend_call_allowed") is False
            and plan.get("runtime_integrated") is False
            and plan.get("production_ready") is False
            and supplied_sha
            and supplied_sha == value.plan_sha256
            and hmac.compare_digest(
                supplied_sha, startup_recovery_plan_sha256_v1(plan)
            )
        )
    except Exception:
        return False


def _canonical_protected_plan_copy(
    value: Any,
) -> ProtectedProductionBackendStartupRecoveryPlanV1 | None:
    if not isinstance(value, ProtectedProductionBackendStartupRecoveryPlanV1):
        return None
    try:
        plan = _canonical_copy(dict(value.plan))
        protected = ProtectedProductionBackendStartupRecoveryPlanV1(
            binding_sha256=plan["binding_sha256"],
            ledger_snapshot_sha256=plan["ledger_snapshot_sha256"],
            prepared_count=plan["prepared_count"],
            deadline_epoch=plan["deadline_epoch"],
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )
    except Exception:
        return None
    return protected if protected_startup_recovery_plan_valid_v1(protected) else None


def _canonical_protected_receipt_copy(
    value: Any,
) -> receipt_port.ProtectedProductionBackendTerminalPortReceiptV1 | None:
    if not isinstance(
        value, receipt_port.ProtectedProductionBackendTerminalPortReceiptV1
    ):
        return None
    try:
        receipt = _canonical_copy(dict(value.receipt))
        protected = receipt_port.ProtectedProductionBackendTerminalPortReceiptV1(
            operation=receipt["operation"],
            binding_sha256=receipt["binding_sha256"],
            request_sha256=receipt["request_sha256"],
            transaction_sha256=receipt["transaction_sha256"],
            terminal_state=receipt["terminal_state"],
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )
    except Exception:
        return None
    return (
        protected
        if receipt_port.protected_backend_terminal_port_receipt_valid_v1(protected)
        else None
    )


class InMemorySyntheticPreparedRecoveryLedgerV1:
    """Exact memory-only ledger; no filesystem or Registry surface exists."""

    def __init__(self, *, binding_sha256: str) -> None:
        normalized_binding = _valid_sha256(binding_sha256)
        if not normalized_binding:
            raise ValueError("binding_sha256 required")
        self._binding_sha256 = normalized_binding
        self._ledger_instance_sha256 = _stable_sha256(
            {
                "kind": "IN_MEMORY_SYNTHETIC_PREPARED_RECOVERY_LEDGER_V1",
                "binding_sha256": normalized_binding,
            }
        )
        self._generation = 0
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def seed_prepared_offline(self, record: Mapping[str, Any]) -> None:
        canonical = _canonical_copy(dict(record))
        if not (
            prepared_recovery_record_valid_v1(canonical)
            and canonical["terminal_state"] == "PREPARED"
            and canonical["binding_sha256"] == self._binding_sha256
        ):
            raise ValueError("synthetic PREPARED record invalid")
        transaction_sha = canonical["transaction_sha256"]
        with self._lock:
            if transaction_sha in self._records:
                raise ValueError("duplicate synthetic transaction")
            self._records[transaction_sha] = canonical
            self._generation += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            records = [
                _canonical_copy(self._records[key])
                for key in sorted(self._records)
            ]
            generation = self._generation
        prepared_count = sum(
            record["terminal_state"] == "PREPARED" for record in records
        )
        snapshot = {
            "snapshot_version": SYNTHETIC_PREPARED_RECOVERY_LEDGER_SNAPSHOT_VERSION_V1,
            "ledger_instance_sha256": self._ledger_instance_sha256,
            "binding_sha256": self._binding_sha256,
            "generation": generation,
            "records": records,
            "record_count": len(records),
            "prepared_count": prepared_count,
            "terminal_count": len(records) - prepared_count,
            "synthetic_only": True,
            "durable": False,
            "production_authority": False,
        }
        snapshot["snapshot_sha256"] = prepared_recovery_ledger_snapshot_sha256_v1(
            snapshot
        )
        return snapshot

    def apply_recovery_batch_offline(
        self,
        *,
        expected_snapshot_sha256: str,
        protected_receipts: Sequence[
            receipt_port.ProtectedProductionBackendTerminalPortReceiptV1
        ],
        resolved_at_epoch: int,
    ) -> dict[str, Any]:
        if type(resolved_at_epoch) is not int:
            raise ValueError("resolved_at_epoch invalid")
        with self._lock:
            current_records = {
                key: _canonical_copy(value) for key, value in self._records.items()
            }
            current_generation = self._generation
            current_snapshot = self._snapshot_from_state(
                current_records, current_generation
            )
            if not hmac.compare_digest(
                current_snapshot["snapshot_sha256"],
                str(expected_snapshot_sha256 or ""),
            ):
                raise ValueError("ledger compare-and-swap mismatch")
            receipts_by_transaction: dict[
                str,
                receipt_port.ProtectedProductionBackendTerminalPortReceiptV1,
            ] = {}
            for supplied_receipt in protected_receipts:
                protected = _canonical_protected_receipt_copy(supplied_receipt)
                if protected is None:
                    raise ValueError("protected recovery receipt invalid")
                if protected.operation != "RECOVERY":
                    raise ValueError("recovery receipt required")
                if protected.transaction_sha256 in receipts_by_transaction:
                    raise ValueError("duplicate recovery receipt")
                receipts_by_transaction[protected.transaction_sha256] = protected
            prepared_ids = {
                key
                for key, record in current_records.items()
                if record["terminal_state"] == "PREPARED"
            }
            if set(receipts_by_transaction) != prepared_ids:
                raise ValueError("complete recovery receipt set required")
            updated: dict[str, dict[str, Any]] = {}
            for transaction_sha in sorted(prepared_ids):
                record = current_records[transaction_sha]
                protected = receipts_by_transaction[transaction_sha]
                receipt = protected.receipt
                store_result = receipt["adapter_store_result"]
                if not (
                    protected.binding_sha256 == self._binding_sha256
                    and receipt["request_sha256"] == record["request_sha256"]
                    and receipt["original_invocation_command_sha256"]
                    == record["original_invocation_command_sha256"]
                    and receipt["backend_instance_sha256"]
                    == record["backend_instance_sha256"]
                    and receipt["previous_maintenance_epoch"]
                    == record["previous_maintenance_epoch"]
                    and store_result["source_raw_document_sha256"]
                    == record["source_raw_document_sha256"]
                    and store_result["candidate_raw_document_sha256"]
                    == record["candidate_raw_document_sha256"]
                    and store_result["prepared_record_sha256"]
                    == record["prepared_record_sha256"]
                    and receipt["terminal_state"] in _TERMINAL_STATES
                    and resolved_at_epoch >= record["prepared_at_epoch"]
                ):
                    raise ValueError("recovery receipt record binding mismatch")
                terminal = _canonical_copy(record)
                terminal.update(
                    terminal_state=receipt["terminal_state"],
                    terminal_receipt_sha256=protected.receipt_sha256,
                    resolved_at_epoch=resolved_at_epoch,
                )
                terminal["record_sha256"] = prepared_recovery_record_sha256_v1(
                    terminal
                )
                if not prepared_recovery_record_valid_v1(terminal):
                    raise ValueError("terminal ledger record invalid")
                updated[transaction_sha] = terminal
            self._records.update(updated)
            if updated:
                self._generation += 1
            return self._snapshot_from_state(self._records, self._generation)

    def _snapshot_from_state(
        self,
        records_by_id: Mapping[str, Mapping[str, Any]],
        generation: int,
    ) -> dict[str, Any]:
        records = [
            _canonical_copy(records_by_id[key]) for key in sorted(records_by_id)
        ]
        prepared_count = sum(
            record["terminal_state"] == "PREPARED" for record in records
        )
        snapshot = {
            "snapshot_version": SYNTHETIC_PREPARED_RECOVERY_LEDGER_SNAPSHOT_VERSION_V1,
            "ledger_instance_sha256": self._ledger_instance_sha256,
            "binding_sha256": self._binding_sha256,
            "generation": generation,
            "records": records,
            "record_count": len(records),
            "prepared_count": prepared_count,
            "terminal_count": len(records) - prepared_count,
            "synthetic_only": True,
            "durable": False,
            "production_authority": False,
        }
        snapshot["snapshot_sha256"] = prepared_recovery_ledger_snapshot_sha256_v1(
            snapshot
        )
        return snapshot


class DormantProductionBackendStartupRecoveryV1:
    def __init__(
        self,
        *,
        config: DormantProductionBackendStartupRecoveryConfigV1 | None = None,
        ledger: InMemorySyntheticPreparedRecoveryLedgerV1 | None = None,
    ) -> None:
        self._config = config or DormantProductionBackendStartupRecoveryConfigV1()
        self._ledger = ledger

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "binding_verified": False,
            "ledger_snapshot_verified": False,
            "all_prepared_records_planned": False,
            "all_recovery_receipts_verified": False,
            "atomic_batch_verified": False,
            "startup_clean": False,
            "in_memory_ledger_mutated": False,
            "durability_verified": False,
            "production_authority": False,
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "runtime_integrated": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "reasons": [],
            "protected_recovery_plan": None,
            "final_ledger_snapshot": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def _preconditions(
        self,
        result: dict[str, Any],
        *,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
    ) -> bool:
        if self._config.enabled is not True:
            result["reasons"].append("STARTUP_RECOVERY_DEFAULT_OFF")
            return False
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append("STARTUP_RECOVERY_OFFLINE_SCOPE_REQUIRED")
            return False
        expected_binding = _valid_sha256(self._config.expected_binding_sha256)
        if not (
            expected_binding
            and binding_contract.protected_provider_store_adapter_binding_valid_v1(
                protected_binding
            )
            and hmac.compare_digest(
                protected_binding.binding_sha256, expected_binding
            )
        ):
            result["reasons"].append("STARTUP_RECOVERY_BINDING_INVALID")
            return False
        result["binding_verified"] = True
        if type(self._ledger) is not InMemorySyntheticPreparedRecoveryLedgerV1:
            result["reasons"].append("EXACT_SYNTHETIC_RECOVERY_LEDGER_REQUIRED")
            return False
        return True

    def plan_startup_recovery_offline(
        self,
        *,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        now_epoch: int,
    ) -> dict[str, Any]:
        result = self._base()
        if not self._preconditions(result, protected_binding=protected_binding):
            return result
        if type(now_epoch) is not int:
            result["reasons"].append("STARTUP_RECOVERY_CLOCK_INVALID")
            return result
        snapshot = self._ledger.snapshot()
        expected_snapshot = _valid_sha256(
            self._config.expected_initial_ledger_snapshot_sha256
        )
        if not (
            expected_snapshot
            and _ledger_snapshot_valid(snapshot)
            and snapshot["binding_sha256"] == protected_binding.binding_sha256
            and hmac.compare_digest(snapshot["snapshot_sha256"], expected_snapshot)
        ):
            result["reasons"].append("STARTUP_RECOVERY_LEDGER_SNAPSHOT_INVALID")
            return result
        result["ledger_snapshot_verified"] = True
        prepared_records = [
            record
            for record in snapshot["records"]
            if record["terminal_state"] == "PREPARED"
        ]
        if len(prepared_records) > self._config.max_prepared_records:
            result["reasons"].append("STARTUP_RECOVERY_PREPARED_BUDGET_EXCEEDED")
            return result
        items = []
        for record in prepared_records:
            item = {
                "item_version": STARTUP_RECOVERY_PLAN_ITEM_VERSION_V1,
                "record_sha256": record["record_sha256"],
                "request_sha256": record["request_sha256"],
                "transaction_sha256": record["transaction_sha256"],
                "original_invocation_command_sha256": record[
                    "original_invocation_command_sha256"
                ],
                "backend_instance_sha256": record[
                    "backend_instance_sha256"
                ],
                "source_raw_document_sha256": record[
                    "source_raw_document_sha256"
                ],
                "candidate_raw_document_sha256": record[
                    "candidate_raw_document_sha256"
                ],
                "prepared_record_sha256": record["prepared_record_sha256"],
                "previous_maintenance_epoch": record[
                    "previous_maintenance_epoch"
                ],
            }
            item["item_sha256"] = startup_recovery_plan_item_sha256_v1(item)
            items.append(item)
        plan = {
            "plan_version": PROTECTED_STARTUP_RECOVERY_PLAN_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1,
            "binding_sha256": protected_binding.binding_sha256,
            "ledger_instance_sha256": snapshot["ledger_instance_sha256"],
            "ledger_snapshot_sha256": snapshot["snapshot_sha256"],
            "ledger_generation": snapshot["generation"],
            "prepared_count": len(items),
            "items": items,
            "created_at_epoch": now_epoch,
            "deadline_epoch": now_epoch + self._config.max_recovery_seconds,
            "all_prepared_records_included": True,
            "atomic_batch_required": True,
            "synthetic_only": True,
            "production_authority": False,
            "backend_call_allowed": False,
            "runtime_integrated": False,
            "production_ready": False,
        }
        plan["plan_sha256"] = startup_recovery_plan_sha256_v1(plan)
        protected_plan = ProtectedProductionBackendStartupRecoveryPlanV1(
            binding_sha256=plan["binding_sha256"],
            ledger_snapshot_sha256=plan["ledger_snapshot_sha256"],
            prepared_count=plan["prepared_count"],
            deadline_epoch=plan["deadline_epoch"],
            plan=_canonical_copy(plan),
            plan_sha256=plan["plan_sha256"],
        )
        if not protected_startup_recovery_plan_valid_v1(protected_plan):
            result["reasons"].append("STARTUP_RECOVERY_PLAN_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_PLANNED_OFFLINE_ONLY",
            all_prepared_records_planned=True,
            startup_clean=len(items) == 0,
            protected_recovery_plan=protected_plan,
        )
        return result

    def reconcile_startup_recovery_offline(
        self,
        *,
        protected_binding: binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        protected_plan: ProtectedProductionBackendStartupRecoveryPlanV1,
        protected_receipts: Sequence[
            receipt_port.ProtectedProductionBackendTerminalPortReceiptV1
        ],
        now_epoch: int,
    ) -> dict[str, Any]:
        result = self._base()
        if not self._preconditions(result, protected_binding=protected_binding):
            return result
        canonical_plan = _canonical_protected_plan_copy(protected_plan)
        if not (
            type(now_epoch) is int
            and canonical_plan is not None
            and canonical_plan.binding_sha256 == protected_binding.binding_sha256
            and canonical_plan.plan["created_at_epoch"] <= now_epoch
            and now_epoch < canonical_plan.deadline_epoch
        ):
            result["reasons"].append("STARTUP_RECOVERY_PLAN_OR_DEADLINE_INVALID")
            return result
        current = self._ledger.snapshot()
        if not (
            _ledger_snapshot_valid(current)
            and current["snapshot_sha256"]
            == canonical_plan.ledger_snapshot_sha256
            and current["ledger_instance_sha256"]
            == canonical_plan.plan["ledger_instance_sha256"]
            and current["generation"] == canonical_plan.plan["ledger_generation"]
        ):
            result["reasons"].append("STARTUP_RECOVERY_LEDGER_CHANGED_SINCE_PLAN")
            return result
        result["ledger_snapshot_verified"] = True
        receipts = list(protected_receipts or ())
        items_by_transaction = {
            item["transaction_sha256"]: item for item in canonical_plan.plan["items"]
        }
        if len(receipts) != canonical_plan.prepared_count:
            result["reasons"].append("COMPLETE_RECOVERY_RECEIPT_SET_REQUIRED")
            return result
        seen: set[str] = set()
        canonical_receipts = []
        for supplied_receipt in receipts:
            protected = _canonical_protected_receipt_copy(supplied_receipt)
            if protected is None:
                result["reasons"].append("PROTECTED_RECOVERY_RECEIPT_INVALID")
                return result
            canonical_receipts.append(protected)
            receipt = protected.receipt
            transaction_sha = protected.transaction_sha256
            item = items_by_transaction.get(transaction_sha)
            if transaction_sha in seen:
                result["reasons"].append("DUPLICATE_RECOVERY_RECEIPT")
                return result
            seen.add(transaction_sha)
            store_result = receipt["adapter_store_result"]
            if not (
                protected.operation == "RECOVERY"
                and item is not None
                and protected.binding_sha256 == canonical_plan.binding_sha256
                and receipt["request_sha256"] == item["request_sha256"]
                and receipt["original_invocation_command_sha256"]
                == item["original_invocation_command_sha256"]
                and receipt["backend_instance_sha256"]
                == item["backend_instance_sha256"]
                and receipt["previous_maintenance_epoch"]
                == item["previous_maintenance_epoch"]
                and store_result["source_raw_document_sha256"]
                == item["source_raw_document_sha256"]
                and store_result["candidate_raw_document_sha256"]
                == item["candidate_raw_document_sha256"]
                and store_result["prepared_record_sha256"]
                == item["prepared_record_sha256"]
                and receipt["completed_at_epoch"] <= now_epoch
                and receipt["deadline_epoch"] <= canonical_plan.deadline_epoch
            ):
                result["reasons"].append("RECOVERY_RECEIPT_PLAN_BINDING_INVALID")
                return result
        if seen != set(items_by_transaction):
            result["reasons"].append("COMPLETE_RECOVERY_RECEIPT_SET_REQUIRED")
            return result
        result["all_recovery_receipts_verified"] = True
        try:
            final_snapshot = self._ledger.apply_recovery_batch_offline(
                expected_snapshot_sha256=canonical_plan.ledger_snapshot_sha256,
                protected_receipts=canonical_receipts,
                resolved_at_epoch=now_epoch,
            )
        except Exception:
            result["reasons"].append("ATOMIC_RECOVERY_BATCH_FAILED_CLOSED")
            return result
        if not (
            _ledger_snapshot_valid(final_snapshot)
            and final_snapshot["prepared_count"] == 0
            and final_snapshot["terminal_count"] == final_snapshot["record_count"]
        ):
            result["reasons"].append("STARTUP_RECOVERY_POSTCONDITION_INVALID")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_BACKEND_STARTUP_RECOVERY_RECONCILED_OFFLINE_ONLY",
            all_prepared_records_planned=True,
            atomic_batch_verified=True,
            startup_clean=True,
            in_memory_ledger_mutated=bool(receipts),
            final_ledger_snapshot=final_snapshot,
        )
        return result


__all__ = [
    "DormantProductionBackendStartupRecoveryConfigV1",
    "DormantProductionBackendStartupRecoveryV1",
    "InMemorySyntheticPreparedRecoveryLedgerV1",
    "OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_PLAN_VERSION_V1",
    "ProtectedProductionBackendStartupRecoveryPlanV1",
    "STARTUP_RECOVERY_PLAN_ITEM_VERSION_V1",
    "SYNTHETIC_PREPARED_RECOVERY_LEDGER_SNAPSHOT_VERSION_V1",
    "SYNTHETIC_PREPARED_RECOVERY_RECORD_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STARTUP_RECOVERY_CONTRACT_V1_VERSION",
    "prepared_recovery_ledger_snapshot_sha256_v1",
    "prepared_recovery_record_sha256_v1",
    "prepared_recovery_record_valid_v1",
    "protected_startup_recovery_plan_valid_v1",
    "startup_recovery_plan_item_sha256_v1",
    "startup_recovery_plan_sha256_v1",
]
