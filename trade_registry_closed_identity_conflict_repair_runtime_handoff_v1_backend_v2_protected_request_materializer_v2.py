"""Default-off offline materializer for one protected synthetic V2 request.

The materializer revalidates an in-memory lease and authorization receipt,
enforces CAS-witness freshness, canonicalizes candidate bytes exactly once and
returns only a protected wrapper.  It never calls a provider, store, backend,
writer, runtime seam, network endpoint, broker, or real Registry.
"""

from __future__ import annotations

import copy
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_MATERIALIZER_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-MATERIALIZER-V2"
)
OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_MATERIALIZER_OFFLINE_ONLY"
)
PROTECTED_MATERIALIZED_TRANSACTION_REQUEST_VERSION_V2 = (
    "C3_PROTECTED_MATERIALIZED_TRANSACTION_REQUEST_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_KEYS = frozenset(
    {
        "envelope_version", "handoff_plan_sha256", "cas_witness_sha256",
        "request_binding_sha256", "request_sha256", "transaction_sha256",
        "authorization_receipt_sha256", "subject_binding_sha256",
        "permit_object_identity_sha256", "lease_token_sha256",
        "lease_token_object_identity_sha256", "lease_witness_object_identity_sha256",
        "materialized_at_epoch", "maximum_cas_witness_age_seconds",
        "cas_witness_age_seconds", "canonicalization_count",
        "lease_revalidated_at_materialization", "authorization_revalidated_at_materialization",
        "same_object_instances_retained", "bare_request_delivery_allowed",
        "backend_call_allowed", "synthetic_only", "production_authority",
        "envelope_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def protected_materialized_request_envelope_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _hash_without(value, "envelope_sha256")


def _request_binding_sha256(request: Mapping[str, Any]) -> str:
    return _hash_without(request, "request_binding_sha256")


def _canonical_candidate(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), allow_nan=False, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, repr=False)
class ProtectedMaterializedTransactionRequestV2:
    handoff_plan: handoff_v2.ProtectedRequestHandoffPlanV2 = field(repr=False)
    cas_witness: handoff_v2.ProtectedTargetCasWitnessV2 = field(repr=False)
    authorization_consumption_receipt: Mapping[str, Any] = field(repr=False)
    maintenance_permit: Any = field(repr=False)
    live_lease_token: Any = field(repr=False)
    lease_witness: Any = field(repr=False)
    request: Mapping[str, Any] = field(repr=False)
    envelope: Mapping[str, Any] = field(repr=False)
    envelope_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedMaterializedTransactionRequestV2(<protected>)"


@dataclass(frozen=True)
class OfflineProtectedRequestMaterializerConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_handoff_plan_sha256: str | None = field(default=None, repr=False)
    maximum_cas_witness_age_seconds: int = 5

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_cas_witness_age_seconds <= 30:
            raise ValueError(
                "maximum_cas_witness_age_seconds must be between 0 and 30"
            )


def _protected_materialized_transaction_request_valid_v2(
    value: Any,
    *,
    known_canonical_candidate: str | None = None,
) -> bool:
    if type(value) is not ProtectedMaterializedTransactionRequestV2:
        return False
    plan = value.handoff_plan
    if not handoff_v2.protected_request_handoff_plan_valid_v2(plan):
        return False
    intent = plan.materialization_intent
    if not handoff_v2.protected_target_cas_witness_valid_v2(
        value.cas_witness,
        intent,
        plan.bridge_plan,
        plan.compatibility_bundle,
    ):
        return False
    request = value.request
    envelope = value.envelope
    receipt = value.authorization_consumption_receipt
    if (
        type(request) is not dict
        or type(envelope) is not dict
        or set(envelope) != _ENVELOPE_KEYS
        or not _valid_sha(envelope.get("envelope_sha256"))
        or not hmac.compare_digest(
            envelope["envelope_sha256"],
            protected_materialized_request_envelope_sha256_v2(envelope),
        )
    ):
        return False
    source_request = intent.source_envelope.request
    intent_data = intent.intent
    identity = plan.plan["identity_policy"]
    target = intent_data["target_binding"]
    candidate = intent_data["candidate_binding"]
    lease = intent_data["lease_instance_binding"]
    authorization = intent_data["authorization_binding"]
    deadline = intent_data["deadline_binding"]
    cas = value.cas_witness.witness
    try:
        canonical_candidate = (
            _canonical_candidate(source_request["candidate_registry"])
            if known_canonical_candidate is None
            else known_canonical_candidate
        )
        canonical_sha = backend_v2.raw_utf8_sha256_v2(canonical_candidate)
        materialized_at = envelope["materialized_at_epoch"]
        witness_age = materialized_at - cas["observed_at_epoch"]
        return bool(
            value.maintenance_permit is intent.maintenance_permit
            and value.live_lease_token is intent.live_lease_token
            and value.lease_witness is intent.lease_witness
            and value.cas_witness.maintenance_permit is value.maintenance_permit
            and value.cas_witness.live_lease_token is value.live_lease_token
            and value.cas_witness.lease_witness is value.lease_witness
            and receipt == intent.authorization_consumption_receipt
            and envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                intent.source_envelope.subject_binding_sha256,
            )
            and receipt["receipt_sha256"]
            == intent.source_envelope.authorization_consumption_receipt_sha256
            and type(materialized_at) is int
            and type(envelope["maximum_cas_witness_age_seconds"]) is int
            and 0 <= envelope["maximum_cas_witness_age_seconds"] <= 30
            and witness_age == envelope["cas_witness_age_seconds"]
            and 0 <= witness_age <= envelope["maximum_cas_witness_age_seconds"]
            and materialized_at < receipt["expires_at_epoch"]
            and materialized_at < value.live_lease_token.expires_at_epoch
            and materialized_at < deadline["effective_deadline_epoch"]
            and backend_v2.transaction_request_valid_v2(
                request, intent.target_snapshot
            )
            and request["request_version"] == backend_v2.TRANSACTION_REQUEST_VERSION_V2
            and request["backend_instance_sha256"]
            == target["target_backend_instance_sha256"]
            and request["backend_snapshot_sha256"]
            == target["target_snapshot_sha256"]
            and request["registry_path_binding_sha256"]
            == target["target_registry_path_binding_sha256"]
            and request["lock_namespace_sha256"]
            == target["target_lock_namespace_sha256"]
            and request["request_sha256"] == identity["expected_request_sha256"]
            and request["transaction_sha256"]
            == identity["expected_transaction_sha256"]
            and request["idempotency_key"] == candidate["idempotency_key"]
            and request["authorization_receipt_sha256"]
            == authorization["authorization_consumption_receipt_sha256"]
            and request["maintenance_epoch"] == lease["maintenance_epoch"]
            and request["expected_generation"]
            == cas["observed_generation"]
            == target["target_generation"]
            == intent.target_snapshot["generation"]
            and request["expected_raw_document_sha256"]
            == cas["observed_raw_document_sha256"]
            == candidate["source_raw_document_sha256"]
            and request["candidate_raw_document_utf8"] == canonical_candidate
            and request["candidate_raw_document_sha256"]
            == canonical_sha
            == candidate["candidate_raw_document_sha256"]
            and request["deadline_epoch"] == deadline["effective_deadline_epoch"]
            and request["synthetic_only"] is True
            and request["production_authority"] is False
            and request["request_binding_sha256"] == _request_binding_sha256(request)
            and envelope["envelope_version"]
            == PROTECTED_MATERIALIZED_TRANSACTION_REQUEST_VERSION_V2
            and envelope["handoff_plan_sha256"] == plan.plan_sha256
            and envelope["cas_witness_sha256"] == value.cas_witness.witness_sha256
            and envelope["request_binding_sha256"]
            == request["request_binding_sha256"]
            and envelope["request_sha256"] == request["request_sha256"]
            and envelope["transaction_sha256"] == request["transaction_sha256"]
            and envelope["authorization_receipt_sha256"]
            == receipt["receipt_sha256"]
            and envelope["subject_binding_sha256"]
            == intent.source_envelope.subject_binding_sha256
            and envelope["permit_object_identity_sha256"]
            == lease["permit_object_identity_sha256"]
            and envelope["lease_token_sha256"] == lease["lease_token_sha256"]
            and envelope["lease_token_object_identity_sha256"]
            == lease["lease_token_object_identity_sha256"]
            and envelope["lease_witness_object_identity_sha256"]
            == lease["lease_witness_object_identity_sha256"]
            and envelope["canonicalization_count"] == 1
            and envelope["lease_revalidated_at_materialization"] is True
            and envelope["authorization_revalidated_at_materialization"] is True
            and envelope["same_object_instances_retained"] is True
            and envelope["bare_request_delivery_allowed"] is False
            and envelope["backend_call_allowed"] is False
            and envelope["synthetic_only"] is True
            and envelope["production_authority"] is False
            and value.envelope_sha256 == envelope["envelope_sha256"]
        )
    except Exception:
        return False


def protected_materialized_transaction_request_valid_v2(value: Any) -> bool:
    return _protected_materialized_transaction_request_valid_v2(value)


class OfflineProtectedRequestMaterializerV2:
    def __init__(
        self, config: OfflineProtectedRequestMaterializerConfigV2 | None = None
    ) -> None:
        self._config = config or OfflineProtectedRequestMaterializerConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_REQUEST_MATERIALIZATION_V2_BLOCKED",
            "reason": reason,
            "protected_request": None,
            "request_materialized": False,
            "request_binding_materialized": False,
            "bare_request_exposed": False,
            "canonicalization_count": 0,
            "lease_revalidation_count": 0,
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

    def materialize_offline(
        self,
        handoff_plan: handoff_v2.ProtectedRequestHandoffPlanV2,
        cas_witness: handoff_v2.ProtectedTargetCasWitnessV2,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("PROTECTED_REQUEST_MATERIALIZER_V2_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2:
            return self._failed("PROTECTED_REQUEST_MATERIALIZER_V2_SCOPE_REQUIRED")
        if not handoff_v2.protected_request_handoff_plan_valid_v2(handoff_plan):
            return self._failed("PROTECTED_REQUEST_HANDOFF_PLAN_INVALID")
        if not (
            _valid_sha(self._config.expected_handoff_plan_sha256)
            and hmac.compare_digest(
                str(self._config.expected_handoff_plan_sha256),
                handoff_plan.plan_sha256,
            )
        ):
            return self._failed("PROTECTED_REQUEST_HANDOFF_PLAN_PIN_MISMATCH")
        intent = handoff_plan.materialization_intent
        if not handoff_v2.protected_target_cas_witness_valid_v2(
            cas_witness,
            intent,
            handoff_plan.bridge_plan,
            handoff_plan.compatibility_bundle,
        ):
            return self._failed("PROTECTED_TARGET_CAS_WITNESS_INVALID")
        if type(now_epoch) is not int:
            return self._failed("PROTECTED_REQUEST_MATERIALIZATION_CLOCK_INVALID")
        witness_age = now_epoch - cas_witness.witness["observed_at_epoch"]
        if not 0 <= witness_age <= self._config.maximum_cas_witness_age_seconds:
            return self._failed("PROTECTED_TARGET_CAS_WITNESS_STALE")
        receipt = intent.authorization_consumption_receipt
        deadline = intent.intent["deadline_binding"]["effective_deadline_epoch"]
        if not (
            now_epoch < deadline
            and now_epoch < intent.live_lease_token.expires_at_epoch
            and now_epoch < receipt["expires_at_epoch"]
            and envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                intent.source_envelope.subject_binding_sha256,
            )
            and receipt["receipt_sha256"]
            == intent.source_envelope.authorization_consumption_receipt_sha256
        ):
            return self._failed("AUTHORIZATION_OR_MATERIALIZATION_DEADLINE_EXPIRED")
        try:
            lease_live = intent.lease_witness.validate_live(
                intent.maintenance_permit,
                intent.live_lease_token,
                now_epoch=now_epoch,
            )
        except Exception:
            lease_live = False
        if not lease_live:
            return self._failed("SAME_INSTANCE_LIVE_LEASE_REVALIDATION_FAILED")
        try:
            canonical_candidate = _canonical_candidate(
                intent.source_envelope.request["candidate_registry"]
            )
            candidate_sha = backend_v2.raw_utf8_sha256_v2(canonical_candidate)
        except Exception:
            return self._failed("CANDIDATE_CANONICALIZATION_FAILED_CLOSED")
        identity = handoff_plan.plan["identity_policy"]
        target = intent.intent["target_binding"]
        candidate = intent.intent["candidate_binding"]
        lease = intent.intent["lease_instance_binding"]
        authorization = intent.intent["authorization_binding"]
        cas = cas_witness.witness
        if not (
            candidate_sha == candidate["candidate_raw_document_sha256"]
            and cas["observed_generation"]
            == target["target_generation"]
            == intent.target_snapshot["generation"]
            and cas["observed_raw_document_sha256"]
            == candidate["source_raw_document_sha256"]
        ):
            return self._failed("CANDIDATE_OR_CAS_PRECONDITION_MISMATCH")
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
            "expected_generation": cas["observed_generation"],
            "expected_raw_document_sha256": cas[
                "observed_raw_document_sha256"
            ],
            "candidate_raw_document_utf8": canonical_candidate,
            "candidate_raw_document_sha256": candidate_sha,
            "deadline_epoch": deadline,
            "synthetic_only": True,
            "production_authority": False,
        }
        request["request_binding_sha256"] = _request_binding_sha256(request)
        if not backend_v2.transaction_request_valid_v2(request, intent.target_snapshot):
            return self._failed("MATERIALIZED_V2_TRANSACTION_REQUEST_INVALID")
        envelope = {
            "envelope_version": PROTECTED_MATERIALIZED_TRANSACTION_REQUEST_VERSION_V2,
            "handoff_plan_sha256": handoff_plan.plan_sha256,
            "cas_witness_sha256": cas_witness.witness_sha256,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "authorization_receipt_sha256": receipt["receipt_sha256"],
            "subject_binding_sha256": intent.source_envelope.subject_binding_sha256,
            "permit_object_identity_sha256": lease["permit_object_identity_sha256"],
            "lease_token_sha256": lease["lease_token_sha256"],
            "lease_token_object_identity_sha256": lease[
                "lease_token_object_identity_sha256"
            ],
            "lease_witness_object_identity_sha256": lease[
                "lease_witness_object_identity_sha256"
            ],
            "materialized_at_epoch": now_epoch,
            "maximum_cas_witness_age_seconds": self._config.maximum_cas_witness_age_seconds,
            "cas_witness_age_seconds": witness_age,
            "canonicalization_count": 1,
            "lease_revalidated_at_materialization": True,
            "authorization_revalidated_at_materialization": True,
            "same_object_instances_retained": True,
            "bare_request_delivery_allowed": False,
            "backend_call_allowed": False,
            "synthetic_only": True,
            "production_authority": False,
        }
        envelope["envelope_sha256"] = (
            protected_materialized_request_envelope_sha256_v2(envelope)
        )
        protected = ProtectedMaterializedTransactionRequestV2(
            handoff_plan=handoff_plan,
            cas_witness=cas_witness,
            authorization_consumption_receipt=copy.deepcopy(dict(receipt)),
            maintenance_permit=intent.maintenance_permit,
            live_lease_token=intent.live_lease_token,
            lease_witness=intent.lease_witness,
            request=copy.deepcopy(request),
            envelope=copy.deepcopy(envelope),
            envelope_sha256=envelope["envelope_sha256"],
        )
        if not _protected_materialized_transaction_request_valid_v2(
            protected,
            known_canonical_candidate=canonical_candidate,
        ):
            return self._failed("PROTECTED_MATERIALIZED_REQUEST_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_REQUEST_MATERIALIZED_OFFLINE_SYNTHETIC_ONLY",
                "reason": None,
                "protected_request": protected,
                "envelope_sha256": protected.envelope_sha256,
                "request_binding_sha256": request["request_binding_sha256"],
                "request_materialized": True,
                "request_binding_materialized": True,
                "canonicalization_count": 1,
                "lease_revalidation_count": 1,
                "cas_witness_age_seconds": witness_age,
            }
        )
        return result


__all__ = [
    "OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2",
    "OfflineProtectedRequestMaterializerConfigV2",
    "OfflineProtectedRequestMaterializerV2",
    "PROTECTED_MATERIALIZED_TRANSACTION_REQUEST_VERSION_V2",
    "ProtectedMaterializedTransactionRequestV2",
    "protected_materialized_request_envelope_sha256_v2",
    "protected_materialized_transaction_request_valid_v2",
]
