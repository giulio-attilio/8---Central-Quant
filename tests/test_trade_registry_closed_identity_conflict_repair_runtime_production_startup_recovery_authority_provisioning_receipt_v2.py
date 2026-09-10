from __future__ import annotations

import copy

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2 as receipt_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_harness_v2 as harness_v2


def test_receipt_contract_is_default_off_and_performs_no_reads() -> None:
    result = receipt_v2.build_dormant_authority_provisioning_receipt_contract_v2().issue_offline(
        protected_manifest=None,
        adapter_bundle=None,
        reference_bindings={},
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_RECEIPT_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["environment_read"] is False
    assert result["render_accessed"] is False
    assert result["live_allowed"] is False


def test_synthetic_provisioning_receipt_harness_passes() -> None:
    result = harness_v2.run_authority_provisioning_receipt_harness_v2()

    assert result["ok"] is True
    assert result["reference_binding_count"] == 3
    assert result["synthetic_reference_bindings_only"] is True
    assert result["secret_material_embedded"] is False
    assert result["filesystem_accessed"] is False
    assert result["environment_read"] is False
    assert result["render_accessed"] is False
    assert result["runtime_wiring_allowed"] is False
    assert result["live_allowed"] is False


def test_receipt_rejects_a_different_manifest_instance() -> None:
    values = harness_v2.build_authority_provisioning_receipt_context_v2()
    original = values["protected_manifest"]
    duplicate = type(original)(
        adapter_bundle_object_identity_sha256=(
            original.adapter_bundle_object_identity_sha256
        ),
        manifest=copy.deepcopy(dict(original.manifest)),
        manifest_sha256=original.manifest_sha256,
    )

    result = values["contract"].issue_offline(
        protected_manifest=duplicate,
        adapter_bundle=values["bundle"],
        reference_bindings=values["references"],
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_MANIFEST_INSTANCE_INVALID"
    assert result["protected_receipt"] is None


def test_receipt_rejects_a_recreated_reference_instance() -> None:
    values = harness_v2.build_authority_provisioning_receipt_context_v2()
    references = dict(values["references"])
    name = next(iter(references))
    original = references[name]
    references[name] = receipt_v2.SyntheticAuthorityProvisioningReferenceV2(
        reference_name=original.reference_name,
        reference_role=original.reference_role,
    )

    result = values["contract"].issue_offline(
        protected_manifest=values["protected_manifest"],
        adapter_bundle=values["bundle"],
        reference_bindings=references,
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHORITY_PROVISIONING_REFERENCE_BINDING_INVALID"
    assert result["runtime_wiring_allowed"] is False


def test_receipt_tampering_invalidates_protected_dto() -> None:
    values = harness_v2.build_authority_provisioning_receipt_context_v2()
    original = values["result"]["protected_receipt"]
    tampered_receipt = copy.deepcopy(dict(original.receipt))
    tampered_receipt["production_ready"] = True
    tampered = receipt_v2.ProtectedAuthorityProvisioningReceiptV2(
        manifest_object_identity_sha256=original.manifest_object_identity_sha256,
        adapter_bundle_object_identity_sha256=(
            original.adapter_bundle_object_identity_sha256
        ),
        receipt=tampered_receipt,
        receipt_sha256=original.receipt_sha256,
    )

    assert receipt_v2.protected_authority_provisioning_receipt_valid_v2(
        tampered
    ) is False
