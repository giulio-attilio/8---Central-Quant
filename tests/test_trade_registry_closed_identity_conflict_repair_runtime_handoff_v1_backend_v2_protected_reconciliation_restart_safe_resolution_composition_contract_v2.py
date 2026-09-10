from __future__ import annotations

import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_harness_v2 as harness


class ProtectedReconciliationRestartSafeResolutionCompositionContractV2Tests(
    unittest.TestCase
):
    def setUp(self) -> None:
        result = harness.run_protected_reconciliation_restart_safe_resolution_composition_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.result = result

    def test_success_is_synthetic_and_barrier_precedes_resolver(self) -> None:
        evidence = self.result["protected_evidence"].evidence
        self.assertEqual(evidence["barrier_evaluation_count"], 2)
        self.assertEqual(evidence["resolver_invocation_count"], 1)
        self.assertEqual(evidence["reminted_resolver_invocation_count"], 0)
        self.assertFalse(evidence["operational_execution"])

    def test_composed_receipt_remains_valid_and_non_operational(self) -> None:
        receipt = self.result["protected_receipt"].receipt
        self.assertEqual(receipt["resolution_state"], "RESOLVED")
        self.assertFalse(receipt["backend_called"])
        self.assertFalse(receipt["registry_write"])
        self.assertFalse(receipt["runtime_integrated"])
        self.assertFalse(receipt["activation_allowed"])
        self.assertFalse(receipt["live_allowed"])

    def test_default_off_rejects_before_input_inspection(self) -> None:
        result = contract.DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2().resolve_offline(
            None, None, None, session_loss_declared=False, now_epoch=0
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_V2_DEFAULT_OFF",
        )
        self.assertEqual(result["barrier_evaluation_count"], 0)
        self.assertEqual(result["resolver_invocation_count"], 0)

    def test_composition_exposes_no_runtime_or_activation_method(self) -> None:
        instance = contract.DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2()
        for method_name in (
            "activate", "start_runtime", "call_backend", "write_registry",
            "send_order",
        ):
            self.assertFalse(hasattr(instance, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
