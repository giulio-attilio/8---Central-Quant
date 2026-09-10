from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off contract must not inspect dependencies")


class StartupRecoveryBatchSessionAuthorityV1Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["batch_contract"].bind_offline(
            protected_authenticated_authority_binding=values[
                "protected_authenticated_binding"
            ],
            protected_restart_admissions=values["protected_restart_admissions"],
            pending_states_by_transaction=values[
                "pending_states_by_transaction"
            ],
            now_epoch=values["now_epoch"],
        )

    def test_harness_binds_one_synthetic_batch_session_without_authority(self) -> None:
        result = (
            harness.run_synthetic_startup_recovery_batch_session_authority_harness_v1()
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["pending_item_count"], 1)
        self.assertTrue(result["same_session_identity_verified"])
        self.assertTrue(result["same_backend_path_lock_epoch_verified"])
        self.assertTrue(result["upstream_temporary_storage_accessed"])
        self.assertTrue(result["upstream_temporary_storage_removed"])
        self.assertFalse(result["batch_contract_filesystem_accessed"])
        self.assertTrue(result["live_lease_revalidation_required"])
        self.assertTrue(result["durable_current_state_revalidation_required"])
        self.assertFalse(result["recovery_authority_granted"])
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["production_authority"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_any_input(self) -> None:
        dormant = contract.DormantStartupRecoveryBatchSessionAuthorityContractV1()

        result = dormant.bind_offline(
            protected_authenticated_authority_binding=_Explosive(),
            protected_restart_admissions=_Explosive(),
            pending_states_by_transaction=_Explosive(),
            now_epoch=0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_DEFAULT_OFF"],
        )
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["backend_called"])

    def test_duplicate_pending_transaction_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        admission = values["protected_restart_admissions"][0]
        values["protected_restart_admissions"] = (admission, admission)
        values["batch_contract"] = harness.make_synthetic_batch_session_contract_v1(
            authenticated_authority_binding_sha256=values[
                "protected_authenticated_binding"
            ].binding_sha256,
            pending_catalog_binding_sha256=values[
                "pending_catalog_binding_sha256"
            ],
            pending_item_count=2,
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["DUPLICATE_PENDING_TRANSACTION"])
        self.assertIsNone(result["protected_batch_session"])
        self.assertFalse(result["write_executed"])

    def test_incomplete_pending_state_map_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        values["pending_states_by_transaction"] = {}

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PENDING_STATE_BINDING_INVALID"])
        self.assertFalse(result["batch_session_bound"])

    def test_expired_admission_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        values["now_epoch"] = values["protected_restart_admissions"][0].admission[
            "expires_at_epoch"
        ]

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["BATCH_SESSION_INSTANCE_OR_IDENTITY_MISMATCH"],
        )
        self.assertFalse(result["recovery_authority_granted"])

    def test_pending_catalog_pin_mismatch_fails_closed(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        values["batch_contract"] = harness.make_synthetic_batch_session_contract_v1(
            authenticated_authority_binding_sha256=values[
                "protected_authenticated_binding"
            ].binding_sha256,
            pending_catalog_binding_sha256="f" * 64,
            pending_item_count=1,
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PENDING_CATALOG_BINDING_PIN_MISMATCH"]
        )
        self.assertFalse(result["batch_session_bound"])

    def test_protected_receipt_rejects_resealed_live_claim(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        result = self._bind(values)
        protected = result["protected_batch_session"]
        tampered_receipt = copy.deepcopy(protected.receipt)
        tampered_receipt["live_allowed"] = True
        tampered_receipt["receipt_sha256"] = (
            contract.startup_recovery_batch_session_authority_receipt_sha256_v1(
                tampered_receipt
            )
        )
        tampered = contract.ProtectedStartupRecoveryBatchSessionAuthorityV1(
            authenticated_authority_binding=protected.authenticated_authority_binding,
            protected_restart_admissions=protected.protected_restart_admissions,
            receipt=tampered_receipt,
            receipt_sha256=tampered_receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_batch_session_authority_valid_v1(
                tampered
            )
        )

    def test_receipt_is_explicitly_non_authoritative_and_protected(self) -> None:
        values = (
            harness.build_synthetic_startup_recovery_batch_session_authority_context_v1()
        )
        result = self._bind(values)
        protected = result["protected_batch_session"]
        receipt = protected.receipt

        self.assertTrue(
            contract.protected_startup_recovery_batch_session_authority_valid_v1(
                protected
            )
        )
        self.assertEqual(
            repr(protected),
            "ProtectedStartupRecoveryBatchSessionAuthorityV1(<protected>)",
        )
        self.assertTrue(receipt["synthetic_only"])
        self.assertFalse(receipt["production_root_authority_verified"])
        self.assertFalse(receipt["complete_catalog_evidence_created"])
        self.assertFalse(receipt["evidence_population_allowed"])
        self.assertFalse(receipt["recovery_execution_allowed"])
        self.assertIn(
            "LIVE_LEASE_NOT_REVALIDATED_AT_BATCH_BOUNDARY",
            receipt["production_blockers"],
        )

    def test_contract_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_batch_session_authority_contract_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn("ProtectedStartupRecoveryBatchSessionAuthorityV1", main_source)


if __name__ == "__main__":
    unittest.main()
