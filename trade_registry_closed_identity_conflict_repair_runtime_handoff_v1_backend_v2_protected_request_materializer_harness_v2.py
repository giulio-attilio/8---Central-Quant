"""Offline harness for the protected V2 transaction-request materializer.

The harness derives an independent synthetic oracle, exercises fail-closed
tamper cases and retains only protected artifacts. It never calls a provider,
store, backend, writer, runtime seam, network endpoint, broker, or real Registry.
"""

from __future__ import annotations

import copy
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as handoff_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_MATERIALIZER_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-MATERIALIZER-HARNESS-V2"
)
PROTECTED_REQUEST_MATERIALIZER_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_REQUEST_MATERIALIZER_HARNESS_EVIDENCE_V2"
)

_CHECK_NAMES = (
    "PROTECTED_MATERIALIZED_REQUEST_VALID",
    "INDEPENDENT_REQUEST_ORACLE_EXACT_MATCH",
    "CANONICAL_CANDIDATE_BYTES_AND_HASH_EXACT",
    "CANONICALIZATION_OCCURRED_EXACTLY_ONCE",
    "LEASE_REVALIDATED_AT_SEALING_EXACTLY_ONCE",
    "SAME_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED",
    "CAS_GENERATION_AND_RAW_HASH_EXACT",
    "AUTHORIZATION_AND_DEADLINE_REVALIDATED",
    "ONLY_PROTECTED_WRAPPER_DELIVERED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "STALE_CAS_WITNESS_REJECTED",
    "SUBSTITUTED_PERMIT_INSTANCE_REJECTED",
    "RESEALED_GENERATION_TAMPER_REJECTED",
    "RESEALED_CANDIDATE_TAMPER_REJECTED",
    "RESEALED_ARBITRARY_IDENTITY_REJECTED",
    "NO_EXECUTION_SURFACE_OR_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "handoff_plan_sha256",
        "cas_witness_sha256",
        "materialized_request_envelope_sha256",
        "request_binding_sha256",
        "independent_oracle_sha256",
        "checks",
        "check_count",
        "passed_count",
        "canonicalization_count",
        "lease_revalidation_count",
        "request_materialized",
        "request_binding_materialized",
        "bare_request_exposed",
        "authorization_consumed",
        "provider_called",
        "store_called",
        "backend_called",
        "writer_called",
        "lock_acquired",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def protected_request_materializer_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _sha(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


def _canonical_candidate(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _independent_request_oracle(plan, cas_witness) -> dict[str, Any]:
    intent = plan.materialization_intent
    intent_data = intent.intent
    identity = plan.plan["identity_policy"]
    target = intent_data["target_binding"]
    candidate = intent_data["candidate_binding"]
    lease = intent_data["lease_instance_binding"]
    authorization = intent_data["authorization_binding"]
    canonical_candidate = _canonical_candidate(
        intent.source_envelope.request["candidate_registry"]
    )
    request = {
        "request_version": backend_v2.TRANSACTION_REQUEST_VERSION_V2,
        "backend_instance_sha256": target["target_backend_instance_sha256"],
        "backend_snapshot_sha256": target["target_snapshot_sha256"],
        "registry_path_binding_sha256": target[
            "target_registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": target["target_lock_namespace_sha256"],
        "request_sha256": identity["expected_request_sha256"],
        "transaction_sha256": identity["expected_transaction_sha256"],
        "idempotency_key": candidate["idempotency_key"],
        "authorization_receipt_sha256": authorization[
            "authorization_consumption_receipt_sha256"
        ],
        "maintenance_epoch": lease["maintenance_epoch"],
        "expected_generation": cas_witness.witness["observed_generation"],
        "expected_raw_document_sha256": cas_witness.witness[
            "observed_raw_document_sha256"
        ],
        "candidate_raw_document_utf8": canonical_candidate,
        "candidate_raw_document_sha256": backend_v2.raw_utf8_sha256_v2(
            canonical_candidate
        ),
        "deadline_epoch": intent_data["deadline_binding"][
            "effective_deadline_epoch"
        ],
        "synthetic_only": True,
        "production_authority": False,
    }
    request["request_binding_sha256"] = _sha(request)
    return request


def _resealed_wrapper(protected, request):
    request = copy.deepcopy(dict(request))
    request["request_binding_sha256"] = _sha(
        {
            key: item
            for key, item in request.items()
            if key != "request_binding_sha256"
        }
    )
    envelope = copy.deepcopy(dict(protected.envelope))
    envelope["request_binding_sha256"] = request["request_binding_sha256"]
    envelope["request_sha256"] = request["request_sha256"]
    envelope["transaction_sha256"] = request["transaction_sha256"]
    envelope["envelope_sha256"] = (
        materializer_v2.protected_materialized_request_envelope_sha256_v2(
            envelope
        )
    )
    return materializer_v2.ProtectedMaterializedTransactionRequestV2(
        handoff_plan=protected.handoff_plan,
        cas_witness=protected.cas_witness,
        authorization_consumption_receipt=(
            protected.authorization_consumption_receipt
        ),
        maintenance_permit=protected.maintenance_permit,
        live_lease_token=protected.live_lease_token,
        lease_witness=protected.lease_witness,
        request=request,
        envelope=envelope,
        envelope_sha256=envelope["envelope_sha256"],
    )


@dataclass(frozen=True, repr=False)
class ProtectedRequestMaterializerHarnessEvidenceV2:
    protected_request: materializer_v2.ProtectedMaterializedTransactionRequestV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedRequestMaterializerHarnessEvidenceV2(<protected>)"


def protected_request_materializer_harness_evidence_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedRequestMaterializerHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    try:
        independent_oracle = _independent_request_oracle(
            value.protected_request.handoff_plan,
            value.protected_request.cas_witness,
        )
        return bool(
            materializer_v2.protected_materialized_transaction_request_valid_v2(
                value.protected_request
            )
            and evidence["evidence_version"]
            == PROTECTED_REQUEST_MATERIALIZER_HARNESS_EVIDENCE_VERSION_V2
            and evidence["handoff_plan_sha256"]
            == value.protected_request.handoff_plan.plan_sha256
            and evidence["cas_witness_sha256"]
            == value.protected_request.cas_witness.witness_sha256
            and evidence["materialized_request_envelope_sha256"]
            == value.protected_request.envelope_sha256
            and evidence["request_binding_sha256"]
            == value.protected_request.request["request_binding_sha256"]
            and evidence["independent_oracle_sha256"]
            == _sha(independent_oracle)
            and value.protected_request.request == independent_oracle
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
            and evidence["canonicalization_count"] == 1
            and evidence["lease_revalidation_count"] == 1
            and evidence["request_materialized"] is True
            and evidence["request_binding_materialized"] is True
            and all(
                evidence[key] is False
                for key in (
                    "bare_request_exposed",
                    "authorization_consumed",
                    "provider_called",
                    "store_called",
                    "backend_called",
                    "writer_called",
                    "lock_acquired",
                    "filesystem_accessed",
                    "real_registry_accessed",
                    "network_accessed",
                    "broker_called",
                    "write_executed",
                    "production_authority",
                    "runtime_integrated",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_request_materializer_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def run_protected_request_materializer_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_REQUEST_MATERIALIZER_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_MATERIALIZER_HARNESS_V2_VERSION,
        "protected_request": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "request_materialized": False,
        "request_binding_materialized": False,
        "bare_request_exposed": False,
        "authorization_consumed": False,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "filesystem_accessed": False,
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
            bound = materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                fixture
            )
            intent = bound.get("protected_intent")
            if bound.get("ok") is not True or intent is None:
                base["reason"] = "UPSTREAM_PROTECTED_INTENT_INVALID"
                return base
            planner = handoff_v2.DormantProtectedRequestHandoffContractV2(
                handoff_v2.DormantProtectedRequestHandoffConfigV2(
                    enabled=True,
                    scope_attestation=(
                        handoff_v2.OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2
                    ),
                    expected_materialization_intent_sha256=intent.intent_sha256,
                )
            )
            planned = planner.plan_offline(
                intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            plan = planned.get("protected_plan")
            if planned.get("ok") is not True or plan is None:
                base["reason"] = "UPSTREAM_HANDOFF_PLAN_INVALID"
                return base
            cas_witness = handoff_harness.build_synthetic_target_cas_witness_offline_v2(
                intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
                observed_at_epoch=fixture["now_epoch"],
            )
            materializer = materializer_v2.OfflineProtectedRequestMaterializerV2(
                materializer_v2.OfflineProtectedRequestMaterializerConfigV2(
                    enabled=True,
                    scope_attestation=(
                        materializer_v2.OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2
                    ),
                    expected_handoff_plan_sha256=plan.plan_sha256,
                    maximum_cas_witness_age_seconds=5,
                )
            )
            materialized = materializer.materialize_offline(
                plan,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            protected = materialized.get("protected_request")
            if materialized.get("ok") is not True or protected is None:
                base["reason"] = "PROTECTED_REQUEST_MATERIALIZATION_FAILED"
                return base

            oracle = _independent_request_oracle(plan, cas_witness)
            request = protected.request
            substituted = materializer_v2.ProtectedMaterializedTransactionRequestV2(
                handoff_plan=protected.handoff_plan,
                cas_witness=protected.cas_witness,
                authorization_consumption_receipt=(
                    protected.authorization_consumption_receipt
                ),
                maintenance_permit=copy.copy(protected.maintenance_permit),
                live_lease_token=protected.live_lease_token,
                lease_witness=protected.lease_witness,
                request=protected.request,
                envelope=protected.envelope,
                envelope_sha256=protected.envelope_sha256,
            )
            generation_request = copy.deepcopy(dict(request))
            generation_request["expected_generation"] += 1
            candidate_request = copy.deepcopy(dict(request))
            candidate_request["candidate_raw_document_utf8"] = "{}"
            candidate_request["candidate_raw_document_sha256"] = (
                backend_v2.raw_utf8_sha256_v2("{}")
            )
            identity_request = copy.deepcopy(dict(request))
            identity_request["request_sha256"] = _sha("arbitrary-request")
            stale = materializer.materialize_offline(
                plan,
                cas_witness,
                now_epoch=fixture["now_epoch"] + 6,
            )
            default_off = (
                materializer_v2.OfflineProtectedRequestMaterializerV2().materialize_offline(
                    None,
                    None,
                    now_epoch=0,
                )
            )
            no_execution_surface = all(
                not hasattr(protected, name)
                for name in (
                    "apply_under_held_maintenance_lease",
                    "apply_attested_transaction_offline",
                    "invoke",
                    "activate",
                )
            )
            receipt = protected.authorization_consumption_receipt
            checks_by_name = {
                "PROTECTED_MATERIALIZED_REQUEST_VALID": materializer_v2.protected_materialized_transaction_request_valid_v2(protected),
                "INDEPENDENT_REQUEST_ORACLE_EXACT_MATCH": request == oracle,
                "CANONICAL_CANDIDATE_BYTES_AND_HASH_EXACT": request["candidate_raw_document_utf8"] == _canonical_candidate(intent.source_envelope.request["candidate_registry"]) and request["candidate_raw_document_sha256"] == backend_v2.raw_utf8_sha256_v2(request["candidate_raw_document_utf8"]),
                "CANONICALIZATION_OCCURRED_EXACTLY_ONCE": materialized["canonicalization_count"] == 1,
                "LEASE_REVALIDATED_AT_SEALING_EXACTLY_ONCE": materialized["lease_revalidation_count"] == 1 and protected.envelope["lease_revalidated_at_materialization"] is True,
                "SAME_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED": protected.maintenance_permit is intent.maintenance_permit and protected.live_lease_token is intent.live_lease_token and protected.lease_witness is intent.lease_witness,
                "CAS_GENERATION_AND_RAW_HASH_EXACT": request["expected_generation"] == cas_witness.witness["observed_generation"] and request["expected_raw_document_sha256"] == cas_witness.witness["observed_raw_document_sha256"],
                "AUTHORIZATION_AND_DEADLINE_REVALIDATED": protected.envelope["authorization_revalidated_at_materialization"] is True and protected.envelope["materialized_at_epoch"] < receipt["expires_at_epoch"] and protected.envelope["materialized_at_epoch"] < request["deadline_epoch"],
                "ONLY_PROTECTED_WRAPPER_DELIVERED": materialized["bare_request_exposed"] is False and type(protected) is materializer_v2.ProtectedMaterializedTransactionRequestV2,
                "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "PROTECTED_REQUEST_MATERIALIZER_V2_DEFAULT_OFF",
                "STALE_CAS_WITNESS_REJECTED": stale["ok"] is False and stale["reason"] == "PROTECTED_TARGET_CAS_WITNESS_STALE",
                "SUBSTITUTED_PERMIT_INSTANCE_REJECTED": not materializer_v2.protected_materialized_transaction_request_valid_v2(substituted),
                "RESEALED_GENERATION_TAMPER_REJECTED": not materializer_v2.protected_materialized_transaction_request_valid_v2(_resealed_wrapper(protected, generation_request)),
                "RESEALED_CANDIDATE_TAMPER_REJECTED": not materializer_v2.protected_materialized_transaction_request_valid_v2(_resealed_wrapper(protected, candidate_request)),
                "RESEALED_ARBITRARY_IDENTITY_REJECTED": not materializer_v2.protected_materialized_transaction_request_valid_v2(_resealed_wrapper(protected, identity_request)),
                "NO_EXECUTION_SURFACE_OR_SIDE_EFFECT": no_execution_surface and all(materialized[key] is False for key in ("provider_called", "store_called", "backend_called", "writer_called", "lock_acquired", "filesystem_accessed", "real_registry_accessed", "network_accessed", "broker_called", "write_executed", "production_authority", "runtime_integrated", "activation_allowed", "live_allowed")),
            }
            checks = [
                {"name": name, "passed": checks_by_name[name] is True}
                for name in _CHECK_NAMES
            ]
            if not all(item["passed"] for item in checks):
                base["reason"] = "PROTECTED_REQUEST_MATERIALIZER_ORACLE_FAILED"
                return base
            evidence = {
                "evidence_version": PROTECTED_REQUEST_MATERIALIZER_HARNESS_EVIDENCE_VERSION_V2,
                "handoff_plan_sha256": plan.plan_sha256,
                "cas_witness_sha256": cas_witness.witness_sha256,
                "materialized_request_envelope_sha256": protected.envelope_sha256,
                "request_binding_sha256": request["request_binding_sha256"],
                "independent_oracle_sha256": _sha(oracle),
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "canonicalization_count": materialized["canonicalization_count"],
                "lease_revalidation_count": materialized["lease_revalidation_count"],
                "request_materialized": True,
                "request_binding_materialized": True,
                "bare_request_exposed": False,
                "authorization_consumed": False,
                "provider_called": False,
                "store_called": False,
                "backend_called": False,
                "writer_called": False,
                "lock_acquired": False,
                "filesystem_accessed": False,
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
                protected_request_materializer_harness_evidence_sha256_v2(
                    evidence
                )
            )
            protected_evidence = ProtectedRequestMaterializerHarnessEvidenceV2(
                protected_request=protected,
                evidence=copy.deepcopy(evidence),
                evidence_sha256=evidence["evidence_sha256"],
            )
            if not protected_request_materializer_harness_evidence_valid_v2(
                protected_evidence
            ):
                base["reason"] = "PROTECTED_MATERIALIZER_EVIDENCE_INTERNAL_INVALID"
                return base
    except Exception:
        base["reason"] = "PROTECTED_REQUEST_MATERIALIZER_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_REQUEST_MATERIALIZER_HARNESS_PASSED_OFFLINE",
            "protected_request": protected,
            "protected_evidence": protected_evidence,
            "request_envelope_sha256": protected.envelope_sha256,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
            "request_materialized": True,
            "request_binding_materialized": True,
        }
    )
    return base


__all__ = [
    "PROTECTED_REQUEST_MATERIALIZER_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedRequestMaterializerHarnessEvidenceV2",
    "protected_request_materializer_harness_evidence_sha256_v2",
    "protected_request_materializer_harness_evidence_valid_v2",
    "run_protected_request_materializer_harness_v2",
]
