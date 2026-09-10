from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as harness


class DurableReconciliationAuthorityHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_temporary_storage_checks(self) -> None:
        result = harness.run_durable_authority_harness_v2()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 20)
        self.assertEqual(result["passed_count"], 20)
        self.assertTrue(result["temporary_storage_removed"])
        self.assertTrue(result["no_order_sent"])
        self.assertTrue(
            harness.protected_durable_authority_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )

    def test_evidence_is_protected(self) -> None:
        result = harness.run_durable_authority_harness_v2()
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedDurableAuthorityHarnessEvidenceV2(<protected>)",
        )

    def test_resealed_evidence_cannot_claim_production_authority(self) -> None:
        result = harness.run_durable_authority_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["production_authority"] = True
        evidence["evidence_sha256"] = harness.durable_authority_harness_evidence_sha256_v2(
            evidence
        )
        tampered = harness.ProtectedDurableAuthorityHarnessEvidenceV2(
            issued_receipt=protected.issued_receipt,
            consumed_receipt=protected.consumed_receipt,
            recovered_receipt=protected.recovered_receipt,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )
        self.assertFalse(
            harness.protected_durable_authority_harness_evidence_valid_v2(tampered)
        )


if __name__ == "__main__":
    unittest.main()
