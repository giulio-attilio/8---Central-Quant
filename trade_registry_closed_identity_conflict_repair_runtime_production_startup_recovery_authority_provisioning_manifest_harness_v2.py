"""In-memory harness for the secret-free authority provisioning manifest."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2 as manifest_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_MANIFEST_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-MANIFEST-HARNESS-V2"
)


def build_authority_provisioning_manifest_context_v2() -> dict[str, Any]:
    bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()
    identity = identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        bundle
    )
    contract = manifest_v2.DormantAuthorityProvisioningManifestContractV2(
        manifest_v2.DormantAuthorityProvisioningManifestConfigV2(
            enabled=True,
            scope_attestation=manifest_v2.OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2,
            expected_adapter_bundle_object_identity_sha256=identity,
        )
    )
    result = contract.define_offline(
        adapter_bundle=bundle,
        key_provider_reference_name="C3_ROOT_AUTHORITY_KEY_PROVIDER_REF",
        transaction_recovery_port_reference_name="C3_TRANSACTION_RECOVERY_PORT_REF",
        resolved_recovery_port_reference_name="C3_RESOLVED_RECOVERY_PORT_REF",
    )
    return {"bundle": bundle, "contract": contract, "result": result}


def run_authority_provisioning_manifest_harness_v2() -> dict[str, Any]:
    values = build_authority_provisioning_manifest_context_v2()
    result = values["result"]
    protected = result.get("protected_manifest")
    manifest = dict(protected.manifest) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and manifest_v2.protected_authority_provisioning_manifest_valid_v2(
            protected
        )
        and manifest.get("adapter_count") == 4
        and manifest.get("root_anchor_symbol") == "CENTRAL_DATA_DIR"
        and manifest.get("secret_material_embedded") is False
        and manifest.get("render_accessed") is False
        and manifest.get("filesystem_accessed") is False
        and manifest.get("environment_read") is False
        and manifest.get("configuration_mutation_allowed") is False
        and manifest.get("runtime_wiring_allowed") is False
        and manifest.get("startup_recovery_allowed") is False
        and manifest.get("production_ready") is False
        and manifest.get("live_allowed") is False
        and repr(protected)
        == "ProtectedAuthorityProvisioningManifestV2(<protected>)"
    )
    return {
        "ok": ok,
        "status": (
            "AUTHORITY_PROVISIONING_MANIFEST_HARNESS_V2_PASSED"
            if ok
            else "AUTHORITY_PROVISIONING_MANIFEST_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_MANIFEST_HARNESS_V2_VERSION,
        "manifest_sha256": getattr(protected, "manifest_sha256", None),
        "adapter_count": manifest.get("adapter_count", 0),
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
    "build_authority_provisioning_manifest_context_v2",
    "run_authority_provisioning_manifest_harness_v2",
]
