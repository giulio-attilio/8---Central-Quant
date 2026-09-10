from __future__ import annotations

import copy
import unittest
from unittest import mock

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_harness_v2 as harness


class PhysicalTerminalEvidenceV2Tests(unittest.TestCase):
    def test_complete_harness_preserves_physical_write_semantics(self) -> None:
        result = harness.run_physical_terminal_evidence_harness_v2()

        self.assertTrue(result["ok"])
        self.assertTrue(result["apply_receipt_valid"])
        self.assertTrue(result["recovery_receipt_valid"])
        self.assertTrue(result["wal_and_catalog_record_hashes_distinct"])
        self.assertTrue(result["protected_repr_verified"])
        self.assertTrue(result["temporary_registry_write_observed"])
        self.assertTrue(result["recovery_wal_only_write_observed"])
        self.assertTrue(result["temporary_storage_only"])
        self.assertTrue(result["no_order_sent"])
        for key in (
            "durability_verified", "production_evidence", "production_authority",
            "runtime_integrated", "activation_allowed", "live_allowed",
            "real_registry_accessed", "network_accessed", "broker_called",
        ):
            self.assertFalse(result[key], key)

    def test_port_is_default_off_and_does_not_inspect_inputs(self) -> None:
        port = contract.PhysicalTerminalEvidencePortV2()

        result = port.normalize_apply_offline(snapshot={}, request={}, result={})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PHYSICAL_TERMINAL_EVIDENCE_DEFAULT_OFF")
        self.assertIsNone(result["protected_receipt"])

    def test_protected_receipt_rejects_resealed_production_authority(self) -> None:
        captured = []
        original = contract.PhysicalTerminalEvidencePortV2._protect

        def capture(port, receipt):
            result = original(port, receipt)
            captured.append(result["protected_receipt"])
            return result

        with mock.patch.object(
            contract.PhysicalTerminalEvidencePortV2, "_protect", capture
        ):
            result = harness.run_physical_terminal_evidence_harness_v2()
        self.assertTrue(result["ok"])
        protected = captured[0]
        changed = copy.deepcopy(dict(protected.receipt))
        changed["production_authority"] = True
        changed["receipt_sha256"] = (
            contract.physical_terminal_evidence_receipt_sha256_v2(changed)
        )
        tampered = contract.ProtectedPhysicalTerminalEvidenceReceiptV2(
            operation=protected.operation,
            transaction_sha256=protected.transaction_sha256,
            terminal_state=protected.terminal_state,
            receipt=changed,
            receipt_sha256=changed["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_physical_terminal_evidence_valid_v2(tampered)
        )

    def test_receipt_schema_contains_no_raw_candidate_document(self) -> None:
        forbidden = {
            "candidate_raw_document_utf8", "candidate_registry", "raw_bytes",
            "storage_root", "target_path",
        }

        self.assertTrue(forbidden.isdisjoint(contract._RECEIPT_KEYS))

    def test_receipt_hash_changes_when_write_semantics_change(self) -> None:
        base = {key: None for key in contract._RECEIPT_KEYS}
        base["write_executed"] = False
        first = contract.physical_terminal_evidence_receipt_sha256_v2(base)
        changed = copy.deepcopy(base)
        changed["write_executed"] = True
        second = contract.physical_terminal_evidence_receipt_sha256_v2(changed)

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
