from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_harness_v2 as harness


class ProtectedRequestMaterializerHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_independent_offline_checks(self) -> None:
        result = harness.run_protected_request_materializer_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 16)
        self.assertEqual(result["passed_count"], 16)
        self.assertTrue(result["request_materialized"])
        self.assertTrue(result["request_binding_materialized"])
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedRequestMaterializerHarnessEvidenceV2(<protected>)",
        )
        self.assertTrue(
            harness.protected_request_materializer_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )

    def test_harness_exposes_no_bare_request_or_operational_side_effect(self) -> None:
        result = harness.run_protected_request_materializer_harness_v2()

        self.assertTrue(result["ok"], result)
        for key in (
            "bare_request_exposed",
            "authorization_consumed",
            "provider_called",
            "store_called",
            "backend_called",
            "writer_called",
            "lock_acquired",
            "filesystem_accessed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "production_authority",
            "runtime_integrated",
            "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)
        self.assertTrue(result["no_order_sent"])

    def test_evidence_tamper_fails_closed_even_when_resealed(self) -> None:
        result = harness.run_protected_request_materializer_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["canonicalization_count"] = 2
        evidence["evidence_sha256"] = (
            harness.protected_request_materializer_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedRequestMaterializerHarnessEvidenceV2(
            protected_request=protected.protected_request,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_request_materializer_harness_evidence_valid_v2(
                tampered
            )
        )

    def test_check_names_are_stable_and_all_passed(self) -> None:
        result = harness.run_protected_request_materializer_harness_v2()
        evidence = result["protected_evidence"].evidence

        self.assertEqual(
            [item["name"] for item in evidence["checks"]],
            list(harness._CHECK_NAMES),
        )
        self.assertTrue(all(item["passed"] for item in evidence["checks"]))


if __name__ == "__main__":
    unittest.main()
