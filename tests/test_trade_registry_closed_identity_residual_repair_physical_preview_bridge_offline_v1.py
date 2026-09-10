from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

import trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_contract_v1 as contract
import trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_harness_v1 as harness
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1 as physical


def _temporary_root():
    return tempfile.TemporaryDirectory(
        prefix=physical.SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1
    )


def _ready_fixture(root: Path, *, clock_values: list[int] | None = None):
    fixture = harness.build_synthetic_physical_preview_bridge_fixture_v1(
        root, clock_values=clock_values
    )
    harness.write_synthetic_bridge_snapshot_v1(fixture)
    return fixture


def test_physical_preview_bridge_harness_passes() -> None:
    result = harness.run_physical_preview_bridge_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())


def test_bridge_is_default_off_before_clock_or_physical_read() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(Path(temporary_name))
        controller = contract.DormantResidualPhysicalPreviewBridgeV1(
            physical_port=fixture["physical_port"],
            physical_authority=fixture["authority"],
            preview_controller=fixture["preview_fixture"]["controller"],
            caps=fixture["preview_fixture"]["caps"],
            clock=fixture["clock"],
        )

        result = controller.preview_from_physical_offline()

        assert result["reasons"] == ["PHYSICAL_PREVIEW_BRIDGE_DEFAULT_OFF"]
        assert result["physical_port_called"] is False
        assert fixture["clock"].calls == 0
        assert not hasattr(controller, "apply")


def test_full_chain_preserves_file_and_returns_sanitized_preview() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(Path(temporary_name))
        raw_before = fixture["target"].read_bytes()

        result = fixture["controller"].preview_from_physical_offline()
        serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))

        assert result["ok"] is True
        assert result["filesystem_accessed"] is True
        assert result["real_registry_accessed"] is False
        assert fixture["target"].read_bytes() == raw_before
        assert result["preview"]["summary"]["residual_record_count"] == 43
        assert result["preview"]["summary"]["quarantined_record_count"] == 32
        assert result["preview"]["repair_ready"] is False
        assert "candidate_registry" not in serialized
        assert "registry_snapshot" not in serialized
        assert "SYNTHETIC:PREDATOR:01" not in serialized
        assert str(fixture["target"]) not in serialized


def test_missing_physical_source_fails_before_preview() -> None:
    with _temporary_root() as temporary_name:
        fixture = harness.build_synthetic_physical_preview_bridge_fixture_v1(
            Path(temporary_name)
        )

        result = fixture["controller"].preview_from_physical_offline()

        assert result["reasons"] == ["PHYSICAL_OBSERVATION_UNAVAILABLE"]
        assert result["physical_reasons"] == ["REGISTRY_SOURCE_MISSING"]
        assert result["preview_called"] is False
        assert result["preview"] is None


def test_tampered_physical_result_fails_closed_without_preview() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(Path(temporary_name))
        original = fixture["physical_port"].read_snapshot_offline

        def tampered_result():
            value = original()
            value["real_registry_accessed"] = True
            return value

        fixture["physical_port"].read_snapshot_offline = tampered_result
        result = fixture["controller"].preview_from_physical_offline()

        assert result["reasons"] == ["PHYSICAL_RESULT_UNSAFE"]
        assert result["preview_called"] is False
        assert result["preview"] is None


def test_unsafe_preview_response_is_sanitized_and_rejected() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(Path(temporary_name))
        fixture["preview_fixture"]["controller"].preview_offline = lambda *_args, **_kwargs: {
            "ok": True,
            "candidate_registry": {"trade_id": "SHOULD_NOT_LEAK"},
        }

        result = fixture["controller"].preview_from_physical_offline()

        assert result["reasons"] == ["PROTECTED_PREVIEW_RESPONSE_UNSAFE"]
        assert result["preview"] is None
        assert "SHOULD_NOT_LEAK" not in json.dumps(result, sort_keys=True)


def test_bridge_deadline_exceeded_discards_preview() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(
            Path(temporary_name),
            clock_values=[40_000, 40_001, 40_002, 40_003, 40_180],
        )

        result = fixture["controller"].preview_from_physical_offline()

        assert result["reasons"] == ["PHYSICAL_PREVIEW_BRIDGE_DEADLINE_EXCEEDED"]
        assert result["preview_called"] is True
        assert result["preview"] is None
        assert result["write_executed"] is False


def test_wrong_contract_or_source_binding_fails_closed() -> None:
    with _temporary_root() as temporary_name:
        fixture = _ready_fixture(Path(temporary_name))
        config = contract.DormantPhysicalPreviewBridgeConfigV1(
            enabled=True,
            scope_attestation=contract.OFFLINE_PHYSICAL_PREVIEW_BRIDGE_SCOPE_ATTESTATION_V1,
            expected_physical_contract_sha256=physical.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256,
            expected_preview_contract_sha256=fixture["preview_fixture"]["controller"]._config.expected_planner_contract_sha256,
            expected_reader_instance_binding_sha256="0" * 64,
            expected_source_path_binding_sha256=fixture[
                "source_path_binding_sha256"
            ],
        )
        controller = contract.DormantResidualPhysicalPreviewBridgeV1(
            config,
            physical_port=fixture["physical_port"],
            physical_authority=fixture["authority"],
            preview_controller=fixture["preview_fixture"]["controller"],
            caps=fixture["preview_fixture"]["caps"],
            clock=fixture["clock"],
        )

        result = controller.preview_from_physical_offline()

        assert result["reasons"] == ["COMPOSED_CONTRACT_BINDING_MISMATCH"]
        assert result["physical_port_called"] is False


def test_bridge_config_caps_are_strict() -> None:
    with pytest.raises(ValueError):
        contract.DormantPhysicalPreviewBridgeConfigV1(
            maximum_operation_seconds=301
        )
    with pytest.raises(ValueError):
        contract.DormantPhysicalPreviewBridgeConfigV1(
            maximum_document_bytes=16_000_001
        )
