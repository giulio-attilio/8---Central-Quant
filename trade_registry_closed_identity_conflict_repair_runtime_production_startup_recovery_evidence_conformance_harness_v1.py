"""In-memory fixture harness for production recovery evidence conformance."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as schema_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-RECOVERY-EVIDENCE-CONFORMANCE-HARNESS-V1"
)
SYNTHETIC_NOW_V1 = 1_788_900_000


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _seal(value: dict[str, Any], hash_field: str) -> dict[str, Any]:
    value[hash_field] = contract.synthetic_evidence_artifact_sha256_v1(
        value, hash_field
    )
    return value


def _snapshot(schema: dict[str, Any], *, generation: int, label: str) -> dict[str, Any]:
    return _seal(
        {
            "snapshot_version": f"SYNTHETIC_PRODUCTION_RECOVERY_SNAPSHOT_{label}_V1",
            "schema_sha256": schema["schema_sha256"],
            "provider_binding_sha256": schema["provider_binding_sha256"],
            "backend_instance_sha256": schema["source_backend_instance_sha256"],
            "backend_module_source_sha256": _sha("synthetic-backend-module"),
            "registry_path_binding_sha256": schema[
                "source_registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": _sha("synthetic-wal-storage"),
            "resolved_ledger_storage_binding_sha256": _sha(
                "synthetic-resolved-ledger-storage"
            ),
            "lock_namespace_sha256": schema["source_lock_namespace_sha256"],
            "backend_capability_attestation_sha256": schema[
                "source_backend_capability_declaration_sha256"
            ],
            "backend_capability_probe_receipt_sha256": _sha(
                "synthetic-non-production-capability-probe"
            ),
            "generation": generation,
            "observed_at_epoch": SYNTHETIC_NOW_V1 + generation,
            "durable": False,
            "production_evidence": False,
            "authenticated_authority_receipt_sha256": _sha(
                "synthetic-unauthenticated-authority-placeholder"
            ),
        },
        "snapshot_sha256",
    )


def _prepared_record(index: int) -> dict[str, Any]:
    return _seal(
        {
            "record_version": "SYNTHETIC_PREPARED_RECORD_FIXTURE_V1",
            "transaction_sha256": _sha(f"prepared-transaction-{index}"),
            "request_sha256": _sha(f"prepared-request-{index}"),
            "prepared_record_sha256": _sha(f"prepared-wal-record-{index}"),
            "source_raw_document_sha256": _sha(f"prepared-source-{index}"),
            "candidate_raw_document_sha256": _sha(
                f"prepared-candidate-{index}"
            ),
            "previous_maintenance_epoch": _sha(
                f"previous-maintenance-epoch-{index}"
            ),
            "prepared_at_epoch": SYNTHETIC_NOW_V1 - 30 + index,
            "deadline_epoch": SYNTHETIC_NOW_V1 + 120,
            "state": "PREPARED",
        },
        "record_sha256",
    )


def _resolved_record(index: int) -> dict[str, Any]:
    return _seal(
        {
            "record_version": "SYNTHETIC_RESOLVED_RECORD_FIXTURE_V1",
            "obligation_sha256": _sha(f"resolved-obligation-{index}"),
            "transaction_sha256": _sha(f"resolved-transaction-{index}"),
            "resolution_receipt_sha256": _sha(f"resolution-receipt-{index}"),
            "terminal_result_sha256": _sha(f"terminal-result-{index}"),
            "resolved_at_epoch": SYNTHETIC_NOW_V1 - 15 + index,
            "projection_committed": False,
            "state": "RESOLVED",
        },
        "record_sha256",
    )


def _terminal_receipt(
    schema: dict[str, Any],
    *,
    transaction_sha256: str,
    source_state: str,
    terminal_state: str,
    maintenance_epoch: str,
    previous_maintenance_epoch: str,
    index: int,
) -> dict[str, Any]:
    return _seal(
        {
            "receipt_version": "SYNTHETIC_TERMINAL_RECEIPT_FIXTURE_V1",
            "schema_sha256": schema["schema_sha256"],
            "provider_binding_sha256": schema["provider_binding_sha256"],
            "backend_instance_sha256": schema[
                "source_backend_instance_sha256"
            ],
            "transaction_sha256": transaction_sha256,
            "source_state": source_state,
            "terminal_state": terminal_state,
            "maintenance_epoch": maintenance_epoch,
            "previous_maintenance_epoch": previous_maintenance_epoch,
            "backend_result_sha256": _sha(f"synthetic-backend-result-{index}"),
            "write_state_known": True,
            "write_executed": True,
            "registry_write": index == 0,
            "completed_at_epoch": SYNTHETIC_NOW_V1 + 5 + index,
            "durable": False,
            "production_evidence": False,
            "authenticated_authority_receipt_sha256": _sha(
                "synthetic-unauthenticated-authority-placeholder"
            ),
        },
        "receipt_sha256",
    )


def _catalog(
    schema: dict[str, Any],
    snapshot: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    resolved: bool,
) -> dict[str, Any]:
    ordered = sorted(records, key=lambda item: item["record_sha256"])
    common = {
        "catalog_version": (
            "SYNTHETIC_RESOLVED_CATALOG_FIXTURE_V1"
            if resolved
            else "SYNTHETIC_PREPARED_CATALOG_FIXTURE_V1"
        ),
        "schema_sha256": schema["schema_sha256"],
        "backend_instance_sha256": snapshot["backend_instance_sha256"],
        "backend_snapshot_sha256": snapshot["snapshot_sha256"],
        "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
        "generation": snapshot["generation"],
        "records": ordered,
        "record_count": len(ordered),
        "complete_scan_verified": True,
        "durable": False,
        "production_evidence": False,
        "authenticated_authority_receipt_sha256": snapshot[
            "authenticated_authority_receipt_sha256"
        ],
    }
    if resolved:
        common["resolved_ledger_storage_binding_sha256"] = snapshot[
            "resolved_ledger_storage_binding_sha256"
        ]
        common["resolved_count"] = len(ordered)
    else:
        common["registry_path_binding_sha256"] = snapshot[
            "registry_path_binding_sha256"
        ]
        common["wal_storage_binding_sha256"] = snapshot[
            "wal_storage_binding_sha256"
        ]
        common["prepared_count"] = len(ordered)
    return _seal(common, "catalog_sha256")


def _audit(
    schema: dict[str, Any],
    snapshot: dict[str, Any],
    state_counts: dict[str, int],
    latest_counts: dict[str, int],
    *,
    label: str,
) -> dict[str, Any]:
    return _seal(
        {
            "audit_version": f"SYNTHETIC_TRANSACTION_LOG_AUDIT_{label}_V1",
            "schema_sha256": schema["schema_sha256"],
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "wal_storage_binding_sha256": snapshot[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": snapshot[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "wal_record_count": sum(state_counts.values()),
            "transaction_count": sum(latest_counts.values()),
            "state_counts": dict(state_counts),
            "latest_state_counts": dict(latest_counts),
            "unresolved_prepared_count": latest_counts["PREPARED"],
            "unresolved_resolved_count": latest_counts["RESOLVED"],
            "hash_chain_head_sha256": _sha(f"synthetic-wal-head-{label}"),
            "wal_integrity_verified": True,
            "catalog_crosscheck_verified": True,
            "fsync_capability_verified": False,
            "durable": False,
            "production_evidence": False,
            "authenticated_authority_receipt_sha256": snapshot[
                "authenticated_authority_receipt_sha256"
            ],
        },
        "audit_sha256",
    )


def build_synthetic_production_startup_recovery_evidence_conformance_context_v1() -> dict[
    str, Any
]:
    values = schema_harness.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
    schema_result = values["schema_contract"].define_offline(
        protected_provider_binding=values["protected_identity_binding"]
    )
    protected_schema = schema_result.get("protected_schema")
    schema = dict(protected_schema.schema)
    initial_snapshot = _snapshot(schema, generation=7, label="INITIAL")
    final_snapshot = _snapshot(schema, generation=9, label="FINAL")
    prepared_records = [_prepared_record(index) for index in range(2)]
    resolved_records = [_resolved_record(0)]
    initial_prepared = _catalog(
        schema, initial_snapshot, prepared_records, resolved=False
    )
    initial_resolved = _catalog(
        schema, initial_snapshot, resolved_records, resolved=True
    )
    final_prepared = _catalog(schema, final_snapshot, [], resolved=False)
    final_resolved = _catalog(schema, final_snapshot, [], resolved=True)
    initial_counts = {
        "PREPARED": 2,
        "RESOLVED": 1,
        "COMMITTED": 0,
        "ABORTED": 0,
        "ROLLED_BACK": 0,
    }
    final_state_counts = {
        "PREPARED": 2,
        "RESOLVED": 1,
        "COMMITTED": 2,
        "ABORTED": 1,
        "ROLLED_BACK": 0,
    }
    final_latest_counts = {
        "PREPARED": 0,
        "RESOLVED": 0,
        "COMMITTED": 2,
        "ABORTED": 1,
        "ROLLED_BACK": 0,
    }
    initial_audit = _audit(
        schema,
        initial_snapshot,
        initial_counts,
        initial_counts,
        label="INITIAL",
    )
    final_audit = _audit(
        schema,
        final_snapshot,
        final_state_counts,
        final_latest_counts,
        label="FINAL",
    )
    maintenance_epoch = _sha("synthetic-fresh-maintenance-epoch")
    terminal_receipts = [
        _terminal_receipt(
            schema,
            transaction_sha256=prepared_records[0]["transaction_sha256"],
            source_state="PREPARED",
            terminal_state="COMMITTED",
            maintenance_epoch=maintenance_epoch,
            previous_maintenance_epoch=prepared_records[0][
                "previous_maintenance_epoch"
            ],
            index=0,
        ),
        _terminal_receipt(
            schema,
            transaction_sha256=prepared_records[1]["transaction_sha256"],
            source_state="PREPARED",
            terminal_state="ABORTED",
            maintenance_epoch=maintenance_epoch,
            previous_maintenance_epoch=prepared_records[1][
                "previous_maintenance_epoch"
            ],
            index=1,
        ),
        _terminal_receipt(
            schema,
            transaction_sha256=resolved_records[0]["transaction_sha256"],
            source_state="RESOLVED",
            terminal_state="COMMITTED",
            maintenance_epoch=maintenance_epoch,
            previous_maintenance_epoch=_sha(
                "resolved-previous-maintenance-epoch-0"
            ),
            index=2,
        ),
    ]
    terminal_receipts.sort(key=lambda item: item["receipt_sha256"])
    completion = _seal(
        {
            "evidence_version": schema["future_evidence_version"],
            "schema_sha256": schema["schema_sha256"],
            "provider_binding_sha256": schema["provider_binding_sha256"],
            "backend_instance_sha256": schema[
                "source_backend_instance_sha256"
            ],
            "registry_path_binding_sha256": schema[
                "source_registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": initial_snapshot[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": initial_snapshot[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": schema["source_lock_namespace_sha256"],
            "maintenance_epoch": maintenance_epoch,
            "maintenance_lease_receipt_sha256": _sha(
                "synthetic-maintenance-lease-receipt"
            ),
            "initial_backend_snapshot_sha256": initial_snapshot[
                "snapshot_sha256"
            ],
            "initial_transaction_log_audit_sha256": initial_audit[
                "audit_sha256"
            ],
            "initial_prepared_catalog_sha256": initial_prepared[
                "catalog_sha256"
            ],
            "initial_resolved_catalog_sha256": initial_resolved[
                "catalog_sha256"
            ],
            "final_backend_snapshot_sha256": final_snapshot[
                "snapshot_sha256"
            ],
            "final_transaction_log_audit_sha256": final_audit[
                "audit_sha256"
            ],
            "final_prepared_catalog_sha256": final_prepared[
                "catalog_sha256"
            ],
            "final_resolved_catalog_sha256": final_resolved[
                "catalog_sha256"
            ],
            "terminal_receipt_set_sha256": (
                contract.synthetic_terminal_receipt_set_sha256_v1(
                    terminal_receipts
                )
            ),
            "prepared_transactions_before": 2,
            "resolved_transactions_before": 1,
            "prepared_transactions_after": 0,
            "resolved_transactions_after": 0,
            "unresolved_transactions_after": 0,
            "writers_blocked_entire_window": True,
            "same_maintenance_epoch_used": True,
            "fresh_maintenance_epoch_verified": True,
            "all_catalogs_drained": True,
            "wal_integrity_verified": True,
            "durability_verified": False,
            "authenticated_authority_verified": False,
            "write_state_known": True,
            "write_executed": True,
            "registry_write": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "production_evidence": False,
            "runtime_admissible": False,
        },
        "startup_recovery_attestation_sha256",
    )
    bundle = {
        "bundle_version": contract.SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1,
        "schema_sha256": schema["schema_sha256"],
        "initial_backend_snapshot": initial_snapshot,
        "initial_transaction_log_audit": initial_audit,
        "initial_prepared_catalog": initial_prepared,
        "initial_resolved_catalog": initial_resolved,
        "final_backend_snapshot": final_snapshot,
        "final_transaction_log_audit": final_audit,
        "final_prepared_catalog": final_prepared,
        "final_resolved_catalog": final_resolved,
        "terminal_receipts": terminal_receipts,
        "completion_attestation": completion,
        "synthetic_fixture_only": True,
        "durable": False,
        "production_evidence": False,
        "production_authority": False,
        "runtime_admissible": False,
    }
    bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
        bundle
    )
    validator = contract.OfflineProductionStartupRecoveryEvidenceConformanceV1(
        config=contract.OfflineProductionStartupRecoveryEvidenceConformanceConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
            ),
            expected_schema_sha256=protected_schema.schema_sha256,
        )
    )
    return {
        **values,
        "schema_result": schema_result,
        "protected_schema": protected_schema,
        "fixture_bundle": bundle,
        "validator": validator,
    }


def run_synthetic_production_startup_recovery_evidence_conformance_harness_v1() -> dict[
    str, Any
]:
    values = build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
    result = values["validator"].audit_offline(
        protected_schema=values["protected_schema"],
        fixture_bundle=values["fixture_bundle"],
    )
    counters = values["store_double"].counters()
    safe = bool(
        result.get("ok") is True
        and result.get("schema_verified") is True
        and result.get("bundle_hash_verified") is True
        and result.get("initial_evidence_verified") is True
        and result.get("final_evidence_verified") is True
        and result.get("cross_binding_verified") is True
        and result.get("safety_vector_verified") is True
        and result.get("schema_conforms") is True
        and result.get("production_admissible") is False
        and result.get("production_authority") is False
        and result.get("production_ready") is False
        and result.get("runtime_integrated") is False
        and result.get("recovery_execution_allowed") is False
        and result.get("live_allowed") is False
        and counters == {"apply_call_count": 0, "recovery_call_count": 0}
        and result.get("provider_called") is False
        and result.get("store_called") is False
        and result.get("backend_called") is False
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_HARNESS_V1_VERSION,
        "schema_conforms": result.get("schema_conforms") is True,
        "prepared_before": values["fixture_bundle"][
            "completion_attestation"
        ]["prepared_transactions_before"],
        "resolved_before": values["fixture_bundle"][
            "completion_attestation"
        ]["resolved_transactions_before"],
        "unresolved_after": values["fixture_bundle"][
            "completion_attestation"
        ]["unresolved_transactions_after"],
        "production_admissible": False,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_provider_instantiated": False,
        "production_provider_called": False,
        "production_store_called": False,
        "production_backend_called": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_HARNESS_V1_VERSION",
    "build_synthetic_production_startup_recovery_evidence_conformance_context_v1",
    "run_synthetic_production_startup_recovery_evidence_conformance_harness_v1",
]
