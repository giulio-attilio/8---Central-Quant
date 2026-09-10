from __future__ import annotations

import ast
import copy
import hashlib
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_harness_v1 as harness


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ProductionBackendStartupRecoveryV1Tests(unittest.TestCase):
    def _recovery(
        self,
        values: dict,
        *,
        enabled: bool = True,
        scope: str | None = contract.OFFLINE_PRODUCTION_BACKEND_STARTUP_RECOVERY_SCOPE_ATTESTATION_V1,
        binding_pin: str | None = None,
        snapshot_pin: str | None = None,
        max_records: int = 64,
        max_seconds: int = 120,
        ledger_marker=Ellipsis,
    ) -> contract.DormantProductionBackendStartupRecoveryV1:
        selected_ledger = values["ledger"] if ledger_marker is Ellipsis else ledger_marker
        return contract.DormantProductionBackendStartupRecoveryV1(
            config=contract.DormantProductionBackendStartupRecoveryConfigV1(
                enabled=enabled,
                scope_attestation=scope,
                expected_binding_sha256=(
                    values["protected_binding"].binding_sha256
                    if binding_pin is None
                    else binding_pin
                ),
                expected_initial_ledger_snapshot_sha256=(
                    values["initial_ledger_snapshot"]["snapshot_sha256"]
                    if snapshot_pin is None
                    else snapshot_pin
                ),
                max_prepared_records=max_records,
                max_recovery_seconds=max_seconds,
            ),
            ledger=selected_ledger,
        )

    def _plan(self, values: dict, *, recovery=None, now_epoch=harness._NOW) -> dict:
        selected = recovery or values["startup_recovery"]
        return selected.plan_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            now_epoch=now_epoch,
        )

    def _receipts(self, values: dict, plan) -> list:
        return [
            harness.build_synthetic_recovery_receipt_for_plan_item_v1(values, item)
            for item in plan.plan["items"]
        ]

    def test_complete_harness_recovers_atomically_without_real_calls(self) -> None:
        result = harness.run_synthetic_backend_startup_recovery_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["prepared_records_planned_synthetic"], 2)
        self.assertTrue(result["failed_batch_left_ledger_unchanged_synthetic"])
        self.assertTrue(result["atomic_recovery_batch_verified_synthetic"])
        self.assertTrue(result["startup_clean_synthetic"])
        self.assertTrue(result["stale_plan_replay_rejected_synthetic"])
        self.assertEqual(result["store_double_apply_call_count"], 0)
        self.assertEqual(result["store_double_recovery_call_count"], 0)
        for key in (
            "production_authority",
            "backend_called",
            "provider_called",
            "store_called",
            "runtime_integrated",
            "production_ready",
            "activation_allowed",
            "live_allowed",
            "real_registry_accessed",
            "network_accessed",
            "broker_called",
            "write_executed",
            "registry_write",
        ):
            self.assertFalse(result[key], key)

    def test_prepared_record_is_exact_and_hash_bound(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=0
        )
        record = harness.build_synthetic_prepared_record_v1(
            values["protected_binding"], index=7
        )

        self.assertEqual(set(record), contract._RECORD_KEYS)
        self.assertTrue(contract.prepared_recovery_record_valid_v1(record))
        self.assertEqual(
            record["record_sha256"],
            contract.prepared_recovery_record_sha256_v1(record),
        )
        self.assertEqual(record["terminal_state"], "PREPARED")
        self.assertIsNone(record["terminal_receipt_sha256"])

    def test_duplicate_prepared_transaction_is_rejected(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=0
        )
        record = harness.build_synthetic_prepared_record_v1(
            values["protected_binding"], index=1
        )
        values["ledger"].seed_prepared_offline(record)

        with self.assertRaises(ValueError):
            values["ledger"].seed_prepared_offline(record)

    def test_ledger_snapshot_is_sorted_exact_and_hash_bound(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=0
        )
        for index in (3, 1, 2):
            values["ledger"].seed_prepared_offline(
                harness.build_synthetic_prepared_record_v1(
                    values["protected_binding"], index=index
                )
            )
        snapshot = values["ledger"].snapshot()

        self.assertEqual(set(snapshot), contract._LEDGER_SNAPSHOT_KEYS)
        self.assertTrue(contract._ledger_snapshot_valid(snapshot))
        self.assertEqual(
            [record["transaction_sha256"] for record in snapshot["records"]],
            sorted(record["transaction_sha256"] for record in snapshot["records"]),
        )
        self.assertEqual(
            snapshot["snapshot_sha256"],
            contract.prepared_recovery_ledger_snapshot_sha256_v1(snapshot),
        )

    def test_rehashed_record_from_another_binding_invalidates_snapshot(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=1
        )
        snapshot = values["ledger"].snapshot()
        snapshot["records"][0]["binding_sha256"] = _sha256_text(
            "other-ledger-binding"
        )
        snapshot["records"][0]["record_sha256"] = (
            contract.prepared_recovery_record_sha256_v1(snapshot["records"][0])
        )
        snapshot["snapshot_sha256"] = (
            contract.prepared_recovery_ledger_snapshot_sha256_v1(snapshot)
        )

        self.assertFalse(contract._ledger_snapshot_valid(snapshot))

    def test_default_off_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(values, recovery=self._recovery(values, enabled=False))

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STARTUP_RECOVERY_DEFAULT_OFF"])

    def test_wrong_scope_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(
            values, recovery=self._recovery(values, scope="EXPLICIT_RUNTIME")
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STARTUP_RECOVERY_OFFLINE_SCOPE_REQUIRED"])

    def test_wrong_binding_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(
            values,
            recovery=self._recovery(
                values, binding_pin=_sha256_text("wrong-binding")
            ),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STARTUP_RECOVERY_BINDING_INVALID"])

    def test_wrong_snapshot_pin_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(
            values,
            recovery=self._recovery(
                values, snapshot_pin=_sha256_text("wrong-ledger-snapshot")
            ),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["STARTUP_RECOVERY_LEDGER_SNAPSHOT_INVALID"]
        )

    def test_exact_synthetic_ledger_type_is_required(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(
            values, recovery=self._recovery(values, ledger_marker=object())
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EXACT_SYNTHETIC_RECOVERY_LEDGER_REQUIRED"])

    def test_invalid_clock_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        result = self._plan(values, now_epoch="invalid")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STARTUP_RECOVERY_CLOCK_INVALID"])

    def test_prepared_record_budget_fails_closed(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=2
        )
        result = self._plan(
            values, recovery=self._recovery(values, max_records=1)
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["STARTUP_RECOVERY_PREPARED_BUDGET_EXCEEDED"]
        )

    def test_plan_is_deterministic_exact_hash_bound_and_protected(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        first = self._plan(values)
        second = self._plan(values)
        plan = first["protected_recovery_plan"]

        self.assertTrue(first["ok"])
        self.assertEqual(set(plan.plan), contract._PLAN_KEYS)
        self.assertEqual(first["protected_recovery_plan"].plan_sha256, second["protected_recovery_plan"].plan_sha256)
        self.assertTrue(contract.protected_startup_recovery_plan_valid_v1(plan))
        self.assertEqual(
            plan.plan_sha256, contract.startup_recovery_plan_sha256_v1(plan.plan)
        )
        self.assertEqual(
            repr(plan),
            "ProtectedProductionBackendStartupRecoveryPlanV1(<protected>)",
        )
        self.assertNotIn(plan.binding_sha256, repr(plan))

    def test_plan_includes_every_prepared_record_once(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=3
        )
        plan = self._plan(values)["protected_recovery_plan"]
        transaction_ids = [item["transaction_sha256"] for item in plan.plan["items"]]

        self.assertEqual(plan.prepared_count, 3)
        self.assertEqual(transaction_ids, sorted(transaction_ids))
        self.assertEqual(len(set(transaction_ids)), 3)
        self.assertTrue(plan.plan["all_prepared_records_included"])

    def test_tampered_plan_is_rejected(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        plan = self._plan(values)["protected_recovery_plan"]
        plan.plan["atomic_batch_required"] = False

        self.assertFalse(contract.protected_startup_recovery_plan_valid_v1(plan))

    def test_empty_ledger_is_clean_without_mutation(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=0
        )
        planned = self._plan(values)
        plan = planned["protected_recovery_plan"]
        before = values["ledger"].snapshot()
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=[],
            now_epoch=harness._NOW + 1,
        )
        after = values["ledger"].snapshot()

        self.assertTrue(planned["startup_clean"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["startup_clean"])
        self.assertFalse(result["in_memory_ledger_mutated"])
        self.assertEqual(before["snapshot_sha256"], after["snapshot_sha256"])

    def test_missing_receipt_rejects_entire_batch_without_mutation(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        plan = self._plan(values)["protected_recovery_plan"]
        receipts = self._receipts(values, plan)
        before = values["ledger"].snapshot()
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts[:-1],
            now_epoch=harness._NOW + 1,
        )
        after = values["ledger"].snapshot()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["COMPLETE_RECOVERY_RECEIPT_SET_REQUIRED"])
        self.assertEqual(before["snapshot_sha256"], after["snapshot_sha256"])

    def test_duplicate_receipt_rejects_entire_batch_without_mutation(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        plan = self._plan(values)["protected_recovery_plan"]
        receipt = self._receipts(values, plan)[0]
        before = values["ledger"].snapshot()
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=[receipt, receipt],
            now_epoch=harness._NOW + 1,
        )
        after = values["ledger"].snapshot()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["DUPLICATE_RECOVERY_RECEIPT"])
        self.assertEqual(before["snapshot_sha256"], after["snapshot_sha256"])

    def test_receipt_for_wrong_record_rejects_entire_batch(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=1
        )
        plan = self._plan(values)["protected_recovery_plan"]
        wrong_item = copy.deepcopy(plan.plan["items"][0])
        wrong_item["request_sha256"] = _sha256_text("wrong-request")
        wrong_receipt = harness.build_synthetic_recovery_receipt_for_plan_item_v1(
            values, wrong_item
        )
        before = values["ledger"].snapshot()
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=[wrong_receipt],
            now_epoch=harness._NOW + 1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RECOVERY_RECEIPT_PLAN_BINDING_INVALID"])
        self.assertEqual(
            before["snapshot_sha256"], values["ledger"].snapshot()["snapshot_sha256"]
        )

    def test_receipt_order_does_not_affect_atomic_recovery(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=3
        )
        plan = self._plan(values)["protected_recovery_plan"]
        receipts = list(reversed(self._receipts(values, plan)))
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts,
            now_epoch=harness._NOW + 1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["final_ledger_snapshot"]["prepared_count"], 0)
        self.assertEqual(result["final_ledger_snapshot"]["terminal_count"], 3)

    def test_all_terminal_recovery_states_are_accepted(self) -> None:
        for terminal_state in ("COMMITTED", "ABORTED", "ROLLED_BACK"):
            with self.subTest(terminal_state=terminal_state):
                values = harness.build_synthetic_startup_recovery_context_v1(
                    prepared_count=1
                )
                plan = self._plan(values)["protected_recovery_plan"]
                receipt = harness.build_synthetic_recovery_receipt_for_plan_item_v1(
                    values,
                    plan.plan["items"][0],
                    terminal_state=terminal_state,
                )
                result = values[
                    "startup_recovery"
                ].reconcile_startup_recovery_offline(
                    protected_binding=values["protected_binding"],
                    protected_plan=plan,
                    protected_receipts=[receipt],
                    now_epoch=harness._NOW + 1,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(
                    result["final_ledger_snapshot"]["records"][0][
                        "terminal_state"
                    ],
                    terminal_state,
                )

    def test_expired_plan_fails_before_ledger_mutation(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1()
        plan = self._plan(values)["protected_recovery_plan"]
        receipts = self._receipts(values, plan)
        before = values["ledger"].snapshot()
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts,
            now_epoch=plan.deadline_epoch,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["STARTUP_RECOVERY_PLAN_OR_DEADLINE_INVALID"])
        self.assertEqual(
            before["snapshot_sha256"], values["ledger"].snapshot()["snapshot_sha256"]
        )

    def test_receipt_deadline_must_fit_inside_plan(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=1
        )
        short_recovery = self._recovery(values, max_seconds=20)
        plan = self._plan(values, recovery=short_recovery)["protected_recovery_plan"]
        receipt = harness.build_synthetic_recovery_receipt_for_plan_item_v1(
            values, plan.plan["items"][0]
        )
        result = short_recovery.reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=[receipt],
            now_epoch=harness._NOW + 1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["RECOVERY_RECEIPT_PLAN_BINDING_INVALID"])

    def test_ledger_change_after_plan_rejects_stale_compare_and_swap(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=1
        )
        plan = self._plan(values)["protected_recovery_plan"]
        receipts = self._receipts(values, plan)
        values["ledger"].seed_prepared_offline(
            harness.build_synthetic_prepared_record_v1(
                values["protected_binding"], index=99
            )
        )
        result = values[
            "startup_recovery"
        ].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts,
            now_epoch=harness._NOW + 1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["STARTUP_RECOVERY_LEDGER_CHANGED_SINCE_PLAN"]
        )

    def test_stale_plan_cannot_be_replayed_after_success(self) -> None:
        values = harness.build_synthetic_startup_recovery_context_v1(
            prepared_count=1
        )
        plan = self._plan(values)["protected_recovery_plan"]
        receipts = self._receipts(values, plan)
        first = values["startup_recovery"].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts,
            now_epoch=harness._NOW + 1,
        )
        replay = values["startup_recovery"].reconcile_startup_recovery_offline(
            protected_binding=values["protected_binding"],
            protected_plan=plan,
            protected_receipts=receipts,
            now_epoch=harness._NOW + 2,
        )

        self.assertTrue(first["ok"])
        self.assertFalse(replay["ok"])
        self.assertEqual(
            replay["reasons"], ["STARTUP_RECOVERY_LEDGER_CHANGED_SINCE_PLAN"]
        )

    def test_config_rejects_unbounded_limits(self) -> None:
        cases = (
            {"max_prepared_records": 0},
            {"max_prepared_records": 1025},
            {"max_recovery_seconds": 0},
            {"max_recovery_seconds": 301},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    contract.DormantProductionBackendStartupRecoveryConfigV1(
                        **kwargs
                    )

    def test_contract_has_no_production_import_or_operational_call_surface(self) -> None:
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

        for forbidden in (
            "main",
            "trade_registry_closed_identity_conflict_repair_production_provider_v1",
            "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1",
        ):
            self.assertNotIn(forbidden, imported)
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
