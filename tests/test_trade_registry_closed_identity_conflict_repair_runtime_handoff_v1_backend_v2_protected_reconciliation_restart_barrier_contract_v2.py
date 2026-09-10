from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_harness_v2 as harness


class ProtectedReconciliationRestartBarrierContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_protected_reconciliation_restart_barrier_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.protected = result["protected_barrier"]

    def test_barrier_is_protected_and_valid(self) -> None:
        self.assertTrue(
            contract.protected_reconciliation_restart_barrier_valid_v2(
                self.protected
            )
        )
        self.assertEqual(
            repr(self.protected),
            "ProtectedReconciliationRestartBarrierV2(<protected>)",
        )

    def test_barrier_never_grants_resolution_or_activation(self) -> None:
        record = self.protected.barrier
        self.assertFalse(record["resolution_authority_granted"])
        self.assertFalse(record["resolution_execution_allowed"])
        self.assertFalse(record["restart_resolution_allowed"])
        self.assertFalse(record["runtime_integrated"])
        self.assertFalse(record["activation_allowed"])
        self.assertFalse(record["live_allowed"])

    def test_resealed_restart_permission_is_rejected(self) -> None:
        record = copy.deepcopy(dict(self.protected.barrier))
        record["restart_resolution_allowed"] = True
        record["barrier_sha256"] = (
            contract.protected_reconciliation_restart_barrier_sha256_v2(record)
        )
        tampered = contract.ProtectedReconciliationRestartBarrierV2(
            obligation=self.protected.obligation,
            reference_authority=self.protected.reference_authority,
            barrier=record,
            barrier_sha256=record["barrier_sha256"],
        )
        self.assertFalse(
            contract.protected_reconciliation_restart_barrier_valid_v2(tampered)
        )

    def test_resealed_durable_validation_claim_is_rejected(self) -> None:
        record = copy.deepcopy(dict(self.protected.barrier))
        record["durable_authority_validation_implemented"] = True
        record["barrier_sha256"] = (
            contract.protected_reconciliation_restart_barrier_sha256_v2(record)
        )
        tampered = contract.ProtectedReconciliationRestartBarrierV2(
            obligation=self.protected.obligation,
            reference_authority=self.protected.reference_authority,
            barrier=record,
            barrier_sha256=record["barrier_sha256"],
        )
        self.assertFalse(
            contract.protected_reconciliation_restart_barrier_valid_v2(tampered)
        )

    def test_barrier_has_no_execution_method(self) -> None:
        for method_name in (
            "resolve", "apply", "retry", "activate", "call_backend",
            "write_registry",
        ):
            self.assertFalse(hasattr(self.protected, method_name), method_name)

    def test_default_off_precedes_input_inspection(self) -> None:
        result = contract.DormantProtectedReconciliationRestartBarrierContractV2().evaluate_offline(
            None,
            None,
            session_loss_declared=False,
            now_epoch=0,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PROTECTED_RECONCILIATION_RESTART_BARRIER_V2_DEFAULT_OFF",
        )
        self.assertFalse(result["resolution_executed"])

    def test_enabled_contract_fails_closed_for_malformed_authority(self) -> None:
        configured = contract.DormantProtectedReconciliationRestartBarrierContractV2(
            contract.DormantProtectedReconciliationRestartBarrierConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
                expected_obligation_sha256=self.protected.obligation.obligation_sha256,
                expected_reference_authority_sha256=self.protected.reference_authority.authority_sha256,
            )
        )
        result = configured.issue_offline(
            self.protected.obligation,
            None,
            now_epoch=self.protected.barrier["issued_at_epoch"],
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "REFERENCE_RECONCILIATION_AUTHORITY_INVALID")
        self.assertFalse(result["resolution_executed"])


if __name__ == "__main__":
    unittest.main()
