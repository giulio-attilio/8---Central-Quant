"""Pure, dormant V2.7 contracts for Central Quant components.

This module describes future V2 identity requirements without integrating any
productive caller.  It validates supplied values only: it never generates an
identity, resolves ownership, reads a registry, or talks to a broker.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from registry_execution_identity import is_v2_execution_id
import registry_execution_schema as schema


REGISTRY_V2_BOT_CONTRACT_OK = "REGISTRY_V2_BOT_CONTRACT_OK"
REGISTRY_V2_BOT_CONTRACT_COMPONENT_UNSUPPORTED = "REGISTRY_V2_BOT_CONTRACT_COMPONENT_UNSUPPORTED"
REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED = "REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED"
REGISTRY_V2_BOT_CONTRACT_ID_INVALID = "REGISTRY_V2_BOT_CONTRACT_ID_INVALID"
REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT = "REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT"
REGISTRY_V2_BOT_CONTRACT_LOGICAL_CONFLICT = "REGISTRY_V2_BOT_CONTRACT_LOGICAL_CONFLICT"
REGISTRY_V2_BOT_CONTRACT_OWNER_CONFLICT = "REGISTRY_V2_BOT_CONTRACT_OWNER_CONFLICT"
REGISTRY_V2_BOT_CONTRACT_MODE_INVALID = "REGISTRY_V2_BOT_CONTRACT_MODE_INVALID"
REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING = "REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING"
REGISTRY_V2_BOT_CONTRACT_INVALID = "REGISTRY_V2_BOT_CONTRACT_INVALID"
REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION = "REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION"
REGISTRY_V2_BOT_CONTRACT_VERIFY_NON_EXECUTION = "REGISTRY_V2_BOT_CONTRACT_VERIFY_NON_EXECUTION"

_BOT_COMPONENTS = frozenset({"FALCON", "TURTLE", "PREDATOR", "DONKEY", "TRENDPRO", "COBRA", "MEME"})
_STRONG_FIELDS = (
    "client_order_id",
    "broker_order_id",
    "exchange_order_id",
    "fill_id",
    "close_event_id",
)


@dataclass(frozen=True)
class RegistryV2BotContractSpec:
    component: str
    priority: str
    requires_execution_id: bool
    requires_lifecycle_alias: bool
    requires_signal_id: bool
    requires_decision_id: bool
    allows_paper: bool
    allows_live_contract: bool
    requirements: tuple[str, ...]
    allows_verify_description: bool = True
    requires_position_side: bool = False
    requires_registry_mode: bool = False


@dataclass(frozen=True)
class RegistryV2BotIdentityProjection:
    component: str
    execution_id: str | None
    lifecycle_id: str | None
    logical_trade_id: str | None
    bot: str
    setup: str
    symbol: str
    side: str
    position_side: str | None
    owner_type: str
    execution_mode: str
    registry_mode: str | None
    signal_id: str | None
    decision_id: str | None
    metadata: tuple[tuple[str, Any], ...] = ()
    client_order_id: str | None = None
    broker_order_id: str | None = None
    exchange_order_id: str | None = None
    fill_id: str | None = None
    close_event_id: str | None = None


@dataclass(frozen=True)
class RegistryV2BotContractResult:
    ok: bool
    status: str
    projection: RegistryV2BotIdentityProjection | None = None
    errors: tuple[str, ...] = ()


def _spec(
    component: str,
    priority: str,
    *,
    requires_signal_id: bool = False,
    requires_decision_id: bool = False,
    allows_live_contract: bool = True,
    requires_position_side: bool = False,
    requires_registry_mode: bool = False,
    requirements: tuple[str, ...],
) -> RegistryV2BotContractSpec:
    return RegistryV2BotContractSpec(
        component=component,
        priority=priority,
        requires_execution_id=True,
        requires_lifecycle_alias=True,
        requires_signal_id=requires_signal_id,
        requires_decision_id=requires_decision_id,
        allows_paper=True,
        allows_live_contract=allows_live_contract,
        requirements=requirements,
        requires_position_side=requires_position_side,
        requires_registry_mode=requires_registry_mode,
    )


_CONTRACT_SPECS = {
    "FALCON": _spec(
        "FALCON",
        "P0",
        requires_signal_id=True,
        requires_decision_id=True,
        requires_position_side=True,
        requirements=(
            "execution_id_before_broker",
            "lifecycle_id_equals_execution_id",
            "signal_id_required",
            "decision_id_required",
            "owner_type_central",
            "position_side_exact",
            "strict_recovery_identity",
            "no_logical_mutation_locator",
            "no_broker_average_truth",
        ),
    ),
    "TURTLE": _spec(
        "TURTLE",
        "P1",
        allows_live_contract=False,
        requirements=(
            "paper_identity_at_birth",
            "execution_id_lifecycle_id_primary",
            "logical_id_grouping_only",
            "no_symbol_side_mutation_fallback",
        ),
    ),
    "PREDATOR": _spec(
        "PREDATOR",
        "P1",
        requires_registry_mode=True,
        requirements=(
            "paper_live_data_contract",
            "execution_id_lifecycle_id_exact",
            "factual_mode_explicit",
            "no_external_manual_adoption",
            "no_logical_mutation_locator",
        ),
    ),
    "DONKEY": _spec(
        "DONKEY",
        "P1",
        requirements=(
            "execution_id_lifecycle_id_primary",
            "logical_id_grouping_only",
            "no_alternative_setup_fallback",
        ),
    ),
    "TRENDPRO": _spec(
        "TRENDPRO",
        "P1",
        requirements=(
            "execution_identity_persists_through_reentry",
            "execution_identity_persists_through_management",
            "new_execution_id_required_for_new_physical_execution",
            "logical_id_not_physical_identity",
        ),
    ),
    "COBRA": _spec(
        "COBRA",
        "P1",
        requirements=(
            "execution_id_lifecycle_id_primary",
            "opposite_sides_are_independent_executions",
            "logical_grouping_never_deduplicates_physical_executions",
        ),
    ),
    "MEME": _spec(
        "MEME",
        "P1",
        requirements=(
            "execution_id_lifecycle_id_primary",
            "close_outcome_tied_to_exact_execution",
            "realized_r_not_inferred_from_mfe",
        ),
    ),
    "MAIN_SYNC": _spec(
        "MAIN_SYNC",
        "P0",
        requirements=(
            "execution_id_lifecycle_id_primary",
            "v2_api_or_reader_only",
            "no_direct_snapshot_writer",
        ),
    ),
    "LIFECYCLE_SHADOW_ADAPTER": _spec(
        "LIFECYCLE_SHADOW_ADAPTER",
        "P1",
        requirements=(
            "execution_id_lifecycle_id_primary",
            "logical_key_compatibility_only",
        ),
    ),
    "REAL_PNL_R_MAPPER": _spec(
        "REAL_PNL_R_MAPPER",
        "P1",
        requirements=(
            "execution_id_first",
            "legacy_archive_lookup_read_only",
            "no_symbol_side_ownership",
        ),
    ),
    "OUTCOME_EVALUATOR": _spec(
        "OUTCOME_EVALUATOR",
        "P2",
        requirements=(
            "paper_outcome_marker_associated_with_execution_id",
            "no_logical_only_ownership",
        ),
    ),
    "REPORTS_DOCTOR": _spec(
        "REPORTS_DOCTOR",
        "P2",
        requirements=(
            "expose_execution_id",
            "expose_logical_trade_id_as_grouping_only",
            "logical_id_not_unique_physical_execution",
        ),
    ),
}

_COMPONENT_ALIASES = {
    "MAIN_PY_SYNC": "MAIN_SYNC",
    "MAIN_SYNC": "MAIN_SYNC",
    "REPORTS_DOCTOR": "REPORTS_DOCTOR",
    "REPORTS": "REPORTS_DOCTOR",
    "DOCTOR": "REPORTS_DOCTOR",
}


def get_registry_v2_bot_contract(component: Any) -> RegistryV2BotContractSpec | None:
    """Return an immutable component contract, or ``None`` if unsupported."""

    normalized = _normalize_component(component)
    return _CONTRACT_SPECS.get(normalized)


def validate_registry_v2_bot_payload(component: Any, payload: Any) -> RegistryV2BotContractResult:
    """Validate supplied V2 identity data without enriching or mutating it."""

    spec = get_registry_v2_bot_contract(component)
    if spec is None:
        return _failure(REGISTRY_V2_BOT_CONTRACT_COMPONENT_UNSUPPORTED, ("component",))
    if not isinstance(payload, Mapping):
        return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("payload",))

    declared_mode = _text(payload.get("execution_mode"))
    verify_description = declared_mode is not None and declared_mode.upper() == schema.VERIFY
    if verify_description and not spec.allows_verify_description:
        return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("execution_mode",))
    execution_id = _text(payload.get("execution_id"))
    lifecycle_id = _text(payload.get("lifecycle_id"))
    if verify_description and (execution_id is not None or lifecycle_id is not None):
        return _failure(REGISTRY_V2_BOT_CONTRACT_VERIFY_NON_EXECUTION, ("execution_id", "lifecycle_id"))
    if spec.requires_execution_id and execution_id is None and not verify_description:
        return _failure(REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED, ("execution_id",))
    if spec.requires_lifecycle_alias and lifecycle_id is None and not verify_description:
        return _failure(REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED, ("lifecycle_id",))
    if execution_id is not None and lifecycle_id is not None and execution_id != lifecycle_id:
        return _failure(REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT, ("execution_id", "lifecycle_id"))
    if not verify_description:
        invalid_identity_fields = tuple(
            field
            for field, value in (
                ("execution_id", execution_id),
                ("lifecycle_id", lifecycle_id),
            )
            if value is not None and not is_v2_execution_id(value)
        )
        if invalid_identity_fields:
            return _failure(REGISTRY_V2_BOT_CONTRACT_ID_INVALID, invalid_identity_fields)

    common = {}
    missing = []
    for field in ("bot", "setup", "symbol", "side", "owner_type", "execution_mode"):
        value = _text(payload.get(field))
        if value is None:
            missing.append(field)
        else:
            common[field] = value
    if missing:
        return _failure(REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING, tuple(missing))

    bot = common["bot"].upper()
    setup = common["setup"].upper()
    symbol = common["symbol"].upper()
    side = common["side"].upper()
    if side not in schema.SIDES:
        return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("side",))
    if spec.component in _BOT_COMPONENTS and bot != spec.component:
        return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("bot", "component"))

    owner_type = common["owner_type"].upper()
    if owner_type != schema.CENTRAL:
        return _failure(REGISTRY_V2_BOT_CONTRACT_OWNER_CONFLICT, ("owner_type",))

    execution_mode = common["execution_mode"].upper()
    if execution_mode not in schema.EXECUTION_MODES:
        return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("execution_mode",))
    if execution_mode == schema.PAPER and not spec.allows_paper:
        return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("execution_mode",))
    if execution_mode == schema.LIVE and not spec.allows_live_contract:
        return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("execution_mode",))

    registry_mode = payload.get("registry_mode")
    if registry_mode is None and spec.requires_registry_mode:
        return _failure(REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING, ("registry_mode",))
    if registry_mode is not None:
        registry_mode = _text(registry_mode)
        if registry_mode is None or registry_mode.upper() not in schema.REGISTRY_MODES:
            return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("registry_mode",))
        registry_mode = registry_mode.upper()
        if execution_mode == schema.VERIFY and registry_mode != schema.VERIFY:
            return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("registry_mode",))
        if execution_mode == schema.PAPER and registry_mode != schema.PAPER:
            return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("registry_mode",))
        if execution_mode == schema.LIVE and registry_mode not in {
            schema.UNKNOWN,
            schema.VERIFY,
            schema.REAL,
            schema.CONFLICT,
        }:
            return _failure(REGISTRY_V2_BOT_CONTRACT_MODE_INVALID, ("registry_mode",))

    position_side = payload.get("position_side")
    if position_side is not None:
        position_side = _text(position_side)
        if position_side is None or position_side.upper() not in schema.POSITION_SIDES:
            return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("position_side",))
        position_side = position_side.upper()
    if spec.requires_position_side and position_side is None:
        return _failure(REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING, ("position_side",))
    if spec.component == "FALCON" and position_side != side:
        return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("position_side",))

    required_ids = []
    signal_id = _text(payload.get("signal_id"))
    decision_id = _text(payload.get("decision_id"))
    if spec.requires_signal_id and signal_id is None:
        required_ids.append("signal_id")
    if spec.requires_decision_id and decision_id is None:
        required_ids.append("decision_id")
    if required_ids:
        return _failure(REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING, tuple(required_ids))

    logical_trade_id = payload.get("logical_trade_id")
    if logical_trade_id is not None:
        logical_trade_id = _text(logical_trade_id)
        expected_logical = f"{bot}:{setup}:{symbol}:{side}"
        if logical_trade_id is None or logical_trade_id.upper() != expected_logical:
            return _failure(REGISTRY_V2_BOT_CONTRACT_LOGICAL_CONFLICT, ("logical_trade_id",))
        logical_trade_id = logical_trade_id.upper()
    elif execution_mode in {schema.PAPER, schema.LIVE}:
        return _failure(REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING, ("logical_trade_id",))

    strong_values = {}
    for field in _STRONG_FIELDS:
        value = payload.get(field)
        if value is None:
            strong_values[field] = None
            continue
        value = _text(value)
        if value is None:
            return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, (field,))
        strong_values[field] = value

    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        return _failure(REGISTRY_V2_BOT_CONTRACT_INVALID, ("metadata",))

    projection = RegistryV2BotIdentityProjection(
        component=spec.component,
        execution_id=execution_id,
        lifecycle_id=lifecycle_id,
        logical_trade_id=logical_trade_id,
        bot=bot,
        setup=setup,
        symbol=symbol,
        side=side,
        position_side=position_side,
        owner_type=owner_type,
        execution_mode=execution_mode,
        registry_mode=registry_mode,
        signal_id=signal_id,
        decision_id=decision_id,
        metadata=tuple((str(key), _freeze(value)) for key, value in sorted(metadata.items(), key=lambda item: str(item[0]))),
        **strong_values,
    )
    status = REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION if verify_description else REGISTRY_V2_BOT_CONTRACT_OK
    return RegistryV2BotContractResult(True, status, projection=projection)


def project_registry_v2_bot_payload(component: Any, payload: Any) -> RegistryV2BotContractResult:
    """Validate and return an immutable projection of supplied payload data."""

    return validate_registry_v2_bot_payload(component, payload)


def _normalize_component(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = "_".join(value.strip().upper().replace("-", "_").replace("/", "_").replace(".", "_").split())
    return _COMPONENT_ALIASES.get(normalized, normalized)


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple((str(key), _freeze(item)) for key, item in sorted(value.items(), key=lambda item: str(item[0])))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def _failure(status: str, errors: tuple[str, ...]) -> RegistryV2BotContractResult:
    return RegistryV2BotContractResult(False, status, errors=errors)


__all__ = (
    "REGISTRY_V2_BOT_CONTRACT_COMPONENT_UNSUPPORTED",
    "REGISTRY_V2_BOT_CONTRACT_ID_INVALID",
    "REGISTRY_V2_BOT_CONTRACT_ID_REQUIRED",
    "REGISTRY_V2_BOT_CONTRACT_INVALID",
    "REGISTRY_V2_BOT_CONTRACT_LIFECYCLE_CONFLICT",
    "REGISTRY_V2_BOT_CONTRACT_LOGICAL_CONFLICT",
    "REGISTRY_V2_BOT_CONTRACT_MODE_INVALID",
    "REGISTRY_V2_BOT_CONTRACT_OK",
    "REGISTRY_V2_BOT_CONTRACT_OWNER_CONFLICT",
    "REGISTRY_V2_BOT_CONTRACT_REQUIRED_FIELD_MISSING",
    "REGISTRY_V2_BOT_CONTRACT_VERIFY_DESCRIPTION",
    "REGISTRY_V2_BOT_CONTRACT_VERIFY_NON_EXECUTION",
    "RegistryV2BotContractResult",
    "RegistryV2BotContractSpec",
    "RegistryV2BotIdentityProjection",
    "get_registry_v2_bot_contract",
    "project_registry_v2_bot_payload",
    "validate_registry_v2_bot_payload",
)
