"""Dormant provider/backend projection for future evidence-builder read ports."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as provider_binding_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as scope_binding_v1
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as startup_provider_binding_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-READ-PORT-ADAPTER-CONTRACT-V1"
)
OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PROJECTION_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_PORTS = (
    "read_backend_snapshot_offline",
    "read_transaction_log_audit_offline",
    "read_prepared_catalog_offline",
    "read_resolved_catalog_offline",
    "read_backend_capability_probe_offline",
    "normalize_terminal_receipt_offline",
)
_SOURCE_PROVIDER_SURFACE = (
    "snapshot",
    "load_exact_raw_registry",
    "reconcile_attested_transaction",
)
_PORT_ROUTE_PLAN = (
    {
        "required_port": "read_backend_snapshot_offline",
        "source_surface": "snapshot",
        "status": "CONTROL_PLANE_SNAPSHOT_INCOMPATIBLE_NEW_READ_ONLY_PORT_REQUIRED",
    },
    {
        "required_port": "read_transaction_log_audit_offline",
        "source_surface": None,
        "status": "MISSING_NEW_READ_ONLY_WAL_AUDIT_PORT_REQUIRED",
    },
    {
        "required_port": "read_prepared_catalog_offline",
        "source_surface": None,
        "status": "MISSING_NEW_READ_ONLY_PREPARED_CATALOG_PORT_REQUIRED",
    },
    {
        "required_port": "read_resolved_catalog_offline",
        "source_surface": None,
        "status": "MISSING_NEW_READ_ONLY_RESOLVED_CATALOG_PORT_REQUIRED",
    },
    {
        "required_port": "read_backend_capability_probe_offline",
        "source_surface": None,
        "status": "MISSING_NEW_READ_ONLY_CAPABILITY_PROBE_PORT_REQUIRED",
    },
    {
        "required_port": "normalize_terminal_receipt_offline",
        "source_surface": None,
        "status": "MISSING_NEW_TERMINAL_RECEIPT_NORMALIZER_REQUIRED",
    },
)
_PLAN_KEYS = frozenset(
    {
        "plan_version",
        "scope_attestation",
        "scope_binding_sha256",
        "startup_provider_binding_sha256",
        "provider_store_binding_sha256",
        "source_provider_version",
        "source_store_version",
        "source_provider_snapshot_sha256",
        "source_store_snapshot_sha256",
        "source_adapter_snapshot_sha256",
        "schema_sha256",
        "provider_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "required_ports",
        "source_provider_surface",
        "port_route_plan",
        "required_port_count",
        "implemented_port_count",
        "missing_port_count",
        "same_provider_store_binding_verified",
        "same_backend_instance_verified",
        "same_registry_path_binding_verified",
        "same_lock_namespace_verified",
        "durability_required",
        "read_only_required",
        "complete_prepared_catalog_required",
        "complete_resolved_catalog_required",
        "empirical_capability_probe_required",
        "terminal_receipt_normalizer_required",
        "adapter_callable_created",
        "provider_instance_bound",
        "backend_instance_bound",
        "provider_called",
        "store_called",
        "backend_called",
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
        "synthetic_projection_only",
        "production_blockers",
        "plan_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "PROVIDER_AND_STORE_ARE_HASH_ONLY_PROJECTIONS",
    "CONTROL_PLANE_SNAPSHOT_IS_NOT_AN_EVIDENCE_SNAPSHOT",
    "READ_ONLY_WAL_AUDIT_PORT_NOT_IMPLEMENTED",
    "READ_ONLY_PREPARED_CATALOG_PORT_NOT_IMPLEMENTED",
    "READ_ONLY_RESOLVED_CATALOG_PORT_NOT_IMPLEMENTED",
    "EMPIRICAL_CAPABILITY_PROBE_PORT_NOT_IMPLEMENTED",
    "TERMINAL_RECEIPT_NORMALIZER_NOT_IMPLEMENTED",
    "PRODUCTION_DURABILITY_AND_AUTHORITY_NOT_VERIFIED",
    "NO_PROVIDER_BACKEND_OR_REGISTRY_INSTANCE_MAY_BE_BOUND_BY_THIS_PLAN",
    "RUNTIME_RECOVERY_READINESS_AND_LIVE_REMAIN_FORBIDDEN",
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


def startup_recovery_evidence_read_port_adapter_plan_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("adapter plan must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "plan_sha256"}
    )


@dataclass(frozen=True)
class DormantStartupRecoveryEvidenceReadPortAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_scope_binding_sha256: str | None = field(default=None, repr=False)
    expected_provider_store_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_startup_provider_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1:
    protected_scope_binding: scope_binding_v1.ProtectedStartupRecoveryBatchEvidenceScopeBindingV1 = field(
        repr=False
    )
    protected_provider_store_binding: provider_binding_v1.ProtectedProductionProviderStoreAdapterBindingV1 = field(
        repr=False
    )
    protected_startup_provider_binding: startup_provider_binding_v1.ProtectedStartupRecoveryProductionProviderBindingV1 = field(
        repr=False
    )
    plan: Mapping[str, Any] = field(repr=False)
    plan_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1(<protected>)"


def _source_bindings_match(
    protected_scope: Any,
    protected_startup_provider: Any,
    protected_provider: Any,
) -> bool:
    if not (
        scope_binding_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
            protected_scope
        )
        and provider_binding_v1.protected_provider_store_adapter_binding_valid_v1(
            protected_provider
        )
        and startup_provider_binding_v1.protected_startup_recovery_production_provider_binding_valid_v1(
            protected_startup_provider
        )
    ):
        return False
    scope = protected_scope.binding
    provider = protected_provider.binding
    schema = protected_scope.protected_evidence_schema.schema
    try:
        return bool(
            scope["provider_binding_sha256"]
            == protected_startup_provider.binding_sha256
            == schema["provider_binding_sha256"]
            and protected_startup_provider.binding[
                "provider_store_binding_sha256"
            ]
            == protected_provider.binding_sha256
            and scope["backend_instance_sha256"]
            == provider["backend_instance_sha256"]
            and scope["registry_path_binding_sha256"]
            == provider["registry_path_binding_sha256"]
            and scope["lock_namespace_sha256"]
            == provider["lock_namespace_sha256"]
            and schema["source_backend_capability_declaration_sha256"]
            == provider["backend_capability_attestation_sha256"]
            and provider["durability_required"] is True
            and provider["durability_verified"] is False
            and provider["provider_call_allowed"] is False
            and provider["store_call_allowed"] is False
            and provider["production_authority"] is False
            and provider["runtime_integrated"] is False
            and provider["synthetic_only"] is True
        )
    except Exception:
        return False


def protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1
    ):
        return False
    if not _source_bindings_match(
        value.protected_scope_binding,
        value.protected_startup_provider_binding,
        value.protected_provider_store_binding,
    ):
        return False
    plan = value.plan
    if type(plan) is not dict or set(plan) != _PLAN_KEYS:
        return False
    scope = value.protected_scope_binding.binding
    provider = value.protected_provider_store_binding.binding
    try:
        return bool(
            plan["plan_version"]
            == PROTECTED_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_VERSION_V1
            and plan["scope_attestation"]
            == OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1
            and plan["scope_binding_sha256"]
            == value.protected_scope_binding.binding_sha256
            and plan["startup_provider_binding_sha256"]
            == value.protected_startup_provider_binding.binding_sha256
            and plan["provider_store_binding_sha256"]
            == value.protected_provider_store_binding.binding_sha256
            and all(
                plan[field_name] == provider[source_field]
                for field_name, source_field in (
                    ("source_provider_version", "source_provider_version"),
                    ("source_store_version", "source_store_version"),
                    (
                        "source_provider_snapshot_sha256",
                        "source_provider_snapshot_sha256",
                    ),
                    (
                        "source_store_snapshot_sha256",
                        "source_store_snapshot_sha256",
                    ),
                    ("source_adapter_snapshot_sha256", "adapter_snapshot_sha256"),
                    (
                        "backend_capability_attestation_sha256",
                        "backend_capability_attestation_sha256",
                    ),
                )
            )
            and all(
                plan[field_name] == scope[field_name]
                for field_name in (
                    "schema_sha256",
                    "provider_binding_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "lock_namespace_sha256",
                    "wal_storage_binding_sha256",
                    "resolved_ledger_storage_binding_sha256",
                )
            )
            and plan["required_ports"] == list(_REQUIRED_PORTS)
            and plan["source_provider_surface"] == list(_SOURCE_PROVIDER_SURFACE)
            and plan["port_route_plan"] == list(_PORT_ROUTE_PLAN)
            and plan["required_port_count"] == len(_REQUIRED_PORTS)
            and plan["implemented_port_count"] == 0
            and plan["missing_port_count"] == len(_REQUIRED_PORTS)
            and all(
                plan[field_name] is True
                for field_name in (
                    "same_provider_store_binding_verified",
                    "same_backend_instance_verified",
                    "same_registry_path_binding_verified",
                    "same_lock_namespace_verified",
                    "durability_required",
                    "read_only_required",
                    "complete_prepared_catalog_required",
                    "complete_resolved_catalog_required",
                    "empirical_capability_probe_required",
                    "terminal_receipt_normalizer_required",
                    "no_order_sent",
                    "synthetic_projection_only",
                )
            )
            and all(
                plan[field_name] is False
                for field_name in (
                    "adapter_callable_created",
                    "provider_instance_bound",
                    "backend_instance_bound",
                    "provider_called",
                    "store_called",
                    "backend_called",
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
            and plan["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and value.plan_sha256 == plan["plan_sha256"]
            and _valid_sha256(plan["plan_sha256"])
            and hmac.compare_digest(
                plan["plan_sha256"],
                startup_recovery_evidence_read_port_adapter_plan_sha256_v1(plan),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryEvidenceReadPortAdapterContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryEvidenceReadPortAdapterConfigV1 | None = None,
    ) -> None:
        self._config = config or DormantStartupRecoveryEvidenceReadPortAdapterConfigV1()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_CONTRACT_V1_VERSION,
            "dormant": True,
            "offline_only": True,
            "synthetic_projection_only": True,
            "scope_binding_verified": False,
            "provider_store_binding_verified": False,
            "startup_provider_binding_verified": False,
            "identity_vector_verified": False,
            "adapter_plan_created": False,
            "adapter_callable_created": False,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "reasons": [],
            "protected_adapter_plan": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "EVIDENCE_READ_PORT_ADAPTER_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            return "EVIDENCE_READ_PORT_ADAPTER_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                self._config.expected_scope_binding_sha256,
                self._config.expected_startup_provider_binding_sha256,
                self._config.expected_provider_store_binding_sha256,
            )
        ):
            return "EVIDENCE_READ_PORT_ADAPTER_PINS_INVALID"
        return None

    def project_offline(
        self,
        *,
        protected_scope_binding: Any,
        protected_startup_provider_binding: Any,
        protected_provider_store_binding: Any,
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
            result["reasons"].append("PROTECTED_EVIDENCE_SCOPE_BINDING_INVALID")
            return result
        result["scope_binding_verified"] = True
        if not (
            startup_provider_binding_v1.protected_startup_recovery_production_provider_binding_valid_v1(
                protected_startup_provider_binding
            )
            and hmac.compare_digest(
                protected_startup_provider_binding.binding_sha256,
                str(self._config.expected_startup_provider_binding_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_STARTUP_PROVIDER_BINDING_INVALID")
            return result
        result["startup_provider_binding_verified"] = True
        if not (
            provider_binding_v1.protected_provider_store_adapter_binding_valid_v1(
                protected_provider_store_binding
            )
            and hmac.compare_digest(
                protected_provider_store_binding.binding_sha256,
                str(self._config.expected_provider_store_binding_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_PROVIDER_STORE_BINDING_INVALID")
            return result
        result["provider_store_binding_verified"] = True
        if not _source_bindings_match(
            protected_scope_binding,
            protected_startup_provider_binding,
            protected_provider_store_binding,
        ):
            result["reasons"].append("SCOPE_PROVIDER_STORE_IDENTITY_MISMATCH")
            return result
        result["identity_vector_verified"] = True
        scope = protected_scope_binding.binding
        provider = protected_provider_store_binding.binding
        plan = {
            "plan_version": PROTECTED_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_VERSION_V1,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1,
            "scope_binding_sha256": protected_scope_binding.binding_sha256,
            "startup_provider_binding_sha256": protected_startup_provider_binding.binding_sha256,
            "provider_store_binding_sha256": protected_provider_store_binding.binding_sha256,
            "source_provider_version": provider["source_provider_version"],
            "source_store_version": provider["source_store_version"],
            "source_provider_snapshot_sha256": provider[
                "source_provider_snapshot_sha256"
            ],
            "source_store_snapshot_sha256": provider[
                "source_store_snapshot_sha256"
            ],
            "source_adapter_snapshot_sha256": provider["adapter_snapshot_sha256"],
            "schema_sha256": scope["schema_sha256"],
            "provider_binding_sha256": scope["provider_binding_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "registry_path_binding_sha256": scope[
                "registry_path_binding_sha256"
            ],
            "backend_capability_attestation_sha256": provider[
                "backend_capability_attestation_sha256"
            ],
            "lock_namespace_sha256": scope["lock_namespace_sha256"],
            "wal_storage_binding_sha256": scope["wal_storage_binding_sha256"],
            "resolved_ledger_storage_binding_sha256": scope[
                "resolved_ledger_storage_binding_sha256"
            ],
            "required_ports": list(_REQUIRED_PORTS),
            "source_provider_surface": list(_SOURCE_PROVIDER_SURFACE),
            "port_route_plan": list(_PORT_ROUTE_PLAN),
            "required_port_count": len(_REQUIRED_PORTS),
            "implemented_port_count": 0,
            "missing_port_count": len(_REQUIRED_PORTS),
            "same_provider_store_binding_verified": True,
            "same_backend_instance_verified": True,
            "same_registry_path_binding_verified": True,
            "same_lock_namespace_verified": True,
            "durability_required": True,
            "read_only_required": True,
            "complete_prepared_catalog_required": True,
            "complete_resolved_catalog_required": True,
            "empirical_capability_probe_required": True,
            "terminal_receipt_normalizer_required": True,
            "adapter_callable_created": False,
            "provider_instance_bound": False,
            "backend_instance_bound": False,
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
            "synthetic_projection_only": True,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        plan["plan_sha256"] = (
            startup_recovery_evidence_read_port_adapter_plan_sha256_v1(plan)
        )
        protected = ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1(
            protected_scope_binding=protected_scope_binding,
            protected_provider_store_binding=protected_provider_store_binding,
            protected_startup_provider_binding=protected_startup_provider_binding,
            plan=_canonical_copy(plan),
            plan_sha256=plan["plan_sha256"],
        )
        if not protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_ADAPTER_PLAN_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_DEFINED_DORMANT",
            adapter_plan_created=True,
            protected_adapter_plan=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryEvidenceReadPortAdapterConfigV1",
    "DormantStartupRecoveryEvidenceReadPortAdapterContractV1",
    "OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_PLAN_VERSION_V1",
    "ProtectedStartupRecoveryEvidenceReadPortAdapterPlanV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_ADAPTER_CONTRACT_V1_VERSION",
    "protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1",
    "startup_recovery_evidence_read_port_adapter_plan_sha256_v1",
]
