"""Offline contract for a future controlled C3 runtime activation proposal.

The contract consumes only already-sanitized, deterministic evidence.  It has
no activation, patching, persistence, environment, runtime, network or broker
surface.  Even a fully valid proposal remains default-off and requires a
separate production patch and authorization.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_CONTRACT_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLED-ACTIVATION-CONTRACT-V1"
)

_PROPOSAL_VERSION = "C3_CONTROLLED_RUNTIME_ACTIVATION_PROPOSAL_OFFLINE_V1"
_SCOPE_ATTESTATION = "C3_CONTROLLED_ACTIVATION_REVIEW_OFFLINE_ONLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PRODUCTION_BLOCKERS = (
    "CONTROLLED_ACTIVATION_IS_PROPOSAL_ONLY",
    "PATCH_CONTENT_ABSENT",
    "RUNTIME_INSTALL_ENTRYPOINT_ABSENT",
    "DORMANT_SEAM_REJECTS_ENABLED_COORDINATOR",
    "REAL_WRITER_QUIESCENCE_NOT_OBSERVED",
    "REAL_SHARED_LOCK_NOT_ACQUIRED",
    "REAL_REGISTRY_NOT_ACCESSED",
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


def controlled_activation_proposal_sha256_v1(
    proposal: Mapping[str, Any],
) -> str:
    if not isinstance(proposal, Mapping):
        raise TypeError("proposal must be a mapping")
    return _stable_sha256(
        {key: value for key, value in proposal.items() if key != "proposal_sha256"}
    )


def _receipt_sha256(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "proposal_contract_verified": False,
        "upstream_patch_plan_verified": False,
        "writer_inventory_verified": False,
        "safety_controls_verified": False,
        "dormant_seam_verified": False,
        "production_ready": False,
        "activation_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "C3_CONTROLLED_RUNTIME_ACTIVATION_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "proposal_only": True,
        "read_only": True,
        "activation_callable_present": False,
        "activation_token": None,
        "patch_content_present": False,
        "write_executed": False,
        "source_file_written": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "proposal_receipt": None,
    }


def _check_upstream_patch_plan(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    receipt = result.get("patch_plan_receipt")
    receipt_sha = (
        _valid_sha256(receipt.get("patch_plan_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _receipt_sha256(receipt, "patch_plan_receipt_sha256")
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_patch_plan_valid"] = bool(
        result.get("ok") is True
        and result.get("patch_plan_contract_verified") is True
        and result.get("source_preconditions_verified") is True
        and result.get("synthetic_rehearsal_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("runtime_start_allowed") is False
        and result.get("live_allowed") is False
        and result.get("patch_content_present") is False
        and result.get("source_file_written") is False
        and result.get("write_executed") is False
        and result.get("runtime_integrated") is False
        and isinstance(receipt, Mapping)
        and receipt_sha
        and hmac.compare_digest(receipt_sha, expected_sha)
        and receipt.get("source_file_count") == 9
        and receipt.get("writer_operation_count") == 19
        and receipt.get("source_hashes_must_be_rechecked") is True
        and receipt.get("apply_allowed") is False
        and receipt.get("runtime_install_allowed") is False
        and receipt.get("runtime_start_allowed") is False
        and receipt.get("live_allowed") is False
        and bool(receipt.get("production_blockers"))
    )
    if not checks["upstream_patch_plan_valid"]:
        reasons.append("CONTROLLED_ACTIVATION_UPSTREAM_PATCH_PLAN_INVALID")
    return receipt_sha


def _check_writer_inventory(
    proposal: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    expected = coordination.canonical_closed_repair_writer_inventory_v1()
    inventory = proposal.get("writer_inventory")
    expected_sha = _stable_sha256(expected)
    checks["writer_inventory_exact"] = bool(
        isinstance(inventory, list)
        and inventory == expected
        and len(inventory) == 19
        and len({item.get("writer_id") for item in inventory}) == 19
        and proposal.get("writer_inventory_sha256") == expected_sha
    )
    if not checks["writer_inventory_exact"]:
        reasons.append("CONTROLLED_ACTIVATION_WRITER_INVENTORY_NOT_EXACT")
    return expected_sha


def _check_dormant_seam(
    evidence: Any, reasons: list[str], checks: dict[str, bool]
) -> None:
    checks["dormant_seam_state_exact"] = bool(
        isinstance(evidence, Mapping)
        and evidence.get("status") == "C3_WRITER_COORDINATION_DORMANT_DEFAULT_OFF"
        and evidence.get("installed") is True
        and evidence.get("enabled") is False
        and evidence.get("coordination_ready") is False
        and evidence.get("runtime_activation_allowed") is False
        and evidence.get("registered_writer_count") == 0
        and evidence.get("real_registry_accessed") is False
        and evidence.get("network_accessed") is False
        and evidence.get("broker_called") is False
        and evidence.get("no_order_sent") is True
    )
    if not checks["dormant_seam_state_exact"]:
        reasons.append("CONTROLLED_ACTIVATION_DORMANT_SEAM_INVALID")


def _check_safety_controls(
    controls: Any, reasons: list[str], checks: dict[str, bool]
) -> None:
    checks["trading_controls_safe"] = bool(
        isinstance(controls, Mapping)
        and controls.get("enable_real_trading") is False
        and controls.get("broker_dry_run") is True
        and controls.get("falcon_mode") == "VERIFY"
        and controls.get("central_real_execution_enabled") is False
        and controls.get("central_real_pilot_enabled") is False
        and controls.get("auto_deploy_enabled") is False
        and controls.get("canary_enabled") is False
        and controls.get("fast_path_enabled") is False
        and controls.get("live_trading_enabled") is False
        and controls.get("order_submission_authorized") is False
    )
    checks["registry_controls_safe"] = bool(
        isinstance(controls, Mapping)
        and controls.get("registry_interlock_required") is True
        and controls.get("registry_interlock_ready_synthetic") is True
        and controls.get("real_registry_observed") is False
        and controls.get("real_writer_quiescence_observed") is False
        and controls.get("real_shared_lock_acquired") is False
        and controls.get("zero_inflight_required") is True
    )
    for check, reason in (
        ("trading_controls_safe", "CONTROLLED_ACTIVATION_TRADING_CONTROLS_UNSAFE"),
        ("registry_controls_safe", "CONTROLLED_ACTIVATION_REGISTRY_CONTROLS_UNSAFE"),
    ):
        if not checks[check]:
            reasons.append(reason)


def _check_activation_window(
    window: Any, reasons: list[str], checks: dict[str, bool]
) -> None:
    duration = window.get("max_duration_seconds") if isinstance(window, Mapping) else None
    rollback = window.get("rollback_deadline_seconds") if isinstance(window, Mapping) else None
    numeric = (
        not isinstance(duration, bool)
        and not isinstance(rollback, bool)
        and isinstance(duration, (int, float))
        and isinstance(rollback, (int, float))
        and math.isfinite(float(duration))
        and math.isfinite(float(rollback))
    )
    checks["activation_window_bounded"] = bool(
        isinstance(window, Mapping)
        and numeric
        and 1.0 <= float(duration) <= 300.0
        and 1.0 <= float(rollback) <= float(duration)
        and window.get("max_inflight_mutations_before_activation") == 0
        and window.get("fail_closed") is True
        and window.get("auto_rollback_on_failure") is True
        and window.get("rollback_preserves_registry_preimage") is True
        and window.get("deadline_injected") is True
    )
    if not checks["activation_window_bounded"]:
        reasons.append("CONTROLLED_ACTIVATION_WINDOW_INVALID")


def _check_authorization(
    authorization: Any, reasons: list[str], checks: dict[str, bool]
) -> None:
    checks["authorization_scope_offline_only"] = bool(
        isinstance(authorization, Mapping)
        and authorization.get("scope_attestation") == _SCOPE_ATTESTATION
        and authorization.get("offline_contract_authorized") is True
        and authorization.get("runtime_patch_authorized") is False
        and authorization.get("production_activation_authorized") is False
        and authorization.get("live_activation_authorized") is False
        and authorization.get("order_submission_authorized") is False
        and authorization.get("separate_production_patch_required") is True
        and authorization.get("separate_production_authorization_required") is True
    )
    if not checks["authorization_scope_offline_only"]:
        reasons.append("CONTROLLED_ACTIVATION_AUTHORIZATION_SCOPE_INVALID")


def evaluate_c3_controlled_runtime_activation_proposal_offline_v1(
    upstream_patch_plan_result: Mapping[str, Any],
    activation_proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a proposal while permanently denying runtime activation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not isinstance(upstream_patch_plan_result, Mapping) or not isinstance(
        activation_proposal, Mapping
    ):
        reasons.append("CONTROLLED_ACTIVATION_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(upstream_patch_plan_result)
        proposal = _canonical_copy(activation_proposal)
    except (TypeError, ValueError, OverflowError):
        reasons.append("CONTROLLED_ACTIVATION_INPUT_NOT_CANONICALIZABLE")
        return base

    patch_receipt_sha = _check_upstream_patch_plan(upstream, reasons, checks)
    supplied_proposal_sha = _valid_sha256(proposal.get("proposal_sha256"))
    checks["proposal_sha256_valid"] = bool(
        supplied_proposal_sha
        and hmac.compare_digest(
            supplied_proposal_sha,
            controlled_activation_proposal_sha256_v1(proposal),
        )
    )
    if not checks["proposal_sha256_valid"]:
        reasons.append("CONTROLLED_ACTIVATION_PROPOSAL_SHA256_INVALID")

    inventory_sha = _check_writer_inventory(proposal, reasons, checks)
    _check_dormant_seam(proposal.get("dormant_seam_evidence"), reasons, checks)
    _check_safety_controls(proposal.get("safety_controls"), reasons, checks)
    _check_activation_window(proposal.get("activation_window"), reasons, checks)
    _check_authorization(proposal.get("authorization"), reasons, checks)

    checks["proposal_envelope_safe"] = bool(
        proposal.get("proposal_version") == _PROPOSAL_VERSION
        and proposal.get("upstream_patch_plan_receipt_sha256") == patch_receipt_sha
        and proposal.get("proposal_only") is True
        and proposal.get("dormant") is True
        and proposal.get("default_off") is True
        and proposal.get("offline_only") is True
        and proposal.get("synthetic_only") is True
        and proposal.get("activation_requested") is False
        and proposal.get("patch_content_present") is False
        and proposal.get("activation_callable_present") is False
        and proposal.get("runtime_integrated") is False
        and proposal.get("real_registry_accessed") is False
        and proposal.get("network_accessed") is False
        and proposal.get("broker_called") is False
        and proposal.get("write_executed") is False
        and proposal.get("no_order_sent") is True
    )
    if not checks["proposal_envelope_safe"]:
        reasons.append("CONTROLLED_ACTIVATION_PROPOSAL_ENVELOPE_UNSAFE")

    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_CONTROLLED_ACTIVATION_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_patch_plan_receipt_sha256": patch_receipt_sha,
        "activation_proposal_sha256": supplied_proposal_sha,
        "writer_inventory_sha256": inventory_sha,
        "writer_count": 19,
        "all_offline_checks_passed": True,
        "proposal_only": True,
        "source_hashes_must_be_rechecked": True,
        "production_ready": False,
        "activation_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["proposal_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "proposal_contract_verified": True,
            "upstream_patch_plan_verified": True,
            "writer_inventory_verified": True,
            "safety_controls_verified": True,
            "dormant_seam_verified": True,
            "status": "C3_CONTROLLED_RUNTIME_ACTIVATION_V1_VALID_OFFLINE_ACTIVATION_DENIED",
            "reasons": [],
            "checks": checks,
            "proposal_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_ACTIVATION_CONTRACT_V1_VERSION",
    "controlled_activation_proposal_sha256_v1",
    "evaluate_c3_controlled_runtime_activation_proposal_offline_v1",
]
