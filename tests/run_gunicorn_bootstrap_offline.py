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

import pytest  # noqa: E402


def _deny_external(*_args, **_kwargs):
    raise AssertionError("external access blocked by offline test harness")


socket.create_connection = _deny_external
socket.getaddrinfo = _deny_external
socket.socket.connect = _deny_external
socket.socket.connect_ex = _deny_external
subprocess.Popen = _deny_external


raise SystemExit(pytest.main([
    "-q",
    str(ROOT / "tests" / "test_gunicorn_runtime_bootstrap_v1.py"),
    str(ROOT / "tests" / "test_runtime_drain_v1.py"),
]))
