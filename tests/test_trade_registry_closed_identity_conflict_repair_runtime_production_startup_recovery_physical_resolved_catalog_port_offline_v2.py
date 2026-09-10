from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as adapter_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_harness_v2 as harness
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2 as contract


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off port must not inspect inputs")


class PhysicalResolvedCatalogPortOfflineV2Tests(unittest.TestCase):
    def test_harness_projects_resolved_record_identically_after_restart(self) -> None:
        result = harness.run_physical_resolved_catalog_port_offline_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["resolved_count"], 1)
        self.assertTrue(result["restart_catalog_identical"])
        self.assertTrue(result["temporary_storage_removed"])
        self.assertFalse(result["real_registry_accessed"])
        self.assertFalse(result["network_accessed"])
        self.assertFalse(result["broker_called"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_rejects_before_inspecting_inputs(self) -> None:
        port = contract.TemporaryPhysicalResolvedCatalogPortV2()

        with self.assertRaisesRegex(
            contract.TemporaryPhysicalResolvedCatalogBlockedV2,
            "PHYSICAL_RESOLVED_CATALOG_PORT_DEFAULT_OFF",
        ):
            port.read_resolved_catalog_offline(
                backend=_Explosive(), backend_snapshot=_Explosive()
            )

    def test_complete_empty_catalog_is_valid(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            snapshot = values["backend"].snapshot_offline()
            catalog = dict(
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=values["backend"], backend_snapshot=snapshot
                )
            )

        self.assertTrue(contract.physical_resolved_catalog_valid_v2(catalog, snapshot))
        self.assertEqual(catalog["resolved_count"], 0)
        self.assertTrue(catalog["complete_scan_verified"])
        self.assertTrue(catalog["wal_integrity_verified"])

    def test_resealed_catalog_with_projection_downgrade_is_invalid(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            snapshot = values["backend"].snapshot_offline()
            catalog = dict(
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=values["backend"], backend_snapshot=snapshot
                )
            )
        catalog["complete_scan_verified"] = False
        catalog["catalog_sha256"] = adapter_harness_v2._sha("resealed-downgrade")

        self.assertFalse(contract.physical_resolved_catalog_valid_v2(catalog, snapshot))

    def test_stale_backend_snapshot_is_rejected(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            backend = values["backend"]
            stale = backend.snapshot_offline()
            request = backend.build_transaction_request_offline(
                {"closed_trades": [], "fixture": "stale", "generation": 99},
                label="resolved-catalog-stale",
                deadline_epoch=adapter_harness_v2.SYNTHETIC_NOW_V2 + 60,
            )
            backend.apply_attested_transaction_offline(request)

            with self.assertRaisesRegex(
                contract.TemporaryPhysicalResolvedCatalogBlockedV2,
                "PHYSICAL_RESOLVED_CATALOG_BACKEND_SNAPSHOT_STALE",
            ):
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=backend, backend_snapshot=stale
                )

    def test_substituted_backend_instance_is_rejected(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as original:
            with adapter_harness_v2.synthetic_physical_conformance_context_v2() as substitute:
                with self.assertRaisesRegex(
                    contract.TemporaryPhysicalResolvedCatalogBlockedV2,
                    "PHYSICAL_RESOLVED_CATALOG_DEPENDENCY_INVALID",
                ):
                    original["resolved_catalog_port"].read_resolved_catalog_offline(
                        backend=substitute["backend"],
                        backend_snapshot=substitute["backend"].snapshot_offline(),
                    )

    def test_corrupt_ledger_snapshot_fails_closed(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            storage = vars(values["resolved_ledger"])["_storage"]
            snapshot_path = Path(storage.snapshot_path)
            stored = json.loads(snapshot_path.read_text(encoding="utf-8"))
            stored["generation"] = stored["generation"] + 1
            snapshot_path.write_text(
                json.dumps(stored, sort_keys=True), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                contract.TemporaryPhysicalResolvedCatalogBlockedV2,
                "PHYSICAL_RESOLVED_LEDGER_SCAN_INVALID",
            ):
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=values["backend"],
                    backend_snapshot=values["backend"].snapshot_offline(),
                )

    def test_corrupt_ledger_journal_fails_closed(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            storage = vars(values["resolved_ledger"])["_storage"]
            Path(storage.journal_path).write_bytes(b"not-json\n")

            with self.assertRaisesRegex(
                contract.TemporaryPhysicalResolvedCatalogBlockedV2,
                "PHYSICAL_RESOLVED_LEDGER_SCAN_INVALID",
            ):
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=values["backend"],
                    backend_snapshot=values["backend"].snapshot_offline(),
                )

    def test_record_or_catalog_extra_fields_are_rejected(self) -> None:
        with adapter_harness_v2.synthetic_physical_conformance_context_v2() as values:
            snapshot = values["backend"].snapshot_offline()
            catalog = dict(
                values["resolved_catalog_port"].read_resolved_catalog_offline(
                    backend=values["backend"], backend_snapshot=snapshot
                )
            )
        tampered = copy.deepcopy(catalog)
        tampered["unexpected"] = True

        self.assertFalse(contract.physical_resolved_catalog_valid_v2(tampered, snapshot))

    def test_port_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")

        self.assertNotIn(
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_physical_resolved_catalog_port_offline_v2",
            main_source,
        )
        self.assertNotIn("TemporaryPhysicalResolvedCatalogPortV2", main_source)


if __name__ == "__main__":
    unittest.main()
