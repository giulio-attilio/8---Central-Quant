"""Offline, synthetic Registry persistence check across fresh Python processes.

Run directly with the project interpreter, not from the sealed offline pytest
runner (which intentionally forbids subprocess creation):

    python -I tests/helpers/personal_registry_process_restart_probe_v1.py

The child processes deny socket creation/name resolution before importing the
project module, use a minimal environment, and operate only in TemporaryDirectory.
This checks process-restart readability on the current filesystem; it does not
prove POSIX directory-fsync or production-disk durability.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile


def _deny_network(*_args, **_kwargs):
    raise RuntimeError("network access denied by Registry restart probe")


def _deny_network_before_project_import() -> None:
    socket.socket = _deny_network
    socket.create_connection = _deny_network
    socket.getaddrinfo = _deny_network
    socket.gethostbyname = _deny_network


def _child(mode: str, repository_root: Path, registry_file: Path) -> int:
    _deny_network_before_project_import()
    sys.path.insert(0, str(repository_root))
    import trade_registry

    if mode == "write":
        payload = {
            "open_trades": {
                "PROCESS_RESTART_PROBE": {"status": "OPEN", "bot": "SYNTHETIC"}
            },
            "closed_trades": [],
        }
        if Path(trade_registry.TRADE_REGISTRY_FILE) != registry_file:
            raise AssertionError("child Registry target differs from the temporary target")
        if trade_registry.save_registry(payload) is not True:
            raise AssertionError("synthetic Registry write was not acknowledged")
        print("writer_process=PASS")
        return 0

    if mode == "read":
        payload = trade_registry.load_registry()
        trade = payload.get("open_trades", {}).get("PROCESS_RESTART_PROBE", {})
        if trade.get("status") != "OPEN" or trade.get("bot") != "SYNTHETIC":
            raise AssertionError("fresh process could not read the persisted sentinel")
        print("fresh_reader_process=PASS; sentinel=PROCESS_RESTART_PROBE")
        return 0

    raise ValueError("unsupported child mode")


def _run_child(mode: str, repository_root: Path, registry_file: Path) -> None:
    environment = {
        "CENTRAL_DATA_DIR": str(registry_file.parent),
        "DATA_DIR": str(registry_file.parent),
        "TRADE_REGISTRY_FILE": str(registry_file),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # Windows Python startup can require SYSTEMROOT even in isolated mode.
    if os.name == "nt" and os.environ.get("SYSTEMROOT"):
        environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--child",
            mode,
            str(repository_root),
            str(registry_file),
        ],
        cwd=str(repository_root),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{mode} child failed ({result.returncode}): {result.stderr.strip()}"
        )
    print(result.stdout.strip())


def main() -> int:
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        return _child(sys.argv[2], Path(sys.argv[3]).resolve(), Path(sys.argv[4]).resolve())
    if len(sys.argv) != 1:
        raise SystemExit("usage: python -I tests/helpers/personal_registry_process_restart_probe_v1.py")

    _deny_network_before_project_import()
    repository_root = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="cq-registry-process-probe-") as temporary_root:
        registry_file = Path(temporary_root) / "trade_registry.json"
        _run_child("write", repository_root, registry_file)
        if not registry_file.is_file() or registry_file.stat().st_size <= 0:
            raise AssertionError("temporary Registry file missing or empty")
        _run_child("read", repository_root, registry_file)
        print(f"temporary_registry_bytes={registry_file.stat().st_size}")
    print("temporary_probe_cleanup=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
