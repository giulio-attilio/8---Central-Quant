from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2 as provider_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as runtime_coordinator
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_contract


def _sha(label: str) -> str:
    return backend_contract.stable_sha256_v2(label)


def _seal(value: dict, key: str) -> dict:
    value[key] = backend_contract.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )
    return value


def _fixture() -> dict:
    provider_values = provider_harness.build_provider_store_projection_fixture_v2()
    provider_bundle = provider_values["projection"]["protected_bundle"]
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    seams = seam_contract.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": _sha("participation")}
    )
    namespace = runtime_coordinator.canonical_runtime_lock_namespace_v1()
    adapter_sha = _sha("invocation-adapter-instance")
    coordinator_sha = _sha("coordinator-instance")
    permit_sha = _sha("permit-instance")
    callable_projection = contract.build_callable_manifest_projection_offline_v2(
        inventory,
        seams,
        adapter_instance_sha256=adapter_sha,
        callable_manifest_sha256=_sha("v1-callable-manifest"),
    )
    coordinator_projection = _seal(
        {
            "projection_version": contract.COORDINATOR_PROJECTION_VERSION_V2,
            "coordinator_contract_version": runtime_coordinator.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION,
            "coordinator_instance_sha256": coordinator_sha,
            "writer_inventory_sha256": backend_contract.stable_sha256_v2(inventory),
            "lock_namespace_sha256": namespace,
            "registered_writer_count": 19,
            "all_writers_registered": True,
            "inflight_mutations": 0,
            "synthetic_rehearsal": True,
            "runtime_enabled": False,
            "runtime_integrated": False,
            "production_authority": False,
        },
        "projection_sha256",
    )
    permit_binding = {
        "coordinator_instance_sha256": coordinator_sha,
        "maintenance_epoch": _sha("maintenance-epoch"),
        "state": "QUIESCED",
        "lock_namespace_sha256": namespace,
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
    }
    permit_projection = _seal(
        {
            "projection_version": contract.MAINTENANCE_PERMIT_PROJECTION_VERSION_V2,
            "permit_instance_sha256": permit_sha,
            "permit_binding_sha256": backend_contract.stable_sha256_v2(permit_binding),
            **permit_binding,
            "synthetic_only": True,
            "production_authority": False,
        },
        "projection_sha256",
    )
    lease_projection = _seal(
        {
            "projection_version": contract.LIVE_LEASE_PROJECTION_VERSION_V2,
            "lease_token_sha256": _sha("lease-token"),
            "permit_instance_sha256": permit_sha,
            "permit_binding_sha256": permit_projection["permit_binding_sha256"],
            "coordinator_instance_sha256": coordinator_sha,
            "maintenance_epoch": permit_projection["maintenance_epoch"],
            "lock_namespace_sha256": namespace,
            "issued_at_epoch": 1_000,
            "expires_at_epoch": 1_120,
            "same_permit_instance": True,
            "active_synthetic": True,
            "single_use": True,
            "synthetic_only": True,
            "production_authority": False,
        },
        "projection_sha256",
    )
    lock_policy = contract.build_single_owner_lock_policy_offline_v2(namespace)
    binder = contract.DormantWriterCoordinationCompatibilityV2(
        contract.WriterCoordinationCompatibilityConfigV2(
            enabled=True,
            scope_attestation=contract.OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2,
            expected_provider_store_bundle_sha256=provider_bundle.bundle_sha256,
        )
    )
    return {
        "provider_bundle": provider_bundle,
        "inventory": inventory,
        "seams": seams,
        "callable": callable_projection,
        "coordinator": coordinator_projection,
        "permit": permit_projection,
        "lease": lease_projection,
        "lock": lock_policy,
        "binder": binder,
        "now": 1_060,
    }


def _bind(values: dict) -> dict:
    return values["binder"].bind_offline(
        provider_store_bundle=values["provider_bundle"],
        writer_inventory=values["inventory"],
        seam_bindings=values["seams"],
        callable_manifest_projection=values["callable"],
        coordinator_projection=values["coordinator"],
        maintenance_permit_projection=values["permit"],
        live_lease_projection=values["lease"],
        lock_ownership_policy=values["lock"],
        now_epoch=values["now"],
    )


class WriterCoordinationCompatibilityV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = _fixture()

    def values(self) -> dict:
        result = copy.deepcopy(self.base)
        result["provider_bundle"] = self.base["provider_bundle"]
        result["binder"] = self.base["binder"]
        return result

    def test_binds_exact_19_writers_and_denies_every_call_surface(self) -> None:
        result = _bind(self.values())

        self.assertTrue(result["ok"])
        self.assertEqual(result["writer_count"], 19)
        self.assertTrue(result["single_lock_owner_verified"])
        self.assertTrue(result["same_permit_instance_verified_synthetic"])
        protected = result["protected_bundle"]
        self.assertTrue(
            contract.protected_writer_coordination_compatibility_bundle_valid_v2(
                protected
            )
        )
        self.assertEqual(
            repr(protected),
            "ProtectedWriterCoordinationCompatibilityBundleV2(<protected>)",
        )
        for method_name in (
            "invoke", "apply", "apply_attested_transaction", "reconcile",
            "load_exact_raw_registry", "acquire", "install", "activate",
        ):
            self.assertFalse(hasattr(protected, method_name), method_name)
        for key in (
            "provider_called", "store_called", "backend_called", "writer_called",
            "lock_acquired", "filesystem_accessed", "real_registry_accessed",
            "network_accessed", "broker_called", "write_executed",
            "production_authority", "runtime_integrated", "activation_allowed",
            "live_allowed",
        ):
            self.assertFalse(result[key], key)

    def test_default_off_does_not_validate_or_inspect_inputs(self) -> None:
        binder = contract.DormantWriterCoordinationCompatibilityV2()

        result = binder.bind_offline(
            provider_store_bundle=None,
            writer_inventory=[],
            seam_bindings=[],
            callable_manifest_projection={},
            coordinator_projection={},
            maintenance_permit_projection={},
            live_lease_projection={},
            lock_ownership_policy={},
            now_epoch=0,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "WRITER_COORDINATION_COMPATIBILITY_V2_DEFAULT_OFF"
        )

    def test_writer_inventory_must_be_exact_and_ordered(self) -> None:
        values = self.values()
        values["inventory"] = list(reversed(values["inventory"]))

        result = _bind(values)

        self.assertEqual(result["reason"], "CANONICAL_19_WRITER_MATERIAL_INVALID")

    def test_non_mapping_projection_fails_closed(self) -> None:
        values = self.values()
        values["callable"] = None

        result = _bind(values)

        self.assertEqual(
            result["reason"], "COMPATIBILITY_PROJECTION_MAPPING_INPUTS_REQUIRED"
        )

    def test_callable_manifest_is_bound_to_source_signatures(self) -> None:
        values = self.values()
        values["callable"]["source_signature_sha256s"][0] = _sha("wrong")
        _seal(values["callable"], "projection_sha256")

        result = _bind(values)

        self.assertEqual(result["reason"], "CALLABLE_MANIFEST_PROJECTION_V2_INVALID")

    def test_same_permit_instance_is_mandatory(self) -> None:
        values = self.values()
        values["lease"]["permit_instance_sha256"] = _sha("different-permit")
        _seal(values["lease"], "projection_sha256")

        result = _bind(values)

        self.assertEqual(result["reason"], "LIVE_LEASE_PROJECTION_V2_INVALID_OR_EXPIRED")

    def test_expired_lease_fails_closed(self) -> None:
        values = self.values()
        values["now"] = values["lease"]["expires_at_epoch"]

        result = _bind(values)

        self.assertEqual(result["reason"], "LIVE_LEASE_PROJECTION_V2_INVALID_OR_EXPIRED")

    def test_backend_lock_reacquisition_is_forbidden(self) -> None:
        values = self.values()
        values["lock"]["backend_reacquire_allowed"] = True
        _seal(values["lock"], "policy_sha256")

        result = _bind(values)

        self.assertEqual(result["reason"], "SINGLE_OWNER_LOCK_POLICY_V2_INVALID")

    def test_resealed_nested_authority_escalation_invalidates_bundle(self) -> None:
        protected = _bind(self.values())["protected_bundle"]
        bundle = copy.deepcopy(dict(protected.bundle))
        bundle["coordinator_projection"]["production_authority"] = True
        _seal(bundle["coordinator_projection"], "projection_sha256")
        _seal(bundle, "bundle_sha256")
        tampered = contract.ProtectedWriterCoordinationCompatibilityBundleV2(
            provider_store_bundle_sha256=protected.provider_store_bundle_sha256,
            coordinator_instance_sha256=protected.coordinator_instance_sha256,
            permit_instance_sha256=protected.permit_instance_sha256,
            bundle=bundle,
            bundle_sha256=bundle["bundle_sha256"],
        )

        self.assertFalse(
            contract.protected_writer_coordination_compatibility_bundle_valid_v2(
                tampered
            )
        )


if __name__ == "__main__":
    unittest.main()
