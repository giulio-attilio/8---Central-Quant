"""Synthetic harness for the dormant scope-aware conformance adapter."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1 as scope_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_harness_v1 as evidence_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_contract_v1 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-SCOPE-AWARE-EVIDENCE-CONFORMANCE-ADAPTER-HARNESS-V1"
)


def _bound_snapshot(
    schema: dict[str, Any],
    scope: dict[str, Any],
    *,
    generation: int,
    label: str,
) -> dict[str, Any]:
    snapshot = evidence_harness_v1._snapshot(
        schema, generation=generation, label=label
    )
    snapshot.update(
        wal_storage_binding_sha256=scope["wal_storage_binding_sha256"],
        resolved_ledger_storage_binding_sha256=scope[
            "resolved_ledger_storage_binding_sha256"
        ],
        authenticated_authority_receipt_sha256=scope[
            "candidate_authenticated_authority_receipt_sha256"
        ],
    )
    return evidence_harness_v1._seal(snapshot, "snapshot_sha256")


def build_scope_compatible_synthetic_evidence_bundle_v1(
    protected_scope_binding: Any,
) -> dict[str, Any]:
    scope = dict(protected_scope_binding.binding)
    schema = dict(protected_scope_binding.protected_evidence_schema.schema)
    initial_snapshot = _bound_snapshot(
        schema, scope, generation=31, label="SCOPE_INITIAL"
    )
    final_snapshot = _bound_snapshot(
        schema, scope, generation=33, label="SCOPE_FINAL"
    )
    prepared_records: list[dict[str, Any]] = []
    resolved_records: list[dict[str, Any]] = []
    for index, item in enumerate(scope["pending_items"]):
        if item["source_state"] == "PREPARED":
            record = evidence_harness_v1._prepared_record(index)
            record["transaction_sha256"] = item["transaction_sha256"]
            record = evidence_harness_v1._seal(record, "record_sha256")
            prepared_records.append(record)
        else:
            record = evidence_harness_v1._resolved_record(index)
            record["transaction_sha256"] = item["transaction_sha256"]
            record["obligation_sha256"] = item["obligation_sha256"]
            record = evidence_harness_v1._seal(record, "record_sha256")
            resolved_records.append(record)
    initial_prepared = evidence_harness_v1._catalog(
        schema, initial_snapshot, prepared_records, resolved=False
    )
    initial_resolved = evidence_harness_v1._catalog(
        schema, initial_snapshot, resolved_records, resolved=True
    )
    final_prepared = evidence_harness_v1._catalog(
        schema, final_snapshot, [], resolved=False
    )
    final_resolved = evidence_harness_v1._catalog(
        schema, final_snapshot, [], resolved=True
    )
    initial_counts = {
        "PREPARED": len(prepared_records),
        "RESOLVED": len(resolved_records),
        "COMMITTED": 0,
        "ABORTED": 0,
        "ROLLED_BACK": 0,
    }
    final_state_counts = {
        "PREPARED": len(prepared_records),
        "RESOLVED": len(resolved_records),
        "COMMITTED": len(prepared_records) + len(resolved_records),
        "ABORTED": 0,
        "ROLLED_BACK": 0,
    }
    final_latest_counts = {
        "PREPARED": 0,
        "RESOLVED": 0,
        "COMMITTED": len(prepared_records) + len(resolved_records),
        "ABORTED": 0,
        "ROLLED_BACK": 0,
    }
    initial_audit = evidence_harness_v1._audit(
        schema,
        initial_snapshot,
        initial_counts,
        initial_counts,
        label="SCOPE_INITIAL",
    )
    final_audit = evidence_harness_v1._audit(
        schema,
        final_snapshot,
        final_state_counts,
        final_latest_counts,
        label="SCOPE_FINAL",
    )
    previous_epochs = {
        record["transaction_sha256"]: record["previous_maintenance_epoch"]
        for record in prepared_records
    }
    terminal_receipts = []
    for index, item in enumerate(scope["pending_items"]):
        previous_epoch = previous_epochs.get(
            item["transaction_sha256"],
            evidence_harness_v1._sha(f"scope-resolved-previous-epoch-{index}"),
        )
        terminal = evidence_harness_v1._terminal_receipt(
            schema,
            transaction_sha256=item["transaction_sha256"],
            source_state=item["source_state"],
            terminal_state="COMMITTED",
            maintenance_epoch=scope["maintenance_epoch"],
            previous_maintenance_epoch=previous_epoch,
            index=index,
        )
        terminal["authenticated_authority_receipt_sha256"] = scope[
            "candidate_authenticated_authority_receipt_sha256"
        ]
        terminal = evidence_harness_v1._seal(terminal, "receipt_sha256")
        terminal_receipts.append(terminal)
    terminal_receipts.sort(key=lambda item: item["receipt_sha256"])
    completion = evidence_harness_v1._seal(
        {
            "evidence_version": schema["future_evidence_version"],
            "schema_sha256": scope["schema_sha256"],
            "provider_binding_sha256": scope["provider_binding_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "registry_path_binding_sha256": scope[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": scope[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": scope[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": scope["lock_namespace_sha256"],
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "candidate_maintenance_lease_receipt_sha256"
            ],
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
            "final_transaction_log_audit_sha256": final_audit["audit_sha256"],
            "final_prepared_catalog_sha256": final_prepared["catalog_sha256"],
            "final_resolved_catalog_sha256": final_resolved["catalog_sha256"],
            "terminal_receipt_set_sha256": conformance_v1.synthetic_terminal_receipt_set_sha256_v1(
                terminal_receipts
            ),
            "prepared_transactions_before": len(prepared_records),
            "resolved_transactions_before": len(resolved_records),
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
            "registry_write": bool(terminal_receipts),
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
        "bundle_version": conformance_v1.SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1,
        "schema_sha256": scope["schema_sha256"],
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
    bundle["bundle_sha256"] = conformance_v1.synthetic_evidence_bundle_sha256_v1(
        bundle
    )
    return bundle


def make_synthetic_scope_aware_adapter_v1(
    *, scope_binding_sha256: str, bundle_sha256: str
) -> contract.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1:
    return contract.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1(
        config=contract.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1
            ),
            expected_scope_binding_sha256=scope_binding_sha256,
            expected_bundle_sha256=bundle_sha256,
        )
    )


def build_synthetic_scope_aware_evidence_conformance_context_v1() -> dict[
    str, Any
]:
    values = (
        scope_harness_v1.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
    )
    scope_result = values["scope_contract"].bind_offline(
        protected_batch_session=values["protected_batch_session"],
        protected_evidence_schema=values["protected_schema"],
    )
    protected_scope = scope_result.get("protected_scope_binding")
    if scope_result.get("ok") is not True or protected_scope is None:
        raise ValueError("synthetic protected scope unavailable")
    bundle = build_scope_compatible_synthetic_evidence_bundle_v1(protected_scope)
    validator = conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceV1(
        config=conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceConfigV1(
            enabled=True,
            scope_attestation=(
                conformance_v1.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
            ),
            expected_schema_sha256=protected_scope.protected_evidence_schema.schema_sha256,
        )
    )
    adapter = make_synthetic_scope_aware_adapter_v1(
        scope_binding_sha256=protected_scope.binding_sha256,
        bundle_sha256=bundle["bundle_sha256"],
    )
    return {
        **values,
        "scope_result": scope_result,
        "protected_scope_binding": protected_scope,
        "fixture_bundle": bundle,
        "conformance_validator": validator,
        "adapter": adapter,
    }


def run_synthetic_scope_aware_evidence_conformance_harness_v1() -> dict[str, Any]:
    values = build_synthetic_scope_aware_evidence_conformance_context_v1()
    result = values["adapter"].audit_offline(
        protected_scope_binding=values["protected_scope_binding"],
        fixture_bundle=values["fixture_bundle"],
        conformance_validator=values["conformance_validator"],
    )
    protected = result.get("protected_conformance")
    receipt = protected.receipt if protected is not None else {}
    restart_result = values["restart_result"]
    safe = bool(
        result.get("ok") is True
        and result.get("scope_cross_binding_verified") is True
        and result.get("delegate_called") is True
        and result.get("delegate_conformance_verified") is True
        and contract.protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
            protected
        )
        and receipt.get("exact_backend_storage_identity_verified") is True
        and receipt.get("exact_maintenance_identity_verified") is True
        and receipt.get("exact_authenticated_authority_verified") is True
        and receipt.get("exact_pending_catalog_transaction_set_verified") is True
        and receipt.get("exact_terminal_receipt_transaction_set_verified") is True
        and receipt.get("production_evidence_created") is False
        and receipt.get("production_authority_granted") is False
        and receipt.get("runtime_integrated") is False
        and receipt.get("live_allowed") is False
        and restart_result.get("temporary_storage_removed") is True
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_SCOPE_AWARE_EVIDENCE_CONFORMANCE_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_SCOPE_AWARE_EVIDENCE_CONFORMANCE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_HARNESS_V1_VERSION,
        "scope_cross_binding_verified": result.get("scope_cross_binding_verified")
        is True,
        "delegate_conformance_verified": result.get(
            "delegate_conformance_verified"
        )
        is True,
        "pending_item_count": receipt.get("pending_item_count", 0),
        "upstream_temporary_storage_removed": restart_result.get(
            "temporary_storage_removed"
        )
        is True,
        "production_evidence_created": False,
        "production_authority": False,
        "runtime_integrated": False,
        "recovery_execution_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_HARNESS_V1_VERSION",
    "build_scope_compatible_synthetic_evidence_bundle_v1",
    "build_synthetic_scope_aware_evidence_conformance_context_v1",
    "make_synthetic_scope_aware_adapter_v1",
    "run_synthetic_scope_aware_evidence_conformance_harness_v1",
]
