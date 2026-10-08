"""Real PostgreSQL, only in the explicit sealed synthetic laboratory."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import hashlib
import hmac
import os
import sqlite3
import time

import pytest

from helpers.c3_postgres_fixture import pg, no_external_access, INSTANCE, NAMESPACE


KEY = b"public-fake-postgres-consumption-signing-key-for-lab"
REQUEST = dict(namespace_sha256=NAMESPACE, claim_sha256="a" * 64,
               payload_sha256="b" * 64, challenge_sha256="c" * 64, deadline=110.0)


def build(pg, **overrides):
    import trade_registry_c3_postgres_consumption_offline_v1 as m
    opts = dict(config=m.PostgresConsumptionConfigV1(enabled=True, scope=m.OFFLINE_SCOPE,
        namespace_sha256=NAMESPACE, instance_sha256=INSTANCE), connect=pg.connect,
        clock=lambda: 100.0, signer=lambda d: hmac.new(KEY, d.encode("ascii"), hashlib.sha256).hexdigest())
    return m.PostgresConsumptionOfflineV1(**(opts | overrides))


def test_default_off_no_io(no_external_access):
    import trade_registry_c3_postgres_consumption_offline_v1 as m
    def bomb(*args, **kwargs):
        pytest.fail("dormant adapter touched dependency")
    assert m.PostgresConsumptionOfflineV1(connect=bomb, clock=bomb, signer=bomb).consume_once() is None


@pytest.mark.parametrize("changes", [dict(scope="runtime"), dict(instance_sha256=None),
    dict(namespace_sha256=None), dict(max_duration_seconds=0), dict(max_duration_seconds=True)])
def test_invalid_config_rejected_before_io(no_external_access, changes):
    import trade_registry_c3_postgres_consumption_offline_v1 as m
    cfg = m.PostgresConsumptionConfigV1(enabled=True, scope=m.OFFLINE_SCOPE,
        instance_sha256=INSTANCE, namespace_sha256=NAMESPACE)
    def bomb(*args, **kwargs):
        pytest.fail("invalid config accessed a dependency")
    assert m.PostgresConsumptionOfflineV1(config=replace(cfg, **changes), connect=bomb,
        signer=bomb, clock=bomb).consume_once(**REQUEST) is None


def test_commit_before_signature_and_no_reissue(pg):
    def sign(digest):
        assert pg.count() == 1  # Separate connection observes committed row.
        return "f" * 64
    consumer = build(pg, signer=sign)
    receipt = consumer.consume_once(**REQUEST)
    assert receipt is not None and receipt.committed is True
    assert receipt.challenge_sha256 == REQUEST["challenge_sha256"]
    assert build(pg).consume_once(**(REQUEST | {"challenge_sha256": "f" * 64})) is None
    assert pg.count() == 1
    assert "a" * 64 not in repr(receipt) and str(pg.root) not in repr(consumer)


def test_concurrent_connections_exactly_one_winner(pg):
    import threading
    ready = threading.Barrier(4)
    def consume(i):
        ready.wait(timeout=5)
        return build(pg).consume_once(**(REQUEST | {"challenge_sha256": str(i) * 64}))
    with ThreadPoolExecutor(4) as pool:
        outcomes = list(pool.map(consume, range(4)))
    assert sum(r is not None for r in outcomes) == 1 and pg.count() == 1


class FaultConnection:
    def __init__(self, connection, mode):
        self.connection, self.mode = connection, mode
    def __getattr__(self, key):
        return getattr(self.connection, key)
    def commit(self):
        if self.mode.startswith("after"):
            self.connection.commit()
        if self.mode.endswith("death"):
            os._exit(81)
        raise TimeoutError("synthetic commit ambiguity")


@pytest.mark.parametrize("mode,count", [("before_timeout", 0), ("after_timeout", 1)])
def test_commit_error_never_signs(pg, mode, count):
    def sign(_):
        pytest.fail("signed an unacknowledged commit")
    c = build(pg, signer=sign, connect=lambda **kw: FaultConnection(pg.connect(**kw), mode))
    assert c.consume_once(**REQUEST) is None and pg.count() == count
    if count:
        assert build(pg).consume_once(**REQUEST) is None


@pytest.mark.parametrize("mode,count", [("before_death", 0), ("after_death", 1)])
def test_actual_client_process_death(pg, mode, count):
    pid = os.fork()
    if pid == 0:
        try:
            c = build(pg, connect=lambda **kw: FaultConnection(pg.connect(**kw), mode))
            c.consume_once(**REQUEST)
        finally:
            os._exit(82)
    end = time.monotonic() + 10
    while True:
        child, status = os.waitpid(pid, os.WNOHANG)
        if child:
            break
        if time.monotonic() > end:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            pytest.fail("synthetic child deadline")
        time.sleep(0.01)
    assert os.waitstatus_to_exitcode(status) == 81 and pg.count() == count
    assert (build(pg).consume_once(**REQUEST) is not None) is (count == 0)


def test_postgres_crash_recovery_retains_consumption(pg):
    assert build(pg).consume_once(**REQUEST) is not None
    pg.stop("immediate")
    pg.start()
    assert pg.count() == 1 and build(pg).consume_once(**REQUEST) is None


@pytest.mark.parametrize("signer", [lambda _: None, lambda _: "invalid"])
def test_bad_signature_burns_claim(pg, signer):
    assert build(pg, signer=signer).consume_once(**REQUEST) is None
    assert pg.count() == 1 and build(pg).consume_once(**REQUEST) is None


def test_signing_exception_burns_claim(pg):
    def fail(_):
        raise RuntimeError("synthetic signing failure")
    assert build(pg, signer=fail).consume_once(**REQUEST) is None
    assert pg.count() == 1


@pytest.mark.parametrize("change", [dict(namespace_sha256="f" * 64), dict(deadline=100.0),
    dict(deadline=float("nan")), dict(claim_sha256=True), dict(payload_sha256="'; DROP TABLE x;")])
def test_invalid_request_has_no_consumption(pg, change):
    assert build(pg).consume_once(**(REQUEST | change)) is None and pg.count() == 0


@pytest.mark.parametrize("sql", [
    "ALTER TABLE c3_authority.claims ADD COLUMN unexpected text",
    "ALTER TABLE c3_authority.claims DROP CONSTRAINT claims_pkey",
    "ALTER TABLE c3_authority.claims SET UNLOGGED",
    "ALTER TABLE c3_authority.claims ENABLE ROW LEVEL SECURITY",
    "GRANT DELETE ON c3_authority.claims TO c3_writer",
    "GRANT CREATE ON SCHEMA c3_authority TO c3_writer",
    "GRANT INSERT ON c3_authority.instance TO c3_writer",
    "UPDATE c3_authority.instance SET instance_sha256=repeat('f',64)",
    "DROP TABLE c3_authority.claims",
])
def test_schema_privilege_and_identity_drift_fail_closed(pg, sql):
    with pg.admin() as db:
        db.execute(sql)
    assert build(pg).consume_once(**REQUEST) is None


def test_owner_connection_rejected(pg):
    assert build(pg, connect=lambda **_: pg.admin()).consume_once(**REQUEST) is None
    assert pg.count() == 0


def test_restricted_role_cannot_erase_consumption(pg):
    assert build(pg).consume_once(**REQUEST) is not None
    for sql in ("DELETE FROM c3_authority.claims", "TRUNCATE c3_authority.claims",
                "UPDATE c3_authority.claims SET receipt_sha256=repeat('0',64)",
                "DROP TABLE c3_authority.claims"):
        with pytest.raises(pg.psycopg.errors.InsufficientPrivilege):
            with pg.connect() as db:
                db.execute(sql)
    assert pg.count() == 1 and build(pg).consume_once(**REQUEST) is None


@pytest.mark.parametrize("mode", ["autocommit", "transaction"])
def test_nonfresh_connection_rejected(pg, mode):
    def connect(**kw):
        db = pg.connect(**kw)
        if mode == "autocommit":
            db.autocommit = True
        else:
            db.execute("SELECT 1")
        return db
    assert build(pg, connect=connect).consume_once(**REQUEST) is None and pg.count() == 0


def test_lock_deadline_fails_closed(pg):
    import trade_registry_c3_postgres_consumption_offline_v1 as m
    cfg = m.PostgresConsumptionConfigV1(enabled=True, scope=m.OFFLINE_SCOPE,
        namespace_sha256=NAMESPACE, instance_sha256=INSTANCE, max_duration_seconds=0.15)
    with pg.admin() as db:
        db.execute("LOCK TABLE c3_authority.claims IN ACCESS EXCLUSIVE MODE")
        begin = time.monotonic()
        assert build(pg, config=cfg).consume_once(**REQUEST) is None
        assert time.monotonic() - begin < 3
    assert pg.count() == 0


def test_deadline_after_commit_burns_without_signing(pg):
    times = iter([100.0] * 4 + [110.0])
    assert build(pg, clock=lambda: next(times)).consume_once(**REQUEST) is None
    assert pg.count() == 1


def test_restore_local_ledger_cannot_reuse_full_signed_authorization(pg, tmp_path):
    import trade_registry_c3_maintenance_authorization_v1 as m
    from helpers.c3_independent_authority_child import build_synthetic_authority, signature, CONSUMPTION_KEY
    root = tmp_path / "synthetic-local"
    root.mkdir()
    ledger = m.SQLiteMaintenanceAuthorizationLedgerV1(root / "synthetic-ledger.sqlite", enabled=True)
    ledger.provision()
    authority, binding, request = build_synthetic_authority(root)
    # Preserve the original independent-verifier keys and namespace of the full chain.
    from helpers.c3_independent_authority_child import NAMESPACE as signed_namespace
    consumer = build(pg, signer=lambda d: signature(CONSUMPTION_KEY, d))
    consumer._config = replace(consumer._config, namespace_sha256=signed_namespace)
    authority._consumer = consumer
    backup = root / "synthetic-backup.sqlite"
    with closing(sqlite3.connect(ledger._database)) as src, closing(sqlite3.connect(backup)) as dst:
        src.backup(dst)
    assert authority(request, binding) is True
    with closing(sqlite3.connect(backup)) as src, closing(sqlite3.connect(ledger._database)) as dst:
        src.backup(dst)
    rebuilt, binding2, request2 = build_synthetic_authority(root)
    rebuilt._consumer = consumer
    assert rebuilt(request2, binding2) is False and pg.count() == 1


def test_negative_control_same_identity_authority_backup_is_not_antirollback(pg):
    """Passing this test demonstrates the remaining trust limit, not readiness."""
    snapshot = pg.backup()
    assert build(pg).consume_once(**REQUEST) is not None
    pg.restore(snapshot)
    restored = build(pg, connect=lambda **kw: pg.connect(database="synthetic_restore", **kw))
    assert restored.consume_once(**REQUEST) is not None


def test_restored_instance_with_new_identity_is_rejected(pg):
    snapshot = pg.backup()
    pg.restore(snapshot)
    with pg.connect(user="cq-c3-lab", database="synthetic_restore") as db:
        db.execute("UPDATE c3_authority.instance SET instance_sha256=repeat('f',64)")
    restored = build(pg, connect=lambda **kw: pg.connect(database="synthetic_restore", **kw))
    assert restored.consume_once(**REQUEST) is None
