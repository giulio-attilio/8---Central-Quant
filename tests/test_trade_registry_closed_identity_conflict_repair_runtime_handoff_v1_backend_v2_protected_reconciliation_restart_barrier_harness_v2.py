from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_harness_v2 as harness


class ProtectedReconciliationRestartBarrierHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_offline_checks(self) -> None:
        result = harness.run_protected_reconciliation_restart_barrier_harness_v2()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 11)
        self.assertEqual(result["passed_count"], 11)
        self.assertFalse(result["resolution_executed"])
        self.assertTrue(result["no_order_sent"])
        self.assertTrue(
            harness.protected_reconciliation_restart_barrier_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )

    def test_harness_evidence_rejects_resealed_execution_claim(self) -> None:
        result = harness.run_protected_reconciliation_restart_barrier_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["resolution_executed"] = True
        evidence["evidence_sha256"] = (
            harness.protected_reconciliation_restart_barrier_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedReconciliationRestartBarrierHarnessEvidenceV2(
            protected_barrier=protected.protected_barrier,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )
        self.assertFalse(
            harness.protected_reconciliation_restart_barrier_harness_evidence_valid_v2(
                tampered
            )
        )

    def test_harness_evidence_is_protected(self) -> None:
        result = harness.run_protected_reconciliation_restart_barrier_harness_v2()
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedReconciliationRestartBarrierHarnessEvidenceV2(<protected>)",
        )


if __name__ == "__main__":
    unittest.main()
