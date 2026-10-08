"""Portable offline ledger probes. Only the fixed synthetic child may execute.

These test process interruption, not hardware power loss or full runtime startup.
"""

from contextlib import closing
import importlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest


@pytest.fixture
def probe(tmp_path, monkeypatch, request):
    def denied(*_a, **_kw):
        raise AssertionError("external access forbidden")
    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    original_popen = subprocess.Popen
    kind = getattr(request, "param", "ledger")
    assert kind in {"ledger", "authority"}
    helper_name = "c3_independent_authority_child.py" if kind == "authority" else "c3_maintenance_ledger_child.py"
    helper = Path(__file__).parent / "helpers" / helper_name
    modes = ({"consume", "before_independent_commit", "after_independent_commit",
              "before_local_commit", "after_local_commit", "sign_failure", "bad_request"}
             if kind == "authority" else {"consume", "before_commit", "after_commit"})
    prefix = [sys.executable, "-I", "-B", str(helper.resolve()), str(tmp_path.resolve())]
    child_env = {"TEMP": str(tmp_path), "TMP": str(tmp_path)}
    if os.name == "nt":
        child_env["SystemRoot"] = os.environ["SystemRoot"]
    processes = []

    def allowed_popen(args, **kwargs):
        if (not isinstance(args, list) or args[:5] != prefix or len(args) != 7
                or args[5] not in modes
                or args[6] not in {"0", "1"}
                or kwargs != dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=child_env, cwd=str(tmp_path))):
            raise AssertionError("only fixed synthetic probe children are permitted")
        child = original_popen(args, **kwargs)
        processes.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", allowed_popen)
    module = importlib.import_module("trade_registry_c3_maintenance_authorization_v1")
    database = tmp_path / "synthetic-ledger.sqlite"
    ledger = module.SQLiteMaintenanceAuthorizationLedgerV1(database, enabled=True)
    ledger.provision()
    authority_database = tmp_path / "synthetic-authority.sqlite"
    if kind == "authority":
        module.SQLiteMaintenanceAuthorizationLedgerV1(authority_database, enabled=True).provision()
    (tmp_path / "synthetic-marker").write_text("synthetic-c3-maintenance-probe-v1")

    def start(mode="consume", participant="0"):
        return subprocess.Popen(prefix + [mode, participant], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=child_env, cwd=str(tmp_path))

    def release(participants):
        deadline = time.monotonic() + 10
        while not all((tmp_path / ("ready-" + p)).exists() for p in participants):
            if time.monotonic() >= deadline or any(p.poll() is not None for p in processes):
                pytest.fail("synthetic child did not reach its start barrier")
            time.sleep(0.01)
        (tmp_path / "release").touch()

    def finish(child, expected_code=0):
        out, err = child.communicate(timeout=20)
        assert child.returncode == expected_code, (child.returncode, err)
        assert not err
        return json.loads(out) if out else None

    yield SimpleNamespace(root=tmp_path, database=database, module=module, ledger=ledger,
                          authority_database=authority_database,
                          start=start, release=release, finish=finish)
    for child in processes:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def rows(probe):
    with closing(sqlite3.connect(probe.database)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return db.execute("SELECT * FROM c3_maintenance_claims").fetchall()


def test_two_real_processes_have_exactly_one_durable_winner(probe):
    children = [probe.start(participant=p) for p in ("0", "1")]
    probe.release(("0", "1"))
    outcomes = [probe.finish(child) for child in children]
    assert sorted(r["consumed"] for r in outcomes) == [False, True]
    assert all(r["synthetic_only"] is True for r in outcomes)
    assert rows(probe) == [("a" * 64, "b" * 64)]
    assert probe.finish(probe.start())["consumed"] is False


@pytest.mark.parametrize("boundary,exit_code,expected_rows,retry", [
    ("before_commit", 71, [], True),
    ("after_commit", 72, [("a" * 64, "b" * 64)], False),
])
def test_abrupt_exit_at_actual_commit_boundary(probe, boundary, exit_code, expected_rows, retry):
    child = probe.start(boundary)
    probe.release(("0",))
    assert probe.finish(child, exit_code) is None
    assert rows(probe) == expected_rows
    assert probe.finish(probe.start())["consumed"] is retry
    assert rows(probe) == [("a" * 64, "b" * 64)]


def test_probe_blocks_network_and_unlisted_commands(probe):
    with pytest.raises(AssertionError, match="external access"):
        socket.create_connection(("127.0.0.1", 1))
    with pytest.raises(AssertionError, match="only fixed synthetic"):
        subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"])


@pytest.mark.skipif(sys.platform != "linux", reason="requires isolated Linux filesystem")
def test_linux_directory_fsync_for_synthetic_ledger(probe):
    fd = os.open(probe.root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    assert rows(probe) == []
