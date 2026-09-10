from __future__ import annotations

import copy
import tempfile
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_harness_v2 as harness


class ResumableStartupRecoveryV2Tests(unittest.TestCase):
    def test_complete_harness_recovers_two_items_by_checkpoint(self) -> None:
        result = harness.run_resumable_startup_recovery_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["initial_prepared_count"], 2)
        self.assertEqual(result["terminal_receipt_count"], 2)
        self.assertEqual(result["checkpoint_count"], 3)
        self.assertTrue(result["all_checkpoints_distinct"])
        self.assertTrue(result["prepared_catalog_drained"])
        self.assertTrue(result["protected_repr_verified"])
        self.assertTrue(result["no_order_sent"])
        for key in (
            "durable", "production_authority", "runtime_integrated",
            "activation_allowed", "live_allowed", "real_registry_accessed",
            "network_accessed", "broker_called",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_does_not_inspect_source(self) -> None:
        startup = contract.ResumableStartupRecoveryV2()

        result = startup.plan_offline({}, {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "STARTUP_RECOVERY_V2_DEFAULT_OFF")
        self.assertIsNone(result["protected_state"])

    def test_plan_rejects_unproven_nonphysical_snapshot(self) -> None:
        startup = contract.ResumableStartupRecoveryV2(
            contract.StartupRecoveryConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2,
            ),
            clock=lambda: harness.SYNTHETIC_NOW_V2,
        )

        result = startup.plan_offline({}, {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "STARTUP_RECOVERY_V2_SOURCE_INVALID")

    def test_completion_requires_empty_final_catalog(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
                root,
                enabled=True,
                scope_attestation=physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
                clock=lambda: harness.SYNTHETIC_NOW_V2,
            )
            backend.initialize_synthetic_registry_offline({"closed_trades": []})
            snapshot = backend.snapshot_offline()
            catalog = backend.list_prepared_transactions_offline()
            startup = contract.ResumableStartupRecoveryV2(
                contract.StartupRecoveryConfigV2(
                    enabled=True,
                    scope_attestation=contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2,
                ),
                clock=lambda: harness.SYNTHETIC_NOW_V2 + 1,
            )
            planned = startup.plan_offline(snapshot, catalog)
            non_empty = copy.deepcopy(catalog)
            non_empty["prepared_count"] = 1

            result = startup.finalize_offline(
                planned["protected_state"], snapshot, non_empty
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "STARTUP_RECOVERY_V2_FINAL_CATALOG_NOT_DRAINED_OR_INVALID",
        )

    def test_config_budgets_are_bounded(self) -> None:
        with self.assertRaises(ValueError):
            contract.StartupRecoveryConfigV2(max_prepared_records=0)
        with self.assertRaises(ValueError):
            contract.StartupRecoveryConfigV2(max_recovery_seconds=301)


if __name__ == "__main__":
    unittest.main()
