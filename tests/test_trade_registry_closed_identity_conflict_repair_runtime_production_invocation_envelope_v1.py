from __future__ import annotations

import ast
import copy
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_harness_v1 as harness


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProductionInvocationEnvelopeV1Tests(unittest.TestCase):
    def test_harness_passes_without_production_authority(self) -> None:
        result = harness.run_synthetic_production_invocation_envelope_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["production_request_projected"])
        self.assertTrue(result["authorization_replay_blocked"])
        for key in (
            "production_authorization_valid",
            "production_terminal_verified",
            "backend_referenced",
            "production_store_called",
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
            self.assertFalse(result[key], key)
        self.assertTrue(result["no_order_sent"])

    def test_projection_uses_exact_production_shaped_schema(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)

        self.assertTrue(result["ok"])
        envelope = result["protected_envelope"]
        request = envelope.request
        self.assertEqual(set(request), contract._PRODUCTION_REQUEST_KEYS)
        self.assertEqual(request["request_version"], contract.PRODUCTION_REQUEST_VERSION_V1)
        self.assertEqual(
            request["scope_attestation"],
            contract.PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1,
        )
        self.assertEqual(
            request["request_sha256"], contract.production_request_sha256_v1(request)
        )
        self.assertTrue(contract._protected_request_valid(envelope)[0])

    def test_projection_preserves_upstream_identity_but_mints_distinct_transaction(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
            intent = values["consumer_result"]["protected_intent"]

        envelope = result["protected_envelope"]
        self.assertEqual(envelope.upstream_raw_transaction_sha256, intent.raw_transaction_sha256)
        self.assertEqual(
            envelope.request["upstream_raw_transaction_sha256"],
            intent.raw_transaction_sha256,
        )
        self.assertNotEqual(
            envelope.production_transaction_sha256,
            envelope.upstream_raw_transaction_sha256,
        )

    def test_authorization_is_consumed_once_and_replay_fails_closed(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            first = harness.project_synthetic_production_invocation_envelope_v1(values)
            second = harness.project_synthetic_production_invocation_envelope_v1(values)
            snapshot = values["authorization_ledger"].snapshot()

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(
            second["reasons"],
            ["AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID"],
        )
        self.assertEqual(snapshot["record_count"], 1)
        self.assertFalse(snapshot["durable"])
        self.assertFalse(snapshot["production_authority"])

    def test_default_off_does_not_consume_authorization(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            ledger = contract.InMemorySyntheticAuthorizationConsumptionLedgerV1()
            builder = contract.DormantProductionInvocationEnvelopeBuilderV1(
                authorization_ledger=ledger,
                lease_witness=values["lease_witness"],
                clock=lambda: harness._NOW,
            )
            result = builder.project_offline(
                consumer_result=values["consumer_result"],
                adapter_result=values["adapter_result"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
                backend_identity_attestation=values["backend_identity_attestation"],
                authorization_grant=values["authorization_grant"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["ENVELOPE_BUILDER_DEFAULT_OFF"])
        self.assertEqual(ledger.snapshot()["record_count"], 0)

    def test_offline_scope_is_mandatory(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            ledger = contract.InMemorySyntheticAuthorizationConsumptionLedgerV1()
            builder = contract.DormantProductionInvocationEnvelopeBuilderV1(
                config=contract.DormantProductionInvocationEnvelopeConfigV1(
                    enabled=True,
                    scope_attestation="WRONG",
                ),
                authorization_ledger=ledger,
                lease_witness=values["lease_witness"],
                clock=lambda: harness._NOW,
            )
            result = builder.project_offline(
                consumer_result=values["consumer_result"],
                adapter_result=values["adapter_result"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
                backend_identity_attestation=values["backend_identity_attestation"],
                authorization_grant=values["authorization_grant"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["ENVELOPE_BUILDER_OFFLINE_SCOPE_REQUIRED"])
        self.assertEqual(ledger.snapshot()["record_count"], 0)

    def test_backend_identity_drift_fails_closed_even_when_resealed(self) -> None:
        for field, value in (
            ("storage_scope", "TEMPORARY_TEST"),
            ("production_backend_referenced", True),
            ("synthetic_only", False),
            ("backend_kind", "invalid lower-case"),
        ):
            with self.subTest(field=field):
                with harness.synthetic_production_invocation_envelope_context_v1() as values:
                    backend = dict(values["backend_identity_attestation"])
                    backend[field] = value
                    backend["attestation_sha256"] = (
                        contract.backend_identity_attestation_sha256_v1(backend)
                    )
                    result = values["envelope_builder"].project_offline(
                        consumer_result=values["consumer_result"],
                        adapter_result=values["adapter_result"],
                        maintenance_permit=values["maintenance_permit"],
                        live_lease_token=values["live_lease_token"],
                        backend_identity_attestation=backend,
                        authorization_grant=values["authorization_grant"],
                    )
                self.assertFalse(result["ok"])
                self.assertEqual(result["reasons"], ["BACKEND_IDENTITY_ATTESTATION_INVALID"])

    def test_authorization_drift_fails_closed_even_when_resealed(self) -> None:
        for field, value in (
            ("max_consumption_count", 2),
            ("production_signature_verified", True),
            ("production_authority", True),
            ("subject_binding_sha256", _sha256_text("wrong-subject")),
            ("expires_at_epoch", harness._NOW),
        ):
            with self.subTest(field=field):
                with harness.synthetic_production_invocation_envelope_context_v1() as values:
                    grant = dict(values["authorization_grant"])
                    grant[field] = value
                    grant["grant_sha256"] = contract.authorization_grant_sha256_v1(grant)
                    result = values["envelope_builder"].project_offline(
                        consumer_result=values["consumer_result"],
                        adapter_result=values["adapter_result"],
                        maintenance_permit=values["maintenance_permit"],
                        live_lease_token=values["live_lease_token"],
                        backend_identity_attestation=values["backend_identity_attestation"],
                        authorization_grant=grant,
                    )
                self.assertFalse(result["ok"])
                self.assertEqual(result["reasons"], ["SYNTHETIC_AUTHORIZATION_GRANT_INVALID"])

    def test_expired_live_lease_cannot_project(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            saved = dict(values)
        result = saved["envelope_builder"].project_offline(
            consumer_result=saved["consumer_result"],
            adapter_result=saved["adapter_result"],
            maintenance_permit=saved["maintenance_permit"],
            live_lease_token=saved["live_lease_token"],
            backend_identity_attestation=saved["backend_identity_attestation"],
            authorization_grant=saved["authorization_grant"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SAME_LIVE_MAINTENANCE_LEASE_REQUIRED"])
        self.assertEqual(saved["authorization_ledger"].snapshot()["record_count"], 0)

    def test_request_tampering_invalidates_terminal_evaluation(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        tampered_request = copy.deepcopy(dict(envelope.request))
        tampered_request["expected_generation_token"] = "tampered"
        tampered = contract.ProtectedProductionInvocationEnvelopeV1(
            subject_binding_sha256=envelope.subject_binding_sha256,
            authorization_consumption_receipt_sha256=envelope.authorization_consumption_receipt_sha256,
            upstream_raw_transaction_sha256=envelope.upstream_raw_transaction_sha256,
            production_transaction_sha256=envelope.production_transaction_sha256,
            backend_instance_sha256=envelope.backend_instance_sha256,
            registry_path_binding_sha256=envelope.registry_path_binding_sha256,
            expires_at_epoch=envelope.expires_at_epoch,
            request=tampered_request,
            envelope_sha256=envelope.envelope_sha256,
        )
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "COMMITTED")

        self.assertFalse(contract._protected_request_valid(tampered)[0])
        evaluation = contract.evaluate_terminal_result_contract_offline_v1(tampered, terminal)
        self.assertFalse(evaluation["ok"])
        self.assertEqual(evaluation["reason"], "TERMINAL_CONTRACT_INPUT_INVALID")

    def test_committed_terminal_contract_does_not_claim_production_evidence(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "COMMITTED")
        evaluation = contract.evaluate_terminal_result_contract_offline_v1(envelope, terminal)

        self.assertTrue(evaluation["ok"])
        self.assertEqual(evaluation["terminal_state"], "COMMITTED")
        self.assertFalse(evaluation["recovery_required"])
        self.assertFalse(evaluation["production_terminal_verified"])
        self.assertFalse(evaluation["production_authority"])
        self.assertFalse(terminal["write_executed"])

    def test_ambiguous_terminal_requires_recovery(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")
        evaluation = contract.evaluate_terminal_result_contract_offline_v1(envelope, terminal)

        self.assertTrue(evaluation["ok"])
        self.assertTrue(evaluation["recovery_required"])
        self.assertEqual(evaluation["terminal_state"], "AMBIGUOUS")

    def test_inconsistent_or_extra_terminal_fields_fail_closed(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")
        terminal["recovery_required"] = False
        terminal["result_sha256"] = contract.terminal_result_sha256_v1(terminal)
        evaluation = contract.evaluate_terminal_result_contract_offline_v1(envelope, terminal)
        self.assertFalse(evaluation["ok"])

        terminal = harness.build_synthetic_terminal_result_v1(envelope, "COMMITTED")
        terminal["unexpected"] = True
        terminal["result_sha256"] = contract.terminal_result_sha256_v1(terminal)
        evaluation = contract.evaluate_terminal_result_contract_offline_v1(envelope, terminal)
        self.assertFalse(evaluation["ok"])

    def test_recovery_requires_a_fresh_maintenance_epoch(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")

        with self.assertRaises(ValueError):
            contract.build_recovery_envelope_contract_offline_v1(
                envelope,
                terminal,
                fresh_maintenance_epoch=envelope.request["maintenance_epoch"],
                expires_at_epoch=harness._NOW + 20,
            )

    def test_recovery_requires_a_positive_bounded_deadline(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")

        for invalid_deadline in (0, envelope.expires_at_epoch + 1):
            with self.subTest(invalid_deadline=invalid_deadline):
                with self.assertRaises(ValueError):
                    contract.build_recovery_envelope_contract_offline_v1(
                        envelope,
                        terminal,
                        fresh_maintenance_epoch=_sha256_text(
                            f"fresh-epoch-{invalid_deadline}"
                        ),
                        expires_at_epoch=invalid_deadline,
                    )

    def test_recovery_envelope_binds_original_request_and_backend(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")
        recovery = contract.build_recovery_envelope_contract_offline_v1(
            envelope,
            terminal,
            fresh_maintenance_epoch=_sha256_text("fresh-maintenance-epoch"),
            expires_at_epoch=harness._NOW + 20,
        )

        request = recovery.request
        self.assertEqual(set(request), contract._RECOVERY_REQUEST_KEYS)
        self.assertEqual(request["original_request_sha256"], envelope.request["request_sha256"])
        self.assertEqual(request["transaction_sha256"], envelope.production_transaction_sha256)
        self.assertEqual(request["backend_instance_sha256"], envelope.backend_instance_sha256)
        self.assertEqual(
            request["authorization_consumption_receipt_sha256"],
            envelope.authorization_consumption_receipt_sha256,
        )
        self.assertEqual(
            request["recovery_request_sha256"],
            contract.recovery_request_sha256_v1(request),
        )
        self.assertFalse(request["production_authority"])

    def test_protected_dtos_hide_payload_and_have_no_execution_methods(self) -> None:
        with harness.synthetic_production_invocation_envelope_context_v1() as values:
            result = harness.project_synthetic_production_invocation_envelope_v1(values)
        envelope = result["protected_envelope"]
        terminal = harness.build_synthetic_terminal_result_v1(envelope, "AMBIGUOUS")
        recovery = contract.build_recovery_envelope_contract_offline_v1(
            envelope,
            terminal,
            fresh_maintenance_epoch=_sha256_text("fresh-protected-epoch"),
            expires_at_epoch=harness._NOW + 20,
        )

        self.assertEqual(repr(envelope), "ProtectedProductionInvocationEnvelopeV1(<protected>)")
        self.assertEqual(repr(recovery), "ProtectedProductionRecoveryEnvelopeV1(<protected>)")
        for value in (envelope, recovery):
            for method in ("apply", "invoke", "execute", "commit", "reconcile"):
                self.assertFalse(hasattr(value, method), method)

    def test_ttl_bounds_are_fail_closed(self) -> None:
        for invalid in (0, 301):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    contract.DormantProductionInvocationEnvelopeConfigV1(
                        max_envelope_ttl_seconds=invalid
                    )

    def test_modules_have_no_runtime_or_io_imports_and_no_backend_call(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = (
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1.py",
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_harness_v1.py",
        )
        forbidden_imports = {
            "main",
            "os",
            "pathlib",
            "requests",
            "httpx",
            "urllib",
            "socket",
            "subprocess",
            "sqlite3",
            "tempfile",
        }
        forbidden_calls = {
            "open",
            "urlopen",
            "create_connection",
            "apply_attested_transaction",
            "load_exact_raw_registry",
        }
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: set[str] = set()
            calls: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        calls.add(node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        calls.add(node.func.attr)
            self.assertFalse(imports & forbidden_imports, (path.name, imports & forbidden_imports))
            self.assertFalse(calls & forbidden_calls, (path.name, calls & forbidden_calls))


if __name__ == "__main__":
    unittest.main()
