from __future__ import annotations

import ast
import copy
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_harness_v1 as harness


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rehash(value: dict) -> dict:
    value["evidence_sha256"] = contract.backend_terminal_evidence_sha256_v1(
        value
    )
    return value


class ProductionBackendTerminalReceiptPortV1Tests(unittest.TestCase):
    def _port(
        self,
        values: dict,
        *,
        enabled: bool = True,
        scope: str | None = contract.OFFLINE_PRODUCTION_BACKEND_TERMINAL_RECEIPT_PORT_SCOPE_ATTESTATION_V1,
        binding_pin: str | None = None,
        max_window: int = 60,
    ) -> contract.DormantProductionBackendTerminalReceiptPortV1:
        return contract.DormantProductionBackendTerminalReceiptPortV1(
            config=contract.DormantProductionBackendTerminalReceiptPortConfigV1(
                enabled=enabled,
                scope_attestation=scope,
                expected_binding_sha256=(
                    values["protected_binding"].binding_sha256
                    if binding_pin is None
                    else binding_pin
                ),
                max_completion_window_seconds=max_window,
            )
        )

    def _evidence(
        self,
        values: dict,
        *,
        operation: str = "APPLY",
        terminal_state: str = "COMMITTED",
    ) -> dict:
        return harness.build_synthetic_terminal_evidence_v1(
            values["protected_binding"],
            operation=operation,
            terminal_state=terminal_state,
        )

    def _normalize(
        self,
        values: dict,
        evidence: dict,
        *,
        port=None,
        now_epoch: int = harness._NOW,
        method: str | None = None,
    ) -> dict:
        selected_port = port or values["terminal_receipt_port"]
        selected_method = method or (
            "normalize_recovery_offline"
            if evidence.get("operation") == "RECOVERY"
            else "normalize_apply_offline"
        )
        return getattr(selected_port, selected_method)(
            protected_binding=values["protected_binding"],
            terminal_evidence=evidence,
            now_epoch=now_epoch,
        )

    def test_complete_harness_normalizes_apply_ambiguity_and_recovery(self) -> None:
        result = harness.run_synthetic_backend_terminal_receipt_port_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["apply_terminal_normalized_synthetic"])
        self.assertTrue(result["ambiguous_apply_requires_recovery_synthetic"])
        self.assertTrue(result["recovery_terminal_normalized_synthetic"])
        self.assertEqual(result["store_double_apply_call_count"], 0)
        self.assertEqual(result["store_double_recovery_call_count"], 0)
        for key in (
            "production_authority",
            "backend_called",
            "provider_called",
            "store_called",
            "runtime_integrated",
            "production_ready",
            "apply_allowed",
            "recovery_allowed",
            "activation_allowed",
            "live_allowed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[key], key)

    def test_terminal_evidence_uses_exact_schema_and_hash(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)

        self.assertEqual(set(evidence), contract._EVIDENCE_KEYS)
        self.assertEqual(
            evidence["evidence_sha256"],
            contract.backend_terminal_evidence_sha256_v1(evidence),
        )
        self.assertEqual(
            evidence["binding_sha256"], values["protected_binding"].binding_sha256
        )

    def test_default_off_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        port = self._port(values, enabled=False)
        result = self._normalize(values, self._evidence(values), port=port)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TERMINAL_RECEIPT_PORT_DEFAULT_OFF"])

    def test_wrong_scope_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        port = self._port(values, scope="EXPLICIT_RUNTIME")
        result = self._normalize(values, self._evidence(values), port=port)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["TERMINAL_RECEIPT_PORT_OFFLINE_SCOPE_REQUIRED"]
        )

    def test_missing_binding_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        port = self._port(values, binding_pin="")
        result = self._normalize(values, self._evidence(values), port=port)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["EXPECTED_PROTECTED_BINDING_SHA_REQUIRED"]
        )

    def test_wrong_binding_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        port = self._port(values, binding_pin=_sha256_text("wrong-binding"))
        result = self._normalize(values, self._evidence(values), port=port)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_PROVIDER_STORE_BINDING_INVALID"]
        )

    def test_tampered_protected_binding_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        values["protected_binding"].binding["runtime_integrated"] = True
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_PROVIDER_STORE_BINDING_INVALID"]
        )

    def test_apply_entrypoint_rejects_recovery_evidence(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values, operation="RECOVERY")
        result = self._normalize(
            values, evidence, method="normalize_apply_offline"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TERMINAL_RECEIPT_OPERATION_MISMATCH"])

    def test_recovery_entrypoint_rejects_apply_evidence(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        result = self._normalize(
            values, evidence, method="normalize_recovery_offline"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TERMINAL_RECEIPT_OPERATION_MISMATCH"])

    def test_expired_deadline_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        evidence["deadline_epoch"] = harness._NOW
        _rehash(evidence)
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_call_window_above_budget_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        evidence["deadline_epoch"] = harness._NOW + 61
        _rehash(evidence)
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_clock_mismatch_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        result = self._normalize(
            values, self._evidence(values), now_epoch=harness._NOW + 1
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_non_integer_clock_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        result = self._normalize(
            values, self._evidence(values), now_epoch="invalid"
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TERMINAL_RECEIPT_PORT_CLOCK_INVALID"])

    def test_apply_rejects_previous_maintenance_epoch(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        evidence["previous_maintenance_epoch"] = _sha256_text("unexpected-epoch")
        _rehash(evidence)
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_recovery_requires_previous_maintenance_epoch(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values, operation="RECOVERY")
        evidence["previous_maintenance_epoch"] = None
        _rehash(evidence)
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_recovery_requires_fresh_command_and_maintenance_epoch(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        cases = ("command", "maintenance")
        for case in cases:
            with self.subTest(case=case):
                evidence = self._evidence(values, operation="RECOVERY")
                if case == "command":
                    evidence["command_sha256"] = evidence[
                        "original_invocation_command_sha256"
                    ]
                else:
                    evidence["maintenance_epoch"] = evidence[
                        "previous_maintenance_epoch"
                    ]
                _rehash(evidence)
                result = self._normalize(values, evidence)
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"]
                )

    def test_recovery_rejects_ambiguous_terminal_state(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(
            values, operation="RECOVERY", terminal_state="AMBIGUOUS"
        )
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_ambiguous_apply_requires_recovery_and_unverified_postconditions(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values, terminal_state="AMBIGUOUS")
        result = self._normalize(values, evidence)
        store_result = result["protected_terminal_receipt"].receipt[
            "adapter_store_result"
        ]

        self.assertTrue(result["ok"])
        self.assertTrue(store_result["ambiguous"])
        self.assertTrue(store_result["recovery_required"])
        self.assertFalse(store_result["postconditions_verified"])

    def test_inconsistent_terminal_semantics_fail_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values, terminal_state="AMBIGUOUS")
        evidence["recovery_required"] = False
        _rehash(evidence)
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_evidence_hash_tamper_fails_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values)
        evidence["terminal_record_sha256"] = _sha256_text("tampered-terminal")
        result = self._normalize(values, evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"])

    def test_binding_identity_mismatches_fail_closed(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        fields = (
            "binding_sha256",
            "store_projection_sha256",
            "source_store_snapshot_sha256",
            "adapter_snapshot_sha256",
            "backend_instance_sha256",
        )
        for field_name in fields:
            with self.subTest(field_name=field_name):
                evidence = self._evidence(values)
                evidence[field_name] = _sha256_text(f"wrong-{field_name}")
                _rehash(evidence)
                result = self._normalize(values, evidence)
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"]
                )

    def test_synthetic_evidence_cannot_claim_durability_or_production(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        cases = ("durability_verified", "production_evidence", "write_executed")
        for field_name in cases:
            with self.subTest(field_name=field_name):
                evidence = self._evidence(values)
                evidence[field_name] = True
                _rehash(evidence)
                result = self._normalize(values, evidence)
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"], ["SYNTHETIC_TERMINAL_EVIDENCE_INVALID"]
                )

    def test_receipt_and_adapter_store_result_are_exact_hash_bound(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        result = self._normalize(values, self._evidence(values))
        protected = result["protected_terminal_receipt"]
        receipt = protected.receipt
        store_result = receipt["adapter_store_result"]

        self.assertTrue(result["ok"])
        self.assertEqual(set(receipt), contract._PORT_RECEIPT_KEYS)
        self.assertEqual(set(store_result), adapter_contract._STORE_RESULT_KEYS)
        self.assertEqual(
            receipt["receipt_sha256"],
            contract.backend_terminal_port_receipt_sha256_v1(receipt),
        )
        self.assertEqual(
            store_result["result_sha256"],
            adapter_contract.synthetic_store_double_result_sha256_v1(
                store_result
            ),
        )
        self.assertTrue(
            contract.protected_backend_terminal_port_receipt_valid_v1(protected)
        )
        self.assertEqual(
            repr(protected),
            "ProtectedProductionBackendTerminalPortReceiptV1(<protected>)",
        )
        self.assertNotIn(protected.transaction_sha256, repr(protected))

    def test_receipt_tamper_invalidates_validation(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        protected = self._normalize(values, self._evidence(values))[
            "protected_terminal_receipt"
        ]
        protected.receipt["runtime_integrated"] = True

        self.assertFalse(
            contract.protected_backend_terminal_port_receipt_valid_v1(protected)
        )

    def test_rehashed_recovery_receipt_cannot_reuse_original_command(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        evidence = self._evidence(values, operation="RECOVERY")
        protected = self._normalize(values, evidence)["protected_terminal_receipt"]
        receipt = copy.deepcopy(protected.receipt)
        receipt["command_sha256"] = receipt[
            "original_invocation_command_sha256"
        ]
        receipt["receipt_sha256"] = (
            contract.backend_terminal_port_receipt_sha256_v1(receipt)
        )
        rebuilt = contract.ProtectedProductionBackendTerminalPortReceiptV1(
            operation=receipt["operation"],
            binding_sha256=receipt["binding_sha256"],
            request_sha256=receipt["request_sha256"],
            transaction_sha256=receipt["transaction_sha256"],
            terminal_state=receipt["terminal_state"],
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_backend_terminal_port_receipt_valid_v1(rebuilt)
        )

    def test_rehashed_receipt_cannot_move_completion_past_deadline(self) -> None:
        values = harness.build_synthetic_terminal_receipt_port_context_v1()
        protected = self._normalize(values, self._evidence(values))[
            "protected_terminal_receipt"
        ]
        receipt = copy.deepcopy(protected.receipt)
        receipt["completed_at_epoch"] = receipt["deadline_epoch"]
        receipt["receipt_sha256"] = (
            contract.backend_terminal_port_receipt_sha256_v1(receipt)
        )
        rebuilt = contract.ProtectedProductionBackendTerminalPortReceiptV1(
            operation=receipt["operation"],
            binding_sha256=receipt["binding_sha256"],
            request_sha256=receipt["request_sha256"],
            transaction_sha256=receipt["transaction_sha256"],
            terminal_state=receipt["terminal_state"],
            receipt=receipt,
            receipt_sha256=receipt["receipt_sha256"],
        )

        self.assertFalse(
            contract.protected_backend_terminal_port_receipt_valid_v1(rebuilt)
        )

    def test_config_rejects_unbounded_completion_window(self) -> None:
        for max_window in (0, 301):
            with self.subTest(max_window=max_window):
                with self.assertRaises(ValueError):
                    contract.DormantProductionBackendTerminalReceiptPortConfigV1(
                        max_completion_window_seconds=max_window
                    )

    def test_contract_has_no_production_import_or_backend_call_surface(self) -> None:
        source = Path(contract.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_attributes = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }

        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_production_provider_v1",
            imported,
        )
        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1",
            imported,
        )
        self.assertNotIn("main", imported)
        self.assertTrue(
            {
                "apply_attested_transaction",
                "reconcile_attested_transaction",
                "load_exact_raw_registry",
                "invoke",
            }.isdisjoint(called_attributes)
        )


if __name__ == "__main__":
    unittest.main()
