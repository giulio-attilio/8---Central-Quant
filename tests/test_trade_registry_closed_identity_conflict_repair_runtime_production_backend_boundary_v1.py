from __future__ import annotations

import ast
import copy
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProductionBackendBoundaryV1Tests(unittest.TestCase):
    def _recovery_fixture(self) -> dict:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            saved = dict(values)
        envelope = saved["production_envelope"]
        invocation = saved["invocation_command"]
        ambiguous_receipt = harness.build_synthetic_backend_terminal_receipt_v1(
            invocation, "AMBIGUOUS"
        )
        normalized = saved["backend_boundary"].normalize_terminal_receipt_offline(
            envelope=envelope,
            invocation_command=invocation,
            terminal_receipt=ambiguous_receipt,
        )
        recovery_envelope = (
            envelope_contract.build_recovery_envelope_contract_offline_v1(
                envelope,
                normalized["terminal_result"],
                fresh_maintenance_epoch=_sha256_text("fresh-boundary-test-epoch"),
                expires_at_epoch=harness._NOW + 20,
            )
        )
        grant = contract.build_synthetic_recovery_authorization_grant_v1(
            invocation,
            recovery_envelope,
            envelope,
            saved["backend_boundary_attestation"],
            issued_at_epoch=harness._NOW - 1,
            expires_at_epoch=harness._NOW + 15,
        )
        return {
            **saved,
            "ambiguous_terminal_result": normalized["terminal_result"],
            "recovery_envelope": recovery_envelope,
            "recovery_grant": grant,
            "fresh_permit": harness.build_fresh_synthetic_maintenance_permit_v1(
                "fresh-boundary-test-epoch"
            ),
        }

    def _project_recovery(self, values: dict, token) -> dict:
        return values["backend_boundary"].project_recovery_offline(
            envelope=values["production_envelope"],
            invocation_command=values["invocation_command"],
            recovery_envelope=values["recovery_envelope"],
            ambiguous_terminal_result=values["ambiguous_terminal_result"],
            backend_boundary_attestation=values[
                "backend_boundary_attestation"
            ],
            fresh_maintenance_permit=values["fresh_permit"],
            fresh_live_lease_token=token,
            recovery_authorization_grant=values["recovery_grant"],
        )

    def test_complete_harness_passes_with_every_production_surface_denied(self) -> None:
        result = harness.run_synthetic_production_backend_boundary_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["upstream_and_production_capabilities_distinct"])
        self.assertTrue(result["committed_terminal_normalized"])
        self.assertTrue(result["ambiguous_terminal_requires_recovery"])
        self.assertTrue(result["recovery_authorization_replay_blocked"])
        for key in (
            "production_authority",
            "backend_referenced",
            "backend_called",
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

    def test_boundary_attestation_separates_capability_domains_exactly(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            attestation = values["backend_boundary_attestation"]
            command = values["invocation_command"].command

        self.assertEqual(set(attestation), contract._BOUNDARY_ATTESTATION_KEYS)
        self.assertEqual(
            attestation["upstream_synthetic_capability_attestation_sha256"],
            command["upstream_synthetic_capability_attestation_sha256"],
        )
        self.assertEqual(
            attestation["production_backend_capability_attestation_sha256"],
            command["production_backend_capability_attestation_sha256"],
        )
        self.assertNotEqual(
            attestation["upstream_synthetic_capability_attestation_sha256"],
            attestation["production_backend_capability_attestation_sha256"],
        )
        self.assertFalse(attestation["production_backend_referenced"])
        self.assertFalse(attestation["production_authority"])

    def test_same_upstream_and_production_capability_is_rejected(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            envelope = values["production_envelope"]
            upstream_sha = envelope.request[
                "backend_capability_attestation_sha256"
            ]

        with self.assertRaises(ValueError):
            contract.build_production_backend_boundary_attestation_offline_v1(
                envelope,
                backend_kind="DURABLE_RAW_TRANSACTION_BACKEND_V1",
                production_backend_capability_attestation_sha256=upstream_sha,
            )

    def test_resealed_boundary_attestation_drift_fails_closed(self) -> None:
        for field, replacement in (
            ("storage_scope", "TEMPORARY_TEST"),
            ("production_backend_referenced", True),
            ("production_authority", True),
            ("recovery_supported", False),
        ):
            with self.subTest(field=field):
                with harness.synthetic_production_backend_boundary_context_v1() as values:
                    attestation = dict(values["backend_boundary_attestation"])
                    attestation[field] = replacement
                    attestation["attestation_sha256"] = (
                        contract.production_backend_boundary_attestation_sha256_v1(
                            attestation
                        )
                    )
                    result = values["backend_boundary"].project_invocation_offline(
                        envelope=values["production_envelope"],
                        backend_boundary_attestation=attestation,
                        maintenance_permit=values["maintenance_permit"],
                        live_lease_token=values["live_lease_token"],
                    )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"],
                    ["PRODUCTION_BACKEND_BOUNDARY_ATTESTATION_INVALID"],
                )

    def test_boundary_is_default_off(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            boundary = contract.DormantProductionBackendBoundaryV1(
                clock=lambda: harness._NOW,
                lease_witness=values["lease_witness"],
                recovery_authorization_ledger=contract.InMemorySyntheticRecoveryAuthorizationLedgerV1(),
            )
            result = boundary.project_invocation_offline(
                envelope=values["production_envelope"],
                backend_boundary_attestation=values[
                    "backend_boundary_attestation"
                ],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PRODUCTION_BACKEND_BOUNDARY_DEFAULT_OFF"]
        )

    def test_invocation_requires_the_same_live_lease(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            saved = dict(values)
        result = saved["backend_boundary"].project_invocation_offline(
            envelope=saved["production_envelope"],
            backend_boundary_attestation=saved["backend_boundary_attestation"],
            maintenance_permit=saved["maintenance_permit"],
            live_lease_token=saved["live_lease_token"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SAME_LIVE_MAINTENANCE_LEASE_REQUIRED"])

    def test_expired_invocation_deadline_fails_closed(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            envelope = values["production_envelope"]
            boundary = contract.DormantProductionBackendBoundaryV1(
                config=contract.DormantProductionBackendBoundaryConfigV1(
                    enabled=True,
                    scope_attestation=contract.OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1,
                ),
                clock=lambda: envelope.expires_at_epoch,
                lease_witness=values["lease_witness"],
                recovery_authorization_ledger=contract.InMemorySyntheticRecoveryAuthorizationLedgerV1(),
            )
            result = boundary.project_invocation_offline(
                envelope=envelope,
                backend_boundary_attestation=values[
                    "backend_boundary_attestation"
                ],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PRODUCTION_BACKEND_BOUNDARY_DEADLINE_EXPIRED"]
        )

    def test_invocation_command_has_exact_schema_and_no_call_authority(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            invocation = values["invocation_command"]

        self.assertEqual(set(invocation.command), contract._INVOCATION_COMMAND_KEYS)
        self.assertTrue(contract._invocation_command_valid(invocation)[0])
        self.assertFalse(invocation.command["backend_call_allowed"])
        self.assertFalse(invocation.command["production_authority"])
        self.assertEqual(
            invocation.command["command_sha256"],
            contract.production_backend_invocation_command_sha256_v1(
                invocation.command
            ),
        )

    def test_resealed_internal_invocation_tampering_is_rejected(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            invocation = values["invocation_command"]
        command = copy.deepcopy(dict(invocation.command))
        command["maintenance_attestation"]["registered_writer_count"] = 18
        command["command_sha256"] = (
            contract.production_backend_invocation_command_sha256_v1(command)
        )
        tampered = contract.ProtectedProductionBackendInvocationCommandV1(
            request_sha256=invocation.request_sha256,
            transaction_sha256=invocation.transaction_sha256,
            backend_boundary_attestation_sha256=invocation.backend_boundary_attestation_sha256,
            backend_instance_sha256=invocation.backend_instance_sha256,
            deadline_epoch=invocation.deadline_epoch,
            command=command,
            command_sha256=command["command_sha256"],
        )

        self.assertFalse(contract._invocation_command_valid(tampered)[0])

    def test_committed_and_ambiguous_terminal_receipts_normalize(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            saved = dict(values)
        for state, recovery_required in (("COMMITTED", False), ("AMBIGUOUS", True)):
            with self.subTest(state=state):
                receipt = harness.build_synthetic_backend_terminal_receipt_v1(
                    saved["invocation_command"], state
                )
                result = saved["backend_boundary"].normalize_terminal_receipt_offline(
                    envelope=saved["production_envelope"],
                    invocation_command=saved["invocation_command"],
                    terminal_receipt=receipt,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(result["terminal_state"], state)
                self.assertEqual(result["recovery_required"], recovery_required)
                self.assertFalse(result["terminal_result"]["production_evidence"])

    def test_terminal_receipt_drift_fails_closed_even_when_resealed(self) -> None:
        for field, replacement in (
            ("deadline_observed", False),
            ("production_evidence", True),
            ("write_executed", True),
            ("backend_instance_sha256", _sha256_text("wrong-backend")),
        ):
            with self.subTest(field=field):
                with harness.synthetic_production_backend_boundary_context_v1() as values:
                    saved = dict(values)
                receipt = harness.build_synthetic_backend_terminal_receipt_v1(
                    saved["invocation_command"], "COMMITTED"
                )
                receipt[field] = replacement
                receipt["receipt_sha256"] = (
                    contract.production_backend_terminal_receipt_sha256_v1(receipt)
                )
                result = saved["backend_boundary"].normalize_terminal_receipt_offline(
                    envelope=saved["production_envelope"],
                    invocation_command=saved["invocation_command"],
                    terminal_receipt=receipt,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"],
                    ["PRODUCTION_BACKEND_TERMINAL_RECEIPT_INVALID"],
                )

    def test_terminal_receipt_at_or_after_deadline_is_rejected(self) -> None:
        with harness.synthetic_production_backend_boundary_context_v1() as values:
            saved = dict(values)
        invocation = saved["invocation_command"]
        receipt = harness.build_synthetic_backend_terminal_receipt_v1(
            invocation, "COMMITTED"
        )
        for now_epoch in (invocation.deadline_epoch, invocation.deadline_epoch + 1):
            with self.subTest(now_epoch=now_epoch):
                late_boundary = contract.DormantProductionBackendBoundaryV1(
                    config=contract.DormantProductionBackendBoundaryConfigV1(
                        enabled=True,
                        scope_attestation=contract.OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1,
                    ),
                    clock=lambda now_epoch=now_epoch: now_epoch,
                    lease_witness=saved["lease_witness"],
                    recovery_authorization_ledger=contract.InMemorySyntheticRecoveryAuthorizationLedgerV1(),
                )
                result = late_boundary.normalize_terminal_receipt_offline(
                    envelope=saved["production_envelope"],
                    invocation_command=invocation,
                    terminal_receipt=receipt,
                )
                self.assertFalse(result["ok"])
                self.assertEqual(
                    result["reasons"],
                    ["PRODUCTION_BACKEND_TERMINAL_RECEIPT_INVALID"],
                )

    def test_recovery_requires_a_fresh_live_lease(self) -> None:
        values = self._recovery_fixture()
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            saved_token = token
        result = self._project_recovery(values, saved_token)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["FRESH_LIVE_MAINTENANCE_LEASE_REQUIRED"])
        self.assertEqual(
            values["recovery_authorization_ledger"].snapshot()["record_count"],
            0,
        )

    def test_recovery_authorization_is_one_shot(self) -> None:
        values = self._recovery_fixture()
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            first = self._project_recovery(values, token)
            second = self._project_recovery(values, token)

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assertEqual(
            second["reasons"],
            ["RECOVERY_AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID"],
        )
        self.assertEqual(
            values["recovery_authorization_ledger"].snapshot()["record_count"],
            1,
        )

    def test_resealed_recovery_authorization_drift_fails_closed(self) -> None:
        values = self._recovery_fixture()
        grant = dict(values["recovery_grant"])
        grant["production_authority"] = True
        grant["grant_sha256"] = contract.production_backend_recovery_grant_sha256_v1(
            grant
        )
        values["recovery_grant"] = grant
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            result = self._project_recovery(values, token)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["SYNTHETIC_RECOVERY_AUTHORIZATION_INVALID"]
        )

    def test_recovery_command_binds_full_fresh_maintenance_and_both_capabilities(self) -> None:
        values = self._recovery_fixture()
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            result = self._project_recovery(values, token)

        self.assertTrue(result["ok"])
        protected = result["protected_recovery_command"]
        command = protected.command
        self.assertEqual(set(command), contract._RECOVERY_COMMAND_KEYS)
        self.assertTrue(contract._recovery_command_valid(protected)[0])
        self.assertEqual(
            command["fresh_maintenance_attestation"]["maintenance_epoch"],
            values["fresh_permit"].maintenance_epoch,
        )
        self.assertNotEqual(
            command["fresh_maintenance_attestation"]["maintenance_epoch"],
            command["previous_maintenance_epoch"],
        )
        self.assertNotEqual(
            command["upstream_synthetic_capability_attestation_sha256"],
            command["production_backend_capability_attestation_sha256"],
        )
        self.assertFalse(command["backend_call_allowed"])

    def test_resealed_internal_recovery_command_tampering_is_rejected(self) -> None:
        values = self._recovery_fixture()
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            result = self._project_recovery(values, token)
        original = result["protected_recovery_command"]
        command = copy.deepcopy(dict(original.command))
        command["fresh_maintenance_attestation"]["registered_writer_count"] = 18
        command["command_sha256"] = (
            contract.production_backend_recovery_command_sha256_v1(command)
        )
        tampered = contract.ProtectedProductionBackendRecoveryCommandV1(
            original_request_sha256=original.original_request_sha256,
            transaction_sha256=original.transaction_sha256,
            backend_boundary_attestation_sha256=original.backend_boundary_attestation_sha256,
            fresh_maintenance_epoch=original.fresh_maintenance_epoch,
            deadline_epoch=original.deadline_epoch,
            command=command,
            command_sha256=command["command_sha256"],
        )

        self.assertFalse(contract._recovery_command_valid(tampered)[0])

    def test_protected_commands_hide_payload_and_expose_no_execution_method(self) -> None:
        values = self._recovery_fixture()
        witness = values["lease_witness"]
        with witness.hold_offline(
            values["fresh_permit"], expires_at_epoch=harness._NOW + 20
        ) as token:
            result = self._project_recovery(values, token)
        recovery = result["protected_recovery_command"]
        invocation = values["invocation_command"]

        self.assertEqual(
            repr(invocation),
            "ProtectedProductionBackendInvocationCommandV1(<protected>)",
        )
        self.assertEqual(
            repr(recovery),
            "ProtectedProductionBackendRecoveryCommandV1(<protected>)",
        )
        for value in (invocation, recovery):
            for method in ("apply", "invoke", "execute", "commit", "reconcile"):
                self.assertFalse(hasattr(value, method), method)

    def test_deadline_bounds_are_fail_closed(self) -> None:
        for invalid in (0, 301):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    contract.DormantProductionBackendBoundaryConfigV1(
                        max_deadline_seconds=invalid
                    )

    def test_contract_and_harness_have_no_io_runtime_or_backend_calls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = (
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1.py",
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_harness_v1.py",
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
            "reconcile_attested_transaction",
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
