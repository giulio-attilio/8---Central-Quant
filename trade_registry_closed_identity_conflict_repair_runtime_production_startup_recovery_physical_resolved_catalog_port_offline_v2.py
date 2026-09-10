"""Read-only RESOLVED catalog port over the synthetic physical authority ledger."""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as source_ports_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-RESOLVED-CATALOG-PORT-OFFLINE-V2"
)
OFFLINE_PHYSICAL_RESOLVED_CATALOG_SCOPE_ATTESTATION_V2 = (
    "C3_PHYSICAL_RESOLVED_CATALOG_TEMPORARY_SYNTHETIC_ONLY_V2"
)
PHYSICAL_RESOLVED_CATALOG_VERSION_V2 = (
    "C3_PHYSICAL_RESOLVED_CATALOG_TEMPORARY_REFERENCE_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PROJECTED_RECORD_KEYS = frozenset(
    {
        "record_version",
        "obligation_sha256",
        "transaction_sha256",
        "resolution_receipt_sha256",
        "terminal_result_sha256",
        "resolved_at_epoch",
        "projection_committed",
        "state",
        "record_sha256",
    }
)
_SCAN_KEYS = frozenset(
    {
        "ok",
        "status",
        "reason",
        "root_identity_sha256",
        "storage_binding_sha256",
        "root_authority_attestation_sha256",
        "generation",
        "records",
        "record_count",
        "complete_scan_verified",
        "wal_integrity_verified",
        "filesystem_accessed",
        "interprocess_lock_acquired",
        "write_executed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "production_authority",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "no_order_sent",
        "synthetic_only",
    }
)
_CATALOG_KEYS = frozenset(
    {
        "catalog_version",
        "backend_instance_sha256",
        "backend_snapshot_sha256",
        "resolved_ledger_storage_binding_sha256",
        "root_authority_attestation_sha256",
        "lock_namespace_sha256",
        "backend_generation",
        "ledger_generation",
        "records",
        "record_count",
        "resolved_count",
        "complete_scan_verified",
        "wal_integrity_verified",
        "synthetic_only",
        "temporary_storage_only",
        "durable",
        "production_evidence",
        "filesystem_accessed",
        "catalog_sha256",
    }
)


class TemporaryPhysicalResolvedCatalogBlockedV2(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = backend_contract_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != field}
    )
    return value


def physical_resolved_catalog_valid_v2(
    value: Any, backend_snapshot: Mapping[str, Any]
) -> bool:
    if type(value) is not dict or set(value) != _CATALOG_KEYS:
        return False
    records = value.get("records")
    if type(records) is not list:
        return False
    hashes = []
    for record in records:
        if type(record) is not dict or set(record) != _PROJECTED_RECORD_KEYS:
            return False
        supplied = str(record.get("record_sha256") or "")
        if not (
            record.get("record_version")
            == "C3_DURABLE_RESOLVED_RECORD_PROJECTION_V2"
            and all(
                _valid_sha(record.get(key))
                for key in (
                    "obligation_sha256",
                    "transaction_sha256",
                    "resolution_receipt_sha256",
                    "terminal_result_sha256",
                    "record_sha256",
                )
            )
            and type(record.get("resolved_at_epoch")) is int
            and record.get("resolved_at_epoch") >= 0
            and record.get("projection_committed") is False
            and record.get("state") == "RESOLVED"
            and hmac.compare_digest(
                supplied,
                backend_contract_v2.stable_sha256_v2(
                    {
                        key: item
                        for key, item in record.items()
                        if key != "record_sha256"
                    }
                ),
            )
        ):
            return False
        hashes.append(supplied)
    supplied_catalog = str(value.get("catalog_sha256") or "")
    try:
        return bool(
            backend_contract_v2.backend_snapshot_valid_v2(backend_snapshot)
            and value["catalog_version"] == PHYSICAL_RESOLVED_CATALOG_VERSION_V2
            and value["backend_instance_sha256"]
            == backend_snapshot["backend_instance_sha256"]
            and value["backend_snapshot_sha256"]
            == backend_snapshot["snapshot_sha256"]
            and _valid_sha(value["resolved_ledger_storage_binding_sha256"])
            and _valid_sha(value["root_authority_attestation_sha256"])
            and value["lock_namespace_sha256"]
            == backend_snapshot["lock_namespace_sha256"]
            and value["backend_generation"] == backend_snapshot["generation"]
            and type(value["ledger_generation"]) is int
            and value["ledger_generation"] >= 0
            and hashes == sorted(hashes)
            and len(hashes) == len(set(hashes))
            and value["record_count"] == len(records)
            and value["resolved_count"] == len(records)
            and value["complete_scan_verified"] is True
            and value["wal_integrity_verified"] is True
            and value["synthetic_only"] is True
            and value["temporary_storage_only"] is True
            and value["durable"] is False
            and value["production_evidence"] is False
            and value["filesystem_accessed"] is True
            and _valid_sha(supplied_catalog)
            and hmac.compare_digest(
                supplied_catalog,
                backend_contract_v2.stable_sha256_v2(
                    {
                        key: item
                        for key, item in value.items()
                        if key != "catalog_sha256"
                    }
                ),
            )
        )
    except Exception:
        return False


def build_physical_resolved_catalog_from_scan_v2(
    *,
    scan: Any,
    backend_snapshot: Mapping[str, Any],
    expected_storage_binding_sha256: str,
) -> dict[str, Any]:
    if not (
        type(scan) is dict
        and set(scan) == _SCAN_KEYS
        and scan["ok"] is True
        and scan["reason"] is None
        and scan["storage_binding_sha256"]
        == expected_storage_binding_sha256
        and type(scan["records"]) is list
        and scan["record_count"] == len(scan["records"])
        and scan["complete_scan_verified"] is True
        and scan["wal_integrity_verified"] is True
        and scan["filesystem_accessed"] is True
        and scan["interprocess_lock_acquired"] is True
        and scan["write_executed"] is False
        and scan["real_registry_accessed"] is False
        and scan["network_accessed"] is False
        and scan["broker_called"] is False
        and scan["production_authority"] is False
        and scan["runtime_integrated"] is False
        and scan["activation_allowed"] is False
        and scan["live_allowed"] is False
        and scan["no_order_sent"] is True
        and scan["synthetic_only"] is True
    ):
        raise TemporaryPhysicalResolvedCatalogBlockedV2(
            "PHYSICAL_RESOLVED_LEDGER_SCAN_INVALID"
        )
    catalog = {
        "catalog_version": PHYSICAL_RESOLVED_CATALOG_VERSION_V2,
        "backend_instance_sha256": backend_snapshot[
            "backend_instance_sha256"
        ],
        "backend_snapshot_sha256": backend_snapshot["snapshot_sha256"],
        "resolved_ledger_storage_binding_sha256": scan[
            "storage_binding_sha256"
        ],
        "root_authority_attestation_sha256": scan[
            "root_authority_attestation_sha256"
        ],
        "lock_namespace_sha256": backend_snapshot["lock_namespace_sha256"],
        "backend_generation": backend_snapshot["generation"],
        "ledger_generation": scan["generation"],
        "records": copy.deepcopy(scan["records"]),
        "record_count": scan["record_count"],
        "resolved_count": scan["record_count"],
        "complete_scan_verified": True,
        "wal_integrity_verified": True,
        "synthetic_only": True,
        "temporary_storage_only": True,
        "durable": False,
        "production_evidence": False,
        "filesystem_accessed": True,
    }
    _seal(catalog, "catalog_sha256")
    if not physical_resolved_catalog_valid_v2(catalog, backend_snapshot):
        raise TemporaryPhysicalResolvedCatalogBlockedV2(
            "PHYSICAL_RESOLVED_CATALOG_SELF_VALIDATION_FAILED"
        )
    return catalog


@dataclass(frozen=True)
class TemporaryPhysicalResolvedCatalogPortConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_backend_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_ledger_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_storage_binding_sha256: str | None = field(
        default=None, repr=False
    )


class TemporaryPhysicalResolvedCatalogPortV2:
    def __init__(
        self,
        config: TemporaryPhysicalResolvedCatalogPortConfigV2 | None = None,
        *,
        backend: Any = None,
        durable_authority_ledger: Any = None,
    ) -> None:
        self._config = config or TemporaryPhysicalResolvedCatalogPortConfigV2()
        self._backend = backend
        self._durable_authority_ledger = durable_authority_ledger

    def _reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PHYSICAL_RESOLVED_CATALOG_PORT_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_RESOLVED_CATALOG_SCOPE_ATTESTATION_V2
        ):
            return "PHYSICAL_RESOLVED_CATALOG_SCOPE_INVALID"
        if not all(
            _valid_sha(item)
            for item in (
                self._config.expected_backend_object_identity_sha256,
                self._config.expected_ledger_object_identity_sha256,
                self._config.expected_storage_binding_sha256,
            )
        ):
            return "PHYSICAL_RESOLVED_CATALOG_PINS_INVALID"
        return None

    def _dependencies_valid(self, backend: Any) -> bool:
        if not (
            backend is self._backend
            and type(backend)
            is physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2
            and type(self._durable_authority_ledger)
            is durable_authority_v2.DormantDurableReconciliationAuthorityLedgerV2
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                ),
                str(self._config.expected_backend_object_identity_sha256),
            )
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    self._durable_authority_ledger
                ),
                str(self._config.expected_ledger_object_identity_sha256),
            )
        ):
            return False
        storage = vars(self._durable_authority_ledger).get("_storage")
        backend_root = Path(vars(backend).get("_root")).resolve(strict=False)
        if storage is None:
            return False
        paths = (
            Path(storage.snapshot_path),
            Path(storage.journal_path),
            Path(storage.lock_path),
            Path(storage.backup_dir),
        )
        try:
            inside_backend_root = all(
                path.resolve(strict=False).is_relative_to(backend_root)
                for path in paths
            )
        except Exception:
            return False
        return bool(
            inside_backend_root
            and hmac.compare_digest(
                durable_authority_v2.durable_authority_storage_binding_sha256_v2(
                    storage
                ),
                str(self._config.expected_storage_binding_sha256),
            )
        )

    def read_resolved_catalog_offline(
        self, *, backend: Any, backend_snapshot: Any
    ) -> Mapping[str, Any]:
        reason = self._reason()
        if reason is not None:
            raise TemporaryPhysicalResolvedCatalogBlockedV2(reason)
        if not self._dependencies_valid(backend):
            raise TemporaryPhysicalResolvedCatalogBlockedV2(
                "PHYSICAL_RESOLVED_CATALOG_DEPENDENCY_INVALID"
            )
        if not backend_contract_v2.backend_snapshot_valid_v2(backend_snapshot):
            raise TemporaryPhysicalResolvedCatalogBlockedV2(
                "PHYSICAL_RESOLVED_CATALOG_BACKEND_SNAPSHOT_INVALID"
            )
        try:
            current = backend.snapshot_offline()
        except Exception as exc:
            raise TemporaryPhysicalResolvedCatalogBlockedV2(
                "PHYSICAL_RESOLVED_CATALOG_BACKEND_READ_FAILED"
            ) from exc
        if current != backend_snapshot:
            raise TemporaryPhysicalResolvedCatalogBlockedV2(
                "PHYSICAL_RESOLVED_CATALOG_BACKEND_SNAPSHOT_STALE"
            )
        try:
            scan = self._durable_authority_ledger.list_resolved_records_offline()
        except Exception as exc:
            raise TemporaryPhysicalResolvedCatalogBlockedV2(
                "PHYSICAL_RESOLVED_LEDGER_SCAN_FAILED_CLOSED"
            ) from exc
        return build_physical_resolved_catalog_from_scan_v2(
            scan=scan,
            backend_snapshot=backend_snapshot,
            expected_storage_binding_sha256=str(
                self._config.expected_storage_binding_sha256
            ),
        )


__all__ = [
    "OFFLINE_PHYSICAL_RESOLVED_CATALOG_SCOPE_ATTESTATION_V2",
    "PHYSICAL_RESOLVED_CATALOG_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_RESOLVED_CATALOG_PORT_OFFLINE_V2_VERSION",
    "TemporaryPhysicalResolvedCatalogBlockedV2",
    "TemporaryPhysicalResolvedCatalogPortConfigV2",
    "TemporaryPhysicalResolvedCatalogPortV2",
    "build_physical_resolved_catalog_from_scan_v2",
    "physical_resolved_catalog_valid_v2",
]
