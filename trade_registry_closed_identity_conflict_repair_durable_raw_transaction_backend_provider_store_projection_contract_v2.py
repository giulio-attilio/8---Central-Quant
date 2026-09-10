"""Dormant provider/store projection for the temporary physical C3 backend V2.

The module converts sanitized synthetic evidence into hash-bound projections.
It exposes no provider, store, apply, reconcile, filesystem, or runtime call.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PROVIDER_STORE_PROJECTION_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PROVIDER-STORE-PROJECTION-CONTRACT-V2"
)
OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2 = (
    "C3_DURABLE_RAW_BACKEND_PROVIDER_STORE_PROJECTION_OFFLINE_ONLY_V2"
)
IMMUTABLE_CAPABILITY_MANIFEST_VERSION_V2 = (
    "C3_DURABLE_RAW_BACKEND_IMMUTABLE_CAPABILITY_MANIFEST_V2"
)
STORE_PROJECTION_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_STORE_PROJECTION_OFFLINE_V2"
PROVIDER_PROJECTION_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_PROVIDER_PROJECTION_OFFLINE_V2"
PROVIDER_STORE_BINDING_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_PROVIDER_STORE_BINDING_OFFLINE_V2"
PROTECTED_PROVIDER_STORE_BUNDLE_VERSION_V2 = "C3_DURABLE_RAW_BACKEND_PROVIDER_STORE_BUNDLE_PROTECTED_V2"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OBSERVATION_KEYS = frozenset(
    {
        "observation_version", "capability", "backend_instance_sha256",
        "fixture_binding_sha256", "probe_kind", "filesystem_accessed",
        "synthetic_only", "production_evidence", "observation_sha256",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "manifest_version", "backend_kind", "backend_instance_sha256",
        "backend_module_source_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "capability_names", "observations",
        "capability_count", "filesystem_evidence", "synthetic_only",
        "durable", "production_evidence", "manifest_sha256",
    }
)
_STORE_KEYS = frozenset(
    {
        "projection_version", "source_backend_snapshot_sha256",
        "source_prepared_catalog_sha256", "backend_generation",
        "prepared_count", "store_instance_sha256", "backend_instance_sha256",
        "capability_manifest_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "request_schema_version",
        "result_schema_version", "prepared_catalog_schema_version",
        "recovery_request_schema_version", "recovery_result_schema_version",
        "terminal_receipt_schema_version", "startup_recovery_schema_version",
        "apply_supported", "recovery_supported", "prepared_catalog_supported",
        "temporary_storage_only", "durability_required", "durability_verified",
        "provider_call_allowed", "store_call_allowed", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "projection_sha256",
    }
)
_PROVIDER_KEYS = frozenset(
    {
        "projection_version", "provider_instance_sha256", "store_projection_sha256",
        "store_instance_sha256", "backend_instance_sha256",
        "capability_manifest_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "required_writer_count",
        "writer_coordination_bound", "invocation_adapter_bound",
        "terminal_receipt_schema_version", "startup_recovery_schema_version",
        "temporary_storage_only", "durability_required", "durability_verified",
        "provider_call_allowed", "store_call_allowed", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "projection_sha256",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_version", "scope_attestation", "provider_projection_sha256",
        "store_projection_sha256", "provider_instance_sha256",
        "store_instance_sha256", "backend_instance_sha256",
        "backend_snapshot_sha256", "prepared_catalog_sha256",
        "capability_manifest_sha256", "registry_path_binding_sha256",
        "lock_namespace_sha256", "request_schema_version",
        "result_schema_version", "recovery_request_schema_version",
        "recovery_result_schema_version", "terminal_receipt_schema_version",
        "startup_recovery_schema_version", "required_writer_count",
        "writer_coordination_bound", "invocation_adapter_bound",
        "terminal_receipt_required", "startup_recovery_required",
        "temporary_storage_only", "durability_required", "durability_verified",
        "provider_call_allowed", "store_call_allowed", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "binding_sha256",
    }
)
_BUNDLE_KEYS = frozenset(
    {
        "bundle_version", "capability_manifest", "store_projection",
        "provider_projection", "provider_store_binding", "synthetic_only",
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


def immutable_capability_manifest_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "manifest_sha256")


def provider_store_projection_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "projection_sha256")


def provider_store_binding_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "binding_sha256")


def provider_store_bundle_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "bundle_sha256")


def _observation_valid(value: Any, backend_instance_sha256: str) -> bool:
    return bool(
        type(value) is dict
        and set(value) == _OBSERVATION_KEYS
        and value["observation_version"] == "C3_CAPABILITY_OBSERVATION_STABLE_V2"
        and value["capability"] in backend_contract.REQUIRED_CAPABILITIES_V2
        and value["backend_instance_sha256"] == backend_instance_sha256
        and _valid_sha(value["fixture_binding_sha256"])
        and value["probe_kind"] == "TEMPORARY_FILESYSTEM_FAULT_INJECTION"
        and value["filesystem_accessed"] is True
        and value["synthetic_only"] is True
        and value["production_evidence"] is False
        and _valid_sha(value["observation_sha256"])
        and hmac.compare_digest(
            value["observation_sha256"], _hash_without(value, "observation_sha256")
        )
    )


def immutable_capability_manifest_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _MANIFEST_KEYS:
        return False
    observations = value.get("observations")
    names = value.get("capability_names")
    supplied = str(value.get("manifest_sha256") or "")
    try:
        return bool(
            value["manifest_version"] == IMMUTABLE_CAPABILITY_MANIFEST_VERSION_V2
            and all(
                _valid_sha(value[key])
                for key in (
                    "backend_instance_sha256", "backend_module_source_sha256",
                    "registry_path_binding_sha256", "lock_namespace_sha256",
                )
            )
            and isinstance(names, list)
            and names == sorted(backend_contract.REQUIRED_CAPABILITIES_V2)
            and isinstance(observations, list)
            and all(
                _observation_valid(item, value["backend_instance_sha256"])
                for item in observations
            )
            and [item["capability"] for item in observations] == names
            and value["capability_count"] == len(names) == 9
            and value["filesystem_evidence"] is True
            and value["synthetic_only"] is True
            and value["durable"] is False
            and value["production_evidence"] is False
            and _valid_sha(supplied)
            and hmac.compare_digest(
                supplied, immutable_capability_manifest_sha256_v2(value)
            )
        )
    except Exception:
        return False


def build_immutable_capability_manifest_offline_v2(
    snapshot: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if not backend_contract.backend_snapshot_valid_v2(snapshot):
        raise ValueError("BACKEND_SNAPSHOT_INVALID")
    canonical = [copy.deepcopy(dict(item)) for item in evidence]
    if (
        snapshot.get("filesystem_accessed") is not True
        or len(canonical) != len(backend_contract.REQUIRED_CAPABILITIES_V2)
        or any(
            not backend_contract.capability_evidence_valid_v2(item, snapshot)
            for item in canonical
        )
        or sorted(item["capability"] for item in canonical)
        != sorted(backend_contract.REQUIRED_CAPABILITIES_V2)
        or any(item["observed"] is not True for item in canonical)
    ):
        raise ValueError("COMPLETE_PHYSICAL_CAPABILITY_EVIDENCE_REQUIRED")
    observations = []
    for item in sorted(canonical, key=lambda candidate: candidate["capability"]):
        observation = {
            "observation_version": "C3_CAPABILITY_OBSERVATION_STABLE_V2",
            "capability": item["capability"],
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "fixture_binding_sha256": item["fixture_binding_sha256"],
            "probe_kind": item["probe_kind"],
            "filesystem_accessed": True,
            "synthetic_only": True,
            "production_evidence": False,
        }
        observation["observation_sha256"] = _hash_without(
            observation, "observation_sha256"
        )
        observations.append(observation)
    manifest = {
        "manifest_version": IMMUTABLE_CAPABILITY_MANIFEST_VERSION_V2,
        "backend_kind": snapshot["backend_kind"],
        "backend_instance_sha256": snapshot["backend_instance_sha256"],
        "backend_module_source_sha256": snapshot["backend_module_source_sha256"],
        "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
        "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
        "capability_names": sorted(backend_contract.REQUIRED_CAPABILITIES_V2),
        "observations": observations,
        "capability_count": len(observations),
        "filesystem_evidence": True,
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
    }
    manifest["manifest_sha256"] = immutable_capability_manifest_sha256_v2(manifest)
    if not immutable_capability_manifest_valid_v2(manifest):
        raise ValueError("CAPABILITY_MANIFEST_INTERNAL_INVALID")
    return manifest


def _store_projection_valid(value: Any, manifest: Mapping[str, Any]) -> bool:
    expected_store_instance = backend_contract.stable_sha256_v2(
        {
            "kind": "C3_DORMANT_PROVIDER_STORE_V2",
            "backend_instance_sha256": manifest["backend_instance_sha256"],
            "capability_manifest_sha256": manifest["manifest_sha256"],
            "registry_path_binding_sha256": manifest["registry_path_binding_sha256"],
            "request_schema_version": backend_contract.TRANSACTION_REQUEST_VERSION_V2,
            "result_schema_version": backend_contract.TRANSACTION_RESULT_VERSION_V2,
            "recovery_request_schema_version": backend_contract.RECOVERY_REQUEST_VERSION_V2,
            "recovery_result_schema_version": backend_contract.RECOVERY_RESULT_VERSION_V2,
        }
    )
    return bool(
        type(value) is dict and set(value) == _STORE_KEYS
        and value["projection_version"] == STORE_PROJECTION_VERSION_V2
        and all(_valid_sha(value[key]) for key in (
            "source_backend_snapshot_sha256", "source_prepared_catalog_sha256",
            "store_instance_sha256", "backend_instance_sha256",
            "capability_manifest_sha256", "registry_path_binding_sha256",
            "lock_namespace_sha256",
        ))
        and value["backend_instance_sha256"] == manifest["backend_instance_sha256"]
        and value["capability_manifest_sha256"] == manifest["manifest_sha256"]
        and value["registry_path_binding_sha256"] == manifest["registry_path_binding_sha256"]
        and value["lock_namespace_sha256"] == manifest["lock_namespace_sha256"]
        and value["store_instance_sha256"] == expected_store_instance
        and value["request_schema_version"] == backend_contract.TRANSACTION_REQUEST_VERSION_V2
        and value["result_schema_version"] == backend_contract.TRANSACTION_RESULT_VERSION_V2
        and value["prepared_catalog_schema_version"] == backend_contract.PREPARED_CATALOG_VERSION_V2
        and value["recovery_request_schema_version"] == backend_contract.RECOVERY_REQUEST_VERSION_V2
        and value["recovery_result_schema_version"] == backend_contract.RECOVERY_RESULT_VERSION_V2
        and value["terminal_receipt_schema_version"] == terminal_contract.PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2
        and value["startup_recovery_schema_version"] == startup_contract.STARTUP_RECOVERY_STATE_VERSION_V2
        and type(value["backend_generation"]) is int and value["backend_generation"] >= 0
        and type(value["prepared_count"]) is int and value["prepared_count"] >= 0
        and all(value[key] is True for key in (
            "apply_supported", "recovery_supported", "prepared_catalog_supported",
            "temporary_storage_only", "durability_required",
        ))
        and all(value[key] is False for key in (
            "durability_verified", "provider_call_allowed", "store_call_allowed",
            "production_authority", "runtime_integrated", "activation_allowed", "live_allowed",
        ))
        and value["synthetic_only"] is True
        and _valid_sha(value["projection_sha256"])
        and hmac.compare_digest(
            value["projection_sha256"], provider_store_projection_sha256_v2(value)
        )
    )


def _provider_projection_valid(value: Any, store: Mapping[str, Any]) -> bool:
    expected_provider_instance = backend_contract.stable_sha256_v2(
        {
            "kind": "C3_DORMANT_PROVIDER_V2",
            "store_instance_sha256": store["store_instance_sha256"],
        }
    )
    return bool(
        type(value) is dict and set(value) == _PROVIDER_KEYS
        and value["projection_version"] == PROVIDER_PROJECTION_VERSION_V2
        and value["store_projection_sha256"] == store["projection_sha256"]
        and all(value[key] == store[key] for key in (
            "store_instance_sha256", "backend_instance_sha256",
            "capability_manifest_sha256", "registry_path_binding_sha256",
            "lock_namespace_sha256", "terminal_receipt_schema_version",
            "startup_recovery_schema_version",
        ))
        and value["provider_instance_sha256"] == expected_provider_instance
        and value["required_writer_count"] == 19
        and all(value[key] is False for key in (
            "writer_coordination_bound", "invocation_adapter_bound",
            "durability_verified", "provider_call_allowed", "store_call_allowed",
            "production_authority", "runtime_integrated", "activation_allowed", "live_allowed",
        ))
        and value["temporary_storage_only"] is True
        and value["durability_required"] is True
        and value["synthetic_only"] is True
        and _valid_sha(value["projection_sha256"])
        and hmac.compare_digest(
            value["projection_sha256"], provider_store_projection_sha256_v2(value)
        )
    )


@dataclass(frozen=True, repr=False)
class ProtectedProviderStoreProjectionBundleV2:
    backend_instance_sha256: str = field(repr=False)
    capability_manifest_sha256: str = field(repr=False)
    store_instance_sha256: str = field(repr=False)
    bundle: Mapping[str, Any] = field(repr=False)
    bundle_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProviderStoreProjectionBundleV2(<protected>)"


@dataclass(frozen=True)
class ProviderStoreProjectionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_backend_snapshot_sha256: str | None = field(default=None, repr=False)
    expected_prepared_catalog_sha256: str | None = field(default=None, repr=False)
    expected_capability_manifest_sha256: str | None = field(default=None, repr=False)


def protected_provider_store_projection_bundle_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedProviderStoreProjectionBundleV2):
        return False
    bundle = value.bundle
    if type(bundle) is not dict or set(bundle) != _BUNDLE_KEYS:
        return False
    manifest = bundle.get("capability_manifest")
    store = bundle.get("store_projection")
    provider = bundle.get("provider_projection")
    binding = bundle.get("provider_store_binding")
    supplied = str(bundle.get("bundle_sha256") or "")
    try:
        return bool(
            bundle["bundle_version"] == PROTECTED_PROVIDER_STORE_BUNDLE_VERSION_V2
            and immutable_capability_manifest_valid_v2(manifest)
            and _store_projection_valid(store, manifest)
            and _provider_projection_valid(provider, store)
            and type(binding) is dict and set(binding) == _BINDING_KEYS
            and binding["binding_version"] == PROVIDER_STORE_BINDING_VERSION_V2
            and binding["scope_attestation"] == OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2
            and binding["provider_projection_sha256"] == provider["projection_sha256"]
            and binding["store_projection_sha256"] == store["projection_sha256"]
            and binding["provider_instance_sha256"] == provider["provider_instance_sha256"]
            and binding["store_instance_sha256"] == store["store_instance_sha256"]
            and binding["backend_instance_sha256"] == manifest["backend_instance_sha256"]
            and binding["capability_manifest_sha256"] == manifest["manifest_sha256"]
            and binding["registry_path_binding_sha256"] == manifest["registry_path_binding_sha256"]
            and binding["lock_namespace_sha256"] == manifest["lock_namespace_sha256"]
            and binding["backend_snapshot_sha256"] == store["source_backend_snapshot_sha256"]
            and binding["prepared_catalog_sha256"] == store["source_prepared_catalog_sha256"]
            and all(
                binding[key] == store[key]
                for key in (
                    "request_schema_version", "result_schema_version",
                    "recovery_request_schema_version", "recovery_result_schema_version",
                    "terminal_receipt_schema_version", "startup_recovery_schema_version",
                )
            )
            and binding["required_writer_count"] == 19
            and all(binding[key] is False for key in (
                "writer_coordination_bound", "invocation_adapter_bound",
                "durability_verified", "provider_call_allowed", "store_call_allowed",
                "production_authority", "runtime_integrated", "activation_allowed", "live_allowed",
            ))
            and binding["terminal_receipt_required"] is True
            and binding["startup_recovery_required"] is True
            and binding["temporary_storage_only"] is True
            and binding["durability_required"] is True
            and binding["synthetic_only"] is True
            and _valid_sha(binding["binding_sha256"])
            and hmac.compare_digest(
                binding["binding_sha256"], provider_store_binding_sha256_v2(binding)
            )
            and bundle["synthetic_only"] is True
            and bundle["production_authority"] is False
            and bundle["runtime_integrated"] is False
            and bundle["activation_allowed"] is False
            and bundle["live_allowed"] is False
            and value.backend_instance_sha256 == manifest["backend_instance_sha256"]
            and value.capability_manifest_sha256 == manifest["manifest_sha256"]
            and value.store_instance_sha256 == store["store_instance_sha256"]
            and supplied == value.bundle_sha256
            and hmac.compare_digest(supplied, provider_store_bundle_sha256_v2(bundle))
        )
    except Exception:
        return False


class DormantProviderStoreProjectionV2:
    def __init__(self, config: ProviderStoreProjectionConfigV2 | None = None) -> None:
        self._config = config or ProviderStoreProjectionConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False, "status": "PROVIDER_STORE_PROJECTION_V2_FAILED_CLOSED",
            "reason": reason, "protected_bundle": None, "synthetic_only": True,
            "production_authority": False, "provider_called": False,
            "store_called": False, "backend_called": False, "runtime_integrated": False,
            "activation_allowed": False, "live_allowed": False,
            "filesystem_accessed": False, "write_executed": False,
        }

    def project_offline(
        self,
        *,
        snapshot: Mapping[str, Any],
        capability_evidence: Sequence[Mapping[str, Any]],
        prepared_catalog: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("PROVIDER_STORE_PROJECTION_V2_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2:
            return self._failed("PROVIDER_STORE_PROJECTION_V2_SCOPE_INVALID")
        try:
            manifest = build_immutable_capability_manifest_offline_v2(
                snapshot, capability_evidence
            )
        except Exception:
            return self._failed("PROVIDER_STORE_PROJECTION_V2_CAPABILITY_MANIFEST_INVALID")
        if not backend_contract.prepared_catalog_valid_v2(prepared_catalog, snapshot):
            return self._failed("PROVIDER_STORE_PROJECTION_V2_CATALOG_INVALID")
        pins = (
            str(self._config.expected_backend_snapshot_sha256 or ""),
            str(self._config.expected_prepared_catalog_sha256 or ""),
            str(self._config.expected_capability_manifest_sha256 or ""),
        )
        actual = (
            snapshot["snapshot_sha256"], prepared_catalog["catalog_sha256"],
            manifest["manifest_sha256"],
        )
        if not all(_valid_sha(item) for item in pins) or pins != actual:
            return self._failed("PROVIDER_STORE_PROJECTION_V2_PIN_MISMATCH")
        store_instance_sha = backend_contract.stable_sha256_v2(
            {
                "kind": "C3_DORMANT_PROVIDER_STORE_V2",
                "backend_instance_sha256": snapshot["backend_instance_sha256"],
                "capability_manifest_sha256": manifest["manifest_sha256"],
                "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
                "request_schema_version": backend_contract.TRANSACTION_REQUEST_VERSION_V2,
                "result_schema_version": backend_contract.TRANSACTION_RESULT_VERSION_V2,
                "recovery_request_schema_version": backend_contract.RECOVERY_REQUEST_VERSION_V2,
                "recovery_result_schema_version": backend_contract.RECOVERY_RESULT_VERSION_V2,
            }
        )
        store = {
            "projection_version": STORE_PROJECTION_VERSION_V2,
            "source_backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "source_prepared_catalog_sha256": prepared_catalog["catalog_sha256"],
            "backend_generation": snapshot["generation"],
            "prepared_count": prepared_catalog["prepared_count"],
            "store_instance_sha256": store_instance_sha,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "capability_manifest_sha256": manifest["manifest_sha256"],
            "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "request_schema_version": backend_contract.TRANSACTION_REQUEST_VERSION_V2,
            "result_schema_version": backend_contract.TRANSACTION_RESULT_VERSION_V2,
            "prepared_catalog_schema_version": backend_contract.PREPARED_CATALOG_VERSION_V2,
            "recovery_request_schema_version": backend_contract.RECOVERY_REQUEST_VERSION_V2,
            "recovery_result_schema_version": backend_contract.RECOVERY_RESULT_VERSION_V2,
            "terminal_receipt_schema_version": terminal_contract.PHYSICAL_TERMINAL_EVIDENCE_RECEIPT_VERSION_V2,
            "startup_recovery_schema_version": startup_contract.STARTUP_RECOVERY_STATE_VERSION_V2,
            "apply_supported": True, "recovery_supported": True,
            "prepared_catalog_supported": True, "temporary_storage_only": True,
            "durability_required": True, "durability_verified": False,
            "provider_call_allowed": False, "store_call_allowed": False,
            "production_authority": False, "runtime_integrated": False,
            "activation_allowed": False, "live_allowed": False, "synthetic_only": True,
        }
        store["projection_sha256"] = provider_store_projection_sha256_v2(store)
        provider_instance_sha = backend_contract.stable_sha256_v2(
            {"kind": "C3_DORMANT_PROVIDER_V2", "store_instance_sha256": store_instance_sha}
        )
        provider = {
            "projection_version": PROVIDER_PROJECTION_VERSION_V2,
            "provider_instance_sha256": provider_instance_sha,
            "store_projection_sha256": store["projection_sha256"],
            "store_instance_sha256": store_instance_sha,
            "backend_instance_sha256": store["backend_instance_sha256"],
            "capability_manifest_sha256": store["capability_manifest_sha256"],
            "registry_path_binding_sha256": store["registry_path_binding_sha256"],
            "lock_namespace_sha256": store["lock_namespace_sha256"],
            "required_writer_count": 19, "writer_coordination_bound": False,
            "invocation_adapter_bound": False,
            "terminal_receipt_schema_version": store["terminal_receipt_schema_version"],
            "startup_recovery_schema_version": store["startup_recovery_schema_version"],
            "temporary_storage_only": True, "durability_required": True,
            "durability_verified": False, "provider_call_allowed": False,
            "store_call_allowed": False, "production_authority": False,
            "runtime_integrated": False, "activation_allowed": False,
            "live_allowed": False, "synthetic_only": True,
        }
        provider["projection_sha256"] = provider_store_projection_sha256_v2(provider)
        binding = {
            "binding_version": PROVIDER_STORE_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2,
            "provider_projection_sha256": provider["projection_sha256"],
            "store_projection_sha256": store["projection_sha256"],
            "provider_instance_sha256": provider_instance_sha,
            "store_instance_sha256": store_instance_sha,
            "backend_instance_sha256": store["backend_instance_sha256"],
            "backend_snapshot_sha256": store["source_backend_snapshot_sha256"],
            "prepared_catalog_sha256": store["source_prepared_catalog_sha256"],
            "capability_manifest_sha256": store["capability_manifest_sha256"],
            "registry_path_binding_sha256": store["registry_path_binding_sha256"],
            "lock_namespace_sha256": store["lock_namespace_sha256"],
            "request_schema_version": store["request_schema_version"],
            "result_schema_version": store["result_schema_version"],
            "recovery_request_schema_version": store["recovery_request_schema_version"],
            "recovery_result_schema_version": store["recovery_result_schema_version"],
            "terminal_receipt_schema_version": store["terminal_receipt_schema_version"],
            "startup_recovery_schema_version": store["startup_recovery_schema_version"],
            "required_writer_count": 19, "writer_coordination_bound": False,
            "invocation_adapter_bound": False, "terminal_receipt_required": True,
            "startup_recovery_required": True, "temporary_storage_only": True,
            "durability_required": True, "durability_verified": False,
            "provider_call_allowed": False, "store_call_allowed": False,
            "production_authority": False, "runtime_integrated": False,
            "activation_allowed": False, "live_allowed": False, "synthetic_only": True,
        }
        binding["binding_sha256"] = provider_store_binding_sha256_v2(binding)
        bundle = {
            "bundle_version": PROTECTED_PROVIDER_STORE_BUNDLE_VERSION_V2,
            "capability_manifest": manifest, "store_projection": store,
            "provider_projection": provider, "provider_store_binding": binding,
            "synthetic_only": True, "production_authority": False,
            "runtime_integrated": False, "activation_allowed": False,
            "live_allowed": False,
        }
        bundle["bundle_sha256"] = provider_store_bundle_sha256_v2(bundle)
        protected = ProtectedProviderStoreProjectionBundleV2(
            backend_instance_sha256=snapshot["backend_instance_sha256"],
            capability_manifest_sha256=manifest["manifest_sha256"],
            store_instance_sha256=store_instance_sha,
            bundle=copy.deepcopy(bundle), bundle_sha256=bundle["bundle_sha256"],
        )
        if not protected_provider_store_projection_bundle_valid_v2(protected):
            return self._failed("PROVIDER_STORE_PROJECTION_V2_INTERNAL_INVALID")
        return {
            "ok": True, "status": "PROVIDER_STORE_PROJECTION_V2_BOUND_OFFLINE",
            "protected_bundle": protected, "bundle_sha256": protected.bundle_sha256,
            "capability_manifest_sha256": protected.capability_manifest_sha256,
            "store_instance_sha256": protected.store_instance_sha256,
            "writer_coordination_bound": False, "invocation_adapter_bound": False,
            "provider_called": False, "store_called": False, "backend_called": False,
            "filesystem_accessed": False, "write_executed": False,
            "production_authority": False, "runtime_integrated": False,
            "activation_allowed": False, "live_allowed": False,
        }


__all__ = [
    "DormantProviderStoreProjectionV2", "OFFLINE_PROVIDER_STORE_PROJECTION_SCOPE_ATTESTATION_V2",
    "ProviderStoreProjectionConfigV2", "ProtectedProviderStoreProjectionBundleV2",
    "build_immutable_capability_manifest_offline_v2",
    "immutable_capability_manifest_sha256_v2", "immutable_capability_manifest_valid_v2",
    "protected_provider_store_projection_bundle_valid_v2",
]
