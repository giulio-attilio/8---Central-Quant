from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off collection must not inspect dependencies")


class PhysicalLockedAggregateCollectionOfflineV2Tests(unittest.TestCase):
    def test_harness_proves_eight_reads_under_same_released_lease(self) -> None:
        result = harness.run_physical_locked_aggregate_collection_offline_harness_v2()

        self.assertTrue(result["ok"])
        self.assertTrue(result["same_lease_eight_reads_verified"])
        self.assertTrue(result["shared_lock_atomicity_verified"])
        self.assertTrue(result["lease_released_after_collection"])
        collected = result["collection_result"]
        self.assertTrue(collected["ok"])
        self.assertEqual(collected["lease_revalidation_count"], 8)
        self.assertFalse(collected["real_registry_accessed"])
        self.assertFalse(collected["network_accessed"])
        self.assertFalse(collected["live_allowed"])

    def test_receipt_binds_all_four_stable_physical_views(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as values:
            result = values["locked_collection"].collect_offline()

        receipt = result["collection_receipt"]
        self.assertTrue(
            contract.physical_locked_aggregate_collection_receipt_valid_v2(receipt)
        )
        self.assertEqual(
            receipt["initial_backend_snapshot_sha256"],
            receipt["final_backend_snapshot_sha256"],
        )
        self.assertEqual(
            receipt["initial_transaction_log_audit_sha256"],
            receipt["final_transaction_log_audit_sha256"],
        )
        self.assertEqual(
            receipt["initial_prepared_catalog_sha256"],
            receipt["final_prepared_catalog_sha256"],
        )
        self.assertEqual(
            receipt["initial_resolved_catalog_sha256"],
            receipt["final_resolved_catalog_sha256"],
        )

    def test_lock_receipt_is_authoritative_while_pure_aggregate_stays_neutral(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as values:
            result = values["locked_collection"].collect_offline()

        self.assertTrue(result["shared_lock_atomicity_verified"])
        self.assertTrue(
            result["collection_receipt"]["shared_lock_atomicity_verified"]
        )
        self.assertFalse(
            result["aggregate_audit"]["shared_lock_atomicity_verified"]
        )

    def test_default_off_returns_without_inspecting_dependencies(self) -> None:
        collector = contract.PhysicalLockedAggregateCollectionV2(
            observation_lease=_Explosive(),
            backend=_Explosive(),
            durable_authority_ledger=_Explosive(),
        )

        result = collector.collect_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_DEFAULT_OFF",
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_expiry_between_reads_fails_closed_and_releases_both_locks(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as values:
            now = physical_harness.SYNTHETIC_NOW_V2
            clock_values = iter([now, now, now + 61])
            collector = harness.make_physical_locked_aggregate_collection_v2(
                observation_lease=values["observation_lease"],
                backend=values["backend"],
                ledger=values["resolved_ledger"],
                clock=lambda: next(clock_values),
            )

            result = collector.collect_offline()
            lease_snapshot = values["observation_lease"].snapshot()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_NOT_LIVE"
        )
        self.assertEqual(result["lease_revalidation_count"], 1)
        self.assertTrue(result["lease_released_after_collection"])
        self.assertEqual(lease_snapshot["held_lock_count"], 0)

    def test_substituted_lease_instance_is_rejected_before_read(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as original:
            with physical_harness.synthetic_physical_conformance_context_v2() as substitute:
                configured = vars(original["locked_collection"])["_config"]
                collector = contract.PhysicalLockedAggregateCollectionV2(
                    configured,
                    observation_lease=substitute["observation_lease"],
                    backend=original["backend"],
                    durable_authority_ledger=original["resolved_ledger"],
                    clock=lambda: physical_harness.SYNTHETIC_NOW_V2,
                )
                result = collector.collect_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_IDENTITY_MISMATCH",
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_tampered_or_resealed_lock_claim_is_rejected(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as values:
            result = values["locked_collection"].collect_offline()

        tampered = copy.deepcopy(result["collection_receipt"])
        tampered["shared_lock_atomicity_verified"] = False
        self.assertFalse(
            contract.physical_locked_aggregate_collection_receipt_valid_v2(tampered)
        )
        tampered["receipt_sha256"] = (
            contract.physical_locked_aggregate_collection_receipt_sha256_v2(
                tampered
            )
        )
        self.assertFalse(
            contract.physical_locked_aggregate_collection_receipt_valid_v2(tampered)
        )

    def test_corrupt_resolved_store_fails_closed_and_releases_lease(self) -> None:
        with physical_harness.synthetic_physical_conformance_context_v2() as values:
            journal = Path(vars(values["resolved_ledger"])["_storage"].journal_path)
            journal.write_text("{corrupt", encoding="utf-8")

            result = values["locked_collection"].collect_offline()
            lease_snapshot = values["observation_lease"].snapshot()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PHYSICAL_MULTISTORE_RESOLVED_SCAN_READ_FAILED"
        )
        self.assertTrue(result["lease_released_after_collection"])
        self.assertEqual(lease_snapshot["held_lock_count"], 0)

    def test_contract_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "physical_locked_aggregate_collection_offline_v2", main_source
        )
        self.assertNotIn("PhysicalLockedAggregateCollectionV2", main_source)


if __name__ == "__main__":
    unittest.main()
