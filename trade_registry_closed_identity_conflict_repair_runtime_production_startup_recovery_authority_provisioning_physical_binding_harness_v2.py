"""In-memory harness for the dormant C3 physical-provisioning binding."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_contract_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_harness_v2 as authenticated_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHORITY-PROVISIONING-PHYSICAL-BINDING-"
    "HARNESS-V2"
)


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def build_authority_provisioning_physical_binding_context_v2() -> dict[str, Any]:
    authenticated_context = (
        authenticated_harness_v2.build_authenticated_provisioning_receipt_verifier_context_v2()
    )
    receipt_context = authenticated_context["receipt_context"]
    protected_manifest = receipt_context["protected_manifest"]
    provisioning_receipt = authenticated_context["protected_receipt"]
    authenticated_verification = authenticated_context["result"][
        "protected_verification"
    ]
    adapter_bundle = receipt_context["bundle"]
    physical_evidence = (
        physical_v2.build_synthetic_physical_authority_provisioning_evidence_v2(
            protected_manifest=protected_manifest,
            provisioning_receipt=provisioning_receipt,
            authenticated_verification=authenticated_verification,
        )
    )
    contract = physical_v2.DormantAuthorityProvisioningPhysicalBindingContractV2(
        physical_v2.DormantAuthorityProvisioningPhysicalBindingConfigV2(
            enabled=True,
            scope_attestation=physical_v2.OFFLINE_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_SCOPE_V2,
            expected_manifest_object_identity_sha256=_object_identity(
                protected_manifest
            ),
            expected_receipt_object_identity_sha256=_object_identity(
                provisioning_receipt
            ),
            expected_authenticated_verification_object_identity_sha256=_object_identity(
                authenticated_verification
            ),
            expected_adapter_bundle_object_identity_sha256=_object_identity(
                adapter_bundle
            ),
            expected_physical_evidence_object_identity_sha256=_object_identity(
                physical_evidence
            ),
        )
    )
    result = contract.bind_offline(
        protected_manifest=protected_manifest,
        provisioning_receipt=provisioning_receipt,
        authenticated_verification=authenticated_verification,
        adapter_bundle=adapter_bundle,
        physical_evidence=physical_evidence,
    )
    return {
        "authenticated_context": authenticated_context,
        "protected_manifest": protected_manifest,
        "provisioning_receipt": provisioning_receipt,
        "authenticated_verification": authenticated_verification,
        "adapter_bundle": adapter_bundle,
        "physical_evidence": physical_evidence,
        "contract": contract,
        "result": result,
    }


def run_authority_provisioning_physical_binding_harness_v2() -> dict[str, Any]:
    values = build_authority_provisioning_physical_binding_context_v2()
    result = values["result"]
    protected = result.get("protected_binding")
    binding = dict(protected.binding) if protected is not None else {}
    ok = bool(
        result.get("ok") is True
        and physical_v2.protected_authority_provisioning_physical_binding_valid_v2(
            protected
        )
        and binding.get("exact_instance_chain_verified") is True
        and binding.get("cross_hash_chain_verified") is True
        and binding.get("authenticated_authority_verified") is True
        and binding.get("revocation_checked") is True
        and binding.get("physical_binding_planned") is True
        and binding.get("durability_requirements_preserved") is True
        and binding.get("synthetic_only") is True
        and binding.get("physical_paths_resolved") is False
        and binding.get("production_resources_observed") is False
        and binding.get("filesystem_accessed") is False
        and binding.get("network_accessed") is False
        and binding.get("render_accessed") is False
        and binding.get("production_ready") is False
        and binding.get("live_allowed") is False
        and repr(protected)
        == "ProtectedAuthorityProvisioningPhysicalBindingV2(<protected>)"
    )
    return {
        "ok": ok,
        "status": (
            "AUTHORITY_PROVISIONING_PHYSICAL_BINDING_HARNESS_V2_PASSED"
            if ok
            else "AUTHORITY_PROVISIONING_PHYSICAL_BINDING_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHORITY_PROVISIONING_PHYSICAL_BINDING_HARNESS_V2_VERSION,
        "binding_sha256": getattr(protected, "binding_sha256", None),
        "exact_instance_chain_verified": binding.get(
            "exact_instance_chain_verified", False
        ),
        "cross_hash_chain_verified": binding.get(
            "cross_hash_chain_verified", False
        ),
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
    }


__all__ = [
    "build_authority_provisioning_physical_binding_context_v2",
    "run_authority_provisioning_physical_binding_harness_v2",
]
