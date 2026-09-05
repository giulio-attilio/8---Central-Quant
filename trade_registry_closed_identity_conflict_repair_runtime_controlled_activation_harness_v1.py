"""Synthetic in-memory harness for the controlled C3 activation contract."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_contract_v1 as activation
import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_harness_v1 as patch_plan_harness
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_HARNESS_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-ACTIVATION-HARNESS-V1"
)


def build_synthetic_c3_controlled_activation_inputs_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    patch_harness = patch_plan_harness.run_closed_repair_runtime_patch_plan_harness_read_only_v1(
        repository_root
    )
    patch_result = patch_harness.get("patch_plan_result")
    if patch_harness.get("ok") is not True or not isinstance(patch_result, dict):
        raise AssertionError("upstream runtime patch-plan harness failed closed")
    patch_receipt = patch_result["patch_plan_receipt"]
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    proposal = {
        "proposal_version": "C3_CONTROLLED_RUNTIME_ACTIVATION_PROPOSAL_OFFLINE_V1",
        "upstream_patch_plan_receipt_sha256": patch_receipt[
            "patch_plan_receipt_sha256"
        ],
        "proposal_only": True,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "activation_requested": False,
        "patch_content_present": False,
        "activation_callable_present": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "writer_inventory": inventory,
        "writer_inventory_sha256": activation._stable_sha256(inventory),
        "dormant_seam_evidence": {
            "status": "C3_WRITER_COORDINATION_DORMANT_DEFAULT_OFF",
            "installed": True,
            "enabled": False,
            "coordination_ready": False,
            "runtime_activation_allowed": False,
            "registered_writer_count": 0,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        },
        "safety_controls": {
            "enable_real_trading": False,
            "broker_dry_run": True,
            "falcon_mode": "VERIFY",
            "central_real_execution_enabled": False,
            "central_real_pilot_enabled": False,
            "auto_deploy_enabled": False,
            "canary_enabled": False,
            "fast_path_enabled": False,
            "live_trading_enabled": False,
            "order_submission_authorized": False,
            "registry_interlock_required": True,
            "registry_interlock_ready_synthetic": True,
            "real_registry_observed": False,
            "real_writer_quiescence_observed": False,
            "real_shared_lock_acquired": False,
            "zero_inflight_required": True,
        },
        "activation_window": {
            "max_duration_seconds": 120.0,
            "rollback_deadline_seconds": 30.0,
            "max_inflight_mutations_before_activation": 0,
            "fail_closed": True,
            "auto_rollback_on_failure": True,
            "rollback_preserves_registry_preimage": True,
            "deadline_injected": True,
        },
        "authorization": {
            "scope_attestation": "C3_CONTROLLED_ACTIVATION_REVIEW_OFFLINE_ONLY_V1",
            "offline_contract_authorized": True,
            "runtime_patch_authorized": False,
            "production_activation_authorized": False,
            "live_activation_authorized": False,
            "order_submission_authorized": False,
            "separate_production_patch_required": True,
            "separate_production_authorization_required": True,
        },
    }
    proposal["proposal_sha256"] = activation.controlled_activation_proposal_sha256_v1(
        proposal
    )
    return {
        "upstream_patch_plan_result": patch_result,
        "activation_proposal": proposal,
    }


def run_synthetic_c3_controlled_activation_harness_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_synthetic_c3_controlled_activation_inputs_v1(repository_root)
    before = copy.deepcopy(inputs)
    before_sha = activation._stable_sha256(before)
    first = activation.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **inputs
    )
    second = activation.evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = activation._stable_sha256(inputs)
    receipt = first.get("proposal_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("proposal_contract_verified") is True
        and first.get("upstream_patch_plan_verified") is True
        and first.get("writer_inventory_verified") is True
        and first.get("safety_controls_verified") is True
        and first.get("dormant_seam_verified") is True
        and first.get("production_ready") is False
        and first.get("activation_allowed") is False
        and first.get("runtime_patch_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("live_allowed") is False
        and first.get("activation_callable_present") is False
        and first.get("activation_token") is None
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and first.get("runtime_integrated") is False
        and first.get("real_registry_accessed") is False
        and first.get("network_accessed") is False
        and first.get("broker_called") is False
        and first.get("no_order_sent") is True
        and isinstance(receipt, dict)
        and receipt.get("writer_count") == 19
        and receipt.get("activation_allowed") is False
        and receipt.get("runtime_patch_allowed") is False
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "C3_CONTROLLED_RUNTIME_ACTIVATION_V1_HARNESS_PASSED_OFFLINE_ACTIVATION_DENIED"
            if ok
            else "C3_CONTROLLED_RUNTIME_ACTIVATION_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "proposal_only": True,
        "production_ready": False,
        "activation_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "activation_callable_present": False,
        "activation_token": None,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "activation_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_HARNESS_V1_VERSION",
    "build_synthetic_c3_controlled_activation_inputs_v1",
    "run_synthetic_c3_controlled_activation_harness_v1",
]
