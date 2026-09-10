"""Default-off reference adapter for synthetic evidence read ports.

This module exercises only the five read operations over the exact injected
in-memory source.  It neither imports nor binds a production provider/backend.
"""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1 as plan_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as reference_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-EVIDENCE-READ-PORT-REFERENCE-ADAPTER-"
    "OFFLINE-V1"
)
OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_MEMORY_ONLY_V1"
)

_SEQUENCE = (
    "INITIAL_BACKEND_SNAPSHOT",
    "INITIAL_BACKEND_CAPABILITY_PROBE",
    "INITIAL_TRANSACTION_LOG_AUDIT",
    "INITIAL_PREPARED_CATALOG",
    "INITIAL_RESOLVED_CATALOG",
    "FINAL_BACKEND_SNAPSHOT",
    "FINAL_TRANSACTION_LOG_AUDIT",
    "FINAL_PREPARED_CATALOG",
    "FINAL_RESOLVED_CATALOG",
)


class StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(RuntimeError):
    """Raised before or immediately after an invalid synthetic read."""


@dataclass(frozen=True)
class OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_plan_sha256: str | None = field(default=None, repr=False)
    expected_source_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1:
    """Sequence-checked reference implementation backed only by memory."""

    offline_only = True
    synthetic_only = True
    filesystem_access_allowed = False
    network_access_allowed = False
    production_access_allowed = False
    write_allowed = False

    def __init__(
        self,
        *,
        protected_adapter_plan: Any,
        source_read_port: Any,
        config: OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1
        | None = None,
    ) -> None:
        self._protected_adapter_plan = protected_adapter_plan
        self._source_read_port = source_read_port
        self._config = (
            config
            or OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1()
        )
        self._step = 0
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._counts = {
            "snapshot": 0,
            "audit": 0,
            "prepared": 0,
            "resolved": 0,
            "probe": 0,
        }

    def _blocked(self, reason: str) -> None:
        raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(reason)

    def _require_ready(self) -> None:
        if self._config.enabled is not True:
            self._blocked("EVIDENCE_READ_PORT_REFERENCE_ADAPTER_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1
        ):
            self._blocked("EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_INVALID")
        protected = self._protected_adapter_plan
        source = self._source_read_port
        if not plan_v1.protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
            protected
        ):
            self._blocked("PROTECTED_EVIDENCE_READ_PORT_ADAPTER_PLAN_INVALID")
        expected_plan_sha = str(
            self._config.expected_adapter_plan_sha256 or ""
        )
        if not hmac.compare_digest(protected.plan_sha256, expected_plan_sha):
            self._blocked("EVIDENCE_READ_PORT_ADAPTER_PLAN_PIN_MISMATCH")
        if type(source) is not reference_v1.InMemorySyntheticEvidenceReadPortV1:
            self._blocked("EXACT_IN_MEMORY_SYNTHETIC_READ_PORT_REQUIRED")
        source_identity = (
            ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                source
            )
        )
        if not hmac.compare_digest(
            source_identity,
            str(self._config.expected_source_object_identity_sha256 or ""),
        ):
            self._blocked("EVIDENCE_READ_PORT_SOURCE_INSTANCE_PIN_MISMATCH")

    def _require_step(self, step: str) -> None:
        self._require_ready()
        if self._step >= len(_SEQUENCE) or _SEQUENCE[self._step] != step:
            self._blocked("EVIDENCE_READ_PORT_SEQUENCE_VIOLATION")

    @staticmethod
    def _phase(value: Any) -> str:
        phase = str(value or "").upper()
        if phase not in {"INITIAL", "FINAL"}:
            raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(
                "EVIDENCE_READ_PORT_PHASE_INVALID"
            )
        return phase

    @property
    def _scope(self) -> Mapping[str, Any]:
        return self._protected_adapter_plan.protected_scope_binding.binding

    @property
    def _schema(self) -> Mapping[str, Any]:
        return (
            self._protected_adapter_plan.protected_scope_binding
            .protected_evidence_schema.schema
        )

    def _scope_for_probe(self) -> dict[str, Any]:
        scope = self._scope
        return {
            "schema_sha256": scope["schema_sha256"],
            "backend_instance_sha256": scope["backend_instance_sha256"],
            "maintenance_epoch": scope["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": scope[
                "candidate_maintenance_lease_receipt_sha256"
            ],
            "authenticated_authority_receipt_sha256": scope[
                "candidate_authenticated_authority_receipt_sha256"
            ],
        }

    def _snapshot_valid(self, value: Any) -> bool:
        scope = self._scope
        plan = self._protected_adapter_plan.plan
        return bool(
            conformance_v1._snapshot_valid(value, self._schema)
            and all(
                value.get(field_name) == scope[scope_name]
                for field_name, scope_name in (
                    ("schema_sha256", "schema_sha256"),
                    ("provider_binding_sha256", "provider_binding_sha256"),
                    ("backend_instance_sha256", "backend_instance_sha256"),
                    (
                        "registry_path_binding_sha256",
                        "registry_path_binding_sha256",
                    ),
                    ("wal_storage_binding_sha256", "wal_storage_binding_sha256"),
                    (
                        "resolved_ledger_storage_binding_sha256",
                        "resolved_ledger_storage_binding_sha256",
                    ),
                    ("lock_namespace_sha256", "lock_namespace_sha256"),
                    (
                        "authenticated_authority_receipt_sha256",
                        "candidate_authenticated_authority_receipt_sha256",
                    ),
                )
            )
            and value.get("backend_capability_attestation_sha256")
            == plan["backend_capability_attestation_sha256"]
        )

    def _snapshot_argument_valid(
        self, snapshot: Any, phase: str
    ) -> bool:
        expected = self._snapshots.get(phase)
        return bool(
            isinstance(snapshot, Mapping)
            and expected is not None
            and snapshot == expected
            and self._snapshot_valid(snapshot)
        )

    def _artifact_authority_valid(self, value: Any) -> bool:
        return bool(
            isinstance(value, Mapping)
            and value.get("authenticated_authority_receipt_sha256")
            == self._scope[
                "candidate_authenticated_authority_receipt_sha256"
            ]
        )

    def read_backend_snapshot_offline(self, *, phase: str) -> Mapping[str, Any]:
        normalized = self._phase(phase)
        self._require_step(f"{normalized}_BACKEND_SNAPSHOT")
        try:
            value = self._source_read_port.read_backend_snapshot_offline(
                phase=normalized
            )
        except Exception as exc:
            raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(
                "SYNTHETIC_BACKEND_SNAPSHOT_READ_FAILED_CLOSED"
            ) from exc
        if not self._snapshot_valid(value):
            self._blocked("SYNTHETIC_BACKEND_SNAPSHOT_INVALID")
        protected_copy = reference_v1._canonical_copy(value)
        self._snapshots[normalized] = protected_copy
        self._counts["snapshot"] += 1
        self._step += 1
        return reference_v1._canonical_copy(protected_copy)

    def read_backend_capability_probe_offline(
        self, *, snapshot: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self._require_step("INITIAL_BACKEND_CAPABILITY_PROBE")
        if not self._snapshot_argument_valid(snapshot, "INITIAL"):
            self._blocked("INITIAL_BACKEND_SNAPSHOT_ARGUMENT_INVALID")
        try:
            value = self._source_read_port.read_backend_capability_probe_offline(
                snapshot=self._snapshots["INITIAL"]
            )
        except Exception as exc:
            raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(
                "SYNTHETIC_BACKEND_CAPABILITY_PROBE_READ_FAILED_CLOSED"
            ) from exc
        if not reference_v1._probe_valid(value, self._scope_for_probe()):
            self._blocked("SYNTHETIC_BACKEND_CAPABILITY_PROBE_INVALID")
        self._counts["probe"] += 1
        self._step += 1
        return reference_v1._canonical_copy(value)

    def read_transaction_log_audit_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        normalized = self._phase(phase)
        self._require_step(f"{normalized}_TRANSACTION_LOG_AUDIT")
        if not self._snapshot_argument_valid(snapshot, normalized):
            self._blocked(f"{normalized}_BACKEND_SNAPSHOT_ARGUMENT_INVALID")
        try:
            value = self._source_read_port.read_transaction_log_audit_offline(
                snapshot=self._snapshots[normalized], phase=normalized
            )
        except Exception as exc:
            raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(
                "SYNTHETIC_TRANSACTION_LOG_AUDIT_READ_FAILED_CLOSED"
            ) from exc
        if not (
            conformance_v1._audit_valid(
                value, self._snapshots[normalized], self._schema
            )
            and self._artifact_authority_valid(value)
        ):
            self._blocked("SYNTHETIC_TRANSACTION_LOG_AUDIT_INVALID")
        self._counts["audit"] += 1
        self._step += 1
        return reference_v1._canonical_copy(value)

    def read_prepared_catalog_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        return self._read_catalog(snapshot=snapshot, phase=phase, resolved=False)

    def read_resolved_catalog_offline(
        self, *, snapshot: Mapping[str, Any], phase: str
    ) -> Mapping[str, Any]:
        return self._read_catalog(snapshot=snapshot, phase=phase, resolved=True)

    def _read_catalog(
        self,
        *,
        snapshot: Mapping[str, Any],
        phase: str,
        resolved: bool,
    ) -> Mapping[str, Any]:
        normalized = self._phase(phase)
        catalog_name = "RESOLVED" if resolved else "PREPARED"
        self._require_step(f"{normalized}_{catalog_name}_CATALOG")
        if not self._snapshot_argument_valid(snapshot, normalized):
            self._blocked(f"{normalized}_BACKEND_SNAPSHOT_ARGUMENT_INVALID")
        source_method = (
            self._source_read_port.read_resolved_catalog_offline
            if resolved
            else self._source_read_port.read_prepared_catalog_offline
        )
        try:
            value = source_method(
                snapshot=self._snapshots[normalized], phase=normalized
            )
        except Exception as exc:
            raise StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1(
                f"SYNTHETIC_{catalog_name}_CATALOG_READ_FAILED_CLOSED"
            ) from exc
        if not (
            conformance_v1._catalog_valid(
                value,
                self._snapshots[normalized],
                self._schema,
                resolved=resolved,
            )
            and self._artifact_authority_valid(value)
        ):
            self._blocked(f"SYNTHETIC_{catalog_name}_CATALOG_INVALID")
        self._counts["resolved" if resolved else "prepared"] += 1
        self._step += 1
        return reference_v1._canonical_copy(value)

    @property
    def completed(self) -> bool:
        return self._step == len(_SEQUENCE)

    def counters(self) -> dict[str, int]:
        return dict(self._counts)

    def state_snapshot(self) -> dict[str, Any]:
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_V1_VERSION,
            "offline_only": True,
            "memory_only": True,
            "synthetic_only": True,
            "enabled": self._config.enabled is True,
            "next_step": (
                _SEQUENCE[self._step] if self._step < len(_SEQUENCE) else None
            ),
            "completed": self.completed,
            "read_count": sum(self._counts.values()),
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "production_authority": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def __repr__(self) -> str:
        return "OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1(<protected>)"


__all__ = [
    "OFFLINE_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_SCOPE_ATTESTATION_V1",
    "OfflineStartupRecoveryEvidenceReadPortReferenceAdapterConfigV1",
    "OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1",
    "StartupRecoveryEvidenceReadPortReferenceAdapterBlockedV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_EVIDENCE_READ_PORT_REFERENCE_ADAPTER_OFFLINE_V1_VERSION",
]
