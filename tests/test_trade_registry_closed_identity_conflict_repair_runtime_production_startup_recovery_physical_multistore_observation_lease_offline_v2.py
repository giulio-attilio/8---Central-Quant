from __future__ import annotations

import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off lease must not inspect dependencies")


class PhysicalMultiStoreObservationLeaseOfflineV2Tests(unittest.TestCase):
    def test_harness_holds_both_writer_locks_and_releases_them(self) -> None:
        result = harness.run_physical_multistore_observation_lease_offline_harness_v2()

        self.assertTrue(result["ok"])
        self.assertTrue(result["two_locks_held"])
        self.assertTrue(result["backend_contention_blocked"])
        self.assertTrue(result["resolved_ledger_contention_blocked"])
        self.assertTrue(result["lease_invalid_after_release"])
        self.assertTrue(result["both_locks_released"])
        self.assertFalse(result["registry_write"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_rejects_before_inspecting_dependencies(self) -> None:
        lease = contract.PhysicalMultiStoreObservationLeaseV2(
            backend=_Explosive(), durable_authority_ledger=_Explosive()
        )

        with self.assertRaisesRegex(
            contract.TemporaryPhysicalObservationLeaseBlockedV2,
            "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_DEFAULT_OFF",
        ):
            with lease.hold_offline(expires_at_epoch=1):
                self.fail("default-off lease unexpectedly opened")

    def test_token_expires_while_locks_remain_safely_held(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            lease = harness.make_physical_multistore_observation_lease_v2(
                backend=values["backend"], ledger=values["resolved_ledger"]
            )
            now = physical_harness_v2.SYNTHETIC_NOW_V2
            with lease.hold_offline(expires_at_epoch=now + 1) as token:
                self.assertTrue(
                    lease.validate_live(
                        token,
                        backend=values["backend"],
                        durable_authority_ledger=values["resolved_ledger"],
                        now_epoch=now,
                    )
                )
                self.assertFalse(
                    lease.validate_live(
                        token,
                        backend=values["backend"],
                        durable_authority_ledger=values["resolved_ledger"],
                        now_epoch=now + 1,
                    )
                )
                self.assertEqual(lease.snapshot()["held_lock_count"], 2)

    def test_substituted_backend_or_ledger_is_not_live(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            with physical_harness_v2.synthetic_physical_conformance_context_v2() as other:
                lease = harness.make_physical_multistore_observation_lease_v2(
                    backend=values["backend"], ledger=values["resolved_ledger"]
                )
                now = physical_harness_v2.SYNTHETIC_NOW_V2
                with lease.hold_offline(expires_at_epoch=now + 60) as token:
                    self.assertFalse(
                        lease.validate_live(
                            token,
                            backend=other["backend"],
                            durable_authority_ledger=values["resolved_ledger"],
                            now_epoch=now,
                        )
                    )
                    self.assertFalse(
                        lease.validate_live(
                            token,
                            backend=values["backend"],
                            durable_authority_ledger=other["resolved_ledger"],
                            now_epoch=now,
                        )
                    )

    def test_nested_hold_is_rejected(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            lease = harness.make_physical_multistore_observation_lease_v2(
                backend=values["backend"], ledger=values["resolved_ledger"]
            )
            now = physical_harness_v2.SYNTHETIC_NOW_V2
            with lease.hold_offline(expires_at_epoch=now + 60):
                with self.assertRaisesRegex(
                    contract.TemporaryPhysicalObservationLeaseBlockedV2,
                    "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_ALREADY_ACTIVE",
                ):
                    with lease.hold_offline(expires_at_epoch=now + 60):
                        self.fail("nested lease unexpectedly opened")

    def test_second_lock_failure_releases_first_lock(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            ledger = values["resolved_ledger"]
            ledger_binding = durable_v2.durable_authority_storage_binding_sha256_v2(
                vars(ledger)["_storage"]
            )
            preheld = vars(ledger)["_lock_backend"].acquire(
                ledger_binding, 0.01
            )
            self.assertIsNotNone(preheld)
            lease = harness.make_physical_multistore_observation_lease_v2(
                backend=backend, ledger=ledger
            )
            try:
                with self.assertRaisesRegex(
                    contract.TemporaryPhysicalObservationLeaseBlockedV2,
                    "PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT",
                ):
                    with lease.hold_offline(
                        expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60
                    ):
                        self.fail("lease unexpectedly acquired contended lock")
                backend_probe = vars(backend)["_lock_backend"].acquire(
                    backend._lock_namespace(), 0.01
                )
                self.assertIsNotNone(backend_probe)
                backend_probe.release()
            finally:
                if preheld is not None and not preheld.released:
                    preheld.release()

    def test_body_exception_releases_both_locks(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            ledger = values["resolved_ledger"]
            lease = harness.make_physical_multistore_observation_lease_v2(
                backend=backend, ledger=ledger
            )
            with self.assertRaisesRegex(RuntimeError, "SYNTHETIC_COLLECTION_FAILURE"):
                with lease.hold_offline(
                    expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60
                ):
                    raise RuntimeError("SYNTHETIC_COLLECTION_FAILURE")
            backend_probe = vars(backend)["_lock_backend"].acquire(
                backend._lock_namespace(), 0.01
            )
            ledger_probe = vars(ledger)["_lock_backend"].acquire(
                durable_v2.durable_authority_storage_binding_sha256_v2(
                    vars(ledger)["_storage"]
                ),
                0.01,
            )
            self.assertIsNotNone(backend_probe)
            self.assertIsNotNone(ledger_probe)
            ledger_probe.release()
            backend_probe.release()

    def test_ledger_outside_backend_root_is_rejected(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            with physical_harness_v2.synthetic_physical_conformance_context_v2() as other:
                lease = harness.make_physical_multistore_observation_lease_v2(
                    backend=values["backend"], ledger=other["resolved_ledger"]
                )

                with self.assertRaisesRegex(
                    contract.TemporaryPhysicalObservationLeaseBlockedV2,
                    "PHYSICAL_MULTISTORE_OBSERVATION_STORAGE_ROOT_MISMATCH",
                ):
                    with lease.hold_offline(
                        expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60
                    ):
                        self.fail("cross-root lease unexpectedly opened")

    def test_protected_token_repr_hides_bindings(self) -> None:
        with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
            lease = harness.make_physical_multistore_observation_lease_v2(
                backend=values["backend"], ledger=values["resolved_ledger"]
            )
            with lease.hold_offline(
                expires_at_epoch=physical_harness_v2.SYNTHETIC_NOW_V2 + 60
            ) as token:
                rendered = repr(token)
                self.assertEqual(
                    rendered,
                    "ProtectedPhysicalMultiStoreObservationLeaseTokenV2(<protected>)",
                )
                self.assertNotIn(token.token_sha256, rendered)

    def test_contract_remains_absent_from_runtime(self) -> None:
        source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_physical_multistore_observation_lease_offline_v2",
            source,
        )
        self.assertNotIn("PhysicalMultiStoreObservationLeaseV2", source)


if __name__ == "__main__":
    unittest.main()
