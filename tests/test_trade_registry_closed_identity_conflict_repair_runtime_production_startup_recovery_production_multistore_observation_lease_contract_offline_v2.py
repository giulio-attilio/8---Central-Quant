from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off contract must not inspect projections")


class ProductionMultistoreObservationLeaseContractOfflineV2Tests(
    unittest.TestCase
):
    def test_harness_binds_two_persistent_lock_requirements_offline(self) -> None:
        result = (
            harness.run_production_multistore_observation_lease_contract_offline_harness_v2()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["two_persistent_lock_ports_required"])
        self.assertTrue(result["acquisition_surface_absent"])
        self.assertFalse(result["production_lock_ports_bound"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["live_allowed"])

    def test_binding_requires_exact_order_and_same_lease_authority(self) -> None:
        transaction, resolved = (
            harness.build_synthetic_production_lock_port_projections_v2()
        )
        binder = harness.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=transaction,
            resolved_projection=resolved,
        )

        result = binder.bind_offline(
            transaction_store_lock_port=transaction,
            resolved_authority_store_lock_port=resolved,
        )
        binding = dict(result["protected_binding"].binding)

        self.assertEqual(binding["lock_order"], list(contract.LOCK_ORDER_V2))
        self.assertEqual(binding["required_lock_count"], 2)
        self.assertEqual(binding["required_writer_count"], 19)
        self.assertEqual(binding["max_lease_ttl_seconds"], 300)
        self.assertEqual(binding["max_lock_acquire_timeout_seconds"], 1)
        self.assertTrue(binding["same_lease_instance_required"])
        self.assertTrue(binding["same_authenticated_authority_instance_required"])
        self.assertTrue(binding["same_writer_coordinator_instance_required"])
        self.assertTrue(binding["maintenance_lease_required"])
        self.assertTrue(binding["pending_transaction_recovery_required_before_readiness"])
        self.assertTrue(binding["all_reads_token_gated_required"])
        self.assertTrue(binding["reverse_order_release_required"])

    def test_default_off_does_not_inspect_inputs(self) -> None:
        binder = contract.DormantProductionMultistoreObservationLeaseContractV2()

        result = binder.bind_offline(
            transaction_store_lock_port=_Explosive(),
            resolved_authority_store_lock_port=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PRODUCTION_MULTISTORE_LEASE_CONTRACT_DEFAULT_OFF"
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_same_lock_namespace_is_rejected(self) -> None:
        transaction, _ = harness.build_synthetic_production_lock_port_projections_v2()
        transaction_projection = dict(transaction.projection)
        resolved = contract.build_production_store_lock_port_projection_offline_v2(
            port_role=contract.RESOLVED_AUTHORITY_STORE_ROLE_V2,
            source_contract_version=(
                contract.EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
            ),
            store_identity_sha256=harness._sha("separate-resolved-identity"),
            storage_binding_sha256=harness._sha("separate-resolved-storage"),
            lock_namespace_sha256=transaction_projection["lock_namespace_sha256"],
        )
        binder = harness.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=transaction,
            resolved_projection=resolved,
        )

        result = binder.bind_offline(
            transaction_store_lock_port=transaction,
            resolved_authority_store_lock_port=resolved,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_MULTISTORE_LOCK_PORT_CROSS_BINDING_INVALID",
        )

    def test_swapped_store_roles_are_rejected(self) -> None:
        transaction, resolved = (
            harness.build_synthetic_production_lock_port_projections_v2()
        )
        binder = harness.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=resolved,
            resolved_projection=transaction,
        )

        result = binder.bind_offline(
            transaction_store_lock_port=resolved,
            resolved_authority_store_lock_port=transaction,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_MULTISTORE_LOCK_PORT_CROSS_BINDING_INVALID",
        )

    def test_projection_pin_mismatch_fails_closed(self) -> None:
        transaction, resolved = (
            harness.build_synthetic_production_lock_port_projections_v2()
        )
        binder = contract.DormantProductionMultistoreObservationLeaseContractV2(
            contract.DormantProductionMultistoreObservationLeaseConfigV2(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
                ),
                expected_transaction_store_projection_sha256=harness._sha(
                    "wrong-transaction-pin"
                ),
                expected_resolved_authority_store_projection_sha256=(
                    resolved.projection_sha256
                ),
                expected_writer_coordination_binding_sha256=harness._sha(
                    "writer-coordination"
                ),
                expected_maintenance_lease_contract_sha256=harness._sha(
                    "maintenance-lease"
                ),
                expected_authenticated_authority_contract_sha256=harness._sha(
                    "authority"
                ),
            )
        )

        result = binder.bind_offline(
            transaction_store_lock_port=transaction,
            resolved_authority_store_lock_port=resolved,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "PRODUCTION_MULTISTORE_LOCK_PORT_CROSS_BINDING_INVALID",
        )

    def test_resealed_attempt_to_enable_acquisition_is_rejected(self) -> None:
        transaction, resolved = (
            harness.build_synthetic_production_lock_port_projections_v2()
        )
        binder = harness.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=transaction,
            resolved_projection=resolved,
        )
        result = binder.bind_offline(
            transaction_store_lock_port=transaction,
            resolved_authority_store_lock_port=resolved,
        )
        original = result["protected_binding"]
        tampered_binding = copy.deepcopy(dict(original.binding))
        tampered_binding["lease_acquire_allowed"] = True
        tampered_binding["binding_sha256"] = (
            contract.production_multistore_observation_lease_binding_sha256_v2(
                tampered_binding
            )
        )
        tampered = contract.ProtectedProductionMultistoreObservationLeaseBindingV2(
            transaction_store_projection_sha256=(
                original.transaction_store_projection_sha256
            ),
            resolved_authority_store_projection_sha256=(
                original.resolved_authority_store_projection_sha256
            ),
            binding=tampered_binding,
            binding_sha256=tampered_binding["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_production_multistore_observation_lease_binding_valid_v2(
                tampered
            )
        )

    def test_projection_rejects_unknown_source_contract(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "PRODUCTION_STORE_LOCK_PORT_PROJECTION_INPUT_INVALID"
        ):
            contract.build_production_store_lock_port_projection_offline_v2(
                port_role=contract.TRANSACTION_STORE_ROLE_V2,
                source_contract_version="UNKNOWN",
                store_identity_sha256=harness._sha("identity"),
                storage_binding_sha256=harness._sha("storage"),
                lock_namespace_sha256=harness._sha("lock"),
            )

    def test_protected_representations_do_not_disclose_bindings(self) -> None:
        transaction, resolved = (
            harness.build_synthetic_production_lock_port_projections_v2()
        )
        binder = harness.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=transaction,
            resolved_projection=resolved,
        )
        result = binder.bind_offline(
            transaction_store_lock_port=transaction,
            resolved_authority_store_lock_port=resolved,
        )

        self.assertEqual(
            repr(transaction),
            "ProtectedProductionStoreLockPortProjectionV2(<protected>)",
        )
        self.assertEqual(
            repr(result["protected_binding"]),
            "ProtectedProductionMultistoreObservationLeaseBindingV2(<protected>)",
        )

    def test_contract_has_no_acquisition_surface_and_is_absent_from_runtime(self) -> None:
        self.assertFalse(
            hasattr(
                contract.DormantProductionMultistoreObservationLeaseContractV2,
                "acquire",
            )
        )
        self.assertFalse(
            hasattr(
                contract.DormantProductionMultistoreObservationLeaseContractV2,
                "release",
            )
        )
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "production_multistore_observation_lease_contract_offline_v2",
            main_source,
        )
        self.assertNotIn(
            "DormantProductionMultistoreObservationLeaseContractV2",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
