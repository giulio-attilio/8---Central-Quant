"""Dormant binding between the production-provider identity and recovery adapter.

The contract binds only an already-protected synthetic provider/store projection
to the exact startup-recovery adapter class.  It never receives an instance of
the provider or adapter, never calls either side, and deliberately records the
direct provider-port gaps that a future bridge must close.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_production_provider_v1 as production_provider
import trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1 as provider_binding_contract
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-RECOVERY-PRODUCTION-PROVIDER-BINDING-CONTRACT-V1"
)
OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_CLASS_ID = (
    "trade_registry_closed_identity_conflict_repair_production_provider_v1."
    "ProductionClosedRepairProviderV1"
)
_ADAPTER_CLASS_ID = (
    "trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_"
    "adapter_offline_v1.OfflineRuntimeStartupRecoveryAdapterV1"
)
_REQUIRED_BACKEND_PORT_METHODS = (
    "snapshot_offline",
    "list_prepared_transactions_offline",
    "inspect_transaction_log_offline",
    "reconcile_attested_transaction_offline",
)
_PROVIDER_SURFACE_MAP = (
    {
        "adapter_requirement": "snapshot_offline",
        "provider_surface": "snapshot",
        "status": "REQUIRES_EXPLICIT_BRIDGE",
    },
    {
        "adapter_requirement": "list_prepared_transactions_offline",
        "provider_surface": None,
        "status": "MISSING_FROM_PROVIDER_SURFACE",
    },
    {
        "adapter_requirement": "inspect_transaction_log_offline",
        "provider_surface": None,
        "status": "MISSING_FROM_PROVIDER_SURFACE",
    },
    {
        "adapter_requirement": "reconcile_attested_transaction_offline",
        "provider_surface": "reconcile_attested_transaction",
        "status": "REQUIRES_EXPLICIT_BRIDGE",
    },
)
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "provider_store_binding_sha256",
        "source_provider_version",
        "source_store_version",
        "source_provider_snapshot_sha256",
        "composition_attestation_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "startup_recovery_adapter_version",
        "startup_recovery_adapter_contract_sha256",
        "provider_class_id",
        "adapter_class_id",
        "required_backend_port_methods",
        "provider_surface_map",
        "same_backend_instance_required",
        "same_registry_path_binding_required",
        "same_lock_namespace_required",
        "same_maintenance_epoch_instance_required",
        "provider_projection_verified",
        "provider_instance_bound",
        "adapter_class_verified",
        "adapter_instance_bound",
        "direct_port_compatibility_verified",
        "bridge_required",
        "recovery_receipt_required",
        "startup_recovery_attestation_required",
        "provider_call_allowed",
        "adapter_call_allowed",
        "recovery_execution_allowed",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "synthetic_only",
        "binding_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "PROVIDER_INSTANCE_IS_NOT_BOUND",
    "ADAPTER_INSTANCE_IS_NOT_BOUND",
    "PROVIDER_PORT_HAS_UNRESOLVED_RECOVERY_CAPABILITY_GAPS",
    "PRODUCTION_WAL_INSPECTION_IS_NOT_BOUND",
    "PRODUCTION_PREPARED_CATALOG_IS_NOT_BOUND",
    "SAME_MAINTENANCE_EPOCH_RUNTIME_COMPOSITION_IS_NOT_BOUND",
    "NO_RECOVERY_EXECUTION_AUTHORITY_EXISTS",
    "RUNTIME_AND_READINESS_REMAIN_DISCONNECTED",
    "LIVE_TRADING_REMAINS_FORBIDDEN",
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


def startup_recovery_adapter_contract_sha256_v1() -> str:
    """Return the static contract identity without constructing the adapter."""

    return _stable_sha256(
        {
            "adapter_version": (
                startup_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION
            ),
            "adapter_class_id": _ADAPTER_CLASS_ID,
            "entrypoint": "__call__",
            "required_backend_port_methods": list(_REQUIRED_BACKEND_PORT_METHODS),
            "same_maintenance_epoch_instance_required": True,
            "startup_recovery_attestation_required": True,
            "default_off": True,
            "offline_only": True,
        }
    )


def startup_recovery_production_provider_binding_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("binding must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


@dataclass(frozen=True)
class DormantStartupRecoveryProductionProviderBindingConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_provider_store_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_adapter_contract_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryProductionProviderBindingV1:
    provider_store_binding_sha256: str = field(repr=False)
    adapter_contract_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryProductionProviderBindingV1(<protected>)"


def protected_startup_recovery_production_provider_binding_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryProductionProviderBindingV1
    ):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    supplied_sha = _valid_sha256(binding.get("binding_sha256"))
    expected_adapter_sha = startup_recovery_adapter_contract_sha256_v1()
    try:
        return bool(
            binding.get("binding_version")
            == PROTECTED_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_VERSION_V1
            and binding.get("scope_attestation")
            == OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
            and all(
                _valid_sha256(binding.get(field_name))
                for field_name in (
                    "provider_store_binding_sha256",
                    "source_provider_snapshot_sha256",
                    "composition_attestation_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "backend_capability_attestation_sha256",
                    "lock_namespace_sha256",
                    "startup_recovery_adapter_contract_sha256",
                )
            )
            and binding.get("provider_store_binding_sha256")
            == value.provider_store_binding_sha256
            and binding.get("startup_recovery_adapter_contract_sha256")
            == value.adapter_contract_sha256
            == expected_adapter_sha
            and binding.get("backend_instance_sha256")
            == value.backend_instance_sha256
            and binding.get("source_provider_version")
            == provider_binding_contract.EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1
            and binding.get("source_store_version")
            == provider_binding_contract.EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1
            and binding.get("startup_recovery_adapter_version")
            == startup_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION
            and binding.get("provider_class_id") == _PROVIDER_CLASS_ID
            and binding.get("adapter_class_id") == _ADAPTER_CLASS_ID
            and binding.get("required_backend_port_methods")
            == list(_REQUIRED_BACKEND_PORT_METHODS)
            and binding.get("provider_surface_map")
            == _canonical_copy(list(_PROVIDER_SURFACE_MAP))
            and binding.get("same_backend_instance_required") is True
            and binding.get("same_registry_path_binding_required") is True
            and binding.get("same_lock_namespace_required") is True
            and binding.get("same_maintenance_epoch_instance_required") is True
            and binding.get("provider_projection_verified") is True
            and binding.get("provider_instance_bound") is False
            and binding.get("adapter_class_verified") is True
            and binding.get("adapter_instance_bound") is False
            and binding.get("direct_port_compatibility_verified") is False
            and binding.get("bridge_required") is True
            and binding.get("recovery_receipt_required") is True
            and binding.get("startup_recovery_attestation_required") is True
            and binding.get("provider_call_allowed") is False
            and binding.get("adapter_call_allowed") is False
            and binding.get("recovery_execution_allowed") is False
            and binding.get("production_authority") is False
            and binding.get("production_ready") is False
            and binding.get("runtime_integrated") is False
            and binding.get("synthetic_only") is True
            and supplied_sha
            and supplied_sha == value.binding_sha256
            and hmac.compare_digest(
                supplied_sha,
                startup_recovery_production_provider_binding_sha256_v1(binding),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryProductionProviderBindingContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryProductionProviderBindingConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config or DormantStartupRecoveryProductionProviderBindingConfigV1()
        )

    def __repr__(self) -> str:
        return "DormantStartupRecoveryProductionProviderBindingContractV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "provider_store_binding_verified": False,
            "provider_class_verified": False,
            "adapter_class_verified": False,
            "contract_identity_verified": False,
            "identity_binding_created": False,
            "direct_port_compatibility_verified": False,
            "bridge_required": True,
            "provider_instance_bound": False,
            "adapter_instance_bound": False,
            "provider_called": False,
            "adapter_called": False,
            "recovery_executed": False,
            "runtime_integrated": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_authority": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "reasons": [],
            "protected_binding": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def bind_offline(
        self,
        *,
        protected_provider_store_binding: provider_binding_contract.ProtectedProductionProviderStoreAdapterBindingV1,
        provider_type: Any,
        adapter_type: Any,
    ) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["reasons"].append(
                "STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_DEFAULT_OFF"
            )
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append(
                "STARTUP_RECOVERY_PRODUCTION_PROVIDER_OFFLINE_SCOPE_REQUIRED"
            )
            return result
        expected_provider_binding = _valid_sha256(
            self._config.expected_provider_store_binding_sha256
        )
        expected_adapter_contract = _valid_sha256(
            self._config.expected_adapter_contract_sha256
        )
        if not (expected_provider_binding and expected_adapter_contract):
            result["reasons"].append("EXACT_DORMANT_BINDING_PINS_REQUIRED")
            return result
        if not provider_binding_contract.protected_provider_store_adapter_binding_valid_v1(
            protected_provider_store_binding
        ):
            result["reasons"].append("PROTECTED_PROVIDER_STORE_BINDING_INVALID")
            return result
        if not hmac.compare_digest(
            protected_provider_store_binding.binding_sha256,
            expected_provider_binding,
        ):
            result["reasons"].append("PROVIDER_STORE_BINDING_PIN_MISMATCH")
            return result
        result["provider_store_binding_verified"] = True
        if provider_type is not production_provider.ProductionClosedRepairProviderV1:
            result["reasons"].append("EXACT_PRODUCTION_PROVIDER_CLASS_REQUIRED")
            return result
        result["provider_class_verified"] = True
        if adapter_type is not startup_adapter.OfflineRuntimeStartupRecoveryAdapterV1:
            result["reasons"].append("EXACT_STARTUP_RECOVERY_ADAPTER_CLASS_REQUIRED")
            return result
        result["adapter_class_verified"] = True
        adapter_contract_sha = startup_recovery_adapter_contract_sha256_v1()
        if not hmac.compare_digest(
            adapter_contract_sha, expected_adapter_contract
        ):
            result["reasons"].append("STARTUP_RECOVERY_ADAPTER_CONTRACT_PIN_MISMATCH")
            return result
        result["contract_identity_verified"] = True
        source = protected_provider_store_binding.binding
        binding = {
            "binding_version": PROTECTED_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_VERSION_V1,
            "scope_attestation": OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1,
            "provider_store_binding_sha256": protected_provider_store_binding.binding_sha256,
            "source_provider_version": source["source_provider_version"],
            "source_store_version": source["source_store_version"],
            "source_provider_snapshot_sha256": source[
                "source_provider_snapshot_sha256"
            ],
            "composition_attestation_sha256": source[
                "composition_attestation_sha256"
            ],
            "backend_instance_sha256": source["backend_instance_sha256"],
            "registry_path_binding_sha256": source[
                "registry_path_binding_sha256"
            ],
            "backend_capability_attestation_sha256": source[
                "backend_capability_attestation_sha256"
            ],
            "lock_namespace_sha256": source["lock_namespace_sha256"],
            "startup_recovery_adapter_version": (
                startup_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_V1_VERSION
            ),
            "startup_recovery_adapter_contract_sha256": adapter_contract_sha,
            "provider_class_id": _PROVIDER_CLASS_ID,
            "adapter_class_id": _ADAPTER_CLASS_ID,
            "required_backend_port_methods": list(_REQUIRED_BACKEND_PORT_METHODS),
            "provider_surface_map": _canonical_copy(list(_PROVIDER_SURFACE_MAP)),
            "same_backend_instance_required": True,
            "same_registry_path_binding_required": True,
            "same_lock_namespace_required": True,
            "same_maintenance_epoch_instance_required": True,
            "provider_projection_verified": True,
            "provider_instance_bound": False,
            "adapter_class_verified": True,
            "adapter_instance_bound": False,
            "direct_port_compatibility_verified": False,
            "bridge_required": True,
            "recovery_receipt_required": True,
            "startup_recovery_attestation_required": True,
            "provider_call_allowed": False,
            "adapter_call_allowed": False,
            "recovery_execution_allowed": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "synthetic_only": True,
        }
        binding["binding_sha256"] = (
            startup_recovery_production_provider_binding_sha256_v1(binding)
        )
        protected = ProtectedStartupRecoveryProductionProviderBindingV1(
            provider_store_binding_sha256=binding[
                "provider_store_binding_sha256"
            ],
            adapter_contract_sha256=binding[
                "startup_recovery_adapter_contract_sha256"
            ],
            backend_instance_sha256=binding["backend_instance_sha256"],
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_startup_recovery_production_provider_binding_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_DORMANT_BINDING_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_PRODUCTION_PROVIDER_IDENTITY_BOUND_DORMANT",
            identity_binding_created=True,
            protected_binding=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryProductionProviderBindingConfigV1",
    "DormantStartupRecoveryProductionProviderBindingContractV1",
    "OFFLINE_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_VERSION_V1",
    "ProtectedStartupRecoveryProductionProviderBindingV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_PRODUCTION_PROVIDER_BINDING_CONTRACT_V1_VERSION",
    "protected_startup_recovery_production_provider_binding_valid_v1",
    "startup_recovery_adapter_contract_sha256_v1",
    "startup_recovery_production_provider_binding_sha256_v1",
]
