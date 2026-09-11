"""Explicit entrypoint for preflight tests inside the existing sealed Linux lab."""

import sys

from c3_linux_lab import verify_isolation


def inside(parent_netns):
    verify_isolation(parent_netns)
    import os
    import socket
    import subprocess

    def forbidden(*_args, **_kwargs):
        raise AssertionError("preflight lab forbids network and child processes")

    class ForbiddenSocket(socket.socket):
        def __new__(cls, *_args, **_kwargs):
            return forbidden()

    socket.socket = ForbiddenSocket
    socket.create_connection = forbidden
    socket.getaddrinfo = forbidden
    subprocess.Popen = forbidden
    os.system = forbidden
    sys.path.insert(0, "/work")
    import pytest

    raise SystemExit(pytest.main([
        "-q", "-rs", "--noconftest", "-p", "no:cacheprovider",
        "--basetemp=/scratch/pytest", "--junitxml=/scratch/preflight-results.xml",
        "tests/test_falcon_real_pilot_preflight_fail_closed_v1.py",
        "tests/test_trade_registry_live_entry_storage_readiness_v1.py",
    ]))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "inside":
        raise SystemExit("explicit isolated inside mode required")
    inside(sys.argv[2])
