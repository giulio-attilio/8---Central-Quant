"""Synthetic in-memory harness for the dormant pre-bootstrap bridge."""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_bridge_v1 as bridge


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def synthetic_registry_before_v1() -> dict[str, Any]:
    return {
        "version": "synthetic-prebootstrap-v1",
        "open_trades": {
            "open-keep": {
                "trade_id": "open-keep",
                "symbol": "BTCUSDT",
                "side": "LONG",
                "quantity": 0.001,
            }
        },
        "closed_trades": [
            {
                "trade_id": "synthetic-closed",
                "status": "CLOSED",
                "close_reason": "BROKER_RECONCILED_CLOSE",
                "pnl_r": -1.26907189,
                "r_multiple": -1.08850668,
                "metadata": {
                    "exit_reason": "STOP",
                    "outcome": {
                        "close_reason": "BROKER_RECONCILED_CLOSE",
                        "r_multiple": -1.08850668,
                    },
                    "preserve": {"exact": True},
                },
            }
        ],
        "extension": {"preserve": "exact"},
    }


def synthetic_registry_candidate_v1() -> dict[str, Any]:
    candidate = copy.deepcopy(synthetic_registry_before_v1())
    trade = candidate["closed_trades"][0]
    trade["close_reason"] = "STOP"
    trade["gross_r_multiple"] = -1.08850668
    trade["r_multiple"] = -1.26907189
    trade["metadata"]["outcome"]["close_reason"] = "STOP"
    trade["metadata"]["outcome"]["gross_r_multiple"] = -1.08850668
    trade["metadata"]["outcome"]["r_multiple"] = -1.26907189
    return candidate


def synthetic_changed_paths_v1() -> list[str]:
    return sorted(
        [
            "closed_trades[0].close_reason",
            "closed_trades[0].gross_r_multiple",
            "closed_trades[0].metadata.outcome.close_reason",
            "closed_trades[0].metadata.outcome.gross_r_multiple",
            "closed_trades[0].metadata.outcome.r_multiple",
            "closed_trades[0].r_multiple",
        ]
    )


def build_synthetic_prebootstrap_evidence_v1() -> dict[str, Any]:
    source = synthetic_registry_before_v1()
    candidate = synthetic_registry_candidate_v1()
    preview = {
        "receipt_version": "C3_CLOSED_IDENTITY_REPAIR_PREVIEW_RECEIPT_V1",
        "source_registry_sha256": _sha(source),
        "candidate_registry_sha256": _sha(candidate),
        "conflict_binding_sha256": "c" * 64,
        "selected_source_paths": {
            "close_reason": "trade.metadata.exit_reason",
            "pnl_r": "trade.pnl_r",
        },
        "gross_r_source_path": "trade.r_multiple",
        "gross_r_preservation_sha256": "d" * 64,
        "changed_paths": synthetic_changed_paths_v1(),
        "issued_at_epoch": 1_788_700_000,
        "expires_at_epoch": 1_788_700_300,
        "apply_allowed": False,
    }
    preview["preview_receipt_sha256"] = _sha(preview)
    return {
        "observed_at_epoch": 1_788_700_100,
        "synthetic_only": True,
        "production_authorization_valid": False,
        "runtime_binding_satisfied": False,
        "trading_controls": {
            "enable_real_trading": False,
            "broker_dry_run": True,
            "falcon_mode": "VERIFY",
            "central_real_execution_enabled": False,
            "central_real_pilot_enabled": False,
            "live_trading_enabled": False,
            "order_submission_authorized": False,
        },
        "registry_status": {
            "status": "PATCH_INSTALLED_MIGRATION_PENDING",
            "active_file_exists": True,
            "migration_pending": True,
            "migration_done": False,
            "restart_readiness_attested": False,
            "temporary_read_only": False,
            "write_allowed": False,
        },
        "conflict_audit": {
            "ok": True,
            "read_only": True,
            "write_executed": False,
            "registry_write": False,
            "conflict_count": 1,
            "financial_conflict_count": 2,
            "financial_conflict_fields": ["close_reason", "pnl_r"],
            "conflict_binding_sha256": "c" * 64,
            "safe_to_commit": False,
            "migration_compatible": False,
        },
        "maintenance_coordinator": {
            "enabled": True,
            "maintenance_only": True,
            "registered_writer_count": 19,
            "all_writers_registered": True,
            "inflight_mutations": 0,
            "shared_lock_backend_ready": True,
            "maintenance_lease_store_ready": True,
            "writer_mutations_allowed": False,
            "runtime_activation_allowed": False,
            "startup_recovery_verified": False,
        },
        "preview_receipt": preview,
    }


def build_synthetic_prebootstrap_request_v1() -> dict[str, Any]:
    request = {
        "ack": bridge.PREBOOTSTRAP_MAINTENANCE_REHEARSAL_ACK_V1,
        "scope_attestation": bridge.PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1,
        "evidence": build_synthetic_prebootstrap_evidence_v1(),
    }
    request["request_sha256"] = (
        bridge.prebootstrap_maintenance_request_sha256_v1(request)
    )
    return request


class SyntheticPrebootstrapEnvironmentV1:
    def __init__(self, request: dict[str, Any], fail_phase: str | None = None):
        self.request = copy.deepcopy(request)
        self.fail_phase = fail_phase
        self.events: list[str] = []
        self.source = synthetic_registry_before_v1()
        self.candidate = synthetic_registry_candidate_v1()
        self.registry = copy.deepcopy(self.source)
        self.open_before = copy.deepcopy(self.source["open_trades"])
        self.permit_identity: int | None = None
        self.bootstrap_done = False
        self.recovery_done = False

    def observe(self) -> dict[str, Any]:
        self.events.append("observe")
        if self.fail_phase == "observe_exception":
            raise RuntimeError("synthetic observation failure")
        observed = copy.deepcopy(self.request["evidence"])
        if self.fail_phase == "observation_drift":
            observed["observed_at_epoch"] += 1
        return observed

    @contextmanager
    def maintenance_lease(self):
        self.events.append("maintenance_enter")
        permit = SimpleNamespace(
            state="QUIESCED",
            registered_writer_count=19,
            inflight_mutations=0,
            shared_lock_acquired=True,
            maintenance_only=True,
            writer_mutations_allowed=False,
            runtime_activation_allowed=False,
            maintenance_epoch="a" * 64,
            lock_namespace_sha256="b" * 64,
        )
        if self.fail_phase == "permit_invalid":
            permit.registered_writer_count = 18
        self.permit_identity = id(permit)
        try:
            yield permit
        finally:
            self.events.append("maintenance_exit")

    def _same_permit(self, permit: Any) -> bool:
        return id(permit) == self.permit_identity

    @staticmethod
    def _safe_result(**values: Any) -> dict[str, Any]:
        return {
            "synthetic_only": True,
            "real_registry_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            **values,
        }

    def repair(self, preview: dict[str, Any], permit: Any) -> dict[str, Any]:
        self.events.append("repair")
        if self.fail_phase == "repair_exception":
            raise RuntimeError("synthetic repair failure")
        if self.fail_phase == "repair_rejected":
            return self._safe_result(ok=False, status="SYNTHETIC_REPAIR_REJECTED")
        if not self._same_permit(permit) or _sha(self.registry) != preview[
            "source_registry_sha256"
        ]:
            return self._safe_result(ok=False, status="SYNTHETIC_REPAIR_DRIFT")
        self.registry = copy.deepcopy(self.candidate)
        result = self._safe_result(
            ok=True,
            status="SYNTHETIC_CLOSED_REPAIR_APPLIED",
            simulated_registry_write=True,
            preservation_verified=True,
            gross_r_preservation_verified=True,
            open_trades_preserved_exactly=(
                self.registry["open_trades"] == self.open_before
            ),
            same_maintenance_permit=self._same_permit(permit),
            conflict_count_after=0,
            source_registry_sha256=_sha(self.source),
            candidate_registry_sha256=_sha(self.registry),
            changed_paths=synthetic_changed_paths_v1(),
        )
        if self.fail_phase == "repair_invalid_receipt":
            result["candidate_registry_sha256"] = "e" * 64
        return result

    def bootstrap(self, repair_result: dict[str, Any], permit: Any) -> dict[str, Any]:
        self.events.append("bootstrap")
        if self.fail_phase == "bootstrap_exception":
            raise RuntimeError("synthetic bootstrap failure")
        if self.fail_phase == "bootstrap_rejected":
            return self._safe_result(ok=False, status="SYNTHETIC_BOOTSTRAP_REJECTED")
        self.bootstrap_done = True
        return self._safe_result(
            ok=True,
            status="SYNTHETIC_BOOTSTRAP_COMPLETED",
            source_registry_sha256=_sha(self.registry),
            conflict_count_after=0,
            migration_done=True,
            restart_readiness_attested=True,
            last_load_ok=True,
            last_write_ok=True,
            write_allowed=True,
            same_maintenance_permit=self._same_permit(permit),
        )

    def startup_recovery(
        self, bootstrap_result: dict[str, Any], permit: Any
    ) -> dict[str, Any]:
        self.events.append("startup_recovery")
        if self.fail_phase == "recovery_exception":
            raise RuntimeError("synthetic recovery failure")
        if self.fail_phase == "recovery_rejected":
            return self._safe_result(ok=False, status="SYNTHETIC_RECOVERY_REJECTED")
        self.recovery_done = True
        return self._safe_result(
            ok=True,
            status="SYNTHETIC_STARTUP_RECOVERY_COMPLETED",
            startup_recovery_verified=True,
            prepared_transactions_after=0,
            resolved_transactions_after=0,
            unresolved_transactions_after=0,
            maintenance_epoch=permit.maintenance_epoch,
            lock_namespace_sha256=permit.lock_namespace_sha256,
        )

    def postflight(self, recovery_result: dict[str, Any], permit: Any) -> dict[str, Any]:
        self.events.append("postflight")
        if self.fail_phase == "postflight_rejected":
            return self._safe_result(ok=False, status="SYNTHETIC_POSTFLIGHT_REJECTED")
        return self._safe_result(
            ok=True,
            status="SYNTHETIC_READINESS_PROJECTED",
            registry_storage_ready=True,
            coordination_ready=True,
            registered_writer_count=19,
            startup_recovery_verified=True,
            same_maintenance_permit=self._same_permit(permit),
            runtime_integrated=False,
            production_ready=False,
            live_allowed=False,
        )

    def rollback(self, repair_result: dict[str, Any], permit: Any) -> dict[str, Any]:
        self.events.append("rollback")
        if self.fail_phase == "rollback_rejected":
            return self._safe_result(ok=False, status="SYNTHETIC_ROLLBACK_REJECTED")
        self.registry = copy.deepcopy(self.source)
        self.bootstrap_done = False
        self.recovery_done = False
        return self._safe_result(
            ok=True,
            status="SYNTHETIC_PREBOOTSTRAP_ROLLBACK_VERIFIED",
            source_restored=_sha(self.registry) == _sha(self.source),
            open_trades_preserved_exactly=(
                self.registry["open_trades"] == self.open_before
            ),
            same_maintenance_permit=self._same_permit(permit),
        )


def build_synthetic_prebootstrap_bridge_v1(
    *,
    enabled: bool,
    request: dict[str, Any] | None = None,
    fail_phase: str | None = None,
) -> tuple[
    bridge.PrebootstrapMaintenanceBridgeV1,
    SyntheticPrebootstrapEnvironmentV1,
    dict[str, Any],
]:
    selected_request = copy.deepcopy(
        request or build_synthetic_prebootstrap_request_v1()
    )
    environment = SyntheticPrebootstrapEnvironmentV1(
        selected_request, fail_phase=fail_phase
    )
    instance = bridge.PrebootstrapMaintenanceBridgeV1(
        observe=environment.observe,
        maintenance_lease=environment.maintenance_lease,
        repair=environment.repair,
        bootstrap=environment.bootstrap,
        startup_recovery=environment.startup_recovery,
        postflight=environment.postflight,
        rollback=environment.rollback,
        config=bridge.PrebootstrapMaintenanceBridgeConfigV1(
            enabled=enabled,
            scope_attestation=(
                bridge.PREBOOTSTRAP_MAINTENANCE_REHEARSAL_SCOPE_ATTESTATION_V1
                if enabled
                else None
            ),
        ),
    )
    return instance, environment, selected_request


def run_synthetic_prebootstrap_maintenance_harness_v1() -> dict[str, Any]:
    instance, environment, request = build_synthetic_prebootstrap_bridge_v1(
        enabled=True
    )
    result = instance.run_offline(request)
    return {
        "result": result,
        "events": list(environment.events),
        "source_registry_sha256": _sha(environment.source),
        "final_registry_sha256": _sha(environment.registry),
        "candidate_registry_sha256": _sha(environment.candidate),
        "open_trades_preserved_exactly": (
            environment.registry["open_trades"] == environment.open_before
        ),
        "real_registry_accessed": False,
        "write_executed": False,
        "registry_write": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "runtime_integrated": False,
        "live_allowed": False,
    }


__all__ = [
    "SyntheticPrebootstrapEnvironmentV1",
    "build_synthetic_prebootstrap_bridge_v1",
    "build_synthetic_prebootstrap_evidence_v1",
    "build_synthetic_prebootstrap_request_v1",
    "run_synthetic_prebootstrap_maintenance_harness_v1",
    "synthetic_changed_paths_v1",
    "synthetic_registry_before_v1",
    "synthetic_registry_candidate_v1",
]
