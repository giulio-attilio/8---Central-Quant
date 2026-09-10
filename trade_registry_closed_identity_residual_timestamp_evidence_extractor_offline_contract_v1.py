"""Offline extractor for independently corroborated residual timestamps.

The source JSONL is injected as text.  The contract never opens a file and
never imports runtime code.  One attestation requires two distinct source
records: an opening event and a closing event with the exact trade_id and the
same factual creation instant.  Anything else remains unresolved.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1 as selection


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-TIMESTAMP-EVIDENCE-EXTRACTOR-OFFLINE-CONTRACT-V1"
)

_SOURCE_NAME = "history_events.jsonl"
_TIMESTAMP_KEYS = frozenset(
    {
        "created_at",
        "opened_at",
        "entry_time",
        "open_time",
        "timestamp",
        "ts",
        "datetime",
        "signal_ts",
        "event_time",
        "time",
        "occurred_at",
    }
)
_SEMANTIC_KEYS = frozenset(
    {"event", "event_type", "type", "action", "status", "state", "reason"}
)
_OPEN_TOKENS = frozenset(
    {
        "OPEN",
        "OPENED",
        "ENTRY",
        "ENTERED",
        "CREATE",
        "CREATED",
        "REGISTER",
        "REGISTERED",
        "ABERTURA",
        "ABERTO",
        "ABERTA",
        "ENTRADA",
    }
)
_CLOSE_TOKENS = frozenset(
    {
        "CLOSE",
        "CLOSED",
        "EXIT",
        "EXITED",
        "FECHAMENTO",
        "FECHADO",
        "FECHADA",
        "SAIDA",
    }
)
_TOKEN_RE = re.compile(r"[A-Z0-9]+")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class ResidualTimestampEvidenceExtractorCapsV1:
    max_source_bytes: int = 2_000_000
    max_lines: int = 10_000
    max_json_depth: int = 10
    max_leaf_nodes_per_line: int = 4_000
    max_targets: int = 32


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _base_result() -> dict[str, Any]:
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_VERSION,
        "ok": False,
        "status": "OFFLINE_TIMESTAMP_EVIDENCE_EXTRACTION_BLOCKED",
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
        "evidence": [],
        "unresolved": [],
        "reasons": [],
    }


def _blocked(reason: str) -> dict[str, Any]:
    result = _base_result()
    result["reasons"] = [reason]
    return result


def _leaf_name(path: str) -> str:
    return path.rsplit(".", 1)[-1].replace("[]", "").lower()


def _flatten(
    value: Any,
    *,
    max_depth: int,
    max_nodes: int,
) -> tuple[list[tuple[str, Any]], bool]:
    output: list[tuple[str, Any]] = []
    exceeded = False

    def visit(item: Any, path: str, depth: int) -> None:
        nonlocal exceeded
        if exceeded:
            return
        if depth > max_depth:
            exceeded = True
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                next_path = f"{path}.{key}" if path else str(key)
                visit(child, next_path, depth + 1)
                if exceeded:
                    return
        elif isinstance(item, list):
            for child in item:
                visit(child, f"{path}[]", depth + 1)
                if exceeded:
                    return
        else:
            output.append((path, item))
            if len(output) > max_nodes:
                exceeded = True

    visit(value, "", 0)
    return output, exceeded


def _line_event(
    line: str,
    *,
    line_number: int,
    caps: ResidualTimestampEvidenceExtractorCapsV1,
) -> tuple[dict[str, Any] | None, str]:
    try:
        payload = json.loads(line)
    except (TypeError, ValueError):
        return None, "SOURCE_JSONL_MALFORMED_LINE"
    if not isinstance(payload, (dict, list)):
        return None, "SOURCE_JSONL_NON_CONTAINER_LINE"
    leaves, exceeded = _flatten(
        payload,
        max_depth=caps.max_json_depth,
        max_nodes=caps.max_leaf_nodes_per_line,
    )
    if exceeded:
        return None, "SOURCE_JSONL_LINE_COMPLEXITY_EXCEEDED"
    trade_ids = {
        str(value or "").strip()
        for path, value in leaves
        if _leaf_name(path) == "trade_id" and value not in (None, "")
    }
    timestamp_values: list[tuple[str, str]] = []
    for path, value in leaves:
        if _leaf_name(path) not in _TIMESTAMP_KEYS:
            continue
        normalized = residual.normalize_residual_timestamp_v1(value)
        if normalized:
            timestamp_values.append((path, normalized))
    semantic_tokens: set[str] = set()
    for path, value in leaves:
        if _leaf_name(path) in _SEMANTIC_KEYS:
            semantic_tokens.update(_TOKEN_RE.findall(str(value or "").upper()))
    try:
        canonical_line = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None, "SOURCE_JSONL_NON_CANONICAL_VALUE"
    return {
        "line_number": line_number,
        "line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
        "canonical_payload_sha256": hashlib.sha256(
            canonical_line.encode("utf-8")
        ).hexdigest(),
        "trade_ids": trade_ids,
        "timestamps": timestamp_values,
        "is_open": bool(semantic_tokens & _OPEN_TOKENS),
        "is_close": bool(semantic_tokens & _CLOSE_TOKENS),
    }, ""


def _eligible_turtle(record: Mapping[str, Any]) -> bool:
    identity = selection.residual_timestamp_identity_binding_v1(record)
    return bool(
        identity["bot"] == "TURTLE"
        and identity["source"] == "main_traderegistry_sync"
        and identity["synced_from"] == "central_open_positions"
        and identity["status"] == "CLOSED"
    )


def _valid_caps(caps: ResidualTimestampEvidenceExtractorCapsV1) -> bool:
    return all(
        not isinstance(value, bool) and isinstance(value, int) and value > 0
        for value in (
            caps.max_source_bytes,
            caps.max_lines,
            caps.max_json_depth,
            caps.max_leaf_nodes_per_line,
            caps.max_targets,
        )
    )


def extract_residual_timestamp_evidence_v1(
    prior_residual_plan: Mapping[str, Any],
    source_jsonl: str,
    *,
    expected_source_sha256: str,
    source_name: str = _SOURCE_NAME,
    caps: ResidualTimestampEvidenceExtractorCapsV1 | None = None,
) -> dict[str, Any]:
    """Extract verified evidence from injected JSONL without reading storage."""

    caps = caps or ResidualTimestampEvidenceExtractorCapsV1()
    if not _valid_caps(caps):
        return _blocked("INVALID_EXTRACTOR_CAPS")
    if source_name != _SOURCE_NAME:
        return _blocked("SOURCE_NAME_NOT_ALLOWED")
    if not isinstance(source_jsonl, str):
        return _blocked("SOURCE_JSONL_NOT_TEXT")
    source_bytes = source_jsonl.encode("utf-8")
    if len(source_bytes) > caps.max_source_bytes:
        return _blocked("SOURCE_BYTE_CAP_EXCEEDED")
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    if source_sha != _valid_sha256(expected_source_sha256):
        return _blocked("SOURCE_SHA256_MISMATCH")

    empty_evidence_sha = residual.stable_sha256_v1([])
    prior_probe = selection.build_residual_timestamp_selection_plan_v1(
        prior_residual_plan,
        [],
        expected_evidence_bundle_sha256=empty_evidence_sha,
    )
    if prior_probe.get("ok") is not True:
        result = _blocked("PRIOR_RESIDUAL_PLAN_INVALID")
        result["prior_plan_reasons"] = list(prior_probe.get("reasons") or [])
        return result
    candidate = prior_probe.get("candidate_registry")
    closed = candidate.get("closed_trades") if isinstance(candidate, Mapping) else None
    if not isinstance(closed, list):
        return _blocked("PRIOR_CANDIDATE_CLOSED_TRADES_INVALID")
    target_indexes = [
        item.get("registry_index")
        for item in prior_probe.get("quarantine") or []
        if isinstance(item, Mapping) and item.get("field") == "opened_at"
    ]
    if len(target_indexes) > caps.max_targets:
        return _blocked("TARGET_CAP_EXCEEDED")

    raw_lines = source_jsonl.splitlines()
    if len(raw_lines) > caps.max_lines:
        return _blocked("SOURCE_LINE_CAP_EXCEEDED")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw_lines, 1):
        if not line.strip():
            continue
        event, reason = _line_event(line, line_number=line_number, caps=caps)
        if reason:
            result = _blocked(reason)
            result["blocked_line_number"] = line_number
            return result
        events.append(event or {})

    evidence_bundle: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    candidate_sha = str(prior_probe.get("source_snapshot_sha256") or "")
    for index in target_indexes:
        record = closed[index]
        record_sha = residual.stable_sha256_v1(record)
        binding = selection.residual_timestamp_record_binding_v1(
            candidate_snapshot_sha256=candidate_sha,
            registry_index=index,
            record=record,
        )
        if not _eligible_turtle(record):
            unresolved.append(
                {
                    "registry_index": index,
                    "record_binding_sha256": binding,
                    "reason": "TARGET_PROVENANCE_NOT_SUPPORTED_BY_TURTLE_EXTRACTOR",
                }
            )
            continue
        metadata = record.get("metadata")
        selected_value = (
            metadata.get("created_at") if isinstance(metadata, Mapping) else None
        )
        selected_timestamp = residual.normalize_residual_timestamp_v1(
            selected_value
        )
        if not selected_timestamp:
            unresolved.append(
                {
                    "registry_index": index,
                    "record_binding_sha256": binding,
                    "reason": "TARGET_METADATA_TIMESTAMP_INVALID",
                }
            )
            continue
        trade_id = str(record.get("trade_id") or "").strip()
        matches = [
            event
            for event in events
            if trade_id
            and trade_id in event["trade_ids"]
            and any(
                timestamp == selected_timestamp
                for _path, timestamp in event["timestamps"]
            )
        ]
        open_events = [event for event in matches if event["is_open"]]
        close_events = [event for event in matches if event["is_close"]]
        pair = next(
            (
                (opened, closed_event)
                for opened in open_events
                for closed_event in close_events
                if opened["line_number"] != closed_event["line_number"]
                and opened["line_sha256"] != closed_event["line_sha256"]
            ),
            None,
        )
        if pair is None:
            unresolved.append(
                {
                    "registry_index": index,
                    "record_binding_sha256": binding,
                    "reason": "DISTINCT_OPEN_CLOSE_EVENT_CHAIN_NOT_PROVEN",
                    "matching_open_event_count": len(open_events),
                    "matching_close_event_count": len(close_events),
                }
            )
            continue
        opened, closed_event = pair
        chain_hashes = sorted(
            {event["line_sha256"] for event in matches}
        )
        evidence = {
            "registry_index": index,
            "candidate_record_sha256": record_sha,
            "record_binding_sha256": binding,
            "identity": selection.residual_timestamp_identity_binding_v1(
                record
            ),
            "evidence_kind": "CENTRAL_POSITION_EVENT_ATTESTATION_V1",
            "selected_source_path": "trade.metadata.created_at",
            "selected_source_value": selected_value,
            "selected_source_value_sha256": residual.stable_sha256_v1(
                selected_value
            ),
            "independent_event_id": (
                "HISTORY-EVENT-" + opened["line_sha256"][:32].upper()
            ),
            "independent_source": _SOURCE_NAME,
            "independent_source_sha256": source_sha,
            "independent_source_record_sha256": opened["line_sha256"],
            "corroborating_close_record_sha256": closed_event[
                "line_sha256"
            ],
            "source_event_chain_sha256": residual.stable_sha256_v1(
                chain_hashes
            ),
            "source_event_record_count": len(chain_hashes),
            "open_event_canonical_payload_sha256": opened[
                "canonical_payload_sha256"
            ],
            "close_event_canonical_payload_sha256": closed_event[
                "canonical_payload_sha256"
            ],
        }
        evidence["selection_attestation_sha256"] = (
            selection.residual_timestamp_selection_attestation_sha256_v1(
                evidence
            )
        )
        evidence_bundle.append(evidence)

    evidence_bundle.sort(key=lambda item: item["registry_index"])
    unresolved.sort(key=lambda item: item["registry_index"])
    result = _base_result()
    result.update(
        {
            "ok": True,
            "status": (
                "OFFLINE_TIMESTAMP_EVIDENCE_PARTIAL"
                if unresolved
                else "OFFLINE_TIMESTAMP_EVIDENCE_COMPLETE"
            ),
            "source_name": _SOURCE_NAME,
            "source_sha256": source_sha,
            "source_line_count": len(raw_lines),
            "parsed_event_count": len(events),
            "prior_plan_sha256": prior_residual_plan.get("plan_sha256"),
            "candidate_snapshot_sha256": candidate_sha,
            "evidence": evidence_bundle,
            "evidence_bundle_sha256": residual.stable_sha256_v1(
                evidence_bundle
            ),
            "unresolved": unresolved,
            "summary": {
                "target_count": len(target_indexes),
                "eligible_turtle_target_count": sum(
                    _eligible_turtle(closed[index]) for index in target_indexes
                ),
                "attested_record_count": len(evidence_bundle),
                "unresolved_record_count": len(unresolved),
            },
            "reasons": [],
        }
    )
    result["extractor_receipt_sha256"] = residual.stable_sha256_v1(
        {
            key: value
            for key, value in result.items()
            if key not in {"evidence", "extractor_receipt_sha256"}
        }
    )
    return result


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_VERSION,
            "source": _SOURCE_NAME,
            "required_chain": [
                "EXACT_TRADE_ID",
                "EXACT_FACTUAL_TIMESTAMP",
                "DISTINCT_OPEN_EVENT",
                "DISTINCT_CLOSE_EVENT",
                "SOURCE_AND_RECORD_SHA256",
            ],
            "unproved_policy": "NO_ATTESTATION",
        }
    )
)


__all__ = [
    "ResidualTimestampEvidenceExtractorCapsV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_CONTRACT_V1_VERSION",
    "extract_residual_timestamp_evidence_v1",
]
