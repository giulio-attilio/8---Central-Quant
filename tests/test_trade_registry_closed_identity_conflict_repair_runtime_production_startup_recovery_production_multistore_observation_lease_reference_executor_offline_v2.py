from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2 as executor_contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off executor must not inspect dependencies")


class ProductionMultistoreObservationLeaseReferenceExecutorOfflineV2Tests(
    unittest.TestCase
):
    @staticmethod
    def _hold(values, *, expires_at_epoch=None):
        return values["executor"].hold_offline(
            binding=values["binding"],
            authority=values["authority"],
            transaction_store_lock_port=values["transaction_port"],
            resolved_authority_store_lock_port=values["resolved_port"],
            expires_at_epoch=(
                expires_at_epoch
                if expires_at_epoch is not None
                else harness.SYNTHETIC_NOW_V2 + 30
            ),
        )

    def test_harness_proves_order_liveness_and_reverse_release(self) -> None:
        result = (
            harness.run_production_multistore_observation_lease_reference_executor_offline_harness_v2()
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["two_locks_held_under_same_token"])
        self.assertTrue(result["acquire_order_verified"])
        self.assertTrue(result["reverse_release_order_verified"])
        self.assertTrue(result["lease_invalid_after_release"])
        self.assertFalse(result["store_called"])
        self.assertFalse(result["filesystem_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_blocks_before_dependency_inspection(self) -> None:
        executor = (
            executor_contract.ReferenceProductionMultistoreObservationLeaseExecutorV2()
        )

        with self.assertRaisesRegex(
            executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_DEFAULT_OFF",
        ):
            with executor.hold_offline(
                binding=_Explosive(),
                authority=_Explosive(),
                transaction_store_lock_port=_Explosive(),
                resolved_authority_store_lock_port=_Explosive(),
                expires_at_epoch=1,
            ):
                self.fail("default-off lease unexpectedly entered")

    def test_failure_on_second_lock_releases_first_lock(self) -> None:
        values = harness.build_reference_lease_executor_context_v2(
            fail_resolved_acquire=True
        )

        with self.assertRaisesRegex(
            executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_LOCK_CONTENTION",
        ):
            with self._hold(values):
                self.fail("partial lease unexpectedly entered")

        self.assertEqual(
            values["event_sink"],
            [
                ("ACQUIRE", "RAW_TRANSACTION_STORE"),
                ("RELEASE", "RAW_TRANSACTION_STORE"),
            ],
        )
        self.assertFalse(values["transaction_port"].snapshot()["active"])
        self.assertFalse(values["resolved_port"].snapshot()["active"])
        self.assertEqual(values["executor"].snapshot()["held_lock_count"], 0)

    def test_body_exception_releases_both_locks_in_reverse_order(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()

        with self.assertRaisesRegex(RuntimeError, "synthetic body failure"):
            with self._hold(values):
                raise RuntimeError("synthetic body failure")

        self.assertEqual(
            values["event_sink"],
            [
                ("ACQUIRE", "RAW_TRANSACTION_STORE"),
                ("ACQUIRE", "RESOLVED_AUTHORITY_LEDGER"),
                ("RELEASE", "RESOLVED_AUTHORITY_LEDGER"),
                ("RELEASE", "RAW_TRANSACTION_STORE"),
            ],
        )
        self.assertEqual(values["executor"].snapshot()["held_lock_count"], 0)

    def test_token_expires_closed_while_handles_remain_scoped(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()

        with self._hold(values) as token:
            self.assertTrue(
                values["executor"].validate_live(
                    token,
                    transaction_store_lock_port=values["transaction_port"],
                    resolved_authority_store_lock_port=values["resolved_port"],
                    now_epoch=harness.SYNTHETIC_NOW_V2,
                )
            )
            self.assertFalse(
                values["executor"].validate_live(
                    token,
                    transaction_store_lock_port=values["transaction_port"],
                    resolved_authority_store_lock_port=values["resolved_port"],
                    now_epoch=harness.SYNTHETIC_NOW_V2 + 30,
                )
            )

        self.assertEqual(values["executor"].snapshot()["held_lock_count"], 0)

    def test_nested_lease_on_same_executor_is_rejected(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()

        with self._hold(values):
            with self.assertRaisesRegex(
                executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
                "PRODUCTION_MULTISTORE_LEASE_REFERENCE_ALREADY_ACTIVE",
            ):
                with self._hold(values):
                    self.fail("nested lease unexpectedly entered")

        self.assertEqual(values["executor"].snapshot()["held_lock_count"], 0)

    def test_reconstructed_authority_instance_is_rejected(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()
        original = values["authority"]
        reconstructed = (
            executor_contract.ProtectedSyntheticProductionObservationAuthorityV2(
                lease_binding_sha256=original.lease_binding_sha256,
                maintenance_epoch=original.maintenance_epoch,
                authority=copy.deepcopy(dict(original.authority)),
                authority_sha256=original.authority_sha256,
            )
        )

        with self.assertRaisesRegex(
            executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_INPUT_INVALID",
        ):
            with values["executor"].hold_offline(
                binding=values["binding"],
                authority=reconstructed,
                transaction_store_lock_port=values["transaction_port"],
                resolved_authority_store_lock_port=values["resolved_port"],
                expires_at_epoch=harness.SYNTHETIC_NOW_V2 + 30,
            ):
                self.fail("reconstructed authority unexpectedly accepted")

        self.assertEqual(values["event_sink"], [])

    def test_substituted_lock_port_instance_is_rejected(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()
        substitute = executor_contract.InMemoryProductionStoreLockPortDoubleV2(
            values["transaction_projection"]
        )

        with self.assertRaisesRegex(
            executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_INPUT_INVALID",
        ):
            with values["executor"].hold_offline(
                binding=values["binding"],
                authority=values["authority"],
                transaction_store_lock_port=substitute,
                resolved_authority_store_lock_port=values["resolved_port"],
                expires_at_epoch=harness.SYNTHETIC_NOW_V2 + 30,
            ):
                self.fail("substituted port unexpectedly accepted")

        self.assertEqual(values["event_sink"], [])

    def test_tampered_authority_is_invalid_even_when_resealed(self) -> None:
        values = harness.build_reference_lease_executor_context_v2()
        original = values["authority"]
        payload = copy.deepcopy(dict(original.authority))
        payload["registered_writer_count"] = 18
        payload["authority_sha256"] = (
            executor_contract.synthetic_production_observation_authority_sha256_v2(
                payload
            )
        )
        tampered = (
            executor_contract.ProtectedSyntheticProductionObservationAuthorityV2(
                lease_binding_sha256=payload["lease_binding_sha256"],
                maintenance_epoch=payload["maintenance_epoch"],
                authority=payload,
                authority_sha256=payload["authority_sha256"],
            )
        )

        self.assertFalse(
            executor_contract.synthetic_production_observation_authority_valid_v2(
                tampered, now_epoch=harness.SYNTHETIC_NOW_V2
            )
        )

    def test_expired_authority_blocks_before_lock_acquisition(self) -> None:
        values = harness.build_reference_lease_executor_context_v2(
            clock=lambda: harness.SYNTHETIC_NOW_V2 + 61
        )

        with self.assertRaisesRegex(
            executor_contract.ReferenceProductionLeaseExecutorBlockedV2,
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_INPUT_INVALID",
        ):
            with self._hold(
                values, expires_at_epoch=harness.SYNTHETIC_NOW_V2 + 62
            ):
                self.fail("expired authority unexpectedly accepted")

        self.assertEqual(values["event_sink"], [])

    def test_reference_executor_is_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn(
            "production_multistore_observation_lease_reference_executor_offline_v2",
            main_source,
        )
        self.assertNotIn(
            "ReferenceProductionMultistoreObservationLeaseExecutorV2",
            main_source,
        )


if __name__ == "__main__":
    unittest.main()
