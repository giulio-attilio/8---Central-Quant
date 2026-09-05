"""Synthetic harness for raw physical-apply readiness V2."""

from __future__ import annotations

import copy
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_physical_apply_readiness_contract_v2 as readiness
import trade_registry_closed_identity_conflict_repair_raw_transaction_rehearsal_harness_v2 as transaction_harness
import trade_registry_closed_identity_conflict_repair_raw_transaction_rehearsal_offline_v2 as rehearsal


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_HARNESS_V2_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PHYSICAL-APPLY-READINESS-HARNESS-V2"
)


def build_synthetic_raw_physical_apply_readiness_inputs_v2() -> dict[str, Any]:
    transaction_inputs = (
        transaction_harness.build_synthetic_raw_transaction_rehearsal_inputs_v2()
    )
    transaction_result = (
        rehearsal.rehearse_closed_identity_conflict_raw_transaction_offline_v2(
            **transaction_inputs
        )
    )
    if transaction_result.get("ok") is not True:
        raise AssertionError("synthetic raw transaction rehearsal unexpectedly failed")
    transaction = transaction_result["transaction"]
    receipt = transaction_inputs["composition_preview_receipt"]
    record_manifest_sha = readiness._stable_sha256(transaction["record_bindings"])
    writers = [
        {
            "writer_id": f"SYNTHETIC-RAW-REGISTRY-WRITER-{index:02d}",
            "synthetic_only": True,
            "real_writer_quiesced": False,
        }
        for index in range(3)
    ]
    writer_inventory_sha = readiness._stable_sha256(writers)
    collection_shape = transaction["record_bindings"][0]["collection_shape"]
    attestations = {
        "attestation_version": "SYNTHETIC_RAW_PHYSICAL_APPLY_READINESS_ATTESTATIONS_V2",
        "synthetic_only": True,
        "offline_only": True,
        "production_observation": False,
        "transaction_sha256": transaction["transaction_sha256"],
        "composition_preview_receipt_sha256": receipt["receipt_sha256"],
        "chain_evidence": {
            "upstream_plan_sha256": transaction["upstream_plan_sha256"],
            "binding_plan_sha256": transaction["binding_plan_sha256"],
            "raw_path_receipt_sha256": transaction["raw_path_receipt_sha256"],
            "composition_preview_receipt_sha256": receipt["receipt_sha256"],
            "transaction_sha256": transaction["transaction_sha256"],
            "record_binding_manifest_sha256": record_manifest_sha,
            "proposal_count": transaction["proposal_count"],
            "changed_path_count": transaction["changed_path_count"],
            "raw_paths_complete": True,
            "independently_revalidated": True,
        },
        "schema_authority": {
            "selected_authority": "SYNTHETIC_RAW_REGISTRY_DOCUMENT_V2",
            "authority_selection_explicit": True,
            "collection_shape": collection_shape,
            "whole_registry_preimage_bound": True,
            "source_raw_registry_document_sha256": transaction[
                "source_raw_registry_document_sha256"
            ],
            "candidate_raw_registry_document_sha256": transaction[
                "candidate_raw_registry_document_sha256"
            ],
            "open_trades_immutable": True,
            "ownership_fields_immutable": True,
            "order_fields_immutable": True,
            "protection_fields_immutable": True,
        },
        "writer_inventory": {
            "inventory_complete": True,
            "real_observation": False,
            "writers": writers,
            "writer_inventory_sha256": writer_inventory_sha,
        },
        "lock": {
            "synthetic_lock_rehearsal_verified": True,
            "real_interprocess_lock_acquired": False,
            "production_writers_quiesced": False,
            "fail_closed_on_timeout": True,
            "writer_inventory_sha256": writer_inventory_sha,
            "transaction_sha256": transaction["transaction_sha256"],
        },
        "backup": {
            "synthetic_backup_verified": True,
            "durable_production_backup_created": False,
            "restore_rehearsal_verified": True,
            "source_raw_registry_document_sha256": transaction[
                "source_raw_registry_document_sha256"
            ],
            "transaction_sha256": transaction["transaction_sha256"],
        },
        "operational_isolation": {
            "runtime_integrated": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "external_service_called": False,
            "real_registry_accessed": False,
            "order_submission_authorized": False,
        },
        "authorization": {
            "scope": "RAW_PHYSICAL_APPLY_READINESS_REVIEW_ONLY_V2",
            "readiness_review_authorized": True,
            "production_apply_authorized": False,
            "live_activation_authorized": False,
            "order_submission_authorized": False,
            "separate_production_authorization_required": True,
        },
    }
    attestations["attestations_sha256"] = (
        readiness.raw_physical_apply_readiness_attestations_sha256_v2(attestations)
    )
    return {
        "transaction": transaction,
        "composition_preview_receipt": receipt,
        "readiness_attestations": attestations,
    }


def run_synthetic_raw_physical_apply_readiness_harness_v2() -> dict[str, Any]:
    inputs = build_synthetic_raw_physical_apply_readiness_inputs_v2()
    before = copy.deepcopy(inputs)
    before_sha = readiness._stable_sha256(before)
    first = readiness.evaluate_closed_identity_conflict_raw_physical_apply_readiness_offline_v2(
        **inputs
    )
    second = readiness.evaluate_closed_identity_conflict_raw_physical_apply_readiness_offline_v2(
        **copy.deepcopy(inputs)
    )
    after_sha = readiness._stable_sha256(inputs)
    gate_receipt = first.get("gate_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("offline_evidence_valid") is True
        and first.get("production_ready") is False
        and first.get("translation_allowed") is False
        and first.get("apply_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and first.get("runtime_integrated") is False
        and first.get("broker_called") is False
        and isinstance(gate_receipt, dict)
        and gate_receipt.get("all_offline_checks_passed") is True
        and gate_receipt.get("production_ready") is False
        and gate_receipt.get("translation_allowed") is False
        and gate_receipt.get("apply_allowed") is False
        and gate_receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "RAW_PHYSICAL_APPLY_READINESS_V2_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "RAW_PHYSICAL_APPLY_READINESS_V2_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_HARNESS_V2_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "translation_allowed": False,
        "apply_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "readiness_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_APPLY_READINESS_HARNESS_V2_VERSION",
    "build_synthetic_raw_physical_apply_readiness_inputs_v2",
    "run_synthetic_raw_physical_apply_readiness_harness_v2",
]
