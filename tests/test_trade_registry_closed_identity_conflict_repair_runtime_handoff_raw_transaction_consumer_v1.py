from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import replace

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1 as production_store
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


class HandoffRawTransactionConsumerV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = (
            harness.build_synthetic_handoff_raw_transaction_consumer_inputs_v1()
        )

    def _consume_with_live_lease(
        self,
        *,
        permit=None,
        supplied_permit=None,
        backend_attestation=None,
        adapter_result=None,
    ) -> dict:
        held_permit = permit or self.inputs["maintenance_permit"]
        consumed_permit = supplied_permit or held_permit
        witness = self.inputs["lease_witness"]
        with witness.hold_offline(
            held_permit,
            expires_at_epoch=self.inputs["lease_expires_at_epoch"],
        ) as token:
            return self.inputs["consumer"].consume_offline(
                adapter_result=adapter_result or self.inputs["adapter_result"],
                maintenance_permit=consumed_permit,
                live_lease_token=token,
                backend_capability_attestation=(
                    backend_attestation
                    or self.inputs["backend_capability_attestation"]
                ),
            )

    @staticmethod
    def _reseal_backend(attestation: dict) -> None:
        attestation["attestation_sha256"] = (
            production_store.production_backend_capability_attestation_sha256_v1(
                attestation
            )
        )

    def test_valid_consume_projects_hash_only_non_executable_intent(self) -> None:
        result = self._consume_with_live_lease()

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["status"],
            "C3_RAW_TRANSACTION_INVOCATION_INTENT_PROJECTED_OFFLINE",
        )
        for field_name in (
            "adapter_projection_verified",
            "same_permit_instance_verified",
            "lease_live_verified_synthetic",
            "canonical_lock_namespace_verified",
            "backend_capabilities_verified_synthetic",
            "deadline_revalidated",
            "invocation_intent_projected",
        ):
            self.assertTrue(result[field_name])
        for field_name in (
            "invocation_material_exposed",
            "backend_referenced",
            "raw_transaction_store_called",
            "transaction_persistence_allowed",
            "runtime_integrated",
            "production_ready",
            "apply_allowed",
            "activation_allowed",
            "live_allowed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[field_name])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_blocks_before_liveness_check(self) -> None:
        dormant = consumer.DormantHandoffRawTransactionConsumerV1(
            clock=lambda: harness._NOW,
            lease_witness=self.inputs["lease_witness"],
        )
        permit = self.inputs["maintenance_permit"]
        with self.inputs["lease_witness"].hold_offline(
            permit,
            expires_at_epoch=self.inputs["lease_expires_at_epoch"],
        ) as token:
            result = dormant.consume_offline(
                adapter_result=self.inputs["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=self.inputs[
                    "backend_capability_attestation"
                ],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["CONSUMER_DEFAULT_OFF"])

    def test_missing_scope_attestation_blocks(self) -> None:
        invalid = consumer.DormantHandoffRawTransactionConsumerV1(
            config=consumer.DormantHandoffRawTransactionConsumerConfigV1(
                enabled=True
            ),
            clock=lambda: harness._NOW,
            lease_witness=self.inputs["lease_witness"],
        )
        permit = self.inputs["maintenance_permit"]
        with self.inputs["lease_witness"].hold_offline(
            permit,
            expires_at_epoch=self.inputs["lease_expires_at_epoch"],
        ) as token:
            result = invalid.consume_offline(
                adapter_result=self.inputs["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=self.inputs[
                    "backend_capability_attestation"
                ],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["CONSUMER_OFFLINE_SCOPE_ATTESTATION_REQUIRED"],
        )

    def test_same_values_in_different_permit_instance_are_rejected(self) -> None:
        held = self.inputs["maintenance_permit"]
        copied = replace(held)

        result = self._consume_with_live_lease(
            permit=held,
            supplied_permit=copied,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH"],
        )
        self.assertFalse(result["same_permit_instance_verified"])

    def test_token_is_invalid_immediately_after_lease_release(self) -> None:
        permit = self.inputs["maintenance_permit"]
        witness = self.inputs["lease_witness"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=self.inputs["lease_expires_at_epoch"],
        ) as token:
            self.assertTrue(
                witness.validate_live(permit, token, now_epoch=harness._NOW)
            )
        result = self.inputs["consumer"].consume_offline(
            adapter_result=self.inputs["adapter_result"],
            maintenance_permit=permit,
            live_lease_token=token,
            backend_capability_attestation=self.inputs[
                "backend_capability_attestation"
            ],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH"],
        )
        self.assertFalse(witness.snapshot()["active"])

    def test_maintenance_epoch_mismatch_is_rejected_before_liveness(self) -> None:
        held = self.inputs["maintenance_permit"]
        divergent = replace(held, maintenance_epoch="f" * 64)

        result = self._consume_with_live_lease(
            permit=held,
            supplied_permit=divergent,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["CANONICAL_MAINTENANCE_PERMIT_INVALID"]
        )

    def test_noncanonical_permit_namespace_cannot_be_held(self) -> None:
        invalid = replace(
            self.inputs["maintenance_permit"],
            lock_namespace_sha256="f" * 64,
        )

        with self.assertRaises(ValueError):
            with self.inputs["lease_witness"].hold_offline(
                invalid,
                expires_at_epoch=self.inputs["lease_expires_at_epoch"],
            ):
                pass

    def test_explicit_production_backend_scope_is_rejected(self) -> None:
        attestation = dict(self.inputs["backend_capability_attestation"])
        attestation["storage_scope"] = "EXPLICIT_PRODUCTION"
        self._reseal_backend(attestation)

        result = self._consume_with_live_lease(backend_attestation=attestation)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["TEMPORARY_BACKEND_CAPABILITY_ATTESTATION_INVALID"],
        )

    def test_backend_namespace_mismatch_is_rejected(self) -> None:
        attestation = dict(self.inputs["backend_capability_attestation"])
        attestation["lock_namespace_sha256"] = "f" * 64
        self._reseal_backend(attestation)

        result = self._consume_with_live_lease(backend_attestation=attestation)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["TEMPORARY_BACKEND_CAPABILITY_ATTESTATION_INVALID"],
        )

    def test_missing_backend_capability_is_rejected(self) -> None:
        attestation = dict(self.inputs["backend_capability_attestation"])
        attestation["capabilities"] = dict(attestation["capabilities"])
        attestation["capabilities"]["interrupted_transaction_recovery"] = False
        self._reseal_backend(attestation)

        result = self._consume_with_live_lease(backend_attestation=attestation)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["TEMPORARY_BACKEND_CAPABILITY_ATTESTATION_INVALID"],
        )

    def test_mutable_request_tampering_is_detected_at_consume_boundary(self) -> None:
        projected = self.inputs["adapter_result"]["protected_request"]
        projected.request["candidate_registry"]["closed_trades"][0][
            "close_reason"
        ] = "TAMPERED"

        result = self._consume_with_live_lease()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["ADAPTER_PROJECTION_INVALID_OR_EXPIRED"]
        )

    def test_adapter_receipt_tampering_is_detected(self) -> None:
        self.inputs["adapter_result"]["adapter_receipt"][
            "production_ready"
        ] = True

        result = self._consume_with_live_lease()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["ADAPTER_PROJECTION_INVALID_OR_EXPIRED"]
        )

    def test_adapter_expiry_is_revalidated_at_consume_boundary(self) -> None:
        expiry = self.inputs["adapter_result"]["protected_request"].expires_at_epoch
        witness = self.inputs["lease_witness"]
        consumer_at_expiry = consumer.DormantHandoffRawTransactionConsumerV1(
            config=consumer.DormantHandoffRawTransactionConsumerConfigV1(
                enabled=True,
                scope_attestation=consumer.OFFLINE_HANDOFF_RAW_TRANSACTION_CONSUMER_SCOPE_ATTESTATION_V1,
            ),
            clock=lambda: expiry,
            lease_witness=witness,
        )
        permit = self.inputs["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=expiry + 1,
        ) as token:
            result = consumer_at_expiry.consume_offline(
                adapter_result=self.inputs["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=self.inputs[
                    "backend_capability_attestation"
                ],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["ADAPTER_PROJECTION_INVALID_OR_EXPIRED"]
        )

    def test_protected_intent_contains_no_request_or_backend_object(self) -> None:
        protected = self._consume_with_live_lease()["protected_intent"]

        self.assertIs(
            type(protected), consumer.ProtectedRawTransactionInvocationIntentV1
        )
        self.assertEqual(
            repr(protected),
            "ProtectedRawTransactionInvocationIntentV1(<protected>)",
        )
        self.assertFalse(hasattr(protected, "request"))
        self.assertFalse(hasattr(protected, "backend"))
        for method_name in (
            "serialize",
            "apply",
            "invoke",
            "commit",
            "persist",
            "write",
        ):
            self.assertFalse(hasattr(protected, method_name))

    def test_complete_offline_consumer_harness(self) -> None:
        result = harness.run_synthetic_handoff_raw_transaction_consumer_harness_v1()

        for field_name in (
            "ok",
            "protected_surface_safe",
            "adapter_projection_verified",
            "same_permit_instance_verified",
            "live_lease_verified_synthetic",
            "lease_live_during_consume",
            "lease_released_after_context",
            "replay_after_lease_release_blocked",
            "canonical_lock_namespace_verified",
            "backend_capabilities_verified_synthetic",
            "no_order_sent",
        ):
            self.assertTrue(result[field_name])
        for field_name in (
            "backend_referenced",
            "raw_transaction_store_called",
            "transaction_persistence_allowed",
            "runtime_integrated",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[field_name])

    def test_consumer_source_has_no_store_runtime_or_io_call(self) -> None:
        tree = ast.parse(inspect.getsource(consumer))
        imported_modules = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        for module_name in (
            "main",
            "requests",
            "httpx",
            "os",
            "pathlib",
            "tempfile",
        ):
            self.assertNotIn(module_name, imported_modules)
        self.assertNotIn("open", called_names)
        for method_name in (
            "apply_synthetic_transaction",
            "apply_attested_transaction",
            "load_exact_raw_registry",
            "reconcile_attested_transaction",
        ):
            self.assertNotIn(method_name, called_attributes)

    def test_consumer_config_rejects_unbounded_ttl(self) -> None:
        with self.assertRaises(ValueError):
            consumer.DormantHandoffRawTransactionConsumerConfigV1(
                max_consume_ttl_seconds=301
            )
        with self.assertRaises(ValueError):
            consumer.DormantHandoffRawTransactionConsumerConfigV1(
                max_consume_ttl_seconds=0
            )

    def test_canonical_namespace_matches_coordinator_contract(self) -> None:
        result = self._consume_with_live_lease()
        self.assertEqual(
            result["protected_intent"].lock_namespace_sha256,
            coordinator.canonical_runtime_lock_namespace_v1(),
        )


if __name__ == "__main__":
    unittest.main()
