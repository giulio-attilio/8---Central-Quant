from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2 as harness


class DurableReconciliationAuthorityContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_durable_authority_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.evidence = result["protected_evidence"]

    def test_all_reference_receipts_are_valid_and_protected(self) -> None:
        for receipt in (
            self.evidence.issued_receipt,
            self.evidence.consumed_receipt,
            self.evidence.recovered_receipt,
        ):
            self.assertTrue(
                contract.protected_durable_reconciliation_authority_receipt_valid_v2(
                    receipt
                )
            )
            self.assertEqual(
                repr(receipt),
                "ProtectedDurableReconciliationAuthorityReceiptV2(<protected>)",
            )

    def test_consumed_receipt_preserves_single_issue_single_consumption(self) -> None:
        record = self.evidence.consumed_receipt.record
        self.assertEqual(record["state"], "CONSUMED")
        self.assertEqual(record["issuance_count"], 1)
        self.assertEqual(record["consumption_count"], 1)
        self.assertFalse(record["production_authority"])

    def test_resealed_receipt_cannot_claim_production_durability(self) -> None:
        original = self.evidence.issued_receipt
        receipt = copy.deepcopy(dict(original.receipt))
        receipt["production_durable"] = True
        receipt["receipt_sha256"] = contract.durable_authority_receipt_sha256_v2(
            receipt
        )
        tampered = contract.ProtectedDurableReconciliationAuthorityReceiptV2(
            record=original.record,
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )
        self.assertFalse(
            contract.protected_durable_reconciliation_authority_receipt_valid_v2(
                tampered
            )
        )

    def test_default_off_does_not_access_filesystem(self) -> None:
        result = contract.DormantDurableReconciliationAuthorityLedgerV2().open_offline()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "DURABLE_RECONCILIATION_AUTHORITY_V2_DEFAULT_OFF")
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["write_executed"])


if __name__ == "__main__":
    unittest.main()
