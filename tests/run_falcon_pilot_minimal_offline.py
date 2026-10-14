"""Run the existing Falcon safety regressions without external access.

Usage: python3 -I tests/run_falcon_pilot_minimal_offline.py
This process does not import main.py or start a service. Pytest is loaded only
after network, subprocess and secret-file access have been denied.
"""

import builtins
import http.client
import inspect
import io
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request


class OfflineBoundaryViolation(BaseException):
    pass


def forbidden(*args, **kwargs):
    raise OfflineBoundaryViolation("offline boundary violated")


def guarded_socket(*args, **kwargs):
    # urllib3 probes IPv6 support while importing ccxt. Report unavailable
    # without creating a socket; every other socket attempt still fails hard.
    caller = inspect.currentframe().f_back
    if (
        caller.f_code.co_name == "_has_ipv6"
        and Path(caller.f_code.co_filename).as_posix().endswith("urllib3/util/connection.py")
        and args == (socket.AF_INET6,)
        and not kwargs
    ):
        raise OSError("IPv6 capability probe disabled in offline tests")
    forbidden()


def guarded_open(original):
    def opener(path, *args, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)) and Path(path).name.lower().startswith(".env"):
            raise OfflineBoundaryViolation("secret file access denied")
        return original(path, *args, **kwargs)
    return opener


socket.socket = guarded_socket
socket.create_connection = forbidden
socket.getaddrinfo = forbidden
socket.gethostbyname = forbidden
http.client.HTTPConnection.connect = forbidden
http.client.HTTPSConnection.connect = forbidden
urllib.request.urlopen = forbidden
subprocess.Popen = forbidden
subprocess.run = forbidden
os.system = forbidden
builtins.open = guarded_open(builtins.open)
io.open = guarded_open(io.open)
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

import pytest  # noqa: E402 - only after guards


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASES = (
    "test_falcon_single_live_execution_path_v1.py",
    "test_falcon_management_safety_v1.py",
    "test_falcon_real_position_ownership_limit_v1.py",
    "test_falcon_real_pilot_preflight_fail_closed_v1.py",
    "test_main_real_pilot_guard_fail_closed_v1.py",
    "test_account_client_order_id_v1.py",
    "test_account_client_order_writer_contract_v1.py",
)
EXTRA_CASES = (
    "test_trade_lifecycle_shadow_runtime_adapter.py",
    "test_registry_remaining_writers_atomic_rmw_v1.py",
    "test_falcon_central_only_reconciliation.py",
    "test_broker_order_constraints_fail_closed_v1.py",
    "test_broker_account_client_order_boundary_v1.py",
)


if __name__ == "__main__":
    cases = EXTRA_CASES if sys.argv[1:] == ["--extra"] else CASES
    filters = ["-k", "not test_shadow_validation_append_is_idempotent_across_processes"] if cases is EXTRA_CASES else []
    raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", *filters, *(str(ROOT / "tests" / name) for name in cases)]))
