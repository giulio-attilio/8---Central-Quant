from __future__ import annotations

import ast
import contextlib
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_harness_v1 as boundary_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProductionBackendStoreAdapterV1Tests(unittest.TestCase):
    def _adapter_for(
        self,
        values: dict,
        *,
        store=None,
        enabled: bool = True,
        scope: str | None = contract.OFFLINE_PRODUCTION_BACKEND_STORE_ADAPTER_SCOPE_ATTESTATION_V1,
        expected_snapshot_sha256: str | None = None,
        max_call_seconds: int = 300,
        clock=None,
    ) -> contract.DormantProductionBackendStoreAdapterV1:
        selected_store = store or values["store_double"]
        expected = (
            expected_snapshot_sha256
            if expected_snapshot_sha256 is not None
            else selected_store.snapshot()["snapshot_sha256"]
        )
        return contract.DormantProductionBackendStoreAdapterV1(
            config=contract.DormantProductionBackendStoreAdapterConfigV1(
                enabled=enabled,
                scope_attestation=scope,
                expected_store_snapshot_sha256=expected,
                max_call_seconds=max_call_seconds,
            ),
            clock=clock or (lambda: harness._NOW),
            lease_witness=values["lease_witness"],
            boundary=values["backend_boundary"],
            store_double=selected_store,
        )

    @contextlib.contextmanager
    def _recovery_ready(self, *, recovery_state: str = "COMMITTED"):
        with harness.synthetic_production_backend_store_adapter_context_v1(
            apply_terminal_state="AMBIGUOUS",
            recovery_terminal_state=recovery_state,
        ) as values:
            apply_result = harness.invoke_synthetic_store_adapter_v1(values)
            prepared = harness._prepare_synthetic_recovery_v1(
                {**values, "apply_result": apply_result}
            )
        witness = prepared["lease_witness"]
        permit = prepared["fresh_permit"]
        with witness.hold_offline(
            permit, expires_at_epoch=harness._NOW + 20
        ) as token:
            projection = prepared["backend_boundary"].project_recovery_offline(
                envelope=prepared["production_envelope"],
                invocation_command=prepared["invocation_command"],
                recovery_envelope=prepared["recovery_envelope"],
                ambiguous_terminal_result=apply_result["terminal_result"],
                backend_boundary_attestation=prepared[
                    "backend_boundary_attestation"
                ],
                fresh_maintenance_permit=permit,
                fresh_live_lease_token=token,
                recovery_authorization_grant=prepared["recovery_grant"],
            )
            self.assertTrue(projection["ok"])
            yield {
                **prepared,
                "apply_result": apply_result,
                "fresh_token": token,
                "recovery_command": projection["protected_recovery_command"],
            }

    def _recover(self, values: dict) -> dict:
        return values["store_adapter"].recover_offline(
            envelope=values["production_envelope"],
            invocation_command=values["invocation_command"],
            recovery_command=values["recovery_command"],
            fresh_maintenance_permit=values["fresh_permit"],
            fresh_live_lease_token=values["fresh_token"],
        )

    def test_complete_harness_passes_without_production_side_effects(self) -> None:
        result = harness.run_synthetic_production_backend_store_adapter_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["store_snapshot_bound_synthetic"])
        self.assertTrue(result["terminal_contract_normalized"])
        self.assertTrue(result["recovery_terminal_normalized"])
        for key in (
            "production_authority",
            "production_store_called",
            "production_backend_called",
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

    def test_store_snapshot_is_exact_hash_bound_and_non_durable(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            snapshot = values["store_double"].snapshot()
            command = values["invocation_command"].command

        self.assertEqual(set(snapshot), contract._SNAPSHOT_KEYS)
        self.assertEqual(
            snapshot["snapshot_sha256"],
            contract.synthetic_store_double_snapshot_sha256_v1(snapshot),
        )
        self.assertEqual(
            snapshot["production_backend_capability_attestation_sha256"],
            command["production_backend_capability_attestation_sha256"],
        )
        self.assertFalse(snapshot["durable"])
        self.assertFalse(snapshot["production_backend_referenced"])
        self.assertFalse(snapshot["production_authority"])

    def test_default_off_never_calls_store_double(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            adapter = self._adapter_for(values, enabled=False)
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )
            counters = values["store_double"].counters()

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PRODUCTION_BACKEND_STORE_ADAPTER_DEFAULT_OFF"]
        )
        self.assertEqual(counters["apply_call_count"], 0)

    def test_missing_offline_scope_never_calls_store_double(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            adapter = self._adapter_for(values, scope="WRONG")
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"],
            ["PRODUCTION_BACKEND_STORE_ADAPTER_OFFLINE_SCOPE_REQUIRED"],
        )

    def test_wrong_pinned_snapshot_fails_before_store_call(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            adapter = self._adapter_for(
                values,
                expected_snapshot_sha256=_sha256_text("wrong-store-snapshot"),
            )
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )
            counters = values["store_double"].counters()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_SNAPSHOT_BINDING_INVALID"])
        self.assertEqual(counters["apply_call_count"], 0)

    def test_capability_mismatch_fails_before_store_call(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            command = values["invocation_command"].command
            wrong_store = contract.InMemoryProductionBackendStoreDoubleV1(
                backend_instance_sha256=command["backend_instance_sha256"],
                registry_path_binding_sha256=command[
                    "registry_path_binding_sha256"
                ],
                production_backend_capability_attestation_sha256=_sha256_text(
                    "wrong-production-capability"
                ),
            )
            adapter = self._adapter_for(values, store=wrong_store)
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_SNAPSHOT_BINDING_INVALID"])
        self.assertEqual(wrong_store.counters()["apply_call_count"], 0)

    def test_released_lease_fails_before_store_call(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            saved = dict(values)
        result = saved["store_adapter"].invoke_offline(
            envelope=saved["production_envelope"],
            invocation_command=saved["invocation_command"],
            maintenance_permit=saved["maintenance_permit"],
            live_lease_token=saved["live_lease_token"],
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SAME_LIVE_MAINTENANCE_LEASE_REQUIRED"])
        self.assertEqual(saved["store_double"].counters()["apply_call_count"], 0)

    def test_expired_deadline_fails_before_store_call(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            deadline = values["invocation_command"].deadline_epoch
            adapter = self._adapter_for(values, clock=lambda: deadline)
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STORE_ADAPTER_INVOCATION_DEADLINE_EXPIRED"])
        self.assertEqual(values["store_double"].counters()["apply_call_count"], 0)

    def test_call_budget_is_enforced_before_store_call(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            adapter = self._adapter_for(values, max_call_seconds=1)
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STORE_ADAPTER_CALL_BUDGET_EXCEEDED"])
        self.assertEqual(values["store_double"].counters()["apply_call_count"], 0)

    def test_deadline_exceeded_during_call_fails_closed(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            deadline = values["invocation_command"].deadline_epoch
            times = iter((harness._NOW, deadline))
            adapter = self._adapter_for(values, clock=lambda: next(times))
            result = adapter.invoke_offline(
                envelope=values["production_envelope"],
                invocation_command=values["invocation_command"],
                maintenance_permit=values["maintenance_permit"],
                live_lease_token=values["live_lease_token"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STORE_ADAPTER_INVOCATION_DEADLINE_EXCEEDED"])
        self.assertEqual(values["store_double"].counters()["apply_call_count"], 1)

    def test_committed_result_is_normalized_to_envelope_contract(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            result = harness.invoke_synthetic_store_adapter_v1(values)

        self.assertTrue(result["ok"])
        self.assertEqual(result["terminal_state"], "COMMITTED")
        evaluation = envelope_contract.evaluate_terminal_result_contract_offline_v1(
            values["production_envelope"], result["terminal_result"]
        )
        self.assertTrue(evaluation["ok"])
        self.assertFalse(result["production_store_called"])
        self.assertFalse(result["write_executed"])

    def test_ambiguous_result_is_normalized_and_requires_recovery(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1(
            apply_terminal_state="AMBIGUOUS"
        ) as values:
            result = harness.invoke_synthetic_store_adapter_v1(values)

        self.assertTrue(result["ok"])
        self.assertEqual(result["terminal_state"], "AMBIGUOUS")
        self.assertTrue(result["recovery_required"])

    def test_replay_is_idempotent_inside_same_lease(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            first = harness.invoke_synthetic_store_adapter_v1(values)
            second = harness.invoke_synthetic_store_adapter_v1(values)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertFalse(first["store_double_result"]["idempotent_replay"])
        self.assertTrue(second["store_double_result"]["idempotent_replay"])

    def test_malformed_store_result_fails_closed(self) -> None:
        with harness.synthetic_production_backend_store_adapter_context_v1() as values:
            values["store_double"]._apply_state = "UNKNOWN"
            result = harness.invoke_synthetic_store_adapter_v1(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_DOUBLE_RESULT_INVALID"])

    def test_recovery_requires_current_fresh_lease(self) -> None:
        with self._recovery_ready() as values:
            saved = dict(values)
        result = self._recover(saved)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["FRESH_LIVE_MAINTENANCE_LEASE_REQUIRED"])
        self.assertEqual(saved["store_double"].counters()["recovery_call_count"], 0)

    def test_recovery_is_normalized_with_fresh_and_previous_epochs(self) -> None:
        with self._recovery_ready(recovery_state="ROLLED_BACK") as values:
            result = self._recover(values)

        self.assertTrue(result["ok"])
        self.assertTrue(result["recovery_terminal_normalized"])
        self.assertEqual(result["terminal_state"], "ROLLED_BACK")
        receipt = result["recovery_terminal_receipt"]
        self.assertEqual(set(receipt), contract._RECOVERY_TERMINAL_RECEIPT_KEYS)
        self.assertNotEqual(
            receipt["previous_maintenance_epoch"], receipt["fresh_maintenance_epoch"]
        )
        self.assertEqual(
            receipt["receipt_sha256"],
            contract.synthetic_recovery_terminal_receipt_sha256_v1(receipt),
        )
        self.assertTrue(
            envelope_contract.evaluate_terminal_result_contract_offline_v1(
                values["production_envelope"], result["terminal_result"]
            )["ok"]
        )

    def test_recovery_replay_is_idempotent_under_the_same_fresh_lease(self) -> None:
        with self._recovery_ready() as values:
            first = self._recover(values)
            second = self._recover(values)

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertFalse(first["store_double_result"]["idempotent_replay"])
        self.assertTrue(second["store_double_result"]["idempotent_replay"])

    def test_recovery_without_ambiguous_store_record_fails_closed(self) -> None:
        with self._recovery_ready() as values:
            values["store_double"]._records[
                values["invocation_command"].transaction_sha256
            ]["terminal_state"] = "COMMITTED"
            result = self._recover(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SYNTHETIC_STORE_DOUBLE_RECOVERY_FAILED_CLOSED"])

    def test_adapter_and_double_configs_are_bounded(self) -> None:
        for invalid in (0, 301):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    contract.DormantProductionBackendStoreAdapterConfigV1(
                        max_call_seconds=invalid
                    )
        with self.assertRaises(ValueError):
            contract.InMemoryProductionBackendStoreDoubleV1(
                backend_instance_sha256="bad",
                registry_path_binding_sha256="bad",
                production_backend_capability_attestation_sha256="bad",
            )

    def test_sources_import_no_runtime_production_store_or_io_modules(self) -> None:
        root = Path(__file__).resolve().parents[1]
        paths = (
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1.py",
            root
            / "trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_harness_v1.py",
        )
        forbidden = {
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
            "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1",
            "trade_registry_closed_identity_conflict_repair_production_provider_v1",
        }
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertFalse(imports & forbidden, (path.name, imports & forbidden))


if __name__ == "__main__":
    unittest.main()
