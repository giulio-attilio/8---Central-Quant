"""Dormant factual timestamp selection for quarantined CLOSED records.

Only injected in-memory documents are accepted.  A timestamp is selected only
when an independent attestation is bound to the exact candidate snapshot,
record, identity, provenance, source value, and source event.  Unproved records
remain unchanged and quarantined.  This module cannot apply its candidate.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-TIMESTAMP-SELECTION-OFFLINE-CONTRACT-V1"
)

_ARCHIVE_KEY = "c3_residual_timestamp_selection_v1"
_ALLOWED_SOURCE_PATHS = frozenset(
    {"trade.opened_at", "trade.metadata.created_at"}
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ResidualTimestampSelectionCapsV1:
    max_quarantined_records: int = 32
    max_evidence_records: int = 32


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _base_result() -> dict[str, Any]:
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_VERSION,
        "ok": False,
        "status": "OFFLINE_TIMESTAMP_SELECTION_BLOCKED",
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
        "actions": [],
        "quarantine": [],
        "changed_paths": [],
        "reasons": [],
    }


def _blocked(reason: str) -> dict[str, Any]:
    result = _base_result()
    result["reasons"] = [reason]
    return result


def _prior_plan_binding(prior_plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in prior_plan.items()
        if key not in {"candidate_registry", "plan_sha256"}
    }


def _identity_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return {
        "trade_id": _text(record.get("trade_id")),
        "bot": _upper(record.get("bot") or metadata.get("bot")),
        "setup": _upper(record.get("setup") or metadata.get("setup")),
        "symbol": _upper(record.get("symbol") or metadata.get("symbol")),
        "side": _upper(record.get("side") or metadata.get("side")),
        "status": _upper(record.get("status")),
        "source": _text(record.get("source") or metadata.get("source")),
        "synced_from": _text(metadata.get("synced_from")),
    }


def residual_timestamp_identity_binding_v1(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose the exact sanitized identity used by selection attestations."""

    return _identity_binding(record)


def residual_timestamp_record_binding_v1(
    *,
    candidate_snapshot_sha256: str,
    registry_index: int,
    record: Mapping[str, Any],
) -> str:
    return residual.stable_sha256_v1(
        {
            "candidate_snapshot_sha256": candidate_snapshot_sha256,
            "registry_index": registry_index,
            "record_sha256": residual.stable_sha256_v1(record),
            "identity": _identity_binding(record),
        }
    )


def residual_timestamp_selection_attestation_sha256_v1(
    evidence: Mapping[str, Any],
) -> str:
    payload = {
        key: value
        for key, value in evidence.items()
        if key != "selection_attestation_sha256"
    }
    return residual.stable_sha256_v1(payload)


def _read_source(record: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    if path == "trade.opened_at":
        return ("opened_at" in record), record.get("opened_at")
    if path == "trade.metadata.created_at":
        metadata = record.get("metadata")
        if isinstance(metadata, Mapping) and "created_at" in metadata:
            return True, metadata.get("created_at")
    return False, None


def _expected_evidence_kind(record: Mapping[str, Any]) -> str:
    identity = _identity_binding(record)
    if (
        identity["source"] == "main_traderegistry_sync"
        and identity["synced_from"] == "central_open_positions"
    ):
        return "CENTRAL_POSITION_EVENT_ATTESTATION_V1"
    if identity["source"] == "falcon" and identity["bot"] == "FALCON":
        return "FALCON_SIGNAL_EVENT_ATTESTATION_V1"
    if (
        identity["source"] == "predator_paper_registry_sync_fix_v1"
        and identity["synced_from"] == "predator_module_open_positions"
        and identity["bot"] == "PREDATOR"
    ):
        return "PREDATOR_POSITION_EVENT_ATTESTATION_V1"
    return ""


def _evidence_reason(
    evidence: Mapping[str, Any],
    *,
    record: Mapping[str, Any],
    registry_index: int,
    candidate_snapshot_sha256: str,
) -> str:
    if evidence.get("registry_index") != registry_index:
        return "EVIDENCE_REGISTRY_INDEX_MISMATCH"
    record_sha = residual.stable_sha256_v1(record)
    if _valid_sha256(evidence.get("candidate_record_sha256")) != record_sha:
        return "EVIDENCE_RECORD_SHA256_MISMATCH"
    expected_binding = residual_timestamp_record_binding_v1(
        candidate_snapshot_sha256=candidate_snapshot_sha256,
        registry_index=registry_index,
        record=record,
    )
    if _valid_sha256(evidence.get("record_binding_sha256")) != expected_binding:
        return "EVIDENCE_RECORD_BINDING_MISMATCH"
    if evidence.get("identity") != _identity_binding(record):
        return "EVIDENCE_IDENTITY_MISMATCH"
    expected_kind = _expected_evidence_kind(record)
    if not expected_kind or _text(evidence.get("evidence_kind")) != expected_kind:
        return "EVIDENCE_PROVENANCE_KIND_MISMATCH"
    source_path = _text(evidence.get("selected_source_path"))
    if source_path not in _ALLOWED_SOURCE_PATHS:
        return "EVIDENCE_SOURCE_PATH_NOT_ALLOWED"
    exists, source_value = _read_source(record, source_path)
    if not exists or evidence.get("selected_source_value") != source_value:
        return "EVIDENCE_SOURCE_VALUE_MISMATCH"
    if _valid_sha256(evidence.get("selected_source_value_sha256")) != residual.stable_sha256_v1(
        source_value
    ):
        return "EVIDENCE_SOURCE_VALUE_SHA256_MISMATCH"
    if not residual.normalize_residual_timestamp_v1(source_value):
        return "EVIDENCE_SELECTED_TIMESTAMP_INVALID"
    if not _text(evidence.get("independent_event_id")):
        return "EVIDENCE_INDEPENDENT_EVENT_ID_MISSING"
    if not _text(evidence.get("independent_source")):
        return "EVIDENCE_INDEPENDENT_SOURCE_MISSING"
    if not _valid_sha256(evidence.get("independent_source_record_sha256")):
        return "EVIDENCE_INDEPENDENT_SOURCE_RECORD_SHA256_INVALID"
    expected_attestation = residual_timestamp_selection_attestation_sha256_v1(
        evidence
    )
    if _valid_sha256(evidence.get("selection_attestation_sha256")) != expected_attestation:
        return "EVIDENCE_ATTESTATION_SHA256_MISMATCH"
    return ""


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


def _authorized_path(path: str) -> bool:
    return bool(
        re.fullmatch(
            rf"closed_trades\[\d+\]\.(?:opened_at|metadata\.(?:created_at|{_ARCHIVE_KEY}(?:\..+)?))",
            path,
        )
    )


def build_residual_timestamp_selection_plan_v1(
    prior_residual_plan: Mapping[str, Any],
    evidence_bundle: Sequence[Mapping[str, Any]],
    *,
    expected_evidence_bundle_sha256: str,
    caps: ResidualTimestampSelectionCapsV1 | None = None,
) -> dict[str, Any]:
    """Build a non-applicable candidate and quarantine every unproved record."""

    caps = caps or ResidualTimestampSelectionCapsV1()
    if (
        isinstance(caps.max_quarantined_records, bool)
        or not isinstance(caps.max_quarantined_records, int)
        or caps.max_quarantined_records <= 0
        or isinstance(caps.max_evidence_records, bool)
        or not isinstance(caps.max_evidence_records, int)
        or caps.max_evidence_records <= 0
    ):
        return _blocked("INVALID_SELECTION_CAPS")
    if not isinstance(prior_residual_plan, Mapping):
        return _blocked("PRIOR_PLAN_NOT_MAPPING")
    if prior_residual_plan.get("ok") is not True:
        return _blocked("PRIOR_PLAN_NOT_OK")
    if prior_residual_plan.get("apply_allowed") is not False:
        return _blocked("PRIOR_PLAN_NOT_DEFAULT_OFF")
    if prior_residual_plan.get("runtime_activation_allowed") is not False:
        return _blocked("PRIOR_PLAN_RUNTIME_ALLOWED")
    prior_plan_sha = _valid_sha256(prior_residual_plan.get("plan_sha256"))
    if prior_plan_sha != residual.stable_sha256_v1(
        _prior_plan_binding(prior_residual_plan)
    ):
        return _blocked("PRIOR_PLAN_SHA256_MISMATCH")
    candidate = prior_residual_plan.get("candidate_registry")
    if not isinstance(candidate, Mapping):
        return _blocked("PRIOR_CANDIDATE_NOT_MAPPING")
    try:
        source = _copy(candidate)
        source_sha = residual.stable_sha256_v1(source)
    except (TypeError, ValueError):
        return _blocked("PRIOR_CANDIDATE_NOT_CANONICAL_JSON")
    if source_sha != _valid_sha256(
        prior_residual_plan.get("candidate_snapshot_sha256")
    ):
        return _blocked("PRIOR_CANDIDATE_SHA256_MISMATCH")
    closed = source.get("closed_trades")
    if not isinstance(closed, list) or any(not isinstance(row, dict) for row in closed):
        return _blocked("PRIOR_CANDIDATE_CLOSED_TRADES_INVALID")

    prior_quarantine = prior_residual_plan.get("quarantine")
    if not isinstance(prior_quarantine, list):
        return _blocked("PRIOR_QUARANTINE_NOT_LIST")
    timestamp_indexes = [
        item.get("registry_index")
        for item in prior_quarantine
        if isinstance(item, Mapping) and item.get("field") == "opened_at"
    ]
    if (
        any(isinstance(index, bool) or not isinstance(index, int) for index in timestamp_indexes)
        or len(timestamp_indexes) != len(set(timestamp_indexes))
        or len(timestamp_indexes) > caps.max_quarantined_records
        or any(index < 0 or index >= len(closed) for index in timestamp_indexes)
    ):
        return _blocked("PRIOR_TIMESTAMP_QUARANTINE_INVALID")
    if isinstance(evidence_bundle, (str, bytes)) or not isinstance(
        evidence_bundle, Sequence
    ):
        return _blocked("EVIDENCE_BUNDLE_NOT_SEQUENCE")
    if len(evidence_bundle) > caps.max_evidence_records:
        return _blocked("EVIDENCE_RECORD_CAP_EXCEEDED")
    if any(not isinstance(item, Mapping) for item in evidence_bundle):
        return _blocked("EVIDENCE_RECORD_NOT_MAPPING")
    try:
        evidence_copy = _copy(list(evidence_bundle))
        evidence_sha = residual.stable_sha256_v1(evidence_copy)
    except (TypeError, ValueError):
        return _blocked("EVIDENCE_BUNDLE_NOT_CANONICAL_JSON")
    if evidence_sha != _valid_sha256(expected_evidence_bundle_sha256):
        return _blocked("EVIDENCE_BUNDLE_SHA256_MISMATCH")

    evidence_by_index: dict[int, Mapping[str, Any]] = {}
    event_ids: set[str] = set()
    for evidence in evidence_copy:
        index = evidence.get("registry_index")
        if isinstance(index, bool) or not isinstance(index, int):
            return _blocked("EVIDENCE_REGISTRY_INDEX_INVALID")
        if index in evidence_by_index:
            return _blocked("DUPLICATE_EVIDENCE_REGISTRY_INDEX")
        event_id = _text(evidence.get("independent_event_id"))
        if event_id and event_id in event_ids:
            return _blocked("DUPLICATE_INDEPENDENT_EVENT_ID")
        if event_id:
            event_ids.add(event_id)
        evidence_by_index[index] = evidence

    output = _copy(source)
    actions: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    for index in timestamp_indexes:
        record = closed[index]
        current = output["closed_trades"][index]
        metadata = current.get("metadata")
        if not isinstance(metadata, dict):
            return _blocked("CANDIDATE_METADATA_INVALID")
        if _ARCHIVE_KEY in metadata:
            return _blocked("PREEXISTING_TIMESTAMP_SELECTION_ARCHIVE")
        evidence = evidence_by_index.get(index)
        if evidence is None:
            quarantine.append(
                {
                    "registry_index": index,
                    "record_sha256": residual.stable_sha256_v1(record),
                    "field": "opened_at",
                    "reason": "FACTUAL_TIMESTAMP_EVIDENCE_MISSING",
                }
            )
            continue
        reason = _evidence_reason(
            evidence,
            record=record,
            registry_index=index,
            candidate_snapshot_sha256=source_sha,
        )
        if reason:
            quarantine.append(
                {
                    "registry_index": index,
                    "record_sha256": residual.stable_sha256_v1(record),
                    "field": "opened_at",
                    "reason": reason,
                }
            )
            continue

        source_path = _text(evidence.get("selected_source_path"))
        _, selected_raw = _read_source(record, source_path)
        normalized = residual.normalize_residual_timestamp_v1(selected_raw)
        original_opened = _copy(record.get("opened_at"))
        original_created = _copy(record["metadata"].get("created_at"))
        metadata[_ARCHIVE_KEY] = {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_VERSION,
            "prior_plan_sha256": prior_plan_sha,
            "record_binding_sha256": evidence["record_binding_sha256"],
            "selection_attestation_sha256": evidence[
                "selection_attestation_sha256"
            ],
            "selected_source_path": source_path,
            "selected_opened_at_utc": normalized,
            "original_opened_at": original_opened,
            "original_opened_at_sha256": residual.stable_sha256_v1(
                original_opened
            ),
            "original_metadata_created_at": original_created,
            "original_metadata_created_at_sha256": residual.stable_sha256_v1(
                original_created
            ),
            "independent_event_id": evidence["independent_event_id"],
            "independent_source": evidence["independent_source"],
            "independent_source_record_sha256": evidence[
                "independent_source_record_sha256"
            ],
        }
        current["opened_at"] = normalized
        del metadata["created_at"]
        actions.append(
            {
                "registry_index": index,
                "record_sha256": residual.stable_sha256_v1(record),
                "field": "opened_at",
                "action": "SELECT_ATTESTED_TIMESTAMP_ARCHIVE_BOTH_ALIASES",
                "selected_source_path": source_path,
                "record_binding_sha256": evidence["record_binding_sha256"],
            }
        )

    unexpected_evidence = sorted(set(evidence_by_index) - set(timestamp_indexes))
    if unexpected_evidence:
        return _blocked("EVIDENCE_TARGET_NOT_QUARANTINED")
    changed = sorted(_changed_leaf_paths(source, output))
    if any(not _authorized_path(path) for path in changed):
        return _blocked("TIMESTAMP_CANDIDATE_CHANGED_UNAUTHORIZED_PATH")

    for action in actions:
        index = action["registry_index"]
        before = closed[index]
        archive = output["closed_trades"][index]["metadata"][_ARCHIVE_KEY]
        if (
            archive["original_opened_at"] != before.get("opened_at")
            or archive["original_metadata_created_at"]
            != before["metadata"].get("created_at")
            or archive["original_opened_at_sha256"]
            != residual.stable_sha256_v1(before.get("opened_at"))
            or archive["original_metadata_created_at_sha256"]
            != residual.stable_sha256_v1(before["metadata"].get("created_at"))
        ):
            return _blocked("TIMESTAMP_ARCHIVE_PRESERVATION_FAILED")

    result = _base_result()
    result.update(
        {
            "ok": True,
            "status": (
                "OFFLINE_TIMESTAMP_SELECTION_PARTIAL_QUARANTINE"
                if quarantine
                else "OFFLINE_TIMESTAMP_SELECTION_COMPLETE"
            ),
            "prior_plan_sha256": prior_plan_sha,
            "source_snapshot_sha256": source_sha,
            "evidence_bundle_sha256": evidence_sha,
            "candidate_snapshot_sha256": residual.stable_sha256_v1(output),
            "candidate_registry": output,
            "actions": actions,
            "quarantine": quarantine,
            "changed_paths": changed,
            "preservation_verified": True,
            "summary": {
                "input_quarantined_record_count": len(timestamp_indexes),
                "selected_record_count": len(actions),
                "remaining_quarantined_record_count": len(quarantine),
                "evidence_record_count": len(evidence_copy),
            },
            "reasons": [],
        }
    )
    result["selection_plan_sha256"] = residual.stable_sha256_v1(
        {
            key: value
            for key, value in result.items()
            if key not in {"candidate_registry", "selection_plan_sha256"}
        }
    )
    return result


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_VERSION,
            "default_off": True,
            "binding": [
                "candidate_snapshot_sha256",
                "candidate_record_sha256",
                "record_binding_sha256",
                "selection_attestation_sha256",
                "independent_source_record_sha256",
            ],
            "unproved_policy": "QUARANTINE_UNCHANGED",
        }
    )
)


__all__ = [
    "ResidualTimestampSelectionCapsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_CONTRACT_V1_VERSION",
    "build_residual_timestamp_selection_plan_v1",
    "residual_timestamp_identity_binding_v1",
    "residual_timestamp_record_binding_v1",
    "residual_timestamp_selection_attestation_sha256_v1",
]
