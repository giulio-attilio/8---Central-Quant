from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as harness


class ProtectedRequestHandoffHarnessV2Tests(unittest.TestCase):
    def test_harness_materializes_only_synthetic_cas_witness(self) -> None:
        result = harness.run_protected_request_handoff_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 14)
        self.assertEqual(result["passed_count"], 14)
        self.assertEqual(result["synthetic_lease_liveness_validation_count"], 1)
        self.assertTrue(result["cas_witness_materialized"])
        self.assertTrue(
            harness.protected_request_handoff_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedRequestHandoffHarnessEvidenceV2(<protected>)",
        )
        for key in (
            "executable_request_materialized", "request_binding_materialized",
            "authorization_consumed", "provider_called", "store_called",
            "backend_called", "writer_called", "lock_acquired_by_harness",
            "filesystem_accessed_by_handoff", "real_registry_accessed",
            "network_accessed", "broker_called", "write_executed",
            "production_authority", "runtime_integrated", "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_witness_contains_no_candidate_bytes_or_executable_request(self) -> None:
        result = harness.run_protected_request_handoff_harness_v2()
        witness = result["protected_cas_witness"].witness

        self.assertNotIn("candidate_raw_document_utf8", witness)
        self.assertNotIn("request_binding_sha256", witness)
        self.assertNotIn("request_version", witness)
        self.assertFalse(result["protected_plan"].plan["request_materialized"])

    def test_resealed_evidence_authority_escalation_is_rejected(self) -> None:
        result = harness.run_protected_request_handoff_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["backend_called"] = True
        evidence["evidence_sha256"] = (
            harness.protected_request_handoff_harness_evidence_sha256_v2(evidence)
        )
        tampered = harness.ProtectedRequestHandoffHarnessEvidenceV2(
            handoff_plan=protected.handoff_plan,
            cas_witness=protected.cas_witness,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_request_handoff_harness_evidence_valid_v2(tampered)
        )

    def test_expired_witness_build_fails_closed(self) -> None:
        with materialization_harness.held_protected_dto_materialization_fixture_v2() as fixture:
            materialization = materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                fixture
            )
            protected_intent = materialization["protected_intent"]

            with self.assertRaisesRegex(ValueError, "CAS_WITNESS_DEADLINE_EXPIRED"):
                harness.build_synthetic_target_cas_witness_offline_v2(
                    protected_intent,
                    fixture["bridge_plan"],
                    fixture["compatibility_bundle"],
                    observed_at_epoch=protected_intent.intent["deadline_binding"][
                        "effective_deadline_epoch"
                    ],
                )


if __name__ == "__main__":
    unittest.main()
