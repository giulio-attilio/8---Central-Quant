"""In-memory harness for the dormant runtime installation manifest."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_contract_v1 as manifest
import trade_registry_closed_identity_conflict_repair_writer_bootstrap_gate_contract_v1 as bootstrap_gate
import trade_registry_closed_identity_conflict_repair_writer_bootstrap_gate_harness_v1 as bootstrap_harness


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-INSTALLATION-MANIFEST-HARNESS-V1"
)


class SyntheticRuntimeInstallationManifestBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantRuntimeInstallationRehearsal:
    """Rehearse ordering and rollback without accepting executable objects."""

    def __init__(
        self,
        *,
        writers: Sequence[Mapping[str, Any]],
        by_name_bot_gates: Sequence[Mapping[str, Any]],
    ) -> None:
        self._writers = copy.deepcopy(list(writers))
        self._bot_gates = copy.deepcopy(list(by_name_bot_gates))
        self._events: list[str] = []
        self._rollback_events: list[str] = []

    @property
    def events(self) -> tuple[str, ...]:
        return tuple(self._events)

    @property
    def rollback_events(self) -> tuple[str, ...]:
        return tuple(self._rollback_events)

    def rehearse(
        self,
        *,
        phase_event_sequence: Sequence[str] | None = None,
        writer_count: int = 19,
        provider_default_off: bool = True,
        provider_before_recovery: bool = True,
        recovery_before_runtime_start: bool = True,
        body_seams_before_bot_imports: bool = True,
        live_gate_default_closed: bool = True,
        executable_object_provided: bool = False,
    ) -> dict[str, Any]:
        expected_writers = manifest.canonical_runtime_installation_writer_manifest_v1()
        expected_bots = manifest.canonical_runtime_installation_bot_import_gates_v1()
        expected_phases = [
            item["phase"]
            for item in manifest.canonical_runtime_installation_phases_v1()
        ]
        supplied_phases = (
            expected_phases
            if phase_event_sequence is None
            else list(phase_event_sequence)
        )
        if executable_object_provided:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "EXECUTABLE_OBJECT_FORBIDDEN"
            )
        if self._writers != expected_writers or int(writer_count) != 19:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "EXACTLY_19_WRITER_SEAMS_REQUIRED"
            )
        if self._bot_gates != expected_bots:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "BY_NAME_BOT_GATE_MANIFEST_INVALID"
            )
        if supplied_phases != expected_phases:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "INSTALLATION_PHASE_ORDER_INVALID"
            )
        if not provider_default_off:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "PROVIDER_MUST_REMAIN_DEFAULT_OFF"
            )
        if not provider_before_recovery:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "RECOVERY_BEFORE_PROVIDER_DENIED"
            )
        if not recovery_before_runtime_start:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "RUNTIME_BEFORE_RECOVERY_DENIED"
            )
        if not body_seams_before_bot_imports:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "BOT_IMPORT_BEFORE_BODY_SEAMS_DENIED"
            )
        if not live_gate_default_closed:
            raise SyntheticRuntimeInstallationManifestBlocked(
                "LIVE_GATE_OPEN_DENIED"
            )

        self._events = list(supplied_phases)
        writer_receipts = [
            {
                "writer_id": item["writer_id"],
                "body_seam_attested_synthetically": True,
                "real_body_modified": False,
                "writer_invoked": False,
            }
            for item in self._writers
        ]
        bot_receipts = [
            {
                "component": item["component"],
                "all_19_seams_ready_before_synthetic_release": True,
                "real_module_imported": False,
            }
            for item in self._bot_gates
        ]
        return {
            "phase_event_sequence": list(self._events),
            "writer_receipts": writer_receipts,
            "by_name_bot_gate_receipts": bot_receipts,
        }

    def rehearse_rollback(self) -> dict[str, Any]:
        self._rollback_events = [
            item["step"]
            for item in manifest.canonical_runtime_installation_rollback_v1()
        ]
        return {
            "trigger": "SYNTHETIC_PROVIDER_INSTALL_FAILURE",
            "event_sequence": list(self._rollback_events),
            "provider_graph_published": False,
            "runtime_started": False,
            "bot_imported": False,
            "registry_bytes_changed": False,
            "live_authorized": False,
            "retry_requires_fresh_preflight": True,
        }


def build_synthetic_closed_repair_runtime_installation_manifest_inputs_v1() -> dict[str, Any]:
    bootstrap_inputs = (
        bootstrap_harness.build_synthetic_closed_repair_writer_bootstrap_gate_inputs_v1()
    )
    bootstrap_result = (
        bootstrap_gate.evaluate_closed_repair_writer_bootstrap_gate_offline_v1(
            **bootstrap_inputs
        )
    )
    if bootstrap_result.get("ok") is not True:
        raise AssertionError("synthetic bootstrap gate unexpectedly failed")
    bootstrap_receipt = bootstrap_result["bootstrap_gate_receipt"]
    writers = manifest.canonical_runtime_installation_writer_manifest_v1()
    imports = manifest.canonical_runtime_installation_import_manifest_v1()
    bots = manifest.canonical_runtime_installation_bot_import_gates_v1()
    phases = manifest.canonical_runtime_installation_phases_v1()
    rollback = manifest.canonical_runtime_installation_rollback_v1()
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_SPEC_V1",
        "upstream_bootstrap_gate_receipt_sha256": bootstrap_receipt[
            "bootstrap_gate_receipt_sha256"
        ],
        "writer_manifest": writers,
        "writer_manifest_sha256": manifest._stable_sha256(writers),
        "runtime_import_manifest": imports,
        "runtime_import_manifest_sha256": manifest._stable_sha256(imports),
        "by_name_bot_import_gates": bots,
        "by_name_bot_import_gates_sha256": manifest._stable_sha256(bots),
        "installation_phases": phases,
        "installation_phases_sha256": manifest._stable_sha256(phases),
        "rollback_protocol": rollback,
        "rollback_protocol_sha256": manifest._stable_sha256(rollback),
        "provider_installation": {
            "installer_function": "_install_c3_closed_repair_writer_coordination_v1",
            "aggregate_provider_builder": "build_production_closed_repair_provider_v1",
            "three_capability_builders_called_directly": True,
            "default_enabled": False,
            "install_before_recovery": True,
            "install_before_bot_imports": True,
            "install_before_runtime_start": True,
            "late_monkey_patch_forbidden": True,
            "real_provider_installed": False,
        },
        "startup_recovery": {
            "function": "_recover_c3_closed_repair_registry_v1",
            "provider_required_before_recovery": True,
            "clean_recovery_required_before_bot_imports": True,
            "clean_recovery_required_before_runtime_start": True,
            "unknown_or_stale_state_fails_closed": True,
            "real_recovery_executed": False,
        },
        "live_preflight_gate": {
            "check_code": "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY",
            "blocking": True,
            "default_state": "CLOSED",
            "provider_attestation_required": True,
            "all_19_writers_required": True,
            "startup_recovery_clean_required": True,
            "runtime_start_function": "start_central_runtime_once",
            "can_enable_live": False,
        },
        "safety_envelope": {
            "contract_only": True,
            "default_off": True,
            "synthetic_memory_only": True,
            "real_source_imported": False,
            "real_callable_bound": False,
            "real_provider_installed": False,
            "real_recovery_executed": False,
            "real_bot_imported": False,
            "real_thread_started": False,
            "real_startup_changed": False,
            "runtime_install_allowed": False,
            "apply_entrypoint_present": False,
        },
    }
    spec["spec_sha256"] = manifest.runtime_installation_manifest_spec_sha256_v1(
        spec
    )

    synthetic = InMemoryDormantRuntimeInstallationRehearsal(
        writers=writers, by_name_bot_gates=bots
    )
    observed = synthetic.rehearse()
    writer_receipts = observed["writer_receipts"]
    bot_receipts = observed["by_name_bot_gate_receipts"]
    rehearsal = {
        "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_REHEARSAL_V1",
        "upstream_bootstrap_gate_receipt_sha256": bootstrap_receipt[
            "bootstrap_gate_receipt_sha256"
        ],
        "runtime_installation_manifest_spec_sha256": spec["spec_sha256"],
        "phase_event_sequence": observed["phase_event_sequence"],
        "writer_count": 19,
        "all_body_seams_before_bot_imports": True,
        "provider_before_recovery": True,
        "recovery_before_runtime_start": True,
        "live_gate_closed_before_runtime_start": True,
        "writer_receipts": writer_receipts,
        "writer_receipts_sha256": manifest._stable_sha256(writer_receipts),
        "by_name_bot_gate_receipts": bot_receipts,
        "by_name_bot_gate_receipts_sha256": manifest._stable_sha256(bot_receipts),
        "live_gate_rehearsal": {
            "check_code": "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY",
            "default_closed": True,
            "synthetic_prerequisites_observed": True,
            "live_authorized": False,
            "flag_changed": False,
        },
        "rollback_rehearsal": synthetic.rehearse_rollback(),
        "safety_envelope": {
            "synthetic_memory_only": True,
            "filesystem_accessed": False,
            "network_accessed": False,
            "real_source_imported": False,
            "real_callable_bound": False,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_install_allowed": False,
            "runtime_start_allowed": False,
            "live_allowed": False,
            "apply_entrypoint_present": False,
            "no_order_sent": True,
        },
    }
    rehearsal["rehearsal_sha256"] = (
        manifest.runtime_installation_manifest_rehearsal_sha256_v1(rehearsal)
    )
    return {
        "bootstrap_gate_result": bootstrap_result,
        "runtime_installation_manifest_spec": spec,
        "runtime_installation_manifest_rehearsal": rehearsal,
    }


def run_synthetic_closed_repair_runtime_installation_manifest_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_runtime_installation_manifest_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = manifest._stable_sha256(before)
    first = manifest.evaluate_closed_repair_runtime_installation_manifest_offline_v1(
        **inputs
    )
    second = manifest.evaluate_closed_repair_runtime_installation_manifest_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = manifest._stable_sha256(inputs)
    receipt = first.get("installation_manifest_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("installation_manifest_contract_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("rollback_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("live_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("writer_count") == 19
        and receipt.get("by_name_bot_gate_count") == 3
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_V1_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "CLOSED_REPAIR_RUNTIME_INSTALLATION_MANIFEST_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "installation_manifest_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_MANIFEST_HARNESS_V1_VERSION",
    "InMemoryDormantRuntimeInstallationRehearsal",
    "SyntheticRuntimeInstallationManifestBlocked",
    "build_synthetic_closed_repair_runtime_installation_manifest_inputs_v1",
    "run_synthetic_closed_repair_runtime_installation_manifest_harness_v1",
]
