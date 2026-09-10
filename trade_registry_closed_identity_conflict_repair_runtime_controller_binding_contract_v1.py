"""Offline contract for the dormant C3 repair-controller binding.

The contract describes the exact dependency wiring required by the repair
controller, but authorizes only a synthetic, default-off construction.  It has
no runtime import, activation callable, environment access or persistence
surface.  Production binding and repair apply remain separately authorized
operations.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1 as readiness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-CONTROLLER-BINDING-CONTRACT-V1"
)

_SPEC_VERSION = "C3_REPAIR_CONTROLLER_BINDING_OFFLINE_V1"
_SCOPE_ATTESTATION = "C3_REPAIR_CONTROLLER_BINDING_OFFLINE_ONLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_SPEC_KEYS = frozenset(
    {
        "spec_version",
        "upstream_readiness_binding_receipt_sha256",
        "binding_plan",
        "binding_plan_sha256",
        "controller_config",
        "installation_state",
        "authorization_state",
        "safety_envelope",
        "binding_mode",
        "dormant",
        "default_off",
        "offline_only",
        "synthetic_only",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "spec_sha256",
    }
)
_CONFIG_KEYS = frozenset(
    {
        "apply_enabled",
        "apply_scope_attestation",
        "preview_available",
        "preview_apply_allowed",
        "unknown_config_fields_denied",
    }
)
_INSTALLATION_KEYS = frozenset(
    {
        "installed",
        "enabled",
        "coordination_ready",
        "runtime_activation_allowed",
        "registered_writer_count",
    }
)
_AUTHORIZATION_KEYS = frozenset(
    {
        "scope_attestation",
        "offline_binding_authorized",
        "activation_requested",
        "activation_receipt",
        "production_authorization",
        "production_dependencies_bound",
        "runtime_patch_authorized",
        "repair_apply_authorized",
        "live_authorized",
        "order_submission_authorized",
    }
)
_SAFETY_KEYS = frozenset(
    {
        "synthetic_dependencies_only",
        "main_imported",
        "main_modified",
        "environment_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "no_order_sent",
        "fail_closed",
    }
)

_BINDING_PLAN = (
    {
        "target": "controller.writer_coordination_status",
        "source": "runtime_seam.c3_closed_repair_writer_coordination_status_v1",
        "required": True,
    },
    {
        "target": "controller.maintenance_lease",
        "source": "dormant_coordinator.maintenance_lease",
        "required": True,
    },
    {
        "target": "controller.config",
        "source": "runtime_operation.ClosedIdentityRepairRuntimeConfigV1",
        "required": True,
    },
)

_PRODUCTION_BLOCKERS = (
    "CONTROLLER_BINDING_IS_SYNTHETIC_ONLY",
    "CONTROLLER_APPLY_REMAINS_DEFAULT_OFF",
    "APPLY_SCOPE_ATTESTATION_IS_ABSENT",
    "ACTIVATION_RECEIPT_IS_ABSENT",
    "PRODUCTION_AUTHORIZATION_IS_ABSENT",
    "PRODUCTION_DEPENDENCIES_ARE_NOT_BOUND",
    "RUNTIME_MAIN_IS_NOT_MODIFIED",
    "REAL_REGISTRY_IS_NOT_ACCESSED",
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


def _receipt_sha256(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def canonical_c3_controller_binding_plan_v1() -> list[dict[str, Any]]:
    return _canonical_copy(list(_BINDING_PLAN))


def controller_binding_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "binding_contract_verified": False,
        "upstream_readiness_binding_verified": False,
        "binding_plan_verified": False,
        "default_off_config_verified": False,
        "synthetic_binding_allowed": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "status": "C3_REPAIR_CONTROLLER_BINDING_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "runtime_imported": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "binding_receipt": None,
    }


def _check_upstream(
    upstream: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    receipt = upstream.get("binding_receipt")
    supplied = (
        _valid_sha256(receipt.get("binding_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected = (
        _receipt_sha256(receipt, "binding_receipt_sha256")
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_readiness_receipt_valid"] = bool(
        upstream.get("ok") is True
        and upstream.get("version")
        == readiness.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_CONTRACT_V1_VERSION
        and upstream.get("binding_contract_verified") is True
        and upstream.get("runtime_readiness_policy_verified") is True
        and upstream.get("runtime_binding_satisfied") is False
        and upstream.get("production_ready") is False
        and upstream.get("apply_allowed") is False
        and upstream.get("activation_allowed") is False
        and upstream.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and hmac.compare_digest(supplied, expected)
        and receipt.get("source_attestation_count") == 4
        and receipt.get("writer_count") == 19
        and receipt.get("required_predicate_count")
        == len(readiness.canonical_c3_live_preflight_predicates_v1())
        and receipt.get("runtime_binding_satisfied") is False
        and receipt.get("apply_allowed") is False
        and receipt.get("activation_allowed") is False
        and receipt.get("live_allowed") is False
        and bool(receipt.get("production_blockers"))
    )
    if not checks["upstream_readiness_receipt_valid"]:
        reasons.append("CONTROLLER_BINDING_UPSTREAM_READINESS_RECEIPT_INVALID")
    return supplied


def _check_plan(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    expected = canonical_c3_controller_binding_plan_v1()
    expected_sha = _stable_sha256(expected)
    plan = spec.get("binding_plan")
    checks["binding_plan_exact"] = bool(
        plan == expected
        and len(expected) == 3
        and len({item["target"] for item in expected}) == 3
        and all(item.get("required") is True for item in expected)
        and spec.get("binding_plan_sha256") == expected_sha
    )
    if not checks["binding_plan_exact"]:
        reasons.append("CONTROLLER_BINDING_PLAN_INVALID")
    return expected_sha


def _check_dormant_config(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> None:
    config = spec.get("controller_config")
    installation = spec.get("installation_state")
    authorization = spec.get("authorization_state")
    checks["controller_config_strictly_default_off"] = bool(
        isinstance(config, Mapping)
        and set(config) == _CONFIG_KEYS
        and config.get("apply_enabled") is False
        and config.get("apply_scope_attestation") is None
        and config.get("preview_available") is True
        and config.get("preview_apply_allowed") is False
        and config.get("unknown_config_fields_denied") is True
    )
    checks["installation_state_strictly_dormant"] = bool(
        isinstance(installation, Mapping)
        and set(installation) == _INSTALLATION_KEYS
        and installation.get("installed") is True
        and installation.get("enabled") is False
        and installation.get("coordination_ready") is False
        and installation.get("runtime_activation_allowed") is False
        and installation.get("registered_writer_count") == 0
    )
    checks["production_authorization_absent"] = bool(
        isinstance(authorization, Mapping)
        and set(authorization) == _AUTHORIZATION_KEYS
        and authorization.get("scope_attestation") == _SCOPE_ATTESTATION
        and authorization.get("offline_binding_authorized") is True
        and authorization.get("activation_requested") is False
        and authorization.get("activation_receipt") is None
        and authorization.get("production_authorization") is None
        and authorization.get("production_dependencies_bound") is False
        and authorization.get("runtime_patch_authorized") is False
        and authorization.get("repair_apply_authorized") is False
        and authorization.get("live_authorized") is False
        and authorization.get("order_submission_authorized") is False
    )
    for check, reason in (
        ("controller_config_strictly_default_off", "CONTROLLER_BINDING_CONFIG_NOT_DEFAULT_OFF"),
        ("installation_state_strictly_dormant", "CONTROLLER_BINDING_INSTALLATION_NOT_DORMANT"),
        ("production_authorization_absent", "CONTROLLER_BINDING_PRODUCTION_AUTHORIZATION_CLAIMED"),
    ):
        if not checks[check]:
            reasons.append(reason)


def _check_safety(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> None:
    safety = spec.get("safety_envelope")
    checks["safety_envelope_offline_only"] = bool(
        isinstance(safety, Mapping)
        and set(safety) == _SAFETY_KEYS
        and safety.get("synthetic_dependencies_only") is True
        and safety.get("main_imported") is False
        and safety.get("main_modified") is False
        and safety.get("environment_accessed") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("broker_called") is False
        and safety.get("write_executed") is False
        and safety.get("no_order_sent") is True
        and safety.get("fail_closed") is True
    )
    if not checks["safety_envelope_offline_only"]:
        reasons.append("CONTROLLER_BINDING_SAFETY_ENVELOPE_INVALID")


def evaluate_c3_repair_controller_binding_offline_v1(
    readiness_binding_result: Mapping[str, Any],
    controller_binding_spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Authorize only a synthetic, dormant controller construction."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not isinstance(readiness_binding_result, Mapping) or not isinstance(
        controller_binding_spec, Mapping
    ):
        reasons.append("CONTROLLER_BINDING_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(readiness_binding_result)
        spec = _canonical_copy(controller_binding_spec)
    except (TypeError, ValueError, OverflowError):
        reasons.append("CONTROLLER_BINDING_INPUT_NOT_CANONICALIZABLE")
        return base

    upstream_sha = _check_upstream(upstream, reasons, checks)
    plan_sha = _check_plan(spec, reasons, checks)
    _check_dormant_config(spec, reasons, checks)
    _check_safety(spec, reasons, checks)

    supplied_spec_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["binding_spec_sha256_valid"] = bool(
        supplied_spec_sha
        and hmac.compare_digest(
            supplied_spec_sha,
            controller_binding_spec_sha256_v1(spec),
        )
    )
    checks["binding_spec_envelope_exact"] = bool(
        set(spec) == _SPEC_KEYS
        and spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_readiness_binding_receipt_sha256") == upstream_sha
        and spec.get("binding_mode") == "SYNTHETIC_DORMANT"
        and spec.get("dormant") is True
        and spec.get("default_off") is True
        and spec.get("offline_only") is True
        and spec.get("synthetic_only") is True
        and spec.get("runtime_binding_satisfied") is False
        and spec.get("production_ready") is False
        and spec.get("apply_allowed") is False
        and spec.get("activation_allowed") is False
        and spec.get("live_allowed") is False
    )
    if not checks["binding_spec_sha256_valid"]:
        reasons.append("CONTROLLER_BINDING_SPEC_SHA256_INVALID")
    if not checks["binding_spec_envelope_exact"]:
        reasons.append("CONTROLLER_BINDING_SPEC_ENVELOPE_INVALID")

    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_CONTROLLER_BINDING_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_readiness_binding_receipt_sha256": upstream_sha,
        "controller_binding_spec_sha256": supplied_spec_sha,
        "binding_plan_sha256": plan_sha,
        "binding_count": 3,
        "writer_count": 19,
        "synthetic_binding_allowed": True,
        "controller_apply_enabled": False,
        "apply_scope_attestation_present": False,
        "activation_receipt_consumed": False,
        "production_authorization_consumed": False,
        "production_dependencies_bound": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["binding_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "binding_contract_verified": True,
            "upstream_readiness_binding_verified": True,
            "binding_plan_verified": True,
            "default_off_config_verified": True,
            "synthetic_binding_allowed": True,
            "status": "C3_REPAIR_CONTROLLER_BINDING_V1_VALID_OFFLINE_DORMANT",
            "reasons": [],
            "checks": checks,
            "binding_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLER_BINDING_CONTRACT_V1_VERSION",
    "canonical_c3_controller_binding_plan_v1",
    "controller_binding_spec_sha256_v1",
    "evaluate_c3_repair_controller_binding_offline_v1",
]
