from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off binding must not inspect dependencies")


class _UnscopedVerifier:
    def __init__(self) -> None:
        self.call_count = 0

    def verify_root_authority_signature_v2(self, **_kwargs) -> bool:
        self.call_count += 1
        return True


class StartupRecoveryAuthenticatedAuthorityBindingV1Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["binding_contract"].bind_offline(
            protected_evidence_schema=values["protected_schema"],
            recovery_identity=values["recovery_identity"],
            root_authority_attestation=values["root_authority_attestation"],
            root_authority_verifier=values["root_authority_verifier"],
            durable_authority_receipt=values["durable_authority_receipt"],
            now_epoch=values["now_epoch"],
        )

    def test_harness_binds_existing_crypto_without_production_authority(self) -> None:
        result = (
            harness.run_synthetic_startup_recovery_authenticated_authority_binding_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["root_signature_verifier_reused"])
        self.assertTrue(result["root_signature_verified"])
        self.assertTrue(result["identity_vector_verified"])
        self.assertTrue(result["cryptographic_contract_compatible"])
        self.assertFalse(result["startup_session_authority_scope_verified"])
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_any_input(self) -> None:
        binding_contract = (
            contract.DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1()
        )

        result = binding_contract.bind_offline(
            protected_evidence_schema=_Explosive(),
            recovery_identity=_Explosive(),
            root_authority_attestation=_Explosive(),
            root_authority_verifier=_Explosive(),
            durable_authority_receipt=_Explosive(),
            now_epoch=0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_DEFAULT_OFF"],
        )
        self.assertFalse(result["verifier_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_backend_identity_mismatch_fails_before_verifier(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        identity = copy.deepcopy(values["recovery_identity"])
        identity["backend_instance_sha256"] = "0" * 64
        identity["identity_sha256"] = (
            contract.startup_recovery_authority_identity_sha256_v1(identity)
        )
        values["recovery_identity"] = identity
        values["binding_contract"] = (
            harness.make_synthetic_authenticated_authority_binding_contract_v1(
                schema_sha256=values["protected_schema"].schema_sha256,
                root_authority_attestation_sha256=values[
                    "root_authority_attestation"
                ]["attestation_sha256"],
                durable_authority_receipt_sha256=values[
                    "durable_authority_receipt"
                ].receipt_sha256,
                recovery_identity_sha256=identity["identity_sha256"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RECOVERY_IDENTITY_VECTOR_NOT_PINNED"])
        self.assertFalse(result["verifier_called"])

    def test_authority_storage_mismatch_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        identity = copy.deepcopy(values["recovery_identity"])
        identity["authority_storage_binding_sha256"] = "1" * 64
        identity["identity_sha256"] = (
            contract.startup_recovery_authority_identity_sha256_v1(identity)
        )
        values["recovery_identity"] = identity
        values["binding_contract"] = (
            harness.make_synthetic_authenticated_authority_binding_contract_v1(
                schema_sha256=values["protected_schema"].schema_sha256,
                root_authority_attestation_sha256=values[
                    "root_authority_attestation"
                ]["attestation_sha256"],
                durable_authority_receipt_sha256=values[
                    "durable_authority_receipt"
                ].receipt_sha256,
                recovery_identity_sha256=identity["identity_sha256"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["ROOT_AUTHORITY_BINDING_INVALID"])
        self.assertFalse(result["verifier_called"])

    def test_forged_root_signature_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        root = copy.deepcopy(values["root_authority_attestation"])
        root["signature_sha256"] = "2" * 64
        root["attestation_sha256"] = (
            contract.authority_v2.authenticated_root_authority_attestation_sha256_v2(
                root
            )
        )
        receipt = values["durable_authority_receipt"]
        receipt_mapping = copy.deepcopy(receipt.receipt)
        receipt_mapping["root_authority_attestation_sha256"] = root[
            "attestation_sha256"
        ]
        receipt_mapping["receipt_sha256"] = (
            contract.authority_v2.durable_authority_receipt_sha256_v2(
                receipt_mapping
            )
        )
        forged_receipt = (
            contract.authority_v2.ProtectedDurableReconciliationAuthorityReceiptV2(
                record=receipt.record,
                receipt=receipt_mapping,
                receipt_sha256=receipt_mapping["receipt_sha256"],
            )
        )
        values["root_authority_attestation"] = root
        values["durable_authority_receipt"] = forged_receipt
        values["binding_contract"] = (
            harness.make_synthetic_authenticated_authority_binding_contract_v1(
                schema_sha256=values["protected_schema"].schema_sha256,
                root_authority_attestation_sha256=root["attestation_sha256"],
                durable_authority_receipt_sha256=forged_receipt.receipt_sha256,
                recovery_identity_sha256=values["recovery_identity"][
                    "identity_sha256"
                ],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["ROOT_AUTHORITY_SIGNATURE_INVALID"])
        self.assertTrue(result["verifier_called"])
        self.assertEqual(values["root_authority_verifier"].call_count, 1)

    def test_unscoped_verifier_is_never_called(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        verifier = _UnscopedVerifier()
        values["root_authority_verifier"] = verifier

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["OFFLINE_ROOT_AUTHORITY_VERIFIER_REQUIRED"]
        )
        self.assertFalse(result["verifier_called"])
        self.assertEqual(verifier.call_count, 0)

    def test_expired_authority_projection_fails_before_signature_check(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        values["now_epoch"] = 2_001

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["DURABLE_AUTHORITY_ISSUED_PROJECTION_NOT_CURRENT"],
        )
        self.assertFalse(result["verifier_called"])

    def test_protected_binding_rejects_resealed_live_claim(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        result = self._bind(values)
        protected = result["protected_binding"]
        tampered_binding = copy.deepcopy(protected.binding)
        tampered_binding["live_allowed"] = True
        tampered_binding["binding_sha256"] = (
            contract.startup_recovery_authenticated_authority_binding_sha256_v1(
                tampered_binding
            )
        )
        tampered = contract.ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1(
            schema_sha256=protected.schema_sha256,
            durable_authority_receipt_sha256=(
                protected.durable_authority_receipt_sha256
            ),
            backend_instance_sha256=protected.backend_instance_sha256,
            binding=tampered_binding,
            binding_sha256=tampered_binding["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_authenticated_authority_binding_valid_v1(
                tampered
            )
        )

    def test_candidate_receipt_is_not_promoted_to_startup_authority(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        result = self._bind(values)
        binding = result["protected_binding"].binding

        self.assertEqual(
            binding["candidate_authenticated_authority_receipt_sha256"],
            values["durable_authority_receipt"].receipt_sha256,
        )
        self.assertEqual(
            binding["authenticated_authority_schema_field"],
            "authenticated_authority_receipt_sha256",
        )
        self.assertFalse(binding["startup_session_authority_scope_verified"])
        self.assertFalse(binding["evidence_population_allowed"])
        self.assertIn(
            "STARTUP_SESSION_AUTHORITY_SCOPE_NOT_PROVEN",
            binding["production_blockers"],
        )

    def test_protected_reprs_hide_binding_details(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_authenticated_authority_binding_context_v1()
        )
        result = self._bind(values)

        self.assertEqual(
            repr(result["protected_binding"]),
            "ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1(<protected>)",
        )
        self.assertEqual(
            repr(values["binding_contract"]),
            "DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1(<protected>)",
        )
        self.assertEqual(
            repr(values["root_authority_verifier"]),
            "SyntheticOfflineRootAuthorityVerifierV1(<protected>)",
        )

    def test_binding_remains_absent_from_runtime_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_production_startup_recovery_authenticated_authority_binding_contract_v1",
            source,
        )
        self.assertNotIn(
            "run_synthetic_startup_recovery_authenticated_authority_binding_harness_v1",
            source,
        )


if __name__ == "__main__":
    unittest.main()
