"""Dormant offline rehearsal of a runtime read-only residual preview adapter.

The adapter accepts only an injected synthetic read port.  It creates the
operation deadline and snapshot binding itself, validates an authenticated
read receipt, and composes the protected synthetic preview exactly once.  It
cannot read files, accept a real Registry observation, integrate a route, or
apply a repair.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_protected_preview_offline_contract_v1 as preview


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-RUNTIME-READ-ONLY-PREVIEW-ADAPTER-OFFLINE-CONTRACT-V1"
)
OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_RESIDUAL_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SYNTHETIC_OFFLINE_ONLY_V1"
)
SYNTHETIC_READ_OBSERVATION_RECEIPT_VERSION_V1 = (
    "C3_RESIDUAL_SYNTHETIC_READ_ONLY_OBSERVATION_RECEIPT_V1"
)
SYNTHETIC_READ_SOURCE_KIND_V1 = "SYNTHETIC_IN_MEMORY_READ_PORT_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_OPERATION_SECONDS = 300
_MAX_DOCUMENT_BYTES = 16_000_000
_OBSERVATION_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "source_kind",
        "source_exists",
        "reader_instance_binding_sha256",
        "source_path_binding_sha256",
        "source_generation",
        "raw_document_sha256",
        "snapshot_sha256",
        "document_size_bytes",
        "read_started_at_epoch",
        "read_finished_at_epoch",
        "deadline_epoch",
        "read_only",
        "synthetic_only",
        "filesystem_accessed",
        "real_registry_accessed",
        "registry_write",
        "write_executed",
        "network_accessed",
        "broker_called",
        "order_sent",
        "authority_key_id_sha256",
        "receipt_hmac_sha256",
    }
)


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


def _receipt_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in receipt.items()
        if key != "receipt_hmac_sha256"
    }


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticReadObservationAuthorityV1:
    key: bytes = field(repr=False)
    key_id_sha256: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not bytes or not 32 <= len(self.key) <= 128:
            raise ValueError("synthetic read authority key must be 32..128 bytes")
        object.__setattr__(self, "key_id_sha256", hashlib.sha256(self.key).hexdigest())

    def __repr__(self) -> str:
        return "ProtectedSyntheticReadObservationAuthorityV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticReadOnlyRegistryObservationV1:
    snapshot: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticReadOnlyRegistryObservationV1(<protected>)"


def build_protected_synthetic_read_only_observation_v1(
    snapshot: Mapping[str, Any],
    *,
    authority: ProtectedSyntheticReadObservationAuthorityV1,
    reader_instance_binding_sha256: str,
    source_path_binding_sha256: str,
    source_generation: int,
    source_exists: bool,
    read_started_at_epoch: int,
    read_finished_at_epoch: int,
    deadline_epoch: int,
) -> ProtectedSyntheticReadOnlyRegistryObservationV1:
    """Materialize one authenticated synthetic observation without I/O."""

    if type(authority) is not ProtectedSyntheticReadObservationAuthorityV1:
        raise ValueError("protected synthetic read authority required")
    try:
        snapshot_copy = json.loads(_canonical_json(dict(snapshot)))
        canonical_bytes = _canonical_json(snapshot_copy).encode("utf-8")
    except (TypeError, ValueError):
        raise ValueError("synthetic snapshot must be canonical JSON") from None
    if not _valid_sha256(reader_instance_binding_sha256):
        raise ValueError("reader instance binding sha256 required")
    if not _valid_sha256(source_path_binding_sha256):
        raise ValueError("source path binding sha256 required")
    if type(source_generation) is not int or source_generation < 0:
        raise ValueError("source generation must be a non-negative integer")
    if type(source_exists) is not bool:
        raise ValueError("source_exists must be bool")
    if not (
        type(read_started_at_epoch) is int
        and type(read_finished_at_epoch) is int
        and type(deadline_epoch) is int
        and read_started_at_epoch <= read_finished_at_epoch <= deadline_epoch
    ):
        raise ValueError("synthetic read timestamps are invalid")
    document_sha = hashlib.sha256(canonical_bytes).hexdigest()
    receipt = {
        "receipt_version": SYNTHETIC_READ_OBSERVATION_RECEIPT_VERSION_V1,
        "source_kind": SYNTHETIC_READ_SOURCE_KIND_V1,
        "source_exists": source_exists,
        "reader_instance_binding_sha256": reader_instance_binding_sha256,
        "source_path_binding_sha256": source_path_binding_sha256,
        "source_generation": source_generation,
        "raw_document_sha256": document_sha,
        "snapshot_sha256": residual.stable_sha256_v1(snapshot_copy),
        "document_size_bytes": len(canonical_bytes),
        "read_started_at_epoch": read_started_at_epoch,
        "read_finished_at_epoch": read_finished_at_epoch,
        "deadline_epoch": deadline_epoch,
        "read_only": True,
        "synthetic_only": True,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "network_accessed": False,
        "broker_called": False,
        "order_sent": False,
        "authority_key_id_sha256": authority.key_id_sha256,
        "receipt_hmac_sha256": "",
    }
    receipt["receipt_hmac_sha256"] = hmac.new(
        authority.key,
        _canonical_json(_receipt_payload(receipt)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return ProtectedSyntheticReadOnlyRegistryObservationV1(
        snapshot=snapshot_copy,
        receipt=receipt,
    )


def protected_synthetic_read_only_observation_valid_v1(
    observation: Any,
    authority: ProtectedSyntheticReadObservationAuthorityV1,
    *,
    expected_deadline_epoch: int,
    now_epoch: int,
) -> bool:
    if (
        type(observation) is not ProtectedSyntheticReadOnlyRegistryObservationV1
        or type(authority) is not ProtectedSyntheticReadObservationAuthorityV1
        or type(observation.receipt) is not dict
        or set(observation.receipt) != _OBSERVATION_RECEIPT_KEYS
        or type(expected_deadline_epoch) is not int
        or type(now_epoch) is not int
    ):
        return False
    receipt = observation.receipt
    signature = _valid_sha256(receipt.get("receipt_hmac_sha256"))
    expected_signature = hmac.new(
        authority.key,
        _canonical_json(_receipt_payload(receipt)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    try:
        canonical_bytes = _canonical_json(dict(observation.snapshot)).encode("utf-8")
        return bool(
            receipt["receipt_version"] == SYNTHETIC_READ_OBSERVATION_RECEIPT_VERSION_V1
            and receipt["source_kind"] == SYNTHETIC_READ_SOURCE_KIND_V1
            and type(receipt["source_exists"]) is bool
            and _valid_sha256(receipt["reader_instance_binding_sha256"])
            and _valid_sha256(receipt["source_path_binding_sha256"])
            and type(receipt["source_generation"]) is int
            and receipt["source_generation"] >= 0
            and receipt["raw_document_sha256"]
            == hashlib.sha256(canonical_bytes).hexdigest()
            and receipt["snapshot_sha256"]
            == residual.stable_sha256_v1(observation.snapshot)
            and receipt["document_size_bytes"] == len(canonical_bytes)
            and type(receipt["read_started_at_epoch"]) is int
            and type(receipt["read_finished_at_epoch"]) is int
            and receipt["read_started_at_epoch"]
            <= receipt["read_finished_at_epoch"]
            <= now_epoch
            < expected_deadline_epoch
            and receipt["deadline_epoch"] == expected_deadline_epoch
            and receipt["read_only"] is True
            and receipt["synthetic_only"] is True
            and receipt["filesystem_accessed"] is False
            and receipt["real_registry_accessed"] is False
            and receipt["registry_write"] is False
            and receipt["write_executed"] is False
            and receipt["network_accessed"] is False
            and receipt["broker_called"] is False
            and receipt["order_sent"] is False
            and receipt["authority_key_id_sha256"] == authority.key_id_sha256
            and signature
            and hmac.compare_digest(signature, expected_signature)
        )
    except (KeyError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class DormantRuntimeReadOnlyPreviewAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_reader_instance_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_source_path_binding_sha256: str | None = field(default=None, repr=False)
    expected_preview_contract_sha256: str | None = field(default=None, repr=False)
    maximum_operation_seconds: int = 120
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
        "status": "RUNTIME_READ_ONLY_PREVIEW_ADAPTER_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_VERSION,
        "offline_only": True,
        "synthetic_only": True,
        "default_off": True,
        "runtime_integrated": False,
        "route_integrated": False,
        "read_port_called": False,
        "preview_called": False,
        "apply_allowed": False,
        "runtime_activation_allowed": False,
        "filesystem_accessed": False,
        "registry_accessed": False,
        "real_registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "network_accessed": False,
        "broker_called": False,
        "order_sent": False,
        "observation_receipt": None,
        "preview": None,
        "reasons": [],
    }


def _blocked(reason: str, result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = dict(result) if isinstance(result, Mapping) else _base_result()
    output["ok"] = False
    output["status"] = "RUNTIME_READ_ONLY_PREVIEW_ADAPTER_BLOCKED"
    output["reasons"] = [reason]
    output["preview"] = None
    return output


def _sanitized_preview_projection(
    value: Any,
    *,
    source_snapshot_sha256: str,
    request_nonce_sha256: str,
    deadline_epoch: int,
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    receipt = value.get("preview_receipt")
    summary = value.get("summary")
    actions = value.get("actions")
    quarantine = value.get("quarantine")
    changed_paths = value.get("changed_paths")
    if not (
        value.get("ok") is True
        and value.get("offline_only") is True
        and value.get("synthetic_only") is True
        and value.get("apply_allowed") is False
        and value.get("runtime_activation_allowed") is False
        and value.get("filesystem_accessed") is False
        and value.get("real_registry_accessed") is False
        and value.get("registry_write") is False
        and value.get("write_executed") is False
        and value.get("network_accessed") is False
        and value.get("broker_called") is False
        and value.get("order_sent") is False
        and value.get("repair_ready") is False
        and type(receipt) is dict
        and receipt.get("contract_sha256")
        == preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256
        and receipt.get("source_attestation")
        == preview.SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1
        and receipt.get("source_snapshot_sha256") == source_snapshot_sha256
        and receipt.get("request_nonce_sha256") == request_nonce_sha256
        and receipt.get("request_deadline_epoch") == deadline_epoch
        and receipt.get("repair_ready") is False
        and receipt.get("apply_allowed") is False
        and receipt.get("runtime_activation_allowed") is False
        and receipt.get("synthetic_only") is True
        and isinstance(summary, Mapping)
        and isinstance(actions, list)
        and all(isinstance(item, Mapping) for item in actions)
        and isinstance(quarantine, list)
        and all(isinstance(item, Mapping) for item in quarantine)
        and isinstance(changed_paths, list)
        and all(isinstance(path, str) for path in changed_paths)
        and _valid_sha256(value.get("sanitized_preview_sha256"))
    ):
        return None
    projection = {
        "ok": True,
        "status": str(value.get("status") or ""),
        "version": str(value.get("version") or ""),
        "offline_only": True,
        "in_memory_only": value.get("in_memory_only") is True,
        "synthetic_only": True,
        "default_off": value.get("default_off") is True,
        "preview_available": value.get("preview_available") is True,
        "preview_candidate_complete": value.get("preview_candidate_complete") is True,
        "repair_ready": False,
        "apply_allowed": False,
        "runtime_activation_allowed": False,
        "filesystem_accessed": False,
        "registry_accessed": value.get("registry_accessed") is True,
        "real_registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "network_accessed": False,
        "broker_called": False,
        "order_sent": False,
        "preview_receipt": copy.deepcopy(receipt),
        "summary": copy.deepcopy(dict(summary)),
        "actions": copy.deepcopy(actions),
        "quarantine": copy.deepcopy(quarantine),
        "changed_paths": copy.deepcopy(changed_paths),
        "reasons": [],
        "sanitized_preview_sha256": value["sanitized_preview_sha256"],
    }
    try:
        serialized = _canonical_json(projection)
    except (TypeError, ValueError):
        return None
    if "candidate_registry" in serialized or "registry_snapshot" in serialized:
        return None
    return projection


def sanitized_protected_preview_projection_v1(
    value: Any,
    *,
    source_snapshot_sha256: str,
    request_nonce_sha256: str,
    deadline_epoch: int,
) -> dict[str, Any] | None:
    """Expose the strict sanitizer for other dormant offline compositions."""

    return _sanitized_preview_projection(
        value,
        source_snapshot_sha256=source_snapshot_sha256,
        request_nonce_sha256=request_nonce_sha256,
        deadline_epoch=deadline_epoch,
    )


class DormantResidualRuntimeReadOnlyPreviewAdapterV1:
    """Synthetic read-port composition rehearsal with no apply capability."""

    def __init__(
        self,
        config: DormantRuntimeReadOnlyPreviewAdapterConfigV1 | None = None,
        *,
        read_port: Callable[[int], ProtectedSyntheticReadOnlyRegistryObservationV1],
        read_authority: ProtectedSyntheticReadObservationAuthorityV1,
        preview_controller: preview.DormantProtectedResidualPreviewV1,
        caps: residual.ResidualClosedIdentityRepairCapsV1,
        clock: Callable[[], int],
    ) -> None:
        self._config = config or DormantRuntimeReadOnlyPreviewAdapterConfigV1()
        self._read_port = read_port
        self._read_authority = read_authority
        self._preview_controller = preview_controller
        self._caps = caps
        self._clock = clock

    def snapshot(self) -> dict[str, Any]:
        result = _base_result()
        result["status"] = (
            "RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_ENABLED"
            if self._config.enabled
            else "RUNTIME_READ_ONLY_PREVIEW_ADAPTER_DEFAULT_OFF"
        )
        return result

    def preview_read_only_offline(self) -> dict[str, Any]:
        result = _base_result()
        if not self._config.enabled:
            return _blocked("ADAPTER_DEFAULT_OFF", result)
        if (
            self._config.scope_attestation
            != OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            return _blocked("OFFLINE_SCOPE_ATTESTATION_REQUIRED", result)
        if (
            self._config.expected_preview_contract_sha256
            != preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256
        ):
            return _blocked("PREVIEW_CONTRACT_BINDING_MISMATCH", result)
        if not (
            callable(self._read_port)
            and type(self._read_authority)
            is ProtectedSyntheticReadObservationAuthorityV1
            and type(self._preview_controller)
            is preview.DormantProtectedResidualPreviewV1
            and type(self._caps) is residual.ResidualClosedIdentityRepairCapsV1
            and callable(self._clock)
            and _valid_sha256(
                self._config.expected_reader_instance_binding_sha256
            )
            and _valid_sha256(self._config.expected_source_path_binding_sha256)
        ):
            return _blocked("ADAPTER_DEPENDENCY_BINDING_INVALID", result)

        try:
            started_at = self._clock()
        except Exception:
            return _blocked("SERVER_CLOCK_UNAVAILABLE", result)
        if type(started_at) is not int:
            return _blocked("SERVER_CLOCK_INVALID", result)
        deadline = started_at + self._config.maximum_operation_seconds
        try:
            observation = self._read_port(deadline)
            result["read_port_called"] = True
        except Exception as exc:
            result["read_port_called"] = True
            result["read_error_type"] = type(exc).__name__
            return _blocked("READ_PORT_FAILED_CLOSED", result)
        try:
            after_read = self._clock()
        except Exception:
            return _blocked("SERVER_CLOCK_UNAVAILABLE_AFTER_READ", result)
        if not protected_synthetic_read_only_observation_valid_v1(
            observation,
            self._read_authority,
            expected_deadline_epoch=deadline,
            now_epoch=after_read,
        ):
            return _blocked("READ_OBSERVATION_INVALID", result)
        receipt = copy.deepcopy(dict(observation.receipt))
        result["observation_receipt"] = receipt
        if receipt["source_exists"] is not True:
            return _blocked("REGISTRY_SOURCE_MISSING", result)
        if (
            receipt["reader_instance_binding_sha256"]
            != self._config.expected_reader_instance_binding_sha256
            or receipt["source_path_binding_sha256"]
            != self._config.expected_source_path_binding_sha256
        ):
            return _blocked("READ_SOURCE_BINDING_MISMATCH", result)
        if receipt["document_size_bytes"] > self._config.maximum_document_bytes:
            return _blocked("READ_DOCUMENT_BUDGET_EXCEEDED", result)

        request_nonce_sha256 = _sha256(
            {
                "observation_receipt_hmac_sha256": receipt[
                    "receipt_hmac_sha256"
                ],
                "started_at_epoch": started_at,
                "deadline_epoch": deadline,
                "adapter_contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_SHA256,
            }
        )
        request = preview.ProtectedResidualPreviewRequestV1(
            registry_snapshot=observation.snapshot,
            expected_snapshot_sha256=receipt["snapshot_sha256"],
            request_nonce_sha256=request_nonce_sha256,
            requested_at_epoch=started_at,
            deadline_epoch=deadline,
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
            return _blocked("SERVER_CLOCK_UNAVAILABLE_AFTER_PREVIEW", result)
        if type(finished_at) is not int or finished_at >= deadline:
            return _blocked("ADAPTER_DEADLINE_EXCEEDED", result)
        if preview_result.get("ok") is not True:
            result["preview_reasons"] = list(preview_result.get("reasons") or [])
            return _blocked("PROTECTED_PREVIEW_FAILED_CLOSED", result)
        sanitized_preview = _sanitized_preview_projection(
            preview_result,
            source_snapshot_sha256=receipt["snapshot_sha256"],
            request_nonce_sha256=request_nonce_sha256,
            deadline_epoch=deadline,
        )
        if sanitized_preview is None:
            return _blocked("PROTECTED_PREVIEW_RESPONSE_UNSAFE", result)

        result.update(
            ok=True,
            status="RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SYNTHETIC_VERIFIED",
            preview=sanitized_preview,
            adapter_receipt_sha256=_sha256(
                {
                    "adapter_contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_SHA256,
                    "reader_instance_binding_sha256": receipt[
                        "reader_instance_binding_sha256"
                    ],
                    "source_path_binding_sha256": receipt[
                        "source_path_binding_sha256"
                    ],
                    "source_generation": receipt["source_generation"],
                    "observation_receipt_hmac_sha256": receipt[
                        "receipt_hmac_sha256"
                    ],
                    "preview_receipt_hmac_sha256": sanitized_preview[
                        "preview_receipt"
                    ]["receipt_hmac_sha256"],
                    "started_at_epoch": started_at,
                    "finished_at_epoch": finished_at,
                    "deadline_epoch": deadline,
                }
            ),
            reasons=[],
        )
        return result


_CONTRACT_DESCRIPTOR = {
    "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_VERSION,
    "preview_contract_sha256": preview.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
    "offline_only": True,
    "synthetic_only": True,
    "default_off": True,
    "server_owned_time_and_hashes": True,
    "missing_source_policy": "FAIL_CLOSED",
    "real_registry_observation_allowed": False,
    "apply_surface": False,
    "maximum_operation_seconds": _MAX_OPERATION_SECONDS,
    "maximum_document_bytes": _MAX_DOCUMENT_BYTES,
}
TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_SHA256 = (
    _sha256(_CONTRACT_DESCRIPTOR)
)


__all__ = [
    "DormantResidualRuntimeReadOnlyPreviewAdapterV1",
    "DormantRuntimeReadOnlyPreviewAdapterConfigV1",
    "OFFLINE_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_SCOPE_ATTESTATION_V1",
    "ProtectedSyntheticReadObservationAuthorityV1",
    "ProtectedSyntheticReadOnlyRegistryObservationV1",
    "SYNTHETIC_READ_OBSERVATION_RECEIPT_VERSION_V1",
    "SYNTHETIC_READ_SOURCE_KIND_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_RUNTIME_READ_ONLY_PREVIEW_ADAPTER_OFFLINE_CONTRACT_V1_VERSION",
    "build_protected_synthetic_read_only_observation_v1",
    "protected_synthetic_read_only_observation_valid_v1",
    "sanitized_protected_preview_projection_v1",
]
