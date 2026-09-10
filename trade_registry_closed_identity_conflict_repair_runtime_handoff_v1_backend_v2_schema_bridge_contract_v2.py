"""Dormant schema bridge contract between the V1 handoff and V2 backend.

This module emits a protected translation plan only.  It never builds a
transaction request, validates a live lease, consumes authorization, calls a
provider/store/backend, acquires a lock, or accesses the Registry.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as compatibility_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-SCHEMA-BRIDGE-CONTRACT-V2"
)
OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION = (
    "C3_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_OFFLINE_ONLY"
)
SCHEMA_BINDING_VERSION = "C3_HANDOFF_V1_BACKEND_V2_SCHEMA_BINDING_V1"
BRIDGE_PLAN_VERSION = "C3_HANDOFF_V1_BACKEND_V2_BRIDGE_PLAN_PROTECTED_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAPPING_KEYS = frozenset(
    {"source", "target", "rule", "required_at_execution"}
)
_SCHEMA_KEYS = frozenset(
    {
        "binding_version", "v1_apply_schema_version", "v1_apply_keys_sha256",
        "v1_terminal_schema_version", "v1_terminal_keys_sha256",
        "v1_recovery_schema_version", "v1_recovery_keys_sha256",
        "v2_apply_schema_version", "v2_apply_keys_sha256",
        "v2_terminal_schema_version", "v2_terminal_keys_sha256",
        "v2_recovery_schema_version", "v2_recovery_keys_sha256",
        "v1_boundary_command_schema_version", "v1_boundary_command_keys_sha256",
        "schema_binding_sha256",
    }
)
_IDENTITY_KEYS = frozenset(
    {
        "reference_backend_instance_sha256", "canonical_lock_namespace_sha256",
        "production_backend_instance_required",
        "production_backend_must_differ_from_reference",
        "production_registry_path_must_be_rebound",
        "production_capability_attestation_required",
        "reference_capability_not_production_evidence",
        "temporary_identity_reuse_forbidden", "policy_sha256",
    }
)
_AUTHORIZATION_KEYS = frozenset(
    {
        "apply_authorization_source", "apply_authorization_target",
        "apply_consumption_count", "authorization_bound_to_subject",
        "generic_hash_substitution_forbidden", "durable_runtime_ledger_required",
        "recovery_authorization_separate", "recovery_consumption_count",
        "production_signature_required_for_runtime", "production_authority",
        "policy_sha256",
    }
)
_PERMIT_KEYS = frozenset(
    {
        "apply_permit_type", "apply_lease_token_type",
        "same_permit_instance_required", "same_lease_witness_required",
        "current_time_liveness_revalidation_required",
        "hash_projection_is_not_live_authority", "fresh_recovery_permit_required",
        "fresh_recovery_lease_required", "fresh_recovery_epoch_required",
        "recovery_epoch_must_differ", "registered_writer_count",
        "inflight_mutations_required", "shared_lock_required",
        "policy_sha256",
    }
)
_DEADLINE_KEYS = frozenset(
    {
        "effective_deadline_rule", "maximum_seconds", "revalidate_at_each_layer",
        "reject_expired_before_translation", "reject_expired_before_call",
        "recovery_uses_fresh_deadline", "policy_sha256",
    }
)
_BUNDLE_KEYS = frozenset(
    {
        "bridge_plan_version", "scope_attestation",
        "source_compatibility_bundle_sha256",
        "source_compatibility_binding_sha256",
        "reference_backend_instance_sha256", "lock_namespace_sha256",
        "schema_binding", "apply_field_mapping", "terminal_field_mapping",
        "recovery_field_mapping", "identity_policy", "authorization_policy",
        "permit_lease_policy", "deadline_policy",
        "upstream_lock_ownership_policy_sha256", "deferred_runtime_evidence",
        "schema_bridge_verified", "translation_executed",
        "runtime_bridge_bound", "provider_call_allowed", "store_call_allowed",
        "backend_call_allowed", "authorization_consumption_allowed",
        "lease_validation_authority", "production_authority",
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


def schema_binding_sha256(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "schema_binding_sha256")


def bridge_policy_sha256(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "policy_sha256")


def bridge_plan_sha256(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "plan_sha256")


def _mapping(
    source: str, target: str, rule: str, *, required: bool = True
) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "rule": rule,
        "required_at_execution": required,
    }


def canonical_apply_field_mapping() -> list[dict[str, Any]]:
    return [
        _mapping("v1.request_version", "v2.request_version", "TRANSLATE_SCHEMA_CONSTANT"),
        _mapping("v1.backend_instance_sha256", "v2.backend_instance_sha256", "REBIND_TO_TARGET_V2_SNAPSHOT"),
        _mapping("v1.none", "v2.backend_snapshot_sha256", "REQUIRE_FRESH_TARGET_V2_SNAPSHOT"),
        _mapping("v1.registry_path_binding_sha256", "v2.registry_path_binding_sha256", "REBIND_AND_PROVE_TARGET_PATH"),
        _mapping("v1.lock_namespace_sha256", "v2.lock_namespace_sha256", "PRESERVE_EXACT"),
        _mapping("v1.request_sha256", "v2.request_sha256", "RECOMPUTE_V2_AND_BIND_ORIGINAL_IN_BRIDGE_RECEIPT"),
        _mapping("v1.transaction_sha256", "v2.transaction_sha256", "RECOMPUTE_V2_AND_BIND_ORIGINAL_IN_BRIDGE_RECEIPT"),
        _mapping("v1.idempotency_key", "v2.idempotency_key", "PRESERVE_EXACT"),
        _mapping("v1.authorization_consumption_receipt_sha256", "v2.authorization_receipt_sha256", "PRESERVE_EXACT_SINGLE_USE_RECEIPT"),
        _mapping("v1.maintenance_epoch", "v2.maintenance_epoch", "PRESERVE_EXACT_FROM_LIVE_PERMIT"),
        _mapping("v1.expected_generation_token", "v2.expected_generation", "RESOLVE_AND_PROVE_TARGET_V2_GENERATION"),
        _mapping("v1.expected_raw_document_sha256", "v2.expected_raw_document_sha256", "PRESERVE_EXACT"),
        _mapping("v1.candidate_registry", "v2.candidate_raw_document_utf8", "CANONICALIZE_UTF8_ONCE"),
        _mapping("v1.candidate_raw_document_sha256", "v2.candidate_raw_document_sha256", "PRESERVE_AND_REVERIFY_UTF8"),
        _mapping("v1.expires_at_epoch", "v2.deadline_epoch", "MINIMUM_EFFECTIVE_DEADLINE"),
        _mapping("v1.synthetic_contract", "v2.synthetic_only", "FORCE_TRUE"),
        _mapping("v1.production_authority", "v2.production_authority", "FORCE_FALSE"),
        _mapping("v1.none", "v2.request_binding_sha256", "RECOMPUTE_EXACT_V2_SCHEMA"),
        _mapping("v1.subject_binding_sha256", "bridge.sidecar.subject_binding_sha256", "PRESERVE_EXACT"),
        _mapping("v1.upstream_raw_transaction_sha256", "bridge.sidecar.upstream_raw_transaction_sha256", "PRESERVE_EXACT"),
        _mapping("v1.handoff_transaction_id", "bridge.sidecar.handoff_transaction_id", "PRESERVE_EXACT"),
    ]


def canonical_terminal_field_mapping() -> list[dict[str, Any]]:
    return [
        _mapping("v2.result_version", "v1.result_version", "TRANSLATE_SCHEMA_CONSTANT"),
        _mapping("bridge.execution_scope", "v1.execution_scope", "REQUIRE_EXPLICIT_RUNTIME_SCOPE"),
        _mapping("v2.result_sha256", "bridge.sidecar.backend_result_sha256", "PRESERVE_EXACT"),
        _mapping("bridge.apply.request_sha256", "v1.request_sha256", "RESTORE_ORIGINAL_V1_IDENTITY"),
        _mapping("bridge.apply.transaction_sha256", "v1.transaction_sha256", "RESTORE_ORIGINAL_V1_IDENTITY"),
        _mapping("bridge.apply.backend_instance_sha256", "v1.backend_instance_sha256", "RESTORE_TARGET_PRODUCTION_IDENTITY"),
        _mapping("bridge.apply.authorization_receipt_sha256", "v1.authorization_consumption_receipt_sha256", "PRESERVE_EXACT"),
        _mapping("bridge.apply.maintenance_epoch", "v1.maintenance_epoch", "PRESERVE_EXACT"),
        _mapping("bridge.apply.source_raw_document_sha256", "v1.source_raw_document_sha256", "PRESERVE_EXACT"),
        _mapping("bridge.apply.candidate_raw_document_sha256", "v1.candidate_raw_document_sha256", "PRESERVE_EXACT"),
        _mapping("v2.terminal_state", "v1.terminal_state", "PRESERVE_ENUM"),
        _mapping("v2.prepared_record_sha256", "v1.prepared_record_sha256", "PRESERVE_EXACT"),
        _mapping("v2.terminal_record_sha256", "v1.terminal_record_sha256", "PRESERVE_EXACT"),
        _mapping("v2.postconditions_verified", "v1.postconditions_verified", "PRESERVE_EXACT"),
        _mapping("v2.recovery_required", "v1.recovery_required", "PRESERVE_EXACT"),
        _mapping("v2.terminal_state", "v1.ambiguous", "DERIVE_TRUE_ONLY_FOR_AMBIGUOUS"),
        _mapping("bridge.runtime_observation", "v1.production_evidence", "NEVER_PROMOTE_SYNTHETIC_EVIDENCE"),
        _mapping("v2.write_executed", "v1.write_executed", "PRESERVE_EXACT"),
        _mapping("v2.registry_write", "v1.registry_write", "PRESERVE_EXACT"),
        _mapping("bridge.idempotency_evidence", "v1.idempotent_replay", "REQUIRE_EXPLICIT_EVIDENCE"),
        _mapping("v1.terminal_material", "v1.result_sha256", "RECOMPUTE_EXACT_V1_SCHEMA"),
    ]


def canonical_recovery_field_mapping() -> list[dict[str, Any]]:
    return [
        _mapping("v1.recovery_request_version", "v2.request_version", "TRANSLATE_SCHEMA_CONSTANT"),
        _mapping("v1.original_request_sha256", "v2.original_request_sha256", "PRESERVE_EXACT"),
        _mapping("bridge.original_invocation_command_sha256", "v2.original_invocation_command_sha256", "PRESERVE_EXACT"),
        _mapping("v1.authorization_consumption_receipt_sha256", "v2.original_authorization_receipt_sha256", "PRESERVE_EXACT"),
        _mapping("bridge.recovery_authorization_consumption_receipt_sha256", "v2.recovery_authorization_receipt_sha256", "REQUIRE_SEPARATE_SINGLE_USE_RECEIPT"),
        _mapping("v1.transaction_sha256", "v2.transaction_sha256", "PRESERVE_V2_TRANSACTION_ID_FROM_APPLY_BRIDGE"),
        _mapping("v1.backend_instance_sha256", "v2.backend_instance_sha256", "REBIND_TO_FRESH_TARGET_V2_SNAPSHOT"),
        _mapping("v1.none", "v2.backend_snapshot_sha256", "REQUIRE_FRESH_TARGET_V2_SNAPSHOT"),
        _mapping("v1.registry_path_binding_sha256", "v2.registry_path_binding_sha256", "REBIND_AND_PROVE_TARGET_PATH"),
        _mapping("bridge.apply.lock_namespace_sha256", "v2.lock_namespace_sha256", "PRESERVE_EXACT"),
        _mapping("v1.source_raw_document_sha256", "v2.source_raw_document_sha256", "PRESERVE_EXACT"),
        _mapping("v1.candidate_raw_document_sha256", "v2.candidate_raw_document_sha256", "PRESERVE_EXACT"),
        _mapping("v1.previous_maintenance_epoch", "v2.previous_maintenance_epoch", "PRESERVE_EXACT"),
        _mapping("v1.fresh_maintenance_epoch", "v2.fresh_maintenance_epoch", "PRESERVE_EXACT_FROM_FRESH_LIVE_PERMIT"),
        _mapping("v1.expires_at_epoch", "v2.deadline_epoch", "MINIMUM_FRESH_EFFECTIVE_DEADLINE"),
        _mapping("bridge.prepared_record_sha256", "v2.prepared_record_sha256", "REQUIRE_PREPARED_CATALOG_EVIDENCE"),
        _mapping("bridge.wal_prepared_record_sha256", "v2.wal_prepared_record_sha256", "REQUIRE_WAL_EVIDENCE"),
        _mapping("bridge.batch_epoch", "v2.batch_epoch", "REQUIRE_FRESH_BATCH"),
        _mapping("bridge.batch_plan_sha256", "v2.batch_plan_sha256", "REQUIRE_FRESH_BATCH"),
        _mapping("bridge.catalog_sha256", "v2.catalog_sha256", "REQUIRE_FRESH_PREPARED_CATALOG"),
        _mapping("bridge.checkpoint_index", "v2.checkpoint_index", "REQUIRE_RESUMABLE_CHECKPOINT"),
        _mapping("v1.synthetic_only", "v2.synthetic_only", "FORCE_TRUE"),
        _mapping("v1.production_authority", "v2.production_authority", "FORCE_FALSE"),
        _mapping("v1.recovery_request_sha256", "v2.request_sha256", "RECOMPUTE_V2_AND_BIND_ORIGINAL_IN_BRIDGE_RECEIPT"),
    ]


def _sealed_policy(value: Any, keys: frozenset[str]) -> bool:
    return bool(
        type(value) is dict
        and set(value) == keys
        and _valid_sha(value.get("policy_sha256"))
        and hmac.compare_digest(
            value["policy_sha256"], bridge_policy_sha256(value)
        )
    )


def _schema_binding() -> dict[str, Any]:
    value = {
        "binding_version": SCHEMA_BINDING_VERSION,
        "v1_apply_schema_version": envelope_v1.PRODUCTION_REQUEST_VERSION_V1,
        "v1_apply_keys_sha256": backend_v2.stable_sha256_v2(sorted(envelope_v1._PRODUCTION_REQUEST_KEYS)),
        "v1_terminal_schema_version": envelope_v1.PRODUCTION_RESULT_VERSION_V1,
        "v1_terminal_keys_sha256": backend_v2.stable_sha256_v2(sorted(envelope_v1._TERMINAL_RESULT_KEYS)),
        "v1_recovery_schema_version": envelope_v1.PRODUCTION_RECOVERY_REQUEST_VERSION_V1,
        "v1_recovery_keys_sha256": backend_v2.stable_sha256_v2(sorted(envelope_v1._RECOVERY_REQUEST_KEYS)),
        "v2_apply_schema_version": backend_v2.TRANSACTION_REQUEST_VERSION_V2,
        "v2_apply_keys_sha256": backend_v2.stable_sha256_v2(sorted(backend_v2._TRANSACTION_REQUEST_KEYS)),
        "v2_terminal_schema_version": backend_v2.TRANSACTION_RESULT_VERSION_V2,
        "v2_terminal_keys_sha256": backend_v2.stable_sha256_v2(sorted(backend_v2._TRANSACTION_RESULT_KEYS)),
        "v2_recovery_schema_version": backend_v2.RECOVERY_REQUEST_VERSION_V2,
        "v2_recovery_keys_sha256": backend_v2.stable_sha256_v2(sorted(backend_v2._RECOVERY_REQUEST_KEYS)),
        "v1_boundary_command_schema_version": boundary_v1.PRODUCTION_BACKEND_INVOCATION_COMMAND_VERSION_V1,
        "v1_boundary_command_keys_sha256": backend_v2.stable_sha256_v2(sorted(boundary_v1._INVOCATION_COMMAND_KEYS)),
    }
    value["schema_binding_sha256"] = schema_binding_sha256(value)
    return value


def _identity_policy(reference_backend_sha: str, namespace: str) -> dict[str, Any]:
    value = {
        "reference_backend_instance_sha256": reference_backend_sha,
        "canonical_lock_namespace_sha256": namespace,
        "production_backend_instance_required": True,
        "production_backend_must_differ_from_reference": True,
        "production_registry_path_must_be_rebound": True,
        "production_capability_attestation_required": True,
        "reference_capability_not_production_evidence": True,
        "temporary_identity_reuse_forbidden": True,
    }
    value["policy_sha256"] = bridge_policy_sha256(value)
    return value


def _authorization_policy() -> dict[str, Any]:
    value = {
        "apply_authorization_source": "V1_AUTHORIZATION_CONSUMPTION_RECEIPT_SHA256",
        "apply_authorization_target": "V2_AUTHORIZATION_RECEIPT_SHA256",
        "apply_consumption_count": 1,
        "authorization_bound_to_subject": True,
        "generic_hash_substitution_forbidden": True,
        "durable_runtime_ledger_required": True,
        "recovery_authorization_separate": True,
        "recovery_consumption_count": 1,
        "production_signature_required_for_runtime": True,
        "production_authority": False,
    }
    value["policy_sha256"] = bridge_policy_sha256(value)
    return value


def _permit_policy() -> dict[str, Any]:
    value = {
        "apply_permit_type": "WriterMaintenancePermitV1",
        "apply_lease_token_type": "ProtectedSyntheticLiveLeaseTokenV1",
        "same_permit_instance_required": True,
        "same_lease_witness_required": True,
        "current_time_liveness_revalidation_required": True,
        "hash_projection_is_not_live_authority": True,
        "fresh_recovery_permit_required": True,
        "fresh_recovery_lease_required": True,
        "fresh_recovery_epoch_required": True,
        "recovery_epoch_must_differ": True,
        "registered_writer_count": 19,
        "inflight_mutations_required": 0,
        "shared_lock_required": True,
    }
    value["policy_sha256"] = bridge_policy_sha256(value)
    return value


def _deadline_policy() -> dict[str, Any]:
    value = {
        "effective_deadline_rule": "MIN(ENVELOPE,LEASE,BOUNDARY,MAX_300_SECONDS)",
        "maximum_seconds": 300,
        "revalidate_at_each_layer": True,
        "reject_expired_before_translation": True,
        "reject_expired_before_call": True,
        "recovery_uses_fresh_deadline": True,
    }
    value["policy_sha256"] = bridge_policy_sha256(value)
    return value


def _mapping_valid(value: Any, expected: list[dict[str, Any]]) -> bool:
    return bool(
        isinstance(value, list)
        and value == expected
        and all(type(item) is dict and set(item) == _MAPPING_KEYS for item in value)
    )


@dataclass(frozen=True, repr=False)
class ProtectedHandoffV1BackendV2SchemaBridgePlan:
    source_compatibility_bundle_sha256: str = field(repr=False)
    reference_backend_instance_sha256: str = field(repr=False)
    plan: Mapping[str, Any] = field(repr=False)
    plan_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHandoffV1BackendV2SchemaBridgePlan(<protected>)"


@dataclass(frozen=True)
class HandoffV1BackendV2SchemaBridgeConfig:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_compatibility_bundle_sha256: str | None = field(default=None, repr=False)


def protected_schema_bridge_plan_valid(value: Any) -> bool:
    if not isinstance(value, ProtectedHandoffV1BackendV2SchemaBridgePlan):
        return False
    plan = value.plan
    if type(plan) is not dict or set(plan) != _BUNDLE_KEYS:
        return False
    schema = plan.get("schema_binding")
    identity = plan.get("identity_policy")
    authorization = plan.get("authorization_policy")
    permit = plan.get("permit_lease_policy")
    deadline = plan.get("deadline_policy")
    try:
        return bool(
            plan["bridge_plan_version"] == BRIDGE_PLAN_VERSION
            and plan["scope_attestation"] == OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION
            and type(schema) is dict
            and set(schema) == _SCHEMA_KEYS
            and schema == _schema_binding()
            and _valid_sha(schema["schema_binding_sha256"])
            and hmac.compare_digest(schema["schema_binding_sha256"], schema_binding_sha256(schema))
            and _mapping_valid(plan["apply_field_mapping"], canonical_apply_field_mapping())
            and _mapping_valid(plan["terminal_field_mapping"], canonical_terminal_field_mapping())
            and _mapping_valid(plan["recovery_field_mapping"], canonical_recovery_field_mapping())
            and _sealed_policy(identity, _IDENTITY_KEYS)
            and identity == _identity_policy(plan["reference_backend_instance_sha256"], plan["lock_namespace_sha256"])
            and _sealed_policy(authorization, _AUTHORIZATION_KEYS)
            and authorization == _authorization_policy()
            and _sealed_policy(permit, _PERMIT_KEYS)
            and permit == _permit_policy()
            and _sealed_policy(deadline, _DEADLINE_KEYS)
            and deadline == _deadline_policy()
            and plan["lock_namespace_sha256"] == coordinator_v1.canonical_runtime_lock_namespace_v1()
            and _valid_sha(plan["source_compatibility_bundle_sha256"])
            and _valid_sha(plan["source_compatibility_binding_sha256"])
            and _valid_sha(plan["reference_backend_instance_sha256"])
            and _valid_sha(plan["upstream_lock_ownership_policy_sha256"])
            and plan["deferred_runtime_evidence"] == [
                "DISTINCT_PRODUCTION_BACKEND_INSTANCE",
                "PRODUCTION_REGISTRY_PATH_BINDING",
                "PRODUCTION_BACKEND_CAPABILITY_ATTESTATION",
                "SAME_INSTANCE_LIVE_MAINTENANCE_PERMIT_AND_LEASE",
                "DURABLE_SINGLE_USE_APPLY_AUTHORIZATION_CONSUMPTION",
                "FRESH_TARGET_V2_SNAPSHOT_AND_GENERATION",
                "FRESH_RECOVERY_PERMIT_LEASE_AND_AUTHORIZATION",
                "V2_TO_V1_TERMINAL_RECEIPT_NORMALIZATION",
            ]
            and plan["schema_bridge_verified"] is True
            and all(
                plan[key] is False
                for key in (
                    "translation_executed", "runtime_bridge_bound",
                    "provider_call_allowed", "store_call_allowed",
                    "backend_call_allowed", "authorization_consumption_allowed",
                    "lease_validation_authority", "production_authority",
                    "runtime_integrated", "activation_allowed", "live_allowed",
                )
            )
            and plan["synthetic_only"] is True
            and value.source_compatibility_bundle_sha256 == plan["source_compatibility_bundle_sha256"]
            and value.reference_backend_instance_sha256 == plan["reference_backend_instance_sha256"]
            and value.plan_sha256 == plan["plan_sha256"]
            and _valid_sha(plan["plan_sha256"])
            and hmac.compare_digest(plan["plan_sha256"], bridge_plan_sha256(plan))
        )
    except Exception:
        return False


class DormantHandoffV1BackendV2SchemaBridge:
    def __init__(self, config: HandoffV1BackendV2SchemaBridgeConfig | None = None) -> None:
        self._config = config or HandoffV1BackendV2SchemaBridgeConfig()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_BLOCKED",
            "reason": reason,
            "protected_plan": None,
            "schema_bridge_verified": False,
            "translation_executed": False,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "authorization_consumed": False,
            "lease_validated_live": False,
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
        compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION:
            return self._failed("HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_REQUIRED")
        if not compatibility_v2.protected_writer_coordination_compatibility_bundle_valid_v2(
            compatibility_bundle
        ):
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_BUNDLE_V2_INVALID")
        if not (
            _valid_sha(self._config.expected_compatibility_bundle_sha256)
            and hmac.compare_digest(
                str(self._config.expected_compatibility_bundle_sha256),
                compatibility_bundle.bundle_sha256,
            )
        ):
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_BUNDLE_V2_PIN_MISMATCH")
        source = compatibility_bundle.bundle["compatibility_binding"]
        upstream_lock_policy = compatibility_bundle.bundle["lock_ownership_policy"]
        reference_backend_sha = source["backend_instance_sha256"]
        namespace = source["lock_namespace_sha256"]
        plan = {
            "bridge_plan_version": BRIDGE_PLAN_VERSION,
            "scope_attestation": OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION,
            "source_compatibility_bundle_sha256": compatibility_bundle.bundle_sha256,
            "source_compatibility_binding_sha256": source["binding_sha256"],
            "reference_backend_instance_sha256": reference_backend_sha,
            "lock_namespace_sha256": namespace,
            "schema_binding": _schema_binding(),
            "apply_field_mapping": canonical_apply_field_mapping(),
            "terminal_field_mapping": canonical_terminal_field_mapping(),
            "recovery_field_mapping": canonical_recovery_field_mapping(),
            "identity_policy": _identity_policy(reference_backend_sha, namespace),
            "authorization_policy": _authorization_policy(),
            "permit_lease_policy": _permit_policy(),
            "deadline_policy": _deadline_policy(),
            "upstream_lock_ownership_policy_sha256": upstream_lock_policy["policy_sha256"],
            "deferred_runtime_evidence": [
                "DISTINCT_PRODUCTION_BACKEND_INSTANCE",
                "PRODUCTION_REGISTRY_PATH_BINDING",
                "PRODUCTION_BACKEND_CAPABILITY_ATTESTATION",
                "SAME_INSTANCE_LIVE_MAINTENANCE_PERMIT_AND_LEASE",
                "DURABLE_SINGLE_USE_APPLY_AUTHORIZATION_CONSUMPTION",
                "FRESH_TARGET_V2_SNAPSHOT_AND_GENERATION",
                "FRESH_RECOVERY_PERMIT_LEASE_AND_AUTHORIZATION",
                "V2_TO_V1_TERMINAL_RECEIPT_NORMALIZATION",
            ],
            "schema_bridge_verified": True,
            "translation_executed": False,
            "runtime_bridge_bound": False,
            "provider_call_allowed": False,
            "store_call_allowed": False,
            "backend_call_allowed": False,
            "authorization_consumption_allowed": False,
            "lease_validation_authority": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        plan["plan_sha256"] = bridge_plan_sha256(plan)
        protected = ProtectedHandoffV1BackendV2SchemaBridgePlan(
            source_compatibility_bundle_sha256=compatibility_bundle.bundle_sha256,
            reference_backend_instance_sha256=reference_backend_sha,
            plan=copy.deepcopy(plan),
            plan_sha256=plan["plan_sha256"],
        )
        if not protected_schema_bridge_plan_valid(protected):
            return self._failed("HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_PLANNED_OFFLINE",
                "reason": None,
                "protected_plan": protected,
                "plan_sha256": protected.plan_sha256,
                "schema_bridge_verified": True,
                "apply_mapping_count": len(plan["apply_field_mapping"]),
                "terminal_mapping_count": len(plan["terminal_field_mapping"]),
                "recovery_mapping_count": len(plan["recovery_field_mapping"]),
                "deferred_runtime_evidence_count": len(plan["deferred_runtime_evidence"]),
            }
        )
        return result


__all__ = [
    "DormantHandoffV1BackendV2SchemaBridge",
    "HandoffV1BackendV2SchemaBridgeConfig",
    "OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION",
    "ProtectedHandoffV1BackendV2SchemaBridgePlan",
    "bridge_plan_sha256",
    "canonical_apply_field_mapping",
    "canonical_recovery_field_mapping",
    "canonical_terminal_field_mapping",
    "protected_schema_bridge_plan_valid",
]
