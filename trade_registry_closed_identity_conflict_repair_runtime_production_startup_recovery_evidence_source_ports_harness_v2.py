"""Synthetic no-call harness for evidence source ports contract V2."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_harness_v1 as scope_harness_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SOURCE-PORTS-HARNESS-V2"
)


class SyntheticEvidenceBackendAnchorV2:
    def __init__(self, scope: dict[str, Any]) -> None:
        self.backend_instance_sha256 = scope["backend_instance_sha256"]
        self.registry_path_binding_sha256 = scope[
            "registry_path_binding_sha256"
        ]
        self.wal_storage_binding_sha256 = scope["wal_storage_binding_sha256"]
        self.resolved_ledger_storage_binding_sha256 = scope[
            "resolved_ledger_storage_binding_sha256"
        ]

    def __repr__(self) -> str:
        return "SyntheticEvidenceBackendAnchorV2(<protected>)"


class SyntheticEvidenceCoordinatorAnchorV2:
    def __init__(self, scope: dict[str, Any]) -> None:
        self.lock_namespace_sha256 = scope["lock_namespace_sha256"]

    def __repr__(self) -> str:
        return "SyntheticEvidenceCoordinatorAnchorV2(<protected>)"


class SyntheticEvidenceMaintenanceLeaseWitnessV2:
    def __init__(self, scope: dict[str, Any]) -> None:
        self.maintenance_epoch = scope["maintenance_epoch"]
        self.receipt_sha256 = scope[
            "candidate_maintenance_lease_receipt_sha256"
        ]

    def __repr__(self) -> str:
        return "SyntheticEvidenceMaintenanceLeaseWitnessV2(<protected>)"


class SyntheticDormantEvidenceReadPortV2:
    contract_binding_only = True
    default_off = True
    synthetic_only = True
    port_calls_allowed = False
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(
        self,
        *,
        backend_instance: Any,
        coordinator_instance: Any,
        maintenance_lease_witness: Any,
        protected_authenticated_authority_binding: Any,
    ) -> None:
        self.backend_instance = backend_instance
        self.coordinator_instance = coordinator_instance
        self.maintenance_lease_witness = maintenance_lease_witness
        self.protected_authenticated_authority_binding = (
            protected_authenticated_authority_binding
        )
        self._call_count = 0

    def _forbidden(self):
        self._call_count += 1
        raise AssertionError("dormant evidence source port must not be called")

    def read_backend_snapshot_offline(self, *_args, **_kwargs):
        return self._forbidden()

    def read_transaction_log_audit_offline(self, *_args, **_kwargs):
        return self._forbidden()

    def read_prepared_catalog_offline(self, *_args, **_kwargs):
        return self._forbidden()

    def read_resolved_catalog_offline(self, *_args, **_kwargs):
        return self._forbidden()

    def read_backend_capability_probe_offline(self, *_args, **_kwargs):
        return self._forbidden()

    @property
    def call_count(self) -> int:
        return self._call_count

    def __repr__(self) -> str:
        return "SyntheticDormantEvidenceReadPortV2(<protected>)"


class SyntheticDormantTerminalReceiptNormalizerPortV2:
    contract_binding_only = True
    default_off = True
    synthetic_only = True
    port_calls_allowed = False
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(
        self,
        *,
        backend_instance: Any,
        coordinator_instance: Any,
        maintenance_lease_witness: Any,
        protected_authenticated_authority_binding: Any,
    ) -> None:
        self.backend_instance = backend_instance
        self.coordinator_instance = coordinator_instance
        self.maintenance_lease_witness = maintenance_lease_witness
        self.protected_authenticated_authority_binding = (
            protected_authenticated_authority_binding
        )
        self._call_count = 0

    def normalize_terminal_receipt_offline(self, *_args, **_kwargs):
        self._call_count += 1
        raise AssertionError("dormant terminal normalizer must not be called")

    @property
    def call_count(self) -> int:
        return self._call_count

    def __repr__(self) -> str:
        return "SyntheticDormantTerminalReceiptNormalizerPortV2(<protected>)"


def make_synthetic_evidence_source_ports_contract_v2(
    *,
    protected_scope_binding: Any,
    evidence_read_port: Any,
    terminal_normalizer_port: Any,
    backend_instance: Any,
    coordinator_instance: Any,
    maintenance_lease_witness: Any,
) -> contract.DormantStartupRecoveryEvidenceSourcePortsContractV2:
    authority = (
        protected_scope_binding.protected_batch_session
        .authenticated_authority_binding
    )
    return contract.DormantStartupRecoveryEvidenceSourcePortsContractV2(
        config=contract.DormantStartupRecoveryEvidenceSourcePortsConfigV2(
            enabled=True,
            scope_attestation=(
                contract.OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2
            ),
            expected_scope_binding_sha256=protected_scope_binding.binding_sha256,
            expected_read_port_object_identity_sha256=(
                contract.startup_recovery_evidence_source_object_identity_sha256_v2(
                    evidence_read_port
                )
            ),
            expected_normalizer_port_object_identity_sha256=(
                contract.startup_recovery_evidence_source_object_identity_sha256_v2(
                    terminal_normalizer_port
                )
            ),
            expected_backend_object_identity_sha256=(
                contract.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend_instance
                )
            ),
            expected_coordinator_object_identity_sha256=(
                contract.startup_recovery_evidence_source_object_identity_sha256_v2(
                    coordinator_instance
                )
            ),
            expected_maintenance_lease_witness_object_identity_sha256=(
                contract.startup_recovery_evidence_source_object_identity_sha256_v2(
                    maintenance_lease_witness
                )
            ),
            expected_authenticated_authority_binding_sha256=(
                authority.binding_sha256
            ),
        )
    )


def build_synthetic_evidence_source_ports_context_v2() -> dict[str, Any]:
    values = scope_harness_v1.build_synthetic_evidence_reference_builder_context_v1()
    protected_scope = values["protected_scope_binding"]
    scope = protected_scope.binding
    authority = (
        protected_scope.protected_batch_session
        .authenticated_authority_binding
    )
    backend = SyntheticEvidenceBackendAnchorV2(scope)
    coordinator = SyntheticEvidenceCoordinatorAnchorV2(scope)
    lease = SyntheticEvidenceMaintenanceLeaseWitnessV2(scope)
    read_port = SyntheticDormantEvidenceReadPortV2(
        backend_instance=backend,
        coordinator_instance=coordinator,
        maintenance_lease_witness=lease,
        protected_authenticated_authority_binding=authority,
    )
    normalizer = SyntheticDormantTerminalReceiptNormalizerPortV2(
        backend_instance=backend,
        coordinator_instance=coordinator,
        maintenance_lease_witness=lease,
        protected_authenticated_authority_binding=authority,
    )
    source_contract = make_synthetic_evidence_source_ports_contract_v2(
        protected_scope_binding=protected_scope,
        evidence_read_port=read_port,
        terminal_normalizer_port=normalizer,
        backend_instance=backend,
        coordinator_instance=coordinator,
        maintenance_lease_witness=lease,
    )
    return {
        **values,
        "authenticated_authority_binding": authority,
        "backend_anchor": backend,
        "coordinator_anchor": coordinator,
        "maintenance_lease_witness": lease,
        "evidence_read_port_v2": read_port,
        "terminal_normalizer_port_v2": normalizer,
        "evidence_source_ports_contract_v2": source_contract,
    }


def run_synthetic_evidence_source_ports_harness_v2() -> dict[str, Any]:
    values = build_synthetic_evidence_source_ports_context_v2()
    result = values["evidence_source_ports_contract_v2"].bind_offline(
        protected_scope_binding=values["protected_scope_binding"],
        evidence_read_port=values["evidence_read_port_v2"],
        terminal_normalizer_port=values["terminal_normalizer_port_v2"],
        backend_instance=values["backend_anchor"],
        coordinator_instance=values["coordinator_anchor"],
        maintenance_lease_witness=values["maintenance_lease_witness"],
    )
    protected = result.get("protected_binding")
    binding = protected.binding if protected is not None else {}
    safe = bool(
        result.get("ok") is True
        and result.get("scope_verified") is True
        and result.get("authority_binding_verified") is True
        and result.get("interface_verified") is True
        and result.get("object_identity_vector_verified") is True
        and result.get("anchor_identity_vector_verified") is True
        and result.get("ports_bound") is True
        and contract.protected_startup_recovery_evidence_source_port_binding_valid_v2(
            protected
        )
        and binding.get("required_port_count") == 6
        and binding.get("complete_resolved_catalog_required") is True
        and binding.get("resolved_state_support_required") is True
        and binding.get("empirical_durability_probe_required") is True
        and binding.get("authenticated_authority_current_state_revalidation_required")
        is True
        and binding.get("maintenance_lease_revalidation_per_call_required")
        is True
        and values["evidence_read_port_v2"].call_count == 0
        and values["terminal_normalizer_port_v2"].call_count == 0
        and result.get("ports_called") is False
        and result.get("backend_called") is False
        and result.get("coordinator_called") is False
        and result.get("maintenance_lease_called") is False
        and result.get("evidence_created") is False
        and result.get("durability_verified") is False
        and result.get("resolved_catalog_verified") is False
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("production_authority") is False
        and result.get("runtime_integrated") is False
        and result.get("live_allowed") is False
        and result.get("no_order_sent") is True
    )
    return {
        "ok": safe,
        "status": (
            "C3_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_V2_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_V2_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_HARNESS_V2_VERSION,
        "required_port_count": binding.get("required_port_count", 0),
        "same_backend_instance_bound": binding.get(
            "same_backend_instance_required"
        )
        is True,
        "same_coordinator_instance_bound": binding.get(
            "same_coordinator_instance_required"
        )
        is True,
        "same_maintenance_lease_instance_bound": binding.get(
            "same_maintenance_lease_instance_required"
        )
        is True,
        "same_authenticated_authority_instance_bound": binding.get(
            "same_authenticated_authority_instance_required"
        )
        is True,
        "ports_called": False,
        "evidence_created": False,
        "durability_verified": False,
        "resolved_catalog_verified": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "SyntheticDormantEvidenceReadPortV2",
    "SyntheticDormantTerminalReceiptNormalizerPortV2",
    "SyntheticEvidenceBackendAnchorV2",
    "SyntheticEvidenceCoordinatorAnchorV2",
    "SyntheticEvidenceMaintenanceLeaseWitnessV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_HARNESS_V2_VERSION",
    "build_synthetic_evidence_source_ports_context_v2",
    "make_synthetic_evidence_source_ports_contract_v2",
    "run_synthetic_evidence_source_ports_harness_v2",
]
