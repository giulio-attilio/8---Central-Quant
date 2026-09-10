"""Synthetic restart harness for the offline durable handoff contract."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_harness_v1 as gateway_harness
import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1 as gateway_module
import trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1 as handoff_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-DURABLE-HANDOFF-HARNESS-V1"
)

_NOW = gateway_harness._NOW


def build_synthetic_durable_handoff_inputs_v1(
    repository_root: object | None = None,
) -> dict[str, Any]:
    gateway_inputs = gateway_harness.build_synthetic_dormant_invocation_gateway_inputs_v1(
        repository_root
    )
    gateway = gateway_harness.build_synthetic_dormant_invocation_gateway_v1()
    gateway_result = gateway.prepare(**gateway_inputs)
    if gateway_result.get("ok") is not True:
        raise AssertionError("synthetic dormant gateway failed closed")
    authorization_result = gateway_inputs["authorization_result"]
    authorization_receipt = authorization_result["authorization_receipt"]
    gateway_receipt = gateway_result["gateway_receipt"]
    envelope = gateway_result["protected_envelope"]
    intent = {
        "intent_version": handoff_module.HANDOFF_INTENT_VERSION_V1,
        "gateway_receipt_sha256": gateway_receipt["gateway_receipt_sha256"],
        "authorization_receipt_sha256": authorization_receipt[
            "authorization_receipt_sha256"
        ],
        "preview_receipt_sha256": envelope.preview_receipt_sha256,
        "controller_instance_sha256": envelope.controller_instance_sha256,
        "source_registry_sha256": authorization_receipt[
            "source_registry_sha256"
        ],
        "candidate_registry_sha256": authorization_receipt[
            "candidate_registry_sha256"
        ],
        "changed_paths_sha256": authorization_receipt["changed_paths_sha256"],
        "terminal_policy": "EXPLICIT_SYNTHETIC_COMMIT_OR_ABORT_ONLY",
        "controller_call_requested": False,
        "registry_write_requested": False,
        "runtime_binding_requested": False,
        "max_terminal_transition_count": 1,
    }
    intent["intent_sha256"] = handoff_module.durable_handoff_intent_sha256_v1(
        intent
    )
    return {
        "gateway_result": gateway_result,
        "authorization_result": authorization_result,
        "handoff_intent": intent,
    }


def build_synthetic_durable_handoff_v1(
    *,
    wal: handoff_module.InMemoryHashChainedHandoffWalV1 | None = None,
    clock=None,
) -> handoff_module.DurableHandoffOfflineV1:
    return handoff_module.DurableHandoffOfflineV1(
        config=handoff_module.DurableHandoffConfigV1(
            enabled=True,
            scope_attestation=handoff_module.OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1,
        ),
        clock=clock if clock is not None else lambda: _NOW,
        wal=(
            wal
            if wal is not None
            else handoff_module.InMemoryHashChainedHandoffWalV1()
        ),
    )


def build_synthetic_terminal_attestation_v1(
    command: handoff_module.ProtectedDurableHandoffCommandV1,
    terminal_state: str,
    *,
    event_epoch: int = _NOW,
) -> dict[str, Any]:
    attestation = {
        "attestation_version": handoff_module.TERMINAL_ATTESTATION_VERSION_V1,
        "transaction_id": command.transaction_id,
        "handoff_binding_sha256": command.handoff_binding_sha256,
        "terminal_state": str(terminal_state).upper().strip(),
        "event_epoch": event_epoch,
        "synthetic_only": True,
        "production_evidence": False,
        "controller_invoked": False,
        "registry_write": False,
    }
    attestation["attestation_sha256"] = (
        handoff_module.synthetic_terminal_attestation_sha256_v1(attestation)
    )
    return attestation


def run_synthetic_durable_handoff_restart_harness_v1(
    repository_root: object | None = None,
) -> dict[str, Any]:
    inputs = build_synthetic_durable_handoff_inputs_v1(repository_root)

    commit_wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    commit_handoff = build_synthetic_durable_handoff_v1(wal=commit_wal)
    prepared_commit = commit_handoff.prepare(**inputs)
    commit_command = prepared_commit.get("protected_command")
    committed = commit_handoff.finalize_offline(
        commit_command,
        build_synthetic_terminal_attestation_v1(commit_command, "COMMITTED"),
    )
    committed_snapshot = commit_wal.export_restart_snapshot()
    restarted_commit_wal = handoff_module.InMemoryHashChainedHandoffWalV1(
        committed_snapshot
    )
    restarted_commit = build_synthetic_durable_handoff_v1(
        wal=restarted_commit_wal
    )
    recovered_commit = restarted_commit.recover_offline(commit_command)
    replayed_commit = restarted_commit.prepare(**inputs)

    abort_wal = handoff_module.InMemoryHashChainedHandoffWalV1()
    abort_handoff = build_synthetic_durable_handoff_v1(wal=abort_wal)
    prepared_abort = abort_handoff.prepare(**inputs)
    abort_command = prepared_abort.get("protected_command")
    prepared_snapshot = abort_wal.export_restart_snapshot()
    restarted_prepared_wal = handoff_module.InMemoryHashChainedHandoffWalV1(
        prepared_snapshot
    )
    restarted_prepared = build_synthetic_durable_handoff_v1(
        wal=restarted_prepared_wal
    )
    recovered_prepared = restarted_prepared.recover_offline(abort_command)
    aborted = restarted_prepared.finalize_offline(
        abort_command,
        build_synthetic_terminal_attestation_v1(abort_command, "ABORTED"),
    )
    aborted_snapshot = restarted_prepared_wal.export_restart_snapshot()
    restarted_abort_wal = handoff_module.InMemoryHashChainedHandoffWalV1(
        aborted_snapshot
    )
    recovered_abort = build_synthetic_durable_handoff_v1(
        wal=restarted_abort_wal
    ).recover_offline(abort_command)

    protected_surface_safe = bool(
        type(commit_command) is handoff_module.ProtectedDurableHandoffCommandV1
        and repr(commit_command) == "ProtectedDurableHandoffCommandV1(<protected>)"
        and not hasattr(commit_command, "serialize")
        and not hasattr(commit_command, "to_payload")
        and not hasattr(commit_command, "apply")
        and not hasattr(commit_command, "invoke")
        and not hasattr(commit_command, "commit")
    )
    ok = bool(
        prepared_commit.get("ok") is True
        and prepared_commit.get("wal_prepared") is True
        and committed.get("ok") is True
        and committed.get("terminal_state") == "COMMITTED"
        and committed.get("production_commit_verified") is False
        and recovered_commit.get("ok") is True
        and recovered_commit.get("state") == "COMMITTED"
        and replayed_commit.get("ok") is True
        and replayed_commit.get("idempotent_replay") is True
        and replayed_commit.get("protected_command") is None
        and recovered_prepared.get("ok") is True
        and recovered_prepared.get("state") == "PREPARED"
        and aborted.get("ok") is True
        and aborted.get("terminal_state") == "ABORTED"
        and recovered_abort.get("ok") is True
        and recovered_abort.get("state") == "ABORTED"
        and protected_surface_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_DURABLE_HANDOFF_RESTART_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_DURABLE_HANDOFF_RESTART_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_HARNESS_V1_VERSION,
        "protected_surface_safe": protected_surface_safe,
        "commit_recovered_after_restart": recovered_commit.get("state")
        == "COMMITTED",
        "commit_replay_idempotent": replayed_commit.get("idempotent_replay") is True,
        "prepared_recovered_after_restart": recovered_prepared.get("state")
        == "PREPARED",
        "abort_recovered_after_restart": recovered_abort.get("state") == "ABORTED",
        "wal_hash_chain_verified": (
            restarted_commit_wal.snapshot()["hash_chain_verified"] is True
            and restarted_abort_wal.snapshot()["hash_chain_verified"] is True
        ),
        "restart_recovery_rehearsed": True,
        "production_durability_verified": False,
        "controller_invocation_allowed": False,
        "registry_write_allowed": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "committed_wal_snapshot": restarted_commit_wal.snapshot(),
        "aborted_wal_snapshot": restarted_abort_wal.snapshot(),
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_HARNESS_V1_VERSION",
    "build_synthetic_durable_handoff_inputs_v1",
    "build_synthetic_durable_handoff_v1",
    "build_synthetic_terminal_attestation_v1",
    "run_synthetic_durable_handoff_restart_harness_v1",
]
