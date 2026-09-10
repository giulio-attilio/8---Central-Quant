"""Default-off reference for synthetic terminal-receipt normalization."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1 as conformance_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1 as plan_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as reference_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1 as scope_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-TERMINAL-RECEIPT-NORMALIZER-REFERENCE-"
    "OFFLINE-V1"
)
OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_MEMORY_ONLY_V1"
)


class StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1(RuntimeError):
    """Raised when a synthetic normalization precondition is not satisfied."""


@dataclass(frozen=True)
class OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_plan_sha256: str | None = field(default=None, repr=False)
    expected_source_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1:
    """Strict batch-scoped facade over the exact in-memory normalizer."""

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
        source_normalizer_port: Any,
        config: OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1
        | None = None,
    ) -> None:
        self._protected_adapter_plan = protected_adapter_plan
        self._source_normalizer_port = source_normalizer_port
        self._config = (
            config
            or OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1()
        )
        self._next_index = 0
        self._normalized_receipts: list[dict[str, Any]] = []

    def _blocked(self, reason: str) -> None:
        raise StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1(reason)

    def _require_ready(self) -> None:
        if self._config.enabled is not True:
            self._blocked("TERMINAL_RECEIPT_NORMALIZER_REFERENCE_DEFAULT_OFF")
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1
        ):
            self._blocked("TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_INVALID")
        protected = self._protected_adapter_plan
        source = self._source_normalizer_port
        if not plan_v1.protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
            protected
        ):
            self._blocked("PROTECTED_EVIDENCE_READ_PORT_ADAPTER_PLAN_INVALID")
        if "normalize_terminal_receipt_offline" not in protected.plan[
            "required_ports"
        ]:
            self._blocked("TERMINAL_RECEIPT_NORMALIZER_PORT_NOT_REQUIRED_BY_PLAN")
        if not hmac.compare_digest(
            protected.plan_sha256,
            str(self._config.expected_adapter_plan_sha256 or ""),
        ):
            self._blocked("EVIDENCE_READ_PORT_ADAPTER_PLAN_PIN_MISMATCH")
        if (
            type(source)
            is not reference_v1.InMemorySyntheticTerminalReceiptNormalizerV1
        ):
            self._blocked("EXACT_IN_MEMORY_SYNTHETIC_NORMALIZER_REQUIRED")
        source_identity = (
            ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                source
            )
        )
        if not hmac.compare_digest(
            source_identity,
            str(self._config.expected_source_object_identity_sha256 or ""),
        ):
            self._blocked("TERMINAL_RECEIPT_NORMALIZER_SOURCE_INSTANCE_PIN_MISMATCH")

    @property
    def _protected_scope(self) -> Any:
        return self._protected_adapter_plan.protected_scope_binding

    @property
    def _scope(self) -> Mapping[str, Any]:
        return self._protected_scope.binding

    @property
    def _schema(self) -> Mapping[str, Any]:
        return self._protected_scope.protected_evidence_schema.schema

    def _expected_items(self) -> list[tuple[str, str]]:
        return sorted(
            (
                item["transaction_sha256"],
                item["source_state"],
            )
            for item in self._scope["pending_items"]
        )

    def _receipt_valid(
        self,
        receipt: Any,
        *,
        transaction_sha256: str,
        source_state: str,
    ) -> bool:
        scope = self._scope
        return bool(
            conformance_v1._terminal_receipt_valid(
                receipt, self._schema, scope["maintenance_epoch"]
            )
            and receipt.get("transaction_sha256") == transaction_sha256
            and receipt.get("source_state") == source_state
            and receipt.get("schema_sha256") == scope["schema_sha256"]
            and receipt.get("provider_binding_sha256")
            == scope["provider_binding_sha256"]
            and receipt.get("backend_instance_sha256")
            == scope["backend_instance_sha256"]
            and receipt.get("authenticated_authority_receipt_sha256")
            == scope["candidate_authenticated_authority_receipt_sha256"]
            and receipt.get("durable") is False
            and receipt.get("production_evidence") is False
        )

    def normalize_terminal_receipt_offline(
        self,
        *,
        raw_receipt: Mapping[str, Any],
        protected_scope_binding: Any,
    ) -> Mapping[str, Any]:
        self._require_ready()
        if protected_scope_binding is not self._protected_scope or not (
            scope_v1.protected_startup_recovery_batch_evidence_scope_binding_valid_v1(
                protected_scope_binding
            )
        ):
            self._blocked("EXACT_PROTECTED_SCOPE_INSTANCE_REQUIRED")
        expected_items = self._expected_items()
        if self._next_index >= len(expected_items):
            self._blocked("TERMINAL_RECEIPT_BATCH_ALREADY_COMPLETE")
        if not reference_v1._raw_receipt_valid(raw_receipt):
            self._blocked("RAW_TERMINAL_RECEIPT_INVALID")
        expected_transaction, expected_source = expected_items[self._next_index]
        if (
            raw_receipt["transaction_sha256"],
            raw_receipt["source_state"],
        ) != (expected_transaction, expected_source):
            self._blocked("TERMINAL_RECEIPT_BATCH_SEQUENCE_MISMATCH")
        try:
            receipt = self._source_normalizer_port.normalize_terminal_receipt_offline(
                raw_receipt=raw_receipt,
                protected_scope_binding=self._protected_scope,
            )
        except Exception as exc:
            raise StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1(
                "SYNTHETIC_TERMINAL_RECEIPT_NORMALIZATION_FAILED_CLOSED"
            ) from exc
        if not self._receipt_valid(
            receipt,
            transaction_sha256=expected_transaction,
            source_state=expected_source,
        ):
            self._blocked("NORMALIZED_TERMINAL_RECEIPT_INVALID")
        protected_copy = reference_v1._canonical_copy(receipt)
        self._normalized_receipts.append(protected_copy)
        self._next_index += 1
        return reference_v1._canonical_copy(protected_copy)

    @property
    def completed(self) -> bool:
        return bool(
            self._config.enabled is True
            and self._next_index == len(self._expected_items())
        )

    @property
    def call_count(self) -> int:
        return self._next_index

    def terminal_receipt_set_snapshot(self) -> list[Mapping[str, Any]]:
        self._require_ready()
        if not self.completed:
            self._blocked("TERMINAL_RECEIPT_BATCH_INCOMPLETE")
        expected = dict(self._expected_items())
        receipts = sorted(
            self._normalized_receipts, key=lambda item: item["receipt_sha256"]
        )
        if not (
            len(receipts) == len(expected)
            and len({item["transaction_sha256"] for item in receipts})
            == len(receipts)
            and {
                item["transaction_sha256"]: item["source_state"]
                for item in receipts
            }
            == expected
            and all(
                self._receipt_valid(
                    item,
                    transaction_sha256=item["transaction_sha256"],
                    source_state=item["source_state"],
                )
                for item in receipts
            )
        ):
            self._blocked("TERMINAL_RECEIPT_SET_INVALID")
        return reference_v1._canonical_copy(receipts)

    def state_snapshot(self) -> dict[str, Any]:
        expected_count = len(self._expected_items()) if self._config.enabled else 0
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_V1_VERSION,
            "offline_only": True,
            "memory_only": True,
            "synthetic_only": True,
            "enabled": self._config.enabled is True,
            "expected_receipt_count": expected_count,
            "normalized_receipt_count": self._next_index,
            "completed": self._config.enabled is True and self.completed,
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
        return "OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1(<protected>)"


__all__ = [
    "OFFLINE_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_SCOPE_ATTESTATION_V1",
    "OfflineStartupRecoveryTerminalReceiptNormalizerReferenceConfigV1",
    "OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1",
    "StartupRecoveryTerminalReceiptNormalizerReferenceBlockedV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_TERMINAL_RECEIPT_NORMALIZER_REFERENCE_OFFLINE_V1_VERSION",
]
