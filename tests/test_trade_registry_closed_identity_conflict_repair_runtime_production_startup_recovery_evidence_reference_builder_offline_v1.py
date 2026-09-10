from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1 as dormant_ports_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as builder


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off builder must not inspect dependencies")


class StartupRecoveryEvidenceReferenceBuilderOfflineV1Tests(unittest.TestCase):
    @staticmethod
    def _build(values):
        return values["reference_builder"].build_offline(
            protected_port_binding=values["protected_port_binding"],
            raw_terminal_receipts=values["raw_terminal_receipts"],
        )

    def test_harness_builds_exact_oracle_bundle_and_conforms(self) -> None:
        result = harness.run_synthetic_evidence_reference_builder_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["read_port_calls"], 9)
        self.assertEqual(result["normalizer_port_calls"], 1)
        self.assertTrue(result["bundle_matches_independent_oracle"])
        self.assertTrue(result["scope_aware_conformance_verified"])
        self.assertTrue(result["synthetic_bundle_created"])
        self.assertFalse(result["production_evidence"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_dependencies(self) -> None:
        dormant = builder.OfflineStartupRecoveryEvidenceReferenceBuilderV1()

        result = dormant.build_offline(
            protected_port_binding=_Explosive(),
            raw_terminal_receipts=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_REFERENCE_BUILDER_DEFAULT_OFF"])
        self.assertFalse(result["ports_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_missing_raw_receipt_fails_before_any_port_call(self) -> None:
        values = harness.build_synthetic_evidence_reference_builder_context_v1()
        values["raw_terminal_receipts"] = []

        result = self._build(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RAW_TERMINAL_RECEIPT_SET_INVALID"])
        self.assertFalse(result["ports_called"])
        self.assertEqual(sum(values["evidence_read_port"].counters().values()), 0)
        self.assertEqual(values["terminal_normalizer_port"].call_count, 0)

    def test_rehashed_wrong_transaction_fails_before_any_port_call(self) -> None:
        values = harness.build_synthetic_evidence_reference_builder_context_v1()
        raw = copy.deepcopy(values["raw_terminal_receipts"][0])
        raw["transaction_sha256"] = "c" * 64
        raw["raw_receipt_sha256"] = builder.synthetic_raw_terminal_receipt_sha256_v1(
            raw
        )
        values["raw_terminal_receipts"] = [raw]

        result = self._build(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RAW_TERMINAL_RECEIPT_SCOPE_MISMATCH"])
        self.assertFalse(result["ports_called"])

    def test_dormant_nonexecuting_port_types_are_rejected(self) -> None:
        scope_values = harness.build_synthetic_evidence_reference_builder_context_v1()
        read_port = dormant_ports_harness.SyntheticEvidenceReadPortDoubleV1()
        normalizer = (
            dormant_ports_harness.SyntheticTerminalReceiptNormalizerPortDoubleV1()
        )
        ports_contract = (
            dormant_ports_harness.make_synthetic_evidence_builder_ports_contract_v1(
                scope_binding_sha256=scope_values[
                    "protected_scope_binding"
                ].binding_sha256,
                evidence_read_port=read_port,
                terminal_normalizer_port=normalizer,
            )
        )
        ports_result = ports_contract.bind_offline(
            protected_scope_binding=scope_values["protected_scope_binding"],
            evidence_read_port=read_port,
            terminal_normalizer_port=normalizer,
        )
        reference_builder = builder.OfflineStartupRecoveryEvidenceReferenceBuilderV1(
            config=builder.OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1(
                enabled=True,
                scope_attestation=(
                    builder.OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1
                ),
                expected_port_binding_sha256=ports_result[
                    "protected_port_binding"
                ].binding_sha256,
            )
        )
        scope_values["reference_builder"] = reference_builder
        scope_values["protected_port_binding"] = ports_result[
            "protected_port_binding"
        ]

        result = self._build(scope_values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_REFERENCE_PORT_BINDING_INVALID"]
        )
        self.assertFalse(result["ports_called"])

    def test_rehashed_invalid_capability_probe_fails_closed(self) -> None:
        values = harness.build_synthetic_evidence_reference_builder_context_v1()
        artifacts = copy.deepcopy(values["evidence_read_port"]._artifacts)
        probe = copy.deepcopy(values["capability_probe"])
        probe["writers_blocked_entire_window"] = False
        probe["probe_receipt_sha256"] = (
            builder.synthetic_capability_probe_receipt_sha256_v1(probe)
        )
        read_port = builder.InMemorySyntheticEvidenceReadPortV1(
            artifacts=artifacts, capability_probe=probe
        )
        ports_contract = (
            dormant_ports_harness.make_synthetic_evidence_builder_ports_contract_v1(
                scope_binding_sha256=values[
                    "protected_scope_binding"
                ].binding_sha256,
                evidence_read_port=read_port,
                terminal_normalizer_port=values["terminal_normalizer_port"],
            )
        )
        ports_result = ports_contract.bind_offline(
            protected_scope_binding=values["protected_scope_binding"],
            evidence_read_port=read_port,
            terminal_normalizer_port=values["terminal_normalizer_port"],
        )
        values["protected_port_binding"] = ports_result["protected_port_binding"]
        values["reference_builder"] = (
            builder.OfflineStartupRecoveryEvidenceReferenceBuilderV1(
                config=builder.OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1(
                    enabled=True,
                    scope_attestation=(
                        builder.OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1
                    ),
                    expected_port_binding_sha256=values[
                        "protected_port_binding"
                    ].binding_sha256,
                )
            )
        )

        result = self._build(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["REFERENCE_PORT_COLLECTION_FAILED_CLOSED"])
        self.assertTrue(result["ports_called"])
        self.assertFalse(result["synthetic_bundle_created"])
        self.assertFalse(result["scope_aware_conformance_verified"])

    def test_generated_bundle_remains_synthetic_and_non_authoritative(self) -> None:
        values = harness.build_synthetic_evidence_reference_builder_context_v1()

        result = self._build(values)
        bundle = result["fixture_bundle"]
        completion = bundle["completion_attestation"]

        self.assertTrue(result["ok"])
        self.assertTrue(bundle["synthetic_fixture_only"])
        self.assertFalse(bundle["durable"])
        self.assertFalse(bundle["production_evidence"])
        self.assertFalse(bundle["production_authority"])
        self.assertFalse(bundle["runtime_admissible"])
        self.assertFalse(completion["durability_verified"])
        self.assertFalse(completion["authenticated_authority_verified"])

    def test_builder_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_evidence_reference_builder_offline_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "OfflineStartupRecoveryEvidenceReferenceBuilderV1", main_source
        )


if __name__ == "__main__":
    unittest.main()
