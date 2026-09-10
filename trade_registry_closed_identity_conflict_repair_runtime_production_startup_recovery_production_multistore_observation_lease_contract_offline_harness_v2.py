"""In-memory harness for the dormant production multistore lease contract."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as contract_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-MULTISTORE-OBSERVATION-"
    "LEASE-CONTRACT-OFFLINE-HARNESS-V2"
)


def _sha(label: str) -> str:
    return hash_v2.stable_sha256_v2(
        {"production_multistore_lease_contract_harness": label}
    )


def build_synthetic_production_lock_port_projections_v2() -> tuple[Any, Any]:
    transaction = contract_v2.build_production_store_lock_port_projection_offline_v2(
        port_role=contract_v2.TRANSACTION_STORE_ROLE_V2,
        source_contract_version=(
            contract_v2.EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2
        ),
        store_identity_sha256=_sha("transaction-store-identity"),
        storage_binding_sha256=_sha("transaction-store-storage-binding"),
        lock_namespace_sha256=_sha("transaction-store-lock-namespace"),
    )
    resolved = contract_v2.build_production_store_lock_port_projection_offline_v2(
        port_role=contract_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2,
        source_contract_version=(
            contract_v2.EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
        ),
        store_identity_sha256=_sha("resolved-authority-store-identity"),
        storage_binding_sha256=_sha("resolved-authority-storage-binding"),
        lock_namespace_sha256=_sha("resolved-authority-lock-namespace"),
    )
    return transaction, resolved


def make_production_multistore_observation_lease_contract_v2(
    *, transaction_projection: Any, resolved_projection: Any, enabled: bool = True
) -> contract_v2.DormantProductionMultistoreObservationLeaseContractV2:
    return contract_v2.DormantProductionMultistoreObservationLeaseContractV2(
        contract_v2.DormantProductionMultistoreObservationLeaseConfigV2(
            enabled=enabled,
            scope_attestation=(
                contract_v2.OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
            ),
            expected_transaction_store_projection_sha256=(
                transaction_projection.projection_sha256
            ),
            expected_resolved_authority_store_projection_sha256=(
                resolved_projection.projection_sha256
            ),
            expected_writer_coordination_binding_sha256=_sha(
                "writer-coordination-binding"
            ),
            expected_maintenance_lease_contract_sha256=_sha(
                "maintenance-lease-contract"
            ),
            expected_authenticated_authority_contract_sha256=_sha(
                "authenticated-authority-contract"
            ),
            required_writer_count=19,
        )
    )


def run_production_multistore_observation_lease_contract_offline_harness_v2(
) -> dict[str, Any]:
    transaction, resolved = build_synthetic_production_lock_port_projections_v2()
    contract = make_production_multistore_observation_lease_contract_v2(
        transaction_projection=transaction,
        resolved_projection=resolved,
    )
    result = contract.bind_offline(
        transaction_store_lock_port=transaction,
        resolved_authority_store_lock_port=resolved,
    )
    protected = result.get("protected_binding")
    binding = dict(protected.binding) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and result.get("status")
        == "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_V2_VERIFIED_OFFLINE"
        and result.get("contract_verified") is True
        and result.get("lock_order_verified") is True
        and result.get("persistent_store_requirements_verified") is True
        and contract_v2.protected_production_multistore_observation_lease_binding_valid_v2(
            protected
        )
        and binding.get("lock_order") == list(contract_v2.LOCK_ORDER_V2)
        and binding.get("required_lock_count") == 2
        and binding.get("required_writer_count") == 19
        and binding.get("max_lease_ttl_seconds") == 300
        and binding.get("max_lock_acquire_timeout_seconds") == 1
        and binding.get("same_lease_instance_required") is True
        and binding.get("same_authenticated_authority_instance_required") is True
        and binding.get("same_writer_coordinator_instance_required") is True
        and binding.get("maintenance_lease_required") is True
        and binding.get("pending_transaction_recovery_required_before_readiness")
        is True
        and binding.get("all_reads_token_gated_required") is True
        and binding.get("reverse_order_release_required") is True
        and binding.get("production_lock_ports_bound") is False
        and binding.get("lease_acquire_allowed") is False
        and result.get("store_called") is False
        and result.get("filesystem_accessed") is False
        and result.get("network_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("broker_called") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("no_order_sent") is True
        and result.get("production_authority") is False
        and result.get("production_ready") is False
        and result.get("runtime_integrated") is False
        and result.get("activation_allowed") is False
        and result.get("live_allowed") is False
        and not hasattr(type(contract), "acquire")
        and not hasattr(type(contract), "release")
    )
    return {
        "ok": ok,
        "status": (
            "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_HARNESS_V2_PASSED"
            if ok
            else "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_HARNESS_V2_VERSION,
        "contract_result": result,
        "two_persistent_lock_ports_required": binding.get("required_lock_count")
        == 2,
        "acquisition_surface_absent": not hasattr(type(contract), "acquire"),
        "synthetic_contract_only": True,
        "production_lock_ports_bound": False,
        "store_called": False,
        "filesystem_accessed": False,
        "network_accessed": False,
        "real_registry_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "build_synthetic_production_lock_port_projections_v2",
    "make_production_multistore_observation_lease_contract_v2",
    "run_production_multistore_observation_lease_contract_offline_harness_v2",
]
