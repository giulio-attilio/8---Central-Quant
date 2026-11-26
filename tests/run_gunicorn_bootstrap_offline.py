"""Run Gunicorn bootstrap and runtime-drain tests with network blocked."""

import os
from pathlib import Path
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
os.environ.pop("CENTRAL_AUTO_START_RUNTIME", None)

def _deny_external(*_args, **_kwargs):
    raise AssertionError("external access blocked by offline test harness")


socket.create_connection = _deny_external
socket.getaddrinfo = _deny_external
socket.socket.connect = _deny_external
socket.socket.connect_ex = _deny_external
subprocess.Popen = _deny_external


def _assert_blocked(label, callback, *args):
    try:
        callback(*args)
    except AssertionError as exc:
        if str(exc) != "external access blocked by offline test harness":
            raise
        return
    raise RuntimeError(f"offline guard not installed: {label}")


_assert_blocked(
    "socket.create_connection",
    socket.create_connection,
    ("127.0.0.1", 1),
)
_assert_blocked("socket.getaddrinfo", socket.getaddrinfo, "localhost", 1)
_assert_blocked(
    "socket.socket.connect",
    socket.socket.connect,
    None,
    ("127.0.0.1", 1),
)
_assert_blocked(
    "socket.socket.connect_ex",
    socket.socket.connect_ex,
    None,
    ("127.0.0.1", 1),
)
_assert_blocked(
    "subprocess.Popen",
    subprocess.Popen,
    [sys.executable, "-c", "pass"],
)

import pytest  # noqa: E402


raise SystemExit(pytest.main([
    "-q",
    # pytest's built-in debugger subclasses subprocess.Popen during configure;
    # disable it because this runner deliberately replaces Popen to deny child
    # processes before pytest configuration.
    "-p",
    "no:debugging",
    str(ROOT / "tests" / "test_gunicorn_runtime_bootstrap_v1.py"),
    str(ROOT / "tests" / "test_runtime_drain_v1.py"),
]))
