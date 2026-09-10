"""Collect aggregate recovery evidence while one synthetic two-store lease is live."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_v2 as aggregate_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as lease_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2 as resolved_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-LOCKED-AGGREGATE-COLLECTION-"
    "OFFLINE-V2"
)
OFFLINE_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_ATTESTATION_V2 = (
    "C3_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_TEMPORARY_ONLY_V2"
)
PHYSICAL_LOCKED_AGGREGATE_COLLECTION_RECEIPT_VERSION_V2 = (
    "C3_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_RECEIPT_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "lease_token_sha256", "lock_order_sha256",
        "backend_object_identity_sha256", "ledger_object_identity_sha256",
        "backend_lock_namespace_sha256",
        "resolved_ledger_storage_binding_sha256",
        "aggregate_audit_sha256", "initial_backend_snapshot_sha256",
        "final_backend_snapshot_sha256", "initial_transaction_log_audit_sha256",
        "final_transaction_log_audit_sha256", "initial_prepared_catalog_sha256",
        "final_prepared_catalog_sha256", "initial_resolved_catalog_sha256",
        "final_resolved_catalog_sha256", "lease_revalidation_count",
        "held_lock_count", "same_lease_instance_verified",
        "same_backend_instance_verified", "same_ledger_instance_verified",
        "shared_lock_atomicity_verified", "stable_observation_window_verified",
        "catalog_crosscheck_verified", "lease_released_after_collection",
        "temporary_storage_only", "synthetic_only", "production_authority",
        "production_ready", "runtime_integrated", "activation_allowed",
        "live_allowed", "write_executed", "registry_write",
        "real_registry_accessed", "network_accessed", "broker_called",
        "no_order_sent", "issued_at_epoch", "expires_at_epoch",
        "receipt_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def physical_locked_aggregate_collection_receipt_sha256_v2(
    value: dict[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def physical_locked_aggregate_collection_receipt_valid_v2(value: Any) -> bool:
    if type(value) is not dict or set(value) != _RECEIPT_KEYS:
        return False
    supplied = str(value.get("receipt_sha256") or "")
    try:
        return bool(
            value["receipt_version"]
            == PHYSICAL_LOCKED_AGGREGATE_COLLECTION_RECEIPT_VERSION_V2
            and all(
                _valid_sha(value[key])
                for key in (
                    "lease_token_sha256", "lock_order_sha256",
                    "backend_object_identity_sha256", "ledger_object_identity_sha256",
                    "backend_lock_namespace_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "aggregate_audit_sha256", "initial_backend_snapshot_sha256",
                    "final_backend_snapshot_sha256",
                    "initial_transaction_log_audit_sha256",
                    "final_transaction_log_audit_sha256",
                    "initial_prepared_catalog_sha256", "final_prepared_catalog_sha256",
                    "initial_resolved_catalog_sha256", "final_resolved_catalog_sha256",
                    "receipt_sha256",
                )
            )
            and value["initial_backend_snapshot_sha256"]
            == value["final_backend_snapshot_sha256"]
            and value["initial_transaction_log_audit_sha256"]
            == value["final_transaction_log_audit_sha256"]
            and value["initial_prepared_catalog_sha256"]
            == value["final_prepared_catalog_sha256"]
            and value["initial_resolved_catalog_sha256"]
            == value["final_resolved_catalog_sha256"]
            and value["lease_revalidation_count"] == 8
            and value["held_lock_count"] == 2
            and all(
                value[key] is True
                for key in (
                    "same_lease_instance_verified", "same_backend_instance_verified",
                    "same_ledger_instance_verified", "shared_lock_atomicity_verified",
                    "stable_observation_window_verified",
                    "catalog_crosscheck_verified", "lease_released_after_collection",
                    "temporary_storage_only", "synthetic_only", "no_order_sent",
                )
            )
            and all(
                value[key] is False
                for key in (
                    "production_authority", "production_ready", "runtime_integrated",
                    "activation_allowed", "live_allowed", "write_executed",
                    "registry_write", "real_registry_accessed", "network_accessed",
                    "broker_called",
                )
            )
            and type(value["issued_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and value["issued_at_epoch"] < value["expires_at_epoch"]
            and hmac.compare_digest(
                supplied,
                physical_locked_aggregate_collection_receipt_sha256_v2(value),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class PhysicalLockedAggregateCollectionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_lease_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_backend_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_ledger_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    lease_ttl_seconds: int = 60

    def __post_init__(self) -> None:
        if not 1 <= self.lease_ttl_seconds <= 300:
            raise ValueError("lease_ttl_seconds must be between 1 and 300")


class PhysicalLockedAggregateCollectionV2:
    def __init__(
        self,
        config: PhysicalLockedAggregateCollectionConfigV2 | None = None,
        *,
        observation_lease: Any = None,
        backend: Any = None,
        durable_authority_ledger: Any = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or PhysicalLockedAggregateCollectionConfigV2()
        self._lease = observation_lease
        self._backend = backend
        self._ledger = durable_authority_ledger
        self._clock = clock or (lambda: 0)

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_V2_BLOCKED",
            "reason": reason,
            "backend_snapshot": None,
            "aggregate_audit": None,
            "collection_receipt": None,
            "lease_revalidation_count": 0,
            "shared_lock_atomicity_verified": False,
            "stable_observation_window_verified": False,
            "catalog_crosscheck_verified": False,
            "lease_released_after_collection": False,
            "filesystem_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_ATTESTATION_V2
        ):
            return "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_INVALID"
        pins = (
            self._config.expected_lease_object_identity_sha256,
            self._config.expected_backend_object_identity_sha256,
            self._config.expected_ledger_object_identity_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_PINS_INVALID"
        if not (
            type(self._lease) is lease_v2.PhysicalMultiStoreObservationLeaseV2
            and type(self._backend)
            is physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2
            and type(self._ledger)
            is durable_v2.DormantDurableReconciliationAuthorityLedgerV2
        ):
            return "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_DEPENDENCY_INVALID"
        identities = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._lease
            ),
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._backend
            ),
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._ledger
            ),
        )
        if identities != pins:
            return "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_IDENTITY_MISMATCH"
        return None

    def collect_offline(self) -> dict[str, Any]:
        result = self._failed("")
        reason = self._reason()
        if reason is not None:
            result["reason"] = reason
            return result
        try:
            issued_at = int(self._clock())
        except Exception:
            result["reason"] = "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_CLOCK_INVALID"
            return result
        expires_at = issued_at + self._config.lease_ttl_seconds
        read_count = 0
        receipt_material: dict[str, Any] | None = None
        try:
            with self._lease.hold_offline(expires_at_epoch=expires_at) as token:
                def now() -> int:
                    return int(self._clock())

                initial_snapshot = dict(
                    self._lease.read_backend_snapshot_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                initial_audit = dict(
                    self._lease.read_transaction_log_audit_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                initial_prepared = dict(
                    self._lease.read_prepared_catalog_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                initial_scan = dict(
                    self._lease.read_resolved_scan_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                initial_resolved = resolved_v2.build_physical_resolved_catalog_from_scan_v2(
                    scan=initial_scan,
                    backend_snapshot=initial_snapshot,
                    expected_storage_binding_sha256=(
                        token.resolved_ledger_storage_binding_sha256
                    ),
                )
                final_snapshot = dict(
                    self._lease.read_backend_snapshot_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                final_audit = dict(
                    self._lease.read_transaction_log_audit_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                final_prepared = dict(
                    self._lease.read_prepared_catalog_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                final_scan = dict(
                    self._lease.read_resolved_scan_offline(
                        token, now_epoch=now()
                    )
                )
                read_count += 1
                final_resolved = resolved_v2.build_physical_resolved_catalog_from_scan_v2(
                    scan=final_scan,
                    backend_snapshot=final_snapshot,
                    expected_storage_binding_sha256=(
                        token.resolved_ledger_storage_binding_sha256
                    ),
                )
                aggregate_result = aggregate_v2.DormantPhysicalAggregateRecoveryAuditV2(
                    aggregate_v2.PhysicalAggregateRecoveryAuditConfigV2(
                        enabled=True,
                        scope_attestation=(
                            aggregate_v2.OFFLINE_PHYSICAL_AGGREGATE_AUDIT_SCOPE_ATTESTATION_V2
                        ),
                    )
                ).build_offline(
                    initial_backend_snapshot=initial_snapshot,
                    transaction_log_audit=initial_audit,
                    prepared_catalog=initial_prepared,
                    initial_resolved_catalog=initial_resolved,
                    final_backend_snapshot=final_snapshot,
                    final_transaction_log_audit=final_audit,
                    final_prepared_catalog=final_prepared,
                    final_resolved_catalog=final_resolved,
                )
                aggregate = aggregate_result.get("aggregate_audit")
                lease_snapshot = self._lease.snapshot()
                if not (
                    aggregate_result.get("ok") is True
                    and aggregate_v2.physical_aggregate_recovery_audit_valid_v2(
                        aggregate
                    )
                    and read_count == 8
                    and self._lease.validate_live(
                        token,
                        backend=self._backend,
                        durable_authority_ledger=self._ledger,
                        now_epoch=now(),
                    )
                    and lease_snapshot["held_lock_count"] == 2
                    and lease_snapshot["all_handles_live"] is True
                ):
                    raise ValueError("LOCKED_AGGREGATE_POSTCONDITIONS_INVALID")
                receipt_material = {
                    "receipt_version": PHYSICAL_LOCKED_AGGREGATE_COLLECTION_RECEIPT_VERSION_V2,
                    "lease_token_sha256": token.token_sha256,
                    "lock_order_sha256": token.lock_order_sha256,
                    "backend_object_identity_sha256": token.backend_object_identity_sha256,
                    "ledger_object_identity_sha256": token.ledger_object_identity_sha256,
                    "backend_lock_namespace_sha256": token.backend_lock_namespace_sha256,
                    "resolved_ledger_storage_binding_sha256": token.resolved_ledger_storage_binding_sha256,
                    "aggregate_audit_sha256": aggregate["aggregate_audit_sha256"],
                    "initial_backend_snapshot_sha256": initial_snapshot["snapshot_sha256"],
                    "final_backend_snapshot_sha256": final_snapshot["snapshot_sha256"],
                    "initial_transaction_log_audit_sha256": initial_audit["audit_sha256"],
                    "final_transaction_log_audit_sha256": final_audit["audit_sha256"],
                    "initial_prepared_catalog_sha256": initial_prepared["catalog_sha256"],
                    "final_prepared_catalog_sha256": final_prepared["catalog_sha256"],
                    "initial_resolved_catalog_sha256": initial_resolved["catalog_sha256"],
                    "final_resolved_catalog_sha256": final_resolved["catalog_sha256"],
                    "lease_revalidation_count": read_count,
                    "held_lock_count": 2,
                    "same_lease_instance_verified": True,
                    "same_backend_instance_verified": True,
                    "same_ledger_instance_verified": True,
                    "shared_lock_atomicity_verified": True,
                    "stable_observation_window_verified": True,
                    "catalog_crosscheck_verified": True,
                    "lease_released_after_collection": False,
                    "temporary_storage_only": True,
                    "synthetic_only": True,
                    "production_authority": False,
                    "production_ready": False,
                    "runtime_integrated": False,
                    "activation_allowed": False,
                    "live_allowed": False,
                    "write_executed": False,
                    "registry_write": False,
                    "real_registry_accessed": False,
                    "network_accessed": False,
                    "broker_called": False,
                    "no_order_sent": True,
                    "issued_at_epoch": token.issued_at_epoch,
                    "expires_at_epoch": token.expires_at_epoch,
                }
                receipt_material["receipt_sha256"] = (
                    physical_locked_aggregate_collection_receipt_sha256_v2(
                        receipt_material
                    )
                )
        except Exception as exc:
            result["reason"] = (
                str(exc)
                if re.fullmatch(r"[A-Z0-9_]{1,160}", str(exc))
                else "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_FAILED_CLOSED"
            )
            result["lease_revalidation_count"] = read_count
            result["filesystem_accessed"] = read_count > 0
            result["lease_released_after_collection"] = (
                self._lease.snapshot()["held_lock_count"] == 0
            )
            return result
        lease_released = self._lease.snapshot()["held_lock_count"] == 0
        if receipt_material is None or not lease_released:
            result["reason"] = "PHYSICAL_LOCKED_AGGREGATE_RECEIPT_UNAVAILABLE"
            return result
        receipt_material["lease_released_after_collection"] = lease_released
        receipt_material["receipt_sha256"] = (
            physical_locked_aggregate_collection_receipt_sha256_v2(
                receipt_material
            )
        )
        if not physical_locked_aggregate_collection_receipt_valid_v2(
            receipt_material
        ):
            result["reason"] = "PHYSICAL_LOCKED_AGGREGATE_RECEIPT_INVALID"
            return result
        result.update(
            {
                "ok": True,
                "status": "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_V2_VERIFIED_OFFLINE",
                "reason": None,
                "backend_snapshot": initial_snapshot,
                "aggregate_audit": aggregate,
                "collection_receipt": receipt_material,
                "lease_revalidation_count": read_count,
                "shared_lock_atomicity_verified": True,
                "stable_observation_window_verified": True,
                "catalog_crosscheck_verified": True,
                "lease_released_after_collection": True,
                "filesystem_accessed": True,
            }
        )
        return result


__all__ = [
    "OFFLINE_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_SCOPE_ATTESTATION_V2",
    "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_RECEIPT_VERSION_V2",
    "PhysicalLockedAggregateCollectionConfigV2",
    "PhysicalLockedAggregateCollectionV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_LOCKED_AGGREGATE_COLLECTION_OFFLINE_V2_VERSION",
    "physical_locked_aggregate_collection_receipt_sha256_v2",
    "physical_locked_aggregate_collection_receipt_valid_v2",
]
