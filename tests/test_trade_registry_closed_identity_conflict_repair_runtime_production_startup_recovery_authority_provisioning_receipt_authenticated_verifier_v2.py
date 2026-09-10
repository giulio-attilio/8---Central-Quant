from __future__ import annotations

import copy

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2 as verifier_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_harness_v2 as harness_v2


def test_authenticated_receipt_verifier_is_default_off() -> None:
    result = verifier_v2.build_dormant_authenticated_provisioning_receipt_verifier_v2().verify_offline(
        protected_receipt=None,
        candidate_receipt={},
        root_authority_attestation={},
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHENTICATED_PROVISIONING_RECEIPT_VERIFIER_DEFAULT_OFF"
    assert result["filesystem_accessed"] is False
    assert result["network_accessed"] is False
    assert result["live_allowed"] is False


def test_authenticated_receipt_verifier_harness_passes() -> None:
    result = harness_v2.run_authenticated_provisioning_receipt_verifier_harness_v2()

    assert result["ok"] is True
    assert result["authenticated"] is True
    assert result["revocation_checked"] is True
    assert result["synthetic_only"] is True
    assert result["persistent_evidence_observed"] is False
    assert result["production_receipt"] is False
    assert result["filesystem_accessed"] is False
    assert result["network_accessed"] is False
    assert result["live_allowed"] is False


def test_revoked_root_key_fails_closed() -> None:
    values = harness_v2.build_authenticated_provisioning_receipt_verifier_context_v2(
        revoked=True
    )

    assert values["result"]["ok"] is False
    assert values["result"]["reason"] == "ROOT_AUTHORITY_KEY_REVOKED"
    assert values["result"]["authenticated"] is False
    assert values["result"]["production_ready"] is False


def test_candidate_with_invalid_signature_fails_closed() -> None:
    values = harness_v2.build_authenticated_provisioning_receipt_verifier_context_v2()
    candidate = copy.deepcopy(values["candidate"])
    candidate["signature_sha256"] = "f" * 64
    candidate["candidate_sha256"] = (
        verifier_v2.authority_provisioning_receipt_candidate_sha256_v2(candidate)
    )

    result = values["contract"].verify_offline(
        protected_receipt=values["protected_receipt"],
        candidate_receipt=candidate,
        root_authority_attestation=values["root_attestation"],
    )

    assert result["ok"] is False
    assert result["reason"] == "PROVISIONING_RECEIPT_SIGNATURE_INVALID"
    assert result["protected_verification"] is None


def test_recreated_verifier_instance_is_rejected() -> None:
    values = harness_v2.build_authenticated_provisioning_receipt_verifier_context_v2()
    original = values["signature_verifier"]
    replacement = harness_v2.SyntheticInMemoryRootSignatureVerifierV2(
        key_id_sha256=vars(original)["_key_id_sha256"],
        key=vars(original)["_key"],
    )
    contract = verifier_v2.DormantAuthenticatedProvisioningReceiptVerifierV2(
        vars(values["contract"])["_config"],
        signature_verifier=replacement,
        revocation_source=values["revocation_source"],
        clock=lambda: harness_v2.SYNTHETIC_NOW_EPOCH_V2,
    )

    result = contract.verify_offline(
        protected_receipt=values["protected_receipt"],
        candidate_receipt=values["candidate"],
        root_authority_attestation=values["root_attestation"],
    )

    assert result["ok"] is False
    assert result["reason"] == "AUTHENTICATED_PROVISIONING_DEPENDENCY_INSTANCE_INVALID"
    assert result["live_allowed"] is False


def test_verification_dto_tampering_is_detected() -> None:
    values = harness_v2.build_authenticated_provisioning_receipt_verifier_context_v2()
    original = values["result"]["protected_verification"]
    tampered_value = copy.deepcopy(dict(original.verification))
    tampered_value["live_allowed"] = True
    tampered = verifier_v2.ProtectedAuthenticatedProvisioningReceiptVerificationV2(
        protected_receipt_object_identity_sha256=(
            original.protected_receipt_object_identity_sha256
        ),
        root_authority_attestation_sha256=(
            original.root_authority_attestation_sha256
        ),
        candidate_sha256=original.candidate_sha256,
        verification=tampered_value,
        verification_sha256=original.verification_sha256,
    )

    assert verifier_v2.protected_authenticated_provisioning_receipt_verification_valid_v2(
        tampered
    ) is False
