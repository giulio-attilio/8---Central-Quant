"""Temporary-file harness for the dormant physical read-only snapshot port."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_offline_harness_v1 as residual_harness
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1 as physical


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PHYSICAL-READ-ONLY-SNAPSHOT-PORT-OFFLINE-HARNESS-V1"
)
_SYNTHETIC_PHYSICAL_AUTHORITY_KEY_V1 = (
    b"C3 synthetic physical read observation authority key v1"
)


class SyntheticPhysicalReadClockV1:
    def __init__(self, values: list[int] | None = None) -> None:
        self.values = list(values or [30_000, 30_001])
        self.calls = 0

    def __call__(self) -> int:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


def build_synthetic_physical_read_port_v1(
    temporary_root: Path,
    *,
    clock_values: list[int] | None = None,
    maximum_document_bytes: int = 8_000_000,
) -> tuple[
    physical.DormantPhysicalReadOnlySnapshotPortV1,
    physical.ProtectedSyntheticPhysicalReadAuthorityV1,
    SyntheticPhysicalReadClockV1,
    Path,
]:
    target = temporary_root / physical.SYNTHETIC_REGISTRY_FILENAME_V1
    authority = physical.ProtectedSyntheticPhysicalReadAuthorityV1(
        _SYNTHETIC_PHYSICAL_AUTHORITY_KEY_V1
    )
    clock = SyntheticPhysicalReadClockV1(clock_values)
    reader_binding = residual.stable_sha256_v1("synthetic-physical-reader-v1")
    port = physical.DormantPhysicalReadOnlySnapshotPortV1(
        physical.DormantPhysicalReadOnlySnapshotPortConfigV1(
            enabled=True,
            scope_attestation=physical.OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1,
            temporary_root=temporary_root,
            expected_reader_instance_binding_sha256=reader_binding,
            expected_source_path_binding_sha256=physical.physical_source_path_binding_sha256_v1(
                target
            ),
            maximum_operation_seconds=120,
            maximum_document_bytes=maximum_document_bytes,
        ),
        target_path=target,
        authority=authority,
        clock=clock,
    )
    return port, authority, clock, target


def run_physical_read_only_snapshot_port_offline_harness_v1() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(
        prefix=physical.SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1
    ) as temporary_name:
        temporary_root = Path(temporary_name)
        port, authority, clock, target = build_synthetic_physical_read_port_v1(
            temporary_root
        )
        snapshot = residual_harness.build_synthetic_residual_matrix_v1()
        raw = json.dumps(
            snapshot,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        target.write_bytes(raw)
        before_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        result = port.read_snapshot_offline()
        after_sha = hashlib.sha256(target.read_bytes()).hexdigest()
        observation = result.get("observation")
        receipt = result.get("observation_receipt") or {}
        result_repr = repr(result)
        checks = {
            "single_bounded_read": result.get("read_count") == 1,
            "filesystem_access_truthful": result.get("filesystem_accessed") is True,
            "real_registry_never_accessed": result.get("real_registry_accessed") is False,
            "source_file_unchanged": before_sha == after_sha,
            "raw_bytes_bound": receipt.get("raw_document_sha256") == before_sha,
            "snapshot_bound": receipt.get("snapshot_sha256")
            == residual.stable_sha256_v1(snapshot),
            "stable_identity_verified": result.get(
                "stable_file_identity_verified"
            )
            is True,
            "observation_valid": physical.protected_synthetic_physical_read_only_observation_valid_v1(
                observation,
                authority,
                now_epoch=30_001,
            ),
            "observation_repr_protected": repr(observation)
            == "ProtectedSyntheticPhysicalReadOnlyObservationV1(<protected>)",
            "authority_repr_protected": repr(authority)
            == "ProtectedSyntheticPhysicalReadAuthorityV1(<protected>)",
            "raw_path_not_public": str(target) not in result_repr,
            "trade_identity_not_public": "SYNTHETIC:PREDATOR:01" not in result_repr,
            "server_clock_used_twice": clock.calls == 2,
            "not_runtime_integrated": result.get("runtime_integrated") is False,
            "not_route_integrated": result.get("route_integrated") is False,
            "no_write": result.get("write_executed") is False,
            "no_network": result.get("network_accessed") is False,
            "no_broker": result.get("broker_called") is False,
            "no_order": result.get("order_sent") is False,
        }
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_VERSION,
            "ok": bool(result.get("ok") and all(checks.values())),
            "checks": checks,
            "receipt": receipt,
        }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_VERSION,
            "source": "TEMPORARY_SYNTHETIC_JSON_FILE",
            "read_mode": "BOUNDED_BINARY_READ_ONLY",
            "real_registry_accessed": False,
            "write_surface": False,
        }
    )
)


__all__ = [
    "SyntheticPhysicalReadClockV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_physical_read_port_v1",
    "run_physical_read_only_snapshot_port_offline_harness_v1",
]
