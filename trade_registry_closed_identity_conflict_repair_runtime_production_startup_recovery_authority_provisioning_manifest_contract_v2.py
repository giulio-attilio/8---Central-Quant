"""Protected, secret-free provisioning manifest for C3 authority adapters.

The manifest names references and relative paths only.  It never resolves an
environment variable, reads the filesystem, contacts Render, or authorizes
runtime/startup/Live activity.
"""

from __future__ import annotations

import copy
import hmac
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_MANIFEST_CONTRACT_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-MANIFEST-CONTRACT-V2"
)
OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2 = (
    "C3_AUTHORITY_PROVISIONING_MANIFEST_SECRET_FREE_OFFLINE_ONLY_V2"
)
AUTHORITY_PROVISIONING_MANIFEST_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_MANIFEST_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE_RE = re.compile(r"^[A-Z][A-Z0-9_]{7,95}_REF$")
_PRODUCTION_BLOCKERS = (
    "PERSISTENT_STORAGE_PATH_NOT_RESOLVED",
    "AUTHENTICATED_KEY_PROVIDER_NOT_RESOLVED",
    "ROOT_AUTHORITY_STATE_NOT_PROVISIONED",
    "ROOT_REVOCATION_STATE_NOT_PROVISIONED",
    "TRANSACTION_RECOVERY_PORT_NOT_BOUND",
    "RESOLVED_AUTHORITY_RECOVERY_PORT_NOT_BOUND",
    "RUNTIME_CONFIGURATION_NOT_APPLIED",
    "STARTUP_RECOVERY_NOT_EXECUTED",
    "LIVE_REMAINS_FORBIDDEN",
)


def authority_provisioning_manifest_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "manifest_sha256"}
    )


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def _safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return bool(
        value == path.as_posix()
        and not path.is_absolute()
        and len(path.parts) >= 2
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


@dataclass(frozen=True)
class DormantAuthorityProvisioningManifestConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_bundle_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedAuthorityProvisioningManifestV2:
    adapter_bundle_object_identity_sha256: str = field(repr=False)
    manifest: Mapping[str, Any] = field(repr=False)
    manifest_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedAuthorityProvisioningManifestV2(<protected>)"


def protected_authority_provisioning_manifest_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedAuthorityProvisioningManifestV2):
        return False
    manifest = value.manifest
    if not isinstance(manifest, Mapping):
        return False
    try:
        adapters = manifest["adapter_requirements"]
        return bool(
            set(manifest)
            == {
                "manifest_version",
                "scope_attestation",
                "root_anchor_symbol",
                "authority_state_relative_path",
                "revocation_state_relative_path",
                "key_provider_reference_name",
                "transaction_recovery_port_reference_name",
                "resolved_recovery_port_reference_name",
                "adapter_bundle_object_identity_sha256",
                "adapter_requirements",
                "adapter_count",
                "same_storage_root_required",
                "same_maintenance_permit_instance_required",
                "same_root_attestation_required",
                "atomic_replace_required",
                "file_fsync_required",
                "directory_fsync_required",
                "secret_material_embedded",
                "render_accessed",
                "filesystem_accessed",
                "environment_read",
                "configuration_mutation_allowed",
                "runtime_wiring_allowed",
                "startup_recovery_allowed",
                "production_ready",
                "activation_allowed",
                "live_allowed",
                "production_blockers",
                "manifest_sha256",
            }
            and manifest["manifest_version"]
            == AUTHORITY_PROVISIONING_MANIFEST_VERSION_V2
            and manifest["scope_attestation"]
            == OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2
            and manifest["root_anchor_symbol"] == "CENTRAL_DATA_DIR"
            and _safe_relative_path(manifest["authority_state_relative_path"])
            and _safe_relative_path(manifest["revocation_state_relative_path"])
            and _REFERENCE_RE.fullmatch(manifest["key_provider_reference_name"])
            and _REFERENCE_RE.fullmatch(
                manifest["transaction_recovery_port_reference_name"]
            )
            and _REFERENCE_RE.fullmatch(
                manifest["resolved_recovery_port_reference_name"]
            )
            and isinstance(adapters, list)
            and len(adapters) == 4
            and {item["role"] for item in adapters}
            == {
                "ROOT_STATE_PROVIDER",
                "ROOT_SIGNATURE_VERIFIER",
                "ROOT_REVOCATION_SOURCE",
                "MULTISTORE_RECOVERY",
            }
            and all(
                set(item) == {"role", "class_name", "required_method", "default_off"}
                and isinstance(item["class_name"], str)
                and isinstance(item["required_method"], str)
                and item["default_off"] is True
                for item in adapters
            )
            and manifest["adapter_count"] == 4
            and all(
                manifest[field_name] is True
                for field_name in (
                    "same_storage_root_required",
                    "same_maintenance_permit_instance_required",
                    "same_root_attestation_required",
                    "atomic_replace_required",
                    "file_fsync_required",
                    "directory_fsync_required",
                )
            )
            and all(
                manifest[field_name] is False
                for field_name in (
                    "secret_material_embedded",
                    "render_accessed",
                    "filesystem_accessed",
                    "environment_read",
                    "configuration_mutation_allowed",
                    "runtime_wiring_allowed",
                    "startup_recovery_allowed",
                    "production_ready",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and manifest["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and _valid_sha(value.adapter_bundle_object_identity_sha256)
            and value.adapter_bundle_object_identity_sha256
            == manifest["adapter_bundle_object_identity_sha256"]
            and _valid_sha(manifest["manifest_sha256"])
            and manifest["manifest_sha256"] == value.manifest_sha256
            and hmac.compare_digest(
                value.manifest_sha256,
                authority_provisioning_manifest_sha256_v2(manifest),
            )
        )
    except Exception:
        return False


class DormantAuthorityProvisioningManifestContractV2:
    def __init__(
        self,
        config: DormantAuthorityProvisioningManifestConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantAuthorityProvisioningManifestConfigV2()

    def __repr__(self) -> str:
        return "DormantAuthorityProvisioningManifestContractV2(<protected>)"

    @staticmethod
    def _base(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_AUTHORITY_PROVISIONING_MANIFEST_V2_BLOCKED",
            "reason": reason,
            "manifest_created": False,
            "secret_material_embedded": False,
            "filesystem_accessed": False,
            "environment_read": False,
            "render_accessed": False,
            "configuration_mutation_allowed": False,
            "runtime_wiring_allowed": False,
            "startup_recovery_allowed": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "protected_manifest": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def define_offline(
        self,
        *,
        adapter_bundle: Any,
        key_provider_reference_name: str,
        transaction_recovery_port_reference_name: str,
        resolved_recovery_port_reference_name: str,
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_DEFAULT_OFF")
        if config.scope_attestation != OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2:
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_SCOPE_INVALID")
        expected_identity = str(
            config.expected_adapter_bundle_object_identity_sha256 or ""
        )
        actual_identity = identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
            adapter_bundle
        )
        if not (
            type(adapter_bundle)
            is adapters_v2.DormantAuthenticatedPersistentAuthorityProductionAdaptersV2
            and _valid_sha(expected_identity)
            and hmac.compare_digest(actual_identity, expected_identity)
            and adapter_bundle.snapshot().get("default_off") is True
            and adapter_bundle.snapshot().get("adapter_count") == 4
            and adapter_bundle.snapshot().get("filesystem_accessed") is False
        ):
            return self._base("AUTHORITY_PROVISIONING_ADAPTER_BUNDLE_INVALID")
        references = (
            key_provider_reference_name,
            transaction_recovery_port_reference_name,
            resolved_recovery_port_reference_name,
        )
        if any(not isinstance(item, str) or not _REFERENCE_RE.fullmatch(item) for item in references):
            return self._base("AUTHORITY_PROVISIONING_REFERENCE_NAME_INVALID")
        manifest = {
            "manifest_version": AUTHORITY_PROVISIONING_MANIFEST_VERSION_V2,
            "scope_attestation": OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2,
            "root_anchor_symbol": "CENTRAL_DATA_DIR",
            "authority_state_relative_path": "c3/authority/c3_root_authority_state_v2.json",
            "revocation_state_relative_path": "c3/authority/c3_root_authority_revocations_v2.json",
            "key_provider_reference_name": key_provider_reference_name,
            "transaction_recovery_port_reference_name": transaction_recovery_port_reference_name,
            "resolved_recovery_port_reference_name": resolved_recovery_port_reference_name,
            "adapter_bundle_object_identity_sha256": actual_identity,
            "adapter_requirements": [
                {"role": "ROOT_STATE_PROVIDER", "class_name": "PersistentRootAuthorityStateProviderV2", "required_method": "read_current_root_authority_v2", "default_off": True},
                {"role": "ROOT_SIGNATURE_VERIFIER", "class_name": "InjectedRootAuthorityVerifierV2", "required_method": "verify_root_authority_signature_v2", "default_off": True},
                {"role": "ROOT_REVOCATION_SOURCE", "class_name": "PersistentRootAuthorityRevocationSourceV2", "required_method": "root_authority_key_revoked_v2", "default_off": True},
                {"role": "MULTISTORE_RECOVERY", "class_name": "CoordinatedMultistoreStartupRecoveryV2", "required_method": "recover_multistore_v2", "default_off": True},
            ],
            "adapter_count": 4,
            "same_storage_root_required": True,
            "same_maintenance_permit_instance_required": True,
            "same_root_attestation_required": True,
            "atomic_replace_required": True,
            "file_fsync_required": True,
            "directory_fsync_required": True,
            "secret_material_embedded": False,
            "render_accessed": False,
            "filesystem_accessed": False,
            "environment_read": False,
            "configuration_mutation_allowed": False,
            "runtime_wiring_allowed": False,
            "startup_recovery_allowed": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        manifest["manifest_sha256"] = authority_provisioning_manifest_sha256_v2(
            manifest
        )
        protected = ProtectedAuthorityProvisioningManifestV2(
            adapter_bundle_object_identity_sha256=actual_identity,
            manifest=copy.deepcopy(manifest),
            manifest_sha256=manifest["manifest_sha256"],
        )
        if not protected_authority_provisioning_manifest_valid_v2(protected):
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_SELF_VALIDATION_FAILED")
        result = self._base("")
        result.update(
            {
                "ok": True,
                "status": "C3_AUTHORITY_PROVISIONING_MANIFEST_V2_DEFINED_OFFLINE",
                "reason": None,
                "manifest_created": True,
                "protected_manifest": protected,
            }
        )
        return result


def build_dormant_authority_provisioning_manifest_contract_v2(
) -> DormantAuthorityProvisioningManifestContractV2:
    return DormantAuthorityProvisioningManifestContractV2()


__all__ = [
    "AUTHORITY_PROVISIONING_MANIFEST_VERSION_V2",
    "DormantAuthorityProvisioningManifestConfigV2",
    "DormantAuthorityProvisioningManifestContractV2",
    "OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2",
    "ProtectedAuthorityProvisioningManifestV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_MANIFEST_CONTRACT_V2_VERSION",
    "authority_provisioning_manifest_sha256_v2",
    "build_dormant_authority_provisioning_manifest_contract_v2",
    "protected_authority_provisioning_manifest_valid_v2",
]
