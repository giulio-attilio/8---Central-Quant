"""Fail-closed conformance adapter over the temporary physical backend V2."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as terminal_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2 as resolved_port_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2 as locked_collection_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2 as observation_lease_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as source_ports_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-SOURCE-PHYSICAL-CONFORMANCE-"
    "ADAPTER-OFFLINE-V2"
)
OFFLINE_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_SCOPE_ATTESTATION_V2 = (
    "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_TEMPORARY_ONLY_V2"
)
SYNTHETIC_PHYSICAL_OBSERVATION_AUTHORITY_VERSION_V2 = (
    "C3_SYNTHETIC_PHYSICAL_OBSERVATION_AUTHORITY_V2"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_KEYS = frozenset(
    {
        "authority_version",
        "backend_instance_sha256",
        "backend_snapshot_sha256",
        "registry_path_binding_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "resolved_ledger_storage_binding_sha256",
        "issued_at_epoch",
        "expires_at_epoch",
        "synthetic_only",
        "production_authority",
        "authority_sha256",
    }
)
_PORT_ROUTES = (
    {
        "required_port": "read_backend_snapshot_offline",
        "temporary_source": "locked_collection.read_backend_snapshot_offline",
        "availability": "AVAILABLE_READ_ONLY",
    },
    {
        "required_port": "read_transaction_log_audit_offline",
        "temporary_source": "locked_collection.read_transaction_log_audit_offline",
        "availability": "AVAILABLE_READ_ONLY",
    },
    {
        "required_port": "read_prepared_catalog_offline",
        "temporary_source": "locked_collection.read_prepared_catalog_offline",
        "availability": "AVAILABLE_READ_ONLY",
    },
    {
        "required_port": "read_resolved_catalog_offline",
        "temporary_source": "locked_collection.read_resolved_scan_then_build_catalog",
        "availability": "AVAILABLE_READ_ONLY",
    },
    {
        "required_port": "read_backend_capability_probe_offline",
        "temporary_source": "capability_evidence_offline",
        "availability": "AVAILABLE_READ_ONLY",
    },
    {
        "required_port": "normalize_terminal_receipt_offline",
        "temporary_source": "normalize_recovery_offline",
        "availability": "AVAILABLE_BINDING_ONLY_NOT_CALLED",
    },
)
_PRODUCTION_BLOCKERS = (
    "TEMPORARY_PHYSICAL_BACKEND_IS_SYNTHETIC_AND_NON_DURABLE",
    "RESOLVED_LEDGER_IS_TEMPORARY_SYNTHETIC_AND_NON_DURABLE",
    "TERMINAL_NORMALIZER_IS_BOUND_BUT_HAS_NO_RESULT_TO_NORMALIZE",
    "OBSERVATION_AUTHORITY_IS_SYNTHETIC_AND_PROCESS_LOCAL",
    "AUTHENTICATED_PRODUCTION_AUTHORITY_HAS_NOT_BEEN_REVALIDATED",
    "PRODUCTION_MAINTENANCE_LEASE_HAS_NOT_BEEN_ACQUIRED",
    "PRODUCTION_EVIDENCE_BUNDLE_CANNOT_BE_CREATED",
    "RUNTIME_RECOVERY_READINESS_ACTIVATION_AND_LIVE_REMAIN_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def physical_observation_authority_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("physical observation authority must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "authority_sha256"}
    )


def build_synthetic_physical_observation_authority_v2(
    *,
    snapshot: Mapping[str, Any],
    maintenance_epoch: str,
    maintenance_lease_receipt_sha256: str,
    resolved_ledger_storage_binding_sha256: str,
    issued_at_epoch: int,
    expires_at_epoch: int,
) -> dict[str, Any]:
    authority = {
        "authority_version": SYNTHETIC_PHYSICAL_OBSERVATION_AUTHORITY_VERSION_V2,
        "backend_instance_sha256": snapshot["backend_instance_sha256"],
        "backend_snapshot_sha256": snapshot["snapshot_sha256"],
        "registry_path_binding_sha256": snapshot[
            "registry_path_binding_sha256"
        ],
        "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
        "maintenance_epoch": maintenance_epoch,
        "maintenance_lease_receipt_sha256": maintenance_lease_receipt_sha256,
        "resolved_ledger_storage_binding_sha256": (
            resolved_ledger_storage_binding_sha256
        ),
        "issued_at_epoch": issued_at_epoch,
        "expires_at_epoch": expires_at_epoch,
        "synthetic_only": True,
        "production_authority": False,
    }
    authority["authority_sha256"] = physical_observation_authority_sha256_v2(
        authority
    )
    return authority


def synthetic_physical_observation_authority_valid_v2(
    value: Any, *, now_epoch: int
) -> bool:
    if type(value) is not dict or set(value) != _AUTHORITY_KEYS:
        return False
    try:
        return bool(
            value["authority_version"]
            == SYNTHETIC_PHYSICAL_OBSERVATION_AUTHORITY_VERSION_V2
            and all(
                _valid_sha256(value[field_name])
                for field_name in (
                    "backend_instance_sha256",
                    "backend_snapshot_sha256",
                    "registry_path_binding_sha256",
                    "lock_namespace_sha256",
                    "maintenance_epoch",
                    "maintenance_lease_receipt_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "authority_sha256",
                )
            )
            and type(value["issued_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and type(now_epoch) is int
            and value["issued_at_epoch"] <= now_epoch < value["expires_at_epoch"]
            and 1 <= value["expires_at_epoch"] - now_epoch <= 300
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and hmac.compare_digest(
                value["authority_sha256"],
                physical_observation_authority_sha256_v2(value),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class OfflineEvidenceSourcePhysicalConformanceAdapterConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_backend_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_terminal_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_catalog_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_observation_lease_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_locked_collection_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_observation_authority_sha256: str | None = field(
        default=None, repr=False
    )


class OfflineEvidenceSourcePhysicalConformanceAdapterV2:
    def __init__(
        self,
        *,
        clock: Callable[[], int] | None = None,
        config: OfflineEvidenceSourcePhysicalConformanceAdapterConfigV2
        | None = None,
    ) -> None:
        self._clock = clock or (lambda: 0)
        self._config = config or OfflineEvidenceSourcePhysicalConformanceAdapterConfigV2()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_V2_VERSION,
            "offline_only": True,
            "temporary_storage_only": True,
            "synthetic_only": True,
            "dependencies_verified": False,
            "observation_authority_verified": False,
            "authority_revalidation_count": 0,
            "lease_revalidation_count": 0,
            "locked_collection_receipt_verified": False,
            "required_port_count": 6,
            "available_port_count": 0,
            "validated_read_port_count": 0,
            "port_routes": [dict(item) for item in _PORT_ROUTES],
            "snapshot_verified": False,
            "transaction_log_audit_verified": False,
            "prepared_catalog_verified": False,
            "resolved_catalog_verified": False,
            "resolved_state_supported": False,
            "capability_probe_verified": False,
            "terminal_normalizer_bound": False,
            "terminal_normalizer_called": False,
            "aggregate_audit_verified": False,
            "stable_observation_window_verified": False,
            "optimistic_atomic_observation_verified": False,
            "shared_lock_atomicity_verified": False,
            "partial_conformance_verified": False,
            "complete_conformance_verified": False,
            "evidence_bundle_created": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "durability_verified": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "reasons": [],
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PHYSICAL_EVIDENCE_CONFORMANCE_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_SCOPE_ATTESTATION_V2
        ):
            return "PHYSICAL_EVIDENCE_CONFORMANCE_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                self._config.expected_backend_object_identity_sha256,
                self._config.expected_terminal_port_object_identity_sha256,
                self._config.expected_resolved_catalog_port_object_identity_sha256,
                self._config.expected_observation_lease_object_identity_sha256,
                self._config.expected_locked_collection_object_identity_sha256,
                self._config.expected_observation_authority_sha256,
            )
        ):
            return "PHYSICAL_EVIDENCE_CONFORMANCE_PINS_INVALID"
        return None

    def assess_offline(
        self,
        *,
        backend: Any,
        terminal_evidence_port: Any,
        resolved_catalog_port: Any,
        observation_lease: Any,
        locked_aggregate_collection: Any,
        observation_authority: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not (
            type(backend) is physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2
            and type(terminal_evidence_port) is terminal_v2.PhysicalTerminalEvidencePortV2
            and type(resolved_catalog_port)
            is resolved_port_v2.TemporaryPhysicalResolvedCatalogPortV2
            and type(observation_lease)
            is observation_lease_v2.PhysicalMultiStoreObservationLeaseV2
            and type(locked_aggregate_collection)
            is locked_collection_v2.PhysicalLockedAggregateCollectionV2
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    backend
                ),
                str(self._config.expected_backend_object_identity_sha256),
            )
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    terminal_evidence_port
                ),
                str(self._config.expected_terminal_port_object_identity_sha256),
            )
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    resolved_catalog_port
                ),
                str(
                    self._config.expected_resolved_catalog_port_object_identity_sha256
                ),
            )
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    observation_lease
                ),
                str(self._config.expected_observation_lease_object_identity_sha256),
            )
            and hmac.compare_digest(
                source_ports_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                    locked_aggregate_collection
                ),
                str(self._config.expected_locked_collection_object_identity_sha256),
            )
            and vars(locked_aggregate_collection).get("_lease")
            is observation_lease
            and vars(locked_aggregate_collection).get("_backend") is backend
            and vars(locked_aggregate_collection).get("_ledger")
            is vars(resolved_catalog_port).get("_durable_authority_ledger")
        ):
            result["reasons"].append("TEMPORARY_PHYSICAL_DEPENDENCY_INVALID")
            return result
        result["dependencies_verified"] = True

        def revalidate() -> bool:
            try:
                valid = bool(
                    synthetic_physical_observation_authority_valid_v2(
                        observation_authority, now_epoch=int(self._clock())
                    )
                    and hmac.compare_digest(
                        observation_authority["authority_sha256"],
                        str(self._config.expected_observation_authority_sha256),
                    )
                )
            except Exception:
                return False
            if valid:
                result["authority_revalidation_count"] += 1
            return valid

        if not revalidate():
            result["reasons"].append("PHYSICAL_OBSERVATION_AUTHORITY_INVALID")
            return result
        result["observation_authority_verified"] = True
        try:
            locked_result = locked_aggregate_collection.collect_offline()
            result["filesystem_accessed"] = bool(
                locked_result.get("filesystem_accessed") is True
            )
            receipt = locked_result.get("collection_receipt")
            snapshot = locked_result.get("backend_snapshot")
            aggregate = locked_result.get("aggregate_audit")
            if not (
                locked_result.get("ok") is True
                and type(snapshot) is dict
                and backend_v2.backend_snapshot_valid_v2(snapshot)
                and snapshot["backend_instance_sha256"]
                == observation_authority["backend_instance_sha256"]
                and snapshot["snapshot_sha256"]
                == observation_authority["backend_snapshot_sha256"]
                and snapshot["registry_path_binding_sha256"]
                == observation_authority["registry_path_binding_sha256"]
                and snapshot["lock_namespace_sha256"]
                == observation_authority["lock_namespace_sha256"]
                and locked_collection_v2.physical_locked_aggregate_collection_receipt_valid_v2(
                    receipt
                )
                and receipt["aggregate_audit_sha256"]
                == aggregate["aggregate_audit_sha256"]
                and receipt["resolved_ledger_storage_binding_sha256"]
                == observation_authority[
                    "resolved_ledger_storage_binding_sha256"
                ]
                and locked_result["lease_revalidation_count"] == 8
                and locked_result["shared_lock_atomicity_verified"] is True
                and locked_result["stable_observation_window_verified"] is True
                and locked_result["catalog_crosscheck_verified"] is True
                and locked_result["lease_released_after_collection"] is True
            ):
                raise ValueError(
                    str(
                        locked_result.get("reason")
                        or "PHYSICAL_LOCKED_AGGREGATE_COLLECTION_INVALID"
                    )
                )
            result["snapshot_verified"] = True
            result["transaction_log_audit_verified"] = True
            result["prepared_catalog_verified"] = True
            result["resolved_catalog_verified"] = True
            result["resolved_state_supported"] = True
            result["validated_read_port_count"] = 4
            result["lease_revalidation_count"] = 8
            result["locked_collection_receipt_verified"] = True
            result["aggregate_audit_verified"] = True
            result["stable_observation_window_verified"] = True
            result["optimistic_atomic_observation_verified"] = True
            result["shared_lock_atomicity_verified"] = True

            if not revalidate():
                raise ValueError("PHYSICAL_OBSERVATION_AUTHORITY_STALE")
            capability_evidence = [
                dict(item) for item in backend.capability_evidence_offline()
            ]
            if not (
                len(capability_evidence) == len(backend_v2.REQUIRED_CAPABILITIES_V2)
                and sorted(item["capability"] for item in capability_evidence)
                == sorted(backend_v2.REQUIRED_CAPABILITIES_V2)
                and all(
                    backend_v2.capability_evidence_valid_v2(item, snapshot)
                    for item in capability_evidence
                )
            ):
                raise ValueError("PHYSICAL_CAPABILITY_EVIDENCE_INVALID")
            result["capability_probe_verified"] = True
            result["validated_read_port_count"] = 5
            if not revalidate():
                raise ValueError("PHYSICAL_OBSERVATION_AUTHORITY_STALE")
        except Exception as exc:
            reason = str(exc)
            if not re.fullmatch(r"[A-Z0-9_]{1,160}", reason):
                reason = "PHYSICAL_EVIDENCE_COLLECTION_FAILED_CLOSED"
            result["reasons"].append(reason)
            return result
        terminal_config = vars(terminal_evidence_port).get("_config")
        terminal_bound = bool(
            terminal_config is not None
            and vars(terminal_config).get("enabled") is True
            and vars(terminal_config).get("scope_attestation")
            == terminal_v2.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2
            and callable(
                getattr(type(terminal_evidence_port), "normalize_recovery_offline", None)
            )
        )
        if not terminal_bound:
            result["reasons"].append("PHYSICAL_TERMINAL_NORMALIZER_NOT_BOUND")
            return result
        result["terminal_normalizer_bound"] = True
        result["available_port_count"] = 6
        result["partial_conformance_verified"] = bool(
            result["validated_read_port_count"] == 5
            and result["terminal_normalizer_bound"] is True
            and result["authority_revalidation_count"] == 3
            and result["lease_revalidation_count"] == 8
            and result["locked_collection_receipt_verified"] is True
            and result["aggregate_audit_verified"] is True
            and result["stable_observation_window_verified"] is True
            and result["optimistic_atomic_observation_verified"] is True
            and result["shared_lock_atomicity_verified"] is True
        )
        result["complete_conformance_verified"] = result[
            "partial_conformance_verified"
        ]
        result["ok"] = result["complete_conformance_verified"]
        result["status"] = (
            "C3_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_TEMPORARY_COMPLETE"
        )
        return result


__all__ = [
    "OFFLINE_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_SCOPE_ATTESTATION_V2",
    "OfflineEvidenceSourcePhysicalConformanceAdapterConfigV2",
    "OfflineEvidenceSourcePhysicalConformanceAdapterV2",
    "SYNTHETIC_PHYSICAL_OBSERVATION_AUTHORITY_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_SOURCE_PHYSICAL_CONFORMANCE_ADAPTER_OFFLINE_V2_VERSION",
    "build_synthetic_physical_observation_authority_v2",
    "physical_observation_authority_sha256_v2",
    "synthetic_physical_observation_authority_valid_v2",
]
