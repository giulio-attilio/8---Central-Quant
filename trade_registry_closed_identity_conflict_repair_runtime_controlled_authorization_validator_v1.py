"""Default-off verifier for a future one-shot C3 repair authorization.

The verifier accepts only injected keys, clocks and an in-memory replay guard.
Successful verification proves a synthetic authorization envelope only; it
never enables the repair controller, runtime activation, Live or order flow.
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

import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1 as controller_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-AUTHORIZATION-VALIDATOR-V1"
)

AUTHORIZATION_ENVELOPE_VERSION_V1 = "C3_CLOSED_REPAIR_ONE_SHOT_AUTHORIZATION_V1"
AUTHORIZATION_ACTION_V1 = "C3_CLOSED_IDENTITY_REPAIR_APPLY_ONCE"
OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_AUTHORIZATION_VALIDATOR_OFFLINE_ONLY_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KEY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
_ENVELOPE_KEYS = frozenset(
    {
        "authorization_version",
        "algorithm",
        "key_id",
        "nonce",
        "issued_at_epoch",
        "expires_at_epoch",
        "action",
        "upstream_controller_binding_receipt_sha256",
        "preview_receipt_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "max_apply_count",
        "repair_apply_requested",
        "writer_coordination_window_requested",
        "runtime_activation_requested",
        "live_requested",
        "order_submission_authorized",
        "signature",
    }
)
_PRODUCTION_BLOCKERS = (
    "AUTHORIZATION_IS_SYNTHETIC_OFFLINE_EVIDENCE_ONLY",
    "SYNTHETIC_KEY_IS_NOT_A_PRODUCTION_CREDENTIAL",
    "PRODUCTION_KEY_RESOLVER_IS_NOT_BOUND",
    "DURABLE_REPLAY_STORE_IS_NOT_BOUND",
    "REAL_PREVIEW_RECEIPT_IS_NOT_CONSUMED",
    "REAL_REGISTRY_HASHES_ARE_NOT_CONSUMED",
    "CONTROLLER_APPLY_REMAINS_DEFAULT_OFF",
    "RUNTIME_BINDING_IS_NOT_SATISFIED",
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


def authorization_signing_payload_v1(envelope: Mapping[str, Any]) -> bytes:
    if not isinstance(envelope, Mapping):
        raise TypeError("envelope must be a mapping")
    return _canonical_json(
        {key: value for key, value in envelope.items() if key != "signature"}
    ).encode("utf-8")


@dataclass(frozen=True)
class ControlledAuthorizationValidatorConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_ttl_seconds: int = 300
    max_clock_skew_seconds: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.max_ttl_seconds <= 300:
            raise ValueError("max_ttl_seconds must be between 1 and 300")
        if not 0 <= self.max_clock_skew_seconds <= 30:
            raise ValueError("max_clock_skew_seconds must be between 0 and 30")


class InMemoryAuthorizationReplayGuardV1:
    """Thread-safe synthetic nonce guard that stores nonce digests only."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._expires_by_nonce_sha256: dict[str, int] = {}

    def consume(self, nonce: str, expires_at_epoch: int, now_epoch: int) -> bool:
        nonce_sha256 = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        with self._lock:
            self._expires_by_nonce_sha256 = {
                digest: expiry
                for digest, expiry in self._expires_by_nonce_sha256.items()
                if expiry >= now_epoch
            }
            if nonce_sha256 in self._expires_by_nonce_sha256:
                return False
            self._expires_by_nonce_sha256[nonce_sha256] = expires_at_epoch
            return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "stored_nonce_digest_count": len(self._expires_by_nonce_sha256),
                "raw_nonce_stored": False,
                "durable": False,
                "synthetic_only": True,
            }


class ControlledAuthorizationValidatorV1:
    """Verify one signed intent while permanently denying real application."""

    def __init__(
        self,
        *,
        config: ControlledAuthorizationValidatorConfigV1 | None = None,
        key_resolver: Callable[[str], bytes] | None = None,
        clock: Callable[[], int] | None = None,
        replay_guard: InMemoryAuthorizationReplayGuardV1 | None = None,
    ) -> None:
        self._config = config or ControlledAuthorizationValidatorConfigV1()
        self._key_resolver = key_resolver
        self._clock = clock
        self._replay_guard = replay_guard

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "authorization_contract_verified": False,
            "upstream_controller_binding_verified": False,
            "signature_verified": False,
            "freshness_verified": False,
            "replay_guard_verified": False,
            "synthetic_authorization_verified": False,
            "production_authorization_valid": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "status": "C3_CONTROLLED_AUTHORIZATION_VALIDATION_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "reasons": [],
            "checks": {},
            "authorization_receipt": None,
        }

    @staticmethod
    def _check_upstream(
        upstream: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
    ) -> str:
        receipt = upstream.get("binding_receipt")
        supplied = (
            _valid_sha256(receipt.get("binding_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _stable_sha256(
                {
                    key: value
                    for key, value in receipt.items()
                    if key != "binding_receipt_sha256"
                }
            )
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["upstream_controller_binding_receipt_valid"] = bool(
            upstream.get("ok") is True
            and upstream.get("version")
            == controller_binding.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_CONTRACT_V1_VERSION
            and upstream.get("binding_contract_verified") is True
            and upstream.get("synthetic_binding_allowed") is True
            and upstream.get("runtime_binding_satisfied") is False
            and upstream.get("production_ready") is False
            and upstream.get("apply_allowed") is False
            and upstream.get("activation_allowed") is False
            and upstream.get("live_allowed") is False
            and isinstance(receipt, Mapping)
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("binding_count") == 3
            and receipt.get("controller_apply_enabled") is False
            and receipt.get("activation_receipt_consumed") is False
            and receipt.get("production_authorization_consumed") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("apply_allowed") is False
        )
        if not checks["upstream_controller_binding_receipt_valid"]:
            reasons.append("AUTHORIZATION_UPSTREAM_CONTROLLER_BINDING_INVALID")
        return supplied

    def verify(
        self,
        controller_binding_result: Mapping[str, Any],
        authorization_envelope: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            reasons.append("AUTHORIZATION_VALIDATOR_DEFAULT_OFF")
            result["status"] = "C3_CONTROLLED_AUTHORIZATION_VALIDATOR_DEFAULT_OFF"
            return result
        if (
            self._config.scope_attestation
            != OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1
        ):
            reasons.append("AUTHORIZATION_VALIDATOR_SCOPE_ATTESTATION_REQUIRED")
            return result
        if not isinstance(controller_binding_result, Mapping) or not isinstance(
            authorization_envelope, Mapping
        ):
            reasons.append("AUTHORIZATION_MAPPING_INPUTS_REQUIRED")
            return result
        try:
            upstream = _canonical_copy(controller_binding_result)
            envelope = _canonical_copy(authorization_envelope)
        except (TypeError, ValueError, OverflowError):
            reasons.append("AUTHORIZATION_INPUT_NOT_CANONICALIZABLE")
            return result

        upstream_sha = self._check_upstream(upstream, reasons, checks)
        checks["authorization_envelope_exact"] = set(envelope) == _ENVELOPE_KEYS
        if not checks["authorization_envelope_exact"]:
            reasons.append("AUTHORIZATION_ENVELOPE_FIELDS_INVALID")

        key_id = str(envelope.get("key_id") or "")
        nonce = str(envelope.get("nonce") or "")
        signature = _valid_sha256(envelope.get("signature"))
        hash_fields = (
            "preview_receipt_sha256",
            "source_registry_sha256",
            "candidate_registry_sha256",
            "changed_paths_sha256",
        )
        checks["authorization_scope_exact"] = bool(
            envelope.get("authorization_version") == AUTHORIZATION_ENVELOPE_VERSION_V1
            and envelope.get("algorithm") == "HMAC-SHA-256"
            and _KEY_ID_RE.fullmatch(key_id)
            and _NONCE_RE.fullmatch(nonce)
            and envelope.get("action") == AUTHORIZATION_ACTION_V1
            and envelope.get("upstream_controller_binding_receipt_sha256")
            == upstream_sha
            and all(_valid_sha256(envelope.get(field)) for field in hash_fields)
            and type(envelope.get("max_apply_count")) is int
            and envelope.get("max_apply_count") == 1
            and envelope.get("repair_apply_requested") is True
            and envelope.get("writer_coordination_window_requested") is True
            and envelope.get("runtime_activation_requested") is False
            and envelope.get("live_requested") is False
            and envelope.get("order_submission_authorized") is False
        )
        if not checks["authorization_scope_exact"]:
            reasons.append("AUTHORIZATION_SCOPE_INVALID")

        issued = envelope.get("issued_at_epoch")
        expires = envelope.get("expires_at_epoch")
        now: int | None = None
        try:
            if not callable(self._clock):
                raise TypeError("clock missing")
            clock_value = self._clock()
            if isinstance(clock_value, bool) or not isinstance(clock_value, int):
                raise TypeError("clock invalid")
            now = clock_value
        except Exception:
            reasons.append("AUTHORIZATION_CLOCK_UNAVAILABLE")
        timestamps_valid = bool(
            now is not None
            and not isinstance(issued, bool)
            and not isinstance(expires, bool)
            and isinstance(issued, int)
            and isinstance(expires, int)
            and issued <= now + self._config.max_clock_skew_seconds
            and now < expires
            and 1 <= expires - issued <= self._config.max_ttl_seconds
        )
        checks["authorization_window_fresh"] = timestamps_valid
        if not timestamps_valid:
            reasons.append("AUTHORIZATION_WINDOW_INVALID_OR_EXPIRED")

        key: bytes | None = None
        if not reasons:
            if not callable(self._key_resolver):
                reasons.append("AUTHORIZATION_KEY_RESOLVER_UNAVAILABLE")
            else:
                try:
                    resolved = self._key_resolver(key_id)
                    if type(resolved) is not bytes or len(resolved) < 32:
                        raise ValueError("key invalid")
                    key = resolved
                except Exception:
                    reasons.append("AUTHORIZATION_KEY_RESOLUTION_FAILED")
        expected_signature = (
            hmac.new(key, authorization_signing_payload_v1(envelope), hashlib.sha256).hexdigest()
            if key is not None
            else ""
        )
        checks["authorization_signature_valid"] = bool(
            signature
            and expected_signature
            and hmac.compare_digest(signature, expected_signature)
        )
        if not checks["authorization_signature_valid"] and key is not None:
            reasons.append("AUTHORIZATION_SIGNATURE_INVALID")

        pre_replay_reasons = sorted(set(str(reason) for reason in reasons))
        replay_consumed = False
        if not pre_replay_reasons:
            if type(self._replay_guard) is not InMemoryAuthorizationReplayGuardV1:
                reasons.append("AUTHORIZATION_REPLAY_GUARD_UNAVAILABLE")
            else:
                replay_consumed = self._replay_guard.consume(nonce, expires, now)
                if not replay_consumed:
                    reasons.append("AUTHORIZATION_REPLAY_DETECTED")
        checks["authorization_nonce_consumed_once"] = replay_consumed

        reasons[:] = sorted(set(str(reason) for reason in reasons))
        if reasons or not checks or not all(checks.values()):
            return result

        receipt = {
            "upstream_controller_binding_receipt_sha256": upstream_sha,
            "authorization_envelope_sha256": _stable_sha256(envelope),
            "signature_sha256": hashlib.sha256(signature.encode("ascii")).hexdigest(),
            "key_id_sha256": hashlib.sha256(key_id.encode("utf-8")).hexdigest(),
            "nonce_sha256": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
            "preview_receipt_sha256": envelope["preview_receipt_sha256"],
            "source_registry_sha256": envelope["source_registry_sha256"],
            "candidate_registry_sha256": envelope["candidate_registry_sha256"],
            "changed_paths_sha256": envelope["changed_paths_sha256"],
            "authorized_action": AUTHORIZATION_ACTION_V1,
            "max_apply_count": 1,
            "issued_at_epoch": issued,
            "expires_at_epoch": expires,
            "ttl_seconds": expires - issued,
            "synthetic_authorization_verified": True,
            "production_authorization_valid": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["authorization_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            {
                "ok": True,
                "authorization_contract_verified": True,
                "upstream_controller_binding_verified": True,
                "signature_verified": True,
                "freshness_verified": True,
                "replay_guard_verified": True,
                "synthetic_authorization_verified": True,
                "status": "C3_CONTROLLED_AUTHORIZATION_VALID_OFFLINE_NON_APPLICABLE",
                "reasons": [],
                "checks": checks,
                "authorization_receipt": receipt,
            }
        )
        return result


__all__ = [
    "AUTHORIZATION_ACTION_V1",
    "AUTHORIZATION_ENVELOPE_VERSION_V1",
    "ControlledAuthorizationValidatorConfigV1",
    "ControlledAuthorizationValidatorV1",
    "InMemoryAuthorizationReplayGuardV1",
    "OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION",
    "authorization_signing_payload_v1",
]
