from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_harness_v2 as harness


class ProtectedHeldLeasePortAdapterContractV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.protected = result["protected_plan"]

    def test_protected_plan_retains_exact_authority_instances(self) -> None:
        self.assertTrue(
            contract.protected_held_lease_port_adapter_plan_valid_v2(
                self.protected
            )
        )
        self.assertEqual(
            repr(self.protected),
            "ProtectedHeldLeasePortAdapterPlanV2(<protected>)",
        )
        self.assertIs(
            self.protected.cas_witness,
            self.protected.protected_request.cas_witness,
        )
        self.assertIs(
            self.protected.maintenance_permit,
            self.protected.protected_request.maintenance_permit,
        )
        self.assertIs(
            self.protected.live_lease_token,
            self.protected.protected_request.live_lease_token,
        )
        self.assertIs(
            self.protected.lease_witness,
            self.protected.protected_request.lease_witness,
        )

    def test_plan_is_strictly_dormant_and_non_reentrant(self) -> None:
        plan = self.protected.plan

        self.assertTrue(plan["execution_deferred"])
        self.assertTrue(plan["lock_already_held_required"])
        self.assertEqual(plan["maximum_lock_acquisition_count"], 1)
        for key in (
            "backend_reacquire_allowed",
            "store_reacquire_allowed",
            "adapter_release_allowed",
            "raw_mapping_input_allowed",
            "candidate_recanonicalization_allowed",
            "backend_bound",
            "backend_call_allowed",
            "production_authority",
            "runtime_integrated",
            "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(plan[key], key)

    def test_resealed_raw_mapping_escalation_is_rejected(self) -> None:
        plan = copy.deepcopy(dict(self.protected.plan))
        plan["raw_mapping_input_allowed"] = True
        plan["plan_sha256"] = (
            contract.protected_held_lease_port_adapter_plan_sha256_v2(plan)
        )
        tampered = contract.ProtectedHeldLeasePortAdapterPlanV2(
            protected_request=self.protected.protected_request,
            cas_witness=self.protected.cas_witness,
            maintenance_permit=self.protected.maintenance_permit,
            live_lease_token=self.protected.live_lease_token,
            lease_witness=self.protected.lease_witness,
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )

        self.assertFalse(
            contract.protected_held_lease_port_adapter_plan_valid_v2(tampered)
        )

    def test_adapter_plan_exposes_no_execution_method(self) -> None:
        for method_name in (
            "apply_under_held_maintenance_lease",
            "apply_attested_transaction_offline",
            "invoke",
            "activate",
        ):
            self.assertFalse(hasattr(self.protected, method_name), method_name)

    def test_invalid_freshness_budget_is_rejected_at_configuration(self) -> None:
        with self.assertRaises(ValueError):
            contract.DormantHeldLeasePortAdapterConfigV2(
                maximum_cas_witness_age_seconds=31
            )


if __name__ == "__main__":
    unittest.main()
