from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1 as ports_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_v1 as adapter_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as reference_v1


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off adapter must not inspect dependencies")


class StartupRecoveryEvidenceReadPortReferenceAdapterOfflineV1Tests(
    unittest.TestCase
):
    def test_harness_completes_nine_reads_in_strict_order(self) -> None:
        result = harness.run_synthetic_evidence_read_port_reference_adapter_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["read_count"], 9)
        self.assertTrue(result["strict_sequence_completed"])
        self.assertTrue(result["artifacts_match_independent_oracle"])
        self.assertTrue(result["capability_probe_matches_independent_oracle"])
        self.assertFalse(result["provider_instance_bound"])
        self.assertFalse(result["backend_instance_bound"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_rejects_before_inspecting_dependencies(self) -> None:
        adapter = adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1(
            protected_adapter_plan=_Explosive(),
            source_read_port=_Explosive(),
        )

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "DEFAULT_OFF",
        ):
            adapter.read_backend_snapshot_offline(phase="INITIAL")

    def test_non_reference_source_type_is_rejected_without_call(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()
        wrong_source = ports_harness_v1.SyntheticEvidenceReadPortDoubleV1()
        adapter = adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_read_port=wrong_source,
            config=adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1(
                enabled=True,
                scope_attestation=(
                    adapter_v1.OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1
                ),
                expected_adapter_plan_sha256=values[
                    "protected_adapter_plan"
                ].plan_sha256,
                expected_source_object_identity_sha256=(
                    ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                        wrong_source
                    )
                ),
            ),
        )

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "EXACT_IN_MEMORY",
        ):
            adapter.read_backend_snapshot_offline(phase="INITIAL")

    def test_wrong_order_fails_before_source_call(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()
        adapter = values["reference_adapter"]

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "SEQUENCE_VIOLATION",
        ):
            adapter.read_transaction_log_audit_offline(
                snapshot={}, phase="INITIAL"
            )

        self.assertEqual(
            values["evidence_read_port"].counters(),
            {"snapshot": 0, "audit": 0, "prepared": 0, "resolved": 0, "probe": 0},
        )

    def test_wrong_phase_fails_closed(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "PHASE_INVALID",
        ):
            values["reference_adapter"].read_backend_snapshot_offline(
                phase="CURRENT"
            )

        self.assertEqual(sum(values["evidence_read_port"].counters().values()), 0)

    def test_malformed_snapshot_is_rejected_after_one_source_read(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()
        source_bundle = values["source_bundle"]
        artifacts = {
            key: copy.deepcopy(source_bundle[key])
            for key in (
                "initial_backend_snapshot",
                "initial_transaction_log_audit",
                "initial_prepared_catalog",
                "initial_resolved_catalog",
                "final_backend_snapshot",
                "final_transaction_log_audit",
                "final_prepared_catalog",
                "final_resolved_catalog",
            )
        }
        artifacts["initial_backend_snapshot"]["generation"] += 1
        source = reference_v1.InMemorySyntheticEvidenceReadPortV1(
            artifacts=artifacts,
            capability_probe=values["capability_probe"],
        )
        adapter = harness.make_synthetic_evidence_read_port_reference_adapter_v1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_read_port=source,
        )

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "SNAPSHOT_INVALID",
        ):
            adapter.read_backend_snapshot_offline(phase="INITIAL")

        self.assertEqual(source.counters()["snapshot"], 1)
        self.assertEqual(adapter.counters()["snapshot"], 0)
        self.assertFalse(adapter.completed)

    def test_source_instance_substitution_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()
        original = values["evidence_read_port"]
        substitute = reference_v1.InMemorySyntheticEvidenceReadPortV1(
            artifacts=copy.deepcopy(original._artifacts),
            capability_probe=copy.deepcopy(original._capability_probe),
        )
        adapter = adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1(
            protected_adapter_plan=values["protected_adapter_plan"],
            source_read_port=substitute,
            config=adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1(
                enabled=True,
                scope_attestation=(
                    adapter_v1.OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1
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
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "SOURCE_INSTANCE_PIN_MISMATCH",
        ):
            adapter.read_backend_snapshot_offline(phase="INITIAL")

        self.assertEqual(substitute.counters()["snapshot"], 0)

    def test_extra_read_after_completion_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_read_port_reference_adapter_context_v1()
        adapter = values["reference_adapter"]
        harness.collect_synthetic_read_port_artifacts_v1(adapter)

        with self.assertRaisesRegex(
            adapter_v1.StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1,
            "SEQUENCE_VIOLATION",
        ):
            adapter.read_backend_snapshot_offline(phase="INITIAL")

        self.assertEqual(sum(adapter.counters().values()), 9)

    def test_reference_adapter_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_evidence_read_port_reference_adapter_offline_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
