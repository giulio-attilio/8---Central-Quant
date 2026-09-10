from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_harness_v2 as harness


class ProtectedReconciliationRestartSafeResolutionCompositionHarnessV2Tests(
    unittest.TestCase
):
    def test_harness_passes_every_offline_check(self) -> None:
        result = harness.run_protected_reconciliation_restart_safe_resolution_composition_harness_v2()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 13)
        self.assertEqual(result["passed_count"], 13)
        self.assertTrue(result["no_order_sent"])
        self.assertTrue(
            harness.protected_reconciliation_restart_safe_resolution_composition_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )

    def test_protected_evidence_hides_bound_objects(self) -> None:
        result = harness.run_protected_reconciliation_restart_safe_resolution_composition_harness_v2()
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2(<protected>)",
        )

    def test_resealed_operational_execution_claim_is_rejected(self) -> None:
        result = harness.run_protected_reconciliation_restart_safe_resolution_composition_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["operational_execution"] = True
        evidence["evidence_sha256"] = (
            harness.protected_reconciliation_restart_safe_resolution_composition_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2(
            protected_barrier=protected.protected_barrier,
            protected_receipt=protected.protected_receipt,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )
        self.assertFalse(
            harness.protected_reconciliation_restart_safe_resolution_composition_harness_evidence_valid_v2(
                tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
