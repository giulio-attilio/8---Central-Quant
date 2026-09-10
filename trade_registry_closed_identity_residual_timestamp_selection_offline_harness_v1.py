"""In-memory harness for factual selection of 32 quarantined timestamps."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_residual_repair_offline_contract_v1 as residual
import trade_registry_closed_identity_residual_repair_offline_harness_v1 as residual_harness
import trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1 as selection


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-RESIDUAL-TIMESTAMP-SELECTION-OFFLINE-HARNESS-V1"
)


def build_prior_residual_plan_v1() -> dict[str, Any]:
    snapshot = residual_harness.build_synthetic_residual_matrix_v1()
    return residual.build_residual_closed_identity_repair_plan_v1(
        snapshot,
        expected_snapshot_sha256=residual.stable_sha256_v1(snapshot),
    )


def build_synthetic_factual_evidence_bundle_v1(
    prior_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    candidate = prior_plan["candidate_registry"]
    candidate_sha = prior_plan["candidate_snapshot_sha256"]
    evidence_bundle = []
    for quarantine in prior_plan["quarantine"]:
        if quarantine.get("field") != "opened_at":
            continue
        index = quarantine["registry_index"]
        record = candidate["closed_trades"][index]
        identity = selection.residual_timestamp_identity_binding_v1(record)
        if identity["source"] == "falcon":
            kind = "FALCON_SIGNAL_EVENT_ATTESTATION_V1"
        elif identity["source"] == "predator_paper_registry_sync_fix_v1":
            kind = "PREDATOR_POSITION_EVENT_ATTESTATION_V1"
        else:
            kind = "CENTRAL_POSITION_EVENT_ATTESTATION_V1"
        selected = record["metadata"]["created_at"]
        evidence = {
            "registry_index": index,
            "candidate_record_sha256": residual.stable_sha256_v1(record),
            "record_binding_sha256": selection.residual_timestamp_record_binding_v1(
                candidate_snapshot_sha256=candidate_sha,
                registry_index=index,
                record=record,
            ),
            "identity": identity,
            "evidence_kind": kind,
            "selected_source_path": "trade.metadata.created_at",
            "selected_source_value": copy.deepcopy(selected),
            "selected_source_value_sha256": residual.stable_sha256_v1(selected),
            "independent_event_id": f"SYNTHETIC-EVENT-{index:04d}",
            "independent_source": "synthetic_source_event_ledger_v1",
            "independent_source_record_sha256": residual.stable_sha256_v1(
                {
                    "event_id": f"SYNTHETIC-EVENT-{index:04d}",
                    "identity": identity,
                    "factual_opened_at": selected,
                }
            ),
        }
        evidence["selection_attestation_sha256"] = (
            selection.residual_timestamp_selection_attestation_sha256_v1(
                evidence
            )
        )
        evidence_bundle.append(evidence)
    return evidence_bundle


def run_residual_timestamp_selection_offline_harness_v1() -> dict[str, Any]:
    prior = build_prior_residual_plan_v1()
    prior_copy = copy.deepcopy(prior)
    evidence = build_synthetic_factual_evidence_bundle_v1(prior)
    evidence_copy = copy.deepcopy(evidence)
    result = selection.build_residual_timestamp_selection_plan_v1(
        prior,
        evidence,
        expected_evidence_bundle_sha256=residual.stable_sha256_v1(evidence),
    )
    candidate = result.get("candidate_registry") or {}
    summary = result.get("summary") or {}
    checks = {
        "prior_unchanged": prior == prior_copy,
        "evidence_unchanged": evidence == evidence_copy,
        "input_quarantine_exact": summary.get("input_quarantined_record_count") == 32,
        "selected_exact": summary.get("selected_record_count") == 32,
        "remaining_quarantine_zero": summary.get("remaining_quarantined_record_count") == 0,
        "all_records_preserved": len(candidate.get("closed_trades") or []) == 42,
        "unrelated_root_preserved": candidate.get("extension") == prior["candidate_registry"]["extension"],
        "never_applicable": result.get("apply_allowed") is False,
        "no_runtime": result.get("runtime_activation_allowed") is False,
        "no_write": result.get("write_executed") is False,
        "no_broker": result.get("broker_called") is False,
        "preservation_verified": result.get("preservation_verified") is True,
    }
    return {
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_VERSION,
        "ok": bool(result.get("ok") and all(checks.values())),
        "checks": checks,
        "selection_plan": result,
    }


TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_SHA256 = (
    residual.stable_sha256_v1(
        {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_VERSION,
            "quarantined_input": 32,
            "synthetic_attestations": 32,
            "expected_remaining_quarantine": 0,
        }
    )
)


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_SHA256",
    "TRADE_REGISTRY_CLOSED_IDENTITY_RESIDUAL_TIMESTAMP_SELECTION_OFFLINE_HARNESS_V1_VERSION",
    "build_prior_residual_plan_v1",
    "build_synthetic_factual_evidence_bundle_v1",
    "run_residual_timestamp_selection_offline_harness_v1",
]
