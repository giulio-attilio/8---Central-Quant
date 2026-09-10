"""Dormant offline compatibility binding for C3 backend V2 coordination.

The contract joins already-sanitized synthetic projections.  It never accepts
runtime objects, invokes a writer, acquires a lock, opens the Registry, or calls
the provider/store/backend.  A successful result proves schema compatibility
only and grants no runtime or production authority.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2 as provider_contract
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination_contract
import trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1 as invocation_adapter
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as runtime_coordinator
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_WRITER_COORDINATION_COMPATIBILITY_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-WRITER-COORDINATION-COMPATIBILITY-CONTRACT-V2"
)
OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RAW_BACKEND_WRITER_COORDINATION_COMPATIBILITY_OFFLINE_ONLY_V2"
)
CALLABLE_MANIFEST_PROJECTION_VERSION_V2 = (
    "C3_WRITER_CALLABLE_MANIFEST_PROJECTION_OFFLINE_V2"
)
COORDINATOR_PROJECTION_VERSION_V2 = "C3_WRITER_COORDINATOR_PROJECTION_OFFLINE_V2"
MAINTENANCE_PERMIT_PROJECTION_VERSION_V2 = (
    "C3_MAINTENANCE_PERMIT_PROJECTION_SYNTHETIC_V2"
)
LIVE_LEASE_PROJECTION_VERSION_V2 = "C3_LIVE_LEASE_PROJECTION_SYNTHETIC_V2"
LOCK_OWNERSHIP_POLICY_VERSION_V2 = "C3_SINGLE_OWNER_LOCK_POLICY_OFFLINE_V2"
COMPATIBILITY_BINDING_VERSION_V2 = (
    "C3_BACKEND_WRITER_COORDINATION_COMPATIBILITY_BINDING_OFFLINE_V2"
)
PROTECTED_COMPATIBILITY_BUNDLE_VERSION_V2 = (
    "C3_BACKEND_WRITER_COORDINATION_COMPATIBILITY_BUNDLE_PROTECTED_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CALLABLE_KEYS = frozenset(
    {
        "projection_version", "adapter_contract_version",
        "adapter_instance_sha256", "callable_manifest_sha256", "writer_ids",
        "source_signature_sha256s", "writer_count", "seam_bindings_sha256",
        "binding_scope", "bound_writer_count",
        "adapter_enabled_for_synthetic_rehearsal", "adapter_call_allowed",
        "real_callable_bound", "runtime_integrated", "production_authority",
        "projection_sha256",
    }
)
_COORDINATOR_KEYS = frozenset(
    {
        "projection_version", "coordinator_contract_version",
        "coordinator_instance_sha256",
        "writer_inventory_sha256", "lock_namespace_sha256",
        "registered_writer_count", "all_writers_registered",
        "inflight_mutations", "synthetic_rehearsal", "runtime_enabled",
        "runtime_integrated", "production_authority", "projection_sha256",
    }
)
_PERMIT_KEYS = frozenset(
    {
        "projection_version", "permit_instance_sha256",
        "permit_binding_sha256", "coordinator_instance_sha256",
        "maintenance_epoch", "state", "lock_namespace_sha256",
        "registered_writer_count", "inflight_mutations",
        "shared_lock_acquired", "synthetic_only", "production_authority",
        "projection_sha256",
    }
)
_LEASE_KEYS = frozenset(
    {
        "projection_version", "lease_token_sha256", "permit_instance_sha256",
        "permit_binding_sha256", "coordinator_instance_sha256",
        "maintenance_epoch", "lock_namespace_sha256", "issued_at_epoch",
        "expires_at_epoch", "same_permit_instance", "active_synthetic",
        "single_use", "synthetic_only", "production_authority",
        "projection_sha256",
    }
)
_LOCK_KEYS = frozenset(
    {
        "policy_version", "lock_namespace_sha256", "maintenance_lock_owner",
        "normal_writer_lock_owner", "maximum_acquisition_count",
        "lock_already_held_by_permit", "backend_reacquire_allowed",
        "store_reacquire_allowed", "invocation_adapter_reacquire_allowed",
        "repair_via_writer_invocation_allowed", "non_reentrant_handoff_required",
        "release_owner", "runtime_integrated", "production_authority",
        "policy_sha256",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_version", "scope_attestation", "provider_store_bundle_sha256",
        "backend_instance_sha256", "provider_instance_sha256",
        "store_instance_sha256", "writer_inventory_sha256",
        "seam_bindings_sha256", "callable_manifest_projection_sha256",
        "callable_manifest_sha256",
        "adapter_instance_sha256", "coordinator_projection_sha256",
        "coordinator_instance_sha256", "maintenance_permit_projection_sha256",
        "permit_instance_sha256", "live_lease_projection_sha256",
        "lease_token_sha256", "lock_ownership_policy_sha256",
        "lock_namespace_sha256", "writer_count", "same_permit_instance_required",
        "lease_liveness_required", "single_lock_owner_verified",
        "invocation_projection_bound", "writer_coordination_projection_bound",
        "runtime_invocation_adapter_bound", "runtime_writer_coordination_bound",
        "provider_call_allowed", "store_call_allowed", "backend_call_allowed",
        "writer_call_allowed", "production_authority", "runtime_integrated",
        "activation_allowed", "live_allowed", "synthetic_only",
        "binding_sha256",
    }
)
_BUNDLE_KEYS = frozenset(
    {
        "bundle_version", "writer_inventory", "seam_bindings",
        "callable_manifest_projection", "coordinator_projection",
        "maintenance_permit_projection", "live_lease_projection",
        "lock_ownership_policy", "compatibility_binding", "synthetic_only",
        "production_authority", "runtime_integrated", "activation_allowed",
        "live_allowed", "bundle_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_contract.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def compatibility_projection_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "projection_sha256")


def lock_ownership_policy_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "policy_sha256")


def compatibility_binding_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "binding_sha256")


def compatibility_bundle_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "bundle_sha256")


def _sealed(value: Mapping[str, Any], key: str, expected_keys: frozenset[str]) -> bool:
    if type(value) is not dict or set(value) != expected_keys:
        return False
    supplied = str(value.get(key) or "")
    return bool(
        _valid_sha(supplied)
        and hmac.compare_digest(supplied, _hash_without(value, key))
    )


def _canonical_writer_material(
    writer_inventory: Sequence[Mapping[str, Any]],
    seam_bindings: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    try:
        inventory = copy.deepcopy(list(writer_inventory))
        bindings = copy.deepcopy(list(seam_bindings))
    except Exception:
        return None
    expected_inventory = coordination_contract.canonical_closed_repair_writer_inventory_v1()
    if inventory != expected_inventory or len(inventory) != 19:
        return None
    if (
        len(bindings) != 19
        or not bindings
        or any(not isinstance(item, Mapping) for item in bindings)
    ):
        return None
    receipt_sha = str(bindings[0].get("upstream_participation_receipt_sha256") or "")
    if not _valid_sha(receipt_sha):
        return None
    expected_bindings = seam_contract.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": receipt_sha}
    )
    if bindings != expected_bindings:
        return None
    return inventory, bindings


def build_callable_manifest_projection_offline_v2(
    writer_inventory: Sequence[Mapping[str, Any]],
    seam_bindings: Sequence[Mapping[str, Any]],
    *,
    adapter_instance_sha256: str,
    callable_manifest_sha256: str,
) -> dict[str, Any]:
    material = _canonical_writer_material(writer_inventory, seam_bindings)
    if (
        material is None
        or not _valid_sha(adapter_instance_sha256)
        or not _valid_sha(callable_manifest_sha256)
    ):
        raise ValueError("CANONICAL_WRITER_MATERIAL_REQUIRED")
    inventory, bindings = material
    value = {
        "projection_version": CALLABLE_MANIFEST_PROJECTION_VERSION_V2,
        "adapter_contract_version": invocation_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION,
        "adapter_instance_sha256": adapter_instance_sha256,
        "callable_manifest_sha256": callable_manifest_sha256,
        "writer_ids": [item["writer_id"] for item in inventory],
        "source_signature_sha256s": [
            item["source_signature_sha256"] for item in bindings
        ],
        "writer_count": 19,
        "seam_bindings_sha256": backend_contract.stable_sha256_v2(bindings),
        "binding_scope": "TEMPORARY_TEST",
        "bound_writer_count": 19,
        "adapter_enabled_for_synthetic_rehearsal": True,
        "adapter_call_allowed": False,
        "real_callable_bound": False,
        "runtime_integrated": False,
        "production_authority": False,
    }
    value["projection_sha256"] = compatibility_projection_sha256_v2(value)
    return value


def build_single_owner_lock_policy_offline_v2(
    lock_namespace_sha256: str,
) -> dict[str, Any]:
    if not _valid_sha(lock_namespace_sha256):
        raise ValueError("CANONICAL_LOCK_NAMESPACE_REQUIRED")
    value = {
        "policy_version": LOCK_OWNERSHIP_POLICY_VERSION_V2,
        "lock_namespace_sha256": lock_namespace_sha256,
        "maintenance_lock_owner": "COORDINATOR_MAINTENANCE_LEASE",
        "normal_writer_lock_owner": "INVOCATION_ADAPTER_MUTATION_PERMIT",
        "maximum_acquisition_count": 1,
        "lock_already_held_by_permit": True,
        "backend_reacquire_allowed": False,
        "store_reacquire_allowed": False,
        "invocation_adapter_reacquire_allowed": False,
        "repair_via_writer_invocation_allowed": False,
        "non_reentrant_handoff_required": True,
        "release_owner": "COORDINATOR_CONTEXT_EXIT",
        "runtime_integrated": False,
        "production_authority": False,
    }
    value["policy_sha256"] = lock_ownership_policy_sha256_v2(value)
    return value


@dataclass(frozen=True, repr=False)
class ProtectedWriterCoordinationCompatibilityBundleV2:
    provider_store_bundle_sha256: str = field(repr=False)
    coordinator_instance_sha256: str = field(repr=False)
    permit_instance_sha256: str = field(repr=False)
    bundle: Mapping[str, Any] = field(repr=False)
    bundle_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedWriterCoordinationCompatibilityBundleV2(<protected>)"


@dataclass(frozen=True)
class WriterCoordinationCompatibilityConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_provider_store_bundle_sha256: str | None = field(default=None, repr=False)
    max_lease_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_lease_seconds <= 300:
            raise ValueError("max_lease_seconds must be between 1 and 300")


def _callable_valid(value: Any, inventory: list[dict[str, Any]], bindings: list[dict[str, Any]]) -> bool:
    return bool(
        _sealed(value, "projection_sha256", _CALLABLE_KEYS)
        and value["projection_version"] == CALLABLE_MANIFEST_PROJECTION_VERSION_V2
        and value["adapter_contract_version"]
        == invocation_adapter.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_INVOCATION_ADAPTER_V1_VERSION
        and _valid_sha(value["adapter_instance_sha256"])
        and _valid_sha(value["callable_manifest_sha256"])
        and value["writer_ids"] == [item["writer_id"] for item in inventory]
        and value["source_signature_sha256s"]
        == [item["source_signature_sha256"] for item in bindings]
        and value["writer_count"] == 19
        and value["seam_bindings_sha256"] == backend_contract.stable_sha256_v2(bindings)
        and value["binding_scope"] == "TEMPORARY_TEST"
        and value["bound_writer_count"] == 19
        and value["adapter_enabled_for_synthetic_rehearsal"] is True
        and value["adapter_call_allowed"] is False
        and value["real_callable_bound"] is False
        and value["runtime_integrated"] is False
        and value["production_authority"] is False
    )


def _coordinator_valid(value: Any, inventory_sha: str, namespace: str) -> bool:
    return bool(
        _sealed(value, "projection_sha256", _COORDINATOR_KEYS)
        and value["projection_version"] == COORDINATOR_PROJECTION_VERSION_V2
        and value["coordinator_contract_version"]
        == runtime_coordinator.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION
        and _valid_sha(value["coordinator_instance_sha256"])
        and value["writer_inventory_sha256"] == inventory_sha
        and value["lock_namespace_sha256"] == namespace
        and value["registered_writer_count"] == 19
        and value["all_writers_registered"] is True
        and value["inflight_mutations"] == 0
        and value["synthetic_rehearsal"] is True
        and value["runtime_enabled"] is False
        and value["runtime_integrated"] is False
        and value["production_authority"] is False
    )


def _permit_valid(value: Any, coordinator_value: Mapping[str, Any], namespace: str) -> bool:
    if not _sealed(value, "projection_sha256", _PERMIT_KEYS):
        return False
    binding = {
        "coordinator_instance_sha256": value["coordinator_instance_sha256"],
        "maintenance_epoch": value["maintenance_epoch"],
        "state": value["state"],
        "lock_namespace_sha256": value["lock_namespace_sha256"],
        "registered_writer_count": value["registered_writer_count"],
        "inflight_mutations": value["inflight_mutations"],
        "shared_lock_acquired": value["shared_lock_acquired"],
    }
    return bool(
        value["projection_version"] == MAINTENANCE_PERMIT_PROJECTION_VERSION_V2
        and _valid_sha(value["permit_instance_sha256"])
        and value["permit_binding_sha256"] == backend_contract.stable_sha256_v2(binding)
        and value["coordinator_instance_sha256"] == coordinator_value["coordinator_instance_sha256"]
        and _valid_sha(value["maintenance_epoch"])
        and value["state"] == "QUIESCED"
        and value["lock_namespace_sha256"] == namespace
        and value["registered_writer_count"] == 19
        and value["inflight_mutations"] == 0
        and value["shared_lock_acquired"] is True
        and value["synthetic_only"] is True
        and value["production_authority"] is False
    )


def _lease_valid(
    value: Any,
    permit: Mapping[str, Any],
    *,
    now_epoch: int,
    max_lease_seconds: int,
) -> bool:
    return bool(
        _sealed(value, "projection_sha256", _LEASE_KEYS)
        and value["projection_version"] == LIVE_LEASE_PROJECTION_VERSION_V2
        and _valid_sha(value["lease_token_sha256"])
        and value["permit_instance_sha256"] == permit["permit_instance_sha256"]
        and value["permit_binding_sha256"] == permit["permit_binding_sha256"]
        and value["coordinator_instance_sha256"] == permit["coordinator_instance_sha256"]
        and value["maintenance_epoch"] == permit["maintenance_epoch"]
        and value["lock_namespace_sha256"] == permit["lock_namespace_sha256"]
        and type(value["issued_at_epoch"]) is int
        and type(value["expires_at_epoch"]) is int
        and value["issued_at_epoch"] <= now_epoch < value["expires_at_epoch"]
        and value["expires_at_epoch"] - value["issued_at_epoch"] <= max_lease_seconds
        and value["same_permit_instance"] is True
        and value["active_synthetic"] is True
        and value["single_use"] is True
        and value["synthetic_only"] is True
        and value["production_authority"] is False
    )


def _lock_valid(value: Any, namespace: str) -> bool:
    return bool(
        _sealed(value, "policy_sha256", _LOCK_KEYS)
        and value["policy_version"] == LOCK_OWNERSHIP_POLICY_VERSION_V2
        and value["lock_namespace_sha256"] == namespace
        and value["maintenance_lock_owner"] == "COORDINATOR_MAINTENANCE_LEASE"
        and value["normal_writer_lock_owner"] == "INVOCATION_ADAPTER_MUTATION_PERMIT"
        and value["maximum_acquisition_count"] == 1
        and value["lock_already_held_by_permit"] is True
        and value["backend_reacquire_allowed"] is False
        and value["store_reacquire_allowed"] is False
        and value["invocation_adapter_reacquire_allowed"] is False
        and value["repair_via_writer_invocation_allowed"] is False
        and value["non_reentrant_handoff_required"] is True
        and value["release_owner"] == "COORDINATOR_CONTEXT_EXIT"
        and value["runtime_integrated"] is False
        and value["production_authority"] is False
    )


def protected_writer_coordination_compatibility_bundle_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedWriterCoordinationCompatibilityBundleV2):
        return False
    bundle = value.bundle
    if type(bundle) is not dict or set(bundle) != _BUNDLE_KEYS:
        return False
    binding = bundle.get("compatibility_binding")
    try:
        material = _canonical_writer_material(
            bundle["writer_inventory"], bundle["seam_bindings"]
        )
        if material is None:
            return False
        inventory, bindings = material
        inventory_sha = backend_contract.stable_sha256_v2(inventory)
        seams_sha = backend_contract.stable_sha256_v2(bindings)
        callable_projection = bundle["callable_manifest_projection"]
        coordinator_value = bundle["coordinator_projection"]
        permit = bundle["maintenance_permit_projection"]
        lease = bundle["live_lease_projection"]
        lock_policy = bundle["lock_ownership_policy"]
        namespace = binding["lock_namespace_sha256"]
        return bool(
            _sealed(bundle, "bundle_sha256", _BUNDLE_KEYS)
            and _sealed(binding, "binding_sha256", _BINDING_KEYS)
            and _callable_valid(callable_projection, inventory, bindings)
            and _coordinator_valid(coordinator_value, inventory_sha, namespace)
            and _permit_valid(permit, coordinator_value, namespace)
            and _lease_valid(
                lease,
                permit,
                now_epoch=lease["issued_at_epoch"],
                max_lease_seconds=300,
            )
            and _lock_valid(lock_policy, namespace)
            and namespace == runtime_coordinator.canonical_runtime_lock_namespace_v1()
            and value.provider_store_bundle_sha256 == binding["provider_store_bundle_sha256"]
            and value.coordinator_instance_sha256 == binding["coordinator_instance_sha256"]
            and value.permit_instance_sha256 == binding["permit_instance_sha256"]
            and value.bundle_sha256 == bundle["bundle_sha256"]
            and binding["writer_inventory_sha256"] == inventory_sha
            and binding["seam_bindings_sha256"] == seams_sha
            and binding["callable_manifest_projection_sha256"]
            == callable_projection["projection_sha256"]
            and binding["callable_manifest_sha256"]
            == callable_projection["callable_manifest_sha256"]
            and binding["adapter_instance_sha256"]
            == callable_projection["adapter_instance_sha256"]
            and binding["coordinator_projection_sha256"]
            == coordinator_value["projection_sha256"]
            and binding["coordinator_instance_sha256"]
            == coordinator_value["coordinator_instance_sha256"]
            and binding["maintenance_permit_projection_sha256"]
            == permit["projection_sha256"]
            and binding["permit_instance_sha256"] == permit["permit_instance_sha256"]
            and binding["live_lease_projection_sha256"] == lease["projection_sha256"]
            and binding["lease_token_sha256"] == lease["lease_token_sha256"]
            and binding["lock_ownership_policy_sha256"] == lock_policy["policy_sha256"]
            and binding["writer_count"] == 19
            and binding["same_permit_instance_required"] is True
            and binding["lease_liveness_required"] is True
            and binding["single_lock_owner_verified"] is True
            and binding["invocation_projection_bound"] is True
            and binding["writer_coordination_projection_bound"] is True
            and all(
                binding[key] is False
                for key in (
                    "runtime_invocation_adapter_bound", "runtime_writer_coordination_bound",
                    "provider_call_allowed", "store_call_allowed", "backend_call_allowed",
                    "writer_call_allowed", "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and binding["synthetic_only"] is True
            and bundle["synthetic_only"] is True
            and bundle["production_authority"] is False
            and bundle["runtime_integrated"] is False
            and bundle["activation_allowed"] is False
            and bundle["live_allowed"] is False
        )
    except Exception:
        return False


class DormantWriterCoordinationCompatibilityV2:
    def __init__(self, config: WriterCoordinationCompatibilityConfigV2 | None = None) -> None:
        self._config = config or WriterCoordinationCompatibilityConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "WRITER_COORDINATION_COMPATIBILITY_V2_BLOCKED",
            "reason": reason,
            "protected_bundle": None,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "filesystem_accessed": False,
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

    def bind_offline(
        self,
        *,
        provider_store_bundle: provider_contract.ProtectedProviderStoreProjectionBundleV2,
        writer_inventory: Sequence[Mapping[str, Any]],
        seam_bindings: Sequence[Mapping[str, Any]],
        callable_manifest_projection: Mapping[str, Any],
        coordinator_projection: Mapping[str, Any],
        maintenance_permit_projection: Mapping[str, Any],
        live_lease_projection: Mapping[str, Any],
        lock_ownership_policy: Mapping[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_V2_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2:
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_V2_SCOPE_REQUIRED")
        if type(now_epoch) is not int:
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_V2_CLOCK_INVALID")
        if not provider_contract.protected_provider_store_projection_bundle_valid_v2(provider_store_bundle):
            return self._failed("PROVIDER_STORE_BUNDLE_V2_INVALID")
        if not (
            _valid_sha(self._config.expected_provider_store_bundle_sha256)
            and hmac.compare_digest(
                str(self._config.expected_provider_store_bundle_sha256),
                provider_store_bundle.bundle_sha256,
            )
        ):
            return self._failed("PROVIDER_STORE_BUNDLE_V2_PIN_MISMATCH")
        material = _canonical_writer_material(writer_inventory, seam_bindings)
        if material is None:
            return self._failed("CANONICAL_19_WRITER_MATERIAL_INVALID")
        inventory, bindings = material
        source_binding = provider_store_bundle.bundle["provider_store_binding"]
        namespace = source_binding["lock_namespace_sha256"]
        inventory_sha = backend_contract.stable_sha256_v2(inventory)
        try:
            callable_projection = copy.deepcopy(dict(callable_manifest_projection))
            coordinator_value = copy.deepcopy(dict(coordinator_projection))
            permit = copy.deepcopy(dict(maintenance_permit_projection))
            lease = copy.deepcopy(dict(live_lease_projection))
            lock_policy = copy.deepcopy(dict(lock_ownership_policy))
        except Exception:
            return self._failed("COMPATIBILITY_PROJECTION_MAPPING_INPUTS_REQUIRED")
        if namespace != runtime_coordinator.canonical_runtime_lock_namespace_v1():
            return self._failed("CANONICAL_LOCK_NAMESPACE_MISMATCH")
        if not _callable_valid(callable_projection, inventory, bindings):
            return self._failed("CALLABLE_MANIFEST_PROJECTION_V2_INVALID")
        if not _coordinator_valid(coordinator_value, inventory_sha, namespace):
            return self._failed("COORDINATOR_PROJECTION_V2_INVALID")
        if not _permit_valid(permit, coordinator_value, namespace):
            return self._failed("MAINTENANCE_PERMIT_PROJECTION_V2_INVALID")
        if not _lease_valid(
            lease, permit, now_epoch=now_epoch,
            max_lease_seconds=self._config.max_lease_seconds,
        ):
            return self._failed("LIVE_LEASE_PROJECTION_V2_INVALID_OR_EXPIRED")
        if not _lock_valid(lock_policy, namespace):
            return self._failed("SINGLE_OWNER_LOCK_POLICY_V2_INVALID")
        binding = {
            "binding_version": COMPATIBILITY_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2,
            "provider_store_bundle_sha256": provider_store_bundle.bundle_sha256,
            "backend_instance_sha256": source_binding["backend_instance_sha256"],
            "provider_instance_sha256": source_binding["provider_instance_sha256"],
            "store_instance_sha256": source_binding["store_instance_sha256"],
            "writer_inventory_sha256": inventory_sha,
            "seam_bindings_sha256": backend_contract.stable_sha256_v2(bindings),
            "callable_manifest_projection_sha256": callable_projection["projection_sha256"],
            "callable_manifest_sha256": callable_projection["callable_manifest_sha256"],
            "adapter_instance_sha256": callable_projection["adapter_instance_sha256"],
            "coordinator_projection_sha256": coordinator_value["projection_sha256"],
            "coordinator_instance_sha256": coordinator_value["coordinator_instance_sha256"],
            "maintenance_permit_projection_sha256": permit["projection_sha256"],
            "permit_instance_sha256": permit["permit_instance_sha256"],
            "live_lease_projection_sha256": lease["projection_sha256"],
            "lease_token_sha256": lease["lease_token_sha256"],
            "lock_ownership_policy_sha256": lock_policy["policy_sha256"],
            "lock_namespace_sha256": namespace,
            "writer_count": 19,
            "same_permit_instance_required": True,
            "lease_liveness_required": True,
            "single_lock_owner_verified": True,
            "invocation_projection_bound": True,
            "writer_coordination_projection_bound": True,
            "runtime_invocation_adapter_bound": False,
            "runtime_writer_coordination_bound": False,
            "provider_call_allowed": False,
            "store_call_allowed": False,
            "backend_call_allowed": False,
            "writer_call_allowed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        binding["binding_sha256"] = compatibility_binding_sha256_v2(binding)
        bundle = {
            "bundle_version": PROTECTED_COMPATIBILITY_BUNDLE_VERSION_V2,
            "writer_inventory": inventory,
            "seam_bindings": bindings,
            "callable_manifest_projection": callable_projection,
            "coordinator_projection": coordinator_value,
            "maintenance_permit_projection": permit,
            "live_lease_projection": lease,
            "lock_ownership_policy": lock_policy,
            "compatibility_binding": binding,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        bundle["bundle_sha256"] = compatibility_bundle_sha256_v2(bundle)
        protected = ProtectedWriterCoordinationCompatibilityBundleV2(
            provider_store_bundle_sha256=provider_store_bundle.bundle_sha256,
            coordinator_instance_sha256=coordinator_value["coordinator_instance_sha256"],
            permit_instance_sha256=permit["permit_instance_sha256"],
            bundle=copy.deepcopy(bundle),
            bundle_sha256=bundle["bundle_sha256"],
        )
        if not protected_writer_coordination_compatibility_bundle_valid_v2(protected):
            return self._failed("WRITER_COORDINATION_COMPATIBILITY_V2_INTERNAL_INVALID")
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "WRITER_COORDINATION_COMPATIBILITY_V2_BOUND_OFFLINE",
                "reason": None,
                "protected_bundle": protected,
                "bundle_sha256": protected.bundle_sha256,
                "writer_count": 19,
                "invocation_projection_bound": True,
                "writer_coordination_projection_bound": True,
                "single_lock_owner_verified": True,
                "same_permit_instance_verified_synthetic": True,
                "lease_live_verified_synthetic": True,
            }
        )
        return result


__all__ = [
    "CALLABLE_MANIFEST_PROJECTION_VERSION_V2",
    "COORDINATOR_PROJECTION_VERSION_V2",
    "DormantWriterCoordinationCompatibilityV2",
    "LIVE_LEASE_PROJECTION_VERSION_V2",
    "LOCK_OWNERSHIP_POLICY_VERSION_V2",
    "MAINTENANCE_PERMIT_PROJECTION_VERSION_V2",
    "OFFLINE_WRITER_COORDINATION_COMPATIBILITY_SCOPE_ATTESTATION_V2",
    "ProtectedWriterCoordinationCompatibilityBundleV2",
    "WriterCoordinationCompatibilityConfigV2",
    "build_callable_manifest_projection_offline_v2",
    "build_single_owner_lock_policy_offline_v2",
    "compatibility_binding_sha256_v2",
    "compatibility_bundle_sha256_v2",
    "compatibility_projection_sha256_v2",
    "lock_ownership_policy_sha256_v2",
    "protected_writer_coordination_compatibility_bundle_valid_v2",
]
