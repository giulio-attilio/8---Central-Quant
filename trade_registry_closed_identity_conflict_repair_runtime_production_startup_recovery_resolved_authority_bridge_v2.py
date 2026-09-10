"""Dormant startup bridge for PREPARED recovery plus RESOLVED authority.

The runtime placeholder is default-off and performs no I/O.  The enabled
surface is restricted to synthetic temporary storage and combines one existing
PREPARED recovery callback with the exact physical RESOLVED store reference.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2 as physical_store_v2
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-RESOLVED-AUTHORITY-BRIDGE-V2"
)
OFFLINE_RESOLVED_AUTHORITY_STARTUP_BRIDGE_SCOPE_ATTESTATION_V2 = (
    "C3_RESOLVED_AUTHORITY_STARTUP_BRIDGE_TEMPORARY_SYNTHETIC_ONLY_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _permit_valid(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value)
        == {
            "maintenance_epoch",
            "state",
            "lock_namespace_sha256",
            "registered_writer_count",
            "inflight_mutations",
            "shared_lock_acquired",
        }
        and _valid_sha(value.get("maintenance_epoch"))
        and value.get("state") == "QUIESCED"
        and _valid_sha(value.get("lock_namespace_sha256"))
        and value.get("registered_writer_count") == 19
        and value.get("inflight_mutations") == 0
        and value.get("shared_lock_acquired") is True
    )


def _prepared_attestation_valid(value: Any, permit: Mapping[str, Any]) -> bool:
    if not isinstance(value, Mapping):
        return False
    supplied = str(value.get("startup_recovery_attestation_sha256") or "")
    counts = (
        value.get("prepared_transactions_before"),
        value.get("resolved_transactions_before"),
        value.get("prepared_transactions_after"),
        value.get("resolved_transactions_after"),
        value.get("unresolved_transactions_after"),
    )
    try:
        return bool(
            value.get("ok") is True
            and all(type(item) is int and item >= 0 for item in counts)
            and counts[2:] == (0, 0, 0)
            and value.get("wal_inspected") is True
            and value.get("transaction_log_inspected") is True
            and value.get("prepared_transactions_inspected") is True
            and value.get("resolved_transactions_inspected") is True
            and value.get("recovery_completed") is True
            and value.get("reconciliation_completed") is True
            and value.get("maintenance_epoch") == permit["maintenance_epoch"]
            and value.get("lock_namespace_sha256")
            == permit["lock_namespace_sha256"]
            and value.get("real_registry_accessed") is False
            and type(value.get("write_executed")) is bool
            and type(value.get("registry_write")) is bool
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("no_order_sent") is True
            and _valid_sha(supplied)
            and hmac.compare_digest(
                supplied,
                runtime_seam_v1.startup_recovery_attestation_sha256_v1(value),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class ResolvedAuthorityStartupRecoveryBridgeConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_prepared_recovery_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_physical_store_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class ResolvedAuthorityStartupRecoveryBridgeV2:
    def __init__(
        self,
        config: ResolvedAuthorityStartupRecoveryBridgeConfigV2 | None = None,
        *,
        prepared_recovery: Callable[[Mapping[str, Any]], Mapping[str, Any]]
        | None = None,
        physical_store: Any = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or ResolvedAuthorityStartupRecoveryBridgeConfigV2()
        self._prepared_recovery = prepared_recovery
        self._physical_store = physical_store
        self._clock = clock

    def __repr__(self) -> str:
        return "ResolvedAuthorityStartupRecoveryBridgeV2(<protected>)"

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_V2_BLOCKED",
            "reason": reason,
            "wal_inspected": False,
            "transaction_log_inspected": False,
            "prepared_transactions_inspected": False,
            "resolved_transactions_inspected": False,
            "recovery_completed": False,
            "reconciliation_completed": False,
            "physical_resolved_store_inspected": False,
            "physical_store_implementation_bound": False,
            "filesystem_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_RESOLVED_AUTHORITY_STARTUP_BRIDGE_SCOPE_ATTESTATION_V2
        ):
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_SCOPE_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                config.expected_prepared_recovery_object_identity_sha256,
                config.expected_physical_store_object_identity_sha256,
            )
        ):
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_PINS_INVALID"
        if not callable(self._prepared_recovery) or not callable(self._clock):
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_DEPENDENCY_INVALID"
        if type(self._physical_store) is not physical_store_v2.ResolvedAuthorityPhysicalStoreReferenceV2:
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_PHYSICAL_STORE_INVALID"
        if not (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._prepared_recovery
            )
            == config.expected_prepared_recovery_object_identity_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._physical_store
            )
            == config.expected_physical_store_object_identity_sha256
        ):
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_INSTANCE_MISMATCH"
        physical_snapshot = self._physical_store.snapshot()
        if not (
            physical_snapshot.get("ready_for_temporary_offline_use") is True
            and physical_snapshot.get("physical_store_implementation_bound")
            is True
            and physical_snapshot.get("production_ready") is False
            and physical_snapshot.get("runtime_integrated") is False
            and physical_snapshot.get("live_allowed") is False
        ):
            return "RESOLVED_AUTHORITY_STARTUP_RECOVERY_PHYSICAL_STORE_NOT_READY"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        physical_snapshot = (
            self._physical_store.snapshot()
            if type(self._physical_store)
            is physical_store_v2.ResolvedAuthorityPhysicalStoreReferenceV2
            else {}
        )
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_V2_VERSION,
            "enabled": self._config.enabled is True,
            "default_off": self._config.enabled is not True,
            "temporary_offline_ready": reason is None,
            "reason": reason,
            "physical_store_implementation_bound": reason is None,
            "storage_binding_sha256": physical_snapshot.get(
                "storage_binding_sha256"
            ),
            "root_authority_attestation_sha256": physical_snapshot.get(
                "root_authority_attestation_sha256"
            ),
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def __call__(self, maintenance_permit: Mapping[str, Any]) -> dict[str, Any]:
        reason = self._reason()
        if reason is not None:
            return self._failed(reason)
        if not _permit_valid(maintenance_permit):
            return self._failed(
                "RESOLVED_AUTHORITY_STARTUP_RECOVERY_MAINTENANCE_PERMIT_INVALID"
            )
        try:
            now_epoch = self._clock()
        except Exception:
            return self._failed("RESOLVED_AUTHORITY_STARTUP_RECOVERY_CLOCK_FAILED")
        if type(now_epoch) is not int:
            return self._failed("RESOLVED_AUTHORITY_STARTUP_RECOVERY_CLOCK_INVALID")
        try:
            prepared = self._prepared_recovery(dict(maintenance_permit))
        except Exception:
            return self._failed("PREPARED_STARTUP_RECOVERY_FAILED_CLOSED")
        if not _prepared_attestation_valid(prepared, maintenance_permit):
            return self._failed("PREPARED_STARTUP_RECOVERY_ATTESTATION_INVALID")
        opened = self._physical_store.open_offline(now_epoch=now_epoch)
        recovered = self._physical_store.recover_offline(now_epoch=now_epoch)
        scanned = self._physical_store.read_resolved_records_offline(
            now_epoch=now_epoch
        )
        if not (
            opened.get("ok") is True
            and recovered.get("ok") is True
            and scanned.get("ok") is True
            and scanned.get("complete_scan_verified") is True
            and scanned.get("wal_integrity_verified") is True
            and type(scanned.get("record_count")) is int
            and scanned.get("record_count") >= 0
            and recovered.get("root_signature_reverified") is True
            and scanned.get("root_signature_reverified") is True
            and recovered.get("root_revocation_checked") is True
            and scanned.get("root_revocation_checked") is True
            and recovered.get("root_revoked") is False
            and scanned.get("root_revoked") is False
        ):
            return self._failed("RESOLVED_AUTHORITY_PHYSICAL_RECOVERY_INVALID")
        attestation = {
            "ok": True,
            "status": "C3_RESOLVED_AUTHORITY_STARTUP_RECOVERY_BRIDGE_V2_COMPLETED_OFFLINE",
            "adapter_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_V2_VERSION,
            "wal_inspected": True,
            "transaction_log_inspected": True,
            "prepared_transactions_inspected": True,
            "resolved_transactions_inspected": True,
            "prepared_transactions_before": prepared[
                "prepared_transactions_before"
            ],
            "resolved_transactions_before": 0,
            "prepared_transactions_after": 0,
            "resolved_transactions_after": 0,
            "unresolved_transactions_after": 0,
            "authoritative_resolved_record_count": scanned["record_count"],
            "recovery_completed": True,
            "reconciliation_completed": True,
            "maintenance_epoch": maintenance_permit["maintenance_epoch"],
            "lock_namespace_sha256": maintenance_permit[
                "lock_namespace_sha256"
            ],
            "prepared_recovery_attestation_sha256": prepared[
                "startup_recovery_attestation_sha256"
            ],
            "resolved_store_open_receipt_sha256": opened["receipt_sha256"],
            "resolved_store_recovery_receipt_sha256": recovered[
                "receipt_sha256"
            ],
            "resolved_store_scan_receipt_sha256": scanned["receipt_sha256"],
            "storage_binding_sha256": scanned["storage_binding_sha256"],
            "root_authority_attestation_sha256": self._physical_store.snapshot()[
                "root_authority_attestation_sha256"
            ],
            "physical_resolved_store_inspected": True,
            "physical_store_implementation_bound": True,
            "root_signature_reverified": True,
            "root_revocation_checked": True,
            "filesystem_accessed": True,
            "write_executed": bool(
                prepared["write_executed"]
                or recovered.get("temporary_write_executed")
            ),
            "registry_write": prepared["registry_write"],
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        attestation["startup_recovery_attestation_sha256"] = (
            runtime_seam_v1.startup_recovery_attestation_sha256_v1(
                attestation
            )
        )
        return attestation


def build_dormant_resolved_authority_startup_recovery_bridge_v2(
) -> ResolvedAuthorityStartupRecoveryBridgeV2:
    """Return a no-dependency placeholder that cannot run recovery."""

    return ResolvedAuthorityStartupRecoveryBridgeV2()


__all__ = [
    "OFFLINE_RESOLVED_AUTHORITY_STARTUP_BRIDGE_SCOPE_ATTESTATION_V2",
    "ResolvedAuthorityStartupRecoveryBridgeConfigV2",
    "ResolvedAuthorityStartupRecoveryBridgeV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_RESOLVED_AUTHORITY_BRIDGE_V2_VERSION",
    "build_dormant_resolved_authority_startup_recovery_bridge_v2",
]
