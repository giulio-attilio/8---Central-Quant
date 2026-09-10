from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2 as provider_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2 as compatibility_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


def _compatibility_bundle():
    provider_values = provider_harness.build_provider_store_projection_fixture_v2()
    provider_bundle = provider_values["projection"]["protected_bundle"]
    compatibility = compatibility_harness.run_writer_coordination_compatibility_harness_v2(
        provider_bundle
    )
    if compatibility.get("ok") is not True:
        raise AssertionError("compatibility harness failed")
    return compatibility["protected_bundle"]


class HandoffV1BackendV2SchemaBridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compatibility_bundle = _compatibility_bundle()

    def bridge(self, expected_sha: str | None = None):
        return contract.DormantHandoffV1BackendV2SchemaBridge(
            contract.HandoffV1BackendV2SchemaBridgeConfig(
                enabled=True,
                scope_attestation=contract.OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION,
                expected_compatibility_bundle_sha256=(
                    expected_sha or self.compatibility_bundle.bundle_sha256
                ),
            )
        )

    def test_builds_protected_schema_plan_without_translation(self) -> None:
        result = self.bridge().plan_offline(self.compatibility_bundle)

        self.assertTrue(result["ok"])
        self.assertTrue(result["schema_bridge_verified"])
        self.assertEqual(result["apply_mapping_count"], 21)
        self.assertEqual(result["terminal_mapping_count"], 21)
        self.assertEqual(result["recovery_mapping_count"], 24)
        self.assertEqual(result["deferred_runtime_evidence_count"], 8)
        protected = result["protected_plan"]
        self.assertTrue(contract.protected_schema_bridge_plan_valid(protected))
        self.assertEqual(
            repr(protected),
            "ProtectedHandoffV1BackendV2SchemaBridgePlan(<protected>)",
        )
        for name in (
            "translate", "build_request", "invoke", "apply", "reconcile",
            "consume", "validate_live", "acquire", "activate",
        ):
            self.assertFalse(hasattr(protected, name), name)
        for key in (
            "translation_executed", "provider_called", "store_called",
            "backend_called", "authorization_consumed", "lease_validated_live",
            "lock_acquired", "filesystem_accessed", "real_registry_accessed",
            "network_accessed", "broker_called", "write_executed",
            "production_authority", "runtime_integrated", "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_does_not_inspect_input(self) -> None:
        bridge = contract.DormantHandoffV1BackendV2SchemaBridge()

        result = bridge.plan_offline(None)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_DEFAULT_OFF"
        )

    def test_upstream_bundle_is_hash_pinned(self) -> None:
        result = self.bridge(
            backend_v2.stable_sha256_v2("wrong-upstream")
        ).plan_offline(self.compatibility_bundle)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "WRITER_COORDINATION_COMPATIBILITY_BUNDLE_V2_PIN_MISMATCH",
        )

    def test_schema_versions_are_bound_to_both_contracts(self) -> None:
        plan = self.bridge().plan_offline(self.compatibility_bundle)[
            "protected_plan"
        ].plan
        schema = plan["schema_binding"]

        self.assertEqual(
            schema["v1_apply_schema_version"],
            envelope_v1.PRODUCTION_REQUEST_VERSION_V1,
        )
        self.assertEqual(
            schema["v2_apply_schema_version"],
            backend_v2.TRANSACTION_REQUEST_VERSION_V2,
        )
        self.assertNotEqual(
            schema["v1_apply_schema_version"], schema["v2_apply_schema_version"]
        )

    def test_identity_policy_forbids_temporary_backend_reuse(self) -> None:
        plan = self.bridge().plan_offline(self.compatibility_bundle)[
            "protected_plan"
        ].plan
        identity = plan["identity_policy"]

        self.assertTrue(identity["production_backend_must_differ_from_reference"])
        self.assertTrue(identity["production_registry_path_must_be_rebound"])
        self.assertTrue(identity["temporary_identity_reuse_forbidden"])
        self.assertTrue(identity["production_capability_attestation_required"])

    def test_authorization_and_recovery_are_strictly_single_use(self) -> None:
        plan = self.bridge().plan_offline(self.compatibility_bundle)[
            "protected_plan"
        ].plan
        authorization = plan["authorization_policy"]
        permit = plan["permit_lease_policy"]

        self.assertEqual(authorization["apply_consumption_count"], 1)
        self.assertEqual(authorization["recovery_consumption_count"], 1)
        self.assertTrue(authorization["recovery_authorization_separate"])
        self.assertTrue(authorization["generic_hash_substitution_forbidden"])
        self.assertTrue(permit["same_permit_instance_required"])
        self.assertTrue(permit["current_time_liveness_revalidation_required"])
        self.assertTrue(permit["fresh_recovery_permit_required"])
        self.assertTrue(permit["recovery_epoch_must_differ"])

    def test_resealed_mapping_change_invalidates_protected_plan(self) -> None:
        protected = self.bridge().plan_offline(self.compatibility_bundle)[
            "protected_plan"
        ]
        plan = copy.deepcopy(dict(protected.plan))
        plan["apply_field_mapping"][0]["rule"] = "COPY_WITHOUT_VALIDATION"
        plan["plan_sha256"] = contract.bridge_plan_sha256(plan)
        tampered = contract.ProtectedHandoffV1BackendV2SchemaBridgePlan(
            source_compatibility_bundle_sha256=(
                protected.source_compatibility_bundle_sha256
            ),
            reference_backend_instance_sha256=(
                protected.reference_backend_instance_sha256
            ),
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )

        self.assertFalse(contract.protected_schema_bridge_plan_valid(tampered))

    def test_resealed_authority_escalation_invalidates_protected_plan(self) -> None:
        protected = self.bridge().plan_offline(self.compatibility_bundle)[
            "protected_plan"
        ]
        plan = copy.deepcopy(dict(protected.plan))
        plan["authorization_policy"]["production_authority"] = True
        policy = plan["authorization_policy"]
        policy["policy_sha256"] = contract.bridge_policy_sha256(policy)
        plan["plan_sha256"] = contract.bridge_plan_sha256(plan)
        tampered = contract.ProtectedHandoffV1BackendV2SchemaBridgePlan(
            source_compatibility_bundle_sha256=(
                protected.source_compatibility_bundle_sha256
            ),
            reference_backend_instance_sha256=(
                protected.reference_backend_instance_sha256
            ),
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )

        self.assertFalse(contract.protected_schema_bridge_plan_valid(tampered))


if __name__ == "__main__":
    unittest.main()
