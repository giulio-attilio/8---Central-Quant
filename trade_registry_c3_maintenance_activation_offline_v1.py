"""Executable offline composition of C3 maintenance with physical lease ports.

Nothing installs this composition in the application. All operations and the
authorization verifier are trusted, injected ports; tests provide synthetic
operations and temporary storage. A request's hashes are NOT authentication.
The production verifier must authenticate and durably consume a request bound
to AuthorizationBindingV1 before this composition can be integrated.

Deadlines are cooperative: each operation receives the deadline and must bound
its own I/O. This module checks it at every boundary, but cannot interrupt a
blocked callback. Completion never grants runtime or trading readiness.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1 as coordinator_module
from trade_registry_closed_identity_conflict_repair_prebootstrap_maintenance_only_coordinator_entrypoint_contract_v1 import _SAFE_CONTROL_VECTOR


OFFLINE_MAINTENANCE_SCOPE = "C3_COORDINATED_MAINTENANCE_OFFLINE_V1"


class MaintenanceActivationBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class MaintenanceActivationConfigV1:
    enabled: bool = False
    scope_attestation: str | None = field(default=None, repr=False)
    max_duration_seconds: float = 30.0
    lock_timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        for value in (self.max_duration_seconds, self.lock_timeout_seconds):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("finite numeric maintenance deadlines required")
        if not 0 < self.lock_timeout_seconds <= self.max_duration_seconds <= 300:
            raise ValueError("maintenance deadlines must satisfy 0 < lock <= total <= 300")
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be a boolean")


@dataclass(frozen=True)
class AuthorizationBindingV1:
    scope: str
    storage_root_binding_sha256: str = field(repr=False)
    nonce: str = field(repr=False)
    deadline: float = field(repr=False)
    writer_count: int = 19
    maintenance_only: bool = True


class OfflineMaintenanceActivationV1:
    """One-shot maintenance composition; missing dependencies deny execution."""

    def __init__(
        self,
        *,
        config: MaintenanceActivationConfigV1 | None = None,
        lock_backend: Any = None,
        lease_store: Any = None,
        maintenance_coordinator: Any = None,
        storage_root_binding_sha256: str | None = None,
        registry_path: str | None = None,
        clock: Callable[[], float] | None = None,
        nonce_source: Callable[[], str] | None = None,
        consume_authorization: Callable[[Any, AuthorizationBindingV1], bool] | None = None,
        trading_controls: Callable[[], Mapping[str, Any]] | None = None,
        kill_switch: Callable[[], bool] | None = None,
        bootstrap: Callable[[Any, float], Mapping[str, Any]] | None = None,
        startup_recovery: Callable[[Any, float], Mapping[str, Any]] | None = None,
        postflight: Callable[[Any, float], Mapping[str, Any]] | None = None,
    ) -> None:
        self._config = config or MaintenanceActivationConfigV1()
        self._lock_backend = lock_backend
        self._lease_store = lease_store
        self._supplied_coordinator = maintenance_coordinator
        self._root_binding = storage_root_binding_sha256
        self._registry_path = registry_path
        self._clock = clock
        self._nonce = nonce_source
        self._authorize = consume_authorization
        self._controls = trading_controls
        self._kill_switch = kill_switch
        self._steps = (bootstrap, startup_recovery, postflight)
        self._attempt_lock = threading.Lock()
        self._attempted = False
        self._coordinator = None
        self._last_time = None

    def __repr__(self) -> str:
        return "<OfflineMaintenanceActivationV1 protected>"

    @staticmethod
    def _result(status: str, *, ok: bool = False) -> dict[str, Any]:
        return {
            "ok": ok,
            "status": status,
            "offline_only": True,
            "maintenance_only": True,
            "runtime_integrated": False,
            "production_ready": False,
            "coordination_ready": False,
            "runtime_activation_allowed": False,
            "live_allowed": False,
        }

    def _now(self) -> float:
        value = self._clock()
        if type(value) not in (int, float) or not math.isfinite(value):
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_CLOCK_INVALID")
        if self._last_time is not None and value < self._last_time:
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_CLOCK_REGRESSED")
        self._last_time = float(value)
        return self._last_time

    def _check_controls(self, deadline: float) -> None:
        if self._now() >= deadline:
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_DEADLINE_EXCEEDED")
        if self._kill_switch() is not False:
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_KILL_SWITCH_ENGAGED")
        controls = self._controls()
        if not isinstance(controls, Mapping) or set(controls) != set(_SAFE_CONTROL_VECTOR):
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_CONTROLS_UNSAFE")
        if any(
            type(controls[key]) is not type(expected) or controls[key] != expected
            for key, expected in _SAFE_CONTROL_VECTOR.items()
        ):
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_CONTROLS_UNSAFE")
        if self._now() >= deadline:
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_DEADLINE_EXCEEDED")

    def _check_supplied_coordinator(self, coordinator: Any, config: Any) -> None:
        """Check the injected graph without reading a lease or acquiring a lock.

        Ports are trusted injected dependencies, not a Python security boundary.
        The same clock/nonce functions must be shared; no coordinator is rebuilt
        or reconfigured here. Live lease ownership is checked separately.
        """
        storage = coordinator_module.runtime_storage
        try:
            coordinator_module._validate_production_registry_storage_binding_v1(
                self._registry_path, self._lock_backend.storage_root
            )
        except (AttributeError, coordinator_module.WriterRuntimeCoordinationBlocked) as exc:
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_COORDINATOR_BINDING_INVALID") from exc
        if not (
            type(coordinator) is coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1
            and coordinator is self._supplied_coordinator
            and type(config) is coordinator_module.WriterRuntimeCoordinatorConfigV1
            and coordinator._config is config
            and config.enabled is True and config.maintenance_only is True
            and type(config.lock_timeout_seconds) in (int, float)
            and math.isfinite(config.lock_timeout_seconds)
            and 0 < config.lock_timeout_seconds <= self._config.lock_timeout_seconds
            and coordinator._lock_backend is self._lock_backend
            and coordinator._lease_store is self._lease_store
            and coordinator._clock is self._clock
            and coordinator._nonce_source is self._nonce
            and type(self._lock_backend) is storage.CrossPlatformInterprocessFileLockBackendV1
            and type(self._lease_store) is storage.DurableJsonMaintenanceLeaseStoreV1
            and self._lock_backend.enabled is True and self._lease_store.enabled is True
            and self._lock_backend.storage_root == self._lease_store.storage_root
            and self._root_binding == coordinator_module.production_coordinator_storage_root_binding_sha256_v1(
                self._lock_backend.storage_root)
            and coordinator.lock_namespace == coordinator_module.canonical_runtime_lock_namespace_v1()
            and coordinator.registered_writer_count == 19
            and coordinator.all_writers_registered is True
            and coordinator.inflight_mutations == 0
        ):
            raise MaintenanceActivationBlocked("C3_MAINTENANCE_COORDINATOR_BINDING_INVALID")

    @staticmethod
    def _check_step(phase: str, result: Any, permit: Any) -> None:
        if not (
            isinstance(result, Mapping)
            and result.get("ok") is True
            and result.get("maintenance_permit") is permit
            and result.get("synthetic_only") is True
            and result.get("registry_write") is False
            and result.get("no_order_sent") is True
        ):
            raise MaintenanceActivationBlocked(f"C3_MAINTENANCE_{phase}_UNVERIFIED")
        if phase == "BOOTSTRAP":
            safe = all(result.get(key) is True for key in (
                "migration_done", "restart_readiness_attested", "last_load_ok",
                "last_write_ok", "write_allowed",
            )) and result.get("temporary_read_only") is False
        elif phase == "RECOVERY":
            safe = result.get("startup_recovery_verified") is True and all(
                type(result.get(key)) is int and result[key] == 0
                for key in ("prepared_transactions_after", "resolved_transactions_after",
                            "unresolved_transactions_after")
            )
        else:
            safe = (
                result.get("registry_storage_ready") is True
                and result.get("startup_recovery_verified") is True
                and type(result.get("blocking_failures")) is int
                and result["blocking_failures"] == 0
                and result.get("runtime_activation_allowed") is False
                and result.get("live_allowed") is False
            )
        if not safe:
            raise MaintenanceActivationBlocked(f"C3_MAINTENANCE_{phase}_UNVERIFIED")

    def run_offline(self, request: Any = None) -> dict[str, Any]:
        if self._config.enabled is not True:
            return self._result("C3_MAINTENANCE_DEFAULT_OFF")
        if self._config.scope_attestation != OFFLINE_MAINTENANCE_SCOPE:
            return self._result("C3_MAINTENANCE_SCOPE_REQUIRED")
        if not self._attempt_lock.acquire(blocking=False):
            return self._result("C3_MAINTENANCE_ATTEMPT_IN_PROGRESS")
        try:
            if self._attempted:
                return self._result("C3_MAINTENANCE_ATTEMPT_ALREADY_CONSUMED")
            self._attempted = True
            if not all(callable(port) for port in (
                self._clock, self._nonce, self._authorize, self._controls,
                self._kill_switch, *self._steps,
            )):
                return self._result("C3_MAINTENANCE_DEPENDENCIES_REQUIRED")
            deadline = self._now() + self._config.max_duration_seconds
            self._check_controls(deadline)
            supplied = self._supplied_coordinator
            supplied_config = (supplied._config if type(supplied) is
                               coordinator_module.ClosedRepairWriterRuntimeCoordinatorV1 else None)
            if supplied is not None:
                self._check_supplied_coordinator(supplied, supplied_config)
                if supplied._active_maintenance_frame is not None:
                    raise MaintenanceActivationBlocked("C3_MAINTENANCE_COORDINATOR_BINDING_INVALID")
            nonce = self._nonce()
            if type(nonce) is not str or not nonce:
                raise MaintenanceActivationBlocked("C3_MAINTENANCE_NONCE_REQUIRED")
            binding = AuthorizationBindingV1(
                scope=OFFLINE_MAINTENANCE_SCOPE,
                storage_root_binding_sha256=self._root_binding,
                nonce=nonce,
                deadline=deadline,
            )
            if self._authorize(request, binding) is not True:
                raise MaintenanceActivationBlocked("C3_MAINTENANCE_AUTHORIZATION_DENIED")
            self._check_controls(deadline)
            if supplied is not None:
                self._check_supplied_coordinator(supplied, supplied_config)
                if supplied_config.lock_timeout_seconds > deadline - self._now():
                    raise MaintenanceActivationBlocked("C3_MAINTENANCE_DEADLINE_EXCEEDED")
                coordinator = supplied
            else:
                coordinator = coordinator_module.build_production_closed_repair_writer_runtime_coordinator_v1(
                    config=coordinator_module.ProductionWriterRuntimeCoordinatorBindingConfigV1(
                        enabled=True,
                        scope_attestation=coordinator_module.PRODUCTION_COORDINATOR_EXPLICIT_DEPENDENCY_BINDING_ATTESTATION_V1,
                        storage_root_binding_sha256=self._root_binding,
                        lock_timeout_seconds=min(self._config.lock_timeout_seconds, deadline - self._now()),
                        maintenance_only=True,
                    ),
                    lock_backend=self._lock_backend,
                    lease_store=self._lease_store,
                    registry_path=self._registry_path,
                    clock=self._now,
                    nonce_source=self._nonce,
                )
            self._coordinator = coordinator
            with coordinator.maintenance_lease() as permit:
                if not (
                    type(permit) is coordinator_module.WriterMaintenancePermitV1
                    and permit.state == "QUIESCED"
                    and permit.registered_writer_count == 19
                    and permit.inflight_mutations == 0
                    and permit.shared_lock_acquired is True
                    and permit.lock_namespace_sha256 == coordinator.lock_namespace
                ):
                    raise MaintenanceActivationBlocked("C3_MAINTENANCE_PERMIT_INVALID")
                for phase, operation in zip(("BOOTSTRAP", "RECOVERY", "POSTFLIGHT"), self._steps):
                    self._check_controls(deadline)
                    if supplied is not None:
                        self._check_supplied_coordinator(supplied, supplied_config)
                    if not coordinator.maintenance_permit_is_current_v1(
                        asdict(permit), lock_backend=self._lock_backend
                    ):
                        raise MaintenanceActivationBlocked("C3_MAINTENANCE_PERMIT_INVALID")
                    result = operation(permit, deadline)
                    self._check_controls(deadline)
                    if supplied is not None:
                        self._check_supplied_coordinator(supplied, supplied_config)
                    if not coordinator.maintenance_permit_is_current_v1(
                        asdict(permit), lock_backend=self._lock_backend
                    ):
                        raise MaintenanceActivationBlocked("C3_MAINTENANCE_PERMIT_INVALID")
                    self._check_step(phase, result, permit)
            self._check_controls(deadline)
            released = self._lease_store.read(coordinator.lock_namespace)
            if not (
                isinstance(released, Mapping)
                and released.get("state") == "RELEASED"
                and released.get("maintenance_epoch") == permit.maintenance_epoch
            ):
                raise MaintenanceActivationBlocked("C3_MAINTENANCE_RELEASE_UNVERIFIED")
            self._check_controls(deadline)
            return {
                **self._result("C3_OFFLINE_MAINTENANCE_COMPLETED", ok=True),
                "registered_writer_count": 19,
                "maintenance_lease_released": True,
                "synthetic_steps_verified": True,
            }
        except MaintenanceActivationBlocked as exc:
            known = {
                "C3_MAINTENANCE_CLOCK_INVALID", "C3_MAINTENANCE_CLOCK_REGRESSED",
                "C3_MAINTENANCE_DEADLINE_EXCEEDED", "C3_MAINTENANCE_KILL_SWITCH_ENGAGED",
                "C3_MAINTENANCE_CONTROLS_UNSAFE", "C3_MAINTENANCE_NONCE_REQUIRED",
                "C3_MAINTENANCE_AUTHORIZATION_DENIED", "C3_MAINTENANCE_PERMIT_INVALID",
                "C3_MAINTENANCE_RELEASE_UNVERIFIED", "C3_MAINTENANCE_BOOTSTRAP_UNVERIFIED",
                "C3_MAINTENANCE_RECOVERY_UNVERIFIED", "C3_MAINTENANCE_POSTFLIGHT_UNVERIFIED",
                "C3_MAINTENANCE_COORDINATOR_BINDING_INVALID",
            }
            return self._result(str(exc) if str(exc) in known else "C3_MAINTENANCE_FAILED_CLOSED")
        except coordinator_module.WriterRuntimeCoordinationBlocked:
            return self._result("C3_MAINTENANCE_COORDINATOR_BLOCKED")
        except Exception:
            # Callback errors can contain paths, records or credentials.
            return self._result("C3_MAINTENANCE_FAILED_CLOSED")
        finally:
            self._attempt_lock.release()
