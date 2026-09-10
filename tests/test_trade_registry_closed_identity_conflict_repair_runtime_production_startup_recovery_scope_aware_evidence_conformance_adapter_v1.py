from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off adapter must not inspect dependencies")


class _FakeValidator:
    def __init__(self) -> None:
        self.called = False

    def audit_offline(self, **_kwargs):
        self.called = True
        raise AssertionError("unapproved validator must never be called")


class StartupRecoveryScopeAwareEvidenceConformanceAdapterV1Tests(
    unittest.TestCase
):
    @staticmethod
    def _audit(values):
        return values["adapter"].audit_offline(
            protected_scope_binding=values["protected_scope_binding"],
            fixture_bundle=values["fixture_bundle"],
            conformance_validator=values["conformance_validator"],
        )

    @staticmethod
    def _repin_bundle(values, bundle):
        bundle["bundle_sha256"] = (
            contract.conformance_v1.synthetic_evidence_bundle_sha256_v1(bundle)
        )
        values["fixture_bundle"] = bundle
        values["adapter"] = harness.make_synthetic_scope_aware_adapter_v1(
            scope_binding_sha256=values[
                "protected_scope_binding"
            ].binding_sha256,
            bundle_sha256=bundle["bundle_sha256"],
        )

    def test_harness_requires_exact_scope_before_delegate(self) -> None:
        result = harness.run_synthetic_scope_aware_evidence_conformance_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["scope_cross_binding_verified"])
        self.assertTrue(result["delegate_conformance_verified"])
        self.assertEqual(result["pending_item_count"], 1)
        self.assertTrue(result["upstream_temporary_storage_removed"])
        self.assertFalse(result["production_evidence_created"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_dependencies(self) -> None:
        adapter = (
            contract.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1()
        )

        result = adapter.audit_offline(
            protected_scope_binding=_Explosive(),
            fixture_bundle=_Explosive(),
            conformance_validator=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SCOPE_AWARE_EVIDENCE_CONFORMANCE_DEFAULT_OFF"]
        )
        self.assertFalse(result["delegate_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_rehashed_different_maintenance_epoch_fails_before_delegate(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["completion_attestation"]["maintenance_epoch"] = "a" * 64
        self._repin_bundle(values, bundle)

        result = self._audit(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SCOPE_TO_EVIDENCE_CROSS_BINDING_INVALID"]
        )
        self.assertFalse(result["delegate_called"])

    def test_rehashed_missing_terminal_receipt_fails_before_delegate(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["terminal_receipts"].clear()
        self._repin_bundle(values, bundle)

        result = self._audit(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SCOPE_TO_EVIDENCE_CROSS_BINDING_INVALID"]
        )
        self.assertFalse(result["delegate_called"])

    def test_rehashed_wrong_authority_receipt_fails_before_delegate(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["terminal_receipts"][0][
            "authenticated_authority_receipt_sha256"
        ] = "b" * 64
        self._repin_bundle(values, bundle)

        result = self._audit(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SCOPE_TO_EVIDENCE_CROSS_BINDING_INVALID"]
        )
        self.assertFalse(result["delegate_called"])

    def test_unapproved_validator_type_is_never_called(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        fake = _FakeValidator()
        values["conformance_validator"] = fake

        result = self._audit(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["OFFLINE_CONFORMANCE_VALIDATOR_INVALID"])
        self.assertFalse(result["delegate_called"])
        self.assertFalse(fake.called)

    def test_default_off_delegate_fails_closed_without_protected_receipt(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        values["conformance_validator"] = (
            contract.conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceV1()
        )

        result = self._audit(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["DELEGATE_CONFORMANCE_FAILED_CLOSED"])
        self.assertTrue(result["delegate_called"])
        self.assertFalse(result["delegate_conformance_verified"])
        self.assertIsNone(result["protected_conformance"])

    def test_protected_receipt_rejects_resealed_live_claim(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        result = self._audit(values)
        protected = result["protected_conformance"]
        receipt = copy.deepcopy(protected.receipt)
        receipt["live_allowed"] = True
        receipt["receipt_sha256"] = (
            contract.startup_recovery_scope_aware_conformance_receipt_sha256_v1(
                receipt
            )
        )
        tampered = contract.ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1(
            protected_scope_binding=protected.protected_scope_binding,
            fixture_bundle=protected.fixture_bundle,
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
                tampered
            )
        )

    def test_protected_receipt_independently_rejects_nonconforming_bundle(self) -> None:
        values = harness.build_synthetic_scope_aware_evidence_conformance_context_v1()
        result = self._audit(values)
        protected = result["protected_conformance"]
        bundle = copy.deepcopy(protected.fixture_bundle)
        bundle["completion_attestation"]["all_catalogs_drained"] = False
        bundle["bundle_sha256"] = (
            contract.conformance_v1.synthetic_evidence_bundle_sha256_v1(bundle)
        )
        receipt = copy.deepcopy(protected.receipt)
        receipt["bundle_sha256"] = bundle["bundle_sha256"]
        receipt["receipt_sha256"] = (
            contract.startup_recovery_scope_aware_conformance_receipt_sha256_v1(
                receipt
            )
        )
        forged = contract.ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1(
            protected_scope_binding=protected.protected_scope_binding,
            fixture_bundle=bundle,
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
                forged
            )
        )

    def test_contract_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_scope_aware_evidence_conformance_"
            "adapter_contract_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
