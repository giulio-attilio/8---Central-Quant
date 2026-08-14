"""Pure identity taxonomy for the Trade Evidence Offset Index V1.

The journal index is an observational accelerator.  This module intentionally
contains no file, database, environment, network, or application imports.  Its
extraction rules mirror the identity helpers in ``trade_timeline_validator``
while exposing a deterministic contract fingerprint for persisted indexes.

Legacy client order IDs ending in ``-DS`` remain visible in
``extract_identity_pairs`` because the Validator can use them as supporting
evidence for one narrowly-scoped historical broker relation.  They are never
returned by ``extract_typed_identities`` and therefore cannot become an
independent STRONG or SECONDARY posting.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional


IDENTITY_CONTRACT_VERSION = 1

IDENTITY_CLASS_STRONG = "STRONG"
IDENTITY_CLASS_SECONDARY = "SECONDARY"

# Keep these keys, aliases, and groups aligned with the pure identity helpers
# in trade_timeline_validator.py.  Values remain case-sensitive; only field
# names are lower-cased and stripped.
IDENTITY_KEYS = frozenset(
    {
        "trade_id",
        "trade_uuid",
        "registry_record_id",
        "lifecycle_id",
        "registry_id",
        "execution_id",
        "decision_id",
        "signal_id",
        "client_order_id",
        "clientorderid",
        "exchange_order_id",
        "broker_order_id",
        "broker_stop_order_id",
        "disaster_stop_order_id",
        "order_id",
        "fill_id",
        "fill_ids",
    }
)

IDENTITY_KEY_ALIASES = {
    "clientorderid": "client_order_id",
    "registry_record_id": "registry_id",
    "tradelifecycleid": "lifecycle_id",
    "trade_lifecycle_id": "lifecycle_id",
    "position_uuid": "trade_uuid",
    "broker_stop_client_order_id": "client_order_id",
    "brokerstopclientorderid": "client_order_id",
    "disaster_stop_client_order_id": "client_order_id",
    "disasterstopclientorderid": "client_order_id",
    "falcon_disaster_stop_client_order_id": "client_order_id",
    "falcondisasterstopclientorderid": "client_order_id",
}

IDENTITY_GROUPS = {
    "trade_id": "trade",
    "trade_uuid": "trade_uuid",
    "registry_id": "registry",
    "lifecycle_id": "lifecycle",
    "execution_id": "execution",
    "decision_id": "decision",
    "signal_id": "signal",
    "client_order_id": "client_order",
    "exchange_order_id": "order",
    "broker_order_id": "order",
    "broker_stop_order_id": "order",
    "disaster_stop_order_id": "order",
    "order_id": "order",
    "fill_id": "fill",
    "fill_ids": "fill",
}

STRONG_IDENTITY_GROUPS = frozenset(
    {
        "trade_uuid",
        "registry",
        "lifecycle",
        "client_order",
        "order",
        "fill",
    }
)
SECONDARY_IDENTITY_GROUPS = frozenset(
    {"execution", "decision", "signal", "trade"}
)

# These names document fields that cannot establish indexed trade identity.
# They are deliberately absent from IDENTITY_KEYS.  The list is included in
# the contract hash so that a future taxonomy change invalidates old indexes.
EXCLUDED_EVENT_IDENTITY_FIELDS = frozenset({"uid", "event_id"})
UNSAFE_IDENTITY_FIELDS = frozenset(
    {
        "bot",
        "bot_name",
        "setup",
        "strategy",
        "symbol",
        "bingx_symbol",
        "side",
        "direction",
        "position_side",
        "positionside",
        "occurred_at",
        "event_ts",
        "timestamp",
        "ts",
        "created_at",
        "generated_at",
        "received_at",
        "updated_at",
        "last_update",
        "opened_at",
        "closed_at",
        "epoch",
    }
)

LEGACY_DERIVED_STOP_CLIENT_ID_SUFFIX = "-DS"


@dataclass(frozen=True, order=True)
class TypedIdentity:
    """One deterministic, typed, indexable journal identity.

    ``identity_type`` is the canonical field name rather than only the broad
    correlation group.  Consequently, the same textual value under different
    types remains represented by distinct entries.
    """

    identity_type: str
    identity_value: str
    identity_group: str
    identity_class: str

    @property
    def classification(self) -> str:
        """Compatibility spelling for storage/reporting code."""

        return self.identity_class


def canonical_identity_key(value: Any) -> str:
    """Return the canonical Validator identity field name."""

    key = str(value or "").lower().strip()
    return IDENTITY_KEY_ALIASES.get(key, key)


def iter_mapping_nodes(value: Any) -> Iterable[Mapping[str, Any]]:
    """Walk mappings with the exact container recursion used by the Validator.

    Mapping values and list/tuple children are recursive.  Sets are accepted
    as identity value collections but are not structural traversal containers.
    """

    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            if isinstance(child, (Mapping, list, tuple)):
                yield from iter_mapping_nodes(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from iter_mapping_nodes(child)


def extract_identity_pairs(record: Mapping[str, Any]) -> Dict[str, set[str]]:
    """Collect canonical typed values using the current Validator semantics.

    This factual extraction includes historical ``*-DS`` values.  Callers that
    create index postings must use :func:`extract_typed_identities` instead.
    """

    found: Dict[str, set[str]] = {}
    for item in iter_mapping_nodes(record):
        for raw_key, raw_value in item.items():
            key = canonical_identity_key(raw_key)
            if key not in IDENTITY_KEYS:
                continue
            values = (
                raw_value
                if isinstance(raw_value, (list, tuple, set))
                else (raw_value,)
            )
            for value in values:
                if value in (None, "") or isinstance(value, Mapping):
                    continue
                text = str(value).strip()
                if text:
                    found.setdefault(key, set()).add(text)
    return found


def group_identity_pairs(
    record_or_pairs: Mapping[str, Any],
    *,
    already_extracted: bool = False,
) -> Dict[str, set[str]]:
    """Group extracted identities exactly as the Validator does.

    ``already_extracted`` exists to avoid re-walking a record during a streaming
    build.  It must only be set for the output of ``extract_identity_pairs``.
    """

    pairs = record_or_pairs if already_extracted else extract_identity_pairs(record_or_pairs)
    grouped: Dict[str, set[str]] = {}
    for key, values in pairs.items():
        group = IDENTITY_GROUPS.get(key)
        if group:
            grouped.setdefault(group, set()).update(values)
    return grouped


def is_legacy_derived_stop_client_id(value: Any) -> bool:
    """Return whether an extracted client ID is the historical ``*-DS`` form."""

    return str(value or "").upper().endswith(LEGACY_DERIVED_STOP_CLIENT_ID_SUFFIX)


def classify_identity(identity_type: Any, identity_value: Any) -> Optional[str]:
    """Classify an identity for indexing, or return ``None`` when non-indexable.

    The classification is deliberately rejection-first.  Unsupported/unsafe
    fields and legacy derived stop client IDs receive no posting class.
    """

    key = canonical_identity_key(identity_type)
    group = IDENTITY_GROUPS.get(key)
    value = str(identity_value).strip() if identity_value is not None else ""
    if not value or group is None:
        return None
    if group == "client_order" and is_legacy_derived_stop_client_id(value):
        return None
    if group in STRONG_IDENTITY_GROUPS:
        return IDENTITY_CLASS_STRONG
    if group in SECONDARY_IDENTITY_GROUPS:
        return IDENTITY_CLASS_SECONDARY
    return None


def extract_typed_identities(record: Mapping[str, Any]) -> tuple[TypedIdentity, ...]:
    """Return deterministically ordered STRONG/SECONDARY index entries."""

    entries: list[TypedIdentity] = []
    for identity_type, values in extract_identity_pairs(record).items():
        identity_group = IDENTITY_GROUPS.get(identity_type)
        if identity_group is None:
            continue
        for identity_value in values:
            identity_class = classify_identity(identity_type, identity_value)
            if identity_class is None:
                continue
            entries.append(
                TypedIdentity(
                    identity_type=identity_type,
                    identity_value=identity_value,
                    identity_group=identity_group,
                    identity_class=identity_class,
                )
            )
    return tuple(sorted(entries))


def identity_contract_manifest() -> Dict[str, Any]:
    """Return the canonical JSON-safe manifest hashed by this contract."""

    return {
        "contract_version": IDENTITY_CONTRACT_VERSION,
        "identity_keys": sorted(IDENTITY_KEYS),
        "identity_key_aliases": {
            key: IDENTITY_KEY_ALIASES[key] for key in sorted(IDENTITY_KEY_ALIASES)
        },
        "identity_groups": {
            key: IDENTITY_GROUPS[key] for key in sorted(IDENTITY_GROUPS)
        },
        "strong_identity_groups": sorted(STRONG_IDENTITY_GROUPS),
        "secondary_identity_groups": sorted(SECONDARY_IDENTITY_GROUPS),
        "excluded_event_identity_fields": sorted(EXCLUDED_EVENT_IDENTITY_FIELDS),
        "unsafe_identity_fields": sorted(UNSAFE_IDENTITY_FIELDS),
        "legacy_derived_stop_client_id": {
            "suffix": LEGACY_DERIVED_STOP_CLIENT_ID_SUFFIX,
            "case_insensitive": True,
            "index_class": None,
        },
        "extraction": {
            "field_key_normalization": "str(value or '').lower().strip() then alias",
            "value_normalization": "str(value).strip(); case-sensitive",
            "mapping_walk": "preorder mappings; recurse mapping/list/tuple children",
            "value_collections": ["list", "tuple", "set"],
            "skip_values": ["None", "empty-string", "mapping"],
            "deduplication_scope": "canonical-identity-type",
        },
    }


def identity_contract_hash() -> str:
    """Return the deterministic SHA-256 fingerprint of the identity contract."""

    encoded = json.dumps(
        identity_contract_manifest(),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


IDENTITY_CONTRACT_HASH = identity_contract_hash()


__all__ = (
    "EXCLUDED_EVENT_IDENTITY_FIELDS",
    "IDENTITY_CLASS_SECONDARY",
    "IDENTITY_CLASS_STRONG",
    "IDENTITY_CONTRACT_HASH",
    "IDENTITY_CONTRACT_VERSION",
    "IDENTITY_GROUPS",
    "IDENTITY_KEYS",
    "IDENTITY_KEY_ALIASES",
    "LEGACY_DERIVED_STOP_CLIENT_ID_SUFFIX",
    "SECONDARY_IDENTITY_GROUPS",
    "STRONG_IDENTITY_GROUPS",
    "TypedIdentity",
    "UNSAFE_IDENTITY_FIELDS",
    "canonical_identity_key",
    "classify_identity",
    "extract_identity_pairs",
    "extract_typed_identities",
    "group_identity_pairs",
    "identity_contract_hash",
    "identity_contract_manifest",
    "is_legacy_derived_stop_client_id",
    "iter_mapping_nodes",
)
