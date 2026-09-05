"""Dormant pre-runtime bootstrap gate for CLOSED repair writer coordination.

This module validates only synthetic, in-memory attestations.  It deliberately
has no capability to import a bot, start a thread, install a runtime hook or
touch the Trade Registry.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-BOOTSTRAP-GATE-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PHASES = (
    "COORDINATION_ATTESTATION_VERIFIED",
    "STORAGE_BOUNDARY_ATTESTATION_VERIFIED",
    "WRITER_PARTICIPATION_ATTESTATION_VERIFIED",
    "ALL_19_WRITER_SEAMS_ATTESTED",
    "SINK_OWNER_TOKEN_PREFLIGHT_VERIFIED",
    "STARTUP_INTERLOCK_ARMED_SYNTHETICALLY",
    "BOT_IMPORT_GATE_EVALUATED_SYNTHETICALLY",
    "BOT_THREAD_GATE_EVALUATED_SYNTHETICALLY",
)
_BOT_SURFACES = (
    ("TRENDPRO", "bots/trendpro.py", 62, "MODULE_REFERENCE"),
    ("DONKEY", "bots/donkey.py", 63, "MODULE_REFERENCE"),
    ("COBRA", "bots/cobra.py", 24, "MODULE_REFERENCE"),
    ("MEME", "bots/meme.py", 65, "BY_NAME_FUNCTION_REFERENCE"),
    ("PREDATOR", "bots/predator.py", 73, "BY_NAME_FUNCTION_REFERENCE"),
    ("TURTLE", "bots/turtle.py", 76, "BY_NAME_FUNCTION_REFERENCE"),
    ("FALCON", "bots/falcon.py", 203, "MODULE_REFERENCE"),
)
_PRODUCTION_BLOCKERS = (
    "BOOTSTRAP_GATE_IS_CONTRACT_ONLY",
    "REAL_STARTUP_INTERLOCK_ABSENT",
    "REAL_SINK_OWNER_TOKEN_VALIDATION_ABSENT",
    "REAL_BOT_IMPORT_GATE_ABSENT",
    "REAL_THREAD_START_GATE_ABSENT",
    "RUNTIME_BOOTSTRAP_NOT_AUTHORIZED",
    "PHYSICAL_APPLY_ENTRYPOINT_ABSENT",
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


def writer_bootstrap_gate_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256(
        {key: value for key, value in spec.items() if key != "spec_sha256"}
    )


def writer_bootstrap_gate_rehearsal_sha256_v1(
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


def canonical_writer_bootstrap_phases_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": ordinal * 10, "phase": phase}
        for ordinal, phase in enumerate(_PHASES, start=1)
    ]


def canonical_writer_bootstrap_bot_surfaces_v1() -> list[dict[str, Any]]:
    return [
        {
            "bot_id": bot_id,
            "component": component,
            "source_anchor_line": source_anchor_line,
            "registry_import_mode": import_mode,
            "function_body_seams_required": True,
            "synthetic_import_only": True,
            "real_module_imported": False,
            "real_thread_started": False,
        }
        for bot_id, component, source_anchor_line, import_mode in _BOT_SURFACES
    ]


def _seam_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key != "seam_binding_receipt_sha256"
        }
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "bootstrap_gate_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "synthetic_bot_import_gate_passed": False,
        "synthetic_bot_thread_gate_passed": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_bootstrap_allowed": False,
        "status": "CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_CONTRACT_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_bot_imported": False,
        "real_thread_started": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "bootstrap_gate_receipt": None,
    }


def _check_upstream(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[Mapping[str, Any] | None, str]:
    receipt = result.get("seam_binding_receipt")
    supplied_sha = (
        _valid_sha256(receipt.get("seam_binding_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _seam_receipt_sha256(receipt) if isinstance(receipt, Mapping) else ""
    )
    checks["upstream_seam_binding_valid"] = bool(
        result.get("ok") is True
        and result.get("seam_binding_contract_verified") is True
        and result.get("synthetic_rehearsal_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and result.get("real_source_imported") is False
        and result.get("real_callable_bound") is False
        and isinstance(receipt, Mapping)
        and supplied_sha
        and hmac.compare_digest(supplied_sha, expected_sha)
        and receipt.get("writer_count") == 19
        and receipt.get("all_source_signatures_bound") is True
        and receipt.get("reentrant_owner_token_required") is True
        and receipt.get("installation_order_bound") is True
        and receipt.get("production_blockers")
    )
    if not checks["upstream_seam_binding_valid"]:
        reasons.append("WRITER_BOOTSTRAP_GATE_UPSTREAM_SEAM_BINDING_INVALID")
    return receipt if isinstance(receipt, Mapping) else None, supplied_sha


def _check_spec(
    spec: Mapping[str, Any],
    upstream_receipt: Mapping[str, Any] | None,
    upstream_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha, writer_bootstrap_gate_spec_sha256_v1(spec)
        )
    )
    expected_phases = canonical_writer_bootstrap_phases_v1()
    expected_bots = canonical_writer_bootstrap_bot_surfaces_v1()
    checks["phase_manifest_exact"] = bool(
        spec.get("bootstrap_phases") == expected_phases
        and spec.get("bootstrap_phases_sha256") == _stable_sha256(expected_phases)
    )
    checks["bot_surface_manifest_exact"] = bool(
        spec.get("bot_surfaces") == expected_bots
        and spec.get("bot_surfaces_sha256") == _stable_sha256(expected_bots)
        and len(expected_bots) == 7
        and len({item["bot_id"] for item in expected_bots}) == 7
    )
    interlock = spec.get("startup_interlock")
    checks["startup_interlock_valid"] = bool(
        isinstance(interlock, Mapping)
        and interlock.get("default_state") == "CLOSED"
        and interlock.get("all_upstream_attestations_required") is True
        and interlock.get("exact_writer_count_required") == 19
        and interlock.get("sink_owner_token_preflight_required") is True
        and interlock.get("bot_import_denied_before_all_seams") is True
        and interlock.get("bot_thread_denied_before_import_gate") is True
        and interlock.get("by_name_imports_require_function_body_seams") is True
        and interlock.get("unknown_or_stale_evidence_fails_closed") is True
        and interlock.get("runtime_callable_absent") is True
    )
    safety = spec.get("safety_envelope")
    checks["spec_chain_and_safety_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_seam_binding_receipt_sha256") == upstream_sha
        and isinstance(upstream_receipt, Mapping)
        and spec.get("upstream_participation_receipt_sha256")
        == upstream_receipt.get("upstream_participation_receipt_sha256")
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("synthetic_memory_only") is True
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("real_bot_imported") is False
        and safety.get("real_thread_started") is False
        and safety.get("real_startup_changed") is False
        and safety.get("runtime_bootstrap_allowed") is False
        and safety.get("apply_entrypoint_present") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "WRITER_BOOTSTRAP_GATE_SPEC_SHA256_INVALID"),
        ("phase_manifest_exact", "WRITER_BOOTSTRAP_GATE_PHASE_MANIFEST_INVALID"),
        (
            "bot_surface_manifest_exact",
            "WRITER_BOOTSTRAP_GATE_BOT_SURFACE_MANIFEST_INVALID",
        ),
        ("startup_interlock_valid", "WRITER_BOOTSTRAP_GATE_INTERLOCK_INVALID"),
        (
            "spec_chain_and_safety_valid",
            "WRITER_BOOTSTRAP_GATE_SPEC_CHAIN_OR_SAFETY_INVALID",
        ),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def _check_rehearsal(
    rehearsal: Mapping[str, Any],
    upstream_sha: str,
    spec_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied_sha
        and hmac.compare_digest(
            supplied_sha,
            writer_bootstrap_gate_rehearsal_sha256_v1(rehearsal),
        )
    )
    expected_sequence = [
        item["phase"] for item in canonical_writer_bootstrap_phases_v1()
    ]
    checks["phase_rehearsal_valid"] = bool(
        rehearsal.get("phase_event_sequence") == expected_sequence
        and rehearsal.get("all_19_seams_ready_before_import_gate") is True
        and rehearsal.get("sink_preflight_before_import_gate") is True
        and rehearsal.get("import_gate_before_thread_gate") is True
    )
    expected_bots = canonical_writer_bootstrap_bot_surfaces_v1()
    bot_receipts = rehearsal.get("bot_gate_receipts")
    checks["bot_gate_receipts_valid"] = bool(
        isinstance(bot_receipts, list)
        and len(bot_receipts) == 7
        and [item.get("bot_id") for item in bot_receipts if isinstance(item, Mapping)]
        == [item["bot_id"] for item in expected_bots]
        and all(
            isinstance(item, Mapping)
            and item.get("component") == expected["component"]
            and item.get("registry_import_mode")
            == expected["registry_import_mode"]
            and item.get("synthetic_import_gate_passed") is True
            and item.get("synthetic_thread_gate_passed") is True
            and item.get("real_module_imported") is False
            and item.get("real_thread_started") is False
            for item, expected in zip(bot_receipts, expected_bots)
        )
        and rehearsal.get("bot_gate_receipts_sha256")
        == _stable_sha256(bot_receipts)
    )
    sink = rehearsal.get("sink_owner_token_preflight")
    checks["sink_owner_token_preflight_valid"] = bool(
        isinstance(sink, Mapping)
        and sink.get("synthetic_token_present") is True
        and sink.get("namespace_matches") is True
        and sink.get("owner_matches") is True
        and sink.get("nested_depth") == 2
        and sink.get("synthetic_preflight_accepted") is True
        and sink.get("real_sink_called") is False
    )
    negative = rehearsal.get("negative_controls")
    checks["negative_controls_valid"] = bool(
        isinstance(negative, Mapping)
        and negative.get("missing_seam_denies_import") is True
        and negative.get("invalid_sink_token_denies_import") is True
        and negative.get("wrong_phase_order_denies_import") is True
        and negative.get("thread_before_import_denied") is True
        and negative.get("runtime_callable_denied") is True
    )
    safety = rehearsal.get("safety_envelope")
    checks["rehearsal_chain_and_safety_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("upstream_seam_binding_receipt_sha256")
        == upstream_sha
        and rehearsal.get("bootstrap_gate_spec_sha256") == spec_sha
        and rehearsal.get("writer_count") == 19
        and rehearsal.get("bot_count") == 7
        and isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("real_bot_imported") is False
        and safety.get("real_thread_started") is False
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("runtime_integrated") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("runtime_bootstrap_allowed") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        (
            "rehearsal_sha256_valid",
            "WRITER_BOOTSTRAP_GATE_REHEARSAL_SHA256_INVALID",
        ),
        ("phase_rehearsal_valid", "WRITER_BOOTSTRAP_GATE_PHASE_REHEARSAL_INVALID"),
        (
            "bot_gate_receipts_valid",
            "WRITER_BOOTSTRAP_GATE_BOT_RECEIPTS_INVALID",
        ),
        (
            "sink_owner_token_preflight_valid",
            "WRITER_BOOTSTRAP_GATE_SINK_PREFLIGHT_INVALID",
        ),
        (
            "negative_controls_valid",
            "WRITER_BOOTSTRAP_GATE_NEGATIVE_CONTROLS_INVALID",
        ),
        (
            "rehearsal_chain_and_safety_valid",
            "WRITER_BOOTSTRAP_GATE_REHEARSAL_CHAIN_OR_SAFETY_INVALID",
        ),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def evaluate_closed_repair_writer_bootstrap_gate_offline_v1(
    seam_binding_result: Mapping[str, Any],
    bootstrap_gate_spec: Mapping[str, Any],
    bootstrap_gate_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the synthetic gate while always denying real bootstrap."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (
            seam_binding_result,
            bootstrap_gate_spec,
            bootstrap_gate_rehearsal,
        )
    ):
        reasons.append("WRITER_BOOTSTRAP_GATE_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(seam_binding_result)
        spec = _canonical_copy(bootstrap_gate_spec)
        rehearsal = _canonical_copy(bootstrap_gate_rehearsal)
    except (TypeError, ValueError, OverflowError):
        reasons.append("WRITER_BOOTSTRAP_GATE_INPUT_NOT_CANONICALIZABLE")
        return base

    upstream_receipt, upstream_sha = _check_upstream(upstream, reasons, checks)
    spec_sha = _check_spec(
        spec, upstream_receipt, upstream_sha, reasons, checks
    )
    rehearsal_sha = _check_rehearsal(
        rehearsal, upstream_sha, spec_sha, reasons, checks
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_WRITER_BOOTSTRAP_GATE_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_seam_binding_receipt_sha256": upstream_sha,
        "bootstrap_gate_spec_sha256": spec_sha,
        "bootstrap_gate_rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "bot_count": 7,
        "all_prerequisites_attested_synthetically": True,
        "synthetic_import_gate_passed": True,
        "synthetic_thread_gate_passed": True,
        "real_bot_imported": False,
        "real_thread_started": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_bootstrap_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["bootstrap_gate_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "bootstrap_gate_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "synthetic_bot_import_gate_passed": True,
            "synthetic_bot_thread_gate_passed": True,
            "status": "CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "bootstrap_gate_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_CONTRACT_V1_VERSION",
    "canonical_writer_bootstrap_bot_surfaces_v1",
    "canonical_writer_bootstrap_phases_v1",
    "evaluate_closed_repair_writer_bootstrap_gate_offline_v1",
    "writer_bootstrap_gate_rehearsal_sha256_v1",
    "writer_bootstrap_gate_spec_sha256_v1",
]
