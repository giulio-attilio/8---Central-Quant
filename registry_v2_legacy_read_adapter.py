"""Dormant, read-only compatibility projections for Registry V2.

Legacy logical identity is treated only as a selector for a deterministic
read resolution.  The adapter never returns a mutation key and never writes
the supplied document or an explicitly supplied snapshot path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from typing import Any

import registry_execution_schema as schema
import registry_v2_reader as reader


REGISTRY_LEGACY_UNIQUE = "REGISTRY_LEGACY_UNIQUE"
REGISTRY_LEGACY_NOT_FOUND = "REGISTRY_LEGACY_NOT_FOUND"
REGISTRY_LEGACY_AMBIGUOUS = "REGISTRY_LEGACY_AMBIGUOUS"
REGISTRY_LEGACY_EXTERNAL_ONLY = "REGISTRY_LEGACY_EXTERNAL_ONLY"
REGISTRY_LEGACY_INVALID = "REGISTRY_LEGACY_INVALID"
REGISTRY_LEGACY_CONFLICT = "REGISTRY_LEGACY_CONFLICT"

_STRONG_FIELDS = ("client_order_id", "broker_order_id", "exchange_order_id", "fill_id")
_COMPONENT_FIELDS = ("bot", "setup", "symbol", "side")
_CLOSE_EVENT_INDEX = "by_close_event_id"
_COLLECTION_ORDER = {"open_trades": 0, "closed_trades": 1}
_V25_TEMPORARY_PHASE = "V2_CORE_TEMPORARY"


@dataclass(frozen=True)
class StrongIdentityFact:
    """One factual strong-ID observation with its role and source."""

    field: str
    value: str
    role: str
    source: str


@dataclass(frozen=True)
class _CloseEventFact:
    close_event_id: str
    digest: str | None = None


@dataclass(frozen=True)
class _IndexOwner:
    execution_id: str
    role: str | None = None
    legacy_string: bool = False


@dataclass(frozen=True)
class LegacyCandidate:
    execution_id: str
    lifecycle_id: str
    logical_trade_id: str
    bot: str
    setup: str
    symbol: str
    side: str
    lifecycle_state: str
    collection: str
    strong_ids: tuple[tuple[str, str], ...] = ()
    close_event_ids: tuple[str, ...] = ()
    strong_facts: tuple[StrongIdentityFact, ...] = ()
    close_event_facts: tuple[_CloseEventFact, ...] = ()


@dataclass(frozen=True)
class LegacyExternalMatch:
    observation_id: str
    logical_trade_id: str | None = None
    bot: str | None = None
    setup: str | None = None
    symbol: str | None = None
    side: str | None = None


@dataclass(frozen=True)
class LegacyResolutionResult:
    ok: bool
    status: str
    execution_id: str | None = None
    lifecycle_id: str | None = None
    logical_trade_id: str | None = None
    collection: str | None = None
    candidates: tuple[LegacyCandidate, ...] = ()
    external_matches: tuple[LegacyExternalMatch, ...] = ()
    errors: tuple[str, ...] = ()


class _AdapterError(ValueError):
    def __init__(self, status: str, errors: tuple[str, ...]):
        super().__init__(";".join(errors))
        self.status = status
        self.errors = errors


def resolve_legacy_trade_v2(
    registry_document: Any,
    *,
    trade_id: str | None = None,
    logical_trade_id: str | None = None,
    execution_id: str | None = None,
    lifecycle_id: str | None = None,
    client_order_id: str | None = None,
    broker_order_id: str | None = None,
    exchange_order_id: str | None = None,
    fill_id: str | None = None,
    close_event_id: str | None = None,
    bot: str | None = None,
    setup: str | None = None,
    symbol: str | None = None,
    side: str | None = None,
    include_closed: bool = True,
) -> LegacyResolutionResult:
    """Resolve one legacy reference against explicitly supplied V2 data.

    A unique result is a read-only projection.  Logical, component and
    strong-ID selectors are never usable as a mutation selector by this
    module.
    """

    try:
        document = _coerce_document(registry_document)
        selectors = _prepare_selectors(
            trade_id=trade_id,
            logical_trade_id=logical_trade_id,
            execution_id=execution_id,
            lifecycle_id=lifecycle_id,
            client_order_id=client_order_id,
            broker_order_id=broker_order_id,
            exchange_order_id=exchange_order_id,
            fill_id=fill_id,
            close_event_id=close_event_id,
            bot=bot,
            setup=setup,
            symbol=symbol,
            side=side,
            include_closed=include_closed,
        )
        all_candidates = _canonical_candidates(document, include_closed=True)
        candidates = (
            all_candidates
            if include_closed
            else tuple(candidate for candidate in all_candidates if candidate.collection == "open_trades")
        )
        external_matches = _external_matches(document, selectors)
        selected = _select_candidates(
            document,
            candidates,
            selectors,
            verification_candidates=all_candidates,
        )
    except _AdapterError as error:
        return LegacyResolutionResult(False, error.status, errors=error.errors)

    if selected is None:
        return LegacyResolutionResult(
            False,
            REGISTRY_LEGACY_CONFLICT,
            candidates=(),
            external_matches=external_matches,
            errors=("selector_conflict",),
        )
    selected = tuple(selected)
    if len(selected) == 1:
        candidate = selected[0]
        return LegacyResolutionResult(
            True,
            REGISTRY_LEGACY_UNIQUE,
            execution_id=candidate.execution_id,
            lifecycle_id=candidate.lifecycle_id,
            logical_trade_id=candidate.logical_trade_id,
            collection=candidate.collection,
            candidates=selected,
            external_matches=external_matches,
        )
    if len(selected) > 1:
        return LegacyResolutionResult(
            False,
            REGISTRY_LEGACY_AMBIGUOUS,
            candidates=selected,
            external_matches=external_matches,
            errors=("multiple_central_candidates",),
        )
    if external_matches:
        return LegacyResolutionResult(
            False,
            REGISTRY_LEGACY_EXTERNAL_ONLY,
            external_matches=external_matches,
            errors=("external_observation_only",),
        )
    return LegacyResolutionResult(
        False,
        REGISTRY_LEGACY_NOT_FOUND,
        external_matches=(),
        errors=("no_central_candidate",),
    )


def resolve_strong_id_v2(
    registry_document: Any,
    field: str,
    value: str,
    *,
    include_closed: bool = True,
) -> LegacyResolutionResult:
    """Resolve one canonical strong ID through the same read-only contract."""

    if field not in _STRONG_FIELDS and field != "close_event_id":
        return LegacyResolutionResult(False, REGISTRY_LEGACY_INVALID, errors=("strong_id_field_invalid",))
    kwargs = {field: value}
    return resolve_legacy_trade_v2(registry_document, include_closed=include_closed, **kwargs)


def _coerce_document(source: Any) -> Mapping[str, Any]:
    if isinstance(source, reader.RegistryV2ReadResult):
        if not source.ok or source.document is None:
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"reader:{source.status}", *source.errors))
        document = source.document
    elif isinstance(source, Mapping):
        document = source
    elif isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        result = reader.read_registry_v2(source)
        if not result.ok or result.document is None:
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"reader:{result.status}", *result.errors))
        document = result.document
    else:
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("registry_document_required",))
    if not isinstance(document, Mapping):
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("registry_document_mapping_required",))
    for field in ("open_trades", "closed_trades", "external_observations"):
        if not isinstance(document.get(field), Mapping):
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{field}:mapping_required",))
    return document


def _prepare_selectors(**values: Any) -> dict[str, Any]:
    include_closed = values.pop("include_closed")
    if not isinstance(include_closed, bool):
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("include_closed_invalid",))

    selectors: dict[str, Any] = {"include_closed": include_closed}
    for field in ("execution_id", "lifecycle_id"):
        value = values.pop(field)
        selectors[field] = _selector_string(value, field) if value is not None else None
    for field in ("trade_id", "logical_trade_id"):
        value = values.pop(field)
        selectors[field] = _selector_string(value, field, upper=True) if value is not None else None
    for field in _COMPONENT_FIELDS:
        value = values.pop(field)
        selectors[field] = _selector_string(value, field, upper=True) if value is not None else None
    for field in (*_STRONG_FIELDS, "close_event_id"):
        value = values.pop(field)
        selectors[field] = _selector_string(value, field) if value is not None else None

    if selectors["execution_id"] is not None and selectors["lifecycle_id"] is not None:
        if selectors["execution_id"] != selectors["lifecycle_id"]:
            raise _AdapterError(REGISTRY_LEGACY_CONFLICT, ("execution_id_lifecycle_id_mismatch",))
    if selectors["trade_id"] is not None and selectors["logical_trade_id"] is not None:
        if selectors["trade_id"] != selectors["logical_trade_id"]:
            raise _AdapterError(REGISTRY_LEGACY_CONFLICT, ("trade_id_logical_trade_id_conflict",))
    if selectors["logical_trade_id"] is None:
        selectors["logical_trade_id"] = selectors["trade_id"]
    component_count = sum(selectors[field] is not None for field in _COMPONENT_FIELDS)
    if component_count and component_count != len(_COMPONENT_FIELDS) and selectors["logical_trade_id"] is None:
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("incomplete_component_selector",))
    if selectors["side"] is not None and selectors["side"] not in schema.SIDES:
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("side_invalid",))
    if not any(
        selectors[field] is not None
        for field in ("execution_id", "lifecycle_id", "logical_trade_id", *_COMPONENT_FIELDS, *_STRONG_FIELDS, "close_event_id")
    ):
        raise _AdapterError(REGISTRY_LEGACY_INVALID, ("selector_required",))
    return selectors


def _selector_string(value: Any, field: str, *, upper: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{field}_invalid",))
    value = value.strip()
    return value.upper() if upper else value


def _canonical_candidates(document: Mapping[str, Any], *, include_closed: bool) -> tuple[LegacyCandidate, ...]:
    candidates: list[LegacyCandidate] = []
    collections = [("open_trades", document["open_trades"])]
    if include_closed:
        collections.append(("closed_trades", document["closed_trades"]))
    for collection, rows in collections:
        for key, row in rows.items():
            if not isinstance(row, Mapping):
                raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:mapping_required",))
            if row.get("owner_type") != schema.CENTRAL:
                continue
            candidates.append(_candidate_from_row(collection, key, row))
    return tuple(sorted(candidates, key=lambda item: (_COLLECTION_ORDER[item.collection], item.execution_id)))


def _candidate_from_row(collection: str, key: Any, row: Mapping[str, Any]) -> LegacyCandidate:
    fields = ("execution_id", "lifecycle_id", "logical_trade_id", "bot", "setup", "symbol", "side", "lifecycle_state")
    values: dict[str, str] = {}
    for field in fields:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:{field}_invalid",))
        values[field] = value.strip()
    if values["execution_id"] != str(key) or values["execution_id"] != values["lifecycle_id"]:
        raise _AdapterError(REGISTRY_LEGACY_CONFLICT, (f"{collection}:{key}:execution_identity_conflict",))
    if values["side"].upper() not in schema.SIDES:
        raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:side_invalid",))

    strong_facts = _extract_strong_identity_facts(collection, key, row)

    close_event_facts: list[_CloseEventFact] = []
    close_events = row.get("close_events", [])
    if close_events is not None and not isinstance(close_events, list):
        raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:close_events_invalid",))
    if close_events is None:
        close_events = []
    for close_event in close_events:
        if not isinstance(close_event, Mapping):
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:close_event_invalid",))
        close_id = close_event.get("close_event_id")
        if not isinstance(close_id, str) or not close_id.strip():
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:close_event_id_invalid",))
        close_event_facts.append(
            _CloseEventFact(close_id.strip(), _close_event_digest(collection, key, close_event))
        )
    close_event_by_id: dict[str, _CloseEventFact] = {}
    for fact in close_event_facts:
        previous = close_event_by_id.get(fact.close_event_id)
        if previous is not None and previous.digest != fact.digest:
            raise _AdapterError(REGISTRY_LEGACY_CONFLICT, (f"{collection}:{key}:close_event_digest_conflict",))
        close_event_by_id[fact.close_event_id] = fact
    close_event_facts = [close_event_by_id[event_id] for event_id in sorted(close_event_by_id)]
    strong_ids = sorted({(fact.field, fact.value) for fact in strong_facts})
    return LegacyCandidate(
        execution_id=values["execution_id"],
        lifecycle_id=values["lifecycle_id"],
        logical_trade_id=values["logical_trade_id"],
        bot=values["bot"],
        setup=values["setup"],
        symbol=values["symbol"],
        side=values["side"],
        lifecycle_state=values["lifecycle_state"],
        collection=collection,
        strong_ids=tuple(strong_ids),
        close_event_ids=tuple(fact.close_event_id for fact in close_event_facts),
        strong_facts=tuple(strong_facts),
        close_event_facts=tuple(close_event_facts),
    )


def _extract_strong_identity_facts(
    collection: str,
    key: Any,
    row: Mapping[str, Any],
) -> tuple[StrongIdentityFact, ...]:
    facts: list[StrongIdentityFact] = []
    for field in _STRONG_FIELDS:
        _append_identity_values(
            facts,
            collection,
            key,
            field,
            row.get(field),
            "TOP_LEVEL",
            "top_level",
        )

    entry_order = row.get("entry_order")
    if entry_order is not None:
        if not isinstance(entry_order, Mapping):
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:entry_order_invalid",))
        role = _nested_role(collection, key, entry_order, "ENTRY")
        for field in ("client_order_id", "broker_order_id", "exchange_order_id"):
            _append_identity_values(
                facts,
                collection,
                key,
                field,
                entry_order.get(field),
                role,
                "entry_order",
            )

    orders = row.get("orders")
    if orders is not None:
        if not isinstance(orders, Mapping):
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:orders_invalid",))
        for order_name in sorted(orders, key=lambda item: str(item)):
            order = orders[order_name]
            if order is None:
                continue
            if not isinstance(order_name, str) or not isinstance(order, Mapping):
                if str(order_name).lower() in {"stop", "tp", "close"}:
                    raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:order_invalid",))
                continue
            role = _nested_role(collection, key, order, order_name.upper())
            source = f"orders.{order_name}"
            for field in ("client_order_id", "broker_order_id", "exchange_order_id"):
                _append_identity_values(
                    facts,
                    collection,
                    key,
                    field,
                    order.get(field),
                    role,
                    source,
                )

    fills = row.get("fills")
    if fills is not None:
        if not isinstance(fills, (list, tuple)):
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:fills_invalid",))
        for position, fill in enumerate(fills):
            if not isinstance(fill, Mapping):
                raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:fill_invalid",))
            role = _nested_role(collection, key, fill, "FILL")
            _append_identity_values(
                facts,
                collection,
                key,
                "fill_id",
                fill.get("fill_id"),
                role,
                f"fills[{position}]",
            )

    deduplicated: dict[tuple[str, str, str], StrongIdentityFact] = {}
    for fact in facts:
        identity = (fact.field, fact.value, fact.role)
        previous = deduplicated.get(identity)
        if previous is None or fact.source < previous.source:
            deduplicated[identity] = fact
    return tuple(
        sorted(
            deduplicated.values(),
            key=lambda fact: (fact.field, fact.value, fact.role, fact.source),
        )
    )


def _append_identity_values(
    facts: list[StrongIdentityFact],
    collection: str,
    key: Any,
    field: str,
    value: Any,
    role: str,
    source: str,
) -> None:
    if value is None:
        return
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(sorted(value, key=lambda item: str(item)))
    else:
        raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:{field}_invalid",))
    for item in values:
        if not isinstance(item, str) or not item.strip():
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:{field}_invalid",))
        facts.append(StrongIdentityFact(field, item.strip(), role, source))


def _nested_role(collection: str, key: Any, value: Mapping[str, Any], default: str) -> str:
    role = value.get("role", default)
    if role is None:
        role = default
    if not isinstance(role, str) or not role.strip():
        raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:role_invalid",))
    return role.strip().upper()


def _close_event_digest(collection: str, key: Any, close_event: Mapping[str, Any]) -> str | None:
    for field in ("close_event_digest", "evidence_digest", "digest"):
        if field not in close_event:
            continue
        digest = close_event[field]
        if not isinstance(digest, str) or not digest.strip():
            raise _AdapterError(REGISTRY_LEGACY_INVALID, (f"{collection}:{key}:{field}_invalid",))
        return digest.strip()
    if len(close_event) <= 1:
        return None
    try:
        return _sha256(close_event)
    except (TypeError, ValueError):
        return None


def _sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_v25_temp_projection(document: Mapping[str, Any]) -> bool:
    """Return True only for the factual V2.5 temporary snapshot marker."""

    migration = document.get("migration")
    if not isinstance(migration, Mapping):
        return False
    phase = migration.get("phase")
    return isinstance(phase, str) and phase.strip().upper() == _V25_TEMPORARY_PHASE


def _select_candidates(
    document: Mapping[str, Any],
    candidates: tuple[LegacyCandidate, ...],
    selectors: Mapping[str, Any],
    *,
    verification_candidates: tuple[LegacyCandidate, ...] | None = None,
) -> tuple[LegacyCandidate, ...] | None:
    verification_candidates = candidates if verification_candidates is None else verification_candidates
    physical = selectors.get("execution_id") or selectors.get("lifecycle_id")
    factually_selected = verification_candidates
    selected = candidates
    if physical is not None:
        factually_selected = tuple(
            candidate for candidate in factually_selected if candidate.execution_id == physical
        )
        selected = tuple(candidate for candidate in selected if candidate.execution_id == physical)

    strong_fields = [field for field in _STRONG_FIELDS if selectors.get(field) is not None]
    if selectors.get("close_event_id") is not None:
        strong_fields.append("close_event_id")
    for field in strong_fields:
        matches, stale = _strong_matches(
            document,
            verification_candidates,
            field,
            selectors[field],
        )
        if stale:
            raise _AdapterError(REGISTRY_LEGACY_CONFLICT, (stale,))
        if not matches:
            if physical is not None:
                return None if factually_selected else ()
            factually_selected = ()
            selected = ()
            continue
        if factually_selected and not set(factually_selected).intersection(matches):
            return None
        factually_selected = tuple(candidate for candidate in factually_selected if candidate in matches)
        selected = tuple(candidate for candidate in selected if candidate in matches)

    for field in ("logical_trade_id", *_COMPONENT_FIELDS):
        value = selectors.get(field)
        if value is None:
            continue
        matching_factual = tuple(
            candidate for candidate in factually_selected if _candidate_matches(candidate, field, value)
        )
        if factually_selected and not matching_factual:
            return None
        factually_selected = matching_factual
        selected = tuple(candidate for candidate in selected if candidate in matching_factual)
    return selected


def _candidate_matches(candidate: LegacyCandidate, field: str, value: str) -> bool:
    actual = getattr(candidate, field)
    return actual.upper() == value.upper()


def _candidate_has_strong(candidate: LegacyCandidate, field: str, value: str) -> bool:
    if field == "close_event_id":
        return value in candidate.close_event_ids
    return any(fact.field == field and fact.value == value for fact in candidate.strong_facts)


def _candidate_has_role_fact(
    candidate: LegacyCandidate,
    field: str,
    value: str,
    role: str,
) -> bool:
    return any(
        fact.field == field
        and fact.value == value
        and fact.role == role
        for fact in candidate.strong_facts
    )


def _strong_matches(
    document: Mapping[str, Any],
    candidates: tuple[LegacyCandidate, ...],
    field: str,
    value: str,
) -> tuple[tuple[LegacyCandidate, ...], str | None]:
    matches = tuple(candidate for candidate in candidates if _candidate_has_strong(candidate, field, value))
    indexes, index_error = _relevant_indexes_for_field(document, field)
    if index_error:
        return (), index_error
    if field == "close_event_id":
        if not indexes:
            return matches, None
        return _close_event_index_matches(
            indexes[0][1],
            matches,
            value,
            allow_temp_legacy=_is_v25_temp_projection(document),
        )
    if not indexes:
        return matches, None

    indexed_groups: list[tuple[str, tuple[_IndexOwner, ...]]] = []
    allow_temp_legacy = _is_v25_temp_projection(document)
    for index_name, index in indexes:
        if value not in index:
            continue
        try:
            owners = _parse_index_owners(index[value], allow_legacy_string=allow_temp_legacy)
        except ValueError:
            return (), f"{field}_index_value_invalid"
        if not _index_owners_match_candidates(owners, matches, field, value):
            return (), f"{field}_index_stale"
        indexed_groups.append((index_name, owners))

    if not indexed_groups:
        if matches:
            return (), f"{field}_index_stale"
        return matches, None
    if not _index_owner_groups_coherent(indexed_groups):
        return (), f"{field}_index_stale"
    return matches, None


def _relevant_indexes_for_field(
    document: Mapping[str, Any],
    field: str,
) -> tuple[tuple[tuple[str, Mapping[str, Any]], ...], str | None]:
    if "indexes" not in document:
        return (), None
    indexes = document.get("indexes")
    if not isinstance(indexes, Mapping):
        return (), f"{field}_index_invalid"
    if field == "close_event_id":
        names = (_CLOSE_EVENT_INDEX,)
    elif field == "exchange_order_id":
        names = ("by_exchange_order_id", "by_broker_order_id")
    else:
        names = (_index_name(field),)
    relevant: list[tuple[str, Mapping[str, Any]]] = []
    for name in names:
        if name not in indexes:
            continue
        index = indexes[name]
        if not isinstance(index, Mapping):
            return (), f"{field}_index_invalid"
        relevant.append((name, index))
    return tuple(relevant), None


def _index_owners_match_candidates(
    owners: tuple[_IndexOwner, ...],
    matches: tuple[LegacyCandidate, ...],
    field: str,
    value: str,
) -> bool:
    actual_ids = {candidate.execution_id for candidate in matches}
    indexed_ids = {owner.execution_id for owner in owners}
    if not owners or indexed_ids != actual_ids:
        return False
    for owner in owners:
        owner_candidates = tuple(
            candidate for candidate in matches if candidate.execution_id == owner.execution_id
        )
        if owner.role is None:
            if not any(_candidate_has_strong(candidate, field, value) for candidate in owner_candidates):
                return False
        elif not any(
            _candidate_has_role_fact(candidate, field, value, owner.role)
            for candidate in owner_candidates
        ):
            return False
    for execution_id in indexed_ids:
        execution_owners = tuple(owner for owner in owners if owner.execution_id == execution_id)
        structured_roles = {owner.role for owner in execution_owners if owner.role is not None}
        if not structured_roles:
            # TEMP V2.5 bare strings have no role metadata and cannot prove
            # completeness; execution ownership was already verified above.
            continue
        factual_roles = {
            fact.role
            for candidate in matches
            if candidate.execution_id == execution_id
            for fact in candidate.strong_facts
            if fact.field == field and fact.value == value
        }
        if structured_roles != factual_roles:
            return False
    return True


def _index_owner_groups_coherent(
    indexed_groups: list[tuple[str, tuple[_IndexOwner, ...]]],
) -> bool:
    if len(indexed_groups) < 2:
        return True
    first_owners = indexed_groups[0][1]
    first_ids = {owner.execution_id for owner in first_owners}
    first_roles = {owner.role for owner in first_owners if owner.role is not None}
    for _, owners in indexed_groups[1:]:
        if {owner.execution_id for owner in owners} != first_ids:
            return False
        roles = {owner.role for owner in owners if owner.role is not None}
        if first_roles and roles and roles != first_roles:
            return False
    return True


def _parse_index_owners(value: Any, *, allow_legacy_string: bool) -> tuple[_IndexOwner, ...]:
    """Parse canonical execution/role owners plus the TEMP V2.5 string fallback.

    A bare string is accepted only for the dormant V2.5 projection, where the
    index value was still an execution ID without role metadata.  Structured
    values must carry an explicit execution ID and role.
    """

    if isinstance(value, str):
        if not allow_legacy_string:
            raise ValueError("legacy_index_value_not_allowed")
        if not value.strip():
            raise ValueError("empty_legacy_index_value")
        return (_IndexOwner(value.strip(), legacy_string=True),)
    if isinstance(value, Mapping):
        execution_id = value.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id_required")
        if "role" in value and "roles" in value:
            raise ValueError("role_ambiguous")
        if "roles" in value:
            roles = value["roles"]
            if not isinstance(roles, (list, tuple, set, frozenset)) or not roles:
                raise ValueError("roles_invalid")
            owners = []
            for role in roles:
                owners.append(_IndexOwner(execution_id.strip(), _parse_index_role(role)))
            return tuple(sorted(set(owners), key=lambda owner: (owner.execution_id, owner.role or "")))
        if "role" not in value:
            raise ValueError("role_required")
        return (_IndexOwner(execution_id.strip(), _parse_index_role(value["role"])),)
    if isinstance(value, (list, tuple)):
        owners: list[_IndexOwner] = []
        for item in value:
            owners.extend(_parse_index_owners(item, allow_legacy_string=allow_legacy_string))
        return tuple(sorted(set(owners), key=lambda owner: (owner.execution_id, owner.role or "")))
    raise ValueError("index_value_uninterpretable")


def _parse_index_role(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("role_invalid")
    return value.strip().upper()


def _close_event_index_matches(
    index: Mapping[str, Any],
    matches: tuple[LegacyCandidate, ...],
    close_event_id: str,
    *,
    allow_temp_legacy: bool,
) -> tuple[tuple[LegacyCandidate, ...], str | None]:
    matching_keys = {f"{candidate.execution_id}|{close_event_id}" for candidate in matches}
    relevant_keys = {
        key
        for key in index
        if isinstance(key, str) and key.partition("|")[2] == close_event_id
    }
    if not matches:
        if relevant_keys:
            return (), "close_event_id_index_stale"
        return matches, None
    if relevant_keys != matching_keys:
        return (), "close_event_id_index_stale"
    for candidate in matches:
        key = f"{candidate.execution_id}|{close_event_id}"
        digest = index[key]
        if not isinstance(digest, str) or not digest.strip():
            return (), "close_event_id_index_value_invalid"
        digest = digest.strip()
        expected = _candidate_close_digest(candidate, close_event_id)
        if not allow_temp_legacy and digest == candidate.execution_id:
            return (), "close_event_id_index_stale"
        if allow_temp_legacy and digest == candidate.execution_id:
            continue
        if expected is not None and digest == expected:
            continue
        return (), "close_event_id_index_stale"
    return matches, None


def _candidate_close_digest(candidate: LegacyCandidate, close_event_id: str) -> str | None:
    for fact in candidate.close_event_facts:
        if fact.close_event_id == close_event_id:
            return fact.digest
    return None


def _index_name(field: str) -> str:
    if field == "close_event_id":
        return _CLOSE_EVENT_INDEX
    return f"by_{field}"


def _external_matches(document: Mapping[str, Any], selectors: Mapping[str, Any]) -> tuple[LegacyExternalMatch, ...]:
    observations = document["external_observations"]
    matches: list[LegacyExternalMatch] = []
    for key in sorted(observations, key=lambda item: str(item)):
        observation = observations[key]
        if not isinstance(observation, Mapping):
            continue
        if not _external_matches_selectors(str(key), observation, selectors):
            continue
        logical = observation.get("logical_trade_id", observation.get("trade_id"))
        matches.append(
            LegacyExternalMatch(
                observation_id=str(key),
                logical_trade_id=logical.strip() if isinstance(logical, str) and logical.strip() else None,
                bot=_optional_text(observation.get("bot")),
                setup=_optional_text(observation.get("setup")),
                symbol=_optional_text(observation.get("symbol")),
                side=_optional_text(observation.get("side")),
            )
        )
    return tuple(matches)


def _external_matches_selectors(
    key: str,
    observation: Mapping[str, Any],
    selectors: Mapping[str, Any],
) -> bool:
    logical = observation.get("logical_trade_id", observation.get("trade_id", key))
    for field in ("logical_trade_id", *_COMPONENT_FIELDS):
        value = selectors.get(field)
        if value is None:
            continue
        actual = logical if field == "logical_trade_id" else observation.get(field)
        if not isinstance(actual, str) or actual.strip().upper() != value.upper():
            return False
    physical = selectors.get("execution_id") or selectors.get("lifecycle_id")
    if physical is not None and observation.get("execution_id") != physical:
        return False
    for field in _STRONG_FIELDS:
        value = selectors.get(field)
        if value is not None and observation.get(field) != value:
            return False
    close_event = selectors.get("close_event_id")
    if close_event is not None and observation.get("close_event_id") != close_event:
        return False
    return True


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


__all__ = (
    "LegacyCandidate",
    "LegacyExternalMatch",
    "LegacyResolutionResult",
    "StrongIdentityFact",
    "REGISTRY_LEGACY_AMBIGUOUS",
    "REGISTRY_LEGACY_CONFLICT",
    "REGISTRY_LEGACY_EXTERNAL_ONLY",
    "REGISTRY_LEGACY_INVALID",
    "REGISTRY_LEGACY_NOT_FOUND",
    "REGISTRY_LEGACY_UNIQUE",
    "resolve_legacy_trade_v2",
    "resolve_strong_id_v2",
)
