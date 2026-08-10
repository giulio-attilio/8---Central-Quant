"""Pure Falcon V2.8 VERIFY factual-identity shadow projection.

The observer receives facts already produced by Falcon V2.7A.  It never
generates, repairs, persists, or authorizes an identity, and it has no broker,
Registry, network, or Decision Identity Store dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any


SHADOW_STAGE_PRE_DECISION = "PRE_DECISION"
SHADOW_STAGE_POST_DECISION = "POST_DECISION"

OBSERVED = "OBSERVED"
IDENTITY_UNAVAILABLE = "IDENTITY_UNAVAILABLE"
IDENTITY_INCOMPLETE = "IDENTITY_INCOMPLETE"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
IDENTITY_HISTORICAL_ONLY = "IDENTITY_HISTORICAL_ONLY"
NOT_APPLICABLE = "NOT_APPLICABLE"

# Stable public aliases retained for the V2.8 surface.
FALCON_V2_VERIFY_SHADOW_OBSERVED = OBSERVED
FALCON_V2_VERIFY_SHADOW_OK = OBSERVED
FALCON_V2_VERIFY_SHADOW_IDENTITY_UNAVAILABLE = IDENTITY_UNAVAILABLE
FALCON_V2_VERIFY_SHADOW_IDENTITY_INCOMPLETE = IDENTITY_INCOMPLETE
FALCON_V2_VERIFY_SHADOW_IDENTITY_CONFLICT = IDENTITY_CONFLICT
FALCON_V2_VERIFY_SHADOW_HISTORICAL_IDENTITY_ONLY = IDENTITY_HISTORICAL_ONLY
FALCON_V2_VERIFY_SHADOW_MODE_BLOCKED = "VERIFY_MODE_REQUIRED"
FALCON_V2_VERIFY_SHADOW_PHYSICAL_ID_FORBIDDEN = "PHYSICAL_IDENTITY_FORBIDDEN"

_EXTERNAL_OWNER_TYPES = frozenset({"MANUAL_EXTERNAL", "EXTERNAL"})
_STATUS_PRIORITY = {
    OBSERVED: 0,
    NOT_APPLICABLE: 0,
    IDENTITY_UNAVAILABLE: 1,
    IDENTITY_INCOMPLETE: 2,
    IDENTITY_HISTORICAL_ONLY: 3,
    IDENTITY_CONFLICT: 4,
}


class FalconRegistryV2VerifyShadowObservationError(Exception):
    """Expected non-authoritative observer/projection failure boundary."""


@dataclass(frozen=True)
class FalconRegistryV2VerifyShadowInput:
    """Explicit read-only input shape for one factual shadow observation."""

    shadow_stage: Any = SHADOW_STAGE_PRE_DECISION
    execution_mode: Any = "VERIFY"
    signal: Any = None
    decision: Any = None
    paired_pre: Any = None
    execution_id: Any = None
    lifecycle_id: Any = None
    logical_trade_id: Any = None


@dataclass(frozen=True)
class FalconRegistryV2VerifyShadowProjection:
    """Immutable factual projection; physical execution identity is always absent."""

    shadow_stage: str | None
    execution_mode: Any
    setup: Any
    symbol: Any
    side: Any
    position_side: Any
    position_side_source: str | None
    raw_positionSide: Any
    raw_position_side: Any
    raw_side: Any
    raw_position_side_conflict: bool
    owner_type: Any
    owner_status: str
    central_plan_provenance: bool
    ownership_scope: Any
    owner_plan_provenance: Any
    logical_trade_id: Any
    signal_id: str | None
    signal_identity_status: str
    decision_request_id: str | None
    decision_request_identity_status: str
    decision_id: str | None
    decision_identity_status: str
    identity_status: str
    execution_id: None = None
    lifecycle_id: None = None
    shadow_identity_operational: bool = False


@dataclass(frozen=True)
class FalconRegistryV2VerifyShadowResult:
    """Stable result of a pure factual observation."""

    ok: bool
    status: str
    projection: FalconRegistryV2VerifyShadowProjection
    errors: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


def observe_falcon_registry_v2_verify_shadow(
    payload: Any,
) -> FalconRegistryV2VerifyShadowResult:
    """Project factual V2.7A identity without changing its meaning or state."""

    values = _as_mapping(payload) or {}
    signal = _as_mapping(values.get("signal")) or {}
    decision = _as_mapping(values.get("decision")) or {}
    stage = _text(values.get("shadow_stage"))
    execution_mode = values.get("execution_mode")
    diagnostics: list[str] = []
    statuses: list[str] = []

    if stage not in {SHADOW_STAGE_PRE_DECISION, SHADOW_STAGE_POST_DECISION}:
        statuses.append(IDENTITY_CONFLICT)
        diagnostics.append("shadow_stage_invalid")
    if _upper(execution_mode) != "VERIFY":
        statuses.append(IDENTITY_CONFLICT)
        diagnostics.append(FALCON_V2_VERIFY_SHADOW_MODE_BLOCKED)

    for field in ("execution_id", "lifecycle_id"):
        if _present(values.get(field)) or _present(signal.get(field)) or _present(
            decision.get(field)
        ):
            statuses.append(IDENTITY_CONFLICT)
            diagnostics.append(f"{field}:{FALCON_V2_VERIFY_SHADOW_PHYSICAL_ID_FORBIDDEN}")

    position_side, position_side_source, position_provenance = _position_side(signal)
    owner = _owner_projection(signal)
    signal_id = _text(signal.get("signal_id"))
    request_id = _text(signal.get("decision_request_id"))
    decision_id = _text(decision.get("decision_id"))

    signal_status, signal_diagnostics = _signal_status(signal, signal_id)
    request_status, request_diagnostics = _request_status(signal, signal_id, request_id)
    diagnostics.extend(signal_diagnostics)
    diagnostics.extend(request_diagnostics)
    statuses.extend((signal_status, request_status))

    if stage == SHADOW_STAGE_PRE_DECISION:
        decision_status, decision_diagnostics = _pre_decision_status(signal, decision)
    elif stage == SHADOW_STAGE_POST_DECISION:
        decision_status, decision_diagnostics = _post_decision_status(
            signal, decision, signal_id, request_id, decision_id
        )
        pair_status, pair_diagnostics = _paired_pre_status(
            values.get("paired_pre"),
            signal,
            signal_id,
            request_id,
            position_side,
            position_provenance,
            owner,
        )
        decision_status = _worst_status(decision_status, pair_status)
        decision_diagnostics.extend(pair_diagnostics)
    else:
        decision_status, decision_diagnostics = IDENTITY_CONFLICT, [
            "shadow_stage_invalid"
        ]
    diagnostics.extend(decision_diagnostics)
    statuses.append(decision_status)

    identity_status = _worst_status(*statuses)
    projection = FalconRegistryV2VerifyShadowProjection(
        shadow_stage=stage,
        execution_mode=execution_mode,
        setup=_freeze(signal.get("setup")),
        symbol=_freeze(signal.get("symbol")),
        side=_freeze(signal.get("side")),
        position_side=_freeze(position_side),
        position_side_source=position_side_source,
        raw_positionSide=_freeze(position_provenance["raw_positionSide"]),
        raw_position_side=_freeze(position_provenance["raw_position_side"]),
        raw_side=_freeze(position_provenance["raw_side"]),
        raw_position_side_conflict=position_provenance["conflict"],
        owner_type=_freeze(owner["owner_type"]),
        owner_status=owner["status"],
        central_plan_provenance=owner["central_plan_provenance"],
        ownership_scope=_freeze(owner["ownership_scope"]),
        owner_plan_provenance=_freeze(owner["plan_provenance"]),
        logical_trade_id=_freeze(
            values.get("logical_trade_id", signal.get("logical_trade_id"))
        ),
        signal_id=signal_id,
        signal_identity_status=signal_status,
        decision_request_id=request_id,
        decision_request_identity_status=request_status,
        decision_id=decision_id,
        decision_identity_status=decision_status,
        identity_status=identity_status,
    )
    errors = tuple(item for item in diagnostics if ":" in item or item.endswith("invalid"))
    return FalconRegistryV2VerifyShadowResult(
        ok=identity_status == OBSERVED,
        status=identity_status,
        projection=projection,
        errors=errors,
        diagnostics=tuple(diagnostics),
    )


def project_falcon_registry_v2_verify_shadow(
    payload: Any,
) -> FalconRegistryV2VerifyShadowResult:
    """Alias for the pure observer entry point."""

    return observe_falcon_registry_v2_verify_shadow(payload)


def validate_falcon_registry_v2_verify_shadow(
    payload: Any,
) -> FalconRegistryV2VerifyShadowResult:
    """Alias emphasizing validation without any repair or write."""

    return observe_falcon_registry_v2_verify_shadow(payload)


def _signal_status(signal: Mapping[str, Any], signal_id: str | None) -> tuple[str, list[str]]:
    if signal_id is None:
        return IDENTITY_UNAVAILABLE, ["signal_id:IDENTITY_UNAVAILABLE"]
    version = _text(signal.get("signal_identity_version"))
    provenance = _as_mapping(signal.get("signal_identity_provenance"))
    if version is None or provenance is None:
        return IDENTITY_INCOMPLETE, ["signal_id:IDENTITY_INCOMPLETE"]
    provenance_version = _text(provenance.get("identity_version"))
    if provenance_version is not None and provenance_version != version:
        return IDENTITY_CONFLICT, ["signal_identity_version:IDENTITY_CONFLICT"]
    return OBSERVED, []


def _request_status(
    signal: Mapping[str, Any], signal_id: str | None, request_id: str | None
) -> tuple[str, list[str]]:
    if request_id is None:
        return IDENTITY_UNAVAILABLE, ["decision_request_id:IDENTITY_UNAVAILABLE"]
    if signal_id is None:
        return IDENTITY_UNAVAILABLE, ["decision_request_signal:IDENTITY_UNAVAILABLE"]
    version = _text(signal.get("decision_request_identity_version"))
    provenance = _as_mapping(signal.get("decision_request_identity_provenance"))
    if version is None or provenance is None:
        return IDENTITY_INCOMPLETE, ["decision_request_id:IDENTITY_INCOMPLETE"]
    provenance_signal = _text(provenance.get("signal_id"))
    if provenance_signal is None:
        return IDENTITY_INCOMPLETE, ["decision_request_signal:IDENTITY_INCOMPLETE"]
    if provenance_signal != signal_id:
        return IDENTITY_CONFLICT, ["decision_request_signal:IDENTITY_CONFLICT"]
    provenance_version = _text(provenance.get("identity_version"))
    if provenance_version is not None and provenance_version != version:
        return IDENTITY_CONFLICT, ["decision_request_version:IDENTITY_CONFLICT"]
    return OBSERVED, []


def _pre_decision_status(
    signal: Mapping[str, Any], decision: Mapping[str, Any]
) -> tuple[str, list[str]]:
    if _present(signal.get("decision_id")) or _present(decision.get("decision_id")):
        return IDENTITY_CONFLICT, ["pre_decision_id_present:IDENTITY_CONFLICT"]
    return NOT_APPLICABLE, []


def _post_decision_status(
    signal: Mapping[str, Any],
    decision: Mapping[str, Any],
    signal_id: str | None,
    request_id: str | None,
    decision_id: str | None,
) -> tuple[str, list[str]]:
    metadata = _as_mapping(decision.get("decision_identity_v2_7a_2"))
    metadata_status = _text(metadata.get("status")) if metadata is not None else None
    if metadata_status == "IDENTITY_REPLAY_HISTORICAL_ONLY":
        return IDENTITY_HISTORICAL_ONLY, ["decision_identity:IDENTITY_HISTORICAL_ONLY"]
    if decision_id is None:
        if metadata_status and ("INCOMPLETE" in metadata_status or "CLAIMED" in metadata_status):
            return IDENTITY_INCOMPLETE, ["decision_id:IDENTITY_INCOMPLETE"]
        if metadata_status and "CONFLICT" in metadata_status:
            return IDENTITY_CONFLICT, ["decision_id:IDENTITY_CONFLICT"]
        return IDENTITY_UNAVAILABLE, ["decision_id:IDENTITY_UNAVAILABLE"]
    version = _text(decision.get("decision_identity_version"))
    provenance = _as_mapping(decision.get("decision_identity_provenance"))
    if signal_id is None or request_id is None or version is None or provenance is None:
        return IDENTITY_INCOMPLETE, ["decision_identity:IDENTITY_INCOMPLETE"]
    if metadata is None or metadata_status != "COMPLETED" or metadata.get("identity_available") is not True:
        return IDENTITY_INCOMPLETE, ["decision_completion:IDENTITY_INCOMPLETE"]

    conflicts = []
    for field, expected in (
        ("signal_id", signal_id),
        ("request_id", request_id),
    ):
        value = _text(provenance.get(field))
        if value is None:
            return IDENTITY_INCOMPLETE, [f"decision_{field}:IDENTITY_INCOMPLETE"]
        if value != expected:
            conflicts.append(f"decision_{field}:IDENTITY_CONFLICT")
    for field, expected in (
        ("signal_id", signal_id),
        ("decision_request_id", request_id),
    ):
        value = _text(metadata.get(field))
        if value is None:
            return IDENTITY_INCOMPLETE, [f"decision_metadata_{field}:IDENTITY_INCOMPLETE"]
        if value != expected:
            conflicts.append(f"decision_metadata_{field}:IDENTITY_CONFLICT")
    for container, field in ((provenance, "decision_id"), (metadata, "decision_id")):
        value = _text(container.get(field))
        if value is not None and value != decision_id:
            conflicts.append("decision_id:IDENTITY_CONFLICT")
    response_request_id = _text(decision.get("decision_request_id"))
    if response_request_id is None:
        return IDENTITY_INCOMPLETE, ["decision_request_response:IDENTITY_INCOMPLETE"]
    if response_request_id != request_id:
        conflicts.append("decision_request_response:IDENTITY_CONFLICT")
    response_signal_id = _text(decision.get("signal_id"))
    if response_signal_id is not None and response_signal_id != signal_id:
        conflicts.append("decision_signal_response:IDENTITY_CONFLICT")
    if conflicts:
        return IDENTITY_CONFLICT, conflicts
    return OBSERVED, []


def _paired_pre_status(
    value: Any,
    signal: Mapping[str, Any],
    signal_id: str | None,
    request_id: str | None,
    position_side: Any,
    position_provenance: Mapping[str, Any],
    owner: Mapping[str, Any],
) -> tuple[str, list[str]]:
    result = _paired_result(value)
    if result is None:
        return IDENTITY_INCOMPLETE, ["paired_pre:IDENTITY_INCOMPLETE"]
    if result.status != OBSERVED:
        status = (
            IDENTITY_CONFLICT
            if result.status in {IDENTITY_CONFLICT, IDENTITY_HISTORICAL_ONLY}
            else IDENTITY_INCOMPLETE
        )
        return status, [f"paired_pre:{status}"]
    prior = result.projection
    comparisons = {
        "signal_id": (prior.signal_id, signal_id),
        "decision_request_id": (prior.decision_request_id, request_id),
        "setup": (prior.setup, _freeze(signal.get("setup"))),
        "symbol": (prior.symbol, _freeze(signal.get("symbol"))),
        "side": (prior.side, _freeze(signal.get("side"))),
        "position_side": (prior.position_side, _freeze(position_side)),
        "raw_positionSide": (
            prior.raw_positionSide,
            _freeze(position_provenance["raw_positionSide"]),
        ),
        "raw_position_side": (
            prior.raw_position_side,
            _freeze(position_provenance["raw_position_side"]),
        ),
        "owner_type": (prior.owner_type, _freeze(owner["owner_type"])),
        "owner_plan_provenance": (
            prior.owner_plan_provenance,
            _freeze(owner["plan_provenance"]),
        ),
    }
    mismatches = [
        f"paired_pre_{field}:IDENTITY_CONFLICT"
        for field, (before, after) in comparisons.items()
        if before != after
    ]
    if mismatches:
        return IDENTITY_CONFLICT, mismatches
    return OBSERVED, []


def _paired_result(value: Any) -> FalconRegistryV2VerifyShadowResult | None:
    if isinstance(value, FalconRegistryV2VerifyShadowResult):
        return value
    result = getattr(value, "result", None)
    if isinstance(result, FalconRegistryV2VerifyShadowResult):
        return result
    return None


def _position_side(signal: Mapping[str, Any]) -> tuple[Any, str | None, dict[str, Any]]:
    raw_camel = signal.get("positionSide")
    raw_snake = signal.get("position_side")
    raw_side = signal.get("side")
    selected = None
    source = None
    for key, value in (
        ("positionSide", raw_camel),
        ("position_side", raw_snake),
        ("side", raw_side),
    ):
        if _present(value):
            selected = value
            source = key
            break
    conflict = bool(
        _present(raw_camel)
        and _present(raw_snake)
        and _upper(raw_camel) != _upper(raw_snake)
    )
    return selected, source, {
        "raw_positionSide": raw_camel,
        "raw_position_side": raw_snake,
        "raw_side": raw_side,
        "conflict": conflict,
    }


def _owner_projection(signal: Mapping[str, Any]) -> dict[str, Any]:
    owner_type = signal.get("owner_type")
    owner_text = _upper(owner_type)
    signal_provenance = _as_mapping(signal.get("signal_identity_provenance")) or {}
    plan_provenance = _as_mapping(signal_provenance.get("plan_provenance")) or {}
    scope = plan_provenance.get("ownership_scope")
    if owner_text in _EXTERNAL_OWNER_TYPES:
        return {
            "owner_type": owner_type,
            "status": "EXTERNAL_PRESERVED",
            "central_plan_provenance": False,
            "ownership_scope": scope,
            "plan_provenance": plan_provenance,
        }
    central_plan = bool(
        plan_provenance.get("plan_owner_type") == "CENTRAL"
        and scope == "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP"
    )
    return {
        "owner_type": owner_type,
        "status": "CENTRAL_PLAN_ONLY" if central_plan else "OWNER_PLAN_UNAVAILABLE",
        "central_plan_provenance": central_plan,
        "ownership_scope": scope,
        "plan_provenance": plan_provenance,
    }


def _worst_status(*statuses: str) -> str:
    return max(statuses, key=lambda value: _STATUS_PRIORITY.get(value, 4))


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, FalconRegistryV2VerifyShadowInput):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    return None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _upper(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text is not None else None


def _present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _freeze(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_freeze(item) for item in value), key=repr))
    return value


__all__ = (
    "FALCON_V2_VERIFY_SHADOW_HISTORICAL_IDENTITY_ONLY",
    "FALCON_V2_VERIFY_SHADOW_IDENTITY_CONFLICT",
    "FALCON_V2_VERIFY_SHADOW_IDENTITY_INCOMPLETE",
    "FALCON_V2_VERIFY_SHADOW_IDENTITY_UNAVAILABLE",
    "FALCON_V2_VERIFY_SHADOW_MODE_BLOCKED",
    "FALCON_V2_VERIFY_SHADOW_OBSERVED",
    "FALCON_V2_VERIFY_SHADOW_OK",
    "FALCON_V2_VERIFY_SHADOW_PHYSICAL_ID_FORBIDDEN",
    "FalconRegistryV2VerifyShadowInput",
    "FalconRegistryV2VerifyShadowObservationError",
    "FalconRegistryV2VerifyShadowProjection",
    "FalconRegistryV2VerifyShadowResult",
    "IDENTITY_CONFLICT",
    "IDENTITY_HISTORICAL_ONLY",
    "IDENTITY_INCOMPLETE",
    "IDENTITY_UNAVAILABLE",
    "NOT_APPLICABLE",
    "OBSERVED",
    "SHADOW_STAGE_POST_DECISION",
    "SHADOW_STAGE_PRE_DECISION",
    "observe_falcon_registry_v2_verify_shadow",
    "project_falcon_registry_v2_verify_shadow",
    "validate_falcon_registry_v2_verify_shadow",
)
