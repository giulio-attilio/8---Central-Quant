"""Run only the isolated candidate's reviewed offline validation suite."""
import sys
from c3_linux_lab import verify_isolation


def inside(parent_netns):
    verify_isolation(parent_netns)
    import os
    import socket
    import subprocess

    def forbidden(*_args, **_kwargs):
        raise AssertionError("candidate lab forbids network and child execution")

    class ForbiddenSocket(socket.socket):
        def __new__(cls, *_args, **_kwargs):
            return forbidden()

    prefix = "trade_registry_closed_identity_conflict_repair_"
    denied = {"main", "trade_registry", "broker", "bots"} | {
        prefix + name for name in (
            "runtime_seam_v1", "production_provider_v1",
            "raw_transaction_store_production_v1", "writer_invocation_adapter_v1",
            "writer_runtime_coordinator_v1",
        )
    }

    class SourceOnlyRuntimeBlocked:
        def find_spec(self, fullname, _path=None, _target=None):
            if (fullname.split(".")[0] in denied
                    or fullname.startswith(prefix + "runtime_production_")):
                raise AssertionError("source-only runtime import forbidden: " + fullname)
            return None

    def audit(event, _args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            forbidden()

    socket.socket = ForbiddenSocket
    socket.create_connection = forbidden
    socket.getaddrinfo = forbidden
    subprocess.Popen = forbidden
    os.system = forbidden
    sys.addaudithook(audit)
    sys.meta_path.insert(0, SourceOnlyRuntimeBlocked())
    sys.path.insert(0, "/work")
    import pytest

    raise SystemExit(pytest.main([
        "-q", "-rs", "--noconftest", "--runxfail", "-p", "no:cacheprovider",
        "--basetemp=/scratch/pytest", "--junitxml=/scratch/candidate-results.xml",
        "tests/test_falcon_real_pilot_preflight_fail_closed_v1.py",
        "tests/test_trade_registry_live_entry_storage_readiness_v1.py",
        "tests/test_" + prefix + "runtime_readiness_binding_v1.py",
        "tests/test_" + prefix + "runtime_readiness_preflight_patch_plan_v1.py",
        "tests/test_" + prefix + "runtime_static_preflight_v1.py",
        "tests/test_c3_preflight_candidate_integrity.py",
    ]))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "inside":
        raise SystemExit("explicit isolated inside mode required")
    inside(sys.argv[2])
