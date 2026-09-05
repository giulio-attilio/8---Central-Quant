"""Dormant manifest for a future CLOSED-repair runtime installation.

This module records the exact integration topology found by the read-only
runtime audit.  It validates only canonical, synthetic mappings.  It cannot
import runtime modules, bind callables, start workers, install a provider,
recover a Registry or authorize Live.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_bootstrap_gate_contract_v1 as bootstrap_gate
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-INSTALLATION-MANIFEST-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LIVE_PREFLIGHT_CODE = "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY"
_INSTALLER_FUNCTION = "_install_c3_closed_repair_writer_coordination_v1"
_RECOVERY_FUNCTION = "_recover_c3_closed_repair_registry_v1"
_RUNTIME_START_FUNCTION = "start_central_runtime_once"
_WRITER_MARKER = "_c3_closed_repair_writer_mutation_v1"

_PHASES = (
    "MANIFEST_ATTESTED_OFFLINE",
    "ALL_19_WRITER_BODY_SEAMS_AVAILABLE",
    "LIVE_PREFLIGHT_GATE_AVAILABLE_CLOSED",
    "PERSISTENCE_BOOTSTRAP_COMPLETED",
    "C3_PROVIDER_INSTALLED_DEFAULT_OFF",
    "C3_STARTUP_RECOVERY_COMPLETED",
    "BY_NAME_BOT_IMPORT_GATE_RELEASED",
    "BOT_MODULE_IMPORTS_ALLOWED",
    "CENTRAL_RUNTIME_START_ALLOWED",
)

_REQUIRED_RUNTIME_IMPORTS = (
    (
        "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1",
        "build_production_closed_repair_writer_runtime_coordinator_v1",
    ),
    (
        "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1",
        "build_production_writer_invocation_adapter_v1",
    ),
    (
        "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1",
        "build_production_raw_transaction_store_v1",
    ),
    (
        "trade_registry_closed_identity_conflict_repair_production_provider_v1",
        "build_production_closed_repair_provider_v1",
    ),
)

_BY_NAME_BOT_IMPORTS = (
    ("bots/meme.py", 65),
    ("bots/predator.py", 73),
    ("bots/turtle.py", 76),
)

_ROLLBACK_STEPS = (
    "KEEP_LIVE_PREFLIGHT_CLOSED",
    "KEEP_RUNTIME_START_CLOSED",
    "KEEP_BOT_IMPORT_GATE_CLOSED",
    "FENCE_NEW_C3_MUTATIONS",
    "DRAIN_SYNTHETIC_INFLIGHT_MUTATIONS",
    "DISCARD_UNPUBLISHED_PROVIDER_GRAPH",
    "PRESERVE_REGISTRY_BYTES_UNCHANGED",
    "REQUIRE_FRESH_PREFLIGHT_BEFORE_RETRY",
)

_PRODUCTION_BLOCKERS = (
    "RUNTIME_INSTALLATION_MANIFEST_IS_CONTRACT_ONLY",
    "REAL_RUNTIME_MODULES_NOT_IMPORTED",
    "REAL_19_WRITER_BODY_SEAMS_NOT_INSTALLED",
    "REAL_PERSISTENCE_BOOTSTRAP_NOT_REORDERED",
    "REAL_PROVIDER_NOT_INSTALLED",
    "REAL_STARTUP_RECOVERY_NOT_EXECUTED",
    "REAL_BOT_IMPORT_GATE_NOT_INSTALLED",
    "REAL_RUNTIME_START_NOT_GATED",
    "REAL_LIVE_PREFLIGHT_GATE_NOT_INSTALLED",
    "PHYSICAL_INSTALL_ENTRYPOINT_ABSENT",
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


def canonical_runtime_installation_phases_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": index * 10, "phase": phase}
        for index, phase in enumerate(_PHASES, start=1)
    ]


def canonical_runtime_installation_writer_manifest_v1() -> list[dict[str, Any]]:
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    bindings = seam_binding.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": "0" * 64}
    )
    if len(inventory) != 19 or len(bindings) != 19:
        raise AssertionError("runtime installation writer inventory diverged")
    return [
        {
            "writer_id": writer["writer_id"],
            "component": writer["component"],
            "function": writer["function"],
            "source_anchor_line": binding["source_anchor_line"],
            "source_signature_sha256": binding["source_signature_sha256"],
            "adaptation_strategy": binding["adaptation_strategy"],
            "required_target_lock_scope": "SHARED_INTERPROCESS_FULL_RMW",
            "mutation_marker": _WRITER_MARKER,
            "body_seam_required": True,
            "must_be_ready_before_bot_import": True,
            "runtime_callable_bound": False,
        }
        for writer, binding in zip(inventory, bindings, strict=True)
    ]


def canonical_runtime_installation_import_manifest_v1() -> list[dict[str, Any]]:
    direct_builders = {builder for _, builder in _REQUIRED_RUNTIME_IMPORTS[:3]}
    return [
        {
            "module": module,
            "builder": builder,
            "installer_function": _INSTALLER_FUNCTION,
            "direct_builder_call_required_by_static_preflight": builder
            in direct_builders,
            "real_module_imported": False,
            "real_builder_called": False,
        }
        for module, builder in _REQUIRED_RUNTIME_IMPORTS
    ]


def canonical_runtime_installation_bot_import_gates_v1() -> list[dict[str, Any]]:
    return [
        {
            "component": component,
            "source_anchor_line": source_anchor_line,
            "imported_functions": [
                "register_open_trade",
                "update_trade",
                "close_trade",
            ],
            "import_mode": "BY_NAME_FUNCTION_REFERENCE",
            "all_19_body_seams_required_before_import": True,
            "late_module_attribute_replacement_insufficient": True,
            "real_module_imported": False,
        }
        for component, source_anchor_line in _BY_NAME_BOT_IMPORTS
    ]


def canonical_runtime_installation_rollback_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": index * 10, "step": step}
        for index, step in enumerate(_ROLLBACK_STEPS, start=1)
    ]


def runtime_installation_manifest_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256(
        {key: value for key, value in spec.items() if key != "spec_sha256"}
    )


def runtime_installation_manifest_rehearsal_sha256_v1(
    rehearsal: Mapping[str, Any],
) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in rehearsal.items()
            if key != "rehearsal_sha256"
        }
    )


def _bootstrap_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key != "bootstrap_gate_receipt_sha256"
        }
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "installation_manifest_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "rollback_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_module_imported": False,
        "real_bot_imported": False,
        "real_thread_started": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "installation_manifest_receipt": None,
    }


def _check_upstream(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[Mapping[str, Any] | None, str]:
    receipt = result.get("bootstrap_gate_receipt")
    supplied_sha = (
        _valid_sha256(receipt.get("bootstrap_gate_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _bootstrap_receipt_sha256(receipt)
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_bootstrap_gate_valid"] = bool(
        result.get("ok") is True
        and result.get("bootstrap_gate_contract_verified") is True
        and result.get("synthetic_rehearsal_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_bootstrap_allowed") is False
        and result.get("real_bot_imported") is False
        and result.get("real_thread_started") is False
        and isinstance(receipt, Mapping)
        and supplied_sha
        and hmac.compare_digest(supplied_sha, expected_sha)
        and receipt.get("writer_count") == 19
        and receipt.get("bot_count") == 7
        and receipt.get("production_blockers")
    )
    if not checks["upstream_bootstrap_gate_valid"]:
        reasons.append("RUNTIME_INSTALLATION_MANIFEST_UPSTREAM_BOOTSTRAP_GATE_INVALID")
    return receipt if isinstance(receipt, Mapping) else None, supplied_sha


def _check_spec(
    spec: Mapping[str, Any],
    upstream_receipt: Mapping[str, Any] | None,
    upstream_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    spec_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        spec_sha
        and hmac.compare_digest(
            spec_sha, runtime_installation_manifest_spec_sha256_v1(spec)
        )
    )
    expected_writers = canonical_runtime_installation_writer_manifest_v1()
    expected_imports = canonical_runtime_installation_import_manifest_v1()
    expected_bots = canonical_runtime_installation_bot_import_gates_v1()
    expected_phases = canonical_runtime_installation_phases_v1()
    expected_rollback = canonical_runtime_installation_rollback_v1()
    writers = spec.get("writer_manifest")
    checks["writer_manifest_exact"] = bool(
        writers == expected_writers
        and len(expected_writers) == 19
        and len({item["writer_id"] for item in expected_writers}) == 19
        and spec.get("writer_manifest_sha256") == _stable_sha256(expected_writers)
    )
    imports = spec.get("runtime_import_manifest")
    direct_builder_count = sum(
        item["direct_builder_call_required_by_static_preflight"]
        for item in expected_imports
    )
    checks["runtime_import_manifest_exact"] = bool(
        imports == expected_imports
        and direct_builder_count == 3
        and spec.get("runtime_import_manifest_sha256")
        == _stable_sha256(expected_imports)
    )
    checks["bot_import_gates_exact"] = bool(
        spec.get("by_name_bot_import_gates") == expected_bots
        and len(expected_bots) == 3
        and spec.get("by_name_bot_import_gates_sha256")
        == _stable_sha256(expected_bots)
    )
    checks["installation_order_exact"] = bool(
        spec.get("installation_phases") == expected_phases
        and spec.get("installation_phases_sha256")
        == _stable_sha256(expected_phases)
        and [item["phase"] for item in expected_phases] == list(_PHASES)
    )
    checks["rollback_exact"] = bool(
        spec.get("rollback_protocol") == expected_rollback
        and spec.get("rollback_protocol_sha256")
        == _stable_sha256(expected_rollback)
    )
    provider = spec.get("provider_installation")
    checks["provider_installation_valid"] = bool(
        isinstance(provider, Mapping)
        and provider.get("installer_function") == _INSTALLER_FUNCTION
        and provider.get("aggregate_provider_builder")
        == "build_production_closed_repair_provider_v1"
        and provider.get("three_capability_builders_called_directly") is True
        and provider.get("default_enabled") is False
        and provider.get("install_before_recovery") is True
        and provider.get("install_before_bot_imports") is True
        and provider.get("install_before_runtime_start") is True
        and provider.get("late_monkey_patch_forbidden") is True
        and provider.get("real_provider_installed") is False
    )
    recovery = spec.get("startup_recovery")
    checks["startup_recovery_valid"] = bool(
        isinstance(recovery, Mapping)
        and recovery.get("function") == _RECOVERY_FUNCTION
        and recovery.get("provider_required_before_recovery") is True
        and recovery.get("clean_recovery_required_before_bot_imports") is True
        and recovery.get("clean_recovery_required_before_runtime_start") is True
        and recovery.get("unknown_or_stale_state_fails_closed") is True
        and recovery.get("real_recovery_executed") is False
    )
    live = spec.get("live_preflight_gate")
    checks["live_preflight_gate_valid"] = bool(
        isinstance(live, Mapping)
        and live.get("check_code") == _LIVE_PREFLIGHT_CODE
        and live.get("blocking") is True
        and live.get("default_state") == "CLOSED"
        and live.get("provider_attestation_required") is True
        and live.get("all_19_writers_required") is True
        and live.get("startup_recovery_clean_required") is True
        and live.get("runtime_start_function") == _RUNTIME_START_FUNCTION
        and live.get("can_enable_live") is False
    )
    safety = spec.get("safety_envelope")
    checks["spec_chain_and_safety_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_bootstrap_gate_receipt_sha256") == upstream_sha
        and isinstance(upstream_receipt, Mapping)
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("default_off") is True
        and safety.get("synthetic_memory_only") is True
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("real_provider_installed") is False
        and safety.get("real_recovery_executed") is False
        and safety.get("real_bot_imported") is False
        and safety.get("real_thread_started") is False
        and safety.get("real_startup_changed") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("apply_entrypoint_present") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "RUNTIME_INSTALLATION_MANIFEST_SPEC_SHA256_INVALID"),
        ("writer_manifest_exact", "RUNTIME_INSTALLATION_WRITER_MANIFEST_INVALID"),
        ("runtime_import_manifest_exact", "RUNTIME_INSTALLATION_IMPORT_MANIFEST_INVALID"),
        ("bot_import_gates_exact", "RUNTIME_INSTALLATION_BOT_IMPORT_GATES_INVALID"),
        ("installation_order_exact", "RUNTIME_INSTALLATION_ORDER_INVALID"),
        ("rollback_exact", "RUNTIME_INSTALLATION_ROLLBACK_PROTOCOL_INVALID"),
        ("provider_installation_valid", "RUNTIME_INSTALLATION_PROVIDER_PROTOCOL_INVALID"),
        ("startup_recovery_valid", "RUNTIME_INSTALLATION_RECOVERY_PROTOCOL_INVALID"),
        ("live_preflight_gate_valid", "RUNTIME_INSTALLATION_LIVE_PREFLIGHT_GATE_INVALID"),
        ("spec_chain_and_safety_valid", "RUNTIME_INSTALLATION_SPEC_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return spec_sha


def _check_rehearsal(
    rehearsal: Mapping[str, Any],
    upstream_sha: str,
    spec_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    rehearsal_sha = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        rehearsal_sha
        and hmac.compare_digest(
            rehearsal_sha,
            runtime_installation_manifest_rehearsal_sha256_v1(rehearsal),
        )
    )
    expected_phases = [item["phase"] for item in canonical_runtime_installation_phases_v1()]
    checks["phase_rehearsal_valid"] = bool(
        rehearsal.get("phase_event_sequence") == expected_phases
        and rehearsal.get("writer_count") == 19
        and rehearsal.get("all_body_seams_before_bot_imports") is True
        and rehearsal.get("provider_before_recovery") is True
        and rehearsal.get("recovery_before_runtime_start") is True
        and rehearsal.get("live_gate_closed_before_runtime_start") is True
    )
    writer_receipts = rehearsal.get("writer_receipts")
    expected_writers = canonical_runtime_installation_writer_manifest_v1()
    checks["writer_rehearsal_valid"] = bool(
        isinstance(writer_receipts, list)
        and len(writer_receipts) == 19
        and [item.get("writer_id") for item in writer_receipts if isinstance(item, Mapping)]
        == [item["writer_id"] for item in expected_writers]
        and all(
            isinstance(item, Mapping)
            and item.get("body_seam_attested_synthetically") is True
            and item.get("real_body_modified") is False
            and item.get("writer_invoked") is False
            for item in writer_receipts
        )
        and rehearsal.get("writer_receipts_sha256") == _stable_sha256(writer_receipts)
    )
    bot_receipts = rehearsal.get("by_name_bot_gate_receipts")
    expected_bots = canonical_runtime_installation_bot_import_gates_v1()
    checks["bot_gate_rehearsal_valid"] = bool(
        isinstance(bot_receipts, list)
        and len(bot_receipts) == 3
        and [item.get("component") for item in bot_receipts if isinstance(item, Mapping)]
        == [item["component"] for item in expected_bots]
        and all(
            isinstance(item, Mapping)
            and item.get("all_19_seams_ready_before_synthetic_release") is True
            and item.get("real_module_imported") is False
            for item in bot_receipts
        )
        and rehearsal.get("by_name_bot_gate_receipts_sha256")
        == _stable_sha256(bot_receipts)
    )
    live = rehearsal.get("live_gate_rehearsal")
    checks["live_gate_rehearsal_valid"] = bool(
        isinstance(live, Mapping)
        and live.get("check_code") == _LIVE_PREFLIGHT_CODE
        and live.get("default_closed") is True
        and live.get("synthetic_prerequisites_observed") is True
        and live.get("live_authorized") is False
        and live.get("flag_changed") is False
    )
    rollback = rehearsal.get("rollback_rehearsal")
    expected_rollback = [item["step"] for item in canonical_runtime_installation_rollback_v1()]
    checks["rollback_rehearsal_valid"] = bool(
        isinstance(rollback, Mapping)
        and rollback.get("trigger") == "SYNTHETIC_PROVIDER_INSTALL_FAILURE"
        and rollback.get("event_sequence") == expected_rollback
        and rollback.get("provider_graph_published") is False
        and rollback.get("runtime_started") is False
        and rollback.get("bot_imported") is False
        and rollback.get("registry_bytes_changed") is False
        and rollback.get("live_authorized") is False
        and rollback.get("retry_requires_fresh_preflight") is True
    )
    safety = rehearsal.get("safety_envelope")
    checks["rehearsal_chain_and_safety_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("upstream_bootstrap_gate_receipt_sha256") == upstream_sha
        and rehearsal.get("runtime_installation_manifest_spec_sha256") == spec_sha
        and isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("runtime_integrated") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("runtime_start_allowed") is False
        and safety.get("live_allowed") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        ("rehearsal_sha256_valid", "RUNTIME_INSTALLATION_REHEARSAL_SHA256_INVALID"),
        ("phase_rehearsal_valid", "RUNTIME_INSTALLATION_PHASE_REHEARSAL_INVALID"),
        ("writer_rehearsal_valid", "RUNTIME_INSTALLATION_WRITER_REHEARSAL_INVALID"),
        ("bot_gate_rehearsal_valid", "RUNTIME_INSTALLATION_BOT_GATE_REHEARSAL_INVALID"),
        ("live_gate_rehearsal_valid", "RUNTIME_INSTALLATION_LIVE_GATE_REHEARSAL_INVALID"),
        ("rollback_rehearsal_valid", "RUNTIME_INSTALLATION_ROLLBACK_REHEARSAL_INVALID"),
        ("rehearsal_chain_and_safety_valid", "RUNTIME_INSTALLATION_REHEARSAL_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return rehearsal_sha


def evaluate_closed_repair_runtime_installation_manifest_offline_v1(
    bootstrap_gate_result: Mapping[str, Any],
    runtime_installation_manifest_spec: Mapping[str, Any],
    runtime_installation_manifest_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate synthetic installation evidence and always deny installation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (
            bootstrap_gate_result,
            runtime_installation_manifest_spec,
            runtime_installation_manifest_rehearsal,
        )
    ):
        reasons.append("RUNTIME_INSTALLATION_MANIFEST_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(bootstrap_gate_result)
        spec = _canonical_copy(runtime_installation_manifest_spec)
        rehearsal = _canonical_copy(runtime_installation_manifest_rehearsal)
    except (TypeError, ValueError, OverflowError):
        reasons.append("RUNTIME_INSTALLATION_MANIFEST_INPUT_NOT_CANONICALIZABLE")
        return base

    upstream_receipt, upstream_sha = _check_upstream(upstream, reasons, checks)
    spec_sha = _check_spec(spec, upstream_receipt, upstream_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(
        rehearsal, upstream_sha, spec_sha, reasons, checks
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_RUNTIME_INSTALLATION_MANIFEST_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_bootstrap_gate_receipt_sha256": upstream_sha,
        "runtime_installation_manifest_spec_sha256": spec_sha,
        "runtime_installation_manifest_rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "by_name_bot_gate_count": 3,
        "runtime_import_count": 4,
        "direct_capability_builder_count": 3,
        "installation_phase_count": len(_PHASES),
        "rollback_step_count": len(_ROLLBACK_STEPS),
        "live_preflight_check_code": _LIVE_PREFLIGHT_CODE,
        "all_requirements_attested_synthetically": True,
        "rollback_rehearsed_synthetically": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["installation_manifest_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "installation_manifest_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "rollback_rehearsal_valid": True,
            "status": "CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "installation_manifest_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_CONTRACT_V1_VERSION",
    "canonical_runtime_installation_bot_import_gates_v1",
    "canonical_runtime_installation_import_manifest_v1",
    "canonical_runtime_installation_phases_v1",
    "canonical_runtime_installation_rollback_v1",
    "canonical_runtime_installation_writer_manifest_v1",
    "evaluate_closed_repair_runtime_installation_manifest_offline_v1",
    "runtime_installation_manifest_rehearsal_sha256_v1",
    "runtime_installation_manifest_spec_sha256_v1",
]
