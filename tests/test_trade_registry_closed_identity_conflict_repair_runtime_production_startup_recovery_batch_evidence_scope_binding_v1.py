from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1 as schema_harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off binding must not inspect dependencies")


class StartupRecoveryBatchEvidenceScopeBindingV1Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["scope_contract"].bind_offline(
            protected_batch_session=values["protected_batch_session"],
            protected_evidence_schema=values["protected_schema"],
        )

    def test_harness_binds_scope_without_building_evidence(self) -> None:
        result = (
            harness.run_synthetic_startup_recovery_batch_evidence_scope_binding_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pending_item_count"], 1)
        self.assertTrue(result["batch_scope_bound"])
        self.assertTrue(result["exact_maintenance_identity_required"])
        self.assertTrue(
            result["exact_catalog_and_authority_crosscheck_required"]
        )
        self.assertTrue(result["upstream_temporary_storage_accessed"])
        self.assertTrue(result["upstream_temporary_storage_removed"])
        self.assertFalse(result["scope_contract_filesystem_accessed"])
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["evidence_builder_called"])
        self.assertFalse(result["evidence_population_allowed"])
        self.assertFalse(result["recovery_authority_granted"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_dependencies(self) -> None:
        dormant = (
            contract.DormantStartupRecoveryBatchEvidenceScopeBindingContractV1()
        )

        result = dormant.bind_offline(
            protected_batch_session=_Explosive(),
            protected_evidence_schema=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_DEFAULT_OFF"],
        )
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["backend_called"])

    def test_valid_but_different_schema_identity_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
        )
        different = (
            schema_harness.build_synthetic_production_startup_recovery_evidence_schema_context_v1()
        )
        different_result = different["schema_contract"].define_offline(
            protected_provider_binding=different["protected_identity_binding"]
        )
        different_schema = different_result["protected_schema"]
        values["protected_schema"] = different_schema
        values["scope_contract"] = (
            harness.make_synthetic_batch_evidence_scope_binding_contract_v1(
                batch_session_receipt_sha256=values[
                    "protected_batch_session"
                ].receipt_sha256,
                schema_sha256=different_schema.schema_sha256,
                pending_catalog_binding_sha256=values[
                    "protected_batch_session"
                ].receipt["pending_catalog_binding_sha256"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["BATCH_SCHEMA_IDENTITY_MISMATCH"])
        self.assertFalse(result["batch_scope_bound"])
        self.assertFalse(result["evidence_created"])

    def test_pending_catalog_pin_mismatch_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
        )
        values["scope_contract"] = (
            harness.make_synthetic_batch_evidence_scope_binding_contract_v1(
                batch_session_receipt_sha256=values[
                    "protected_batch_session"
                ].receipt_sha256,
                schema_sha256=values["protected_schema"].schema_sha256,
                pending_catalog_binding_sha256="e" * 64,
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PENDING_CATALOG_BINDING_PIN_MISMATCH"]
        )
        self.assertFalse(result["identity_vector_verified"])

    def test_invalid_batch_session_is_rejected_before_schema_use(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
        )
        protected = values["protected_batch_session"]
        tampered_receipt = copy.deepcopy(protected.receipt)
        tampered_receipt["maintenance_epoch"] = "d" * 64
        tampered_receipt["receipt_sha256"] = (
            contract.batch_authority_v1.startup_recovery_batch_session_authority_receipt_sha256_v1(
                tampered_receipt
            )
        )
        tampered = contract.batch_authority_v1.ProtectedStartupRecoveryBatchSessionAuthorityV1(
            authenticated_authority_binding=protected.authenticated_authority_binding,
            protected_restart_admissions=protected.protected_restart_admissions,
            receipt=tampered_receipt,
            receipt_sha256=tampered_receipt["receipt_sha256"],
        )
        values["protected_batch_session"] = tampered
        values["scope_contract"] = (
            harness.make_synthetic_batch_evidence_scope_binding_contract_v1(
                batch_session_receipt_sha256=tampered.receipt_sha256,
                schema_sha256=values["protected_schema"].schema_sha256,
                pending_catalog_binding_sha256=tampered.receipt[
                    "pending_catalog_binding_sha256"
                ],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PROTECTED_BATCH_SESSION_INVALID"])
        self.assertFalse(result["evidence_schema_verified"])

    def test_protected_binding_rejects_resealed_evidence_claim(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
        )
        result = self._bind(values)
        protected = result["protected_scope_binding"]
        tampered_binding = copy.deepcopy(protected.binding)
        tampered_binding["evidence_created"] = True
        tampered_binding["binding_sha256"] = (
            contract.startup_recovery_batch_evidence_scope_binding_sha256_v1(
                tampered_binding
            )
        )
        tampered = contract.ProtectedStartupRecoveryBatchEvidenceScopeBindingV1(
            protected_batch_session=protected.protected_batch_session,
            protected_evidence_schema=protected.protected_evidence_schema,
            binding=tampered_binding,
            binding_sha256=tampered_binding["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                tampered
            )
        )

    def test_binding_pins_exact_candidate_authority_and_catalog(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_evidence_scope_binding_context_v1()
        )
        result = self._bind(values)
        protected = result["protected_scope_binding"]
        binding = protected.binding
        batch_receipt = values["protected_batch_session"].receipt
        authenticated = values[
            "protected_batch_session"
        ].authenticated_authority_binding.binding

        self.assertTrue(
            contract.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                protected
            )
        )
        self.assertEqual(
            binding["candidate_authenticated_authority_receipt_sha256"],
            authenticated["candidate_authenticated_authority_receipt_sha256"],
        )
        self.assertEqual(
            binding["candidate_maintenance_lease_receipt_sha256"],
            batch_receipt["candidate_maintenance_lease_receipt_sha256"],
        )
        self.assertEqual(
            binding["pending_catalog_binding_sha256"],
            batch_receipt["pending_catalog_binding_sha256"],
        )
        self.assertEqual(
            repr(protected),
            "ProtectedStartupRecoveryBatchEvidenceScopeBindingV1(<protected>)",
        )

    def test_contract_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_batch_evidence_scope_binding_contract_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "ProtectedStartupRecoveryBatchEvidenceScopeBindingV1", main_source
        )


if __name__ == "__main__":
    unittest.main()
