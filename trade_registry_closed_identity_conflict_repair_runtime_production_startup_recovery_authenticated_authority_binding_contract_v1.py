"""Dormant binding from authenticated authority to startup-recovery evidence.

The contract reuses the existing durable-authority signature verifier and
binds only synthetic, caller-provided identity projections in memory.  It does
not read a ledger, populate recovery evidence, grant production authority, or
integrate with runtime/readiness/Live.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1 as evidence_schema_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_CONTRACT_V1_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-AUTHORITY-BINDING-CONTRACT-V1"
)
OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1 = (
    "C3_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_OFFLINE_ONLY_V1"
)
SYNTHETIC_STARTUP_RECOVERY_AUTHORITY_IDENTITY_VERSION_V1 = (
    "C3_STARTUP_RECOVERY_AUTHORITY_IDENTITY_SYNTHETIC_V1"
)
PROTECTED_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_VERSION_V1 = (
    "C3_PROTECTED_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_DORMANT_V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY_KEYS = frozenset(
    {
        "identity_version",
        "authority_storage_binding_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "synthetic_only",
        "production_evidence",
        "identity_sha256",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_version",
        "scope_attestation",
        "schema_sha256",
        "provider_binding_sha256",
        "recovery_identity_sha256",
        "backend_instance_sha256",
        "registry_path_binding_sha256",
        "wal_storage_binding_sha256",
        "resolved_ledger_storage_binding_sha256",
        "lock_namespace_sha256",
        "maintenance_epoch",
        "maintenance_lease_receipt_sha256",
        "root_identity_sha256",
        "root_authority_attestation_sha256",
        "root_authority_key_id_sha256",
        "root_authority_key_epoch",
        "previous_root_authority_attestation_sha256",
        "durable_authority_storage_binding_sha256",
        "durable_authority_receipt_sha256",
        "durable_authority_record_sha256",
        "durable_authority_obligation_sha256",
        "durable_authority_transaction_sha256",
        "candidate_authenticated_authority_receipt_sha256",
        "authenticated_authority_schema_field",
        "root_signature_verifier_contract_reused",
        "root_signature_verified",
        "root_rotation_contract_reused",
        "root_rotation_current_state_revalidation_required",
        "durable_authority_receipt_verified",
        "durable_authority_current_state_revalidation_required",
        "synthetic_identity_vector_verified",
        "same_backend_instance_required",
        "same_registry_path_binding_required",
        "same_lock_namespace_required",
        "same_maintenance_epoch_instance_required",
        "maintenance_lease_authentication_required",
        "complete_prepared_catalog_authentication_required",
        "complete_resolved_catalog_authentication_required",
        "empirical_durability_probe_required",
        "cryptographic_contract_compatible",
        "startup_session_authority_scope_verified",
        "evidence_population_allowed",
        "production_blockers",
        "production_authority",
        "production_ready",
        "runtime_integrated",
        "recovery_execution_allowed",
        "activation_allowed",
        "live_allowed",
        "synthetic_only",
        "binding_sha256",
    }
)
_PRODUCTION_BLOCKERS = (
    "PRODUCTION_ROOT_KEY_PROVIDER_NOT_BOUND",
    "DURABLE_AUTHORITY_CURRENT_STATE_REVALIDATION_NOT_BOUND",
    "ROOT_ROTATION_CURRENT_STATE_REVALIDATION_NOT_BOUND",
    "STARTUP_SESSION_AUTHORITY_SCOPE_NOT_PROVEN",
    "PRODUCTION_BACKEND_INSTANCE_AUTHENTICATION_NOT_BOUND",
    "PRODUCTION_REGISTRY_PATH_AUTHENTICATION_NOT_BOUND",
    "PRODUCTION_LOCK_NAMESPACE_AUTHENTICATION_NOT_BOUND",
    "PRODUCTION_MAINTENANCE_LEASE_AUTHENTICATION_NOT_BOUND",
    "COMPLETE_PREPARED_CATALOG_AUTHENTICATION_NOT_BOUND",
    "COMPLETE_RESOLVED_CATALOG_AUTHENTICATION_NOT_BOUND",
    "EMPIRICAL_DURABILITY_PROBE_NOT_BOUND",
    "EVIDENCE_POPULATION_AND_RUNTIME_REMAIN_FORBIDDEN",
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


def _canonical_copy(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _stable_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_sha256(value: Any) -> str:
    normalized = str(value or "").lower().strip()
    return normalized if _SHA256_RE.fullmatch(normalized) else ""


def startup_recovery_authority_identity_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("identity must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "identity_sha256"}
    )


def startup_recovery_authenticated_authority_binding_sha256_v1(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("binding must be a mapping")
    return _stable_sha256(
        {key: item for key, item in value.items() if key != "binding_sha256"}
    )


@dataclass(frozen=True)
class DormantStartupRecoveryAuthenticatedAuthorityBindingConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_schema_sha256: str | None = field(default=None, repr=False)
    expected_root_authority_attestation_sha256: str | None = field(
        default=None, repr=False
    )
    expected_durable_authority_receipt_sha256: str | None = field(
        default=None, repr=False
    )
    expected_recovery_identity_sha256: str | None = field(
        default=None, repr=False
    )


@dataclass(frozen=True, repr=False)
class ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1:
    schema_sha256: str = field(repr=False)
    durable_authority_receipt_sha256: str = field(repr=False)
    backend_instance_sha256: str = field(repr=False)
    binding: Mapping[str, Any] = field(repr=False)
    binding_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1(<protected>)"


def _synthetic_recovery_identity_valid_v1(value: Any) -> bool:
    if type(value) is not dict or set(value) != _IDENTITY_KEYS:
        return False
    supplied_sha = _valid_sha256(value.get("identity_sha256"))
    try:
        return bool(
            value.get("identity_version")
            == SYNTHETIC_STARTUP_RECOVERY_AUTHORITY_IDENTITY_VERSION_V1
            and all(
                _valid_sha256(value.get(field_name))
                for field_name in (
                    "authority_storage_binding_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "wal_storage_binding_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "lock_namespace_sha256",
                    "maintenance_epoch",
                    "maintenance_lease_receipt_sha256",
                )
            )
            and value.get("synthetic_only") is True
            and value.get("production_evidence") is False
            and supplied_sha
            and hmac.compare_digest(
                supplied_sha,
                startup_recovery_authority_identity_sha256_v1(value),
            )
        )
    except Exception:
        return False


def protected_startup_recovery_authenticated_authority_binding_valid_v1(
    value: Any,
) -> bool:
    if not isinstance(
        value, ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1
    ):
        return False
    binding = value.binding
    if type(binding) is not dict or set(binding) != _BINDING_KEYS:
        return False
    supplied_sha = _valid_sha256(binding.get("binding_sha256"))
    try:
        return bool(
            binding.get("binding_version")
            == PROTECTED_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_VERSION_V1
            and binding.get("scope_attestation")
            == OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1
            and all(
                _valid_sha256(binding.get(field_name))
                for field_name in (
                    "schema_sha256",
                    "provider_binding_sha256",
                    "recovery_identity_sha256",
                    "backend_instance_sha256",
                    "registry_path_binding_sha256",
                    "wal_storage_binding_sha256",
                    "resolved_ledger_storage_binding_sha256",
                    "lock_namespace_sha256",
                    "maintenance_epoch",
                    "maintenance_lease_receipt_sha256",
                    "root_identity_sha256",
                    "root_authority_attestation_sha256",
                    "root_authority_key_id_sha256",
                    "durable_authority_storage_binding_sha256",
                    "durable_authority_receipt_sha256",
                    "durable_authority_record_sha256",
                    "durable_authority_obligation_sha256",
                    "durable_authority_transaction_sha256",
                    "candidate_authenticated_authority_receipt_sha256",
                )
            )
            and binding.get("schema_sha256") == value.schema_sha256
            and binding.get("durable_authority_receipt_sha256")
            == value.durable_authority_receipt_sha256
            and binding.get("backend_instance_sha256")
            == value.backend_instance_sha256
            and binding.get("candidate_authenticated_authority_receipt_sha256")
            == binding.get("durable_authority_receipt_sha256")
            and binding.get("authenticated_authority_schema_field")
            == "authenticated_authority_receipt_sha256"
            and type(binding.get("root_authority_key_epoch")) is int
            and binding.get("root_authority_key_epoch") >= 1
            and (
                binding.get("previous_root_authority_attestation_sha256") is None
                if binding.get("root_authority_key_epoch") == 1
                else _valid_sha256(
                    binding.get("previous_root_authority_attestation_sha256")
                )
            )
            and all(
                binding.get(field_name) is True
                for field_name in (
                    "root_signature_verifier_contract_reused",
                    "root_signature_verified",
                    "root_rotation_contract_reused",
                    "root_rotation_current_state_revalidation_required",
                    "durable_authority_receipt_verified",
                    "durable_authority_current_state_revalidation_required",
                    "synthetic_identity_vector_verified",
                    "same_backend_instance_required",
                    "same_registry_path_binding_required",
                    "same_lock_namespace_required",
                    "same_maintenance_epoch_instance_required",
                    "maintenance_lease_authentication_required",
                    "complete_prepared_catalog_authentication_required",
                    "complete_resolved_catalog_authentication_required",
                    "empirical_durability_probe_required",
                    "cryptographic_contract_compatible",
                )
            )
            and all(
                binding.get(field_name) is False
                for field_name in (
                    "startup_session_authority_scope_verified",
                    "evidence_population_allowed",
                    "production_authority",
                    "production_ready",
                    "runtime_integrated",
                    "recovery_execution_allowed",
                    "activation_allowed",
                    "live_allowed",
                )
            )
            and binding.get("production_blockers") == list(_PRODUCTION_BLOCKERS)
            and binding.get("synthetic_only") is True
            and supplied_sha
            and supplied_sha == value.binding_sha256
            and hmac.compare_digest(
                supplied_sha,
                startup_recovery_authenticated_authority_binding_sha256_v1(
                    binding
                ),
            )
        )
    except Exception:
        return False


class DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1:
    def __init__(
        self,
        *,
        config: DormantStartupRecoveryAuthenticatedAuthorityBindingConfigV1
        | None = None,
    ) -> None:
        self._config = (
            config
            or DormantStartupRecoveryAuthenticatedAuthorityBindingConfigV1()
        )

    def __repr__(self) -> str:
        return "DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1(<protected>)"

    @staticmethod
    def _base() -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_BLOCKED",
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_CONTRACT_V1_VERSION,
            "dormant": True,
            "default_off": True,
            "offline_only": True,
            "synthetic_only": True,
            "schema_verified": False,
            "identity_vector_verified": False,
            "root_signature_verifier_reused": False,
            "root_signature_verified": False,
            "durable_authority_receipt_verified": False,
            "binding_created": False,
            "verifier_called": False,
            "evidence_created": False,
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
            "protected_binding": None,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
        }

    def _config_reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1
        ):
            return "STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_INVALID"
        if not all(
            _valid_sha256(item)
            for item in (
                config.expected_schema_sha256,
                config.expected_root_authority_attestation_sha256,
                config.expected_durable_authority_receipt_sha256,
                config.expected_recovery_identity_sha256,
            )
        ):
            return "STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_PINS_INVALID"
        return None

    def bind_offline(
        self,
        *,
        protected_evidence_schema: Any,
        recovery_identity: Any,
        root_authority_attestation: Any,
        root_authority_verifier: Any,
        durable_authority_receipt: Any,
        now_epoch: int,
    ) -> dict[str, Any]:
        result = self._base()
        reason = self._config_reason()
        if reason is not None:
            result["reasons"].append(reason)
            return result
        config = self._config
        if not (
            evidence_schema_v1.protected_production_startup_recovery_evidence_schema_valid_v1(
                protected_evidence_schema
            )
            and hmac.compare_digest(
                protected_evidence_schema.schema_sha256,
                str(config.expected_schema_sha256),
            )
        ):
            result["reasons"].append("PROTECTED_RECOVERY_EVIDENCE_SCHEMA_INVALID")
            return result
        schema = protected_evidence_schema.schema
        result["schema_verified"] = True
        if not (
            _synthetic_recovery_identity_valid_v1(recovery_identity)
            and hmac.compare_digest(
                recovery_identity["identity_sha256"],
                str(config.expected_recovery_identity_sha256),
            )
            and recovery_identity["backend_instance_sha256"]
            == schema["source_backend_instance_sha256"]
            and recovery_identity["registry_path_binding_sha256"]
            == schema["source_registry_path_binding_sha256"]
            and recovery_identity["lock_namespace_sha256"]
            == schema["source_lock_namespace_sha256"]
        ):
            result["reasons"].append("RECOVERY_IDENTITY_VECTOR_NOT_PINNED")
            return result
        result["identity_vector_verified"] = True
        if not (
            authority_v2.protected_durable_reconciliation_authority_receipt_valid_v2(
                durable_authority_receipt
            )
            and hmac.compare_digest(
                durable_authority_receipt.receipt_sha256,
                str(config.expected_durable_authority_receipt_sha256),
            )
        ):
            result["reasons"].append("DURABLE_AUTHORITY_RECEIPT_INVALID")
            return result
        receipt = durable_authority_receipt.receipt
        record = durable_authority_receipt.record
        if not (
            receipt["state"] == "ISSUED"
            and record["state"] == "ISSUED"
            and receipt["consumption_count"] == 0
            and record["consumption_count"] == 0
            and type(now_epoch) is int
            and record["issued_at_epoch"] <= now_epoch < record["expires_at_epoch"]
        ):
            result["reasons"].append(
                "DURABLE_AUTHORITY_ISSUED_PROJECTION_NOT_CURRENT"
            )
            return result
        result["durable_authority_receipt_verified"] = True
        if not (
            isinstance(root_authority_attestation, Mapping)
            and authority_v2.authenticated_root_authority_attestation_valid_v2(
                root_authority_attestation
            )
            and root_authority_attestation.get("attestation_sha256")
            == config.expected_root_authority_attestation_sha256
            == receipt["root_authority_attestation_sha256"]
            and root_authority_attestation.get("root_identity_sha256")
            == receipt["root_identity_sha256"]
            == record["root_identity_sha256"]
            and root_authority_attestation.get("storage_binding_sha256")
            == receipt["storage_binding_sha256"]
            == recovery_identity["authority_storage_binding_sha256"]
            and type(now_epoch) is int
            and root_authority_attestation.get("issued_at_epoch")
            <= now_epoch
            < root_authority_attestation.get("expires_at_epoch")
        ):
            result["reasons"].append("ROOT_AUTHORITY_BINDING_INVALID")
            return result
        if not (
            getattr(root_authority_verifier, "offline_only", None) is True
            and getattr(root_authority_verifier, "filesystem_access_allowed", None)
            is False
            and getattr(root_authority_verifier, "network_access_allowed", None)
            is False
            and callable(
                getattr(
                    root_authority_verifier,
                    "verify_root_authority_signature_v2",
                    None,
                )
            )
        ):
            result["reasons"].append("OFFLINE_ROOT_AUTHORITY_VERIFIER_REQUIRED")
            return result
        result["verifier_called"] = True
        result["root_signature_verifier_reused"] = True
        if not authority_v2.authenticated_root_authority_attestation_verified_v2(
            root_authority_attestation,
            root_authority_verifier,
        ):
            result["reasons"].append("ROOT_AUTHORITY_SIGNATURE_INVALID")
            return result
        result["root_signature_verified"] = True
        binding = {
            "binding_version": PROTECTED_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_VERSION_V1,
            "scope_attestation": OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1,
            "schema_sha256": protected_evidence_schema.schema_sha256,
            "provider_binding_sha256": schema["provider_binding_sha256"],
            "recovery_identity_sha256": recovery_identity["identity_sha256"],
            "backend_instance_sha256": recovery_identity[
                "backend_instance_sha256"
            ],
            "registry_path_binding_sha256": recovery_identity[
                "registry_path_binding_sha256"
            ],
            "wal_storage_binding_sha256": recovery_identity[
                "wal_storage_binding_sha256"
            ],
            "resolved_ledger_storage_binding_sha256": recovery_identity[
                "resolved_ledger_storage_binding_sha256"
            ],
            "lock_namespace_sha256": recovery_identity[
                "lock_namespace_sha256"
            ],
            "maintenance_epoch": recovery_identity["maintenance_epoch"],
            "maintenance_lease_receipt_sha256": recovery_identity[
                "maintenance_lease_receipt_sha256"
            ],
            "root_identity_sha256": receipt["root_identity_sha256"],
            "root_authority_attestation_sha256": root_authority_attestation[
                "attestation_sha256"
            ],
            "root_authority_key_id_sha256": root_authority_attestation[
                "key_id_sha256"
            ],
            "root_authority_key_epoch": root_authority_attestation["key_epoch"],
            "previous_root_authority_attestation_sha256": root_authority_attestation[
                "previous_attestation_sha256"
            ],
            "durable_authority_storage_binding_sha256": receipt[
                "storage_binding_sha256"
            ],
            "durable_authority_receipt_sha256": durable_authority_receipt.receipt_sha256,
            "durable_authority_record_sha256": receipt["record_sha256"],
            "durable_authority_obligation_sha256": receipt[
                "obligation_sha256"
            ],
            "durable_authority_transaction_sha256": receipt[
                "transaction_sha256"
            ],
            "candidate_authenticated_authority_receipt_sha256": durable_authority_receipt.receipt_sha256,
            "authenticated_authority_schema_field": "authenticated_authority_receipt_sha256",
            "root_signature_verifier_contract_reused": True,
            "root_signature_verified": True,
            "root_rotation_contract_reused": True,
            "root_rotation_current_state_revalidation_required": True,
            "durable_authority_receipt_verified": True,
            "durable_authority_current_state_revalidation_required": True,
            "synthetic_identity_vector_verified": True,
            "same_backend_instance_required": True,
            "same_registry_path_binding_required": True,
            "same_lock_namespace_required": True,
            "same_maintenance_epoch_instance_required": True,
            "maintenance_lease_authentication_required": True,
            "complete_prepared_catalog_authentication_required": True,
            "complete_resolved_catalog_authentication_required": True,
            "empirical_durability_probe_required": True,
            "cryptographic_contract_compatible": True,
            "startup_session_authority_scope_verified": False,
            "evidence_population_allowed": False,
            "production_blockers": list(_PRODUCTION_BLOCKERS),
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "recovery_execution_allowed": False,
            "activation_allowed": False,
            "live_allowed": False,
            "synthetic_only": True,
        }
        binding["binding_sha256"] = (
            startup_recovery_authenticated_authority_binding_sha256_v1(binding)
        )
        protected = ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1(
            schema_sha256=binding["schema_sha256"],
            durable_authority_receipt_sha256=binding[
                "durable_authority_receipt_sha256"
            ],
            backend_instance_sha256=binding["backend_instance_sha256"],
            binding=_canonical_copy(binding),
            binding_sha256=binding["binding_sha256"],
        )
        if not protected_startup_recovery_authenticated_authority_binding_valid_v1(
            protected
        ):
            result["reasons"].append(
                "PROTECTED_AUTHENTICATED_AUTHORITY_BINDING_SELF_CHECK_FAILED"
            )
            return result
        result.update(
            ok=True,
            status="C3_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BOUND_DORMANT",
            binding_created=True,
            protected_binding=protected,
        )
        return result


__all__ = [
    "DormantStartupRecoveryAuthenticatedAuthorityBindingConfigV1",
    "DormantStartupRecoveryAuthenticatedAuthorityBindingContractV1",
    "OFFLINE_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_SCOPE_ATTESTATION_V1",
    "PROTECTED_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_VERSION_V1",
    "ProtectedStartupRecoveryAuthenticatedAuthorityBindingV1",
    "SYNTHETIC_STARTUP_RECOVERY_AUTHORITY_IDENTITY_VERSION_V1",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_AUTHORITY_BINDING_CONTRACT_V1_VERSION",
    "protected_startup_recovery_authenticated_authority_binding_valid_v1",
    "startup_recovery_authenticated_authority_binding_sha256_v1",
    "startup_recovery_authority_identity_sha256_v1",
]
