"""Dormant, read-only C3 V3 post-protection proof finalizer.

The runtime integration always calls this finalizer with ``enabled=False``.
The enabled branch exists solely for deterministic offline tests and performs
no I/O, persistence, broker calls, or legacy-stage execution.
"""

from __future__ import annotations

import hashlib
from typing import Any


C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_VERSION = (
    "TEIOI-C3-POST-PROTECTION-RUNTIME-PROOF-FINALIZER-DORMANT-V1"
)
C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_DEFAULT_ENABLED = False
C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZATION_ORDER = (
    "ENTRY_ACK_FROM_ENGINE",
    "DISASTER_STOP_FROM_BROKER_STRICT",
    "ENGINE_BROKER_STATE_PERSISTENCE",
    "ROUTE_TRADE_REGISTRY_SYNC",
    "ROUTE_POST_EXECUTION_SAFETY",
    "ROUTE_DISASTER_STOP_FALLBACK",
    "ROUTE_POST_PROTECTION_SEAM",
)
_CONVERGED_ORIGINS = frozenset({"CONSOLE", "EXECUTIONLIVE"})


def _blocked(origin: str, reason: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "fail_closed": True,
        "legacy_authoritative": True,
        "origin": origin,
        "proof_emitted": False,
        "reason": reason,
        "status": "BLOCKED_FAIL_CLOSED",
        "version": C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_VERSION,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stage_summary(value: dict[str, Any]) -> dict[str, Any]:
    status = value.get("status")
    version = value.get("version")
    return {
        "ok": value.get("ok") is True,
        "status": str(status)[:160] if status is not None else None,
        "version": str(version)[:160] if version is not None else None,
    }


def _live_result(engine_result: dict[str, Any]) -> dict[str, Any] | None:
    payload = engine_result.get("payload")
    if type(payload) is dict and type(payload.get("live_result")) is dict:
        return payload["live_result"]
    if type(engine_result.get("live_result")) is dict:
        return engine_result["live_result"]
    return None


def finalize_c3_post_protection_runtime_proof_v3(
    *,
    origin: str,
    engine_result: Any,
    registry_sync: Any,
    safety_check: Any,
    disaster_stop_fallback: Any,
    enabled: bool = C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_DEFAULT_ENABLED,
) -> dict[str, Any]:
    """Observe already-returned facts; never execute or modify legacy stages."""

    origin_normalized = str(origin or "").strip().upper()
    if enabled is not True:
        return {
            "enabled": False,
            "fail_closed": True,
            "legacy_authoritative": True,
            "origin": origin_normalized,
            "proof_emitted": False,
            "reason": "DEFAULT_OFF",
            "status": "BYPASSED_DEFAULT_OFF",
            "version": C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_VERSION,
        }
    if origin_normalized not in _CONVERGED_ORIGINS:
        return _blocked(origin_normalized, "ORIGIN_NOT_CONVERGED")
    if any(
        type(value) is not dict
        for value in (
            engine_result,
            registry_sync,
            safety_check,
            disaster_stop_fallback,
        )
    ):
        return _blocked(origin_normalized, "LEGACY_STAGE_RESULT_REQUIRED")

    live_result = _live_result(engine_result)
    if live_result is None:
        return _blocked(origin_normalized, "ENGINE_RESULT_SHAPE_INVALID")

    # The route-local objects must be the exact objects attached to the
    # authoritative result. A pre-existing different object is ambiguous.
    payload = engine_result.get("payload")
    payload = payload if type(payload) is dict else {}
    stage_bindings = (
        ("trade_registry_sync_v1", registry_sync),
        ("post_execution_safety_check_v1", safety_check),
        ("disaster_stop_fallback_v1", disaster_stop_fallback),
    )
    if any(
        engine_result.get(key) is not value or payload.get(key) is not value
        for key, value in stage_bindings
    ):
        return _blocked(origin_normalized, "LEGACY_STAGE_BINDING_AMBIGUOUS")

    falcon_audit = engine_result.get("falcon_live_execution_audit_guard_v1")
    if type(falcon_audit) is dict and type(falcon_audit.get("registry_result")) is dict:
        return _blocked(origin_normalized, "DUPLICATE_REGISTRY_STAGE")

    expected_client_order_id = live_result.get("client_order_id")
    returned_client_order_id = live_result.get("returned_client_order_id")
    entry_order_id = live_result.get("order_id") or live_result.get("id")
    if not all(
        type(value) is str and bool(value.strip())
        for value in (
            expected_client_order_id,
            returned_client_order_id,
            entry_order_id,
        )
    ):
        return _blocked(origin_normalized, "ENTRY_IDENTITY_PROOF_REQUIRED")
    if not (
        expected_client_order_id == returned_client_order_id
        and live_result.get("returned_client_order_id_matches") is True
        and live_result.get("entry_acknowledged") is True
    ):
        return _blocked(origin_normalized, "ENTRY_IDENTITY_PROOF_INVALID")

    disaster_stop = live_result.get("disaster_stop")
    if type(disaster_stop) is not dict:
        return _blocked(origin_normalized, "DISASTER_STOP_PROOF_REQUIRED")
    stop_order_id = disaster_stop.get("order_id")
    if not (type(stop_order_id) is str and stop_order_id.strip()):
        return _blocked(origin_normalized, "DISASTER_STOP_ORDER_ID_REQUIRED")
    if not all(
        disaster_stop.get(field) is True
        for field in (
            "confirmed",
            "returned_client_order_id_matches",
            "stop_status_active",
            "stop_materially_valid",
            "stop_operationally_armed",
        )
    ):
        return _blocked(origin_normalized, "DISASTER_STOP_STRICT_PROOF_INVALID")

    broker_state = live_result.get("engine_broker_state")
    if not (
        type(broker_state) is dict
        and broker_state.get("ok") is True
        and broker_state.get("persistent") is True
        and broker_state.get("status") == "ENGINE_BROKER_RESULT_CONFIRMED"
    ):
        return _blocked(origin_normalized, "ENGINE_BROKER_STATE_PROOF_INVALID")

    return {
        "enabled": True,
        "fail_closed": True,
        "finalization_order": list(
            C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZATION_ORDER
        ),
        "legacy_authoritative": True,
        "origin": origin_normalized,
        "proof": {
            "entry": {
                "client_order_id_sha256": _digest(expected_client_order_id),
                "entry_acknowledged": True,
                "order_id_sha256": _digest(entry_order_id),
                "returned_client_order_id_matches": True,
            },
            "legacy_stages": {
                "disaster_stop_fallback": _stage_summary(disaster_stop_fallback),
                "post_execution_safety": _stage_summary(safety_check),
                "trade_registry_sync": _stage_summary(registry_sync),
            },
            "stop": {
                "confirmed": True,
                "order_id_sha256": _digest(stop_order_id),
                "returned_client_order_id_matches": True,
                "stop_materially_valid": True,
                "stop_operationally_armed": True,
                "stop_status_active": True,
            },
        },
        "proof_emitted": True,
        "reason": "STRICT_RUNTIME_PROOF_OBSERVED",
        "status": "PROOF_EMITTED_READ_ONLY",
        "telemetry_persistent": False,
        "version": C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_VERSION,
    }


__all__ = [
    "C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZATION_ORDER",
    "C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_DEFAULT_ENABLED",
    "C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_VERSION",
    "finalize_c3_post_protection_runtime_proof_v3",
]
