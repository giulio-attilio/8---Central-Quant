from __future__ import annotations

import copy

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_contract_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_harness_v2 as harness_v2


def test_physical_binding_contract_is_default_off() -> None:
    result = physical_v2.build_dormant_authority_provisioning_physical_binding_contract_v2().bind_offline(
        protected_manifest=None,
        provisioning_receipt=None,
        authenticated_verification=None,
        adapter_bundle=None,
        physical_evidence=None,
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_PHYSICAL_BINDING_DEFAULT_OFF"
    assert result["physical_paths_resolved"] is False
    assert result["filesystem_accessed"] is False
    assert result["live_allowed"] is False


def test_physical_binding_harness_passes() -> None:
    result = harness_v2.run_authority_provisioning_physical_binding_harness_v2()

    assert result["ok"] is True
    assert result["exact_instance_chain_verified"] is True
    assert result["cross_hash_chain_verified"] is True
    assert result["synthetic_only"] is True
    assert result["physical_paths_resolved"] is False
    assert result["production_resources_observed"] is False
    assert result["filesystem_accessed"] is False
    assert result["network_accessed"] is False
    assert result["live_allowed"] is False


def test_recreated_physical_evidence_instance_is_rejected() -> None:
    values = harness_v2.build_authority_provisioning_physical_binding_context_v2()
    original = values["physical_evidence"]
    duplicate = physical_v2.ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2(
        evidence=copy.deepcopy(dict(original.evidence)),
        evidence_sha256=original.evidence_sha256,
    )

    result = values["contract"].bind_offline(
        protected_manifest=values["protected_manifest"],
        provisioning_receipt=values["provisioning_receipt"],
        authenticated_verification=values["authenticated_verification"],
        adapter_bundle=values["adapter_bundle"],
        physical_evidence=duplicate,
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_EXACT_INSTANCE_CHAIN_INVALID"
    assert result["production_ready"] is False


def test_tampered_physical_evidence_is_rejected() -> None:
    values = harness_v2.build_authority_provisioning_physical_binding_context_v2()
    original = values["physical_evidence"]
    tampered_value = copy.deepcopy(dict(original.evidence))
    tampered_value["production_resources_observed"] = True
    tampered = physical_v2.ProtectedSyntheticPhysicalAuthorityProvisioningEvidenceV2(
        evidence=tampered_value,
        evidence_sha256=original.evidence_sha256,
    )

    assert physical_v2.protected_synthetic_physical_authority_provisioning_evidence_valid_v2(
        tampered
    ) is False


def test_different_adapter_bundle_is_rejected() -> None:
    values = harness_v2.build_authority_provisioning_physical_binding_context_v2()
    other_bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()

    result = values["contract"].bind_offline(
        protected_manifest=values["protected_manifest"],
        provisioning_receipt=values["provisioning_receipt"],
        authenticated_verification=values["authenticated_verification"],
        adapter_bundle=other_bundle,
        physical_evidence=values["physical_evidence"],
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_EXACT_INSTANCE_CHAIN_INVALID"
    assert result["runtime_wiring_allowed"] is False


def test_protected_binding_tampering_is_detected() -> None:
    values = harness_v2.build_authority_provisioning_physical_binding_context_v2()
    original = values["result"]["protected_binding"]
    tampered_value = copy.deepcopy(dict(original.binding))
    tampered_value["live_allowed"] = True
    tampered = physical_v2.ProtectedAuthorityProvisioningPhysicalBindingV2(
        binding=tampered_value,
        binding_sha256=original.binding_sha256,
    )

    assert physical_v2.protected_authority_provisioning_physical_binding_valid_v2(
        tampered
    ) is False
