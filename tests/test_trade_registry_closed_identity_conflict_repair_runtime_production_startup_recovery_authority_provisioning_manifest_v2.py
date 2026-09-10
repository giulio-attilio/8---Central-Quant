from __future__ import annotations

import copy

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as adapters_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2 as manifest_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_harness_v2 as harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


def _enabled_contract(bundle):
    return manifest_v2.DormantAuthorityProvisioningManifestContractV2(
        manifest_v2.DormantAuthorityProvisioningManifestConfigV2(
            enabled=True,
            scope_attestation=manifest_v2.OFFLINE_AUTHORITY_PROVISIONING_MANIFEST_SCOPE_ATTESTATION_V2,
            expected_adapter_bundle_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    bundle
                )
            ),
        )
    )


def test_manifest_contract_is_default_off_and_performs_no_reads() -> None:
    result = manifest_v2.build_dormant_authority_provisioning_manifest_contract_v2().define_offline(
        adapter_bundle=None,
        key_provider_reference_name="C3_ROOT_AUTHORITY_KEY_PROVIDER_REF",
        transaction_recovery_port_reference_name="C3_TRANSACTION_RECOVERY_PORT_REF",
        resolved_recovery_port_reference_name="C3_RESOLVED_RECOVERY_PORT_REF",
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_MANIFEST_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["environment_read"] is False
    assert result["render_accessed"] is False
    assert result["live_allowed"] is False


def test_secret_free_provisioning_manifest_harness_passes() -> None:
    result = harness_v2.run_authority_provisioning_manifest_harness_v2()

    assert result["ok"] is True
    assert result["adapter_count"] == 4
    assert result["secret_material_embedded"] is False
    assert result["filesystem_accessed"] is False
    assert result["environment_read"] is False
    assert result["render_accessed"] is False
    assert result["runtime_wiring_allowed"] is False
    assert result["live_allowed"] is False


def test_literal_secret_value_cannot_be_used_as_reference_name() -> None:
    bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()
    result = _enabled_contract(bundle).define_offline(
        adapter_bundle=bundle,
        key_provider_reference_name="a-real-secret-value",
        transaction_recovery_port_reference_name="C3_TRANSACTION_RECOVERY_PORT_REF",
        resolved_recovery_port_reference_name="C3_RESOLVED_RECOVERY_PORT_REF",
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_REFERENCE_NAME_INVALID"
    assert result["protected_manifest"] is None
    assert result["secret_material_embedded"] is False


def test_manifest_tampering_invalidates_protected_dto() -> None:
    values = harness_v2.build_authority_provisioning_manifest_context_v2()
    original = values["result"]["protected_manifest"]
    tampered_manifest = copy.deepcopy(dict(original.manifest))
    tampered_manifest["live_allowed"] = True
    tampered = manifest_v2.ProtectedAuthorityProvisioningManifestV2(
        adapter_bundle_object_identity_sha256=(
            original.adapter_bundle_object_identity_sha256
        ),
        manifest=tampered_manifest,
        manifest_sha256=original.manifest_sha256,
    )

    assert manifest_v2.protected_authority_provisioning_manifest_valid_v2(
        tampered
    ) is False


def test_manifest_is_bound_to_exact_adapter_bundle_instance() -> None:
    expected_bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()
    other_bundle = adapters_v2.build_dormant_authenticated_persistent_authority_production_adapters_v2()
    result = _enabled_contract(expected_bundle).define_offline(
        adapter_bundle=other_bundle,
        key_provider_reference_name="C3_ROOT_AUTHORITY_KEY_PROVIDER_REF",
        transaction_recovery_port_reference_name="C3_TRANSACTION_RECOVERY_PORT_REF",
        resolved_recovery_port_reference_name="C3_RESOLVED_RECOVERY_PORT_REF",
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_ADAPTER_BUNDLE_INVALID"
    assert result["runtime_wiring_allowed"] is False
    assert result["live_allowed"] is False
