from __future__ import annotations

import copy
import unittest
from pathlib import Path

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1 as harness


ROOT = Path(__file__).resolve().parents[1]


class _Explosive:
    def __getattribute__(self, _name):
        raise AssertionError("default-off contract must not inspect dependencies")


class _IncompleteReadPort:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def read_backend_snapshot_offline(self):
        raise AssertionError

    def read_transaction_log_audit_offline(self):
        raise AssertionError

    def read_prepared_catalog_offline(self):
        raise AssertionError

    def read_backend_capability_probe_offline(self):
        raise AssertionError


class _UnsafeNormalizer:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = True

    def normalize_terminal_receipt_offline(self):
        raise AssertionError


class StartupRecoveryEvidenceBuilderPortsV1Tests(unittest.TestCase):
    @staticmethod
    def _bind(values):
        return values["ports_contract"].bind_offline(
            protected_scope_binding=values["protected_scope_binding"],
            evidence_read_port=values["evidence_read_port"],
            terminal_normalizer_port=values["terminal_normalizer_port"],
        )

    def test_harness_binds_all_ports_without_calling_them(self) -> None:
        result = harness.run_synthetic_evidence_builder_ports_harness_v1()

        self.assertTrue(result["ok"])
        self.assertTrue(result["all_port_surfaces_bound"])
        self.assertEqual(result["read_port_calls"], 0)
        self.assertEqual(result["normalizer_port_calls"], 0)
        self.assertFalse(result["evidence_created"])
        self.assertFalse(result["evidence_builder_available"])
        self.assertFalse(result["runtime_integrated"])
        self.assertFalse(result["live_allowed"])
        self.assertTrue(result["no_order_sent"])

    def test_default_off_returns_before_inspecting_dependencies(self) -> None:
        dormant = contract.DormantStartupRecoveryEvidenceBuilderPortsContractV1()

        result = dormant.bind_offline(
            protected_scope_binding=_Explosive(),
            evidence_read_port=_Explosive(),
            terminal_normalizer_port=_Explosive(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_BUILDER_PORTS_DEFAULT_OFF"])
        self.assertFalse(result["ports_called"])
        self.assertFalse(result["filesystem_accessed"])

    def test_missing_resolved_catalog_surface_fails_closed(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        incomplete = _IncompleteReadPort()
        values["evidence_read_port"] = incomplete
        values["ports_contract"] = (
            harness.make_synthetic_evidence_builder_ports_contract_v1(
                scope_binding_sha256=values[
                    "protected_scope_binding"
                ].binding_sha256,
                evidence_read_port=incomplete,
                terminal_normalizer_port=values["terminal_normalizer_port"],
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_READ_PORT_INVALID"])
        self.assertFalse(result["normalizer_port_verified"])
        self.assertFalse(result["ports_called"])

    def test_unsafe_normalizer_fails_without_reading_any_port(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        unsafe = _UnsafeNormalizer()
        values["terminal_normalizer_port"] = unsafe
        values["ports_contract"] = (
            harness.make_synthetic_evidence_builder_ports_contract_v1(
                scope_binding_sha256=values[
                    "protected_scope_binding"
                ].binding_sha256,
                evidence_read_port=values["evidence_read_port"],
                terminal_normalizer_port=unsafe,
            )
        )

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["TERMINAL_NORMALIZER_PORT_INVALID"])
        self.assertEqual(
            sum(values["evidence_read_port"].counters().values()), 0
        )
        self.assertFalse(result["ports_called"])

    def test_different_read_port_instance_fails_identity_pin(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        values["evidence_read_port"] = harness.SyntheticEvidenceReadPortDoubleV1()

        result = self._bind(values)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reasons"], ["EVIDENCE_READ_PORT_INVALID"])
        self.assertFalse(result["read_port_verified"])

    def test_protected_binding_rejects_dependency_substitution(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        result = self._bind(values)
        protected = result["protected_port_binding"]
        substituted = contract.ProtectedStartupRecoveryEvidenceBuilderPortBindingV1(
            protected_scope_binding=protected.protected_scope_binding,
            evidence_read_port=harness.SyntheticEvidenceReadPortDoubleV1(),
            terminal_normalizer_port=protected.terminal_normalizer_port,
            binding=protected.binding,
            binding_sha256=protected.binding_sha256,
        )

        self.assertFalse(
            contract.protected_startup_recovery_evidence_builder_port_binding_valid_v1(
                substituted
            )
        )

    def test_protected_binding_rejects_resealed_builder_available_claim(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        result = self._bind(values)
        protected = result["protected_port_binding"]
        binding = copy.deepcopy(protected.binding)
        binding["evidence_builder_available"] = True
        binding["binding_sha256"] = (
            contract.startup_recovery_evidence_builder_port_binding_sha256_v1(
                binding
            )
        )
        tampered = contract.ProtectedStartupRecoveryEvidenceBuilderPortBindingV1(
            protected_scope_binding=protected.protected_scope_binding,
            evidence_read_port=protected.evidence_read_port,
            terminal_normalizer_port=protected.terminal_normalizer_port,
            binding=binding,
            binding_sha256=binding["binding_sha256"],
        )

        self.assertFalse(
            contract.protected_startup_recovery_evidence_builder_port_binding_valid_v1(
                tampered
            )
        )

    def test_binding_requires_initial_final_and_resolved_phases(self) -> None:
        values = harness.build_synthetic_evidence_builder_ports_context_v1()
        result = self._bind(values)
        binding = result["protected_port_binding"].binding

        self.assertIn("INITIAL_RESOLVED_CATALOG", binding["required_phase_sequence"])
        self.assertIn("FINAL_RESOLVED_CATALOG", binding["required_phase_sequence"])
        self.assertIn(
            "TERMINAL_RECEIPT_NORMALIZATION_PER_PENDING_ITEM",
            binding["required_phase_sequence"],
        )
        self.assertTrue(binding["same_read_port_instance_required"])
        self.assertTrue(binding["same_normalizer_port_instance_required"])
        self.assertEqual(
            repr(result["protected_port_binding"]),
            "ProtectedStartupRecoveryEvidenceBuilderPortBindingV1(<protected>)",
        )

    def test_contract_remains_absent_from_runtime_composition(self) -> None:
        main_source = (ROOT / "main.py").read_text(encoding="utf-8")
        module_name = (
            "trade_registry_closed_identity_conflict_repair_runtime_"
            "production_startup_recovery_evidence_builder_ports_contract_v1"
        )

        self.assertNotIn(module_name, main_source)
        self.assertNotIn(
            "ProtectedStartupRecoveryEvidenceBuilderPortBindingV1", main_source
        )


if __name__ == "__main__":
    unittest.main()
