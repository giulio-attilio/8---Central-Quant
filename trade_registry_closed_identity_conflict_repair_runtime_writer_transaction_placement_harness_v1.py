"""Offline in-memory harness for the 19 transaction placement contracts."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_harness_v1 as patch_plan_harness
import trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1 as placement


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-WRITER-TRANSACTION-PLACEMENT-HARNESS-V1"
)


class RuntimeWriterTransactionPlacementHarnessBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantTransactionPlacementRehearsal:
    """Rehearse events only; never acquire a lock or touch Registry storage."""

    def rehearse(
        self,
        placements: Sequence[Mapping[str, Any]],
        *,
        wrong_lock_order: bool = False,
        omit_fresh_read: bool = False,
        leak_on_return: bool = False,
        leak_on_exception: bool = False,
        downgrade_partial_commit: bool = False,
        external_collection_under_lease: bool = False,
    ) -> list[dict[str, Any]]:
        if wrong_lock_order:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("WRONG_LOCK_ORDER_DENIED")
        if omit_fresh_read:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("MISSING_FRESH_READ_DENIED")
        if leak_on_return:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("RETURN_PATH_LEASE_LEAK_DENIED")
        if leak_on_exception:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("EXCEPTION_PATH_LEASE_LEAK_DENIED")
        if downgrade_partial_commit:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("PARTIAL_COMMIT_DOWNGRADE_DENIED")
        if external_collection_under_lease:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("EXTERNAL_COLLECTION_UNDER_LEASE_DENIED")
        supplied = copy.deepcopy(list(placements))
        expected = placement.canonical_runtime_writer_transaction_placements_v1()
        if supplied != expected:
            raise RuntimeWriterTransactionPlacementHarnessBlocked("TRANSACTION_PLACEMENTS_INVALID")
        receipts: list[dict[str, Any]] = []
        for item in supplied:
            if item["process_local_lock_line"] is not None and not item["coordinator_before_process_local_lock"]:
                raise RuntimeWriterTransactionPlacementHarnessBlocked("WRONG_LOCK_ORDER_DENIED")
            if item["writer_id"] != "TRADE_REGISTRY_RESET" and item["fresh_read_after_acquire_line"] is None:
                raise RuntimeWriterTransactionPlacementHarnessBlocked("MISSING_FRESH_READ_DENIED")
            if not item["release_on_all_returns"]:
                raise RuntimeWriterTransactionPlacementHarnessBlocked("RETURN_PATH_LEASE_LEAK_DENIED")
            if not item["release_on_all_exceptions"]:
                raise RuntimeWriterTransactionPlacementHarnessBlocked("EXCEPTION_PATH_LEASE_LEAK_DENIED")
            receipts.append(
                {
                    "writer_id": item["writer_id"],
                    "classification": item["classification"],
                    "synthetic_acquire": True,
                    "fresh_read_rehearsed": item["fresh_read_after_acquire_line"] is not None,
                    "authoritative_write_simulated": True,
                    "return_release_rehearsed": True,
                    "exception_release_rehearsed": True,
                    "real_lock_acquired": False,
                    "registry_read": False,
                    "registry_write": False,
                }
            )
        return receipts


def _control_denied(**kwargs: bool) -> bool:
    try:
        InMemoryDormantTransactionPlacementRehearsal().rehearse(
            placement.canonical_runtime_writer_transaction_placements_v1(),
            **kwargs,
        )
    except RuntimeWriterTransactionPlacementHarnessBlocked:
        return True
    return False


def build_closed_repair_runtime_writer_transaction_placement_inputs_read_only_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    patch_inputs = patch_plan_harness.build_closed_repair_runtime_patch_plan_inputs_read_only_v1(
        repository_root
    )
    patch_result = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **patch_inputs
    )
    if patch_result.get("ok") is not True:
        raise RuntimeWriterTransactionPlacementHarnessBlocked("UPSTREAM_PATCH_PLAN_INVALID")
    patch_receipt = patch_result["patch_plan_receipt"]
    placements = placement.canonical_runtime_writer_transaction_placements_v1()
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_SPEC_V1",
        "upstream_patch_plan_receipt_sha256": patch_receipt["patch_plan_receipt_sha256"],
        "placements": placements,
        "classification_counts": dict(Counter(item["classification"] for item in placements)),
        "lock_protocol": placement.canonical_runtime_writer_lock_protocol_v1(),
        "partial_commit_truth": placement.canonical_runtime_writer_partial_commit_truth_v1(),
        "declarative_only": True,
        "patch_content_present": False,
        "apply_entrypoint_present": False,
        "runtime_imported": False,
        "source_file_written": False,
        "live_allowed": False,
    }
    spec["spec_sha256"] = placement.runtime_writer_transaction_placement_spec_sha256_v1(spec)
    writer_receipts = InMemoryDormantTransactionPlacementRehearsal().rehearse(placements)
    negative_controls = {
        "wrong_lock_order_denied": _control_denied(wrong_lock_order=True),
        "missing_fresh_read_denied": _control_denied(omit_fresh_read=True),
        "return_path_lease_leak_denied": _control_denied(leak_on_return=True),
        "exception_path_lease_leak_denied": _control_denied(leak_on_exception=True),
        "partial_commit_downgrade_denied": _control_denied(downgrade_partial_commit=True),
        "external_collection_under_lease_denied": _control_denied(external_collection_under_lease=True),
    }
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_REHEARSAL_V1",
        "spec_sha256": spec["spec_sha256"],
        "writer_receipts": writer_receipts,
        "classification_counts": spec["classification_counts"],
        "partial_commit_truth_case_count": len(spec["partial_commit_truth"]),
        "negative_controls": negative_controls,
        "source_bytes_preserved": True,
        "runtime_executed": False,
        "live_allowed": False,
    }
    rehearsal["rehearsal_sha256"] = placement.runtime_writer_transaction_placement_rehearsal_sha256_v1(rehearsal)
    return {
        "runtime_patch_plan_result": patch_result,
        "transaction_placement_spec": spec,
        "transaction_placement_rehearsal": rehearsal,
    }


def run_closed_repair_runtime_writer_transaction_placement_harness_read_only_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    first_inputs = build_closed_repair_runtime_writer_transaction_placement_inputs_read_only_v1(repository_root)
    preserved = copy.deepcopy(first_inputs)
    first = placement.evaluate_closed_repair_runtime_writer_transaction_placement_offline_v1(**first_inputs)
    second_inputs = build_closed_repair_runtime_writer_transaction_placement_inputs_read_only_v1(repository_root)
    second = placement.evaluate_closed_repair_runtime_writer_transaction_placement_offline_v1(**second_inputs)
    receipt = first.get("transaction_placement_receipt")
    return {
        **first,
        "input_preserved": first_inputs == preserved,
        "deterministic": first == second and first_inputs == second_inputs,
        "read_only": True,
        "declarative_only": True,
        "source_file_written": False,
        "registry_read": False,
        "registry_write": False,
        "real_lock_acquired": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "receipt_sha256": receipt.get("transaction_placement_receipt_sha256") if isinstance(receipt, Mapping) else None,
        "harness_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_HARNESS_V1_VERSION,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_TRANSACTION_PLACEMENT_HARNESS_V1_VERSION",
    "InMemoryDormantTransactionPlacementRehearsal",
    "RuntimeWriterTransactionPlacementHarnessBlocked",
    "build_closed_repair_runtime_writer_transaction_placement_inputs_read_only_v1",
    "run_closed_repair_runtime_writer_transaction_placement_harness_read_only_v1",
]
