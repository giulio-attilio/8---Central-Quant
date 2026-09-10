from __future__ import annotations

import ast
import copy
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_v1 as package_module


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def package_inputs() -> dict:
    return harness.build_synthetic_c3_controlled_repair_package_inputs_v1(ROOT)


def _reseal_manifest(inputs: dict) -> None:
    manifest = inputs["package_manifest"]
    manifest["package_sha256"] = package_module.controlled_repair_package_sha256_v1(
        manifest
    )


def _reseal_preview(inputs: dict) -> None:
    receipt = inputs["preview_result"]["preview_receipt"]
    receipt["preview_receipt_sha256"] = package_module._stable_sha256(
        {key: value for key, value in receipt.items() if key != "preview_receipt_sha256"}
    )


def _reseal_authorization(inputs: dict) -> None:
    receipt = inputs["authorization_result"]["authorization_receipt"]
    receipt["authorization_receipt_sha256"] = package_module._stable_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key != "authorization_receipt_sha256"
        }
    )


def _assembler(
    *,
    now: int = harness._NOW,
    guard: package_module.InMemoryRepairPackageReplayGuardV1 | None = None,
) -> package_module.ControlledRepairPackageAssemblerV1:
    return package_module.ControlledRepairPackageAssemblerV1(
        config=package_module.ControlledRepairPackageConfigV1(
            enabled=True,
            scope_attestation=package_module.OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: now,
        replay_guard=guard or package_module.InMemoryRepairPackageReplayGuardV1(),
    )


def test_default_assembler_fails_closed_without_mutating_inputs(
    package_inputs: dict,
) -> None:
    inputs = copy.deepcopy(package_inputs)
    before = copy.deepcopy(inputs)

    result = package_module.ControlledRepairPackageAssemblerV1().assemble(**inputs)

    assert result["ok"] is False
    assert result["status"] == "C3_CONTROLLED_REPAIR_PACKAGE_ASSEMBLER_DEFAULT_OFF"
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert inputs == before


def test_valid_package_is_cross_bound_but_non_applicable(package_inputs: dict) -> None:
    result = _assembler().assemble(**copy.deepcopy(package_inputs))

    assert result["ok"] is True
    assert result["package_contract_verified"] is True
    assert result["controller_binding_verified"] is True
    assert result["authorization_verified"] is True
    assert result["preview_verified"] is True
    assert result["cross_binding_verified"] is True
    assert result["freshness_verified"] is True
    assert result["replay_guard_verified"] is True
    assert result["package_assembled_offline"] is True
    assert result["production_authorization_valid"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True


def test_authorization_receipt_is_consumed_once(package_inputs: dict) -> None:
    guard = package_module.InMemoryRepairPackageReplayGuardV1()
    assembler = _assembler(guard=guard)

    first = assembler.assemble(**copy.deepcopy(package_inputs))
    second = assembler.assemble(**copy.deepcopy(package_inputs))

    assert first["ok"] is True
    assert second["ok"] is False
    assert "PACKAGE_AUTHORIZATION_REPLAY_DETECTED" in second["reasons"]
    assert second["package_receipt"] is None
    assert guard.snapshot() == {
        "stored_authorization_digest_count": 1,
        "raw_authorization_receipt_stored": False,
        "durable": False,
        "synthetic_only": True,
    }


def test_concurrent_package_assembly_has_one_winner(package_inputs: dict) -> None:
    guard = package_module.InMemoryRepairPackageReplayGuardV1()
    assembler = _assembler(guard=guard)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _index: assembler.assemble(**copy.deepcopy(package_inputs)),
                range(16),
            )
        )

    assert sum(result["ok"] is True for result in results) == 1
    assert sum(
        "PACKAGE_AUTHORIZATION_REPLAY_DETECTED" in result["reasons"]
        for result in results
    ) == 15
    assert guard.snapshot()["stored_authorization_digest_count"] == 1


def test_preview_candidate_drift_breaks_cross_binding(package_inputs: dict) -> None:
    inputs = copy.deepcopy(package_inputs)
    preview = inputs["preview_result"]["preview_receipt"]
    preview["candidate_registry_sha256"] = "f" * 64
    _reseal_preview(inputs)
    manifest = inputs["package_manifest"]
    manifest["preview_receipt_sha256"] = preview["preview_receipt_sha256"]
    manifest["candidate_registry_sha256"] = preview["candidate_registry_sha256"]
    _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert "PACKAGE_CROSS_BINDING_MISMATCH" in result["reasons"]
    assert result["apply_allowed"] is False


def test_preview_with_apply_permission_is_rejected_even_when_resealed(
    package_inputs: dict,
) -> None:
    inputs = copy.deepcopy(package_inputs)
    preview = inputs["preview_result"]["preview_receipt"]
    preview["apply_allowed"] = True
    _reseal_preview(inputs)
    inputs["package_manifest"]["preview_receipt_sha256"] = preview[
        "preview_receipt_sha256"
    ]
    _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert "PACKAGE_PREVIEW_INVALID" in result["reasons"]
    assert result["package_receipt"] is None


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("package_manifest", "unexpected_authority"),
        ("preview_result", "unexpected_runtime_result"),
        ("preview_receipt", "unexpected_preview_permission"),
    ],
)
def test_unknown_fields_fail_closed(
    package_inputs: dict, container: str, field: str
) -> None:
    inputs = copy.deepcopy(package_inputs)
    if container == "preview_receipt":
        inputs["preview_result"]["preview_receipt"][field] = True
        _reseal_preview(inputs)
    else:
        inputs[container][field] = True
    if container == "package_manifest":
        _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert result["apply_allowed"] is False
    assert result["package_receipt"] is None


@pytest.mark.parametrize(
    ("result_name", "receipt_name", "reason"),
    [
        (
            "controller_binding_result",
            "binding_receipt",
            "PACKAGE_CONTROLLER_BINDING_INVALID",
        ),
        (
            "authorization_result",
            "authorization_receipt",
            "PACKAGE_AUTHORIZATION_INVALID",
        ),
    ],
)
def test_unknown_upstream_receipt_field_fails_closed(
    package_inputs: dict,
    result_name: str,
    receipt_name: str,
    reason: str,
) -> None:
    inputs = copy.deepcopy(package_inputs)
    receipt = inputs[result_name][receipt_name]
    receipt["unexpected_authority"] = True
    digest_field = f"{receipt_name}_sha256"
    receipt[digest_field] = package_module._stable_sha256(
        {key: value for key, value in receipt.items() if key != digest_field}
    )

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert reason in result["reasons"]
    assert result["apply_allowed"] is False


def test_expired_effective_window_fails_closed(package_inputs: dict) -> None:
    inputs = copy.deepcopy(package_inputs)
    auth = inputs["authorization_result"]["authorization_receipt"]
    auth["issued_at_epoch"] = harness._NOW - 60
    auth["expires_at_epoch"] = harness._NOW
    auth["ttl_seconds"] = 60
    _reseal_authorization(inputs)
    manifest = inputs["package_manifest"]
    manifest["authorization_receipt_sha256"] = auth[
        "authorization_receipt_sha256"
    ]
    manifest["expires_at_epoch"] = harness._NOW
    _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert "PACKAGE_WINDOW_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["package_receipt"] is None


def test_inconsistent_authorization_ttl_fails_closed(package_inputs: dict) -> None:
    inputs = copy.deepcopy(package_inputs)
    auth = inputs["authorization_result"]["authorization_receipt"]
    auth["ttl_seconds"] = 1
    _reseal_authorization(inputs)
    inputs["package_manifest"]["authorization_receipt_sha256"] = auth[
        "authorization_receipt_sha256"
    ]
    _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert "PACKAGE_WINDOW_INVALID_OR_EXPIRED" in result["reasons"]
    assert result["package_receipt"] is None


@pytest.mark.parametrize("value", [True, 2, 0])
def test_max_apply_count_requires_exact_integer_one(
    package_inputs: dict, value: object
) -> None:
    inputs = copy.deepcopy(package_inputs)
    inputs["package_manifest"]["max_apply_count"] = value
    _reseal_manifest(inputs)

    result = _assembler().assemble(**inputs)

    assert result["ok"] is False
    assert "PACKAGE_MANIFEST_INVALID" in result["reasons"]
    assert result["apply_allowed"] is False


def test_missing_replay_guard_fails_closed(package_inputs: dict) -> None:
    assembler = package_module.ControlledRepairPackageAssemblerV1(
        config=package_module.ControlledRepairPackageConfigV1(
            enabled=True,
            scope_attestation=package_module.OFFLINE_PACKAGE_SCOPE_ATTESTATION_V1,
        ),
        clock=lambda: harness._NOW,
        replay_guard=None,
    )

    result = assembler.assemble(**copy.deepcopy(package_inputs))

    assert result["ok"] is False
    assert "PACKAGE_REPLAY_GUARD_UNAVAILABLE" in result["reasons"]
    assert result["package_receipt"] is None


def test_harness_is_sanitized_offline_and_non_applicable() -> None:
    result = harness.run_synthetic_c3_controlled_repair_package_harness_v1(ROOT)

    assert result["ok"] is True
    assert result["input_preserved"] is True
    assert result["replay_denied"] is True
    assert result["package_assembled_offline"] is True
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


def test_package_module_has_no_apply_runtime_or_external_surface() -> None:
    tree = ast.parse(inspect.getsource(package_module))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imports
    assert "trade_registry" not in imports
    assert "broker" not in imports
    source = inspect.getsource(package_module)
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
    assert not hasattr(package_module, "activate")
    assert not hasattr(package_module, "apply")
