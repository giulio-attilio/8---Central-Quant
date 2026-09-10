"""Dormant physical read-only port for one temporary synthetic Registry file.

The port is intentionally unable to address the active Registry.  It accepts
only a fixed synthetic filename directly inside a dedicated directory under
the operating-system temporary root.  A bounded binary read is protected by
pre/descriptor/post file identity checks and produces an HMAC-authenticated,
repr-protected observation.  No write, runtime, route, broker, or network
capability exists here.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PHYSICAL-READ-ONLY-SNAPSHOT-PORT-OFFLINE-CONTRACT-V1"
)
OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1 = (
    "C3_RESIDUAL_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_TEMPORARY_SYNTHETIC_ONLY_V1"
)
PHYSICAL_READ_ONLY_OBSERVATION_RECEIPT_VERSION_V1 = (
    "C3_RESIDUAL_PHYSICAL_READ_ONLY_OBSERVATION_RECEIPT_V1"
)
SYNTHETIC_REGISTRY_FILENAME_V1 = "synthetic_trade_registry.json"
SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1 = "c3_residual_read_only_"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_OPERATION_SECONDS = 300
_MAX_DOCUMENT_BYTES = 16_000_000
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "contract_version",
        "contract_sha256",
        "reader_instance_binding_sha256",
        "source_path_binding_sha256",
        "file_identity_before_sha256",
        "file_identity_descriptor_sha256",
        "file_identity_after_sha256",
        "raw_document_sha256",
        "snapshot_sha256",
        "document_size_bytes",
        "source_generation",
        "read_started_at_epoch",
        "read_finished_at_epoch",
        "deadline_epoch",
        "source_exists",
        "regular_file_verified",
        "symlink_rejected",
        "stable_file_identity_verified",
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


def physical_source_path_binding_sha256_v1(path: str | os.PathLike[str]) -> str:
    normalized = os.path.normcase(str(Path(path).resolve(strict=False)))
    return _sha256({"kind": "TEMPORARY_SYNTHETIC_REGISTRY_PATH_V1", "path": normalized})


def _file_identity(value: os.stat_result) -> dict[str, int]:
    return {
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(value.st_mode),
        "size": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
    }


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticPhysicalReadAuthorityV1:
    key: bytes = field(repr=False)
    key_id_sha256: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not bytes or not 32 <= len(self.key) <= 128:
            raise ValueError("synthetic physical read authority key must be 32..128 bytes")
        object.__setattr__(self, "key_id_sha256", hashlib.sha256(self.key).hexdigest())

    def __repr__(self) -> str:
        return "ProtectedSyntheticPhysicalReadAuthorityV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticPhysicalReadOnlyObservationV1:
    snapshot: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticPhysicalReadOnlyObservationV1(<protected>)"


@dataclass(frozen=True)
class DormantPhysicalReadOnlySnapshotPortConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    temporary_root: str | os.PathLike[str] | None = field(default=None, repr=False)
    expected_reader_instance_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_source_path_binding_sha256: str | None = field(default=None, repr=False)
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
        "status": "PHYSICAL_READ_ONLY_SNAPSHOT_PORT_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION,
        "offline_only": True,
        "synthetic_only": True,
        "default_off": True,
        "runtime_integrated": False,
        "route_integrated": False,
        "source_exists": False,
        "regular_file_verified": False,
        "symlink_rejected": False,
        "stable_file_identity_verified": False,
        "read_count": 0,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "network_accessed": False,
        "broker_called": False,
        "order_sent": False,
        "observation": None,
        "observation_receipt": None,
        "reasons": [],
    }


def _blocked(reason: str, result: Mapping[str, Any] | None = None) -> dict[str, Any]:
    output = dict(result) if isinstance(result, Mapping) else _base_result()
    output["ok"] = False
    output["status"] = "PHYSICAL_READ_ONLY_SNAPSHOT_PORT_BLOCKED"
    output["reasons"] = [reason]
    output["observation"] = None
    return output


def protected_synthetic_physical_read_only_observation_valid_v1(
    observation: Any,
    authority: ProtectedSyntheticPhysicalReadAuthorityV1,
    *,
    now_epoch: int | None = None,
) -> bool:
    if (
        type(observation) is not ProtectedSyntheticPhysicalReadOnlyObservationV1
        or type(authority) is not ProtectedSyntheticPhysicalReadAuthorityV1
        or type(observation.receipt) is not dict
        or set(observation.receipt) != _RECEIPT_KEYS
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
        snapshot_sha = residual.stable_sha256_v1(observation.snapshot)
        structural = bool(
            receipt["receipt_version"]
            == PHYSICAL_READ_ONLY_OBSERVATION_RECEIPT_VERSION_V1
            and receipt["contract_version"]
            == TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION
            and receipt["contract_sha256"]
            == TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256
            and all(
                _valid_sha256(receipt[key])
                for key in (
                    "reader_instance_binding_sha256",
                    "source_path_binding_sha256",
                    "file_identity_before_sha256",
                    "file_identity_descriptor_sha256",
                    "file_identity_after_sha256",
                    "raw_document_sha256",
                    "snapshot_sha256",
                )
            )
            and receipt["snapshot_sha256"] == snapshot_sha
            and receipt["file_identity_before_sha256"]
            == receipt["file_identity_descriptor_sha256"]
            == receipt["file_identity_after_sha256"]
            and type(receipt["document_size_bytes"]) is int
            and receipt["document_size_bytes"] > 0
            and type(receipt["source_generation"]) is int
            and receipt["source_generation"] >= 0
            and type(receipt["read_started_at_epoch"]) is int
            and type(receipt["read_finished_at_epoch"]) is int
            and type(receipt["deadline_epoch"]) is int
            and receipt["read_started_at_epoch"]
            <= receipt["read_finished_at_epoch"]
            < receipt["deadline_epoch"]
            and receipt["source_exists"] is True
            and receipt["regular_file_verified"] is True
            and receipt["symlink_rejected"] is True
            and receipt["stable_file_identity_verified"] is True
            and receipt["read_only"] is True
            and receipt["synthetic_only"] is True
            and receipt["filesystem_accessed"] is True
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
    if not structural:
        return False
    return now_epoch is None or (
        type(now_epoch) is int
        and receipt["read_finished_at_epoch"] <= now_epoch < receipt["deadline_epoch"]
    )


class DormantPhysicalReadOnlySnapshotPortV1:
    """Read exactly one bounded temporary synthetic JSON document."""

    def __init__(
        self,
        config: DormantPhysicalReadOnlySnapshotPortConfigV1 | None = None,
        *,
        target_path: str | os.PathLike[str],
        authority: ProtectedSyntheticPhysicalReadAuthorityV1,
        clock: Callable[[], int],
    ) -> None:
        self._config = config or DormantPhysicalReadOnlySnapshotPortConfigV1()
        self._target = Path(target_path)
        self._authority = authority
        self._clock = clock

    def snapshot(self) -> dict[str, Any]:
        result = _base_result()
        result["status"] = (
            "PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_ENABLED"
            if self._config.enabled
            else "PHYSICAL_READ_ONLY_SNAPSHOT_PORT_DEFAULT_OFF"
        )
        return result

    def read_snapshot_offline(self) -> dict[str, Any]:
        result = _base_result()
        if not self._config.enabled:
            return _blocked("PHYSICAL_READ_PORT_DEFAULT_OFF", result)
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1
        ):
            return _blocked("OFFLINE_SCOPE_ATTESTATION_REQUIRED", result)
        if not (
            type(self._authority) is ProtectedSyntheticPhysicalReadAuthorityV1
            and callable(self._clock)
            and _valid_sha256(
                self._config.expected_reader_instance_binding_sha256
            )
            and _valid_sha256(self._config.expected_source_path_binding_sha256)
        ):
            return _blocked("PHYSICAL_READ_PORT_DEPENDENCY_BINDING_INVALID", result)
        if self._config.temporary_root is None:
            return _blocked("SYNTHETIC_TEMPORARY_ROOT_REQUIRED", result)
        try:
            temporary_base = Path(tempfile.gettempdir()).resolve(strict=True)
            temporary_root_literal = Path(self._config.temporary_root)
            target_literal = self._target
            if temporary_root_literal.is_symlink() or target_literal.is_symlink():
                result["filesystem_accessed"] = True
                return _blocked("SYMLINK_SOURCE_FORBIDDEN", result)
            temporary_root = temporary_root_literal.resolve(strict=True)
            target = target_literal.resolve(strict=False)
            result["filesystem_accessed"] = True
        except (OSError, RuntimeError):
            result["filesystem_accessed"] = True
            return _blocked("TEMPORARY_PATH_RESOLUTION_FAILED", result)
        try:
            inside_system_temp = os.path.commonpath(
                [str(temporary_root), str(temporary_base)]
            ) == str(temporary_base)
        except ValueError:
            inside_system_temp = False
        if not (
            inside_system_temp
            and temporary_root != temporary_base
            and temporary_root.name.startswith(SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1)
            and target.parent == temporary_root
            and target.name == SYNTHETIC_REGISTRY_FILENAME_V1
        ):
            return _blocked("SYNTHETIC_TEMPORARY_PATH_POLICY_FAILED", result)
        path_binding = physical_source_path_binding_sha256_v1(target)
        if path_binding != self._config.expected_source_path_binding_sha256:
            return _blocked("SOURCE_PATH_BINDING_MISMATCH", result)
        if not target.exists():
            return _blocked("REGISTRY_SOURCE_MISSING", result)

        result["source_exists"] = True
        try:
            started_at = self._clock()
        except Exception:
            return _blocked("SERVER_CLOCK_UNAVAILABLE", result)
        if type(started_at) is not int:
            return _blocked("SERVER_CLOCK_INVALID", result)
        deadline = started_at + self._config.maximum_operation_seconds
        try:
            before_stat = target.stat()
            if not stat.S_ISREG(before_stat.st_mode):
                return _blocked("SOURCE_NOT_REGULAR_FILE", result)
            result["regular_file_verified"] = True
            if before_stat.st_size <= 0:
                return _blocked("SOURCE_DOCUMENT_EMPTY", result)
            if before_stat.st_size > self._config.maximum_document_bytes:
                return _blocked("SOURCE_DOCUMENT_BUDGET_EXCEEDED", result)
            with target.open("rb") as source:
                descriptor_before = os.fstat(source.fileno())
                raw = source.read(self._config.maximum_document_bytes + 1)
                descriptor_after = os.fstat(source.fileno())
                result["read_count"] = 1
            after_stat = target.stat()
        except Exception as exc:
            result["read_error_type"] = type(exc).__name__
            return _blocked("PHYSICAL_READ_FAILED_CLOSED", result)
        if len(raw) > self._config.maximum_document_bytes:
            return _blocked("SOURCE_DOCUMENT_BUDGET_EXCEEDED", result)
        before_identity = _file_identity(before_stat)
        descriptor_before_identity = _file_identity(descriptor_before)
        descriptor_after_identity = _file_identity(descriptor_after)
        after_identity = _file_identity(after_stat)
        if not (
            before_identity
            == descriptor_before_identity
            == descriptor_after_identity
            == after_identity
        ):
            return _blocked("SOURCE_CHANGED_DURING_READ", result)
        result["stable_file_identity_verified"] = True
        result["symlink_rejected"] = True
        try:
            text = raw.decode("utf-8")
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                return _blocked("SOURCE_DOCUMENT_NOT_MAPPING", result)
            snapshot_copy = json.loads(_canonical_json(parsed))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return _blocked("SOURCE_DOCUMENT_INVALID_JSON", result)
        try:
            finished_at = self._clock()
        except Exception:
            return _blocked("SERVER_CLOCK_UNAVAILABLE_AFTER_READ", result)
        if type(finished_at) is not int or finished_at >= deadline:
            return _blocked("PHYSICAL_READ_DEADLINE_EXCEEDED", result)

        identity_sha = _sha256(before_identity)
        receipt = {
            "receipt_version": PHYSICAL_READ_ONLY_OBSERVATION_RECEIPT_VERSION_V1,
            "contract_version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION,
            "contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256,
            "reader_instance_binding_sha256": self._config.expected_reader_instance_binding_sha256,
            "source_path_binding_sha256": path_binding,
            "file_identity_before_sha256": identity_sha,
            "file_identity_descriptor_sha256": _sha256(descriptor_before_identity),
            "file_identity_after_sha256": _sha256(after_identity),
            "raw_document_sha256": hashlib.sha256(raw).hexdigest(),
            "snapshot_sha256": residual.stable_sha256_v1(snapshot_copy),
            "document_size_bytes": len(raw),
            "source_generation": int(before_stat.st_mtime_ns),
            "read_started_at_epoch": started_at,
            "read_finished_at_epoch": finished_at,
            "deadline_epoch": deadline,
            "source_exists": True,
            "regular_file_verified": True,
            "symlink_rejected": True,
            "stable_file_identity_verified": True,
            "read_only": True,
            "synthetic_only": True,
            "filesystem_accessed": True,
            "real_registry_accessed": False,
            "registry_write": False,
            "write_executed": False,
            "network_accessed": False,
            "broker_called": False,
            "order_sent": False,
            "authority_key_id_sha256": self._authority.key_id_sha256,
            "receipt_hmac_sha256": "",
        }
        receipt["receipt_hmac_sha256"] = hmac.new(
            self._authority.key,
            _canonical_json(_receipt_payload(receipt)).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        observation = ProtectedSyntheticPhysicalReadOnlyObservationV1(
            snapshot=snapshot_copy,
            receipt=receipt,
        )
        if not protected_synthetic_physical_read_only_observation_valid_v1(
            observation,
            self._authority,
            now_epoch=finished_at,
        ):
            return _blocked("PHYSICAL_OBSERVATION_SELF_VALIDATION_FAILED", result)
        result.update(
            ok=True,
            status="PHYSICAL_READ_ONLY_SYNTHETIC_OBSERVATION_VERIFIED",
            observation=observation,
            observation_receipt=copy.deepcopy(receipt),
            reasons=[],
        )
        return result


_CONTRACT_DESCRIPTOR = {
    "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION,
    "offline_only": True,
    "synthetic_only": True,
    "default_off": True,
    "temporary_root_required": True,
    "synthetic_filename": SYNTHETIC_REGISTRY_FILENAME_V1,
    "bounded_binary_read": True,
    "stable_file_identity_required": True,
    "authenticated_observation": "HMAC_SHA256_SYNTHETIC_AUTHORITY",
    "real_registry_allowed": False,
    "write_surface": False,
    "maximum_operation_seconds": _MAX_OPERATION_SECONDS,
    "maximum_document_bytes": _MAX_DOCUMENT_BYTES,
}
TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256 = (
    _sha256(_CONTRACT_DESCRIPTOR)
)


__all__ = [
    "DormantPhysicalReadOnlySnapshotPortConfigV1",
    "DormantPhysicalReadOnlySnapshotPortV1",
    "OFFLINE_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_SCOPE_ATTESTATION_V1",
    "PHYSICAL_READ_ONLY_OBSERVATION_RECEIPT_VERSION_V1",
    "ProtectedSyntheticPhysicalReadAuthorityV1",
    "ProtectedSyntheticPhysicalReadOnlyObservationV1",
    "SYNTHETIC_REGISTRY_FILENAME_V1",
    "SYNTHETIC_TEMP_DIRECTORY_PREFIX_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PHYSICAL_READ_ONLY_SNAPSHOT_PORT_OFFLINE_CONTRACT_V1_VERSION",
    "physical_source_path_binding_sha256_v1",
    "protected_synthetic_physical_read_only_observation_valid_v1",
]
