"""Default-off production-shaped adapters for authenticated C3 recovery.

No path, key provider, or recovery port is inferred.  Default construction is
side-effect free.  Enabled construction requires explicit path and instance
pins; the reference tests use temporary synthetic storage only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-PERSISTENT-AUTHORITY-PRODUCTION-ADAPTERS-V2"
)
PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2 = (
    "C3_PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_BINDING_V2"
)
ROOT_AUTHORITY_STATE_ENVELOPE_VERSION_V2 = "C3_ROOT_AUTHORITY_STATE_ENVELOPE_V2"
ROOT_REVOCATION_STATE_ENVELOPE_VERSION_V2 = "C3_ROOT_REVOCATION_STATE_ENVELOPE_V2"
STORE_RECOVERY_PORT_RECEIPT_VERSION_V2 = "C3_STORE_RECOVERY_PORT_RECEIPT_V2"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_ROOT_STATE_FILENAME = "c3_root_authority_state_v2.json"
_REVOCATION_FILENAME = "c3_root_authority_revocations_v2.json"


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def authority_adapter_storage_root_binding_sha256_v2(root: str | os.PathLike[str]) -> str:
    path = Path(root).resolve(strict=False)
    if path == Path(path.anchor):
        raise ValueError("authority adapter storage root cannot be filesystem root")
    return hash_v2.stable_sha256_v2(
        {
            "binding_version": "C3_AUTHORITY_ADAPTER_STORAGE_ROOT_BINDING_V2",
            "storage_root": os.path.normcase(str(path)),
        }
    )


def authority_adapter_state_envelope_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "envelope_sha256"}
    )


def store_recovery_port_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


@dataclass(frozen=True)
class PersistentAuthorityFileAdapterConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_storage_root_binding_sha256: str | None = field(
        default=None, repr=False
    )


class PersistentRootAuthorityStateProviderV2:
    def __init__(
        self,
        config: PersistentAuthorityFileAdapterConfigV2 | None = None,
        *,
        storage_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self._config = config or PersistentAuthorityFileAdapterConfigV2()
        self._root = (
            Path(storage_root).resolve(strict=False)
            if storage_root is not None
            else None
        )

    def __repr__(self) -> str:
        return "PersistentRootAuthorityStateProviderV2(<protected>)"

    def _reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PERSISTENT_ROOT_AUTHORITY_PROVIDER_DEFAULT_OFF"
        if self._config.scope_attestation != PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2:
            return "PERSISTENT_ROOT_AUTHORITY_PROVIDER_SCOPE_INVALID"
        if self._root is None or not _valid_sha(
            self._config.expected_storage_root_binding_sha256
        ):
            return "PERSISTENT_ROOT_AUTHORITY_PROVIDER_PATH_BINDING_REQUIRED"
        try:
            actual = authority_adapter_storage_root_binding_sha256_v2(self._root)
        except Exception:
            return "PERSISTENT_ROOT_AUTHORITY_PROVIDER_PATH_INVALID"
        if not hmac.compare_digest(
            actual, str(self._config.expected_storage_root_binding_sha256)
        ):
            return "PERSISTENT_ROOT_AUTHORITY_PROVIDER_PATH_MISMATCH"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        return {
            "enabled": self._config.enabled is True,
            "default_off": self._config.enabled is not True,
            "path_bound": reason is None,
            "reason": reason,
            "filesystem_accessed": False,
            "production_ready": False,
            "runtime_integrated": False,
            "live_allowed": False,
        }

    def read_current_root_authority_v2(self, *, now_epoch: int) -> dict[str, Any]:
        reason = self._reason()
        if reason is not None:
            raise RuntimeError(reason)
        if type(now_epoch) is not int:
            raise RuntimeError("PERSISTENT_ROOT_AUTHORITY_NOW_INVALID")
        try:
            envelope = json.loads(
                (self._root / _ROOT_STATE_FILENAME).read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise RuntimeError("PERSISTENT_ROOT_AUTHORITY_READ_FAILED") from exc
        if not isinstance(envelope, Mapping):
            raise RuntimeError("PERSISTENT_ROOT_AUTHORITY_ENVELOPE_INVALID")
        supplied = str(envelope.get("envelope_sha256") or "")
        attestation = envelope.get("root_authority_attestation")
        if not (
            envelope.get("envelope_version") == ROOT_AUTHORITY_STATE_ENVELOPE_VERSION_V2
            and type(envelope.get("generation")) is int
            and envelope["generation"] >= 1
            and authority_v2.authenticated_root_authority_attestation_valid_v2(
                attestation
            )
            and _valid_sha(supplied)
            and hmac.compare_digest(
                supplied, authority_adapter_state_envelope_sha256_v2(envelope)
            )
        ):
            raise RuntimeError("PERSISTENT_ROOT_AUTHORITY_ENVELOPE_INVALID")
        receipt = {
            "ok": True,
            "receipt_version": boundary_v2.PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_VERSION_V2,
            "storage_binding_sha256": attestation["storage_binding_sha256"],
            "root_authority_attestation_sha256": attestation[
                "attestation_sha256"
            ],
            "root_authority_attestation": attestation,
            "generation": envelope["generation"],
            "observed_at_epoch": now_epoch,
            "durable_read_verified": True,
            "atomic_replace_on_write": True,
            "fsync_on_write": True,
            "filesystem_accessed": True,
            "temporary_storage_only": bool(envelope.get("synthetic_only")),
            "synthetic_only": bool(envelope.get("synthetic_only")),
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        receipt["receipt_sha256"] = (
            boundary_v2.persistent_root_authority_read_receipt_sha256_v2(receipt)
        )
        return receipt


@dataclass(frozen=True)
class InjectedRootAuthorityVerifierConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_key_provider_object_identity_sha256: str | None = field(
        default=None, repr=False
    )


class InjectedRootAuthorityVerifierV2:
    def __init__(
        self,
        config: InjectedRootAuthorityVerifierConfigV2 | None = None,
        *,
        key_provider: Any = None,
    ) -> None:
        self._config = config or InjectedRootAuthorityVerifierConfigV2()
        self._key_provider = key_provider

    def __repr__(self) -> str:
        return "InjectedRootAuthorityVerifierV2(<protected>)"

    def verify_root_authority_signature_v2(
        self,
        *,
        key_id_sha256: str,
        payload_sha256: str,
        signature_sha256: str,
    ) -> bool:
        if not (
            self._config.enabled is True
            and self._config.scope_attestation
            == PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2
            and _valid_sha(self._config.expected_key_provider_object_identity_sha256)
            and _object_identity(self._key_provider)
            == self._config.expected_key_provider_object_identity_sha256
        ):
            return False
        resolver = getattr(self._key_provider, "resolve_root_hmac_key_v2", None)
        if not callable(resolver) or not all(
            _valid_sha(item)
            for item in (key_id_sha256, payload_sha256, signature_sha256)
        ):
            return False
        try:
            key = resolver(key_id_sha256=key_id_sha256)
        except Exception:
            return False
        if not isinstance(key, bytes) or len(key) < 32:
            return False
        expected = hmac.new(
            key, payload_sha256.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_sha256)


class PersistentRootAuthorityRevocationSourceV2:
    def __init__(
        self,
        config: PersistentAuthorityFileAdapterConfigV2 | None = None,
        *,
        storage_root: str | os.PathLike[str] | None = None,
    ) -> None:
        self._config = config or PersistentAuthorityFileAdapterConfigV2()
        self._root = (
            Path(storage_root).resolve(strict=False)
            if storage_root is not None
            else None
        )

    def __repr__(self) -> str:
        return "PersistentRootAuthorityRevocationSourceV2(<protected>)"

    def _ready(self) -> bool:
        if not (
            self._config.enabled is True
            and self._config.scope_attestation
            == PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2
            and self._root is not None
            and _valid_sha(self._config.expected_storage_root_binding_sha256)
        ):
            return False
        try:
            return hmac.compare_digest(
                authority_adapter_storage_root_binding_sha256_v2(self._root),
                str(self._config.expected_storage_root_binding_sha256),
            )
        except Exception:
            return False

    def root_authority_key_revoked_v2(
        self, *, key_id_sha256: str, key_epoch: int, now_epoch: int
    ) -> bool:
        if not self._ready():
            raise RuntimeError("PERSISTENT_ROOT_REVOCATION_SOURCE_DEFAULT_OFF")
        if not _valid_sha(key_id_sha256) or type(key_epoch) is not int or type(now_epoch) is not int:
            raise RuntimeError("PERSISTENT_ROOT_REVOCATION_QUERY_INVALID")
        try:
            envelope = json.loads(
                (self._root / _REVOCATION_FILENAME).read_text(encoding="utf-8")
            )
        except Exception as exc:
            raise RuntimeError("PERSISTENT_ROOT_REVOCATION_READ_FAILED") from exc
        supplied = str(envelope.get("envelope_sha256") or "")
        revoked = envelope.get("revoked_key_ids")
        if not (
            envelope.get("envelope_version") == ROOT_REVOCATION_STATE_ENVELOPE_VERSION_V2
            and type(envelope.get("generation")) is int
            and envelope["generation"] >= 1
            and isinstance(revoked, list)
            and all(_valid_sha(item) for item in revoked)
            and len(revoked) == len(set(revoked))
            and _valid_sha(supplied)
            and hmac.compare_digest(
                supplied, authority_adapter_state_envelope_sha256_v2(envelope)
            )
        ):
            raise RuntimeError("PERSISTENT_ROOT_REVOCATION_ENVELOPE_INVALID")
        return key_id_sha256 in revoked


@dataclass(frozen=True)
class CoordinatedMultistoreRecoveryConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_transaction_recovery_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_recovery_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_storage_binding_sha256: str | None = field(default=None, repr=False)


class CoordinatedMultistoreStartupRecoveryV2:
    def __init__(
        self,
        config: CoordinatedMultistoreRecoveryConfigV2 | None = None,
        *,
        transaction_recovery: Any = None,
        resolved_recovery: Any = None,
    ) -> None:
        self._config = config or CoordinatedMultistoreRecoveryConfigV2()
        self._transaction_recovery = transaction_recovery
        self._resolved_recovery = resolved_recovery

    def __repr__(self) -> str:
        return "CoordinatedMultistoreStartupRecoveryV2(<protected>)"

    @staticmethod
    def _port_receipt_valid(value: Any, role: str) -> bool:
        if not isinstance(value, Mapping):
            return False
        try:
            return bool(
                value.get("ok") is True
                and value.get("receipt_version") == STORE_RECOVERY_PORT_RECEIPT_VERSION_V2
                and value.get("store_role") == role
                and _valid_sha(value.get("maintenance_epoch"))
                and _valid_sha(value.get("lock_namespace_sha256"))
                and _valid_sha(value.get("root_authority_attestation_sha256"))
                and _valid_sha(value.get("storage_binding_sha256"))
                and value.get("transactions_remaining") == 0
                and value.get("recovery_completed") is True
                and value.get("filesystem_accessed") is True
                and value.get("real_registry_accessed") is False
                and value.get("network_accessed") is False
                and value.get("broker_called") is False
                and value.get("no_order_sent") is True
                and _valid_sha(value.get("receipt_sha256"))
                and hmac.compare_digest(
                    value["receipt_sha256"],
                    store_recovery_port_receipt_sha256_v2(value),
                )
            )
        except Exception:
            return False

    def recover_multistore_v2(
        self,
        *,
        maintenance_permit: Mapping[str, Any],
        root_authority_attestation: Mapping[str, Any],
        now_epoch: int,
    ) -> dict[str, Any]:
        config = self._config
        transaction_call = getattr(
            self._transaction_recovery, "recover_store_v2", None
        )
        resolved_call = getattr(self._resolved_recovery, "recover_store_v2", None)
        if not (
            config.enabled is True
            and config.scope_attestation
            == PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2
            and all(
                _valid_sha(item)
                for item in (
                    config.expected_transaction_recovery_object_identity_sha256,
                    config.expected_resolved_recovery_object_identity_sha256,
                    config.expected_storage_binding_sha256,
                )
            )
            and _object_identity(self._transaction_recovery)
            == config.expected_transaction_recovery_object_identity_sha256
            and _object_identity(self._resolved_recovery)
            == config.expected_resolved_recovery_object_identity_sha256
            and callable(transaction_call)
            and callable(resolved_call)
            and isinstance(maintenance_permit, Mapping)
            and maintenance_permit.get("state") == "QUIESCED"
            and maintenance_permit.get("registered_writer_count") == 19
            and maintenance_permit.get("inflight_mutations") == 0
            and maintenance_permit.get("shared_lock_acquired") is True
            and authority_v2.authenticated_root_authority_attestation_valid_v2(
                root_authority_attestation
            )
            and root_authority_attestation.get("storage_binding_sha256")
            == config.expected_storage_binding_sha256
            and type(now_epoch) is int
        ):
            raise RuntimeError("COORDINATED_MULTISTORE_RECOVERY_NOT_READY")
        shared = {
            "maintenance_permit": dict(maintenance_permit),
            "root_authority_attestation": dict(root_authority_attestation),
            "now_epoch": now_epoch,
        }
        transaction = transaction_call(**shared)
        if not self._port_receipt_valid(transaction, "TRANSACTION_STORE"):
            raise RuntimeError("TRANSACTION_STORE_RECOVERY_INVALID")
        resolved = resolved_call(**shared)
        if not self._port_receipt_valid(resolved, "RESOLVED_AUTHORITY_STORE"):
            raise RuntimeError("RESOLVED_AUTHORITY_STORE_RECOVERY_INVALID")
        for receipt in (transaction, resolved):
            if not (
                receipt["maintenance_epoch"] == maintenance_permit["maintenance_epoch"]
                and receipt["lock_namespace_sha256"]
                == maintenance_permit["lock_namespace_sha256"]
                and receipt["root_authority_attestation_sha256"]
                == root_authority_attestation["attestation_sha256"]
                and receipt["storage_binding_sha256"]
                == config.expected_storage_binding_sha256
            ):
                raise RuntimeError("MULTISTORE_RECOVERY_CROSS_BINDING_INVALID")
        result = {
            "ok": True,
            "receipt_version": boundary_v2.MULTISTORE_RECOVERY_RECEIPT_VERSION_V2,
            "maintenance_epoch": maintenance_permit["maintenance_epoch"],
            "lock_namespace_sha256": maintenance_permit["lock_namespace_sha256"],
            "root_authority_attestation_sha256": root_authority_attestation[
                "attestation_sha256"
            ],
            "storage_binding_sha256": config.expected_storage_binding_sha256,
            "transaction_store_recovered": True,
            "resolved_authority_store_recovered": True,
            "transaction_recovery_receipt_sha256": transaction["receipt_sha256"],
            "resolved_recovery_receipt_sha256": resolved["receipt_sha256"],
            "lock_order_verified": True,
            "reverse_release_verified": True,
            "all_locks_released": True,
            "prepared_transactions_remaining": 0,
            "resolved_transactions_remaining": 0,
            "filesystem_accessed": True,
            "temporary_storage_only": bool(
                transaction.get("temporary_storage_only")
                and resolved.get("temporary_storage_only")
            ),
            "synthetic_only": bool(
                transaction.get("synthetic_only")
                and resolved.get("synthetic_only")
            ),
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }
        result["receipt_sha256"] = boundary_v2.multistore_recovery_receipt_sha256_v2(
            result
        )
        return result


@dataclass(frozen=True, repr=False)
class DormantAuthenticatedPersistentAuthorityProductionAdaptersV2:
    root_state_provider: PersistentRootAuthorityStateProviderV2 = field(repr=False)
    root_authority_verifier: InjectedRootAuthorityVerifierV2 = field(repr=False)
    root_revocation_source: PersistentRootAuthorityRevocationSourceV2 = field(
        repr=False
    )
    multistore_recovery: CoordinatedMultistoreStartupRecoveryV2 = field(repr=False)

    def __repr__(self) -> str:
        return "DormantAuthenticatedPersistentAuthorityProductionAdaptersV2(<protected>)"

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2_VERSION,
            "enabled": False,
            "default_off": True,
            "adapter_count": 4,
            "dependencies_bound": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }


def build_dormant_authenticated_persistent_authority_production_adapters_v2(
) -> DormantAuthenticatedPersistentAuthorityProductionAdaptersV2:
    """Construct four disabled adapters without paths, keys, or I/O."""

    return DormantAuthenticatedPersistentAuthorityProductionAdaptersV2(
        root_state_provider=PersistentRootAuthorityStateProviderV2(),
        root_authority_verifier=InjectedRootAuthorityVerifierV2(),
        root_revocation_source=PersistentRootAuthorityRevocationSourceV2(),
        multistore_recovery=CoordinatedMultistoreStartupRecoveryV2(),
    )


__all__ = [
    "CoordinatedMultistoreRecoveryConfigV2",
    "CoordinatedMultistoreStartupRecoveryV2",
    "DormantAuthenticatedPersistentAuthorityProductionAdaptersV2",
    "InjectedRootAuthorityVerifierConfigV2",
    "InjectedRootAuthorityVerifierV2",
    "PRODUCTION_AUTHORITY_ADAPTERS_EXPLICIT_DEPENDENCY_SCOPE_V2",
    "PersistentAuthorityFileAdapterConfigV2",
    "PersistentRootAuthorityRevocationSourceV2",
    "PersistentRootAuthorityStateProviderV2",
    "ROOT_AUTHORITY_STATE_ENVELOPE_VERSION_V2",
    "ROOT_REVOCATION_STATE_ENVELOPE_VERSION_V2",
    "STORE_RECOVERY_PORT_RECEIPT_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2_VERSION",
    "authority_adapter_state_envelope_sha256_v2",
    "authority_adapter_storage_root_binding_sha256_v2",
    "build_dormant_authenticated_persistent_authority_production_adapters_v2",
    "store_recovery_port_receipt_sha256_v2",
]
