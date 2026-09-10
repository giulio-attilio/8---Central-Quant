"""In-memory harness for the production-shaped reference lease executor."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_harness_v2 as contract_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2 as executor_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_REFERENCE_EXECUTOR_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-MULTISTORE-OBSERVATION-"
    "LEASE-REFERENCE-EXECUTOR-OFFLINE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_710_000


def build_reference_lease_executor_context_v2(
    *,
    fail_transaction_acquire: bool = False,
    fail_resolved_acquire: bool = False,
    clock=None,
) -> dict[str, Any]:
    transaction_projection, resolved_projection = (
        contract_harness_v2.build_synthetic_production_lock_port_projections_v2()
    )
    binder = (
        contract_harness_v2.make_production_multistore_observation_lease_contract_v2(
            transaction_projection=transaction_projection,
            resolved_projection=resolved_projection,
        )
    )
    binding_result = binder.bind_offline(
        transaction_store_lock_port=transaction_projection,
        resolved_authority_store_lock_port=resolved_projection,
    )
    if binding_result.get("ok") is not True:
        raise RuntimeError("SYNTHETIC_PRODUCTION_LEASE_BINDING_FAILED")
    binding = binding_result["protected_binding"]
    authority = (
        executor_v2.build_synthetic_production_observation_authority_offline_v2(
            binding,
            maintenance_epoch=contract_harness_v2._sha("maintenance-epoch"),
            issued_at_epoch=SYNTHETIC_NOW_V2 - 1,
            expires_at_epoch=SYNTHETIC_NOW_V2 + 60,
        )
    )
    event_sink: list[tuple[str, str]] = []
    transaction_port = executor_v2.InMemoryProductionStoreLockPortDoubleV2(
        transaction_projection,
        fail_acquire=fail_transaction_acquire,
        event_sink=event_sink,
    )
    resolved_port = executor_v2.InMemoryProductionStoreLockPortDoubleV2(
        resolved_projection,
        fail_acquire=fail_resolved_acquire,
        event_sink=event_sink,
    )
    executor = executor_v2.ReferenceProductionMultistoreObservationLeaseExecutorV2(
        executor_v2.ReferenceProductionMultistoreObservationLeaseExecutorConfigV2(
            enabled=True,
            scope_attestation=(
                executor_v2.OFFLINE_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_ATTESTATION_V2
            ),
            expected_binding_sha256=binding.binding_sha256,
            expected_authority_sha256=authority.authority_sha256,
            expected_authority_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    authority
                )
            ),
            expected_transaction_lock_port_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    transaction_port
                )
            ),
            expected_resolved_lock_port_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_port
                )
            ),
            max_ttl_seconds=300,
            lock_timeout_seconds=1.0,
        ),
        clock=clock or (lambda: SYNTHETIC_NOW_V2),
        nonce_source=lambda: "synthetic-reference-production-lease",
    )
    return {
        "binding": binding,
        "authority": authority,
        "transaction_projection": transaction_projection,
        "resolved_projection": resolved_projection,
        "transaction_port": transaction_port,
        "resolved_port": resolved_port,
        "executor": executor,
        "event_sink": event_sink,
    }


def run_production_multistore_observation_lease_reference_executor_offline_harness_v2(
) -> dict[str, Any]:
    values = build_reference_lease_executor_context_v2()
    executor = values["executor"]
    token = None
    with executor.hold_offline(
        binding=values["binding"],
        authority=values["authority"],
        transaction_store_lock_port=values["transaction_port"],
        resolved_authority_store_lock_port=values["resolved_port"],
        expires_at_epoch=SYNTHETIC_NOW_V2 + 30,
    ) as active_token:
        token = active_token
        live = executor.validate_live(
            active_token,
            transaction_store_lock_port=values["transaction_port"],
            resolved_authority_store_lock_port=values["resolved_port"],
            now_epoch=SYNTHETIC_NOW_V2,
        )
        active_snapshot = executor.snapshot()
    inactive_snapshot = executor.snapshot()
    invalid_after_release = not executor.validate_live(
        token,
        transaction_store_lock_port=values["transaction_port"],
        resolved_authority_store_lock_port=values["resolved_port"],
        now_epoch=SYNTHETIC_NOW_V2,
    )
    expected_events = [
        ("ACQUIRE", "RAW_TRANSACTION_STORE"),
        ("ACQUIRE", "RESOLVED_AUTHORITY_LEDGER"),
        ("RELEASE", "RESOLVED_AUTHORITY_LEDGER"),
        ("RELEASE", "RAW_TRANSACTION_STORE"),
    ]
    ok = bool(
        live
        and active_snapshot["active"] is True
        and active_snapshot["held_lock_count"] == 2
        and active_snapshot["all_handles_live"] is True
        and invalid_after_release
        and inactive_snapshot["active"] is False
        and inactive_snapshot["held_lock_count"] == 0
        and values["event_sink"] == expected_events
        and values["transaction_port"].snapshot()["active"] is False
        and values["resolved_port"].snapshot()["active"] is False
        and repr(token)
        == "ProtectedReferenceProductionObservationLeaseTokenV2(<protected>)"
    )
    return {
        "ok": ok,
        "status": (
            "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_OFFLINE_HARNESS_V2_PASSED"
            if ok
            else "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_OFFLINE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_REFERENCE_EXECUTOR_OFFLINE_HARNESS_V2_VERSION,
        "two_locks_held_under_same_token": bool(
            active_snapshot["held_lock_count"] == 2
        ),
        "acquire_order_verified": values["event_sink"][:2]
        == expected_events[:2],
        "reverse_release_order_verified": values["event_sink"][2:]
        == expected_events[2:],
        "lease_invalid_after_release": invalid_after_release,
        "in_memory_only": True,
        "production_lock_ports_bound": False,
        "store_called": False,
        "filesystem_accessed": False,
        "network_accessed": False,
        "write_executed": False,
        "registry_write": False,
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
    "SYNTHETIC_NOW_V2",
    "build_reference_lease_executor_context_v2",
    "run_production_multistore_observation_lease_reference_executor_offline_harness_v2",
]
