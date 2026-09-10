from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1 as ports_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as reference_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_v1 as normalizer_v1


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off normalizer must not inspect dependencies")


class StartupRecoveryTerminalReceiptNormalizerReferenceOfflineV1Tests(
    unittest.TestCase
):
    @staticmethod
    def _normalize_first(values):
        return values["normalizer_reference"].normalize_terminal_receipt_offline(
            raw_receipt=values["raw_terminal_receipts"][0],
            protected_scope_binding=values["protected_scope_binding"],
        )

    def test_harness_normalizes_complete_batch_against_oracle(self) -> None:
        result = harness.run_synthetic_terminal_receipt_normalizer_reference_harness_v1()

        self.assertTrue(result["ok"])
        self.assertGreater(result["normalized_receipt_count"], 0)
        self.assertTrue(result["batch_sequence_completed"])
        self.assertTrue(result["receipt_set_matches_independent_oracle"])
        self.assertFalse(result["provider_instance_bound"])
        self.assertFalse(result["backend_instance_bound"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_rejects_before_inspecting_dependencies(self) -> None:
        normalizer = normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1(
            protected_adapter_plan=_Explosive(),
            source_normalizer_port=_Explosive(),
        )

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "DEFAULT_OFF",
        ):
            normalizer.normalize_terminal_receipt_offline(
                raw_receipt=_Explosive(), protected_scope_binding=_Explosive()
            )

    def test_non_reference_source_type_is_rejected_without_call(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        source = ports_harness_v1.SyntheticTerminalReceiptNormalizerPortDoubleV1()
        normalizer = normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_normalizer_port=source,
            config=normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1(
                enabled=True,
                scope_attestation=(
                    normalizer_v1.OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1
                ),
                expected_adapter_plan_sha256=values[
                    "protected_adapter_plan"
                ].plan_sha256,
                expected_source_object_identity_sha256=(
                    ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                        source
                    )
                ),
            ),
        )

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "EXACT_IN_MEMORY",
        ):
            normalizer.normalize_terminal_receipt_offline(
                raw_receipt=values["raw_terminal_receipts"][0],
                protected_scope_binding=values["protected_scope_binding"],
            )

        self.assertEqual(source.call_count, 0)

    def test_different_scope_instance_is_rejected_before_source_call(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        other = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "EXACT_PROTECTED_SCOPE_INSTANCE_REQUIRED",
        ):
            values["normalizer_reference"].normalize_terminal_receipt_offline(
                raw_receipt=values["raw_terminal_receipts"][0],
                protected_scope_binding=other["protected_scope_binding"],
            )

        self.assertEqual(values["terminal_normalizer_port"].call_count, 0)

    def test_resealed_wrong_transaction_fails_before_source_call(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        raw = copy.deepcopy(values["raw_terminal_receipts"][0])
        raw["transaction_sha256"] = "c" * 64
        raw["raw_receipt_sha256"] = (
            reference_v1.synthetic_raw_terminal_receipt_sha256_v1(raw)
        )

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "BATCH_SEQUENCE_MISMATCH",
        ):
            values["normalizer_reference"].normalize_terminal_receipt_offline(
                raw_receipt=raw,
                protected_scope_binding=values["protected_scope_binding"],
            )

        self.assertEqual(values["terminal_normalizer_port"].call_count, 0)

    def test_semantically_invalid_normalized_receipt_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        receipt = copy.deepcopy(values["source_bundle"]["terminal_receipts"][0])
        receipt["terminal_state"] = "UNKNOWN"
        receipt["receipt_sha256"] = conformance_v1.synthetic_terminal_receipt_sha256_v1(
            receipt
        )
        source = reference_v1.InMemorySyntheticTerminalReceiptNormalizerV1(
            terminal_receipts=[receipt]
        )
        normalizer = harness.make_synthetic_terminal_receipt_normalizer_reference_v1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_normalizer_port=source,
        )

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "NORMALIZED_TERMINAL_RECEIPT_INVALID",
        ):
            normalizer.normalize_terminal_receipt_offline(
                raw_receipt=values["raw_terminal_receipts"][0],
                protected_scope_binding=values["protected_scope_binding"],
            )

        self.assertEqual(source.call_count, 1)
        self.assertEqual(normalizer.call_count, 0)
        self.assertFalse(normalizer.completed)

    def test_source_instance_substitution_is_rejected(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        original = values["terminal_normalizer_port"]
        substitute = reference_v1.InMemorySyntheticTerminalReceiptNormalizerV1(
            terminal_receipts=values["source_bundle"]["terminal_receipts"]
        )
        normalizer = normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_normalizer_port=substitute,
            config=normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1(
                enabled=True,
                scope_attestation=(
                    normalizer_v1.OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1
                ),
                expected_adapter_plan_sha256=values[
                    "protected_adapter_plan"
                ].plan_sha256,
                expected_source_object_identity_sha256=(
                    ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                        original
                    )
                ),
            ),
        )

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "SOURCE_INSTANCE_PIN_MISMATCH",
        ):
            normalizer.normalize_terminal_receipt_offline(
                raw_receipt=values["raw_terminal_receipts"][0],
                protected_scope_binding=values["protected_scope_binding"],
            )

        self.assertEqual(substitute.call_count, 0)

    def test_incomplete_and_duplicate_batches_fail_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_normalizer_reference_context_v1()
        normalizer = values["normalizer_reference"]

        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "BATCH_INCOMPLETE",
        ):
            normalizer.terminal_receipt_set_snapshot()

        self._normalize_first(values)
        with self.assertRaisesRegex(
            normalizer_v1.StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1,
            "BATCH_ALREADY_COMPLETE",
        ):
            self._normalize_first(values)

        self.assertEqual(normalizer.call_count, 1)

    def test_reference_normalizer_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_terminal_receipt_normalizer_reference_offline_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
