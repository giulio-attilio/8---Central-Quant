"""Synthetic harness for the dormant protected held-lease adapter contract."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as handoff_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2 as adapter_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HELD-LEASE-PORT-ADAPTER-HARNESS-V2"
)
PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EVIDENCE_V2"
)

_CHECK_NAMES = (
    "PROTECTED_ADAPTER_PLAN_VALID",
    "EXACT_REQUEST_AND_CAS_INSTANCES_RETAINED",
    "EXACT_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED",
    "LEASE_REVALIDATED_AT_BOUNDARY_EXACTLY_ONCE",
    "AUTHORIZATION_DEADLINE_AND_CAS_FRESHNESS_BOUND",
    "NON_REENTRANT_PORT_REQUIRED",
    "RAW_MAPPING_AND_RECANONICALIZATION_FORBIDDEN",
    "BACKEND_BINDING_AND_EXECUTION_DEFERRED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "COPIED_CAS_WITNESS_INSTANCE_REJECTED",
    "STALE_CAS_WITNESS_REJECTED",
    "CAS_FRESHNESS_BUDGET_ESCALATION_REJECTED",
    "ENVELOPE_PIN_MISMATCH_REJECTED",
    "RESEALED_BACKEND_CALL_ESCALATION_REJECTED",
    "NO_EXECUTION_METHOD_EXPOSED",
    "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "adapter_plan_sha256",
        "materialized_request_envelope_sha256",
        "cas_witness_sha256",
        "checks",
        "check_count",
        "passed_count",
        "lease_revalidation_count",
        "backend_bound",
        "backend_called",
        "provider_called",
        "store_called",
        "writer_called",
        "lock_acquired",
        "lock_released",
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


def protected_held_lease_port_adapter_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return backend_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedHeldLeasePortAdapterHarnessEvidenceV2:
    adapter_plan: adapter_v2.ProtectedHeldLeasePortAdapterPlanV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHeldLeasePortAdapterHarnessEvidenceV2(<protected>)"


def protected_held_lease_port_adapter_harness_evidence_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedHeldLeasePortAdapterHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    try:
        return bool(
            adapter_v2.protected_held_lease_port_adapter_plan_valid_v2(
                value.adapter_plan
            )
            and evidence["evidence_version"]
            == PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EVIDENCE_VERSION_V2
            and evidence["adapter_plan_sha256"]
            == value.adapter_plan.plan_sha256
            and evidence["materialized_request_envelope_sha256"]
            == value.adapter_plan.protected_request.envelope_sha256
            and evidence["cas_witness_sha256"]
            == value.adapter_plan.cas_witness.witness_sha256
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
            and evidence["lease_revalidation_count"] == 1
            and all(
                evidence[key] is False
                for key in (
                    "backend_bound",
                    "backend_called",
                    "provider_called",
                    "store_called",
                    "writer_called",
                    "lock_acquired",
                    "lock_released",
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
                protected_held_lease_port_adapter_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def _adapter(protected_request, *, maximum_age: int = 5, pin: str | None = None):
    return adapter_v2.DormantProtectedHeldLeasePortAdapterV2(
        adapter_v2.DormantHeldLeasePortAdapterConfigV2(
            enabled=True,
            scope_attestation=(
                adapter_v2.OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
            ),
            expected_materialized_request_envelope_sha256=(
                pin or protected_request.envelope_sha256
            ),
            maximum_cas_witness_age_seconds=maximum_age,
        )
    )


def _resealed_backend_escalation(protected_plan):
    plan = copy.deepcopy(dict(protected_plan.plan))
    plan["backend_bound"] = True
    plan["backend_call_allowed"] = True
    plan["execution_deferred"] = False
    plan["plan_sha256"] = (
        adapter_v2.protected_held_lease_port_adapter_plan_sha256_v2(plan)
    )
    return adapter_v2.ProtectedHeldLeasePortAdapterPlanV2(
        protected_request=protected_plan.protected_request,
        cas_witness=protected_plan.cas_witness,
        maintenance_permit=protected_plan.maintenance_permit,
        live_lease_token=protected_plan.live_lease_token,
        lease_witness=protected_plan.lease_witness,
        plan=plan,
        plan_sha256=plan["plan_sha256"],
    )


def run_protected_held_lease_port_adapter_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_HARNESS_V2_VERSION,
        "protected_plan": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "lease_revalidation_count": 0,
        "backend_bound": False,
        "backend_called": False,
        "provider_called": False,
        "store_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "lock_released": False,
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
            materialization = materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                fixture
            )
            intent = materialization.get("protected_intent")
            if materialization.get("ok") is not True or intent is None:
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
            planned_handoff = planner.plan_offline(
                intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            handoff_plan = planned_handoff.get("protected_plan")
            if planned_handoff.get("ok") is not True or handoff_plan is None:
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
                    expected_handoff_plan_sha256=handoff_plan.plan_sha256,
                    maximum_cas_witness_age_seconds=5,
                )
            )
            materialized = materializer.materialize_offline(
                handoff_plan,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            protected_request = materialized.get("protected_request")
            if materialized.get("ok") is not True or protected_request is None:
                base["reason"] = "UPSTREAM_PROTECTED_REQUEST_INVALID"
                return base
            adapter = _adapter(protected_request)
            planned_adapter = adapter.plan_offline(
                protected_request,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            protected_plan = planned_adapter.get("protected_plan")
            if planned_adapter.get("ok") is not True or protected_plan is None:
                base["reason"] = "PROTECTED_ADAPTER_PLAN_FAILED"
                return base

            copied_cas = handoff_v2.ProtectedTargetCasWitnessV2(
                maintenance_permit=cas_witness.maintenance_permit,
                live_lease_token=cas_witness.live_lease_token,
                lease_witness=cas_witness.lease_witness,
                witness=cas_witness.witness,
                witness_sha256=cas_witness.witness_sha256,
            )
            copied_cas_result = adapter.plan_offline(
                protected_request,
                copied_cas,
                now_epoch=fixture["now_epoch"],
            )
            stale = adapter.plan_offline(
                protected_request,
                cas_witness,
                now_epoch=fixture["now_epoch"] + 6,
            )
            budget_escalation = _adapter(
                protected_request,
                maximum_age=6,
            ).plan_offline(
                protected_request,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            pin_mismatch = _adapter(
                protected_request,
                pin=backend_v2.stable_sha256_v2("wrong-envelope"),
            ).plan_offline(
                protected_request,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            default_off = adapter_v2.DormantProtectedHeldLeasePortAdapterV2().plan_offline(
                None,
                None,
                now_epoch=0,
            )
            plan = protected_plan.plan
            no_execution_method = all(
                not hasattr(protected_plan, name)
                for name in (
                    "apply_under_held_maintenance_lease",
                    "apply_attested_transaction_offline",
                    "invoke",
                    "activate",
                )
            )
            operational_false = (
                "backend_called",
                "provider_called",
                "store_called",
                "writer_called",
                "lock_acquired",
                "lock_released",
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
            checks_by_name = {
                "PROTECTED_ADAPTER_PLAN_VALID": adapter_v2.protected_held_lease_port_adapter_plan_valid_v2(protected_plan),
                "EXACT_REQUEST_AND_CAS_INSTANCES_RETAINED": protected_plan.protected_request is protected_request and protected_plan.cas_witness is protected_request.cas_witness,
                "EXACT_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED": protected_plan.maintenance_permit is protected_request.maintenance_permit and protected_plan.live_lease_token is protected_request.live_lease_token and protected_plan.lease_witness is protected_request.lease_witness,
                "LEASE_REVALIDATED_AT_BOUNDARY_EXACTLY_ONCE": planned_adapter["lease_revalidation_count"] == 1 and plan["lease_revalidated_at_boundary"] is True,
                "AUTHORIZATION_DEADLINE_AND_CAS_FRESHNESS_BOUND": plan["authorization_revalidated_at_boundary"] is True and plan["deadline_revalidated_at_boundary"] is True and plan["cas_freshness_revalidated_at_boundary"] is True,
                "NON_REENTRANT_PORT_REQUIRED": plan["required_method"] == handoff_v2.HELD_LEASE_BACKEND_PORT_METHOD_V2 and plan["maximum_lock_acquisition_count"] == 1 and plan["backend_reacquire_allowed"] is False and plan["store_reacquire_allowed"] is False and plan["adapter_release_allowed"] is False,
                "RAW_MAPPING_AND_RECANONICALIZATION_FORBIDDEN": plan["raw_mapping_input_allowed"] is False and plan["candidate_recanonicalization_allowed"] is False,
                "BACKEND_BINDING_AND_EXECUTION_DEFERRED": plan["backend_bound"] is False and plan["backend_call_allowed"] is False and plan["execution_deferred"] is True,
                "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "HELD_LEASE_PORT_ADAPTER_V2_DEFAULT_OFF",
                "COPIED_CAS_WITNESS_INSTANCE_REJECTED": copied_cas_result["ok"] is False and copied_cas_result["reason"] == "EXACT_EMBEDDED_CAS_WITNESS_INSTANCE_REQUIRED",
                "STALE_CAS_WITNESS_REJECTED": stale["ok"] is False and stale["reason"] == "PROTECTED_TARGET_CAS_WITNESS_STALE_AT_BOUNDARY",
                "CAS_FRESHNESS_BUDGET_ESCALATION_REJECTED": budget_escalation["ok"] is False and budget_escalation["reason"] == "CAS_FRESHNESS_BUDGET_ESCALATION_FORBIDDEN",
                "ENVELOPE_PIN_MISMATCH_REJECTED": pin_mismatch["ok"] is False and pin_mismatch["reason"] == "MATERIALIZED_REQUEST_ENVELOPE_PIN_MISMATCH",
                "RESEALED_BACKEND_CALL_ESCALATION_REJECTED": not adapter_v2.protected_held_lease_port_adapter_plan_valid_v2(_resealed_backend_escalation(protected_plan)),
                "NO_EXECUTION_METHOD_EXPOSED": no_execution_method,
                "NO_BACKEND_OR_OPERATIONAL_SIDE_EFFECT": all(planned_adapter[key] is False for key in operational_false),
            }
            checks = [
                {"name": name, "passed": checks_by_name[name] is True}
                for name in _CHECK_NAMES
            ]
            if not all(item["passed"] for item in checks):
                base["reason"] = "PROTECTED_HELD_LEASE_ADAPTER_ORACLE_FAILED"
                return base
            evidence = {
                "evidence_version": PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EVIDENCE_VERSION_V2,
                "adapter_plan_sha256": protected_plan.plan_sha256,
                "materialized_request_envelope_sha256": protected_request.envelope_sha256,
                "cas_witness_sha256": cas_witness.witness_sha256,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "lease_revalidation_count": 1,
                "backend_bound": False,
                "backend_called": False,
                "provider_called": False,
                "store_called": False,
                "writer_called": False,
                "lock_acquired": False,
                "lock_released": False,
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
                protected_held_lease_port_adapter_harness_evidence_sha256_v2(
                    evidence
                )
            )
            protected_evidence = ProtectedHeldLeasePortAdapterHarnessEvidenceV2(
                adapter_plan=protected_plan,
                evidence=copy.deepcopy(evidence),
                evidence_sha256=evidence["evidence_sha256"],
            )
            if not protected_held_lease_port_adapter_harness_evidence_valid_v2(
                protected_evidence
            ):
                base["reason"] = "PROTECTED_ADAPTER_EVIDENCE_INTERNAL_INVALID"
                return base
    except Exception:
        base["reason"] = "PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_PASSED_OFFLINE",
            "protected_plan": protected_plan,
            "protected_evidence": protected_evidence,
            "adapter_plan_sha256": protected_plan.plan_sha256,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
            "lease_revalidation_count": 1,
        }
    )
    return base


__all__ = [
    "PROTECTED_HELD_LEASE_PORT_ADAPTER_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedHeldLeasePortAdapterHarnessEvidenceV2",
    "protected_held_lease_port_adapter_harness_evidence_sha256_v2",
    "protected_held_lease_port_adapter_harness_evidence_valid_v2",
    "run_protected_held_lease_port_adapter_harness_v2",
]
