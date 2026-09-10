from __future__ import annotations

import copy
import json

import pytest

import trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_contract_v1 as contract
import trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_harness_v1 as harness


def test_runtime_read_only_adapter_harness_passes() -> None:
    result = harness.run_runtime_read_only_preview_adapter_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())


def test_adapter_is_default_off_before_clock_or_read_port() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    controller = contract.DormantResidualRuntimeReadOnlyPreviewAdapterV1(
        read_port=fixture["read_port"],
        read_authority=fixture["read_authority"],
        preview_controller=fixture["preview_fixture"]["controller"],
        caps=fixture["preview_fixture"]["caps"],
        clock=fixture["clock"],
    )

    result = controller.preview_read_only_offline()

    assert result["reasons"] == ["ADAPTER_DEFAULT_OFF"]
    assert fixture["read_port"].calls == 0
    assert fixture["clock"].calls == 0
    assert not hasattr(controller, "apply")


def test_authenticated_observation_and_protected_repr() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    observation = fixture["read_port"](20_120)

    assert repr(observation) == (
        "ProtectedSyntheticReadOnlyRegistryObservationV1(<protected>)"
    )
    assert repr(fixture["read_authority"]) == (
        "ProtectedSyntheticReadObservationAuthorityV1(<protected>)"
    )
    assert contract.protected_synthetic_read_only_observation_valid_v1(
        observation,
        fixture["read_authority"],
        expected_deadline_epoch=20_120,
        now_epoch=20_001,
    )


def test_adapter_calls_one_read_and_returns_only_sanitized_preview() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()

    result = fixture["controller"].preview_read_only_offline()
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))

    assert result["ok"] is True
    assert fixture["read_port"].calls == 1
    assert result["preview"]["summary"]["residual_record_count"] == 43
    assert result["preview"]["repair_ready"] is False
    assert "candidate_registry" not in serialized
    assert "registry_snapshot" not in serialized
    assert "SYNTHETIC:PREDATOR:01" not in serialized
    assert result["filesystem_accessed"] is False
    assert result["real_registry_accessed"] is False


def test_missing_source_fails_closed_before_preview() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1(
        source_exists=False
    )

    result = fixture["controller"].preview_read_only_offline()

    assert result["ok"] is False
    assert result["reasons"] == ["REGISTRY_SOURCE_MISSING"]
    assert result["read_port_called"] is True
    assert result["preview_called"] is False
    assert result["preview"] is None


def test_tampered_observation_fails_closed_before_preview() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1(
        tamper_receipt=True
    )

    result = fixture["controller"].preview_read_only_offline()

    assert result["reasons"] == ["READ_OBSERVATION_INVALID"]
    assert result["preview_called"] is False


def test_deadline_exceeded_after_preview_discards_preview() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1(
        clock_values=[20_000, 20_001, 20_120]
    )

    result = fixture["controller"].preview_read_only_offline()

    assert result["ok"] is False
    assert result["reasons"] == ["ADAPTER_DEADLINE_EXCEEDED"]
    assert result["preview_called"] is True
    assert result["preview"] is None
    assert result["write_executed"] is False


def test_wrong_reader_or_path_binding_fails_closed() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    bad_config = contract.DormantRuntimeReadOnlyPreviewAdapterConfigV1(
        enabled=True,
        scope_attestation=contract.OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1,
        expected_reader_instance_binding_sha256="0" * 64,
        expected_source_path_binding_sha256=fixture["source_path_binding_sha256"],
        expected_preview_contract_sha256=contract.preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
    )
    controller = contract.DormantResidualRuntimeReadOnlyPreviewAdapterV1(
        bad_config,
        read_port=fixture["read_port"],
        read_authority=fixture["read_authority"],
        preview_controller=fixture["preview_fixture"]["controller"],
        caps=fixture["preview_fixture"]["caps"],
        clock=fixture["clock"],
    )

    result = controller.preview_read_only_offline()

    assert result["reasons"] == ["READ_SOURCE_BINDING_MISMATCH"]
    assert result["preview_called"] is False


def test_document_budget_and_config_hard_caps_fail_closed() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    small_budget = contract.DormantRuntimeReadOnlyPreviewAdapterConfigV1(
        enabled=True,
        scope_attestation=contract.OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1,
        expected_reader_instance_binding_sha256=fixture["reader_binding_sha256"],
        expected_source_path_binding_sha256=fixture["source_path_binding_sha256"],
        expected_preview_contract_sha256=contract.preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
        maximum_document_bytes=1,
    )
    controller = contract.DormantResidualRuntimeReadOnlyPreviewAdapterV1(
        small_budget,
        read_port=fixture["read_port"],
        read_authority=fixture["read_authority"],
        preview_controller=fixture["preview_fixture"]["controller"],
        caps=fixture["preview_fixture"]["caps"],
        clock=fixture["clock"],
    )

    result = controller.preview_read_only_offline()

    assert result["reasons"] == ["READ_DOCUMENT_BUDGET_EXCEEDED"]
    assert result["preview_called"] is False
    with pytest.raises(ValueError):
        contract.DormantRuntimeReadOnlyPreviewAdapterConfigV1(
            maximum_operation_seconds=301
        )
    with pytest.raises(ValueError):
        contract.DormantRuntimeReadOnlyPreviewAdapterConfigV1(
            maximum_document_bytes=16_000_001
        )


def test_observation_snapshot_or_receipt_mutation_is_rejected() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    observation = fixture["read_port"](20_120)
    mutated_snapshot = copy.deepcopy(dict(observation.snapshot))
    mutated_snapshot["extension"] = {"must_remain_exact": False}
    mutated = contract.ProtectedSyntheticReadOnlyRegistryObservationV1(
        snapshot=mutated_snapshot,
        receipt=observation.receipt,
    )

    assert not contract.protected_synthetic_read_only_observation_valid_v1(
        mutated,
        fixture["read_authority"],
        expected_deadline_epoch=20_120,
        now_epoch=20_001,
    )


def test_unsafe_or_raising_preview_dependency_fails_closed_without_leak() -> None:
    fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()
    fixture["preview_fixture"]["controller"].preview_offline = lambda *_args, **_kwargs: {
        "ok": True,
        "candidate_registry": fixture["read_port"].snapshot,
    }

    unsafe = fixture["controller"].preview_read_only_offline()

    assert unsafe["reasons"] == ["PROTECTED_PREVIEW_RESPONSE_UNSAFE"]
    assert unsafe["preview"] is None
    assert "candidate_registry" not in json.dumps(unsafe, sort_keys=True)

    raising_fixture = harness.build_synthetic_runtime_read_only_adapter_fixture_v1()

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic preview failure")

    raising_fixture["preview_fixture"]["controller"].preview_offline = explode
    failed = raising_fixture["controller"].preview_read_only_offline()
    assert failed["reasons"] == ["PROTECTED_PREVIEW_FAILED_CLOSED"]
    assert failed["preview_error_type"] == "RuntimeError"
    assert failed["preview"] is None
