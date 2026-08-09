"""Pure factual Falcon signal-identity construction for V2.7A.1.

The module receives only the immutable facts present when a productive Falcon
ORB signal is born.  It performs no I/O and has no runtime, broker, Registry,
or persistence dependency.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping


FALCON_SIGNAL_IDENTITY_VERSION = "FALCON-SIGNAL-IDENTITY-V2.7A.1"
FALCON_SIGNAL_ID_PREFIX = "FALCON-SIGNAL-V2_7A_1:"
FALCON_SIGNAL_IDENTITY_ISSUER = "analyze_symbol_setup"
FALCON_SIGNAL_IDENTITY_MECHANISM = "SHA256-CANONICAL-JSON"
FALCON_SIGNAL_BIRTH_BASIS = "FALCON_ORB_CLOSED_CANDLE_BREAKOUT"

_CANONICAL_MATERIAL_FIELDS = (
    "version",
    "strategy",
    "closed_candle",
    "orb_range",
)
_EXTERNAL_OWNER_TYPES = frozenset({"MANUAL_EXTERNAL", "EXTERNAL"})


class FalconSignalIdentityConstructionError(ValueError):
    """Strict factual identity construction failed without affecting V1 signal data."""


def _nonempty(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _required_text(value: Any, name: str, *, uppercase: bool = False) -> str:
    if not _nonempty(value):
        raise FalconSignalIdentityConstructionError(
            f"{name} is required for factual signal identity"
        )
    text = str(value).strip()
    return text.upper() if uppercase else text


def _integer_text(value: Any, name: str) -> str:
    if isinstance(value, bool):
        raise FalconSignalIdentityConstructionError(
            f"{name} must be an integer factual value"
        )
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise FalconSignalIdentityConstructionError(
            f"{name} must be an integer factual value"
        ) from exc
    if str(value).strip() not in {str(integer), f"+{integer}"}:
        raise FalconSignalIdentityConstructionError(
            f"{name} must be an integer factual value"
        )
    return str(integer)


def _number_text(value: Any, name: str) -> str:
    if isinstance(value, bool) or value is None:
        raise FalconSignalIdentityConstructionError(
            f"{name} must be a finite factual number"
        )
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FalconSignalIdentityConstructionError(
            f"{name} must be a finite factual number"
        ) from exc
    if not number.is_finite():
        raise FalconSignalIdentityConstructionError(
            f"{name} must be a finite factual number"
        )
    normalized = number.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _selected_position_side(signal: Mapping[str, Any]) -> tuple[Any, str]:
    for key in ("positionSide", "position_side", "side"):
        value = signal.get(key)
        if _nonempty(value):
            return value, key
    return None, ""


def _position_side_provenance(signal: Mapping[str, Any]) -> dict[str, Any]:
    raw_position_side_camel = signal.get("positionSide")
    raw_position_side_snake = signal.get("position_side")
    selected_value, selected_source = _selected_position_side(signal)
    explicit_conflict = bool(
        _nonempty(raw_position_side_camel)
        and _nonempty(raw_position_side_snake)
        and str(raw_position_side_camel).strip().upper()
        != str(raw_position_side_snake).strip().upper()
    )
    return {
        "selected_value": selected_value,
        "selected_source": selected_source or None,
        "raw_positionSide": raw_position_side_camel,
        "raw_position_side": raw_position_side_snake,
        "raw_side": signal.get("side"),
        "explicit_position_side_conflict": explicit_conflict,
    }


def _plan_provenance(signal: Mapping[str, Any]) -> dict[str, Any]:
    explicit_owner = signal.get("owner_type")
    owner_text = str(explicit_owner).strip().upper() if _nonempty(explicit_owner) else ""
    if owner_text in _EXTERNAL_OWNER_TYPES:
        return {
            "plan_origin": "EXTERNAL_OWNER_EVIDENCE_PRESERVED",
            "plan_owner_type": None,
            "ownership_scope": "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP",
            "explicit_owner_type_preserved": explicit_owner,
        }
    return {
        "plan_origin": "CENTRAL_FALCON_PRODUCTIVE_SIGNAL",
        "plan_owner_type": "CENTRAL",
        "ownership_scope": "PLAN_ONLY_NOT_BROKER_POSITION_OWNERSHIP",
        "explicit_owner_type_preserved": explicit_owner,
    }


def canonical_falcon_signal_identity_material(
    signal: Mapping[str, Any], *, birth_facts: Mapping[str, Any]
) -> dict[str, Any]:
    """Return only immutable factual material for one Falcon signal birth."""

    if not isinstance(signal, Mapping):
        raise FalconSignalIdentityConstructionError("signal must be a mapping")
    if not isinstance(birth_facts, Mapping):
        raise FalconSignalIdentityConstructionError("birth_facts must be a mapping")

    return {
        "version": FALCON_SIGNAL_IDENTITY_VERSION,
        "strategy": {
            "bot": "FALCON",
            "setup": _required_text(signal.get("setup"), "setup", uppercase=True),
            "symbol": _required_text(signal.get("symbol"), "symbol", uppercase=True),
            "side": _required_text(signal.get("side"), "side", uppercase=True),
            "timeframe": _required_text(signal.get("timeframe"), "timeframe"),
            "ny_date": _required_text(signal.get("ny_date"), "ny_date"),
        },
        "closed_candle": {
            "ts": _integer_text(birth_facts.get("closed_candle_ts"), "closed_candle_ts"),
            "high": _number_text(birth_facts.get("closed_candle_high"), "closed_candle_high"),
            "low": _number_text(birth_facts.get("closed_candle_low"), "closed_candle_low"),
            "close": _number_text(birth_facts.get("closed_candle_close"), "closed_candle_close"),
        },
        "orb_range": {
            "high": _number_text(birth_facts.get("orb_range_high"), "orb_range_high"),
            "low": _number_text(birth_facts.get("orb_range_low"), "orb_range_low"),
            "minutes": _integer_text(birth_facts.get("orb_range_minutes"), "orb_range_minutes"),
            "start_ny": _required_text(birth_facts.get("orb_range_start_ny"), "orb_range_start_ny"),
            "end_ny": _required_text(birth_facts.get("orb_range_end_ny"), "orb_range_end_ny"),
        },
    }


def build_falcon_signal_identity(
    signal: Mapping[str, Any], *, birth_facts: Mapping[str, Any]
) -> dict[str, Any]:
    """Build the additive V2.7A.1 fields for a factual signal birth."""

    material = canonical_falcon_signal_identity_material(
        signal, birth_facts=birth_facts
    )
    canonical_json = json.dumps(
        material, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest().upper()
    position_side = _position_side_provenance(signal)

    return {
        "signal_id": FALCON_SIGNAL_ID_PREFIX + digest,
        "signal_identity_version": FALCON_SIGNAL_IDENTITY_VERSION,
        "signal_identity_provenance": {
            "issuer_function": FALCON_SIGNAL_IDENTITY_ISSUER,
            "mechanism": FALCON_SIGNAL_IDENTITY_MECHANISM,
            "identity_version": FALCON_SIGNAL_IDENTITY_VERSION,
            "canonical_material_sha256": digest,
            "canonical_material_fields": list(_CANONICAL_MATERIAL_FIELDS),
            "factual_signal_birth_basis": FALCON_SIGNAL_BIRTH_BASIS,
            "legacy_signal_id_equivalence": "NOT_ASSUMED",
            "position_side": position_side,
            "plan_provenance": _plan_provenance(signal),
        },
    }


def attach_falcon_signal_identity(
    signal: Mapping[str, Any], *, birth_facts: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach the canonical signal identity without changing V1 fields."""

    result = dict(signal)
    additive = build_falcon_signal_identity(result, birth_facts=birth_facts)
    existing_signal_id = result.get("signal_id")
    if _nonempty(existing_signal_id) and str(existing_signal_id) != additive["signal_id"]:
        raise FalconSignalIdentityConstructionError(
            "preexisting signal_id conflicts with factual birth material"
        )
    result.update(additive)
    return result


__all__ = [
    "FALCON_SIGNAL_BIRTH_BASIS",
    "FalconSignalIdentityConstructionError",
    "FALCON_SIGNAL_IDENTITY_ISSUER",
    "FALCON_SIGNAL_IDENTITY_MECHANISM",
    "FALCON_SIGNAL_IDENTITY_VERSION",
    "FALCON_SIGNAL_ID_PREFIX",
    "attach_falcon_signal_identity",
    "build_falcon_signal_identity",
    "canonical_falcon_signal_identity_material",
]
