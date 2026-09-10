"""Temporary synthetic harness for the physical-to-preview bridge."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_contract_v1 as bridge
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1 as physical
import trade_registry_closed_identity_residual_repair_protected_preview_offline_harness_v1 as preview_harness


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PHYSICAL-PREVIEW-BRIDGE-OFFLINE-HARNESS-V1"
)
_PHYSICAL_AUTHORITY_KEY_V1 = b"C3 physical preview bridge synthetic authority v1"


class SyntheticBridgeClockV1:
    def __init__(self, values: list[int] | None = None) -> None:
        self.values = list(values or [40_000, 40_001, 40_002, 40_003, 40_004])
        self.calls = 0

    def __call__(self) -> int:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


def build_synthetic_physical_preview_bridge_fixture_v1(
    temporary_root: Path,
    *,
    clock_values: list[int] | None = None,
) -> dict[str, Any]:
    preview_fixture = preview_harness.build_synthetic_protected_preview_fixture_v1()
    clock = SyntheticBridgeClockV1(clock_values)
    authority = physical.ProtectedSyntheticPhysicalReadAuthorityV1(
        _PHYSICAL_AUTHORITY_KEY_V1
    )
    target = temporary_root / physical.SYNTHETIC_REGISTRY_FILENAME_V1
    reader_binding = residual.stable_sha256_v1(
        "synthetic-physical-preview-bridge-reader-v1"
    )
    path_binding = physical.physical_source_path_binding_sha256_v1(target)
    physical_port = physical.DormantPhysicalReadOnlySnapshotPortV1(
        physical.DormantPhysicalReadOnlySnapshotPortConfigV1(
            enabled=True,
            scope_attestation=physical.OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1,
            temporary_root=temporary_root,
            expected_reader_instance_binding_sha256=reader_binding,
            expected_source_path_binding_sha256=path_binding,
            maximum_operation_seconds=120,
            maximum_document_bytes=8_000_000,
        ),
        target_path=target,
        authority=authority,
        clock=clock,
    )
    controller = bridge.DormantResidualPhysicalPreviewBridgeV1(
        bridge.DormantPhysicalPreviewBridgeConfigV1(
            enabled=True,
            scope_attestation=bridge.OFFLINE_PHYSICAL_PREVIEW_BRIDGE_SCOPE_ATTESTATION_V1,
            expected_physical_contract_sha256=physical.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256,
            expected_preview_contract_sha256=preview_harness.preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
            expected_reader_instance_binding_sha256=reader_binding,
            expected_source_path_binding_sha256=path_binding,
            maximum_operation_seconds=180,
            maximum_document_bytes=8_000_000,
        ),
        physical_port=physical_port,
        physical_authority=authority,
        preview_controller=preview_fixture["controller"],
        caps=preview_fixture["caps"],
        clock=clock,
    )
    return {
        "preview_fixture": preview_fixture,
        "clock": clock,
        "authority": authority,
        "target": target,
        "reader_binding_sha256": reader_binding,
        "source_path_binding_sha256": path_binding,
        "physical_port": physical_port,
        "controller": controller,
    }


def write_synthetic_bridge_snapshot_v1(fixture: dict[str, Any]) -> bytes:
    raw = json.dumps(
        fixture["preview_fixture"]["snapshot"],
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    fixture["target"].write_bytes(raw)
    return raw


def run_physical_preview_bridge_offline_harness_v1() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=physical.SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1
    ) as temporary_name:
        fixture = build_synthetic_physical_preview_bridge_fixture_v1(
            Path(temporary_name)
        )
        raw = write_synthetic_bridge_snapshot_v1(fixture)
        before_sha = hashlib.sha256(raw).hexdigest()
        result = fixture["controller"].preview_from_physical_offline()
        after_sha = hashlib.sha256(fixture["target"].read_bytes()).hexdigest()
        serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
        checks = {
            "physical_port_called": result.get("physical_port_called") is True,
            "preview_called": result.get("preview_called") is True,
            "shared_clock_sequence_exact": fixture["clock"].calls == 5,
            "source_file_preserved": before_sha == after_sha,
            "filesystem_access_truthful": result.get("filesystem_accessed") is True,
            "real_registry_never_accessed": result.get("real_registry_accessed") is False,
            "physical_receipt_preserved": result.get(
                "physical_observation_receipt", {}
            ).get("raw_document_sha256")
            == before_sha,
            "preview_source_bound_to_physical_snapshot": result.get("preview", {})
            .get("preview_receipt", {})
            .get("source_snapshot_sha256")
            == result.get("physical_observation_receipt", {}).get(
                "snapshot_sha256"
            ),
            "known_residual_count_exact": result.get("preview", {})
            .get("summary", {})
            .get("residual_record_count")
            == 43,
            "quarantine_not_ready": result.get("preview", {}).get(
                "repair_ready"
            )
            is False,
            "raw_snapshot_not_public": "candidate_registry" not in serialized
            and "registry_snapshot" not in serialized,
            "trade_identity_not_public": "SYNTHETIC:PREDATOR:01" not in serialized,
            "path_not_public": str(fixture["target"]) not in serialized,
            "no_apply_surface": not hasattr(fixture["controller"], "apply"),
            "not_runtime_integrated": result.get("runtime_integrated") is False,
            "not_route_integrated": result.get("route_integrated") is False,
            "no_write": result.get("write_executed") is False,
            "no_network": result.get("network_accessed") is False,
            "no_broker": result.get("broker_called") is False,
            "no_order": result.get("order_sent") is False,
        }
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_VERSION,
            "ok": bool(result.get("ok") and all(checks.values())),
            "checks": checks,
            "bridge_result": result,
        }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_VERSION,
            "chain": "TEMPORARY_PHYSICAL_READ_TO_PROTECTED_PREVIEW",
            "matrix": "43_SYNTHETIC_RESIDUAL_RECORDS",
            "filesystem_access_truthful": True,
            "real_registry_accessed": False,
            "apply_surface": False,
        }
    )
)


__all__ = [
    "SyntheticBridgeClockV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_physical_preview_bridge_fixture_v1",
    "run_physical_preview_bridge_offline_harness_v1",
    "write_synthetic_bridge_snapshot_v1",
]
