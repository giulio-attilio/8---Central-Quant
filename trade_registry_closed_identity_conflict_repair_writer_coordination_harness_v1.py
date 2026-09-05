"""In-memory harness for dormant coordination of all 19 Registry writers."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_raw_physical_storage_boundary_contract_v1 as storage_boundary
import trade_registry_closed_identity_conflict_repair_raw_physical_storage_boundary_harness_v1 as storage_boundary_harness
import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-COORDINATION-HARNESS-V1"
)


class SyntheticWriterCoordinationBlocked(RuntimeError):
    """Fail-closed outcome from the synthetic coordinator."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantWriterCoordinator:
    """Synthetic maintenance coordinator with no runtime or I/O surface."""

    def __init__(self, writer_ids: Iterable[str]) -> None:
        self._writer_ids = tuple(str(writer_id) for writer_id in writer_ids)
        self._event_sequence: list[str] = []
        self._lock_held = False
        self._lease_active = False

    @property
    def event_sequence(self) -> list[str]:
        return list(self._event_sequence)

    @property
    def lock_held(self) -> bool:
        return self._lock_held

    @property
    def lease_active(self) -> bool:
        return self._lease_active

    def rehearse(
        self,
        *,
        boundary_result: Mapping[str, Any],
        coordination_spec: Mapping[str, Any],
        unknown_writer_ids: Iterable[str] = (),
        missing_ack_ids: Iterable[str] = (),
        stale_epoch_ids: Iterable[str] = (),
        inflight_by_writer: Mapping[str, int] | None = None,
        lock_available: bool = True,
    ) -> dict[str, Any]:
        self._event_sequence = []
        unknown = tuple(str(value) for value in unknown_writer_ids)
        missing = {str(value) for value in missing_ack_ids}
        stale = {str(value) for value in stale_epoch_ids}
        inflight = {
            str(key): int(value)
            for key, value in dict(inflight_by_writer or {}).items()
        }
        if len(self._writer_ids) != 19 or len(set(self._writer_ids)) != 19:
            raise SyntheticWriterCoordinationBlocked("WRITER_INVENTORY_NOT_CLOSED")
        expected_ids = tuple(
            item["writer_id"]
            for item in coordination.canonical_closed_repair_writer_inventory_v1()
        )
        if self._writer_ids != expected_ids:
            raise SyntheticWriterCoordinationBlocked("WRITER_INVENTORY_NOT_CANONICAL")
        self._event_sequence.append("WRITER_INVENTORY_BOUND")
        if unknown:
            raise SyntheticWriterCoordinationBlocked("UNKNOWN_WRITER_PRESENT")

        boundary_receipt = boundary_result.get("boundary_receipt")
        if not isinstance(boundary_receipt, Mapping):
            raise SyntheticWriterCoordinationBlocked("UPSTREAM_BOUNDARY_RECEIPT_MISSING")
        boundary_sha = str(boundary_receipt.get("boundary_receipt_sha256") or "")
        transaction_sha = str(boundary_receipt.get("transaction_sha256") or "")
        spec_sha = str(coordination_spec.get("spec_sha256") or "")
        inventory_sha = str(coordination_spec.get("writer_inventory_sha256") or "")
        lock_protocol = coordination_spec.get("shared_lock_protocol")
        namespace_sha = (
            str(lock_protocol.get("lock_namespace_sha256") or "")
            if isinstance(lock_protocol, Mapping)
            else ""
        )
        epoch = coordination._stable_sha256(
            {
                "transaction_sha256": transaction_sha,
                "writer_inventory_sha256": inventory_sha,
                "lock_namespace_sha256": namespace_sha,
                "lease_ordinal": 1,
            }
        )

        self._lease_active = True
        self._event_sequence.append("MAINTENANCE_LEASE_REQUESTED")
        self._event_sequence.append("NEW_WRITES_FENCED")
        try:
            if missing:
                raise SyntheticWriterCoordinationBlocked("WRITER_ACK_MISSING")
            if stale:
                raise SyntheticWriterCoordinationBlocked("WRITER_ACK_STALE_EPOCH")
            acknowledgements = [
                {
                    "writer_id": writer_id,
                    "lease_epoch": epoch,
                    "new_mutations_fenced": True,
                    "inflight_mutations": inflight.get(writer_id, 0),
                    "acknowledged": True,
                }
                for writer_id in self._writer_ids
            ]
            self._event_sequence.append("ALL_WRITERS_ACKNOWLEDGED")
            if any(item["inflight_mutations"] != 0 for item in acknowledgements):
                raise SyntheticWriterCoordinationBlocked("INFLIGHT_MUTATIONS_NOT_DRAINED")
            self._event_sequence.append("ZERO_INFLIGHT_CONFIRMED")
            if not lock_available:
                raise SyntheticWriterCoordinationBlocked("SHARED_LOCK_TIMEOUT")
            self._lock_held = True
            self._event_sequence.append("SYNTHETIC_SHARED_LOCK_ACQUIRED")
            self._event_sequence.append("STORAGE_BOUNDARY_PREFLIGHT_REHEARSED")
            self._lock_held = False
            self._event_sequence.append("SYNTHETIC_SHARED_LOCK_RELEASED")
        finally:
            if self._lock_held:
                self._lock_held = False
                self._event_sequence.append("SYNTHETIC_SHARED_LOCK_RELEASED")
            self._lease_active = False
            self._event_sequence.append("MAINTENANCE_LEASE_RELEASED")

        receipt = {
            "rehearsal_version": "SYNTHETIC_CLOSED_REPAIR_WRITER_COORDINATION_REHEARSAL_V1",
            "upstream_boundary_receipt_sha256": boundary_sha,
            "transaction_sha256": transaction_sha,
            "coordination_spec_sha256": spec_sha,
            "writer_inventory_sha256": inventory_sha,
            "writer_count": len(self._writer_ids),
            "event_sequence": list(self._event_sequence),
            "writer_acknowledgements": acknowledgements,
            "writer_acknowledgements_sha256": coordination._stable_sha256(
                acknowledgements
            ),
            "maintenance_lease": {
                "epoch": epoch,
                "initial_state": "REQUESTED",
                "drain_state": "DRAINING",
                "quiesced_state": "QUIESCED",
                "final_state": "RELEASED",
                "new_mutations_fenced": True,
                "unknown_writer_count": 0,
                "missing_ack_count": 0,
                "stale_epoch_count": 0,
                "inflight_mutation_count": 0,
            },
            "shared_lock": {
                "lock_namespace_sha256": namespace_sha,
                "synthetic_acquired": True,
                "synthetic_released": True,
                "acquired_after_quiescence": True,
                "released_before_lease": True,
                "fail_closed_on_timeout": True,
                "real_lock_acquired": False,
            },
            "storage_boundary_preflight": {
                "boundary_contract_verified": boundary_result.get(
                    "boundary_contract_verified"
                )
                is True,
                "production_ready": False,
                "apply_allowed": False,
                "physical_apply_entrypoint_present": False,
                "candidate_materialized": False,
            },
            "safety_envelope": {
                "synthetic_memory_only": True,
                "real_writer_contacted": False,
                "real_registry_accessed": False,
                "filesystem_accessed": False,
                "network_accessed": False,
                "runtime_integrated": False,
                "write_executed": False,
                "registry_write": False,
                "apply_entrypoint_present": False,
                "broker_called": False,
                "no_order_sent": True,
            },
        }
        receipt["rehearsal_sha256"] = (
            coordination.closed_repair_writer_coordination_rehearsal_sha256_v1(
                receipt
            )
        )
        return receipt


def build_synthetic_closed_repair_writer_coordination_inputs_v1() -> dict[str, Any]:
    boundary_inputs = (
        storage_boundary_harness.build_synthetic_raw_physical_storage_boundary_inputs_v1()
    )
    boundary_result = storage_boundary.evaluate_closed_identity_conflict_raw_physical_storage_boundary_offline_v1(
        **boundary_inputs
    )
    if boundary_result.get("ok") is not True:
        raise AssertionError("synthetic storage boundary unexpectedly failed")
    boundary_receipt = boundary_result["boundary_receipt"]
    inventory = coordination.canonical_closed_repair_writer_inventory_v1()
    inventory_sha = coordination._stable_sha256(inventory)
    authority = {
        "authority_id": "SYNTHETIC_RAW_REGISTRY_AUTHORITY_V1",
        "synthetic_only": True,
        "canonical_runtime_path_required_later": True,
    }
    authority_sha = coordination._stable_sha256(authority)
    authority["authority_sha256"] = authority_sha
    authority["real_path_observed"] = False
    namespace_sha = coordination._stable_sha256(
        {
            "authority_sha256": authority_sha,
            "purpose": "TRADE_REGISTRY_FULL_RMW_COORDINATION",
        }
    )
    writer_ids = [item["writer_id"] for item in inventory]
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_WRITER_COORDINATION_SPEC_V1",
        "upstream_boundary_receipt_sha256": boundary_receipt[
            "boundary_receipt_sha256"
        ],
        "transaction_sha256": boundary_receipt["transaction_sha256"],
        "writer_inventory": inventory,
        "writer_inventory_sha256": inventory_sha,
        "storage_authority": authority,
        "shared_lock_protocol": {
            "namespace_derivation": "SHA256_CANONICAL_STORAGE_AUTHORITY_V1",
            "lock_namespace_sha256": namespace_sha,
            "covered_writer_ids": writer_ids,
            "exclusive": True,
            "interprocess": True,
            "reentrant_within_owner": True,
            "bounded_timeout": True,
            "fail_closed_on_timeout": True,
            "scope": "READ_THROUGH_DURABLE_COMMIT_OR_ABORT",
        },
        "maintenance_lease_protocol": {
            "states": ["REQUESTED", "DRAINING", "QUIESCED", "RELEASED"],
            "epoch_bound": True,
            "new_mutations_fenced_while_active": True,
            "all_registered_writers_ack_required": True,
            "zero_inflight_required": True,
            "unknown_writer_fails_closed": True,
            "missing_ack_fails_closed": True,
            "stale_epoch_fails_closed": True,
            "release_requires_lock_released": True,
        },
        "writer_mutation_protocol": {
            "register_before_mutation": True,
            "lease_check_before_read": True,
            "increment_inflight_before_read": True,
            "shared_lock_before_read": True,
            "decrement_inflight_after_commit_or_abort": True,
            "ack_only_at_zero_inflight": True,
            "normalization_forbidden_for_raw_repair": True,
        },
        "safety_envelope": {
            "contract_only": True,
            "runtime_install_allowed": False,
            "real_writer_contacted": False,
            "real_lease_issued": False,
            "real_lock_acquired": False,
            "real_registry_accessed": False,
            "apply_entrypoint_present": False,
            "production_apply_authorized": False,
        },
    }
    spec["spec_sha256"] = coordination.closed_repair_writer_coordination_spec_sha256_v1(
        spec
    )
    coordinator = InMemoryDormantWriterCoordinator(writer_ids)
    rehearsal_receipt = coordinator.rehearse(
        boundary_result=boundary_result,
        coordination_spec=spec,
    )
    return {
        "storage_boundary_result": boundary_result,
        "coordination_spec": spec,
        "rehearsal_receipt": rehearsal_receipt,
    }


def run_synthetic_closed_repair_writer_coordination_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_writer_coordination_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = coordination._stable_sha256(before)
    first = coordination.evaluate_closed_repair_writer_coordination_offline_v1(
        **inputs
    )
    second = coordination.evaluate_closed_repair_writer_coordination_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = coordination._stable_sha256(inputs)
    receipt = first.get("coordination_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("coordination_contract_verified") is True
        and first.get("synthetic_rehearsal_valid") is True
        and first.get("production_ready") is False
        and first.get("apply_allowed") is False
        and first.get("runtime_install_allowed") is False
        and first.get("write_executed") is False
        and first.get("registry_write") is False
        and isinstance(receipt, Mapping)
        and receipt.get("writer_count") == 19
        and receipt.get("production_blockers")
        and inputs == before
        and before_sha == after_sha
        and first == second
    )
    return {
        "ok": ok,
        "status": (
            "CLOSED_REPAIR_WRITER_COORDINATION_V1_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "CLOSED_REPAIR_WRITER_COORDINATION_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_HARNESS_V1_VERSION,
        "dormant": True,
        "offline_only": True,
        "synthetic_only": True,
        "production_ready": False,
        "apply_allowed": False,
        "runtime_install_allowed": False,
        "write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "broker_called": False,
        "no_order_sent": True,
        "input_preserved": inputs == before and before_sha == after_sha,
        "deterministic": first == second,
        "coordination_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_COORDINATION_HARNESS_V1_VERSION",
    "InMemoryDormantWriterCoordinator",
    "SyntheticWriterCoordinationBlocked",
    "build_synthetic_closed_repair_writer_coordination_inputs_v1",
    "run_synthetic_closed_repair_writer_coordination_harness_v1",
]
