from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_harness_v2 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off contract must not inspect inputs")


class _IncompleteReadPort:
    contract_binding_only = True
    default_off = True
    synthetic_only = True
    port_calls_allowed = False
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(self, values):
        self.backend_instance = values["backend_anchor"]
        self.coordinator_instance = values["coordinator_anchor"]
        self.maintenance_lease_witness = values["maintenance_lease_witness"]
        self.protected_authenticated_authority_binding = values[
            "authenticated_authority_binding"
        ]

    def read_backend_snapshot_offline(self):
        raise AssertionError

    def read_transaction_log_audit_offline(self):
        raise AssertionError

    def read_prepared_catalog_offline(self):
        raise AssertionError

    def read_backend_capability_probe_offline(self):
        raise AssertionError


class StartupRecoveryEvidenceSourcePortsV2Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["evidence_source_ports_contract_v2"].bind_offline(
            protected_scope_binding=values["protected_scope_binding"],
            evidence_read_port=values["evidence_read_port_v2"],
            terminal_normalizer_port=values["terminal_normalizer_port_v2"],
            backend_instance=values["backend_anchor"],
            coordinator_instance=values["coordinator_anchor"],
            maintenance_lease_witness=values["maintenance_lease_witness"],
        )

    def test_harness_binds_six_ports_without_calling_them(self) -> None:
        result = harness.run_synthetic_evidence_source_ports_harness_v2()

        self.assertTrue(result["ok"])
        self.assertEqual(result["required_port_count"], 6)
        self.assertTrue(result["same_backend_instance_bound"])
        self.assertTrue(result["same_coordinator_instance_bound"])
        self.assertTrue(result["same_maintenance_lease_instance_bound"])
        self.assertTrue(result["same_authenticated_authority_instance_bound"])
        self.assertFalse(result["ports_called"])
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["durability_verified"])
        self.assertFalse(result["resolved_catalog_verified"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])

    def test_default_off_returns_before_inspecting_inputs(self) -> None:
        dormant = contract.DormantStartupRecoveryEvidenceSourcePortsContractV2()

        result = dormant.bind_offline(
            protected_scope_binding=_Explosive(),
            evidence_read_port=_Explosive(),
            terminal_normalizer_port=_Explosive(),
            backend_instance=_Explosive(),
            coordinator_instance=_Explosive(),
            maintenance_lease_witness=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_SOURCE_PORTS_V2_DEFAULT_OFF"])
        self.assertFalse(result["ports_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_missing_resolved_catalog_method_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        incomplete = _IncompleteReadPort(values)
        values["evidence_read_port_v2"] = incomplete
        values["evidence_source_ports_contract_v2"] = (
            harness.make_synthetic_evidence_source_ports_contract_v2(
                protected_scope_binding=values["protected_scope_binding"],
                evidence_read_port=incomplete,
                terminal_normalizer_port=values["terminal_normalizer_port_v2"],
                backend_instance=values["backend_anchor"],
                coordinator_instance=values["coordinator_anchor"],
                maintenance_lease_witness=values["maintenance_lease_witness"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["SIX_PORT_INTERFACE_INVALID"])
        self.assertFalse(result["ports_bound"])

    def test_substituted_backend_anchor_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        substitute = harness.SyntheticEvidenceBackendAnchorV2(
            values["protected_scope_binding"].binding
        )
        values["backend_anchor"] = substitute
        values["evidence_source_ports_contract_v2"] = (
            harness.make_synthetic_evidence_source_ports_contract_v2(
                protected_scope_binding=values["protected_scope_binding"],
                evidence_read_port=values["evidence_read_port_v2"],
                terminal_normalizer_port=values["terminal_normalizer_port_v2"],
                backend_instance=substitute,
                coordinator_instance=values["coordinator_anchor"],
                maintenance_lease_witness=values["maintenance_lease_witness"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["EVIDENCE_SOURCE_ANCHOR_IDENTITY_MISMATCH"]
        )
        self.assertEqual(values["evidence_read_port_v2"].call_count, 0)

    def test_substituted_coordinator_anchor_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        substitute = harness.SyntheticEvidenceCoordinatorAnchorV2(
            values["protected_scope_binding"].binding
        )
        values["coordinator_anchor"] = substitute
        values["evidence_source_ports_contract_v2"] = (
            harness.make_synthetic_evidence_source_ports_contract_v2(
                protected_scope_binding=values["protected_scope_binding"],
                evidence_read_port=values["evidence_read_port_v2"],
                terminal_normalizer_port=values["terminal_normalizer_port_v2"],
                backend_instance=values["backend_anchor"],
                coordinator_instance=substitute,
                maintenance_lease_witness=values["maintenance_lease_witness"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["EVIDENCE_SOURCE_ANCHOR_IDENTITY_MISMATCH"]
        )

    def test_substituted_authority_instance_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        other = harness.build_synthetic_evidence_source_ports_context_v2()
        values[
            "terminal_normalizer_port_v2"
        ].protected_authenticated_authority_binding = other[
            "authenticated_authority_binding"
        ]

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(
            result["reasons"], ["EVIDENCE_SOURCE_ANCHOR_IDENTITY_MISMATCH"]
        )
        self.assertEqual(values["terminal_normalizer_port_v2"].call_count, 0)

    def test_resealed_resolved_requirement_downgrade_is_rejected(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        result = self._bind(values)
        protected = result["protected_binding"]
        binding = copy.deepcopy(protected.binding)
        binding["resolved_state_support_required"] = False
        binding["binding_sha256"] = (
            contract.startup_recovery_evidence_source_port_binding_sha256_v2(
                binding
            )
        )
        tampered = contract.ProtectedStartupRecoveryEvidenceSourcePortBindingV2(
            protected_scope_binding=protected.protected_scope_binding,
            evidence_read_port=protected.evidence_read_port,
            terminal_normalizer_port=protected.terminal_normalizer_port,
            backend_instance=protected.backend_instance,
            coordinator_instance=protected.coordinator_instance,
            maintenance_lease_witness=protected.maintenance_lease_witness,
            binding=binding,
            binding_sha256=binding["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_evidence_source_port_binding_valid_v2(
                tampered
            )
        )

    def test_protected_binding_repr_hides_instances(self) -> None:
        values = harness.build_synthetic_evidence_source_ports_context_v2()
        protected = self._bind(values)["protected_binding"]

        rendered = repr(protected)

        self.assertEqual(
            rendered,
            "ProtectedStartupRecoveryEvidenceSourcePortBindingV2(<protected>)",
        )
        self.assertNotIn(protected.binding_sha256, rendered)

    def test_contract_remains_absent_from_runtime(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_production_"
            "startup_recovery_evidence_source_ports_contract_v2"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "ProtectedStartupRecoveryEvidenceSourcePortBindingV2", main_source
        )


if __name__ == "__main__":
    unittest.main()
