"""In-memory harness for the dormant raw physical-storage boundary V1."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_physical_apply_readiness_contract_v2 as readiness
import trade_registry_closed_identity_conflict_repair_raw_physical_apply_readiness_harness_v2 as readiness_harness
import trade_registry_closed_identity_conflict_repair_raw_physical_storage_boundary_contract_v1 as boundary


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RAW-PHYSICAL-STORAGE-BOUNDARY-HARNESS-V1"
)


class SyntheticCasMismatch(RuntimeError):
    """Raised when the injected synthetic snapshot no longer matches."""


class InMemoryDormantPhysicalStorageBoundary:
    """Test double with no filesystem, runtime or physical apply surface."""

    def __init__(self, raw_registry_document: Mapping[str, Any], generation: int = 7) -> None:
        self._source = copy.deepcopy(dict(raw_registry_document))
        self._generation = generation
        self._locked = False
        self._writers_quiesced = False
        self._backups: dict[str, dict[str, Any]] = {}
        self._journal: list[dict[str, Any]] = []

    @property
    def source_document(self) -> dict[str, Any]:
        return copy.deepcopy(self._source)

    @property
    def journal(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._journal)

    @property
    def backups(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._backups)

    def rehearse(
        self,
        transaction: Mapping[str, Any],
        readiness_gate_receipt_sha256: str,
        boundary_spec_sha256: str,
        *,
        expected_generation: int,
    ) -> dict[str, Any]:
        source_before = copy.deepcopy(self._source)
        source_sha = boundary._stable_sha256(source_before)
        expected_sha = transaction.get("source_raw_registry_document_sha256")
        events: list[str] = []
        self._locked = True
        events.append("SYNTHETIC_LOCK_ACQUIRED")
        try:
            self._writers_quiesced = True
            events.append("SYNTHETIC_WRITERS_QUIESCED")
            events.append("SYNTHETIC_EXACT_SOURCE_READ")
            if source_sha != expected_sha or self._generation != expected_generation:
                raise SyntheticCasMismatch("synthetic_compare_and_swap_mismatch")

            content_address = "sha256:" + boundary._stable_sha256(
                {
                    "source_raw_registry_document_sha256": source_sha,
                    "transaction_sha256": transaction["transaction_sha256"],
                }
            )
            backup_value = {
                "raw_registry_document": copy.deepcopy(source_before),
                "transaction_sha256": transaction["transaction_sha256"],
            }
            existing = self._backups.get(content_address)
            if existing is not None and existing != backup_value:
                raise SyntheticCasMismatch("synthetic_immutable_backup_conflict")
            self._backups.setdefault(content_address, backup_value)
            events.append("SYNTHETIC_IMMUTABLE_BACKUP_REHEARSED")
            events.append("SYNTHETIC_CAS_VERIFIED")
            prepared_event = {
                "state": "PREPARED_REHEARSAL_ONLY",
                "transaction_sha256": transaction["transaction_sha256"],
                "idempotency_key": transaction["idempotency_key"],
                "source_raw_registry_document_sha256": source_sha,
                "generation": self._generation,
            }
            matching_events = [
                event
                for event in self._journal
                if event.get("idempotency_key") == transaction["idempotency_key"]
            ]
            if matching_events and matching_events != [prepared_event]:
                raise SyntheticCasMismatch("synthetic_idempotency_conflict")
            if not matching_events:
                self._journal.append(prepared_event)
            events.append("SYNTHETIC_WAL_PREPARED_REHEARSED")
        finally:
            self._writers_quiesced = False
            self._locked = False
            events.append("SYNTHETIC_LOCK_RELEASED")

        receipt = {
            "rehearsal_version": "SYNTHETIC_RAW_PHYSICAL_STORAGE_BOUNDARY_REHEARSAL_V1",
            "transaction_sha256": transaction["transaction_sha256"],
            "readiness_gate_receipt_sha256": readiness_gate_receipt_sha256,
            "boundary_spec_sha256": boundary_spec_sha256,
            "source_raw_registry_document_sha256": source_sha,
            "event_sequence": events,
            "synthetic_lock_exclusive": True,
            "synthetic_all_writers_quiesced": True,
            "synthetic_unknown_writer_count": 0,
            "synthetic_inflight_mutation_count": 0,
            "backup": {
                "content_address": content_address,
                "raw_registry_document_sha256": source_sha,
                "transaction_sha256": transaction["transaction_sha256"],
                "immutable": True,
                "restore_digest_verified": boundary._stable_sha256(
                    self._backups[content_address]["raw_registry_document"]
                )
                == source_sha,
                "synthetic_memory_only": True,
            },
            "compare_and_swap": {
                "source_hash_matched": True,
                "generation_matched": True,
                "verified_under_synthetic_shared_lock": True,
                "fail_closed_on_mismatch": True,
            },
            "journal": {
                "append_only": True,
                "prepared_rehearsal_present": len(self._journal) == 1,
                "candidate_write_event_present": False,
                "commit_event_present": False,
                "synthetic_memory_only": True,
            },
            "durability": {
                "requirements_modeled": True,
                "filesystem_touched": False,
                "temp_file_fsync_executed": False,
                "atomic_replace_executed": False,
                "parent_directory_fsync_executed": False,
                "journal_fsync_executed": False,
            },
            "synthetic_memory_mutation_executed": True,
            "source_document_preserved": self._source == source_before,
            "candidate_persisted": False,
            "apply_entrypoint_present": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_integrated": False,
            "real_storage_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        receipt["rehearsal_sha256"] = (
            boundary.raw_physical_storage_boundary_rehearsal_sha256_v1(receipt)
        )
        return receipt


def build_synthetic_raw_physical_storage_boundary_inputs_v1() -> dict[str, Any]:
    readiness_inputs = readiness_harness.build_synthetic_raw_physical_apply_readiness_inputs_v2()
    readiness_result = readiness.evaluate_closed_identity_conflict_raw_physical_apply_readiness_offline_v2(
        **readiness_inputs
    )
    if readiness_result.get("ok") is not True:
        raise AssertionError("synthetic readiness unexpectedly failed")
    transaction = readiness_inputs["transaction"]
    gate = readiness_result["gate_receipt"]
    spec = {
        "spec_version": "DORMANT_RAW_PHYSICAL_STORAGE_BOUNDARY_SPEC_V1",
        "transaction_sha256": transaction["transaction_sha256"],
        "readiness_gate_receipt_sha256": gate["gate_receipt_sha256"],
        "capabilities": {
            "exact_raw_loader": True,
            "shared_interprocess_lock": True,
            "writer_quiescence": True,
            "immutable_versioned_backup": True,
            "generation_and_hash_cas": True,
            "append_only_wal": True,
            "file_and_directory_fsync": True,
            "atomic_same_directory_replace": True,
            "rollback_recovery": True,
        },
        "shared_lock_contract": {
            "all_registry_writers_same_namespace": True,
            "exclusive": True,
            "interprocess": True,
            "bounded_timeout": True,
            "fail_closed_on_timeout": True,
        },
        "writer_quiescence_contract": {
            "complete_inventory_required": True,
            "lease_epoch_required": True,
            "all_writers_ack_required": True,
            "zero_inflight_mutations_required": True,
            "fail_closed_on_unknown_writer": True,
        },
        "backup_contract": {
            "content_addressed": True,
            "immutable": True,
            "versioned": True,
            "transaction_bound": True,
            "restore_digest_required": True,
            "durability_confirmation_required": True,
        },
        "compare_and_swap_contract": {
            "expected_raw_document_sha256": transaction["source_raw_registry_document_sha256"],
            "expected_snapshot_envelope_sha256": transaction["source_snapshot_envelope_sha256"],
            "generation_token_required": True,
            "verified_under_shared_lock": True,
            "fail_closed_on_mismatch": True,
        },
        "journal_contract": {
            "append_only": True,
            "transaction_sha256": transaction["transaction_sha256"],
            "idempotency_key": transaction["idempotency_key"],
            "prepared_before_candidate": True,
            "commit_after_durable_replace": True,
            "recovery_state_required": True,
        },
        "durability_contract": {
            "same_directory_temp": True,
            "temp_file_fsync": True,
            "atomic_replace": True,
            "parent_directory_fsync": True,
            "journal_fsync": True,
        },
        "recovery_contract": {
            "rollback_preimage_required": True,
            "partial_state_detection_required": True,
            "candidate_already_present_detection_required": True,
            "manual_recovery_on_ambiguity": True,
        },
        "safety_envelope": {
            "contract_only": True,
            "apply_entrypoint_present": False,
            "real_storage_accessed": False,
            "real_lock_acquired": False,
            "real_writers_quiesced": False,
            "real_backup_created": False,
            "real_cas_executed": False,
            "real_journal_written": False,
            "real_fsync_executed": False,
            "production_apply_authorized": False,
        },
    }
    spec["spec_sha256"] = boundary.raw_physical_storage_boundary_spec_sha256_v1(spec)
    source_document = transaction["backup_envelope"]["snapshot"]["raw_registry_document"]
    storage = InMemoryDormantPhysicalStorageBoundary(source_document)
    rehearsal_receipt = storage.rehearse(
        transaction,
        gate["gate_receipt_sha256"],
        spec["spec_sha256"],
        expected_generation=7,
    )
    return {
        "transaction": transaction,
        "readiness_result": readiness_result,
        "boundary_spec": spec,
        "rehearsal_receipt": rehearsal_receipt,
    }


def run_synthetic_raw_physical_storage_boundary_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_raw_physical_storage_boundary_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = boundary._stable_sha256(before)
    first = boundary.evaluate_closed_identity_conflict_raw_physical_storage_boundary_offline_v1(
        **inputs
    )
    second = boundary.evaluate_closed_identity_conflict_raw_physical_storage_boundary_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = boundary._stable_sha256(inputs)
    receipt = first.get("boundary_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("boundary_contract_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("physical_apply_entrypoint_present") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "RAW_PHYSICAL_STORAGE_BOUNDARY_V1_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "RAW_PHYSICAL_STORAGE_BOUNDARY_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_HARNESS_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "physical_apply_entrypoint_present": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "boundary_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RAW_PHYSICAL_STORAGE_BOUNDARY_HARNESS_V1_VERSION",
    "InMemoryDormantPhysicalStorageBoundary",
    "SyntheticCasMismatch",
    "build_synthetic_raw_physical_storage_boundary_inputs_v1",
    "run_synthetic_raw_physical_storage_boundary_harness_v1",
]
