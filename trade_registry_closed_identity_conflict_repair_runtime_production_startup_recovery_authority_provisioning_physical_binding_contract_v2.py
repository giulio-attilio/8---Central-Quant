"""Dormant physical-provisioning binding plan for C3 authority recovery.

The contract binds the exact manifest, synthetic provisioning receipt,
authenticated verification and dormant adapter bundle to a protected synthetic
description of future physical resources.  It performs no path resolution or
I/O and never claims that production resources exist.
"""

from __future__ import annotations

import copy
import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2 as manifest_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2 as authenticated_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2 as receipt_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_CONTRACT_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-PHYSICAL-BINDING-"
    "CONTRACT-V2"
)
OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2 = (
    "C3_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SYNTHETIC_OFFLINE_ONLY_V2"
)
AUTHORITY_PROVISIONING_PHYSICAL_EVIDENCE_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_PHYSICAL_EVIDENCE_SYNTHETIC_V2"
)
AUTHORITY_PROVISIONING_PHYSICAL_BINDING_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PRODUCTION_BLOCKERS = (
    "PHYSICAL_BINDING_USES_SYNTHETIC_EVIDENCE_ONLY",
    "CENTRAL_DATA_DIR_HAS_NOT_BEEN_RESOLVED",
    "AUTHORITY_AND_REVOCATION_PATHS_HAVE_NOT_BEEN_OPENED",
    "KEY_PROVIDER_REFERENCE_HAS_NOT_BEEN_RESOLVED",
    "RECOVERY_PORT_REFERENCES_HAVE_NOT_BEEN_RESOLVED",
    "PERSISTENT_GENERATIONS_HAVE_NOT_BEEN_OBSERVED",
    "ATOMIC_REPLACE_AND_FSYNC_HAVE_NOT_BEEN_PROBED",
    "PRODUCTION_RECEIPT_HAS_NOT_BEEN_ISSUED",
    "RUNTIME_CONFIGURATION_NOT_APPLIED",
    "STARTUP_RECOVERY_NOT_EXECUTED",
    "LIVE_REMAINS_FORBIDDEN",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def authority_provisioning_physical_evidence_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


def authority_provisioning_physical_binding_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2:
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2(<protected>)"


def protected_synthetic_physical_authority_provisioning_evidence_valid_v2(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2
    ):
        return False
    evidence = value.evidence
    if not isinstance(evidence, Mapping):
        return False
    try:
        reference_bindings = evidence[
            "resolved_reference_binding_sha256_by_name"
        ]
        return bool(
            set(evidence)
            == {
                "evidence_version",
                "scope_attestation",
                "manifest_sha256",
                "provisioning_receipt_sha256",
                "authenticated_verification_sha256",
                "root_authority_attestation_sha256",
                "storage_binding_sha256",
                "root_anchor_symbol",
                "root_anchor_binding_sha256",
                "authority_state_relative_path",
                "authority_state_path_binding_sha256",
                "revocation_state_relative_path",
                "revocation_state_path_binding_sha256",
                "resolved_reference_binding_sha256_by_name",
                "reference_binding_count",
                "authority_state_generation",
                "revocation_state_generation",
                "atomic_replace_required",
                "file_fsync_required",
                "directory_fsync_required",
                "same_storage_root_required",
                "same_maintenance_permit_instance_required",
                "synthetic_only",
                "physical_paths_resolved",
                "production_resources_observed",
                "persistent_generations_observed",
                "durability_probe_executed",
                "secret_material_embedded",
                "filesystem_accessed",
                "environment_read",
                "network_accessed",
                "render_accessed",
                "evidence_sha256",
            }
            and evidence["evidence_version"]
            == AUTHORITY_PROVISIONING_PHYSICAL_EVIDENCE_VERSION_V2
            and evidence["scope_attestation"]
            == OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2
            and all(
                _valid_sha(evidence[field_name])
                for field_name in (
                    "manifest_sha256",
                    "provisioning_receipt_sha256",
                    "authenticated_verification_sha256",
                    "root_authority_attestation_sha256",
                    "storage_binding_sha256",
                    "root_anchor_binding_sha256",
                    "authority_state_path_binding_sha256",
                    "revocation_state_path_binding_sha256",
                )
            )
            and evidence["root_anchor_symbol"] == "CENTRAL_DATA_DIR"
            and isinstance(evidence["authority_state_relative_path"], str)
            and isinstance(evidence["revocation_state_relative_path"], str)
            and isinstance(reference_bindings, Mapping)
            and len(reference_bindings) == 3
            and all(_valid_sha(item) for item in reference_bindings.values())
            and len(set(reference_bindings.values())) == 3
            and evidence["reference_binding_count"] == 3
            and type(evidence["authority_state_generation"]) is int
            and evidence["authority_state_generation"] >= 1
            and type(evidence["revocation_state_generation"]) is int
            and evidence["revocation_state_generation"] >= 1
            and all(
                evidence[field_name] is True
                for field_name in (
                    "atomic_replace_required",
                    "file_fsync_required",
                    "directory_fsync_required",
                    "same_storage_root_required",
                    "same_maintenance_permit_instance_required",
                    "synthetic_only",
                )
            )
            and all(
                evidence[field_name] is False
                for field_name in (
                    "physical_paths_resolved",
                    "production_resources_observed",
                    "persistent_generations_observed",
                    "durability_probe_executed",
                    "secret_material_embedded",
                    "filesystem_accessed",
                    "environment_read",
                    "network_accessed",
                    "render_accessed",
                )
            )
            and _valid_sha(evidence["evidence_sha256"])
            and evidence["evidence_sha256"] == value.evidence_sha256
            and hmac.compare_digest(
                value.evidence_sha256,
                authority_provisioning_physical_evidence_sha256_v2(evidence),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantAuthorityProvisioningPhysicalBindingConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_manifest_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_receipt_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authenticated_verification_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_adapter_bundle_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_physical_evidence_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedAuthorityProvisioningPhysicalBindingV2:
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedAuthorityProvisioningPhysicalBindingV2(<protected>)"


def protected_authority_provisioning_physical_binding_valid_v2(
    value: Any,
) -> bool:
    if not isinstance(value, ProtectedAuthorityProvisioningPhysicalBindingV2):
        return False
    binding = value.binding
    if not isinstance(binding, Mapping):
        return False
    try:
        return bool(
            set(binding)
            == {
                "binding_version",
                "scope_attestation",
                "manifest_object_identity_sha256",
                "receipt_object_identity_sha256",
                "authenticated_verification_object_identity_sha256",
                "adapter_bundle_object_identity_sha256",
                "physical_evidence_object_identity_sha256",
                "manifest_sha256",
                "provisioning_receipt_sha256",
                "authenticated_verification_sha256",
                "physical_evidence_sha256",
                "root_authority_attestation_sha256",
                "storage_binding_sha256",
                "root_anchor_binding_sha256",
                "authority_state_path_binding_sha256",
                "revocation_state_path_binding_sha256",
                "reference_binding_count",
                "exact_instance_chain_verified",
                "cross_hash_chain_verified",
                "authenticated_authority_verified",
                "revocation_checked",
                "physical_binding_planned",
                "durability_requirements_preserved",
                "synthetic_only",
                "physical_paths_resolved",
                "production_resources_observed",
                "persistent_generations_observed",
                "durability_probe_executed",
                "secret_material_embedded",
                "real_registry_accessed",
                "filesystem_accessed",
                "environment_read",
                "network_accessed",
                "render_accessed",
                "broker_called",
                "no_order_sent",
                "runtime_wiring_allowed",
                "startup_recovery_allowed",
                "production_ready",
                "activation_allowed",
                "live_allowed",
                "production_blockers",
                "binding_sha256",
            }
            and binding["binding_version"]
            == AUTHORITY_PROVISIONING_PHYSICAL_BINDING_VERSION_V2
            and binding["scope_attestation"]
            == OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2
            and all(
                _valid_sha(binding[field_name])
                for field_name in (
                    "manifest_object_identity_sha256",
                    "receipt_object_identity_sha256",
                    "authenticated_verification_object_identity_sha256",
                    "adapter_bundle_object_identity_sha256",
                    "physical_evidence_object_identity_sha256",
                    "manifest_sha256",
                    "provisioning_receipt_sha256",
                    "authenticated_verification_sha256",
                    "physical_evidence_sha256",
                    "root_authority_attestation_sha256",
                    "storage_binding_sha256",
                    "root_anchor_binding_sha256",
                    "authority_state_path_binding_sha256",
                    "revocation_state_path_binding_sha256",
                )
            )
            and binding["reference_binding_count"] == 3
            and all(
                binding[field_name] is True
                for field_name in (
                    "exact_instance_chain_verified",
                    "cross_hash_chain_verified",
                    "authenticated_authority_verified",
                    "revocation_checked",
                    "physical_binding_planned",
                    "durability_requirements_preserved",
                    "synthetic_only",
                    "no_order_sent",
                )
            )
            and all(
                binding[field_name] is False
                for field_name in (
                    "physical_paths_resolved",
                    "production_resources_observed",
                    "persistent_generations_observed",
                    "durability_probe_executed",
                    "secret_material_embedded",
                    "real_registry_accessed",
                    "filesystem_accessed",
                    "environment_read",
                    "network_accessed",
                    "render_accessed",
                    "broker_called",
                    "runtime_wiring_allowed",
                    "startup_recovery_allowed",
                    "production_ready",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and binding["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and _valid_sha(binding["binding_sha256"])
            and binding["binding_sha256"] == value.binding_sha256
            and hmac.compare_digest(
                value.binding_sha256,
                authority_provisioning_physical_binding_sha256_v2(binding),
            )
        )
    except Exception:
        return False


def build_synthetic_physical_authority_provisioning_evidence_v2(
    *,
    protected_manifest: manifest_v2.ProtectedAuthorityProvisioningManifestV2,
    provisioning_receipt: receipt_v2.ProtectedAuthorityProvisioningReceiptV2,
    authenticated_verification: authenticated_v2.ProtectedAuthenticatedProvisioningReceiptVerificationV2,
) -> ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2:
    manifest = protected_manifest.manifest
    verification = authenticated_verification.verification
    root_anchor_binding = hash_v2.stable_sha256_v2(
        {
            "root_anchor_symbol": manifest["root_anchor_symbol"],
            "synthetic_resolution": True,
        }
    )
    authority_path_binding = hash_v2.stable_sha256_v2(
        {
            "root_anchor_binding_sha256": root_anchor_binding,
            "relative_path": manifest["authority_state_relative_path"],
        }
    )
    revocation_path_binding = hash_v2.stable_sha256_v2(
        {
            "root_anchor_binding_sha256": root_anchor_binding,
            "relative_path": manifest["revocation_state_relative_path"],
        }
    )
    resolved_bindings = {
        name: hash_v2.stable_sha256_v2(
            {
                "reference_name": name,
                "synthetic_reference_identity_sha256": reference_identity,
                "synthetic_resolution": True,
            }
        )
        for name, reference_identity in provisioning_receipt.receipt[
            "reference_object_identity_sha256_by_name"
        ].items()
    }
    evidence = {
        "evidence_version": AUTHORITY_PROVISIONING_PHYSICAL_EVIDENCE_VERSION_V2,
        "scope_attestation": OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2,
        "manifest_sha256": protected_manifest.manifest_sha256,
        "provisioning_receipt_sha256": provisioning_receipt.receipt_sha256,
        "authenticated_verification_sha256": authenticated_verification.verification_sha256,
        "root_authority_attestation_sha256": verification[
            "root_authority_attestation_sha256"
        ],
        "storage_binding_sha256": verification["storage_binding_sha256"],
        "root_anchor_symbol": manifest["root_anchor_symbol"],
        "root_anchor_binding_sha256": root_anchor_binding,
        "authority_state_relative_path": manifest[
            "authority_state_relative_path"
        ],
        "authority_state_path_binding_sha256": authority_path_binding,
        "revocation_state_relative_path": manifest[
            "revocation_state_relative_path"
        ],
        "revocation_state_path_binding_sha256": revocation_path_binding,
        "resolved_reference_binding_sha256_by_name": dict(
            sorted(resolved_bindings.items())
        ),
        "reference_binding_count": 3,
        "authority_state_generation": verification[
            "authority_state_generation"
        ],
        "revocation_state_generation": verification[
            "revocation_state_generation"
        ],
        "atomic_replace_required": True,
        "file_fsync_required": True,
        "directory_fsync_required": True,
        "same_storage_root_required": True,
        "same_maintenance_permit_instance_required": True,
        "synthetic_only": True,
        "physical_paths_resolved": False,
        "production_resources_observed": False,
        "persistent_generations_observed": False,
        "durability_probe_executed": False,
        "secret_material_embedded": False,
        "filesystem_accessed": False,
        "environment_read": False,
        "network_accessed": False,
        "render_accessed": False,
    }
    evidence["evidence_sha256"] = (
        authority_provisioning_physical_evidence_sha256_v2(evidence)
    )
    protected = ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2(
        evidence=copy.deepcopy(evidence),
        evidence_sha256=evidence["evidence_sha256"],
    )
    if not protected_synthetic_physical_authority_provisioning_evidence_valid_v2(
        protected
    ):
        raise ValueError("SYNTHETIC_PHYSICAL_PROVISIONING_EVIDENCE_INVALID")
    return protected


class DormantAuthorityProvisioningPhysicalBindingContractV2:
    def __init__(
        self,
        config: DormantAuthorityProvisioningPhysicalBindingConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantAuthorityProvisioningPhysicalBindingConfigV2()

    def __repr__(self) -> str:
        return "DormantAuthorityProvisioningPhysicalBindingContractV2(<protected>)"

    @staticmethod
    def _base(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_V2_BLOCKED",
            "reason": reason,
            "binding_created": False,
            "protected_binding": None,
            "synthetic_only": True,
            "physical_paths_resolved": False,
            "production_resources_observed": False,
            "persistent_generations_observed": False,
            "durability_probe_executed": False,
            "secret_material_embedded": False,
            "real_registry_accessed": False,
            "filesystem_accessed": False,
            "environment_read": False,
            "network_accessed": False,
            "render_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "runtime_wiring_allowed": False,
            "startup_recovery_allowed": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def bind_offline(
        self,
        *,
        protected_manifest: Any,
        provisioning_receipt: Any,
        authenticated_verification: Any,
        adapter_bundle: Any,
        physical_evidence: Any,
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._base("AUTHORITY_PROVISIONING_PHYSICAL_BINDING_DEFAULT_OFF")
        if (
            config.scope_attestation
            != OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2
        ):
            return self._base("AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_INVALID")
        if not manifest_v2.protected_authority_provisioning_manifest_valid_v2(
            protected_manifest
        ):
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_INVALID")
        if not receipt_v2.protected_authority_provisioning_receipt_valid_v2(
            provisioning_receipt
        ):
            return self._base("AUTHORITY_PROVISIONING_RECEIPT_INVALID")
        if not authenticated_v2.protected_authenticated_provisioning_receipt_verification_valid_v2(
            authenticated_verification
        ):
            return self._base("AUTHENTICATED_PROVISIONING_VERIFICATION_INVALID")
        if not protected_synthetic_physical_authority_provisioning_evidence_valid_v2(
            physical_evidence
        ):
            return self._base("PHYSICAL_PROVISIONING_EVIDENCE_INVALID")
        if type(adapter_bundle) is not adapters_v2.DormantAuthenticatedPersistentAuthorityProductionAdaptersV2:
            return self._base("AUTHORITY_PROVISIONING_ADAPTER_BUNDLE_INVALID")

        objects = (
            protected_manifest,
            provisioning_receipt,
            authenticated_verification,
            adapter_bundle,
            physical_evidence,
        )
        actual_identities = tuple(_object_identity(item) for item in objects)
        expected_identities = (
            config.expected_manifest_object_identity_sha256,
            config.expected_receipt_object_identity_sha256,
            config.expected_authenticated_verification_object_identity_sha256,
            config.expected_adapter_bundle_object_identity_sha256,
            config.expected_physical_evidence_object_identity_sha256,
        )
        if not all(_valid_sha(item) for item in expected_identities) or any(
            not hmac.compare_digest(str(expected), actual)
            for expected, actual in zip(expected_identities, actual_identities)
        ):
            return self._base("AUTHORITY_PROVISIONING_EXACT_INSTANCE_CHAIN_INVALID")

        manifest = protected_manifest.manifest
        receipt = provisioning_receipt.receipt
        verification = authenticated_verification.verification
        evidence = physical_evidence.evidence
        adapter_identity = actual_identities[3]
        expected_reference_names = {
            manifest["key_provider_reference_name"],
            manifest["transaction_recovery_port_reference_name"],
            manifest["resolved_recovery_port_reference_name"],
        }
        cross_hashes_valid = bool(
            receipt["manifest_sha256"] == protected_manifest.manifest_sha256
            and verification["manifest_sha256"]
            == protected_manifest.manifest_sha256
            and verification["base_receipt_sha256"]
            == provisioning_receipt.receipt_sha256
            and authenticated_verification.protected_receipt_object_identity_sha256
            == actual_identities[1]
            and manifest["adapter_bundle_object_identity_sha256"]
            == adapter_identity
            and receipt["adapter_bundle_object_identity_sha256"]
            == adapter_identity
            and evidence["manifest_sha256"] == protected_manifest.manifest_sha256
            and evidence["provisioning_receipt_sha256"]
            == provisioning_receipt.receipt_sha256
            and evidence["authenticated_verification_sha256"]
            == authenticated_verification.verification_sha256
            and evidence["root_authority_attestation_sha256"]
            == verification["root_authority_attestation_sha256"]
            and evidence["storage_binding_sha256"]
            == verification["storage_binding_sha256"]
            and evidence["authority_state_generation"]
            == verification["authority_state_generation"]
            and evidence["revocation_state_generation"]
            == verification["revocation_state_generation"]
            and evidence["authority_state_relative_path"]
            == manifest["authority_state_relative_path"]
            and evidence["revocation_state_relative_path"]
            == manifest["revocation_state_relative_path"]
            and set(evidence["resolved_reference_binding_sha256_by_name"])
            == expected_reference_names
            and adapter_bundle.snapshot().get("default_off") is True
            and adapter_bundle.snapshot().get("filesystem_accessed") is False
        )
        if not cross_hashes_valid:
            return self._base("AUTHORITY_PROVISIONING_CROSS_HASH_CHAIN_INVALID")

        binding = {
            "binding_version": AUTHORITY_PROVISIONING_PHYSICAL_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2,
            "manifest_object_identity_sha256": actual_identities[0],
            "receipt_object_identity_sha256": actual_identities[1],
            "authenticated_verification_object_identity_sha256": actual_identities[2],
            "adapter_bundle_object_identity_sha256": adapter_identity,
            "physical_evidence_object_identity_sha256": actual_identities[4],
            "manifest_sha256": protected_manifest.manifest_sha256,
            "provisioning_receipt_sha256": provisioning_receipt.receipt_sha256,
            "authenticated_verification_sha256": authenticated_verification.verification_sha256,
            "physical_evidence_sha256": physical_evidence.evidence_sha256,
            "root_authority_attestation_sha256": verification[
                "root_authority_attestation_sha256"
            ],
            "storage_binding_sha256": verification["storage_binding_sha256"],
            "root_anchor_binding_sha256": evidence[
                "root_anchor_binding_sha256"
            ],
            "authority_state_path_binding_sha256": evidence[
                "authority_state_path_binding_sha256"
            ],
            "revocation_state_path_binding_sha256": evidence[
                "revocation_state_path_binding_sha256"
            ],
            "reference_binding_count": 3,
            "exact_instance_chain_verified": True,
            "cross_hash_chain_verified": True,
            "authenticated_authority_verified": True,
            "revocation_checked": True,
            "physical_binding_planned": True,
            "durability_requirements_preserved": True,
            "synthetic_only": True,
            "physical_paths_resolved": False,
            "production_resources_observed": False,
            "persistent_generations_observed": False,
            "durability_probe_executed": False,
            "secret_material_embedded": False,
            "real_registry_accessed": False,
            "filesystem_accessed": False,
            "environment_read": False,
            "network_accessed": False,
            "render_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "runtime_wiring_allowed": False,
            "startup_recovery_allowed": False,
            "production_ready": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        binding["binding_sha256"] = (
            authority_provisioning_physical_binding_sha256_v2(binding)
        )
        protected_binding = ProtectedAuthorityProvisioningPhysicalBindingV2(
            binding=copy.deepcopy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_authority_provisioning_physical_binding_valid_v2(
            protected_binding
        ):
            return self._base("AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SELF_VALIDATION_FAILED")
        result = self._base("")
        result.update(
            {
                "ok": True,
                "status": "C3_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_V2_DEFINED_OFFLINE",
                "reason": None,
                "binding_created": True,
                "protected_binding": protected_binding,
            }
        )
        return result


def build_dormant_authority_provisioning_physical_binding_contract_v2(
) -> DormantAuthorityProvisioningPhysicalBindingContractV2:
    return DormantAuthorityProvisioningPhysicalBindingContractV2()


__all__ = [
    "AUTHORITY_PROVISIONING_PHYSICAL_BINDING_VERSION_V2",
    "AUTHORITY_PROVISIONING_PHYSICAL_EVIDENCE_VERSION_V2",
    "DormantAuthorityProvisioningPhysicalBindingConfigV2",
    "DormantAuthorityProvisioningPhysicalBindingContractV2",
    "OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2",
    "ProtectedAuthorityProvisioningPhysicalBindingV2",
    "ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_CONTRACT_V2_VERSION",
    "authority_provisioning_physical_binding_sha256_v2",
    "authority_provisioning_physical_evidence_sha256_v2",
    "build_dormant_authority_provisioning_physical_binding_contract_v2",
    "build_synthetic_physical_authority_provisioning_evidence_v2",
    "protected_authority_provisioning_physical_binding_valid_v2",
    "protected_synthetic_physical_authority_provisioning_evidence_valid_v2",
]
