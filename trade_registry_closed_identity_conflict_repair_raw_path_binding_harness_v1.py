"""Synthetic in-memory harness for the dormant raw-path binding contract."""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_path_binding_contract_v1 as binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PATH-BINDING-HARNESS-V1"
)


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _descriptor(
    record: dict[str, Any], canonical_field: str, alias: str, path: str
) -> dict[str, Any]:
    exists, raw_value = binding._read_source_path(record, path)
    if not exists:
        raise AssertionError(f"synthetic path missing: {path}")
    normalized = (
        binding._normalize_financial(canonical_field, raw_value)
        if canonical_field in {"close_reason", "pnl_r"}
        else binding._normalize_legacy(canonical_field, raw_value)
    )
    return {
        "canonical_field": canonical_field,
        "alias": alias,
        "path": path,
        "raw_type": binding._json_type(raw_value),
        "raw_value": copy.deepcopy(raw_value),
        "raw_value_sha256": binding._stable_sha256(raw_value),
        "normalized_value": normalized,
    }


def build_synthetic_raw_path_binding_inputs_v1() -> dict[str, Any]:
    legacy_record = {
        "status": "CLOSED",
        "trade_id": "SYNTHETIC-LEGACY-001",
        "entry": 100,
        "metadata": {
            "entry": "100.5",
            "closed_history_sources": ["synthetic-transient-source"],
        },
        "ownership": {"lifecycle_id": "SYNTHETIC-LIFECYCLE-LEGACY"},
        "protection": {"disaster_stop_confirmed": True},
    }
    financial_record = {
        "status": "CLOSED",
        "trade_id": "SYNTHETIC-FINANCIAL-001",
        "lifecycle_id": "SYNTHETIC-LIFECYCLE-FINANCIAL",
        "client_order_id": "SYNTHETIC-CLIENT-001",
        "order_id": "SYNTHETIC-ORDER-001",
        "symbol": "BTCUSDT",
        "side": "LONG",
        "close_reason": "STOP_LOSS",
        "pnl_r": -1.0,
        "metadata": {
            "outcome": {
                "exit_reason": "MANUAL_CLOSE",
                "result_r": "-0.5",
            }
        },
        "protection": {"disaster_stop_confirmed": True},
    }
    document = {
        "ok": True,
        "version": "synthetic-legacy-v1",
        "updated_at": "2026-09-04T09:00:00+00:00",
        "open_trades": {
            "SYNTHETIC-OPEN-EXTERNAL": {
                "owner": "EXTERNAL",
                "must_remain_exact": True,
            }
        },
        "closed_trades": [legacy_record, financial_record],
        "synthetic_top_level_extension": {"must_remain_exact": True},
    }
    snapshot = {
        "snapshot_version": "SYNTHETIC_RAW_TRADE_REGISTRY_SNAPSHOT_V1",
        "synthetic_only": True,
        "offline_only": True,
        "source_kind": "INJECTED_SYNTHETIC_MEMORY",
        "raw_registry_document": document,
        "raw_registry_document_sha256": binding.raw_registry_document_sha256_v1(
            document
        ),
        "closed_collection_locator_sha256": binding.raw_closed_collection_locator_sha256_v1(
            document
        ),
    }
    snapshot["snapshot_envelope_sha256"] = (
        binding.raw_registry_snapshot_envelope_sha256_v1(snapshot)
    )

    legacy_fingerprint = binding.legacy_raw_closed_trade_identity_fingerprint_v1(
        legacy_record
    )
    financial_fingerprint = binding.legacy_raw_closed_trade_identity_fingerprint_v1(
        financial_record
    )
    legacy_proposal = {
        "proposal_type": "LEGACY_ALIAS_CANONICALIZATION",
        "registry_index": 0,
        "record_fingerprint": legacy_fingerprint,
        "field": "entry",
        "expected_current_aliases": ["trade.entry", "trade.metadata.entry"],
        "expected_current_normalized_values": ["100", "100.5"],
        "selected_normalized_value": "100.5",
        "canonical_alias_updates": {
            "trade.entry": "100.5",
            "trade.metadata.entry": "100.5",
        },
        "preconditions": [
            "RELOAD_REGISTRY_BEFORE_ANY_FUTURE_WRITE",
            "REQUIRE_SAME_RECORD_FINGERPRINT",
            "REQUIRE_SAME_CONFLICT_SHA256",
            "REQUIRE_INDEPENDENT_EVIDENCE_REVALIDATION",
            "REQUIRE_EXPLICIT_SEPARATE_PRODUCTION_AUTHORIZATION",
        ],
        "conflict_sha256": _digest_text("synthetic-legacy-conflict"),
        "evidence_sha256": _digest_text("synthetic-legacy-evidence"),
    }
    financial_proposal = {
        "proposal_type": "FINANCIAL_OUTCOME_CANONICALIZATION",
        "registry_index": 1,
        "record_fingerprint": financial_fingerprint,
        "trade_id": financial_record["trade_id"],
        "strong_identity": {
            "lifecycle_id": financial_record["lifecycle_id"],
            "client_order_id": financial_record["client_order_id"],
            "order_id": financial_record["order_id"],
        },
        "expected_current_candidates": {
            "close_reason": ["MANUAL_CLOSE", "STOP_LOSS"],
            "pnl_r": [-1.0, -0.5],
        },
        "canonical_updates": {"close_reason": "MANUAL_CLOSE", "pnl_r": -0.5},
        "preconditions": [
            "RELOAD_REGISTRY_BEFORE_ANY_FUTURE_WRITE",
            "REQUIRE_SAME_RECORD_FINGERPRINT",
            "REQUIRE_SAME_CONFLICT_SHA256",
            "REQUIRE_EXPLICIT_SEPARATE_PRODUCTION_AUTHORIZATION",
        ],
        "conflict_sha256": _digest_text("synthetic-financial-conflict"),
        "evidence_sha256": _digest_text("synthetic-financial-evidence"),
    }
    proposals = [legacy_proposal, financial_proposal]
    plan = {
        "plan_version": "SYNTHETIC_CLOSED_IDENTITY_REPAIR_PLAN_V1",
        "offline_only": True,
        "synthetic_only": True,
        "proposal_count": len(proposals),
        "proposals": proposals,
    }
    plan["plan_sha256"] = binding.repair_plan_sha256_v1(plan)

    path_sets = [
        [
            _descriptor(legacy_record, "entry", "entry", "trade.entry"),
            _descriptor(
                legacy_record, "entry", "entry", "trade.metadata.entry"
            ),
        ],
        [
            _descriptor(
                financial_record,
                "close_reason",
                "close_reason",
                "trade.close_reason",
            ),
            _descriptor(
                financial_record,
                "close_reason",
                "exit_reason",
                "trade.metadata.outcome.exit_reason",
            ),
            _descriptor(financial_record, "pnl_r", "pnl_r", "trade.pnl_r"),
            _descriptor(
                financial_record,
                "pnl_r",
                "result_r",
                "trade.metadata.outcome.result_r",
            ),
        ],
    ]
    bindings: list[dict[str, Any]] = []
    for ordinal, (proposal, record, path_set) in enumerate(
        zip(proposals, document["closed_trades"], path_sets, strict=True)
    ):
        record_fingerprint = binding.legacy_raw_closed_trade_identity_fingerprint_v1(
            record
        )
        item = {
            "proposal_ordinal": ordinal,
            "proposal_sha256": binding._stable_sha256(proposal),
            "proposal_type": proposal["proposal_type"],
            "registry_index": proposal["registry_index"],
            "registry_collection_key": None,
            "collection_shape": "list",
            "record_fingerprint": record_fingerprint,
            "legacy_identity_fingerprint": record_fingerprint,
            "raw_record_sha256": binding._stable_sha256(record),
            "conflict_sha256": proposal["conflict_sha256"],
            "evidence_sha256": proposal["evidence_sha256"],
            "path_bindings": path_set,
        }
        item["binding_sha256"] = binding.raw_path_binding_sha256_v1(item)
        bindings.append(item)
    inventory = {
        "inventory_version": "SYNTHETIC_RAW_PATH_BINDING_INVENTORY_V1",
        "synthetic_only": True,
        "offline_only": True,
        "plan_sha256": plan["plan_sha256"],
        "raw_registry_document_sha256": snapshot[
            "raw_registry_document_sha256"
        ],
        "binding_count": len(bindings),
        "bindings": bindings,
    }
    inventory["inventory_sha256"] = binding.raw_path_binding_inventory_sha256_v1(
        inventory
    )
    return {
        "plan": plan,
        "raw_registry_snapshot": snapshot,
        "raw_path_inventory": inventory,
    }


def run_synthetic_raw_path_binding_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_raw_path_binding_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = binding._stable_sha256(before)
    first = binding.bind_closed_identity_conflict_raw_paths_offline_v1(**inputs)
    second = binding.bind_closed_identity_conflict_raw_paths_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = binding._stable_sha256(inputs)
    preserved = inputs == before and before_sha == after_sha
    deterministic = first == second
    request = first.get("translation_request")
    ok = bool(
        first.get("ok") is True
        and first.get("bindings_valid") is True
        and first.get("translation_allowed") is False
        and first.get("apply_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and first.get("runtime_integrated") is False
        and first.get("broker_called") is False
        and isinstance(request, dict)
        and request.get("binding_count") == 2
        and request.get("translation_allowed") is False
        and request.get("apply_allowed") is False
        and preserved
        and deterministic
    )
    return {
        "ok": ok,
        "status": (
            "RAW_PATH_BINDING_HARNESS_PASSED_OFFLINE_TRANSLATION_BLOCKED"
            if ok
            else "RAW_PATH_BINDING_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_HARNESS_V1_VERSION,
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
        "input_preserved": preserved,
        "deterministic": deterministic,
        "input_sha256_before": before_sha,
        "input_sha256_after": after_sha,
        "binding_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PATH_BINDING_HARNESS_V1_VERSION",
    "build_synthetic_raw_path_binding_inputs_v1",
    "run_synthetic_raw_path_binding_harness_v1",
]
