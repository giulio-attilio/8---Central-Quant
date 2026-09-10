"""Offline mapping harness for the dormant V1-to-V2 schema bridge.

Only protected schema plans and hash-only mapping traces are produced.  No
request or result DTO accepted by an operational boundary is materialized.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2 as compatibility_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2 as bridge_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-SCHEMA-BRIDGE-HARNESS-V2"
)
MAPPING_TRACE_VERSION = "C3_HANDOFF_V1_BACKEND_V2_MAPPING_TRACE_PROTECTED_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TRACE_ENTRY_KEYS = frozenset(
    {
        "direction", "ordinal", "source", "target", "rule",
        "source_sample_sha256", "oracle_relation",
        "expected_target_sha256", "materialized",
    }
)
_TRACE_KEYS = frozenset(
    {
        "trace_version", "bridge_plan_sha256", "apply_trace",
        "terminal_trace", "recovery_trace", "apply_target_keys",
        "terminal_target_keys", "recovery_target_keys", "preserve_exact_count",
        "forced_constant_count", "deferred_mapping_count",
        "materialized_target_count", "executable_request_materialized",
        "executable_result_materialized", "authorization_consumed",
        "lease_validated_live", "provider_called", "store_called",
        "backend_called", "writer_called", "lock_acquired",
        "filesystem_accessed", "real_registry_accessed", "network_accessed",
        "broker_called", "write_executed", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "synthetic_only", "trace_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _trace_sha(value: Mapping[str, Any]) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != "trace_sha256"}
    )


def _oracle(rule: str, source_sha: str) -> tuple[str, str | None]:
    if rule.startswith("PRESERVE") or rule.startswith("RESTORE"):
        return "EQUAL_HASH", source_sha
    if rule == "FORCE_TRUE":
        return "FORCED_TRUE", backend_v2.stable_sha256_v2(True)
    if rule == "FORCE_FALSE":
        return "FORCED_FALSE", backend_v2.stable_sha256_v2(False)
    return "DEFERRED_RUNTIME_EVIDENCE", None


def _build_direction_trace(
    direction: str,
    mappings: list[dict[str, Any]],
    plan_sha256: str,
) -> list[dict[str, Any]]:
    trace = []
    for ordinal, item in enumerate(mappings, start=1):
        source_sha = backend_v2.stable_sha256_v2(
            {
                "kind": "C3_SCHEMA_MAPPING_SOURCE_SAMPLE_V1",
                "bridge_plan_sha256": plan_sha256,
                "direction": direction,
                "ordinal": ordinal,
                "source": item["source"],
            }
        )
        relation, expected_sha = _oracle(item["rule"], source_sha)
        trace.append(
            {
                "direction": direction,
                "ordinal": ordinal,
                "source": item["source"],
                "target": item["target"],
                "rule": item["rule"],
                "source_sample_sha256": source_sha,
                "oracle_relation": relation,
                "expected_target_sha256": expected_sha,
                "materialized": False,
            }
        )
    return trace


def _target_keys(mappings: list[dict[str, Any]], prefix: str) -> list[str]:
    return sorted(
        item["target"].split(".", 1)[1]
        for item in mappings
        if item["target"].startswith(prefix)
    )


@dataclass(frozen=True, repr=False)
class ProtectedSchemaBridgeMappingTraceV2:
    bridge_plan_sha256: str = field(repr=False)
    trace: Mapping[str, Any] = field(repr=False)
    trace_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSchemaBridgeMappingTraceV2(<protected>)"


def protected_mapping_trace_valid_v2(
    value: Any,
    plan: bridge_contract.ProtectedHandoffV1BackendV2SchemaBridgePlan,
) -> bool:
    if (
        not isinstance(value, ProtectedSchemaBridgeMappingTraceV2)
        or not bridge_contract.protected_schema_bridge_plan_valid(plan)
    ):
        return False
    trace = value.trace
    if type(trace) is not dict or set(trace) != _TRACE_KEYS:
        return False
    plan_data = plan.plan
    expected_apply = _build_direction_trace(
        "APPLY", plan_data["apply_field_mapping"], plan.plan_sha256
    )
    expected_terminal = _build_direction_trace(
        "TERMINAL", plan_data["terminal_field_mapping"], plan.plan_sha256
    )
    expected_recovery = _build_direction_trace(
        "RECOVERY", plan_data["recovery_field_mapping"], plan.plan_sha256
    )
    all_entries = expected_apply + expected_terminal + expected_recovery
    try:
        return bool(
            trace["trace_version"] == MAPPING_TRACE_VERSION
            and trace["bridge_plan_sha256"] == plan.plan_sha256
            and trace["apply_trace"] == expected_apply
            and trace["terminal_trace"] == expected_terminal
            and trace["recovery_trace"] == expected_recovery
            and all(
                type(item) is dict
                and set(item) == _TRACE_ENTRY_KEYS
                and _valid_sha(item["source_sample_sha256"])
                and item["materialized"] is False
                for item in (
                    trace["apply_trace"]
                    + trace["terminal_trace"]
                    + trace["recovery_trace"]
                )
            )
            and trace["apply_target_keys"]
            == sorted(backend_v2._TRANSACTION_REQUEST_KEYS)
            and trace["terminal_target_keys"]
            == sorted(envelope_v1._TERMINAL_RESULT_KEYS)
            and trace["recovery_target_keys"]
            == sorted(backend_v2._RECOVERY_REQUEST_KEYS)
            and trace["preserve_exact_count"]
            == sum(item["oracle_relation"] == "EQUAL_HASH" for item in all_entries)
            and trace["forced_constant_count"]
            == sum(item["oracle_relation"].startswith("FORCED_") for item in all_entries)
            and trace["deferred_mapping_count"]
            == sum(
                item["oracle_relation"] == "DEFERRED_RUNTIME_EVIDENCE"
                for item in all_entries
            )
            and trace["materialized_target_count"] == 0
            and all(
                trace[key] is False
                for key in (
                    "executable_request_materialized", "executable_result_materialized",
                    "authorization_consumed", "lease_validated_live",
                    "provider_called", "store_called", "backend_called",
                    "writer_called", "lock_acquired", "filesystem_accessed",
                    "real_registry_accessed", "network_accessed", "broker_called",
                    "write_executed", "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and trace["synthetic_only"] is True
            and value.bridge_plan_sha256 == plan.plan_sha256
            and value.trace_sha256 == trace["trace_sha256"]
            and _valid_sha(trace["trace_sha256"])
            and hmac.compare_digest(trace["trace_sha256"], _trace_sha(trace))
        )
    except Exception:
        return False


def build_mapping_trace_offline_v2(
    plan: bridge_contract.ProtectedHandoffV1BackendV2SchemaBridgePlan,
) -> ProtectedSchemaBridgeMappingTraceV2:
    if not bridge_contract.protected_schema_bridge_plan_valid(plan):
        raise ValueError("VALID_PROTECTED_SCHEMA_BRIDGE_PLAN_REQUIRED")
    plan_data = plan.plan
    apply_trace = _build_direction_trace(
        "APPLY", plan_data["apply_field_mapping"], plan.plan_sha256
    )
    terminal_trace = _build_direction_trace(
        "TERMINAL", plan_data["terminal_field_mapping"], plan.plan_sha256
    )
    recovery_trace = _build_direction_trace(
        "RECOVERY", plan_data["recovery_field_mapping"], plan.plan_sha256
    )
    all_entries = apply_trace + terminal_trace + recovery_trace
    trace = {
        "trace_version": MAPPING_TRACE_VERSION,
        "bridge_plan_sha256": plan.plan_sha256,
        "apply_trace": apply_trace,
        "terminal_trace": terminal_trace,
        "recovery_trace": recovery_trace,
        "apply_target_keys": _target_keys(plan_data["apply_field_mapping"], "v2."),
        "terminal_target_keys": _target_keys(plan_data["terminal_field_mapping"], "v1."),
        "recovery_target_keys": _target_keys(plan_data["recovery_field_mapping"], "v2."),
        "preserve_exact_count": sum(
            item["oracle_relation"] == "EQUAL_HASH" for item in all_entries
        ),
        "forced_constant_count": sum(
            item["oracle_relation"].startswith("FORCED_") for item in all_entries
        ),
        "deferred_mapping_count": sum(
            item["oracle_relation"] == "DEFERRED_RUNTIME_EVIDENCE"
            for item in all_entries
        ),
        "materialized_target_count": 0,
        "executable_request_materialized": False,
        "executable_result_materialized": False,
        "authorization_consumed": False,
        "lease_validated_live": False,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "synthetic_only": True,
    }
    trace["trace_sha256"] = _trace_sha(trace)
    protected = ProtectedSchemaBridgeMappingTraceV2(
        bridge_plan_sha256=plan.plan_sha256,
        trace=copy.deepcopy(trace),
        trace_sha256=trace["trace_sha256"],
    )
    if not protected_mapping_trace_valid_v2(protected, plan):
        raise ValueError("SCHEMA_BRIDGE_MAPPING_TRACE_INTERNAL_INVALID")
    return protected


def run_handoff_v1_backend_v2_schema_bridge_harness_v2(
    compatibility_bundle: compatibility_v2.ProtectedWriterCoordinationCompatibilityBundleV2,
) -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_HARNESS_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_HARNESS_V2_VERSION,
        "protected_plan": None,
        "protected_trace": None,
        "complete_apply_coverage": False,
        "complete_terminal_coverage": False,
        "complete_recovery_coverage": False,
        "executable_request_materialized": False,
        "executable_result_materialized": False,
        "authorization_consumed": False,
        "lease_validated_live": False,
        "provider_called": False,
        "store_called": False,
        "backend_called": False,
        "writer_called": False,
        "lock_acquired": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        planner = bridge_contract.DormantHandoffV1BackendV2SchemaBridge(
            bridge_contract.HandoffV1BackendV2SchemaBridgeConfig(
                enabled=True,
                scope_attestation=bridge_contract.OFFLINE_HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_SCOPE_ATTESTATION,
                expected_compatibility_bundle_sha256=compatibility_bundle.bundle_sha256,
            )
        )
        plan_result = planner.plan_offline(compatibility_bundle)
        plan = plan_result.get("protected_plan")
        trace = build_mapping_trace_offline_v2(plan)
    except Exception:
        base["reason"] = "SCHEMA_BRIDGE_HARNESS_INPUT_OR_TRACE_INVALID"
        return base
    trace_data = trace.trace
    ok = bool(
        plan_result.get("ok") is True
        and bridge_contract.protected_schema_bridge_plan_valid(plan)
        and protected_mapping_trace_valid_v2(trace, plan)
        and trace_data["apply_target_keys"] == sorted(backend_v2._TRANSACTION_REQUEST_KEYS)
        and trace_data["terminal_target_keys"] == sorted(envelope_v1._TERMINAL_RESULT_KEYS)
        and trace_data["recovery_target_keys"] == sorted(backend_v2._RECOVERY_REQUEST_KEYS)
        and trace_data["materialized_target_count"] == 0
    )
    if not ok:
        base["reason"] = "SCHEMA_BRIDGE_HARNESS_COVERAGE_INVALID"
        return base
    base.update(
        {
            "ok": True,
            "status": "HANDOFF_V1_BACKEND_V2_SCHEMA_BRIDGE_HARNESS_PASSED_OFFLINE",
            "protected_plan": plan,
            "protected_trace": trace,
            "plan_sha256": plan.plan_sha256,
            "trace_sha256": trace.trace_sha256,
            "apply_mapping_count": len(trace_data["apply_trace"]),
            "terminal_mapping_count": len(trace_data["terminal_trace"]),
            "recovery_mapping_count": len(trace_data["recovery_trace"]),
            "complete_apply_coverage": True,
            "complete_terminal_coverage": True,
            "complete_recovery_coverage": True,
        }
    )
    return base


__all__ = [
    "ProtectedSchemaBridgeMappingTraceV2",
    "build_mapping_trace_offline_v2",
    "protected_mapping_trace_valid_v2",
    "run_handoff_v1_backend_v2_schema_bridge_harness_v2",
]
