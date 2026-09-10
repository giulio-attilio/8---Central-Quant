from __future__ import annotations

import copy
import unittest

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as harness


class DurableRawTransactionBackendConformanceV2Tests(unittest.TestCase):
    def _auditor(self) -> contract.DurableRawTransactionBackendConformanceV2:
        return contract.DurableRawTransactionBackendConformanceV2(
            contract.DurableRawTransactionBackendConformanceConfigV2(
                enabled=True,
                scope_attestation=contract.OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2,
            )
        )

    def test_complete_harness_passes_without_production_authority(self) -> None:
        result = harness.run_durable_raw_transaction_backend_conformance_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["capability_count"], 9)
        self.assertEqual(result["checkpoint_count"], 3)
        self.assertTrue(result["exact_transaction_contract_verified"])
        self.assertTrue(result["resumable_recovery_verified"])
        self.assertTrue(result["synthetic_only"])
        self.assertTrue(result["no_order_sent"])
        for key in (
            "durable", "production_evidence", "production_ready", "runtime_integrated",
            "activation_allowed", "live_allowed", "real_registry_accessed",
            "filesystem_accessed", "network_accessed", "broker_called", "write_executed",
        ):
            self.assertFalse(result[key], key)

    def test_conformance_is_default_off(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        result = contract.DurableRawTransactionBackendConformanceV2().audit_offline(backend)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["DURABLE_BACKEND_CONFORMANCE_DEFAULT_OFF", "DURABLE_BACKEND_CONFORMANCE_SCOPE_INVALID"])
        self.assertEqual(backend.calls, [])

    def test_exactly_one_evidence_receipt_per_capability_is_required(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        backend._evidence.pop()

        result = self._auditor().audit_offline(backend)

        self.assertFalse(result["ok"])
        self.assertIn("DURABLE_BACKEND_V2_CAPABILITY_EVIDENCE_COUNT_INVALID", result["reasons"])

    def test_self_declared_or_resealed_capability_without_observation_fails(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        item = backend._evidence[0]
        item["observed"] = False
        item["evidence_sha256"] = contract.stable_sha256_v2(
            {key: value for key, value in item.items() if key != "evidence_sha256"}
        )

        result = self._auditor().audit_offline(backend)

        self.assertFalse(result["ok"])
        self.assertIn("DURABLE_BACKEND_V2_CAPABILITY_EVIDENCE_INVALID", result["reasons"])

    def test_snapshot_module_source_path_and_lock_are_hash_bound(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        snapshot = backend.snapshot_offline()

        self.assertTrue(contract.backend_snapshot_valid_v2(snapshot))
        for field in (
            "backend_module_source_sha256", "registry_path_binding_sha256", "lock_namespace_sha256"
        ):
            changed = copy.deepcopy(snapshot)
            changed[field] = harness._sha(f"tampered:{field}")
            self.assertFalse(contract.backend_snapshot_valid_v2(changed), field)

    def test_catalog_is_sorted_unique_complete_and_snapshot_bound(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2(prepared_count=2)
        snapshot = backend.snapshot_offline()
        catalog = backend.list_prepared_transactions_offline()

        self.assertTrue(contract.prepared_catalog_valid_v2(catalog, snapshot))
        changed = copy.deepcopy(catalog)
        changed["records"].reverse()
        changed["catalog_sha256"] = contract.stable_sha256_v2(
            {key: value for key, value in changed.items() if key != "catalog_sha256"}
        )
        self.assertFalse(contract.prepared_catalog_valid_v2(changed, snapshot))

    def test_request_and_result_exact_schemas_fail_on_extra_field(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        snapshot = backend.snapshot_offline()
        request = harness.build_synthetic_transaction_request_v2(snapshot)
        result = harness.build_synthetic_transaction_result_v2(request)

        self.assertTrue(contract.transaction_request_valid_v2(request, snapshot))
        self.assertTrue(contract.transaction_result_valid_v2(result, request))
        request["unexpected"] = True
        self.assertFalse(contract.transaction_request_valid_v2(request, snapshot))

    def test_terminal_result_requires_state_specific_generation_and_postconditions(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()
        snapshot = backend.snapshot_offline()
        request = harness.build_synthetic_transaction_request_v2(snapshot)
        committed = harness.build_synthetic_transaction_result_v2(request)

        for field, value in (
            ("generation_before", request["expected_generation"] + 1),
            ("generation_after", request["expected_generation"]),
            ("postconditions_verified", False),
            ("prepared_record_sha256", "not-a-sha256"),
            ("terminal_record_sha256", "not-a-sha256"),
        ):
            changed = copy.deepcopy(committed)
            changed[field] = value
            changed["result_sha256"] = contract.stable_sha256_v2(
                {
                    key: item
                    for key, item in changed.items()
                    if key != "result_sha256"
                }
            )
            self.assertFalse(
                contract.transaction_result_valid_v2(changed, request),
                field,
            )

        for state, postconditions, recovery in (
            ("ABORTED", True, False),
            ("ROLLED_BACK", True, False),
            ("AMBIGUOUS", False, True),
        ):
            changed = copy.deepcopy(committed)
            changed["terminal_state"] = state
            changed["postconditions_verified"] = postconditions
            changed["recovery_required"] = recovery
            changed["result_sha256"] = contract.stable_sha256_v2(
                {
                    key: item
                    for key, item in changed.items()
                    if key != "result_sha256"
                }
            )
            self.assertTrue(
                contract.transaction_result_valid_v2(changed, request),
                state,
            )

    def test_recovery_batch_is_resumable_and_rejects_out_of_order_result(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2(prepared_count=2)
        snapshot = backend.snapshot_offline()
        catalog = backend.list_prepared_transactions_offline()
        batch = contract.build_resumable_recovery_batch_offline_v2(
            snapshot, catalog,
            batch_epoch=harness._sha("test-batch-epoch"),
            deadline_epoch=harness.SYNTHETIC_NOW_V2 + 60,
        )
        records = {item["record_sha256"]: item for item in catalog["records"]}
        wrong_record = records[batch["item_record_sha256s"][1]]
        request = harness.build_synthetic_recovery_request_v2(wrong_record, batch, checkpoint_index=0)
        result = harness.build_synthetic_recovery_result_v2(request)

        with self.assertRaisesRegex(ValueError, "RECOVERY_RESULT_OUT_OF_ORDER"):
            contract.advance_recovery_batch_offline_v2(batch, result)

    def test_recovery_batch_rejects_resealed_claim_of_production_evidence(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2(prepared_count=1)
        snapshot = backend.snapshot_offline()
        catalog = backend.list_prepared_transactions_offline()
        batch = contract.build_resumable_recovery_batch_offline_v2(
            snapshot, catalog,
            batch_epoch=harness._sha("write-claim-test-batch"),
            deadline_epoch=harness.SYNTHETIC_NOW_V2 + 60,
        )
        record = catalog["records"][0]
        request = harness.build_synthetic_recovery_request_v2(record, batch, checkpoint_index=0)
        result = harness.build_synthetic_recovery_result_v2(request)
        result["production_evidence"] = True
        result["result_sha256"] = contract.stable_sha256_v2(
            {key: value for key, value in result.items() if key != "result_sha256"}
        )

        with self.assertRaisesRegex(ValueError, "RECOVERY_RESULT_INVALID"):
            contract.advance_recovery_batch_offline_v2(batch, result)

    def test_backend_interface_has_no_runtime_or_production_methods(self) -> None:
        backend = harness.InMemoryEvidenceDurableRawTransactionBackendV2()

        for name in ("apply", "execute", "install", "start", "activate", "open_registry"):
            self.assertFalse(hasattr(backend, name), name)


if __name__ == "__main__":
    unittest.main()
