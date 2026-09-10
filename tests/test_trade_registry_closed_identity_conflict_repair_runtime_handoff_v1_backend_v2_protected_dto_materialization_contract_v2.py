from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as harness


class ProtectedDtoMaterializationContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture_context = harness.held_protected_dto_materialization_fixture_v2()
        self.fixture = self.fixture_context.__enter__()
        self.addCleanup(self.fixture_context.__exit__, None, None, None)

    def _bind(self):
        result = harness.bind_protected_dto_materialization_fixture_offline_v2(
            self.fixture
        )
        return result, self.fixture["bridge_plan"], self.fixture["compatibility_bundle"]

    def _tampered(self, protected, **changes):
        values = {
            "source_envelope": protected.source_envelope,
            "authorization_consumption_receipt": protected.authorization_consumption_receipt,
            "maintenance_permit": protected.maintenance_permit,
            "live_lease_token": protected.live_lease_token,
            "lease_witness": protected.lease_witness,
            "target_snapshot": protected.target_snapshot,
            "intent": protected.intent,
            "intent_sha256": protected.intent_sha256,
        }
        values.update(changes)
        return contract.ProtectedBackendV2DtoMaterializationIntent(**values)

    def test_binds_protected_intent_without_materializing_or_calling(self) -> None:
        result, bridge_plan, compatibility_bundle = self._bind()

        self.assertTrue(result["ok"], result)
        protected = result["protected_intent"]
        self.assertTrue(
            contract.protected_backend_v2_dto_materialization_intent_valid(
                protected, bridge_plan, compatibility_bundle
            )
        )
        self.assertIs(protected.maintenance_permit, self.fixture["maintenance_permit"])
        self.assertIs(protected.live_lease_token, self.fixture["live_lease_token"])
        self.assertIs(protected.lease_witness, self.fixture["lease_witness"])
        self.assertEqual(
            repr(protected), "ProtectedBackendV2DtoMaterializationIntent(<protected>)"
        )
        self.assertTrue(result["authorization_consumed_upstream"])
        self.assertTrue(result["lease_instance_bound"])
        for key in (
            "authorization_consumed", "lease_validated_live", "request_materialized",
            "recovery_request_materialized", "provider_called", "store_called",
            "backend_called", "writer_called", "lock_acquired", "filesystem_accessed",
            "real_registry_accessed", "network_accessed", "broker_called",
            "write_executed", "production_authority", "runtime_integrated",
            "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_does_not_inspect_inputs(self) -> None:
        result = contract.DormantBackendV2DtoMaterializationContract().bind_intent_offline(
            bridge_plan=None,
            compatibility_bundle=None,
            source_envelope=None,
            authorization_consumption_receipt=None,
            maintenance_permit=None,
            live_lease_token=None,
            lease_witness=None,
            target_snapshot=None,
            target_backend_capability_attestation_sha256="",
            generation_resolver_evidence_sha256="",
            boundary_deadline_epoch=0,
            now_epoch=0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "BACKEND_V2_DTO_MATERIALIZATION_DEFAULT_OFF")

    def test_tampered_single_use_receipt_fails_closed(self) -> None:
        result, bridge_plan, compatibility_bundle = self._bind()
        protected = result["protected_intent"]
        receipt = copy.deepcopy(dict(protected.authorization_consumption_receipt))
        receipt["consumption_count"] = 2

        self.assertFalse(
            contract.protected_backend_v2_dto_materialization_intent_valid(
                self._tampered(
                    protected, authorization_consumption_receipt=receipt
                ),
                bridge_plan,
                compatibility_bundle,
            )
        )

    def test_substituting_permit_instance_invalidates_intent(self) -> None:
        result, bridge_plan, compatibility_bundle = self._bind()
        protected = result["protected_intent"]

        self.assertFalse(
            contract.protected_backend_v2_dto_materialization_intent_valid(
                self._tampered(
                    protected, maintenance_permit=copy.copy(protected.maintenance_permit)
                ),
                bridge_plan,
                compatibility_bundle,
            )
        )

    def test_resealed_lock_reacquisition_is_rejected(self) -> None:
        result, bridge_plan, compatibility_bundle = self._bind()
        protected = result["protected_intent"]
        intent = copy.deepcopy(dict(protected.intent))
        lock = intent["lock_handoff_policy"]
        lock["backend_reacquire_allowed"] = True
        lock["binding_sha256"] = contract.materialization_binding_sha256_v2(lock)
        intent["intent_sha256"] = contract.materialization_intent_sha256_v2(intent)

        self.assertFalse(
            contract.protected_backend_v2_dto_materialization_intent_valid(
                self._tampered(
                    protected, intent=intent, intent_sha256=intent["intent_sha256"]
                ),
                bridge_plan,
                compatibility_bundle,
            )
        )

    def test_target_must_differ_from_reference_backend(self) -> None:
        result, bridge_plan, compatibility_bundle = self._bind()
        protected = result["protected_intent"]
        snapshot = copy.deepcopy(dict(protected.target_snapshot))
        snapshot["backend_instance_sha256"] = bridge_plan.reference_backend_instance_sha256
        snapshot["snapshot_sha256"] = backend_v2.stable_sha256_v2(
            {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
        )

        self.assertFalse(
            contract.protected_backend_v2_dto_materialization_intent_valid(
                self._tampered(protected, target_snapshot=snapshot),
                bridge_plan,
                compatibility_bundle,
            )
        )


if __name__ == "__main__":
    unittest.main()
