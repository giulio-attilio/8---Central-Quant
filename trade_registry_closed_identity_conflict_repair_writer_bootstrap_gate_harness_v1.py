"""In-memory harness for the dormant pre-runtime writer bootstrap gate."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_bootstrap_gate_contract_v1 as bootstrap_gate
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_binding
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_harness_v1 as seam_binding_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-BOOTSTRAP-GATE-HARNESS-V1"
)


class SyntheticWriterBootstrapGateBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantWriterBootstrapGate:
    """State-free synthetic gate that cannot accept or execute a callable."""

    def __init__(self, bot_surfaces: Sequence[Mapping[str, Any]]) -> None:
        self._bot_surfaces = copy.deepcopy(list(bot_surfaces))
        self._synthetic_import_gate_passed = False
        self._synthetic_thread_gate_passed = False

    @property
    def synthetic_import_gate_passed(self) -> bool:
        return self._synthetic_import_gate_passed

    @property
    def synthetic_thread_gate_passed(self) -> bool:
        return self._synthetic_thread_gate_passed

    def rehearse(
        self,
        *,
        upstream_chain_valid: bool = True,
        writer_count: int = 19,
        sink_owner_token_valid: bool = True,
        phase_event_sequence: Sequence[str] | None = None,
        thread_requested_before_import_gate: bool = False,
        runtime_callable_provided: bool = False,
    ) -> dict[str, Any]:
        expected_sequence = [
            item["phase"]
            for item in bootstrap_gate.canonical_writer_bootstrap_phases_v1()
        ]
        supplied_sequence = (
            expected_sequence
            if phase_event_sequence is None
            else list(phase_event_sequence)
        )
        if not upstream_chain_valid:
            raise SyntheticWriterBootstrapGateBlocked("UPSTREAM_CHAIN_INVALID")
        if int(writer_count) != 19:
            raise SyntheticWriterBootstrapGateBlocked("EXACTLY_19_SEAMS_REQUIRED")
        if not sink_owner_token_valid:
            raise SyntheticWriterBootstrapGateBlocked("SINK_OWNER_TOKEN_INVALID")
        if supplied_sequence != expected_sequence:
            raise SyntheticWriterBootstrapGateBlocked("BOOTSTRAP_PHASE_ORDER_INVALID")
        if thread_requested_before_import_gate:
            raise SyntheticWriterBootstrapGateBlocked(
                "THREAD_BEFORE_IMPORT_GATE_DENIED"
            )
        if runtime_callable_provided:
            raise SyntheticWriterBootstrapGateBlocked("RUNTIME_CALLABLE_FORBIDDEN")
        expected_bots = bootstrap_gate.canonical_writer_bootstrap_bot_surfaces_v1()
        if self._bot_surfaces != expected_bots:
            raise SyntheticWriterBootstrapGateBlocked("BOT_SURFACE_MANIFEST_INVALID")

        self._synthetic_import_gate_passed = True
        self._synthetic_thread_gate_passed = True
        bot_receipts = [
            {
                "bot_id": item["bot_id"],
                "component": item["component"],
                "registry_import_mode": item["registry_import_mode"],
                "synthetic_import_gate_passed": True,
                "synthetic_thread_gate_passed": True,
                "real_module_imported": False,
                "real_thread_started": False,
            }
            for item in self._bot_surfaces
        ]
        return {
            "phase_event_sequence": supplied_sequence,
            "bot_gate_receipts": bot_receipts,
            "sink_owner_token_preflight": {
                "synthetic_token_present": True,
                "namespace_matches": True,
                "owner_matches": True,
                "nested_depth": 2,
                "synthetic_preflight_accepted": True,
                "real_sink_called": False,
            },
        }


def build_synthetic_closed_repair_writer_bootstrap_gate_inputs_v1() -> dict[str, Any]:
    seam_inputs = seam_binding_harness.build_synthetic_closed_repair_writer_seam_binding_inputs_v1()
    seam_result = seam_binding.evaluate_closed_repair_writer_seam_binding_offline_v1(
        **seam_inputs
    )
    if seam_result.get("ok") is not True:
        raise AssertionError("synthetic writer seam binding unexpectedly failed")
    seam_receipt = seam_result["seam_binding_receipt"]
    phases = bootstrap_gate.canonical_writer_bootstrap_phases_v1()
    bot_surfaces = bootstrap_gate.canonical_writer_bootstrap_bot_surfaces_v1()
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_SPEC_V1",
        "upstream_seam_binding_receipt_sha256": seam_receipt[
            "seam_binding_receipt_sha256"
        ],
        "upstream_participation_receipt_sha256": seam_receipt[
            "upstream_participation_receipt_sha256"
        ],
        "bootstrap_phases": phases,
        "bootstrap_phases_sha256": bootstrap_gate._stable_sha256(phases),
        "bot_surfaces": bot_surfaces,
        "bot_surfaces_sha256": bootstrap_gate._stable_sha256(bot_surfaces),
        "startup_interlock": {
            "default_state": "CLOSED",
            "all_upstream_attestations_required": True,
            "exact_writer_count_required": 19,
            "sink_owner_token_preflight_required": True,
            "bot_import_denied_before_all_seams": True,
            "bot_thread_denied_before_import_gate": True,
            "by_name_imports_require_function_body_seams": True,
            "unknown_or_stale_evidence_fails_closed": True,
            "runtime_callable_absent": True,
        },
        "safety_envelope": {
            "contract_only": True,
            "synthetic_memory_only": True,
            "real_source_imported": False,
            "real_callable_bound": False,
            "real_bot_imported": False,
            "real_thread_started": False,
            "real_startup_changed": False,
            "runtime_bootstrap_allowed": False,
            "apply_entrypoint_present": False,
        },
    }
    spec["spec_sha256"] = bootstrap_gate.writer_bootstrap_gate_spec_sha256_v1(
        spec
    )
    synthetic = InMemoryDormantWriterBootstrapGate(bot_surfaces).rehearse()
    bot_receipts = synthetic["bot_gate_receipts"]
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_REHEARSAL_V1",
        "upstream_seam_binding_receipt_sha256": seam_receipt[
            "seam_binding_receipt_sha256"
        ],
        "bootstrap_gate_spec_sha256": spec["spec_sha256"],
        "writer_count": 19,
        "bot_count": 7,
        "phase_event_sequence": synthetic["phase_event_sequence"],
        "all_19_seams_ready_before_import_gate": True,
        "sink_preflight_before_import_gate": True,
        "import_gate_before_thread_gate": True,
        "bot_gate_receipts": bot_receipts,
        "bot_gate_receipts_sha256": bootstrap_gate._stable_sha256(bot_receipts),
        "sink_owner_token_preflight": synthetic["sink_owner_token_preflight"],
        "negative_controls": {
            "missing_seam_denies_import": True,
            "invalid_sink_token_denies_import": True,
            "wrong_phase_order_denies_import": True,
            "thread_before_import_denied": True,
            "runtime_callable_denied": True,
        },
        "safety_envelope": {
            "synthetic_memory_only": True,
            "real_source_imported": False,
            "real_callable_bound": False,
            "real_bot_imported": False,
            "real_thread_started": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_bootstrap_allowed": False,
            "apply_entrypoint_present": False,
            "no_order_sent": True,
        },
    }
    rehearsal["rehearsal_sha256"] = (
        bootstrap_gate.writer_bootstrap_gate_rehearsal_sha256_v1(rehearsal)
    )
    return {
        "seam_binding_result": seam_result,
        "bootstrap_gate_spec": spec,
        "bootstrap_gate_rehearsal": rehearsal,
    }


def run_synthetic_closed_repair_writer_bootstrap_gate_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_writer_bootstrap_gate_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = bootstrap_gate._stable_sha256(before)
    first = bootstrap_gate.evaluate_closed_repair_writer_bootstrap_gate_offline_v1(
        **inputs
    )
    second = bootstrap_gate.evaluate_closed_repair_writer_bootstrap_gate_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = bootstrap_gate._stable_sha256(inputs)
    receipt = first.get("bootstrap_gate_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("bootstrap_gate_contract_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("synthetic_bot_import_gate_passed") is True
        and first.get("synthetic_bot_thread_gate_passed") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_bootstrap_allowed") is False
        and first.get("real_bot_imported") is False
        and first.get("real_thread_started") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("writer_count") == 19
        and receipt.get("bot_count") == 7
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_V1_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "CLOSED_REPAIR_WRITER_BOOTSTRAP_GATE_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_HARNESS_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_bootstrap_allowed": False,
        "real_bot_imported": False,
        "real_thread_started": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "bootstrap_gate_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_BOOTSTRAP_GATE_HARNESS_V1_VERSION",
    "InMemoryDormantWriterBootstrapGate",
    "SyntheticWriterBootstrapGateBlocked",
    "build_synthetic_closed_repair_writer_bootstrap_gate_inputs_v1",
    "run_synthetic_closed_repair_writer_bootstrap_gate_harness_v1",
]
