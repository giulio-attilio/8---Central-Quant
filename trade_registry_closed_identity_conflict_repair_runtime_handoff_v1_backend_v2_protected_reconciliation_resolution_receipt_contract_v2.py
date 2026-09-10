"""Dormant offline contract for resolving a protected reconciliation obligation.

The contract accepts only synthetic evidence, requires authority that is fresh
and object-distinct from the original apply authority, validates one live
in-memory maintenance lease, and emits a protected resolution receipt.  It has
no backend, Registry, runtime, filesystem, network, or trading binding.
"""

from __future__ import annotations

import copy
import hmac
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as backend_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1 as consumer_v1
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2 as obligation_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_CONTRACT_V2_VERSION = (
    "2026-09-08-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-HANDOFF-V1-BACKEND-V2-PROTECTED-RECONCILIATION-RESOLUTION-RECEIPT-CONTRACT-V2"
)
OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_OFFLINE_ONLY"
)
FRESH_RECONCILIATION_AUTHORITY_VERSION_V2 = "C3_FRESH_RECONCILIATION_AUTHORITY_V2"
RECONCILIATION_AUTHORIZATION_RECEIPT_VERSION_V2 = (
    "C3_SYNTHETIC_RECONCILIATION_AUTHORIZATION_CONSUMPTION_RECEIPT_V2"
)
RECONCILIATION_AUTHORIZED_ACTION_V2 = "RECONCILE_C3_TRANSACTION_ONCE"
TERMINAL_RESOLUTION_EVIDENCE_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_TERMINAL_RESOLUTION_EVIDENCE_V2"
)
PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_VERSION_V2 = (
    "C3_PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_V2"
)

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTH_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "grant_sha256", "subject_binding_sha256",
        "authorized_action", "consumption_count", "consumed_at_epoch",
        "authorization_issuer_object_identity_sha256",
        "resolution_ledger_object_identity_sha256",
        "process_session_anchor_object_identity_sha256",
        "expires_at_epoch", "synthetic_only", "production_authority",
        "receipt_sha256",
    }
)
_AUTHORITY_KEYS = frozenset(
    {
        "authority_version", "scope_attestation", "obligation_sha256",
        "subject_binding_sha256", "authorization_receipt_sha256",
        "maintenance_epoch", "permit_binding_sha256",
        "permit_object_identity_sha256", "lease_token_sha256",
        "lease_token_object_identity_sha256", "lease_witness_object_identity_sha256",
        "single_use_ledger_object_identity_sha256",
        "authorization_issuer_object_identity_sha256",
        "process_session_anchor_object_identity_sha256",
        "issued_at_epoch", "expires_at_epoch", "single_use",
        "fresh_from_original", "synthetic_only", "production_authority",
        "runtime_integrated", "authority_sha256",
    }
)
_TERMINAL_KEYS = frozenset(
    {
        "evidence_version", "obligation_sha256", "obligation_id_sha256",
        "source_evidence_sha256", "adapter_plan_sha256",
        "request_binding_sha256", "request_sha256", "transaction_sha256",
        "idempotency_key_sha256", "backend_instance_sha256",
        "original_terminal_result_sha256", "terminal_state",
        "fresh_authority_sha256", "fresh_authorization_receipt_sha256",
        "fresh_maintenance_epoch", "fresh_lease_token_sha256",
        "single_use_ledger_object_identity_sha256",
        "observed_under_fresh_lease",
        "reconciled_at_epoch", "same_transaction_identity_verified",
        "terminal_state_verified", "postconditions_verified",
        "recovery_required", "new_apply_allowed", "retry_allowed",
        "backend_called", "registry_write", "write_executed", "synthetic_only",
        "production_evidence", "evidence_sha256",
    }
)
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version", "scope_attestation", "obligation_sha256",
        "obligation_id_sha256", "source_evidence_sha256",
        "adapter_plan_sha256", "request_sha256", "transaction_sha256",
        "fresh_authority_sha256", "fresh_authorization_receipt_sha256",
        "fresh_maintenance_epoch", "fresh_lease_token_sha256",
        "restart_barrier_sha256", "restart_barrier_continuity_verified",
        "single_use_ledger_object_identity_sha256",
        "single_use_consumption_receipt_sha256",
        "terminal_resolution_evidence_sha256", "terminal_state",
        "resolved_at_epoch", "resolution_state", "reconciliation_required",
        "same_transaction_identity_verified", "fresh_authority_verified",
        "terminal_resolution_verified", "original_authorization_reused",
        "new_apply_allowed", "retry_allowed", "backend_bound",
        "backend_called", "registry_write", "write_executed",
        "filesystem_accessed", "real_registry_accessed", "network_accessed",
        "broker_called", "synthetic_only", "production_authority",
        "runtime_integrated", "activation_allowed", "live_allowed",
        "receipt_sha256",
    }
)
_SINGLE_USE_CONSUMPTION_KEYS = frozenset(
    {
        "consumption_version", "obligation_sha256",
        "authorization_receipt_sha256", "fresh_authority_sha256",
        "single_use_ledger_object_identity_sha256",
        "terminal_resolution_evidence_sha256", "consumption_count",
        "consumed_at_epoch", "in_memory_only", "durable", "synthetic_only",
        "production_authority", "consumption_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return backend_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def _identity_sha(kind: str, value: object) -> str:
    return backend_v2.stable_sha256_v2(
        {"kind": kind, "process_object_identity": id(value)}
    )


def _permit_binding(permit: coordinator_v1.WriterMaintenancePermitV1) -> dict[str, Any]:
    return {
        "maintenance_epoch": permit.maintenance_epoch,
        "state": permit.state,
        "lock_namespace_sha256": permit.lock_namespace_sha256,
        "registered_writer_count": permit.registered_writer_count,
        "inflight_mutations": permit.inflight_mutations,
        "shared_lock_acquired": permit.shared_lock_acquired,
    }


def reconciliation_authorization_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "receipt_sha256")


def fresh_reconciliation_authority_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "authority_sha256")


def terminal_resolution_evidence_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "evidence_sha256")


def protected_reconciliation_resolution_receipt_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return _hash_without(value, "receipt_sha256")


def single_use_resolution_consumption_sha256_v2(value: Mapping[str, Any]) -> str:
    return _hash_without(value, "consumption_sha256")


class InMemorySyntheticReconciliationResolutionLedgerV2:
    """Atomic, process-local replay barrier with no persistence or I/O."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}

    def consume_once(
        self,
        *,
        obligation_sha256: str,
        authorization_receipt_sha256: str,
        fresh_authority_sha256: str,
        terminal_resolution_evidence_sha256: str,
        now_epoch: int,
    ) -> dict[str, Any] | None:
        if not (
            all(
                _valid_sha(value)
                for value in (
                    obligation_sha256,
                    authorization_receipt_sha256,
                    fresh_authority_sha256,
                    terminal_resolution_evidence_sha256,
                )
            )
            and type(now_epoch) is int
        ):
            return None
        with self._lock:
            if authorization_receipt_sha256 in self._records:
                return None
            consumption = {
                "consumption_version": "C3_SYNTHETIC_RECONCILIATION_RESOLUTION_CONSUMPTION_V2",
                "obligation_sha256": obligation_sha256,
                "authorization_receipt_sha256": authorization_receipt_sha256,
                "fresh_authority_sha256": fresh_authority_sha256,
                "single_use_ledger_object_identity_sha256": _identity_sha(
                    "synthetic_reconciliation_resolution_ledger_v2", self
                ),
                "terminal_resolution_evidence_sha256": terminal_resolution_evidence_sha256,
                "consumption_count": 1,
                "consumed_at_epoch": now_epoch,
                "in_memory_only": True,
                "durable": False,
                "synthetic_only": True,
                "production_authority": False,
            }
            consumption["consumption_sha256"] = (
                single_use_resolution_consumption_sha256_v2(consumption)
            )
            self._records[authorization_receipt_sha256] = copy.deepcopy(consumption)
            return copy.deepcopy(consumption)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "consumed_authority_count": len(self._records),
                "in_memory_only": True,
                "durable": False,
                "synthetic_only": True,
                "production_authority": False,
            }


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticReconciliationProcessSessionAnchorV2:
    session_nonce_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        if not _valid_sha(self.session_nonce_sha256):
            raise ValueError("session_nonce_sha256 must be a lowercase SHA-256")

    def __repr__(self) -> str:
        return "ProtectedSyntheticReconciliationProcessSessionAnchorV2(<protected>)"


class InMemorySyntheticReconciliationAuthorizationIssuerV2:
    """One-shot synthetic issuer bound to one session and resolution ledger."""

    def __init__(
        self,
        *,
        process_session_anchor: ProtectedSyntheticReconciliationProcessSessionAnchorV2,
        resolution_ledger: InMemorySyntheticReconciliationResolutionLedgerV2,
    ) -> None:
        if type(process_session_anchor) is not ProtectedSyntheticReconciliationProcessSessionAnchorV2:
            raise TypeError("protected process session anchor required")
        if type(resolution_ledger) is not InMemorySyntheticReconciliationResolutionLedgerV2:
            raise TypeError("synthetic resolution ledger required")
        self._process_session_anchor = process_session_anchor
        self._resolution_ledger = resolution_ledger
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}

    @property
    def process_session_anchor(self) -> ProtectedSyntheticReconciliationProcessSessionAnchorV2:
        return self._process_session_anchor

    @property
    def resolution_ledger(self) -> InMemorySyntheticReconciliationResolutionLedgerV2:
        return self._resolution_ledger

    def issue_once(
        self,
        *,
        grant_sha256: str,
        obligation_sha256: str,
        now_epoch: int,
        expires_at_epoch: int,
    ) -> dict[str, Any] | None:
        if not (
            _valid_sha(grant_sha256)
            and _valid_sha(obligation_sha256)
            and type(now_epoch) is int
            and type(expires_at_epoch) is int
            and now_epoch < expires_at_epoch
        ):
            return None
        with self._lock:
            if grant_sha256 in self._records:
                return None
            receipt = {
                "receipt_version": RECONCILIATION_AUTHORIZATION_RECEIPT_VERSION_V2,
                "grant_sha256": grant_sha256,
                "subject_binding_sha256": obligation_sha256,
                "authorized_action": RECONCILIATION_AUTHORIZED_ACTION_V2,
                "consumption_count": 1,
                "consumed_at_epoch": now_epoch,
                "authorization_issuer_object_identity_sha256": _identity_sha(
                    "synthetic_reconciliation_authorization_issuer_v2", self
                ),
                "resolution_ledger_object_identity_sha256": _identity_sha(
                    "synthetic_reconciliation_resolution_ledger_v2",
                    self._resolution_ledger,
                ),
                "process_session_anchor_object_identity_sha256": _identity_sha(
                    "synthetic_reconciliation_process_session_anchor_v2",
                    self._process_session_anchor,
                ),
                "expires_at_epoch": expires_at_epoch,
                "synthetic_only": True,
                "production_authority": False,
            }
            receipt["receipt_sha256"] = (
                reconciliation_authorization_receipt_sha256_v2(receipt)
            )
            self._records[grant_sha256] = copy.deepcopy(receipt)
            return copy.deepcopy(receipt)

    def receipt_was_issued(self, receipt: Mapping[str, Any]) -> bool:
        if type(receipt) is not dict:
            return False
        grant_sha256 = str(receipt.get("grant_sha256") or "")
        with self._lock:
            stored = self._records.get(grant_sha256)
            return bool(stored is not None and hmac.compare_digest(
                backend_v2.stable_sha256_v2(stored),
                backend_v2.stable_sha256_v2(dict(receipt)),
            ))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "issued_authorization_count": len(self._records),
                "in_memory_only": True,
                "durable": False,
                "synthetic_only": True,
                "production_authority": False,
            }


@dataclass(frozen=True, repr=False)
class ProtectedFreshReconciliationAuthorityV2:
    authorization_receipt: Mapping[str, Any] = field(repr=False)
    maintenance_permit: coordinator_v1.WriterMaintenancePermitV1 = field(repr=False)
    live_lease_token: consumer_v1.ProtectedSyntheticLiveLeaseTokenV1 = field(repr=False)
    lease_witness: consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1 = field(repr=False)
    single_use_ledger: InMemorySyntheticReconciliationResolutionLedgerV2 = field(
        repr=False
    )
    authorization_issuer: InMemorySyntheticReconciliationAuthorizationIssuerV2 = field(
        repr=False
    )
    process_session_anchor: ProtectedSyntheticReconciliationProcessSessionAnchorV2 = field(
        repr=False
    )
    authority: Mapping[str, Any] = field(repr=False)
    authority_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedFreshReconciliationAuthorityV2(<protected>)"


@dataclass(frozen=True, repr=False)
class ProtectedReconciliationResolutionReceiptV2:
    obligation: obligation_v2.ProtectedReconciliationObligationV2 = field(repr=False)
    fresh_authority: ProtectedFreshReconciliationAuthorityV2 = field(repr=False)
    protected_restart_barrier: Any = field(repr=False)
    terminal_resolution_evidence: Mapping[str, Any] = field(repr=False)
    single_use_consumption_receipt: Mapping[str, Any] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReconciliationResolutionReceiptV2(<protected>)"


@dataclass(frozen=True)
class DormantProtectedReconciliationResolutionConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_obligation_sha256: str | None = field(default=None, repr=False)
    expected_restart_barrier_sha256: str | None = field(default=None, repr=False)
    maximum_authority_ttl_seconds: int = 300

    def __post_init__(self) -> None:
        if not 1 <= self.maximum_authority_ttl_seconds <= 300:
            raise ValueError("maximum_authority_ttl_seconds must be between 1 and 300")


def _authorization_receipt_valid(
    value: Any, obligation_sha256: str, now_epoch: int, maximum_ttl: int
) -> bool:
    if type(value) is not dict or set(value) != _AUTH_RECEIPT_KEYS:
        return False
    try:
        return bool(
            value["receipt_version"] == RECONCILIATION_AUTHORIZATION_RECEIPT_VERSION_V2
            and _valid_sha(value["grant_sha256"])
            and value["subject_binding_sha256"] == obligation_sha256
            and value["authorized_action"] == RECONCILIATION_AUTHORIZED_ACTION_V2
            and value["consumption_count"] == 1
            and type(value["consumed_at_epoch"]) is int
            and type(value["expires_at_epoch"]) is int
            and value["consumed_at_epoch"] <= now_epoch < value["expires_at_epoch"]
            and 0 < value["expires_at_epoch"] - value["consumed_at_epoch"] <= maximum_ttl
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and _valid_sha(value["receipt_sha256"])
            and hmac.compare_digest(
                value["receipt_sha256"],
                reconciliation_authorization_receipt_sha256_v2(value),
            )
        )
    except Exception:
        return False


def fresh_reconciliation_authority_valid_v2(
    value: Any,
    obligation: obligation_v2.ProtectedReconciliationObligationV2,
    *,
    now_epoch: int,
    maximum_ttl_seconds: int = 300,
    expected_single_use_ledger: InMemorySyntheticReconciliationResolutionLedgerV2 | None = None,
    expected_authorization_issuer: InMemorySyntheticReconciliationAuthorizationIssuerV2 | None = None,
) -> bool:
    if type(value) is not ProtectedFreshReconciliationAuthorityV2:
        return False
    if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
        return False
    authority = value.authority
    if type(authority) is not dict or set(authority) != _AUTHORITY_KEYS:
        return False
    receipt = value.authorization_receipt
    permit = value.maintenance_permit
    token = value.live_lease_token
    witness = value.lease_witness
    ledger = value.single_use_ledger
    issuer = value.authorization_issuer
    session_anchor = value.process_session_anchor
    original = obligation.adapter_plan
    try:
        permit_sha = backend_v2.stable_sha256_v2(_permit_binding(permit))
        return bool(
            type(permit) is coordinator_v1.WriterMaintenancePermitV1
            and type(token) is consumer_v1.ProtectedSyntheticLiveLeaseTokenV1
            and type(witness) is consumer_v1.InMemoryLiveMaintenanceLeaseWitnessV1
            and type(ledger) is InMemorySyntheticReconciliationResolutionLedgerV2
            and type(issuer) is InMemorySyntheticReconciliationAuthorizationIssuerV2
            and type(session_anchor) is ProtectedSyntheticReconciliationProcessSessionAnchorV2
            and (
                expected_single_use_ledger is None
                or ledger is expected_single_use_ledger
            )
            and (
                expected_authorization_issuer is None
                or issuer is expected_authorization_issuer
            )
            and issuer.resolution_ledger is ledger
            and issuer.process_session_anchor is session_anchor
            and _authorization_receipt_valid(
                receipt, obligation.obligation_sha256, now_epoch, maximum_ttl_seconds
            )
            and issuer.receipt_was_issued(receipt)
            and receipt["authorization_issuer_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_authorization_issuer_v2", issuer
            )
            and receipt["resolution_ledger_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_resolution_ledger_v2", ledger
            )
            and receipt["process_session_anchor_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_process_session_anchor_v2",
                session_anchor,
            )
            and receipt["receipt_sha256"]
            != obligation.obligation["authorization_receipt_sha256"]
            and permit is not original.maintenance_permit
            and token is not original.live_lease_token
            and witness is not original.lease_witness
            and permit.maintenance_epoch != original.maintenance_permit.maintenance_epoch
            and permit.state == "QUIESCED"
            and permit.lock_namespace_sha256
            == coordinator_v1.canonical_runtime_lock_namespace_v1()
            and permit.registered_writer_count == 19
            and permit.inflight_mutations == 0
            and permit.shared_lock_acquired is True
            and token.permit_binding_sha256 == permit_sha
            and now_epoch < token.expires_at_epoch
            and authority["authority_version"] == FRESH_RECONCILIATION_AUTHORITY_VERSION_V2
            and authority["scope_attestation"]
            == OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2
            and authority["obligation_sha256"] == obligation.obligation_sha256
            and authority["subject_binding_sha256"] == obligation.obligation_sha256
            and authority["authorization_receipt_sha256"] == receipt["receipt_sha256"]
            and authority["maintenance_epoch"] == permit.maintenance_epoch
            and authority["permit_binding_sha256"] == permit_sha
            and authority["permit_object_identity_sha256"]
            == _identity_sha("fresh_reconciliation_permit_v2", permit)
            and authority["lease_token_sha256"] == token.token_sha256
            and authority["lease_token_object_identity_sha256"]
            == _identity_sha("fresh_reconciliation_lease_token_v2", token)
            and authority["lease_witness_object_identity_sha256"]
            == _identity_sha("fresh_reconciliation_lease_witness_v2", witness)
            and authority["single_use_ledger_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_resolution_ledger_v2", ledger
            )
            and authority["authorization_issuer_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_authorization_issuer_v2", issuer
            )
            and authority["process_session_anchor_object_identity_sha256"]
            == _identity_sha(
                "synthetic_reconciliation_process_session_anchor_v2",
                session_anchor,
            )
            and authority["issued_at_epoch"] == receipt["consumed_at_epoch"]
            and authority["expires_at_epoch"]
            == min(receipt["expires_at_epoch"], token.expires_at_epoch)
            and now_epoch < authority["expires_at_epoch"]
            and authority["single_use"] is True
            and authority["fresh_from_original"] is True
            and authority["synthetic_only"] is True
            and authority["production_authority"] is False
            and authority["runtime_integrated"] is False
            and value.authority_sha256 == authority["authority_sha256"]
            and _valid_sha(authority["authority_sha256"])
            and hmac.compare_digest(
                authority["authority_sha256"],
                fresh_reconciliation_authority_sha256_v2(authority),
            )
        )
    except Exception:
        return False


def terminal_resolution_evidence_valid_v2(
    value: Any,
    obligation: obligation_v2.ProtectedReconciliationObligationV2,
    fresh_authority: ProtectedFreshReconciliationAuthorityV2,
    *,
    now_epoch: int,
) -> bool:
    if type(value) is not dict or set(value) != _TERMINAL_KEYS:
        return False
    record = obligation.obligation
    request = obligation.adapter_plan.protected_request.request
    try:
        return bool(
            value["evidence_version"] == TERMINAL_RESOLUTION_EVIDENCE_VERSION_V2
            and value["obligation_sha256"] == obligation.obligation_sha256
            and value["obligation_id_sha256"] == record["obligation_id_sha256"]
            and value["source_evidence_sha256"] == record["source_evidence_sha256"]
            and value["adapter_plan_sha256"] == record["adapter_plan_sha256"]
            and value["request_binding_sha256"] == record["request_binding_sha256"]
            and value["request_sha256"] == record["request_sha256"]
            and value["transaction_sha256"] == record["transaction_sha256"]
            and value["idempotency_key_sha256"] == record["idempotency_key_sha256"]
            and value["backend_instance_sha256"] == request["backend_instance_sha256"]
            and value["original_terminal_result_sha256"]
            == obligation.source_evidence["terminal_result_sha256"]
            and value["fresh_authority_sha256"] == fresh_authority.authority_sha256
            and value["fresh_authorization_receipt_sha256"]
            == fresh_authority.authorization_receipt["receipt_sha256"]
            and value["fresh_maintenance_epoch"]
            == fresh_authority.maintenance_permit.maintenance_epoch
            and value["fresh_lease_token_sha256"]
            == fresh_authority.live_lease_token.token_sha256
            and value["single_use_ledger_object_identity_sha256"]
            == fresh_authority.authority[
                "single_use_ledger_object_identity_sha256"
            ]
            and value["observed_under_fresh_lease"] is True
            and value["terminal_state"] in {"COMMITTED", "ABORTED", "ROLLED_BACK"}
            and type(value["reconciled_at_epoch"]) is int
            and value["reconciled_at_epoch"] == now_epoch
            and now_epoch >= record["created_at_epoch"]
            and value["same_transaction_identity_verified"] is True
            and value["terminal_state_verified"] is True
            and value["postconditions_verified"] is True
            and value["recovery_required"] is False
            and value["new_apply_allowed"] is False
            and value["retry_allowed"] is False
            and value["backend_called"] is False
            and value["registry_write"] is False
            and value["write_executed"] is False
            and value["synthetic_only"] is True
            and value["production_evidence"] is False
            and _valid_sha(value["evidence_sha256"])
            and hmac.compare_digest(
                value["evidence_sha256"], terminal_resolution_evidence_sha256_v2(value)
            )
        )
    except Exception:
        return False


def single_use_resolution_consumption_valid_v2(
    value: Any,
    obligation: obligation_v2.ProtectedReconciliationObligationV2,
    authority: ProtectedFreshReconciliationAuthorityV2,
    terminal_evidence: Mapping[str, Any],
    *,
    now_epoch: int,
) -> bool:
    if type(value) is not dict or set(value) != _SINGLE_USE_CONSUMPTION_KEYS:
        return False
    try:
        return bool(
            value["consumption_version"]
            == "C3_SYNTHETIC_RECONCILIATION_RESOLUTION_CONSUMPTION_V2"
            and value["obligation_sha256"] == obligation.obligation_sha256
            and value["authorization_receipt_sha256"]
            == authority.authorization_receipt["receipt_sha256"]
            and value["fresh_authority_sha256"] == authority.authority_sha256
            and value["single_use_ledger_object_identity_sha256"]
            == authority.authority["single_use_ledger_object_identity_sha256"]
            and value["terminal_resolution_evidence_sha256"]
            == terminal_evidence["evidence_sha256"]
            and value["consumption_count"] == 1
            and value["consumed_at_epoch"] == now_epoch
            and value["in_memory_only"] is True
            and value["durable"] is False
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and _valid_sha(value["consumption_sha256"])
            and hmac.compare_digest(
                value["consumption_sha256"],
                single_use_resolution_consumption_sha256_v2(value),
            )
        )
    except Exception:
        return False


def protected_reconciliation_resolution_receipt_valid_v2(value: Any) -> bool:
    if type(value) is not ProtectedReconciliationResolutionReceiptV2:
        return False
    obligation = value.obligation
    authority = value.fresh_authority
    receipt = value.receipt
    if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
        return False
    if not terminal_resolution_evidence_valid_v2(
        value.terminal_resolution_evidence,
        obligation,
        authority,
        now_epoch=receipt.get("resolved_at_epoch") if type(receipt) is dict else -1,
    ):
        return False
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        return False
    record = obligation.obligation
    evidence = value.terminal_resolution_evidence
    consumption = value.single_use_consumption_receipt
    try:
        import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2

        return bool(
            barrier_v2.protected_reconciliation_restart_barrier_valid_v2(
                value.protected_restart_barrier
            )
            and value.protected_restart_barrier.obligation is obligation
            and value.protected_restart_barrier.reference_authority is authority
            and
            fresh_reconciliation_authority_valid_v2(
                authority,
                obligation,
                now_epoch=receipt["resolved_at_epoch"],
                expected_single_use_ledger=authority.single_use_ledger,
                expected_authorization_issuer=authority.authorization_issuer,
            )
            and
            receipt["receipt_version"]
            == PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_VERSION_V2
            and receipt["scope_attestation"]
            == OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2
            and receipt["obligation_sha256"] == obligation.obligation_sha256
            and receipt["obligation_id_sha256"] == record["obligation_id_sha256"]
            and receipt["source_evidence_sha256"] == record["source_evidence_sha256"]
            and receipt["adapter_plan_sha256"] == record["adapter_plan_sha256"]
            and receipt["request_sha256"] == record["request_sha256"]
            and receipt["transaction_sha256"] == record["transaction_sha256"]
            and receipt["fresh_authority_sha256"] == authority.authority_sha256
            and receipt["fresh_authorization_receipt_sha256"]
            == authority.authorization_receipt["receipt_sha256"]
            and receipt["fresh_maintenance_epoch"]
            == authority.maintenance_permit.maintenance_epoch
            and receipt["fresh_lease_token_sha256"]
            == authority.live_lease_token.token_sha256
            and receipt["restart_barrier_sha256"]
            == value.protected_restart_barrier.barrier_sha256
            and receipt["restart_barrier_continuity_verified"] is True
            and receipt["single_use_ledger_object_identity_sha256"]
            == authority.authority["single_use_ledger_object_identity_sha256"]
            and single_use_resolution_consumption_valid_v2(
                consumption,
                obligation,
                authority,
                evidence,
                now_epoch=receipt["resolved_at_epoch"],
            )
            and receipt["single_use_consumption_receipt_sha256"]
            == consumption["consumption_sha256"]
            and receipt["terminal_resolution_evidence_sha256"]
            == evidence["evidence_sha256"]
            and receipt["terminal_state"] == evidence["terminal_state"]
            and receipt["resolved_at_epoch"] == evidence["reconciled_at_epoch"]
            and receipt["resolution_state"] == "RESOLVED"
            and receipt["reconciliation_required"] is False
            and receipt["same_transaction_identity_verified"] is True
            and receipt["fresh_authority_verified"] is True
            and receipt["terminal_resolution_verified"] is True
            and receipt["original_authorization_reused"] is False
            and receipt["new_apply_allowed"] is False
            and receipt["retry_allowed"] is False
            and all(
                receipt[key] is False
                for key in (
                    "backend_bound", "backend_called", "registry_write", "write_executed",
                    "filesystem_accessed", "real_registry_accessed", "network_accessed",
                    "broker_called", "production_authority", "runtime_integrated",
                    "activation_allowed", "live_allowed",
                )
            )
            and receipt["synthetic_only"] is True
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and _valid_sha(receipt["receipt_sha256"])
            and hmac.compare_digest(
                receipt["receipt_sha256"],
                protected_reconciliation_resolution_receipt_sha256_v2(receipt),
            )
        )
    except Exception:
        return False


class DormantProtectedReconciliationResolutionContractV2:
    def __init__(
        self,
        config: DormantProtectedReconciliationResolutionConfigV2 | None = None,
        *,
        single_use_ledger: InMemorySyntheticReconciliationResolutionLedgerV2 | None = None,
        authorization_issuer: InMemorySyntheticReconciliationAuthorizationIssuerV2 | None = None,
        protected_restart_barrier: Any = None,
    ) -> None:
        self._config = config or DormantProtectedReconciliationResolutionConfigV2()
        self._single_use_ledger = single_use_ledger
        self._authorization_issuer = authorization_issuer
        self._protected_restart_barrier = protected_restart_barrier

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PROTECTED_RECONCILIATION_RESOLUTION_V2_BLOCKED",
            "reason": reason,
            "protected_receipt": None,
            "restart_barrier_reason": None,
            "restart_barrier_evaluation_count": 0,
            "lease_revalidation_count": 0,
            "single_use_consumption_count": 0,
            "backend_called": False,
            "provider_called": False,
            "store_called": False,
            "writer_called": False,
            "lock_acquired": False,
            "registry_write": False,
            "write_executed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "no_order_sent": True,
        }

    @classmethod
    def _failed_after_restart_barrier(cls, reason: str) -> dict[str, Any]:
        failed = cls._failed(reason)
        failed["restart_barrier_evaluation_count"] = 1
        return failed

    def resolve_offline(
        self,
        obligation: obligation_v2.ProtectedReconciliationObligationV2,
        fresh_authority: ProtectedFreshReconciliationAuthorityV2,
        terminal_resolution_evidence: Mapping[str, Any],
        *,
        now_epoch: int,
        protected_restart_barrier: Any = None,
        session_loss_declared: bool = False,
        durable_authority_evidence: Any = None,
    ) -> dict[str, Any]:
        if not self._config.enabled:
            return self._failed("PROTECTED_RECONCILIATION_RESOLUTION_V2_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2:
            return self._failed("PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_REQUIRED")
        if not obligation_v2.protected_reconciliation_obligation_valid_v2(obligation):
            return self._failed("OPEN_PROTECTED_RECONCILIATION_OBLIGATION_REQUIRED")
        if not (
            _valid_sha(self._config.expected_obligation_sha256)
            and hmac.compare_digest(
                str(self._config.expected_obligation_sha256), obligation.obligation_sha256
            )
        ):
            return self._failed("PROTECTED_RECONCILIATION_OBLIGATION_PIN_MISMATCH")
        if type(now_epoch) is not int:
            return self._failed("INTEGER_NOW_EPOCH_REQUIRED")
        if not _valid_sha(self._config.expected_restart_barrier_sha256):
            return self._failed("EXPECTED_PROTECTED_RESTART_BARRIER_SHA256_REQUIRED")
        try:
            import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2 as barrier_v2
        except Exception:
            return self._failed("PROTECTED_RESTART_BARRIER_CONTRACT_UNAVAILABLE")
        if type(self._protected_restart_barrier) is not barrier_v2.ProtectedReconciliationRestartBarrierV2:
            return self._failed("PINNED_PROTECTED_RESTART_BARRIER_REQUIRED")
        if protected_restart_barrier is not self._protected_restart_barrier:
            return self._failed("PROTECTED_RESTART_BARRIER_INSTANCE_NOT_PINNED")
        if not barrier_v2.protected_reconciliation_restart_barrier_valid_v2(
            protected_restart_barrier
        ):
            return self._failed("PROTECTED_RESTART_BARRIER_INVALID")
        if not hmac.compare_digest(
            str(self._config.expected_restart_barrier_sha256),
            protected_restart_barrier.barrier_sha256,
        ):
            return self._failed("PROTECTED_RESTART_BARRIER_PIN_MISMATCH")
        barrier_contract = barrier_v2.DormantProtectedReconciliationRestartBarrierContractV2(
            barrier_v2.DormantProtectedReconciliationRestartBarrierConfigV2(
                enabled=True,
                scope_attestation=barrier_v2.OFFLINE_PROTECTED_RECONCILIATION_RESTART_BARRIER_SCOPE_ATTESTATION_V2,
                expected_obligation_sha256=obligation.obligation_sha256,
                expected_reference_authority_sha256=protected_restart_barrier.reference_authority.authority_sha256,
                maximum_authority_ttl_seconds=self._config.maximum_authority_ttl_seconds,
            )
        )
        barrier_result = barrier_contract.evaluate_offline(
            protected_restart_barrier,
            fresh_authority,
            session_loss_declared=session_loss_declared,
            now_epoch=now_epoch,
            durable_authority_evidence=durable_authority_evidence,
        )
        if not (
            barrier_result.get("ok") is True
            and barrier_result.get("barrier_passed_offline") is True
            and barrier_result.get("original_session_continuity_confirmed") is True
        ):
            failed = self._failed("PROTECTED_RESTART_BARRIER_REJECTED")
            failed["restart_barrier_reason"] = barrier_result.get("reason")
            failed["restart_barrier_evaluation_count"] = 1
            return failed
        if type(self._single_use_ledger) is not InMemorySyntheticReconciliationResolutionLedgerV2:
            return self._failed_after_restart_barrier("SYNTHETIC_SINGLE_USE_LEDGER_REQUIRED")
        if type(self._authorization_issuer) is not InMemorySyntheticReconciliationAuthorizationIssuerV2:
            return self._failed_after_restart_barrier("SYNTHETIC_SINGLE_USE_AUTHORIZATION_ISSUER_REQUIRED")
        if not fresh_reconciliation_authority_valid_v2(
            fresh_authority,
            obligation,
            now_epoch=now_epoch,
            maximum_ttl_seconds=self._config.maximum_authority_ttl_seconds,
            expected_single_use_ledger=self._single_use_ledger,
            expected_authorization_issuer=self._authorization_issuer,
        ):
            return self._failed_after_restart_barrier("FRESH_RECONCILIATION_AUTHORITY_INVALID")
        try:
            lease_live = fresh_authority.lease_witness.validate_live(
                fresh_authority.maintenance_permit,
                fresh_authority.live_lease_token,
                now_epoch=now_epoch,
            )
        except Exception:
            return self._failed_after_restart_barrier("FRESH_RECONCILIATION_LEASE_VALIDATION_FAILED")
        if lease_live is not True:
            return self._failed_after_restart_barrier("FRESH_RECONCILIATION_LEASE_NOT_LIVE")
        if not terminal_resolution_evidence_valid_v2(
            terminal_resolution_evidence,
            obligation,
            fresh_authority,
            now_epoch=now_epoch,
        ):
            failed = self._failed("TERMINAL_RESOLUTION_EVIDENCE_INVALID")
            failed["restart_barrier_evaluation_count"] = 1
            failed["lease_revalidation_count"] = 1
            return failed
        record = obligation.obligation
        evidence = terminal_resolution_evidence
        consumption = self._single_use_ledger.consume_once(
            obligation_sha256=obligation.obligation_sha256,
            authorization_receipt_sha256=fresh_authority.authorization_receipt[
                "receipt_sha256"
            ],
            fresh_authority_sha256=fresh_authority.authority_sha256,
            terminal_resolution_evidence_sha256=evidence["evidence_sha256"],
            now_epoch=now_epoch,
        )
        if consumption is None:
            failed = self._failed("FRESH_RECONCILIATION_AUTHORITY_ALREADY_CONSUMED")
            failed["restart_barrier_evaluation_count"] = 1
            failed["lease_revalidation_count"] = 1
            return failed
        receipt = {
            "receipt_version": PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_VERSION_V2,
            "scope_attestation": OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2,
            "obligation_sha256": obligation.obligation_sha256,
            "obligation_id_sha256": record["obligation_id_sha256"],
            "source_evidence_sha256": record["source_evidence_sha256"],
            "adapter_plan_sha256": record["adapter_plan_sha256"],
            "request_sha256": record["request_sha256"],
            "transaction_sha256": record["transaction_sha256"],
            "fresh_authority_sha256": fresh_authority.authority_sha256,
            "fresh_authorization_receipt_sha256": fresh_authority.authorization_receipt["receipt_sha256"],
            "fresh_maintenance_epoch": fresh_authority.maintenance_permit.maintenance_epoch,
            "fresh_lease_token_sha256": fresh_authority.live_lease_token.token_sha256,
            "restart_barrier_sha256": protected_restart_barrier.barrier_sha256,
            "restart_barrier_continuity_verified": True,
            "single_use_ledger_object_identity_sha256": fresh_authority.authority[
                "single_use_ledger_object_identity_sha256"
            ],
            "single_use_consumption_receipt_sha256": consumption[
                "consumption_sha256"
            ],
            "terminal_resolution_evidence_sha256": evidence["evidence_sha256"],
            "terminal_state": evidence["terminal_state"],
            "resolved_at_epoch": evidence["reconciled_at_epoch"],
            "resolution_state": "RESOLVED",
            "reconciliation_required": False,
            "same_transaction_identity_verified": True,
            "fresh_authority_verified": True,
            "terminal_resolution_verified": True,
            "original_authorization_reused": False,
            "new_apply_allowed": False,
            "retry_allowed": False,
            "backend_bound": False,
            "backend_called": False,
            "registry_write": False,
            "write_executed": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "synthetic_only": True,
            "production_authority": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }
        receipt["receipt_sha256"] = protected_reconciliation_resolution_receipt_sha256_v2(receipt)
        protected = ProtectedReconciliationResolutionReceiptV2(
            obligation=obligation,
            fresh_authority=fresh_authority,
            protected_restart_barrier=protected_restart_barrier,
            terminal_resolution_evidence=copy.deepcopy(dict(evidence)),
            single_use_consumption_receipt=copy.deepcopy(consumption),
            receipt=copy.deepcopy(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_reconciliation_resolution_receipt_valid_v2(protected):
            failed = self._failed("PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_INTERNAL_INVALID")
            failed["restart_barrier_evaluation_count"] = 1
            failed["lease_revalidation_count"] = 1
            failed["single_use_consumption_count"] = 1
            return failed
        result = self._failed("")
        result.update(
            {
                "ok": True,
                "status": "PROTECTED_RECONCILIATION_RESOLVED_OFFLINE",
                "reason": None,
                "protected_receipt": protected,
                "receipt_sha256": protected.receipt_sha256,
                "terminal_state": evidence["terminal_state"],
                "resolution_state": "RESOLVED",
                "reconciliation_required": False,
                "restart_barrier_evaluation_count": 1,
                "lease_revalidation_count": 1,
                "single_use_consumption_count": 1,
            }
        )
        return result


__all__ = [
    "DormantProtectedReconciliationResolutionConfigV2",
    "DormantProtectedReconciliationResolutionContractV2",
    "FRESH_RECONCILIATION_AUTHORITY_VERSION_V2",
    "InMemorySyntheticReconciliationAuthorizationIssuerV2",
    "InMemorySyntheticReconciliationResolutionLedgerV2",
    "OFFLINE_PROTECTED_RECONCILIATION_RESOLUTION_SCOPE_ATTESTATION_V2",
    "PROTECTED_RECONCILIATION_RESOLUTION_RECEIPT_VERSION_V2",
    "ProtectedFreshReconciliationAuthorityV2",
    "ProtectedReconciliationResolutionReceiptV2",
    "ProtectedSyntheticReconciliationProcessSessionAnchorV2",
    "RECONCILIATION_AUTHORIZATION_RECEIPT_VERSION_V2",
    "RECONCILIATION_AUTHORIZED_ACTION_V2",
    "TERMINAL_RESOLUTION_EVIDENCE_VERSION_V2",
    "fresh_reconciliation_authority_sha256_v2",
    "fresh_reconciliation_authority_valid_v2",
    "protected_reconciliation_resolution_receipt_sha256_v2",
    "protected_reconciliation_resolution_receipt_valid_v2",
    "reconciliation_authorization_receipt_sha256_v2",
    "single_use_resolution_consumption_sha256_v2",
    "single_use_resolution_consumption_valid_v2",
    "terminal_resolution_evidence_sha256_v2",
    "terminal_resolution_evidence_valid_v2",
]
