from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


ROOT = Path(__file__).resolve().parents[1]


class _DependencySpy:
    def __init__(self) -> None:
        self.calls = 0

    def _called(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("dependency must not be called")

    snapshot_offline = _called
    list_prepared_transactions_offline = _called
    inspect_transaction_log_offline = _called
    reconcile_attested_transaction_offline = _called
    plan_offline = _called
    record_terminal_receipt_offline = _called
    finalize_offline = _called
    normalize_recovery_offline = _called


class OfflineRuntimeStartupRecoveryAdapterV1Tests(unittest.TestCase):
    def test_harness_drains_catalog_under_one_maintenance_epoch(self) -> None:
        result = harness.run_offline_runtime_startup_recovery_adapter_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["initial_prepared_count"], 2)
        self.assertEqual(result["final_prepared_count"], 0)
        self.assertEqual(result["final_resolved_count"], 0)
        self.assertEqual(result["recovery_request_count"], 2)
        self.assertTrue(
            result["all_recovery_requests_bound_to_same_maintenance_epoch"]
        )
        self.assertFalse(result["startup_recovery_verified"])
        self.assertFalse(result["coordination_ready"])
        self.assertTrue(result["runtime_unlock_blocked_for_offline_evidence"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["activation_allowed"])
        self.assertFalse(result["live_allowed"])
        self.assertFalse(result["real_registry_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["broker_called"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_any_dependency_call(self) -> None:
        spy = _DependencySpy()
        adapter = contract.OfflineRuntimeStartupRecoveryAdapterV1(
            backend=spy,
            startup_recovery=spy,
            terminal_evidence_port=spy,
        )

        result = adapter({})

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "STARTUP_RECOVERY_ADAPTER_DEFAULT_OFF")
        self.assertFalse(result["backend_called"])
        self.assertFalse(result["write_executed"])
        self.assertFalse(result["write_state_unknown"])
        self.assertEqual(spy.calls, 0)

    def test_invalid_maintenance_permit_fails_before_backend_access(self) -> None:
        spy = _DependencySpy()
        adapter = contract.OfflineRuntimeStartupRecoveryAdapterV1(
            backend=spy,
            startup_recovery=spy,
            terminal_evidence_port=spy,
            config=contract.OfflineRuntimeStartupRecoveryAdapterConfigV1(
                enabled=True,
                scope_attestation=(
                    contract.OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1
                ),
            ),
        )

        result = adapter(
            {
                "state": "DRAINING",
                "maintenance_epoch": "a" * 64,
                "lock_namespace_sha256": "b" * 64,
                "registered_writer_count": 19,
                "inflight_mutations": 0,
                "shared_lock_acquired": True,
            }
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reason"],
            "STARTUP_RECOVERY_ADAPTER_MAINTENANCE_PERMIT_INVALID",
        )
        self.assertFalse(result["backend_called"])
        self.assertEqual(spy.calls, 0)

    def test_transaction_log_audit_is_aggregate_and_tamper_evident(self) -> None:
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
                root,
                enabled=True,
                scope_attestation=(
                    physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
                ),
                clock=lambda: 1_788_900_000,
            )
            backend.initialize_synthetic_registry_offline(
                {"closed_trades": [], "fixture": "log-audit"}
            )
            snapshot = backend.snapshot_offline()
            audit = backend.inspect_transaction_log_offline()

            self.assertTrue(
                contract.temporary_transaction_log_audit_valid_v1(
                    audit, snapshot
                )
            )
            self.assertNotIn("records", audit)
            self.assertNotIn("storage_root", audit)
            tampered = copy.deepcopy(audit)
            tampered["unresolved_resolved_count"] = 1
            self.assertFalse(
                contract.temporary_transaction_log_audit_valid_v1(
                    tampered, snapshot
                )
            )

    def test_backend_exception_after_recovery_attempt_reports_unknown_write_state(
        self,
    ) -> None:
        now = 1_788_900_000
        with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
            backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
                root,
                enabled=True,
                scope_attestation=(
                    physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
                ),
                clock=lambda: now,
            )
            backend.initialize_synthetic_registry_offline(
                {"closed_trades": [], "fixture": "backend-failure-source"}
            )
            request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "backend-failure-candidate"},
                label="backend-failure",
                deadline_epoch=now + 120,
            )
            backend.prepare_interrupted_transaction_offline(request)
            recovery = startup_contract.ResumableStartupRecoveryV2(
                startup_contract.StartupRecoveryConfigV2(
                    enabled=True,
                    scope_attestation=(
                        startup_contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2
                    ),
                    max_prepared_records=8,
                    max_recovery_seconds=120,
                ),
                clock=lambda: now + 1,
            )
            terminal_port = terminal_contract.PhysicalTerminalEvidencePortV2(
                terminal_contract.PhysicalTerminalEvidencePortConfigV2(
                    enabled=True,
                    scope_attestation=(
                        terminal_contract.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2
                    ),
                    max_completion_window_seconds=120,
                ),
                clock=lambda: now + 2,
            )
            adapter = contract.OfflineRuntimeStartupRecoveryAdapterV1(
                backend=backend,
                startup_recovery=recovery,
                terminal_evidence_port=terminal_port,
                config=contract.OfflineRuntimeStartupRecoveryAdapterConfigV1(
                    enabled=True,
                    scope_attestation=(
                        contract.OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1
                    ),
                ),
            )

            def fail_recovery(_request):
                raise RuntimeError("synthetic backend interruption")

            backend.reconcile_attested_transaction_offline = fail_recovery
            result = adapter(
                {
                    "state": "QUIESCED",
                    "maintenance_epoch": "a" * 64,
                    "lock_namespace_sha256": (
                        coordinator_module.canonical_runtime_lock_namespace_v1()
                    ),
                    "registered_writer_count": 19,
                    "inflight_mutations": 0,
                    "shared_lock_acquired": True,
                }
            )

            self.assertFalse(result["ok"])
            self.assertTrue(result["backend_called"])
            self.assertTrue(result["write_state_unknown"])
            self.assertFalse(result["real_registry_accessed"])
            self.assertFalse(result["network_accessed"])
            self.assertTrue(result["no_order_sent"])

    def test_adapter_remains_absent_from_runtime_main(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "runtime_startup_recovery_adapter_offline_v1", source
        )
        self.assertNotIn(
            "run_offline_runtime_startup_recovery_adapter_harness_v1", source
        )


if __name__ == "__main__":
    unittest.main()
