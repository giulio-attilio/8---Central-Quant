from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_execution_harness_v2 as harness


class ProtectedHeldLeasePortAdapterExecutionHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_in_memory_execution_checks(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_execution_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 19)
        self.assertEqual(result["passed_count"], 19)
        self.assertEqual(result["backend_call_count"], 1)
        self.assertTrue(
            harness.protected_held_lease_port_adapter_execution_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2(<protected>)",
        )

    def test_evidence_resealed_call_count_tamper_is_rejected(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_execution_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["backend_call_count"] = 2
        evidence["evidence_sha256"] = (
            harness.protected_held_lease_port_adapter_execution_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2(
            protected_result=protected.protected_result,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_held_lease_port_adapter_execution_harness_evidence_valid_v2(
                tampered
            )
        )

    def test_all_named_fail_closed_scenarios_passed(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_execution_harness_v2()
        checks = result["protected_evidence"].evidence["checks"]

        self.assertEqual([item["name"] for item in checks], list(harness._CHECK_NAMES))
        self.assertTrue(all(item["passed"] for item in checks))


if __name__ == "__main__":
    unittest.main()
