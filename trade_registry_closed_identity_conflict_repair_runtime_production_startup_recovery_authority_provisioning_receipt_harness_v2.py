"""In-memory harness for the synthetic authority provisioning receipt."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_harness_v2 as manifest_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2 as receipt_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-RECEIPT-HARNESS-V2"
)


def build_authority_provisioning_receipt_context_v2() -> dict[str, Any]:
    manifest_context = (
        manifest_harness_v2.build_authority_provisioning_manifest_context_v2()
    )
    bundle = manifest_context["bundle"]
    protected_manifest = manifest_context["result"]["protected_manifest"]
    manifest = protected_manifest.manifest
    roles = {
        manifest["key_provider_reference_name"]: "ROOT_AUTHORITY_KEY_PROVIDER",
        manifest["transaction_recovery_port_reference_name"]: "TRANSACTION_RECOVERY_PORT",
        manifest["resolved_recovery_port_reference_name"]: "RESOLVED_RECOVERY_PORT",
    }
    references = {
        name: receipt_v2.SyntheticAuthorityProvisioningReferenceV2(
            reference_name=name,
            reference_role=role,
        )
        for name, role in roles.items()
    }
    reference_identities = {
        name: identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
            reference
        )
        for name, reference in references.items()
    }
    contract = receipt_v2.DormantAuthorityProvisioningReceiptContractV2(
        receipt_v2.DormantAuthorityProvisioningReceiptConfigV2(
            enabled=True,
            scope_attestation=receipt_v2.OFFLINE_AUTHORITY_PROVISIONING_RECEIPT_SCOPE_ATTESTATION_V2,
            expected_manifest_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    protected_manifest
                )
            ),
            expected_adapter_bundle_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    bundle
                )
            ),
            expected_reference_object_identity_sha256_by_name=reference_identities,
        )
    )
    result = contract.issue_offline(
        protected_manifest=protected_manifest,
        adapter_bundle=bundle,
        reference_bindings=references,
    )
    return {
        "manifest_context": manifest_context,
        "bundle": bundle,
        "protected_manifest": protected_manifest,
        "references": references,
        "contract": contract,
        "result": result,
    }


def run_authority_provisioning_receipt_harness_v2() -> dict[str, Any]:
    values = build_authority_provisioning_receipt_context_v2()
    result = values["result"]
    protected = result.get("protected_receipt")
    receipt = dict(protected.receipt) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and receipt_v2.protected_authority_provisioning_receipt_valid_v2(
            protected
        )
        and receipt.get("reference_binding_count") == 3
        and receipt.get("synthetic_reference_bindings_only") is True
        and receipt.get("manifest_validated") is True
        and receipt.get("secret_material_embedded") is False
        and receipt.get("filesystem_accessed") is False
        and receipt.get("environment_read") is False
        and receipt.get("render_accessed") is False
        and receipt.get("runtime_wiring_allowed") is False
        and receipt.get("startup_recovery_allowed") is False
        and receipt.get("production_ready") is False
        and receipt.get("live_allowed") is False
        and repr(protected)
        == "ProtectedAuthorityProvisioningReceiptV2(<protected>)"
    )
    return {
        "ok": ok,
        "status": (
            "AUTHORITY_PROVISIONING_RECEIPT_HARNESS_V2_PASSED"
            if ok
            else "AUTHORITY_PROVISIONING_RECEIPT_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_RECEIPT_HARNESS_V2_VERSION,
        "receipt_sha256": getattr(protected, "receipt_sha256", None),
        "reference_binding_count": receipt.get("reference_binding_count", 0),
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
    }


__all__ = [
    "build_authority_provisioning_receipt_context_v2",
    "run_authority_provisioning_receipt_harness_v2",
]
