"""Dormant adapter from a controlled repair package to a protected request.

The adapter projects the exact request shape required by the repair controller
without importing or invoking it.  It accepts only synthetic, default-off
evidence, reserves each package once in memory and exposes no serialization,
runtime installation, apply or activation callable.
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

import trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_v1 as package_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PACKAGE-APPLY-REQUEST-ADAPTER-V1"
)

PREVIEW_INSTANCE_ATTESTATION_VERSION_V1 = (
    "C3_DORMANT_PREVIEW_INSTANCE_ATTESTATION_V1"
)
APPLY_REQUEST_INTENT_VERSION_V1 = "C3_DORMANT_APPLY_REQUEST_INTENT_V1"
OFFLINE_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_PACKAGE_APPLY_REQUEST_ADAPTER_OFFLINE_ONLY_V1"
)

_APPLY_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_RECEIPT_KEYS = frozenset(
    {
        "package_sha256",
        "controller_binding_receipt_sha256",
        "authorization_receipt_sha256",
        "preview_receipt_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "assembled_at_epoch",
        "expires_at_epoch",
        "max_apply_count",
        "package_assembled_offline",
        "production_authorization_valid",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "package_receipt_sha256",
    }
)
_INSTANCE_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version",
        "controller_instance_sha256",
        "preview_receipt_sha256",
        "package_receipt_sha256",
        "pending_preview_present",
        "pending_preview_same_instance",
        "controller_apply_enabled",
        "apply_scope_attested",
        "expires_at_epoch",
        "synthetic_only",
        "real_controller_referenced",
        "attestation_sha256",
    }
)
_INTENT_KEYS = frozenset(
    {
        "intent_version",
        "package_receipt_sha256",
        "preview_instance_attestation_sha256",
        "operation",
        "request_payload_fields",
        "apply_ack_sha256",
        "max_apply_count",
        "apply_invocation_requested",
        "serialization_allowed",
        "runtime_adapter_bound",
        "intent_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "ADAPTER_IS_SYNTHETIC_OFFLINE_ONLY",
    "PACKAGE_PRODUCTION_AUTHORIZATION_IS_FALSE",
    "CONTROLLER_APPLY_IS_DISABLED",
    "APPLY_SCOPE_ATTESTATION_IS_ABSENT",
    "REAL_CONTROLLER_INSTANCE_IS_NOT_REFERENCED",
    "PENDING_PREVIEW_IDENTITY_IS_SYNTHETIC",
    "RESERVATION_STORE_IS_IN_MEMORY_ONLY",
    "PROTECTED_REQUEST_IS_NOT_SERIALIZABLE",
    "APPLY_INVOCATION_IS_FORBIDDEN",
    "RUNTIME_ADAPTER_IS_NOT_BOUND",
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


def preview_instance_attestation_sha256_v1(
    attestation: Mapping[str, Any],
) -> str:
    if not isinstance(attestation, Mapping):
        raise TypeError("attestation must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in attestation.items()
            if key != "attestation_sha256"
        }
    )


def apply_request_intent_sha256_v1(intent: Mapping[str, Any]) -> str:
    if not isinstance(intent, Mapping):
        raise TypeError("intent must be a mapping")
    return _stable_sha256(
        {key: value for key, value in intent.items() if key != "intent_sha256"}
    )


@dataclass(frozen=True)
class DormantApplyRequestAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_request_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_request_ttl_seconds <= 300:
            raise ValueError("max_request_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedDormantApplyRequestV1:
    ack: str = field(repr=False)
    preview_receipt_sha256: str = field(repr=False)
    package_receipt_sha256: str = field(repr=False)
    authorization_receipt_sha256: str = field(repr=False)
    controller_instance_sha256: str = field(repr=False)
    reservation_token_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDormantApplyRequestV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProjectedApplyReservationV1:
    reservation_token_sha256: str = field(repr=False)
    package_receipt_sha256: str = field(repr=False)
    controller_instance_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    state: str = field(default="RESERVED", repr=False)

    def __repr__(self) -> str:
        return "ProjectedApplyReservationV1(<protected>)"


class InMemoryProjectedApplyReservationStoreV1:
    """Atomic synthetic reservation store; terminal aborts cannot be reused."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records_by_package_sha256: dict[str, dict[str, Any]] = {}

    def reserve(
        self,
        package_receipt_sha256: str,
        controller_instance_sha256: str,
        expires_at_epoch: int,
        now_epoch: int,
    ) -> ProjectedApplyReservationV1 | None:
        if not (
            _valid_sha256(package_receipt_sha256)
            and _valid_sha256(controller_instance_sha256)
            and type(expires_at_epoch) is int
            and type(now_epoch) is int
            and now_epoch < expires_at_epoch
        ):
            return None
        with self._lock:
            if package_receipt_sha256 in self._records_by_package_sha256:
                return None
            token = _stable_sha256(
                {
                    "kind": "C3_PROJECTED_APPLY_RESERVATION_V1",
                    "package_receipt_sha256": package_receipt_sha256,
                    "controller_instance_sha256": controller_instance_sha256,
                    "expires_at_epoch": expires_at_epoch,
                }
            )
            record = {
                "reservation_token_sha256": token,
                "controller_instance_sha256": controller_instance_sha256,
                "expires_at_epoch": expires_at_epoch,
                "state": "RESERVED",
            }
            self._records_by_package_sha256[package_receipt_sha256] = record
            return ProjectedApplyReservationV1(
                reservation_token_sha256=token,
                package_receipt_sha256=package_receipt_sha256,
                controller_instance_sha256=controller_instance_sha256,
                expires_at_epoch=expires_at_epoch,
            )

    def abort_without_invocation(
        self, reservation: ProjectedApplyReservationV1
    ) -> bool:
        if type(reservation) is not ProjectedApplyReservationV1:
            return False
        with self._lock:
            record = self._records_by_package_sha256.get(
                reservation.package_receipt_sha256
            )
            if not (
                isinstance(record, Mapping)
                and record.get("state") == "RESERVED"
                and hmac.compare_digest(
                    str(record.get("reservation_token_sha256") or ""),
                    reservation.reservation_token_sha256,
                )
            ):
                return False
            record["state"] = "ABORTED_WITHOUT_INVOCATION"
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for record in self._records_by_package_sha256.values():
                state = str(record.get("state") or "UNKNOWN")
                states[state] = states.get(state, 0) + 1
            return {
                "reservation_count": len(self._records_by_package_sha256),
                "states": states,
                "raw_package_receipt_stored": False,
                "durable": False,
                "synthetic_only": True,
            }


class DormantPackageApplyRequestAdapterV1:
    def __init__(
        self,
        *,
        config: DormantApplyRequestAdapterConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        reservation_store: InMemoryProjectedApplyReservationStoreV1 | None = None,
    ) -> None:
        self._config = config or DormantApplyRequestAdapterConfigV1()
        self._clock = clock
        self._reservation_store = reservation_store

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "adapter_contract_verified": False,
            "package_verified": False,
            "same_instance_preview_verified_synthetic": False,
            "same_runtime_instance_verified": False,
            "deadline_verified": False,
            "reservation_verified": False,
            "request_projected": False,
            "request_serialization_allowed": False,
            "apply_invocation_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "status": "C3_PACKAGE_APPLY_REQUEST_ADAPTER_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_V1_VERSION,
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
            "protected_request": None,
            "reservation": None,
            "adapter_receipt": None,
        }

    @staticmethod
    def _check_package(
        value: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
    ) -> tuple[str, Mapping[str, Any] | None]:
        receipt = value.get("package_receipt")
        supplied = (
            _valid_sha256(receipt.get("package_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "package_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["controlled_package_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == package_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_REPAIR_PACKAGE_V1_VERSION
            and value.get("package_contract_verified") is True
            and value.get("package_assembled_offline") is True
            and value.get("production_authorization_valid") is False
            and value.get("runtime_binding_satisfied") is False
            and value.get("apply_allowed") is False
            and value.get("activation_allowed") is False
            and value.get("live_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _PACKAGE_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("package_assembled_offline") is True
            and receipt.get("production_authorization_valid") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
            and type(receipt.get("max_apply_count")) is int
            and receipt.get("max_apply_count") == 1
            and _valid_sha256(receipt.get("preview_receipt_sha256"))
            and _valid_sha256(receipt.get("authorization_receipt_sha256"))
        )
        if not checks["controlled_package_receipt_valid"]:
            reasons.append("APPLY_ADAPTER_PACKAGE_INVALID")
        return supplied, receipt if isinstance(receipt, Mapping) else None

    @staticmethod
    def _check_instance(
        value: Mapping[str, Any],
        package_sha: str,
        package_receipt: Mapping[str, Any] | None,
        reasons: list[str],
        checks: dict[str, bool],
    ) -> tuple[str, str, int | None]:
        supplied = _valid_sha256(value.get("attestation_sha256"))
        expected = preview_instance_attestation_sha256_v1(value)
        controller_sha = _valid_sha256(value.get("controller_instance_sha256"))
        expiry = value.get("expires_at_epoch")
        checks["preview_instance_attestation_valid"] = bool(
            set(value) == _INSTANCE_ATTESTATION_KEYS
            and value.get("attestation_version")
            == PREVIEW_INSTANCE_ATTESTATION_VERSION_V1
            and supplied
            and hmac.compare_digest(supplied, expected)
            and controller_sha
            and isinstance(package_receipt, Mapping)
            and value.get("preview_receipt_sha256")
            == package_receipt.get("preview_receipt_sha256")
            and value.get("package_receipt_sha256") == package_sha
            and value.get("pending_preview_present") is True
            and value.get("pending_preview_same_instance") is True
            and value.get("controller_apply_enabled") is False
            and value.get("apply_scope_attested") is False
            and type(expiry) is int
            and expiry == package_receipt.get("expires_at_epoch")
            and value.get("synthetic_only") is True
            and value.get("real_controller_referenced") is False
        )
        if not checks["preview_instance_attestation_valid"]:
            reasons.append("APPLY_ADAPTER_PREVIEW_INSTANCE_ATTESTATION_INVALID")
        return supplied, controller_sha, expiry if type(expiry) is int else None

    @staticmethod
    def _check_intent(
        value: Mapping[str, Any],
        package_sha: str,
        instance_attestation_sha: str,
        reasons: list[str],
        checks: dict[str, bool],
    ) -> str:
        supplied = _valid_sha256(value.get("intent_sha256"))
        expected = apply_request_intent_sha256_v1(value)
        checks["apply_request_intent_valid"] = bool(
            set(value) == _INTENT_KEYS
            and value.get("intent_version") == APPLY_REQUEST_INTENT_VERSION_V1
            and value.get("package_receipt_sha256") == package_sha
            and value.get("preview_instance_attestation_sha256")
            == instance_attestation_sha
            and value.get("operation") == "PROJECT_DORMANT_APPLY_REQUEST"
            and value.get("request_payload_fields")
            == ["ack", "preview_receipt_sha256"]
            and value.get("apply_ack_sha256")
            == hashlib.sha256(_APPLY_ACK_V1.encode("utf-8")).hexdigest()
            and type(value.get("max_apply_count")) is int
            and value.get("max_apply_count") == 1
            and value.get("apply_invocation_requested") is False
            and value.get("serialization_allowed") is False
            and value.get("runtime_adapter_bound") is False
            and supplied
            and hmac.compare_digest(supplied, expected)
        )
        if not checks["apply_request_intent_valid"]:
            reasons.append("APPLY_ADAPTER_REQUEST_INTENT_INVALID")
        return supplied

    def prepare(
        self,
        controlled_package_result: Mapping[str, Any],
        preview_instance_attestation: Mapping[str, Any],
        apply_request_intent: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            reasons.append("APPLY_ADAPTER_DEFAULT_OFF")
            result["status"] = "C3_PACKAGE_APPLY_REQUEST_ADAPTER_DEFAULT_OFF"
            return result
        if self._config.scope_attestation != OFFLINE_ADAPTER_SCOPE_ATTESTATION_V1:
            reasons.append("APPLY_ADAPTER_SCOPE_ATTESTATION_REQUIRED")
            return result
        values = (
            controlled_package_result,
            preview_instance_attestation,
            apply_request_intent,
        )
        if not all(isinstance(value, Mapping) for value in values):
            reasons.append("APPLY_ADAPTER_MAPPING_INPUTS_REQUIRED")
            return result
        try:
            package = _canonical_copy(controlled_package_result)
            instance = _canonical_copy(preview_instance_attestation)
            intent = _canonical_copy(apply_request_intent)
        except (TypeError, ValueError, OverflowError):
            reasons.append("APPLY_ADAPTER_INPUT_NOT_CANONICALIZABLE")
            return result

        package_sha, package_receipt = self._check_package(package, reasons, checks)
        instance_sha, controller_sha, expiry = self._check_instance(
            instance, package_sha, package_receipt, reasons, checks
        )
        intent_sha = self._check_intent(
            intent, package_sha, instance_sha, reasons, checks
        )

        now: int | None = None
        try:
            if not callable(self._clock):
                raise TypeError("clock missing")
            value = self._clock()
            if type(value) is not int:
                raise TypeError("clock invalid")
            now = value
        except Exception:
            reasons.append("APPLY_ADAPTER_CLOCK_UNAVAILABLE")
        assembled = (
            package_receipt.get("assembled_at_epoch")
            if isinstance(package_receipt, Mapping)
            else None
        )
        checks["strict_request_deadline_valid"] = bool(
            now is not None
            and type(assembled) is int
            and type(expiry) is int
            and assembled <= now < expiry
            and 1 <= expiry - now <= self._config.max_request_ttl_seconds
        )
        if not checks["strict_request_deadline_valid"]:
            reasons.append("APPLY_ADAPTER_DEADLINE_INVALID_OR_EXPIRED")

        reservation: ProjectedApplyReservationV1 | None = None
        pre_reservation_reasons = sorted(set(str(reason) for reason in reasons))
        if not pre_reservation_reasons:
            if (
                type(self._reservation_store)
                is not InMemoryProjectedApplyReservationStoreV1
            ):
                reasons.append("APPLY_ADAPTER_RESERVATION_STORE_UNAVAILABLE")
            else:
                reservation = self._reservation_store.reserve(
                    package_sha, controller_sha, expiry, now
                )
                if reservation is None:
                    reasons.append("APPLY_ADAPTER_PACKAGE_ALREADY_RESERVED")
        checks["projected_reservation_acquired"] = reservation is not None

        reasons[:] = sorted(set(str(reason) for reason in reasons))
        if reasons or not checks or not all(checks.values()):
            return result

        protected = ProtectedDormantApplyRequestV1(
            ack=_APPLY_ACK_V1,
            preview_receipt_sha256=package_receipt["preview_receipt_sha256"],
            package_receipt_sha256=package_sha,
            authorization_receipt_sha256=package_receipt[
                "authorization_receipt_sha256"
            ],
            controller_instance_sha256=controller_sha,
            reservation_token_sha256=reservation.reservation_token_sha256,
            expires_at_epoch=expiry,
        )
        receipt = {
            "package_receipt_sha256": package_sha,
            "preview_instance_attestation_sha256": instance_sha,
            "apply_request_intent_sha256": intent_sha,
            "controller_instance_sha256": controller_sha,
            "reservation_token_sha256": reservation.reservation_token_sha256,
            "expires_at_epoch": expiry,
            "request_payload_field_count": 2,
            "request_projected": True,
            "request_material_exposed": False,
            "same_instance_preview_verified_synthetic": True,
            "same_runtime_instance_verified": False,
            "apply_invocation_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["adapter_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            {
                "ok": True,
                "adapter_contract_verified": True,
                "package_verified": True,
                "same_instance_preview_verified_synthetic": True,
                "deadline_verified": True,
                "reservation_verified": True,
                "request_projected": True,
                "status": "C3_PACKAGE_APPLY_REQUEST_ADAPTER_VALID_OFFLINE_DORMANT",
                "reasons": [],
                "checks": checks,
                "protected_request": protected,
                "reservation": reservation,
                "adapter_receipt": receipt,
            }
        )
        return result


__all__ = [
    "APPLY_REQUEST_INTENT_VERSION_V1",
    "DormantApplyRequestAdapterConfigV1",
    "DormantPackageApplyRequestAdapterV1",
    "InMemoryProjectedApplyReservationStoreV1",
    "OFFLINE_ADAPTER_SCOPE_ATTESTATION_V1",
    "PREVIEW_INSTANCE_ATTESTATION_VERSION_V1",
    "ProjectedApplyReservationV1",
    "ProtectedDormantApplyRequestV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_V1_VERSION",
    "apply_request_intent_sha256_v1",
    "preview_instance_attestation_sha256_v1",
]
