"""In-memory AST projection harness for the dormant installation manifest."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_contract_v1 as installation_manifest
import trade_registry_closed_identity_conflict_repair_runtime_installation_manifest_harness_v1 as manifest_harness
import trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_contract_v1 as projection
import trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1 as static_preflight
import trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1 as seam_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-INSTALLATION-PREFLIGHT-PROJECTION-HARNESS-V1"
)

_COORDINATOR_MODULE = (
    "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1"
)
_INVOCATION_MODULE = (
    "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1"
)
_STORE_MODULE = (
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1"
)
_PROVIDER_MODULE = (
    "trade_registry_closed_identity_conflict_repair_production_provider_v1"
)
_MARKER = "_c3_closed_repair_writer_mutation_v1"


class SyntheticRuntimePreflightProjectionBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _pad_to_line(lines: list[str], line_number: int) -> None:
    if line_number <= len(lines):
        raise SyntheticRuntimePreflightProjectionBlocked(
            "SYNTHETIC_SOURCE_LINE_COLLISION"
        )
    lines.extend("" for _ in range(line_number - len(lines) - 1))


def _place_function(
    lines: list[str],
    *,
    line_number: int,
    function: str,
    signature: str,
    body: Sequence[str],
) -> None:
    _pad_to_line(lines, line_number)
    lines.append(f"def {function}{signature}:")
    lines.extend(f"    {statement}" for statement in body)


def _place_statement(lines: list[str], *, line_number: int, statement: str) -> None:
    _pad_to_line(lines, line_number)
    lines.append(statement)


def _writer_bindings_by_component() -> dict[str, list[dict[str, Any]]]:
    bindings = seam_binding.canonical_writer_seam_bindings_v1(
        {"participation_receipt_sha256": "0" * 64}
    )
    grouped: dict[str, list[dict[str, Any]]] = {
        "main.py": [],
        "trade_registry.py": [],
    }
    for binding in bindings:
        grouped[binding["writer"]["component"]].append(binding)
    return grouped


def _build_synthetic_main_source() -> str:
    lines = [
        f"from {_COORDINATOR_MODULE} import build_production_closed_repair_writer_runtime_coordinator_v1",
        f"from {_INVOCATION_MODULE} import build_production_writer_invocation_adapter_v1",
        f"from {_STORE_MODULE} import build_production_raw_transaction_store_v1",
        f"from {_PROVIDER_MODULE} import build_production_closed_repair_provider_v1",
    ]
    _place_function(
        lines,
        line_number=20,
        function=_MARKER,
        signature="(*args, **kwargs)",
        body=("pass",),
    )
    _place_function(
        lines,
        line_number=30,
        function="trade_registry_persistent_storage_fix_v1_status",
        signature="(force=False)",
        body=("return True",),
    )
    _place_function(
        lines,
        line_number=40,
        function="_install_c3_closed_repair_writer_coordination_v1",
        signature="()",
        body=(
            "build_production_closed_repair_writer_runtime_coordinator_v1()",
            "build_production_writer_invocation_adapter_v1()",
            "build_production_raw_transaction_store_v1()",
            "build_production_closed_repair_provider_v1()",
        ),
    )
    _place_function(
        lines,
        line_number=50,
        function="_recover_c3_closed_repair_registry_v1",
        signature="()",
        body=("recover_stale_maintenance_lease_v1()",),
    )
    _place_function(
        lines,
        line_number=60,
        function="_frpp_v1_build_checklist",
        signature="()",
        body=(
            "c3_coordination = c3_runtime_seam_v1.c3_closed_repair_writer_coordination_status_v1()",
            "add(",
            '    "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY",',
            '    c3_coordination.get("enabled") is True',
            '    and c3_coordination.get("coordination_ready") is True',
            '    and c3_coordination.get("runtime_activation_allowed") is True',
            '    and c3_coordination.get("registered_writer_count") == 19',
            '    and c3_coordination.get("all_writers_registered") is True',
            '    and c3_coordination.get("inflight_mutations") == 0',
            '    and c3_coordination.get("shared_lock_backend_ready") is True',
            '    and c3_coordination.get("maintenance_lease_store_ready") is True',
            '    and c3_coordination.get("registry_interlock_ready") is True',
            '    and c3_coordination.get("activation_receipt_verified") is True',
            '    and c3_coordination.get("source_hashes_verified") is True',
            '    and c3_coordination.get("rollback_ready") is True',
            '    and c3_coordination.get("kill_switch_ready") is True,',
            "    True,",
            "    True,",
            "    True,",
            "    c3_coordination,",
            ")",
            "return []",
        ),
    )
    _place_function(
        lines,
        line_number=100,
        function="start_central_runtime_once",
        signature="()",
        body=("pass",),
    )
    for binding in sorted(
        _writer_bindings_by_component()["main.py"],
        key=lambda item: item["source_anchor_line"],
    ):
        writer = binding["writer"]
        _place_function(
            lines,
            line_number=binding["source_anchor_line"],
            function=writer["function"],
            signature=binding["source_signature"],
            body=(f"{_MARKER}()", "pass"),
        )
    _place_statement(
        lines,
        line_number=67500,
        statement="trade_registry_persistent_storage_fix_v1_status()",
    )
    _place_statement(
        lines,
        line_number=67501,
        statement="_install_c3_closed_repair_writer_coordination_v1()",
    )
    _place_statement(
        lines,
        line_number=67502,
        statement="_recover_c3_closed_repair_registry_v1()",
    )
    _place_statement(
        lines,
        line_number=67503,
        statement="start_central_runtime_once()",
    )
    return "\n".join(lines) + "\n"


def _build_synthetic_trade_registry_source() -> str:
    lines: list[str] = []
    _place_function(
        lines,
        line_number=10,
        function=_MARKER,
        signature="(*args, **kwargs)",
        body=("pass",),
    )
    for binding in sorted(
        _writer_bindings_by_component()["trade_registry.py"],
        key=lambda item: item["source_anchor_line"],
    ):
        writer = binding["writer"]
        _place_function(
            lines,
            line_number=binding["source_anchor_line"],
            function=writer["function"],
            signature=binding["source_signature"],
            body=(f"{_MARKER}()", "pass"),
        )
    return "\n".join(lines) + "\n"


def _capability_sources() -> dict[str, str]:
    return {
        f"{_COORDINATOR_MODULE}.py": """
class ClosedRepairWriterRuntimeCoordinatorV1:
    def maintenance_lease(self): pass
    def mutation(self): pass
    def snapshot(self): pass

def build_production_closed_repair_writer_runtime_coordinator_v1(): pass
def recover_stale_maintenance_lease_v1(): pass
""".lstrip(),
        f"{_INVOCATION_MODULE}.py": """
class ProductionWriterInvocationAdapterV1:
    def invoke(self): pass

def build_production_writer_invocation_adapter_v1(): pass
""".lstrip(),
        f"{_STORE_MODULE}.py": """
class ProductionRawTransactionStoreV1:
    def apply_attested_transaction(self): pass
    def load_exact_raw_registry(self): pass
    def reconcile_attested_transaction(self): pass
    def snapshot(self): pass

def build_production_raw_transaction_store_v1(): pass
""".lstrip(),
    }


def build_synthetic_runtime_installation_projected_sources_v1() -> dict[str, str]:
    """Build the exact allowlisted source set entirely in memory."""

    bot_import = (
        "from trade_registry import register_open_trade, update_trade, close_trade\n"
    )
    sources = {
        "main.py": _build_synthetic_main_source(),
        "trade_registry.py": _build_synthetic_trade_registry_source(),
        "bots/meme.py": bot_import,
        "bots/predator.py": bot_import,
        "bots/turtle.py": bot_import,
        **_capability_sources(),
    }
    if set(sources) != set(static_preflight.REQUIRED_SOURCE_KEYS_V1):
        raise SyntheticRuntimePreflightProjectionBlocked(
            "SYNTHETIC_SOURCE_SET_INVALID"
        )
    return {
        key: sources[key] for key in static_preflight.REQUIRED_SOURCE_KEYS_V1
    }


def _remove_exact(source: str, needle: str, reason: str) -> str:
    if source.count(needle) != 1:
        raise SyntheticRuntimePreflightProjectionBlocked(reason)
    return source.replace(needle, "", 1)


def _negative_control_sources(
    control_id: str, sources: Mapping[str, str]
) -> dict[str, str]:
    mutated = copy.deepcopy(dict(sources))
    if control_id == "ALL_19_WRITER_BODY_SEAMS_COORDINATED":
        needle = f"    {_MARKER}()\n"
        if needle not in mutated["trade_registry.py"]:
            raise SyntheticRuntimePreflightProjectionBlocked(
                "WRITER_MARKER_CONTROL_TARGET_MISSING"
            )
        mutated["trade_registry.py"] = mutated["trade_registry.py"].replace(
            needle, "    pass\n", 1
        )
    elif control_id == "C3_RUNTIME_DEPENDENCIES_IMPORTED":
        needle = (
            f"from {_COORDINATOR_MODULE} import "
            "build_production_closed_repair_writer_runtime_coordinator_v1\n"
        )
        mutated["main.py"] = _remove_exact(
            mutated["main.py"], needle, "COORDINATOR_IMPORT_CONTROL_TARGET_MISSING"
        )
    elif control_id == "PRODUCTION_TRANSACTION_STORE_PRESENT":
        needle = (
            f"from {_STORE_MODULE} import "
            "build_production_raw_transaction_store_v1\n"
        )
        mutated["main.py"] = _remove_exact(
            mutated["main.py"], needle, "STORE_IMPORT_CONTROL_TARGET_MISSING"
        )
    elif control_id == "PERSISTENCE_BOOTSTRAP_BEFORE_RUNTIME_START":
        call = "trade_registry_persistent_storage_fix_v1_status()\n"
        mutated["main.py"] = _remove_exact(
            mutated["main.py"], call, "PERSISTENCE_CALL_CONTROL_TARGET_MISSING"
        )
        mutated["main.py"] += call
    elif control_id == "C3_PROVIDER_INSTALLED_BEFORE_RUNTIME_START":
        mutated["main.py"] = _remove_exact(
            mutated["main.py"],
            "_install_c3_closed_repair_writer_coordination_v1()\n",
            "PROVIDER_CALL_CONTROL_TARGET_MISSING",
        )
    elif control_id == "C3_PROVIDER_BINDS_PRODUCTION_CAPABILITIES":
        mutated["main.py"] = _remove_exact(
            mutated["main.py"],
            "    build_production_writer_invocation_adapter_v1()\n",
            "PROVIDER_BUILDER_CONTROL_TARGET_MISSING",
        )
    elif control_id == "C3_STARTUP_RECOVERY_BEFORE_RUNTIME_START":
        mutated["main.py"] = _remove_exact(
            mutated["main.py"],
            "_recover_c3_closed_repair_registry_v1()\n",
            "RECOVERY_CALL_CONTROL_TARGET_MISSING",
        )
    elif control_id == "BY_NAME_BOT_WRITER_IMPORTS_GATED":
        mutated["bots/meme.py"] = (
            "from trade_registry import register_open_trade, update_trade\n"
        )
    elif control_id == "LIVE_PREFLIGHT_REQUIRES_C3_COORDINATION":
        mutated["main.py"] = mutated["main.py"].replace(
            "TRADE_REGISTRY_C3_WRITER_COORDINATION_READY",
            "TRADE_REGISTRY_LEGACY_ONLY",
            1,
        )
    else:
        raise SyntheticRuntimePreflightProjectionBlocked(
            "UNKNOWN_NEGATIVE_CONTROL"
        )
    return mutated


def build_synthetic_closed_repair_runtime_installation_preflight_projection_inputs_v1() -> dict[str, Any]:
    manifest_inputs = (
        manifest_harness.build_synthetic_closed_repair_runtime_installation_manifest_inputs_v1()
    )
    manifest_result = (
        installation_manifest.evaluate_closed_repair_runtime_installation_manifest_offline_v1(
            **manifest_inputs
        )
    )
    if manifest_result.get("ok") is not True:
        raise AssertionError("synthetic installation manifest unexpectedly failed")
    manifest_receipt = manifest_result["installation_manifest_receipt"]
    sources = build_synthetic_runtime_installation_projected_sources_v1()
    projected = static_preflight.evaluate_closed_repair_runtime_static_preflight_v1(
        sources
    )
    control_receipts = []
    for control_id in projection.canonical_resolved_runtime_preflight_blockers_v1():
        controlled_sources = _negative_control_sources(control_id, sources)
        controlled = static_preflight.evaluate_closed_repair_runtime_static_preflight_v1(
            controlled_sources
        )
        control_receipts.append(
            {
                "control_id": control_id,
                "observed_blockers": list(controlled.get("blockers") or ()),
                "static_readiness": controlled.get("static_readiness") is True,
                "production_ready": controlled.get("production_ready") is True,
                "live_allowed": controlled.get("live_allowed") is True,
                "runtime_executed": controlled.get("runtime_executed") is True,
                "source_executed": False,
            }
        )
    evidence = {
        "evidence_version": "SYNTHETIC_CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_EVIDENCE_V1",
        "upstream_installation_manifest_receipt_sha256": manifest_receipt[
            "installation_manifest_receipt_sha256"
        ],
        "resolved_blocker_codes": projection.canonical_resolved_runtime_preflight_blockers_v1(),
        "source_keys": list(static_preflight.REQUIRED_SOURCE_KEYS_V1),
        "projected_preflight_result": projected,
        "negative_control_receipts": control_receipts,
        "negative_control_receipts_sha256": projection._stable_sha256(
            control_receipts
        ),
        "safety_envelope": {
            "synthetic_strings_only": True,
            "real_files_read": False,
            "real_files_written": False,
            "projected_source_executed": False,
            "runtime_module_imported": False,
            "runtime_started": False,
            "bot_started": False,
            "registry_accessed": False,
            "network_accessed": False,
            "runtime_install_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        },
    }
    evidence["evidence_sha256"] = (
        projection.runtime_installation_preflight_projection_evidence_sha256_v1(
            evidence
        )
    )
    return {
        "installation_manifest_result": manifest_result,
        "projection_evidence": evidence,
    }


def run_synthetic_closed_repair_runtime_installation_preflight_projection_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_runtime_installation_preflight_projection_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = projection._stable_sha256(before)
    first = projection.evaluate_closed_repair_runtime_installation_preflight_projection_offline_v1(
        **inputs
    )
    second = projection.evaluate_closed_repair_runtime_installation_preflight_projection_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = projection._stable_sha256(inputs)
    receipt = first.get("projection_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("projection_contract_verified") is True
        and first.get("synthetic_static_readiness_proven") is True
        and first.get("negative_controls_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("runtime_start_allowed") is False
        and first.get("live_allowed") is False
        and first.get("runtime_imported") is False
        and first.get("runtime_executed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("resolved_blocker_count") == 9
        and receipt.get("negative_control_count") == 9
        and receipt.get("real_runtime_readiness_proven") is False
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_V1_HARNESS_PASSED_SYNTHETIC_PRODUCTION_BLOCKED"
            if ok
            else "CLOSED_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_HARNESS_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "ast_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "runtime_start_allowed": False,
        "live_allowed": False,
        "runtime_imported": False,
        "runtime_executed": False,
        "write_executed": False,
        "registry_write": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "projection_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_INSTALLATION_PREFLIGHT_PROJECTION_HARNESS_V1_VERSION",
    "SyntheticRuntimePreflightProjectionBlocked",
    "build_synthetic_closed_repair_runtime_installation_preflight_projection_inputs_v1",
    "build_synthetic_runtime_installation_projected_sources_v1",
    "run_synthetic_closed_repair_runtime_installation_preflight_projection_harness_v1",
]
