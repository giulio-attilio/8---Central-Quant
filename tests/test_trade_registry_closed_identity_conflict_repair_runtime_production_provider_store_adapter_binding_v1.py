from __future__ import annotations

import ast
import copy
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1 as harness


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rehash_provider(value: dict) -> dict:
    value["projection_sha256"] = contract.provider_binding_projection_sha256_v1(
        value
    )
    return value


def _rehash_store(value: dict) -> dict:
    value["projection_sha256"] = contract.store_port_projection_sha256_v1(value)
    return value


def _rehash_adapter(value: dict) -> dict:
    value["snapshot_sha256"] = (
        adapter_contract.synthetic_store_double_snapshot_sha256_v1(value)
    )
    return value


class ProductionProviderStoreAdapterBindingV1Tests(unittest.TestCase):
    def _binder(
        self,
        *,
        provider: dict,
        store: dict,
        adapter: dict,
        enabled: bool = True,
        scope: str | None = contract.OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1,
        provider_pin: str | None = None,
        store_pin: str | None = None,
        adapter_pin: str | None = None,
        composition_pin: str | None = None,
    ) -> contract.DormantProductionProviderStoreAdapterBindingContractV1:
        return contract.DormantProductionProviderStoreAdapterBindingContractV1(
            config=contract.DormantProductionProviderStoreAdapterBindingConfigV1(
                enabled=enabled,
                scope_attestation=scope,
                expected_provider_projection_sha256=(
                    provider["projection_sha256"]
                    if provider_pin is None
                    else provider_pin
                ),
                expected_store_projection_sha256=(
                    store["projection_sha256"] if store_pin is None else store_pin
                ),
                expected_adapter_snapshot_sha256=(
                    adapter["snapshot_sha256"]
                    if adapter_pin is None
                    else adapter_pin
                ),
                expected_composition_attestation_sha256=(
                    provider["composition_attestation_sha256"]
                    if composition_pin is None
                    else composition_pin
                ),
            )
        )

    def _bind(
        self,
        values: dict,
        *,
        provider: dict | None = None,
        store: dict | None = None,
        adapter: dict | None = None,
        **config_overrides,
    ) -> dict:
        selected_provider = provider or values["provider_projection"]
        selected_store = store or values["store_projection"]
        selected_adapter = adapter or values["adapter_snapshot"]
        binder = self._binder(
            provider=selected_provider,
            store=selected_store,
            adapter=selected_adapter,
            **config_overrides,
        )
        return binder.bind_offline(
            provider_projection=selected_provider,
            store_projection=selected_store,
            adapter_snapshot=selected_adapter,
        )

    def test_complete_harness_passes_without_component_calls(self) -> None:
        result = harness.run_synthetic_provider_store_adapter_binding_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["cross_binding_verified_synthetic"])
        self.assertEqual(result["store_double_apply_call_count"], 0)
        self.assertEqual(result["store_double_recovery_call_count"], 0)
        for key in (
            "production_authority",
            "provider_called",
            "production_store_called",
            "production_backend_called",
            "runtime_integrated",
            "production_ready",
            "apply_allowed",
            "recovery_allowed",
            "activation_allowed",
            "live_allowed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[key], key)

    def test_projections_use_exact_schemas_and_independent_hashes(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        provider = values["provider_projection"]
        store = values["store_projection"]

        self.assertEqual(set(provider), contract._PROVIDER_PROJECTION_KEYS)
        self.assertEqual(set(store), contract._STORE_PROJECTION_KEYS)
        self.assertEqual(
            provider["projection_sha256"],
            contract.provider_binding_projection_sha256_v1(provider),
        )
        self.assertEqual(
            store["projection_sha256"],
            contract.store_port_projection_sha256_v1(store),
        )
        self.assertEqual(
            provider["transaction_store_projection_sha256"],
            store["projection_sha256"],
        )

    def test_default_off_fails_closed_without_calls(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(values, enabled=False)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROVIDER_STORE_ADAPTER_BINDING_DEFAULT_OFF"]
        )
        self.assertEqual(
            values["store_double"].counters(),
            {"apply_call_count": 0, "recovery_call_count": 0},
        )

    def test_wrong_scope_fails_closed(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(values, scope="EXPLICIT_RUNTIME")

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["PROVIDER_STORE_ADAPTER_BINDING_OFFLINE_SCOPE_REQUIRED"],
        )

    def test_missing_exact_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(values, provider_pin="")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EXACT_SYNTHETIC_BINDING_PINS_REQUIRED"])

    def test_wrong_exact_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(values, adapter_pin=_sha256_text("wrong-adapter-pin"))

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_BINDING_PIN_MISMATCH"])

    def test_wrong_composition_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(
            values,
            composition_pin=_sha256_text("wrong-composition-attestation"),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_BINDING_PIN_MISMATCH"])

    def test_provider_production_claim_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        provider = copy.deepcopy(values["provider_projection"])
        provider["production_ready"] = True
        _rehash_provider(provider)
        result = self._bind(values, provider=provider)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_PROVIDER_PROJECTION_INVALID"])

    def test_provider_real_component_claim_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        provider = copy.deepcopy(values["provider_projection"])
        provider["real_component_referenced"] = True
        _rehash_provider(provider)
        result = self._bind(values, provider=provider)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_PROVIDER_PROJECTION_INVALID"])

    def test_store_unverified_durability_cannot_be_promoted(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        store = copy.deepcopy(values["store_projection"])
        store["durability_verified"] = True
        _rehash_store(store)
        result = self._bind(values, store=store)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_PROJECTION_INVALID"])

    def test_store_schema_version_mismatch_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        store = copy.deepcopy(values["store_projection"])
        store["result_schema_version"] = "WRONG_RESULT_SCHEMA"
        _rehash_store(store)
        result = self._bind(values, store=store)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_PROJECTION_INVALID"])

    def test_source_contract_version_drift_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        cases = (
            ("provider", "source_provider_version"),
            ("store", "source_store_version"),
        )
        for target, field_name in cases:
            with self.subTest(target=target):
                provider = copy.deepcopy(values["provider_projection"])
                store = copy.deepcopy(values["store_projection"])
                if target == "provider":
                    provider[field_name] = "DRIFTED-PROVIDER-VERSION"
                    _rehash_provider(provider)
                    expected_reason = "SYNTHETIC_PROVIDER_PROJECTION_INVALID"
                else:
                    store[field_name] = "DRIFTED-STORE-VERSION"
                    _rehash_store(store)
                    expected_reason = "SYNTHETIC_STORE_PROJECTION_INVALID"
                result = self._bind(values, provider=provider, store=store)
                self.assertFalse(result["ok"])
                self.assertEqual(result["reasons"], [expected_reason])

    def test_adapter_production_authority_claim_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        adapter = copy.deepcopy(values["adapter_snapshot"])
        adapter["production_authority"] = True
        _rehash_adapter(adapter)
        result = self._bind(values, adapter=adapter)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_ADAPTER_SNAPSHOT_INVALID"])

    def test_adapter_snapshot_hash_tamper_is_rejected(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        adapter = copy.deepcopy(values["adapter_snapshot"])
        adapter["backend_instance_sha256"] = _sha256_text("tampered-backend")
        result = self._bind(values, adapter=adapter)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_ADAPTER_SNAPSHOT_INVALID"])

    def test_provider_store_path_mismatch_fails_cross_binding(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        provider = copy.deepcopy(values["provider_projection"])
        provider["registry_path_binding_sha256"] = _sha256_text("other-path")
        _rehash_provider(provider)
        result = self._bind(values, provider=provider)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROVIDER_STORE_ADAPTER_CROSS_BINDING_INVALID"]
        )

    def test_provider_store_projection_hash_mismatch_fails_cross_binding(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        provider = copy.deepcopy(values["provider_projection"])
        provider["transaction_store_projection_sha256"] = _sha256_text(
            "other-store-projection"
        )
        _rehash_provider(provider)
        result = self._bind(values, provider=provider)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROVIDER_STORE_ADAPTER_CROSS_BINDING_INVALID"]
        )

    def test_store_adapter_backend_mismatch_fails_cross_binding(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        store = copy.deepcopy(values["store_projection"])
        provider = copy.deepcopy(values["provider_projection"])
        store["backend_instance_sha256"] = _sha256_text("other-backend-instance")
        _rehash_store(store)
        provider["transaction_store_projection_sha256"] = store[
            "projection_sha256"
        ]
        _rehash_provider(provider)
        result = self._bind(values, provider=provider, store=store)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROVIDER_STORE_ADAPTER_CROSS_BINDING_INVALID"]
        )

    def test_store_adapter_capability_mismatch_fails_cross_binding(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        store = copy.deepcopy(values["store_projection"])
        provider = copy.deepcopy(values["provider_projection"])
        other = _sha256_text("other-backend-capability")
        store["backend_capability_attestation_sha256"] = other
        _rehash_store(store)
        provider["backend_capability_attestation_sha256"] = other
        provider["transaction_store_projection_sha256"] = store[
            "projection_sha256"
        ]
        _rehash_provider(provider)
        result = self._bind(values, provider=provider, store=store)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROVIDER_STORE_ADAPTER_CROSS_BINDING_INVALID"]
        )

    def test_successful_binding_is_exact_hash_bound_and_protected_in_repr(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        result = self._bind(values)
        protected = result["protected_binding"]

        self.assertTrue(result["ok"])
        self.assertEqual(set(protected.binding), contract._BINDING_KEYS)
        self.assertEqual(
            protected.binding_sha256,
            contract.provider_store_adapter_binding_sha256_v1(protected.binding),
        )
        self.assertEqual(
            protected.binding["source_provider_version"],
            contract.EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1,
        )
        self.assertEqual(
            protected.binding["source_store_version"],
            contract.EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1,
        )
        self.assertEqual(protected.binding["storage_scope"], "EXPLICIT_PRODUCTION")
        self.assertTrue(
            contract.protected_provider_store_adapter_binding_valid_v1(protected)
        )
        self.assertEqual(
            repr(protected),
            "ProtectedProductionProviderStoreAdapterBindingV1(<protected>)",
        )
        self.assertNotIn(protected.backend_instance_sha256, repr(protected))

    def test_binding_tamper_invalidates_self_validation(self) -> None:
        values = harness.build_synthetic_provider_store_adapter_binding_context_v1()
        protected = self._bind(values)["protected_binding"]
        protected.binding["runtime_integrated"] = True

        self.assertFalse(
            contract.protected_provider_store_adapter_binding_valid_v1(protected)
        )

    def test_contract_has_no_production_component_import_or_call_surface(self) -> None:
        source_path = Path(contract.__file__)
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_production_provider_v1",
            imported,
        )
        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1",
            imported,
        )
        self.assertNotIn("main", imported)
        self.assertTrue(
            {
                "apply_attested_transaction",
                "reconcile_attested_transaction",
                "load_exact_raw_registry",
                "invoke",
            }.isdisjoint(called_attributes)
        )


if __name__ == "__main__":
    unittest.main()
