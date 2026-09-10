"""In-memory harness for the controlled C3 authorization validator."""

from __future__ import annotations

import copy
import hashlib
import hmac
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1 as binding_contract
import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_harness_v1 as binding_harness
import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as validator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-AUTHORIZATION-HARNESS-V1"
)

_SYNTHETIC_KEY_ID = "synthetic-c3-authorization-key-v1"
_SYNTHETIC_KEY = hashlib.sha256(
    b"C3 synthetic authorization harness key; never production"
).digest()
_SYNTHETIC_NOW = 2_000_000_000


def _synthetic_sha256(label: str) -> str:
    return hashlib.sha256(f"synthetic:{label}".encode("utf-8")).hexdigest()


def build_synthetic_c3_controlled_authorization_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    binding_inputs = binding_harness.build_synthetic_c3_repair_controller_binding_inputs_v1(
        repository_root
    )
    binding_result = binding_contract.evaluate_c3_repair_controller_binding_offline_v1(
        **binding_inputs
    )
    if binding_result.get("ok") is not True:
        raise AssertionError("upstream controller-binding contract failed closed")
    binding_receipt_sha = binding_result["binding_receipt"]["binding_receipt_sha256"]
    envelope = {
        "authorization_version": validator_module.AUTHORIZATION_ENVELOPE_VERSION_V1,
        "algorithm": "HMAC-SHA-256",
        "key_id": _SYNTHETIC_KEY_ID,
        "nonce": "SYNTHETIC_NONCE_0123456789_ABCDEFGH",
        "issued_at_epoch": _SYNTHETIC_NOW - 5,
        "expires_at_epoch": _SYNTHETIC_NOW + 55,
        "action": validator_module.AUTHORIZATION_ACTION_V1,
        "upstream_controller_binding_receipt_sha256": binding_receipt_sha,
        "preview_receipt_sha256": _synthetic_sha256("preview-receipt"),
        "source_registry_sha256": _synthetic_sha256("source-registry"),
        "candidate_registry_sha256": _synthetic_sha256("candidate-registry"),
        "changed_paths_sha256": _synthetic_sha256("changed-paths"),
        "max_apply_count": 1,
        "repair_apply_requested": True,
        "writer_coordination_window_requested": True,
        "runtime_activation_requested": False,
        "live_requested": False,
        "order_submission_authorized": False,
    }
    envelope["signature"] = hmac.new(
        _SYNTHETIC_KEY,
        validator_module.authorization_signing_payload_v1(envelope),
        hashlib.sha256,
    ).hexdigest()
    return {
        "controller_binding_result": binding_result,
        "authorization_envelope": envelope,
    }


def build_synthetic_c3_controlled_authorization_validator_v1(
    *, replay_guard: validator_module.InMemoryAuthorizationReplayGuardV1 | None = None
) -> validator_module.ControlledAuthorizationValidatorV1:
    def key_resolver(key_id: str) -> bytes:
        if key_id != _SYNTHETIC_KEY_ID:
            raise KeyError("synthetic key id unknown")
        return _SYNTHETIC_KEY

    return validator_module.ControlledAuthorizationValidatorV1(
        config=validator_module.ControlledAuthorizationValidatorConfigV1(
            enabled=True,
            scope_attestation=validator_module.OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1,
            max_ttl_seconds=300,
            max_clock_skew_seconds=30,
        ),
        key_resolver=key_resolver,
        clock=lambda: _SYNTHETIC_NOW,
        replay_guard=(
            replay_guard
            if replay_guard is not None
            else validator_module.InMemoryAuthorizationReplayGuardV1()
        ),
    )


def run_synthetic_c3_controlled_authorization_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_controlled_authorization_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    guard = validator_module.InMemoryAuthorizationReplayGuardV1()
    validator = build_synthetic_c3_controlled_authorization_validator_v1(
        replay_guard=guard
    )
    first = validator.verify(**inputs)
    replay = validator.verify(**copy.deepcopy(inputs))
    receipt = first.get("authorization_receipt")
    guard_snapshot = guard.snapshot()
    ok = bool(
        first.get("ok") is True
        and first.get("authorization_contract_verified") is True
        and first.get("signature_verified") is True
        and first.get("freshness_verified") is True
        and first.get("replay_guard_verified") is True
        and first.get("synthetic_authorization_verified") is True
        and first.get("production_authorization_valid") is False
        and first.get("runtime_binding_satisfied") is False
        and first.get("apply_allowed") is False
        and first.get("activation_allowed") is False
        and first.get("live_allowed") is False
        and isinstance(receipt, dict)
        and receipt.get("max_apply_count") == 1
        and receipt.get("synthetic_authorization_verified") is True
        and receipt.get("production_authorization_valid") is False
        and receipt.get("apply_allowed") is False
        and replay.get("ok") is False
        and "AUTHORIZATION_REPLAY_DETECTED" in replay.get("reasons", [])
        and replay.get("authorization_receipt") is None
        and guard_snapshot.get("stored_nonce_digest_count") == 1
        and guard_snapshot.get("raw_nonce_stored") is False
        and inputs == before
    )
    return {
        "ok": ok,
        "status": (
            "C3_CONTROLLED_AUTHORIZATION_HARNESS_PASSED_OFFLINE_NON_APPLICABLE"
            if ok
            else "C3_CONTROLLED_AUTHORIZATION_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "synthetic_authorization_verified": first.get(
            "synthetic_authorization_verified", False
        ),
        "production_authorization_valid": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "input_preserved": inputs == before,
        "replay_denied": replay.get("ok") is False,
        "replay_guard_snapshot": guard_snapshot,
        "authorization_result": first,
        "replay_result": replay,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_HARNESS_V1_VERSION",
    "build_synthetic_c3_controlled_authorization_inputs_v1",
    "build_synthetic_c3_controlled_authorization_validator_v1",
    "run_synthetic_c3_controlled_authorization_harness_v1",
]
