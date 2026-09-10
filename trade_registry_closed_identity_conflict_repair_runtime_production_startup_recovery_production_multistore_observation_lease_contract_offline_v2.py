"""Dormant production-shaped two-store observation lease contract.

The module binds sanitized lock-port projections only.  It intentionally has
no acquire/release implementation and never imports, opens, or calls a real
store.  A later runtime composition must provide authenticated authority,
writer coordination, maintenance leasing, and the exact two persistent lock
ports before acquisition can become possible.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-MULTISTORE-OBSERVATION-"
    "LEASE-CONTRACT-OFFLINE-V2"
)
OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2 = (
    "C3_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_ONLY_V2"
)
PRODUCTION_STORE_LOCK_PORT_PROJECTION_VERSION_V2 = (
    "C3_PRODUCTION_STORE_LOCK_PORT_PROJECTION_OFFLINE_V2"
)
PRODUCTION_MULTISTORE_OBSERVATION_LEASE_BINDING_VERSION_V2 = (
    "C3_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_BINDING_OFFLINE_V2"
)
EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2 = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-"
    "RAW-TRANSACTION-STORE-PRODUCTION-V1"
)
EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2 = (
    "C3-DURABLE-RESOLVED-AUTHORITY-LEDGER-PRODUCTION-V2-REQUIRED"
)
TRANSACTION_STORE_ROLE_V2 = "RAW_TRANSACTION_STORE"
RESOLVED_AUTHORITY_STORE_ROLE_V2 = "RESOLVED_AUTHORITY_LEDGER"
LOCK_ORDER_V2 = (
    TRANSACTION_STORE_ROLE_V2,
    RESOLVED_AUTHORITY_STORE_ROLE_V2,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PORT_PROJECTION_KEYS = frozenset(
    {
        "projection_version",
        "port_role",
        "source_contract_version",
        "storage_scope",
        "store_identity_sha256",
        "storage_binding_sha256",
        "lock_namespace_sha256",
        "lock_backend_kind",
        "lock_acquire_operation",
        "lock_release_operation",
        "exclusive_lock_required",
        "cross_process_lock_required",
        "durable_storage_required",
        "writer_coordination_required",
        "read_only_observation",
        "synthetic_projection_only",
        "production_store_referenced",
        "production_authority",
        "projection_sha256",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "transaction_store_projection_sha256",
        "resolved_authority_store_projection_sha256",
        "transaction_store_identity_sha256",
        "resolved_authority_store_identity_sha256",
        "transaction_store_storage_binding_sha256",
        "resolved_authority_store_storage_binding_sha256",
        "transaction_store_lock_namespace_sha256",
        "resolved_authority_store_lock_namespace_sha256",
        "writer_coordination_binding_sha256",
        "maintenance_lease_contract_sha256",
        "authenticated_authority_contract_sha256",
        "lock_order",
        "lock_order_sha256",
        "required_lock_count",
        "required_writer_count",
        "max_lease_ttl_seconds",
        "max_lock_acquire_timeout_seconds",
        "same_lease_instance_required",
        "same_authenticated_authority_instance_required",
        "same_writer_coordinator_instance_required",
        "maintenance_lease_required",
        "pending_transaction_recovery_required_before_readiness",
        "all_reads_token_gated_required",
        "lease_deadline_required",
        "reverse_order_release_required",
        "fail_closed_on_partial_acquisition",
        "fail_closed_on_expiry",
        "fail_closed_on_store_substitution",
        "persistent_production_storage_required",
        "production_lock_ports_bound",
        "authenticated_authority_bound",
        "writer_coordination_bound",
        "maintenance_lease_bound",
        "lease_acquire_allowed",
        "lease_release_called",
        "store_called",
        "filesystem_accessed",
        "network_accessed",
        "synthetic_contract_only",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "activation_allowed",
        "live_allowed",
        "write_executed",
        "registry_write",
        "real_registry_accessed",
        "broker_called",
        "no_order_sent",
        "binding_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "LOCK_PORTS_ARE_SANITIZED_PROJECTIONS_ONLY",
    "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_IS_NOT_IMPLEMENTED",
    "AUTHENTICATED_PERSISTENT_AUTHORITY_IS_NOT_BOUND",
    "WRITER_COORDINATOR_INSTANCE_IS_NOT_BOUND",
    "MAINTENANCE_LEASE_INSTANCE_IS_NOT_BOUND",
    "NO_LOCK_ACQUISITION_SURFACE_EXISTS",
    "RUNTIME_RECOVERY_READINESS_ACTIVATION_AND_LIVE_REMAIN_FORBIDDEN",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return hash_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def production_store_lock_port_projection_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("store lock port projection must be a mapping")
    return _hash_without(value, "projection_sha256")


def production_multistore_observation_lease_binding_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("multistore lease binding must be a mapping")
    return _hash_without(value, "binding_sha256")


@dataclass(frozen=True, repr=False)
class ProtectedProductionStoreLockPortProjectionV2:
    port_role: str = field(repr=False)
    store_identity_sha256: str = field(repr=False)
    projection: Mapping[str, Any] = field(repr=False)
    projection_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionStoreLockPortProjectionV2(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedProductionMultistoreObservationLeaseBindingV2:
    transaction_store_projection_sha256: str = field(repr=False)
    resolved_authority_store_projection_sha256: str = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return (
            "ProtectedProductionMultistoreObservationLeaseBindingV2"
            "(<protected>)"
        )


def _expected_source_version(role: str) -> str:
    if role == TRANSACTION_STORE_ROLE_V2:
        return EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2
    if role == RESOLVED_AUTHORITY_STORE_ROLE_V2:
        return EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
    return ""


def production_store_lock_port_projection_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedProductionStoreLockPortProjectionV2:
        return False
    try:
        projection = copy.deepcopy(dict(value.projection))
        supplied = str(projection.get("projection_sha256") or "")
        role = str(projection.get("port_role") or "")
        return bool(
            set(projection) == _PORT_PROJECTION_KEYS
            and projection["projection_version"]
            == PRODUCTION_STORE_LOCK_PORT_PROJECTION_VERSION_V2
            and role in LOCK_ORDER_V2
            and projection["source_contract_version"]
            == _expected_source_version(role)
            and projection["storage_scope"] == "EXPLICIT_PRODUCTION"
            and all(
                _valid_sha(projection[key])
                for key in (
                    "store_identity_sha256",
                    "storage_binding_sha256",
                    "lock_namespace_sha256",
                    "projection_sha256",
                )
            )
            and projection["lock_backend_kind"]
            == "CROSS_PROCESS_ADVISORY_EXCLUSIVE"
            and projection["lock_acquire_operation"] == "acquire_exclusive"
            and projection["lock_release_operation"] == "release"
            and all(
                projection[key] is True
                for key in (
                    "exclusive_lock_required",
                    "cross_process_lock_required",
                    "durable_storage_required",
                    "writer_coordination_required",
                    "read_only_observation",
                    "synthetic_projection_only",
                )
            )
            and projection["production_store_referenced"] is False
            and projection["production_authority"] is False
            and value.port_role == role
            and value.store_identity_sha256
            == projection["store_identity_sha256"]
            and value.projection_sha256 == supplied
            and hmac.compare_digest(
                supplied,
                production_store_lock_port_projection_sha256_v2(projection),
            )
        )
    except Exception:
        return False


def build_production_store_lock_port_projection_offline_v2(
    *,
    port_role: str,
    source_contract_version: str,
    store_identity_sha256: str,
    storage_binding_sha256: str,
    lock_namespace_sha256: str,
) -> ProtectedProductionStoreLockPortProjectionV2:
    role = str(port_role or "").upper().strip()
    if not (
        role in LOCK_ORDER_V2
        and source_contract_version == _expected_source_version(role)
        and all(
            _valid_sha(item)
            for item in (
                store_identity_sha256,
                storage_binding_sha256,
                lock_namespace_sha256,
            )
        )
    ):
        raise ValueError("PRODUCTION_STORE_LOCK_PORT_PROJECTION_INPUT_INVALID")
    projection = {
        "projection_version": PRODUCTION_STORE_LOCK_PORT_PROJECTION_VERSION_V2,
        "port_role": role,
        "source_contract_version": source_contract_version,
        "storage_scope": "EXPLICIT_PRODUCTION",
        "store_identity_sha256": str(store_identity_sha256),
        "storage_binding_sha256": str(storage_binding_sha256),
        "lock_namespace_sha256": str(lock_namespace_sha256),
        "lock_backend_kind": "CROSS_PROCESS_ADVISORY_EXCLUSIVE",
        "lock_acquire_operation": "acquire_exclusive",
        "lock_release_operation": "release",
        "exclusive_lock_required": True,
        "cross_process_lock_required": True,
        "durable_storage_required": True,
        "writer_coordination_required": True,
        "read_only_observation": True,
        "synthetic_projection_only": True,
        "production_store_referenced": False,
        "production_authority": False,
    }
    projection["projection_sha256"] = (
        production_store_lock_port_projection_sha256_v2(projection)
    )
    protected = ProtectedProductionStoreLockPortProjectionV2(
        port_role=role,
        store_identity_sha256=projection["store_identity_sha256"],
        projection=copy.deepcopy(projection),
        projection_sha256=projection["projection_sha256"],
    )
    if not production_store_lock_port_projection_valid_v2(protected):
        raise ValueError("PRODUCTION_STORE_LOCK_PORT_PROJECTION_INTERNAL_INVALID")
    return protected


@dataclass(frozen=True)
class DormantProductionMultistoreObservationLeaseConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_transaction_store_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_authority_store_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_writer_coordination_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_maintenance_lease_contract_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authenticated_authority_contract_sha256: str | None = field(
        default=None, repr=False
    )
    required_writer_count: int = 19

    def __post_init__(self) -> None:
        if self.required_writer_count != 19:
            raise ValueError("required_writer_count must be exactly 19")


def protected_production_multistore_observation_lease_binding_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedProductionMultistoreObservationLeaseBindingV2:
        return False
    try:
        binding = copy.deepcopy(dict(value.binding))
        supplied = str(binding.get("binding_sha256") or "")
        required_true = (
            "same_lease_instance_required",
            "same_authenticated_authority_instance_required",
            "same_writer_coordinator_instance_required",
            "maintenance_lease_required",
            "pending_transaction_recovery_required_before_readiness",
            "all_reads_token_gated_required",
            "lease_deadline_required",
            "reverse_order_release_required",
            "fail_closed_on_partial_acquisition",
            "fail_closed_on_expiry",
            "fail_closed_on_store_substitution",
            "persistent_production_storage_required",
            "synthetic_contract_only",
            "no_order_sent",
        )
        required_false = (
            "production_lock_ports_bound",
            "authenticated_authority_bound",
            "writer_coordination_bound",
            "maintenance_lease_bound",
            "lease_acquire_allowed",
            "lease_release_called",
            "store_called",
            "filesystem_accessed",
            "network_accessed",
            "production_authority",
            "production_ready",
            "runtime_integrated",
            "recovery_execution_allowed",
            "activation_allowed",
            "live_allowed",
            "write_executed",
            "registry_write",
            "real_registry_accessed",
            "broker_called",
        )
        return bool(
            set(binding) == _BINDING_KEYS
            and binding["binding_version"]
            == PRODUCTION_MULTISTORE_OBSERVATION_LEASE_BINDING_VERSION_V2
            and binding["scope_attestation"]
            == OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
            and all(
                _valid_sha(binding[key])
                for key in (
                    "transaction_store_projection_sha256",
                    "resolved_authority_store_projection_sha256",
                    "transaction_store_identity_sha256",
                    "resolved_authority_store_identity_sha256",
                    "transaction_store_storage_binding_sha256",
                    "resolved_authority_store_storage_binding_sha256",
                    "transaction_store_lock_namespace_sha256",
                    "resolved_authority_store_lock_namespace_sha256",
                    "writer_coordination_binding_sha256",
                    "maintenance_lease_contract_sha256",
                    "authenticated_authority_contract_sha256",
                    "lock_order_sha256",
                    "binding_sha256",
                )
            )
            and binding["transaction_store_identity_sha256"]
            != binding["resolved_authority_store_identity_sha256"]
            and binding["transaction_store_storage_binding_sha256"]
            != binding["resolved_authority_store_storage_binding_sha256"]
            and binding["transaction_store_lock_namespace_sha256"]
            != binding["resolved_authority_store_lock_namespace_sha256"]
            and binding["lock_order"] == list(LOCK_ORDER_V2)
            and binding["lock_order_sha256"]
            == hash_v2.stable_sha256_v2(
                {
                    "lock_order": list(LOCK_ORDER_V2),
                    "transaction_store_lock_namespace_sha256": binding[
                        "transaction_store_lock_namespace_sha256"
                    ],
                    "resolved_authority_store_lock_namespace_sha256": binding[
                        "resolved_authority_store_lock_namespace_sha256"
                    ],
                }
            )
            and binding["required_lock_count"] == 2
            and binding["required_writer_count"] == 19
            and binding["max_lease_ttl_seconds"] == 300
            and binding["max_lock_acquire_timeout_seconds"] == 1
            and all(binding[key] is True for key in required_true)
            and all(binding[key] is False for key in required_false)
            and value.transaction_store_projection_sha256
            == binding["transaction_store_projection_sha256"]
            and value.resolved_authority_store_projection_sha256
            == binding["resolved_authority_store_projection_sha256"]
            and value.binding_sha256 == supplied
            and hmac.compare_digest(
                supplied,
                production_multistore_observation_lease_binding_sha256_v2(
                    binding
                ),
            )
        )
    except Exception:
        return False


class DormantProductionMultistoreObservationLeaseContractV2:
    def __init__(
        self,
        config: DormantProductionMultistoreObservationLeaseConfigV2 | None = None,
    ) -> None:
        self._config = (
            config or DormantProductionMultistoreObservationLeaseConfigV2()
        )

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_V2_BLOCKED",
            "reason": reason,
            "protected_binding": None,
            "contract_verified": False,
            "lock_order_verified": False,
            "persistent_store_requirements_verified": False,
            "production_lock_ports_bound": False,
            "lease_acquire_allowed": False,
            "lease_release_called": False,
            "store_called": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_contract_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def bind_offline(
        self,
        *,
        transaction_store_lock_port: Any,
        resolved_authority_store_lock_port: Any,
    ) -> dict[str, Any]:
        result = self._failed("")
        config = self._config
        if config.enabled is not True:
            result["reason"] = "PRODUCTION_MULTISTORE_LEASE_CONTRACT_DEFAULT_OFF"
            return result
        if (
            config.scope_attestation
            != OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
        ):
            result["reason"] = "PRODUCTION_MULTISTORE_LEASE_CONTRACT_SCOPE_INVALID"
            return result
        pins = (
            config.expected_transaction_store_projection_sha256,
            config.expected_resolved_authority_store_projection_sha256,
            config.expected_writer_coordination_binding_sha256,
            config.expected_maintenance_lease_contract_sha256,
            config.expected_authenticated_authority_contract_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            result["reason"] = "PRODUCTION_MULTISTORE_LEASE_CONTRACT_PINS_INVALID"
            return result
        if not (
            production_store_lock_port_projection_valid_v2(
                transaction_store_lock_port
            )
            and production_store_lock_port_projection_valid_v2(
                resolved_authority_store_lock_port
            )
        ):
            result["reason"] = "PRODUCTION_MULTISTORE_LOCK_PORT_INVALID"
            return result
        transaction = copy.deepcopy(dict(transaction_store_lock_port.projection))
        resolved = copy.deepcopy(dict(resolved_authority_store_lock_port.projection))
        if not (
            transaction["port_role"] == TRANSACTION_STORE_ROLE_V2
            and resolved["port_role"] == RESOLVED_AUTHORITY_STORE_ROLE_V2
            and transaction["projection_sha256"] == pins[0]
            and resolved["projection_sha256"] == pins[1]
            and transaction["store_identity_sha256"]
            != resolved["store_identity_sha256"]
            and transaction["storage_binding_sha256"]
            != resolved["storage_binding_sha256"]
            and transaction["lock_namespace_sha256"]
            != resolved["lock_namespace_sha256"]
        ):
            result["reason"] = "PRODUCTION_MULTISTORE_LOCK_PORT_CROSS_BINDING_INVALID"
            return result
        lock_order_sha = hash_v2.stable_sha256_v2(
            {
                "lock_order": list(LOCK_ORDER_V2),
                "transaction_store_lock_namespace_sha256": transaction[
                    "lock_namespace_sha256"
                ],
                "resolved_authority_store_lock_namespace_sha256": resolved[
                    "lock_namespace_sha256"
                ],
            }
        )
        binding = {
            "binding_version": PRODUCTION_MULTISTORE_OBSERVATION_LEASE_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2,
            "transaction_store_projection_sha256": transaction[
                "projection_sha256"
            ],
            "resolved_authority_store_projection_sha256": resolved[
                "projection_sha256"
            ],
            "transaction_store_identity_sha256": transaction[
                "store_identity_sha256"
            ],
            "resolved_authority_store_identity_sha256": resolved[
                "store_identity_sha256"
            ],
            "transaction_store_storage_binding_sha256": transaction[
                "storage_binding_sha256"
            ],
            "resolved_authority_store_storage_binding_sha256": resolved[
                "storage_binding_sha256"
            ],
            "transaction_store_lock_namespace_sha256": transaction[
                "lock_namespace_sha256"
            ],
            "resolved_authority_store_lock_namespace_sha256": resolved[
                "lock_namespace_sha256"
            ],
            "writer_coordination_binding_sha256": str(pins[2]),
            "maintenance_lease_contract_sha256": str(pins[3]),
            "authenticated_authority_contract_sha256": str(pins[4]),
            "lock_order": list(LOCK_ORDER_V2),
            "lock_order_sha256": lock_order_sha,
            "required_lock_count": 2,
            "required_writer_count": 19,
            "max_lease_ttl_seconds": 300,
            "max_lock_acquire_timeout_seconds": 1,
            "same_lease_instance_required": True,
            "same_authenticated_authority_instance_required": True,
            "same_writer_coordinator_instance_required": True,
            "maintenance_lease_required": True,
            "pending_transaction_recovery_required_before_readiness": True,
            "all_reads_token_gated_required": True,
            "lease_deadline_required": True,
            "reverse_order_release_required": True,
            "fail_closed_on_partial_acquisition": True,
            "fail_closed_on_expiry": True,
            "fail_closed_on_store_substitution": True,
            "persistent_production_storage_required": True,
            "production_lock_ports_bound": False,
            "authenticated_authority_bound": False,
            "writer_coordination_bound": False,
            "maintenance_lease_bound": False,
            "lease_acquire_allowed": False,
            "lease_release_called": False,
            "store_called": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "synthetic_contract_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        binding["binding_sha256"] = (
            production_multistore_observation_lease_binding_sha256_v2(binding)
        )
        protected = ProtectedProductionMultistoreObservationLeaseBindingV2(
            transaction_store_projection_sha256=binding[
                "transaction_store_projection_sha256"
            ],
            resolved_authority_store_projection_sha256=binding[
                "resolved_authority_store_projection_sha256"
            ],
            binding=copy.deepcopy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_production_multistore_observation_lease_binding_valid_v2(
            protected
        ):
            result["reason"] = "PRODUCTION_MULTISTORE_LEASE_BINDING_INTERNAL_INVALID"
            return result
        result.update(
            {
                "ok": True,
                "status": "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_V2_VERIFIED_OFFLINE",
                "reason": None,
                "protected_binding": protected,
                "contract_verified": True,
                "lock_order_verified": True,
                "persistent_store_requirements_verified": True,
            }
        )
        return result


__all__ = [
    "DormantProductionMultistoreObservationLeaseConfigV2",
    "DormantProductionMultistoreObservationLeaseContractV2",
    "EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2",
    "EXPECTED_TRANSACTION_STORE_CONTRACT_VERSION_V2",
    "LOCK_ORDER_V2",
    "OFFLINE_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2",
    "PRODUCTION_MULTISTORE_OBSERVATION_LEASE_BINDING_VERSION_V2",
    "PRODUCTION_STORE_LOCK_PORT_PROJECTION_VERSION_V2",
    "ProtectedProductionMultistoreObservationLeaseBindingV2",
    "ProtectedProductionStoreLockPortProjectionV2",
    "RESOLVED_AUTHORITY_STORE_ROLE_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_CONTRACT_OFFLINE_V2_VERSION",
    "TRANSACTION_STORE_ROLE_V2",
    "build_production_store_lock_port_projection_offline_v2",
    "production_multistore_observation_lease_binding_sha256_v2",
    "production_store_lock_port_projection_sha256_v2",
    "production_store_lock_port_projection_valid_v2",
    "protected_production_multistore_observation_lease_binding_valid_v2",
]
