"""Synthetic harness for the dormant runtime read-only preview adapter."""

from __future__ import annotations

import copy
import json
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_protected_preview_offline_harness_v1 as preview_harness
import trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_contract_v1 as adapter


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-RUNTIME-READ-ONLY-PREVIEW-ADAPTER-OFFLINE-HARNESS-V1"
)
DEFAULT_SYNTHETIC_START_EPOCH_V1 = 20_000
_SYNTHETIC_READ_AUTHORITY_KEY_V1 = b"C3 synthetic read observation authority key v1"


class SyntheticServerClockV1:
    def __init__(self, values: list[int] | None = None) -> None:
        self.values = list(values or [20_000, 20_001, 20_002])
        self.calls = 0

    def __call__(self) -> int:
        index = min(self.calls, len(self.values) - 1)
        self.calls += 1
        return self.values[index]


class SyntheticReadOnlyRegistryPortV1:
    def __init__(
        self,
        snapshot: dict[str, Any],
        *,
        authority: adapter.ProtectedSyntheticReadObservationAuthorityV1,
        reader_binding_sha256: str,
        source_path_binding_sha256: str,
        source_exists: bool = True,
        tamper_receipt: bool = False,
    ) -> None:
        self.snapshot = copy.deepcopy(snapshot)
        self.authority = authority
        self.reader_binding_sha256 = reader_binding_sha256
        self.source_path_binding_sha256 = source_path_binding_sha256
        self.source_exists = source_exists
        self.tamper_receipt = tamper_receipt
        self.calls = 0
        self.deadlines: list[int] = []

    def __call__(
        self, deadline_epoch: int
    ) -> adapter.ProtectedSyntheticReadOnlyRegistryObservationV1:
        self.calls += 1
        self.deadlines.append(deadline_epoch)
        observation = adapter.build_protected_synthetic_read_only_observation_v1(
            self.snapshot,
            authority=self.authority,
            reader_instance_binding_sha256=self.reader_binding_sha256,
            source_path_binding_sha256=self.source_path_binding_sha256,
            source_generation=7,
            source_exists=self.source_exists,
            read_started_at_epoch=DEFAULT_SYNTHETIC_START_EPOCH_V1,
            read_finished_at_epoch=DEFAULT_SYNTHETIC_START_EPOCH_V1 + 1,
            deadline_epoch=deadline_epoch,
        )
        if not self.tamper_receipt:
            return observation
        tampered = copy.deepcopy(dict(observation.receipt))
        tampered["snapshot_sha256"] = "f" * 64
        return adapter.ProtectedSyntheticReadOnlyRegistryObservationV1(
            snapshot=observation.snapshot,
            receipt=tampered,
        )


def build_synthetic_runtime_read_only_adapter_fixture_v1(
    *,
    source_exists: bool = True,
    tamper_receipt: bool = False,
    clock_values: list[int] | None = None,
) -> dict[str, Any]:
    preview_fixture = preview_harness.build_synthetic_protected_preview_fixture_v1()
    read_authority = adapter.ProtectedSyntheticReadObservationAuthorityV1(
        _SYNTHETIC_READ_AUTHORITY_KEY_V1
    )
    reader_binding = residual.stable_sha256_v1("synthetic-runtime-reader-instance-v1")
    path_binding = residual.stable_sha256_v1("synthetic-registry-path-v1")
    read_port = SyntheticReadOnlyRegistryPortV1(
        preview_fixture["snapshot"],
        authority=read_authority,
        reader_binding_sha256=reader_binding,
        source_path_binding_sha256=path_binding,
        source_exists=source_exists,
        tamper_receipt=tamper_receipt,
    )
    clock = SyntheticServerClockV1(clock_values)
    controller = adapter.DormantResidualRuntimeReadOnlyPreviewAdapterV1(
        adapter.DormantRuntimeReadOnlyPreviewAdapterConfigV1(
            enabled=True,
            scope_attestation=adapter.OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1,
            expected_reader_instance_binding_sha256=reader_binding,
            expected_source_path_binding_sha256=path_binding,
            expected_preview_contract_sha256=preview_harness.preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
            maximum_operation_seconds=120,
            maximum_document_bytes=8_000_000,
        ),
        read_port=read_port,
        read_authority=read_authority,
        preview_controller=preview_fixture["controller"],
        caps=preview_fixture["caps"],
        clock=clock,
    )
    return {
        "preview_fixture": preview_fixture,
        "read_authority": read_authority,
        "reader_binding_sha256": reader_binding,
        "source_path_binding_sha256": path_binding,
        "read_port": read_port,
        "clock": clock,
        "controller": controller,
    }


def run_runtime_read_only_preview_adapter_offline_harness_v1() -> dict[str, Any]:
    fixture = build_synthetic_runtime_read_only_adapter_fixture_v1()
    snapshot_before = copy.deepcopy(fixture["read_port"].snapshot)
    result = fixture["controller"].preview_read_only_offline()
    serialized = json.dumps(result, sort_keys=True, separators=(",", ":"))
    disabled_port = fixture["read_port"]
    disabled_clock = SyntheticServerClockV1()
    disabled = adapter.DormantResidualRuntimeReadOnlyPreviewAdapterV1(
        read_port=disabled_port,
        read_authority=fixture["read_authority"],
        preview_controller=fixture["preview_fixture"]["controller"],
        caps=fixture["preview_fixture"]["caps"],
        clock=disabled_clock,
    ).preview_read_only_offline()
    checks = {
        "single_read_port_call": fixture["read_port"].calls == 1,
        "server_deadline_forwarded": fixture["read_port"].deadlines == [20_120],
        "three_server_clock_reads": fixture["clock"].calls == 3,
        "source_snapshot_unchanged": fixture["read_port"].snapshot == snapshot_before,
        "preview_called_once_by_composition": result.get("preview_called") is True,
        "known_residual_count_exact": result.get("preview", {})
        .get("summary", {})
        .get("residual_record_count")
        == 43,
        "quarantine_not_ready": result.get("preview", {}).get("repair_ready") is False,
        "read_receipt_bound": result.get("observation_receipt", {}).get(
            "reader_instance_binding_sha256"
        )
        == fixture["reader_binding_sha256"],
        "raw_snapshot_not_public": "candidate_registry" not in serialized
        and "registry_snapshot" not in serialized,
        "trade_identity_not_public": "SYNTHETIC:PREDATOR:01" not in serialized,
        "default_off_does_not_read": disabled.get("reasons") == ["ADAPTER_DEFAULT_OFF"]
        and disabled_port.calls == 1
        and disabled_clock.calls == 0,
        "no_apply_surface": not hasattr(fixture["controller"], "apply"),
        "not_runtime_integrated": result.get("runtime_integrated") is False,
        "not_route_integrated": result.get("route_integrated") is False,
        "no_filesystem": result.get("filesystem_accessed") is False,
        "no_real_registry": result.get("real_registry_accessed") is False,
        "no_network": result.get("network_accessed") is False,
        "no_write": result.get("write_executed") is False,
        "no_broker": result.get("broker_called") is False,
        "no_order": result.get("order_sent") is False,
    }
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_VERSION,
        "ok": bool(result.get("ok") and all(checks.values())),
        "checks": checks,
        "adapter_result": result,
    }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_VERSION,
            "reader": "INJECTED_SYNTHETIC_READ_ONLY_PORT",
            "matrix": "43_SYNTHETIC_RESIDUAL_RECORDS",
            "runtime_integrated": False,
            "apply_surface": False,
        }
    )
)


__all__ = [
    "DEFAULT_SYNTHETIC_START_EPOCH_V1",
    "SyntheticReadOnlyRegistryPortV1",
    "SyntheticServerClockV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_runtime_read_only_adapter_fixture_v1",
    "run_runtime_read_only_preview_adapter_offline_harness_v1",
]
