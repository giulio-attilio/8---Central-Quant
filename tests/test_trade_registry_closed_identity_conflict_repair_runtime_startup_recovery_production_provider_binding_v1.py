from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_production_provider_v1 as production_provider
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _ProviderSubclass(production_provider.ProductionClosedRepairProviderV1):
    pass


class _AdapterSubclass(startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1):
    pass


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off must not inspect dependencies")


class StartupRecoveryProductionProviderBindingV1Tests(unittest.TestCase):
    def _enabled_binder(self, protected):
        return contract.DormantStartupRecoveryProductionProviderBindingContractV1(
            config=contract.DormantStartupRecoveryProductionProviderBindingConfigV1(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
                ),
                expected_provider_store_binding_sha256=(
                    protected.binding_sha256
                ),
                expected_adapter_contract_sha256=(
                    contract.startup_recovery_adapter_contract_sha256_v1()
                ),
            )
        )

    def test_harness_binds_identities_without_calls_or_authority(self) -> None:
        result = (
            harness.run_synthetic_startup_recovery_production_provider_binding_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["provider_store_binding_verified"])
        self.assertTrue(result["exact_provider_class_verified"])
        self.assertTrue(result["exact_adapter_class_verified"])
        self.assertTrue(result["identity_binding_created"])
        self.assertFalse(result["direct_port_compatibility_verified"])
        self.assertTrue(result["bridge_required"])
        self.assertEqual(result["store_double_apply_call_count"], 0)
        self.assertEqual(result["store_double_recovery_call_count"], 0)
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["adapter_called"])
        self.assertFalse(result["recovery_executed"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["live_allowed"])
        self.assertFalse(result["real_registry_accessed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_does_not_inspect_any_argument(self) -> None:
        binder = contract.DormantStartupRecoveryProductionProviderBindingContractV1()

        result = binder.bind_offline(
            protected_provider_store_binding=_Explosive(),
            provider_type=_Explosive(),
            adapter_type=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_DEFAULT_OFF"],
        )
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["adapter_called"])

    def test_wrong_provider_binding_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_production_provider_binding_context_v1()
        binder = contract.DormantStartupRecoveryProductionProviderBindingContractV1(
            config=contract.DormantStartupRecoveryProductionProviderBindingConfigV1(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
                ),
                expected_provider_store_binding_sha256="0" * 64,
                expected_adapter_contract_sha256=(
                    contract.startup_recovery_adapter_contract_sha256_v1()
                ),
            )
        )

        result = binder.bind_offline(
            protected_provider_store_binding=values[
                "protected_provider_binding"
            ],
            provider_type=production_provider.ProductionClosedRepairProviderV1,
            adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
        )

        self.assertFalse(result["ok"])
        self.assertIn("PROVIDER_STORE_BINDING_PIN_MISMATCH", result["reasons"])
        self.assertFalse(result["identity_binding_created"])

    def test_subclasses_cannot_replace_exact_contract_classes(self) -> None:
        values = harness.build_synthetic_startup_recovery_production_provider_binding_context_v1()
        protected = values["protected_provider_binding"]
        binder = self._enabled_binder(protected)

        provider_result = binder.bind_offline(
            protected_provider_store_binding=protected,
            provider_type=_ProviderSubclass,
            adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
        )
        adapter_result = binder.bind_offline(
            protected_provider_store_binding=protected,
            provider_type=production_provider.ProductionClosedRepairProviderV1,
            adapter_type=_AdapterSubclass,
        )

        self.assertIn(
            "EXACT_PRODUCTION_PROVIDER_CLASS_REQUIRED",
            provider_result["reasons"],
        )
        self.assertIn(
            "EXACT_STARTUP_RECOVERY_ADAPTER_CLASS_REQUIRED",
            adapter_result["reasons"],
        )

    def test_protected_binding_is_tamper_evident_and_repr_safe(self) -> None:
        values = harness.build_synthetic_startup_recovery_production_provider_binding_context_v1()
        protected_provider = values["protected_provider_binding"]
        result = self._enabled_binder(protected_provider).bind_offline(
            protected_provider_store_binding=protected_provider,
            provider_type=production_provider.ProductionClosedRepairProviderV1,
            adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
        )
        protected = result["protected_binding"]

        self.assertTrue(
            contract.protected_startup_recovery_production_provider_binding_valid_v1(
                protected
            )
        )
        self.assertEqual(
            repr(protected),
            "ProtectedStartupRecoveryProductionProviderBindingV1(<protected>)",
        )
        tampered_mapping = copy.deepcopy(protected.binding)
        tampered_mapping["recovery_execution_allowed"] = True
        tampered = contract.ProtectedStartupRecoveryProductionProviderBindingV1(
            provider_store_binding_sha256=protected.provider_store_binding_sha256,
            adapter_contract_sha256=protected.adapter_contract_sha256,
            backend_instance_sha256=protected.backend_instance_sha256,
            binding=tampered_mapping,
            binding_sha256=protected.binding_sha256,
        )
        self.assertFalse(
            contract.protected_startup_recovery_production_provider_binding_valid_v1(
                tampered
            )
        )

    def test_binding_records_unresolved_direct_provider_port_gap(self) -> None:
        values = harness.build_synthetic_startup_recovery_production_provider_binding_context_v1()
        protected_provider = values["protected_provider_binding"]
        result = self._enabled_binder(protected_provider).bind_offline(
            protected_provider_store_binding=protected_provider,
            provider_type=production_provider.ProductionClosedRepairProviderV1,
            adapter_type=startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1,
        )
        binding = result["protected_binding"].binding

        self.assertTrue(result["ok"])
        self.assertFalse(binding["direct_port_compatibility_verified"])
        self.assertTrue(binding["bridge_required"])
        self.assertEqual(
            binding["required_backend_port_methods"],
            [
                "snapshot_offline",
                "list_prepared_transactions_offline",
                "inspect_transaction_log_offline",
                "reconcile_attested_transaction_offline",
            ],
        )
        self.assertFalse(binding["recovery_execution_allowed"])

    def test_contract_remains_absent_from_runtime_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_startup_recovery_production_provider_binding_contract_v1",
            source,
        )
        self.assertNotIn(
            "run_synthetic_startup_recovery_production_provider_binding_harness_v1",
            source,
        )


if __name__ == "__main__":
    unittest.main()
