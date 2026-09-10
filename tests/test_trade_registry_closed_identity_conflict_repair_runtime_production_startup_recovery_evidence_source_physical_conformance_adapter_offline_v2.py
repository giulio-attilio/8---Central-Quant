from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off adapter must not inspect dependencies")


class PhysicalConformanceAdapterOfflineV2Tests(unittest.TestCase):
    @staticmethod
    def _assess(values):
        return values["adapter"].assess_offline(
            backend=values["backend"],
            terminal_evidence_port=values["terminal_port"],
            resolved_catalog_port=values["resolved_catalog_port"],
            observation_lease=values["observation_lease"],
            locked_aggregate_collection=values["locked_collection"],
            observation_authority=values["authority"],
        )

    def test_harness_verifies_all_six_routes_offline(self) -> None:
        result = harness.run_physical_conformance_adapter_offline_harness_v2()

        self.assertTrue(result["ok"])
        self.assertTrue(result["complete_offline"])
        adapter_result = result["adapter_result"]
        self.assertTrue(adapter_result["ok"])
        self.assertEqual(adapter_result["required_port_count"], 6)
        self.assertEqual(adapter_result["available_port_count"], 6)
        self.assertEqual(adapter_result["validated_read_port_count"], 5)
        self.assertEqual(adapter_result["authority_revalidation_count"], 3)
        self.assertEqual(adapter_result["lease_revalidation_count"], 8)
        self.assertTrue(adapter_result["locked_collection_receipt_verified"])
        self.assertTrue(adapter_result["partial_conformance_verified"])
        self.assertTrue(adapter_result["complete_conformance_verified"])
        self.assertTrue(adapter_result["resolved_catalog_verified"])
        self.assertTrue(adapter_result["aggregate_audit_verified"])
        self.assertTrue(adapter_result["stable_observation_window_verified"])
        self.assertTrue(adapter_result["optimistic_atomic_observation_verified"])
        self.assertTrue(adapter_result["shared_lock_atomicity_verified"])
        self.assertFalse(adapter_result["terminal_normalizer_called"])
        self.assertFalse(adapter_result["real_registry_accessed"])
        self.assertFalse(adapter_result["live_allowed"])

    def test_default_off_returns_before_inspecting_dependencies(self) -> None:
        dormant = contract.OfflineEvidenceSourcePhysicalConformanceAdapterV2()

        result = dormant.assess_offline(
            backend=_Explosive(),
            terminal_evidence_port=_Explosive(),
            resolved_catalog_port=_Explosive(),
            observation_lease=_Explosive(),
            locked_aggregate_collection=_Explosive(),
            observation_authority=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PHYSICAL_EVIDENCE_CONFORMANCE_DEFAULT_OFF"]
        )
        self.assertFalse(result["filesystem_accessed"])

    def test_tampered_authority_is_rejected_before_filesystem_read(self) -> None:
        with harness.synthetic_physical_conformance_context_v2() as values:
            values["authority"] = copy.deepcopy(values["authority"])
            values["authority"]["maintenance_epoch"] = "0" * 64

            result = self._assess(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PHYSICAL_OBSERVATION_AUTHORITY_INVALID"])
        self.assertEqual(result["authority_revalidation_count"], 0)
        self.assertFalse(result["filesystem_accessed"])

    def test_expired_authority_is_rejected_before_filesystem_read(self) -> None:
        with harness.synthetic_physical_conformance_context_v2() as values:
            authority = contract.build_synthetic_physical_observation_authority_v2(
                snapshot=values["snapshot"],
                maintenance_epoch=harness._sha("expired-maintenance-epoch"),
                maintenance_lease_receipt_sha256=harness._sha("expired-lease"),
                resolved_ledger_storage_binding_sha256=values["authority"][
                    "resolved_ledger_storage_binding_sha256"
                ],
                issued_at_epoch=harness.SYNTHETIC_NOW_V2 - 60,
                expires_at_epoch=harness.SYNTHETIC_NOW_V2,
            )
            values["authority"] = authority
            values["adapter"] = harness.make_adapter_v2(
                backend=values["backend"],
                terminal_evidence_port=values["terminal_port"],
                resolved_catalog_port=values["resolved_catalog_port"],
                observation_lease=values["observation_lease"],
                locked_aggregate_collection=values["locked_collection"],
                authority_sha256=authority["authority_sha256"],
            )

            result = self._assess(values)

        self.assertEqual(result["reasons"], ["PHYSICAL_OBSERVATION_AUTHORITY_INVALID"])
        self.assertFalse(result["filesystem_accessed"])

    def test_authority_is_revalidated_after_locked_collection(self) -> None:
        with harness.synthetic_physical_conformance_context_v2() as values:
            clock_values = iter(
                [
                    harness.SYNTHETIC_NOW_V2,
                    harness.SYNTHETIC_NOW_V2 + 61,
                ]
            )
            values["adapter"] = harness.make_adapter_v2(
                backend=values["backend"],
                terminal_evidence_port=values["terminal_port"],
                resolved_catalog_port=values["resolved_catalog_port"],
                observation_lease=values["observation_lease"],
                locked_aggregate_collection=values["locked_collection"],
                authority_sha256=values["authority"]["authority_sha256"],
                clock=lambda: next(clock_values),
            )

            result = self._assess(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PHYSICAL_OBSERVATION_AUTHORITY_STALE"])
        self.assertEqual(result["authority_revalidation_count"], 1)
        self.assertTrue(result["snapshot_verified"])
        self.assertTrue(result["transaction_log_audit_verified"])
        self.assertEqual(result["lease_revalidation_count"], 8)
        self.assertTrue(result["filesystem_accessed"])

    def test_substituted_backend_instance_is_rejected_without_read(self) -> None:
        with harness.synthetic_physical_conformance_context_v2() as original:
            with harness.synthetic_physical_conformance_context_v2() as substitute:
                result = original["adapter"].assess_offline(
                    backend=substitute["backend"],
                    terminal_evidence_port=original["terminal_port"],
                    resolved_catalog_port=original["resolved_catalog_port"],
                    observation_lease=original["observation_lease"],
                    locked_aggregate_collection=original["locked_collection"],
                    observation_authority=original["authority"],
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TEMPORARY_PHYSICAL_DEPENDENCY_INVALID"])
        self.assertFalse(result["filesystem_accessed"])

    def test_disabled_terminal_normalizer_fails_closed_without_calling_it(self) -> None:
        with harness.synthetic_physical_conformance_context_v2(
            terminal_enabled=False
        ) as values:
            result = self._assess(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PHYSICAL_TERMINAL_NORMALIZER_NOT_BOUND"])
        self.assertEqual(result["validated_read_port_count"], 5)
        self.assertFalse(result["terminal_normalizer_bound"])
        self.assertFalse(result["terminal_normalizer_called"])

    def test_unobserved_backend_capabilities_fail_closed(self) -> None:
        with harness.synthetic_physical_conformance_context_v2(
            exercise_capabilities=False
        ) as values:
            result = self._assess(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["PHYSICAL_CAPABILITY_EVIDENCE_INVALID"])
        self.assertEqual(result["validated_read_port_count"], 4)
        self.assertFalse(result["capability_probe_verified"])
        self.assertFalse(result["complete_conformance_verified"])

    def test_route_contract_is_complete_but_adapter_absent_from_runtime(self) -> None:
        with harness.synthetic_physical_conformance_context_v2() as values:
            result = self._assess(values)
        required_ports = [route["required_port"] for route in result["port_routes"]]

        self.assertEqual(
            required_ports,
            [
                "read_backend_snapshot_offline",
                "read_transaction_log_audit_offline",
                "read_prepared_catalog_offline",
                "read_resolved_catalog_offline",
                "read_backend_capability_probe_offline",
                "normalize_terminal_receipt_offline",
            ],
        )
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_evidence_source_physical_conformance_adapter_"
            "offline_v2"
        )
        self.assertNotIn(module_name, main_source)
        self.assertNotIn("OfflineEvidenceSourcePhysicalConformanceAdapterV2", main_source)


if __name__ == "__main__":
    unittest.main()
