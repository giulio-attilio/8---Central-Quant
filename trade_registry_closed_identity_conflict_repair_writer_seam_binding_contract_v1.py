"""Dormant binding contract for the 19 audited Trade Registry writer seams.

The manifest records source-facing metadata but never imports, decorates or
invokes a production module.  All evidence accepted here is synthetic and the
result always keeps runtime installation and Registry writes disabled.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-SEAM-BINDING-CONTRACT-V1"
)

_SPEC_VERSION = "DORMANT_CLOSED_REPAIR_WRITER_SEAM_BINDING_SPEC_V1"
_REHEARSAL_VERSION = "SYNTHETIC_CLOSED_REPAIR_WRITER_SEAM_BINDING_REHEARSAL_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REENTRANCY_MODE = "OWNER_TOKEN_REENTRANT_OUTERMOST_RELEASE_V1"
_INSTALLATION_SEQUENCE = (
    "COORDINATION_PROVIDER_AVAILABLE",
    "STORAGE_BOUNDARY_AVAILABLE",
    "TRADE_REGISTRY_BODY_SEAMS_AVAILABLE",
    "BOT_MODULE_IMPORTS_ALLOWED",
    "BOT_THREADS_ALLOWED",
    "MAIN_WRITER_ROUTES_ALLOWED",
)
_PRODUCTION_BLOCKERS = (
    "SEAM_BINDING_IS_CONTRACT_ONLY",
    "REAL_SOURCE_MODULES_NOT_IMPORTED",
    "REAL_WRITER_CALLABLES_NOT_BOUND",
    "REAL_STARTUP_ORDER_NOT_CHANGED",
    "RUNTIME_INSTALL_NOT_AUTHORIZED",
    "PHYSICAL_APPLY_ENTRYPOINT_ABSENT",
)


# Immutable output of the read-only 2026-09-04 seam audit.  Signatures are
# deliberately stored as text so validating this module cannot import main,
# trade_registry or any bot with import-time side effects.
_SEAM_DETAILS = (
    (263, "() -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (366, "(bot: Any, symbol: Any, side: Any, entry: Any, sl: Any = None, tp50: Any = None, setup: Any = None, qty: Any = None, source: str = 'central', metadata: Optional[Dict[str, Any]] = None, registry_mode: Any = None, execution_mode: Any = None, broker_order_id: Any = None, client_order_id: Any = None, **extra: Any) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (443, "(trade_id: str, **updates: Any) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (603, "(trade_id: Optional[str] = None, *, bot: Any = None, symbol: Any = None, side: Any = None, setup: Any = None, expected_identity: Optional[Dict[str, Any]] = None, metadata: Optional[Dict[str, Any]] = None, **updates: Any) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (2714, "(payload: Dict[str, Any], *, ack: Any = None) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (2853, "(trade_id: str, close_event_id: str, outcome: Dict[str, Any], *, expected_identity: Optional[Dict[str, Any]] = None) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (3098, "(trade_id: str, exit_price: Any = None, pnl_pct: Any = None, pnl_r: Any = None, reason: Any = None, metadata: Optional[Dict[str, Any]] = None, registry_mode: Any = None, realized_pnl: Any = None, fee: Any = None, funding: Any = None, broker_close_order_id: Any = None, expected_identity: Optional[Dict[str, Any]] = None, expected_open_trade_id_count: Optional[int] = None, clear_financial_results: bool = False, **extra: Any) -> Dict[str, Any]", "FUNCTION_BODY_FULL_RMW_REENTRANT", True),
    (3302, "(confirm: bool = False) -> Dict[str, Any]", "FUNCTION_BODY_EXCLUSIVE_WRITE_REENTRANT", False),
    (4488, "(candidate)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (7249, "(symbol=None, side=None, bot=None, setup=None, lifecycle=None, commit=False)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (9859, "(commit=False, ack=None, _lock_held=False)", "MAIN_EXISTING_SCOPE_COORDINATOR_UPGRADE", True),
    (10186, "(symbol=None, side=None, bot=None, setup=None, commit=False, ack=None, entry=None, qty=None, sl=None, tp50=None, exit_price=None, realized_pnl=None, last_mark_price=None, last_unrealized_pnl=None, close_reason=None)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (11052, "(found_payload, selected_payload, outcome)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (11606, "(commit=False, include_trades=True, source='manual')", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (14681, "(removed)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (49325, "(commit=False, ack=None, include_samples=True, use_cache=False)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (49761, "(commit=False, ack=None, include_samples=True, track_state=True)", "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD", True),
    (67527, "(commit=False, ack=None, automatic=False, include_samples=True)", "MAIN_EXISTING_SCOPE_COORDINATOR_UPGRADE", True),
    (50537, "(force=False, _lock_held=False)", "MAIN_EXISTING_SCOPE_COORDINATOR_UPGRADE", True),
)

_BY_NAME_IMPORT_CONSUMERS = (
    {"component": "bots/meme.py", "source_anchor_line": 65},
    {"component": "bots/predator.py", "source_anchor_line": 73},
    {"component": "bots/turtle.py", "source_anchor_line": 76},
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def writer_seam_binding_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def writer_seam_binding_rehearsal_sha256_v1(rehearsal: Mapping[str, Any]) -> str:
    if not isinstance(rehearsal, Mapping):
        raise TypeError("rehearsal must be a mapping")
    return _stable_sha256({key: value for key, value in rehearsal.items() if key != "rehearsal_sha256"})


def canonical_writer_seam_bindings_v1(
    participation_receipt: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return the exact audited seam map, bound to participation evidence."""

    if not isinstance(participation_receipt, Mapping):
        raise TypeError("participation_receipt must be a mapping")
    receipt_sha = str(participation_receipt.get("participation_receipt_sha256") or "")
    writers = coordination.canonical_closed_repair_writer_inventory_v1()
    if len(writers) != len(_SEAM_DETAILS):
        raise AssertionError("writer inventory and seam details diverged")
    bindings = []
    for writer, details in zip(writers, _SEAM_DETAILS):
        line, signature, strategy, fresh_read = details
        bindings.append(
            {
                "writer": writer,
                "source_anchor_line": line,
                "source_signature": signature,
                "source_signature_sha256": _stable_sha256(signature),
                "adaptation_strategy": strategy,
                "reentrancy_mode": _REENTRANCY_MODE,
                "same_owner_token_required_for_nested_calls": True,
                "sink_token_validation_required": True,
                "fresh_read_after_lock_required": fresh_read,
                "result_contract_preserved": True,
                "function_body_binding_required": writer["component"] == "trade_registry.py",
                "runtime_callable_bound": False,
                "upstream_participation_receipt_sha256": receipt_sha,
            }
        )
    return bindings


def canonical_writer_seam_installation_order_v1() -> list[dict[str, Any]]:
    return [
        {"ordinal": index * 10, "phase": phase}
        for index, phase in enumerate(_INSTALLATION_SEQUENCE, start=1)
    ]


def _participation_receipt_sha256(receipt: Mapping[str, Any]) -> str:
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != "participation_receipt_sha256"}
    )


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "seam_binding_contract_verified": False,
        "synthetic_rehearsal_valid": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "status": "CLOSED_REPAIR_WRITER_SEAM_BINDING_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_CONTRACT_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_source_imported": False,
        "real_callable_bound": False,
        "broker_called": False,
        "no_order_sent": True,
        "reasons": [],
        "checks": {},
        "seam_binding_receipt": None,
    }


def _check_participation(
    result: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[Mapping[str, Any] | None, str]:
    receipt = result.get("participation_receipt")
    supplied_sha = _valid_sha256(receipt.get("participation_receipt_sha256")) if isinstance(receipt, Mapping) else ""
    expected_sha = _participation_receipt_sha256(receipt) if isinstance(receipt, Mapping) else ""
    checks["upstream_participation_valid"] = bool(
        result.get("ok") is True
        and result.get("participation_contract_verified") is True
        and result.get("synthetic_participants_valid") is True
        and result.get("production_ready") is False
        and result.get("apply_allowed") is False
        and result.get("runtime_install_allowed") is False
        and result.get("write_executed") is False
        and result.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and supplied_sha
        and hmac.compare_digest(supplied_sha, expected_sha)
        and receipt.get("writer_count") == 19
        and receipt.get("production_blockers")
    )
    if not checks["upstream_participation_valid"]:
        reasons.append("WRITER_SEAM_BINDING_UPSTREAM_PARTICIPATION_INVALID")
    return receipt if isinstance(receipt, Mapping) else None, supplied_sha


def _check_spec(
    spec: Mapping[str, Any],
    participation_receipt: Mapping[str, Any] | None,
    receipt_sha: str,
    reasons: list[str],
    checks: dict[str, bool],
) -> tuple[str, list[dict[str, Any]]]:
    supplied_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["spec_sha256_valid"] = bool(
        supplied_sha and hmac.compare_digest(supplied_sha, writer_seam_binding_spec_sha256_v1(spec))
    )
    expected = canonical_writer_seam_bindings_v1(participation_receipt) if isinstance(participation_receipt, Mapping) else []
    bindings = spec.get("seam_bindings")
    checks["seam_bindings_exact"] = bool(
        isinstance(bindings, list)
        and bindings == expected
        and len(bindings) == 19
        and len({item["writer"]["writer_id"] for item in bindings if isinstance(item, Mapping) and isinstance(item.get("writer"), Mapping)}) == 19
        and spec.get("seam_bindings_sha256") == _stable_sha256(expected)
    )
    expected_order = canonical_writer_seam_installation_order_v1()
    ordering = spec.get("installation_protocol")
    checks["installation_protocol_valid"] = bool(
        isinstance(ordering, Mapping)
        and ordering.get("ordered_phases") == expected_order
        and ordering.get("ordered_phases_sha256") == _stable_sha256(expected_order)
        and ordering.get("coordination_before_storage") is True
        and ordering.get("storage_before_body_seams") is True
        and ordering.get("body_seams_before_bot_imports") is True
        and ordering.get("bot_imports_before_threads") is True
        and ordering.get("fail_closed_on_unknown_order") is True
    )
    reentrancy = spec.get("reentrancy_protocol")
    checks["reentrancy_protocol_valid"] = bool(
        isinstance(reentrancy, Mapping)
        and reentrancy.get("mode") == _REENTRANCY_MODE
        and reentrancy.get("same_owner_token_for_nested_calls") is True
        and reentrancy.get("release_only_at_outermost_depth") is True
        and reentrancy.get("sink_validates_owner_token") is True
        and reentrancy.get("nested_load_and_write_supported") is True
        and reentrancy.get("fail_closed_on_token_mismatch") is True
    )
    import_risk = spec.get("import_binding_risk")
    checks["import_binding_risk_valid"] = bool(
        isinstance(import_risk, Mapping)
        and import_risk.get("by_name_consumers") == list(_BY_NAME_IMPORT_CONSUMERS)
        and import_risk.get("late_monkey_patch_insufficient") is True
        and import_risk.get("function_body_binding_required") is True
    )
    safety = spec.get("safety_envelope")
    checks["spec_safety_valid"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_participation_receipt_sha256") == receipt_sha
        and isinstance(safety, Mapping)
        and safety.get("contract_only") is True
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("real_startup_changed") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("apply_entrypoint_present") is False
    )
    for check, reason in (
        ("spec_sha256_valid", "WRITER_SEAM_BINDING_SPEC_SHA256_INVALID"),
        ("seam_bindings_exact", "WRITER_SEAM_BINDINGS_NOT_EXACT"),
        ("installation_protocol_valid", "WRITER_SEAM_INSTALLATION_PROTOCOL_INVALID"),
        ("reentrancy_protocol_valid", "WRITER_SEAM_REENTRANCY_PROTOCOL_INVALID"),
        ("import_binding_risk_valid", "WRITER_SEAM_IMPORT_RISK_INVALID"),
        ("spec_safety_valid", "WRITER_SEAM_BINDING_SPEC_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha, expected


def _check_rehearsal(
    rehearsal: Mapping[str, Any],
    receipt_sha: str,
    spec_sha: str,
    expected_bindings: list[dict[str, Any]],
    reasons: list[str],
    checks: dict[str, bool],
) -> str:
    supplied_sha = _valid_sha256(rehearsal.get("rehearsal_sha256"))
    checks["rehearsal_sha256_valid"] = bool(
        supplied_sha and hmac.compare_digest(supplied_sha, writer_seam_binding_rehearsal_sha256_v1(rehearsal))
    )
    receipts = rehearsal.get("binding_receipts")
    expected_ids = [item["writer"]["writer_id"] for item in expected_bindings]
    checks["binding_receipts_valid"] = bool(
        isinstance(receipts, list)
        and len(receipts) == 19
        and [item.get("writer_id") for item in receipts if isinstance(item, Mapping)] == expected_ids
        and all(
            isinstance(item, Mapping)
            and item.get("source_signature_sha256") == binding["source_signature_sha256"]
            and item.get("adaptation_strategy") == binding["adaptation_strategy"]
            and item.get("reentrancy_mode") == _REENTRANCY_MODE
            and item.get("synthetic_binding_observed") is True
            and item.get("real_callable_bound") is False
            and item.get("writer_invoked") is False
            for item, binding in zip(receipts, expected_bindings)
        )
        and rehearsal.get("binding_receipts_sha256") == _stable_sha256(receipts)
    )
    reentrant = rehearsal.get("reentrancy_rehearsal")
    checks["reentrancy_rehearsal_valid"] = bool(
        isinstance(reentrant, Mapping)
        and reentrant.get("mode") == _REENTRANCY_MODE
        and reentrant.get("depth_sequence") == [0, 1, 2, 1, 0]
        and reentrant.get("single_owner_token_preserved") is True
        and reentrant.get("sink_token_accepted_synthetically") is True
        and reentrant.get("lock_released_at_outermost_only") is True
        and reentrant.get("real_lock_acquired") is False
    )
    expected_order = [item["phase"] for item in canonical_writer_seam_installation_order_v1()]
    checks["installation_rehearsal_valid"] = bool(
        rehearsal.get("installation_event_sequence") == expected_order
        and rehearsal.get("body_seams_ready_before_bot_imports") is True
        and rehearsal.get("all_seams_ready_before_threads") is True
    )
    safety = rehearsal.get("safety_envelope")
    checks["rehearsal_chain_and_safety_valid"] = bool(
        rehearsal.get("rehearsal_version") == _REHEARSAL_VERSION
        and rehearsal.get("upstream_participation_receipt_sha256") == receipt_sha
        and rehearsal.get("seam_binding_spec_sha256") == spec_sha
        and rehearsal.get("writer_count") == 19
        and isinstance(safety, Mapping)
        and safety.get("synthetic_memory_only") is True
        and safety.get("real_source_imported") is False
        and safety.get("real_callable_bound") is False
        and safety.get("writer_invoked") is False
        and safety.get("filesystem_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("runtime_integrated") is False
        and safety.get("write_executed") is False
        and safety.get("registry_write") is False
        and safety.get("runtime_install_allowed") is False
        and safety.get("apply_entrypoint_present") is False
        and safety.get("no_order_sent") is True
    )
    for check, reason in (
        ("rehearsal_sha256_valid", "WRITER_SEAM_BINDING_REHEARSAL_SHA256_INVALID"),
        ("binding_receipts_valid", "WRITER_SEAM_BINDING_RECEIPTS_INVALID"),
        ("reentrancy_rehearsal_valid", "WRITER_SEAM_REENTRANCY_REHEARSAL_INVALID"),
        ("installation_rehearsal_valid", "WRITER_SEAM_INSTALLATION_REHEARSAL_INVALID"),
        ("rehearsal_chain_and_safety_valid", "WRITER_SEAM_BINDING_REHEARSAL_SAFETY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return supplied_sha


def evaluate_closed_repair_writer_seam_binding_offline_v1(
    participation_result: Mapping[str, Any],
    seam_binding_spec: Mapping[str, Any],
    seam_binding_rehearsal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate synthetic seam evidence and always deny runtime installation."""

    base = _base()
    reasons = base["reasons"]
    checks = base["checks"]
    if not all(isinstance(value, Mapping) for value in (participation_result, seam_binding_spec, seam_binding_rehearsal)):
        reasons.append("WRITER_SEAM_BINDING_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        result = _canonical_copy(participation_result)
        spec = _canonical_copy(seam_binding_spec)
        rehearsal = _canonical_copy(seam_binding_rehearsal)
    except (TypeError, ValueError, OverflowError):
        reasons.append("WRITER_SEAM_BINDING_INPUT_NOT_CANONICALIZABLE")
        return base

    participation_receipt, receipt_sha = _check_participation(result, reasons, checks)
    spec_sha, expected_bindings = _check_spec(spec, participation_receipt, receipt_sha, reasons, checks)
    rehearsal_sha = _check_rehearsal(rehearsal, receipt_sha, spec_sha, expected_bindings, reasons, checks)
    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_WRITER_SEAM_BINDING_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_participation_receipt_sha256": receipt_sha,
        "seam_binding_spec_sha256": spec_sha,
        "seam_binding_rehearsal_sha256": rehearsal_sha,
        "writer_count": 19,
        "all_source_signatures_bound": True,
        "all_adaptation_strategies_bound": True,
        "reentrant_owner_token_required": True,
        "installation_order_bound": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["seam_binding_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "seam_binding_contract_verified": True,
            "synthetic_rehearsal_valid": True,
            "status": "CLOSED_REPAIR_WRITER_SEAM_BINDING_V1_VALID_OFFLINE_PRODUCTION_BLOCKED",
            "reasons": [],
            "checks": checks,
            "seam_binding_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_CONTRACT_V1_VERSION",
    "canonical_writer_seam_bindings_v1",
    "canonical_writer_seam_installation_order_v1",
    "evaluate_closed_repair_writer_seam_binding_offline_v1",
    "writer_seam_binding_rehearsal_sha256_v1",
    "writer_seam_binding_spec_sha256_v1",
]
