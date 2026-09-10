"""Offline harness for the dormant protected V2 request handoff contract.

The harness materializes only a synthetic CAS witness and protected evidence.
It never materializes a V2 transaction request or request binding, and never
calls a provider, store, backend, writer, runtime seam, network, or broker.
"""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2 as materialization_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HANDOFF_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HANDOFF-HARNESS-V2"
)
PROTECTED_REQUEST_HANDOFF_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_REQUEST_HANDOFF_HARNESS_EVIDENCE_V2"
)

_CHECK_NAMES = (
    "HANDOFF_PLAN_VALID",
    "CANONICAL_TRANSACTION_IDENTITY_STABLE",
    "CANONICAL_REQUEST_IDENTITY_STABLE",
    "SAME_INSTANCE_LEASE_LIVE_SYNTHETIC",
    "TYPED_CAS_WITNESS_VALID",
    "CAS_GENERATION_AND_RAW_HASH_BOUND",
    "CAS_CAPTURE_BOUND_TO_SAME_HELD_LOCK",
    "AUTHORIZATION_SIDECAR_REQUIRED",
    "NON_REENTRANT_PORT_REQUIRED",
    "EXECUTABLE_REQUEST_NOT_MATERIALIZED",
    "STALE_GENERATION_REJECTED",
    "SUBSTITUTED_PERMIT_REJECTED",
    "SECOND_LOCK_ACQUISITION_REJECTED",
    "EXPIRED_WITNESS_REJECTED",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "handoff_plan_sha256", "materialization_intent_sha256",
        "cas_witness_sha256", "expected_transaction_sha256",
        "expected_request_sha256", "checks", "check_count", "passed_count",
        "synthetic_lease_liveness_validation_count", "cas_witness_materialized",
        "executable_request_materialized", "request_binding_materialized",
        "authorization_consumed", "provider_called", "store_called",
        "backend_called", "writer_called", "lock_acquired_by_harness",
        "filesystem_accessed_by_handoff", "real_registry_accessed",
        "network_accessed", "broker_called", "write_executed",
        "production_authority", "runtime_integrated", "activation_allowed",
        "live_allowed", "synthetic_only", "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def protected_request_handoff_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _sha(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


def build_synthetic_target_cas_witness_offline_v2(
    protected_intent,
    bridge_plan,
    compatibility_bundle,
    *,
    observed_at_epoch: int,
) -> handoff_v2.ProtectedTargetCasWitnessV2:
    """Build a synthetic witness after an explicit same-instance live check."""

    if not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
        protected_intent, bridge_plan, compatibility_bundle
    ):
        raise ValueError("VALID_PROTECTED_MATERIALIZATION_INTENT_REQUIRED")
    if type(observed_at_epoch) is not int:
        raise ValueError("INTEGER_OBSERVED_AT_EPOCH_REQUIRED")
    permit = protected_intent.maintenance_permit
    token = protected_intent.live_lease_token
    witness_authority = protected_intent.lease_witness
    if not witness_authority.validate_live(
        permit, token, now_epoch=observed_at_epoch
    ):
        raise ValueError("SAME_INSTANCE_LIVE_LEASE_REQUIRED")
    intent = protected_intent.intent
    target = intent["target_binding"]
    candidate = intent["candidate_binding"]
    lease = intent["lease_instance_binding"]
    deadline = intent["deadline_binding"]
    if not observed_at_epoch < deadline["effective_deadline_epoch"]:
        raise ValueError("CAS_WITNESS_DEADLINE_EXPIRED")
    value = {
        "witness_version": handoff_v2.TARGET_CAS_WITNESS_VERSION_V2,
        "materialization_intent_sha256": protected_intent.intent_sha256,
        "target_backend_instance_sha256": target["target_backend_instance_sha256"],
        "target_snapshot_sha256": target["target_snapshot_sha256"],
        "registry_path_binding_sha256": target[
            "target_registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": target["target_lock_namespace_sha256"],
        "observed_generation": target["target_generation"],
        "observed_raw_document_sha256": candidate["source_raw_document_sha256"],
        "maintenance_epoch": lease["maintenance_epoch"],
        "permit_object_identity_sha256": lease["permit_object_identity_sha256"],
        "lease_token_sha256": lease["lease_token_sha256"],
        "lease_token_object_identity_sha256": lease[
            "lease_token_object_identity_sha256"
        ],
        "lease_witness_object_identity_sha256": lease[
            "lease_witness_object_identity_sha256"
        ],
        "observed_at_epoch": observed_at_epoch,
        "lease_expires_at_epoch": token.expires_at_epoch,
        "snapshot_collected_under_same_lock": True,
        "raw_document_loaded_under_same_lock": True,
        "lease_liveness_validated_at_capture": True,
        "lock_already_held": True,
        "lock_acquisition_count": 1,
        "synthetic_only": True,
        "production_authority": False,
    }
    value["witness_sha256"] = handoff_v2.target_cas_witness_sha256_v2(value)
    protected = handoff_v2.ProtectedTargetCasWitnessV2(
        maintenance_permit=permit,
        live_lease_token=token,
        lease_witness=witness_authority,
        witness=copy.deepcopy(value),
        witness_sha256=value["witness_sha256"],
    )
    if not handoff_v2.protected_target_cas_witness_valid_v2(
        protected, protected_intent, bridge_plan, compatibility_bundle
    ):
        raise ValueError("SYNTHETIC_TARGET_CAS_WITNESS_INTERNAL_INVALID")
    return protected


@dataclass(frozen=True, repr=False)
class ProtectedRequestHandoffHarnessEvidenceV2:
    handoff_plan: handoff_v2.ProtectedRequestHandoffPlanV2 = field(repr=False)
    cas_witness: handoff_v2.ProtectedTargetCasWitnessV2 = field(repr=False)
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedRequestHandoffHarnessEvidenceV2(<protected>)"


def protected_request_handoff_harness_evidence_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedRequestHandoffHarnessEvidenceV2:
        return False
    plan = value.handoff_plan
    evidence = value.evidence
    if (
        not handoff_v2.protected_request_handoff_plan_valid_v2(plan)
        or type(evidence) is not dict
        or set(evidence) != _EVIDENCE_KEYS
    ):
        return False
    checks = evidence.get("checks")
    try:
        return bool(
            handoff_v2.protected_target_cas_witness_valid_v2(
                value.cas_witness,
                plan.materialization_intent,
                plan.bridge_plan,
                plan.compatibility_bundle,
            )
            and evidence["evidence_version"]
            == PROTECTED_REQUEST_HANDOFF_HARNESS_EVIDENCE_VERSION_V2
            and evidence["handoff_plan_sha256"] == plan.plan_sha256
            and evidence["materialization_intent_sha256"]
            == plan.materialization_intent.intent_sha256
            and evidence["cas_witness_sha256"] == value.cas_witness.witness_sha256
            and evidence["expected_transaction_sha256"]
            == plan.plan["identity_policy"]["expected_transaction_sha256"]
            and evidence["expected_request_sha256"]
            == plan.plan["identity_policy"]["expected_request_sha256"]
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
            and evidence["synthetic_lease_liveness_validation_count"] == 1
            and evidence["cas_witness_materialized"] is True
            and all(
                evidence[key] is False
                for key in (
                    "executable_request_materialized", "request_binding_materialized",
                    "authorization_consumed", "provider_called", "store_called",
                    "backend_called", "writer_called", "lock_acquired_by_harness",
                    "filesystem_accessed_by_handoff", "real_registry_accessed",
                    "network_accessed", "broker_called", "write_executed",
                    "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_request_handoff_harness_evidence_sha256_v2(evidence),
            )
        )
    except Exception:
        return False


def _tampered_cas_witness(
    protected: handoff_v2.ProtectedTargetCasWitnessV2,
    *,
    witness: Mapping[str, Any] | None = None,
    maintenance_permit: Any = None,
) -> handoff_v2.ProtectedTargetCasWitnessV2:
    supplied_witness = protected.witness if witness is None else witness
    return handoff_v2.ProtectedTargetCasWitnessV2(
        maintenance_permit=(
            protected.maintenance_permit
            if maintenance_permit is None
            else maintenance_permit
        ),
        live_lease_token=protected.live_lease_token,
        lease_witness=protected.lease_witness,
        witness=supplied_witness,
        witness_sha256=(
            protected.witness_sha256
            if witness is None
            else supplied_witness["witness_sha256"]
        ),
    )


def run_protected_request_handoff_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_REQUEST_HANDOFF_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HANDOFF_HARNESS_V2_VERSION,
        "protected_plan": None,
        "protected_cas_witness": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "synthetic_lease_liveness_validation_count": 0,
        "cas_witness_materialized": False,
        "executable_request_materialized": False,
        "request_binding_materialized": False,
        "authorization_consumed": False,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "lock_acquired_by_harness": False,
        "filesystem_accessed_by_handoff": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        with materialization_harness.held_protected_dto_materialization_fixture_v2() as fixture:
            materialization = materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                fixture
            )
            protected_intent = materialization.get("protected_intent")
            if materialization.get("ok") is not True or protected_intent is None:
                base["reason"] = "UPSTREAM_MATERIALIZATION_INTENT_INVALID"
                return base
            planner = handoff_v2.DormantProtectedRequestHandoffContractV2(
                handoff_v2.DormantProtectedRequestHandoffConfigV2(
                    enabled=True,
                    scope_attestation=handoff_v2.OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2,
                    expected_materialization_intent_sha256=protected_intent.intent_sha256,
                )
            )
            plan_result = planner.plan_offline(
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            plan = plan_result.get("protected_plan")
            if plan_result.get("ok") is not True or plan is None:
                base["reason"] = "PROTECTED_HANDOFF_PLAN_INVALID"
                return base
            cas_witness = build_synthetic_target_cas_witness_offline_v2(
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
                observed_at_epoch=fixture["now_epoch"],
            )
            cas = cas_witness.witness
            identity = plan.plan["identity_policy"]
            envelope_contract = plan.plan["protected_request_envelope_contract"]
            port = plan.plan["held_lease_backend_port_contract"]

            stale = copy.deepcopy(dict(cas))
            stale["observed_generation"] += 1
            stale["witness_sha256"] = handoff_v2.target_cas_witness_sha256_v2(stale)
            stale_rejected = not handoff_v2.protected_target_cas_witness_valid_v2(
                _tampered_cas_witness(cas_witness, witness=stale),
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            substituted_permit_rejected = not handoff_v2.protected_target_cas_witness_valid_v2(
                _tampered_cas_witness(
                    cas_witness,
                    maintenance_permit=copy.copy(cas_witness.maintenance_permit),
                ),
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            second_lock = copy.deepcopy(dict(cas))
            second_lock["lock_acquisition_count"] = 2
            second_lock["witness_sha256"] = handoff_v2.target_cas_witness_sha256_v2(
                second_lock
            )
            second_lock_rejected = not handoff_v2.protected_target_cas_witness_valid_v2(
                _tampered_cas_witness(cas_witness, witness=second_lock),
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            expired = copy.deepcopy(dict(cas))
            expired["observed_at_epoch"] = protected_intent.intent[
                "deadline_binding"
            ]["effective_deadline_epoch"]
            expired["witness_sha256"] = handoff_v2.target_cas_witness_sha256_v2(
                expired
            )
            expired_rejected = not handoff_v2.protected_target_cas_witness_valid_v2(
                _tampered_cas_witness(cas_witness, witness=expired),
                protected_intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            checks_by_name = {
                "HANDOFF_PLAN_VALID": handoff_v2.protected_request_handoff_plan_valid_v2(plan),
                "CANONICAL_TRANSACTION_IDENTITY_STABLE": identity["expected_transaction_sha256"] == handoff_v2.canonical_transaction_sha256_v2(protected_intent, fixture["bridge_plan"], fixture["compatibility_bundle"]),
                "CANONICAL_REQUEST_IDENTITY_STABLE": identity["expected_request_sha256"] == handoff_v2.canonical_request_sha256_v2(protected_intent, fixture["bridge_plan"], fixture["compatibility_bundle"]),
                "SAME_INSTANCE_LEASE_LIVE_SYNTHETIC": cas["lease_liveness_validated_at_capture"] is True and cas_witness.maintenance_permit is protected_intent.maintenance_permit and cas_witness.live_lease_token is protected_intent.live_lease_token and cas_witness.lease_witness is protected_intent.lease_witness,
                "TYPED_CAS_WITNESS_VALID": handoff_v2.protected_target_cas_witness_valid_v2(cas_witness, protected_intent, fixture["bridge_plan"], fixture["compatibility_bundle"]),
                "CAS_GENERATION_AND_RAW_HASH_BOUND": cas["observed_generation"] == protected_intent.intent["target_binding"]["target_generation"] and cas["observed_raw_document_sha256"] == protected_intent.intent["candidate_binding"]["source_raw_document_sha256"],
                "CAS_CAPTURE_BOUND_TO_SAME_HELD_LOCK": cas["snapshot_collected_under_same_lock"] is True and cas["raw_document_loaded_under_same_lock"] is True and cas["lock_already_held"] is True and cas["lock_acquisition_count"] == 1,
                "AUTHORIZATION_SIDECAR_REQUIRED": envelope_contract["authorization_receipt_sidecar_required"] is True and envelope_contract["raw_mapping_delivery_forbidden"] is True and envelope_contract["bare_v2_request_authority"] is False,
                "NON_REENTRANT_PORT_REQUIRED": port["required_method"] == handoff_v2.HELD_LEASE_BACKEND_PORT_METHOD_V2 and port["backend_reacquire_allowed"] is False and port["legacy_self_locking_method_forbidden"] == "apply_attested_transaction_offline",
                "EXECUTABLE_REQUEST_NOT_MATERIALIZED": plan.plan["request_materialized"] is False and plan.plan["request_binding_materialized"] is False,
                "STALE_GENERATION_REJECTED": stale_rejected,
                "SUBSTITUTED_PERMIT_REJECTED": substituted_permit_rejected,
                "SECOND_LOCK_ACQUISITION_REJECTED": second_lock_rejected,
                "EXPIRED_WITNESS_REJECTED": expired_rejected,
            }
            checks = [
                {"name": name, "passed": checks_by_name[name] is True}
                for name in _CHECK_NAMES
            ]
            if not all(item["passed"] for item in checks):
                base["reason"] = "PROTECTED_REQUEST_HANDOFF_ORACLE_FAILED"
                return base
            evidence = {
                "evidence_version": PROTECTED_REQUEST_HANDOFF_HARNESS_EVIDENCE_VERSION_V2,
                "handoff_plan_sha256": plan.plan_sha256,
                "materialization_intent_sha256": protected_intent.intent_sha256,
                "cas_witness_sha256": cas_witness.witness_sha256,
                "expected_transaction_sha256": identity[
                    "expected_transaction_sha256"
                ],
                "expected_request_sha256": identity["expected_request_sha256"],
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "synthetic_lease_liveness_validation_count": 1,
                "cas_witness_materialized": True,
                "executable_request_materialized": False,
                "request_binding_materialized": False,
                "authorization_consumed": False,
                "provider_called": False,
                "store_called": False,
                "backend_called": False,
                "writer_called": False,
                "lock_acquired_by_harness": False,
                "filesystem_accessed_by_handoff": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "write_executed": False,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "synthetic_only": True,
            }
            evidence["evidence_sha256"] = (
                protected_request_handoff_harness_evidence_sha256_v2(evidence)
            )
            protected_evidence = ProtectedRequestHandoffHarnessEvidenceV2(
                handoff_plan=plan,
                cas_witness=cas_witness,
                evidence=copy.deepcopy(evidence),
                evidence_sha256=evidence["evidence_sha256"],
            )
            if not protected_request_handoff_harness_evidence_valid_v2(
                protected_evidence
            ):
                base["reason"] = "PROTECTED_REQUEST_HANDOFF_EVIDENCE_INTERNAL_INVALID"
                return base
    except Exception:
        base["reason"] = "PROTECTED_REQUEST_HANDOFF_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_REQUEST_HANDOFF_HARNESS_V2_PASSED_OFFLINE",
            "protected_plan": plan,
            "protected_cas_witness": cas_witness,
            "protected_evidence": protected_evidence,
            "plan_sha256": plan.plan_sha256,
            "cas_witness_sha256": cas_witness.witness_sha256,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
            "synthetic_lease_liveness_validation_count": 1,
            "cas_witness_materialized": True,
        }
    )
    return base


__all__ = [
    "ProtectedRequestHandoffHarnessEvidenceV2",
    "build_synthetic_target_cas_witness_offline_v2",
    "protected_request_handoff_harness_evidence_sha256_v2",
    "protected_request_handoff_harness_evidence_valid_v2",
    "run_protected_request_handoff_harness_v2",
]
