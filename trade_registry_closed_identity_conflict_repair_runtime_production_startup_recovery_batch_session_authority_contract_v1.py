"""Dormant batch-session authority projection for startup recovery.

The contract aggregates already-protected synthetic restart admissions under
one process-local maintenance session.  It performs no ledger, backend,
Registry, filesystem, network, or runtime call and never grants recovery or
production authority.  Current durable state and live-lease checks remain
mandatory at the future operational boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2 as admission_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as authority_binding_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-BATCH-SESSION-AUTHORITY-CONTRACT-V1"
)
OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_OFFLINE_ONLY_V1"
)
PROTECTED_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PENDING_STATES = frozenset({"PREPARED", "RESOLVED"})
_PENDING_ITEM_KEYS = frozenset(
    {
        "source_state",
        "transaction_sha256",
        "obligation_sha256",
        "restart_admission_sha256",
        "durable_authority_receipt_sha256",
        "item_sha256",
    }
)
_RECEIPT_KEYS = frozenset(
    {
        "receipt_version",
        "scope_attestation",
        "authenticated_authority_binding_sha256",
        "schema_sha256",
        "provider_binding_sha256",
        "pending_catalog_binding_sha256",
        "pending_items",
        "pending_item_count",
        "transaction_set_sha256",
        "obligation_set_sha256",
        "restart_admission_set_sha256",
        "durable_authority_receipt_set_sha256",
        "durable_root_identity_sha256",
        "durable_storage_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "candidate_maintenance_lease_receipt_sha256",
        "permit_binding_sha256",
        "lease_token_sha256",
        "lease_expires_at_epoch",
        "permit_object_identity_sha256",
        "lease_token_object_identity_sha256",
        "lease_witness_object_identity_sha256",
        "session_anchor_object_identity_sha256",
        "authorization_issuer_object_identity_sha256",
        "single_use_ledger_object_identity_sha256",
        "issued_at_epoch",
        "expires_at_epoch",
        "same_permit_instance_verified",
        "same_lease_token_instance_verified",
        "same_lease_witness_instance_verified",
        "same_session_anchor_instance_verified",
        "same_authorization_issuer_instance_verified",
        "same_single_use_ledger_instance_verified",
        "same_backend_instance_verified",
        "same_registry_path_binding_verified",
        "same_lock_namespace_verified",
        "same_maintenance_epoch_verified",
        "durable_current_state_verified_at_admission",
        "fresh_quiesced_lease_verified_at_admission",
        "live_lease_revalidation_required",
        "durable_current_state_revalidation_required",
        "per_item_single_use_required",
        "catalog_scope_bound",
        "cryptographic_binding_reused",
        "complete_catalog_evidence_created",
        "production_root_authority_verified",
        "recovery_authority_granted",
        "evidence_population_allowed",
        "production_blockers",
        "filesystem_accessed",
        "real_registry_accessed",
        "network_accessed",
        "broker_called",
        "write_executed",
        "registry_write",
        "no_order_sent",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "receipt_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "BATCH_SESSION_RECEIPT_IS_SYNTHETIC_AND_NOT_PRODUCTION_SIGNED",
    "PRODUCTION_ROOT_AUTHORITY_REMAINS_UNVERIFIED",
    "LIVE_LEASE_NOT_REVALIDATED_AT_BATCH_BOUNDARY",
    "DURABLE_AUTHORITY_CURRENT_STATE_NOT_REVALIDATED_AT_BATCH_BOUNDARY",
    "PRODUCTION_MAINTENANCE_LEASE_RECEIPT_NOT_IMPLEMENTED",
    "COMPLETE_PREPARED_AND_RESOLVED_CATALOG_EVIDENCE_NOT_ATTACHED",
    "EMPIRICAL_DURABILITY_EVIDENCE_NOT_ATTACHED",
    "EVIDENCE_POPULATION_AND_RECOVERY_EXECUTION_REMAIN_FORBIDDEN",
    "RUNTIME_READINESS_AND_LIVE_REMAIN_FORBIDDEN",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def _hash_without(value: Mapping[str, Any], field_name: str) -> str:
    return _stable_sha256(
        {key: item for key, item in value.items() if key != field_name}
    )


def startup_recovery_batch_pending_item_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("pending item must be a mapping")
    return _hash_without(value, "item_sha256")


def startup_recovery_batch_pending_catalog_binding_sha256_v1(
    pending_items: Sequence[Mapping[str, Any]],
) -> str:
    if not isinstance(pending_items, (list, tuple)):
        raise TypeError("pending items must be a sequence")
    return _stable_sha256(
        {
            "kind": "C3_STARTUP_RECOVERY_BATCH_PENDING_CATALOG_BINDING_V1",
            "pending_items": list(pending_items),
        }
    )


def startup_recovery_batch_maintenance_lease_receipt_sha256_v1(
    protected_admission: admission_v2.ProtectedDurableRestartAdmissionV2,
) -> str:
    if not admission_v2.protected_durable_restart_admission_valid_v2(
        protected_admission
    ):
        raise ValueError("valid protected restart admission required")
    fresh = protected_admission.fresh_authority
    authority = fresh.authority
    permit = fresh.maintenance_permit
    return _stable_sha256(
        {
            "kind": "C3_STARTUP_RECOVERY_BATCH_MAINTENANCE_LEASE_REFERENCE_V1",
            "maintenance_epoch": authority["maintenance_epoch"],
            "lock_namespace_sha256": permit.lock_namespace_sha256,
            "permit_binding_sha256": authority["permit_binding_sha256"],
            "permit_object_identity_sha256": authority[
                "permit_object_identity_sha256"
            ],
            "lease_token_sha256": authority["lease_token_sha256"],
            "lease_token_object_identity_sha256": authority[
                "lease_token_object_identity_sha256"
            ],
            "lease_witness_object_identity_sha256": authority[
                "lease_witness_object_identity_sha256"
            ],
            "process_session_anchor_object_identity_sha256": authority[
                "process_session_anchor_object_identity_sha256"
            ],
            "authorization_issuer_object_identity_sha256": authority[
                "authorization_issuer_object_identity_sha256"
            ],
            "single_use_ledger_object_identity_sha256": authority[
                "single_use_ledger_object_identity_sha256"
            ],
            "expires_at_epoch": authority["expires_at_epoch"],
            "synthetic_only": True,
        }
    )


def startup_recovery_batch_session_authority_receipt_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("receipt must be a mapping")
    return _hash_without(value, "receipt_sha256")


def _pending_items(
    protected_admissions: Sequence[
        admission_v2.ProtectedDurableRestartAdmissionV2
    ],
    pending_states_by_transaction: Mapping[str, str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for protected in protected_admissions:
        record = protected.admission
        transaction_sha256 = record["transaction_sha256"]
        item = {
            "source_state": pending_states_by_transaction[transaction_sha256],
            "transaction_sha256": transaction_sha256,
            "obligation_sha256": record["obligation_sha256"],
            "restart_admission_sha256": protected.admission_sha256,
            "durable_authority_receipt_sha256": (
                protected.durable_authority_receipt.receipt_sha256
            ),
        }
        item["item_sha256"] = startup_recovery_batch_pending_item_sha256_v1(
            item
        )
        items.append(item)
    return sorted(items, key=lambda item: item["transaction_sha256"])


def _pending_item_valid(value: Any) -> bool:
    if type(value) is not dict or set(value) != _PENDING_ITEM_KEYS:
        return False
    try:
        return bool(
            value["source_state"] in _PENDING_STATES
            and all(
                _valid_sha256(value[field_name])
                for field_name in (
                    "transaction_sha256",
                    "obligation_sha256",
                    "restart_admission_sha256",
                    "durable_authority_receipt_sha256",
                    "item_sha256",
                )
            )
            and hmac.compare_digest(
                value["item_sha256"],
                startup_recovery_batch_pending_item_sha256_v1(value),
            )
        )
    except Exception:
        return False


def _source_contexts(
    protected_admissions: Any,
) -> list[dict[str, Any]] | None:
    if not isinstance(protected_admissions, (list, tuple)) or not protected_admissions:
        return None
    contexts: list[dict[str, Any]] = []
    for protected in protected_admissions:
        if not admission_v2.protected_durable_restart_admission_valid_v2(
            protected
        ):
            return None
        admission = protected.admission
        fresh = protected.fresh_authority
        authority = fresh.authority
        request = protected.obligation.adapter_plan.protected_request.request
        contexts.append(
            {
                "protected": protected,
                "admission": admission,
                "fresh": fresh,
                "authority": authority,
                "request": request,
                "permit": fresh.maintenance_permit,
                "token": fresh.live_lease_token,
                "witness": fresh.lease_witness,
                "session_anchor": fresh.process_session_anchor,
                "issuer": fresh.authorization_issuer,
                "ledger": fresh.single_use_ledger,
            }
        )
    return contexts


def _sources_valid(
    protected_binding: Any,
    protected_admissions: Any,
    pending_states_by_transaction: Any,
    *,
    now_epoch: int,
    expected_count: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    if not authority_binding_v1.protected_startup_recovery_authenticated_authority_binding_valid_v1(
        protected_binding
    ):
        return [], [], "AUTHENTICATED_AUTHORITY_BINDING_INVALID"
    contexts = _source_contexts(protected_admissions)
    if contexts is None:
        return [], [], "PROTECTED_RESTART_ADMISSIONS_INVALID"
    if type(now_epoch) is not int or len(contexts) != expected_count:
        return [], [], "BATCH_SIZE_OR_TIME_INVALID"
    transactions = [ctx["admission"]["transaction_sha256"] for ctx in contexts]
    if len(set(transactions)) != len(transactions):
        return [], [], "DUPLICATE_PENDING_TRANSACTION"
    if not (
        type(pending_states_by_transaction) is dict
        and set(pending_states_by_transaction) == set(transactions)
        and all(state in _PENDING_STATES for state in pending_states_by_transaction.values())
    ):
        return [], [], "PENDING_STATE_BINDING_INVALID"
    binding = protected_binding.binding
    first = contexts[0]
    first_admission = first["admission"]
    first_authority = first["authority"]
    candidate_lease_receipt_sha256 = (
        startup_recovery_batch_maintenance_lease_receipt_sha256_v1(
            first["protected"]
        )
    )
    if not (
        first_admission["fresh_maintenance_epoch"] == binding["maintenance_epoch"]
        and candidate_lease_receipt_sha256
        == binding["maintenance_lease_receipt_sha256"]
    ):
        return [], [], "MAINTENANCE_SESSION_NOT_BOUND"
    for ctx in contexts:
        admission = ctx["admission"]
        authority = ctx["authority"]
        request = ctx["request"]
        if not (
            admission["admitted_at_epoch"] <= now_epoch < admission["expires_at_epoch"]
            and admission["durable_authority_currently_issued_verified"] is True
            and admission["fresh_quiesced_lease_verified"] is True
            and admission["restart_admission_single_use_required"] is True
            and admission["downstream_current_state_revalidation_required"] is True
            and admission["durable_root_identity_sha256"]
            == binding["root_identity_sha256"]
            and admission["durable_storage_binding_sha256"]
            == binding["durable_authority_storage_binding_sha256"]
            and request["backend_instance_sha256"]
            == binding["backend_instance_sha256"]
            and request["registry_path_binding_sha256"]
            == binding["registry_path_binding_sha256"]
            and request["lock_namespace_sha256"]
            == binding["lock_namespace_sha256"]
            and admission["fresh_maintenance_epoch"]
            == binding["maintenance_epoch"]
            and authority["permit_binding_sha256"]
            == first_authority["permit_binding_sha256"]
            and authority["lease_token_sha256"]
            == first_authority["lease_token_sha256"]
            and startup_recovery_batch_maintenance_lease_receipt_sha256_v1(
                ctx["protected"]
            )
            == candidate_lease_receipt_sha256
            and ctx["permit"] is first["permit"]
            and ctx["token"] is first["token"]
            and ctx["witness"] is first["witness"]
            and ctx["session_anchor"] is first["session_anchor"]
            and ctx["issuer"] is first["issuer"]
            and ctx["ledger"] is first["ledger"]
        ):
            return [], [], "BATCH_SESSION_INSTANCE_OR_IDENTITY_MISMATCH"
    items = _pending_items(protected_admissions, pending_states_by_transaction)
    return contexts, items, None


@dataclass(frozen=True)
class DormantStartupRecoveryBatchSessionAuthorityConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_authenticated_authority_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_pending_catalog_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_pending_item_count: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.expected_pending_item_count <= 10_000:
            raise ValueError("expected_pending_item_count must be between 1 and 10000")


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryBatchSessionAuthorityV1:
    authenticated_authority_binding: authority_binding_v1.ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1 = field(
        repr=False
    )
    protected_restart_admissions: tuple[
        admission_v2.ProtectedDurableRestartAdmissionV2, ...
    ] = field(repr=False)
    receipt: Mapping[str, Any] = field(repr=False)
    receipt_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryBatchSessionAuthorityV1(<protected>)"


def protected_startup_recovery_batch_session_authority_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(value, ProtectedStartupRecoveryBatchSessionAuthorityV1):
        return False
    receipt = value.receipt
    if type(receipt) is not dict or set(receipt) != _RECEIPT_KEYS:
        return False
    pending_items = receipt.get("pending_items")
    if not (
        isinstance(pending_items, list)
        and pending_items
        and all(_pending_item_valid(item) for item in pending_items)
        and [item["transaction_sha256"] for item in pending_items]
        == sorted(item["transaction_sha256"] for item in pending_items)
    ):
        return False
    states = {
        item["transaction_sha256"]: item["source_state"]
        for item in pending_items
    }
    contexts, expected_items, failure = _sources_valid(
        value.authenticated_authority_binding,
        value.protected_restart_admissions,
        states,
        now_epoch=receipt.get("issued_at_epoch"),
        expected_count=receipt.get("pending_item_count"),
    )
    if failure is not None or not contexts:
        return False
    binding = value.authenticated_authority_binding.binding
    first = contexts[0]
    admission = first["admission"]
    authority = first["authority"]
    token = first["token"]
    try:
        return bool(
            receipt["receipt_version"]
            == PROTECTED_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_VERSION_V1
            and receipt["scope_attestation"]
            == OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1
            and receipt["authenticated_authority_binding_sha256"]
            == value.authenticated_authority_binding.binding_sha256
            and receipt["schema_sha256"] == binding["schema_sha256"]
            and receipt["provider_binding_sha256"]
            == binding["provider_binding_sha256"]
            and receipt["pending_items"] == expected_items
            and receipt["pending_item_count"] == len(expected_items)
            and receipt["pending_catalog_binding_sha256"]
            == startup_recovery_batch_pending_catalog_binding_sha256_v1(
                expected_items
            )
            and receipt["transaction_set_sha256"]
            == _stable_sha256(
                [item["transaction_sha256"] for item in expected_items]
            )
            and receipt["obligation_set_sha256"]
            == _stable_sha256(
                sorted(item["obligation_sha256"] for item in expected_items)
            )
            and receipt["restart_admission_set_sha256"]
            == _stable_sha256(
                sorted(
                    item["restart_admission_sha256"] for item in expected_items
                )
            )
            and receipt["durable_authority_receipt_set_sha256"]
            == _stable_sha256(
                sorted(
                    item["durable_authority_receipt_sha256"]
                    for item in expected_items
                )
            )
            and receipt["durable_root_identity_sha256"]
            == admission["durable_root_identity_sha256"]
            == binding["root_identity_sha256"]
            and receipt["durable_storage_binding_sha256"]
            == admission["durable_storage_binding_sha256"]
            == binding["durable_authority_storage_binding_sha256"]
            and receipt["backend_instance_sha256"]
            == binding["backend_instance_sha256"]
            and receipt["registry_path_binding_sha256"]
            == binding["registry_path_binding_sha256"]
            and receipt["wal_storage_binding_sha256"]
            == binding["wal_storage_binding_sha256"]
            and receipt["resolved_ledger_storage_binding_sha256"]
            == binding["resolved_ledger_storage_binding_sha256"]
            and receipt["lock_namespace_sha256"]
            == binding["lock_namespace_sha256"]
            and receipt["maintenance_epoch"] == binding["maintenance_epoch"]
            and receipt["candidate_maintenance_lease_receipt_sha256"]
            == binding["maintenance_lease_receipt_sha256"]
            and receipt["permit_binding_sha256"]
            == authority["permit_binding_sha256"]
            and receipt["lease_token_sha256"] == authority["lease_token_sha256"]
            and receipt["lease_expires_at_epoch"] == token.expires_at_epoch
            and receipt["permit_object_identity_sha256"]
            == authority["permit_object_identity_sha256"]
            and receipt["lease_token_object_identity_sha256"]
            == authority["lease_token_object_identity_sha256"]
            and receipt["lease_witness_object_identity_sha256"]
            == authority["lease_witness_object_identity_sha256"]
            and receipt["session_anchor_object_identity_sha256"]
            == authority["process_session_anchor_object_identity_sha256"]
            and receipt["authorization_issuer_object_identity_sha256"]
            == authority["authorization_issuer_object_identity_sha256"]
            and receipt["single_use_ledger_object_identity_sha256"]
            == authority["single_use_ledger_object_identity_sha256"]
            and type(receipt["issued_at_epoch"]) is int
            and receipt["issued_at_epoch"] < receipt["expires_at_epoch"]
            and receipt["expires_at_epoch"]
            == min(ctx["admission"]["expires_at_epoch"] for ctx in contexts)
            and all(
                receipt[field_name] is True
                for field_name in (
                    "same_permit_instance_verified",
                    "same_lease_token_instance_verified",
                    "same_lease_witness_instance_verified",
                    "same_session_anchor_instance_verified",
                    "same_authorization_issuer_instance_verified",
                    "same_single_use_ledger_instance_verified",
                    "same_backend_instance_verified",
                    "same_registry_path_binding_verified",
                    "same_lock_namespace_verified",
                    "same_maintenance_epoch_verified",
                    "durable_current_state_verified_at_admission",
                    "fresh_quiesced_lease_verified_at_admission",
                    "live_lease_revalidation_required",
                    "durable_current_state_revalidation_required",
                    "per_item_single_use_required",
                    "catalog_scope_bound",
                    "cryptographic_binding_reused",
                    "no_order_sent",
                )
            )
            and all(
                receipt[field_name] is False
                for field_name in (
                    "complete_catalog_evidence_created",
                    "production_root_authority_verified",
                    "recovery_authority_granted",
                    "evidence_population_allowed",
                    "filesystem_accessed",
                    "real_registry_accessed",
                    "network_accessed",
                    "broker_called",
                    "write_executed",
                    "registry_write",
                    "production_authority",
                    "production_ready",
                    "runtime_integrated",
                    "recovery_execution_allowed",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and receipt["production_blockers"] == list(_PRODUCTION_BLOCKERS)
            and receipt["synthetic_only"] is True
            and value.receipt_sha256 == receipt["receipt_sha256"]
            and _valid_sha256(receipt["receipt_sha256"])
            and hmac.compare_digest(
                receipt["receipt_sha256"],
                startup_recovery_batch_session_authority_receipt_sha256_v1(
                    receipt
                ),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryBatchSessionAuthorityContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryBatchSessionAuthorityConfigV1 | None = None,
    ) -> None:
        self._config = config or DormantStartupRecoveryBatchSessionAuthorityConfigV1()

    def __repr__(self) -> str:
        return "DormantStartupRecoveryBatchSessionAuthorityContractV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "authenticated_binding_verified": False,
            "restart_admissions_verified": False,
            "batch_identity_verified": False,
            "batch_session_bound": False,
            "recovery_authority_granted": False,
            "evidence_created": False,
            "provider_called": False,
            "store_called": False,
            "backend_called": False,
            "writer_called": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "reasons": [],
            "protected_batch_session": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def _config_reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1
        ):
            return "STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                config.expected_authenticated_authority_binding_sha256,
                config.expected_pending_catalog_binding_sha256,
            )
        ):
            return "STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        protected_authenticated_authority_binding: Any,
        protected_restart_admissions: Any,
        pending_states_by_transaction: Any,
        now_epoch: int,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        config = self._config
        if not (
            authority_binding_v1.protected_startup_recovery_authenticated_authority_binding_valid_v1(
                protected_authenticated_authority_binding
            )
            and hmac.compare_digest(
                protected_authenticated_authority_binding.binding_sha256,
                str(config.expected_authenticated_authority_binding_sha256),
            )
        ):
            result["reasons"].append("AUTHENTICATED_AUTHORITY_BINDING_INVALID")
            return result
        result["authenticated_binding_verified"] = True
        contexts, pending_items, failure = _sources_valid(
            protected_authenticated_authority_binding,
            protected_restart_admissions,
            pending_states_by_transaction,
            now_epoch=now_epoch,
            expected_count=config.expected_pending_item_count,
        )
        if failure is not None:
            result["reasons"].append(failure)
            return result
        result["restart_admissions_verified"] = True
        catalog_binding_sha256 = (
            startup_recovery_batch_pending_catalog_binding_sha256_v1(
                pending_items
            )
        )
        if not hmac.compare_digest(
            catalog_binding_sha256,
            str(config.expected_pending_catalog_binding_sha256),
        ):
            result["reasons"].append("PENDING_CATALOG_BINDING_PIN_MISMATCH")
            return result
        result["batch_identity_verified"] = True
        binding = protected_authenticated_authority_binding.binding
        first = contexts[0]
        admission = first["admission"]
        authority = first["authority"]
        token = first["token"]
        receipt = {
            "receipt_version": PROTECTED_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1,
            "authenticated_authority_binding_sha256": protected_authenticated_authority_binding.binding_sha256,
            "schema_sha256": binding["schema_sha256"],
            "provider_binding_sha256": binding["provider_binding_sha256"],
            "pending_catalog_binding_sha256": catalog_binding_sha256,
            "pending_items": _canonical_copy(pending_items),
            "pending_item_count": len(pending_items),
            "transaction_set_sha256": _stable_sha256(
                [item["transaction_sha256"] for item in pending_items]
            ),
            "obligation_set_sha256": _stable_sha256(
                sorted(item["obligation_sha256"] for item in pending_items)
            ),
            "restart_admission_set_sha256": _stable_sha256(
                sorted(
                    item["restart_admission_sha256"] for item in pending_items
                )
            ),
            "durable_authority_receipt_set_sha256": _stable_sha256(
                sorted(
                    item["durable_authority_receipt_sha256"]
                    for item in pending_items
                )
            ),
            "durable_root_identity_sha256": admission[
                "durable_root_identity_sha256"
            ],
            "durable_storage_binding_sha256": admission[
                "durable_storage_binding_sha256"
            ],
            "backend_instance_sha256": binding["backend_instance_sha256"],
            "registry_path_binding_sha256": binding[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": binding[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": binding[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": binding["lock_namespace_sha256"],
            "maintenance_epoch": binding["maintenance_epoch"],
            "candidate_maintenance_lease_receipt_sha256": binding[
                "maintenance_lease_receipt_sha256"
            ],
            "permit_binding_sha256": authority["permit_binding_sha256"],
            "lease_token_sha256": authority["lease_token_sha256"],
            "lease_expires_at_epoch": token.expires_at_epoch,
            "permit_object_identity_sha256": authority[
                "permit_object_identity_sha256"
            ],
            "lease_token_object_identity_sha256": authority[
                "lease_token_object_identity_sha256"
            ],
            "lease_witness_object_identity_sha256": authority[
                "lease_witness_object_identity_sha256"
            ],
            "session_anchor_object_identity_sha256": authority[
                "process_session_anchor_object_identity_sha256"
            ],
            "authorization_issuer_object_identity_sha256": authority[
                "authorization_issuer_object_identity_sha256"
            ],
            "single_use_ledger_object_identity_sha256": authority[
                "single_use_ledger_object_identity_sha256"
            ],
            "issued_at_epoch": now_epoch,
            "expires_at_epoch": min(
                ctx["admission"]["expires_at_epoch"] for ctx in contexts
            ),
            "same_permit_instance_verified": True,
            "same_lease_token_instance_verified": True,
            "same_lease_witness_instance_verified": True,
            "same_session_anchor_instance_verified": True,
            "same_authorization_issuer_instance_verified": True,
            "same_single_use_ledger_instance_verified": True,
            "same_backend_instance_verified": True,
            "same_registry_path_binding_verified": True,
            "same_lock_namespace_verified": True,
            "same_maintenance_epoch_verified": True,
            "durable_current_state_verified_at_admission": True,
            "fresh_quiesced_lease_verified_at_admission": True,
            "live_lease_revalidation_required": True,
            "durable_current_state_revalidation_required": True,
            "per_item_single_use_required": True,
            "catalog_scope_bound": True,
            "cryptographic_binding_reused": True,
            "complete_catalog_evidence_created": False,
            "production_root_authority_verified": False,
            "recovery_authority_granted": False,
            "evidence_population_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "write_executed": False,
            "registry_write": False,
            "no_order_sent": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        receipt["receipt_sha256"] = (
            startup_recovery_batch_session_authority_receipt_sha256_v1(receipt)
        )
        protected = ProtectedStartupRecoveryBatchSessionAuthorityV1(
            authenticated_authority_binding=protected_authenticated_authority_binding,
            protected_restart_admissions=tuple(protected_restart_admissions),
            receipt=_canonical_copy(receipt),
            receipt_sha256=receipt["receipt_sha256"],
        )
        if not protected_startup_recovery_batch_session_authority_valid_v1(
            protected
        ):
            result["reasons"].append("PROTECTED_BATCH_SESSION_SELF_CHECK_FAILED")
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_BATCH_SESSION_BOUND_DORMANT",
            batch_session_bound=True,
            protected_batch_session=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryBatchSessionAuthorityConfigV1",
    "DormantStartupRecoveryBatchSessionAuthorityContractV1",
    "OFFLINE_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_VERSION_V1",
    "ProtectedStartupRecoveryBatchSessionAuthorityV1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_BATCH_SESSION_AUTHORITY_CONTRACT_V1_VERSION",
    "protected_startup_recovery_batch_session_authority_valid_v1",
    "startup_recovery_batch_maintenance_lease_receipt_sha256_v1",
    "startup_recovery_batch_pending_catalog_binding_sha256_v1",
    "startup_recovery_batch_pending_item_sha256_v1",
    "startup_recovery_batch_session_authority_receipt_sha256_v1",
]
