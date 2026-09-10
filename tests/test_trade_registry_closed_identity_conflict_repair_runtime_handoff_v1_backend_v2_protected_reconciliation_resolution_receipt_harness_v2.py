from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as harness


class ProtectedReconciliationResolutionReceiptHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_offline_checks(self) -> None:
        result = harness.run_protected_reconciliation_resolution_receipt_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 20)
        self.assertEqual(result["passed_count"], 20)
        self.assertTrue(
            harness.protected_reconciliation_resolution_receipt_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedReconciliationResolutionReceiptHarnessEvidenceV2(<protected>)",
        )

    def test_harness_has_no_operational_side_effect(self) -> None:
        result = harness.run_protected_reconciliation_resolution_receipt_harness_v2()

        self.assertTrue(result["ok"], result)
        for key in (
            "backend_called", "provider_called", "store_called", "writer_called",
            "lock_acquired", "registry_write", "write_executed", "filesystem_accessed",
            "real_registry_accessed", "network_accessed", "broker_called",
            "production_authority", "runtime_integrated", "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)
        self.assertTrue(result["no_order_sent"])

    def test_resealed_harness_evidence_is_rejected(self) -> None:
        result = harness.run_protected_reconciliation_resolution_receipt_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["runtime_integrated"] = True
        evidence["evidence_sha256"] = (
            harness.protected_reconciliation_resolution_receipt_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedReconciliationResolutionReceiptHarnessEvidenceV2(
            protected_receipt=protected.protected_receipt,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_reconciliation_resolution_receipt_harness_evidence_valid_v2(
                tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
