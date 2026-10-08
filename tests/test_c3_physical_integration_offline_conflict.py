import socket
import subprocess

def _block(*args, **kwargs):
    raise RuntimeError("Network/Subprocess blocked")

socket.socket = _block
subprocess.Popen = _block

import unittest
from pathlib import Path
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_harness_v2 as lease_harness

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_harness_v2 as collector_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2

class OfflineConflictTests(unittest.TestCase):
    def test_coordinator_lease_and_observation_conflict(self):
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            ledger = values["resolved_ledger"]
            
            # Extract dependencies to bind the coordinator to the same physical namespace
            lock_backend = vars(backend)["_lock_backend"]
            lock_namespace = backend._lock_namespace()
            root = vars(backend)["_root"]
            lease_store = storage_v1.DurableJsonMaintenanceLeaseStoreV1(
                lock_backend.storage_root,
                enabled=True,
                directory_fsync=lambda p: None
            )
            Path(lease_store._root).mkdir(parents=True, exist_ok=True)
            
            coord_config = coordinator_v1.WriterRuntimeCoordinatorConfigV1(enabled=True)
            coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
                config=coord_config,
                lock_backend=lock_backend,
                lease_store=lease_store,
                clock=lambda: physical_harness_v2.SYNTHETIC_NOW_V2,
                nonce_source=lambda: "synthetic-nonce",
                lock_namespace=lock_namespace,
            )
            
            lease = lease_harness.make_physical_multistore_observation_lease_v2(
                backend=backend, ledger=ledger
            )
            
            collector = collector_harness.make_physical_locked_aggregate_collection_v2(
                observation_lease=lease, backend=backend, ledger=ledger
            )
            
            coordinator.register_all_declared_writers()
            
            # Prove the conflict: Coordinator acquires its lock
            with coordinator.maintenance_lease() as permit:
                import dataclasses
                permit_dict = dataclasses.asdict(permit)
                self.assertTrue(coordinator.maintenance_permit_is_current_v1(permit_dict, lock_backend=lock_backend))
                
                # Without delegation: Observation Lease tries to acquire BOTH locks (including the backend lock)
                # It will block and timeout because the Coordinator holds it exclusively.
                with self.assertRaisesRegex(Exception, "PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT"):
                    with lease.hold_offline(expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60) as token:
                        pass
                # Without delegation: collect_offline tries to acquire the backend lock
                # It will block and fail because the Coordinator holds it exclusively.
                res = collector.collect_offline()
                self.assertFalse(res["ok"])
                self.assertIn("PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT", res["reason"])
                
                # With delegation: It should skip the backend lock and succeed
                # With delegation: collect_offline should skip the backend lock and succeed
                validator = lambda p: coordinator.maintenance_permit_is_current_v1(p, lock_backend=lock_backend)
                with lease.hold_offline(expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60, delegated_permit=permit_dict, delegated_permit_validator=validator) as token:
                    self.assertTrue(lease.validate_live(token, backend=backend, durable_authority_ledger=ledger, now_epoch=physical_harness_v2.SYNTHETIC_NOW_V2))
                    snapshot = lease.snapshot()
                    self.assertEqual(snapshot["held_lock_count"], 1)
                    self.assertEqual(snapshot["delegated_lock_count"], 1)
                res2 = collector.collect_offline(delegated_permit=permit_dict, delegated_permit_validator=validator)
                self.assertTrue(res2["ok"], res2.get("reason"))
                self.assertEqual(res2["collection_receipt"]["held_lock_count"], 2)
                
                # Negative test: lost lease during collection.
                # The validator must return True on the first call (hold_offline) and False on the second call (validate_live)
                call_count = [0]
                def volatile_validator(p):
                    call_count[0] += 1
                    return call_count[0] <= 1
                res3 = collector.collect_offline(delegated_permit=permit_dict, delegated_permit_validator=volatile_validator)
                self.assertFalse(res3["ok"])
                self.assertIn("PHYSICAL_MULTISTORE_OBSERVATION_LEASE_NOT_LIVE", res3["reason"])

    def test_ledger_lock_timeout_with_delegated_permit(self):
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            ledger = values["resolved_ledger"]
            
            lock_backend = vars(backend)["_lock_backend"]
            lock_namespace = backend._lock_namespace()
            lease_store = storage_v1.DurableJsonMaintenanceLeaseStoreV1(
                lock_backend.storage_root,
                enabled=True,
                directory_fsync=lambda p: None
            )
            Path(lease_store._root).mkdir(parents=True, exist_ok=True)
            
            coord_config = coordinator_v1.WriterRuntimeCoordinatorConfigV1(enabled=True)
            coordinator = coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1(
                config=coord_config,
                lock_backend=lock_backend,
                lease_store=lease_store,
                clock=lambda: physical_harness_v2.SYNTHETIC_NOW_V2,
                nonce_source=lambda: "synthetic-nonce",
                lock_namespace=lock_namespace,
            )
            
            lease = lease_harness.make_physical_multistore_observation_lease_v2(
                backend=backend, ledger=ledger
            )
            
            collector = collector_harness.make_physical_locked_aggregate_collection_v2(
                observation_lease=lease, backend=backend, ledger=ledger
            )
            
            coordinator.register_all_declared_writers()
            
            with coordinator.maintenance_lease() as permit:
                import dataclasses
                permit_dict = dataclasses.asdict(permit)
                validator = lambda p: coordinator.maintenance_permit_is_current_v1(p, lock_backend=lock_backend)
                
                # Simulate another process holding the ledger lock
                ledger_lock_backend = vars(ledger)["_lock_backend"]
                ledger_binding = durable_v2.durable_authority_storage_binding_sha256_v2(vars(ledger)["_storage"])
                handle = ledger_lock_backend.acquire(ledger_binding, 0.05)
                self.assertIsNotNone(handle)
                
                try:
                    # Even with a delegated permit, it should fail to acquire the ledger lock
                    res = collector.collect_offline(delegated_permit=permit_dict, delegated_permit_validator=validator)
                    self.assertFalse(res["ok"])
                    self.assertIn("PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT", res["reason"])
                finally:
                    handle.release()

if __name__ == "__main__":
    unittest.main()
