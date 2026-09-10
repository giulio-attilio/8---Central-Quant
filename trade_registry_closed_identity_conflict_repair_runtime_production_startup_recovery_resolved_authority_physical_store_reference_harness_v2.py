"""Temporary-filesystem harness for the RESOLVED physical store reference."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import registry_v2_wal as wal_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1 as authenticated_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as schema_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2 as store_contract_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2 as reference_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-RESOLVED-AUTHORITY-PHYSICAL-STORE-"
    "REFERENCE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_500


def _sha(label: str) -> str:
    return hash_v2.stable_sha256_v2(
        {"resolved_authority_physical_store_reference": label}
    )


def _storage(root: Path) -> wal_v2.RegistryV2WalStorage:
    return wal_v2.RegistryV2WalStorage(
        snapshot_path=root / "authority.snapshot.json",
        journal_path=root / "authority.journal.jsonl",
        lock_path=root / "authority.wal.lock",
        backup_dir=root / "backups",
    )


def build_resolved_authority_physical_store_reference_context_v2(
    root: str | Path,
    *,
    revoked: bool = False,
) -> dict[str, Any]:
    temporary_root = Path(root).resolve(strict=False)
    ledger_storage = _storage(temporary_root)
    storage_binding_sha256 = (
        authority_v2.durable_authority_storage_binding_sha256_v2(
            ledger_storage
        )
    )

    schema_values = (
        schema_harness_v1.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
    )
    schema_result = schema_values["schema_contract"].define_offline(
        protected_provider_binding=schema_values["protected_identity_binding"]
    )
    protected_schema = schema_result["protected_schema"]
    schema = dict(protected_schema.schema)
    root_identity_sha256 = _sha("root-identity")
    root_attestation = authenticated_harness_v1._root_authority_attestation(
        root_identity_sha256=root_identity_sha256,
        storage_binding_sha256=storage_binding_sha256,
    )
    verifier = authenticated_harness_v1.SyntheticOfflineRootAuthorityVerifierV1()
    durable_receipt = authenticated_harness_v1._durable_authority_receipt(
        root_identity_sha256=root_identity_sha256,
        storage_binding_sha256=storage_binding_sha256,
        root_authority_attestation_sha256=root_attestation[
            "attestation_sha256"
        ],
    )
    recovery_identity = (
        authenticated_harness_v1.make_synthetic_startup_recovery_authority_identity_v1(
            backend_instance_sha256=schema[
                "source_backend_instance_sha256"
            ],
            registry_path_binding_sha256=schema[
                "source_registry_path_binding_sha256"
            ],
            lock_namespace_sha256=schema["source_lock_namespace_sha256"],
            authority_storage_binding_sha256=storage_binding_sha256,
        )
    )
    authority_contract = (
        authenticated_harness_v1.make_synthetic_authenticated_authority_binding_contract_v1(
            schema_sha256=protected_schema.schema_sha256,
            root_authority_attestation_sha256=root_attestation[
                "attestation_sha256"
            ],
            durable_authority_receipt_sha256=durable_receipt.receipt_sha256,
            recovery_identity_sha256=recovery_identity["identity_sha256"],
        )
    )
    authority_result = authority_contract.bind_offline(
        protected_evidence_schema=protected_schema,
        recovery_identity=recovery_identity,
        root_authority_attestation=root_attestation,
        root_authority_verifier=verifier,
        durable_authority_receipt=durable_receipt,
        now_epoch=SYNTHETIC_NOW_V2,
    )
    authenticated_binding = authority_result["protected_binding"]

    transaction_projection = (
        multistore_v2.build_production_store_lock_port_projection_offline_v2(
            port_role=multistore_v2.TRANSACTION_STORE_ROLE_V2,
            source_contract_version=(
                multistore_v2.EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2
            ),
            store_identity_sha256=_sha("transaction-store"),
            storage_binding_sha256=_sha("transaction-storage"),
            lock_namespace_sha256=_sha("transaction-lock"),
        )
    )
    resolved_projection = (
        multistore_v2.build_production_store_lock_port_projection_offline_v2(
            port_role=multistore_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2,
            source_contract_version=(
                multistore_v2.EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
            ),
            store_identity_sha256=_sha("resolved-store"),
            storage_binding_sha256=storage_binding_sha256,
            lock_namespace_sha256=_sha("resolved-lock"),
        )
    )
    multistore_contract = (
        multistore_v2.DormantProductionMultistoreObservationLeaseContractV2(
            multistore_v2.DormantProductionMultistoreObservationLeaseConfigV2(
                enabled=True,
                scope_attestation=(
                    multistore_v2.OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
                ),
                expected_transaction_store_projection_sha256=(
                    transaction_projection.projection_sha256
                ),
                expected_resolved_authority_store_projection_sha256=(
                    resolved_projection.projection_sha256
                ),
                expected_writer_coordination_binding_sha256=_sha(
                    "writer-coordination"
                ),
                expected_maintenance_lease_contract_sha256=dict(
                    authenticated_binding.binding
                )["maintenance_lease_receipt_sha256"],
                expected_authenticated_authority_contract_sha256=(
                    authenticated_binding.binding_sha256
                ),
                required_writer_count=19,
            )
        )
    )
    multistore_result = multistore_contract.bind_offline(
        transaction_store_lock_port=transaction_projection,
        resolved_authority_store_lock_port=resolved_projection,
    )
    multistore_binding = multistore_result["protected_binding"]
    store_contract = store_contract_v2.DormantProductionResolvedAuthorityStoreContractV2(
        store_contract_v2.DormantProductionResolvedAuthorityStoreConfigV2(
            enabled=True,
            scope_attestation=(
                store_contract_v2.OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2
            ),
            expected_authenticated_binding_sha256=(
                authenticated_binding.binding_sha256
            ),
            expected_multistore_binding_sha256=multistore_binding.binding_sha256,
            expected_resolved_projection_sha256=(
                resolved_projection.projection_sha256
            ),
            expected_authenticated_binding_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    authenticated_binding
                )
            ),
            expected_multistore_binding_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    multistore_binding
                )
            ),
            expected_resolved_projection_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_projection
                )
            ),
        )
    )
    store_result = store_contract.bind_offline(
        authenticated_authority_binding=authenticated_binding,
        multistore_lease_binding=multistore_binding,
        resolved_lock_port_projection=resolved_projection,
    )
    protected_store_binding = store_result["protected_binding"]

    ledger = authority_v2.DormantDurableReconciliationAuthorityLedgerV2(
        authority_v2.DormantDurableReconciliationAuthorityConfigV2(
            enabled=True,
            scope_attestation=(
                authority_v2.OFFLINE_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_SCOPE_ATTESTATION_V2
            ),
            expected_root_identity_sha256=root_identity_sha256,
            expected_storage_binding_sha256=storage_binding_sha256,
        ),
        storage=ledger_storage,
        lock_backend=storage_v1.CrossPlatformInterprocessFileLockBackendV1(
            temporary_root, enabled=True
        ),
        root_authority_attestation=root_attestation,
        root_authority_verifier=verifier,
    )
    revoked_keys = (
        frozenset({root_attestation["key_id_sha256"]})
        if revoked
        else frozenset()
    )
    revocation_source = reference_v2.InMemorySyntheticRootRevocationSourceV2(
        revoked_keys
    )
    reference = reference_v2.ResolvedAuthorityPhysicalStoreReferenceV2(
        reference_v2.ResolvedAuthorityPhysicalStoreReferenceConfigV2(
            enabled=True,
            scope_attestation=(
                reference_v2.OFFLINE_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_SCOPE_ATTESTATION_V2
            ),
            expected_store_binding_sha256=(
                protected_store_binding.binding_sha256
            ),
            expected_ledger_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    ledger
                )
            ),
            expected_root_verifier_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    verifier
                )
            ),
            expected_revocation_source_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    revocation_source
                )
            ),
            expected_storage_binding_sha256=storage_binding_sha256,
            expected_temporary_root_sha256=hash_v2.stable_sha256_v2(
                {"temporary_root": str(temporary_root)}
            ),
        ),
        protected_store_binding=protected_store_binding,
        durable_authority_ledger=ledger,
        root_authority_verifier=verifier,
        root_revocation_source=revocation_source,
        temporary_root=temporary_root,
    )
    return {
        "temporary_root": temporary_root,
        "schema_result": schema_result,
        "authority_result": authority_result,
        "multistore_result": multistore_result,
        "store_result": store_result,
        "protected_store_binding": protected_store_binding,
        "ledger": ledger,
        "root_authority_verifier": verifier,
        "root_revocation_source": revocation_source,
        "reference": reference,
    }


def run_resolved_authority_physical_store_reference_harness_v2() -> dict[str, Any]:
    root_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="c3_resolved_authority_v2_") as root:
        root_path = Path(root)
        values = build_resolved_authority_physical_store_reference_context_v2(
            root_path
        )
        reference = values["reference"]
        before = reference.snapshot()
        opened = reference.open_offline(now_epoch=SYNTHETIC_NOW_V2)
        recovered = reference.recover_offline(now_epoch=SYNTHETIC_NOW_V2)
        scanned = reference.read_resolved_records_offline(
            now_epoch=SYNTHETIC_NOW_V2
        )
        ok = bool(
            before["ready_for_temporary_offline_use"] is True
            and before["physical_store_implementation_bound"] is True
            and opened.get("ok") is True
            and recovered.get("ok") is True
            and scanned.get("ok") is True
            and scanned.get("record_count") == 0
            and scanned.get("complete_scan_verified") is True
            and scanned.get("wal_integrity_verified") is True
            and values["root_revocation_source"].call_count == 3
            and all(
                result.get("root_signature_reverified") is True
                and result.get("root_revocation_checked") is True
                and result.get("root_revoked") is False
                and result.get("physical_store_implementation_bound") is True
                and result.get("filesystem_accessed") is True
                and result.get("real_registry_accessed") is False
                and result.get("network_accessed") is False
                and result.get("broker_called") is False
                and result.get("no_order_sent") is True
                and result.get("production_ready") is False
                and result.get("runtime_integrated") is False
                and result.get("live_allowed") is False
                for result in (opened, recovered, scanned)
            )
            and repr(reference)
            == "ResolvedAuthorityPhysicalStoreReferenceV2(<protected>)"
        )
    temporary_storage_removed = bool(root_path and not root_path.exists())
    ok = bool(ok and temporary_storage_removed)
    return {
        "ok": ok,
        "status": (
            "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_HARNESS_V2_PASSED"
            if ok
            else "RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_PHYSICAL_STORE_REFERENCE_HARNESS_V2_VERSION,
        "temporary_storage_removed": temporary_storage_removed,
        "physical_store_implementation_bound": True,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "filesystem_accessed": True,
        "temporary_write_executed": True,
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
    "build_resolved_authority_physical_store_reference_context_v2",
    "run_resolved_authority_physical_store_reference_harness_v2",
]
