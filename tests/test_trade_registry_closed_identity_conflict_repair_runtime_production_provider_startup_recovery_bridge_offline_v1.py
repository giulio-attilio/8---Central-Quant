from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_v1 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off bridge must not inspect dependencies")


class _ProviderPortSubclass(
    contract.SyntheticProductionStartupRecoveryProviderPortDoubleV1
):
    pass


class ProductionProviderStartupRecoveryBridgeOfflineV1Tests(unittest.TestCase):
    def test_harness_exercises_all_four_capabilities_synthetically(self) -> None:
        result = (
            harness.run_synthetic_production_provider_startup_recovery_bridge_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["initial_prepared_count"], 2)
        self.assertEqual(result["final_prepared_count"], 0)
        self.assertEqual(result["final_resolved_count"], 0)
        self.assertTrue(result["all_four_bridge_capabilities_exercised"])
        self.assertEqual(
            result["bridge_counters"],
            {
                "snapshot_offline": 2,
                "list_prepared_transactions_offline": 2,
                "inspect_transaction_log_offline": 2,
                "reconcile_attested_transaction_offline": 2,
            },
        )
        self.assertEqual(result["production_store_apply_call_count"], 0)
        self.assertEqual(result["production_store_recovery_call_count"], 0)
        self.assertFalse(result["production_provider_instantiated"])
        self.assertFalse(result["production_provider_called"])
        self.assertFalse(result["production_backend_called"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["live_allowed"])
        self.assertFalse(result["real_registry_accessed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_fails_before_dependency_inspection(self) -> None:
        bridge = contract.OfflineProductionProviderStartupRecoveryBridgeV1(
            protected_binding=_Explosive(),
            provider_port=_Explosive(),
        )

        with self.assertRaisesRegex(
            contract.OfflineProductionProviderStartupRecoveryBridgeBlockedV1,
            "PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_DEFAULT_OFF",
        ):
            bridge.snapshot_offline()

    def test_wrong_binding_pin_fails_before_provider_port_call(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            values = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                root, prepared_count=0
            )
            bridge = contract.OfflineProductionProviderStartupRecoveryBridgeV1(
                protected_binding=values["protected_identity_binding"],
                provider_port=values["provider_port"],
                config=contract.OfflineProductionProviderStartupRecoveryBridgeConfigV1(
                    enabled=True,
                    scope_attestation=(
                        contract.OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1
                    ),
                    expected_binding_sha256="0" * 64,
                ),
            )

            with self.assertRaisesRegex(
                contract.OfflineProductionProviderStartupRecoveryBridgeBlockedV1,
                "PRODUCTION_PROVIDER_STARTUP_RECOVERY_BINDING_INVALID",
            ):
                bridge.snapshot_offline()
            self.assertEqual(
                values["provider_port"].counters()["snapshot_call_count"], 0
            )

    def test_provider_port_subclass_is_rejected_without_call(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            values = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                root, prepared_count=0
            )
            subclass_port = _ProviderPortSubclass(
                temporary_backend=values["backend"]
            )
            binding = values["protected_identity_binding"]
            bridge = contract.OfflineProductionProviderStartupRecoveryBridgeV1(
                protected_binding=binding,
                provider_port=subclass_port,
                config=contract.OfflineProductionProviderStartupRecoveryBridgeConfigV1(
                    enabled=True,
                    scope_attestation=(
                        contract.OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1
                    ),
                    expected_binding_sha256=binding.binding_sha256,
                ),
            )

            with self.assertRaisesRegex(
                contract.OfflineProductionProviderStartupRecoveryBridgeBlockedV1,
                "EXACT_SYNTHETIC_PROVIDER_PORT_REQUIRED",
            ):
                bridge.snapshot_offline()
            self.assertEqual(subclass_port.counters()["snapshot_call_count"], 0)

    def test_snapshot_from_different_backend_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as first:
            with tempfile.TemporaryDirectory(
                prefix="c3_durable_backend_v2_"
            ) as second:
                values = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                    first, prepared_count=0
                )
                other = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                    second, prepared_count=0
                )
                binding = values["protected_identity_binding"]
                mismatched_port = contract.SyntheticProductionStartupRecoveryProviderPortDoubleV1(
                    temporary_backend=other["backend"]
                )
                bridge = contract.OfflineProductionProviderStartupRecoveryBridgeV1(
                    protected_binding=binding,
                    provider_port=mismatched_port,
                    config=contract.OfflineProductionProviderStartupRecoveryBridgeConfigV1(
                        enabled=True,
                        scope_attestation=(
                            contract.OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1
                        ),
                        expected_binding_sha256=binding.binding_sha256,
                    ),
                )

                with self.assertRaisesRegex(
                    contract.OfflineProductionProviderStartupRecoveryBridgeBlockedV1,
                    "SYNTHETIC_PROVIDER_BACKEND_SNAPSHOT_INVALID",
                ):
                    bridge.snapshot_offline()

    def test_interruption_after_recovery_delegation_fails_unknown_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            values = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                root, prepared_count=1
            )

            def interrupt_after_delegation(_request):
                raise RuntimeError("synthetic bridge interruption")

            values[
                "provider_port"
            ].reconcile_startup_recovery_transaction_offline = (
                interrupt_after_delegation
            )
            snapshot = values["backend_snapshot"]
            result = values["adapter"](
                {
                    "state": "QUIESCED",
                    "maintenance_epoch": backend_contract.stable_sha256_v2(
                        "synthetic-interrupted-provider-bridge-epoch-v1"
                    ),
                    "lock_namespace_sha256": snapshot[
                        "lock_namespace_sha256"
                    ],
                    "registered_writer_count": 19,
                    "inflight_mutations": 0,
                    "shared_lock_acquired": True,
                }
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["backend_called"])
            self.assertTrue(result["write_state_unknown"])
            self.assertEqual(
                values["bridge"].counters()[
                    "reconcile_attested_transaction_offline"
                ],
                1,
            )
            self.assertFalse(result["real_registry_accessed"])
            self.assertFalse(result["network_accessed"])
            self.assertTrue(result["no_order_sent"])

    def test_reprs_hide_bound_dependencies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            values = harness.build_synthetic_production_provider_startup_recovery_bridge_context_v1(
                root, prepared_count=0
            )

            self.assertEqual(
                repr(values["bridge"]),
                "OfflineProductionProviderStartupRecoveryBridgeV1(<protected>)",
            )
            self.assertEqual(
                repr(values["provider_port"]),
                "SyntheticProductionStartupRecoveryProviderPortDoubleV1(<protected>)",
            )

    def test_bridge_remains_absent_from_runtime_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_production_provider_startup_recovery_bridge_offline_v1",
            source,
        )
        self.assertNotIn(
            "run_synthetic_production_provider_startup_recovery_bridge_harness_v1",
            source,
        )


if __name__ == "__main__":
    unittest.main()
