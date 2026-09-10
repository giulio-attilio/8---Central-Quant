"""Dormant production RESOLVED-authority store contract.

This module cross-binds sanitized, protected projections only.  It reuses the
existing authenticated-authority and multistore-lease contracts, but exposes
no physical store or lifecycle operation.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1 as authenticated_binding_v1
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as multistore_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-RESOLVED-AUTHORITY-STORE-"
    "CONTRACT-OFFLINE-V2"
)
OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2 = (
    "C3_PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_ONLY_V2"
)
PRODUCTION_RESOLVED_AUTHORITY_STORE_BINDING_VERSION_V2 = (
    "C3_PRODUCTION_RESOLVED_AUTHORITY_STORE_BINDING_OFFLINE_V2"
)
PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2 = (
    multistore_v2.EXPECTED_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "store_contract_version",
        "source_durable_authority_contract_version",
        "source_authenticated_authority_binding_version",
        "authenticated_authority_binding_sha256",
        "multistore_lease_binding_sha256",
        "resolved_lock_port_projection_sha256",
        "store_identity_sha256",
        "storage_binding_sha256",
        "lock_namespace_sha256",
        "root_identity_sha256",
        "root_authority_attestation_sha256",
        "root_authority_key_id_sha256",
        "root_authority_key_epoch",
        "previous_root_authority_attestation_sha256",
        "durable_authority_receipt_sha256",
        "durable_authority_record_sha256",
        "root_signature_evidence_verified",
        "root_signature_reverification_required_on_open",
        "root_signature_reverification_required_on_recovery",
        "monotonic_key_epoch_required",
        "previous_attestation_chain_required",
        "root_rotation_compare_and_swap_required",
        "root_rotation_zero_issued_authorities_required",
        "root_revocation_registry_required",
        "root_revocation_recovery_required",
        "snapshot_required",
        "append_only_journal_required",
        "write_ahead_log_required",
        "backup_required",
        "cross_process_lock_required",
        "atomic_replace_required",
        "directory_fsync_required",
        "crash_recovery_required",
        "interrupted_rotation_recovery_required",
        "corruption_fails_closed",
        "unresolved_transactions_block_readiness",
        "same_authenticated_binding_instance_required",
        "same_multistore_binding_instance_required",
        "same_resolved_lock_projection_instance_required",
        "persistent_production_storage_required",
        "physical_store_implementation_bound",
        "production_root_verifier_bound",
        "production_revocation_source_bound",
        "store_open_allowed",
        "store_read_allowed",
        "store_write_allowed",
        "root_rotation_allowed",
        "recovery_allowed",
        "filesystem_accessed",
        "network_accessed",
        "synthetic_contract_only",
        "production_signature_verified",
        "production_authority",
        "production_durable",
        "production_ready",
        "runtime_integrated",
        "activation_allowed",
        "live_allowed",
        "write_executed",
        "registry_write",
        "real_registry_accessed",
        "broker_called",
        "no_order_sent",
        "binding_sha256",
    }
)
_REQUIRED_TRUE = (
    "root_signature_evidence_verified",
    "root_signature_reverification_required_on_open",
    "root_signature_reverification_required_on_recovery",
    "monotonic_key_epoch_required",
    "previous_attestation_chain_required",
    "root_rotation_compare_and_swap_required",
    "root_rotation_zero_issued_authorities_required",
    "root_revocation_registry_required",
    "root_revocation_recovery_required",
    "snapshot_required",
    "append_only_journal_required",
    "write_ahead_log_required",
    "backup_required",
    "cross_process_lock_required",
    "atomic_replace_required",
    "directory_fsync_required",
    "crash_recovery_required",
    "interrupted_rotation_recovery_required",
    "corruption_fails_closed",
    "unresolved_transactions_block_readiness",
    "same_authenticated_binding_instance_required",
    "same_multistore_binding_instance_required",
    "same_resolved_lock_projection_instance_required",
    "persistent_production_storage_required",
    "synthetic_contract_only",
    "no_order_sent",
)
_REQUIRED_FALSE = (
    "physical_store_implementation_bound",
    "production_root_verifier_bound",
    "production_revocation_source_bound",
    "store_open_allowed",
    "store_read_allowed",
    "store_write_allowed",
    "root_rotation_allowed",
    "recovery_allowed",
    "filesystem_accessed",
    "network_accessed",
    "production_signature_verified",
    "production_authority",
    "production_durable",
    "production_ready",
    "runtime_integrated",
    "activation_allowed",
    "live_allowed",
    "write_executed",
    "registry_write",
    "real_registry_accessed",
    "broker_called",
)
_PRODUCTION_BLOCKERS = (
    "PHYSICAL_PRODUCTION_STORE_IMPLEMENTATION_IS_NOT_BOUND",
    "PRODUCTION_ROOT_SIGNATURE_VERIFIER_IS_NOT_BOUND",
    "PRODUCTION_REVOCATION_SOURCE_IS_NOT_BOUND",
    "PERSISTENCE_AND_RESTART_RECOVERY_ARE_REQUIREMENTS_NOT_EVIDENCE",
    "STORE_OPEN_READ_WRITE_ROTATE_AND_RECOVER_SURFACES_ARE_ABSENT",
    "RUNTIME_READINESS_ACTIVATION_AND_LIVE_REMAIN_FORBIDDEN",
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def production_resolved_authority_store_binding_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("production resolved store binding must be a mapping")
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


@dataclass(frozen=True, repr=False)
class ProtectedProductionResolvedAuthorityStoreBindingV2:
    authenticated_authority_binding_sha256: str = field(repr=False)
    multistore_lease_binding_sha256: str = field(repr=False)
    resolved_lock_port_projection_sha256: str = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedProductionResolvedAuthorityStoreBindingV2(<protected>)"


def protected_production_resolved_authority_store_binding_valid_v2(
    value: Any,
) -> bool:
    if type(value) is not ProtectedProductionResolvedAuthorityStoreBindingV2:
        return False
    try:
        binding = copy.deepcopy(dict(value.binding))
        supplied = str(binding.get("binding_sha256") or "")
        previous = binding.get("previous_root_authority_attestation_sha256")
        return bool(
            set(binding) == _BINDING_KEYS
            and binding["binding_version"]
            == PRODUCTION_RESOLVED_AUTHORITY_STORE_BINDING_VERSION_V2
            and binding["scope_attestation"]
            == OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2
            and binding["store_contract_version"]
            == PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
            and binding["source_durable_authority_contract_version"]
            == durable_authority_v2.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_CONTRACT_V2_VERSION
            and binding["source_authenticated_authority_binding_version"]
            == authenticated_binding_v1.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_CONTRACT_V1_VERSION
            and all(
                _valid_sha(binding[key])
                for key in (
                    "authenticated_authority_binding_sha256",
                    "multistore_lease_binding_sha256",
                    "resolved_lock_port_projection_sha256",
                    "store_identity_sha256",
                    "storage_binding_sha256",
                    "lock_namespace_sha256",
                    "root_identity_sha256",
                    "root_authority_attestation_sha256",
                    "root_authority_key_id_sha256",
                    "durable_authority_receipt_sha256",
                    "durable_authority_record_sha256",
                    "binding_sha256",
                )
            )
            and type(binding["root_authority_key_epoch"]) is int
            and binding["root_authority_key_epoch"] >= 1
            and (
                previous is None
                if binding["root_authority_key_epoch"] == 1
                else _valid_sha(previous)
            )
            and all(binding[key] is True for key in _REQUIRED_TRUE)
            and all(binding[key] is False for key in _REQUIRED_FALSE)
            and value.authenticated_authority_binding_sha256
            == binding["authenticated_authority_binding_sha256"]
            and value.multistore_lease_binding_sha256
            == binding["multistore_lease_binding_sha256"]
            and value.resolved_lock_port_projection_sha256
            == binding["resolved_lock_port_projection_sha256"]
            and value.binding_sha256 == supplied
            and hmac.compare_digest(
                supplied,
                production_resolved_authority_store_binding_sha256_v2(binding),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class DormantProductionResolvedAuthorityStoreConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_authenticated_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_multistore_binding_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_projection_sha256: str | None = field(
        default=None, repr=False
    )
    expected_authenticated_binding_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_multistore_binding_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_projection_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class DormantProductionResolvedAuthorityStoreContractV2:
    def __init__(
        self,
        config: DormantProductionResolvedAuthorityStoreConfigV2 | None = None,
    ) -> None:
        self._config = config or DormantProductionResolvedAuthorityStoreConfigV2()

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_V2_BLOCKED",
            "reason": reason,
            "protected_binding": None,
            "contract_verified": False,
            "authenticated_root_evidence_verified": False,
            "rotation_recovery_requirements_verified": False,
            "multistore_cross_binding_verified": False,
            "physical_store_implementation_bound": False,
            "store_open_allowed": False,
            "store_read_allowed": False,
            "store_write_allowed": False,
            "root_rotation_allowed": False,
            "recovery_allowed": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_contract_only": True,
            "production_signature_verified": False,
            "production_authority": False,
            "production_durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def _config_reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2
        ):
            return "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_SCOPE_INVALID"
        pins = (
            config.expected_authenticated_binding_sha256,
            config.expected_multistore_binding_sha256,
            config.expected_resolved_projection_sha256,
            config.expected_authenticated_binding_object_identity_sha256,
            config.expected_multistore_binding_object_identity_sha256,
            config.expected_resolved_projection_object_identity_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        authenticated_authority_binding: Any,
        multistore_lease_binding: Any,
        resolved_lock_port_projection: Any,
    ) -> dict[str, Any]:
        result = self._failed("")
        reason = self._config_reason()
        if reason is not None:
            result["reason"] = reason
            return result
        config = self._config
        if not (
            authenticated_binding_v1.protected_startup_recovery_authenticated_authority_binding_valid_v1(
                authenticated_authority_binding
            )
            and multistore_v2.protected_production_multistore_observation_lease_binding_valid_v2(
                multistore_lease_binding
            )
            and multistore_v2.production_store_lock_port_projection_valid_v2(
                resolved_lock_port_projection
            )
        ):
            result["reason"] = "PRODUCTION_RESOLVED_AUTHORITY_STORE_INPUT_INVALID"
            return result
        if not (
            authenticated_authority_binding.binding_sha256
            == config.expected_authenticated_binding_sha256
            and multistore_lease_binding.binding_sha256
            == config.expected_multistore_binding_sha256
            and resolved_lock_port_projection.projection_sha256
            == config.expected_resolved_projection_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                authenticated_authority_binding
            )
            == config.expected_authenticated_binding_object_identity_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                multistore_lease_binding
            )
            == config.expected_multistore_binding_object_identity_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                resolved_lock_port_projection
            )
            == config.expected_resolved_projection_object_identity_sha256
        ):
            result["reason"] = "PRODUCTION_RESOLVED_AUTHORITY_STORE_INSTANCE_OR_PIN_MISMATCH"
            return result
        authority = copy.deepcopy(dict(authenticated_authority_binding.binding))
        lease = copy.deepcopy(dict(multistore_lease_binding.binding))
        projection = copy.deepcopy(dict(resolved_lock_port_projection.projection))
        if not (
            projection["port_role"] == multistore_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2
            and projection["source_contract_version"]
            == PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2
            and lease["resolved_authority_store_projection_sha256"]
            == projection["projection_sha256"]
            and lease["resolved_authority_store_identity_sha256"]
            == projection["store_identity_sha256"]
            and lease["resolved_authority_store_storage_binding_sha256"]
            == projection["storage_binding_sha256"]
            == authority["durable_authority_storage_binding_sha256"]
            and lease["resolved_authority_store_lock_namespace_sha256"]
            == projection["lock_namespace_sha256"]
            and lease["authenticated_authority_contract_sha256"]
            == authenticated_authority_binding.binding_sha256
            and authority["root_signature_verified"] is True
            and authority["root_rotation_contract_reused"] is True
            and authority[
                "root_rotation_current_state_revalidation_required"
            ]
            is True
            and authority[
                "durable_authority_current_state_revalidation_required"
            ]
            is True
        ):
            result["reason"] = "PRODUCTION_RESOLVED_AUTHORITY_STORE_CROSS_BINDING_INVALID"
            return result
        binding = {
            "binding_version": PRODUCTION_RESOLVED_AUTHORITY_STORE_BINDING_VERSION_V2,
            "scope_attestation": OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2,
            "store_contract_version": PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2,
            "source_durable_authority_contract_version": durable_authority_v2.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_HANDOFF_V1_BACKEND_V2_PROTECTED_RECONCILIATION_DURABLE_AUTHORITY_CONTRACT_V2_VERSION,
            "source_authenticated_authority_binding_version": authenticated_binding_v1.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_CONTRACT_V1_VERSION,
            "authenticated_authority_binding_sha256": authenticated_authority_binding.binding_sha256,
            "multistore_lease_binding_sha256": multistore_lease_binding.binding_sha256,
            "resolved_lock_port_projection_sha256": projection[
                "projection_sha256"
            ],
            "store_identity_sha256": projection["store_identity_sha256"],
            "storage_binding_sha256": projection["storage_binding_sha256"],
            "lock_namespace_sha256": projection["lock_namespace_sha256"],
            "root_identity_sha256": authority["root_identity_sha256"],
            "root_authority_attestation_sha256": authority[
                "root_authority_attestation_sha256"
            ],
            "root_authority_key_id_sha256": authority[
                "root_authority_key_id_sha256"
            ],
            "root_authority_key_epoch": authority["root_authority_key_epoch"],
            "previous_root_authority_attestation_sha256": authority[
                "previous_root_authority_attestation_sha256"
            ],
            "durable_authority_receipt_sha256": authority[
                "durable_authority_receipt_sha256"
            ],
            "durable_authority_record_sha256": authority[
                "durable_authority_record_sha256"
            ],
            "root_signature_evidence_verified": True,
            "root_signature_reverification_required_on_open": True,
            "root_signature_reverification_required_on_recovery": True,
            "monotonic_key_epoch_required": True,
            "previous_attestation_chain_required": True,
            "root_rotation_compare_and_swap_required": True,
            "root_rotation_zero_issued_authorities_required": True,
            "root_revocation_registry_required": True,
            "root_revocation_recovery_required": True,
            "snapshot_required": True,
            "append_only_journal_required": True,
            "write_ahead_log_required": True,
            "backup_required": True,
            "cross_process_lock_required": True,
            "atomic_replace_required": True,
            "directory_fsync_required": True,
            "crash_recovery_required": True,
            "interrupted_rotation_recovery_required": True,
            "corruption_fails_closed": True,
            "unresolved_transactions_block_readiness": True,
            "same_authenticated_binding_instance_required": True,
            "same_multistore_binding_instance_required": True,
            "same_resolved_lock_projection_instance_required": True,
            "persistent_production_storage_required": True,
            "physical_store_implementation_bound": False,
            "production_root_verifier_bound": False,
            "production_revocation_source_bound": False,
            "store_open_allowed": False,
            "store_read_allowed": False,
            "store_write_allowed": False,
            "root_rotation_allowed": False,
            "recovery_allowed": False,
            "filesystem_accessed": False,
            "network_accessed": False,
            "synthetic_contract_only": True,
            "production_signature_verified": False,
            "production_authority": False,
            "production_durable": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
            "write_executed": False,
            "registry_write": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        binding["binding_sha256"] = (
            production_resolved_authority_store_binding_sha256_v2(binding)
        )
        protected = ProtectedProductionResolvedAuthorityStoreBindingV2(
            authenticated_authority_binding_sha256=binding[
                "authenticated_authority_binding_sha256"
            ],
            multistore_lease_binding_sha256=binding[
                "multistore_lease_binding_sha256"
            ],
            resolved_lock_port_projection_sha256=binding[
                "resolved_lock_port_projection_sha256"
            ],
            binding=copy.deepcopy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_production_resolved_authority_store_binding_valid_v2(
            protected
        ):
            result["reason"] = "PRODUCTION_RESOLVED_AUTHORITY_STORE_INTERNAL_INVALID"
            return result
        result.update(
            {
                "ok": True,
                "status": "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_V2_VERIFIED_OFFLINE",
                "reason": None,
                "protected_binding": protected,
                "contract_verified": True,
                "authenticated_root_evidence_verified": True,
                "rotation_recovery_requirements_verified": True,
                "multistore_cross_binding_verified": True,
            }
        )
        return result


__all__ = [
    "DormantProductionResolvedAuthorityStoreConfigV2",
    "DormantProductionResolvedAuthorityStoreContractV2",
    "OFFLINE_PRODUCTION_RESOLVED_AUTHORITY_STORE_SCOPE_ATTESTATION_V2",
    "PRODUCTION_RESOLVED_AUTHORITY_STORE_BINDING_VERSION_V2",
    "PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_VERSION_V2",
    "ProtectedProductionResolvedAuthorityStoreBindingV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_RESOLVED_AUTHORITY_STORE_CONTRACT_OFFLINE_V2_VERSION",
    "production_resolved_authority_store_binding_sha256_v2",
    "protected_production_resolved_authority_store_binding_valid_v2",
]
