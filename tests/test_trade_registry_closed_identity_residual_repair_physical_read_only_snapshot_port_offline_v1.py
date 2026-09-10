from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

import trade_registry_closed_identity_residual_repair_offline_harness_v1 as residual_harness
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1 as contract
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_harness_v1 as harness


def _temporary_root():
    return tempfile.TemporaryDirectory(
        prefix=contract.SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1
    )


def _write_snapshot(target: Path) -> bytes:
    raw = json.dumps(
        residual_harness.build_synthetic_residual_matrix_v1(),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    target.write_bytes(raw)
    return raw


def test_physical_read_only_harness_passes() -> None:
    result = harness.run_physical_read_only_snapshot_port_offline_harness_v1()

    assert result["ok"] is True
    assert all(result["checks"].values())


def test_port_is_default_off_before_path_or_clock_access() -> None:
    authority = contract.ProtectedSyntheticPhysicalReadAuthorityV1(b"a" * 32)
    clock = harness.SyntheticPhysicalReadClockV1()
    port = contract.DormantPhysicalReadOnlySnapshotPortV1(
        target_path="definitely-not-a-real-registry.json",
        authority=authority,
        clock=clock,
    )

    result = port.read_snapshot_offline()

    assert result["reasons"] == ["PHYSICAL_READ_PORT_DEFAULT_OFF"]
    assert result["filesystem_accessed"] is False
    assert clock.calls == 0
    assert not hasattr(port, "apply")


def test_single_read_preserves_file_and_returns_protected_observation() -> None:
    with _temporary_root() as temporary_name:
        root = Path(temporary_name)
        port, authority, clock, target = harness.build_synthetic_physical_read_port_v1(
            root
        )
        raw = _write_snapshot(target)

        result = port.read_snapshot_offline()
        observation = result["observation"]

        assert result["ok"] is True
        assert result["read_count"] == 1
        assert target.read_bytes() == raw
        assert result["observation_receipt"]["raw_document_sha256"] == hashlib.sha256(
            raw
        ).hexdigest()
        assert contract.protected_synthetic_physical_read_only_observation_valid_v1(
            observation, authority, now_epoch=30_001
        )
        assert "SYNTHETIC:PREDATOR:01" not in repr(result)
        assert str(target) not in repr(result)
        assert clock.calls == 2


def test_missing_source_never_fabricates_empty_registry() -> None:
    with _temporary_root() as temporary_name:
        root = Path(temporary_name)
        port, _authority, _clock, _target = harness.build_synthetic_physical_read_port_v1(
            root
        )

        result = port.read_snapshot_offline()

        assert result["ok"] is False
        assert result["reasons"] == ["REGISTRY_SOURCE_MISSING"]
        assert result["source_exists"] is False
        assert result["read_count"] == 0
        assert result["observation"] is None


def test_invalid_json_and_non_mapping_fail_closed_without_write() -> None:
    for payload, expected in ((b"{", "SOURCE_DOCUMENT_INVALID_JSON"), (b"[]", "SOURCE_DOCUMENT_NOT_MAPPING")):
        with _temporary_root() as temporary_name:
            root = Path(temporary_name)
            port, _authority, _clock, target = harness.build_synthetic_physical_read_port_v1(
                root
            )
            target.write_bytes(payload)

            result = port.read_snapshot_offline()

            assert result["reasons"] == [expected]
            assert target.read_bytes() == payload
            assert result["write_executed"] is False


def test_document_budget_is_enforced_before_read() -> None:
    with _temporary_root() as temporary_name:
        root = Path(temporary_name)
        port, _authority, _clock, target = harness.build_synthetic_physical_read_port_v1(
            root, maximum_document_bytes=10
        )
        target.write_bytes(b"{" + b"x" * 100 + b"}")

        result = port.read_snapshot_offline()

        assert result["reasons"] == ["SOURCE_DOCUMENT_BUDGET_EXCEEDED"]
        assert result["read_count"] == 0


def test_path_outside_dedicated_system_temp_root_is_rejected() -> None:
    with _temporary_root() as temporary_name, _temporary_root() as other_name:
        root = Path(temporary_name)
        other = Path(other_name)
        target = other / contract.SYNTHETIC_REGISTRY_FILENAME_V1
        _write_snapshot(target)
        authority = contract.ProtectedSyntheticPhysicalReadAuthorityV1(b"b" * 32)
        port = contract.DormantPhysicalReadOnlySnapshotPortV1(
            contract.DormantPhysicalReadOnlySnapshotPortConfigV1(
                enabled=True,
                scope_attestation=contract.OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1,
                temporary_root=root,
                expected_reader_instance_binding_sha256="1" * 64,
                expected_source_path_binding_sha256=contract.physical_source_path_binding_sha256_v1(
                    target
                ),
            ),
            target_path=target,
            authority=authority,
            clock=harness.SyntheticPhysicalReadClockV1(),
        )

        result = port.read_snapshot_offline()

        assert result["reasons"] == ["SYNTHETIC_TEMPORARY_PATH_POLICY_FAILED"]
        assert result["read_count"] == 0


def test_deadline_exceeded_discards_observation() -> None:
    with _temporary_root() as temporary_name:
        root = Path(temporary_name)
        port, _authority, _clock, target = harness.build_synthetic_physical_read_port_v1(
            root, clock_values=[30_000, 30_120]
        )
        _write_snapshot(target)

        result = port.read_snapshot_offline()

        assert result["reasons"] == ["PHYSICAL_READ_DEADLINE_EXCEEDED"]
        assert result["read_count"] == 1
        assert result["observation"] is None


def test_tampered_receipt_or_snapshot_is_rejected() -> None:
    with _temporary_root() as temporary_name:
        root = Path(temporary_name)
        port, authority, _clock, target = harness.build_synthetic_physical_read_port_v1(
            root
        )
        _write_snapshot(target)
        result = port.read_snapshot_offline()
        observation = result["observation"]

        tampered_receipt = copy.deepcopy(dict(observation.receipt))
        tampered_receipt["source_generation"] += 1
        tampered = contract.ProtectedSyntheticPhysicalReadOnlyObservationV1(
            snapshot=observation.snapshot,
            receipt=tampered_receipt,
        )
        assert not contract.protected_synthetic_physical_read_only_observation_valid_v1(
            tampered, authority, now_epoch=30_001
        )

        changed_snapshot = copy.deepcopy(dict(observation.snapshot))
        changed_snapshot["extension"] = {"must_remain_exact": False}
        changed = contract.ProtectedSyntheticPhysicalReadOnlyObservationV1(
            snapshot=changed_snapshot,
            receipt=observation.receipt,
        )
        assert not contract.protected_synthetic_physical_read_only_observation_valid_v1(
            changed, authority, now_epoch=30_001
        )


def test_authority_config_and_filename_are_strict() -> None:
    with pytest.raises(ValueError):
        contract.ProtectedSyntheticPhysicalReadAuthorityV1(b"short")
    with pytest.raises(ValueError):
        contract.DormantPhysicalReadOnlySnapshotPortConfigV1(
            maximum_operation_seconds=301
        )
    with pytest.raises(ValueError):
        contract.DormantPhysicalReadOnlySnapshotPortConfigV1(
            maximum_document_bytes=16_000_001
        )
    assert contract.SYNTHETIC_REGISTRY_FILENAME_V1 != "trade_registry.json"
