"""Dormant V2 contract for future production startup-recovery evidence ports.

The contract binds only process-local synthetic interface doubles.  No port is
called and no production, durability, recovery, runtime, or Live authority is
created.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as authority_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as scope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_CONTRACT_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SOURCE-PORTS-CONTRACT-V2"
)
OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2 = (
    "C3_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_CONTRACT_OFFLINE_ONLY_V2"
)
PROTECTED_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORT_BINDING_VERSION_V2 = (
    "C3_PROTECTED_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORT_BINDING_DORMANT_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_READ_METHODS = (
    "read_backend_snapshot_offline",
    "read_transaction_log_audit_offline",
    "read_prepared_catalog_offline",
    "read_resolved_catalog_offline",
    "read_backend_capability_probe_offline",
)
_NORMALIZER_METHODS = ("normalize_terminal_receipt_offline",)
_PORT_MARKERS = {
    "contract_binding_only": True,
    "default_off": True,
    "synthetic_only": True,
    "port_calls_allowed": False,
    "filesystem_access_allowed": False,
    "network_access_allowed": False,
    "production_access_allowed": False,
    "write_allowed": False,
}
_ANCHOR_NAMES = (
    "backend_instance",
    "coordinator_instance",
    "maintenance_lease_witness",
    "protected_authenticated_authority_binding",
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
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "authenticated_authority_binding_sha256",
        "authenticated_authority_receipt_sha256",
        "read_port_class_id",
        "read_port_object_identity_sha256",
        "normalizer_port_class_id",
        "normalizer_port_object_identity_sha256",
        "backend_object_identity_sha256",
        "coordinator_object_identity_sha256",
        "maintenance_lease_witness_object_identity_sha256",
        "required_read_methods",
        "required_normalizer_methods",
        "required_port_markers",
        "required_port_count",
        "same_backend_instance_required",
        "same_coordinator_instance_required",
        "same_maintenance_lease_instance_required",
        "same_authenticated_authority_instance_required",
        "exact_scope_cross_binding_required",
        "complete_prepared_catalog_required",
        "complete_resolved_catalog_required",
        "resolved_state_support_required",
        "empirical_durability_probe_required",
        "authenticated_authority_current_state_revalidation_required",
        "maintenance_lease_revalidation_per_call_required",
        "atomic_observation_window_required",
        "fail_closed_required",
        "interface_verified",
        "object_identity_vector_verified",
        "anchor_identity_vector_verified",
        "ports_bound",
        "ports_called",
        "backend_called",
        "coordinator_called",
        "maintenance_lease_called",
        "authority_revalidated",
        "durability_verified",
        "resolved_catalog_verified",
        "evidence_created",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "registry_write",
        "no_order_sent",
        "synthetic_only",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "binding_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "ONLY_SYNTHETIC_PROCESS_LOCAL_INTERFACES_ARE_BOUND",
    "PRODUCTION_PROVIDER_AND_BACKEND_INSTANCES_ARE_NOT_BOUND",
    "PORT_OUTPUTS_HAVE_NOT_BEEN_COLLECTED_OR_VALIDATED",
    "COMPLETE_RESOLVED_CATALOG_HAS_NOT_BEEN_VERIFIED",
    "EMPIRICAL_DURABILITY_PROBE_HAS_NOT_BEEN_EXECUTED",
    "AUTHENTICATED_AUTHORITY_CURRENT_STATE_HAS_NOT_BEEN_REVALIDATED",
    "MAINTENANCE_LEASE_HAS_NOT_BEEN_REVALIDATED_AT_A_PORT_CALL",
    "ATOMIC_PRODUCTION_OBSERVATION_WINDOW_HAS_NOT_BEEN_PROVEN",
    "PRODUCTION_EVIDENCE_BUILDER_AND_RUNTIME_REMAIN_DISCONNECTED",
    "RECOVERY_READINESS_ACTIVATION_AND_LIVE_REMAIN_FORBIDDEN",
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


def startup_recovery_evidence_source_object_identity_sha256_v2(
    value: Any,
) -> str:
    return _stable_sha256(
        {"class_id": _class_id(value), "process_object_id": id(value)}
    )


def startup_recovery_evidence_source_port_binding_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("evidence source port binding must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


def _instance_dict(value: Any) -> dict[str, Any] | None:
    try:
        instance = vars(value)
    except Exception:
        return None
    return instance if type(instance) is dict else None


def _port_safe(value: Any, methods: tuple[str, ...]) -> bool:
    instance = _instance_dict(value)
    type_dict = vars(type(value)) if value is not None else {}
    return bool(
        instance is not None
        and all(type_dict.get(name) is expected for name, expected in _PORT_MARKERS.items())
        and all(callable(type_dict.get(name)) for name in methods)
        and all(name in instance for name in _ANCHOR_NAMES)
    )


@dataclass(frozen=True)
class DormantStartupRecoveryEvidenceSourcePortsConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_scope_binding_sha256: str | None = field(default=None, repr=False)
    expected_read_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_normalizer_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_backend_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_coordinator_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_maintenance_lease_witness_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authenticated_authority_binding_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryEvidenceSourcePortBindingV2:
    protected_scope_binding: Any = field(repr=False)
    evidence_read_port: Any = field(repr=False)
    terminal_normalizer_port: Any = field(repr=False)
    backend_instance: Any = field(repr=False)
    coordinator_instance: Any = field(repr=False)
    maintenance_lease_witness: Any = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryEvidenceSourcePortBindingV2(<protected>)"


def _anchors_match(
    *,
    protected_scope_binding: Any,
    evidence_read_port: Any,
    terminal_normalizer_port: Any,
    backend_instance: Any,
    coordinator_instance: Any,
    maintenance_lease_witness: Any,
) -> bool:
    if not scope_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
        protected_scope_binding
    ):
        return False
    authority = (
        protected_scope_binding.protected_batch_session
        .authenticated_authority_binding
    )
    if not authority_v1.protected_startup_recovery_authenticated_authority_binding_valid_v1(
        authority
    ):
        return False
    read = _instance_dict(evidence_read_port)
    normalizer = _instance_dict(terminal_normalizer_port)
    backend = _instance_dict(backend_instance)
    coordinator = _instance_dict(coordinator_instance)
    lease = _instance_dict(maintenance_lease_witness)
    if any(item is None for item in (read, normalizer, backend, coordinator, lease)):
        return False
    scope = protected_scope_binding.binding
    try:
        return bool(
            read["backend_instance"] is backend_instance
            and normalizer["backend_instance"] is backend_instance
            and read["coordinator_instance"] is coordinator_instance
            and normalizer["coordinator_instance"] is coordinator_instance
            and read["maintenance_lease_witness"] is maintenance_lease_witness
            and normalizer["maintenance_lease_witness"]
            is maintenance_lease_witness
            and read["protected_authenticated_authority_binding"] is authority
            and normalizer["protected_authenticated_authority_binding"] is authority
            and backend["backend_instance_sha256"]
            == scope["backend_instance_sha256"]
            and backend["registry_path_binding_sha256"]
            == scope["registry_path_binding_sha256"]
            and backend["wal_storage_binding_sha256"]
            == scope["wal_storage_binding_sha256"]
            and backend["resolved_ledger_storage_binding_sha256"]
            == scope["resolved_ledger_storage_binding_sha256"]
            and coordinator["lock_namespace_sha256"]
            == scope["lock_namespace_sha256"]
            and lease["maintenance_epoch"] == scope["maintenance_epoch"]
            and lease["receipt_sha256"]
            == scope["candidate_maintenance_lease_receipt_sha256"]
            and authority.binding_sha256
            == protected_scope_binding.protected_batch_session.receipt[
                "authenticated_authority_binding_sha256"
            ]
            and authority.binding[
                "candidate_authenticated_authority_receipt_sha256"
            ]
            == scope["candidate_authenticated_authority_receipt_sha256"]
        )
    except Exception:
        return False


def protected_startup_recovery_evidence_source_port_binding_valid_v2(
    value: Any,
) -> bool:
    if not isinstance(value, ProtectedStartupRecoveryEvidenceSourcePortBindingV2):
        return False
    if not (
        _port_safe(value.evidence_read_port, _READ_METHODS)
        and _port_safe(value.terminal_normalizer_port, _NORMALIZER_METHODS)
        and _anchors_match(
            protected_scope_binding=value.protected_scope_binding,
            evidence_read_port=value.evidence_read_port,
            terminal_normalizer_port=value.terminal_normalizer_port,
            backend_instance=value.backend_instance,
            coordinator_instance=value.coordinator_instance,
            maintenance_lease_witness=value.maintenance_lease_witness,
        )
    ):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    scope = value.protected_scope_binding.binding
    authority = (
        value.protected_scope_binding.protected_batch_session
        .authenticated_authority_binding
    )
    try:
        return bool(
            binding["binding_version"]
            == PROTECTED_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORT_BINDING_VERSION_V2
            and binding["scope_attestation"]
            == OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2
            and binding["scope_binding_sha256"]
            == value.protected_scope_binding.binding_sha256
            and all(
                binding[field_name] == scope[scope_name]
                for field_name, scope_name in (
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
            and binding["authenticated_authority_binding_sha256"]
            == authority.binding_sha256
            and binding["read_port_class_id"] == _class_id(value.evidence_read_port)
            and binding["normalizer_port_class_id"]
            == _class_id(value.terminal_normalizer_port)
            and binding["read_port_object_identity_sha256"]
            == startup_recovery_evidence_source_object_identity_sha256_v2(
                value.evidence_read_port
            )
            and binding["normalizer_port_object_identity_sha256"]
            == startup_recovery_evidence_source_object_identity_sha256_v2(
                value.terminal_normalizer_port
            )
            and binding["backend_object_identity_sha256"]
            == startup_recovery_evidence_source_object_identity_sha256_v2(
                value.backend_instance
            )
            and binding["coordinator_object_identity_sha256"]
            == startup_recovery_evidence_source_object_identity_sha256_v2(
                value.coordinator_instance
            )
            and binding["maintenance_lease_witness_object_identity_sha256"]
            == startup_recovery_evidence_source_object_identity_sha256_v2(
                value.maintenance_lease_witness
            )
            and binding["required_read_methods"] == list(_READ_METHODS)
            and binding["required_normalizer_methods"] == list(_NORMALIZER_METHODS)
            and binding["required_port_markers"] == dict(_PORT_MARKERS)
            and binding["required_port_count"] == 6
            and all(
                binding[field_name] is True
                for field_name in (
                    "same_backend_instance_required",
                    "same_coordinator_instance_required",
                    "same_maintenance_lease_instance_required",
                    "same_authenticated_authority_instance_required",
                    "exact_scope_cross_binding_required",
                    "complete_prepared_catalog_required",
                    "complete_resolved_catalog_required",
                    "resolved_state_support_required",
                    "empirical_durability_probe_required",
                    "authenticated_authority_current_state_revalidation_required",
                    "maintenance_lease_revalidation_per_call_required",
                    "atomic_observation_window_required",
                    "fail_closed_required",
                    "interface_verified",
                    "object_identity_vector_verified",
                    "anchor_identity_vector_verified",
                    "ports_bound",
                    "no_order_sent",
                    "synthetic_only",
                )
            )
            and all(
                binding[field_name] is False
                for field_name in (
                    "ports_called",
                    "backend_called",
                    "coordinator_called",
                    "maintenance_lease_called",
                    "authority_revalidated",
                    "durability_verified",
                    "resolved_catalog_verified",
                    "evidence_created",
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
                startup_recovery_evidence_source_port_binding_sha256_v2(binding),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryEvidenceSourcePortsContractV2:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryEvidenceSourcePortsConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantStartupRecoveryEvidenceSourcePortsConfigV2()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_V2_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_CONTRACT_V2_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "scope_verified": False,
            "authority_binding_verified": False,
            "interface_verified": False,
            "object_identity_vector_verified": False,
            "anchor_identity_vector_verified": False,
            "ports_bound": False,
            "ports_called": False,
            "backend_called": False,
            "coordinator_called": False,
            "maintenance_lease_called": False,
            "evidence_created": False,
            "durability_verified": False,
            "resolved_catalog_verified": False,
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
            "protected_binding": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "EVIDENCE_SOURCE_PORTS_V2_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2
        ):
            return "EVIDENCE_SOURCE_PORTS_V2_SCOPE_INVALID"
        pins = (
            self._config.expected_scope_binding_sha256,
            self._config.expected_read_port_object_identity_sha256,
            self._config.expected_normalizer_port_object_identity_sha256,
            self._config.expected_backend_object_identity_sha256,
            self._config.expected_coordinator_object_identity_sha256,
            self._config.expected_maintenance_lease_witness_object_identity_sha256,
            self._config.expected_authenticated_authority_binding_sha256,
        )
        if any(not _valid_sha256(item) for item in pins):
            return "EVIDENCE_SOURCE_PORTS_V2_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        protected_scope_binding: Any,
        evidence_read_port: Any,
        terminal_normalizer_port: Any,
        backend_instance: Any,
        coordinator_instance: Any,
        maintenance_lease_witness: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not (
            scope_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                protected_scope_binding
            )
            and hmac.compare_digest(
                protected_scope_binding.binding_sha256,
                str(self._config.expected_scope_binding_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_EVIDENCE_SCOPE_INVALID")
            return result
        result["scope_verified"] = True
        authority = (
            protected_scope_binding.protected_batch_session
            .authenticated_authority_binding
        )
        if not (
            authority_v1.protected_startup_recovery_authenticated_authority_binding_valid_v1(
                authority
            )
            and hmac.compare_digest(
                authority.binding_sha256,
                str(
                    self._config.expected_authenticated_authority_binding_sha256
                ),
            )
        ):
            result["reasons"].append("AUTHENTICATED_AUTHORITY_BINDING_INVALID")
            return result
        result["authority_binding_verified"] = True
        if not (
            _port_safe(evidence_read_port, _READ_METHODS)
            and _port_safe(terminal_normalizer_port, _NORMALIZER_METHODS)
        ):
            result["reasons"].append("SIX_PORT_INTERFACE_INVALID")
            return result
        result["interface_verified"] = True
        supplied_objects = (
            (evidence_read_port, self._config.expected_read_port_object_identity_sha256),
            (
                terminal_normalizer_port,
                self._config.expected_normalizer_port_object_identity_sha256,
            ),
            (backend_instance, self._config.expected_backend_object_identity_sha256),
            (
                coordinator_instance,
                self._config.expected_coordinator_object_identity_sha256,
            ),
            (
                maintenance_lease_witness,
                self._config.expected_maintenance_lease_witness_object_identity_sha256,
            ),
        )
        if not all(
            hmac.compare_digest(
                startup_recovery_evidence_source_object_identity_sha256_v2(value),
                str(expected),
            )
            for value, expected in supplied_objects
        ):
            result["reasons"].append("EVIDENCE_SOURCE_OBJECT_IDENTITY_MISMATCH")
            return result
        result["object_identity_vector_verified"] = True
        if not _anchors_match(
            protected_scope_binding=protected_scope_binding,
            evidence_read_port=evidence_read_port,
            terminal_normalizer_port=terminal_normalizer_port,
            backend_instance=backend_instance,
            coordinator_instance=coordinator_instance,
            maintenance_lease_witness=maintenance_lease_witness,
        ):
            result["reasons"].append("EVIDENCE_SOURCE_ANCHOR_IDENTITY_MISMATCH")
            return result
        result["anchor_identity_vector_verified"] = True
        scope = protected_scope_binding.binding
        binding = {
            "binding_version": PROTECTED_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORT_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2,
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
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "candidate_maintenance_lease_receipt_sha256"
            ],
            "authenticated_authority_binding_sha256": authority.binding_sha256,
            "authenticated_authority_receipt_sha256": scope[
                "candidate_authenticated_authority_receipt_sha256"
            ],
            "read_port_class_id": _class_id(evidence_read_port),
            "read_port_object_identity_sha256": startup_recovery_evidence_source_object_identity_sha256_v2(
                evidence_read_port
            ),
            "normalizer_port_class_id": _class_id(terminal_normalizer_port),
            "normalizer_port_object_identity_sha256": startup_recovery_evidence_source_object_identity_sha256_v2(
                terminal_normalizer_port
            ),
            "backend_object_identity_sha256": startup_recovery_evidence_source_object_identity_sha256_v2(
                backend_instance
            ),
            "coordinator_object_identity_sha256": startup_recovery_evidence_source_object_identity_sha256_v2(
                coordinator_instance
            ),
            "maintenance_lease_witness_object_identity_sha256": startup_recovery_evidence_source_object_identity_sha256_v2(
                maintenance_lease_witness
            ),
            "required_read_methods": list(_READ_METHODS),
            "required_normalizer_methods": list(_NORMALIZER_METHODS),
            "required_port_markers": dict(_PORT_MARKERS),
            "required_port_count": 6,
            "same_backend_instance_required": True,
            "same_coordinator_instance_required": True,
            "same_maintenance_lease_instance_required": True,
            "same_authenticated_authority_instance_required": True,
            "exact_scope_cross_binding_required": True,
            "complete_prepared_catalog_required": True,
            "complete_resolved_catalog_required": True,
            "resolved_state_support_required": True,
            "empirical_durability_probe_required": True,
            "authenticated_authority_current_state_revalidation_required": True,
            "maintenance_lease_revalidation_per_call_required": True,
            "atomic_observation_window_required": True,
            "fail_closed_required": True,
            "interface_verified": True,
            "object_identity_vector_verified": True,
            "anchor_identity_vector_verified": True,
            "ports_bound": True,
            "ports_called": False,
            "backend_called": False,
            "coordinator_called": False,
            "maintenance_lease_called": False,
            "authority_revalidated": False,
            "durability_verified": False,
            "resolved_catalog_verified": False,
            "evidence_created": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        binding["binding_sha256"] = (
            startup_recovery_evidence_source_port_binding_sha256_v2(binding)
        )
        protected = ProtectedStartupRecoveryEvidenceSourcePortBindingV2(
            protected_scope_binding=protected_scope_binding,
            evidence_read_port=evidence_read_port,
            terminal_normalizer_port=terminal_normalizer_port,
            backend_instance=backend_instance,
            coordinator_instance=coordinator_instance,
            maintenance_lease_witness=maintenance_lease_witness,
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_startup_recovery_evidence_source_port_binding_valid_v2(
            protected
        ):
            result["reasons"].append("PROTECTED_EVIDENCE_SOURCE_BINDING_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_V2_BOUND_DORMANT",
            ports_bound=True,
            protected_binding=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryEvidenceSourcePortsConfigV2",
    "DormantStartupRecoveryEvidenceSourcePortsContractV2",
    "OFFLINE_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_SCOPE_ATTESTATION_V2",
    "PROTECTED_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORT_BINDING_VERSION_V2",
    "ProtectedStartupRecoveryEvidenceSourcePortBindingV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PORTS_CONTRACT_V2_VERSION",
    "protected_startup_recovery_evidence_source_port_binding_valid_v2",
    "startup_recovery_evidence_source_object_identity_sha256_v2",
    "startup_recovery_evidence_source_port_binding_sha256_v2",
]
