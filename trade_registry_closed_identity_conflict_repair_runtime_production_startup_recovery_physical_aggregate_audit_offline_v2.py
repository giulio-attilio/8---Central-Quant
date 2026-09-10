"""Pure fail-closed aggregate audit for temporary physical recovery evidence."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
import re

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2 as resolved_v2
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_AGGREGATE_AUDIT_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-AGGREGATE-AUDIT-OFFLINE-V2"
)
OFFLINE_PHYSICAL_AGGREGATE_AUDIT_SCOPE_ATTESTATION_V2 = (
    "C3_PHYSICAL_AGGREGATE_RECOVERY_AUDIT_TEMPORARY_ONLY_V2"
)
PHYSICAL_AGGREGATE_AUDIT_VERSION_V2 = (
    "C3_PHYSICAL_AGGREGATE_RECOVERY_AUDIT_REFERENCE_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AGGREGATE_KEYS = frozenset(
    {
        "audit_version", "backend_instance_sha256", "backend_snapshot_sha256",
        "registry_path_binding_sha256", "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256", "backend_generation",
        "resolved_ledger_generation", "transaction_log_audit_sha256",
        "prepared_catalog_sha256", "resolved_catalog_sha256",
        "wal_record_count", "wal_transaction_count",
        "unresolved_prepared_count", "unresolved_resolved_count",
        "total_pending_count", "raw_wal_resolved_state_supported",
        "separate_resolved_ledger_verified", "catalog_crosscheck_verified",
        "stable_observation_window_verified",
        "optimistic_atomic_observation_verified",
        "shared_lock_atomicity_verified", "complete_scan_verified",
        "wal_integrity_verified", "source_filesystem_accessed",
        "builder_filesystem_accessed", "write_executed",
        "real_registry_accessed", "network_accessed", "broker_called",
        "no_order_sent", "synthetic_only", "temporary_storage_only",
        "durable", "production_evidence", "production_ready",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "aggregate_audit_sha256",
    }
)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value["aggregate_audit_sha256"] = backend_v2.stable_sha256_v2(
        {
            key: item
            for key, item in value.items()
            if key != "aggregate_audit_sha256"
        }
    )
    return value


def physical_aggregate_recovery_audit_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _AGGREGATE_KEYS:
        return False
    supplied = str(value.get("aggregate_audit_sha256") or "")
    try:
        return bool(
            value["audit_version"] == PHYSICAL_AGGREGATE_AUDIT_VERSION_V2
            and all(
                _SHA256_RE.fullmatch(str(value[key] or ""))
                for key in (
                    "backend_instance_sha256", "backend_snapshot_sha256",
                    "registry_path_binding_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "lock_namespace_sha256", "transaction_log_audit_sha256",
                    "prepared_catalog_sha256", "resolved_catalog_sha256",
                    "aggregate_audit_sha256",
                )
            )
            and all(
                type(value[key]) is int and value[key] >= 0
                for key in (
                    "backend_generation", "resolved_ledger_generation",
                    "wal_record_count", "wal_transaction_count",
                    "unresolved_prepared_count", "unresolved_resolved_count",
                    "total_pending_count",
                )
            )
            and value["total_pending_count"]
            == value["unresolved_prepared_count"]
            + value["unresolved_resolved_count"]
            and all(
                value[key] is True
                for key in (
                    "separate_resolved_ledger_verified",
                    "catalog_crosscheck_verified",
                    "stable_observation_window_verified",
                    "optimistic_atomic_observation_verified",
                    "complete_scan_verified", "wal_integrity_verified",
                    "source_filesystem_accessed", "no_order_sent",
                    "synthetic_only", "temporary_storage_only",
                )
            )
            and all(
                value[key] is False
                for key in (
                    "raw_wal_resolved_state_supported",
                    "shared_lock_atomicity_verified",
                    "builder_filesystem_accessed", "write_executed",
                    "real_registry_accessed", "network_accessed",
                    "broker_called", "durable", "production_evidence",
                    "production_ready", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and hmac.compare_digest(
                supplied,
                backend_v2.stable_sha256_v2(
                    {
                        key: item
                        for key, item in value.items()
                        if key != "aggregate_audit_sha256"
                    }
                ),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class PhysicalAggregateRecoveryAuditConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)


class DormantPhysicalAggregateRecoveryAuditV2:
    def __init__(
        self, config: PhysicalAggregateRecoveryAuditConfigV2 | None = None
    ) -> None:
        self._config = config or PhysicalAggregateRecoveryAuditConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_V2_BLOCKED",
            "reason": reason,
            "aggregate_audit": None,
            "stable_observation_window_verified": False,
            "catalog_crosscheck_verified": False,
            "optimistic_atomic_observation_verified": False,
            "shared_lock_atomicity_verified": False,
            "builder_filesystem_accessed": False,
            "source_filesystem_accessed": False,
            "write_executed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "production_evidence": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def build_offline(
        self,
        *,
        initial_backend_snapshot: Any,
        transaction_log_audit: Any,
        prepared_catalog: Any,
        initial_resolved_catalog: Any,
        final_backend_snapshot: Any,
        final_transaction_log_audit: Any,
        final_prepared_catalog: Any,
        final_resolved_catalog: Any,
    ) -> dict[str, Any]:
        if self._config.enabled is not True:
            return self._failed("PHYSICAL_AGGREGATE_RECOVERY_AUDIT_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_AGGREGATE_AUDIT_SCOPE_ATTESTATION_V2
        ):
            return self._failed("PHYSICAL_AGGREGATE_RECOVERY_AUDIT_SCOPE_INVALID")
        evidence = (
            initial_backend_snapshot,
            transaction_log_audit,
            prepared_catalog,
            initial_resolved_catalog,
            final_backend_snapshot,
            final_transaction_log_audit,
            final_prepared_catalog,
            final_resolved_catalog,
        )
        if any(type(item) is not dict for item in evidence):
            return self._failed("PHYSICAL_AGGREGATE_RECOVERY_EVIDENCE_INVALID")
        source_filesystem_accessed = all(
            item.get("filesystem_accessed") is True
            for item in (
                initial_backend_snapshot,
                transaction_log_audit,
                initial_resolved_catalog,
                final_backend_snapshot,
                final_transaction_log_audit,
                final_resolved_catalog,
            )
        )
        try:
            validators_passed = bool(
                backend_v2.backend_snapshot_valid_v2(initial_backend_snapshot)
                and backend_v2.backend_snapshot_valid_v2(final_backend_snapshot)
                and startup_v1.temporary_transaction_log_audit_valid_v1(
                    transaction_log_audit, initial_backend_snapshot
                )
                and backend_v2.prepared_catalog_valid_v2(
                    prepared_catalog, initial_backend_snapshot
                )
                and startup_v1.temporary_transaction_log_audit_valid_v1(
                    final_transaction_log_audit, final_backend_snapshot
                )
                and backend_v2.prepared_catalog_valid_v2(
                    final_prepared_catalog, final_backend_snapshot
                )
                and resolved_v2.physical_resolved_catalog_valid_v2(
                    initial_resolved_catalog, initial_backend_snapshot
                )
                and resolved_v2.physical_resolved_catalog_valid_v2(
                    final_resolved_catalog, final_backend_snapshot
                )
            )
        except Exception:
            validators_passed = False
        if not validators_passed:
            failed = self._failed("PHYSICAL_AGGREGATE_RECOVERY_EVIDENCE_INVALID")
            failed["source_filesystem_accessed"] = source_filesystem_accessed
            return failed
        stable = bool(
            hmac.compare_digest(
                initial_backend_snapshot["snapshot_sha256"],
                final_backend_snapshot["snapshot_sha256"],
            )
            and initial_backend_snapshot == final_backend_snapshot
            and hmac.compare_digest(
                transaction_log_audit["audit_sha256"],
                final_transaction_log_audit["audit_sha256"],
            )
            and transaction_log_audit == final_transaction_log_audit
            and hmac.compare_digest(
                prepared_catalog["catalog_sha256"],
                final_prepared_catalog["catalog_sha256"],
            )
            and prepared_catalog == final_prepared_catalog
            and hmac.compare_digest(
                initial_resolved_catalog["catalog_sha256"],
                final_resolved_catalog["catalog_sha256"],
            )
            and initial_resolved_catalog == final_resolved_catalog
        )
        if not stable:
            failed = self._failed("PHYSICAL_OBSERVATION_WINDOW_CHANGED")
            failed["source_filesystem_accessed"] = source_filesystem_accessed
            return failed
        crosschecked = bool(
            transaction_log_audit["unresolved_prepared_count"]
            == prepared_catalog["prepared_count"]
            and transaction_log_audit["unresolved_resolved_count"] == 0
            and transaction_log_audit["resolved_state_supported"] is False
            and final_transaction_log_audit["unresolved_prepared_count"]
            == final_prepared_catalog["prepared_count"]
            and final_transaction_log_audit["unresolved_resolved_count"] == 0
            and final_transaction_log_audit["resolved_state_supported"] is False
            and initial_resolved_catalog["resolved_count"]
            == initial_resolved_catalog["record_count"]
            and prepared_catalog["backend_snapshot_sha256"]
            == initial_resolved_catalog["backend_snapshot_sha256"]
            == initial_backend_snapshot["snapshot_sha256"]
        )
        if not crosschecked:
            failed = self._failed("PHYSICAL_PENDING_CATALOG_CROSSCHECK_FAILED")
            failed.update(
                {
                    "stable_observation_window_verified": True,
                    "source_filesystem_accessed": source_filesystem_accessed,
                }
            )
            return failed
        aggregate = _seal(
            {
                "audit_version": PHYSICAL_AGGREGATE_AUDIT_VERSION_V2,
                "backend_instance_sha256": initial_backend_snapshot[
                    "backend_instance_sha256"
                ],
                "backend_snapshot_sha256": initial_backend_snapshot[
                    "snapshot_sha256"
                ],
                "registry_path_binding_sha256": initial_backend_snapshot[
                    "registry_path_binding_sha256"
                ],
                "resolved_ledger_storage_binding_sha256": (
                    initial_resolved_catalog[
                        "resolved_ledger_storage_binding_sha256"
                    ]
                ),
                "lock_namespace_sha256": initial_backend_snapshot[
                    "lock_namespace_sha256"
                ],
                "backend_generation": initial_backend_snapshot["generation"],
                "resolved_ledger_generation": initial_resolved_catalog[
                    "ledger_generation"
                ],
                "transaction_log_audit_sha256": transaction_log_audit[
                    "audit_sha256"
                ],
                "prepared_catalog_sha256": prepared_catalog["catalog_sha256"],
                "resolved_catalog_sha256": initial_resolved_catalog[
                    "catalog_sha256"
                ],
                "wal_record_count": transaction_log_audit["wal_record_count"],
                "wal_transaction_count": transaction_log_audit[
                    "transaction_count"
                ],
                "unresolved_prepared_count": prepared_catalog[
                    "prepared_count"
                ],
                "unresolved_resolved_count": initial_resolved_catalog[
                    "resolved_count"
                ],
                "total_pending_count": (
                    prepared_catalog["prepared_count"]
                    + initial_resolved_catalog["resolved_count"]
                ),
                "raw_wal_resolved_state_supported": False,
                "separate_resolved_ledger_verified": True,
                "catalog_crosscheck_verified": True,
                "stable_observation_window_verified": True,
                "optimistic_atomic_observation_verified": True,
                "shared_lock_atomicity_verified": False,
                "complete_scan_verified": True,
                "wal_integrity_verified": True,
                "source_filesystem_accessed": source_filesystem_accessed,
                "builder_filesystem_accessed": False,
                "write_executed": False,
                "real_registry_accessed": False,
                "network_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
                "synthetic_only": True,
                "temporary_storage_only": True,
                "durable": False,
                "production_evidence": False,
                "production_ready": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
            }
        )
        if not physical_aggregate_recovery_audit_valid_v2(aggregate):
            failed = self._failed(
                "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_SELF_VALIDATION_FAILED"
            )
            failed["source_filesystem_accessed"] = source_filesystem_accessed
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PHYSICAL_AGGREGATE_RECOVERY_AUDIT_V2_VERIFIED_OFFLINE",
                "reason": None,
                "aggregate_audit": aggregate,
                "stable_observation_window_verified": True,
                "catalog_crosscheck_verified": True,
                "optimistic_atomic_observation_verified": True,
                "source_filesystem_accessed": source_filesystem_accessed,
            }
        )
        return result


__all__ = [
    "DormantPhysicalAggregateRecoveryAuditV2",
    "OFFLINE_PHYSICAL_AGGREGATE_AUDIT_SCOPE_ATTESTATION_V2",
    "PHYSICAL_AGGREGATE_AUDIT_VERSION_V2",
    "PhysicalAggregateRecoveryAuditConfigV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_AGGREGATE_AUDIT_OFFLINE_V2_VERSION",
    "physical_aggregate_recovery_audit_valid_v2",
]
