"""Read-only AST harness for the dormant Registry writer source anchors."""

from __future__ import annotations

import ast
import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_patch_plan_harness_v1 as patch_plan_harness
import trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1 as contract
import trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1 as placement
import trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_harness_v1 as placement_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-WRITER-SOURCE-ANCHOR-HARNESS-V1"
)


class RuntimeWriterSourceAnchorHarnessBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _marker_kind(line: str) -> str:
    stripped = line.strip()
    if "save_registry(" in stripped:
        return "REGISTRY_SAVE_CALL"
    if "_trpsf_v1_atomic_write_json(" in stripped:
        return "ATOMIC_JSON_WRITE_CALL"
    if "fh.write(" in stripped:
        return "EVENT_APPEND_WRITE_CALL"
    if "_rp_v1_registry_snapshot_full(" in stripped:
        return "REGISTRY_SNAPSHOT_READ_CALL"
    if "_trpsf_v1_read_json(" in stripped:
        return "RAW_REGISTRY_READ_CALL"
    if "load_registry(" in stripped or "_load_registry(" in stripped:
        return "REGISTRY_READ_CALL"
    if "path.exists()" in stripped:
        return "REGISTRY_STORAGE_STATE_GUARD"
    if stripped.startswith("with _lock:") or (
        stripped.startswith("with _c3_closed_repair_writer_mutation_v1(")
        and stripped.endswith(", _lock:")
    ):
        return "WITH_MODULE_RLOCK"
    if stripped.startswith("with registry_lock:"):
        return "WITH_LOCAL_LOCK"
    if "registry_lock.acquire(" in stripped:
        return "LOCAL_LOCK_ACQUIRE"
    if stripped == "try:":
        return "TRY_INSERTION_SEAM"
    if stripped.startswith("for "):
        return "LOOP_INSERTION_SEAM"
    if stripped.startswith("if "):
        return "IF_GUARD"
    return "OTHER"


class InMemoryDormantSourceAnchorRehearsal:
    def rehearse(
        self,
        observed_anchors: Sequence[Mapping[str, Any]],
        *,
        function_line_shift: bool = False,
        writer_missing: bool = False,
        write_marker_drift: bool = False,
        lock_marker_drift: bool = False,
        fresh_read_anchor_drift: bool = False,
        source_hash_mismatch: bool = False,
        runtime_import_requested: bool = False,
    ) -> dict[str, Any]:
        for enabled, reason in (
            (function_line_shift, "FUNCTION_LINE_SHIFT_DENIED"),
            (writer_missing, "WRITER_MISSING_DENIED"),
            (write_marker_drift, "WRITE_MARKER_DRIFT_DENIED"),
            (lock_marker_drift, "LOCK_MARKER_DRIFT_DENIED"),
            (fresh_read_anchor_drift, "FRESH_READ_ANCHOR_DRIFT_DENIED"),
            (source_hash_mismatch, "SOURCE_HASH_MISMATCH_DENIED"),
            (runtime_import_requested, "RUNTIME_IMPORT_REQUEST_DENIED"),
        ):
            if enabled:
                raise RuntimeWriterSourceAnchorHarnessBlocked(reason)
        supplied = copy.deepcopy(list(observed_anchors))
        expected = contract.canonical_runtime_writer_source_anchor_expectations_v1()
        if len(supplied) != 19:
            raise RuntimeWriterSourceAnchorHarnessBlocked("WRITER_MISSING_DENIED")
        for observed, wanted in zip(supplied, expected):
            if observed.get("writer_id") != wanted["writer_id"]:
                raise RuntimeWriterSourceAnchorHarnessBlocked("WRITER_MISSING_DENIED")
            if (observed.get("function_start_line"), observed.get("function_end_line")) != (
                wanted["function_start_line"],
                wanted["function_end_line"],
            ):
                raise RuntimeWriterSourceAnchorHarnessBlocked("FUNCTION_LINE_SHIFT_DENIED")
            if observed.get("write_markers") != wanted["expected_write_markers"]:
                raise RuntimeWriterSourceAnchorHarnessBlocked("WRITE_MARKER_DRIFT_DENIED")
            if observed.get("local_lock_marker") != wanted["expected_local_lock_marker"]:
                raise RuntimeWriterSourceAnchorHarnessBlocked("LOCK_MARKER_DRIFT_DENIED")
            if observed.get("fresh_marker") != wanted["expected_fresh_marker"]:
                raise RuntimeWriterSourceAnchorHarnessBlocked("FRESH_READ_ANCHOR_DRIFT_DENIED")
            if observed.get("commit_guard_marker") != wanted["expected_commit_guard_marker"]:
                raise RuntimeWriterSourceAnchorHarnessBlocked("COMMIT_GUARD_DRIFT_DENIED")
            if observed.get("all_placement_lines_within_function") is not True:
                raise RuntimeWriterSourceAnchorHarnessBlocked("PLACEMENT_OUTSIDE_FUNCTION_DENIED")
        return {
            "writer_count": 19,
            "validated_source_files": ["trade_registry.py", "main.py"],
            "source_bytes_preserved": True,
            "runtime_executed": False,
            "live_allowed": False,
        }


def _line(lines: list[str], number: int | None) -> str | None:
    if number is None:
        return None
    if number < 1 or number > len(lines):
        raise RuntimeWriterSourceAnchorHarnessBlocked("SOURCE_ANCHOR_LINE_OUT_OF_RANGE")
    return lines[number - 1]


def _observe_source_anchors(contents: Mapping[str, str]) -> list[dict[str, Any]]:
    placements = placement.canonical_runtime_writer_transaction_placements_v1()
    ast_by_file: dict[str, dict[str, ast.AST]] = {}
    lines_by_file: dict[str, list[str]] = {}
    for component in ("trade_registry.py", "main.py"):
        source = contents.get(component)
        if not isinstance(source, str) or not source:
            raise RuntimeWriterSourceAnchorHarnessBlocked("SOURCE_CONTENT_UNAVAILABLE")
        try:
            tree = ast.parse(source, filename=component)
        except SyntaxError as exc:
            raise RuntimeWriterSourceAnchorHarnessBlocked("SOURCE_AST_PARSE_FAILED") from exc
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        ast_by_file[component] = functions
        lines_by_file[component] = source.splitlines()
    observed: list[dict[str, Any]] = []
    for item in placements:
        component = item["component"]
        node = ast_by_file[component].get(item["function"])
        if node is None or getattr(node, "end_lineno", None) is None:
            raise RuntimeWriterSourceAnchorHarnessBlocked("WRITER_FUNCTION_MISSING")
        lines = lines_by_file[component]
        placement_lines = [
            item["acquire_before_line"],
            item["release_after_line"],
            *item["authoritative_write_lines"],
        ]
        for optional in (
            item["fresh_read_after_acquire_line"],
            item["process_local_lock_line"],
            item["commit_guard_line"],
        ):
            if optional is not None:
                placement_lines.append(optional)
        start = int(node.lineno)
        end = int(node.end_lineno)
        fresh_line = _line(lines, item["fresh_read_after_acquire_line"])
        local_lock_line = _line(lines, item["process_local_lock_line"])
        commit_guard_line = _line(lines, item["commit_guard_line"])
        observed.append(
            {
                "writer_id": item["writer_id"],
                "component": component,
                "function": item["function"],
                "function_start_line": start,
                "function_end_line": end,
                "all_placement_lines_within_function": all(start <= number <= end for number in placement_lines),
                "fresh_marker": _marker_kind(fresh_line) if fresh_line is not None else None,
                "write_markers": [_marker_kind(_line(lines, number) or "") for number in item["authoritative_write_lines"]],
                "local_lock_marker": _marker_kind(local_lock_line) if local_lock_line is not None else None,
                "commit_guard_marker": _marker_kind(commit_guard_line) if commit_guard_line is not None else None,
                "source_content_exposed": False,
            }
        )
    return observed


def _control_denied(**kwargs: bool) -> bool:
    expected = contract.canonical_runtime_writer_source_anchor_expectations_v1()
    synthetic = [
        {
            "writer_id": item["writer_id"],
            "function_start_line": item["function_start_line"],
            "function_end_line": item["function_end_line"],
            "write_markers": item["expected_write_markers"],
            "local_lock_marker": item["expected_local_lock_marker"],
            "fresh_marker": item["expected_fresh_marker"],
            "commit_guard_marker": item["expected_commit_guard_marker"],
            "all_placement_lines_within_function": True,
        }
        for item in expected
    ]
    try:
        InMemoryDormantSourceAnchorRehearsal().rehearse(synthetic, **kwargs)
    except RuntimeWriterSourceAnchorHarnessBlocked:
        return True
    return False


def build_closed_repair_runtime_writer_source_anchor_inputs_read_only_v1(
    repository_root: str | Path,
) -> dict[str, Any]:
    placement_inputs = placement_harness.build_closed_repair_runtime_writer_transaction_placement_inputs_read_only_v1(repository_root)
    placement_result = placement.evaluate_closed_repair_runtime_writer_transaction_placement_offline_v1(**placement_inputs)
    if placement_result.get("ok") is not True:
        raise RuntimeWriterSourceAnchorHarnessBlocked("UPSTREAM_TRANSACTION_PLACEMENT_INVALID")
    placement_receipt = placement_result["transaction_placement_receipt"]
    contents, source_preconditions = patch_plan_harness.load_runtime_patch_source_preconditions_read_only_v1(repository_root)
    if source_preconditions["source_set_sha256"] != placement_receipt["source_preconditions_sha256"]:
        raise RuntimeWriterSourceAnchorHarnessBlocked("SOURCE_HASH_MISMATCH_DENIED")
    expectations = contract.canonical_runtime_writer_source_anchor_expectations_v1()
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_SPEC_V1",
        "upstream_transaction_placement_receipt_sha256": placement_receipt["transaction_placement_receipt_sha256"],
        "source_files": ["trade_registry.py", "main.py"],
        "writer_count": 19,
        "anchor_expectations": expectations,
        "parse_only": True,
        "runtime_import_allowed": False,
        "patch_content_present": False,
        "apply_entrypoint_present": False,
        "source_file_write_allowed": False,
        "live_allowed": False,
    }
    spec["spec_sha256"] = contract.runtime_writer_source_anchor_spec_sha256_v1(spec)
    observed = _observe_source_anchors(contents)
    evidence = {
        "evidence_version": "READ_ONLY_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_EVIDENCE_V1",
        "source_precondition_evidence": source_preconditions,
        "observed_anchors": observed,
        "ast_parse_only": True,
        "runtime_imported": False,
        "runtime_executed": False,
        "source_content_exposed": False,
        "source_file_written": False,
        "registry_read": False,
        "registry_write": False,
    }
    evidence["evidence_sha256"] = contract.runtime_writer_source_anchor_evidence_sha256_v1(evidence)
    observed_rehearsal = InMemoryDormantSourceAnchorRehearsal().rehearse(observed)
    negative_controls = {
        "function_line_shift_denied": _control_denied(function_line_shift=True),
        "writer_missing_denied": _control_denied(writer_missing=True),
        "write_marker_drift_denied": _control_denied(write_marker_drift=True),
        "lock_marker_drift_denied": _control_denied(lock_marker_drift=True),
        "fresh_read_anchor_drift_denied": _control_denied(fresh_read_anchor_drift=True),
        "source_hash_mismatch_denied": _control_denied(source_hash_mismatch=True),
        "runtime_import_request_denied": _control_denied(runtime_import_requested=True),
    }
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_REHEARSAL_V1",
        "spec_sha256": spec["spec_sha256"],
        "evidence_sha256": evidence["evidence_sha256"],
        **observed_rehearsal,
        "negative_controls": negative_controls,
    }
    rehearsal["rehearsal_sha256"] = contract.runtime_writer_source_anchor_rehearsal_sha256_v1(rehearsal)
    return {
        "transaction_placement_result": placement_result,
        "source_anchor_spec": spec,
        "source_anchor_evidence": evidence,
        "source_anchor_rehearsal": rehearsal,
    }


def run_closed_repair_runtime_writer_source_anchor_harness_read_only_v1(repository_root: str | Path) -> dict[str, Any]:
    inputs = build_closed_repair_runtime_writer_source_anchor_inputs_read_only_v1(repository_root)
    preserved = copy.deepcopy(inputs)
    result = contract.evaluate_closed_repair_runtime_writer_source_anchors_offline_v1(**inputs)
    return {
        **result,
        "input_preserved": inputs == preserved,
        "read_only": True,
        "source_content_exposed": False,
        "source_file_written": False,
        "runtime_imported": False,
        "runtime_executed": False,
        "registry_read": False,
        "registry_write": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "harness_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_HARNESS_V1_VERSION,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_WRITER_SOURCE_ANCHOR_HARNESS_V1_VERSION",
    "InMemoryDormantSourceAnchorRehearsal",
    "RuntimeWriterSourceAnchorHarnessBlocked",
    "build_closed_repair_runtime_writer_source_anchor_inputs_read_only_v1",
    "run_closed_repair_runtime_writer_source_anchor_harness_read_only_v1",
]
