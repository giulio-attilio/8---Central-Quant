"""Temporary-filesystem harness for the C3 durable backend V2 reference."""

from __future__ import annotations

import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as conformance_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_REFERENCE_HARNESS_V2_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PHYSICAL-REFERENCE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_710_000


def _sha(label: str) -> str:
    return contract.stable_sha256_v2({"physical_harness": label})


def run_temporary_physical_reference_harness_v2() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        backend = physical.TemporaryPhysicalDurableRawTransactionBackendV2(
            root,
            enabled=True,
            scope_attestation=physical.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "source", "generation": 0}
        )
        lock_verified = backend.mark_lock_probe_offline()

        first_request = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "committed", "generation": 1},
            label="committed",
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        first_result = backend.apply_attested_transaction_offline(first_request)
        first_valid = contract.transaction_result_valid_v2(first_result, first_request)
        idempotency_verified = backend.prove_idempotency_offline(first_request)
        cas_verified = backend.prove_compare_and_swap_offline(first_request)

        rollback_request = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "must-rollback", "generation": 2},
            label="rollback",
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        rollback_result = backend.apply_with_fault_offline(
            rollback_request, "AFTER_REPLACE"
        )
        rollback_valid = bool(
            contract.transaction_result_valid_v2(rollback_result, rollback_request)
            and rollback_result["terminal_state"] == "ROLLED_BACK"
        )

        recovery_request_source = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "interrupted", "generation": 3},
            label="interrupted",
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        backend.prepare_interrupted_transaction_offline(recovery_request_source)
        recovery_snapshot = backend.snapshot_offline()
        prepared_catalog = backend.list_prepared_transactions_offline()
        batch = contract.build_resumable_recovery_batch_offline_v2(
            recovery_snapshot,
            prepared_catalog,
            batch_epoch=_sha("physical-recovery-batch"),
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        prepared_record = prepared_catalog["records"][0]
        recovery_request = conformance_harness.build_synthetic_recovery_request_v2(
            prepared_record, batch, checkpoint_index=0
        )
        recovery_result = backend.reconcile_attested_transaction_offline(
            recovery_request
        )
        recovery_valid = bool(
            contract.recovery_request_valid_v2(
                recovery_request, prepared_record, batch
            )
            and contract.recovery_result_valid_v2(
                recovery_result, recovery_request, 0
            )
        )
        completed_batch = contract.advance_recovery_batch_offline_v2(
            batch, recovery_result
        )
        final_catalog = backend.list_prepared_transactions_offline()
        backend.finalize_probe_observations_offline(lock_verified=lock_verified)

        auditor = contract.DurableRawTransactionBackendConformanceV2(
            contract.DurableRawTransactionBackendConformanceConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2,
            )
        )
        audit = auditor.audit_offline(backend)
        final_snapshot = backend.snapshot_offline()
        evidence = backend.capability_evidence_offline()

        ok = bool(
            first_valid
            and first_result["terminal_state"] == "COMMITTED"
            and idempotency_verified
            and cas_verified
            and rollback_valid
            and recovery_valid
            and recovery_result["terminal_state"] == "ABORTED"
            and completed_batch["complete"] is True
            and final_catalog["prepared_count"] == 0
            and len(evidence) == len(contract.REQUIRED_CAPABILITIES_V2)
            and all(item["observed"] is True for item in evidence)
            and audit.get("ok") is True
            and audit.get("filesystem_accessed") is True
        )
        return {
            "ok": ok,
            "status": (
                "DURABLE_BACKEND_V2_TEMPORARY_PHYSICAL_REFERENCE_PASSED"
                if ok else "DURABLE_BACKEND_V2_TEMPORARY_PHYSICAL_REFERENCE_FAILED_CLOSED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_REFERENCE_HARNESS_V2_VERSION,
            "backend_snapshot_sha256": final_snapshot["snapshot_sha256"],
            "backend_snapshot": final_snapshot,
            "capability_evidence": evidence,
            "prepared_catalog": final_catalog,
            "capability_evidence_count": len(evidence),
            "lock_verified": lock_verified,
            "wal_cas_replace_fsync_backup_verified": all(
                capability in {item["capability"] for item in evidence if item["observed"]}
                for capability in (
                    "append_only_hash_chained_wal",
                    "atomic_same_directory_replace",
                    "compare_and_swap_hash_and_generation",
                    "exact_raw_loader",
                    "file_and_directory_fsync",
                    "immutable_content_addressed_backup",
                )
            ),
            "idempotency_verified": idempotency_verified,
            "rollback_verified": rollback_valid,
            "interrupted_recovery_verified": recovery_valid,
            "prepared_catalog_drained": final_catalog["prepared_count"] == 0,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


__all__ = ["run_temporary_physical_reference_harness_v2"]
