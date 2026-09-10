"""In-memory reference executor for the dormant production lease contract.

Only exact in-memory lock doubles are accepted.  No production store, file,
network, broker, runtime, or trading surface is imported or called.
"""

from __future__ import annotations

import copy
import hmac
import re
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2 as hash_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2 as lease_contract_v2
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2 as identity_v2


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_REFERENCE_EXECUTOR_OFFLINE_V2_VERSION = (
    "2026-09-09-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-RUNTIME-"
    "PRODUCTION-STARTUP-RECOVERY-PRODUCTION-MULTISTORE-OBSERVATION-"
    "LEASE-REFERENCE-EXECUTOR-OFFLINE-V2"
)
OFFLINE_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_ATTESTATION_V2 = (
    "C3_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_IN_MEMORY_ONLY_V2"
)
SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_VERSION_V2 = (
    "C3_SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_V2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_AUTHORITY_KEYS = frozenset(
    {
        "authority_version",
        "lease_binding_sha256",
        "writer_coordination_binding_sha256",
        "maintenance_lease_contract_sha256",
        "authenticated_authority_contract_sha256",
        "maintenance_epoch",
        "writer_coordination_state",
        "registered_writer_count",
        "inflight_mutations",
        "maintenance_lease_verified",
        "writer_coordination_verified",
        "synthetic_only",
        "production_signature_verified",
        "production_authority",
        "issued_at_epoch",
        "expires_at_epoch",
        "authority_sha256",
    }
)


def _valid_sha(value: Any) -> bool:
    return bool(_SHA256_RE.fullmatch(str(value or "").lower().strip()))


def _hash_without(value: Mapping[str, Any], key: str) -> str:
    return hash_v2.stable_sha256_v2(
        {name: item for name, item in value.items() if name != key}
    )


def synthetic_production_observation_authority_sha256_v2(
    value: Mapping[str, Any],
) -> str:
    if not isinstance(value, Mapping):
        raise TypeError("synthetic observation authority must be a mapping")
    return _hash_without(value, "authority_sha256")


@dataclass(frozen=True, repr=False)
class ProtectedSyntheticProductionObservationAuthorityV2:
    lease_binding_sha256: str = field(repr=False)
    maintenance_epoch: str = field(repr=False)
    authority: Mapping[str, Any] = field(repr=False)
    authority_sha256: str = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedSyntheticProductionObservationAuthorityV2(<protected>)"


def synthetic_production_observation_authority_valid_v2(
    value: Any, *, now_epoch: int
) -> bool:
    if (
        type(value) is not ProtectedSyntheticProductionObservationAuthorityV2
        or type(now_epoch) is not int
    ):
        return False
    try:
        authority = copy.deepcopy(dict(value.authority))
        supplied = str(authority.get("authority_sha256") or "")
        return bool(
            set(authority) == _AUTHORITY_KEYS
            and authority["authority_version"]
            == SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_VERSION_V2
            and all(
                _valid_sha(authority[key])
                for key in (
                    "lease_binding_sha256",
                    "writer_coordination_binding_sha256",
                    "maintenance_lease_contract_sha256",
                    "authenticated_authority_contract_sha256",
                    "maintenance_epoch",
                    "authority_sha256",
                )
            )
            and authority["writer_coordination_state"] == "QUIESCED"
            and authority["registered_writer_count"] == 19
            and authority["inflight_mutations"] == 0
            and authority["maintenance_lease_verified"] is True
            and authority["writer_coordination_verified"] is True
            and authority["synthetic_only"] is True
            and authority["production_signature_verified"] is False
            and authority["production_authority"] is False
            and type(authority["issued_at_epoch"]) is int
            and type(authority["expires_at_epoch"]) is int
            and authority["issued_at_epoch"] <= now_epoch
            < authority["expires_at_epoch"]
            and 1 <= authority["expires_at_epoch"] - now_epoch <= 300
            and value.lease_binding_sha256
            == authority["lease_binding_sha256"]
            and value.maintenance_epoch == authority["maintenance_epoch"]
            and value.authority_sha256 == supplied
            and hmac.compare_digest(
                supplied,
                synthetic_production_observation_authority_sha256_v2(authority),
            )
        )
    except Exception:
        return False


def build_synthetic_production_observation_authority_offline_v2(
    binding: Any,
    *,
    maintenance_epoch: str,
    issued_at_epoch: int,
    expires_at_epoch: int,
) -> ProtectedSyntheticProductionObservationAuthorityV2:
    if not (
        lease_contract_v2.protected_production_multistore_observation_lease_binding_valid_v2(
            binding
        )
        and _valid_sha(maintenance_epoch)
        and type(issued_at_epoch) is int
        and type(expires_at_epoch) is int
        and issued_at_epoch < expires_at_epoch
        and expires_at_epoch - issued_at_epoch <= 300
    ):
        raise ValueError("SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_INPUT_INVALID")
    lease_binding = copy.deepcopy(dict(binding.binding))
    authority = {
        "authority_version": SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_VERSION_V2,
        "lease_binding_sha256": binding.binding_sha256,
        "writer_coordination_binding_sha256": lease_binding[
            "writer_coordination_binding_sha256"
        ],
        "maintenance_lease_contract_sha256": lease_binding[
            "maintenance_lease_contract_sha256"
        ],
        "authenticated_authority_contract_sha256": lease_binding[
            "authenticated_authority_contract_sha256"
        ],
        "maintenance_epoch": maintenance_epoch,
        "writer_coordination_state": "QUIESCED",
        "registered_writer_count": 19,
        "inflight_mutations": 0,
        "maintenance_lease_verified": True,
        "writer_coordination_verified": True,
        "synthetic_only": True,
        "production_signature_verified": False,
        "production_authority": False,
        "issued_at_epoch": issued_at_epoch,
        "expires_at_epoch": expires_at_epoch,
    }
    authority["authority_sha256"] = (
        synthetic_production_observation_authority_sha256_v2(authority)
    )
    protected = ProtectedSyntheticProductionObservationAuthorityV2(
        lease_binding_sha256=authority["lease_binding_sha256"],
        maintenance_epoch=authority["maintenance_epoch"],
        authority=copy.deepcopy(authority),
        authority_sha256=authority["authority_sha256"],
    )
    if not synthetic_production_observation_authority_valid_v2(
        protected, now_epoch=issued_at_epoch
    ):
        raise ValueError("SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_INTERNAL_INVALID")
    return protected


class ReferenceProductionLeaseExecutorBlockedV2(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InMemoryProductionLockHandleV2:
    def __init__(self, owner: Any, port_role: str) -> None:
        self._owner = owner
        self._port_role = port_role
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        self._owner._release_exact(self)

    def __repr__(self) -> str:
        return "InMemoryProductionLockHandleV2(<protected>)"


class InMemoryProductionStoreLockPortDoubleV2:
    """Exact in-memory double; it has no store read or write operation."""

    def __init__(
        self,
        projection: Any,
        *,
        fail_acquire: bool = False,
        event_sink: list[tuple[str, str]] | None = None,
    ) -> None:
        if not lease_contract_v2.production_store_lock_port_projection_valid_v2(
            projection
        ):
            raise ValueError("IN_MEMORY_PRODUCTION_LOCK_PORT_PROJECTION_INVALID")
        self._projection = projection
        self._fail_acquire = bool(fail_acquire)
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._active: InMemoryProductionLockHandleV2 | None = None
        self._events: list[tuple[str, str]] = []
        self._event_sink = event_sink

    @property
    def projection_sha256(self) -> str:
        return self._projection.projection_sha256

    @property
    def port_role(self) -> str:
        return self._projection.port_role

    def acquire_exclusive(
        self, lock_namespace_sha256: str, timeout_seconds: float
    ) -> InMemoryProductionLockHandleV2 | None:
        projection = dict(self._projection.projection)
        if not (
            lock_namespace_sha256 == projection["lock_namespace_sha256"]
            and type(timeout_seconds) in (int, float)
            and 0 < float(timeout_seconds) <= 1
        ):
            raise ReferenceProductionLeaseExecutorBlockedV2(
                "IN_MEMORY_PRODUCTION_LOCK_ACQUIRE_ARGUMENT_INVALID"
            )
        if self._fail_acquire or not self._lock.acquire(blocking=False):
            return None
        handle = InMemoryProductionLockHandleV2(self, self.port_role)
        with self._state_lock:
            self._active = handle
            self._events.append(("ACQUIRE", self.port_role))
            if self._event_sink is not None:
                self._event_sink.append(("ACQUIRE", self.port_role))
        return handle

    def _release_exact(self, handle: Any) -> None:
        with self._state_lock:
            if handle is not self._active or handle.released:
                raise ReferenceProductionLeaseExecutorBlockedV2(
                    "IN_MEMORY_PRODUCTION_LOCK_RELEASE_INVALID"
                )
            handle._released = True
            self._active = None
            self._events.append(("RELEASE", self.port_role))
            if self._event_sink is not None:
                self._event_sink.append(("RELEASE", self.port_role))
        self._lock.release()

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            return {
                "port_role": self.port_role,
                "active": self._active is not None,
                "event_count": len(self._events),
                "events": [list(item) for item in self._events],
                "in_memory_only": True,
                "store_called": False,
                "filesystem_accessed": False,
                "network_accessed": False,
                "production_authority": False,
                "runtime_integrated": False,
                "live_allowed": False,
            }


@dataclass(frozen=True, repr=False)
class ProtectedReferenceProductionObservationLeaseTokenV2:
    token_sha256: str = field(repr=False)
    binding_sha256: str = field(repr=False)
    authority_sha256: str = field(repr=False)
    lock_order_sha256: str = field(repr=False)
    maintenance_epoch: str = field(repr=False)
    issued_at_epoch: int = field(repr=False)
    expires_at_epoch: int = field(repr=False)

    def __repr__(self) -> str:
        return "ProtectedReferenceProductionObservationLeaseTokenV2(<protected>)"


@dataclass(frozen=True)
class ReferenceProductionMultistoreObservationLeaseExecutorConfigV2:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    expected_binding_sha256: str | None = field(default=None, repr=False)
    expected_authority_sha256: str | None = field(default=None, repr=False)
    expected_authority_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_transaction_lock_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    expected_resolved_lock_port_object_identity_sha256: str | None = field(
        default=None, repr=False
    )
    max_ttl_seconds: int = 300
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_ttl_seconds <= 300:
            raise ValueError("max_ttl_seconds must be between 1 and 300")
        if not 0 < self.lock_timeout_seconds <= 1:
            raise ValueError("lock_timeout_seconds must be between 0 and 1")


class ReferenceProductionMultistoreObservationLeaseExecutorV2:
    def __init__(
        self,
        config: ReferenceProductionMultistoreObservationLeaseExecutorConfigV2
        | None = None,
        *,
        clock: Callable[[], int] | None = None,
        nonce_source: Callable[[], str] | None = None,
    ) -> None:
        self._config = (
            config
            or ReferenceProductionMultistoreObservationLeaseExecutorConfigV2()
        )
        self._clock = clock or (lambda: 0)
        self._nonce_source = nonce_source or (lambda: "")
        self._state_lock = threading.Lock()
        self._active_token: ProtectedReferenceProductionObservationLeaseTokenV2 | None = None
        self._active_ports: tuple[InMemoryProductionStoreLockPortDoubleV2, ...] = ()
        self._active_handles: tuple[InMemoryProductionLockHandleV2, ...] = ()

    def _config_reason(self) -> str | None:
        if self._config.enabled is not True:
            return "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_DEFAULT_OFF"
        if (
            self._config.scope_attestation
            != OFFLINE_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_ATTESTATION_V2
        ):
            return "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_INVALID"
        if not (
            _valid_sha(self._config.expected_binding_sha256)
            and _valid_sha(self._config.expected_authority_sha256)
            and _valid_sha(
                self._config.expected_authority_object_identity_sha256
            )
            and _valid_sha(
                self._config.expected_transaction_lock_port_object_identity_sha256
            )
            and _valid_sha(
                self._config.expected_resolved_lock_port_object_identity_sha256
            )
        ):
            return "PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_PINS_INVALID"
        return None

    @contextmanager
    def hold_offline(
        self,
        *,
        binding: Any,
        authority: Any,
        transaction_store_lock_port: Any,
        resolved_authority_store_lock_port: Any,
        expires_at_epoch: int,
    ) -> Iterator[ProtectedReferenceProductionObservationLeaseTokenV2]:
        reason = self._config_reason()
        if reason is not None:
            raise ReferenceProductionLeaseExecutorBlockedV2(reason)
        try:
            now_epoch = self._clock()
            nonce = str(self._nonce_source())
        except Exception as exc:
            raise ReferenceProductionLeaseExecutorBlockedV2(
                "PRODUCTION_MULTISTORE_LEASE_REFERENCE_SOURCE_FAILED"
            ) from exc
        if not (
            type(now_epoch) is int
            and type(expires_at_epoch) is int
            and now_epoch < expires_at_epoch
            and expires_at_epoch - now_epoch <= self._config.max_ttl_seconds
            and nonce
            and lease_contract_v2.protected_production_multistore_observation_lease_binding_valid_v2(
                binding
            )
            and synthetic_production_observation_authority_valid_v2(
                authority, now_epoch=now_epoch
            )
            and binding.binding_sha256 == self._config.expected_binding_sha256
            and authority.authority_sha256
            == self._config.expected_authority_sha256
            and authority.lease_binding_sha256 == binding.binding_sha256
            and expires_at_epoch <= authority.authority["expires_at_epoch"]
            and type(transaction_store_lock_port)
            is InMemoryProductionStoreLockPortDoubleV2
            and type(resolved_authority_store_lock_port)
            is InMemoryProductionStoreLockPortDoubleV2
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                authority
            )
            == self._config.expected_authority_object_identity_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                transaction_store_lock_port
            )
            == self._config.expected_transaction_lock_port_object_identity_sha256
            and identity_v2.startup_recovery_evidence_source_object_identity_sha256_v2(
                resolved_authority_store_lock_port
            )
            == self._config.expected_resolved_lock_port_object_identity_sha256
        ):
            raise ReferenceProductionLeaseExecutorBlockedV2(
                "PRODUCTION_MULTISTORE_LEASE_REFERENCE_INPUT_INVALID"
            )
        lease_binding = dict(binding.binding)
        authority_payload = dict(authority.authority)
        if not (
            transaction_store_lock_port.port_role
            == lease_contract_v2.TRANSACTION_STORE_ROLE_V2
            and resolved_authority_store_lock_port.port_role
            == lease_contract_v2.RESOLVED_AUTHORITY_STORE_ROLE_V2
            and transaction_store_lock_port.projection_sha256
            == lease_binding["transaction_store_projection_sha256"]
            and resolved_authority_store_lock_port.projection_sha256
            == lease_binding["resolved_authority_store_projection_sha256"]
            and authority_payload["writer_coordination_binding_sha256"]
            == lease_binding["writer_coordination_binding_sha256"]
            and authority_payload["maintenance_lease_contract_sha256"]
            == lease_binding["maintenance_lease_contract_sha256"]
            and authority_payload["authenticated_authority_contract_sha256"]
            == lease_binding["authenticated_authority_contract_sha256"]
        ):
            raise ReferenceProductionLeaseExecutorBlockedV2(
                "PRODUCTION_MULTISTORE_LEASE_REFERENCE_PORT_SUBSTITUTION"
            )
        with self._state_lock:
            if self._active_token is not None:
                raise ReferenceProductionLeaseExecutorBlockedV2(
                    "PRODUCTION_MULTISTORE_LEASE_REFERENCE_ALREADY_ACTIVE"
                )
        ports = (
            transaction_store_lock_port,
            resolved_authority_store_lock_port,
        )
        namespaces = (
            lease_binding["transaction_store_lock_namespace_sha256"],
            lease_binding["resolved_authority_store_lock_namespace_sha256"],
        )
        handles: list[InMemoryProductionLockHandleV2] = []
        token: ProtectedReferenceProductionObservationLeaseTokenV2 | None = None
        try:
            for port, namespace in zip(ports, namespaces, strict=True):
                handle = port.acquire_exclusive(
                    namespace, self._config.lock_timeout_seconds
                )
                if handle is None:
                    raise ReferenceProductionLeaseExecutorBlockedV2(
                        "PRODUCTION_MULTISTORE_LEASE_REFERENCE_LOCK_CONTENTION"
                    )
                handles.append(handle)
            token = ProtectedReferenceProductionObservationLeaseTokenV2(
                token_sha256=hash_v2.stable_sha256_v2(
                    {
                        "kind": "C3_REFERENCE_PRODUCTION_OBSERVATION_LEASE_TOKEN_V2",
                        "binding_sha256": binding.binding_sha256,
                        "authority_sha256": authority.authority_sha256,
                        "maintenance_epoch": authority.maintenance_epoch,
                        "lock_order_sha256": lease_binding["lock_order_sha256"],
                        "issued_at_epoch": now_epoch,
                        "expires_at_epoch": expires_at_epoch,
                        "nonce": nonce,
                    }
                ),
                binding_sha256=binding.binding_sha256,
                authority_sha256=authority.authority_sha256,
                lock_order_sha256=lease_binding["lock_order_sha256"],
                maintenance_epoch=authority.maintenance_epoch,
                issued_at_epoch=now_epoch,
                expires_at_epoch=expires_at_epoch,
            )
            with self._state_lock:
                self._active_token = token
                self._active_ports = ports
                self._active_handles = tuple(handles)
            yield token
        finally:
            with self._state_lock:
                if self._active_token is token:
                    self._active_token = None
                    self._active_ports = ()
                    self._active_handles = ()
            for handle in reversed(handles):
                if not handle.released:
                    handle.release()

    def validate_live(
        self,
        token: Any,
        *,
        transaction_store_lock_port: Any,
        resolved_authority_store_lock_port: Any,
        now_epoch: int,
    ) -> bool:
        if (
            type(token)
            is not ProtectedReferenceProductionObservationLeaseTokenV2
            or type(now_epoch) is not int
        ):
            return False
        with self._state_lock:
            return bool(
                token is self._active_token
                and self._active_ports
                == (
                    transaction_store_lock_port,
                    resolved_authority_store_lock_port,
                )
                and len(self._active_handles) == 2
                and all(not handle.released for handle in self._active_handles)
                and token.issued_at_epoch <= now_epoch < token.expires_at_epoch
                and token.binding_sha256 == self._config.expected_binding_sha256
                and token.authority_sha256
                == self._config.expected_authority_sha256
                and _valid_sha(token.token_sha256)
                and _valid_sha(token.lock_order_sha256)
                and _valid_sha(token.maintenance_epoch)
            )

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
                "in_memory_only": True,
                "production_lock_ports_bound": False,
                "store_called": False,
                "filesystem_accessed": False,
                "network_accessed": False,
                "production_authority": False,
                "production_ready": False,
                "runtime_integrated": False,
                "activation_allowed": False,
                "live_allowed": False,
            }


__all__ = [
    "InMemoryProductionLockHandleV2",
    "InMemoryProductionStoreLockPortDoubleV2",
    "OFFLINE_PRODUCTION_MULTISTORE_LEASE_REFERENCE_EXECUTOR_SCOPE_ATTESTATION_V2",
    "ProtectedReferenceProductionObservationLeaseTokenV2",
    "ProtectedSyntheticProductionObservationAuthorityV2",
    "ReferenceProductionLeaseExecutorBlockedV2",
    "ReferenceProductionMultistoreObservationLeaseExecutorConfigV2",
    "ReferenceProductionMultistoreObservationLeaseExecutorV2",
    "SYNTHETIC_PRODUCTION_OBSERVATION_AUTHORITY_VERSION_V2",
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_RUNTIME_PRODUCTION_STARTUP_RECOVERY_PRODUCTION_MULTISTORE_OBSERVATION_LEASE_REFERENCE_EXECUTOR_OFFLINE_V2_VERSION",
    "build_synthetic_production_observation_authority_offline_v2",
    "synthetic_production_observation_authority_sha256_v2",
    "synthetic_production_observation_authority_valid_v2",
]
