"""Offline assembler for a non-applicable controlled C3 repair package.

The package binds a dormant controller receipt, a synthetic authenticated
authorization receipt and a synthetic preview receipt.  Assembly is
default-off, consumes each authorization receipt once in memory and never
exposes an apply or activation surface.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as authorization
import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1 as controller_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-REPAIR-PACKAGE-V1"
)

CONTROLLED_REPAIR_PACKAGE_VERSION_V1 = "C3_CONTROLLED_REPAIR_PACKAGE_OFFLINE_V1"
OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1 = "C3_CONTROLLED_REPAIR_PACKAGE_OFFLINE_ONLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PREVIEW_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "conflict_binding_sha256",
        "selected_source_paths",
        "gross_r_source_path",
        "gross_r_preservation_sha256",
        "changed_paths",
        "issued_at_epoch",
        "expires_at_epoch",
        "apply_allowed",
        "preview_receipt_sha256",
    }
)
_PREVIEW_RESULT_KEYS = frozenset(
    {
        "ok",
        "status",
        "synthetic_only",
        "preservation_verified",
        "gross_r_preservation_verified",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "no_order_sent",
        "preview_receipt",
    }
)
_CONTROLLER_RECEIPT_KEYS = frozenset(
    {
        "upstream_readiness_binding_receipt_sha256",
        "controller_binding_spec_sha256",
        "binding_plan_sha256",
        "binding_count",
        "writer_count",
        "synthetic_binding_allowed",
        "controller_apply_enabled",
        "apply_scope_attestation_present",
        "activation_receipt_consumed",
        "production_authorization_consumed",
        "production_dependencies_bound",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "binding_receipt_sha256",
    }
)
_AUTHORIZATION_RECEIPT_KEYS = frozenset(
    {
        "upstream_controller_binding_receipt_sha256",
        "authorization_envelope_sha256",
        "signature_sha256",
        "key_id_sha256",
        "nonce_sha256",
        "preview_receipt_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "authorized_action",
        "max_apply_count",
        "issued_at_epoch",
        "expires_at_epoch",
        "ttl_seconds",
        "synthetic_authorization_verified",
        "production_authorization_valid",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "authorization_receipt_sha256",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "package_version",
        "controller_binding_receipt_sha256",
        "authorization_receipt_sha256",
        "preview_receipt_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "assembled_at_epoch",
        "expires_at_epoch",
        "max_apply_count",
        "dormant",
        "default_off",
        "offline_only",
        "synthetic_only",
        "production_authorization_valid",
        "runtime_binding_satisfied",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "package_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "PACKAGE_IS_SYNTHETIC_OFFLINE_EVIDENCE_ONLY",
    "PREVIEW_IS_SYNTHETIC",
    "AUTHORIZATION_IS_NOT_A_PRODUCTION_AUTHORIZATION",
    "REPLAY_GUARD_IS_IN_MEMORY_ONLY",
    "CONTROLLER_APPLY_REMAINS_DEFAULT_OFF",
    "RUNTIME_BINDING_IS_NOT_SATISFIED",
    "PACKAGE_HAS_NO_APPLY_CALLABLE",
    "REAL_REGISTRY_IS_NOT_ACCESSED",
    "SEPARATE_PRODUCTION_PATCH_REQUIRED",
    "SEPARATE_PRODUCTION_AUTHORIZATION_REQUIRED",
    "LIVE_TRADING_REMAINS_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _receipt_sha256(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def controlled_repair_package_sha256_v1(manifest: Mapping[str, Any]) -> str:
    if not isinstance(manifest, Mapping):
        raise TypeError("manifest must be a mapping")
    return _stable_sha256(
        {key: value for key, value in manifest.items() if key != "package_sha256"}
    )


@dataclass(frozen=True)
class ControlledRepairPackageConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_package_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_package_ttl_seconds <= 300:
            raise ValueError("max_package_ttl_seconds must be between 1 and 300")


class InMemoryRepairPackageReplayGuardV1:
    """Consume authorization receipt digests atomically, never raw receipts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._expires_by_authorization_sha256: dict[str, int] = {}

    def consume(
        self, authorization_receipt_sha256: str, expires_at_epoch: int, now_epoch: int
    ) -> bool:
        digest = hashlib.sha256(
            authorization_receipt_sha256.encode("ascii")
        ).hexdigest()
        with self._lock:
            self._expires_by_authorization_sha256 = {
                item: expiry
                for item, expiry in self._expires_by_authorization_sha256.items()
                if expiry >= now_epoch
            }
            if digest in self._expires_by_authorization_sha256:
                return False
            self._expires_by_authorization_sha256[digest] = expires_at_epoch
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stored_authorization_digest_count": len(
                    self._expires_by_authorization_sha256
                ),
                "raw_authorization_receipt_stored": False,
                "durable": False,
                "synthetic_only": True,
            }


class ControlledRepairPackageAssemblerV1:
    def __init__(
        self,
        *,
        config: ControlledRepairPackageConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        replay_guard: InMemoryRepairPackageReplayGuardV1 | None = None,
    ) -> None:
        self._config = config or ControlledRepairPackageConfigV1()
        self._clock = clock
        self._replay_guard = replay_guard

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "package_contract_verified": False,
            "controller_binding_verified": False,
            "authorization_verified": False,
            "preview_verified": False,
            "cross_binding_verified": False,
            "freshness_verified": False,
            "replay_guard_verified": False,
            "package_assembled_offline": False,
            "production_authorization_valid": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "status": "C3_CONTROLLED_REPAIR_PACKAGE_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "reasons": [],
            "checks": {},
            "package_receipt": None,
        }

    @staticmethod
    def _check_controller(
        value: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
    ) -> str:
        receipt = value.get("binding_receipt")
        supplied = (
            _valid_sha256(receipt.get("binding_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "binding_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["controller_binding_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == controller_binding.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_CONTRACT_V1_VERSION
            and value.get("binding_contract_verified") is True
            and value.get("synthetic_binding_allowed") is True
            and value.get("runtime_binding_satisfied") is False
            and value.get("apply_allowed") is False
            and value.get("activation_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _CONTROLLER_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("controller_apply_enabled") is False
            and receipt.get("apply_scope_attestation_present") is False
            and receipt.get("activation_receipt_consumed") is False
            and receipt.get("production_authorization_consumed") is False
            and receipt.get("production_dependencies_bound") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
        )
        if not checks["controller_binding_receipt_valid"]:
            reasons.append("PACKAGE_CONTROLLER_BINDING_INVALID")
        return supplied

    @staticmethod
    def _check_authorization(
        value: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
    ) -> tuple[str, Mapping[str, Any] | None]:
        receipt = value.get("authorization_receipt")
        supplied = (
            _valid_sha256(receipt.get("authorization_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "authorization_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["synthetic_authorization_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == authorization.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION
            and value.get("authorization_contract_verified") is True
            and value.get("synthetic_authorization_verified") is True
            and value.get("production_authorization_valid") is False
            and value.get("runtime_binding_satisfied") is False
            and value.get("apply_allowed") is False
            and value.get("activation_allowed") is False
            and value.get("live_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _AUTHORIZATION_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("authorized_action") == authorization.AUTHORIZATION_ACTION_V1
            and type(receipt.get("max_apply_count")) is int
            and receipt.get("max_apply_count") == 1
            and receipt.get("synthetic_authorization_verified") is True
            and receipt.get("production_authorization_valid") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
        )
        if not checks["synthetic_authorization_receipt_valid"]:
            reasons.append("PACKAGE_AUTHORIZATION_INVALID")
        return supplied, receipt if isinstance(receipt, Mapping) else None

    @staticmethod
    def _check_preview(
        value: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
    ) -> tuple[str, Mapping[str, Any] | None]:
        receipt = value.get("preview_receipt")
        supplied = (
            _valid_sha256(receipt.get("preview_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "preview_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        selected = receipt.get("selected_source_paths") if isinstance(receipt, Mapping) else None
        changed = receipt.get("changed_paths") if isinstance(receipt, Mapping) else None
        checks["synthetic_preview_receipt_valid"] = bool(
            set(value) == _PREVIEW_RESULT_KEYS
            and value.get("ok") is True
            and value.get("status") == "REPAIR_PREVIEW_CANDIDATE_VERIFIED"
            and value.get("synthetic_only") is True
            and value.get("preservation_verified") is True
            and value.get("gross_r_preservation_verified") is True
            and value.get("real_registry_accessed") is False
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("write_executed") is False
            and value.get("no_order_sent") is True
            and isinstance(receipt, Mapping)
            and set(receipt) == _PREVIEW_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and _valid_sha256(receipt.get("source_registry_sha256"))
            and _valid_sha256(receipt.get("candidate_registry_sha256"))
            and receipt.get("source_registry_sha256")
            != receipt.get("candidate_registry_sha256")
            and _valid_sha256(receipt.get("conflict_binding_sha256"))
            and _valid_sha256(receipt.get("gross_r_preservation_sha256"))
            and selected
            == {
                "close_reason": "trade.metadata.exit_reason",
                "pnl_r": "trade.pnl_r",
            }
            and receipt.get("gross_r_source_path") == "trade.r_multiple"
            and isinstance(changed, list)
            and bool(changed)
            and changed == sorted(set(changed))
            and all(isinstance(path, str) and path for path in changed)
            and receipt.get("apply_allowed") is False
        )
        if not checks["synthetic_preview_receipt_valid"]:
            reasons.append("PACKAGE_PREVIEW_INVALID")
        return supplied, receipt if isinstance(receipt, Mapping) else None

    def assemble(
        self,
        controller_binding_result: Mapping[str, Any],
        authorization_result: Mapping[str, Any],
        preview_result: Mapping[str, Any],
        package_manifest: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            reasons.append("PACKAGE_ASSEMBLER_DEFAULT_OFF")
            result["status"] = "C3_CONTROLLED_REPAIR_PACKAGE_ASSEMBLER_DEFAULT_OFF"
            return result
        if self._config.scope_attestation != OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1:
            reasons.append("PACKAGE_ASSEMBLER_SCOPE_ATTESTATION_REQUIRED")
            return result
        values = (
            controller_binding_result,
            authorization_result,
            preview_result,
            package_manifest,
        )
        if not all(isinstance(value, Mapping) for value in values):
            reasons.append("PACKAGE_MAPPING_INPUTS_REQUIRED")
            return result
        try:
            controller = _canonical_copy(controller_binding_result)
            auth = _canonical_copy(authorization_result)
            preview = _canonical_copy(preview_result)
            manifest = _canonical_copy(package_manifest)
        except (TypeError, ValueError, OverflowError):
            reasons.append("PACKAGE_INPUT_NOT_CANONICALIZABLE")
            return result

        controller_sha = self._check_controller(controller, reasons, checks)
        auth_sha, auth_receipt = self._check_authorization(auth, reasons, checks)
        preview_sha, preview_receipt = self._check_preview(preview, reasons, checks)

        auth_upstream_sha = (
            auth_receipt.get("upstream_controller_binding_receipt_sha256")
            if isinstance(auth_receipt, Mapping)
            else None
        )
        checks["authorization_controller_cross_binding_exact"] = bool(
            controller_sha
            and auth_upstream_sha == controller_sha
        )
        preview_source = (
            preview_receipt.get("source_registry_sha256")
            if isinstance(preview_receipt, Mapping)
            else None
        )
        preview_candidate = (
            preview_receipt.get("candidate_registry_sha256")
            if isinstance(preview_receipt, Mapping)
            else None
        )
        preview_changed_sha = (
            _stable_sha256(preview_receipt.get("changed_paths"))
            if isinstance(preview_receipt, Mapping)
            else ""
        )
        checks["authorization_preview_cross_binding_exact"] = bool(
            isinstance(auth_receipt, Mapping)
            and auth_receipt.get("preview_receipt_sha256") == preview_sha
            and auth_receipt.get("source_registry_sha256") == preview_source
            and auth_receipt.get("candidate_registry_sha256") == preview_candidate
            and auth_receipt.get("changed_paths_sha256") == preview_changed_sha
        )
        for check in (
            "authorization_controller_cross_binding_exact",
            "authorization_preview_cross_binding_exact",
        ):
            if not checks[check]:
                reasons.append("PACKAGE_CROSS_BINDING_MISMATCH")

        now: int | None = None
        try:
            if not callable(self._clock):
                raise TypeError("clock missing")
            value = self._clock()
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("clock invalid")
            now = value
        except Exception:
            reasons.append("PACKAGE_CLOCK_UNAVAILABLE")
        auth_issued = auth_receipt.get("issued_at_epoch") if isinstance(auth_receipt, Mapping) else None
        auth_expires = auth_receipt.get("expires_at_epoch") if isinstance(auth_receipt, Mapping) else None
        preview_issued = preview_receipt.get("issued_at_epoch") if isinstance(preview_receipt, Mapping) else None
        preview_expires = preview_receipt.get("expires_at_epoch") if isinstance(preview_receipt, Mapping) else None
        time_values = (auth_issued, auth_expires, preview_issued, preview_expires)
        time_types_valid = all(
            isinstance(value, int) and not isinstance(value, bool) for value in time_values
        )
        effective_expiry = (
            min(auth_expires, preview_expires) if time_types_valid else None
        )
        checks["package_window_fresh_and_bounded"] = bool(
            now is not None
            and time_types_valid
            and auth_issued <= now < auth_expires
            and preview_issued <= now < preview_expires
            and auth_receipt.get("ttl_seconds") == auth_expires - auth_issued
            and 1 <= auth_expires - auth_issued <= 300
            and 1 <= preview_expires - preview_issued <= 300
            and effective_expiry is not None
            and 1 <= effective_expiry - now <= self._config.max_package_ttl_seconds
        )
        if not checks["package_window_fresh_and_bounded"]:
            reasons.append("PACKAGE_WINDOW_INVALID_OR_EXPIRED")

        supplied_package_sha = _valid_sha256(manifest.get("package_sha256"))
        checks["package_manifest_exact"] = bool(
            set(manifest) == _MANIFEST_KEYS
            and manifest.get("package_version") == CONTROLLED_REPAIR_PACKAGE_VERSION_V1
            and manifest.get("controller_binding_receipt_sha256") == controller_sha
            and manifest.get("authorization_receipt_sha256") == auth_sha
            and manifest.get("preview_receipt_sha256") == preview_sha
            and manifest.get("source_registry_sha256") == preview_source
            and manifest.get("candidate_registry_sha256") == preview_candidate
            and manifest.get("changed_paths_sha256") == preview_changed_sha
            and manifest.get("assembled_at_epoch") == now
            and manifest.get("expires_at_epoch") == effective_expiry
            and type(manifest.get("max_apply_count")) is int
            and manifest.get("max_apply_count") == 1
            and manifest.get("dormant") is True
            and manifest.get("default_off") is True
            and manifest.get("offline_only") is True
            and manifest.get("synthetic_only") is True
            and manifest.get("production_authorization_valid") is False
            and manifest.get("runtime_binding_satisfied") is False
            and manifest.get("apply_allowed") is False
            and manifest.get("activation_allowed") is False
            and manifest.get("live_allowed") is False
            and supplied_package_sha
            and hmac.compare_digest(
                supplied_package_sha,
                controlled_repair_package_sha256_v1(manifest),
            )
        )
        if not checks["package_manifest_exact"]:
            reasons.append("PACKAGE_MANIFEST_INVALID")

        pre_replay_reasons = sorted(set(str(reason) for reason in reasons))
        replay_consumed = False
        if not pre_replay_reasons:
            if type(self._replay_guard) is not InMemoryRepairPackageReplayGuardV1:
                reasons.append("PACKAGE_REPLAY_GUARD_UNAVAILABLE")
            else:
                replay_consumed = self._replay_guard.consume(
                    auth_sha, effective_expiry, now
                )
                if not replay_consumed:
                    reasons.append("PACKAGE_AUTHORIZATION_REPLAY_DETECTED")
        checks["authorization_receipt_consumed_once"] = replay_consumed

        reasons[:] = sorted(set(str(reason) for reason in reasons))
        if reasons or not checks or not all(checks.values()):
            return result

        receipt = {
            "package_sha256": supplied_package_sha,
            "controller_binding_receipt_sha256": controller_sha,
            "authorization_receipt_sha256": auth_sha,
            "preview_receipt_sha256": preview_sha,
            "source_registry_sha256": preview_source,
            "candidate_registry_sha256": preview_candidate,
            "changed_paths_sha256": preview_changed_sha,
            "assembled_at_epoch": now,
            "expires_at_epoch": effective_expiry,
            "max_apply_count": 1,
            "package_assembled_offline": True,
            "production_authorization_valid": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["package_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            {
                "ok": True,
                "package_contract_verified": True,
                "controller_binding_verified": True,
                "authorization_verified": True,
                "preview_verified": True,
                "cross_binding_verified": True,
                "freshness_verified": True,
                "replay_guard_verified": True,
                "package_assembled_offline": True,
                "status": "C3_CONTROLLED_REPAIR_PACKAGE_VALID_OFFLINE_NON_APPLICABLE",
                "reasons": [],
                "checks": checks,
                "package_receipt": receipt,
            }
        )
        return result


__all__ = [
    "CONTROLLED_REPAIR_PACKAGE_VERSION_V1",
    "ControlledRepairPackageAssemblerV1",
    "ControlledRepairPackageConfigV1",
    "InMemoryRepairPackageReplayGuardV1",
    "OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_V1_VERSION",
    "controlled_repair_package_sha256_v1",
]
