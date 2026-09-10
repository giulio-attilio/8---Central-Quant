from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_harness_v2 as harness


class ProtectedHeldLeasePortAdapterHarnessV2Tests(unittest.TestCase):
    def test_harness_passes_all_synthetic_fail_closed_checks(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_harness_v2()

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["check_count"], 16)
        self.assertEqual(result["passed_count"], 16)
        self.assertEqual(result["lease_revalidation_count"], 1)
        self.assertTrue(
            harness.protected_held_lease_port_adapter_harness_evidence_valid_v2(
                result["protected_evidence"]
            )
        )
        self.assertEqual(
            repr(result["protected_evidence"]),
            "ProtectedHeldLeasePortAdapterHarnessEvidenceV2(<protected>)",
        )

    def test_harness_has_no_operational_side_effect(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_harness_v2()

        self.assertTrue(result["ok"], result)
        for key in (
            "backend_bound",
            "backend_called",
            "provider_called",
            "store_called",
            "writer_called",
            "lock_acquired",
            "lock_released",
            "filesystem_accessed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "production_authority",
            "runtime_integrated",
            "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)
        self.assertTrue(result["no_order_sent"])

    def test_resealed_evidence_count_tamper_is_rejected(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_harness_v2()
        protected = result["protected_evidence"]
        evidence = copy.deepcopy(dict(protected.evidence))
        evidence["lease_revalidation_count"] = 2
        evidence["evidence_sha256"] = (
            harness.protected_held_lease_port_adapter_harness_evidence_sha256_v2(
                evidence
            )
        )
        tampered = harness.ProtectedHeldLeasePortAdapterHarnessEvidenceV2(
            adapter_plan=protected.adapter_plan,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )

        self.assertFalse(
            harness.protected_held_lease_port_adapter_harness_evidence_valid_v2(
                tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
