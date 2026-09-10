"""Dormant offline contract for the protected V2 held-lease port adapter.

This module binds a protected materialized request to the exact CAS witness and
same in-memory maintenance authority at a future non-reentrant backend boundary.
It creates only a protected plan and cannot receive or call a backend.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HELD-LEASE-PORT-ADAPTER-CONTRACT-V2"
)
OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_OFFLINE_ONLY"
)
PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_VERSION_V2 = (
    "C3_PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLAN_KEYS = frozenset(
    {
        "plan_version",
        "scope_attestation",
        "materialized_request_envelope_sha256",
        "handoff_plan_sha256",
        "cas_witness_sha256",
        "request_binding_sha256",
        "request_sha256",
        "transaction_sha256",
        "authorization_receipt_sha256",
        "subject_binding_sha256",
        "permit_object_identity_sha256",
        "lease_token_sha256",
        "lease_token_object_identity_sha256",
        "lease_witness_object_identity_sha256",
        "planned_at_epoch",
        "maximum_cas_witness_age_seconds",
        "cas_witness_age_seconds",
        "required_method",
        "legacy_self_locking_method_forbidden",
        "accepted_request_type",
        "accepted_cas_witness_type",
        "same_cas_witness_instance_required",
        "same_permit_instance_required",
        "same_lease_token_instance_required",
        "same_lease_witness_instance_required",
        "lease_revalidated_at_boundary",
        "authorization_revalidated_at_boundary",
        "deadline_revalidated_at_boundary",
        "cas_freshness_revalidated_at_boundary",
        "request_wrapper_revalidated_at_boundary",
        "lock_already_held_required",
        "maximum_lock_acquisition_count",
        "backend_reacquire_allowed",
        "store_reacquire_allowed",
        "adapter_release_allowed",
        "raw_mapping_input_allowed",
        "candidate_recanonicalization_allowed",
        "terminal_result_validation_required",
        "execution_deferred",
        "backend_bound",
        "backend_call_allowed",
        "synthetic_only",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "plan_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def protected_held_lease_port_adapter_plan_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return backend_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "plan_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedHeldLeasePortAdapterPlanV2:
    protected_request: materializer_v2.ProtectedMaterializedTransactionRequestV2 = field(
        repr=False
    )
    cas_witness: handoff_v2.ProtectedTargetCasWitnessV2 = field(repr=False)
    maintenance_permit: Any = field(repr=False)
    live_lease_token: Any = field(repr=False)
    lease_witness: Any = field(repr=False)
    plan: Mapping[str, Any] = field(repr=False)
    plan_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHeldLeasePortAdapterPlanV2(<protected>)"


@dataclass(frozen=True)
class DormantHeldLeasePortAdapterConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_materialized_request_envelope_sha256: str | None = field(
        default=None,
        repr=False,
    )
    maximum_cas_witness_age_seconds: int = 5

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_cas_witness_age_seconds <= 30:
            raise ValueError(
                "maximum_cas_witness_age_seconds must be between 0 and 30"
            )


def protected_held_lease_port_adapter_plan_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedHeldLeasePortAdapterPlanV2:
        return False
    protected = value.protected_request
    if not materializer_v2.protected_materialized_transaction_request_valid_v2(
        protected
    ):
        return False
    if value.cas_witness is not protected.cas_witness:
        return False
    plan = value.plan
    if type(plan) is not dict or set(plan) != _PLAN_KEYS:
        return False
    intent = protected.handoff_plan.materialization_intent
    lease = intent.intent["lease_instance_binding"]
    request = protected.request
    envelope = protected.envelope
    receipt = protected.authorization_consumption_receipt
    cas = value.cas_witness.witness
    port = protected.handoff_plan.plan["held_lease_backend_port_contract"]
    try:
        witness_age = plan["planned_at_epoch"] - cas["observed_at_epoch"]
        return bool(
            value.maintenance_permit is protected.maintenance_permit
            and value.live_lease_token is protected.live_lease_token
            and value.lease_witness is protected.lease_witness
            and plan["plan_version"]
            == PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_VERSION_V2
            and plan["scope_attestation"]
            == OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
            and plan["materialized_request_envelope_sha256"]
            == protected.envelope_sha256
            and plan["handoff_plan_sha256"]
            == protected.handoff_plan.plan_sha256
            and plan["cas_witness_sha256"] == value.cas_witness.witness_sha256
            and plan["request_binding_sha256"]
            == request["request_binding_sha256"]
            and plan["request_sha256"] == request["request_sha256"]
            and plan["transaction_sha256"] == request["transaction_sha256"]
            and plan["authorization_receipt_sha256"]
            == receipt["receipt_sha256"]
            and plan["subject_binding_sha256"]
            == intent.source_envelope.subject_binding_sha256
            and plan["permit_object_identity_sha256"]
            == lease["permit_object_identity_sha256"]
            and plan["lease_token_sha256"] == lease["lease_token_sha256"]
            and plan["lease_token_object_identity_sha256"]
            == lease["lease_token_object_identity_sha256"]
            and plan["lease_witness_object_identity_sha256"]
            == lease["lease_witness_object_identity_sha256"]
            and type(plan["planned_at_epoch"]) is int
            and plan["planned_at_epoch"] >= envelope["materialized_at_epoch"]
            and type(plan["maximum_cas_witness_age_seconds"]) is int
            and 0 <= plan["maximum_cas_witness_age_seconds"]
            <= envelope["maximum_cas_witness_age_seconds"]
            and witness_age == plan["cas_witness_age_seconds"]
            and 0 <= witness_age <= plan["maximum_cas_witness_age_seconds"]
            and plan["planned_at_epoch"] < request["deadline_epoch"]
            and plan["planned_at_epoch"] < receipt["expires_at_epoch"]
            and plan["planned_at_epoch"] < value.live_lease_token.expires_at_epoch
            and envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                intent.source_envelope.subject_binding_sha256,
            )
            and plan["required_method"]
            == port["required_method"]
            == handoff_v2.HELD_LEASE_BACKEND_PORT_METHOD_V2
            and plan["legacy_self_locking_method_forbidden"]
            == port["legacy_self_locking_method_forbidden"]
            == "apply_attested_transaction_offline"
            and plan["accepted_request_type"]
            == port["accepted_request_type"]
            == "ProtectedMaterializedTransactionRequestV2"
            and plan["accepted_cas_witness_type"]
            == port["accepted_cas_witness_type"]
            == "ProtectedTargetCasWitnessV2"
            and plan["same_cas_witness_instance_required"] is True
            and plan["same_permit_instance_required"] is True
            and plan["same_lease_token_instance_required"] is True
            and plan["same_lease_witness_instance_required"] is True
            and plan["lease_revalidated_at_boundary"] is True
            and plan["authorization_revalidated_at_boundary"] is True
            and plan["deadline_revalidated_at_boundary"] is True
            and plan["cas_freshness_revalidated_at_boundary"] is True
            and plan["request_wrapper_revalidated_at_boundary"] is True
            and plan["lock_already_held_required"] is True
            and plan["maximum_lock_acquisition_count"] == 1
            and plan["backend_reacquire_allowed"] is False
            and plan["store_reacquire_allowed"] is False
            and plan["adapter_release_allowed"] is False
            and plan["raw_mapping_input_allowed"] is False
            and plan["candidate_recanonicalization_allowed"] is False
            and plan["terminal_result_validation_required"] is True
            and plan["execution_deferred"] is True
            and plan["backend_bound"] is False
            and plan["backend_call_allowed"] is False
            and plan["synthetic_only"] is True
            and plan["production_authority"] is False
            and plan["runtime_integrated"] is False
            and plan["activation_allowed"] is False
            and plan["live_allowed"] is False
            and value.plan_sha256 == plan["plan_sha256"]
            and _valid_sha(plan["plan_sha256"])
            and hmac.compare_digest(
                plan["plan_sha256"],
                protected_held_lease_port_adapter_plan_sha256_v2(plan),
            )
        )
    except Exception:
        return False


class DormantProtectedHeldLeasePortAdapterV2:
    def __init__(
        self,
        config: DormantHeldLeasePortAdapterConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantHeldLeasePortAdapterConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_V2_BLOCKED",
            "reason": reason,
            "protected_plan": None,
            "lease_revalidation_count": 0,
            "authorization_consumed": False,
            "raw_request_exposed": False,
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

    def plan_offline(
        self,
        protected_request: materializer_v2.ProtectedMaterializedTransactionRequestV2,
        cas_witness: handoff_v2.ProtectedTargetCasWitnessV2,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("HELD_LEASE_PORT_ADAPTER_V2_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
        ):
            return self._failed("HELD_LEASE_PORT_ADAPTER_V2_SCOPE_REQUIRED")
        if not materializer_v2.protected_materialized_transaction_request_valid_v2(
            protected_request
        ):
            return self._failed("PROTECTED_MATERIALIZED_REQUEST_INVALID")
        if not (
            _valid_sha(
                self._config.expected_materialized_request_envelope_sha256
            )
            and hmac.compare_digest(
                str(
                    self._config.expected_materialized_request_envelope_sha256
                ),
                protected_request.envelope_sha256,
            )
        ):
            return self._failed("MATERIALIZED_REQUEST_ENVELOPE_PIN_MISMATCH")
        if cas_witness is not protected_request.cas_witness:
            return self._failed("EXACT_EMBEDDED_CAS_WITNESS_INSTANCE_REQUIRED")
        if type(now_epoch) is not int:
            return self._failed("HELD_LEASE_PORT_ADAPTER_CLOCK_INVALID")
        envelope = protected_request.envelope
        if (
            self._config.maximum_cas_witness_age_seconds
            > envelope["maximum_cas_witness_age_seconds"]
        ):
            return self._failed("CAS_FRESHNESS_BUDGET_ESCALATION_FORBIDDEN")
        cas = cas_witness.witness
        witness_age = now_epoch - cas["observed_at_epoch"]
        if not (
            now_epoch >= envelope["materialized_at_epoch"]
            and 0
            <= witness_age
            <= self._config.maximum_cas_witness_age_seconds
        ):
            return self._failed("PROTECTED_TARGET_CAS_WITNESS_STALE_AT_BOUNDARY")
        intent = protected_request.handoff_plan.materialization_intent
        receipt = protected_request.authorization_consumption_receipt
        request = protected_request.request
        if not (
            now_epoch < request["deadline_epoch"]
            and now_epoch < receipt["expires_at_epoch"]
            and now_epoch < protected_request.live_lease_token.expires_at_epoch
            and envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                intent.source_envelope.subject_binding_sha256,
            )
        ):
            return self._failed("AUTHORIZATION_OR_BOUNDARY_DEADLINE_EXPIRED")
        try:
            lease_live = protected_request.lease_witness.validate_live(
                protected_request.maintenance_permit,
                protected_request.live_lease_token,
                now_epoch=now_epoch,
            )
        except Exception:
            lease_live = False
        if not lease_live:
            return self._failed("SAME_INSTANCE_LEASE_NOT_LIVE_AT_BOUNDARY")
        lease = intent.intent["lease_instance_binding"]
        port = protected_request.handoff_plan.plan[
            "held_lease_backend_port_contract"
        ]
        if not (
            port["required_method"]
            == handoff_v2.HELD_LEASE_BACKEND_PORT_METHOD_V2
            and port["lock_already_held_required"] is True
            and port["maximum_acquisition_count"] == 1
            and port["backend_reacquire_allowed"] is False
            and port["store_reacquire_allowed"] is False
            and port["backend_call_allowed"] is False
        ):
            return self._failed("NON_REENTRANT_PORT_CONTRACT_INVALID")
        plan = {
            "plan_version": PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_VERSION_V2,
            "scope_attestation": OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2,
            "materialized_request_envelope_sha256": protected_request.envelope_sha256,
            "handoff_plan_sha256": protected_request.handoff_plan.plan_sha256,
            "cas_witness_sha256": cas_witness.witness_sha256,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "authorization_receipt_sha256": receipt["receipt_sha256"],
            "subject_binding_sha256": intent.source_envelope.subject_binding_sha256,
            "permit_object_identity_sha256": lease[
                "permit_object_identity_sha256"
            ],
            "lease_token_sha256": lease["lease_token_sha256"],
            "lease_token_object_identity_sha256": lease[
                "lease_token_object_identity_sha256"
            ],
            "lease_witness_object_identity_sha256": lease[
                "lease_witness_object_identity_sha256"
            ],
            "planned_at_epoch": now_epoch,
            "maximum_cas_witness_age_seconds": self._config.maximum_cas_witness_age_seconds,
            "cas_witness_age_seconds": witness_age,
            "required_method": handoff_v2.HELD_LEASE_BACKEND_PORT_METHOD_V2,
            "legacy_self_locking_method_forbidden": "apply_attested_transaction_offline",
            "accepted_request_type": "ProtectedMaterializedTransactionRequestV2",
            "accepted_cas_witness_type": "ProtectedTargetCasWitnessV2",
            "same_cas_witness_instance_required": True,
            "same_permit_instance_required": True,
            "same_lease_token_instance_required": True,
            "same_lease_witness_instance_required": True,
            "lease_revalidated_at_boundary": True,
            "authorization_revalidated_at_boundary": True,
            "deadline_revalidated_at_boundary": True,
            "cas_freshness_revalidated_at_boundary": True,
            "request_wrapper_revalidated_at_boundary": True,
            "lock_already_held_required": True,
            "maximum_lock_acquisition_count": 1,
            "backend_reacquire_allowed": False,
            "store_reacquire_allowed": False,
            "adapter_release_allowed": False,
            "raw_mapping_input_allowed": False,
            "candidate_recanonicalization_allowed": False,
            "terminal_result_validation_required": True,
            "execution_deferred": True,
            "backend_bound": False,
            "backend_call_allowed": False,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        plan["plan_sha256"] = protected_held_lease_port_adapter_plan_sha256_v2(
            plan
        )
        protected_plan = ProtectedHeldLeasePortAdapterPlanV2(
            protected_request=protected_request,
            cas_witness=cas_witness,
            maintenance_permit=protected_request.maintenance_permit,
            live_lease_token=protected_request.live_lease_token,
            lease_witness=protected_request.lease_witness,
            plan=copy.deepcopy(plan),
            plan_sha256=plan["plan_sha256"],
        )
        if not protected_held_lease_port_adapter_plan_valid_v2(protected_plan):
            return self._failed("PROTECTED_HELD_LEASE_PORT_PLAN_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_PLANNED_OFFLINE",
                "reason": None,
                "protected_plan": protected_plan,
                "plan_sha256": protected_plan.plan_sha256,
                "lease_revalidation_count": 1,
            }
        )
        return result


__all__ = [
    "DormantHeldLeasePortAdapterConfigV2",
    "DormantProtectedHeldLeasePortAdapterV2",
    "OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2",
    "PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_VERSION_V2",
    "ProtectedHeldLeasePortAdapterPlanV2",
    "protected_held_lease_port_adapter_plan_sha256_v2",
    "protected_held_lease_port_adapter_plan_valid_v2",
]
