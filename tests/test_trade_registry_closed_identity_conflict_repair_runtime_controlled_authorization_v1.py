from __future__ import annotations

import ast
import copy
import hashlib
import hmac
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as validator_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def authorization_inputs() -> dict:
    return harness.build_synthetic_c3_controlled_authorization_inputs_v1(ROOT)


def _resign(inputs: dict) -> None:
    envelope = inputs["authorization_envelope"]
    envelope["signature"] = hmac.new(
        harness._SYNTHETIC_KEY,
        validator_module.authorization_signing_payload_v1(envelope),
        hashlib.sha256,
    ).hexdigest()


def _validator(
    *,
    now: int = harness._SYNTHETIC_NOW,
    guard: validator_module.InMemoryAuthorizationReplayGuardV1 | None = None,
    key_resolver=None,
) -> validator_module.ControlledAuthorizationValidatorV1:
    resolver = key_resolver
    if resolver is None:
        resolver = lambda key_id: (
            harness._SYNTHETIC_KEY
            if key_id == harness._SYNTHETIC_KEY_ID
            else (_ for _ in ()).throw(KeyError(key_id))
        )
    return validator_module.ControlledAuthorizationValidatorV1(
        config=validator_module.ControlledAuthorizationValidatorConfigV1(
            enabled=True,
            scope_attestation=validator_module.OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1,
        ),
        key_resolver=resolver,
        clock=lambda: now,
        replay_guard=guard or validator_module.InMemoryAuthorizationReplayGuardV1(),
    )


def test_default_validator_fails_closed_without_touching_inputs(
    authorization_inputs: dict,
) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    before = copy.deepcopy(inputs)

    result = validator_module.ControlledAuthorizationValidatorV1().verify(**inputs)

    assert result["ok"] is False
    assert result["status"] == "C3_CONTROLLED_AUTHORIZATION_VALIDATOR_DEFAULT_OFF"
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["no_order_sent"] is True
    assert inputs == before


def test_valid_synthetic_signature_still_denies_real_application(
    authorization_inputs: dict,
) -> None:
    result = _validator().verify(**copy.deepcopy(authorization_inputs))

    assert result["ok"] is True
    assert result["authorization_contract_verified"] is True
    assert result["upstream_controller_binding_verified"] is True
    assert result["signature_verified"] is True
    assert result["freshness_verified"] is True
    assert result["replay_guard_verified"] is True
    assert result["synthetic_authorization_verified"] is True
    assert result["production_authorization_valid"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False


def test_same_nonce_is_consumed_exactly_once(authorization_inputs: dict) -> None:
    guard = validator_module.InMemoryAuthorizationReplayGuardV1()
    validator = _validator(guard=guard)

    first = validator.verify(**copy.deepcopy(authorization_inputs))
    second = validator.verify(**copy.deepcopy(authorization_inputs))

    assert first["ok"] is True
    assert second["ok"] is False
    assert "AUTHORIZATION_REPLAY_DETECTED" in second["reasons"]
    assert second["authorization_receipt"] is None
    assert guard.snapshot() == {
        "stored_nonce_digest_count": 1,
        "raw_nonce_stored": False,
        "durable": False,
        "synthetic_only": True,
    }


def test_concurrent_replay_allows_exactly_one_consumer(
    authorization_inputs: dict,
) -> None:
    guard = validator_module.InMemoryAuthorizationReplayGuardV1()
    validator = _validator(guard=guard)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _index: validator.verify(
                    **copy.deepcopy(authorization_inputs)
                ),
                range(16),
            )
        )

    assert sum(result["ok"] is True for result in results) == 1
    assert sum(
        "AUTHORIZATION_REPLAY_DETECTED" in result["reasons"]
        for result in results
    ) == 15
    assert guard.snapshot()["stored_nonce_digest_count"] == 1


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("action", "LIVE", "AUTHORIZATION_SCOPE_INVALID"),
        ("max_apply_count", 2, "AUTHORIZATION_SCOPE_INVALID"),
        ("repair_apply_requested", False, "AUTHORIZATION_SCOPE_INVALID"),
        ("writer_coordination_window_requested", False, "AUTHORIZATION_SCOPE_INVALID"),
        ("runtime_activation_requested", True, "AUTHORIZATION_SCOPE_INVALID"),
        ("live_requested", True, "AUTHORIZATION_SCOPE_INVALID"),
        ("order_submission_authorized", True, "AUTHORIZATION_SCOPE_INVALID"),
        ("preview_receipt_sha256", "f" * 64, "AUTHORIZATION_SIGNATURE_INVALID"),
    ],
)
def test_scope_or_signed_payload_tampering_fails_closed(
    authorization_inputs: dict, field: str, value: object, reason: str
) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    inputs["authorization_envelope"][field] = value

    result = _validator().verify(**inputs)

    assert result["ok"] is False
    assert reason in result["reasons"]
    assert result["apply_allowed"] is False
    assert result["authorization_receipt"] is None


def test_unknown_field_fails_closed_even_with_valid_signature(
    authorization_inputs: dict,
) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    inputs["authorization_envelope"]["unexpected_authority"] = True
    _resign(inputs)

    result = _validator().verify(**inputs)

    assert result["ok"] is False
    assert "AUTHORIZATION_ENVELOPE_FIELDS_INVALID" in result["reasons"]
    assert result["activation_allowed"] is False


def test_valid_signature_cannot_authorize_live_or_orders(
    authorization_inputs: dict,
) -> None:
    for field in ("live_requested", "order_submission_authorized"):
        inputs = copy.deepcopy(authorization_inputs)
        inputs["authorization_envelope"][field] = True
        _resign(inputs)

        result = _validator().verify(**inputs)

        assert result["ok"] is False
        assert "AUTHORIZATION_SCOPE_INVALID" in result["reasons"]
        assert result["signature_verified"] is False
        assert result["apply_allowed"] is False
        assert result["live_allowed"] is False


@pytest.mark.parametrize(
    ("issued_offset", "expires_offset"),
    [
        (-301, -1),
        (-301, 1),
        (31, 60),
        (-1, 301),
    ],
)
def test_expired_future_or_oversized_window_fails_closed(
    authorization_inputs: dict, issued_offset: int, expires_offset: int
) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    envelope = inputs["authorization_envelope"]
    envelope["issued_at_epoch"] = harness._SYNTHETIC_NOW + issued_offset
    envelope["expires_at_epoch"] = harness._SYNTHETIC_NOW + expires_offset
    _resign(inputs)

    result = _validator().verify(**inputs)

    assert result["ok"] is False
    assert "AUTHORIZATION_WINDOW_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["apply_allowed"] is False


def test_missing_short_or_wrong_key_fails_closed(authorization_inputs: dict) -> None:
    resolvers = (
        None,
        lambda _key_id: b"short",
        lambda _key_id: b"x" * 32,
    )
    for resolver in resolvers:
        validator = validator_module.ControlledAuthorizationValidatorV1(
            config=validator_module.ControlledAuthorizationValidatorConfigV1(
                enabled=True,
                scope_attestation=validator_module.OFFLINE_VALIDATOR_SCOPE_ATTESTATION_V1,
            ),
            key_resolver=resolver,
            clock=lambda: harness._SYNTHETIC_NOW,
            replay_guard=validator_module.InMemoryAuthorizationReplayGuardV1(),
        )
        result = validator.verify(**copy.deepcopy(authorization_inputs))
        assert result["ok"] is False
        assert result["signature_verified"] is False
        assert result["apply_allowed"] is False


def test_tampered_upstream_binding_receipt_fails_closed(
    authorization_inputs: dict,
) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    inputs["controller_binding_result"]["binding_receipt"]["binding_count"] = 4

    result = _validator().verify(**inputs)

    assert result["ok"] is False
    assert "AUTHORIZATION_UPSTREAM_CONTROLLER_BINDING_INVALID" in result["reasons"]
    assert result["authorization_receipt"] is None


def test_invalid_upstream_does_not_resolve_key(authorization_inputs: dict) -> None:
    inputs = copy.deepcopy(authorization_inputs)
    inputs["controller_binding_result"]["binding_receipt"]["binding_count"] = 4
    calls = []

    def resolver(_key_id: str) -> bytes:
        calls.append("called")
        return harness._SYNTHETIC_KEY

    result = _validator(key_resolver=resolver).verify(**inputs)

    assert result["ok"] is False
    assert calls == []
    assert result["signature_verified"] is False


def test_harness_is_offline_sanitized_and_non_applicable() -> None:
    result = harness.run_synthetic_c3_controlled_authorization_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["replay_denied"] is True
    assert result["production_authorization_valid"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["runtime_integrated"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["broker_called"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True
    receipt = result["authorization_result"]["authorization_receipt"]
    assert "key_id" not in receipt
    assert "nonce" not in receipt
    assert "signature" not in receipt


def test_validator_module_has_no_runtime_or_external_surface() -> None:
    tree = ast.parse(inspect.getsource(validator_module))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imports
    assert "trade_registry" not in imports
    assert "broker" not in imports
    source = inspect.getsource(validator_module)
    for token in (
        "write_text(",
        "write_bytes(",
        "open(",
        "requests.",
        "httpx.",
        "subprocess",
        "os.environ",
        "save_registry(",
        "start_central_runtime_once(",
    ):
        assert token not in source
    assert not hasattr(validator_module, "activate")
    assert not hasattr(validator_module, "apply")
