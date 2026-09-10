from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off store contract must not inspect inputs")


class ProductionResolvedAuthorityStoreContractOfflineV2Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["store_contract"].bind_offline(
            authenticated_authority_binding=values["authenticated_binding"],
            multistore_lease_binding=values["multistore_binding"],
            resolved_lock_port_projection=values["resolved_projection"],
        )

    @staticmethod
    def _store_contract(values, *, multistore_binding=None):
        selected = multistore_binding or values["multistore_binding"]
        return contract.DormantProductionResolvedAuthorityStoreContractV2(
            contract.DormantProductionResolvedAuthorityStoreConfigV2(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2
                ),
                expected_authenticated_binding_sha256=(
                    values["authenticated_binding"].binding_sha256
                ),
                expected_multistore_binding_sha256=selected.binding_sha256,
                expected_resolved_projection_sha256=(
                    values["resolved_projection"].projection_sha256
                ),
                expected_authenticated_binding_object_identity_sha256=(
                    identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        values["authenticated_binding"]
                    )
                ),
                expected_multistore_binding_object_identity_sha256=(
                    identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        selected
                    )
                ),
                expected_resolved_projection_object_identity_sha256=(
                    identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        values["resolved_projection"]
                    )
                ),
            )
        )

    def test_harness_binds_authenticated_root_rotation_and_recovery(self) -> None:
        result = (
            harness.run_production_resolved_authority_store_contract_offline_harness_v2()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["authenticated_root_evidence_verified"])
        self.assertTrue(result["rotation_recovery_requirements_verified"])
        self.assertTrue(result["multistore_cross_binding_verified"])
        self.assertFalse(result["physical_store_implementation_bound"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_returns_before_input_inspection(self) -> None:
        store = contract.DormantProductionResolvedAuthorityStoreContractV2()

        result = store.bind_offline(
            authenticated_authority_binding=_Explosive(),
            multistore_lease_binding=_Explosive(),
            resolved_lock_port_projection=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_DEFAULT_OFF",
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_same_authenticated_binding_instance_is_required(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        original = values["authenticated_binding"]
        reconstructed = type(original)(
            schema_sha256=original.schema_sha256,
            durable_authority_receipt_sha256=(
                original.durable_authority_receipt_sha256
            ),
            backend_instance_sha256=original.backend_instance_sha256,
            binding=copy.deepcopy(dict(original.binding)),
            binding_sha256=original.binding_sha256,
        )

        result = values["store_contract"].bind_offline(
            authenticated_authority_binding=reconstructed,
            multistore_lease_binding=values["multistore_binding"],
            resolved_lock_port_projection=values["resolved_projection"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_RESOLVED_AUTHORITY_STORE_INSTANCE_OR_PIN_MISMATCH",
        )

    def test_same_resolved_projection_instance_is_required(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        original = values["resolved_projection"]
        reconstructed = type(original)(
            port_role=original.port_role,
            store_identity_sha256=original.store_identity_sha256,
            projection=copy.deepcopy(dict(original.projection)),
            projection_sha256=original.projection_sha256,
        )

        result = values["store_contract"].bind_offline(
            authenticated_authority_binding=values["authenticated_binding"],
            multistore_lease_binding=values["multistore_binding"],
            resolved_lock_port_projection=reconstructed,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_RESOLVED_AUTHORITY_STORE_INSTANCE_OR_PIN_MISMATCH",
        )

    def test_storage_binding_mismatch_fails_cross_binding(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        original = values["multistore_binding"]
        payload = copy.deepcopy(dict(original.binding))
        payload["resolved_authority_store_storage_binding_sha256"] = (
            harness.multistore_harness_v2._sha("mismatched-resolved-storage")
        )
        payload["binding_sha256"] = (
            multistore_v2.production_multistore_observation_lease_binding_sha256_v2(
                payload
            )
        )
        tampered = multistore_v2.ProtectedProductionMultistoreObservationLeaseBindingV2(
            transaction_store_projection_sha256=(
                original.transaction_store_projection_sha256
            ),
            resolved_authority_store_projection_sha256=(
                original.resolved_authority_store_projection_sha256
            ),
            binding=payload,
            binding_sha256=payload["binding_sha256"],
        )
        self.assertTrue(
            multistore_v2.protected_production_multistore_observation_lease_binding_valid_v2(
                tampered
            )
        )
        store = self._store_contract(values, multistore_binding=tampered)

        result = store.bind_offline(
            authenticated_authority_binding=values["authenticated_binding"],
            multistore_lease_binding=tampered,
            resolved_lock_port_projection=values["resolved_projection"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_RESOLVED_AUTHORITY_STORE_CROSS_BINDING_INVALID",
        )

    def test_resealed_open_permission_is_rejected(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        result = self._bind(values)
        original = result["protected_binding"]
        payload = copy.deepcopy(dict(original.binding))
        payload["store_open_allowed"] = True
        payload["binding_sha256"] = (
            contract.production_resolved_authority_store_binding_sha256_v2(payload)
        )
        tampered = contract.ProtectedProductionResolvedAuthorityStoreBindingV2(
            authenticated_authority_binding_sha256=(
                original.authenticated_authority_binding_sha256
            ),
            multistore_lease_binding_sha256=(
                original.multistore_lease_binding_sha256
            ),
            resolved_lock_port_projection_sha256=(
                original.resolved_lock_port_projection_sha256
            ),
            binding=payload,
            binding_sha256=payload["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_production_resolved_authority_store_binding_valid_v2(
                tampered
            )
        )

    def test_root_epoch_requires_previous_attestation_chain(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        result = self._bind(values)
        original = result["protected_binding"]
        payload = copy.deepcopy(dict(original.binding))
        payload["root_authority_key_epoch"] = 1
        payload["binding_sha256"] = (
            contract.production_resolved_authority_store_binding_sha256_v2(payload)
        )
        tampered = contract.ProtectedProductionResolvedAuthorityStoreBindingV2(
            authenticated_authority_binding_sha256=(
                original.authenticated_authority_binding_sha256
            ),
            multistore_lease_binding_sha256=(
                original.multistore_lease_binding_sha256
            ),
            resolved_lock_port_projection_sha256=(
                original.resolved_lock_port_projection_sha256
            ),
            binding=payload,
            binding_sha256=payload["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_production_resolved_authority_store_binding_valid_v2(
                tampered
            )
        )

    def test_contract_requires_full_durability_and_recovery_vector(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        result = self._bind(values)
        binding = dict(result["protected_binding"].binding)

        for field in (
            "snapshot_required",
            "append_only_journal_required",
            "write_ahead_log_required",
            "backup_required",
            "cross_process_lock_required",
            "atomic_replace_required",
            "directory_fsync_required",
            "crash_recovery_required",
            "interrupted_rotation_recovery_required",
            "corruption_fails_closed",
            "unresolved_transactions_block_readiness",
        ):
            self.assertTrue(binding[field], field)

    def test_protected_binding_repr_does_not_disclose_root_or_storage(self) -> None:
        values = harness.build_production_resolved_authority_store_context_v2()
        result = self._bind(values)

        self.assertEqual(
            repr(result["protected_binding"]),
            "ProtectedProductionResolvedAuthorityStoreBindingV2(<protected>)",
        )

    def test_store_surfaces_are_absent_and_module_is_not_in_runtime(self) -> None:
        store_type = contract.DormantProductionResolvedAuthorityStoreContractV2
        for name in ("open", "read", "write", "rotate", "recover"):
            self.assertFalse(hasattr(store_type, name), name)
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "production_resolved_authority_store_contract_offline_v2",
            main_source,
        )
        self.assertNotIn(
            "DormantProductionResolvedAuthorityStoreContractV2", main_source
        )


if __name__ == "__main__":
    unittest.main()
