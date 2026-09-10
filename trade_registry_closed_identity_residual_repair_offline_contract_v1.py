"""Dormant offline planner for residual CLOSED identity conflicts.

The module accepts only an injected in-memory snapshot.  It has no runtime,
filesystem, network, broker, or persistence integration.  It can archive
source-position aliases when provenance and bounded clock resolution prove the
operation safe; genuinely divergent timestamps remain quarantined.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-REPAIR-OFFLINE-CONTRACT-V1"
)

_ARCHIVE_KEY = "c3_residual_identity_evidence_v1"
_UTC = dt.timezone.utc
_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_MINUTE_ONLY_RE = re.compile(r"(?:T|\s)\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?$")
_SAFE_CENTRAL_SOURCE = "main_traderegistry_sync"
_SAFE_CENTRAL_MARKER = "central_open_positions"
_SAFE_PREDATOR_SOURCE = "predator_paper_registry_sync_fix_v1"
_SAFE_PREDATOR_MARKER = "predator_module_open_positions"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_sha256_v1(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64:
        return ""
    try:
        bytes.fromhex(normalized)
    except ValueError:
        return ""
    return normalized


def _copy_document(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_canonical_json(dict(value)))


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _minute_precision(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", stripped):
        return True
    return bool(_MINUTE_ONLY_RE.search(stripped))


def _timestamp(value: Any) -> tuple[dt.datetime, str] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        unit = "EPOCH_MILLISECONDS" if abs(number) >= 100_000_000_000 else "EPOCH_SECONDS"
        seconds = number / 1000.0 if unit == "EPOCH_MILLISECONDS" else number
        try:
            parsed = dt.datetime.fromtimestamp(seconds, _UTC)
        except (OverflowError, OSError, ValueError):
            return None
        if not 946_684_800 <= seconds <= 4_102_444_800:
            return None
        return parsed, unit

    raw = _text(value)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            parsed = dt.datetime.strptime(raw, fmt).replace(tzinfo=_SAO_PAULO)
            return parsed.astimezone(_UTC), "LOCAL_TEXT"
        except ValueError:
            pass
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_SAO_PAULO)
    return parsed.astimezone(_UTC), "ISO_TEXT"


def normalize_residual_timestamp_v1(value: Any) -> str:
    """Return one validated UTC instant without performing I/O."""

    parsed = _timestamp(value)
    return parsed[0].isoformat() if parsed is not None else ""


@dataclass(frozen=True)
class ResidualClosedIdentityRepairCapsV1:
    max_closed_records: int = 10_000
    max_residual_records: int = 42
    predator_epoch_tolerance_seconds: float = 60.0
    minute_boundary_tolerance_seconds: float = 90.0


def _base_result() -> dict[str, Any]:
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION,
        "ok": False,
        "status": "OFFLINE_RESIDUAL_REPAIR_BLOCKED",
        "offline_only": True,
        "in_memory_only": True,
        "default_off": True,
        "apply_allowed": False,
        "runtime_activation_allowed": False,
        "registry_accessed": False,
        "registry_write": False,
        "write_executed": False,
        "broker_called": False,
        "order_sent": False,
        "candidate_registry": None,
        "changed_paths": [],
        "quarantine": [],
        "reasons": [],
    }


def _blocked(reason: str, *, snapshot_sha256: str = "") -> dict[str, Any]:
    result = _base_result()
    result["reasons"] = [reason]
    result["source_snapshot_sha256"] = snapshot_sha256
    return result


def _provenance(trade: Mapping[str, Any], metadata: Mapping[str, Any]) -> tuple[str, str, str]:
    source = _text(trade.get("source") or metadata.get("source"))
    marker = _text(metadata.get("synced_from"))
    bot = _upper(trade.get("bot") or metadata.get("bot"))
    return source, marker, bot


def _safe_timestamp_rule(
    trade: Mapping[str, Any],
    metadata: Mapping[str, Any],
    *,
    caps: ResidualClosedIdentityRepairCapsV1,
) -> tuple[str, float, str] | None:
    canonical_raw = trade.get("opened_at")
    alias_raw = metadata.get("created_at")
    canonical = _timestamp(canonical_raw)
    alias = _timestamp(alias_raw)
    if canonical is None or alias is None:
        return None
    delta = abs((canonical[0] - alias[0]).total_seconds())
    if delta == 0:
        return "EXACT_INSTANT", delta, alias[1]

    source, marker, bot = _provenance(trade, metadata)
    if (
        source == _SAFE_PREDATOR_SOURCE
        and marker == _SAFE_PREDATOR_MARKER
        and bot == "PREDATOR"
        and alias[1] in {"EPOCH_SECONDS", "EPOCH_MILLISECONDS"}
        and _minute_precision(canonical_raw)
        and delta <= caps.predator_epoch_tolerance_seconds
    ):
        return "PREDATOR_EPOCH_SAME_MINUTE", delta, alias[1]

    minute_resolution_proven = _minute_precision(canonical_raw) or _minute_precision(alias_raw)
    if (
        source == "falcon"
        and bot == "FALCON"
        and minute_resolution_proven
        and delta <= caps.minute_boundary_tolerance_seconds
    ):
        return "FALCON_SIGNAL_MINUTE_BOUNDARY", delta, alias[1]

    if (
        source == _SAFE_CENTRAL_SOURCE
        and marker == _SAFE_CENTRAL_MARKER
        and minute_resolution_proven
        and delta <= caps.minute_boundary_tolerance_seconds
        and alias[1] not in {"EPOCH_SECONDS", "EPOCH_MILLISECONDS"}
    ):
        return "CENTRAL_POSITION_MINUTE_BOUNDARY", delta, alias[1]
    return None


def _timestamp_delta_seconds(
    trade: Mapping[str, Any], metadata: Mapping[str, Any]
) -> float | None:
    canonical = _timestamp(trade.get("opened_at"))
    alias = _timestamp(metadata.get("created_at"))
    if canonical is None or alias is None:
        return None
    return abs((canonical[0] - alias[0]).total_seconds())


def _archive_field(
    metadata: dict[str, Any],
    *,
    field: str,
    source_value: Any,
    canonical_path: str,
    canonical_value: Any,
    classification: str,
    delta_seconds: float | None = None,
) -> None:
    archive = metadata.setdefault(
        _ARCHIVE_KEY,
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION,
            "fields": {},
        },
    )
    fields = archive["fields"]
    evidence = {
        "source_path": f"trade.metadata.{field}",
        "source_value": copy.deepcopy(source_value),
        "source_value_sha256": stable_sha256_v1(source_value),
        "canonical_path": canonical_path,
        "canonical_value_sha256": stable_sha256_v1(canonical_value),
        "classification": classification,
    }
    if delta_seconds is not None:
        evidence["delta_seconds"] = round(float(delta_seconds), 6)
    fields[field] = evidence


def _changed_leaf_paths(before: Any, after: Any, prefix: str = "") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        paths: set[str] = set()
        for key in set(before) | set(after):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.add(child)
            else:
                paths.update(_changed_leaf_paths(before[key], after[key], child))
        return paths
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return {prefix}
        paths = set()
        for index, (left, right) in enumerate(zip(before, after)):
            paths.update(_changed_leaf_paths(left, right, f"{prefix}[{index}]"))
        return paths
    return set() if before == after else {prefix}


def _authorized_changed_path(path: str) -> bool:
    return bool(
        re.fullmatch(
            rf"closed_trades\[\d+\]\.metadata\.(?:created_at|status|{_ARCHIVE_KEY}(?:\..+)?)",
            path,
        )
    )


def build_residual_closed_identity_repair_plan_v1(
    registry_snapshot: Mapping[str, Any],
    *,
    expected_snapshot_sha256: str,
    caps: ResidualClosedIdentityRepairCapsV1 | None = None,
) -> dict[str, Any]:
    """Return a deterministic, non-applicable repair candidate or fail closed."""

    caps = caps or ResidualClosedIdentityRepairCapsV1()
    if (
        isinstance(caps.max_closed_records, bool)
        or not isinstance(caps.max_closed_records, int)
        or caps.max_closed_records <= 0
        or isinstance(caps.max_residual_records, bool)
        or not isinstance(caps.max_residual_records, int)
        or caps.max_residual_records <= 0
        or isinstance(caps.predator_epoch_tolerance_seconds, bool)
        or not isinstance(caps.predator_epoch_tolerance_seconds, (int, float))
        or not math.isfinite(float(caps.predator_epoch_tolerance_seconds))
        or caps.predator_epoch_tolerance_seconds < 0
        or isinstance(caps.minute_boundary_tolerance_seconds, bool)
        or not isinstance(caps.minute_boundary_tolerance_seconds, (int, float))
        or not math.isfinite(float(caps.minute_boundary_tolerance_seconds))
        or caps.minute_boundary_tolerance_seconds < 0
    ):
        return _blocked("INVALID_REPAIR_CAPS")
    if not isinstance(registry_snapshot, Mapping):
        return _blocked("REGISTRY_SNAPSHOT_NOT_MAPPING")
    try:
        source = _copy_document(registry_snapshot)
    except (TypeError, ValueError):
        return _blocked("REGISTRY_SNAPSHOT_NOT_CANONICAL_JSON")
    source_sha = stable_sha256_v1(source)
    if _valid_sha256(expected_snapshot_sha256) != source_sha:
        return _blocked("SOURCE_SNAPSHOT_SHA256_MISMATCH", snapshot_sha256=source_sha)
    closed = source.get("closed_trades")
    if not isinstance(closed, list):
        return _blocked("CLOSED_TRADES_NOT_LIST", snapshot_sha256=source_sha)
    if len(closed) > caps.max_closed_records:
        return _blocked("CLOSED_RECORD_CAP_EXCEEDED", snapshot_sha256=source_sha)
    if any(not isinstance(item, dict) for item in closed):
        return _blocked("CLOSED_TRADES_INVALID_RECORD", snapshot_sha256=source_sha)

    candidate = copy.deepcopy(source)
    actions: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    residual_indexes: set[int] = set()
    timestamp_archived = 0
    status_archived = 0

    for index, before_trade in enumerate(closed):
        before_metadata = before_trade.get("metadata")
        if before_metadata is not None and not isinstance(before_metadata, dict):
            return _blocked("CLOSED_TRADE_METADATA_INVALID", snapshot_sha256=source_sha)
        metadata = before_metadata if isinstance(before_metadata, dict) else {}
        if _ARCHIVE_KEY in metadata:
            return _blocked("PREEXISTING_RESIDUAL_EVIDENCE_ARCHIVE", snapshot_sha256=source_sha)
        opened_present = before_trade.get("opened_at") not in (None, "")
        created_present = metadata.get("created_at") not in (None, "")
        opened_conflict = False
        if opened_present and created_present:
            left = _timestamp(before_trade.get("opened_at"))
            right = _timestamp(metadata.get("created_at"))
            opened_conflict = left is None or right is None or left[0] != right[0]
        canonical_status = _upper(before_trade.get("status"))
        legacy_status = _upper(metadata.get("status"))
        status_conflict = bool(canonical_status and legacy_status and canonical_status != legacy_status)
        if not opened_conflict and not status_conflict:
            continue
        residual_indexes.add(index)
        if len(residual_indexes) > caps.max_residual_records:
            return _blocked("RESIDUAL_RECORD_CAP_EXCEEDED", snapshot_sha256=source_sha)

        after_trade = candidate["closed_trades"][index]
        after_metadata = after_trade.get("metadata")
        if not isinstance(after_metadata, dict):
            after_metadata = {}
            after_trade["metadata"] = after_metadata
        record_sha = stable_sha256_v1(before_trade)

        if opened_conflict:
            safe_rule = _safe_timestamp_rule(before_trade, metadata, caps=caps)
            delta = _timestamp_delta_seconds(before_trade, metadata)
            if safe_rule is None:
                quarantine.append(
                    {
                        "registry_index": index,
                        "record_sha256": record_sha,
                        "field": "opened_at",
                        "reason": "TIMESTAMP_PROVENANCE_OR_DELTA_UNPROVEN",
                        "delta_seconds": None if delta is None else round(delta, 6),
                    }
                )
            else:
                classification, delta, _kind = safe_rule
                original = copy.deepcopy(metadata["created_at"])
                _archive_field(
                    after_metadata,
                    field="created_at",
                    source_value=original,
                    canonical_path="trade.opened_at",
                    canonical_value=before_trade.get("opened_at"),
                    classification=classification,
                    delta_seconds=delta,
                )
                del after_metadata["created_at"]
                timestamp_archived += 1
                actions.append(
                    {
                        "registry_index": index,
                        "record_sha256": record_sha,
                        "field": "opened_at",
                        "action": "ARCHIVE_METADATA_ALIAS_PRESERVE_CANONICAL",
                        "classification": classification,
                    }
                )

        if status_conflict:
            source_name, marker, _bot = _provenance(before_trade, metadata)
            if (
                canonical_status == "CLOSED"
                and source_name == _SAFE_CENTRAL_SOURCE
                and marker == _SAFE_CENTRAL_MARKER
            ):
                original = copy.deepcopy(metadata["status"])
                _archive_field(
                    after_metadata,
                    field="status",
                    source_value=original,
                    canonical_path="trade.status",
                    canonical_value=before_trade.get("status"),
                    classification="CLOSED_CANONICAL_SOURCE_POSITION_STATUS_ARCHIVED",
                )
                del after_metadata["status"]
                status_archived += 1
                actions.append(
                    {
                        "registry_index": index,
                        "record_sha256": record_sha,
                        "field": "status",
                        "action": "ARCHIVE_METADATA_ALIAS_PRESERVE_CLOSED",
                        "classification": "SOURCE_POSITION_STATE_NOT_CLOSED_LIFECYCLE_STATE",
                    }
                )
            else:
                quarantine.append(
                    {
                        "registry_index": index,
                        "record_sha256": record_sha,
                        "field": "status",
                        "reason": "STATUS_PROVENANCE_OR_CLOSED_STATE_UNPROVEN",
                    }
                )

    changed = sorted(_changed_leaf_paths(source, candidate))
    if any(not _authorized_changed_path(path) for path in changed):
        return _blocked("CANDIDATE_CHANGED_UNAUTHORIZED_PATH", snapshot_sha256=source_sha)

    for action in actions:
        index = action["registry_index"]
        field = "created_at" if action["field"] == "opened_at" else "status"
        before_value = closed[index]["metadata"][field]
        archive = candidate["closed_trades"][index]["metadata"][_ARCHIVE_KEY]["fields"][field]
        if archive.get("source_value") != before_value or archive.get(
            "source_value_sha256"
        ) != stable_sha256_v1(before_value):
            return _blocked("ARCHIVED_VALUE_PRESERVATION_FAILED", snapshot_sha256=source_sha)

    candidate_sha = stable_sha256_v1(candidate)
    quarantine_records = sorted({item["registry_index"] for item in quarantine})
    result = _base_result()
    result.update(
        {
            "ok": True,
            "status": (
                "OFFLINE_RESIDUAL_REPAIR_PLAN_PARTIAL_QUARANTINE"
                if quarantine
                else "OFFLINE_RESIDUAL_REPAIR_PLAN_COMPLETE"
            ),
            "source_snapshot_sha256": source_sha,
            "candidate_snapshot_sha256": candidate_sha,
            "plan_sha256": "",
            "candidate_registry": candidate,
            "changed_paths": changed,
            "actions": actions,
            "quarantine": quarantine,
            "preservation_verified": True,
            "summary": {
                "residual_record_count": len(residual_indexes),
                "timestamp_aliases_archived": timestamp_archived,
                "status_aliases_archived": status_archived,
                "quarantined_conflict_count": len(quarantine),
                "quarantined_record_count": len(quarantine_records),
                "modified_record_count": len(
                    {item["registry_index"] for item in actions}
                ),
            },
            "reasons": [],
        }
    )
    plan_binding = {
        key: value
        for key, value in result.items()
        if key not in {"candidate_registry", "plan_sha256"}
    }
    result["plan_sha256"] = stable_sha256_v1(plan_binding)
    return result


_CONTRACT_DESCRIPTOR = {
    "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION,
    "offline_only": True,
    "default_off": True,
    "timestamp_rules": [
        "PREDATOR_EPOCH_SAME_MINUTE",
        "FALCON_SIGNAL_MINUTE_BOUNDARY",
        "CENTRAL_POSITION_MINUTE_BOUNDARY",
    ],
    "status_rule": "PRESERVE_CLOSED_ARCHIVE_CENTRAL_POSITION_STATUS",
    "unproven_policy": "QUARANTINE",
}
TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256 = (
    stable_sha256_v1(_CONTRACT_DESCRIPTOR)
)


__all__ = [
    "ResidualClosedIdentityRepairCapsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_REPAIR_OFFLINE_CONTRACT_V1_VERSION",
    "build_residual_closed_identity_repair_plan_v1",
    "normalize_residual_timestamp_v1",
    "stable_sha256_v1",
]
