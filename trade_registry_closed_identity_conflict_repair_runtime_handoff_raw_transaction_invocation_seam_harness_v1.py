"""In-memory success/interruption/recovery harness for the invocation seam."""

from __future__ import annotations

import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_harness_v1 as consumer_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1 as adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-RAW-TRANSACTION-INVOCATION-SEAM-HARNESS-V1"
)

_NOW = consumer_harness._NOW


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_synthetic_raw_transaction_invocation_seam_inputs_v1(
    *,
    fault_mode: str | None = None,
) -> dict[str, Any]:
    upstream = (
        consumer_harness.build_synthetic_handoff_raw_transaction_consumer_inputs_v1()
    )
    store = seam.InMemoryAttestedRawTransactionStoreDoubleV1(
        backend_capability_attestation=upstream[
            "backend_capability_attestation"
        ],
        nonce=(
            "synthetic-interrupted-store-instance-v1"
            if fault_mode
            else "synthetic-success-store-instance-v1"
        ),
        fault_mode=fault_mode,
    )
    invocation_seam = seam.DormantRawTransactionInvocationSeamV1(
        config=seam.DormantRawTransactionInvocationSeamConfigV1(
            enabled=True,
            scope_attestation=seam.OFFLINE_RAW_TRANSACTION_INVOCATION_SEAM_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: _NOW,
        lease_witness=upstream["lease_witness"],
        store_double=store,
    )
    return {
        **upstream,
        "invocation_seam": invocation_seam,
        "store_double": store,
    }


def build_synthetic_recovery_maintenance_v1() -> dict[str, Any]:
    epoch = _sha256_text("synthetic-fresh-recovery-maintenance-epoch-v1")
    permit = coordinator.WriterMaintenancePermitV1(
        maintenance_epoch=epoch,
        state="QUIESCED",
        lock_namespace_sha256=coordinator.canonical_runtime_lock_namespace_v1(),
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )
    attestation = {
        "attestation_version": adapter.MAINTENANCE_ATTESTATION_VERSION_V1,
        "state": "QUIESCED",
        "maintenance_epoch": epoch,
        "lock_namespace_sha256": coordinator.canonical_runtime_lock_namespace_v1(),
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "shared_lock_acquired": True,
        "issued_at_epoch": _NOW,
        "expires_at_epoch": _NOW + 30,
        "synthetic_only": True,
        "production_evidence": False,
    }
    attestation["attestation_sha256"] = (
        adapter.maintenance_attestation_sha256_v1(attestation)
    )
    return {
        "permit": permit,
        "attestation": attestation,
        "lease_expires_at_epoch": _NOW + 25,
    }


def _consumer_result_inside_live_lease(inputs: dict[str, Any], token) -> dict:
    return inputs["consumer"].consume_offline(
        adapter_result=inputs["adapter_result"],
        maintenance_permit=inputs["maintenance_permit"],
        live_lease_token=token,
        backend_capability_attestation=inputs["backend_capability_attestation"],
    )


def run_synthetic_raw_transaction_invocation_seam_harness_v1() -> dict[str, Any]:
    success_inputs = build_synthetic_raw_transaction_invocation_seam_inputs_v1()
    success_witness = success_inputs["lease_witness"]
    success_permit = success_inputs["maintenance_permit"]
    with success_witness.hold_offline(
        success_permit,
        expires_at_epoch=success_inputs["lease_expires_at_epoch"],
    ) as success_token:
        success_consumer = _consumer_result_inside_live_lease(
            success_inputs, success_token
        )
        success = success_inputs["invocation_seam"].invoke_offline(
            consumer_result=success_consumer,
            adapter_result=success_inputs["adapter_result"],
            maintenance_permit=success_permit,
            live_lease_token=success_token,
        )
        replay = success_inputs["invocation_seam"].invoke_offline(
            consumer_result=success_consumer,
            adapter_result=success_inputs["adapter_result"],
            maintenance_permit=success_permit,
            live_lease_token=success_token,
        )

    interrupted_inputs = build_synthetic_raw_transaction_invocation_seam_inputs_v1(
        fault_mode="AFTER_PREPARED"
    )
    interrupted_witness = interrupted_inputs["lease_witness"]
    interrupted_permit = interrupted_inputs["maintenance_permit"]
    with interrupted_witness.hold_offline(
        interrupted_permit,
        expires_at_epoch=interrupted_inputs["lease_expires_at_epoch"],
    ) as interrupted_token:
        interrupted_consumer = _consumer_result_inside_live_lease(
            interrupted_inputs, interrupted_token
        )
        interrupted = interrupted_inputs["invocation_seam"].invoke_offline(
            consumer_result=interrupted_consumer,
            adapter_result=interrupted_inputs["adapter_result"],
            maintenance_permit=interrupted_permit,
            live_lease_token=interrupted_token,
        )
    recovery_command = interrupted.get("protected_recovery_command")
    recovery_material = build_synthetic_recovery_maintenance_v1()
    recovery_permit = recovery_material["permit"]
    with interrupted_witness.hold_offline(
        recovery_permit,
        expires_at_epoch=recovery_material["lease_expires_at_epoch"],
    ) as recovery_token:
        recovered = interrupted_inputs["invocation_seam"].recover_offline(
            recovery_command=recovery_command,
            recovery_maintenance_permit=recovery_permit,
            recovery_live_lease_token=recovery_token,
            recovery_maintenance_attestation=recovery_material["attestation"],
        )

    recovery_surface_safe = bool(
        type(recovery_command)
        is seam.ProtectedSyntheticPreparedRecoveryCommandV1
        and repr(recovery_command)
        == "ProtectedSyntheticPreparedRecoveryCommandV1(<protected>)"
        and not hasattr(recovery_command, "apply")
        and not hasattr(recovery_command, "invoke")
        and not hasattr(recovery_command, "commit")
    )
    success_snapshot = success_inputs["store_double"].snapshot()
    recovery_snapshot = interrupted_inputs["store_double"].snapshot()
    ok = bool(
        success.get("ok") is True
        and success.get("postconditions_verified") is True
        and success.get("synthetic_store_double_called") is True
        and success.get("production_store_called") is False
        and success.get("write_executed") is False
        and success.get("registry_write") is False
        and replay.get("ok") is True
        and replay["synthetic_store_result"].get("idempotent_replay") is True
        and success_snapshot["states"] == {"COMMITTED": 1}
        and interrupted.get("ok") is False
        and interrupted.get("recovery_required") is True
        and interrupted.get("synthetic_store_double_called") is True
        and interrupted.get("production_store_called") is False
        and recovered.get("ok") is True
        and recovered.get("status")
        == "C3_SYNTHETIC_PREPARED_TRANSACTION_RECOVERED_ABORTED_OFFLINE"
        and recovered.get("postconditions_verified") is True
        and recovered.get("recovery_required") is False
        and recovery_snapshot["states"] == {"ABORTED": 1}
        and recovery_surface_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_RAW_TRANSACTION_INVOCATION_SEAM_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_RAW_TRANSACTION_INVOCATION_SEAM_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_HARNESS_V1_VERSION,
        "success_postconditions_verified": success.get("postconditions_verified")
        is True,
        "success_idempotent_replay_verified": replay.get("ok") is True
        and replay.get("synthetic_store_result", {}).get("idempotent_replay")
        is True,
        "interruption_after_prepared_detected": interrupted.get(
            "recovery_required"
        )
        is True,
        "fresh_lease_recovery_verified": recovered.get("ok") is True,
        "recovery_terminal_state": recovered.get("synthetic_store_result", {}).get(
            "terminal_state"
        ),
        "recovery_surface_safe": recovery_surface_safe,
        "same_store_instance_recovered": bool(
            recovery_command
            and recovery_command.store_instance_sha256
            == interrupted_inputs["store_double"].instance_sha256
        ),
        "synthetic_store_double_called": True,
        "production_store_called": False,
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
        "success_store_snapshot": success_snapshot,
        "recovery_store_snapshot": recovery_snapshot,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_RAW_TRANSACTION_INVOCATION_SEAM_HARNESS_V1_VERSION",
    "build_synthetic_raw_transaction_invocation_seam_inputs_v1",
    "build_synthetic_recovery_maintenance_v1",
    "run_synthetic_raw_transaction_invocation_seam_harness_v1",
]
