"""Shared in-process coordination and durable JSON writes for PAPER state."""

import json
import os
import stat
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, TextIO


# Render currently runs one service instance. This lock serializes read/modify/write
# operations among the PAPER executor, lifecycle, and outcome evaluator threads.
# It intentionally does not claim cross-process or distributed coordination.
PAPER_STATE_LOCK = threading.RLock()


def paper_data_mount_verified(
    path: Path,
    *,
    platform_name: str | None = None,
    data_root: Path = Path("/data"),
) -> bool:
    """Require Render's persistent mount for any state path under /data."""
    if (platform_name or os.name) == "nt":
        return True
    root = Path(data_root)
    target = Path(path)
    try:
        lexical_root = Path(os.path.abspath(os.fspath(root)))
        lexical_target = Path(os.path.abspath(os.fspath(target)))
        relative_target = lexical_target.relative_to(lexical_root)
    except ValueError:
        # Paths outside the configured persistent root may be local test data.
        # Do not allow a lexical path outside the root to alias back into /data.
        if os.environ.get("RENDER", "").strip().lower() == "true":
            # On Render, a PAPER path outside the persistent mount is never a
            # valid production fallback, even if it is otherwise a normal path.
            return False
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError:
            return True
        except (OSError, RuntimeError):
            return False
        return False
    except (OSError, RuntimeError):
        return False

    try:
        # The mountpoint itself must be a real directory, not a symlink to a
        # different filesystem (including a separately mounted ephemeral path).
        if root.is_symlink() or not root.is_dir():
            return False
        root_resolved = root.resolve()
        target_resolved = target.resolve()
        if target_resolved != root_resolved and root_resolved not in target_resolved.parents:
            return False
        if not os.path.ismount(str(root)):
            return False

        root_device = root.stat().st_dev
        current = root
        for component in relative_target.parts:
            current = current / component
            try:
                current_stat = current.lstat()
            except FileNotFoundError:
                # Continue lexically so a later existing component cannot hide
                # an intermediate symlink in a partially-created path.
                continue
            if stat.S_ISLNK(current_stat.st_mode) or current_stat.st_dev != root_device:
                return False
        return True
    except OSError:
        return False
    except RuntimeError:
        # Path resolution can report a symlink loop as RuntimeError on some
        # supported Python/platform combinations.
        return False


def ensure_paper_data_dir(path: Path) -> bool:
    """Create local/PAPER storage only when its persistent mount is verified."""
    target = Path(path)
    if not paper_data_mount_verified(target):
        return False
    if os.name != "nt":
        absolute = Path(os.path.abspath(os.fspath(target)))
        try:
            absolute.relative_to(Path("/data"))
        except ValueError:
            if os.environ.get("RENDER", "").strip().lower() == "true":
                return False
        else:
            parent_fd = root_fd = -1
            try:
                parent_fd, _name, root_fd, _device, _mount_id = _open_parent_under_root(
                    absolute / ".paper-dir-check",
                    Path("/data"),
                    create_parent=True,
                    require_mount=True,
                )
                return True
            except OSError:
                return False
            finally:
                if parent_fd >= 0:
                    os.close(parent_fd)
                if root_fd >= 0:
                    os.close(root_fd)
    target.mkdir(parents=True, exist_ok=True)
    return True


def resolve_paper_data_dir(module_file: str) -> Path:
    """Resolve shared PAPER storage without falling back ahead of Render /data."""
    configured = os.environ.get("CENTRAL_DATA_DIR") or os.environ.get("DATA_DIR")
    if configured:
        return Path(configured)
    try:
        if os.path.isdir("/data"):
            return Path("/data")
    except Exception:
        pass
    return Path(module_file).resolve().parent / "data"


def _mount_id_for_fd(fd: int) -> int:
    """Return Linux's mount ID for an already-open descriptor, fail closed."""
    if os.name == "nt":
        raise OSError("PAPER_MOUNT_ID_UNAVAILABLE")
    try:
        with open(f"/proc/self/fdinfo/{fd}", "r", encoding="ascii") as info:
            for line in info:
                if line.startswith("mnt_id:"):
                    return int(line.split(":", 1)[1].strip())
    except (OSError, ValueError) as exc:
        raise OSError("PAPER_MOUNT_ID_UNAVAILABLE") from exc
    raise OSError("PAPER_MOUNT_ID_UNAVAILABLE")


def _open_parent_under_root(
    path: Path,
    root: Path,
    *,
    create_parent: bool = False,
    require_mount: bool = True,
) -> tuple[int, str, int, int, int]:
    """Open a file's parent by dir_fd, rejecting symlinks and mount changes.

    ``require_mount`` is false only for isolated filesystem tests. Production
    callers use /data and require it to be a distinct mount from the root FS.
    The returned descriptors are owned by the caller.
    """
    if os.name == "nt":
        raise OSError("PAPER_DIRFD_UNAVAILABLE")
    root_path = Path(os.path.abspath(os.fspath(root)))
    target = Path(os.path.abspath(os.fspath(path)))
    try:
        relative = target.relative_to(root_path)
    except ValueError as exc:
        raise OSError("PAPER_PATH_OUTSIDE_DATA_ROOT") from exc
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise OSError("PAPER_PATH_INVALID")

    if require_mount and not paper_data_mount_verified(target, data_root=root_path):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")

    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    root_fd = os.open(str(root_path), directory_flags)
    parent_fd = -1
    try:
        root_stat = os.fstat(root_fd)
        root_mount_id = _mount_id_for_fd(root_fd)
        if require_mount:
            filesystem_root_fd = os.open("/", directory_flags)
            try:
                filesystem_root_stat = os.fstat(filesystem_root_fd)
                if (
                    filesystem_root_stat.st_dev == root_stat.st_dev
                    or _mount_id_for_fd(filesystem_root_fd) == root_mount_id
                ):
                    raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
            finally:
                os.close(filesystem_root_fd)

        parent_fd = os.dup(root_fd)
        for component in relative.parts[:-1]:
            try:
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                if not create_parent:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                next_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            try:
                component_stat = os.fstat(next_fd)
                if component_stat.st_dev != root_stat.st_dev:
                    raise OSError("PAPER_NESTED_DEVICE_REJECTED")
                if _mount_id_for_fd(next_fd) != root_mount_id:
                    raise OSError("PAPER_NESTED_MOUNT_REJECTED")
            except Exception:
                os.close(next_fd)
                raise
            os.close(parent_fd)
            parent_fd = next_fd

        return parent_fd, relative.parts[-1], root_fd, root_stat.st_dev, root_mount_id
    except Exception:
        if parent_fd >= 0:
            os.close(parent_fd)
        os.close(root_fd)
        raise


def _open_fd_under_root(
    path: Path,
    root: Path,
    flags: int,
    *,
    mode: int = 0o600,
    create_parent: bool = False,
    require_mount: bool = True,
) -> int:
    """Open a regular file relative to a verified directory descriptor."""
    parent_fd, name, root_fd, root_device, root_mount_id = _open_parent_under_root(
        path,
        root,
        create_parent=create_parent,
        require_mount=require_mount,
    )
    try:
        nofollow_flags = flags | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        file_fd = os.open(name, nofollow_flags, mode, dir_fd=parent_fd)
        try:
            file_stat = os.fstat(file_fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise OSError("PAPER_FILE_NOT_REGULAR")
            if file_stat.st_dev != root_device:
                raise OSError("PAPER_FILE_DEVICE_REJECTED")
            if _mount_id_for_fd(file_fd) != root_mount_id:
                raise OSError("PAPER_FILE_MOUNT_REJECTED")
            return file_fd
        except Exception:
            os.close(file_fd)
            raise
    finally:
        os.close(parent_fd)
        os.close(root_fd)


def open_paper_text(path: Path, mode: str = "r", *, encoding: str = "utf-8") -> TextIO:
    """Open PAPER text safely; Render /data accesses are descriptor-anchored."""
    target = Path(path)
    if not paper_data_mount_verified(target):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    if os.name == "nt":
        return target.open(mode, encoding=encoding)

    absolute = Path(os.path.abspath(os.fspath(target)))
    data_root = Path("/data")
    try:
        absolute.relative_to(data_root)
    except ValueError:
        if os.environ.get("RENDER", "").strip().lower() == "true":
            raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
        return target.open(mode, encoding=encoding)

    if mode == "r":
        flags = os.O_RDONLY
    elif mode == "a":
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    else:
        raise ValueError("PAPER_TEXT_MODE_UNSUPPORTED")
    fd = _open_fd_under_root(absolute, data_root, flags, mode=0o600, create_parent=mode == "a")
    try:
        return os.fdopen(fd, mode, encoding=encoding)
    except Exception:
        os.close(fd)
        raise


def open_paper_binary(
    path: Path,
    mode: str = "rb",
    *,
    data_root: Path = Path("/data"),
    require_mount: bool = True,
):
    """Open PAPER bytes safely; intended for bounded scanners and snapshots."""
    target = Path(path)
    if require_mount and not paper_data_mount_verified(target, data_root=data_root):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    if os.name == "nt":
        return target.open(mode)

    absolute = Path(os.path.abspath(os.fspath(target)))
    data_root = Path(data_root)
    try:
        absolute.relative_to(data_root)
    except ValueError:
        if os.environ.get("RENDER", "").strip().lower() == "true":
            raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
        return target.open(mode)

    if mode == "rb":
        flags = os.O_RDONLY
    elif mode == "ab":
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    elif mode == "r+b":
        flags = os.O_RDWR
    elif mode == "a+b":
        flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    else:
        raise ValueError("PAPER_BINARY_MODE_UNSUPPORTED")
    fd = _open_fd_under_root(
        absolute,
        data_root,
        flags,
        mode=0o600,
        create_parent=mode in {"ab", "a+b"},
        require_mount=require_mount,
    )
    try:
        return os.fdopen(fd, mode)
    except Exception:
        os.close(fd)
        raise


def read_paper_text(
    path: Path,
    *,
    encoding: str = "utf-8",
    max_bytes: int | None = None,
) -> str:
    if max_bytes is None:
        with open_paper_text(path, "r", encoding=encoding) as handle:
            return handle.read()
    if max_bytes < 0:
        raise ValueError("PAPER_FILE_SIZE_LIMIT_INVALID")
    with open_paper_binary(path, "rb") as handle:
        if os.fstat(handle.fileno()).st_size > max_bytes:
            raise OSError("PAPER_FILE_SIZE_LIMIT_EXCEEDED")
        raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise OSError("PAPER_FILE_SIZE_LIMIT_EXCEEDED")
        return raw.decode(encoding)


def append_paper_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    with open_paper_text(path, "a", encoding=encoding) as handle:
        handle.write(content)
        handle.flush()
        if os.name != "nt":
            os.fsync(handle.fileno())


def paper_file_exists(
    path: Path,
    *,
    data_root: Path = Path("/data"),
    require_mount: bool = True,
) -> bool:
    """Check a PAPER file without following symlinks under the Render disk."""
    target = Path(path)
    if require_mount and not paper_data_mount_verified(target, data_root=data_root):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    absolute = Path(os.path.abspath(os.fspath(target)))
    data_root = Path(data_root)
    try:
        absolute.relative_to(data_root)
    except ValueError:
        if os.environ.get("RENDER", "").strip().lower() == "true":
            raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
        return target.is_file()

    parent_fd = -1
    root_fd = -1
    try:
        parent_fd, name, root_fd, _device, _mount_id = _open_parent_under_root(
            absolute, data_root, create_parent=False, require_mount=require_mount
        )
        try:
            info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(info.st_mode):
            raise OSError("PAPER_SYMLINK_REJECTED")
        if not stat.S_ISREG(info.st_mode):
            raise OSError("PAPER_FILE_NOT_REGULAR")
        return True
    except FileNotFoundError:
        return False
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
        if root_fd >= 0:
            os.close(root_fd)


def write_paper_bytes_atomically(
    path: Path,
    content: bytes,
    *,
    after_temp_fsync: Callable[[], None] | None = None,
    data_root: Path = Path("/data"),
    require_mount: bool = True,
) -> None:
    """Durably replace one PAPER file, anchoring Render /data operations by fd."""
    target = Path(path)
    if not isinstance(content, bytes):
        raise TypeError("PAPER_CONTENT_BYTES_REQUIRED")
    if require_mount and not paper_data_mount_verified(target, data_root=data_root):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    absolute = Path(os.path.abspath(os.fspath(target)))
    data_root = Path(data_root)
    try:
        absolute.relative_to(data_root)
    except ValueError:
        if os.environ.get("RENDER", "").strip().lower() == "true":
            raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{target.name}.", suffix=".tmp",
                dir=str(target.parent), delete=False
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if after_temp_fsync is not None:
                after_temp_fsync()
            os.replace(str(temp_path), str(target))
            temp_path = None
            _fsync_directory(target.parent)
            return
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    parent_fd = -1
    root_fd = -1
    temp_name = None
    try:
        parent_fd, target_name, root_fd, _device, _mount_id = _open_parent_under_root(
            absolute,
            data_root,
            create_parent=True,
            require_mount=require_mount,
        )
        for _attempt in range(5):
            candidate = f".{target_name}.{uuid.uuid4().hex}.tmp"
            try:
                fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                temp_name = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError("PAPER_TEMP_FILE_COLLISION")
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if after_temp_fsync is not None:
            after_temp_fsync()
        os.replace(temp_name, target_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp_name = None
        os.fsync(parent_fd)
    finally:
        if temp_name is not None and parent_fd >= 0:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd >= 0:
            os.close(parent_fd)
        if root_fd >= 0:
            os.close(root_fd)


def fsync_paper_directory(
    path: Path,
    *,
    data_root: Path = Path("/data"),
    require_mount: bool = True,
) -> None:
    """Fsync a PAPER directory without following /data symlinks."""
    target = Path(path)
    if require_mount and not paper_data_mount_verified(target, data_root=data_root):
        raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
    absolute = Path(os.path.abspath(os.fspath(target)))
    data_root = Path(data_root)
    try:
        absolute.relative_to(data_root)
    except ValueError:
        if os.environ.get("RENDER", "").strip().lower() == "true":
            raise OSError("PAPER_DATA_MOUNT_NOT_VERIFIED")
        _fsync_directory(target)
        return
    parent_fd = -1
    root_fd = -1
    try:
        parent_fd, _name, root_fd, _device, _mount_id = _open_parent_under_root(
            absolute / ".paper-fsync-anchor",
            data_root,
            create_parent=False,
            require_mount=require_mount,
        )
        os.fsync(parent_fd)
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
        if root_fd >= 0:
            os.close(root_fd)


def _write_json_atomically_under_data(
    path: Path,
    payload: Any,
    *,
    data_root: Path = Path("/data"),
    require_mount: bool = True,
) -> bool:
    parent_fd = -1
    root_fd = -1
    temp_name = None
    try:
        parent_fd, target_name, root_fd, _root_device, _root_mount_id = _open_parent_under_root(
            path,
            data_root,
            create_parent=True,
            require_mount=require_mount,
        )
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        for _attempt in range(5):
            candidate = f".{target_name}.{uuid.uuid4().hex}.tmp"
            try:
                fd = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                temp_name = candidate
                break
            except FileExistsError:
                continue
        else:
            raise OSError("PAPER_TEMP_FILE_COLLISION")

        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temp_name,
            target_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temp_name = None
        os.fsync(parent_fd)
        return True
    except Exception:
        return False
    finally:
        if temp_name is not None and parent_fd >= 0:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd >= 0:
            os.close(parent_fd)
        if root_fd >= 0:
            os.close(root_fd)


def read_paper_positions_state(path: Path):
    """Return positions plus an explicit state status; missing is never empty."""
    target = Path(path)
    if not paper_data_mount_verified(target):
        return None, "PAPER_DATA_MOUNT_NOT_VERIFIED"
    if not target.is_file():
        return None, "PAPER_STATE_FILES_MISSING"
    try:
        positions = json.loads(read_paper_text(target, encoding="utf-8"))
    except Exception:
        return None, "PAPER_STATE_FILES_INVALID"
    if not isinstance(positions, list) or any(
        not isinstance(position, dict)
        or position.get("status") not in {"OPEN", "CLOSED"}
        for position in positions
    ):
        return None, "PAPER_STATE_FILES_INVALID"
    return positions, "PAPER_STATE_FILES_PRESENT"


def _fsync_directory(path: Path) -> None:
    """Persist a replaced directory entry where POSIX exposes directory fsync."""
    if os.name == "nt":
        # Windows does not provide the same portable directory-fsync contract.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(str(path), flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def write_json_atomically(path: Path, payload: Any) -> bool:
    """Write JSON to a unique same-directory temp file and durably replace it."""
    target = Path(path)
    if not paper_data_mount_verified(target):
        return False
    if os.name != "nt":
        absolute = Path(os.path.abspath(os.fspath(target)))
        try:
            absolute.relative_to(Path("/data"))
        except ValueError:
            if os.environ.get("RENDER", "").strip().lower() == "true":
                return False
        else:
            return _write_json_atomically_under_data(absolute, payload)
    temp_path = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(target))
        temp_path = None
        _fsync_directory(target.parent)
        return True
    except Exception:
        # A directory-fsync failure after replace means the file may be visible,
        # but crash durability is uncertain; callers must fail closed.
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        return False
