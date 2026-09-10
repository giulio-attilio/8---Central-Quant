"""Synthetic harness for the dormant C3 repair-controller binding."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_operation_v1 as operation
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as readiness_contract
import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_harness_v1 as readiness_harness
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as seam
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLER-BINDING-HARNESS-V1"
)


def build_synthetic_c3_repair_controller_binding_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    readiness_inputs = readiness_harness.build_synthetic_c3_runtime_readiness_binding_inputs_v1(
        repository_root
    )
    readiness_result = readiness_contract.evaluate_c3_runtime_readiness_binding_policy_offline_v1(
        **readiness_inputs
    )
    if readiness_result.get("ok") is not True:
        raise AssertionError("upstream readiness-binding contract failed closed")
    readiness_receipt = readiness_result["binding_receipt"]
    plan = contract.canonical_c3_controller_binding_plan_v1()
    spec = {
        "spec_version": "C3_REPAIR_CONTROLLER_BINDING_OFFLINE_V1",
        "upstream_readiness_binding_receipt_sha256": readiness_receipt[
            "binding_receipt_sha256"
        ],
        "binding_plan": plan,
        "binding_plan_sha256": contract._stable_sha256(plan),
        "controller_config": {
            "apply_enabled": False,
            "apply_scope_attestation": None,
            "preview_available": True,
            "preview_apply_allowed": False,
            "unknown_config_fields_denied": True,
        },
        "installation_state": {
            "installed": True,
            "enabled": False,
            "coordination_ready": False,
            "runtime_activation_allowed": False,
            "registered_writer_count": 0,
        },
        "authorization_state": {
            "scope_attestation": "C3_REPAIR_CONTROLLER_BINDING_OFFLINE_ONLY_V1",
            "offline_binding_authorized": True,
            "activation_requested": False,
            "activation_receipt": None,
            "production_authorization": None,
            "production_dependencies_bound": False,
            "runtime_patch_authorized": False,
            "repair_apply_authorized": False,
            "live_authorized": False,
            "order_submission_authorized": False,
        },
        "safety_envelope": {
            "synthetic_dependencies_only": True,
            "main_imported": False,
            "main_modified": False,
            "environment_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "fail_closed": True,
        },
        "binding_mode": "SYNTHETIC_DORMANT",
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
    }
    spec["spec_sha256"] = contract.controller_binding_spec_sha256_v1(spec)
    return {
        "readiness_binding_result": readiness_result,
        "controller_binding_spec": spec,
    }


def run_synthetic_c3_repair_controller_binding_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_repair_controller_binding_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    first = contract.evaluate_c3_repair_controller_binding_offline_v1(**inputs)
    second = contract.evaluate_c3_repair_controller_binding_offline_v1(
        **copy.deepcopy(inputs)
    )
    if first.get("synthetic_binding_allowed") is not True:
        return {
            "ok": False,
            "status": "C3_REPAIR_CONTROLLER_BINDING_HARNESS_FAILED_CLOSED",
            "binding_result": first,
        }

    coordinator = coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1()
    installation = seam.install_dormant_c3_closed_repair_writer_coordinator_v1(
        coordinator
    )
    dependency_calls = {
        "registry_loader": 0,
        "conflict_auditor": 0,
        "registry_lock": 0,
        "trading_controls": 0,
    }

    def forbidden_dependency(name: str):
        def call(*_args, **_kwargs):
            dependency_calls[name] += 1
            raise AssertionError(f"dormant controller called {name}")

        return call

    root = Path(repository_root).resolve()
    controller = operation.ClosedIdentityRepairRuntimeOperationV1(
        registry_loader=forbidden_dependency("registry_loader"),
        conflict_auditor=forbidden_dependency("conflict_auditor"),
        registry_lock=forbidden_dependency("registry_lock"),
        trading_controls=forbidden_dependency("trading_controls"),
        target_path=root / ".synthetic_c3_controller_binding" / "registry.json",
        backup_root=root / ".synthetic_c3_controller_binding" / "backups",
        writer_coordination_status=seam.c3_closed_repair_writer_coordination_status_v1,
        maintenance_lease=coordinator.maintenance_lease,
        config=operation.ClosedIdentityRepairRuntimeConfigV1(),
        clock=lambda: 0.0,
    )
    snapshot = controller.snapshot()
    denied = controller.apply({})
    status = seam.c3_closed_repair_writer_coordination_status_v1()
    coordination_binding_exact = bool(
        controller._writer_coordination_status
        is seam.c3_closed_repair_writer_coordination_status_v1
    )
    lease = controller._maintenance_lease
    maintenance_binding_exact = bool(
        getattr(lease, "__self__", None) is coordinator
        and getattr(lease, "__func__", None)
        is coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1.maintenance_lease
    )
    ok = bool(
        first.get("ok") is True
        and first == second
        and inputs == before
        and installation.get("enabled") is False
        and installation.get("coordination_ready") is False
        and status.get("runtime_activation_allowed") is False
        and snapshot.get("apply_enabled") is False
        and snapshot.get("apply_configured") is False
        and snapshot.get("apply_scope_attested") is False
        and snapshot.get("writer_coordination_bound") is True
        and snapshot.get("maintenance_lease_bound") is True
        and coordination_binding_exact
        and maintenance_binding_exact
        and denied.get("status") == "REPAIR_APPLY_DEFAULT_OFF"
        and denied.get("write_executed") is False
        and denied.get("no_order_sent") is True
        and all(value == 0 for value in dependency_calls.values())
    )
    return {
        "ok": ok,
        "status": (
            "C3_REPAIR_CONTROLLER_BINDING_HARNESS_PASSED_OFFLINE_DORMANT"
            if ok
            else "C3_REPAIR_CONTROLLER_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "controller_constructed": True,
        "controller_apply_enabled": False,
        "coordination_binding_exact": coordination_binding_exact,
        "maintenance_binding_exact": maintenance_binding_exact,
        "dependency_calls": dependency_calls,
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
        "deterministic": first == second,
        "installation_snapshot": installation,
        "controller_snapshot": snapshot,
        "default_off_apply_result": denied,
        "binding_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_c3_repair_controller_binding_inputs_v1",
    "run_synthetic_c3_repair_controller_binding_harness_v1",
]
