"""Dormant offline gateway contract for a protected CLOSED-repair request.

This module validates the complete synthetic chain immediately before a future
runtime invocation boundary.  It can project only a protected, non-serializable
envelope.  It has no controller import, invocation callable, runtime binding,
file access, environment access or production authority.
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

import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1 as conformance_module
import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as authorization_module
import trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1 as adapter_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-DORMANT-INVOCATION-GATEWAY-V1"
)

OFFLINE_INVOCATION_GATEWAY_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_DORMANT_INVOCATION_GATEWAY_OFFLINE_ONLY_V1"
)
INVOCATION_INTENT_VERSION_V1 = "C3_CLOSED_REPAIR_DORMANT_INVOCATION_INTENT_V1"

_APPLY_ACK_V1 = "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ENVELOPE_FIELDS = ("operation", "ack", "preview_receipt_sha256")
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
_ADAPTER_RECEIPT_KEYS = frozenset(
    {
        "package_receipt_sha256",
        "preview_instance_attestation_sha256",
        "apply_request_intent_sha256",
        "controller_instance_sha256",
        "reservation_token_sha256",
        "expires_at_epoch",
        "request_payload_field_count",
        "request_projected",
        "request_material_exposed",
        "same_instance_preview_verified_synthetic",
        "same_runtime_instance_verified",
        "apply_invocation_allowed",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "adapter_receipt_sha256",
    }
)
_CONFORMANCE_RECEIPT_KEYS = frozenset(
    {
        "operation_source_sha256",
        "route_source_sha256",
        "adapter_source_sha256",
        "apply_ack_sha256",
        "controller_request_fields",
        "adapter_request_fields",
        "protected_dto_fields",
        "route_request_fields",
        "route_operations",
        "direct_controller_schema_compatible",
        "http_route_payload_compatible",
        "deadline_semantics_aligned",
        "authorization_gateway_bound",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "semantic_snapshot_sha256",
        "conformance_receipt_sha256",
    }
)
_INTENT_KEYS = frozenset(
    {
        "intent_version",
        "conformance_receipt_sha256",
        "adapter_receipt_sha256",
        "authorization_receipt_sha256",
        "controller_instance_sha256",
        "reservation_token_sha256",
        "operation",
        "envelope_fields",
        "max_invocation_count",
        "serialization_requested",
        "controller_call_requested",
        "runtime_binding_requested",
        "intent_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "GATEWAY_IS_OFFLINE_AND_SYNTHETIC_ONLY",
    "AUTHORIZATION_IS_SYNTHETIC_AND_NON_PRODUCTION",
    "CONTROLLER_INSTANCE_IS_SYNTHETIC",
    "SAME_RUNTIME_INSTANCE_IS_NOT_VERIFIED",
    "CONTROLLER_DEADLINE_SEMANTICS_REMAIN_UNALIGNED",
    "CONTROLLER_DOES_NOT_CONSUME_PROTECTED_AUTHORITY_FIELDS",
    "GATEWAY_LEASE_IS_IN_MEMORY_ONLY",
    "ENVELOPE_IS_NOT_SERIALIZABLE",
    "CONTROLLER_INVOCATION_IS_FORBIDDEN",
    "RUNTIME_BINDING_IS_ABSENT",
    "SEPARATE_PRODUCTION_IMPLEMENTATION_AND_AUTHORIZATION_REQUIRED",
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


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _receipt_sha256(receipt: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != field_name}
    )


def dormant_invocation_intent_sha256_v1(intent: Mapping[str, Any]) -> str:
    if not isinstance(intent, Mapping):
        raise TypeError("intent must be a mapping")
    return _receipt_sha256(intent, "intent_sha256")


@dataclass(frozen=True)
class DormantInvocationGatewayConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_invocation_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_invocation_ttl_seconds <= 300:
            raise ValueError("max_invocation_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class SyntheticDormantControllerInstanceV1:
    controller_instance_sha256: str = field(repr=False)
    pending_preview_receipt_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    synthetic_only: bool = field(default=True, repr=False)
    real_controller_referenced: bool = field(default=False, repr=False)

    def __repr__(self) -> str:
        return "SyntheticDormantControllerInstanceV1(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedDormantInvocationEnvelopeV1:
    operation: str = field(repr=False)
    ack: str = field(repr=False)
    preview_receipt_sha256: str = field(repr=False)
    package_receipt_sha256: str = field(repr=False)
    authorization_receipt_sha256: str = field(repr=False)
    controller_instance_sha256: str = field(repr=False)
    reservation_token_sha256: str = field(repr=False)
    gateway_lease_token_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDormantInvocationEnvelopeV1(<protected>)"


@dataclass(frozen=True, repr=False)
class DormantInvocationLeaseV1:
    lease_token_sha256: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    state: str = field(default="RESERVED", repr=False)

    def __repr__(self) -> str:
        return "DormantInvocationLeaseV1(<protected>)"


class InMemoryDormantInvocationLeaseStoreV1:
    """Atomic one-shot synthetic lease store; abort is terminal."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}

    def reserve(
        self, binding_sha256: str, expires_at_epoch: int, now_epoch: int
    ) -> DormantInvocationLeaseV1 | None:
        binding = _valid_sha256(binding_sha256)
        if not (
            binding
            and type(expires_at_epoch) is int
            and type(now_epoch) is int
            and now_epoch < expires_at_epoch
        ):
            return None
        with self._lock:
            if binding in self._records:
                return None
            token = _stable_sha256(
                {
                    "binding_sha256": binding,
                    "expires_at_epoch": expires_at_epoch,
                    "now_epoch": now_epoch,
                    "purpose": "DORMANT_INVOCATION_LEASE_V1",
                }
            )
            self._records[binding] = {
                "lease_token_sha256": token,
                "expires_at_epoch": expires_at_epoch,
                "state": "RESERVED",
            }
            return DormantInvocationLeaseV1(token, binding, expires_at_epoch)

    def abort_without_invocation(self, lease: DormantInvocationLeaseV1) -> bool:
        if type(lease) is not DormantInvocationLeaseV1:
            return False
        with self._lock:
            record = self._records.get(lease.binding_sha256)
            if not (
                isinstance(record, Mapping)
                and record.get("state") == "RESERVED"
                and hmac.compare_digest(
                    str(record.get("lease_token_sha256") or ""),
                    lease.lease_token_sha256,
                )
            ):
                return False
            record["state"] = "ABORTED_WITHOUT_INVOCATION"
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for record in self._records.values():
                state = str(record.get("state") or "UNKNOWN")
                states[state] = states.get(state, 0) + 1
            return {
                "lease_count": len(self._records),
                "states": states,
                "durable": False,
                "raw_envelope_stored": False,
                "synthetic_only": True,
            }


class DormantInvocationGatewayV1:
    def __init__(
        self,
        *,
        config: DormantInvocationGatewayConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        lease_store: InMemoryDormantInvocationLeaseStoreV1 | None = None,
    ) -> None:
        self._config = config or DormantInvocationGatewayConfigV1()
        self._clock = clock
        self._lease_store = lease_store

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_DORMANT_INVOCATION_GATEWAY_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_V1_VERSION,
            "gateway_contract_verified": False,
            "static_conformance_verified": False,
            "adapter_verified": False,
            "authorization_verified_synthetic": False,
            "same_instance_preview_verified_synthetic": False,
            "same_runtime_instance_verified": False,
            "strict_deadline_verified": False,
            "http_envelope_projected": False,
            "lease_verified": False,
            "request_material_exposed": False,
            "serialization_allowed": False,
            "controller_invocation_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_imported": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "checks": {},
            "reasons": [],
            "protected_envelope": None,
            "invocation_lease": None,
            "gateway_receipt": None,
        }

    @staticmethod
    def _check_conformance(
        value: Mapping[str, Any], checks: dict[str, bool], reasons: list[str]
    ) -> tuple[str, Mapping[str, Any] | None]:
        receipt = value.get("conformance_receipt")
        supplied = (
            _valid_sha256(receipt.get("conformance_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "conformance_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        semantic_payload = (
            {
                key: item
                for key, item in receipt.items()
                if key not in {"semantic_snapshot_sha256", "conformance_receipt_sha256"}
            }
            if isinstance(receipt, Mapping)
            else {}
        )
        checks["static_conformance_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == conformance_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_APPLY_SCHEMA_STATIC_CONFORMANCE_V1_VERSION
            and value.get("static_conformance_verified") is True
            and value.get("drift_detected") is False
            and value.get("direct_controller_schema_compatible") is True
            and value.get("http_route_payload_compatible") is False
            and value.get("deadline_semantics_aligned") is False
            and value.get("authorization_gateway_bound") is False
            and value.get("runtime_binding_satisfied") is False
            and value.get("production_ready") is False
            and value.get("apply_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _CONFORMANCE_RECEIPT_KEYS
            and receipt.get("controller_request_fields")
            == ["ack", "preview_receipt_sha256"]
            and receipt.get("adapter_request_fields")
            == ["ack", "preview_receipt_sha256"]
            and receipt.get("route_request_fields") == ["operation"]
            and receipt.get("route_operations") == ["apply", "preview"]
            and all(
                _valid_sha256(receipt.get(field_name))
                for field_name in (
                    "operation_source_sha256",
                    "route_source_sha256",
                    "adapter_source_sha256",
                )
            )
            and receipt.get("apply_ack_sha256")
            == hashlib.sha256(_APPLY_ACK_V1.encode("utf-8")).hexdigest()
            and receipt.get("semantic_snapshot_sha256")
            == _stable_sha256(semantic_payload)
            and supplied
            and hmac.compare_digest(supplied, expected)
        )
        if not checks["static_conformance_receipt_valid"]:
            reasons.append("GATEWAY_STATIC_CONFORMANCE_INVALID_OR_DRIFTED")
        return supplied, receipt if isinstance(receipt, Mapping) else None

    @staticmethod
    def _check_adapter(
        value: Mapping[str, Any], checks: dict[str, bool], reasons: list[str]
    ) -> tuple[
        adapter_module.ProtectedDormantApplyRequestV1 | None,
        Mapping[str, Any] | None,
        str,
    ]:
        protected = value.get("protected_request")
        receipt = value.get("adapter_receipt")
        supplied = (
            _valid_sha256(receipt.get("adapter_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "adapter_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["dormant_adapter_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == adapter_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PACKAGE_APPLY_REQUEST_ADAPTER_V1_VERSION
            and value.get("adapter_contract_verified") is True
            and value.get("request_projected") is True
            and value.get("request_serialization_allowed") is False
            and value.get("apply_invocation_allowed") is False
            and value.get("runtime_binding_satisfied") is False
            and value.get("production_ready") is False
            and value.get("apply_allowed") is False
            and type(protected) is adapter_module.ProtectedDormantApplyRequestV1
            and isinstance(receipt, Mapping)
            and set(receipt) == _ADAPTER_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("request_payload_field_count") == 2
            and receipt.get("request_projected") is True
            and receipt.get("request_material_exposed") is False
            and receipt.get("same_runtime_instance_verified") is False
            and receipt.get("apply_invocation_allowed") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and protected.ack == _APPLY_ACK_V1
            and protected.preview_receipt_sha256
            == receipt.get("preview_receipt_sha256", protected.preview_receipt_sha256)
            and protected.package_receipt_sha256
            == receipt.get("package_receipt_sha256")
            and protected.authorization_receipt_sha256
            and protected.controller_instance_sha256
            == receipt.get("controller_instance_sha256")
            and protected.reservation_token_sha256
            == receipt.get("reservation_token_sha256")
            and protected.expires_at_epoch == receipt.get("expires_at_epoch")
        )
        if not checks["dormant_adapter_receipt_valid"]:
            reasons.append("GATEWAY_DORMANT_ADAPTER_INVALID")
        return (
            protected
            if type(protected) is adapter_module.ProtectedDormantApplyRequestV1
            else None,
            receipt if isinstance(receipt, Mapping) else None,
            supplied,
        )

    @staticmethod
    def _check_authorization(
        value: Mapping[str, Any],
        protected: adapter_module.ProtectedDormantApplyRequestV1 | None,
        checks: dict[str, bool],
        reasons: list[str],
    ) -> tuple[Mapping[str, Any] | None, str]:
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
            == authorization_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION
            and value.get("authorization_contract_verified") is True
            and value.get("upstream_controller_binding_verified") is True
            and value.get("signature_verified") is True
            and value.get("freshness_verified") is True
            and value.get("replay_guard_verified") is True
            and value.get("synthetic_authorization_verified") is True
            and value.get("apply_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _AUTHORIZATION_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("authorized_action")
            == authorization_module.AUTHORIZATION_ACTION_V1
            and receipt.get("max_apply_count") == 1
            and receipt.get("synthetic_authorization_verified") is True
            and receipt.get("production_authorization_valid") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and receipt.get("activation_allowed") is False
            and receipt.get("live_allowed") is False
            and protected is not None
            and protected.authorization_receipt_sha256 == supplied
            and protected.preview_receipt_sha256
            == receipt.get("preview_receipt_sha256")
        )
        if not checks["synthetic_authorization_receipt_valid"]:
            reasons.append("GATEWAY_SYNTHETIC_AUTHORIZATION_INVALID")
        return receipt if isinstance(receipt, Mapping) else None, supplied

    @staticmethod
    def _check_same_instance(
        owner: SyntheticDormantControllerInstanceV1,
        target: SyntheticDormantControllerInstanceV1,
        protected: adapter_module.ProtectedDormantApplyRequestV1 | None,
        checks: dict[str, bool],
        reasons: list[str],
    ) -> None:
        checks["same_synthetic_instance_identity_valid"] = bool(
            type(owner) is SyntheticDormantControllerInstanceV1
            and type(target) is SyntheticDormantControllerInstanceV1
            and owner is target
            and owner.synthetic_only is True
            and owner.real_controller_referenced is False
            and protected is not None
            and _valid_sha256(owner.controller_instance_sha256)
            == protected.controller_instance_sha256
            and owner.pending_preview_receipt_sha256
            == protected.preview_receipt_sha256
            and owner.expires_at_epoch == protected.expires_at_epoch
        )
        if not checks["same_synthetic_instance_identity_valid"]:
            reasons.append("GATEWAY_SAME_SYNTHETIC_INSTANCE_REQUIRED")

    @staticmethod
    def _check_intent(
        value: Mapping[str, Any],
        conformance_sha: str,
        adapter_sha: str,
        authorization_sha: str,
        protected: adapter_module.ProtectedDormantApplyRequestV1 | None,
        checks: dict[str, bool],
        reasons: list[str],
    ) -> str:
        supplied = _valid_sha256(value.get("intent_sha256"))
        expected = dormant_invocation_intent_sha256_v1(value)
        checks["invocation_intent_valid"] = bool(
            set(value) == _INTENT_KEYS
            and value.get("intent_version") == INVOCATION_INTENT_VERSION_V1
            and value.get("conformance_receipt_sha256") == conformance_sha
            and value.get("adapter_receipt_sha256") == adapter_sha
            and value.get("authorization_receipt_sha256") == authorization_sha
            and protected is not None
            and value.get("controller_instance_sha256")
            == protected.controller_instance_sha256
            and value.get("reservation_token_sha256")
            == protected.reservation_token_sha256
            and value.get("operation") == "apply"
            and value.get("envelope_fields") == list(_ENVELOPE_FIELDS)
            and value.get("max_invocation_count") == 1
            and value.get("serialization_requested") is False
            and value.get("controller_call_requested") is False
            and value.get("runtime_binding_requested") is False
            and supplied
            and hmac.compare_digest(supplied, expected)
        )
        if not checks["invocation_intent_valid"]:
            reasons.append("GATEWAY_INVOCATION_INTENT_INVALID")
        return supplied

    def prepare(
        self,
        *,
        static_conformance_result: Mapping[str, Any],
        adapter_result: Mapping[str, Any],
        authorization_result: Mapping[str, Any],
        preview_owner_instance: SyntheticDormantControllerInstanceV1,
        invocation_target_instance: SyntheticDormantControllerInstanceV1,
        invocation_intent: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            result.update(
                status="C3_DORMANT_INVOCATION_GATEWAY_DEFAULT_OFF",
                reasons=["GATEWAY_DEFAULT_OFF"],
            )
            return result
        if self._config.scope_attestation != OFFLINE_INVOCATION_GATEWAY_SCOPE_ATTESTATION_V1:
            result.update(
                status="C3_DORMANT_INVOCATION_GATEWAY_SCOPE_REQUIRED",
                reasons=["GATEWAY_OFFLINE_SCOPE_ATTESTATION_REQUIRED"],
            )
            return result
        mappings = (
            static_conformance_result,
            adapter_result,
            authorization_result,
            invocation_intent,
        )
        if not all(isinstance(value, Mapping) for value in mappings):
            result["reasons"] = ["GATEWAY_MAPPING_INPUTS_REQUIRED"]
            return result

        conformance_sha, _ = self._check_conformance(
            static_conformance_result, checks, reasons
        )
        protected, adapter_receipt, adapter_sha = self._check_adapter(
            adapter_result, checks, reasons
        )
        authorization_receipt, authorization_sha = self._check_authorization(
            authorization_result, protected, checks, reasons
        )
        self._check_same_instance(
            preview_owner_instance,
            invocation_target_instance,
            protected,
            checks,
            reasons,
        )
        intent_sha = self._check_intent(
            invocation_intent,
            conformance_sha,
            adapter_sha,
            authorization_sha,
            protected,
            checks,
            reasons,
        )

        now: int | None = None
        try:
            if not callable(self._clock):
                raise TypeError("clock unavailable")
            clock_value = self._clock()
            if type(clock_value) is not int:
                raise TypeError("clock invalid")
            now = clock_value
        except Exception:
            reasons.append("GATEWAY_CLOCK_UNAVAILABLE")

        protected_expiry = protected.expires_at_epoch if protected is not None else None
        authorization_expiry = (
            authorization_receipt.get("expires_at_epoch")
            if isinstance(authorization_receipt, Mapping)
            else None
        )
        instance_expiry = (
            preview_owner_instance.expires_at_epoch
            if type(preview_owner_instance) is SyntheticDormantControllerInstanceV1
            else None
        )
        expiry_values = (protected_expiry, authorization_expiry, instance_expiry)
        effective_expiry = (
            min(expiry_values)
            if all(type(value) is int for value in expiry_values)
            else None
        )
        checks["strict_effective_deadline_valid"] = bool(
            now is not None
            and type(effective_expiry) is int
            and now < effective_expiry
            and 1 <= effective_expiry - now
            <= self._config.max_invocation_ttl_seconds
        )
        if not checks["strict_effective_deadline_valid"]:
            reasons.append("GATEWAY_DEADLINE_INVALID_OR_EXPIRED")

        binding_sha = _stable_sha256(
            {
                "conformance_receipt_sha256": conformance_sha,
                "adapter_receipt_sha256": adapter_sha,
                "authorization_receipt_sha256": authorization_sha,
                "invocation_intent_sha256": intent_sha,
                "controller_instance_sha256": (
                    protected.controller_instance_sha256 if protected else ""
                ),
                "reservation_token_sha256": (
                    protected.reservation_token_sha256 if protected else ""
                ),
                "effective_expiry": effective_expiry,
            }
        )
        lease: DormantInvocationLeaseV1 | None = None
        pre_lease_reasons = sorted(set(reasons))
        if not pre_lease_reasons:
            if type(self._lease_store) is not InMemoryDormantInvocationLeaseStoreV1:
                reasons.append("GATEWAY_LEASE_STORE_UNAVAILABLE")
            else:
                lease = self._lease_store.reserve(binding_sha, effective_expiry, now)
                if lease is None:
                    reasons.append("GATEWAY_REPLAY_OR_DUPLICATE_DETECTED")
        checks["one_shot_invocation_lease_acquired"] = lease is not None

        reasons[:] = sorted(set(reasons))
        if reasons or not checks or not all(checks.values()):
            return result

        envelope = ProtectedDormantInvocationEnvelopeV1(
            operation="apply",
            ack=protected.ack,
            preview_receipt_sha256=protected.preview_receipt_sha256,
            package_receipt_sha256=protected.package_receipt_sha256,
            authorization_receipt_sha256=protected.authorization_receipt_sha256,
            controller_instance_sha256=protected.controller_instance_sha256,
            reservation_token_sha256=protected.reservation_token_sha256,
            gateway_lease_token_sha256=lease.lease_token_sha256,
            expires_at_epoch=effective_expiry,
        )
        receipt = {
            "conformance_receipt_sha256": conformance_sha,
            "adapter_receipt_sha256": adapter_sha,
            "authorization_receipt_sha256": authorization_sha,
            "invocation_intent_sha256": intent_sha,
            "controller_instance_sha256": protected.controller_instance_sha256,
            "preview_receipt_sha256": protected.preview_receipt_sha256,
            "reservation_token_sha256": protected.reservation_token_sha256,
            "gateway_lease_token_sha256": lease.lease_token_sha256,
            "binding_sha256": binding_sha,
            "expires_at_epoch": effective_expiry,
            "envelope_fields": list(_ENVELOPE_FIELDS),
            "same_instance_preview_verified_synthetic": True,
            "same_runtime_instance_verified": False,
            "authorization_verified_synthetic": True,
            "production_authorization_valid": False,
            "request_material_exposed": False,
            "serialization_allowed": False,
            "controller_invocation_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["gateway_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_DORMANT_INVOCATION_GATEWAY_VALID_OFFLINE_NON_EXECUTABLE",
            gateway_contract_verified=True,
            static_conformance_verified=True,
            adapter_verified=True,
            authorization_verified_synthetic=True,
            same_instance_preview_verified_synthetic=True,
            strict_deadline_verified=True,
            http_envelope_projected=True,
            lease_verified=True,
            reasons=[],
            protected_envelope=envelope,
            invocation_lease=lease,
            gateway_receipt=receipt,
        )
        return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_V1_VERSION",
    "OFFLINE_INVOCATION_GATEWAY_SCOPE_ATTESTATION_V1",
    "INVOCATION_INTENT_VERSION_V1",
    "DormantInvocationGatewayConfigV1",
    "SyntheticDormantControllerInstanceV1",
    "ProtectedDormantInvocationEnvelopeV1",
    "DormantInvocationLeaseV1",
    "InMemoryDormantInvocationLeaseStoreV1",
    "DormantInvocationGatewayV1",
    "dormant_invocation_intent_sha256_v1",
]
