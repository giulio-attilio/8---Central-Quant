"""Full signed authorization in fresh processes, against two synthetic stores."""

from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3

import pytest

from test_c3_maintenance_ledger_process_probe import probe


pytestmark = pytest.mark.parametrize("probe", ["authority"], indirect=True)


def count(database):
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return db.execute("SELECT COUNT(*) FROM c3_maintenance_claims").fetchone()[0]


def backup(source, target):
    with closing(sqlite3.connect(source)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def helper_module():
    path = Path(__file__).parent / "helpers" / "c3_independent_authority_child.py"
    spec = importlib.util.spec_from_file_location("synthetic_authority_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authorization_rejects_replay_from_fresh_process(probe):
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is True
    assert probe.finish(probe.start())["authorized"] is False
    assert count(probe.authority_database) == count(probe.database) == 1


def test_two_processes_receive_exactly_one_signed_authorization(probe):
    children = [probe.start(participant=p) for p in ("0", "1")]
    probe.release(("0", "1"))
    results = [probe.finish(child) for child in children]
    assert sorted(r["authorized"] for r in results) == [False, True]
    assert all(r["synthetic_only"] and not r["live_allowed"] and not r["runtime_integrated"] for r in results)
    assert count(probe.authority_database) == count(probe.database) == 1


@pytest.mark.parametrize("mode,code,independent,local,retry", [
    ("before_independent_commit", 71, 0, 0, True),
    ("after_independent_commit", 72, 1, 0, False),
    ("before_local_commit", 73, 1, 0, False),
    ("after_local_commit", 74, 1, 1, False),
])
def test_actual_process_death_at_each_commit_boundary(probe, mode, code, independent, local, retry):
    child = probe.start(mode)
    probe.release(("0",))
    assert probe.finish(child, code) is None
    assert count(probe.authority_database) == independent and count(probe.database) == local
    assert probe.finish(probe.start())["authorized"] is retry
    assert count(probe.authority_database) == 1


def test_local_backup_restore_does_not_restore_consumed_authorization(probe):
    snapshot = probe.root / "synthetic-local-backup.sqlite"
    backup(probe.database, snapshot)
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is True
    backup(snapshot, probe.database)
    assert count(probe.database) == 0
    assert probe.finish(probe.start())["authorized"] is False
    assert count(probe.authority_database) == 1 and count(probe.database) == 0


def test_signing_failure_burns_claim_without_authorizing(probe):
    child = probe.start("sign_failure")
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is False
    assert count(probe.authority_database) == 1 and count(probe.database) == 0
    assert probe.finish(probe.start())["authorized"] is False


def test_invalid_request_never_consumes_either_store(probe):
    child = probe.start("bad_request")
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is False
    assert count(probe.authority_database) == count(probe.database) == 0


def test_reference_is_default_off_and_does_not_inspect_root(probe):
    class PoisonRoot:
        def __fspath__(self):
            pytest.fail("default-off consumer accessed root")
    consumer = helper_module().SyntheticPersistentConsumer(PoisonRoot())
    assert consumer.consume_once() is None
    assert count(probe.authority_database) == count(probe.database) == 0


def test_missing_authority_store_is_not_recreated(probe):
    probe.authority_database.unlink()  # Only this fixture's newly provisioned synthetic DB.
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is False
    assert not probe.authority_database.exists() and count(probe.database) == 0


def test_invalid_authority_schema_is_rejected(probe):
    with closing(sqlite3.connect(probe.authority_database)) as db:
        db.execute("ALTER TABLE c3_maintenance_claims ADD COLUMN unexpected TEXT")
        db.commit()
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is False
    assert count(probe.database) == count(probe.authority_database) == 0


def test_same_physical_file_cannot_model_independent_storage(probe):
    probe.authority_database.unlink()  # Only the fixture's synthetic DB.
    os.link(probe.database, probe.authority_database)
    assert probe.authority_database.samefile(probe.database)
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is False
    assert count(probe.database) == 0


@pytest.mark.parametrize("clock_values,expected_count", [([110.0], 0), ([100.0, 110.0], 1)])
def test_reference_deadline_before_and_after_commit(probe, clock_values, expected_count):
    helper = helper_module()
    values = iter(clock_values)
    consumer = helper.SyntheticPersistentConsumer(probe.root, enabled=True, clock=lambda: next(values))
    assert consumer.consume_once(namespace_sha256=helper.NAMESPACE, claim_sha256="a" * 64,
        payload_sha256="b" * 64, challenge_sha256="c" * 64, deadline=110.0) is None
    assert count(probe.authority_database) == expected_count and count(probe.database) == 0


def test_negative_control_joint_restore_is_not_protected_by_this_reference(probe):
    """Characterize the trust limit, NOT production safety acceptance.

    Rolling back the allegedly independent store violates the model assumption;
    two files on one host must not be represented as an anti-rollback service.
    """
    local_backup = probe.root / "synthetic-local-snapshot.sqlite"
    independent_backup = probe.root / "synthetic-independent-snapshot.sqlite"
    backup(probe.database, local_backup)
    backup(probe.authority_database, independent_backup)
    child = probe.start()
    probe.release(("0",))
    assert probe.finish(child)["authorized"] is True
    backup(local_backup, probe.database)
    backup(independent_backup, probe.authority_database)
    assert probe.finish(probe.start())["authorized"] is True
