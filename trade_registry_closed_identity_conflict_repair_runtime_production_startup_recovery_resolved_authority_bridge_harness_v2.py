"""Offline harness for the dormant RESOLVED-authority startup bridge."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_harness_v2 as store_harness_v2
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_HARNESS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-RESOLVED-AUTHORITY-BRIDGE-HARNESS-V2"
)


class _SyntheticPreparedRecovery:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, permit: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        attestation = {
            "ok": True,
            "status": "SYNTHETIC_PREPARED_RECOVERY_COMPLETED",
            "wal_inspected": True,
            "transaction_log_inspected": True,
            "prepared_transactions_inspected": True,
            "resolved_transactions_inspected": True,
            "prepared_transactions_before": 2,
            "resolved_transactions_before": 0,
            "prepared_transactions_after": 0,
            "resolved_transactions_after": 0,
            "unresolved_transactions_after": 0,
            "recovery_completed": True,
            "reconciliation_completed": True,
            "maintenance_epoch": permit["maintenance_epoch"],
            "lock_namespace_sha256": permit["lock_namespace_sha256"],
            "real_registry_accessed": False,
            "write_executed": True,
            "registry_write": True,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        attestation["startup_recovery_attestation_sha256"] = (
            runtime_seam_v1.startup_recovery_attestation_sha256_v1(
                attestation
            )
        )
        return attestation


def run_resolved_authority_startup_recovery_bridge_harness_v2() -> dict[str, Any]:
    root_path: Path | None = None
    with tempfile.TemporaryDirectory(prefix="c3_resolved_bridge_v2_") as root:
        root_path = Path(root)
        values = (
            store_harness_v2.build_resolved_authority_physical_store_reference_context_v2(
                root_path
            )
        )
        store = values["reference"]
        prepared = _SyntheticPreparedRecovery()
        bridge = bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2(
            bridge_v2.ResolvedAuthorityStartupRecoveryBridgeConfigV2(
                enabled=True,
                scope_attestation=(
                    bridge_v2.OFFLINE_RESOLVED_AUTHORITY_STARTUP_BRIDGE_SCOPE_ATTESTATION_V2
                ),
                expected_prepared_recovery_object_identity_sha256=(
                    identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        prepared
                    )
                ),
                expected_physical_store_object_identity_sha256=(
                    identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                        store
                    )
                ),
            ),
            prepared_recovery=prepared,
            physical_store=store,
            clock=lambda: store_harness_v2.SYNTHETIC_NOW_V2,
        )
        permit = {
            "maintenance_epoch": hash_v2.stable_sha256_v2(
                {"maintenance_epoch": "resolved-bridge"}
            ),
            "state": "QUIESCED",
            "lock_namespace_sha256": hash_v2.stable_sha256_v2(
                {"lock_namespace": "resolved-bridge"}
            ),
            "registered_writer_count": 19,
            "inflight_mutations": 0,
            "shared_lock_acquired": True,
        }
        before = bridge.snapshot()
        result = bridge(permit)
        supplied_sha = result.get("startup_recovery_attestation_sha256")
        ok = bool(
            before["temporary_offline_ready"] is True
            and before["physical_store_implementation_bound"] is True
            and result.get("ok") is True
            and result.get("prepared_transactions_before") == 2
            and result.get("prepared_transactions_after") == 0
            and result.get("resolved_transactions_before") == 0
            and result.get("resolved_transactions_after") == 0
            and result.get("unresolved_transactions_after") == 0
            and result.get("authoritative_resolved_record_count") == 0
            and result.get("physical_resolved_store_inspected") is True
            and result.get("physical_store_implementation_bound") is True
            and result.get("root_signature_reverified") is True
            and result.get("root_revocation_checked") is True
            and result.get("real_registry_accessed") is False
            and result.get("network_accessed") is False
            and result.get("broker_called") is False
            and result.get("no_order_sent") is True
            and result.get("production_ready") is False
            and result.get("runtime_integrated") is False
            and result.get("live_allowed") is False
            and prepared.call_count == 1
            and isinstance(supplied_sha, str)
            and supplied_sha
            == runtime_seam_v1.startup_recovery_attestation_sha256_v1(result)
            and repr(bridge)
            == "ResolvedAuthorityStartupRecoveryBridgeV2(<protected>)"
        )
    temporary_storage_removed = bool(root_path and not root_path.exists())
    ok = bool(ok and temporary_storage_removed)
    return {
        "ok": ok,
        "status": (
            "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_HARNESS_V2_PASSED"
            if ok
            else "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_HARNESS_V2_FAILED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_HARNESS_V2_VERSION,
        "reason": result.get("reason"),
        "temporary_storage_removed": temporary_storage_removed,
        "prepared_recovery_called_once": prepared.call_count == 1,
        "physical_store_implementation_bound": True,
        "temporary_storage_only": True,
        "synthetic_only": True,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
    }


__all__ = [
    "run_resolved_authority_startup_recovery_bridge_harness_v2",
]
