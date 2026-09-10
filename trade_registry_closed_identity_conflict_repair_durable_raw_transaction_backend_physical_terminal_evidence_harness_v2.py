"""Temporary-filesystem harness for physical terminal evidence V2."""

from __future__ import annotations

import tempfile
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_contract
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2 as conformance_harness
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_backend
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2 as evidence_contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_TERMINAL_EVIDENCE_HARNESS_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-PHYSICAL-TERMINAL-EVIDENCE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_800_000


def _sha(label: str) -> str:
    return backend_contract.stable_sha256_v2({"physical_terminal_evidence": label})


def run_physical_terminal_evidence_harness_v2() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="c3_durable_backend_v2_") as root:
        backend = physical_backend.TemporaryPhysicalDurableRawTransactionBackendV2(
            root,
            enabled=True,
            scope_attestation=physical_backend.TEMPORARY_PHYSICAL_REFERENCE_SCOPE_ATTESTATION_V2,
            clock=lambda: SYNTHETIC_NOW_V2,
        )
        backend.initialize_synthetic_registry_offline(
            {"closed_trades": [], "fixture": "terminal-evidence-source"}
        )
        port = evidence_contract.PhysicalTerminalEvidencePortV2(
            evidence_contract.PhysicalTerminalEvidencePortConfigV2(
                enabled=True,
                scope_attestation=evidence_contract.OFFLINE_PHYSICAL_TERMINAL_EVIDENCE_SCOPE_ATTESTATION_V2,
            ),
            clock=lambda: SYNTHETIC_NOW_V2 + 1,
        )

        apply_snapshot = backend.snapshot_offline()
        apply_request = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "terminal-evidence-committed"},
            label="terminal-evidence-apply",
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        apply_result = backend.apply_attested_transaction_offline(apply_request)
        apply_evidence = port.normalize_apply_offline(
            snapshot=apply_snapshot,
            request=apply_request,
            result=apply_result,
        )

        interrupted_request = backend.build_transaction_request_offline(
            {"closed_trades": [], "fixture": "terminal-evidence-interrupted"},
            label="terminal-evidence-recovery",
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        backend.prepare_interrupted_transaction_offline(interrupted_request)
        recovery_snapshot = backend.snapshot_offline()
        catalog = backend.list_prepared_transactions_offline()
        batch = backend_contract.build_resumable_recovery_batch_offline_v2(
            recovery_snapshot,
            catalog,
            batch_epoch=_sha("recovery-batch"),
            deadline_epoch=SYNTHETIC_NOW_V2 + 60,
        )
        record = catalog["records"][0]
        recovery_request = conformance_harness.build_synthetic_recovery_request_v2(
            record, batch, checkpoint_index=0
        )
        recovery_result = backend.reconcile_attested_transaction_offline(
            recovery_request
        )
        recovery_evidence = port.normalize_recovery_offline(
            snapshot=recovery_snapshot,
            catalog_record=record,
            batch=batch,
            request=recovery_request,
            result=recovery_result,
        )

        apply_receipt = apply_evidence.get("protected_receipt")
        recovery_receipt = recovery_evidence.get("protected_receipt")
        apply_valid = evidence_contract.protected_physical_terminal_evidence_valid_v2(
            apply_receipt
        )
        recovery_valid = evidence_contract.protected_physical_terminal_evidence_valid_v2(
            recovery_receipt
        )
        physical_hashes_distinct = bool(
            recovery_receipt
            and recovery_receipt.receipt["catalog_record_sha256"]
            != recovery_receipt.receipt["wal_prepared_record_sha256"]
        )
        protected_repr = bool(
            repr(apply_receipt)
            == "ProtectedPhysicalTerminalEvidenceReceiptV2(<protected>)"
            and repr(recovery_receipt)
            == "ProtectedPhysicalTerminalEvidenceReceiptV2(<protected>)"
        )
        ok = bool(
            apply_evidence.get("ok") is True
            and recovery_evidence.get("ok") is True
            and apply_valid
            and recovery_valid
            and apply_receipt.receipt["write_executed"] is True
            and apply_receipt.receipt["registry_write"] is True
            and recovery_receipt.receipt["write_executed"] is True
            and recovery_receipt.receipt["registry_write"] is False
            and physical_hashes_distinct
            and protected_repr
        )
        return {
            "ok": ok,
            "status": (
                "PHYSICAL_TERMINAL_EVIDENCE_V2_HARNESS_PASSED_OFFLINE"
                if ok else "PHYSICAL_TERMINAL_EVIDENCE_V2_HARNESS_FAILED_CLOSED"
            ),
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_PHYSICAL_TERMINAL_EVIDENCE_HARNESS_V2_VERSION,
            "apply_receipt_sha256": apply_evidence.get("receipt_sha256"),
            "recovery_receipt_sha256": recovery_evidence.get("receipt_sha256"),
            "apply_receipt_valid": apply_valid,
            "recovery_receipt_valid": recovery_valid,
            "wal_and_catalog_record_hashes_distinct": physical_hashes_distinct,
            "protected_repr_verified": protected_repr,
            "temporary_registry_write_observed": bool(
                apply_receipt and apply_receipt.receipt["registry_write"]
            ),
            "recovery_wal_only_write_observed": bool(
                recovery_receipt
                and recovery_receipt.receipt["write_executed"]
                and not recovery_receipt.receipt["registry_write"]
            ),
            "temporary_storage_only": True,
            "synthetic_only": True,
            "durability_verified": False,
            "production_evidence": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


__all__ = ["run_physical_terminal_evidence_harness_v2"]
