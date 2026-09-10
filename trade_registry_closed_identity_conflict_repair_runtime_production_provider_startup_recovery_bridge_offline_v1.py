"""Offline bridge for the production-provider startup-recovery port.

Only the exact synthetic provider-port double defined here is accepted.  The
double can wrap only the temporary physical V2 backend, so this module cannot
open or mutate the real Registry even when explicitly enabled in a local test.
No production provider instance is accepted, constructed, or called.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1 as startup_adapter
import trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1 as provider_binding


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-PRODUCTION-PROVIDER-STARTUP-RECOVERY-BRIDGE-OFFLINE-V1"
)
OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SYNTHETIC_TEMPORARY_ONLY_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha256(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


class OfflineProductionProviderStartupRecoveryBridgeBlockedV1(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class OfflineProductionProviderStartupRecoveryBridgeConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_binding_sha256: str | None = field(default=None, repr=False)


class SyntheticProductionStartupRecoveryProviderPortDoubleV1:
    """Translate future provider-port calls to an exact temporary backend."""

    def __init__(self, *, temporary_backend: Any = None) -> None:
        if (
            type(temporary_backend)
            is not physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2
        ):
            raise ValueError("exact temporary physical backend required")
        self._backend = temporary_backend
        self._counters = {
            "snapshot_call_count": 0,
            "prepared_catalog_call_count": 0,
            "transaction_log_audit_call_count": 0,
            "reconcile_call_count": 0,
        }

    def __repr__(self) -> str:
        return "SyntheticProductionStartupRecoveryProviderPortDoubleV1(<protected>)"

    def read_startup_recovery_snapshot_offline(self) -> Mapping[str, Any]:
        self._counters["snapshot_call_count"] += 1
        return self._backend.snapshot_offline()

    def read_startup_recovery_prepared_catalog_offline(
        self,
    ) -> Mapping[str, Any]:
        self._counters["prepared_catalog_call_count"] += 1
        return self._backend.list_prepared_transactions_offline()

    def read_startup_recovery_transaction_log_audit_offline(
        self,
    ) -> Mapping[str, Any]:
        self._counters["transaction_log_audit_call_count"] += 1
        return self._backend.inspect_transaction_log_offline()

    def reconcile_startup_recovery_transaction_offline(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self._counters["reconcile_call_count"] += 1
        return self._backend.reconcile_attested_transaction_offline(request)

    def counters(self) -> dict[str, int]:
        return dict(self._counters)


class OfflineProductionProviderStartupRecoveryBridgeV1:
    """Expose the four adapter methods without production authority."""

    def __init__(
        self,
        *,
        protected_binding: provider_binding.ProtectedStartupRecoveryProductionProviderBindingV1
        | None = None,
        provider_port: Any = None,
        config: OfflineProductionProviderStartupRecoveryBridgeConfigV1
        | None = None,
    ) -> None:
        self._binding = protected_binding
        self._provider_port = provider_port
        self._config = (
            config or OfflineProductionProviderStartupRecoveryBridgeConfigV1()
        )
        self._counters = {
            "snapshot_offline": 0,
            "list_prepared_transactions_offline": 0,
            "inspect_transaction_log_offline": 0,
            "reconcile_attested_transaction_offline": 0,
        }

    def __repr__(self) -> str:
        return "OfflineProductionProviderStartupRecoveryBridgeV1(<protected>)"

    def _require_ready(self) -> Mapping[str, Any]:
        if self._config.enabled is not True:
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_DEFAULT_OFF"
            )
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_INVALID"
            )
        expected_binding = str(
            self._config.expected_binding_sha256 or ""
        ).lower().strip()
        if not (
            _valid_sha256(expected_binding)
            and provider_binding.protected_startup_recovery_production_provider_binding_valid_v1(
                self._binding
            )
            and hmac.compare_digest(self._binding.binding_sha256, expected_binding)
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "PRODUCTION_PROVIDER_STARTUP_RECOVERY_BINDING_INVALID"
            )
        if (
            type(self._provider_port)
            is not SyntheticProductionStartupRecoveryProviderPortDoubleV1
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "EXACT_SYNTHETIC_PROVIDER_PORT_REQUIRED"
            )
        binding = self._binding.binding
        if not (
            binding.get("provider_instance_bound") is False
            and binding.get("adapter_instance_bound") is False
            and binding.get("bridge_required") is True
            and binding.get("recovery_execution_allowed") is False
            and binding.get("production_authority") is False
            and binding.get("runtime_integrated") is False
            and binding.get("production_ready") is False
            and binding.get("synthetic_only") is True
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "DORMANT_PROVIDER_BINDING_SAFETY_VECTOR_INVALID"
            )
        return binding

    @staticmethod
    def _snapshot_valid(
        snapshot: Any, binding: Mapping[str, Any]
    ) -> bool:
        return bool(
            backend_contract.backend_snapshot_valid_v2(snapshot)
            and snapshot.get("backend_instance_sha256")
            == binding.get("backend_instance_sha256")
            and snapshot.get("registry_path_binding_sha256")
            == binding.get("registry_path_binding_sha256")
            and snapshot.get("lock_namespace_sha256")
            == binding.get("lock_namespace_sha256")
            and snapshot.get("synthetic_only") is True
            and snapshot.get("durable") is False
            and snapshot.get("production_evidence") is False
            and snapshot.get("filesystem_accessed") is True
        )

    def _read_snapshot(
        self, binding: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        snapshot = self._provider_port.read_startup_recovery_snapshot_offline()
        if not self._snapshot_valid(snapshot, binding):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_BACKEND_SNAPSHOT_INVALID"
            )
        return snapshot

    def snapshot_offline(self) -> Mapping[str, Any]:
        binding = self._require_ready()
        self._counters["snapshot_offline"] += 1
        return self._read_snapshot(binding)

    def list_prepared_transactions_offline(self) -> Mapping[str, Any]:
        binding = self._require_ready()
        self._counters["list_prepared_transactions_offline"] += 1
        snapshot = self._read_snapshot(binding)
        catalog = (
            self._provider_port.read_startup_recovery_prepared_catalog_offline()
        )
        if not backend_contract.prepared_catalog_valid_v2(catalog, snapshot):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_PREPARED_CATALOG_INVALID"
            )
        return catalog

    def inspect_transaction_log_offline(self) -> Mapping[str, Any]:
        binding = self._require_ready()
        self._counters["inspect_transaction_log_offline"] += 1
        snapshot = self._read_snapshot(binding)
        audit = (
            self._provider_port.read_startup_recovery_transaction_log_audit_offline()
        )
        if not startup_adapter.temporary_transaction_log_audit_valid_v1(
            audit, snapshot
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_TRANSACTION_LOG_AUDIT_INVALID"
            )
        return audit

    def reconcile_attested_transaction_offline(
        self, request: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        binding = self._require_ready()
        self._counters["reconcile_attested_transaction_offline"] += 1
        if not isinstance(request, Mapping):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_RECOVERY_REQUEST_INVALID"
            )
        supplied_sha = str(request.get("request_sha256") or "")
        expected_sha = backend_contract.stable_sha256_v2(
            {
                key: item
                for key, item in request.items()
                if key != "request_sha256"
            }
        )
        if not (
            _valid_sha256(supplied_sha)
            and hmac.compare_digest(supplied_sha, expected_sha)
            and request.get("backend_instance_sha256")
            == binding.get("backend_instance_sha256")
            and request.get("registry_path_binding_sha256")
            == binding.get("registry_path_binding_sha256")
            and request.get("lock_namespace_sha256")
            == binding.get("lock_namespace_sha256")
            and _valid_sha256(request.get("fresh_maintenance_epoch"))
            and request.get("fresh_maintenance_epoch")
            != request.get("previous_maintenance_epoch")
            and request.get("synthetic_only") is True
            and request.get("production_authority") is False
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_RECOVERY_REQUEST_INVALID"
            )
        result = self._provider_port.reconcile_startup_recovery_transaction_offline(
            request
        )
        if not backend_contract.recovery_result_valid_v2(
            result, request, request.get("checkpoint_index")
        ):
            raise OfflineProductionProviderStartupRecoveryBridgeBlockedV1(
                "SYNTHETIC_PROVIDER_RECOVERY_RESULT_INVALID"
            )
        return result

    def counters(self) -> dict[str, int]:
        return dict(self._counters)


__all__ = [
    "OFFLINE_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_SCOPE_ATTESTATION_V1",
    "OfflineProductionProviderStartupRecoveryBridgeBlockedV1",
    "OfflineProductionProviderStartupRecoveryBridgeConfigV1",
    "OfflineProductionProviderStartupRecoveryBridgeV1",
    "SyntheticProductionStartupRecoveryProviderPortDoubleV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_PROVIDER_STARTUP_RECOVERY_BRIDGE_OFFLINE_V1_VERSION",
]
