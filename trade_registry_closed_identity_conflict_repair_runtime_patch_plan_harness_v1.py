"""Read-only harness for the non-applicable runtime patch plan."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_contract_v1 as installation_manifest
import trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_contract_v1 as projection
import trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_harness_v1 as projection_harness
import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_contract_v1 as patch_plan
import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as static_preflight


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PATCH-PLAN-HARNESS-V1"
)

_MAX_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_TOTAL_BYTES = 20 * 1024 * 1024


class RuntimePatchPlanHarnessBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantRuntimePatchPlanner:
    """Validate plan topology without receiving patch text or callables."""

    def __init__(self, source_files: Sequence[Mapping[str, Any]]) -> None:
        self._source_files = copy.deepcopy(list(source_files))
        self._events: list[str] = []

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self._events)

    def rehearse(
        self,
        *,
        operations_by_file: Mapping[str, Sequence[Mapping[str, Any]]],
        phase_event_sequence: Sequence[str] | None = None,
        source_hashes_match: bool = True,
        patch_payload_provided: bool = False,
        replacement_text_provided: bool = False,
        apply_requested: bool = False,
        executable_object_provided: bool = False,
    ) -> dict[str, Any]:
        expected_operations = patch_plan.canonical_runtime_patch_operations_v1()
        expected_phases = [
            item["phase"]
            for item in patch_plan.canonical_runtime_patch_rehearsal_phases_v1()
        ]
        supplied_phases = (
            expected_phases
            if phase_event_sequence is None
            else list(phase_event_sequence)
        )
        if not source_hashes_match:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_HASH_DRIFT_DENIED")
        if patch_payload_provided:
            raise RuntimePatchPlanHarnessBlocked("PATCH_PAYLOAD_DENIED")
        if replacement_text_provided:
            raise RuntimePatchPlanHarnessBlocked("REPLACEMENT_TEXT_DENIED")
        if apply_requested:
            raise RuntimePatchPlanHarnessBlocked("APPLY_REQUEST_DENIED")
        if executable_object_provided:
            raise RuntimePatchPlanHarnessBlocked("EXECUTABLE_OBJECT_DENIED")
        if copy.deepcopy(dict(operations_by_file)) != expected_operations:
            raise RuntimePatchPlanHarnessBlocked("PATCH_OPERATIONS_INVALID")
        if supplied_phases != expected_phases:
            raise RuntimePatchPlanHarnessBlocked("PATCH_PLAN_PHASE_ORDER_INVALID")
        expected_paths = patch_plan.canonical_runtime_patch_source_files_v1()
        observed_paths = [item.get("relative_path") for item in self._source_files]
        if observed_paths != expected_paths:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_PRECONDITIONS_INVALID")
        self._events = list(supplied_phases)
        operation_items = [
            item for values in expected_operations.values() for item in values
        ]
        return {
            "phase_event_sequence": list(self._events),
            "writer_operation_count": sum(
                item.get("writer_id") is not None for item in operation_items
            ),
            "mutated_file_count": 2,
            "verified_only_file_count": 7,
            "source_bytes_preserved": True,
            "source_file_written": False,
            "runtime_executed": False,
            "live_allowed": False,
        }


def load_runtime_patch_source_preconditions_read_only_v1(
    repository_root: str | Path,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Read only the nine explicit source files and expose hashes, never content."""

    root = Path(repository_root).resolve(strict=True)
    if not root.is_dir():
        raise RuntimePatchPlanHarnessBlocked("REPOSITORY_ROOT_NOT_DIRECTORY")
    contents: dict[str, str] = {}
    file_receipts: list[dict[str, Any]] = []
    total = 0
    mutated = {"trade_registry.py", "main.py"}
    for relative in patch_plan.canonical_runtime_patch_source_files_v1():
        candidate = (root / relative).resolve(strict=True)
        if not candidate.is_relative_to(root) or not candidate.is_file():
            raise RuntimePatchPlanHarnessBlocked("SOURCE_PATH_OUTSIDE_ROOT")
        size = candidate.stat().st_size
        if size <= 0 or size > _MAX_SOURCE_BYTES:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_SIZE_INVALID")
        total += size
        if total > _MAX_TOTAL_BYTES:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_SET_SIZE_LIMIT_EXCEEDED")
        try:
            source = candidate.read_text(encoding="utf-8")
        except UnicodeError as exc:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_UTF8_DECODE_FAILED") from exc
        if "\x00" in source:
            raise RuntimePatchPlanHarnessBlocked("SOURCE_TEXT_INVALID")
        encoded = source.encode("utf-8")
        contents[relative] = source
        file_receipts.append(
            {
                "relative_path": relative,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "size_bytes": len(encoded),
                "role": (
                    "MUTATE_DECLARATIVELY"
                    if relative in mutated
                    else "VERIFY_UNCHANGED"
                ),
            }
        )
    preflight_sources = {
        key: contents[key] for key in static_preflight.REQUIRED_SOURCE_KEYS_V1
    }
    current = static_preflight.evaluate_closed_repair_runtime_static_preflight_v1(
        preflight_sources
    )
    evidence = {
        "source_set_version": "READ_ONLY_CLOSED_REPAIR_RUNTIME_SOURCE_PRECONDITIONS_V1",
        "files": file_receipts,
        "current_static_preflight": {
            "evaluation_complete": current.get("evaluation_complete") is True,
            "static_readiness": current.get("static_readiness") is True,
            "production_ready": current.get("production_ready") is True,
            "live_allowed": current.get("live_allowed") is True,
            "runtime_executed": current.get("runtime_executed") is True,
            "blockers": list(current.get("blockers") or ()),
            "writer_summary": copy.deepcopy(current.get("writer_summary")),
        },
        "read_only_collection": True,
        "secret_files_excluded": True,
    }
    evidence["source_set_sha256"] = (
        patch_plan.runtime_patch_source_preconditions_sha256_v1(evidence)
    )
    return contents, evidence


def build_closed_repair_runtime_patch_plan_inputs_read_only_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    projection_inputs = (
        projection_harness.build_synthetic_closed_repair_runtime_installation_preflight_projection_inputs_v1()
    )
    projection_result = (
        projection.evaluate_closed_repair_runtime_installation_preflight_projection_offline_v1(
            **projection_inputs
        )
    )
    if projection_result.get("ok") is not True:
        raise AssertionError("synthetic preflight projection unexpectedly failed")
    projection_receipt = projection_result["projection_receipt"]
    contents, source_evidence = load_runtime_patch_source_preconditions_read_only_v1(
        repository_root
    )
    expected_blockers = projection.canonical_resolved_runtime_preflight_blockers_v1()
    current_preflight = source_evidence["current_static_preflight"]
    pre_install_state = current_preflight["blockers"] == expected_blockers
    post_install_state = bool(
        current_preflight["blockers"] == []
        and current_preflight["static_readiness"] is True
        and (current_preflight.get("writer_summary") or {}).get("coordinated_count") == 19
    )
    if not (pre_install_state or post_install_state):
        raise RuntimePatchPlanHarnessBlocked("CURRENT_PREFLIGHT_BLOCKERS_CHANGED")
    operations = patch_plan.canonical_runtime_patch_operations_v1()
    rollback = patch_plan.canonical_runtime_patch_rollback_v1()
    plan = {
        "plan_version": "DORMANT_CLOSED_REPAIR_RUNTIME_HASH_BOUND_PATCH_PLAN_V1",
        "upstream_projection_receipt_sha256": projection_receipt[
            "projection_receipt_sha256"
        ],
        "source_preconditions_sha256": source_evidence["source_set_sha256"],
        "file_preconditions": copy.deepcopy(source_evidence["files"]),
        "mutated_files": ["trade_registry.py", "main.py"],
        "verified_only_files": patch_plan.canonical_runtime_patch_source_files_v1()[
            2:
        ],
        "operations_by_file": operations,
        "blocker_coverage": patch_plan.canonical_runtime_patch_blocker_coverage_v1(),
        "installation_order": installation_manifest.canonical_runtime_installation_phases_v1(),
        "rollback_protocol": rollback,
        "rollback_protocol_sha256": patch_plan._stable_sha256(rollback),
        "safety_envelope": {
            "declarative_only": True,
            "patch_content_absent": True,
            "replacement_text_absent": True,
            "file_writer_absent": True,
            "apply_entrypoint_present": False,
            "runtime_imported": False,
            "runtime_executed": False,
            "source_file_written": False,
            "runtime_install_allowed": False,
            "live_allowed": False,
        },
    }
    plan["plan_sha256"] = patch_plan.runtime_patch_plan_sha256_v1(plan)
    planner = InMemoryDormantRuntimePatchPlanner(source_evidence["files"])
    before_hashes = {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for key, value in contents.items()
    }
    observed = planner.rehearse(operations_by_file=operations)
    after_hashes = {
        key: hashlib.sha256(value.encode("utf-8")).hexdigest()
        for key, value in contents.items()
    }
    if before_hashes != after_hashes:
        raise RuntimePatchPlanHarnessBlocked("SOURCE_BYTES_CHANGED")
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_RUNTIME_PATCH_PLAN_REHEARSAL_V1",
        "patch_plan_sha256": plan["plan_sha256"],
        "source_preconditions_sha256": source_evidence["source_set_sha256"],
        **observed,
        "negative_controls": {
            "source_hash_drift_denied": True,
            "missing_operation_denied": True,
            "unknown_operation_denied": True,
            "patch_payload_denied": True,
            "apply_request_denied": True,
        },
    }
    rehearsal["rehearsal_sha256"] = patch_plan.runtime_patch_rehearsal_sha256_v1(
        rehearsal
    )
    return {
        "projection_result": projection_result,
        "source_precondition_evidence": source_evidence,
        "runtime_patch_plan": plan,
        "runtime_patch_rehearsal": rehearsal,
    }


def run_closed_repair_runtime_patch_plan_harness_read_only_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    inputs = build_closed_repair_runtime_patch_plan_inputs_read_only_v1(
        repository_root
    )
    before = copy.deepcopy(inputs)
    before_sha = patch_plan._stable_sha256(before)
    first = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **inputs
    )
    second = patch_plan.evaluate_closed_repair_runtime_patch_plan_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = patch_plan._stable_sha256(inputs)
    receipt = first.get("patch_plan_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("patch_plan_contract_verified") is True
        and first.get("source_preconditions_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("live_allowed") is False
        and first.get("patch_content_present") is False
        and first.get("source_file_written") is False
        and first.get("write_executed") is False
        and isinstance(receipt, Mapping)
        and receipt.get("source_file_count") == 9
        and receipt.get("writer_operation_count") == 19
        and receipt.get("source_hashes_must_be_rechecked") is True
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "CLOSED_REPAIR_RUNTIME_PATCH_PLAN_V1_HARNESS_PASSED_READ_ONLY_NON_APPLICABLE"
            if ok
            else "CLOSED_REPAIR_RUNTIME_PATCH_PLAN_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "read_only": True,
        "declarative_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "patch_content_present": False,
        "source_file_written": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "patch_plan_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PATCH_PLAN_HARNESS_V1_VERSION",
    "InMemoryDormantRuntimePatchPlanner",
    "RuntimePatchPlanHarnessBlocked",
    "build_closed_repair_runtime_patch_plan_inputs_read_only_v1",
    "load_runtime_patch_source_preconditions_read_only_v1",
    "run_closed_repair_runtime_patch_plan_harness_read_only_v1",
]
