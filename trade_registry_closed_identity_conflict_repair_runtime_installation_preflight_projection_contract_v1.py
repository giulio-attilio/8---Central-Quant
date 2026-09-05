"""Dormant contract binding the installation manifest to an AST preflight.

Only already-evaluated synthetic mappings are accepted.  This module does not
load source files, import runtime code, execute projected source, mutate the
Registry or grant production/Live authority.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_contract_v1 as installation_manifest
import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as static_preflight


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-INSTALLATION-PREFLIGHT-PROJECTION-CONTRACT-V1"
)

_EVIDENCE_VERSION = (
    "SYNTHETIC_CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_EVIDENCE_V1"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_RESOLVED_BLOCKERS = (
    "ALL_19_WRITER_BODY_SEAMS_COORDINATED",
    "C3_RUNTIME_DEPENDENCIES_IMPORTED",
    "PRODUCTION_TRANSACTION_STORE_PRESENT",
    "PERSISTENCE_BOOTSTRAP_BEFORE_RUNTIME_START",
    "C3_PROVIDER_INSTALLED_BEFORE_RUNTIME_START",
    "C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES",
    "C3_STARTUP_RECOVERY_BEFORE_RUNTIME_START",
    "BY_NAME_BOT_WRITER_IMPORTS_GATED",
    "LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION",
)
_PRODUCTION_BLOCKERS = (
    "PREFLIGHT_PROJECTION_IS_SYNTHETIC_ONLY",
    "PROJECTED_SOURCE_WAS_NOT_EXECUTED",
    "REAL_RUNTIME_SOURCE_WAS_NOT_CHANGED",
    "REAL_PROVIDER_WAS_NOT_INSTALLED",
    "REAL_RECOVERY_WAS_NOT_EXECUTED",
    "REAL_BOT_IMPORT_GATE_WAS_NOT_INSTALLED",
    "REAL_RUNTIME_WAS_NOT_STARTED",
    "REAL_LIVE_PREFLIGHT_WAS_NOT_CHANGED",
    "SEPARATE_RUNTIME_INTEGRATION_AUTHORIZATION_REQUIRED",
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


def canonical_resolved_runtime_preflight_blockers_v1() -> list[str]:
    return list(_EXPECTED_RESOLVED_BLOCKERS)


def runtime_installation_preflight_projection_evidence_sha256_v1(
    evidence: Mapping[str, Any],
) -> str:
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    return _stable_sha256(
        {
            key: value
            for key, value in evidence.items()
            if key != "evidence_sha256"
        }
    )


def _manifest_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key != "installation_manifest_receipt_sha256"
        }
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "projection_contract_verified": False,
        "synthetic_static_readiness_proven": False,
        "negative_controls_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "status": "CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "ast_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "runtime_imported": False,
        "runtime_executed": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "projection_receipt": None,
    }


def _check_manifest(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[Mapping[str, Any] | None, str]:
    receipt = result.get("installation_manifest_receipt")
    supplied_sha = (
        _valid_sha256(receipt.get("installation_manifest_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected_sha = (
        _manifest_receipt_sha256(receipt)
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_installation_manifest_valid"] = bool(
        result.get("ok") is True
        and result.get("installation_manifest_contract_verified") is True
        and result.get("synthetic_rehearsal_valid") is True
        and result.get("rollback_rehearsal_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("runtime_start_allowed") is False
        and result.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied_sha
        and hmac.compare_digest(supplied_sha, expected_sha)
        and receipt.get("writer_count") == 19
        and receipt.get("by_name_bot_gate_count") == 3
        and receipt.get("production_blockers")
    )
    if not checks["upstream_installation_manifest_valid"]:
        reasons.append("PREFLIGHT_PROJECTION_UPSTREAM_MANIFEST_INVALID")
    return receipt if isinstance(receipt, Mapping) else None, supplied_sha


def _check_projection(
    evidence: Mapping[str, Any],
    manifest_receipt: Mapping[str, Any] | None,
    manifest_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    evidence_sha = _valid_sha256(evidence.get("evidence_sha256"))
    checks["evidence_sha256_valid"] = bool(
        evidence_sha
        and hmac.compare_digest(
            evidence_sha,
            runtime_installation_preflight_projection_evidence_sha256_v1(
                evidence
            ),
        )
    )
    preflight = evidence.get("projected_preflight_result")
    preflight_checks = preflight.get("checks") if isinstance(preflight, Mapping) else None
    checks["projected_preflight_satisfied"] = bool(
        isinstance(preflight, Mapping)
        and preflight.get("ok") is True
        and preflight.get("evaluation_complete") is True
        and preflight.get("static_readiness") is True
        and preflight.get("blockers") == []
        and isinstance(preflight_checks, list)
        and preflight_checks
        and all(
            isinstance(item, Mapping) and item.get("ok") is True
            for item in preflight_checks
        )
    )
    checks["projected_preflight_preserves_denial"] = bool(
        isinstance(preflight, Mapping)
        and preflight.get("production_ready") is False
        and preflight.get("apply_allowed") is False
        and preflight.get("live_allowed") is False
        and preflight.get("runtime_imported") is False
        and preflight.get("runtime_executed") is False
        and preflight.get("write_executed") is False
        and preflight.get("registry_write") is False
        and preflight.get("network_accessed") is False
        and preflight.get("broker_called") is False
        and preflight.get("no_order_sent") is True
    )
    summary = preflight.get("writer_summary") if isinstance(preflight, Mapping) else None
    checks["projected_writer_inventory_exact"] = bool(
        isinstance(summary, Mapping)
        and summary.get("expected_count") == 19
        and summary.get("discovered_count") == 19
        and summary.get("signature_mismatch_count") == 0
        and summary.get("anchor_mismatch_count") == 0
        and summary.get("coordinated_count") == 19
    )
    attestations = preflight.get("source_attestations") if isinstance(preflight, Mapping) else None
    checks["synthetic_source_attestations_valid"] = bool(
        isinstance(attestations, Mapping)
        and set(attestations) == set(static_preflight.REQUIRED_SOURCE_KEYS_V1)
        and all(
            isinstance(value, Mapping)
            and set(value) == {"sha256", "size_bytes"}
            and _valid_sha256(value.get("sha256"))
            and int(value.get("size_bytes") or 0) > 0
            for value in attestations.values()
        )
    )
    controls = evidence.get("negative_control_receipts")
    expected_codes = canonical_resolved_runtime_preflight_blockers_v1()
    checks["negative_controls_exact"] = bool(
        isinstance(controls, list)
        and len(controls) == len(expected_codes)
        and [item.get("control_id") for item in controls if isinstance(item, Mapping)]
        == expected_codes
        and all(
            isinstance(item, Mapping)
            and item.get("control_id") in item.get("observed_blockers", [])
            and item.get("static_readiness") is False
            and item.get("production_ready") is False
            and item.get("live_allowed") is False
            and item.get("runtime_executed") is False
            and item.get("source_executed") is False
            for item in controls
        )
        and evidence.get("negative_control_receipts_sha256")
        == _stable_sha256(controls)
    )
    safety = evidence.get("safety_envelope")
    checks["evidence_chain_and_safety_valid"] = bool(
        evidence.get("evidence_version") == _EVIDENCE_VERSION
        and evidence.get("upstream_installation_manifest_receipt_sha256")
        == manifest_sha
        and isinstance(manifest_receipt, Mapping)
        and evidence.get("resolved_blocker_codes") == expected_codes
        and evidence.get("source_keys")
        == list(static_preflight.REQUIRED_SOURCE_KEYS_V1)
        and isinstance(safety, Mapping)
        and safety.get("synthetic_strings_only") is True
        and safety.get("real_files_read") is False
        and safety.get("real_files_written") is False
        and safety.get("projected_source_executed") is False
        and safety.get("runtime_module_imported") is False
        and safety.get("runtime_started") is False
        and safety.get("bot_started") is False
        and safety.get("registry_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("live_allowed") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        ("evidence_sha256_valid", "PREFLIGHT_PROJECTION_EVIDENCE_SHA256_INVALID"),
        ("projected_preflight_satisfied", "PROJECTED_STATIC_PREFLIGHT_NOT_SATISFIED"),
        ("projected_preflight_preserves_denial", "PROJECTED_PREFLIGHT_AUTHORITY_DENIAL_INVALID"),
        ("projected_writer_inventory_exact", "PROJECTED_WRITER_INVENTORY_INVALID"),
        ("synthetic_source_attestations_valid", "PROJECTED_SOURCE_ATTESTATIONS_INVALID"),
        ("negative_controls_exact", "PREFLIGHT_PROJECTION_NEGATIVE_CONTROLS_INVALID"),
        ("evidence_chain_and_safety_valid", "PREFLIGHT_PROJECTION_CHAIN_OR_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return evidence_sha


def evaluate_closed_repair_runtime_installation_preflight_projection_offline_v1(
    installation_manifest_result: Mapping[str, Any],
    projection_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the projection while preserving every operational denial."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not all(
        isinstance(value, Mapping)
        for value in (installation_manifest_result, projection_evidence)
    ):
        reasons.append("PREFLIGHT_PROJECTION_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        manifest_result = _canonical_copy(installation_manifest_result)
        evidence = _canonical_copy(projection_evidence)
    except (TypeError, ValueError, OverflowError):
        reasons.append("PREFLIGHT_PROJECTION_INPUT_NOT_CANONICALIZABLE")
        return base

    manifest_receipt, manifest_sha = _check_manifest(
        manifest_result, reasons, checks
    )
    evidence_sha = _check_projection(
        evidence, manifest_receipt, manifest_sha, reasons, checks
    )
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_PREFLIGHT_PROJECTION_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_installation_manifest_receipt_sha256": manifest_sha,
        "projection_evidence_sha256": evidence_sha,
        "synthetic_source_set_sha256": _stable_sha256(
            evidence["projected_preflight_result"]["source_attestations"]
        ),
        "resolved_blocker_codes": canonical_resolved_runtime_preflight_blockers_v1(),
        "resolved_blocker_count": len(_EXPECTED_RESOLVED_BLOCKERS),
        "negative_control_count": len(_EXPECTED_RESOLVED_BLOCKERS),
        "writer_count": 19,
        "synthetic_static_readiness_proven": True,
        "real_runtime_readiness_proven": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["projection_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "projection_contract_verified": True,
            "synthetic_static_readiness_proven": True,
            "negative_controls_valid": True,
            "status": "CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_V1_VALID_SYNTHETIC_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "projection_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_CONTRACT_V1_VERSION",
    "canonical_resolved_runtime_preflight_blockers_v1",
    "evaluate_closed_repair_runtime_installation_preflight_projection_offline_v1",
    "runtime_installation_preflight_projection_evidence_sha256_v1",
]
