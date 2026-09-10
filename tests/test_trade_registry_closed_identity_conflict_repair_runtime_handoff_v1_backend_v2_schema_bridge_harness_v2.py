from __future__ import annotations

import builtins
import copy
import socket
import unittest
from unittest import mock

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2 as provider_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2 as compatibility_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


def _compatibility_bundle():
    upstream = provider_harness.build_provider_store_projection_fixture_v2()
    result = compatibility_harness.run_writer_coordination_compatibility_harness_v2(
        upstream["projection"]["protected_bundle"]
    )
    if result.get("ok") is not True:
        raise AssertionError("compatibility harness failed")
    return result["protected_bundle"]


class HandoffV1BackendV2SchemaBridgeHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compatibility_bundle = _compatibility_bundle()

    def test_complete_mapping_harness_never_calls_operational_surfaces(self) -> None:
        with (
            mock.patch.object(
                envelope_v1.DormantProductionInvocationEnvelopeBuilderV1,
                "project_offline",
                side_effect=AssertionError("ENVELOPE_BUILDER_CALLED"),
            ),
            mock.patch.object(
                envelope_v1.InMemorySyntheticAuthorizationConsumptionLedgerV1,
                "consume_once",
                side_effect=AssertionError("AUTHORIZATION_CONSUMED"),
            ),
            mock.patch.object(
                boundary_v1.DormantProductionBackendBoundaryV1,
                "project_invocation_offline",
                side_effect=AssertionError("BOUNDARY_CALLED"),
            ),
            mock.patch.object(
                physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2,
                "apply_attested_transaction_offline",
                side_effect=AssertionError("BACKEND_CALLED"),
            ),
            mock.patch.object(
                builtins, "open", side_effect=AssertionError("FILESYSTEM_CALLED")
            ),
            mock.patch.object(
                socket,
                "create_connection",
                side_effect=AssertionError("NETWORK_CALLED"),
            ),
        ):
            result = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
                self.compatibility_bundle
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["apply_mapping_count"], 21)
        self.assertEqual(result["terminal_mapping_count"], 21)
        self.assertEqual(result["recovery_mapping_count"], 24)
        self.assertTrue(result["complete_apply_coverage"])
        self.assertTrue(result["complete_terminal_coverage"])
        self.assertTrue(result["complete_recovery_coverage"])
        for key in (
            "executable_request_materialized", "executable_result_materialized",
            "authorization_consumed", "lease_validated_live", "provider_called",
            "store_called", "backend_called", "writer_called", "lock_acquired",
            "filesystem_accessed", "real_registry_accessed", "network_accessed",
            "broker_called", "write_executed", "production_authority",
            "runtime_integrated", "activation_allowed", "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_target_key_coverage_is_exact(self) -> None:
        result = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )
        trace = result["protected_trace"].trace

        self.assertEqual(
            trace["apply_target_keys"], sorted(backend_v2._TRANSACTION_REQUEST_KEYS)
        )
        self.assertEqual(
            trace["terminal_target_keys"], sorted(envelope_v1._TERMINAL_RESULT_KEYS)
        )
        self.assertEqual(
            trace["recovery_target_keys"], sorted(backend_v2._RECOVERY_REQUEST_KEYS)
        )

    def test_trace_oracle_preserves_hashes_without_materializing_values(self) -> None:
        result = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )
        trace = result["protected_trace"].trace
        entries = trace["apply_trace"] + trace["terminal_trace"] + trace["recovery_trace"]

        self.assertGreater(trace["preserve_exact_count"], 0)
        self.assertGreater(trace["forced_constant_count"], 0)
        self.assertGreater(trace["deferred_mapping_count"], 0)
        self.assertTrue(
            all(
                item["source_sample_sha256"] == item["expected_target_sha256"]
                for item in entries
                if item["oracle_relation"] == "EQUAL_HASH"
            )
        )
        self.assertTrue(all(item["materialized"] is False for item in entries))
        self.assertEqual(trace["materialized_target_count"], 0)

    def test_harness_is_deterministic(self) -> None:
        first = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )
        second = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )

        self.assertEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertEqual(first["trace_sha256"], second["trace_sha256"])

    def test_missing_upstream_fails_closed_without_calls(self) -> None:
        result = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(None)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "SCHEMA_BRIDGE_HARNESS_INPUT_OR_TRACE_INVALID"
        )
        self.assertFalse(result["backend_called"])
        self.assertFalse(result["authorization_consumed"])

    def test_resealed_trace_tampering_is_rejected(self) -> None:
        result = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )
        plan = result["protected_plan"]
        protected = result["protected_trace"]
        trace = copy.deepcopy(dict(protected.trace))
        trace["apply_trace"][0]["materialized"] = True
        trace["trace_sha256"] = backend_v2.stable_sha256_v2(
            {name: item for name, item in trace.items() if name != "trace_sha256"}
        )
        tampered = harness.ProtectedSchemaBridgeMappingTraceV2(
            bridge_plan_sha256=protected.bridge_plan_sha256,
            trace=trace,
            trace_sha256=trace["trace_sha256"],
        )

        self.assertFalse(harness.protected_mapping_trace_valid_v2(tampered, plan))

    def test_protected_trace_exposes_no_execution_methods(self) -> None:
        protected = harness.run_handoff_v1_backend_v2_schema_bridge_harness_v2(
            self.compatibility_bundle
        )["protected_trace"]

        self.assertEqual(repr(protected), "ProtectedSchemaBridgeMappingTraceV2(<protected>)")
        for name in (
            "translate", "build_request", "invoke", "apply", "reconcile",
            "consume", "validate_live", "acquire", "activate",
        ):
            self.assertFalse(hasattr(protected, name), name)


if __name__ == "__main__":
    unittest.main()
