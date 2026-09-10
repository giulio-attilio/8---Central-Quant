"""Synthetic harness for the offline Turtle history evidence extractor."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_contract_v1 as extractor
import trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1 as selection
import trade_registry_closed_identity_residual_timestamp_selection_offline_harness_v1 as selection_harness


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-TIMESTAMP-EVIDENCE-EXTRACTOR-OFFLINE-HARNESS-V1"
)


def build_synthetic_history_jsonl_v1(
    prior_plan: dict[str, Any],
) -> tuple[str, list[int]]:
    candidate = prior_plan["candidate_registry"]
    turtle_indexes = [
        item["registry_index"]
        for item in prior_plan["quarantine"]
        if item.get("field") == "opened_at"
        and selection.residual_timestamp_identity_binding_v1(
            candidate["closed_trades"][item["registry_index"]]
        )["bot"]
        == "TURTLE"
    ][:10]
    lines = [
        {
            "event": "UNRELATED_HEALTH_EVENT",
            "ts": "2026-09-06T00:00:00+00:00",
            "details": {"trade_id": "UNRELATED"},
        }
    ]
    for index in turtle_indexes:
        record = candidate["closed_trades"][index]
        created_at = record["metadata"]["created_at"]
        trade_id = record["trade_id"]
        lines.extend(
            [
                {
                    "event": "TRADE_OPENED",
                    "ts": created_at,
                    "trade_id": trade_id,
                    "raw": {
                        "created_at": created_at,
                        "trade_id": trade_id,
                        "bot": "TURTLE",
                    },
                },
                {
                    "event": "TRADE_CLOSED",
                    "ts": "2026-09-06T01:00:00+00:00",
                    "trade_id": trade_id,
                    "raw": {
                        "created_at": created_at,
                        "trade_id": trade_id,
                        "bot": "TURTLE",
                    },
                },
            ]
        )
    text = "\n".join(
        json.dumps(line, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for line in lines
    )
    return text, turtle_indexes


def run_residual_timestamp_evidence_extractor_offline_harness_v1() -> dict[str, Any]:
    prior = selection_harness.build_prior_residual_plan_v1()
    prior_copy = copy.deepcopy(prior)
    source, attested_indexes = build_synthetic_history_jsonl_v1(prior)
    result = extractor.extract_residual_timestamp_evidence_v1(
        prior,
        source,
        expected_source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
    )
    selection_result = selection.build_residual_timestamp_selection_plan_v1(
        prior,
        result.get("evidence") or [],
        expected_evidence_bundle_sha256=result.get("evidence_bundle_sha256")
        or residual.stable_sha256_v1([]),
    )
    checks = {
        "prior_unchanged": prior == prior_copy,
        "ten_attestations": result.get("summary", {}).get("attested_record_count") == 10,
        "twenty_two_unresolved": result.get("summary", {}).get("unresolved_record_count") == 22,
        "attested_indexes_exact": [item["registry_index"] for item in result.get("evidence") or []] == attested_indexes,
        "selection_accepts_ten": selection_result.get("summary", {}).get("selected_record_count") == 10,
        "selection_keeps_twenty_two": selection_result.get("summary", {}).get("remaining_quarantined_record_count") == 22,
        "extractor_never_applies": result.get("apply_allowed") is False,
        "selection_never_applies": selection_result.get("apply_allowed") is False,
        "no_runtime": result.get("runtime_activation_allowed") is False,
        "no_write": result.get("write_executed") is False,
        "no_broker": result.get("broker_called") is False,
    }
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_VERSION,
        "ok": bool(result.get("ok") and selection_result.get("ok") and all(checks.values())),
        "checks": checks,
        "extraction": result,
        "selection": selection_result,
    }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_VERSION,
            "synthetic_attestations": 10,
            "expected_unresolved": 22,
            "source": "INJECTED_JSONL_TEXT",
        }
    )
)


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_EVIDENCE_EXTRACTOR_OFFLINE_HARNESS_V1_VERSION",
    "build_synthetic_history_jsonl_v1",
    "run_residual_timestamp_evidence_extractor_offline_harness_v1",
]
