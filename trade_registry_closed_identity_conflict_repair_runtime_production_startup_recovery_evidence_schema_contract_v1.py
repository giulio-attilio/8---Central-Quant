"""Dormant schema contract for future production startup-recovery evidence.

This module defines the exact evidence fields and safety invariants that a
future authenticated production implementation must satisfy.  It accepts only
an offline protected identity projection and emits no operational evidence,
authority, provider callable, backend callable, or runtime integration.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as provider_store_binding
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as provider_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SCHEMA-CONTRACT-V1"
)
OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_OFFLINE_ONLY_V1"
)
PROTECTED_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1 = (
    "C3_PROTECTED_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_DORMANT_V1"
)
FUTURE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_VERSION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_FUTURE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PENDING_STATES = ("PREPARED", "RESOLVED")
_TERMINAL_STATES = ("COMMITTED", "ABORTED", "ROLLED_BACK")
_BACKEND_SNAPSHOT_FIELDS = (
    "snapshot_version",
    "schema_sha256",
    "provider_binding_sha256",
    "backend_instance_sha256",
    "backend_module_source_sha256",
    "registry_path_binding_sha256",
    "wal_storage_binding_sha256",
    "resolved_ledger_storage_binding_sha256",
    "lock_namespace_sha256",
    "backend_capability_attestation_sha256",
    "backend_capability_probe_receipt_sha256",
    "generation",
    "observed_at_epoch",
    "durable",
    "production_evidence",
    "authenticated_authority_receipt_sha256",
    "snapshot_sha256",
)
_TRANSACTION_LOG_AUDIT_FIELDS = (
    "audit_version",
    "schema_sha256",
    "backend_instance_sha256",
    "backend_snapshot_sha256",
    "wal_storage_binding_sha256",
    "resolved_ledger_storage_binding_sha256",
    "lock_namespace_sha256",
    "wal_record_count",
    "transaction_count",
    "state_counts",
    "latest_state_counts",
    "unresolved_prepared_count",
    "unresolved_resolved_count",
    "hash_chain_head_sha256",
    "wal_integrity_verified",
    "catalog_crosscheck_verified",
    "fsync_capability_verified",
    "durable",
    "production_evidence",
    "authenticated_authority_receipt_sha256",
    "audit_sha256",
)
_PREPARED_CATALOG_FIELDS = (
    "catalog_version",
    "schema_sha256",
    "backend_instance_sha256",
    "backend_snapshot_sha256",
    "registry_path_binding_sha256",
    "wal_storage_binding_sha256",
    "lock_namespace_sha256",
    "generation",
    "records",
    "record_count",
    "prepared_count",
    "complete_scan_verified",
    "durable",
    "production_evidence",
    "authenticated_authority_receipt_sha256",
    "catalog_sha256",
)
_PREPARED_RECORD_FIELDS = (
    "record_version",
    "transaction_sha256",
    "request_sha256",
    "prepared_record_sha256",
    "source_raw_document_sha256",
    "candidate_raw_document_sha256",
    "previous_maintenance_epoch",
    "prepared_at_epoch",
    "deadline_epoch",
    "state",
    "record_sha256",
)
_RESOLVED_CATALOG_FIELDS = (
    "catalog_version",
    "schema_sha256",
    "backend_instance_sha256",
    "backend_snapshot_sha256",
    "resolved_ledger_storage_binding_sha256",
    "lock_namespace_sha256",
    "generation",
    "records",
    "record_count",
    "resolved_count",
    "complete_scan_verified",
    "durable",
    "production_evidence",
    "authenticated_authority_receipt_sha256",
    "catalog_sha256",
)
_RESOLVED_RECORD_FIELDS = (
    "record_version",
    "obligation_sha256",
    "transaction_sha256",
    "resolution_receipt_sha256",
    "terminal_result_sha256",
    "resolved_at_epoch",
    "projection_committed",
    "state",
    "record_sha256",
)
_TERMINAL_RECEIPT_FIELDS = (
    "receipt_version",
    "schema_sha256",
    "provider_binding_sha256",
    "backend_instance_sha256",
    "transaction_sha256",
    "source_state",
    "terminal_state",
    "maintenance_epoch",
    "previous_maintenance_epoch",
    "backend_result_sha256",
    "write_state_known",
    "write_executed",
    "registry_write",
    "completed_at_epoch",
    "durable",
    "production_evidence",
    "authenticated_authority_receipt_sha256",
    "receipt_sha256",
)
_COMPLETION_ATTESTATION_FIELDS = (
    "evidence_version",
    "schema_sha256",
    "provider_binding_sha256",
    "backend_instance_sha256",
    "registry_path_binding_sha256",
    "wal_storage_binding_sha256",
    "resolved_ledger_storage_binding_sha256",
    "lock_namespace_sha256",
    "maintenance_epoch",
    "maintenance_lease_receipt_sha256",
    "initial_backend_snapshot_sha256",
    "initial_transaction_log_audit_sha256",
    "initial_prepared_catalog_sha256",
    "initial_resolved_catalog_sha256",
    "final_backend_snapshot_sha256",
    "final_transaction_log_audit_sha256",
    "final_prepared_catalog_sha256",
    "final_resolved_catalog_sha256",
    "terminal_receipt_set_sha256",
    "prepared_transactions_before",
    "resolved_transactions_before",
    "prepared_transactions_after",
    "resolved_transactions_after",
    "unresolved_transactions_after",
    "writers_blocked_entire_window",
    "same_maintenance_epoch_used",
    "fresh_maintenance_epoch_verified",
    "all_catalogs_drained",
    "wal_integrity_verified",
    "durability_verified",
    "authenticated_authority_verified",
    "write_state_known",
    "write_executed",
    "registry_write",
    "real_registry_accessed",
    "network_accessed",
    "broker_called",
    "no_order_sent",
    "production_evidence",
    "runtime_admissible",
    "startup_recovery_attestation_sha256",
)
_REQUIRED_AUTHENTICATED_PROOFS = (
    "AUTHENTICATED_BACKEND_INSTANCE",
    "AUTHENTICATED_REGISTRY_PATH_BINDING",
    "EMPIRICAL_DURABILITY_CAPABILITY_PROBES",
    "COMPLETE_HASH_CHAINED_WAL_SCAN",
    "COMPLETE_PREPARED_CATALOG_SCAN",
    "COMPLETE_RESOLVED_LEDGER_SCAN",
    "FRESH_SAME_INSTANCE_MAINTENANCE_LEASE",
    "TERMINAL_RECEIPT_FOR_EACH_PENDING_ITEM",
    "FINAL_POST_WRITE_REINSPECTION",
    "KNOWN_WRITE_OUTCOME_OR_CONTINUED_BLOCK",
)
_SAFETY_INVARIANTS = (
    "PROVIDER_BACKEND_AND_EVIDENCE_SHARE_ONE_BACKEND_INSTANCE",
    "PROVIDER_BACKEND_AND_EVIDENCE_SHARE_ONE_REGISTRY_PATH_BINDING",
    "PROVIDER_BACKEND_AND_EVIDENCE_SHARE_ONE_LOCK_NAMESPACE",
    "ALL_RECOVERY_REQUESTS_USE_THE_EXACT_ACQUIRED_MAINTENANCE_EPOCH",
    "FRESH_MAINTENANCE_EPOCH_DIFFERS_FROM_EACH_PREVIOUS_EPOCH",
    "PREPARED_AND_RESOLVED_COUNTS_BOTH_REACH_ZERO",
    "NO_WRITER_IS_ADMITTED_DURING_RECOVERY",
    "UNKNOWN_WRITE_STATE_NEVER_GRANTS_READINESS",
    "SELF_HASHED_EVIDENCE_ALONE_NEVER_PROVES_AUTHORITY",
    "LIVE_REMAINS_FORBIDDEN_UNTIL_EXTERNAL_AUTHENTICATED_VERIFICATION",
)
_SCHEMA_KEYS = frozenset(
    {
        "schema_version",
        "scope_attestation",
        "future_evidence_version",
        "provider_binding_sha256",
        "source_provider_version",
        "source_store_version",
        "source_provider_snapshot_sha256",
        "source_composition_attestation_sha256",
        "source_backend_instance_sha256",
        "source_registry_path_binding_sha256",
        "source_backend_capability_declaration_sha256",
        "source_lock_namespace_sha256",
        "backend_snapshot_fields",
        "transaction_log_audit_fields",
        "prepared_catalog_fields",
        "prepared_record_fields",
        "resolved_catalog_fields",
        "resolved_record_fields",
        "terminal_receipt_fields",
        "completion_attestation_fields",
        "pending_states",
        "terminal_states",
        "required_authenticated_proofs",
        "safety_invariants",
        "same_backend_instance_required",
        "same_registry_path_binding_required",
        "same_lock_namespace_required",
        "same_maintenance_epoch_instance_required",
        "fresh_maintenance_epoch_required",
        "prepared_and_resolved_catalogs_required",
        "authenticated_verifier_required",
        "empirical_capability_probe_required",
        "schema_only",
        "evidence_builder_available",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "live_allowed",
        "synthetic_projection_only",
        "schema_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "PRODUCTION_EVIDENCE_BUILDER_NOT_IMPLEMENTED",
    "AUTHENTICATED_PRODUCTION_AUTHORITY_VERIFIER_NOT_IMPLEMENTED",
    "EMPIRICAL_PRODUCTION_BACKEND_PROBES_NOT_IMPLEMENTED",
    "PRODUCTION_WAL_AND_PREPARED_CATALOG_PORT_NOT_IMPLEMENTED",
    "PRODUCTION_RESOLVED_LEDGER_PORT_NOT_IMPLEMENTED",
    "PRODUCTION_BACKEND_INSTANCE_BINDING_NOT_VERIFIED",
    "STARTUP_RECOVERY_RUNTIME_INTEGRATION_NOT_IMPLEMENTED",
    "READINESS_AND_LIVE_REMAIN_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def production_startup_recovery_evidence_schema_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("schema must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "schema_sha256"}
    )


@dataclass(frozen=True)
class DormantProductionStartupRecoveryEvidenceSchemaConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_provider_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedProductionStartupRecoveryEvidenceSchemaV1:
    provider_binding_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    schema: Mapping[str, Any] = field(repr=False)
    schema_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionStartupRecoveryEvidenceSchemaV1(<protected>)"


def protected_production_startup_recovery_evidence_schema_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedProductionStartupRecoveryEvidenceSchemaV1
    ):
        return False
    schema = value.schema
    if type(schema) is not dict or set(schema) != _SCHEMA_KEYS:
        return False
    supplied_sha = _valid_sha256(schema.get("schema_sha256"))
    try:
        return bool(
            schema.get("schema_version")
            == PROTECTED_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1
            and schema.get("scope_attestation")
            == OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1
            and schema.get("future_evidence_version")
            == FUTURE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_VERSION_V1
            and all(
                _valid_sha256(schema.get(field_name))
                for field_name in (
                    "provider_binding_sha256",
                    "source_provider_snapshot_sha256",
                    "source_composition_attestation_sha256",
                    "source_backend_instance_sha256",
                    "source_registry_path_binding_sha256",
                    "source_backend_capability_declaration_sha256",
                    "source_lock_namespace_sha256",
                )
            )
            and schema.get("provider_binding_sha256")
            == value.provider_binding_sha256
            and schema.get("source_backend_instance_sha256")
            == value.backend_instance_sha256
            and schema.get("source_provider_version")
            == provider_store_binding.EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1
            and schema.get("source_store_version")
            == provider_store_binding.EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1
            and schema.get("backend_snapshot_fields")
            == list(_BACKEND_SNAPSHOT_FIELDS)
            and schema.get("transaction_log_audit_fields")
            == list(_TRANSACTION_LOG_AUDIT_FIELDS)
            and schema.get("prepared_catalog_fields")
            == list(_PREPARED_CATALOG_FIELDS)
            and schema.get("prepared_record_fields")
            == list(_PREPARED_RECORD_FIELDS)
            and schema.get("resolved_catalog_fields")
            == list(_RESOLVED_CATALOG_FIELDS)
            and schema.get("resolved_record_fields")
            == list(_RESOLVED_RECORD_FIELDS)
            and schema.get("terminal_receipt_fields")
            == list(_TERMINAL_RECEIPT_FIELDS)
            and schema.get("completion_attestation_fields")
            == list(_COMPLETION_ATTESTATION_FIELDS)
            and schema.get("pending_states") == list(_PENDING_STATES)
            and schema.get("terminal_states") == list(_TERMINAL_STATES)
            and schema.get("required_authenticated_proofs")
            == list(_REQUIRED_AUTHENTICATED_PROOFS)
            and schema.get("safety_invariants") == list(_SAFETY_INVARIANTS)
            and schema.get("same_backend_instance_required") is True
            and schema.get("same_registry_path_binding_required") is True
            and schema.get("same_lock_namespace_required") is True
            and schema.get("same_maintenance_epoch_instance_required") is True
            and schema.get("fresh_maintenance_epoch_required") is True
            and schema.get("prepared_and_resolved_catalogs_required") is True
            and schema.get("authenticated_verifier_required") is True
            and schema.get("empirical_capability_probe_required") is True
            and schema.get("schema_only") is True
            and schema.get("evidence_builder_available") is False
            and schema.get("production_authority") is False
            and schema.get("production_ready") is False
            and schema.get("runtime_integrated") is False
            and schema.get("recovery_execution_allowed") is False
            and schema.get("live_allowed") is False
            and schema.get("synthetic_projection_only") is True
            and supplied_sha
            and supplied_sha == value.schema_sha256
            and hmac.compare_digest(
                supplied_sha,
                production_startup_recovery_evidence_schema_sha256_v1(schema),
            )
        )
    except Exception:
        return False


class DormantProductionStartupRecoveryEvidenceSchemaContractV1:
    def __init__(
        self,
        *,
        config: DormantProductionStartupRecoveryEvidenceSchemaConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config or DormantProductionStartupRecoveryEvidenceSchemaConfigV1()
        )

    def __repr__(self) -> str:
        return "DormantProductionStartupRecoveryEvidenceSchemaContractV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "schema_only": True,
            "provider_binding_verified": False,
            "prepared_schema_defined": False,
            "resolved_schema_defined": False,
            "authenticated_proofs_required": True,
            "empirical_capability_probe_required": True,
            "schema_created": False,
            "evidence_created": False,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "reasons": [],
            "protected_schema": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def define_offline(
        self,
        *,
        protected_provider_binding: provider_binding.ProtectedStartupRecoveryProductionProviderBindingV1,
    ) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["reasons"].append(
                "PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_DEFAULT_OFF"
            )
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append(
                "PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_INVALID"
            )
            return result
        expected_binding = _valid_sha256(
            self._config.expected_provider_binding_sha256
        )
        if not (
            expected_binding
            and provider_binding.protected_startup_recovery_production_provider_binding_valid_v1(
                protected_provider_binding
            )
            and hmac.compare_digest(
                protected_provider_binding.binding_sha256, expected_binding
            )
        ):
            result["reasons"].append(
                "PRODUCTION_STARTUP_RECOVERY_PROVIDER_BINDING_INVALID"
            )
            return result
        source = protected_provider_binding.binding
        if not (
            source.get("provider_instance_bound") is False
            and source.get("adapter_instance_bound") is False
            and source.get("direct_port_compatibility_verified") is False
            and source.get("recovery_execution_allowed") is False
            and source.get("production_authority") is False
            and source.get("runtime_integrated") is False
            and source.get("production_ready") is False
            and source.get("synthetic_only") is True
        ):
            result["reasons"].append(
                "PRODUCTION_STARTUP_RECOVERY_SOURCE_SAFETY_VECTOR_INVALID"
            )
            return result
        result["provider_binding_verified"] = True
        schema = {
            "schema_version": PROTECTED_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1,
            "future_evidence_version": FUTURE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_VERSION_V1,
            "provider_binding_sha256": protected_provider_binding.binding_sha256,
            "source_provider_version": source["source_provider_version"],
            "source_store_version": source["source_store_version"],
            "source_provider_snapshot_sha256": source[
                "source_provider_snapshot_sha256"
            ],
            "source_composition_attestation_sha256": source[
                "composition_attestation_sha256"
            ],
            "source_backend_instance_sha256": source[
                "backend_instance_sha256"
            ],
            "source_registry_path_binding_sha256": source[
                "registry_path_binding_sha256"
            ],
            "source_backend_capability_declaration_sha256": source[
                "backend_capability_attestation_sha256"
            ],
            "source_lock_namespace_sha256": source[
                "lock_namespace_sha256"
            ],
            "backend_snapshot_fields": list(_BACKEND_SNAPSHOT_FIELDS),
            "transaction_log_audit_fields": list(
                _TRANSACTION_LOG_AUDIT_FIELDS
            ),
            "prepared_catalog_fields": list(_PREPARED_CATALOG_FIELDS),
            "prepared_record_fields": list(_PREPARED_RECORD_FIELDS),
            "resolved_catalog_fields": list(_RESOLVED_CATALOG_FIELDS),
            "resolved_record_fields": list(_RESOLVED_RECORD_FIELDS),
            "terminal_receipt_fields": list(_TERMINAL_RECEIPT_FIELDS),
            "completion_attestation_fields": list(
                _COMPLETION_ATTESTATION_FIELDS
            ),
            "pending_states": list(_PENDING_STATES),
            "terminal_states": list(_TERMINAL_STATES),
            "required_authenticated_proofs": list(
                _REQUIRED_AUTHENTICATED_PROOFS
            ),
            "safety_invariants": list(_SAFETY_INVARIANTS),
            "same_backend_instance_required": True,
            "same_registry_path_binding_required": True,
            "same_lock_namespace_required": True,
            "same_maintenance_epoch_instance_required": True,
            "fresh_maintenance_epoch_required": True,
            "prepared_and_resolved_catalogs_required": True,
            "authenticated_verifier_required": True,
            "empirical_capability_probe_required": True,
            "schema_only": True,
            "evidence_builder_available": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "live_allowed": False,
            "synthetic_projection_only": True,
        }
        schema["schema_sha256"] = (
            production_startup_recovery_evidence_schema_sha256_v1(schema)
        )
        protected = ProtectedProductionStartupRecoveryEvidenceSchemaV1(
            provider_binding_sha256=schema["provider_binding_sha256"],
            backend_instance_sha256=schema[
                "source_backend_instance_sha256"
            ],
            schema=_canonical_copy(schema),
            schema_sha256=schema["schema_sha256"],
        )
        if not protected_production_startup_recovery_evidence_schema_valid_v1(
            protected
        ):
            result["reasons"].append(
                "PROTECTED_PRODUCTION_RECOVERY_SCHEMA_SELF_CHECK_FAILED"
            )
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_DEFINED_DORMANT",
            prepared_schema_defined=True,
            resolved_schema_defined=True,
            schema_created=True,
            protected_schema=protected,
        )
        return result


__all__ = [
    "DormantProductionStartupRecoveryEvidenceSchemaConfigV1",
    "DormantProductionStartupRecoveryEvidenceSchemaContractV1",
    "FUTURE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_VERSION_V1",
    "OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_SCOPE_ATTESTATION_V1",
    "PROTECTED_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_VERSION_V1",
    "ProtectedProductionStartupRecoveryEvidenceSchemaV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SCHEMA_CONTRACT_V1_VERSION",
    "production_startup_recovery_evidence_schema_sha256_v1",
    "protected_production_startup_recovery_evidence_schema_valid_v1",
]
