"""Synthetic temporary-filesystem harness for the physical source adapter V2."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as backend_harness_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as durable_authority_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_v2 as adapter_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as source_ports_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as locked_collection_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_lease_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_harness_v2 as resolved_port_harness_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SOURCE-PHYSICAL-CONFORMANCE-"
    "ADAPTER-OFFLINE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_710_000


def _sha(label: str) -> str:
    return backend_contract_v2.stable_sha256_v2(
        {"physical_conformance_adapter_harness": label}
    )


def make_adapter_v2(
    *,
    backend: Any,
    terminal_evidence_port: Any,
    resolved_catalog_port: Any,
    observation_lease: Any,
    locked_aggregate_collection: Any,
    authority_sha256: str,
    enabled: bool = True,
    clock=None,
) -> adapter_v2.OfflineEvidenceSourcePhysicalConformanceAdapterV2:
    return adapter_v2.OfflineEvidenceSourcePhysicalConformanceAdapterV2(
        clock=clock or (lambda: SYNTHETIC_NOW_V2),
        config=adapter_v2.OfflineEvidenceSourcePhysicalConformanceAdapterConfigV2(
            enabled=enabled,
            scope_attestation=(
                adapter_v2.OFFLINE_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_SCOPE_ATTESTATION_V2
            ),
            expected_backend_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                )
            ),
            expected_terminal_port_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    terminal_evidence_port
                )
            ),
            expected_resolved_catalog_port_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_catalog_port
                )
            ),
            expected_observation_lease_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    observation_lease
                )
            ),
            expected_locked_collection_object_identity_sha256=(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    locked_aggregate_collection
                )
            ),
            expected_observation_authority_sha256=authority_sha256,
        ),
    )


@contextmanager
def synthetic_physical_conformance_context_v2(
    *,
    exercise_capabilities: bool = True,
    terminal_enabled: bool = True,
) -> Iterator[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        backend = physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2(
            root,
            enabled=True,
            scope_attestation=(
                physical_v2.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
            ),
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "source", "generation": 0}
        )
        if exercise_capabilities:
            lock_verified = backend.mark_lock_probe_offline()
            committed_request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "committed", "generation": 1},
                label="committed",
                deadline_epoch=SYNTHETIC_NOW_V2 + 60,
            )
            backend.apply_attested_transaction_offline(committed_request)
            backend.prove_idempotency_offline(committed_request)
            backend.prove_compare_and_swap_offline(committed_request)

            rollback_request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "rollback", "generation": 2},
                label="rollback",
                deadline_epoch=SYNTHETIC_NOW_V2 + 60,
            )
            backend.apply_with_fault_offline(rollback_request, "AFTER_REPLACE")

            interrupted_request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "interrupted", "generation": 3},
                label="interrupted",
                deadline_epoch=SYNTHETIC_NOW_V2 + 60,
            )
            backend.prepare_interrupted_transaction_offline(interrupted_request)
            recovery_snapshot = backend.snapshot_offline()
            prepared_catalog = backend.list_prepared_transactions_offline()
            batch = backend_contract_v2.build_resumable_recovery_batch_offline_v2(
                recovery_snapshot,
                prepared_catalog,
                batch_epoch=_sha("recovery-batch"),
                deadline_epoch=SYNTHETIC_NOW_V2 + 60,
            )
            recovery_request = backend_harness_v2.build_synthetic_recovery_request_v2(
                prepared_catalog["records"][0], batch, checkpoint_index=0
            )
            backend.reconcile_attested_transaction_offline(recovery_request)
            backend.finalize_probe_observations_offline(
                lock_verified=lock_verified
            )

        snapshot = backend.snapshot_offline()
        terminal_port = terminal_v2.PhysicalTerminalEvidencePortV2(
            terminal_v2.PhysicalTerminalEvidencePortConfigV2(
                enabled=terminal_enabled,
                scope_attestation=(
                    terminal_v2.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2
                ),
            ),
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        ledger_root = Path(root) / "resolved-authority"
        ledger_storage = durable_authority_harness_v2._storage(ledger_root)
        ledger = durable_authority_harness_v2._ledger(
            ledger_root,
            ledger_storage,
            _sha("resolved-authority-root"),
        )
        opened = ledger.open_offline()
        if opened.get("ok") is not True:
            raise RuntimeError("SYNTHETIC_RESOLVED_LEDGER_OPEN_FAILED")
        resolved_catalog_port = (
            resolved_port_harness_v2.make_physical_resolved_catalog_port_v2(
                backend=backend, ledger=ledger
            )
        )
        resolved_storage_binding = (
            durable_authority_v2.durable_authority_storage_binding_sha256_v2(
                ledger_storage
            )
        )
        authority = adapter_v2.build_synthetic_physical_observation_authority_v2(
            snapshot=snapshot,
            maintenance_epoch=_sha("maintenance-epoch"),
            maintenance_lease_receipt_sha256=_sha("maintenance-lease-receipt"),
            resolved_ledger_storage_binding_sha256=resolved_storage_binding,
            issued_at_epoch=SYNTHETIC_NOW_V2 - 1,
            expires_at_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        observation_lease = observation_lease_v2.PhysicalMultiStoreObservationLeaseV2(
            observation_lease_v2.PhysicalMultiStoreObservationLeaseConfigV2(
                enabled=True,
                scope_attestation=(
                    observation_lease_v2.OFFLINE_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
                ),
                expected_backend_object_identity_sha256=(
                    source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        backend
                    )
                ),
                expected_ledger_object_identity_sha256=(
                    source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        ledger
                    )
                ),
                expected_backend_lock_namespace_sha256=backend._lock_namespace(),
                expected_resolved_ledger_storage_binding_sha256=(
                    resolved_storage_binding
                ),
                max_ttl_seconds=300,
                lock_timeout_seconds=0.01,
            ),
            backend=backend,
            durable_authority_ledger=ledger,
            clock=lambda: SYNTHETIC_NOW_V2,
            nonce_source=lambda: "synthetic-physical-conformance-lease",
        )
        locked_collection = locked_collection_v2.PhysicalLockedAggregateCollectionV2(
            locked_collection_v2.PhysicalLockedAggregateCollectionConfigV2(
                enabled=True,
                scope_attestation=(
                    locked_collection_v2.OFFLINE_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_ATTESTATION_V2
                ),
                expected_lease_object_identity_sha256=(
                    source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        observation_lease
                    )
                ),
                expected_backend_object_identity_sha256=(
                    source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        backend
                    )
                ),
                expected_ledger_object_identity_sha256=(
                    source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        ledger
                    )
                ),
                lease_ttl_seconds=60,
            ),
            observation_lease=observation_lease,
            backend=backend,
            durable_authority_ledger=ledger,
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        adapter = make_adapter_v2(
            backend=backend,
            terminal_evidence_port=terminal_port,
            resolved_catalog_port=resolved_catalog_port,
            observation_lease=observation_lease,
            locked_aggregate_collection=locked_collection,
            authority_sha256=authority["authority_sha256"],
        )
        yield {
            "adapter": adapter,
            "backend": backend,
            "terminal_port": terminal_port,
            "resolved_catalog_port": resolved_catalog_port,
            "resolved_ledger": ledger,
            "observation_lease": observation_lease,
            "locked_collection": locked_collection,
            "authority": authority,
            "snapshot": snapshot,
        }


def run_physical_conformance_adapter_offline_harness_v2() -> dict[str, Any]:
    with synthetic_physical_conformance_context_v2() as values:
        result = values["adapter"].assess_offline(
            backend=values["backend"],
            terminal_evidence_port=values["terminal_port"],
            resolved_catalog_port=values["resolved_catalog_port"],
            observation_lease=values["observation_lease"],
            locked_aggregate_collection=values["locked_collection"],
            observation_authority=values["authority"],
        )
        complete_offline = bool(
            result.get("ok") is True
            and result.get("status")
            == "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_TEMPORARY_COMPLETE"
            and result.get("reasons") == []
            and result.get("dependencies_verified") is True
            and result.get("observation_authority_verified") is True
            and result.get("authority_revalidation_count") == 3
            and result.get("lease_revalidation_count") == 8
            and result.get("locked_collection_receipt_verified") is True
            and result.get("required_port_count") == 6
            and result.get("available_port_count") == 6
            and result.get("validated_read_port_count") == 5
            and result.get("snapshot_verified") is True
            and result.get("transaction_log_audit_verified") is True
            and result.get("prepared_catalog_verified") is True
            and result.get("resolved_catalog_verified") is True
            and result.get("resolved_state_supported") is True
            and result.get("capability_probe_verified") is True
            and result.get("terminal_normalizer_bound") is True
            and result.get("terminal_normalizer_called") is False
            and result.get("partial_conformance_verified") is True
            and result.get("complete_conformance_verified") is True
            and result.get("aggregate_audit_verified") is True
            and result.get("stable_observation_window_verified") is True
            and result.get("optimistic_atomic_observation_verified") is True
            and result.get("shared_lock_atomicity_verified") is True
            and result.get("filesystem_accessed") is True
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("write_executed") is False
            and result.get("registry_write") is False
            and result.get("no_order_sent") is True
            and result.get("production_authority") is False
            and result.get("production_ready") is False
            and result.get("runtime_integrated") is False
            and result.get("activation_allowed") is False
            and result.get("live_allowed") is False
        )
        return {
            "ok": complete_offline,
            "status": (
                "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_PASSED"
                if complete_offline
                else "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_HARNESS_FAILED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_HARNESS_V2_VERSION,
            "complete_offline": complete_offline,
            "adapter_result": result,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }


__all__ = [
    "SYNTHETIC_NOW_V2",
    "make_adapter_v2",
    "run_physical_conformance_adapter_offline_harness_v2",
    "synthetic_physical_conformance_context_v2",
]
