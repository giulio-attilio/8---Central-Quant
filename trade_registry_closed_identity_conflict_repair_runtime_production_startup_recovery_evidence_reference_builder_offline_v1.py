"""Reference builder for synthetic startup-recovery evidence, memory only."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_contract_v1 as scope_conformance_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-REFERENCE-BUILDER-OFFLINE-V1"
)
OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_MEMORY_ONLY_V1"
)
SYNTHETIC_CAPABILITY_PROBE_VERSION_V1 = (
    "C3_SYNTHETIC_STARTUP_RECOVERY_CAPABILITY_PROBE_V1"
)
SYNTHETIC_RAW_TERMINAL_RECEIPT_VERSION_V1 = (
    "C3_SYNTHETIC_RAW_TERMINAL_RECEIPT_REFERENCE_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RAW_RECEIPT_KEYS = frozenset(
    {
        "raw_version",
        "transaction_sha256",
        "source_state",
        "synthetic_only",
        "raw_receipt_sha256",
    }
)
_PROBE_KEYS = frozenset(
    {
        "probe_version",
        "schema_sha256",
        "backend_instance_sha256",
        "backend_snapshot_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "authenticated_authority_receipt_sha256",
        "writers_blocked_entire_window",
        "fsync_capability_verified",
        "durable",
        "production_evidence",
        "synthetic_only",
        "probe_receipt_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "REFERENCE_BUILDER_OUTPUT_IS_SYNTHETIC_AND_NON_DURABLE",
    "PRODUCTION_READ_PORTS_NOT_IMPLEMENTED",
    "PRODUCTION_TERMINAL_RECEIPT_NORMALIZER_NOT_IMPLEMENTED",
    "AUTHENTICATED_PRODUCTION_AUTHORITY_NOT_VERIFIED",
    "LIVE_LEASE_NOT_REVALIDATED_AT_EXECUTION_BOUNDARY",
    "DURABLE_AUTHORITY_CURRENT_STATE_NOT_REVALIDATED",
    "EMPIRICAL_FSYNC_DURABILITY_NOT_VERIFIED",
    "RUNTIME_INTEGRATION_RECOVERY_READINESS_AND_LIVE_REMAIN_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def synthetic_raw_terminal_receipt_sha256_v1(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("raw terminal receipt must be a mapping")
    return _stable_sha256(
        {
            key: item
            for key, item in value.items()
            if key != "raw_receipt_sha256"
        }
    )


def synthetic_capability_probe_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("capability probe must be a mapping")
    return _stable_sha256(
        {
            key: item
            for key, item in value.items()
            if key != "probe_receipt_sha256"
        }
    )


def _raw_receipt_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _RAW_RECEIPT_KEYS:
        return False
    try:
        return bool(
            value["raw_version"] == SYNTHETIC_RAW_TERMINAL_RECEIPT_VERSION_V1
            and _valid_sha256(value["transaction_sha256"])
            and value["source_state"] in {"PREPARED", "RESOLVED"}
            and value["synthetic_only"] is True
            and _valid_sha256(value["raw_receipt_sha256"])
            and hmac.compare_digest(
                value["raw_receipt_sha256"],
                synthetic_raw_terminal_receipt_sha256_v1(value),
            )
        )
    except Exception:
        return False


def _probe_valid(value: Any, scope: Mapping[str, Any]) -> bool:
    if type(value) is not dict or set(value) != _PROBE_KEYS:
        return False
    try:
        return bool(
            value["probe_version"] == SYNTHETIC_CAPABILITY_PROBE_VERSION_V1
            and value["schema_sha256"] == scope["schema_sha256"]
            and value["backend_instance_sha256"]
            == scope["backend_instance_sha256"]
            and _valid_sha256(value["backend_snapshot_sha256"])
            and value["maintenance_epoch"] == scope["maintenance_epoch"]
            and value["maintenance_lease_receipt_sha256"]
            == scope["maintenance_lease_receipt_sha256"]
            and value["authenticated_authority_receipt_sha256"]
            == scope["authenticated_authority_receipt_sha256"]
            and value["writers_blocked_entire_window"] is True
            and value["fsync_capability_verified"] is False
            and value["durable"] is False
            and value["production_evidence"] is False
            and value["synthetic_only"] is True
            and _valid_sha256(value["probe_receipt_sha256"])
            and hmac.compare_digest(
                value["probe_receipt_sha256"],
                synthetic_capability_probe_receipt_sha256_v1(value),
            )
        )
    except Exception:
        return False


class InMemorySyntheticEvidenceReadPortV1:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(self, *, artifacts: Mapping[str, Any], capability_probe: Any) -> None:
        required = {
            "initial_backend_snapshot",
            "initial_transaction_log_audit",
            "initial_prepared_catalog",
            "initial_resolved_catalog",
            "final_backend_snapshot",
            "final_transaction_log_audit",
            "final_prepared_catalog",
            "final_resolved_catalog",
        }
        if type(artifacts) is not dict or set(artifacts) != required:
            raise ValueError("exact in-memory artifact set required")
        self._artifacts = _canonical_copy(artifacts)
        self._capability_probe = _canonical_copy(capability_probe)
        self._counts = {
            "snapshot": 0,
            "audit": 0,
            "prepared": 0,
            "resolved": 0,
            "probe": 0,
        }

    @staticmethod
    def _phase(value: Any) -> str:
        phase = str(value or "").upper()
        if phase not in {"INITIAL", "FINAL"}:
            raise ValueError("phase must be INITIAL or FINAL")
        return phase.lower()

    def read_backend_snapshot_offline(self, *, phase: str) -> Mapping[str, Any]:
        self._counts["snapshot"] += 1
        key = f"{self._phase(phase)}_backend_snapshot"
        return _canonical_copy(self._artifacts[key])

    def read_transaction_log_audit_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        self._counts["audit"] += 1
        key = f"{self._phase(phase)}_transaction_log_audit"
        value = self._artifacts[key]
        if value.get("backend_snapshot_sha256") != snapshot.get("snapshot_sha256"):
            raise ValueError("audit snapshot binding mismatch")
        return _canonical_copy(value)

    def read_prepared_catalog_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        self._counts["prepared"] += 1
        key = f"{self._phase(phase)}_prepared_catalog"
        value = self._artifacts[key]
        if value.get("backend_snapshot_sha256") != snapshot.get("snapshot_sha256"):
            raise ValueError("prepared catalog snapshot binding mismatch")
        return _canonical_copy(value)

    def read_resolved_catalog_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        self._counts["resolved"] += 1
        key = f"{self._phase(phase)}_resolved_catalog"
        value = self._artifacts[key]
        if value.get("backend_snapshot_sha256") != snapshot.get("snapshot_sha256"):
            raise ValueError("resolved catalog snapshot binding mismatch")
        return _canonical_copy(value)

    def read_backend_capability_probe_offline(
        self, *, snapshot: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self._counts["probe"] += 1
        if self._capability_probe.get("backend_snapshot_sha256") != snapshot.get(
            "snapshot_sha256"
        ):
            raise ValueError("capability probe snapshot binding mismatch")
        return _canonical_copy(self._capability_probe)

    def counters(self) -> dict[str, int]:
        return dict(self._counts)

    def __repr__(self) -> str:
        return "InMemorySyntheticEvidenceReadPortV1(<protected>)"


class InMemorySyntheticTerminalReceiptNormalizerV1:
    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(self, *, terminal_receipts: Sequence[Mapping[str, Any]]) -> None:
        receipts = [_canonical_copy(item) for item in terminal_receipts]
        transactions = [item.get("transaction_sha256") for item in receipts]
        if (
            not receipts
            or any(not _valid_sha256(item) for item in transactions)
            or len(transactions) != len(set(transactions))
        ):
            raise ValueError("unique synthetic terminal receipts required")
        self._receipts = dict(zip(transactions, receipts, strict=True))
        self._call_count = 0

    def normalize_terminal_receipt_offline(
        self,
        *,
        raw_receipt: Mapping[str, Any],
        protected_scope_binding: Any,
    ) -> Mapping[str, Any]:
        self._call_count += 1
        if not (
            _raw_receipt_valid(raw_receipt)
            and ports_v1.scope_binding_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                protected_scope_binding
            )
        ):
            raise ValueError("synthetic raw terminal receipt invalid")
        receipt = self._receipts.get(raw_receipt["transaction_sha256"])
        if not (
            receipt
            and receipt.get("source_state") == raw_receipt["source_state"]
        ):
            raise ValueError("terminal receipt scope mismatch")
        return _canonical_copy(receipt)

    @property
    def call_count(self) -> int:
        return self._call_count

    def __repr__(self) -> str:
        return "InMemorySyntheticTerminalReceiptNormalizerV1(<protected>)"


@dataclass(frozen=True)
class OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_port_binding_sha256: str | None = field(default=None, repr=False)
    max_pending_items: int = 100

    def __post_init__(self) -> None:
        if not 1 <= self.max_pending_items <= 10_000:
            raise ValueError("max_pending_items must be between 1 and 10000")


class OfflineStartupRecoveryEvidenceReferenceBuilderV1:
    def __init__(
        self,
        *,
        config: OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1 | None = None,
    ) -> None:
        self._config = config or OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1()

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILD_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_V1_VERSION,
            "offline_only": True,
            "memory_only": True,
            "synthetic_only": True,
            "port_binding_verified": False,
            "raw_receipts_verified": False,
            "initial_evidence_collected": False,
            "terminal_receipts_normalized": False,
            "final_evidence_collected": False,
            "synthetic_bundle_created": False,
            "scope_aware_conformance_verified": False,
            "ports_called": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "production_evidence": False,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "reasons": [],
            "fixture_bundle": None,
            "protected_conformance": None,
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "EVIDENCE_REFERENCE_BUILDER_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1
        ):
            return "EVIDENCE_REFERENCE_BUILDER_SCOPE_INVALID"
        if not _valid_sha256(self._config.expected_port_binding_sha256):
            return "EVIDENCE_REFERENCE_BUILDER_PORT_PIN_INVALID"
        return None

    def build_offline(
        self,
        *,
        protected_port_binding: Any,
        raw_terminal_receipts: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not (
            ports_v1.protected_startup_recovery_evidence_builder_port_binding_valid_v1(
                protected_port_binding
            )
            and hmac.compare_digest(
                protected_port_binding.binding_sha256,
                str(self._config.expected_port_binding_sha256),
            )
            and type(protected_port_binding.evidence_read_port)
            is InMemorySyntheticEvidenceReadPortV1
            and type(protected_port_binding.terminal_normalizer_port)
            is InMemorySyntheticTerminalReceiptNormalizerV1
        ):
            result["reasons"].append("PROTECTED_REFERENCE_PORT_BINDING_INVALID")
            return result
        result["port_binding_verified"] = True
        scope_protected = protected_port_binding.protected_scope_binding
        scope = protected_port_binding.binding
        if not (
            isinstance(raw_terminal_receipts, (list, tuple))
            and 1 <= len(raw_terminal_receipts) <= self._config.max_pending_items
            and len(raw_terminal_receipts) == scope_protected.binding["pending_item_count"]
            and all(_raw_receipt_valid(item) for item in raw_terminal_receipts)
        ):
            result["reasons"].append("RAW_TERMINAL_RECEIPT_SET_INVALID")
            return result
        raw_by_transaction = {
            item["transaction_sha256"]: item for item in raw_terminal_receipts
        }
        expected_sources = {
            item["transaction_sha256"]: item["source_state"]
            for item in scope_protected.binding["pending_items"]
        }
        if not (
            len(raw_by_transaction) == len(raw_terminal_receipts)
            and {
                transaction: item["source_state"]
                for transaction, item in raw_by_transaction.items()
            }
            == expected_sources
        ):
            result["reasons"].append("RAW_TERMINAL_RECEIPT_SCOPE_MISMATCH")
            return result
        result["raw_receipts_verified"] = True
        read_port = protected_port_binding.evidence_read_port
        normalizer = protected_port_binding.terminal_normalizer_port
        try:
            result["ports_called"] = True
            initial_snapshot = read_port.read_backend_snapshot_offline(
                phase="INITIAL"
            )
            capability_probe = read_port.read_backend_capability_probe_offline(
                snapshot=initial_snapshot
            )
            initial_audit = read_port.read_transaction_log_audit_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            initial_prepared = read_port.read_prepared_catalog_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            initial_resolved = read_port.read_resolved_catalog_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            if not _probe_valid(capability_probe, scope):
                raise ValueError("synthetic capability probe invalid")
            result["initial_evidence_collected"] = True
            terminal_receipts = [
                normalizer.normalize_terminal_receipt_offline(
                    raw_receipt=raw_by_transaction[transaction_sha256],
                    protected_scope_binding=scope_protected,
                )
                for transaction_sha256 in sorted(raw_by_transaction)
            ]
            terminal_receipts.sort(key=lambda item: item["receipt_sha256"])
            result["terminal_receipts_normalized"] = True
            final_snapshot = read_port.read_backend_snapshot_offline(phase="FINAL")
            final_audit = read_port.read_transaction_log_audit_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            final_prepared = read_port.read_prepared_catalog_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            final_resolved = read_port.read_resolved_catalog_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            result["final_evidence_collected"] = True
        except Exception:
            result["reasons"].append("REFERENCE_PORT_COLLECTION_FAILED_CLOSED")
            return result
        completion = {
            "evidence_version": scope_protected.binding["future_evidence_version"],
            "schema_sha256": scope["schema_sha256"],
            "provider_binding_sha256": scope["provider_binding_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "registry_path_binding_sha256": scope[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": scope["wal_storage_binding_sha256"],
            "resolved_ledger_storage_binding_sha256": scope[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": scope["lock_namespace_sha256"],
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "maintenance_lease_receipt_sha256"
            ],
            "initial_backend_snapshot_sha256": initial_snapshot["snapshot_sha256"],
            "initial_transaction_log_audit_sha256": initial_audit["audit_sha256"],
            "initial_prepared_catalog_sha256": initial_prepared["catalog_sha256"],
            "initial_resolved_catalog_sha256": initial_resolved["catalog_sha256"],
            "final_backend_snapshot_sha256": final_snapshot["snapshot_sha256"],
            "final_transaction_log_audit_sha256": final_audit["audit_sha256"],
            "final_prepared_catalog_sha256": final_prepared["catalog_sha256"],
            "final_resolved_catalog_sha256": final_resolved["catalog_sha256"],
            "terminal_receipt_set_sha256": conformance_v1.synthetic_terminal_receipt_set_sha256_v1(
                terminal_receipts
            ),
            "prepared_transactions_before": initial_prepared["prepared_count"],
            "resolved_transactions_before": initial_resolved["resolved_count"],
            "prepared_transactions_after": final_prepared["prepared_count"],
            "resolved_transactions_after": final_resolved["resolved_count"],
            "unresolved_transactions_after": final_prepared["prepared_count"]
            + final_resolved["resolved_count"],
            "writers_blocked_entire_window": capability_probe[
                "writers_blocked_entire_window"
            ],
            "same_maintenance_epoch_used": True,
            "fresh_maintenance_epoch_verified": True,
            "all_catalogs_drained": final_prepared["prepared_count"] == 0
            and final_resolved["resolved_count"] == 0,
            "wal_integrity_verified": initial_audit["wal_integrity_verified"]
            and final_audit["wal_integrity_verified"],
            "durability_verified": False,
            "authenticated_authority_verified": False,
            "write_state_known": all(
                item["write_state_known"] is True for item in terminal_receipts
            ),
            "write_executed": any(
                item["write_executed"] is True for item in terminal_receipts
            ),
            "registry_write": any(
                item["registry_write"] is True for item in terminal_receipts
            ),
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "production_evidence": False,
            "runtime_admissible": False,
        }
        completion["startup_recovery_attestation_sha256"] = (
            conformance_v1.synthetic_completion_attestation_sha256_v1(completion)
        )
        bundle = {
            "bundle_version": conformance_v1.SYNTHETIC_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_BUNDLE_VERSION_V1,
            "schema_sha256": scope["schema_sha256"],
            "initial_backend_snapshot": _canonical_copy(initial_snapshot),
            "initial_transaction_log_audit": _canonical_copy(initial_audit),
            "initial_prepared_catalog": _canonical_copy(initial_prepared),
            "initial_resolved_catalog": _canonical_copy(initial_resolved),
            "final_backend_snapshot": _canonical_copy(final_snapshot),
            "final_transaction_log_audit": _canonical_copy(final_audit),
            "final_prepared_catalog": _canonical_copy(final_prepared),
            "final_resolved_catalog": _canonical_copy(final_resolved),
            "terminal_receipts": _canonical_copy(terminal_receipts),
            "completion_attestation": _canonical_copy(completion),
            "synthetic_fixture_only": True,
            "durable": False,
            "production_evidence": False,
            "production_authority": False,
            "runtime_admissible": False,
        }
        bundle["bundle_sha256"] = conformance_v1.synthetic_evidence_bundle_sha256_v1(
            bundle
        )
        adapter = scope_conformance_v1.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterV1(
            config=scope_conformance_v1.DormantStartupRecoveryScopeAwareEvidenceConformanceAdapterConfigV1(
                enabled=True,
                scope_attestation=(
                    scope_conformance_v1.OFFLINE_STARTUP_RECOVERY_SCOPE_AWARE_EVIDENCE_CONFORMANCE_ADAPTER_ATTESTATION_V1
                ),
                expected_scope_binding_sha256=scope_protected.binding_sha256,
                expected_bundle_sha256=bundle["bundle_sha256"],
            )
        )
        validator = conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceV1(
            config=conformance_v1.OfflineProductionStartupRecoveryEvidenceConformanceConfigV1(
                enabled=True,
                scope_attestation=(
                    conformance_v1.OFFLINE_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_CONFORMANCE_SCOPE_ATTESTATION_V1
                ),
                expected_schema_sha256=scope_protected.protected_evidence_schema.schema_sha256,
            )
        )
        conformance_result = adapter.audit_offline(
            protected_scope_binding=scope_protected,
            fixture_bundle=bundle,
            conformance_validator=validator,
        )
        protected_conformance = conformance_result.get("protected_conformance")
        if not (
            conformance_result.get("ok") is True
            and scope_conformance_v1.protected_startup_recovery_scope_aware_evidence_conformance_valid_v1(
                protected_conformance
            )
        ):
            result["reasons"].append("SCOPE_AWARE_CONFORMANCE_FAILED_CLOSED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUNDLE_BUILT_SYNTHETIC_ONLY",
            synthetic_bundle_created=True,
            scope_aware_conformance_verified=True,
            fixture_bundle=_canonical_copy(bundle),
            protected_conformance=protected_conformance,
        )
        return result


__all__ = [
    "InMemorySyntheticEvidenceReadPortV1",
    "InMemorySyntheticTerminalReceiptNormalizerV1",
    "OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1",
    "OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1",
    "OfflineStartupRecoveryEvidenceReferenceBuilderV1",
    "SYNTHETIC_CAPABILITY_PROBE_VERSION_V1",
    "SYNTHETIC_RAW_TERMINAL_RECEIPT_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_OFFLINE_V1_VERSION",
    "synthetic_capability_probe_receipt_sha256_v1",
    "synthetic_raw_terminal_receipt_sha256_v1",
]
