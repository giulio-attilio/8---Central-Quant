from __future__ import annotations

import ast
import copy
import inspect
from pathlib import Path

import pytest

import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_harness_v1 as harness
import trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1 as contract


ROOT = Path(__file__).resolve().parents[1]


def _evaluate(sources: dict[str, str]) -> dict:
    return contract.evaluate_c3_apply_schema_static_conformance_offline_v1(
        **sources,
        config=harness.build_enabled_static_conformance_config_v1(),
    )


def test_synthetic_snapshot_is_verified_but_remains_non_executable() -> None:
    result = _evaluate(harness.build_synthetic_apply_schema_sources_v1())

    assert result["ok"] is True
    assert result["static_conformance_verified"] is True
    assert result["drift_detected"] is False
    assert result["direct_controller_schema_compatible"] is True
    assert result["http_route_payload_compatible"] is False
    assert result["deadline_semantics_aligned"] is False
    assert result["authorization_gateway_bound"] is False
    assert result["same_runtime_instance_verified"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False
    assert result["no_order_sent"] is True
    assert result["conformance_receipt"]["controller_request_fields"] == [
        "ack",
        "preview_receipt_sha256",
    ]


def test_current_repository_sources_conform_without_importing_runtime() -> None:
    sources = {
        "operation_source": (
            ROOT
            / "trade_registry_closed_identity_conflict_repair_runtime_operation_v1.py"
        ).read_text(encoding="utf-8"),
        "route_source": (ROOT / "main.py").read_text(encoding="utf-8"),
        "adapter_source": (
            ROOT
            / "trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1.py"
        ).read_text(encoding="utf-8"),
    }

    result = _evaluate(sources)

    assert result["ok"] is True
    assert result["static_conformance_verified"] is True
    assert result["drift_detected"] is False
    assert result["direct_controller_schema_compatible"] is True
    assert result["http_route_payload_compatible"] is False
    assert result["deadline_semantics_aligned"] is False
    assert result["authorization_gateway_bound"] is False
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False


@pytest.mark.parametrize(
    ("source_name", "old", "new", "failed_check"),
    [
        (
            "operation_source",
            "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1",
            "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V2",
            "operation_ack_exact",
        ),
        (
            "adapter_source",
            "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V1",
            "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_APPLY_V2",
            "adapter_ack_exact",
        ),
        (
            "operation_source",
            'request_payload.get("preview_receipt_sha256")',
            'request_payload.get("preview_sha256")',
            "controller_request_fields_exact",
        ),
        (
            "adapter_source",
            '["ack", "preview_receipt_sha256"]',
            '["ack", "preview_sha256"]',
            "adapter_request_fields_exact",
        ),
        (
            "route_source",
            '{"preview", "apply"}',
            '{"preview", "execute"}',
            "route_operations_exact",
        ),
        (
            "route_source",
            'controller.apply(decision["payload"])',
            'controller.execute(decision["payload"])',
            "route_apply_dispatch_exact",
        ),
        (
            "adapter_source",
            "    expires_at_epoch: int",
            "    deadline_epoch: int",
            "protected_dto_fields_exact",
        ),
        (
            "operation_source",
            'self._pending.get(receipt_sha)',
            'self._pending.get("latest")',
            "same_instance_pending_lookup_present",
        ),
        (
            "operation_source",
            'int(self._clock()) > int(receipt["expires_at_epoch"])',
            'int(self._clock()) >= int(receipt["expires_at_epoch"])',
            "controller_expiry_snapshot_is_legacy_gt",
        ),
        (
            "adapter_source",
            "assembled <= now < expiry",
            "assembled <= now <= expiry",
            "adapter_expiry_is_strict_lt",
        ),
    ],
)
def test_any_reviewed_surface_drift_fails_closed(
    source_name: str, old: str, new: str, failed_check: str
) -> None:
    sources = harness.build_synthetic_apply_schema_sources_v1()
    assert old in sources[source_name]
    sources[source_name] = sources[source_name].replace(old, new, 1)

    result = _evaluate(sources)

    assert result["ok"] is False
    assert result["static_conformance_verified"] is False
    assert result["drift_detected"] is True
    assert result["checks"][failed_check] is False
    assert result["conformance_receipt"] is None
    assert result["apply_allowed"] is False
    assert result["activation_allowed"] is False
    assert result["live_allowed"] is False


@pytest.mark.parametrize(
    ("source_name", "source_value"),
    [
        ("operation_source", ""),
        ("route_source", "def broken("),
        ("adapter_source", "\x00"),
        ("operation_source", None),
    ],
)
def test_invalid_source_fails_closed(source_name: str, source_value: object) -> None:
    sources = harness.build_synthetic_apply_schema_sources_v1()
    sources[source_name] = source_value

    result = _evaluate(sources)

    assert result["ok"] is False
    assert result["drift_detected"] is True
    assert result["conformance_receipt"] is None
    assert result["apply_allowed"] is False
    assert result["runtime_invoked"] is False


def test_default_off_and_scope_attestation_are_required() -> None:
    sources = harness.build_synthetic_apply_schema_sources_v1()

    default_result = contract.evaluate_c3_apply_schema_static_conformance_offline_v1(
        **sources
    )
    wrong_scope = contract.evaluate_c3_apply_schema_static_conformance_offline_v1(
        **sources,
        config=contract.StaticApplySchemaConformanceConfigV1(
            enabled=True, scope_attestation="wrong"
        ),
    )

    assert default_result["status"] == "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_DEFAULT_OFF"
    assert wrong_scope["status"] == "C3_APPLY_SCHEMA_STATIC_CONFORMANCE_SCOPE_REQUIRED"
    for result in (default_result, wrong_scope):
        assert result["ok"] is False
        assert result["apply_allowed"] is False
        assert result["runtime_invoked"] is False


def test_receipt_is_deterministic_and_bound_to_all_source_snapshots() -> None:
    sources = harness.build_synthetic_apply_schema_sources_v1()
    first = _evaluate(copy.deepcopy(sources))
    second = _evaluate(copy.deepcopy(sources))

    assert first["conformance_receipt"] == second["conformance_receipt"]
    receipt = first["conformance_receipt"]
    supplied = receipt["conformance_receipt_sha256"]
    payload = {key: value for key, value in receipt.items() if key != "conformance_receipt_sha256"}
    assert supplied == contract._stable_sha256(payload)
    assert len({receipt[key] for key in (
        "operation_source_sha256",
        "route_source_sha256",
        "adapter_source_sha256",
    )}) == 3


def test_harness_reports_known_blockers_and_no_external_effects() -> None:
    result = harness.run_synthetic_apply_schema_static_conformance_harness_v1()

    assert result["ok"] is True
    assert result["known_blockers"] == [
        "HTTP_ROUTE_REQUIRES_OPERATION_ENVELOPE_NOT_PRESENT_IN_PROJECTED_FIELDS",
        "CONTROLLER_DOES_NOT_CONSUME_PACKAGE_AUTHORIZATION_OR_RESERVATION",
        "SAME_RUNTIME_INSTANCE_IS_NOT_PROVEN_BY_OFFLINE_DTO",
        "CONTROLLER_AND_ADAPTER_DEADLINE_SEMANTICS_DIFFER",
        "CONTROLLER_ACCEPTS_UNKNOWN_REQUEST_FIELDS",
        "ADAPTER_HAS_NO_RUNTIME_BINDING_OR_INVOCATION_SURFACE",
    ]
    assert result["runtime_binding_satisfied"] is False
    assert result["production_ready"] is False
    assert result["apply_allowed"] is False
    assert result["real_registry_accessed"] is False
    assert result["network_accessed"] is False
    assert result["write_executed"] is False
    assert result["no_order_sent"] is True


def test_contract_and_harness_have_no_runtime_or_external_surface() -> None:
    modules = (contract, harness)
    source = "\n".join(inspect.getsource(module) for module in modules)
    imported = {
        alias.name
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "main" not in imported
    assert "trade_registry_closed_identity_conflict_repair_runtime_operation_v1" not in imported
    assert "trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1" not in imported
    for token in (
        "Path(",
        "read_text(",
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
    executable_calls = [
        node
        for module in modules
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Call)
    ]
    assert not any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "apply"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "controller"
        for node in executable_calls
    )
    assert not hasattr(contract, "apply")
    assert not hasattr(contract, "activate")
    assert not hasattr(contract, "serialize")
