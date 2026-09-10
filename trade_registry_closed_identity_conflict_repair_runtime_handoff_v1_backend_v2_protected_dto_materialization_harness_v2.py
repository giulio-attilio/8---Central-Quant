"""Offline harness for the dormant protected V2 DTO materialization intent.

Only synthetic fixtures and protected, non-executable evidence are produced.
No V2 request is materialized and no authorization, provider, store, backend,
writer, runtime seam, network endpoint, or real Registry is invoked.
"""

from __future__ import annotations

import copy
import hmac
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2 as provider_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as compatibility_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2 as compatibility_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2 as materialization_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-DTO-MATERIALIZATION-HARNESS-V2"
)
PROTECTED_DTO_MATERIALIZATION_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_HARNESS_EVIDENCE_V2"
)
DEFAULT_SYNTHETIC_NOW_EPOCH_V2 = 10_000

_CHECK_NAMES = (
    "PROTECTED_INTENT_VALID",
    "AUTHORIZATION_ALREADY_CONSUMED_EXACTLY_ONCE",
    "EXACT_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED",
    "LEASE_LIVENESS_DEFERRED_NOT_INFERRED_FROM_HASH",
    "TARGET_SNAPSHOT_AND_GENERATION_BOUND",
    "CANONICAL_CANDIDATE_HASH_PRESERVED",
    "EFFECTIVE_DEADLINE_BOUNDED",
    "SINGLE_LOCK_OWNER_AND_NO_REACQUISITION",
    "FRESH_RECOVERY_AUTHORITY_REQUIRED",
    "EXECUTABLE_DTOS_NOT_MATERIALIZED",
    "TAMPERED_AUTHORIZATION_REJECTED",
    "SUBSTITUTED_PERMIT_INSTANCE_REJECTED",
    "LOCK_REACQUISITION_ESCALATION_REJECTED",
    "REFERENCE_BACKEND_REUSE_REJECTED",
    "EXPIRED_DEADLINE_REJECTED",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version", "contract_intent_sha256", "bridge_plan_sha256",
        "compatibility_bundle_sha256", "checks", "check_count", "passed_count",
        "authorization_consumed", "lease_validated_live",
        "executable_request_materialized", "executable_recovery_request_materialized",
        "provider_called", "store_called", "backend_called", "writer_called",
        "lock_acquired", "filesystem_accessed_by_materializer",
        "real_registry_accessed", "network_accessed", "broker_called",
        "write_executed", "production_authority", "runtime_integrated",
        "activation_allowed", "live_allowed", "synthetic_only", "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def _evidence_sha(value: Mapping[str, Any]) -> str:
    return _sha({key: item for key, item in value.items() if key != "evidence_sha256"})


def dto_materialization_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _evidence_sha(value)


def _in_memory_provider_store_bundle():
    """Build a sealed synthetic upstream projection without a backend call."""

    snapshot = {
        "snapshot_version": backend_v2.BACKEND_SNAPSHOT_VERSION_V2,
        "backend_kind": "SYNTHETIC_IN_MEMORY_UPSTREAM_PROJECTION",
        "backend_instance_sha256": _sha("in-memory-upstream-backend-instance"),
        "backend_module_source_sha256": _sha("in-memory-upstream-module"),
        "registry_path_binding_sha256": _sha("in-memory-upstream-path"),
        "lock_namespace_sha256": coordinator_v1.canonical_runtime_lock_namespace_v1(),
        "generation": 0,
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
        "filesystem_accessed": True,
    }
    snapshot["snapshot_sha256"] = _sha(snapshot)
    evidence = []
    for capability in backend_v2.REQUIRED_CAPABILITIES_V2:
        item = {
            "evidence_version": backend_v2.CAPABILITY_EVIDENCE_VERSION_V2,
            "capability": capability,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "fixture_binding_sha256": _sha(
                {"synthetic_in_memory_capability": capability}
            ),
            "probe_kind": "TEMPORARY_FILESYSTEM_FAULT_INJECTION",
            "observed": True,
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "filesystem_accessed": True,
        }
        item["evidence_sha256"] = _sha(item)
        evidence.append(item)
    catalog = {
        "catalog_version": backend_v2.PREPARED_CATALOG_VERSION_V2,
        "backend_instance_sha256": snapshot["backend_instance_sha256"],
        "backend_snapshot_sha256": snapshot["snapshot_sha256"],
        "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
        "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
        "generation": snapshot["generation"],
        "records": [],
        "record_count": 0,
        "prepared_count": 0,
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
    }
    catalog["catalog_sha256"] = _sha(catalog)
    manifest = provider_v2.build_immutable_capability_manifest_offline_v2(
        snapshot, evidence
    )
    projector = provider_v2.DormantProviderStoreProjectionV2(
        provider_v2.ProviderStoreProjectionConfigV2(
            enabled=True,
            scope_attestation=provider_v2.OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2,
            expected_backend_snapshot_sha256=snapshot["snapshot_sha256"],
            expected_prepared_catalog_sha256=catalog["catalog_sha256"],
            expected_capability_manifest_sha256=manifest["manifest_sha256"],
        )
    )
    projection = projector.project_offline(
        snapshot=snapshot,
        capability_evidence=evidence,
        prepared_catalog=catalog,
    )
    protected = projection.get("protected_bundle")
    if projection.get("ok") is not True or protected is None:
        raise ValueError("IN_MEMORY_PROVIDER_STORE_PROJECTION_BUILD_FAILED")
    return protected


def _compatibility_for_token(
    fixture: Mapping[str, Any], token_sha256: str
) -> compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2:
    lease = copy.deepcopy(fixture["live_lease_projection"])
    lease["lease_token_sha256"] = token_sha256
    lease["projection_sha256"] = compatibility_v2.compatibility_projection_sha256_v2(
        lease
    )
    result = fixture["binder"].bind_offline(
        provider_store_bundle=fixture["provider_store_bundle"],
        writer_inventory=fixture["writer_inventory"],
        seam_bindings=fixture["seam_bindings"],
        callable_manifest_projection=fixture["callable_manifest_projection"],
        coordinator_projection=fixture["coordinator_projection"],
        maintenance_permit_projection=fixture["maintenance_permit_projection"],
        live_lease_projection=lease,
        lock_ownership_policy=fixture["lock_ownership_policy"],
        now_epoch=fixture["live_lease_projection"]["issued_at_epoch"],
    )
    protected = result.get("protected_bundle")
    if result.get("ok") is not True or protected is None:
        raise ValueError("SYNTHETIC_COMPATIBILITY_BUNDLE_BUILD_FAILED")
    return protected


def _bridge_plan(
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan:
    planner = bridge_v2.DormantHandoffV1BackendV2SchemaBridge(
        bridge_v2.HandoffV1BackendV2SchemaBridgeConfig(
            enabled=True,
            scope_attestation=bridge_v2.OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION,
            expected_compatibility_bundle_sha256=compatibility_bundle.bundle_sha256,
        )
    )
    result = planner.plan_offline(compatibility_bundle)
    protected = result.get("protected_plan")
    if result.get("ok") is not True or protected is None:
        raise ValueError("SYNTHETIC_SCHEMA_BRIDGE_PLAN_BUILD_FAILED")
    return protected


def _source_envelope(
    maintenance_epoch: str,
    registry_path_sha256: str,
    *,
    now_epoch: int,
) -> tuple[envelope_v1.ProtectedProductionInvocationEnvelopeV1, dict[str, Any]]:
    subject_sha = _sha("synthetic-materialization-subject")
    receipt = {
        "receipt_version": "C3_SYNTHETIC_AUTHORIZATION_CONSUMPTION_RECEIPT_V1",
        "grant_sha256": _sha("synthetic-materialization-grant"),
        "subject_binding_sha256": subject_sha,
        "authorized_action": envelope_v1.AUTHORIZATION_ACTION_V1,
        "consumption_count": 1,
        "consumed_at_epoch": now_epoch - 1,
        "expires_at_epoch": now_epoch + 100,
        "synthetic_only": True,
        "production_authority": False,
    }
    receipt["receipt_sha256"] = envelope_v1._stable_sha256(receipt)
    candidate = {"closed_trades": [], "schema_version": "C3_SYNTHETIC_V2"}
    candidate_sha = backend_v2.raw_utf8_sha256_v2(
        envelope_v1._canonical_json(candidate)
    )
    request = {
        "request_version": envelope_v1.PRODUCTION_REQUEST_VERSION_V1,
        "scope_attestation": envelope_v1.PRODUCTION_REQUEST_CONTRACT_ONLY_SCOPE_V1,
        "subject_binding_sha256": subject_sha,
        "authorization_consumption_receipt_sha256": receipt["receipt_sha256"],
        "upstream_raw_transaction_sha256": _sha("synthetic-upstream-raw-transaction"),
        "handoff_transaction_id": "synthetic-handoff-v2-materialization",
        "idempotency_key": _sha("synthetic-materialization-idempotency"),
        "backend_instance_sha256": _sha("synthetic-source-v1-backend"),
        "registry_path_binding_sha256": registry_path_sha256,
        "backend_capability_attestation_sha256": _sha("synthetic-source-capability"),
        "lock_namespace_sha256": coordinator_v1.canonical_runtime_lock_namespace_v1(),
        "maintenance_epoch": maintenance_epoch,
        "expected_raw_document_sha256": _sha("synthetic-source-raw-document"),
        "expected_generation_token": _sha("synthetic-source-generation-token"),
        "candidate_registry": candidate,
        "candidate_raw_document_sha256": candidate_sha,
        "expires_at_epoch": now_epoch + 90,
        "recovery_policy": envelope_v1.PRODUCTION_RECOVERY_POLICY_V1,
        "transaction_sha256": _sha("synthetic-source-v1-transaction"),
    }
    request["request_sha256"] = envelope_v1.production_request_sha256_v1(request)
    envelope_sha = envelope_v1._stable_sha256(
        {
            "subject_binding_sha256": subject_sha,
            "authorization_consumption_receipt_sha256": receipt["receipt_sha256"],
            "upstream_raw_transaction_sha256": request["upstream_raw_transaction_sha256"],
            "production_transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "registry_path_binding_sha256": registry_path_sha256,
            "expires_at_epoch": request["expires_at_epoch"],
            "request_sha256": request["request_sha256"],
        }
    )
    protected = envelope_v1.ProtectedProductionInvocationEnvelopeV1(
        subject_binding_sha256=subject_sha,
        authorization_consumption_receipt_sha256=receipt["receipt_sha256"],
        upstream_raw_transaction_sha256=request["upstream_raw_transaction_sha256"],
        production_transaction_sha256=request["transaction_sha256"],
        backend_instance_sha256=request["backend_instance_sha256"],
        registry_path_binding_sha256=registry_path_sha256,
        expires_at_epoch=request["expires_at_epoch"],
        request=request,
        envelope_sha256=envelope_sha,
    )
    return protected, receipt


def _target_snapshot(
    reference_backend_sha256: str,
    registry_path_sha256: str,
) -> dict[str, Any]:
    value = {
        "snapshot_version": backend_v2.BACKEND_SNAPSHOT_VERSION_V2,
        "backend_kind": "SYNTHETIC_PROTECTED_MATERIALIZATION_TARGET",
        "backend_instance_sha256": _sha(
            {"target": "synthetic-v2", "different_from": reference_backend_sha256}
        ),
        "backend_module_source_sha256": _sha("synthetic-target-module"),
        "registry_path_binding_sha256": registry_path_sha256,
        "lock_namespace_sha256": coordinator_v1.canonical_runtime_lock_namespace_v1(),
        "generation": 7,
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
        "filesystem_accessed": False,
    }
    value["snapshot_sha256"] = _sha(value)
    return value


@contextmanager
def held_protected_dto_materialization_fixture_v2(
    *, now_epoch: int = DEFAULT_SYNTHETIC_NOW_EPOCH_V2
) -> Iterator[dict[str, Any]]:
    """Yield one active, entirely synthetic lease-bound contract fixture."""

    if type(now_epoch) is not int:
        raise ValueError("INTEGER_SYNTHETIC_NOW_EPOCH_REQUIRED")
    provider_bundle = _in_memory_provider_store_bundle()
    compatibility_fixture = (
        compatibility_harness.build_writer_coordination_compatibility_fixture_v2(
            provider_bundle, now_epoch=now_epoch
        )
    )
    permit_projection = compatibility_fixture["maintenance_permit_projection"]
    permit = coordinator_v1.WriterMaintenancePermitV1(
        maintenance_epoch=permit_projection["maintenance_epoch"],
        state="QUIESCED",
        lock_namespace_sha256=coordinator_v1.canonical_runtime_lock_namespace_v1(),
        registered_writer_count=19,
        inflight_mutations=0,
        shared_lock_acquired=True,
    )
    witness = consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1(
        clock=lambda: now_epoch,
        nonce_source=lambda: "protected-materialization-harness-v2",
    )
    registry_path_sha = _sha("synthetic-materialization-target-registry-path")
    with witness.hold_offline(permit, expires_at_epoch=now_epoch + 120) as token:
        compatibility_bundle = _compatibility_for_token(
            compatibility_fixture, token.token_sha256
        )
        bridge_plan = _bridge_plan(compatibility_bundle)
        source_envelope, receipt = _source_envelope(
            permit.maintenance_epoch, registry_path_sha, now_epoch=now_epoch
        )
        snapshot = _target_snapshot(
            bridge_plan.reference_backend_instance_sha256, registry_path_sha
        )
        binder = materialization_v2.DormantBackendV2DtoMaterializationContract(
            materialization_v2.DormantBackendV2DtoMaterializationConfig(
                enabled=True,
                scope_attestation=materialization_v2.OFFLINE_PROTECTED_DTO_MATERIALIZATION_SCOPE_ATTESTATION_V2,
                expected_bridge_plan_sha256=bridge_plan.plan_sha256,
                expected_compatibility_bundle_sha256=compatibility_bundle.bundle_sha256,
                maximum_deadline_seconds=120,
            )
        )
        yield {
            "now_epoch": now_epoch,
            "bridge_plan": bridge_plan,
            "compatibility_bundle": compatibility_bundle,
            "source_envelope": source_envelope,
            "authorization_consumption_receipt": receipt,
            "maintenance_permit": permit,
            "live_lease_token": token,
            "lease_witness": witness,
            "target_snapshot": snapshot,
            "target_backend_capability_attestation_sha256": _sha("synthetic-target-capability"),
            "generation_resolver_evidence_sha256": _sha("synthetic-generation-resolver"),
            "boundary_deadline_epoch": now_epoch + 80,
            "binder": binder,
        }


def bind_protected_dto_materialization_fixture_offline_v2(
    fixture: Mapping[str, Any], *, now_epoch: int | None = None
) -> dict[str, Any]:
    return fixture["binder"].bind_intent_offline(
        bridge_plan=fixture["bridge_plan"],
        compatibility_bundle=fixture["compatibility_bundle"],
        source_envelope=fixture["source_envelope"],
        authorization_consumption_receipt=fixture["authorization_consumption_receipt"],
        maintenance_permit=fixture["maintenance_permit"],
        live_lease_token=fixture["live_lease_token"],
        lease_witness=fixture["lease_witness"],
        target_snapshot=fixture["target_snapshot"],
        target_backend_capability_attestation_sha256=fixture[
            "target_backend_capability_attestation_sha256"
        ],
        generation_resolver_evidence_sha256=fixture[
            "generation_resolver_evidence_sha256"
        ],
        boundary_deadline_epoch=fixture["boundary_deadline_epoch"],
        now_epoch=fixture["now_epoch"] if now_epoch is None else now_epoch,
    )


@dataclass(frozen=True, repr=False)
class ProtectedDtoMaterializationHarnessEvidenceV2:
    protected_intent: materialization_v2.ProtectedBackendV2DtoMaterializationIntent = field(repr=False)
    bridge_plan: bridge_v2.ProtectedHandoffV1BackendV2SchemaBridgePlan = field(repr=False)
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2 = field(repr=False)
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDtoMaterializationHarnessEvidenceV2(<protected>)"


def protected_dto_materialization_harness_evidence_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedDtoMaterializationHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    try:
        return bool(
            materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                value.protected_intent, value.bridge_plan, value.compatibility_bundle
            )
            and evidence["evidence_version"]
            == PROTECTED_DTO_MATERIALIZATION_HARNESS_EVIDENCE_VERSION_V2
            and evidence["contract_intent_sha256"] == value.protected_intent.intent_sha256
            and evidence["bridge_plan_sha256"] == value.bridge_plan.plan_sha256
            and evidence["compatibility_bundle_sha256"]
            == value.compatibility_bundle.bundle_sha256
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(type(item) is dict and set(item) == _CHECK_KEYS and item["passed"] is True for item in checks)
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and all(
                evidence[key] is False
                for key in (
                    "authorization_consumed", "lease_validated_live",
                    "executable_request_materialized",
                    "executable_recovery_request_materialized", "provider_called",
                    "store_called", "backend_called", "writer_called", "lock_acquired",
                    "filesystem_accessed_by_materializer", "real_registry_accessed",
                    "network_accessed", "broker_called", "write_executed",
                    "production_authority", "runtime_integrated", "activation_allowed",
                    "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                dto_materialization_harness_evidence_sha256_v2(evidence),
            )
        )
    except Exception:
        return False


def _tampered_wrapper(
    protected: materialization_v2.ProtectedBackendV2DtoMaterializationIntent,
    *,
    receipt: Mapping[str, Any] | None = None,
    permit: coordinator_v1.WriterMaintenancePermitV1 | None = None,
    snapshot: Mapping[str, Any] | None = None,
    intent: Mapping[str, Any] | None = None,
) -> materialization_v2.ProtectedBackendV2DtoMaterializationIntent:
    return materialization_v2.ProtectedBackendV2DtoMaterializationIntent(
        source_envelope=protected.source_envelope,
        authorization_consumption_receipt=(
            protected.authorization_consumption_receipt if receipt is None else receipt
        ),
        maintenance_permit=protected.maintenance_permit if permit is None else permit,
        live_lease_token=protected.live_lease_token,
        lease_witness=protected.lease_witness,
        target_snapshot=protected.target_snapshot if snapshot is None else snapshot,
        intent=protected.intent if intent is None else intent,
        intent_sha256=(protected.intent_sha256 if intent is None else intent["intent_sha256"]),
    )


def run_protected_dto_materialization_harness_v2(
    *, now_epoch: int = DEFAULT_SYNTHETIC_NOW_EPOCH_V2
) -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_DTO_MATERIALIZATION_HARNESS_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_DTO_MATERIALIZATION_HARNESS_V2_VERSION,
        "protected_intent": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "authorization_consumed": False,
        "lease_validated_live": False,
        "executable_request_materialized": False,
        "executable_recovery_request_materialized": False,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "filesystem_accessed_by_materializer": False,
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
        with held_protected_dto_materialization_fixture_v2(now_epoch=now_epoch) as fixture:
            result = bind_protected_dto_materialization_fixture_offline_v2(fixture)
            protected = result.get("protected_intent")
            if result.get("ok") is not True or protected is None:
                base["reason"] = "PROTECTED_INTENT_BIND_FAILED"
                return base
            bridge_plan = fixture["bridge_plan"]
            compatibility_bundle = fixture["compatibility_bundle"]
            intent = protected.intent
            receipt = copy.deepcopy(dict(protected.authorization_consumption_receipt))
            receipt["consumption_count"] = 2
            tampered_authorization_rejected = not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                _tampered_wrapper(protected, receipt=receipt), bridge_plan, compatibility_bundle
            )
            substituted_permit_rejected = not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                _tampered_wrapper(protected, permit=copy.copy(protected.maintenance_permit)),
                bridge_plan,
                compatibility_bundle,
            )
            lock_intent = copy.deepcopy(dict(intent))
            lock_intent["lock_handoff_policy"]["backend_reacquire_allowed"] = True
            lock_intent["lock_handoff_policy"]["binding_sha256"] = (
                materialization_v2.materialization_binding_sha256_v2(
                    lock_intent["lock_handoff_policy"]
                )
            )
            lock_intent["intent_sha256"] = materialization_v2.materialization_intent_sha256_v2(
                lock_intent
            )
            lock_escalation_rejected = not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                _tampered_wrapper(protected, intent=lock_intent), bridge_plan, compatibility_bundle
            )
            snapshot = copy.deepcopy(dict(protected.target_snapshot))
            snapshot["backend_instance_sha256"] = bridge_plan.reference_backend_instance_sha256
            snapshot["snapshot_sha256"] = _sha(
                {key: item for key, item in snapshot.items() if key != "snapshot_sha256"}
            )
            reference_reuse_rejected = not materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                _tampered_wrapper(protected, snapshot=snapshot), bridge_plan, compatibility_bundle
            )
            expired_result = bind_protected_dto_materialization_fixture_offline_v2(
                fixture, now_epoch=fixture["source_envelope"].expires_at_epoch
            )
            expired_deadline_rejected = bool(
                expired_result.get("ok") is False
                and expired_result.get("reason")
                == "AUTHORIZATION_OR_EFFECTIVE_DEADLINE_EXPIRED"
            )
            authority = intent["authorization_binding"]
            lease = intent["lease_instance_binding"]
            target = intent["target_binding"]
            candidate = intent["candidate_binding"]
            deadline = intent["deadline_binding"]
            lock = intent["lock_handoff_policy"]
            recovery = intent["recovery_policy"]
            checks_by_name = {
                "PROTECTED_INTENT_VALID": materialization_v2.protected_backend_v2_dto_materialization_intent_valid(
                    protected, bridge_plan, compatibility_bundle
                ),
                "AUTHORIZATION_ALREADY_CONSUMED_EXACTLY_ONCE": authority["already_consumed_upstream"] is True and authority["consumption_count"] == 1 and intent["authorization_consumption_allowed"] is False,
                "EXACT_PERMIT_TOKEN_WITNESS_INSTANCES_RETAINED": protected.maintenance_permit is fixture["maintenance_permit"] and protected.live_lease_token is fixture["live_lease_token"] and protected.lease_witness is fixture["lease_witness"] and lease["same_object_instances_retained"] is True,
                "LEASE_LIVENESS_DEFERRED_NOT_INFERRED_FROM_HASH": lease["hash_projection_is_not_live_authority"] is True and lease["current_time_liveness_revalidation_required"] is True and intent["lease_validated_live"] is False,
                "TARGET_SNAPSHOT_AND_GENERATION_BOUND": target["target_snapshot_sha256"] == protected.target_snapshot["snapshot_sha256"] and target["target_generation"] == protected.target_snapshot["generation"],
                "CANONICAL_CANDIDATE_HASH_PRESERVED": candidate["candidate_raw_document_sha256"] == candidate["canonical_candidate_utf8_sha256"] and candidate["canonicalization_count"] == 1,
                "EFFECTIVE_DEADLINE_BOUNDED": deadline["observed_at_epoch"] < deadline["effective_deadline_epoch"] <= deadline["observed_at_epoch"] + 120,
                "SINGLE_LOCK_OWNER_AND_NO_REACQUISITION": lock["maximum_acquisition_count"] == 1 and lock["lock_already_held_by_permit"] is True and lock["backend_reacquire_allowed"] is False and lock["store_reacquire_allowed"] is False,
                "FRESH_RECOVERY_AUTHORITY_REQUIRED": recovery["fresh_permit_required"] is True and recovery["fresh_lease_required"] is True and recovery["separate_single_use_authorization_required"] is True and recovery["request_materialization_deferred"] is True,
                "EXECUTABLE_DTOS_NOT_MATERIALIZED": intent["request_materialized"] is False and intent["recovery_request_materialized"] is False,
                "TAMPERED_AUTHORIZATION_REJECTED": tampered_authorization_rejected,
                "SUBSTITUTED_PERMIT_INSTANCE_REJECTED": substituted_permit_rejected,
                "LOCK_REACQUISITION_ESCALATION_REJECTED": lock_escalation_rejected,
                "REFERENCE_BACKEND_REUSE_REJECTED": reference_reuse_rejected,
                "EXPIRED_DEADLINE_REJECTED": expired_deadline_rejected,
            }
            checks = [
                {"name": name, "passed": checks_by_name[name] is True}
                for name in _CHECK_NAMES
            ]
            if not all(item["passed"] for item in checks):
                base["reason"] = "PROTECTED_DTO_MATERIALIZATION_ORACLE_FAILED"
                return base
            evidence = {
                "evidence_version": PROTECTED_DTO_MATERIALIZATION_HARNESS_EVIDENCE_VERSION_V2,
                "contract_intent_sha256": protected.intent_sha256,
                "bridge_plan_sha256": bridge_plan.plan_sha256,
                "compatibility_bundle_sha256": compatibility_bundle.bundle_sha256,
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "authorization_consumed": False,
                "lease_validated_live": False,
                "executable_request_materialized": False,
                "executable_recovery_request_materialized": False,
                "provider_called": False,
                "store_called": False,
                "backend_called": False,
                "writer_called": False,
                "lock_acquired": False,
                "filesystem_accessed_by_materializer": False,
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
                dto_materialization_harness_evidence_sha256_v2(evidence)
            )
            protected_evidence = ProtectedDtoMaterializationHarnessEvidenceV2(
                protected_intent=protected,
                bridge_plan=bridge_plan,
                compatibility_bundle=compatibility_bundle,
                evidence=copy.deepcopy(evidence),
                evidence_sha256=evidence["evidence_sha256"],
            )
            if not protected_dto_materialization_harness_evidence_valid_v2(
                protected_evidence
            ):
                base["reason"] = "PROTECTED_HARNESS_EVIDENCE_INTERNAL_INVALID"
                return base
    except Exception:
        base["reason"] = "PROTECTED_DTO_MATERIALIZATION_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_DTO_MATERIALIZATION_HARNESS_PASSED_OFFLINE",
            "protected_intent": protected,
            "protected_evidence": protected_evidence,
            "intent_sha256": protected.intent_sha256,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
        }
    )
    return base


__all__ = [
    "ProtectedDtoMaterializationHarnessEvidenceV2",
    "bind_protected_dto_materialization_fixture_offline_v2",
    "dto_materialization_harness_evidence_sha256_v2",
    "held_protected_dto_materialization_fixture_v2",
    "protected_dto_materialization_harness_evidence_valid_v2",
    "run_protected_dto_materialization_harness_v2",
]
