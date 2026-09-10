"""Dormant protected preview for residual CLOSED identity repair.

Only a synthetic, injected in-memory Registry snapshot is accepted.  The raw
snapshot and the repair candidate never leave the protected request/planner
boundary.  The public result contains sanitized counts, paths and hashes plus
an expiring HMAC-authenticated receipt.  There is deliberately no apply,
runtime, filesystem, network, broker, or persistence capability in this
module.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-10-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-PROTECTED-PREVIEW-OFFLINE-CONTRACT-V1"
)
OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_SYNTHETIC_OFFLINE_ONLY_V1"
)
SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1 = (
    "C3_SYNTHETIC_IN_MEMORY_REGISTRY_SNAPSHOT_V1"
)
PROTECTED_RESIDUAL_PREVIEW_RECEIPT_VERSION_V1 = (
    "C3_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_RECEIPT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECEIPT_TTL_SECONDS = 300
_MAX_REQUEST_DEADLINE_SECONDS = 300
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "contract_version",
        "contract_sha256",
        "planner_contract_version",
        "planner_contract_sha256",
        "source_attestation",
        "source_snapshot_sha256",
        "candidate_snapshot_sha256",
        "plan_sha256",
        "caps_binding_sha256",
        "request_nonce_sha256",
        "summary_sha256",
        "actions_sha256",
        "quarantine_sha256",
        "changed_paths_sha256",
        "issued_at_epoch",
        "expires_at_epoch",
        "request_deadline_epoch",
        "preview_candidate_complete",
        "repair_ready",
        "apply_allowed",
        "runtime_activation_allowed",
        "synthetic_only",
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
class ProtectedSyntheticResidualPreviewAuthorityV1:
    """Synthetic receipt authority whose key is never included in repr/output."""

    key: bytes = field(repr=False)
    key_id_sha256: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not bytes or not 32 <= len(self.key) <= 128:
            raise ValueError("synthetic preview authority key must be 32..128 bytes")
        object.__setattr__(self, "key_id_sha256", hashlib.sha256(self.key).hexdigest())

    def __repr__(self) -> str:
        return "ProtectedSyntheticResidualPreviewAuthorityV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedResidualPreviewRequestV1:
    """Protected carrier for a synthetic snapshot and its exact request binding."""

    registry_snapshot: Mapping[str, Any] = field(repr=False)
    expected_snapshot_sha256: str = field(repr=False)
    request_nonce_sha256: str = field(repr=False)
    requested_at_epoch: int = field(repr=False)
    deadline_epoch: int = field(repr=False)
    caps: residual.ResidualClosedIdentityRepairCapsV1 = field(repr=False)
    source_attestation: str = field(
        default=SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1,
        repr=False,
    )
    synthetic_only: bool = field(default=True, repr=False)

    def __repr__(self) -> str:
        return "ProtectedResidualPreviewRequestV1(<protected>)"


@dataclass(frozen=True)
class DormantProtectedResidualPreviewConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_planner_contract_sha256: str | None = field(default=None, repr=False)
    receipt_ttl_seconds: int = 60
    maximum_deadline_seconds: int = _MAX_REQUEST_DEADLINE_SECONDS

    def __post_init__(self) -> None:
        if (
            isinstance(self.receipt_ttl_seconds, bool)
            or not isinstance(self.receipt_ttl_seconds, int)
            or not 1 <= self.receipt_ttl_seconds <= _MAX_RECEIPT_TTL_SECONDS
        ):
            raise ValueError("receipt_ttl_seconds must be between 1 and 300")
        if (
            isinstance(self.maximum_deadline_seconds, bool)
            or not isinstance(self.maximum_deadline_seconds, int)
            or not 1 <= self.maximum_deadline_seconds <= _MAX_REQUEST_DEADLINE_SECONDS
        ):
            raise ValueError("maximum_deadline_seconds must be between 1 and 300")


def _base_result() -> dict[str, Any]:
    return {
        "ok": False,
        "status": "PROTECTED_RESIDUAL_PREVIEW_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION,
        "offline_only": True,
        "in_memory_only": True,
        "synthetic_only": True,
        "default_off": True,
        "preview_available": False,
        "preview_candidate_complete": False,
        "repair_ready": False,
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
        "preview_receipt": None,
        "summary": {},
        "actions": [],
        "quarantine": [],
        "changed_paths": [],
        "reasons": [],
    }


def _blocked(reason: str) -> dict[str, Any]:
    result = _base_result()
    result["reasons"] = [reason]
    return result


def _caps_binding(caps: residual.ResidualClosedIdentityRepairCapsV1) -> dict[str, Any]:
    return {
        "max_closed_records": caps.max_closed_records,
        "max_residual_records": caps.max_residual_records,
        "predator_epoch_tolerance_seconds": caps.predator_epoch_tolerance_seconds,
        "minute_boundary_tolerance_seconds": caps.minute_boundary_tolerance_seconds,
        "hard_max_residual_records": (
            residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_HARD_MAX_RECORDS_V1
        ),
    }


def _sanitize_sequence(
    value: Any,
    *,
    allowed_keys: frozenset[str],
) -> list[dict[str, Any]] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    sanitized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        sanitized.append(
            {
                key: copy.deepcopy(item[key])
                for key in sorted(set(item).intersection(allowed_keys))
            }
        )
    return sanitized


def _plan_integral(plan: Mapping[str, Any], source_sha256: str) -> bool:
    plan_sha = _valid_sha256(plan.get("plan_sha256"))
    candidate_sha = _valid_sha256(plan.get("candidate_snapshot_sha256"))
    binding = {
        key: value
        for key, value in plan.items()
        if key not in {"candidate_registry", "plan_sha256"}
    }
    return bool(
        plan.get("ok") is True
        and plan.get("offline_only") is True
        and plan.get("in_memory_only") is True
        and plan.get("apply_allowed") is False
        and plan.get("runtime_activation_allowed") is False
        and plan.get("registry_accessed") is False
        and plan.get("registry_write") is False
        and plan.get("write_executed") is False
        and plan.get("broker_called") is False
        and plan.get("order_sent") is False
        and _valid_sha256(plan.get("source_snapshot_sha256")) == source_sha256
        and candidate_sha
        and plan_sha
        and hmac.compare_digest(plan_sha, residual.stable_sha256_v1(binding))
        and isinstance(plan.get("candidate_registry"), Mapping)
        and hmac.compare_digest(
            candidate_sha,
            residual.stable_sha256_v1(plan["candidate_registry"]),
        )
    )


def protected_residual_preview_receipt_valid_v1(
    receipt: Any,
    authority: ProtectedSyntheticResidualPreviewAuthorityV1,
    *,
    now_epoch: int | None = None,
) -> bool:
    """Validate exact receipt shape, authority, integrity and optional liveness."""

    if (
        type(receipt) is not dict
        or set(receipt) != _RECEIPT_KEYS
        or type(authority) is not ProtectedSyntheticResidualPreviewAuthorityV1
    ):
        return False
    signature = _valid_sha256(receipt.get("receipt_hmac_sha256"))
    expected = hmac.new(
        authority.key,
        _canonical_json(_receipt_payload(receipt)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    try:
        issued = receipt["issued_at_epoch"]
        expires = receipt["expires_at_epoch"]
        deadline = receipt["request_deadline_epoch"]
        structural = bool(
            receipt["receipt_version"] == PROTECTED_RESIDUAL_PREVIEW_RECEIPT_VERSION_V1
            and receipt["contract_version"]
            == TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION
            and receipt["contract_sha256"]
            == TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256
            and receipt["planner_contract_version"]
            == residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION
            and receipt["planner_contract_sha256"]
            == residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256
            and receipt["source_attestation"]
            == SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1
            and receipt["authority_key_id_sha256"] == authority.key_id_sha256
            and all(
                _valid_sha256(receipt[key])
                for key in (
                    "source_snapshot_sha256",
                    "candidate_snapshot_sha256",
                    "plan_sha256",
                    "caps_binding_sha256",
                    "request_nonce_sha256",
                    "summary_sha256",
                    "actions_sha256",
                    "quarantine_sha256",
                    "changed_paths_sha256",
                )
            )
            and type(issued) is int
            and type(expires) is int
            and type(deadline) is int
            and issued <= expires <= deadline
            and 1 <= expires - issued <= _MAX_RECEIPT_TTL_SECONDS
            and receipt["repair_ready"] is False
            and receipt["apply_allowed"] is False
            and receipt["runtime_activation_allowed"] is False
            and receipt["synthetic_only"] is True
            and signature
            and hmac.compare_digest(signature, expected)
        )
    except (KeyError, TypeError, ValueError):
        return False
    if not structural:
        return False
    return now_epoch is None or (
        type(now_epoch) is int and issued <= now_epoch <= expires
    )


class DormantProtectedResidualPreviewV1:
    """Preview-only controller with no apply or runtime integration surface."""

    def __init__(
        self,
        config: DormantProtectedResidualPreviewConfigV1 | None = None,
        *,
        authority: ProtectedSyntheticResidualPreviewAuthorityV1,
    ) -> None:
        self._config = config or DormantProtectedResidualPreviewConfigV1()
        self._authority = authority

    def snapshot(self) -> dict[str, Any]:
        enabled = bool(
            self._config.enabled
            and self._config.scope_attestation
            == OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1
            and self._config.expected_planner_contract_sha256
            == residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256
        )
        result = _base_result()
        result.update(
            status=(
                "PROTECTED_RESIDUAL_PREVIEW_OFFLINE_ENABLED"
                if enabled
                else "PROTECTED_RESIDUAL_PREVIEW_DEFAULT_OFF"
            ),
            preview_available=enabled,
            authority_key_id_sha256=self._authority.key_id_sha256,
        )
        return result

    def preview_offline(
        self,
        request: ProtectedResidualPreviewRequestV1,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return _blocked("PREVIEW_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1
        ):
            return _blocked("OFFLINE_SCOPE_ATTESTATION_REQUIRED")
        if (
            self._config.expected_planner_contract_sha256
            != residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256
        ):
            return _blocked("PLANNER_CONTRACT_BINDING_MISMATCH")
        if type(request) is not ProtectedResidualPreviewRequestV1:
            return _blocked("PROTECTED_REQUEST_REQUIRED")
        if (
            request.synthetic_only is not True
            or request.source_attestation
            != SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1
        ):
            return _blocked("SYNTHETIC_SOURCE_ATTESTATION_REQUIRED")
        if (
            type(now_epoch) is not int
            or type(request.requested_at_epoch) is not int
            or type(request.deadline_epoch) is not int
            or request.requested_at_epoch > now_epoch
            or now_epoch >= request.deadline_epoch
            or request.deadline_epoch - request.requested_at_epoch
            > self._config.maximum_deadline_seconds
            or now_epoch - request.requested_at_epoch
            > self._config.maximum_deadline_seconds
        ):
            return _blocked("REQUEST_DEADLINE_INVALID_OR_EXPIRED")
        source_sha = _valid_sha256(request.expected_snapshot_sha256)
        nonce_sha = _valid_sha256(request.request_nonce_sha256)
        if not source_sha or not nonce_sha:
            return _blocked("REQUEST_HASH_BINDING_INVALID")
        if type(request.caps) is not residual.ResidualClosedIdentityRepairCapsV1:
            return _blocked("EXACT_REPAIR_CAPS_REQUIRED")

        plan = residual.build_residual_closed_identity_repair_plan_v1(
            request.registry_snapshot,
            expected_snapshot_sha256=source_sha,
            caps=request.caps,
        )
        if plan.get("ok") is not True:
            result = _blocked("RESIDUAL_REPAIR_PLAN_BLOCKED")
            result["planner_reasons"] = [str(item) for item in plan.get("reasons") or []]
            return result
        if not _plan_integral(plan, source_sha):
            return _blocked("RESIDUAL_REPAIR_PLAN_INTEGRITY_FAILED")

        actions = _sanitize_sequence(
            plan.get("actions"),
            allowed_keys=frozenset(
                {
                    "registry_index",
                    "record_sha256",
                    "field",
                    "action",
                    "classification",
                }
            ),
        )
        quarantine = _sanitize_sequence(
            plan.get("quarantine"),
            allowed_keys=frozenset(
                {
                    "registry_index",
                    "record_sha256",
                    "field",
                    "reason",
                    "delta_seconds",
                }
            ),
        )
        changed_paths = plan.get("changed_paths")
        summary = plan.get("summary")
        if (
            actions is None
            or quarantine is None
            or not isinstance(changed_paths, list)
            or any(not isinstance(path, str) for path in changed_paths)
            or not isinstance(summary, Mapping)
        ):
            return _blocked("RESIDUAL_REPAIR_PLAN_SANITIZATION_FAILED")
        sanitized_summary = {
            key: int(summary[key])
            for key in (
                "residual_record_count",
                "timestamp_aliases_archived",
                "status_aliases_archived",
                "quarantined_conflict_count",
                "quarantined_record_count",
                "modified_record_count",
            )
            if type(summary.get(key)) is int
        }
        if len(sanitized_summary) != 6:
            return _blocked("RESIDUAL_REPAIR_SUMMARY_INVALID")

        candidate_complete = bool(
            not quarantine
            and plan.get("status") == "OFFLINE_RESIDUAL_REPAIR_PLAN_COMPLETE"
        )
        expires_at = min(
            request.deadline_epoch,
            now_epoch + self._config.receipt_ttl_seconds,
        )
        caps_binding = _caps_binding(request.caps)
        receipt = {
            "receipt_version": PROTECTED_RESIDUAL_PREVIEW_RECEIPT_VERSION_V1,
            "contract_version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION,
            "contract_sha256": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256,
            "planner_contract_version": residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION,
            "planner_contract_sha256": residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256,
            "source_attestation": request.source_attestation,
            "source_snapshot_sha256": source_sha,
            "candidate_snapshot_sha256": plan["candidate_snapshot_sha256"],
            "plan_sha256": plan["plan_sha256"],
            "caps_binding_sha256": _sha256(caps_binding),
            "request_nonce_sha256": nonce_sha,
            "summary_sha256": _sha256(sanitized_summary),
            "actions_sha256": _sha256(actions),
            "quarantine_sha256": _sha256(quarantine),
            "changed_paths_sha256": _sha256(changed_paths),
            "issued_at_epoch": now_epoch,
            "expires_at_epoch": expires_at,
            "request_deadline_epoch": request.deadline_epoch,
            "preview_candidate_complete": candidate_complete,
            "repair_ready": False,
            "apply_allowed": False,
            "runtime_activation_allowed": False,
            "synthetic_only": True,
            "authority_key_id_sha256": self._authority.key_id_sha256,
            "receipt_hmac_sha256": "",
        }
        receipt["receipt_hmac_sha256"] = hmac.new(
            self._authority.key,
            _canonical_json(_receipt_payload(receipt)).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not protected_residual_preview_receipt_valid_v1(
            receipt,
            self._authority,
            now_epoch=now_epoch,
        ):
            return _blocked("PREVIEW_RECEIPT_SELF_VALIDATION_FAILED")

        result = _base_result()
        result.update(
            ok=True,
            status=(
                "PROTECTED_RESIDUAL_PREVIEW_PARTIAL_QUARANTINE"
                if quarantine
                else "PROTECTED_RESIDUAL_PREVIEW_CANDIDATE_COMPLETE"
            ),
            preview_available=True,
            preview_candidate_complete=candidate_complete,
            repair_ready=False,
            preview_receipt=receipt,
            summary=sanitized_summary,
            actions=actions,
            quarantine=quarantine,
            changed_paths=copy.deepcopy(changed_paths),
            reasons=[],
        )
        result["sanitized_preview_sha256"] = _sha256(
            {
                "summary": result["summary"],
                "actions": result["actions"],
                "quarantine": result["quarantine"],
                "changed_paths": result["changed_paths"],
                "preview_receipt": result["preview_receipt"],
            }
        )
        return result


_CONTRACT_DESCRIPTOR = {
    "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION,
    "planner_contract_sha256": residual.TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256,
    "preview_only": True,
    "default_off": True,
    "synthetic_only": True,
    "raw_snapshot_public": False,
    "candidate_registry_public": False,
    "receipt_authentication": "HMAC_SHA256_INJECTED_SYNTHETIC_AUTHORITY",
    "maximum_receipt_ttl_seconds": _MAX_RECEIPT_TTL_SECONDS,
    "maximum_request_deadline_seconds": _MAX_REQUEST_DEADLINE_SECONDS,
    "quarantine_policy": "REPAIR_READY_FALSE",
}
TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256 = (
    _sha256(_CONTRACT_DESCRIPTOR)
)


__all__ = [
    "DormantProtectedResidualPreviewConfigV1",
    "DormantProtectedResidualPreviewV1",
    "OFFLINE_PROTECTED_RESIDUAL_PREVIEW_SCOPE_ATTESTATION_V1",
    "PROTECTED_RESIDUAL_PREVIEW_RECEIPT_VERSION_V1",
    "ProtectedResidualPreviewRequestV1",
    "ProtectedSyntheticResidualPreviewAuthorityV1",
    "SYNTHETIC_IN_MEMORY_SOURCE_ATTESTATION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_PROTECTED_PREVIEW_OFFLINE_CONTRACT_V1_VERSION",
    "protected_residual_preview_receipt_valid_v1",
]
