"""Dormant port contract for a future startup-recovery evidence builder.

The contract binds process-local, injected dependencies but never calls them.
It creates no evidence and grants no backend, recovery, runtime, or production
authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as scope_binding_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-BUILDER-PORTS-CONTRACT-V1"
)
OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORT_BINDING_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORT_BINDING_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_READ_PORT_METHODS = (
    "read_backend_snapshot_offline",
    "read_transaction_log_audit_offline",
    "read_prepared_catalog_offline",
    "read_resolved_catalog_offline",
    "read_backend_capability_probe_offline",
)
_NORMALIZER_PORT_METHODS = ("normalize_terminal_receipt_offline",)
_SAFETY_MARKERS = {
    "offline_only": True,
    "synthetic_only": True,
    "filesystem_access_allowed": False,
    "network_access_allowed": False,
    "production_access_allowed": False,
    "write_allowed": False,
}
_PHASE_SEQUENCE = (
    "INITIAL_BACKEND_SNAPSHOT",
    "INITIAL_BACKEND_CAPABILITY_PROBE",
    "INITIAL_TRANSACTION_LOG_AUDIT",
    "INITIAL_PREPARED_CATALOG",
    "INITIAL_RESOLVED_CATALOG",
    "TERMINAL_RECEIPT_NORMALIZATION_PER_PENDING_ITEM",
    "FINAL_BACKEND_SNAPSHOT",
    "FINAL_TRANSACTION_LOG_AUDIT",
    "FINAL_PREPARED_CATALOG",
    "FINAL_RESOLVED_CATALOG",
)
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "scope_binding_sha256",
        "schema_sha256",
        "provider_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "pending_catalog_binding_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "authenticated_authority_receipt_sha256",
        "evidence_read_port_class_id",
        "evidence_read_port_object_identity_sha256",
        "terminal_normalizer_port_class_id",
        "terminal_normalizer_port_object_identity_sha256",
        "required_read_port_methods",
        "required_normalizer_port_methods",
        "required_safety_markers",
        "required_phase_sequence",
        "same_read_port_instance_required",
        "same_normalizer_port_instance_required",
        "initial_and_final_snapshot_required",
        "initial_and_final_audit_required",
        "complete_prepared_catalog_required",
        "complete_resolved_catalog_required",
        "backend_capability_probe_required",
        "terminal_receipt_normalization_required",
        "exact_scope_cross_binding_required",
        "read_only_port_required",
        "ports_bound",
        "ports_called",
        "snapshot_read",
        "audit_read",
        "prepared_catalog_read",
        "resolved_catalog_read",
        "capability_probe_read",
        "terminal_receipt_normalized",
        "evidence_created",
        "evidence_builder_available",
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
    "PORT_BINDING_IS_PROCESS_LOCAL_AND_SYNTHETIC",
    "PRODUCTION_READ_PORT_IMPLEMENTATION_NOT_BOUND",
    "PRODUCTION_RESOLVED_CATALOG_PORT_NOT_IMPLEMENTED",
    "PRODUCTION_CAPABILITY_PROBE_PORT_NOT_IMPLEMENTED",
    "PRODUCTION_TERMINAL_RECEIPT_NORMALIZER_NOT_IMPLEMENTED",
    "PORT_OUTPUTS_HAVE_NOT_BEEN_COLLECTED_OR_VALIDATED",
    "LIVE_LEASE_AND_DURABLE_STATE_HAVE_NOT_BEEN_REVALIDATED",
    "EVIDENCE_BUILDER_AND_EVIDENCE_POPULATION_REMAIN_FORBIDDEN",
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


def _class_id(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def startup_recovery_evidence_builder_port_object_identity_sha256_v1(
    value: Any,
) -> str:
    return _stable_sha256(
        {
            "class_id": _class_id(value),
            "process_object_id": id(value),
        }
    )


def startup_recovery_evidence_builder_port_binding_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("port binding must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


def _port_safe(value: Any, required_methods: tuple[str, ...]) -> bool:
    if value is None:
        return False
    value_type = type(value)
    try:
        return bool(
            all(
                getattr(value_type, marker_name, None) is expected
                for marker_name, expected in _SAFETY_MARKERS.items()
            )
            and all(
                callable(getattr(value_type, method_name, None))
                for method_name in required_methods
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantStartupRecoveryEvidenceBuilderPortsConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_scope_binding_sha256: str | None = field(default=None, repr=False)
    expected_read_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_normalizer_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryEvidenceBuilderPortBindingV1:
    protected_scope_binding: scope_binding_v1.ProtectedStartupRecoveryBatchEvidenceScopeBindingV1 = field(
        repr=False
    )
    evidence_read_port: Any = field(repr=False)
    terminal_normalizer_port: Any = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryEvidenceBuilderPortBindingV1(<protected>)"


def protected_startup_recovery_evidence_builder_port_binding_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryEvidenceBuilderPortBindingV1
    ):
        return False
    if not (
        scope_binding_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
            value.protected_scope_binding
        )
        and _port_safe(value.evidence_read_port, _READ_PORT_METHODS)
        and _port_safe(
            value.terminal_normalizer_port, _NORMALIZER_PORT_METHODS
        )
    ):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    scope = value.protected_scope_binding.binding
    try:
        return bool(
            binding["binding_version"]
            == PROTECTED_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORT_BINDING_VERSION_V1
            and binding["scope_attestation"]
            == OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1
            and binding["scope_binding_sha256"]
            == value.protected_scope_binding.binding_sha256
            and all(
                binding[field_name] == scope[source_field]
                for field_name, source_field in (
                    ("schema_sha256", "schema_sha256"),
                    ("provider_binding_sha256", "provider_binding_sha256"),
                    ("backend_instance_sha256", "backend_instance_sha256"),
                    (
                        "registry_path_binding_sha256",
                        "registry_path_binding_sha256",
                    ),
                    ("wal_storage_binding_sha256", "wal_storage_binding_sha256"),
                    (
                        "resolved_ledger_storage_binding_sha256",
                        "resolved_ledger_storage_binding_sha256",
                    ),
                    ("lock_namespace_sha256", "lock_namespace_sha256"),
                    (
                        "pending_catalog_binding_sha256",
                        "pending_catalog_binding_sha256",
                    ),
                    ("maintenance_epoch", "maintenance_epoch"),
                    (
                        "maintenance_lease_receipt_sha256",
                        "candidate_maintenance_lease_receipt_sha256",
                    ),
                    (
                        "authenticated_authority_receipt_sha256",
                        "candidate_authenticated_authority_receipt_sha256",
                    ),
                )
            )
            and binding["evidence_read_port_class_id"]
            == _class_id(value.evidence_read_port)
            and binding["evidence_read_port_object_identity_sha256"]
            == startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                value.evidence_read_port
            )
            and binding["terminal_normalizer_port_class_id"]
            == _class_id(value.terminal_normalizer_port)
            and binding["terminal_normalizer_port_object_identity_sha256"]
            == startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                value.terminal_normalizer_port
            )
            and binding["required_read_port_methods"] == list(_READ_PORT_METHODS)
            and binding["required_normalizer_port_methods"]
            == list(_NORMALIZER_PORT_METHODS)
            and binding["required_safety_markers"] == dict(_SAFETY_MARKERS)
            and binding["required_phase_sequence"] == list(_PHASE_SEQUENCE)
            and all(
                binding[field_name] is True
                for field_name in (
                    "same_read_port_instance_required",
                    "same_normalizer_port_instance_required",
                    "initial_and_final_snapshot_required",
                    "initial_and_final_audit_required",
                    "complete_prepared_catalog_required",
                    "complete_resolved_catalog_required",
                    "backend_capability_probe_required",
                    "terminal_receipt_normalization_required",
                    "exact_scope_cross_binding_required",
                    "read_only_port_required",
                    "ports_bound",
                    "no_order_sent",
                    "synthetic_only",
                )
            )
            and all(
                binding[field_name] is False
                for field_name in (
                    "ports_called",
                    "snapshot_read",
                    "audit_read",
                    "prepared_catalog_read",
                    "resolved_catalog_read",
                    "capability_probe_read",
                    "terminal_receipt_normalized",
                    "evidence_created",
                    "evidence_builder_available",
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
                startup_recovery_evidence_builder_port_binding_sha256_v1(
                    binding
                ),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryEvidenceBuilderPortsContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryEvidenceBuilderPortsConfigV1 | None = None,
    ) -> None:
        self._config = config or DormantStartupRecoveryEvidenceBuilderPortsConfigV1()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "scope_binding_verified": False,
            "read_port_verified": False,
            "normalizer_port_verified": False,
            "port_instances_bound": False,
            "ports_called": False,
            "evidence_created": False,
            "evidence_builder_available": False,
            "evidence_population_allowed": False,
            "recovery_authority_granted": False,
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
            "protected_port_binding": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "EVIDENCE_BUILDER_PORTS_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1
        ):
            return "EVIDENCE_BUILDER_PORTS_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                self._config.expected_scope_binding_sha256,
                self._config.expected_read_port_object_identity_sha256,
                self._config.expected_normalizer_port_object_identity_sha256,
            )
        ):
            return "EVIDENCE_BUILDER_PORTS_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        protected_scope_binding: Any,
        evidence_read_port: Any,
        terminal_normalizer_port: Any,
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
        read_identity = startup_recovery_evidence_builder_port_object_identity_sha256_v1(
            evidence_read_port
        )
        if not (
            _port_safe(evidence_read_port, _READ_PORT_METHODS)
            and hmac.compare_digest(
                read_identity,
                str(self._config.expected_read_port_object_identity_sha256),
            )
        ):
            result["reasons"].append("EVIDENCE_READ_PORT_INVALID")
            return result
        result["read_port_verified"] = True
        normalizer_identity = (
            startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                terminal_normalizer_port
            )
        )
        if not (
            _port_safe(terminal_normalizer_port, _NORMALIZER_PORT_METHODS)
            and hmac.compare_digest(
                normalizer_identity,
                str(self._config.expected_normalizer_port_object_identity_sha256),
            )
        ):
            result["reasons"].append("TERMINAL_NORMALIZER_PORT_INVALID")
            return result
        result["normalizer_port_verified"] = True
        scope = protected_scope_binding.binding
        binding = {
            "binding_version": PROTECTED_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORT_BINDING_VERSION_V1,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1,
            "scope_binding_sha256": protected_scope_binding.binding_sha256,
            "schema_sha256": scope["schema_sha256"],
            "provider_binding_sha256": scope["provider_binding_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "registry_path_binding_sha256": scope[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": scope["wal_storage_binding_sha256"],
            "resolved_ledger_storage_binding_sha256": scope[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": scope["lock_namespace_sha256"],
            "pending_catalog_binding_sha256": scope[
                "pending_catalog_binding_sha256"
            ],
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "candidate_maintenance_lease_receipt_sha256"
            ],
            "authenticated_authority_receipt_sha256": scope[
                "candidate_authenticated_authority_receipt_sha256"
            ],
            "evidence_read_port_class_id": _class_id(evidence_read_port),
            "evidence_read_port_object_identity_sha256": read_identity,
            "terminal_normalizer_port_class_id": _class_id(
                terminal_normalizer_port
            ),
            "terminal_normalizer_port_object_identity_sha256": normalizer_identity,
            "required_read_port_methods": list(_READ_PORT_METHODS),
            "required_normalizer_port_methods": list(_NORMALIZER_PORT_METHODS),
            "required_safety_markers": dict(_SAFETY_MARKERS),
            "required_phase_sequence": list(_PHASE_SEQUENCE),
            "same_read_port_instance_required": True,
            "same_normalizer_port_instance_required": True,
            "initial_and_final_snapshot_required": True,
            "initial_and_final_audit_required": True,
            "complete_prepared_catalog_required": True,
            "complete_resolved_catalog_required": True,
            "backend_capability_probe_required": True,
            "terminal_receipt_normalization_required": True,
            "exact_scope_cross_binding_required": True,
            "read_only_port_required": True,
            "ports_bound": True,
            "ports_called": False,
            "snapshot_read": False,
            "audit_read": False,
            "prepared_catalog_read": False,
            "resolved_catalog_read": False,
            "capability_probe_read": False,
            "terminal_receipt_normalized": False,
            "evidence_created": False,
            "evidence_builder_available": False,
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
            startup_recovery_evidence_builder_port_binding_sha256_v1(binding)
        )
        protected = ProtectedStartupRecoveryEvidenceBuilderPortBindingV1(
            protected_scope_binding=protected_scope_binding,
            evidence_read_port=evidence_read_port,
            terminal_normalizer_port=terminal_normalizer_port,
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_startup_recovery_evidence_builder_port_binding_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_PORT_BINDING_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_BOUND_DORMANT",
            port_instances_bound=True,
            protected_port_binding=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryEvidenceBuilderPortsConfigV1",
    "DormantStartupRecoveryEvidenceBuilderPortsContractV1",
    "OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORT_BINDING_VERSION_V1",
    "ProtectedStartupRecoveryEvidenceBuilderPortBindingV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_CONTRACT_V1_VERSION",
    "protected_startup_recovery_evidence_builder_port_binding_valid_v1",
    "startup_recovery_evidence_builder_port_binding_sha256_v1",
    "startup_recovery_evidence_builder_port_object_identity_sha256_v1",
]
