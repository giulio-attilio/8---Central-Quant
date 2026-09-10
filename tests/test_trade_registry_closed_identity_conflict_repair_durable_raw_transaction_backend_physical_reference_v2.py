from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical


class TemporaryPhysicalDurableRawTransactionBackendV2Tests(unittest.TestCase):
    def test_complete_physical_harness_passes_without_production_authority(self) -> None:
        result = harness.run_temporary_physical_reference_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["capability_evidence_count"], 9)
        self.assertTrue(result["lock_verified"])
        self.assertTrue(result["wal_cas_replace_fsync_backup_verified"])
        self.assertTrue(result["idempotency_verified"])
        self.assertTrue(result["rollback_verified"])
        self.assertTrue(result["interrupted_recovery_verified"])
        self.assertTrue(result["prepared_catalog_drained"])
        self.assertTrue(result["temporary_storage_only"])
        self.assertTrue(result["no_order_sent"])
        for key in (
            "durable", "production_evidence", "production_ready", "runtime_integrated",
            "activation_allowed", "live_allowed", "real_registry_accessed",
            "network_accessed", "broker_called",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_constructor_performs_no_filesystem_write(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            target = Path(parent) / "not-created"
            backend = physical.TemporaryPhysicalDurableRawTransactionBackendV2(target)

            self.assertFalse(target.exists())
            with self.assertRaisesRegex(
                physical.TemporaryPhysicalReferenceBlockedV2,
                "PHYSICAL_REFERENCE_DEFAULT_OFF",
            ):
                backend.snapshot_offline()

    def test_enabled_backend_rejects_non_temporary_target(self) -> None:
        workspace_target = Path(__file__).resolve().parent / "c3_durable_backend_v2_forbidden"

        with self.assertRaisesRegex(
            physical.TemporaryPhysicalReferenceBlockedV2,
            "TEMPORARY_ROOT_REQUIRED",
        ):
            physical.TemporaryPhysicalDurableRawTransactionBackendV2(
                workspace_target,
                enabled=True,
                scope_attestation=physical.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            )
        self.assertFalse(workspace_target.exists())

    def test_enabled_backend_requires_exact_scope_attestation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            with self.assertRaisesRegex(
                physical.TemporaryPhysicalReferenceBlockedV2,
                "TEMPORARY_PHYSICAL_REFERENCE_SCOPE_REQUIRED",
            ):
                physical.TemporaryPhysicalDurableRawTransactionBackendV2(
                    root, enabled=True, scope_attestation="WRONG"
                )

    def test_unprobed_backend_fails_evidence_conformance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            backend = physical.TemporaryPhysicalDurableRawTransactionBackendV2(
                root,
                enabled=True,
                scope_attestation=physical.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
                clock=lambda: harness.SYNTHETIC_NOW_V2,
            )
            backend.initialize_synthetic_registry_offline({"closed_trades": []})
            auditor = contract.DurableRawTransactionBackendConformanceV2(
                contract.DurableRawTransactionBackendConformanceConfigV2(
                    enabled=True,
                    scope_attestation=contract.OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2,
                )
            )

            result = auditor.audit_offline(backend)

        self.assertFalse(result["ok"])
        self.assertIn("DURABLE_BACKEND_V2_CAPABILITY_EVIDENCE_INVALID", result["reasons"])

    def test_expired_transaction_deadline_fails_before_request_creation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            backend = physical.TemporaryPhysicalDurableRawTransactionBackendV2(
                root,
                enabled=True,
                scope_attestation=physical.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
                clock=lambda: harness.SYNTHETIC_NOW_V2,
            )
            backend.initialize_synthetic_registry_offline({"closed_trades": []})

            with self.assertRaisesRegex(
                physical.TemporaryPhysicalReferenceBlockedV2,
                "V2_TRANSACTION_DEADLINE_INVALID_OR_EXPIRED",
            ):
                backend.build_transaction_request_offline(
                    {"closed_trades": []},
                    label="expired",
                    deadline_epoch=harness.SYNTHETIC_NOW_V2,
                )


if __name__ == "__main__":
    unittest.main()
