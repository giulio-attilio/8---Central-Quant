from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off projection must not inspect bindings")


class StartupRecoveryEvidenceReadPortAdapterV1Tests(unittest.TestCase):
    @staticmethod
    def _project(values):
        return values["adapter_contract"].project_offline(
            protected_scope_binding=values["protected_scope_binding"],
            protected_startup_provider_binding=values[
                "protected_startup_provider_binding"
            ],
            protected_provider_store_binding=values[
                "protected_provider_store_binding"
            ],
        )

    def test_harness_projects_all_missing_ports_without_callables(self) -> None:
        result = harness.run_synthetic_evidence_read_port_adapter_harness_v1()

        self.assertTrue(result["ok"])
        self.assertEqual(result["required_port_count"], 6)
        self.assertEqual(result["implemented_port_count"], 0)
        self.assertEqual(result["missing_port_count"], 6)
        self.assertTrue(result["identity_vector_verified"])
        self.assertFalse(result["adapter_callable_created"])
        self.assertFalse(result["provider_instance_bound"])
        self.assertFalse(result["backend_instance_bound"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_any_binding(self) -> None:
        dormant = contract.DormantStartupRecoveryEvidenceReadPortAdapterContractV1()

        result = dormant.project_offline(
            protected_scope_binding=_Explosive(),
            protected_startup_provider_binding=_Explosive(),
            protected_provider_store_binding=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_READ_PORT_ADAPTER_DEFAULT_OFF"])
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_startup_provider_pin_mismatch_fails_closed(self) -> None:
        values = harness.build_synthetic_evidence_read_port_adapter_context_v1()
        values["adapter_contract"] = (
            contract.DormantStartupRecoveryEvidenceReadPortAdapterContractV1(
                config=contract.DormantStartupRecoveryEvidenceReadPortAdapterConfigV1(
                    enabled=True,
                    scope_attestation=(
                        contract.OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1
                    ),
                    expected_scope_binding_sha256=values[
                        "protected_scope_binding"
                    ].binding_sha256,
                    expected_startup_provider_binding_sha256="a" * 64,
                    expected_provider_store_binding_sha256=values[
                        "protected_provider_store_binding"
                    ].binding_sha256,
                )
            )
        )

        result = self._project(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_STARTUP_PROVIDER_BINDING_INVALID"]
        )
        self.assertFalse(result["provider_store_binding_verified"])

    def test_wrong_binding_layer_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_read_port_adapter_context_v1()
        values["protected_provider_store_binding"] = values[
            "protected_startup_provider_binding"
        ]
        values["adapter_contract"] = (
            harness.make_synthetic_evidence_read_port_adapter_contract_v1(
                scope_binding_sha256=values[
                    "protected_scope_binding"
                ].binding_sha256,
                startup_provider_binding_sha256=values[
                    "protected_startup_provider_binding"
                ].binding_sha256,
                provider_store_binding_sha256=values[
                    "protected_provider_store_binding"
                ].binding_sha256,
            )
        )

        result = self._project(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["PROTECTED_PROVIDER_STORE_BINDING_INVALID"]
        )
        self.assertFalse(result["identity_vector_verified"])

    def test_plan_routes_every_surface_to_explicit_missing_status(self) -> None:
        values = harness.build_synthetic_evidence_read_port_adapter_context_v1()
        result = self._project(values)
        plan = result["protected_adapter_plan"].plan

        self.assertEqual(
            {item["required_port"] for item in plan["port_route_plan"]},
            set(plan["required_ports"]),
        )
        self.assertTrue(
            all("REQUIRED" in item["status"] for item in plan["port_route_plan"])
        )
        self.assertNotIn("callable", plan)
        self.assertFalse(plan["adapter_callable_created"])

    def test_protected_plan_rejects_resealed_implemented_port_claim(self) -> None:
        values = harness.build_synthetic_evidence_read_port_adapter_context_v1()
        result = self._project(values)
        protected = result["protected_adapter_plan"]
        plan = copy.deepcopy(protected.plan)
        plan["implemented_port_count"] = 1
        plan["missing_port_count"] = 5
        plan["plan_sha256"] = (
            contract.startup_recovery_evidence_read_port_adapter_plan_sha256_v1(
                plan
            )
        )
        tampered = contract.ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1(
            protected_scope_binding=protected.protected_scope_binding,
            protected_provider_store_binding=protected.protected_provider_store_binding,
            protected_startup_provider_binding=protected.protected_startup_provider_binding,
            plan=plan,
            plan_sha256=plan["plan_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
                tampered
            )
        )

    def test_projection_keeps_all_sources_uncalled(self) -> None:
        values = harness.build_synthetic_evidence_read_port_adapter_context_v1()

        result = self._project(values)

        self.assertTrue(result["ok"])
        self.assertEqual(
            values["store_double"].counters(),
            {"apply_call_count": 0, "recovery_call_count": 0},
        )
        self.assertFalse(result["provider_called"])
        self.assertFalse(result["store_called"])
        self.assertFalse(result["backend_called"])
        self.assertFalse(result["real_registry_accessed"])

    def test_contract_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_evidence_read_port_adapter_contract_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1", main_source
        )


if __name__ == "__main__":
    unittest.main()
