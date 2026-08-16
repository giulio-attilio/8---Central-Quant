"""Offline C2 full-response shadow parity for the trade evidence index.

This module is intentionally dormant.  It has no environment-driven entry
point, HTTP route, startup hook, cache, writer, or operational authority.  A
caller must provide explicit schema-V2 sidecars, local journal paths, a
Registry envelope that was already resolved by the legacy correlator, and
static values for every non-indexed source.

Only ``history_manager`` and ``timeline`` are replaced in the hybrid bundle.
All other sources are replayed through the existing Validator collector in its
real component order.  The two source/index sessions remain pinned through
bundle construction, Validator execution, Snapshot execution and the final
mutation check.  Any uncertainty discards the staged hybrid result.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import time
import tracemalloc
from contextlib import ExitStack
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Sequence

import live_trade_snapshot as snapshot_module
import trade_timeline_validator as validator
from trade_evidence_identity_offset_source_envelope_v1 import (
    BUILT,
    COMPLETENESS_FULL_CERTIFIED,
    EnvelopeCaps,
    IndexedSourceEnvelope,
    MAX_SOURCE_JOURNAL_BYTES,
    PinnedSourceIndexSession,
    plan_and_build_from_pinned_session,
)


VERSION = "2026-08-15-TRADE-EVIDENCE-IDENTITY-OFFSET-C2-FULL-SHADOW-V2"

MATCH = "MATCH"
MISMATCH = "MISMATCH"
NOT_COMPARABLE = "NOT_COMPARABLE"
FALLBACK_REQUIRED = "FALLBACK_REQUIRED"

PARITY_AXES = (
    "source_envelope",
    "evidence_bundle",
    "validator",
    "snapshot",
    "physical",
    "semantic",
)
MISMATCH_CATEGORIES = (
    "SOURCE_ROWS",
    "PHYSICAL_METADATA",
    "IDENTITY",
    "PROMOTION",
    "EVENTS",
    "COVERAGE",
    "CURSOR",
    "VALIDATOR",
    "SNAPSHOT",
    "COMPLETENESS",
    "SOURCE_MUTATION",
    "INDEX_MUTATION",
)
INDEXED_SOURCES = ("history_manager", "timeline")
FULL_COMPONENT_ORDER = tuple(snapshot_module.SOURCE_ORDER)

MAX_FULL_SOURCE_JOURNAL_BYTES = 2 * MAX_SOURCE_JOURNAL_BYTES
MAX_FULL_STATIC_SOURCE_BYTES = 16 * 1024 * 1024
MAX_FULL_STATIC_RECORDS = 50_000
POSITIVE_CERTIFIED_COMPLETE = "POSITIVE_CERTIFIED_COMPLETE"
POSITIVE_UNSAFE = "POSITIVE_UNSAFE"
# Existing Validator/Phase-B parity tests already treat only these wall-clock
# execution fields as non-contractual.  Keep the exclusion versioned and
# visible in the bounded C2 report; no semantic/data timestamp is normalized.
NON_CONTRACTUAL_TIMING_FIELDS = (
    "validator.generated_at",
    "validator.summary.duration_ms",
    "snapshot.generated_at",
    "snapshot.duration_ms",
)

FaultInjector = Optional[Callable[[str, Mapping[str, Any]], None]]


class _FullShadowAbort(RuntimeError):
    def __init__(
        self,
        reason: str,
        *,
        status: str = FALLBACK_REQUIRED,
        category: str = "COMPLETENESS",
    ) -> None:
        super().__init__(reason)
        self.reason = str(reason)
        self.status = str(status)
        self.category = str(category)


@dataclass(frozen=True)
class IndexedJournalSpec:
    source_path: Path | str
    index_path: Path | str
    scan_cursor: Optional[str] = None
    planner_options: Mapping[str, Any] = field(default_factory=dict)
    caps: EnvelopeCaps = field(default_factory=EnvelopeCaps)

    def source(self) -> Path:
        return Path(self.source_path)

    def index(self) -> Path:
        return Path(self.index_path)


@dataclass(frozen=True)
class FullShadowCaps:
    max_total_source_journal_bytes: int = MAX_FULL_SOURCE_JOURNAL_BYTES
    max_static_source_bytes: int = MAX_FULL_STATIC_SOURCE_BYTES
    max_static_records: int = MAX_FULL_STATIC_RECORDS

    def validate(self) -> None:
        if not 0 < int(self.max_total_source_journal_bytes) <= MAX_FULL_SOURCE_JOURNAL_BYTES:
            raise ValueError("full shadow journal budget exceeds the C2 hard cap")
        if not 0 < int(self.max_static_source_bytes) <= MAX_FULL_STATIC_SOURCE_BYTES:
            raise ValueError("full shadow static-source budget exceeds the C2 hard cap")
        if not 0 < int(self.max_static_records) <= MAX_FULL_STATIC_RECORDS:
            raise ValueError("full shadow record budget exceeds the C2 hard cap")


@dataclass(frozen=True)
class FullShadowMetrics:
    history_planner_ms: float = 0.0
    history_planner_segment_rows: int = 0
    history_lookup_ms: float = 0.0
    history_certification_ms: float = 0.0
    history_journal_bytes: int = 0
    history_sqlite_rows: int = 0
    history_certification_sqlite_rows: int = 0
    timeline_planner_ms: float = 0.0
    timeline_planner_segment_rows: int = 0
    timeline_lookup_ms: float = 0.0
    timeline_certification_ms: float = 0.0
    timeline_journal_bytes: int = 0
    timeline_sqlite_rows: int = 0
    timeline_certification_sqlite_rows: int = 0
    legacy_journal_bytes: int = 0
    hybrid_journal_bytes: int = 0
    total_journal_bytes: int = 0
    total_planner_segment_rows: int = 0
    total_sqlite_rows: int = 0
    legacy_bundle_ms: float = 0.0
    hybrid_bundle_ms: float = 0.0
    legacy_validator_ms: float = 0.0
    hybrid_validator_ms: float = 0.0
    legacy_snapshot_ms: float = 0.0
    hybrid_snapshot_ms: float = 0.0
    total_duration_ms: float = 0.0
    peak_tracemalloc_bytes: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FullShadowReport:
    status: str
    reason: Optional[str]
    parity: Mapping[str, bool]
    mismatch_categories: tuple[str, ...]
    source_results: Mapping[str, Mapping[str, Any]]
    digests: Mapping[str, Optional[str]]
    metrics: FullShadowMetrics
    normalized_fields: tuple[str, ...] = NON_CONTRACTUAL_TIMING_FIELDS
    version: str = VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "reason": self.reason,
            "parity": dict(self.parity),
            "mismatch_categories": list(self.mismatch_categories),
            "source_results": {
                str(name): dict(value) for name, value in self.source_results.items()
            },
            "digests": dict(self.digests),
            "metrics": self.metrics.to_dict(),
            "normalized_fields": list(self.normalized_fields),
        }


@dataclass(frozen=True)
class FullShadowResult:
    """Offline-only result.  ``report`` is the bounded telemetry projection."""

    report: FullShadowReport
    legacy_bundle: Optional[validator.EvidenceBundle] = field(
        default=None, repr=False, compare=False
    )
    hybrid_bundle: Optional[validator.EvidenceBundle] = field(
        default=None, repr=False, compare=False
    )
    legacy_validator: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    hybrid_validator: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    legacy_snapshot: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    hybrid_snapshot: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    legacy_timeline_payload: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    hybrid_timeline_payload: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    legacy_snapshot_payload: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )
    hybrid_snapshot_payload: Optional[Mapping[str, Any]] = field(
        default=None, repr=False, compare=False
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if is_dataclass(value):
        return {item.name: _plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(item) for item in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Path):
        return os.fspath(value)
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _digest(value: Any) -> str:
    payload = json.dumps(
        _plain(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="surrogatepass")
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


def _context_projection(context: validator.CorrelationContext) -> Mapping[str, Any]:
    return MappingProxyType(
        {item.name: _plain(getattr(context, item.name)) for item in fields(context)}
    )


def _same_stat(left: os.stat_result, right: os.stat_result) -> bool:
    return bool(
        int(left.st_dev) == int(right.st_dev)
        and int(left.st_ino) == int(right.st_ino)
        and int(left.st_size) == int(right.st_size)
        and int(left.st_mtime_ns) == int(right.st_mtime_ns)
        and int(left.st_ctime_ns) == int(right.st_ctime_ns)
    )


def _fault(fault_injector: FaultInjector, point: str, **detail: Any) -> None:
    if fault_injector is not None:
        fault_injector(point, MappingProxyType(dict(detail)))


def _is_cap_failure(reason: str) -> bool:
    upper = str(reason).upper()
    return any(token in upper for token in ("CAP", "BUDGET", "LIMIT_EXCEEDED"))


def _abort_for_reason(reason: str, *, source: Optional[str] = None) -> _FullShadowAbort:
    raw = f"{source}:{reason}" if source else str(reason)
    upper = raw.upper()
    if _is_cap_failure(upper):
        return _FullShadowAbort(
            raw, status=FALLBACK_REQUIRED, category="COMPLETENESS"
        )
    if any(token in upper for token in ("SOURCE", "MUTAT", "TRUNC", "REPLACE")):
        return _FullShadowAbort(
            raw, status=NOT_COMPARABLE, category="SOURCE_MUTATION"
        )
    if any(
        token in upper
        for token in ("INDEX", "GENERATION", "CERTIFICATION", "SIDECAR", "SQLITE")
    ):
        return _FullShadowAbort(
            raw, status=NOT_COMPARABLE, category="INDEX_MUTATION"
        )
    return _FullShadowAbort(raw, category="COMPLETENESS")


def _shadow_runtime_flags_enabled() -> bool:
    enabled = {"1", "true", "yes", "on"}
    return bool(
        str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_ENABLED", ""))
        .strip()
        .lower()
        in enabled
        and str(os.environ.get("TRADE_EVIDENCE_INDEX_SHADOW_COMPARE_ENABLED", ""))
        .strip()
        .lower()
        in enabled
    )


def _bounded_shape_bytes(value: Any, byte_limit: int) -> int:
    """Conservatively size concrete replay input without materializing it."""

    stack = [value]
    seen: set[int] = set()
    total = 0
    nodes = 0
    max_nodes = MAX_FULL_STATIC_RECORDS * 64
    while stack:
        item = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise _FullShadowAbort("STATIC_SOURCE_NODE_CAP_EXCEEDED")
        if item is None or isinstance(item, bool):
            total += 8
        elif isinstance(item, str):
            # Four bytes per code point is a conservative UTF-8 upper bound
            # and avoids allocating a second giant bytes object merely to cap.
            total += len(item) * 4 + 8
        elif isinstance(item, bytes):
            total += len(item) + 8
        elif isinstance(item, (int, float)):
            total += 32
        elif isinstance(item, Path):
            total += len(os.fspath(item)) * 4 + 8
        elif isinstance(item, Mapping):
            marker = id(item)
            if marker in seen:
                raise _FullShadowAbort("CYCLIC_STATIC_SOURCE")
            seen.add(marker)
            total += 32 + len(item) * 8
            if total > byte_limit or nodes + 2 * len(item) > max_nodes:
                raise _FullShadowAbort("STATIC_SOURCE_BYTE_CAP_EXCEEDED")
            for key, nested in item.items():
                if not isinstance(key, (str, int, float, bool)):
                    raise _FullShadowAbort("STATIC_SOURCE_KEY_NOT_REPLAYABLE")
                stack.append(key)
                stack.append(nested)
        elif is_dataclass(item):
            marker = id(item)
            if marker in seen:
                raise _FullShadowAbort("CYCLIC_STATIC_SOURCE")
            seen.add(marker)
            total += 32
            entries = fields(item)
            if nodes + len(entries) > max_nodes:
                raise _FullShadowAbort("STATIC_SOURCE_NODE_CAP_EXCEEDED")
            stack.extend(getattr(item, entry.name) for entry in entries)
        elif isinstance(item, (list, tuple, set, frozenset)):
            marker = id(item)
            if marker in seen:
                raise _FullShadowAbort("CYCLIC_STATIC_SOURCE")
            seen.add(marker)
            total += 32 + len(item) * 8
            if total > byte_limit or nodes + len(item) > max_nodes:
                raise _FullShadowAbort("STATIC_SOURCE_BYTE_CAP_EXCEEDED")
            stack.extend(item)
        else:
            # In particular, generators/iterators are never consumed while
            # deciding whether the request is bounded and replayable.
            raise _FullShadowAbort(
                f"STATIC_SOURCE_TYPE_FORBIDDEN:{type(item).__name__}"
            )
        if total > byte_limit:
            raise _FullShadowAbort("STATIC_SOURCE_BYTE_CAP_EXCEEDED")
    return total


def _concrete_record_count(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Mapping):
        for key in ("records", "items", "events", "lifecycles"):
            rows = value.get(key)
            if isinstance(rows, (list, tuple)):
                head = any(
                    name
                    not in {
                        key,
                        "_reader_metadata",
                        "_identity_metadata",
                        "_evidence_correlated",
                        "_correlation_context",
                        "_shadow_index_capture",
                    }
                    for name in value
                )
                return sum(isinstance(row, Mapping) for row in rows) + int(head)
        return 1
    if isinstance(value, (list, tuple)):
        return sum(isinstance(row, Mapping) for row in value)
    raise _FullShadowAbort("STATIC_SOURCE_NOT_REPLAYABLE")


def _validate_static_sources(
    source_values: Mapping[str, Any],
    registry_envelope: Mapping[str, Any],
    caps: FullShadowCaps,
) -> None:
    allowed = set(FULL_COMPONENT_ORDER) - {"registry", *INDEXED_SOURCES}
    if any(not isinstance(key, str) for key in source_values):
        raise _FullShadowAbort("STATIC_SOURCE_KEY_NOT_TEXT", category="SOURCE_ROWS")
    supplied = set(source_values)
    unknown = sorted(supplied - allowed)
    if unknown:
        raise _FullShadowAbort("UNSUPPORTED_STATIC_SOURCE", category="SOURCE_ROWS")
    missing = sorted(allowed - supplied)
    if missing:
        raise _FullShadowAbort(
            "STATIC_SOURCE_SET_INCOMPLETE",
            status=NOT_COMPARABLE,
            category="SOURCE_ROWS",
        )
    total_bytes = _bounded_shape_bytes(
        registry_envelope, caps.max_static_source_bytes
    )
    total_records = _concrete_record_count(registry_envelope)
    for name, value in source_values.items():
        if callable(value):
            raise _FullShadowAbort(
                f"CALLABLE_SOURCE_FORBIDDEN:{name}", category="SOURCE_ROWS"
            )
        if isinstance(value, Mapping) and value.get("_evidence_correlated") is True:
            raise _FullShadowAbort(
                f"PRECORRELATED_SOURCE_FORBIDDEN:{name}", category="PROMOTION"
            )
        remaining = caps.max_static_source_bytes - total_bytes
        total_bytes += _bounded_shape_bytes(value, remaining)
        total_records += _concrete_record_count(value)
        if total_bytes > caps.max_static_source_bytes:
            raise _FullShadowAbort("STATIC_SOURCE_BYTE_CAP_EXCEEDED")
        if total_records > caps.max_static_records:
            raise _FullShadowAbort("STATIC_SOURCE_RECORD_CAP_EXCEEDED")


def _validated_registry_seed(
    trade_id: str, resolved_registry_envelope: Mapping[str, Any]
) -> tuple[dict[str, Any], validator.CorrelationContext]:
    if not isinstance(resolved_registry_envelope, Mapping):
        raise _FullShadowAbort("REGISTRY_ENVELOPE_REQUIRED", category="IDENTITY")
    context = resolved_registry_envelope.get("_correlation_context")
    if (
        resolved_registry_envelope.get("_evidence_correlated") is not True
        or not isinstance(context, validator.CorrelationContext)
        or str(context.trade_id) != trade_id
    ):
        raise _FullShadowAbort(
            "REGISTRY_ENVELOPE_NOT_RESOLVED", category="IDENTITY"
        )
    try:
        seed = copy.deepcopy(context)
        envelope = copy.deepcopy(dict(resolved_registry_envelope))
    except Exception as exc:
        raise _FullShadowAbort("REGISTRY_SEED_CLONE_FAILED", category="IDENTITY") from exc
    envelope["_evidence_correlated"] = True
    envelope["_correlation_context"] = seed
    if "records" not in envelope:
        raise _FullShadowAbort("REGISTRY_RECORDS_MISSING", category="IDENTITY")
    return envelope, seed


def _source_map_base(
    registry_envelope: Mapping[str, Any],
    holder: dict[str, validator.CorrelationContext],
    source_values: Mapping[str, Any],
) -> dict[str, Any]:
    def registry_reader(_trade_id: str) -> dict[str, Any]:
        value = copy.deepcopy(dict(registry_envelope))
        value["_correlation_context"] = holder["context"]
        return value

    source_map: dict[str, Any] = {
        name: copy.deepcopy(value) for name, value in source_values.items()
    }
    source_map["registry"] = registry_reader
    return source_map


def _build_legacy_bundle(
    trade_id: str,
    registry_envelope: Mapping[str, Any],
    registry_seed: validator.CorrelationContext,
    source_values: Mapping[str, Any],
    specs: Mapping[str, IndexedJournalSpec],
    *,
    logger: logging.Logger,
) -> validator.EvidenceBundle:
    holder = {"context": copy.deepcopy(registry_seed)}
    source_map = _source_map_base(registry_envelope, holder, source_values)

    for source_id in INDEXED_SOURCES:
        spec = specs[source_id]

        def legacy_reader(
            identity: str,
            *,
            _source_id: str = source_id,
            _spec: IndexedJournalSpec = spec,
        ) -> Mapping[str, Any]:
            value = validator._default_reader(
                _source_id,
                (_spec.source(),),
                holder["context"],
                scan_cursor=_spec.scan_cursor,
            )(identity)
            source_context = value.get("_correlation_context")
            if not isinstance(source_context, validator.CorrelationContext):
                raise _FullShadowAbort(
                    f"LEGACY_CONTEXT_MISSING:{_source_id}", category="PROMOTION"
                )
            holder["context"] = source_context
            return value

        source_map[source_id] = legacy_reader

    return validator.collect_evidence_bundle(
        trade_id,
        sources=source_map,
        logger=logger,
        component_order=FULL_COMPONENT_ORDER,
        passthrough_components=("external_exposure",),
        record_coercer=snapshot_module._records,
    )


def _is_full_certified_result(result: IndexedSourceEnvelope) -> bool:
    # C2 source-envelope hardening exports the final label.  Keep the check
    # literal as a fail-closed compatibility guard while older dormant C1 code
    # is present in a checkout.
    return str(result.completeness_status) == COMPLETENESS_FULL_CERTIFIED


def _build_hybrid_bundle(
    trade_id: str,
    registry_envelope: Mapping[str, Any],
    registry_seed: validator.CorrelationContext,
    source_values: Mapping[str, Any],
    sessions: Mapping[str, PinnedSourceIndexSession],
    specs: Mapping[str, IndexedJournalSpec],
    results: dict[str, IndexedSourceEnvelope],
    *,
    logger: logging.Logger,
    fault_injector: FaultInjector,
) -> validator.EvidenceBundle:
    holder = {"context": copy.deepcopy(registry_seed)}
    source_map = _source_map_base(registry_envelope, holder, source_values)
    failure: dict[str, _FullShadowAbort] = {}

    for source_id in INDEXED_SOURCES:
        spec = specs[source_id]

        def indexed_reader(
            identity: str,
            *,
            _source_id: str = source_id,
            _spec: IndexedJournalSpec = spec,
        ) -> Mapping[str, Any]:
            if failure:
                raise next(iter(failure.values()))
            if _source_id == "timeline":
                _fault(fault_injector, "before_timeline", source=_source_id)
                for active in sessions.values():
                    active.final_check()

            def source_fault(point: str, detail: Mapping[str, Any]) -> None:
                _fault(
                    fault_injector,
                    f"{_source_id}:{point}",
                    source=_source_id,
                    detail=dict(detail),
                )

            result = plan_and_build_from_pinned_session(
                sessions[_source_id],
                target_identity=validator.target_identity_from_context(holder["context"]),
                correlation_context=holder["context"],
                scan_cursor=_spec.scan_cursor,
                fault_injector=source_fault,
                **dict(_spec.planner_options),
            )
            results[_source_id] = result
            if result.status != BUILT:
                abort = _abort_for_reason(
                    str(result.fallback_reason or result.status), source=_source_id
                )
                failure[_source_id] = abort
                raise abort
            if not _is_full_certified_result(result):
                abort = _FullShadowAbort(
                    f"{_source_id}:FULL_CERTIFICATION_REQUIRED",
                    category="COMPLETENESS",
                )
                failure[_source_id] = abort
                raise abort
            projected = result.to_legacy_private_envelope()
            # The collector adopts this exact context object.  Keep the holder
            # on the same object so intervening legacy sources promote IDs seen
            # by the later indexed Timeline reader.
            projected_context = projected.get("_correlation_context")
            if not isinstance(projected_context, validator.CorrelationContext):
                abort = _FullShadowAbort(
                    f"{_source_id}:PROJECTED_CONTEXT_MISSING",
                    category="PROMOTION",
                )
                failure[_source_id] = abort
                raise abort
            holder["context"] = projected_context
            if _source_id == "history_manager":
                _fault(
                    fault_injector,
                    "between_history_and_intermediates",
                    source=_source_id,
                )
                for active in sessions.values():
                    active.final_check()
            else:
                _fault(fault_injector, "after_timeline", source=_source_id)
                for active in sessions.values():
                    active.final_check()
            return projected

        source_map[source_id] = indexed_reader

    bundle = validator.collect_evidence_bundle(
        trade_id,
        sources=source_map,
        logger=logger,
        component_order=FULL_COMPONENT_ORDER,
        passthrough_components=("external_exposure",),
        record_coercer=snapshot_module._records,
    )
    if failure:
        raise next(iter(failure.values()))
    indexed_errors = [
        item
        for item in bundle.errors
        if str(item.get("component")) in INDEXED_SOURCES
    ]
    if indexed_errors:
        item = indexed_errors[0]
        raise _abort_for_reason(
            str(item.get("message") or item.get("error_type") or "SOURCE_BUILD_FAILED"),
            source=str(item.get("component") or "indexed_source"),
        )
    for source_id in INDEXED_SOURCES:
        if source_id not in results:
            raise _FullShadowAbort(
                f"{source_id}:SOURCE_NOT_EXECUTED", category="SOURCE_ROWS"
            )
    # Legacy default readers all alias one request-local mutable context, so
    # their private raw envelopes observe the final context after Timeline.
    # Indexed readers stage clones at each source boundary; restore only that
    # private aliasing contract after the complete hybrid build succeeds.
    for value in bundle.raw_sources.values():
        if (
            isinstance(value, dict)
            and value.get("_evidence_correlated") is True
            and isinstance(value.get("_correlation_context"), validator.CorrelationContext)
        ):
            value["_correlation_context"] = bundle.correlation
    return bundle


def _normalize_validator(report: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(report))
    value.pop("generated_at", None)
    summary = value.get("summary")
    if isinstance(summary, Mapping):
        summary = dict(summary)
        summary.pop("duration_ms", None)
        value["summary"] = summary
    return value


def _normalize_snapshot(report: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(report))
    value.pop("generated_at", None)
    value.pop("duration_ms", None)
    return value


def timeline_public_payload(
    report: Mapping[str, Any], trade_id: str
) -> dict[str, Any]:
    """Pure projection of the current ``/trade_timeline`` success payload."""

    validation_status = str(
        report.get("result") or ("PASS" if report.get("valid") else "FAIL")
    ).upper()
    component_status = {
        str(name): (
            str(detail.get("status") or "UNKNOWN")
            if isinstance(detail, Mapping)
            else "UNKNOWN"
        )
        for name, detail in (report.get("components") or {}).items()
    }

    def public_issues(items: Any, kind: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for item in items or ():
            if isinstance(item, Mapping):
                safe = {
                    key: item.get(key)
                    for key in ("component", "error_type", "code", "status")
                    if item.get(key) not in (None, "")
                }
                output.append(safe or {"type": kind})
            else:
                output.append({"type": kind})
        return output

    payload = {
        "ok": bool(report.get("ok", True)),
        "trade_id": trade_id,
        "validation_status": validation_status,
        "pass": validation_status == "PASS",
        "fail_open": bool(report.get("fail_open", True)),
        "production_blocked": False,
        "coverage": copy.deepcopy(report.get("coverage") or {}),
        "conclusive": bool(report.get("conclusive", True)),
        "evidence_status": report.get("evidence_status")
        or ("EVIDENCE_FOUND" if report.get("events_found") else "COMPLETE_NO_EVIDENCE"),
        "generated_at": report.get("generated_at"),
        "component_status": component_status,
        "events_found": copy.deepcopy(report.get("events_found") or []),
        "missing_events": copy.deepcopy(report.get("events_missing") or []),
        "duplicate_events": copy.deepcopy(report.get("events_duplicated") or []),
        "divergences": copy.deepcopy(report.get("divergences") or []),
        "latencies": copy.deepcopy(report.get("latencies") or []),
        "warnings": public_issues(report.get("warnings"), "VALIDATOR_WARNING"),
        "errors": public_issues(report.get("errors"), "VALIDATOR_ERROR"),
    }
    if isinstance(report.get("identity"), Mapping):
        payload["identity"] = copy.deepcopy(report["identity"])
    return payload


_SNAPSHOT_PUBLIC_KEYS = (
    "ok",
    "snapshot_version",
    "generated_at",
    "trade_id",
    "snapshot_status",
    "trade_status",
    "fail_open",
    "production_blocked",
    "operational_impact",
    "conclusive",
    "evidence_status",
    "identity",
    "trade",
    "broker",
    "registry",
    "lifecycle",
    "execution",
    "risk_protection",
    "management",
    "shadow",
    "telegram",
    "timeline_validation",
    "external_exposure",
    "component_status",
    "divergences",
    "warnings",
    "errors",
    "grace_windows_seconds",
    "coverage",
    "duration_ms",
)


def snapshot_public_payload(
    report: Mapping[str, Any], trade_id: str
) -> dict[str, Any]:
    """Pure projection of the current ``/trade_snapshot`` success payload."""

    payload = {key: copy.deepcopy(report.get(key)) for key in _SNAPSHOT_PUBLIC_KEYS}
    payload["trade_id"] = trade_id
    payload["fail_open"] = True
    payload["production_blocked"] = False
    payload["operational_impact"] = False
    return payload


def _indexed_private_projection(
    bundle: validator.EvidenceBundle, source_id: str
) -> Mapping[str, Any]:
    value = bundle.raw_sources.get(source_id)
    return {
        "records": _plain(bundle.records.get(source_id, ())),
        "reader_metadata": _plain(
            value.get("_reader_metadata", {}) if isinstance(value, Mapping) else {}
        ),
        "identity_metadata": _plain(
            value.get("_identity_metadata", {}) if isinstance(value, Mapping) else {}
        ),
        "context": _plain(
            value.get("_correlation_context") if isinstance(value, Mapping) else None
        ),
    }


def _bundle_projection(bundle: validator.EvidenceBundle) -> Mapping[str, Any]:
    return {
        "trade_id": bundle.trade_id,
        "target_identity": _plain(bundle.target_identity),
        "registry_resolution": _plain(bundle.registry_resolution),
        "records": _plain(bundle.records),
        "raw_sources": _plain(bundle.raw_sources),
        "source_coverage": _plain(bundle.source_coverage),
        "component_status": _plain(bundle.component_status),
        "events": _plain(bundle.events),
        "matched_identifiers": _plain(bundle.matched_identifiers),
        "source_fingerprints": _plain(bundle.source_fingerprints),
        "warnings": _plain(bundle.warnings),
        "errors": _plain(bundle.errors),
        "correlation": _plain(bundle.correlation),
    }


def _comparison_categories(
    legacy: validator.EvidenceBundle,
    hybrid: validator.EvidenceBundle,
    legacy_validator: Mapping[str, Any],
    hybrid_validator: Mapping[str, Any],
    legacy_snapshot: Mapping[str, Any],
    hybrid_snapshot: Mapping[str, Any],
) -> tuple[dict[str, bool], tuple[str, ...]]:
    categories: set[str] = set()
    source_equal = all(
        _indexed_private_projection(legacy, source_id)
        == _indexed_private_projection(hybrid, source_id)
        for source_id in INDEXED_SOURCES
    )
    if any(
        _plain(legacy.records.get(source_id, ()))
        != _plain(hybrid.records.get(source_id, ()))
        for source_id in INDEXED_SOURCES
    ):
        categories.add("SOURCE_ROWS")
    physical_equal = all(
        _plain(legacy.source_coverage.get(source_id, {}))
        == _plain(hybrid.source_coverage.get(source_id, {}))
        and _plain(legacy.component_status.get(source_id, {}))
        == _plain(hybrid.component_status.get(source_id, {}))
        for source_id in INDEXED_SOURCES
    )
    if not physical_equal:
        categories.update(("PHYSICAL_METADATA", "COVERAGE"))
        if any(
            legacy.source_coverage.get(source_id, {}).get("next_scan_cursor")
            != hybrid.source_coverage.get(source_id, {}).get("next_scan_cursor")
            for source_id in INDEXED_SOURCES
        ):
            categories.add("CURSOR")
    semantic_equal = bool(
        _plain(legacy.target_identity) == _plain(hybrid.target_identity)
        and _plain(legacy.registry_resolution) == _plain(hybrid.registry_resolution)
        and _plain(legacy.matched_identifiers) == _plain(hybrid.matched_identifiers)
        and _plain(legacy.correlation) == _plain(hybrid.correlation)
        and _plain(legacy.events) == _plain(hybrid.events)
    )
    if _plain(legacy.events) != _plain(hybrid.events):
        categories.add("EVENTS")
    if (
        _plain(legacy.target_identity) != _plain(hybrid.target_identity)
        or _plain(legacy.registry_resolution) != _plain(hybrid.registry_resolution)
        or _plain(legacy.matched_identifiers) != _plain(hybrid.matched_identifiers)
    ):
        categories.add("IDENTITY")
    if _plain(legacy.correlation) != _plain(hybrid.correlation):
        categories.add("PROMOTION")

    bundle_equal = _bundle_projection(legacy) == _bundle_projection(hybrid)
    if not bundle_equal and not categories:
        categories.add("COVERAGE")
    validator_equal = _normalize_validator(legacy_validator) == _normalize_validator(
        hybrid_validator
    )
    if not validator_equal:
        categories.add("VALIDATOR")
    snapshot_equal = _normalize_snapshot(legacy_snapshot) == _normalize_snapshot(
        hybrid_snapshot
    )
    if not snapshot_equal:
        categories.add("SNAPSHOT")
    parity = {
        "source_envelope": source_equal,
        "evidence_bundle": bundle_equal,
        "validator": validator_equal,
        "snapshot": snapshot_equal,
        "physical": physical_equal,
        "semantic": semantic_equal,
    }
    ordered = tuple(name for name in MISMATCH_CATEGORIES if name in categories)
    return parity, ordered


def _source_result_projection(result: IndexedSourceEnvelope) -> Mapping[str, Any]:
    if result.completeness_status == COMPLETENESS_FULL_CERTIFIED:
        if not result.correlated_rows:
            evidence_completeness = result.negative_status
        elif (
            bool(result.physical_metadata.get("coverage_complete"))
            and bool(result.physical_metadata.get("conclusive"))
            and not bool(result.physical_metadata.get("partial"))
            and not result.physical_metadata.get("next_scan_cursor")
            and not bool(
                result.raw_source_metadata.get("terminal_tail_incomplete")
            )
            and not bool(result.raw_source_metadata.get("scan_cursor_supplied"))
        ):
            evidence_completeness = POSITIVE_CERTIFIED_COMPLETE
        else:
            evidence_completeness = POSITIVE_UNSAFE
    else:
        evidence_completeness = "UNCERTIFIED_COMPLETENESS"
    return MappingProxyType(
        {
            "status": result.status,
            "fallback_reason": result.fallback_reason,
            "index_mode": result.index_mode,
            "negative_status": result.negative_status,
            "completeness_status": result.completeness_status,
            "evidence_completeness": evidence_completeness,
            "records": len(result.correlated_rows),
            "coverage_complete": bool(result.physical_metadata.get("coverage_complete")),
            "partial": bool(result.physical_metadata.get("partial")),
        }
    )


def _metrics(
    results: Mapping[str, IndexedSourceEnvelope],
    *,
    legacy_journal_bytes: int,
    legacy_bundle_ms: float,
    hybrid_bundle_ms: float,
    legacy_validator_ms: float,
    hybrid_validator_ms: float,
    legacy_snapshot_ms: float,
    hybrid_snapshot_ms: float,
    total_duration_ms: float,
    peak_tracemalloc_bytes: Optional[int],
) -> FullShadowMetrics:
    history = results.get("history_manager")
    timeline = results.get("timeline")
    history_metrics = history.metrics if history is not None else None
    timeline_metrics = timeline.metrics if timeline is not None else None
    hybrid_journal = sum(
        int(result.metrics.source_journal_bytes) for result in results.values()
    )
    total_rows = sum(int(result.metrics.sqlite_rows_seen) for result in results.values())
    return FullShadowMetrics(
        history_planner_ms=float(history_metrics.planner_ms if history_metrics else 0.0),
        history_planner_segment_rows=int(
            history_metrics.planner_segment_rows if history_metrics else 0
        ),
        history_lookup_ms=float(
            history_metrics.index_lookup_ms if history_metrics else 0.0
        ),
        history_certification_ms=float(
            history_metrics.certification_ms if history_metrics else 0.0
        ),
        history_journal_bytes=int(
            history_metrics.source_journal_bytes if history_metrics else 0
        ),
        history_sqlite_rows=int(history_metrics.sqlite_rows_seen if history_metrics else 0),
        history_certification_sqlite_rows=int(
            history_metrics.certification_sqlite_rows if history_metrics else 0
        ),
        timeline_planner_ms=float(
            timeline_metrics.planner_ms if timeline_metrics else 0.0
        ),
        timeline_planner_segment_rows=int(
            timeline_metrics.planner_segment_rows if timeline_metrics else 0
        ),
        timeline_lookup_ms=float(
            timeline_metrics.index_lookup_ms if timeline_metrics else 0.0
        ),
        timeline_certification_ms=float(
            timeline_metrics.certification_ms if timeline_metrics else 0.0
        ),
        timeline_journal_bytes=int(
            timeline_metrics.source_journal_bytes if timeline_metrics else 0
        ),
        timeline_sqlite_rows=int(
            timeline_metrics.sqlite_rows_seen if timeline_metrics else 0
        ),
        timeline_certification_sqlite_rows=int(
            timeline_metrics.certification_sqlite_rows if timeline_metrics else 0
        ),
        legacy_journal_bytes=int(legacy_journal_bytes),
        hybrid_journal_bytes=hybrid_journal,
        total_journal_bytes=int(legacy_journal_bytes) + hybrid_journal,
        total_planner_segment_rows=sum(
            int(result.metrics.planner_segment_rows) for result in results.values()
        ),
        total_sqlite_rows=total_rows
        + sum(
            int(result.metrics.planner_segment_rows)
            for result in results.values()
        )
        + sum(
            int(result.metrics.certification_sqlite_rows)
            for result in results.values()
        ),
        legacy_bundle_ms=legacy_bundle_ms,
        hybrid_bundle_ms=hybrid_bundle_ms,
        legacy_validator_ms=legacy_validator_ms,
        hybrid_validator_ms=hybrid_validator_ms,
        legacy_snapshot_ms=legacy_snapshot_ms,
        hybrid_snapshot_ms=hybrid_snapshot_ms,
        total_duration_ms=total_duration_ms,
        peak_tracemalloc_bytes=peak_tracemalloc_bytes,
    )


def _empty_metrics(total_duration_ms: float = 0.0) -> FullShadowMetrics:
    return FullShadowMetrics(total_duration_ms=total_duration_ms)


def _failure_result(
    reason: str,
    *,
    status: str,
    category: str,
    started: float,
    results: Optional[Mapping[str, IndexedSourceEnvelope]] = None,
    metrics: Optional[FullShadowMetrics] = None,
) -> FullShadowResult:
    source_results = {
        name: _source_result_projection(result)
        for name, result in (results or {}).items()
    }
    report = FullShadowReport(
        status=status,
        reason=reason,
        parity=MappingProxyType({name: False for name in PARITY_AXES}),
        mismatch_categories=(category,) if category in MISMATCH_CATEGORIES else (),
        source_results=MappingProxyType(source_results),
        digests=MappingProxyType({}),
        metrics=metrics or _empty_metrics((time.perf_counter() - started) * 1000.0),
    )
    return FullShadowResult(report=report)


def _unexpected_failure_result(
    exc: BaseException,
    *,
    started: float,
    results: Mapping[str, IndexedSourceEnvelope],
    metrics: Optional[FullShadowMetrics] = None,
) -> FullShadowResult:
    raw_reason = str(getattr(exc, "reason", "") or type(exc).__name__)
    upper = raw_reason.upper()
    if _is_cap_failure(upper):
        status, category = FALLBACK_REQUIRED, "COMPLETENESS"
    elif any(token in upper for token in ("SOURCE", "MUTAT", "TRUNC", "REPLACE")):
        status, category = NOT_COMPARABLE, "SOURCE_MUTATION"
    elif any(
        token in upper
        for token in ("INDEX", "GENERATION", "CERTIFICATION", "SIDECAR", "SQLITE")
    ):
        status, category = NOT_COMPARABLE, "INDEX_MUTATION"
    else:
        status, category = FALLBACK_REQUIRED, "COMPLETENESS"
    return _failure_result(
        f"C2_FULL_SHADOW_FAILED:{raw_reason}",
        status=status,
        category=category,
        started=started,
        results=results,
        metrics=metrics,
    )


def run_full_response_shadow_v2(
    trade_id: str,
    *,
    resolved_registry_envelope: Mapping[str, Any],
    static_sources: Mapping[str, Any],
    history: IndexedJournalSpec,
    timeline: IndexedJournalSpec,
    now_epoch: Optional[float] = None,
    full_caps: FullShadowCaps = FullShadowCaps(),
    fault_injector: FaultInjector = None,
    measure_memory: bool = False,
    logger: Optional[logging.Logger] = None,
) -> FullShadowResult:
    """Run legacy versus hybrid full-response parity without authority.

    ``resolved_registry_envelope`` must be the already-correlated Registry
    result from the legacy resolution step.  ``static_sources`` must contain
    replayable values, never callables.  No result from this function is wired
    into a runtime response.
    """

    started = time.perf_counter()
    identity = str(trade_id or "").strip()
    effective_now_epoch = 0.0
    active_logger = logger or logging.getLogger(__name__)
    results: dict[str, IndexedSourceEnvelope] = {}
    specs = {"history_manager": history, "timeline": timeline}
    legacy_journal_bytes = 0
    legacy_bundle_ms = 0.0
    hybrid_bundle_ms = 0.0
    legacy_validator_ms = 0.0
    hybrid_validator_ms = 0.0
    legacy_snapshot_ms = 0.0
    hybrid_snapshot_ms = 0.0
    trace_owned = False
    trace_before = 0
    if measure_memory:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            trace_owned = True
        trace_before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()

    def current_metrics() -> FullShadowMetrics:
        peak_bytes: Optional[int] = None
        if measure_memory and tracemalloc.is_tracing():
            _current, peak = tracemalloc.get_traced_memory()
            peak_bytes = max(0, int(peak) - int(trace_before))
        return _metrics(
            results,
            legacy_journal_bytes=legacy_journal_bytes,
            legacy_bundle_ms=legacy_bundle_ms,
            hybrid_bundle_ms=hybrid_bundle_ms,
            legacy_validator_ms=legacy_validator_ms,
            hybrid_validator_ms=hybrid_validator_ms,
            legacy_snapshot_ms=legacy_snapshot_ms,
            hybrid_snapshot_ms=hybrid_snapshot_ms,
            total_duration_ms=(time.perf_counter() - started) * 1000.0,
            peak_tracemalloc_bytes=peak_bytes,
        )

    try:
        effective_now_epoch = float(
            now_epoch if now_epoch is not None else time.time()
        )
        if not math.isfinite(effective_now_epoch):
            raise _FullShadowAbort("NOW_EPOCH_INVALID")
        if not identity:
            raise _FullShadowAbort("TRADE_ID_REQUIRED", category="IDENTITY")
        full_caps.validate()
        for spec in specs.values():
            spec.caps.validate()
        if sum(spec.caps.max_source_journal_bytes for spec in specs.values()) > full_caps.max_total_source_journal_bytes:
            raise _FullShadowAbort("FULL_JOURNAL_CAP_CONFIGURATION_EXCEEDED")
        if _shadow_runtime_flags_enabled():
            raise _FullShadowAbort(
                "RUNTIME_SHADOW_FLAGS_ENABLED",
                status=NOT_COMPARABLE,
                category="INDEX_MUTATION",
            )
        _validate_static_sources(
            static_sources, resolved_registry_envelope, full_caps
        )
        registry_envelope, registry_seed = _validated_registry_seed(
            identity, resolved_registry_envelope
        )
        original_registry_context = copy.deepcopy(
            resolved_registry_envelope["_correlation_context"]
        )

        pre_legacy_stats = {
            source_id: spec.source().lstat() for source_id, spec in specs.items()
        }
        _fault(fault_injector, "before_legacy_bundle")
        legacy_started = time.perf_counter()
        legacy_bundle = _build_legacy_bundle(
            identity,
            registry_envelope,
            registry_seed,
            static_sources,
            specs,
            logger=active_logger,
        )
        legacy_bundle_ms = (time.perf_counter() - legacy_started) * 1000.0
        legacy_journal_bytes = sum(
            int(
                legacy_bundle.source_coverage.get(source_id, {}).get(
                    "bytes_scanned", 0
                )
                or 0
            )
            for source_id in INDEXED_SOURCES
        )
        post_legacy_stats = {
            source_id: spec.source().lstat() for source_id, spec in specs.items()
        }
        if any(
            not _same_stat(pre_legacy_stats[name], post_legacy_stats[name])
            for name in INDEXED_SOURCES
        ):
            raise _FullShadowAbort(
                "SOURCE_CHANGED_DURING_LEGACY",
                status=NOT_COMPARABLE,
                category="SOURCE_MUTATION",
            )
        _fault(fault_injector, "after_legacy_bundle")

        with ExitStack() as stack:
            sessions = {
                source_id: stack.enter_context(
                    PinnedSourceIndexSession(
                        spec.source(),
                        spec.index(),
                        source_id,
                        caps=spec.caps,
                    )
                )
                for source_id, spec in specs.items()
            }
            if any(
                not _same_stat(post_legacy_stats[name], specs[name].source().lstat())
                for name in INDEXED_SOURCES
            ):
                raise _FullShadowAbort(
                    "SOURCE_CHANGED_BEFORE_PIN",
                    status=NOT_COMPARABLE,
                    category="SOURCE_MUTATION",
                )
            _fault(fault_injector, "after_sessions_pinned")
            for session in sessions.values():
                session.final_check()

            hybrid_started = time.perf_counter()
            hybrid_bundle = _build_hybrid_bundle(
                identity,
                registry_envelope,
                registry_seed,
                static_sources,
                sessions,
                specs,
                results,
                logger=active_logger,
                fault_injector=fault_injector,
            )
            hybrid_bundle_ms = (time.perf_counter() - hybrid_started) * 1000.0
            for session in sessions.values():
                session.final_check()
            if sum(
                result.metrics.source_journal_bytes for result in results.values()
            ) > full_caps.max_total_source_journal_bytes:
                raise _FullShadowAbort("FULL_JOURNAL_BYTE_CAP_EXCEEDED")

            _fault(fault_injector, "during_validator")
            legacy_validator_started = time.perf_counter()
            legacy_validator = validator.validate_trade_timeline(
                identity, evidence_bundle=legacy_bundle, logger=active_logger
            )
            legacy_validator_ms = (
                time.perf_counter() - legacy_validator_started
            ) * 1000.0
            hybrid_validator_started = time.perf_counter()
            hybrid_validator = validator.validate_trade_timeline(
                identity, evidence_bundle=hybrid_bundle, logger=active_logger
            )
            hybrid_validator_ms = (
                time.perf_counter() - hybrid_validator_started
            ) * 1000.0
            for session in sessions.values():
                session.final_check()

            _fault(fault_injector, "before_snapshot")
            legacy_snapshot_started = time.perf_counter()
            legacy_snapshot = snapshot_module.build_live_trade_snapshot(
                identity,
                now_epoch=effective_now_epoch,
                logger=active_logger,
                evidence_bundle=legacy_bundle,
            )
            legacy_snapshot_ms = (
                time.perf_counter() - legacy_snapshot_started
            ) * 1000.0
            hybrid_snapshot_started = time.perf_counter()
            hybrid_snapshot = snapshot_module.build_live_trade_snapshot(
                identity,
                now_epoch=effective_now_epoch,
                logger=active_logger,
                evidence_bundle=hybrid_bundle,
            )
            hybrid_snapshot_ms = (
                time.perf_counter() - hybrid_snapshot_started
            ) * 1000.0
            _fault(fault_injector, "after_snapshot")
            for session in sessions.values():
                session.final_check()

        if resolved_registry_envelope["_correlation_context"] != original_registry_context:
            raise _FullShadowAbort(
                "OFFICIAL_CONTEXT_MUTATED", category="PROMOTION"
            )

        legacy_timeline_payload = timeline_public_payload(legacy_validator, identity)
        hybrid_timeline_payload = timeline_public_payload(hybrid_validator, identity)
        legacy_snapshot_payload = snapshot_public_payload(legacy_snapshot, identity)
        hybrid_snapshot_payload = snapshot_public_payload(hybrid_snapshot, identity)

        parity, categories = _comparison_categories(
            legacy_bundle,
            hybrid_bundle,
            legacy_validator,
            hybrid_validator,
            legacy_snapshot,
            hybrid_snapshot,
        )
        if _normalize_validator(legacy_timeline_payload) != _normalize_validator(
            hybrid_timeline_payload
        ):
            parity["validator"] = False
            categories = tuple(
                name
                for name in MISMATCH_CATEGORIES
                if name in set(categories) | {"VALIDATOR"}
            )
        if _normalize_snapshot(legacy_snapshot_payload) != _normalize_snapshot(
            hybrid_snapshot_payload
        ):
            parity["snapshot"] = False
            categories = tuple(
                name
                for name in MISMATCH_CATEGORIES
                if name in set(categories) | {"SNAPSHOT"}
            )

        source_results = MappingProxyType(
            {
                name: _source_result_projection(result)
                for name, result in results.items()
            }
        )
        digests = MappingProxyType(
            {
                "legacy_bundle": _digest(_bundle_projection(legacy_bundle)),
                "hybrid_bundle": _digest(_bundle_projection(hybrid_bundle)),
                "legacy_validator": _digest(_normalize_validator(legacy_validator)),
                "hybrid_validator": _digest(_normalize_validator(hybrid_validator)),
                "legacy_snapshot": _digest(_normalize_snapshot(legacy_snapshot)),
                "hybrid_snapshot": _digest(_normalize_snapshot(hybrid_snapshot)),
                "legacy_timeline_payload": _digest(
                    _normalize_validator(legacy_timeline_payload)
                ),
                "hybrid_timeline_payload": _digest(
                    _normalize_validator(hybrid_timeline_payload)
                ),
                "legacy_snapshot_payload": _digest(
                    _normalize_snapshot(legacy_snapshot_payload)
                ),
                "hybrid_snapshot_payload": _digest(
                    _normalize_snapshot(hybrid_snapshot_payload)
                ),
            }
        )
        # Final response projections/digests are part of the offline C2
        # request.  Measure only after they have been materialized so the
        # harness does not hide their CPU or peak-allocation cost.
        metrics = current_metrics()
        status = MATCH if all(parity.values()) else MISMATCH
        report = FullShadowReport(
            status=status,
            reason=None if status == MATCH else "ZERO_TOLERANCE_PARITY_MISMATCH",
            parity=MappingProxyType(dict(parity)),
            mismatch_categories=categories,
            source_results=source_results,
            digests=digests,
            metrics=metrics,
        )
        return FullShadowResult(
            report=report,
            legacy_bundle=legacy_bundle,
            hybrid_bundle=hybrid_bundle,
            legacy_validator=legacy_validator,
            hybrid_validator=hybrid_validator,
            legacy_snapshot=legacy_snapshot,
            hybrid_snapshot=hybrid_snapshot,
            legacy_timeline_payload=legacy_timeline_payload,
            hybrid_timeline_payload=hybrid_timeline_payload,
            legacy_snapshot_payload=legacy_snapshot_payload,
            hybrid_snapshot_payload=hybrid_snapshot_payload,
        )
    except _FullShadowAbort as exc:
        return _failure_result(
            exc.reason,
            status=exc.status,
            category=exc.category,
            started=started,
            results=results,
            metrics=current_metrics(),
        )
    except FileNotFoundError:
        return _failure_result(
            "SOURCE_OR_INDEX_MISSING",
            status=FALLBACK_REQUIRED,
            category="SOURCE_MUTATION",
            started=started,
            results=results,
            metrics=current_metrics(),
        )
    except Exception as exc:
        return _unexpected_failure_result(
            exc,
            started=started,
            results=results,
            metrics=current_metrics(),
        )
    finally:
        if measure_memory and trace_owned and tracemalloc.is_tracing():
            tracemalloc.stop()


__all__ = (
    "FALLBACK_REQUIRED",
    "FullShadowCaps",
    "FullShadowMetrics",
    "FullShadowReport",
    "FullShadowResult",
    "IndexedJournalSpec",
    "MATCH",
    "MISMATCH",
    "MISMATCH_CATEGORIES",
    "NOT_COMPARABLE",
    "NON_CONTRACTUAL_TIMING_FIELDS",
    "PARITY_AXES",
    "POSITIVE_CERTIFIED_COMPLETE",
    "POSITIVE_UNSAFE",
    "VERSION",
    "run_full_response_shadow_v2",
    "snapshot_public_payload",
    "timeline_public_payload",
)
