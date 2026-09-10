"""Authenticated persistent-authority boundary for C3 startup recovery.

The runtime builder is deliberately default-off and performs no I/O.  The
enabled reference surface is restricted to injected synthetic dependencies
and proves that one persisted root, one revocation view, one multistore
recovery receipt, and one startup bridge are bound to the same instances.
It never grants production, activation, Live, or trading authority.
"""

from __future__ import annotations

import copy
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_runtime_seam_v1 as runtime_seam_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-AUTHENTICATED-PERSISTENT-AUTHORITY-BOUNDARY-V2"
)
OFFLINE_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_SCOPE_ATTESTATION_V2 = (
    "C3_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_TEMPORARY_SYNTHETIC_ONLY_V2"
)
PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_VERSION_V2 = (
    "C3_PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_V2"
)
MULTISTORE_RECOVERY_RECEIPT_VERSION_V2 = "C3_MULTISTORE_RECOVERY_RECEIPT_V2"

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha(value: Any) -> bool:
    return bool(_SHA_RE.fullmatch(str(value or "").lower().strip()))


def _object_identity(value: Any) -> str:
    return identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
        value
    )


def persistent_root_authority_read_receipt_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def multistore_recovery_receipt_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "receipt_sha256"}
    )


def _permit_valid(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and set(value)
        == {
            "maintenance_epoch",
            "state",
            "lock_namespace_sha256",
            "registered_writer_count",
            "inflight_mutations",
            "shared_lock_acquired",
        }
        and _valid_sha(value.get("maintenance_epoch"))
        and value.get("state") == "QUIESCED"
        and _valid_sha(value.get("lock_namespace_sha256"))
        and value.get("registered_writer_count") == 19
        and value.get("inflight_mutations") == 0
        and value.get("shared_lock_acquired") is True
    )


def _root_read_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        attestation = value["root_authority_attestation"]
        return bool(
            value.get("ok") is True
            and value.get("receipt_version")
            == PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_VERSION_V2
            and _valid_sha(value.get("storage_binding_sha256"))
            and type(value.get("generation")) is int
            and value.get("generation") >= 1
            and value.get("durable_read_verified") is True
            and value.get("atomic_replace_on_write") is True
            and value.get("fsync_on_write") is True
            and value.get("filesystem_accessed") is True
            and value.get("temporary_storage_only") is True
            and value.get("synthetic_only") is True
            and value.get("real_registry_accessed") is False
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("no_order_sent") is True
            and authority_v2.authenticated_root_authority_attestation_valid_v2(
                attestation
            )
            and value.get("root_authority_attestation_sha256")
            == attestation["attestation_sha256"]
            and _valid_sha(value.get("receipt_sha256"))
            and hmac.compare_digest(
                value["receipt_sha256"],
                persistent_root_authority_read_receipt_sha256_v2(value),
            )
        )
    except Exception:
        return False


def _multistore_recovery_valid(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        return bool(
            value.get("ok") is True
            and value.get("receipt_version") == MULTISTORE_RECOVERY_RECEIPT_VERSION_V2
            and _valid_sha(value.get("maintenance_epoch"))
            and _valid_sha(value.get("lock_namespace_sha256"))
            and _valid_sha(value.get("root_authority_attestation_sha256"))
            and _valid_sha(value.get("storage_binding_sha256"))
            and value.get("transaction_store_recovered") is True
            and value.get("resolved_authority_store_recovered") is True
            and value.get("lock_order_verified") is True
            and value.get("reverse_release_verified") is True
            and value.get("all_locks_released") is True
            and value.get("prepared_transactions_remaining") == 0
            and value.get("resolved_transactions_remaining") == 0
            and value.get("filesystem_accessed") is True
            and value.get("temporary_storage_only") is True
            and value.get("synthetic_only") is True
            and value.get("real_registry_accessed") is False
            and value.get("network_accessed") is False
            and value.get("broker_called") is False
            and value.get("no_order_sent") is True
            and _valid_sha(value.get("receipt_sha256"))
            and hmac.compare_digest(
                value["receipt_sha256"],
                multistore_recovery_receipt_sha256_v2(value),
            )
        )
    except Exception:
        return False


@dataclass(frozen=True)
class AuthenticatedPersistentAuthorityBoundaryConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_root_state_provider_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_root_verifier_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_revocation_source_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_multistore_recovery_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_startup_bridge_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_storage_binding_sha256: str | None = field(default=None, repr=False)
    expected_root_authority_attestation_sha256: str | None = field(
        default=None, repr=False
    )


class AuthenticatedPersistentAuthorityBoundaryV2:
    """Fail-closed composition boundary over exact injected dependencies."""

    def __init__(
        self,
        config: AuthenticatedPersistentAuthorityBoundaryConfigV2 | None = None,
        *,
        root_state_provider: Any = None,
        root_authority_verifier: Any = None,
        root_revocation_source: Any = None,
        multistore_recovery: Any = None,
        startup_bridge: Any = None,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._config = config or AuthenticatedPersistentAuthorityBoundaryConfigV2()
        self._root_state_provider = root_state_provider
        self._root_verifier = root_authority_verifier
        self._revocation_source = root_revocation_source
        self._multistore_recovery = multistore_recovery
        self._startup_bridge = startup_bridge
        self._clock = clock

    def __repr__(self) -> str:
        return "AuthenticatedPersistentAuthorityBoundaryV2(<protected>)"

    @staticmethod
    def _failed(reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "C3_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_BLOCKED",
            "reason": reason,
            "persistent_root_read": False,
            "root_signature_verified": False,
            "root_revocation_checked": False,
            "root_revoked": None,
            "multistore_recovery_verified": False,
            "startup_bridge_verified": False,
            "filesystem_accessed": False,
            "real_registry_accessed": False,
            "network_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
            "synthetic_only": True,
            "temporary_storage_only": True,
            "production_authority": False,
            "production_ready": False,
            "runtime_integrated": False,
            "activation_allowed": False,
            "live_allowed": False,
        }

    def _reason(self) -> str | None:
        config = self._config
        if config.enabled is not True:
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_DEFAULT_OFF"
        if (
            config.scope_attestation
            != OFFLINE_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_SCOPE_ATTESTATION_V2
        ):
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_SCOPE_INVALID"
        pins = (
            config.expected_root_state_provider_object_identity_sha256,
            config.expected_root_verifier_object_identity_sha256,
            config.expected_revocation_source_object_identity_sha256,
            config.expected_multistore_recovery_object_identity_sha256,
            config.expected_startup_bridge_object_identity_sha256,
            config.expected_storage_binding_sha256,
            config.expected_root_authority_attestation_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_PINS_INVALID"
        methods = (
            getattr(self._root_state_provider, "read_current_root_authority_v2", None),
            getattr(self._root_verifier, "verify_root_authority_signature_v2", None),
            getattr(self._revocation_source, "root_authority_key_revoked_v2", None),
            getattr(self._multistore_recovery, "recover_multistore_v2", None),
            self._startup_bridge,
            self._clock,
        )
        if any(not callable(item) for item in methods):
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_DEPENDENCY_INVALID"
        values = (
            (self._root_state_provider, pins[0]),
            (self._root_verifier, pins[1]),
            (self._revocation_source, pins[2]),
            (self._multistore_recovery, pins[3]),
            (self._startup_bridge, pins[4]),
        )
        if any(_object_identity(value) != expected for value, expected in values):
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_INSTANCE_MISMATCH"
        if type(self._startup_bridge) is not bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2:
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_STARTUP_BRIDGE_INVALID"
        bridge_snapshot = self._startup_bridge.snapshot()
        if not (
            bridge_snapshot.get("temporary_offline_ready") is True
            and bridge_snapshot.get("storage_binding_sha256")
            == config.expected_storage_binding_sha256
            and bridge_snapshot.get("root_authority_attestation_sha256")
            == config.expected_root_authority_attestation_sha256
            and bridge_snapshot.get("production_ready") is False
            and bridge_snapshot.get("runtime_integrated") is False
            and bridge_snapshot.get("live_allowed") is False
        ):
            return "AUTHENTICATED_PERSISTENT_AUTHORITY_BRIDGE_CROSS_BINDING_INVALID"
        return None

    def snapshot(self) -> dict[str, Any]:
        reason = self._reason()
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_VERSION,
            "enabled": self._config.enabled is True,
            "default_off": self._config.enabled is not True,
            "temporary_offline_ready": reason is None,
            "reason": reason,
            "authenticated_root_provider_bound": reason is None,
            "persistent_revocation_source_bound": reason is None,
            "multistore_recovery_bound": reason is None,
            "startup_bridge_bound": reason is None,
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

    def __call__(self, maintenance_permit: Mapping[str, Any]) -> dict[str, Any]:
        reason = self._reason()
        if reason is not None:
            return self._failed(reason)
        if not _permit_valid(maintenance_permit):
            return self._failed("AUTHENTICATED_PERSISTENT_AUTHORITY_PERMIT_INVALID")
        try:
            now_epoch = self._clock()
        except Exception:
            return self._failed("AUTHENTICATED_PERSISTENT_AUTHORITY_CLOCK_FAILED")
        if type(now_epoch) is not int:
            return self._failed("AUTHENTICATED_PERSISTENT_AUTHORITY_CLOCK_INVALID")
        try:
            root_read = self._root_state_provider.read_current_root_authority_v2(
                now_epoch=now_epoch
            )
        except Exception:
            return self._failed("PERSISTENT_ROOT_AUTHORITY_READ_FAILED_CLOSED")
        if not _root_read_valid(root_read):
            return self._failed("PERSISTENT_ROOT_AUTHORITY_RECEIPT_INVALID")
        config = self._config
        attestation = copy.deepcopy(root_read["root_authority_attestation"])
        if not (
            root_read["storage_binding_sha256"]
            == config.expected_storage_binding_sha256
            == attestation["storage_binding_sha256"]
            and root_read["root_authority_attestation_sha256"]
            == config.expected_root_authority_attestation_sha256
            and attestation["issued_at_epoch"] <= now_epoch
            < attestation["expires_at_epoch"]
            and authority_v2.authenticated_root_authority_attestation_verified_v2(
                attestation, self._root_verifier
            )
        ):
            return self._failed("PERSISTENT_ROOT_AUTHORITY_NOT_AUTHENTICATED")
        try:
            revoked = self._revocation_source.root_authority_key_revoked_v2(
                key_id_sha256=attestation["key_id_sha256"],
                key_epoch=attestation["key_epoch"],
                now_epoch=now_epoch,
            )
        except Exception:
            return self._failed("PERSISTENT_ROOT_REVOCATION_READ_FAILED_CLOSED")
        if type(revoked) is not bool:
            return self._failed("PERSISTENT_ROOT_REVOCATION_RESULT_INVALID")
        if revoked:
            failed = self._failed("PERSISTENT_ROOT_AUTHORITY_REVOKED")
            failed["persistent_root_read"] = True
            failed["root_signature_verified"] = True
            failed["root_revocation_checked"] = True
            failed["root_revoked"] = True
            failed["filesystem_accessed"] = True
            return failed
        try:
            recovered = self._multistore_recovery.recover_multistore_v2(
                maintenance_permit=dict(maintenance_permit),
                root_authority_attestation=attestation,
                now_epoch=now_epoch,
            )
        except Exception:
            return self._failed("PERSISTENT_MULTISTORE_RECOVERY_FAILED_CLOSED")
        if not (
            _multistore_recovery_valid(recovered)
            and recovered["maintenance_epoch"]
            == maintenance_permit["maintenance_epoch"]
            and recovered["lock_namespace_sha256"]
            == maintenance_permit["lock_namespace_sha256"]
            and recovered["root_authority_attestation_sha256"]
            == attestation["attestation_sha256"]
            and recovered["storage_binding_sha256"]
            == config.expected_storage_binding_sha256
        ):
            return self._failed("PERSISTENT_MULTISTORE_RECOVERY_RECEIPT_INVALID")
        try:
            startup = self._startup_bridge(dict(maintenance_permit))
        except Exception:
            return self._failed("AUTHENTICATED_STARTUP_BRIDGE_FAILED_CLOSED")
        if not (
            isinstance(startup, Mapping)
            and startup.get("ok") is True
            and startup.get("maintenance_epoch")
            == maintenance_permit["maintenance_epoch"]
            and startup.get("lock_namespace_sha256")
            == maintenance_permit["lock_namespace_sha256"]
            and startup.get("storage_binding_sha256")
            == config.expected_storage_binding_sha256
            and startup.get("root_authority_attestation_sha256")
            == config.expected_root_authority_attestation_sha256
            and startup.get("prepared_transactions_after") == 0
            and startup.get("resolved_transactions_after") == 0
            and startup.get("unresolved_transactions_after") == 0
            and startup.get("real_registry_accessed") is False
            and startup.get("network_accessed") is False
            and startup.get("broker_called") is False
            and startup.get("no_order_sent") is True
            and _valid_sha(startup.get("startup_recovery_attestation_sha256"))
            and hmac.compare_digest(
                startup["startup_recovery_attestation_sha256"],
                runtime_seam_v1.startup_recovery_attestation_sha256_v1(startup),
            )
        ):
            return self._failed("AUTHENTICATED_STARTUP_BRIDGE_RECEIPT_INVALID")
        result = dict(startup)
        result.update(
            {
                "status": "C3_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_COMPLETED_OFFLINE",
                "boundary_version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_VERSION,
                "persistent_root_read": True,
                "persistent_root_read_receipt_sha256": root_read["receipt_sha256"],
                "root_signature_verified": True,
                "root_revocation_checked": True,
                "root_revoked": False,
                "multistore_recovery_verified": True,
                "multistore_recovery_receipt_sha256": recovered["receipt_sha256"],
                "startup_bridge_verified": True,
                "filesystem_accessed": True,
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_authority": False,
                "production_ready": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
            }
        )
        result["startup_recovery_attestation_sha256"] = (
            runtime_seam_v1.startup_recovery_attestation_sha256_v1(result)
        )
        return result


def build_dormant_authenticated_persistent_authority_boundary_v2(
    *,
    root_state_provider: Any = None,
    root_authority_verifier: Any = None,
    root_revocation_source: Any = None,
    multistore_recovery: Any = None,
    startup_bridge: Any = None,
) -> AuthenticatedPersistentAuthorityBoundaryV2:
    """Build the no-I/O placeholder; supplied bridge is retained but not called."""

    return AuthenticatedPersistentAuthorityBoundaryV2(
        root_state_provider=root_state_provider,
        root_authority_verifier=root_authority_verifier,
        root_revocation_source=root_revocation_source,
        multistore_recovery=multistore_recovery,
        startup_bridge=startup_bridge,
    )


__all__ = [
    "AuthenticatedPersistentAuthorityBoundaryConfigV2",
    "AuthenticatedPersistentAuthorityBoundaryV2",
    "MULTISTORE_RECOVERY_RECEIPT_VERSION_V2",
    "OFFLINE_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_SCOPE_ATTESTATION_V2",
    "PERSISTENT_ROOT_AUTHORITY_READ_RECEIPT_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_BOUNDARY_V2_VERSION",
    "build_dormant_authenticated_persistent_authority_boundary_v2",
    "multistore_recovery_receipt_sha256_v2",
    "persistent_root_authority_read_receipt_sha256_v2",
]
