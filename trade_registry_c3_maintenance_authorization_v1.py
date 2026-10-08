"""Default-off authorization ports; no inferred key, database or runtime wiring.

The signer, pinned key epoch and revocation source are trusted provisioning
dependencies. Only synthetic keys and temporary databases are used in tests.
The ledger retains consumed nonces across verifier reconstruction; expiry never
deletes replay history. Its database must be explicitly provisioned beforehand.
Authorization additionally requires a signed one-shot consumption receipt from
an independent trusted authority; the local ledger alone is not anti-rollback.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from trade_registry_c3_maintenance_activation_offline_v1 import AuthorizationBindingV1, OFFLINE_MAINTENANCE_SCOPE
import trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2 as authority_adapters


def _sha(value: Any) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()


def maintenance_authorization_payload_sha256(binding: AuthorizationBindingV1, key_epoch: int) -> str:
    return _digest({
        "domain": "C3_MAINTENANCE_AUTHORIZATION_V1",
        "scope": binding.scope,
        "storage_root_binding_sha256": binding.storage_root_binding_sha256,
        "nonce": binding.nonce,
        "deadline": binding.deadline,
        "writer_count": binding.writer_count,
        "maintenance_only": binding.maintenance_only,
        "key_epoch": key_epoch,
    })


@dataclass(frozen=True, repr=False)
class MonotonicConsumptionReceiptV1:
    namespace_sha256: str
    claim_sha256: str
    payload_sha256: str
    challenge_sha256: str
    deadline: float
    committed: bool
    signature_sha256: str

    def __repr__(self) -> str:
        return "<MonotonicConsumptionReceiptV1 protected>"


def monotonic_consumption_receipt_sha256(receipt: MonotonicConsumptionReceiptV1) -> str:
    return _digest({
        "domain": "C3_MONOTONIC_CONSUMPTION_RECEIPT_V1",
        "namespace": receipt.namespace_sha256, "claim": receipt.claim_sha256,
        "payload": receipt.payload_sha256, "challenge": receipt.challenge_sha256,
        "deadline": receipt.deadline, "committed": receipt.committed,
    })


class SQLiteMaintenanceAuthorizationLedgerV1:
    """Local append-only record, not an independent authorization authority.

    Restoring this file can undo its history; use the authenticated composition
    below for authorization. Disabled construction has no I/O.
    """

    def __init__(self, database: Path | None = None, *, enabled: bool = False):
        self._database = database
        self._enabled = enabled is True

    def __repr__(self) -> str:
        return "<SQLiteMaintenanceAuthorizationLedgerV1 protected>"

    def storage_binding_sha256(self) -> str | None:
        if not self._enabled or not isinstance(self._database, Path):
            return None
        return _digest({"domain": "C3_MAINTENANCE_AUTHORIZATION_LEDGER_V1",
                        "database": str(self._database.absolute())})

    def _uri(self, mode: str) -> str:
        if not self._enabled or not isinstance(self._database, Path):
            raise RuntimeError("C3_AUTHORIZATION_LEDGER_DEFAULT_OFF")
        return self._database.absolute().as_uri() + "?mode=" + mode

    @staticmethod
    def _schema_valid(connection) -> bool:
        fields = connection.execute("PRAGMA table_info(c3_maintenance_claims)").fetchall()
        triggers = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name='c3_maintenance_claims'"
        ).fetchone()
        return triggers is None and [(r[1], r[2], r[3], r[5]) for r in fields] == [
            ("claim_sha256", "TEXT", 1, 1), ("payload_sha256", "TEXT", 1, 0),
        ]

    def provision(self) -> None:
        """Explicit provisioning only; never called by authorization or startup."""
        with closing(sqlite3.connect(self._uri("rwc"), uri=True, timeout=1)) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS c3_maintenance_claims ("
                       "claim_sha256 TEXT NOT NULL PRIMARY KEY, payload_sha256 TEXT NOT NULL)")
            if not self._schema_valid(db):
                raise RuntimeError("C3_AUTHORIZATION_LEDGER_SCHEMA_INVALID")
            db.commit()

    def consume_once(self, *, claim_sha256: str, payload_sha256: str) -> bool:
        if not self._enabled or not _sha(claim_sha256) or not _sha(payload_sha256):
            return False
        try:
            with closing(sqlite3.connect(self._uri("rw"), uri=True, timeout=1)) as db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                if not self._schema_valid(db):
                    return False
                db.execute("INSERT INTO c3_maintenance_claims VALUES (?, ?)",
                           (claim_sha256, payload_sha256))
                db.commit()
                return db.execute("SELECT payload_sha256 FROM c3_maintenance_claims WHERE claim_sha256=?",
                                  (claim_sha256,)).fetchone() == (payload_sha256,)
        except Exception:
            # A failed/ambiguous commit must never authorize a retry.
            return False


@dataclass(frozen=True)
class MaintenanceAuthorityConfigV1:
    enabled: bool = False
    pinned_key_id_sha256: str | None = field(default=None, repr=False)
    pinned_storage_root_sha256: str | None = field(default=None, repr=False)
    pinned_ledger_storage_sha256: str | None = field(default=None, repr=False)
    key_epoch: int = 0
    pinned_consumption_namespace_sha256: str | None = field(default=None, repr=False)
    pinned_consumption_key_id_sha256: str | None = field(default=None, repr=False)
    consumption_key_epoch: int = 0


class AuthenticatedMaintenanceAuthorizationV1:
    """Require independent signed consumption before local durable one-shot use.

    The injected consumer must atomically burn (namespace, claim), retaining it
    across restarts, key rotation and restoration of the local ledger. It must
    sign ONLY the first successful consumption, never reissue a grant on retry.
    Its authenticated durable storage must be outside the local backup domain.
    This module supplies no operational consumer and cannot attest its storage.
    A lost response or any subsequent local failure burns the request; no retry
    or compensation is attempted. Deadlines are cooperative at injected ports.
    """

    def __init__(self, *, config: MaintenanceAuthorityConfigV1 | None = None,
                 signature_verifier=None, revocation_source=None, ledger=None, clock=None,
                 monotonic_consumer=None, consumption_verifier=None):
        self._config = config or MaintenanceAuthorityConfigV1()
        self._verifier = signature_verifier
        self._revocations = revocation_source
        self._ledger = ledger
        self._clock = clock
        self._consumer = monotonic_consumer
        self._consumption_verifier = consumption_verifier

    def __repr__(self) -> str:
        return "<AuthenticatedMaintenanceAuthorizationV1 protected>"

    def _not_revoked(self, now: float) -> bool:
        config = self._config
        return all(self._revocations.root_authority_key_revoked_v2(
            key_id_sha256=key, key_epoch=epoch, now_epoch=int(now),
        ) is False for key, epoch in (
            (config.pinned_key_id_sha256, config.key_epoch),
            (config.pinned_consumption_key_id_sha256, config.consumption_key_epoch),
        ))

    def __call__(self, request: Any, binding: AuthorizationBindingV1) -> bool:
        config = self._config
        if config.enabled is not True:
            return False
        try:
            if not (
                type(binding) is AuthorizationBindingV1
                and binding.scope == OFFLINE_MAINTENANCE_SCOPE
                and binding.maintenance_only is True
                and type(binding.writer_count) is int and binding.writer_count == 19
                and type(binding.nonce) is str and 1 <= len(binding.nonce) <= 256
                and type(binding.deadline) in (int, float) and math.isfinite(binding.deadline)
                and _sha(config.pinned_key_id_sha256)
                and _sha(config.pinned_storage_root_sha256)
                and binding.storage_root_binding_sha256 == config.pinned_storage_root_sha256
                and type(config.key_epoch) is int and config.key_epoch >= 1
                and type(self._verifier) is authority_adapters.InjectedRootAuthorityVerifierV2
                and type(self._ledger) is SQLiteMaintenanceAuthorizationLedgerV1
                and _sha(config.pinned_ledger_storage_sha256)
                and self._ledger.storage_binding_sha256() == config.pinned_ledger_storage_sha256
                and _sha(config.pinned_consumption_namespace_sha256)
                and _sha(config.pinned_consumption_key_id_sha256)
                and type(config.consumption_key_epoch) is int and config.consumption_key_epoch >= 1
                and type(self._consumption_verifier) is authority_adapters.InjectedRootAuthorityVerifierV2
                and callable(getattr(self._consumer, "consume_once", None))
                and isinstance(request, Mapping)
                and set(request) == {"payload_sha256", "signature_sha256"}
                and _sha(request["payload_sha256"]) and _sha(request["signature_sha256"])
            ):
                return False
            payload_sha = maintenance_authorization_payload_sha256(binding, config.key_epoch)
            if request["payload_sha256"] != payload_sha:
                return False
            now = self._clock()
            if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now < binding.deadline:
                return False
            if not self._not_revoked(now):
                return False
            if self._verifier.verify_root_authority_signature_v2(
                key_id_sha256=config.pinned_key_id_sha256, payload_sha256=payload_sha,
                signature_sha256=request["signature_sha256"],
            ) is not True:
                return False
            after = self._clock()
            if type(after) not in (int, float) or not math.isfinite(after) or not now <= after < binding.deadline:
                return False
            if not self._not_revoked(after):
                return False
            claim = _digest({"scope": binding.scope, "root": binding.storage_root_binding_sha256,
                             "nonce": binding.nonce})
            # Fresh OS randomness is independent of the restored ledger and
            # prevents replay of an old signed receipt, even in a new process.
            challenge = os.urandom(32).hex()
            receipt = self._consumer.consume_once(
                namespace_sha256=config.pinned_consumption_namespace_sha256,
                claim_sha256=claim, payload_sha256=payload_sha,
                challenge_sha256=challenge, deadline=binding.deadline,
            )
            if not (
                type(receipt) is MonotonicConsumptionReceiptV1
                and receipt.namespace_sha256 == config.pinned_consumption_namespace_sha256
                and receipt.claim_sha256 == claim and receipt.payload_sha256 == payload_sha
                and receipt.challenge_sha256 == challenge
                and type(receipt.deadline) in (int, float) and receipt.deadline == binding.deadline
                and receipt.committed is True and _sha(receipt.signature_sha256)
            ):
                return False
            if self._consumption_verifier.verify_root_authority_signature_v2(
                key_id_sha256=config.pinned_consumption_key_id_sha256,
                payload_sha256=monotonic_consumption_receipt_sha256(receipt),
                signature_sha256=receipt.signature_sha256,
            ) is not True:
                return False
            consumed_at = self._clock()
            if (type(consumed_at) not in (int, float) or not math.isfinite(consumed_at)
                    or not after <= consumed_at < binding.deadline or not self._not_revoked(consumed_at)):
                return False
            if self._ledger.consume_once(claim_sha256=claim, payload_sha256=payload_sha) is not True:
                return False
            committed_at = self._clock()
            if (type(committed_at) not in (int, float) or not math.isfinite(committed_at)
                    or not consumed_at <= committed_at < binding.deadline):
                return False
            return self._not_revoked(committed_at)
        except Exception:
            return False
