from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as harness


class ProtectedReconciliationResolutionReceiptContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_protected_reconciliation_resolution_receipt_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.protected = result["protected_receipt"]

    def test_receipt_is_protected_and_valid(self) -> None:
        self.assertTrue(
            contract.protected_reconciliation_resolution_receipt_valid_v2(
                self.protected
            )
        )
        self.assertEqual(
            repr(self.protected),
            "ProtectedReconciliationResolutionReceiptV2(<protected>)",
        )
        self.assertEqual(
            repr(self.protected.fresh_authority),
            "ProtectedFreshReconciliationAuthorityV2(<protected>)",
        )

    def test_receipt_resolves_only_the_same_transaction(self) -> None:
        receipt = self.protected.receipt
        obligation = self.protected.obligation.obligation

        self.assertEqual(receipt["transaction_sha256"], obligation["transaction_sha256"])
        self.assertEqual(receipt["resolution_state"], "RESOLVED")
        self.assertFalse(receipt["reconciliation_required"])
        self.assertFalse(receipt["new_apply_allowed"])
        self.assertFalse(receipt["retry_allowed"])
        self.assertFalse(receipt["original_authorization_reused"])
        self.assertTrue(receipt["restart_barrier_continuity_verified"])
        self.assertEqual(
            receipt["restart_barrier_sha256"],
            self.protected.protected_restart_barrier.barrier_sha256,
        )

    def test_resealed_receipt_cannot_substitute_restart_barrier(self) -> None:
        receipt = copy.deepcopy(dict(self.protected.receipt))
        receipt["restart_barrier_sha256"] = "0" * 64
        receipt["receipt_sha256"] = (
            contract.protected_reconciliation_resolution_receipt_sha256_v2(receipt)
        )
        tampered = contract.ProtectedReconciliationResolutionReceiptV2(
            obligation=self.protected.obligation,
            fresh_authority=self.protected.fresh_authority,
            protected_restart_barrier=self.protected.protected_restart_barrier,
            terminal_resolution_evidence=self.protected.terminal_resolution_evidence,
            single_use_consumption_receipt=self.protected.single_use_consumption_receipt,
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )
        self.assertFalse(
            contract.protected_reconciliation_resolution_receipt_valid_v2(tampered)
        )

    def test_resealed_receipt_cannot_escalate_apply_authority(self) -> None:
        receipt = copy.deepcopy(dict(self.protected.receipt))
        receipt["new_apply_allowed"] = True
        receipt["receipt_sha256"] = (
            contract.protected_reconciliation_resolution_receipt_sha256_v2(receipt)
        )
        tampered = contract.ProtectedReconciliationResolutionReceiptV2(
            obligation=self.protected.obligation,
            fresh_authority=self.protected.fresh_authority,
            protected_restart_barrier=self.protected.protected_restart_barrier,
            terminal_resolution_evidence=self.protected.terminal_resolution_evidence,
            single_use_consumption_receipt=(
                self.protected.single_use_consumption_receipt
            ),
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_reconciliation_resolution_receipt_valid_v2(tampered)
        )

    def test_resealed_consumption_receipt_cannot_claim_second_consumption(self) -> None:
        consumption = copy.deepcopy(
            dict(self.protected.single_use_consumption_receipt)
        )
        consumption["consumption_count"] = 2
        consumption["consumption_sha256"] = (
            contract.single_use_resolution_consumption_sha256_v2(consumption)
        )
        tampered = contract.ProtectedReconciliationResolutionReceiptV2(
            obligation=self.protected.obligation,
            fresh_authority=self.protected.fresh_authority,
            protected_restart_barrier=self.protected.protected_restart_barrier,
            terminal_resolution_evidence=self.protected.terminal_resolution_evidence,
            single_use_consumption_receipt=consumption,
            receipt=self.protected.receipt,
            receipt_sha256=self.protected.receipt_sha256,
        )

        self.assertFalse(
            contract.protected_reconciliation_resolution_receipt_valid_v2(tampered)
        )

    def test_protected_authority_cannot_substitute_ledger_instance(self) -> None:
        authority = self.protected.fresh_authority
        substituted = contract.ProtectedFreshReconciliationAuthorityV2(
            authorization_receipt=authority.authorization_receipt,
            maintenance_permit=authority.maintenance_permit,
            live_lease_token=authority.live_lease_token,
            lease_witness=authority.lease_witness,
            single_use_ledger=(
                contract.InMemorySyntheticReconciliationResolutionLedgerV2()
            ),
            authorization_issuer=authority.authorization_issuer,
            process_session_anchor=authority.process_session_anchor,
            authority=authority.authority,
            authority_sha256=authority.authority_sha256,
        )
        tampered = contract.ProtectedReconciliationResolutionReceiptV2(
            obligation=self.protected.obligation,
            fresh_authority=substituted,
            protected_restart_barrier=self.protected.protected_restart_barrier,
            terminal_resolution_evidence=self.protected.terminal_resolution_evidence,
            single_use_consumption_receipt=(
                self.protected.single_use_consumption_receipt
            ),
            receipt=self.protected.receipt,
            receipt_sha256=self.protected.receipt_sha256,
        )

        self.assertFalse(
            contract.protected_reconciliation_resolution_receipt_valid_v2(tampered)
        )

    def test_authorization_issuer_is_single_use_and_session_protected(self) -> None:
        authority = self.protected.fresh_authority
        receipt = authority.authorization_receipt

        replay = authority.authorization_issuer.issue_once(
            grant_sha256=receipt["grant_sha256"],
            obligation_sha256=self.protected.obligation.obligation_sha256,
            now_epoch=receipt["consumed_at_epoch"],
            expires_at_epoch=receipt["expires_at_epoch"],
        )

        self.assertIsNone(replay)
        self.assertEqual(
            authority.authorization_issuer.snapshot()["issued_authorization_count"],
            1,
        )
        self.assertEqual(
            repr(authority.process_session_anchor),
            "ProtectedSyntheticReconciliationProcessSessionAnchorV2(<protected>)",
        )

    def test_receipt_has_no_execution_method(self) -> None:
        for method_name in (
            "apply", "retry", "reconcile", "activate", "call_backend", "write_registry"
        ):
            self.assertFalse(hasattr(self.protected, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
