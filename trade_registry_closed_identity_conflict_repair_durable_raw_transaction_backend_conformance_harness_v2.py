"""In-memory harness for DurableRawTransactionBackendV2 conformance."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as contract


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_HARNESS_V2_VERSION = (
    "2026-09-07-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-DURABLE-RAW-TRANSACTION-BACKEND-CONFORMANCE-HARNESS-V2"
)
SYNTHETIC_NOW_V2 = 1_788_700_000


def _sha(label: str) -> str:
    return contract.stable_sha256_v2({"synthetic_label": label})


def _seal(value: dict[str, Any], field: str) -> dict[str, Any]:
    value[field] = contract.stable_sha256_v2(
        {key: item for key, item in value.items() if key != field}
    )
    return value


class InMemoryEvidenceDurableRawTransactionBackendV2:
    """Synthetic evidence double; never performs I/O or claims durability."""

    def __init__(self, *, prepared_count: int = 2) -> None:
        self.calls: list[str] = []
        self._snapshot = self._build_snapshot()
        self._evidence = self._build_evidence()
        self._catalog = self._build_catalog(prepared_count)

    def _build_snapshot(self) -> dict[str, Any]:
        return _seal(
            {
                "snapshot_version": contract.BACKEND_SNAPSHOT_VERSION_V2,
                "backend_kind": "IN_MEMORY_EVIDENCE_BACKEND_V2",
                "backend_instance_sha256": _sha("backend-instance-v2"),
                "backend_module_source_sha256": _sha("backend-module-source-v2"),
                "registry_path_binding_sha256": _sha("synthetic-registry-path-v2"),
                "lock_namespace_sha256": _sha("synthetic-lock-namespace-v2"),
                "generation": 7,
                "synthetic_only": True,
                "durable": False,
                "production_evidence": False,
                "filesystem_accessed": False,
            },
            "snapshot_sha256",
        )

    def _build_evidence(self) -> list[dict[str, Any]]:
        return [
            _seal(
                {
                    "evidence_version": contract.CAPABILITY_EVIDENCE_VERSION_V2,
                    "capability": capability,
                    "backend_instance_sha256": self._snapshot["backend_instance_sha256"],
                    "backend_snapshot_sha256": self._snapshot["snapshot_sha256"],
                    "fixture_binding_sha256": _sha(f"fixture:{capability}"),
                    "probe_kind": "DETERMINISTIC_IN_MEMORY_FAULT_INJECTION",
                    "observed": True,
                    "synthetic_only": True,
                    "durable": False,
                    "production_evidence": False,
                    "filesystem_accessed": False,
                },
                "evidence_sha256",
            )
            for capability in contract.REQUIRED_CAPABILITIES_V2
        ]

    def _build_record(self, index: int) -> dict[str, Any]:
        return _seal(
            {
                "record_version": contract.PREPARED_RECORD_VERSION_V2,
                "request_sha256": _sha(f"original-request:{index}"),
                "transaction_sha256": _sha(f"transaction:{index}"),
                "original_invocation_command_sha256": _sha(f"invocation-command:{index}"),
                "authorization_receipt_sha256": _sha(f"authorization-receipt:{index}"),
                "backend_instance_sha256": self._snapshot["backend_instance_sha256"],
                "registry_path_binding_sha256": self._snapshot["registry_path_binding_sha256"],
                "lock_namespace_sha256": self._snapshot["lock_namespace_sha256"],
                "source_raw_document_sha256": _sha(f"source-document:{index}"),
                "candidate_raw_document_sha256": _sha(f"candidate-document:{index}"),
                "wal_prepared_record_sha256": _sha(f"wal-prepared-record:{index}"),
                "previous_maintenance_epoch": _sha(f"previous-maintenance:{index}"),
                "prepared_at_epoch": SYNTHETIC_NOW_V2 - 100 + index,
                "deadline_epoch": SYNTHETIC_NOW_V2 + 300,
                "terminal_state": "PREPARED",
                "synthetic_only": True,
                "durable": False,
                "production_evidence": False,
            },
            "record_sha256",
        )

    def _build_catalog(self, prepared_count: int) -> dict[str, Any]:
        records = sorted(
            (self._build_record(index) for index in range(prepared_count)),
            key=lambda item: item["record_sha256"],
        )
        return _seal(
            {
                "catalog_version": contract.PREPARED_CATALOG_VERSION_V2,
                "backend_instance_sha256": self._snapshot["backend_instance_sha256"],
                "backend_snapshot_sha256": self._snapshot["snapshot_sha256"],
                "registry_path_binding_sha256": self._snapshot["registry_path_binding_sha256"],
                "lock_namespace_sha256": self._snapshot["lock_namespace_sha256"],
                "generation": self._snapshot["generation"],
                "records": records,
                "record_count": len(records),
                "prepared_count": len(records),
                "synthetic_only": True,
                "durable": False,
                "production_evidence": False,
            },
            "catalog_sha256",
        )

    def snapshot_offline(self) -> Mapping[str, Any]:
        self.calls.append("snapshot_offline")
        return copy.deepcopy(self._snapshot)

    def capability_evidence_offline(self) -> list[Mapping[str, Any]]:
        self.calls.append("capability_evidence_offline")
        return copy.deepcopy(self._evidence)

    def list_prepared_transactions_offline(self) -> Mapping[str, Any]:
        self.calls.append("list_prepared_transactions_offline")
        return copy.deepcopy(self._catalog)

    def apply_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append("apply_attested_transaction_offline")
        return build_synthetic_transaction_result_v2(request)

    def reconcile_attested_transaction_offline(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append("reconcile_attested_transaction_offline")
        return build_synthetic_recovery_result_v2(request)


def build_synthetic_transaction_request_v2(
    snapshot: Mapping[str, Any], *, deadline_epoch: int = SYNTHETIC_NOW_V2 + 30
) -> dict[str, Any]:
    candidate_raw = '{"closed_trades":[],"generation":8}'
    return _seal(
        {
            "request_version": contract.TRANSACTION_REQUEST_VERSION_V2,
            "backend_instance_sha256": snapshot["backend_instance_sha256"],
            "backend_snapshot_sha256": snapshot["snapshot_sha256"],
            "registry_path_binding_sha256": snapshot["registry_path_binding_sha256"],
            "lock_namespace_sha256": snapshot["lock_namespace_sha256"],
            "request_sha256": _sha("protected-original-request-v2"),
            "transaction_sha256": _sha("protected-transaction-v2"),
            "idempotency_key": "synthetic-idempotency-key-v2",
            "authorization_receipt_sha256": _sha("protected-authorization-receipt-v2"),
            "maintenance_epoch": _sha("protected-maintenance-epoch-v2"),
            "expected_generation": snapshot["generation"],
            "expected_raw_document_sha256": _sha("protected-source-document-v2"),
            "candidate_raw_document_utf8": candidate_raw,
            "candidate_raw_document_sha256": contract.raw_utf8_sha256_v2(candidate_raw),
            "deadline_epoch": deadline_epoch,
            "synthetic_only": True,
            "production_authority": False,
        },
        "request_binding_sha256",
    )


def build_synthetic_transaction_result_v2(request: Mapping[str, Any]) -> dict[str, Any]:
    return _seal(
        {
            "result_version": contract.TRANSACTION_RESULT_VERSION_V2,
            "request_binding_sha256": request["request_binding_sha256"],
            "request_sha256": request["request_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "backend_snapshot_sha256": request["backend_snapshot_sha256"],
            "prepared_record_sha256": _sha("synthetic-apply-prepared-record-v2"),
            "terminal_record_sha256": _sha("synthetic-apply-terminal-record-v2"),
            "terminal_state": "COMMITTED",
            "generation_before": request["expected_generation"],
            "generation_after": request["expected_generation"] + 1,
            "deadline_epoch": request["deadline_epoch"],
            "deadline_observed": True,
            "postconditions_verified": True,
            "recovery_required": False,
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        },
        "result_sha256",
    )


def build_synthetic_recovery_request_v2(
    record: Mapping[str, Any], batch: Mapping[str, Any], *, checkpoint_index: int
) -> dict[str, Any]:
    return _seal(
        {
            "request_version": contract.RECOVERY_REQUEST_VERSION_V2,
            "batch_epoch": batch["batch_epoch"],
            "batch_plan_sha256": batch["batch_plan_sha256"],
            "catalog_sha256": batch["catalog_sha256"],
            "prepared_record_sha256": record["record_sha256"],
            "wal_prepared_record_sha256": record["wal_prepared_record_sha256"],
            "original_request_sha256": record["request_sha256"],
            "original_invocation_command_sha256": record["original_invocation_command_sha256"],
            "original_authorization_receipt_sha256": record["authorization_receipt_sha256"],
            "recovery_authorization_receipt_sha256": _sha(f"recovery-authorization:{checkpoint_index}"),
            "transaction_sha256": record["transaction_sha256"],
            "backend_instance_sha256": record["backend_instance_sha256"],
            "backend_snapshot_sha256": batch["backend_snapshot_sha256"],
            "registry_path_binding_sha256": record["registry_path_binding_sha256"],
            "lock_namespace_sha256": record["lock_namespace_sha256"],
            "source_raw_document_sha256": record["source_raw_document_sha256"],
            "candidate_raw_document_sha256": record["candidate_raw_document_sha256"],
            "previous_maintenance_epoch": record["previous_maintenance_epoch"],
            "fresh_maintenance_epoch": _sha(f"fresh-maintenance:{checkpoint_index}"),
            "deadline_epoch": batch["deadline_epoch"],
            "checkpoint_index": checkpoint_index,
            "synthetic_only": True,
            "production_authority": False,
        },
        "request_sha256",
    )


def build_synthetic_recovery_result_v2(request: Mapping[str, Any]) -> dict[str, Any]:
    return _seal(
        {
            "result_version": contract.RECOVERY_RESULT_VERSION_V2,
            "recovery_request_sha256": request["request_sha256"],
            "batch_epoch": request["batch_epoch"],
            "batch_plan_sha256": request["batch_plan_sha256"],
            "catalog_sha256": request["catalog_sha256"],
            "prepared_record_sha256": request["prepared_record_sha256"],
            "wal_prepared_record_sha256": request["wal_prepared_record_sha256"],
            "transaction_sha256": request["transaction_sha256"],
            "backend_instance_sha256": request["backend_instance_sha256"],
            "terminal_state": "ROLLED_BACK",
            "terminal_record_sha256": _sha(f"synthetic-recovery-terminal:{request['prepared_record_sha256']}"),
            "deadline_epoch": request["deadline_epoch"],
            "deadline_observed": True,
            "postconditions_verified": True,
            "checkpoint_index": request["checkpoint_index"],
            "synthetic_only": True,
            "durable": False,
            "production_evidence": False,
            "write_executed": False,
            "registry_write": False,
        },
        "result_sha256",
    )


def run_durable_raw_transaction_backend_conformance_harness_v2() -> dict[str, Any]:
    backend = InMemoryEvidenceDurableRawTransactionBackendV2(prepared_count=2)
    auditor = contract.DurableRawTransactionBackendConformanceV2(
        contract.DurableRawTransactionBackendConformanceConfigV2(
            enabled=True,
            scope_attestation=contract.OFFLINE_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_SCOPE_V2,
        )
    )
    audit = auditor.audit_offline(backend)
    snapshot = backend.snapshot_offline()
    catalog = backend.list_prepared_transactions_offline()
    transaction_request = build_synthetic_transaction_request_v2(snapshot)
    transaction_result = backend.apply_attested_transaction_offline(transaction_request)
    transaction_valid = bool(
        contract.transaction_request_valid_v2(transaction_request, snapshot)
        and contract.transaction_result_valid_v2(transaction_result, transaction_request)
    )

    batch = contract.build_resumable_recovery_batch_offline_v2(
        snapshot,
        catalog,
        batch_epoch=_sha("resumable-recovery-batch-epoch-v2"),
        deadline_epoch=SYNTHETIC_NOW_V2 + 60,
    )
    recovery_valid = True
    checkpoint_hashes: list[str] = [batch["batch_plan_sha256"]]
    while not batch["complete"]:
        index = batch["next_index"]
        record_by_hash = {record["record_sha256"]: record for record in catalog["records"]}
        record = record_by_hash[batch["item_record_sha256s"][index]]
        recovery_request = build_synthetic_recovery_request_v2(record, batch, checkpoint_index=index)
        recovery_result = dict(backend.reconcile_attested_transaction_offline(recovery_request))
        recovery_valid = bool(
            recovery_valid
            and contract.recovery_request_valid_v2(recovery_request, record, batch)
            and contract.recovery_result_valid_v2(recovery_result, recovery_request, index)
        )
        batch = contract.advance_recovery_batch_offline_v2(batch, recovery_result)
        checkpoint_hashes.append(batch["batch_plan_sha256"])

    ok = bool(
        audit.get("ok") is True
        and transaction_valid
        and recovery_valid
        and contract.recovery_batch_valid_v2(batch)
        and batch["complete"] is True
        and len(set(checkpoint_hashes)) == 3
    )
    return {
        "ok": ok,
        "status": (
            "DURABLE_BACKEND_V2_CONFORMANCE_HARNESS_PASSED_OFFLINE"
            if ok else "DURABLE_BACKEND_V2_CONFORMANCE_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_DURABLE_RAW_TRANSACTION_BACKEND_CONFORMANCE_HARNESS_V2_VERSION,
        "audit_report_sha256": audit.get("report_sha256"),
        "backend_snapshot_sha256": snapshot["snapshot_sha256"],
        "prepared_catalog_sha256": catalog["catalog_sha256"],
        "prepared_count": catalog["prepared_count"],
        "capability_count": len(contract.REQUIRED_CAPABILITIES_V2),
        "exact_transaction_contract_verified": transaction_valid,
        "resumable_recovery_verified": recovery_valid and batch["complete"],
        "checkpoint_count": len(checkpoint_hashes),
        "synthetic_only": True,
        "durable": False,
        "production_evidence": False,
        "production_ready": False,
        "runtime_integrated": False,
        "activation_allowed": False,
        "live_allowed": False,
        "real_registry_accessed": False,
        "filesystem_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "write_executed": False,
        "no_order_sent": True,
    }


__all__ = [
    "InMemoryEvidenceDurableRawTransactionBackendV2", "SYNTHETIC_NOW_V2",
    "build_synthetic_recovery_request_v2", "build_synthetic_recovery_result_v2",
    "build_synthetic_transaction_request_v2", "build_synthetic_transaction_result_v2",
    "run_durable_raw_transaction_backend_conformance_harness_v2",
]
