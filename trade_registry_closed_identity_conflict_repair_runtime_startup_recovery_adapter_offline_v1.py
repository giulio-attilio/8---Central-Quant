"""Offline adapter from the temporary C3 WAL backend to startup readiness.

The adapter is dependency-injected and default-off.  It accepts only
synthetic temporary-backend evidence, binds every recovery request to the
maintenance permit supplied by the caller, and emits the sanitized
attestation consumed by the dormant runtime seam.  It has no runtime or
production entrypoint.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-RECOVERY-ADAPTER-OFFLINE-V1"
)
OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_RUNTIME_STARTUP_RECOVERY_ADAPTER_SYNTHETIC_TEMPORARY_ONLY_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LOG_AUDIT_KEYS = frozenset(
    {
        "audit_version",
        "backend_instance_sha256",
        "backend_snapshot_sha256",
        "lock_namespace_sha256",
        "wal_record_count",
        "transaction_count",
        "state_counts",
        "latest_state_counts",
        "unresolved_prepared_count",
        "unresolved_resolved_count",
        "resolved_state_supported",
        "wal_integrity_verified",
        "synthetic_only",
        "temporary_storage_only",
        "durable",
        "production_evidence",
        "filesystem_accessed",
        "audit_sha256",
    }
)
_WAL_STATES = ("PREPARED", "COMMITTED", "ABORTED", "ROLLED_BACK")


@dataclass(frozen=True)
class OfflineRuntimeStartupRecoveryAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _maintenance_permit_valid_v1(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and value.get("state") == "QUIESCED"
        and value.get("registered_writer_count") == 19
        and value.get("inflight_mutations") == 0
        and value.get("shared_lock_acquired") is True
        and _valid_sha256(value.get("maintenance_epoch"))
        and _valid_sha256(value.get("lock_namespace_sha256"))
    )


def temporary_transaction_log_audit_valid_v1(
    value: Any,
    snapshot: Mapping[str, Any],
) -> bool:
    if not isinstance(value, Mapping) or set(value) != _LOG_AUDIT_KEYS:
        return False
    state_counts = value.get("state_counts")
    latest_counts = value.get("latest_state_counts")
    supplied_sha = str(value.get("audit_sha256") or "")
    expected_sha = backend_contract.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "audit_sha256"}
    )
    try:
        return bool(
            value.get("audit_version")
            == physical_backend.TEMPORARY_TRANSACTION_LOG_AUDIT_VERSION_V2
            and backend_contract.backend_snapshot_valid_v2(snapshot)
            and value.get("backend_instance_sha256")
            == snapshot.get("backend_instance_sha256")
            and value.get("backend_snapshot_sha256")
            == snapshot.get("snapshot_sha256")
            and value.get("lock_namespace_sha256")
            == snapshot.get("lock_namespace_sha256")
            and type(value.get("wal_record_count")) is int
            and value.get("wal_record_count") >= 0
            and type(value.get("transaction_count")) is int
            and value.get("transaction_count") >= 0
            and isinstance(state_counts, Mapping)
            and set(state_counts) == set(_WAL_STATES)
            and all(type(state_counts[state]) is int for state in _WAL_STATES)
            and all(state_counts[state] >= 0 for state in _WAL_STATES)
            and sum(state_counts.values()) == value.get("wal_record_count")
            and isinstance(latest_counts, Mapping)
            and set(latest_counts) == set(_WAL_STATES)
            and all(type(latest_counts[state]) is int for state in _WAL_STATES)
            and all(latest_counts[state] >= 0 for state in _WAL_STATES)
            and sum(latest_counts.values()) == value.get("transaction_count")
            and value.get("unresolved_prepared_count")
            == latest_counts["PREPARED"]
            and value.get("unresolved_resolved_count") == 0
            and value.get("resolved_state_supported") is False
            and value.get("wal_integrity_verified") is True
            and value.get("synthetic_only") is True
            and value.get("temporary_storage_only") is True
            and value.get("durable") is False
            and value.get("production_evidence") is False
            and value.get("filesystem_accessed") is True
            and _valid_sha256(supplied_sha)
            and hmac.compare_digest(supplied_sha, expected_sha)
        )
    except Exception:
        return False


def _build_recovery_request_v1(
    record: Mapping[str, Any],
    batch: Mapping[str, Any],
    permit: Mapping[str, Any],
) -> dict[str, Any]:
    index = batch["next_index"]
    request = {
        "request_version": backend_contract.RECOVERY_REQUEST_VERSION_V2,
        "batch_epoch": batch["batch_epoch"],
        "batch_plan_sha256": batch["batch_plan_sha256"],
        "catalog_sha256": batch["catalog_sha256"],
        "prepared_record_sha256": record["record_sha256"],
        "wal_prepared_record_sha256": record["wal_prepared_record_sha256"],
        "original_request_sha256": record["request_sha256"],
        "original_invocation_command_sha256": record[
            "original_invocation_command_sha256"
        ],
        "original_authorization_receipt_sha256": record[
            "authorization_receipt_sha256"
        ],
        "recovery_authorization_receipt_sha256": (
            backend_contract.stable_sha256_v2(
                {
                    "adapter_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION,
                    "transaction_sha256": record["transaction_sha256"],
                    "checkpoint_index": index,
                    "maintenance_epoch": permit["maintenance_epoch"],
                }
            )
        ),
        "transaction_sha256": record["transaction_sha256"],
        "backend_instance_sha256": record["backend_instance_sha256"],
        "backend_snapshot_sha256": batch["backend_snapshot_sha256"],
        "registry_path_binding_sha256": record[
            "registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": record["lock_namespace_sha256"],
        "source_raw_document_sha256": record[
            "source_raw_document_sha256"
        ],
        "candidate_raw_document_sha256": record[
            "candidate_raw_document_sha256"
        ],
        "previous_maintenance_epoch": record["previous_maintenance_epoch"],
        "fresh_maintenance_epoch": permit["maintenance_epoch"],
        "deadline_epoch": batch["deadline_epoch"],
        "checkpoint_index": index,
        "synthetic_only": True,
        "production_authority": False,
    }
    request["request_sha256"] = backend_contract.stable_sha256_v2(request)
    return request


class OfflineRuntimeStartupRecoveryAdapterV1:
    """Execute one bounded synthetic recovery and emit a seam attestation."""

    def __init__(
        self,
        *,
        backend: Any = None,
        startup_recovery: Any = None,
        terminal_evidence_port: Any = None,
        config: OfflineRuntimeStartupRecoveryAdapterConfigV1 | None = None,
    ) -> None:
        self._backend = backend
        self._startup_recovery = startup_recovery
        self._terminal_evidence_port = terminal_evidence_port
        self._config = config or OfflineRuntimeStartupRecoveryAdapterConfigV1()

    def __repr__(self) -> str:
        return "OfflineRuntimeStartupRecoveryAdapterV1(<protected>)"

    @staticmethod
    def _failed(
        reason: str,
        *,
        backend_called: bool = False,
        write_executed: bool = False,
        registry_write: bool = False,
        write_state_unknown: bool = False,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_RUNTIME_STARTUP_RECOVERY_ADAPTER_FAILED_CLOSED",
            "reason": str(reason),
            "adapter_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "backend_called": backend_called,
            "real_registry_accessed": False,
            "write_executed": write_executed,
            "registry_write": registry_write,
            "write_state_unknown": write_state_unknown,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }

    def _ready(self) -> str | None:
        if self._config.enabled is not True:
            return "STARTUP_RECOVERY_ADAPTER_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            return "STARTUP_RECOVERY_ADAPTER_SCOPE_INVALID"
        required = (
            (self._backend, (
                "snapshot_offline",
                "list_prepared_transactions_offline",
                "inspect_transaction_log_offline",
                "reconcile_attested_transaction_offline",
            )),
            (self._startup_recovery, (
                "plan_offline",
                "record_terminal_receipt_offline",
                "finalize_offline",
            )),
            (self._terminal_evidence_port, ("normalize_recovery_offline",)),
        )
        if any(
            dependency is None
            or any(not callable(getattr(dependency, name, None)) for name in names)
            for dependency, names in required
        ):
            return "STARTUP_RECOVERY_ADAPTER_DEPENDENCY_INVALID"
        return None

    def __call__(self, maintenance_permit: Mapping[str, Any]) -> dict[str, Any]:
        reason = self._ready()
        if reason:
            return self._failed(reason)
        if not _maintenance_permit_valid_v1(maintenance_permit):
            return self._failed("STARTUP_RECOVERY_ADAPTER_MAINTENANCE_PERMIT_INVALID")

        backend_called = False
        any_write = False
        any_registry_write = False
        mutation_outcome_unknown = False

        def fail(reason: str) -> dict[str, Any]:
            return self._failed(
                reason,
                backend_called=backend_called,
                write_executed=any_write,
                registry_write=any_registry_write,
                write_state_unknown=mutation_outcome_unknown,
            )

        try:
            backend_called = True
            initial_snapshot = self._backend.snapshot_offline()
            initial_catalog = self._backend.list_prepared_transactions_offline()
            initial_audit = self._backend.inspect_transaction_log_offline()
            initial_valid = bool(
                backend_contract.backend_snapshot_valid_v2(initial_snapshot)
                and backend_contract.prepared_catalog_valid_v2(
                    initial_catalog, initial_snapshot
                )
                and temporary_transaction_log_audit_valid_v1(
                    initial_audit, initial_snapshot
                )
                and initial_snapshot.get("synthetic_only") is True
                and initial_snapshot.get("durable") is False
                and initial_snapshot.get("production_evidence") is False
                and initial_snapshot.get("filesystem_accessed") is True
                and initial_snapshot.get("lock_namespace_sha256")
                == maintenance_permit.get("lock_namespace_sha256")
                and initial_catalog.get("prepared_count")
                == initial_audit.get("unresolved_prepared_count")
                and initial_audit.get("unresolved_resolved_count") == 0
            )
            if not initial_valid:
                return fail("STARTUP_RECOVERY_ADAPTER_INITIAL_EVIDENCE_INVALID")

            planned = self._startup_recovery.plan_offline(
                initial_snapshot, initial_catalog
            )
            state = planned.get("protected_state")
            if not (
                planned.get("ok") is True
                and startup_contract.protected_startup_recovery_state_valid_v2(
                    state
                )
                and state.state["backend_snapshot"]["snapshot_sha256"]
                == initial_snapshot["snapshot_sha256"]
            ):
                return fail("STARTUP_RECOVERY_ADAPTER_PLAN_INVALID")

            processed = 0
            while not state.complete:
                if processed >= initial_catalog["prepared_count"]:
                    return fail(
                        "STARTUP_RECOVERY_ADAPTER_PROGRESS_BUDGET_EXCEEDED"
                    )
                batch = state.state["recovery_batch"]
                expected_hash = batch["item_record_sha256s"][
                    batch["next_index"]
                ]
                record = next(
                    (
                        item
                        for item in state.state["prepared_catalog"]["records"]
                        if item["record_sha256"] == expected_hash
                    ),
                    None,
                )
                if record is None:
                    return fail("STARTUP_RECOVERY_ADAPTER_RECORD_NOT_FOUND")
                request = _build_recovery_request_v1(
                    record, batch, maintenance_permit
                )
                if not backend_contract.recovery_request_valid_v2(
                    request, record, batch
                ):
                    return fail("STARTUP_RECOVERY_ADAPTER_REQUEST_INVALID")
                mutation_outcome_unknown = True
                result = self._backend.reconcile_attested_transaction_offline(
                    request
                )
                if isinstance(result, Mapping):
                    if type(result.get("write_executed")) is bool:
                        any_write = (
                            any_write or result["write_executed"] is True
                        )
                    if type(result.get("registry_write")) is bool:
                        any_registry_write = (
                            any_registry_write
                            or result["registry_write"] is True
                        )
                if not backend_contract.recovery_result_valid_v2(
                    result, request, batch["next_index"]
                ):
                    return fail("STARTUP_RECOVERY_ADAPTER_RESULT_INVALID")
                mutation_outcome_unknown = False
                terminal = self._terminal_evidence_port.normalize_recovery_offline(
                    snapshot=state.state["backend_snapshot"],
                    catalog_record=record,
                    batch=batch,
                    request=request,
                    result=result,
                )
                receipt = terminal.get("protected_receipt")
                if not (
                    terminal.get("ok") is True
                    and terminal_contract.protected_physical_terminal_evidence_valid_v2(
                        receipt
                    )
                ):
                    return fail(
                        "STARTUP_RECOVERY_ADAPTER_TERMINAL_EVIDENCE_INVALID"
                    )
                recorded = self._startup_recovery.record_terminal_receipt_offline(
                    state, receipt
                )
                next_state = recorded.get("protected_state")
                if not (
                    recorded.get("ok") is True
                    and startup_contract.protected_startup_recovery_state_valid_v2(
                        next_state
                    )
                    and next_state.next_index == state.next_index + 1
                ):
                    return fail("STARTUP_RECOVERY_ADAPTER_CHECKPOINT_INVALID")
                state = next_state
                processed += 1

            final_snapshot = self._backend.snapshot_offline()
            final_catalog = self._backend.list_prepared_transactions_offline()
            final_audit = self._backend.inspect_transaction_log_offline()
            finalized = self._startup_recovery.finalize_offline(
                state, final_snapshot, final_catalog
            )
            completion = finalized.get("protected_completion")
            final_valid = bool(
                backend_contract.backend_snapshot_valid_v2(final_snapshot)
                and backend_contract.prepared_catalog_valid_v2(
                    final_catalog, final_snapshot
                )
                and temporary_transaction_log_audit_valid_v1(
                    final_audit, final_snapshot
                )
                and final_snapshot.get("backend_instance_sha256")
                == initial_snapshot.get("backend_instance_sha256")
                and final_snapshot.get("lock_namespace_sha256")
                == maintenance_permit.get("lock_namespace_sha256")
                and final_catalog.get("prepared_count") == 0
                and final_audit.get("unresolved_prepared_count") == 0
                and final_audit.get("unresolved_resolved_count") == 0
                and finalized.get("ok") is True
                and finalized.get("prepared_catalog_drained") is True
                and startup_contract.protected_startup_recovery_completion_valid_v2(
                    completion
                )
                and completion.recovered_count
                == initial_catalog.get("prepared_count")
            )
            if not final_valid:
                return fail("STARTUP_RECOVERY_ADAPTER_FINAL_EVIDENCE_INVALID")

            attestation = {
                "ok": True,
                "status": "C3_RUNTIME_STARTUP_RECOVERY_ADAPTER_COMPLETED_OFFLINE",
                "adapter_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION,
                "wal_inspected": True,
                "transaction_log_inspected": True,
                "prepared_transactions_inspected": True,
                "resolved_transactions_inspected": True,
                "prepared_transactions_before": initial_catalog[
                    "prepared_count"
                ],
                "resolved_transactions_before": initial_audit[
                    "unresolved_resolved_count"
                ],
                "prepared_transactions_after": final_catalog[
                    "prepared_count"
                ],
                "resolved_transactions_after": final_audit[
                    "unresolved_resolved_count"
                ],
                "unresolved_transactions_after": (
                    final_catalog["prepared_count"]
                    + final_audit["unresolved_resolved_count"]
                ),
                "terminal_transactions_before": sum(
                    initial_audit["latest_state_counts"][state_name]
                    for state_name in ("COMMITTED", "ABORTED", "ROLLED_BACK")
                ),
                "terminal_transactions_after": sum(
                    final_audit["latest_state_counts"][state_name]
                    for state_name in ("COMMITTED", "ABORTED", "ROLLED_BACK")
                ),
                "recovery_completed": True,
                "reconciliation_completed": True,
                "maintenance_epoch": maintenance_permit[
                    "maintenance_epoch"
                ],
                "lock_namespace_sha256": maintenance_permit[
                    "lock_namespace_sha256"
                ],
                "backend_instance_sha256": initial_snapshot[
                    "backend_instance_sha256"
                ],
                "initial_transaction_log_audit_sha256": initial_audit[
                    "audit_sha256"
                ],
                "final_transaction_log_audit_sha256": final_audit[
                    "audit_sha256"
                ],
                "startup_recovery_completion_sha256": completion.completion_sha256,
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "backend_called": True,
                "real_registry_accessed": False,
                "write_executed": any_write,
                "registry_write": any_registry_write,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
            }
            attestation["startup_recovery_attestation_sha256"] = (
                runtime_seam.startup_recovery_attestation_sha256_v1(
                    attestation
                )
            )
            return attestation
        except Exception as exc:
            reason = str(getattr(exc, "reason", type(exc).__name__))
            if not re.fullmatch(r"[A-Z0-9_]{1,160}", reason):
                reason = type(exc).__name__
            return fail(reason)


__all__ = [
    "OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1",
    "OfflineRuntimeStartupRecoveryAdapterConfigV1",
    "OfflineRuntimeStartupRecoveryAdapterV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION",
    "temporary_transaction_log_audit_valid_v1",
]
