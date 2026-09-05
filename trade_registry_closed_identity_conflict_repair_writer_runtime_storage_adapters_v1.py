"""Default-off physical adapters for the isolated writer coordinator.

The caller must explicitly provide a storage directory and enable each adapter.
Nothing in this module knows the Central runtime path or installs itself.  Tests
can therefore exercise real OS file locking and atomic lease persistence only
inside caller-owned temporary directories.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

try:
    import msvcrt as _msvcrt
except ImportError:
    _msvcrt = None


TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_STORAGE_ADAPTERS_V1_VERSION = (
    "2026-09-04-TRADE-REGISTRY-CLOSED-IDENTITY-CONFLICT-REPAIR-WRITER-RUNTIME-STORAGE-ADAPTERS-V1"
)

_LEASE_FORMAT_VERSION = "CLOSED_REPAIR_MAINTENANCE_LEASE_FILE_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_STATES = frozenset({"REQUESTED", "DRAINING", "QUIESCED"})
_ALL_STATES = frozenset({*_ACTIVE_STATES, "RELEASED"})


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


def _validate_namespace(namespace: str) -> str:
    normalized = str(namespace or "").lower().strip()
    if not _SHA256_RE.fullmatch(normalized):
        raise RuntimeStorageAdapterBlocked("LOCK_NAMESPACE_INVALID")
    return normalized


def _validate_storage_root(storage_root: str | os.PathLike[str]) -> Path:
    root = Path(storage_root).resolve(strict=False)
    if root == Path(root.anchor):
        raise ValueError("storage_root cannot be a filesystem root")
    return root


def _strict_directory_fsync(directory: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
        os.fsync(descriptor)
    except Exception as exc:
        raise RuntimeStorageAdapterBlocked("DIRECTORY_FSYNC_FAILED") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


class RuntimeStorageAdapterBlocked(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InterprocessFileLockHandleV1:
    """Own one locked file descriptor until an explicit release."""

    def __init__(self, file_obj: BinaryIO, platform: str) -> None:
        self._file_obj = file_obj
        self._platform = platform
        self._released = False

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        if self._released:
            raise RuntimeStorageAdapterBlocked("LOCK_ALREADY_RELEASED")
        try:
            if self._platform == "POSIX":
                if _fcntl is None:
                    raise RuntimeStorageAdapterBlocked("POSIX_LOCK_UNAVAILABLE")
                _fcntl.flock(self._file_obj.fileno(), _fcntl.LOCK_UN)
            elif self._platform == "WINDOWS":
                if _msvcrt is None:
                    raise RuntimeStorageAdapterBlocked("WINDOWS_LOCK_UNAVAILABLE")
                self._file_obj.seek(0)
                _msvcrt.locking(self._file_obj.fileno(), _msvcrt.LK_UNLCK, 1)
            else:
                raise RuntimeStorageAdapterBlocked("PLATFORM_LOCK_UNAVAILABLE")
        except RuntimeStorageAdapterBlocked:
            raise
        except Exception as exc:
            raise RuntimeStorageAdapterBlocked("LOCK_RELEASE_FAILED") from exc
        finally:
            self._file_obj.close()
            self._released = True


class CrossPlatformInterprocessFileLockBackendV1:
    """OS advisory lock backend; unavailable platforms fail closed."""

    def __init__(
        self,
        storage_root: str | os.PathLike[str],
        *,
        enabled: bool = False,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        poll_interval_seconds: float = 0.01,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._root = _validate_storage_root(storage_root)
        self._enabled = bool(enabled)
        self._monotonic = monotonic or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._poll_interval = float(poll_interval_seconds)
        if self._enabled:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def storage_root(self) -> Path:
        return self._root

    def _platform(self) -> str:
        if _fcntl is not None:
            return "POSIX"
        if _msvcrt is not None:
            return "WINDOWS"
        raise RuntimeStorageAdapterBlocked("PLATFORM_LOCK_UNAVAILABLE")

    def _try_lock(self, file_obj: BinaryIO, platform: str) -> bool:
        try:
            if platform == "POSIX":
                _fcntl.flock(
                    file_obj.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB
                )
            elif platform == "WINDOWS":
                file_obj.seek(0)
                _msvcrt.locking(file_obj.fileno(), _msvcrt.LK_NBLCK, 1)
            else:
                raise RuntimeStorageAdapterBlocked("PLATFORM_LOCK_UNAVAILABLE")
            return True
        except (BlockingIOError, PermissionError):
            return False
        except OSError:
            return False

    def acquire(
        self, namespace: str, timeout_seconds: float
    ) -> InterprocessFileLockHandleV1 | None:
        if not self._enabled:
            return None
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        normalized = _validate_namespace(namespace)
        platform = self._platform()
        lock_path = self._root / f"{normalized}.writer.lock"
        try:
            file_obj = lock_path.open("a+b")
            os.chmod(lock_path, 0o600)
            file_obj.seek(0, os.SEEK_END)
            if file_obj.tell() == 0:
                file_obj.write(b"\0")
                file_obj.flush()
            file_obj.seek(0)
        except Exception as exc:
            raise RuntimeStorageAdapterBlocked("LOCK_FILE_OPEN_FAILED") from exc

        deadline = self._monotonic() + float(timeout_seconds)
        try:
            while True:
                if self._try_lock(file_obj, platform):
                    return InterprocessFileLockHandleV1(file_obj, platform)
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    file_obj.close()
                    return None
                self._sleeper(min(self._poll_interval, remaining))
        except Exception:
            file_obj.close()
            raise


class DurableJsonMaintenanceLeaseStoreV1:
    """Hash-bound atomic JSON lease store with strict durability callback."""

    def __init__(
        self,
        storage_root: str | os.PathLike[str],
        *,
        enabled: bool = False,
        directory_fsync: Callable[[Path], None] | None = None,
        replacer: Callable[[str, str], None] | None = None,
        monotonic: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        replace_timeout_seconds: float = 0.5,
        replace_poll_interval_seconds: float = 0.01,
    ) -> None:
        if replace_timeout_seconds <= 0 or replace_poll_interval_seconds <= 0:
            raise ValueError("replace timeout and poll interval must be positive")
        self._root = _validate_storage_root(storage_root)
        self._enabled = bool(enabled)
        self._directory_fsync = directory_fsync or _strict_directory_fsync
        self._replacer = replacer or os.replace
        self._monotonic = monotonic or time.monotonic
        self._sleeper = sleeper or time.sleep
        self._replace_timeout = float(replace_timeout_seconds)
        self._replace_poll_interval = float(replace_poll_interval_seconds)
        if self._enabled:
            self._root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def storage_root(self) -> Path:
        return self._root

    def _path(self, namespace: str) -> Path:
        return self._root / f"{_validate_namespace(namespace)}.lease.json"

    def _validate_lease(self, lease: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(lease, Mapping):
            raise RuntimeStorageAdapterBlocked("LEASE_PAYLOAD_INVALID")
        value = json.loads(_canonical_json(dict(lease)))
        state = str(value.get("state") or "").upper().strip()
        if state not in _ALL_STATES:
            raise RuntimeStorageAdapterBlocked("LEASE_STATE_INVALID")
        value["state"] = state
        epoch = str(value.get("maintenance_epoch") or "").lower().strip()
        if state in _ACTIVE_STATES and not _SHA256_RE.fullmatch(epoch):
            raise RuntimeStorageAdapterBlocked("LEASE_EPOCH_INVALID")
        if epoch and not _SHA256_RE.fullmatch(epoch):
            raise RuntimeStorageAdapterBlocked("LEASE_EPOCH_INVALID")
        if epoch:
            value["maintenance_epoch"] = epoch
        writer_count = value.get("registered_writer_count")
        if writer_count is not None and int(writer_count) != 19:
            raise RuntimeStorageAdapterBlocked("LEASE_WRITER_COUNT_INVALID")
        return value

    def _replace_with_deadline(self, source: Path, target: Path) -> None:
        deadline = self._monotonic() + self._replace_timeout
        while True:
            try:
                self._replacer(str(source), str(target))
                return
            except PermissionError as exc:
                remaining = deadline - self._monotonic()
                if remaining <= 0:
                    raise RuntimeStorageAdapterBlocked(
                        "LEASE_ATOMIC_REPLACE_TIMEOUT"
                    ) from exc
                self._sleeper(min(self._replace_poll_interval, remaining))

    def read(self, namespace: str) -> Mapping[str, Any] | None:
        if not self._enabled:
            return None
        normalized = _validate_namespace(namespace)
        path = self._path(normalized)
        if not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeStorageAdapterBlocked("LEASE_FILE_READ_FAILED") from exc
        if not isinstance(envelope, Mapping):
            raise RuntimeStorageAdapterBlocked("LEASE_ENVELOPE_INVALID")
        lease = envelope.get("lease")
        supplied_sha = str(envelope.get("lease_sha256") or "").lower().strip()
        expected_sha = _stable_sha256(lease) if isinstance(lease, Mapping) else ""
        if (
            envelope.get("format_version") != _LEASE_FORMAT_VERSION
            or envelope.get("lock_namespace_sha256") != normalized
            or not _SHA256_RE.fullmatch(supplied_sha)
            or not expected_sha
            or not hmac.compare_digest(supplied_sha, expected_sha)
        ):
            raise RuntimeStorageAdapterBlocked("LEASE_ENVELOPE_INTEGRITY_FAILED")
        return self._validate_lease(lease)

    def write(self, namespace: str, lease: Mapping[str, Any]) -> None:
        if not self._enabled:
            raise RuntimeStorageAdapterBlocked("LEASE_STORE_DEFAULT_OFF")
        normalized = _validate_namespace(namespace)
        value = self._validate_lease(lease)
        envelope = {
            "format_version": _LEASE_FORMAT_VERSION,
            "lock_namespace_sha256": normalized,
            "lease": value,
            "lease_sha256": _stable_sha256(value),
        }
        path = self._path(normalized)
        temp_path: Path | None = None
        try:
            descriptor, raw_temp_path = tempfile.mkstemp(
                prefix=f".{normalized}.", suffix=".lease.tmp", dir=str(self._root)
            )
            temp_path = Path(raw_temp_path)
            with os.fdopen(descriptor, "w", encoding="utf-8") as file_obj:
                file_obj.write(_canonical_json(envelope))
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.chmod(temp_path, 0o600)
            self._replace_with_deadline(temp_path, path)
            temp_path = None
            self._directory_fsync(self._root)
        except RuntimeStorageAdapterBlocked:
            raise
        except Exception as exc:
            raise RuntimeStorageAdapterBlocked("LEASE_FILE_WRITE_FAILED") from exc
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass


__all__ = [
    "TRADE_REGISTRY_CLOSED_IDENTITY_CONFLICT_REPAIR_WRITER_RUNTIME_STORAGE_ADAPTERS_V1_VERSION",
    "CrossPlatformInterprocessFileLockBackendV1",
    "DurableJsonMaintenanceLeaseStoreV1",
    "InterprocessFileLockHandleV1",
    "RuntimeStorageAdapterBlocked",
]
