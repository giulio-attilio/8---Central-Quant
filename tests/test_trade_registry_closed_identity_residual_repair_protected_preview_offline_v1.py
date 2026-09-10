from __future__ import annotations

import copy
import json

import pytest

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_protected_preview_offline_contract_v1 as contract
import trade_registry_closed_identity_residual_repair_protected_preview_offline_harness_v1 as harness


def _run_fixture():
    fixture = harness.build_synthetic_protected_preview_fixture_v1()
    result = fixture["controller"].preview_offline(
        fixture["request"],
        now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
    )
    return fixture, result


def test_protected_preview_harness_passes_all_checks() -> None:
    result = harness.run_protected_residual_preview_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())


def test_controller_is_default_off_and_has_no_apply_surface() -> None:
    fixture = harness.build_synthetic_protected_preview_fixture_v1()
    controller = contract.DormantProtectedResidualPreviewV1(
        authority=fixture["authority"]
    )

    result = controller.preview_offline(
        fixture["request"],
        now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
    )

    assert result["ok"] is False
    assert result["reasons"] == ["PREVIEW_DEFAULT_OFF"]
    assert not hasattr(controller, "apply")
    assert result["write_executed"] is False
    assert result["runtime_activation_allowed"] is False


def test_request_and_authority_repr_are_protected() -> None:
    fixture = harness.build_synthetic_protected_preview_fixture_v1()

    assert repr(fixture["request"]) == "ProtectedResidualPreviewRequestV1(<protected>)"
    assert repr(fixture["authority"]) == (
        "ProtectedSyntheticResidualPreviewAuthorityV1(<protected>)"
    )
    assert "SYNTHETIC:PREDATOR:01" not in repr(fixture["request"])


def test_public_preview_excludes_raw_snapshot_candidate_and_trade_values() -> None:
    _fixture, result = _run_fixture()
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))

    assert result["ok"] is True
    assert result["status"] == "PROTECTED_RESIDUAL_PREVIEW_PARTIAL_QUARANTINE"
    assert "candidate_registry" not in serialized
    assert "registry_snapshot" not in serialized
    assert "SYNTHETIC:PREDATOR:01" not in serialized
    assert result["summary"]["residual_record_count"] == 43
    assert result["summary"]["quarantined_record_count"] == 32
    assert result["repair_ready"] is False


def test_receipt_is_authenticated_expiring_and_tamper_evident() -> None:
    fixture, result = _run_fixture()
    receipt = result["preview_receipt"]
    now = harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1

    assert contract.protected_residual_preview_receipt_valid_v1(
        receipt, fixture["authority"], now_epoch=now
    )
    assert contract.protected_residual_preview_receipt_valid_v1(
        receipt, fixture["authority"], now_epoch=now + 60
    )
    assert not contract.protected_residual_preview_receipt_valid_v1(
        receipt, fixture["authority"], now_epoch=now - 1
    )
    assert not contract.protected_residual_preview_receipt_valid_v1(
        receipt, fixture["authority"], now_epoch=now + 61
    )

    tampered = copy.deepcopy(receipt)
    tampered["summary_sha256"] = "0" * 64
    assert not contract.protected_residual_preview_receipt_valid_v1(
        tampered, fixture["authority"], now_epoch=now
    )
    different_authority = contract.ProtectedSyntheticResidualPreviewAuthorityV1(
        b"different synthetic residual preview authority key"
    )
    assert not contract.protected_residual_preview_receipt_valid_v1(
        receipt, different_authority, now_epoch=now
    )


def test_snapshot_hash_mismatch_fails_closed_without_public_snapshot() -> None:
    fixture = harness.build_synthetic_protected_preview_fixture_v1()
    request = contract.ProtectedResidualPreviewRequestV1(
        registry_snapshot=fixture["snapshot"],
        expected_snapshot_sha256="0" * 64,
        request_nonce_sha256=fixture["request"].request_nonce_sha256,
        requested_at_epoch=fixture["request"].requested_at_epoch,
        deadline_epoch=fixture["request"].deadline_epoch,
        caps=fixture["caps"],
    )

    result = fixture["controller"].preview_offline(
        request, now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1
    )

    assert result["ok"] is False
    assert result["reasons"] == ["RESIDUAL_REPAIR_PLAN_BLOCKED"]
    assert result["planner_reasons"] == ["SOURCE_SNAPSHOT_SHA256_MISMATCH"]
    assert "candidate_registry" not in result


def test_expired_or_overlong_deadline_fails_before_planning() -> None:
    fixture = harness.build_synthetic_protected_preview_fixture_v1()
    request = contract.ProtectedResidualPreviewRequestV1(
        registry_snapshot=fixture["snapshot"],
        expected_snapshot_sha256=fixture["request"].expected_snapshot_sha256,
        request_nonce_sha256=fixture["request"].request_nonce_sha256,
        requested_at_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1,
        deadline_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1 + 121,
        caps=fixture["caps"],
    )

    result = fixture["controller"].preview_offline(
        request, now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1
    )

    assert result["ok"] is False
    assert result["reasons"] == ["REQUEST_DEADLINE_INVALID_OR_EXPIRED"]
    assert result["preview_receipt"] is None


def test_wrong_contract_binding_and_non_synthetic_source_fail_closed() -> None:
    fixture = harness.build_synthetic_protected_preview_fixture_v1()
    wrong_binding = contract.DormantProtectedResidualPreviewV1(
        contract.DormantProtectedResidualPreviewConfigV1(
            enabled=True,
            scope_attestation=contract.OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1,
            expected_planner_contract_sha256="0" * 64,
        ),
        authority=fixture["authority"],
    )
    mismatch = wrong_binding.preview_offline(
        fixture["request"], now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1
    )
    assert mismatch["reasons"] == ["PLANNER_CONTRACT_BINDING_MISMATCH"]

    real_source = contract.ProtectedResidualPreviewRequestV1(
        registry_snapshot=fixture["snapshot"],
        expected_snapshot_sha256=fixture["request"].expected_snapshot_sha256,
        request_nonce_sha256=fixture["request"].request_nonce_sha256,
        requested_at_epoch=fixture["request"].requested_at_epoch,
        deadline_epoch=fixture["request"].deadline_epoch,
        caps=fixture["caps"],
        source_attestation="REAL_REGISTRY",
        synthetic_only=False,
    )
    rejected = fixture["controller"].preview_offline(
        real_source, now_epoch=harness.DEFAULT_SYNTHETIC_NOW_EPOCH_V1
    )
    assert rejected["reasons"] == ["SYNTHETIC_SOURCE_ATTESTATION_REQUIRED"]


def test_authority_and_config_caps_validate_fail_closed() -> None:
    with pytest.raises(ValueError):
        contract.ProtectedSyntheticResidualPreviewAuthorityV1(b"too-short")
    with pytest.raises(ValueError):
        contract.DormantProtectedResidualPreviewConfigV1(receipt_ttl_seconds=301)
    with pytest.raises(ValueError):
        contract.DormantProtectedResidualPreviewConfigV1(maximum_deadline_seconds=0)


def test_contract_hash_binds_exact_bounded_residual_planner() -> None:
    _fixture, result = _run_fixture()
    receipt = result["preview_receipt"]

    assert receipt["planner_contract_version"] == (
        residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION
    )
    assert receipt["planner_contract_sha256"] == (
        residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256
    )
    assert receipt["apply_allowed"] is False
    assert receipt["runtime_activation_allowed"] is False
    assert receipt["repair_ready"] is False
