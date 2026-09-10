from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as harness


class ProtectedDtoMaterializationHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_with_all_executable_surfaces_dormant(self) -> None:
        result = harness.run_protected_dto_materialization_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 15)
        self.assertEqual(result["passed_count"], 15)
        self.assertTrue(
            harness.protected_dto_materialization_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedDtoMaterializationHarnessEvidenceV2(<protected>)",
        )
        for key in (
            "authorization_consumed", "lease_validated_live",
            "executable_request_materialized", "executable_recovery_request_materialized",
            "provider_called", "store_called", "backend_called", "writer_called",
            "lock_acquired", "filesystem_accessed_by_materializer",
            "real_registry_accessed", "network_accessed", "broker_called",
            "write_executed", "production_authority", "runtime_integrated",
            "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_resealed_evidence_escalation_is_rejected(self) -> None:
        result = harness.run_protected_dto_materialization_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["backend_called"] = True
        evidence["evidence_sha256"] = (
            harness.dto_materialization_harness_evidence_sha256_v2(evidence)
        )
        tampered = harness.ProtectedDtoMaterializationHarnessEvidenceV2(
            protected_intent=protected.protected_intent,
            bridge_plan=protected.bridge_plan,
            compatibility_bundle=protected.compatibility_bundle,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_dto_materialization_harness_evidence_valid_v2(tampered)
        )

    def test_invalid_clock_fails_closed(self) -> None:
        result = harness.run_protected_dto_materialization_harness_v2(
            now_epoch="invalid"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PROTECTED_DTO_MATERIALIZATION_HARNESS_EXCEPTION"
        )


if __name__ == "__main__":
    unittest.main()
