"""Synthetic temporary-filesystem harness for the offline startup adapter."""

from __future__ import annotations

import hashlib
import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2 as startup_contract
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as adapter_contract
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_HARNESS_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-STARTUP-RECOVERY-ADAPTER-OFFLINE-HARNESS-V1"
)
SYNTHETIC_NOW_V1 = 1_788_900_000

_SOURCE_FILES = (
    "trade_registry.py",
    "main.py",
    "bots/meme.py",
    "bots/predator.py",
    "bots/turtle.py",
    "trade_registry_closed_identity_conflict_repair_raw_transaction_store_production_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_invocation_adapter_v1.py",
    "trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py",
    "trade_registry_closed_identity_conflict_repair_production_provider_v1.py",
)


class _LockHandle:
    def __init__(self, backend: "_LockBackend") -> None:
        self._backend = backend
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._released = True
            self._backend.held = False


class _LockBackend:
    def __init__(self) -> None:
        self.held = False

    def acquire(self, _namespace: str, _timeout_seconds: float):
        if self.held:
            return None
        self.held = True
        return _LockHandle(self)


class _LeaseStore:
    def __init__(self) -> None:
        self.values: dict[str, dict] = {}

    def read(self, namespace: str):
        value = self.values.get(namespace)
        return dict(value) if value is not None else None

    def write(self, namespace: str, lease) -> None:
        self.values[namespace] = dict(lease)


def _activation_evidence() -> dict[str, Any]:
    evidence = {
        "activation_requested": True,
        "activation_receipt_sha256": "a" * 64,
        "activation_receipt_verified": True,
        "source_hashes_verified": True,
        "source_hashes": {
            name: hashlib.sha256(name.encode("utf-8")).hexdigest()
            for name in _SOURCE_FILES
        },
        "shared_lock_backend_ready": True,
        "maintenance_lease_store_ready": True,
        "registry_interlock_ready": True,
        "registry_interlock": {
            "migration_done": True,
            "restart_readiness_attested": True,
            "last_load_ok": True,
            "last_write_ok": True,
            "write_allowed": True,
            "temporary_read_only": False,
        },
        "rollback_ready": True,
        "kill_switch_ready": True,
        "activation_window": {
            "max_duration_seconds": 120.0,
            "rollback_deadline_seconds": 30.0,
            "max_inflight_mutations_before_activation": 0,
            "fail_closed": True,
            "auto_rollback_on_failure": True,
        },
        "trading_controls": {
            "enable_real_trading": False,
            "broker_dry_run": True,
            "falcon_mode": "VERIFY",
            "central_real_execution_enabled": False,
            "central_real_pilot_enabled": False,
            "live_trading_enabled": False,
            "order_submission_authorized": False,
        },
    }
    evidence["activation_evidence_sha256"] = (
        runtime_seam.controlled_activation_evidence_sha256_v1(evidence)
    )
    return evidence


def run_offline_runtime_startup_recovery_adapter_harness_v1() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
            root,
            enabled=True,
            scope_attestation=(
                physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2
            ),
            clock=lambda: SYNTHETIC_NOW_V1,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "offline-startup-adapter-source"}
        )
        for index in range(2):
            request = backend.build_transaction_request_offline(
                {
                    "closed_trades": [],
                    "fixture": f"offline-startup-adapter-candidate-{index}",
                },
                label=f"offline-startup-adapter-prepared-{index}",
                deadline_epoch=SYNTHETIC_NOW_V1 + 120,
            )
            backend.prepare_interrupted_transaction_offline(request)

        recovery = startup_contract.ResumableStartupRecoveryV2(
            startup_contract.StartupRecoveryConfigV2(
                enabled=True,
                scope_attestation=(
                    startup_contract.OFFLINE_STARTUP_RECOVERY_SCOPE_ATTESTATION_V2
                ),
                max_prepared_records=8,
                max_recovery_seconds=120,
            ),
            clock=lambda: SYNTHETIC_NOW_V1 + 1,
        )
        terminal_port = terminal_contract.PhysicalTerminalEvidencePortV2(
            terminal_contract.PhysicalTerminalEvidencePortConfigV2(
                enabled=True,
                scope_attestation=(
                    terminal_contract.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2
                ),
                max_completion_window_seconds=120,
            ),
            clock=lambda: SYNTHETIC_NOW_V1 + 2,
        )
        adapter = adapter_contract.OfflineRuntimeStartupRecoveryAdapterV1(
            backend=backend,
            startup_recovery=recovery,
            terminal_evidence_port=terminal_port,
            config=adapter_contract.OfflineRuntimeStartupRecoveryAdapterConfigV1(
                enabled=True,
                scope_attestation=(
                    adapter_contract.OFFLINE_RUNTIME_STARTUP_RECOVERY_ADAPTER_SCOPE_ATTESTATION_V1
                ),
            ),
        )

        maintenance_epochs: list[str] = []
        original_reconcile = backend.reconcile_attested_transaction_offline

        def reconcile_with_binding(request):
            maintenance_epochs.append(request["fresh_maintenance_epoch"])
            return original_reconcile(request)

        backend.reconcile_attested_transaction_offline = reconcile_with_binding

        coordinator = coordinator_module.build_closed_repair_writer_runtime_coordinator_v1(
            config=coordinator_module.WriterRuntimeCoordinatorConfigV1(
                enabled=True
            ),
            lock_backend=_LockBackend(),
            lease_store=_LeaseStore(),
            clock=lambda: float(SYNTHETIC_NOW_V1 + 3),
            nonce_source=lambda: "offline-startup-adapter-nonce",
        )
        coordinator.register_all_declared_writers()
        captured: dict[str, Any] = {}
        try:
            pending = runtime_seam.install_controlled_c3_closed_repair_writer_coordinator_v1(
                coordinator,
                enabled=True,
                scope_attestation=(
                    runtime_seam.C3_CONTROLLED_RUNTIME_ACTIVATION_SCOPE_ATTESTATION_V1
                ),
                activation_evidence=_activation_evidence(),
                kill_switch=lambda: False,
            )
            def capture(permit):
                result = adapter(permit)
                captured.update(result)
                return result

            binding = runtime_seam.bind_c3_closed_repair_runtime_interlocks_v1(
                coordinator,
                startup_recovery=capture,
            )
            runtime_unlock_blocked = False
            try:
                binding.run_startup_recovery_v1()
            except coordinator_module.WriterRuntimeCoordinationBlocked as exc:
                runtime_unlock_blocked = (
                    "C3_STARTUP_RECOVERY_ATTESTATION_INVALID" in str(exc)
                )
            ready = binding.coordination_status()
            final_catalog = backend.list_prepared_transactions_offline()
            final_audit = backend.inspect_transaction_log_offline()
            all_requests_bound = bool(
                len(maintenance_epochs) == 2
                and len(set(maintenance_epochs)) == 1
                and maintenance_epochs[0] == captured.get("maintenance_epoch")
            )
            ok = bool(
                pending.get("coordination_ready") is False
                and pending.get("startup_recovery_verified") is False
                and captured.get("ok") is True
                and captured.get("prepared_transactions_before") == 2
                and captured.get("prepared_transactions_after") == 0
                and captured.get("resolved_transactions_after") == 0
                and captured.get("unresolved_transactions_after") == 0
                and captured.get("wal_inspected") is True
                and captured.get("transaction_log_inspected") is True
                and captured.get("recovery_completed") is True
                and captured.get("reconciliation_completed") is True
                and captured.get("real_registry_accessed") is False
                and captured.get("network_accessed") is False
                and captured.get("broker_called") is False
                and captured.get("no_order_sent") is True
                and runtime_unlock_blocked
                and ready.get("coordination_ready") is False
                and ready.get("runtime_activation_allowed") is False
                and ready.get("startup_recovery_verified") is False
                and final_catalog.get("prepared_count") == 0
                and final_audit.get("unresolved_prepared_count") == 0
                and final_audit.get("unresolved_resolved_count") == 0
                and all_requests_bound
                and repr(adapter)
                == "OfflineRuntimeStartupRecoveryAdapterV1(<protected>)"
            )
            return {
                "ok": ok,
                "status": (
                    "C3_RUNTIME_STARTUP_RECOVERY_ADAPTER_HARNESS_PASSED_OFFLINE"
                    if ok
                    else "C3_RUNTIME_STARTUP_RECOVERY_ADAPTER_HARNESS_FAILED_CLOSED"
                ),
                "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_HARNESS_V1_VERSION,
                "initial_prepared_count": captured.get(
                    "prepared_transactions_before"
                ),
                "final_prepared_count": final_catalog.get("prepared_count"),
                "final_resolved_count": final_audit.get(
                    "unresolved_resolved_count"
                ),
                "recovery_request_count": len(maintenance_epochs),
                "all_recovery_requests_bound_to_same_maintenance_epoch": all_requests_bound,
                "startup_recovery_attestation_sha256": captured.get(
                    "startup_recovery_attestation_sha256"
                ),
                "startup_recovery_verified": ready.get(
                    "startup_recovery_verified"
                ),
                "coordination_ready": ready.get("coordination_ready"),
                "runtime_unlock_blocked_for_offline_evidence": runtime_unlock_blocked,
                "adapter_repr_protected": "<protected>" in repr(adapter),
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
            }
        finally:
            runtime_seam.install_dormant_c3_closed_repair_writer_coordinator_v1(
                coordinator_module.build_closed_repair_writer_runtime_coordinator_v1()
            )


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_STARTUP_RECOVERY_ADAPTER_OFFLINE_HARNESS_V1_VERSION",
    "run_offline_runtime_startup_recovery_adapter_harness_v1",
]
