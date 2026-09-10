from __future__ import annotations

import copy
import unittest
from unittest import mock

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as handoff_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2


class ProtectedRequestMaterializerV2Tests(unittest.TestCase):
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
        planner = handoff_v2.DormantProtectedRequestHandoffContractV2(
            handoff_v2.DormantProtectedRequestHandoffConfigV2(
                enabled=True,
                scope_attestation=(
                    handoff_v2.OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2
                ),
                expected_materialization_intent_sha256=self.intent.intent_sha256,
            )
        )
        planned = planner.plan_offline(
            self.intent,
            self.fixture["bridge_plan"],
            self.fixture["compatibility_bundle"],
        )
        if planned.get("ok") is not True:
            raise AssertionError(planned)
        self.plan = planned["protected_plan"]
        self.cas_witness = (
            handoff_harness.build_synthetic_target_cas_witness_offline_v2(
                self.intent,
                self.fixture["bridge_plan"],
                self.fixture["compatibility_bundle"],
                observed_at_epoch=self.fixture["now_epoch"],
            )
        )

    def materializer(self, *, maximum_age: int = 5):
        return materializer_v2.OfflineProtectedRequestMaterializerV2(
            materializer_v2.OfflineProtectedRequestMaterializerConfigV2(
                enabled=True,
                scope_attestation=(
                    materializer_v2.OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2
                ),
                expected_handoff_plan_sha256=self.plan.plan_sha256,
                maximum_cas_witness_age_seconds=maximum_age,
            )
        )

    def materialize(self):
        return self.materializer().materialize_offline(
            self.plan,
            self.cas_witness,
            now_epoch=self.fixture["now_epoch"],
        )

    def reseal_request(self, protected, request):
        request["request_binding_sha256"] = backend_v2.stable_sha256_v2(
            {
                key: item
                for key, item in request.items()
                if key != "request_binding_sha256"
            }
        )
        envelope = copy.deepcopy(dict(protected.envelope))
        envelope["request_binding_sha256"] = request["request_binding_sha256"]
        envelope["request_sha256"] = request["request_sha256"]
        envelope["transaction_sha256"] = request["transaction_sha256"]
        envelope["envelope_sha256"] = (
            materializer_v2.protected_materialized_request_envelope_sha256_v2(
                envelope
            )
        )
        return materializer_v2.ProtectedMaterializedTransactionRequestV2(
            handoff_plan=protected.handoff_plan,
            cas_witness=protected.cas_witness,
            authorization_consumption_receipt=(
                protected.authorization_consumption_receipt
            ),
            maintenance_permit=protected.maintenance_permit,
            live_lease_token=protected.live_lease_token,
            lease_witness=protected.lease_witness,
            request=request,
            envelope=envelope,
            envelope_sha256=envelope["envelope_sha256"],
        )

    def test_materializes_one_protected_request_without_calling_backend(self) -> None:
        result = self.materialize()

        self.assertTrue(result["ok"], result)
        protected = result["protected_request"]
        self.assertTrue(
            materializer_v2.protected_materialized_transaction_request_valid_v2(
                protected
            )
        )
        self.assertEqual(
            repr(protected),
            "ProtectedMaterializedTransactionRequestV2(<protected>)",
        )
        self.assertIs(protected.maintenance_permit, self.intent.maintenance_permit)
        self.assertIs(protected.live_lease_token, self.intent.live_lease_token)
        self.assertIs(protected.lease_witness, self.intent.lease_witness)
        self.assertEqual(result["canonicalization_count"], 1)
        self.assertEqual(result["lease_revalidation_count"], 1)
        self.assertTrue(result["request_materialized"])
        self.assertTrue(result["request_binding_materialized"])
        for key in (
            "bare_request_exposed", "authorization_consumed", "provider_called",
            "store_called", "backend_called", "writer_called", "lock_acquired",
            "filesystem_accessed", "real_registry_accessed", "network_accessed",
            "broker_called", "write_executed", "production_authority",
            "runtime_integrated", "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_request_is_exact_v2_and_bound_to_plan_and_cas(self) -> None:
        protected = self.materialize()["protected_request"]
        request = protected.request
        intent = self.intent.intent
        identity = self.plan.plan["identity_policy"]

        self.assertEqual(set(request), backend_v2._TRANSACTION_REQUEST_KEYS)
        self.assertTrue(
            backend_v2.transaction_request_valid_v2(
                request, self.intent.target_snapshot
            )
        )
        self.assertEqual(request["request_sha256"], identity["expected_request_sha256"])
        self.assertEqual(
            request["transaction_sha256"], identity["expected_transaction_sha256"]
        )
        self.assertEqual(
            request["expected_generation"],
            self.cas_witness.witness["observed_generation"],
        )
        self.assertEqual(
            request["expected_raw_document_sha256"],
            self.cas_witness.witness["observed_raw_document_sha256"],
        )
        self.assertEqual(
            backend_v2.raw_utf8_sha256_v2(request["candidate_raw_document_utf8"]),
            intent["candidate_binding"]["candidate_raw_document_sha256"],
        )

    def test_materialization_canonicalizes_candidate_exactly_once(self) -> None:
        with mock.patch.object(
            materializer_v2,
            "_canonical_candidate",
            wraps=materializer_v2._canonical_candidate,
        ) as canonicalize:
            result = self.materialize()

        self.assertTrue(result["ok"], result)
        self.assertEqual(canonicalize.call_count, 1)
        self.assertEqual(result["canonicalization_count"], 1)

    def test_default_off_does_not_inspect_inputs(self) -> None:
        result = materializer_v2.OfflineProtectedRequestMaterializerV2().materialize_offline(
            None, None, now_epoch=0
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PROTECTED_REQUEST_MATERIALIZER_V2_DEFAULT_OFF"
        )

    def test_stale_cas_witness_fails_closed(self) -> None:
        result = self.materializer(maximum_age=5).materialize_offline(
            self.plan,
            self.cas_witness,
            now_epoch=self.fixture["now_epoch"] + 6,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PROTECTED_TARGET_CAS_WITNESS_STALE")
        self.assertFalse(result["request_materialized"])
        self.assertFalse(result["backend_called"])

    def test_copied_permit_invalidates_protected_wrapper(self) -> None:
        protected = self.materialize()["protected_request"]
        substituted = materializer_v2.ProtectedMaterializedTransactionRequestV2(
            handoff_plan=protected.handoff_plan,
            cas_witness=protected.cas_witness,
            authorization_consumption_receipt=(
                protected.authorization_consumption_receipt
            ),
            maintenance_permit=copy.copy(protected.maintenance_permit),
            live_lease_token=protected.live_lease_token,
            lease_witness=protected.lease_witness,
            request=protected.request,
            envelope=protected.envelope,
            envelope_sha256=protected.envelope_sha256,
        )

        self.assertFalse(
            materializer_v2.protected_materialized_transaction_request_valid_v2(
                substituted
            )
        )

    def test_resealed_generation_tamper_is_rejected_by_cas_binding(self) -> None:
        protected = self.materialize()["protected_request"]
        request = copy.deepcopy(dict(protected.request))
        request["expected_generation"] += 1
        tampered = self.reseal_request(protected, request)

        self.assertFalse(
            materializer_v2.protected_materialized_transaction_request_valid_v2(
                tampered
            )
        )

    def test_resealed_arbitrary_request_identity_is_rejected(self) -> None:
        protected = self.materialize()["protected_request"]
        request = copy.deepcopy(dict(protected.request))
        request["request_sha256"] = backend_v2.stable_sha256_v2("arbitrary")
        tampered = self.reseal_request(protected, request)

        self.assertFalse(
            materializer_v2.protected_materialized_transaction_request_valid_v2(
                tampered
            )
        )

    def test_wrapper_exposes_no_execution_method(self) -> None:
        protected = self.materialize()["protected_request"]

        for method_name in (
            "apply_under_held_maintenance_lease",
            "apply_attested_transaction_offline",
            "invoke",
            "activate",
        ):
            self.assertFalse(hasattr(protected, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
