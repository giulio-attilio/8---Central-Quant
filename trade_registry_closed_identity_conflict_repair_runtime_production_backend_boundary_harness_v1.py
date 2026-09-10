"""Synthetic harness for the dormant production backend boundary contract."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Any, Iterator

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_harness_v1 as envelope_harness
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-BOUNDARY-HARNESS-V1"
)

_NOW = envelope_harness._NOW


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def synthetic_production_backend_boundary_context_v1() -> Iterator[dict[str, Any]]:
    with envelope_harness.synthetic_production_invocation_envelope_context_v1() as values:
        envelope_result = (
            envelope_harness.project_synthetic_production_invocation_envelope_v1(
                values
            )
        )
        if envelope_result.get("ok") is not True:
            raise AssertionError("synthetic production envelope projection failed")
        envelope = envelope_result["protected_envelope"]
        production_capability_sha = _sha256_text(
            "synthetic-distinct-production-shaped-backend-capability-v1"
        )
        boundary_attestation = (
            boundary_contract.build_production_backend_boundary_attestation_offline_v1(
                envelope,
                backend_kind="DURABLE_RAW_TRANSACTION_BACKEND_V1",
                production_backend_capability_attestation_sha256=(
                    production_capability_sha
                ),
            )
        )
        recovery_ledger = (
            boundary_contract.InMemorySyntheticRecoveryAuthorizationLedgerV1()
        )
        boundary = boundary_contract.DormantProductionBackendBoundaryV1(
            config=boundary_contract.DormantProductionBackendBoundaryConfigV1(
                enabled=True,
                scope_attestation=boundary_contract.OFFLINE_PRODUCTION_BACKEND_BOUNDARY_SCOPE_ATTESTATION_V1,
            ),
            clock=lambda: _NOW,
            lease_witness=values["lease_witness"],
            recovery_authorization_ledger=recovery_ledger,
        )
        invocation_result = boundary.project_invocation_offline(
            envelope=envelope,
            backend_boundary_attestation=boundary_attestation,
            maintenance_permit=values["maintenance_permit"],
            live_lease_token=values["live_lease_token"],
        )
        if invocation_result.get("ok") is not True:
            raise AssertionError("synthetic backend boundary projection failed")
        yield {
            **values,
            "envelope_result": envelope_result,
            "production_envelope": envelope,
            "production_capability_sha256": production_capability_sha,
            "backend_boundary_attestation": boundary_attestation,
            "recovery_authorization_ledger": recovery_ledger,
            "backend_boundary": boundary,
            "invocation_result": invocation_result,
            "invocation_command": invocation_result[
                "protected_invocation_command"
            ],
        }


def build_synthetic_backend_terminal_receipt_v1(
    invocation_command: boundary_contract.ProtectedProductionBackendInvocationCommandV1,
    terminal_state: str,
) -> dict[str, Any]:
    command = invocation_command.command
    request = command["production_request"]
    state = str(terminal_state or "").upper().strip()
    ambiguous = state == "AMBIGUOUS"
    receipt = {
        "receipt_version": boundary_contract.PRODUCTION_BACKEND_TERMINAL_RECEIPT_VERSION_V1,
        "execution_scope": "SYNTHETIC_BACKEND_BOUNDARY_EVALUATION",
        "command_sha256": command["command_sha256"],
        "request_sha256": request["request_sha256"],
        "transaction_sha256": request["transaction_sha256"],
        "backend_boundary_attestation_sha256": command[
            "backend_boundary_attestation_sha256"
        ],
        "backend_instance_sha256": request["backend_instance_sha256"],
        "authorization_consumption_receipt_sha256": request[
            "authorization_consumption_receipt_sha256"
        ],
        "maintenance_epoch": request["maintenance_epoch"],
        "source_raw_document_sha256": request[
            "expected_raw_document_sha256"
        ],
        "candidate_raw_document_sha256": request[
            "candidate_raw_document_sha256"
        ],
        "terminal_state": state,
        "prepared_record_sha256": _sha256_text(
            f"synthetic-backend-{state}-prepared-record-v1"
        ),
        "terminal_record_sha256": _sha256_text(
            f"synthetic-backend-{state}-terminal-record-v1"
        ),
        "postconditions_verified": not ambiguous,
        "recovery_required": ambiguous,
        "ambiguous": ambiguous,
        "idempotent_replay": False,
        "deadline_epoch": command["deadline_epoch"],
        "deadline_observed": True,
        "production_evidence": False,
        "write_executed": False,
        "registry_write": False,
    }
    receipt["receipt_sha256"] = (
        boundary_contract.production_backend_terminal_receipt_sha256_v1(receipt)
    )
    return receipt


def build_fresh_synthetic_maintenance_permit_v1(
    label: str = "synthetic-production-backend-boundary-fresh-maintenance-epoch-v1",
) -> coordinator.WriterMaintenancePermitV1:
    return coordinator.WriterMaintenancePermitV1(
        maintenance_epoch=_sha256_text(label),
        state="QUIESCED",
        lock_namespace_sha256=coordinator.canonical_runtime_lock_namespace_v1(),
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )


def run_synthetic_production_backend_boundary_harness_v1() -> dict[str, Any]:
    with synthetic_production_backend_boundary_context_v1() as values:
        envelope = values["production_envelope"]
        invocation_command = values["invocation_command"]
        boundary = values["backend_boundary"]
        upstream_sha = invocation_command.command[
            "upstream_synthetic_capability_attestation_sha256"
        ]
        production_sha = invocation_command.command[
            "production_backend_capability_attestation_sha256"
        ]

    committed_receipt = build_synthetic_backend_terminal_receipt_v1(
        invocation_command, "COMMITTED"
    )
    committed = boundary.normalize_terminal_receipt_offline(
        envelope=envelope,
        invocation_command=invocation_command,
        terminal_receipt=committed_receipt,
    )
    ambiguous_receipt = build_synthetic_backend_terminal_receipt_v1(
        invocation_command, "AMBIGUOUS"
    )
    ambiguous = boundary.normalize_terminal_receipt_offline(
        envelope=envelope,
        invocation_command=invocation_command,
        terminal_receipt=ambiguous_receipt,
    )
    recovery_envelope = envelope_contract.build_recovery_envelope_contract_offline_v1(
        envelope,
        ambiguous["terminal_result"],
        fresh_maintenance_epoch=_sha256_text(
            "synthetic-production-backend-boundary-fresh-maintenance-epoch-v1"
        ),
        expires_at_epoch=_NOW + 20,
    )
    recovery_grant = (
        boundary_contract.build_synthetic_recovery_authorization_grant_v1(
            invocation_command,
            recovery_envelope,
            envelope,
            values["backend_boundary_attestation"],
            issued_at_epoch=_NOW - 1,
            expires_at_epoch=_NOW + 15,
        )
    )
    fresh_permit = build_fresh_synthetic_maintenance_permit_v1()
    witness = values["lease_witness"]
    with witness.hold_offline(
        fresh_permit,
        expires_at_epoch=_NOW + 20,
    ) as fresh_token:
        recovery = boundary.project_recovery_offline(
            envelope=envelope,
            invocation_command=invocation_command,
            recovery_envelope=recovery_envelope,
            ambiguous_terminal_result=ambiguous["terminal_result"],
            backend_boundary_attestation=values[
                "backend_boundary_attestation"
            ],
            fresh_maintenance_permit=fresh_permit,
            fresh_live_lease_token=fresh_token,
            recovery_authorization_grant=recovery_grant,
        )
        replay = boundary.project_recovery_offline(
            envelope=envelope,
            invocation_command=invocation_command,
            recovery_envelope=recovery_envelope,
            ambiguous_terminal_result=ambiguous["terminal_result"],
            backend_boundary_attestation=values[
                "backend_boundary_attestation"
            ],
            fresh_maintenance_permit=fresh_permit,
            fresh_live_lease_token=fresh_token,
            recovery_authorization_grant=recovery_grant,
        )

    protected_recovery = recovery.get("protected_recovery_command")
    safe_surfaces = bool(
        repr(invocation_command)
        == "ProtectedProductionBackendInvocationCommandV1(<protected>)"
        and repr(protected_recovery)
        == "ProtectedProductionBackendRecoveryCommandV1(<protected>)"
        and not hasattr(invocation_command, "invoke")
        and not hasattr(invocation_command, "apply")
        and not hasattr(protected_recovery, "reconcile")
        and not hasattr(protected_recovery, "execute")
    )
    ok = bool(
        values["invocation_result"].get("ok") is True
        and upstream_sha != production_sha
        and committed.get("ok") is True
        and committed.get("terminal_state") == "COMMITTED"
        and ambiguous.get("ok") is True
        and ambiguous.get("recovery_required") is True
        and recovery.get("ok") is True
        and recovery.get("recovery_authorization_consumed_once_synthetic") is True
        and replay.get("ok") is False
        and replay.get("reasons")
        == ["RECOVERY_AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID"]
        and values["recovery_authorization_ledger"].snapshot()["record_count"]
        == 1
        and safe_surfaces
    )
    return {
        "ok": ok,
        "status": (
            "C3_PRODUCTION_BACKEND_BOUNDARY_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_PRODUCTION_BACKEND_BOUNDARY_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_HARNESS_V1_VERSION,
        "upstream_and_production_capabilities_distinct": upstream_sha
        != production_sha,
        "invocation_command_projected": values["invocation_result"].get(
            "invocation_command_projected"
        )
        is True,
        "deadline_verified_synthetic": values["invocation_result"].get(
            "deadline_verified_synthetic"
        )
        is True,
        "committed_terminal_normalized": committed.get("ok") is True,
        "ambiguous_terminal_requires_recovery": ambiguous.get(
            "recovery_required"
        )
        is True,
        "fresh_recovery_lease_required": protected_recovery.fresh_maintenance_epoch
        != envelope.request["maintenance_epoch"],
        "recovery_authorization_consumed_once_synthetic": recovery.get(
            "recovery_authorization_consumed_once_synthetic"
        )
        is True,
        "recovery_authorization_replay_blocked": replay.get("ok") is False,
        "protected_surfaces_safe": safe_surfaces,
        "production_authority": False,
        "backend_referenced": False,
        "backend_called": False,
        "production_store_called": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_BOUNDARY_HARNESS_V1_VERSION",
    "build_fresh_synthetic_maintenance_permit_v1",
    "build_synthetic_backend_terminal_receipt_v1",
    "run_synthetic_production_backend_boundary_harness_v1",
    "synthetic_production_backend_boundary_context_v1",
]
