"""Synthetic end-to-end harness for the boundary-to-store adapter."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Any, Iterator

import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1 as boundary_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_harness_v1 as boundary_harness
import trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1 as envelope_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_HARNESS_V1_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-BACKEND-STORE-ADAPTER-HARNESS-V1"
)
_NOW = boundary_harness._NOW


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def synthetic_production_backend_store_adapter_context_v1(
    *,
    apply_terminal_state: str = "COMMITTED",
    recovery_terminal_state: str = "COMMITTED",
) -> Iterator[dict[str, Any]]:
    with boundary_harness.synthetic_production_backend_boundary_context_v1() as values:
        invocation = values["invocation_command"]
        command = invocation.command
        store = adapter_contract.InMemoryProductionBackendStoreDoubleV1(
            backend_instance_sha256=command["backend_instance_sha256"],
            registry_path_binding_sha256=command[
                "registry_path_binding_sha256"
            ],
            production_backend_capability_attestation_sha256=command[
                "production_backend_capability_attestation_sha256"
            ],
            apply_terminal_state=apply_terminal_state,
            recovery_terminal_state=recovery_terminal_state,
        )
        adapter = adapter_contract.DormantProductionBackendStoreAdapterV1(
            config=adapter_contract.DormantProductionBackendStoreAdapterConfigV1(
                enabled=True,
                scope_attestation=adapter_contract.OFFLINE_PRODUCTION_BACKEND_STORE_ADAPTER_SCOPE_ATTESTATION_V1,
                expected_store_snapshot_sha256=store.snapshot()[
                    "snapshot_sha256"
                ],
            ),
            clock=lambda: _NOW,
            lease_witness=values["lease_witness"],
            boundary=values["backend_boundary"],
            store_double=store,
        )
        yield {
            **values,
            "store_double": store,
            "store_adapter": adapter,
        }


def invoke_synthetic_store_adapter_v1(values: dict[str, Any]) -> dict[str, Any]:
    return values["store_adapter"].invoke_offline(
        envelope=values["production_envelope"],
        invocation_command=values["invocation_command"],
        maintenance_permit=values["maintenance_permit"],
        live_lease_token=values["live_lease_token"],
    )


def _prepare_synthetic_recovery_v1(values: dict[str, Any]) -> dict[str, Any]:
    envelope = values["production_envelope"]
    invocation = values["invocation_command"]
    ambiguous_result = values["apply_result"]["terminal_result"]
    fresh_epoch_label = "synthetic-store-adapter-fresh-recovery-epoch-v1"
    recovery_envelope = envelope_contract.build_recovery_envelope_contract_offline_v1(
        envelope,
        ambiguous_result,
        fresh_maintenance_epoch=_sha256_text(fresh_epoch_label),
        expires_at_epoch=_NOW + 20,
    )
    recovery_grant = boundary_contract.build_synthetic_recovery_authorization_grant_v1(
        invocation,
        recovery_envelope,
        envelope,
        values["backend_boundary_attestation"],
        issued_at_epoch=_NOW - 1,
        expires_at_epoch=_NOW + 15,
    )
    fresh_permit = boundary_harness.build_fresh_synthetic_maintenance_permit_v1(
        fresh_epoch_label
    )
    return {
        **values,
        "recovery_envelope": recovery_envelope,
        "recovery_grant": recovery_grant,
        "fresh_permit": fresh_permit,
    }


def run_synthetic_production_backend_store_adapter_harness_v1() -> dict[str, Any]:
    with synthetic_production_backend_store_adapter_context_v1() as committed_values:
        committed = invoke_synthetic_store_adapter_v1(committed_values)
        replay = invoke_synthetic_store_adapter_v1(committed_values)
        committed_counters = committed_values["store_double"].counters()

    with synthetic_production_backend_store_adapter_context_v1(
        apply_terminal_state="AMBIGUOUS",
        recovery_terminal_state="COMMITTED",
    ) as ambiguous_values:
        ambiguous_apply = invoke_synthetic_store_adapter_v1(ambiguous_values)
        recovery_values = _prepare_synthetic_recovery_v1(
            {**ambiguous_values, "apply_result": ambiguous_apply}
        )

    witness = recovery_values["lease_witness"]
    fresh_permit = recovery_values["fresh_permit"]
    with witness.hold_offline(
        fresh_permit,
        expires_at_epoch=_NOW + 20,
    ) as fresh_token:
        recovery_projection = recovery_values[
            "backend_boundary"
        ].project_recovery_offline(
            envelope=recovery_values["production_envelope"],
            invocation_command=recovery_values["invocation_command"],
            recovery_envelope=recovery_values["recovery_envelope"],
            ambiguous_terminal_result=ambiguous_apply["terminal_result"],
            backend_boundary_attestation=recovery_values[
                "backend_boundary_attestation"
            ],
            fresh_maintenance_permit=fresh_permit,
            fresh_live_lease_token=fresh_token,
            recovery_authorization_grant=recovery_values["recovery_grant"],
        )
        recovered = recovery_values["store_adapter"].recover_offline(
            envelope=recovery_values["production_envelope"],
            invocation_command=recovery_values["invocation_command"],
            recovery_command=recovery_projection[
                "protected_recovery_command"
            ],
            fresh_maintenance_permit=fresh_permit,
            fresh_live_lease_token=fresh_token,
        )
        recovery_counters = recovery_values["store_double"].counters()

    safe = bool(
        committed.get("ok") is True
        and committed.get("terminal_state") == "COMMITTED"
        and replay.get("ok") is True
        and replay["store_double_result"]["idempotent_replay"] is True
        and committed_counters == {
            "apply_call_count": 2,
            "recovery_call_count": 0,
        }
        and ambiguous_apply.get("ok") is True
        and ambiguous_apply.get("recovery_required") is True
        and recovery_projection.get("ok") is True
        and recovered.get("ok") is True
        and recovered.get("terminal_state") == "COMMITTED"
        and recovered.get("recovery_required") is False
        and recovery_counters == {
            "apply_call_count": 1,
            "recovery_call_count": 1,
        }
    )
    return {
        "ok": safe,
        "status": (
            "C3_PRODUCTION_BACKEND_STORE_ADAPTER_HARNESS_PASSED_OFFLINE"
            if safe
            else "C3_PRODUCTION_BACKEND_STORE_ADAPTER_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_HARNESS_V1_VERSION,
        "store_snapshot_bound_synthetic": committed.get(
            "store_snapshot_verified_synthetic"
        )
        is True,
        "deadline_verified_synthetic": committed.get(
            "deadline_verified_synthetic"
        )
        is True,
        "terminal_contract_normalized": committed.get(
            "terminal_contract_normalized"
        )
        is True,
        "idempotent_replay_verified_synthetic": replay.get(
            "store_double_result", {}
        ).get("idempotent_replay")
        is True,
        "ambiguous_result_required_recovery": ambiguous_apply.get(
            "recovery_required"
        )
        is True,
        "fresh_recovery_lease_verified_synthetic": recovered.get(
            "same_live_lease_verified_synthetic"
        )
        is True,
        "recovery_terminal_normalized": recovered.get(
            "recovery_terminal_normalized"
        )
        is True,
        "store_double_called": True,
        "production_authority": False,
        "production_store_called": False,
        "production_backend_called": False,
        "runtime_integrated": False,
        "production_ready": False,
        "apply_allowed": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "registry_write": False,
        "no_order_sent": True,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_BACKEND_STORE_ADAPTER_HARNESS_V1_VERSION",
    "invoke_synthetic_store_adapter_v1",
    "run_synthetic_production_backend_store_adapter_harness_v1",
    "synthetic_production_backend_store_adapter_context_v1",
]
