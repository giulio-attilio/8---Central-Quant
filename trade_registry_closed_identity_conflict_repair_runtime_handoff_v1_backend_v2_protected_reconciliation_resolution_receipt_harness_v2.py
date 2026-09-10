"""Offline harness for the protected reconciliation resolution receipt V2."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESOLUTION-RECEIPT-HARNESS-V2"
)
PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_EVIDENCE_V2"
)
_CHECK_NAMES = (
    "OPEN_OBLIGATION_RESOLVED_WITH_PROTECTED_RECEIPT",
    "FRESH_AUTHORIZATION_CONSUMED_EXACTLY_ONCE",
    "FRESH_PERMIT_TOKEN_WITNESS_OBJECTS_REQUIRED",
    "FRESH_MAINTENANCE_EPOCH_REQUIRED",
    "SAME_TRANSACTION_IDENTITY_PRESERVED",
    "TERMINAL_NON_AMBIGUOUS_PROOF_REQUIRED",
    "ORIGINAL_AUTHORITY_SUBSTITUTION_REJECTED",
    "RESEALED_AUTHORIZATION_REPLAY_REJECTED",
    "RESEALED_TRANSACTION_SUBSTITUTION_REJECTED",
    "TERMINAL_EVIDENCE_FRESH_AUTHORITY_BOUND",
    "FUTURE_RESOLUTION_TIME_REJECTED",
    "SINGLE_USE_LEDGER_REQUIRED",
    "SAME_AUTHORITY_SECOND_RESOLUTION_REJECTED",
    "LEDGER_INSTANCE_SUBSTITUTION_REJECTED",
    "SINGLE_USE_AUTHORIZATION_ISSUER_REQUIRED",
    "RECONSTRUCTED_AUTHORIZATION_RECEIPT_TRANSFER_REJECTED",
    "DIRECT_RESOLVER_BYPASS_REJECTED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "NO_APPLY_OR_RETRY_AUTHORITY_EMITTED",
    "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "obligation_sha256", "resolution_receipt_sha256",
        "fresh_authority_sha256", "transaction_sha256", "terminal_state",
        "checks", "check_count", "passed_count", "backend_called",
        "provider_called", "store_called", "writer_called", "lock_acquired",
        "registry_write", "write_executed", "filesystem_accessed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "production_authority", "runtime_integrated", "activation_allowed",
        "live_allowed", "synthetic_only", "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def _identity_sha(kind: str, value: object) -> str:
    return _sha({"kind": kind, "process_object_identity": id(value)})


def _permit_binding(permit) -> dict[str, Any]:
    return {
        "maintenance_epoch": permit.maintenance_epoch,
        "state": permit.state,
        "lock_namespace_sha256": permit.lock_namespace_sha256,
        "registered_writer_count": permit.registered_writer_count,
        "inflight_mutations": permit.inflight_mutations,
        "shared_lock_acquired": permit.shared_lock_acquired,
    }


def _authorization_receipt(obligation, issuer, now_epoch: int) -> dict[str, Any]:
    value = issuer.issue_once(
        grant_sha256=_sha(
            {"fresh-reconciliation-grant": obligation.obligation_sha256}
        ),
        obligation_sha256=obligation.obligation_sha256,
        now_epoch=now_epoch,
        expires_at_epoch=now_epoch + 90,
    )
    if value is None:
        raise ValueError("SYNTHETIC_RECONCILIATION_AUTHORIZATION_NOT_ISSUED")
    return value


def _protected_authority(
    obligation, permit, token, witness, ledger, issuer, session_anchor,
    now_epoch: int, receipt
):
    receipt = copy.deepcopy(receipt)
    permit_sha = _sha(_permit_binding(permit))
    authority = {
        "authority_version": resolution_v2.FRESH_RECONCILIATION_AUTHORITY_VERSION_V2,
        "scope_attestation": resolution_v2.OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2,
        "obligation_sha256": obligation.obligation_sha256,
        "subject_binding_sha256": obligation.obligation_sha256,
        "authorization_receipt_sha256": receipt["receipt_sha256"],
        "maintenance_epoch": permit.maintenance_epoch,
        "permit_binding_sha256": permit_sha,
        "permit_object_identity_sha256": _identity_sha("fresh_reconciliation_permit_v2", permit),
        "lease_token_sha256": token.token_sha256,
        "lease_token_object_identity_sha256": _identity_sha("fresh_reconciliation_lease_token_v2", token),
        "lease_witness_object_identity_sha256": _identity_sha("fresh_reconciliation_lease_witness_v2", witness),
        "single_use_ledger_object_identity_sha256": _identity_sha(
            "synthetic_reconciliation_resolution_ledger_v2", ledger
        ),
        "authorization_issuer_object_identity_sha256": _identity_sha(
            "synthetic_reconciliation_authorization_issuer_v2", issuer
        ),
        "process_session_anchor_object_identity_sha256": _identity_sha(
            "synthetic_reconciliation_process_session_anchor_v2", session_anchor
        ),
        "issued_at_epoch": receipt["consumed_at_epoch"],
        "expires_at_epoch": min(receipt["expires_at_epoch"], token.expires_at_epoch),
        "single_use": True,
        "fresh_from_original": True,
        "synthetic_only": True,
        "production_authority": False,
        "runtime_integrated": False,
    }
    authority["authority_sha256"] = resolution_v2.fresh_reconciliation_authority_sha256_v2(authority)
    return resolution_v2.ProtectedFreshReconciliationAuthorityV2(
        authorization_receipt=receipt,
        maintenance_permit=permit,
        live_lease_token=token,
        lease_witness=witness,
        single_use_ledger=ledger,
        authorization_issuer=issuer,
        process_session_anchor=session_anchor,
        authority=authority,
        authority_sha256=authority["authority_sha256"],
    )


def _terminal_evidence(
    obligation, authority, now_epoch: int, terminal_state: str = "COMMITTED"
):
    record = obligation.obligation
    request = obligation.adapter_plan.protected_request.request
    value = {
        "evidence_version": resolution_v2.TERMINAL_RESOLUTION_EVIDENCE_VERSION_V2,
        "obligation_sha256": obligation.obligation_sha256,
        "obligation_id_sha256": record["obligation_id_sha256"],
        "source_evidence_sha256": record["source_evidence_sha256"],
        "adapter_plan_sha256": record["adapter_plan_sha256"],
        "request_binding_sha256": record["request_binding_sha256"],
        "request_sha256": record["request_sha256"],
        "transaction_sha256": record["transaction_sha256"],
        "idempotency_key_sha256": record["idempotency_key_sha256"],
        "backend_instance_sha256": request["backend_instance_sha256"],
        "original_terminal_result_sha256": obligation.source_evidence["terminal_result_sha256"],
        "fresh_authority_sha256": authority.authority_sha256,
        "fresh_authorization_receipt_sha256": authority.authorization_receipt[
            "receipt_sha256"
        ],
        "fresh_maintenance_epoch": authority.maintenance_permit.maintenance_epoch,
        "fresh_lease_token_sha256": authority.live_lease_token.token_sha256,
        "single_use_ledger_object_identity_sha256": authority.authority[
            "single_use_ledger_object_identity_sha256"
        ],
        "observed_under_fresh_lease": True,
        "terminal_state": terminal_state,
        "reconciled_at_epoch": now_epoch,
        "same_transaction_identity_verified": True,
        "terminal_state_verified": True,
        "postconditions_verified": terminal_state != "AMBIGUOUS",
        "recovery_required": terminal_state == "AMBIGUOUS",
        "new_apply_allowed": False,
        "retry_allowed": False,
        "backend_called": False,
        "registry_write": False,
        "write_executed": False,
        "synthetic_only": True,
        "production_evidence": False,
    }
    value["evidence_sha256"] = resolution_v2.terminal_resolution_evidence_sha256_v2(value)
    return value


def _reseal_terminal(value: Mapping[str, Any], **changes) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.update(changes)
    result["evidence_sha256"] = resolution_v2.terminal_resolution_evidence_sha256_v2(result)
    return result


def _resolver(obligation, ledger=None, issuer=None, protected_restart_barrier=None):
    ledger = ledger or resolution_v2.InMemorySyntheticReconciliationResolutionLedgerV2()
    if issuer is None:
        anchor = resolution_v2.ProtectedSyntheticReconciliationProcessSessionAnchorV2(
            _sha({"implicit-harness-session": obligation.obligation_sha256})
        )
        issuer = resolution_v2.InMemorySyntheticReconciliationAuthorizationIssuerV2(
            process_session_anchor=anchor,
            resolution_ledger=ledger,
        )
    return resolution_v2.DormantProtectedReconciliationResolutionContractV2(
        resolution_v2.DormantProtectedReconciliationResolutionConfigV2(
            enabled=True,
            scope_attestation=resolution_v2.OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2,
            expected_obligation_sha256=obligation.obligation_sha256,
            expected_restart_barrier_sha256=(
                protected_restart_barrier.barrier_sha256
                if type(protected_restart_barrier)
                is barrier_v2.ProtectedReconciliationRestartBarrierV2
                else None
            ),
        ),
        single_use_ledger=ledger,
        authorization_issuer=issuer,
        protected_restart_barrier=protected_restart_barrier,
    )


def _restart_barrier(obligation, authority, now_epoch: int):
    issuer = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2(
        barrier_v2.DormantProtectedReconciliationRestartBarrierConfigV2(
            enabled=True,
            scope_attestation=barrier_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
            expected_obligation_sha256=obligation.obligation_sha256,
            expected_reference_authority_sha256=authority.authority_sha256,
        )
    )
    result = issuer.issue_offline(obligation, authority, now_epoch=now_epoch)
    protected = result.get("protected_barrier")
    if result.get("ok") is not True or protected is None:
        raise ValueError("SYNTHETIC_PROTECTED_RESTART_BARRIER_NOT_ISSUED")
    return protected


def protected_reconciliation_resolution_receipt_harness_evidence_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return _sha({key: item for key, item in value.items() if key != "evidence_sha256"})


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationResolutionReceiptHarnessEvidenceV2:
    protected_receipt: resolution_v2.ProtectedReconciliationResolutionReceiptV2 = field(repr=False)
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationResolutionReceiptHarnessEvidenceV2(<protected>)"


def protected_reconciliation_resolution_receipt_harness_evidence_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedReconciliationResolutionReceiptHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    receipt = value.protected_receipt
    try:
        return bool(
            resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(receipt)
            and evidence["evidence_version"]
            == PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_EVIDENCE_VERSION_V2
            and evidence["obligation_sha256"] == receipt.obligation.obligation_sha256
            and evidence["resolution_receipt_sha256"] == receipt.receipt_sha256
            and evidence["fresh_authority_sha256"] == receipt.fresh_authority.authority_sha256
            and evidence["transaction_sha256"] == receipt.receipt["transaction_sha256"]
            and evidence["terminal_state"] == receipt.receipt["terminal_state"]
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(type(item) is dict and set(item) == _CHECK_KEYS and item["passed"] is True for item in checks)
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and all(
                evidence[key] is False
                for key in (
                    "backend_called", "provider_called", "store_called", "writer_called",
                    "lock_acquired", "registry_write", "write_executed", "filesystem_accessed",
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "production_authority", "runtime_integrated", "activation_allowed", "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_reconciliation_resolution_receipt_harness_evidence_sha256_v2(evidence),
            )
        )
    except Exception:
        return False


def run_protected_reconciliation_resolution_receipt_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_V2_VERSION,
        "protected_receipt": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "registry_write": False,
        "write_executed": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        permit = coordinator_v1.WriterMaintenancePermitV1(
            maintenance_epoch=_sha({"fresh-maintenance-epoch": obligation.obligation_sha256}),
            state="QUIESCED",
            lock_namespace_sha256=coordinator_v1.canonical_runtime_lock_namespace_v1(),
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
        )
        witness = consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1(
            clock=lambda: now_epoch,
            nonce_source=lambda: "fresh-reconciliation-resolution-harness-v2",
        )
        ledger = resolution_v2.InMemorySyntheticReconciliationResolutionLedgerV2()
        session_anchor = (
            resolution_v2.ProtectedSyntheticReconciliationProcessSessionAnchorV2(
                _sha({"resolution-session-anchor": obligation.obligation_sha256})
            )
        )
        issuer = resolution_v2.InMemorySyntheticReconciliationAuthorizationIssuerV2(
            process_session_anchor=session_anchor,
            resolution_ledger=ledger,
        )
        authorization_receipt = _authorization_receipt(
            obligation, issuer, now_epoch
        )
        default_off = resolution_v2.DormantProtectedReconciliationResolutionContractV2().resolve_offline(
            None, None, None, now_epoch=0
        )
        with witness.hold_offline(permit, expires_at_epoch=now_epoch + 120) as token:
            authority = _protected_authority(
                obligation, permit, token, witness, ledger, issuer,
                session_anchor, now_epoch, authorization_receipt
            )
            terminal = _terminal_evidence(obligation, authority, now_epoch)
            protected_restart_barrier = _restart_barrier(
                obligation, authority, now_epoch
            )
            barrier_kwargs = {
                "protected_restart_barrier": protected_restart_barrier,
                "session_loss_declared": False,
            }
            resolver = _resolver(
                obligation, ledger, issuer, protected_restart_barrier
            )
            direct_bypass_rejected = resolver.resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch
            )
            missing_ledger = resolution_v2.DormantProtectedReconciliationResolutionContractV2(
                resolution_v2.DormantProtectedReconciliationResolutionConfigV2(
                    enabled=True,
                    scope_attestation=resolution_v2.OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2,
                    expected_obligation_sha256=obligation.obligation_sha256,
                    expected_restart_barrier_sha256=protected_restart_barrier.barrier_sha256,
                ),
                protected_restart_barrier=protected_restart_barrier,
            ).resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )
            missing_issuer = resolution_v2.DormantProtectedReconciliationResolutionContractV2(
                resolution_v2.DormantProtectedReconciliationResolutionConfigV2(
                    enabled=True,
                    scope_attestation=resolution_v2.OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2,
                    expected_obligation_sha256=obligation.obligation_sha256,
                    expected_restart_barrier_sha256=protected_restart_barrier.barrier_sha256,
                ),
                single_use_ledger=ledger,
                protected_restart_barrier=protected_restart_barrier,
            ).resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )
            resolved = resolver.resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )
            protected_receipt = resolved.get("protected_receipt")
            second_resolution = resolver.resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )
            substituted_ledger = (
                resolution_v2.InMemorySyntheticReconciliationResolutionLedgerV2()
            )
            cross_instance_rejected = _resolver(
                obligation, substituted_ledger,
                protected_restart_barrier=protected_restart_barrier,
            ).resolve_offline(
                obligation, authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )
            transferred_anchor = (
                resolution_v2.ProtectedSyntheticReconciliationProcessSessionAnchorV2(
                    _sha("transferred-process-session-anchor")
                )
            )
            transferred_issuer = (
                resolution_v2.InMemorySyntheticReconciliationAuthorizationIssuerV2(
                    process_session_anchor=transferred_anchor,
                    resolution_ledger=substituted_ledger,
                )
            )
            transferred_authority = _protected_authority(
                obligation, permit, token, witness, substituted_ledger,
                transferred_issuer, transferred_anchor, now_epoch,
                authorization_receipt,
            )
            transferred_terminal = _terminal_evidence(
                obligation, transferred_authority, now_epoch
            )
            transferred_rejected = _resolver(
                obligation, substituted_ledger, transferred_issuer,
                protected_restart_barrier,
            ).resolve_offline(
                obligation,
                transferred_authority,
                transferred_terminal,
                now_epoch=now_epoch,
                **barrier_kwargs,
            )

            original_plan = obligation.adapter_plan
            substituted = _protected_authority(
                obligation,
                original_plan.maintenance_permit,
                original_plan.live_lease_token,
                original_plan.lease_witness,
                ledger,
                issuer,
                session_anchor,
                now_epoch,
                authorization_receipt,
            )
            original_rejected = resolver.resolve_offline(
                obligation, substituted, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )

            replayed_receipt = copy.deepcopy(authorization_receipt)
            replayed_receipt["consumption_count"] = 2
            replayed_receipt["receipt_sha256"] = resolution_v2.reconciliation_authorization_receipt_sha256_v2(replayed_receipt)
            replayed_authority = _protected_authority(
                obligation, permit, token, witness, ledger, issuer,
                session_anchor, now_epoch, replayed_receipt
            )
            replay_rejected = resolver.resolve_offline(
                obligation, replayed_authority, terminal, now_epoch=now_epoch,
                **barrier_kwargs,
            )

            transaction_substitution = _reseal_terminal(
                terminal, transaction_sha256=_sha("different-transaction")
            )
            transaction_rejected = resolver.resolve_offline(
                obligation, authority, transaction_substitution,
                now_epoch=now_epoch, **barrier_kwargs,
            )
            ambiguous_rejected = resolver.resolve_offline(
                obligation,
                authority,
                _terminal_evidence(obligation, authority, now_epoch, "AMBIGUOUS"),
                now_epoch=now_epoch,
                **barrier_kwargs,
            )
            authority_substitution = _reseal_terminal(
                terminal, fresh_authority_sha256=_sha("different-fresh-authority")
            )
            authority_binding_rejected = resolver.resolve_offline(
                obligation, authority, authority_substitution,
                now_epoch=now_epoch, **barrier_kwargs,
            )
            future_evidence = _terminal_evidence(
                obligation, authority, now_epoch + 30
            )
            future_rejected = resolver.resolve_offline(
                obligation, authority, future_evidence, now_epoch=now_epoch,
                **barrier_kwargs,
            )
        if resolved.get("ok") is not True or protected_receipt is None:
            base["reason"] = "PROTECTED_RESOLUTION_RECEIPT_NOT_ISSUED"
            return base
        receipt = protected_receipt.receipt
        checks_by_name = {
            "OPEN_OBLIGATION_RESOLVED_WITH_PROTECTED_RECEIPT": resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(protected_receipt) and receipt["resolution_state"] == "RESOLVED" and receipt["reconciliation_required"] is False,
            "FRESH_AUTHORIZATION_CONSUMED_EXACTLY_ONCE": authority.authorization_receipt["consumption_count"] == 1 and protected_receipt.single_use_consumption_receipt["consumption_count"] == 1 and ledger.snapshot()["consumed_authority_count"] == 1 and authority.authorization_receipt["receipt_sha256"] != obligation.obligation["authorization_receipt_sha256"],
            "FRESH_PERMIT_TOKEN_WITNESS_OBJECTS_REQUIRED": authority.maintenance_permit is not obligation.adapter_plan.maintenance_permit and authority.live_lease_token is not obligation.adapter_plan.live_lease_token and authority.lease_witness is not obligation.adapter_plan.lease_witness,
            "FRESH_MAINTENANCE_EPOCH_REQUIRED": authority.maintenance_permit.maintenance_epoch != obligation.adapter_plan.maintenance_permit.maintenance_epoch,
            "SAME_TRANSACTION_IDENTITY_PRESERVED": receipt["transaction_sha256"] == obligation.obligation["transaction_sha256"] == terminal["transaction_sha256"],
            "TERMINAL_NON_AMBIGUOUS_PROOF_REQUIRED": ambiguous_rejected["ok"] is False and ambiguous_rejected["reason"] == "TERMINAL_RESOLUTION_EVIDENCE_INVALID",
            "ORIGINAL_AUTHORITY_SUBSTITUTION_REJECTED": original_rejected["ok"] is False and original_rejected["reason"] == "PROTECTED_RESTART_BARRIER_REJECTED" and original_rejected["restart_barrier_reason"] == "ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN",
            "RESEALED_AUTHORIZATION_REPLAY_REJECTED": replay_rejected["ok"] is False and replay_rejected["reason"] == "PROTECTED_RESTART_BARRIER_REJECTED" and replay_rejected["restart_barrier_reason"] == "ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN",
            "RESEALED_TRANSACTION_SUBSTITUTION_REJECTED": transaction_rejected["ok"] is False and transaction_rejected["reason"] == "TERMINAL_RESOLUTION_EVIDENCE_INVALID",
            "TERMINAL_EVIDENCE_FRESH_AUTHORITY_BOUND": authority_binding_rejected["ok"] is False and authority_binding_rejected["reason"] == "TERMINAL_RESOLUTION_EVIDENCE_INVALID" and terminal["fresh_authority_sha256"] == authority.authority_sha256 and terminal["fresh_lease_token_sha256"] == authority.live_lease_token.token_sha256,
            "FUTURE_RESOLUTION_TIME_REJECTED": future_rejected["ok"] is False and future_rejected["reason"] == "TERMINAL_RESOLUTION_EVIDENCE_INVALID",
            "SINGLE_USE_LEDGER_REQUIRED": missing_ledger["ok"] is False and missing_ledger["reason"] == "SYNTHETIC_SINGLE_USE_LEDGER_REQUIRED",
            "SAME_AUTHORITY_SECOND_RESOLUTION_REJECTED": second_resolution["ok"] is False and second_resolution["reason"] == "FRESH_RECONCILIATION_AUTHORITY_ALREADY_CONSUMED",
            "LEDGER_INSTANCE_SUBSTITUTION_REJECTED": cross_instance_rejected["ok"] is False and cross_instance_rejected["reason"] == "FRESH_RECONCILIATION_AUTHORITY_INVALID" and substituted_ledger.snapshot()["consumed_authority_count"] == 0,
            "SINGLE_USE_AUTHORIZATION_ISSUER_REQUIRED": missing_issuer["ok"] is False and missing_issuer["reason"] == "SYNTHETIC_SINGLE_USE_AUTHORIZATION_ISSUER_REQUIRED",
            "RECONSTRUCTED_AUTHORIZATION_RECEIPT_TRANSFER_REJECTED": transferred_rejected["ok"] is False and transferred_rejected["reason"] == "PROTECTED_RESTART_BARRIER_REJECTED" and transferred_rejected["restart_barrier_reason"] == "ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN" and transferred_issuer.snapshot()["issued_authorization_count"] == 0,
            "DIRECT_RESOLVER_BYPASS_REJECTED": direct_bypass_rejected["ok"] is False and direct_bypass_rejected["reason"] == "PROTECTED_RESTART_BARRIER_INSTANCE_NOT_PINNED" and direct_bypass_rejected["restart_barrier_evaluation_count"] == 0,
            "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "PROTECTED_RECONCILIATION_RESOLUTION_V2_DEFAULT_OFF",
            "NO_APPLY_OR_RETRY_AUTHORITY_EMITTED": receipt["new_apply_allowed"] is False and receipt["retry_allowed"] is False and receipt["original_authorization_reused"] is False,
            "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT": all(resolved[key] is False for key in ("backend_called", "provider_called", "store_called", "writer_called", "lock_acquired", "registry_write", "write_executed", "filesystem_accessed", "real_registry_accessed", "network_accessed", "broker_called", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")),
        }
        checks = [{"name": name, "passed": checks_by_name[name] is True} for name in _CHECK_NAMES]
        if not all(item["passed"] for item in checks):
            base["reason"] = "PROTECTED_RESOLUTION_RECEIPT_ORACLE_FAILED"
            return base
        evidence = {
            "evidence_version": PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_EVIDENCE_VERSION_V2,
            "obligation_sha256": obligation.obligation_sha256,
            "resolution_receipt_sha256": protected_receipt.receipt_sha256,
            "fresh_authority_sha256": authority.authority_sha256,
            "transaction_sha256": receipt["transaction_sha256"],
            "terminal_state": receipt["terminal_state"],
            "checks": checks,
            "check_count": len(checks),
            "passed_count": sum(item["passed"] for item in checks),
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "registry_write": False,
            "write_executed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        evidence["evidence_sha256"] = protected_reconciliation_resolution_receipt_harness_evidence_sha256_v2(evidence)
        protected_evidence = ProtectedReconciliationResolutionReceiptHarnessEvidenceV2(
            protected_receipt=protected_receipt,
            evidence=copy.deepcopy(evidence),
            evidence_sha256=evidence["evidence_sha256"],
        )
        if not protected_reconciliation_resolution_receipt_harness_evidence_valid_v2(protected_evidence):
            base["reason"] = "PROTECTED_RESOLUTION_HARNESS_EVIDENCE_INTERNAL_INVALID"
            return base
    except Exception as exc:
        base["reason"] = "PROTECTED_RECONCILIATION_RESOLUTION_HARNESS_EXCEPTION"
        base["diagnostic"] = type(exc).__name__
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_PASSED_OFFLINE",
            "protected_receipt": protected_receipt,
            "protected_evidence": protected_evidence,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
        }
    )
    return base


__all__ = [
    "PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedReconciliationResolutionReceiptHarnessEvidenceV2",
    "protected_reconciliation_resolution_receipt_harness_evidence_sha256_v2",
    "protected_reconciliation_resolution_receipt_harness_evidence_valid_v2",
    "run_protected_reconciliation_resolution_receipt_harness_v2",
]
