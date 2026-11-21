"""Offline, read-only comparison of legacy PAPER Registry and bot snapshots.

This module consumes local JSON snapshots only. It never connects to Redis,
the broker, or Render and never writes or repairs any Registry or PAPER ledger.
All matches are diagnostic; ``eligible_for_import`` is always false.

Expected source snapshot shape::

    {
        "source_status_by_bot": {"TURTLE": "OK", ...},
        "positions_by_bot": {"TURTLE": {"BTCUSDT": {"symbol": "BTCUSDT", ...}}, ...},
    }

Every configured bot needs an explicit read status. ``OK`` with an empty
mapping/list means the source was read and contained no positions; an absent
key or failed/invalid read must use a non-OK status and blocks all matching.

The value for each bot may be a mapping of source locator to position mapping,
or a list of position mappings. Raw position data and identifiers are not
included in the generated report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any


_IDENTITY_ALIASES = {
    "lifecycle_id": ("lifecycle_id", "lifecycle_uuid", "lifecycle", "execution_id"),
    "client_order_id": ("client_order_id", "clientOrderId", "live_client_order_id", "entry_client_order_id"),
    "broker_order_id": ("broker_order_id", "brokerOrderId", "order_id", "orderId", "live_order_id", "entry_order_id"),
    "exchange_order_id": ("exchange_order_id", "exchangeOrderId", "bingx_order_id"),
    "fill_id": ("fill_id", "fill_ids"),
    # TRENDPRO snapshots call this legacy logical Registry identifier
    # ``registry_trade_id``. It is review-only, never strong lifecycle proof.
    "trade_id": ("trade_id", "trade_registry_id", "registry_trade_id", "logical_trade_id"),
    # A signal identifies an originating market event, not an executed
    # position/order lifecycle. It may support a sanitized review match only.
    "signal_id": ("signal_id",),
    "source_position_id": ("source_position_id", "position_id", "positionId", "id"),
}
_REVIEW_ID_FIELDS = ("trade_id", "signal_id", "source_position_id")
_STRONG_FIELDS = tuple(name for name in _IDENTITY_ALIASES if name not in _REVIEW_ID_FIELDS)
_COMPOSITE_FIELDS = ("bot", "symbol", "side", "setup", "entry_time", "entry_price")
_COMPOSITE_ALIASES = {
    "bot": ("bot", "bot_name", "strategy_bot"),
    "symbol": ("symbol", "ticker"),
    "side": ("side", "direction", "position_side"),
    "setup": ("setup", "strategy", "strategy_name"),
    "entry_time": ("entry_time", "entry_at", "opened_at"),
    "entry_price": ("entry_price", "entry", "entryPrice", "preco_entrada"),
}
_EXECUTION_MODE_ALIASES = ("execution_mode",)
_REGISTRY_MODE_ALIASES = ("registry_mode",)
_REGISTRY_MODE_CLAIMS = frozenset({"PAPER", "REAL", "VERIFY", "SYNC_ONLY", "UNKNOWN"})
_EXPECTED_SOURCE_BOTS = ("COBRA", "DONKEY", "FALCON", "MEME", "PREDATOR", "TRENDPRO", "TURTLE")
_BOT_DISPLAY_ALIASES = {
    "DONKEY": ("Donkey H4",),
    "FALCON": ("Falcon Strike ORB PRO",),
    "PREDATOR": ("Smart Predator",),
    "TRENDPRO": ("Trend PRO Elite",),
    "TURTLE": ("Turtle Breakout PRO 2.0",),
}
_SOURCE_CLOSE_MARKER_ALIASES = ("closed_at", "closed_datetime", "closed_reason", "closed_price")
# These are counted for operator review only. A signal ID identifies a signal,
# and the V2 register idempotency key identifies a registration/replay event;
# neither is sufficient proof of a position lifecycle across stores.
_SOURCE_DIAGNOSTIC_ID_FIELDS = {
    **_IDENTITY_ALIASES,
    "signal_id": ("signal_id",),
    "registry_v2_register_idempotency_key": (
        "registry_v2_register_idempotency_key",
        "idempotency_key",
    ),
}


def _json_digest(value: Any) -> str:
    return _full_json_digest(value)[:12]


def _full_json_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _values(row: Mapping[str, Any], aliases: tuple[str, ...], *, flatten: bool = False) -> tuple[str, ...]:
    sources = [row]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        sources.append(metadata)
    found: list[str] = []
    for source in sources:
        for alias in aliases:
            if alias not in source:
                continue
            value = source[alias]
            items = value if flatten and isinstance(value, (list, tuple, set)) else (value,)
            for item in items:
                if isinstance(item, (str, int)) and not isinstance(item, bool):
                    normalized = str(item).strip()
                    if normalized and normalized not in found:
                        found.append(normalized)
    # Predator stores register_open_trade's result beside trade_registry_id.
    # Its nested trade_id is useful only to detect a logical-ID disagreement;
    # _review_ids keeps this class review-only, never strong/importable proof.
    if aliases == _IDENTITY_ALIASES["trade_id"]:
        open_result = row.get("trade_registry_open_result")
        if isinstance(open_result, Mapping):
            nested_values = [open_result.get("trade_id")]
            nested_trade = open_result.get("trade")
            if isinstance(nested_trade, Mapping):
                nested_values.append(nested_trade.get("trade_id"))
            for value in nested_values:
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    normalized = str(value).strip()
                    if normalized and normalized not in found:
                        found.append(normalized)
    return tuple(found)


def _canonical_bot_name(value: str) -> str:
    normalized = str(value).strip().upper()
    for canonical, display_aliases in _BOT_DISPLAY_ALIASES.items():
        if normalized == canonical or normalized in {
            alias.upper() for alias in display_aliases
        }:
            return canonical
    return normalized


def _single_alias_value(row: Mapping[str, Any], aliases: tuple[str, ...], *, canonical: bool = False) -> str | None:
    values = _values(row, aliases)
    if canonical and aliases == _COMPOSITE_ALIASES["bot"]:
        normalized = {_canonical_bot_name(value) for value in values}
        return next(iter(normalized)) if len(normalized) == 1 else None
    if len(values) != 1:
        return None
    value = values[0]
    return value.upper() if canonical else value


def _strong_ids(row: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    result = []
    for field in _STRONG_FIELDS:
        for value in _values(row, _IDENTITY_ALIASES[field], flatten=field == "fill_id"):
            result.append((field, value))
    return tuple(result)


def _review_ids(row: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return logical/source-local identifiers that can only support review."""
    result = []
    for field in _REVIEW_ID_FIELDS:
        for value in _values(row, _IDENTITY_ALIASES[field]):
            result.append((field, value))
    return tuple(result)


def _derive_donkey_logical_trade_id(row: Mapping[str, Any], bot: str) -> str | None:
    """Mirror DONKEY's deterministic Registry key for review-only matching.

    DONKEY's writer derives ``make_trade_id(bot, symbol, side, setup)`` and
    does not persist that ID on every bot position. This recreates only that
    logical key; it is not lifecycle/order identity and cannot authorize import.
    """
    if bot != "DONKEY":
        return None
    setup = (
        _single_alias_value(row, ("signal_type",), canonical=True)
        or _single_alias_value(row, ("setup",), canonical=True)
    )
    raw_symbol = (
        _single_alias_value(row, ("symbol_clean",))
        or _single_alias_value(row, ("symbol",))
    )
    raw_side = (
        _single_alias_value(row, ("side",), canonical=True)
        or _single_alias_value(row, ("signal",), canonical=True)
    )
    if not setup or not raw_symbol or not raw_side:
        return None

    symbol = (
        raw_symbol.replace("/USDT:USDT", "USDT")
        .replace("/USDT", "USDT")
        .upper()
        .replace("/", "")
        .replace(":USDT", "")
        .replace("-", "")
        .strip()
    )
    side = {"BUY": "LONG", "SELL": "SHORT"}.get(raw_side, raw_side)
    if not symbol or symbol == "UNKNOWN" or not side or side == "UNKNOWN":
        return None
    return f"DONKEY:{setup}:{symbol}:{side}"


def _source_review_ids(row: Mapping[str, Any], bot: str) -> tuple[tuple[str, str], ...]:
    """Return stored review IDs, or a DONKEY logical key when derivable."""
    stored = _review_ids(row)
    if stored:
        return stored
    derived = _derive_donkey_logical_trade_id(row, bot)
    return (("trade_id", derived),) if derived else ()


def _ambiguous_review_status(fields: set[str]) -> str:
    if fields == {"source_position_id"}:
        return "AMBIGUOUS_POSITION_ID"
    if fields == {"signal_id"}:
        return "AMBIGUOUS_SIGNAL_ID"
    return "AMBIGUOUS_LOGICAL_ID"


def _missing_review_status(fields: set[str]) -> str:
    if fields == {"source_position_id"}:
        return "POSITION_ID_NOT_FOUND"
    if fields == {"signal_id"}:
        return "SIGNAL_ID_NOT_FOUND"
    return "LOGICAL_ID_NOT_FOUND"


def _identity_alias_conflict(row: Mapping[str, Any]) -> bool:
    fields = {**_IDENTITY_ALIASES, **_COMPOSITE_ALIASES}
    for field, aliases in fields.items():
        if field == "fill_id":
            continue
        values = _values(row, aliases)
        if field == "bot":
            if len({_canonical_bot_name(value) for value in values}) > 1:
                return True
        elif len(values) > 1:
            return True
    return False


def _mode_status(registry_row: Mapping[str, Any], source_row: Mapping[str, Any]) -> str:
    # A generic ``mode`` can describe a bot/scanner/registry mode rather than
    # the mode in which a factual position was executed. Only the explicit
    # execution_mode field is suitable for this confirmation.
    registry_values = _values(registry_row, _EXECUTION_MODE_ALIASES)
    source_values = _values(source_row, _EXECUTION_MODE_ALIASES)
    if len(registry_values) > 1 or len(source_values) > 1:
        return "MODE_ALIAS_CONFLICT"
    registry_mode = _single_alias_value(registry_row, _EXECUTION_MODE_ALIASES, canonical=True)
    source_mode = _single_alias_value(source_row, _EXECUTION_MODE_ALIASES, canonical=True)
    if registry_mode and source_mode and registry_mode != source_mode:
        return "MODE_CONFLICT"
    if registry_mode == "PAPER" and source_mode == "PAPER":
        return "PAPER_CONFIRMED_BY_BOTH_SNAPSHOTS"
    return "MODE_UNVERIFIED"


def _registry_mode_claim(registry_row: Mapping[str, Any]) -> str:
    """Report the Registry's mode claim separately from execution proof."""
    values = {value.upper() for value in _values(registry_row, _REGISTRY_MODE_ALIASES)}
    if not values:
        return "UNSET"
    if len(values) > 1:
        return "CONFLICT"
    claim = next(iter(values))
    return claim if claim in _REGISTRY_MODE_CLAIMS else "INVALID"


def _composite_key(row: Mapping[str, Any], bot: str) -> tuple[str, ...] | None:
    values = {field: _single_alias_value(row, _COMPOSITE_ALIASES[field], canonical=True) for field in _COMPOSITE_FIELDS if field != "bot"}
    values["bot"] = _single_alias_value(row, _COMPOSITE_ALIASES["bot"], canonical=True) or bot
    if any(not values.get(field) for field in _COMPOSITE_FIELDS):
        return None
    return tuple(values[field] for field in _COMPOSITE_FIELDS)


def _registry_rows(registry_snapshot: Mapping[str, Any], collection: str) -> list[tuple[str, str, Mapping[str, Any]]]:
    if not isinstance(registry_snapshot, Mapping):
        raise ValueError("registry_snapshot_object_required")
    raw = registry_snapshot.get(collection)
    if isinstance(raw, Mapping):
        candidates = [(str(key), row) for key, row in raw.items()]
    elif isinstance(raw, list):
        candidates = [(str(index), row) for index, row in enumerate(raw)]
    else:
        raise ValueError(f"registry_{collection}_invalid")
    rows = []
    for index, (locator, row) in enumerate(candidates, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"registry_{collection}_row_invalid")
        rows.append((f"registry-{collection}-{index:04d}-{_json_digest(row)}", locator, row))
    return rows


def _source_rows(source_snapshot: Mapping[str, Any]) -> list[tuple[str, str, str, Mapping[str, Any]]]:
    if not isinstance(source_snapshot, Mapping):
        raise ValueError("source_snapshot_object_required")
    by_bot = source_snapshot.get("positions_by_bot")
    if not isinstance(by_bot, Mapping):
        raise ValueError("source_positions_by_bot_invalid")
    status_by_bot = source_snapshot.get("source_status_by_bot")
    if not isinstance(status_by_bot, Mapping):
        raise ValueError("source_status_by_bot_invalid")

    normalized_statuses: dict[str, str] = {}
    for bot_key, raw_status in status_by_bot.items():
        bot = str(bot_key).strip().upper()
        status = str(raw_status).strip().upper() if isinstance(raw_status, str) else ""
        if not bot or not status or bot in normalized_statuses:
            raise ValueError("source_status_by_bot_invalid")
        normalized_statuses[bot] = status
    if set(normalized_statuses) != set(_EXPECTED_SOURCE_BOTS):
        raise ValueError("source_status_bot_set_incomplete")

    normalized_positions: dict[str, Any] = {}
    for bot_key, positions in by_bot.items():
        bot = str(bot_key).strip().upper()
        if not bot or bot in normalized_positions:
            raise ValueError("source_bot_name_invalid")
        normalized_positions[bot] = positions
    if set(normalized_positions) - set(_EXPECTED_SOURCE_BOTS):
        raise ValueError("source_positions_bot_unknown")
    for bot, status in normalized_statuses.items():
        if status == "OK" and bot not in normalized_positions:
            raise ValueError("source_positions_missing_for_ok_bot")

    rows = []
    index = 0
    for bot in _EXPECTED_SOURCE_BOTS:
        if normalized_statuses[bot] != "OK":
            continue
        positions = normalized_positions[bot]
        if isinstance(positions, Mapping):
            items = [(str(key), value) for key, value in positions.items()]
        elif isinstance(positions, list):
            items = [(str(item_index), value) for item_index, value in enumerate(positions)]
        else:
            raise ValueError("source_positions_for_bot_invalid")
        for locator, position in items:
            if not isinstance(position, Mapping):
                raise ValueError("source_position_invalid")
            declared_bot = _single_alias_value(position, _COMPOSITE_ALIASES["bot"], canonical=True)
            if declared_bot and declared_bot != bot:
                raise ValueError("source_bot_key_conflict")
            if len({
                _canonical_bot_name(value)
                for value in _values(position, _COMPOSITE_ALIASES["bot"])
            }) > 1:
                raise ValueError("source_bot_alias_conflict")
            index += 1
            ref = f"source-{index:04d}-{_json_digest(position)}"
            rows.append((ref, bot, locator, position))
    return rows


def _source_diagnostics(
    sources: list[tuple[str, str, str, Mapping[str, Any]]],
    source_statuses: Mapping[str, str],
) -> dict[str, Any]:
    """Summarize source state without returning position values or identifiers."""
    by_bot: dict[str, Any] = {}
    for bot in _EXPECTED_SOURCE_BOTS:
        rows = [row for _, row_bot, _, row in sources if row_bot == bot]
        statuses = Counter(
            _single_alias_value(row, ("status",), canonical=True) or "<UNSET>"
            for row in rows
        )
        execution_modes = Counter(
            _single_alias_value(row, _EXECUTION_MODE_ALIASES, canonical=True) or "<UNSET>"
            for row in rows
        )
        close_marked = sum(
            bool(_values(row, _SOURCE_CLOSE_MARKER_ALIASES)) for row in rows
        )
        identity_presence = {
            field: sum(bool(_values(row, aliases, flatten=field == "fill_id")) for row in rows)
            for field, aliases in _SOURCE_DIAGNOSTIC_ID_FIELDS.items()
        }
        derived_logical_ids = sum(
            not _review_ids(row) and _derive_donkey_logical_trade_id(row, bot) is not None
            for row in rows
        )
        by_bot[bot] = {
            "source_status": source_statuses.get(bot, "<UNSET>"),
            "record_count": len(rows),
            "status_counts": dict(sorted(statuses.items())),
            "execution_mode_counts": dict(sorted(execution_modes.items())),
            "records_with_close_marker": close_marked,
            "records_without_close_marker": len(rows) - close_marked,
            "derived_logical_trade_id_records": derived_logical_ids,
            "identity_field_presence_counts": {
                field: count for field, count in sorted(identity_presence.items()) if count
            },
        }
    return {"by_bot": by_bot, "record_count": len(sources)}


def source_snapshot_structure_diagnostics(source_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return fixed-field counts even when strict source validation fails.

    This diagnostic intentionally does not reconcile records. It exists so a
    malformed or bot-key-conflicting snapshot can be investigated without
    echoing arbitrary labels, identifiers, status values, or payloads.
    """
    positions_by_bot = source_snapshot.get("positions_by_bot")
    source_statuses = source_snapshot.get("source_status_by_bot")
    if not isinstance(positions_by_bot, Mapping) or not isinstance(source_statuses, Mapping):
        return {"record_count": 0, "by_bot": {}}

    by_bot: dict[str, Any] = {}
    total_records = 0
    for bot in _EXPECTED_SOURCE_BOTS:
        raw_positions = positions_by_bot.get(bot)
        if isinstance(raw_positions, Mapping):
            rows = list(raw_positions.values())
        elif isinstance(raw_positions, list):
            rows = raw_positions
        else:
            rows = []

        counts = Counter({
            "bot_field_present_records": 0,
            "bot_field_missing_records": 0,
            "canonical_bot_match_records": 0,
            "known_display_name_match_records": 0,
            "other_bot_label_records": 0,
            "bot_alias_conflict_records": 0,
            "invalid_row_records": 0,
        })
        identity_presence = Counter()
        for row in rows:
            if not isinstance(row, Mapping):
                counts["invalid_row_records"] += 1
                continue
            values = _values(row, _COMPOSITE_ALIASES["bot"])
            normalized = {_canonical_bot_name(value) for value in values}
            if values:
                counts["bot_field_present_records"] += 1
                if len(normalized) > 1:
                    counts["bot_alias_conflict_records"] += 1
                elif normalized == {bot}:
                    raw_values = {value.upper() for value in values}
                    if bot in raw_values:
                        counts["canonical_bot_match_records"] += 1
                    else:
                        counts["known_display_name_match_records"] += 1
                else:
                    counts["other_bot_label_records"] += 1
            else:
                counts["bot_field_missing_records"] += 1
            for field, aliases in _SOURCE_DIAGNOSTIC_ID_FIELDS.items():
                if _values(row, aliases, flatten=field == "fill_id"):
                    identity_presence[field] += 1

        total_records += len(rows)
        by_bot[bot] = {
            "source_status": str(source_statuses.get(bot, "<UNSET>")).upper()
            if str(source_statuses.get(bot, "<UNSET>")).upper() in {
                "OK", "KEY_MISSING", "READ_FAILED", "INVALID_JSON", "INVALID_SHAPE"
            }
            else "INVALID_STATUS",
            "record_count": len(rows),
            **dict(counts),
            "identity_field_presence_counts": dict(sorted(identity_presence.items())),
        }
    return {"record_count": total_records, "by_bot": by_bot}


def preview_paper_registry_sources(
    registry_snapshot: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Return sanitized identity diagnostics; never an import/migration plan."""
    registry = _registry_rows(registry_snapshot, "open_trades")
    closed_registry = _registry_rows(registry_snapshot, "closed_trades")
    all_registry = registry + closed_registry
    sources = _source_rows(source_snapshot)
    source_statuses = {
        str(bot).strip().upper(): str(status).strip().upper()
        for bot, status in source_snapshot["source_status_by_bot"].items()
    }
    incomplete_bots = sorted(bot for bot, status in source_statuses.items() if status != "OK")
    source_complete = not incomplete_bots
    source_diagnostics = _source_diagnostics(sources, source_statuses)

    source_by_strong: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    registry_by_strong: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    source_by_review_id: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    registry_by_review_id: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    source_review_fields: set[tuple[str, str]] = set()
    source_by_composite: dict[tuple[str, ...], list[int]] = defaultdict(list)
    registry_by_composite: dict[tuple[str, ...], list[int]] = defaultdict(list)

    for index, (_, bot, _, row) in enumerate(sources):
        for field, value in _strong_ids(row):
            source_by_strong[(bot, field, value)].append(index)
        for field, value in _source_review_ids(row, bot):
            source_by_review_id[(bot, field, value)].append(index)
            source_review_fields.add((bot, field))
        key = _composite_key(row, bot)
        if key:
            source_by_composite[key].append(index)

    registry_bots: list[str] = []
    registry_review_ids: list[tuple[tuple[str, str], ...]] = []
    registry_strong: list[tuple[tuple[str, str], ...]] = []
    registry_alias_conflicts: list[bool] = []
    for index, (_, _, row) in enumerate(all_registry):
        bot = _single_alias_value(row, _COMPOSITE_ALIASES["bot"], canonical=True) or ""
        registry_bots.append(bot)
        review_ids = _review_ids(row)
        registry_review_ids.append(review_ids)
        strong = _strong_ids(row)
        registry_strong.append(strong)
        registry_alias_conflicts.append(_identity_alias_conflict(row))
        for field, value in strong:
            registry_by_strong[(bot, field, value)].append(index)
        for field, value in review_ids:
            registry_by_review_id[(bot, field, value)].append(index)
        key = _composite_key(row, bot)
        if key:
            registry_by_composite[key].append(index)

    results = []
    matched_source_indexes: set[int] = set()
    candidate_indexes_by_registry: list[set[int]] = []
    matched_registry_by_source: dict[int, list[tuple[int, str]]] = defaultdict(list)
    # Classify both open and closed Registry rows. Closed history must be able
    # to explain a bot snapshot; otherwise source rows that match only a
    # closed lifecycle would be incorrectly reported as unmatched.
    for index, (registry_ref, _, row) in enumerate(all_registry):
        bot = registry_bots[index]
        strong_conflicts: set[int] = set()
        candidate_source_indexes: set[int] = set()
        source_index = None
        if not source_complete:
            status = "SOURCE_SNAPSHOT_INCOMPLETE"
        elif registry_alias_conflicts[index]:
            status = "IDENTITY_ALIAS_CONFLICT"
        elif registry_strong[index]:
            identifier_sets = []
            any_strong_found = False
            for field, value in registry_strong[index]:
                matching = set(source_by_strong.get((bot, field, value), ()))
                identifier_sets.append(matching)
                any_strong_found = any_strong_found or bool(matching)
                for (source_bot, source_field, source_value), source_indexes in source_by_strong.items():
                    if source_field == field and source_value == value and source_bot != bot:
                        strong_conflicts.update(source_indexes)
            common_matches = set.intersection(*identifier_sets) if identifier_sets else set()
            for matches in identifier_sets:
                candidate_source_indexes.update(matches)
            candidate_source_indexes.update(strong_conflicts)
            if strong_conflicts:
                status = "STRONG_ID_BOT_CONFLICT"
            elif len(common_matches) == 1:
                candidate = next(iter(common_matches))
                # Enforce one-to-one use for every identity field.
                reverse_indexes = {
                    other
                    for field, value in registry_strong[index]
                    for other in registry_by_strong.get((bot, field, value), ())
                }
                source_alias_conflict = _identity_alias_conflict(sources[candidate][3])
                if source_alias_conflict:
                    status = "SOURCE_IDENTITY_ALIAS_CONFLICT"
                elif len(reverse_indexes) == 1:
                    status = "STRONG_IDENTITY_MATCH_REVIEW"
                    source_index = candidate
                else:
                    status = "AMBIGUOUS_STRONG_ID"
            elif len(common_matches) > 1:
                status = "AMBIGUOUS_STRONG_ID"
            elif any_strong_found:
                status = "STRONG_ID_PARTIAL_CONFLICT"
            else:
                status = "STRONG_ID_NOT_FOUND"
        else:
            review_ids = registry_review_ids[index]
            shared_review_ids = [
                (field, value)
                for field, value in review_ids
                if (bot, field) in source_review_fields
            ]
            review_candidates = [
                set(source_by_review_id.get((bot, field, value), ()))
                for field, value in shared_review_ids
            ]
            any_review_id_found = any(review_candidates)
            common_review_candidates = (
                set.intersection(*review_candidates) if review_candidates else set()
            )
            for matches in review_candidates:
                candidate_source_indexes.update(matches)
            review_fields = {field for field, _ in shared_review_ids}
            if shared_review_ids and len(common_review_candidates) == 1:
                candidate = next(iter(common_review_candidates))
                reverse_indexes = {
                    other
                    for field, value in shared_review_ids
                    for other in registry_by_review_id.get((bot, field, value), ())
                }
                if _identity_alias_conflict(sources[candidate][3]):
                    status = "SOURCE_IDENTITY_ALIAS_CONFLICT"
                elif len(reverse_indexes) == 1:
                    if review_fields == {"trade_id"}:
                        status = "LOGICAL_ID_REVIEW_ONLY"
                    elif review_fields == {"signal_id"}:
                        status = "SIGNAL_ID_REVIEW_ONLY"
                    elif review_fields == {"source_position_id"}:
                        status = "POSITION_ID_REVIEW_ONLY"
                    else:
                        status = "REVIEW_IDENTITY_REVIEW_ONLY"
                    source_index = candidate
                else:
                    status = _ambiguous_review_status(review_fields)
            elif shared_review_ids and len(common_review_candidates) > 1:
                status = _ambiguous_review_status(review_fields)
            elif shared_review_ids and any_review_id_found:
                status = "PARTIAL_REVIEW_ID_CONFLICT"
            elif review_ids:
                status = _missing_review_status(review_fields or {field for field, _ in review_ids})
            else:
                composite = _composite_key(row, bot)
                source_candidates = set(source_by_composite.get(composite, ())) if composite else set()
                candidate_source_indexes.update(source_candidates)
                if composite and len(source_candidates) == 1 and len(registry_by_composite.get(composite, ())) == 1:
                    candidate = next(iter(source_candidates))
                    if _identity_alias_conflict(sources[candidate][3]):
                        status = "SOURCE_IDENTITY_ALIAS_CONFLICT"
                    elif _strong_ids(sources[candidate][3]) or _source_review_ids(
                        sources[candidate][3], sources[candidate][1]
                    ):
                        status = "COMPOSITE_HAS_SOURCE_ID_UNMATCHED"
                    else:
                        status = "COMPOSITE_REVIEW_ONLY"
                        source_index = candidate
                elif composite and source_candidates:
                    status = "AMBIGUOUS_COMPOSITE"
                else:
                    status = "UNMATCHED"

        source_ref = sources[source_index][0] if source_index is not None else None
        if source_index is not None:
            matched_source_indexes.add(source_index)
            matched_registry_by_source[source_index].append((index, status))
            mode_status = _mode_status(row, sources[source_index][3])
        else:
            mode_status = "MODE_UNVERIFIED"
        registry_mode_claim = _registry_mode_claim(row)
        results.append({
            "registry_ref": registry_ref,
            "source_ref": source_ref,
            "status": status,
            "registry_mode_claim": registry_mode_claim,
            "mode_status": mode_status,
            "eligible_for_import": False,
        })
        candidate_indexes_by_registry.append(candidate_source_indexes)

    open_results = results[:len(registry)]
    closed_results = results[len(registry):]
    status_counts = Counter(item["status"] for item in open_results)
    mode_counts = Counter(item["mode_status"] for item in open_results)
    registry_mode_claim_counts = Counter(item["registry_mode_claim"] for item in open_results)
    closed_status_counts = Counter(item["status"] for item in closed_results)
    closed_mode_counts = Counter(item["mode_status"] for item in closed_results)
    source_reconciliation_counts = Counter()
    review_only_statuses = {
        "LOGICAL_ID_REVIEW_ONLY",
        "SIGNAL_ID_REVIEW_ONLY",
        "POSITION_ID_REVIEW_ONLY",
        "REVIEW_IDENTITY_REVIEW_ONLY",
        "COMPOSITE_REVIEW_ONLY",
    }
    for source_index in range(len(sources)):
        candidate_registry_indexes = [
            registry_index
            for registry_index, candidates in enumerate(candidate_indexes_by_registry)
            if source_index in candidates
        ]
        matches = matched_registry_by_source.get(source_index, [])
        if not source_complete:
            source_reconciliation_counts["unresolved_incomplete_snapshot"] += 1
        elif not candidate_registry_indexes:
            # Only a complete seven-key snapshot can establish an orphan in the
            # captured sources; missing bots make all negative matches uncertain.
            source_reconciliation_counts["orphan_no_registry_candidate"] += 1
        elif (
            len(candidate_registry_indexes) == 1
            and len(matches) == 1
            and matches[0][0] == candidate_registry_indexes[0]
        ):
            registry_index, match_status = matches[0]
            collection = "open" if registry_index < len(registry) else "closed"
            if match_status == "STRONG_IDENTITY_MATCH_REVIEW":
                source_reconciliation_counts[f"unique_strong_match_{collection}"] += 1
            elif match_status in review_only_statuses:
                source_reconciliation_counts[f"unique_review_only_match_{collection}"] += 1
            else:
                source_reconciliation_counts["ambiguous_or_conflicting_candidate"] += 1
        else:
            source_reconciliation_counts["ambiguous_or_conflicting_candidate"] += 1

    # Keep a stable schema, including zero-valued categories, in sanitized output.
    source_reconciliation_counts = {
        key: int(source_reconciliation_counts.get(key, 0))
        for key in (
            "unique_strong_match_open",
            "unique_review_only_match_open",
            "unique_strong_match_closed",
            "unique_review_only_match_closed",
            "ambiguous_or_conflicting_candidate",
            "orphan_no_registry_candidate",
            "unresolved_incomplete_snapshot",
        )
    }
    return {
        "ok": True,
        "status": "PREVIEW_ONLY_NOT_MIGRATABLE",
        "registry_snapshot_sha256": _full_json_digest(registry_snapshot),
        "source_snapshot_sha256": _full_json_digest(source_snapshot),
        "registry_open_count": len(registry),
        "registry_closed_count": len(closed_registry),
        "source_position_count": len(sources),
        "source_diagnostics": source_diagnostics,
        "source_reconciliation_counts": source_reconciliation_counts,
        "source_snapshot_complete": source_complete,
        "source_incomplete_bots": incomplete_bots,
        "source_bot_status_counts": dict(sorted(Counter(source_statuses.values()).items())),
        "unmatched_source_count": len(sources) - len(matched_source_indexes),
        "registry_status_counts": dict(sorted(status_counts.items())),
        "registry_closed_status_counts": dict(sorted(closed_status_counts.items())),
        "registry_mode_claim_counts": dict(sorted(registry_mode_claim_counts.items())),
        "registry_mode_status_counts": dict(sorted(mode_counts.items())),
        "registry_closed_mode_status_counts": dict(sorted(closed_mode_counts.items())),
        "all_rows_ineligible_for_import": True,
        "rows": open_results,
    }


def _load_local_json(path: str) -> Mapping[str, Any]:
    if "://" in path:
        raise ValueError("local_json_paths_required")
    try:
        raw = Path(path).read_bytes()
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json_number")))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        raise ValueError("snapshot_read_or_parse_failed") from None
    if not isinstance(value, Mapping):
        raise ValueError("snapshot_object_required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview legacy PAPER Registry identity against local bot snapshots; never migrates.")
    parser.add_argument("--registry-snapshot", required=True)
    parser.add_argument("--source-snapshot", required=True)
    args = parser.parse_args(argv)
    try:
        report = preview_paper_registry_sources(
            _load_local_json(args.registry_snapshot),
            _load_local_json(args.source_snapshot),
        )
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    # Keep local CLI output shareable by allowlisting fields. An omit-list is
    # insufficient here: source_diagnostics contains mappings keyed by raw
    # position status/execution_mode values, and source status/bot names can be
    # caller-controlled too. The detailed in-process report remains available
    # to callers, but the CLI must not emit those arbitrary strings.
    safe_fields = (
        "ok",
        "status",
        "registry_open_count",
        "registry_closed_count",
        "source_position_count",
        "source_reconciliation_counts",
        "source_snapshot_complete",
        "unmatched_source_count",
        "registry_status_counts",
        "registry_closed_status_counts",
        "registry_mode_claim_counts",
        "registry_mode_status_counts",
        "registry_closed_mode_status_counts",
        "all_rows_ineligible_for_import",
    )
    sanitized_report = {key: report[key] for key in safe_fields}
    sanitized_report["row_details_omitted"] = True
    print(json.dumps(sanitized_report, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
