"""Dormant protected intent for future V1-to-V2 DTO materialization.

The contract binds the already-consumed V1 authorization, exact in-process
maintenance permit/token/witness instances, a synthetic target V2 snapshot,
canonical candidate bytes and a single-owner lock handoff.  It deliberately
does not build a V2 request, validate lease liveness, acquire a lock, consume
authorization, or call any provider, store, backend, writer, or runtime seam.
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
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as compatibility_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-DTO-MATERIALIZATION-CONTRACT-V2"
)
OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_OFFLINE_ONLY"
)
PROTECTED_DTO_MATERIALIZATION_INTENT_VERSION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_INTENT_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_KEYS = frozenset(
    {
        "subject_binding_sha256", "authorization_grant_sha256",
        "authorization_consumption_receipt_sha256", "consumption_count",
        "consumed_at_epoch", "expires_at_epoch", "already_consumed_upstream",
        "reconsumption_forbidden", "durable_runtime_ledger_required",
        "generic_hash_substitution_forbidden", "binding_sha256",
    }
)
_LEASE_KEYS = frozenset(
    {
        "coordinator_instance_sha256", "permit_instance_sha256",
        "permit_object_identity_sha256", "lease_token_sha256",
        "lease_token_object_identity_sha256", "lease_witness_object_identity_sha256",
        "maintenance_epoch", "lock_namespace_sha256", "registered_writer_count",
        "inflight_mutations", "shared_lock_acquired", "same_object_instances_retained",
        "hash_projection_is_not_live_authority", "current_time_liveness_revalidation_required",
        "lease_liveness_validated", "binding_sha256",
    }
)
_TARGET_KEYS = frozenset(
    {
        "target_backend_instance_sha256", "reference_backend_instance_sha256",
        "backend_instance_distinct_from_reference", "target_snapshot_sha256",
        "target_registry_path_binding_sha256", "target_lock_namespace_sha256",
        "target_generation", "source_expected_generation_token_sha256",
        "generation_resolver_evidence_sha256", "target_backend_capability_attestation_sha256",
        "fresh_snapshot_required_at_materialization", "production_identity_rebind_deferred",
        "binding_sha256",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "source_request_sha256", "source_transaction_sha256", "idempotency_key",
        "source_raw_document_sha256", "candidate_raw_document_sha256",
        "canonical_candidate_utf8_sha256", "canonicalization_count",
        "canonical_bytes_materialized_in_intent", "recanonicalization_forbidden",
        "binding_sha256",
    }
)
_DEADLINE_KEYS = frozenset(
    {
        "observed_at_epoch", "source_envelope_deadline_epoch",
        "lease_deadline_epoch", "boundary_deadline_epoch", "maximum_seconds",
        "effective_deadline_epoch", "current_time_revalidation_required",
        "binding_sha256",
    }
)
_LOCK_KEYS = frozenset(
    {
        "lock_namespace_sha256", "lock_owner", "maximum_acquisition_count",
        "lock_already_held_by_permit", "backend_reacquire_allowed",
        "store_reacquire_allowed", "invocation_adapter_reacquire_allowed",
        "non_reentrant_handoff_required", "release_owner",
        "lock_acquisition_performed", "binding_sha256",
    }
)
_RECOVERY_KEYS = frozenset(
    {
        "fresh_permit_required", "fresh_lease_required", "fresh_witness_validation_required",
        "fresh_maintenance_epoch_required", "epoch_must_differ",
        "separate_single_use_authorization_required", "fresh_target_snapshot_required",
        "fresh_prepared_catalog_required", "fresh_batch_required",
        "checkpoint_required", "request_materialization_deferred", "binding_sha256",
    }
)
_INTENT_KEYS = frozenset(
    {
        "intent_version", "scope_attestation", "bridge_plan_sha256",
        "compatibility_bundle_sha256", "schema_binding_sha256",
        "authorization_binding", "lease_instance_binding", "target_binding",
        "candidate_binding", "deadline_binding", "lock_handoff_policy",
        "recovery_policy", "deferred_runtime_evidence",
        "authorization_consumed_upstream", "authorization_consumption_allowed",
        "lease_validated_live", "request_materialized", "recovery_request_materialized",
        "provider_call_allowed", "store_call_allowed", "backend_call_allowed",
        "writer_call_allowed", "lock_acquired", "filesystem_accessed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "write_executed", "production_authority", "runtime_integrated",
        "activation_allowed", "live_allowed", "synthetic_only", "intent_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def materialization_binding_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "binding_sha256")


def materialization_intent_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "intent_sha256")


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value["binding_sha256"] = materialization_binding_sha256_v2(value)
    return value


def _sealed(value: Any, keys: frozenset[str]) -> bool:
    return bool(
        type(value) is dict
        and set(value) == keys
        and _valid_sha(value.get("binding_sha256"))
        and hmac.compare_digest(
            value["binding_sha256"], materialization_binding_sha256_v2(value)
        )
    )


def _object_identity_sha(kind: str, value: object) -> str:
    return backend_v2.stable_sha256_v2(
        {"kind": kind, "process_object_identity": id(value)}
    )


def _permit_material(
    permit: coordinator_v1.WriterMaintenancePermitV1,
) -> dict[str, Any]:
    return {
        "maintenance_epoch": permit.maintenance_epoch,
        "state": permit.state,
        "lock_namespace_sha256": permit.lock_namespace_sha256,
        "registered_writer_count": permit.registered_writer_count,
        "inflight_mutations": permit.inflight_mutations,
        "shared_lock_acquired": permit.shared_lock_acquired,
    }


def _canonical_candidate(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), allow_nan=False, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, repr=False)
class ProtectedBackendV2DtoMaterializationIntent:
    source_envelope: envelope_v1.ProtectedProductionInvocationEnvelopeV1 = field(repr=False)
    authorization_consumption_receipt: Mapping[str, Any] = field(repr=False)
    maintenance_permit: coordinator_v1.WriterMaintenancePermitV1 = field(repr=False)
    live_lease_token: consumer_v1.ProtectedSyntheticLiveLeaseTokenV1 = field(repr=False)
    lease_witness: consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1 = field(repr=False)
    target_snapshot: Mapping[str, Any] = field(repr=False)
    intent: Mapping[str, Any] = field(repr=False)
    intent_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedBackendV2DtoMaterializationIntent(<protected>)"


@dataclass(frozen=True)
class DormantBackendV2DtoMaterializationConfig:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_bridge_plan_sha256: str | None = field(default=None, repr=False)
    expected_compatibility_bundle_sha256: str | None = field(default=None, repr=False)
    maximum_deadline_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_deadline_seconds <= 300:
            raise ValueError("maximum_deadline_seconds must be between 1 and 300")


def _source_valid(
    source_envelope: envelope_v1.ProtectedProductionInvocationEnvelopeV1,
    authorization_consumption_receipt: Mapping[str, Any],
) -> tuple[bool, Mapping[str, Any] | None]:
    valid, request = envelope_v1._protected_request_valid(source_envelope)
    if not valid or request is None:
        return False, None
    receipt = authorization_consumption_receipt
    try:
        receipt_valid = bool(
            envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                source_envelope.subject_binding_sha256,
            )
            and receipt["receipt_sha256"]
            == source_envelope.authorization_consumption_receipt_sha256
        )
    except Exception:
        receipt_valid = False
    return receipt_valid, request if receipt_valid else None


def protected_backend_v2_dto_materialization_intent_valid(
    value: Any,
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> bool:
    if (
        type(value) is not ProtectedBackendV2DtoMaterializationIntent
        or not bridge_v2.protected_schema_bridge_plan_valid(bridge_plan)
        or not compatibility_v2.protected_writer_coordination_compatibility_bundle_valid_v2(
            compatibility_bundle
        )
    ):
        return False
    intent = value.intent
    if type(intent) is not dict or set(intent) != _INTENT_KEYS:
        return False
    source_valid, request = _source_valid(
        value.source_envelope, value.authorization_consumption_receipt
    )
    if not source_valid or request is None:
        return False
    permit = value.maintenance_permit
    token = value.live_lease_token
    witness = value.lease_witness
    snapshot = value.target_snapshot
    authorization = intent.get("authorization_binding")
    lease = intent.get("lease_instance_binding")
    target = intent.get("target_binding")
    candidate = intent.get("candidate_binding")
    deadline = intent.get("deadline_binding")
    lock = intent.get("lock_handoff_policy")
    recovery = intent.get("recovery_policy")
    compatibility = compatibility_bundle.bundle["compatibility_binding"]
    permit_projection = compatibility_bundle.bundle["maintenance_permit_projection"]
    lease_projection = compatibility_bundle.bundle["live_lease_projection"]
    try:
        canonical_candidate = _canonical_candidate(request["candidate_registry"])
        canonical_sha = backend_v2.raw_utf8_sha256_v2(canonical_candidate)
        return bool(
            _sealed(authorization, _AUTHORITY_KEYS)
            and _sealed(lease, _LEASE_KEYS)
            and _sealed(target, _TARGET_KEYS)
            and _sealed(candidate, _CANDIDATE_KEYS)
            and _sealed(deadline, _DEADLINE_KEYS)
            and _sealed(lock, _LOCK_KEYS)
            and _sealed(recovery, _RECOVERY_KEYS)
            and intent["intent_version"] == PROTECTED_DTO_MATERIALIZATION_INTENT_VERSION_V2
            and intent["scope_attestation"] == OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2
            and intent["bridge_plan_sha256"] == bridge_plan.plan_sha256
            and intent["compatibility_bundle_sha256"] == compatibility_bundle.bundle_sha256
            and bridge_plan.source_compatibility_bundle_sha256 == compatibility_bundle.bundle_sha256
            and intent["schema_binding_sha256"]
            == bridge_plan.plan["schema_binding"]["schema_binding_sha256"]
            and authorization["subject_binding_sha256"] == request["subject_binding_sha256"]
            and authorization["authorization_grant_sha256"]
            == value.authorization_consumption_receipt["grant_sha256"]
            and authorization["authorization_consumption_receipt_sha256"]
            == request["authorization_consumption_receipt_sha256"]
            and authorization["consumption_count"] == 1
            and authorization["consumed_at_epoch"]
            == value.authorization_consumption_receipt["consumed_at_epoch"]
            and authorization["expires_at_epoch"]
            == value.authorization_consumption_receipt["expires_at_epoch"]
            and authorization["already_consumed_upstream"] is True
            and authorization["reconsumption_forbidden"] is True
            and authorization["durable_runtime_ledger_required"] is True
            and authorization["generic_hash_substitution_forbidden"] is True
            and type(permit) is coordinator_v1.WriterMaintenancePermitV1
            and type(token) is consumer_v1.ProtectedSyntheticLiveLeaseTokenV1
            and type(witness) is consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1
            and permit.state == "QUIESCED"
            and permit.maintenance_epoch == request["maintenance_epoch"]
            and permit.lock_namespace_sha256 == coordinator_v1.canonical_runtime_lock_namespace_v1()
            and permit.registered_writer_count == 19
            and permit.inflight_mutations == 0
            and permit.shared_lock_acquired is True
            and token.permit_binding_sha256 == backend_v2.stable_sha256_v2(_permit_material(permit))
            and lease["coordinator_instance_sha256"] == compatibility["coordinator_instance_sha256"]
            and lease["permit_instance_sha256"] == compatibility["permit_instance_sha256"]
            and lease["permit_object_identity_sha256"] == _object_identity_sha("C3_MAINTENANCE_PERMIT_V1", permit)
            and lease["lease_token_sha256"] == token.token_sha256 == compatibility["lease_token_sha256"]
            and lease["lease_token_object_identity_sha256"] == _object_identity_sha("C3_LIVE_LEASE_TOKEN_V1", token)
            and lease["lease_witness_object_identity_sha256"] == _object_identity_sha("C3_LIVE_LEASE_WITNESS_V1", witness)
            and lease["maintenance_epoch"] == permit.maintenance_epoch == permit_projection["maintenance_epoch"] == lease_projection["maintenance_epoch"]
            and lease["lock_namespace_sha256"] == permit.lock_namespace_sha256
            and lease["registered_writer_count"] == 19
            and lease["inflight_mutations"] == 0
            and lease["shared_lock_acquired"] is True
            and lease["same_object_instances_retained"] is True
            and lease["hash_projection_is_not_live_authority"] is True
            and lease["current_time_liveness_revalidation_required"] is True
            and lease["lease_liveness_validated"] is False
            and backend_v2.backend_snapshot_valid_v2(snapshot)
            and target["target_backend_instance_sha256"] == snapshot["backend_instance_sha256"]
            and target["reference_backend_instance_sha256"] == bridge_plan.reference_backend_instance_sha256
            and target["backend_instance_distinct_from_reference"] is True
            and snapshot["backend_instance_sha256"] != bridge_plan.reference_backend_instance_sha256
            and target["target_snapshot_sha256"] == snapshot["snapshot_sha256"]
            and target["target_registry_path_binding_sha256"] == snapshot["registry_path_binding_sha256"] == request["registry_path_binding_sha256"]
            and target["target_lock_namespace_sha256"] == snapshot["lock_namespace_sha256"] == permit.lock_namespace_sha256
            and target["target_generation"] == snapshot["generation"]
            and target["source_expected_generation_token_sha256"] == request["expected_generation_token"]
            and _valid_sha(target["generation_resolver_evidence_sha256"])
            and _valid_sha(target["target_backend_capability_attestation_sha256"])
            and target["fresh_snapshot_required_at_materialization"] is True
            and target["production_identity_rebind_deferred"] is True
            and candidate["source_request_sha256"] == request["request_sha256"]
            and candidate["source_transaction_sha256"] == request["transaction_sha256"]
            and candidate["idempotency_key"] == request["idempotency_key"]
            and candidate["source_raw_document_sha256"] == request["expected_raw_document_sha256"]
            and candidate["candidate_raw_document_sha256"] == request["candidate_raw_document_sha256"] == canonical_sha
            and candidate["canonical_candidate_utf8_sha256"] == canonical_sha
            and candidate["canonicalization_count"] == 1
            and candidate["canonical_bytes_materialized_in_intent"] is False
            and candidate["recanonicalization_forbidden"] is True
            and deadline["source_envelope_deadline_epoch"] == value.source_envelope.expires_at_epoch
            and deadline["lease_deadline_epoch"] == token.expires_at_epoch
            and deadline["maximum_seconds"] <= 300
            and deadline["effective_deadline_epoch"] == min(
                deadline["source_envelope_deadline_epoch"],
                deadline["lease_deadline_epoch"],
                deadline["boundary_deadline_epoch"],
                deadline["observed_at_epoch"] + deadline["maximum_seconds"],
            )
            and deadline["observed_at_epoch"] < deadline["effective_deadline_epoch"]
            and deadline["current_time_revalidation_required"] is True
            and value.authorization_consumption_receipt["consumed_at_epoch"] <= deadline["observed_at_epoch"]
            and deadline["observed_at_epoch"] < value.authorization_consumption_receipt["expires_at_epoch"]
            and lock["lock_namespace_sha256"] == permit.lock_namespace_sha256
            and lock["lock_owner"] == "COORDINATOR_MAINTENANCE_LEASE"
            and lock["maximum_acquisition_count"] == 1
            and lock["lock_already_held_by_permit"] is True
            and lock["backend_reacquire_allowed"] is False
            and lock["store_reacquire_allowed"] is False
            and lock["invocation_adapter_reacquire_allowed"] is False
            and lock["non_reentrant_handoff_required"] is True
            and lock["release_owner"] == "COORDINATOR_CONTEXT_EXIT"
            and lock["lock_acquisition_performed"] is False
            and recovery["fresh_permit_required"] is True
            and recovery["fresh_lease_required"] is True
            and recovery["fresh_witness_validation_required"] is True
            and recovery["fresh_maintenance_epoch_required"] is True
            and recovery["epoch_must_differ"] is True
            and recovery["separate_single_use_authorization_required"] is True
            and recovery["fresh_target_snapshot_required"] is True
            and recovery["fresh_prepared_catalog_required"] is True
            and recovery["fresh_batch_required"] is True
            and recovery["checkpoint_required"] is True
            and recovery["request_materialization_deferred"] is True
            and intent["deferred_runtime_evidence"] == [
                "CURRENT_TIME_SAME_INSTANCE_LEASE_LIVENESS",
                "DURABLE_LEDGER_RECEIPT_CONFIRMATION",
                "FRESH_TARGET_V2_SNAPSHOT_AND_GENERATION_CAS",
                "NON_REENTRANT_BACKEND_PORT_USING_ALREADY_HELD_LOCK",
                "SEPARATE_RECOVERY_AUTHORIZATION_PERMIT_LEASE_AND_SNAPSHOT",
            ]
            and intent["authorization_consumed_upstream"] is True
            and all(
                intent[key] is False
                for key in (
                    "authorization_consumption_allowed", "lease_validated_live",
                    "request_materialized", "recovery_request_materialized",
                    "provider_call_allowed", "store_call_allowed", "backend_call_allowed",
                    "writer_call_allowed", "lock_acquired", "filesystem_accessed",
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "write_executed", "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and intent["synthetic_only"] is True
            and value.intent_sha256 == intent["intent_sha256"]
            and _valid_sha(intent["intent_sha256"])
            and hmac.compare_digest(intent["intent_sha256"], materialization_intent_sha256_v2(intent))
        )
    except Exception:
        return False


class DormantBackendV2DtoMaterializationContract:
    def __init__(self, config: DormantBackendV2DtoMaterializationConfig | None = None) -> None:
        self._config = config or DormantBackendV2DtoMaterializationConfig()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "BACKEND_V2_DTO_MATERIALIZATION_INTENT_BLOCKED",
            "reason": reason,
            "protected_intent": None,
            "authorization_consumed_upstream": False,
            "authorization_consumed": False,
            "lease_instance_bound": False,
            "lease_validated_live": False,
            "request_materialized": False,
            "recovery_request_materialized": False,
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

    def bind_intent_offline(
        self,
        *,
        bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
        compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
        source_envelope: envelope_v1.ProtectedProductionInvocationEnvelopeV1,
        authorization_consumption_receipt: Mapping[str, Any],
        maintenance_permit: coordinator_v1.WriterMaintenancePermitV1,
        live_lease_token: consumer_v1.ProtectedSyntheticLiveLeaseTokenV1,
        lease_witness: consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1,
        target_snapshot: Mapping[str, Any],
        target_backend_capability_attestation_sha256: str,
        generation_resolver_evidence_sha256: str,
        boundary_deadline_epoch: int,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("BACKEND_V2_DTO_MATERIALIZATION_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2:
            return self._failed("BACKEND_V2_DTO_MATERIALIZATION_SCOPE_REQUIRED")
        if not bridge_v2.protected_schema_bridge_plan_valid(bridge_plan):
            return self._failed("PROTECTED_SCHEMA_BRIDGE_PLAN_INVALID")
        if not compatibility_v2.protected_writer_coordination_compatibility_bundle_valid_v2(compatibility_bundle):
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_BUNDLE_INVALID")
        if not (
            _valid_sha(self._config.expected_bridge_plan_sha256)
            and hmac.compare_digest(str(self._config.expected_bridge_plan_sha256), bridge_plan.plan_sha256)
            and _valid_sha(self._config.expected_compatibility_bundle_sha256)
            and hmac.compare_digest(str(self._config.expected_compatibility_bundle_sha256), compatibility_bundle.bundle_sha256)
            and bridge_plan.source_compatibility_bundle_sha256 == compatibility_bundle.bundle_sha256
        ):
            return self._failed("UPSTREAM_PROTECTED_BINDING_PIN_MISMATCH")
        source_valid, request = _source_valid(
            source_envelope, authorization_consumption_receipt
        )
        if not source_valid or request is None:
            return self._failed("SOURCE_V1_ENVELOPE_OR_AUTHORIZATION_RECEIPT_INVALID")
        if not (
            type(maintenance_permit) is coordinator_v1.WriterMaintenancePermitV1
            and type(live_lease_token) is consumer_v1.ProtectedSyntheticLiveLeaseTokenV1
            and type(lease_witness) is consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1
            and backend_v2.backend_snapshot_valid_v2(target_snapshot)
            and _valid_sha(target_backend_capability_attestation_sha256)
            and _valid_sha(generation_resolver_evidence_sha256)
            and type(boundary_deadline_epoch) is int
            and type(now_epoch) is int
        ):
            return self._failed("MATERIALIZATION_AUTHORITY_OR_TARGET_INPUT_INVALID")
        compatibility = compatibility_bundle.bundle["compatibility_binding"]
        permit_projection = compatibility_bundle.bundle["maintenance_permit_projection"]
        lease_projection = compatibility_bundle.bundle["live_lease_projection"]
        permit_sha = backend_v2.stable_sha256_v2(_permit_material(maintenance_permit))
        if not (
            maintenance_permit.state == "QUIESCED"
            and maintenance_permit.maintenance_epoch == request["maintenance_epoch"] == permit_projection["maintenance_epoch"] == lease_projection["maintenance_epoch"]
            and maintenance_permit.lock_namespace_sha256 == coordinator_v1.canonical_runtime_lock_namespace_v1() == target_snapshot["lock_namespace_sha256"]
            and maintenance_permit.registered_writer_count == 19
            and maintenance_permit.inflight_mutations == 0
            and maintenance_permit.shared_lock_acquired is True
            and live_lease_token.permit_binding_sha256 == permit_sha
            and live_lease_token.token_sha256 == lease_projection["lease_token_sha256"] == compatibility["lease_token_sha256"]
            and now_epoch < live_lease_token.expires_at_epoch
            and target_snapshot["backend_instance_sha256"] != bridge_plan.reference_backend_instance_sha256
            and target_snapshot["registry_path_binding_sha256"] == request["registry_path_binding_sha256"]
        ):
            return self._failed("SAME_INSTANCE_LEASE_OR_TARGET_BINDING_INVALID")
        try:
            receipt = copy.deepcopy(dict(authorization_consumption_receipt))
            snapshot = copy.deepcopy(dict(target_snapshot))
            canonical_candidate = _canonical_candidate(request["candidate_registry"])
            canonical_sha = backend_v2.raw_utf8_sha256_v2(canonical_candidate)
        except Exception:
            return self._failed("CANDIDATE_CANONICALIZATION_FAILED_CLOSED")
        if canonical_sha != request["candidate_raw_document_sha256"]:
            return self._failed("CANDIDATE_CANONICAL_BYTES_HASH_MISMATCH")
        effective_deadline = min(
            source_envelope.expires_at_epoch,
            live_lease_token.expires_at_epoch,
            boundary_deadline_epoch,
            now_epoch + self._config.maximum_deadline_seconds,
        )
        if not (
            receipt["consumption_count"] == 1
            and receipt["consumed_at_epoch"] <= now_epoch < receipt["expires_at_epoch"]
            and now_epoch < effective_deadline
        ):
            return self._failed("AUTHORIZATION_OR_EFFECTIVE_DEADLINE_EXPIRED")
        authorization = _seal(
            {
                "subject_binding_sha256": source_envelope.subject_binding_sha256,
                "authorization_grant_sha256": receipt["grant_sha256"],
                "authorization_consumption_receipt_sha256": receipt["receipt_sha256"],
                "consumption_count": 1,
                "consumed_at_epoch": receipt["consumed_at_epoch"],
                "expires_at_epoch": receipt["expires_at_epoch"],
                "already_consumed_upstream": True,
                "reconsumption_forbidden": True,
                "durable_runtime_ledger_required": True,
                "generic_hash_substitution_forbidden": True,
            }
        )
        lease = _seal(
            {
                "coordinator_instance_sha256": compatibility["coordinator_instance_sha256"],
                "permit_instance_sha256": compatibility["permit_instance_sha256"],
                "permit_object_identity_sha256": _object_identity_sha("C3_MAINTENANCE_PERMIT_V1", maintenance_permit),
                "lease_token_sha256": live_lease_token.token_sha256,
                "lease_token_object_identity_sha256": _object_identity_sha("C3_LIVE_LEASE_TOKEN_V1", live_lease_token),
                "lease_witness_object_identity_sha256": _object_identity_sha("C3_LIVE_LEASE_WITNESS_V1", lease_witness),
                "maintenance_epoch": maintenance_permit.maintenance_epoch,
                "lock_namespace_sha256": maintenance_permit.lock_namespace_sha256,
                "registered_writer_count": 19,
                "inflight_mutations": 0,
                "shared_lock_acquired": True,
                "same_object_instances_retained": True,
                "hash_projection_is_not_live_authority": True,
                "current_time_liveness_revalidation_required": True,
                "lease_liveness_validated": False,
            }
        )
        target = _seal(
            {
                "target_backend_instance_sha256": snapshot["backend_instance_sha256"],
                "reference_backend_instance_sha256": bridge_plan.reference_backend_instance_sha256,
                "backend_instance_distinct_from_reference": True,
                "target_snapshot_sha256": snapshot["snapshot_sha256"],
                "target_registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
                "target_lock_namespace_sha256": snapshot["lock_namespace_sha256"],
                "target_generation": snapshot["generation"],
                "source_expected_generation_token_sha256": request["expected_generation_token"],
                "generation_resolver_evidence_sha256": generation_resolver_evidence_sha256,
                "target_backend_capability_attestation_sha256": target_backend_capability_attestation_sha256,
                "fresh_snapshot_required_at_materialization": True,
                "production_identity_rebind_deferred": True,
            }
        )
        candidate = _seal(
            {
                "source_request_sha256": request["request_sha256"],
                "source_transaction_sha256": request["transaction_sha256"],
                "idempotency_key": request["idempotency_key"],
                "source_raw_document_sha256": request["expected_raw_document_sha256"],
                "candidate_raw_document_sha256": request["candidate_raw_document_sha256"],
                "canonical_candidate_utf8_sha256": canonical_sha,
                "canonicalization_count": 1,
                "canonical_bytes_materialized_in_intent": False,
                "recanonicalization_forbidden": True,
            }
        )
        deadline = _seal(
            {
                "observed_at_epoch": now_epoch,
                "source_envelope_deadline_epoch": source_envelope.expires_at_epoch,
                "lease_deadline_epoch": live_lease_token.expires_at_epoch,
                "boundary_deadline_epoch": boundary_deadline_epoch,
                "maximum_seconds": self._config.maximum_deadline_seconds,
                "effective_deadline_epoch": effective_deadline,
                "current_time_revalidation_required": True,
            }
        )
        lock = _seal(
            {
                "lock_namespace_sha256": maintenance_permit.lock_namespace_sha256,
                "lock_owner": "COORDINATOR_MAINTENANCE_LEASE",
                "maximum_acquisition_count": 1,
                "lock_already_held_by_permit": True,
                "backend_reacquire_allowed": False,
                "store_reacquire_allowed": False,
                "invocation_adapter_reacquire_allowed": False,
                "non_reentrant_handoff_required": True,
                "release_owner": "COORDINATOR_CONTEXT_EXIT",
                "lock_acquisition_performed": False,
            }
        )
        recovery = _seal(
            {
                "fresh_permit_required": True,
                "fresh_lease_required": True,
                "fresh_witness_validation_required": True,
                "fresh_maintenance_epoch_required": True,
                "epoch_must_differ": True,
                "separate_single_use_authorization_required": True,
                "fresh_target_snapshot_required": True,
                "fresh_prepared_catalog_required": True,
                "fresh_batch_required": True,
                "checkpoint_required": True,
                "request_materialization_deferred": True,
            }
        )
        intent = {
            "intent_version": PROTECTED_DTO_MATERIALIZATION_INTENT_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2,
            "bridge_plan_sha256": bridge_plan.plan_sha256,
            "compatibility_bundle_sha256": compatibility_bundle.bundle_sha256,
            "schema_binding_sha256": bridge_plan.plan["schema_binding"]["schema_binding_sha256"],
            "authorization_binding": authorization,
            "lease_instance_binding": lease,
            "target_binding": target,
            "candidate_binding": candidate,
            "deadline_binding": deadline,
            "lock_handoff_policy": lock,
            "recovery_policy": recovery,
            "deferred_runtime_evidence": [
                "CURRENT_TIME_SAME_INSTANCE_LEASE_LIVENESS",
                "DURABLE_LEDGER_RECEIPT_CONFIRMATION",
                "FRESH_TARGET_V2_SNAPSHOT_AND_GENERATION_CAS",
                "NON_REENTRANT_BACKEND_PORT_USING_ALREADY_HELD_LOCK",
                "SEPARATE_RECOVERY_AUTHORIZATION_PERMIT_LEASE_AND_SNAPSHOT",
            ],
            "authorization_consumed_upstream": True,
            "authorization_consumption_allowed": False,
            "lease_validated_live": False,
            "request_materialized": False,
            "recovery_request_materialized": False,
            "provider_call_allowed": False,
            "store_call_allowed": False,
            "backend_call_allowed": False,
            "writer_call_allowed": False,
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
        intent["intent_sha256"] = materialization_intent_sha256_v2(intent)
        protected = ProtectedBackendV2DtoMaterializationIntent(
            source_envelope=source_envelope,
            authorization_consumption_receipt=receipt,
            maintenance_permit=maintenance_permit,
            live_lease_token=live_lease_token,
            lease_witness=lease_witness,
            target_snapshot=snapshot,
            intent=copy.deepcopy(intent),
            intent_sha256=intent["intent_sha256"],
        )
        if not protected_backend_v2_dto_materialization_intent_valid(
            protected, bridge_plan, compatibility_bundle
        ):
            return self._failed("BACKEND_V2_DTO_MATERIALIZATION_INTENT_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "BACKEND_V2_DTO_MATERIALIZATION_INTENT_BOUND_OFFLINE",
                "reason": None,
                "protected_intent": protected,
                "intent_sha256": protected.intent_sha256,
                "authorization_consumed_upstream": True,
                "lease_instance_bound": True,
            }
        )
        return result


__all__ = [
    "DormantBackendV2DtoMaterializationConfig",
    "DormantBackendV2DtoMaterializationContract",
    "OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2",
    "ProtectedBackendV2DtoMaterializationIntent",
    "materialization_binding_sha256_v2",
    "materialization_intent_sha256_v2",
    "protected_backend_v2_dto_materialization_intent_valid",
]
