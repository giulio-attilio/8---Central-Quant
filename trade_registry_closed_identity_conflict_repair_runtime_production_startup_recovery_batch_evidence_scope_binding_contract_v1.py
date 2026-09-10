"""Dormant binding from batch-session authority to recovery-evidence scope.

This module only projects already-protected synthetic identities.  It does not
build evidence, inspect a backend, touch the Registry, validate a live lease,
or grant recovery/runtime/production authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_contract_v1 as batch_authority_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1 as evidence_schema_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-BATCH-EVIDENCE-SCOPE-BINDING-CONTRACT-V1"
)
OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "batch_session_receipt_sha256",
        "authenticated_authority_binding_sha256",
        "candidate_authenticated_authority_receipt_sha256",
        "schema_sha256",
        "future_evidence_version",
        "provider_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "durable_root_identity_sha256",
        "durable_storage_binding_sha256",
        "maintenance_epoch",
        "candidate_maintenance_lease_receipt_sha256",
        "pending_catalog_binding_sha256",
        "pending_items",
        "pending_item_count",
        "prepared_transactions",
        "resolved_transactions",
        "transaction_set_sha256",
        "terminal_receipt_transaction_set_sha256",
        "same_schema_verified",
        "same_provider_binding_verified",
        "same_backend_instance_verified",
        "same_registry_path_binding_verified",
        "same_lock_namespace_verified",
        "exact_maintenance_epoch_required",
        "exact_maintenance_lease_receipt_required",
        "exact_authenticated_authority_receipt_required",
        "exact_pending_catalog_crosscheck_required",
        "complete_initial_catalogs_required",
        "terminal_receipt_per_pending_item_required",
        "final_catalog_drain_required",
        "live_lease_revalidation_required",
        "durable_current_state_revalidation_required",
        "external_authenticated_verification_required",
        "empirical_durability_verification_required",
        "storage_bindings_projected_not_schema_authenticated",
        "batch_scope_bound",
        "evidence_created",
        "evidence_builder_called",
        "evidence_population_allowed",
        "recovery_authority_granted",
        "production_blockers",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "registry_write",
        "no_order_sent",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "binding_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "SCOPE_BINDING_IS_SYNTHETIC_AND_NOT_PRODUCTION_SIGNED",
    "LIVE_MAINTENANCE_LEASE_REVALIDATION_NOT_IMPLEMENTED",
    "DURABLE_AUTHORITY_CURRENT_STATE_REVALIDATION_NOT_IMPLEMENTED",
    "COMPLETE_INITIAL_PREPARED_AND_RESOLVED_CATALOGS_NOT_ATTACHED",
    "PENDING_CATALOG_TO_INITIAL_CATALOG_CROSSCHECK_NOT_EXECUTED",
    "TERMINAL_RECEIPTS_NOT_ATTACHED",
    "FINAL_CATALOG_DRAIN_NOT_VERIFIED",
    "AUTHENTICATED_PRODUCTION_AUTHORITY_NOT_VERIFIED",
    "EMPIRICAL_DURABILITY_NOT_VERIFIED",
    "EVIDENCE_BUILDER_AND_RUNTIME_INTEGRATION_REMAIN_FORBIDDEN",
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


def startup_recovery_batch_evidence_scope_binding_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("scope binding must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


@dataclass(frozen=True)
class DormantStartupRecoveryBatchEvidenceScopeBindingConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_batch_session_receipt_sha256: str | None = field(
        default=None, repr=False
    )
    expected_schema_sha256: str | None = field(default=None, repr=False)
    expected_pending_catalog_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryBatchEvidenceScopeBindingV1:
    protected_batch_session: batch_authority_v1.ProtectedStartupRecoveryBatchSessionAuthorityV1 = field(
        repr=False
    )
    protected_evidence_schema: evidence_schema_v1.ProtectedProductionStartupRecoveryEvidenceSchemaV1 = field(
        repr=False
    )
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryBatchEvidenceScopeBindingV1(<protected>)"


def _source_identity_matches(
    protected_batch_session: batch_authority_v1.ProtectedStartupRecoveryBatchSessionAuthorityV1,
    protected_evidence_schema: evidence_schema_v1.ProtectedProductionStartupRecoveryEvidenceSchemaV1,
) -> bool:
    receipt = protected_batch_session.receipt
    schema = protected_evidence_schema.schema
    authenticated = protected_batch_session.authenticated_authority_binding.binding
    try:
        return bool(
            receipt["schema_sha256"] == protected_evidence_schema.schema_sha256
            == schema["schema_sha256"]
            and receipt["provider_binding_sha256"]
            == protected_evidence_schema.provider_binding_sha256
            == schema["provider_binding_sha256"]
            and receipt["backend_instance_sha256"]
            == protected_evidence_schema.backend_instance_sha256
            == schema["source_backend_instance_sha256"]
            and receipt["registry_path_binding_sha256"]
            == schema["source_registry_path_binding_sha256"]
            and receipt["lock_namespace_sha256"]
            == schema["source_lock_namespace_sha256"]
            and receipt["authenticated_authority_binding_sha256"]
            == protected_batch_session.authenticated_authority_binding.binding_sha256
            and receipt["candidate_maintenance_lease_receipt_sha256"]
            == authenticated["maintenance_lease_receipt_sha256"]
            and receipt["maintenance_epoch"] == authenticated["maintenance_epoch"]
        )
    except Exception:
        return False


def protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryBatchEvidenceScopeBindingV1
    ):
        return False
    if not (
        batch_authority_v1.protected_startup_recovery_batch_session_authority_valid_v1(
            value.protected_batch_session
        )
        and evidence_schema_v1.protected_production_startup_recovery_evidence_schema_valid_v1(
            value.protected_evidence_schema
        )
        and _source_identity_matches(
            value.protected_batch_session, value.protected_evidence_schema
        )
    ):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    receipt = value.protected_batch_session.receipt
    schema = value.protected_evidence_schema.schema
    authenticated = value.protected_batch_session.authenticated_authority_binding.binding
    pending_items = receipt["pending_items"]
    prepared = sorted(
        item["transaction_sha256"]
        for item in pending_items
        if item["source_state"] == "PREPARED"
    )
    resolved = sorted(
        item["transaction_sha256"]
        for item in pending_items
        if item["source_state"] == "RESOLVED"
    )
    try:
        return bool(
            binding["binding_version"]
            == PROTECTED_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_VERSION_V1
            and binding["scope_attestation"]
            == OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1
            and binding["batch_session_receipt_sha256"]
            == value.protected_batch_session.receipt_sha256
            and binding["authenticated_authority_binding_sha256"]
            == receipt["authenticated_authority_binding_sha256"]
            and binding["candidate_authenticated_authority_receipt_sha256"]
            == authenticated["candidate_authenticated_authority_receipt_sha256"]
            and binding["schema_sha256"] == schema["schema_sha256"]
            and binding["future_evidence_version"]
            == schema["future_evidence_version"]
            and binding["provider_binding_sha256"]
            == receipt["provider_binding_sha256"]
            and binding["backend_instance_sha256"]
            == receipt["backend_instance_sha256"]
            and binding["registry_path_binding_sha256"]
            == receipt["registry_path_binding_sha256"]
            and binding["wal_storage_binding_sha256"]
            == receipt["wal_storage_binding_sha256"]
            and binding["resolved_ledger_storage_binding_sha256"]
            == receipt["resolved_ledger_storage_binding_sha256"]
            and binding["lock_namespace_sha256"]
            == receipt["lock_namespace_sha256"]
            and binding["durable_root_identity_sha256"]
            == receipt["durable_root_identity_sha256"]
            and binding["durable_storage_binding_sha256"]
            == receipt["durable_storage_binding_sha256"]
            and binding["maintenance_epoch"] == receipt["maintenance_epoch"]
            and binding["candidate_maintenance_lease_receipt_sha256"]
            == receipt["candidate_maintenance_lease_receipt_sha256"]
            and binding["pending_catalog_binding_sha256"]
            == receipt["pending_catalog_binding_sha256"]
            and binding["pending_items"] == pending_items
            and binding["pending_item_count"] == len(pending_items)
            and binding["prepared_transactions"] == prepared
            and binding["resolved_transactions"] == resolved
            and binding["transaction_set_sha256"]
            == receipt["transaction_set_sha256"]
            and binding["terminal_receipt_transaction_set_sha256"]
            == receipt["transaction_set_sha256"]
            and all(
                binding[field_name] is True
                for field_name in (
                    "same_schema_verified",
                    "same_provider_binding_verified",
                    "same_backend_instance_verified",
                    "same_registry_path_binding_verified",
                    "same_lock_namespace_verified",
                    "exact_maintenance_epoch_required",
                    "exact_maintenance_lease_receipt_required",
                    "exact_authenticated_authority_receipt_required",
                    "exact_pending_catalog_crosscheck_required",
                    "complete_initial_catalogs_required",
                    "terminal_receipt_per_pending_item_required",
                    "final_catalog_drain_required",
                    "live_lease_revalidation_required",
                    "durable_current_state_revalidation_required",
                    "external_authenticated_verification_required",
                    "empirical_durability_verification_required",
                    "storage_bindings_projected_not_schema_authenticated",
                    "batch_scope_bound",
                    "no_order_sent",
                    "synthetic_only",
                )
            )
            and all(
                binding[field_name] is False
                for field_name in (
                    "evidence_created",
                    "evidence_builder_called",
                    "evidence_population_allowed",
                    "recovery_authority_granted",
                    "filesystem_accessed",
                    "real_registry_accessed",
                    "network_accessed",
                    "broker_called",
                    "write_executed",
                    "registry_write",
                    "production_authority",
                    "production_ready",
                    "runtime_integrated",
                    "recovery_execution_allowed",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and binding["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and value.binding_sha256 == binding["binding_sha256"]
            and _valid_sha256(binding["binding_sha256"])
            and hmac.compare_digest(
                binding["binding_sha256"],
                startup_recovery_batch_evidence_scope_binding_sha256_v1(
                    binding
                ),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryBatchEvidenceScopeBindingContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryBatchEvidenceScopeBindingConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config or DormantStartupRecoveryBatchEvidenceScopeBindingConfigV1()
        )

    def __repr__(self) -> str:
        return "DormantStartupRecoveryBatchEvidenceScopeBindingContractV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "batch_session_verified": False,
            "evidence_schema_verified": False,
            "identity_vector_verified": False,
            "batch_scope_bound": False,
            "evidence_created": False,
            "evidence_builder_called": False,
            "evidence_population_allowed": False,
            "recovery_authority_granted": False,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "writer_called": False,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "reasons": [],
            "protected_scope_binding": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1
        ):
            return "STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                self._config.expected_batch_session_receipt_sha256,
                self._config.expected_schema_sha256,
                self._config.expected_pending_catalog_binding_sha256,
            )
        ):
            return "STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        protected_batch_session: Any,
        protected_evidence_schema: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not (
            batch_authority_v1.protected_startup_recovery_batch_session_authority_valid_v1(
                protected_batch_session
            )
            and hmac.compare_digest(
                protected_batch_session.receipt_sha256,
                str(self._config.expected_batch_session_receipt_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_BATCH_SESSION_INVALID")
            return result
        result["batch_session_verified"] = True
        if not (
            evidence_schema_v1.protected_production_startup_recovery_evidence_schema_valid_v1(
                protected_evidence_schema
            )
            and hmac.compare_digest(
                protected_evidence_schema.schema_sha256,
                str(self._config.expected_schema_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_EVIDENCE_SCHEMA_INVALID")
            return result
        result["evidence_schema_verified"] = True
        if not _source_identity_matches(
            protected_batch_session, protected_evidence_schema
        ):
            result["reasons"].append("BATCH_SCHEMA_IDENTITY_MISMATCH")
            return result
        receipt = protected_batch_session.receipt
        if not hmac.compare_digest(
            receipt["pending_catalog_binding_sha256"],
            str(self._config.expected_pending_catalog_binding_sha256),
        ):
            result["reasons"].append("PENDING_CATALOG_BINDING_PIN_MISMATCH")
            return result
        result["identity_vector_verified"] = True
        schema = protected_evidence_schema.schema
        authenticated = protected_batch_session.authenticated_authority_binding.binding
        pending_items = _canonical_copy(receipt["pending_items"])
        prepared = sorted(
            item["transaction_sha256"]
            for item in pending_items
            if item["source_state"] == "PREPARED"
        )
        resolved = sorted(
            item["transaction_sha256"]
            for item in pending_items
            if item["source_state"] == "RESOLVED"
        )
        binding = {
            "binding_version": PROTECTED_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1,
            "batch_session_receipt_sha256": protected_batch_session.receipt_sha256,
            "authenticated_authority_binding_sha256": receipt[
                "authenticated_authority_binding_sha256"
            ],
            "candidate_authenticated_authority_receipt_sha256": authenticated[
                "candidate_authenticated_authority_receipt_sha256"
            ],
            "schema_sha256": schema["schema_sha256"],
            "future_evidence_version": schema["future_evidence_version"],
            "provider_binding_sha256": receipt["provider_binding_sha256"],
            "backend_instance_sha256": receipt["backend_instance_sha256"],
            "registry_path_binding_sha256": receipt[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": receipt[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": receipt[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": receipt["lock_namespace_sha256"],
            "durable_root_identity_sha256": receipt[
                "durable_root_identity_sha256"
            ],
            "durable_storage_binding_sha256": receipt[
                "durable_storage_binding_sha256"
            ],
            "maintenance_epoch": receipt["maintenance_epoch"],
            "candidate_maintenance_lease_receipt_sha256": receipt[
                "candidate_maintenance_lease_receipt_sha256"
            ],
            "pending_catalog_binding_sha256": receipt[
                "pending_catalog_binding_sha256"
            ],
            "pending_items": pending_items,
            "pending_item_count": len(pending_items),
            "prepared_transactions": prepared,
            "resolved_transactions": resolved,
            "transaction_set_sha256": receipt["transaction_set_sha256"],
            "terminal_receipt_transaction_set_sha256": receipt[
                "transaction_set_sha256"
            ],
            "same_schema_verified": True,
            "same_provider_binding_verified": True,
            "same_backend_instance_verified": True,
            "same_registry_path_binding_verified": True,
            "same_lock_namespace_verified": True,
            "exact_maintenance_epoch_required": True,
            "exact_maintenance_lease_receipt_required": True,
            "exact_authenticated_authority_receipt_required": True,
            "exact_pending_catalog_crosscheck_required": True,
            "complete_initial_catalogs_required": True,
            "terminal_receipt_per_pending_item_required": True,
            "final_catalog_drain_required": True,
            "live_lease_revalidation_required": True,
            "durable_current_state_revalidation_required": True,
            "external_authenticated_verification_required": True,
            "empirical_durability_verification_required": True,
            "storage_bindings_projected_not_schema_authenticated": True,
            "batch_scope_bound": True,
            "evidence_created": False,
            "evidence_builder_called": False,
            "evidence_population_allowed": False,
            "recovery_authority_granted": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
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
            "synthetic_only": True,
        }
        binding["binding_sha256"] = (
            startup_recovery_batch_evidence_scope_binding_sha256_v1(binding)
        )
        protected = ProtectedStartupRecoveryBatchEvidenceScopeBindingV1(
            protected_batch_session=protected_batch_session,
            protected_evidence_schema=protected_evidence_schema,
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_SCOPE_BINDING_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BOUND_DORMANT",
            batch_scope_bound=True,
            protected_scope_binding=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryBatchEvidenceScopeBindingConfigV1",
    "DormantStartupRecoveryBatchEvidenceScopeBindingContractV1",
    "OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_VERSION_V1",
    "ProtectedStartupRecoveryBatchEvidenceScopeBindingV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_EVIDENCE_SCOPE_BINDING_CONTRACT_V1_VERSION",
    "protected_startup_recovery_batch_evidence_scope_binding_valid_v1",
    "startup_recovery_batch_evidence_scope_binding_sha256_v1",
]
