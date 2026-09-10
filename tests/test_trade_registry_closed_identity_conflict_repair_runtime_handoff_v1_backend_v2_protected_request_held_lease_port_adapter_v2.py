from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_execution_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2 as adapter


class SyntheticProtectedHeldLeasePortAdapterV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        result = harness.run_protected_held_lease_port_adapter_execution_harness_v2()
        if result.get("ok") is not True:
            raise AssertionError(result)
        self.result = result
        self.protected = result["protected_result"]

    def reseal(self, *, terminal=None, attestation=None):
        terminal = copy.deepcopy(
            dict(self.protected.terminal_result if terminal is None else terminal)
        )
        attestation = copy.deepcopy(
            dict(self.protected.port_attestation if attestation is None else attestation)
        )
        envelope = copy.deepcopy(dict(self.protected.envelope))
        envelope["terminal_result_sha256"] = terminal["result_sha256"]
        envelope["port_attestation_sha256"] = attestation[
            "attestation_sha256"
        ]
        envelope["envelope_sha256"] = (
            adapter.protected_held_lease_port_invocation_result_envelope_sha256_v2(
                envelope
            )
        )
        return adapter.ProtectedHeldLeasePortInvocationResultV2(
            adapter_plan=self.protected.adapter_plan,
            port_attestation=attestation,
            terminal_result=terminal,
            envelope=envelope,
            envelope_sha256=envelope["envelope_sha256"],
        )

    def test_returns_only_valid_protected_terminal_result(self) -> None:
        self.assertTrue(
            adapter.protected_held_lease_port_invocation_result_valid_v2(
                self.protected
            )
        )
        self.assertEqual(
            repr(self.protected),
            "ProtectedHeldLeasePortInvocationResultV2(<protected>)",
        )
        self.assertFalse(self.result["raw_result_exposed"])
        self.assertEqual(self.result["backend_call_count"], 1)
        self.assertEqual(self.result["lease_revalidation_count"], 1)
        self.assertTrue(self.result["synthetic_memory_write_executed"])

    def test_resealed_ambiguous_terminal_without_recovery_is_rejected(self) -> None:
        terminal = copy.deepcopy(dict(self.protected.terminal_result))
        terminal["terminal_state"] = "AMBIGUOUS"
        terminal["result_sha256"] = backend_v2.stable_sha256_v2(
            {
                key: item
                for key, item in terminal.items()
                if key != "result_sha256"
            }
        )

        self.assertFalse(
            adapter.protected_held_lease_port_invocation_result_valid_v2(
                self.reseal(terminal=terminal)
            )
        )

    def test_resealed_real_registry_attestation_escalation_is_rejected(self) -> None:
        attestation = copy.deepcopy(dict(self.protected.port_attestation))
        attestation["real_registry_access_allowed"] = True
        attestation["attestation_sha256"] = (
            adapter.synthetic_held_lease_backend_port_attestation_sha256_v2(
                attestation
            )
        )

        self.assertFalse(
            adapter.protected_held_lease_port_invocation_result_valid_v2(
                self.reseal(attestation=attestation)
            )
        )

    def test_no_real_operational_effect_is_reported(self) -> None:
        for key in (
            "filesystem_write_executed",
            "real_registry_write_executed",
            "provider_called",
            "store_called",
            "writer_called",
            "lock_acquired_by_adapter",
            "lock_released_by_adapter",
            "filesystem_accessed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "production_authority",
            "runtime_integrated",
            "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(self.result[key], key)
        self.assertTrue(self.result["no_order_sent"])


if __name__ == "__main__":
    unittest.main()
