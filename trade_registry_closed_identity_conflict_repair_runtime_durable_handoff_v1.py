"""Offline durable-handoff contract for the dormant CLOSED-repair chain.

The module binds an already validated dormant gateway receipt to a deterministic
transaction identity and a hash-chained synthetic WAL.  The WAL can be exported
and restored to rehearse process restart, but it is intentionally memory-only
and never claims production durability.  No controller, Registry or runtime is
imported or invoked.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1 as authorization_module
import trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1 as gateway_module


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_V1_VERSION = (
    "2026-09-06-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-DURABLE-HANDOFF-V1"
)

OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1 = (
    "C3_CLOSED_REPAIR_DURABLE_HANDOFF_OFFLINE_ONLY_V1"
)
HANDOFF_INTENT_VERSION_V1 = "C3_CLOSED_REPAIR_DURABLE_HANDOFF_INTENT_V1"
TERMINAL_ATTESTATION_VERSION_V1 = (
    "C3_CLOSED_REPAIR_SYNTHETIC_TERMINAL_ATTESTATION_V1"
)
HANDOFF_COMMAND_VERSION_V1 = "C3_CLOSED_REPAIR_PROTECTED_HANDOFF_COMMAND_V1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WAL_STATES = frozenset({"PREPARED", "COMMITTED", "ABORTED"})
_WAL_RECORD_KEYS = frozenset(
    {
        "sequence",
        "previous_record_sha256",
        "transaction_id",
        "handoff_binding_sha256",
        "state",
        "prior_state",
        "event_epoch",
        "synthetic_only",
        "controller_invoked",
        "registry_write",
        "record_sha256",
    }
)
_GATEWAY_RECEIPT_KEYS = frozenset(
    {
        "conformance_receipt_sha256",
        "adapter_receipt_sha256",
        "authorization_receipt_sha256",
        "invocation_intent_sha256",
        "controller_instance_sha256",
        "preview_receipt_sha256",
        "reservation_token_sha256",
        "gateway_lease_token_sha256",
        "binding_sha256",
        "expires_at_epoch",
        "envelope_fields",
        "same_instance_preview_verified_synthetic",
        "same_runtime_instance_verified",
        "authorization_verified_synthetic",
        "production_authorization_valid",
        "request_material_exposed",
        "serialization_allowed",
        "controller_invocation_allowed",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "gateway_receipt_sha256",
    }
)
_AUTHORIZATION_RECEIPT_KEYS = frozenset(
    {
        "upstream_controller_binding_receipt_sha256",
        "authorization_envelope_sha256",
        "signature_sha256",
        "key_id_sha256",
        "nonce_sha256",
        "preview_receipt_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "authorized_action",
        "max_apply_count",
        "issued_at_epoch",
        "expires_at_epoch",
        "ttl_seconds",
        "synthetic_authorization_verified",
        "production_authorization_valid",
        "runtime_binding_satisfied",
        "production_ready",
        "apply_allowed",
        "activation_allowed",
        "live_allowed",
        "production_blockers",
        "authorization_receipt_sha256",
    }
)
_INTENT_KEYS = frozenset(
    {
        "intent_version",
        "gateway_receipt_sha256",
        "authorization_receipt_sha256",
        "preview_receipt_sha256",
        "controller_instance_sha256",
        "source_registry_sha256",
        "candidate_registry_sha256",
        "changed_paths_sha256",
        "terminal_policy",
        "controller_call_requested",
        "registry_write_requested",
        "runtime_binding_requested",
        "max_terminal_transition_count",
        "intent_sha256",
    }
)
_TERMINAL_ATTESTATION_KEYS = frozenset(
    {
        "attestation_version",
        "transaction_id",
        "handoff_binding_sha256",
        "terminal_state",
        "event_epoch",
        "synthetic_only",
        "production_evidence",
        "controller_invoked",
        "registry_write",
        "attestation_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "HANDOFF_WAL_IS_SYNTHETIC_MEMORY_ONLY",
    "RESTART_IS_REHEARSED_BY_SNAPSHOT_TRANSFER_ONLY",
    "AUTHORIZATION_IS_SYNTHETIC_NON_PRODUCTION",
    "SAME_RUNTIME_CONTROLLER_INSTANCE_IS_NOT_VERIFIED",
    "CONTROLLER_IS_NOT_INVOKED",
    "REGISTRY_IS_NOT_READ_OR_WRITTEN",
    "PRODUCTION_TRANSACTION_STORE_IS_NOT_BOUND",
    "DURABLE_AUTHORIZATION_CONSUMPTION_IS_NOT_BOUND",
    "RUNTIME_STARTUP_RECOVERY_IS_NOT_BOUND",
    "SEPARATE_PRODUCTION_IMPLEMENTATION_AND_AUTHORIZATION_REQUIRED",
    "LIVE_TRADING_REMAINS_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _receipt_sha256(receipt: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: value for key, value in receipt.items() if key != field_name}
    )


def durable_handoff_intent_sha256_v1(intent: Mapping[str, Any]) -> str:
    if not isinstance(intent, Mapping):
        raise TypeError("intent must be a mapping")
    return _receipt_sha256(intent, "intent_sha256")


def synthetic_terminal_attestation_sha256_v1(
    attestation: Mapping[str, Any],
) -> str:
    if not isinstance(attestation, Mapping):
        raise TypeError("attestation must be a mapping")
    return _receipt_sha256(attestation, "attestation_sha256")


def deterministic_handoff_transaction_id_v1(binding: Mapping[str, Any]) -> str:
    if not isinstance(binding, Mapping):
        raise TypeError("binding must be a mapping")
    return _stable_sha256(
        {
            **dict(binding),
            "transaction_identity_version": "C3_DURABLE_HANDOFF_TRANSACTION_ID_V1",
        }
    )


@dataclass(frozen=True)
class DurableHandoffConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_handoff_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.max_handoff_ttl_seconds <= 300:
            raise ValueError("max_handoff_ttl_seconds must be between 1 and 300")


@dataclass(frozen=True, repr=False)
class ProtectedDurableHandoffCommandV1:
    command_version: str = field(repr=False)
    transaction_id: str = field(repr=False)
    idempotency_key: str = field(repr=False)
    handoff_binding_sha256: str = field(repr=False)
    gateway_receipt_sha256: str = field(repr=False)
    authorization_receipt_sha256: str = field(repr=False)
    handoff_intent_sha256: str = field(repr=False)
    preview_receipt_sha256: str = field(repr=False)
    controller_instance_sha256: str = field(repr=False)
    source_registry_sha256: str = field(repr=False)
    candidate_registry_sha256: str = field(repr=False)
    changed_paths_sha256: str = field(repr=False)
    expires_at_epoch: int = field(repr=False)
    wal_prepared_record_sha256: str = field(repr=False)
    command_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedDurableHandoffCommandV1(<protected>)"


class HandoffWalIntegrityError(RuntimeError):
    pass


def _command_payload(
    command: ProtectedDurableHandoffCommandV1,
) -> dict[str, Any]:
    return {
        "command_version": command.command_version,
        "transaction_id": command.transaction_id,
        "idempotency_key": command.idempotency_key,
        "handoff_binding_sha256": command.handoff_binding_sha256,
        "gateway_receipt_sha256": command.gateway_receipt_sha256,
        "authorization_receipt_sha256": command.authorization_receipt_sha256,
        "handoff_intent_sha256": command.handoff_intent_sha256,
        "preview_receipt_sha256": command.preview_receipt_sha256,
        "controller_instance_sha256": command.controller_instance_sha256,
        "source_registry_sha256": command.source_registry_sha256,
        "candidate_registry_sha256": command.candidate_registry_sha256,
        "changed_paths_sha256": command.changed_paths_sha256,
        "expires_at_epoch": command.expires_at_epoch,
        "wal_prepared_record_sha256": command.wal_prepared_record_sha256,
    }


def protected_handoff_command_sha256_v1(
    command: ProtectedDurableHandoffCommandV1,
) -> str:
    if type(command) is not ProtectedDurableHandoffCommandV1:
        raise TypeError("command must be a ProtectedDurableHandoffCommandV1")
    return _stable_sha256(_command_payload(command))


def _command_integrity_valid(command: Any) -> bool:
    if type(command) is not ProtectedDurableHandoffCommandV1:
        return False
    binding = {
        "gateway_receipt_sha256": command.gateway_receipt_sha256,
        "authorization_receipt_sha256": command.authorization_receipt_sha256,
        "handoff_intent_sha256": command.handoff_intent_sha256,
        "preview_receipt_sha256": command.preview_receipt_sha256,
        "controller_instance_sha256": command.controller_instance_sha256,
        "source_registry_sha256": command.source_registry_sha256,
        "candidate_registry_sha256": command.candidate_registry_sha256,
        "changed_paths_sha256": command.changed_paths_sha256,
        "expires_at_epoch": command.expires_at_epoch,
    }
    try:
        return bool(
            command.command_version == HANDOFF_COMMAND_VERSION_V1
            and command.idempotency_key == command.transaction_id
            and command.handoff_binding_sha256 == _stable_sha256(binding)
            and command.transaction_id
            == deterministic_handoff_transaction_id_v1(binding)
            and _valid_sha256(command.wal_prepared_record_sha256)
            and _valid_sha256(command.command_sha256)
            and hmac.compare_digest(
                command.command_sha256,
                protected_handoff_command_sha256_v1(command),
            )
        )
    except Exception:
        return False


class InMemoryHashChainedHandoffWalV1:
    """Synthetic WAL whose exported snapshot can be restored after restart."""

    def __init__(self, restored_records: Sequence[Mapping[str, Any]] = ()) -> None:
        self._lock = threading.Lock()
        try:
            records = json.loads(_canonical_json(list(restored_records)))
        except Exception as exc:
            raise HandoffWalIntegrityError("HANDOFF_WAL_SNAPSHOT_INVALID") from exc
        self._validate_chain(records)
        self._records: list[dict[str, Any]] = records

    @staticmethod
    def _validate_chain(records: Sequence[Mapping[str, Any]]) -> None:
        previous_sha = "0" * 64
        latest_by_transaction: dict[str, tuple[str, str, int]] = {}
        for expected_sequence, record in enumerate(records, start=1):
            if not isinstance(record, Mapping) or set(record) != _WAL_RECORD_KEYS:
                raise HandoffWalIntegrityError("HANDOFF_WAL_RECORD_SCHEMA_INVALID")
            supplied_sha = _valid_sha256(record.get("record_sha256"))
            transaction_id = _valid_sha256(record.get("transaction_id"))
            binding_sha = _valid_sha256(record.get("handoff_binding_sha256"))
            state = record.get("state")
            prior_state = record.get("prior_state")
            if not (
                record.get("sequence") == expected_sequence
                and record.get("previous_record_sha256") == previous_sha
                and supplied_sha
                and transaction_id
                and binding_sha
                and state in _WAL_STATES
                and type(record.get("event_epoch")) is int
                and record.get("synthetic_only") is True
                and record.get("controller_invoked") is False
                and record.get("registry_write") is False
                and hmac.compare_digest(
                    supplied_sha, _receipt_sha256(record, "record_sha256")
                )
            ):
                raise HandoffWalIntegrityError("HANDOFF_WAL_RECORD_INTEGRITY_FAILED")
            previous = latest_by_transaction.get(transaction_id)
            previous_state = previous[0] if previous is not None else None
            valid_transition = bool(
                (previous_state is None and state == "PREPARED" and prior_state is None)
                or (
                    previous_state == "PREPARED"
                    and state in {"COMMITTED", "ABORTED"}
                    and prior_state == "PREPARED"
                    and previous is not None
                    and binding_sha == previous[1]
                    and record.get("event_epoch") >= previous[2]
                )
            )
            if not valid_transition:
                raise HandoffWalIntegrityError("HANDOFF_WAL_STATE_TRANSITION_INVALID")
            latest_by_transaction[transaction_id] = (
                str(state),
                binding_sha,
                int(record["event_epoch"]),
            )
            previous_sha = supplied_sha

    def _append(
        self,
        *,
        transaction_id: str,
        binding_sha256: str,
        state: str,
        prior_state: str | None,
        event_epoch: int,
    ) -> dict[str, Any]:
        record = {
            "sequence": len(self._records) + 1,
            "previous_record_sha256": (
                self._records[-1]["record_sha256"] if self._records else "0" * 64
            ),
            "transaction_id": transaction_id,
            "handoff_binding_sha256": binding_sha256,
            "state": state,
            "prior_state": prior_state,
            "event_epoch": event_epoch,
            "synthetic_only": True,
            "controller_invoked": False,
            "registry_write": False,
        }
        record["record_sha256"] = _stable_sha256(record)
        self._records.append(record)
        return json.loads(_canonical_json(record))

    def _matching(self, transaction_id: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._records
            if record.get("transaction_id") == transaction_id
        ]

    def prepare(
        self,
        transaction_id: str,
        binding_sha256: str,
        event_epoch: int,
    ) -> dict[str, Any]:
        transaction = _valid_sha256(transaction_id)
        binding = _valid_sha256(binding_sha256)
        if not transaction or not binding or type(event_epoch) is not int:
            return {"ok": False, "reason": "HANDOFF_WAL_PREPARE_INPUT_INVALID"}
        with self._lock:
            matching = self._matching(transaction)
            if matching:
                if any(record["handoff_binding_sha256"] != binding for record in matching):
                    return {"ok": False, "reason": "HANDOFF_WAL_IDEMPOTENCY_CONFLICT"}
                latest = matching[-1]
                prepared = matching[0]
                return {
                    "ok": True,
                    "state": latest["state"],
                    "idempotent_replay": True,
                    "record_sha256": latest["record_sha256"],
                    "prepared_record_sha256": prepared["record_sha256"],
                    "append_executed": False,
                }
            prepared = self._append(
                transaction_id=transaction,
                binding_sha256=binding,
                state="PREPARED",
                prior_state=None,
                event_epoch=event_epoch,
            )
            return {
                "ok": True,
                "state": "PREPARED",
                "idempotent_replay": False,
                "record_sha256": prepared["record_sha256"],
                "prepared_record_sha256": prepared["record_sha256"],
                "append_executed": True,
            }

    def finalize(
        self,
        transaction_id: str,
        binding_sha256: str,
        terminal_state: str,
        event_epoch: int,
    ) -> dict[str, Any]:
        transaction = _valid_sha256(transaction_id)
        binding = _valid_sha256(binding_sha256)
        state = str(terminal_state or "").upper().strip()
        if not (
            transaction
            and binding
            and state in {"COMMITTED", "ABORTED"}
            and type(event_epoch) is int
        ):
            return {"ok": False, "reason": "HANDOFF_WAL_FINALIZE_INPUT_INVALID"}
        with self._lock:
            matching = self._matching(transaction)
            if not matching:
                return {"ok": False, "reason": "HANDOFF_WAL_PREPARED_REQUIRED"}
            if any(record["handoff_binding_sha256"] != binding for record in matching):
                return {"ok": False, "reason": "HANDOFF_WAL_IDEMPOTENCY_CONFLICT"}
            latest = matching[-1]
            if event_epoch < latest["event_epoch"]:
                return {"ok": False, "reason": "HANDOFF_WAL_EVENT_ORDER_INVALID"}
            if latest["state"] in {"COMMITTED", "ABORTED"}:
                if latest["state"] != state:
                    return {"ok": False, "reason": "HANDOFF_WAL_TERMINAL_CONFLICT"}
                return {
                    "ok": True,
                    "state": state,
                    "idempotent_replay": True,
                    "record_sha256": latest["record_sha256"],
                    "append_executed": False,
                }
            terminal = self._append(
                transaction_id=transaction,
                binding_sha256=binding,
                state=state,
                prior_state="PREPARED",
                event_epoch=event_epoch,
            )
            return {
                "ok": True,
                "state": state,
                "idempotent_replay": False,
                "record_sha256": terminal["record_sha256"],
                "append_executed": True,
            }

    def recover(self, transaction_id: str, binding_sha256: str) -> dict[str, Any]:
        transaction = _valid_sha256(transaction_id)
        binding = _valid_sha256(binding_sha256)
        if not transaction or not binding:
            return {"ok": False, "reason": "HANDOFF_WAL_RECOVERY_INPUT_INVALID"}
        with self._lock:
            matching = self._matching(transaction)
            if not matching:
                return {"ok": False, "reason": "HANDOFF_WAL_TRANSACTION_NOT_FOUND"}
            if any(record["handoff_binding_sha256"] != binding for record in matching):
                return {"ok": False, "reason": "HANDOFF_WAL_IDEMPOTENCY_CONFLICT"}
            latest = matching[-1]
            return {
                "ok": True,
                "state": latest["state"],
                "record_sha256": latest["record_sha256"],
                "idempotent_replay": True,
                "recovered_after_restart_simulation": True,
            }

    def export_restart_snapshot(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(json.loads(_canonical_json(self._records)))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            states: dict[str, int] = {}
            for record in self._records:
                state = str(record["state"])
                states[state] = states.get(state, 0) + 1
            return {
                "record_count": len(self._records),
                "states": states,
                "chain_head_sha256": (
                    self._records[-1]["record_sha256"]
                    if self._records
                    else "0" * 64
                ),
                "hash_chain_verified": True,
                "storage_kind": "SYNTHETIC_MEMORY_WITH_RESTART_SNAPSHOT",
                "production_durable": False,
                "raw_authorization_stored": False,
                "raw_registry_stored": False,
            }


class DurableHandoffOfflineV1:
    def __init__(
        self,
        *,
        config: DurableHandoffConfigV1 | None = None,
        clock: Callable[[], int] | None = None,
        wal: InMemoryHashChainedHandoffWalV1 | None = None,
    ) -> None:
        self._config = config or DurableHandoffConfigV1()
        self._clock = clock
        self._wal = wal

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_DURABLE_HANDOFF_OFFLINE_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_V1_VERSION,
            "handoff_contract_verified": False,
            "gateway_verified": False,
            "authorization_verified_synthetic": False,
            "transaction_identity_verified": False,
            "strict_deadline_verified": False,
            "wal_prepared": False,
            "idempotent_replay": False,
            "restart_recovery_rehearsed": False,
            "production_durability_verified": False,
            "controller_invocation_allowed": False,
            "registry_write_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "offline_only": True,
            "synthetic_only": True,
            "runtime_imported": False,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "checks": {},
            "reasons": [],
            "protected_command": None,
            "handoff_receipt": None,
        }

    @staticmethod
    def _check_gateway(
        value: Mapping[str, Any], checks: dict[str, bool], reasons: list[str]
    ) -> tuple[
        gateway_module.ProtectedDormantInvocationEnvelopeV1 | None,
        Mapping[str, Any] | None,
        str,
    ]:
        envelope = value.get("protected_envelope")
        receipt = value.get("gateway_receipt")
        supplied = (
            _valid_sha256(receipt.get("gateway_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "gateway_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["dormant_gateway_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == gateway_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DORMANT_INVOCATION_GATEWAY_V1_VERSION
            and value.get("gateway_contract_verified") is True
            and value.get("authorization_verified_synthetic") is True
            and value.get("same_instance_preview_verified_synthetic") is True
            and value.get("same_runtime_instance_verified") is False
            and value.get("strict_deadline_verified") is True
            and value.get("http_envelope_projected") is True
            and value.get("controller_invocation_allowed") is False
            and value.get("runtime_binding_satisfied") is False
            and value.get("production_ready") is False
            and value.get("apply_allowed") is False
            and type(envelope)
            is gateway_module.ProtectedDormantInvocationEnvelopeV1
            and isinstance(receipt, Mapping)
            and set(receipt) == _GATEWAY_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("same_runtime_instance_verified") is False
            and receipt.get("production_authorization_valid") is False
            and receipt.get("controller_invocation_allowed") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and envelope.operation == "apply"
            and envelope.gateway_lease_token_sha256
            == receipt.get("gateway_lease_token_sha256")
            and envelope.authorization_receipt_sha256
            == receipt.get("authorization_receipt_sha256")
            and envelope.preview_receipt_sha256
            == receipt.get("preview_receipt_sha256")
            and envelope.controller_instance_sha256
            == receipt.get("controller_instance_sha256")
            and envelope.expires_at_epoch == receipt.get("expires_at_epoch")
        )
        if not checks["dormant_gateway_receipt_valid"]:
            reasons.append("HANDOFF_GATEWAY_INVALID")
        return (
            envelope
            if type(envelope)
            is gateway_module.ProtectedDormantInvocationEnvelopeV1
            else None,
            receipt if isinstance(receipt, Mapping) else None,
            supplied,
        )

    @staticmethod
    def _check_authorization(
        value: Mapping[str, Any],
        envelope: gateway_module.ProtectedDormantInvocationEnvelopeV1 | None,
        checks: dict[str, bool],
        reasons: list[str],
    ) -> tuple[Mapping[str, Any] | None, str]:
        receipt = value.get("authorization_receipt")
        supplied = (
            _valid_sha256(receipt.get("authorization_receipt_sha256"))
            if isinstance(receipt, Mapping)
            else ""
        )
        expected = (
            _receipt_sha256(receipt, "authorization_receipt_sha256")
            if isinstance(receipt, Mapping)
            else ""
        )
        checks["synthetic_authorization_receipt_valid"] = bool(
            value.get("ok") is True
            and value.get("version")
            == authorization_module.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_CONTROLLED_AUTHORIZATION_VALIDATOR_V1_VERSION
            and value.get("authorization_contract_verified") is True
            and value.get("signature_verified") is True
            and value.get("freshness_verified") is True
            and value.get("replay_guard_verified") is True
            and value.get("synthetic_authorization_verified") is True
            and value.get("apply_allowed") is False
            and isinstance(receipt, Mapping)
            and set(receipt) == _AUTHORIZATION_RECEIPT_KEYS
            and supplied
            and hmac.compare_digest(supplied, expected)
            and receipt.get("authorized_action")
            == authorization_module.AUTHORIZATION_ACTION_V1
            and receipt.get("max_apply_count") == 1
            and receipt.get("synthetic_authorization_verified") is True
            and receipt.get("production_authorization_valid") is False
            and receipt.get("runtime_binding_satisfied") is False
            and receipt.get("production_ready") is False
            and receipt.get("apply_allowed") is False
            and envelope is not None
            and envelope.authorization_receipt_sha256 == supplied
            and envelope.preview_receipt_sha256
            == receipt.get("preview_receipt_sha256")
        )
        if not checks["synthetic_authorization_receipt_valid"]:
            reasons.append("HANDOFF_AUTHORIZATION_INVALID")
        return receipt if isinstance(receipt, Mapping) else None, supplied

    @staticmethod
    def _check_intent(
        value: Mapping[str, Any],
        gateway_sha: str,
        authorization_sha: str,
        envelope: gateway_module.ProtectedDormantInvocationEnvelopeV1 | None,
        authorization_receipt: Mapping[str, Any] | None,
        checks: dict[str, bool],
        reasons: list[str],
    ) -> str:
        supplied = _valid_sha256(value.get("intent_sha256"))
        expected = durable_handoff_intent_sha256_v1(value)
        checks["durable_handoff_intent_valid"] = bool(
            set(value) == _INTENT_KEYS
            and value.get("intent_version") == HANDOFF_INTENT_VERSION_V1
            and value.get("gateway_receipt_sha256") == gateway_sha
            and value.get("authorization_receipt_sha256") == authorization_sha
            and envelope is not None
            and value.get("preview_receipt_sha256")
            == envelope.preview_receipt_sha256
            and value.get("controller_instance_sha256")
            == envelope.controller_instance_sha256
            and isinstance(authorization_receipt, Mapping)
            and value.get("source_registry_sha256")
            == authorization_receipt.get("source_registry_sha256")
            and value.get("candidate_registry_sha256")
            == authorization_receipt.get("candidate_registry_sha256")
            and value.get("changed_paths_sha256")
            == authorization_receipt.get("changed_paths_sha256")
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "source_registry_sha256",
                    "candidate_registry_sha256",
                    "changed_paths_sha256",
                )
            )
            and value.get("terminal_policy")
            == "EXPLICIT_SYNTHETIC_COMMIT_OR_ABORT_ONLY"
            and value.get("controller_call_requested") is False
            and value.get("registry_write_requested") is False
            and value.get("runtime_binding_requested") is False
            and value.get("max_terminal_transition_count") == 1
            and supplied
            and hmac.compare_digest(supplied, expected)
        )
        if not checks["durable_handoff_intent_valid"]:
            reasons.append("HANDOFF_INTENT_INVALID")
        return supplied

    def prepare(
        self,
        *,
        gateway_result: Mapping[str, Any],
        authorization_result: Mapping[str, Any],
        handoff_intent: Mapping[str, Any],
    ) -> dict[str, Any]:
        result = self._base()
        reasons: list[str] = result["reasons"]
        checks: dict[str, bool] = result["checks"]
        if self._config.enabled is not True:
            result.update(
                status="C3_DURABLE_HANDOFF_OFFLINE_DEFAULT_OFF",
                reasons=["HANDOFF_DEFAULT_OFF"],
            )
            return result
        if self._config.scope_attestation != OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1:
            result.update(
                status="C3_DURABLE_HANDOFF_OFFLINE_SCOPE_REQUIRED",
                reasons=["HANDOFF_OFFLINE_SCOPE_ATTESTATION_REQUIRED"],
            )
            return result
        if not all(
            isinstance(value, Mapping)
            for value in (gateway_result, authorization_result, handoff_intent)
        ):
            result["reasons"] = ["HANDOFF_MAPPING_INPUTS_REQUIRED"]
            return result

        envelope, _, gateway_sha = self._check_gateway(
            gateway_result, checks, reasons
        )
        authorization_receipt, authorization_sha = self._check_authorization(
            authorization_result, envelope, checks, reasons
        )
        intent_sha = self._check_intent(
            handoff_intent,
            gateway_sha,
            authorization_sha,
            envelope,
            authorization_receipt,
            checks,
            reasons,
        )

        now: int | None = None
        try:
            if not callable(self._clock):
                raise TypeError("clock unavailable")
            clock_value = self._clock()
            if type(clock_value) is not int:
                raise TypeError("clock invalid")
            now = clock_value
        except Exception:
            reasons.append("HANDOFF_CLOCK_UNAVAILABLE")
        expiry = envelope.expires_at_epoch if envelope is not None else None
        authorization_expiry = (
            authorization_receipt.get("expires_at_epoch")
            if isinstance(authorization_receipt, Mapping)
            else None
        )
        checks["strict_handoff_deadline_valid"] = bool(
            now is not None
            and type(expiry) is int
            and type(authorization_expiry) is int
            and expiry <= authorization_expiry
            and now < expiry
            and 1 <= expiry - now <= self._config.max_handoff_ttl_seconds
        )
        if not checks["strict_handoff_deadline_valid"]:
            reasons.append("HANDOFF_DEADLINE_INVALID_OR_EXPIRED")

        binding = {
            "gateway_receipt_sha256": gateway_sha,
            "authorization_receipt_sha256": authorization_sha,
            "handoff_intent_sha256": intent_sha,
            "preview_receipt_sha256": (
                envelope.preview_receipt_sha256 if envelope else ""
            ),
            "controller_instance_sha256": (
                envelope.controller_instance_sha256 if envelope else ""
            ),
            "source_registry_sha256": handoff_intent.get("source_registry_sha256"),
            "candidate_registry_sha256": handoff_intent.get(
                "candidate_registry_sha256"
            ),
            "changed_paths_sha256": handoff_intent.get("changed_paths_sha256"),
            "expires_at_epoch": expiry,
        }
        transaction_id = deterministic_handoff_transaction_id_v1(binding)
        binding_sha = _stable_sha256(binding)
        checks["deterministic_transaction_identity_valid"] = bool(
            _valid_sha256(transaction_id) and _valid_sha256(binding_sha)
        )

        wal_result: dict[str, Any] | None = None
        if not reasons:
            if type(self._wal) is not InMemoryHashChainedHandoffWalV1:
                reasons.append("HANDOFF_WAL_UNAVAILABLE")
            else:
                wal_result = self._wal.prepare(transaction_id, binding_sha, now)
                if wal_result.get("ok") is not True:
                    reasons.append(str(wal_result.get("reason") or "HANDOFF_WAL_FAILED"))
        checks["wal_prepared_or_replayed"] = bool(
            isinstance(wal_result, Mapping)
            and wal_result.get("ok") is True
            and wal_result.get("state") in _WAL_STATES
        )

        reasons[:] = sorted(set(reasons))
        if reasons or not checks or not all(checks.values()):
            return result
        if wal_result["state"] in {"COMMITTED", "ABORTED"}:
            result.update(
                ok=True,
                status=f"C3_DURABLE_HANDOFF_OFFLINE_ALREADY_{wal_result['state']}",
                handoff_contract_verified=True,
                gateway_verified=True,
                authorization_verified_synthetic=True,
                transaction_identity_verified=True,
                strict_deadline_verified=True,
                idempotent_replay=True,
                reasons=[],
                handoff_receipt={
                    "transaction_id": transaction_id,
                    "handoff_binding_sha256": binding_sha,
                    "terminal_state": wal_result["state"],
                    "wal_record_sha256": wal_result["record_sha256"],
                    "production_durability_verified": False,
                    "controller_invocation_allowed": False,
                    "registry_write_allowed": False,
                    "production_blockers": list(_PRODUCTION_BLOCKERS),
                },
            )
            return result

        command_values = {
            "command_version": HANDOFF_COMMAND_VERSION_V1,
            "transaction_id": transaction_id,
            "idempotency_key": transaction_id,
            "handoff_binding_sha256": binding_sha,
            "gateway_receipt_sha256": gateway_sha,
            "authorization_receipt_sha256": authorization_sha,
            "handoff_intent_sha256": intent_sha,
            "preview_receipt_sha256": envelope.preview_receipt_sha256,
            "controller_instance_sha256": envelope.controller_instance_sha256,
            "source_registry_sha256": handoff_intent["source_registry_sha256"],
            "candidate_registry_sha256": handoff_intent[
                "candidate_registry_sha256"
            ],
            "changed_paths_sha256": handoff_intent["changed_paths_sha256"],
            "expires_at_epoch": expiry,
            "wal_prepared_record_sha256": wal_result["prepared_record_sha256"],
        }
        unsigned_command = ProtectedDurableHandoffCommandV1(
            **command_values,
            command_sha256="0" * 64,
        )
        command = ProtectedDurableHandoffCommandV1(
            **command_values,
            command_sha256=protected_handoff_command_sha256_v1(unsigned_command),
        )
        receipt = {
            **binding,
            "transaction_id": transaction_id,
            "idempotency_key": transaction_id,
            "handoff_binding_sha256": binding_sha,
            "wal_prepared_record_sha256": wal_result["prepared_record_sha256"],
            "wal_replayed": wal_result["idempotent_replay"],
            "wal_state": "PREPARED",
            "restart_recovery_rehearsable": True,
            "production_durability_verified": False,
            "controller_invocation_allowed": False,
            "registry_write_allowed": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }
        receipt["handoff_receipt_sha256"] = _stable_sha256(receipt)
        result.update(
            ok=True,
            status="C3_DURABLE_HANDOFF_PREPARED_OFFLINE_NON_EXECUTABLE",
            handoff_contract_verified=True,
            gateway_verified=True,
            authorization_verified_synthetic=True,
            transaction_identity_verified=True,
            strict_deadline_verified=True,
            wal_prepared=True,
            idempotent_replay=wal_result["idempotent_replay"],
            reasons=[],
            protected_command=command,
            handoff_receipt=receipt,
        )
        return result

    def finalize_offline(
        self,
        command: ProtectedDurableHandoffCommandV1,
        terminal_attestation: Mapping[str, Any],
    ) -> dict[str, Any]:
        base = {
            "ok": False,
            "status": "C3_DURABLE_HANDOFF_TERMINAL_BLOCKED",
            "terminal_state": None,
            "idempotent_replay": False,
            "restart_recovery_rehearsed": False,
            "production_commit_verified": False,
            "controller_invoked": False,
            "registry_write": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "no_order_sent": True,
            "reason": None,
            "terminal_receipt": None,
        }
        if self._config.enabled is not True:
            base["reason"] = "HANDOFF_DEFAULT_OFF"
            return base
        if self._config.scope_attestation != OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1:
            base["reason"] = "HANDOFF_OFFLINE_SCOPE_ATTESTATION_REQUIRED"
            return base
        if not _command_integrity_valid(command) or not isinstance(
            terminal_attestation, Mapping
        ):
            base["reason"] = "HANDOFF_TERMINAL_INPUT_INVALID"
            return base
        supplied = _valid_sha256(terminal_attestation.get("attestation_sha256"))
        expected = synthetic_terminal_attestation_sha256_v1(terminal_attestation)
        state = str(terminal_attestation.get("terminal_state") or "").upper().strip()
        try:
            terminal_now = self._clock() if callable(self._clock) else None
        except Exception:
            terminal_now = None
        valid = bool(
            set(terminal_attestation) == _TERMINAL_ATTESTATION_KEYS
            and terminal_attestation.get("attestation_version")
            == TERMINAL_ATTESTATION_VERSION_V1
            and terminal_attestation.get("transaction_id") == command.transaction_id
            and terminal_attestation.get("handoff_binding_sha256")
            == command.handoff_binding_sha256
            and state in {"COMMITTED", "ABORTED"}
            and type(terminal_attestation.get("event_epoch")) is int
            and type(terminal_now) is int
            and terminal_attestation.get("event_epoch") == terminal_now
            and (state == "ABORTED" or terminal_now < command.expires_at_epoch)
            and terminal_attestation.get("synthetic_only") is True
            and terminal_attestation.get("production_evidence") is False
            and terminal_attestation.get("controller_invoked") is False
            and terminal_attestation.get("registry_write") is False
            and supplied
            and hmac.compare_digest(supplied, expected)
        )
        if not valid:
            base["reason"] = "HANDOFF_TERMINAL_ATTESTATION_INVALID"
            return base
        if type(self._wal) is not InMemoryHashChainedHandoffWalV1:
            base["reason"] = "HANDOFF_WAL_UNAVAILABLE"
            return base
        wal_result = self._wal.finalize(
            command.transaction_id,
            command.handoff_binding_sha256,
            state,
            terminal_attestation["event_epoch"],
        )
        if wal_result.get("ok") is not True:
            base["reason"] = wal_result.get("reason")
            return base
        receipt = {
            "transaction_id": command.transaction_id,
            "handoff_binding_sha256": command.handoff_binding_sha256,
            "terminal_state": state,
            "terminal_attestation_sha256": supplied,
            "wal_terminal_record_sha256": wal_result["record_sha256"],
            "idempotent_replay": wal_result["idempotent_replay"],
            "synthetic_terminal_only": True,
            "production_commit_verified": False,
            "controller_invoked": False,
            "registry_write": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
        }
        receipt["terminal_receipt_sha256"] = _stable_sha256(receipt)
        base.update(
            ok=True,
            status=f"C3_DURABLE_HANDOFF_{state}_OFFLINE_SYNTHETIC",
            terminal_state=state,
            idempotent_replay=wal_result["idempotent_replay"],
            terminal_receipt=receipt,
        )
        return base

    def recover_offline(
        self, command: ProtectedDurableHandoffCommandV1
    ) -> dict[str, Any]:
        result = {
            "ok": False,
            "status": "C3_DURABLE_HANDOFF_RECOVERY_BLOCKED",
            "state": None,
            "restart_recovery_rehearsed": False,
            "production_recovery": False,
            "controller_invoked": False,
            "registry_write": False,
            "runtime_binding_satisfied": False,
            "production_ready": False,
            "apply_allowed": False,
            "no_order_sent": True,
            "reason": None,
        }
        if not _command_integrity_valid(command):
            result["reason"] = "HANDOFF_RECOVERY_COMMAND_INVALID"
            return result
        if type(self._wal) is not InMemoryHashChainedHandoffWalV1:
            result["reason"] = "HANDOFF_WAL_UNAVAILABLE"
            return result
        recovered = self._wal.recover(
            command.transaction_id, command.handoff_binding_sha256
        )
        if recovered.get("ok") is not True:
            result["reason"] = recovered.get("reason")
            return result
        result.update(
            ok=True,
            status=f"C3_DURABLE_HANDOFF_RECOVERED_{recovered['state']}_OFFLINE",
            state=recovered["state"],
            restart_recovery_rehearsed=True,
        )
        return result


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_DURABLE_HANDOFF_V1_VERSION",
    "OFFLINE_DURABLE_HANDOFF_SCOPE_ATTESTATION_V1",
    "HANDOFF_INTENT_VERSION_V1",
    "TERMINAL_ATTESTATION_VERSION_V1",
    "HANDOFF_COMMAND_VERSION_V1",
    "DurableHandoffConfigV1",
    "ProtectedDurableHandoffCommandV1",
    "HandoffWalIntegrityError",
    "InMemoryHashChainedHandoffWalV1",
    "DurableHandoffOfflineV1",
    "durable_handoff_intent_sha256_v1",
    "synthetic_terminal_attestation_sha256_v1",
    "deterministic_handoff_transaction_id_v1",
    "protected_handoff_command_sha256_v1",
]
