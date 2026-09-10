from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_v1 as composition_v1


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off composition must not inspect dependencies")


class StartupRecoverySixPortEvidenceBuilderCompositionOfflineV1Tests(
    unittest.TestCase
):
    @staticmethod
    def _compose(values):
        return values["six_port_composition"].compose_offline(
            protected_adapter_plan=values["protected_adapter_plan"],
            read_adapter=values["reference_adapter"],
            terminal_normalizer=values["normalizer_reference"],
            raw_terminal_receipts=values["raw_terminal_receipts"],
        )

    def test_harness_builds_exact_independent_oracle_bundle(self) -> None:
        result = harness.run_synthetic_six_port_evidence_builder_composition_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["protected_read_count"], 9)
        self.assertEqual(result["replay_read_count"], 9)
        self.assertGreater(result["protected_normalizer_call_count"], 0)
        self.assertEqual(
            result["protected_normalizer_call_count"],
            result["replay_normalizer_call_count"],
        )
        self.assertTrue(result["bundle_matches_independent_oracle"])
        self.assertTrue(result["scope_aware_conformance_verified"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_any_input(self) -> None:
        composition = (
            composition_v1.OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1()
        )

        result = composition.compose_offline(
            protected_adapter_plan=_Explosive(),
            read_adapter=_Explosive(),
            terminal_normalizer=_Explosive(),
            raw_terminal_receipts=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_DEFAULT_OFF"],
        )
        self.assertFalse(result["evidence_builder_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_missing_raw_receipts_fails_before_any_protected_call(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        values["raw_terminal_receipts"] = []

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RAW_TERMINAL_RECEIPT_SET_INVALID"])
        self.assertEqual(
            sum(values["reference_adapter"].counters().values()), 0
        )
        self.assertEqual(values["normalizer_reference"].call_count, 0)
        self.assertFalse(result["evidence_builder_called"])

    def test_duplicate_raw_receipt_fails_before_any_protected_call(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        raw = values["raw_terminal_receipts"][0]
        values["raw_terminal_receipts"] = [raw, copy.deepcopy(raw)]

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertIn(
            result["reasons"][0],
            {"RAW_TERMINAL_RECEIPT_SET_INVALID", "RAW_TERMINAL_RECEIPT_SCOPE_MISMATCH"},
        )
        self.assertEqual(
            sum(values["reference_adapter"].counters().values()), 0
        )

    def test_mixed_plan_instances_are_rejected_before_calls(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        other = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        values["normalizer_reference"] = other["normalizer_reference"]

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_SIX_PORT_DEPENDENCIES_INVALID"]
        )
        self.assertEqual(
            sum(values["reference_adapter"].counters().values()), 0
        )
        self.assertEqual(other["normalizer_reference"].call_count, 0)

    def test_preused_read_adapter_is_rejected(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        values["reference_adapter"].read_backend_snapshot_offline(
            phase="INITIAL"
        )

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_SIX_PORT_DEPENDENCIES_INVALID"]
        )
        self.assertFalse(result["evidence_builder_called"])

    def test_preused_normalizer_is_rejected(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        values["normalizer_reference"].normalize_terminal_receipt_offline(
            raw_receipt=values["raw_terminal_receipts"][0],
            protected_scope_binding=values["protected_scope_binding"],
        )

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_SIX_PORT_DEPENDENCIES_INVALID"]
        )
        self.assertEqual(
            sum(values["reference_adapter"].counters().values()), 0
        )
        self.assertFalse(result["evidence_builder_called"])

    def test_invalid_protected_receipt_prevents_builder_call(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()
        source = values["terminal_normalizer_port"]
        transaction_sha = values["raw_terminal_receipts"][0][
            "transaction_sha256"
        ]
        receipt = copy.deepcopy(source._receipts[transaction_sha])
        receipt["terminal_state"] = "UNKNOWN"
        receipt["receipt_sha256"] = conformance_v1.synthetic_terminal_receipt_sha256_v1(
            receipt
        )
        source._receipts[transaction_sha] = receipt

        result = self._compose(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_SIX_PORT_COLLECTION_FAILED_CLOSED"]
        )
        self.assertEqual(result["protected_read_count"], 5)
        self.assertFalse(result["evidence_builder_called"])
        self.assertFalse(result["bundle_created"])

    def test_result_remains_synthetic_and_non_authoritative(self) -> None:
        values = harness.build_synthetic_six_port_evidence_builder_composition_context_v1()

        result = self._compose(values)
        bundle = result["fixture_bundle"]

        self.assertTrue(result["ok"])
        self.assertTrue(bundle["synthetic_fixture_only"])
        self.assertFalse(bundle["durable"])
        self.assertFalse(bundle["production_evidence"])
        self.assertFalse(bundle["production_authority"])
        self.assertFalse(bundle["runtime_admissible"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["activation_allowed"])

    def test_composition_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_six_port_evidence_builder_composition_offline_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
