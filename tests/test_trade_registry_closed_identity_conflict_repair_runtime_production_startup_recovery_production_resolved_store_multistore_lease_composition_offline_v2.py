from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off composition must not inspect dependencies")


class ProductionResolvedStoreMultistoreLeaseCompositionOfflineV2Tests(
    unittest.TestCase
):
    def test_harness_proves_full_protected_chain_in_memory(self) -> None:
        result = (
            harness.run_resolved_store_multistore_lease_composition_offline_harness_v2()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["chain_verified"])
        self.assertTrue(result["lease_released_after_execution"])
        self.assertFalse(result["physical_store_called"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_returns_before_dependency_inspection(self) -> None:
        composition = contract.ProductionResolvedStoreMultistoreLeaseCompositionV2(
            resolved_store_binding=_Explosive(),
            multistore_lease_binding=_Explosive(),
            synthetic_authority=_Explosive(),
            transaction_projection=_Explosive(),
            resolved_projection=_Explosive(),
            transaction_lock_port=_Explosive(),
            resolved_lock_port=_Explosive(),
            lease_executor=_Explosive(),
            event_observer=_Explosive(),
        )

        result = composition.execute_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_DEFAULT_OFF",
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_receipt_binds_store_projection_multistore_and_executor(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()

        result = values["composition"].execute_offline()
        receipt = result["execution_receipt"]

        self.assertTrue(
            contract.production_resolved_store_multistore_lease_execution_receipt_valid_v2(
                receipt
            )
        )
        self.assertEqual(
            receipt["resolved_store_binding_sha256"],
            values["store_binding"].binding_sha256,
        )
        self.assertEqual(
            receipt["multistore_lease_binding_sha256"],
            values["multistore_binding"].binding_sha256,
        )
        self.assertEqual(
            receipt["resolved_projection_sha256"],
            values["resolved_projection"].projection_sha256,
        )
        self.assertTrue(receipt["same_instances_verified"])

    def test_reconstructed_resolved_projection_is_rejected_before_lock(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()
        original = values["resolved_projection"]
        reconstructed = type(original)(
            port_role=original.port_role,
            store_identity_sha256=original.store_identity_sha256,
            projection=copy.deepcopy(dict(original.projection)),
            projection_sha256=original.projection_sha256,
        )
        values["composition"]._resolved_projection = reconstructed

        result = values["composition"].execute_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_INSTANCE_MISMATCH",
        )
        self.assertEqual(values["events"], [])

    def test_reconstructed_store_binding_is_rejected_before_lock(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()
        original = values["store_binding"]
        reconstructed = type(original)(
            authenticated_authority_binding_sha256=(
                original.authenticated_authority_binding_sha256
            ),
            multistore_lease_binding_sha256=(
                original.multistore_lease_binding_sha256
            ),
            resolved_lock_port_projection_sha256=(
                original.resolved_lock_port_projection_sha256
            ),
            binding=copy.deepcopy(dict(original.binding)),
            binding_sha256=original.binding_sha256,
        )
        values["composition"]._store_binding = reconstructed

        result = values["composition"].execute_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_INSTANCE_MISMATCH",
        )
        self.assertEqual(values["events"], [])

    def test_unshared_event_observer_is_rejected_before_lock(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()
        values["resolved_port"]._event_sink = []

        result = values["composition"].execute_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "RESOLVED_STORE_MULTISTORE_LEASE_CROSS_BINDING_INVALID",
        )
        self.assertEqual(values["events"], [])

    def test_second_lock_failure_releases_first_and_returns_no_receipt(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2(
            fail_resolved_acquire=True
        )

        result = values["composition"].execute_offline()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_LOCK_CONTENTION",
        )
        self.assertIsNone(result["execution_receipt"])
        self.assertTrue(result["lease_released_after_execution"])
        self.assertEqual(
            values["events"],
            [
                ("ACQUIRE", "RAW_TRANSACTION_STORE"),
                ("RELEASE", "RAW_TRANSACTION_STORE"),
            ],
        )
        self.assertEqual(values["executor"].snapshot()["held_lock_count"], 0)

    def test_execution_is_single_use_because_event_history_is_bound(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()

        first = values["composition"].execute_offline()
        second = values["composition"].execute_offline()

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(
            second["reason"],
            "RESOLVED_STORE_MULTISTORE_LEASE_CROSS_BINDING_INVALID",
        )

    def test_resealed_live_or_store_call_claim_is_rejected(self) -> None:
        values = harness.build_resolved_store_multistore_lease_composition_context_v2()
        result = values["composition"].execute_offline()
        tampered = copy.deepcopy(result["execution_receipt"])
        tampered["live_allowed"] = True
        tampered["physical_store_called"] = True
        tampered["receipt_sha256"] = (
            contract.production_resolved_store_multistore_lease_execution_receipt_sha256_v2(
                tampered
            )
        )

        self.assertFalse(
            contract.production_resolved_store_multistore_lease_execution_receipt_valid_v2(
                tampered
            )
        )

    def test_composition_is_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "production_resolved_store_multistore_lease_composition_offline_v2",
            main_source,
        )
        self.assertNotIn(
            "ProductionResolvedStoreMultistoreLeaseCompositionV2", main_source
        )


if __name__ == "__main__":
    unittest.main()
