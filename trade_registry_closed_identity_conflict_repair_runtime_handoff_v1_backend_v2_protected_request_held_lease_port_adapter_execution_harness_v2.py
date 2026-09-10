"""In-memory execution harness for the protected held-lease port adapter V2."""

from __future__ import annotations

import copy
import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2 as materialization_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2 as handoff_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2 as handoff_harness
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2 as adapter_contract_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2 as adapter_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HELD-LEASE-PORT-ADAPTER-EXECUTION-HARNESS-V2"
)
PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_EVIDENCE_V2"
)

_CHECK_NAMES = (
    "PROTECTED_TERMINAL_RESULT_VALID",
    "EXACT_PROTECTED_REQUEST_AND_CAS_RECEIVED",
    "BACKEND_CALLED_EXACTLY_ONCE",
    "LEASE_REVALIDATED_EXACTLY_ONCE_AT_INVOCATION",
    "LOCK_ACQUISITION_AND_RELEASE_COUNTS_UNCHANGED",
    "TERMINAL_RESULT_SCHEMA_AND_BINDINGS_EXACT",
    "RAW_TERMINAL_RESULT_NOT_EXPOSED",
    "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION",
    "STALE_CAS_REJECTED_BEFORE_BACKEND_CALL",
    "INVALID_PORT_ATTESTATION_REJECTED_BEFORE_CALL",
    "LEGACY_SELF_LOCKING_SURFACE_REJECTED_BEFORE_CALL",
    "LOCK_REACQUISITION_DETECTED_AFTER_CALL",
    "MALFORMED_TERMINAL_RESULT_REJECTED",
    "BACKEND_EXCEPTION_REQUIRES_RECONCILIATION",
    "ABORTED_TERMINAL_STATE_REPORTED_DISTINCTLY",
    "ROLLED_BACK_TERMINAL_STATE_REPORTED_DISTINCTLY",
    "AMBIGUOUS_TERMINAL_STATE_REQUIRES_RECONCILIATION",
    "ONLY_SYNTHETIC_MEMORY_WRITE_OBSERVED",
    "NO_FILESYSTEM_NETWORK_REGISTRY_BROKER_OR_RUNTIME_EFFECT",
)
_CHECK_KEYS = frozenset({"name", "passed"})
_EVIDENCE_KEYS = frozenset(
    {
        "evidence_version",
        "adapter_plan_sha256",
        "port_attestation_sha256",
        "result_envelope_sha256",
        "terminal_result_sha256",
        "checks",
        "check_count",
        "passed_count",
        "lease_revalidation_count",
        "backend_call_count",
        "synthetic_memory_write_executed",
        "filesystem_write_executed",
        "real_registry_write_executed",
        "provider_called",
        "store_called",
        "writer_called",
        "lock_acquired_by_adapter",
        "lock_released_by_adapter",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "evidence_sha256",
    }
)


def _sha(value: Any) -> str:
    return backend_v2.stable_sha256_v2(value)


def protected_held_lease_port_adapter_execution_harness_evidence_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _sha(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


class InMemoryHeldLeaseBackendPortDoubleV2:
    """Non-reentrant test double with observable lock and call counters."""

    def __init__(self, protected_request, *, mode: str = "valid") -> None:
        request = protected_request.request
        attestation = {
            "attestation_version": adapter_v2.SYNTHETIC_HELD_LEASE_BACKEND_PORT_ATTESTATION_VERSION_V2,
            "backend_instance_sha256": request["backend_instance_sha256"],
            "lock_namespace_sha256": request["lock_namespace_sha256"],
            "required_method": "apply_under_held_maintenance_lease",
            "accepted_request_type": "ProtectedMaterializedTransactionRequestV2",
            "accepted_cas_witness_type": "ProtectedTargetCasWitnessV2",
            "lock_already_held": True,
            "initial_lock_acquisition_count": 1,
            "backend_reacquire_allowed": False,
            "store_reacquire_allowed": False,
            "adapter_release_allowed": False,
            "filesystem_access_allowed": False,
            "network_access_allowed": False,
            "real_registry_access_allowed": False,
            "synthetic_only": True,
            "production_authority": False,
        }
        attestation["attestation_sha256"] = (
            adapter_v2.synthetic_held_lease_backend_port_attestation_sha256_v2(
                attestation
            )
        )
        self.port_attestation = attestation
        self.lock_acquisition_count = 1
        self.lock_release_count = 0
        self.call_count = 0
        self.mode = mode
        self.received_protected_request = None
        self.received_cas_witness = None
        self.memory_document_sha256 = request["expected_raw_document_sha256"]

    def apply_under_held_maintenance_lease(
        self,
        protected_request,
        cas_witness,
    ) -> Mapping[str, Any]:
        self.call_count += 1
        self.received_protected_request = protected_request
        self.received_cas_witness = cas_witness
        if self.mode == "raise":
            raise RuntimeError("synthetic injected failure")
        if self.mode == "reacquire":
            self.lock_acquisition_count += 1
        if self.mode == "malformed":
            return {}
        request = protected_request.request
        self.memory_document_sha256 = request["candidate_raw_document_sha256"]
        terminal_state = (
            self.mode
            if self.mode in {"ABORTED", "ROLLED_BACK", "AMBIGUOUS"}
            else "COMMITTED"
        )
        ambiguous = terminal_state == "AMBIGUOUS"
        wrote = terminal_state in {"COMMITTED", "ROLLED_BACK", "AMBIGUOUS"}
        result = {
            "result_version": backend_v2.TRANSACTION_RESULT_VERSION_V2,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "backend_snapshot_sha256": request["backend_snapshot_sha256"],
            "prepared_record_sha256": _sha(
                {"synthetic_prepared": request["transaction_sha256"]}
            ),
            "terminal_record_sha256": _sha(
                {"synthetic_terminal": request["transaction_sha256"]}
            ),
            "terminal_state": terminal_state,
            "generation_before": request["expected_generation"],
            "generation_after": request["expected_generation"] + 1,
            "deadline_epoch": request["deadline_epoch"],
            "deadline_observed": True,
            "postconditions_verified": not ambiguous,
            "recovery_required": ambiguous,
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "write_executed": wrote,
            "registry_write": wrote,
        }
        result["result_sha256"] = _sha(result)
        return result


class LegacySurfaceInMemoryPortDoubleV2(InMemoryHeldLeaseBackendPortDoubleV2):
    def apply_attested_transaction_offline(self, request):
        raise AssertionError("legacy method must never be called")


@dataclass(frozen=True, repr=False)
class ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2:
    protected_result: adapter_v2.ProtectedHeldLeasePortInvocationResultV2 = field(
        repr=False
    )
    evidence: Mapping[str, Any] = field(repr=False)
    evidence_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2(<protected>)"


def protected_held_lease_port_adapter_execution_harness_evidence_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2:
        return False
    evidence = value.evidence
    if type(evidence) is not dict or set(evidence) != _EVIDENCE_KEYS:
        return False
    checks = evidence.get("checks")
    try:
        return bool(
            adapter_v2.protected_held_lease_port_invocation_result_valid_v2(
                value.protected_result
            )
            and evidence["evidence_version"]
            == PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_EVIDENCE_VERSION_V2
            and evidence["adapter_plan_sha256"]
            == value.protected_result.adapter_plan.plan_sha256
            and evidence["port_attestation_sha256"]
            == value.protected_result.port_attestation["attestation_sha256"]
            and evidence["result_envelope_sha256"]
            == value.protected_result.envelope_sha256
            and evidence["terminal_result_sha256"]
            == value.protected_result.terminal_result["result_sha256"]
            and isinstance(checks, list)
            and [item["name"] for item in checks] == list(_CHECK_NAMES)
            and all(
                type(item) is dict
                and set(item) == _CHECK_KEYS
                and item["passed"] is True
                for item in checks
            )
            and evidence["check_count"] == len(_CHECK_NAMES)
            and evidence["passed_count"] == len(_CHECK_NAMES)
            and evidence["lease_revalidation_count"] == 1
            and evidence["backend_call_count"] == 1
            and evidence["synthetic_memory_write_executed"] is True
            and all(
                evidence[key] is False
                for key in (
                    "filesystem_write_executed",
                    "real_registry_write_executed",
                    "provider_called",
                    "store_called",
                    "writer_called",
                    "lock_acquired_by_adapter",
                    "lock_released_by_adapter",
                    "filesystem_accessed",
                    "real_registry_accessed",
                    "network_accessed",
                    "broker_called",
                    "production_authority",
                    "runtime_integrated",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and evidence["synthetic_only"] is True
            and value.evidence_sha256 == evidence["evidence_sha256"]
            and hmac.compare_digest(
                evidence["evidence_sha256"],
                protected_held_lease_port_adapter_execution_harness_evidence_sha256_v2(
                    evidence
                ),
            )
        )
    except Exception:
        return False


def _concrete_adapter(adapter_plan, port):
    return adapter_v2.SyntheticProtectedHeldLeasePortAdapterV2(
        adapter_v2.SyntheticHeldLeasePortAdapterConfigV2(
            enabled=True,
            scope_attestation=(
                adapter_v2.SYNTHETIC_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
            ),
            expected_adapter_plan_sha256=adapter_plan.plan_sha256,
            expected_port_attestation_sha256=port.port_attestation[
                "attestation_sha256"
            ],
        )
    )


def run_protected_held_lease_port_adapter_execution_harness_v2() -> dict[str, Any]:
    base = {
        "ok": False,
        "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_V2_FAILED_CLOSED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_V2_VERSION,
        "protected_result": None,
        "protected_evidence": None,
        "check_count": 0,
        "passed_count": 0,
        "lease_revalidation_count": 0,
        "backend_call_count": 0,
        "synthetic_memory_write_executed": False,
        "raw_result_exposed": False,
        "filesystem_write_executed": False,
        "real_registry_write_executed": False,
        "provider_called": False,
        "store_called": False,
        "writer_called": False,
        "lock_acquired_by_adapter": False,
        "lock_released_by_adapter": False,
        "filesystem_accessed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "production_authority": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "no_order_sent": True,
    }
    try:
        with materialization_harness.held_protected_dto_materialization_fixture_v2() as fixture:
            materialization = materialization_harness.bind_protected_dto_materialization_fixture_offline_v2(
                fixture
            )
            intent = materialization.get("protected_intent")
            if materialization.get("ok") is not True or intent is None:
                base["reason"] = "UPSTREAM_PROTECTED_INTENT_INVALID"
                return base
            handoff_planner = handoff_v2.DormantProtectedRequestHandoffContractV2(
                handoff_v2.DormantProtectedRequestHandoffConfigV2(
                    enabled=True,
                    scope_attestation=(
                        handoff_v2.OFFLINE_PROTECTED_REQUEST_HANDOFF_SCOPE_ATTESTATION_V2
                    ),
                    expected_materialization_intent_sha256=intent.intent_sha256,
                )
            )
            handoff_result = handoff_planner.plan_offline(
                intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
            )
            handoff_plan = handoff_result.get("protected_plan")
            if handoff_result.get("ok") is not True or handoff_plan is None:
                base["reason"] = "UPSTREAM_HANDOFF_PLAN_INVALID"
                return base
            cas_witness = handoff_harness.build_synthetic_target_cas_witness_offline_v2(
                intent,
                fixture["bridge_plan"],
                fixture["compatibility_bundle"],
                observed_at_epoch=fixture["now_epoch"],
            )
            materializer = materializer_v2.OfflineProtectedRequestMaterializerV2(
                materializer_v2.OfflineProtectedRequestMaterializerConfigV2(
                    enabled=True,
                    scope_attestation=(
                        materializer_v2.OFFLINE_PROTECTED_REQUEST_MATERIALIZER_SCOPE_ATTESTATION_V2
                    ),
                    expected_handoff_plan_sha256=handoff_plan.plan_sha256,
                    maximum_cas_witness_age_seconds=5,
                )
            )
            materialized = materializer.materialize_offline(
                handoff_plan,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            protected_request = materialized.get("protected_request")
            if materialized.get("ok") is not True or protected_request is None:
                base["reason"] = "UPSTREAM_PROTECTED_REQUEST_INVALID"
                return base
            contract_planner = adapter_contract_v2.DormantProtectedHeldLeasePortAdapterV2(
                adapter_contract_v2.DormantHeldLeasePortAdapterConfigV2(
                    enabled=True,
                    scope_attestation=(
                        adapter_contract_v2.OFFLINE_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
                    ),
                    expected_materialized_request_envelope_sha256=protected_request.envelope_sha256,
                    maximum_cas_witness_age_seconds=5,
                )
            )
            adapter_plan_result = contract_planner.plan_offline(
                protected_request,
                cas_witness,
                now_epoch=fixture["now_epoch"],
            )
            adapter_plan = adapter_plan_result.get("protected_plan")
            if adapter_plan_result.get("ok") is not True or adapter_plan is None:
                base["reason"] = "UPSTREAM_ADAPTER_PLAN_INVALID"
                return base

            port = InMemoryHeldLeaseBackendPortDoubleV2(protected_request)
            adapter = _concrete_adapter(adapter_plan, port)
            invoked = adapter.invoke_synthetic_offline(
                adapter_plan,
                port,
                now_epoch=fixture["now_epoch"],
            )
            protected_result = invoked.get("protected_result")
            if invoked.get("ok") is not True or protected_result is None:
                base["reason"] = "SYNTHETIC_ADAPTER_INVOCATION_FAILED"
                return base

            default_off = adapter_v2.SyntheticProtectedHeldLeasePortAdapterV2().invoke_synthetic_offline(
                None,
                None,
                now_epoch=0,
            )
            stale_port = InMemoryHeldLeaseBackendPortDoubleV2(protected_request)
            stale = _concrete_adapter(adapter_plan, stale_port).invoke_synthetic_offline(
                adapter_plan,
                stale_port,
                now_epoch=fixture["now_epoch"] + 6,
            )
            invalid_attestation_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request
            )
            invalid_attestation_port.port_attestation[
                "filesystem_access_allowed"
            ] = True
            invalid_attestation_port.port_attestation["attestation_sha256"] = (
                adapter_v2.synthetic_held_lease_backend_port_attestation_sha256_v2(
                    invalid_attestation_port.port_attestation
                )
            )
            invalid_attestation = _concrete_adapter(
                adapter_plan,
                invalid_attestation_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                invalid_attestation_port,
                now_epoch=fixture["now_epoch"],
            )
            legacy_port = LegacySurfaceInMemoryPortDoubleV2(protected_request)
            legacy = _concrete_adapter(
                adapter_plan,
                legacy_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                legacy_port,
                now_epoch=fixture["now_epoch"],
            )
            reacquire_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="reacquire",
            )
            reacquire = _concrete_adapter(
                adapter_plan,
                reacquire_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                reacquire_port,
                now_epoch=fixture["now_epoch"],
            )
            malformed_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="malformed",
            )
            malformed = _concrete_adapter(
                adapter_plan,
                malformed_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                malformed_port,
                now_epoch=fixture["now_epoch"],
            )
            exception_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="raise",
            )
            exception = _concrete_adapter(
                adapter_plan,
                exception_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                exception_port,
                now_epoch=fixture["now_epoch"],
            )
            aborted_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="ABORTED",
            )
            aborted = _concrete_adapter(
                adapter_plan,
                aborted_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                aborted_port,
                now_epoch=fixture["now_epoch"],
            )
            rolled_back_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="ROLLED_BACK",
            )
            rolled_back = _concrete_adapter(
                adapter_plan,
                rolled_back_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                rolled_back_port,
                now_epoch=fixture["now_epoch"],
            )
            ambiguous_port = InMemoryHeldLeaseBackendPortDoubleV2(
                protected_request,
                mode="AMBIGUOUS",
            )
            ambiguous = _concrete_adapter(
                adapter_plan,
                ambiguous_port,
            ).invoke_synthetic_offline(
                adapter_plan,
                ambiguous_port,
                now_epoch=fixture["now_epoch"],
            )
            terminal = protected_result.terminal_result
            envelope = protected_result.envelope
            operational_false = (
                "filesystem_write_executed",
                "real_registry_write_executed",
                "provider_called",
                "store_called",
                "writer_called",
                "lock_acquired_by_adapter",
                "lock_released_by_adapter",
                "filesystem_accessed",
                "real_registry_accessed",
                "network_accessed",
                "broker_called",
                "production_authority",
                "runtime_integrated",
                "activation_allowed",
                "live_allowed",
            )
            checks_by_name = {
                "PROTECTED_TERMINAL_RESULT_VALID": adapter_v2.protected_held_lease_port_invocation_result_valid_v2(protected_result),
                "EXACT_PROTECTED_REQUEST_AND_CAS_RECEIVED": port.received_protected_request is protected_request and port.received_cas_witness is cas_witness,
                "BACKEND_CALLED_EXACTLY_ONCE": invoked["backend_call_count"] == 1 and port.call_count == 1,
                "LEASE_REVALIDATED_EXACTLY_ONCE_AT_INVOCATION": invoked["lease_revalidation_count"] == 1 and envelope["lease_revalidation_count"] == 1,
                "LOCK_ACQUISITION_AND_RELEASE_COUNTS_UNCHANGED": port.lock_acquisition_count == 1 and port.lock_release_count == 0 and envelope["lock_count_unchanged"] is True,
                "TERMINAL_RESULT_SCHEMA_AND_BINDINGS_EXACT": backend_v2.transaction_result_valid_v2(terminal, protected_request.request) and terminal["terminal_state"] == "COMMITTED",
                "RAW_TERMINAL_RESULT_NOT_EXPOSED": invoked["raw_result_exposed"] is False and type(protected_result) is adapter_v2.ProtectedHeldLeasePortInvocationResultV2,
                "DEFAULT_OFF_REJECTED_BEFORE_INPUT_INSPECTION": default_off["ok"] is False and default_off["reason"] == "SYNTHETIC_HELD_LEASE_PORT_ADAPTER_V2_DEFAULT_OFF",
                "STALE_CAS_REJECTED_BEFORE_BACKEND_CALL": stale["ok"] is False and stale["reason"] == "CAS_WITNESS_STALE_AT_SYNTHETIC_INVOCATION" and stale_port.call_count == 0,
                "INVALID_PORT_ATTESTATION_REJECTED_BEFORE_CALL": invalid_attestation["ok"] is False and invalid_attestation["reason"] == "SYNTHETIC_HELD_LEASE_PORT_ATTESTATION_INVALID" and invalid_attestation_port.call_count == 0,
                "LEGACY_SELF_LOCKING_SURFACE_REJECTED_BEFORE_CALL": legacy["ok"] is False and legacy["reason"] == "NON_REENTRANT_SYNTHETIC_PORT_METHOD_REQUIRED" and legacy_port.call_count == 0,
                "LOCK_REACQUISITION_DETECTED_AFTER_CALL": reacquire["ok"] is False and reacquire["reason"] == "NON_REENTRANT_PORT_COUNTER_INVARIANT_VIOLATED" and reacquire["backend_called"] is True,
                "MALFORMED_TERMINAL_RESULT_REJECTED": malformed["ok"] is False and malformed["reason"] == "SYNTHETIC_TERMINAL_RESULT_INVALID" and malformed["backend_called"] is True,
                "BACKEND_EXCEPTION_REQUIRES_RECONCILIATION": exception["ok"] is False and exception["reason"] == "SYNTHETIC_HELD_LEASE_PORT_CALL_FAILED_CLOSED" and exception["backend_called"] is True and exception["recovery_required"] is True and exception["retry_allowed"] is False and exception["lease_revalidation_count"] == 1,
                "ABORTED_TERMINAL_STATE_REPORTED_DISTINCTLY": aborted["ok"] is False and aborted["terminal_state"] == "ABORTED" and aborted["status"] == "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_ABORTED_OFFLINE" and aborted["recovery_required"] is False and aborted["protected_result"] is not None,
                "ROLLED_BACK_TERMINAL_STATE_REPORTED_DISTINCTLY": rolled_back["ok"] is False and rolled_back["terminal_state"] == "ROLLED_BACK" and rolled_back["status"] == "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_ROLLED_BACK_OFFLINE" and rolled_back["recovery_required"] is False and rolled_back["protected_result"] is not None,
                "AMBIGUOUS_TERMINAL_STATE_REQUIRES_RECONCILIATION": ambiguous["ok"] is False and ambiguous["terminal_state"] == "AMBIGUOUS" and ambiguous["recovery_required"] is True and ambiguous["retry_allowed"] is False and ambiguous["protected_result"] is not None,
                "ONLY_SYNTHETIC_MEMORY_WRITE_OBSERVED": invoked["synthetic_memory_write_executed"] is True and port.memory_document_sha256 == protected_request.request["candidate_raw_document_sha256"],
                "NO_FILESYSTEM_NETWORK_REGISTRY_BROKER_OR_RUNTIME_EFFECT": all(invoked[key] is False for key in operational_false),
            }
            checks = [
                {"name": name, "passed": checks_by_name[name] is True}
                for name in _CHECK_NAMES
            ]
            if not all(item["passed"] for item in checks):
                base["reason"] = "SYNTHETIC_ADAPTER_EXECUTION_ORACLE_FAILED"
                return base
            evidence = {
                "evidence_version": PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_EVIDENCE_VERSION_V2,
                "adapter_plan_sha256": adapter_plan.plan_sha256,
                "port_attestation_sha256": port.port_attestation[
                    "attestation_sha256"
                ],
                "result_envelope_sha256": protected_result.envelope_sha256,
                "terminal_result_sha256": terminal["result_sha256"],
                "checks": checks,
                "check_count": len(checks),
                "passed_count": sum(item["passed"] for item in checks),
                "lease_revalidation_count": 1,
                "backend_call_count": 1,
                "synthetic_memory_write_executed": True,
                "filesystem_write_executed": False,
                "real_registry_write_executed": False,
                "provider_called": False,
                "store_called": False,
                "writer_called": False,
                "lock_acquired_by_adapter": False,
                "lock_released_by_adapter": False,
                "filesystem_accessed": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "synthetic_only": True,
            }
            evidence["evidence_sha256"] = (
                protected_held_lease_port_adapter_execution_harness_evidence_sha256_v2(
                    evidence
                )
            )
            protected_evidence = (
                ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2(
                    protected_result=protected_result,
                    evidence=copy.deepcopy(evidence),
                    evidence_sha256=evidence["evidence_sha256"],
                )
            )
            if not protected_held_lease_port_adapter_execution_harness_evidence_valid_v2(
                protected_evidence
            ):
                base["reason"] = "SYNTHETIC_EXECUTION_EVIDENCE_INTERNAL_INVALID"
                return base
    except Exception:
        base["reason"] = "PROTECTED_ADAPTER_EXECUTION_HARNESS_EXCEPTION"
        return base
    base.update(
        {
            "ok": True,
            "status": "PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_PASSED_OFFLINE",
            "protected_result": protected_result,
            "protected_evidence": protected_evidence,
            "result_envelope_sha256": protected_result.envelope_sha256,
            "evidence_sha256": protected_evidence.evidence_sha256,
            "check_count": len(_CHECK_NAMES),
            "passed_count": len(_CHECK_NAMES),
            "lease_revalidation_count": 1,
            "backend_call_count": 1,
            "synthetic_memory_write_executed": True,
        }
    )
    return base


__all__ = [
    "InMemoryHeldLeaseBackendPortDoubleV2",
    "PROTECTED_HELD_LEASE_PORT_ADAPTER_EXECUTION_HARNESS_EVIDENCE_VERSION_V2",
    "ProtectedHeldLeasePortAdapterExecutionHarnessEvidenceV2",
    "protected_held_lease_port_adapter_execution_harness_evidence_sha256_v2",
    "protected_held_lease_port_adapter_execution_harness_evidence_valid_v2",
    "run_protected_held_lease_port_adapter_execution_harness_v2",
]
