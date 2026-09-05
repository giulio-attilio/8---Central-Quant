"""Isolated runtime coordinator core for the 19 CLOSED-repair writers.

The coordinator is disabled by default and has no concrete persistence, file
lock, runtime installation or repair adapter.  Locking, lease storage, time and
nonce generation are injected so the protocol can be exercised without I/O.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import re
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

import trade_registry_closed_identity_conflict_repair_writer_coordination_contract_v1 as coordination
import trade_registry_closed_identity_conflict_repair_writer_runtime_storage_adapters_v1 as runtime_storage


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-RUNTIME-COORDINATOR-V1"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_LEASE_STATES = frozenset({"REQUESTED", "DRAINING", "QUIESCED"})
_LEASE_STATES = frozenset({*_ACTIVE_LEASE_STATES, "RELEASED"})
_NAMESPACE_PURPOSE = "TRADE_REGISTRY_FULL_RMW_COORDINATION"
SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1 = (
    "SYNTHETIC_OFFLINE_STALE_MAINTENANCE_LEASE_RECOVERY_ONLY_V1"
)
PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1 = (
    "C3_PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_V1"
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


def canonical_runtime_writer_inventory_v1() -> list[dict[str, str]]:
    return copy.deepcopy(coordination.canonical_closed_repair_writer_inventory_v1())


def canonical_runtime_lock_namespace_v1() -> str:
    return _stable_sha256(
        {
            "authority_id": "TRADE_REGISTRY_CANONICAL_RAW_DOCUMENT_V1",
            "purpose": _NAMESPACE_PURPOSE,
        }
    )


class SharedLockHandle(Protocol):
    def release(self) -> None: ...


class SharedLockBackend(Protocol):
    def acquire(
        self, namespace: str, timeout_seconds: float
    ) -> SharedLockHandle | None: ...


class MaintenanceLeaseStore(Protocol):
    def read(self, namespace: str) -> Mapping[str, Any] | None: ...

    def write(self, namespace: str, lease: Mapping[str, Any]) -> None: ...


class _DenyLockBackend:
    def acquire(
        self, namespace: str, timeout_seconds: float
    ) -> SharedLockHandle | None:
        return None


class _DenyLeaseStore:
    def read(self, namespace: str) -> Mapping[str, Any] | None:
        return None

    def write(self, namespace: str, lease: Mapping[str, Any]) -> None:
        raise RuntimeError("LEASE_STORE_NOT_CONFIGURED")


class WriterRuntimeCoordinationBlocked(RuntimeError):
    """Fail-closed protocol rejection with a stable, non-sensitive reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class WriterRuntimeCoordinatorConfigV1:
    enabled: bool = False
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")


@dataclass(frozen=True)
class ProductionWriterRuntimeCoordinatorBindingConfigV1:
    enabled: bool = False
    scope_attestation: str | None = None
    storage_root_binding_sha256: str | None = None
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive")


@dataclass(frozen=True)
class WriterMutationPermitV1:
    writer_id: str
    status: str
    admitted: bool
    coordinated: bool
    owner_token: str | None
    depth: int
    reentrant: bool
    shared_lock_acquired: bool


@dataclass(frozen=True)
class WriterMaintenancePermitV1:
    maintenance_epoch: str
    state: str
    lock_namespace_sha256: str
    registered_writer_count: int
    inflight_mutations: int
    shared_lock_acquired: bool


@dataclass(frozen=True)
class _OwnerFrame:
    owner_token: str
    depth: int


class ClosedRepairWriterRuntimeCoordinatorV1:
    """Dependency-injected coordinator with no production binding surface."""

    def __init__(
        self,
        *,
        config: WriterRuntimeCoordinatorConfigV1 | None = None,
        lock_backend: SharedLockBackend | None = None,
        lease_store: MaintenanceLeaseStore | None = None,
        clock: Callable[[], float] | None = None,
        nonce_source: Callable[[], str] | None = None,
        lock_namespace: str | None = None,
        writer_inventory: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        self._config = config or WriterRuntimeCoordinatorConfigV1()
        if self._config.enabled and any(
            dependency is None
            for dependency in (lock_backend, lease_store, clock, nonce_source)
        ):
            raise ValueError(
                "enabled coordinator requires injected lock, lease, clock and nonce dependencies"
            )
        self._lock_backend = lock_backend or _DenyLockBackend()
        self._lease_store = lease_store or _DenyLeaseStore()
        self._clock = clock or (lambda: 0.0)
        self._nonce_source = nonce_source or (lambda: "NONCE_SOURCE_NOT_CONFIGURED")
        self._namespace = str(
            lock_namespace or canonical_runtime_lock_namespace_v1()
        ).lower().strip()
        if not _SHA256_RE.fullmatch(self._namespace):
            raise ValueError("lock_namespace must be a lowercase SHA-256")
        expected_inventory = canonical_runtime_writer_inventory_v1()
        supplied_inventory = (
            copy.deepcopy(list(writer_inventory))
            if writer_inventory is not None
            else expected_inventory
        )
        if supplied_inventory != expected_inventory:
            raise ValueError("writer_inventory must match the canonical 19 writers")
        self._inventory = supplied_inventory
        self._writers = {
            item["writer_id"]: copy.deepcopy(item) for item in self._inventory
        }
        self._registered: dict[str, str] = {}
        self._inflight = 0
        self._state_lock = threading.RLock()
        self._owner_frame: ContextVar[_OwnerFrame | None] = ContextVar(
            "closed_repair_writer_owner_frame_v1", default=None
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def lock_namespace(self) -> str:
        return self._namespace

    @property
    def registered_writer_count(self) -> int:
        with self._state_lock:
            return len(self._registered)

    @property
    def inflight_mutations(self) -> int:
        with self._state_lock:
            return self._inflight

    @property
    def all_writers_registered(self) -> bool:
        with self._state_lock:
            return set(self._registered) == set(self._writers)

    def _token(self, token_type: str, payload: Mapping[str, Any]) -> str:
        return _stable_sha256(
            {
                "token_type": token_type,
                "namespace": self._namespace,
                "payload": payload,
            }
        )

    def register_writer(self, writer_id: str) -> dict[str, Any]:
        normalized = str(writer_id or "").strip()
        writer = self._writers.get(normalized)
        if writer is None:
            raise WriterRuntimeCoordinationBlocked("UNKNOWN_WRITER")
        registration_token = self._token(
            "WRITER_REGISTRATION_TOKEN_V1", writer
        )
        with self._state_lock:
            existing = self._registered.get(normalized)
            if existing is not None and existing != registration_token:
                raise WriterRuntimeCoordinationBlocked(
                    "WRITER_REGISTRATION_TOKEN_CONFLICT"
                )
            self._registered[normalized] = registration_token
        return {
            "writer_id": normalized,
            "registration_token": registration_token,
            "registered": True,
            "idempotent": existing == registration_token,
            "runtime_callable_bound": False,
        }

    def register_all_declared_writers(self) -> list[dict[str, Any]]:
        return [self.register_writer(item["writer_id"]) for item in self._inventory]

    def _require_registered(self, writer_id: str) -> None:
        if writer_id not in self._writers:
            raise WriterRuntimeCoordinationBlocked("UNKNOWN_WRITER")
        with self._state_lock:
            if writer_id not in self._registered:
                raise WriterRuntimeCoordinationBlocked("WRITER_NOT_REGISTERED")

    def _read_lease(self) -> dict[str, Any] | None:
        try:
            value = self._lease_store.read(self._namespace)
        except Exception as exc:
            raise WriterRuntimeCoordinationBlocked("LEASE_READ_FAILED") from exc
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise WriterRuntimeCoordinationBlocked("LEASE_RECORD_INVALID")
        lease = copy.deepcopy(dict(value))
        state = str(lease.get("state") or "").upper().strip()
        if state not in _LEASE_STATES:
            raise WriterRuntimeCoordinationBlocked("LEASE_STATE_INVALID")
        if state in _ACTIVE_LEASE_STATES and not _SHA256_RE.fullmatch(
            str(lease.get("maintenance_epoch") or "")
        ):
            raise WriterRuntimeCoordinationBlocked("LEASE_EPOCH_INVALID")
        return lease

    def _require_lease_absent(self) -> None:
        lease = self._read_lease()
        if lease and lease.get("state") in _ACTIVE_LEASE_STATES:
            raise WriterRuntimeCoordinationBlocked("MAINTENANCE_LEASE_ACTIVE")

    def _acquire_shared_lock(self) -> SharedLockHandle:
        try:
            handle = self._lock_backend.acquire(
                self._namespace, self._config.lock_timeout_seconds
            )
        except Exception as exc:
            raise WriterRuntimeCoordinationBlocked("SHARED_LOCK_ACQUIRE_FAILED") from exc
        if handle is None or not callable(getattr(handle, "release", None)):
            raise WriterRuntimeCoordinationBlocked("SHARED_LOCK_TIMEOUT")
        return handle

    @contextmanager
    def mutation(self, writer_id: str) -> Iterator[WriterMutationPermitV1]:
        normalized = str(writer_id or "").strip()
        if not self._config.enabled:
            yield WriterMutationPermitV1(
                writer_id=normalized,
                status="COORDINATOR_DEFAULT_OFF_PASSTHROUGH",
                admitted=True,
                coordinated=False,
                owner_token=None,
                depth=0,
                reentrant=False,
                shared_lock_acquired=False,
            )
            return

        self._require_registered(normalized)
        current = self._owner_frame.get()
        if current is not None:
            nested = _OwnerFrame(current.owner_token, current.depth + 1)
            reset_token = self._owner_frame.set(nested)
            try:
                yield WriterMutationPermitV1(
                    writer_id=normalized,
                    status="COORDINATED_REENTRANT_MUTATION_ADMITTED",
                    admitted=True,
                    coordinated=True,
                    owner_token=current.owner_token,
                    depth=nested.depth,
                    reentrant=True,
                    shared_lock_acquired=True,
                )
            finally:
                self._owner_frame.reset(reset_token)
            return

        self._require_lease_absent()
        with self._state_lock:
            self._inflight += 1
        handle: SharedLockHandle | None = None
        reset_token = None
        try:
            handle = self._acquire_shared_lock()
            self._require_lease_absent()
            owner_token = self._token(
                "WRITER_OWNER_TOKEN_V1",
                {
                    "writer_id": normalized,
                    "nonce": str(self._nonce_source()),
                    "started_at": float(self._clock()),
                },
            )
            reset_token = self._owner_frame.set(_OwnerFrame(owner_token, 1))
            yield WriterMutationPermitV1(
                writer_id=normalized,
                status="COORDINATED_MUTATION_ADMITTED",
                admitted=True,
                coordinated=True,
                owner_token=owner_token,
                depth=1,
                reentrant=False,
                shared_lock_acquired=True,
            )
        finally:
            if reset_token is not None:
                self._owner_frame.reset(reset_token)
            release_error: Exception | None = None
            if handle is not None:
                try:
                    handle.release()
                except Exception as exc:
                    release_error = exc
            with self._state_lock:
                self._inflight = max(0, self._inflight - 1)
            if release_error is not None:
                raise WriterRuntimeCoordinationBlocked(
                    "SHARED_LOCK_RELEASE_FAILED"
                ) from release_error

    def _write_lease(self, lease: Mapping[str, Any]) -> None:
        try:
            self._lease_store.write(self._namespace, copy.deepcopy(dict(lease)))
        except Exception as exc:
            raise WriterRuntimeCoordinationBlocked("LEASE_WRITE_FAILED") from exc

    @contextmanager
    def maintenance_lease(self) -> Iterator[WriterMaintenancePermitV1]:
        if not self._config.enabled:
            raise WriterRuntimeCoordinationBlocked("COORDINATOR_DEFAULT_OFF")
        if self._owner_frame.get() is not None:
            raise WriterRuntimeCoordinationBlocked(
                "MAINTENANCE_FROM_MUTATION_OWNER_FORBIDDEN"
            )
        if not self.all_writers_registered:
            raise WriterRuntimeCoordinationBlocked(
                "ALL_19_WRITERS_MUST_BE_REGISTERED"
            )
        handle = self._acquire_shared_lock()
        epoch = self._token(
            "MAINTENANCE_EPOCH_V1",
            {
                "nonce": str(self._nonce_source()),
                "requested_at": float(self._clock()),
                "registered_writer_count": self.registered_writer_count,
            },
        )
        released = False
        lease_started = False
        try:
            with self._state_lock:
                inflight = self._inflight
            if inflight != 0:
                raise WriterRuntimeCoordinationBlocked(
                    "ZERO_INFLIGHT_MUTATIONS_REQUIRED"
                )
            self._require_lease_absent()
            common = {
                "maintenance_epoch": epoch,
                "registered_writer_count": self.registered_writer_count,
                "writer_inventory_sha256": _stable_sha256(self._inventory),
                "updated_at": float(self._clock()),
            }
            self._write_lease({**common, "state": "REQUESTED"})
            lease_started = True
            self._write_lease({**common, "state": "DRAINING"})
            self._write_lease({**common, "state": "QUIESCED"})
            yield WriterMaintenancePermitV1(
                maintenance_epoch=epoch,
                state="QUIESCED",
                lock_namespace_sha256=self._namespace,
                registered_writer_count=self.registered_writer_count,
                inflight_mutations=0,
                shared_lock_acquired=True,
            )
        finally:
            lease_release_error: Exception | None = None
            try:
                if lease_started:
                    current = self._read_lease()
                    if current and current.get("maintenance_epoch") == epoch:
                        self._write_lease(
                            {
                                **current,
                                "state": "RELEASED",
                                "updated_at": float(self._clock()),
                            }
                        )
                        released = True
            except Exception as exc:
                lease_release_error = exc
            finally:
                try:
                    handle.release()
                except Exception as exc:
                    raise WriterRuntimeCoordinationBlocked(
                        "SHARED_LOCK_RELEASE_FAILED"
                    ) from exc
            if lease_release_error is not None:
                raise WriterRuntimeCoordinationBlocked(
                    "MAINTENANCE_LEASE_RELEASE_FAILED"
                ) from lease_release_error
            if lease_started and not released:
                raise WriterRuntimeCoordinationBlocked(
                    "MAINTENANCE_LEASE_RELEASE_NOT_CONFIRMED"
                )

    def snapshot(self) -> dict[str, Any]:
        lease = self._read_lease() if self._config.enabled else None
        return {
            "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION,
            "enabled": self._config.enabled,
            "default_off": not self._config.enabled,
            "lock_namespace_sha256": self._namespace,
            "writer_count": len(self._inventory),
            "registered_writer_count": self.registered_writer_count,
            "all_writers_registered": self.all_writers_registered,
            "inflight_mutations": self.inflight_mutations,
            "maintenance_lease_state": lease.get("state") if lease else None,
            "runtime_integrated": False,
            "real_registry_accessed": False,
            "broker_called": False,
            "no_order_sent": True,
        }


def _stale_lease_recovery_base_result_v1() -> dict[str, Any]:
    return {
        "ok": False,
        "status": "STALE_MAINTENANCE_LEASE_RECOVERY_V1_BLOCKED",
        "reason": None,
        "version": TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION,
        "dormant": True,
        "default_off": True,
        "offline_only": True,
        "synthetic_only": True,
        "recovery_performed": False,
        "idempotent": False,
        "lease_write_executed": False,
        "registry_write": False,
        "runtime_integrated": False,
        "real_registry_accessed": False,
        "network_accessed": False,
        "broker_called": False,
        "no_order_sent": True,
    }


def recover_stale_maintenance_lease_v1(
    *,
    enabled: bool = False,
    scope_attestation: str | None = None,
    lock_backend: SharedLockBackend | None = None,
    lease_store: MaintenanceLeaseStore | None = None,
    clock: Callable[[], float] | None = None,
    current_process_identity: str | None = None,
    owner_liveness: Callable[[str], bool | None] | None = None,
    stale_after_seconds: float = 30.0,
    lock_timeout_seconds: float = 1.0,
    lock_namespace: str | None = None,
) -> dict[str, Any]:
    """Recover only an attested synthetic lease whose owner is proven dead."""

    base = _stale_lease_recovery_base_result_v1()
    if not enabled:
        base["reason"] = "STALE_LEASE_RECOVERY_DEFAULT_OFF"
        return base
    if scope_attestation != SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1:
        base["reason"] = "SYNTHETIC_STALE_LEASE_RECOVERY_SCOPE_REQUIRED"
        return base
    if any(
        dependency is None
        for dependency in (lock_backend, lease_store, clock, owner_liveness)
    ):
        base["reason"] = "STALE_LEASE_RECOVERY_DEPENDENCIES_REQUIRED"
        return base
    identity = str(current_process_identity or "").strip()
    if not identity or len(identity) > 256:
        base["reason"] = "CURRENT_PROCESS_IDENTITY_INVALID"
        return base
    try:
        stale_after = float(stale_after_seconds)
        lock_timeout = float(lock_timeout_seconds)
    except (TypeError, ValueError, OverflowError):
        base["reason"] = "STALE_LEASE_RECOVERY_BUDGET_INVALID"
        return base
    if (
        not math.isfinite(stale_after)
        or not math.isfinite(lock_timeout)
        or stale_after <= 0
        or lock_timeout <= 0
    ):
        base["reason"] = "STALE_LEASE_RECOVERY_BUDGET_INVALID"
        return base
    namespace = str(
        lock_namespace or canonical_runtime_lock_namespace_v1()
    ).lower().strip()
    if (
        not _SHA256_RE.fullmatch(namespace)
        or not hmac.compare_digest(namespace, canonical_runtime_lock_namespace_v1())
    ):
        base["reason"] = "STALE_LEASE_RECOVERY_NAMESPACE_INVALID"
        return base
    try:
        now = float(clock())
    except Exception:
        base["reason"] = "STALE_LEASE_RECOVERY_CLOCK_FAILED"
        return base
    if not math.isfinite(now):
        base["reason"] = "STALE_LEASE_RECOVERY_CLOCK_INVALID"
        return base
    current_identity_sha256 = _stable_sha256({"process_identity": identity})

    try:
        handle = lock_backend.acquire(namespace, lock_timeout)
    except Exception:
        base["reason"] = "STALE_LEASE_RECOVERY_LOCK_ACQUIRE_FAILED"
        return base
    if handle is None or not callable(getattr(handle, "release", None)):
        base["reason"] = "STALE_LEASE_RECOVERY_LOCK_TIMEOUT"
        return base

    outcome = base
    try:
        try:
            raw_lease = lease_store.read(namespace)
        except Exception:
            raise WriterRuntimeCoordinationBlocked(
                "STALE_LEASE_RECOVERY_READ_FAILED"
            ) from None
        if raw_lease is None:
            outcome = {
                **base,
                "ok": True,
                "status": "STALE_MAINTENANCE_LEASE_RECOVERY_V1_NO_LEASE",
                "reason": None,
                "idempotent": True,
            }
        elif not isinstance(raw_lease, Mapping):
            raise WriterRuntimeCoordinationBlocked(
                "STALE_LEASE_RECOVERY_RECORD_INVALID"
            )
        else:
            lease = copy.deepcopy(dict(raw_lease))
            state = str(lease.get("state") or "").upper().strip()
            epoch = str(lease.get("maintenance_epoch") or "").lower().strip()
            if state == "RELEASED":
                outcome = {
                    **base,
                    "ok": True,
                    "status": "STALE_MAINTENANCE_LEASE_RECOVERY_V1_ALREADY_RELEASED",
                    "reason": None,
                    "idempotent": True,
                    "maintenance_epoch_sha256": (
                        _stable_sha256({"maintenance_epoch": epoch})
                        if _SHA256_RE.fullmatch(epoch)
                        else None
                    ),
                }
            elif state not in _ACTIVE_LEASE_STATES:
                raise WriterRuntimeCoordinationBlocked(
                    "STALE_LEASE_RECOVERY_STATE_INVALID"
                )
            else:
                owner_sha = str(
                    lease.get("owner_identity_sha256") or ""
                ).lower().strip()
                inventory_sha = str(
                    lease.get("writer_inventory_sha256") or ""
                ).lower().strip()
                expected_inventory_sha = _stable_sha256(
                    canonical_runtime_writer_inventory_v1()
                )
                if (
                    lease.get("recovery_scope_attestation")
                    != SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1
                    or not _SHA256_RE.fullmatch(epoch)
                    or not _SHA256_RE.fullmatch(owner_sha)
                    or lease.get("registered_writer_count") != 19
                    or not _SHA256_RE.fullmatch(inventory_sha)
                    or not hmac.compare_digest(
                        inventory_sha, expected_inventory_sha
                    )
                ):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_ATTESTATION_INVALID"
                    )
                if hmac.compare_digest(owner_sha, current_identity_sha256):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_SELF_OWNER_FORBIDDEN"
                    )
                updated_at = lease.get("updated_at")
                if isinstance(updated_at, bool):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_TIMESTAMP_INVALID"
                    )
                try:
                    updated_at_value = float(updated_at)
                except (TypeError, ValueError, OverflowError):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_TIMESTAMP_INVALID"
                    ) from None
                if not math.isfinite(updated_at_value):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_TIMESTAMP_INVALID"
                    )
                age_seconds = now - updated_at_value
                if age_seconds < 0:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_CLOCK_REGRESSION"
                    )
                if age_seconds < stale_after:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_NOT_STALE"
                    )
                try:
                    owner_alive = owner_liveness(owner_sha)
                except Exception:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_OWNER_LIVENESS_UNKNOWN"
                    ) from None
                if owner_alive is True:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_OWNER_STILL_ALIVE"
                    )
                if owner_alive is not False:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_OWNER_LIVENESS_UNKNOWN"
                    )
                try:
                    current = lease_store.read(namespace)
                except Exception:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_READ_FAILED"
                    ) from None
                if not isinstance(current, Mapping) or not hmac.compare_digest(
                    _stable_sha256(dict(current)), _stable_sha256(lease)
                ):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_CHANGED_DURING_RECOVERY"
                    )
                recovered = {
                    **lease,
                    "state": "RELEASED",
                    "updated_at": now,
                    "recovered_at": now,
                    "recovered_from_state": state,
                    "recovery_reason": "STALE_OWNER_CONFIRMED_DEAD",
                    "recovered_by_identity_sha256": current_identity_sha256,
                }
                try:
                    lease_store.write(namespace, recovered)
                    verified = lease_store.read(namespace)
                except Exception:
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_WRITE_FAILED"
                    ) from None
                if (
                    not isinstance(verified, Mapping)
                    or verified.get("state") != "RELEASED"
                    or verified.get("maintenance_epoch") != epoch
                    or verified.get("recovery_reason")
                    != "STALE_OWNER_CONFIRMED_DEAD"
                    or verified.get("recovered_by_identity_sha256")
                    != current_identity_sha256
                ):
                    raise WriterRuntimeCoordinationBlocked(
                        "STALE_LEASE_RECOVERY_VERIFY_FAILED"
                    )
                outcome = {
                    **base,
                    "ok": True,
                    "status": "STALE_MAINTENANCE_LEASE_RECOVERY_V1_RELEASED_SYNTHETIC_ONLY",
                    "reason": None,
                    "default_off": False,
                    "recovery_performed": True,
                    "lease_write_executed": True,
                    "previous_state": state,
                    "age_seconds": age_seconds,
                    "maintenance_epoch_sha256": _stable_sha256(
                        {"maintenance_epoch": epoch}
                    ),
                    "owner_identity_sha256": owner_sha,
                    "recovered_by_identity_sha256": current_identity_sha256,
                }
    except WriterRuntimeCoordinationBlocked as exc:
        outcome = {**base, "reason": exc.reason}
    except Exception:
        outcome = {**base, "reason": "STALE_LEASE_RECOVERY_FAILED_CLOSED"}

    try:
        handle.release()
    except Exception:
        return {
            **base,
            "reason": "STALE_LEASE_RECOVERY_LOCK_RELEASE_FAILED",
        }
    return outcome


def build_closed_repair_writer_runtime_coordinator_v1(
    *,
    config: WriterRuntimeCoordinatorConfigV1 | None = None,
    lock_backend: SharedLockBackend | None = None,
    lease_store: MaintenanceLeaseStore | None = None,
    clock: Callable[[], float] | None = None,
    nonce_source: Callable[[], str] | None = None,
) -> ClosedRepairWriterRuntimeCoordinatorV1:
    """Construct an isolated coordinator; omitted config is always disabled."""

    return ClosedRepairWriterRuntimeCoordinatorV1(
        config=config,
        lock_backend=lock_backend,
        lease_store=lease_store,
        clock=clock,
        nonce_source=nonce_source,
    )


def production_coordinator_storage_root_binding_sha256_v1(
    storage_root: os.PathLike[str] | str,
) -> str:
    """Bind an explicitly supplied coordinator storage root without exposing it."""

    normalized = os.path.normcase(os.path.abspath(os.fspath(storage_root)))
    return _stable_sha256(
        {
            "binding_version": "C3_PRODUCTION_COORDINATOR_STORAGE_ROOT_BINDING_V1",
            "storage_root": normalized,
            "lock_namespace_sha256": canonical_runtime_lock_namespace_v1(),
            "lock_backend_version": runtime_storage.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_STORAGE_ADAPTERS_V1_VERSION,
            "lease_store_version": runtime_storage.TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_STORAGE_ADAPTERS_V1_VERSION,
        }
    )


def build_production_closed_repair_writer_runtime_coordinator_v1(
    *,
    config: ProductionWriterRuntimeCoordinatorBindingConfigV1 | None = None,
    lock_backend: runtime_storage.CrossPlatformInterprocessFileLockBackendV1
    | None = None,
    lease_store: runtime_storage.DurableJsonMaintenanceLeaseStoreV1
    | None = None,
    clock: Callable[[], float] | None = None,
    nonce_source: Callable[[], str] | None = None,
) -> ClosedRepairWriterRuntimeCoordinatorV1:
    """Build a production-shaped coordinator solely from explicit dependencies."""

    binding = config or ProductionWriterRuntimeCoordinatorBindingConfigV1()
    if not binding.enabled:
        return ClosedRepairWriterRuntimeCoordinatorV1()
    if (
        binding.scope_attestation
        != PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1
    ):
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_SCOPE_ATTESTATION_REQUIRED"
        )
    supplied_root_sha = str(
        binding.storage_root_binding_sha256 or ""
    ).lower().strip()
    if not _SHA256_RE.fullmatch(supplied_root_sha):
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_STORAGE_ROOT_BINDING_INVALID"
        )
    if type(lock_backend) is not runtime_storage.CrossPlatformInterprocessFileLockBackendV1:
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_LOCK_BACKEND_INVALID"
        )
    if type(lease_store) is not runtime_storage.DurableJsonMaintenanceLeaseStoreV1:
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_LEASE_STORE_INVALID"
        )
    if lock_backend.enabled is not True or lease_store.enabled is not True:
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_STORAGE_DEPENDENCIES_DEFAULT_OFF"
        )
    if lock_backend.storage_root != lease_store.storage_root:
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_STORAGE_ROOT_MISMATCH"
        )
    expected_root_sha = production_coordinator_storage_root_binding_sha256_v1(
        lock_backend.storage_root
    )
    if not hmac.compare_digest(supplied_root_sha, expected_root_sha):
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_STORAGE_ROOT_BINDING_MISMATCH"
        )
    if not callable(clock) or not callable(nonce_source):
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_CLOCK_AND_NONCE_REQUIRED"
        )
    coordinator = ClosedRepairWriterRuntimeCoordinatorV1(
        config=WriterRuntimeCoordinatorConfigV1(
            enabled=True,
            lock_timeout_seconds=binding.lock_timeout_seconds,
        ),
        lock_backend=lock_backend,
        lease_store=lease_store,
        clock=clock,
        nonce_source=nonce_source,
        lock_namespace=canonical_runtime_lock_namespace_v1(),
        writer_inventory=canonical_runtime_writer_inventory_v1(),
    )
    registrations = coordinator.register_all_declared_writers()
    if len(registrations) != 19 or coordinator.all_writers_registered is not True:
        raise WriterRuntimeCoordinationBlocked(
            "PRODUCTION_COORDINATOR_WRITER_REGISTRATION_FAILED"
        )
    return coordinator


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_COORDINATOR_V1_VERSION",
    "SYNTHETIC_STALE_LEASE_RECOVERY_ATTESTATION_V1",
    "PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1",
    "ClosedRepairWriterRuntimeCoordinatorV1",
    "MaintenanceLeaseStore",
    "SharedLockBackend",
    "SharedLockHandle",
    "WriterMaintenancePermitV1",
    "WriterMutationPermitV1",
    "WriterRuntimeCoordinationBlocked",
    "WriterRuntimeCoordinatorConfigV1",
    "ProductionWriterRuntimeCoordinatorBindingConfigV1",
    "build_closed_repair_writer_runtime_coordinator_v1",
    "build_production_closed_repair_writer_runtime_coordinator_v1",
    "canonical_runtime_lock_namespace_v1",
    "canonical_runtime_writer_inventory_v1",
    "recover_stale_maintenance_lease_v1",
    "production_coordinator_storage_root_binding_sha256_v1",
]
