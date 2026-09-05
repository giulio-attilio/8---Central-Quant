"""Offline contract for binding C3 readiness to an exact future Live gate.

The module validates only canonical source attestations and policy data.  It
does not import runtime modules, inspect the Registry, bind a coordinator or
authorize activation.  A valid result means that the *policy contract* is
complete; production, runtime installation, activation and Live remain denied.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from typing import Any


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-05-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-READINESS-BINDING-CONTRACT-V1"
)

_SPEC_VERSION = "C3_RUNTIME_READINESS_BINDING_POLICY_OFFLINE_V1"
_SCOPE_ATTESTATION = "C3_RUNTIME_READINESS_BINDING_REVIEW_OFFLINE_ONLY_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_SOURCE_ATTESTATION_PINS = (
    {
        "role": "controlled_activation_contract",
        "path": "trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_contract_v1.py",
        "sha256": "ee4359680ee610ee2424271f4bd1552a2018b802b25d3c4396faeb9c17b572d1",
        "normalized_size_bytes": 15557,
    },
    {
        "role": "runtime_seam",
        "path": "trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py",
        "sha256": "a730aed656c96c8def4393676e76f049730b5853eaaded7340d91725a79da3c7",
        "normalized_size_bytes": 15709,
    },
    {
        "role": "static_preflight",
        "path": "trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py",
        "sha256": "38b534fa7e91a4f0b11eb6494789027a2fa044df3628bea9e895619aa9bed2ea",
        "normalized_size_bytes": 24501,
    },
    {
        "role": "live_preflight_owner",
        "path": "main.py",
        "sha256": "b2d5c53770b0ba20ef29ac0cc0dbe8c2792b814475bbf29d77bf1e4125c0599f",
        "normalized_size_bytes": 2962946,
    },
)

_RUNTIME_READINESS_VECTOR = (
    ("enabled", True),
    ("coordination_ready", True),
    ("runtime_activation_allowed", True),
    ("registered_writer_count", 19),
    ("all_writers_registered", True),
    ("inflight_mutations", 0),
    ("shared_lock_backend_ready", True),
    ("maintenance_lease_store_ready", True),
    ("registry_interlock_ready", True),
    ("activation_receipt_verified", True),
    ("source_hashes_verified", True),
    ("rollback_ready", True),
    ("kill_switch_ready", True),
)

_LIVE_PREFLIGHT_PREDICATES = tuple(
    {
        "field": field,
        "operator": "is" if isinstance(expected, bool) else "equals",
        "expected": expected,
        "blocking": True,
    }
    for field, expected in _RUNTIME_READINESS_VECTOR
)

_PRODUCTION_BLOCKERS = (
    "READINESS_BINDING_IS_POLICY_ONLY",
    "RUNTIME_SEAM_DOES_NOT_EXPOSE_POSITIVE_READINESS_VECTOR",
    "CONTROLLED_ACTIVATION_RECEIPT_IS_NOT_CONSUMED_BY_RUNTIME",
    "DORMANT_SEAM_REJECTS_ENABLED_COORDINATOR",
    "RUNTIME_BINDING_NOT_IMPLEMENTED",
    "REAL_SOURCE_HASHES_MUST_BE_RECHECKED_AFTER_ANY_PATCH",
    "SEPARATE_RUNTIME_PATCH_REQUIRED",
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


def source_text_sha256_v1(source_text: str) -> tuple[str, int]:
    """Hash UTF-8 source after deterministic newline normalization."""

    if not isinstance(source_text, str):
        raise TypeError("source_text must be str")
    normalized = source_text.replace("\r\n", "\n").replace("\r", "\n")
    payload = normalized.encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), len(payload)


def canonical_c3_readiness_source_attestation_pins_v1() -> list[dict[str, Any]]:
    return _canonical_copy(list(_SOURCE_ATTESTATION_PINS))


def canonical_c3_runtime_readiness_vector_v1() -> dict[str, Any]:
    return dict(_RUNTIME_READINESS_VECTOR)


def canonical_c3_live_preflight_predicates_v1() -> list[dict[str, Any]]:
    return _canonical_copy(list(_LIVE_PREFLIGHT_PREDICATES))


def readiness_binding_spec_sha256_v1(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("spec must be a mapping")
    return _stable_sha256({key: value for key, value in spec.items() if key != "spec_sha256"})


def _receipt_sha256(receipt: Mapping[str, Any], field: str) -> str:
    return _stable_sha256({key: value for key, value in receipt.items() if key != field})


def _base() -> dict[str, Any]:
    return {
        "ok": False,
        "binding_contract_verified": False,
        "upstream_activation_contract_verified": False,
        "source_hashes_verified": False,
        "runtime_readiness_policy_verified": False,
        "live_preflight_policy_verified": False,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "status": "C3_RUNTIME_READINESS_BINDING_V1_BLOCKED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_CONTRACT_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "policy_only": True,
        "read_only": True,
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
    receipt = upstream.get("proposal_receipt")
    supplied = (
        _valid_sha256(receipt.get("proposal_receipt_sha256"))
        if isinstance(receipt, Mapping)
        else ""
    )
    expected = (
        _receipt_sha256(receipt, "proposal_receipt_sha256")
        if isinstance(receipt, Mapping)
        else ""
    )
    checks["upstream_controlled_activation_receipt_valid"] = bool(
        upstream.get("ok") is True
        and upstream.get("proposal_contract_verified") is True
        and upstream.get("upstream_patch_plan_verified") is True
        and upstream.get("writer_inventory_verified") is True
        and upstream.get("safety_controls_verified") is True
        and upstream.get("dormant_seam_verified") is True
        and upstream.get("production_ready") is False
        and upstream.get("activation_allowed") is False
        and upstream.get("runtime_patch_allowed") is False
        and upstream.get("runtime_install_allowed") is False
        and upstream.get("runtime_start_allowed") is False
        and upstream.get("live_allowed") is False
        and isinstance(receipt, Mapping)
        and supplied
        and hmac.compare_digest(supplied, expected)
        and receipt.get("writer_count") == 19
        and receipt.get("source_hashes_must_be_rechecked") is True
        and receipt.get("production_ready") is False
        and receipt.get("activation_allowed") is False
        and receipt.get("runtime_patch_allowed") is False
        and receipt.get("runtime_install_allowed") is False
        and receipt.get("runtime_start_allowed") is False
        and receipt.get("live_allowed") is False
        and bool(receipt.get("production_blockers"))
    )
    if not checks["upstream_controlled_activation_receipt_valid"]:
        reasons.append("READINESS_BINDING_UPSTREAM_ACTIVATION_RECEIPT_INVALID")
    return supplied


def _check_sources(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> str:
    expected = canonical_c3_readiness_source_attestation_pins_v1()
    attestations = spec.get("source_attestations")
    expected_sha = _stable_sha256(expected)
    checks["source_attestations_exact"] = bool(
        attestations == expected
        and len(expected) == 4
        and len({item["role"] for item in expected}) == 4
        and len({item["path"] for item in expected}) == 4
        and all(_valid_sha256(item.get("sha256")) for item in expected)
        and spec.get("source_attestations_sha256") == expected_sha
    )
    if not checks["source_attestations_exact"]:
        reasons.append("READINESS_BINDING_SOURCE_ATTESTATIONS_INVALID")
    return expected_sha


def _check_readiness_policy(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> tuple[str, str]:
    expected_vector = canonical_c3_runtime_readiness_vector_v1()
    vector = spec.get("required_runtime_readiness_vector")
    vector_sha = _stable_sha256(expected_vector)
    checks["runtime_readiness_vector_exact"] = bool(
        vector == expected_vector
        and len(expected_vector) == 13
        and spec.get("required_runtime_readiness_vector_sha256") == vector_sha
    )

    expected_predicates = canonical_c3_live_preflight_predicates_v1()
    predicates = spec.get("live_preflight_predicates")
    predicates_sha = _stable_sha256(expected_predicates)
    checks["live_preflight_predicates_exact"] = bool(
        predicates == expected_predicates
        and len(expected_predicates) == len(expected_vector)
        and [item.get("field") for item in predicates]
        == list(expected_vector)
        and all(item.get("blocking") is True for item in predicates)
        and spec.get("live_preflight_predicates_sha256") == predicates_sha
    )

    consumer = spec.get("consumer_policy")
    checks["consumer_policy_fail_closed"] = bool(
        isinstance(consumer, Mapping)
        and consumer.get("require_all_predicates") is True
        and consumer.get("missing_field_blocks") is True
        and consumer.get("unknown_field_blocks") is True
        and consumer.get("generic_ok_is_insufficient") is True
        and consumer.get("exact_boolean_identity_required") is True
        and consumer.get("activation_receipt_sha256_required") is True
        and consumer.get("source_attestation_sha256_required") is True
        and consumer.get("static_preflight_must_prove_predicate_semantics") is True
        and consumer.get("runtime_status_must_be_sampled_at_decision_time") is True
        and consumer.get("cached_readiness_forbidden") is True
    )
    for check, reason in (
        ("runtime_readiness_vector_exact", "READINESS_BINDING_RUNTIME_VECTOR_INVALID"),
        ("live_preflight_predicates_exact", "READINESS_BINDING_LIVE_PREDICATES_INVALID"),
        ("consumer_policy_fail_closed", "READINESS_BINDING_CONSUMER_POLICY_INVALID"),
    ):
        if not checks[check]:
            reasons.append(reason)
    return vector_sha, predicates_sha


def _check_safety(
    spec: Mapping[str, Any], reasons: list[str], checks: dict[str, bool]
) -> None:
    safety = spec.get("safety_envelope")
    checks["safety_envelope_offline_only"] = bool(
        isinstance(safety, Mapping)
        and safety.get("scope_attestation") == _SCOPE_ATTESTATION
        and safety.get("policy_contract_only") is True
        and safety.get("source_read_only") is True
        and safety.get("runtime_imported") is False
        and safety.get("runtime_integrated") is False
        and safety.get("real_registry_accessed") is False
        and safety.get("network_accessed") is False
        and safety.get("broker_called") is False
        and safety.get("write_executed") is False
        and safety.get("runtime_patch_authorized") is False
        and safety.get("production_activation_authorized") is False
        and safety.get("live_authorized") is False
        and safety.get("order_submission_authorized") is False
        and safety.get("no_order_sent") is True
    )
    if not checks["safety_envelope_offline_only"]:
        reasons.append("READINESS_BINDING_SAFETY_ENVELOPE_INVALID")


def evaluate_c3_runtime_readiness_binding_policy_offline_v1(
    controlled_activation_result: Mapping[str, Any],
    readiness_binding_spec: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the future binding policy while always denying activation."""

    base = _base()
    reasons: list[str] = base["reasons"]
    checks: dict[str, bool] = base["checks"]
    if not isinstance(controlled_activation_result, Mapping) or not isinstance(
        readiness_binding_spec, Mapping
    ):
        reasons.append("READINESS_BINDING_MAPPING_INPUTS_REQUIRED")
        return base
    try:
        upstream = _canonical_copy(controlled_activation_result)
        spec = _canonical_copy(readiness_binding_spec)
    except (TypeError, ValueError, OverflowError):
        reasons.append("READINESS_BINDING_INPUT_NOT_CANONICALIZABLE")
        return base

    upstream_sha = _check_upstream(upstream, reasons, checks)
    source_sha = _check_sources(spec, reasons, checks)
    vector_sha, predicates_sha = _check_readiness_policy(spec, reasons, checks)
    _check_safety(spec, reasons, checks)

    supplied_spec_sha = _valid_sha256(spec.get("spec_sha256"))
    checks["binding_spec_sha256_valid"] = bool(
        supplied_spec_sha
        and hmac.compare_digest(
            supplied_spec_sha,
            readiness_binding_spec_sha256_v1(spec),
        )
    )
    checks["binding_spec_envelope_exact"] = bool(
        spec.get("spec_version") == _SPEC_VERSION
        and spec.get("upstream_proposal_receipt_sha256") == upstream_sha
        and spec.get("dormant") is True
        and spec.get("default_off") is True
        and spec.get("offline_only") is True
        and spec.get("policy_only") is True
        and spec.get("runtime_binding_satisfied") is False
        and spec.get("production_ready") is False
        and spec.get("activation_allowed") is False
        and spec.get("live_allowed") is False
    )
    if not checks["binding_spec_sha256_valid"]:
        reasons.append("READINESS_BINDING_SPEC_SHA256_INVALID")
    if not checks["binding_spec_envelope_exact"]:
        reasons.append("READINESS_BINDING_SPEC_ENVELOPE_INVALID")

    reasons[:] = sorted(set(str(reason) for reason in reasons))
    if reasons or not checks or not all(checks.values()):
        if not reasons:
            reasons.append("ONE_OR_MORE_READINESS_BINDING_CHECKS_FAILED")
        return base

    receipt = {
        "upstream_proposal_receipt_sha256": upstream_sha,
        "readiness_binding_spec_sha256": supplied_spec_sha,
        "source_attestations_sha256": source_sha,
        "required_runtime_readiness_vector_sha256": vector_sha,
        "live_preflight_predicates_sha256": predicates_sha,
        "source_attestation_count": 4,
        "required_predicate_count": len(_RUNTIME_READINESS_VECTOR),
        "writer_count": 19,
        "policy_complete_offline": True,
        "source_hashes_must_be_rechecked_after_patch": True,
        "runtime_binding_satisfied": False,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_patch_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "production_blockers": list(_PRODUCTION_BLOCKERS),
    }
    receipt["binding_receipt_sha256"] = _stable_sha256(receipt)
    base.update(
        {
            "ok": True,
            "binding_contract_verified": True,
            "upstream_activation_contract_verified": True,
            "source_hashes_verified": True,
            "runtime_readiness_policy_verified": True,
            "live_preflight_policy_verified": True,
            "status": "C3_RUNTIME_READINESS_BINDING_V1_VALID_OFFLINE_NON_APPLICABLE",
            "reasons": [],
            "checks": checks,
            "binding_receipt": receipt,
        }
    )
    return base


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_READINESS_BINDING_CONTRACT_V1_VERSION",
    "canonical_c3_live_preflight_predicates_v1",
    "canonical_c3_readiness_source_attestation_pins_v1",
    "canonical_c3_runtime_readiness_vector_v1",
    "evaluate_c3_runtime_readiness_binding_policy_offline_v1",
    "readiness_binding_spec_sha256_v1",
    "source_text_sha256_v1",
]
