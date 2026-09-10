from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_bridge_v1 as bridge
import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_harness_v1 as harness


def _sha(value) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _reseal(request: dict) -> dict:
    preview = request["evidence"]["preview_receipt"]
    preview_payload = {
        key: value
        for key, value in preview.items()
        if key != "preview_receipt_sha256"
    }
    preview["preview_receipt_sha256"] = _sha(preview_payload)
    request["request_sha256"] = (
        bridge.prebootstrap_maintenance_request_sha256_v1(request)
    )
    return request


def test_bridge_is_default_off_and_invokes_no_dependency() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=False
    )

    result = instance.run_offline(request)

    assert result["ok"] is False
    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_BRIDGE_DEFAULT_OFF"
    assert environment.events == []
    assert result["runtime_integrated"] is False
    assert result["live_allowed"] is False


def test_contract_imports_no_runtime_filesystem_network_or_broker_module() -> None:
    source = Path(bridge.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])

    assert not imported.intersection(
        {
            "main",
            "trade_registry",
            "requests",
            "httpx",
            "urllib",
            "socket",
            "pathlib",
            "os",
            "subprocess",
            "ccxt",
        }
    )


def test_happy_rehearsal_uses_one_permit_and_preserves_open_exactly() -> None:
    payload = harness.run_synthetic_prebootstrap_maintenance_harness_v1()
    result = payload["result"]

    assert result["ok"] is True
    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_REHEARSAL_VERIFIED"
    assert payload["events"] == [
        "observe",
        "maintenance_enter",
        "repair",
        "bootstrap",
        "startup_recovery",
        "postflight",
        "maintenance_exit",
    ]
    assert payload["final_registry_sha256"] == payload["candidate_registry_sha256"]
    assert payload["source_registry_sha256"] != payload["final_registry_sha256"]
    assert payload["open_trades_preserved_exactly"] is True
    assert result["same_maintenance_permit_used"] is True
    assert result["conflict_count_after"] == 0
    assert result["write_executed"] is False
    assert result["registry_write"] is False
    assert result["runtime_integrated"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert len(result["receipt"]["receipt_sha256"]) == 64


def test_successful_request_is_consumed_once() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True
    )
    first = instance.run_offline(request)
    event_count = len(environment.events)

    second = instance.run_offline(request)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["status"] == "PREBOOTSTRAP_REQUEST_REPLAY_BLOCKED"
    assert len(environment.events) == event_count


def test_outer_request_hash_tamper_fails_before_observation() -> None:
    request = harness.build_synthetic_prebootstrap_request_v1()
    request["request_sha256"] = "0" * 64
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, request=request
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_REQUEST_HASH_MISMATCH"
    assert environment.events == []


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("trading_controls", "enable_real_trading"), True),
        (("registry_status", "migration_done"), True),
        (("conflict_audit", "conflict_count"), 2),
        (("conflict_audit", "financial_conflict_count"), 1),
        (("maintenance_coordinator", "registered_writer_count"), 18),
        (("maintenance_coordinator", "runtime_activation_allowed"), True),
    ],
)
def test_unsafe_preconditions_fail_before_observation(path, value) -> None:
    request = harness.build_synthetic_prebootstrap_request_v1()
    request["evidence"][path[0]][path[1]] = value
    _reseal(request)
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, request=request
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_EVIDENCE_UNSAFE"
    assert environment.events == []


def test_preview_receipt_must_be_self_hash_bound() -> None:
    request = harness.build_synthetic_prebootstrap_request_v1()
    request["evidence"]["preview_receipt"]["preview_receipt_sha256"] = "f" * 64
    request["request_sha256"] = bridge.prebootstrap_maintenance_request_sha256_v1(
        request
    )
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, request=request
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_EVIDENCE_UNSAFE"
    assert environment.events == []


def test_changed_paths_are_restricted_to_one_closed_record() -> None:
    request = harness.build_synthetic_prebootstrap_request_v1()
    request["evidence"]["preview_receipt"]["changed_paths"][0] = (
        "open_trades.open-keep.quantity"
    )
    _reseal(request)
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, request=request
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_EVIDENCE_UNSAFE"
    assert environment.events == []


def test_observation_drift_fails_before_maintenance() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase="observation_drift"
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_OBSERVATION_DRIFT"
    assert environment.events == ["observe"]


def test_invalid_maintenance_permit_never_reaches_repair() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase="permit_invalid"
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_MAINTENANCE_PERMIT_INVALID"
    assert environment.events == [
        "observe",
        "maintenance_enter",
        "maintenance_exit",
    ]


@pytest.mark.parametrize("fail_phase", ["repair_rejected", "repair_exception"])
def test_repair_failure_never_reaches_bootstrap_or_rollback(fail_phase) -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase=fail_phase
    )

    result = instance.run_offline(request)

    assert result["ok"] is False
    assert "bootstrap" not in environment.events
    assert "rollback" not in environment.events
    assert environment.registry == environment.source
    assert result["live_allowed"] is False


def test_invalid_repair_receipt_rolls_back_before_lease_release() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase="repair_invalid_receipt"
    )

    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_REPAIR_FAILED_CLOSED"
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is True
    assert environment.events.index("rollback") < environment.events.index(
        "maintenance_exit"
    )
    assert environment.registry == environment.source


@pytest.mark.parametrize(
    ("fail_phase", "expected_status"),
    [
        ("bootstrap_rejected", "PREBOOTSTRAP_BOOTSTRAP_FAILED_CLOSED"),
        ("bootstrap_exception", "PREBOOTSTRAP_BOOTSTRAP_FAILED_CLOSED"),
        ("recovery_rejected", "PREBOOTSTRAP_RECOVERY_FAILED_CLOSED"),
        ("recovery_exception", "PREBOOTSTRAP_STARTUP_RECOVERY_FAILED_CLOSED"),
        ("postflight_rejected", "PREBOOTSTRAP_POSTFLIGHT_FAILED_CLOSED"),
    ],
)
def test_post_repair_failures_rollback_inside_same_lease(
    fail_phase, expected_status
) -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase=fail_phase
    )

    result = instance.run_offline(request)

    assert result["status"] == expected_status
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is True
    assert environment.events.index("rollback") < environment.events.index(
        "maintenance_exit"
    )
    assert environment.registry == environment.source
    assert environment.open_before == environment.registry["open_trades"]
    assert result["runtime_integrated"] is False
    assert result["live_allowed"] is False


def test_rollback_failure_stays_fail_closed() -> None:
    instance, environment, request = harness.build_synthetic_prebootstrap_bridge_v1(
        enabled=True, fail_phase="rollback_rejected"
    )

    original_bootstrap = environment.bootstrap

    def rejected_bootstrap(repair_result, permit):
        environment.fail_phase = "rollback_rejected"
        result = original_bootstrap(repair_result, permit)
        result["ok"] = False
        return result

    instance._bootstrap = rejected_bootstrap
    result = instance.run_offline(request)

    assert result["status"] == "PREBOOTSTRAP_ROLLBACK_FAILED_CLOSED"
    assert result["rollback_attempted"] is True
    assert result["rollback_verified"] is False
    assert result["live_allowed"] is False


def test_scope_is_required_even_when_enabled() -> None:
    request = harness.build_synthetic_prebootstrap_request_v1()
    environment = harness.SyntheticPrebootstrapEnvironmentV1(request)
    instance = bridge.PrebootstrapMaintenanceBridgeV1(
        observe=environment.observe,
        maintenance_lease=environment.maintenance_lease,
        repair=environment.repair,
        bootstrap=environment.bootstrap,
        startup_recovery=environment.startup_recovery,
        postflight=environment.postflight,
        rollback=environment.rollback,
        config=bridge.PrebootstrapMaintenanceBridgeConfigV1(enabled=True),
    )

    result = instance.run_offline(copy.deepcopy(request))

    assert result["status"] == "C3_PREBOOTSTRAP_MAINTENANCE_SCOPE_REQUIRED"
    assert environment.events == []
