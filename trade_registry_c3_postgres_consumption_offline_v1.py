"""Default-off PostgreSQL consumption experiment, NOT a production authority.

No driver import, DSN lookup, provisioning, runtime wiring or automatic retry.
Only an explicitly injected fresh connection and signer may be used. The lab
uses a private Unix socket, synthetic data and public test keys. Database pins
detect substitution, not rollback of a backup that contains the same identity.
The connector, administrator and signer remain trusted dependencies.
"""

from dataclasses import dataclass, field, replace
import math

from trade_registry_c3_maintenance_authorization_v1 import (
    MonotonicConsumptionReceiptV1, _sha, monotonic_consumption_receipt_sha256,
)


OFFLINE_SCOPE = "C3_POSTGRES_SYNTHETIC_CONSUMPTION_V1"


@dataclass(frozen=True)
class PostgresConsumptionConfigV1:
    enabled: bool = False
    scope: str | None = None
    namespace_sha256: str | None = field(default=None, repr=False)
    instance_sha256: str | None = field(default=None, repr=False)
    max_duration_seconds: float = 5.0


@dataclass(frozen=True, repr=False)
class CommittedDigestOfflineV1:
    """Unsigned storage outcome; never an authorization by itself."""
    digest: str
    committed_at: float
    deadline: float

    def __repr__(self):
        return "<CommittedDigestOfflineV1 synthetic-only protected>"


# Fixed, schema-qualified objects. Provisioning belongs ONLY to the lab.
_TABLES_SQL = """
SELECT c.relname, c.relkind, c.relpersistence, c.relrowsecurity,
       c.relforcerowsecurity, c.relowner = r.oid,
       has_table_privilege(c.oid, 'UPDATE,DELETE,TRUNCATE,TRIGGER'),
       EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgrelid=c.oid),
       EXISTS (SELECT 1 FROM pg_catalog.pg_rewrite w WHERE w.ev_class=c.oid)
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN pg_catalog.pg_roles r
WHERE n.nspname='c3_authority' AND c.relname IN ('instance', 'claims')
AND r.rolname=current_user ORDER BY c.relname
"""
_COLUMNS_SQL = """
SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod),
       a.attnotnull, a.atthasdef, a.attidentity, a.attgenerated
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='c3_authority' AND c.relname IN ('instance','claims')
AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum
"""
_EXPECTED_COLUMNS = [
    (table, name, "text", True, False, "", "")
    for table, names in (("claims", ("namespace_sha256", "claim_sha256", "receipt_sha256")),
                         ("instance", ("instance_sha256",))) for name in names
]


class PostgresConsumptionOfflineV1:
    """One successful durable INSERT may produce one signed receipt.

    A fresh, idle, non-autocommit connection is required. Its factory must obey
    timeout_seconds, must not consult environment credentials, and must target
    only the synthetic laboratory. Deadlines at injected ports are cooperative;
    SQL statement/lock/transaction timeouts additionally bound server work.
    An uncertain commit, failed signature or late response produces no receipt;
    a committed claim is never deleted or signed again.
    """

    def __init__(self, *, config=None, connect=None, signer=None, clock=None):
        self._config = config or PostgresConsumptionConfigV1()
        self._connect, self._signer, self._clock = connect, signer, clock

    def __repr__(self):
        return "<PostgresConsumptionOfflineV1 synthetic-only protected>"

    def _now(self, floor, deadline):
        now = self._clock()
        if type(now) not in (int, float) or not math.isfinite(now) or not floor <= now < deadline:
            raise ValueError("C3_POSTGRES_DEADLINE")
        return now

    def _schema_valid(self, db):
        if db.execute(_TABLES_SQL).fetchall() != [
            (name, "r", "p", False, False, False, False, False, False)
            for name in ("claims", "instance")
        ]:
            return False
        if db.execute(_COLUMNS_SQL).fetchall() != _EXPECTED_COLUMNS:
            return False
        # Require the exact immediate primary key, not a caller assertion.
        if db.execute("""SELECT conkey::smallint[], condeferrable, convalidated
            FROM pg_catalog.pg_constraint WHERE conrelid='c3_authority.claims'::regclass
            AND contype='p'""").fetchall() != [([1, 2], False, True)]:
            return False
        if db.execute("""SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication,
            rolbypassrls, has_schema_privilege('c3_authority','CREATE'),
            has_table_privilege('c3_authority.instance','INSERT'),
            pg_has_role(current_user, c.relowner, 'MEMBER')
            FROM pg_catalog.pg_roles r CROSS JOIN pg_catalog.pg_class c
            WHERE r.rolname=current_user AND c.oid='c3_authority.claims'::regclass
            """).fetchone() != (False,) * 8:
            return False
        return db.execute("SELECT instance_sha256 FROM c3_authority.instance").fetchall() == [
            (self._config.instance_sha256,)
        ]

    def consume_once(self, *, namespace_sha256=None, claim_sha256=None,
                     payload_sha256=None, challenge_sha256=None, deadline=None):
        if self._config.enabled is not True:
            return None
        try:
            if not all(_sha(v) for v in (payload_sha256, challenge_sha256)) or not callable(self._signer):
                return None
            receipt = MonotonicConsumptionReceiptV1(namespace_sha256, claim_sha256,
                payload_sha256, challenge_sha256, deadline, True, "")
            digest = monotonic_consumption_receipt_sha256(receipt)
            committed = self.commit_digest_once(namespace_sha256=namespace_sha256,
                claim_sha256=claim_sha256, digest=digest, deadline=deadline)
            if type(committed) is not CommittedDigestOfflineV1:
                return None
            signature = self._signer(digest)
            self._now(committed.committed_at, committed.deadline)
            return replace(receipt, signature_sha256=signature) if _sha(signature) else None
        except Exception:
            return None

    def commit_digest_once(self, *, namespace_sha256=None, claim_sha256=None,
                           digest=None, deadline=None):
        """Shared storage primitive. No signature, runtime grant or readiness."""
        cfg = self._config
        if cfg.enabled is not True:
            return None
        db = None
        try:
            if (cfg.scope != OFFLINE_SCOPE or not _sha(cfg.instance_sha256)
                    or not _sha(cfg.namespace_sha256) or namespace_sha256 != cfg.namespace_sha256
                    or any(not _sha(v) for v in (claim_sha256, digest))
                    or type(deadline) not in (int, float) or not math.isfinite(deadline)
                    or type(cfg.max_duration_seconds) not in (int, float)
                    or not 0 < cfg.max_duration_seconds <= 5
                    or not all(callable(p) for p in (self._connect, self._clock))):
                return None
            now = self._now(0, deadline)
            limit = min(deadline, now + cfg.max_duration_seconds)
            db = self._connect(timeout_seconds=limit - now)
            # A pooled/open transaction or autocommit could weaken our boundary.
            if db.autocommit is not False or db.info.transaction_status != 0:
                return None
            now = self._now(now, limit)
            milliseconds = max(1, int((limit - now) * 1000))
            db.execute("SELECT set_config('search_path','pg_catalog',true)")
            db.execute("SELECT set_config('synchronous_commit','on',true)")
            for setting in ("statement_timeout", "lock_timeout", "transaction_timeout"):
                db.execute("SELECT set_config(%s,%s,true)", (setting, str(milliseconds)))
            if db.execute("SELECT current_setting('fsync'), current_setting('synchronous_commit'), "
                          "pg_is_in_recovery()").fetchone() != ("on", "on", False):
                return None
            if not self._schema_valid(db):
                return None
            now = self._now(now, limit)
            result = db.execute("""INSERT INTO c3_authority.claims
                (namespace_sha256,claim_sha256,receipt_sha256) VALUES (%s,%s,%s)
                ON CONFLICT (namespace_sha256,claim_sha256) DO NOTHING RETURNING receipt_sha256""",
                (namespace_sha256, claim_sha256, digest)).fetchone()
            if result != (digest,):
                return None
            now = self._now(now, limit)
            db.commit()  # No receipt before acknowledged commit; never retry here.
            now = self._now(now, limit)
            db.close()
            db = None
            return CommittedDigestOfflineV1(digest, now, limit)
        except Exception:
            # Do not leak SQL, endpoints, parameters or signing details.
            return None
        finally:
            if db is not None:
                try:
                    db.close()  # An uncommitted transaction is discarded, not committed.
                except Exception:
                    pass
