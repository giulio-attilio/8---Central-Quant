"""Dormant bridge from a temporary physical read to protected residual preview.

The bridge composes only already-protected synthetic capabilities.  It retains
the physical observation receipt, truthfully reports filesystem access, and
passes the in-memory snapshot to the protected preview without exposing either
the snapshot or candidate.  No active Registry, route, runtime seam, write, or
apply capability is accepted.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1 as physical
import trade_registry_closed_identity_residual_repair_protected_preview_offline_contract_v1 as preview
import trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_contract_v1 as adapter


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PHYSICAL-PREVIEW-BRIDGE-OFFLINE-CONTRACT-V1"
)
OFFLINE_PHYSICAL_PREVIEW_BRIDGE_SCOPE_ATTESTATION_V1 = (
    "C3_RESIDUAL_PHYSICAL_PREVIEW_BRIDGE_TEMPORARY_SYNTHETIC_OFFLINE_ONLY_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_OPERATION_SECONDS = 300
_MAX_DOCUMENT_BYTES = 16_000_000
_PREVIEW_MAXIMUM_DEADLINE_SECONDS = 120


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


@dataclass(frozen=True)
class DormantPhysicalPreviewBridgeConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_physical_contract_sha256: str | None = field(default=None, repr=False)
    expected_preview_contract_sha256: str | None = field(default=None, repr=False)
    expected_reader_instance_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_source_path_binding_sha256: str | None = field(default=None, repr=False)
    maximum_operation_seconds: int = 180
    maximum_document_bytes: int = 8_000_000

    def __post_init__(self) -> None:
        if (
            type(self.maximum_operation_seconds) is not int
            or not 1 <= self.maximum_operation_seconds <= _MAX_OPERATION_SECONDS
        ):
            raise ValueError("maximum_operation_seconds must be between 1 and 300")
        if (
            type(self.maximum_document_bytes) is not int
            or not 1 <= self.maximum_document_bytes <= _MAX_DOCUMENT_BYTES
        ):
            raise ValueError("maximum_document_bytes must be between 1 and 16000000")


def _base_result() -> dict[str, Any]:
    return {
        "ok": False,
        "status": "PHYSICAL_PREVIEW_BRIDGE_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_VERSION,
        "offline_only": True,
        "synthetic_only": True,
        "default_off": True,
        "runtime_integrated": False,
        "route_integrated": False,
        "physical_port_called": False,
        "preview_called": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "network_accessed": False,
        "broker_called": False,
        "order_sent": False,
        "apply_allowed": False,
        "runtime_activation_allowed": False,
        "repair_ready": False,
        "physical_observation_receipt": None,
        "preview": None,
        "reasons": [],
    }


def _blocked(reason: str, result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = dict(result) if isinstance(result, Mapping) else _base_result()
    output["ok"] = False
    output["status"] = "PHYSICAL_PREVIEW_BRIDGE_BLOCKED"
    output["preview"] = None
    output["reasons"] = [reason]
    return output


class DormantResidualPhysicalPreviewBridgeV1:
    """One-shot temporary physical read to protected synthetic preview bridge."""

    def __init__(
        self,
        config: DormantPhysicalPreviewBridgeConfigV1 | None = None,
        *,
        physical_port: physical.DormantPhysicalReadOnlySnapshotPortV1,
        physical_authority: physical.ProtectedSyntheticPhysicalReadAuthorityV1,
        preview_controller: preview.DormantProtectedResidualPreviewV1,
        caps: residual.ResidualClosedIdentityRepairCapsV1,
        clock: Callable[[], int],
    ) -> None:
        self._config = config or DormantPhysicalPreviewBridgeConfigV1()
        self._physical_port = physical_port
        self._physical_authority = physical_authority
        self._preview_controller = preview_controller
        self._caps = caps
        self._clock = clock

    def snapshot(self) -> dict[str, Any]:
        result = _base_result()
        result["status"] = (
            "PHYSICAL_PREVIEW_BRIDGE_OFFLINE_ENABLED"
            if self._config.enabled
            else "PHYSICAL_PREVIEW_BRIDGE_DEFAULT_OFF"
        )
        return result

    def preview_from_physical_offline(self) -> dict[str, Any]:
        result = _base_result()
        if not self._config.enabled:
            return _blocked("PHYSICAL_PREVIEW_BRIDGE_DEFAULT_OFF", result)
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_PREVIEW_BRIDGE_SCOPE_ATTESTATION_V1
        ):
            return _blocked("OFFLINE_SCOPE_ATTESTATION_REQUIRED", result)
        if (
            self._config.expected_physical_contract_sha256
            != physical.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256
            or self._config.expected_preview_contract_sha256
            != preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256
        ):
            return _blocked("COMPOSED_CONTRACT_BINDING_MISMATCH", result)
        if not (
            type(self._physical_port)
            is physical.DormantPhysicalReadOnlySnapshotPortV1
            and type(self._physical_authority)
            is physical.ProtectedSyntheticPhysicalReadAuthorityV1
            and type(self._preview_controller)
            is preview.DormantProtectedResidualPreviewV1
            and type(self._caps) is residual.ResidualClosedIdentityRepairCapsV1
            and callable(self._clock)
            and _valid_sha256(
                self._config.expected_reader_instance_binding_sha256
            )
            and _valid_sha256(self._config.expected_source_path_binding_sha256)
        ):
            return _blocked("PHYSICAL_PREVIEW_BRIDGE_DEPENDENCIES_INVALID", result)
        try:
            started_at = self._clock()
        except Exception:
            return _blocked("BRIDGE_CLOCK_UNAVAILABLE", result)
        if type(started_at) is not int:
            return _blocked("BRIDGE_CLOCK_INVALID", result)
        bridge_deadline = started_at + self._config.maximum_operation_seconds
        try:
            physical_result = self._physical_port.read_snapshot_offline()
            result["physical_port_called"] = True
        except Exception as exc:
            result["physical_port_called"] = True
            result["physical_error_type"] = type(exc).__name__
            return _blocked("PHYSICAL_PORT_FAILED_CLOSED", result)
        result["filesystem_accessed"] = bool(
            physical_result.get("filesystem_accessed") is True
        )
        if physical_result.get("ok") is not True:
            result["physical_reasons"] = list(physical_result.get("reasons") or [])
            return _blocked("PHYSICAL_OBSERVATION_UNAVAILABLE", result)
        observation = physical_result.get("observation")
        receipt = physical_result.get("observation_receipt")
        if not (
            type(observation)
            is physical.ProtectedSyntheticPhysicalReadOnlyObservationV1
            and type(receipt) is dict
            and receipt == observation.receipt
            and physical_result.get("filesystem_accessed") is True
            and physical_result.get("real_registry_accessed") is False
            and physical_result.get("registry_write") is False
            and physical_result.get("write_executed") is False
            and physical_result.get("network_accessed") is False
            and physical_result.get("broker_called") is False
            and physical_result.get("order_sent") is False
        ):
            return _blocked("PHYSICAL_RESULT_UNSAFE", result)
        try:
            after_read = self._clock()
        except Exception:
            return _blocked("BRIDGE_CLOCK_UNAVAILABLE_AFTER_READ", result)
        if (
            type(after_read) is not int
            or after_read >= bridge_deadline
            or not physical.protected_synthetic_physical_read_only_observation_valid_v1(
                observation,
                self._physical_authority,
                now_epoch=after_read,
            )
        ):
            return _blocked("PHYSICAL_OBSERVATION_INVALID_OR_EXPIRED", result)
        result["physical_observation_receipt"] = copy.deepcopy(receipt)
        if (
            receipt.get("reader_instance_binding_sha256")
            != self._config.expected_reader_instance_binding_sha256
            or receipt.get("source_path_binding_sha256")
            != self._config.expected_source_path_binding_sha256
        ):
            return _blocked("PHYSICAL_SOURCE_BINDING_MISMATCH", result)
        if receipt.get("document_size_bytes", 0) > self._config.maximum_document_bytes:
            return _blocked("PHYSICAL_DOCUMENT_BUDGET_EXCEEDED", result)

        preview_deadline = min(
            bridge_deadline,
            receipt["deadline_epoch"],
            after_read + _PREVIEW_MAXIMUM_DEADLINE_SECONDS,
        )
        if after_read >= preview_deadline:
            return _blocked("NO_PREVIEW_DEADLINE_REMAINING", result)
        request_nonce_sha256 = _sha256(
            {
                "bridge_contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_SHA256,
                "physical_receipt_hmac_sha256": receipt["receipt_hmac_sha256"],
                "file_identity_sha256": receipt[
                    "file_identity_descriptor_sha256"
                ],
                "source_generation": receipt["source_generation"],
                "preview_deadline_epoch": preview_deadline,
            }
        )
        request = preview.ProtectedResidualPreviewRequestV1(
            registry_snapshot=observation.snapshot,
            expected_snapshot_sha256=receipt["snapshot_sha256"],
            request_nonce_sha256=request_nonce_sha256,
            requested_at_epoch=after_read,
            deadline_epoch=preview_deadline,
            caps=self._caps,
        )
        try:
            preview_result = self._preview_controller.preview_offline(
                request,
                now_epoch=after_read,
            )
            result["preview_called"] = True
        except Exception as exc:
            result["preview_called"] = True
            result["preview_error_type"] = type(exc).__name__
            return _blocked("PROTECTED_PREVIEW_FAILED_CLOSED", result)
        try:
            finished_at = self._clock()
        except Exception:
            return _blocked("BRIDGE_CLOCK_UNAVAILABLE_AFTER_PREVIEW", result)
        if (
            type(finished_at) is not int
            or finished_at >= bridge_deadline
            or finished_at > preview_deadline
        ):
            return _blocked("PHYSICAL_PREVIEW_BRIDGE_DEADLINE_EXCEEDED", result)
        sanitized_preview = adapter.sanitized_protected_preview_projection_v1(
            preview_result,
            source_snapshot_sha256=receipt["snapshot_sha256"],
            request_nonce_sha256=request_nonce_sha256,
            deadline_epoch=preview_deadline,
        )
        if sanitized_preview is None:
            return _blocked("PROTECTED_PREVIEW_RESPONSE_UNSAFE", result)
        if finished_at > sanitized_preview["preview_receipt"]["expires_at_epoch"]:
            return _blocked("PROTECTED_PREVIEW_RECEIPT_EXPIRED", result)

        result.update(
            ok=True,
            status="PHYSICAL_PREVIEW_BRIDGE_SYNTHETIC_VERIFIED",
            preview=sanitized_preview,
            bridge_receipt_sha256=_sha256(
                {
                    "bridge_contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_SHA256,
                    "physical_receipt_hmac_sha256": receipt[
                        "receipt_hmac_sha256"
                    ],
                    "preview_receipt_hmac_sha256": sanitized_preview[
                        "preview_receipt"
                    ]["receipt_hmac_sha256"],
                    "filesystem_accessed": True,
                    "real_registry_accessed": False,
                    "started_at_epoch": started_at,
                    "finished_at_epoch": finished_at,
                    "bridge_deadline_epoch": bridge_deadline,
                    "preview_deadline_epoch": preview_deadline,
                }
            ),
            reasons=[],
        )
        return result


_CONTRACT_DESCRIPTOR = {
    "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_VERSION,
    "physical_contract_sha256": physical.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256,
    "preview_contract_sha256": preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
    "preview_sanitizer_contract_sha256": adapter.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_SHA256,
    "offline_only": True,
    "synthetic_only": True,
    "filesystem_access_truthful": True,
    "real_registry_allowed": False,
    "default_off": True,
    "apply_surface": False,
    "maximum_operation_seconds": _MAX_OPERATION_SECONDS,
    "maximum_document_bytes": _MAX_DOCUMENT_BYTES,
}
TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_SHA256 = (
    _sha256(_CONTRACT_DESCRIPTOR)
)


__all__ = [
    "DormantPhysicalPreviewBridgeConfigV1",
    "DormantResidualPhysicalPreviewBridgeV1",
    "OFFLINE_PHYSICAL_PREVIEW_BRIDGE_SCOPE_ATTESTATION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_PREVIEW_BRIDGE_OFFLINE_CONTRACT_V1_VERSION",
]
