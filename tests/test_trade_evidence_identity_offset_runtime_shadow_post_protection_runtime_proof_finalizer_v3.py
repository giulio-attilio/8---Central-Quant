from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from trade_evidence_identity_offset_runtime_shadow_post_protection_runtime_proof_finalizer_v3 import (
    C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZATION_ORDER,
    C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_DEFAULT_ENABLED,
    finalize_c3_post_protection_runtime_proof_v3,
)


ROOT = Path(__file__).resolve().parents[1]


def _runtime_facts():
    registry = {"ok": True, "status": "REGISTERED", "secret": "discard"}
    safety = {"ok": True, "status": "STOP_CONFIRMED", "positions": ["discard"]}
    fallback = {"ok": True, "status": "STOP_ALREADY_CONFIRMED", "raw": "discard"}
    live = {
        "client_order_id": "ENT1-EXPECTED",
        "returned_client_order_id": "ENT1-EXPECTED",
        "returned_client_order_id_matches": True,
        "entry_acknowledged": True,
        "order_id": "ENTRY-ORDER-1",
        "engine_broker_state": {
            "ok": True,
            "persistent": True,
            "status": "ENGINE_BROKER_RESULT_CONFIRMED",
        },
        "disaster_stop": {
            "confirmed": True,
            "order_id": "STOP-ORDER-1",
            "returned_client_order_id_matches": True,
            "stop_status_active": True,
            "stop_materially_valid": True,
            "stop_operationally_armed": True,
        },
    }
    payload = {
        "live_result": live,
        "trade_registry_sync_v1": registry,
        "post_execution_safety_check_v1": safety,
        "disaster_stop_fallback_v1": fallback,
    }
    result = {
        "payload": payload,
        "trade_registry_sync_v1": registry,
        "post_execution_safety_check_v1": safety,
        "disaster_stop_fallback_v1": fallback,
    }
    return result, registry, safety, fallback


def _finalize(*, origin="CONSOLE", mutate=None):
    result, registry, safety, fallback = _runtime_facts()
    if mutate is not None:
        mutate(result, registry, safety, fallback)
    return finalize_c3_post_protection_runtime_proof_v3(
        origin=origin,
        engine_result=result,
        registry_sync=registry,
        safety_check=safety,
        disaster_stop_fallback=fallback,
        enabled=True,
    )


def test_finalizer_is_default_off_and_does_not_require_runtime_facts():
    assert C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZER_DEFAULT_ENABLED is False
    result = finalize_c3_post_protection_runtime_proof_v3(
        origin="AUTO_BRIDGE",
        engine_result=None,
        registry_sync=None,
        safety_check=None,
        disaster_stop_fallback=None,
    )
    assert result["status"] == "BYPASSED_DEFAULT_OFF"
    assert result["reason"] == "DEFAULT_OFF"
    assert result["proof_emitted"] is False
    assert result["legacy_authoritative"] is True


def test_enabled_offline_branch_emits_only_sanitized_strict_proof():
    result = _finalize()

    assert result["status"] == "PROOF_EMITTED_READ_ONLY"
    assert result["proof_emitted"] is True
    assert result["finalization_order"] == list(
        C3_POST_PROTECTION_RUNTIME_PROOF_FINALIZATION_ORDER
    )
    assert result["proof"]["entry"]["client_order_id_sha256"] == hashlib.sha256(
        b"ENT1-EXPECTED"
    ).hexdigest()
    assert result["proof"]["stop"]["order_id_sha256"] == hashlib.sha256(
        b"STOP-ORDER-1"
    ).hexdigest()
    rendered = repr(result)
    assert "ENT1-EXPECTED" not in rendered
    assert "ENTRY-ORDER-1" not in rendered
    assert "STOP-ORDER-1" not in rendered
    assert "discard" not in rendered


def test_non_converged_origin_is_blocked_even_with_complete_facts():
    result = _finalize(origin="FALCON_DIRECT")
    assert result["status"] == "BLOCKED_FAIL_CLOSED"
    assert result["reason"] == "ORIGIN_NOT_CONVERGED"


def test_exact_route_local_stage_bindings_are_required():
    result = _finalize(
        mutate=lambda engine, *_args: engine.__setitem__(
            "trade_registry_sync_v1", {"ok": True, "status": "OTHER"}
        )
    )
    assert result["reason"] == "LEGACY_STAGE_BINDING_AMBIGUOUS"


def test_falcon_wrapper_registry_duplication_is_blocked():
    result = _finalize(
        mutate=lambda engine, *_args: engine.__setitem__(
            "falcon_live_execution_audit_guard_v1",
            {"registry_result": {"ok": True, "status": "REGISTERED_AGAIN"}},
        )
    )
    assert result["reason"] == "DUPLICATE_REGISTRY_STAGE"


def test_entry_identity_mismatch_and_weak_stop_confirmation_fail_closed():
    mismatch = _finalize(
        mutate=lambda engine, *_args: engine["payload"]["live_result"].__setitem__(
            "returned_client_order_id", "ENT1-DIFFERENT"
        )
    )
    assert mismatch["reason"] == "ENTRY_IDENTITY_PROOF_INVALID"

    weak_stop = _finalize(
        mutate=lambda engine, *_args: engine["payload"]["live_result"][
            "disaster_stop"
        ].__setitem__("stop_materially_valid", False)
    )
    assert weak_stop["reason"] == "DISASTER_STOP_STRICT_PROOF_INVALID"


def test_engine_broker_state_must_be_confirmed_and_persistent():
    result = _finalize(
        mutate=lambda engine, *_args: engine["payload"]["live_result"][
            "engine_broker_state"
        ].__setitem__("persistent", False)
    )
    assert result["reason"] == "ENGINE_BROKER_STATE_PROOF_INVALID"


def test_main_integrates_exactly_two_literal_default_off_manual_origins():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "finalize_c3_post_protection_runtime_proof_v3"
    ]
    assert len(calls) == 2
    origins = set()
    for call in calls:
        kwargs = {keyword.arg: keyword.value for keyword in call.keywords}
        assert isinstance(kwargs["enabled"], ast.Constant)
        assert kwargs["enabled"].value is False
        assert isinstance(kwargs["origin"], ast.Constant)
        origins.add(kwargs["origin"].value)
    assert origins == {"CONSOLE", "EXECUTIONLIVE"}
