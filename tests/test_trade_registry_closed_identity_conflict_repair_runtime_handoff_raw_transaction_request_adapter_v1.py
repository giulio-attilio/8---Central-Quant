from __future__ import annotations

import ast
import copy
import inspect
import unittest
from dataclasses import replace
from unittest import mock

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_v1 as raw_store
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter


class HandoffRawTransactionRequestAdapterV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.inputs = (
            harness.build_synthetic_handoff_raw_request_adapter_inputs_v1()
        )

    def _project(self, *, clock=None) -> dict:
        return harness.build_synthetic_handoff_raw_request_adapter_v1(
            clock=clock
        ).project_offline(**self.inputs)

    def _reseal_proof(self) -> None:
        proof = self.inputs["canonical_raw_proof"]
        proof["proof_sha256"] = adapter.canonical_raw_proof_sha256_v1(proof)

    def _reseal_maintenance(self) -> None:
        attestation = self.inputs["maintenance_attestation"]
        attestation["attestation_sha256"] = (
            adapter.maintenance_attestation_sha256_v1(attestation)
        )

    def test_valid_projection_binds_both_hash_domains_and_generation(self) -> None:
        result = self._project()

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["status"],
            "C3_HANDOFF_RAW_TRANSACTION_REQUEST_PROJECTED_OFFLINE",
        )
        for field_name in (
            "handoff_verified",
            "source_snapshot_verified",
            "canonical_raw_proof_verified",
            "changed_paths_verified",
            "maintenance_attestation_verified_synthetic",
            "deadline_verified",
            "request_projected",
        ):
            self.assertTrue(result[field_name])
        for field_name in (
            "raw_transaction_store_called",
            "transaction_persistence_allowed",
            "runtime_integrated",
            "apply_allowed",
            "live_allowed",
            "real_registry_accessed",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[field_name])
        self.assertTrue(result["no_order_sent"])

        protected = result["protected_request"]
        request = protected.request
        self.assertIs(
            type(protected), adapter.ProtectedHandoffRawTransactionRequestV1
        )
        self.assertEqual(
            repr(protected),
            "ProtectedHandoffRawTransactionRequestV1(<protected>)",
        )
        self.assertEqual(
            request["idempotency_key"], self.inputs["command"].transaction_id
        )
        self.assertEqual(
            request["expected_raw_document_sha256"],
            self.inputs["source_snapshot"].raw_document_sha256,
        )
        self.assertEqual(
            request["expected_generation_token"],
            self.inputs["source_snapshot"].generation_token,
        )
        self.assertEqual(
            request["maintenance_epoch"],
            self.inputs["maintenance_attestation"]["maintenance_epoch"],
        )
        self.assertEqual(
            request["transaction_sha256"],
            raw_store.raw_transaction_request_sha256_v1(request),
        )

    def test_source_logical_and_exact_raw_hashes_remain_distinct(self) -> None:
        self.assertNotEqual(
            self.inputs["command"].source_registry_sha256,
            self.inputs["source_snapshot"].raw_document_sha256,
        )
        result = self._project()
        receipt = result["adapter_receipt"]

        self.assertTrue(result["ok"])
        self.assertEqual(
            receipt["source_registry_sha256"],
            self.inputs["command"].source_registry_sha256,
        )
        self.assertEqual(
            receipt["source_raw_document_sha256"],
            self.inputs["source_snapshot"].raw_document_sha256,
        )

    def test_handoff_and_raw_transaction_identities_remain_distinct(self) -> None:
        result = self._project()
        protected = result["protected_request"]

        self.assertTrue(result["ok"])
        self.assertEqual(
            protected.handoff_transaction_id,
            self.inputs["command"].transaction_id,
        )
        self.assertNotEqual(
            protected.raw_transaction_sha256,
            protected.handoff_transaction_id,
        )

    def test_default_off_blocks_before_projection(self) -> None:
        dormant = adapter.DormantHandoffRawTransactionRequestAdapterV1(
            clock=lambda: harness._NOW
        )
        result = dormant.project_offline(**self.inputs)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["ADAPTER_DEFAULT_OFF"])
        self.assertIsNone(result["protected_request"])
        self.assertFalse(result["raw_transaction_store_called"])

    def test_missing_offline_scope_blocks(self) -> None:
        invalid = adapter.DormantHandoffRawTransactionRequestAdapterV1(
            config=adapter.DormantHandoffRawRequestAdapterConfigV1(enabled=True),
            clock=lambda: harness._NOW,
        )
        result = invalid.project_offline(**self.inputs)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["ADAPTER_OFFLINE_SCOPE_ATTESTATION_REQUIRED"],
        )

    def test_exact_command_expiry_fails_closed(self) -> None:
        expiry = self.inputs["command"].expires_at_epoch
        result = self._project(clock=lambda: expiry)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["HANDOFF_COMMAND_INVALID_OR_EXPIRED"]
        )
        self.assertFalse(result["deadline_verified"])

    def test_tampered_command_fails_before_material_projection(self) -> None:
        self.inputs["command"] = replace(
            self.inputs["command"], candidate_registry_sha256="f" * 64
        )
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["HANDOFF_COMMAND_INVALID_OR_EXPIRED"]
        )
        self.assertFalse(result["source_snapshot_verified"])

    def test_raw_bytes_hash_tampering_fails_closed(self) -> None:
        snapshot = self.inputs["source_snapshot"]
        self.inputs["source_snapshot"] = replace(
            snapshot,
            raw_bytes=snapshot.raw_bytes + b" ",
            size_bytes=snapshot.size_bytes + 1,
        )
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SOURCE_SNAPSHOT_INVALID"])
        self.assertFalse(result["canonical_raw_proof_verified"])

    def test_raw_payload_disagreement_fails_closed(self) -> None:
        snapshot = self.inputs["source_snapshot"]
        divergent = copy.deepcopy(snapshot.payload)
        divergent["schema_version"] = 999
        self.inputs["source_snapshot"] = replace(snapshot, payload=divergent)
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SOURCE_SNAPSHOT_INVALID"])

    def test_candidate_drift_fails_closed(self) -> None:
        self.inputs["candidate_registry"]["closed_trades"][0]["pnl_r"] = 123.0
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["CANDIDATE_LOGICAL_HASH_MISMATCH"]
        )

    def test_changed_path_omission_fails_closed(self) -> None:
        self.inputs["changed_paths"] = ["closed_trades[0].close_reason"]
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["CHANGED_PATHS_BINDING_INVALID"]
        )

    def test_non_quiescent_or_non_synthetic_maintenance_fails_closed(self) -> None:
        variants = (
            ("state", "ACTIVE"),
            ("registered_writer_count", 18),
            ("inflight_mutations", 1),
            ("shared_lock_acquired", False),
            ("synthetic_only", False),
            ("production_evidence", True),
        )
        for field_name, value in variants:
            with self.subTest(field_name=field_name):
                self.setUp()
                self.inputs["maintenance_attestation"][field_name] = value
                self._reseal_maintenance()
                self.inputs["canonical_raw_proof"][
                    "maintenance_attestation_sha256"
                ] = self.inputs["maintenance_attestation"]["attestation_sha256"]
                self._reseal_proof()
                result = self._project()

                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"], ["MAINTENANCE_ATTESTATION_INVALID"]
                )
                self.assertIsNone(result["protected_request"])

    def test_generation_token_proof_drift_fails_closed(self) -> None:
        self.inputs["canonical_raw_proof"]["source_generation_token"] = "e" * 64
        self._reseal_proof()
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["CANONICAL_RAW_PROOF_INVALID"])

    def test_unknown_proof_field_fails_closed_even_when_resealed(self) -> None:
        self.inputs["canonical_raw_proof"]["production_authority"] = False
        self._reseal_proof()
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["CANONICAL_RAW_PROOF_INVALID"])

    def test_unknown_maintenance_field_fails_closed_even_when_resealed(
        self,
    ) -> None:
        self.inputs["maintenance_attestation"]["store_enabled"] = False
        self._reseal_maintenance()
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["MAINTENANCE_ATTESTATION_INVALID"])

    def test_proof_exact_expiry_fails_closed(self) -> None:
        self.inputs["canonical_raw_proof"]["expires_at_epoch"] = harness._NOW
        self._reseal_proof()
        result = self._project()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["CANONICAL_RAW_PROOF_INVALID"])

    def test_request_builder_is_used_but_no_store_method_is_called(self) -> None:
        calls = []
        original = raw_store.build_raw_transaction_request_v1

        def observed_builder(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        with mock.patch.object(
            raw_store,
            "build_raw_transaction_request_v1",
            side_effect=observed_builder,
        ):
            result = self._project()

        self.assertTrue(result["ok"])
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["raw_transaction_store_called"])
        self.assertFalse(result["transaction_persistence_allowed"])

    def test_protected_request_exposes_no_execution_surface(self) -> None:
        protected = self._project()["protected_request"]

        for method_name in (
            "serialize",
            "to_payload",
            "send",
            "apply",
            "invoke",
            "commit",
            "persist",
            "write",
        ):
            self.assertFalse(hasattr(protected, method_name))
        self.assertNotIn("candidate", repr(protected))
        self.assertNotIn("trade_id", repr(protected))

    def test_harness_covers_the_complete_offline_bridge(self) -> None:
        result = harness.run_synthetic_handoff_raw_request_adapter_harness_v1()

        for field_name in (
            "ok",
            "protected_surface_safe",
            "source_hash_domains_distinct",
            "handoff_and_raw_transaction_identities_distinct",
            "canonical_raw_proof_verified",
            "generation_token_bound",
            "maintenance_epoch_bound",
            "request_projected",
            "no_order_sent",
        ):
            self.assertTrue(result[field_name])
        for field_name in (
            "raw_transaction_store_called",
            "transaction_persistence_allowed",
            "runtime_integrated",
            "write_executed",
        ):
            self.assertFalse(result[field_name])

    def test_adapter_source_has_no_io_runtime_or_store_invocation_surface(
        self,
    ) -> None:
        tree = ast.parse(inspect.getsource(adapter))
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
            "read_bytes",
            "write_bytes",
            "apply_synthetic_transaction",
            "apply_attested_transaction",
            "load_exact_raw_registry",
            "reconcile_attested_transaction",
        ):
            self.assertNotIn(method_name, called_attributes)

    def test_adapter_config_rejects_unbounded_ttl(self) -> None:
        with self.assertRaises(ValueError):
            adapter.DormantHandoffRawRequestAdapterConfigV1(
                max_proof_ttl_seconds=301
            )
        with self.assertRaises(ValueError):
            adapter.DormantHandoffRawRequestAdapterConfigV1(
                max_proof_ttl_seconds=0
            )


if __name__ == "__main__":
    unittest.main()
