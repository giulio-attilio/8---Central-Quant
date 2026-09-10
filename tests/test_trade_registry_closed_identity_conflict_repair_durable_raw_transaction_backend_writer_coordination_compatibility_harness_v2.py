from __future__ import annotations

import builtins
import socket
import unittest
from unittest import mock

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2 as provider_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1 as invocation
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


class WriterCoordinationCompatibilityHarnessV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        upstream = provider_harness.build_provider_store_projection_fixture_v2()
        cls.provider_bundle = upstream["projection"]["protected_bundle"]

    def test_complete_harness_passes_without_operational_calls(self) -> None:
        with (
            mock.patch.object(
                invocation.ProductionWriterInvocationAdapterV1,
                "invoke",
                side_effect=AssertionError("INVOCATION_ADAPTER_CALLED"),
            ),
            mock.patch.object(
                coordinator.ClosedRepairWriterRuntimeCoordinatorV1,
                "mutation",
                side_effect=AssertionError("COORDINATOR_MUTATION_CALLED"),
            ),
            mock.patch.object(
                coordinator.ClosedRepairWriterRuntimeCoordinatorV1,
                "maintenance_lease",
                side_effect=AssertionError("COORDINATOR_MAINTENANCE_CALLED"),
            ),
            mock.patch.object(
                builtins, "open", side_effect=AssertionError("FILESYSTEM_CALLED")
            ),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("NETWORK_CALLED"),
            ),
        ):
            result = harness.run_writer_coordination_compatibility_harness_v2(
                self.provider_bundle
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["writer_count"], 19)
        self.assertEqual(result["writer_callback_invocations"], 0)
        self.assertTrue(result["exact_writer_inventory_verified"])
        self.assertTrue(result["source_signatures_verified"])
        self.assertTrue(result["v1_callable_manifest_verified"])
        self.assertTrue(result["same_permit_instance_verified_synthetic"])
        self.assertTrue(result["lease_live_verified_synthetic"])
        self.assertTrue(result["single_lock_owner_verified"])
        self.assertTrue(result["no_call_surface"])
        for key in (
            "provider_called", "store_called", "backend_called", "writer_called",
            "invocation_adapter_called", "coordinator_called", "lock_acquired",
            "filesystem_accessed", "real_registry_accessed", "network_accessed",
            "broker_called", "write_executed", "production_authority",
            "runtime_integrated", "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)
        self.assertTrue(result["no_order_sent"])

    def test_callable_manifest_uses_the_v1_manifest_algorithm(self) -> None:
        fixture = harness.build_writer_coordination_compatibility_fixture_v2(
            self.provider_bundle
        )

        expected = invocation.production_writer_callable_manifest_sha256_v1(
            fixture["callable_wrappers"]
        )

        self.assertEqual(
            fixture["callable_manifest_projection"]["callable_manifest_sha256"],
            expected,
        )
        self.assertEqual(fixture["callback_counter"]["count"], 0)

    def test_output_is_deterministic_for_same_upstream_and_clock(self) -> None:
        first = harness.run_writer_coordination_compatibility_harness_v2(
            self.provider_bundle, now_epoch=2_000
        )
        second = harness.run_writer_coordination_compatibility_harness_v2(
            self.provider_bundle, now_epoch=2_000
        )

        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(first["bundle_sha256"], second["bundle_sha256"])

    def test_missing_upstream_bundle_fails_closed(self) -> None:
        result = harness.run_writer_coordination_compatibility_harness_v2(None)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "WRITER_COORDINATION_COMPATIBILITY_V2_FIXTURE_INVALID",
        )
        self.assertEqual(result["writer_callback_invocations"], 0)
        self.assertFalse(result["backend_called"])

    def test_protected_output_has_no_executable_surface(self) -> None:
        result = harness.run_writer_coordination_compatibility_harness_v2(
            self.provider_bundle
        )
        protected = result["protected_bundle"]

        self.assertTrue(
            contract.protected_writer_coordination_compatibility_bundle_valid_v2(
                protected
            )
        )
        for name in (
            "invoke", "apply", "reconcile", "load_exact_raw_registry",
            "acquire", "install", "activate", "start",
        ):
            self.assertFalse(hasattr(protected, name), name)


if __name__ == "__main__":
    unittest.main()
