"""Synthetic harness for the dormant raw composition V2 contract."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_composition_contract_v2 as composition
import trade_registry_closed_identity_conflict_repair_raw_path_binding_contract_v1 as raw_binding
import trade_registry_closed_identity_conflict_repair_raw_path_binding_harness_v1 as raw_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_HARNESS_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-COMPOSITION-HARNESS-V2"
)


_PLAN_PRECONDITIONS = [
    "PLAN_IS_NOT_AN_APPLY_COMMAND",
    "PRESERVE_COMPLETE_PRE_REPAIR_BACKUP",
    "RELOAD_REGISTRY_BEFORE_ANY_FUTURE_WRITE",
    "REQUIRE_IDENTICAL_INPUT_MANIFEST_SHA256",
    "REQUIRE_EVERY_RECORD_FINGERPRINT_UNCHANGED",
    "REQUIRE_SEPARATE_PRODUCTION_REVIEW_AND_AUTHORIZATION",
]


def _source_plan(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    legacy_count = sum(
        item.get("proposal_type") == "LEGACY_ALIAS_CANONICALIZATION"
        for item in proposals
    )
    financial_count = sum(
        item.get("proposal_type") == "FINANCIAL_OUTCOME_CANONICALIZATION"
        for item in proposals
    )
    fingerprints = sorted(item["record_fingerprint"] for item in proposals)
    manifest = {
        "legacy_conflict_sha256": sorted(
            item["conflict_sha256"]
            for item in proposals
            if item["proposal_type"] == "LEGACY_ALIAS_CANONICALIZATION"
        ),
        "financial_conflict_sha256": sorted(
            item["conflict_sha256"]
            for item in proposals
            if item["proposal_type"] == "FINANCIAL_OUTCOME_CANONICALIZATION"
        ),
        "record_fingerprints": fingerprints,
    }
    plan = {
        "proposal_count": len(proposals),
        "legacy_proposal_count": legacy_count,
        "financial_proposal_count": financial_count,
        "proposals": proposals,
        "preservation": {
            "input_record_count": len(proposals),
            "preserved_record_count": len(proposals),
            "removed_record_count": 0,
            "mutated_record_count": 0,
            "record_fingerprints": fingerprints,
            "input_manifest_sha256": composition._stable_sha256(manifest),
        },
        "preconditions": list(_PLAN_PRECONDITIONS),
    }
    plan["plan_sha256"] = composition.planner_plan_sha256_v2(plan)
    return plan


def _reseal_inventory_for_plan(
    inventory: dict[str, Any], plan: dict[str, Any], binding_plan: dict[str, Any]
) -> None:
    old_by_type = {
        item["proposal_type"]: item for item in inventory["bindings"]
    }
    rebuilt = []
    for ordinal, proposal in enumerate(plan["proposals"]):
        item = copy.deepcopy(old_by_type[proposal["proposal_type"]])
        item["proposal_ordinal"] = ordinal
        item["proposal_sha256"] = composition._stable_sha256(proposal)
        item["record_fingerprint"] = proposal["record_fingerprint"]
        item["conflict_sha256"] = proposal["conflict_sha256"]
        item["evidence_sha256"] = proposal["evidence_sha256"]
        item["binding_sha256"] = raw_binding.raw_path_binding_sha256_v1(item)
        rebuilt.append(item)
    inventory["plan_sha256"] = binding_plan["plan_sha256"]
    inventory["binding_count"] = len(rebuilt)
    inventory["bindings"] = rebuilt
    inventory["inventory_sha256"] = raw_binding.raw_path_binding_inventory_sha256_v1(
        inventory
    )


def build_synthetic_raw_composition_inputs_v2() -> dict[str, Any]:
    base = raw_harness.build_synthetic_raw_path_binding_inputs_v1()
    proposals = copy.deepcopy(base["plan"]["proposals"])
    for proposal in proposals:
        if proposal["proposal_type"] == "LEGACY_ALIAS_CANONICALIZATION":
            proposal["selected_normalized_value"] = "100"
            proposal["canonical_alias_updates"] = {
                alias: "100" for alias in proposal["expected_current_aliases"]
            }
    proposals.sort(
        key=lambda item: (
            item["proposal_type"],
            item["record_fingerprint"],
            item["conflict_sha256"],
        )
    )
    planner_plan = _source_plan(proposals)
    binding_plan = composition.derive_raw_binding_plan_envelope_v2(planner_plan)
    inventory = copy.deepcopy(base["raw_path_inventory"])
    _reseal_inventory_for_plan(inventory, planner_plan, binding_plan)
    return {
        "planner_plan": planner_plan,
        "raw_registry_snapshot": copy.deepcopy(base["raw_registry_snapshot"]),
        "raw_path_inventory": inventory,
        "expected_legacy_count": 1,
        "expected_financial_count": 1,
        "max_proposals": 2,
    }


def run_synthetic_raw_composition_harness_v2() -> dict[str, Any]:
    inputs = build_synthetic_raw_composition_inputs_v2()
    before = copy.deepcopy(inputs)
    before_sha = composition._stable_sha256(before)
    first = composition.compose_closed_identity_conflict_raw_preview_offline_v2(
        **inputs
    )
    second = composition.compose_closed_identity_conflict_raw_preview_offline_v2(
        **copy.deepcopy(inputs)
    )
    after_sha = composition._stable_sha256(inputs)
    receipt = first.get("preview_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("preview_materialized") is True
        and first.get("translation_allowed") is False
        and first.get("apply_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and first.get("runtime_integrated") is False
        and first.get("broker_called") is False
        and isinstance(receipt, dict)
        and receipt.get("round_trip_verified") is True
        and receipt.get("translation_allowed") is False
        and receipt.get("apply_allowed") is False
        and receipt.get("proposal_count") == 2
        and receipt.get("changed_path_count") == 3
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "RAW_COMPOSITION_V2_HARNESS_PASSED_OFFLINE_TRANSLATION_BLOCKED"
            if ok
            else "RAW_COMPOSITION_V2_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_HARNESS_V2_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "translation_allowed": False,
        "apply_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "composition_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_COMPOSITION_HARNESS_V2_VERSION",
    "build_synthetic_raw_composition_inputs_v2",
    "run_synthetic_raw_composition_harness_v2",
]
