from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as harness


class ProtectedReconciliationObligationContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_protected_reconciliation_obligation_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.terminal = result["terminal_ambiguity_obligation"]
        self.exception = result["post_call_exception_obligation"]

    def test_terminal_and_unknown_obligations_are_protected(self) -> None:
        for protected in (self.terminal, self.exception):
            self.assertTrue(
                contract.protected_reconciliation_obligation_valid_v2(
                    protected
                )
            )
            self.assertEqual(
                repr(protected),
                "ProtectedReconciliationObligationV2(<protected>)",
            )
        self.assertEqual(
            self.terminal.obligation["cause_kind"],
            "TERMINAL_RESULT_AMBIGUOUS",
        )
        self.assertEqual(self.terminal.obligation["terminal_state"], "AMBIGUOUS")
        self.assertEqual(self.exception.obligation["cause_kind"], "PORT_CALL_EXCEPTION")
        self.assertEqual(self.exception.obligation["terminal_state"], "UNKNOWN")

    def test_apply_and_retry_remain_blocked_until_resolution(self) -> None:
        obligation = self.terminal.obligation

        self.assertEqual(obligation["resolution_state"], "UNRESOLVED")
        self.assertTrue(obligation["reconciliation_required"])
        self.assertTrue(obligation["reconcile_before_retry_required"])
        self.assertFalse(obligation["new_apply_allowed"])
        self.assertFalse(obligation["retry_allowed"])
        self.assertFalse(obligation["original_authorization_reusable"])
        self.assertTrue(obligation["fresh_single_use_authorization_required"])
        self.assertTrue(obligation["fresh_maintenance_permit_required"])
        self.assertTrue(obligation["fresh_lease_required"])

    def test_resealed_source_reason_substitution_is_rejected(self) -> None:
        evidence = copy.deepcopy(dict(self.exception.source_evidence))
        evidence["reason_code"] = "SYNTHETIC_TERMINAL_RESULT_INVALID"
        evidence["evidence_sha256"] = (
            contract.protected_reconciliation_source_evidence_sha256_v2(
                evidence
            )
        )
        tampered = contract.ProtectedReconciliationObligationV2(
            adapter_plan=self.exception.adapter_plan,
            protected_terminal_result=self.exception.protected_terminal_result,
            source_evidence=evidence,
            obligation=self.exception.obligation,
            obligation_sha256=self.exception.obligation_sha256,
        )

        self.assertFalse(
            contract.protected_reconciliation_obligation_valid_v2(tampered)
        )

    def test_obligation_exposes_no_execution_or_resolution_method(self) -> None:
        for method_name in (
            "apply_under_held_maintenance_lease",
            "reconcile_under_fresh_maintenance_lease",
            "resolve",
            "retry",
            "activate",
        ):
            self.assertFalse(hasattr(self.terminal, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
