from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as handoff_harness


class ProtectedRequestHandoffContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_context = (
            materialization_harness.held_protected_dto_materialization_fixture_v2()
        )
        self.fixture = self.fixture_context.__enter__()
        self.addCleanup(self.fixture_context.__exit__, None, None, None)
        materialization = (
            materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                self.fixture
            )
        )
        if materialization.get("ok") is not True:
            raise AssertionError(materialization)
        self.intent = materialization["protected_intent"]

    def planner(self, expected_sha256: str | None = None):
        return contract.DormantProtectedRequestHandoffContractV2(
            contract.DormantProtectedRequestHandoffConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2,
                expected_materialization_intent_sha256=(
                    expected_sha256 or self.intent.intent_sha256
                ),
            )
        )

    def plan(self):
        return self.planner().plan_offline(
            self.intent,
            self.fixture["bridge_plan"],
            self.fixture["compatibility_bundle"],
        )

    def cas_witness(self):
        return handoff_harness.build_synthetic_target_cas_witness_offline_v2(
            self.intent,
            self.fixture["bridge_plan"],
            self.fixture["compatibility_bundle"],
            observed_at_epoch=self.fixture["now_epoch"],
        )

    def test_plans_handoff_without_materializing_request_or_calling_port(self) -> None:
        result = self.plan()

        self.assertTrue(result["ok"], result)
        protected = result["protected_plan"]
        self.assertTrue(contract.protected_request_handoff_plan_valid_v2(protected))
        self.assertEqual(repr(protected), "ProtectedRequestHandoffPlanV2(<protected>)")
        self.assertEqual(
            result["expected_transaction_sha256"],
            contract.canonical_transaction_sha256_v2(
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
            ),
        )
        self.assertEqual(
            result["expected_request_sha256"],
            contract.canonical_request_sha256_v2(
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
            ),
        )
        for key in (
            "cas_witness_materialized", "request_materialized",
            "request_binding_materialized", "lease_validated_live",
            "provider_called", "store_called", "backend_called", "writer_called",
            "lock_acquired", "filesystem_accessed", "real_registry_accessed",
            "network_accessed", "broker_called", "write_executed",
            "production_authority", "runtime_integrated", "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_does_not_inspect_inputs(self) -> None:
        result = contract.DormantProtectedRequestHandoffContractV2().plan_offline(
            None, None, None
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PROTECTED_REQUEST_HANDOFF_V2_DEFAULT_OFF")

    def test_materialization_intent_is_hash_pinned(self) -> None:
        result = self.planner(backend_v2.stable_sha256_v2("wrong")).plan_offline(
            self.intent,
            self.fixture["bridge_plan"],
            self.fixture["compatibility_bundle"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PROTECTED_MATERIALIZATION_INTENT_PIN_MISMATCH"
        )

    def test_typed_cas_witness_requires_same_object_instances(self) -> None:
        witness = self.cas_witness()

        self.assertTrue(
            contract.protected_target_cas_witness_valid_v2(
                witness,
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
            )
        )
        self.assertEqual(repr(witness), "ProtectedTargetCasWitnessV2(<protected>)")
        substituted = contract.ProtectedTargetCasWitnessV2(
            maintenance_permit=copy.copy(witness.maintenance_permit),
            live_lease_token=witness.live_lease_token,
            lease_witness=witness.lease_witness,
            witness=witness.witness,
            witness_sha256=witness.witness_sha256,
        )
        self.assertFalse(
            contract.protected_target_cas_witness_valid_v2(
                substituted,
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
            )
        )

    def test_stale_cas_generation_is_rejected(self) -> None:
        protected = self.cas_witness()
        witness = copy.deepcopy(dict(protected.witness))
        witness["observed_generation"] += 1
        witness["witness_sha256"] = contract.target_cas_witness_sha256_v2(witness)
        stale = contract.ProtectedTargetCasWitnessV2(
            maintenance_permit=protected.maintenance_permit,
            live_lease_token=protected.live_lease_token,
            lease_witness=protected.lease_witness,
            witness=witness,
            witness_sha256=witness["witness_sha256"],
        )

        self.assertFalse(
            contract.protected_target_cas_witness_valid_v2(
                stale,
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
            )
        )

    def test_resealed_lock_reacquisition_escalation_invalidates_plan(self) -> None:
        protected = self.plan()["protected_plan"]
        plan = copy.deepcopy(dict(protected.plan))
        port = plan["held_lease_backend_port_contract"]
        port["backend_reacquire_allowed"] = True
        port["contract_sha256"] = (
            contract.protected_request_handoff_contract_sha256_v2(port)
        )
        plan["plan_sha256"] = contract.protected_request_handoff_plan_sha256_v2(plan)
        tampered = contract.ProtectedRequestHandoffPlanV2(
            materialization_intent=protected.materialization_intent,
            bridge_plan=protected.bridge_plan,
            compatibility_bundle=protected.compatibility_bundle,
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )

        self.assertFalse(contract.protected_request_handoff_plan_valid_v2(tampered))

    def test_port_contract_forbids_legacy_self_locking_backend_method(self) -> None:
        port = self.plan()["protected_plan"].plan[
            "held_lease_backend_port_contract"
        ]

        self.assertEqual(
            port["required_method"], "apply_under_held_maintenance_lease"
        )
        self.assertEqual(
            port["legacy_self_locking_method_forbidden"],
            "apply_attested_transaction_offline",
        )
        self.assertTrue(port["lock_already_held_required"])
        self.assertEqual(port["maximum_acquisition_count"], 1)
        self.assertFalse(port["backend_reacquire_allowed"])
        self.assertFalse(port["backend_call_allowed"])


if __name__ == "__main__":
    unittest.main()
