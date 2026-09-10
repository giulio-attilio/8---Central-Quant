from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off validator must not inspect inputs")


class ProductionStartupRecoveryEvidenceConformanceV1Tests(unittest.TestCase):
    def test_complete_synthetic_bundle_conforms_but_is_not_admissible(self) -> None:
        result = harness.run_synthetic_production_startup_recovery_evidence_conformance_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["schema_conforms"])
        self.assertEqual(result["prepared_before"], 2)
        self.assertEqual(result["resolved_before"], 1)
        self.assertEqual(result["unresolved_after"], 0)
        self.assertFalse(result["production_admissible"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertFalse(result["production_provider_instantiated"])
        self.assertFalse(result["production_backend_called"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["real_registry_accessed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_input_inspection(self) -> None:
        validator = contract.OfflineProductionStartupRecoveryEvidenceConformanceV1()

        result = validator.audit_offline(
            protected_schema=_Explosive(), fixture_bundle=_Explosive()
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["PRODUCTION_RECOVERY_EVIDENCE_CONFORMANCE_DEFAULT_OFF"],
        )

    def test_wrong_schema_pin_fails_before_bundle_inspection(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        validator = contract.OfflineProductionStartupRecoveryEvidenceConformanceV1(
            config=contract.OfflineProductionStartupRecoveryEvidenceConformanceConfigV1(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
                ),
                expected_schema_sha256="0" * 64,
            )
        )

        result = validator.audit_offline(
            protected_schema=values["protected_schema"],
            fixture_bundle=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_RECOVERY_EVIDENCE_SCHEMA_INVALID"]
        )

    def test_tampered_wal_count_is_rejected(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["initial_transaction_log_audit"]["wal_record_count"] += 1
        bundle["initial_transaction_log_audit"]["audit_sha256"] = (
            contract.synthetic_transaction_log_audit_sha256_v1(
                bundle["initial_transaction_log_audit"]
            )
        )
        bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
            bundle
        )

        result = values["validator"].audit_offline(
            protected_schema=values["protected_schema"], fixture_bundle=bundle
        )

        self.assertFalse(result["ok"])
        self.assertIn("INITIAL_SYNTHETIC_EVIDENCE_INVALID", result["reasons"])

    def test_missing_terminal_receipt_is_rejected(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["terminal_receipts"].pop()
        bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
            bundle
        )

        result = values["validator"].audit_offline(
            protected_schema=values["protected_schema"], fixture_bundle=bundle
        )

        self.assertFalse(result["ok"])
        self.assertIn("TERMINAL_RECEIPT_SET_INVALID", result["reasons"])

    def test_rehashed_stale_maintenance_epoch_receipt_is_rejected(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        receipt = bundle["terminal_receipts"][0]
        receipt["previous_maintenance_epoch"] = receipt["maintenance_epoch"]
        receipt["receipt_sha256"] = contract.synthetic_terminal_receipt_sha256_v1(
            receipt
        )
        bundle["terminal_receipts"].sort(
            key=lambda item: item["receipt_sha256"]
        )
        completion = bundle["completion_attestation"]
        completion["terminal_receipt_set_sha256"] = (
            contract.synthetic_terminal_receipt_set_sha256_v1(
                bundle["terminal_receipts"]
            )
        )
        completion["startup_recovery_attestation_sha256"] = (
            contract.synthetic_completion_attestation_sha256_v1(completion)
        )
        bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
            bundle
        )

        result = values["validator"].audit_offline(
            protected_schema=values["protected_schema"], fixture_bundle=bundle
        )

        self.assertFalse(result["ok"])
        self.assertIn("TERMINAL_RECEIPT_SET_INVALID", result["reasons"])

    def test_rehashed_production_claim_is_rejected_semantically(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["production_evidence"] = True
        bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
            bundle
        )

        result = values["validator"].audit_offline(
            protected_schema=values["protected_schema"], fixture_bundle=bundle
        )

        self.assertFalse(result["ok"])
        self.assertIn("SYNTHETIC_FIXTURE_SAFETY_VECTOR_INVALID", result["reasons"])
        self.assertFalse(result["production_admissible"])

    def test_final_resolved_catalog_cannot_remain_nonempty(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()
        bundle = copy.deepcopy(values["fixture_bundle"])
        bundle["completion_attestation"]["resolved_transactions_after"] = 1
        bundle["completion_attestation"]["unresolved_transactions_after"] = 1
        bundle["completion_attestation"]["startup_recovery_attestation_sha256"] = (
            contract.synthetic_completion_attestation_sha256_v1(
                bundle["completion_attestation"]
            )
        )
        bundle["bundle_sha256"] = contract.synthetic_evidence_bundle_sha256_v1(
            bundle
        )

        result = values["validator"].audit_offline(
            protected_schema=values["protected_schema"], fixture_bundle=bundle
        )

        self.assertFalse(result["ok"])
        self.assertIn("SYNTHETIC_EVIDENCE_CROSS_BINDING_INVALID", result["reasons"])

    def test_validator_repr_is_protected(self) -> None:
        values = harness.build_synthetic_production_startup_recovery_evidence_conformance_context_v1()

        self.assertEqual(
            repr(values["validator"]),
            "OfflineProductionStartupRecoveryEvidenceConformanceV1(<protected>)",
        )

    def test_conformance_contract_remains_absent_from_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_production_startup_recovery_evidence_conformance_contract_v1",
            source,
        )
        self.assertNotIn(
            "run_synthetic_production_startup_recovery_evidence_conformance_harness_v1",
            source,
        )


if __name__ == "__main__":
    unittest.main()
