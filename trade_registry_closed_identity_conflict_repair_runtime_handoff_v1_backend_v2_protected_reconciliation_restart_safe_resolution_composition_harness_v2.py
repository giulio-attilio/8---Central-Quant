"""Offline harness for restart-barrier-to-resolver composition V2."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2 as obligation_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2 as resolution_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2 as resolution_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_harness_v2 as barrier_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_contract_v2 as composition_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESTART-SAFE-RESOLUTION-COMPOSITION-HARNESS-V2"
)
PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EVIDENCE_V2"
)
_CHECK_NAMES = (
    "EXACT_BARRIER_PRECEDES_RESOLVER",
    "ORIGINAL_SESSION_RESOLVES_OFFLINE",
    "SESSION_LOSS_BLOCKED_BEFORE_RESOLVER",
    "FULL_REMINT_BLOCKED_BEFORE_RESOLVER",
    "SAME_GRANT_NEW_RECEIPT_REJECTED",
    "REMINTED_LEDGER_NOT_CONSUMED",
    "RECONSTRUCTED_BARRIER_INSTANCE_REJECTED",
    "DURABLE_EVIDENCE_UNSUPPORTED_BEFORE_RESOLVER",
    "ORIGINAL_LEDGER_CONSUMED_EXACTLY_ONCE",
    "SAME_AUTHORITY_REPLAY_REJECTED_BY_RESOLVER",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "NO_RESOLUTION_AUTHORITY_ESCALATION",
    "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "barrier_sha256", "obligation_sha256",
        "resolution_receipt_sha256", "reference_authority_sha256",
        "reminted_authority_sha256", "checks", "check_count", "passed_count",
        "barrier_evaluation_count", "resolver_invocation_count",
        "reminted_resolver_invocation_count", "backend_called",
        "provider_called", "store_called", "writer_called", "lock_acquired",
        "registry_write", "write_executed", "filesystem_accessed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "production_authority", "runtime_integrated", "activation_allowed",
        "live_allowed", "operational_execution", "synthetic_only",
        "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def protected_reconciliation_restart_safe_resolution_composition_harness_evidence_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return _sha({key: item for key, item in value.items() if key != "evidence_sha256"})


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2:
    protected_barrier: barrier_v2.ProtectedReconciliationRestartBarrierV2 = field(
        repr=False
    )
    protected_receipt: resolution_v2.ProtectedReconciliationResolutionReceiptV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2(<protected>)"


def protected_reconciliation_restart_safe_resolution_composition_harness_evidence_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2:
        return False
    evidence = value.evidence
    checks = evidence.get("checks") if type(evidence) is dict else None
    try:
        return bool(
            type(evidence) is dict
            and set(evidence) == _EVIDENCE_KEYS
            and barrier_v2.protected_reconciliation_restart_barrier_valid_v2(
                value.protected_barrier
            )
            and resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(
                value.protected_receipt
            )
            and evidence["evidence_version"]
            == PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EVIDENCE_VERSION_V2
            and evidence["barrier_sha256"] == value.protected_barrier.barrier_sha256
            and evidence["obligation_sha256"]
            == value.protected_barrier.obligation.obligation_sha256
            and evidence["resolution_receipt_sha256"]
            == value.protected_receipt.receipt_sha256
            and evidence["reference_authority_sha256"]
            == value.protected_barrier.reference_authority.authority_sha256
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(
                type(item) is dict
                and set(item) == _CHECK_KEYS
                and item["passed"] is True
                for item in checks
            )
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and evidence["barrier_evaluation_count"] == 2
            and evidence["resolver_invocation_count"] == 1
            and evidence["reminted_resolver_invocation_count"] == 0
            and all(
                evidence[key] is False
                for key in (
                    "backend_called", "provider_called", "store_called",
                    "writer_called", "lock_acquired", "registry_write",
                    "write_executed", "filesystem_accessed",
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed", "operational_execution",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_reconciliation_restart_safe_resolution_composition_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def run_protected_reconciliation_restart_safe_resolution_composition_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_V2_VERSION,
        "protected_barrier": None,
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
        "operational_execution": False,
        "no_order_sent": True,
    }
    try:
        upstream = obligation_harness_v2.run_protected_reconciliation_obligation_harness_v2()
        obligation = upstream.get("terminal_ambiguity_obligation")
        if upstream.get("ok") is not True or obligation is None:
            base["reason"] = "UPSTREAM_OPEN_OBLIGATION_INVALID"
            return base
        now_epoch = obligation.obligation["created_at_epoch"] + 1
        ledger1, anchor1, issuer1, permit1, witness1, receipt1 = (
            barrier_harness_v2._session_components(obligation, "composition-original", now_epoch)
        )
        ledger2, anchor2, issuer2, permit2, witness2, receipt2 = (
            barrier_harness_v2._session_components(obligation, "composition-reminted", now_epoch)
        )
        default_off = composition_v2.DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2().resolve_offline(
            None, None, None, session_loss_declared=False, now_epoch=0
        )
        with witness1.hold_offline(permit1, expires_at_epoch=now_epoch + 120) as token1:
            authority1 = resolution_harness_v2._protected_authority(
                obligation, permit1, token1, witness1, ledger1, issuer1, anchor1,
                now_epoch, receipt1,
            )
            terminal1 = resolution_harness_v2._terminal_evidence(
                obligation, authority1, now_epoch
            )
            barrier_contract = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2(
                barrier_v2.DormantProtectedReconciliationRestartBarrierConfigV2(
                    enabled=True,
                    scope_attestation=barrier_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
                    expected_obligation_sha256=obligation.obligation_sha256,
                    expected_reference_authority_sha256=authority1.authority_sha256,
                )
            )
            barrier_result = barrier_contract.issue_offline(
                obligation, authority1, now_epoch=now_epoch
            )
            protected_barrier = barrier_result.get("protected_barrier")
            if barrier_result.get("ok") is not True or protected_barrier is None:
                base["reason"] = "PROTECTED_RESTART_BARRIER_NOT_ISSUED"
                return base
            resolver = resolution_harness_v2._resolver(
                obligation, ledger1, issuer1, protected_barrier
            )
            composition = composition_v2.DormantProtectedReconciliationRestartSafeResolutionCompositionContractV2(
                composition_v2.DormantProtectedReconciliationRestartSafeResolutionCompositionConfigV2(
                    enabled=True,
                    scope_attestation=composition_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_SCOPE_ATTESTATION_V2,
                    expected_obligation_sha256=obligation.obligation_sha256,
                    expected_barrier_sha256=protected_barrier.barrier_sha256,
                    expected_reference_authority_sha256=authority1.authority_sha256,
                ),
                protected_barrier=protected_barrier,
                resolution_contract=resolver,
            )
            declared_loss = composition.resolve_offline(
                protected_barrier, authority1, terminal1,
                session_loss_declared=True, now_epoch=now_epoch,
            )
            durable_unsupported = composition.resolve_offline(
                protected_barrier, authority1, terminal1,
                session_loss_declared=True, now_epoch=now_epoch,
                durable_authority_evidence={"synthetic": "unsupported"},
            )
            reconstructed_barrier = barrier_v2.ProtectedReconciliationRestartBarrierV2(
                obligation=protected_barrier.obligation,
                reference_authority=protected_barrier.reference_authority,
                barrier=protected_barrier.barrier,
                barrier_sha256=protected_barrier.barrier_sha256,
            )
            reconstructed_rejected = composition.resolve_offline(
                reconstructed_barrier, authority1, terminal1,
                session_loss_declared=False, now_epoch=now_epoch,
            )
            with witness2.hold_offline(permit2, expires_at_epoch=now_epoch + 120) as token2:
                authority2 = resolution_harness_v2._protected_authority(
                    obligation, permit2, token2, witness2, ledger2, issuer2, anchor2,
                    now_epoch, receipt2,
                )
                terminal2 = resolution_harness_v2._terminal_evidence(
                    obligation, authority2, now_epoch
                )
                reminted_rejected = composition.resolve_offline(
                    protected_barrier, authority2, terminal2,
                    session_loss_declared=False, now_epoch=now_epoch,
                )
            original_before_success = ledger1.snapshot()["consumed_authority_count"]
            reminted_before_success = ledger2.snapshot()["consumed_authority_count"]
            resolved = composition.resolve_offline(
                protected_barrier, authority1, terminal1,
                session_loss_declared=False, now_epoch=now_epoch,
            )
            protected_receipt = resolved.get("protected_receipt")
            replay = composition.resolve_offline(
                protected_barrier, authority1, terminal1,
                session_loss_declared=False, now_epoch=now_epoch,
            )
        if resolved.get("ok") is not True or protected_receipt is None:
            base["reason"] = "RESTART_SAFE_COMPOSITION_DID_NOT_RESOLVE"
            return base
        same_grant = receipt1["grant_sha256"] == receipt2["grant_sha256"]
        distinct_receipts = receipt1["receipt_sha256"] != receipt2["receipt_sha256"]
        blocked_results = (
            declared_loss, durable_unsupported, reconstructed_rejected,
            reminted_rejected,
        )
        checks_by_name = {
            "EXACT_BARRIER_PRECEDES_RESOLVER": resolved["barrier_evaluation_count"] == 2 and resolved["resolver_invocation_count"] == 1 and resolved["original_session_continuity_confirmed"] is True,
            "ORIGINAL_SESSION_RESOLVES_OFFLINE": resolution_v2.protected_reconciliation_resolution_receipt_valid_v2(protected_receipt) and resolved["synthetic_resolution_receipt_emitted"] is True,
            "SESSION_LOSS_BLOCKED_BEFORE_RESOLVER": declared_loss["ok"] is False and declared_loss["barrier_reason"] == "RESTART_RESOLUTION_FORBIDDEN_DURABLE_AUTHORITY_REQUIRED" and declared_loss["resolver_invocation_count"] == 0,
            "FULL_REMINT_BLOCKED_BEFORE_RESOLVER": reminted_rejected["ok"] is False and reminted_rejected["barrier_reason"] == "ORIGINAL_SESSION_CONTINUITY_NOT_PROVEN" and reminted_rejected["resolver_invocation_count"] == 0,
            "SAME_GRANT_NEW_RECEIPT_REJECTED": same_grant and distinct_receipts and reminted_rejected["ok"] is False,
            "REMINTED_LEDGER_NOT_CONSUMED": reminted_before_success == 0 and ledger2.snapshot()["consumed_authority_count"] == 0,
            "RECONSTRUCTED_BARRIER_INSTANCE_REJECTED": reconstructed_rejected["ok"] is False and reconstructed_rejected["reason"] == "PROTECTED_RESTART_BARRIER_INSTANCE_NOT_PINNED" and reconstructed_rejected["barrier_evaluation_count"] == 0 and reconstructed_rejected["resolver_invocation_count"] == 0,
            "DURABLE_EVIDENCE_UNSUPPORTED_BEFORE_RESOLVER": durable_unsupported["ok"] is False and durable_unsupported["barrier_reason"] == "DURABLE_AUTHORITY_VALIDATION_NOT_IMPLEMENTED" and durable_unsupported["resolver_invocation_count"] == 0,
            "ORIGINAL_LEDGER_CONSUMED_EXACTLY_ONCE": original_before_success == 0 and ledger1.snapshot()["consumed_authority_count"] == 1,
            "SAME_AUTHORITY_REPLAY_REJECTED_BY_RESOLVER": replay["ok"] is False and replay["reason"] == "PROTECTED_RECONCILIATION_RESOLVER_REJECTED" and replay["resolver_reason"] == "FRESH_RECONCILIATION_AUTHORITY_ALREADY_CONSUMED" and replay["resolver_invocation_count"] == 1,
            "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "PROTECTED_RECONCILIATION_RESTART_SAFE_COMPOSITION_V2_DEFAULT_OFF" and default_off["resolver_invocation_count"] == 0,
            "NO_RESOLUTION_AUTHORITY_ESCALATION": all(result["resolution_authority_granted"] is False for result in (*blocked_results, resolved, replay)),
            "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT": all(all(result[key] is False for key in ("backend_called", "provider_called", "store_called", "writer_called", "lock_acquired", "registry_write", "write_executed", "filesystem_accessed", "real_registry_accessed", "network_accessed", "broker_called", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed", "operational_execution")) for result in (*blocked_results, resolved, replay)),
        }
        checks = [
            {"name": name, "passed": checks_by_name[name] is True}
            for name in _CHECK_NAMES
        ]
        if not all(item["passed"] for item in checks):
            base["reason"] = "RESTART_SAFE_COMPOSITION_ORACLE_FAILED"
            base["failed_checks"] = [item["name"] for item in checks if not item["passed"]]
            return base
        evidence = {
            "evidence_version": PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EVIDENCE_VERSION_V2,
            "barrier_sha256": protected_barrier.barrier_sha256,
            "obligation_sha256": obligation.obligation_sha256,
            "resolution_receipt_sha256": protected_receipt.receipt_sha256,
            "reference_authority_sha256": authority1.authority_sha256,
            "reminted_authority_sha256": authority2.authority_sha256,
            "checks": checks,
            "check_count": len(checks),
            "passed_count": sum(item["passed"] for item in checks),
            "barrier_evaluation_count": resolved["barrier_evaluation_count"],
            "resolver_invocation_count": resolved["resolver_invocation_count"],
            "reminted_resolver_invocation_count": reminted_rejected["resolver_invocation_count"],
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
            "operational_execution": False,
            "synthetic_only": True,
        }
        evidence["evidence_sha256"] = protected_reconciliation_restart_safe_resolution_composition_harness_evidence_sha256_v2(evidence)
        protected_evidence = ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2(
            protected_barrier=protected_barrier,
            protected_receipt=protected_receipt,
            evidence=evidence,
            evidence_sha256=evidence["evidence_sha256"],
        )
        if not protected_reconciliation_restart_safe_resolution_composition_harness_evidence_valid_v2(
            protected_evidence
        ):
            base["reason"] = "RESTART_SAFE_COMPOSITION_EVIDENCE_INTERNAL_INVALID"
            return base
    except Exception as exc:
        base["reason"] = "RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EXCEPTION"
        base["diagnostic"] = type(exc).__name__
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_PASSED_OFFLINE",
            "protected_barrier": protected_barrier,
            "protected_receipt": protected_receipt,
            "protected_evidence": protected_evidence,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
        }
    )
    return base


__all__ = [
    "PROTECTED_RECONCILIATION_RESTART_SAFE_RESOLUTION_COMPOSITION_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedReconciliationRestartSafeResolutionCompositionHarnessEvidenceV2",
    "protected_reconciliation_restart_safe_resolution_composition_harness_evidence_sha256_v2",
    "protected_reconciliation_restart_safe_resolution_composition_harness_evidence_valid_v2",
    "run_protected_reconciliation_restart_safe_resolution_composition_harness_v2",
]
