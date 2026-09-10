"""Synthetic two-lock harness for the physical observation lease V2."""

from __future__ import annotations

from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2 as physical_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as lease_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_OFFLINE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-MULTISTORE-OBSERVATION-LEASE-"
    "OFFLINE-HARNESS-V2"
)


def make_physical_multistore_observation_lease_v2(
    *, backend: Any, ledger: Any, clock=None
) -> lease_v2.PhysicalMultiStoreObservationLeaseV2:
    storage = vars(ledger)["_storage"]
    return lease_v2.PhysicalMultiStoreObservationLeaseV2(
        lease_v2.PhysicalMultiStoreObservationLeaseConfigV2(
            enabled=True,
            scope_attestation=(
                lease_v2.OFFLINE_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
            ),
            expected_backend_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                )
            ),
            expected_ledger_object_identity_sha256=(
                identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    ledger
                )
            ),
            expected_backend_lock_namespace_sha256=backend._lock_namespace(),
            expected_resolved_ledger_storage_binding_sha256=(
                durable_v2.durable_authority_storage_binding_sha256_v2(storage)
            ),
            max_ttl_seconds=300,
            lock_timeout_seconds=0.01,
        ),
        backend=backend,
        durable_authority_ledger=ledger,
        clock=clock or (lambda: physical_harness_v2.SYNTHETIC_NOW_V2),
        nonce_source=lambda: "synthetic-two-store-observation-lease",
    )


def run_physical_multistore_observation_lease_offline_harness_v2() -> dict[str, Any]:
    with physical_harness_v2.synthetic_physical_conformance_context_v2() as values:
        backend = values["backend"]
        ledger = values["resolved_ledger"]
        lease = make_physical_multistore_observation_lease_v2(
            backend=backend, ledger=ledger
        )
        now = physical_harness_v2.SYNTHETIC_NOW_V2
        token = None
        with lease.hold_offline(expires_at_epoch=now + 60) as active_token:
            token = active_token
            live = lease.validate_live(
                active_token,
                backend=backend,
                durable_authority_ledger=ledger,
                now_epoch=now,
            )
            active_snapshot = lease.snapshot()
            backend_lock = vars(backend)["_lock_backend"].acquire(
                backend._lock_namespace(), 0.001
            )
            ledger_lock = vars(ledger)["_lock_backend"].acquire(
                durable_v2.durable_authority_storage_binding_sha256_v2(
                    vars(ledger)["_storage"]
                ),
                0.001,
            )
            backend_contention_blocked = backend_lock is None
            ledger_contention_blocked = ledger_lock is None
            if backend_lock is not None:
                backend_lock.release()
            if ledger_lock is not None:
                ledger_lock.release()
        inactive_snapshot = lease.snapshot()
        invalid_after_release = not lease.validate_live(
            token,
            backend=backend,
            durable_authority_ledger=ledger,
            now_epoch=now,
        )
        backend_reacquired = vars(backend)["_lock_backend"].acquire(
            backend._lock_namespace(), 0.01
        )
        ledger_reacquired = vars(ledger)["_lock_backend"].acquire(
            durable_v2.durable_authority_storage_binding_sha256_v2(
                vars(ledger)["_storage"]
            ),
            0.01,
        )
        locks_released = backend_reacquired is not None and ledger_reacquired is not None
        if ledger_reacquired is not None:
            ledger_reacquired.release()
        if backend_reacquired is not None:
            backend_reacquired.release()
        ok = bool(
            live
            and active_snapshot["active"] is True
            and active_snapshot["held_lock_count"] == 2
            and active_snapshot["all_handles_live"] is True
            and backend_contention_blocked
            and ledger_contention_blocked
            and invalid_after_release
            and inactive_snapshot["active"] is False
            and inactive_snapshot["held_lock_count"] == 0
            and locks_released
            and repr(token)
            == "ProtectedPhysicalMultiStoreObservationLeaseTokenV2(<protected>)"
        )
    return {
        "ok": ok,
        "status": (
            "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_V2_HARNESS_PASSED"
            if ok
            else "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_V2_HARNESS_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_OFFLINE_HARNESS_V2_VERSION,
        "two_locks_held": active_snapshot["held_lock_count"] == 2,
        "backend_contention_blocked": backend_contention_blocked,
        "resolved_ledger_contention_blocked": ledger_contention_blocked,
        "lease_invalid_after_release": invalid_after_release,
        "both_locks_released": locks_released,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "filesystem_accessed": True,
        "registry_write": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_authority": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "make_physical_multistore_observation_lease_v2",
    "run_physical_multistore_observation_lease_offline_harness_v2",
]
