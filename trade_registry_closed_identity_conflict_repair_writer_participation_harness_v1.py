"""In-memory harness for all dormant CLOSED repair writer participants."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_coordination_harness_v1 as coordination_harness
import trade_registry_closed_identity_conflict_repair_writer_participation_contract_v1 as participation


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_HARNESS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-PARTICIPATION-HARNESS-V1"
)


class SyntheticWriterParticipationBlocked(RuntimeError):
    """Fail-closed result from one synthetic writer participant."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryDormantWriterParticipant:
    """Protocol-only participant that never binds or invokes a real callable."""

    def __init__(
        self,
        binding: Mapping[str, Any],
        *,
        transaction_sha256: str,
        maintenance_epoch: str,
    ) -> None:
        self._binding = copy.deepcopy(dict(binding))
        self._transaction_sha = str(transaction_sha256)
        self._maintenance_epoch = str(maintenance_epoch)
        self._inflight = 0
        self._lock_held = False

    @property
    def inflight(self) -> int:
        return self._inflight

    @property
    def lock_held(self) -> bool:
        return self._lock_held

    def rehearse(
        self,
        *,
        normal_lease_active: bool = False,
        maintenance_inflight: int = 0,
        lock_available: bool = True,
        registration_token: str | None = None,
    ) -> dict[str, Any]:
        writer = self._binding.get("writer")
        if not isinstance(writer, Mapping):
            raise SyntheticWriterParticipationBlocked("WRITER_BINDING_INVALID")
        expected_registration = str(self._binding.get("registration_token") or "")
        supplied_registration = (
            expected_registration
            if registration_token is None
            else str(registration_token)
        )
        if supplied_registration != expected_registration:
            raise SyntheticWriterParticipationBlocked("REGISTRATION_TOKEN_INVALID")
        if normal_lease_active:
            raise SyntheticWriterParticipationBlocked("NORMAL_MUTATION_FENCED_BY_LEASE")
        if int(maintenance_inflight) != 0:
            raise SyntheticWriterParticipationBlocked("LEASE_ACK_REQUIRES_ZERO_INFLIGHT")
        if not lock_available:
            raise SyntheticWriterParticipationBlocked("SYNTHETIC_SHARED_LOCK_TIMEOUT")

        namespace_sha = str(self._binding.get("lock_namespace_sha256") or "")
        inflight_token = participation._inflight_token(
            expected_registration, self._transaction_sha
        )
        lock_token = participation._lock_token(inflight_token, namespace_sha)
        self._inflight = 1
        self._lock_held = True
        self._lock_held = False
        self._inflight = 0
        lease_ack_token = participation._lease_ack_token(
            expected_registration, self._maintenance_epoch
        )
        receipt = {
            "receipt_version": "SYNTHETIC_CLOSED_REPAIR_WRITER_PARTICIPANT_RECEIPT_V1",
            "writer_id": writer["writer_id"],
            "registration_token": expected_registration,
            "normal_cycle": {
                "event_sequence": [
                    "WRITER_REGISTERED",
                    "MAINTENANCE_LEASE_ABSENT",
                    "INFLIGHT_TOKEN_ISSUED",
                    "SYNTHETIC_SHARED_LOCK_ACQUIRED",
                    "WRITER_OPERATION_NOT_INVOKED_CONTRACT_ONLY",
                    "SYNTHETIC_SHARED_LOCK_RELEASED",
                    "INFLIGHT_TOKEN_COMPLETED",
                ],
                "maintenance_lease_active": False,
                "mutation_admitted": True,
                "inflight_before": 0,
                "inflight_during": 1,
                "inflight_after": 0,
                "inflight_token": inflight_token,
                "lock_namespace_sha256": namespace_sha,
                "lock_token": lock_token,
                "synthetic_lock_acquired": True,
                "synthetic_lock_released": True,
                "writer_operation_executed": False,
            },
            "maintenance_cycle": {
                "event_sequence": [
                    "WRITER_REGISTERED",
                    "MAINTENANCE_LEASE_OBSERVED",
                    "NEW_MUTATION_FENCED",
                    "ZERO_INFLIGHT_CONFIRMED",
                    "LEASE_ACK_TOKEN_ISSUED",
                ],
                "maintenance_lease_active": True,
                "maintenance_epoch": self._maintenance_epoch,
                "new_mutation_admitted": False,
                "inflight_mutations": 0,
                "lease_ack_token": lease_ack_token,
                "lease_acknowledged": True,
                "shared_lock_attempted": False,
                "writer_operation_executed": False,
            },
            "safety_envelope": {
                "synthetic_memory_only": True,
                "runtime_callable_bound": False,
                "real_token_issued": False,
                "real_lock_acquired": False,
                "real_writer_called": False,
                "real_registry_accessed": False,
                "filesystem_accessed": False,
                "network_accessed": False,
                "write_executed": False,
                "registry_write": False,
                "no_order_sent": True,
            },
        }
        receipt["participant_receipt_sha256"] = (
            participation.writer_participant_receipt_sha256_v1(receipt)
        )
        return receipt


def build_synthetic_closed_repair_writer_participation_inputs_v1() -> dict[str, Any]:
    coordination_inputs = (
        coordination_harness.build_synthetic_closed_repair_writer_coordination_inputs_v1()
    )
    coordination_result = coordination.evaluate_closed_repair_writer_coordination_offline_v1(
        **coordination_inputs
    )
    if coordination_result.get("ok") is not True:
        raise AssertionError("synthetic writer coordination unexpectedly failed")
    coordination_receipt = coordination_result["coordination_receipt"]
    bindings = participation.canonical_writer_participation_bindings_v1(
        coordination_receipt
    )
    spec = {
        "spec_version": "DORMANT_CLOSED_REPAIR_WRITER_PARTICIPATION_SPEC_V1",
        "upstream_coordination_receipt_sha256": coordination_receipt[
            "coordination_receipt_sha256"
        ],
        "transaction_sha256": coordination_receipt["transaction_sha256"],
        "writer_bindings": bindings,
        "writer_bindings_sha256": participation._stable_sha256(bindings),
        "individual_protocol": {
            "registration_token_required": True,
            "lease_check_before_inflight": True,
            "active_lease_fences_new_mutation": True,
            "inflight_token_single_use": True,
            "lock_token_requires_inflight_token": True,
            "lock_namespace_must_match_coordination": True,
            "lock_release_before_inflight_completion": True,
            "lease_ack_requires_zero_inflight": True,
            "writer_callable_absent": True,
            "fail_closed_on_unknown_token": True,
        },
        "safety_envelope": {
            "contract_only": True,
            "runtime_writer_bound": False,
            "real_token_issued": False,
            "real_lock_acquired": False,
            "real_writer_called": False,
            "real_registry_accessed": False,
            "runtime_install_allowed": False,
            "apply_entrypoint_present": False,
        },
    }
    spec["spec_sha256"] = participation.writer_participation_spec_sha256_v1(spec)
    maintenance_epoch = participation._maintenance_epoch(
        coordination_receipt["transaction_sha256"],
        coordination_receipt["writer_inventory_sha256"],
        coordination_receipt["lock_namespace_sha256"],
    )
    receipts = [
        InMemoryDormantWriterParticipant(
            binding,
            transaction_sha256=coordination_receipt["transaction_sha256"],
            maintenance_epoch=maintenance_epoch,
        ).rehearse()
        for binding in bindings
    ]
    bundle = {
        "bundle_version": "SYNTHETIC_CLOSED_REPAIR_WRITER_PARTICIPATION_BUNDLE_V1",
        "upstream_coordination_receipt_sha256": coordination_receipt[
            "coordination_receipt_sha256"
        ],
        "participation_spec_sha256": spec["spec_sha256"],
        "transaction_sha256": coordination_receipt["transaction_sha256"],
        "writer_inventory_sha256": coordination_receipt[
            "writer_inventory_sha256"
        ],
        "lock_namespace_sha256": coordination_receipt["lock_namespace_sha256"],
        "maintenance_epoch": maintenance_epoch,
        "writer_count": len(receipts),
        "participant_receipts": receipts,
        "participant_receipts_sha256": participation._stable_sha256(receipts),
        "safety_envelope": {
            "synthetic_memory_only": True,
            "all_writer_operations_executed": False,
            "real_registry_accessed": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "runtime_integrated": False,
            "write_executed": False,
            "registry_write": False,
            "runtime_install_allowed": False,
            "apply_entrypoint_present": False,
            "no_order_sent": True,
        },
    }
    bundle["bundle_sha256"] = participation.writer_participation_bundle_sha256_v1(
        bundle
    )
    return {
        "coordination_result": coordination_result,
        "participation_spec": spec,
        "participation_bundle": bundle,
    }


def run_synthetic_closed_repair_writer_participation_harness_v1() -> dict[str, Any]:
    inputs = build_synthetic_closed_repair_writer_participation_inputs_v1()
    before = copy.deepcopy(inputs)
    before_sha = participation._stable_sha256(before)
    first = participation.evaluate_closed_repair_writer_participation_offline_v1(
        **inputs
    )
    second = participation.evaluate_closed_repair_writer_participation_offline_v1(
        **copy.deepcopy(inputs)
    )
    after_sha = participation._stable_sha256(inputs)
    receipt = first.get("participation_receipt")
    ok = bool(
        first.get("ok") is True
        and first.get("participation_contract_verified") is True
        and first.get("synthetic_participants_valid") is True
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
            "CLOSED_REPAIR_WRITER_PARTICIPATION_V1_HARNESS_PASSED_PRODUCTION_BLOCKED"
            if ok
            else "CLOSED_REPAIR_WRITER_PARTICIPATION_V1_HARNESS_FAILED_CLOSED"
        ),
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_HARNESS_V1_VERSION,
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
        "participation_result": first,
    }


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_PARTICIPATION_HARNESS_V1_VERSION",
    "InMemoryDormantWriterParticipant",
    "SyntheticWriterParticipationBlocked",
    "build_synthetic_closed_repair_writer_participation_inputs_v1",
    "run_synthetic_closed_repair_writer_participation_harness_v1",
]
