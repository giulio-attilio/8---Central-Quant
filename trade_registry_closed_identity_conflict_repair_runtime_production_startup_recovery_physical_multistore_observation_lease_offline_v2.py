"""Shared two-store observation lease for synthetic temporary C3 evidence."""

from __future__ import annotations

import threading
import re
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2 as physical_v2
import trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2 as durable_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as storage_v1


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PHYSICAL-MULTISTORE-OBSERVATION-LEASE-"
    "OFFLINE-V2"
)
OFFLINE_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2 = (
    "C3_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_TEMPORARY_ONLY_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


class TemporaryPhysicalObservationLeaseBlockedV2(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, repr=False)
class ProtectedPhysicalMultiStoreObservationLeaseTokenV2:
    token_sha256: str = field(repr=False)
    backend_object_identity_sha256: str = field(repr=False)
    ledger_object_identity_sha256: str = field(repr=False)
    backend_lock_namespace_sha256: str = field(repr=False)
    resolved_ledger_storage_binding_sha256: str = field(repr=False)
    lock_order_sha256: str = field(repr=False)
    issued_at_epoch: int = field(repr=False)
    expires_at_epoch: int = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedPhysicalMultiStoreObservationLeaseTokenV2(<protected>)"


@dataclass(frozen=True)
class PhysicalMultiStoreObservationLeaseConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_backend_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_ledger_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_backend_lock_namespace_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_ledger_storage_binding_sha256: str | None = field(
        default=None, repr=False
    )
    max_ttl_seconds: int = 300
    lock_timeout_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not 1 <= self.max_ttl_seconds <= 300:
            raise ValueError("max_ttl_seconds must be between 1 and 300")
        if not 0 < self.lock_timeout_seconds <= 1:
            raise ValueError("lock_timeout_seconds must be between 0 and 1")


class PhysicalMultiStoreObservationLeaseV2:
    def __init__(
        self,
        config: PhysicalMultiStoreObservationLeaseConfigV2 | None = None,
        *,
        backend: Any = None,
        durable_authority_ledger: Any = None,
        clock: Callable[[], int] | None = None,
        nonce_source: Callable[[], str] | None = None,
    ) -> None:
        self._config = config or PhysicalMultiStoreObservationLeaseConfigV2()
        self._backend = backend
        self._ledger = durable_authority_ledger
        self._clock = clock or (lambda: 0)
        self._nonce_source = nonce_source or (lambda: "")
        self._state_lock = threading.Lock()
        self._acquiring = False
        self._active_token: ProtectedPhysicalMultiStoreObservationLeaseTokenV2 | None = None
        self._active_handles: tuple[storage_v1.InterprocessFileLockHandleV1, ...] = ()

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2
        ):
            return "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_INVALID"
        pins = (
            self._config.expected_backend_object_identity_sha256,
            self._config.expected_ledger_object_identity_sha256,
            self._config.expected_backend_lock_namespace_sha256,
            self._config.expected_resolved_ledger_storage_binding_sha256,
        )
        if any(not _valid_sha(item) for item in pins):
            return "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_PINS_INVALID"
        return None

    def _dependencies_reason(self) -> str | None:
        if not (
            type(self._backend)
            is physical_v2.TemporaryPhysicalDurableRawTransactionBackendV2
            and type(self._ledger)
            is durable_v2.DormantDurableReconciliationAuthorityLedgerV2
        ):
            return "PHYSICAL_MULTISTORE_OBSERVATION_DEPENDENCIES_INVALID"
        backend_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._backend
            )
        )
        ledger_identity = (
            identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                self._ledger
            )
        )
        storage = vars(self._ledger).get("_storage")
        if storage is None:
            return "PHYSICAL_MULTISTORE_OBSERVATION_LEDGER_STORAGE_INVALID"
        storage_binding = durable_v2.durable_authority_storage_binding_sha256_v2(
            storage
        )
        backend_namespace = self._backend._lock_namespace()
        if not (
            backend_identity
            == self._config.expected_backend_object_identity_sha256
            and ledger_identity
            == self._config.expected_ledger_object_identity_sha256
            and backend_namespace
            == self._config.expected_backend_lock_namespace_sha256
            and storage_binding
            == self._config.expected_resolved_ledger_storage_binding_sha256
        ):
            return "PHYSICAL_MULTISTORE_OBSERVATION_DEPENDENCY_PIN_MISMATCH"
        backend_root = Path(vars(self._backend).get("_root")).resolve(strict=False)
        ledger_paths = (
            Path(storage.snapshot_path),
            Path(storage.journal_path),
            Path(storage.lock_path),
            Path(storage.backup_dir),
        )
        if any(
            not path.resolve(strict=False).is_relative_to(backend_root)
            for path in ledger_paths
        ):
            return "PHYSICAL_MULTISTORE_OBSERVATION_STORAGE_ROOT_MISMATCH"
        return None

    def _specs(self) -> tuple[tuple[Any, str], tuple[Any, str]]:
        return (
            (
                vars(self._backend).get("_lock_backend"),
                str(self._config.expected_backend_lock_namespace_sha256),
            ),
            (
                vars(self._ledger).get("_lock_backend"),
                str(
                    self._config.expected_resolved_ledger_storage_binding_sha256
                ),
            ),
        )

    @contextmanager
    def hold_offline(
        self, *, expires_at_epoch: int
    ) -> Iterator[ProtectedPhysicalMultiStoreObservationLeaseTokenV2]:
        reason = self._config_reason()
        if reason is not None:
            raise TemporaryPhysicalObservationLeaseBlockedV2(reason)
        reason = self._dependencies_reason()
        if reason is not None:
            raise TemporaryPhysicalObservationLeaseBlockedV2(reason)
        try:
            now_epoch = self._clock()
            nonce = str(self._nonce_source())
        except Exception as exc:
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SOURCE_FAILED"
            ) from exc
        if not (
            type(now_epoch) is int
            and type(expires_at_epoch) is int
            and now_epoch < expires_at_epoch
            and expires_at_epoch - now_epoch <= self._config.max_ttl_seconds
            and nonce
        ):
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_TIME_OR_NONCE_INVALID"
            )
        with self._state_lock:
            if self._acquiring or self._active_token is not None:
                raise TemporaryPhysicalObservationLeaseBlockedV2(
                    "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_ALREADY_ACTIVE"
                )
            self._acquiring = True
        handles: list[storage_v1.InterprocessFileLockHandleV1] = []
        token: ProtectedPhysicalMultiStoreObservationLeaseTokenV2 | None = None
        try:
            for lock_backend, namespace in self._specs():
                if type(lock_backend) is not storage_v1.CrossPlatformInterprocessFileLockBackendV1:
                    raise TemporaryPhysicalObservationLeaseBlockedV2(
                        "PHYSICAL_MULTISTORE_OBSERVATION_LOCK_BACKEND_INVALID"
                    )
                handle = lock_backend.acquire(
                    namespace, self._config.lock_timeout_seconds
                )
                if handle is None:
                    raise TemporaryPhysicalObservationLeaseBlockedV2(
                        "PHYSICAL_MULTISTORE_OBSERVATION_LOCK_TIMEOUT"
                    )
                handles.append(handle)
            backend_identity = str(
                self._config.expected_backend_object_identity_sha256
            )
            ledger_identity = str(
                self._config.expected_ledger_object_identity_sha256
            )
            lock_order_sha256 = hash_v2.stable_sha256_v2(
                {
                    "order": "BACKEND_THEN_RESOLVED_LEDGER",
                    "backend_lock_namespace_sha256": self._config.expected_backend_lock_namespace_sha256,
                    "resolved_ledger_storage_binding_sha256": self._config.expected_resolved_ledger_storage_binding_sha256,
                }
            )
            token = ProtectedPhysicalMultiStoreObservationLeaseTokenV2(
                token_sha256=hash_v2.stable_sha256_v2(
                    {
                        "kind": "C3_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_TOKEN_V2",
                        "backend_object_identity_sha256": backend_identity,
                        "ledger_object_identity_sha256": ledger_identity,
                        "lock_order_sha256": lock_order_sha256,
                        "issued_at_epoch": now_epoch,
                        "expires_at_epoch": expires_at_epoch,
                        "nonce": nonce,
                    }
                ),
                backend_object_identity_sha256=backend_identity,
                ledger_object_identity_sha256=ledger_identity,
                backend_lock_namespace_sha256=str(
                    self._config.expected_backend_lock_namespace_sha256
                ),
                resolved_ledger_storage_binding_sha256=str(
                    self._config.expected_resolved_ledger_storage_binding_sha256
                ),
                lock_order_sha256=lock_order_sha256,
                issued_at_epoch=now_epoch,
                expires_at_epoch=expires_at_epoch,
            )
            with self._state_lock:
                self._active_token = token
                self._active_handles = tuple(handles)
                self._acquiring = False
            yield token
        finally:
            with self._state_lock:
                self._acquiring = False
                if self._active_token is token:
                    self._active_token = None
                    self._active_handles = ()
            release_error: Exception | None = None
            for handle in reversed(handles):
                if not handle.released:
                    try:
                        handle.release()
                    except Exception as exc:
                        release_error = release_error or exc
            if release_error is not None:
                raise TemporaryPhysicalObservationLeaseBlockedV2(
                    "PHYSICAL_MULTISTORE_OBSERVATION_LOCK_RELEASE_FAILED"
                ) from release_error

    def validate_live(
        self,
        token: Any,
        *,
        backend: Any,
        durable_authority_ledger: Any,
        now_epoch: int,
    ) -> bool:
        if (
            type(token) is not ProtectedPhysicalMultiStoreObservationLeaseTokenV2
            or backend is not self._backend
            or durable_authority_ledger is not self._ledger
            or type(now_epoch) is not int
        ):
            return False
        with self._state_lock:
            return bool(
                token is self._active_token
                and len(self._active_handles) == 2
                and all(not handle.released for handle in self._active_handles)
                and token.issued_at_epoch <= now_epoch < token.expires_at_epoch
                and token.backend_object_identity_sha256
                == self._config.expected_backend_object_identity_sha256
                and token.ledger_object_identity_sha256
                == self._config.expected_ledger_object_identity_sha256
                and token.backend_lock_namespace_sha256
                == self._config.expected_backend_lock_namespace_sha256
                and token.resolved_ledger_storage_binding_sha256
                == self._config.expected_resolved_ledger_storage_binding_sha256
                and _valid_sha(token.token_sha256)
                and _valid_sha(token.lock_order_sha256)
            )

    def _require_live(
        self,
        token: Any,
        *,
        now_epoch: int,
    ) -> None:
        if not self.validate_live(
            token,
            backend=self._backend,
            durable_authority_ledger=self._ledger,
            now_epoch=now_epoch,
        ):
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_OBSERVATION_LEASE_NOT_LIVE"
            )

    def read_backend_snapshot_offline(
        self, token: Any, *, now_epoch: int
    ) -> Mapping[str, Any]:
        self._require_live(token, now_epoch=now_epoch)
        try:
            return self._backend.snapshot_offline()
        except Exception as exc:
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_BACKEND_SNAPSHOT_READ_FAILED"
            ) from exc

    def read_transaction_log_audit_offline(
        self, token: Any, *, now_epoch: int
    ) -> Mapping[str, Any]:
        self._require_live(token, now_epoch=now_epoch)
        try:
            return self._backend.inspect_transaction_log_offline()
        except Exception as exc:
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_TRANSACTION_LOG_READ_FAILED"
            ) from exc

    def read_prepared_catalog_offline(
        self, token: Any, *, now_epoch: int
    ) -> Mapping[str, Any]:
        self._require_live(token, now_epoch=now_epoch)
        try:
            return self._backend.list_prepared_transactions_offline()
        except Exception as exc:
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_PREPARED_CATALOG_READ_FAILED"
            ) from exc

    def read_resolved_scan_offline(
        self, token: Any, *, now_epoch: int
    ) -> Mapping[str, Any]:
        self._require_live(token, now_epoch=now_epoch)
        try:
            snapshot, failure = self._ledger._read_valid_locked()
            if failure is not None or snapshot is None:
                raise ValueError(failure or "RESOLVED_LEDGER_SNAPSHOT_INVALID")
            return self._ledger._resolved_scan_from_snapshot(snapshot)
        except Exception as exc:
            raise TemporaryPhysicalObservationLeaseBlockedV2(
                "PHYSICAL_MULTISTORE_RESOLVED_SCAN_READ_FAILED"
            ) from exc

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "active": self._active_token is not None,
                "held_lock_count": len(self._active_handles),
                "all_handles_live": bool(
                    self._active_handles
                    and all(
                        not handle.released for handle in self._active_handles
                    )
                ),
                "synthetic_only": True,
                "temporary_storage_only": True,
                "production_authority": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
            }


__all__ = [
    "OFFLINE_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_SCOPE_ATTESTATION_V2",
    "PhysicalMultiStoreObservationLeaseConfigV2",
    "PhysicalMultiStoreObservationLeaseV2",
    "ProtectedPhysicalMultiStoreObservationLeaseTokenV2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PHYSICAL_MULTISTORE_OBSERVATION_LEASE_OFFLINE_V2_VERSION",
    "TemporaryPhysicalObservationLeaseBlockedV2",
]
