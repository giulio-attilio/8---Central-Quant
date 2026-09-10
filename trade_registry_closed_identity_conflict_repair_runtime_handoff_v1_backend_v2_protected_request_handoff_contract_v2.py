"""Dormant contract for a protected, non-reentrant V2 request handoff.

This module defines canonical request identities, a same-lease CAS witness and
the shape of a backend port that consumes an already-held maintenance lease.
It emits a protected plan only.  It never materializes a transaction request,
validates lease liveness, loads the Registry, acquires a lock, or invokes a
provider, store, backend, writer, runtime seam, network endpoint, or broker.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as compatibility_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2 as materialization_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HANDOFF_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HANDOFF-CONTRACT-V2"
)
OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HANDOFF_OFFLINE_ONLY"
)
PROTECTED_REQUEST_HANDOFF_PLAN_VERSION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HANDOFF_PLAN_V2"
)
TARGET_CAS_WITNESS_VERSION_V2 = "C3_TARGET_CAS_WITNESS_PROTECTED_V2"
TRANSACTION_IDENTITY_DERIVATION_VERSION_V2 = (
    "C3_V2_TRANSACTION_IDENTITY_DERIVATION_V1"
)
REQUEST_IDENTITY_DERIVATION_VERSION_V2 = "C3_V2_REQUEST_IDENTITY_DERIVATION_V1"
HELD_LEASE_BACKEND_PORT_METHOD_V2 = "apply_under_held_maintenance_lease"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CAS_WITNESS_KEYS = frozenset(
    {
        "witness_version", "materialization_intent_sha256",
        "target_backend_instance_sha256", "target_snapshot_sha256",
        "registry_path_binding_sha256", "lock_namespace_sha256",
        "observed_generation", "observed_raw_document_sha256",
        "maintenance_epoch", "permit_object_identity_sha256",
        "lease_token_sha256", "lease_token_object_identity_sha256",
        "lease_witness_object_identity_sha256", "observed_at_epoch",
        "lease_expires_at_epoch", "snapshot_collected_under_same_lock",
        "raw_document_loaded_under_same_lock", "lease_liveness_validated_at_capture",
        "lock_already_held", "lock_acquisition_count", "synthetic_only",
        "production_authority", "witness_sha256",
    }
)
_IDENTITY_POLICY_KEYS = frozenset(
    {
        "transaction_derivation_version", "request_derivation_version",
        "expected_transaction_sha256", "expected_request_sha256",
        "source_request_sha256", "source_transaction_sha256", "idempotency_key",
        "authorization_receipt_sha256", "target_backend_instance_sha256",
        "target_snapshot_sha256", "maintenance_epoch", "expected_generation",
        "expected_raw_document_sha256", "candidate_raw_document_sha256",
        "deadline_epoch", "request_binding_recomputed_after_materialization",
        "arbitrary_request_identity_forbidden", "arbitrary_transaction_identity_forbidden",
        "policy_sha256",
    }
)
_CAS_CONTRACT_KEYS = frozenset(
    {
        "witness_version", "witness_schema_keys_sha256",
        "same_permit_instance_required", "same_lease_token_instance_required",
        "same_lease_witness_instance_required", "current_time_liveness_required",
        "snapshot_and_raw_document_under_same_lock_required",
        "generation_must_equal_target_snapshot", "raw_hash_must_equal_source_precondition",
        "witness_deadline_bounded_by_request_and_lease", "hash_only_authority_forbidden",
        "witness_materialized", "contract_sha256",
    }
)
_ENVELOPE_CONTRACT_KEYS = frozenset(
    {
        "envelope_type", "raw_mapping_delivery_forbidden",
        "authorization_receipt_sidecar_required", "cas_witness_required",
        "same_object_authority_references_required", "canonical_candidate_bytes_required",
        "candidate_recanonicalization_forbidden", "bare_v2_request_authority",
        "envelope_materialized", "contract_sha256",
    }
)
_PORT_CONTRACT_KEYS = frozenset(
    {
        "port_type", "required_method", "accepted_request_type",
        "accepted_cas_witness_type", "lock_owner", "lock_already_held_required",
        "maximum_acquisition_count", "backend_reacquire_allowed",
        "store_reacquire_allowed", "legacy_self_locking_method_forbidden",
        "release_owner", "default_off", "port_bound", "backend_call_allowed",
        "contract_sha256",
    }
)
_PLAN_KEYS = frozenset(
    {
        "plan_version", "scope_attestation", "materialization_intent_sha256",
        "bridge_plan_sha256", "compatibility_bundle_sha256",
        "v2_request_schema_version", "v2_request_schema_keys_sha256",
        "identity_policy", "cas_witness_contract", "protected_request_envelope_contract",
        "held_lease_backend_port_contract", "deferred_runtime_evidence",
        "identity_derivation_completed", "cas_witness_materialized",
        "request_materialized", "request_binding_materialized",
        "lease_validated_live", "provider_call_allowed", "store_call_allowed",
        "backend_call_allowed", "writer_call_allowed", "lock_acquired",
        "filesystem_accessed", "real_registry_accessed", "network_accessed",
        "broker_called", "write_executed", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "plan_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def protected_request_handoff_policy_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "policy_sha256")


def protected_request_handoff_contract_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "contract_sha256")


def protected_request_handoff_plan_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "plan_sha256")


def target_cas_witness_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "witness_sha256")


def _object_identity_sha(kind: str, value: object) -> str:
    return backend_v2.stable_sha256_v2(
        {"kind": kind, "process_object_identity": id(value)}
    )


def _seal(value: dict[str, Any], key: str) -> dict[str, Any]:
    value[key] = _hash_without(value, key)
    return value


def _sealed(value: Any, keys: frozenset[str], hash_key: str) -> bool:
    return bool(
        type(value) is dict
        and set(value) == keys
        and _valid_sha(value.get(hash_key))
        and hmac.compare_digest(value[hash_key], _hash_without(value, hash_key))
    )


def _transaction_identity_material(
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
) -> dict[str, Any]:
    intent = protected_intent.intent
    authorization = intent["authorization_binding"]
    lease = intent["lease_instance_binding"]
    target = intent["target_binding"]
    candidate = intent["candidate_binding"]
    return {
        "derivation_version": TRANSACTION_IDENTITY_DERIVATION_VERSION_V2,
        "source_request_sha256": candidate["source_request_sha256"],
        "source_transaction_sha256": candidate["source_transaction_sha256"],
        "idempotency_key": candidate["idempotency_key"],
        "authorization_receipt_sha256": authorization[
            "authorization_consumption_receipt_sha256"
        ],
        "target_backend_instance_sha256": target["target_backend_instance_sha256"],
        "target_snapshot_sha256": target["target_snapshot_sha256"],
        "registry_path_binding_sha256": target[
            "target_registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": target["target_lock_namespace_sha256"],
        "maintenance_epoch": lease["maintenance_epoch"],
        "expected_generation": target["target_generation"],
        "expected_raw_document_sha256": candidate["source_raw_document_sha256"],
        "candidate_raw_document_sha256": candidate[
            "candidate_raw_document_sha256"
        ],
    }


def canonical_transaction_sha256_v2(
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> str:
    if not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
        protected_intent, bridge_plan, compatibility_bundle
    ):
        raise ValueError("VALID_PROTECTED_MATERIALIZATION_INTENT_REQUIRED")
    return backend_v2.stable_sha256_v2(_transaction_identity_material(protected_intent))


def _request_identity_material(
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    transaction_sha256: str,
) -> dict[str, Any]:
    intent = protected_intent.intent
    authorization = intent["authorization_binding"]
    lease = intent["lease_instance_binding"]
    target = intent["target_binding"]
    candidate = intent["candidate_binding"]
    deadline = intent["deadline_binding"]
    return {
        "derivation_version": REQUEST_IDENTITY_DERIVATION_VERSION_V2,
        "request_version": backend_v2.TRANSACTION_REQUEST_VERSION_V2,
        "transaction_sha256": transaction_sha256,
        "backend_instance_sha256": target["target_backend_instance_sha256"],
        "backend_snapshot_sha256": target["target_snapshot_sha256"],
        "registry_path_binding_sha256": target[
            "target_registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": target["target_lock_namespace_sha256"],
        "idempotency_key": candidate["idempotency_key"],
        "authorization_receipt_sha256": authorization[
            "authorization_consumption_receipt_sha256"
        ],
        "maintenance_epoch": lease["maintenance_epoch"],
        "expected_generation": target["target_generation"],
        "expected_raw_document_sha256": candidate["source_raw_document_sha256"],
        "candidate_raw_document_sha256": candidate[
            "candidate_raw_document_sha256"
        ],
        "deadline_epoch": deadline["effective_deadline_epoch"],
        "synthetic_only": True,
        "production_authority": False,
    }


def canonical_request_sha256_v2(
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> str:
    transaction_sha = canonical_transaction_sha256_v2(
        protected_intent, bridge_plan, compatibility_bundle
    )
    return backend_v2.stable_sha256_v2(
        _request_identity_material(protected_intent, transaction_sha)
    )


@dataclass(frozen=True, repr=False)
class ProtectedTargetCasWitnessV2:
    maintenance_permit: coordinator_v1.WriterMaintenancePermitV1 = field(repr=False)
    live_lease_token: consumer_v1.ProtectedSyntheticLiveLeaseTokenV1 = field(repr=False)
    lease_witness: consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1 = field(repr=False)
    witness: Mapping[str, Any] = field(repr=False)
    witness_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedTargetCasWitnessV2(<protected>)"


def protected_target_cas_witness_valid_v2(
    value: Any,
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> bool:
    if (
        type(value) is not ProtectedTargetCasWitnessV2
        or not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
            protected_intent, bridge_plan, compatibility_bundle
        )
    ):
        return False
    witness = value.witness
    if not _sealed(witness, _CAS_WITNESS_KEYS, "witness_sha256"):
        return False
    intent = protected_intent.intent
    target = intent["target_binding"]
    candidate = intent["candidate_binding"]
    lease = intent["lease_instance_binding"]
    deadline = intent["deadline_binding"]
    try:
        return bool(
            value.maintenance_permit is protected_intent.maintenance_permit
            and value.live_lease_token is protected_intent.live_lease_token
            and value.lease_witness is protected_intent.lease_witness
            and witness["witness_version"] == TARGET_CAS_WITNESS_VERSION_V2
            and witness["materialization_intent_sha256"]
            == protected_intent.intent_sha256
            and witness["target_backend_instance_sha256"]
            == target["target_backend_instance_sha256"]
            and witness["target_snapshot_sha256"] == target["target_snapshot_sha256"]
            and witness["registry_path_binding_sha256"]
            == target["target_registry_path_binding_sha256"]
            and witness["lock_namespace_sha256"]
            == target["target_lock_namespace_sha256"]
            and witness["observed_generation"] == target["target_generation"]
            and witness["observed_raw_document_sha256"]
            == candidate["source_raw_document_sha256"]
            and witness["maintenance_epoch"] == lease["maintenance_epoch"]
            and witness["permit_object_identity_sha256"]
            == _object_identity_sha(
                "C3_MAINTENANCE_PERMIT_V1", value.maintenance_permit
            )
            and witness["lease_token_sha256"] == value.live_lease_token.token_sha256
            and witness["lease_token_object_identity_sha256"]
            == _object_identity_sha("C3_LIVE_LEASE_TOKEN_V1", value.live_lease_token)
            and witness["lease_witness_object_identity_sha256"]
            == _object_identity_sha("C3_LIVE_LEASE_WITNESS_V1", value.lease_witness)
            and type(witness["observed_at_epoch"]) is int
            and witness["observed_at_epoch"] < deadline["effective_deadline_epoch"]
            and witness["lease_expires_at_epoch"]
            == value.live_lease_token.expires_at_epoch
            and witness["observed_at_epoch"] < witness["lease_expires_at_epoch"]
            and witness["snapshot_collected_under_same_lock"] is True
            and witness["raw_document_loaded_under_same_lock"] is True
            and witness["lease_liveness_validated_at_capture"] is True
            and witness["lock_already_held"] is True
            and witness["lock_acquisition_count"] == 1
            and witness["synthetic_only"] is True
            and witness["production_authority"] is False
            and value.witness_sha256 == witness["witness_sha256"]
        )
    except Exception:
        return False


class HeldMaintenanceLeaseBackendPortV2(Protocol):
    """Shape only; implementations must not acquire or release the shared lock."""

    def apply_under_held_maintenance_lease(
        self,
        protected_request: Any,
        cas_witness: ProtectedTargetCasWitnessV2,
    ) -> Mapping[str, Any]: ...


def _identity_policy(
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> dict[str, Any]:
    intent = protected_intent.intent
    candidate = intent["candidate_binding"]
    authorization = intent["authorization_binding"]
    lease = intent["lease_instance_binding"]
    target = intent["target_binding"]
    deadline = intent["deadline_binding"]
    value = {
        "transaction_derivation_version": TRANSACTION_IDENTITY_DERIVATION_VERSION_V2,
        "request_derivation_version": REQUEST_IDENTITY_DERIVATION_VERSION_V2,
        "expected_transaction_sha256": canonical_transaction_sha256_v2(
            protected_intent, bridge_plan, compatibility_bundle
        ),
        "expected_request_sha256": canonical_request_sha256_v2(
            protected_intent, bridge_plan, compatibility_bundle
        ),
        "source_request_sha256": candidate["source_request_sha256"],
        "source_transaction_sha256": candidate["source_transaction_sha256"],
        "idempotency_key": candidate["idempotency_key"],
        "authorization_receipt_sha256": authorization[
            "authorization_consumption_receipt_sha256"
        ],
        "target_backend_instance_sha256": target["target_backend_instance_sha256"],
        "target_snapshot_sha256": target["target_snapshot_sha256"],
        "maintenance_epoch": lease["maintenance_epoch"],
        "expected_generation": target["target_generation"],
        "expected_raw_document_sha256": candidate["source_raw_document_sha256"],
        "candidate_raw_document_sha256": candidate[
            "candidate_raw_document_sha256"
        ],
        "deadline_epoch": deadline["effective_deadline_epoch"],
        "request_binding_recomputed_after_materialization": True,
        "arbitrary_request_identity_forbidden": True,
        "arbitrary_transaction_identity_forbidden": True,
    }
    return _seal(value, "policy_sha256")


def _cas_contract() -> dict[str, Any]:
    value = {
        "witness_version": TARGET_CAS_WITNESS_VERSION_V2,
        "witness_schema_keys_sha256": backend_v2.stable_sha256_v2(
            sorted(_CAS_WITNESS_KEYS)
        ),
        "same_permit_instance_required": True,
        "same_lease_token_instance_required": True,
        "same_lease_witness_instance_required": True,
        "current_time_liveness_required": True,
        "snapshot_and_raw_document_under_same_lock_required": True,
        "generation_must_equal_target_snapshot": True,
        "raw_hash_must_equal_source_precondition": True,
        "witness_deadline_bounded_by_request_and_lease": True,
        "hash_only_authority_forbidden": True,
        "witness_materialized": False,
    }
    return _seal(value, "contract_sha256")


def _envelope_contract() -> dict[str, Any]:
    value = {
        "envelope_type": "ProtectedMaterializedTransactionRequestV2",
        "raw_mapping_delivery_forbidden": True,
        "authorization_receipt_sidecar_required": True,
        "cas_witness_required": True,
        "same_object_authority_references_required": True,
        "canonical_candidate_bytes_required": True,
        "candidate_recanonicalization_forbidden": True,
        "bare_v2_request_authority": False,
        "envelope_materialized": False,
    }
    return _seal(value, "contract_sha256")


def _port_contract() -> dict[str, Any]:
    value = {
        "port_type": "HeldMaintenanceLeaseBackendPortV2",
        "required_method": HELD_LEASE_BACKEND_PORT_METHOD_V2,
        "accepted_request_type": "ProtectedMaterializedTransactionRequestV2",
        "accepted_cas_witness_type": "ProtectedTargetCasWitnessV2",
        "lock_owner": "COORDINATOR_MAINTENANCE_LEASE",
        "lock_already_held_required": True,
        "maximum_acquisition_count": 1,
        "backend_reacquire_allowed": False,
        "store_reacquire_allowed": False,
        "legacy_self_locking_method_forbidden": "apply_attested_transaction_offline",
        "release_owner": "COORDINATOR_CONTEXT_EXIT",
        "default_off": True,
        "port_bound": False,
        "backend_call_allowed": False,
    }
    return _seal(value, "contract_sha256")


@dataclass(frozen=True, repr=False)
class ProtectedRequestHandoffPlanV2:
    materialization_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent = field(repr=False)
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan = field(repr=False)
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2 = field(repr=False)
    plan: Mapping[str, Any] = field(repr=False)
    plan_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedRequestHandoffPlanV2(<protected>)"


@dataclass(frozen=True)
class DormantProtectedRequestHandoffConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_materialization_intent_sha256: str | None = field(
        default=None, repr=False
    )


def protected_request_handoff_plan_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedRequestHandoffPlanV2:
        return False
    if not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
        value.materialization_intent, value.bridge_plan, value.compatibility_bundle
    ):
        return False
    plan = value.plan
    if type(plan) is not dict or set(plan) != _PLAN_KEYS:
        return False
    identity = plan.get("identity_policy")
    cas = plan.get("cas_witness_contract")
    envelope = plan.get("protected_request_envelope_contract")
    port = plan.get("held_lease_backend_port_contract")
    try:
        return bool(
            _sealed(identity, _IDENTITY_POLICY_KEYS, "policy_sha256")
            and identity
            == _identity_policy(
                value.materialization_intent,
                value.bridge_plan,
                value.compatibility_bundle,
            )
            and _sealed(cas, _CAS_CONTRACT_KEYS, "contract_sha256")
            and cas == _cas_contract()
            and _sealed(envelope, _ENVELOPE_CONTRACT_KEYS, "contract_sha256")
            and envelope == _envelope_contract()
            and _sealed(port, _PORT_CONTRACT_KEYS, "contract_sha256")
            and port == _port_contract()
            and plan["plan_version"] == PROTECTED_REQUEST_HANDOFF_PLAN_VERSION_V2
            and plan["scope_attestation"]
            == OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2
            and plan["materialization_intent_sha256"]
            == value.materialization_intent.intent_sha256
            and plan["bridge_plan_sha256"] == value.bridge_plan.plan_sha256
            and plan["compatibility_bundle_sha256"]
            == value.compatibility_bundle.bundle_sha256
            and plan["v2_request_schema_version"]
            == backend_v2.TRANSACTION_REQUEST_VERSION_V2
            and plan["v2_request_schema_keys_sha256"]
            == backend_v2.stable_sha256_v2(sorted(backend_v2._TRANSACTION_REQUEST_KEYS))
            and plan["deferred_runtime_evidence"] == [
                "CURRENT_TIME_SAME_INSTANCE_LEASE_VALIDATION",
                "TARGET_SNAPSHOT_AND_RAW_DOCUMENT_CAPTURED_UNDER_HELD_LOCK",
                "TYPED_TARGET_CAS_WITNESS",
                "CANONICAL_CANDIDATE_UTF8_MATERIALIZATION_ONCE",
                "PROTECTED_V2_REQUEST_ENVELOPE",
                "NON_REENTRANT_HELD_LEASE_BACKEND_PORT",
                "DURABLE_AUTHORIZATION_LEDGER_CONFIRMATION",
            ]
            and plan["identity_derivation_completed"] is True
            and all(
                plan[key] is False
                for key in (
                    "cas_witness_materialized", "request_materialized",
                    "request_binding_materialized", "lease_validated_live",
                    "provider_call_allowed", "store_call_allowed",
                    "backend_call_allowed", "writer_call_allowed", "lock_acquired",
                    "filesystem_accessed", "real_registry_accessed",
                    "network_accessed", "broker_called", "write_executed",
                    "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and plan["synthetic_only"] is True
            and value.plan_sha256 == plan["plan_sha256"]
            and _valid_sha(plan["plan_sha256"])
            and hmac.compare_digest(
                plan["plan_sha256"], protected_request_handoff_plan_sha256_v2(plan)
            )
        )
    except Exception:
        return False


class DormantProtectedRequestHandoffContractV2:
    def __init__(self, config: DormantProtectedRequestHandoffConfigV2 | None = None) -> None:
        self._config = config or DormantProtectedRequestHandoffConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_REQUEST_HANDOFF_V2_BLOCKED",
            "reason": reason,
            "protected_plan": None,
            "identity_derivation_completed": False,
            "cas_witness_materialized": False,
            "request_materialized": False,
            "request_binding_materialized": False,
            "lease_validated_live": False,
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

    def plan_offline(
        self,
        protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
        bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan,
        compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("PROTECTED_REQUEST_HANDOFF_V2_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2:
            return self._failed("PROTECTED_REQUEST_HANDOFF_V2_SCOPE_REQUIRED")
        if not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
            protected_intent, bridge_plan, compatibility_bundle
        ):
            return self._failed("PROTECTED_MATERIALIZATION_INTENT_INVALID")
        if not (
            _valid_sha(self._config.expected_materialization_intent_sha256)
            and hmac.compare_digest(
                str(self._config.expected_materialization_intent_sha256),
                protected_intent.intent_sha256,
            )
        ):
            return self._failed("PROTECTED_MATERIALIZATION_INTENT_PIN_MISMATCH")
        plan = {
            "plan_version": PROTECTED_REQUEST_HANDOFF_PLAN_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2,
            "materialization_intent_sha256": protected_intent.intent_sha256,
            "bridge_plan_sha256": bridge_plan.plan_sha256,
            "compatibility_bundle_sha256": compatibility_bundle.bundle_sha256,
            "v2_request_schema_version": backend_v2.TRANSACTION_REQUEST_VERSION_V2,
            "v2_request_schema_keys_sha256": backend_v2.stable_sha256_v2(
                sorted(backend_v2._TRANSACTION_REQUEST_KEYS)
            ),
            "identity_policy": _identity_policy(
                protected_intent, bridge_plan, compatibility_bundle
            ),
            "cas_witness_contract": _cas_contract(),
            "protected_request_envelope_contract": _envelope_contract(),
            "held_lease_backend_port_contract": _port_contract(),
            "deferred_runtime_evidence": [
                "CURRENT_TIME_SAME_INSTANCE_LEASE_VALIDATION",
                "TARGET_SNAPSHOT_AND_RAW_DOCUMENT_CAPTURED_UNDER_HELD_LOCK",
                "TYPED_TARGET_CAS_WITNESS",
                "CANONICAL_CANDIDATE_UTF8_MATERIALIZATION_ONCE",
                "PROTECTED_V2_REQUEST_ENVELOPE",
                "NON_REENTRANT_HELD_LEASE_BACKEND_PORT",
                "DURABLE_AUTHORIZATION_LEDGER_CONFIRMATION",
            ],
            "identity_derivation_completed": True,
            "cas_witness_materialized": False,
            "request_materialized": False,
            "request_binding_materialized": False,
            "lease_validated_live": False,
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
        plan["plan_sha256"] = protected_request_handoff_plan_sha256_v2(plan)
        protected = ProtectedRequestHandoffPlanV2(
            materialization_intent=protected_intent,
            bridge_plan=bridge_plan,
            compatibility_bundle=compatibility_bundle,
            plan=copy.deepcopy(plan),
            plan_sha256=plan["plan_sha256"],
        )
        if not protected_request_handoff_plan_valid_v2(protected):
            return self._failed("PROTECTED_REQUEST_HANDOFF_V2_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_REQUEST_HANDOFF_V2_PLANNED_OFFLINE",
                "reason": None,
                "protected_plan": protected,
                "plan_sha256": protected.plan_sha256,
                "expected_transaction_sha256": plan["identity_policy"][
                    "expected_transaction_sha256"
                ],
                "expected_request_sha256": plan["identity_policy"][
                    "expected_request_sha256"
                ],
                "identity_derivation_completed": True,
            }
        )
        return result


__all__ = [
    "DormantProtectedRequestHandoffConfigV2",
    "DormantProtectedRequestHandoffContractV2",
    "HELD_LEASE_BACKEND_PORT_METHOD_V2",
    "HeldMaintenanceLeaseBackendPortV2",
    "OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2",
    "ProtectedRequestHandoffPlanV2",
    "ProtectedTargetCasWitnessV2",
    "TARGET_CAS_WITNESS_VERSION_V2",
    "canonical_request_sha256_v2",
    "canonical_transaction_sha256_v2",
    "protected_request_handoff_contract_sha256_v2",
    "protected_request_handoff_plan_sha256_v2",
    "protected_request_handoff_plan_valid_v2",
    "protected_request_handoff_policy_sha256_v2",
    "protected_target_cas_witness_valid_v2",
    "target_cas_witness_sha256_v2",
]
