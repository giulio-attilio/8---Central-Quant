"""In-memory harness for the dormant 19-writer seam binding contract."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_participation_contract_v1 as participation
import trade_registry_closed_identity_conflict_repair_writer_participation_harness_v1 as participation_harness
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-SEAM-BINDING-HARNESS-V1"
)


class SyntheticWriterSeamBindingBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantWriterSeamBinder:
    """Rehearse metadata bindings without accepting a production callable."""

    def __init__(self, bindings: Sequence[Mapping[str, Any]]) -> None:
        self._bindings = copy.deepcopy(list(bindings))
        self._bound_count = 0
        self._runtime_callable_bound = False

    @property
    def bound_count(self) -> int:
        return self._bound_count

    @property
    def runtime_callable_bound(self) -> bool:
        return self._runtime_callable_bound

    def rehearse(
        self,
        *,
        installation_event_sequence: Sequence[str] | None = None,
        non_reentrant_writer_ids: Sequence[str] = (),
        callable_bound_writer_ids: Sequence[str] = (),
    ) -> dict[str, Any]:
        expected_order = [item["phase"] for item in seam_binding.canonical_writer_seam_installation_order_v1()]
        supplied_order = expected_order if installation_event_sequence is None else list(installation_event_sequence)
        if supplied_order != expected_order:
            raise SyntheticWriterSeamBindingBlocked("INSTALLATION_ORDER_INVALID")
        if len(self._bindings) != 19:
            raise SyntheticWriterSeamBindingBlocked("EXACTLY_19_SEAM_BINDINGS_REQUIRED")
        ids = [item.get("writer", {}).get("writer_id") for item in self._bindings]
        if len(set(ids)) != 19 or any(not item for item in ids):
            raise SyntheticWriterSeamBindingBlocked("SEAM_BINDING_WRITER_IDS_INVALID")
        if set(non_reentrant_writer_ids).intersection(ids):
            raise SyntheticWriterSeamBindingBlocked("REENTRANCY_REQUIRED")
        if set(callable_bound_writer_ids).intersection(ids):
            self._runtime_callable_bound = True
            raise SyntheticWriterSeamBindingBlocked("REAL_CALLABLE_BINDING_FORBIDDEN")
        allowed_strategies = {
            "FUNCTION_BODY_FULL_RMW_REENTRANT",
            "FUNCTION_BODY_EXCLUSIVE_WRITE_REENTRANT",
            "MAIN_COMMIT_BRANCH_FULL_RMW_RELOAD",
            "MAIN_EXISTING_SCOPE_COORDINATOR_UPGRADE",
        }
        if any(item.get("adaptation_strategy") not in allowed_strategies for item in self._bindings):
            raise SyntheticWriterSeamBindingBlocked("ADAPTATION_STRATEGY_INVALID")

        self._bound_count = len(self._bindings)
        receipts = [
            {
                "writer_id": binding["writer"]["writer_id"],
                "source_signature_sha256": binding["source_signature_sha256"],
                "adaptation_strategy": binding["adaptation_strategy"],
                "reentrancy_mode": "OWNER_TOKEN_REENTRANT_OUTERMOST_RELEASE_V1",
                "synthetic_binding_observed": True,
                "real_callable_bound": False,
                "writer_invoked": False,
            }
            for binding in self._bindings
        ]
        return {
            "binding_receipts": receipts,
            "installation_event_sequence": supplied_order,
            "reentrancy_rehearsal": {
                "mode": "OWNER_TOKEN_REENTRANT_OUTERMOST_RELEASE_V1",
                "depth_sequence": [0, 1, 2, 1, 0],
                "single_owner_token_preserved": True,
                "sink_token_accepted_synthetically": True,
                "lock_released_at_outermost_only": True,
                "real_lock_acquired": False,
            },
        }


def build_synthetic_closed_repair_writer_seam_binding_inputs_v1() -> dict[str, Any]:
    participation_inputs = participation_harness.build_synthetic_closed_repair_writer_participation_inputs_v1()
    participation_result = participation.evaluate_closed_repair_writer_participation_offline_v1(**participation_inputs)
    if participation_result.get("ok") is not True:
        raise AssertionError("synthetic writer participation unexpectedly failed")
    receipt = participation_result["participation_receipt"]
    bindings = seam_binding.canonical_writer_seam_bindings_v1(receipt)
    installation_order = seam_binding.canonical_writer_seam_installation_order_v1()
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_WRITER_SEAM_BINDING_SPEC_V1",
        "upstream_participation_receipt_sha256": receipt["participation_receipt_sha256"],
        "seam_bindings": bindings,
        "seam_bindings_sha256": seam_binding._stable_sha256(bindings),
        "installation_protocol": {
            "ordered_phases": installation_order,
            "ordered_phases_sha256": seam_binding._stable_sha256(installation_order),
            "coordination_before_storage": True,
            "storage_before_body_seams": True,
            "body_seams_before_bot_imports": True,
            "bot_imports_before_threads": True,
            "fail_closed_on_unknown_order": True,
        },
        "reentrancy_protocol": {
            "mode": "OWNER_TOKEN_REENTRANT_OUTERMOST_RELEASE_V1",
            "same_owner_token_for_nested_calls": True,
            "release_only_at_outermost_depth": True,
            "sink_validates_owner_token": True,
            "nested_load_and_write_supported": True,
            "fail_closed_on_token_mismatch": True,
        },
        "import_binding_risk": {
            "by_name_consumers": [
                {"component": "bots/meme.py", "source_anchor_line": 65},
                {"component": "bots/predator.py", "source_anchor_line": 73},
                {"component": "bots/turtle.py", "source_anchor_line": 76},
            ],
            "late_monkey_patch_insufficient": True,
            "function_body_binding_required": True,
        },
        "safety_envelope": {
            "contract_only": True,
            "real_source_imported": False,
            "real_callable_bound": False,
            "real_startup_changed": False,
            "runtime_install_allowed": False,
            "apply_entrypoint_present": False,
        },
    }
    spec["spec_sha256"] = seam_binding.writer_seam_binding_spec_sha256_v1(spec)
    synthetic = InMemoryDormantWriterSeamBinder(bindings).rehearse()
    receipts = synthetic["binding_receipts"]
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_WRITER_SEAM_BINDING_REHEARSAL_V1",
        "upstream_participation_receipt_sha256": receipt["participation_receipt_sha256"],
        "seam_binding_spec_sha256": spec["spec_sha256"],
        "writer_count": len(receipts),
        "binding_receipts": receipts,
        "binding_receipts_sha256": seam_binding._stable_sha256(receipts),
        "installation_event_sequence": synthetic["installation_event_sequence"],
        "body_seams_ready_before_bot_imports": True,
        "all_seams_ready_before_threads": True,
        "reentrancy_rehearsal": synthetic["reentrancy_rehearsal"],
        "safety_envelope": {
            "synthetic_memory_only": True,
            "real_source_imported": False,
            "real_callable_bound": False,
            "writer_invoked": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_install_allowed": False,
            "apply_entrypoint_present": False,
            "no_order_sent": True,
        },
    }
    rehearsal["rehearsal_sha256"] = seam_binding.writer_seam_binding_rehearsal_sha256_v1(rehearsal)
    return {
        "participation_result": participation_result,
        "seam_binding_spec": spec,
        "seam_binding_rehearsal": rehearsal,
    }


def run_synthetic_closed_repair_writer_seam_binding_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_writer_seam_binding_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = seam_binding._stable_sha256(before)
    first = seam_binding.evaluate_closed_repair_writer_seam_binding_offline_v1(**inputs)
    second = seam_binding.evaluate_closed_repair_writer_seam_binding_offline_v1(**copy.deepcopy(inputs))
    after_sha = seam_binding._stable_sha256(inputs)
    receipt = first.get("seam_binding_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("seam_binding_contract_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("writer_count") == 19
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": "CLOSED_REPAIR_WRITER_SEAM_BINDING_V1_HARNESS_PASSED_PRODUCTION_BLOCKED" if ok else "CLOSED_REPAIR_WRITER_SEAM_BINDING_V1_HARNESS_FAILED_CLOSED",
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_HARNESS_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "seam_binding_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_SEAM_BINDING_HARNESS_V1_VERSION",
    "InMemoryDormantWriterSeamBinder",
    "SyntheticWriterSeamBindingBlocked",
    "build_synthetic_closed_repair_writer_seam_binding_inputs_v1",
    "run_synthetic_closed_repair_writer_seam_binding_harness_v1",
]
