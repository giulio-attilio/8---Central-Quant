from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off audit must not inspect evidence")


class PhysicalAggregateAuditOfflineV2Tests(unittest.TestCase):
    def test_harness_crosschecks_all_pending_catalogs(self) -> None:
        result = harness.run_physical_aggregate_audit_offline_harness_v2()

        self.assertTrue(result["ok"])
        audit = result["aggregate_audit"]
        self.assertTrue(audit["catalog_crosscheck_verified"])
        self.assertTrue(audit["stable_observation_window_verified"])
        self.assertTrue(audit["optimistic_atomic_observation_verified"])
        self.assertFalse(audit["shared_lock_atomicity_verified"])
        self.assertFalse(audit["production_ready"])
        self.assertFalse(audit["live_allowed"])

    def test_default_off_returns_before_inspecting_evidence(self) -> None:
        dormant = contract.DormantPhysicalAggregateRecoveryAuditV2()

        result = dormant.build_offline(
            initial_backend_snapshot=_Explosive(),
            transaction_log_audit=_Explosive(),
            prepared_catalog=_Explosive(),
            initial_resolved_catalog=_Explosive(),
            final_backend_snapshot=_Explosive(),
            final_transaction_log_audit=_Explosive(),
            final_prepared_catalog=_Explosive(),
            final_resolved_catalog=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_DEFAULT_OFF"
        )
        self.assertFalse(result["source_filesystem_accessed"])

    def test_prepared_wal_change_with_same_backend_generation_is_detected(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            port = values["resolved_catalog_port"]
            initial_snapshot = dict(backend.snapshot_offline())
            initial_audit = dict(backend.inspect_transaction_log_offline())
            initial_prepared = dict(backend.list_prepared_transactions_offline())
            initial_resolved = dict(
                port.read_resolved_catalog_offline(
                    backend=backend, backend_snapshot=initial_snapshot
                )
            )
            request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "new-prepared", "generation": 4},
                label="aggregate-new-prepared",
                deadline_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60,
            )
            backend.prepare_interrupted_transaction_offline(request)
            final_snapshot = dict(backend.snapshot_offline())
            final_audit = dict(backend.inspect_transaction_log_offline())
            final_prepared = dict(backend.list_prepared_transactions_offline())
            final_resolved = dict(
                port.read_resolved_catalog_offline(
                    backend=backend, backend_snapshot=final_snapshot
                )
            )
            result = harness.make_physical_aggregate_audit_v2().build_offline(
                initial_backend_snapshot=initial_snapshot,
                transaction_log_audit=initial_audit,
                prepared_catalog=initial_prepared,
                initial_resolved_catalog=initial_resolved,
                final_backend_snapshot=final_snapshot,
                final_transaction_log_audit=final_audit,
                final_prepared_catalog=final_prepared,
                final_resolved_catalog=final_resolved,
            )

        self.assertEqual(
            initial_snapshot["generation"], final_snapshot["generation"]
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PHYSICAL_OBSERVATION_WINDOW_CHANGED")

    def test_terminal_backend_generation_change_is_detected(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            evidence = harness.collect_physical_aggregate_evidence_v2(values)
            backend = values["backend"]
            request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "terminal-change", "generation": 4},
                label="aggregate-terminal-change",
                deadline_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60,
            )
            backend.apply_attested_transaction_offline(request)
            evidence["final_backend_snapshot"] = dict(backend.snapshot_offline())
            evidence["final_transaction_log_audit"] = dict(
                backend.inspect_transaction_log_offline()
            )
            evidence["final_prepared_catalog"] = dict(
                backend.list_prepared_transactions_offline()
            )
            evidence["final_resolved_catalog"] = dict(
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=backend,
                    backend_snapshot=evidence["final_backend_snapshot"],
                )
            )
            result = harness.make_physical_aggregate_audit_v2().build_offline(
                **evidence
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "PHYSICAL_OBSERVATION_WINDOW_CHANGED")

    def test_tampered_resolved_catalog_is_rejected(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            evidence = harness.collect_physical_aggregate_evidence_v2(values)
        evidence["final_resolved_catalog"] = copy.deepcopy(
            evidence["final_resolved_catalog"]
        )
        evidence["final_resolved_catalog"]["resolved_count"] = 1

        result = harness.make_physical_aggregate_audit_v2().build_offline(**evidence)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"], "PHYSICAL_AGGREGATE_RECOVERY_EVIDENCE_INVALID"
        )

    def test_invalid_scope_fails_without_using_evidence(self) -> None:
        invalid = contract.DormantPhysicalAggregateRecoveryAuditV2(
            contract.PhysicalAggregateRecoveryAuditConfigV2(
                enabled=True, scope_attestation="WRONG"
            )
        )

        result = invalid.build_offline(
            initial_backend_snapshot=_Explosive(),
            transaction_log_audit=_Explosive(),
            prepared_catalog=_Explosive(),
            initial_resolved_catalog=_Explosive(),
            final_backend_snapshot=_Explosive(),
            final_transaction_log_audit=_Explosive(),
            final_prepared_catalog=_Explosive(),
            final_resolved_catalog=_Explosive(),
        )

        self.assertEqual(
            result["reason"], "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_SCOPE_INVALID"
        )

    def test_aggregate_hash_binds_pending_counts(self) -> None:
        result = harness.run_physical_aggregate_audit_offline_harness_v2()
        original = result["aggregate_audit"]
        tampered = copy.deepcopy(original)
        tampered["total_pending_count"] = 1

        self.assertFalse(contract.physical_aggregate_recovery_audit_valid_v2(tampered))
        self.assertNotEqual(
            original["aggregate_audit_sha256"],
            contract._seal(tampered)["aggregate_audit_sha256"],
        )

    def test_contract_remains_absent_from_runtime(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_physical_aggregate_audit_offline_v2",
            source,
        )
        self.assertNotIn("DormantPhysicalAggregateRecoveryAuditV2", source)


if __name__ == "__main__":
    unittest.main()
