"""Default-off production-shaped adapters for authenticated C3 recovery.

No path, key provider, or recovery port is inferred.  Default construction is
side-effect free.  Enabled construction requires explicit path and instance
pins; the reference tests use temporary synthetic storage only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as authority_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2 as boundary_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2 as bridge_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as lock_storage_v1
import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_v1


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
PHYSICAL_STORE_RECOVERY_EVIDENCE_VERSION_V2 = "C3_TEMPORARY_PHYSICAL_STORE_RECOVERY_EVIDENCE_V2"
ROOT_HMAC_LOCAL_KEY_MODE_V2 = "ROOT_HMAC_LOCAL_KEY_V2"
ROOT_HMAC_REMOTE_VERDICT_MODE_V2 = "ROOT_HMAC_REMOTE_VERDICT_V2"

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
    verification_mode: str = ROOT_HMAC_LOCAL_KEY_MODE_V2


def physical_store_recovery_evidence_sha256_v2(value: Mapping[str, Any]) -> str:
    return hash_v2.stable_sha256_v2(
        {key: item for key, item in value.items() if key != "evidence_sha256"}
    )


def _physical_store_recovery_evidence_valid_v2(
    value: Any, role: str, port_receipt: Mapping[str, Any],
) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        return bool(
            set(value) == {
                "evidence_version", "store_role", "maintenance_epoch",
                "storage_binding_sha256", "source_store_instance_sha256",
                "source_receipt_sha256", "postcondition_receipt_sha256",
                "unresolved_transactions_remaining", "physical_store_accessed",
                "temporary_storage_only", "synthetic_only", "production_authority",
                "evidence_sha256",
            }
            and value["evidence_version"] == PHYSICAL_STORE_RECOVERY_EVIDENCE_VERSION_V2
            and value["store_role"] == role
            and value["maintenance_epoch"] == port_receipt["maintenance_epoch"]
            and value["storage_binding_sha256"] == port_receipt["storage_binding_sha256"]
            and all(_valid_sha(value[key]) for key in (
                "source_store_instance_sha256", "source_receipt_sha256",
                "postcondition_receipt_sha256", "evidence_sha256",
            ))
            and type(value["unresolved_transactions_remaining"]) is int
            and value["unresolved_transactions_remaining"] == 0
            and value["physical_store_accessed"] is True
            and value["temporary_storage_only"] is True
            and value["synthetic_only"] is True
            and value["production_authority"] is False
            and hmac.compare_digest(
                value["evidence_sha256"],
                physical_store_recovery_evidence_sha256_v2(value),
            )
        )
    except Exception:
        return False


class InjectedRootAuthorityVerifierV2:
    """Default-off HMAC root verifier with an explicit remote-verdict option.

    The remote provider must pin the key identity and validate the exact MAC;
    this class contains no SDK, credential lookup, network access, or fallback.
    """

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
        if not all(
            type(item) is str and _SHA_RE.fullmatch(item)
            for item in (key_id_sha256, payload_sha256, signature_sha256)
        ):
            return False
        if self._config.verification_mode == ROOT_HMAC_REMOTE_VERDICT_MODE_V2:
            try:
                verify = getattr(self._key_provider, "verify_root_hmac_v2", None)
                if not callable(verify):
                    return False
                return verify(
                    key_id_sha256=key_id_sha256,
                    message=payload_sha256.encode("ascii"),
                    mac=bytes.fromhex(signature_sha256),
                    mac_algorithm="HMAC_SHA_256",
                ) is True
            except Exception:
                return False
        if self._config.verification_mode != ROOT_HMAC_LOCAL_KEY_MODE_V2:
            return False
        resolver = getattr(self._key_provider, "resolve_root_hmac_key_v2", None)
        if not callable(resolver):
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
    expected_lock_backend_object_identity_sha256: str | None = field(default=None, repr=False)
    expected_lock_storage_root_binding_sha256: str | None = field(default=None, repr=False)
    transaction_lock_namespace_sha256: str | None = field(default=None, repr=False)
    resolved_lock_namespace_sha256: str | None = field(default=None, repr=False)
    lock_timeout_seconds: float = 1.0
    expected_maintenance_coordinator_object_identity_sha256: str | None = field(default=None, repr=False)
    require_physical_recovery_evidence: bool = False


class CoordinatedMultistoreStartupRecoveryV2:
    def __init__(
        self,
        config: CoordinatedMultistoreRecoveryConfigV2 | None = None,
        *,
        transaction_recovery: Any = None,
        resolved_recovery: Any = None,
        lock_backend: Any = None,
        maintenance_coordinator: Any = None,
    ) -> None:
        self._config = config or CoordinatedMultistoreRecoveryConfigV2()
        self._transaction_recovery = transaction_recovery
        self._resolved_recovery = resolved_recovery
        self._lock_backend = lock_backend
        self._maintenance_coordinator = maintenance_coordinator

    def __repr__(self) -> str:
        return "CoordinatedMultistoreStartupRecoveryV2(<protected>)"

    def dormant_coordinator_bound_v2(self, coordinator: Any) -> bool:
        """Check the disabled startup edge without acquiring a lease or doing I/O."""
        return bool(
            self._config.enabled is False
            and type(coordinator) is coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1
            and coordinator.enabled is False
            and self._maintenance_coordinator is coordinator
            and self._config.expected_maintenance_coordinator_object_identity_sha256
            == _object_identity(coordinator)
        )

    def coordinated_bridge_bound_v2(self, bridge: Any) -> bool:
        """Require the same live lease owner and RESOLVED lock for bridge reads."""
        return bool(
            self._config.enabled is True
            and type(bridge) is bridge_v2.ResolvedAuthorityStartupRecoveryBridgeV2
            and bridge._config.require_coordinated_physical_recovery is True
            and bridge._maintenance_coordinator is self._maintenance_coordinator
            and bridge._lock_backend is self._lock_backend
            and bridge._config.resolved_lock_namespace_sha256
            == self._config.resolved_lock_namespace_sha256
        )

    def maintenance_permit_current_v2(self, permit: Mapping[str, Any]) -> bool:
        """Expose only a current-lease check for the optional offline audit."""
        try:
            self._require_current_maintenance(permit, self._lock_backend)
            return True
        except Exception:
            return False

    def _lock_plan(self, maintenance_namespace: str) -> tuple[Any, tuple[str, str]]:
        """Bind explicit store locks, never infer the writer-maintenance lock.

        This proves only ownership of these injected OS locks. It does not
        authenticate a production mapping or prove the outer maintenance lease.
        All participating store writers must use the same backend/namespaces.
        """
        config, backend = self._config, self._lock_backend
        namespaces = (config.transaction_lock_namespace_sha256,
                      config.resolved_lock_namespace_sha256)
        if not (
            type(backend) is lock_storage_v1.CrossPlatformInterprocessFileLockBackendV1
            and backend.enabled is True
            and _object_identity(backend) == config.expected_lock_backend_object_identity_sha256
            and authority_adapter_storage_root_binding_sha256_v2(backend.storage_root)
            == config.expected_lock_storage_root_binding_sha256
            and all(type(ns) is str and _SHA_RE.fullmatch(ns) for ns in namespaces)
            and type(maintenance_namespace) is str
            and _SHA_RE.fullmatch(maintenance_namespace)
            and len(set((*namespaces, maintenance_namespace))) == 3
            and type(config.lock_timeout_seconds) in (int, float)
            and math.isfinite(config.lock_timeout_seconds)
            and config.lock_timeout_seconds > 0
            and all(
                getattr(port, "recovery_lock_backend", None) is backend
                and getattr(port, "recovery_lock_namespace_sha256", None) == namespace
                for port, namespace in zip(
                    (self._transaction_recovery, self._resolved_recovery), namespaces
                )
            )
        ):
            raise RuntimeError("MULTISTORE_LOCK_DEPENDENCIES_INVALID")
        return backend, namespaces

    def _require_current_maintenance(self, permit: Mapping[str, Any], backend: Any) -> None:
        coordinator = self._maintenance_coordinator
        if not (
            type(coordinator) is coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1
            and _object_identity(coordinator)
            == self._config.expected_maintenance_coordinator_object_identity_sha256
            and coordinator.maintenance_permit_is_current_v1(permit, lock_backend=backend) is True
        ):
            raise RuntimeError("MULTISTORE_MAINTENANCE_NOT_CURRENT")

    @staticmethod
    def _port_receipt_valid(
        value: Any, role: str, require_physical_evidence: bool = False,
    ) -> bool:
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
                and (
                    _physical_store_recovery_evidence_valid_v2(
                        value["physical_recovery_evidence"], role, value,
                    ) if "physical_recovery_evidence" in value
                    else not require_physical_evidence
                )
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
            and type(config.require_physical_recovery_evidence) is bool
        ):
            raise RuntimeError("COORDINATED_MULTISTORE_RECOVERY_NOT_READY")
        backend, namespaces = self._lock_plan(maintenance_permit.get("lock_namespace_sha256"))
        # Snapshot bindings before invoking any injected port. Each port receives
        # fresh copies, so mutation by one cannot rebind the next store or receipt.
        permit_snapshot = dict(maintenance_permit)
        root_snapshot = dict(root_authority_attestation)
        self._require_current_maintenance(permit_snapshot, backend)
        receipts = []
        acquired = []
        released = []
        deadline = time.monotonic() + config.lock_timeout_seconds
        try:
            for namespace in namespaces:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("MULTISTORE_LOCK_DEADLINE_EXCEEDED")
                handle = backend.acquire(namespace, remaining)
                if handle is None:
                    raise RuntimeError("MULTISTORE_LOCK_ACQUISITION_FAILED")
                acquired.append((namespace, handle))
                if not (type(handle) is lock_storage_v1.InterprocessFileLockHandleV1
                        and handle.released is False):
                    raise RuntimeError("MULTISTORE_LOCK_HANDLE_INVALID")
                if time.monotonic() >= deadline:
                    raise RuntimeError("MULTISTORE_LOCK_DEADLINE_EXCEEDED")
            for recovery_call, role in (
                (transaction_call, "TRANSACTION_STORE"),
                (resolved_call, "RESOLVED_AUTHORITY_STORE"),
            ):
                self._require_current_maintenance(permit_snapshot, backend)
                if not all(handle.released is False for _, handle in acquired):
                    raise RuntimeError("MULTISTORE_LOCK_OWNERSHIP_LOST")
                receipt = recovery_call(
                    maintenance_permit=dict(permit_snapshot),
                    root_authority_attestation=dict(root_snapshot), now_epoch=now_epoch,
                )
                self._require_current_maintenance(permit_snapshot, backend)
                if not all(handle.released is False for _, handle in acquired):
                    raise RuntimeError("MULTISTORE_LOCK_OWNERSHIP_LOST")
                if not self._port_receipt_valid(
                    receipt, role, config.require_physical_recovery_evidence,
                ):
                    raise RuntimeError(f"{role}_RECOVERY_INVALID")
                # Validate this store before invoking the next one, under both locks.
                if not (
                    receipt["maintenance_epoch"] == permit_snapshot["maintenance_epoch"]
                    and receipt["lock_namespace_sha256"] == permit_snapshot["lock_namespace_sha256"]
                    and receipt["root_authority_attestation_sha256"] == root_snapshot["attestation_sha256"]
                    and receipt["storage_binding_sha256"] == config.expected_storage_binding_sha256
                ):
                    raise RuntimeError("MULTISTORE_RECOVERY_CROSS_BINDING_INVALID")
                receipts.append(dict(receipt))
        finally:
            release_failed = False
            for namespace, handle in reversed(acquired):
                try:
                    handle.release()
                    if handle.released is not True:
                        raise RuntimeError("MULTISTORE_LOCK_RELEASE_UNCONFIRMED")
                    released.append(namespace)
                except BaseException:
                    # Attempt every remaining release, but never emit success if
                    # even one failed (the OS handle may still report released).
                    release_failed = True
            if release_failed:
                raise RuntimeError("MULTISTORE_LOCK_RELEASE_FAILED")
        self._require_current_maintenance(permit_snapshot, backend)
        transaction, resolved = receipts
        result = {
            "ok": True,
            "receipt_version": boundary_v2.MULTISTORE_RECOVERY_RECEIPT_VERSION_V2,
            "maintenance_epoch": permit_snapshot["maintenance_epoch"],
            "lock_namespace_sha256": permit_snapshot["lock_namespace_sha256"],
            "root_authority_attestation_sha256": root_snapshot[
                "attestation_sha256"
            ],
            "storage_binding_sha256": config.expected_storage_binding_sha256,
            "transaction_store_recovered": True,
            "resolved_authority_store_recovered": True,
            "transaction_recovery_receipt_sha256": transaction["receipt_sha256"],
            "resolved_recovery_receipt_sha256": resolved["receipt_sha256"],
            "lock_order_verified": tuple(ns for ns, _ in acquired) == namespaces,
            "reverse_release_verified": tuple(released) == tuple(reversed(namespaces)),
            "all_locks_released": len(released) == 2 and all(
                handle.released is True for _, handle in acquired),
            "lock_proof_scope": "INJECTED_STORE_LOCKS_ONLY_V2",
            "store_lock_namespaces_sha256": list(namespaces),
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
        if config.require_physical_recovery_evidence:
            # This verifies the injected port's envelope, not source authenticity.
            result["physical_evidence_envelope_verified"] = True
            result["transaction_physical_evidence_sha256"] = transaction[
                "physical_recovery_evidence"
            ]["evidence_sha256"]
            result["resolved_physical_evidence_sha256"] = resolved[
                "physical_recovery_evidence"
            ]["evidence_sha256"]
            result["transaction_physical_store_instance_sha256"] = transaction[
                "physical_recovery_evidence"
            ]["source_store_instance_sha256"]
            result["transaction_postcondition_audit_sha256"] = transaction[
                "physical_recovery_evidence"
            ]["postcondition_receipt_sha256"]
            result["resolved_physical_ledger_identity_sha256"] = resolved[
                "physical_recovery_evidence"
            ]["source_store_instance_sha256"]
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
    *, maintenance_coordinator: Any = None,
) -> DormantAuthenticatedPersistentAuthorityProductionAdaptersV2:
    """Construct disabled adapters, optionally pinning the same dormant coordinator.

    No physical lock, storage root or authority is inferred from this binding.
    It cannot be promoted to readiness: all operational dependencies remain absent.
    """

    if maintenance_coordinator is not None and not (
        type(maintenance_coordinator) is coordinator_v1.ClosedRepairWriterRuntimeCoordinatorV1
        and maintenance_coordinator.enabled is False
    ):
        raise RuntimeError("DORMANT_MAINTENANCE_COORDINATOR_REQUIRED")

    return DormantAuthenticatedPersistentAuthorityProductionAdaptersV2(
        root_state_provider=PersistentRootAuthorityStateProviderV2(),
        root_authority_verifier=InjectedRootAuthorityVerifierV2(),
        root_revocation_source=PersistentRootAuthorityRevocationSourceV2(),
        multistore_recovery=CoordinatedMultistoreStartupRecoveryV2(
            config=CoordinatedMultistoreRecoveryConfigV2(
                expected_maintenance_coordinator_object_identity_sha256=(
                    _object_identity(maintenance_coordinator)
                    if maintenance_coordinator is not None else None
                ),
            ),
            maintenance_coordinator=maintenance_coordinator,
        ),
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
    "PHYSICAL_STORE_RECOVERY_EVIDENCE_VERSION_V2",
    "ROOT_AUTHORITY_STATE_ENVELOPE_VERSION_V2",
    "ROOT_REVOCATION_STATE_ENVELOPE_VERSION_V2",
    "STORE_RECOVERY_PORT_RECEIPT_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_AUTHENTICATED_PERSISTENT_AUTHORITY_PRODUCTION_ADAPTERS_V2_VERSION",
    "authority_adapter_state_envelope_sha256_v2",
    "authority_adapter_storage_root_binding_sha256_v2",
    "build_dormant_authenticated_persistent_authority_production_adapters_v2",
    "physical_store_recovery_evidence_sha256_v2",
    "store_recovery_port_receipt_sha256_v2",
]
