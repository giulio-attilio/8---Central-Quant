"""Protected synthetic provisioning receipt for the C3 authority boundary.

The receipt binds one exact protected manifest, one exact dormant adapter bundle,
and three exact synthetic reference objects.  It performs no resolution or I/O
and cannot attest that production provisioning has happened.
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
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_CONTRACT_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-RECEIPT-CONTRACT-V2"
)
OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2 = (
    "C3_AUTHORITY_PROVISIONING_RECEIPT_SYNTHETIC_OFFLINE_ONLY_V2"
)
AUTHORITY_PROVISIONING_RECEIPT_VERSION_V2 = (
    "C3_AUTHORITY_PROVISIONING_RECEIPT_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_REFERENCE_ROLES = {
    "key_provider_reference_name": "ROOT_AUTHORITY_KEY_PROVIDER",
    "transaction_recovery_port_reference_name": "TRANSACTION_RECOVERY_PORT",
    "resolved_recovery_port_reference_name": "RESOLVED_RECOVERY_PORT",
}
_PRODUCTION_BLOCKERS = (
    "PROVISIONING_RECEIPT_IS_SYNTHETIC_ONLY",
    "REFERENCE_NAMES_HAVE_NOT_BEEN_RESOLVED_IN_PRODUCTION",
    "AUTHENTICATED_KEY_MATERIAL_HAS_NOT_BEEN_PROVISIONED",
    "PERSISTENT_AUTHORITY_STATE_HAS_NOT_BEEN_PROVISIONED",
    "PERSISTENT_REVOCATION_STATE_HAS_NOT_BEEN_PROVISIONED",
    "TRANSACTION_RECOVERY_PORT_HAS_NOT_BEEN_BOUND",
    "RESOLVED_RECOVERY_PORT_HAS_NOT_BEEN_BOUND",
    "PRODUCTION_PROVISIONING_RECEIPT_NOT_ISSUED",
    "RUNTIME_CONFIGURATION_NOT_APPLIED",
    "STARTUP_RECOVERY_NOT_EXECUTED",
    "LIVE_REMAINS_FORBIDDEN",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def authority_provisioning_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


@dataclass(frozen=True, repr=False)
class SyntheticAuthorityProvisioningReferenceV2:
    reference_name: str = field(repr=False)
    reference_role: str = field(repr=False)
    synthetic_only: bool = field(default=True, repr=False)

    def __repr__(self) -> str:
        return "SyntheticAuthorityProvisioningReferenceV2(<protected>)"


@dataclass(frozen=True)
class DormantAuthorityProvisioningReceiptConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_manifest_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_adapter_bundle_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_reference_object_identity_sha256_by_name: Mapping[str, str] = field(
        default_factory=dict, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedAuthorityProvisioningReceiptV2:
    manifest_object_identity_sha256: str = field(repr=False)
    adapter_bundle_object_identity_sha256: str = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedAuthorityProvisioningReceiptV2(<protected>)"


def protected_authority_provisioning_receipt_valid_v2(value: Any) -> bool:
    if not isinstance(value, ProtectedAuthorityProvisioningReceiptV2):
        return False
    receipt = value.receipt
    if not isinstance(receipt, Mapping):
        return False
    try:
        identities = receipt["reference_object_identity_sha256_by_name"]
        return bool(
            set(receipt)
            == {
                "receipt_version",
                "scope_attestation",
                "manifest_sha256",
                "manifest_object_identity_sha256",
                "adapter_bundle_object_identity_sha256",
                "root_anchor_symbol",
                "authority_state_relative_path",
                "revocation_state_relative_path",
                "reference_object_identity_sha256_by_name",
                "reference_binding_count",
                "synthetic_reference_bindings_only",
                "manifest_validated",
                "same_manifest_instance_required",
                "same_adapter_bundle_instance_required",
                "same_reference_instances_required",
                "same_storage_root_required",
                "same_maintenance_permit_instance_required",
                "secret_material_embedded",
                "filesystem_accessed",
                "environment_read",
                "render_accessed",
                "configuration_mutation_allowed",
                "runtime_wiring_allowed",
                "startup_recovery_allowed",
                "production_ready",
                "activation_allowed",
                "live_allowed",
                "production_blockers",
                "receipt_sha256",
            }
            and receipt["receipt_version"]
            == AUTHORITY_PROVISIONING_RECEIPT_VERSION_V2
            and receipt["scope_attestation"]
            == OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2
            and _valid_sha(receipt["manifest_sha256"])
            and _valid_sha(receipt["manifest_object_identity_sha256"])
            and receipt["manifest_object_identity_sha256"]
            == value.manifest_object_identity_sha256
            and _valid_sha(receipt["adapter_bundle_object_identity_sha256"])
            and receipt["adapter_bundle_object_identity_sha256"]
            == value.adapter_bundle_object_identity_sha256
            and receipt["root_anchor_symbol"] == "CENTRAL_DATA_DIR"
            and isinstance(receipt["authority_state_relative_path"], str)
            and isinstance(receipt["revocation_state_relative_path"], str)
            and isinstance(identities, Mapping)
            and len(identities) == 3
            and all(_valid_sha(item) for item in identities.values())
            and len(set(identities.values())) == 3
            and receipt["reference_binding_count"] == 3
            and all(
                receipt[field_name] is True
                for field_name in (
                    "synthetic_reference_bindings_only",
                    "manifest_validated",
                    "same_manifest_instance_required",
                    "same_adapter_bundle_instance_required",
                    "same_reference_instances_required",
                    "same_storage_root_required",
                    "same_maintenance_permit_instance_required",
                )
            )
            and all(
                receipt[field_name] is False
                for field_name in (
                    "secret_material_embedded",
                    "filesystem_accessed",
                    "environment_read",
                    "render_accessed",
                    "configuration_mutation_allowed",
                    "runtime_wiring_allowed",
                    "startup_recovery_allowed",
                    "production_ready",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and receipt["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and _valid_sha(receipt["receipt_sha256"])
            and receipt["receipt_sha256"] == value.receipt_sha256
            and hmac.compare_digest(
                value.receipt_sha256,
                authority_provisioning_receipt_sha256_v2(receipt),
            )
        )
    except Exception:
        return False


class DormantAuthorityProvisioningReceiptContractV2:
    def __init__(
        self,
        config: DormantAuthorityProvisioningReceiptConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantAuthorityProvisioningReceiptConfigV2()

    def __repr__(self) -> str:
        return "DormantAuthorityProvisioningReceiptContractV2(<protected>)"

    @staticmethod
    def _base(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_AUTHORITY_PROVISIONING_RECEIPT_V2_BLOCKED",
            "reason": reason,
            "receipt_created": False,
            "protected_receipt": None,
            "synthetic_reference_bindings_only": True,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def issue_offline(
        self,
        *,
        protected_manifest: Any,
        adapter_bundle: Any,
        reference_bindings: Mapping[str, Any],
    ) -> dict[str, Any]:
        config = self._config
        if config.enabled is not True:
            return self._base("AUTHORITY_PROVISIONING_RECEIPT_DEFAULT_OFF")
        if (
            config.scope_attestation
            != OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2
        ):
            return self._base("AUTHORITY_PROVISIONING_RECEIPT_SCOPE_INVALID")
        if not manifest_v2.protected_authority_provisioning_manifest_valid_v2(
            protected_manifest
        ):
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_INVALID")

        manifest_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                protected_manifest
            )
        )
        adapter_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                adapter_bundle
            )
        )
        expected_manifest_identity = str(
            config.expected_manifest_object_identity_sha256 or ""
        )
        expected_adapter_identity = str(
            config.expected_adapter_bundle_object_identity_sha256 or ""
        )
        if not (
            _valid_sha(expected_manifest_identity)
            and hmac.compare_digest(manifest_identity, expected_manifest_identity)
        ):
            return self._base("AUTHORITY_PROVISIONING_MANIFEST_INSTANCE_INVALID")
        if not (
            type(adapter_bundle)
            is adapters_v2.DormantAuthenticatedPersistentAuthorityProductionAdaptersV2
            and _valid_sha(expected_adapter_identity)
            and hmac.compare_digest(adapter_identity, expected_adapter_identity)
            and hmac.compare_digest(
                adapter_identity,
                protected_manifest.adapter_bundle_object_identity_sha256,
            )
            and adapter_bundle.snapshot().get("default_off") is True
            and adapter_bundle.snapshot().get("filesystem_accessed") is False
        ):
            return self._base("AUTHORITY_PROVISIONING_ADAPTER_BUNDLE_INVALID")

        manifest = protected_manifest.manifest
        expected_names = {
            manifest[field_name]: role
            for field_name, role in _REFERENCE_ROLES.items()
        }
        expected_reference_identities = dict(
            config.expected_reference_object_identity_sha256_by_name
        )
        if not (
            isinstance(reference_bindings, Mapping)
            and set(reference_bindings) == set(expected_names)
            and set(expected_reference_identities) == set(expected_names)
        ):
            return self._base("AUTHORITY_PROVISIONING_REFERENCE_SET_INVALID")

        actual_reference_identities: dict[str, str] = {}
        for name, role in expected_names.items():
            reference = reference_bindings[name]
            identity = (
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    reference
                )
            )
            if not (
                type(reference) is SyntheticAuthorityProvisioningReferenceV2
                and reference.reference_name == name
                and reference.reference_role == role
                and reference.synthetic_only is True
                and _valid_sha(expected_reference_identities[name])
                and hmac.compare_digest(
                    identity, expected_reference_identities[name]
                )
            ):
                return self._base("AUTHORITY_PROVISIONING_REFERENCE_BINDING_INVALID")
            actual_reference_identities[name] = identity
        if len(set(actual_reference_identities.values())) != 3:
            return self._base("AUTHORITY_PROVISIONING_REFERENCE_IDENTITY_REUSED")

        receipt = {
            "receipt_version": AUTHORITY_PROVISIONING_RECEIPT_VERSION_V2,
            "scope_attestation": OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2,
            "manifest_sha256": protected_manifest.manifest_sha256,
            "manifest_object_identity_sha256": manifest_identity,
            "adapter_bundle_object_identity_sha256": adapter_identity,
            "root_anchor_symbol": manifest["root_anchor_symbol"],
            "authority_state_relative_path": manifest["authority_state_relative_path"],
            "revocation_state_relative_path": manifest["revocation_state_relative_path"],
            "reference_object_identity_sha256_by_name": dict(
                sorted(actual_reference_identities.items())
            ),
            "reference_binding_count": 3,
            "synthetic_reference_bindings_only": True,
            "manifest_validated": True,
            "same_manifest_instance_required": True,
            "same_adapter_bundle_instance_required": True,
            "same_reference_instances_required": True,
            "same_storage_root_required": True,
            "same_maintenance_permit_instance_required": True,
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
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["receipt_sha256"] = authority_provisioning_receipt_sha256_v2(
            receipt
        )
        protected_receipt = ProtectedAuthorityProvisioningReceiptV2(
            manifest_object_identity_sha256=manifest_identity,
            adapter_bundle_object_identity_sha256=adapter_identity,
            receipt=copy.deepcopy(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_authority_provisioning_receipt_valid_v2(
            protected_receipt
        ):
            return self._base("AUTHORITY_PROVISIONING_RECEIPT_SELF_VALIDATION_FAILED")
        result = self._base("")
        result.update(
            {
                "ok": True,
                "status": "C3_AUTHORITY_PROVISIONING_RECEIPT_V2_ISSUED_OFFLINE",
                "reason": None,
                "receipt_created": True,
                "protected_receipt": protected_receipt,
            }
        )
        return result


def build_dormant_authority_provisioning_receipt_contract_v2(
) -> DormantAuthorityProvisioningReceiptContractV2:
    return DormantAuthorityProvisioningReceiptContractV2()


__all__ = [
    "AUTHORITY_PROVISIONING_RECEIPT_VERSION_V2",
    "DormantAuthorityProvisioningReceiptConfigV2",
    "DormantAuthorityProvisioningReceiptContractV2",
    "OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2",
    "ProtectedAuthorityProvisioningReceiptV2",
    "SyntheticAuthorityProvisioningReferenceV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_CONTRACT_V2_VERSION",
    "authority_provisioning_receipt_sha256_v2",
    "build_dormant_authority_provisioning_receipt_contract_v2",
    "protected_authority_provisioning_receipt_valid_v2",
]
