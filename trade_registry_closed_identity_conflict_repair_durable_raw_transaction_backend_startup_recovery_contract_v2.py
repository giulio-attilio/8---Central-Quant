"""Resumable offline startup recovery contract for the C3 physical backend V2.

The contract only validates protected mappings.  It does not import runtime
code or call a backend, filesystem, Registry, network, broker, or service.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_STARTUP_RECOVERY_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-STARTUP-RECOVERY-CONTRACT-V2"
)
OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RAW_BACKEND_STARTUP_RECOVERY_OFFLINE_ONLY_V2"
)
STARTUP_RECOVERY_STATE_VERSION_V2 = (
    "C3_DURABLE_RAW_BACKEND_STARTUP_RECOVERY_STATE_PROTECTED_V2"
)
STARTUP_RECOVERY_COMPLETION_VERSION_V2 = (
    "C3_DURABLE_RAW_BACKEND_STARTUP_RECOVERY_COMPLETION_PROTECTED_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_STATE_KEYS = frozenset(
    {
        "state_version", "scope_attestation", "backend_snapshot",
        "prepared_catalog", "recovery_batch", "terminal_receipt_sha256s",
        "prior_state_sha256s", "receipt_count", "next_index", "complete", "created_at_epoch",
        "deadline_epoch", "synthetic_only", "temporary_storage_only",
        "durable", "production_authority", "backend_call_allowed",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "state_sha256",
    }
)
_COMPLETION_KEYS = frozenset(
    {
        "completion_version", "startup_state_sha256", "backend_instance_sha256",
        "initial_backend_snapshot_sha256", "final_backend_snapshot_sha256",
        "initial_prepared_catalog_sha256", "final_prepared_catalog_sha256",
        "initial_generation", "final_generation", "recovered_count",
        "terminal_receipt_sha256s", "prepared_catalog_drained",
        "completed_at_epoch", "deadline_epoch", "synthetic_only",
        "temporary_storage_only", "durable", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "completion_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_contract.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def startup_recovery_state_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "state_sha256")


def startup_recovery_completion_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "completion_sha256")


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryStateV2:
    backend_instance_sha256: str = field(repr=False)
    prepared_catalog_sha256: str = field(repr=False)
    next_index: int = field(repr=False)
    complete: bool = field(repr=False)
    state: Mapping[str, Any] = field(repr=False)
    state_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryStateV2(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryCompletionV2:
    backend_instance_sha256: str = field(repr=False)
    recovered_count: int = field(repr=False)
    completion: Mapping[str, Any] = field(repr=False)
    completion_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryCompletionV2(<protected>)"


@dataclass(frozen=True)
class StartupRecoveryConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_prepared_records: int = 64
    max_recovery_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_prepared_records <= 1024:
            raise ValueError("max_prepared_records must be between 1 and 1024")
        if not 1 <= self.max_recovery_seconds <= 300:
            raise ValueError("max_recovery_seconds must be between 1 and 300")


def protected_startup_recovery_state_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedStartupRecoveryStateV2):
        return False
    state = value.state
    if type(state) is not dict or set(state) != _STATE_KEYS:
        return False
    snapshot = state.get("backend_snapshot")
    catalog = state.get("prepared_catalog")
    batch = state.get("recovery_batch")
    receipts = state.get("terminal_receipt_sha256s")
    prior_states = state.get("prior_state_sha256s")
    supplied = str(state.get("state_sha256") or "")
    try:
        return bool(
            state.get("state_version") == STARTUP_RECOVERY_STATE_VERSION_V2
            and state.get("scope_attestation") == OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2
            and backend_contract.backend_snapshot_valid_v2(snapshot)
            and snapshot.get("filesystem_accessed") is True
            and backend_contract.prepared_catalog_valid_v2(catalog, snapshot)
            and backend_contract.recovery_batch_valid_v2(batch)
            and batch.get("backend_instance_sha256") == snapshot.get("backend_instance_sha256")
            and batch.get("backend_snapshot_sha256") == snapshot.get("snapshot_sha256")
            and batch.get("catalog_sha256") == catalog.get("catalog_sha256")
            and batch.get("item_count") == catalog.get("prepared_count")
            and batch.get("item_record_sha256s")
            == [record["record_sha256"] for record in catalog["records"]]
            and isinstance(receipts, list) and all(_valid_sha(item) for item in receipts)
            and len(receipts) == len(set(receipts))
            and isinstance(prior_states, list)
            and all(_valid_sha(item) for item in prior_states)
            and len(prior_states) == len(set(prior_states)) == len(receipts)
            and state.get("receipt_count") == len(receipts)
            and state.get("next_index") == batch.get("next_index") == len(receipts)
            and state.get("complete") is batch.get("complete")
            and type(state.get("created_at_epoch")) is int
            and type(state.get("deadline_epoch")) is int
            and state.get("created_at_epoch") < state.get("deadline_epoch")
            and state.get("deadline_epoch") == batch.get("deadline_epoch")
            and state.get("synthetic_only") is True
            and state.get("temporary_storage_only") is True
            and state.get("durable") is False
            and state.get("production_authority") is False
            and state.get("backend_call_allowed") is False
            and state.get("runtime_integrated") is False
            and state.get("activation_allowed") is False
            and state.get("live_allowed") is False
            and value.backend_instance_sha256 == snapshot.get("backend_instance_sha256")
            and value.prepared_catalog_sha256 == catalog.get("catalog_sha256")
            and value.next_index == state.get("next_index")
            and value.complete is state.get("complete")
            and supplied == value.state_sha256
            and hmac.compare_digest(supplied, startup_recovery_state_sha256_v2(state))
        )
    except Exception:
        return False


def protected_startup_recovery_completion_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedStartupRecoveryCompletionV2):
        return False
    completion = value.completion
    if type(completion) is not dict or set(completion) != _COMPLETION_KEYS:
        return False
    supplied = str(completion.get("completion_sha256") or "")
    receipts = completion.get("terminal_receipt_sha256s")
    try:
        return bool(
            completion.get("completion_version") == STARTUP_RECOVERY_COMPLETION_VERSION_V2
            and all(
                _valid_sha(completion.get(key))
                for key in (
                    "startup_state_sha256", "backend_instance_sha256",
                    "initial_backend_snapshot_sha256", "final_backend_snapshot_sha256",
                    "initial_prepared_catalog_sha256", "final_prepared_catalog_sha256",
                )
            )
            and type(completion.get("initial_generation")) is int
            and type(completion.get("final_generation")) is int
            and completion.get("final_generation")
            == completion.get("initial_generation") + completion.get("recovered_count")
            and isinstance(receipts, list) and all(_valid_sha(item) for item in receipts)
            and len(receipts) == len(set(receipts))
            and completion.get("recovered_count") == len(receipts)
            and completion.get("prepared_catalog_drained") is True
            and type(completion.get("completed_at_epoch")) is int
            and completion.get("completed_at_epoch") < completion.get("deadline_epoch")
            and completion.get("synthetic_only") is True
            and completion.get("temporary_storage_only") is True
            and completion.get("durable") is False
            and completion.get("production_authority") is False
            and completion.get("runtime_integrated") is False
            and completion.get("activation_allowed") is False
            and completion.get("live_allowed") is False
            and value.backend_instance_sha256 == completion.get("backend_instance_sha256")
            and value.recovered_count == completion.get("recovered_count")
            and supplied == value.completion_sha256
            and hmac.compare_digest(
                supplied, startup_recovery_completion_sha256_v2(completion)
            )
        )
    except Exception:
        return False


def _protected_state(state: dict[str, Any]) -> ProtectedStartupRecoveryStateV2:
    state["state_sha256"] = startup_recovery_state_sha256_v2(state)
    return ProtectedStartupRecoveryStateV2(
        backend_instance_sha256=state["backend_snapshot"]["backend_instance_sha256"],
        prepared_catalog_sha256=state["prepared_catalog"]["catalog_sha256"],
        next_index=state["next_index"],
        complete=state["complete"],
        state=copy.deepcopy(state),
        state_sha256=state["state_sha256"],
    )


class ResumableStartupRecoveryV2:
    def __init__(
        self,
        config: StartupRecoveryConfigV2 | None = None,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or StartupRecoveryConfigV2()
        self._clock = clock or (lambda: 0)

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "STARTUP_RECOVERY_V2_FAILED_CLOSED",
            "reason": reason,
            "protected_state": None,
            "protected_completion": None,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_authority": False,
            "backend_called": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _ready(self) -> str | None:
        if not self._config.enabled:
            return "STARTUP_RECOVERY_V2_DEFAULT_OFF"
        if self._config.scope_attestation != OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2:
            return "STARTUP_RECOVERY_V2_SCOPE_INVALID"
        return None

    def plan_offline(
        self, snapshot: Mapping[str, Any], catalog: Mapping[str, Any]
    ) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        now = int(self._clock())
        if (
            not backend_contract.backend_snapshot_valid_v2(snapshot)
            or snapshot.get("filesystem_accessed") is not True
            or not backend_contract.prepared_catalog_valid_v2(catalog, snapshot)
            or catalog.get("prepared_count", 0) > self._config.max_prepared_records
        ):
            return self._failed("STARTUP_RECOVERY_V2_SOURCE_INVALID")
        deadline = now + self._config.max_recovery_seconds
        batch = backend_contract.build_resumable_recovery_batch_offline_v2(
            snapshot,
            catalog,
            batch_epoch=backend_contract.stable_sha256_v2(
                {
                    "snapshot_sha256": snapshot["snapshot_sha256"],
                    "catalog_sha256": catalog["catalog_sha256"],
                    "created_at_epoch": now,
                }
            ),
            deadline_epoch=deadline,
        )
        state = {
            "state_version": STARTUP_RECOVERY_STATE_VERSION_V2,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2,
            "backend_snapshot": copy.deepcopy(dict(snapshot)),
            "prepared_catalog": copy.deepcopy(dict(catalog)),
            "recovery_batch": batch,
            "terminal_receipt_sha256s": [],
            "prior_state_sha256s": [],
            "receipt_count": 0,
            "next_index": 0,
            "complete": batch["complete"],
            "created_at_epoch": now,
            "deadline_epoch": deadline,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "durable": False,
            "production_authority": False,
            "backend_call_allowed": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        protected = _protected_state(state)
        if not protected_startup_recovery_state_valid_v2(protected):
            return self._failed("STARTUP_RECOVERY_V2_PLAN_INTERNAL_INVALID")
        return {
            "ok": True,
            "status": "STARTUP_RECOVERY_V2_PLANNED_OFFLINE",
            "protected_state": protected,
            "prepared_count": catalog["prepared_count"],
            "complete": protected.complete,
            "backend_called": False,
            "filesystem_accessed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def record_terminal_receipt_offline(
        self,
        state: ProtectedStartupRecoveryStateV2,
        receipt: terminal_contract.ProtectedPhysicalTerminalEvidenceReceiptV2,
    ) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        if (
            not protected_startup_recovery_state_valid_v2(state)
            or state.complete
            or not terminal_contract.protected_physical_terminal_evidence_valid_v2(receipt)
        ):
            return self._failed("STARTUP_RECOVERY_V2_STATE_OR_RECEIPT_INVALID")
        now = int(self._clock())
        current = copy.deepcopy(dict(state.state))
        batch = current["recovery_batch"]
        catalog = current["prepared_catalog"]
        if now >= current["deadline_epoch"]:
            return self._failed("STARTUP_RECOVERY_V2_DEADLINE_EXPIRED")
        expected_hash = batch["item_record_sha256s"][batch["next_index"]]
        expected = next(
            record for record in catalog["records"]
            if record["record_sha256"] == expected_hash
        )
        source = receipt.receipt
        bindings_valid = bool(
            receipt.operation == "RECOVERY"
            and source["backend_snapshot_sha256"] == current["backend_snapshot"]["snapshot_sha256"]
            and source["backend_instance_sha256"] == state.backend_instance_sha256
            and source["prepared_catalog_sha256"] == state.prepared_catalog_sha256
            and source["batch_epoch"] == batch["batch_epoch"]
            and source["batch_plan_sha256"] == batch["batch_plan_sha256"]
            and source["checkpoint_index"] == batch["next_index"]
            and source["catalog_record_sha256"] == expected["record_sha256"]
            and source["wal_prepared_record_sha256"] == expected["wal_prepared_record_sha256"]
            and source["transaction_sha256"] == expected["transaction_sha256"]
            and source["original_request_sha256"] == expected["request_sha256"]
            and source["original_authorization_receipt_sha256"] == expected["authorization_receipt_sha256"]
            and source["previous_maintenance_epoch"] == expected["previous_maintenance_epoch"]
            and source["source_raw_document_sha256"] == expected["source_raw_document_sha256"]
            and source["candidate_raw_document_sha256"] == expected["candidate_raw_document_sha256"]
            and source["deadline_epoch"] <= current["deadline_epoch"]
        )
        if not bindings_valid:
            return self._failed("STARTUP_RECOVERY_V2_RECEIPT_BINDING_MISMATCH")
        advanced_batch = copy.deepcopy(batch)
        advanced_batch["terminal_result_sha256s"] = [
            *advanced_batch["terminal_result_sha256s"],
            source["backend_result_sha256"],
        ]
        advanced_batch["next_index"] += 1
        advanced_batch["complete"] = (
            advanced_batch["next_index"] == advanced_batch["item_count"]
        )
        advanced_batch["batch_plan_sha256"] = _hash_without(
            advanced_batch, "batch_plan_sha256"
        )
        if not backend_contract.recovery_batch_valid_v2(advanced_batch):
            return self._failed("STARTUP_RECOVERY_V2_BATCH_ADVANCE_INVALID")
        current["recovery_batch"] = advanced_batch
        current["terminal_receipt_sha256s"] = [
            *current["terminal_receipt_sha256s"], receipt.receipt_sha256
        ]
        current["prior_state_sha256s"] = [
            *current["prior_state_sha256s"], state.state_sha256
        ]
        current["receipt_count"] += 1
        current["next_index"] = advanced_batch["next_index"]
        current["complete"] = advanced_batch["complete"]
        advanced = _protected_state(current)
        if not protected_startup_recovery_state_valid_v2(advanced):
            return self._failed("STARTUP_RECOVERY_V2_ADVANCED_STATE_INVALID")
        return {
            "ok": True,
            "status": (
                "STARTUP_RECOVERY_V2_RECEIPT_RECORDED_COMPLETE"
                if advanced.complete
                else "STARTUP_RECOVERY_V2_RECEIPT_RECORDED_CHECKPOINTED"
            ),
            "protected_state": advanced,
            "next_index": advanced.next_index,
            "complete": advanced.complete,
            "backend_called": False,
            "filesystem_accessed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def finalize_offline(
        self,
        state: ProtectedStartupRecoveryStateV2,
        final_snapshot: Mapping[str, Any],
        final_catalog: Mapping[str, Any],
    ) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        now = int(self._clock())
        if (
            not protected_startup_recovery_state_valid_v2(state)
            or not state.complete
            or now >= state.state["deadline_epoch"]
            or not backend_contract.backend_snapshot_valid_v2(final_snapshot)
            or not backend_contract.prepared_catalog_valid_v2(final_catalog, final_snapshot)
            or final_catalog["prepared_count"] != 0
            or final_snapshot["backend_instance_sha256"] != state.backend_instance_sha256
            or final_snapshot["registry_path_binding_sha256"]
            != state.state["backend_snapshot"]["registry_path_binding_sha256"]
            or final_snapshot["lock_namespace_sha256"]
            != state.state["backend_snapshot"]["lock_namespace_sha256"]
            or final_snapshot["generation"]
            != state.state["backend_snapshot"]["generation"] + state.state["receipt_count"]
        ):
            return self._failed("STARTUP_RECOVERY_V2_FINAL_CATALOG_NOT_DRAINED_OR_INVALID")
        completion = {
            "completion_version": STARTUP_RECOVERY_COMPLETION_VERSION_V2,
            "startup_state_sha256": state.state_sha256,
            "backend_instance_sha256": state.backend_instance_sha256,
            "initial_backend_snapshot_sha256": state.state["backend_snapshot"]["snapshot_sha256"],
            "final_backend_snapshot_sha256": final_snapshot["snapshot_sha256"],
            "initial_prepared_catalog_sha256": state.prepared_catalog_sha256,
            "final_prepared_catalog_sha256": final_catalog["catalog_sha256"],
            "initial_generation": state.state["backend_snapshot"]["generation"],
            "final_generation": final_snapshot["generation"],
            "recovered_count": state.state["receipt_count"],
            "terminal_receipt_sha256s": list(state.state["terminal_receipt_sha256s"]),
            "prepared_catalog_drained": True,
            "completed_at_epoch": now,
            "deadline_epoch": state.state["deadline_epoch"],
            "synthetic_only": True,
            "temporary_storage_only": True,
            "durable": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        completion["completion_sha256"] = startup_recovery_completion_sha256_v2(completion)
        protected = ProtectedStartupRecoveryCompletionV2(
            backend_instance_sha256=completion["backend_instance_sha256"],
            recovered_count=completion["recovered_count"],
            completion=copy.deepcopy(completion),
            completion_sha256=completion["completion_sha256"],
        )
        if not protected_startup_recovery_completion_valid_v2(protected):
            return self._failed("STARTUP_RECOVERY_V2_COMPLETION_INTERNAL_INVALID")
        return {
            "ok": True,
            "status": "STARTUP_RECOVERY_V2_COMPLETED_CATALOG_DRAINED_OFFLINE",
            "protected_completion": protected,
            "completion_sha256": protected.completion_sha256,
            "recovered_count": protected.recovered_count,
            "prepared_catalog_drained": True,
            "backend_called": False,
            "filesystem_accessed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }


__all__ = [
    "OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2",
    "ProtectedStartupRecoveryCompletionV2", "ProtectedStartupRecoveryStateV2",
    "ResumableStartupRecoveryV2", "StartupRecoveryConfigV2",
    "protected_startup_recovery_completion_valid_v2",
    "protected_startup_recovery_state_valid_v2",
    "startup_recovery_completion_sha256_v2", "startup_recovery_state_sha256_v2",
]
