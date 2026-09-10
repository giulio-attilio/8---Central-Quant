"""Synthetic in-memory harness for the dormant raw-transaction consumer."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1 as production_store
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_harness_v1 as adapter_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-CONSUMER-HARNESS-V1"
)

_NOW = adapter_harness._NOW


def build_synthetic_handoff_raw_transaction_consumer_inputs_v1() -> dict[str, Any]:
    adapter_inputs = (
        adapter_harness.build_synthetic_handoff_raw_request_adapter_inputs_v1()
    )
    canonical_namespace = coordinator.canonical_runtime_lock_namespace_v1()
    maintenance = adapter_inputs["maintenance_attestation"]
    maintenance["lock_namespace_sha256"] = canonical_namespace
    maintenance["attestation_sha256"] = (
        adapter.maintenance_attestation_sha256_v1(maintenance)
    )
    proof = adapter_inputs["canonical_raw_proof"]
    proof["maintenance_attestation_sha256"] = maintenance[
        "attestation_sha256"
    ]
    proof["proof_sha256"] = adapter.canonical_raw_proof_sha256_v1(proof)
    adapter_result = (
        adapter_harness.build_synthetic_handoff_raw_request_adapter_v1().project_offline(
            **adapter_inputs
        )
    )
    if adapter_result.get("ok") is not True:
        raise AssertionError("synthetic handoff raw request projection failed closed")

    permit = coordinator.WriterMaintenancePermitV1(
        maintenance_epoch=maintenance["maintenance_epoch"],
        state="QUIESCED",
        lock_namespace_sha256=canonical_namespace,
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )
    backend_attestation = (
        production_store.build_production_backend_capability_attestation_v1(
            "synthetic-memory-only/c3-registry.json",
            backend_kind="SYNTHETIC_IN_MEMORY_WITNESS_V1",
            storage_scope="TEMPORARY_TEST",
        )
    )
    witness = consumer.InMemoryLiveMaintenanceLeaseWitnessV1(
        clock=lambda: _NOW,
        nonce_source=lambda: "synthetic-live-lease-witness-nonce-v1",
    )
    dormant_consumer = consumer.DormantHandoffRawTransactionConsumerV1(
        config=consumer.DormantHandoffRawTransactionConsumerConfigV1(
            enabled=True,
            scope_attestation=consumer.OFFLINE_HANDOFF_RAW_TRANSACTION_CONSUMER_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: _NOW,
        lease_witness=witness,
    )
    return {
        "consumer": dormant_consumer,
        "lease_witness": witness,
        "adapter_result": adapter_result,
        "maintenance_permit": permit,
        "backend_capability_attestation": backend_attestation,
        "lease_expires_at_epoch": _NOW + 45,
    }


def run_synthetic_handoff_raw_transaction_consumer_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_handoff_raw_transaction_consumer_inputs_v1()
    witness = inputs["lease_witness"]
    permit = inputs["maintenance_permit"]
    with witness.hold_offline(
        permit,
        expires_at_epoch=inputs["lease_expires_at_epoch"],
    ) as live_token:
        result = inputs["consumer"].consume_offline(
            adapter_result=inputs["adapter_result"],
            maintenance_permit=permit,
            live_lease_token=live_token,
            backend_capability_attestation=inputs[
                "backend_capability_attestation"
            ],
        )
        live_during_consume = witness.snapshot()["active"] is True
    replay_after_release = inputs["consumer"].consume_offline(
        adapter_result=inputs["adapter_result"],
        maintenance_permit=permit,
        live_lease_token=live_token,
        backend_capability_attestation=inputs["backend_capability_attestation"],
    )
    protected = result.get("protected_intent")
    protected_surface_safe = bool(
        type(protected) is consumer.ProtectedRawTransactionInvocationIntentV1
        and repr(protected)
        == "ProtectedRawTransactionInvocationIntentV1(<protected>)"
        and not hasattr(protected, "serialize")
        and not hasattr(protected, "apply")
        and not hasattr(protected, "invoke")
        and not hasattr(protected, "commit")
    )
    ok = bool(
        result.get("ok") is True
        and result.get("adapter_projection_verified") is True
        and result.get("same_permit_instance_verified") is True
        and result.get("lease_live_verified_synthetic") is True
        and result.get("canonical_lock_namespace_verified") is True
        and result.get("backend_capabilities_verified_synthetic") is True
        and result.get("deadline_revalidated") is True
        and result.get("invocation_intent_projected") is True
        and result.get("backend_referenced") is False
        and result.get("raw_transaction_store_called") is False
        and result.get("transaction_persistence_allowed") is False
        and result.get("write_executed") is False
        and live_during_consume
        and witness.snapshot()["active"] is False
        and replay_after_release.get("ok") is False
        and replay_after_release.get("reasons")
        == ["MAINTENANCE_LEASE_NOT_LIVE_OR_INSTANCE_MISMATCH"]
        and protected_surface_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_HANDOFF_RAW_TRANSACTION_CONSUMER_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_HANDOFF_RAW_TRANSACTION_CONSUMER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_HARNESS_V1_VERSION,
        "protected_surface_safe": protected_surface_safe,
        "adapter_projection_verified": result.get("adapter_projection_verified")
        is True,
        "same_permit_instance_verified": result.get(
            "same_permit_instance_verified"
        )
        is True,
        "live_lease_verified_synthetic": result.get(
            "lease_live_verified_synthetic"
        )
        is True,
        "lease_live_during_consume": live_during_consume,
        "lease_released_after_context": witness.snapshot()["active"] is False,
        "replay_after_lease_release_blocked": replay_after_release.get("ok")
        is False,
        "canonical_lock_namespace_verified": result.get(
            "canonical_lock_namespace_verified"
        )
        is True,
        "backend_capabilities_verified_synthetic": result.get(
            "backend_capabilities_verified_synthetic"
        )
        is True,
        "backend_storage_scope": "TEMPORARY_TEST",
        "backend_referenced": False,
        "raw_transaction_store_called": False,
        "transaction_persistence_allowed": False,
        "runtime_integrated": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_CONSUMER_HARNESS_V1_VERSION",
    "build_synthetic_handoff_raw_transaction_consumer_inputs_v1",
    "run_synthetic_handoff_raw_transaction_consumer_harness_v1",
]
