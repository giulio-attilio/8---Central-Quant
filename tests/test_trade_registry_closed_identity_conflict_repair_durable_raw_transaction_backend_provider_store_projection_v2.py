from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2 as harness


class ProviderStoreProjectionV2Tests(unittest.TestCase):
    def test_complete_harness_builds_dormant_cross_binding(self) -> None:
        result = harness.run_provider_store_projection_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["capability_count"], 9)
        self.assertTrue(result["immutable_manifest_verified"])
        self.assertTrue(result["cross_binding_verified"])
        self.assertTrue(result["no_call_surface"])
        self.assertTrue(result["no_order_sent"])
        for key in (
            "writer_coordination_bound", "invocation_adapter_bound",
            "durability_verified", "production_authority", "provider_called",
            "store_called", "backend_called_by_projection", "runtime_integrated",
            "activation_allowed", "live_allowed", "real_registry_accessed",
            "network_accessed", "broker_called",
        ):
            self.assertFalse(result[key], key)

    def test_projection_is_default_off_and_does_not_inspect_inputs(self) -> None:
        projector = contract.DormantProviderStoreProjectionV2()

        result = projector.project_offline(
            snapshot={}, capability_evidence=[], prepared_catalog={}
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PROVIDER_STORE_PROJECTION_V2_DEFAULT_OFF")
        self.assertIsNone(result["protected_bundle"])

    def test_capability_manifest_is_stable_across_backend_generation(self) -> None:
        values = harness.build_provider_store_projection_fixture_v2()
        first = values["manifest"]
        snapshot = copy.deepcopy(values["snapshot"])
        snapshot["generation"] += 1
        snapshot["snapshot_sha256"] = backend_contract.stable_sha256_v2(
            {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
        )
        evidence = copy.deepcopy(values["evidence"])
        for item in evidence:
            item["backend_snapshot_sha256"] = snapshot["snapshot_sha256"]
            item["evidence_sha256"] = backend_contract.stable_sha256_v2(
                {key: value for key, value in item.items() if key != "evidence_sha256"}
            )

        second = contract.build_immutable_capability_manifest_offline_v2(
            snapshot, evidence
        )

        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])

    def test_missing_capability_evidence_fails_closed(self) -> None:
        values = harness.build_provider_store_projection_fixture_v2()

        with self.assertRaisesRegex(
            ValueError, "COMPLETE_PHYSICAL_CAPABILITY_EVIDENCE_REQUIRED"
        ):
            contract.build_immutable_capability_manifest_offline_v2(
                values["snapshot"], values["evidence"][:-1]
            )

    def test_projection_requires_exact_snapshot_catalog_and_manifest_pins(self) -> None:
        values = harness.build_provider_store_projection_fixture_v2()
        projector = contract.DormantProviderStoreProjectionV2(
            contract.ProviderStoreProjectionConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2,
                expected_backend_snapshot_sha256=values["snapshot"]["snapshot_sha256"],
                expected_prepared_catalog_sha256=values["catalog"]["catalog_sha256"],
                expected_capability_manifest_sha256=backend_contract.stable_sha256_v2("wrong"),
            )
        )

        result = projector.project_offline(
            snapshot=values["snapshot"],
            capability_evidence=values["evidence"],
            prepared_catalog=values["catalog"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PROVIDER_STORE_PROJECTION_V2_PIN_MISMATCH")

    def test_resealed_authority_escalation_invalidates_protected_bundle(self) -> None:
        values = harness.build_provider_store_projection_fixture_v2()
        protected = values["projection"]["protected_bundle"]
        bundle = copy.deepcopy(dict(protected.bundle))
        bundle["provider_store_binding"]["production_authority"] = True
        binding = bundle["provider_store_binding"]
        binding["binding_sha256"] = contract.provider_store_binding_sha256_v2(binding)
        bundle["bundle_sha256"] = contract.provider_store_bundle_sha256_v2(bundle)
        tampered = contract.ProtectedProviderStoreProjectionBundleV2(
            backend_instance_sha256=protected.backend_instance_sha256,
            capability_manifest_sha256=protected.capability_manifest_sha256,
            store_instance_sha256=protected.store_instance_sha256,
            bundle=bundle,
            bundle_sha256=bundle["bundle_sha256"],
        )

        self.assertFalse(
            contract.protected_provider_store_projection_bundle_valid_v2(tampered)
        )


if __name__ == "__main__":
    unittest.main()
