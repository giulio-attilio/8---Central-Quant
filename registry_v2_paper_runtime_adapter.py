"""Strictly gated Registry V2 PAPER persistence for the Turtle runtime.

This adapter is intentionally the only V2.9 runtime-facing write boundary.  It
does not create a storage location, infer a mode, talk to a broker, or fall
back to Registry V1.  The existing V2 core and WAL remain the sole mutation
and idempotency authorities.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
import copy
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

from registry_execution_identity import generate_execution_lifecycle_id, is_v2_execution_id
import registry_execution_schema as schema
import registry_v2_bot_contract as bot_contract
import registry_v2_core as core
import registry_v2_wal as wal


REGISTRY_V2_PAPER_WRITE_ENABLED_ENV = "REGISTRY_V2_PAPER_WRITE_ENABLED"
REGISTRY_V2_PAPER_STORAGE_DIR_ENV = "REGISTRY_V2_PAPER_STORAGE_DIR"

REGISTRY_V2_PAPER_SNAPSHOT_FILENAME = "registry_v2.json"
REGISTRY_V2_PAPER_JOURNAL_FILENAME = "registry_v2_events.jsonl"
REGISTRY_V2_PAPER_LOCK_FILENAME = "registry_v2.lock"
REGISTRY_V2_PAPER_BACKUP_DIRNAME = "registry_v2_backups"

REGISTRY_V2_PAPER_RUNTIME_DISABLED = "REGISTRY_V2_PAPER_WRITE_DISABLED"
REGISTRY_V2_PAPER_RUNTIME_MODE_REJECTED = "REGISTRY_V2_PAPER_MODE_REJECTED"
REGISTRY_V2_PAPER_RUNTIME_STORAGE_REQUIRED = "REGISTRY_V2_PAPER_STORAGE_CONFIG_REQUIRED"
REGISTRY_V2_PAPER_RUNTIME_STORAGE_INVALID = "REGISTRY_V2_PAPER_STORAGE_CONFIG_INVALID"
REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED = "REGISTRY_V2_PAPER_RECOVERY_BLOCKED"
REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID = "REGISTRY_V2_PAPER_POSITION_INVALID"
REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID = "REGISTRY_V2_PAPER_IDENTITY_INVALID"
REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID = "REGISTRY_V2_PAPER_IDEMPOTENCY_INVALID"
REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID = "REGISTRY_V2_PAPER_CONTRACT_INVALID"
REGISTRY_PERSISTENCE_LOCK_TIMEOUT = "REGISTRY_PERSISTENCE_LOCK_TIMEOUT"

# Local PAPER persistence should never wait indefinitely for another writer.
# Tests may temporarily replace this module-level value; it is intentionally
# not an environment switch or a productive runtime mode configuration.
REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS = 2.0

_REGISTER_KEY_FIELD = "registry_v2_register_idempotency_key"
_CLOSE_EVENT_FIELD = "registry_v2_close_event_id"
_CLOSE_KEY_FIELD = "registry_v2_close_idempotency_key"
_V2_ROUTED_FIELD = "registry_v2_routed"
_TURTLE_REGISTER_OCCURRENCE_PREFIX = "turtle-paper-register-occurrence:v1:"

_RUNTIME_LOCKS_GUARD = threading.Lock()
_RUNTIME_LOCKS: dict[str, threading.RLock] = {}

_IMMUTABLE_UPDATE_FIELDS = frozenset(
    {
        "execution_id",
        "lifecycle_id",
        "logical_trade_id",
        "bot",
        "setup",
        "symbol",
        "side",
        "owner_type",
        "execution_mode",
        "registry_mode",
        "quantity",
        "remaining_qty",
        "closed_qty",
        "close_events",
        "close_event_id",
        "close_reason",
    }
)


def parse_registry_v2_paper_write_enabled(value: Any) -> bool:
    """Return true only for the explicitly enabled PAPER write value."""

    return isinstance(value, str) and value.strip().lower() == "true"


REGISTRY_V2_PAPER_WRITE_ENABLED = parse_registry_v2_paper_write_enabled(
    os.environ.get(REGISTRY_V2_PAPER_WRITE_ENABLED_ENV)
)


@dataclass(frozen=True)
class RegistryV2PaperRuntimeResult:
    """Read-only observability envelope for one adapter operation."""

    ok: bool
    status: str
    enabled: bool
    eligible: bool
    mode: str
    operation: str
    execution_id: str | None = None
    lifecycle_id: str | None = None
    idempotency_key_present: bool = False
    storage_configured: bool = False
    write_attempted: bool = False
    write_committed: bool = False
    core_status: str | None = None
    wal_status: str | None = None
    event_id: str | None = None
    event_seq: int | None = None
    event_state: str | None = None
    expected_generation: int | None = None
    target_generation: int | None = None
    recovery_required: bool = False
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "enabled": self.enabled,
            "eligible": self.eligible,
            "mode": self.mode,
            "operation": self.operation,
            "execution_id": self.execution_id,
            "lifecycle_id": self.lifecycle_id,
            "idempotency_key_present": self.idempotency_key_present,
            "storage_configured": self.storage_configured,
            "write_attempted": self.write_attempted,
            "write_committed": self.write_committed,
            "core_status": self.core_status,
            "wal_status": self.wal_status,
            "event_id": self.event_id,
            "event_seq": self.event_seq,
            "event_state": self.event_state,
            "expected_generation": self.expected_generation,
            "target_generation": self.target_generation,
            "recovery_required": self.recovery_required,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class RegistryV2PaperRuntimeReadResult:
    """Read-only evidence for an exact committed PAPER lifecycle event."""

    ok: bool
    status: str
    enabled: bool
    eligible: bool
    mode: str
    operation: str
    execution_id: str | None = None
    lifecycle_id: str | None = None
    storage_configured: bool = False
    found: bool = False
    event_id: str | None = None
    event_seq: int | None = None
    event_state: str | None = None
    committed_at: str | None = None
    mutation_payload: Mapping[str, Any] | None = None
    recovery_required: bool = False
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "enabled": self.enabled,
            "eligible": self.eligible,
            "mode": self.mode,
            "operation": self.operation,
            "execution_id": self.execution_id,
            "lifecycle_id": self.lifecycle_id,
            "storage_configured": self.storage_configured,
            "found": self.found,
            "event_id": self.event_id,
            "event_seq": self.event_seq,
            "event_state": self.event_state,
            "committed_at": self.committed_at,
            "mutation_payload": (
                copy.deepcopy(dict(self.mutation_payload))
                if isinstance(self.mutation_payload, Mapping)
                else None
            ),
            "recovery_required": self.recovery_required,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class _Preflight:
    storage: wal.RegistryV2WalStorage
    mode: str
    operation: str
    inspection: wal.WalRecoveryInspection | None = None


class _RuntimeRegistryLockTimeout(RuntimeError):
    """The bounded Registry V2 runtime serialization boundary was unavailable."""


def _normalized_runtime_lock_path(lock_path: Path) -> str:
    """Return one process-wide key for an explicit Registry V2 lock file."""

    return os.path.normcase(str(lock_path.resolve()))


def _process_lock_for(lock_path: Path) -> threading.RLock:
    """Return the module-shared local lock for one Registry document."""

    normalized = _normalized_runtime_lock_path(lock_path)
    with _RUNTIME_LOCKS_GUARD:
        lock = _RUNTIME_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _RUNTIME_LOCKS[normalized] = lock
        return lock


class _RuntimeRegistryLock:
    """Bounded process-local plus OS-level lock for one Registry V2 document."""

    def __init__(self, lock_path: Path, timeout_seconds: float) -> None:
        self._lock_path = Path(lock_path)
        self._thread_lock = _process_lock_for(self._lock_path)
        self._timeout_seconds = max(0.0, float(timeout_seconds))
        self._lock_file: Any | None = None
        self._thread_locked = False
        self._platform_locked = False

    def __enter__(self) -> "_RuntimeRegistryLock":
        deadline = time.monotonic() + self._timeout_seconds
        if not self._thread_lock.acquire(timeout=self._timeout_seconds):
            raise _RuntimeRegistryLockTimeout("process_local_lock_timeout")
        self._thread_locked = True
        try:
            self._lock_file = open(self._lock_path, "a+b")
            self._ensure_lock_byte(self._lock_file)
            self._acquire_platform_lock(self._lock_file, deadline)
            self._platform_locked = True
        except _RuntimeRegistryLockTimeout:
            self._release_after_failed_acquire()
            raise
        except OSError as exc:
            self._release_after_failed_acquire()
            raise _RuntimeRegistryLockTimeout("os_lock_unavailable") from exc
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            if self._platform_locked and self._lock_file is not None:
                try:
                    self._release_platform_lock(self._lock_file)
                except OSError:
                    # Closing the descriptor still releases an OS advisory lock.
                    pass
        finally:
            self._platform_locked = False
            self._close_lock_file()
            if self._thread_locked:
                self._thread_lock.release()
                self._thread_locked = False

    @staticmethod
    def _ensure_lock_byte(lock_file: Any) -> None:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
            os.fsync(lock_file.fileno())
        lock_file.seek(0)

    @staticmethod
    def _acquire_platform_lock(lock_file: Any, deadline: float) -> None:
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise _RuntimeRegistryLockTimeout("interprocess_lock_timeout") from exc
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise _RuntimeRegistryLockTimeout("interprocess_lock_timeout") from exc
                    time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    @staticmethod
    def _release_platform_lock(lock_file: Any) -> None:
        if os.name == "nt":
            import msvcrt

            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _release_after_failed_acquire(self) -> None:
        self._close_lock_file()
        if self._thread_locked:
            self._thread_lock.release()
            self._thread_locked = False

    def _close_lock_file(self) -> None:
        if self._lock_file is not None:
            try:
                self._lock_file.close()
            finally:
                self._lock_file = None


class RegistryV2PaperRuntimeAdapter:
    """PAPER-only Turtle adapter with an explicit local V2 storage location."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        storage_dir: str | Path | None = None,
    ) -> None:
        self._enabled = REGISTRY_V2_PAPER_WRITE_ENABLED if enabled is None else enabled is True
        self._storage_dir = (
            os.environ.get(REGISTRY_V2_PAPER_STORAGE_DIR_ENV)
            if storage_dir is None
            else storage_dir
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def has_explicit_paper_storage(self) -> bool:
        """Whether a caller supplied a storage location for exact read recovery."""

        return self._storage_dir is not None and bool(str(self._storage_dir).strip())

    def register_turtle_paper(
        self,
        position: MutableMapping[str, Any],
        *,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> RegistryV2PaperRuntimeResult:
        """Register one new Turtle PAPER position through V2 WAL/core only."""

        preflight = self._preflight(core.REGISTER, execution_mode, registry_mode)
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return preflight
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return invalid_position
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return component_error
        assert components is not None
        facts, facts_error = self._open_facts(position, preflight)
        if facts_error is not None:
            return facts_error
        return self._run_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._register_locked(
                locked_preflight,
                position,
                components,
                facts,
                idempotency_key,
                fault_hook,
            ),
        )

    def read_turtle_paper_committed_register(
        self,
        position: MutableMapping[str, Any],
        *,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Read one exact source-keyed committed Turtle register without writing."""

        preflight = self._preflight(
            core.REGISTER,
            execution_mode,
            registry_mode,
            allow_disabled_read=True,
        )
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return self._read_from_write_failure(preflight)
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return self._read_from_write_failure(invalid_position)
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return self._read_from_write_failure(component_error)
        assert components is not None
        facts, facts_error = self._open_facts(position, preflight)
        if facts_error is not None:
            return self._read_from_write_failure(facts_error)
        assert facts is not None
        if "signal_ts" not in facts:
            return self._read_failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("signal_ts",),
            )
        source_key, source_key_error = self._stable_key(
            position,
            _REGISTER_KEY_FIELD,
            idempotency_key,
            "",
            preflight,
        )
        if source_key_error is not None:
            return self._read_from_write_failure(source_key_error)
        if (
            not source_key
            or not source_key.startswith(_TURTLE_REGISTER_OCCURRENCE_PREFIX)
        ):
            return self._read_failure(
                REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID,
                preflight,
                errors=("register_source_occurrence_key_required",),
            )
        return self._read_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._read_committed_register(
                locked_preflight,
                position,
                components,
                facts,
                source_key,
            ),
        )

    def update_turtle_paper(
        self,
        position: MutableMapping[str, Any],
        *,
        event: Any,
        updates: Mapping[str, Any] | None,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> RegistryV2PaperRuntimeResult:
        """Apply one Turtle management update selected by exact V2 identity."""

        preflight = self._preflight(core.UPDATE, execution_mode, registry_mode)
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return preflight
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return invalid_position
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return component_error
        assert components is not None
        execution_id, identity_error = self._existing_identity(position, preflight)
        if identity_error is not None:
            return identity_error
        assert execution_id is not None
        event_text = _nonempty_text(event)
        if event_text is None:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=("event_required",),
            )
        patch, patch_error = self._management_patch(position, event_text, updates, preflight)
        if patch_error is not None:
            return patch_error
        assert patch is not None
        key, key_error = self._operation_key(
            idempotency_key,
            f"turtle-paper-update:{execution_id}:{event_text}",
            preflight,
            execution_id,
        )
        if key_error is not None:
            return key_error
        assert key is not None
        return self._run_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._update_locked(
                locked_preflight,
                execution_id,
                components,
                patch,
                key,
                fault_hook,
            ),
        )

    def close_turtle_paper(
        self,
        position: MutableMapping[str, Any],
        *,
        exit_price: Any,
        reason: Any,
        result_pct: Any = None,
        result_r: Any = None,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
        fault_hook: Callable[[str], None] | None = None,
    ) -> RegistryV2PaperRuntimeResult:
        """Close one Turtle PAPER execution through the exact-ID V2 core API."""

        preflight = self._preflight(core.FULL_CLOSE, execution_mode, registry_mode)
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return preflight
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return invalid_position
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return component_error
        assert components is not None
        execution_id, identity_error = self._existing_identity(position, preflight)
        if identity_error is not None:
            return identity_error
        assert execution_id is not None
        economics, economics_error = self._close_economics(
            exit_price,
            reason,
            result_pct,
            result_r,
            preflight,
            execution_id,
        )
        if economics_error is not None:
            return economics_error
        assert economics is not None
        close_event_id, close_event_error = self._stable_key(
            position,
            _CLOSE_EVENT_FIELD,
            None,
            f"turtle-paper-close:{execution_id}",
            preflight,
            execution_id=execution_id,
        )
        if close_event_error is not None:
            return close_event_error
        assert close_event_id is not None
        key, key_error = self._stable_key(
            position,
            _CLOSE_KEY_FIELD,
            idempotency_key,
            f"turtle-paper-close-request:{execution_id}",
            preflight,
            execution_id=execution_id,
        )
        if key_error is not None:
            return key_error
        assert key is not None
        return self._run_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._close_locked(
                locked_preflight,
                position,
                execution_id,
                components,
                close_event_id,
                key,
                economics,
                fault_hook,
            ),
        )

    def read_turtle_paper_committed_update(
        self,
        position: MutableMapping[str, Any],
        *,
        event: Any,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Read one exact committed Turtle management update without writing."""

        preflight = self._preflight(core.UPDATE, execution_mode, registry_mode)
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return self._read_from_write_failure(preflight)
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return self._read_from_write_failure(invalid_position)
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return self._read_from_write_failure(component_error)
        assert components is not None
        execution_id, identity_error = self._existing_identity(position, preflight)
        if identity_error is not None:
            return self._read_from_write_failure(identity_error)
        assert execution_id is not None
        event_text = _nonempty_text(event)
        if event_text is None:
            return self._read_failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                execution_id=execution_id,
                errors=("event_required",),
            )
        key, key_error = self._operation_key(
            idempotency_key,
            f"turtle-paper-update:{execution_id}:{event_text}",
            preflight,
            execution_id,
        )
        if key_error is not None:
            return self._read_from_write_failure(key_error)
        assert key is not None
        return self._read_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._read_exact_committed(
                locked_preflight,
                core.UPDATE,
                execution_id,
                key,
                components,
            ),
        )

    def read_turtle_paper_committed_close(
        self,
        position: MutableMapping[str, Any],
        *,
        execution_mode: Any,
        registry_mode: Any,
        idempotency_key: str | None = None,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Read one exact committed Turtle full close without writing."""

        preflight = self._preflight(core.FULL_CLOSE, execution_mode, registry_mode)
        if isinstance(preflight, RegistryV2PaperRuntimeResult):
            return self._read_from_write_failure(preflight)
        invalid_position = self._require_mutable_position(position, preflight)
        if invalid_position is not None:
            return self._read_from_write_failure(invalid_position)
        components, component_error = self._turtle_components(position, preflight)
        if component_error is not None:
            return self._read_from_write_failure(component_error)
        assert components is not None
        execution_id, identity_error = self._existing_identity(position, preflight)
        if identity_error is not None:
            return self._read_from_write_failure(identity_error)
        assert execution_id is not None
        close_event_id, close_event_error = self._stable_key(
            position,
            _CLOSE_EVENT_FIELD,
            None,
            f"turtle-paper-close:{execution_id}",
            preflight,
            execution_id=execution_id,
        )
        if close_event_error is not None:
            return self._read_from_write_failure(close_event_error)
        assert close_event_id is not None
        key, key_error = self._stable_key(
            position,
            _CLOSE_KEY_FIELD,
            idempotency_key,
            f"turtle-paper-close-request:{execution_id}",
            preflight,
            execution_id=execution_id,
        )
        if key_error is not None:
            return self._read_from_write_failure(key_error)
        assert key is not None
        return self._read_with_runtime_lock(
            preflight,
            lambda locked_preflight: self._read_exact_committed(
                locked_preflight,
                core.FULL_CLOSE,
                execution_id,
                key,
                components,
                close_event_id=close_event_id,
            ),
        )

    def _run_with_runtime_lock(
        self,
        preflight: _Preflight,
        operation: Callable[[_Preflight], RegistryV2PaperRuntimeResult],
    ) -> RegistryV2PaperRuntimeResult:
        """Inspect, resolve generation, and mutate under one runtime boundary."""

        try:
            with _RuntimeRegistryLock(
                preflight.storage.lock_path,
                REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS,
            ):
                locked_preflight = self._inspect_after_runtime_lock(preflight)
                if isinstance(locked_preflight, RegistryV2PaperRuntimeResult):
                    return locked_preflight
                return operation(locked_preflight)
        except _RuntimeRegistryLockTimeout as error:
            return RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_PERSISTENCE_LOCK_TIMEOUT,
                True,
                True,
                preflight.mode,
                preflight.operation,
                storage_configured=True,
                errors=(str(error) or "runtime_lock_timeout",),
            )

    def _read_with_runtime_lock(
        self,
        preflight: _Preflight,
        operation: Callable[[_Preflight], RegistryV2PaperRuntimeReadResult],
    ) -> RegistryV2PaperRuntimeReadResult:
        """Inspect exact committed evidence under the established runtime lock."""

        try:
            with _RuntimeRegistryLock(
                preflight.storage.lock_path,
                REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS,
            ):
                locked_preflight = self._inspect_after_runtime_lock(preflight)
                if isinstance(locked_preflight, RegistryV2PaperRuntimeResult):
                    return self._read_from_write_failure(locked_preflight)
                return operation(locked_preflight)
        except _RuntimeRegistryLockTimeout as error:
            return RegistryV2PaperRuntimeReadResult(
                False,
                REGISTRY_PERSISTENCE_LOCK_TIMEOUT,
                True,
                True,
                preflight.mode,
                preflight.operation,
                storage_configured=True,
                errors=(str(error) or "runtime_lock_timeout",),
            )

    def _read_exact_committed(
        self,
        preflight: _Preflight,
        operation: str,
        execution_id: str,
        idempotency_key: str,
        components: Mapping[str, str],
        *,
        close_event_id: str | None = None,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Return only one validated exact committed journal event, if present."""

        assert preflight.inspection is not None
        lookup = wal.find_committed_operation(
            preflight.inspection.committed_events,
            operation,
            execution_id,
            idempotency_key,
        )
        if lookup.status == wal.WAL_NOT_FOUND:
            return RegistryV2PaperRuntimeReadResult(
                True,
                wal.WAL_NOT_FOUND,
                True,
                True,
                preflight.mode,
                operation,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                storage_configured=True,
            )
        if not lookup.ok or lookup.event is None:
            return self._read_failure(
                lookup.status,
                preflight,
                execution_id=execution_id,
                errors=tuple(lookup.errors) or (lookup.status,),
            )
        event = lookup.event
        if event.execution_id != execution_id or event.lifecycle_id != execution_id:
            return self._read_failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                execution_id=execution_id,
                errors=("committed_event_identity_mismatch",),
            )
        payload = event.mutation_payload
        if not isinstance(payload, Mapping):
            return self._read_failure(
                REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                preflight,
                execution_id=execution_id,
                errors=("committed_event_payload_invalid",),
            )
        if operation == core.UPDATE:
            patch = payload.get("patch")
            if not isinstance(patch, Mapping):
                return self._read_failure(
                    REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                    preflight,
                    execution_id=execution_id,
                    errors=("committed_update_patch_invalid",),
                )
        elif operation == core.FULL_CLOSE:
            close = payload.get("close")
            if (
                not isinstance(close, Mapping)
                or close.get("kind") != core.FULL_CLOSE
                or close.get("close_event_id") != close_event_id
                or not isinstance(close.get("factual_economics"), Mapping)
            ):
                return self._read_failure(
                    REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                    preflight,
                    execution_id=execution_id,
                    errors=("committed_close_payload_invalid",),
                )
        expected = self._expected_identity(execution_id, components)
        payload_identity = payload.get("expected_identity")
        if isinstance(payload_identity, Mapping):
            for field, value in expected.items():
                if payload_identity.get(field) != value:
                    return self._read_failure(
                        REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                        preflight,
                        execution_id=execution_id,
                        errors=(f"committed_event_expected_identity:{field}",),
                    )
        return RegistryV2PaperRuntimeReadResult(
            True,
            wal.WAL_OK,
            True,
            True,
            preflight.mode,
            operation,
            execution_id=execution_id,
            lifecycle_id=execution_id,
            storage_configured=True,
            found=True,
            event_id=event.event_id,
            event_seq=event.event_seq,
            event_state=event.state,
            committed_at=event.committed_at,
            mutation_payload=copy.deepcopy(dict(payload)),
        )

    def _read_committed_register(
        self,
        preflight: _Preflight,
        position: MutableMapping[str, Any],
        components: Mapping[str, str],
        facts: Mapping[str, Any],
        idempotency_key: str,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Read and materialize only one validated source-keyed registration."""

        replay = self._recover_committed_register(
            preflight,
            position,
            components,
            facts,
            idempotency_key,
        )
        if isinstance(replay, RegistryV2PaperRuntimeResult):
            return self._read_from_write_failure(replay)
        if replay is None:
            return RegistryV2PaperRuntimeReadResult(
                True,
                wal.WAL_NOT_FOUND,
                True,
                True,
                preflight.mode,
                core.REGISTER,
                storage_configured=True,
            )
        event, row = replay
        execution_id = event.execution_id
        assert isinstance(execution_id, str)
        self._apply_registered_row(position, row, idempotency_key)
        return RegistryV2PaperRuntimeReadResult(
            True,
            wal.WAL_OK,
            True,
            True,
            preflight.mode,
            core.REGISTER,
            execution_id=execution_id,
            lifecycle_id=execution_id,
            storage_configured=True,
            found=True,
            event_id=event.event_id,
            event_seq=event.event_seq,
            event_state=event.state,
            committed_at=event.committed_at,
            mutation_payload={"trade": copy.deepcopy(dict(row))},
        )

    def _inspect_after_runtime_lock(
        self,
        preflight: _Preflight,
    ) -> _Preflight | RegistryV2PaperRuntimeResult:
        """Fail closed on recovery only after the outer runtime lock is held."""

        inspection = wal.inspect_wal_recovery_state(preflight.storage)
        locked_preflight = _Preflight(
            preflight.storage,
            preflight.mode,
            preflight.operation,
            inspection,
        )
        if inspection.status != wal.CLEAN:
            return RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED,
                True,
                False,
                preflight.mode,
                preflight.operation,
                storage_configured=True,
                wal_status=inspection.status,
                recovery_required=True,
                errors=tuple(inspection.errors) or (inspection.status,),
            )
        if inspection.snapshot_generation is None and inspection.events:
            return RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED,
                True,
                False,
                preflight.mode,
                preflight.operation,
                storage_configured=True,
                wal_status=inspection.status,
                recovery_required=True,
                errors=("missing_factual_generation",),
            )
        return locked_preflight

    def _register_locked(
        self,
        preflight: _Preflight,
        position: MutableMapping[str, Any],
        components: Mapping[str, str],
        facts: Mapping[str, Any],
        idempotency_key: str | None,
        fault_hook: Callable[[str], None] | None,
    ) -> RegistryV2PaperRuntimeResult:
        """Recover an exact source occurrence before generating a new identity."""

        supplied_key, supplied_key_error = self._stable_key(
            position,
            _REGISTER_KEY_FIELD,
            idempotency_key,
            "",
            preflight,
        )
        if supplied_key_error is not None:
            return supplied_key_error
        if supplied_key and supplied_key.startswith(_TURTLE_REGISTER_OCCURRENCE_PREFIX):
            replay = self._recover_committed_register(
                preflight,
                position,
                components,
                facts,
                supplied_key,
            )
            if isinstance(replay, RegistryV2PaperRuntimeResult):
                return replay
            if replay is not None:
                event, row = replay
                execution_id = event.execution_id
                assert execution_id is not None
                self._apply_registered_row(position, row, supplied_key)
                return self._committed_replay_result(preflight, event, execution_id, supplied_key)

        identity, _created, identity_error = self._new_or_existing_identity(position, preflight)
        if identity_error is not None:
            return identity_error
        assert identity is not None
        execution_id = identity
        key = supplied_key or f"turtle-paper-register:{execution_id}"
        row, row_error = self._register_row(position, components, execution_id, facts, preflight)
        if row_error is not None:
            return row_error
        assert row is not None

        contract = bot_contract.validate_registry_v2_bot_payload("TURTLE", row)
        if not contract.ok:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=(contract.status, *contract.errors),
            )
        validation = schema.validate_registry_execution_row(row)
        if not validation.ok:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=(validation.status, *validation.errors),
            )

        assert preflight.inspection is not None
        expected_generation = self._generation_for_request(
            preflight.inspection,
            core.REGISTER,
            execution_id,
            key,
        )
        core_result = core.register_trade_v2(
            preflight.storage,
            row,
            key,
            expected_generation,
            fault_hook=fault_hook,
        )
        result = self._core_result(
            core_result,
            preflight,
            execution_id,
            key,
            expected_generation,
        )
        if result.ok and result.write_committed:
            self._apply_registered_row(position, row, key)
        return result

    def _recover_committed_register(
        self,
        preflight: _Preflight,
        position: Mapping[str, Any],
        components: Mapping[str, str],
        facts: Mapping[str, Any],
        idempotency_key: str,
    ) -> tuple[wal.WalEvent, Mapping[str, Any]] | RegistryV2PaperRuntimeResult | None:
        """Find one source-keyed registration without selecting by logical trade."""

        assert preflight.inspection is not None
        matches = [
            event
            for event in preflight.inspection.committed_events
            if event.operation == core.REGISTER and event.idempotency_key == idempotency_key
        ]
        if not matches:
            return None
        if len(matches) != 1:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                idempotency_key_present=True,
                errors=("register_source_key_not_unique",),
            )
        event = matches[0]
        execution_id = event.execution_id
        if (
            not isinstance(execution_id, str)
            or event.lifecycle_id != execution_id
            or not is_v2_execution_id(execution_id)
        ):
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                errors=("committed_register_identity_invalid",),
            )
        provided_execution_id = position.get("execution_id")
        provided_lifecycle_id = position.get("lifecycle_id")
        if (
            provided_execution_id is not None
            or provided_lifecycle_id is not None
        ) and (provided_execution_id != execution_id or provided_lifecycle_id != execution_id):
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                execution_id=(provided_execution_id if isinstance(provided_execution_id, str) else None),
                lifecycle_id=(provided_lifecycle_id if isinstance(provided_lifecycle_id, str) else None),
                idempotency_key_present=True,
                errors=("register_source_key_identity_conflict",),
            )
        payload = event.mutation_payload
        row = payload.get("trade") if isinstance(payload, Mapping) else None
        if not isinstance(row, Mapping):
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=("committed_register_trade_invalid",),
            )
        row_copy = copy.deepcopy(dict(row))
        validation = schema.validate_registry_execution_row(row_copy)
        if not validation.ok:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=(validation.status, *validation.errors),
            )
        if row_copy.get("execution_id") != execution_id or row_copy.get("lifecycle_id") != execution_id:
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=("committed_register_row_identity_mismatch",),
            )
        for field, value in components.items():
            if row_copy.get(field) != value:
                return self._failure(
                    REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                    preflight,
                    execution_id=execution_id,
                    lifecycle_id=execution_id,
                    idempotency_key_present=True,
                    errors=(f"committed_register_component_mismatch:{field}",),
                )
        if row_copy.get("signal_ts") != facts.get("signal_ts"):
            return self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                idempotency_key_present=True,
                errors=("committed_register_component_mismatch:signal_ts",),
            )
        return event, row_copy

    @staticmethod
    def _apply_registered_row(
        position: MutableMapping[str, Any],
        row: Mapping[str, Any],
        idempotency_key: str,
    ) -> None:
        """Materialize only V2-committed opening facts into the local card."""

        position["execution_id"] = row["execution_id"]
        position["lifecycle_id"] = row["lifecycle_id"]
        for source, target in (
            ("entry_price", "entry"),
            ("initial_stop_price", "initial_stop"),
            ("stop_price", "stop"),
            ("tp50_price", "tp50"),
            ("signal_ts", "signal_ts"),
        ):
            if source in row:
                position[target] = copy.deepcopy(row[source])
        position[_REGISTER_KEY_FIELD] = idempotency_key
        position[_V2_ROUTED_FIELD] = True

    def _committed_replay_result(
        self,
        preflight: _Preflight,
        event: wal.WalEvent,
        execution_id: str,
        idempotency_key: str,
    ) -> RegistryV2PaperRuntimeResult:
        """Expose an exact existing committed fact without a second core call."""

        return RegistryV2PaperRuntimeResult(
            True,
            wal.WAL_OK,
            True,
            True,
            preflight.mode,
            core.REGISTER,
            execution_id=execution_id,
            lifecycle_id=execution_id,
            idempotency_key_present=bool(idempotency_key),
            storage_configured=True,
            write_attempted=False,
            write_committed=True,
            core_status=wal.WAL_OK,
            wal_status=wal.CLEAN,
            event_id=event.event_id,
            event_seq=event.event_seq,
            event_state=event.state,
            expected_generation=event.expected_generation,
            target_generation=event.target_generation,
        )

    def _update_locked(
        self,
        preflight: _Preflight,
        execution_id: str,
        components: Mapping[str, str],
        patch: Mapping[str, Any],
        idempotency_key: str,
        fault_hook: Callable[[str], None] | None,
    ) -> RegistryV2PaperRuntimeResult:
        """Resolve the exact update generation and call core under the lock."""

        assert preflight.inspection is not None
        expected_generation = self._generation_for_request(
            preflight.inspection,
            core.UPDATE,
            execution_id,
            idempotency_key,
        )
        core_result = core.update_trade_v2(
            preflight.storage,
            execution_id,
            execution_id,
            patch,
            idempotency_key,
            expected_generation,
            expected_identity=self._expected_identity(execution_id, components),
            fault_hook=fault_hook,
        )
        return self._core_result(
            core_result,
            preflight,
            execution_id,
            idempotency_key,
            expected_generation,
        )

    def _close_locked(
        self,
        preflight: _Preflight,
        position: MutableMapping[str, Any],
        execution_id: str,
        components: Mapping[str, str],
        close_event_id: str,
        idempotency_key: str,
        economics: Mapping[str, Any],
        fault_hook: Callable[[str], None] | None,
    ) -> RegistryV2PaperRuntimeResult:
        """Resolve the exact close generation and call core under the lock."""

        assert preflight.inspection is not None
        expected_generation = self._generation_for_request(
            preflight.inspection,
            core.FULL_CLOSE,
            execution_id,
            idempotency_key,
        )
        core_result = core.close_trade_v2(
            preflight.storage,
            execution_id,
            execution_id,
            close_event_id,
            idempotency_key,
            expected_generation,
            factual_economics=economics,
            expected_identity=self._expected_identity(execution_id, components),
            fault_hook=fault_hook,
        )
        result = self._core_result(
            core_result,
            preflight,
            execution_id,
            idempotency_key,
            expected_generation,
        )
        if result.ok and result.write_committed:
            position[_CLOSE_EVENT_FIELD] = close_event_id
            position[_CLOSE_KEY_FIELD] = idempotency_key
            position[_V2_ROUTED_FIELD] = True
        return result

    def _preflight(
        self,
        operation: str,
        execution_mode: Any,
        registry_mode: Any,
        *,
        allow_disabled_read: bool = False,
    ) -> _Preflight | RegistryV2PaperRuntimeResult:
        mode = _mode_label(execution_mode, registry_mode)
        if not self.enabled and not allow_disabled_read:
            return RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_DISABLED,
                False,
                False,
                mode,
                operation,
                errors=("paper_write_gate_disabled",),
            )
        if execution_mode != schema.PAPER or registry_mode != schema.PAPER:
            return RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_MODE_REJECTED,
                True,
                False,
                mode,
                operation,
                errors=("execution_mode", "registry_mode"),
            )
        storage, storage_error = self._storage(operation, mode)
        if storage_error is not None:
            return storage_error
        assert storage is not None
        return _Preflight(storage, mode, operation)

    def _storage(
        self,
        operation: str,
        mode: str,
    ) -> tuple[wal.RegistryV2WalStorage | None, RegistryV2PaperRuntimeResult | None]:
        if self._storage_dir is None or not str(self._storage_dir).strip():
            return None, RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_STORAGE_REQUIRED,
                True,
                False,
                mode,
                operation,
                errors=("explicit_storage_dir_required",),
            )
        try:
            directory = Path(self._storage_dir)
        except (TypeError, ValueError):
            return None, RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_STORAGE_INVALID,
                True,
                False,
                mode,
                operation,
                errors=("storage_dir_invalid",),
            )
        if not directory.is_absolute() or not directory.is_dir():
            return None, RegistryV2PaperRuntimeResult(
                False,
                REGISTRY_V2_PAPER_RUNTIME_STORAGE_INVALID,
                True,
                False,
                mode,
                operation,
                errors=("storage_dir_must_be_existing_absolute_directory",),
            )
        return (
            wal.RegistryV2WalStorage(
                snapshot_path=directory / REGISTRY_V2_PAPER_SNAPSHOT_FILENAME,
                journal_path=directory / REGISTRY_V2_PAPER_JOURNAL_FILENAME,
                lock_path=directory / REGISTRY_V2_PAPER_LOCK_FILENAME,
                backup_dir=directory / REGISTRY_V2_PAPER_BACKUP_DIRNAME,
            ),
            None,
        )

    def _require_mutable_position(
        self,
        position: Any,
        preflight: _Preflight,
    ) -> RegistryV2PaperRuntimeResult | None:
        if isinstance(position, MutableMapping):
            return None
        return self._failure(
            REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
            preflight,
            errors=("mutable_position_mapping_required",),
        )

    def _turtle_components(
        self,
        position: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[dict[str, str] | None, RegistryV2PaperRuntimeResult | None]:
        owner_type = position.get("owner_type", schema.CENTRAL)
        if owner_type != schema.CENTRAL:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("owner_type_not_central",),
            )
        setup = _canonical_text(position.get("setup"))
        symbol = _canonical_text(position.get("symbol"))
        side = _canonical_text(position.get("side"))
        missing = tuple(
            field
            for field, value in (("setup", setup), ("symbol", symbol), ("side", side))
            if value is None
        )
        if missing:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=missing,
            )
        if side not in schema.SIDES:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("side",),
            )
        if "position_side" in position and position.get("position_side") not in schema.POSITION_SIDES:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("position_side",),
            )
        return {
            "bot": "TURTLE",
            "setup": setup,
            "symbol": symbol,
            "side": side,
            "owner_type": schema.CENTRAL,
        }, None

    def _open_facts(
        self,
        position: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[dict[str, Any] | None, RegistryV2PaperRuntimeResult | None]:
        facts: dict[str, Any] = {}
        for source, target in (
            ("entry", "entry_price"),
            ("initial_stop", "initial_stop_price"),
            ("stop", "stop_price"),
            ("tp50", "tp50_price"),
        ):
            if source not in position or position.get(source) is None:
                continue
            value = _finite_number(position.get(source))
            if value is None:
                return None, self._failure(
                    REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                    preflight,
                    errors=(source,),
                )
            facts[target] = value
        signal_ts = position.get("signal_ts")
        if signal_ts is not None:
            if not isinstance(signal_ts, int) or isinstance(signal_ts, bool):
                return None, self._failure(
                    REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                    preflight,
                    errors=("signal_ts",),
                )
            facts["signal_ts"] = signal_ts
        return facts, None

    def _new_or_existing_identity(
        self,
        position: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[str | None, bool, RegistryV2PaperRuntimeResult | None]:
        execution_id = position.get("execution_id")
        lifecycle_id = position.get("lifecycle_id")
        if execution_id is None and lifecycle_id is None:
            return generate_execution_lifecycle_id(), True, None
        if (
            isinstance(execution_id, str)
            and isinstance(lifecycle_id, str)
            and execution_id == lifecycle_id
            and is_v2_execution_id(execution_id)
        ):
            return execution_id, False, None
        return None, False, self._failure(
            REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
            preflight,
            execution_id=execution_id if isinstance(execution_id, str) else None,
            lifecycle_id=lifecycle_id if isinstance(lifecycle_id, str) else None,
            errors=("execution_id_lifecycle_id_matching_canonical_v2_required",),
        )

    def _existing_identity(
        self,
        position: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[str | None, RegistryV2PaperRuntimeResult | None]:
        identity, created, error = self._new_or_existing_identity_for_existing(position, preflight)
        if error is not None:
            return None, error
        assert created is False
        return identity, None

    def _new_or_existing_identity_for_existing(
        self,
        position: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[str | None, bool, RegistryV2PaperRuntimeResult | None]:
        execution_id = position.get("execution_id")
        lifecycle_id = position.get("lifecycle_id")
        if (
            isinstance(execution_id, str)
            and isinstance(lifecycle_id, str)
            and execution_id == lifecycle_id
            and is_v2_execution_id(execution_id)
        ):
            return execution_id, False, None
        return None, False, self._failure(
            REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID,
            preflight,
            execution_id=execution_id if isinstance(execution_id, str) else None,
            lifecycle_id=lifecycle_id if isinstance(lifecycle_id, str) else None,
            errors=("existing_execution_id_lifecycle_id_required",),
        )

    def _stable_key(
        self,
        position: Mapping[str, Any],
        field: str,
        supplied: str | None,
        default: str,
        preflight: _Preflight,
        *,
        execution_id: str | None = None,
    ) -> tuple[str | None, RegistryV2PaperRuntimeResult | None]:
        stored = position.get(field)
        stored_text = _nonempty_text(stored) if stored is not None else None
        supplied_text = _nonempty_text(supplied) if supplied is not None else None
        if (stored is not None and stored_text is None) or (supplied is not None and supplied_text is None):
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=(field,),
            )
        if stored_text is not None and supplied_text is not None and stored_text != supplied_text:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=(f"{field}_conflict",),
            )
        return stored_text or supplied_text or default, None

    def _operation_key(
        self,
        supplied: str | None,
        default: str,
        preflight: _Preflight,
        execution_id: str,
    ) -> tuple[str | None, RegistryV2PaperRuntimeResult | None]:
        key = _nonempty_text(supplied) if supplied is not None else default
        if key is None:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=("idempotency_key",),
            )
        return key, None

    def _register_row(
        self,
        position: Mapping[str, Any],
        components: Mapping[str, str],
        execution_id: str,
        facts: Mapping[str, Any],
        preflight: _Preflight,
    ) -> tuple[dict[str, Any] | None, RegistryV2PaperRuntimeResult | None]:
        signal_id, signal_error = _optional_identity(position, "signal_id")
        decision_id, decision_error = _optional_identity(position, "decision_id")
        if signal_error or decision_error:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=tuple(error for error in (signal_error, decision_error) if error is not None),
            )
        metadata: dict[str, Any] = {
            "runtime_adapter": "REGISTRY_V2_PAPER_RUNTIME_ADAPTER",
            "paper_position_unit": "ONE_POSITION",
        }
        row: dict[str, Any] = {
            "execution_id": execution_id,
            "lifecycle_id": execution_id,
            "logical_trade_id": schema.build_logical_trade_id(
                components["bot"],
                components["setup"],
                components["symbol"],
                components["side"],
            ),
            "bot": components["bot"],
            "setup": components["setup"],
            "symbol": components["symbol"],
            "side": components["side"],
            "owner_type": schema.CENTRAL,
            "execution_mode": schema.PAPER,
            "registry_mode": schema.PAPER,
            "lifecycle_state": schema.OPEN,
            "execution_provenance": {
                "source": "registry_v2_paper_runtime_adapter",
                "component": "TURTLE",
            },
            "metadata": metadata,
            # Turtle has no tradable quantity.  This is an explicit PAPER
            # position-cardinality unit, never a sizing or broker quantity.
            "quantity": 1,
            "remaining_qty": 1,
            **copy.deepcopy(dict(facts)),
        }
        if "position_side" in position:
            row["position_side"] = position.get("position_side")
        if signal_id is not None:
            row["signal_id"] = signal_id
        if decision_id is not None:
            row["decision_id"] = decision_id
        if signal_id is None or decision_id is None:
            row["legacy_missing"] = True
            row["legacy_missing_marker"] = schema.LEGACY_MISSING
            metadata["legacy_missing"] = True
            metadata["legacy_missing_marker"] = schema.LEGACY_MISSING
        return row, None

    def _management_patch(
        self,
        position: Mapping[str, Any],
        event: str,
        updates: Mapping[str, Any] | None,
        preflight: _Preflight,
    ) -> tuple[dict[str, Any] | None, RegistryV2PaperRuntimeResult | None]:
        if updates is not None and not isinstance(updates, Mapping):
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("updates_mapping_required",),
            )
        update_values = copy.deepcopy(dict(updates or {}))
        forbidden = tuple(sorted(set(update_values).intersection(_IMMUTABLE_UPDATE_FIELDS)))
        if forbidden:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=tuple(f"immutable_update:{field}" for field in forbidden),
            )
        try:
            wal.canonical_json(update_values)
        except (TypeError, ValueError):
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("updates_not_json_serializable",),
            )
        patch: dict[str, Any] = {"last_event": event}
        for source, target in (
            ("status", "status"),
            ("stop", "stop_price"),
            ("tp50", "tp50_price"),
            ("tp50_hit", "tp50_hit"),
            ("be_moved", "breakeven"),
            ("mfe_pct", "mfe_pct"),
            ("mae_pct", "mae_pct"),
            ("mfe_r", "mfe_r"),
            ("mae_r", "mae_r"),
            ("best_price", "best_price"),
            ("worst_price", "worst_price"),
            ("management_cycles", "management_cycles"),
        ):
            value = position.get(source)
            if value is not None:
                patch[target] = copy.deepcopy(value)
        patch.update(update_values)
        try:
            wal.canonical_json(patch)
        except (TypeError, ValueError):
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                errors=("patch_not_json_serializable",),
            )
        return patch, None

    def _close_economics(
        self,
        exit_price: Any,
        reason: Any,
        result_pct: Any,
        result_r: Any,
        preflight: _Preflight,
        execution_id: str,
    ) -> tuple[dict[str, Any] | None, RegistryV2PaperRuntimeResult | None]:
        exit_value = _finite_number(exit_price)
        reason_text = _nonempty_text(reason)
        if exit_value is None or reason_text is None:
            return None, self._failure(
                REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                preflight,
                execution_id=execution_id,
                lifecycle_id=execution_id,
                errors=("exit_price", "close_reason"),
            )
        economics: dict[str, Any] = {
            "exit_price": exit_value,
            "close_reason": reason_text,
        }
        for field, value in (("pnl_pct", result_pct), ("realized_r", result_r)):
            if value is None:
                continue
            finite = _finite_number(value)
            if finite is None:
                return None, self._failure(
                    REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID,
                    preflight,
                    execution_id=execution_id,
                    lifecycle_id=execution_id,
                    errors=(field,),
                )
            economics[field] = finite
        return economics, None

    def _expected_identity(
        self,
        execution_id: str,
        components: Mapping[str, str],
    ) -> dict[str, str]:
        return {
            "execution_id": execution_id,
            "lifecycle_id": execution_id,
            "owner_type": schema.CENTRAL,
            "bot": components["bot"],
            "setup": components["setup"],
            "symbol": components["symbol"],
            "side": components["side"],
        }

    def _generation_for_request(
        self,
        inspection: wal.WalRecoveryInspection,
        operation: str,
        execution_id: str,
        idempotency_key: str,
    ) -> int:
        committed = [
            event
            for event in inspection.committed_events
            if event.operation == operation
            and event.execution_id == execution_id
            and event.idempotency_key == idempotency_key
        ]
        if committed:
            return committed[-1].expected_generation
        if inspection.snapshot_generation is not None:
            return inspection.snapshot_generation
        return 0

    def _core_result(
        self,
        result: wal.WalOperationResult,
        preflight: _Preflight,
        execution_id: str,
        idempotency_key: str,
        expected_generation: int,
    ) -> RegistryV2PaperRuntimeResult:
        committed = result.ok and result.state == wal.EVENT_COMMITTED
        recovery_required = result.status == wal.WAL_RECOVERY_REQUIRED
        assert preflight.inspection is not None
        return RegistryV2PaperRuntimeResult(
            result.ok,
            result.status,
            True,
            True,
            preflight.mode,
            preflight.operation,
            execution_id=execution_id,
            lifecycle_id=execution_id,
            idempotency_key_present=bool(idempotency_key),
            storage_configured=True,
            write_attempted=True,
            write_committed=committed,
            core_status=result.status,
            wal_status=preflight.inspection.status,
            event_id=result.event_id,
            event_seq=result.event_seq,
            event_state=result.state,
            expected_generation=expected_generation,
            target_generation=result.generation if result.generation is not None else expected_generation + 1,
            recovery_required=recovery_required,
            errors=tuple(result.errors),
        )

    def _failure(
        self,
        status: str,
        preflight: _Preflight,
        *,
        execution_id: str | None = None,
        lifecycle_id: str | None = None,
        idempotency_key_present: bool = False,
        errors: tuple[str, ...] = (),
    ) -> RegistryV2PaperRuntimeResult:
        inspection = preflight.inspection
        return RegistryV2PaperRuntimeResult(
            False,
            status,
            True,
            False,
            preflight.mode,
            preflight.operation,
            execution_id=execution_id,
            lifecycle_id=lifecycle_id,
            idempotency_key_present=idempotency_key_present,
            storage_configured=True,
            wal_status=inspection.status if inspection is not None else None,
            errors=errors,
        )

    @staticmethod
    def _read_from_write_failure(
        result: RegistryV2PaperRuntimeResult,
    ) -> RegistryV2PaperRuntimeReadResult:
        """Project preflight/validation failures into a no-write read envelope."""

        return RegistryV2PaperRuntimeReadResult(
            result.ok,
            result.status,
            result.enabled,
            result.eligible,
            result.mode,
            result.operation,
            execution_id=result.execution_id,
            lifecycle_id=result.lifecycle_id,
            storage_configured=result.storage_configured,
            recovery_required=result.recovery_required,
            errors=result.errors,
        )

    def _read_failure(
        self,
        status: str,
        preflight: _Preflight,
        *,
        execution_id: str | None = None,
        errors: tuple[str, ...] = (),
    ) -> RegistryV2PaperRuntimeReadResult:
        inspection = preflight.inspection
        return RegistryV2PaperRuntimeReadResult(
            False,
            status,
            True,
            False,
            preflight.mode,
            preflight.operation,
            execution_id=execution_id,
            lifecycle_id=execution_id,
            storage_configured=True,
            recovery_required=(
                status == REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED
                or status == wal.WAL_RECOVERY_REQUIRED
            ),
            errors=errors or (
                tuple(inspection.errors)
                if inspection is not None and inspection.errors
                else (status,)
            ),
        )


def get_registry_v2_paper_runtime_adapter() -> RegistryV2PaperRuntimeAdapter:
    """Build an unactivated adapter from the explicit environment settings."""

    return RegistryV2PaperRuntimeAdapter()


def _canonical_text(value: Any) -> str | None:
    text = _nonempty_text(value)
    return text.upper() if text is not None else None


def _nonempty_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _optional_identity(position: Mapping[str, Any], field: str) -> tuple[str | None, str | None]:
    value = position.get(field)
    if value is None:
        return None, None
    text = _nonempty_text(value)
    if text is None:
        if isinstance(value, str):
            return None, None
        return None, field
    return text, None


def _mode_label(execution_mode: Any, registry_mode: Any) -> str:
    execution = execution_mode if isinstance(execution_mode, str) else type(execution_mode).__name__
    registry = registry_mode if isinstance(registry_mode, str) else type(registry_mode).__name__
    return f"{execution}/{registry}"


__all__ = (
    "REGISTRY_PERSISTENCE_LOCK_TIMEOUT",
    "REGISTRY_V2_PAPER_BACKUP_DIRNAME",
    "REGISTRY_V2_PAPER_JOURNAL_FILENAME",
    "REGISTRY_V2_PAPER_LOCK_FILENAME",
    "REGISTRY_V2_PAPER_RUNTIME_CONTRACT_INVALID",
    "REGISTRY_V2_PAPER_RUNTIME_DISABLED",
    "REGISTRY_V2_PAPER_RUNTIME_IDEMPOTENCY_INVALID",
    "REGISTRY_V2_PAPER_RUNTIME_IDENTITY_INVALID",
    "REGISTRY_V2_PAPER_RUNTIME_LOCK_TIMEOUT_SECONDS",
    "REGISTRY_V2_PAPER_RUNTIME_MODE_REJECTED",
    "REGISTRY_V2_PAPER_RUNTIME_POSITION_INVALID",
    "REGISTRY_V2_PAPER_RUNTIME_RECOVERY_BLOCKED",
    "REGISTRY_V2_PAPER_RUNTIME_STORAGE_INVALID",
    "REGISTRY_V2_PAPER_RUNTIME_STORAGE_REQUIRED",
    "REGISTRY_V2_PAPER_SNAPSHOT_FILENAME",
    "REGISTRY_V2_PAPER_STORAGE_DIR_ENV",
    "REGISTRY_V2_PAPER_WRITE_ENABLED",
    "REGISTRY_V2_PAPER_WRITE_ENABLED_ENV",
    "RegistryV2PaperRuntimeAdapter",
    "RegistryV2PaperRuntimeReadResult",
    "RegistryV2PaperRuntimeResult",
    "get_registry_v2_paper_runtime_adapter",
    "parse_registry_v2_paper_write_enabled",
)
