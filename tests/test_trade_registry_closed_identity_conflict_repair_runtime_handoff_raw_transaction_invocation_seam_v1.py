from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import replace

import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter


class RawTransactionInvocationSeamV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = harness.build_synthetic_raw_transaction_invocation_seam_inputs_v1()

    def _invoke_inside_lease(self, inputs=None) -> dict:
        values = inputs or self.inputs
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            return values["invocation_seam"].invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

    def _interrupt(self) -> tuple[dict, dict]:
        values = harness.build_synthetic_raw_transaction_invocation_seam_inputs_v1(
            fault_mode="AFTER_PREPARED"
        )
        return values, self._invoke_inside_lease(values)

    def _recover(self, values: dict, interrupted: dict, *, material=None) -> dict:
        recovery = material or harness.build_synthetic_recovery_maintenance_v1()
        permit = recovery["permit"]
        witness = values["lease_witness"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=recovery["lease_expires_at_epoch"],
        ) as token:
            return values["invocation_seam"].recover_offline(
                recovery_command=interrupted["protected_recovery_command"],
                recovery_maintenance_permit=permit,
                recovery_live_lease_token=token,
                recovery_maintenance_attestation=recovery["attestation"],
            )

    def test_success_postconditions_and_store_identity_are_verified(self) -> None:
        result = self._invoke_inside_lease()

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["status"], "C3_SYNTHETIC_RAW_TRANSACTION_COMMITTED_OFFLINE"
        )
        for field_name in (
            "consumer_intent_verified",
            "adapter_material_revalidated",
            "same_permit_instance_verified",
            "lease_live_verified_synthetic",
            "store_instance_bound_synthetic",
            "deadline_revalidated",
            "postconditions_verified",
            "synthetic_store_double_called",
            "no_order_sent",
        ):
            self.assertTrue(result[field_name])
        for field_name in (
            "production_store_called",
            "recovery_required",
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
        self.assertEqual(
            result["invocation_receipt"]["store_instance_sha256"],
            self.inputs["store_double"].instance_sha256,
        )

    def test_replay_is_idempotent_inside_same_live_lease(self) -> None:
        values = self.inputs
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            first = values["invocation_seam"].invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )
            replay = values["invocation_seam"].invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

        self.assertTrue(first["ok"])
        self.assertTrue(replay["ok"])
        self.assertTrue(replay["synthetic_store_result"]["idempotent_replay"])
        self.assertEqual(values["store_double"].snapshot()["record_count"], 1)

    def test_interruption_after_prepared_emits_protected_recovery_command(
        self,
    ) -> None:
        values, interrupted = self._interrupt()
        command = interrupted["protected_recovery_command"]

        self.assertFalse(interrupted["ok"])
        self.assertEqual(
            interrupted["status"],
            "C3_SYNTHETIC_TRANSACTION_INTERRUPTED_AFTER_PREPARED",
        )
        self.assertTrue(interrupted["recovery_required"])
        self.assertIs(
            type(command), seam.ProtectedSyntheticPreparedRecoveryCommandV1
        )
        self.assertEqual(
            repr(command),
            "ProtectedSyntheticPreparedRecoveryCommandV1(<protected>)",
        )
        self.assertEqual(
            values["store_double"].snapshot()["states"], {"PREPARED": 1}
        )
        self.assertFalse(interrupted["production_store_called"])
        self.assertFalse(interrupted["write_executed"])

    def test_interrupted_prepared_recovers_under_fresh_lease(self) -> None:
        values, interrupted = self._interrupt()
        recovered = self._recover(values, interrupted)

        self.assertTrue(recovered["ok"])
        self.assertEqual(
            recovered["status"],
            "C3_SYNTHETIC_PREPARED_TRANSACTION_RECOVERED_ABORTED_OFFLINE",
        )
        self.assertTrue(recovered["postconditions_verified"])
        self.assertFalse(recovered["recovery_required"])
        self.assertEqual(
            recovered["synthetic_store_result"]["terminal_state"], "ABORTED"
        )
        self.assertEqual(
            values["store_double"].snapshot()["states"], {"ABORTED": 1}
        )

    def test_recovery_rejects_original_maintenance_epoch(self) -> None:
        values, interrupted = self._interrupt()
        original = values["maintenance_permit"]
        material = harness.build_synthetic_recovery_maintenance_v1()
        material["permit"] = replace(
            material["permit"], maintenance_epoch=original.maintenance_epoch
        )
        material["attestation"]["maintenance_epoch"] = original.maintenance_epoch
        material["attestation"]["attestation_sha256"] = (
            adapter.maintenance_attestation_sha256_v1(material["attestation"])
        )
        result = self._recover(values, interrupted, material=material)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["FRESH_RECOVERY_MAINTENANCE_ATTESTATION_INVALID"],
        )
        self.assertEqual(
            values["store_double"].snapshot()["states"], {"PREPARED": 1}
        )

    def test_tampered_recovery_command_fails_before_store_call(self) -> None:
        values, interrupted = self._interrupt()
        interrupted["protected_recovery_command"] = replace(
            interrupted["protected_recovery_command"],
            candidate_raw_document_sha256="f" * 64,
        )
        recovered = self._recover(values, interrupted)

        self.assertFalse(recovered["ok"])
        self.assertEqual(
            recovered["reasons"],
            ["SYNTHETIC_RECOVERY_COMMAND_INVALID_OR_EXPIRED"],
        )

    def test_recovery_command_is_bound_to_same_store_instance(self) -> None:
        values, interrupted = self._interrupt()
        alternate = harness.build_synthetic_raw_transaction_invocation_seam_inputs_v1()
        alternate_store = seam.InMemoryAttestedRawTransactionStoreDoubleV1(
            backend_capability_attestation=alternate[
                "backend_capability_attestation"
            ],
            nonce="genuinely-distinct-recovery-store-instance-v1",
        )
        alternate_seam = seam.DormantRawTransactionInvocationSeamV1(
            config=seam.DormantRawTransactionInvocationSeamConfigV1(
                enabled=True,
                scope_attestation=seam.OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1,
            ),
            clock=lambda: harness._NOW,
            lease_witness=alternate["lease_witness"],
            store_double=alternate_store,
        )
        recovery = harness.build_synthetic_recovery_maintenance_v1()
        permit = recovery["permit"]
        with alternate["lease_witness"].hold_offline(
            permit,
            expires_at_epoch=recovery["lease_expires_at_epoch"],
        ) as token:
            result = alternate_seam.recover_offline(
                recovery_command=interrupted["protected_recovery_command"],
                recovery_maintenance_permit=permit,
                recovery_live_lease_token=token,
                recovery_maintenance_attestation=recovery["attestation"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["SYNTHETIC_RECOVERY_COMMAND_INVALID_OR_EXPIRED"],
        )
        self.assertNotEqual(
            values["store_double"].instance_sha256,
            alternate_store.instance_sha256,
        )

    def test_default_off_never_calls_store_double(self) -> None:
        values = self.inputs
        dormant = seam.DormantRawTransactionInvocationSeamV1(
            clock=lambda: harness._NOW,
            lease_witness=values["lease_witness"],
            store_double=values["store_double"],
        )
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            result = dormant.invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["INVOCATION_SEAM_DEFAULT_OFF"])
        self.assertFalse(result["synthetic_store_double_called"])
        self.assertEqual(values["store_double"].snapshot()["record_count"], 0)

    def test_consumer_receipt_tampering_fails_before_store_call(self) -> None:
        values = self.inputs
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            consumer_result["consumer_receipt"]["production_ready"] = True
            result = values["invocation_seam"].invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["CONSUMER_INTENT_OR_ADAPTER_MATERIAL_INVALID"]
        )
        self.assertEqual(values["store_double"].snapshot()["record_count"], 0)

    def test_adapter_request_tampering_fails_before_store_call(self) -> None:
        values = self.inputs
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            values["adapter_result"]["protected_request"].request[
                "candidate_registry"
            ]["schema_version"] = 999
            result = values["invocation_seam"].invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["CONSUMER_INTENT_OR_ADAPTER_MATERIAL_INVALID"]
        )
        self.assertEqual(values["store_double"].snapshot()["record_count"], 0)

    def test_call_after_lease_release_is_blocked(self) -> None:
        values = self.inputs
        witness = values["lease_witness"]
        permit = values["maintenance_permit"]
        with witness.hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
        result = values["invocation_seam"].invoke_offline(
            consumer_result=consumer_result,
            adapter_result=values["adapter_result"],
            maintenance_permit=permit,
            live_lease_token=token,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH"],
        )
        self.assertEqual(values["store_double"].snapshot()["record_count"], 0)

    def test_unattested_success_result_fails_closed(self) -> None:
        values = harness.build_synthetic_raw_transaction_invocation_seam_inputs_v1(
            fault_mode="INVALID_SUCCESS"
        )
        result = self._invoke_inside_lease(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SYNTHETIC_STORE_POSTCONDITIONS_INVALID"]
        )
        self.assertTrue(result["recovery_required"])
        self.assertFalse(result["postconditions_verified"])

    def test_complete_harness_covers_success_interruption_and_recovery(self) -> None:
        result = harness.run_synthetic_raw_transaction_invocation_seam_harness_v1()

        for field_name in (
            "ok",
            "success_postconditions_verified",
            "success_idempotent_replay_verified",
            "interruption_after_prepared_detected",
            "fresh_lease_recovery_verified",
            "recovery_surface_safe",
            "same_store_instance_recovered",
            "synthetic_store_double_called",
            "no_order_sent",
        ):
            self.assertTrue(result[field_name])
        self.assertEqual(result["recovery_terminal_state"], "ABORTED")
        for field_name in (
            "production_store_called",
            "transaction_persistence_allowed",
            "runtime_integrated",
            "production_ready",
            "apply_allowed",
            "live_allowed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[field_name])

    def test_source_has_no_filesystem_network_or_production_store_call(self) -> None:
        tree = ast.parse(inspect.getsource(seam))
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
            "apply_attested_transaction",
            "reconcile_attested_transaction",
            "load_exact_raw_registry",
            "read_bytes",
            "write_bytes",
        ):
            self.assertNotIn(method_name, called_attributes)

    def test_only_exact_store_double_type_is_accepted(self) -> None:
        values = self.inputs
        invalid = seam.DormantRawTransactionInvocationSeamV1(
            config=seam.DormantRawTransactionInvocationSeamConfigV1(
                enabled=True,
                scope_attestation=seam.OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1,
            ),
            clock=lambda: harness._NOW,
            lease_witness=values["lease_witness"],
            store_double=None,
        )
        permit = values["maintenance_permit"]
        with values["lease_witness"].hold_offline(
            permit,
            expires_at_epoch=values["lease_expires_at_epoch"],
        ) as token:
            consumer_result = values["consumer"].consume_offline(
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
                backend_capability_attestation=values[
                    "backend_capability_attestation"
                ],
            )
            result = invalid.invoke_offline(
                consumer_result=consumer_result,
                adapter_result=values["adapter_result"],
                maintenance_permit=permit,
                live_lease_token=token,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EXACT_SYNTHETIC_DEPENDENCIES_REQUIRED"])

    def test_config_rejects_unbounded_recovery_ttl(self) -> None:
        with self.assertRaises(ValueError):
            seam.DormantRawTransactionInvocationSeamConfigV1(
                max_recovery_ttl_seconds=301
            )
        with self.assertRaises(ValueError):
            seam.DormantRawTransactionInvocationSeamConfigV1(
                max_recovery_ttl_seconds=0
            )


if __name__ == "__main__":
    unittest.main()
