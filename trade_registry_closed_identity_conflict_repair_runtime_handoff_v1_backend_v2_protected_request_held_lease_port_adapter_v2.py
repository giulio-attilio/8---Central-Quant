"""Concrete default-off adapter for a synthetic in-memory held-lease port.

The adapter accepts only a protected adapter plan and an injected port carrying
a sealed synthetic-only attestation. It revalidates all authority immediately
before one non-reentrant call and returns only a protected terminal wrapper.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2 as adapter_contract_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2 as materializer_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_REQUEST_HELD_LEASE_PORT_ADAPTER_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-REQUEST-HELD-LEASE-PORT-ADAPTER-V2"
)
SYNTHETIC_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_HELD_LEASE_PORT_ADAPTER_SYNTHETIC_IN_MEMORY_ONLY"
)
SYNTHETIC_HELD_LEASE_BACKEND_PORT_ATTESTATION_VERSION_V2 = (
    "C3_SYNTHETIC_HELD_LEASE_BACKEND_PORT_ATTESTATION_V2"
)
PROTECTED_HELD_LEASE_PORT_INVOCATION_RESULT_VERSION_V2 = (
    "C3_PROTECTED_HELD_LEASE_PORT_INVOCATION_RESULT_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PORT_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version",
        "backend_instance_sha256",
        "lock_namespace_sha256",
        "required_method",
        "accepted_request_type",
        "accepted_cas_witness_type",
        "lock_already_held",
        "initial_lock_acquisition_count",
        "backend_reacquire_allowed",
        "store_reacquire_allowed",
        "adapter_release_allowed",
        "filesystem_access_allowed",
        "network_access_allowed",
        "real_registry_access_allowed",
        "synthetic_only",
        "production_authority",
        "attestation_sha256",
    }
)
_RESULT_ENVELOPE_KEYS = frozenset(
    {
        "envelope_version",
        "adapter_plan_sha256",
        "materialized_request_envelope_sha256",
        "cas_witness_sha256",
        "port_attestation_sha256",
        "request_binding_sha256",
        "request_sha256",
        "transaction_sha256",
        "terminal_result_sha256",
        "invoked_at_epoch",
        "lease_revalidation_count",
        "backend_call_count",
        "lock_acquisition_count_before",
        "lock_acquisition_count_after",
        "lock_release_count_before",
        "lock_release_count_after",
        "lock_count_unchanged",
        "terminal_result_validated",
        "raw_result_delivery_allowed",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "synthetic_only",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "envelope_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def synthetic_held_lease_backend_port_attestation_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _hash_without(value, "attestation_sha256")


def protected_held_lease_port_invocation_result_envelope_sha256_v2(
    value: Mapping[str, Any]
) -> str:
    return _hash_without(value, "envelope_sha256")


def synthetic_held_lease_backend_port_attestation_valid_v2(
    value: Any,
    protected_request: materializer_v2.ProtectedMaterializedTransactionRequestV2,
) -> bool:
    if type(value) is not dict or set(value) != _PORT_ATTESTATION_KEYS:
        return False
    request = protected_request.request
    try:
        return bool(
            value["attestation_version"]
            == SYNTHETIC_HELD_LEASE_BACKEND_PORT_ATTESTATION_VERSION_V2
            and value["backend_instance_sha256"]
            == request["backend_instance_sha256"]
            and value["lock_namespace_sha256"]
            == request["lock_namespace_sha256"]
            and value["required_method"]
            == "apply_under_held_maintenance_lease"
            and value["accepted_request_type"]
            == "ProtectedMaterializedTransactionRequestV2"
            and value["accepted_cas_witness_type"]
            == "ProtectedTargetCasWitnessV2"
            and value["lock_already_held"] is True
            and value["initial_lock_acquisition_count"] == 1
            and value["backend_reacquire_allowed"] is False
            and value["store_reacquire_allowed"] is False
            and value["adapter_release_allowed"] is False
            and value["filesystem_access_allowed"] is False
            and value["network_access_allowed"] is False
            and value["real_registry_access_allowed"] is False
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and _valid_sha(value["attestation_sha256"])
            and hmac.compare_digest(
                value["attestation_sha256"],
                synthetic_held_lease_backend_port_attestation_sha256_v2(value),
            )
        )
    except Exception:
        return False


class SyntheticHeldLeaseBackendPortV2(Protocol):
    port_attestation: Mapping[str, Any]
    lock_acquisition_count: int
    lock_release_count: int
    call_count: int

    def apply_under_held_maintenance_lease(
        self,
        protected_request: materializer_v2.ProtectedMaterializedTransactionRequestV2,
        cas_witness: Any,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, repr=False)
class ProtectedHeldLeasePortInvocationResultV2:
    adapter_plan: adapter_contract_v2.ProtectedHeldLeasePortAdapterPlanV2 = field(
        repr=False
    )
    port_attestation: Mapping[str, Any] = field(repr=False)
    terminal_result: Mapping[str, Any] = field(repr=False)
    envelope: Mapping[str, Any] = field(repr=False)
    envelope_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedHeldLeasePortInvocationResultV2(<protected>)"


@dataclass(frozen=True)
class SyntheticHeldLeasePortAdapterConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_plan_sha256: str | None = field(default=None, repr=False)
    expected_port_attestation_sha256: str | None = field(
        default=None,
        repr=False,
    )


def protected_held_lease_port_invocation_result_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedHeldLeasePortInvocationResultV2:
        return False
    adapter_plan = value.adapter_plan
    if not adapter_contract_v2.protected_held_lease_port_adapter_plan_valid_v2(
        adapter_plan
    ):
        return False
    protected_request = adapter_plan.protected_request
    if not synthetic_held_lease_backend_port_attestation_valid_v2(
        value.port_attestation,
        protected_request,
    ):
        return False
    terminal = value.terminal_result
    envelope = value.envelope
    if (
        type(terminal) is not dict
        or type(envelope) is not dict
        or set(envelope) != _RESULT_ENVELOPE_KEYS
    ):
        return False
    request = protected_request.request
    try:
        return bool(
            backend_v2.transaction_result_valid_v2(terminal, request)
            and envelope["envelope_version"]
            == PROTECTED_HELD_LEASE_PORT_INVOCATION_RESULT_VERSION_V2
            and envelope["adapter_plan_sha256"] == adapter_plan.plan_sha256
            and envelope["materialized_request_envelope_sha256"]
            == protected_request.envelope_sha256
            and envelope["cas_witness_sha256"]
            == adapter_plan.cas_witness.witness_sha256
            and envelope["port_attestation_sha256"]
            == value.port_attestation["attestation_sha256"]
            and envelope["request_binding_sha256"]
            == request["request_binding_sha256"]
            and envelope["request_sha256"] == request["request_sha256"]
            and envelope["transaction_sha256"] == request["transaction_sha256"]
            and envelope["terminal_result_sha256"] == terminal["result_sha256"]
            and type(envelope["invoked_at_epoch"]) is int
            and envelope["invoked_at_epoch"] >= adapter_plan.plan["planned_at_epoch"]
            and envelope["invoked_at_epoch"] < request["deadline_epoch"]
            and envelope["lease_revalidation_count"] == 1
            and envelope["backend_call_count"] == 1
            and envelope["lock_acquisition_count_before"] == 1
            and envelope["lock_acquisition_count_after"] == 1
            and envelope["lock_release_count_before"] == 0
            and envelope["lock_release_count_after"] == 0
            and envelope["lock_count_unchanged"] is True
            and envelope["terminal_result_validated"] is True
            and envelope["raw_result_delivery_allowed"] is False
            and envelope["filesystem_accessed"] is False
            and envelope["real_registry_accessed"] is False
            and envelope["network_accessed"] is False
            and envelope["broker_called"] is False
            and envelope["synthetic_only"] is True
            and envelope["production_authority"] is False
            and envelope["runtime_integrated"] is False
            and envelope["activation_allowed"] is False
            and envelope["live_allowed"] is False
            and value.envelope_sha256 == envelope["envelope_sha256"]
            and _valid_sha(envelope["envelope_sha256"])
            and hmac.compare_digest(
                envelope["envelope_sha256"],
                protected_held_lease_port_invocation_result_envelope_sha256_v2(
                    envelope
                ),
            )
        )
    except Exception:
        return False


class SyntheticProtectedHeldLeasePortAdapterV2:
    def __init__(
        self,
        config: SyntheticHeldLeasePortAdapterConfigV2 | None = None,
    ) -> None:
        self._config = config or SyntheticHeldLeasePortAdapterConfigV2()

    @staticmethod
    def _failed(
        reason: str,
        *,
        backend_called: bool = False,
        lease_revalidated: bool = False,
        recovery_required: bool = False,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "status": (
                "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_AMBIGUOUS_RECONCILIATION_REQUIRED"
                if recovery_required
                else "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_V2_BLOCKED"
            ),
            "reason": reason,
            "protected_result": None,
            "terminal_state": None,
            "recovery_required": recovery_required,
            "retry_allowed": False,
            "lease_revalidation_count": 1 if lease_revalidated else 0,
            "backend_call_count": 1 if backend_called else 0,
            "backend_called": backend_called,
            "raw_result_exposed": False,
            "synthetic_memory_write_executed": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired_by_adapter": False,
            "lock_released_by_adapter": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "filesystem_write_executed": False,
            "real_registry_write_executed": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    def invoke_synthetic_offline(
        self,
        adapter_plan: adapter_contract_v2.ProtectedHeldLeasePortAdapterPlanV2,
        backend_port: SyntheticHeldLeaseBackendPortV2,
        *,
        now_epoch: int,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("SYNTHETIC_HELD_LEASE_PORT_ADAPTER_V2_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != SYNTHETIC_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2
        ):
            return self._failed("SYNTHETIC_HELD_LEASE_PORT_ADAPTER_SCOPE_REQUIRED")
        if not adapter_contract_v2.protected_held_lease_port_adapter_plan_valid_v2(
            adapter_plan
        ):
            return self._failed("PROTECTED_HELD_LEASE_PORT_ADAPTER_PLAN_INVALID")
        if not (
            _valid_sha(self._config.expected_adapter_plan_sha256)
            and hmac.compare_digest(
                str(self._config.expected_adapter_plan_sha256),
                adapter_plan.plan_sha256,
            )
        ):
            return self._failed("HELD_LEASE_PORT_ADAPTER_PLAN_PIN_MISMATCH")
        if type(now_epoch) is not int:
            return self._failed("SYNTHETIC_HELD_LEASE_PORT_ADAPTER_CLOCK_INVALID")
        protected_request = adapter_plan.protected_request
        if adapter_plan.cas_witness is not protected_request.cas_witness:
            return self._failed("EXACT_EMBEDDED_CAS_WITNESS_INSTANCE_REQUIRED")
        if not materializer_v2.protected_materialized_transaction_request_valid_v2(
            protected_request
        ):
            return self._failed("PROTECTED_MATERIALIZED_REQUEST_INVALID")
        request = protected_request.request
        receipt = protected_request.authorization_consumption_receipt
        cas = adapter_plan.cas_witness.witness
        maximum_age = adapter_plan.plan["maximum_cas_witness_age_seconds"]
        witness_age = now_epoch - cas["observed_at_epoch"]
        if not (
            now_epoch >= adapter_plan.plan["planned_at_epoch"]
            and 0 <= witness_age <= maximum_age
        ):
            return self._failed("CAS_WITNESS_STALE_AT_SYNTHETIC_INVOCATION")
        intent = protected_request.handoff_plan.materialization_intent
        if not (
            now_epoch < request["deadline_epoch"]
            and now_epoch < receipt["expires_at_epoch"]
            and now_epoch < protected_request.live_lease_token.expires_at_epoch
            and envelope_v1._consumption_receipt_valid(
                receipt,
                receipt["grant_sha256"],
                intent.source_envelope.subject_binding_sha256,
            )
        ):
            return self._failed("AUTHORIZATION_OR_INVOCATION_DEADLINE_EXPIRED")
        try:
            lease_live = protected_request.lease_witness.validate_live(
                protected_request.maintenance_permit,
                protected_request.live_lease_token,
                now_epoch=now_epoch,
            )
        except Exception:
            lease_live = False
        if not lease_live:
            return self._failed(
                "SAME_INSTANCE_LEASE_NOT_LIVE_AT_INVOCATION",
                lease_revalidated=True,
            )
        try:
            port_attestation = copy.deepcopy(dict(backend_port.port_attestation))
        except Exception:
            return self._failed(
                "SYNTHETIC_HELD_LEASE_PORT_ATTESTATION_MISSING",
                lease_revalidated=True,
            )
        if not synthetic_held_lease_backend_port_attestation_valid_v2(
            port_attestation,
            protected_request,
        ):
            return self._failed(
                "SYNTHETIC_HELD_LEASE_PORT_ATTESTATION_INVALID",
                lease_revalidated=True,
            )
        if not (
            _valid_sha(self._config.expected_port_attestation_sha256)
            and hmac.compare_digest(
                str(self._config.expected_port_attestation_sha256),
                port_attestation["attestation_sha256"],
            )
        ):
            return self._failed(
                "SYNTHETIC_HELD_LEASE_PORT_ATTESTATION_PIN_MISMATCH",
                lease_revalidated=True,
            )
        method = getattr(backend_port, "apply_under_held_maintenance_lease", None)
        if not callable(method) or hasattr(
            backend_port,
            "apply_attested_transaction_offline",
        ):
            return self._failed(
                "NON_REENTRANT_SYNTHETIC_PORT_METHOD_REQUIRED",
                lease_revalidated=True,
            )
        try:
            acquisition_before = backend_port.lock_acquisition_count
            release_before = backend_port.lock_release_count
            call_before = backend_port.call_count
        except Exception:
            return self._failed(
                "SYNTHETIC_PORT_COUNTERS_REQUIRED",
                lease_revalidated=True,
            )
        if not (
            type(acquisition_before) is int
            and acquisition_before == 1
            and type(release_before) is int
            and release_before == 0
            and type(call_before) is int
            and call_before == 0
        ):
            return self._failed(
                "SYNTHETIC_PORT_INITIAL_COUNTERS_INVALID",
                lease_revalidated=True,
            )
        try:
            terminal_result = method(
                protected_request,
                adapter_plan.cas_witness,
            )
        except Exception:
            return self._failed(
                "SYNTHETIC_HELD_LEASE_PORT_CALL_FAILED_CLOSED",
                backend_called=True,
                lease_revalidated=True,
                recovery_required=True,
            )
        try:
            acquisition_after = backend_port.lock_acquisition_count
            release_after = backend_port.lock_release_count
            call_after = backend_port.call_count
        except Exception:
            return self._failed(
                "SYNTHETIC_PORT_POST_CALL_COUNTERS_MISSING",
                backend_called=True,
                lease_revalidated=True,
                recovery_required=True,
            )
        if not (
            acquisition_after == acquisition_before
            and release_after == release_before
            and call_after == call_before + 1 == 1
        ):
            return self._failed(
                "NON_REENTRANT_PORT_COUNTER_INVARIANT_VIOLATED",
                backend_called=True,
                lease_revalidated=True,
                recovery_required=True,
            )
        if type(terminal_result) is not dict or not backend_v2.transaction_result_valid_v2(
            terminal_result,
            request,
        ):
            return self._failed(
                "SYNTHETIC_TERMINAL_RESULT_INVALID",
                backend_called=True,
                lease_revalidated=True,
                recovery_required=True,
            )
        envelope = {
            "envelope_version": PROTECTED_HELD_LEASE_PORT_INVOCATION_RESULT_VERSION_V2,
            "adapter_plan_sha256": adapter_plan.plan_sha256,
            "materialized_request_envelope_sha256": protected_request.envelope_sha256,
            "cas_witness_sha256": adapter_plan.cas_witness.witness_sha256,
            "port_attestation_sha256": port_attestation["attestation_sha256"],
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "terminal_result_sha256": terminal_result["result_sha256"],
            "invoked_at_epoch": now_epoch,
            "lease_revalidation_count": 1,
            "backend_call_count": 1,
            "lock_acquisition_count_before": acquisition_before,
            "lock_acquisition_count_after": acquisition_after,
            "lock_release_count_before": release_before,
            "lock_release_count_after": release_after,
            "lock_count_unchanged": True,
            "terminal_result_validated": True,
            "raw_result_delivery_allowed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        envelope["envelope_sha256"] = (
            protected_held_lease_port_invocation_result_envelope_sha256_v2(
                envelope
            )
        )
        protected_result = ProtectedHeldLeasePortInvocationResultV2(
            adapter_plan=adapter_plan,
            port_attestation=copy.deepcopy(port_attestation),
            terminal_result=copy.deepcopy(terminal_result),
            envelope=copy.deepcopy(envelope),
            envelope_sha256=envelope["envelope_sha256"],
        )
        if not protected_held_lease_port_invocation_result_valid_v2(
            protected_result
        ):
            return self._failed(
                "PROTECTED_SYNTHETIC_RESULT_INTERNAL_INVALID",
                backend_called=True,
                lease_revalidated=True,
                recovery_required=True,
            )
        terminal_state = terminal_result["terminal_state"]
        recovery_required = terminal_state == "AMBIGUOUS"
        result = self._failed(
            "",
            backend_called=True,
            lease_revalidated=True,
            recovery_required=recovery_required,
        )
        statuses = {
            "COMMITTED": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_COMMITTED_OFFLINE",
            "ABORTED": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_ABORTED_OFFLINE",
            "ROLLED_BACK": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_ROLLED_BACK_OFFLINE",
            "AMBIGUOUS": "SYNTHETIC_HELD_LEASE_PORT_INVOCATION_AMBIGUOUS_RECONCILIATION_REQUIRED",
        }
        reasons = {
            "COMMITTED": None,
            "ABORTED": "SYNTHETIC_TRANSACTION_ABORTED",
            "ROLLED_BACK": "SYNTHETIC_TRANSACTION_ROLLED_BACK",
            "AMBIGUOUS": "SYNTHETIC_TRANSACTION_AMBIGUOUS_RECONCILIATION_REQUIRED",
        }
        result.update(
            {
                "ok": terminal_state == "COMMITTED",
                "status": statuses[terminal_state],
                "reason": reasons[terminal_state],
                "protected_result": protected_result,
                "result_envelope_sha256": protected_result.envelope_sha256,
                "terminal_state": terminal_state,
                "recovery_required": recovery_required,
                "retry_allowed": False,
                "lease_revalidation_count": 1,
                "backend_call_count": 1,
                "synthetic_memory_write_executed": bool(
                    terminal_result["write_executed"]
                ),
            }
        )
        return result


__all__ = [
    "PROTECTED_HELD_LEASE_PORT_INVOCATION_RESULT_VERSION_V2",
    "ProtectedHeldLeasePortInvocationResultV2",
    "SYNTHETIC_HELD_LEASE_BACKEND_PORT_ATTESTATION_VERSION_V2",
    "SYNTHETIC_HELD_LEASE_PORT_ADAPTER_SCOPE_ATTESTATION_V2",
    "SyntheticHeldLeaseBackendPortV2",
    "SyntheticHeldLeasePortAdapterConfigV2",
    "SyntheticProtectedHeldLeasePortAdapterV2",
    "protected_held_lease_port_invocation_result_envelope_sha256_v2",
    "protected_held_lease_port_invocation_result_valid_v2",
    "synthetic_held_lease_backend_port_attestation_sha256_v2",
    "synthetic_held_lease_backend_port_attestation_valid_v2",
]
