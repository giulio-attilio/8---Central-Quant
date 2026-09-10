"""Offline composition of six protected reference ports and evidence builder."""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1 as ports_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1 as plan_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_v1 as read_adapter_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1 as builder_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_v1 as normalizer_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-SIX-PORT-EVIDENCE-BUILDER-COMPOSITION-"
    "OFFLINE-V1"
)
OFFLINE_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_SCOPE_ATTESTATION_V1 = (
    "C3_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_MEMORY_ONLY_V1"
)


@dataclass(frozen=True)
class OfflineStartupRecoverySixPortEvidenceBuilderCompositionConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_adapter_plan_sha256: str | None = field(default=None, repr=False)
    expected_read_adapter_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_normalizer_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    max_pending_items: int = 100

    def __post_init__(self) -> None:
        if not 1 <= self.max_pending_items <= 10_000:
            raise ValueError("max_pending_items must be between 1 and 10000")


class OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1:
    """Collects through protected facades, then builds from a canonical replay."""

    def __init__(
        self,
        *,
        config: OfflineStartupRecoverySixPortEvidenceBuilderCompositionConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config
            or OfflineStartupRecoverySixPortEvidenceBuilderCompositionConfigV1()
        )

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_V1_VERSION,
            "offline_only": True,
            "memory_only": True,
            "synthetic_only": True,
            "dependencies_verified": False,
            "raw_receipts_verified": False,
            "protected_reads_completed": False,
            "protected_normalization_completed": False,
            "canonical_replay_bound": False,
            "evidence_builder_called": False,
            "bundle_created": False,
            "bundle_matches_protected_collection": False,
            "scope_aware_conformance_verified": False,
            "fixture_bundle": None,
            "protected_read_count": 0,
            "protected_normalizer_call_count": 0,
            "replay_read_count": 0,
            "replay_normalizer_call_count": 0,
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
            "reasons": [],
        }

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_SCOPE_ATTESTATION_V1
        ):
            return "SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_SCOPE_INVALID"
        pins = (
            self._config.expected_adapter_plan_sha256,
            self._config.expected_read_adapter_object_identity_sha256,
            self._config.expected_normalizer_object_identity_sha256,
        )
        if any(not builder_v1._valid_sha256(item) for item in pins):
            return "SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_PINS_INVALID"
        return None

    def _dependencies_valid(
        self,
        *,
        protected_adapter_plan: Any,
        read_adapter: Any,
        terminal_normalizer: Any,
    ) -> bool:
        if not (
            plan_v1.protected_startup_recovery_evidence_read_port_adapter_plan_valid_v1(
                protected_adapter_plan
            )
            and hmac.compare_digest(
                protected_adapter_plan.plan_sha256,
                str(self._config.expected_adapter_plan_sha256),
            )
            and type(read_adapter)
            is read_adapter_v1.OfflineStartupRecoveryEvidenceReadPortReferenceAdapterV1
            and type(terminal_normalizer)
            is normalizer_v1.OfflineStartupRecoveryTerminalReceiptNormalizerReferenceV1
            and read_adapter._protected_adapter_plan is protected_adapter_plan
            and terminal_normalizer._protected_adapter_plan
            is protected_adapter_plan
        ):
            return False
        read_identity = (
            ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                read_adapter
            )
        )
        normalizer_identity = (
            ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                terminal_normalizer
            )
        )
        return bool(
            hmac.compare_digest(
                read_identity,
                str(
                    self._config.expected_read_adapter_object_identity_sha256
                ),
            )
            and hmac.compare_digest(
                normalizer_identity,
                str(self._config.expected_normalizer_object_identity_sha256),
            )
            and read_adapter.counters()
            == {
                "snapshot": 0,
                "audit": 0,
                "prepared": 0,
                "resolved": 0,
                "probe": 0,
            }
            and terminal_normalizer.call_count == 0
        )

    def compose_offline(
        self,
        *,
        protected_adapter_plan: Any,
        read_adapter: Any,
        terminal_normalizer: Any,
        raw_terminal_receipts: Any,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        if not self._dependencies_valid(
            protected_adapter_plan=protected_adapter_plan,
            read_adapter=read_adapter,
            terminal_normalizer=terminal_normalizer,
        ):
            result["reasons"].append("PROTECTED_SIX_PORT_DEPENDENCIES_INVALID")
            return result
        result["dependencies_verified"] = True
        protected_scope = protected_adapter_plan.protected_scope_binding
        expected_sources = {
            item["transaction_sha256"]: item["source_state"]
            for item in protected_scope.binding["pending_items"]
        }
        if not (
            isinstance(raw_terminal_receipts, (list, tuple))
            and 1
            <= len(raw_terminal_receipts)
            <= self._config.max_pending_items
            and len(raw_terminal_receipts) == len(expected_sources)
            and all(
                builder_v1._raw_receipt_valid(item)
                for item in raw_terminal_receipts
            )
        ):
            result["reasons"].append("RAW_TERMINAL_RECEIPT_SET_INVALID")
            return result
        raw_by_transaction = {
            item["transaction_sha256"]: item for item in raw_terminal_receipts
        }
        if not (
            len(raw_by_transaction) == len(raw_terminal_receipts)
            and {
                key: item["source_state"]
                for key, item in raw_by_transaction.items()
            }
            == expected_sources
        ):
            result["reasons"].append("RAW_TERMINAL_RECEIPT_SCOPE_MISMATCH")
            return result
        result["raw_receipts_verified"] = True
        try:
            initial_snapshot = read_adapter.read_backend_snapshot_offline(
                phase="INITIAL"
            )
            capability_probe = read_adapter.read_backend_capability_probe_offline(
                snapshot=initial_snapshot
            )
            initial_audit = read_adapter.read_transaction_log_audit_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            initial_prepared = read_adapter.read_prepared_catalog_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            initial_resolved = read_adapter.read_resolved_catalog_offline(
                snapshot=initial_snapshot, phase="INITIAL"
            )
            result["protected_read_count"] = 5
            normalized_receipts = [
                terminal_normalizer.normalize_terminal_receipt_offline(
                    raw_receipt=raw_by_transaction[transaction_sha256],
                    protected_scope_binding=protected_scope,
                )
                for transaction_sha256 in sorted(raw_by_transaction)
            ]
            normalized_receipts = (
                terminal_normalizer.terminal_receipt_set_snapshot()
            )
            result["protected_normalization_completed"] = True
            result["protected_normalizer_call_count"] = len(
                normalized_receipts
            )
            final_snapshot = read_adapter.read_backend_snapshot_offline(
                phase="FINAL"
            )
            final_audit = read_adapter.read_transaction_log_audit_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            final_prepared = read_adapter.read_prepared_catalog_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            final_resolved = read_adapter.read_resolved_catalog_offline(
                snapshot=final_snapshot, phase="FINAL"
            )
            result["protected_read_count"] = 9
            result["protected_reads_completed"] = read_adapter.completed
        except Exception:
            result["reasons"].append("PROTECTED_SIX_PORT_COLLECTION_FAILED_CLOSED")
            return result
        artifacts = {
            "initial_backend_snapshot": initial_snapshot,
            "initial_transaction_log_audit": initial_audit,
            "initial_prepared_catalog": initial_prepared,
            "initial_resolved_catalog": initial_resolved,
            "final_backend_snapshot": final_snapshot,
            "final_transaction_log_audit": final_audit,
            "final_prepared_catalog": final_prepared,
            "final_resolved_catalog": final_resolved,
        }
        replay_read_port = builder_v1.InMemorySyntheticEvidenceReadPortV1(
            artifacts=artifacts, capability_probe=capability_probe
        )
        replay_normalizer = (
            builder_v1.InMemorySyntheticTerminalReceiptNormalizerV1(
                terminal_receipts=normalized_receipts
            )
        )
        ports_contract = ports_v1.DormantStartupRecoveryEvidenceBuilderPortsContractV1(
            config=ports_v1.DormantStartupRecoveryEvidenceBuilderPortsConfigV1(
                enabled=True,
                scope_attestation=(
                    ports_v1.OFFLINE_STARTUP_RECOVERY_EVIDENCE_BUILDER_PORTS_SCOPE_ATTESTATION_V1
                ),
                expected_scope_binding_sha256=protected_scope.binding_sha256,
                expected_read_port_object_identity_sha256=(
                    ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                        replay_read_port
                    )
                ),
                expected_normalizer_port_object_identity_sha256=(
                    ports_v1.startup_recovery_evidence_builder_port_object_identity_sha256_v1(
                        replay_normalizer
                    )
                ),
            )
        )
        ports_result = ports_contract.bind_offline(
            protected_scope_binding=protected_scope,
            evidence_read_port=replay_read_port,
            terminal_normalizer_port=replay_normalizer,
        )
        protected_ports = ports_result.get("protected_port_binding")
        if ports_result.get("ok") is not True or protected_ports is None:
            result["reasons"].append("CANONICAL_REPLAY_PORT_BINDING_FAILED")
            return result
        result["canonical_replay_bound"] = True
        builder = builder_v1.OfflineStartupRecoveryEvidenceReferenceBuilderV1(
            config=builder_v1.OfflineStartupRecoveryEvidenceReferenceBuilderConfigV1(
                enabled=True,
                scope_attestation=(
                    builder_v1.OFFLINE_STARTUP_RECOVERY_EVIDENCE_REFERENCE_BUILDER_SCOPE_ATTESTATION_V1
                ),
                expected_port_binding_sha256=protected_ports.binding_sha256,
                max_pending_items=self._config.max_pending_items,
            )
        )
        result["evidence_builder_called"] = True
        builder_result = builder.build_offline(
            protected_port_binding=protected_ports,
            raw_terminal_receipts=raw_terminal_receipts,
        )
        result["replay_read_count"] = sum(replay_read_port.counters().values())
        result["replay_normalizer_call_count"] = replay_normalizer.call_count
        bundle = builder_result.get("fixture_bundle")
        if builder_result.get("ok") is not True or bundle is None:
            result["reasons"].append("OFFLINE_EVIDENCE_BUILDER_FAILED_CLOSED")
            return result
        collection_matches = bool(
            all(bundle[key] == value for key, value in artifacts.items())
            and bundle["terminal_receipts"] == normalized_receipts
        )
        if not collection_matches:
            result["reasons"].append("BUILDER_BUNDLE_COLLECTION_MISMATCH")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_PASSED_OFFLINE",
            bundle_created=True,
            bundle_matches_protected_collection=True,
            scope_aware_conformance_verified=(
                builder_result.get("scope_aware_conformance_verified") is True
            ),
            fixture_bundle=builder_v1._canonical_copy(bundle),
        )
        return result


__all__ = [
    "OFFLINE_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_SCOPE_ATTESTATION_V1",
    "OfflineStartupRecoverySixPortEvidenceBuilderCompositionConfigV1",
    "OfflineStartupRecoverySixPortEvidenceBuilderCompositionV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_SIX_PORT_EVIDENCE_BUILDER_COMPOSITION_OFFLINE_V1_VERSION",
]
