from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off schema must not inspect dependencies")


class ProductionStartupRecoveryEvidenceSchemaV1Tests(unittest.TestCase):
    def _define(self):
        values = harness.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
        result = values["schema_contract"].define_offline(
            protected_provider_binding=values["protected_identity_binding"]
        )
        return values, result

    def test_harness_defines_schema_without_operational_evidence(self) -> None:
        result = (
            harness.run_synthetic_production_startup_recovery_evidence_schema_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["prepared_and_resolved_schemas_defined"])
        self.assertEqual(result["pending_states"], ["PREPARED", "RESOLVED"])
        self.assertTrue(result["authenticated_proofs_required"])
        self.assertTrue(result["empirical_capability_probe_required"])
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["production_provider_instantiated"])
        self.assertFalse(result["production_provider_called"])
        self.assertFalse(result["production_backend_called"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_input_inspection(self) -> None:
        schema_contract = (
            contract.DormantProductionStartupRecoveryEvidenceSchemaContractV1()
        )

        result = schema_contract.define_offline(
            protected_provider_binding=_Explosive()
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_DEFAULT_OFF"],
        )
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["backend_called"])

    def test_wrong_provider_binding_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
        schema_contract = contract.DormantProductionStartupRecoveryEvidenceSchemaContractV1(
            config=contract.DormantProductionStartupRecoveryEvidenceSchemaConfigV1(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1
                ),
                expected_provider_binding_sha256="0" * 64,
            )
        )

        result = schema_contract.define_offline(
            protected_provider_binding=values["protected_identity_binding"]
        )

        self.assertFalse(result["ok"])
        self.assertIn(
            "PRODUCTION_STARTUP_RECOVERY_PROVIDER_BINDING_INVALID",
            result["reasons"],
        )
        self.assertFalse(result["schema_created"])

    def test_schema_is_hash_bound_and_tamper_evident(self) -> None:
        _values, result = self._define()
        protected = result["protected_schema"]

        self.assertTrue(
            contract.protected_production_startup_recovery_evidence_schema_valid_v1(
                protected
            )
        )
        tampered_schema = copy.deepcopy(protected.schema)
        tampered_schema["live_allowed"] = True
        tampered = contract.ProtectedProductionStartupRecoveryEvidenceSchemaV1(
            provider_binding_sha256=protected.provider_binding_sha256,
            backend_instance_sha256=protected.backend_instance_sha256,
            schema=tampered_schema,
            schema_sha256=protected.schema_sha256,
        )
        self.assertFalse(
            contract.protected_production_startup_recovery_evidence_schema_valid_v1(
                tampered
            )
        )

    def test_schema_requires_both_pending_catalogs_and_fresh_lease(self) -> None:
        _values, result = self._define()
        schema = result["protected_schema"].schema

        self.assertEqual(schema["pending_states"], ["PREPARED", "RESOLVED"])
        self.assertTrue(schema["prepared_and_resolved_catalogs_required"])
        self.assertTrue(schema["same_maintenance_epoch_instance_required"])
        self.assertTrue(schema["fresh_maintenance_epoch_required"])
        self.assertIn(
            "COMPLETE_RESOLVED_LEDGER_SCAN",
            schema["required_authenticated_proofs"],
        )
        self.assertIn(
            "UNKNOWN_WRITE_STATE_NEVER_GRANTS_READINESS",
            schema["safety_invariants"],
        )

    def test_schema_cannot_masquerade_as_runtime_evidence(self) -> None:
        _values, result = self._define()
        schema = result["protected_schema"].schema

        self.assertTrue(schema["schema_only"])
        self.assertFalse(schema["evidence_builder_available"])
        self.assertFalse(schema["production_authority"])
        self.assertFalse(schema["production_ready"])
        self.assertFalse(schema["runtime_integrated"])
        self.assertFalse(schema["recovery_execution_allowed"])
        self.assertFalse(schema["live_allowed"])
        self.assertTrue(schema["authenticated_verifier_required"])

    def test_protected_reprs_do_not_expose_hashes(self) -> None:
        values, result = self._define()

        self.assertEqual(
            repr(result["protected_schema"]),
            "ProtectedProductionStartupRecoveryEvidenceSchemaV1(<protected>)",
        )
        self.assertEqual(
            repr(values["schema_contract"]),
            "DormantProductionStartupRecoveryEvidenceSchemaContractV1(<protected>)",
        )

    def test_schema_contract_remains_absent_from_runtime_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_production_startup_recovery_evidence_schema_contract_v1",
            source,
        )
        self.assertNotIn(
            "run_synthetic_production_startup_recovery_evidence_schema_harness_v1",
            source,
        )


if __name__ == "__main__":
    unittest.main()
