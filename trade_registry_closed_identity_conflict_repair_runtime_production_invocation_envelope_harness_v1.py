"""Synthetic harness for the production-shaped invocation envelope contract."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Any, Iterator

import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_harness_v1 as consumer_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-INVOCATION-ENVELOPE-HARNESS-V1"
)

_NOW = consumer_harness._NOW


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _build_backend_identity_attestation_v1(
    capability_sha256: str,
) -> dict[str, Any]:
    value = {
        "attestation_version": contract.BACKEND_IDENTITY_ATTESTATION_VERSION_V1,
        "backend_instance_sha256": _sha256_text(
            "synthetic-production-shaped-backend-instance-v1"
        ),
        "backend_kind": "PRODUCTION_SHAPED_CONTRACT_WITNESS_V1",
        "registry_path_binding_sha256": _sha256_text(
            "synthetic-production-registry-path-binding-v1"
        ),
        "backend_capability_attestation_sha256": capability_sha256,
        "lock_namespace_sha256": coordinator.canonical_runtime_lock_namespace_v1(),
        "storage_scope": "EXPLICIT_PRODUCTION",
        "request_schema_version": contract.PRODUCTION_REQUEST_VERSION_V1,
        "result_schema_version": contract.PRODUCTION_RESULT_VERSION_V1,
        "recovery_supported": True,
        "synthetic_only": True,
        "production_backend_referenced": False,
    }
    value["attestation_sha256"] = (
        contract.backend_identity_attestation_sha256_v1(value)
    )
    return value


def _subject_binding_v1(
    upstream: dict[str, Any],
    consumer_result: dict[str, Any],
    token,
    backend_identity: dict[str, Any],
) -> str:
    intent = consumer_result["protected_intent"]
    protected_request = upstream["adapter_result"]["protected_request"]
    request = protected_request.request
    maintenance = protected_request.maintenance_attestation
    effective_expiry = min(
        intent.expires_at_epoch,
        token.expires_at_epoch,
        int(maintenance["expires_at_epoch"]),
        _NOW + 300,
    )
    return contract._stable_sha256(
        {
            "consumer_intent_sha256": intent.intent_sha256,
            "adapter_receipt_sha256": intent.adapter_receipt_sha256,
            "upstream_raw_transaction_sha256": intent.raw_transaction_sha256,
            "handoff_transaction_id": intent.handoff_transaction_id,
            "source_raw_document_sha256": request[
                "expected_raw_document_sha256"
            ],
            "expected_generation_token": request["expected_generation_token"],
            "candidate_raw_document_sha256": request[
                "candidate_raw_document_sha256"
            ],
            "maintenance_epoch": upstream[
                "maintenance_permit"
            ].maintenance_epoch,
            "backend_identity_attestation_sha256": backend_identity[
                "attestation_sha256"
            ],
            "expires_at_epoch": effective_expiry,
        }
    )


def _build_authorization_grant_v1(subject_binding_sha256: str) -> dict[str, Any]:
    grant = {
        "grant_version": contract.AUTHORIZATION_GRANT_VERSION_V1,
        "authorized_action": contract.AUTHORIZATION_ACTION_V1,
        "subject_binding_sha256": subject_binding_sha256,
        "max_consumption_count": 1,
        "issued_at_epoch": _NOW - 1,
        "expires_at_epoch": _NOW + 30,
        "synthetic_only": True,
        "production_signature_verified": False,
        "production_authority": False,
    }
    grant["grant_sha256"] = contract.authorization_grant_sha256_v1(grant)
    return grant


@contextmanager
def synthetic_production_invocation_envelope_context_v1() -> Iterator[dict[str, Any]]:
    upstream = (
        consumer_harness.build_synthetic_handoff_raw_transaction_consumer_inputs_v1()
    )
    witness = upstream["lease_witness"]
    permit = upstream["maintenance_permit"]
    with witness.hold_offline(
        permit,
        expires_at_epoch=upstream["lease_expires_at_epoch"],
    ) as token:
        consumer_result = upstream["consumer"].consume_offline(
            adapter_result=upstream["adapter_result"],
            maintenance_permit=permit,
            live_lease_token=token,
            backend_capability_attestation=upstream[
                "backend_capability_attestation"
            ],
        )
        if consumer_result.get("ok") is not True:
            raise AssertionError("synthetic consumer projection failed closed")
        backend_identity = _build_backend_identity_attestation_v1(
            consumer_result["protected_intent"].backend_capability_attestation_sha256
        )
        subject_sha = _subject_binding_v1(
            upstream,
            consumer_result,
            token,
            backend_identity,
        )
        grant = _build_authorization_grant_v1(subject_sha)
        ledger = contract.InMemorySyntheticAuthorizationConsumptionLedgerV1()
        builder = contract.DormantProductionInvocationEnvelopeBuilderV1(
            config=contract.DormantProductionInvocationEnvelopeConfigV1(
                enabled=True,
                scope_attestation=contract.OFFLINE_PRODUCTION_INVOCATION_ENVELOPE_SCOPE_ATTESTATION_V1,
            ),
            clock=lambda: _NOW,
            lease_witness=witness,
            authorization_ledger=ledger,
        )
        yield {
            **upstream,
            "live_lease_token": token,
            "consumer_result": consumer_result,
            "backend_identity_attestation": backend_identity,
            "authorization_grant": grant,
            "authorization_ledger": ledger,
            "envelope_builder": builder,
        }


def project_synthetic_production_invocation_envelope_v1(
    values: dict[str, Any],
) -> dict[str, Any]:
    return values["envelope_builder"].project_offline(
        consumer_result=values["consumer_result"],
        adapter_result=values["adapter_result"],
        maintenance_permit=values["maintenance_permit"],
        live_lease_token=values["live_lease_token"],
        backend_identity_attestation=values["backend_identity_attestation"],
        authorization_grant=values["authorization_grant"],
    )


def build_synthetic_terminal_result_v1(
    envelope: contract.ProtectedProductionInvocationEnvelopeV1,
    terminal_state: str,
) -> dict[str, Any]:
    request = envelope.request
    state = str(terminal_state).upper().strip()
    ambiguous = state == "AMBIGUOUS"
    result = {
        "result_version": contract.PRODUCTION_RESULT_VERSION_V1,
        "execution_scope": "SYNTHETIC_CONTRACT_EVALUATION",
        "request_sha256": request["request_sha256"],
        "transaction_sha256": request["transaction_sha256"],
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
            f"synthetic-terminal-{state}-prepared-record-v1"
        ),
        "terminal_record_sha256": _sha256_text(
            f"synthetic-terminal-{state}-terminal-record-v1"
        ),
        "postconditions_verified": not ambiguous,
        "recovery_required": ambiguous,
        "ambiguous": ambiguous,
        "idempotent_replay": False,
        "production_evidence": False,
        "write_executed": False,
        "registry_write": False,
    }
    result["result_sha256"] = contract.terminal_result_sha256_v1(result)
    return result


def run_synthetic_production_invocation_envelope_harness_v1() -> dict[str, Any]:
    with synthetic_production_invocation_envelope_context_v1() as values:
        projected = project_synthetic_production_invocation_envelope_v1(values)
        replay = project_synthetic_production_invocation_envelope_v1(values)
        envelope = projected.get("protected_envelope")
        committed_result = build_synthetic_terminal_result_v1(
            envelope, "COMMITTED"
        )
        committed = contract.evaluate_terminal_result_contract_offline_v1(
            envelope, committed_result
        )
        ambiguous_result = build_synthetic_terminal_result_v1(
            envelope, "AMBIGUOUS"
        )
        ambiguous = contract.evaluate_terminal_result_contract_offline_v1(
            envelope, ambiguous_result
        )
        recovery = contract.build_recovery_envelope_contract_offline_v1(
            envelope,
            ambiguous_result,
            fresh_maintenance_epoch=_sha256_text(
                "synthetic-production-shaped-fresh-recovery-epoch-v1"
            ),
            expires_at_epoch=_NOW + 20,
        )
        ledger_snapshot = values["authorization_ledger"].snapshot()

    protected_surfaces_safe = bool(
        type(envelope) is contract.ProtectedProductionInvocationEnvelopeV1
        and repr(envelope) == "ProtectedProductionInvocationEnvelopeV1(<protected>)"
        and type(recovery) is contract.ProtectedProductionRecoveryEnvelopeV1
        and repr(recovery) == "ProtectedProductionRecoveryEnvelopeV1(<protected>)"
        and not hasattr(envelope, "apply")
        and not hasattr(envelope, "invoke")
        and not hasattr(recovery, "reconcile")
        and not hasattr(recovery, "invoke")
    )
    ok = bool(
        projected.get("ok") is True
        and projected.get("production_request_projected") is True
        and projected.get("authorization_consumed_once_synthetic") is True
        and projected.get("production_authorization_valid") is False
        and projected.get("backend_referenced") is False
        and projected.get("production_store_called") is False
        and replay.get("ok") is False
        and replay.get("reasons")
        == ["AUTHORIZATION_ALREADY_CONSUMED_OR_RECEIPT_INVALID"]
        and ledger_snapshot == {
            "record_count": 1,
            "states": {"CONSUMED": 1},
            "durable": False,
            "synthetic_only": True,
            "production_authority": False,
        }
        and committed.get("ok") is True
        and committed.get("terminal_state") == "COMMITTED"
        and committed.get("production_terminal_verified") is False
        and ambiguous.get("ok") is True
        and ambiguous.get("recovery_required") is True
        and recovery.fresh_maintenance_epoch
        != envelope.request["maintenance_epoch"]
        and recovery.request["recovery_policy"]
        == contract.PRODUCTION_RECOVERY_POLICY_V1
        and protected_surfaces_safe
    )
    return {
        "ok": ok,
        "status": (
            "C3_PRODUCTION_INVOCATION_ENVELOPE_HARNESS_PASSED_OFFLINE"
            if ok
            else "C3_PRODUCTION_INVOCATION_ENVELOPE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_HARNESS_V1_VERSION,
        "protected_surfaces_safe": protected_surfaces_safe,
        "production_request_projected": projected.get(
            "production_request_projected"
        )
        is True,
        "upstream_raw_transaction_preserved": bool(
            envelope
            and envelope.upstream_raw_transaction_sha256
            == values["consumer_result"][
                "protected_intent"
            ].raw_transaction_sha256
        ),
        "production_transaction_identity_distinct": bool(
            envelope
            and envelope.production_transaction_sha256
            != envelope.upstream_raw_transaction_sha256
        ),
        "authorization_consumed_once_synthetic": projected.get(
            "authorization_consumed_once_synthetic"
        )
        is True,
        "authorization_replay_blocked": replay.get("ok") is False,
        "terminal_contract_committed_valid": committed.get("ok") is True,
        "ambiguous_requires_recovery": ambiguous.get("recovery_required") is True,
        "fresh_recovery_epoch_required": recovery.fresh_maintenance_epoch
        != envelope.request["maintenance_epoch"],
        "production_authorization_valid": False,
        "production_terminal_verified": False,
        "backend_referenced": False,
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
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_INVOCATION_ENVELOPE_HARNESS_V1_VERSION",
    "build_synthetic_terminal_result_v1",
    "project_synthetic_production_invocation_envelope_v1",
    "run_synthetic_production_invocation_envelope_harness_v1",
    "synthetic_production_invocation_envelope_context_v1",
]
