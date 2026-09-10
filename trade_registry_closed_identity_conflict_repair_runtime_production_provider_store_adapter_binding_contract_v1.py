"""Dormant offline binding for provider/store projections and the C3 adapter.

The contract accepts plain synthetic snapshots only.  It neither imports nor
instantiates the production provider/store and exposes no callable capable of
loading or mutating a Registry.  A successful result proves hash/schema
compatibility only; it never grants production authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-PROVIDER-STORE-ADAPTER-BINDING-CONTRACT-V1"
)
OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_OFFLINE_ONLY_V1"
)
SYNTHETIC_PROVIDER_BINDING_PROJECTION_VERSION_V1 = (
    "C3_PRODUCTION_PROVIDER_BINDING_PROJECTION_SYNTHETIC_V1"
)
SYNTHETIC_STORE_PORT_PROJECTION_VERSION_V1 = (
    "C3_PRODUCTION_STORE_PORT_PROJECTION_SYNTHETIC_V1"
)
PROTECTED_PROVIDER_STORE_ADAPTER_BINDING_VERSION_V1 = (
    "C3_PROTECTED_PROVIDER_STORE_ADAPTER_BINDING_OFFLINE_V1"
)
EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1 = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-PRODUCTION-PROVIDER-V1"
)
EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1 = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-TRANSACTION-STORE-PRODUCTION-V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER_PROJECTION_KEYS = frozenset(
    {
        "projection_version",
        "source_provider_version",
        "source_provider_snapshot_sha256",
        "composition_attestation_sha256",
        "binding_scope",
        "components_bound",
        "transaction_store_version",
        "transaction_store_storage_scope",
        "transaction_store_projection_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "production_ready",
        "runtime_integrated",
        "synthetic_projection",
        "real_component_referenced",
        "production_evidence",
        "projection_sha256",
    }
)
_STORE_PROJECTION_KEYS = frozenset(
    {
        "projection_version",
        "source_store_version",
        "source_store_snapshot_sha256",
        "storage_scope",
        "store_instance_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "request_schema_version",
        "result_schema_version",
        "recovery_request_schema_version",
        "apply_supported",
        "recovery_supported",
        "path_binding_required",
        "production_interface_bound_required",
        "durability_required",
        "durability_verified",
        "production_ready",
        "runtime_integrated",
        "synthetic_projection",
        "real_component_referenced",
        "production_evidence",
        "projection_sha256",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "provider_projection_sha256",
        "source_provider_version",
        "source_provider_snapshot_sha256",
        "composition_attestation_sha256",
        "store_projection_sha256",
        "source_store_version",
        "source_store_snapshot_sha256",
        "storage_scope",
        "adapter_snapshot_sha256",
        "store_instance_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "backend_capability_attestation_sha256",
        "lock_namespace_sha256",
        "request_schema_version",
        "result_schema_version",
        "recovery_request_schema_version",
        "terminal_receipt_required",
        "recovery_receipt_required",
        "production_interface_bound_required",
        "durability_required",
        "durability_verified",
        "provider_call_allowed",
        "store_call_allowed",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "synthetic_only",
        "binding_sha256",
    }
)

_PRODUCTION_BLOCKERS = (
    "PROVIDER_SNAPSHOT_IS_A_SYNTHETIC_HASH_ONLY_PROJECTION",
    "STORE_SNAPSHOT_IS_A_SYNTHETIC_HASH_ONLY_PROJECTION",
    "PRODUCTION_PROVIDER_IS_NOT_IMPORTED_OR_CALLED",
    "PRODUCTION_STORE_IS_NOT_IMPORTED_OR_CALLED",
    "DURABLE_BACKEND_IS_NOT_IMPLEMENTED_OR_VERIFIED",
    "TERMINAL_RECEIPT_EMITTER_IS_NOT_BOUND",
    "STARTUP_RECOVERY_IS_NOT_BOUND",
    "RUNTIME_IS_NOT_INTEGRATED",
    "READINESS_IS_NOT_ACTIVATED",
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


def _hash_without(value: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: item for key, item in value.items() if key != field_name}
    )


def provider_binding_projection_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("provider projection must be a mapping")
    return _hash_without(value, "projection_sha256")


def store_port_projection_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("store projection must be a mapping")
    return _hash_without(value, "projection_sha256")


def provider_store_adapter_binding_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("binding must be a mapping")
    return _hash_without(value, "binding_sha256")


@dataclass(frozen=True)
class DormantProductionProviderStoreAdapterBindingConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_provider_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_store_projection_sha256: str | None = field(default=None, repr=False)
    expected_adapter_snapshot_sha256: str | None = field(default=None, repr=False)
    expected_composition_attestation_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedProductionProviderStoreAdapterBindingV1:
    provider_projection_sha256: str = field(repr=False)
    store_projection_sha256: str = field(repr=False)
    adapter_snapshot_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionProviderStoreAdapterBindingV1(<protected>)"


def _provider_projection_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _PROVIDER_PROJECTION_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("projection_sha256"))
    try:
        return bool(
            value.get("projection_version")
            == SYNTHETIC_PROVIDER_BINDING_PROJECTION_VERSION_V1
            and value.get("source_provider_version")
            == EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1
            and _valid_sha256(value.get("source_provider_snapshot_sha256"))
            and _valid_sha256(value.get("composition_attestation_sha256"))
            and value.get("binding_scope") == "EXPLICIT_RUNTIME"
            and value.get("components_bound") is True
            and value.get("transaction_store_version")
            == EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1
            and value.get("transaction_store_storage_scope")
            == "EXPLICIT_PRODUCTION"
            and _valid_sha256(value.get("transaction_store_projection_sha256"))
            and _valid_sha256(value.get("registry_path_binding_sha256"))
            and _valid_sha256(value.get("backend_capability_attestation_sha256"))
            and _valid_sha256(value.get("lock_namespace_sha256"))
            and value.get("production_ready") is False
            and value.get("runtime_integrated") is False
            and value.get("synthetic_projection") is True
            and value.get("real_component_referenced") is False
            and value.get("production_evidence") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, provider_binding_projection_sha256_v1(value)
            )
        )
    except Exception:
        return False


def _store_projection_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _STORE_PROJECTION_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("projection_sha256"))
    try:
        return bool(
            value.get("projection_version")
            == SYNTHETIC_STORE_PORT_PROJECTION_VERSION_V1
            and value.get("source_store_version")
            == EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "source_store_snapshot_sha256",
                    "store_instance_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "backend_capability_attestation_sha256",
                    "lock_namespace_sha256",
                )
            )
            and value.get("storage_scope") == "EXPLICIT_PRODUCTION"
            and value.get("request_schema_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and value.get("result_schema_version")
            == envelope_contract.PRODUCTION_RESULT_VERSION_V1
            and value.get("recovery_request_schema_version")
            == envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1
            and value.get("apply_supported") is True
            and value.get("recovery_supported") is True
            and value.get("path_binding_required") is True
            and value.get("production_interface_bound_required") is True
            and value.get("durability_required") is True
            and value.get("durability_verified") is False
            and value.get("production_ready") is False
            and value.get("runtime_integrated") is False
            and value.get("synthetic_projection") is True
            and value.get("real_component_referenced") is False
            and value.get("production_evidence") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha, store_port_projection_sha256_v1(value)
            )
        )
    except Exception:
        return False


def _adapter_snapshot_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != adapter_contract._SNAPSHOT_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("snapshot_sha256"))
    try:
        return bool(
            value.get("snapshot_version")
            == adapter_contract.SYNTHETIC_STORE_DOUBLE_SNAPSHOT_VERSION_V1
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "store_instance_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "production_backend_capability_attestation_sha256",
                    "lock_namespace_sha256",
                )
            )
            and value.get("request_schema_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and value.get("result_schema_version")
            == envelope_contract.PRODUCTION_RESULT_VERSION_V1
            and value.get("recovery_request_schema_version")
            == envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1
            and value.get("apply_supported") is True
            and value.get("recovery_supported") is True
            and value.get("enabled") is True
            and value.get("synthetic_only") is True
            and value.get("durable") is False
            and value.get("production_backend_referenced") is False
            and value.get("production_authority") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                adapter_contract.synthetic_store_double_snapshot_sha256_v1(value),
            )
        )
    except Exception:
        return False


def protected_provider_store_adapter_binding_valid_v1(value: Any) -> bool:
    if not isinstance(value, ProtectedProductionProviderStoreAdapterBindingV1):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    supplied_sha = _valid_sha256(binding.get("binding_sha256"))
    try:
        return bool(
            binding.get("binding_version")
            == PROTECTED_PROVIDER_STORE_ADAPTER_BINDING_VERSION_V1
            and binding.get("scope_attestation")
            == OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1
            and binding.get("provider_projection_sha256")
            == value.provider_projection_sha256
            and binding.get("store_projection_sha256")
            == value.store_projection_sha256
            and binding.get("adapter_snapshot_sha256")
            == value.adapter_snapshot_sha256
            and binding.get("backend_instance_sha256")
            == value.backend_instance_sha256
            and all(
                _valid_sha256(binding.get(field_name))
                for field_name in (
                    "provider_projection_sha256",
                    "source_provider_snapshot_sha256",
                    "composition_attestation_sha256",
                    "store_projection_sha256",
                    "source_store_snapshot_sha256",
                    "adapter_snapshot_sha256",
                    "store_instance_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "backend_capability_attestation_sha256",
                    "lock_namespace_sha256",
                )
            )
            and binding.get("source_provider_version")
            == EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1
            and binding.get("source_store_version")
            == EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1
            and binding.get("storage_scope") == "EXPLICIT_PRODUCTION"
            and binding.get("request_schema_version")
            == envelope_contract.PRODUCTION_REQUEST_VERSION_V1
            and binding.get("result_schema_version")
            == envelope_contract.PRODUCTION_RESULT_VERSION_V1
            and binding.get("recovery_request_schema_version")
            == envelope_contract.PRODUCTION_RECOVERY_REQUEST_VERSION_V1
            and binding.get("terminal_receipt_required") is True
            and binding.get("recovery_receipt_required") is True
            and binding.get("production_interface_bound_required") is True
            and binding.get("durability_required") is True
            and binding.get("durability_verified") is False
            and binding.get("provider_call_allowed") is False
            and binding.get("store_call_allowed") is False
            and binding.get("production_authority") is False
            and binding.get("production_ready") is False
            and binding.get("runtime_integrated") is False
            and binding.get("synthetic_only") is True
            and supplied_sha
            and supplied_sha == value.binding_sha256
            and hmac.compare_digest(
                supplied_sha, provider_store_adapter_binding_sha256_v1(binding)
            )
        )
    except Exception:
        return False


class DormantProductionProviderStoreAdapterBindingContractV1:
    def __init__(
        self,
        *,
        config: DormantProductionProviderStoreAdapterBindingConfigV1 | None = None,
    ) -> None:
        self._config = (
            config or DormantProductionProviderStoreAdapterBindingConfigV1()
        )

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "provider_projection_verified": False,
            "store_projection_verified": False,
            "adapter_snapshot_verified": False,
            "cross_binding_verified": False,
            "terminal_receipt_contract_required": True,
            "recovery_receipt_contract_required": True,
            "durability_required": True,
            "durability_verified": False,
            "binding_created": False,
            "production_authority": False,
            "provider_called": False,
            "store_called": False,
            "production_backend_called": False,
            "runtime_integrated": False,
            "production_ready": False,
            "apply_allowed": False,
            "recovery_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
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
        provider_projection: Mapping[str, Any],
        store_projection: Mapping[str, Any],
        adapter_snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        if self._config.enabled is not True:
            result["reasons"].append("PROVIDER_STORE_ADAPTER_BINDING_DEFAULT_OFF")
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1
        ):
            result["reasons"].append(
                "PROVIDER_STORE_ADAPTER_BINDING_OFFLINE_SCOPE_REQUIRED"
            )
            return result
        pins = {
            "provider": _valid_sha256(
                self._config.expected_provider_projection_sha256
            ),
            "store": _valid_sha256(self._config.expected_store_projection_sha256),
            "adapter": _valid_sha256(
                self._config.expected_adapter_snapshot_sha256
            ),
            "composition": _valid_sha256(
                self._config.expected_composition_attestation_sha256
            ),
        }
        if not all(pins.values()):
            result["reasons"].append("EXACT_SYNTHETIC_BINDING_PINS_REQUIRED")
            return result
        try:
            provider = _canonical_copy(dict(provider_projection))
            store = _canonical_copy(dict(store_projection))
            adapter = _canonical_copy(dict(adapter_snapshot))
        except Exception:
            result["reasons"].append("SYNTHETIC_BINDING_PROJECTIONS_INVALID")
            return result
        if not _provider_projection_valid(provider):
            result["reasons"].append("SYNTHETIC_PROVIDER_PROJECTION_INVALID")
            return result
        result["provider_projection_verified"] = True
        if not _store_projection_valid(store):
            result["reasons"].append("SYNTHETIC_STORE_PROJECTION_INVALID")
            return result
        result["store_projection_verified"] = True
        if not _adapter_snapshot_valid(adapter):
            result["reasons"].append("SYNTHETIC_ADAPTER_SNAPSHOT_INVALID")
            return result
        result["adapter_snapshot_verified"] = True
        if not (
            hmac.compare_digest(provider["projection_sha256"], pins["provider"])
            and hmac.compare_digest(store["projection_sha256"], pins["store"])
            and hmac.compare_digest(adapter["snapshot_sha256"], pins["adapter"])
            and hmac.compare_digest(
                provider["composition_attestation_sha256"], pins["composition"]
            )
        ):
            result["reasons"].append("SYNTHETIC_BINDING_PIN_MISMATCH")
            return result
        shared_provider_store_fields = (
            "registry_path_binding_sha256",
            "backend_capability_attestation_sha256",
            "lock_namespace_sha256",
        )
        shared_store_adapter_fields = (
            "store_instance_sha256",
            "backend_instance_sha256",
            "registry_path_binding_sha256",
            "lock_namespace_sha256",
            "request_schema_version",
            "result_schema_version",
            "recovery_request_schema_version",
        )
        if not (
            provider["transaction_store_projection_sha256"]
            == store["projection_sha256"]
            and provider["transaction_store_version"]
            == store["source_store_version"]
            and provider["transaction_store_storage_scope"]
            == store["storage_scope"]
            and all(
                provider[field_name] == store[field_name]
                for field_name in shared_provider_store_fields
            )
            and all(
                store[field_name] == adapter[field_name]
                for field_name in shared_store_adapter_fields
            )
            and store["backend_capability_attestation_sha256"]
            == adapter["production_backend_capability_attestation_sha256"]
        ):
            result["reasons"].append("PROVIDER_STORE_ADAPTER_CROSS_BINDING_INVALID")
            return result
        result["cross_binding_verified"] = True
        binding = {
            "binding_version": PROTECTED_PROVIDER_STORE_ADAPTER_BINDING_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1,
            "provider_projection_sha256": provider["projection_sha256"],
            "source_provider_version": provider["source_provider_version"],
            "source_provider_snapshot_sha256": provider[
                "source_provider_snapshot_sha256"
            ],
            "composition_attestation_sha256": provider[
                "composition_attestation_sha256"
            ],
            "store_projection_sha256": store["projection_sha256"],
            "source_store_version": store["source_store_version"],
            "source_store_snapshot_sha256": store[
                "source_store_snapshot_sha256"
            ],
            "storage_scope": store["storage_scope"],
            "adapter_snapshot_sha256": adapter["snapshot_sha256"],
            "store_instance_sha256": store["store_instance_sha256"],
            "backend_instance_sha256": store["backend_instance_sha256"],
            "registry_path_binding_sha256": store[
                "registry_path_binding_sha256"
            ],
            "backend_capability_attestation_sha256": store[
                "backend_capability_attestation_sha256"
            ],
            "lock_namespace_sha256": store["lock_namespace_sha256"],
            "request_schema_version": store["request_schema_version"],
            "result_schema_version": store["result_schema_version"],
            "recovery_request_schema_version": store[
                "recovery_request_schema_version"
            ],
            "terminal_receipt_required": True,
            "recovery_receipt_required": True,
            "production_interface_bound_required": True,
            "durability_required": True,
            "durability_verified": False,
            "provider_call_allowed": False,
            "store_call_allowed": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "synthetic_only": True,
        }
        binding["binding_sha256"] = provider_store_adapter_binding_sha256_v1(
            binding
        )
        protected = ProtectedProductionProviderStoreAdapterBindingV1(
            provider_projection_sha256=binding["provider_projection_sha256"],
            store_projection_sha256=binding["store_projection_sha256"],
            adapter_snapshot_sha256=binding["adapter_snapshot_sha256"],
            backend_instance_sha256=binding["backend_instance_sha256"],
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_provider_store_adapter_binding_valid_v1(protected):
            result["reasons"].append("PROTECTED_BINDING_SELF_VALIDATION_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_VERIFIED_OFFLINE_ONLY",
            binding_created=True,
            protected_binding=protected,
        )
        return result


__all__ = [
    "DormantProductionProviderStoreAdapterBindingConfigV1",
    "DormantProductionProviderStoreAdapterBindingContractV1",
    "EXPECTED_PRODUCTION_PROVIDER_CONTRACT_VERSION_V1",
    "EXPECTED_PRODUCTION_STORE_CONTRACT_VERSION_V1",
    "OFFLINE_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_SCOPE_ATTESTATION_V1",
    "PROTECTED_PROVIDER_STORE_ADAPTER_BINDING_VERSION_V1",
    "ProtectedProductionProviderStoreAdapterBindingV1",
    "SYNTHETIC_PROVIDER_BINDING_PROJECTION_VERSION_V1",
    "SYNTHETIC_STORE_PORT_PROJECTION_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STORE_ADAPTER_BINDING_CONTRACT_V1_VERSION",
    "protected_provider_store_adapter_binding_valid_v1",
    "provider_binding_projection_sha256_v1",
    "provider_store_adapter_binding_sha256_v1",
    "store_port_projection_sha256_v1",
]
