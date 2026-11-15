"""Shared in-process coordination and durable JSON writes for PAPER state."""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


# Render currently runs one service instance. This lock serializes read/modify/write
# operations among the PAPER executor, lifecycle, and outcome evaluator threads.
# It intentionally does not claim cross-process or distributed coordination.
PAPER_STATE_LOCK = threading.RLock()


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


def read_paper_positions_state(path: Path):
    """Return positions plus an explicit state status; missing is never empty."""
    target = Path(path)
    if not target.is_file():
        return None, "PAPER_STATE_FILES_MISSING"
    try:
        positions = json.loads(target.read_text(encoding="utf-8"))
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
