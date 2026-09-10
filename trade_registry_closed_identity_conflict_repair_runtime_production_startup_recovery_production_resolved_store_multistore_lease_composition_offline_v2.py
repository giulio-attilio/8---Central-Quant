"""Protected in-memory composition: RESOLVED store -> lock -> lease executor."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as multistore_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2 as executor_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2 as store_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-RESOLVED-STORE-"
    "MULTISTORE-LEASE-COMPOSITION-OFFLINE-V2"
)
OFFLINE_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_SCOPE_ATTESTATION_V2 = (
    "C3_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_IN_MEMORY_ONLY_V2"
)
PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_RECEIPT_VERSION_V2 = (
    "C3_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_RECEIPT_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "resolved_store_binding_sha256",
        "multistore_lease_binding_sha256",
        "synthetic_authority_sha256",
        "transaction_projection_sha256",
        "resolved_projection_sha256",
        "executor_object_identity_sha256",
        "authority_object_identity_sha256",
        "transaction_port_object_identity_sha256",
        "resolved_port_object_identity_sha256",
        "event_observer_object_identity_sha256",
        "lease_token_sha256",
        "lock_order_sha256",
        "maintenance_epoch",
        "held_lock_count",
        "same_instances_verified",
        "store_to_projection_binding_verified",
        "projection_to_multistore_binding_verified",
        "multistore_to_executor_binding_verified",
        "lease_live_verified",
        "acquire_order_verified",
        "reverse_release_order_verified",
        "lease_released_after_execution",
        "in_memory_only",
        "synthetic_only",
        "physical_store_called",
        "filesystem_accessed",
        "network_accessed",
        "production_signature_verified",
        "production_authority",
        "production_durable",
        "production_ready",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "write_executed",
        "registry_write",
        "real_registry_accessed",
        "broker_called",
        "no_order_sent",
        "issued_at_epoch",
        "expires_at_epoch",
        "receipt_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def production_resolved_store_multistore_lease_execution_receipt_sha256_v2(
    value: dict[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def production_resolved_store_multistore_lease_execution_receipt_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not dict or set(value) != _RECEIPT_KEYS:
        return False
    try:
        supplied = str(value["receipt_sha256"])
        return bool(
            value["receipt_version"]
            == PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_RECEIPT_VERSION_V2
            and all(
                _valid_sha(value[key])
                for key in (
                    "resolved_store_binding_sha256",
                    "multistore_lease_binding_sha256",
                    "synthetic_authority_sha256",
                    "transaction_projection_sha256",
                    "resolved_projection_sha256",
                    "executor_object_identity_sha256",
                    "authority_object_identity_sha256",
                    "transaction_port_object_identity_sha256",
                    "resolved_port_object_identity_sha256",
                    "event_observer_object_identity_sha256",
                    "lease_token_sha256",
                    "lock_order_sha256",
                    "maintenance_epoch",
                    "receipt_sha256",
                )
            )
            and value["held_lock_count"] == 2
            and all(
                value[key] is True
                for key in (
                    "same_instances_verified",
                    "store_to_projection_binding_verified",
                    "projection_to_multistore_binding_verified",
                    "multistore_to_executor_binding_verified",
                    "lease_live_verified",
                    "acquire_order_verified",
                    "reverse_release_order_verified",
                    "lease_released_after_execution",
                    "in_memory_only",
                    "synthetic_only",
                    "no_order_sent",
                )
            )
            and all(
                value[key] is False
                for key in (
                    "physical_store_called",
                    "filesystem_accessed",
                    "network_accessed",
                    "production_signature_verified",
                    "production_authority",
                    "production_durable",
                    "production_ready",
                    "runtime_integrated",
                    "activation_allowed",
                    "live_allowed",
                    "write_executed",
                    "registry_write",
                    "real_registry_accessed",
                    "broker_called",
                )
            )
            and type(value["issued_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and value["issued_at_epoch"] < value["expires_at_epoch"]
            and value["expires_at_epoch"] - value["issued_at_epoch"] <= 300
            and hmac.compare_digest(
                supplied,
                production_resolved_store_multistore_lease_execution_receipt_sha256_v2(
                    value
                ),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class ProductionResolvedStoreMultistoreLeaseCompositionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_store_binding_sha256: str | None = field(default=None, repr=False)
    expected_multistore_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authority_sha256: str | None = field(default=None, repr=False)
    expected_transaction_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_store_binding_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_multistore_binding_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authority_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_transaction_projection_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_projection_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_transaction_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_executor_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_event_observer_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    lease_ttl_seconds: int = 30

    def __post_init__(self) -> None:
        if not 1 <= self.lease_ttl_seconds <= 300:
            raise ValueError("lease_ttl_seconds must be between 1 and 300")


class ProductionResolvedStoreMultistoreLeaseCompositionV2:
    def __init__(
        self,
        config: ProductionResolvedStoreMultistoreLeaseCompositionConfigV2
        | None = None,
        *,
        resolved_store_binding: Any = None,
        multistore_lease_binding: Any = None,
        synthetic_authority: Any = None,
        transaction_projection: Any = None,
        resolved_projection: Any = None,
        transaction_lock_port: Any = None,
        resolved_lock_port: Any = None,
        lease_executor: Any = None,
        event_observer: Any = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = (
            config or ProductionResolvedStoreMultistoreLeaseCompositionConfigV2()
        )
        self._store_binding = resolved_store_binding
        self._multistore_binding = multistore_lease_binding
        self._authority = synthetic_authority
        self._transaction_projection = transaction_projection
        self._resolved_projection = resolved_projection
        self._transaction_port = transaction_lock_port
        self._resolved_port = resolved_lock_port
        self._executor = lease_executor
        self._event_observer = event_observer
        self._clock = clock or (lambda: 0)

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_V2_BLOCKED",
            "reason": reason,
            "execution_receipt": None,
            "chain_verified": False,
            "lease_live_verified": False,
            "lease_released_after_execution": False,
            "in_memory_only": True,
            "physical_store_called": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "production_signature_verified": False,
            "production_authority": False,
            "production_durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_SCOPE_ATTESTATION_V2
        ):
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_SCOPE_INVALID"
        pins = (
            config.expected_store_binding_sha256,
            config.expected_multistore_binding_sha256,
            config.expected_authority_sha256,
            config.expected_transaction_projection_sha256,
            config.expected_resolved_projection_sha256,
            config.expected_store_binding_object_identity_sha256,
            config.expected_multistore_binding_object_identity_sha256,
            config.expected_authority_object_identity_sha256,
            config.expected_transaction_projection_object_identity_sha256,
            config.expected_resolved_projection_object_identity_sha256,
            config.expected_transaction_port_object_identity_sha256,
            config.expected_resolved_port_object_identity_sha256,
            config.expected_executor_object_identity_sha256,
            config.expected_event_observer_object_identity_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_PINS_INVALID"
        if not (
            type(self._store_binding)
            is store_v2.ProtectedProductionResolvedAuthorityStoreBindingV2
            and type(self._multistore_binding)
            is multistore_v2.ProtectedProductionMultistoreObservationLeaseBindingV2
            and type(self._authority)
            is executor_v2.ProtectedSyntheticProductionObservationAuthorityV2
            and type(self._transaction_projection)
            is multistore_v2.ProtectedProductionStoreLockPortProjectionV2
            and type(self._resolved_projection)
            is multistore_v2.ProtectedProductionStoreLockPortProjectionV2
            and type(self._transaction_port)
            is executor_v2.InMemoryProductionStoreLockPortDoubleV2
            and type(self._resolved_port)
            is executor_v2.InMemoryProductionStoreLockPortDoubleV2
            and type(self._executor)
            is executor_v2.ReferenceProductionMultistoreObservationLeaseExecutorV2
            and type(self._event_observer) is list
        ):
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_DEPENDENCY_INVALID"
        objects = (
            self._store_binding,
            self._multistore_binding,
            self._authority,
            self._transaction_projection,
            self._resolved_projection,
            self._transaction_port,
            self._resolved_port,
            self._executor,
            self._event_observer,
        )
        expected_identities = pins[5:]
        actual_identities = tuple(
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                item
            )
            for item in objects
        )
        if actual_identities != expected_identities:
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_INSTANCE_MISMATCH"
        if not (
            self._store_binding.binding_sha256 == pins[0]
            and self._multistore_binding.binding_sha256 == pins[1]
            and self._authority.authority_sha256 == pins[2]
            and self._transaction_projection.projection_sha256 == pins[3]
            and self._resolved_projection.projection_sha256 == pins[4]
        ):
            return "RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_HASH_MISMATCH"
        return None

    def execute_offline(self) -> dict[str, Any]:
        result = self._failed("")
        reason = self._reason()
        if reason is not None:
            result["reason"] = reason
            return result
        if not (
            store_v2.protected_production_resolved_authority_store_binding_valid_v2(
                self._store_binding
            )
            and multistore_v2.protected_production_multistore_observation_lease_binding_valid_v2(
                self._multistore_binding
            )
            and multistore_v2.production_store_lock_port_projection_valid_v2(
                self._transaction_projection
            )
            and multistore_v2.production_store_lock_port_projection_valid_v2(
                self._resolved_projection
            )
        ):
            result["reason"] = "RESOLVED_STORE_MULTISTORE_LEASE_CHAIN_INVALID"
            return result
        store_binding = dict(self._store_binding.binding)
        multistore_binding = dict(self._multistore_binding.binding)
        if not (
            self._store_binding.multistore_lease_binding_sha256
            == self._multistore_binding.binding_sha256
            and self._store_binding.resolved_lock_port_projection_sha256
            == self._resolved_projection.projection_sha256
            and store_binding["resolved_lock_port_projection_sha256"]
            == self._resolved_projection.projection_sha256
            and store_binding["storage_binding_sha256"]
            == multistore_binding[
                "resolved_authority_store_storage_binding_sha256"
            ]
            and store_binding["lock_namespace_sha256"]
            == multistore_binding[
                "resolved_authority_store_lock_namespace_sha256"
            ]
            and multistore_binding["transaction_store_projection_sha256"]
            == self._transaction_projection.projection_sha256
            and multistore_binding[
                "resolved_authority_store_projection_sha256"
            ]
            == self._resolved_projection.projection_sha256
            and self._authority.lease_binding_sha256
            == self._multistore_binding.binding_sha256
            and vars(self._transaction_port).get("_projection")
            is self._transaction_projection
            and vars(self._resolved_port).get("_projection")
            is self._resolved_projection
            and vars(self._transaction_port).get("_event_sink")
            is self._event_observer
            and vars(self._resolved_port).get("_event_sink")
            is self._event_observer
            and self._event_observer == []
            and self._executor.snapshot()["held_lock_count"] == 0
        ):
            result["reason"] = "RESOLVED_STORE_MULTISTORE_LEASE_CROSS_BINDING_INVALID"
            return result
        try:
            issued_at = int(self._clock())
            expires_at = issued_at + self._config.lease_ttl_seconds
            with self._executor.hold_offline(
                binding=self._multistore_binding,
                authority=self._authority,
                transaction_store_lock_port=self._transaction_port,
                resolved_authority_store_lock_port=self._resolved_port,
                expires_at_epoch=expires_at,
            ) as token:
                live = self._executor.validate_live(
                    token,
                    transaction_store_lock_port=self._transaction_port,
                    resolved_authority_store_lock_port=self._resolved_port,
                    now_epoch=issued_at,
                )
                active_snapshot = self._executor.snapshot()
                if not (
                    live
                    and active_snapshot["held_lock_count"] == 2
                    and active_snapshot["all_handles_live"] is True
                ):
                    raise ValueError(
                        "RESOLVED_STORE_MULTISTORE_LEASE_NOT_LIVE"
                    )
            expected_events = [
                ("ACQUIRE", multistore_v2.TRANSACTION_STORE_ROLE_V2),
                ("ACQUIRE", multistore_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2),
                ("RELEASE", multistore_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2),
                ("RELEASE", multistore_v2.TRANSACTION_STORE_ROLE_V2),
            ]
            if not (
                self._executor.snapshot()["held_lock_count"] == 0
                and self._event_observer == expected_events
                and self._transaction_port.snapshot()["active"] is False
                and self._resolved_port.snapshot()["active"] is False
            ):
                raise ValueError(
                    "RESOLVED_STORE_MULTISTORE_LEASE_RELEASE_INVALID"
                )
            receipt = {
                "receipt_version": PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_RECEIPT_VERSION_V2,
                "resolved_store_binding_sha256": self._store_binding.binding_sha256,
                "multistore_lease_binding_sha256": self._multistore_binding.binding_sha256,
                "synthetic_authority_sha256": self._authority.authority_sha256,
                "transaction_projection_sha256": self._transaction_projection.projection_sha256,
                "resolved_projection_sha256": self._resolved_projection.projection_sha256,
                "executor_object_identity_sha256": self._config.expected_executor_object_identity_sha256,
                "authority_object_identity_sha256": self._config.expected_authority_object_identity_sha256,
                "transaction_port_object_identity_sha256": self._config.expected_transaction_port_object_identity_sha256,
                "resolved_port_object_identity_sha256": self._config.expected_resolved_port_object_identity_sha256,
                "event_observer_object_identity_sha256": self._config.expected_event_observer_object_identity_sha256,
                "lease_token_sha256": token.token_sha256,
                "lock_order_sha256": token.lock_order_sha256,
                "maintenance_epoch": token.maintenance_epoch,
                "held_lock_count": 2,
                "same_instances_verified": True,
                "store_to_projection_binding_verified": True,
                "projection_to_multistore_binding_verified": True,
                "multistore_to_executor_binding_verified": True,
                "lease_live_verified": True,
                "acquire_order_verified": True,
                "reverse_release_order_verified": True,
                "lease_released_after_execution": True,
                "in_memory_only": True,
                "synthetic_only": True,
                "physical_store_called": False,
                "filesystem_accessed": False,
                "network_accessed": False,
                "production_signature_verified": False,
                "production_authority": False,
                "production_durable": False,
                "production_ready": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
                "write_executed": False,
                "registry_write": False,
                "real_registry_accessed": False,
                "broker_called": False,
                "no_order_sent": True,
                "issued_at_epoch": issued_at,
                "expires_at_epoch": expires_at,
            }
            receipt["receipt_sha256"] = (
                production_resolved_store_multistore_lease_execution_receipt_sha256_v2(
                    receipt
                )
            )
            if not production_resolved_store_multistore_lease_execution_receipt_valid_v2(
                receipt
            ):
                raise ValueError(
                    "RESOLVED_STORE_MULTISTORE_LEASE_RECEIPT_INVALID"
                )
        except Exception as exc:
            failure = str(exc)
            result["reason"] = (
                failure
                if re.fullmatch(r"[A-Z0-9_]{1,160}", failure)
                else "RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_FAILED_CLOSED"
            )
            result["lease_released_after_execution"] = bool(
                self._executor.snapshot()["held_lock_count"] == 0
            )
            return result
        result.update(
            {
                "ok": True,
                "status": "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_V2_VERIFIED_OFFLINE",
                "reason": None,
                "execution_receipt": receipt,
                "chain_verified": True,
                "lease_live_verified": True,
                "lease_released_after_execution": True,
            }
        )
        return result


__all__ = [
    "OFFLINE_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_SCOPE_ATTESTATION_V2",
    "PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_EXECUTION_RECEIPT_VERSION_V2",
    "ProductionResolvedStoreMultistoreLeaseCompositionConfigV2",
    "ProductionResolvedStoreMultistoreLeaseCompositionV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_STORE_MULTISTORE_LEASE_COMPOSITION_OFFLINE_V2_VERSION",
    "production_resolved_store_multistore_lease_execution_receipt_sha256_v2",
    "production_resolved_store_multistore_lease_execution_receipt_valid_v2",
]
