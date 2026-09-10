"""Dormant scope-aware adapter for synthetic recovery-evidence conformance."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as scope_binding_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-SCOPE-AWARE-EVIDENCE-CONFORMANCE-ADAPTER-CONTRACT-V1"
)
OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "scope_attestation",
        "scope_binding_sha256",
        "bundle_sha256",
        "schema_sha256",
        "provider_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "authenticated_authority_receipt_sha256",
        "pending_catalog_binding_sha256",
        "transaction_set_sha256",
        "pending_item_count",
        "scope_cross_binding_verified",
        "delegate_conformance_verified",
        "exact_backend_storage_identity_verified",
        "exact_maintenance_identity_verified",
        "exact_authenticated_authority_verified",
        "exact_pending_catalog_transaction_set_verified",
        "exact_terminal_receipt_transaction_set_verified",
        "live_lease_revalidation_required",
        "durable_current_state_revalidation_required",
        "external_authenticated_verification_required",
        "empirical_durability_verification_required",
        "production_evidence_created",
        "production_authority_granted",
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
        "receipt_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "CONFORMANCE_RESULT_IS_SYNTHETIC_AND_NOT_PRODUCTION_EVIDENCE",
    "LIVE_MAINTENANCE_LEASE_REVALIDATION_NOT_EXECUTED",
    "DURABLE_AUTHORITY_CURRENT_STATE_REVALIDATION_NOT_EXECUTED",
    "AUTHENTICATED_PRODUCTION_AUTHORITY_NOT_VERIFIED",
    "EMPIRICAL_DURABILITY_NOT_VERIFIED",
    "PRODUCTION_EVIDENCE_BUILDER_NOT_IMPLEMENTED",
    "RUNTIME_INTEGRATION_AND_RECOVERY_EXECUTION_REMAIN_FORBIDDEN",
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


def startup_recovery_scope_aware_conformance_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("conformance receipt must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def _source_map(catalogs: tuple[Any, Any]) -> dict[str, str] | None:
    prepared, resolved = catalogs
    if not (
        isinstance(prepared, Mapping)
        and isinstance(resolved, Mapping)
        and isinstance(prepared.get("records"), list)
        and isinstance(resolved.get("records"), list)
    ):
        return None
    result: dict[str, str] = {}
    try:
        for record in prepared["records"]:
            transaction_sha256 = record["transaction_sha256"]
            if transaction_sha256 in result:
                return None
            result[transaction_sha256] = "PREPARED"
        for record in resolved["records"]:
            transaction_sha256 = record["transaction_sha256"]
            if transaction_sha256 in result:
                return None
            result[transaction_sha256] = "RESOLVED"
    except Exception:
        return None
    return result


def _scope_cross_binding_valid(protected_scope_binding: Any, bundle: Any) -> bool:
    if not (
        scope_binding_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
            protected_scope_binding
        )
        and type(bundle) is dict
    ):
        return False
    scope = protected_scope_binding.binding
    try:
        initial_snapshot = bundle["initial_backend_snapshot"]
        final_snapshot = bundle["final_backend_snapshot"]
        initial_audit = bundle["initial_transaction_log_audit"]
        final_audit = bundle["final_transaction_log_audit"]
        initial_prepared = bundle["initial_prepared_catalog"]
        initial_resolved = bundle["initial_resolved_catalog"]
        final_prepared = bundle["final_prepared_catalog"]
        final_resolved = bundle["final_resolved_catalog"]
        terminal_receipts = bundle["terminal_receipts"]
        completion = bundle["completion_attestation"]
    except Exception:
        return False
    if not (
        all(
            isinstance(item, Mapping)
            for item in (
                initial_snapshot,
                final_snapshot,
                initial_audit,
                final_audit,
                initial_prepared,
                initial_resolved,
                final_prepared,
                final_resolved,
                completion,
            )
        )
        and isinstance(terminal_receipts, list)
        and all(isinstance(item, Mapping) for item in terminal_receipts)
    ):
        return False
    expected_sources = {
        item["transaction_sha256"]: item["source_state"]
        for item in scope["pending_items"]
    }
    catalog_sources = _source_map((initial_prepared, initial_resolved))
    terminal_sources = {
        item.get("transaction_sha256"): item.get("source_state")
        for item in terminal_receipts
    }
    auth_sha = scope["candidate_authenticated_authority_receipt_sha256"]
    snapshots = (initial_snapshot, final_snapshot)
    audits = (initial_audit, final_audit)
    catalogs = (
        initial_prepared,
        initial_resolved,
        final_prepared,
        final_resolved,
    )
    try:
        return bool(
            bundle["schema_sha256"] == scope["schema_sha256"]
            and catalog_sources == expected_sources
            and terminal_sources == expected_sources
            and len(terminal_receipts) == len(expected_sources)
            and all(
                snapshot["schema_sha256"] == scope["schema_sha256"]
                and snapshot["provider_binding_sha256"]
                == scope["provider_binding_sha256"]
                and snapshot["backend_instance_sha256"]
                == scope["backend_instance_sha256"]
                and snapshot["registry_path_binding_sha256"]
                == scope["registry_path_binding_sha256"]
                and snapshot["wal_storage_binding_sha256"]
                == scope["wal_storage_binding_sha256"]
                and snapshot["resolved_ledger_storage_binding_sha256"]
                == scope["resolved_ledger_storage_binding_sha256"]
                and snapshot["lock_namespace_sha256"]
                == scope["lock_namespace_sha256"]
                and snapshot["authenticated_authority_receipt_sha256"]
                == auth_sha
                for snapshot in snapshots
            )
            and all(
                audit["schema_sha256"] == scope["schema_sha256"]
                and audit["backend_instance_sha256"]
                == scope["backend_instance_sha256"]
                and audit["wal_storage_binding_sha256"]
                == scope["wal_storage_binding_sha256"]
                and audit["resolved_ledger_storage_binding_sha256"]
                == scope["resolved_ledger_storage_binding_sha256"]
                and audit["lock_namespace_sha256"]
                == scope["lock_namespace_sha256"]
                and audit["authenticated_authority_receipt_sha256"] == auth_sha
                for audit in audits
            )
            and all(
                catalog["schema_sha256"] == scope["schema_sha256"]
                and catalog["backend_instance_sha256"]
                == scope["backend_instance_sha256"]
                and catalog["lock_namespace_sha256"]
                == scope["lock_namespace_sha256"]
                and catalog["authenticated_authority_receipt_sha256"]
                == auth_sha
                for catalog in catalogs
            )
            and initial_prepared["registry_path_binding_sha256"]
            == final_prepared["registry_path_binding_sha256"]
            == scope["registry_path_binding_sha256"]
            and initial_prepared["wal_storage_binding_sha256"]
            == final_prepared["wal_storage_binding_sha256"]
            == scope["wal_storage_binding_sha256"]
            and initial_resolved["resolved_ledger_storage_binding_sha256"]
            == final_resolved["resolved_ledger_storage_binding_sha256"]
            == scope["resolved_ledger_storage_binding_sha256"]
            and all(
                item["schema_sha256"] == scope["schema_sha256"]
                and item["provider_binding_sha256"]
                == scope["provider_binding_sha256"]
                and item["backend_instance_sha256"]
                == scope["backend_instance_sha256"]
                and item["maintenance_epoch"] == scope["maintenance_epoch"]
                and item["authenticated_authority_receipt_sha256"] == auth_sha
                for item in terminal_receipts
            )
            and completion["schema_sha256"] == scope["schema_sha256"]
            and completion["provider_binding_sha256"]
            == scope["provider_binding_sha256"]
            and completion["backend_instance_sha256"]
            == scope["backend_instance_sha256"]
            and completion["registry_path_binding_sha256"]
            == scope["registry_path_binding_sha256"]
            and completion["wal_storage_binding_sha256"]
            == scope["wal_storage_binding_sha256"]
            and completion["resolved_ledger_storage_binding_sha256"]
            == scope["resolved_ledger_storage_binding_sha256"]
            and completion["lock_namespace_sha256"]
            == scope["lock_namespace_sha256"]
            and completion["maintenance_epoch"] == scope["maintenance_epoch"]
            and completion["maintenance_lease_receipt_sha256"]
            == scope["candidate_maintenance_lease_receipt_sha256"]
        )
    except Exception:
        return False


def _fixture_conforms_independently(
    protected_scope_binding: Any,
    bundle: Any,
) -> bool:
    if not _scope_cross_binding_valid(protected_scope_binding, bundle):
        return False
    validator = conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceV1(
        config=conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceConfigV1(
            enabled=True,
            scope_attestation=(
                conformance_v1.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
            ),
            expected_schema_sha256=(
                protected_scope_binding.protected_evidence_schema.schema_sha256
            ),
        )
    )
    try:
        result = validator.audit_offline(
            protected_schema=protected_scope_binding.protected_evidence_schema,
            fixture_bundle=bundle,
        )
    except Exception:
        return False
    return bool(
        type(result) is dict
        and result.get("ok") is True
        and result.get("schema_conforms") is True
        and result.get("production_admissible") is False
        and result.get("production_authority") is False
        and result.get("runtime_integrated") is False
        and result.get("recovery_execution_allowed") is False
        and result.get("live_allowed") is False
        and result.get("filesystem_accessed") is False
        and result.get("real_registry_accessed") is False
        and result.get("network_accessed") is False
        and result.get("broker_called") is False
        and result.get("no_order_sent") is True
    )


@dataclass(frozen=True)
class DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_scope_binding_sha256: str | None = field(default=None, repr=False)
    expected_bundle_sha256: str | None = field(default=None, repr=False)


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1:
    protected_scope_binding: scope_binding_v1.ProtectedStartupRecoveryBatchEvidenceScopeBindingV1 = field(
        repr=False
    )
    fixture_bundle: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1(<protected>)"


def protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1
    ):
        return False
    if not _scope_cross_binding_valid(
        value.protected_scope_binding, value.fixture_bundle
    ):
        return False
    if not _fixture_conforms_independently(
        value.protected_scope_binding, value.fixture_bundle
    ):
        return False
    receipt = value.receipt
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        return False
    scope = value.protected_scope_binding.binding
    try:
        return bool(
            receipt["receipt_version"]
            == PROTECTED_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_VERSION_V1
            and receipt["scope_attestation"]
            == OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1
            and receipt["scope_binding_sha256"]
            == value.protected_scope_binding.binding_sha256
            and receipt["bundle_sha256"]
            == value.fixture_bundle["bundle_sha256"]
            and receipt["schema_sha256"] == scope["schema_sha256"]
            and receipt["provider_binding_sha256"]
            == scope["provider_binding_sha256"]
            and receipt["backend_instance_sha256"]
            == scope["backend_instance_sha256"]
            and receipt["registry_path_binding_sha256"]
            == scope["registry_path_binding_sha256"]
            and receipt["wal_storage_binding_sha256"]
            == scope["wal_storage_binding_sha256"]
            and receipt["resolved_ledger_storage_binding_sha256"]
            == scope["resolved_ledger_storage_binding_sha256"]
            and receipt["lock_namespace_sha256"]
            == scope["lock_namespace_sha256"]
            and receipt["maintenance_epoch"] == scope["maintenance_epoch"]
            and receipt["maintenance_lease_receipt_sha256"]
            == scope["candidate_maintenance_lease_receipt_sha256"]
            and receipt["authenticated_authority_receipt_sha256"]
            == scope["candidate_authenticated_authority_receipt_sha256"]
            and receipt["pending_catalog_binding_sha256"]
            == scope["pending_catalog_binding_sha256"]
            and receipt["transaction_set_sha256"]
            == scope["transaction_set_sha256"]
            and receipt["pending_item_count"] == scope["pending_item_count"]
            and all(
                receipt[field_name] is True
                for field_name in (
                    "scope_cross_binding_verified",
                    "delegate_conformance_verified",
                    "exact_backend_storage_identity_verified",
                    "exact_maintenance_identity_verified",
                    "exact_authenticated_authority_verified",
                    "exact_pending_catalog_transaction_set_verified",
                    "exact_terminal_receipt_transaction_set_verified",
                    "live_lease_revalidation_required",
                    "durable_current_state_revalidation_required",
                    "external_authenticated_verification_required",
                    "empirical_durability_verification_required",
                    "no_order_sent",
                    "synthetic_only",
                )
            )
            and all(
                receipt[field_name] is False
                for field_name in (
                    "production_evidence_created",
                    "production_authority_granted",
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
            and receipt["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and _valid_sha256(receipt["receipt_sha256"])
            and hmac.compare_digest(
                receipt["receipt_sha256"],
                startup_recovery_scope_aware_conformance_receipt_sha256_v1(
                    receipt
                ),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config
            or DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1()
        )

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "scope_binding_verified": False,
            "bundle_pin_verified": False,
            "scope_cross_binding_verified": False,
            "delegate_called": False,
            "delegate_conformance_verified": False,
            "production_evidence_created": False,
            "production_authority_granted": False,
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
            "protected_conformance": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "SCOPE_AWARE_EVIDENCE_CONFORMANCE_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1
        ):
            return "SCOPE_AWARE_EVIDENCE_CONFORMANCE_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                self._config.expected_scope_binding_sha256,
                self._config.expected_bundle_sha256,
            )
        ):
            return "SCOPE_AWARE_EVIDENCE_CONFORMANCE_PINS_INVALID"
        return None

    def audit_offline(
        self,
        *,
        protected_scope_binding: Any,
        fixture_bundle: Any,
        conformance_validator: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not (
            scope_binding_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                protected_scope_binding
            )
            and hmac.compare_digest(
                protected_scope_binding.binding_sha256,
                str(self._config.expected_scope_binding_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_SCOPE_BINDING_INVALID")
            return result
        result["scope_binding_verified"] = True
        try:
            bundle = _canonical_copy(dict(fixture_bundle))
        except Exception:
            result["reasons"].append("SYNTHETIC_EVIDENCE_BUNDLE_INVALID")
            return result
        if not (
            _valid_sha256(bundle.get("bundle_sha256"))
            and hmac.compare_digest(
                bundle["bundle_sha256"],
                str(self._config.expected_bundle_sha256),
            )
            and hmac.compare_digest(
                bundle["bundle_sha256"],
                conformance_v1.synthetic_evidence_bundle_sha256_v1(bundle),
            )
        ):
            result["reasons"].append("SYNTHETIC_EVIDENCE_BUNDLE_PIN_INVALID")
            return result
        result["bundle_pin_verified"] = True
        if not _scope_cross_binding_valid(protected_scope_binding, bundle):
            result["reasons"].append("SCOPE_TO_EVIDENCE_CROSS_BINDING_INVALID")
            return result
        result["scope_cross_binding_verified"] = True
        if type(conformance_validator) is not conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceV1:
            result["reasons"].append("OFFLINE_CONFORMANCE_VALIDATOR_INVALID")
            return result
        result["delegate_called"] = True
        delegate_result = conformance_validator.audit_offline(
            protected_schema=protected_scope_binding.protected_evidence_schema,
            fixture_bundle=bundle,
        )
        if not (
            type(delegate_result) is dict
            and delegate_result.get("ok") is True
            and delegate_result.get("schema_conforms") is True
            and delegate_result.get("production_admissible") is False
            and delegate_result.get("production_authority") is False
            and delegate_result.get("runtime_integrated") is False
            and delegate_result.get("recovery_execution_allowed") is False
            and delegate_result.get("live_allowed") is False
            and delegate_result.get("filesystem_accessed") is False
            and delegate_result.get("real_registry_accessed") is False
            and delegate_result.get("network_accessed") is False
            and delegate_result.get("broker_called") is False
            and delegate_result.get("no_order_sent") is True
        ):
            result["reasons"].append("DELEGATE_CONFORMANCE_FAILED_CLOSED")
            return result
        result["delegate_conformance_verified"] = True
        scope = protected_scope_binding.binding
        receipt = {
            "receipt_version": PROTECTED_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_VERSION_V1,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1,
            "scope_binding_sha256": protected_scope_binding.binding_sha256,
            "bundle_sha256": bundle["bundle_sha256"],
            "schema_sha256": scope["schema_sha256"],
            "provider_binding_sha256": scope["provider_binding_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "registry_path_binding_sha256": scope[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": scope[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": scope[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": scope["lock_namespace_sha256"],
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "candidate_maintenance_lease_receipt_sha256"
            ],
            "authenticated_authority_receipt_sha256": scope[
                "candidate_authenticated_authority_receipt_sha256"
            ],
            "pending_catalog_binding_sha256": scope[
                "pending_catalog_binding_sha256"
            ],
            "transaction_set_sha256": scope["transaction_set_sha256"],
            "pending_item_count": scope["pending_item_count"],
            "scope_cross_binding_verified": True,
            "delegate_conformance_verified": True,
            "exact_backend_storage_identity_verified": True,
            "exact_maintenance_identity_verified": True,
            "exact_authenticated_authority_verified": True,
            "exact_pending_catalog_transaction_set_verified": True,
            "exact_terminal_receipt_transaction_set_verified": True,
            "live_lease_revalidation_required": True,
            "durable_current_state_revalidation_required": True,
            "external_authenticated_verification_required": True,
            "empirical_durability_verification_required": True,
            "production_evidence_created": False,
            "production_authority_granted": False,
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
        receipt["receipt_sha256"] = (
            startup_recovery_scope_aware_conformance_receipt_sha256_v1(receipt)
        )
        protected = ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1(
            protected_scope_binding=protected_scope_binding,
            fixture_bundle=_canonical_copy(bundle),
            receipt=_canonical_copy(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_CONFORMANCE_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMS_SYNTHETIC_ONLY",
            protected_conformance=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1",
    "DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1",
    "OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_VERSION_V1",
    "ProtectedStartupRecoveryScopeAwareEvidenceConformanceV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_CONTRACT_V1_VERSION",
    "protected_startup_recovery_scope_aware_evidence_conformance_valid_v1",
    "startup_recovery_scope_aware_conformance_receipt_sha256_v1",
]
